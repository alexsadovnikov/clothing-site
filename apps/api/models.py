from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
    JSON,
    Text,
    Index,
    UniqueConstraint,
    CheckConstraint,
    text,
)
from sqlalchemy.types import TypeDecorator, CHAR

try:
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID
except Exception:  # pragma: no cover
    PG_UUID = None


def _utcnow() -> datetime:
    return datetime.utcnow()


SERVER_NOW = text("CURRENT_TIMESTAMP")


class GUID(TypeDecorator):
    """
    Кросс-СУБД UUID тип:
    - PostgreSQL: UUID(as_uuid=True)
    - Остальные: CHAR(36)
    + валидация UUID на входе.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if PG_UUID is not None and dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value if (PG_UUID is not None and dialect.name == "postgresql") else str(value)

        v = uuid.UUID(str(value))  # валидируем формат
        return v if (PG_UUID is not None and dialect.name == "postgresql") else str(v)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class Base(DeclarativeBase):
    pass


# ---------------- Users ----------------

class User(Base):
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    email = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)

    is_active = Column(Boolean, default=True, nullable=False, comment="Аккаунт активен/отключён")

    created_at = Column(DateTime, default=_utcnow, server_default=SERVER_NOW, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, server_default=SERVER_NOW, nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    media = relationship("Media", back_populates="owner", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="owner", cascade="all, delete-orphan")
    looks = relationship("Look", back_populates="owner", cascade="all, delete-orphan")
    wear_logs = relationship("WearLog", back_populates="owner", cascade="all, delete-orphan")
    ai_jobs = relationship("AIJob", back_populates="owner", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
        Index("ix_users_is_active", "is_active"),
        Index("ix_users_deleted_at", "deleted_at"),
        Index("ix_users_deleted_at_is_active", "deleted_at", "is_active"),
    )


# ---------------- Catalog ----------------

class Category(Base):
    __tablename__ = "categories"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    parent_id = Column(GUID(), ForeignKey("categories.id"), nullable=True)

    name = Column(String(255), nullable=False)
    slug = Column(String(120), nullable=False, comment="Слаг категории (уникальный)")
    path = Column(String(1024), nullable=False, comment="Полный путь вида root/sub/...")

    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    ai_aliases = Column(
        JSON,
        default=lambda: {},
        nullable=False,
        comment="Синонимы/алиасы категории для AI"
    )

    parent = relationship("Category", remote_side=[id], backref="children")

    __table_args__ = (
        UniqueConstraint("path", name="uq_categories_path"),
        UniqueConstraint("slug", name="uq_categories_slug"),
        Index("ix_categories_parent_id", "parent_id"),
        Index("ix_categories_path", "path"),
        Index("ix_categories_slug", "slug"),
        # Ограничение на глубину дерева: число '/' в path <= 50
        # (портируемо: LENGTH/REPLACE есть в SQLite/Postgres/MySQL)
        CheckConstraint(
            "(LENGTH(path) - LENGTH(REPLACE(path, '/', ''))) <= 50",
            name="ck_categories_path_depth",
        ),
    )


# ---------------- Media ----------------

class Media(Base):
    __tablename__ = "media"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    bucket = Column(String(128), nullable=False, comment="Название хранилища (например, 'user-uploads')")
    object_key = Column(String(1024), nullable=False)
    content_type = Column(String(100), nullable=False)

    size_bytes = Column(Integer, nullable=True, comment="Размер файла в байтах")
    checksum_sha256 = Column(String(64), nullable=True, comment="SHA256 хэш содержимого (64 hex)")

    created_at = Column(DateTime, default=_utcnow, server_default=SERVER_NOW, nullable=False)

    owner = relationship("User", back_populates="media")
    ai_jobs = relationship("AIJob", back_populates="media", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("bucket", "object_key", name="uq_media_bucket_object_key"),
        Index("ix_media_owner_created", "owner_id", "created_at"),
        CheckConstraint(
            "content_type IN ('image/jpeg','image/png','image/webp')",
            name="ck_media_content_type_image",
        ),
        CheckConstraint(
            "checksum_sha256 IS NULL OR LENGTH(checksum_sha256) = 64",
            name="ck_media_checksum_len_64",
        ),
        # Портируемая защита object_key от URL-ломающих символов:
        # запрещаем пробел, '?', '#', ':' (частые причины проблем с URL/роутингом).
        CheckConstraint(
            "object_key NOT LIKE '% %' AND object_key NOT LIKE '%?%' AND object_key NOT LIKE '%#%' AND object_key NOT LIKE '%:%'",
            name="ck_media_object_key_no_bad_url_chars",
        ),
        # Если нужна строгая regex-проверка ТОЛЬКО под PostgreSQL, лучше добавить через Alembic миграцию:
        # CheckConstraint(
        #     "object_key ~ '^[a-zA-Z0-9_./-]+$'",
        #     name="ck_media_object_key_safe_chars",
        # )
    )


# ---------------- Products ----------------

class Product(Base):
    __tablename__ = "products"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(24), nullable=False, comment="draft/published/archived")
    title = Column(String(200), nullable=True, comment="Название вещи (до 200 символов)")
    description = Column(Text, nullable=True)

    category_id = Column(GUID(), ForeignKey("categories.id"), nullable=True)

    attributes = Column(JSON, default=lambda: {}, nullable=False)
    tags = Column(JSON, default=lambda: [], nullable=False)

    created_at = Column(DateTime, default=_utcnow, server_default=SERVER_NOW, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, server_default=SERVER_NOW, nullable=False)

    owner = relationship("User", back_populates="products")
    category = relationship("Category")

    # Медиафайлы, связанные с продуктом (изображения, обработанные версии и т.д.)
    media_items = relationship("ProductMedia", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_products_owner_status", "owner_id", "status"),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_owner_updated", "owner_id", "updated_at"),
        Index("ix_products_status", "status"),
        # Ограничение на длину описания (если важно на уровне БД)
        CheckConstraint(
            "description IS NULL OR LENGTH(description) <= 10000",
            name="ck_products_description_len_10000",
        ),
    )


class ProductMedia(Base):
    __tablename__ = "product_media"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    product_id = Column(GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)

    bucket = Column(String(128), nullable=False, comment="Название хранилища (например, 'user-uploads')")
    object_key = Column(String(1024), nullable=False)

    kind = Column(String(24), nullable=False, comment="original/processed")
    content_type = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=_utcnow, server_default=SERVER_NOW, nullable=False)

    product = relationship("Product", back_populates="media_items")

    __table_args__ = (
        UniqueConstraint(
            "product_id", "bucket", "object_key", "kind",
            name="uq_product_media_product_bucket_key_kind",
        ),
        Index("ix_product_media_product_id", "product_id"),
        Index("ix_product_media_kind", "kind"),
        CheckConstraint("kind IN ('original','processed')", name="ck_product_media_kind"),
    )


# ---------------- Looks ----------------

class Look(Base):
    __tablename__ = "looks"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(200), nullable=True)
    occasion = Column(String(64), nullable=True)  # work/date/travel/party/etc
    season = Column(String(32), nullable=True)    # winter/summer/demi/all

    created_at = Column(DateTime, default=_utcnow, server_default=SERVER_NOW, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, server_default=SERVER_NOW, nullable=False)

    owner = relationship("User", back_populates="looks")
    items = relationship("LookItem", back_populates="look", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_looks_owner_created", "owner_id", "created_at"),
        Index("ix_looks_owner_updated", "owner_id", "updated_at"),
        Index("ix_looks_occasion", "occasion"),
        Index("ix_looks_season", "season"),
    )


class LookItem(Base):
    __tablename__ = "look_items"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    look_id = Column(GUID(), ForeignKey("looks.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime, default=_utcnow, server_default=SERVER_NOW, nullable=False)

    look = relationship("Look", back_populates="items")
    product = relationship("Product")

    __table_args__ = (
        UniqueConstraint("look_id", "product_id", name="uq_look_items_look_product"),
        Index("ix_look_items_look_id", "look_id"),
        Index("ix_look_items_product_id", "product_id"),
    )


# ---------------- Wear log ----------------

class WearLog(Base):
    __tablename__ = "wear_log"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(GUID(), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)

    worn_at = Column(DateTime, nullable=False)
    context = Column(String(64), nullable=True, comment="work/date/travel/party/other")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=_utcnow, server_default=SERVER_NOW, nullable=False)

    owner = relationship("User", back_populates="wear_logs")
    product = relationship("Product")

    __table_args__ = (
        Index("ix_wear_log_owner_worn_at", "owner_id", "worn_at"),
        Index("ix_wear_log_product_worn_at", "product_id", "worn_at"),
        Index("ix_wear_log_worn_at_owner", "worn_at", "owner_id"),
        CheckConstraint(
            "context IS NULL OR context IN ('work','date','travel','party','other')",
            name="ck_wear_log_context",
        ),
    )


# ---------------- AI Jobs ----------------

class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    owner_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(24), nullable=False, comment="queued/processing/finished/failed")

    media_id = Column(GUID(), ForeignKey("media.id", ondelete="CASCADE"), nullable=False)

    hint = Column(
        JSON,
        default=lambda: {},
        nullable=False,
        comment="Подсказки для AI в формате JSON",
    )

    result_json = Column(
        JSON,
        nullable=True,
        comment="Результат работы AI в формате JSON",
    )

    error = Column(Text, nullable=True)

    model_version = Column(
        String(64),
        nullable=True,
        comment="Версия модели AI, например 'v1.2.0'",
    )

    draft_product_id = Column(
        GUID(),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        comment="Draft product, созданный по результату AI (если применимо)",
    )

    created_at = Column(DateTime, default=_utcnow, server_default=SERVER_NOW, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, server_default=SERVER_NOW, nullable=False)

    owner = relationship("User", back_populates="ai_jobs")
    media = relationship("Media", back_populates="ai_jobs")
    draft_product = relationship("Product")

    __table_args__ = (
        Index("ix_ai_jobs_owner_created", "owner_id", "created_at"),
        Index("ix_ai_jobs_media_id", "media_id"),
        Index("ix_ai_jobs_draft_product_id", "draft_product_id"),
        Index("ix_ai_jobs_status", "status"),
        Index("ix_ai_jobs_model_version", "model_version"),
        Index("ix_ai_jobs_error", "error"),
        # Ограничение на размер result_json (работает в SQLite/Postgres через CAST AS TEXT).
        # Если появится MySQL — может потребоваться адаптация (CAST(... AS CHAR)).
        CheckConstraint(
            "result_json IS NULL OR LENGTH(CAST(result_json AS TEXT)) <= 100000",
            name="ck_ai_job_result_json_size_100k",
        ),
    )