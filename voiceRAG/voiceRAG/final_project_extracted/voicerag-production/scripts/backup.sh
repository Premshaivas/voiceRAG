#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
set -a; . ./.env; set +a
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$BACKUP_DIR"

echo "Backing up PostgreSQL"
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-voicerag}" -d "${POSTGRES_DB:-voicerag}" --format=custom > "$BACKUP_DIR/postgres.dump"
echo "Backing up Qdrant"
curl --fail --silent --show-error -X POST "${QDRANT_URL:-http://localhost:6333}/collections/${QDRANT_COLLECTION:-voice_transcripts}/snapshots" > "$BACKUP_DIR/qdrant-snapshot.json"
echo "Syncing object storage"
if command -v mc >/dev/null 2>&1; then mc mirror "${MINIO_ALIAS:-local}/${S3_BUCKET:-voicerag}" "$BACKUP_DIR/object-storage"
else echo "mc not installed; object storage backup requires mc mirror" >&2
fi
sha256sum "$BACKUP_DIR"/* > "$BACKUP_DIR/SHA256SUMS"
echo "Backup written to $BACKUP_DIR"
