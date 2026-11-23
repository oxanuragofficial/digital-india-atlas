"""Integration test against a real PostgreSQL + PostGIS instance.

Skipped unless TEST_DATABASE_URL is set, e.g. to the Docker Compose database:
    postgresql+psycopg://USER:PASSWORD@localhost:5432/DBNAME
"""

import os

import pytest
from sqlalchemy import text

from app.api.deps import get_engine_dep
from app.config import Settings
from app.db.session import create_db_engine
from app.main import create_app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL not set (needs PostgreSQL + PostGIS)"
)


@pytest.fixture
def pg_engine():
    engine = create_db_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


def test_postgis_extension_is_available(pg_engine):
    with pg_engine.connect() as conn:
        version = conn.execute(text("SELECT PostGIS_Version()")).scalar_one()
    assert version


def test_postgis_can_compute_a_geometry_operation(pg_engine):
    # Distance between two arbitrary coordinates on the unit grid; no real-world data involved.
    with pg_engine.connect() as conn:
        value = conn.execute(
            text("SELECT ST_Distance(ST_MakePoint(0, 0), ST_MakePoint(3, 4))")
        ).scalar_one()
    assert value == pytest.approx(5.0)


def test_health_db_endpoint_reports_postgis(pg_engine):
    from fastapi.testclient import TestClient

    app = create_app(Settings(_env_file=None, app_env="test"))
    app.dependency_overrides[get_engine_dep] = lambda: pg_engine
    with TestClient(app) as client:
        response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json()["postgis"]
