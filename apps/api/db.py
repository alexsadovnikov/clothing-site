# db.py
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models import Base  # ✅ безопасно: Base живёт в models


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (check .env and docker compose env_file)")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)


def init_db() -> None:
    """
    DEV/MVP fallback режим:
    Создание таблиц напрямую ТОЛЬКО по флагу.
    По умолчанию используем Alembic миграции.
    """
    if os.getenv("AUTO_CREATE_DB", "0") == "1":
        Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()