#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose -f compose.yaml --env-file .env"
DB_SVC="db"
DB_USER="clothing"
DB_NAME="clothing"

TS="$(date -u +"%Y-%m-%d %H:%M:%S UTC")"
OUT_SQL="doc/DB_SCHEMA.sql"
OUT_META="doc/DB_SCHEMA.sql.meta"

# 1) Сохраняем мета-инфу
{
  echo "# DB schema-only dump"
  echo "# Generated: $TS"
  echo "# Service: $DB_SVC"
  echo "# Database: $DB_NAME"
} > "$OUT_META"

# 2) Делаем schema-only дамп внутри контейнера и выводим наружу в файл
$COMPOSE exec -T "$DB_SVC" sh -lc \
  "pg_dump -U '$DB_USER' -d '$DB_NAME' --schema-only --no-owner --no-privileges" \
  > "$OUT_SQL"

# 3) Нормализуем (убираем шум, который мешает диффам)
#    - комментарии pg_dump про версию
#    - строки SET (зависят от окружения)
#    - volatile SELECT pg_catalog.set_config(...)
sed -i \
  -e '/^-- Dumped from database version/d' \
  -e '/^-- Dumped by pg_dump version/d' \
  -e '/^SET /d' \
  -e "/^SELECT pg_catalog.set_config/d" \
  "$OUT_SQL"

echo "OK -> $OUT_SQL"
echo "META -> $OUT_META"
