"""Engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def create_db_engine(url: str) -> Engine:
    """Create an engine. `pool_pre_ping` drops stale connections transparently."""
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def get_engine() -> Engine | None:
    """Return the shared engine, or None when DATABASE_URL is not configured."""
    url = get_settings().database_url
    if url is None:
        return None
    return create_db_engine(url.get_secret_value())


def get_session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
