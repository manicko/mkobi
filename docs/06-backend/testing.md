---
id: testing
domain: backend
tags:
  - pytest
  - async-testing
  - fixtures
  - test-database
  - coverage
  - mocking
related:
  - backend-architecture
  - configuration
  - logging
---

# Testing

## Purpose

This document describes how the mkobi test suite is structured and run: the
pytest configuration, the `tests/` layout, the shared fixtures in `conftest.py`,
the test database model and the coverage areas. It is the reference for adding
tests and for understanding what the fixtures guarantee and what they do not.

## Overview

The project uses **pytest** as its testing framework with async support via `pytest-asyncio`. Tests cover API endpoints, business logic services, data processing, authentication, configuration, and Pydantic model validation.

**Test directory:** `tests/`

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures (DB, auth, Redis mock)
├── test_auth.py             # Auth API endpoint tests
├── test_auth_service.py     # AuthService unit tests
├── test_config.py           # Configuration loading tests
├── test_dashboards_api.py   # Dashboard API endpoint tests
├── test_data_service.py     # DataService unit tests
├── test_filters.py          # Filter API tests
├── test_graph_service.py    # GraphService unit tests
├── test_graphs.py           # Graph API tests
├── test_layouts.py          # Layout API tests
├── test_processing_logs.py  # Processing log tests
├── test_pydantic_models.py  # Pydantic model validation tests
├── test_repositories.py     # Repository layer tests
├── test_security.py         # Security utility tests
├── test_storage_manager.py  # File storage tests
├── test_upload_api.py       # Upload API endpoint tests
└── test_users_api.py        # User management API tests
```

## Test Categories

### API Tests

Test HTTP endpoints using `httpx.AsyncClient` with FastAPI's `ASGITransport`:

- **Fixtures:** `async_client` provides an in-memory HTTP client; `authenticated_client` adds JWT auth headers
- **Database:** Uses the same test session. Its SAVEPOINT rollback isolates only work that stayed inside the SAVEPOINT — see [Database Isolation](#database-isolation)
- **Coverage:** Request validation, authentication, authorization, response schemas, error handling

### Service Tests

Test business logic in isolation using mocked repositories:

- **Pattern:** `unittest.mock.AsyncMock` for all repository dependencies
- **Coverage:** Business rules, data transformation, error conditions, edge cases
- **Examples:** `test_auth_service.py`, `test_data_service.py`, `test_graph_service.py`

### Configuration Tests

Test the multi-source configuration loading:

- Environment variable parsing
- Docker secrets (`_FILE` suffix)
- `.env` file loading
- YAML config loading
- Source priority validation
- Production credential enforcement

### Model Tests

Test Pydantic model validation:

- Field constraints and validators
- StrEnum value serialization
- Custom validators (e.g., CORS origins, admin credentials)

## Test Fixtures

Defined in `conftest.py`:

| Fixture              | Scope     | Description                                      |
| -------------------- | --------- | ------------------------------------------------ |
| `_reset_config_cache` | function  | Autouse; clears the settings singleton before each test and rebuilds it after teardown |
| `_auto_mock_redis`   | function  | Auto-mocks Redis for all tests (rate limiting bypassed) |
| `mock_redis`         | function  | Opt-in Redis mock that bypasses rate limiting    |
| `strict_redis`       | function  | In-memory Redis mock with real rate limiting     |
| `setup_test_database` | session  | Recreates, migrates and finally drops **this run's** test database. **Not autouse** — declared by name, see [The Fixture Is Declared, Not Forced](#the-fixture-is-declared-not-forced) |
| `async_test_engine`  | session   | Async SQLAlchemy engine with NullPool            |
| `async_session_maker` | session  | Async session factory                            |
| `async_db_session`   | function  | Per-test session; rolls back its SAVEPOINT, but not rows a test commits |
| `async_client`       | function  | httpx AsyncClient with overridden DB dependency  |
| `authenticated_client` | function | HTTP client with JWT auth headers               |
| `test_user`          | function  | Creates a test user and returns token            |
| `auth_headers`       | function  | Returns `{"Authorization": "Bearer <token>"}`    |

## Test Database

Every pytest process resolves **its own** database name, so two runs on one machine
never share a database and cannot destroy each other's work.

| Property       | Value                                                                                 |
| -------------- | ------------------------------------------------------------------------------------- |
| Name           | `bidb_test_<run token><worker id>`, resolved once per process                          |
| Run token      | `MKOBI_TEST_RUN_ID` when the caller sets it, otherwise `uuid4().hex[:8]`              |
| Worker id      | The pytest-xdist worker id (`gw0`, …) with its leading underscore stripped and **concatenated into the same token** |
| Created        | When `setup_test_database` runs: terminate this name's backends, drop, create, apply the Alembic chain |
| Dropped        | At session end, guarded so that only a process which created the database can drop it |
| Connection     | `localhost:5434` by default — the `test-db` container's published host port            |
| Engine         | `NullPool`, to prevent connection pooling issues in tests                              |
| Server         | The test compose still provisions a bare `bidb_test` as `POSTGRES_DB`. That is what `test-migrate` targets, not what a test run uses |

### Where the Name Comes From

`_compute_test_db_name()` in `tests/conftest.py` runs at **module import, before any
`mkobi` module is imported**. The ordering is load-bearing: `TEST_ASYNC_DB_URL` is a
module-level constant built from the memoised `get_config()` singleton, so
`DATABASE__DBNAME` and `DATABASE__TEST_DBNAME` must already be in `os.environ` when the
first `mkobi` import happens. `pytest_load_initial_conftests` then re-applies the same
values; it reuses the name resolved at import, because recomputing would mint a second
token and silently break per-run isolation.

Every other variable the test process needs is applied with `os.environ.setdefault`, so
Compose values still win inside the container. The two database names are the
exception: they are assigned **unconditionally**, overriding the `bidb_test` that
`docker/docker-compose.test.yml` hardcodes on `test-app`. A `setdefault` there would
always lose and every run would land on the same database. Both are set because the
database URL the health tests use is built from `DATABASE__DBNAME`.

### The Worker Segment

`pytest-xdist` is a declared dev dependency, but nothing passes `-n`, so
`PYTEST_XDIST_WORKER` is unset and **the worker segment is empty in every run today**.
The branch exists for when parallel execution is enabled. It concatenates into the
single token rather than appending a second `_`-separated segment, on purpose: the
starter's guard (`TEST_DATABASE_NAME_PATTERN = ^bidb_test(_[A-Za-z0-9]+)?$`) accepts
exactly one optional suffix segment, so a two-segment name such as
`bidb_test_<token>_gw0` would be refused.

### Recreation and the Session-End Drop

`setup_test_database` requests `recreate_test_database()` against this run's name. The
starter terminates connections to that name, drops it, recreates it and applies the
Alembic chain. Because the name is per-run, the sequence cannot terminate another
process's connections or drop another process's database — which is precisely what it
used to do when every process resolved the same `bidb_test`.

The teardown in `pytest_sessionfinish` drops the same name over the same admin
connection path, and it is **guarded**: the module-level `_test_db_created` flag is set
only inside `setup_test_database`, that is, only when this process actually created the
database. A process that created nothing — a pytest-xdist controller, or a session whose
selected modules never requested a live database — cannot trigger a drop. A failed drop
is logged and swallowed, so it can never fail the session.

### `MKOBI_TEST_RUN_ID` Is a Foot-Gun

Set the variable only to make a run's database name predictable, and never give two
concurrent runs the same value. Two runs sharing a token target one database and are
**mutually destructive**: the first to finish drops the database the second is still
using. The teardown guard proves that *this process created* the database, not that this
process is its only user, so it cannot catch this case. Distinct tokens are the default —
a fresh `uuid4().hex[:8]` per run already supplies them.

A caller-supplied token is passed through **unsanitised**, deliberately. It has to
clear the starter's name gate, and one that does not is refused loudly rather than
silently repaired:

```
UnsafeTestDatabaseRecreationError: Refusing to recreate database
'bidb_test_x"; DROP DATABASE bidb_test; --': name does not match the
test-database convention '^bidb_test(_[A-Za-z0-9]+)?$'.
```

That gate is production code and per-run naming did not change it: it is a safety
interlock that refuses to recreate any database whose name is not clearly a test
database, whoever asked for the recreation. See
[Architecture](architecture.md) for where it sits in startup.

### Isolation and Migrations

- **SAVEPOINT pattern** — the fixture rolls back its nested transaction when the test
  ends, which undoes only work that stayed inside it. `Session.commit()` commits the
  session's **root** transaction, so rows a test commits survive the rollback and stay
  visible to later tests; cross-test cleanup is the test's own responsibility (see
  [Database Isolation](#database-isolation))
- **Migrations** — the Alembic chain is applied to this run's database during session
  setup, by `conftest`, not by the `test-migrate` service (see
  [Docker Guide](../11-guides/docker.md#testing))

### The Fixture Is Declared, Not Forced

`setup_test_database` is **not** `autouse`. The modules and fixtures that need a live
database request it by name, and nothing else pays for it. A pure-unit selection
therefore creates no database at all: `uv run pytest tests/test_validators.py` emits no
database-creation log line and never opens a connection. `tests/test_health.py` requests
the fixture explicitly because `/health` reports a database component whose status it
asserts.

## Running Tests

On the host, with the test stack up (see the constraints below):

```bash
# Full suite
uv run pytest tests/

