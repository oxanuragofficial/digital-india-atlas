# Digital India Atlas

A free, open, nationwide geographic and knowledge platform for India.

Digital India Atlas aims to bring India's geography, administrative structure and public information together in one place, so that students, researchers, developers, journalists and citizens can explore the country through maps and well-organised data.

> **Status:** Early development. The engineering foundation (Milestone 1) is in place: a web app with a map, a backend API with health checks, and a PostGIS database setup. **No Indian administrative boundaries, identifiers or statistics are included yet**, and the map is a general-purpose basemap, not an official map of India.

## Purpose

India's geographic and public data is spread across many portals, formats and languages. It is often hard to find, hard to compare and hard to reuse. Digital India Atlas exists to make that information:

- **Discoverable**: one place to explore states, districts, cities and regions on an interactive map.
- **Accessible**: free to use, with no paywall or account required for core features.
- **Reusable**: structured, documented and openly licensed data that others can build on.
- **Trustworthy**: every dataset carries its source, licence and update date.

## Vision

A reliable, open digital atlas of India that:

1. Presents the country's geography clearly, from national overviews down to local detail.
2. Pairs maps with a searchable knowledge layer covering places, administrative units and public information.
3. Serves learners and professionals alike, and works well on low-bandwidth connections and mobile devices.
4. Grows through community contribution, with transparent data rules and review.

## Planned Capabilities

Goals, not yet implemented unless marked:

- Interactive map of India with administrative boundaries (*basemap only so far*)
- Search across places and administrative units
- Dataset catalogue with source and licence information
- Open data downloads and a public API (*health endpoints only so far*)
- Clear contribution guidelines for data and code

## Data Principles

- Use only data that is openly licensed or in the public domain, and attribute it properly.
- Record the source, licence and retrieval date for every dataset.
- Prefer official and authoritative sources; document any corrections made.
- Never publish personal or sensitive data.
- Never invent boundaries, identifiers (including LGD codes) or statistics, and never ship placeholder data that could be mistaken for official data.

## Technology

| Area | Choice |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Map | MapLibre GL JS with the OpenFreeMap basemap ([attribution and usage](docs/MAP_BASEMAP.md)) |
| Backend | FastAPI (Python), SQLAlchemy |
| Database | PostgreSQL with PostGIS, run through Docker Compose |
| Tests | pytest (backend), Vitest and Testing Library (frontend) |

## Repository layout

```
apps/api/        FastAPI backend, GIS utilities and tests
apps/web/        Next.js frontend
infra/db/init/   SQL run on first database start
docs/            setup, basemap, architecture and data-model notes
docker-compose.yml, .env.example
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for details.

## Quick start

Full step-by-step instructions with exact Windows PowerShell commands: **[docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md)**.

In short:

1. Copy `.env.example` to `.env` and set `POSTGRES_PASSWORD` and `DATABASE_URL` (no default passwords are shipped).
2. `docker compose up -d db` starts PostgreSQL with PostGIS.
3. Backend: create a virtual environment in `apps/api`, `pip install -e ".[dev]"`, then `python -m uvicorn app.main:app --port 8000`.
4. Frontend: in `apps/web`, `npm install` then `npm run dev`, and open http://localhost:3000.

## Testing

- Backend: `python -m pytest` in `apps/api`. Database tests run only when `TEST_DATABASE_URL` is set (see [docs/ADMIN_DATA_MODEL.md](docs/ADMIN_DATA_MODEL.md)).
- Frontend: `npm run check` in `apps/web` (lint, type-check, unit tests) and `npm run build`.

## Security

- Never commit `.env` files, passwords, tokens or API keys. `.env` is git-ignored; only the `*.example` templates are tracked.
- `NEXT_PUBLIC_*` variables are visible in the browser. Never put secrets in them.
- The database port is published on `127.0.0.1` only.

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repository bootstrap and documentation | Done |
| 1 | Project scaffold and starter application (Milestone 1: engineering foundation) | Implemented; Windows smoke test pending |
| 2 | Administrative data foundation (Milestone 2: schema, provenance, safe import; no real data yet) | Implemented on a feature branch; not merged |
| 3 | Core map experience and data pipeline | Planned |
| 4 | Search, knowledge layer and public API | Planned |
| 5 | Community contributions and wider coverage | Planned |

## Contributing

Contribution guidelines will be published as the project structure takes shape. Until then, please open an issue to discuss ideas or data sources.

## Licence

A licence will be added before the first public release.
