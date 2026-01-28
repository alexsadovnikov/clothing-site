# DB Tables & Operational Rules
As of: 2026-01-27

## Tables / entities we rely on (core)
> Названия могут отличаться в деталях (схема — через Alembic). Источник истины: `\dt` в Postgres и `apps/api/models.py`.

- `users` — owners/auth
- `media` — uploaded objects metadata (`bucket`, `object_key`, `content_type`, `size_bytes`, `checksum`, timestamps)
- `products` — product drafts/published
- `ai_jobs` — AI processing jobs (`status`, `error`, `draft_product_id`, `result_json`, timestamps)
- `outbox_events` — domain events for integration processing (outbox pattern)
- `processed_events` — idempotency ledger for outbox consumer

## Rules / invariants
### 1) Secrets
- OpenAI key only on EU gateway.
- RU stack uses only `AI_INTERNAL_TOKEN`.

### 2) Idempotency
- Worker: if AIJob already SUCCEEDED and has `draft_product_id` → no-op.
- Outbox consumer: checks `processed_events` before handling.

### 3) Storage
- Media bytes in MinIO; DB stores only pointers.
- Product search in MeiliSearch is derived data (can be rebuilt).

## Verification commands
### List tables
```bash
docker compose -f compose.yaml --env-file .env exec -T db psql -U clothing -d clothing -c "\dt"
```

### Show last migrations
```bash
docker compose -f compose.yaml --env-file .env exec -T api sh -lc "ls -la apps/api/alembic/versions | tail -n 20"
```

### Inspect media pointers
```bash
docker compose -f compose.yaml --env-file .env exec -T db psql -U clothing -d clothing -c \
  "select id,bucket,object_key,created_at from media order by created_at desc limit 10;"
```