# Specific test file
uv run pytest tests/test_auth_service.py

# Verbose output
uv run pytest tests/ -v

# Specific test class
uv run pytest tests/test_auth_service.py::TestAuthService
```

The same selections go inside the container through `.\Makefile.ps1 test-select <args>`,
which forwards every argument after the target name to `pytest` unchanged.

The canonical gate is `.\Makefile.ps1 test`, and it runs the suite inside the
`test-app` container. That service bind-mounts `src/`, `tests/` and `docker/` from
the working tree — so the gate grades the files you just edited and a test-side change
is graded without an image rebuild. The mounts are writes-through: any stray artefact a
test leaves behind in `src/` or `tests/` can appear on the host. See
[Docker Guide](../11-guides/docker.md#testing) for the stack.

A host-side `uv run pytest` is no longer excluded for safety reasons: each process
owns its own test database, so a host run and a container run — or two host runs — can
no longer drop each other's database. It is still not the gate, and it is not available
for every module:

- The test stack must be up (`.\Makefile.ps1 test-up`), because `tests/conftest.py`
  points a host run at the `test-db` container's published port, `localhost:5434`.
- The test image installs `libmagic1`, which the Windows host does not have, so any
  module whose import graph reaches `src/mkobi/services/file_processing.py` (which
  imports `magic`) fails at collection with
  `ImportError: failed to find libmagic`. Modules that do not reach it run on the host,
  database-backed ones included.

## Coverage Areas

| Area          | Description                                              |
| ------------- | -------------------------------------------------------- |
| **API**       | All endpoint handlers, request validation, auth, errors  |
| **Processing**| Data upload, parsing (Polars), transformation, aggregation |
| **Auth**      | Login, registration, JWT creation/verification, password change |
| **Config**    | Settings loading from all sources, priority, validation  |
| **Security**  | Password hashing, token creation, rate limiting          |
| **Models**    | Pydantic model validation, StrEnum serialization         |
| **Repositories** | Data access layer, query correctness                  |

## Key Patterns

### Async Tests

All async tests use `pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
class TestAuthService:
    async def test_login_success(self, auth_service):
        result = await auth_service.login("user@example.com", "password")
        assert result is not None
