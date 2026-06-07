# AWS-1 — App-side cloud integrations (S3 transcripts + Secrets Manager creds) (design)

**Status:** approved 2026-06-03
**Slice:** AWS-1 (first sub-slice of the AWS-foundation band; HLD ADR-008 / §9 / §6 / §audit)
**Builds on:** RA-3c (the pluggable `TranscriptStore`), OMS-3b (the `CredentialResolver` + `build_alpaca_adapter`). Unblocks the two concrete "needs-AWS" deferrals with real, locally-verifiable code.

## Goal

Deliver the application-side cloud integrations that prior slices deferred for "needs AWS", behind optional `boto3` extras and verifiable now against **LocalStack** (no AWS account required for the default tests; an env-gated real-AWS smoke runs against a real account):

1. **`S3TranscriptStore`** — an S3-backed implementation of RA-3c's `TranscriptStore`, selected by config; persists/reads the multi-agent transcript in S3 instead of Postgres.
2. **`SecretsManagerResolver` + `CompositeCredentialResolver`** — resolve OMS broker `credential_ref`s of the form `secretsmanager:<id>` from AWS Secrets Manager, routed by ref prefix alongside the existing `env:` resolver.

This is **app-side only**. It *uses* an S3 bucket + a Secrets Manager secret; **provisioning** them is the Terraform foundation (AWS-2+), or LocalStack in tests / manual for the real smoke.

## Approved decisions

1. **Sync `boto3` via `asyncio.to_thread`** for the async S3 store (matches the `AlpacaAdapter` off-load pattern); `boto3` is a lazy, optional extra. The `CredentialResolver` Protocol is **synchronous**, so `SecretsManagerResolver.resolve` makes a sync boto3 call — one-time, **cached per ref**, and off the latency-critical path (live order placement, behind the 14-day promotion gate) — rather than reworking the whole resolver/OMS chain to async.
2. **Prefix-dispatch `CompositeCredentialResolver`**: `env:` → `EnvCredentialResolver`, `secretsmanager:` → `SecretsManagerResolver`; different broker accounts can use either scheme with no global switch.
3. **LocalStack-first, env-gated** tests (default gate stays green without LocalStack/boto3); real-AWS smoke env-gated separately. `boto3` ABSENT in the default env (isolation, like `openai`/`anthropic`/`alpaca-py`).

## S3 transcript store

`packages/core/saalr_core/research/transcript_store.py` gains a second `TranscriptStore` implementation (the Protocol + `DbTranscriptStore` from RA-3c are unchanged):

```python
class S3TranscriptStore:
    """S3-backed transcript store. Sync boto3 off-loaded via asyncio.to_thread so the async
    TranscriptStore interface holds no thread/loop. boto3 is imported lazily (optional extra)."""

    def __init__(self, bucket, *, client=None, region=None, endpoint_url=None, prefix="transcripts"):
        self._bucket = bucket
        self._client = client            # injectable for tests (LocalStack); else lazy-built
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

    async def save(self, *, tenant_id, note_id, steps):
        body = json.dumps(steps).encode("utf-8")
        client = self._get_client()
        await asyncio.to_thread(
            client.put_object, Bucket=self._bucket, Key=self._key(tenant_id, note_id),
            Body=body, ContentType="application/json")

    async def load(self, *, tenant_id, note_id):
        client = self._get_client()
        try:
            resp = await asyncio.to_thread(
                client.get_object, Bucket=self._bucket, Key=self._key(tenant_id, note_id))
        except client.exceptions.NoSuchKey:
            return None
        body = await asyncio.to_thread(resp["Body"].read)
        return json.loads(body)
```

- **Key scheme** `transcripts/{tenant_id}/{note_id}.json` puts the tenant in the key (defense-in-depth: a wrong tenant can't read another's object). The read endpoint already runs `get_note` (RLS) first, so cross-tenant is doubly guarded.
- **`load` maps `NoSuchKey → None`** (so a missing transcript stays a clean `404`); other errors propagate (an S3 outage surfaces, same risk profile as a DB error — no silent fallback).
- **`make_transcript_store` becomes config-driven** (was: always `DbTranscriptStore`):
```python
def make_transcript_store(settings, sessionmaker):
    bucket = getattr(settings, "transcript_s3_bucket", None)
    if bucket:
        return S3TranscriptStore(bucket, region=getattr(settings, "aws_region", None),
                                 endpoint_url=getattr(settings, "aws_endpoint_url", None))
    return DbTranscriptStore(sessionmaker)
```
No worker or API call-site changes — both already build the store via this factory (RA-3c). With no `transcript_s3_bucket` configured, behaviour is identical to RA-3c (DB store), so all RA-3c tests stay green.

