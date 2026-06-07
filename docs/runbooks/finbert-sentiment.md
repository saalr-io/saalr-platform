# Runbook — FinBERT sentiment (C1)

The sentiment-scoring core: a Massive news adapter (`saalr_core/marketdata/news.py`), the pure
time-decay aggregation (`saalr_core/sentiment/`), and the real FinBERT scorer
(`apps/ml-worker/ml_worker/finbert.py`, torch + transformers).

## torch is opt-in
`apps/ml-worker` is NOT a root dependency, so normal `uv sync` / `uv run pytest` never install
torch. The default test gate (`uv run pytest packages/core/tests`) is torch-free — an inline stub
stands in for the model.

## Run the real model (downloads ~440 MB on first run)
```bash
uv sync --package saalr-ml-worker            # installs torch (CPU) + transformers
SAALR_LIVE_FINBERT=1 uv run --package saalr-ml-worker pytest apps/ml-worker/tests -v
```
The first run downloads `ProsusAI/finbert` to the Hugging Face cache (`~/.cache/huggingface`).

## Live news smoke (needs a Massive news entitlement)
```bash
RUN_LIVE_SMOKE=1 uv run pytest tests/integration/test_market_smoke.py::test_massive_news_live -v
```
