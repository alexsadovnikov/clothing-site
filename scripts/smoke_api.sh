#!/usr/bin/env bash
set -euo pipefail

# По умолчанию тестируем локально.
# Для домена: BASE_URL="https://voicecrm.online/api" bash scripts/smoke_api.sh
BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
BASE_URL="${BASE_URL%/}"

# AI блок по умолчанию выключен.
# Включить: SMOKE_AI=1 BASE_URL="http://127.0.0.1:8101" bash scripts/smoke_api.sh
SMOKE_AI="${SMOKE_AI:-0}"

# Поллинг AI job
AI_POLL_INTERVAL="${AI_POLL_INTERVAL:-0.5}"   # seconds
AI_POLL_TRIES="${AI_POLL_TRIES:-80}"          # 80 * 0.5 = 40s

# --- deps ---
need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1"; exit 127; }; }
need_cmd curl
# python может быть python3
if command -v python >/dev/null 2>&1; then
  PYTHON=python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
else
  echo "Missing dependency: python/python3"
  exit 127
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

LAST_BODY="$tmpdir/last_body"
LAST_CODE="$tmpdir/last_code"
LAST_REQ="$tmpdir/last_req"

say(){ printf '%s\n' "$*"; }

# Универсальный HTTP для JSON
http() {
  local method="$1"; local url="$2"; local data="${3:-}"; local token="${4:-}"

  echo "$method $url" >"$LAST_REQ"

  if [[ -n "$data" ]]; then
    curl -sS -L -o "$LAST_BODY" -w "%{http_code}" -X "$method" "$url" \
      ${token:+-H "Authorization: Bearer $token"} \
      -H "Content-Type: application/json" \
      -d "$data" >"$LAST_CODE" || true
  else
    curl -sS -L -o "$LAST_BODY" -w "%{http_code}" -X "$method" "$url" \
      ${token:+-H "Authorization: Bearer $token"} \
      >"$LAST_CODE" || true
  fi

  # если curl упал и файл пустой — чтобы не было пустого HTTP-кода
  if [[ ! -s "$LAST_CODE" ]]; then
    echo "000" >"$LAST_CODE"
  fi
}

# Отдельный helper для multipart/form-data (upload)
http_upload_file() {
  local url="$1"; local file_path="$2"; local token="${3:-}"

  echo "POST $url (multipart file=$file_path)" >"$LAST_REQ"

  curl -sS -L -o "$LAST_BODY" -w "%{http_code}" \
    ${token:+-H "Authorization: Bearer $token"} \
    -F "file=@${file_path};type=image/jpeg" \
    "$url" >"$LAST_CODE" || true

  if [[ ! -s "$LAST_CODE" ]]; then
    echo "000" >"$LAST_CODE"
  fi
}

fail_dump() {
  local msg="${1:-FAIL}"
  echo "---- FAIL ----"
  echo "$msg"
  echo "REQ: $(cat "$LAST_REQ")"
  echo "HTTP: $(cat "$LAST_CODE")"
  echo "BODY:"
  cat "$LAST_BODY"; echo
  exit 1
}

expect_2xx() {
  local code; code="$(cat "$LAST_CODE")"
  [[ "$code" =~ ^2 ]] || fail_dump "HTTP not 2xx"
}

json_field() {
  local field="$1"
  "$PYTHON" - "$field" "$LAST_BODY" <<'PY'
import json,sys
field=sys.argv[1]; path=sys.argv[2]
data=open(path,'r',encoding='utf-8').read()
if not data.strip():
  print("")
  raise SystemExit(0)
try:
  obj=json.loads(data)
except Exception:
  print("")
  raise SystemExit(0)
v=obj.get(field,"")
print("" if v is None else v)
PY
}

wait_health() {
  for _ in $(seq 1 40); do
    http GET "$BASE_URL/health"
    [[ "$(cat "$LAST_CODE")" == "200" ]] && return 0
    sleep 0.5
  done
  fail_dump "api not ready"
}

say "BASE_URL=$BASE_URL"
say "SMOKE_AI=$SMOKE_AI"
say "[wait] api /health..."
wait_health
say "[OK] api ready"

http GET "$BASE_URL/health"
expect_2xx
say "[OK] health"

http GET "$BASE_URL/openapi.json"
expect_2xx
say "[OK] openapi routes"

