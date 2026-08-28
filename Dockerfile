FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM python:3.14.7-slim AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.14.7-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN addgroup --system hanin && adduser --system --ingroup hanin hanin
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app
USER hanin
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]

FROM runtime AS migrate
CMD ["alembic", "upgrade", "head"]

# Last stage is the default `docker build` / EasyPanel target when none is set.
FROM runtime AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]
