"""Hierarchy integrity enforced by composite foreign keys. Synthetic data only."""

from __future__ import annotations

from helpers import expect_rejected, make_chain, make_unit, make_version, requires_db
from sqlalchemy import text, update

from app.admin_data.hierarchy import ancestors, children, path_codes
from app.admin_data.models import AdminUnit

pytestmark = requires_db


def test_walking_up_and_down_the_chain(session):
    chain = make_chain(session, make_version(session))
    assert [a.code for a in ancestors(session, chain["locality"].id)] == ["00001", "001", "01"]
    assert ancestors(session, chain["state"].id) == []
    assert path_codes(session, chain["locality"].id) == ["01", "001", "00001", "000001"]
    assert [c.code for c in children(session, chain["state"].id)] == ["001"]
    assert children(session, chain["locality"].id) == []


def test_children_are_returned_in_code_order(session):
    v = make_version(session)
    state = make_unit(session, v, "state_ut", "01")
    for code in ("003", "001", "002"):
        make_unit(session, v, "district", code, parent=state)
    assert [c.code for c in children(session, state.id)] == ["001", "002", "003"]


# ---- levels may not be skipped, reversed or mixed -------------------------------------------


def test_a_locality_cannot_hang_directly_off_a_district(session):
    v = make_version(session)
    state = make_unit(session, v, "state_ut", "01")
    district = make_unit(session, v, "district", "001", parent=state)
    with expect_rejected(session, constraint="fk_admin_unit_parent_edge"):
        make_unit(session, v, "locality", "000001", parent=district)


def test_a_subdistrict_cannot_hang_directly_off_a_state(session):
    v = make_version(session)
    state = make_unit(session, v, "state_ut", "01")
    with expect_rejected(session, constraint="fk_admin_unit_parent_edge"):
        make_unit(session, v, "subdistrict", "00001", parent=state)


def test_a_state_cannot_have_a_parent(session):
    v = make_version(session)
    state = make_unit(session, v, "state_ut", "01")
    with expect_rejected(session, constraint="fk_admin_unit_parent_edge"):
        make_unit(session, v, "state_ut", "02", parent=state)


def test_a_parent_cannot_be_a_lower_level_than_its_child(session):
    chain = make_chain(session, make_version(session))
    # try to re-parent the district under its own grandchild
    with expect_rejected(session, constraint="fk_admin_unit_parent_edge"):
        session.execute(
            update(AdminUnit)
            .where(AdminUnit.id == chain["district"].id)
            .values(parent_id=chain["subdistrict"].id, parent_level_key="subdistrict")
        )


def test_cycles_are_impossible_a_unit_cannot_be_its_own_parent(session):
    chain = make_chain(session, make_version(session))
    with expect_rejected(session, constraint="fk_admin_unit_parent_edge"):
        session.execute(
            update(AdminUnit)
            .where(AdminUnit.id == chain["district"].id)
            .values(parent_id=chain["district"].id, parent_level_key="district")
        )


# ---- parents must be real, correctly described and in the same dataset version ---------------


def test_the_parent_must_exist(session):
    v = make_version(session)
    with expect_rejected(session, constraint="fk_admin_unit_parent"):
        session.add(
            AdminUnit(
                dataset_version_id=v.id,
                level_key="district",
                code="001",
                name="Synthetic D",
                parent_id=987654321,
                parent_level_key="state_ut",
            )
        )


def test_a_parent_in_another_dataset_version_is_rejected(session):
    v1, v2 = make_version(session), make_version(session)
    state_in_v1 = make_unit(session, v1, "state_ut", "01")
    with expect_rejected(session, constraint="fk_admin_unit_parent"):
        make_unit(session, v2, "district", "001", parent=state_in_v1)


def test_parent_level_must_match_the_parents_real_level(session):
    v = make_version(session)
    state = make_unit(session, v, "state_ut", "01")
    district = make_unit(session, v, "district", "001", parent=state)
    # (locality -> subdistrict) is an allowed pairing, but this parent is really a DISTRICT.
    # Only the composite parent key can catch the lie.
    with expect_rejected(session, constraint="fk_admin_unit_parent"):
        session.add(
            AdminUnit(
                dataset_version_id=v.id,
                level_key="locality",
                code="000001",
                name="Synthetic Loc",
                parent_id=district.id,
                parent_level_key="subdistrict",
            )
        )


def test_a_parent_with_children_cannot_be_deleted(session):
    chain = make_chain(session, make_version(session))
    with expect_rejected(session, constraint="fk_admin_unit_parent"):
        session.delete(chain["district"])


def test_leaf_units_can_be_deleted_while_the_version_is_still_editable(session):
    chain = make_chain(session, make_version(session))
    session.delete(chain["locality"])
    session.flush()
    assert children(session, chain["subdistrict"].id) == []


def test_every_non_root_unit_has_a_parent_in_the_same_version(session):
    v1, v2 = make_version(session), make_version(session)
    make_chain(session, v1)
    make_chain(session, v2)
    orphans = session.execute(
        text(
            "SELECT count(*) FROM admin_unit c LEFT JOIN admin_unit p "
            "ON p.id = c.parent_id AND p.dataset_version_id = c.dataset_version_id "
            "WHERE c.level_key <> 'state_ut' AND p.id IS NULL"
        )
    ).scalar_one()
    assert orphans == 0
