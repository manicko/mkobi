---
phase: 15-security-baseline
role: phase-1-code-context-auditor
executed: 2026-10-01
head: 863b81bb7a0296dc3ddd422388db693f742aef94
finding_prefix: SEC-
report_findings: 9 (SEC-001 … SEC-009)
report_defects: 4 (VAL-15-001 … VAL-15-004)
status: complete
---

# Phase 15 — Security Baseline — Code Context

## 1. Scope and method

### 1.1 What was read

| Input | Use |
|---|---|
| `.ai/audit/99-validation/15-security-baseline-validated-findings.md` (1060 lines) | primary; finding IDs, anchors, verdicts, `VAL-15-*` |
| `.ai/audit/15-security-baseline/findings.md` | provenance only (upstream raw report) |
| `.ai/plans/01,04,07,10,11,12,13-*-execution.md` | frontmatter, block tables, `C0x-*` seam registers, "Out of scope" tables |
| `docs/08-security/error-format.md`, `security-overview.md`, `docs/90-adr/adr-004-cookie-refresh-tokens.md`, `docker/init-scripts/01-create-app-role.sh` | normative baselines |
| `src/mkobi/**`, `tests/**`, `docker/**`, `frontend/src/**` | anchor re-derivation |

> **Mid-run correction.** At the start of this run `14-schema-migrations-remediation-execution.md` did **not** exist; by
> the end it had landed (untracked), alongside new dirty files `tests/test_data_worker.py` and
> `tests/test_file_cleanup.py`. Plan 14 is therefore now a **live counterparty** for the two schema-adjacent seams
> (`processing_logs.message`, any new `ErrorCode` member). See §4 and R6 — re-check plan 14's block table before
> decomposing; it may now own part of SEC-008's column fix.

### 1.2 HEAD vs working tree

| Item | Value |
|---|---|
| `git rev-parse HEAD` | `863b81bb7a0296dc3ddd422388db693f742aef94` — **matches the stated baseline `863b81b`** |
| Validation report's own baseline | `4a5db54` — **the tree moved since the report was written**; every anchor re-resolved |
| Modified, tracked | `src/mkobi/workers/data_worker.py`, `tests/test_processing_logs.py` — **and, by the end of this run, `tests/test_data_worker.py`, `tests/test_file_cleanup.py`** (a concurrent agent landed work mid-run) |
| Deleted, tracked | 28 `.ai/**` scaffolding files + 15 `frontend/coverage/**` (pre-existing, out of scope) |
| Untracked | plans `01`–`13`, `.ai/plans/_code-context/`, `.ai/tasks/B{1,2,3}-*.yaml` |

**The one dirty production file is `workers/data_worker.py`, and it is the file SEC-008's Path B fix must touch.** The
dirty diff is the durable-processing-transition work (`ab76989` / task `B3-txn-003`), still in flight. This is the single
most important ordering fact in this document.

### 1.3 Verified at runtime vs by reading only

| Method | Used for |
|---|---|
| `docker compose … ps` (read-only) | dev stack live: `app`, `db`, `frontend`, `redis`, `rq-worker` running |
| `docker inspect` (read-only) | `ReadonlyRootfs` / `CapDrop` / `SecurityOpt` / `User` / `Cmd` / network IPs per container |
| `HTTP GET localhost:8010/health/detailed` (read-only) | unauthenticated 200 + body shape |
| `git log` / `git status` / `git diff` | HEAD split, in-flight work |
| **Reading only** | every Python, compose, Dockerfile, test and frontend claim. **No service was started, stopped or reconfigured; no container was mutated; no secret value was read or printed.** |

Runtime facts that matter: `redis:7.4-alpine` runs with `Cmd: ["redis-server"]` (image default, **no override**),
`Entrypoint: docker-entrypoint.sh`, on `mkobi_default` at **`172.21.0.2`**; `app` is at **`172.21.0.3`**. `app` carries
`CapDrop=[ALL]`, `SecurityOpt=[no-new-privileges:true]`, `User=app`, `ReadonlyRootfs=False` (dev override relaxes it).
`rq-worker`, `redis` and `db` carry **no** `CapDrop`, **no** `SecurityOpt`, and `redis`/`db` run as the image default user.

### 1.4 Ownership position — what phase 15 is left with

Verified against the sibling plans' own scope tables. **No sibling plan cites a `SEC-` identifier** (zero hits across
`.ai/plans/**`), so nothing is pre-claimed by ID — but seven seams are pre-claimed by mechanism.

| Finding | Already owned | Phase-15 residue |
|---|---|---|
| SEC-001 | **phase 04** explicitly hands *"Password hashing cost, at-rest policy, credential rotation periods"* to **phase 15** (`04-…md:599`) | **phase 15 owns it** |
| SEC-002 | nothing by ID; phase 04 owns store *failure* semantics (AUTH-002/006) | **phase 15 owns the encoding** |
| SEC-003 | **key derivation → phase 04** (AUTH-001, `D-04-E`); ingress budget → phase 07 (EXT-004) | defaults disagreement + dead instance + dev-overlay gap |
| SEC-004 | `frontend/src/**` → phase 13/16 per `04-…md:589` | **phase 15 owns the backend boundary**; the frontend half is a hand-over |
| SEC-005 | nothing; EXT-003 sink half is explicitly **not** phase 15's (`07-…md:642`) | **phase 15 owns it** |
| SEC-006 | health *contract* → phase 10 | **phase 15 owns the disclosure** |
| SEC-007 | `X-Frame-Options`/CSP in dev = deployment decision → phase 10 | **phase 15 owns the 500-path header gap** |
| SEC-008 | `processing_logs` schema → **phase 06** (ART-002, C06-3) / phase 14 (migration); error vocabulary register → phase 09 | **phase 15 owns the disclosure content at the 23 sites** |
| SEC-009 | `frontend/src/**` → phase 13 (C13-*), phase 16 | **phase 15 owns the invariant; the code is phase 13's** |

**Count: 0 of 9 fully owned elsewhere; 5 of 9 partially owned (SEC-003, SEC-004, SEC-006, SEC-007, SEC-008, SEC-009 → 6);
1 explicitly handed to phase 15 by phase 04 (SEC-001).** Phase 15 keeps a real, non-trivial residue.

---

## 2. Per-finding context

