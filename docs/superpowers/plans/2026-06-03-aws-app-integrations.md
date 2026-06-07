# AWS-1 — App-side cloud integrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `S3TranscriptStore` (RA-3c `TranscriptStore` backend, config-selected) and `SecretsManagerResolver` + `CompositeCredentialResolver` (OMS broker creds), behind optional `boto3` extras, verifiable on LocalStack with no AWS account.

**Architecture:** Sync `boto3` off-loaded via `asyncio.to_thread` for the async S3 store; sync+cached `boto3` for the sync `CredentialResolver`. Config-driven factories (`make_transcript_store`, `make_credential_resolver`) so worker/API/OMS call sites are untouched. `boto3` stays ABSENT in the default env; cloud round-trips are LocalStack-gated, with pure routing/selection tests in the always-on gate.

**Tech Stack:** Python 3.12, boto3 (optional extra), LocalStack, pytest. No migration, no new endpoints.

**Spec:** `docs/superpowers/specs/2026-06-03-aws-app-integrations-design.md`

**Conventions for every task:**
- Repo root: `c:/Users/sreek/myprojects/saalr-demo/SAALR F2F`. Bash tool available (Windows).
- Lint: `uvx ruff check <paths>` (line length 100).
- Commit footer (after a blank line): `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Git: stage ONLY the listed files. Never `git add -A`/`.`. Never stage `.gitignore`, `.env`, `uv.lock`, or `tools/`.
- **LocalStack gated tests:** `boto3` is an optional extra NOT in the default env. To run the gated round-trip tests: bring up LocalStack (`docker compose -f infra/docker/docker-compose.localstack.yml up -d`), `uv pip install boto3`, then run with `AWS_ENDPOINT_URL=http://localhost:4566 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 uv run --no-sync pytest <file>`, then `git checkout uv.lock` (the `uv pip install` mutates it — do NOT commit it). Without LocalStack/boto3 the gated tests SKIP cleanly; the pure tests are the hard TDD gate.

---

### Task 1: `S3TranscriptStore` + config + LocalStack

**Files:**
- Modify: `packages/core/saalr_core/config.py` (AWS settings)
- Modify: `packages/core/pyproject.toml` (`aws` extra)
- Modify: `packages/core/saalr_core/research/transcript_store.py` (add `S3TranscriptStore`, select in `make_transcript_store`)
- Create: `infra/docker/docker-compose.localstack.yml`
- Test (pure, default gate): `packages/core/tests/test_transcript_store_select.py`
- Test (LocalStack-gated): `packages/core/tests/test_s3_transcript_store.py`

- [ ] **Step 1: Config + extra + LocalStack compose**

In `packages/core/saalr_core/config.py`, add to `Settings` after the `llm_monthly_budget_usd` line:
```python
    # AWS (app-side integrations; AWS-1)
    aws_region: str | None = None
    aws_endpoint_url: str | None = None   # LocalStack/MinIO override for S3 + Secrets Manager
    transcript_s3_bucket: str | None = None
```

In `packages/core/pyproject.toml`, extend the optional-dependencies (it currently has `openai` + `anthropic`):
```toml
[project.optional-dependencies]
openai = ["openai>=1.40"]
anthropic = ["anthropic>=0.40"]
aws = ["boto3>=1.34"]
```

Create `infra/docker/docker-compose.localstack.yml`:
```yaml
# LocalStack for AWS-1 app-side integration tests (S3 + Secrets Manager).
# Usage: docker compose -f infra/docker/docker-compose.localstack.yml up -d
#   then export AWS_ENDPOINT_URL=http://localhost:4566 AWS_ACCESS_KEY_ID=test \
#              AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
services:
  localstack:
    image: localstack/localstack:3
    ports:
      - "4566:4566"
    environment:
      - SERVICES=s3,secretsmanager
      - DEBUG=0
```

- [ ] **Step 2: Write the failing pure select test**

