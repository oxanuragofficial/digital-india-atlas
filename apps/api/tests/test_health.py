from sqlalchemy import create_engine


def test_liveness_ok(make_client):
    response = make_client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "digital-india-atlas-api"
    assert body["version"]


def test_db_health_not_configured(make_client):
    response = make_client(engine=None).get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "not_configured"}


def test_db_health_ok_with_working_engine(make_client, sqlite_engine):
    response = make_client(engine=sqlite_engine).get("/health/db")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "up"


def test_db_health_connection_failure_does_not_leak_credentials(make_client):
    secret = "s3cret-pass-do-not-leak"
    engine = create_engine(
        f"postgresql+psycopg://atlas_user:{secret}@127.0.0.1:1/atlas",
        connect_args={"connect_timeout": 1},
    )
    response = make_client(engine=engine).get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "connection_failed"}
    assert secret not in response.text
    assert "atlas_user" not in response.text
    engine.dispose()


def test_cors_allows_configured_origin_only(make_client):
    client = make_client()
    ok = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
