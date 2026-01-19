from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict
import uuid


@dataclass
class BaseEvent:
    event_type: str
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: Dict[str, Any]
    occurred_at: datetime

    def to_outbox(self) -> dict:
        return {
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "payload": self.payload,
            "occurred_at": self.occurred_at,
        }
