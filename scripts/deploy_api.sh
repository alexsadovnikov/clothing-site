#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-https://voicecrm.online/api}"

echo "[1/7] build + up api..."
docker compose up -d --build api

echo "[2/7] show ps..."
docker compose ps

echo "[3/7] wait api healthy (3 OK in a row)..."
ok=0
for i in {1..120}; do
  if curl -fsS "${BASE}/health" >/dev/null; then
    ok=$((ok+1))
    if [[ $ok -ge 3 ]]; then
      echo "OK: health stable"
      break
    fi
  else
    ok=0
  fi

  sleep 1

  if [[ "$i" == "120" ]]; then
    echo "FAIL: api not healthy"
    docker compose logs -n 200 api
    exit 1
  fi
done

echo "[4/7] alembic upgrade..."
docker compose exec -T api sh -lc 'cd /app && alembic -c apps/api/alembic.ini upgrade head'

echo "[5/7] smoke..."
./scripts/smoke_product_media.sh | tee /tmp/smoke.log

echo "[6/7] export PID/MID1/MID2..."
eval "$(grep -E '^(PID|MID1|MID2)=' /tmp/smoke.log | sed 's/^/export /')"

echo "[7/7] DB assert primary == 1 and == MID2..."
docker compose exec -T db psql -U clothing -d clothing -Atc \
"select count(*) from product_media where product_id='${PID}' and kind='primary';" \
| grep -qx "1"

docker compose exec -T db psql -U clothing -d clothing -Atc \
"select media_id from product_media where product_id='${PID}' and kind='primary' limit 1;" \
| grep -qx "${MID2}"

echo "DEPLOY OK"
echo "PID=${PID}"
echo "MID1=${MID1}"
echo "MID2=${MID2}"
