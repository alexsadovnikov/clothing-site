from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from apps.api.models import OutboxEvent  # canonical table mapping
from apps.api.events.base import BaseEvent


def write_outbox_event(db: Session, event: BaseEvent) -> OutboxEvent:
    """
    Writes domain event into canonical outbox_events table.

    Canonical DB schema (db/init/001_schema.sql):
      outbox_events (
        id bigserial PK,
        event_type varchar not null,
        aggregate_type varchar not null,
        aggregate_id varchar not null,
        payload json not null,
        occurred_at timestamp not null default now(),
        processed_at timestamp null
      )
    """
    outbox_row = event.to_outbox()

    # Normalize occurred_at:
    occurred_at: Any = outbox_row.get("occurred_at")
    if isinstance(occurred_at, datetime):
        # store naive timestamp (DB is timestamp without tz)
        if occurred_at.tzinfo is not None:
            occurred_at = occurred_at.astimezone(datetime.UTC).replace(tzinfo=None)
        else:
            occurred_at = occurred_at
    else:
        occurred_at = None

    row = OutboxEvent(
        event_type=outbox_row["event_type"],
        aggregate_type=outbox_row["aggregate_type"],
        aggregate_id=str(outbox_row["aggregate_id"]),
        payload=outbox_row["payload"],
        occurred_at=occurred_at,  # can be None -> DB default now()
        processed_at=None,
    )

    db.add(row)
    # flush ensures row.id is available if needed in the same transaction
    db.flush()
    return row
