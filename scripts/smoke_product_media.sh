#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-https://voicecrm.online/api}"
EMAIL="${EMAIL:-a.sadovnikov@dixy.ru}"
PASS="${PASS:-Asad123sad}"

echo "[1/8] Login..."
TOKEN="$(curl -fsS -X POST "$BASE/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
echo "TOKEN_LEN=${#TOKEN}"

echo "[2/8] OpenAPI schema check..."
rm -f /tmp/openapi.json
curl -fsS "${BASE}/openapi.json" -o /tmp/openapi.json
python3 - <<'PY'
import json
o=json.load(open("/tmp/openapi.json"))
k="/v1/products/{product_id}/media"
get_schema=o["paths"][k]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
post_schema=o["paths"][k]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
assert "$ref" in get_schema and "ProductMediaListOut" in get_schema["$ref"], get_schema
assert "$ref" in post_schema and "ProductMediaAttachOut" in post_schema["$ref"], post_schema
cs=o.get("components",{}).get("schemas",{})
assert "ProductMediaListOut" in cs, "ProductMediaListOut missing in components.schemas"
assert "ProductMediaAttachOut" in cs, "ProductMediaAttachOut missing in components.schemas"
print("OK: OpenAPI response_model wired")
PY

echo "[3/8] Create product..."
PID="$(curl -fsS -X POST "$BASE/v1/products" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"SMOKE primary switch","description":"x"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')"
echo "PID=$PID"

echo "[4/8] Upload media 1..."
echo "pm smoke FIRST $(date -Is)" > /tmp/pm_smoke_1.txt
MID1="$(curl -fsS -X POST "$BASE/v1/media/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/pm_smoke_1.txt;type=text/plain" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])' | tr -d "\r")"
echo "MID1=$MID1"

echo "[5/8] Upload media 2..."
echo "pm smoke SECOND $(date -Is)" > /tmp/pm_smoke_2.txt
MID2="$(curl -fsS -X POST "$BASE/v1/media/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/pm_smoke_2.txt;type=text/plain" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])' | tr -d "\r")"
echo "MID2=$MID2"

echo "[6/8] Attach primary -> MID1..."
curl -fsS -X POST "$BASE/v1/products/$PID/media" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"media_id\":\"$MID1\",\"kind\":\"primary\"}" \
| python3 -m json.tool >/tmp/attach1.json

echo "[7/8] Switch primary -> MID2..."
curl -fsS -X POST "$BASE/v1/products/$PID/media" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"media_id\":\"$MID2\",\"kind\":\"primary\"}" \
| python3 -m json.tool >/tmp/attach2.json

echo "[8/8] List + contract checks..."
curl -fsS "$BASE/v1/products/$PID/media" \
  -H "Authorization: Bearer $TOKEN" \
  -o /tmp/pm_list.json

python3 - <<'PY'
import json
o=json.load(open("/tmp/pm_list.json"))
items=o.get("items", [])
assert items, "items empty"

# primary == 1
prim=[x for x in items if x.get("kind")=="primary"]
assert len(prim)==1, f"primary count={len(prim)}"

it=prim[0]

# nested media contract
assert "media" in it and isinstance(it["media"], dict), "missing nested media object"
m=it["media"]
for k in ("id","bucket","object_key","content_type","filename","size_bytes","created_at"):
    assert k in m, f"missing media.{k}"

# no leaked media_* fields in root
bad=[k for k in it.keys() if k in ("bucket","object_key","content_type","filename","size_bytes")]
assert not bad, f"media fields leaked to root: {bad}"

print("OK: single primary =", it["media_id"])
print("OK: nested media contract")
PY

echo "DONE OK"
echo "PID=$PID"
echo "MID1=$MID1"
echo "MID2=$MID2"
