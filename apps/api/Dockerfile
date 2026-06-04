# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# Copy the uv workspace (apps/web, docs, etc. excluded via the root .dockerignore) and install
# only the API package + its dependency closure (saalr-core, saalr-ml, saalr-content, uvicorn).
COPY . /app
RUN uv sync --frozen --package saalr-api

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser /app
USER appuser

EXPOSE 8000

# Local/compose health check; the ALB target group is the production health check.
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD ["uv", "run", "--no-sync", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"]

# Factory app: saalr_api.main:create_app() -> FastAPI. Port 8000 MUST match the Terraform
# api_service container_port.
ENTRYPOINT ["uv", "run", "--no-sync", "uvicorn", "saalr_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
