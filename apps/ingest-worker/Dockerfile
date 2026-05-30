# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# supercronic — container-native cron (runs in foreground, logs to stdout, unlike system cron)
ARG SUPERCRONIC_VERSION=v0.2.33
ARG SUPERCRONIC_SHA1SUM=71b0d58cc53f6bd72cf2f293e09e294b79c666d8
ADD https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN echo "${SUPERCRONIC_SHA1SUM}  /usr/local/bin/supercronic" | sha1sum -c - \
 && chmod +x /usr/local/bin/supercronic

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# Copy the uv workspace (apps/web, docs, etc. are excluded via .dockerignore) and install
# only the worker package + its dependency closure (saalr-core).
COPY . /app
RUN uv sync --frozen --package saalr-ingest-worker

RUN sed -i 's/\r$//' /app/apps/ingest-worker/docker-entrypoint.sh \
 && chmod +x /app/apps/ingest-worker/docker-entrypoint.sh \
 && useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

ENTRYPOINT ["/app/apps/ingest-worker/docker-entrypoint.sh"]