`json` + `asyncio` are imported at the top of the module (stdlib); `boto3` stays lazy inside `_get_client`. The class definition imports no SDK, so `make_transcript_store` resolves `S3TranscriptStore` even when `boto3` is absent (only constructing + using one needs the bucket configured + the extra installed).

## Secrets Manager credential resolver

`packages/brokers/saalr_brokers/credentials.py` gains two classes + a factory (the `CredentialResolver` Protocol, `EnvCredentialResolver`, and `build_alpaca_adapter` are unchanged):

```python
class SecretsManagerResolver:
    """Resolves a credential_ref 'secretsmanager:<secret-id>' to (api_key, api_secret) from a
    secret whose JSON is {"key": ..., "secret": ...}. Sync (the CredentialResolver Protocol is
    sync); the boto3 fetch is cached per ref, so it runs at most once per credential and off the
    hot path. boto3 is lazy (optional extra). Errors never carry the secret values."""

    _PREFIX = "secretsmanager:"

    def __init__(self, *, client=None, region=None, endpoint_url=None):
        self._client = client
        self._region = region
        self._endpoint = endpoint_url
        self._cache: dict[str, tuple[str, str]] = {}

    def _get_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("secretsmanager", region_name=self._region,
                                        endpoint_url=self._endpoint)
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

    def __init__(self, resolvers: dict[str, CredentialResolver]):
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

- The `SecretsManagerResolver` is constructed lazily-safe: building it imports no boto3 (the import is inside `_get_client`), so `make_credential_resolver` works in the default env; only resolving a `secretsmanager:` ref needs boto3 + the extra. Env-only deployments never touch boto3.
- **Secret JSON shape**: `{"key": "<api_key>", "secret": "<api_secret>"}`. The `credential_ref` stored on a `broker_account` is `secretsmanager:<secret-id>` (the secret id/ARN); the ref is a pointer — the secret values are never logged, returned, or persisted (carried over from OMS-3b).

### `main.py` wiring

The lifespan's alpaca factory swaps the inline env resolver for the composite:
```python
from saalr_brokers.credentials import build_alpaca_adapter, make_credential_resolver
...
        resolver = make_credential_resolver(settings, os.environ)
        app.state.alpaca_adapter_factory = lambda account: build_alpaca_adapter(
            account.credential_ref, account.is_paper, resolver)
```
(Previously: `EnvCredentialResolver(os.environ)`.) Existing `env:` accounts behave identically; the OMS service is unchanged.

## Config + dependencies

`packages/core/saalr_core/config.py` adds (after the RA-3a block):
```python
    # AWS (app-side integrations; AWS-1)
    aws_region: str | None = None
    aws_endpoint_url: str | None = None   # LocalStack/MinIO override for S3 + Secrets Manager
    transcript_s3_bucket: str | None = None
