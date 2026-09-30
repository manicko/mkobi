# BI Dashboard System — Overview

## Purpose

A web application for uploading CSV/CSV.gz data files, processing them with Polars, storing aggregated results in PostgreSQL, and visualizing data through configurable dashboards with role-based access control.

---

## Technology Stack

| Layer            | Technology                                |
| ---------------- | ----------------------------------------- |
| Backend          | **FastAPI**                               |
| Frontend         | **React 18+ (TypeScript) + Vite**        |
| State Management | **TanStack Query**                        |
| Forms            | **React Hook Form + Zod**                |
| Charts           | **Plotly.js React**                       |
| Data Processing  | **Polars** (pandas is forbidden)          |
| Storage          | **PostgreSQL + JSONB**                    |
| Validation       | **Pydantic v2**                           |
| Auth             | **JWT + bcrypt**                          |
| ORM              | **SQLAlchemy 2.0 (async) + asyncpg**     |
| Migrations       | **Alembic**                               |
| Rate Limiting    | **Redis**                                 |
| Testing          | **pytest**                                |
| Package Manager  | **uv**                                    |

---

## Architecture

**Backend:** Clean Architecture — strict layered design (API → Service → Repository).

**Frontend:** Feature-Sliced Design (FSD) — React SPA with type-safe API communication.

```
Browser (React SPA)
       ↓ HTTPS/JSON
FastAPI (REST API)
       ↓
Service Layer
       ↓
PostgreSQL
```

Key principles:
- All business logic resides in the backend service layer.
- React is UI-only; no business logic on the frontend.
- Access control is enforced on every API request.
- Stateless backend — JWT tokens carry authentication state.

> See [Backend Architecture](06-backend/architecture.md) and [Frontend Architecture](07-frontend/architecture.md) for details.

---

## Main Data Flow

1. **Upload** — `POST /api/v1/upload/{dashboard_id}` — file saved to temp directory (platformdirs), MIME-type and size validated.
2. **Parse** — Polars reads the file (UTF-8), structure validated against processing config.
3. **Transform** — LoaderConfig transformations applied, custom metrics evaluated.
4. **Aggregate** — GroupBy, YoY, shares, custom metrics — full recalculation.
5. **Save** — Results written to `aggregated_data` table (JSONB `dims` + `metrics`), temp file deleted.
6. **Retrieve** — `GET /api/v1/data/aggregated` — access check, filters applied, JSON response.
7. **Render** — React SPA receives data via TanStack Query, Plotly.js renders charts.

> See [Data Flow](00-overview/data-flow.md) for the complete end-to-end diagram.

---

## Roles & Permissions

| Role    | Capabilities                                          |
| ------- | ----------------------------------------------------- |
| Admin   | Full CRUD on dashboards, users, configs; grants access |
| Editor  | Uploads CSV, triggers data recalculation              |
| Viewer  | Read-only access to assigned dashboards               |

Access is validated on every request via the `dashboard_access` table.

> See [Auth & Access Control](01-auth/) and [Access Control](08-security/access-control.md) for details.

---

## Documentation Index

### Core Overview
- [System Overview](00-overview/overview.md) — Purpose, stack, entities, roles, API summary.
- [Data Flow](00-overview/data-flow.md) — End-to-end upload-to-display pipeline.

### Domain Documentation
- [Auth & Access Control](01-auth/) — Login, registration, JWT, password change, auth endpoints.
- [Dashboards API](02-dashboards/) — Dashboard CRUD, layout, graph, and filter endpoints.
- [Data Processing](03-processing/) — Upload, parse, transform, aggregate pipeline; task queue; custom metrics.
- [Admin API](04-admin/) — User management, registration requests, processing logs.
- [Health Checks](05-health/) — Health and detailed health endpoints.
- [Backend Architecture](06-backend/) — Clean Architecture layers, configuration, logging, testing.
- [Frontend Architecture](07-frontend/) — FSD structure, pages, auth flow, upload UI, frontend security.
- [Security](08-security/) — Rate limiting, CORS, file validation, credential enforcement, access control, client error reporting.
- [Database](09-database/) — Core schema, processing schema, access control tables, indexes, enums.
- [Deployment](10-deployment/) — Development setup, production deployment, Docker, migrations.

