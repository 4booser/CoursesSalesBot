#!/usr/bin/env sh
set -eu

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

echo "== Docker services =="
docker compose ps

echo "== API health =="
curl -fsS http://localhost:8000/health
echo

echo "== Redis health =="
docker compose exec -T redis redis-cli ping

echo "== PostgreSQL health =="
docker compose exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "== Latest backup =="
if [ -f backups/latest_backup.txt ]; then
  cat backups/latest_backup.txt
else
  echo "No backup metadata found"
fi