```

### Mocking

Repositories and external services are mocked at the service layer:

```python
@pytest.fixture
def mock_user_repo():
    mock = AsyncMock()
    mock.get_by_email.return_value = None
    return mock
```

### Settings Cache

`mkobi.config` memoises `Settings` in a module-level `_settings`, and
`clear_config_cache()` is its only reset. The autouse `_reset_config_cache`
fixture clears that cache before every test and rebuilds it after the test's
environment changes have been undone, so a test that mutates `os.environ` cannot
leak its configuration — including a foreign `JWT__SECRET_KEY` — into the next
one, whatever the execution order.

The manual `clear_config_cache()` calls inside tests are load-bearing, not
redundant: a test that changes the environment and then reads configuration
mid-test needs the cache cleared *before* that read, and teardown runs after it.

### Database Isolation

Tests that need database access use the `async_db_session` fixture, which opens a
nested transaction (SAVEPOINT) and rolls it back when the test ends:

```python
async def test_create_user(async_db_session, test_user):
    # test_user is created inside the fixture's SAVEPOINT
    assert test_user["email"].endswith("@example.com")
```

**This is not full per-test isolation.** `Session.commit()` inside a test commits
the session's *root* transaction, and the fixture's SAVEPOINT rollback does not
undo it. A committed row persists in the test database and is visible to every
later test. A test that commits rows is therefore responsible for deleting them
before it ends: the compensating `delete(...)` blocks shipped in such tests are
load-bearing, not redundant, and must not be removed.

A test that needs to observe or shape **global** state scopes its reads and writes to
the rows it owns instead of clearing a shared table, because a committed delete is a
row the rest of the session can no longer find. `tests/test_users_api.py::TestDeleteAccount::test_admin_cannot_delete_self`
is the reference: the production guard reads the whole `users` table, so the test
deletes only *foreign* `ADMIN` rows and deliberately does **not** commit them — the
request shares the session, so the guard sees the pending deletes, and the fixture's
SAVEPOINT rollback restores those rows for every later test. It asserts its own state
by selecting the uuid-suffixed addresses it created, never a global row count.

## Cross-References

- [Backend Architecture](architecture.md) — System architecture and layer responsibilities
- [Configuration](configuration.md) — Test configuration via environment variables
- [Logging](logging.md) — Log output during test runs
- [Database Schema](../09-database/schema-core.md) — Test database structure and migrations
