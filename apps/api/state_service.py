import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from models import StateHistory
from state_machine import PRODUCT_STATE_TRANSITIONS, InvalidStateTransition


EntityType = Literal["product", "media", "ai_job"]


class StateTransitionError(Exception):
    """
    Бизнес-ошибка перехода состояния.
    НЕ является системной ошибкой (500).
    """
    pass


# ============================================================
# ВАЛИДАЦИЯ ПЕРЕХОДА (ТОЛЬКО ДЛЯ PRODUCT)
# ============================================================

def _validate_transition(current_state, event: str, transitions: dict):
    if current_state not in transitions:
        raise StateTransitionError(
            f"No transitions defined for state: {current_state}"
        )

    if event not in transitions[current_state]:
        allowed = ", ".join(transitions[current_state].keys())
        raise InvalidStateTransition(
            f"Event '{event}' is not allowed from state '{current_state}'. "
            f"Allowed events: {allowed}"
        )

    return transitions[current_state][event]


# ============================================================
# УНИВЕРСАЛЬНЫЙ CHANGE_STATE
# ============================================================

def change_state(
    db: Session,
    entity,
    entity_type: EntityType,
    event: str,
    actor_id: str | None = None,
):
    """
    Универсальный сервис фиксации состояния / событий.

    - product → строгая FSM (state_machine)
    - media / ai_job → event-only (без FSM)
    """

    # --------------------------------------------------------
    # PRODUCT — строгая FSM
    # --------------------------------------------------------
    if entity_type == "product":
        current_state = entity.state

        next_state = _validate_transition(
            current_state=current_state,
            event=event,
            transitions=PRODUCT_STATE_TRANSITIONS,
        )

        entity.state = next_state

        history = StateHistory(
            id=uuid.uuid4(),
            entity_type="product",
            entity_id=entity.id,
            from_state=current_state.value if current_state else None,
            to_state=next_state.value,
            event=event,
            actor=str(actor_id) if actor_id else None,
            created_at=datetime.utcnow(),
        )

        db.add(history)
        return next_state

    # --------------------------------------------------------
    # MEDIA / AI_JOB — ТОЛЬКО ФИКСАЦИЯ СОБЫТИЯ
    # --------------------------------------------------------
    if entity_type in ("media", "ai_job"):
        history = StateHistory(
            id=uuid.uuid4(),
            entity_type=entity_type,
            entity_id=entity.id,
            from_state=None,
            to_state=None,
            event=event,
            actor=str(actor_id) if actor_id else None,
            created_at=datetime.utcnow(),
        )

        db.add(history)
        return None

    # --------------------------------------------------------
    # НЕИЗВЕСТНАЯ СУЩНОСТЬ
    # --------------------------------------------------------
    raise StateTransitionError(f"Unsupported entity_type: {entity_type}")