```

Optional extras (lazy `boto3`, ABSENT in the default env):
- `packages/core/pyproject.toml`: `aws = ["boto3>=1.34"]`
- `packages/brokers/pyproject.toml`: `aws = ["boto3>=1.34"]`

Sync `boto3` calls in the async S3 store are wrapped in `asyncio.to_thread`. The `CredentialResolver` is sync by Protocol; its cached boto3 call is acceptable as designed.

## Error handling & edge cases

| Case | Where | Result |
|------|-------|--------|
| transcript object missing | `S3TranscriptStore.load` | `None` → endpoint `404` (same as DB) |
| S3 outage on load | `S3TranscriptStore.load` | error propagates (no silent fallback) |
| S3 failure on save | worker phase 3 | already best-effort (RA-3c) — logged, note still succeeds |
| `secretsmanager:` secret missing / malformed JSON | `SecretsManagerResolver.resolve` | `CredentialError` (generic; no secret leak) → OMS maps to `502 BROKER_CREDENTIALS_UNAVAILABLE` |
| unknown ref prefix | `CompositeCredentialResolver.resolve` | `CredentialError` |
| `boto3` not installed but an S3/SM ref is used | lazy `_get_client` import | `ImportError` → surfaces as `CredentialError`/save-error (a config/deploy error, not a runtime path in env-only deployments) |
| `transcript_s3_bucket` unset | `make_transcript_store` | `DbTranscriptStore` (RA-3c behaviour, unchanged) |

## Testing

- **LocalStack** compose `infra/docker/docker-compose.localstack.yml`: LocalStack on `4566`, `SERVICES=s3,secretsmanager`.
- **Integration tests are gated** so the default suite stays green without LocalStack/boto3:
  - top-of-file `boto3 = pytest.importorskip("boto3")`;
  - `pytestmark = pytest.mark.skipif(not os.environ.get("AWS_ENDPOINT_URL"), reason="LocalStack not configured")`.
  Run them with `boto3` installed + LocalStack up + `AWS_ENDPOINT_URL=http://localhost:4566` and dummy creds (`AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1`):
  - **`tests/integration/test_s3_transcript_store.py`**: create the bucket, `S3TranscriptStore.save` then `load` round-trips the steps; `load` of a missing key → `None`; `make_transcript_store` returns `S3TranscriptStore` when `transcript_s3_bucket` is set (a tiny settings stub) and `DbTranscriptStore` otherwise.
  - **`packages/brokers/tests/test_secrets_resolver.py`**: create a secret `{"key","secret"}`, `SecretsManagerResolver.resolve` returns the pair + serves a 2nd call from cache (delete the secret between calls to prove caching); bad prefix → `CredentialError`; missing secret → `CredentialError`; `CompositeCredentialResolver` routes `env:` → env pair and `secretsmanager:` → SM pair; unknown prefix → `CredentialError`.
- **Pure unit (no LocalStack, default gate):** `CompositeCredentialResolver` routing with **stub resolvers** (in-memory) — no boto3 needed — asserts prefix dispatch + unknown-prefix `CredentialError`. This keeps the routing logic covered in the always-on suite.
- **Real-AWS smoke** (env-gated separately, `RUN_AWS_SMOKE=1` + real creds + a real bucket/secret, `AWS_ENDPOINT_URL` unset) — the same store/resolver exercised against real AWS; documented, not run by default.
- **Regression:** RA-3c's transcript tests (DB store path unchanged when `transcript_s3_bucket` unset); OMS tests (the composite resolver resolves `env:` identically to before); `uv sync` → `boto3` ABSENT in the default env.

**Test-invocation note:** `boto3` is an optional extra not in the default env. Like the Alpaca adapter tests, install it transiently for the integration run (`uv pip install boto3 && uv run --no-sync pytest ... && git checkout uv.lock`) with LocalStack up + the AWS env vars; or skip them (they no-op without `AWS_ENDPOINT_URL`). The pure composite-routing unit test runs in the default gate.

## Out of scope (AWS-2+ / later)

The Terraform foundation — VPC, RDS (TimescaleDB), ElastiCache, ECR, ECS cluster + Fargate services + EventBridge scheduled tasks, ALB, IAM, KMS — **including provisioning the S3 bucket + the Secrets Manager secret** this slice consumes; S3 model storage (HLD §4 SageMaker) + audit-log S3 Object Lock (compliance archive); credential rotation; `aioboto3`; per-account KMS encryption contexts; a transcript-archival/TTL lifecycle policy.

## Runbook update

`docs/runbooks/research-agent.md` (transcripts) + `docs/runbooks/oms-reconcile.md` (creds) gain an "AWS backends (AWS-1)" note: set `TRANSCRIPT_S3_BUCKET` (+ `AWS_REGION`) to route transcripts to S3 (else Postgres); store broker creds as a Secrets Manager secret `{"key","secret"}` and point a `broker_account.credential_ref` at `secretsmanager:<id>` (the composite resolver routes it; `env:` refs still work); for local dev/tests run LocalStack (`docker-compose.localstack.yml`) and set `AWS_ENDPOINT_URL=http://localhost:4566`. A short runbook snippet shows the `aws --endpoint-url` CLI to create the bucket/secret for LocalStack, and the `RUN_AWS_SMOKE` flag for the real-AWS smoke.
