from __future__ import annotations

from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool
from alembic import context

# IMPORTANT:
# env.py is executed by Alembic CLI. When it is imported as a regular module,
# alembic.context has no attribute "config". In that case we must do nothing
# and MUST NOT raise any exception (your import_check treats any exception as FAIL).
if not hasattr(context, "config"):
    # Safe no-op on plain import
    pass
else:
    config = context.config

    # Interpret the config file for Python logging.
    # This line sets up loggers basically.
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)

    # Import metadata
    from apps.api.models import Base  # noqa: E402
    target_metadata = Base.metadata

    def _get_url() -> str:
        # Prefer env var (works well in Docker), fallback to alembic.ini
        url = os.getenv("DATABASE_URL")
        if url:
            return url
        return config.get_main_option("sqlalchemy.url")

    def run_migrations_offline() -> None:
        url = _get_url()
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    def run_migrations_online() -> None:
        configuration = config.get_section(config.config_ini_section) or {}
        configuration["sqlalchemy.url"] = _get_url()

        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()

    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()

