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
| 4        | **`app.yaml`**                              | `cors_origins`, `app.name`/`app.version`, hosts, ports, paths |
| 5 (lowest) | **Code defaults**                         | Field defaults in `Settings` class             |

This is implemented via `Settings.settings_customise_sources()` which returns sources in priority order.

`app.yaml` contributes `cors_origins` — `http://localhost:3000` and
`http://localhost:5173` — above the field default of an empty list. It is also the
single owner of the application's displayed name and version through `app.name` and
`app.version`.

It carries **no key that sets the environment tier**. The lowercase `env` key it used
to carry resolved to nothing: `Settings.environment` declares `alias="ENV"` and the
YAML source matches case-sensitively, so the unrenamed key was dropped by
`extra="ignore"`. Set the tier with the `ENV` environment variable.

## Environment Variables

All environment variables use the double-underscore (`__`) delimiter for nesting:

| Variable                      | Nested Path              | Default        | Description                     |
| ----------------------------- | ------------------------ | -------------- | ------------------------------- |
| `ENV`                         | `environment`            | `development`  | Application environment         |
| `DATABASE__HOST`              | `database.host`          | `localhost`    | PostgreSQL host                 |
| `DATABASE__PORT`              | `database.port`          | `5432`         | PostgreSQL port                 |
| `DATABASE__DBNAME`            | `database.dbname`        | `bidb`         | Main database name              |
| `DATABASE__USER`              | `database.user`          | `mkobi_app`    | Database user                   |
| `DATABASE__PASSWORD`          | `database.password`      | `None`         | Database password (secret)      |
| `DATABASE__TEST_DBNAME`       | `database.test_dbname`   | `bidb_test`    | Test database name              |
| `JWT__SECRET_KEY`             | `jwt.secret_key`         | `None`         | JWT signing key (secret)        |
| `JWT__ALGORITHM`              | `jwt.algorithm`          | `HS256`        | JWT signing algorithm           |
| `JWT__ACCESS_TOKEN_EXPIRE_MINUTES` | `jwt.access_token_expire_minutes` | `15` | Token TTL      |
| `REDIS__HOST`                 | `redis.host`             | `localhost`    | Redis host                      |
| `REDIS__PORT`                 | `redis.port`             | `6379`         | Redis port                      |
| `ADMIN_USERNAME`              | `admin_username`         | `admin`        | Admin user email                |
| `ADMIN_PASSWORD`              | `admin_password`         | `CHANGE_ME_ADMIN_PASSWORD` | Admin user password (secret)    |
| `AUTO_MIGRATE`                | `auto_migrate`           | `false`        | Auto-apply Alembic migrations   |
| `RECREATE_TEST_DB`            | `recreate_test_db`       | `false`        | Recreate test DB on startup. Set to `true` in test environment for automatic test database recreation. |
| `STALE_FILE_THRESHOLD_HOURS`  | `stale_file_threshold_hours` | `24`      | Temp file cleanup threshold     |
| `RATE_LIMITER_FAIL_CLOSED`    | `rate_limiter_fail_closed` | `true`      | Fail-closed on Redis outage     |
| `CORS_ORIGINS`                | `cors_origins`           | `["http://localhost:3000", "http://localhost:5173"]` | Allowed CORS origins (from `app.yaml`) |
| `TEMP_PASSWORD_TTL_SECONDS`   | `temp_password_ttl_seconds` | `86400`     | Temp password Redis TTL (min 60s) |

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

Every other `*_FILE` variable is skipped without the file being read, and logged at
debug level with the variable name only. A path-valued or list-valued setting is
therefore ignored: `LOGGING__LOG_FILE` names a filesystem path, not a secret, and is
no longer read as one.

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
`DatabaseStarter.ensure_admin_user()` now calls the same two functions under the same
tier condition, so the two copies cannot drift apart.

Neither message interpolates the rejected value:

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
| `allowed_mime_types`  | `upload.allowed_mime_types`   | Allowed MIME types             |
| `log_level`           | `logging.level`               | Logging level                  |

## Cross-References

- [Backend Architecture](architecture.md) — System architecture and startup lifecycle
- [Logging](logging.md) — Logging configuration and standards
- [Security](../08-security/) — Security configuration details
- [Deployment](../10-deployment/deployment.md) — Production deployment and Docker Compose
- [Security Overview](../08-security/security-overview.md) — Production credential enforcement and secrets management
