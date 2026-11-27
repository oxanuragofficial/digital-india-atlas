"""Administrative hierarchy, dataset provenance and publication guards.

Creates admin_level, admin_level_parent, dataset_version and admin_unit, seeds the four level
definitions (schema configuration, NOT geography), installs the triggers that enforce the
publication workflow, and creates the `published_admin_unit` view.

This migration inserts NO administrative units and no dataset versions.

Revision ID: 0001
Revises:
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_LIST = (
    "'received', 'validated', 'under_review', 'approved', 'published', 'rejected', 'superseded'"
)
VALIDATED_LIST = "'validated', 'under_review', 'approved', 'published', 'superseded'"
REVIEWED_LIST = "'approved', 'published', 'superseded'"
PUBLISHED_LIST = "'published', 'superseded'"

DATASET_VERSION_GUARD = """
CREATE FUNCTION dataset_version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.status <> 'received' THEN
      RAISE EXCEPTION 'a dataset version must be created with status received (got %)', NEW.status
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
  END IF;

  IF TG_OP = 'DELETE' THEN
    IF OLD.status NOT IN ('received', 'validated', 'rejected') THEN
      RAISE EXCEPTION 'a dataset version with status % cannot be deleted', OLD.status
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
  END IF;

  -- UPDATE
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF NOT (
      (OLD.status = 'received'     AND NEW.status IN ('validated', 'rejected')) OR
      (OLD.status = 'validated'    AND NEW.status IN ('under_review', 'rejected')) OR
      (OLD.status = 'under_review' AND NEW.status IN ('approved', 'rejected')) OR
      (OLD.status = 'approved'     AND NEW.status IN ('published', 'rejected')) OR
      (OLD.status = 'published'    AND NEW.status = 'superseded')
    ) THEN
      RAISE EXCEPTION 'illegal status change from % to %', OLD.status, NEW.status
        USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status = 'validated' AND NEW.record_count <= 0 THEN
      RAISE EXCEPTION 'a dataset version must contain at least one unit to be validated'
        USING ERRCODE = 'check_violation';
    END IF;

    -- Review starts here: what the reviewer sees must be exactly what was counted at import.
    IF NEW.status = 'under_review'
       AND (SELECT count(*) FROM admin_unit WHERE dataset_version_id = NEW.id) <> NEW.record_count
    THEN
      RAISE EXCEPTION 'record_count does not match the units stored for this dataset version'
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;

  -- Provenance is immutable once review has started. Corrections require a new dataset version.
  IF OLD.status NOT IN ('received', 'validated') AND (
    (OLD.publisher, OLD.dataset_name, OLD.version_label, OLD.code_system, OLD.source_date,
     OLD.source_url, OLD.license_name, OLD.license_url, OLD.attribution_text, OLD.file_name,
     OLD.file_sha256, OLD.record_count, OLD.validation_summary, OLD.imported_at, OLD.imported_by)
    IS DISTINCT FROM
    (NEW.publisher, NEW.dataset_name, NEW.version_label, NEW.code_system, NEW.source_date,
     NEW.source_url, NEW.license_name, NEW.license_url, NEW.attribution_text, NEW.file_name,
     NEW.file_sha256, NEW.record_count, NEW.validation_summary, NEW.imported_at, NEW.imported_by)
  ) THEN
    RAISE EXCEPTION 'provenance of a dataset version cannot change once review has started'
      USING ERRCODE = 'check_violation';
  END IF;

  RETURN NEW;
END
$$;
"""

ADMIN_UNIT_GUARD = """
CREATE FUNCTION admin_unit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_id bigint;
  v_status text;
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.dataset_version_id IS DISTINCT FROM OLD.dataset_version_id THEN
    RAISE EXCEPTION 'an administrative unit cannot move to another dataset version'
      USING ERRCODE = 'check_violation';
  END IF;

  IF TG_OP = 'DELETE' THEN
    v_id := OLD.dataset_version_id;
  ELSE
    v_id := NEW.dataset_version_id;
  END IF;

  SELECT status INTO v_status FROM dataset_version WHERE id = v_id;

  IF v_status IS NOT NULL THEN
    IF TG_OP = 'DELETE' THEN
      IF v_status NOT IN ('received', 'validated', 'rejected') THEN
        RAISE EXCEPTION 'units of a dataset version with status % cannot be deleted', v_status
          USING ERRCODE = 'check_violation';
      END IF;
    ELSIF v_status NOT IN ('received', 'validated') THEN
      RAISE EXCEPTION 'units of a dataset version with status % are frozen', v_status
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

