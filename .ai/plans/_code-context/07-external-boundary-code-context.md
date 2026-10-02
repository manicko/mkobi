---
id: 07-external-boundary-code-context
audit_phase: 07-external-boundary
report: .ai/audit/99-validation/07-external-boundary-validated-findings.md
finding_prefix: EXT-
validation_prefix: VAL-07-
code_context_authority: Phase-1 Auditor (overrides every report anchor)
baseline_read: 2174895
status: complete
---

# Phase 07 — External boundary: code context (Phase-1 Auditor)

## 1. Scope and method

| Item | Value |
|---|---|
| Report under decomposition | `.ai/audit/99-validation/07-external-boundary-validated-findings.md` (1325 lines, 100,906 B) |
| Finding-ID prefix actually used | **`EXT-`**, `EXT-001` … `EXT-010`, no gap, no collision (declared at `07-audit-external-boundary.md:139` per the report's Appendix G) |
| Report-level defects | **`VAL-07-`**, `VAL-07-001` … `VAL-07-011` (11) |
| Report's own baseline | `c3c0a61` (2026-10-01 audit date 2026-09-30) |
| **Baseline read for this context** | **`2174895`** at start; **`cea2d06`** at completion (see §1.1 — no anchor moved) |
| Verified **by execution** | `GET /openapi.json` on the live dev stack (`localhost:8010`); `GET /health`; `GET /health/detailed`; `docker exec mkobi-app-1` reads of `uvicorn.Config` and `redis.asyncio.Redis().connection_pool.connection_kwargs` |
| Verified **by reading** | everything else — every symbol, anchor, test, doc line and compose key below was resolved against files on disk |
| **Not** re-run | the 5 MB `client-errors` body, the Redis-pause outage, the `X-Forwarded-For` five-key reproduction (each mutates shared state other agents are using) |

### 1.1 HEAD-vs-worktree split

Nine commits stand between the report's `c3c0a61` and this context's `2174895`. Two land findings; four
invalidate anchors.

| Commit | Subject | Effect on phase 07 |
|---|---|---|
| `d008f55` | docs(deploy): resolve the CORS_ORIGINS contradictions | moves the `app.py` CORS guard (VAL-07-009) |
| `3848e7a` | submit background work to RQ | **`rq` becomes genuinely imported** → EXT-009 drift |
| `9c49c20` | gate the reverse proxy on application readiness | **dev healthcheck re-enabled**; `health-api.md:196` rationale added → refutes EXT-001's dev refinement |
| `9c49c20` + `4a5db54` | readiness gate, reconciler lease | **third `/health/detailed` component**; `app.py` now references Redis |
| `3856f27`…`9a77625`, `b646ef1`, `a92b546` | rq-worker liveness, lifespan teardown, lease | outside every `EXT-*` target |
| **`2de4156`** | **own the approval transaction in AuthService and write the credential after commit** | **EXT-008 already-fixed**; EXT-005 anchors dead |
| `2174895` | own the unit of work for user writes | outside every `EXT-*` target |
| `cea2d06` | test(users): clean up rows the durable user writes now persist | committed the five files that were dirty; **no `EXT-*` anchor moved** |

Dirty tracked files at session start — `src/mkobi/api/routes/admin.py` (7 lines, **docstring only**),
`src/mkobi/services/user_service.py` (3 lines, **comment only**), three test files (CRLF/whitespace
only) — **were committed by another agent as `cea2d06` while this context was being written.** No
`EXT-*` anchor moved. Untracked: the six sibling plans, `.ai/plans/_code-context/`, one `.ai/tasks/`
yaml. Deleted trees (`.ai/builders`, `.ai/structure`, `.ai/models`, `.ai/templates`,
`frontend/coverage`) predate the audit and are not targets.

**Anchor drift summary.** Of ~40 cited line anchors: **9 resolve exactly, 21 resolve to the same symbol
at a shifted line, 8 no longer name anything** (the `admin.py` approval bodies). VAL-07-009's own table
is **also stale** — it corrected anchors to `b23a9cb`, and `HEAD` has moved twice since. **Every anchor
below is recorded as a symbol; the Planner must resolve by symbol.**

---

## 2. Per-finding context

### EXT-001 — health probe reports `healthy` while authenticated requests fail

| Field | Value |
|---|---|
| **Verdict** | **drifted** — substantive claim substantiated; two evidence claims and the recommendation's blocker are now wrong |
| Load-bearing symbols | `app.py::create_app` → `health_check` (`:297-316`), `detailed_health_check` (`:318-379`); `deps.py::get_current_user_dependency` (`:475`) → `security.py::is_token_revoked` (`:492`, `exists` at `:503`), `::is_user_tokens_revoked` (`:542`, `exists` at `:553`) |

| Claim | Report | Code today |
|---|---|---|
| `/health` probes only PostgreSQL | `app.py:257-276` | **True.** `app.py:304-310`, `SELECT 1` at `:307`, returns `{"status":"healthy","database":"connected"}` at `:308-310` |
| `/health/detailed` cannot return non-200 | returns `dict[str, Any]` | **True.** `:319` signature, `:379` bare return |
| `Select-String "redis"` over `app.py` → **zero** matches | 0 matches | **REFUTED.** 5 matches: `:22` import `get_async_redis_client`, `:131` lease client, `:138`/`:198` comments, `:356` comment |
| `/health/detailed` has 2 components | db + static | **drifted.** 3: `database`, `static_files`, `stale_processing_reconciler` (`:360-376`) |
| Docker HEALTHCHECK disabled in dev | `override.yml:111-112` | **REFUTED.** Now inherited — `docker-compose.override.yml:120-121` comment, no `disable` |
| Probe blind to Redis, 503 on failure | — | `docker/Dockerfile:180-181` `curl -f /health`; `docker/docker-compose.yml:157-162` (30s/10s/3, `start_period: 40s`) |

**Runtime confirmation (read-only GETs).** `/health` → `{"status":"healthy","database":"connected"}`;
`/health/detailed` → `status=healthy components=database,static_files,stale_processing_reconciler`.

**Seams an implementor would touch.** `app.py::health_check`; `app.py::detailed_health_check`;
`core/redis_client.py` (for a ping helper); `docs/05-health/health-api.md:100-138, 196, 247-249`.

**Three things the report missed — all blocking or decision-shaping.**
1. **`tests/test_health.py:191-238` `TestHealthWithRedisDown::test_health_still_healthy_when_redis_down` asserts the defect.** `:233` is an **exact dict equality** `== {"status": "healthy", "database": "connected"}`; `:237` asserts `detailed["status"] == "healthy"`. Adding a `redis` key to `/health` **breaks this test**. The report's "no shipped test blocker" is **refuted**; the report only checked the *detailed* assertions at `test_health.py:110-125`, which are membership-only and do survive.
2. **The behaviour is a documented, reasoned decision.** `docs/05-health/health-api.md:196`: *"`/health` is what the container healthcheck curls and what `nginx` gates on … If reconciler or lease state fed that endpoint, then during any Redis blip three of the four workers would report unhealthy and the reverse proxy would refuse to start … `/health` therefore keeps meaning one thing only: *the database is reachable*."* `app.py:355-359` carries the same decision as a code comment.
3. **Doc self-contradiction.** `health-api.md:108` / `:137` say the overall `status` reflects the worst component; `:138` and `app.py:355-359` say the reconciler component never does. Only the **database** failure can set `unhealthy` (`app.py:340-346`).

---

### EXT-002 — one Redis outage takes down every page, reported as a bad credential

| Field | Value |
|---|---|
| **Verdict** | **substantiated** (blast radius + undeclared bound); the 401-on-outage mechanism **already fixed** in the sense that it is now owned and ruled by plan 04; anchors shifted +3 |

| Symbol | Report anchor | Anchor today |
|---|---|---|
| `core/redis_client.py::get_async_redis_client` → `aioredis.Redis(...)` | `:46-52` | **`:46-52` — exact.** Only `host`, `port`, `db`, `password`, `decode_responses` |
| `api/deps.py::get_redis_client_dependency` | `:475` | `:125-131` (`:475` is now `get_current_user_dependency`) |
| `deps.py::get_current_user_dependency` → `is_token_revoked` | `:506` | `:509` |
| `deps.py::get_current_user_dependency` → `is_user_tokens_revoked` | `:526` | `:529` |
| `deps.py` catch-all → `AUTHENTICATION_FAILED` "Authentication failed" | `:570-576` | **`:573-579`** |
| `security.py::is_token_revoked` / `::is_user_tokens_revoked` | `:502-504` / `:552-554` | `:503` / `:553` (one line off) |
| `jti` always present | `security.py:286, 327` | **exact** |

**Runtime confirmation of the undeclared bound (from the running image).**
`redis 8.0.0` · `socket_timeout=5` · `socket_connect_timeout=5` · `retry=Retry` **`retries=10`** ·
`ExponentialWithJitterBackoff(cap=1, base=0.01)`. No code in `src/` sets any of these.
`uvicorn 0.49.0`, `forwarded_allow_ips='127.0.0.1'`, `proxy_headers=True`.

**A fourth and fifth revocation call site the report did not name.** `core/permissions.py:326` and
`:332` call the same two functions inside `_get_current_user_with_session` (`:291`). Plan 04's VAL-04-009
records that function as having **no src-level caller**, so it adds no blast radius — but it is a
**fifth and sixth edit site** for any `RedisError` guard, and a silent one.

**Where a bound would live.** `config.py:319` `class RedisSettings`, `config.py:556`
`redis: RedisSettings = RedisSettings()`, and `config.py:335` already puts
`("redis", RedisSettings, ("password",))` in the `SECRET_FIELD_REGISTRY` (so `REDIS__PASSWORD_FILE` is
wired). Whether the transport bounds belong on `RedisSettings` or inline in `redis_client.py` is a
config-seam overlap with phase 01 — **DP-3**, unruled in every existing plan.

---

### EXT-003 — anonymous 5 MB body logged verbatim, no field cap

| Field | Value |
|---|---|
| **Verdict** | **substantiated and strengthened** — the one named first-party caller does not exist |

Every anchor resolves **exactly**: `client_errors.py:21` router (`redirect_slashes=False`, no
credential), `:42` `client_ip = request.client.host if request.client else "unknown"`, `:45-50`
`AsyncRateLimiter(..., fail_closed=config.rate_limiter_fail_closed)` and key `client-errors:{client_ip}`
100/3600 s, `:62-68` the unbounded `logger.error` of `payload.error.get("message", …)`, `payload.url`,
`payload.componentStack`. `models/data.py:504-528` `ClientErrorPayload` — `error: dict[str, Any]`
at `:511`, `model_config` at `:517-527` carrying only `from_attributes` + `json_schema_extra`, **no
`extra`, no `max_length` on any of the five fields** (`:511-515`). No `Content-Length` check on the route.
Ceiling: `docker/nginx/nginx.conf:18` `client_max_body_size 100m`, un-overridden by `location /api` (`:34`).

**The report's compatibility caveat is refuted.** It names
`frontend/src/shared/components/ErrorBoundary.tsx:40` as "the one shipped caller" to check before
narrowing `ClientErrorPayload.error`. That file is **47 lines** and contains no such call;
`Select-String 'client-errors'` across all of `frontend/src/` returns **zero** matches. **There is no
first-party caller of `POST /api/v1/client-errors`.** Narrowing `error` to a strict model therefore has
**no first-party regression risk**; the only caller is an external browser. The report's "usable, but
check the frontend reporter" verdict in Appendix E is stale in the implementor's favour.

---

### EXT-004 — the whole inbound budget collapses onto the proxy's address

| Field | Value |
|---|---|
| **Verdict** | **substantiated** (mechanism runtime-confirmed); **merged** into AUTH-001 and already owned by plan 04; one sub-claim **refuted**; anchors drifted |

Mechanism re-confirmed from the running image: `uvicorn 0.49.0`, `proxy_headers=True`,
`forwarded_allow_ips='127.0.0.1'`. Neither `docker/Dockerfile:183` (prod `CMD`, `--workers 4`) nor
`docker/docker-compose.override.yml:119` (dev `CMD`, `--reload`) passes `--forwarded-allow-ips`;
`Select-String` finds **no** `forwarded-allow-ips` / `forwarded_allow_ips` / `always_trust` anywhere in
`src/` or `docker/`. `docker/nginx/nginx.conf:38` sets
`X-Forwarded-For $proxy_add_x_forwarded_for` — **appends**, so a caller-supplied left-most entry survives.

**All five bounds resolve at the right symbols, two with shifted lines.**

| Bound | Report | Today | Keyed on |
|---|---|---|---|
| `login:` 5/300 s | `auth.py:83-90` | `auth.py:83-89` | `request.client.host` or `"unknown"` (`:83`) |
| `refresh:` 10/300 s | `auth.py:309-315` | **`:309-315` exact** | same (`:309`) |
| `register-request:` 3/3600 s | `auth.py:566-568` | **`:566-568` exact** | `str(ip_address(host))` (`:557-559`) |
| `client-errors:` 100/3600 s | `client_errors.py:49-50` | **`:49-50` exact** | `request.client.host` or `"unknown"` (`:42`) |
| `upload:` 100/3600 s | `upload.py:144-148` | `upload.py:144-152` | `current_user.id` — unaffected, correctly excluded |

**The "email branch is unreachable" claim is refuted for `register-request`.** The report reasons from
`auth.py:83` and `client_errors.py:42`, where the fallback is the *string* `"unknown"` — correct there.
But `routes/auth.py:557-559` declares `client_ip: str | None = None` and assigns only
`if request.client:` — so at `auth.py:566` the email branch is **reachable** exactly when
`request.client is None`. Two further facts the report missed: `register-request:` normalises through
`ip_address()` while the other two use the raw `host`, so the three keys are not even built the same
way; and `ip_address()` raises `ValueError` on a non-IP peer string, which is unhandled at `:559`.

**Ownership is already taken.** Plan 04 (**`source_head: 2174895`**, same as this context) owns
**AB-7 "Proxy trust for the effective client IP"** and **AB-6 "Rate-limit key identity"**, and has
already **applied** VAL-04-001: *"Option (b) of AUTH-001's remedy is **deleted**, not deferred"*.
VAL-07-002's wildcard prohibition is therefore **already ruled** — the Planner must not re-open it.

---

### EXT-005 — approval returns 200 and a handle for a credential never stored

| Field | Value |
|---|---|
| **Verdict** | **substantiated on the write side**, **refuted as a route-level finding** (bodies moved); merged into AUTH-002, owned by plan 04 **AB-1** |
| Symbols | `auth_service.py::AuthService.approve_registration_request` (`:607-679`); `auth_service.py::AuthService.reset_password_admin` (`:540-605`); `admin.py::approve_registration_request_admin_endpoint` (`:315-361`); `admin.py::retrieve_temp_password_admin_endpoint` (`:426-439`); `core/temp_password_store.py::TempPasswordStore.store` (`:30-48`) |

**Every `admin.py` anchor the report cites is dead.** `admin.py:307` `create_user`, `:315`
`force_password_change`, `:320` `uuid4`, `:321` `store`, `:324` `update_status(APPROVED)`, `:330`
`db.commit()`, `:339-345` rollback — **none is in `admin.py` today**. The route (`:342-346`) is a
three-line delegation to `auth_service.approve_registration_request`. The report independently
predicted the result; the Planner should not spend an anchor budget on `admin.py:307-345`.

**The defect survives, with a deliberate shape.**

| Step | `auth_service.py` | Note |
|---|---|---|
| create user | `:647-652` | uncommitted |
| set `force_password_change` | `:655` | uncommitted |
| mark `APPROVED` | `:657-662` | uncommitted |
| `await db.commit()` | **`:663`** | |
| `retrieval_token = str(uuid4())` | `:667` | |
| `await self.temp_password_store.store(...)` | **`:669`** | guarded by `if self.temp_password_store is not None` at `:668` |
| return `{"retrieval_token": retrieval_token}` | **`:675-679`** | **unconditional** — the handle is returned whether or not the store succeeded |

`TempPasswordStore.store` is still `-> None` and still swallows at `temp_password_store.py:47-48`
("Failed to store temp password in Redis" at ERROR). The docstrings at `auth_service.py:617-624`
**state the residual in prose**: *"a failure after the commit leaves an existing user with a
not-yet-retrievable credential (recoverable) instead of a live retrieval token pointing at a user who
does not exist"* and *"a non-raising call is not proof that the credential is retrievable"*.
So EXT-005's core claim — 200 + a dead handle — is **true and knowingly accepted**.

**Read side still one 404 for two states.** `admin.py:433` `retrieve(...)`; `:434-438` maps `None` to
`AppException(NOT_FOUND, "Temporary password not found or already retrieved")`. `retrieve` returns
`str | None` (`temp_password_store.py:50`) with **two** states (absent-or-spent, store-fault), not
three — plan 04's Z-14 records the same. Plan 04 **AB-2** owns it.

**VAL-07-008 confirmed verbatim.** `tests/core/test_temp_password_store.py:164-181`
`test_store_fail_open_on_error` and `:184-190` `test_retrieve_fail_graceful_on_error` are byte-identical
to what the report quotes. Additionally `tests/test_admin_user_management.py:619-641`
`test_reset_user_password_admin` asserts `200` + `retrieval_token` present — a fourth pin the report
did not list.

---

### EXT-006 — credential check runs after the router's slash redirect

| Field | Value |
|---|---|
| **Verdict** | **substantiated**, **runtime-confirmed** at exactly the corrected scope (4 paths, not 43) |

`redirect_slashes=False` is set on **twelve** routers — VAL-07-010(b) confirmed: `auth.py:68`,
`admin.py:31`, `client_errors.py:21`, `dashboards.py:20`, `dashboards_crud.py:45`, `data.py:36`,
`graphs.py:42`, `upload.py:48`, `layouts.py:40`, `processing_logs.py:28`, `processing_configs.py:33`,
`users.py:37`. All twelve lines exact. As the report states, the flag does not suppress the
no-slash→slash direction.

**Runtime enumeration (live `/openapi.json`).** `pathCount = 43`; trailing-slash paths are exactly
**`/api/v1/users/`, `/api/v1/dashboards/`, `/api/v1/graphs/`, `/api/v1/admin/logs/`**;
`/api/v1/dashboards` is **absent** while `/api/v1/dashboards/` is present. **VAL-07-007 confirmed and
independently reproduced.** No test asserts a `307` (`Select-String 'status_code == 307'` over `tests/`
→ only two unrelated docstring hits).

---

### EXT-007 — no request-body model declares a strictness policy

| Field | Value |
|---|---|
| **Verdict** | **substantiated**, every anchor exact |

Re-enumerated against disk. **Seven** `extra` policies exist and all seven are exactly the ones filed:

| Policy | Location | Count |
|---|---|---|
| `extra="forbid"` | `models/transformation_configs.py:133` | 1 |
| `{"extra": "allow"}` | `models/types.py:47, 247, 260, 279, 292, 305` | 6 |

Deferred boundaries resolve exactly: `routes/data.py:54` `filters: str | None = Query(default=None, …)`;
`data.py:106-115` `json.loads(filters)` **outside** the model layer, inside a `try` that maps
`json.JSONDecodeError` → `AppException(VALIDATION_ERROR)` at `:112-115`; `types.py:138`
`class GraphConfigDict(TypedDict, total=False)`; `models/graph.py:15` `config: GraphConfigDict` and
`:45` `config: GraphConfigDict | None = None`.

**Two corrections to the report's framing.** (a) The report's "64 `BaseModel` subclasses" is the
**file-local** count and its own re-derivation of 76 is the import-reachable count; I reproduce **64**
by file-local grep, so both figures stand and neither is an error — but only the **0-of-21** figure is
load-bearing, and a regex census of route signatures yields **20** model-shaped candidates
(`LoginRequest`, `RegisterRequest`, `RegistrationRequestCreate`, `UserCreateRequest`,
`UserUpdateRequest`, `UserUpdateActiveRequest`, `ChangePasswordRequest`, `DashboardCreate`,
`DashboardUpdate`, `GraphCreate`, `GraphUpdate`, `LayoutCreate`, `LayoutUpdate`, `ClientErrorPayload`,
`ProcessingConfigUpdate`, …). **The Planner must re-derive the exact set by symbol, not by count.**
(b) The report's Consequence — "the caller gets an empty result set or a later error rather than a
`422`" — is **wrong for syntactically invalid `filters`**, which does yield a 422-class
`AppException`. What is unvalidated is the **document shape** of a well-formed object, and that is what
reaches the repository. The severity of the finding is unaffected; the wording is.

`SELECT`-safety re-confirmed: `db/repositories/aggregated_data_repo.py` builds
`AggregatedData.dims[key].astext == str(value)` as a SQLAlchemy expression — no interpolation.

---

### EXT-008 — the credential write is ordered before the commit that records it

| Field | Value |
|---|---|
| **Verdict** | **already-fixed** — landed as `2de4156` (phase-02 block B7 / **TOPO-006**) and pinned by three shipped tests. The **compensation** half is not done and is **contradicted** by landed work. |

This is the largest single change in the report's status. The prescribed ordering exists today:

```
auth_service.py:647 create_user  →  :655 update(force_password_change)  →  :657 update_status(APPROVED)
  →  :663 db.commit()          →  :667 uuid4()                       →  :669 store(...)
```

**Three shipped tests now pin it** (`tests/test_auth_service.py`, all landed with `2de4156`):

| Test | Line | Pins |
|---|---|---|
| `test_approve_registration_request_commit_precedes_store` | `:619-665` | `order.index("store") > order.index("commit")`; docstring says *"It pins TOPO-006's fix"* |
| `test_approve_registration_request_failed_commit_leaves_no_credential` | `:667-712` | `store.store.assert_not_called()` when the commit raises |
| `test_approve_registration_request_store_failure_after_commit_keeps_user` | `:714-757` | a store failure **keeps** the user; `retrieval_token` still returned; `db.commit()` still called |

`AuthService.reset_password_admin` carries the same fixed order: `:585-589` update → **`:590`** commit →
`:594` uuid4 → `:595-596` store → `:601-605` return. Both docstrings (`:549-554`, `:615-624`) argue the
ordering **on purpose**.

**VAL-07-005's prescribed outcome is now contested.** The report ruled: *"commit the durable record
first, then publish the credential, and on a publish failure **compensate the committed record (mark
the request failed and remove the account)**"*. The shipped code chose **commit-first, publish-after,
no compensation, keep the user** — and
`test_approve_registration_request_store_failure_after_commit_keeps_user` asserts exactly that.
Adopting VAL-07-005 literally **reverses a shipped test, a shipped docstring and
`docs/04-admin/admin-api.md`**. The one-line trigger for the "compensated delete in the window between
commit and delete" hazard the report's Rollout Safety predicts (`DUPLICATE_RESOURCE` on retry) is
therefore **not** the code's current behaviour.

---

### EXT-009 — the startup self-check certifies four libraries the app never imports

| Field | Value |
|---|---|
| **Verdict** | **drifted** — the arithmetic changed from four gate-only libraries to **three**; `rq` is now genuinely used |

`main.py:10-25` `REQUIRED_MODULES` resolves **exactly** (httpx `:14`, plotly `:16`, rq `:23`,
tenacity `:24`; `requests` correctly absent). `check_dependencies()` `:28-47` with `__import__` at `:37`
and `raise SystemExit(1)` at `:47`; the gate runs at import time `:50`, before
`from mkobi.app import create_app` at `:52`. All anchors exact.

**But the "never imported" census is now wrong for one of the four.** `3848e7a` made RQ real:

| Library | `src/` import sites today | Status |
|---|---|---|
| `httpx` | 0 (only the `main.py:14` literal) | still gate-only |
| `tenacity` | 0 (only the `main.py:24` literal) | still gate-only |
| `plotly` | 0 (3 comment/docstring mentions only) | still gate-only |
| **`rq`** | **39 matches**, incl. `rq_worker_wrapper.py:15,16,17` and `:220-221` (`rq.Queue`, `rq.Worker`) | **genuinely imported** |

So `REQUIRED_MODULES` is 14 names, **3** of which certify an absence and **1** of which (`rq`) is a
real contract for the *worker* entrypoint that `check_dependencies()` happens to share with the API
app. The report's own caution — *"establish intent for `httpx` and `tenacity` before touching them"* —
is right and now extends to `plotly` alone. **Do not remove `rq`; the recommendation never said to,
and the "twelve the application imports" figure is now wrong.**

---

### EXT-010 — the schema document advertises a stale version; only half of it is tier-gated

| Field | Value |
|---|---|
| **Verdict** | **drifted** — the literal is already gone (half already-fixed); the tier gate is unchanged and substantiated |

| Claim | Report | Code today |
|---|---|---|
| `app.py` passes the literal `version="1.0.0"` | `app.py:218` | **REFUTED as written.** `app.py:258` is `version=config.app.version` — the literal was removed by `eeb9a5e`. `config.py:449` carries `version: str = "1.0.0"` (report said `:320`, then `:383`) |
| `docs_url`/`redoc_url` gated on production | `app.py:220-221` | **True.** `app.py:260-261` |
| `openapi_url` ungated | — | **True.** `Select-String 'openapi'` over `app.py` → **0 matches** |
| `pyproject.toml` `version = "1.0.8"` at line 7 | line 4 (VAL-07-010a) | **Confirmed at line 7** |
| Served document reports `1.0.0` | — | **Runtime-confirmed:** `openapi version = 1.0.0, title = mkobi, pathCount = 43` |

So the report's second half ("source the version from the installed distribution metadata rather
than a literal") is **already half-done** — the app now reads `config.app.version`, but *that* value is
still a hand-written `"1.0.0"` in `config.py:449`, so the drift is unchanged. The one source of truth
the report asks for does not exist. `APP_VERSION` appears nowhere in `src/`, `docs/` or `frontend/src/`.
`nginx.conf:34` (`location /api`) and `:43` (the two health paths) mean `/openapi.json`, `/docs` and
`/redoc` fall through to `location /` (`:49`) and get the React bundle — the production protection is
nginx's, not the app's.

---

## 2.1 Report-level defects (`VAL-07-*`)

The eleven `VAL-07-*` records are defects **in the report**, not in the code. Their verdicts below say
whether each still changes a remediation target. Six do; two are overtaken by landed work; three are
cosmetic.

| ID | Subject | Verdict today | Changes a target? |
|---|---|---|---|
| **VAL-07-001** | EXT-005 duplicates AUTH-002 + AUTH-006, filed with no merge ruling | **substantiated and escalated** | **Yes.** The bodies it names have since moved out of `admin.py` entirely (see EXT-005). A ticket against `admin.py:321` lands on a delegation. |
| **VAL-07-002** | EXT-004's `forwarded-allow-ips="*"` is a caller-chosen bucket | **substantiated**; mechanism re-confirmed at runtime | **Yes — already ruled.** Plan 04 records VAL-04-001 **applied**: *"Option (b) of AUTH-001's remedy is deleted, not deferred."* Inherit the ruling; do not re-open. |
| **VAL-07-003** | EXT-002's claim that `SERVICE_UNAVAILABLE` does not exist | **substantiated** | **Yes.** `models/enums.py:225` inside `class ErrorCode(StrEnum)` at `:216`; mapped to 503 at `utils/exceptions.py:36`; title at `:187`. Report's anchors (`:188`, `:197`) are stale; the claim stands. **No new enum member.** |
| **VAL-07-004** | EXT-002's refusal class duplicates AUTH-008 at the same sites | **substantiated — and the site list is larger** | **Yes.** Plan 04 **AB-5** owns it. Phase 07 keeps only blast radius + undeclared bound. **Six** call sites, not two: `deps.py:509`, `deps.py:529`, `permissions.py:326`, `permissions.py:332`. |
| **VAL-07-005** | EXT-005/EXT-008/AUTH-002 prescribe three orderings; the report picks a fourth | **refuted in its prescribed outcome** | **Yes, decisively.** The ordering half is **already-fixed**; the compensation half it prescribes (*"mark the request failed and remove the account"*) is **contradicted** by `test_auth_service.py:714-757`, by `auth_service.py:617-624` and by `docs/04-admin/admin-api.md`. Do not schedule as written. |
| **VAL-07-006** | EXT-002's "three retries of a 5 s timeout" is wrong; the library retries ten | **substantiated — runtime-confirmed** | **Yes, as a wording correction only.** Measured: `retries=10`, `ExponentialWithJitterBackoff(cap=1, base=0.01)`, `socket_timeout=5`. The *conclusion* is unaffected. |
| **VAL-07-007** | EXT-006 overstates the enumeration surface ~10× | **substantiated — runtime-confirmed** | **Yes.** 4 paths, exactly as corrected. Scope the Recommendation to `/api/v1/users/`, `/api/v1/dashboards/`, `/api/v1/graphs/`, `/api/v1/admin/logs/`. |
| **VAL-07-008** | EXT-005/EXT-008 blocked by two shipped tests the reports deny | **substantiated verbatim** | **Yes.** `tests/core/test_temp_password_store.py:164-181` and `:184-190` unchanged. A **fourth** pin the report missed: `tests/test_admin_user_management.py:619-641`. |
| **VAL-07-009** | nine anchors moved and are now committed | **substantiated and superseded** | **Partly.** Its correction table targets `b23a9cb`; `HEAD` is `2174895`, two commits later. The table is **itself stale**. Keep the method, discard the numbers. |
| **VAL-07-010** | four evidence anchors and one search characterisation are wrong | **substantiated for (a)–(c); (d) overtaken** | **Marginally.** (a) `pyproject.toml:7` confirmed; (b) twelve routers confirmed exactly as listed; (c) confirmed; (d) superseded by VAL-07-001. **A fifth error exists that VAL-07-010 does not name:** EXT-004's "email branch is unreachable". |
| **VAL-07-011** | the report's restoration claim omits five `bidb` rows | **not actionable for the Planner** | **No.** It is a claim about the report's own prose. A Planner must not create or delete DB rows; if the Coordinator wants them gone, that is a separate authorised action. |

**The one record that changes a *target* rather than a *wording*** is VAL-07-005 — the only one whose
prescribed remediation is already implemented **and tested in the opposite shape**. VAL-07-002 and
VAL-07-003 change targets only by **deleting** options other reports offered.

---

## 3. Cross-cutting architecture and constraints

### 3.1 The external boundary as it exists

**The report's headline negative result holds: there is no outbound boundary.** Search over all `.py`
files under `src/`: **zero** `httpx`, `aiohttp`, `openai`, `anthropic`, `boto3` or outbound-socket call
sites. `httpx` and `tenacity` exist only as strings in `REQUIRED_MODULES`. The *only* external
dependency in production is **Redis**; the only external *surface* is the browser.

| Redis use | Client obtained from | Declared timeouts / retries? |
|---|---|---|
| Rate limiting (4 inline sites) | `core/redis_client.py::get_async_redis_client` (`:33-52`) | **No** — all three are library defaults |
| Token revocation | same, via `deps.py::get_redis_client_dependency` (`:125-131`) | **No** |
| Temp-password store | same, via `deps.py::get_temp_password_store` (`:137-152`) | **No** |
| Reconciler lease | `app.py:131`; one per process, closed in `lifespan`'s `finally` | **No** |
| RQ broker | `rq_worker_wrapper.py::_build_redis_url` (`:43-50`); worker container only | `check_redis_connection` retries 3× with its own backoff (`:69-100`) — **the only declared retry in `src/`** |
| PostgreSQL | `db/session.py`; `app.py::health_check` / `detailed_health_check` | pool settings in `config.py` |

**There is no HTTP client layer, no outbound-service abstraction in `interfaces/` (service ABCs only),
and no `tenacity` usage in `src/`.** No finding asks for one; a remedy that needed one would introduce a
pattern rather than extend one.

### 3.2 DI wiring and interfaces

`api/deps.py::get_redis_client_dependency` (`:125-131`) is the single FastAPI-injected provider, and it
returns a **new client per request** — yet four route sites **bypass** it to call
`redis_client.get_async_redis_client()` inline (`auth.py:85, 311, 563`; `client_errors.py:46`;
`upload.py:145`). A `redis_client.py` change reaches all of them; there is no single seam at which to
inject a policy object. `AuthService.__init__` additionally builds a private `self._rate_limiter`
(plan 04 Y-09) — a fifth, redundant instance whose only real consumer is the conftest patch. And
`core/permissions.py::_get_current_user_with_session` (`:291`) is a **second identity path** with its
own two revocation reads and no src-level caller.

### 3.3 Failure semantics

| Layer | On Redis failure | Where declared |
|---|---|---|
| Rate limiter (5 surfaces) | `fail_closed=config.rate_limiter_fail_closed` → **default `True`**; compose pins `RATE_LIMITER_FAIL_CLOSED: true` | `config.py:578`; `docker-compose.yml:142`; wired `auth.py:84-86, 310-312, 562-564`, `client_errors.py:45-47`, `upload.py:144-146` |
| Revocation read (2 live sites) | `except Exception` → **`401 AUTHENTICATION_FAILED` "Authentication failed"** | `deps.py:573-579` |
| Temp-password `store` | **fail open**, ERROR log, `-> None` | `temp_password_store.py:47-48` |
| Temp-password `retrieve` | **fail graceful** → `None` → `404` | `temp_password_store.py:73-75`; `admin.py:434-438` |
| Reconciler lease | **fail open** — "an unreachable Redis still boots and still repairs" | `app.py:136-156` |
| `/health` | **cannot report it** | `app.py:297-316` |
| `/health/detailed` | surfaces `lease_state: "unprotected"`, **never changes `status`** | `app.py:355-376` |

**Cost / usage accounting: there is none.** No token accounting, no LLM cost, no per-caller ledger, no
upload meter beyond the rate-limit counter. Nothing here has a cost dimension to regress; the only
"cost" claims are latency (EXT-002's ~59 s) and log volume (EXT-003's 5 MB record).

**Streaming and cancellation: none at this boundary.** The only streaming is `upload.py`'s file write;
the only cancellation is `lifespan`'s `cleanup_task.cancel()`. No `StreamingResponse`, no SSE, no
client-disconnect handling on `/data/aggregated` or `/client-errors`.

### 3.4 Shared seams and owner phase

| Seam | Symbols | Owner | Why |
|---|---|---|---|
| `redis_client.py` construction | `get_redis_client` `:11`, `get_async_redis_client` `:33` | **01** settings surface / **07** the call | `RedisSettings` is a phase-01 object; inline-vs-settings is DP-3 |
| `config.rate_limiter_fail_closed` | `config.py:578` | **01** (already `True`, already compose-pinned) | no phase-07 change needed |
| `/health` + probe contract | `app.py:297-379`, `Dockerfile:180-181`, `docker-compose.yml:157-162`, `health-api.md` | **10 co-owns; 07 owns "what the probe measures"** | Appendix F ruling stands — **but `health-api.md:196` now carries a decision 07 must read first** |
| Dev-vs-prod `command:` / healthcheck | `docker-compose.override.yml:119-121` | **02 (executed, B3/B4)** | already re-enabled; do not re-litigate |
| `--forwarded-allow-ips` + rate-limit key | `Dockerfile:183`, `override.yml:119`, `auth.py:83, 309, 566` | **04 (AB-7, AB-6)** | AUTH-001; VAL-04-001 applied |
| Revocation-read failure | `deps.py:509, 529`, `permissions.py:326, 332` | **04 (AB-5)** | AUTH-008 |
| Store contract + retrieval refusal | `temp_password_store.py`, `auth_service.py:540-605, 607-679`, `admin.py:426-439` | **04 (AB-1, AB-2)** | AUTH-002 / AUTH-006 |
| Commit-vs-durable-effect ordering | same symbols | **02 (executed, B7 / TOPO-006)**; 07 owns only the *rule* | implemented + tested |
| Orphan `temp_pwd:` keys, leftover `bidb` rows | `registration_requests`, `users` | **unowned** | no phase owns DB row hygiene — DP-5 |
| `extra="forbid"` → `422` on every write route | `models/**`, `frontend/src/**` | **07 with 16** | report: "revert is a revert of the base class" |
| `REQUIRED_MODULES` / `check_dependencies` | `main.py:10-52` | **07** (three gate-only names); **01** (TOPO-001 residue) | report declines to re-file the residue |
| OpenAPI version + tier gate | `app.py:255-263`, `config.py:449`, `pyproject.toml:7` | **07** | `config.py` is under **01/02** concurrent edit — the repo's highest-churn file |
| Rate-limit test that cannot detect the collapse | `tests/test_rate_limiting.py:154-193` | **09** | the test *name* promises per-IP separation it never exercises |
| 4 workers × ~59 s saturation | `Dockerfile:183`, `deps.py:573` | **11** | the report hands this to 11 explicitly |
| Credential material reaching a log sink | `client_errors.py:62-68` | **07** (volume) + **15** (sink) | Appendix F: split, cross-reference not merged |
| `tests/test_health.py:233` exact-dict assertion | `test_health.py:191-238` | **07** with **09** | see DP-2 |

---

## 4. In-flight and already-landed work

### 4.1 Commits intersecting this phase

| Commit | Symbol touched | Relation to `EXT-*` |
|---|---|---|
| `d008f55` | `app.py::create_app` CORS guard | anchor drift only (VAL-07-009) |
| `3848e7a` | `src/mkobi/rq_worker_wrapper.py`, `core/task_queue.py` | **EXT-009**: `rq` becomes a real import; the "four gate-only libraries" count drops to three |
| `9c49c20` | `docker-compose.override.yml` (dev healthcheck), `docker/nginx/nginx.conf`, `health-api.md` | **EXT-001**: refutes the dev-tier refinement; **adds `health-api.md:196`, a decision that contradicts EXT-001's recommendation** |
| `4a5db54` | `app.py::lifespan`, `app.py::detailed_health_check`, `core/reconciler_lease.py`, `test_health.py` | **EXT-001**: third component added; **new pinned test** at `test_health.py:191-238` |
| `b646ef1` | `app.py::lifespan` teardown | anchor drift |
| `a92b546`, `9a77625`, `3856f27` | `core/reconciler_lease.py`, `rq_worker_wrapper.py` | outside every `EXT-*` target |
| `2de4156` | `auth_service.py::approve_registration_request`, `::reset_password_admin`, `admin.py::approve_registration_request_admin_endpoint`, `docs/04-admin/admin-api.md`, `tests/test_auth_service.py` | **EXT-008 already-fixed**; **EXT-005's anchors dead**; **VAL-07-005's outcome contradicted** |
| `2174895` | `user_service.py::UserService.create_user`, `core/permissions.py`, `admin.py` docstring | outside every `EXT-*` target |

### 4.2 Dirty working tree

**`HEAD` moved from `2174895` to `cea2d06` while this context was being written**, by another agent
committing the five files that were dirty at session start. The tracked working tree is now clean of
modifications. **No `EXT-*` anchor moved:** `admin.py:315` and `:426`, `auth_service.py:590`/`:596` and
`:663`/`:669`, `app.py:258`/`:298`/`:319` all resolve at `cea2d06` exactly as recorded above.

| File | Content of the change | Relation |
|---|---|---|
| `src/mkobi/api/routes/admin.py` (7 lines) | `update_user_active_admin_endpoint` docstring: the login routes consult neither `is_active` nor the Redis marker | no `EXT-*` behaviour; makes the sentence *more* accurate. Plan 04 Y-02 flags a different stale clause in this file |
| `src/mkobi/services/user_service.py` (3 lines) | comment on `await db.rollback()`: it discards *any* uncommitted work | none |
| `tests/test_admin_user_management.py` (67 lines) | whitespace/CRLF only — `git diff` rendered empty while dirty | none; the `:619-641` pin is intact |
| `tests/test_user_service.py`, `tests/test_users_api.py` | CRLF only | none |
| untracked | `.ai/plans/01…06-*.md` (sibling plans), `.ai/plans/_code-context/`, `.ai/tasks/B1-txn-001-transaction-ownership.yaml` | this programme's, not a target |
| deleted | `.ai/builders/**`, `.ai/structure/**`, `.ai/models/**`, `.ai/templates/**`, `.ai/plans/audit-fix-plan.md`, `frontend/coverage/**` | predate the audit; not targets |

### 4.3 Sibling-plan hand-over aimed at phase 07

**No sibling plan names an `EXT-*` identifier** (0 `EXT-0` matches across all nine plan files).
Hand-over is by *subject*, and it is substantial.

| Sibling plan | Block | Subject | True in the code today? |
|---|---|---|---|
| `04-authentication` (`source_head: 2174895`) | **AB-1** | credential issuance reporting after a fail-open store — `TempPasswordStore.store`, `auth_service.py::reset_password_admin`, `::approve_registration_request`, both admin routes | **Yes, open.** Blocked on `D-04-A`; 4 options (a)–(d). **This is EXT-005's write side.** |
| `04-authentication` | **AB-2** | retrieval refusal semantics + single-use verification — `retrieve`, `admin.py::retrieve_temp_password_admin_endpoint` | **Yes.** EXT-005's read side. Blocked on `D-04-C` (verify-first gate). |
| `04-authentication` | **AB-5** | revocation-read failure direction | **Yes**, and the site list is **larger** than the report's. **This is EXT-002's second element.** |
| `04-authentication` | **AB-6 / AB-7** | rate-limit key identity / proxy trust | **Yes.** Plan 04 has already **applied** VAL-04-001 (wildcard deleted). **This is EXT-004.** |
| `04-authentication` | **AB-0** (Y-01) | independently records that AUTH-002's five `admin.py` anchors **do not exist** | **Yes — this context reproduces the same finding for EXT-005.** Two Planners, one conclusion. |
| `02-process-architecture` | **B7 / TOPO-006** | entry-layer transaction ownership for the approval path | **Landed** as `2de4156`. **This is EXT-008.** |
| `02-process-architecture` | **B3 / TOPO-008** | readiness gate — re-enables the dev healthcheck | **Landed** as `9c49c20`. Refutes EXT-001's dev refinement. |
| `02-process-architecture` | **B4 / TOPO-005** | multi-worker safety + reconciler observability | **Landed** as `4a5db54`. Adds EXT-001's third component **and** the blocking test. |
| `02-process-architecture` | **R6(c)** | *"`test_health.py` asserts membership only, never an exact key set"* | **Half-stale.** True for `/health/detailed`; **false for `/health`**, which `:233` asserts by exact dict equality. |
| `02-process-architecture` | **R7** | *"`rq` is a hard import-time contract in `main.py` … plus a `pyproject.toml` dependency"* | **True and now stronger** — `rq` is also a real runtime import. Direction B (delete RQ) was **not** taken. |
| `01-configuration-secrets` | *(executed)* | `config.py` + CORS work | Landed; `config.py` is the file EXT-010 edits. |
| `03-db-concurrency` | `B1` (landed) | `user_service.py`, `core/permissions.py` | Landed; no `EXT-*` target. |
| `05`, `06` | PB-*, FAB-* | data pipeline, file artifacts | **No `EXT-*` subject** — `/health` and `temp_password_store` appear as context only. |

**Net effect: five of the ten `EXT-*` findings (002, 004, 005, 008 and EXT-001's deployment half) are
already owned by executed or in-flight sibling plans, and one (EXT-008) is already fixed.** Phase 07's
genuinely unowned residue is narrow: **EXT-003**, **EXT-006**, **EXT-007**, **EXT-009** (three names),
**EXT-010**, and the *probe-measurement* half of **EXT-001**.

---

## 5. Discrepancies and risks

### 5.1 Stale or dead anchors the Planner must not use

| Report anchor | Reality today |
|---|---|
| `admin.py:307, 315, 320, 321, 324, 330, 339-345` (approval) | **do not exist** — bodies are `auth_service.py:607-679` |
| `admin.py:418-422` (retrieve) | `admin.py:433-438` |
| `app.py:257-276, 278-316, 300-306, 218, 220-221, 245-255` | `:297-316, 318-379, 340-346, 258, 260-261, 285-295` |
| `config.py:320` (`version`), `:461` (`rate_limiter_fail_closed`) | `:449`, `:578` |
| `deps.py:506, 526, 475, 570-576` | `:509, 529, 125-131, 573-579` |
| `security.py:502-504, 552-554` | `:503`, `:553` |
| `Dockerfile:176-177, 179` | `:180-181`, `:183` |
| `docker-compose.yml:142-147, 157-173` | `:157-162`, `:171-181` |
| `docker-compose.override.yml:104-108, 109, 111-112` | `:115-118`, `:119`; healthcheck **no longer disabled** |
| `enums.py:188, 197` | `:216`, `:225` (`exceptions.py:36, 187` are exact) |
| `security-overview.md:234` (revocation degradation) | **`:252`** |
| `health-api.md:164-169, 179-181` | `:196`, `:247-249`; **`:196` carries a new decision** |
| `pyproject.toml:4` | **`:7`** (VAL-07-010a) |

### 5.2 Refuted claims the Planner must not carry

| Claim | Verdict |
|---|---|
| EXT-001: "zero `redis` matches in `app.py`" | **refuted** — 5 matches |
| EXT-001: "dev override disables the container healthcheck" | **refuted** — re-enabled by `9c49c20` |
| EXT-001: "`tests/test_health.py:110-125` means no test blocks a `redis` component" | **refuted** — `:233` is an exact-dict assertion that blocks it |
| EXT-003: "the one shipped caller is `ErrorBoundary.tsx:40`" | **refuted** — no `client-errors` reference exists in `frontend/src/` |
| EXT-004: "the email branch is unreachable" | **refuted for `register-request`** — `auth.py:557` uses `None`, not `"unknown"` |
| EXT-007: "`filters` yields an empty set or a later error rather than a 422" | **refuted for malformed JSON** — `data.py:112-115` raises a 422-class `AppException`; only the *document shape* is unvalidated |
| EXT-009: "`rq` is never imported" | **refuted** — 39 sites, incl. `rq_worker_wrapper.py:15` |
| EXT-009: "reduce `REQUIRED_MODULES` to the twelve the application imports" | **refuted** — the correct count is 13 (14 minus `rq`) |
| EXT-010: "`app.py` passes the literal `version="1.0.0"`" | **refuted** — `app.py:258` reads `config.app.version`; the literal now lives at `config.py:449` |
| VAL-07-005: "on a publish failure compensate the committed record (mark failed, remove the account)" | **refuted in effect** — contradicted by a shipped test, a shipped docstring and a shipped doc |

### 5.3 Contested ownership

| Seam | Contested between | Ruling visible in the corpus |
|---|---|---|
| `/health` probe contract | **07** (what it measures) vs **10** (deployed composition) | report Appendix F: co-owned, not merged. **Unchanged and still correct.** |
| Revocation-read failure | **07** (EXT-002) vs **04** (AUTH-008) | plan 04 AB-5 owns the edit; 07 keeps blast radius + bound |
| Proxy trust / rate-limit key | **07** (EXT-004) vs **04** (AUTH-001) | plan 04 AB-6/AB-7 own it; wildcard already deleted |
| Store failure contract | **07** (EXT-005) vs **04** (AUTH-002/AUTH-006) | plan 04 AB-1/AB-2 own it |
| Commit-vs-effect ordering rule | **07** (EXT-008) vs **05** (DP-001) vs **02** (TOPO-006) | the *rule statement* is 07's; the *edit* landed under 02 |
| Redis timeouts on the client | **01** (`RedisSettings`) vs **07** (`redis_client.py`) | **no ruling exists in any plan** — DP-3 |
| The five leftover `bidb` rows | nobody | DP-5 |

### 5.4 Tests that will break

| Test | Line | Breaks under |
|---|---|---|
| `TestHealthWithRedisDown::test_health_still_healthy_when_redis_down` | `test_health.py:217-238` (assert at `:233`, `:237`) | **any** EXT-001 remedy that adds a Redis component or a non-200 to `/health` |
| `TestTempPasswordStore::test_store_fail_open_on_error` | `test_temp_password_store.py:164-181` | any fail-closed store contract (EXT-005, AB-1) |
| `TestTempPasswordStore::test_retrieve_fail_graceful_on_error` | `test_temp_password_store.py:184-190` | any store-fault refusal that returns 503 (AB-2) |
| `test_approve_registration_request_commit_precedes_store` | `test_auth_service.py:619-665` | any reordering back to store-before-commit |
| `test_approve_registration_request_store_failure_after_commit_keeps_user` | `test_auth_service.py:714-757` | **VAL-07-005's prescribed compensation** |
| `test_reset_user_password_admin` | `test_admin_user_management.py:619-641` | a 503 or a changed response body on the reset route |
| `test_rate_limit_reset_allow_writes` | `test_rate_limiting.py:106` (hard-codes `login:127.0.0.1`) | any `--forwarded-allow-ips` change **that alters the observed peer** — plan 04 VAL-04-002/AB-6 |
| every write-route test | all | `extra="forbid"` on the request bodies (EXT-007) — "will look like a regression if it lands alone" |

### 5.5 Security and cost regression risk

| Risk | Source | Note |
|---|---|---|
| **Wildcard `--forwarded-allow-ips` = brute-force bypass** | EXT-004, VAL-07-002 | **Already ruled out** by plan 04 (VAL-04-001 applied). Any phase-07 plan text repeating `"*"` re-opens a closed decision. |
| **401→503 on every authenticated request during an outage** | EXT-002, AB-5 | The SPA interceptor treats 401 as "refresh the token", and refresh needs the same Redis — so today's user-visible state is a silent sign-out loop. A 503 stops that. Visible contract change; belongs in a release note. |
| **`/health` → non-200 during a Redis blip makes nginx refuse to start** | EXT-001, `health-api.md:196` | The documented reason the probe is DB-only. `nginx.conf` gates on `app: service_healthy`; `docker-compose.yml:157-162` sets `start_period: 40s`; under `--workers 4` three of four workers would report unhealthy. **A naive EXT-001 remedy converts a degraded sweep into an API outage** — the exact inversion `:196` warns about. |
| **Unbounded log volume + unmasked credential material** | EXT-003 | ~100 MB per request (`nginx.conf:18`), ×100/hour on a **shared** counter. There is no cost/usage accounting anywhere, so nothing would surface this as spend. |
| **`extra="forbid"` → 422 on every write route** | EXT-007 | Revert is a base-class revert. Schedule with the frontend owner. |
| **Wildcard in the *production* tier** | EXT-010 | `nginx` is production-only; `/openapi.json` reaching the SPA is protection by topology, not code. |

---

## 6. Decision points for the Planner

Each is genuine uncertainty. **I pick none.**

| ID | Question | Alternatives | Chooser | Blocks |
|---|---|---|---|---|
| **DP-1** | Does EXT-001's "add Redis to `/health`, 503 on failure" survive contact with `health-api.md:196` and `test_health.py:233`? | (a) drop the `/health` half, extend `/health/detailed` only; (b) add Redis to `/health` and accept that nginx's `service_healthy` gate turns a Redis blip into an API outage; (c) split the endpoints (a new `/health/ready`); (d) leave `/health` DB-only and change the documented consumer contract at `health-api.md:247-249` | **Tech Lead**, with phase 10 as co-signer of the probe contract | all EXT-001 work |
| **DP-2** | If DP-1 lands, what happens to `test_health.py:233`'s exact-dict assertion? | (a) update the test with the code and rewrite its class docstring (which states the opposite intent); (b) relax to key-subset membership, matching `/health/detailed`; (c) add a second test pinning the new intent | **09** owns the test-quality ruling; **07** owns the production change | EXT-001's definition of done |
| **DP-3** | Where do the Redis transport bounds belong — `redis_client.py` literals or `config.py::RedisSettings`? | (a) inline (smallest diff, not operator-tunable); (b) new `RedisSettings` fields with env aliases, per the project's settings discipline; (c) both | **01** owns `config.py`, **07** the call. **Unruled in every existing plan.** | EXT-002's residue |
| **DP-4** | Is retry policy a config value or a code invariant? `Retry(retries=10)` is a library default nobody pinned. | (a) pin `Retry(NoBackoff(), 0)` as the report's step 4 proposes; (b) a small bounded retry to survive one packet loss; (c) timeouts only | **Tech Lead** — a reliability-vs-latency call over 53 operations | EXT-002; phase 11's projection |
| **DP-5** | The five `bidb` rows VAL-07-011 names (`03c82044-…` / `wo.probe.1395195825@example.com`, `bce038fd-…`, three pending requests) | (a) delete; (b) record as knowingly retained; (c) leave | **Coordinator**, not the Planner. Row deletion is outside every phase's scope; no block may do it silently. | nothing — but it must be stated, not dropped |
| **DP-6** | Is the strict base for EXT-007 applied to all request bodies or only the write bodies? | (a) all (report's scope); (b) writes only, leaving reads permissive; (c) all, with a per-model opt-out for fields the frontend demonstrably over-sends | **07** with the **16** owner; needs a frontend field census first | EXT-007 |
| **DP-7** | For EXT-006 — register the route so the declared shape is matched, or emit a path-relative `Location` after the credential dependency? | (a) route registration on the four collection paths (changes the declared shape, breaks any non-redirect-following client); (b) path-relative `Location` (no contract change, oracle remains); (c) both | **Tech Lead**; (a) is wire-visible on four declared paths | EXT-006 |
| **DP-8** | Should `check_dependencies()` keep gating modules the API app never imports, now that `rq` is a *worker* contract sharing the gate? | (a) split into app-required and worker-required sets; (b) drop the three gate-only names, keep `rq`; (c) establish intent first for `httpx`/`tenacity`/`plotly` (the report's own instruction) and defer | **01** (TOPO-001 owns the residue) with **07**; the report declines to guess intent | EXT-009 |
| **DP-9** | For EXT-010 — what is the single source of truth for the version? | (a) `importlib.metadata.version`; (b) a new env-overridable `config.app.version` defaulting to the distribution version; (c) leave the literal, fix the docs | **01** owns the settings surface; `config.py` is the repo's highest-churn file | EXT-010 |
| **DP-10** | Does phase 07 re-file what the sibling plans own, or record hand-overs only? | (a) hand-overs only (this context's evidence supports it: 5 of 10 findings are owned elsewhere); (b) re-file the `rq-worker` row despite EXT-009 declining it; (c) re-open the wildcard to re-confirm it | **Coordinator** — a recommendation-grade question, not a technical one | the whole block map |

---

## 7. Coverage ledger

| Finding | Verdict | Evidence anchor(s) resolved at `2174895` | How verified |
|---|---|---|---|
| **EXT-001** | **drifted** | `app.py::health_check` `:297-316`; `::detailed_health_check` `:318-379`; `Dockerfile:180-181`; `docker-compose.yml:157-162`; `override.yml:120-121`; `health-api.md:196, 247-249`; `test_health.py:233` | read + **live GET** `/health`, `/health/detailed` |
| **EXT-002** | **substantiated** (residue); refusal class → 04 | `redis_client.py:46-52`; `deps.py:125-131, 509, 529, 573-579`; `security.py:503, 553`; `permissions.py:326, 332`; `enums.py:216, 225`; `exceptions.py:36, 187` | read + **`docker exec` (redis-py defaults)** |
| **EXT-003** | **substantiated, strengthened** | `client_errors.py:21, 42, 45-50, 62-68`; `models/data.py:504-528`; `nginx.conf:18`; `frontend/src/` — **0 `client-errors` refs** | read (all anchors exact) |
| **EXT-004** | **substantiated**; merged → 04 (AB-6/AB-7) | `auth.py:83-89, 309-315, 557-559, 566-568`; `client_errors.py:49-50`; `upload.py:144-152`; `Dockerfile:183`; `override.yml:118-119`; `nginx.conf:38` | read + **`docker exec` (`forwarded_allow_ips='127.0.0.1'`)** |
| **EXT-005** | **substantiated** (write side); anchors dead; → 04 (AB-1) | `auth_service.py:607-679` (`:663` commit, `:669` store, `:678` token); `admin.py:315-361, 426-439`; `temp_password_store.py:30-48, 50-75, 20`; `test_temp_password_store.py:164-190`; `test_admin_user_management.py:619-641` | read |
| **EXT-006** | **substantiated** at 4 paths | 12 × `redirect_slashes=False` (all exact); `/openapi.json` | read + **live enumeration** |
| **EXT-007** | **substantiated** | `transformation_configs.py:133`; `types.py:47, 247, 260, 279, 292, 305, 138`; `graph.py:15, 45`; `data.py:54, 106-115` | read (all exact) |
| **EXT-008** | **already-fixed** | `auth_service.py:647-669`; `test_auth_service.py:619-757`; `temp_password_store.py:63-66`; `auth_service.py:585-596` | read |
| **EXT-009** | **drifted** | `main.py:10-25, 28-47, 50, 52` (exact); `rq_worker_wrapper.py:15, 220-221` | read |
| **EXT-010** | **drifted** (half already-fixed) | `app.py:255-263` (`:258`, `:260-261`); `config.py:449`; `pyproject.toml:7`; `nginx.conf:34, 43, 49` | read + **live `/openapi.json`** |
| **VAL-07-001** | substantiated, escalated | `admin.py:315-361`; `auth_service.py:607-679` | read |
| **VAL-07-002** | substantiated; **already ruled** | plan 04 `VAL-04-001` "applied"; `nginx.conf:38`; `override.yml:118` | read + exec |
| **VAL-07-003** | substantiated | `enums.py:216, 225`; `exceptions.py:36, 187` | read |
| **VAL-07-004** | substantiated; **6 sites** | `deps.py:509, 529`; `permissions.py:326, 332` | read |
| **VAL-07-005** | **refuted in outcome** | `test_auth_service.py:714-757`; `auth_service.py:617-624`; `docs/04-admin/admin-api.md` | read |
| **VAL-07-006** | substantiated, runtime-confirmed | `redis 8.0.0`, `retries=10`, `ExponentialWithJitterBackoff(cap=1, base=0.01)`, `socket_timeout=5` | **`docker exec`** |
| **VAL-07-007** | substantiated, runtime-confirmed | 4 trailing-slash paths from live `/openapi.json` | **live** |
| **VAL-07-008** | substantiated verbatim (+1 extra) | `test_temp_password_store.py:164-181, 184-190`; `test_admin_user_management.py:619-641` | read |
| **VAL-07-009** | substantiated, superseded | `app.py:297-379`; `config.py:449, 578` | read |
| **VAL-07-010** | substantiated (a)–(c) | `pyproject.toml:7`; 12 router lines; 43 `docs/*.md` | read |
| **VAL-07-011** | not actionable for the Planner | `bidb` rows (no code anchor) | n/a — requires a DB write this role may not perform |

**Tally.** 10 audited findings: **3 substantiated** (003, 004, 006) · **3 substantiated-but-drifted**
(001, 002, 007) · **1 substantiated + strengthened** (005) · **1 drifted** (009, 010 → see table) ·
**1 already-fixed** (008). Nothing is fully refuted; one claim (`VAL-07-005`'s prescribed outcome) is
refuted **in effect**. 11 validation-level defects: 8 substantiated (1 and 4 escalated), 1 superseded,
1 not actionable, 1 refuted-in-effect.
