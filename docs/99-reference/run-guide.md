---
id: run-guide
domain: reference
tags:
  - setup
  - configuration
  - deployment
  - database
  - migrations
  - testing
  - troubleshooting
related:
  - swagger-guide
  - system-overview
  - deployment
  - configuration
  - backend-architecture
---

# Application Run Guide

## Prerequisites

- PostgreSQL installed and running
- Python 3.12+
- uv (package manager)

## Configuration via YAML Config

All settings are located in: `src/mkobi/settings/app.yaml`

### Main Settings

```yaml
# No environment tier key here: the tier is selected by the ENV environment
# variable (development, staging, production, test). Settings.environment
# declares alias="ENV" without populate_by_name, so only the exact spelling
# "ENV" populates the field; an "env" key is passed through unrenamed and
# discarded. An uppercase "ENV" key here would work, but this YAML source
# ranks below the environment and .env sources, so ENV as an environment
# variable is the supported way to select the tier.

# Automatic migrations (true/false)
auto_migrate: true

# Test database (optional)
# test_database_url: "postgresql+asyncpg://postgres:1234@localhost:5432/bidb_test"
recreate_test_db: false

# Database
database:
  host: localhost
  port: 5432
  dbname: bidb
  user: postgres
  password: "1234"  # In production, use environment variables

# JWT
jwt:
  secret_key: "your-secret-key-change-in-production"
  algorithm: HS256
  access_token_expire_minutes: 30

# Upload
# No temp_dir key here: without one the field resolves to an absolute
# platformdirs path (user_data_dir("mkobi", "ZOO")/tmp_uploads). Override it
# with the UPLOAD__TEMP_DIR environment variable.
upload:
  allowed_file_types:
    - ".csv.gz"
    - ".csv"
  max_file_size: 104857600  # 100MB
  lazy_threshold_mb: 10.0

# Redis
redis:
  host: localhost
  port: 6379
  db: 0

# Logging
# No format key here: setup_logging takes no format parameter, so the
# non-JSON format is a literal in the logging configuration module.
logging:
  level: INFO

# Charts
charts:
  default_colors:
    - "#1f77b4"
    - "#ff7f0e"
    - "#2ca02c"
    - "#d62728"
  yoy:
    current_year_style:
      line:
        dash: "solid"
        width: 3
    previous_year_style:
      line:
        dash: "dash"
        width: 2
  layout:
    template: "plotly_white"
    margin:
      l: 50
      r: 50
      t: 50
      b: 50

# CORS origins
cors_origins:
  - "https://example.com"
  - "https://app.example.com"
```

## Creating the Database

```bash
# Via psql
set "PGPASSWORD=1234" & psql -h localhost -p 5432 -U postgres -c "CREATE DATABASE bidb;"
```

**Note:** Use Alembic migrations for schema setup:
```bash
uv run alembic upgrade head
```

## Running the Application

### Quick Start (Development)

```bash
uv run uvicorn src.mkobi.main:app --reload
```

The application will be available at: http://127.0.0.1:8010

### Logs on Successful Startup

```
INFO:     Will watch for changes in these directories: ['C:\\py_dev\\mkobi']
INFO:     Uvicorn running on http://127.0.0.1:8010 (Press CTRL+C to quit)
INFO:     Started reloader process [21368] using StatReload
Configuring CORS with allowed origins: [...]
Starting database initialization for ENV=development
Database exists and is accessible
Database initialization completed
```

## Accessing the Application

After starting, the React SPA will be available at:
- **Root/Login**: http://localhost:8010/
- **Dashboards list**: http://localhost:8010/dashboards
- **Specific dashboard**: http://localhost:8010/dashboard/{dashboard_id}
- **Admin panel**: http://localhost:8010/admin
- **Profile**: http://localhost:8010/profile

> In development, the React dev server runs separately on http://localhost:5173 and proxies API requests to FastAPI over the Docker network at container port 8000. The Docker dev app is published on host port **8010** (`${APP_HOST_PORT:-8010}`). See [Deployment](../10-deployment/deployment.md) for details.

> **Development Login:** Use `admin@example.com` / `admin@example.com` to log in to the development environment. Weak passwords are allowed in development mode only — production rejects known weak password values.

