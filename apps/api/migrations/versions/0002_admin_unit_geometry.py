"""Optional geometry for administrative units.

Coordinate reference system: EPSG:4326 (WGS 84), longitude/latitude in degrees.
  - boundary:             geometry(MultiPolygon, 4326)
  - representative_point: geometry(Point, 4326)

Adds no geometry rows. Geometry is frozen together with its unit once review starts.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GEOMETRY_GUARD = """
CREATE FUNCTION admin_unit_geometry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_unit_id bigint;
  v_status text;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.unit_id IS DISTINCT FROM OLD.unit_id THEN
    RAISE EXCEPTION 'geometry cannot be moved to another administrative unit'
      USING ERRCODE = 'check_violation';
  END IF;

  IF TG_OP = 'DELETE' THEN
    v_unit_id := OLD.unit_id;
  ELSE
    v_unit_id := NEW.unit_id;
  END IF;

  SELECT v.status INTO v_status
  FROM admin_unit AS u
  JOIN dataset_version AS v ON v.id = u.dataset_version_id
  WHERE u.id = v_unit_id;

  IF v_status IS NOT NULL THEN
    IF TG_OP = 'DELETE' THEN
      IF v_status NOT IN ('received', 'validated', 'rejected') THEN
        RAISE EXCEPTION 'geometry of a dataset version with status % cannot be deleted', v_status
          USING ERRCODE = 'check_violation';
      END IF;
    ELSIF v_status NOT IN ('received', 'validated') THEN
      RAISE EXCEPTION 'geometry of a dataset version with status % is frozen', v_status
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
$$;
"""

PUBLISHED_GEOMETRY_VIEW = """
CREATE VIEW published_admin_unit_geometry AS
SELECT g.unit_id, g.boundary, g.representative_point
FROM admin_unit_geometry AS g
JOIN admin_unit AS u ON u.id = g.unit_id
JOIN dataset_version AS v ON v.id = u.dataset_version_id
WHERE v.status = 'published'
"""


def upgrade() -> None:
    op.create_table(
        "admin_unit_geometry",
        sa.Column("unit_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "boundary",
            Geometry("MULTIPOLYGON", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column(
            "representative_point",
            Geometry("POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("unit_id", name=op.f("pk_admin_unit_geometry")),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["admin_unit.id"],
            name=op.f("fk_admin_unit_geometry_unit"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "boundary IS NOT NULL OR representative_point IS NOT NULL",
            name=op.f("ck_admin_unit_geometry_not_empty"),
        ),
        sa.CheckConstraint(
            "boundary IS NULL OR (ST_IsValid(boundary) AND NOT ST_IsEmpty(boundary)"
            " AND ST_XMin(boundary) >= -180 AND ST_XMax(boundary) <= 180"
            " AND ST_YMin(boundary) >= -90 AND ST_YMax(boundary) <= 90)",
            name=op.f("ck_admin_unit_geometry_boundary_valid"),
        ),
        sa.CheckConstraint(
            "representative_point IS NULL OR (NOT ST_IsEmpty(representative_point)"
            " AND ST_X(representative_point) BETWEEN -180 AND 180"
            " AND ST_Y(representative_point) BETWEEN -90 AND 90)",
            name=op.f("ck_admin_unit_geometry_point_valid"),
        ),
    )
    op.create_index(
        "gix_admin_unit_geometry_boundary",
        "admin_unit_geometry",
        ["boundary"],
        postgresql_using="gist",
    )
    op.create_index(
        "gix_admin_unit_geometry_point",
        "admin_unit_geometry",
        ["representative_point"],
        postgresql_using="gist",
    )

    op.execute(sa.text(GEOMETRY_GUARD))
    op.execute(
        "CREATE TRIGGER trg_admin_unit_geometry_guard BEFORE INSERT OR UPDATE OR DELETE "
        "ON admin_unit_geometry FOR EACH ROW EXECUTE FUNCTION admin_unit_geometry_guard()"
    )
    op.execute(PUBLISHED_GEOMETRY_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS published_admin_unit_geometry")
    op.execute("DROP TRIGGER IF EXISTS trg_admin_unit_geometry_guard ON admin_unit_geometry")
    op.execute("DROP FUNCTION IF EXISTS admin_unit_geometry_guard()")
    op.drop_table("admin_unit_geometry")
