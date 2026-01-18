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
    Table,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

# ============================================================
# BASE
# ============================================================

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
    """
    Состояние карточки продукта.
    """
    DRAFT_EMPTY = "DRAFT_EMPTY"
    DRAFT_READY = "DRAFT_READY"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


# ============================================================
# ASSOCIATION TABLE
# products <-> media
# M:N через UUID (АКТУАЛЬНАЯ СХЕМА)
# ============================================================

product_media = Table(
    "product_media",
    Base.metadata,
    Column(
        "product_id_uuid",
        UUID(as_uuid=True),
        ForeignKey("products.id_uuid", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "media_id",
        String,
        ForeignKey("media.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


# ============================================================
# CATEGORY
# ============================================================

class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True)
    path = Column(String, nullable=False)
    title = Column(String, nullable=False)


# ============================================================
# PRODUCT
# PRIMARY KEY = id_uuid
# legacy id — временно (PHASE 5 → удалить)
# ============================================================

class Product(Base):
    __tablename__ = "products"

    # 🔥 ЕДИНСТВЕННЫЙ АКТУАЛЬНЫЙ PRIMARY KEY
    id_uuid = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ⚠️ legacy string id (старые данные / обратная совместимость)
    # PHASE 5: колонка будет удалена
    id = Column(String, nullable=False, unique=True, index=True)

    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(
        String,  # Enum переведём позже, когда уберём legacy
        nullable=False,
        default=ProductState.DRAFT_EMPTY.value,
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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    # 🔥 M:N MEDIA через UUID
    media = relationship(
        "Media",
        secondary=product_media,
        back_populates="products",
        lazy="selectin",
    )


# ============================================================
# MEDIA
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

    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship(
        "Product",
        secondary=product_media,
        back_populates="media",
        lazy="selectin",
    )


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

    # 🔥 UUID-ссылка на продукт (draft / результат AI)
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

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)