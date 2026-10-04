# Subagents
Max allowed parallel subagents = 2
Only 1 implementor agent is allowed at a time.
Do not launch agents in background.
If stop or break prefer resume old session not launching new agent.

# Project Commands

**Env:** Windows 11 · `uv` (Python) · PostgreSQL 18 in Docker · Vue/React frontend (npm)

`.\Makefile.ps1 <target>` (PowerShell 7+) is the canonical entry point. Every
invocation runs `docker compose` against an explicit project name (`-p mkobi` for
dev, `-p mkobi-test` for the test stack) — the script never mutates
`$env:COMPOSE_PROJECT_NAME`. There is no GNU `Makefile` and no `make` wrapper in
this repo.

Run the script from the repo root: relative paths (`--env-file .env`,
`-f docker/...`) resolve against the current working directory.

## Quick start

**This environment is Windows 11** — use `.\Makefile.ps1` in PowerShell 7+.

| Task | Command |
|---|---|
| Dev up (app :8010 + Vite :5173) | `.\Makefile.ps1 up` |
| Stop dev stack | `.\Makefile.ps1 down` |
| Start test services (test-db :5434, test-redis :6381) | `.\Makefile.ps1 test-up` |
| Full test suite | `.\Makefile.ps1 test` |
| Full suite with live coverage gate | `.\Makefile.ps1 test-all` |
| Fresh test schema (after migration changes) | `.\Makefile.ps1 test-fresh` |
| Stop test stack | `.\Makefile.ps1 test-down` |

`head` and `tail` commands are not working in PowerShell.

## Python (local, PowerShell)

| Task | Command |
|---|---|
| Lint | `uv run ruff check <path>` |
| Auto-fix (incl. import sorting, I001) | `uv run ruff check --fix <path>` |
| Typecheck | `uv run mypy <path>` |
| Add dep | `uv add <pkg>` / `uv add --dev <pkg>` |

> `ruff check --fix` handles import sorting (I001). `ruff format` only reformats
> (line wraps, quotes) and does **NOT** sort imports — `.\Makefile.ps1 format`
> runs `ruff check --fix src/ tests/`, not `ruff format`.

## Tests

`.\Makefile.ps1 test` — the canonical gate — runs the suite through the `test-app`
service of the `mkobi-test` Compose project (`docker/docker-compose.test.yml`,
PostgreSQL on host port 5434).

A host-side `uv run pytest` is **not** excluded any more. Every pytest process
resolves its own test database name, `bidb_test_<run token>`, so a host run and a
container run — or two host runs — can no longer drop each other's database. Two
limits are left, and both are real:

- The test stack must be up (`.\Makefile.ps1 test-up`), because `tests/conftest.py`
  points a host run at the `test-db` container's published port, `localhost:5434`.
- The image installs `libmagic1`; the Windows host does not have it. Any module whose
  import graph reaches `src/mkobi/services/file_processing.py` therefore fails to
  collect on the host with `ImportError: failed to find libmagic`. Modules that do
  not reach it run on the host, database-backed ones included.

`docs/06-backend/testing.md` is the SSOT for the per-run database.

**Canonical path:**

```powershell
.\Makefile.ps1 test                 # full suite, schema recreated by conftest
.\Makefile.ps1 test-select -k some_test -v   # forward args to pytest verbatim
.\Makefile.ps1 test-shell           # interactive bash inside the test image
```

The `test-select` target forwards every argument after the target name to
`pytest` unchanged.

**Raw alias (one-off overrides only):**

```powershell
$dc = 'docker compose -p mkobi-test -f docker/docker-compose.test.yml'
```

No `--env-file` is needed: the test compose is hermetic (all credentials are
hard-coded literals). Pass `--project-directory` **never** — it resolves the
services' `build.context: ..` to the repo's parent directory.

| Task | Command | When |
|---|---|---|
| Start test services | `$dc up -d --wait test-db test-redis` | Once per session |
| Full suite | `$dc run --rm --no-deps test-app pytest` | Default |
| Stop | `$dc down` | Done (preserves named volumes) |

