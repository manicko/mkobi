# Code Context — Audit phase 04: Authentication

**Deliverable** Phase-1 (code-context) audit · **Phase** `04-authentication` · **HEAD** `b646ef1`
**Inputs** `.ai/audit/99-validation/04-authentication-validated-findings.md` (`AUTH-001..008`, `VAL-04-001..010`),
`.ai/audit/04-authentication/findings.md`, sibling plans `01-`/`02-`/`03-`.

> **Anchor authority.** Every anchor below is a symbol, module, route, config key, table or test id.
> Report line numbers appear only as drift evidence. The validated report's own `VAL-04-001`..`010`
> already re-derived most anchors; this document supersedes them where the working tree has moved on.

---

## 1. Scope and method

### 1.1 What was read

| Class | Files |
| --- | --- |
| Report | `.ai/audit/99-validation/04-authentication-validated-findings.md`; `.ai/audit/04-authentication/findings.md` |
| Plans | `.ai/plans/01-configuration-secrets-remediation-execution.md`, `02-process-architecture-remediation-execution.md` (B7 / `TSK_07`), `03-db-concurrency-remediation.md` (B0–B10, decisions D-1..D-4, coordination C-1..C-7) |
| Backend prod | `src/mkobi/api/routes/{auth,admin,users}.py`, `src/mkobi/api/deps.py`, `src/mkobi/services/{auth_service,user_service}.py`, `src/mkobi/core/{security,permissions,temp_password_store,config}.py` → `src/mkobi/config.py`, `src/mkobi/db/{starter,session}.py`, `src/mkobi/db/models/user.py`, `src/mkobi/models/{user,enums}.py`, `src/mkobi/utils/exceptions.py`, `src/mkobi/interfaces/service_interfaces.py` |
| Infra | `docker/nginx/nginx.conf`, `docker/Dockerfile`, `docker/docker-compose.override.yml`, `frontend/vite.config.ts` |
| Tests | `tests/test_auth_service.py`, `tests/test_auth_api.py`, `tests/test_rate_limiting.py`, `tests/core/test_temp_password_store.py`, `tests/api/test_temp_password_retrieval.py`, `tests/test_registration_flow.py`, `tests/test_force_password_change_backend.py`, `tests/test_admin_user_management.py`, `tests/test_token_revocation.py`, `tests/test_users_api.py`, `tests/test_user_service.py`, `tests/conftest.py` |
| Frontend | `frontend/src/features/auth/model/useAuth.ts`, `features/auth/ui/LoginForm.tsx`, `features/auth/model/__tests__/useAuth.test.tsx`, `shared/api/{axiosInstance,errorHandler,errorMessages}.ts`, `shared/types/api.types.ts`, `features/admin/{ui/UserManagement.tsx,ui/RegistrationRequests.tsx,api/adminApi.ts}` |
| Docs | `docs/01-auth/auth-api.md`, `docs/04-admin/admin-api.md`, `docs/06-backend/{architecture,logging}.md`, `docs/07-frontend/pages.md`, `docs/08-security/security-overview.md`, `docs/00-overview/overview.md`, `docs/09-database/schema-core.md` |

### 1.2 Verification method

| Claim class | Method |
| --- | --- |
| All eight findings | **By reading only.** Every claim re-derived statically against files on disk. |
| HEAD-vs-worktree split | **By execution.** `git log`, `git status --porcelain`, `git diff`, `git show HEAD:<path>`. |
| Dev stack liveness | **By execution.** `.\Makefile.ps1 ps` — `db`, `redis`, `app`, `rq-worker`, `frontend` all healthy. |
| Runtime image content | **By execution, read-only.** `docker exec mkobi-app-1 grep -c …` on `auth_service.py`, `user_service.py`, `starter.py`. |

**Not verified by execution:** no HTTP request, no pytest run, no DB/Redis write. Reason: the running
image is a *snapshot of a working tree*, not a build of HEAD or of the current tree — it contains the
uncommitted `IntegrityError` classifier in `user_service.py` but not necessarily today's tree. Any
runtime reproduction must first rebuild. The shared dev stack is also the one phase-03 in-flight work
touches; the upstream validator recorded that it was left untouched, and this audit keeps that posture.

### 1.3 HEAD-vs-worktree split (brief corrections)

