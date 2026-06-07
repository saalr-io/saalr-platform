"""content_embeddings table for the RAG semantic index (pgvector)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-02
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE EXTENSION IF NOT EXISTS vector;

        CREATE TABLE content_embeddings (
          chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          module_slug     TEXT NOT NULL,
          chunk_index     INTEGER NOT NULL,
          content         TEXT NOT NULL,
          embedding       vector(1536) NOT NULL,
          embedding_model TEXT NOT NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (module_slug, chunk_index, embedding_model)
        );

        CREATE INDEX idx_content_embeddings_hnsw
          ON content_embeddings USING hnsw (embedding vector_cosine_ops);

        GRANT SELECT, INSERT, UPDATE, DELETE ON content_embeddings TO saalr_app;
    """)


def downgrade() -> None:
    # The `vector` extension is intentionally NOT dropped — it is shared and may be
    # depended on by other objects; it is safe to leave installed.
    op.execute("DROP TABLE IF EXISTS content_embeddings;")
