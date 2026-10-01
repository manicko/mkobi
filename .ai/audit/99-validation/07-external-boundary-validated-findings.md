---
phase: 07-external-boundary
executed: 2026-09-30
executor: validator
problems-only: true
baseline: c3c0a61bf41cad68bf3a3ac105de91ea63c82268
baseline-dirty: >-
  src/mkobi/config.py, src/mkobi/db/starter.py, tests/test_config.py,
  tests/test_starter.py modified; .ai/builders, .ai/structure, .ai/models,
  .ai/templates, .ai/plans deleted.
baseline-note: >-
  HEAD moved twice during this validation: c3c0a61 -> 5a2cfb6 (config.py, db/starter.py and their
  tests) -> b23a9cb (app.py, config.py, tests/test_config.py). Every anchor this report relies on
  resolves at c3c0a61, the revision the input filed against; the app.py and config.py anchors have
  since moved and are recorded as VAL-07-009 with their current line numbers.
findings: 10
by-severity:
  CRITICAL: 0
  HIGH: 4
  MEDIUM: 4
  LOW: 2
validation-findings: 11
by-validation-severity:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 8
  LOW: 3
---

# Phase 07 — Validated Findings (External Boundary)

## Summary

All ten `EXT-` findings were re-derived from the executing path, every location reference resolved
mechanically first, and the two load-bearing runtime claims were reproduced independently against the
live dev stack: **eight confirmed, two merged**. The EXT-004 merge ruling is upheld on stronger grounds
than the input argued — phase 04's AUTH-001 already named the refresh and register-request surfaces at
the same anchors EXT-004 cites — and EXT-005, which AUTH-002 and AUTH-006 already hold at the same
anchors, was filed with no merge ruling at all. The single most consequential thing re-established is
the Redis-on-the-authentication-path pair: with `mkobi-redis-1` paused, `GET /health` returns
`200 {"status":"healthy","database":"connected"}` in 0.014 s and `/health/detailed` returns
`200 "status":"healthy"` in 0.012 s, while `GET /api/v1/auth/me` with a *valid* bearer returns
`401 AUTHENTICATION_FAILED` with `detail: "Authentication failed"` in **59.396 s** and
`GET /api/v1/dashboards/` returns the same in **58.792 s**; both recovered to 200 in 0.060 s after
`docker unpause`. The 401 is provably the dependency path and not an ordinary rejection:
`detail="Authentication failed"` occurs exactly once in `src/mkobi` — at `deps.py:574`, inside the
catch-all at `deps.py:570-576` — and the server-side traceback runs
`deps.py:506 → security.py:503 → redis/asyncio/connection.py:350 retry.call_with_retry →
redis.exceptions.TimeoutError: Timeout reading from redis:6379`.

Four of the input's own negative results were tested and all four hold: no outbound boundary exists
(independent 40-match search inventory over 115 `.py` files, zero imports or call sites), the
rate-limiter failure direction is a declared value defaulting fail-closed and wired on every surface,
newlines in the untrusted body are JSON-escaped so no log injection is possible, and `/auth/logout`
cannot half-apply. The empty CRITICAL band is **genuine and not merely unclaimed**: every candidate
was tested against the CRITICAL predicate and each fails it on a named ground (Appendix J).

The report needs repair in three places the reader must not act past: the retry arithmetic in EXT-002
is wrong, EXT-005 is a duplicate of two findings phase 04 already filed, and EXT-004's recommended
`forwarded_allow_ips="*"` alternative is a brute-force bypass in the tier where this project publishes
the app port unbound.

## Findings

Identifiers are preserved; none was renumbered. Each block carries its disposition inside the
Observation field, because the shared template mandates no disposition field (Appendix H).

### EXT-001 — The health probe reports `healthy` while every authenticated request fails

**Severity** — HIGH

**Zone** — A degraded result the consumer cannot tell from a real one

**Observation** — Disposition: **confirmed**; band upheld at HIGH. Re-derived from the executing path.
`GET /health` (`app.py:257-276`) probes exactly one dependency, `await db.execute(text("SELECT 1"))` at
`app.py:267`, and returns `{"status": "healthy", "database": "connected"}` at `:269`; the `except`
arm at `:271-276` returns 503. `GET /health/detailed` (`app.py:278-316`) probes PostgreSQL at `:295`
and `os.path.isdir("frontend/dist")` at `:311`, and returns `dict[str, Any]` — it cannot return a
non-200 status at all. `Select-String -Pattern "redis"` over `src/mkobi/app.py` returns **zero
matches**: no Redis reference exists anywhere in the module. The revocation check every protected
endpoint runs first is `is_token_revoked` (`deps.py:506`, body at `security.py:492-504`) and
`is_user_tokens_revoked` (`deps.py:526`, body at `security.py:542-554`), both a bare
`await redis_client.exists(key)` with no guard; `jti` is always present (`security.py:286`, `:327`),
so the call is unconditional. The input's anchor set resolves exactly at both `c3c0a61` and `5a2cfb6`
(`app.py:218`, `:220-221`, `:245-255`, `:257-276`, `:278-316`, `:300-306`); the working tree has
drifted −9 (VAL-07-009). The Docker `HEALTHCHECK` at `docker/Dockerfile:176-177` and
`docker/docker-compose.yml:142-147` are both `curl -f http://localhost:8000/health` and resolve;
`docs/05-health/health-api.md:179-181` instructs operators to use these endpoints as Kubernetes
`livenessProbe`/`readinessProbe` targets, to "determine instance availability" with a load balancer,
and to "alert on non-200 responses" — the quoted words are present verbatim. Band upheld: the probe is
a guard that permits where it was meant to bound, and the direction is a hard-coded branch (only the
database is enumerated in the code; Redis coverage is absent, not declared). Appendix C records the
competing MEDIUM clause.

**Evidence** — Independent reproduction, `mkobi-redis-1` paused and restored in one command block:

| Probe | Redis reachable | Redis paused |
|---|---|---|
| `GET /health` | `200` in 0.030 s | `200 {"status":"healthy","database":"connected"}` in **0.014 s** |
| `GET /health/detailed` | `200` in 0.022 s | `200 "status":"healthy"` in **0.012 s** |
| `GET /api/v1/auth/me` (valid bearer) | `200` in 0.321 s | **`401` `detail:"Authentication failed"` in 59.396 s** |
| `GET /api/v1/dashboards/` (valid bearer) | — | **`401` `detail:"Authentication failed"` in 58.792 s** |

The bearer was minted in-container with the application's own `create_access_token` for a live,
active user, so the 401 is a genuine authenticated request refused, not a missing credential. The
control is decisive: `/auth/me` **without** a credential returns `detail: "Not authenticated"` (the
`HTTPBearer` auto-error), a different string from a different code path. Server-side:

```
{"level":"ERROR","module":"deps","function":"get_current_user_dependency",
 "message":"Error getting current user: Timeout reading from redis:6379",
 "exception":"... File \"/app/src/mkobi/api/deps.py\", line 506, in get_current_user_dependency
   if await is_token_revoked(redis_client, jti):
   File \"/app/src/mkobi/core/security.py\", line 503, in is_token_revoked
     exists = await redis_client.exists(key)
   ... File \"/app/.venv/.../redis/asyncio/connection.py\", line 350, in connect
     await self.retry.call_with_retry(
   redis.exceptions.TimeoutError: Timeout reading from redis:6379"}
```

Recovery verified: `/health` 200 in 0.025 s and `/auth/me` 200 in 0.060 s after `docker unpause`;
`ACL WHOAMI -> default`, `ACL LIST -> user default on nopass sanitize-payload ~* &* +@all`,
`redis-cli ping -> PONG`, container status `(healthy)`. The one Redis key created during this
validation was deleted (Appendix K).

**Consequence** — Unchanged and re-measured: during a Redis outage the deployment reports itself
healthy while serving no authenticated page. Note one refinement the input does not record: the dev
override disables the container healthcheck (`docker/docker-compose.override.yml:111-112`), so the
Docker-health consequence is a production-tier property; the *application* 200 is the tier-independent
part, and it is the answer the k8s/lb/uptime contract at `health-api.md:179-181` consumes.

**Recommendation** — Executable as written, and verified to have no shipped test blocker:
`tests/test_health.py:110-125` asserts the *presence* of `database` and `static_files` components
(`assert "database" in components`) rather than an exact component set, so adding a `redis` entry does
not break it, and the other five assertions check only status code and `status == "healthy"`. Add the
`PING` at `app.py:257-276` and `app.py:293-306`, return 503 on failure, update
`docs/05-health/health-api.md:164-169` and `:179-181` in the same change. **Co-ownership:** phase 10
took in "the health, liveness and readiness endpoint and probe contract (from 01)"
(`10-audit-production-ops.md:17-18`) and owns "the health contract"; 10 must be named as co-owner of
the probe-contract half so two teams do not edit `app.py:257-316` independently. This is a
cross-reference with a named co-owner, **not** a merge into 10 — see VAL-07-004 and Appendix F.

### EXT-002 — One Redis outage takes down every page rather than one feature, and reports it as a bad credential

**Severity** — HIGH

**Zone** — The derived dependency set: what the request path cannot answer without, and what each one's failure takes down

**Observation** — Disposition: **confirmed**, with the asserted cause **refuted** (VAL-07-006) and one
element **merged** into AUTH-008 (VAL-07-004). The surviving and distinct content is the blast radius
and the undeclared cost bound. Two dependencies are preconditions of every route: PostgreSQL via
`get_db_dependency` and Redis via `get_redis_client_dependency` (`deps.py:475`). `jti` is set
unconditionally by both token factories (`security.py:286`, `:327`), so the Redis read is not optional
on any protected request. The catch-all at `deps.py:570-576` converts any Redis exception into
`AppException(AUTHENTICATION_FAILED, "Authentication failed")`. The blast radius of **53 authenticated
operations** was re-derived from the live document, not taken on trust: 60 operations across 43
declared paths, 53 carrying `security`, 7 anonymous (Appendix D). The client construction at
`src/mkobi/core/redis_client.py:46-52` passes only `host`, `port`, `db`, `password`,
`decode_responses=True` — no `socket_timeout`, no `socket_connect_timeout`, no `retry` — and the
input's structural point is exact: the effective bound is held by the lockfile, not by this project.

**Evidence** — The 401 and its cause are re-established in EXT-001's evidence. The bound itself was
read from the running image rather than inferred:

```
REDIS_PY_VERSION 8.0.0
KW socket_timeout = 5            KW socket_connect_timeout = 5
KW retry = <redis.asyncio.retry.Retry object>
RETRY_RETRIES 10   RETRY_SUPPORTED ['TimeoutError','ConnectionError']
BACKOFF_TYPE ExponentialWithJitterBackoff   BACKOFF_VARS {'_cap': 1, '_base': 0.01}
```

`uv.lock:1817-1818` resolves `redis` to `8.0.0`, as filed. `socket_timeout`, `socket_connect_timeout`
and the retry policy are therefore library defaults that **no code in this project sets**. The
measured cost, 59.396 s, is 11 attempts of a 5 s read timeout plus jittered backoff; the input's
"three retries of a 5 s timeout" would be 20 s and is refuted — see VAL-07-006. A direct measurement of
the same client against an unassigned address in the app container's own subnet
(`172.21.0.0/16`, app `172.21.0.6`, redis `172.21.0.4`) failed with
`ConnectionError "Error 113 connecting to 172.21.0.199:6379"` after 36.823 s, confirming the same
undeclared default governs the connect path under a different failure mode.

**Consequence** — Unchanged: one Redis instance going away is a total outage of the authenticated
product with no degraded mode, presented as a credential fault. Two facts the input does not carry are
added here. First, the browser-visible form: the SPA's axios interceptor answers 401 by attempting a
silent refresh, which also depends on the same Redis, so the user-visible state is a silent sign-out
loop across all users at once. Second, `docs/01-auth/auth-api.md:510` reads *"Deactivated users
(`is_active=false`) receive HTTP 401 on any authenticated endpoint"* — the anchor is `:510`, not the
`:511` the input cites, and an operator following it reads the outage as a deactivation event.

