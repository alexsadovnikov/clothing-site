from __future__ import annotations

import os
import time
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from handlers.registry import get_handler  # callable или None

LOG = logging.getLogger("outbox-consumer")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "1.0"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DB_HOST = os.getenv("DB_HOST", "db")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "clothing")
    DB_USER = os.getenv("DB_USER", "clothing")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "clothing")
    DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def utcnow_naive() -> datetime:
    return datetime.utcnow()


def _normalize_payload(payload: Any) -> dict:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    # на случай если драйвер/мэппинг вернул строку (редко, но бывает)
    try:
        import json
        if isinstance(payload, str):
            return json.loads(payload)
    except Exception:
        pass
    return {}


def build_event_envelope(row: dict) -> dict:
    """
    Приводим событие к формату, который ожидают handlers/analytics.

    Минимальный контракт, который мы обеспечиваем:
      event_id, event_type, event_schema, occurred_at, aggregate{type,id}, payload

    Плюс оставляем поля для совместимости:
      outbox_id, aggregate_type, aggregate_id
    """
    payload = _normalize_payload(row.get("payload"))

    event_id = payload.get("event_id")
    # analytics.py у вас ожидает event_schema; если producer не пишет — ставим дефолт
    event_schema = payload.get("event_schema") or payload.get("schema") or "outbox.event.v1"

    occurred_at = row.get("occurred_at")
    # occurred_at в БД timestamp без tz — оставляем как есть (datetime),
    # но для удобства добавим iso-строку в meta.
    occurred_at_iso = None
    if hasattr(occurred_at, "isoformat"):
        occurred_at_iso = occurred_at.isoformat()

    aggregate_type = row.get("aggregate_type")
    aggregate_id = row.get("aggregate_id")

    return {
        "outbox_id": row.get("id"),
        "event_id": event_id,
        "event_type": row.get("event_type"),
        "event_schema": event_schema,
        "occurred_at": occurred_at,  # datetime (как пришло из БД)
        "aggregate": {
            "type": aggregate_type,
            "id": aggregate_id,
        },
        "payload": payload,

        # совместимость: старые потребители могли ждать плоские поля
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,

        # служебка
        "meta": {
            "source": "outbox_events",
            "occurred_at_iso": occurred_at_iso,
        },
    }


def mark_outbox_processed(db, outbox_id: int) -> None:
    db.execute(
        text("update outbox_events set processed_at = now() where id = :id"),
        {"id": outbox_id},
    )


def is_already_processed(db, event_id: str) -> bool:
    q = text("select 1 from processed_events where event_id = :eid limit 1")
    return db.execute(q, {"eid": event_id}).scalar() is not None


def register_processed(db, event_id: str, event_type: str) -> None:
    db.execute(
        text(
            "insert into processed_events(event_id, event_type) "
            "values (:eid, :etype) "
            "on conflict (event_id) do nothing"
        ),
        {"eid": event_id, "etype": event_type},
    )


def fetch_batch(db) -> list[dict]:
    q = text(
        "select id, event_type, aggregate_type, aggregate_id, payload, occurred_at "
        "from outbox_events "
        "where processed_at is null "
        "order by id asc "
        "limit :lim"
    )
    rows = db.execute(q, {"lim": BATCH_SIZE}).mappings().all()
    return [dict(r) for r in rows]


def process_one(db, row: dict) -> None:
    event = build_event_envelope(row)
    outbox_id = event.get("outbox_id")
    event_type = event.get("event_type")
    event_id = event.get("event_id")

    # 1) Poison-pill: нет event_id → помечаем processed и едем дальше
    if not event_id:
        LOG.error(
            "Event id missing in payload; marking as processed to avoid blocking. outbox_id=%s type=%s",
            outbox_id,
            event_type,
        )
        mark_outbox_processed(db, outbox_id)
        return

    # 2) Ранний idempotency
    if is_already_processed(db, event_id):
        LOG.info(
            "Already processed (idempotent skip) event_id=%s type=%s outbox_id=%s",
            event_id, event_type, outbox_id
        )
        mark_outbox_processed(db, outbox_id)
        return

    handler = get_handler(event_type)

    try:
        if handler is None:
            LOG.warning("No handler for event_type=%s, skipping side-effects", event_type)
        else:
            handler(event)  # передаём ENVELOPE, а не payload

        register_processed(db, event_id, event_type)
        mark_outbox_processed(db, outbox_id)

        LOG.info("Processed event event_id=%s type=%s outbox_id=%s", event_id, event_type, outbox_id)

    except Exception:
        # текущая стратегия: не блокировать очередь
        LOG.exception(
            "Failed to handle event; marking as processed to avoid blocking. event_id=%s type=%s outbox_id=%s",
            event_id, event_type, outbox_id
        )
        mark_outbox_processed(db, outbox_id)
        register_processed(db, event_id, event_type)


def main() -> None:
    LOG.info("Outbox consumer started")

    while True:
        try:
            with SessionLocal() as db:
                batch = fetch_batch(db)

                if not batch:
                    db.commit()
                    time.sleep(POLL_INTERVAL_SEC)
                    continue

                for row in batch:
                    process_one(db, row)

                db.commit()

        except Exception:
            LOG.exception("Consumer loop error")
            time.sleep(max(POLL_INTERVAL_SEC, 1.0))


if __name__ == "__main__":
    main()