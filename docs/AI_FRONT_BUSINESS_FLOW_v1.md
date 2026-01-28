# AI Front Business Flow (v1) — DFD Level 1/2

**Version:** v1  
**Date:** 2026-01-27  
**Scope:** Front business process and the backend/AI runtime it relies on.

---

## DFD Level 1 — System context

**Goal:** User uploads a photo → system generates a draft product card via AI → user edits → publish.

**Key components**
- **Frontend (Browser/UI)**
- **Nginx (voicecrm.online)** — routes `/api` → clothing-api, `/ai` → ai.voicecrm.online (gateway)
- **clothing-api (FastAPI)** — upload, jobs, products
- **clothing-worker (RQ)** — background AI job processor
- **PostgreSQL** — `media`, `ai_jobs`, `products`, outbox tables
- **MinIO** — image storage (`bucket/object_key`)
- **AI Gateway (ai.voicecrm.online)** — isolates OpenAI key, validates internal token
- **OpenAI** — model execution

See: **AI_FRONT_BUSINESS_FLOW_L1** diagram (PDF + draw.io).

---

## DFD Level 2 — Front UX & Status transitions

### UX screens
1. **Upload**
2. **Processing**
3. **Draft editor**
4. **Publish**

### Status mapping (AIJob)
- `queued`  → “In queue”
- `running` → “Analyzing…”
- `failed`  → “Failed” + Retry
- `succeeded` → “Ready” + Open draft

See: **AI_FRONT_BUSINESS_FLOW_L2** diagram (PDF + draw.io).

---

## Minimal API calls from UI
- **Upload media:** `POST /v1/media/upload` (name may differ in your codebase)
- **Create job:** `POST /v1/ai-jobs`
- **Poll job:** `GET /v1/ai-jobs/{job_id}`
- **Open draft:** `GET /v1/products/{draft_product_id}`
- **Save draft:** `PATCH /v1/products/{id}`
- **Publish:** `POST /v1/products/{id}/publish`

(Exact routes can be aligned to your existing `main.py` / routers; this doc defines the business contract.)

---

## Notes
- AI internal auth uses `X-AI-Internal-Token`.
- Preferred analyze payload is `bucket + object_key` (worker-safe, avoids extra DB lookups).
