# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# saalr-ml-worker pulls torch + transformers (large image, slow build). The FinBERT model is
# downloaded at first run into the HF cache unless pre-baked (out of scope).
COPY . /app
RUN uv sync --frozen --package saalr-ml-worker

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

# ECS supplies the CLI subcommand as the container command (e.g. ["sentiment"]).
ENTRYPOINT ["uv", "run", "--no-sync", "python", "-m", "ml_worker"]
