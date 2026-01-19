from __future__ import annotations

import logging
from typing import Dict, Any

logger = logging.getLogger("search")


def index_product(event: Dict[str, Any]) -> None:
    """
    Обновление поискового индекса.

    Здесь позже:
    - Meilisearch
    - Elasticsearch
    - OpenSearch
    """

    payload = event["payload"]

    logger.info(
        "Index product",
        extra={
            "product_id": payload.get("product_id"),
            "category_id": payload.get("category_id"),
            "status": payload.get("status"),
        },
    )
