"""Database connectivity / PostGIS checks."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError


@dataclass(frozen=True)
class DatabaseStatus:
    ok: bool
    reason: str | None = None  # short, non-sensitive code
    postgis_version: str | None = None


def check_database(engine: Engine) -> DatabaseStatus:
    """Run `SELECT 1`; on PostgreSQL also require the PostGIS extension.

    Error details are intentionally NOT returned (they can contain hostnames or credentials).
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            if engine.dialect.name != "postgresql":
                return DatabaseStatus(ok=True)
            try:
                version = conn.execute(text("SELECT PostGIS_Version()")).scalar_one()
            except SQLAlchemyError:
                return DatabaseStatus(ok=False, reason="postgis_unavailable")
            return DatabaseStatus(ok=True, postgis_version=str(version))
    except SQLAlchemyError:
        return DatabaseStatus(ok=False, reason="connection_failed")
