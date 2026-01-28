#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose -f compose.yaml --env-file .env"
DB_SVC="db"
DB_USER="clothing"
DB_NAME="clothing"

OUT="doc/DB_SCHEMA_SNAPSHOT.md"
TS="$(date -u +"%Y-%m-%d %H:%M:%S UTC")"

psql_exec() {
  $COMPOSE exec -T "$DB_SVC" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 "$@"
}

echo "# DB schema snapshot" > "$OUT"
echo "" >> "$OUT"
echo "- Generated: $TS" >> "$OUT"
echo "- Service: $DB_SVC" >> "$OUT"
echo "- Database: $DB_NAME" >> "$OUT"
echo "" >> "$OUT"

echo "## Tables (public)" >> "$OUT"
echo "" >> "$OUT"

# Список таблиц
TABLES="$(psql_exec -Atc "select tablename from pg_tables where schemaname='public' order by tablename;")"

if [[ -z "${TABLES// /}" ]]; then
  echo "_No tables found in public schema._" >> "$OUT"
  exit 0
fi

while IFS= read -r t; do
  [[ -z "$t" ]] && continue
  echo "### \`$t\`" >> "$OUT"
  echo "" >> "$OUT"

  echo "**Columns**" >> "$OUT"
  echo "" >> "$OUT"
  echo "| column | type | nullable | default |" >> "$OUT"
  echo "|---|---|---|---|" >> "$OUT"

  # Колонки
  psql_exec -Atc "
    select
      c.column_name,
      c.data_type
        || case
            when c.character_maximum_length is not null then '('||c.character_maximum_length||')'
            when c.numeric_precision is not null and c.numeric_scale is not null then '('||c.numeric_precision||','||c.numeric_scale||')'
            else ''
           end as data_type,
      c.is_nullable,
      coalesce(c.column_default,'') as column_default
    from information_schema.columns c
    where c.table_schema='public' and c.table_name='$t'
    order by c.ordinal_position;
  " | while IFS='|' read -r col typ nul def; do
        # экранируем пайпы в default
        def="${def//|/\\|}"
        echo "| \`$col\` | \`$typ\` | $nul | \`$def\` |" >> "$OUT"
      done

  echo "" >> "$OUT"
  echo "**Indexes**" >> "$OUT"
  echo "" >> "$OUT"
  echo '```sql' >> "$OUT"
  psql_exec -Atc "select indexname || ': ' || indexdef from pg_indexes where schemaname='public' and tablename='$t' order by indexname;" \
    | sed 's/|/: /g' >> "$OUT"
  echo '```' >> "$OUT"
  echo "" >> "$OUT"

done <<< "$TABLES"

echo "OK -> $OUT"
