from __future__ import annotations

from typing import Dict, Any

from handlers.analytics import track_event
from handlers.search import index_product


def handle(event: Dict[str, Any]) -> None:
    """
    product.published.v1
    """

    track_event(event)
    index_product(event)
