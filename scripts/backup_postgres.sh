#!/usr/bin/env sh
set -eu

BACKUP_DIR=${BACKUP_DIR:-./backups}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILE_NAME=${POSTGRES_DB}_${TIMESTAMP}.sql.gz

mkdir -p "$BACKUP_DIR"

docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$BACKUP_DIR/$FILE_NAME"

echo "Backup created: $BACKUP_DIR/$FILE_NAME"
