from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy.orm import Session

from models import Product, StateHistory
from state_machine import apply_product_transition

EntityType = Literal["product"]


class StateTransitionError(Exception):
    """
    Бизнес-ошибка перехода состояния (4xx).
    """
    pass


def change_state(
    *,
    db: Session,
    entity,
    entity_type: EntityType,
    event: str,
    actor_id: str | None = None,
):
    """
    Универсальный сервис смены состояния.

    Для product:
    - вызывает FSM (state_machine)
    - пишет audit history

    ❌ НЕ коммитит
    ❌ НЕ эмитит события напрямую (это делает FSM)
    """

    if entity_type != "product":
        raise StateTransitionError("Only product supported")

    if not isinstance(entity, Product):
        raise StateTransitionError("Entity is not Product")

    current_state = entity.status

    # 1️⃣ FSM + domain events
    apply_product_transition(
        session=db,
        product=entity,
        transition=event,
        actor=actor_id or "system",
    )

    # 2️⃣ Audit log
    history = StateHistory(
        id=uuid.uuid4(),
        entity_type="product",
        entity_id=entity.id_uuid,
        from_state=current_state.value if current_state else None,
        to_state=entity.status,
        event=event,
        actor=str(actor_id) if actor_id else None,
    )

    db.add(history)

    return entity.status