### Guides
- [Docker Setup](11-guides/docker.md) — Multi-stage Dockerfile, Docker Compose, quick start.
- [Task Queue Migration](11-guides/task-queue-migration.md) — In-memory `TaskQueue` to Redis/RQ migration plan.

### Reference
- [Swagger UI Guide](99-reference/swagger.md) — Using the interactive API docs at `/docs/`.
- [Run Guide](99-reference/run-guide.md) — Application setup, configuration, and run instructions.

---

## Key Design Decisions

- **JSONB for aggregated data** — Single `aggregated_data` table with JSONB `dims` + `metrics` supports any dashboard without schema migrations.
- **JSONB key normalization** — `dims` keys are sorted recursively before writes to ensure deterministic UPSERT conflict detection.
- **Full recalculation on upload** — Every upload triggers a complete rebuild of all aggregates for the dashboard.
- **StrEnum for all constants** — All fixed values (roles, statuses, types) use `StrEnum` in `src/mkobi/models/enums.py`.
- **Frontend enum presence (ButtonVariant, ComponentSize)** — These UI concept enums are defined in the backend to support server-side validation of dashboard layout configurations stored in the `layouts.definition` JSONB column. This represents a minor architectural trade-off where frontend concepts leak into the backend for validation purposes only, rather than being treated as shared types across layers.
- **Fail-open rate limiter** — When Redis is unavailable, requests are allowed through by default (configurable to fail-closed).
- **Production credential enforcement** — Application refuses to start in production with default credentials.
- **Background task queue** — In-memory `TaskQueue` (MVP) with a documented migration path to Redis/RQ.
- **Login returns user data** — The login endpoint returns `TokenWithUser` (token + user profile) to eliminate the need for a separate `/me` call after authentication.
- **Admin bypass for dashboards** — Users with the `admin` role implicitly see all dashboards without requiring explicit `dashboard_access` entries.
- **403/404 dual-signal for dashboard access** — The system distinguishes "dashboard not found" (HTTP 404) from "dashboard exists but no access" (HTTP 403) to avoid leaking dashboard existence information.
- **`display_name` computed field** — The `UserRead` model exposes a computed `display_name` derived from the email prefix (text before `@`), available in all API responses returning user data.
- **Upload as modal dialog** — File upload is implemented as `UploadModal` embedded in `DashboardView`, not as a separate page. This eliminates page navigation during upload and provides inline progress feedback.
- **Dashboard-filter binding** — Filters are linked to dashboards via the `dashboard_filters` many-to-many join table. Admins bind/unbind filters using `POST/DELETE /api/v1/dashboards/{id}/filters`. Bound filters are listed via `GET /api/v1/dashboards/{id}/filters`.
- **Dashboard access management** — Admins grant, list, and revoke dashboard access via dedicated endpoints: `POST/GET /api/v1/dashboards/{id}/access` and `DELETE /api/v1/dashboards/{id}/access/{user_id}`. This is in addition to the admin panel endpoints.
- **Dashboard-specific graph endpoints** — Graphs can be created and listed via dashboard-scoped endpoints (`POST/GET /api/v1/dashboards/{id}/graphs`) in addition to the global `/api/v1/graphs` endpoints.
- **File processing service** — `file_processing.py` encapsulates validation, upload processing, and task management functions extracted from `DataService` for modularity and testability.
- **Background data worker** — `data_worker.py` provides `process_csv_background` (async) and `process_csv_background_sync` (sync RQ wrapper) for CSV processing in background. The `_store_aggregate` function handles mode-aware (overwrite/append) data persistence.
- **Processing log date filtering** — The `GET /api/v1/admin/logs` endpoint supports `date_from` and `date_to` query parameters for filtering logs by `started_at` range, in addition to `status` and `dashboard_id` filters.
- **Top navigation Header** — The sidebar was replaced with a top navigation bar (`Header`) containing role-based nav items (Dashboards, Admin, Profile), user email display, and an AccountCircle menu for logout.
- **DataGrid tables for admin and dashboard list** — `DashboardList` and all admin panel tabs use MUI `DataGrid` with pagination, sorting, and quick filter instead of card lists or basic tables.
- **ConfirmDialog pattern** — Destructive actions (delete user, delete dashboard, reject registration) use a shared `ConfirmDialog` component with configurable labels, invoked imperatively via the `useConfirmDialog` hook.
- **Toast notifications** — User feedback for success/failure actions uses `react-hot-toast` (top-right, 3s success, 5s error duration) instead of inline alerts.
- **Short UUID display** — UUIDs displayed in tables are truncated to 8 characters via the shared `shortUuid` utility for improved readability.
- **Admin tab state preservation** — The admin panel uses `display: none/block` to hide inactive tabs, preserving pagination and sorting state across tab switches.
- **Zod v4 migration** — Frontend form validation uses Zod v4 API (`z.email()` instead of `z.string().email()`).
- **Per-IP login rate limiting** — Login rate limiter uses per-IP keys (not per-email) to prevent email enumeration attacks. The rate limiter key was changed from `f"login:{email}`" to `f"login:{client_ip}`" to avoid leaking registered email addresses through rate limit side-channels.
- **Migration advisory lock** — `_apply_migrations()` acquires a PostgreSQL advisory lock (`pg_advisory_lock(42)`) before running Alembic migrations, preventing concurrent migrations in multi-instance deployments (K8s replicas, multiple Gunicorn workers).
- **Dedicated database role (least-privilege)** — The application connects using a dedicated `mkobi_app` role with limited privileges (`CONNECT`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`) instead of the superuser `postgres` role. The superuser role is used only for DDL migrations.
- **Migration job pattern** — Production Docker Compose uses a dedicated `migrate` service that runs before the app service starts, with `depends_on: service_completed_successfully` to ensure migrations complete before the application accepts requests.
- **Stale processing heartbeat** — A periodic cleanup task marks processing logs stuck in `PROCESSING` state for more than 30 minutes (configurable) as `FAILED`, providing visibility into crashed workers and preventing indefinite `PROCESSING` states.
- **Upload memory streaming** — File uploads use chunked streaming writes (`aiofiles` with 8KB chunks) instead of reading the entire file into memory, reducing memory pressure for large uploads (up to 100MB).
- **Weak admin credential detection** — `validate_admin_credentials()` checks against a set of known-weak values (`{"admin", "administrator", "root", "test", "user"}` for usernames, `{"password", "123456", "admin", "secret", "test"}` for passwords) instead of only the exact string `"admin"`.
- **Config reload for testing** — `get_config()` supports a `reload=True` parameter and `clear_config_cache()` function, allowing tests to reload configuration without monkeypatching the global singleton.
- **Atomic UPSERT for admin user** — `ensure_admin_user()` uses `INSERT ... ON CONFLICT (email) DO NOTHING` instead of check-then-create, eliminating the TOCTOU race condition on concurrent startup.
- **Sanitized database URL logging** — `_apply_migrations()` logs the database URL with `render_as_string(hide_password=True)` to prevent credential leakage in log files.
- **LRU token cache** — `_token_cache` in permissions.py uses `functools.lru_cache(maxsize=1000)` instead of an unbounded dict, preventing memory leaks in long-running processes.
- **User deactivation enforcement** — `get_current_user_dependency()` checks `user.is_active` on every authenticated request. Deactivated users receive HTTP 401 with detail "User account is deactivated", preventing access even with a valid JWT.
- **Security headers middleware** — `SecurityHeadersMiddleware` in `app.py` sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, and `Referrer-Policy: strict-origin-when-cross-origin` on every response as defense-in-depth.
- **Standardized error format** — All exception handlers (HTTP, validation, AppException) return responses with a consistent `error_code` field, enabling programmatic frontend error handling and simplified backend monitoring.
- **Processing config auto-wiring** — The upload pipeline automatically fetches the dashboard's `processing_config` from the database and passes it through to the background worker, ensuring transformations are applied consistently.
- **Upload response model** — The upload endpoint returns a structured `UploadResponse` model (with `task_id`, `filename`, `dashboard_id`, `status`, `message`, `uploaded_at`) instead of an ad-hoc dict.
- **Upload transaction safety** — File move to final path occurs after DB commit to prevent orphan files on commit failure. The dashboard existence is verified before the access check on upload, returning a clear 404 for non-existent dashboards.
- **Internationalized character support** — Full Cyrillic and Latin character support across all system layers (database UTF-8, backend Polars/SQLAlchemy, frontend React). The standard user-facing date format is `dd/mm/yyyy` with flexible input parsing via `date_format` in processing config.
- **Cookie-based refresh tokens** — Refresh tokens are stored in httpOnly cookies (`mkobi_refresh_token`) instead of the request body, eliminating XSS-based token theft. The access token lifetime was reduced from 30 to 15 minutes; refresh tokens live 7 days. Login sets the cookie, refresh reads from it, logout clears it.
- **POST /auth/logout endpoint** — Dedicated logout endpoint that clears the refresh token cookie. The frontend calls this on logout and then clears the in-memory access token.
- **Frontend silent refresh** — On app initialization, if no access token exists, the frontend attempts a silent refresh using the httpOnly cookie. This keeps users logged in across page refreshes without requiring re-authentication.
- **Request queue for concurrent 401s** — The axios interceptor implements a request queue (`failedQueue`) with an `isRefreshing` flag. When multiple requests fail with 401 simultaneously, only one refresh call is made; all queued requests are retried after the refresh completes.
- **ProtectedRoute loading state** — `ProtectedRoute` shows a loading spinner during silent refresh to prevent flash of login page for valid sessions with expired access tokens.
- **Docker folder restructure** — All Docker configuration files were consolidated into a dedicated `docker/` folder at the project root. This includes `docker-compose.yml`, `docker-compose.override.yml`, `docker-compose.test.yml`, `Dockerfile`, `.dockerignore`, `nginx/nginx.conf`, and `init-scripts/`. The root directory now contains only application code and project metadata. All `docker compose` commands require the `-f docker/` prefix (e.g., `docker compose -f docker/docker-compose.yml up -d`). The `Dockerfile` COPY paths remain unchanged because Docker's `-f` flag only changes the Dockerfile location, not the build context (root). The `.dockerignore` file was moved to `docker/.dockerignore` but the build context remains the root, so it is still picked up automatically. The nginx volume mount in `docker-compose.yml` was updated from `./nginx/nginx.conf` to `./docker/nginx/nginx.conf`.
- **Standalone test compose** — `docker-compose.test.yml` is a fully standalone compose configuration (no overlay/merge with production compose). It defines four isolated services (`test-db`, `test-redis`, `test-migrate`, `test-app`) with separate volumes (`test_postgres_data`, `test_redis_data`), a separate network (`test_network`), and its own project name `mkobi-test`. The `conftest.py` uses `os.environ.setdefault()` so Docker Compose environment variables take precedence inside containers while preserving localhost defaults for native test execution.
- **Compose project-name isolation** — Every compose file declares a top-level `name:` so the stacks cannot collide: `mkobi` for dev/production and `mkobi-test` for tests. Without it, Compose derives the project name from the directory of the first `-f` file, which is `docker/` for all three files — so dev and test resolved to the same project and one stack's `down` destroyed the other. The dev override deliberately declares no `name:` (with multiple `-f` files the last one wins, and dev/production are the same stack). Fixed `container_name:` keys are not used: they are daemon-global, prevent a second concurrent stack, and are silently discarded by `docker compose run`.
- **Configurable host ports for parallel checkouts** — All published host ports are Compose-interpolated with defaults, so several checkouts can run side by side without editing committed files. Dev backend is `${APP_HOST_PORT:-8010}:8000`; test services are `${TEST_DB_HOST_PORT:-5434}:5432`, `${TEST_REDIS_HOST_PORT:-6381}:6379`, and `${TEST_APP_HOST_PORT:-8001}:8000`. Container-internal ports are unchanged, so the Vite proxy (`http://app:8000`), the container healthcheck, and the nginx upstream are unaffected. Dev PostgreSQL stays loopback-bound at `127.0.0.1:5432`.
- **Hermetic test credentials** — The test compose hard-codes every credential as a literal. It previously used `${VAR:-default}` interpolation, which meant an ambient shell variable silently overrode test passwords, producing non-reproducible runs. Interpolation is confined to ports; no secret is ever read from the process environment.
- **Temp password security** — Registration approval via `POST /api/v1/admin/registration-requests/:id/approve` returns `temp_password` in plaintext JSON. Security requirements: HTTPS must be enforced in production; the temp password is one-time use (user must change on first login); never log `temp_password` in application logs; admin should communicate the password through a secure out-of-band channel, not via the registration email.
- **Redis-backed token revocation** — Tokens can be immediately revoked before their natural expiration using a Redis-backed blacklist. On logout (`POST /api/v1/auth/logout`), both the access token and refresh token JTIs are added to Redis with `SETEX` TTL = remaining token lifetime (auto-expiring, no indefinite growth). On every authenticated request, `is_token_revoked()` checks the blacklist in `get_current_user_dependency()`. Revoked tokens receive HTTP 401. This closes the window where deactivated or logged-out users could continue using valid tokens until expiry.
- **Server-side MIME type detection** — File upload MIME type validation uses `python-magic` to detect the actual MIME type from file content (first 2KB of bytes) instead of trusting the client `Content-Type` header. Falls back to extension-based detection if `libmagic` is unavailable. This prevents MIME type spoofing attacks.
- **Cumulative streaming size enforcement** — File uploads enforce the maximum file size limit during streaming by tracking cumulative bytes written, even when the client does not provide `Content-Length` (file.size is None). If the cumulative size exceeds the limit, the upload is aborted (HTTP 413) and the temporary file is cleaned up, preventing disk exhaustion attacks.
- **Backend password strength validation** — Password strength requirements (minimum 8 characters, at least one letter, at least one digit) are enforced at the Pydantic model level on `ChangePasswordRequest.new_password` and `UserCreateRequest.password` via `field_validator`. This provides a backend security boundary independent of the frontend Zod validation.
- **Resource-level access control on dashboard CRUD** — Dashboard update (`PUT /api/v1/dashboards/:id`) and delete (`DELETE /api/v1/dashboards/:id`) endpoints check resource-level access in addition to role-level permissions. Admin role bypasses resource-level checks; non-admin users must have explicit `edit` or `admin` permission on the target dashboard.
- **Redis-backed temporary password storage** — `TempPasswordStore` (`core/temp_password_store.py`) provides Redis-backed one-time temporary password storage with TTL. Passwords are stored under `temp_pwd:{token}` keys and deleted immediately upon retrieval via atomic Redis pipeline (GET+DELETE). Fail-open on store errors (logged, no crash), graceful degradation on retrieve errors (returns None). The `TEMP_PASSWORD_TTL_SECONDS` setting controls TTL (default 86400 = 24h, minimum 60s).
- **Retrieval-token pattern** — Admin reset-password and registration-approval endpoints now return a `retrieval_token` (UUID) instead of the plaintext `temp_password`. The admin uses `GET /api/v1/admin/temp-passwords/{retrieval_token}` to retrieve the password in a separate step, one-time only. This prevents plaintext passwords from persisting in API response logs and reduces the window of exposure. The frontend implements a two-step flow: reset/approve → show "Show Password" dialog → call retrieve endpoint → display password in `ResetPasswordResultDialog` with copy-to-clipboard.
- **Dashboard filter values table** — `dashboard_filter_values` table stores distinct filter values extracted from aggregated data during CSV processing. Supports dynamic filter UI population via `GET /api/v1/dashboards/{id}/filter-values?filter_name={name}`. Filters with `config.source === "data"` fetch values from this table instead of static `config.options`. Values are rebuilt on each upload (idempotent overwrite).
- **Per-chart GROUP BY aggregation** — `AggregationService` performs Polars GROUP BY per graph with `graph.dimensions + dashboard.filters.dimensions` as GROUP BY columns. Replaces the previous row-by-row iteration approach. Produces one row per unique dimension combination with aggregated metric values.
- **CSV parsing config pass-through** — Processing config settings (separator, encoding, column_types, decimal_separator) are fetched from `processing_config` and applied to CSV parsing in `data_worker.py`. Post-read Polars transformation handles comma decimal separator for float columns.
- **Expression index for UPSERT** — The `aggregated_data` table uses a unique expression index `((dims)::text)` for conflict detection. SQLAlchemy UPSERT statements must use `text("((dims)::text)")` in `index_elements` to match the expression index — a plain column reference fails with `InvalidColumnReferenceError`.
- **AccessDenied as default fallback** — `RoleBasedAccess` renders `<AccessDenied />` as the default fallback when users lack required roles, providing clear feedback instead of a blank page.
- **PlaceholderPage for route stubs** — `PlaceholderPage` provides a standardized "coming soon" UI for routes that exist in navigation but lack full implementation. Not for in-page elements (use disabled button + tooltip) or error states (use `NotFound`/`AccessDenied`).
- **Charts under dashboards feature** — Chart components reside in `features/dashboards/ui/charts/` as dashboard-specific UI. No standalone `features/charts/` module is needed — chart functionality is fully contained within the dashboard rendering pipeline.
- **Test port exposure trade-off** — Test compose ports (`5434`, `6381`, `8001` by default) are intentionally exposed for native pytest execution. Risk is LOW (no production data). Alternative: run tests inside the container via `docker compose exec` to avoid exposing ports.
- **Production Redis host must be set explicitly** — `RedisSettings.host` defaults to `localhost` (`config.py`), which inside a container is the container itself, not the `redis` service. The production compose therefore sets `REDIS__HOST: redis` and `REDIS__PORT: "6379"` for the `app` service. This is mandatory, not cosmetic: `rate_limiter_fail_closed` defaults to true and the auth/upload paths have no Redis error handling, so a wrong host is a total production auth outage. The `rq-worker` service does not need these variables — it receives its target from the explicit `--url redis://redis:6379/0` command line, and its worker code reads no Redis configuration.
- **`Makefile.ps1` is the canonical entry point** — All developer commands run through `.\Makefile.ps1 <target>` (PowerShell 7+), which wraps `docker compose` with explicit project names (`-p mkobi` / `-p mkobi-test`). It never sets `COMPOSE_PROJECT_NAME` in the process environment, because that leaks into unrelated invocations. It also never passes `--project-directory`, which would repoint the build context to the repository's parent directory. Use `.\Makefile.ps1 help` for the target list.
- **Two rows above are maintained, not append-only** — *Standalone test compose* and *Test port exposure trade-off* were updated **in place** in 3.11, when the test host ports became configurable, rather than being superseded by a new row. They consequently track the current configuration, not the state at the version that introduced them. The per-version record of the original values is in the Version History table below.

