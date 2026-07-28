#!/usr/bin/env bash
set -euo pipefail

export MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-local}"
export MINERU_API_MAX_CONCURRENT_REQUESTS="${MINERU_API_MAX_CONCURRENT_REQUESTS:-4}"

exec mineru-api \
  --host 0.0.0.0 \
  --port "${PORT:-8000}"
