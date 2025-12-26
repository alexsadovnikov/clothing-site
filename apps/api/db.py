import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Берём из .env (через docker compose env_file), чистим пробелы
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

# Важно: импорт после engine/sessionmaker (во избежание циклических импортов)
import models  # noqa: E402,F401  (важно: загружаем модели)
from models import Base  # noqa: E402


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