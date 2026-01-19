from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    BigInteger,
    String,
    DateTime,
    JSON,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(BigInteger, primary_key=True)

    event_type = Column(String, nullable=False, index=True)
    aggregate_type = Column(String, nullable=False)
    aggregate_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    payload = Column(JSON, nullable=False)

    occurred_at = Column(DateTime, nullable=False)
    processed_at = Column(DateTime, nullable=True)
