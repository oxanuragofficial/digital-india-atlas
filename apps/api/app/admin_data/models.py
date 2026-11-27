"""ORM models for administrative geography and its provenance.

Design summary (details and rationale: docs/ADMIN_DATA_MODEL.md):

- `admin_level` / `admin_level_parent`   which levels exist and which level may parent which.
- `dataset_version`                      one imported dataset: provenance, licence, checksum,
                                         publication status. Everything below belongs to one.
- `admin_unit`                           one row per administrative unit per dataset version, in a
                                         single self-referencing table (adjacency list).
- `admin_unit_geometry`                  optional PostGIS geometry, 1:1 with a unit.

Identifiers are TEXT, never integers, so leading zeros survive. Constraints are declared here AND
written out in the Alembic migrations; a test fails if the two drift apart. A few rules (status
transitions, freezing reviewed data) are enforced by triggers that exist only in the migrations.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.admin_data.levels import ROOT_LEVEL_KEY
from app.admin_data.status import PublicationStatus
from app.db.base import Base

S = PublicationStatus

# Geometry conventions (documented in docs/ADMIN_DATA_MODEL.md).
GEOMETRY_SRID = 4326  # WGS 84, longitude/latitude in degrees
BOUNDARY_GEOMETRY_TYPE = "MULTIPOLYGON"
POINT_GEOMETRY_TYPE = "POINT"

# Identifier / text rules shared with the import validator.
CODE_REGEX = r"^[A-Za-z0-9]+$"
CODE_MAX_LENGTH = 32
CODE_SYSTEM_REGEX = r"^[A-Z][A-Z0-9_]*$"
LEVEL_KEY_REGEX = r"^[a-z][a-z0-9_]*$"

_STATUS_LIST = ", ".join(f"'{s.value}'" for s in PublicationStatus)
_REVIEWED_LIST = ", ".join(f"'{s.value}'" for s in (S.APPROVED, S.PUBLISHED, S.SUPERSEDED))
_PUBLISHED_LIST = ", ".join(f"'{s.value}'" for s in (S.PUBLISHED, S.SUPERSEDED))
_VALIDATED_LIST = ", ".join(
    f"'{s.value}'" for s in (S.VALIDATED, S.UNDER_REVIEW, S.APPROVED, S.PUBLISHED, S.SUPERSEDED)
)


class AdminLevel(Base):
    """A level of the hierarchy (state_ut, district, subdistrict, locality, ...)."""

    __tablename__ = "admin_level"

    level_key: Mapped[str] = mapped_column(String(32))
    rank: Mapped[int] = mapped_column(SmallInteger)
    label: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        PrimaryKeyConstraint("level_key", name="pk_admin_level"),
        UniqueConstraint("rank", name="uq_admin_level_rank"),
        # Target for the composite foreign keys on admin_level_parent.
        UniqueConstraint("level_key", "rank", name="uq_admin_level_key_rank"),
        CheckConstraint(f"level_key ~ '{LEVEL_KEY_REGEX}'", name="key_format"),
        CheckConstraint("rank > 0", name="rank_positive"),
    )


class AdminLevelParent(Base):
    """An allowed (child level -> parent level) edge. Parents must rank strictly above children,
    which makes cycles impossible."""

    __tablename__ = "admin_level_parent"

    level_key: Mapped[str] = mapped_column(String(32))
    level_rank: Mapped[int] = mapped_column(SmallInteger)
    parent_level_key: Mapped[str] = mapped_column(String(32))
    parent_rank: Mapped[int] = mapped_column(SmallInteger)

    __table_args__ = (
        PrimaryKeyConstraint("level_key", "parent_level_key", name="pk_admin_level_parent"),
        ForeignKeyConstraint(
            ["level_key", "level_rank"],
            ["admin_level.level_key", "admin_level.rank"],
            name="fk_admin_level_parent_level",
        ),
        ForeignKeyConstraint(
            ["parent_level_key", "parent_rank"],
            ["admin_level.level_key", "admin_level.rank"],
            name="fk_admin_level_parent_parent",
        ),
        CheckConstraint("parent_rank < level_rank", name="rank_order"),
    )


class DatasetVersion(Base):
    """One imported dataset: where it came from, under what licence, and whether it is published.

    Rows are only ever created with status 'received'. Status changes follow
    `app.admin_data.status.ALLOWED_TRANSITIONS`, enforced by a database trigger.
    """

    __tablename__ = "dataset_version"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False))

    # Provenance: who published it, what it is, which version, and the identifier scheme it uses.
    publisher: Mapped[str] = mapped_column(Text)
    dataset_name: Mapped[str] = mapped_column(Text)
    version_label: Mapped[str] = mapped_column(Text)
    code_system: Mapped[str] = mapped_column(String(32))  # e.g. an official scheme name
    # As-of / publication date stated by the source.
    source_date: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(Text)

    # Licence information. The name is mandatory: no licence, no import.
    license_name: Mapped[str] = mapped_column(Text)
    license_url: Mapped[str | None] = mapped_column(Text)
    attribution_text: Mapped[str | None] = mapped_column(Text)

    # Integrity of the file that was imported.
    file_name: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(String(64))
    record_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    validation_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    imported_by: Mapped[str | None] = mapped_column(Text)

    # Publication workflow.
    status: Mapped[str] = mapped_column(String(16), server_default=text("'received'"))
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_dataset_version"),
        UniqueConstraint(
            "publisher", "dataset_name", "version_label", name="uq_dataset_version_identity"
        ),
        # The same file cannot be imported twice for the same dataset.
        UniqueConstraint(
            "publisher", "dataset_name", "file_sha256", name="uq_dataset_version_file"
        ),
        CheckConstraint(f"status IN ({_STATUS_LIST})", name="status"),
        CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        CheckConstraint(f"code_system ~ '{CODE_SYSTEM_REGEX}'", name="code_system_format"),
        CheckConstraint(
            "btrim(publisher) <> '' AND btrim(dataset_name) <> '' AND btrim(version_label) <> ''"
            " AND btrim(license_name) <> '' AND btrim(file_name) <> ''",
            name="text_not_blank",
        ),
        CheckConstraint("record_count >= 0", name="record_count"),
        CheckConstraint(
            f"status NOT IN ({_VALIDATED_LIST}) OR validated_at IS NOT NULL", name="validated_at"
        ),
        CheckConstraint(
            f"status NOT IN ({_REVIEWED_LIST}) OR (reviewed_by IS NOT NULL"
            " AND btrim(reviewed_by) <> '' AND reviewed_at IS NOT NULL)",
            name="reviewed_fields",
        ),
        CheckConstraint(
            f"status NOT IN ({_PUBLISHED_LIST}) OR published_at IS NOT NULL", name="published_at"
        ),
        # At most one published version per dataset; publishing a new one supersedes the old one.
        Index(
            "ux_dataset_version_one_published",
            "publisher",
            "dataset_name",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        Index("ix_dataset_version_status", "status"),
    )


class AdminUnit(Base):
    """One administrative unit within one dataset version.

    `code` is the official identifier as a string (leading zeros preserved), unique per
    (dataset version, level). Its identifier scheme is `dataset_version.code_system`.

    Hierarchy is enforced by the database through two composite foreign keys:
      * (dataset_version_id, parent_id, parent_level_key) -> admin_unit(dataset_version_id, id,
        level_key): the parent exists, is in the SAME dataset version, and really has the level
        recorded in `parent_level_key`;
      * (level_key, parent_level_key) -> admin_level_parent: that level pairing is allowed.
    Root units (level 'state_ut') have no parent; every other level must have one.
    """

    __tablename__ = "admin_unit"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    dataset_version_id: Mapped[int] = mapped_column(BigInteger)
    level_key: Mapped[str] = mapped_column(String(32))
    code: Mapped[str] = mapped_column(String(CODE_MAX_LENGTH))
    name: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(BigInteger)
    parent_level_key: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_admin_unit"),
        ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_version.id"],
            name="fk_admin_unit_dataset_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["level_key"], ["admin_level.level_key"], name="fk_admin_unit_level"),
        ForeignKeyConstraint(
            ["level_key", "parent_level_key"],
            ["admin_level_parent.level_key", "admin_level_parent.parent_level_key"],
            name="fk_admin_unit_parent_edge",
        ),
        ForeignKeyConstraint(
            ["dataset_version_id", "parent_id", "parent_level_key"],
            ["admin_unit.dataset_version_id", "admin_unit.id", "admin_unit.level_key"],
            name="fk_admin_unit_parent",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("dataset_version_id", "level_key", "code", name="uq_admin_unit_code"),
        # Target of the composite parent foreign key.
        UniqueConstraint(
            "dataset_version_id", "id", "level_key", name="uq_admin_unit_version_id_level"
        ),
        # '7' and '007' must never coexist at one level: that is how zero-stripping corrupts data.
        Index(
            "ux_admin_unit_code_zero_insensitive",
            "dataset_version_id",
            "level_key",
            text("(COALESCE(NULLIF(ltrim(code, '0'), ''), '0'))"),
            unique=True,
        ),
        CheckConstraint(f"code ~ '{CODE_REGEX}'", name="code_format"),
        CheckConstraint("btrim(name) = name AND name <> ''", name="name_trimmed"),
        CheckConstraint("(parent_id IS NULL) = (parent_level_key IS NULL)", name="parent_pair"),
        CheckConstraint(
            f"parent_id IS NOT NULL OR level_key = '{ROOT_LEVEL_KEY}'", name="root_level"
        ),
        Index("ix_admin_unit_parent", "dataset_version_id", "parent_id"),
        Index("ix_admin_unit_level_code", "level_key", "code"),
    )


class AdminUnitGeometry(Base):
    """Optional geometry for a unit. Kept out of `admin_unit` so large polygons do not bloat the
    hierarchy table.

    Coordinate reference system: EPSG:4326 (WGS 84), longitude/latitude in degrees, axis order
    x = longitude, y = latitude.
    - `boundary`: MultiPolygon, so one column type fits units made of several parts. A single
      Polygon is accepted and PostGIS promotes it to a MultiPolygon on insert, so the stored
      type is always MultiPolygon. Points, lines and other types are refused.
    - `representative_point`: Point, for units without a published boundary (typically
      localities). It is a display anchor, NOT an official coordinate.
    At least one of the two must be present. Geometries must be valid, non-empty and within
    lon/lat bounds.
    """

    __tablename__ = "admin_unit_geometry"

    unit_id: Mapped[int] = mapped_column(BigInteger)
    boundary: Mapped[Any | None] = mapped_column(
        Geometry(BOUNDARY_GEOMETRY_TYPE, srid=GEOMETRY_SRID, spatial_index=False)
    )
    representative_point: Mapped[Any | None] = mapped_column(
        Geometry(POINT_GEOMETRY_TYPE, srid=GEOMETRY_SRID, spatial_index=False)
    )

    __table_args__ = (
        PrimaryKeyConstraint("unit_id", name="pk_admin_unit_geometry"),
        ForeignKeyConstraint(
            ["unit_id"],
            ["admin_unit.id"],
            name="fk_admin_unit_geometry_unit",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "boundary IS NOT NULL OR representative_point IS NOT NULL", name="not_empty"
        ),
        CheckConstraint(
            "boundary IS NULL OR (ST_IsValid(boundary) AND NOT ST_IsEmpty(boundary)"
            " AND ST_XMin(boundary) >= -180 AND ST_XMax(boundary) <= 180"
            " AND ST_YMin(boundary) >= -90 AND ST_YMax(boundary) <= 90)",
            name="boundary_valid",
        ),
        CheckConstraint(
            "representative_point IS NULL OR (NOT ST_IsEmpty(representative_point)"
            " AND ST_X(representative_point) BETWEEN -180 AND 180"
            " AND ST_Y(representative_point) BETWEEN -90 AND 90)",
            name="point_valid",
        ),
        Index("gix_admin_unit_geometry_boundary", "boundary", postgresql_using="gist"),
        Index("gix_admin_unit_geometry_point", "representative_point", postgresql_using="gist"),
    )
