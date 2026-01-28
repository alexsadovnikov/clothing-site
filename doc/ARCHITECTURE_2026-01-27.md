# Clothing Platform — Backend Architecture

**Status:** canonical  
**Version:** 1.1  
**Date:** 2026-01-27  
**Owner:** Platform / Backend  

---

## 1. Назначение документа

Данный документ фиксирует **каноническую архитектуру backend-платформы Clothing** и контуры выполнения:
- Public Web/API (RU)
- Data services (Postgres/Redis/MinIO/Meili)
- Background processing (RQ worker + outbox-consumer)
- **External AI Gateway (EU)** как прокси к OpenAI

---

## 2. Контуры и окружения

### 2.1 RU (clothing-site)

**Основной сервер (RU/Timeweb):** `voicecrm.online`  
В Docker Compose развёрнут стек:
- `api` (FastAPI)
- `worker` (RQ worker)
- `outbox-consumer` (domain events consumer)
- `db` (PostgreSQL)
- `redis` (Redis)
- `minio` (S3-compatible)
- `meilisearch` (Search)

Публичные точки входа (через Nginx/SSL):
- `https://voicecrm.online/` — web (static)
- `https://voicecrm.online/api` — API reverse-proxy на `127.0.0.1:8001`
- `https://voicecrm.online/media` — MinIO S3 на `127.0.0.1:9100`

> Примечание: портовые биндинги контейнеров на RU-сервере, как правило, ограничены `127.0.0.1`, внешняя экспозиция — только через Nginx.

### 2.2 EU (ai-gateway)

**EU VPS (NL):** домен `ai.voicecrm.online`  
Назначение: **прокси/шлюз к OpenAI** (вынос ключей и доступа из RU).

Состав:
- `ai-gateway` (FastAPI + OpenAI SDK) в Docker
- публичный TLS endpoint `https://ai.voicecrm.online` (Caddy reverse-proxy → `127.0.0.1:8080`)

---

## 3. AI архитектура (актуально на 2026-01-27)

### 3.1 Зачем gateway

Причина: чтобы **RU API/worker не ходили в OpenAI напрямую** и не хранили OpenAI API ключ в RU контуре.

Цепочка:
`RU API/worker` → HTTPS → `ai.voicecrm.online` → OpenAI

Аутентификация: заголовок `X-AI-Internal-Token` (общий секрет).

### 3.2 Переменные окружения (RU)

Минимум для использования gateway:

- `AI_PROVIDER=gateway`
- `AI_GATEWAY_URL=https://ai.voicecrm.online`
- `AI_GATEWAY_TIMEOUT_S=60` (опционально)
- `AI_INTERNAL_TOKEN=<shared-secret>`

### 3.3 Внутренний endpoint анализа (RU)

В RU API присутствует внутренний endpoint:
- `POST /v1/analyze`  
  *Auth:* `X-AI-Internal-Token`  
  *Payload (предпочтительно):* `{ "bucket": "...", "object_key": "..." }`

Что делает:
1) читает объект из MinIO (`bucket/object_key`)  
2) формирует data_url (base64)  
3) вызывает provider:
   - `gateway` → `POST {AI_GATEWAY_URL}/v1/chat/completions`
   - `openai` → прямой OpenAI call (для dev/локально, если включено)
4) возвращает нормализованный JSON:
```json
{
  "provider": "gateway",
  "model": "gpt-4o-mini",
  "ms": 1234,
  "title_suggested": "...",
  "description_draft": "...",
  "attributes": { },
  "tags": [ ]
}
```

---

## 4. Флоу “Upload → AI → Draft Product”

**1) Upload**
- клиент грузит файл → API сохраняет в MinIO
- создаётся запись `media`

**2) AI Job**
- создаётся `ai_jobs` (или событие для outbox/worker)
- `worker` берёт job, вызывает **внутренний** `/v1/analyze` на API
- API читает MinIO, зовёт `ai-gateway`, возвращает JSON

**3) Draft Product**
- `worker` создаёт `products` со статусом draft
- переносит title/description/tags/attributes из AI результата
- фиксирует `ai_jobs.result_json`, `ai_jobs.draft_product_id`

---

## 5. Data services

### 5.1 Postgres
- доменные сущности (users, products, media, ai_jobs, …)
- события (outbox) и идемпотентность (processed_events), если включено

### 5.2 Redis
- очередь RQ (`RQ_QUEUE=clothing`)
- технические ключи/локи

### 5.3 MinIO
- исходники медиа
- базовый bucket: `products`

### 5.4 MeiliSearch
- индексирование продуктов
- filterable/sortable attrs настроены через `init_meili()` в worker

---

## 6. Наблюдаемость и логирование (контур)

- Логи сервисов читаются через `docker compose logs`
- Для дебага включается `LOG_LEVEL=DEBUG` (RU)

---

## 7. Контрольные проверки (операторские команды)

RU:
- Health API: `curl -fsS http://127.0.0.1:8001/health || true` (если реализовано)
- AI analyze smoke (worker-safe):
  `curl -i http://127.0.0.1:8001/v1/analyze -H "X-AI-Internal-Token: $TOKEN" -d '{"bucket":"products","object_key":"..."}'`

EU:
- `curl -fsS https://ai.voicecrm.online/health`
- `curl -i https://ai.voicecrm.online/v1/chat/completions -H "X-AI-Internal-Token: $TOKEN" -d '{...}'`

---

## 8. История изменений

- **1.1 (2026-01-27):** добавлен контур `ai-gateway (EU)` и описан переход `AI_PROVIDER=gateway`.
