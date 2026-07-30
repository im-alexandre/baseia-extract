FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN python -m pip install --no-cache-dir "uv>=0.8,<1"

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic.ini ./
COPY infra/catalog/migrations ./infra/catalog/migrations
COPY --chmod=0755 infra/catalog/start.sh /usr/local/bin/start-catalog-api

RUN uv sync --frozen --no-dev

EXPOSE 8088

ENTRYPOINT ["/usr/local/bin/start-catalog-api"]
