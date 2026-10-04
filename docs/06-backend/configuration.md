---
id: configuration
domain: backend
tags:
  - configuration
  - pydantic-settings
  - secrets
  - environment-variables
  - docker-secrets
  - production-security
related:
  - backend-architecture
  - logging
  - security-overview
  - deployment
---

# Configuration

## Purpose

This document describes how the application loads configuration: the multi-source
priority order exposed by `Settings`, the environment-variable contract, Docker
secrets support, production credential enforcement and the settings singleton. It
is the reference for adding or changing a setting and for understanding startup
validation.

## Overview

The application uses **pydantic-settings** for configuration management with a multi-source priority system. All configuration is loaded into a singleton `Settings` instance via `get_config()`.

**Implementation:** `src/mkobi/config.py`

See [Backend Architecture](architecture.md) for the startup lifecycle and how configuration is loaded during initialization. See [Deployment](../10-deployment/deployment.md) for Docker secrets and production environment setup.

## Config Source Priority

Settings are loaded from multiple sources. The first matching value wins:

| Priority | Source                                      | Description                                    |
| -------- | ------------------------------------------- | ---------------------------------------------- |
| 1 (highest) | **Environment variables**                | `DATABASE__PASSWORD`, `JWT__SECRET_KEY`, etc.  |
| 2        | **Docker secrets files** (`_FILE` suffix)   | `DATABASE__PASSWORD_FILE=/run/secrets/db_password` |
| 3        | **`.env` file**                             | Development convenience via pydantic-settings  |
| 4        | **`app.yaml`**                              | `cors_origins`, `app.name`, hosts, ports, paths. It does **not** set `app.version`: that value has one source, the installed distribution, resolved in code and overridable through `APP__VERSION`. |
| 5 (lowest) | **Code defaults**                         | Field defaults in `Settings` class             |

This is implemented via `Settings.settings_customise_sources()` which returns sources in priority order.

`app.yaml` contributes `cors_origins` — `http://localhost:3000` and
`http://localhost:5173` — above the field default of an empty list. It also supplies
`app.name`, the application's displayed name.

It is **not** the owner of the application's version. `app.version` has exactly one
source: the installed distribution's declared version, resolved by
`config.py::distribution_version()` and overridable through `APP__VERSION`. The
`app.yaml` file deliberately carries **no** `version` key, because a YAML value
outranks the code default and would pin the advertised version independently of the
distribution — the exact drift that left the published document seven patch releases
behind `pyproject.toml`.

It carries **no key that sets the environment tier**. The lowercase `env` key it used
to carry resolved to nothing, and the reason is not case-sensitivity:
`Settings.environment` declares `alias="ENV"` while `model_config` does **not** set
`populate_by_name`, so `env` is not an accepted name for the field at all. The key
was passed through unrenamed and dropped by `extra="ignore"`.
`Settings.model_config["case_sensitive"]` is `False`, and that flag governs the
environment-variable and `.env` sources, not the YAML one. An uppercase `ENV` key in
`app.yaml` **would** in fact take effect, but the YAML source ranks below the
environment and `.env` sources, so the supported way to select the tier is the `ENV`
environment variable.

## Environment Variables

All environment variables use the double-underscore (`__`) delimiter for nesting:

