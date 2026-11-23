import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.api.deps import get_engine_dep
from app.config import Settings
from app.main import create_app


def make_settings(**overrides) -> Settings:
    # `_env_file=None` keeps a developer's real .env out of the tests.
    return Settings(_env_file=None, app_env="test", **overrides)


@pytest.fixture
def make_client():
    clients: list[TestClient] = []

    def _make(engine=None) -> TestClient:
        app = create_app(make_settings())
        app.dependency_overrides[get_engine_dep] = lambda: engine
        client = TestClient(app)
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.close()


@pytest.fixture
def sqlite_engine():
    engine = create_engine("sqlite://")
    yield engine
    engine.dispose()
