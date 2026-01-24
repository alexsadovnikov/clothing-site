from __future__ import annotations

from enum import Enum

import uuid
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship, synonym

Base = declarative_base()


class ProductState(str, Enum):
    DRAFT_EMPTY = "draft_empty"
    DRAFT_READY = "draft_ready"
    READY = "ready"
    PUBLISHED = "published"
    ARCHIVED = "archived"
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


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, index=True)

    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    media = relationship("Media", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    products = relationship("Product", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    jobs = relationship("AIJob", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class Media(Base):
    __tablename__ = "media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)

    content_type = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True)

    filename = Column(String, nullable=True)

    user = relationship("User", back_populates="media")
    jobs = relationship("AIJob", back_populates="media", cascade="all, delete-orphan", passive_deletes=True)


class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String, nullable=False)

    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    category_id = Column(String, ForeignKey("categories.id"), nullable=True)

    attributes = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="products")
    category = relationship("Category")
    media = relationship("ProductMedia", back_populates="product", cascade="all, delete-orphan", passive_deletes=True)
    jobs = relationship("AIJob", back_populates="draft_product")


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False)

    media_id = Column(String, ForeignKey("media.id", ondelete="CASCADE"), nullable=False, index=True)

    hint = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=True)

    error = Column(Text, nullable=True)
    model_version = Column(String, nullable=True)

    draft_product_id = Column(String, ForeignKey("products.id"), nullable=True)

    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

    # совместимость со старым кодом, где могли ожидать user_id
    user_id = synonym("owner_id")

    user = relationship("User", back_populates="jobs")
    media = relationship("Media", back_populates="jobs")
    draft_product = relationship("Product", back_populates="jobs")


class ProductMedia(Base):
    __tablename__ = "product_media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id = Column(String, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)

    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)
    kind = Column(String, nullable=False)

    content_type = Column(String, nullable=True)

    product = relationship("Product", back_populates="media")