| Brief said | Reality on disk |
| --- | --- |
| worktree mods: `deps.py`, `admin.py`, `session.py`, `service_interfaces.py`, `user_service.py`, `test_admin_user_management.py`; new `test_user_service.py` | Those **plus** `tests/test_token_revocation.py` and `tests/test_users_api.py`, also modified. New untracked `tests/test_user_service.py`. |
| implied `config.py` / `starter.py` carry uncommitted phase-01 changes | Both are **clean** — phase 01 is committed. Their content changed anyway since the report was written (`is_weak_admin_password` / `is_weak_admin_username` now exist in `config.py`; `starter.py::ensure_admin_user` moved). |

**Pre-existing, not phase-related:** `git status` shows deletions under `.ai/builders/`, `.ai/structure/`,
`.ai/models/`, `.ai/templates/`, `frontend/coverage/`, and `.ai/plans/audit-fix-plan.md`. One of those
deleted paths is `AGENTS.md`'s first "Key link" (`.ai/structure/map.md`).

---

## 2. Per-finding context

### AUTH-001 — Password reset writes an unretrievable credential (HIGH)

| Claim | Current behaviour (anchor) | Verdict |
| --- | --- | --- |
| Store fails open | `TempPasswordStore.store` catches `Exception`, logs, returns — `core/temp_password_store.py` (`store`) | substantiated |
| Every write precedes the Redis write | `AuthService.reset_password_admin` (`update` → `commit` → `store`) and `AuthService.approve_registration_request` (`create_user` → `flag` → `commit` → `store`) | substantiated |
| Rate-limit key is IP-only | `routes/auth.py::_handle_login` builds `f"login:{client_ip}"`; `max_attempts=5, ttl=300` hard-coded | substantiated |
| Refresh key is IP-only | `routes/auth.py::refresh` builds `f"refresh:{client_ip}"`, `max_attempts=10, ttl=300` | substantiated |
| Store availability is a key component | increment at `core/security.py::AsyncRateLimiter.check_rate_limit` (`pipeline.incr`/`expire`/`execute`) | substantiated |
| Docs state "5 attempts / 5 minutes per IP" | `docs/01-auth/auth-api.md` login + `login_form` rows; `docs/08-security/security-overview.md` rate-limit table | substantiated |
| **VAL-04-001** — option (b) key would need `RATE_LIMITER_ENABLED` | `AsyncRateLimiter` has no enabled flag; its only constructor params are `_redis`, `_fail_closed` | substantiated → **drop option (b)** |

