#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://voicecrm.online/api}"
PASS="${PASS:-12345678}"

# normalize: remove trailing slash
BASE_URL="${BASE_URL%/}"

echo "BASE_URL=$BASE_URL"

need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "[FAIL] missing command: $1"; exit 1; }; }
need_cmd curl
need_cmd python3

CURL_JSON() { curl -fsSL "$@"; }   # follow redirects, fail fast
CURL_OK()   { curl -fsSL "$@" >/dev/null; }

# temp files cleanup
OPENAPI_TMP="$(mktemp)"
TMP_JPG=""
cleanup() {
  rm -f "$OPENAPI_TMP" >/dev/null 2>&1 || true
  [[ -n "${TMP_JPG:-}" ]] && rm -f "$TMP_JPG" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 0) wait for api
echo "[wait] api /health..."
ready=0
for i in {1..30}; do
  if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    echo "[OK] api ready"
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" != "1" ]]; then
  echo "[FAIL] api not ready: $BASE_URL/health"
  exit 1
fi

# 1) health
CURL_OK "$BASE_URL/health"
echo "[OK] health"

# 1.1) openapi routes exist
curl -fsSL -o "$OPENAPI_TMP" "$BASE_URL/openapi.json"

python3 - <<'PY' "$OPENAPI_TMP"
import json, sys
p = json.load(open(sys.argv[1], "r", encoding="utf-8")).get("paths", {})

def need(path, method):
    ops = p.get(path, {})
    if method not in ops:
        raise SystemExit(f"[FAIL] openapi missing: {method.upper()} {path}")

# auth
need("/v1/auth/register", "post")
need("/v1/auth/login", "post")
need("/v1/auth/me", "get")
need("/v1/auth/me", "delete")

# products
need("/v1/products", "post")
need("/v1/products", "get")
need("/v1/products/{product_id}", "get")
need("/v1/products/{product_id}", "patch")
need("/v1/products/{product_id}/publish", "post")

# media
need("/v1/media/upload", "post")
need("/v1/products/{product_id}/media", "post")

# search
need("/v1/search", "get")

print("[OK] openapi routes")
PY

# 2) register -> token
EMAIL="smoke-$(date +%s)-$RANDOM@example.com"
TOKEN="$(CURL_JSON -X POST "$BASE_URL/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))')"
test "${#TOKEN}" -gt 20
echo "[OK] register"

# 3) login -> token
TOKEN="$(CURL_JSON -X POST "$BASE_URL/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))')"
test "${#TOKEN}" -gt 20
echo "[OK] login"

export BASE_URL TOKEN
AUTH_HEADER="Authorization: Bearer $TOKEN"

# 4) me
CURL_OK "$BASE_URL/v1/auth/me" -H "$AUTH_HEADER"
echo "[OK] me"

# 5) create product
CREATE_RESP="$(CURL_JSON -X POST "$BASE_URL/v1/products" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d '{"title":"Smoke product","description":"Smoke desc"}')"

PRODUCT_ID="$(echo "$CREATE_RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("id",""))')"
test "${#PRODUCT_ID}" -gt 20
echo "[OK] create_product id=$PRODUCT_ID"

# 6) list products contains product_id
LIST_RESP="$(CURL_JSON "$BASE_URL/v1/products" -H "$AUTH_HEADER")"
echo "$LIST_RESP" | python3 - <<PY
import sys, json
pid = "$PRODUCT_ID"
obj = json.load(sys.stdin)

if isinstance(obj, dict) and "items" in obj and isinstance(obj["items"], list):
    items = obj["items"]
elif isinstance(obj, list):
    items = obj
else:
    raise SystemExit(f"[FAIL] unexpected list response shape: {type(obj)}")

ids = [x.get("id") for x in items if isinstance(x, dict)]
if pid not in ids:
    raise SystemExit(f"[FAIL] product not found in list: {pid}")
print("[OK] list_products contains product")
PY

# 7) upload media (1x1 jpg)
TMP_JPG="$(mktemp --suffix=.jpg)"
python3 - <<'PY' "$TMP_JPG"
import sys, base64
b64 = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wCEAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAGwA//EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAQUCcf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQMBAT8Bcf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQIBAT8Bcf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEABj8Ccf/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAT8hcf/Z"
open(sys.argv[1], "wb").write(base64.b64decode(b64))
PY

UPLOAD_RESP="$(CURL_JSON -X POST "$BASE_URL/v1/media/upload" \
  -H "$AUTH_HEADER" \
  -F "file=@$TMP_JPG;type=image/jpeg")"

MEDIA_ID="$(echo "$UPLOAD_RESP" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("media_id",""))')"
test "${#MEDIA_ID}" -gt 20
echo "[OK] upload_media media_id=$MEDIA_ID"

# 8) attach media
CURL_OK -X POST "$BASE_URL/v1/products/$PRODUCT_ID/media" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d "{\"media_id\":\"$MEDIA_ID\",\"kind\":\"original\"}"
echo "[OK] attach_media"

# 9) get product includes media
GETP_RESP="$(CURL_JSON "$BASE_URL/v1/products/$PRODUCT_ID" -H "$AUTH_HEADER")"
echo "$GETP_RESP" | python3 - <<PY
import sys, json
mid = "$MEDIA_ID"
obj = json.load(sys.stdin)
media = obj.get("media", [])
mids = [m.get("id") for m in media if isinstance(m, dict)]
if mid not in mids:
    raise SystemExit(f"[FAIL] media not attached: {mid}")
print("[OK] get_product includes media")
PY

# 10) publish
CURL_OK -X POST "$BASE_URL/v1/products/$PRODUCT_ID/publish" -H "$AUTH_HEADER"
echo "[OK] publish_product"

# 11) search (retry; index async через worker)
python3 - <<PY
import os, time, sys, json, subprocess, urllib.parse
base = os.environ["BASE_URL"]
token = os.environ["TOKEN"]
pid = "$PRODUCT_ID"

q = "Smoke"
url = f"{base}/v1/search?q={urllib.parse.quote(q)}"

def run():
    out = subprocess.check_output(["curl","-fsSL", url, "-H", f"Authorization: Bearer {token}"])
    return json.loads(out)

for _ in range(15):
    try:
        obj = run()
        items = obj.get("items", obj if isinstance(obj, list) else [])
        ids = [x.get("id") for x in items if isinstance(x, dict)]
        if pid in ids:
            print("[OK] search found product")
            sys.exit(0)
    except Exception:
        pass
    time.sleep(1)

print("[FAIL] search did not find published product (worker/indexer?)")
sys.exit(2)
PY

# 12) cleanup user
CURL_OK -X DELETE "$BASE_URL/v1/auth/me" -H "$AUTH_HEADER"
echo "[OK] delete_me"

echo "SMOKE OK"