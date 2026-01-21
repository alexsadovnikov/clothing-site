from __future__ import annotations

from typing import Dict, Any

from handlers.analytics import track_event
from handlers.search import index_product


def handle(event: Dict[str, Any]) -> None:
    """
    Handle product.published.v1 domain event.

    Side effects:
    - send analytics event
    - index product in search

    Idempotency is guaranteed by outbox consumer.
    """

    track_event(event)
    index_product(event)