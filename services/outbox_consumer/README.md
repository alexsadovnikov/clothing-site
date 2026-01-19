# Outbox Consumer Service

## Назначение

`outbox_consumer` — отдельный сервис для обработки **domain events**, записанных
в таблицу `outbox_events` основным API (`apps/api`).

Сервис реализует **Transactional Outbox Pattern** и обеспечивает:
- асинхронную доставку событий
- изоляцию сайд-эффектов от бизнес-транзакций
- гарантированную обработку событий (at-least-once)

---

## Архитектурная роль
API (FastAPI)
│
│  (DB transaction)
▼
outbox_events (Postgres)
│
│  polling
▼
outbox_consumer
│
├── analytics handlers
├── search handlers
└── other integrations

API **только пишет** события в `outbox_events`.  
Consumer **только читает и обрабатывает** их.

---

## Обрабатываемые события

На текущий момент поддерживаются:

- `product.created`
- `product.published`

Каждое событие:
- имеет `event_type`
- содержит payload
- обрабатывается строго своим handler’ом

---

## Структура сервиса

services/outbox_consumer/
├── consumer.py              # основной polling loop
├── db.py                    # подключение к БД
├── models.py                # ORM-модель outbox_events
├── handlers/
│   ├── product_created.py
│   ├── product_published.py
│   ├── analytics.py
│   └── search.py
├── requirements.txt
├── Dockerfile
└── README.md
---

## Принцип работы

1. Consumer периодически читает **необработанные** записи из `outbox_events`
2. Для каждого события:
   - выбирается handler по `event_type`
   - handler выполняет сайд-эффект (analytics / search / и т.д.)
3. После успешной обработки:
   - заполняется `processed_at`
4. При ошибке:
   - событие остаётся необработанным
   - будет повторно взято в следующем цикле

⚠️ Consumer **НЕ удаляет события** — только помечает как обработанные.

---

## Гарантии

- ✔ События не теряются
- ✔ API не зависит от внешних систем
- ✔ Повторная обработка возможна
- ✔ Масштабируется горизонтально (в будущем)

Текущая семантика: **at-least-once delivery**

---

## Переменные окружения

Минимально необходимые:

```env
DATABASE_URL=postgresql://clothing:clothing@db:5432/clothing
POLL_INTERVAL=1.0
BATCH_SIZE=100
