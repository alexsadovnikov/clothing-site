# AI Data Flow (DFD)
As of: 2026-01-27

## 0) Preconditions
- Media uploaded to MinIO, row created in `media` table (bucket+object_key).
- `AI_INTERNAL_TOKEN` set in both stacks.

## 1) Upload → Media row
1. Client uploads image → `clothing-api /upload`
2. API writes object to MinIO:
   - bucket: `products`
   - object_key: `<owner_id>/<media_id>_<filename>`
3. API inserts `media` row.

## 2) Create AIJob → enqueue worker
4. API creates `ai_jobs` row (status=PENDING) referencing `media_id`.
5. API enqueues RQ job `process_ai_job(job_id)`.

## 3) Worker → internal analyze
6. Worker loads AIJob + Media from DB.
7. Worker calls API internal endpoint:
   - `POST http://api:8001/v1/analyze`
   - Header: `X-AI-Internal-Token: <token>`
   - Body: `{"bucket":"products","object_key":"..."}`

## 4) API /v1/analyze (provider=gateway)
8. API reads object bytes from MinIO.
9. API builds prompt + messages (Vision).
10. API calls gateway:
    - `POST https://ai.voicecrm.online/v1/chat/completions`
    - Header: `X-AI-Internal-Token: <token>`
11. Gateway calls OpenAI and returns raw response.

## 5) Worker persists result
12. Worker parses JSON, creates `products` row in DRAFT state.
13. Worker updates `ai_jobs`:
    - status=SUCCEEDED
    - draft_product_id=<product_id>
    - result_json=<ai dict>
14. Optional: `index_product(product_id)` → MeiliSearch.

## Observability
- `LOG_LEVEL=DEBUG` during troubleshooting.
- Gateway logs: `POST /v1/chat/completions 200`.