**Extra doc defect the report did not name.** `docs/01-auth/auth-api.md` ("Rate limiting: Redis-based;
fail-open by default, configurable to fail-closed") contradicts both the code
(`config.py::rate_limiter_fail_closed` defaults to `True`) and `security-overview.md`'s
"Fail-closed (default)" row. Same documentation pass.

**Seams.** `core/temp_password_store.py::store`; `services/auth_service.py::{reset_password_admin, approve_registration_request}`; `api/routes/admin.py::reset_user_password_admin_endpoint`; `api/routes/admin.py::reset_user_password_admin_retrieve_endpoint` (returns `retrieval_token` to the client verbatim); `core/security.py::AsyncRateLimiter`; `config.py::rate_limiter_fail_closed`.
**Tests pinning current behaviour:** `tests/core/test_temp_password_store.py::test_store_fail_open_on_error` (asserts one `logger.error` call and no raise); `tests/test_auth_service.py::test_store_failure_after_commit_returns_success` (asserts HTTP 200 + `retrieval_token` present after a fail-open store); `tests/test_auth_service.py::test_reset_password_admin_commit_precedes_store` (asserts `order == ["update","commit","store"]`); `tests/api/test_temp_password_retrieval.py` 404-on-missing cases.
**Frontend callers of the returned handle:** `features/admin/api/adminApi.ts::retrieveTempPassword`, consumed by `features/admin/ui/UserManagement.tsx` and `features/admin/ui/RegistrationRequests.tsx`.

### AUTH-002 — Approval/reset commit ordering vs the temp-password store (HIGH) → **partly already fixed, partly drifted**

| Claim | Current behaviour (anchor) | Verdict |
| --- | --- | --- |
| Store write precedes the commit; commit hoisted out of `register_user` into the route | **Gone.** `AuthService.approve_registration_request` now owns `create_user → force_password_change → commit → store`; `AuthService.reset_password_admin` orders `update → commit → store`. Landed by `2de4156` | **already-fixed** |
| Handle is returned regardless of store outcome | Both service methods return `{"retrieval_token": retrieval_token}` unconditionally; `TempPasswordStore.store` returns `None` on both success and swallow | substantiated |
| Route returns the service dict verbatim, with no compensation | `api/routes/admin.py::approve_registration_request_admin_endpoint` returns the service dict | substantiated |
| `admin.py` lines "321 / 330 / 335" | Those statements **no longer exist in `admin.py`** — they moved to `auth_service.py` | **drifted** (see §5) |

**The conflict that decides this finding.** `2de4156` deliberately encoded *commit-then-store* and
`docs/04-admin/admin-api.md` now documents it as accepted behaviour ("`TempPasswordStore.store` fails
open… the service therefore neither treats a non-raising call as proof that the credential is
retrievable, nor rolls the user back", plus an ASCII sequence diagram ending "store temp password in
Redis ← deliberately after the commit"). Two shipped tests and that documentation paragraph state the
**opposite** of the report's recommended 503-with-rollback. AUTH-002 is therefore not a stale finding —
it is a live disagreement between the audit and a landed, documented, deliberately-chosen design.
See **DP-1**.

**Seams.** `services/auth_service.py::{reset_password_admin, approve_registration_request}`; `interfaces/service_interfaces.py::IAuthService`; `api/routes/admin.py::{reset_user_password_admin_endpoint, approve_registration_request_admin_endpoint, reset_user_password_admin_retrieve_endpoint}`; `core/temp_password_store.py::store`; `docs/04-admin/admin-api.md` (transaction-ordering section, error table, both `retrieval_token` security notes).

### AUTH-003 — `force_password_change` is documented and field-tested but never enforced (HIGH)

| Claim | Current behaviour (anchor) | Verdict |
| --- | --- | --- |
| No access-control check consumes the flag | Zero occurrences of the flag in any gate. `api/deps.py::get_current_user_dependency` checks only signature, blacklist, `user_tokens_revoked`, row existence, `is_active`. `core/permissions.py::get_current_user` / `_get_current_user_with_session` checks signature + the two Redis markers | substantiated |
| Field exists end-to-end | `db/models/user.py::User.force_password_change`, `models/user.py::UserRead.force_password_change`, `shared/types/api.types.ts` | substantiated |
| Login responses carry the flag | `services/auth_service.py::login_user` returns the whole `UserRead`; `routes/auth.py::_handle_login` builds `TokenWithUser`; `routes/auth.py::register_request` returns `message` only | substantiated |
| Changing the password clears it | `AuthService.change_password` calls `user_repo.update(..., force_password_change=False)` | substantiated |
| Docs promise next-login enforcement | `docs/00-overview/overview.md`, `docs/09-database/schema-core.md` ("Forces password change on next login"), `docs/01-auth/auth-api.md`, `docs/04-admin/admin-api.md`, `docs/07-frontend/pages.md` | substantiated |

**Seams.** `api/deps.py::get_current_user_dependency`; `core/permissions.py::get_current_user`, `_get_current_user_with_session` (**currently no caller in `src/` — only `tests/test_permissions.py`**; see `VAL-04-009`); `services/auth_service.py::{login_user, change_password}`; `db/models/user.py::User.force_password_change`; `frontend/src/shared/api/axiosInstance.ts` (both sign-out blocks), `features/auth/model/useAuth.ts`, `features/auth/ui/LoginForm.tsx`.
**Frontend consumers (browser-surfaced):** `useAuth.ts` (initial load + refresh branches), `LoginForm.tsx` (post-login), `features/admin/ui/UserManagement.tsx` (admin table cell).
**Tests pinning current behaviour:** `frontend/src/features/auth/model/__tests__/useAuth.test.tsx` "force_password_change redirect" describe block (3 cases); `tests/test_force_password_change_backend.py` (4 cases asserting the flag is present in the login body); `tests/test_auth_api.py::{test_approve_registration_sets_force_password_change, test_password_change_clears_force_password_change}`; `tests/test_auth_service.py` (mock assertions on `force_password_change=True`); `tests/test_registration_flow.py` approval→change-password path.

### AUTH-004 — Token revocation is unusable as a deactivation mechanism (HIGH)

| Claim | Current behaviour (anchor) | Verdict |
| --- | --- | --- |
| `UserRepository.set_active` returns without revoking | Repo-only; no Redis import at repository level | substantiated |
| `UserService.update_user_active_status` ends at `repo.update` | `services/user_service.py` — no revocation, and (worktree) now commits | substantiated |
| Route revokes only after a successful service return | `api/routes/admin.py::update_user_active_admin_endpoint` → `revoke_all_user_tokens`, then re-raises as `INTERNAL_ERROR` | substantiated |
| Generic `except Exception` swallows it | Same route, terminal `except Exception` | substantiated |
| Race window between the two | Redis call is not inside a DB transaction | substantiated |

**New claim handed over by plan 03 (`C-7`) — substantiated, not in the report.**
`routes/auth.py::refresh` loads the user and then gates only on `is_refresh_token_revoked` and
`is_user_tokens_revoked` (both purely Redis); `services/auth_service.py::login_user` returns a signed
token for any row whose password verifies. **`user.is_active` is compared nowhere in `src/` outside
`api/deps.py::get_current_user_dependency`.** A committed deactivation plus a failed Redis revocation
therefore still yields fresh signed tokens. Plan 03 `B1` explicitly declines to fix this and assigns
it to phase 04, inside AUTH-004's "what a revocation marker must be able to express" zone.

**Seams.** `db/repositories/user_repo.py::UserRepository.set_active`; `services/user_service.py::update_user_active_status`; `interfaces/service_interfaces.py::IUserService`; `api/routes/admin.py::update_user_active_admin_endpoint`; `core/security.py::{revoke_all_user_tokens, is_user_tokens_revoked}`; `routes/auth.py::{refresh, _handle_login, login_form}`; `services/auth_service.py::login_user`.
**Tests pinning current behaviour:** `tests/test_admin_user_management.py::{test_deactivate_user_admin, test_reactivate_user_admin}`; `tests/test_token_revocation.py::test_user_deactivation_revokes_all_tokens` (now, worktree, also asserts `is_active is False` through a second session).

### AUTH-005 — Client-IP rate limiting keys on an untrusted header (HIGH)

| Claim | Current behaviour (anchor) | Verdict |
| --- | --- | --- |
| Login/refresh keys read `request.client.host` | `routes/auth.py::_handle_login`, `routes/auth.py::refresh` | substantiated |
| No proxy trust configured | No `--forwarded-allow-ips` in `docker/Dockerfile` (dev and prod `CMD`) nor in `docker/docker-compose.override.yml` (dev `command:`) | substantiated |
| Dev proxy sets `X-Real-IP` / `X-Forwarded-For` | `docker/nginx/nginx.conf` (`proxy_set_header X-Real-IP`, `X-Forwarded-For`); `frontend/vite.config.ts` dev proxy | substantiated |
| Production nginx logs the right client IP | `nginx.conf` `access_log` with no `log_format` override → nginx default `combined` | substantiated |
| Admin route drifts | `update_user_active_admin_endpoint` is later in the file than the report's range | drifted (cosmetic) |

**Seams.** `api/routes/auth.py::{_handle_login, refresh}`; `api/routes/admin.py::update_user_active_admin_endpoint`; the uvicorn invocation — one of `docker/Dockerfile` (two `CMD`s), `docker/docker-compose.yml`, `docker/docker-compose.override.yml`; `docker/nginx/nginx.conf`; `docs/08-security/security-overview.md` (per-IP table).
**Consumers of the real client IP in production:** `routes/auth.py::register_request` uses `request.headers.get("X-Forwarded-For")` directly. `admin_responses` already declares **429**.

### AUTH-006 — `GET /admin/temp-passwords/{token}` is an oracle (MEDIUM)

| Claim | Current behaviour (anchor) | Verdict |
| --- | --- | --- |
| Lookup distinguishes absent from expired | `core/temp_password_store.py::retrieve` → `(None, None)` vs `(None, "expired")` | substantiated |
| Retrieve endpoint maps both to 404 with identical bodies | `api/routes/admin.py::reset_user_password_admin_retrieve_endpoint` | substantiated |
| Single-use claim relies on a `GETDEL` | `TempPasswordStore.retrieve` | substantiated (shape unchanged) |

**Unresolved, and now more important.** The single-use claim has **never been observed in a test**.
Plan 03 `B1`'s harness note establishes that a production commit escapes the `SAVEPOINT` fixture; if
`retrieve`'s atomicity ever depends on a transaction or a connection-affecting call, the guarantee is
untested. Treat the single-use property as **unverified**, not as working. See **DP-3**.

**Seams.** `core/temp_password_store.py::{retrieve, delete}`; `api/routes/admin.py::reset_user_password_admin_retrieve_endpoint`; `config.py::temp_password_ttl_seconds`.
**Tests pinning current behaviour:** `tests/api/test_temp_password_retrieval.py::{test_retrieve_temp_password_not_found, test_retrieve_temp_password_expired, test_retrieve_temp_password_single_use}` — the last asserts 200-then-404 only.

### AUTH-007 — Admin bootstrap logs "ensured" for every startup (MEDIUM)

| Claim | Current behaviour (anchor) | Verdict |
| --- | --- | --- |
| `ON CONFLICT (email) DO NOTHING`, no rowcount/role check | `db/starter.py::ensure_admin_user` — `INSERT … ON CONFLICT (email) DO NOTHING`; no `SELECT role` | substantiated |
| Unconditional success log | Same method, after `async with db.begin()` | substantiated |
| Runs before the environment gate | `db/starter.py` calls `ensure_admin_user()` in its startup sequence ahead of the `configured_env` gate | substantiated |
| Dev/production-startup logging is not distinguishable | Single logger, no environment tag | substantiated |
| Docs already claim the correct behaviour | `docs/06-backend/logging.md` shows `"Admin user created successfully: admin@example.com"` — a message the code never emits | substantiated |

**Validator note confirmed.** `config.py` now has `is_weak_admin_password` / `is_weak_admin_username`
helpers (and `WEAK_USERNAMES`), yet a second, inline `.lower() in WEAK_USERNAMES` form still survives
inside a validator. The de-duplication lead is real; it is a code-hygiene item, not an AUTH-007 target.

**Seams.** `db/starter.py::ensure_admin_user`; `config.py::{is_weak_admin_password, is_weak_admin_username, WEAK_USERNAMES, admin_username, admin_password}`; `docs/06-backend/logging.md`; `docs/06-backend/architecture.md` (bootstrap subsection).

### AUTH-008 — Redis degradation is fail-open at the revocation boundary (MEDIUM)

| Claim | Current behaviour (anchor) | Verdict |
| --- | --- | --- |
| Revocation read swallows `RedisError` | `core/security.py::is_token_revoked`, `::is_refresh_token_revoked`, `::is_user_tokens_revoked` each `try/except Exception → return False` | substantiated |
| Logs `warning`, no `extra` | Same three functions | substantiated |
| Admin doc advertises graceful degradation | `docs/08-security/security-overview.md` revocation table row ("degrades gracefully (logged at WARNING level)") | substantiated |
| Generic gate swallows the fault | `api/deps.py::get_current_user_dependency` terminal `except Exception` → `AUTHENTICATION_FAILED`; drift `+3` lines from the report's range (the working-tree `deps.py` edit adds three lines above it) | substantiated |
| The counterpart limiter does not fail open | `core/security.py::AsyncRateLimiter.check_rate_limit` `except Exception` → `logger.critical` when `_fail_closed` | substantiated (report cites the **sync** variant's `logger.critical` block; the `AsyncRateLimiter` equivalent is a separate block further down the same method family) |

**Seams.** `core/security.py::{is_token_revoked, is_refresh_token_revoked, is_user_tokens_revoked}`; `api/deps.py::get_current_user_dependency`; `routes/auth.py::{refresh, logout}`; `core/permissions.py::_get_current_user_with_session`; `docs/08-security/security-overview.md`.
**Frontend:** `shared/api/axiosInstance.ts` has **two** identical sign-out blocks; `shared/api/errorHandler.ts` extracts `code` and `shared/api/errorMessages.ts` maps `RATE_LIMIT_EXCEEDED` — so an added code reaches the UI only if the enum mapping is extended.

---

## 3. Cross-cutting architecture and constraints

| Seam | Shape today | Shared with | Owner phase |
| --- | --- | --- | --- |
| Access-token gate | `api/deps.py::get_current_user_dependency` → signature, `is_token_revoked`, `is_user_tokens_revoked`, row lookup, `is_active` | 03 (`B1` made the `is_active` re-read load-bearing), 05 | **04** (AUTH-003/008) |
| Cached/second gate | `core/permissions.py::get_current_user` → `_get_current_user_with_session`; **no `src/` caller**, only `tests/test_permissions.py` | — | 04 (AUTH-003/008 inventory) |
| Revocation primitives | `core/security.py::{revoke_token, revoke_refresh_token, revoke_all_user_tokens}` + the three `is_*_revoked` readers | 03 (`B1` pairs the deactivation commit with Redis) | **04** (AUTH-004/008) |
| Refresh cookie | `routes/auth.py::_handle_login` → `set_secure_cookie`; `routes/auth.py::refresh` reads `COOKIE_NAME` and **does not rotate** it | 05 (session lifetime) | **04** (AUTH-001 key only) |
| Login surface | Two routes (`login`, `login_form`) share `_handle_login` | — | 04 |
| Temp-credential store | `core/temp_password_store.py` (Redis, TTL from `config.py::temp_password_ttl_seconds`); two producers in `AuthService`, one consumer route | 02 (`B7`/`TOPO-006` owns the ordering, landed) | **04** (AUTH-001/002/006) |
| Admin bootstrap | `db/starter.py::ensure_admin_user`; predicates in `config.py` | 01 (`B3` owns the weak-credential predicates) | **04** (AUTH-007 logging) |
| Error surface | `AppException` + `ErrorCode` → status via `utils/exceptions.py` map; `ErrorCode.SERVICE_UNAVAILABLE` exists and is unused on any auth path | 15 (error-format consolidation) | 04 (new codes must not bypass the map) |
| Client IP | nginx sets `X-Real-IP` / `X-Forwarded-For`; uvicorn trusts no proxy; Vite dev proxy sets `changeOrigin` only | 12 (nginx) | **04** (uvicorn trust flag) |
| Rate limiter | `core/security.py::AsyncRateLimiter`, `config.py::rate_limiter_fail_closed` (default `True`); test harness stubs `check_rate_limit` in `tests/conftest.py` | — | 04 |

**Hard constraints for any implementor.** One `ValueError`→`VALIDATION_ERROR`→**422** path is the only
duplicate-email mapping; `ErrorCode.EMAIL_ALREADY_EXISTS` (409) exists and is unused. `IUserService`
gained a commit contract in worktree. `admin_responses` currently declares 401/403/404/422/429/500 —
adding a code changes the declared contract. No `IntegrityError`/`SQLAlchemyError` handler exists in
`src/`.

---

## 4. In-flight and already-landed work

| Ref | State | Symbol it touches | Phase-04 consequence |
| --- | --- | --- | --- |
| `2de4156` `refactor(auth): own the approval transaction in AuthService and write the credential after commit` | **Committed** (child of `b646ef1`; 6 files, +378/−50) | new `AuthService.approve_registration_request`; `AuthService.reset_password_admin`; `api/routes/admin.py::approve_registration_request_admin_endpoint`; `IAuthService`; `tests/test_auth_service.py` (+378) | Discharges AUTH-002's commit-hoist half; creates the design conflict in **DP-1**; invalidates AUTH-002's `admin.py` anchors; adds four test blockers the report never named |
| `0717b65`, `4a5db54` | Committed (phase 02) | worker reporting / single sweeper | Phase 03's regression guard; AUTH-* unaffected |
| Plan 01 `B3` | Committed | `config.py`, `db/starter.py` | Introduced `is_weak_admin_password` / `is_weak_admin_username`; both files moved again |
| Plan 03 `B1` — **worktree, uncommitted** | In flight | `services/user_service.py::{create_user, update_user_role, update_user_active_status}` (+ commit and `IntegrityError` classifier); `interfaces/service_interfaces.py::IUserService`; `api/deps.py` (+3 docstring lines); `api/routes/admin.py::update_user_active_admin_endpoint`; `db/session.py`; `tests/test_admin_user_management.py`, `tests/test_token_revocation.py`, `tests/test_users_api.py`; new `tests/test_user_service.py` | **Directly changes AUTH-004's premise and the `deps.py` anchors.** `update_user_active_admin_endpoint` is being rewritten in the same route block AUTH-004 targets. Adds `test_create_user_non_duplicate_integrity_error_returns_500`, which will conflict with any new 503 mapping on a sibling endpoint |
| Plan 03 `B0`–`B10` | Planned | `docs/SPEC.md` version rows; `docs/06-backend/architecture.md` (transaction ownership, `B10`) | AUTH-007/008 doc edits must re-read `SPEC.md` and must not take the architecture transaction statement |
| Plan 02 `B7` / `TSK_07` | `status: ready` — but the change is **already on disk** via `2de4156` | same files as `2de4156` | If the task is still queued it will re-apply a landed change; the Planner must sequence around it |
| Plan 03 `C-7` | Notification | `routes/auth.py::refresh`, `services/auth_service.py::login_user` | A live AUTH-004 sub-claim assigned to 04 |

---

## 5. Discrepancies and risks

| # | Risk / discrepancy | Evidence |
| --- | --- | --- |
| R1 | **Four shipped tests encode the opposite of AUTH-002's recommendation**: `test_store_failure_after_commit_returns_success` (asserts 200 + `retrieval_token`), `test_approve_registration_request_store_failure_after_commit_keeps_user`, `test_reset_password_admin_commit_precedes_store` (`order == ["update","commit","store"]`), `test_approve_registration_request_commit_precedes_store` | `tests/test_auth_service.py` |
| R2 | **`docs/04-admin/admin-api.md` documents the fail-open store as accepted behaviour**, including a sequence diagram ending "deliberately after the commit". AUTH-002 must update *or* overturn a shipped doc, not just code | `admin-api.md` transaction-ordering section |
| R3 | **Live inversion hazard**: phase 03 `B1` is making `is_active` durable while `routes/auth.py::refresh` and `login_user` never test it. Any AUTH-004 change and the `B1` change collide in `admin.py` and in the deactivation contract | plan 03 `C-7`, worktree diff |
| R4 | **Security regression risk from an over-broad AUTH-008 fix**: making revocation reads fail-closed converts a silent degradation into a 401/503 on every authenticated request whenever Redis is unavailable — including read paths that currently absorb the fault. The blast radius is the whole API, not the auth surface | `deps.py` gate is the only per-request reader on most routes |
| R5 | **AUTH-005's fix site is a deployment surface, not application code** — no `--forwarded-allow-ips` exists in any `CMD` or compose `command:`; the dev override is Windows-specific (`--reload` + watchfiles) | `docker/Dockerfile`, `docker/docker-compose.override.yml` |
| R6 | **Tests that will break:** `tests/test_rate_limiting.py::test_rate_limit_reset_allow_writes` hard-codes `login:127.0.0.1`; `tests/core/test_temp_password_store.py::{test_store_fail_open_on_error, test_retrieve_fail_graceful_on_error}`; `tests/conftest.py` autouse-stubs `check_rate_limit`; `tests/test_registration_flow.py` approval→`/auth/change-password` flow | as cited |
| R7 | **Stale anchors:** AUTH-002's `admin.py` statements (moved to `auth_service.py`); `deps.py` ranges `+3`; `starter.py::ensure_admin_user` moved again; `docs/08-security/security-overview.md` revocation row `:234 → :252`; `docs/04-admin/admin-api.md` `:396 → :401`; `docs/06-backend/architecture.md` bootstrap rows `:128,:130 → :130,:132`; `docs/07-frontend/pages.md:239` and `:285` repeat two AUTH-003 doc claims the report never named; `core/permissions.py:354` **does not exist** (file ends at 353) | as cited |
| R8 | **Live-stack evidence is not reproducible from the current tree** — the running image is a working-tree snapshot; a rebuild is required before any browser-based confirmation of AUTH-001/002/005 | `docker exec mkobi-app-1 grep -c …` |

---

## 6. Decision points for the Planner (leave open — do not choose)

| # | Uncertainty | Alternatives | Who chooses |
| --- | --- | --- | --- |
| **DP-1** | AUTH-002's fail-open store vs the landed, documented, deliberately-ruled commit-then-store invariant | (a) keep fail-open, change only the *reporting* (return a handle only when the store confirmed, or add an explicit `credential_stored` field); (b) make the store raise and surface **503**, overturning R1/R2; (c) keep behaviour, add compensating observability only | **Tech Lead** — it overturns a shipped ruling (`2de4156`) and shipped docs |
| **DP-2** | AUTH-003's enforcement surface | (a) gate centrally in `api/deps.py::get_current_user_dependency` (but `core/permissions.py` has no `src/` caller, so it is not equivalent coverage); (b) gate per-route; (c) gate only the refresh + change-password + logout flows; (d) leave the API alone and make the frontend the enforcement point (**rejected by the report, but it is the cheapest**) | **Tech Lead** + Planner (security-boundary decision) |
| **DP-3** | AUTH-006's single-use guarantee is unverified | (a) keep `GETDEL` and add an explicit atomicity test; (b) move to `GETSET`-plus-`DEL`; (c) re-verify empirically under the `SAVEPOINT`-escaping harness before changing anything | Planner (verification first), Tech Lead if the store changes |
| **DP-4** | AUTH-001's rate-limit keying | (a) dual key (IP + identifier) with fail-closed on any component; (b) identifier-only; (c) status quo + documentation. `VAL-04-001` has already removed the "add an enabled flag" variant | **Tech Lead** — it trades enumeration resistance for availability |
| **DP-5** | AUTH-005's proxy-trust seam | (a) uvicorn `--forwarded-allow-ips` in `Dockerfile` + both compose files; (b) `ProxyHeadersMiddleware` in `app.py`; (c) terminate trust at nginx only. Each has a different dev/prod/test blast radius | Planner (technical), Tech Lead if nginx or `app.py` is touched |
| **DP-6** | AUTH-008's failure direction | (a) fail closed on revocation reads; (b) fail closed but only on the *user-level* marker; (c) fail open with a new `ErrorCode` surfaced to the client | **Tech Lead** — the choice changes availability behaviour for the whole API |
| **DP-7** | Sequencing against phase 03 `B1` | whether AUTH-004 lands before, after, or merged with the in-flight deactivation rewrite in `api/routes/admin.py::update_user_active_admin_endpoint` | **Coordinator** |
| **DP-8** | Whether the in-flight `B1` worktree edit is committed before phase 04 starts | Plan 03 `C-4` demands AUTH-003/AUTH-004 be re-checked against the *pending* change; that re-check is exactly this document | Coordinator |

---

## 7. Coverage ledger

| Finding | Verdict | Evidence anchors (semantic) |
| --- | --- | --- |
| **AUTH-001** | substantiated (VAL-04-001 correction upheld) | `TempPasswordStore.store`; `AuthService.reset_password_admin`; `AuthService.approve_registration_request`; `routes/auth.py::_handle_login`; `routes/auth.py::refresh`; `AsyncRateLimiter.check_rate_limit`; `config.py::rate_limiter_fail_closed`; `tests/core/test_temp_password_store.py::test_store_fail_open_on_error`; `tests/test_rate_limiting.py::test_rate_limit_reset_allow_writes` |
| **AUTH-002** | **drifted** (commit-hoist already fixed; fail-open + handle claims substantiated; report anchors dead) | `AuthService.approve_registration_request`; `AuthService.reset_password_admin`; `api/routes/admin.py::approve_registration_request_admin_endpoint`; `IAuthService`; `tests/test_auth_service.py::test_store_failure_after_commit_returns_success`; `docs/04-admin/admin-api.md` transaction-ordering section |
| **AUTH-003** | substantiated | `api/deps.py::get_current_user_dependency`; `core/permissions.py::_get_current_user_with_session`; `User.force_password_change`; `AuthService.login_user`; `AuthService.change_password`; `useAuth.ts`; `LoginForm.tsx`; `axiosInstance.ts`; `useAuth.test.tsx` force_password_change describe |
| **AUTH-004** | substantiated **+ new C-7 sub-claim substantiated** | `UserRepository.set_active`; `UserService.update_user_active_status`; `api/routes/admin.py::update_user_active_admin_endpoint`; `core/security.py::revoke_all_user_tokens`; `routes/auth.py::refresh`; `AuthService.login_user`; `tests/test_token_revocation.py::test_user_deactivation_revokes_all_tokens` |
| **AUTH-005** | substantiated | `routes/auth.py::_handle_login`; `routes/auth.py::refresh`; `routes/auth.py::register_request`; `docker/nginx/nginx.conf`; `docker/Dockerfile` `CMD`; `docker/docker-compose.override.yml`; `frontend/vite.config.ts` |
| **AUTH-006** | substantiated (single-use property unverified) | `TempPasswordStore.retrieve`; `api/routes/admin.py::reset_user_password_admin_retrieve_endpoint`; `tests/api/test_temp_password_retrieval.py::test_retrieve_temp_password_single_use` |
| **AUTH-007** | substantiated | `db/starter.py::ensure_admin_user`; `config.py::{is_weak_admin_password, is_weak_admin_username, WEAK_USERNAMES}`; `docs/06-backend/logging.md`; `docs/06-backend/architecture.md` |
| **AUTH-008** | substantiated (sync/async `logger.critical` anchor corrected) | `core/security.py::{is_token_revoked, is_refresh_token_revoked, is_user_tokens_revoked}`; `AsyncRateLimiter.check_rate_limit`; `api/deps.py::get_current_user_dependency`; `errorMessages.ts`; `docs/08-security/security-overview.md` |

**`VAL-04-*` dispositions** — change a target: **001** (drops AUTH-001 option b), **002** (adds
`test_rate_limit_reset_allow_writes` as a blocker), **003** (restates AUTH-005's dev-tier cause),
**007** (converts AUTH-007's documentation note into three concrete edits), **010** (extends the
AUTH-001/AUTH-002 doc inventory). Change evidentiary weight only: **008** (demotes AUTH-006's atomicity
claim to optional). Report-text only, no target change: **004** (count), **005** (evidence framing),
**006** (quote fidelity), **009** (inventory row is test-only).