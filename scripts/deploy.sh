#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Можно переопределить:
#   NO_CACHE=1 ./scripts/deploy.sh
#   BASE_URL=https://voicecrm.online/api ./scripts/deploy.sh
BASE_URL="${BASE_URL:-https://voicecrm.online/api}"
NO_CACHE="${NO_CACHE:-0}"

echo "[deploy] repo: $ROOT_DIR"
echo "[deploy] base_url: $BASE_URL"
echo "[deploy] no_cache: $NO_CACHE"

echo "[deploy] git pull..."
git pull --ff-only

echo "[deploy] docker compose build..."
if [[ "$NO_CACHE" == "1" ]]; then
  docker compose build --no-cache api worker
else
  docker compose build api worker
fi

echo "[deploy] docker compose up..."
docker compose up -d --force-recreate api worker

echo "[deploy] wait a bit for api..."
sleep 2

echo "[deploy] smoke test..."
BASE_URL="$BASE_URL" ./scripts/smoke_api.sh

echo "[deploy] OK"