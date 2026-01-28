from __future__ import annotations

import uuid
import logging
from datetime import datetime
from typing import Literal, Any

from sqlalchemy.orm import Session
from sqlalchemy import inspect

from apps.api.models import Product, StateHistory
from apps.api.state_machine import apply_product_transition, InvalidStateTransition
from apps.api.outbox import add_outbox_event
from apps.api.events.base import BaseEvent

logger = logging.getLogger(__name__)

EntityType = Literal["product"]


class StateTransitionError(Exception):
    pass


def _has_state_history_table(db: Session) -> bool:
    try:
        bind = db.get_bind()
        if not bind:
            return False
        insp = inspect(bind)
        return bool(insp.has_table("state_history"))
    except Exception:
        return False


def change_state(
    *,
    db: Session,
    entity,
    entity_type: EntityType,
    event: str,
    actor_id: str | None = None,
    meta: Any | None = None,
):
    if entity_type != "product":
        raise StateTransitionError("Only product supported")

    if not isinstance(entity, Product):
        raise StateTransitionError("Entity is not Product")

    prev_state = (entity.status or "").strip().lower()

    try:
        domain_event: BaseEvent | None = apply_product_transition(
            session=db,
            product=entity,
            transition=event,
            actor=actor_id or "system",
        )
    except InvalidStateTransition as e:
        raise StateTransitionError(str(e)) from e

    if domain_event:
        add_outbox_event(db, domain_event)

    # история состояния — полезна, но не должна ломать основной флоу
    if _has_state_history_table(db):
        db.add(
            StateHistory(
                id=str(uuid.uuid4()),
                product_id=entity.id,
                from_state=prev_state or None,
                to_state=(entity.status or "").strip().lower(),
                action=event,
                actor_id=actor_id,
                meta=meta,
                created_at=datetime.utcnow(),
            )
        )
    else:
        logger.warning("[state] state_history table missing -> skip history write")

    return entity.status


# Backward-compatible alias
change_product_state = change_state