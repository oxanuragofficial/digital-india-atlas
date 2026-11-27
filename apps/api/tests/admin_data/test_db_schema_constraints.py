"""Schema constraints, enforced by PostgreSQL itself. Synthetic data only."""

from __future__ import annotations

import pytest
from helpers import expect_rejected, make_chain, make_unit, make_version, requires_db
from sqlalchemy import select, text

from app.admin_data.models import AdminLevel, AdminLevelParent, AdminUnit

pytestmark = requires_db


def test_level_definitions_are_seeded_and_nothing_else(session):
    levels = {r.level_key: r.rank for r in session.scalars(select(AdminLevel))}
    assert levels == {"state_ut": 1, "district": 2, "subdistrict": 3, "locality": 4}
    edges = {(r.level_key, r.parent_level_key) for r in session.scalars(select(AdminLevelParent))}
    assert edges == {
        ("district", "state_ut"),
        ("subdistrict", "district"),
        ("locality", "subdistrict"),
    }


def test_the_migrated_database_contains_no_geography(session):
    assert session.scalar(text("SELECT count(*) FROM admin_unit")) == 0
    assert session.scalar(text("SELECT count(*) FROM dataset_version")) == 0
    assert session.scalar(text("SELECT count(*) FROM admin_unit_geometry")) == 0


# ---- uniqueness -----------------------------------------------------------------------------


def test_code_is_unique_per_dataset_version_and_level(session):
    v = make_version(session)
    make_unit(session, v, "state_ut", "01")
    with expect_rejected(session, constraint="uq_admin_unit_code"):
        make_unit(session, v, "state_ut", "01", "Synthetic Duplicate")


def test_same_code_is_allowed_at_another_level_and_in_another_version(session):
    v1, v2 = make_version(session), make_version(session)
    state = make_unit(session, v1, "state_ut", "01")
    make_unit(session, v1, "district", "01", parent=state)  # other level
    make_unit(session, v2, "state_ut", "01")  # other version


def test_names_may_repeat_because_real_names_do(session):
    v = make_version(session)
    state = make_unit(session, v, "state_ut", "01")
    make_unit(session, v, "district", "001", "Synthetic Same Name", state)
    make_unit(session, v, "district", "002", "Synthetic Same Name", state)


# ---- value rules ----------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["", " 01", "01 ", "1.0", "1,5", "a b", "-1", "é1", "1" * 33])
def test_code_format_is_enforced(session, code):
    v = make_version(session)
    with expect_rejected(session):
        make_unit(session, v, "state_ut", code)


@pytest.mark.parametrize("name", ["", "   ", " leading", "trailing "])
def test_name_must_be_non_blank_and_trimmed(session, name):
    v = make_version(session)
    with expect_rejected(session, constraint="ck_admin_unit_name_trimmed"):
        make_unit(session, v, "state_ut", "01", name)


def test_unknown_level_is_rejected(session):
    v = make_version(session)
    state = make_unit(session, v, "state_ut", "01")
    with expect_rejected(session):  # several constraints refuse it; any of them is fine
        make_unit(session, v, "planet", "01", parent=state)


# ---- root and parent shape ------------------------------------------------------------------


def test_only_the_root_level_may_be_parentless(session):
    v = make_version(session)
    with expect_rejected(session, constraint="ck_admin_unit_root_level"):
        make_unit(session, v, "district", "001")


def test_parent_id_and_parent_level_must_be_set_together(session):
    v = make_version(session)
    state = make_unit(session, v, "state_ut", "01")
    with expect_rejected(session, constraint="ck_admin_unit_parent_pair"):
        session.add(
            AdminUnit(
                dataset_version_id=v.id,
                level_key="district",
                code="001",
                name="Synthetic D",
                parent_id=state.id,
                parent_level_key=None,
            )
        )
    with expect_rejected(session, constraint="ck_admin_unit_parent_pair"):
        session.add(
            AdminUnit(
                dataset_version_id=v.id,
                level_key="district",
                code="002",
                name="Synthetic D2",
                parent_id=None,
                parent_level_key="state_ut",
            )
        )


def test_a_dataset_version_with_units_cannot_be_deleted_out_from_under_them(session):
    v = make_version(session)
    make_unit(session, v, "state_ut", "01")
    with expect_rejected(session, constraint="fk_admin_unit_dataset_version"):
        session.delete(v)


def test_a_unit_cannot_be_moved_to_another_dataset_version(session):
    v1, v2 = make_version(session), make_version(session)
    unit = make_unit(session, v1, "state_ut", "01")
    with expect_rejected(session, message="cannot move to another dataset version"):
        unit.dataset_version_id = v2.id


def test_constraints_exist_under_their_documented_names(session):
    names = set(
        session.scalars(
            text(
                "SELECT conname FROM pg_constraint WHERE conrelid IN "
                "('admin_unit'::regclass, 'dataset_version'::regclass)"
            )
        )
    )
    assert {
        "uq_admin_unit_code",
        "fk_admin_unit_parent",
        "fk_admin_unit_parent_edge",
        "ck_admin_unit_root_level",
        "ck_admin_unit_code_format",
        "uq_dataset_version_identity",
        "uq_dataset_version_file",
        "ck_dataset_version_status",
    } <= names


def test_indexes_exist_for_lookups(session):
    indexes = set(
        session.scalars(text("SELECT indexname FROM pg_indexes WHERE tablename = 'admin_unit'"))
    )
    assert {
        "ix_admin_unit_parent",
        "ix_admin_unit_level_code",
        "ux_admin_unit_code_zero_insensitive",
    } <= indexes


def test_a_full_chain_can_be_stored(session):
    v = make_version(session)
    chain = make_chain(session, v)
    assert [u.level_key for u in chain.values()] == [
        "state_ut",
        "district",
        "subdistrict",
        "locality",
    ]
