import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Берём из .env (через docker compose env_file), чистим пробелы
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (check .env and docker compose env_file)")

# pool_pre_ping помогает при разрывах соединения с Postgres
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
from models import Base  # noqa: E402


def init_db() -> None:
    """
    MVP режим:
    создаём таблицы напрямую (без alembic миграций).
    """
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency:
    - отдаёт SQLAlchemy Session
    - гарантирует закрытие сессии в конце запроса
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()