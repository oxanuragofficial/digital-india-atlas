# Setup on Windows (PowerShell)

Everything below runs in **Windows PowerShell** or **PowerShell 7**. Run each command from the folder indicated.

> **Verification note.** The project was built and tested on Linux. The commands here are the Windows equivalents, but the Windows-specific steps (virtual-environment activation, Docker Desktop, PowerShell syntax) have **not** been executed on a Windows machine. If one fails, see Troubleshooting and please report it.

## 1. Prerequisites

| Tool | Version used when building | Get it |
|---|---|---|
| Git | any recent | https://git-scm.com/download/win |
| Node.js | 22 LTS (v22.23 tested) | https://nodejs.org (includes npm) |
| Python | 3.11 or newer (3.13 tested) | https://www.python.org/downloads/ (tick "Add python.exe to PATH") |
| Docker Desktop | with the WSL 2 backend | https://www.docker.com/products/docker-desktop/ |

Check them:

```powershell
git --version
node --version
npm --version
python --version
docker --version
docker compose version
```

## 2. Get the code

```powershell
git clone https://github.com/oxanuragofficial/digital-india-atlas.git
cd digital-india-atlas
```

## 3. Create your private settings file

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(24))"
notepad .env
```

In Notepad, paste the generated value (call it `YOURPASSWORD`) into **both** places, with no spaces or quotes:

```
POSTGRES_PASSWORD=YOURPASSWORD
DATABASE_URL=postgresql+psycopg://atlas:YOURPASSWORD@localhost:5432/atlas
```

Save and close. `.env` is git-ignored: it never gets committed. Do not share it or paste it into chats or issues.

The generated password uses only letters, digits, `-` and `_`, so it needs no URL-encoding. If you choose your own, URL-encode any special characters in `DATABASE_URL`.

## 4. Start PostgreSQL with PostGIS

Make sure Docker Desktop is running, then:

```powershell
docker compose up -d db
docker compose ps
```

Wait until the `db` service shows `healthy`. Then confirm PostGIS is installed:

```powershell
docker compose exec db psql -U atlas -d atlas -c "SELECT PostGIS_Version();"
```

To stop it: `docker compose down` (your data is kept in a Docker volume). To delete the data as well: `docker compose down -v`.

## 5. Backend (FastAPI)

```powershell
cd apps\api
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If activation is blocked ("running scripts is disabled"), allow it for this window only and retry:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Run the tests:

```powershell
python -m pytest
```

Without a database, the 3 PostGIS integration tests are **skipped**. To include them, point them at the Docker database (replace `YOURPASSWORD`):

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://atlas:YOURPASSWORD@localhost:5432/atlas"
python -m pytest
Remove-Item Env:TEST_DATABASE_URL
```

Start the API:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

In a **second** PowerShell window:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/health/db
```

Expected: `/health` returns `status: ok`; `/health/db` returns `status: ok`, `database: up` and a `postgis` version. Interactive API docs (development only): http://localhost:8000/docs

Lint (optional): `python -m ruff check .`

### Database migrations (Milestone 2)

With the database running and `DATABASE_URL` set in `.env`, from `apps\api` with the virtual environment active:

```powershell
python -m alembic upgrade head
python -m app.admin_data status
```

This creates the tables only; it loads **no** administrative data. The import commands are described in [ADMIN_DATA_MODEL.md](ADMIN_DATA_MODEL.md).

To run the database tests, point `TEST_DATABASE_URL` at the Docker database (its `atlas` user may create databases):

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://atlas:YOUR_PASSWORD@localhost:5432/atlas"
python -m pytest
```

The tests create and drop their own temporary database. Without the variable, database tests are skipped.

> The Milestone 2 commands and tests have been run on Linux only. They have **not** been verified on Windows yet; please report anything that fails.

## 6. Frontend (Next.js)

In a **new** PowerShell window, from the repository root:

```powershell
cd apps\web
npm install
npm run dev
```

Open **http://localhost:3000** (use `localhost`, not `127.0.0.1`: the API only allows `http://localhost:3000` by default).

You should see the header, the side panel and the map. The panel shows **API online** when the backend is running.

Frontend checks:

```powershell
npm run check     # lint + type-check + tests
npm run build     # production build
```

From the repository root you can also use the shortcuts in the root `package.json`, for example `npm run web:check`, `npm run web:dev`, `npm run db:up`.

Optional frontend settings: copy `apps\web\.env.example` to `apps\web\.env.local` and edit. See that file for details.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `docker compose up` says `POSTGRES_PASSWORD` is missing | Fill in `POSTGRES_PASSWORD` in `.env` (step 3). This is intentional: there is no default password. |
| `docker` cannot connect to the daemon | Start Docker Desktop and wait until it reports it is running. |
| Port 5432 already in use | Another PostgreSQL is running. Change `POSTGRES_PORT` in `.env` (and the port inside `DATABASE_URL`), then `docker compose up -d db`. |
| `/health/db` returns `connection_failed` | The database is not running, or the password or port in `DATABASE_URL` does not match `.env`. If you changed `POSTGRES_PASSWORD` after the first start, run `docker compose down -v` and start again (this deletes local data). |
| `/health/db` returns `not_configured` | `DATABASE_URL` is blank in `.env`. Set it, then restart the API. |
| `/health/db` returns `postgis_unavailable` | You are connected to a PostgreSQL without PostGIS. Use the Docker `db` service. |
| Panel says **API offline** | Backend not running, or you opened the site via `127.0.0.1` (CORS). Use http://localhost:3000. |
| Map area is blank or shows "The basemap could not be loaded" | WebGL disabled, or the network or a firewall blocks `tiles.openfreemap.org`. Open https://tiles.openfreemap.org/styles/liberty in the browser to test. |
| Browser console: "Worker failed to load" | The worker copy is missing. Run `npm install` (or `node scripts/copy-maplibre-worker.mjs`) in `apps\web`. |
| `npm install` fails on a peer-dependency error | Use Node 22 LTS and delete `apps\web\node_modules`, then retry. |
