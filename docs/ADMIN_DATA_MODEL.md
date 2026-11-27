# Administrative data model (Milestone 2)

This milestone adds the **database foundation** for India's administrative hierarchy and a **safe import pipeline**. It deliberately contains **no real geography**: no boundaries, no official identifiers, no statistics. Every row used in tests is synthetic and exists only inside a temporary test database.

> Status: tested against PostgreSQL 16 + PostGIS 3.4 on Linux. **Not yet verified on Windows or against the Docker Compose database.**

## 1. Design in one paragraph

One generic, self-referencing table (`admin_unit`) holds every unit at every level. Which levels exist, and which level may sit under which, is *data* (`admin_level`, `admin_level_parent`), not table structure. Every unit belongs to a **dataset version**, an immutable-once-reviewed snapshot that carries source, licence and publication status. Only versions with status `published` are visible through the read views. Hierarchy rules are enforced by the database itself with composite foreign keys, so no application code path can create an orphan or a cross-level link.

## 2. Tables

```
admin_level (level_key PK, rank, label)
      ^   ^
      |   +-- admin_level_parent (level_key, parent_level_key)  allowed edges; parent_rank < level_rank
      |
dataset_version (id PK, publisher, dataset_name, version_label, code_system, source_date,
      |          source_url, license_name, license_url, attribution_text,
      |          file_name, file_sha256, record_count, validation_summary, imported_at, imported_by,
      |          status, validated_at, reviewed_by, reviewed_at, review_note, published_at)
      |
admin_unit (id PK, dataset_version_id FK, level_key FK, code, name, parent_id, parent_level_key)
      |        self-reference: (dataset_version_id, parent_id, parent_level_key) -> admin_unit
      |
admin_unit_geometry (unit_id PK/FK, boundary, representative_point)      optional, 1:1
```

Default levels (schema configuration seeded by migration 0001, not geography):

| rank | level_key | allowed parent |
|---|---|---|
| 1 | `state_ut` | none (root) |
| 2 | `district` | `state_ut` |
| 3 | `subdistrict` | `district` |
| 4 | `locality` | `subdistrict` |

### Identifiers

- `code` is the **official identifier as a string** (`VARCHAR(32)`, `^[A-Za-z0-9]+$`). It is never converted to a number, so leading zeros survive.
- Unique per (dataset version, level, code). A second unique index on the code with leading zeros stripped blocks look-alikes such as `7` and `007` inside one level and version, because that usually indicates a corrupted export.
- Codes are case-sensitive and never trimmed or padded by the importer. Anything doubtful is reported, not fixed.
- `dataset_version.code_system` names the scheme the codes belong to (for example a government coding system) so codes from different systems are never conflated.
- The model **does not assume** the identifiers are unique across levels or stable between versions. Crosswalks between versions or systems are future work.

### Hierarchy integrity (declarative)

| Rule | Mechanism |
|---|---|
| Parent exists, is in the **same dataset version**, and has the stated level | composite FK `fk_admin_unit_parent` (dataset_version_id, parent_id, parent_level_key) |
| The child level may sit under that parent level | composite FK `fk_admin_unit_parent_edge` to `admin_level_parent` |
| Only `state_ut` may be a root; everything else needs a parent | CHECK `ck_admin_unit_root_level`, `ck_admin_unit_parent_pair` |
| No cycles | `admin_level_parent` CHECK `parent_rank < level_rank`; units can only point at a higher-ranked level |

### Provenance and licence

Every `dataset_version` records: publisher, dataset name, version label, code system, **source date**, source URL, **licence name (mandatory)**, licence URL, attribution text, the imported **file name and SHA-256**, record count, a JSON validation summary, **import timestamp** (timezone-aware) and importer name. Blank strings are rejected. A published version's provenance cannot be edited.

## 3. Publication workflow

```
received -> validated -> under_review -> approved -> published -> superseded
   \____________\______________\____________\-> rejected (terminal, from any pre-published state)
```

Enforced by a database trigger (`dataset_version_guard`), not only application code:

- New versions can only be inserted as `received`.
- Only the transitions above are legal. Validation requires at least one unit; entering review requires `record_count` to match the stored units.
- From `under_review` onward, units, geometry and provenance are **frozen**.
- Units and geometry can be edited only in `received` / `validated`; whole versions can be deleted only in `received`, `validated` or `rejected`.
- At most **one published version per dataset** (partial unique index). Publishing a new version supersedes the old one in the same transaction.
- **The importer never publishes.** It always stops at `validated`. A named human reviewer runs `submit-for-review`, `approve`, then `publish`.

Read access for the application goes through the views `published_admin_unit` and `published_admin_unit_geometry`, which expose only published data together with its licence and publisher.

## 4. Geometry