**Recommendation** — Part (1), the explicit bound, is executable and correct. Part (2) is executable,
but its stated blocker is false: the input says `SERVICE_UNAVAILABLE` "does not exist in
`src/mkobi/models/enums.py` and would need adding". It exists at `enums.py:197`, is mapped to 503 at
`utils/exceptions.py:36` and titled at `:187` (VAL-07-003). The second half of part (2) — catching
`redis.exceptions.RedisError` around the two revocation reads — is the *same change* phase 04's AUTH-008
recommends at the same sites; phase 04 owns that edit (VAL-07-004). The input's statement that
`tests/test_auth.py:328,365` cover the rate limiter's directions rather than the revocation path is
correct and confirmed.

### EXT-003 — An anonymous 5 MB body is written verbatim into a single ERROR log record with no field cap

**Severity** — HIGH

**Zone** — The untrusted body as it is logged

**Observation** — Disposition: **confirmed**; band upheld at HIGH, matching the rubric's HIGH clause
"a body written to the log verbatim from anyone, with no bound on the volume" almost verbatim.
`POST /api/v1/client-errors` (`client_errors.py:24-68`) requires no credential and logs the caller's
body at `client_errors.py:62-68`: `payload.error.get("message", "Unknown error")`, `payload.url`,
`payload.componentStack`, with no truncation, no sanitiser and no mask. `ClientErrorPayload`
(`models/data.py:504-528`) declares `error: dict[str, Any]` at `:511` and a `model_config` at
`:517-527` carrying only `from_attributes` and `json_schema_extra` — **no `extra` policy and no
`max_length` on any field** — so neither the container nor the body is bounded by the model. The route
has no `Content-Length` check. The only ceiling on this path is nginx's server-level
`client_max_body_size 100m` (`nginx.conf:18`), which applies because `location /api` (`nginx.conf:34`)
does not override it, and `location /` (`nginx.conf:49`) serves the SPA. The volume bound is
`100 / 3600 s` keyed on `f"client-errors:{client_ip}"` (`client_errors.py:49-50`) with
`client_ip = request.client.host` at `:42`, i.e. one constant in the shipped deployment (EXT-004).

**Evidence** — Independent reproduction, no `Authorization` header: a **5,000,160-byte** body returned
`204` in 0.329 s and produced one log record of **5,000,321 characters**, read from the container's
stdout log without printing it. The record length tracks the body length; no cap exists at any point.
The log-injection negative result is confirmed on its own terms: a body carrying
`LINE1\n{"level":"INFO","message":"forged"}\n<password>hunter2</password>` produced **one physical
log line of 382 characters** in which both newlines appear as the two-character escape `\n` and the
inner JSON quotes are escaped — the record is emitted through the JSON formatter, so no caller can
forge a record boundary. The credential-shaped field is written verbatim and unmasked, which is the
finding. The log *file* handler is not active in the dev tier (`/app/data/logs/` is empty), so the
5 MB record went only to stdout and left no file on the `app_data` volume.

**Consequence** — Unchanged: any credential, token or personal datum a browser places in the reported
`error` object is persisted verbatim, and an anonymous caller controls the record size up to the proxy
ceiling. The two halves of the ceiling are separately real and the input keeps them separate
correctly — a ~100 MB per-request ceiling at `nginx.conf:18`, and a 100/hour budget that is a *shared*
pool at `client_errors.py:49-50` rather than a per-caller bound.

**Recommendation** — Executable as written. Cap the three fields before the log call and log the
untruncated length beside the capped value; narrow `ClientErrorPayload.error` to the fields actually
read with `max_length`; add a `Content-Length` pre-check. Note for the reader that the
`error`-narrowing half converts a silently-accepted oversized body into a `422`, which is a behaviour
change for whatever client currently posts it — the one shipped caller is
`frontend/src/shared/components/ErrorBoundary.tsx:40`, so that reporter is the client to check.
No shipped test asserts the current verbatim behaviour.

### EXT-004 — The whole inbound budget collapses onto the proxy's address: five distinct callers charged one key

**Severity** — HIGH

**Zone** — The aggregate ingress budget: what bounds arrival, how its scope is shared, and whether one caller is recognised the same way on every surface

**Observation** — Disposition: **merged** into phase 04 AUTH-001 — the ruling is upheld, but its stated
justification is refuted, and the residual the input retains is not distinct (VAL-07-001, VAL-07-010).
The mechanism is real and was reproduced without a forwarder. `docker/Dockerfile:179` starts uvicorn
with `--workers 4` and no `--forwarded-allow-ips`; `docker-compose.override.yml:109` does the same for
dev. uvicorn 0.49.0 in the running image resolves `Config("mkobi.main:app").forwarded_allow_ips` to
`'127.0.0.1'` with `proxy_headers=True`, and `uvicorn/middleware/proxy_headers.py` consults
`X-Forwarded-For` only `if client_host in self.trusted_hosts` — for a `172.21.0.x` peer the header is
never read. The five-bound inventory is confirmed: `login:{client_ip}` 5/300 s (`auth.py:83-90`),
`refresh:{client_ip}` 10/300 s (`auth.py:309-315`), `register-request:{client_ip or email}` 3/3600 s
(`auth.py:566-568`, key composed at `:566` verbatim as filed), `client-errors:{client_ip}` 100/3600 s
(`client_errors.py:49-50`), `upload:{current_user.id}` 100/3600 s (`upload.py:144-148`). All five
counters live in Redis, so the four workers and the single Redis instance
(`docker-compose.yml:157-173`) do **not** multiply any budget — that half of the input's analysis is
correct and worth keeping. `upload:` is keyed on a principal and is unaffected, correctly excluded.

The merge justification is where the input is wrong. It states AUTH-001 "filed the collapse for the
`login:` key only and did not establish that three further surfaces share it". AUTH-001's Consequence
names them: *"The same keying defect applies to `/auth/refresh` (10 per 300 s, `auth.py:309-315`) and
to `/api/v1/auth/register-request` (3 per 3600 s, `auth.py:566-569`)"* — the same two anchors EXT-004
uses — and its Roadmap Step 6 already schedules the documentation correction at `auth-api.md:46,96`.
The merge therefore stands on stronger ground than claimed: same root cause, same call sites, same
anchors, and **AUTH-001's own remediation already covers both surfaces the input says it missed**. The
one surface AUTH-001 does not name is `client-errors:`, which is added here to the merged item rather
than filed separately, because one `forwarded-allow-ips` line closes it too.

**Evidence** — Reproduced without a proxy container by injecting the header directly, which tests the
app's trust decision and nothing else: five requests carrying `X-Forwarded-For` of `4.4.4.4`, `5.5.5.5`,
`6.6.6.6`, `7.7.7.7`, `8.8.8.8` each returned `204`, and Redis afterwards held exactly one key —
`client-errors:172.21.0.1` (the connecting peer), value `7`, `TTL 3599` — with no key for any of the
five supplied addresses. uvicorn's effective `forwarded_allow_ips` read from the image: `'127.0.0.1'`.
The key was created by this validation and has been deleted (Appendix K).

**Consequence** — Unchanged: the platform has no per-caller throttle on any address-keyed budget in
its own shipped deployment; the budget is per proxy. The doc drift is real and measured:
`docs/01-auth/auth-api.md:46` and `:96` promise "5 attempts per 5 minutes **per IP**", and `:113`
promises "3 attempts per hour **per IP/email**" while `auth.py:566` reaches the email branch only when
`client_ip` is falsy — and `client_ip` is `"unknown"` rather than empty when `request.client` is
`None` (`auth.py:83`, `client_errors.py:42`), so **the email branch is unreachable, not merely
unlikely**. The input says "which in practice never happens"; unreachable is the stronger and correct
statement.

**Recommendation** — Not executable as written. The recommendation offers `--forwarded-allow-ips "*"`
as an acceptable alternative; in uvicorn 0.49 `always_trust` makes
`_TrustedHosts.get_trusted_client_address` return `x_forwarded_for_hosts[0]` — the **left-most** entry,
which nginx's `$proxy_add_x_forwarded_for` (`nginx.conf:38`) leaves caller-supplied. A wildcard
therefore converts the global lockout into a caller-chosen bucket: a brute-force bypass, in exactly the
tier where `docker-compose.override.yml:104-108` publishes the app port unbound and any host-reachable
caller can reach `app:8000` directly. Use the compose bridge subnet only. This is the same hazard phase
04 recorded as VAL-04-001, reached by a different door, and it is filed here as VAL-07-002 because this
report states it independently. The input's own Rollout Safety flags the risk and then recommends the
unsafe option anyway; the recommendation must be corrected before it is executed, not merely noted.

### EXT-005 — Approving a registration returns 200 and a retrieval handle for a credential that was never stored

**Severity** — MEDIUM

**Zone** — A degraded result the consumer cannot tell from a real one

**Observation** — Disposition: **merged** into phase 04 AUTH-002 (write side) and AUTH-006 (read side);
the input filed this with **no merge or adjacency ruling at all** (VAL-07-001). Both halves are already
held by phase 04 at the same anchors. AUTH-002: *"The registration-approval path has the same shape
(`api/routes/admin.py:321` store, `:330` commit, `:335` returns the handle)"*, and its Consequence
already states that *"the request is marked `APPROVED`, the `viewer` account exists with an unknown
password, and the request can never be re-approved because `admin.py:299-303` refuses any status other
than `PENDING`"* — EXT-005's consequence, verbatim. AUTH-006: `retrieve` returning `None` for all three
states and `admin.py:418-422` collapsing them into one 404 — EXT-005's read side, verbatim. Re-derived
independently here: `TempPasswordStore.store` is declared `-> None` and catches `Exception` at
`temp_password_store.py:47-48`, logging at ERROR; the caller at `admin.py:321` therefore **cannot**
check the outcome even if it wanted to — the signature forbids it, which is a stronger statement than
the input's "the return value is ignored". `retrieve` swallows at `:73-75`; `admin.py:419-423` maps
both states to 404. The approval interleaving was re-verified line by line and matches the input's
table exactly (`admin.py:307`, `:315`, `:320`, `:321`, `:324`, `:330`, `:339-345`).

**Evidence** — Accepted as filed but not re-run: the runtime reproduction required mutating the shared
`default` user's Redis ACL, which this validation declined to do on a stack other agents are using.
The static proof above is unconditional and does not depend on the transcript: a `-> None` function
that cannot raise, whose caller cannot observe the result, followed by an unconditional `200` with a
handle. This is recorded as a deliberate limit, not as agreement with the transcript.

**Consequence** — Unchanged, and *present in the live database right now*: this validation found the
probe the input ran still in place. `users` row `03c82044-ca95-4ba4-ba53-e053ce8ae150` /
`wo.probe.1395195825@example.com` with `force_password_change = true`, and `registration_requests` row
`bce038fd-1101-459d-ad55-556539d71edf` with status `approved` — the exact identifiers quoted in EXT-005's
own evidence. An account exists whose password is held by nobody, and the only recovery is direct
database surgery (VAL-07-011).

**Recommendation** — Merged into AUTH-002's remediation; do not schedule separately. Two corrections to
the text as written. The store's failure contract must be decided first because **the shipped test
suite encodes fail-open by name**: `tests/core/test_temp_password_store.py:164-181`
(`test_store_fail_open_on_error`, asserting *"Should not raise - graceful degradation"* and
`mock_logger.error.assert_called_once()`) and `:184-190` (`test_retrieve_fail_graceful_on_error`,
asserting `result is None`) both block this recommendation, and the input asserts that no shipped test
does (VAL-07-008). Phase 04's AUTH-002 names the first as a remediation blocker; this phase named
neither. Separately, this finding's "abort the approval with a 503 before `db.commit()`" **conflicts**
with EXT-008's "move the store after `db.commit()`" on the same two lines (VAL-07-005).