### SEC-001 — >72-byte passwords silently aliased to their first 72 bytes

**Verdict: `substantiated`** — every anchor resolves exactly; one consequence text is stale.

| Anchor in report | Resolves at `863b81b` | Note |
|---|---|---|
| `security.py:37-38` `SALT_ROUNDS=12`, `MAX_PASSWORD_LENGTH=72` | `core/security.py:37-38` | exact |
| `security.py:154-187` `_truncate_password` | `:154-187` | exact; `logger.warning` at `:182-186` |
| `security.py:208` / `:236` truncation call sites | `:208`, `:236` | exact — the symmetric proof |
| `models/auth.py:181-183` three bare `str` | `:181-183` | exact |
| `auth_service.py:498-505` | `:498` verify, `:505` `current_password == new_password` | exact |

**Consequence text that is now wrong:** SEC-009's "short-lived (30 minutes)". `config.py:298` is
`access_token_expire_minutes: int = 15`. `create_access_token`'s docstring (`core/security.py:257-258`) still says
"default 30 minutes" — **a docstring/code mismatch that ADR-004 correctly records as 15** (`adr-004…md:42,65`).

**Remediation blockers (confirmed present):**
- `tests/test_security.py::TestTruncatePassword::test_long_password_truncated` (`:22-27`) and
  `test_unicode_password_truncated` (`:29-33`) assert truncation — they encode the defect.
- No `max_length` anywhere in `src/mkobi/models/` — confirmed; `max_length=72` on a `str` is a *character* count, so a
  byte validator is required, as filed.

**Seams an implementor would touch:** `core/security.py::{_truncate_password, hash_password, verify_password}`;
`models/auth.py::{RegisterRequest.password, ChangePasswordRequest.new_password}`; `utils/validators.py::validate_password_or_raise`;
tests `tests/test_security.py`; docs `docs/08-security/security-overview.md`. **Owner: phase 15.**

### SEC-002 — delegated credential stored in Redis as the credential itself

**Verdict: `substantiated`** — re-typed claim survives; two anchors have drifted.

| Anchor | Resolves at `863b81b` | Note |
|---|---|---|
| `temp_password_store.py:39-41` `set(key, password, ex=ttl)` | `:39` key, `:41` `set` — **exact** | the plaintext is the argument |
| `retrieve` `:50-75`, pipeline `:63-66` | exact | single-read `GET+DELETE` in one transaction |
| `config.py:581` `temp_password_ttl_seconds` default 86400 | **`config.py:587`** (drift +6) | `validate_temp_password_ttl` floor at `:589` |
| `docker-compose.yml:172-188` redis, no auth | **`:171-188`** (comment at 171) | exact claim; `healthcheck` `redis-cli ping` at `:177-181` |
| `admin.py:320-321` approval mints through the same path | **STALE** — moved to `services/auth_service.py::approve_registration_request` `:667-669` | landed `2174895`/`2de4156` |
| `auth_service.py:577-583` reset path | **`auth_service.py:594-596`** | same commit |

Runtime confirmation: the redis container's `Cmd` is the image default `["redis-server"]` — no `command:` override, no
`requirepass`, no `REDISCLI_AUTH`, no ACL, no TLS. Named volume `mkobi_redis_data:/data` ⇒ plaintext is also at rest in
the RDB past the 24 h TTL. The same instance holds `token_blacklist:*`, `refresh_token_blacklist:*` and the reconciler lease.

**Un-named seam found here (adjacent, not filed):** `core/temp_password_store.py:44, 69, 71` log `token[:8]`; and
`auth_service.py:599` logs `retrieval_token[:8]` at INFO, `admin.py:432` likewise. The retrieval handle's first 8 chars
reach the rotated log file. With `docker/nginx/nginx.conf:10` using the **default combined** `access_log`, the *full*
request line — `GET /api/v1/admin/temp-passwords/<token>` — is also written to nginx's log. **Owner of log redaction:
phase 04 (`D-04-K` / `C04-5`), not phase 15.**

**Seams:** `core/temp_password_store.py::{store, retrieve}`; `services/auth_service.py::{reset_password_admin:594,
approve_registration_request:667}`; `config.py:587`; `docker/docker-compose.yml:171-188` (redis `command:` +
healthcheck must change in the same commit); tests `tests/` for the store contract. **Owner: phase 15.**

### SEC-003 — rate limiter: two defaults disagree; key claim refuted

**Verdict: `substantiated` on substance (defaults, dead instance, dev-overlay gap); the key-derivation clause is
`refuted`.**

| Clause | Anchor | Resolves at `863b81b` | Verdict |
|---|---|---|---|
| 1 · two defaults | `config.py:578` fail-closed | **`config.py:584`** (`# --- Rate Limiter ---` at 583) | substantiated |
| 1 · two defaults | `security.py:107` fail-open | `core/security.py:107` exact | substantiated |
| 1 · Redis-error path | `security.py:137-151` | exact; `:139-145` reject, `:146-151` admit | substantiated |
| 2 · five sites | `auth.py:84-86`, `310-312`, `562-564`; `client_errors.py:45-47`; `upload.py:144-146` | all exact; keys at `:89`, `:314`, `:566`, `:49`, `:149` | substantiated |
| 2 · dead instance | `auth_service.py:66-68` | `:66-69`; grep for `_rate_limiter` in that file returns **exactly one hit — the construction** | substantiated |
| 3 · env reach | `.env.production:49`; `compose.yml:142`, `:236`; **absent from `override.yml`** | all exact; override grep = **0 hits** | substantiated |
| 4 · the key | `FORWARDED_ALLOW_IPS` nowhere | **repo-wide grep: 0 hits in `docker/`, `src/`, `docs/`.** Only `.ai/**` prose and `docs/STRUCT.md:17368` (a vendored-file listing) | **refuted** |

**Runtime corroboration of the refutation (new, and decisive):** the app's peers are container bridge addresses —
`app` at `172.21.0.3`, `redis` at `172.21.0.2`, network `mkobi_default`. uvicorn's `forwarded_allow_ips` default is
`127.0.0.1`, so the trust gate never opens and `request.client.host` is the **proxy's** address for every request. The
collapse is today's state. `VAL-15-001` is upheld; `AUTH-001` / `EXT-004` already own the fix.

