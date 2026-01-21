from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy.orm import Session
from apps.api.models import Product, StateHistory
from apps.api.state_machine import apply_product_transition
from apps.api.outbox import add_outbox_event
from apps.api.events.base import BaseEvent

EntityType = Literal["product"]


class StateTransitionError(Exception):
    pass


def change_state(
    *,
    db: Session,
    entity,
    entity_type: EntityType,
    event: str,
    actor_id: str | None = None,
):
    if entity_type != "product":
        raise StateTransitionError("Only product supported")

    if not isinstance(entity, Product):
        raise StateTransitionError("Entity is not Product")

    prev_state = entity.status

    domain_event: BaseEvent | None = apply_product_transition(
        session=db,
        product=entity,
        transition=event,
        actor=actor_id or "system",
    )

    if domain_event:
        add_outbox_event(db, domain_event)

    db.add(
        StateHistory(
            id=uuid.uuid4(),
            entity_type="product",
            entity_id=entity.id_uuid,
            from_state=prev_state.value if prev_state else None,
            to_state=entity.status.value,
            event=event,
            actor=actor_id,
        )
    )

    return entity.status