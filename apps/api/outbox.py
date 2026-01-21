import uuid
from sqlalchemy.orm import Session

from apps.api.models import OutboxEvent
from apps.api.events.base import BaseEvent


def add_outbox_event(db: Session, event: BaseEvent):
    db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            payload=event.payload,
            occurred_at=event.occurred_at,
        )
    )