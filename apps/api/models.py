from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

# ============================================================
# BASE — ЕДИНСТВЕННЫЙ SOURCE OF TRUTH ДЛЯ ALEMBIC
# ============================================================

Base = declarative_base()

# ============================================================
# USERS
# ============================================================


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, unique=True, index=True)

    password_hash = Column(String, nullable=False)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    media = relationship(
        "Media",
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
# MEDIA (СООТВЕТСТВУЕТ ТЕКУЩЕЙ БД: owner_id, bucket, object_key, size_bytes)
# ============================================================


class Media(Base):
    __tablename__ = "media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # ВАЖНО: в БД у тебя owner_id — под него и выравниваемся
    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=True)

    size_bytes = Column(Integer, nullable=False)
    bucket = Column(String, nullable=False)
    object_key = Column(String, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="media")


# ============================================================
# AI JOBS (минимально совместимо; можно уточнить после стабилизации upload)
# ============================================================


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")

    payload = Column(Text, nullable=True)
    result = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="jobs")