| Column | Type | CRS |
|---|---|---|
| `boundary` | `geometry(MultiPolygon, 4326)` | EPSG:4326 (WGS 84), x = longitude, y = latitude |
| `representative_point` | `geometry(Point, 4326)` | EPSG:4326 |

- Geometry is **optional and lives in its own table**, so hierarchy and identifiers can be imported and reviewed before any boundary exists, and so large geometry never bloats the hierarchy table.
- MultiPolygon is used because many units are non-contiguous (islands, enclaves). A plain Polygon is accepted and **promoted** to MultiPolygon by PostGIS (tested). Points, wrong SRIDs, empty, invalid (self-intersecting) and out-of-range (|lon| > 180, |lat| > 90) shapes are rejected by the database.
- Both columns have GiST indexes. At least one of the two must be present.
- EPSG:4326 is a storage CRS. Area and length calculations need a projected CRS or `geography`; this milestone does not compute any.
- **No boundary data is shipped or downloaded.** Official boundary sources and their licences have to be assessed before any are loaded.

## 5. Import foundation

Command (run from `apps/api` with the virtual environment active):

```
python -m app.admin_data validate FILE [--code-width LEVEL=N] [--report-file REPORT]
python -m app.admin_data import   FILE --manifest MANIFEST.json [--imported-by NAME] [--code-width LEVEL=N] [--report-file REPORT]
python -m app.admin_data status
python -m app.admin_data submit-for-review ID
python -m app.admin_data approve   ID --reviewer NAME [--note TEXT]
python -m app.admin_data publish   ID
python -m app.admin_data reject    ID --reviewer NAME --reason TEXT
```

Exit codes: `0` success, `1` data refused (validation failed, duplicate import, checksum mismatch, illegal transition), `2` usage or configuration problem. Database error text is never printed (it can contain connection details).

### CSV format `atlas-admin-units-v1`

UTF-8, header row exactly `level,code,name,parent_level,parent_code`. Roots leave the parent columns empty. Rows may appear in any order; parents are inserted before children. Quote codes in spreadsheets as text; opening and re-saving in a spreadsheet application commonly destroys leading zeros, which is why the validator exists.

This is an *Atlas* interchange format. Converting an official export into it needs a small adapter written against that specific source, once its structure and licence are confirmed.

### Manifest (JSON)

Required: `publisher`, `dataset_name`, `version_label`, `code_system`, `source_date` (not in the future), `license_name`. Optional: `source_url`, `license_url`, `attribution_text`, `expected_sha256` (import is refused if the file does not match). Unknown keys are rejected so typos cannot silently drop provenance.

### Validation

Pure function, no database writes. Reports every problem with a rule ID and line number, capped at `max_issues`. Nothing is silently corrected; the only normalisation is name whitespace/Unicode NFC, and it is reported as a warning. Rules include: encoding, header, field count, control characters, unknown level, code blank/whitespace/format/fixed-width/zero-padding ambiguity, name blank/length, parent missing/not found/wrong level/not allowed, duplicates.

### Safety properties (each covered by tests)

- Invalid file: nothing written.
- Same file (by checksum), or same version label with different content: refused.
- Import runs inside the caller's transaction; a failure part-way rolls everything back.
- Imported data is never visible in the published views until explicitly published.

## 6. Adding a level (village, town, ward, ...)

No table changes. Add an Alembic data migration that inserts a row in `admin_level` (unique rank) and rows in `admin_level_parent` for each allowed parent. A level may have several allowed parents (for example a village under a subdistrict, a ward under a town). Then add the level to `DEFAULT_LEVELS` / `DEFAULT_PARENT_EDGES` in `app/admin_data/levels.py`; a test compares the code defaults with the migrated database.

## 7. Scale and known limits

- Each dataset version is a **full snapshot**. India has on the order of hundreds of thousands to over a million named units depending on levels included; a handful of versions is fine, but retaining many snapshots will cost storage. Pruning of superseded versions is not implemented.
- Guard triggers run per row; bulk loads of millions of rows are slower than an unguarded load. Import inserts in chunks of 5,000.
- `TRUNCATE` bypasses row triggers and is **not guarded**. Use database roles to withhold `TRUNCATE` and `DELETE` from the application user in production (deployment work, not yet done).
- Not yet modelled: multilingual names and aliases, effective-date history, crosswalks between code systems or versions, towns/wards/villages data, simplified geometry tiles for rendering.
- No API endpoints expose this data yet.

## 8. Running the database tests

```
export TEST_DATABASE_URL="postgresql+psycopg://USER:PASSWORD@localhost:5432/atlas"
python -m pytest
```

The suite creates a private temporary database `atlas_test_<random>` on that server (the role needs `CREATEDB`), runs the real Alembic migrations into it, and drops it afterwards. Your own data is not touched. The older M1 PostGIS tests connect to the given database directly and expect PostGIS to be enabled there (the Docker image's init script does that). Without `TEST_DATABASE_URL`, database tests are skipped.