### EXT-006 — The credential check runs after the router's slash redirect, so every declared path answers an anonymous caller

**Severity** — MEDIUM

**Zone** — The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM as a bounded disclosure gap, but the
enumeration claim is overstated by an order of magnitude (VAL-07-007). The mechanism is exactly as
filed: Starlette's slash handling runs ahead of route resolution and therefore ahead of every
`Depends`, so a declared trailing-slash path requested without its slash answers `307` with no
credential presented, while an undeclared path answers `404`. `redirect_slashes=False` is set on
**twelve** routers, not the four cited (`auth.py:68`, `admin.py:31`, `client_errors.py:21`,
`dashboards.py:20`, `dashboards_crud.py:45`, `data.py:36`, `graphs.py:42`, `upload.py:48`,
`layouts.py:40`, `processing_logs.py:28`, `processing_configs.py:33`, `users.py:37`), and it does not
suppress the no-slash-to-slash direction that this finding is about.

**Evidence** — Anonymous probes: `GET /api/v1/dashboards` → `307` with a `Location` header;
`GET /api/v1/graphs` → `307`; `GET /api/v1/layouts` → `401` (declared slash-less, served directly);
`GET /nonexistent-spa-route` → `404`; with a caller-chosen `Host: attacker.example.com`,
`GET /api/v1/dashboards` → `307` echoing that host. From the live document: 43 declared paths, of
which **four** end in `/` — `/api/v1/users/`, `/api/v1/dashboards/`, `/api/v1/graphs/`,
`/api/v1/admin/logs/` — and `/api/v1/dashboards` is absent from `paths` while `/api/v1/dashboards/` is
present, exactly as filed. No shipped test asserts the `307`.

**Consequence** — Correctly bounded by the input's own hedge, and correctly narrower than its headline:
the observable effect is an anonymous existence oracle over **four** collection paths and a `Location`
header echoing a caller-supplied `Host`. The title's "every declared path" and the Observation's "all
43 declared paths discoverable" are both wrong by roughly a factor of ten; the input's Evidence names
two of the four and omits `/api/v1/users/` and `/api/v1/admin/logs/` (VAL-07-007). The input's own
assessment that the host echo is not an open redirect against the canonical hostname holds and is the
right call.

**Recommendation** — Executable as written; register the affected routes so the declared shape is the
matched shape, or emit a path-relative `Location` after the credential dependency. Scope it to the four
paths above rather than to the surface generally, and align the declared paths with the served ones.

### EXT-007 — No request-body model declares a strictness policy, so an unrecognised field is silently dropped

**Severity** — MEDIUM