EMAIL="smoke$(date +%s)@example.com"
PASS="test12345"

# register: 2xx ок, 409 тоже ок
http POST "$BASE_URL/v1/auth/register" "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}"
code="$(cat "$LAST_CODE")"
if [[ "$code" =~ ^2 ]]; then
  say "[OK] register"
elif [[ "$code" == "409" ]]; then
  say "[OK] register (already exists)"
else
  fail_dump "register failed"
fi

http POST "$BASE_URL/v1/auth/login" "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}"
expect_2xx
TOKEN="$(json_field access_token)"
[[ -n "$TOKEN" ]] || fail_dump "login: access_token empty"
say "[OK] login"

http GET "$BASE_URL/v1/auth/me" "" "$TOKEN"
expect_2xx
say "[OK] me"

http POST "$BASE_URL/v1/products" '{"title":"Smoke jacket","tags":["winter"]}' "$TOKEN"
expect_2xx
PID="$(json_field id)"
[[ -n "$PID" ]] || fail_dump "create_product: id empty"
say "[OK] create_product id=$PID"

http POST "$BASE_URL/v1/products/$PID/publish" "" "$TOKEN"
expect_2xx
say "[OK] publish_product"

http POST "$BASE_URL/v1/looks" '{"title":"Зима офис","season":"winter","occasion":"work"}' "$TOKEN"
expect_2xx
LOOK_ID="$(json_field id)"
[[ -n "$LOOK_ID" ]] || fail_dump "create_look: id empty"
say "[OK] create_look id=$LOOK_ID"

http POST "$BASE_URL/v1/looks/$LOOK_ID/items" "{\"product_id\":\"$PID\"}" "$TOKEN"
expect_2xx
say "[OK] add_item_to_look"

http POST "$BASE_URL/v1/wear-log" "{\"product_id\":\"$PID\",\"context\":\"work\"}" "$TOKEN"
expect_2xx
say "[OK] wear_log_create"

http GET "$BASE_URL/v1/wear-log" "" "$TOKEN"
expect_2xx
say "[OK] wear_log_list"

# ---------------- AI JOB (optional) ----------------
if [[ "$SMOKE_AI" == "1" ]]; then
  say "[AI] start..."

  # 1) make tiny jpg
  TMP_JPG="$tmpdir/tiny.jpg"
  "$PYTHON" - <<'PY' "$TMP_JPG"
import sys, base64
b64 = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wCEAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAGnAP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAQUCsf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQMBAT8Bl//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQIBAT8Bl//EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEABj8Cl//Z"
open(sys.argv[1], "wb").write(base64.b64decode(b64))
PY

  # 2) upload media
  http_upload_file "$BASE_URL/v1/media/upload" "$TMP_JPG" "$TOKEN"
  expect_2xx
  MEDIA_ID="$(json_field id)"
  [[ -n "$MEDIA_ID" ]] || fail_dump "media_upload: id empty"
  say "[OK] media_upload id=$MEDIA_ID"

  # 3) create ai job
  http POST "$BASE_URL/v1/ai/jobs" "{\"media_id\":\"$MEDIA_ID\",\"hint\":{}}" "$TOKEN"
  expect_2xx
  JOB_ID="$(json_field id)"
  [[ -n "$JOB_ID" ]] || fail_dump "ai_job_create: id empty"
  say "[OK] ai_job_create id=$JOB_ID"

  # 4) poll status
  poll_ai_job() {
    for _ in $(seq 1 "$AI_POLL_TRIES"); do
      http GET "$BASE_URL/v1/ai/jobs/$JOB_ID" "" "$TOKEN"
      expect_2xx
      status="$(json_field status)"
      [[ -n "$status" ]] || status="unknown"

      # допускаем разные названия финальных статусов
      case "$status" in
        finished|done|completed|success|succeeded)
          say "[OK] ai_job finished (status=$status)"
          return 0
          ;;
        failed|error)
          fail_dump "ai_job failed (status=$status)"
          ;;
        *)
          # queued/running/processing/unknown
          sleep "$AI_POLL_INTERVAL"
          ;;
      esac
    done
    fail_dump "ai_job timeout"
  }

  poll_ai_job
  say "[AI] done"
else
  say "[AI] skipped (set SMOKE_AI=1 to enable)"
fi

say "[OK] smoke done"