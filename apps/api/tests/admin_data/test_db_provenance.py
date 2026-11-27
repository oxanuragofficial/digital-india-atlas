"""Provenance, licence and import-metadata rules. Synthetic data only."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from helpers import expect_rejected, make_unit, make_version, requires_db
from sqlalchemy import text

from app.admin_data.models import DatasetVersion

pytestmark = requires_db


def test_all_provenance_fields_round_trip(session):
    v = make_version(
        session,
        source_date=date(2019, 12, 31),
        source_url="https://example.test/data",
        license_url="https://example.test/licence",
        attribution_text="Synthetic credit line",
        imported_by="Synthetic Importer",
        validation_summary={"format": "synthetic", "warnings": []},
    )
    session.expire_all()
    got = session.get(DatasetVersion, v.id)
    assert got.publisher == "Synthetic Test Publisher"
    assert got.dataset_name == "Synthetic Dataset"
    assert got.code_system == "TEST_SYSTEM"
    assert got.source_date == date(2019, 12, 31)
    assert got.source_url == "https://example.test/data"
    assert got.license_name == "Synthetic Test Licence"
    assert got.license_url == "https://example.test/licence"
    assert got.attribution_text == "Synthetic credit line"
    assert got.imported_by == "Synthetic Importer"
    assert got.validation_summary == {"format": "synthetic", "warnings": []}
    assert got.status == "received" and got.record_count == 0


def test_import_timestamp_is_recorded_automatically_and_is_timezone_aware(session):
    v = make_version(session)
    session.refresh(v)
    assert v.imported_at.tzinfo is not None
    assert abs(datetime.now(UTC) - v.imported_at) < timedelta(minutes=5)


# ---- licence and required provenance ---------------------------------------------------------


@pytest.mark.parametrize(
    "column", ["publisher", "dataset_name", "version_label", "license_name", "file_name"]
)
def test_required_text_cannot_be_blank(session, column):
    with expect_rejected(session, constraint="ck_dataset_version_text_not_blank"):
        make_version(session, **{column: "   "})


@pytest.mark.parametrize(
    "column",
    [
        "publisher",
        "dataset_name",
        "version_label",
        "license_name",
        "file_name",
        "file_sha256",
        "code_system",
        "source_date",
    ],
)
def test_required_provenance_cannot_be_null(session, column):
    with expect_rejected(session):
        make_version(session, **{column: None})


def test_a_licence_is_mandatory(session):
    with expect_rejected(session, constraint="ck_dataset_version_text_not_blank"):
        make_version(session, license_name="")


@pytest.mark.parametrize("bad", ["test_system", "1TEST", "TEST SYSTEM", "TEST-SYSTEM"])
def test_code_system_format(session, bad):
    with expect_rejected(session, constraint="ck_dataset_version_code_system_format"):
        make_version(session, code_system=bad)


@pytest.mark.parametrize("bad", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_checksum_must_be_64_lowercase_hex_characters(session, bad):
    with expect_rejected(session):
        make_version(session, file_sha256=bad)


def test_record_count_cannot_be_negative(session):
    with expect_rejected(session, constraint="ck_dataset_version_record_count"):
        make_version(session, record_count=-1)


def test_status_must_be_a_known_value(session):
    with expect_rejected(session):
        make_version(session, status="almost_published")


# ---- identity and de-duplication --------------------------------------------------------------


def test_a_version_label_cannot_be_reused_for_the_same_dataset(session):
    make_version(session, version_label="synthetic-reuse")
    with expect_rejected(session, constraint="uq_dataset_version_identity"):
        make_version(session, version_label="synthetic-reuse")


def test_the_same_label_is_fine_for_a_different_dataset_or_publisher(session):
    make_version(session, version_label="synthetic-shared")
    make_version(
        session, version_label="synthetic-shared", dataset_name="Another Synthetic Dataset"
    )
    make_version(session, version_label="synthetic-shared", publisher="Another Synthetic Publisher")


def test_the_same_file_cannot_be_imported_twice_for_a_dataset(session):
    make_version(session, file_sha256="ab" * 32)
    with expect_rejected(session, constraint="uq_dataset_version_file"):
        make_version(session, file_sha256="ab" * 32)


def test_the_same_file_is_allowed_for_a_different_dataset(session):
    make_version(session, file_sha256="cd" * 32)
    make_version(session, file_sha256="cd" * 32, dataset_name="Another Synthetic Dataset")


# ---- units belong to exactly one provenance record ---------------------------------------------


def test_every_unit_traces_back_to_its_dataset_version(session):
    v = make_version(session, license_name="Synthetic Licence X")
    make_unit(session, v, "state_ut", "01")
    row = session.execute(
        text(
            "SELECT d.publisher, d.license_name, d.code_system FROM admin_unit u "
            "JOIN dataset_version d ON d.id = u.dataset_version_id WHERE d.id = :v"
        ),
        {"v": v.id},
    ).one()
    assert row == ("Synthetic Test Publisher", "Synthetic Licence X", "TEST_SYSTEM")


def test_a_unit_cannot_exist_without_a_dataset_version(session):
    with expect_rejected(session):
        session.execute(
            text(
                "INSERT INTO admin_unit (dataset_version_id, level_key, code, name) "
                "VALUES (NULL, 'state_ut', '01', 'Synthetic')"
            )
        )
    with expect_rejected(session):
        session.execute(
            text(
                "INSERT INTO admin_unit (dataset_version_id, level_key, code, name) "
                "VALUES (987654321, 'state_ut', '01', 'Synthetic')"
            )
        )
