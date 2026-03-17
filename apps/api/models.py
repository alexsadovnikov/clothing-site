from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, synonym
from sqlalchemy.sql import func

Base = declarative_base()


# ============================================================
# MIXINS (timestamps)
# ============================================================

class CreatedAtMixin:
    created_at = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
    )


class TimestampsMixin(CreatedAtMixin):
    updated_at = Column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


# ============================================================
# ENUMS
# ============================================================

class ProductState(str, Enum):
    DRAFT_EMPTY = "draft_empty"
    DRAFT_READY = "draft_ready"
    READY = "ready"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AIJobState(str, Enum):
    """
    Бизнес-состояние AI job (FSM).

    Используется для:
    - поля ai_jobs.status
    - state_service / change_state
    - бизнес-условий (SUCCEEDED → create product и т.д.)

    Это НЕ pipeline и НЕ progress.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AIJobStage(str, Enum):
    """
    Строгий backend-контракт этапов выполнения AI job (backend → frontend).

    Порядок фиксирован, пропускать этапы нельзя.
    Пишет ТОЛЬКО backend, frontend — только читает.

    Порядок этапов:
    1. queued
    2. analyze_request
    3. ai_processing
    4. ai_response_received
    5. product_create
    6. state_transition
    7. done
    8. failed
    """

    QUEUED = "queued"
    ANALYZE_REQUEST = "analyze_request"
    AI_PROCESSING = "ai_processing"
    AI_RESPONSE_RECEIVED = "ai_response_received"
    PRODUCT_CREATE = "product_create"
    STATE_TRANSITION = "state_transition"
    DONE = "done"
    FAILED = "failed"

    # legacy aliases (ТОЛЬКО для normalize / чтения, НЕ для записи)
    PROCESSING = "running"
    SUCCEEDED = "succeeded"

    @classmethod
    def terminal(cls) -> set[str]:
        return {cls.DONE.value, cls.FAILED.value}

    @classmethod
    def active(cls) -> set[str]:
        return {
            cls.QUEUED.value,
            cls.ANALYZE_REQUEST.value,
            cls.AI_PROCESSING.value,
            cls.AI_RESPONSE_RECEIVED.value,
            cls.PRODUCT_CREATE.value,
            cls.STATE_TRANSITION.value,
        }



# ============================================================
# CATALOG
# ============================================================

class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_id = Column(String, ForeignKey("categories.id"), nullable=True)

    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, index=True)
    path = Column(String, nullable=False, index=True)

    sort_order = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=True)
    ai_aliases = Column(JSON, nullable=True)

    parent = relationship("Category", remote_side=[id], backref="children")


# ============================================================
# USERS
# ============================================================

class User(Base, TimestampsMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, index=True)

    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False)

    deleted_at = Column(DateTime(timezone=False), nullable=True)

    media = relationship(
        "Media",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    products = relationship(
        "Product",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    jobs = relationship(
        "AIJob",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# ============================================================
# MEDIA
# ============================================================

class Media(Base, CreatedAtMixin):
    __tablename__ = "media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)

    content_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    filename = Column(String, nullable=True)

    user = relationship("User", back_populates="media")

    jobs = relationship(
        "AIJob",
        back_populates="media",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    product_links = relationship(
        "ProductMedia",
        back_populates="media",
        passive_deletes=True,
    )


# ============================================================
# PRODUCTS
# ============================================================

class Product(Base, TimestampsMixin):
    __tablename__ = "products"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(String, nullable=False)

    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    category_id = Column(String, ForeignKey("categories.id"), nullable=True)

    attributes = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)

    user = relationship("User", back_populates="products")
    category = relationship("Category")

    media = relationship(
        "ProductMedia",
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    jobs = relationship("AIJob", back_populates="draft_product")


# ============================================================
# PRODUCT MEDIA
# ============================================================

class ProductMedia(Base, CreatedAtMixin):
    __tablename__ = "product_media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    product_id = Column(
        String,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    media_id = Column(
        String,
        ForeignKey("media.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    kind = Column(String, nullable=False)

    product = relationship("Product", back_populates="media")
    media = relationship("Media", back_populates="product_links")


# ============================================================
# AI JOBS
# ============================================================

class AIJob(Base, TimestampsMixin):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        CheckConstraint(
            "stage IS NULL OR stage IN ("
            "'queued','analyze_request','ai_processing','ai_response_received',"
            "'product_create','state_transition','done','failed'"
            ")",
            name="ck_ai_jobs_stage_valid",
        ),
        Index("ix_ai_jobs_status", "status"),
        Index("ix_ai_jobs_stage", "stage"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    owner_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # основной статус (legacy + совместимость)
    status = Column(String, nullable=False)

    # === SERVER-SIDE PROGRESS CONTRACT ===
    progress = Column(Integer, nullable=True)        # 0–100
    stage = Column(String, nullable=True)            # AIJobStage
    stage_message = Column(Text, nullable=True)      # human readable
    # ===================================

    media_id = Column(
        String,
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    hint = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=True)

    # legacy error
    error = Column(Text, nullable=True)

    # structured error
    error_code = Column(String, nullable=True)
    error_stage = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    model_version = Column(String, nullable=True)

    draft_product_id = Column(
        String,
        ForeignKey("products.id"),
        nullable=True,
    )

    # legacy compatibility
    user_id = synonym("owner_id")

    user = relationship("User", back_populates="jobs")
    media = relationship("Media", back_populates="jobs")
    draft_product = relationship("Product", back_populates="jobs")

    # -------------------------
    # helpers
    # -------------------------

    def set_stage(self, stage: AIJobStage, message: str | None = None) -> None:
        self.stage = stage.value
        self.stage_message = message

        if stage == AIJobStage.DONE:
            self.status = AIJobState.SUCCEEDED.value
            self.progress = 100
        elif stage == AIJobStage.FAILED:
            self.status = AIJobState.FAILED.value

    @property
    def is_completed(self) -> bool:
        return self.stage in (
            AIJobStage.DONE.value,
            AIJobStage.FAILED.value,
        )

    @property
    def progress_percent(self) -> int:
        if not self.stage:
            return 0
        stages = list(AIJobStage)
        try:
            idx = stages.index(AIJobStage(self.stage))
            return int((idx / (len(stages) - 1)) * 100)
        except Exception:
            return 0

    def __repr__(self) -> str:
        return f"<AIJob id={self.id} status={self.status} stage={self.stage}>"


# ============================================================
# OUTBOX
# ============================================================

class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    event_type = Column(String, nullable=False)
    aggregate_type = Column(String, nullable=False)
    aggregate_id = Column(String, nullable=False)

    payload = Column(JSON, nullable=False)

    occurred_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    processed_at = Column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("ix_outbox_events_event_type", "event_type"),
        Index("ix_outbox_events_aggregate_id", "aggregate_id"),
    )


# ============================================================
# OPTIONAL / FUTURE MODELS
# ============================================================

class StateHistory(Base):
    __tablename__ = "state_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(
        String,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    from_state = Column(String, nullable=True)
    to_state = Column(String, nullable=False)

    action = Column(String, nullable=True)
    actor_id = Column(
        String,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=False), nullable=True)

    product = relationship("Product", backref="state_history")
    actor = relationship("User")


class Look(Base):
    __tablename__ = "looks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), nullable=True)
    updated_at = Column(DateTime(timezone=False), nullable=True)

    user = relationship("User", backref="looks")


class LookItem(Base):
    __tablename__ = "look_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    look_id = Column(
        String,
        ForeignKey("looks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = Column(
        String,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sort_order = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=False), nullable=True)

    look = relationship("Look", backref="items")
    product = relationship("Product")


class WearLog(Base):
    __tablename__ = "wear_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = Column(
        String,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    worn_at = Column(DateTime(timezone=False), nullable=True)
    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=False), nullable=True)

    user = relationship("User", backref="wear_logs")
    product = relationship("Product", backref="wear_logs")
