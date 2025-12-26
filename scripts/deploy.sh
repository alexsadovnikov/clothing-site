#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# overrides:
#   NO_CACHE=1 ./scripts/deploy.sh
#   BASE_URL=https://voicecrm.online/api ./scripts/deploy.sh
BASE_URL="${BASE_URL:-https://voicecrm.online/api}"
NO_CACHE="${NO_CACHE:-0}"

# normalize: remove trailing slash
BASE_URL="${BASE_URL%/}"

echo "[deploy] repo: $ROOT_DIR"
echo "[deploy] base_url: $BASE_URL"
echo "[deploy] no_cache: $NO_CACHE"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "[FAIL] missing command: $1"; exit 1; }; }
need_cmd docker
need_cmd git
need_cmd curl

on_err() {
  echo "[deploy][FAIL] deploy failed (line=$1)."
}
trap 'on_err $LINENO' ERR

echo "[deploy] git pull..."
git pull --ff-only

echo "[deploy] docker compose build..."
if [[ "$NO_CACHE" == "1" ]]; then
  docker compose build --no-cache api worker
else
  docker compose build api worker
fi

echo "[deploy] docker compose up infra..."
docker compose up -d db redis minio meilisearch

echo "[deploy] wait for db..."
DB_USER="${POSTGRES_USER:-clothing}"
for i in {1..60}; do
  if docker compose exec -T db pg_isready -U "$DB_USER" >/dev/null 2>&1; then
    echo "[deploy] db ready"
    break
  fi
  sleep 1
  if [[ "$i" == "60" ]]; then
    echo "[deploy][FAIL] db not ready"
    docker compose logs --tail=200 db || true
    exit 1
  fi
done

echo "[deploy] run migrations..."
# migrations via one-off container (no dependency on api runtime state)
docker compose run --rm api bash -lc "cd /app && alembic upgrade head"

echo "[deploy] docker compose up app..."
# важно: worker поднимаем вместе с api, до smoke
docker compose up -d --force-recreate api worker

echo "[deploy] wait for api /health..."
for i in {1..60}; do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    echo "[deploy] api ready"
    break
  fi
  sleep 1
  if [[ "$i" == "60" ]]; then
    echo "[deploy][FAIL] api not ready: $BASE_URL/health"
    docker compose logs --tail=200 api || true
    exit 1
  fi
done

echo "[deploy] smoke test..."
BASE_URL="$BASE_URL" ./scripts/smoke_api.sh

echo "[deploy] OK"