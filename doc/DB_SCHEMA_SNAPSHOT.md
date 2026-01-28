# DB schema snapshot

- Generated: 2026-01-27 20:21:18 UTC
- Service: db
- Database: clothing

## Tables (public)

### `ai_jobs`

**Columns**

| column | type | nullable | default |
|---|---|---|---|
| `id` | `character varying` | NO | `` |
| `owner_id` | `character varying` | NO | `` |
| `media_id` | `character varying` | NO | `` |
| `status` | `character varying` | NO | `` |
| `created_at` | `timestamp without time zone` | NO | `now()` |
| `hint` | `json` | YES | `` |
| `result_json` | `json` | YES | `` |
| `error` | `text` | YES | `` |
| `model_version` | `character varying` | YES | `` |
| `draft_product_id` | `character varying` | YES | `` |
| `updated_at` | `timestamp without time zone` | NO | `now()` |

**Indexes**

```sql
ai_jobs_pkey: CREATE UNIQUE INDEX ai_jobs_pkey ON public.ai_jobs USING btree (id)
ix_ai_jobs_draft_product_id: CREATE INDEX ix_ai_jobs_draft_product_id ON public.ai_jobs USING btree (draft_product_id)
ix_ai_jobs_media_id: CREATE INDEX ix_ai_jobs_media_id ON public.ai_jobs USING btree (media_id)
ix_ai_jobs_owner_created: CREATE INDEX ix_ai_jobs_owner_created ON public.ai_jobs USING btree (owner_id, created_at)
ix_ai_jobs_owner_id: CREATE INDEX ix_ai_jobs_owner_id ON public.ai_jobs USING btree (owner_id)
```

