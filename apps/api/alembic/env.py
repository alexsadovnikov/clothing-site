from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool


# Alembic Config object (alembic.ini)
config = context.config

# Logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _build_db_url() -> str:
    """
    Priority:
    1) DATABASE_URL / SQLALCHEMY_DATABASE_URL
    2) POSTGRES_* parts -> postgresql+psycopg2://...
    """
    url = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URL")
    if url:
        return url

    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd = os.getenv("POSTGRES_PASSWORD", "postgres")
    db = os.getenv("POSTGRES_DB", "postgres")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"


# Inject runtime DB URL into alembic config (works in контейнере и локально)
config.set_main_option("sqlalchemy.url", _build_db_url())


# --- TARGET METADATA ---
# В вашем проекте обычно:
# - Base в db.py
# - модели в models.py
#
# ВАЖНО: импорт models должен произойти, чтобы таблицы попали в Base.metadata
try:
    # /app/db.py (apps/api/db.py копируется в /app/db.py согласно Dockerfile COPY . /app)
    from db import Base  # type: ignore
except Exception:
    # fallback (если Base лежит в models.py)
    from models import Base  # type: ignore

# импортируем models, чтобы зарегистрировать таблицы
try:
    import models  # noqa: F401
except Exception:
    # если у тебя модели разнесены по папкам, добавь импорты сюда
    # например: import app_models.products, app_models.users ...
    pass

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Offline: генерит SQL без подключения к БД.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Online: подключается к БД и применяет миграции.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()