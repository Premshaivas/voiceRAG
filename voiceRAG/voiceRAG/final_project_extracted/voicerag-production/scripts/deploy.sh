#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
[[ -f .env ]] || { echo 'Missing .env; copy .env.example first' >&2; exit 2; }
python3 scripts/validate_env.py
docker compose config >/dev/null
docker compose build --pull
docker compose up -d postgres redis qdrant minio minio-init clamav
docker compose run --rm migrate
docker compose up -d api worker beat frontend caddy
for attempt in {1..60}; do
  if curl --fail --silent http://127.0.0.1:8000/health/ready >/dev/null; then
    echo 'VoiceRAG deployment is ready'
    exit 0
  fi
  sleep 2
done
docker compose ps
docker compose logs --tail=100 api worker
echo 'VoiceRAG deployment did not become ready' >&2
exit 1
