#!/usr/bin/env bash
set -euo pipefail
KEY="$(docker exec -i clothing-search sh -lc 'printf "%s" "$MEILI_MASTER_KEY"' | tr -d '\r\n')"
AUTH=(-H "Authorization: Bearer $KEY")
curl -sS "${AUTH[@]}" http://127.0.0.1:7700/version; echo