PUBLISHED_VIEW = """
CREATE VIEW published_admin_unit AS
SELECT
  u.id,
  u.level_key,
  u.code,
  u.name,
  u.parent_id,
  u.parent_level_key,
  v.id AS dataset_version_id,
  v.publisher,
  v.dataset_name,
  v.version_label,
  v.code_system,
  v.source_date,
  v.license_name,
  v.license_url,
  v.attribution_text,
  v.published_at
FROM admin_unit AS u
JOIN dataset_version AS v ON v.id = u.dataset_version_id
WHERE v.status = 'published'
"""


def upgrade() -> None:
    # Needs a role allowed to create the extension (the Docker Compose user is a superuser).
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # ---- level definitions ----------------------------------------------------------------
    admin_level = op.create_table(
        "admin_level",
        sa.Column("level_key", sa.String(32), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("label", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("level_key", name=op.f("pk_admin_level")),
        sa.UniqueConstraint("rank", name=op.f("uq_admin_level_rank")),
        sa.UniqueConstraint("level_key", "rank", name=op.f("uq_admin_level_key_rank")),
        sa.CheckConstraint(
            "level_key ~ '^[a-z][a-z0-9_]*$'", name=op.f("ck_admin_level_key_format")
        ),
        sa.CheckConstraint("rank > 0", name=op.f("ck_admin_level_rank_positive")),
    )
    admin_level_parent = op.create_table(
        "admin_level_parent",
        sa.Column("level_key", sa.String(32), nullable=False),
        sa.Column("level_rank", sa.SmallInteger(), nullable=False),
        sa.Column("parent_level_key", sa.String(32), nullable=False),
        sa.Column("parent_rank", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint(
            "level_key", "parent_level_key", name=op.f("pk_admin_level_parent")
        ),
        sa.ForeignKeyConstraint(
            ["level_key", "level_rank"],
            ["admin_level.level_key", "admin_level.rank"],
            name=op.f("fk_admin_level_parent_level"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_level_key", "parent_rank"],
            ["admin_level.level_key", "admin_level.rank"],
            name=op.f("fk_admin_level_parent_parent"),
        ),
        sa.CheckConstraint(
            "parent_rank < level_rank", name=op.f("ck_admin_level_parent_rank_order")
        ),
    )

    # Reference configuration: the level definitions. These are schema, not geography.
    op.bulk_insert(
        admin_level,
        [
            {"level_key": "state_ut", "rank": 1, "label": "State / Union Territory"},
            {"level_key": "district", "rank": 2, "label": "District"},
            {"level_key": "subdistrict", "rank": 3, "label": "Subdistrict"},
            {"level_key": "locality", "rank": 4, "label": "Locality"},
        ],
    )
    op.bulk_insert(
        admin_level_parent,
        [
            {
                "level_key": "district",
                "level_rank": 2,
                "parent_level_key": "state_ut",
                "parent_rank": 1,
            },
            {
                "level_key": "subdistrict",
                "level_rank": 3,
                "parent_level_key": "district",
                "parent_rank": 2,
            },
            {
                "level_key": "locality",
                "level_rank": 4,
                "parent_level_key": "subdistrict",
                "parent_rank": 3,
            },
        ],
    )

    # ---- dataset provenance and publication status ----------------------------------------
    op.create_table(
        "dataset_version",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=False),
        sa.Column("dataset_name", sa.Text(), nullable=False),
        sa.Column("version_label", sa.Text(), nullable=False),
        sa.Column("code_system", sa.String(32), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("license_name", sa.Text(), nullable=False),
        sa.Column("license_url", sa.Text(), nullable=True),
        sa.Column("attribution_text", sa.Text(), nullable=True),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("record_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "validation_summary",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("imported_by", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), server_default=sa.text("'received'"), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_version")),
        sa.UniqueConstraint(
            "publisher", "dataset_name", "version_label", name=op.f("uq_dataset_version_identity")
        ),
        sa.UniqueConstraint(
            "publisher", "dataset_name", "file_sha256", name=op.f("uq_dataset_version_file")
        ),
        sa.CheckConstraint(f"status IN ({STATUS_LIST})", name=op.f("ck_dataset_version_status")),
        sa.CheckConstraint(
            "file_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_dataset_version_sha256_hex")
        ),
        sa.CheckConstraint(
            "code_system ~ '^[A-Z][A-Z0-9_]*$'", name=op.f("ck_dataset_version_code_system_format")
        ),
        sa.CheckConstraint(
            "btrim(publisher) <> '' AND btrim(dataset_name) <> '' AND btrim(version_label) <> ''"
            " AND btrim(license_name) <> '' AND btrim(file_name) <> ''",
            name=op.f("ck_dataset_version_text_not_blank"),
        ),
        sa.CheckConstraint("record_count >= 0", name=op.f("ck_dataset_version_record_count")),
        sa.CheckConstraint(
            f"status NOT IN ({VALIDATED_LIST}) OR validated_at IS NOT NULL",
            name=op.f("ck_dataset_version_validated_at"),
        ),
        sa.CheckConstraint(
            f"status NOT IN ({REVIEWED_LIST}) OR (reviewed_by IS NOT NULL"
            " AND btrim(reviewed_by) <> '' AND reviewed_at IS NOT NULL)",
            name=op.f("ck_dataset_version_reviewed_fields"),
        ),
        sa.CheckConstraint(
            f"status NOT IN ({PUBLISHED_LIST}) OR published_at IS NOT NULL",
            name=op.f("ck_dataset_version_published_at"),
        ),
    )
    op.create_index(
        "ux_dataset_version_one_published",
        "dataset_version",
        ["publisher", "dataset_name"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
    )
    op.create_index("ix_dataset_version_status", "dataset_version", ["status"])

    # ---- administrative units -------------------------------------------------------------
    op.create_table(
        "admin_unit",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("level_key", sa.String(32), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("parent_level_key", sa.String(32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_unit")),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_version.id"],
            name=op.f("fk_admin_unit_dataset_version"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["level_key"], ["admin_level.level_key"], name=op.f("fk_admin_unit_level")
        ),
        sa.ForeignKeyConstraint(
            ["level_key", "parent_level_key"],
            ["admin_level_parent.level_key", "admin_level_parent.parent_level_key"],
            name=op.f("fk_admin_unit_parent_edge"),
        ),
        sa.UniqueConstraint(
            "dataset_version_id", "level_key", "code", name=op.f("uq_admin_unit_code")
        ),
        sa.UniqueConstraint(
            "dataset_version_id", "id", "level_key", name=op.f("uq_admin_unit_version_id_level")
        ),
        sa.CheckConstraint("code ~ '^[A-Za-z0-9]+$'", name=op.f("ck_admin_unit_code_format")),
        sa.CheckConstraint(
            "btrim(name) = name AND name <> ''", name=op.f("ck_admin_unit_name_trimmed")
        ),
        sa.CheckConstraint(
            "(parent_id IS NULL) = (parent_level_key IS NULL)",
            name=op.f("ck_admin_unit_parent_pair"),
        ),
        sa.CheckConstraint(
            "parent_id IS NOT NULL OR level_key = 'state_ut'", name=op.f("ck_admin_unit_root_level")
        ),
    )
    # The self-referencing key needs the unique constraint above to exist first.
    op.create_foreign_key(
        op.f("fk_admin_unit_parent"),
        "admin_unit",
        "admin_unit",
        ["dataset_version_id", "parent_id", "parent_level_key"],
        ["dataset_version_id", "id", "level_key"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ux_admin_unit_code_zero_insensitive",
        "admin_unit",
        [
            "dataset_version_id",
            "level_key",
            sa.text("(COALESCE(NULLIF(ltrim(code, '0'), ''), '0'))"),
        ],
        unique=True,
    )
    op.create_index("ix_admin_unit_parent", "admin_unit", ["dataset_version_id", "parent_id"])
    op.create_index("ix_admin_unit_level_code", "admin_unit", ["level_key", "code"])

    # ---- guards: publication workflow and frozen data -------------------------------------
    op.execute(sa.text(DATASET_VERSION_GUARD))
    op.execute(
        "CREATE TRIGGER trg_dataset_version_guard BEFORE INSERT OR UPDATE OR DELETE "
        "ON dataset_version FOR EACH ROW EXECUTE FUNCTION dataset_version_guard()"
    )
    op.execute(sa.text(ADMIN_UNIT_GUARD))
    op.execute(
        "CREATE TRIGGER trg_admin_unit_guard BEFORE INSERT OR UPDATE OR DELETE "
        "ON admin_unit FOR EACH ROW EXECUTE FUNCTION admin_unit_guard()"
    )

    # ---- read model: only published data -------------------------------------------------
    op.execute(PUBLISHED_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS published_admin_unit")
    op.execute("DROP TRIGGER IF EXISTS trg_admin_unit_guard ON admin_unit")
    op.execute("DROP FUNCTION IF EXISTS admin_unit_guard()")
    op.execute("DROP TRIGGER IF EXISTS trg_dataset_version_guard ON dataset_version")
    op.execute("DROP FUNCTION IF EXISTS dataset_version_guard()")
    op.drop_table("admin_unit")
    op.drop_table("dataset_version")
    op.drop_table("admin_level_parent")
    op.drop_table("admin_level")
    # PostGIS is intentionally left installed: other objects may depend on it.
