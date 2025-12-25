#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://voicecrm.online/api}"
PASS="${PASS:-12345678}"

echo "BASE_URL=$BASE_URL"

# 1) health
curl -fsS "$BASE_URL/health" >/dev/null
echo "[OK] health"

# 2) register unique user -> token
EMAIL="smoke-$(date +%s)-$RANDOM@example.com"
TOKEN="$(curl -fsS -X POST "$BASE_URL/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))')"
test "${#TOKEN}" -gt 20
echo "[OK] register"

# 3) login -> token
TOKEN="$(curl -fsS -X POST "$BASE_URL/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))')"
test "${#TOKEN}" -gt 20
echo "[OK] login"

# 4) me
curl -fsS "$BASE_URL/v1/auth/me" -H "Authorization: Bearer $TOKEN" >/dev/null
echo "[OK] me"

# 5) delete me
curl -fsS -X DELETE "$BASE_URL/v1/auth/me" -H "Authorization: Bearer $TOKEN" >/dev/null
echo "[OK] delete_me"

echo "SMOKE OK"