Create `packages/core/tests/test_transcript_store_select.py`:
```python
from saalr_core.research.transcript_store import (
    DbTranscriptStore,
    S3TranscriptStore,
    make_transcript_store,
)


class _Settings:
    def __init__(self, bucket=None, region=None, endpoint_url=None):
        self.transcript_s3_bucket = bucket
        self.aws_region = region
        self.aws_endpoint_url = endpoint_url


def test_make_transcript_store_picks_s3_when_bucket_set():
    store = make_transcript_store(_Settings(bucket="b", region="us-east-1"), object())
    assert isinstance(store, S3TranscriptStore)


def test_make_transcript_store_defaults_to_db():
    store = make_transcript_store(_Settings(bucket=None), object())
    assert isinstance(store, DbTranscriptStore)
```
(Constructing `S3TranscriptStore` imports no boto3 — the SDK is lazy — so this runs in the default gate.)

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest packages/core/tests/test_transcript_store_select.py -q`
Expected: FAIL — `cannot import name 'S3TranscriptStore'`.

- [ ] **Step 4: Implement `S3TranscriptStore` + selection**

In `packages/core/saalr_core/research/transcript_store.py`:
- Add stdlib imports at the top (after `from __future__ import annotations`):
```python
import asyncio
import json
```
- Add the `S3TranscriptStore` class (after `DbTranscriptStore`):
```python
class S3TranscriptStore:
    """S3-backed transcript store. Sync boto3 is off-loaded via asyncio.to_thread so the async
    TranscriptStore interface holds no thread/loop. boto3 is imported lazily (optional `aws` extra)."""

    def __init__(self, bucket, *, client=None, region=None, endpoint_url=None, prefix="transcripts"):
        self._bucket = bucket
        self._client = client            # injectable for tests; else lazy-built
        self._region = region
        self._endpoint = endpoint_url
        self._prefix = prefix

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("s3", region_name=self._region, endpoint_url=self._endpoint)
        return self._client

    def _key(self, tenant_id, note_id) -> str:
        return f"{self._prefix}/{tenant_id}/{note_id}.json"

    async def save(self, *, tenant_id, note_id, steps: list[dict]) -> None:
        client = self._get_client()
        body = json.dumps(steps).encode("utf-8")
        await asyncio.to_thread(
            client.put_object, Bucket=self._bucket, Key=self._key(tenant_id, note_id),
            Body=body, ContentType="application/json")

    async def load(self, *, tenant_id, note_id) -> list[dict] | None:
        client = self._get_client()
        try:
            resp = await asyncio.to_thread(
                client.get_object, Bucket=self._bucket, Key=self._key(tenant_id, note_id))
        except client.exceptions.NoSuchKey:
            return None
        body = await asyncio.to_thread(resp["Body"].read)
        return json.loads(body)
```
- Replace `make_transcript_store` with the config-driven version:
```python
def make_transcript_store(settings, sessionmaker) -> TranscriptStore:
    """S3 store when `transcript_s3_bucket` is configured, else the Postgres store."""
    bucket = getattr(settings, "transcript_s3_bucket", None)
    if bucket:
        return S3TranscriptStore(
            bucket, region=getattr(settings, "aws_region", None),
            endpoint_url=getattr(settings, "aws_endpoint_url", None))
    return DbTranscriptStore(sessionmaker)
```

- [ ] **Step 5: Run the pure test + RA-3c regression**

Run: `uv run pytest packages/core/tests/test_transcript_store_select.py -q`
Expected: PASS (2 passed).
Run (DB env prefix — confirms the DB path is unchanged when no bucket is set):
`ADMIN_DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:55432/saalr" APP_DATABASE_URL="postgresql+asyncpg://saalr_app:saalr_app@localhost:55432/saalr" uv run pytest tests/integration/test_transcript_store.py tests/integration/test_research_transcript.py -q`
Expected: PASS (RA-3c transcript tests still green — `transcript_s3_bucket` is unset, so `make_transcript_store` returns `DbTranscriptStore`).

- [ ] **Step 6: Write + run the LocalStack-gated round-trip test**

