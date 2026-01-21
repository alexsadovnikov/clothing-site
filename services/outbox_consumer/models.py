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
from sqlalchemy.sql import func

Base = declarative_base()


# ============================================================
# OUTBOX EVENTS (SOURCE OF TRUTH, PRODUCER-SIDE)
# ============================================================

class OutboxEvent(Base):
    """
    Immutable domain events written by API inside business transaction.
    Consumer reads from this table.
    """

    __tablename__ = "outbox_events"

    id = Column(BigInteger, primary_key=True)

    event_type = Column(String, nullable=False, index=True)
    aggregate_type = Column(String, nullable=False)
    aggregate_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    payload = Column(JSON, nullable=False)

    occurred_at = Column(DateTime, nullable=False)
    processed_at = Column(DateTime, nullable=True)


# ============================================================
# PROCESSED EVENTS (CONSUMER-SIDE IDEMPOTENCY)
# ============================================================

class ProcessedEvent(Base):
    """
    Consumer-side idempotency table.

    Guarantees that each domain event (event_id)
    is processed at most once, even if:
    - consumer crashes
    - retries happen
    - multiple consumers run in parallel
    """

    __tablename__ = "processed_events"

    # 🔥 event_id из payload (UUID в виде строки)
    event_id = Column(String, primary_key=True)

    # Тип события (для диагностики / аналитики)
    event_type = Column(String, nullable=False, index=True)

    # Когда side-effect был успешно зафиксирован
    processed_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )