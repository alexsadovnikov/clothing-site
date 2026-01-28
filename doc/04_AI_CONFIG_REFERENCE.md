# AI Config Reference
As of: 2026-01-27

## RU stack (`/srv/clothing-site`)
### Required env (compose.yaml → x-ai-env)
- `AI_ENABLED=true`
- `AI_PROVIDER=gateway`
- `AI_GATEWAY_URL=https://ai.voicecrm.online`
- `AI_GATEWAY_TIMEOUT_S=60`
- `AI_INTERNAL_TOKEN=<64 hex>`
- `AI_INTERNAL_URL=http://api:8001` (worker)

### Internal auth header
- `X-AI-Internal-Token: <AI_INTERNAL_TOKEN>`

### Endpoints
- `POST /v1/analyze` (internal, worker-safe)
  - body: `{"bucket": "...", "object_key": "..."}`
- `POST /upload` (public, creates Media)
- (jobs) `process_ai_job(job_id)` uses `/v1/analyze`

## EU stack (`/srv/ai-gateway`)
### Required env
- `AI_INTERNAL_TOKEN=<same token>`
- `OPENAI_API_KEY=<secret>`
- `OPENAI_MODEL=gpt-4o-mini`
- `OPENAI_TIMEOUT_S=45`

### Endpoints
- `GET /` → `ok` (simple probe)
- `GET /health` → `{"ok": true}`
- `POST /v1/chat/completions` (OpenAI proxy)
  - header: `X-AI-Internal-Token`
