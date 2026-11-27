"""Fixtures for the administrative-data tests.

Database tests need a PostgreSQL server with PostGIS and a role allowed to create databases (the
Docker Compose `atlas` user qualifies). Point TEST_DATABASE_URL at any database on that server:

    postgresql+psycopg://USER:PASSWORD@localhost:5432/atlas

The suite then creates its OWN temporary database (atlas_test_<random>), runs the real Alembic
migrations into it, and drops it afterwards. Your own data is never read or modified. Without
TEST_DATABASE_URL the database tests are skipped and the pure tests still run.

ALL DATA IN THESE TESTS IS SYNTHETIC. Names such as "Synthetic State A" and the identifier scheme
TEST_SYSTEM exist only to exercise constraints; none of it is, or resembles, real geography.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from helpers import TEST_DATABASE_URL
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

API_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(url: URL) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    # Passed via attributes (not the ini file) so passwords containing '%' are safe.
    config.attributes["sqlalchemy_url"] = url.render_as_string(hide_password=False)
    return config


@contextmanager
def temporary_database() -> Iterator[URL]:
    """Create an empty temporary database on the test server; drop it afterwards."""
    assert TEST_DATABASE_URL
    base = make_url(TEST_DATABASE_URL)
    name = f"atlas_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        try:
            yield base.set(database=name)
        finally:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        admin.dispose()


@pytest.fixture
def blank_database_url() -> Iterator[URL]:
    """A brand-new EMPTY database (no migrations applied). For migration tests."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    with temporary_database() as url:
        yield url


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[URL]:
    """One temporary database, migrated to head with the real Alembic migrations."""
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    with temporary_database() as url:
        command.upgrade(alembic_config(url), "head")
        yield url


@pytest.fixture(scope="session")
def engine(migrated_database_url: URL) -> Iterator[Engine]:
    eng = create_engine(migrated_database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after each test. Constraint failures are tested inside
    SAVEPOINTs (see `expect_rejected`) so the session stays usable afterwards."""
    connection = engine.connect()
    outer = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield db
    finally:
        db.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def fresh_migrated_url(blank_database_url: URL) -> URL:
    """A private, migrated database for tests that COMMIT (CLI and migration tests), so they cannot
    leak data into the shared, rolled-back database used by the other tests."""
    command.upgrade(alembic_config(blank_database_url), "head")
    return blank_database_url
