"""Official identifiers are strings; leading zeros must survive storage. Synthetic data only."""

from __future__ import annotations

import pytest
from helpers import expect_rejected, make_unit, make_version, requires_db
from sqlalchemy import select, text

from app.admin_data.models import AdminUnit

pytestmark = requires_db

ZERO_PADDED = ["0", "00", "01", "007", "000123", "0A1", "00000001"]


def test_the_code_column_is_text_not_a_number(session):
    data_type = session.scalar(
        text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'admin_unit' AND column_name = 'code'"
        )
    )
    assert data_type == "character varying"


@pytest.mark.parametrize("code", ZERO_PADDED)
def test_codes_round_trip_exactly(session, code):
    v = make_version(session)
    unit = make_unit(session, v, "state_ut", code)
    session.expire_all()
    stored = session.get(AdminUnit, unit.id).code
    assert stored == code and isinstance(stored, str)


@pytest.mark.parametrize("code", ZERO_PADDED)
def test_codes_survive_a_raw_sql_round_trip(session, code):
    v = make_version(session)
    make_unit(session, v, "state_ut", code)
    stored = session.scalar(
        text("SELECT code FROM admin_unit WHERE dataset_version_id = :v"), {"v": v.id}
    )
    assert stored == code


def test_leading_zeros_survive_at_every_level_of_a_chain(session):
    v = make_version(session)
    s = make_unit(session, v, "state_ut", "01")
    d = make_unit(session, v, "district", "001", parent=s)
    sd = make_unit(session, v, "subdistrict", "00001", parent=d)
    make_unit(session, v, "locality", "000001", parent=sd)
    codes = list(
        session.scalars(
            select(AdminUnit.code)
            .where(AdminUnit.dataset_version_id == v.id)
            .order_by(AdminUnit.id)
        )
    )
    assert codes == ["01", "001", "00001", "000001"]


def test_lookup_by_code_is_exact_so_7_does_not_find_007(session):
    v = make_version(session)
    make_unit(session, v, "state_ut", "007")
    found = session.scalar(
        select(AdminUnit.code).where(AdminUnit.dataset_version_id == v.id, AdminUnit.code == "7")
    )
    assert found is None


def test_codes_sort_as_text_so_zero_padded_codes_keep_their_order(session):
    v = make_version(session)
    for code in ("010", "002", "001"):
        make_unit(session, v, "state_ut", code)
    ordered = list(
        session.scalars(
            select(AdminUnit.code)
            .where(AdminUnit.dataset_version_id == v.id)
            .order_by(AdminUnit.code)
        )
    )
    assert ordered == ["001", "002", "010"]


# ---- the zero-padding twin rule -------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "twin"), [("7", "007"), ("007", "7"), ("0", "00"), ("012", "12")]
)
def test_zero_padded_twins_cannot_coexist_at_one_level(session, first, twin):
    v = make_version(session)
    make_unit(session, v, "state_ut", first)
    with expect_rejected(session, constraint="ux_admin_unit_code_zero_insensitive"):
        make_unit(session, v, "state_ut", twin)


def test_zero_padded_twins_are_fine_at_different_levels(session):
    v = make_version(session)
    s = make_unit(session, v, "state_ut", "7")
    make_unit(session, v, "district", "007", parent=s)


def test_zero_padded_twins_are_fine_in_different_dataset_versions(session):
    make_unit(session, make_version(session), "state_ut", "7")
    make_unit(session, make_version(session), "state_ut", "007")


def test_genuinely_different_codes_are_not_mistaken_for_twins(session):
    v = make_version(session)
    for code in ("1", "10", "100", "01010"):
        make_unit(session, v, "state_ut", code)


def test_codes_are_case_sensitive(session):
    v = make_version(session)
    make_unit(session, v, "state_ut", "a1")
    make_unit(session, v, "state_ut", "A1")
