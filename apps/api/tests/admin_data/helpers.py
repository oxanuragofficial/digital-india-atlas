"""Builders for SYNTHETIC test data. Nothing here is real geography or a real identifier scheme."""

from __future__ import annotations

import hashlib
import itertools
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.admin_data.models import AdminUnit, DatasetVersion
from app.admin_data.status import ALLOWED_TRANSITIONS, PublicationStatus

S = PublicationStatus
CODE_SYSTEM = "TEST_SYSTEM"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_db = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL not set (needs PostgreSQL + PostGIS and CREATEDB rights)",
)


@contextmanager
def expect_rejected(
    session: Session, *, constraint: str | None = None, message: str | None = None
) -> Iterator[None]:
    """Assert that the database refuses whatever happens inside the block.

    The block runs in a SAVEPOINT that is rolled back, so the session remains usable. Pass
    `constraint` to require that a specific named constraint/index was the reason, or `message` to
    require text in the database's error (used for trigger-raised errors).
    """
    with pytest.raises(DBAPIError) as caught:
        with session.begin_nested():
            yield
            session.flush()
    original = caught.value.orig
    if constraint is not None:
        actual = getattr(getattr(original, "diag", None), "constraint_name", None)
        assert actual == constraint, f"rejected by {actual!r}, expected {constraint!r}: {original}"
    if message is not None:
        assert message in str(original), f"{message!r} not in {original}"


_counter = itertools.count(1)


def make_version(session: Session, **overrides: Any) -> DatasetVersion:
    """A dataset version in status 'received' with synthetic provenance."""
    n = next(_counter)
    values: dict[str, Any] = {
        "publisher": "Synthetic Test Publisher",
        "dataset_name": "Synthetic Dataset",
        "version_label": f"synthetic-v{n}",
        "code_system": CODE_SYSTEM,
        "source_date": date(2020, 1, 1),
        "license_name": "Synthetic Test Licence",
        "file_name": f"synthetic-{n}.csv",
        "file_sha256": hashlib.sha256(f"synthetic-{n}".encode()).hexdigest(),
        "status": S.RECEIVED.value,
    }
    values.update(overrides)
    version = DatasetVersion(**values)
    session.add(version)
    session.flush()
    return version


def make_unit(
    session: Session,
    version: DatasetVersion,
    level: str,
    code: str,
    name: str | None = None,
    parent: AdminUnit | None = None,
) -> AdminUnit:
    unit = AdminUnit(
        dataset_version_id=version.id,
        level_key=level,
        code=code,
        name=name if name is not None else f"Synthetic {level} {code}",
        parent_id=parent.id if parent else None,
        parent_level_key=parent.level_key if parent else None,
    )
    session.add(unit)
    session.flush()
    return unit


def make_chain(session: Session, version: DatasetVersion) -> dict[str, AdminUnit]:
    """state_ut > district > subdistrict > locality, with leading-zero codes."""
    state = make_unit(session, version, "state_ut", "01", "Synthetic State A")
    district = make_unit(session, version, "district", "001", "Synthetic District A1", state)
    sub = make_unit(session, version, "subdistrict", "00001", "Synthetic Subdistrict A1a", district)
    loc = make_unit(session, version, "locality", "000001", "Synthetic Locality A1a-i", sub)
    return {"state": state, "district": district, "subdistrict": sub, "locality": loc}


def status_fields(target: PublicationStatus, now: datetime | None = None) -> dict[str, Any]:
    """Columns the CHECK constraints require for a given status."""
    now = now or datetime.now(UTC)
    fields: dict[str, Any] = {"status": target.value}
    if target in {S.VALIDATED, S.UNDER_REVIEW, S.APPROVED, S.PUBLISHED, S.SUPERSEDED}:
        fields["validated_at"] = now
    if target in {S.APPROVED, S.PUBLISHED, S.SUPERSEDED, S.REJECTED}:
        fields["reviewed_by"] = "Synthetic Reviewer"
        fields["reviewed_at"] = now
    if target in {S.PUBLISHED, S.SUPERSEDED}:
        fields["published_at"] = now
    return fields


def _path_to(target: PublicationStatus) -> list[PublicationStatus]:
    """Shortest legal path from 'received' to target."""
    queue: list[list[PublicationStatus]] = [[S.RECEIVED]]
    while queue:
        path = queue.pop(0)
        if path[-1] is target:
            return path[1:]
        for nxt in sorted(ALLOWED_TRANSITIONS[path[-1]], key=lambda s: s.value):
            if nxt not in path:
                queue.append([*path, nxt])
    raise AssertionError(f"no path to {target}")


def force_status(
    session: Session, version: DatasetVersion, target: PublicationStatus
) -> DatasetVersion:
    """Move a version to `target` through LEGAL transitions using direct updates (not the
    publishing service), setting the bookkeeping columns the CHECK constraints demand."""
    count = session.scalar(
        select(func.count())
        .select_from(AdminUnit)
        .where(AdminUnit.dataset_version_id == version.id)
    )
    for step in _path_to(target):
        values = status_fields(step)
        if step in {S.VALIDATED, S.UNDER_REVIEW}:
            values["record_count"] = count
        session.execute(
            update(DatasetVersion).where(DatasetVersion.id == version.id).values(**values)
        )
        session.flush()
    session.refresh(version)
    return version