**Additional finding the report did not name:** `auth.py:566` falls back to
`f"register-request:{request_data.email}"` when `client_ip` is falsy — a **caller-supplied** key component, and the
only site whose key can be chosen by the caller even with the gate closed.

**Blast radius of the dev-overlay gap:** `override.yml` app service (`:60-123`) and rq-worker (`:127-177`) carry no
`RATE_LIMITER_FAIL_CLOSED`; production `compose.yml:142` / `:236` do. `tests/test_config.py` pins compose text
(plan 10 `B8` cites `TestRqWorkerComposeWiring`).

**Remediation blocker confirmed:** `tests/test_rate_limiting.py:124` hardcodes `rate_limit_key = "login:127.0.0.1"`,
popped at `:138-139`. **Owner: phase 15 for the defaults/dead-instance/overlay items; phase 04 (`D-04-E`,
`D-04-D`) for the key; phase 07 for the ingress budget.**

### SEC-004 — `GraphConfigDict` is a `total=False` TypedDict used as a field type

**Verdict: `substantiated`; consequence widened by VAL-15-004, which is upheld.**

| Anchor | Resolves at `863b81b` |
|---|---|
| `types.py:138-152` `GraphConfigDict`, 11 keys | `models/types.py:138-152` — exact |
| `graph.py:15`, `:45` | `models/graph.py:15` (`GraphBase`), `:45` (`GraphUpdate`) — exact |
| `GraphCreate.model_config` has no `extra` policy | inherits `ConfigDict(from_attributes=True)` at `graph.py:19-31` |
| `api.types.ts:209-215` | **`frontend/src/shared/types/api.types.ts:203`, `config?` block `:208-215`** (`metrics?:212`, `orientation?:213`, `barmode?:214`) |
| `ChartRenderer.tsx:18,37,105-106,149` | **exact** — `:18` `orientation`, `:37` applied, `:105-106` `layout.showlegend`, `:149` `barmode` |

`metrics`, `orientation`, `barmode`, `plot_type`, `stacked`, `showlegend` are all absent from `GraphConfigDict`; the
**shipped client reads three of them back on every render** and silently falls back to defaults. `ChartRenderer.tsx:17`
also reads `config.metrics`, absent from the declared set. VAL-15-004 is upheld: the defect is live today, not latent,
and `extra="forbid"` at the model level would **not** catch it (nested `TypedDict`).

**Seams:** `models/types.py:138`; `models/graph.py::{GraphBase.config, GraphUpdate.config}`; `api/routes/graphs.py`,
`api/routes/dashboards_graphs.py`; **frontend `api.types.ts:203-215` + `ChartRenderer.tsx:15-18,105-106,149` →
phase 13/16 hand-over** (`04-…md:589`). **Owner: phase 15 backend / phase 13 frontend.**

### SEC-005 — rejected password change writes plaintext to log **and** response body

**Verdict: `substantiated` — the most consequential claim in the set; reproduced by the validator and re-derived here.**

| Anchor | Resolves at `863b81b` | Note |
|---|---|---|
| `exceptions.py:263-297` handler | exact; `logger.error("RequestValidationError raised: %s", exc.errors())` at **`:272-275`** | logs the whole `input` dict |
| `:285-290` `clean_err = dict(err)` | **`:287`** — shallow copy, no key removed | **exact** |
| `:291-296` return | `:291-297` | `errors` array returned verbatim |
| `models/auth.py:178-208` | exact; `model_validator(mode="after")` `:196-201`, `field_validator` `:203-208` | all three `input` shapes apply |
| `logging_config.py:114-122` rotating file | exact — `RotatingFileHandler`, `maxBytes` 10 MB, `backupCount` 5 | |
| `compose.yml:129`, `:224` `LOGGING__LOG_FILE` | exact (`app`, `rq-worker`) | |
| `global_exception_handler` returns no internals | `:330-345` — `detail="Internal server error"`, no `exc_info` | upheld negative |

**Spec authority (the load-bearing citation):** `docs/08-security/error-format.md:91-94` documents `errors[]` entries as
`{ "loc", "msg", "type" }` — **`input` is nowhere in the documented shape**, and `:42` defines `errors` as
"Field-level validation errors". Removing `input` is a **conformance fix**, not a contract break. VAL-15-002 upheld.

**Frontend corroboration:** `frontend/src/shared/api/errorHandler.ts:128-137` `extractFieldErrors` reads only
`err.loc` / `err.msg`; `:52` and `:68` still ship the whole array as `details: { validation_errors: validationErrors }`,
so `input` continues past the response body. `ValidationFieldError.input?: string` is declared `string` while the
backend sends a **dict** for a whole-body failure — already inaccurate.

**Test:** `tests/test_auth_api.py:556-560` matches on `msg` (`"do not match" in errors_str.lower()`) → **passes
unchanged**. No shipped test asserts the current `input` shape. **No regression guard exists for either property.**

**Seams:** `utils/exceptions.py::{request_validation_exception_handler:263-297, global_exception_handler:330-345}`;
`models/auth.py::{LoginRequest:14, RegisterRequest:100, ChangePasswordRequest:181-183}`; `frontend/.../api.types.ts`
(`input?: string`); tests `tests/test_auth_api.py`, new guard test. **Owner: phase 15.**

### SEC-006 — `/health/detailed` returns the DB driver's exception text unauthenticated

**Verdict: `substantiated`; anchors have drifted +~20 lines.**

| Anchor | Resolves at `863b81b` |
|---|---|
| route | **`app.py:318-319`** (`@application.get("/health/detailed")` at 318, `def detailed_health_check` at 319); report said `:298`/`:299` |
| `"error": str(e)` | **`app.py:341-346`** (`logger.error` at `:341`, `"error": str(e)` at **`:345`**) inside a **200**; report said `:320-326` |
| `"path": "frontend/dist"` | **`:350-353`** |
| reconciler counters | **`:355-364+`** (`sweep_count`, `unprotected_ticks`, `last_success_at`, `lease_state`) |
| `/health` returns no `str(e)` | `:297-316` — `"database": "disconnected"` constant; upheld |
| role name corroboration | `docker/init-scripts/01-create-app-role.sh:24` creates exactly one role |

