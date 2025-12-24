from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, JSON, Text

class Base(DeclarativeBase):
    pass

class Category(Base):
    __tablename__ = "categories"
    id = Column(String, primary_key=True)
    parent_id = Column(String, ForeignKey("categories.id"), nullable=True)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False)
    path = Column(String, nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    ai_aliases = Column(JSON, default=dict)

class Media(Base):
    __tablename__ = "media"
    id = Column(String, primary_key=True)
    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=True)

class AIJob(Base):
    __tablename__ = "ai_jobs"
    id = Column(String, primary_key=True)
    status = Column(String, nullable=False)  # queued/processing/done/error
    media_id = Column(String, ForeignKey("media.id"), nullable=False)
    hint = Column(JSON, default=dict)
    result_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    model_version = Column(String, nullable=True)
    draft_product_id = Column(String, ForeignKey("products.id"), nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True)
    status = Column(String, nullable=False)  # draft/published/archived
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    category_id = Column(String, ForeignKey("categories.id"), nullable=True)
    attributes = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)

class ProductMedia(Base):
    __tablename__ = "product_media"
    id = Column(String, primary_key=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # original/processed
    content_type = Column(String, nullable=True)