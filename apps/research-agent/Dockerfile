# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# saalr-research-agent depends on saalr-core[openai,anthropic] (non-optional -> installed here).
COPY . /app
RUN uv sync --frozen --package saalr-research-agent

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

# ECS supplies the CLI subcommand as the container command (e.g. ["consume"]).
ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "research_agent"]
