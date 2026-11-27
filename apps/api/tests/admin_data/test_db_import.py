"""End-to-end import: CSV file -> validated dataset version -> review -> publication.

Every file and identifier here is SYNTHETIC and exists only inside a throwaway test database.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from helpers import requires_db
from sqlalchemy import func, select, text

from app.admin_data import importer, publishing
from app.admin_data.hierarchy import path_codes
from app.admin_data.importer import (
    AlreadyImported,
    ChecksumMismatch,
    ImportRejected,
    import_units_csv,
)
from app.admin_data.manifest import DatasetManifest
from app.admin_data.models import AdminUnit, DatasetVersion
from app.admin_data.status import InvalidTransition, PublicationStatus
from app.admin_data.validation import CSV_COLUMNS

pytestmark = requires_db
S = PublicationStatus
HEADER = ",".join(CSV_COLUMNS)

GOOD_ROWS = [
    "state_ut,01,Synthetic State A,,",
    "district,001,Synthetic District A1,state_ut,01",
    "district,002,Synthetic District A2,state_ut,01",
    "subdistrict,00001,Synthetic Subdistrict A1a,district,001",
    "locality,000001,Synthetic Locality A1a-i,subdistrict,00001",
    "locality,000002,Synthetic Locality A1a-ii,subdistrict,00001",
]


def write_csv(tmp_path, rows=GOOD_ROWS, name="units.csv"):
    path = tmp_path / name
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return path


def manifest(**overrides) -> DatasetManifest:
    values = {
        "publisher": "Synthetic Test Publisher",
        "dataset_name": "Synthetic Dataset",
        "version_label": "synthetic-import-v1",
        "code_system": "TEST_SYSTEM",
        "source_date": "2020-06-30",
        "source_url": "https://example.test/source",
        "license_name": "Synthetic Test Licence",
        "license_url": "https://example.test/licence",
        "attribution_text": "Synthetic credit line",
    }
    values.update(overrides)
    return DatasetManifest.model_validate(values)


def counts(session) -> tuple[int, int]:
    return (
        session.scalar(select(func.count()).select_from(DatasetVersion)),
        session.scalar(select(func.count()).select_from(AdminUnit)),
    )


def published_count(session) -> int:
    return session.scalar(text("SELECT count(*) FROM published_admin_unit"))


# ---- a successful import --------------------------------------------------------------------------


def test_import_creates_a_validated_dataset_version_with_full_provenance(session, tmp_path):
    path = write_csv(tmp_path)
    result = import_units_csv(session, path, manifest(), imported_by="Synthetic Importer")

    v = session.get(DatasetVersion, result.dataset_version_id)
    assert v.status == "validated" and result.status is S.VALIDATED
    assert (v.publisher, v.dataset_name, v.version_label) == (
        "Synthetic Test Publisher",
        "Synthetic Dataset",
        "synthetic-import-v1",
    )
    assert v.code_system == "TEST_SYSTEM"
    assert str(v.source_date) == "2020-06-30"
    assert v.source_url == "https://example.test/source"
    assert (v.license_name, v.license_url) == (
        "Synthetic Test Licence",
        "https://example.test/licence",
    )
    assert v.attribution_text == "Synthetic credit line"
    assert v.imported_by == "Synthetic Importer"
    assert v.file_name == "units.csv"
    assert v.file_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert v.record_count == 6 == result.record_count
    assert v.validated_at is not None
    assert v.reviewed_by is None and v.published_at is None
    session.refresh(v)
    assert v.imported_at.tzinfo is not None
    assert abs(datetime.now(UTC) - v.imported_at) < timedelta(minutes=5)


def test_import_stores_a_validation_summary(session, tmp_path):
    rows = ['state_ut,01,"  Synthetic   State A ",,', *GOOD_ROWS[1:]]
    result = import_units_csv(session, write_csv(tmp_path, rows), manifest())
    summary = session.get(DatasetVersion, result.dataset_version_id).validation_summary
    assert summary["format"] == "atlas-admin-units-v1"
    assert summary["row_count"] == 6
    assert summary["counts_by_level"] == {
        "state_ut": 1,
        "district": 2,
        "subdistrict": 1,
        "locality": 2,
    }
    assert summary["warning_total"] == 1
    assert summary["warnings"][0]["rule"] == "name.normalized"
    assert result.warning_total == 1


def test_identifiers_keep_their_leading_zeros_end_to_end(session, tmp_path):
    result = import_units_csv(session, write_csv(tmp_path), manifest())
    codes = set(
        session.scalars(
            select(AdminUnit.code).where(AdminUnit.dataset_version_id == result.dataset_version_id)
        )
    )
    assert codes == {"01", "001", "002", "00001", "000001", "000002"}


def test_parent_child_links_are_correct(session, tmp_path):
    result = import_units_csv(session, write_csv(tmp_path), manifest())
    locality = session.scalar(
        select(AdminUnit).where(
            AdminUnit.dataset_version_id == result.dataset_version_id, AdminUnit.code == "000002"
        )
    )
    assert path_codes(session, locality.id) == ["01", "001", "00001", "000002"]
    assert locality.parent_level_key == "subdistrict"


def test_a_child_listed_before_its_parent_still_imports(session, tmp_path):
    result = import_units_csv(session, write_csv(tmp_path, list(reversed(GOOD_ROWS))), manifest())
    assert result.record_count == 6


def test_large_files_are_inserted_in_chunks_with_correct_parents(session, tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "INSERT_CHUNK_SIZE", 7)
    rows = ["state_ut,01,Synthetic State,,"]
    rows += [f"district,{d:03d},Synthetic District {d},state_ut,01" for d in range(1, 6)]
    rows += [
        f"subdistrict,{d:03d}{s:02d},Synthetic Sub {d}-{s},district,{d:03d}"
        for d in range(1, 6)
        for s in range(1, 6)
    ]
    result = import_units_csv(session, write_csv(tmp_path, rows), manifest())
    assert result.record_count == 31
    wrong = session.scalar(
        text(
            "SELECT count(*) FROM admin_unit c JOIN admin_unit p ON p.id = c.parent_id "
            "WHERE c.level_key = 'subdistrict' AND left(c.code, 3) <> p.code "
            "AND c.dataset_version_id = :v"
        ),
        {"v": result.dataset_version_id},
    )
    assert wrong == 0


# ---- importing never publishes -----------------------------------------------------------------------


def test_an_imported_dataset_is_not_published_and_cannot_be_published_directly(session, tmp_path):
    result = import_units_csv(session, write_csv(tmp_path), manifest())
    assert published_count(session) == 0
    with pytest.raises(InvalidTransition):
        publishing.publish(session, result.dataset_version_id)
    assert published_count(session) == 0


def test_full_lifecycle_import_review_approve_publish(session, tmp_path):
    result = import_units_csv(session, write_csv(tmp_path), manifest())
    vid = result.dataset_version_id
    publishing.submit_for_review(session, vid)
    assert published_count(session) == 0
    publishing.approve(session, vid, reviewer="Synthetic Reviewer", note="spot-checked")
    assert published_count(session) == 0
    publishing.publish(session, vid)
    assert published_count(session) == 6
    row = (
        session.execute(text("SELECT * FROM published_admin_unit WHERE code = '000002'"))
        .mappings()
        .one()
    )
    assert row["license_name"] == "Synthetic Test Licence"
    assert row["publisher"] == "Synthetic Test Publisher"


# ---- refusals leave nothing behind ---------------------------------------------------------------------


def test_an_invalid_file_is_rejected_with_a_report_and_writes_nothing(session, tmp_path):
    before = counts(session)
    rows = [
        *GOOD_ROWS,
        "district,003,Synthetic Orphan,state_ut,99",
        "locality,1.0,Synthetic,subdistrict,00001",
    ]
    with pytest.raises(ImportRejected) as caught:
        import_units_csv(session, write_csv(tmp_path, rows), manifest())
    report = caught.value.report
    assert {"parent.not_found", "code.format"} <= {i.rule for i in report.errors}
    assert counts(session) == before


def test_a_checksum_mismatch_is_refused_and_writes_nothing(session, tmp_path):
    before = counts(session)
    with pytest.raises(ChecksumMismatch):
        import_units_csv(session, write_csv(tmp_path), manifest(expected_sha256="0" * 64))
    assert counts(session) == before


def test_a_matching_expected_checksum_is_accepted(session, tmp_path):
    path = write_csv(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert import_units_csv(session, path, manifest(expected_sha256=digest)).record_count == 6


def test_the_same_file_cannot_be_imported_twice(session, tmp_path):
    path = write_csv(tmp_path)
    first = import_units_csv(session, path, manifest())
    before = counts(session)
    with pytest.raises(AlreadyImported) as caught:
        import_units_csv(session, path, manifest(version_label="synthetic-import-v2"))
    assert caught.value.dataset_version_id == first.dataset_version_id
    assert "exact file" in str(caught.value)
    assert counts(session) == before


def test_a_version_label_cannot_be_reused_with_a_different_file(session, tmp_path):
    import_units_csv(session, write_csv(tmp_path), manifest())
    different = write_csv(tmp_path, GOOD_ROWS[:3], name="other.csv")
    with pytest.raises(AlreadyImported, match="version label"):
        import_units_csv(session, different, manifest())


def test_the_same_file_may_be_imported_for_a_different_dataset(session, tmp_path):
    path = write_csv(tmp_path)
    import_units_csv(session, path, manifest())
    other = import_units_csv(session, path, manifest(dataset_name="Another Synthetic Dataset"))
    assert other.record_count == 6


def test_a_failure_part_way_through_rolls_back_the_whole_import(session, tmp_path, monkeypatch):
    before = counts(session)
    real_insert = importer._insert_units

    def insert_then_crash(sess, version_id, units):
        real_insert(sess, version_id, units)
        raise RuntimeError("simulated crash after the units were written")

    monkeypatch.setattr(importer, "_insert_units", insert_then_crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        with session.begin_nested():  # the caller's transaction
            import_units_csv(session, write_csv(tmp_path), manifest())
    assert counts(session) == before


def test_zero_padded_twins_in_a_file_are_rejected_before_anything_is_written(session, tmp_path):
    before = counts(session)
    rows = ["state_ut,7,Synthetic One,,", "state_ut,007,Synthetic Two,,"]
    with pytest.raises(ImportRejected) as caught:
        import_units_csv(session, write_csv(tmp_path, rows), manifest())
    assert "code.zero_padding_ambiguous" in {i.rule for i in caught.value.report.errors}
    assert counts(session) == before


def test_fixed_width_rules_are_enforced_during_import(session, tmp_path):
    rows = ["state_ut,1,Synthetic State,,"]
    with pytest.raises(ImportRejected) as caught:
        import_units_csv(
            session, write_csv(tmp_path, rows), manifest(), code_widths={"state_ut": 2}
        )
    assert "code.width" in {i.rule for i in caught.value.report.errors}


def test_a_missing_file_is_reported_not_silently_ignored(session, tmp_path):
    with pytest.raises(FileNotFoundError):
        import_units_csv(session, tmp_path / "nope.csv", manifest())
