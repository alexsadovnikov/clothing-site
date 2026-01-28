# Docs Index — Clothing-site / AI Gateway (as of 2026-01-27)

## What is in this bundle
- `01_AI_OVERVIEW.md` — high-level overview of the AI contour (why it exists, components, trust boundaries)
- `02_AI_RUNTIME_ARCHITECTURE.md` — infra/runtime diagram explanation (ports, DNS, reverse proxy, docker)
- `03_AI_DATAFLOW.md` — step-by-step request/data flow (upload → AI job → gateway → draft)
- `04_AI_CONFIG_REFERENCE.md` — env vars + headers + endpoints (source of truth)
- `05_DB_TABLES_AND_RULES.md` — DB entities/tables we rely on + operational rules (idempotency, outbox)
- `AI_ARCHITECTURE_2026-01-27.drawio` — editable diagram for diagrams.net (draw.io)

## Versioning rule
- Every significant infra/feature delivery → new folder `docs/YYYY-MM-DD/` on the server.
- Each document header includes `As of: YYYY-MM-DD` and a `Changelog` section.
- Old docs are not overwritten; instead we add “Superseded by” notes and link to the new version.

## Quick links
- Clothing stack root: `/srv/clothing-site` (compose: `compose.yaml`)
- AI gateway stack root (EU VPS): `/srv/ai-gateway` (compose: `compose.yaml`)
- Public endpoints:
  - API (host loopback): `http://127.0.0.1:8001`
  - AI gateway (public): `https://ai.voicecrm.online`
  - MinIO console (host loopback): `http://127.0.0.1:9101`

## What was updated on 2026-01-27
- AI provider switched to `gateway` (OpenAI key stored ONLY on EU gateway).
- Internal auth stabilized with `AI_INTERNAL_TOKEN` (no default; must be set).
- `/v1/analyze` updated to accept `bucket/object_key` (worker-safe) and to call provider via gateway.
