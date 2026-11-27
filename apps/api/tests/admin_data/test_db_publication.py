"""Publication workflow and 'no unreviewed data' guarantees. Synthetic data only."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from helpers import (
    expect_rejected,
    force_status,
    make_chain,
    make_unit,
    make_version,
    requires_db,
    status_fields,
)
from sqlalchemy import select, text, update

from app.admin_data import publishing
from app.admin_data.models import AdminUnit, DatasetVersion
from app.admin_data.status import (
    ALLOWED_TRANSITIONS,
    InvalidTransition,
    PublicationStatus,
    can_transition,
)

pytestmark = requires_db
S = PublicationStatus


def version_with_units(session, status=S.RECEIVED, **kw):
    v = make_version(session, **kw)
    make_chain(session, v)
    return force_status(session, v, status) if status is not S.RECEIVED else v


def published_codes(session) -> set[tuple[int, str]]:
    return {
        (r.dataset_version_id, r.code)
        for r in session.execute(text("SELECT dataset_version_id, code FROM published_admin_unit"))
    }


# ---- the database agrees with the Python transition table, for every pair ----------------------

ALL_PAIRS = [(a, b) for a in S for b in S if a is not b]


@pytest.mark.parametrize(("current", "target"), ALL_PAIRS, ids=lambda s: s.value)
def test_database_enforces_exactly_the_documented_transitions(session, current, target):
    v = version_with_units(session, current)
    fields = status_fields(target)
    if target in {S.VALIDATED, S.UNDER_REVIEW}:
        fields["record_count"] = 4
    statement = update(DatasetVersion).where(DatasetVersion.id == v.id).values(**fields)

    if can_transition(current, target):
        session.execute(statement)
        session.flush()
        session.refresh(v)
        assert v.status == target.value
    else:
        with expect_rejected(session, message="illegal status change"):
            session.execute(statement)


def test_every_status_pair_was_covered():
    assert len(ALL_PAIRS) == 42
    assert sum(can_transition(a, b) for a, b in ALL_PAIRS) == sum(
        len(v) for v in ALLOWED_TRANSITIONS.values()
    )


def test_a_dataset_version_can_only_be_created_as_received(session):
    for status in S:
        if status is S.RECEIVED:
            continue
        with expect_rejected(session, message="must be created with status received"):
            make_version(session, **status_fields(status))


# ---- the happy path through the service -----------------------------------------------------------


def test_full_workflow_through_the_service(session):
    v = version_with_units(session, S.VALIDATED)
    publishing.submit_for_review(session, v.id)
    assert v.status == "under_review"
    publishing.approve(session, v.id, reviewer="Synthetic Reviewer", note="looks right")
    assert (v.status, v.reviewed_by, v.review_note) == (
        "approved",
        "Synthetic Reviewer",
        "looks right",
    )
    assert v.reviewed_at is not None and v.published_at is None
    publishing.publish(session, v.id)
    assert v.status == "published" and v.published_at is not None


def test_unreviewed_data_cannot_be_published_through_the_service(session):
    for status in (S.VALIDATED, S.UNDER_REVIEW):
        v = version_with_units(session, status)
        with pytest.raises(InvalidTransition):
            publishing.publish(session, v.id)
        session.refresh(v)
        assert v.status == status.value


def test_unreviewed_data_cannot_be_published_by_a_raw_update_either(session):
    v = version_with_units(session, S.VALIDATED)
    with expect_rejected(session, message="illegal status change"):
        session.execute(
            update(DatasetVersion)
            .where(DatasetVersion.id == v.id)
            .values(**status_fields(S.PUBLISHED))
        )


def test_approval_requires_a_named_reviewer(session):
    v = version_with_units(session, S.UNDER_REVIEW)
    for reviewer in (None, "", "   "):
        with pytest.raises(publishing.MissingActor):
            publishing.approve(session, v.id, reviewer=reviewer)
    session.refresh(v)
    assert v.status == "under_review"


def test_approval_without_reviewer_columns_is_rejected_by_the_database(session):
    v = version_with_units(session, S.UNDER_REVIEW)
    with expect_rejected(session, constraint="ck_dataset_version_reviewed_fields"):
        session.execute(
            update(DatasetVersion).where(DatasetVersion.id == v.id).values(status="approved")
        )


def test_rejection_requires_a_reviewer_and_a_reason(session):
    v = version_with_units(session, S.VALIDATED)
    with pytest.raises(publishing.MissingActor):
        publishing.reject(session, v.id, reviewer="Synthetic Reviewer", reason=" ")
    with pytest.raises(publishing.MissingActor):
        publishing.reject(session, v.id, reviewer=None, reason="because")
    publishing.reject(session, v.id, reviewer="Synthetic Reviewer", reason="codes look corrupted")
    assert (v.status, v.review_note) == ("rejected", "codes look corrupted")


def test_a_published_version_cannot_be_rejected_or_reverted(session):
    v = version_with_units(session, S.PUBLISHED)
    with pytest.raises(InvalidTransition):
        publishing.reject(session, v.id, reviewer="Synthetic Reviewer", reason="too late")
    with expect_rejected(session, message="illegal status change"):
        session.execute(
            update(DatasetVersion).where(DatasetVersion.id == v.id).values(status="validated")
        )


def test_unknown_dataset_version_is_reported(session):
    with pytest.raises(publishing.DatasetVersionNotFound):
        publishing.submit_for_review(session, 987654321)


# ---- supersession: at most one published version per dataset --------------------------------------


def test_publishing_a_new_version_supersedes_the_old_one(session):
    old = version_with_units(session, S.PUBLISHED)
    new = version_with_units(session, S.APPROVED)
    publishing.publish(session, new.id)
    session.refresh(old)
    assert (old.status, new.status) == ("superseded", "published")


def test_only_one_version_of_a_dataset_can_be_published_at_once(session):
    version_with_units(session, S.PUBLISHED)
    other = version_with_units(session, S.APPROVED)
    with expect_rejected(session, constraint="ux_dataset_version_one_published"):
        session.execute(
            update(DatasetVersion)
            .where(DatasetVersion.id == other.id)
            .values(**status_fields(S.PUBLISHED))
        )


def test_different_datasets_can_each_have_a_published_version(session):
    version_with_units(session, S.PUBLISHED)
    version_with_units(session, S.PUBLISHED, dataset_name="Another Synthetic Dataset")


# ---- the read model only ever shows published data ------------------------------------------------


def test_unpublished_data_is_invisible_in_the_published_view(session):
    for status in (S.RECEIVED, S.VALIDATED, S.UNDER_REVIEW, S.APPROVED, S.REJECTED):
        version_with_units(session, status)
    assert published_codes(session) == set()


def test_published_data_appears_with_its_provenance(session):
    v = version_with_units(
        session,
        S.PUBLISHED,
        license_url="https://example.test/l",
        attribution_text="Synthetic credit",
    )
    rows = (
        session.execute(
            text("SELECT * FROM published_admin_unit WHERE dataset_version_id = :v ORDER BY id"),
            {"v": v.id},
        )
        .mappings()
        .all()
    )
    assert len(rows) == 4
    first = rows[0]
    assert first["publisher"] == "Synthetic Test Publisher"
    assert first["license_name"] == "Synthetic Test Licence"
    assert first["license_url"] == "https://example.test/l"
    assert first["attribution_text"] == "Synthetic credit"
    assert first["code_system"] == "TEST_SYSTEM"
    assert first["published_at"] is not None
    assert [r["code"] for r in rows] == ["01", "001", "00001", "000001"]


def test_superseded_and_rejected_versions_drop_out_of_the_view(session):
    old = version_with_units(session, S.PUBLISHED)
    assert {vid for vid, _ in published_codes(session)} == {old.id}
    new = version_with_units(session, S.APPROVED)
    publishing.publish(session, new.id)
    assert {vid for vid, _ in published_codes(session)} == {new.id}


def test_nothing_is_published_after_the_importer_style_flow_until_someone_publishes(session):
    v = version_with_units(session, S.VALIDATED)
    assert published_codes(session) == set()
    publishing.submit_for_review(session, v.id)
    publishing.approve(session, v.id, reviewer="Synthetic Reviewer")
    assert published_codes(session) == set()  # approved is still not published
    publishing.publish(session, v.id)
    assert len(published_codes(session)) == 4


# ---- content is frozen once review starts --------------------------------------------------------


@pytest.mark.parametrize("status", [S.RECEIVED, S.VALIDATED])
def test_units_can_be_added_changed_and_removed_before_review(session, status):
    v = version_with_units(session, status)
    state = session.scalar(
        select(AdminUnit).where(AdminUnit.dataset_version_id == v.id, AdminUnit.code == "01")
    )
    extra = make_unit(session, v, "district", "002", parent=state)
    extra.name = "Synthetic Renamed"
    session.flush()
    session.delete(extra)
    session.flush()


@pytest.mark.parametrize("status", [S.UNDER_REVIEW, S.APPROVED, S.PUBLISHED, S.SUPERSEDED])
def test_units_are_frozen_from_review_onward(session, status):
    v = version_with_units(session, status)
    state = session.scalar(
        select(AdminUnit).where(AdminUnit.dataset_version_id == v.id, AdminUnit.code == "01")
    )
    with expect_rejected(session, message="are frozen"):
        make_unit(session, v, "district", "002", parent=state)
    with expect_rejected(session, message="are frozen"):
        state.name = "Synthetic Tampered"
    with expect_rejected(session, message="cannot be deleted"):
        session.execute(text("DELETE FROM admin_unit WHERE dataset_version_id = :v"), {"v": v.id})


def test_rejected_data_may_be_purged_but_not_edited(session):
    v = version_with_units(session, S.REJECTED)
    state = session.scalar(
        select(AdminUnit).where(AdminUnit.dataset_version_id == v.id, AdminUnit.code == "01")
    )
    with expect_rejected(session, message="are frozen"):
        state.name = "Synthetic Edited"
    session.execute(
        text("DELETE FROM admin_unit WHERE dataset_version_id = :v AND level_key = 'locality'"),
        {"v": v.id},
    )
    session.execute(
        text("DELETE FROM admin_unit WHERE dataset_version_id = :v AND level_key = 'subdistrict'"),
        {"v": v.id},
    )
    session.execute(
        text("DELETE FROM admin_unit WHERE dataset_version_id = :v AND level_key = 'district'"),
        {"v": v.id},
    )
    session.execute(text("DELETE FROM admin_unit WHERE dataset_version_id = :v"), {"v": v.id})
    session.execute(text("DELETE FROM dataset_version WHERE id = :v"), {"v": v.id})


@pytest.mark.parametrize("status", [S.UNDER_REVIEW, S.APPROVED, S.PUBLISHED, S.SUPERSEDED])
def test_provenance_is_immutable_from_review_onward(session, status):
    v = version_with_units(session, status)
    for column, value in {
        "license_name": "Synthetic Edited Licence",
        "publisher": "Synthetic Edited Publisher",
        "source_date": datetime(2000, 1, 1, tzinfo=UTC).date(),
        "file_sha256": "ef" * 32,
        "record_count": 99,
        "attribution_text": "edited",
    }.items():
        with expect_rejected(session, message="provenance of a dataset version cannot change"):
            session.execute(
                update(DatasetVersion).where(DatasetVersion.id == v.id).values({column: value})
            )


@pytest.mark.parametrize("status", [S.RECEIVED, S.VALIDATED])
def test_provenance_can_still_be_corrected_before_review(session, status):
    v = version_with_units(session, status)
    session.execute(
        update(DatasetVersion)
        .where(DatasetVersion.id == v.id)
        .values(license_name="Synthetic Corrected")
    )
    session.refresh(v)
    assert v.license_name == "Synthetic Corrected"


def test_review_bookkeeping_can_be_set_without_touching_provenance(session):
    v = version_with_units(session, S.UNDER_REVIEW)
    publishing.approve(session, v.id, reviewer="Synthetic Reviewer")  # does not raise


# ---- integrity checks at the moment review starts -----------------------------------------------


def test_a_dataset_version_with_no_units_cannot_be_validated(session):
    v = make_version(session)
    with expect_rejected(session, message="at least one unit"):
        session.execute(
            update(DatasetVersion)
            .where(DatasetVersion.id == v.id)
            .values(**status_fields(S.VALIDATED))
        )


def test_review_cannot_start_if_the_record_count_does_not_match_the_stored_units(session):
    v = version_with_units(session, S.VALIDATED)
    session.execute(update(DatasetVersion).where(DatasetVersion.id == v.id).values(record_count=3))
    with expect_rejected(session, message="record_count does not match"):
        publishing.submit_for_review(session, v.id)


def test_validated_and_later_statuses_require_a_validation_timestamp(session):
    v = version_with_units(session, S.RECEIVED)
    with expect_rejected(session, constraint="ck_dataset_version_validated_at"):
        session.execute(
            update(DatasetVersion)
            .where(DatasetVersion.id == v.id)
            .values(status="validated", record_count=4)
        )


def test_published_versions_cannot_be_deleted(session):
    v = version_with_units(session, S.PUBLISHED)
    with expect_rejected(session, message="cannot be deleted"):
        session.execute(text("DELETE FROM dataset_version WHERE id = :v"), {"v": v.id})
