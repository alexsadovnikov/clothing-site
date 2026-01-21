# Clothing Platform — Backend Architecture

**Status:** canonical  
**Version:** 1.0  
**Date:** 2026-01-21  
**Owner:** Platform / Backend  

---

## 1. Назначение документа

Данный документ фиксирует **каноническую архитектуру backend-платформы Clothing**.

Он является **единственным источником правды (Single Source of Truth)** по устройству:
- API
- worker-процессов
- доменной логики
- AI pipeline

Любые изменения архитектуры должны:
- либо обновлять этот документ,
- либо сопровождаться отдельным ADR.

---

## 2. Что мы сделали и зачем

### Было
- относительные импорты (`from models import …`)
- разное поведение API и worker
- код зависел от текущей директории запуска
- сложно добавлять AI без ломки домена
- высокая хрупкость Docker / CI

### Стало (чисто и осознанно)
- **Единая точка входа:** `apps.api.main`
- **Абсолютные импорты:** `apps.api.*`
- **Одинаковая модель исполнения** в API и worker
- **Чёткие DDD-границы**
- Предсказуемая загрузка модулей в Docker

---

## 3. DDD-границы (ответственность слоёв)

apps/api/models.py        → persistence (ORM, таблицы, SQLAlchemy)
apps/api/events/*         → domain events
apps/api/state_machine.py → бизнес-правила и переходы состояний
apps/api/state_service.py → orchestration / use-cases
apps/api/outbox.py        → интеграции и delivery событий

**Принцип:**  
Доменные правила не знают:
- про HTTP
- про Redis
- про AI
- про очереди

---

## 4. Поток данных (основной API)

---

## 4. Поток данных (основной API)

HTTP request
↓
FastAPI router
↓
state_service (use-case)
↓
state_machine (business rules)
↓
models (ORM / DB)
↓
outbox (domain event)
↓
DB commit
---

## 5. Поток данных — AI pipeline

HTTP / Upload / Action
↓
Create AIJob (DB)
↓
enqueue_process_job()
↓
Redis Queue
↓
Worker
↓
AI processing
↓
DB update
↓
(optional) Domain Event

---

## 6. Где добавлять новую AI-фичу

Принципы:
- AI всегда **асинхронен**
- AI не меняет бизнес-истину напрямую
- AI = side-effect, а не core-домен

---

## 6. Где добавлять новую AI-фичу

Пример: **AI-оценка качества фото**

1. Модель  
`apps/api/models.py`

2. Очередь  
`apps/api/queueing.py`

3. Worker-обработка  
`apps/api/jobs.py`

4. API endpoint  
`apps/api/main.py` или отдельный router

5. (опционально) Domain Event  
`apps/api/events/*`

⚠️ **Важно:**  
AI не должен:
- напрямую менять статус продукта
- обходить state_machine
- ломать транзакционность

---

## 7. Почему это production-grade

- абсолютные импорты → стабильность
- единый entrypoint → предсказуемость
- чистые слои → масштабируемость
- безопасное добавление AI
- понятна любому senior backend-разработчику

Это фундамент, а не «проект для поиграться».

---

## 8. История версий

| Version | Date       | Description |
|-------:|------------|------------|
| 1.0    | 2026-01-21 | Initial canonical architecture |