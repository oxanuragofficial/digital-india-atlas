"""Administrative levels and which level may be the parent of which.

The levels are DATA, stored in the `admin_level` and `admin_level_parent` tables (seeded by the
first migration), so a new level (village, town, ward, ...) is added with a data migration and
needs no table redesign. The constants below mirror that seed so that file validation can run
without a database; a test asserts the two never drift apart.

Rules of the graph:
- `rank` increases as you go down the hierarchy (state_ut = 1).
- A level may only have parents of strictly lower rank, which makes cycles impossible.
- Exactly one level is the root (no parent). It is a schema constant (`ROOT_LEVEL_KEY`) and is
  also written into a CHECK constraint on `admin_unit`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT_LEVEL_KEY = "state_ut"


@dataclass(frozen=True)
class LevelDef:
    key: str
    rank: int
    label: str


DEFAULT_LEVELS: tuple[LevelDef, ...] = (
    LevelDef("state_ut", 1, "State / Union Territory"),
    LevelDef("district", 2, "District"),
    LevelDef("subdistrict", 3, "Subdistrict"),
    LevelDef("locality", 4, "Locality"),
)

# (child level, allowed parent level)
DEFAULT_PARENT_EDGES: tuple[tuple[str, str], ...] = (
    ("district", "state_ut"),
    ("subdistrict", "district"),
    ("locality", "subdistrict"),
)


class LevelGraphError(ValueError):
    pass


class LevelGraph:
    """Immutable description of the level hierarchy."""

    def __init__(self, levels: Iterable[LevelDef], parent_edges: Iterable[tuple[str, str]]) -> None:
        self._levels = {lvl.key: lvl for lvl in levels}
        if ROOT_LEVEL_KEY not in self._levels:
            raise LevelGraphError(f"root level {ROOT_LEVEL_KEY!r} is missing")
        if len({lvl.rank for lvl in self._levels.values()}) != len(self._levels):
            raise LevelGraphError("level ranks must be unique")

        parents: dict[str, set[str]] = {key: set() for key in self._levels}
        for child, parent in parent_edges:
            if child not in self._levels or parent not in self._levels:
                raise LevelGraphError(f"edge {child!r} -> {parent!r} uses an unknown level")
            if self._levels[parent].rank >= self._levels[child].rank:
                raise LevelGraphError(f"parent {parent!r} must rank above child {child!r}")
            parents[child].add(parent)
        for key, allowed in parents.items():
            if key == ROOT_LEVEL_KEY and allowed:
                raise LevelGraphError("the root level cannot have parents")
            if key != ROOT_LEVEL_KEY and not allowed:
                raise LevelGraphError(f"level {key!r} has no allowed parent level")
        self._parents = {key: frozenset(v) for key, v in parents.items()}

    @property
    def level_keys(self) -> frozenset[str]:
        return frozenset(self._levels)

    def has_level(self, key: str) -> bool:
        return key in self._levels

    def rank(self, key: str) -> int:
        return self._levels[key].rank

    def is_root(self, key: str) -> bool:
        return key == ROOT_LEVEL_KEY

    def allowed_parents(self, key: str) -> frozenset[str]:
        return self._parents[key]

    def edges(self) -> frozenset[tuple[str, str]]:
        return frozenset((c, p) for c, ps in self._parents.items() for p in ps)

    def levels_by_rank(self) -> list[LevelDef]:
        return sorted(self._levels.values(), key=lambda lvl: lvl.rank)


DEFAULT_LEVEL_GRAPH = LevelGraph(DEFAULT_LEVELS, DEFAULT_PARENT_EDGES)


def load_level_graph(session: Session) -> LevelGraph:
    """Read the authoritative level graph from the database."""
    from app.admin_data.models import AdminLevel, AdminLevelParent

    levels = [LevelDef(r.level_key, r.rank, r.label) for r in session.scalars(select(AdminLevel))]
    edges = [(r.level_key, r.parent_level_key) for r in session.scalars(select(AdminLevelParent))]
    return LevelGraph(levels, edges)
