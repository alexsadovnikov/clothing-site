# AI — Infra & Architecture (as of 2026-01-27)

## Scope
This document describes the **AI subsystem** added to the Clothing-site stack:
- **Image-to-product enrichment** via `/v1/analyze`
- **Worker-driven pipeline** (RQ) that creates/updates Product drafts from AI output
- **External AI Gateway** (`ai.voicecrm.online`) that safely proxies requests to OpenAI

## 1) Components

### 1.1 Clothing-site (RU VPS / voicecrm.online)
**Runtime:** Docker Compose (`/srv/clothing-site/compose.yaml`, network `clothing-site_default`)

- **api** (`clothing-api`, FastAPI, `:8001`)
  - internal endpoint: `POST /v1/analyze` (protected by `X-AI-Internal-Token`)
  - reads image from MinIO, calls provider (gateway/openai), returns normalized JSON
- **worker** (`clothing-worker`, RQ)
  - consumes queue `clothing`
  - calls `api:/v1/analyze`
  - persists results: `AIJob` → `SUCCEEDED/FAILED`, creates Product draft, triggers state transition
- **db** (PostgreSQL 16) — stores Users / Media / Products / AIJob / Outbox
- **redis** (Redis 7) — RQ queues + cache
- **minio** (S3-compatible) — stores uploaded images (`bucket=products`)
- **meilisearch** — product search index (`products`)

### 1.2 AI Gateway (EU VPS / ai.voicecrm.online)
**Runtime:** Docker Compose (`/srv/ai-gateway/compose.yaml`)

- **gateway** (FastAPI)
  - `GET /health`
  - `POST /v1/chat/completions` (OpenAI-compatible subset)
  - validates `X-AI-Internal-Token`
  - calls OpenAI with server-side `OPENAI_API_KEY`
  - returns raw OpenAI response to caller

### 1.3 External
- **OpenAI API** (only reachable from EU gateway)

## 2) Trust boundaries & auth

### 2.1 Internal token (single shared secret)
Header: `X-AI-Internal-Token`

Used for:
- `worker → api` (`/v1/analyze`)
- `api → ai-gateway` (`/v1/chat/completions`)

Token value is stored in `.env` on both servers:
- `/srv/clothing-site/.env` → `AI_INTERNAL_TOKEN=...`
- `/srv/ai-gateway/.env` → `AI_INTERNAL_TOKEN=...`

**Rule:** no default token in compose. Empty token must break fast (401) to avoid silent misconfig.

## 3) Endpoints & contracts

### 3.1 API: `POST /v1/analyze`
**Auth:** `X-AI-Internal-Token`

**Input (preferred):**
```json
{"bucket":"products","object_key":"<path/in/minio>"}
```

**Legacy input (still supported):**
```json
{"media_id":"<uuid>","job_id":"<uuid>"}
```

**Output (normalized):**
```json
{
  "provider": "gateway",
  "model": "gpt-4o-mini",
  "ms": 2359,
  "title_suggested": "...",
  "description_draft": "...",
  "attributes": {...},
  "tags": ["..."]
}
```

### 3.2 Gateway: `POST /v1/chat/completions`
**Auth:** `X-AI-Internal-Token`

OpenAI-like request:
```json
{"model":"gpt-4o-mini","messages":[...],"max_tokens":600,"temperature":0.2}
```

## 4) Data flow (happy path)

1. **Upload**
   - user uploads image → stored in **MinIO** (`Media.bucket`, `Media.object_key`)
   - (optional) create `AIJob` row referencing `media_id`

2. **Enqueue**
   - RQ job created: `process_ai_job(job_id)` in **worker**
   - queue: `clothing` (Redis)

3. **Analyze**
   - worker calls **api** `POST /v1/analyze` with `{bucket, object_key}`
   - api reads image bytes from MinIO → creates data_url
   - provider switch:
     - `AI_PROVIDER=gateway` → call `AI_GATEWAY_URL=/v1/chat/completions`
     - `AI_PROVIDER=openai` (fallback) → call OpenAI directly (if key exists)

4. **Persist**
   - worker creates Product draft (`ProductState.DRAFT_EMPTY`)
   - fills: `title/description/attributes/tags`
   - sets `AIJob.status=SUCCEEDED`, stores `result_json`, `draft_product_id`
   - triggers state-machine event `ready_for_publish` (best-effort)

5. **Index**
   - optional: `index_product(product_id)` pushes document into MeiliSearch index

## 5) Configuration (env)

### 5.1 Clothing-site `.env`
Required:
- `AI_PROVIDER=gateway`
- `AI_GATEWAY_URL=https://ai.voicecrm.online`
- `AI_GATEWAY_TIMEOUT_S=60`
- `AI_INTERNAL_TOKEN=<64hex>`
- MinIO/DB/Redis/Meili envs

Optional (only if using direct OpenAI in this VPS):
- `OPENAI_API_KEY=...`

### 5.2 AI Gateway `.env`
Required:
- `AI_INTERNAL_TOKEN=<same 64hex>`
- `OPENAI_API_KEY=<real key>`
Optional:
- `OPENAI_MODEL=gpt-4o-mini`
- `OPENAI_TIMEOUT_S=45`

## 6) Operational notes

### 6.1 Logs to look at
- Clothing-site:
  - `docker compose -f compose.yaml --env-file .env logs -f api`
  - `docker compose -f compose.yaml --env-file .env logs -f worker`
- AI Gateway:
  - `docker compose --env-file .env logs -f gateway`

### 6.2 Common failure modes
- **401 invalid ai internal token**
  - token not passed / mismatch / newline glued in `.env`
- **502 minio error NoSuchKey**
  - object_key wrong or upload missing
- **502 openai error**
  - upstream timeout, wrong key, model not available

### 6.3 Security baseline
- gateway binds to `127.0.0.1:8080` on EU VPS, public exposure only via HTTPS (Caddy)
- internal token never embedded into frontend / browser
- `.env` secrets only on servers, not in git

## 7) Key DB entities (high-level)
Not exhaustive; list covers AI pipeline:

- `media` — object location in MinIO (`bucket`, `object_key`, `content_type`, `size_bytes`, `checksum`, `owner_id`)
- `ai_jobs` — async AI tasks (`status`, `error`, `result_json`, `draft_product_id`, `media_id`, `owner_id`)
- `products` — drafts + published (`status`, `title`, `description`, `attributes`, `tags`, `category_id`, `owner_id`)
- `outbox_events`, `processed_events` — transactional outbox + idempotency tracking (domain events)