**Runtime observation (new):** `GET http://localhost:8010/health/detailed` with no credentials returned **200** and
`{"status":"healthy","components":{...,"static_files":{"status":"unavailable","path":"frontend/dist"},
"stale_processing_reconciler":{"status":"ok","lease_state":"holder","last_success_at":"…","sweep_count":1,
"unprotected_ticks":0}}}`. The `str(e)` arm did not fire (DB healthy), but the **path disclosure and the
lease-holding-replica disclosure are live and unauthenticated today**.

**Note on the gate:** `nginx.conf:43-46` explicitly routes `/health(/detailed)?` with the comment
"no auth required". `require_admin_role` exists but is not applied. **Owner: phase 15** (disclosure); phase 10 owns the
health *contract*; the nginx location is phase 10/12 territory.

### SEC-007 — a 500 from the project's own handler carries none of the three security headers

**Verdict: `substantiated`.**

| Anchor | Resolves at `863b81b` |
|---|---|
| `SecurityHeadersMiddleware.dispatch` | **`app.py:67-87`** — exact; `:78-80` the three unconditional headers, `:83-85` HSTS + CSP under `ENV=production` |
| `add_middleware` positions | **`:267` CORS, `:276` GZip, `:282` SecurityHeaders** (report said `:248,257,263` — drift +19) |
| `global_exception_handler` | `utils/exceptions.py:330-345` — exact |
| nginx `always` headers | `nginx.conf:20-23` (incl. `X-Frame-Options SAMEORIGIN` at **`:21`**) and `:30` CSP |
| dev stack has no nginx | confirmed — `nginx` is `profiles: [production]`; running services are `app`, `db`, `frontend`, `redis`, `rq-worker` |
| app sets `X-Frame-Options` nowhere | confirmed by reading `app.py:67-87` in full |

Mechanism is Starlette's: `ServerErrorMiddleware` is outermost, `SecurityHeadersMiddleware` is added last and therefore
sits **inside** it, so a `500` produced by the `Exception` handler bypasses the header middleware. **HELD.** The
`X-Frame-Options` gap in dev is a **deployment decision, not a code defect** — the middleware docstring (`app.py:56-57`)
is accurate. **Owner: phase 15 for the 500-path stamp; phase 10 for the dev-tier header decision.**

### SEC-008 — `detail=str(e)` on ~25 sites; worker persists a path and a Redis endpoint

**Verdict: `substantiated` on substance; count re-typed exactly as VAL-15-003 ruled. Two anchors drifted; the third is dirty.**

Re-run of the inventory at `863b81b`: **25 occurrences of the token `detail=str(`** —

| Class | Count | Anchors |
|---|---|---|
| Route modules | **23 across 11 files** | `admin.py:91,127,266` · `auth.py:239,510,599` · `dashboards_access.py:114` · `dashboards_crud.py:151,389` · `dashboards_graphs.py:104` · `data.py:203,209` · `graphs.py:131,378` · `layouts.py:108,348` · `processing_configs.py:192,265` · `upload.py:242` · `users.py:81,258,312,366` |
| Dependency (not a route) | 1 | **`api/deps.py:570`** (report: `:567`, drift +3) |
| Non-member | 1 | **`utils/exceptions.py:321`** — `detail=str(exc.detail) if exc.detail else get_error_title(code)`, a *developer-supplied* detail |