| Variable                      | Nested Path              | Default        | Description                     |
| ----------------------------- | ------------------------ | -------------- | ------------------------------- |
| `ENV`                         | `environment`            | `development`  | Application environment         |
| `APP__NAME`                   | `app.name`               | `mkobi`        | The application's displayed name, transferred to the FastAPI title. `app.yaml` supplies it; the environment variable overrides it. |
| `APP__VERSION`                | `app.version`            | the installed distribution's declared version | The advertised API version, transferred to the FastAPI version and published as the schema document's `info.version`. The default is **not** a literal: it is resolved from the installed distribution's metadata (`config.py::distribution_version()`), so the document and `pyproject.toml` cannot drift — the seven-patch-releases-stale `1.0.0` is exactly the staleness this removes. Setting the variable overrides the derived value, which the settings precedence guarantees and a test proves. `app.yaml` deliberately carries **no** `version` key: a YAML literal would outrank this default and leave the document stale again. If the distribution is not installed, resolution raises rather than falling back to a literal, because a fallback would re-create the hand-written value. |
| `DATABASE__HOST`              | `database.host`          | `localhost`    | PostgreSQL host                 |
| `DATABASE__PORT`              | `database.port`          | `5432`         | PostgreSQL port                 |
| `DATABASE__DBNAME`            | `database.dbname`        | `bidb`         | Main database name              |
| `DATABASE__USER`              | `database.user`          | `mkobi_app`    | Database user                   |
| `DATABASE__PASSWORD`          | `database.password`      | `None`         | Database password (secret)      |
| `DATABASE__TEST_DBNAME`       | `database.test_dbname`   | `bidb_test`    | Test database name              |
| `DATABASE__LOCK_TIMEOUT_MS`   | `database.lock_timeout_ms` | `180000`     | Bound on the aggregate-rebuild advisory-lock wait (ms). `0` means **unbounded** (PostgreSQL's own sentinel — a wedged holder then holds a pooled connection indefinitely). PostgreSQL has no per-lock timeout, so the bound applies to **every lock wait in the worker's transaction**, not only the advisory one; keep it well below `STALE_PROCESSING_TIMEOUT_MINUTES`. Applied per transaction with `set_config(…, true)`, so it does not survive the commit on a pooled connection. See [Architecture](architecture.md#aggregate-rebuild-exclusion). |
| `DATABASE__POOL_SIZE`         | `database.pool_size`     | `10`           | Application engine pool size. `0` is SQLAlchemy's unbounded sentinel and is refused — it removes the cap **and discards `max_overflow`**; use `NullPool` for no pooling. |
| `DATABASE__MAX_OVERFLOW`      | `database.max_overflow`  | `20`           | Extra connections above `pool_size`. `0` is legitimate (a strict cap) and is **not** refused. |
| `DATABASE__POOL_TIMEOUT`      | `database.pool_timeout`  | `30`           | Seconds to wait for a pooled connection. `0` means **fail immediately, never queue** — not "wait forever" — so it is refused; every burst would become an instant 500. |
| `DATABASE__POOL_RECYCLE`      | `database.pool_recycle`  | `-1`           | Connection recycle age in seconds. `-1` means **no recycle**. Recommended production value is `300` (see [Architecture](architecture.md)); the sizing decision is not yet taken. |
| `DATABASE__APPLICATION_NAME`  | `database.application_name` | `mkobi-app` | The PostgreSQL `application_name` attached to every pool connection, so per-application `pg_stat_activity` breakdowns attribute connections. |
| `DATA__MAX_ROWS_PER_GRAPH`    | `data.max_rows_per_graph` | `2000` | Rows returned for one graph in one dashboard aggregate response. The read path allocates roughly 3,402 B/row and its linear memory curve crosses the 1 GiB application limit between 250k and 300k rows, so the read is capped. `ge=0`. |
| `DATA__MAX_ROWS_TOTAL`        | `data.max_rows_total`   | `20000` | Rows returned across the whole dashboard aggregate response. **Derivation:** 20,000 rows × 3,402 B/row ≈ **68 MB**, leaving comfortable headroom inside the 1 GiB application limit while `--workers 4` serve concurrently. Truncation is visible: the true counts travel alongside the bounded rows in the response. `ge=0`. |
| `JWT__SECRET_KEY`             | `jwt.secret_key`         | `None`         | JWT signing key (secret)        |
| `JWT__ALGORITHM`              | `jwt.algorithm`          | `HS256`        | JWT signing algorithm           |
| `JWT__ACCESS_TOKEN_EXPIRE_MINUTES` | `jwt.access_token_expire_minutes` | `15` | Token TTL      |
| `REDIS__HOST`                 | `redis.host`             | `localhost`    | Redis host                      |
| `REDIS__PORT`                 | `redis.port`             | `6379`         | Redis port                      |
| `REDIS__DB`                   | `redis.db`               | `0`            | Redis logical database index. Honoured in `.env.example`, compose and `settings/app.yaml`; this row closes a pre-existing documentation gap and is not part of the transport bound below. |
| `REDIS__SOCKET_TIMEOUT_SECONDS` | `redis.socket_timeout_seconds` | `1.0` | Bound in seconds on a single socket *read*. Without it the transport inherits the library's undeclared default — `socket_timeout=5` with a ten-retry backoff, i.e. eleven 5-second attempts, roughly 59 s, per request during an outage. `1.0 s` sits strictly below the reconciler lease's existing `2.0 s` `asyncio.wait_for` ceiling, so this inner socket bound is the one that fires, and it is far above normal in-subnet latency, so ordinary load is not reported as an outage. `gt=0`, `le=60`. |
| `REDIS__SOCKET_CONNECT_TIMEOUT_SECONDS` | `redis.socket_connect_timeout_seconds` | `1.0` | Bound in seconds on a single socket *connect*. Set independently of the read bound: a value of `None` would silently inherit `socket_timeout`, coupling the two into one number, so both are always passed explicitly. `gt=0`, `le=60`. |
| `ADMIN_USERNAME`              | `admin_username`         | `admin`        | Admin user email                |
| `ADMIN_PASSWORD`              | `admin_password`         | `CHANGE_ME_ADMIN_PASSWORD` | Admin user password (secret)    |
| `AUTO_MIGRATE`                | `auto_migrate`           | `false`        | Auto-apply Alembic migrations   |
| `RECREATE_TEST_DB`            | `recreate_test_db`       | `false`        | Recreate test DB on startup. Set to `true` in test environment for automatic test database recreation. |
| `STALE_FILE_THRESHOLD_HOURS`  | `stale_file_threshold_hours` | `24`      | Temp file cleanup threshold     |
| `STALE_PROCESSING_TIMEOUT_MINUTES` | `stale_processing_timeout_minutes` | `30` | **The one stale horizon.** Ages a processing log past which "this job is stuck" is asserted, shared by the boot-time `UPLOADED` marker and the periodic `PROCESSING` sweep. It bounds time to *first report*, not job lifetime: a legitimately long rebuild can be flipped to `FAILED` at the horizon and later overwritten back to `COMPLETED` by the worker's own commit. See [Architecture](architecture.md#stale-processing-log-cleanup). |
| `RATE_LIMITER_FAIL_CLOSED`    | `rate_limiter_fail_closed` | `true`      | Fail-closed on Redis outage     |
| `CORS_ORIGINS`                | `cors_origins`           | `["http://localhost:3000", "http://localhost:5173"]` | Allowed CORS origins (from `app.yaml`) |
| `TEMP_PASSWORD_TTL_SECONDS`   | `temp_password_ttl_seconds` | `86400`     | Temp password Redis TTL (min 60s) |
| `FRONTEND__DIST_DIR`          | `frontend.dist_dir`    | `frontend/dist` | Location of the built SPA bundle. The **single** configured source for both the static mount and the `static_files` component of `/health/detailed`: it is resolved to an absolute path once, and both read the one availability predicate, so the route table and the health verdict cannot disagree. The bundle counts as available only when the directory exists **and** carries an `index.html` — a `dist` directory without one is reported `unavailable` and is not mounted. Container `HEALTHCHECK` is unchanged. |

> **Hand-over `HO-9` — two Redis transport paths are still undeclared (owned by phase 01).** The
> socket bounds above are declared on `RedisSettings` and are applied by the shared factories in
> `core/redis_client.py`. They do **not** reach the two places that build their own client instead
> of using those factories, so "the Redis transport is bounded" is true of the shared factories only:
>
> - `src/mkobi/rq_worker_wrapper.py` constructs clients with `redis.Redis.from_url(...)` at three
>   sites — `check_redis_connection`, `check_worker_registered` and `start_rq_worker`'s `rq.Queue` —
>   with no `socket_timeout` and no pinned retry. It therefore inherits the library default *and*
>   wraps it in its own `MAX_RETRIES = 3` loop, so its worst case is roughly 165 s, not the ~59 s the
>   undeclared default produces on its own. Its **failure direction** is declared (3 attempts, then
>   `ConnectionError` and exit); its **transport bound** is not.
> - `src/mkobi/core/task_queue.py::get_rq_queue` is `functools.cache`d, has live callers on the
>   upload enqueue path, and builds `redis.Redis(host=..., port=..., db=..., password=...)` with
>   neither a timeout nor a pinned retry. Neither bound above reaches it.
>
> Both are phase 01's surface (the rq-worker and dependency/queue topology), so neither is corrected
> here. Any statement elsewhere that a Redis operation is bounded must be read as bounded **through
> `core/redis_client.py`**.

## Secrets Management

### Docker Secrets Support

The application supports Docker secrets through the `_FILE` suffix pattern:

```bash
# Instead of passing the secret directly:
DATABASE__PASSWORD=supersecret

# Point to a file containing the secret:
DATABASE__PASSWORD_FILE=/run/secrets/db_password
```

The custom `SecretsFileSource` class honours a `*_FILE` variable **only when the base
name — the part before the suffix — is a declared secret-bearing field**. The honoured
set is derived from `SECRET_FIELD_REGISTRY` in `config.py` rather than hard-coded, and
is exactly these five names:

| Honoured variable          | Field it populates      |
| -------------------------- | ----------------------- |
| `DATABASE__PASSWORD_FILE`  | `database.password`     |
| `DATABASE__ADMIN_USER_FILE` | `database.admin_user`  |
| `DATABASE__ADMIN_PASSWORD_FILE` | `database.admin_password` |
| `JWT__SECRET_KEY_FILE`     | `jwt.secret_key`        |
| `REDIS__PASSWORD_FILE`     | `redis.password`        |

Every other `*_FILE` variable is skipped without the file being read. A name that
resolves to a real but non-secret field is **ignored with a warning** naming the
variable and the field (never the value); a name that resolves to no field at all —
`LOGGING__LOG_FILE`, which strips to `LOGGING__LOG`, addressing nothing — is skipped
at debug level. So a path-valued or list-valued setting is not read as a secret
pointer.

> **Per-process log file default removed.** No compose service sets
> `LOGGING__LOG_FILE` anymore. It used to be set for `app` and `rq-worker`, so
> four processes each opened one rotating handler against the same file
> (`4 writers x 6 files x 10 MB ~= 240 MB`). The setting still works when an
> operator supplies it explicitly in `.env`; it is simply no longer set for
> everyone. See [Logging](logging.md) for the rotation arithmetic.

> **Behaviour change.** Only the five names in the table above are honoured. A
> `*_FILE` variable naming a real but non-secret field, for example
> `DATABASE__USER_FILE`, used to be applied and is now ignored with a warning. The
> risk this removes is silent fallback: where no `DATABASE__USER` environment
> variable is supplied, the field would have fallen through to the next source down,
> which is `app.yaml`'s `postgres` — the **superuser** role — so a mis-set `*_FILE`
> could quietly downgrade the runtime connection.

Note the **double underscore** in the last row. `redis` is a nested model, so the
single-underscore spelling `REDIS_PASSWORD_FILE` addresses no field and has never been
honoured.

### Secrets in Code

- Secrets are **never logged** — the `_log_initialization()` method logs only non-sensitive settings
- Secrets are **never stored in `app.yaml`** — the YAML file contains only non-sensitive configuration
- The `extra="ignore"` model config prevents unknown fields from being stored

## Production Credential Enforcement

The application **refuses to start in production** if known-weak credentials are
detected. Every guard below is gated on the resolved tier being `production`; outside
production the same values are permitted and only a warning is logged.

The base compose file (`docker/docker-compose.yml`) pins `ENV: production` as a
literal for `migrate`, `app` and `rq-worker`, so an env file cannot downgrade the tier
and these guards cannot be switched off that way. Only the development override
(`docker/docker-compose.override.yml`) declares a different tier.

### Admin Credentials

`Settings.validate_admin_credentials()` refuses an admin username or password that is:

- an **exact, case-insensitive member** of `WEAK_USERNAMES` / `WEAK_PASSWORDS`;
- carrying the **case-insensitive `change_me` prefix** — the shape every shipped
  `CHANGE_ME_*` template value takes, which exact membership alone misses;
- **empty or whitespace-only**;
- a password **shorter than 8 characters**.

The predicates live in `config.py` as `is_weak_admin_username()` and
`is_weak_admin_password()`, and the bootstrap path in
`DatabaseStarter.ensure_admin_user()` now calls the same two functions, so the two
copies cannot drift apart. They do **not** behave identically, by design: they share
the predicate and the production tier condition, but the action differs.

| Value | `Settings.validate_admin_credentials()` | `DatabaseStarter.ensure_admin_user()` |
| --- | --- | --- |
| Weak **password**, production tier | **Raises** `ValueError` | **Raises** `ValueError` |
| Weak password, any other tier | Warns (exact weak member only) | Warns (full predicate) |
| Weak **username**, production tier | **Raises** `ValueError` | **Warns** and proceeds |
| Weak username, any other tier | Warns (exact weak member only) | Warns (full predicate) |

The username asymmetry is deliberate: the configuration guard has already refused an
unusable username by the time the starter runs, so the starter's check is a backstop
that must never be the thing that stops a legitimate bootstrap. The password is
re-raised at the point of use because the hash is written there. Outside production
the two differ only in breadth, not in severity — the settings guard's non-production
warning covers exact weak members, while the starter applies the full composite
predicate and so also warns on a `change_me` prefix, an empty value or a short one.

The messages below come from `Settings.validate_admin_credentials`. Neither
interpolates the rejected value:

| Value | Message |
| --- | --- |
| Username is an exact weak member | `Admin username is too common. Please choose a more secure username.` |
| Username is a placeholder or empty | `Admin username is unset or still a shipped placeholder value. Set ADMIN_USERNAME to a real, unique username.` |
| Password is an exact weak member | `Admin password is too common. Please choose a more secure password.` |
| Password carries the `change_me` prefix | `Admin password is a known placeholder value. Set ADMIN_PASSWORD to a strong, unique password.` |
| Password is empty after strip | `Admin password must not be empty. Set ADMIN_PASSWORD to a strong, unique password.` |
| Password is shorter than 8 characters | `Admin password is too short. Please choose a stronger password.` |

**Required in production:**
- `ADMIN_USERNAME` must be explicitly set to a value outside `WEAK_USERNAMES`, with no
  `change_me` prefix and not empty
- `ADMIN_PASSWORD` must be explicitly set to a value at least 8 characters long that
  is neither a known weak value nor a `change_me` placeholder

In development, default credentials are permitted but a warning is logged.

### JWT Secret Key

- `JWT__SECRET_KEY` must be explicitly set in production; `JWTSettings.validate_secret_key`
  refuses any value shorter than 32 characters, and refuses an exact, case-insensitive
  member of `JWTSettings.WEAK_SECRETS`.
- `Settings.validate_production_credentials()` adds a production-only refusal for a
  `change_me` prefix on the same field.
- The base compose file uses `${JWT__SECRET_KEY:?...}`, which aborts interpolation when
  the variable is absent.

### Database Password

- `DATABASE__PASSWORD` must be explicitly set in production. `Settings.DATABASE_URL`
  raises when it is unset in production.
- `Settings.validate_production_credentials()` refuses an exact, case-insensitive member
  of `WEAK_PASSWORDS` and a `change_me` prefix. Outside production both are permitted and
  a warning is logged, which is what allows a convenient development database.
- **The name carries two roles in the base compose file.** On `db` and `migrate` it is the
  PostgreSQL **superuser** password (`POSTGRES_PASSWORD` and the migration connection).
  The least-privilege `mkobi_app` role's password is supplied as `MKOBI_APP_PASSWORD` and
  mapped onto `DATABASE__PASSWORD` for `app` and `rq-worker` only. See
  [Docker Guide](../11-guides/docker.md#required-variables).
- `${DATABASE__PASSWORD:?...}` is required by `db` and `migrate`; `app` and `rq-worker`
  require `${MKOBI_APP_PASSWORD:?...}` instead.
- **Where `mkobi_app`'s privileges come from depends on the tier.** The main
  (development and production) database is granted its schema, table and sequence
  privileges by the Docker init scripts under `docker/init-scripts/`, which run
  once when the PostgreSQL data volume is first initialised; nothing in the
  application grants them. The test database recreated by
  `db/starter.py::recreate_test_database` does not go through those scripts, so
  that function grants `mkobi_app` the equivalent set itself — the five grants are
  applied inside one explicit transaction, so a partial grant set cannot survive.
  The two sources are deliberately separate: init scripts own the main database,
  the starter owns the recreated test database, and neither grants on the other's
  behalf.

### CORS Origins

- `CORS_ORIGINS` must be explicitly configured in production
- The application validates CORS configuration at startup and raises an error if origins are not set in production mode
- `Settings.validate_cors_origins` refuses a `"*"` wildcard outright in production, naming the wildcard and how to remove it; in every other tier the wildcard and any non-`http(s)` entry are dropped with a warning
- `Settings.validate_cors_origins_not_placeholder` additionally refuses the known placeholder origins (`http://localhost:3000`, `http://localhost:5173`, `https://example.com`, `https://your-domain.com`) in production

### Temp Password TTL

- `TEMP_PASSWORD_TTL_SECONDS` controls the Redis TTL for temporarily stored passwords (default: `86400` = 24 hours)
- A Pydantic `field_validator` enforces a minimum value of `60` seconds
- Passwords are stored in Redis via `TempPasswordStore` and automatically expire after the configured TTL
- This setting affects both admin password reset and registration approval flows
- Passwords are also deleted immediately upon retrieval (single-use pattern)

## YAML Configuration

The `app.yaml` file (at `src/mkobi/settings/app.yaml`) contains only non-sensitive settings:

- Hosts and ports
- File paths
- Feature flags
- Default values

It is loaded via pydantic-settings `YamlConfigSettingsSource` and has lower priority than environment variables, Docker secrets, and `.env` files.

## Settings Singleton

Configuration is accessed through a module-level singleton:

```python
from mkobi.config import get_config

config = get_config()
```

The `get_config()` function uses a cached global `_settings` instance, ensuring a single configuration source throughout the application.

`clear_config_cache()` is that cache's only reset. In the test suite the autouse
`_reset_config_cache` fixture calls it around every test, so a test that mutates
`os.environ` cannot leave its configuration — or its `JWT__SECRET_KEY` — cached
for the next one; see [Settings Cache](testing.md#settings-cache).

## Key Properties

The `Settings` class exposes convenient properties that map to nested config values:

| Property              | Source Path                   | Description                    |
| --------------------- | ----------------------------- | ------------------------------ |
| `DATABASE_URL`        | `database.database_url`       | Full asyncpg connection URL    |
| `TEST_DATABASE_URL`   | `database.test_database_url`  | Test database connection URL   |
| `jwt_secret_key`      | `jwt.secret_key`              | JWT signing key                |
| `upload_temp_dir`     | `upload.temp_dir`             | Temp file directory            |
| `max_file_size`       | `upload.max_file_size_mb`     | Max upload size in bytes       |
| `allowed_file_types`  | `upload.allowed_extensions`   | Allowed file extensions        |
| `log_level`           | `logging.level`               | Logging level                  |

> `allowed_mime_types` was **removed** from this table and from `config.py`. The
> admitted MIME set is now declared in exactly one place — the three `MimeTypeEnum`
> members — with no configuration key able to widen or narrow it. The detector behind
> it (libmagic) is a hard startup dependency enforced by `main.check_dependencies` from
> the **app-required** set: `magic` is certified because the API entrypoint imports
> `mkobi.services.file_processing`, which imports it at boot. The verdict is therefore
> the image's rather than the host's. See
> [Processing API](../03-processing/processing-api.md) for what that changed.

## Cross-References

- [Backend Architecture](architecture.md) — System architecture and startup lifecycle
- [Logging](logging.md) — Logging configuration and standards
- [Security](../08-security/) — Security configuration details
- [Deployment](../10-deployment/deployment.md) — Production deployment and Docker Compose
- [Security Overview](../08-security/security-overview.md) — Production credential enforcement and secrets management
