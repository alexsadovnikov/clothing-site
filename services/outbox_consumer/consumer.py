from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable, Dict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import SessionLocal
from models import OutboxEvent, ProcessedEvent

from handlers.product_created import handle as handle_product_created
from handlers.product_published import handle as handle_product_published

logger = logging.getLogger("outbox-consumer")
logging.basicConfig(level=logging.INFO)

POLL_INTERVAL_SECONDS = 1.0
BATCH_SIZE = 50


HANDLERS: Dict[str, Callable[[dict], None]] = {
    "product.created": handle_product_created,
    "product.published": handle_product_published,
}


# ============================================================
# IDEMPOTENCY HELPERS
# ============================================================

def mark_processed(db: Session, event: OutboxEvent) -> None:
    """
    Атомарно:
    - фиксируем processed_events (idempotency barrier)
    - помечаем outbox_events.processed_at
    """
    processed = ProcessedEvent(
        event_id=event.payload["event_id"],
        event_type=event.event_type,
    )
    db.add(processed)

    event.processed_at = datetime.utcnow()


# ============================================================
# SINGLE EVENT PROCESSING
# ============================================================

def process_event(db: Session, event: OutboxEvent) -> bool:
    """
    Обрабатывает ОДНО событие.

    Возвращает:
    - True  — успешно обработано / уже обработано
    - False — ошибка, batch нужно остановить
    """

    event_id = event.payload.get("event_id")
    if not event_id:
        logger.error(
            "Event id missing in payload, outbox_id=%s type=%s",
            event.id,
            event.event_type,
        )
        return False

    handler = HANDLERS.get(event.event_type)

    try:
        # =====================================================
        # 1️⃣ Выполняем business handler (side-effect)
        # =====================================================
        if handler:
            handler(event.payload)
        else:
            logger.warning(
                "No handler for event_type=%s, skipping side-effects",
                event.event_type,
            )

        # =====================================================
        # 2️⃣ Idempotency barrier (atomic insert)
        # =====================================================
        mark_processed(db, event)
        db.commit()

        logger.info(
            "Processed event event_id=%s type=%s",
            event_id,
            event.event_type,
        )
        return True

    except IntegrityError:
        # 🔒 ДРУГОЙ consumer уже обработал это событие
        db.rollback()

        logger.info(
            "Event already processed (idempotent skip) event_id=%s",
            event_id,
        )

        # помечаем outbox, чтобы не забирать снова
        event.processed_at = datetime.utcnow()
        db.commit()
        return True

    except Exception:
        db.rollback()
        logger.exception(
            "Failed to handle event event_id=%s type=%s",
            event_id,
            event.event_type,
        )
        return False


# ============================================================
# BATCH PROCESSING
# ============================================================

def process_batch(db: Session) -> int:
    """
    Забирает batch событий и обрабатывает их по одному.
    """

    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.processed_at.is_(None))
        .order_by(OutboxEvent.id)
        .limit(BATCH_SIZE)
    )

    events = db.execute(stmt).scalars().all()

    if not events:
        return 0

    processed_count = 0

    for event in events:
        success = process_event(db, event)
        if not success:
            break
        processed_count += 1

    return processed_count


# ============================================================
# MAIN LOOP
# ============================================================

def run() -> None:
    logger.info("Outbox consumer started")

    while True:
        try:
            with SessionLocal() as db:
                processed = process_batch(db)

            if processed == 0:
                time.sleep(POLL_INTERVAL_SECONDS)

        except Exception:
            logger.exception("Outbox consumer crashed")
            time.sleep(5)


if __name__ == "__main__":
    run()