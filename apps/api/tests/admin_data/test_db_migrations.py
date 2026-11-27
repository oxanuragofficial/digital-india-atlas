"""Alembic migrations: apply from an empty database, seed only schema configuration, reverse
cleanly, and stay in sync with the ORM models."""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from conftest import alembic_config
from helpers import requires_db
from sqlalchemy import create_engine, text

from app.admin_data.levels import (
    DEFAULT_LEVEL_GRAPH,
    DEFAULT_LEVELS,
    DEFAULT_PARENT_EDGES,
    load_level_graph,
)
from app.db.base import Base

pytestmark = requires_db

APP_TABLES = {
    "admin_level",
    "admin_level_parent",
    "dataset_version",
    "admin_unit",
    "admin_unit_geometry",
}
APP_VIEWS = {"published_admin_unit", "published_admin_unit_geometry"}


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.scalar(text(sql))


def names(engine, sql):
    with engine.connect() as conn:
        return {r[0] for r in conn.execute(text(sql))}


def app_tables(engine):
    return names(engine, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'") & APP_TABLES


def app_views(engine):
    return names(engine, "SELECT viewname FROM pg_views WHERE schemaname = 'public'") & APP_VIEWS


def test_there_is_a_single_linear_migration_head(blank_database_url):
    script = ScriptDirectory.from_config(alembic_config(blank_database_url))
    assert len(script.get_heads()) == 1


def test_upgrade_from_empty_creates_everything(blank_database_url):
    command.upgrade(alembic_config(blank_database_url), "head")
    eng = create_engine(blank_database_url)
    try:
        head = ScriptDirectory.from_config(alembic_config(blank_database_url)).get_current_head()
        assert scalar(eng, "SELECT version_num FROM alembic_version") == head
        assert app_tables(eng) == APP_TABLES
        assert app_views(eng) == APP_VIEWS
        assert scalar(eng, "SELECT count(*) FROM pg_extension WHERE extname = 'postgis'") == 1
    finally:
        eng.dispose()


def test_migrations_seed_schema_configuration_but_no_geography(fresh_migrated_url):
    eng = create_engine(fresh_migrated_url)
    try:
        assert scalar(eng, "SELECT count(*) FROM dataset_version") == 0
        assert scalar(eng, "SELECT count(*) FROM admin_unit") == 0
        assert scalar(eng, "SELECT count(*) FROM admin_unit_geometry") == 0
        with eng.connect() as conn:
            levels = conn.execute(
                text("SELECT level_key, rank FROM admin_level ORDER BY rank")
            ).all()
            edges = conn.execute(
                text("SELECT level_key, parent_level_key FROM admin_level_parent")
            ).all()
        assert levels == [(d.key, d.rank) for d in sorted(DEFAULT_LEVELS, key=lambda d: d.rank)]
        assert set(edges) == set(DEFAULT_PARENT_EDGES)
    finally:
        eng.dispose()


def test_level_graph_loaded_from_the_database_matches_the_code_default(fresh_migrated_url):
    from sqlalchemy.orm import Session

    eng = create_engine(fresh_migrated_url)
    try:
        with Session(eng) as db:
            loaded = load_level_graph(db)
        assert loaded.levels_by_rank() == DEFAULT_LEVEL_GRAPH.levels_by_rank()
        assert loaded.edges() == DEFAULT_LEVEL_GRAPH.edges()
    finally:
        eng.dispose()


def test_models_and_migrations_are_in_sync(fresh_migrated_url):
    from app.admin_data import models  # noqa: F401  (registers the tables)

    eng = create_engine(fresh_migrated_url)
    try:
        with eng.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "compare_type": True,
                    "include_object": lambda obj, name, type_, reflected, compare_to: (
                        not (type_ == "table" and name == "spatial_ref_spatial_ref_sys")
                        and not (type_ == "table" and name == "spatial_ref_sys")
                    ),
                },
            )
            diff = compare_metadata(ctx, Base.metadata)
        assert diff == [], f"models differ from migrations: {diff}"
    finally:
        eng.dispose()


def test_downgrade_to_base_removes_everything_and_upgrade_works_again(blank_database_url):
    cfg = alembic_config(blank_database_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    eng = create_engine(blank_database_url)
    try:
        assert app_tables(eng) == set()
        assert app_views(eng) == set()
        guards = names(
            eng,
            "SELECT proname FROM pg_proc WHERE proname IN "
            "('dataset_version_guard','admin_unit_guard','admin_unit_geometry_guard')",
        )
        assert guards == set()
        command.upgrade(cfg, "head")
        assert app_tables(eng) == APP_TABLES
    finally:
        eng.dispose()


def test_each_revision_can_be_applied_and_reversed_step_by_step(blank_database_url):
    cfg = alembic_config(blank_database_url)
    script = ScriptDirectory.from_config(cfg)
    revisions = [r.revision for r in reversed(list(script.walk_revisions()))]
    assert len(revisions) >= 2
    for rev in revisions:
        command.upgrade(cfg, rev)
    for _ in revisions:
        command.downgrade(cfg, "-1")
    eng = create_engine(blank_database_url)
    try:
        assert app_tables(eng) == set()
    finally:
        eng.dispose()


@pytest.mark.parametrize("table", sorted(APP_TABLES))
def test_every_table_has_a_primary_key(fresh_migrated_url, table):
    eng = create_engine(fresh_migrated_url)
    try:
        assert (
            scalar(
                eng,
                f"SELECT count(*) FROM pg_constraint WHERE contype = 'p' "
                f"AND conrelid = 'public.{table}'::regclass",
            )
            == 1
        )
    finally:
        eng.dispose()
