from typing import Dict

from sqlalchemy.orm import Session

from models import Product, ProductState
from outbox import emit_event
from events.product import product_published_v1


class InvalidStateTransition(Exception):
    """Бизнес-ошибка перехода состояния (4xx)."""
    pass


# ============================================================
# PRODUCT FSM — строго под models.ProductState
# ============================================================

PRODUCT_STATE_TRANSITIONS: Dict[ProductState, Dict[str, ProductState]] = {
    ProductState.DRAFT_EMPTY: {
        "prepare": ProductState.DRAFT_READY,
    },
    ProductState.DRAFT_READY: {
        "ready": ProductState.READY,
    },
    ProductState.READY: {
        "publish": ProductState.PUBLISHED,
    },
    ProductState.PUBLISHED: {
        "archive": ProductState.ARCHIVED,
    },
    ProductState.ARCHIVED: {},
}


# ============================================================
# APPLY TRANSITION
# ============================================================

def apply_product_transition(
    *,
    session: Session,
    product: Product,
    transition: str,
    actor: str | None = None,
) -> ProductState:
    """
    Меняет состояние продукта и кладёт domain-event в outbox.

    ❌ не делает commit
    ❌ не пишет историю
    """

    current_state = product.status

    allowed = PRODUCT_STATE_TRANSITIONS.get(current_state, {})
    if transition not in allowed:
        raise InvalidStateTransition(
            f"Transition '{transition}' not allowed from state '{current_state.value}'"
        )

    next_state = allowed[transition]

    # 1️⃣ Обновляем агрегат
    product.status = next_state

    # 2️⃣ Domain event — только publish
    if transition == "publish":
        emit_event(
            session=session,
            event=product_published_v1(
                product_id=product.id_uuid,
                owner_id=product.owner_id,
                category_id=product.category_id,
            ),
        )

    return next_state