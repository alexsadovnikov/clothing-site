# ADR-003 — AI Provider via External Gateway (2026-01-27)

## Status
Accepted

## Context
- RU VPS cannot reliably access OpenAI directly.
- We need a stable, controllable integration point with:
  - consistent auth (internal token)
  - centralized OpenAI key management
  - future multi-provider routing

## Decision
Introduce **AI Gateway** service on EU VPS (ai.voicecrm.online).
Clothing-site API uses `AI_PROVIDER=gateway` to call the gateway over HTTPS.

## Consequences
### Positive
- RU stack becomes independent from OpenAI network constraints
- Keys live only in EU gateway
- Single place to implement retries, timeouts, observability, model policy

### Negative / Risks
- Extra hop (latency)
- New service to operate (deploy + monitoring)
- Shared-secret token must be rotated carefully

## Implementation notes
- Gateway API:
  - `GET /health`
  - `POST /v1/chat/completions` (OpenAI-compatible subset)
- Auth:
  - Header `X-AI-Internal-Token`
- Config:
  - RU: `AI_GATEWAY_URL`, `AI_GATEWAY_TIMEOUT_S`, `AI_INTERNAL_TOKEN`
  - EU: `OPENAI_API_KEY`, `AI_INTERNAL_TOKEN`

## Rollback plan
Set `AI_PROVIDER=openai` and provide `OPENAI_API_KEY` to clothing-site (only if outbound connectivity permits).

