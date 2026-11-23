"""FastAPI dependencies."""

from __future__ import annotations

from sqlalchemy import Engine

from app.db.session import get_engine


def get_engine_dep() -> Engine | None:
    """Overridable in tests via `app.dependency_overrides`."""
    return get_engine()
