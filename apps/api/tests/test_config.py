import pytest
from pydantic import ValidationError

from app.config import Settings


def build(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_no_default_database_credentials():
    assert build().database_url is None


def test_database_url_is_masked_in_repr():
    s = build(database_url="postgresql+psycopg://u:topsecret@localhost/db")
    assert "topsecret" not in repr(s)
    assert "topsecret" not in str(s)
    assert s.database_url.get_secret_value().endswith("@localhost/db")


def test_cors_origins_parsed_from_comma_separated_string():
    s = build(cors_allowed_origins="http://a.test, http://b.test ,")
    assert s.cors_origins == ["http://a.test", "http://b.test"]


def test_production_requires_database_url():
    with pytest.raises(ValidationError):
        build(app_env="production")


def test_production_rejects_placeholder_password():
    with pytest.raises(ValidationError):
        build(app_env="production", database_url="postgresql+psycopg://u:CHANGE_ME@h/db")


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError):
        build(
            app_env="production",
            database_url="postgresql+psycopg://u:realpass@h/db",
            cors_allowed_origins="*",
        )


def test_production_accepts_valid_config():
    s = build(
        app_env="production",
        database_url="postgresql+psycopg://u:realpass@h/db",
        cors_allowed_origins="https://atlas.example",
    )
    assert s.app_env == "production"


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_database_url_is_treated_as_unset(blank):
    assert build(database_url=blank).database_url is None


def test_blank_database_url_env_var_yields_no_engine(monkeypatch):
    """Regression: the shipped .env.example leaves DATABASE_URL blank."""
    from app.config import get_settings
    from app.db.session import get_engine

    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        assert get_engine() is None
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()