## Health Checks

### API Endpoints

```bash
# Health check
curl http://localhost:8010/health

# API Documentation
# Swagger UI: http://localhost:8010/docs
# ReDoc: http://localhost:8010/redoc
```

### Testing

`.\Makefile.ps1` is the authority for every gate command. The suite runs inside
the `mkobi-test` Compose project and is not a host command; the `lint` and
`typecheck` targets run in the dev `app` container. The commands below are the
gates the project actually executes, and each was run to confirm it behaves as
documented.

```bash
# Full suite (invoked as a bare `pytest`; see the coverage note below)
.\Makefile.ps1 test

# Full suite with the live coverage gate (the only place --cov is passed)
.\Makefile.ps1 test-all

# Forward arguments to pytest verbatim (run `.\Makefile.ps1 test-up` first)
.\Makefile.ps1 test-select tests/test_dashboards_api.py -v

# Code style check (Invoke-Lint: ruff check src/ tests/ alembic/env.py)
.\Makefile.ps1 lint

# Type checking (Invoke-Typecheck: mypy src/ alembic/env.py)
.\Makefile.ps1 typecheck
```

The bare-host spellings these targets wrap are:

- lint → `uv run ruff check src/ tests/ alembic/env.py`
- typecheck → `uv run mypy src/ alembic/env.py`

Both scopes matter and neither may be narrowed. `ruff check .` scans the whole
tree, including the historical `alembic/versions/` files the gate deliberately
excludes, and fails on them; `mypy src/mkobi/` drops `alembic/env.py`, which the
gate includes.

#### Coverage floor

The coverage floor is **inert on `test` and live on `test-all`**. `pyproject.toml`
puts `--cov-fail-under=65` in `[tool.pytest.ini_options] addopts` but passes **no
`--cov`**; the source is declared only under `[tool.coverage.run] source =
["src/mkobi"]` with `[tool.coverage.report] fail_under = 65` restating the floor.
`pytest-cov` (7.1.0) registers its plugin only when `cov_source` is set, so a
bare `pytest` run measures nothing and enforces no threshold, while `test-all`
supplies `--cov=src/mkobi` and makes the 65% floor bite.

#### mypy override note

`pyproject.toml` carries `[[tool.mypy.overrides]] module = ["tests.*"]`, and mypy
prints `pyproject.toml: note: unused section(s): module = ['tests.*']` on every
run. It is inert because every invocation the project runs is scoped to `src/`
(plus `alembic/env.py`) — `tests/` is never type-checked, so no module can match
the override. It is **not** shadowed by `mkobi.*`; a `mkobi.*` pattern cannot
match a `tests.*` module at all. The override is left in place because
`warn_unused_ignores` would object if it were removed.

## Troubleshooting

### PostgreSQL Connection Error

**Solution**: Check that PostgreSQL is running:
```bash
pg_isready -h localhost -p 5432
```

### Error: "database 'bidb' does not exist"

**Solution**: Create the database (see "Creating the Database" section).

### Migration Error

**Solution**: Ensure `auto_migrate: true` in `app.yaml` or run migrations manually:
```bash
uv run alembic upgrade head
```

## Configuration Structure

Configuration is stored in: `src/mkobi/settings/app.yaml`

Pydantic-settings reads settings from the YAML file. For sensitive data (passwords), it is recommended to use environment variables, overriding values from YAML.

## Additional Commands

### Database Migrations (Manual)

```bash
# Apply migrations
uv run alembic upgrade head

# Create new migration
uv run alembic revision --autogenerate -m "description"

# Rollback migration
uv run alembic downgrade -1

# Detect schema drift (recommended path: hermetic test DB, not the dev DB)
.\Makefile.ps1 migration-check

# The equivalent bare-host invocation is NOT equivalent: with no sqlalchemy.url
# in alembic.ini it resolves to the dev database (bidb), and it can create
# alembic_version and then falsely pass against an unmigrated database.
# uv run alembic check
```

### Recreating Test Database

Set in `app.yaml`:
```yaml
test_database_url: "postgresql+asyncpg://postgres:1234@localhost:5432/bidb_test"
recreate_test_db: true
```

Then run:
```bash
uv run python -m mkobi.db.starter --recreate-test-db
```
