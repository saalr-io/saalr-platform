# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# saalr-content-worker pulls saalr-core[openai] + saalr-content (openai SDK, not torch).
COPY . /app
RUN uv sync --frozen --package saalr-content-worker

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

# One-off reindex job — ECS/`aws ecs run-task` supplies the subcommand (["reindex"]).
ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "content_worker"]