VAL-15-003's "23 sites across 11 route modules, plus one dependency site and one non-member" is **exact**.
`admin.py:266` binds to `exc`, not `e` (drift from `:230` — the same finding as the report's precision note, now +36).
`auth.py:510` is `change_password`'s own `except ValueError` — **the same route as SEC-005**.

**The two live leaks, re-anchored:**

| Leak | Report | Resolves at `863b81b` |
|---|---|---|
| Path A · Redis endpoint → response | `task_queue.py:72-77`, `:76` | **`core/task_queue.py:74-79`**, `detail=f"Failed to enqueue processing job: {e}"` at **`:78`**, `from e` already present |
| Path B · path → durable column | `data_worker.py:571-594`, `:606-631` | test arm **`:606-609` (`str(e)` at 607, `logger.exception` at 609) and `:626`**; production arm **`:671-674` and `:695`** |
| Read-back | `data_service.py:335-341` | **`:337`** `filename=log.message or "unknown"`, **`:341`** `message=log.message` |

`logger.exception` already exists at `:609` / `:674`, so the report's "keep the full text in `logger.exception`" is
already satisfied. `ProcessingLog` has no name/path column (phase 06's `C06-3` owns adding `artifact_filename`).
Neither leak is unauthenticated: upload requires editor+, `/upload/status/{task_id}` requires a session + ownership.
**The corrected blast radius (authenticated editor learns the container upload dir and the internal Redis endpoint) holds.**

**`workers/data_worker.py` is DIRTY** — the in-flight durable-transition work edits the same function. See §5.

**Seams:** 23 route modules; `core/task_queue.py:78`; `workers/data_worker.py:{626,695}`; `services/data_service.py:{337,341}`;
`utils/exceptions.py::get_error_title`. **Owner: phase 15 (content) / phase 06 + 14 (`processing_logs` schema, `C06-3`).**

### SEC-009 — access token in `sessionStorage` in every non-production build

**Verdict: `substantiated`; the "30 minutes" figure is stale; the test-path citation is imprecise but the file exists.**

| Anchor | Resolves at `863b81b` |
|---|---|
| `authToken.ts:74` `USE_MEMORY_STORAGE = import.meta.env.PROD` | **exact** |
| `sessionStorage` at `:89,124,139,148` | **exact**; also `:105`/`:112` register a cross-tab `storage` listener in dev |
| invariant comment `:64` | exact; **enforced by nothing** — no assertion, no lint rule, no test |
| `security.py:416-441` HttpOnly refresh cookie | exact — `set_secure_cookie`, `httponly=COOKIE_HTTPONLY`, `samesite=COOKIE_SAMESITE` (`"strict"`), `secure=config.app.cookie_secure` |
| `override.yml:37-57` Vite dev server | confirmed (running `frontend` container) |
| `authToken.test.ts:11-16` | file is at **`frontend/src/features/auth/model/__tests__/authToken.test.ts`** (report omitted the `__tests__` segment); `:11-12` comment, `:15-21` `sessionStorage.clear()` in `beforeEach`/`afterEach` |

**The validator's correction is upheld and is stronger than filed:** the *entire* 165-line test file runs on the DEV
branch (`setToken`/`getToken` round-trip at `:23-38` asserts through `sessionStorage`). So the dev-mode assertion is
**not** a defect-encoding test to invert — the file would need its storage fixture re-plumbed, and what is actually
missing is a test asserting the **production** build takes the memory path.

**Tier context:** `override.yml:76` sets `APP__COOKIE_SECURE: "false"` — the refresh cookie's `Secure` flag is off in
dev, matching ADR-004's "HTTPS-only" claim in the production tier only.
**Owner: phase 15 owns the invariant statement; `frontend/src/**` is phase 13's (`C13-*`) / phase 16's.**

---

## 3. Cross-cutting architecture and constraints

Every row names the owner phase for the seam.

| Seam | Current mechanism at `863b81b` | Owner |
|---|---|---|
| Secret resolution | `config.py::SecretsFileSource.__call__` `:145-210`; `*_FILE` → base env name `:174`; allow-list `_secret_field_env_names` `:166`; non-secret `*_FILE` warned **by name, never by value** `:180-184`; names-nothing case silent at debug `:190-193`; source tuple `:735-741` (env first) | **phase 01** (`B4`, CFG-008/009) |
| Placeholder origin guard | `config.py` rejects the shipped placeholder under `ENV=production`; `app.py:250-253` refuses to boot without `cors_origins`; `compose.yml:138`, `:222` default to `["http://localhost:5173"]`; `override.yml:94` defaults to `["http://localhost:3000"]` (**tiers differ**) | **phase 01** (CFG-006/007, `B2`/`B5`) |
| CORS | `app.py:267-273` — `allow_credentials=True`, explicit origins, `allow_methods` GET/POST/PUT/DELETE/PATCH, `allow_headers` Authorization/Content-Type/Accept. No wildcard shipped | **phase 01** |
| Trusted-host policy | **Absent.** No `TrustedHostMiddleware`, no `allowed_hosts` setting, no `ProxyHeadersMiddleware` install. Documented in §5 as a gap, not filed | **phase 15 / 04** |
| Cookie flags | `core/security.py:43-45` `COOKIE_HTTPONLY=True`, `COOKIE_SAMESITE="strict"`, `COOKIE_NAME="mkobi_refresh_token"`; `set_secure_cookie` `:416-441`; `delete_secure_cookie` `:444-460`. `secure` is `config.app.cookie_secure` (`config.py:458`), forced `false` in dev (`override.yml:76`) | **phase 04** (`AB-8`, `D-04-J`) |
| Refresh-cookie decision record | `docs/90-adr/adr-004-cookie-refresh-tokens.md` — Status **Accepted**, 2026-05-23; HttpOnly/Secure/SameSite=Strict, Max-Age 604800, access token 30→**15** min, silent refresh, logout endpoint. **Phase 04's `C04-7` reserves amendment to the Coordinator** | **phase 04 / Coordinator** |
| JWT lifetime | `config.py:298` `access_token_expire_minutes=15`; `:299` `refresh_token_expire_minutes=10080` (7 d). **Docstring `core/security.py:257-258` still says 30 min — stale.** Blacklist prefixes `security.py:39-40`; revocation read direction is phase 04 `D-04-F` (six read sites per `VAL-07-004`) | **phase 04** |
| Rate-limiter trust boundary | `core/security.py:106-151` — settings `True` (`config.py:584`), class default `False` (`:107`), sync twin `RateLimiter:58-103` with the same default. Key is `request.client.host`; gate closed ⇒ **the proxy's bridge address**. `tests/test_rate_limiting.py:124` pins `login:127.0.0.1` | **phase 15** (defaults) / **04** (`D-04-D`, `D-04-E`) / **07** (`EXT-004`) |
| RFC 7807 leakage | Four handlers in `utils/exceptions.py`; the 422 handler copies `input` verbatim (`:287`); `global_exception_handler:330-345` is clean; `get_error_title` is a closed mapping. Spec: `error-format.md:42, 91-94` omits `input` | **phase 15** |
| Stack traces | `debug` default `False` (`config.py:542`); `validate_debug_mode` refuses it in production (`config.py:658-666`). Handler never passes `exc_info`. Residual: Starlette debug page when `DEBUG=true` + `ENV=development` | **phase 15** (record) / **phase 10** |
| Logging hygiene — retrieval handle | `temp_password_store.py:44,69,71` `token[:8]`; `auth_service.py:599` `retrieval_token[:8]`; `admin.py:432` `retrieval_token[:8]`; `nginx.conf:10` default combined `access_log` writes the **full URI** incl. `/admin/temp-passwords/<token>`; no `log_format` override anywhere | **phase 04** (`D-04-K`, `C04-5`) / **phase 12** (nginx `log_format`) |
| Logging hygiene — credential values | Only the `exc.errors()` path reaches a **value** (SEC-005). No `logger.*(password…)` site found; `security.py:247` logs only the exception. Rotation: 10 MB × 5 generations on `app_data` | **phase 15** (value) / **phase 07** (`EB-3` volume bound — explicitly *not* a sink fix, `07-…md:642`) |
| Dependency / image supply chain | `Dockerfile`: `node:20-alpine`, `python:3.12-slim-bookworm` (base + prod-base), `redis:7.4-alpine`; `UV_VERSION=0.11.16` **pinned as a build arg** (`compose.yml:99`); `uv.lock` present. **Images are floating tags, not digests** | **phase 01** (`B1`/`.dockerignore`) / **phase 10** |
| Container security options | `compose.yml`: `app` has `read_only: true` `:150`, `security_opt: [no-new-privileges:true]` `:152-153`, `cap_drop: [ALL]` `:155-156`; `nginx` `read_only: true` + tmpfs `:285-286`. **`rq-worker` (`:191-266`), `redis` (`:171-188`), `db` (`:16-53`), `migrate` have none.** Runtime confirms: only `app` carries `CapDrop`/`SecurityOpt`. `override.yml:123`, `:164` set `read_only: false` for dev | **phase 10** (`B8` = rq-worker boundary; `B13` = nginx log destinations). **Redis boundary is unassigned** |
| DB role privileges | `init-scripts/01-create-app-role.sh:24-42` — `mkobi_app` LOGIN, `CONNECT`, `USAGE` on `public`, `SELECT/INSERT/UPDATE/DELETE ON ALL TABLES`, `USAGE ON ALL SEQUENCES`, plus `ALTER DEFAULT PRIVILEGES`. No `CREATEDB`. Single role ⇒ app can read `users.password_hash` and every table; no read-only separation | **phase 14** (schema) / **phase 12** (authorization) |
| File permissions on the artefact volume | `app_data:/app/data` on `app` (`:146-147`) and `rq-worker` (`:240-241`); log at `/app/data/logs/app.log`; uploads at `/app/data/tmp_uploads`. Runtime: `app` runs `User=app`; `/app` stays root-owned in dev (`override.yml:99-104`) | **phase 06** (`D-06-K` read-write mount of the artefact area — Coordinator, via `10-…md:176`) / **phase 10** |
| Admin-surface protections | Bootstrap from `ADMIN_USERNAME`/`ADMIN_PASSWORD` (`compose.yml:126-127`, `:216-217`; required-vars fail closed); `require_admin_role` exists and is **not** on `/health/detailed`; `reset_password_admin` writes after commit (`auth_service.py:590-596`); retrieval endpoint `admin.py:420-433` collapses refusal classes to one 404 (phase 04 `AB-2`); `register-request` **does not enumerate** — byte-identical `ValueError` on four conditions (`auth_service.py:423,429,437,443`) surfaced through one `detail=str(e)` at `auth.py:239` (the `Invalid email format` fifth shape at `:402-407` discriminates on syntax, not existence) | **phase 04** (`AB-1`, `AB-2`, `AB-10`, `D-04-A`, `D-04-B`) |

---

## 4. In-flight and already-landed work

| Commit / file | Touches | Bearing on phase 15 |
|---|---|---|
| `2174895` *fix(user): own the unit of work for user writes* | moved the reset/approve credential write into `services/auth_service.py` | **invalidates the report's `admin.py:320-321` anchor**; new sites `:594-596`, `:667-669` |
| `2de4156` *refactor(auth): own the approval transaction in AuthService* | same file, `approve_registration_request` docstring `:613-621` | same |
| `9a77625` *fix(rq-worker): liveness diagnosis; pin queue name* | `core/task_queue.py` `DEFAULT_QUEUE_NAME` | adjacent to SEC-008 Path A |
| `ab76989` + `863b81b` *advisory lock / non-vacuous leak guard* | `db/advisory_lock`, `data_worker.py` | landed; dirty diff continues it |
| **DIRTY** `src/mkobi/workers/data_worker.py` (+90) | `_process_csv_file_async` split into two ordered commits; `mark_orphaned_uploaded_logs_failed` horizon from `get_config().stale_processing_timeout_minutes` | **SEC-008 Path B's two `message=f"Processing failed: {error_msg}"` sites (`:626`, `:695`) are inside this in-flight edit** |
| **DIRTY** `tests/test_processing_logs.py` (+257) | durable PROCESSING transition tests | re-baselines the same worker tests |
| **DIRTY (new since run start)** `tests/test_data_worker.py`, `tests/test_file_cleanup.py` | landed by a concurrent agent mid-run | further narrows the window in which `data_worker.py` may be edited |
| `.ai/tasks/B3-txn-003-durable-processing-transitions.yaml` | queued | must close before phase 15 edits `data_worker.py` |
| `.ai/tasks/B1-txn-001-transaction-ownership.yaml`, `B2-txn-005-rebuild-exclusion.yaml` | queued | phase 02/03 work, no phase-15 seam |

Plans **01–14** are untracked and unexecuted (14 landed mid-run); none is committed. Nothing is landed from any of them,
so no phase-15 seam is yet blocked by a *landed* sibling commit — but see §5 for the ordering risk.

---

## 5. Discrepancies and risks

### 5.1 Stale / drifted anchors (evidence table for the Planner)

| Finding | Report anchor | Actual at `863b81b` | Δ |
|---|---|---|---|
| SEC-002 | `admin.py:320-321` | `auth_service.py:667-669` | **moved (stale symbol location)** |
| SEC-002 | `auth_service.py:577-583` | `auth_service.py:594-596` | +17 |
| SEC-002 | `config.py:581` | `config.py:587` | +6 |
| SEC-003 | `config.py:578` | `config.py:584` | +6 |
| SEC-006 | `app.py:298`, `:320-326`, `:330-333`, `:349-356` | `app.py:318-319`, `:341-346`, `:350-353`, `:355-364` | **+20** |
| SEC-007 | `add_middleware` `:248,257,263` | `:267,276,282` | +19 |
| SEC-008 | `admin.py:230` | `admin.py:266` | +36 |
| SEC-008 | `deps.py:567` | `deps.py:570` | +3 |
| SEC-008 | `task_queue.py:76` | `task_queue.py:78` | +2 |
| SEC-008 | `data_worker.py:571-594,606-631` | `:606-609,626` + `:671-674,695` | restructured |
| SEC-008 | `data_service.py:336` | `data_service.py:337` | +1 |
| SEC-004 | `api.types.ts:209-215` | `api.types.ts:203,208-215` | −6 |
| SEC-009 | `authToken.test.ts` | `.../model/__tests__/authToken.test.ts` | path segment missing |
| SEC-001 | `tests/test_security.py:19-32` | `:19-33` | +1 |

**No symbol the report names is absent.** The only *absent* citations are the two `Dockerfile:127,183` line numbers the
report itself already flagged as superseded by a whole-repo search, and `authToken.test.ts` as a path (the file exists).

### 5.2 Refuted and contested

| Item | Status |
|---|---|
| SEC-003's key-derivation claim | **refuted.** `FORWARDED_ALLOW_IPS` has zero hits in shipped config/source/docs; runtime peers are `172.21.0.2`/`.3`. The collapse is today's state; the caller does not choose the key. Owned by 04 `AUTH-001` / 07 `EXT-004` |
| SEC-005's "possible contract break" framing | **refuted in its favour** — `error-format.md:91-94` omits `input`; it is a conformance fix (VAL-15-002) |
| SEC-005's "a shipped test must change" | **refuted** — `tests/test_auth_api.py:556-560` matches on `msg` |
| SEC-008's "25 route sites across ten modules" | **re-typed** — 25 tokens, 23 mechanism sites, 11 route modules, 1 dependency, 1 non-member (VAL-15-003) |
| SEC-009's "30 minutes" | **stale** — `config.py:298` is 15; `core/security.py:257-258` docstring is the stale artifact |
| SEC-006's zone title "Unauthenticated Inbound **Writes**" | paraphrase; the route performs no write |

### 5.3 Tests that will break

| Test | Breaks on | Note |
|---|---|---|
| `tests/test_security.py::TestTruncatePassword` (`:22-27`, `:29-33`) | SEC-001's byte-bound + raise-on-mint | encodes the defect |
| `tests/test_rate_limiting.py:124`, `:138-139` | SEC-003's key derivation | **also** breaks 04's `AUTH-001` — already recorded as `VAL-04-002` |
| `tests/test_auth_api.py:556-560` | **nothing** for SEC-005 | passes unchanged |
| `frontend/.../__tests__/authToken.test.ts` (whole file) | SEC-009's opt-in flag | dev-branch fixture; the *missing* test is the prod-memory assertion |
| `tests/test_config.py::TestRqWorkerComposeWiring` | any compose-text edit (plan 10 `B8`) | reads **both** compose files |

### 5.4 Ordering risks

| # | Risk | Detail |
|---|---|---|
| **R1** | **`data_worker.py` collision** | The file is dirty with the in-flight durable-transition work (`B3-txn-003`). SEC-008 Path B's two `message=f"Processing failed: {error_msg}"` sites sit inside `_process_csv_file_async`. Editing before `B3` lands risks the "re-apply a landed change" failure plan 04 warns about at `04-…md:594` |
| **R2** | **`compose.yml` triple ownership** | Phase 01 `B2` (CFG-006 env wiring) · phase 10 `B8` (rq-worker boundary) · phase 15 SEC-003 part 3 (dev-overlay `RATE_LIMITER_FAIL_CLOSED`) all edit `docker/docker-compose*.yml`. Plan 10's compose-text contract test covers the collision |
| **R3** | **SEC-005 → SEC-001 test re-baselining** | The report's own roadmap says steps 1, 2 and 4 all re-baseline the 422 surface. Sequencing them as separate passes re-baselines three times |
| **R4** | **`utils/exceptions.py` triple ownership** | SEC-005 (strip `input`) · SEC-007 (stamp headers on 500) · SEC-008 (close the `detail` vocabulary) all land in the same 346-line module. Three commits, one file — must be serialised |
| **R5** | **Frontend boundary** | SEC-004's fix needs `GraphConfigDict` ↔ `GraphDataWithConfig` reconciled in one change; `frontend/src/**` is phase 13/16's per `04-…md:589`. A backend-only validator turns today's silent mismatch into a **422 on a path the shipped client walks** |
| **R6** | **Plan 14 landed mid-run** | `processing_logs.message` (SEC-008) and any new `ErrorCode` member need a schema owner. Plan 06 `C06-3` routes `artifact_filename` to phase 14. **Plan 14 now exists but was not read for this context** — its block table must be checked for an overlap with SEC-008's column fix before decomposition |

### 5.5 Un-assigned seams (no plan owns them)

| Seam | Why it matters |
|---|---|
| **Redis container boundary** — no `read_only` / `cap_drop` / `security_opt` / non-root user on `compose.yml:171-188`; runtime confirms all four absent | Directly bounds SEC-002's blast radius. Plan 10 `B8` names `rq-worker` and `migrate`; plan 07 `DP-3` is "where Redis bounds live" (the *application-side* bounds, not the container) |
| **Trusted-host policy absent** — no `TrustedHostMiddleware`, no `allowed_hosts` | The structural twin of SEC-003's key defect. Runtime-relevant in dev, where the host-published app port binds with no host-IP restriction (`override.yml:114-118`) |
| **Floating image tags** — `python:3.12-slim-bookworm`, `node:20-alpine`, `redis:7.4-alpine` are tags, not digests | Supply-chain seam; `uv.lock` and the pinned `UV_VERSION` are the only pins |

---

## 6. Decision points for the Planner — leave these open

Genuine technical uncertainty. **This run picks none.**

| # | Decision | Alternatives | Chooser |
|---|---|---|---|
| **D-15-A** | SEC-001 byte-bound enforcement surface | (a) `field_validator` on UTF-8 byte length via `validate_password_or_raise` · (b) Pydantic `Annotated[..., StringConstraints(max_length=…)]` on the two minting fields | Planner + Coordinator |
| **D-15-B** | SEC-001: does `_truncate_password` raise on the **minting** side while verification keeps truncating, or is the asymmetry maintained by caller discipline? | (a) symmetric raise · (b) asymmetric by call-site | Planner |
| **D-15-C** | SEC-002 store shape | (a) keep password in issuing-process memory, put only a random key in Redis · (b) AEAD under a `_FILE` key · (c) store a derivation and route retrieval through a second channel. **The validator already showed (b) leaves the credential recoverable by anyone with Redis *and* the environment** | Coordinator (deployment-scheduled) |
| **D-15-D** | SEC-002 rollout window | drain the store vs accept the bounded loss window; and whether `requirepass` + ACL is one commit with the app/worker/healthcheck or two | Coordinator |
| **D-15-E** | SEC-005 order | `SecretStr` on the password fields first (removes the value at source, fixes the frontend's `input?: string`) vs strip `input` in the handler first (one line) | Planner |
| **D-15-F** | SEC-005 guard | which test layer pins "no `input` key and neither password in the log record" — and whether `docs/08-security/error-format.md` gains an explicit "no `input`" sentence | Planner + docs owner |
| **D-15-G** | SEC-006 `/health/detailed` fork | (a) gate with existing `require_admin_role` (one line) · (b) reduce the body to readiness. **The reader's to take** — the validator explicitly declined it | Coordinator |
| **D-15-H** | SEC-006 reconciler counters | keep `lease_state` / `sweep_count` / `unprotected_ticks` in the public body or move them behind (a) | Coordinator |
| **D-15-I** | SEC-004 schema reconciliation direction | (a) add `metrics`/`orientation`/`barmode`/`showlegend` to `GraphConfigDict` · (b) remove them from `GraphDataWithConfig` and from `ChartRenderer` — a product decision, and (b) is a real frontend behaviour change | Coordinator + phase 13 |
| **D-15-J** | SEC-004 enforcement shape | `field_validator(mode="before")` raising `AppException(ErrorCode.VALIDATION_ERROR)` · vs replacing the `TypedDict` with a Pydantic model carrying `extra="forbid"` | Planner |
| **D-15-K** | SEC-008 closed vocabulary | derive `detail` from `ErrorCode` at all 23 sites · vs introduce one sanitising helper the sites call. `deps.py:570` (a curated JWT-library message) and `exceptions.py:321` (developer-supplied) are **separate decisions on their own merits** | Planner |
| **D-15-L** | SEC-008 `processing_logs.message` | stable per-failure-class message with the full text only in `logger.exception` (already present at `:609`/`:674`) · vs wait for phase 06's `artifact_filename` (C06-3) and phase 14's migration — **plan 14 landed mid-run and was not read for this context** | Coordinator (cross-phase) |
| **D-15-M** | SEC-003 `fail_closed` shape | required keyword arg · vs invert to `admit_on_redis_error: bool = False`. Also: is the dead `AuthService._rate_limiter` deleted (report's preference) or given a reader | Planner |
| **D-15-N** | SEC-009 opt-in flag name and test shape | `VITE_ALLOW_INSECURE_TOKEN_STORAGE` opt-in · vs delete the branch. **The validator prefers the opt-in**; the real gap is the *absent* production-memory assertion | Planner + phase 13 |
| **D-15-O** | Whether phase 15 takes the un-assigned seams (Redis container boundary, trusted-host policy, image pinning) or files them as cross-phase hand-overs | take · hand to 10/04/01 · record only | Coordinator |

---

## 7. Coverage ledger

| ID | Verdict | Evidence anchor(s) at `863b81b` |
|---|---|---|
| **SEC-001** | **substantiated** | `core/security.py:37-38,154-187,208,236`; `models/auth.py:181-183,203-208`; `services/auth_service.py:498,505`; `tests/test_security.py:19-33` |
| **SEC-002** | **substantiated** | `core/temp_password_store.py:39,41,63-66`; `config.py:587`; `services/auth_service.py:594-596,667-669` (**report's `admin.py:320-321` stale**); `docker-compose.yml:171-188`; **runtime `docker inspect` → `Cmd=["redis-server"]`, ip `172.21.0.2`** |
| **SEC-003** | **substantiated** (defaults / dead instance / dev-overlay gap); **key clause `refuted`** | `config.py:584`; `core/security.py:107,137-151`; `api/routes/auth.py:83-89,309-315,562-568`; `client_errors.py:45-50`; `upload.py:144-152`; `auth_service.py:66` (1 grep hit); `compose.yml:142,236`; `override.yml` **0 hits**; repo-wide `FORWARDED_ALLOW_IPS` **0 hits**; **runtime peers `172.21.0.2`/`.3`**; `tests/test_rate_limiting.py:124,138-139` |
| **SEC-004** | **substantiated** (consequence widened) | `models/types.py:138-152`; `models/graph.py:15,45`; `frontend/src/shared/types/api.types.ts:203,208-215`; `ChartRenderer.tsx:15-18,37,105-106,149` |
| **SEC-005** | **substantiated** | `utils/exceptions.py:263-297` (`:272-275`, `:287`), `:330-345`; `models/auth.py:14,100,178-208`; `core/logging_config.py:114-122`; `compose.yml:129,224`; **`docs/08-security/error-format.md:42,91-94`**; `frontend/src/shared/api/errorHandler.ts:52,68,128-137`; `tests/test_auth_api.py:556-560` (passes unchanged) |
| **SEC-006** | **substantiated** (anchors +20) | `app.py:318-319,341-346,350-353,355-364`; `:297-316`; `init-scripts/01-create-app-role.sh:24`; `nginx.conf:43-46`; **runtime `GET /health/detailed` → 200 unauthenticated, `lease_state:"holder"` + `path:"frontend/dist"` disclosed** |
| **SEC-007** | **substantiated** | `app.py:67-87`, `add_middleware` `:267,276,282`; `utils/exceptions.py:330-345`; `nginx.conf:20-23,30`; no `X-Frame-Options` in `app.py` |
| **SEC-008** | **substantiated** on substance; count re-typed (23+1+1) | 25 `detail=str(` anchors re-classified (`admin.py:91,127,266`; `auth.py:239,510,599`; `dashboards_access.py:114`; `dashboards_crud.py:151,389`; `dashboards_graphs.py:104`; `data.py:203,209`; `graphs.py:131,378`; `layouts.py:108,348`; `processing_configs.py:192,265`; `upload.py:242`; `users.py:81,258,312,366` = **23**); `deps.py:570`; `exceptions.py:321`; `core/task_queue.py:78`; `workers/data_worker.py:607,609,626,674,695`; `services/data_service.py:337,341` |
| **SEC-009** | **substantiated** ("30 min" **stale** → 15) | `authToken.ts:64,74,89,105,112,124,139,148`; `.../model/__tests__/authToken.test.ts:11-21`; `core/security.py:416-441`; `config.py:298`; `override.yml:76` |
| **VAL-15-001** | **upheld** | §2 SEC-003 clause 4; `override.yml:119` (only uvicorn launch, no proxy flag); runtime bridge IPs |
| **VAL-15-002** | **upheld** | `docs/08-security/error-format.md:42,91-94`; `errorHandler.ts:128-137`; `tests/test_auth_api.py:556-560`; consumer search for `input` = 1 non-consumer |
| **VAL-15-003** | **upheld exactly** | 25 tokens / 23 route sites / 11 modules / `deps.py:570` / `exceptions.py:321` |
| **VAL-15-004** | **upheld** | `api.types.ts:203,208-215`; `ChartRenderer.tsx:15-18,37,105-106,149` |

**Totals — `SEC-`:** substantiated **9** (of which SEC-003 partially refuted on one clause, SEC-008 re-typed on count);
stale **1** (SEC-009's 30-minute figure) · **13** line anchors drifted, **1 symbol location moved**
(`admin.py:320-321` → `auth_service.py:667-669`) · refuted **0 findings, 3 claims** (SEC-003 key, SEC-005 contract-break,
SEC-005 test-blocker) · already-fixed **0** · merged away **0** · already owned elsewhere **0 whole / 6 partial**.

**Totals — `VAL-15-*`:** 4 substantiated, 0 refuted, 0 stale.