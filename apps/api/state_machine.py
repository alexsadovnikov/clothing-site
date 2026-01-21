from __future__ import annotations

from typing import Dict
from sqlalchemy.orm import Session

from apps.api.models import Product, ProductState
from apps.api.events.product import product_published_v1
from apps.api.events.base import BaseEvent


class InvalidStateTransition(Exception):
    pass


PRODUCT_STATE_TRANSITIONS: Dict[ProductState, Dict[str, ProductState]] = {
    ProductState.DRAFT_EMPTY: {"prepare": ProductState.DRAFT_READY},
    ProductState.DRAFT_READY: {"ready": ProductState.READY},
    ProductState.READY: {"publish": ProductState.PUBLISHED},
    ProductState.PUBLISHED: {"archive": ProductState.ARCHIVED},
    ProductState.ARCHIVED: {},
}


def apply_product_transition(
    *,
    session: Session,
    product: Product,
    transition: str,
    actor: str | None = None,
) -> BaseEvent | None:

    current_state = product.status
    allowed = PRODUCT_STATE_TRANSITIONS.get(current_state, {})

    if transition not in allowed:
        raise InvalidStateTransition(
            f"Transition '{transition}' not allowed from '{current_state.value}'"
        )

    product.status = allowed[transition]

    if transition == "publish":
        return product_published_v1(
            product_id=product.id_uuid,
            owner_id=product.owner_id,
            category_id=product.category_id,
        )

    return None