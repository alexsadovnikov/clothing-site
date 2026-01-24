from __future__ import annotations

from uuid import UUID

from apps.api.events.base import BaseEvent


def product_created_v1(
    *,
    product_id: UUID,
    owner_id: UUID,
    status: str,
    title: str | None = None,
    category_id: str | None = None,
) -> BaseEvent:
    return BaseEvent(
        event_type="product.created.v1",
        aggregate_type="product",
        aggregate_id=product_id,
        payload={
            "product_id": str(product_id),
            "owner_id": str(owner_id),
            "status": status,
            "title": title,
            "category_id": category_id,
        },
    )


def product_published_v1(
    *,
    product_id: UUID,
    owner_id: UUID,
    category_id: str | None,
) -> BaseEvent:
    return BaseEvent(
        event_type="product.published.v1",
        aggregate_type="product",
        aggregate_id=product_id,
        payload={
            "product_id": str(product_id),
            "owner_id": str(owner_id),
            "category_id": category_id,
        },
    )

# Backward-compatible alias (do not use in new code)
ProductCreated = product_created_v1
