# OMS reconciliation worker

Polls Alpaca for open orders on every active `broker='alpaca'` account, persists fills as
executions + positions, advances order status, and stamps `broker_accounts.last_reconciled_at`.

## Credentials
Alpaca keys are **process env vars** (not `.env`/pydantic-settings fields). A broker_account's
`credential_ref` names the env prefix, e.g. `credential_ref = "env:ALPACA_PAPER"` resolves
`ALPACA_PAPER_KEY` + `ALPACA_PAPER_SECRET`. Paper vs live is encoded in the ref by convention
(`ALPACA_PAPER` / `ALPACA_LIVE`) and mirrored by the account's `is_paper`.

## Run
    uv run --package saalr-oms-worker python -m oms_worker reconcile --interval 5      # loop
    uv run --package saalr-oms-worker python -m oms_worker reconcile --once            # one pass (cron/test)

Needs `APP_DATABASE_URL` (per-tenant, RLS) and `ADMIN_DATABASE_URL` (cross-tenant account discovery,
RLS bypass). DB on 55432 locally.

## Notes
- Discovery uses the admin engine (RLS bypass) to enumerate alpaca accounts; each account is then
  reconciled inside a `tenant_session` so all reads/writes are tenant-scoped. A SECURITY DEFINER
  discovery function (to drop the admin dependency) is a later hardening.
- At-least-once safe for a **single** worker: the synthetic
  `broker_execution_id = recon:{order_id}:{cumulative_filled}` makes a re-poll of the same fill level
  a no-op (`delta == 0`). Running two workers concurrently could race on that key (IntegrityError);
  multi-worker reconciliation (savepoint or claim-based partitioning) is deferred with worker scaling.
- Incremental fill price is the broker's cumulative `filled_avg_price` (a VWAP approximation); Alpaca's
  orders endpoint exposes no per-fill price. Per-fill accuracy would need the trade-update websocket.
- `alpaca-py` is an optional extra carried only by this worker package (`saalr-brokers[alpaca]`); the
  default `uv run pytest` env stays alpaca-free.
- Live smoke (opt-in): set `ALPACA_PAPER_KEY`/`ALPACA_PAPER_SECRET`, submit a tiny paper order, run
  `--once`, confirm the order advances.
- Deferred: containerize + schedule (supercronic, like the ingest-worker); the real trade-update
  websocket (`stream_executions`).

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
