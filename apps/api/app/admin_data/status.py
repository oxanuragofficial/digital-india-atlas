"""Publication status of a dataset version, and the only legal ways to change it.

    received -> validated -> under_review -> approved -> published -> superseded
        \\____________\\____________\\____________\\-> rejected   (from any pre-published state)

The same rules are enforced inside PostgreSQL by a trigger on `dataset_version`, so they hold even
for code or people that bypass this module. A test compares this table to the database's actual
behaviour.
"""

from __future__ import annotations

from enum import StrEnum


class PublicationStatus(StrEnum):
    RECEIVED = "received"
    VALIDATED = "validated"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


S = PublicationStatus

ALLOWED_TRANSITIONS: dict[PublicationStatus, frozenset[PublicationStatus]] = {
    S.RECEIVED: frozenset({S.VALIDATED, S.REJECTED}),
    S.VALIDATED: frozenset({S.UNDER_REVIEW, S.REJECTED}),
    S.UNDER_REVIEW: frozenset({S.APPROVED, S.REJECTED}),
    S.APPROVED: frozenset({S.PUBLISHED, S.REJECTED}),
    S.PUBLISHED: frozenset({S.SUPERSEDED}),
    S.REJECTED: frozenset(),
    S.SUPERSEDED: frozenset(),
}

# Units (and geometry) may only be added or changed in these states. From `under_review` onward the
# content is frozen, so what a reviewer saw is exactly what gets published.
EDITABLE_STATUSES = frozenset({S.RECEIVED, S.VALIDATED})

# Units may be deleted in these states (rejected data can be purged).
DELETABLE_STATUSES = frozenset({S.RECEIVED, S.VALIDATED, S.REJECTED})

# Statuses in which a reviewer must be on record.
REVIEWED_STATUSES = frozenset({S.APPROVED, S.PUBLISHED, S.SUPERSEDED})


class InvalidTransition(ValueError):
    def __init__(self, current: PublicationStatus, target: PublicationStatus) -> None:
        super().__init__(f"cannot change status from {current.value!r} to {target.value!r}")
        self.current = current
        self.target = target


def can_transition(current: PublicationStatus, target: PublicationStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def require_transition(current: PublicationStatus, target: PublicationStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(current, target)
