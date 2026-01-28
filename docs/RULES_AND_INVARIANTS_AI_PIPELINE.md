# Rules & Invariants — AI Pipeline (clothing-site)

**Version:** v1  
**Date:** 2026-01-27  
**Scope:** Front ↔ API ↔ Worker ↔ AI Gateway ↔ OpenAI, and resulting DB objects (`media`, `ai_jobs`, `products`).

---

## 1) Domain objects

### Media
**Purpose:** immutable fact of an uploaded file.  
**DB table:** `media`  
**Key fields:**
- `id` — UUID of media
- `owner_id` — user UUID (tenant boundary)
- `bucket` — MinIO bucket (e.g. `products`)
- `object_key` — MinIO object key (e.g. `OWNER_ID/MEDIA_ID_filename.jpg`)
- `created_at`

**Invariant M1:** `bucket` and `object_key` MUST be non-empty for any media usable in AI.

**Invariant M2:** all reads must enforce `media.owner_id == current_user.id`.

---

### AIJob
**Purpose:** record of an analysis request and its lifecycle.  
**DB table:** `ai_jobs`  
**Key fields:**
- `id` — UUID
- `owner_id`
- `media_id`
- `status` — `queued | running | succeeded | failed`
- `draft_product_id` — set on success (or early if you create draft before enrich)
- `created_at`, `updated_at`

**Invariant J1:** `ai_jobs.owner_id` MUST equal `media.owner_id`.

**Invariant J2:** transition model:
- `queued` → `running` → `succeeded`
- `queued` → `running` → `failed`
No backward transitions.

**Invariant J3:** if `status == succeeded` then `draft_product_id` MUST be non-null and point to a product owned by the same user.

---

### Product (Draft)
**Purpose:** editable product card created by AI.  
**DB table:** `products`  
**Key fields:**
- `id`
- `owner_id`
- `status` — (current observed) `draft_empty | ready | published` (your project may have more)
- `title` (string)
- `updated_at`

**Invariant P1:** `products.owner_id == ai_jobs.owner_id`.

**Invariant P2:** UI opens draft by `draft_product_id` from a succeeded `ai_job`.

---

## 2) API contracts (minimum)

### Upload
**Typical flow:** Front → API upload endpoint → DB `media` created → MinIO putObject.

**Required response to UI (minimum):**
- `media_id`
- `bucket`
- `object_key`
- (optional) preview/public URL if you have it

---

### AI analyze (internal)
**Endpoint:** `POST /v1/analyze`  
**Auth:** `X-AI-Internal-Token`  
**Payload supported:**
- preferred: `{"bucket":"...","object_key":"..."}`
- legacy: `{"media_id":"..."}` or `{"job_id":"..."}`

**Invariant A1:** if token is configured, request MUST include a valid token.

**Output:** JSON with:
- `provider` (e.g. `gateway`)
- `model`
- `ms`
- `title_suggested`, `description_draft`, `attributes`, `tags`

---

## 3) Frontend state model

### Screen: Upload
- show selected file(s)
- call upload
- store returned `media_id / object_key`
- enable CTA **“Generate product card”**

### Screen: Processing
- show `ai_job.status`:
  - `queued` → “In queue”
  - `running` → “Analyzing…”
  - `failed` → “Failed” + “Retry”
  - `succeeded` → “Ready” + “Open draft”

### Screen: Draft editor
- load product by `draft_product_id`
- allow edits
- save
- publish

---

## 4) Error classification

### User-facing errors
- invalid file, upload rejected (4xx)
- AI job failed (status `failed`)
- draft cannot be opened (missing product / permission)

### System errors (log + 5xx)
- MinIO read errors (`NoSuchKey`, etc.)
- gateway unavailable / timeout
- OpenAI provider error (502 from gateway)

---

## 5) Recommended product rule (to avoid “DB spam”)

Choose **one** of these policies:

**Policy A — each “Generate” creates a new draft**  
- every succeeded `ai_job` sets a new `draft_product_id`

**Policy B — one active draft per media** (recommended)  
- first success creates draft
- subsequent runs update the same draft (or create version history)

Document which policy is active and enforce it in `jobs.py` / worker logic.
