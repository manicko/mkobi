---
id: logging
domain: backend
tags:
  - logging
  - json-logging
  - log-levels
  - structured-logging
  - python-logging
  - log-output
related:
  - backend-architecture
  - configuration
  - testing
---

# Logging

## Overview

The application uses Python's standard `logging` module with structured JSON output. All log messages and code comments are in **English only** — Russian or other languages are not permitted in logs or code.

**Implementation:** `src/mkobi/core/logging_config.py`

## Log Levels

| Level   | Usage                                           |
| ------- | ----------------------------------------------- |
| `INFO`  | Normal operations: uploads, processing, access events |
| `WARNING` | Recoverable issues: default credentials, stale files |
| `ERROR` | Failures: database connection errors, processing failures, rate limiter issues |

## Structured JSON Logging

By default, the application uses JSON formatting for machine-readable logs:

```json
{
  "timestamp": "2026-01-15 10:30:00",
  "level": "INFO",
  "service": "mkobi",
  "message": "Admin user created: admin@example.com",
  "module": "mkobi.db.starter",
  "function": "ensure_admin_user"
}
```

`ensure_admin_user` distinguishes the two outcomes of its `INSERT ... ON
CONFLICT DO NOTHING`. A row that was created logs `Admin user created: <email>`;
a row that the conflict clause matched logs `Admin user already existed:
<email> (id=<id>, role=<role>)`, naming the occupant's id and role and never a
credential:

```json
{
  "timestamp": "2026-01-15 10:30:01",
  "level": "INFO",
  "service": "mkobi",
  "message": "Admin user already existed: admin@example.com (id=3f..., role=admin)",
  "module": "mkobi.db.starter",
  "function": "ensure_admin_user"
}
```

If the address is occupied by a **non-admin** user, a different message is used — one that names
the collision rather than reporting an ordinary pre-existing admin — and the outcome is
environment-scoped: `WARNING` in development, and a `ValueError` that aborts startup in
production. `ON CONFLICT DO NOTHING` silently declines to promote anyone, so a production tier
whose configured admin address is held by a viewer would otherwise start up "successfully" with no
admin at all. The message shape matches the one above, and again no credential appears:

```json
{
  "timestamp": "2026-01-15 10:30:02",
  "level": "WARNING",
  "service": "mkobi",
  "message": "Admin address is occupied by a non-admin user: admin@example.com (id=3f..., role=viewer)",
  "module": "mkobi.db.starter",
  "function": "ensure_admin_user"
}
```

### JSON Formatter Fields

| Field       | Description                                      |
| ----------- | ------------------------------------------------ |
| `timestamp` | Formatted as `YYYY-MM-DD HH:MM:SS`               |
| `level`     | Log level name (INFO, WARNING, ERROR)            |
| `service`   | Always `"mkobi"`                                 |
| `message`   | The log message                                  |
| `module`    | Python module name                               |
| `function`  | Function name where the log was emitted          |
| `exception` | Exception traceback (present only on errors)     |

Extra fields can be added via the `extra` parameter:
```python
logger.info("Upload complete", extra={"file_size": 1024, "dashboard_id": "..."})
```

## Logger Hierarchy

Loggers follow the `mkobi.*` namespace hierarchy:

| Logger              | Scope                           |
| ------------------- | ------------------------------- |
| `mkobi`             | Root application logger         |
| `mkobi.api`         | API route handlers              |
| `mkobi.data`        | Data processing (Polars)        |
| `mkobi.db`          | Database operations             |
| `mkobi.services`    | Business logic services         |
| `mkobi.core`        | Security, permissions, config   |
| `mkobi.workers`     | Background task processing      |
| `uvicorn`           | ASGI server                     |
| `uvicorn.error`     | ASGI server errors              |
| `uvicorn.access`    | HTTP access logs                |

## Usage Pattern

Every module creates its own logger at the top of the file:

```python
import logging

logger = logging.getLogger(__name__)
```

**The `print()` function is forbidden.** Always use the module-level logger.

### Getting a Logger

For modules outside the `mkobi.*` namespace, use the `get_logger()` helper which ensures the correct prefix:

```python
from mkobi.core.logging_config import get_logger

logger = get_logger(__name__)
```

## What Is Logged

The following events are logged:

| Event Type        | Level   | Example                                      |
| ----------------- | ------- | -------------------------------------------- |
| File upload       | INFO    | "File uploaded: sales_data.csv (5.2 MB)"     |
| Processing start  | INFO    | "Processing started for dashboard abc-123"   |
| Processing result | INFO    | "Processing completed: 1500 rows aggregated" |
| Processing failure| ERROR   | "Processing failed: invalid CSV format"      |
| Access events     | INFO    | "User admin@example.com accessed dashboard"  |
| Auth events       | INFO    | "Login successful: user@example.com"         |
| Auth failures     | WARNING | "Failed login attempt: unknown@example.com"  |
| Rate limit        | WARNING | "Rate limit exceeded for IP 192.168.1.1"    |
| Startup           | INFO    | "Database initialization completed"          |
| Shutdown          | INFO    | "Database engines disposed"                  |
| Config loading    | INFO    | "Configuration loaded: env=development"      |

## Log Output

Logs are written to **stdout** by default. An optional rotating file handler can be configured:

- **Max file size:** 10 MB per file
- **Backup count:** 5 rotated files
- **Encoding:** UTF-8

File output is enabled by setting the `log_file` configuration property
(`LOGGING__LOG_FILE`). It is **not set by any compose service by default**: the
docker services previously set it for `app` and `rq-worker`, which made four
processes (app, rq-worker, migrate and the dev worker) each open one
`RotatingFileHandler` against the same file. The rotation ceiling was therefore
`4 writers x 6 files x 10 MB ~= 240 MB`, not the `~150 MB` a single writer would
give. With the per-process default removed the ceiling is **zero** by default —
one process owns the file only when an operator sets the key explicitly in
`.env`. The setting itself is unchanged; it is simply no longer set for everyone.

## Code Comments

**All code comments must be in English.** This applies to:

- Python code (backend)
- TypeScript/JavaScript code (frontend)
- Docstrings (Google style recommended)
- Inline comments

This requirement exists to ensure consistency across the codebase and to prevent mixed-language code that is difficult to maintain.

## Cross-References

- [Backend Architecture](architecture.md) — System architecture and layer responsibilities
- [Configuration](configuration.md) — Logging configuration settings
- [Testing](testing.md) — Testing strategy and coverage areas
- [Deployment](../10-deployment/deployment.md) — Log output in Docker and production
