"""Read helpers for walking the administrative hierarchy within one dataset version."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_data.models import AdminUnit


def children(session: Session, unit_id: int) -> list[AdminUnit]:
    """Direct children of a unit, ordered by code."""
    return list(
        session.scalars(
            select(AdminUnit).where(AdminUnit.parent_id == unit_id).order_by(AdminUnit.code)
        )
    )


def ancestors(session: Session, unit_id: int) -> list[AdminUnit]:
    """The chain of parents from the unit's parent up to the root (nearest first)."""
    chain: list[AdminUnit] = []
    seen: set[int] = {unit_id}
    current = session.get(AdminUnit, unit_id)
    while current is not None and current.parent_id is not None:
        if current.parent_id in seen:  # impossible with the schema's rank rule; defensive only
            raise RuntimeError("cycle detected in administrative hierarchy")
        seen.add(current.parent_id)
        current = session.get(AdminUnit, current.parent_id)
        if current is not None:
            chain.append(current)
    return chain


def path_codes(session: Session, unit_id: int) -> list[str]:
    """Codes from the root down to the unit itself, e.g. for building a breadcrumb."""
    unit = session.get(AdminUnit, unit_id)
    if unit is None:
        return []
    return [a.code for a in reversed(ancestors(session, unit_id))] + [unit.code]
