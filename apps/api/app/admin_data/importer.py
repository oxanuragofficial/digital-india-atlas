"""Persist a validated administrative-units file as a new dataset version.

Guarantees:
- Nothing is written unless the whole file validates (no partial imports).
- The caller owns the transaction. This function only flushes, so a failure anywhere rolls the
  entire import back.
- The result is ALWAYS left in status 'validated'. Importing never publishes: review, approval
  and publication are separate, explicit steps (`publishing.py`).
- The same file cannot be imported twice for a dataset (checksum), and a version label cannot be
  reused.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.admin_data.levels import load_level_graph
from app.admin_data.manifest import DatasetManifest
from app.admin_data.models import AdminUnit, DatasetVersion
from app.admin_data.status import PublicationStatus
from app.admin_data.validation import (
    FORMAT_NAME,
    ParsedUnit,
    ValidationReport,
    group_by_level,
    validate_units_csv,
)

INSERT_CHUNK_SIZE = 5000
MAX_STORED_WARNINGS = 100


class ImportRefused(Exception):
    """Base class for import refusals (a refusal is expected behaviour, not a crash)."""


class ImportRejected(ImportRefused):
    """The file failed validation. `report` lists every problem; nothing was written."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__(f"file rejected: {report.error_total} error(s)")
        self.report = report


class ChecksumMismatch(ImportRefused):
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            f"file checksum {actual} does not match the manifest's expected_sha256 {expected}"
        )


class AlreadyImported(ImportRefused):
    def __init__(self, dataset_version_id: int, reason: str) -> None:
        super().__init__(f"{reason} (existing dataset version id {dataset_version_id})")
        self.dataset_version_id = dataset_version_id


@dataclass(frozen=True)
class ImportResult:
    dataset_version_id: int
    record_count: int
    counts_by_level: dict[str, int]
    warning_total: int
    status: PublicationStatus


def sha256_of_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def import_units_csv(
    session: Session,
    csv_path: str | Path,
    manifest: DatasetManifest,
    *,
    imported_by: str | None = None,
    code_widths: dict[str, int] | None = None,
    now: datetime | None = None,
) -> ImportResult:
    path = Path(csv_path)
    checksum = sha256_of_file(path)
    if manifest.expected_sha256 and manifest.expected_sha256 != checksum:
        raise ChecksumMismatch(manifest.expected_sha256, checksum)

    # Validate against the level graph stored in the database (the authority), not the constant.
    graph = load_level_graph(session)
    report, units = validate_units_csv(path, graph, code_widths=code_widths)
    if not report.ok:
        raise ImportRejected(report)

    _refuse_duplicates(session, manifest, checksum)

    version = DatasetVersion(
        publisher=manifest.publisher,
        dataset_name=manifest.dataset_name,
        version_label=manifest.version_label,
        code_system=manifest.code_system,
        source_date=manifest.source_date,
        source_url=manifest.source_url,
        license_name=manifest.license_name,
        license_url=manifest.license_url,
        attribution_text=manifest.attribution_text,
        file_name=path.name,
        file_sha256=checksum,
        imported_by=imported_by,
        status=PublicationStatus.RECEIVED.value,
    )
    session.add(version)
    session.flush()

    _insert_units(session, version.id, units)

    version.record_count = len(units)
    version.validation_summary = {
        "format": FORMAT_NAME,
        "row_count": report.row_count,
        "counts_by_level": dict(report.counts_by_level),
        "warning_total": report.warning_total,
        "warnings": [w.to_dict() for w in report.warnings[:MAX_STORED_WARNINGS]],
    }
    version.status = PublicationStatus.VALIDATED.value
    version.validated_at = now or datetime.now(UTC)
    session.flush()

    return ImportResult(
        dataset_version_id=version.id,
        record_count=len(units),
        counts_by_level=dict(report.counts_by_level),
        warning_total=report.warning_total,
        status=PublicationStatus.VALIDATED,
    )


def _refuse_duplicates(session: Session, manifest: DatasetManifest, checksum: str) -> None:
    same_file = session.scalar(
        select(DatasetVersion.id).where(
            DatasetVersion.publisher == manifest.publisher,
            DatasetVersion.dataset_name == manifest.dataset_name,
            DatasetVersion.file_sha256 == checksum,
        )
    )
    if same_file is not None:
        raise AlreadyImported(same_file, "this exact file was already imported for this dataset")
    same_label = session.scalar(
        select(DatasetVersion.id).where(
            DatasetVersion.publisher == manifest.publisher,
            DatasetVersion.dataset_name == manifest.dataset_name,
            DatasetVersion.version_label == manifest.version_label,
        )
    )
    if same_label is not None:
        raise AlreadyImported(same_label, "this version label already exists for this dataset")


def _insert_units(session: Session, version_id: int, units: list[ParsedUnit]) -> None:
    """Insert level by level (parents first) so parent ids are known when children are inserted."""
    ids: dict[tuple[str, str], int] = {}
    grouped = group_by_level(units)  # `units` is already ordered by level rank
    for level in dict.fromkeys(u.level for u in units):
        rows = grouped[level]
        for start in range(0, len(rows), INSERT_CHUNK_SIZE):
            chunk = rows[start : start + INSERT_CHUNK_SIZE]
            values = [
                {
                    "dataset_version_id": version_id,
                    "level_key": u.level,
                    "code": u.code,
                    "name": u.name,
                    "parent_id": ids[(u.parent_level, u.parent_code)] if u.parent_level else None,
                    "parent_level_key": u.parent_level,
                }
                for u in chunk
            ]
            result = session.execute(
                insert(AdminUnit).returning(AdminUnit.id, AdminUnit.code), values
            )
            for unit_id, code in result:
                ids[(level, code)] = unit_id
