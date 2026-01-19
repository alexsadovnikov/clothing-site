from __future__ import annotations

import logging
from typing import Dict, Any

logger = logging.getLogger("analytics")


def track_event(event: Dict[str, Any]) -> None:
    """
    Универсальный analytics handler.

    Здесь в будущем:
    - ClickHouse
    - BigQuery
    - Kafka
    - Amplitude / Segment
    """

    logger.info(
        "Analytics event",
        extra={
            "event_type": event["event_type"],
            "schema": event["event_schema"],
            "aggregate": event["aggregate"],
            "payload": event["payload"],
        },
    )
