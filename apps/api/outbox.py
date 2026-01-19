from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy.orm import Session

from models import OutboxEvent


def emit_event(
    *,
    session: Session,
    event_type: str,
    aggregate_type: str,
    aggregate_id,
    payload: Dict[str, Any],
) -> OutboxEvent:
    """
    Записывает domain event в outbox.

    ⚠️ ДОЛЖЕН вызываться внутри активной транзакции.
    ⚠️ commit() здесь НЕ делаем.
    """
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        occurred_at=datetime.utcnow(),
    )

    session.add(event)
    return event