---

## Version History

| Version | Date       | Description                              |
| ------- | ---------- | ---------------------------------------- |
| 2.2     | 2026-05-16 | Updated with implemented features        |
| 2.3     | 2026-05-19 | Added login user-in-response, admin bypass, 403/404 dual-signal, display_name |
| 2.4     | 2026-05-19 | Upload modal (no page nav), top nav Header, DataGrid tables, ConfirmDialog pattern, toast notifications, short UUID display, Zod v4 migration, admin tab state preservation |
| 2.5     | 2026-05-19 | Dashboard-filter binding API, dashboard access management endpoints, dashboard-scoped graph endpoints, file processing service, background data worker, processing log date filtering |
| 2.6     | 2026-05-20 | Per-IP login rate limiting (email enumeration fix), migration advisory lock, dedicated DB role (least-privilege), migration job compose pattern, stale processing heartbeat, upload memory streaming, weak admin credential detection, config reload for testing, atomic UPSERT admin user, sanitized DB URL logging, LRU token cache |
| 2.7     | 2026-05-23 | Cookie-based refresh token flow: httpOnly refresh cookies (7-day TTL), 15-min access tokens, POST /auth/logout endpoint, frontend silent refresh on mount, request queue for concurrent 401s, ProtectedRoute loading state during refresh |
| 2.8     | 2026-05-25 | Docker folder restructure (all compose/Dockerfile/config into docker/ folder), standalone test compose (isolated test-db/test-redis/test-migrate/test-app with separate volumes/networks/ports), conftest.py setdefault for Docker Compose env var precedence, dev/test parallel execution support |
| 2.9     | 2026-05-26 | Doc updates: admin logs pagination changed from page/page_size to skip/limit (D-001), added temp_password security note for registration approval (D-003), documented frontend enum presence rationale (D-004) |
| 3.0     | 2026-05-29 | Audit-driven improvements: client error reporting API, password strength validation at Pydantic model level, MIME-type validation hardening (415 on missing Content-Type), error message sanitization across all route modules (no internal detail leaks), dashboard_name resolved in processing log responses via join, callback registration pattern to break circular frontend dependency (axiosInstance ↔ authApi), processing log filter status parameter alignment (status → status_filter), frontend ARIA accessibility attributes for upload components, LogViewer error handling and null-safe datetime rendering |
| 3.1     | 2026-05-31 | Security hardening: is_active check on JWT auth (deactivated users get 401), security headers middleware (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy), standardized error response format with error_code field across all exception handlers. Data integrity: transaction-safe file move (after DB commit), automatic processing config wiring through upload pipeline, structured UploadResponse model for upload endpoint, explicit dashboard existence check before access verification on upload. |
| 3.2     | 2026-05-31 | Force password change flow: `force_password_change` boolean column on `users` table (NOT NULL, default false), admin-triggered password reset via `POST /api/v1/admin/users/{user_id}/reset-password` (generates temp password, sets flag), registration approval sets `force_password_change=True`, `change_password()` clears the flag, login response includes `force_password_change` field, frontend redirects to `/profile/change-password?force=true` when flag is set, force mode disables Cancel button and shows informational alert, `ResetPasswordResultDialog` component with copy-to-clipboard for temp password, `UserManagement` grid includes Reset Password action button with confirmation dialog, self-reset prevention guard (admin cannot reset own password), `display_name` computed from email prefix, silent refresh checks `force_password_change` and redirects via `window.location.href`. |
| 3.3     | 2026-06-02 | Token revocation: Redis-backed blacklist with auto-expiring entries on logout (both access and refresh tokens revoked immediately). Server-side MIME type detection: python-magic reads actual file content instead of trusting client Content-Type header. Cumulative streaming size enforcement: file size limit checked during streaming even without Content-Length (prevents disk exhaustion). Backend password strength validation: Pydantic field_validator enforces min 8 chars + at least one letter + at least one digit. Resource-level access control on dashboard CRUD: update/delete endpoints check per-dashboard permissions, not just role. |
| 3.4     | 2026-06-02 | Redis-backed temp password storage: `TempPasswordStore` with atomic GET+DELETE pipeline, configurable TTL via `TEMP_PASSWORD_TTL_SECONDS`. Retrieval-token pattern: reset/approve endpoints return `retrieval_token` instead of plaintext `temp_password`. New admin endpoint `GET /admin/temp-passwords/{retrieval_token}` for one-time retrieval. Frontend two-step retrieval flow with `RetrievePasswordDialog`. |
| 3.5     | 2026-06-03 | Filter values subsystem: `dashboard_filter_values` table for caching distinct filter values extracted from aggregated data, `AggregationService` for per-chart Polars GROUP BY (graph.dims + filter.dims), `GET /dashboards/{id}/filter-values` API endpoint for dynamic filter UI population, automatic filter value extraction in `_store_aggregates` after each CSV upload, CSV parsing config (separator, encoding, column_types, decimal_separator) applied from `processing_config` settings. |
| 3.6     | 2026-06-08 | Expression index UPSERT fix: `StorageManager._bulk_upsert()` and `upsert_aggregate()` now use `text("((dims)::text)")` in ON CONFLICT clauses to match the expression index `uq_aggregated_data_dashboard_graph_dims`. Frontend component documentation: `PlaceholderPage` (route-level stub), `AccessDenied` (default `RoleBasedAccess` fallback), chart components confirmed under `features/dashboards/ui/charts/` (no standalone `features/charts/` module needed). Test port security assessment: documented trade-offs for exposed test ports (5433, 6380, 8001) with LOW risk classification. |
| 3.7     | 2026-06-09 | Internationalized character support: full Cyrillic and Latin character support documented across database (UTF-8 encoding), backend (Polars/SQLAlchemy Unicode handling), and frontend (React rendering). Standard user-facing date format set to `dd/mm/yyyy` with flexible input parsing via processing config `date_format` setting. |
| 3.8     | 2026-06-09 | PostgreSQL 18 upgrade: migrated from `postgres:16.3` to `postgres:18-bookworm` with `builtin` locale provider and `C.UTF-8` collation. This eliminates collation version mismatch errors on Docker image updates by using an immutable collation version (fixed at `1`). Volume mount path changed from `/var/lib/postgresql/data` to `/var/lib/postgresql` per PG18 requirements. See `docker/docker-compose.yml` for configuration. |
| 3.9     | 2026-06-11 | Added `idx_processing_logs_status_finished_at` composite index on processing_logs (status, finished_at) for optimized cleanup query performance. Processing config settings documentation updated with complete field reference including metric_agg, separator, encoding, column_types, decimal_separator, and date_format. Processing config API response now documents metric_agg field. List logs query parameter renamed from `status` to `status_filter` for consistency with ProcessingStatus enum usage. |
| 3.10    | 2026-06-16 | Chart data sorting in AggregationService. X-axis sorted chronologically (via year/month columns when available). Color dimension (brands/categories) sorted by total metric volume (descending) for proper stacked bar visualization. Implemented via `_apply_chart_sorting()` method after GROUP BY. Uses helper `_color_total` column excluded from final output. `SortConfig` TypedDict added to `GraphConfigDict` with `sort_x` and `sort_color` optional fields. |
| 3.11    | 2026-09-30 | Docker and task-runner remediation (plan: `.ai/plans/mkobi-docker-taskrunner-remediation.md`). **Compose project-name isolation** — top-level `name: mkobi` and `name: mkobi-test`; previously all three compose files resolved to `docker`, so tearing down one stack destroyed the other. Removed the four daemon-global `container_name:` keys from the test compose. **Un-gated `rq-worker`** — `profiles: []` in the dev override does not remove a profile (Compose folds it into the base list), so the background worker never started in dev; the profile was removed from the base instead. **Safe `CORS_ORIGINS` default** — the base compose used `${CORS_ORIGINS:?}`, which fired before the dev override could supply a default and blocked any minimal env file; it now uses a placeholder origin that `config.py` still rejects when `ENV=production`. **Hermetic test stack** — removed all `${...}` interpolation so ambient shell variables can no longer override test credentials. **Backend hot reload on Windows** — added `WATCHFILES_FORCE_POLLING` to the dev `app` service; the existing `CHOKIDAR_USEPOLLING` vars applied only to the frontend container and had no effect on uvicorn. **Configurable host ports** — dev backend and all test services now use env-overridable ports (`8010`, `5434`, `6381`, `8001` by default) so multiple checkouts can run in parallel; container-internal ports unchanged. **Production `REDIS__HOST`** — the base compose omitted it, so production resolved Redis to `localhost` (the container itself) and, with fail-closed rate limiting, login and upload would have failed entirely. **Greenfield `Makefile.ps1`** — replaced a task-runner copied from an unrelated Django project that referenced non-existent services, `manage.py`, `basedpyright`, and `.env.dev` parsing. |
| 3.12    | 2026-09-30 | Configuration and secrets hardening. **Pinned production tier** — the base compose file declared `ENV: ${ENV:-production}`, so the repository's own `.env` (`ENV=development`) silently downgraded `migrate`, `app` and `rq-worker` and disabled every production guard; `ENV` is now the literal `production` in the base file, and only the development override sets another tier. **Least-privilege runtime services** — `DATABASE__ADMIN_USER`/`DATABASE__ADMIN_PASSWORD` were injected into `app` and `rq-worker`, which run as `mkobi_app` and never use them; they are now supplied to the dev and test paths only. **Credential strength is now reachable** — the production guards refuse the shipped `CHANGE_ME_*` placeholder family (case-insensitive prefix), empty and whitespace-only admin credentials, and admin passwords under 8 characters, with two guard copies collapsed into one shared predicate. **`*_FILE` is secret-scoped** — `SecretsFileSource` honours only the five derived secret-bearing names (`DATABASE__PASSWORD_FILE`, `DATABASE__ADMIN_USER_FILE`, `DATABASE__ADMIN_PASSWORD_FILE`, `JWT__SECRET_KEY_FILE`, `REDIS__PASSWORD_FILE`), so a path-valued setting such as `LOGGING__LOG_FILE` is no longer read as a secret pointer. **CORS wildcard refusal is reachable** — it moved into `Settings.validate_cors_origins`, ahead of the filter that used to remove `"*"` before either copy could see it. **Unread configuration removed** — eight fields nothing read were deleted (`host`, `port`, `app_name`, `logging.format`, `upload.temp_dir_prefix`, `dashboard.default_items_per_page`, `DatabaseSettings.admin_database_url`, `Settings.load_yaml_config()`); `app.name`/`app.version` are now the single owner of the displayed name and version, and `upload.temp_dir` resolves to an absolute platformdirs path. **Build context** — `.dockerignore` now excludes every `.env*` file at any depth plus `*.dump`, `backups/` and `.ai/`. |

Each version row records the state of the project **as of that version**, so a
value that changed later is expected to differ from its current value. The
`3.6` row's test ports `(5433, 6380, 8001)` and the `3.11` row's
`(5434, 6381, 8001)` are therefore consistent rather than contradictory: `3.6`
records the ports in use at that date, and `3.11` records the configurable
ports introduced by the remediation. Neither row is wrong for its own version.
Current values are documented in [Docker Guide](./11-guides/docker.md).

---

**Author:** Senior Python Architect
**Date:** 2026-09-30
**Version:** 3.11
