from __future__ import annotations

from sqlalchemy import Column, BigInteger, String, DateTime, JSON, Text, Index
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(BigInteger, primary_key=True)

    event_type = Column(String, nullable=False)
    aggregate_type = Column(String, nullable=False)
    aggregate_id = Column(String, nullable=False)

    payload = Column(JSON, nullable=False)

    occurred_at = Column(DateTime, nullable=False, server_default=func.now())
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # DB also has partial index ix_outbox_events_unprocessed created by init SQL
        Index("ix_outbox_events_event_type", "event_type"),
    )


class ProcessedEvent(Base):
    """
    Consumer-side idempotency table.
    """
    __tablename__ = "processed_events"

    event_id = Column(String, primary_key=True)
    event_type = Column(String, nullable=False, index=True)
    processed_at = Column(DateTime, server_default=func.now(), nullable=False)