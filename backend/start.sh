#!/bin/sh
# Production entrypoint for single-service hosting (decision 0004). Migrates, optionally seeds the
# synthetic DEMO orgs (idempotent), then serves API + frontend on $PORT.
set -e
alembic upgrade head
if [ "${SEED_DEMO_ON_START:-false}" = "true" ]; then
  python -m app.seed_demo
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
