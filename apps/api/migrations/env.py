"""Alembic environment.

The database URL comes from, in order:
  1. `config.attributes["sqlalchemy_url"]` (used by the test suite to migrate a temporary
     database; never touches the ini file, so passwords with '%' are safe),
  2. the application settings (DATABASE_URL from the environment or the git-ignored .env file).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.admin_data.models  # noqa: F401  (registers the tables on Base.metadata)
from app.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    # Keep the application's own loggers alive (pytest, uvicorn) when migrations run in-process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# PostGIS owns these; they are not part of our models.
POSTGIS_TABLES = {"spatial_ref_sys", "geometry_columns", "geography_columns"}


def get_url() -> str:
    explicit = config.attributes.get("sqlalchemy_url")
    if explicit:
        return str(explicit)
    secret = get_settings().database_url
    if secret is None:
        raise SystemExit(
            "DATABASE_URL is not set. Copy .env.example to .env in the repository root and set "
            "DATABASE_URL (see docs/SETUP_WINDOWS.md)."
        )
    return secret.get_secret_value()


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001
    if type_ == "table" and name in POSTGIS_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic upgrade head --sql`)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
