from __future__ import annotations

from typing import Dict
from sqlalchemy.orm import Session

from apps.api.models import Product, ProductState
from apps.api.events.product import product_published_v1
from apps.api.events.base import BaseEvent


class InvalidStateTransition(Exception):
    pass


# NOTE:
# Product.status в БД — это строка (VARCHAR), не Enum.
# Поэтому transitions храним по string value.
PRODUCT_STATE_TRANSITIONS: Dict[str, Dict[str, str]] = {
    ProductState.DRAFT_EMPTY.value: {
        "prepare": ProductState.DRAFT_READY.value,
        # alias: worker может сразу перевести продукт в READY после AI анализа
        "ready_for_publish": ProductState.READY.value,
    },
    ProductState.DRAFT_READY.value: {
        "ready": ProductState.READY.value,
        # alias (чтобы было единообразно)
        "ready_for_publish": ProductState.READY.value,
    },
    ProductState.READY.value: {
        "publish": ProductState.PUBLISHED.value,
    },
    ProductState.PUBLISHED.value: {
        "archive": ProductState.ARCHIVED.value,
    },
    ProductState.ARCHIVED.value: {},
}


def apply_product_transition(
    *,
    session: Session,
    product: Product,
    transition: str,
    actor: str | None = None,
) -> BaseEvent | None:
    current_state = (product.status or "").strip().lower()
    transition = (transition or "").strip().lower()

    allowed = PRODUCT_STATE_TRANSITIONS.get(current_state, {})
    if transition not in allowed:
        raise InvalidStateTransition(
            f"Transition '{transition}' not allowed from '{current_state}'"
        )

    product.status = allowed[transition]

    if transition == "publish":
        # Product.id — строковый uuid (как в твоей модели)
        return product_published_v1(
            product_id=product.id,
            owner_id=product.owner_id,
            category_id=product.category_id,
        )

    return None