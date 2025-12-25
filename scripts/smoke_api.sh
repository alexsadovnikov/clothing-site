#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://voicecrm.online/api}"
PASS="${PASS:-12345678}"

echo "BASE_URL=$BASE_URL"

# 1) health
curl -fsS "$BASE_URL/health" >/dev/null
echo "[OK] health"

# 1.1) openapi routes exist (guard against missing methods)
OPENAPI_TMP="$(mktemp)"
curl -fsS "$BASE_URL/openapi.json" -o "$OPENAPI_TMP"

python3 - <<'PY' "$OPENAPI_TMP"
import json, sys
p = json.load(open(sys.argv[1], "r", encoding="utf-8")).get("paths", {})

def need(path, method):
    ops = p.get(path, {})
    if method not in ops:
        raise SystemExit(f"[FAIL] openapi missing: {method.upper()} {path}")

need("/v1/auth/register", "post")
need("/v1/auth/login", "post")
need("/v1/auth/me", "get")
need("/v1/auth/me", "delete")
print("[OK] openapi routes")
PY

rm -f "$OPENAPI_TMP"

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