Create `packages/core/tests/test_s3_transcript_store.py`:
```python
import os
from uuid import uuid4

import pytest

boto3 = pytest.importorskip("boto3")

from saalr_core.research.transcript_store import S3TranscriptStore  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("AWS_ENDPOINT_URL"), reason="LocalStack/AWS endpoint not configured")

_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL")
_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
_BUCKET = "saalr-transcripts-test"


def _ensure_bucket():
    c = boto3.client("s3", region_name=_REGION, endpoint_url=_ENDPOINT)
    try:
        c.create_bucket(Bucket=_BUCKET)
    except Exception:  # noqa: BLE001 - already exists is fine
        pass


async def test_s3_save_load_roundtrip():
    _ensure_bucket()
    store = S3TranscriptStore(_BUCKET, region=_REGION, endpoint_url=_ENDPOINT)
    tid, nid = uuid4(), uuid4()
    steps = [{"role": "fundamentals", "memo": "F"}, {"role": "pm", "memo": "P"}]
    await store.save(tenant_id=tid, note_id=nid, steps=steps)
    assert await store.load(tenant_id=tid, note_id=nid) == steps
    assert await store.load(tenant_id=tid, note_id=uuid4()) is None
```
Run it (best-effort — see the LocalStack instructions in the conventions block):
```bash
docker compose -f infra/docker/docker-compose.localstack.yml up -d
uv pip install boto3
AWS_ENDPOINT_URL=http://localhost:4566 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 \
  uv run --no-sync pytest packages/core/tests/test_s3_transcript_store.py -q
git checkout uv.lock
```
Expected: PASS (1 passed). If LocalStack can't be started/pulled in this environment, note it — the test SKIPs cleanly without `AWS_ENDPOINT_URL`, and Steps 5 + 7 still gate the code. Tear down: `docker compose -f infra/docker/docker-compose.localstack.yml down`.

- [ ] **Step 7: Isolation check**

Run: `uv sync && uv run python -c "import importlib.util as u; print('boto3', bool(u.find_spec('boto3')))"`
Expected: `boto3 False` (the default env has no boto3; only the `aws` extra / a transient `uv pip install` brings it in).

- [ ] **Step 8: Lint + commit**
```bash
uvx ruff check packages/core/saalr_core/research/transcript_store.py packages/core/saalr_core/config.py packages/core/tests/test_transcript_store_select.py packages/core/tests/test_s3_transcript_store.py
git add packages/core/saalr_core/research/transcript_store.py packages/core/saalr_core/config.py packages/core/pyproject.toml infra/docker/docker-compose.localstack.yml packages/core/tests/test_transcript_store_select.py packages/core/tests/test_s3_transcript_store.py
git commit -m "feat(aws): S3TranscriptStore + config-driven make_transcript_store (AWS-1)"
```

---

### Task 2: `SecretsManagerResolver` + `CompositeCredentialResolver`

**Files:**
- Modify: `packages/brokers/saalr_brokers/credentials.py` (add the resolvers + factory)
- Modify: `packages/brokers/pyproject.toml` (`aws` extra)
- Modify: `apps/api/saalr_api/main.py` (use `make_credential_resolver`)
- Test (pure, default gate): `packages/brokers/tests/test_credentials_composite.py`
- Test (LocalStack-gated): `packages/brokers/tests/test_secrets_resolver.py`

- [ ] **Step 1: Write the failing pure test**

Create `packages/brokers/tests/test_credentials_composite.py`:
```python
import pytest

from saalr_brokers.credentials import (
    CompositeCredentialResolver,
    CredentialError,
    SecretsManagerResolver,
)


class _Stub:
    def __init__(self, pair):
        self._pair = pair

    def resolve(self, credential_ref, is_paper):
        return self._pair


def test_composite_routes_by_prefix():
    comp = CompositeCredentialResolver({
        "env:": _Stub(("ek", "es")),
        "secretsmanager:": _Stub(("sk", "ss")),
    })
    assert comp.resolve("env:ALPACA_PAPER", True) == ("ek", "es")
    assert comp.resolve("secretsmanager:saalr/brokers/x", False) == ("sk", "ss")


def test_composite_unknown_prefix_raises():
    comp = CompositeCredentialResolver({"env:": _Stub(("a", "b"))})
    with pytest.raises(CredentialError):
        comp.resolve("vault:whatever", True)


def test_secrets_resolver_rejects_bad_prefix_without_boto3():
    # the prefix guard runs before any boto3 import, so this needs no SDK
    r = SecretsManagerResolver()
    with pytest.raises(CredentialError):
        r.resolve("env:NOPE", True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest packages/brokers/tests/test_credentials_composite.py -q`
Expected: FAIL — `cannot import name 'CompositeCredentialResolver'`.

- [ ] **Step 3: Implement the resolvers + factory**

