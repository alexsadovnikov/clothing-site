from __future__ import annotations

from uuid import UUID

from events.base import BaseEvent


def product_created_v1(
    *,
    product_id: UUID,
    owner_id: UUID,
    status: str,
    title: str | None = None,
    category_id: str | None = None,
) -> BaseEvent:
    """
    Domain event: product.created.v1
    """
    return BaseEvent(
        event_type="product.created",
        aggregate_type="product",
        aggregate_id=product_id,
        payload={
            "product_id": str(product_id),
            "owner_id": str(owner_id),
            "status": status,
            "title": title,
            "category_id": category_id,
        },
        event_schema="product.created.v1",
    )


def product_published_v1(
    *,
    product_id: UUID,
    owner_id: UUID,
    category_id: str | None,
) -> BaseEvent:
    """
    Domain event: product.published.v1
    """
    return BaseEvent(
        event_type="product.published",
        aggregate_type="product",
        aggregate_id=product_id,
        payload={
            "product_id": str(product_id),
            "owner_id": str(owner_id),
            "category_id": category_id,
        },
        event_schema="product.published.v1",
    )