# Project Commands

## Environment

- **OS:** Windows
- **Package manager (Python):** uv
- **Package manager (Frontend):** npm
- **Database (Development):** PostgreSQL (localhost:5432, db: bidb, user: mkobi_app)
- **Database (Testing):** PostgreSQL (localhost:5434, user: mkobi_app)
  - The server provisions `bidb_test`, but every pytest run creates, migrates and then
    drops its own `bidb_test_<run token>` (`MKOBI_TEST_RUN_ID` when set, otherwise
    `uuid4().hex[:8]`). Two runs therefore cannot collide. Never pass the same
    `MKOBI_TEST_RUN_ID` to two concurrent runs — they would share one database and the
    first to finish would drop it out from under the second.
  - Default password: `test_app_password` (mkobi_app user)
  - Admin password: `test_password` (postgres user)

---

## Docker — Required for All Checks and Tests

> **Before running any tests, lint, type checks, or database operations — ensure Docker services are running.**
> Full setup and start instructions: [`docs/11-guides/docker.md`](../11-guides/docker.md)

> **Important:** Use `.env` for development and `docker/.env.production` for production deployments. The `.env` file contains placeholder values and is gitignored.

Quick check (test environment):
```powershell
docker compose -f docker/docker-compose.test.yml ps
```

Quick check (dev environment):
```powershell
docker compose -f docker/docker-compose.yml --env-file .env ps
```


IMPORTANT: USE Get-Content to read .env files. 
---

## Python (backend) — use `uv run` for all commands

| Task | Command |
|------|---------|
| Run tests | `uv run pytest <path>` |
| Run tests (in Docker) | `docker compose -f docker/docker-compose.test.yml exec test-app /app/.venv/bin/pytest tests/ -v` |
| Start test environment | `docker compose -f docker/docker-compose.test.yml up -d --build` |
| Stop test environment | `docker compose -f docker/docker-compose.test.yml down -v` |
| Lint (ruff) | `uv run ruff check <path>` |
| Type check (mypy) | `uv run mypy <path>` |
| Migrations | `uv run alembic ...` |
| Add dependency | `uv add <package>` |
| Add dev dependency | `uv add --dev <package>` |
| Database CLI (dev) | `set "PGPASSWORD=<your_password>" & psql -h localhost -p 5432 -U postgres -d bidb` |
| Database CLI (test) | `set "PGPASSWORD=test_password" & psql -h localhost -p 5434 -U postgres -d bidb_test` (the server's own database; a pytest run's tables live in its per-run `bidb_test_<run token>` instead) |

> **Always run from repo root:** `C:\py_dev\mkobi`

---

## TypeScript / React (frontend) — use `npm run` for all commands

> **Always run from:** `C:\py_dev\mkobi\frontend`

| Task | Command |
|------|---------|
| Type check | `npm run build` (runs `tsc -b && vite build`) |
| Lint (ESLint) | `npm run lint` |
| Run tests | `npm run test` (vitest) |
| Dev server | `npm run dev` |
| Production build | `npm run build` |
| Preview build | `npm run preview` |
| Add dependency | `npm install <package>` |
| Add dev dependency | `npm install --save-dev <package>` |

---

## Important

- **ALWAYS** run `C:\py_dev\mkobi\.ai\builders\build.bat` to update project info before starting work.
- **BEFORE starting any task:** audit → research → plan → implement.