**How the schema is created.** `tests/conftest.py` recreates and migrates the test
database itself (session-scoped `setup_test_database` fixture), so there is no
separate migrate step on the test path. The database it recreates is **this run's own**
`bidb_test_<run token>` — the token is `MKOBI_TEST_RUN_ID` when set, otherwise
`uuid4().hex[:8]` — and the session-end teardown drops it again, so the run leaves no
database behind. Never pass the same `MKOBI_TEST_RUN_ID` to two concurrent runs: they
would share one database and the first to finish would drop it out from under the
second. `setup_test_database` is **not** autouse; only the modules and fixtures that
need a live database request it, so a pure-unit selection creates no database at all.
The `mkobi_app` role must pre-exist — it is created by
`docker/init-scripts/01-create-app-role.sh` on first `test-db` volume initialisation.
If pytest reports `role "mkobi_app" does not exist`, run `.\Makefile.ps1 test-reset`
once to rebuild the volume.

## Dev stack

```powershell
.\Makefile.ps1 up         # rm -sf migrate, then up -d --wait
.\Makefile.ps1 ps
.\Makefile.ps1 logs app
.\Makefile.ps1 shell      # throwaway bash in the app image
.\Makefile.ps1 restart
```

The dev services are `db`, `migrate`, `app`, `redis`, `rq-worker`, `frontend`;
`nginx` is production-only (`--profile production`) and is not part of the dev
stack. Migrations are **Alembic** (`.\Makefile.ps1 migrate`,
`migration-new`, `migration-status`) — this is not a Django project, so there is
no ORM migration command and no Django admin bootstrap. The admin user is
bootstrapped from `ADMIN_USERNAME` / `ADMIN_PASSWORD` at application startup.

## Database and backup

| Task | Command |
|---|---|
| Apply migrations | `.\Makefile.ps1 migrate` |
| Autogenerate a revision | `.\Makefile.ps1 migration-new "message"` |
| Show current vs head | `.\Makefile.ps1 migration-status` |
| Interactive psql | `.\Makefile.ps1 psql` |
| One-shot SQL | `.\Makefile.ps1 psql-c "SELECT 1"` |
| Backup | `.\Makefile.ps1 backup` |
| Restore | `.\Makefile.ps1 restore .\backups\bidb-<stamp>.dump` |
| Prune old backups | `.\Makefile.ps1 prune-backups` |

Never redirect `pg_dump` stdout to a host file — PowerShell corrupts binary
output. `backup` writes the dump inside the container and copies it out with
`docker compose cp`.

## Quality gates

| Task | Command |
|---|---|
| Lint (ruff) | `.\Makefile.ps1 lint` |
| Auto-fix (ruff) | `.\Makefile.ps1 format` |
| Typecheck (mypy) | `.\Makefile.ps1 typecheck` |
| Frontend lint (eslint) | `.\Makefile.ps1 fe-lint` |
| Frontend tests (vitest) | `.\Makefile.ps1 fe-test` |
| All of the above | `.\Makefile.ps1 check` |

`fe-lint` and `fe-test` are host-native and require `.\Makefile.ps1 fe-install`
to have been run once.

## Diagnostics and cleanup

| Task | Command |
|---|---|
| Resolved dev config | `.\Makefile.ps1 config` |
| Resolved test config | `.\Makefile.ps1 config-test` |
| Versions + service lists | `.\Makefile.ps1 doctor` |
| Remove containers/networks, keep volumes | `.\Makefile.ps1 clean` |
| Remove both projects' volumes (prompts) | `.\Makefile.ps1 fullclean` |
| fullclean + cache/image prune (prompts) | `.\Makefile.ps1 nuke` |

`config` and `config-test` print resolved secrets. Do not paste their output into
a shared channel. `fullclean` and `nuke` are scoped to `-p mkobi` / `-p mkobi-test`
only and never run a daemon-global volume prune.
