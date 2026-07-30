#!/usr/bin/env sh
set -eu

alembic upgrade head
exec uvicorn baseia_extract.catalog.api:app \
  --host 0.0.0.0 \
  --port "${CATALOG_API_PORT:-8088}"
