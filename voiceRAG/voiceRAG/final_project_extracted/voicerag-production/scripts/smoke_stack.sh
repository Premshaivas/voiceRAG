#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required for the stack smoke test." >&2
  exit 2
fi
if [[ ! -f .env ]]; then
  echo "Create .env from .env.example before starting the stack." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a
python3 scripts/validate_env.py
docker compose config >/dev/null
docker compose up -d --build
cleanup() {
  if [[ "${KEEP_STACK:-0}" != "1" ]]; then
    docker compose down
  fi
}
trap cleanup EXIT

for attempt in {1..60}; do
  if curl --fail --silent http://127.0.0.1:8000/health/ready >/tmp/voicerag-ready.json; then
    cat /tmp/voicerag-ready.json
    python3 scripts/integration_probe.py --api-url http://127.0.0.1:8000
    echo "VoiceRAG Compose smoke test passed"
    exit 0
  fi
  sleep 2
done

echo "API did not become ready" >&2
docker compose ps
docker compose logs --tail=100 api worker qdrant postgres redis minio
exit 1