**Zone** — Which inbound boundaries validate, which defer validation past acceptance, and which documented exceptions are load-bearing

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM ("a document accepted at a boundary
only a later process can reject"). The enumeration was re-run against the running image rather than
inherited. Every `BaseModel` subclass reachable from `src/mkobi/models/` was collected and its
`model_config["extra"]` read: **seven** models carry one — `TransformationConfig` with `extra="forbid"`
(`transformation_configs.py:133`) and six internal runtime-validation types with
`model_config = {"extra": "allow"}` at `types.py:47,247,260,279,292,305`, exactly the six lines the
input names. All 21 named request-body models resolve and **all 21 report `extra` unset**, so all 21
run on Pydantic v2's `extra="ignore"`: an unrecognised field is ignored, the request proceeds, and the
write commits with its default. The two deferred boundaries resolve as filed:
`data.py:54` takes `filters: str | None = Query(default=None, ...)` and `data.py:109` does
`parsed_filters = json.loads(filters)` outside the model layer; `GraphConfigDict` is
`class GraphConfigDict(TypedDict, total=False)` at `types.py:138`, typed into `GraphBase.config`
(`models/graph.py:15`) and `GraphUpdate.config` (`:45`).

**Evidence** — Live enumeration inside the application image:

```
BASE_MODEL_CLASSES 76
KEYWORD_FORM_EXTRA 7  (1 forbid + 6 allow, at the six types.py lines named)
RESOLVED 21 of 21   -> every one: extra='<unset>'
GraphConfigDict_total False
ClientErrorPayload_error_type dict[str, typing.Any]
```

The count differs from the input's "64 `BaseModel` subclasses" — 76 classes are *reachable* by import
from the package, which includes re-exported definitions; the input's figure is a file-local count. The
load-bearing count, 0 of 21, is identical. The search inventory is substantively right: across 43
`.md` files under `docs/` (excluding the `docs/STRUCT.md` build artefact) there is **no** model-strictness
convention documented, and no `extra` policy is described anywhere; the `forbid` matches are pandas,
raw-SQL and HTTP-403 text, and the `strict` matches are `SameSite=Strict`,
`strict-origin-when-cross-origin` and "strict layered design" (VAL-07-010).

The CRITICAL-band test on the strongest candidate in this finding was run explicitly, because an
unvalidated document reaching a query is the one shape that could be CRITICAL. It fails on a named
ground: `aggregated_data_repo.py:160-162` builds `query.where(AggregatedData.dims[key].astext ==
str(value))` as SQLAlchemy expressions. There is no string interpolation, so a crafted `filters`
document can add predicates on `dims` keys and nothing else; no credential is exposed and no
capability is reachable without a gate. `1.0.8` appears nowhere in `docs/` or `frontend/src/` except
the `docs/STRUCT.md` build artefact, as EXT-010 also records.

**Consequence** — Unchanged: every write surface accepts a malformed body with a success response, and
the failure surfaces later by inspection with nothing correlating it to the request that caused it.
`data.py:109` and `graph.py:15` are worse than the rest: the caller gets an empty result set or a later
error rather than a `422`.

**Recommendation** — Executable and correctly scoped as the smallest change. Adopt the strict base on
the 21 request bodies, model the `filters` document, and give `GraphBase.config` a real `BaseModel`.
One correction of emphasis: the input says `forbid` is "likely correct" on the six `{"extra": "allow"}`
types because they are internal. That is an inference about intent, not a fact about the boundary, and
the input's own dead-code discipline argues against acting on it — establish whether each of the six is
genuinely open before changing it, exactly as the input does for the libraries in EXT-009. Naming the
21 models is correct; do not carry the six along on an inference.

### EXT-008 — The credential write is ordered before the commit that records it, with no compensation

**Severity** — MEDIUM

**Zone** — Isolation of failure inside a batch, and the order of a durable record against the effect it describes

**Observation** — Disposition: **confirmed**; the adjacency to phase 05 DP-001 is **upheld**, and the
input's own ordering recommendation **conflicts** with phase 04's (VAL-07-005). The interleaving was
re-read line by line and is exact: `admin.py:307` `create_user` (uncommitted), `:315` the
`force_password_change` update, `:320` `retrieval_token = str(uuid4())`, `:321`
`await temp_password_store.store(...)` — durable in Redis immediately — `:324` `update_status(APPROVED)`,
`:330` the single `await db.commit()`, `:339-345` `except Exception: await db.rollback()` returning
500 `INTERNAL_ERROR`. The handler compensates for the database only, and the token that reaches the
surviving key is returned solely on the success path, so nobody is ever told which key was orphaned. The
service-layer twin is `auth_service.py:581-598`: `store` at `:583`, the row update at `:585-589`,
`db.commit()` at `:590`, the handle returned at `:595-598`. The read side is atomic by contrast —
`retrieve` wraps `GET`+`DELETE` in `pipeline(transaction=True)` (`temp_password_store.py:63-66`),
which establishes atomic multi-step Redis use as this module's own convention. The TTL bound is
`ttl_seconds: int = 86400` (`temp_password_store.py:20`), 24 h.

**Evidence** — Static ordering proof re-derived from source, interleaved as the input presents it and
matching at every line. The residue claim is bounded correctly: one `temp_pwd:{uuid4}` key per failed
commit, unreachable and unenumerable, expiring within 24 h.

**Consequence** — Unchanged: a failed commit leaves a live credential in Redis describing a user that
was never created, with no record of the token that reaches it. The input's own framing of the residue
as "bounded rather than permanent" is the right one and is not upgraded here.

**Recommendation** — The ordering direction is right and this phase owns it: block 6 of this phase's
contract takes "the order of a durable record against the effect it describes", and DP-001's
Recommendation is a *rule statement*, not a shared edit. The adjacency ruling is upheld on the merits:
the path, the effect and the residue differ (a Redis credential versus a moved file and a queued job),
the two remediations touch disjoint code, and one convention can be recorded once and applied twice —
which is what the input proposes. Two constraints the input does not state. First, the reconciled
design must satisfy AUTH-002 as well: commit first, then store, and if the store fails **after** the
commit, compensate the durable record rather than leaving a committed `APPROVED` request — which is the
mirror image of today's defect and is not the same as either recommendation as written (VAL-07-005).
Second, moving the store after `db.commit()` does not by itself unblock the build:
`tests/core/test_temp_password_store.py:164-181` asserts the fail-open behaviour and must change with
the store's contract (VAL-07-008).

### EXT-009 — The startup self-check refuses to start on four libraries the application never imports

**Severity** — LOW

**Zone** — Whether this boundary exists at all, and every mechanism that would carry one

**Observation** — Disposition: **confirmed**; band upheld at LOW, matching the rubric's LOW clause "a
declared dependency or capability the code does not implement". `REQUIRED_MODULES` at `main.py:10-25`
lists fourteen names including `httpx` (`:14`), `plotly` (`:16`), `rq` (`:23`) and `tenacity` (`:24`);
`requests` is correctly absent. `check_dependencies()` at `main.py:28-47` calls
`__import__(module_name)` at `:37` and raises `SystemExit(1)` at `:47`, so the gate is the only thing
that ever loads the libraries it certifies. `main.py:50` runs the gate at import time, before
`from mkobi.app import create_app` at `:52`.

**Evidence** — Re-run in the running image. `import mkobi.app` alone: `aiofiles`, `fastapi`,
`sqlalchemy`, `pydantic`, `polars`, `redis`, `bcrypt`, `jose`, `alembic`, `asyncpg` all LOADED;
`httpx`, `plotly`, `rq`, `tenacity`, `requests` all `-- never imported --`. Loading through
`mkobi.main` (which runs the gate) reports all fourteen LOADED and `requests` ABSENT. Identical to the
input's artefact, independently produced.

**Consequence** — Unchanged and correctly rated as having no runtime consequence today: every library
is installed, so the process starts. The operational consequence stands — a `uv lock --upgrade` or a
dependency audit that drops any of the four produces a `SystemExit(1)` naming a module the codebase
never touches, and the gate passing is evidence of nothing beyond the presence of a wheel.

**Recommendation** — Executable as written, and the input is right to refuse to jump to deletion: the
routing `rq-worker` row is the same residue phase 01 TOPO-001 already owns from the topology side, and
re-filing it is correctly declined. Establish intent for `httpx` and `tenacity` before touching them,
then either reduce `REQUIRED_MODULES` to the twelve the application imports or document the decision.

### EXT-010 — The schema document advertises a version the package has moved past, and only the human-facing half of it is gated by tier

**Severity** — LOW

**Zone** — The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them

**Observation** — Disposition: **confirmed**, with two evidence anchors corrected (VAL-07-010).
`app.py:218` passes the literal `version="1.0.0"`; `config.py:320` carries `version: str = "1.0.0"` at
`HEAD` and at line `383` in the working tree after the concurrent config edit. `pyproject.toml`
declares `version = "1.0.8"` at **line 7**, not line 4 as the input's evidence block states.
`app.py:220-221` sets `docs_url=None` and `redoc_url=None` when
`config.environment == EnvironmentEnum.PRODUCTION` and leaves `openapi_url` at FastAPI's default, so
in the production tier the two human-facing surfaces are switched off and the machine-readable one is
not. Nothing in the application code closes it; `nginx.conf:34` forwards only `location /api` and
`:43` only the two health paths, so `/openapi.json`, `/docs` and `/redoc` fall through to `location /`
(`:49`) and receive the React bundle.

**Evidence** — Measured against the live dev instance: `openapi title=mkobi version=1.0.0
pathCount=43`, 60 operations, 7 anonymous; anonymous `GET /docs` → `200 text/html`, `GET /redoc` →
`200 text/html`. `1.0.8` appears nowhere in `docs/` or `frontend/src/` outside `docs/STRUCT.md`, and
`API_VERSION` appears nowhere in either — confirmed by search. The production-tier claim is static, as
the input itself records, and that limitation is correctly stated.

**Consequence** — Unchanged: no runtime consequence in the shipped production topology, where an nginx
`location` block rather than the application holds the protection. A `1.0.0` document seven patch
releases behind the package leaves a consumer with no version with which to detect a contract change.

**Recommendation** — Executable as written; set `openapi_url=None` alongside the other two URLs and
source the version from the installed distribution metadata rather than a literal. Neither change has a
shipped test asserting the current behaviour.

## Validation-Level Findings

Separate section, separate scale, separate namespace. The flat `VAL-` prefix is already occupied by the
phase-01 and phase-02 validation reports, and phase 03 through phase 05 each adopted a `VAL-NN-` infix;
this report follows that established precedent with `VAL-07-`, and the deviation from the flat prefix
its output contract specifies is recorded here and in Appendix G.

### VAL-07-001 — EXT-005 is a duplicate of two findings phase 04 already filed, and was filed with no merge ruling

**Severity** — MEDIUM

**Zone** — Cross-Phase Conflict, Ownership and Merge

**Observation** — EXT-005 states the fail-open credential write on the admin approval path and the
conflating read on the retrieval path. AUTH-002 states both halves of the write at the same anchors
(`admin.py:321` store, `:330` commit, `:335` handle) and its Consequence already carries EXT-005's
consequence verbatim, including the `admin.py:299-303` re-approval refusal. AUTH-006 carries the read
side verbatim (`temp_password_store.py:73-75` collapsing three states, `admin.py:418-422` returning one
404). EXT-004 received a merge ruling in its own text; EXT-005, EXT-002 and EXT-008 received none, and
all three overlap filings already in the set.

**Evidence** — Textual comparison of `.ai/audit/04-authentication/findings.md:127-132,161-163`
(AUTH-002) and `:388-397,409-414` (AUTH-006) against `.ai/audit/07-external-boundary/findings.md`
(EXT-005), plus anchor resolution at `admin.py:321,330,332-336,339-345,419-423` and
`temp_password_store.py:30-48,50-75`. No `Merge/adjacency ruling` paragraph exists in EXT-005's block.

**Consequence** — Two teams will schedule the same `admin.py` edit, and the second one to land will
either duplicate the first or silently revert it. The set's owner cannot tell from the phase-07 report
that the defect already has a filing.

**Recommendation** — Record EXT-005 as merged into AUTH-002 (write) and AUTH-006 (read) in the set's
merge register, naming phase 04 as the remediation owner. Do not renumber either phase's identifiers.
Add the `client-errors:` surface to AUTH-001 per EXT-004's disposition.

### VAL-07-002 — EXT-004's recommended `forwarded-allow-ips="*"` is a caller-chosen rate-limit bucket, not a fix

**Severity** — MEDIUM

**Zone** — Whether the Recommendation Can Be Carried Out

**Observation** — EXT-004 recommends passing `--forwarded-allow-ips` covering the compose bridge subnet
**"(or `"*"` if the app is only ever reachable from the compose network)"**. In uvicorn 0.49.0,
`_TrustedHosts.get_trusted_client_address` branches on `if self.always_trust: return
_parse_host_port(x_forwarded_for_hosts[0])`. A wildcard sets `always_trust`, so uvicorn reads the
**left-most** `X-Forwarded-For` entry — the one the caller supplied — because
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for` (`nginx.conf:38`) *appends* the real peer
at the right. The dev tier publishes the app port unbound (`docker-compose.override.yml:104-108`), so a
host-reachable caller can reach `app:8000` directly and choose their own bucket, converting a global
lockout into no lockout at all.

**Evidence** — `inspect.getsource(uvicorn.middleware.proxy_headers._TrustedHosts.get_trusted_client_address)`
from the running image, docstring *"In general this is the first 'untrusted' host in the forwarded for
list"*, with the `always_trust` short-circuit above the reverse walk; `nginx.conf:38`;
`docker-compose.override.yml:104-108` (`"${APP_HOST_PORT:-8010}:8000"`, no host binding). The non-wildcard
path is safe and was confirmed reading the same source: walking `reversed(x_forwarded_for_hosts)` returns
the first host not in the trusted set, which with nginx's append semantics is the real caller.

**Consequence** — Acting on the recommendation as written replaces a denial-of-service vector with a
brute-force bypass on every rate-limited surface, in the tier where it is easiest to exploit. The input's
own Rollout Safety names this risk and then offers the unsafe value anyway, so the hazard survives to
the implementation step.

**Recommendation** — Amend the recommendation to the subnet form only and delete the wildcard
alternative. This is the same defect phase 04 recorded as VAL-04-001, reached through a second door;
if the wildcard is wanted anywhere, gate it on `app:8000` being unreachable from outside the compose
network, verified rather than assumed.

### VAL-07-003 — EXT-002's recommendation names a blocker that does not exist

**Severity** — MEDIUM

**Zone** — Whether the Recommendation Can Be Carried Out

**Observation** — EXT-002 states that `SERVICE_UNAVAILABLE` "does not exist in
`src/mkobi/models/enums.py` and would need adding". It exists at `enums.py:197` inside `ErrorCode`
(`enums.py:188`), is mapped to `HTTP_503_SERVICE_UNAVAILABLE` at `utils/exceptions.py:36`, and carries
the title `"Service unavailable"` at `:187`. Phase 04's AUTH-002 and AUTH-006 both recommend mapping to
it as though it were available.

**Evidence** — Grep of `src/mkobi/models/enums.py:197` and `src/mkobi/utils/exceptions.py:36,187`;
`ErrorCode` has 98 members. No `HTTP_503` or `SERVICE_UNAVAILABLE` entry is missing anywhere.

**Consequence** — A reader following the plan adds a duplicate enum member, which the project's own
`StrEnum` discipline forbids and which would shadow or collide with the existing mapping. The cost is
small but the plan is wrong about its own dependency.

**Recommendation** — Delete the false blocker sentence from EXT-002 and apply the existing
`ErrorCode.SERVICE_UNAVAILABLE` directly. Nothing else in the recommendation changes.

### VAL-07-004 — EXT-002's second element duplicates AUTH-008 at the same sites and the same fix

**Severity** — MEDIUM

**Zone** — Cross-Phase Conflict, Ownership and Merge

**Observation** — EXT-002 states that the Redis error on the revocation read "is caught only by the
catch-all `except Exception` at `deps.py:570-576` and converted into
`AppException(AUTHENTICATION_FAILED, "Authentication failed")`, byte-for-byte the response a caller
receives for a malformed, expired or forged token", and recommends catching `redis.exceptions.RedisError`
around the two revocation calls and mapping it to 503. AUTH-008 states the same thing at the same sites
(`security.py:502-504`, `:552-554`, `deps.py:570-576`), recommends the same 503 mapping, and notes the
same SPA sign-out consequence. The two bands differ legitimately, because each graded its own subject:
phase 04 graded a documentation claim LOW ("the documentation says the revocation check degrades
gracefully at WARNING"), phase 07 graded a blast radius HIGH ("one dependency's failure taking down a
surface rather than a feature").

**Evidence** — `.ai/audit/04-authentication/findings.md:492-504,513-530` against the EXT-002 block;
anchors `deps.py:570-576` and `security.py:502-504,552-554` resolve identically from both reports.

**Consequence** — Two teams editing `deps.py:504-532`. If phase 07's copy of the fix is built without
phase 04's, `docs/08-security/security-overview.md:234` keeps asserting a WARNING-level graceful
degradation that the new 503 also does not satisfy.

**Recommendation** — Merge the refusal-class change into AUTH-008, whose remediation already carries it,
and keep in phase 07 only what AUTH-008 does not establish: the 53-operation blast radius, the
undeclared `redis-py` bound, and the 58-59 s per-request cost. AUTH-008's `security-overview.md:234`
correction must ship with the code change.

### VAL-07-005 — EXT-005 and EXT-008 prescribe opposite orderings for the same two lines, and AUTH-002 a third

**Severity** — MEDIUM

**Zone** — Cross-Phase Conflict, Ownership and Merge

**Observation** — Three reports prescribe three different orders for the store write relative to
`db.commit()` on `admin.py:321` / `:330`. EXT-008: move the store **after** `db.commit()`. EXT-005:
abort the approval with a 503 **before** `db.commit()`. AUTH-002: keep the store **after** the
`user_repo.update` but **before** `db.commit()`. Two of the three agree that the store precedes the
commit, which is precisely the ordering EXT-008 exists to remove.

**Evidence** — `.ai/audit/07-external-boundary/findings.md` EXT-008 Recommendation ("Move the
`temp_password_store.store` call to after `db.commit()` at `admin.py:330`") and EXT-005 Recommendation
("abort the approval with a 503 before `db.commit()`"), against
`.ai/audit/04-authentication/findings.md:165-172` ("have both callers do the store write *after* the
`user_repo.update` but *before* `db.commit()`"). All three anchor the same pair.

**Consequence** — Whichever lands second is reverted or duplicated, and the durable-record/effect
ordering question this phase owns is decided by accident of scheduling rather than by the phase that
owns it.

**Recommendation** — Phase 07 owns the ordering question by its own block 6, so adjudicate one shape and
record it: commit the durable record first, then publish the credential, and on a publish failure
compensate the committed record (mark the request failed and remove the account) rather than leaving an
`APPROVED` request with no credential. That satisfies EXT-008's ordering, EXT-005's fail-closed
intent and AUTH-002's "no durable record for an absent credential", and it is strictly better than the
fail-open the code has today. Phase 04's `register_user` commit-hoisting note still applies.

### VAL-07-006 — EXT-002's retry arithmetic is wrong: the library retries ten times, not three

**Severity** — MEDIUM

**Zone** — The Claim Re-Derived from the Executing Path (asserted cause)

**Observation** — EXT-002 states the 58 s comes from `redis-py` 8.0.0's "automatic `Retry` with jittered
backoff — **three retries of a 5 s timeout**, which is where ~58 s comes from". Three retries of five
seconds is 20 s. The installed default is `Retry(ExponentialWithJitterBackoff(base=0.01, cap=1),
retries=10)`, whose supported errors include `TimeoutError`, so the cost is eleven attempts of a 5 s
read timeout plus jittered backoff — which is what the measured 58.792 s and 59.396 s are. The finding's
*conclusion* — that the per-request cost is inherited from an undeclared library default no code in this
project sets — is confirmed and survives intact; only the mechanism a reader would verify against does
not.

**Evidence** — Read from the running image: `RETRY_RETRIES 10`,
`RETRY_SUPPORTED ['TimeoutError','ConnectionError']`, `BACKOFF_VARS {'_cap': 1, '_base': 0.01}`,
`KW socket_timeout = 5`, `KW socket_connect_timeout = 5`. The server-side traceback shows the retry loop
at `redis/asyncio/connection.py:350 in connect → retry.call_with_retry → retry.py:81 raise error`,
confirming the exhausted-retry path rather than a single timeout. Measured cost 59.396 s and 58.792 s.

**Consequence** — A reader who checks the arithmetic finds 20 s against a measured 59 s and concludes the
evidence is fabricated, then discounts the finding that is in fact correct. That is a wrong rejection
caused by the report, which is worse than no finding.

**Recommendation** — Replace the sentence with the measured configuration and the arithmetic it implies
(eleven 5-second attempts plus jittered backoff). Do not restate a library default the project does not
pin as though it were a constant.

### VAL-07-007 — EXT-006 overstates the enumeration surface by roughly a factor of ten

**Severity** — MEDIUM

**Zone** — The Claim Re-Derived from the Executing Path

**Observation** — EXT-006's title says the credential check runs after the slash redirect "so **every**
declared path answers an anonymous caller"; the Observation says the pair "makes **all 43** declared
paths discoverable by an anonymous caller"; the Consequence says an anonymous caller "can enumerate the
declared API surface from the 307/404 pair". The live document declares **four** paths ending in `/`:
`/api/v1/users/`, `/api/v1/dashboards/`, `/api/v1/graphs/`, `/api/v1/admin/logs/`. The other 39 declared
paths answer `401` or `404` and reveal nothing. The input's own Evidence names two of the four and omits
`/api/v1/users/` and `/api/v1/admin/logs/`.

**Evidence** — Enumerated from the live `/openapi.json`: 43 declared paths, 60 operations, 53 with
`security` and 7 anonymous; 4 paths carry a trailing slash. Live probes: `/api/v1/dashboards` → 307,
`/api/v1/graphs` → 307, `/api/v1/layouts` → 401, `/nonexistent-spa-route` → 404.

**Consequence** — The finding's real, measured effect is an existence oracle over four collection paths
plus a caller-echoed `Location` header. As written it reads as full-surface enumeration, which is a
different claim with a different remediation appetite and a different owner conversation.

**Recommendation** — Restate the title, Observation and Consequence around four paths, add the two the
Evidence omitted, and scope the Recommendation to those four. Keep the band: a bounded disclosure gap
is MEDIUM either way.

### VAL-07-008 — EXT-005's and EXT-008's recommendations are blocked by a shipped test both reports say does not exist

**Severity** — MEDIUM

**Zone** — Whether the Recommendation Can Be Carried Out

**Observation** — EXT-005 states "No shipped test asserts the current 200-with-dead-token behaviour" and
EXT-008 states "No shipped test asserts the current ordering". Both are true as written and both miss the
blocker: `tests/core/test_temp_password_store.py:164-181` (`test_store_fail_open_on_error`) asserts the
store must **not** raise and that the error is logged exactly once — "Should not raise - graceful
degradation" — and `:184-190` (`test_retrieve_fail_graceful_on_error`) asserts `result is None` on
Redis failure. Both recommendations change that contract, so both cannot land until those tests are
replaced. Phase 04's AUTH-002 names the first as a remediation blocker; phase 07 names neither.

**Evidence** — `tests/core/test_temp_password_store.py:164-181,184-190` read in full: the docstrings,
the `FailingSetRedis` stub raising on `set`, the `patch("mkobi.core.temp_password_store.logger")`
block and the two assertions. The tests are green today, so the behaviour is encoded, not merely
undocumented.

**Consequence** — The store's failure contract is decided by two shipped tests, and neither phase-07
recommendation mentions them. A team picking up EXT-005 alone will discover the blocker at
implementation time and may conclude the finding is wrong.

**Recommendation** — Name both tests as remediation blockers in EXT-005's and EXT-008's
Recommendations, and sequence the store-contract change once (VAL-07-005) rather than twice.

### VAL-07-009 — Nine anchors cited by three findings moved under this validation and are now committed

**Severity** — LOW

**Zone** — Finding-ID Namespace Integrity / anchor re-resolution

**Observation** — `src/mkobi/app.py` was edited **during** this validation, removing the
`"*" in config.cors_origins` guard from `create_app()` (9 lines), and `src/mkobi/config.py` was
rewritten by the concurrent remediation programme. Both landed as commits `5a2cfb6` and `b23a9cb`, so
the drift is now committed rather than a transient working-tree state. Nine anchors cited by EXT-001,
EXT-006, EXT-010 and EXT-004 no longer resolve at current `HEAD` (`b23a9cb`):

| Anchor as filed | Resolves at `c3c0a61` / `5a2cfb6` | Resolves at `b23a9cb` |
|---|---|---|
| `app.py:257-276` — `/health` handler | yes | `:248-267` |
| `app.py:278-316` — `/health/detailed` handler | yes | `:269-307` |
| `app.py:300-306` — the pattern to copy | yes | `:291-297` |
| `app.py:218` — `version="1.0.0"` | yes | `:209` |
| `app.py:220-221` — `docs_url` / `redoc_url` | yes | `:211-212` |
| `app.py:245-255` — router registration | yes | `:236-246` |
| `config.py:320` — `version: str = "1.0.0"` | yes | `:383` |
| `config.py:461` — `rate_limiter_fail_closed` | yes | `:524` |
| `client_errors.py:49-50` — the key | yes | `:49-50` (unchanged; listed for completeness) |

**Evidence** — `git show --stat` for `5a2cfb6` (`config.py`, `db/starter.py`, `tests/test_config.py`,
`tests/test_starter.py`) and `b23a9cb` (`app.py` −9 lines, `config.py` +118/−, `tests/test_config.py`
+91); anchor resolution run against `HEAD` at each revision and compared. `git status --porcelain --
src/mkobi/app.py` is now empty — the working tree matches `b23a9cb`.

**Consequence** — No claim changes. `app.py` still contains **no** reference to Redis at all, the
version and tier-gate literals are unchanged, and `rate_limiter_fail_closed` still defaults to
fail-closed. What changes is usability: a remediation ticket quoting the input's `app.py` line numbers
would land on the wrong lines, and the second anchor drift touches a file (`config.py`) that EXT-002's
and EXT-010's evidence both cite.

**Recommendation** — Quote the current `HEAD` numbers from the table above in any ticket derived from
this report, and re-resolve every `config.py` and `app.py` anchor immediately before editing, since
both are under active concurrent change. Phase-07's own evidence is sound as filed; the drift is in
the repository, not the report.

### VAL-07-010 — Four evidence anchors and one search characterisation are wrong

**Severity** — LOW

**Zone** — The Claim Re-Derived from the Executing Path

**Observation** — Four small inaccuracies, none load-bearing. (a) EXT-010's evidence block cites
`pyproject.toml:4` for `version = "1.0.8"`; it is at line 7. (b) EXT-006 lists four routers carrying
`redirect_slashes=False` ("auth, client-errors, upload and combined dashboard"); twelve do. (c)
EXT-007's search characterisation says "the only `strict` matches are `SameSite=Strict` cookie
attributes", while `docs/` also carries "strict layered design" three times,
`Referrer-Policy: strict-origin-when-cross-origin` twice and a `strict_redis` fixture in
`docs/09-testing/testing.md:93`. (d) EXT-004's merge justification says AUTH-001's scope "excluded that
surface", which is contradicted by AUTH-001's own Roadmap Step 6.

**Evidence** — Line resolution for each: `pyproject.toml:7`; `redirect_slashes=False` at
`auth.py:68`, `admin.py:31`, `client_errors.py:21`, `dashboards_crud.py:45`, `dashboards.py:20`,
`data.py:36`, `graphs.py:42`, `upload.py:48`, `layouts.py:40`, `processing_logs.py:28`,
`processing_configs.py:33`, `users.py:37`; 43 `.md` files searched for `forbid` and `strict`;
`.ai/audit/04-authentication/findings.md:623-627`.

**Consequence** — Each would send a reader to a line that does not hold the claim, or would make the
search inventory look sloppier than the finding. (d) is the one that matters, because it is the stated
basis for keeping a residual that AUTH-001 already owns.

**Recommendation** — Correct (a)-(c) in place. Treat (d) as superseded by VAL-07-001: the residual
doc-drift at `auth-api.md:113` belongs to AUTH-001's documentation step, not to phase 07.

### VAL-07-011 — The input's restoration claim omits five durable rows its own evidence created

**Severity** — LOW

**Zone** — Does the Input Rest on its Own Declared Blocks and Evidence Fields

**Observation** — Appendix E narrates restoration in detail — Redis ACL restored and verified, probe
container removed, login and `/auth/me` returning 200, `/health` healthy — and closes with "all probe
artefacts created by this phase were removed, and the working tree shows the four baseline modifications
and no trace of this phase's work". Read strictly that is a statement about the git working tree, and it
is true. It is not a statement about the database, and the database holds five rows this phase created
and disclosed nowhere.

**Evidence** — Live `bidb`: `users` row `03c82044-ca95-4ba4-ba53-e053ce8ae150` /
`wo.probe.1395195825@example.com`, `is_active = true`, `force_password_change = true`, created
2026-09-30 13:03:54 — the exact `user_id` quoted in EXT-005's evidence; `registration_requests` row
`bce038fd-1101-459d-ad55-556539d71edf`, status `approved` — the exact request id quoted there; plus
three `pending` requests `approve.probe.2144024641@…`, `probe.user4.4.4.4@…`,
`probe.user5.5.5.5@…`, the last two corresponding to the `X-Forwarded-For` values in EXT-004's
reproduction.

**Consequence** — The first pair is a live instance of the very defect EXT-005 describes: an account
that exists, is active, is flagged `force_password_change`, and whose password is held by nobody, with
its registration request already `approved` and therefore not re-approvable. It is the best possible
demonstration of the finding and it is unreachable from the report.

**Recommendation** — Delete the two probe rows and the three pending requests before this phase's
artefacts are treated as cleaned up, or record them in Appendix E as knowingly retained. A validator
reproducing EXT-005 should scope its writes to a rollback it then performs.

## Disposition Tally

Audited findings, against the fixed vocabulary:

| Finding | Disposition | Band carried | Band the rubric assigns |
|---|---|---|---|
| EXT-001 | confirmed (co-owned with phase 10) | HIGH | HIGH — a guard that permits where meant to bound, direction a hard-coded branch |
| EXT-002 | confirmed; asserted cause refuted (VAL-07-006); one element merged (VAL-07-004) | HIGH | HIGH — one dependency's failure taking down a surface rather than a feature |
| EXT-003 | confirmed | HIGH | HIGH — a body written to the log verbatim from anyone, no bound on the volume |
| EXT-004 | **merged** into AUTH-001 — ruling upheld, justification refuted | HIGH | HIGH — a bound correct per process and unbounded once the topology multiplies it |
| EXT-005 | **merged** into AUTH-002 + AUTH-006 — ruling absent as filed (VAL-07-001) | MEDIUM | MEDIUM — a fallback that returns a value where the caller needed a status |
| EXT-006 | confirmed; enumeration overstated (VAL-07-007) | MEDIUM | MEDIUM — a bounded resource or operability gap |
| EXT-007 | confirmed | MEDIUM | MEDIUM — a document accepted at a boundary only a later process can reject |
| EXT-008 | confirmed; adjacency to DP-001 upheld; recommendation conflict (VAL-07-005) | MEDIUM | MEDIUM — batch ordering without compensation |
| EXT-009 | confirmed | LOW | LOW — a declared dependency or capability the code does not implement |
| EXT-010 | confirmed; two anchors corrected (VAL-07-010) | LOW | LOW — documentation and observability drift |

No band was re-graded: every band carried is the band phase 07's own rubric assigns to the subject the
finding grades. One rubric tension is recorded rather than resolved silently — phase 07's MEDIUM clause
*"a probe reporting the same words for different underlying states"* describes EXT-001 almost verbatim,
while its HIGH clause *"a guard that permits where it was meant to bound, with the direction a hard-coded
branch rather than a decision"* describes the same finding's deployed consequence. HIGH was upheld on the
second reading; a later run may read the first and grade MEDIUM, and that disagreement should be recorded
in the set's rubric rather than settled per-finding.

Tally check: confirmed 8 (EXT-001, EXT-002, EXT-003, EXT-006, EXT-007, EXT-008, EXT-009, EXT-010),
merged 2 (EXT-004 into AUTH-001, EXT-005 into AUTH-002 + AUTH-006), re-graded 0, re-typed 0,
not substantiated 0, unsettled 0 — ten dispositions for ten findings. Validation-level findings, counted
separately and on their own scale: MEDIUM 8 (VAL-07-001 … -008), LOW 3 (VAL-07-009, -010, -011). No
identifier was renumbered, and no audited identifier was reused in the validation namespace.

## Distribution

The ten findings fall on three surfaces, and one dependency carries four of them. The boundary layer
concentrates: `app.py` (EXT-001, EXT-010), `api/deps.py` with `core/security.py` (EXT-002),
`api/routes/admin.py` (EXT-005, EXT-008), `api/routes/client_errors.py` (EXT-003), `api/routes/auth.py`
(EXT-004), the routing layer (EXT-006), `models/` (EXT-007), `main.py` (EXT-009).

- **Redis as a critical path with undeclared failure semantics** — EXT-001, EXT-002, EXT-005, and
  EXT-003's shared key. Four findings, one component, one missing declaration. This cluster carries the
  most weight and is the only one where remediation is split across phases.
- **The health and version surface in `app.py`** — EXT-001, EXT-010.
- **The admin approval sequence in `admin.py`** — EXT-005, EXT-008, with a third prescription from
  phase 04 and two shipped tests binding the contract.
- **Inbound identity and volume model** — EXT-003, EXT-004, EXT-006.
- **Validation-strategy defects in the report itself** — VAL-07-001 … -008: five of eight are about the
  *recommendation* layer rather than the claim layer, which is the same shape phase 04's validator found
  and it recurs.

Nothing in this phase falls in the data pipeline, the database layer or the frontend. Two findings
(EXT-004, EXT-005) are no longer phase 07's to remediate.

## Cross-Finding Analysis

Two causes account for eight of the ten audited findings, and this validation confirms both from the
executing path rather than from the input's narrative.

**Redis is on critical paths whose reported outcome does not depend on it.** EXT-001, EXT-002 and
EXT-005 are one omission seen from three directions: the revocation read is unguarded, the probe does
not cover it, and the credential write fails open while the endpoint reports success. The common defect
is not any single call site — it is that no call site on this dependency states what happens when it
fails, and the application's failure reporting was written for the database and never extended. This
validation's independent measurement sharpens the shared claim: the cost is not 58 s by accident of
load but 11 attempts of a library default nobody in this project set (VAL-07-006), so the defect is not
only semantic but *undeclared in two independent places* — the call sites and the client construction.

**The boundary's identity and volume model was derived for a directly-exposed process and never
re-derived for the shipped topology.** EXT-004 because the caller collapses to the proxy's address,
EXT-003 because the volume bound that depends on that address is therefore a shared pool, and EXT-006
because the routing layer answers before the layer that would have identified the caller. This
validation confirms the collapse is a property of uvicorn's trust decision and not of any proxy
configuration — the header is never consulted for a non-loopback peer — which means the collapse is
invisible to any test that does not inject the header, and explains why `tests/test_rate_limiting.py`
cannot detect it.

The consequence that follows from confirming both causes is the one the input states and this
validation can now make precise: the single `forwarded-allow-ips` value is a prerequisite for reasoning
correctly about EXT-003, EXT-004 and EXT-006, **and it is now a prerequisite for acting on EXT-004's own
recommendation**, because the wildcard form of that fix is itself a bypass (VAL-07-002). A roadmap that
executes the input's Step 2 verbatim does not close EXT-004; it trades it for a worse defect.

EXT-007, EXT-009 and EXT-010 share no cause with any other finding or with each other.

## Roadmap

The input's eight-step sequence is **not executable as written**: Step 2's fix, Step 1's enum premise
and Steps 1/4's test assumptions each fail. This sequence reorders by cause and by owner.

1. **Correct the plan before executing any of it.** Apply VAL-07-002 (drop the wildcard alternative),
   VAL-07-003 (drop the false enum premise), VAL-07-006 (correct the retry arithmetic),
   VAL-07-007 (four paths, not 43), VAL-07-008 (name both store tests), VAL-07-010 (four anchors).
   *Before starting:* nothing. *Done when:* no recommendation in the set names a blocker that does not
   exist or an unsafe value.

2. **Decide and record the ownership splits.** Register EXT-004 as merged into AUTH-001 (phase 04 adds
   the `client-errors:` surface and owns `auth-api.md:113`); EXT-005 as merged into AUTH-002 + AUTH-006;
   EXT-002's refusal-class element as merged into AUTH-008. Name phase 10 co-owner of EXT-001's
   probe-contract half. *Before starting:* nothing. Closes VAL-07-001, VAL-07-004 and the ownership half
   of VAL-07-002's context. *Done when:* each merged finding names its owning phase and no two
   schedules touch the same file for the same reason.

3. **Settle the store contract once, then apply it.** Decide fail-closed on the credential write;
   replace `tests/core/test_temp_password_store.py:164-181` and `:184-190`; make `store` report failure;
   and adopt the reconciled ordering from VAL-07-005 — commit the record, publish the credential,
   compensate the record if publication fails. Applies to `admin.py:321` and `auth_service.py:583`
   together. *Before starting:* step 2, so phase 04 does not ship its own ordering first.
   Closes EXT-005 (via AUTH-002/AUTH-006), EXT-008, VAL-07-005, VAL-07-008.

4. **Declare the Redis failure semantics.** Explicit `socket_timeout`, `socket_connect_timeout` and
   `retry=Retry(NoBackoff(), 0)` in `core/redis_client.py:46-52`; map the two revocation reads'
   transport error to the existing `ErrorCode.SERVICE_UNAVAILABLE`. *Before starting:* step 2, because
   phase 04's AUTH-008 owns the second half. Closes EXT-002's distinct residue, EXT-001's cost half.

5. **Restore per-caller identity at the edge — subnet form only.** `--forwarded-allow-ips` covering the
   compose bridge CIDR in `docker/Dockerfile:179` and `docker-compose.override.yml:109`. Never `*`.
   *Before starting:* step 1. Closes EXT-004 via AUTH-001 and unblocks correct reasoning on EXT-003
   and EXT-006. *Done when:* N distinct `X-Forwarded-For` values produce N distinct keys.

6. **Make the probe answer the question its consumers ask.** Redis `PING` component on `/health` and
   `/health/detailed`, 503 on failure, `health-api.md:164-169,179-181` updated. *Before starting:*
   step 4, so the probe reports a bounded failure. Closes EXT-001. Co-owned with phase 10.

7. **Bound what an anonymous caller can write.** Truncate and constrain the `client-errors` fields;
   narrow `ClientErrorPayload.error`; `Content-Length` pre-check. *Before starting:* step 5.
   Closes EXT-003.

8. **Align served paths with declared paths**, scoped to the four collection routes. Closes EXT-006.
   Independent; parallel with 4-7.

9. **Make the validation convention executable.** Strict request-model base on the 21 request bodies;
   model the `filters` document; give `GraphBase.config` a real model. Closes EXT-007. Schedule with
   the frontend owner; independent of everything above.

10. **Make the tier decision in one place** (EXT-010) and **reconcile the startup gate** (EXT-009).
    Trivial; group each with any other edit to the same file.

## Rollout Safety

Step 5 is the widest-blast-radius change in the set and must be verified first after deploy. Setting
`--forwarded-allow-ips` changes the key under every address-keyed bound at once, so existing counters
are abandoned rather than migrated — harmless for short-TTL integers — but the *effective* budget per
caller rises from a shared 3 or 5 to a per-caller 3 or 5, which is the intent. The risk is the opposite
and it is now the load-bearing warning of this report: if the allow-list is set too broadly, a
caller-reachable `app:8000` becomes a caller-chosen bucket (VAL-07-002), converting a global-lockout
defect into a brute-force bypass. Verify with the EXT-004 reproduction immediately after deploy, and
scope to the CIDR rather than `*`. This closes AUTH-001 and must not ship separately from it.

Steps 3, 4 and 6 change status codes callers branch on. Today a Redis outage yields
`401 AUTHENTICATION_FAILED`; after steps 4 and 6 it yields `503` from `/auth/me` and non-200 from
`/health`. Any client that treats 401 as "refresh the token" will stop doing so during an outage,
which is correct, since the refresh endpoint depends on the same Redis — but it is a visible behaviour
change and belongs in the release note. Step 3 changes `POST /admin/registration-requests/{id}/approve`
from `200` with a handle to `503` when the store refuses, and moves the durable record to commit-first;
an administrator's workflow that retries the approval will now see `DUPLICATE_RESOURCE` in the window
between commit and the compensated delete, so the compensating path must be implemented in the same
change rather than later.

Step 9 is the one to sequence with the frontend owner: converting `extra="ignore"` to `extra="forbid"`
on 21 request bodies turns silent field drops into `422`s, which is correct and will look like a
regression if it lands alone. Revert is a revert of the base class in every case; no stored data
changes in any step.

## Appendices

### Appendix A — Block 1: claim re-derivation ledger

Every location reference was resolved mechanically before the claim was tested. Anchors are recorded as
they resolve at `HEAD` (`c3c0a61`, `5a2cfb6`) unless a drift is named.

| Finding | Executing path | Anchor resolved? | Claim tested on its own terms | Asserted cause tested separately |
|---|---|---|---|---|
| EXT-001 | `app.py:257-276`, `:278-316`; `deps.py:504-532`; `security.py:492-504,542-554` | yes, all (app.py lines now `:248-267`, `:269-307` — VAL-07-009) | reproduced: 200 healthy while 401 at 59.396 s | probe blind to Redis — yes, zero `redis` matches in `app.py` |
| EXT-002 | `deps.py:475,506,526,570-576`; `redis_client.py:46-52` | yes | reproduced; 53-operation blast radius re-derived | **refuted** — `retries=10`, not 3 (VAL-07-006) |
| EXT-003 | `client_errors.py:42,49-50,62-68`; `models/data.py:504-528` | yes | reproduced: 5,000,160 B → 5,000,321-char record | no field cap — yes, no `max_length`, no `extra` |
| EXT-004 | `Dockerfile:179`; `override.yml:109`; `auth.py:83-90,309-315,566-568`; `client_errors.py:49`; `upload.py:144-148` | yes | reproduced: 5 distinct XFF → 1 key | header discarded — yes, `forwarded_allow_ips='127.0.0.1'` in the image |
| EXT-005 | `admin.py:307-345,419-423`; `temp_password_store.py:20,30-48,50-75` | yes | static proof unconditional; runtime not re-run (limit) | `store` is `-> None`, so the outcome is unobservable, not merely ignored |
| EXT-006 | `app.py:245-255`; 12 routers with `redirect_slashes=False` | yes | reproduced: 307 for `/dashboards` and `/graphs`, 401 for `/layouts` | router order precedes `Depends` — yes |
| EXT-007 | `data.py:54,109`; `models/graph.py:15,45`; `types.py:138`; `transformation_configs.py:133` | yes | re-enumerated in the image: 0 of 21 | the one `extra="forbid"` and the six `allow` — both confirmed |
| EXT-008 | `admin.py:307-345`; `auth_service.py:581-598` | yes | static interleaving re-read line by line | read side atomic (`transaction=True`) — yes, contrasted |
| EXT-009 | `main.py:10-25,28-47,50,52` | yes | reproduced: 4 libraries never imported by the app | gate is the sole loader — yes, `main.py:37` |
| EXT-010 | `app.py:218,220-221`; `config.py:320`; `pyproject.toml:7` | yes, except `pyproject.toml:4`; `app.py`/`config.py` lines now `b23a9cb` (VAL-07-009) | reproduced: version 1.0.0, 43 paths, 60 ops | `openapi_url` ungated — yes, absent from the constructor |

### Appendix B — Block 2: the vacuous-control angle, applied to this input

Three questions per control — does it exist, what scope does it declare, what did it actually examine —
with "did it run at all" kept separate from "did it decide anything".

| Control | Exists | Declared scope | Items actually examined | Verdict reaches a decision? |
|---|---|---|---|---|
| `/health` | yes, `app.py:257-276` | DB reachability only | 1 dependency of 2 on the request path | no — runs green over an unexamined dependency, and the outage probe shows it cannot distinguish the two states |
| `/health/detailed` | yes, `app.py:278-316` | DB + static bundle | same | no — same words for two states, and returns `dict`, so it cannot express a non-200 |
| Docker `HEALTHCHECK` | yes, `Dockerfile:176-177`, `compose.yml:142-147` | container liveness | 1 of the 2 preconditions | no — consumes the blind answer; **disabled in dev** by `override.yml:111-112`, so it decides nothing in the tier the evidence was gathered in |
| `main.py::check_dependencies` | yes, `main.py:28-47` | 14 modules importable | 4 of the 14 are never imported by the application | no — green over zero reached call sites; the gate's own `__import__` is the only loader, so it certifies its own absence of use |
| Rate-limiter failure direction | yes, `security.py:111-151` | declared value, default fail-closed | all 5 surfaces | yes — `AsyncRateLimiter` wired with `fail_closed=config.rate_limiter_fail_closed` at `auth.py:84-86,310-312,562-564`, `client_errors.py:45-47`, `upload.py:144-146` (plus a service-level limiter at `auth_service.py:66-69`); `config.py:461` at `HEAD` |
| The sync `RateLimiter` | yes, `security.py:58-103` | class default `fail_closed=False` | 0 production call sites | no — configured, reachable by import, reached by nothing |

### Appendix C — Block 3: each band against phase 07's own rubric

The rubric of record is `07-audit-external-boundary.md:126-133`. Grading is by effect and blast radius
on present state, not by mechanism name. The mapping is in the Disposition Tally. Three points of
tension are recorded rather than resolved:

- **EXT-001** sits between the HIGH clause *"a guard that permits where it was meant to bound, with the
  direction a hard-coded branch rather than a decision"* and the MEDIUM clause *"a probe reporting the
  same words for different underlying states"*, the latter being almost a verbatim description of the
  title. HIGH upheld on the first; see the Tally note.
- **EXT-005** is graded MEDIUM on the "a fallback that returns a value where the caller needed a
  status" clause, which fits precisely. Its merge into a phase-04 HIGH does not change the band, because
  each phase's band reflects its own rubric and its own subject.
- **EXT-006** is graded MEDIUM on the "bounded resource or operability gap" preamble rather than on any
  enumerated example — no enumerated clause covers an anonymous `307`. Its band survives the
  overstatement correction because the corrected effect is still a bounded disclosure gap, not a
  LOW-band documentation drift.

### Appendix D — Block 4: which side moves

| Finding | Load-bearing artefact | Specification-corpus answer | Disposition |
|---|---|---|---|
| EXT-001 | the probe's answer, consumed by `Dockerfile:176-177`, `compose.yml:142-147` and `health-api.md:179-181` | the corpus *expects* a probe the deployment trusts; the document is what the operator acts on | code moves; the doc moves with it |
| EXT-002 | the code path | `security-overview.md:234` asserts graceful WARNING degradation — the corpus **misstates** the code (phase 04's AUTH-008) | code moves, plus AUTH-008's doc correction |
| EXT-003 | the code | no corpus claim about log field caps | code moves |
| EXT-004 | one configuration value | `auth-api.md:46,96,113` asserts per-IP scope the deployment cannot deliver | code moves, doc follows (AUTH-001) |
| EXT-005 | the code | no corpus claim; `admin-api.md` describes the handshake | code moves (AUTH-002/AUTH-006) |
| EXT-006 | the served path | the description declares the slash form; the router redirects it | both move — declare and serve the same shape |
| EXT-007 | the model layer | no corpus convention exists; the one exception is undocumented | code moves, and a convention is written |
| EXT-008 | the commit boundary | `data-flow.md:113` states the correct rule for the *pipeline* path and is honoured nowhere on the admin path | code moves |
| EXT-009 | the gate's claim | `REQUIRED_MODULES` has no docstring and no corpus entry | **not re-typed to dead code** — intent is unestablished, exactly as the input states; re-typing requires the corpus question first |
| EXT-010 | the document and the constructor | `pyproject.toml:7` is the only current version signal | both move; one source of truth |

EXT-009 is the one place the block could have re-typed a finding and did not, and the input's reasoning
is the correct one: a library no code path reaches but that a startup gate certifies is a *mismatched
gate*, not dead code, because the deployment depends on it starting.

### Appendix E — Block 5: whether each recommendation can be carried out

| Finding | Target resolves? | Removes the defect? | Depends on | What else it breaks | Verdict |
|---|---|---|---|---|---|
| EXT-001 | yes | yes | phase 10 co-signature | none; `test_health.py` asserts component *presence*, not an exact set | **usable** |
| EXT-002 | yes | partly — part 2 is AUTH-008's | AUTH-008 owns the edit; enum already exists | 401 → 503 for clients branching on 401 | **usable after VAL-07-003** |
| EXT-003 | yes | yes | EXT-004's fix for the volume half | oversized bodies become `422`; check the frontend reporter | **usable** |
| EXT-004 | yes | yes, with the subnet form | — | counter identity changes; `*` is a bypass | **usable after VAL-07-002** |
| EXT-005 | yes | yes | AUTH-002/AUTH-006 merge; store contract first | two shipped tests must change; ordering conflict | **usable after VAL-07-005, -008** |
| EXT-006 | yes | yes | — | four paths change shape | **usable** |
| EXT-007 | yes | partly | frontend owner | `422` on every write route | **usable**; the six `allow` types need intent, not inference |
| EXT-008 | yes | yes | store contract; EXT-005's merge | mirrors today's defect if the compensation is skipped | **usable after VAL-07-005** |
| EXT-009 | yes | partly | intent | removing a library the gate requires | **usable**, intent first |
| EXT-010 | yes | yes | — | `/openapi.json` 404 in the production tier | **usable** |

Order: steps 1-3 of the Roadmap before 4-10, because steps 4-10 each assume the plan was corrected.

### Appendix F — Block 6: cross-phase comparison, ownership, and the seam check

Sibling reports compared: `.ai/audit/01-process-architecture/findings.md` (raw),
`.ai/audit/04-authentication/findings.md` (raw) with
`.ai/audit/99-validation/04-authentication-validated-findings.md` (**validated**),
`.ai/audit/05-data-pipeline/findings.md` (raw), and the validated reports for phases 01-05. Nothing in
this comparison contests a sibling's identifiers, and nothing was written into another phase's directory.

| Contested item | Rival claim | Owner | Disposition |
|---|---|---|---|
| EXT-004 vs AUTH-001 | AUTH-001 (HIGH, raw + validated) | phase 04 | **merge upheld**, on AUTH-001's own Consequence rather than the input's justification; `client-errors:` added to it; `auth-api.md:113` folded into AUTH-001's doc step |
| EXT-005 vs AUTH-002 + AUTH-006 | AUTH-002 (HIGH), AUTH-006 (MEDIUM) | phase 04 | **merge** — the input filed no ruling at all |
| EXT-002's refusal class vs AUTH-008 | AUTH-008 (LOW, raw + validated) | phase 04 | **merge** of that element; EXT-002 keeps blast radius and cost |
| EXT-002 vs VAL-04-001 | phase 04's validation caution about fix (b) | phase 04, extended here | independent confirmation plus a second route to the same hazard (VAL-07-002) |
| EXT-001/EXT-002 vs phase 10 | 10's scope takes in "the health, liveness and readiness endpoint and probe contract (from 01)" and "the health contract" | **co-owned** | **not merged.** 07's block 5 names probes as its own subject ("the component a probe reports", "the status a caller polls"; evidence "one probe answer that covers more than one underlying state"), and 10's own carve-out reports an arrangement only "where the code's own description of the arrangement in force is contradicted by the arrangement actually deployed" — which is this case. 10 files about the *deployed composition* (the healthcheck disabled in dev, `start_period`, the 5 s vs 10 s timeout split); 07 files about *what the probe measures*. Phase 10 is named co-owner of the probe-contract half. Adjacency to phase 01 TOPO-001 is upheld as the input states: an absent gate versus a present gate answering the wrong question |
| EXT-008 vs DP-001 | DP-001 (CRITICAL, raw) | phase 07 owns the ordering question | **adjacency upheld** on the merits: same defect class (an external effect made durable before the commit that records it, compensation on some edges and not others), different path, different effect, different residue, disjoint code. DP-001's Recommendation states a *rule*; EXT-008's applies it to the admin path. One convention, two applications |
| EXT-003's credential-material half vs phase 15 | 15 owns "what credential material reaches any other sink" | split | **cross-reference, not merged**: the unbounded-volume half is 07's block 9 verbatim; the sink question is 15's, with a different mechanism and a different owner conversation |
| EXT-007's upload deferral vs DP-001/DP-005 | phase 05 | phase 05 | upheld; the input names but does not duplicate, which is correct |

**Seam check.** No finding is filed outside the input's own declared scope paragraph, and the two
closest calls were tested rather than assumed. EXT-004's residual doc-drift *is* outside it — phase 07's
scope assigns "the identity an inbound bound is keyed on" to 04 — and the input retained it in phase 07
on a claim about phase 04's scope that phase 04's own roadmap contradicts; that is a merge decision
reached wrongly, not a seam (VAL-07-001). EXT-009's "do not delete the libraries, establish intent
first" is the opposite of a seam: it declines a claim the block would have allowed. EXT-001 is filed in
the zone of block 5 verbatim. No finding is a defect of the input report's scope discipline.

### Appendix G — Block 7: finding-ID namespace integrity, and the ruling

Every provenance claim was re-derived from the working tree. Phase 07 declares `EXT-` at
`07-audit-external-boundary.md:139` and minted `EXT-001` … `EXT-010` with no gap and no collision
against any other phase's prefix in the set. In-source markers: a search of `src/`, `tests/`,
`docker/`, `frontend/src/` and `docs/` for `EXT-0` finds no embedded marker, so there is no
in-source provenance to migrate and nothing to retire. The compound form the template's front matter
pairs with the prefix is `phase: 07-external-boundary` + `EXT-`, which the input uses correctly.

**The ruling.** The validation namespace is the second one in the set. Phase 01 and phase 02 reports
carry a flat `VAL-` prefix (`VAL-001` … `VAL-009` in phase 01), so the flat space is occupied and reusing
it would produce an identifier resolving to two findings. Rather than mint a third variant of the same
identifier, this report adopts the `VAL-NN-` infix already established by the phase-03, phase-04 and
phase-05 validation reports, giving `VAL-07-001` … `VAL-07-011`. The deviation from the flat prefix the
output contract specifies is recorded here and in the Validation-Level Findings preamble. No sibling
file in `.ai/audit/99-validation/` was created, edited or renumbered by this run.

### Appendix H — Block 8: the shared findings template as a controlled artefact

The template resolves and was not repaired from inside this run. Per mandated element, across the ten
audited blocks of the input:

| Mandated element | Verdict | Detail |
|---|---|---|
| Front-matter `phase:` | present, honest | `07-external-boundary`, the phase that wrote it |
| Front-matter `executed` / `executor` / `problems-only` / `findings` / `by-severity` | all present | counts re-verified against the bodies; consistent |
| Non-templated extensions | benign | `baseline` / `baseline-dirty` added; no conflict with the contract |
| Per-finding five fields | all present in all ten blocks | none omitted, none renamed |
| **Zone = the block title quoted verbatim** | **10 of 10 comply** | EXT-001 and EXT-005 → block 5's title verbatim; EXT-002 → block 2; EXT-003 → block 9; EXT-004 → block 4; EXT-006 and EXT-010 → block 7; EXT-007 → block 8; EXT-008 → block 6; EXT-009 → block 1. No paraphrase and no absent zone was found, so the block's evidence requirement yields no defect on this input |
| Reserved empty-state string | not applicable | the input produced findings and did not pad a summary in its place |
| Sections | all present, none padded | Summary, Findings, Distribution, Cross-Finding Analysis, Roadmap, Rollout Safety, Appendices |

One structural note, not a defect in this input: the template carries a single `Severity` column and
enumerates no finding-ID prefixes. The input keeps its audited bands in the front matter and puts its
coverage ledger in its appendices, which is the arrangement the output contract requires of a validator
and the arrangement this report follows. No repair is warranted to the template from inside this run.

### Appendix I — Block 9: does the input rest on its own declared blocks and evidence fields

| Finding | Support: declared block / own evidence / independent observation | Angle the declared blocks do not name |
|---|---|---|
| EXT-001 | block 5 (declarative) + own evidence | — |
| EXT-002 | block 2 (declarative) + own evidence | — |
| EXT-003 | block 9 (declarative) + own evidence | — |
| EXT-004 | block 4 (declarative) + own evidence | the *documentation* claim on `auth-api.md:113` is not a block-4 question |
| EXT-005 | block 5 (declarative) for the report side; **the store fail-open is block 3's question** | block 3 is a guard-failure-direction block and EXT-005 never cites it |
| EXT-006 | block 7 (declarative) + own evidence | — |
| EXT-007 | block 8 (declarative) + own evidence | — |
| EXT-008 | block 6 (declarative) + own evidence | — |
| EXT-009 | block 1 (declarative) + own evidence | — |
| EXT-010 | block 7 (declarative) + own evidence | — |

The signature the block asks about is present once: EXT-005's root cause is a guard that permits where
it was meant to bound, which is block 3's question, filed under block 5 without citing block 3 — and
block 3's own verdict table (Appendix C of the input) already records that `TempPasswordStore.store`
"**Permits** — swallows and logs", while declining to file it. That is the one substantive finding whose
support is not its own declared block, and it is the same finding that turns out to duplicate phase
04. The remaining nine rest on their own declared blocks and their own evidence fields. No angle
outside the declared blocks produced a finding.

### Appendix J — the empty CRITICAL band, tested rather than accepted

Phase 07's CRITICAL predicate is *"a live capability reachable with no gate at all, or credential
material exposed irreversibly, where the exposure cannot be withdrawn without rotating it"*. Each
candidate was tested against it:

| Candidate | Test | Verdict |
|---|---|---|
| EXT-003, EXT-004 | is a capability reachable with no gate? | the capability is "write to the log" and "spend a shared counter" — bounded, and the input does not claim otherwise | not CRITICAL |
| EXT-005, EXT-008 | credential material exposed irreversibly? | the temp password's cleartext existed only inside the discarded request and no principal ever received it; the orphaned Redis key is reachable by nobody, so nothing is exposed | not CRITICAL |
| EXT-007, `filters` document | can it reach a capability? | `aggregated_data_repo.py:160-162` builds SQLAlchemy expressions; no interpolation, no injection, no credential | not CRITICAL |
| EXT-002, EXT-001 | availability | the predicate has no availability clause | not CRITICAL |
| EXT-006, EXT-009, EXT-010 | disclosure and drift | none matches either clause | not CRITICAL |

The band is **genuinely empty**, not merely unclaimed — and the set is not uniformly empty in it, since
phase 05's DP-001 is banded CRITICAL. The one CRITICAL-shaped near-miss, EXT-005's orphaned credential,
fails the "exposed" half of the predicate on a named ground rather than by omission, which is the
distinction worth recording.

### Appendix K — environment, restoration, and what was not settled here

**Baseline.** `git rev-parse HEAD` at the start of this run → `c3c0a61bf41cad68bf3a3ac105de91ea63c82268`,
identical to the input's recorded baseline, with the same four modified tracked files plus the same
deleted `.ai/` trees. `HEAD` then moved twice during the run — to `5a2cfb6` (`config.py`,
`db/starter.py` and their tests) and to `b23a9cb` (`app.py`, `config.py`, `tests/test_config.py`) — both
from the concurrent remediation programme. Every anchor in this report resolves at `c3c0a61`, the
revision the input filed against; the `app.py` and `config.py` anchors have since moved and are tabulated
with their current line numbers as VAL-07-009. No file was edited, staged, committed, reverted or
stashed by this run; `git status --porcelain` at completion shows only the concurrent programme's
committed work, the `.ai/` deletions that predate this run, and untracked `.ai/audit/**`,
`.ai/plans/**` — plus this report, inside the already-untracked `.ai/audit/99-validation/`. The peer's
`.tmp/b4/` tree, the `mko-bazuna-*` containers, and the five `bidb` rows discussed in VAL-07-011 were
left untouched.

**Restoration, verified.** `mkobi-redis-1` was paused once, for the EXT-001/EXT-002 reproduction, inside
a command block whose `finally` clause unpauses it; it is `Up (healthy)`, `redis-cli ping` → `PONG`,
`ACL WHOAMI` → `default`, `ACL LIST` → `user default on nopass sanitize-payload ~* &* +@all` — this run
never changed the ACL. The single Redis key it created, `client-errors:172.21.0.1`, was deleted; the only
key remaining is the pre-existing `rq:worker:*`. No container, no file and no database row was created by
this run; the two files in `/app/data/tmp_uploads` predate it, and `/app/data/logs/` is empty, so the
5 MB record measured for EXT-003 went to container stdout only. Other agents' artefacts — the
`.tmp/b4/` tree, `mko-bazuna-*` containers, and the five `bidb` rows discussed in VAL-07-011 — were left
untouched.

**What could not be settled here, and why.**

- *The write-only Redis failure behind EXT-005 was not re-run.* It requires mutating the shared
  `default` user's ACL on a Redis other agents are using. The static proof is unconditional — `store` is
  declared `-> None` and cannot raise, so its caller cannot observe the outcome — and the transcript is
  accepted as filed.
- *The production tier was not booted* (it requires a prior `frontend/dist` build and production-grade
  secrets), so EXT-010's production `/openapi.json` claim and EXT-001's Docker-health consequence remain
  static readings of `app.py:215-226` (the `FastAPI(...)` constructor) and the shipped compose, as the
  input also records.
- *The batch for EXT-003's volume ceiling was not run at the 100 MB nginx ceiling*, only at 5 MB. The
  reachable aggregate is computed from the two independently confirmed bounds, not measured.
- *Worker and connection-pool exhaustion during a Redis outage was not measured* — 4 workers × ~59 s is a
  projection from the measured per-request cost. Phase 11 owns that measurement.
- *The `filters` query parameter was not exercised with a hostile document*; the CRITICAL-band test rests
  on the repository's expression construction, read from source.

### Appendix L — Block 11: the shared angles, and their bindings

**The vacuous-control angle**, defined once at `99-audit-validate.md:60-69`: per control, does it exist,
what scope does it declare, what did it actually examine — with "did it run" kept apart from "did it
decide anything". Bindings across the set, read in the phases' own words:

| Binding phase | Wording used | Do the three questions survive? |
|---|---|---|
| 02 (`:107`) | "For every validation and gate over configuration, establish what values it reads, what predicate it applies to them, and whether that predicate can match the form the value takes … a gate that examines nothing and a gate never invoked are different defects" | yes — and it adds the invocation-path question 99 keeps separate |
| 09 (`:100`) | "for every control that can emit a verdict on this repository, establish what it is configured to examine and what it actually examined … the controls with the item count each examined" | yes, verbatim in substance |
| 10 (`:64`) | "for each, establish what it is configured to examine and what it actually examined … A control whose declared and actual scope differ is a finding however green it is" | yes, and it states the green-is-not-a-verdict rule explicitly |
| 08 (`:144`) | "the vacuous-control angle is 99's" — mentioned as ownership, then its own evidence asks "which checks are declared, where each runs, what it covers, and whether it is reachable" | **no** — a mention plus a reachability question, which is 08's own angle rather than a binding of 99's. Recorded as a set-level observation; not adjudicated from this lane |
| 07 | none | the angle is **not bound** by this phase, which is why Appendix B above was assembled as a validation product rather than as a check the input was asked to run |

**The cross-resource side-effect angle** — an effect spanning more than one resource, together with which
resource is the real unit of atomicity — is defined at `99-audit-validate.md:160-161` and bound by
**no phase in the set in its own words**. A search of all sixteen phase files for `cross-resource`,
`side-effect` and `atomicity` returns the definition in 99 and one phase-owned block title in 05
(`05-audit-data-pipeline.md:57`, *"The unit of atomicity: what commits together, and what a rollback
leaves behind"*), which is the same question asked without naming the angle. Recorded as a set-level
observation with no disposition claimed from this lane, because it affects no phase-07 finding: EXT-008
was filed and adjudicated as a phase-07 block-6 item on exactly that question regardless.

The live cross-resource instance in this phase's own corpus is EXT-008 (a Redis credential and a
PostgreSQL row, with the row as the real unit of atomicity), and phase 05's DP-001 is the other. Neither
was displaced from its owning phase by the angle's absence from the bindings.

### Appendix M — Coverage ledger

The fixed residual footer. Blocks examined and the item count each actually reached.

| Block | Items reached | Result |
|---|---|---|
| 1 — the claim re-derived from the executing path | 10 findings, anchors resolved mechanically first | 10 dispositions; 1 asserted cause refuted, 5 anchor corrections, 9 anchors relocated by concurrent commits (VAL-07-009) |
| 2 — the vacuous-control angle | 6 controls | 4 configured-and-deciding-nothing, 1 partially, 1 sound |
| 3 — the grade against the audited phase's own rubric | 10 findings | 0 re-grades; 1 rubric tension recorded |
| 4 — which side moves | 10 findings | 10 dispositions; 1 declined re-typing with the reason |
| 5 — whether the recommendation can be carried out | 10 recommendations | 7 usable as written, 3 usable after correction, 0 unusable |
| 6 — cross-phase conflict, ownership, merge, seam | 8 contested items + 1 seam check | 3 merges upheld, 1 adjacency upheld, 1 co-ownership, 1 cross-reference, 0 seams |
| 7 — finding-ID namespace integrity | 1 declared prefix, 10 minted identifiers, 3 sibling namespaces | ruling recorded; collision reported, not resolved by a second variant |
| 8 — the shared template as a controlled artefact | 7 mandated elements across 10 blocks | zone verbatim in 10 of 10; template not repaired |
| 9 — whether the input rests on its own declared blocks | 10 findings | 1 finding (EXT-005) rests on a block its zone does not name |
| 10 — the validated report as an artefact | front matter, 10 + 11 blocks, tally, namespace separation | tally agrees with the per-finding verdicts; 2 internal corrections made during drafting |
| 11 — the shared angles and their bindings | 4 bindings + 1 unbound angle + 1 phase silent | 3 bindings sound, 1 drifted (08), 1 unbound (cross-resource) |
| Claimed negative results | 4 | 4 confirmed |
| Empty CRITICAL band | 5 candidates tested against the predicate | genuinely empty, not merely unclaimed |

**Every claim left unsettled, with its reason.** (1) The write-only Redis failure behind EXT-005 was not
reproduced here: it requires mutating the shared `default` user's ACL on a Redis other agents are using,
and the static proof is unconditional. (2) The production tier was not booted — it needs a prior
`frontend/dist` build and production-grade secrets — so EXT-010's `/openapi.json` claim and EXT-001's
Docker-health consequence remain static readings of `app.py:215-223` and the shipped compose, as the
input also records. (3) EXT-003's reachable aggregate was computed from two independently confirmed
bounds rather than measured at the 100 MB nginx ceiling. (4) Worker and connection-pool exhaustion under
a Redis outage is a projection from the measured per-request cost, not a measured saturation point; phase
11 owns it. (5) EXT-007's `filters` boundary was not exercised with a hostile document; its
CRITICAL-band verdict rests on the repository's expression construction read from source. (6) The
in-source marker search found no embedded `EXT-` provenance, so the "migrate or retire" half of the
namespace ruling has nothing to act on and is recorded as a null result rather than a verdict.