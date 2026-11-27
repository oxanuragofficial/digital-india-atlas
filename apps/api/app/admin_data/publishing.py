"""Review and publication workflow for dataset versions.

Each function performs exactly one legal status change. The database enforces the same rules with
a trigger, so these functions add clear error messages and bookkeeping (who reviewed, when), not
the only line of defence.

    validated --submit_for_review--> under_review --approve--> approved --publish--> published
    (any state before published) --reject--> rejected

Publishing a new version of a dataset marks the previously published version 'superseded' in the
same transaction. The caller owns the transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.admin_data.models import DatasetVersion
from app.admin_data.status import InvalidTransition, PublicationStatus, require_transition

S = PublicationStatus


class DatasetVersionNotFound(LookupError):
    pass


class MissingActor(ValueError):
    pass


def _lock(session: Session, dataset_version_id: int) -> DatasetVersion:
    version = session.scalar(
        select(DatasetVersion).where(DatasetVersion.id == dataset_version_id).with_for_update()
    )
    if version is None:
        raise DatasetVersionNotFound(f"no dataset version with id {dataset_version_id}")
    return version


def _require_actor(actor: str | None, action: str) -> str:
    if actor is None or not actor.strip():
        raise MissingActor(f"{action} requires the name of the person doing it")
    return actor.strip()


def submit_for_review(session: Session, dataset_version_id: int) -> DatasetVersion:
    """Freeze the content for review. Fails if the stored units do not match the record count."""
    version = _lock(session, dataset_version_id)
    require_transition(S(version.status), S.UNDER_REVIEW)
    version.status = S.UNDER_REVIEW.value
    session.flush()
    return version


def approve(
    session: Session,
    dataset_version_id: int,
    *,
    reviewer: str | None,
    note: str | None = None,
    now: datetime | None = None,
) -> DatasetVersion:
    reviewer = _require_actor(reviewer, "approval")
    version = _lock(session, dataset_version_id)
    require_transition(S(version.status), S.APPROVED)
    version.status = S.APPROVED.value
    version.reviewed_by = reviewer
    version.reviewed_at = now or datetime.now(UTC)
    version.review_note = note
    session.flush()
    return version


def publish(
    session: Session,
    dataset_version_id: int,
    *,
    now: datetime | None = None,
) -> DatasetVersion:
    """Publish an APPROVED version. Anything else is refused: unreviewed data is never published."""
    version = _lock(session, dataset_version_id)
    current = S(version.status)
    if current is not S.APPROVED:
        raise InvalidTransition(current, S.PUBLISHED)
    moment = now or datetime.now(UTC)

    # Supersede first: at most one version per dataset may be published at any time.
    session.execute(
        update(DatasetVersion)
        .where(
            DatasetVersion.publisher == version.publisher,
            DatasetVersion.dataset_name == version.dataset_name,
            DatasetVersion.status == S.PUBLISHED.value,
            DatasetVersion.id != version.id,
        )
        .values(status=S.SUPERSEDED.value)
    )
    session.refresh(version)
    version.status = S.PUBLISHED.value
    version.published_at = moment
    session.flush()
    return version


def reject(
    session: Session,
    dataset_version_id: int,
    *,
    reviewer: str | None,
    reason: str | None,
    now: datetime | None = None,
) -> DatasetVersion:
    reviewer = _require_actor(reviewer, "rejection")
    if reason is None or not reason.strip():
        raise MissingActor("rejection requires a reason")
    version = _lock(session, dataset_version_id)
    require_transition(S(version.status), S.REJECTED)
    version.status = S.REJECTED.value
    version.reviewed_by = reviewer
    version.reviewed_at = now or datetime.now(UTC)
    version.review_note = reason.strip()
    session.flush()
    return version
