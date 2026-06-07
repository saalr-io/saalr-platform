from saalr_core.db.base import Base
import saalr_core.db.models  # noqa: F401  (registers all models on Base.metadata)

EXPECTED_TABLES = {
    "tenants", "users", "memberships", "api_keys",
    "subscriptions", "billing_events",
    "strategies", "backtests", "model_validation_runs",
    "broker_accounts", "orders", "executions", "positions",
    "audit_log",
    "bars", "options_chain_snapshots", "instruments",
    "config_kv",
    "research_notes", "research_transcripts",
    "content_embeddings", "user_progress",
    "news_sentiment",
    "llm_usage",
}


def test_all_tables_registered():
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES