from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable, Dict

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionLocal
from models import OutboxEvent

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


def process_batch(db: Session) -> int:
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.processed_at.is_(None))
        .order_by(OutboxEvent.id)
        .limit(BATCH_SIZE)
    )

    events = db.execute(stmt).scalars().all()

    if not events:
        return 0

    for event in events:
        handler = HANDLERS.get(event.event_type)

        if not handler:
            logger.warning(
                "No handler for event_type=%s",
                event.event_type,
            )
            event.processed_at = datetime.utcnow()
            continue

        try:
            handler(event.payload)
            event.processed_at = datetime.utcnow()
        except Exception:
            logger.exception(
                "Failed to handle event id=%s type=%s",
                event.id,
                event.event_type,
            )
            break

    db.commit()
    return len(events)


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
