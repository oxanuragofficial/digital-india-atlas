# Architecture (Milestones 1-2)

## Layout

```
digital-india-atlas/
├── apps/
│   ├── api/                  FastAPI backend (Python)
│   │   ├── app/
│   │   │   ├── main.py       application factory (create_app)
│   │   │   ├── config.py     settings from environment / .env, no default credentials
│   │   │   ├── api/          HTTP routes (health.py) and dependencies (deps.py)
│   │   │   ├── db/           SQLAlchemy base, engine/session, connectivity + PostGIS check
│   │   │   └── gis/          pure-Python GIS helpers (bounding boxes, GeoJSON validation)
│   │   └── tests/            pytest suite
│   └── web/                  Next.js + TypeScript + Tailwind CSS frontend
│       ├── src/app/          routes and layout
│       ├── src/components/   AtlasShell, Sidebar, ApiStatusBadge, map/
│       ├── src/lib/          map-config.ts, api.ts
│       └── scripts/          copy-maplibre-worker.mjs
├── infra/db/init/            SQL run on first database start (enables PostGIS)
├── docs/                     setup, basemap, architecture
├── docker-compose.yml        PostgreSQL + PostGIS for local development
└── .env.example              backend / database settings template
```

## Backend

- **Endpoints:** `GET /health` (liveness, never touches the database) and `GET /health/db` (readiness: `SELECT 1`, then `PostGIS_Version()` on PostgreSQL). Failure responses carry a short code (`not_configured`, `connection_failed`, `postgis_unavailable`) and never include driver error text, which can contain hostnames or credentials.
- **Configuration:** `pydantic-settings`. `DATABASE_URL` is a `SecretStr` (masked in reprs) and **has no default**. A blank value means "not configured". With `APP_ENV=production`, startup is refused if `DATABASE_URL` is missing or looks like a placeholder, or if CORS contains `*`. API docs are disabled in production.
- **Database:** SQLAlchemy 2.x with the `psycopg` (v3) driver and `pool_pre_ping`. ORM models for the administrative hierarchy live in `app/admin_data/` (Milestone 2); schema changes go through Alembic migrations in `apps/api/migrations`. See [ADMIN_DATA_MODEL.md](ADMIN_DATA_MODEL.md).
- **GIS utilities:** `BoundingBox` and a structural GeoJSON validator (types, coordinate ranges, ring closure). They validate shape only; they do not repair geometries or judge whether data is authoritative. `INDIA_VIEWPORT` is a map framing convenience, not a boundary.
- **CORS:** only the origins in `CORS_ALLOWED_ORIGINS`, `GET` only for now.

## Administrative data (Milestone 2)

- `app/admin_data/`: models, level graph, status workflow, manifest, CSV validator, importer, publishing and a CLI (`python -m app.admin_data`).
- One self-referencing `admin_unit` table plus level configuration tables; hierarchy enforced by composite foreign keys; versioned dataset snapshots with provenance and licence; publication guarded by database triggers; optional `MultiPolygon`/`Point` geometry in EPSG:4326.
- Imports validate first, write nothing on error, and stop at `validated`; a person must review and publish. **No real administrative data is included or downloaded.**
- Alembic: `alembic.ini` has no database URL; it comes from `DATABASE_URL`. Run `python -m alembic upgrade head` in `apps/api`.
- The HTTP API does not expose this data yet.

## Frontend

- Next.js (App Router) with TypeScript and Tailwind CSS 4.
- **Map-first layout:** a fixed side panel and a full-height map on desktop; on small screens the map fills the viewport and the panel is a toggleable bottom sheet.
- MapLibre GL JS is loaded client-side only (`next/dynamic`, `ssr: false`) because it needs WebGL.
- The panel states plainly that **no datasets are loaded**. There is no placeholder data of any kind.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`) are set in `next.config.ts`. A Content-Security-Policy is **not** yet configured (it needs care with MapLibre's workers and tile origins) and is listed as follow-up work.

## Decisions worth knowing

- **TypeScript is pinned to 6.0.x**, not 7: `typescript-eslint` (used by `eslint-config-next`) does not yet support TypeScript 7 and ESLint fails to start. Revisit when it does.
- **MapLibre worker is self-hosted** from `public/` because bundling breaks its default lookup. See `docs/MAP_BASEMAP.md`.
- **The map container is sized with `h-full w-full`**, not `absolute inset-0`: MapLibre's CSS sets `position: relative` on its container and would override it, collapsing the map to zero height.

## Not yet done

Any real Indian administrative data or official identifiers, API endpoints for the hierarchy, official-source adapters, multilingual names, authentication, a Content-Security-Policy, deployment configuration (including restricted database roles).