In `packages/brokers/saalr_brokers/credentials.py`:
- Add `import json` at the top (after `from __future__ import annotations`).
- Add the two classes + factory at the end of the file (after `build_alpaca_adapter`):
```python
class SecretsManagerResolver:
    """Resolves 'secretsmanager:<secret-id>' to (api_key, api_secret) from a secret whose JSON is
    {"key": ..., "secret": ...}. Sync (the CredentialResolver Protocol is sync); the boto3 fetch
    is cached per ref so it runs at most once per credential. boto3 is lazy (optional `aws` extra).
    Errors never carry the secret values."""

    _PREFIX = "secretsmanager:"

    def __init__(self, *, client=None, region=None, endpoint_url=None) -> None:
        self._client = client
        self._region = region
        self._endpoint = endpoint_url
        self._cache: dict[str, tuple[str, str]] = {}

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "secretsmanager", region_name=self._region, endpoint_url=self._endpoint)
        return self._client

    def resolve(self, credential_ref: str, is_paper: bool) -> tuple[str, str]:
        if not credential_ref.startswith(self._PREFIX):
            raise CredentialError("credential_ref must start with 'secretsmanager:'")
        if credential_ref in self._cache:
            return self._cache[credential_ref]
        secret_id = credential_ref[len(self._PREFIX):]
        try:
            resp = self._get_client().get_secret_value(SecretId=secret_id)
            data = json.loads(resp["SecretString"])
            pair = (data["key"], data["secret"])
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError(f"could not resolve {credential_ref!r}") from exc
        self._cache[credential_ref] = pair
        return pair


class CompositeCredentialResolver:
    """Routes a credential_ref to a delegate resolver by prefix (e.g. 'env:' / 'secretsmanager:')."""

    def __init__(self, resolvers: dict[str, CredentialResolver]) -> None:
        self._resolvers = resolvers

    def resolve(self, credential_ref: str, is_paper: bool) -> tuple[str, str]:
        for prefix, resolver in self._resolvers.items():
            if credential_ref.startswith(prefix):
                return resolver.resolve(credential_ref, is_paper)
        raise CredentialError(f"no resolver for credential_ref {credential_ref!r}")


def make_credential_resolver(settings, env) -> CredentialResolver:
    """Composite of the env resolver (always) + the Secrets Manager resolver (lazy)."""
    return CompositeCredentialResolver({
        "env:": EnvCredentialResolver(env),
        "secretsmanager:": SecretsManagerResolver(
            region=getattr(settings, "aws_region", None),
            endpoint_url=getattr(settings, "aws_endpoint_url", None)),
    })
```

In `packages/brokers/pyproject.toml`, add the `aws` extra (it currently has only `alpaca`):
```toml
[project.optional-dependencies]
alpaca = ["alpaca-py>=0.20"]
aws = ["boto3>=1.34"]
```

- [ ] **Step 4: Run the pure test**

Run: `uv run pytest packages/brokers/tests/test_credentials_composite.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Wire `make_credential_resolver` into `main.py`**

In `apps/api/saalr_api/main.py`:
- Change the credentials import (currently `from saalr_brokers.credentials import EnvCredentialResolver, build_alpaca_adapter`) to:
```python
from saalr_brokers.credentials import build_alpaca_adapter, make_credential_resolver
```
- Replace the alpaca-factory lines in the lifespan:
```python
        app.state.alpaca_adapter_factory = lambda account: build_alpaca_adapter(
            account.credential_ref, account.is_paper, EnvCredentialResolver(os.environ)
        )
```
with:
```python
        resolver = make_credential_resolver(settings, os.environ)
        app.state.alpaca_adapter_factory = lambda account: build_alpaca_adapter(
            account.credential_ref, account.is_paper, resolver
        )
```
(Verify `EnvCredentialResolver` is no longer referenced elsewhere in `main.py` — it isn't; ruff will flag an unused import if missed.)

- [ ] **Step 6: Write + run the LocalStack-gated SM test**

Create `packages/brokers/tests/test_secrets_resolver.py`:
```python
import json
import os

import pytest

boto3 = pytest.importorskip("boto3")

from saalr_brokers.credentials import (  # noqa: E402
    CompositeCredentialResolver,
    CredentialError,
    EnvCredentialResolver,
    SecretsManagerResolver,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("AWS_ENDPOINT_URL"), reason="LocalStack/AWS endpoint not configured")

_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL")
_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


def _sm():
    return boto3.client("secretsmanager", region_name=_REGION, endpoint_url=_ENDPOINT)


def _put_secret(name, key, secret):
    c = _sm()
    body = json.dumps({"key": key, "secret": secret})
    try:
        c.create_secret(Name=name, SecretString=body)
    except c.exceptions.ResourceExistsException:
        c.put_secret_value(SecretId=name, SecretString=body)
    return name


