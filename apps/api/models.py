from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Boolean,
    BigInteger,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

# ============================================================
# ENUMS
# ============================================================

class AIJobState(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    FAILED = "failed"
    DONE = "done"


class ProductState(str, enum.Enum):
    DRAFT_EMPTY = "DRAFT_EMPTY"
    DRAFT_READY = "DRAFT_READY"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


# ============================================================
# USER
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)
    deleted_at = Column(DateTime)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


# ============================================================
# CATEGORY
# ============================================================

class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True)
    path = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)


# ============================================================
# PRODUCT
# ============================================================

class Product(Base):
    __tablename__ = "products"

    id_uuid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # legacy id (будет удалён позже)
    id = Column(String, nullable=False, unique=True, index=True)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(
        Enum(ProductState, name="product_state"),
        nullable=False,
        default=ProductState.DRAFT_EMPTY,
        index=True,
    )

    title = Column(String)
    description = Column(String)

    category_id = Column(
        String,
        ForeignKey("categories.id"),
        nullable=True,
        index=True,
    )

    attributes = Column(JSON)
    tags = Column(JSON)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # ВАЖНО: product_media — это НЕ many-to-many
    media_items = relationship(
        "ProductMedia",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# ============================================================
# PRODUCT MEDIA (РЕАЛЬНАЯ ТАБЛИЦА, НЕ ASSOCIATION)
# ============================================================

class ProductMedia(Base):
    __tablename__ = "product_media"

    id = Column(String, primary_key=True)

    product_id_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id_uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id = Column(String, nullable=False)

    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)
    kind = Column(String, nullable=False)
    content_type = Column(String)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    product = relationship("Product", back_populates="media_items")


# ============================================================
# MEDIA (как физический объект, используется AIJob)
# ============================================================

class Media(Base):
    __tablename__ = "media"

    id = Column(String, primary_key=True)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)
    content_type = Column(String, nullable=False)

    size_bytes = Column(BigInteger)
    checksum_sha256 = Column(String(64))

    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# ============================================================
# AI JOB
# ============================================================

class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(String, primary_key=True)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    media_id = Column(
        String,
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    draft_product_id_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id_uuid", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status = Column(
        Enum(AIJobState, name="ai_job_state"),
        nullable=False,
        default=AIJobState.QUEUED,
        index=True,
    )

    hint = Column(JSON, default=dict)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


# ============================================================
# OUTBOX EVENTS
# ============================================================

class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(BigInteger, primary_key=True)

    event_type = Column(String, nullable=False, index=True)
    aggregate_type = Column(String, nullable=False)
    aggregate_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    payload = Column(JSON, nullable=False)

    occurred_at = Column(DateTime, server_default=func.now(), nullable=False)
    processed_at = Column(DateTime, nullable=True)


# ============================================================
# STATE HISTORY (AUDIT LOG)
# ============================================================

class StateHistory(Base):
    __tablename__ = "state_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entity_type = Column(String, nullable=False, index=True)
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    from_state = Column(String, nullable=True)
    to_state = Column(String, nullable=True)

    event = Column(String, nullable=False)
    actor = Column(String, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)