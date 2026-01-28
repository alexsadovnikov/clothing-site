# AI Contour — Overview
As of: 2026-01-27

## Goal
Allow the RU stack (`/srv/clothing-site`) to run AI enrichment even when direct OpenAI access is restricted.
OpenAI key is stored only on the EU gateway (`/srv/ai-gateway`).

## Components
### RU VPS (voicecrm.online)
- **Nginx (host)** — TLS termination + reverse proxy routes
- **clothing-api (FastAPI)** — API + internal endpoint `/v1/analyze`
- **clothing-worker (RQ)** — background jobs (AIJob → draft Product)
- **MinIO** — stores uploaded media (`bucket=products`, `object_key=<owner>/<media>_<filename>`)
- **PostgreSQL** — source of truth (users/media/products/ai_jobs/outbox…)
- **Redis** — RQ queues + caching
- **MeiliSearch** — product search index (optional background indexing)

### EU VPS (ai.voicecrm.online)
- **Caddy (host)** — TLS termination for `ai.voicecrm.online`
- **ai-gateway (FastAPI)** — minimal OpenAI proxy: `/v1/chat/completions`
  - Auth: header `X-AI-Internal-Token`
  - OpenAI key lives here (`OPENAI_API_KEY`)

## Trust boundaries
- Public internet only sees HTTPS endpoints.
- RU containers never get OpenAI key.
- Only `AI_INTERNAL_TOKEN` is shared between RU (api/worker) and EU gateway.

## Failure modes (expected)
- MinIO `NoSuchKey` → `/v1/analyze` returns 502 (bubble up to job error)
- Gateway auth mismatch → 401
- OpenAI provider errors → 502 from gateway