def test_resolve_and_cache():
    name = _put_secret("saalr/test/alpaca", "AKIA-KEY", "the-secret")
    r = SecretsManagerResolver(region=_REGION, endpoint_url=_ENDPOINT)
    assert r.resolve(f"secretsmanager:{name}", True) == ("AKIA-KEY", "the-secret")
    # delete the secret; a cached ref still resolves (proves caching)
    _sm().delete_secret(SecretId=name, ForceDeleteWithoutRecovery=True)
    assert r.resolve(f"secretsmanager:{name}", True) == ("AKIA-KEY", "the-secret")


def test_missing_secret_raises_credential_error():
    r = SecretsManagerResolver(region=_REGION, endpoint_url=_ENDPOINT)
    with pytest.raises(CredentialError):
        r.resolve("secretsmanager:saalr/test/does-not-exist", True)


def test_composite_routes_env_and_secretsmanager():
    name = _put_secret("saalr/test/comp", "K2", "S2")
    comp = CompositeCredentialResolver({
        "env:": EnvCredentialResolver({"ALPACA_PAPER_KEY": "EK", "ALPACA_PAPER_SECRET": "ES"}),
        "secretsmanager:": SecretsManagerResolver(region=_REGION, endpoint_url=_ENDPOINT),
    })
    assert comp.resolve("env:ALPACA_PAPER", True) == ("EK", "ES")
    assert comp.resolve(f"secretsmanager:{name}", False) == ("K2", "S2")
```
Run it (LocalStack up + boto3 installed, per the conventions block):
```bash
docker compose -f infra/docker/docker-compose.localstack.yml up -d
uv pip install boto3
AWS_ENDPOINT_URL=http://localhost:4566 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 \
  uv run --no-sync pytest packages/brokers/tests/test_secrets_resolver.py -q
git checkout uv.lock
```
Expected: PASS (3 passed). If LocalStack is unavailable, note the skip — the pure test (Step 4) is the hard gate.

- [ ] **Step 7: OMS regression + isolation**

Run (DB+Redis env prefix): `uv run pytest tests/integration/test_oms.py packages/brokers/tests/test_credentials_composite.py -q`
Expected: PASS (the composite resolves `env:` refs exactly as `EnvCredentialResolver` did — OMS paper/`env:` paths unchanged).
Run: `uv sync && uv run python -c "import importlib.util as u; print('boto3', bool(u.find_spec('boto3')))"`
Expected: `boto3 False`.

- [ ] **Step 8: Lint + commit**
```bash
uvx ruff check packages/brokers/saalr_brokers/credentials.py apps/api/saalr_api/main.py packages/brokers/tests/test_credentials_composite.py packages/brokers/tests/test_secrets_resolver.py
git add packages/brokers/saalr_brokers/credentials.py packages/brokers/pyproject.toml apps/api/saalr_api/main.py packages/brokers/tests/test_credentials_composite.py packages/brokers/tests/test_secrets_resolver.py
git commit -m "feat(aws): SecretsManagerResolver + CompositeCredentialResolver (AWS-1)"
```

---

### Task 3: Runbook updates

**Files:**
- Modify: `docs/runbooks/research-agent.md`
- Modify: `docs/runbooks/oms-reconcile.md`

- [ ] **Step 1: Transcript-backend note (research-agent runbook)**

Append to `docs/runbooks/research-agent.md`:
```markdown

## AWS backends (AWS-1)

Set `TRANSCRIPT_S3_BUCKET` (+ `AWS_REGION`) to route transcripts to **S3**
(`S3TranscriptStore`, key `transcripts/{tenant_id}/{note_id}.json`); unset, they
go to Postgres (`DbTranscriptStore`). `boto3` is an optional extra
(`saalr-core[aws]`) — install it where the API/worker run against real S3.

For local dev/tests, run LocalStack and point boto3 at it:

    docker compose -f infra/docker/docker-compose.localstack.yml up -d
    export AWS_ENDPOINT_URL=http://localhost:4566 AWS_DEFAULT_REGION=us-east-1 \
           AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test
    aws --endpoint-url=$AWS_ENDPOINT_URL s3 mb s3://saalr-transcripts

The gated tests (`packages/core/tests/test_s3_transcript_store.py`) run only when
`AWS_ENDPOINT_URL` is set + `boto3` is installed; a real-AWS smoke uses real
creds with `AWS_ENDPOINT_URL` unset.
```

- [ ] **Step 2: Broker-credentials note (oms-reconcile runbook)**

Append to `docs/runbooks/oms-reconcile.md`:
```markdown

