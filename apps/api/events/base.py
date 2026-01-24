from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class BaseEvent:
    """
    Canonical domain event object.

    Notes:
    - event_id MUST exist (idempotency key for consumer)
    - occurred_at is timezone-aware UTC
    - aggregate_id is stored as string in canonical DB schema
    """
    event_type: str
    aggregate_type: str
    aggregate_id: str

    payload: Dict[str, Any] = field(default_factory=dict)

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=utcnow)

    # Optional: for analytics / tracing, without DB schema changes
    event_schema: Optional[str] = None

    def to_outbox(self) -> dict:
        """
        What producer writes into outbox_events.
        DB columns:
          event_type, aggregate_type, aggregate_id, payload, occurred_at
        """
        payload = dict(self.payload or {})
        payload.setdefault("event_id", self.event_id)

        return {
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "payload": payload,
            "occurred_at": self.occurred_at,
        }