## Broker credentials via Secrets Manager (AWS-1)

A `broker_account.credential_ref` is resolved by a `CompositeCredentialResolver`:
`env:PREFIX` → env vars `PREFIX_KEY`/`PREFIX_SECRET` (dev); `secretsmanager:<id>`
→ AWS Secrets Manager, a secret whose JSON is `{"key": ..., "secret": ...}`. Both
schemes coexist — set the ref per account. `boto3` is an optional extra
(`saalr-brokers[aws]`); the resolver caches each secret after first fetch and
never logs/returns the values.

Create a secret for LocalStack (or real AWS):

    aws --endpoint-url=$AWS_ENDPOINT_URL secretsmanager create-secret \
      --name saalr/brokers/alpaca-paper \
      --secret-string '{"key":"<ALPACA_KEY>","secret":"<ALPACA_SECRET>"}'

then set the account's `credential_ref` to `secretsmanager:saalr/brokers/alpaca-paper`.
```

- [ ] **Step 3: Commit**
```bash
git add docs/runbooks/research-agent.md docs/runbooks/oms-reconcile.md
git commit -m "docs(aws): runbooks — S3 transcripts + Secrets Manager creds (AWS-1)"
```

---

## Final verification (after all tasks)

- [ ] **Pure/default gate:** `uv run pytest packages/core/tests/test_transcript_store_select.py packages/brokers/tests/test_credentials_composite.py -q` — green.
- [ ] **Regression (DB+Redis env prefix):** `uv run pytest tests/integration/test_transcript_store.py tests/integration/test_research_transcript.py tests/integration/test_oms.py -q` — green (DB transcript path + OMS `env:` creds unchanged).
- [ ] **LocalStack gated (best-effort):** with LocalStack up + `boto3` installed + the AWS env vars: `uv run --no-sync pytest packages/core/tests/test_s3_transcript_store.py packages/brokers/tests/test_secrets_resolver.py -q` — green (4 passed); then `git checkout uv.lock`.
- [ ] **Isolation:** `uv sync && uv run python -c "import importlib.util as u; print('boto3', bool(u.find_spec('boto3')))"` — `boto3 False`.
- [ ] **Lint:** `uvx ruff check packages/core/saalr_core/research/transcript_store.py packages/brokers/saalr_brokers/credentials.py apps/api/saalr_api/main.py` — clean.
- [ ] **Final code-review subagent** over the whole AWS-1 diff.

## Self-review notes
- **Spec coverage:** `S3TranscriptStore` + config-driven `make_transcript_store` + config + `aws` extra + LocalStack compose (T1); `SecretsManagerResolver` + `CompositeCredentialResolver` + `make_credential_resolver` + `main.py` wiring + `aws` extra (T2); runbooks (T3). All spec sections map to a task.
- **Signature consistency:** `S3TranscriptStore(bucket, *, client, region, endpoint_url, prefix)` satisfies the RA-3c `TranscriptStore` Protocol (`async save/load(*, tenant_id, note_id, ...)`); `make_transcript_store(settings, sessionmaker)` keeps its existing signature (RA-3c callers untouched). `SecretsManagerResolver`/`CompositeCredentialResolver`/`EnvCredentialResolver` all satisfy `CredentialResolver` (sync `resolve(credential_ref, is_paper) -> (str, str)`); `make_credential_resolver(settings, env)` ↔ the `main.py` call `make_credential_resolver(settings, os.environ)`.
- **Deliberate choices flagged for the reviewer:** sync+cached resolver (the Protocol is sync; the boto3 fetch is one-time per ref, off the hot path); `asyncio.to_thread` only for the async S3 store; `load` maps `NoSuchKey → None` (no silent fallback on other errors); config-driven selection means zero RA-3c/OMS call-site churn and identical behaviour when AWS is unconfigured; `boto3` lazy + ABSENT in the default env; generic `CredentialError`/error messages never carry secret values.
- **No-regression:** with `transcript_s3_bucket` unset and `env:` refs, behaviour is byte-identical to RA-3c/OMS — those suites are the regression guard. The pure tests (select + composite routing + prefix guard) hold the always-on gate; the boto3 round-trips are LocalStack-gated and skip cleanly when the endpoint/SDK are absent.
