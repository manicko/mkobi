---
phase: 07-external-boundary
executed: 2026-09-30
executor: auditor
problems-only: true
baseline: c3c0a61bf41cad68bf3a3ac105de91ea63c82268
baseline-dirty: src/mkobi/config.py, src/mkobi/db/starter.py, tests/test_config.py, tests/test_starter.py (+ deleted .ai/builders, .ai/structure, .ai/models, .ai/templates, .ai/plans)
findings: 10
by-severity:
  CRITICAL: 0
  HIGH: 4
  MEDIUM: 4
  LOW: 2
---

# Phase 07 — Findings

## Summary

The zone examined is the boundary with the outside: whether an outbound boundary exists, the derived
dependency set, what bounds arrival, what the anonymous ingress surface answers and discloses, which
boundaries validate, and what an untrusted body is written to the log as. All nine blocks were
executed against a live `mkobi` dev stack with the `app`, `db`, `redis`, `rq-worker` and `frontend`
services up; the outage, collapse, log-volume and refusal-ordering probes were reproduced at runtime
and the environment was restored afterwards.

There is no outbound boundary: nothing in `src/` opens a connection to a host it does not control, and
no webhook, notification or callback sink exists in the model layer. The single most consequential
thing found is that **Redis sits on the authentication path of every protected endpoint while the
health probe that both the Docker `HEALTHCHECK` and the documented liveness/readiness integration
consume never looks at it** — with Redis unreachable, `/health` returns
`{"status":"healthy","database":"connected"}` in 19 ms while `GET /api/v1/auth/me` and
`GET /api/v1/dashboards/` both return `401 AUTHENTICATION_FAILED "Authentication failed"` after
**58.8 s and 57.9 s** respectively. A second Redis defect on the admin approval path returns
`200 {"message":"Registration request approved", "retrieval_token": …}` for a credential that was
never stored, and the returned token then resolves to `404`.

## Findings

### EXT-001 — The health probe reports `healthy` while every authenticated request fails

**Severity** — HIGH

**Zone** — A degraded result the consumer cannot tell from a real one

**Observation** — `GET /health` (`src/mkobi/app.py:257-276`) and `GET /health/detailed`
(`src/mkobi/app.py:278-316`) each probe exactly one dependency: `SELECT 1` against PostgreSQL through
`get_session()`. Neither opens a Redis connection. The token-revocation check that every protected
endpoint runs first — `is_token_revoked(redis_client, jti)` and
`is_user_tokens_revoked(redis_client, user_id)` in `get_current_user_dependency`
(`src/mkobi/api/deps.py:504-532`), both of which call `await redis_client.exists(key)` unguarded
(`src/mkobi/core/security.py:492-519`) — is therefore invisible to both probes. The answer
`{"status": "healthy", "database": "connected"}` is returned for a process in which 100% of
authenticated traffic is refused.

This answer is what the deployment itself consumes. `docker/Dockerfile:176-177` and
`docker/docker-compose.yml:142-147` both define the container healthcheck as
`curl -f http://localhost:8000/health`, so Docker keeps reporting the container `Healthy` throughout
the outage. `docs/05-health/health-api.md:180-182` instructs operators to use these endpoints as
Kubernetes `livenessProbe`/`readinessProbe` targets, to "determine instance availability" with a load
balancer, and to "alert on non-200 responses" from an uptime monitor — an alert rule that cannot fire,
because the failing condition does not produce a non-200.

**Evidence** — Runtime probe against the live dev stack with `mkobi-redis-1` paused (deterministically
unreachable, no restart), same session, four requests in order:

| Probe | Redis reachable | Redis paused |
|---|---|---|
| `GET /health` | `200` `{"status":"healthy","database":"connected"}` in 0.010 s | `200` `{"status":"healthy","database":"connected"}` in **0.019 s** |
| `GET /health/detailed` | `200` `"status":"healthy"` in 0.011 s | `200` `"status":"healthy"` in **0.018 s** |
| `GET /api/v1/auth/me` (valid bearer) | `200` in 0.045 s | **`401 AUTHENTICATION_FAILED` in 58.815 s** |
| `GET /api/v1/dashboards/` (valid bearer) | `200` in 0.193 s | **`401 AUTHENTICATION_FAILED` in 57.910 s** |

The `/health/detailed` body in the paused column is byte-identical to the reachable column. Server-side
log line for the failing authenticated request, captured from `mkobi-app-1`:

```
{"level": "ERROR", "module": "deps", "function": "get_current_user_dependency",
 "message": "Error getting current user: Timeout reading from redis:6379"}
```

Recovery was verified: after `docker unpause`, `GET /api/v1/auth/me` returned `200` in 0.028 s. The
defect is bounded to the outage window, not persistent.

**Consequence** — During a Redis outage the deployment reports itself healthy while serving no
authenticated page. Docker will not mark the container unhealthy; a load balancer will keep routing to
it; the documented uptime alert cannot fire. An operator's first signal is user reports, not a
monitor. The probe answers a question (is PostgreSQL reachable?) that is not the question every caller
of the probe is asking (can this instance serve a request?).

**Recommendation** — Add a Redis `PING` to `/health` and to the component block of
`/health/detailed`, and return `503` when it fails, so the existing `curl -f` healthcheck and the
documented probe contract become true. The smallest correct shape is a third component entry
(`"redis": {"status": "connected"|"disconnected"}`) using `redis_client.ping()`, with
`health_status["status"] = "unhealthy"` on failure — `app.py:300-306` already contains the exact
pattern to copy. Update `docs/05-health/health-api.md:163-172` (failure-mode table) and `:180-185` in
the same change. No shipped test asserts `/health` reports healthy when Redis is down, so there is no
test to unblock; `tests/` should gain one case per component.

**Cross-reference** — Same root cause as EXT-002 and EXT-005. Adjacent to Phase 01 TOPO-001
(nothing gates traffic on readiness; 40-57 s of connection-refused after restart): this is the
*reporting* half of that gap — the gate exists and it is blind. Not merged, because Phase 01's
finding is about the absence of a gate and this is about a present gate that answers the wrong
question.

### EXT-002 — One Redis outage takes down every page rather than one feature, and reports it as a bad credential

**Severity** — HIGH

**Zone** — The derived dependency set: what the request path cannot answer without, and what each one's failure takes down

**Observation** — The request path cannot answer without two dependencies: PostgreSQL (every route,
through `get_db_dependency`) and Redis. Redis is not a feature dependency — it is a *precondition* of
the authentication dependency itself. `get_current_user_dependency`
(`src/mkobi/api/deps.py:472-576`) calls `is_token_revoked` and `is_user_tokens_revoked` before it
resolves the user, and both perform a bare `await redis_client.exists(key)` with no timeout wrapper and
no exception handling of their own. `jti` is always present — `create_access_token` and
`create_refresh_token` both set it unconditionally (`src/mkobi/core/security.py:286`, `:327`) — so the
Redis call is not optional on any protected request. `TempPasswordStore` adds a third Redis role and
the rate limiter a fourth.

The blast radius is therefore the whole authenticated surface, not a feature: all 53 authenticated
operations in the OpenAPI document route through this dependency. There is no degraded mode — a Redis
error is caught only by the catch-all `except Exception` at `deps.py:570-576` and converted into
`AppException(AUTHENTICATION_FAILED, "Authentication failed")`, byte-for-byte the response a caller
receives for a malformed, expired or forged token.

The per-request cost is 58 s, not 58 ms. `src/mkobi/core/redis_client.py:46-52` constructs
`aioredis.Redis(host, port, db, password, decode_responses=True)` with no `socket_timeout`, no
`socket_connect_timeout` and no `retry` argument, so the effective bound is the library default. The
runtime image resolves `redis` to **8.0.0** (`uv.lock`), whose defaults are `socket_timeout=5`,
`socket_connect_timeout=5` and an automatic `Retry` with jittered backoff — three retries of a 5 s
timeout, which is where ~58 s comes from. The application declares no bound of its own; only the
lockfile holds that figure, and any `uv lock --upgrade` moving the redis major can change it with no
code change.

**Evidence** — Same paused-Redis probe as EXT-001: `GET /api/v1/auth/me` `401` in **58.815 s**,
`GET /api/v1/dashboards/` `401` in **57.910 s**, with the identical body
`{"type":"…/authentication_failed","title":"Authentication failed","status":401,"detail":"Authentication failed","code":"AUTHENTICATION_FAILED"}`.
Library defaults read from the running container:

```
redis-py 8.0.0
socket_timeout         -> 5
socket_connect_timeout -> 5
retry                  -> <redis.asyncio.retry.Retry object>
```

Measured latencies with Redis reachable were 0.045 s and 0.193 s, so the outage multiplies request
cost by roughly 300x. Recovery to 0.028 s verified after `docker unpause`.

**Consequence** — A single Redis instance going away is a total outage of the authenticated product
with no degraded mode, presented to the user as an authentication failure and to the operator as a
mass credential invalidation. In the deployed topology (`docker/Dockerfile:179`,
`uvicorn … --workers 4`) each worker holds requests for ~58 s at a time, so the outage converts
directly into worker and connection-pool exhaustion. An operator following
`docs/01-auth/auth-api.md:511` — "Deactivated users receive HTTP 401 on any authenticated endpoint" —
will read the outage as a deactivation event.

**Recommendation** — Two changes, both small. (1) Bound the client: pass explicit `socket_timeout`
and `socket_connect_timeout` (≈1 s is appropriate for an `EXISTS` on a local socket) and
`retry=Retry(NoBackoff(), 0)` in `src/mkobi/core/redis_client.py`, so the per-request cost is
declared by this project rather than inherited. (2) Separate the dependency's failure from the
credential's: catch `redis.exceptions.RedisError` around the two revocation calls in `deps.py` and
raise a distinct code mapped to 503 (`SERVICE_UNAVAILABLE` does not exist in
`src/mkobi/models/enums.py` and would need adding), so the refusal class states the cause. A
revocation check that cannot run should be refused as a dependency outage, not reported as a bad
token. No shipped test asserts the 401 shape under a Redis failure; `tests/test_auth.py:328` and
`:365` cover the *rate limiter's* fail-open/fail-closed directions, not the revocation path, and
should be extended rather than changed.

**Cross-reference** — Shares the cause with EXT-001 and EXT-005. Adjacent to Phase 03
(TXN-001..012), which owns pooler semantics: the 58 s figure is a client-side timeout, not pool
exhaustion, so it is reported here and not merged into TXN. Adjacent to Phase 04, which owns the
revocation marker's meaning — the finding here is not what a marker must express but that failing to
read one is reported as a credential fault.

### EXT-003 — An anonymous 5 MB body is written verbatim into a single ERROR log record with no field cap

**Severity** — HIGH

**Zone** — The untrusted body as it is logged

**Observation** — `POST /api/v1/client-errors` (`src/mkobi/api/routes/client_errors.py:24-68`) is the
only anonymous sink in the application. It requires no credential, and it writes the caller's body to
the log:

```python
error_message = payload.error.get("message", "Unknown error")
logger.error(
    "Client error: %s | url=%s | componentStack=%s",
    error_message, payload.url, payload.componentStack,
)
```

`error` is declared `dict[str, Any]` (`src/mkobi/models/data.py:511`) with no size limit, and
`ClientErrorPayload` declares no `extra` policy, so neither the container nor the body is bounded by
the model. There is no `Content-Length` check on the route and no field-length truncation before the
log call. The only size ceiling on this path is nginx's server-level
`client_max_body_size 100m` (`docker/nginx/nginx.conf:18`), which applies in production because the
`/api` location does not override it. In production the log destination is a file on a named volume —
`LOGGING__LOG_FILE: /app/data/logs/app.log` (`docker/docker-compose.yml:114`).

The volume bound on the path is `100 attempts / 3600 s` keyed on
`f"client-errors:{client_ip}"` (`client_errors.py:49-50`). Behind the project's own shipped proxy that
key is a single constant for the entire caller population (EXT-004), so the 100 records/hour is a
shared pool one caller can spend alone, and each record can be up to ~100 MB.

**Evidence** — Two anonymous probes against the live stack, no `Authorization` header.

Probe 1 — masking and transformation. A body carrying a newline-embedded fake log record and a
credential-shaped field:

```
POST /api/v1/client-errors -> 204
```

produced exactly one log record, with newlines JSON-escaped (`\n`, so no log-line injection — a
passing check, not a finding) and the credential verbatim and unmasked:

```json
{"level": "ERROR", "module": "client_errors", "function": "report_client_error",
 "message": "Client error: INJECT-150037 FAKE | forged line pretending to be a server log\n{\"timestamp\":\"2020-01-01\",\"level\":\"INFO\",\"message\":\"admin login ok\"}\n<password>hunter2</password> | url=https://evil.invalid/INJECT-150037?token=abc | componentStack=INJECT-150037 STACK"}
```

Probe 2 — volume. A single request with a **5,000,073-byte** body:

```
POST 5MB anonymous body -> 204|0.214956s
largest log record length (chars): 5000304
```

A 5 MB request produced a 5,000,304-character log record in 215 ms, i.e. the body is buffered whole
and written whole. At the production ceiling of ~100 MB per request and 100 requests per hour on one
shared key, the reachable volume is ~10 GB of log written to the `app_data` volume from a single
anonymous source, with no field-level cap at any point.

**Consequence** — Any credential, token or personal datum a browser client places in the reported
`error` object is persisted verbatim in the application log, and an anonymous caller controls the size
of that record up to the proxy ceiling. The disk-fill path needs no credential and no session, and the
100/hour bound that appears to limit it is a shared pool (EXT-004), so it bounds the total rather than
any one caller.

**Recommendation** — Cap the fields before the log call, not after it: truncate each of
`error["message"]`, `url` and `componentStack` to a fixed length (512 characters is ample for
diagnostics) and log the untruncated length alongside, so a caller can see that truncation occurred
without being able to choose the record size. Constrain `ClientErrorPayload.error` to the two fields
actually read (`message: str | None`, `name: str | None`) with `max_length`, which turns an oversized
body into a `422` at the boundary instead of a disk write. Add a `Content-Length` pre-check to the
route so an oversized body is refused before it is read into memory. No shipped test asserts the
current verbatim behaviour; `tests/` should gain one case per field asserting the truncation boundary.

### EXT-004 — The whole inbound budget collapses onto the proxy's address: five distinct callers charged one key

**Severity** — HIGH

**Zone** — The aggregate ingress budget: what bounds arrival, how its scope is shared, and whether one caller is recognised the same way on every surface

**Observation** — Five inbound volume bounds exist, and their scope differs by surface:

| Bound | Key | Limit | Counter lives in | Shared across processes? |
|---|---|---|---|---|
| `POST /api/v1/auth/login`, `/login/form` | `login:{request.client.host}` | 5 / 300 s | Redis | yes |
| `POST /api/v1/auth/refresh` | `refresh:{request.client.host}` | 10 / 300 s | Redis | yes |
| `POST /api/v1/auth/register-request` | `register-request:{client_ip or email}` | 3 / 3600 s | Redis | yes |
| `POST /api/v1/client-errors` | `client-errors:{request.client.host}` | 100 / 3600 s | Redis | yes |
| `POST /api/v1/upload/{dashboard_id}` | `upload:{current_user.id}` | 100 / 3600 s | Redis | yes |

All five counters live in Redis, so the process and replica counts derived from the shipped
configuration — 4 uvicorn workers (`docker/Dockerfile:179`), 1 app container, 1 Redis
(`docker/docker-compose.yml:157-173`) — do **not** multiply any budget. That part of the budget is
correct. The defect is the opposite one: four of the five keys are derived from
`request.client.host`, and in the project's own shipped deployment that value is a single constant.
`docker/Dockerfile:179` starts uvicorn without `--forwarded-allow-ips`, so uvicorn's default
`127.0.0.1` applies and the `X-Forwarded-For` that `docker/nginx/nginx.conf:38` sets
(`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`) is discarded. The only process in
front of the app is the nginx container on the compose bridge, so every caller presents the same
`request.client.host` and the same key.

The consequence is worst on the smallest budget. `/api/v1/auth/register-request` allows 3 requests per
hour, shared by the entire caller population, on a public state-changing surface: three anonymous
requests exhaust the platform's registration capacity and every subsequent visitor is refused with
`429` for the remainder of the hour. `/api/v1/auth/refresh` (10 / 300 s) is the more operationally
severe instance, because the access token expires after 15 minutes
(`config.py:280`), so a shared 300 s refresh budget that one caller exhausts locks the whole user base
out of the application for the balance of each access-token lifetime.

The documentation states the opposite of the behaviour on two of the five: `docs/01-auth/auth-api.md:114`
promises "3 attempts per hour per IP/email" for `register-request`, but `auth.py:566` is
`f"register-request:{client_ip}" if client_ip else f"register-request:{request_data.email}"` — the
email is only part of the key when no IP is available, which in practice never happens; and
`auth.py:81-82` and `docs/01-auth/auth-api.md:46,96` promise "5 attempts per 5 minutes **per IP**",
which the deployed topology does not deliver.

**Evidence** — The proxy collapse was reproduced with a purpose-built forwarding container on the
project's own `mkobi_default` compose network — the same position nginx occupies — forwarding to
`app:8000` and injecting distinct `X-Forwarded-For` values. The app was left with its shipped
configuration (no `--forwarded-allow-ips`). Five requests carrying five syntactically distinct caller
addresses:

```
caller XFF=4.4.4.4 -> 422      (that email already existed from an earlier probe)
caller XFF=5.5.5.5 -> 429
caller XFF=6.6.6.6 -> 429
caller XFF=7.7.7.7 -> 429
caller XFF=8.8.8.8 -> 429
```

Redis afterwards held exactly one key for all five:

```
register-request:172.21.0.7
GET  register-request:172.21.0.7 -> 3
TTL  register-request:172.21.0.7 -> 3599
```

Three requests from three distinct addresses (`1.1.1.1`, `2.2.2.2`, `3.3.3.3`) to
`POST /api/v1/client-errors` each returned `204` and produced one key, `client-errors:172.21.0.7` —
the forwarder container's bridge address. No key exists for any of the six `X-Forwarded-For` values.
The app log confirms the derivation directly: `Rate limit exceeded for client-errors endpoint … "ip": "172.21.0.7"`.

**Consequence** — A single unauthenticated caller can deny a public capability platform-wide for the
length of the window and cannot be distinguished from any other caller in the counter, the log, or the
`429`. The two IP-keyed budgets on the authentication path mean the platform has no per-caller login
throttle at all in its own shipped deployment: the budget is per proxy. The remedy is one line
(`--forwarded-allow-ips` for the compose network subnet), and until it lands, every IP-keyed bound in
the table above is a global limit with a five-request or three-request trigger.

**Recommendation** — Pass `--forwarded-allow-ips` to uvicorn covering the compose bridge subnet (or
`"*"` if the app is only ever reachable from the compose network) in `docker/Dockerfile:179` and in
the dev command at `docker/docker-compose.override.yml:109`, then confirm with the reproduction above
that N distinct `X-Forwarded-For` values produce N distinct keys. While doing so, decide explicitly
whether the two authentication budgets should also be keyed on a principal (email, or
email+address) so that a single attacker cannot spend a shared address budget, and correct
`docs/01-auth/auth-api.md:46,96,113,114` to the key composition that is actually implemented.
No shipped test asserts the collapsed behaviour; `tests/test_rate_limiting.py:203-243` constructs
`AsyncRateLimiter` with a literal key and so cannot detect the collapse — add a test that asserts two
different client addresses yield two different Redis keys through the real dependency.

**Merge/adjacency ruling** — **Merge into Phase 04 AUTH-001.** The root cause is identical and one fix
(`forwarded-allow-ips`) closes every instance. AUTH-001 filed the collapse for the `login:` key only and
did not establish that three further surfaces share it, nor the 3-per-hour consequence on a public
state-changing surface; this finding is the same defect at a wider blast radius and should be tracked
as one remediation item, not two. What is *not* merged: the doc-drift on "per IP/email"
(`auth-api.md:113`) is this phase's, because it is a published-description claim about the boundary, and
Phase 04's scope excluded that surface.
### EXT-005 — Approving a registration returns 200 and a retrieval handle for a credential that was never stored

**Severity** — MEDIUM

**Zone** — A degraded result the consumer cannot tell from a real one

**Observation** — `POST /api/v1/admin/registration-requests/{id}/approve`
(`src/mkobi/api/routes/admin.py:279-345`) performs six steps in order: generate a random temporary
password, create the user row, set `force_password_change`, generate a `retrieval_token`, **store the
password in Redis**, mark the request `APPROVED`, and `db.commit()`. Step 5 goes through
`TempPasswordStore.store`, which is documented to fail open and does exactly that
(`src/mkobi/core/temp_password_store.py:30-48`):

```python
except Exception as exc:
    logger.error("Failed to store temp password in Redis: %s", exc)
```

`store()` returns `None` on failure, the return value is ignored at `admin.py:321`, and the endpoint
unconditionally returns `200` with the `retrieval_token` at `admin.py:332-336`. The same swallow is on
the read side: `retrieve()` returns `None` for both "not found" and "Redis error"
(`temp_password_store.py:73-75`), and `admin.py:419-423` maps both to
`404 "Temporary password not found or already retrieved"`. A stored value is returned where the
caller needed a status, and the status that is returned names the wrong cause.

**Evidence** — Reproduced against the live stack with a write-only Redis failure, so the auth
dependency's reads succeed and the path is reachable. An ACL was applied to the `default` user
granting `+get +exists +ttl +incr +expire +ping +select` and denying everything else, which leaves
`is_token_revoked`/`is_user_tokens_revoked` working and breaks only `SET`/`SETEX`:

```
request id = bce038fd-1101-459d-ad55-556539d71edf
=== install a WRITE-ONLY Redis failure (reads still work) ===
OK
APPROVE RESULT (wall=709ms):
{"message":"Registration request approved",
 "user_id":"03c82044-ca95-4ba4-ba53-e053ce8ae150",
 "retrieval_token":"00067fe9-45bc-45f7-8958-b370cdc613d3"}

retrieve -> {"type":"…/not_found","status":404,
             "detail":"Temporary password not found or already retrieved","code":"NOT_FOUND"}
```

The endpoint reported success in 709 ms and handed back a retrieval handle that resolves to `404`. The
user row and the `APPROVED` status were committed, so the password is now a random value held by
nobody. The ACL was restored to `+@all` afterwards and verified (`ACL WHOAMI -> default`,
`ACL LIST -> user default on nopass sanitize-payload ~* &* +@all`).

The same fail-open shape exists on the service-layer path at
`src/mkobi/services/auth_service.py:581-598` (admin password reset), which builds and returns a
`retrieval_token` the same way.

**Consequence** — The approval appears to have succeeded to the administrator and the durable record
says `APPROVED`, but the user account exists with a password that can never be retrieved. The
registration request is now `APPROVED`, so re-approving is refused with `DUPLICATE_RESOURCE`; the only
recovery is direct database surgery. Nothing in the response path distinguishes this from a successful
approval, and the follow-up `404` misreports the cause as "already retrieved", so the administrator's
natural conclusion — that the handle was consumed — is wrong. There is no self-healing path.

**Recommendation** — Make the store's result observable at the caller: have `TempPasswordStore.store`
re-raise (or return a `bool` the caller must check) and have `admin.py:321` abort the approval with a
503 before `db.commit()` when the password was not stored, so no durable record is written for an
absent credential. The docstring at `temp_password_store.py:33` currently promises fail-open as
intent; decide deliberately and record the choice, because fail-open is only defensible where losing
the write loses nothing — here it loses the credential. Separately, distinguish the two `None` cases
in `retrieve()` so the retrieval endpoint can say "already retrieved" versus "store unavailable". No
shipped test asserts the current 200-with-dead-token behaviour; `tests/` should gain a case that
fails the Redis write and asserts the approval is refused.

### EXT-006 — The credential check runs after the router's slash redirect, so every declared path answers an anonymous caller

**Severity** — MEDIUM

**Zone** — The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them

**Observation** — Seven of the sixty operations in the machine-readable description are anonymous:
`POST /api/v1/auth/login`, `/login/form`, `/refresh`, `/register-request`, `/client-errors`, and both
health endpoints. The remaining 53 all require a bearer token. The boundary is otherwise clean, but the
routing layer answers before the authentication layer does. Starlette's `redirect_slashes` handling
runs ahead of route resolution and therefore ahead of every `Depends`, so a request for a declared
path without its trailing slash receives a `307` with no credential presented, while an undeclared
path receives `404`. The two response classes are trivially distinguishable, which makes all 43
declared paths discoverable by an anonymous caller from the slash/no-slash pair alone.

The `Location` header is absolute and built from the request's `Host`, so the caller also chooses the
host it is redirected to. `redirect_slashes=False` is set on the auth, client-errors, upload and
combined dashboard routers (`auth.py:68`, `client_errors.py:21`, `upload.py:48`, `dashboards.py:20`),
which suppresses the *trailing-slash-to-no-slash* direction but not the no-slash-to-trailing-slash
direction that this finding is about.

**Evidence** — Anonymous probes against the live stack:

```
GET /api/v1/dashboards  ->  307 Temporary Redirect
                             location: http://localhost:8010/api/v1/dashboards/
                             x-content-type-options: nosniff
GET /api/v1/dashboards/ ->  401 {"code":"AUTHENTICATION_FAILED", … "detail":"Not authenticated"}
GET /nonexistent-spa-route -> 404 {"code":"NOT_FOUND", …}
GET /api/v1/auth/me     -> 401 {"code":"AUTHENTICATION_FAILED", … "detail":"Not authenticated"}
```

With a caller-chosen `Host`:

```
$ curl -H "Host: attacker.example.com" http://localhost:8010/api/v1/dashboards
HTTP/1.1 307 Temporary Redirect
location: http://attacker.example.com/api/v1/dashboards/
```

The published description declares the trailing-slash form only — `"/api/v1/dashboards"` is absent
from `paths` while `"/api/v1/dashboards/"` is present — so the shape that answers anonymously is the
one the description omits. The same asymmetry holds for `"/api/v1/graphs/"` and `"/api/v1/dashboards/"`;
`"/api/v1/layouts"` is declared and served without a redirect.

**Consequence** — An anonymous caller can enumerate the declared API surface from the 307/404 pair, and
for every affected path the 307 leaks a `Location` whose host the caller supplied. The realistic
exploitability of the host echo is limited: a browser resolving the application's own hostname sends
that hostname, so the cross-host bounce needs an attacker who can also control the victim's `Host`,
which browsers do not permit. The live consequence today is the anonymous path-existence oracle and
the extra hop before authentication, not an open redirect against the canonical hostname.

**Recommendation** — Serve the slash-normalised path directly instead of redirecting: register each
affected route under both spellings, or register the collection routes at the slash-less path so the
shape the description declares is the shape the router matches. If a redirect must remain, emit a
path-relative `Location` and perform it after the credential dependency has run. Align the declared
path in the description with the served path either way. No shipped test asserts the 307; `tests/`
should gain a case asserting `GET /api/v1/dashboards` returns `401`, not `307`.

### EXT-007 — No request-body model declares a strictness policy, so an unrecognised field is silently dropped

**Severity** — MEDIUM

**Zone** — Which inbound boundaries validate, which defer validation past acceptance, and which documented exceptions are load-bearing

**Observation** — There is no strict-by-default base to inherit. All 64 Pydantic `BaseModel` subclasses
in `src/mkobi/models/` derive from `BaseModel` directly; there is no shared request-model base and no
`ConfigDict` factory. Exactly one model in the whole package declares a keyword-form `extra` policy —
`TransformationConfig` (`src/mkobi/models/transformation_configs.py:131-133`, `extra="forbid"`) — and it
is a nested configuration model, not a request body. Six models in `src/mkobi/models/types.py` use the
dict form `{"extra": "allow"}` (lines 47, 247, 260, 279, 292, 305), all of them internal
runtime-validation types. **None of the 21 models used as a request body declares any `extra` policy**:
`LoginRequest`, `RegisterRequest`, `ChangePasswordRequest`, `RegistrationRequestCreate`,
`ClientErrorPayload`, `DashboardCreate`, `DashboardUpdate`, `FilterBase`, `FilterUpdate`, `GraphBase`,
`GraphUpdate`, `LayoutBase`, `LayoutUpdate`, `ProcessingConfigBase`, `ProcessingConfigUpdate`,
`ProcessingLogFilter`, `ProcessingLogCreate`, `ProcessingLogUpdate`, `UserCreateRequest`,
`UserUpdateRequest`, `UserUpdateActiveRequest`.

All 21 therefore run on Pydantic v2's default `extra="ignore"`: an unrecognised field is **ignored**,
not rejected and not coerced, and the request proceeds. A client that misspells or renames a field
receives a normal `200`/`201` with that field dropped, and the write commits with its default. The
single `extra="forbid"` exception is undocumented — nothing in `docs/` states that the convention
exists, that it is applied to exactly one model, or why.

Two further boundaries validate later than acceptance. `GET /api/v1/data/aggregated` takes
`filters: str | None = Query(...)` and hand-parses it with `json.loads(filters)` at
`src/mkobi/api/routes/data.py:109`, outside the model layer, into a `dict[str, Any]` that goes
straight to the repository as a JSONB containment filter with no schema check — the only structural
check is that the string parses as JSON. And `GraphBase.config` / `GraphUpdate.config` are
`GraphConfigDict`, a `TypedDict(total=False)` (`src/mkobi/models/types.py:138-152`): a plain `dict` at
the boundary, so the chart configuration a client submits is not validated at all before it is stored.

**Evidence** — Derived by enumeration, not assumed:

```
Pydantic BaseModel subclasses in src/mkobi/models/ : 64
TypedDict type aliases                             : 18
with a keyword-form extra policy                   :  1   (transformation_configs.py:133)
with a dict-form {"extra": ...} policy             :  6   (types.py:47,247,260,279,292,305)
request-body models declaring any extra policy     :  0   of 21
```

`docs/` contains no reference to `extra`, `forbid`, or a strictness convention (searched across all
`.md`; the only `strict` matches are `SameSite=Strict` cookie attributes). The deferred-validation
boundaries are static: `data.py:54` + `:109`, and `models/graph.py:15` / `:45` typed
`GraphConfigDict` from a `TypedDict`.

The upload boundary is named here for completeness and not filed: the request is accepted and an
`UPLOADED` `ProcessingLog` row is written (`src/mkobi/services/data_service.py:163`) before a later
process validates the CSV content. The defects in that pipeline belong to Phase 05 (DP-001, DP-005) and
are cross-referenced rather than duplicated.

**Consequence** — Every write surface accepts a malformed body with a success response. A client
renaming a field loses the value with no error, no warning in the log, and a committed row containing
the default — the failure is discovered later, by inspection, with nothing correlating it to the
request that caused it. The `filters` query parameter and the graph `config` document are worse: they
are unvalidated structures persisted or used as a query filter, so the only feedback a caller gets for
a wrong shape is an empty result set or a server error from a later layer.

**Recommendation** — Introduce one request-model base in `src/mkobi/models/` (for example
`StrictRequestModel`) carrying `ConfigDict(extra="forbid")`, and have the 21 request-body models
inherit it. This is the smallest change that makes the convention executable and gives it one place to
document; add a line to `docs/08-security/` or `docs/99-reference/error-handling-guide.md` recording
it, so the current single exception in `transformation_configs.py:133` is either justified in the doc
or removed as accidental. For the two deferred boundaries, model `filters` as a Pydantic type in the
query signature (or validate the parsed dict against it before use) and give `GraphBase.config` a
real `BaseModel` instead of a `TypedDict`. Adopt the convention on the six `{"extra": "allow"}` types
only if they are genuinely open — they are internal, so `forbid` is likely correct there too. No
shipped test asserts the drop-on-unknown behaviour; `tests/` should gain one case per model class
asserting a `422` for an unrecognised field.
### EXT-008 — The credential write is ordered before the commit that records it, with no compensation

**Severity** — MEDIUM

**Zone** — Isolation of failure inside a batch, and the order of a durable record against the effect it describes

**Observation** — The same approval sequence as EXT-005 has a second, independent ordering defect. The
Redis write at `src/mkobi/api/routes/admin.py:321` is committed to Redis immediately, while the durable
record that describes it — the user row, the `force_password_change` flag and the `APPROVED` status — is
committed by a single `await db.commit()` at `admin.py:330`, nine lines later. If that commit fails, the
`except Exception` at `admin.py:339-345` rolls the database back and returns `500 INTERNAL_ERROR`, but
the Redis entry survives: a live temporary password sits in Redis under a `temp_pwd:{token}` key for
`temp_password_ttl_seconds`, describing a user that does not exist. The handler compensates for nothing,
and the `retrieval_token` — the only key to that entry — is returned solely on the success path, so
nobody is ever told which orphan key was left behind.

The same ordering appears on the service-layer reset path at
`src/mkobi/services/auth_service.py:581-598`. A repeat of the operation re-does all six steps and mints
a fresh `retrieval_token` each time, so orphan keys accumulate one per failed commit until their TTL
expires rather than being reachable or reclaimable by the administrator.

By contrast the same batch on `/api/v1/auth/logout` was checked and is *not* defective: the two
revocation writes there are unreachable under a Redis outage, because `get_current_user_dependency`
fails first, so a half-applied logout cannot occur by that route. Recorded here so the block's
isolation question has a negative result on record rather than an untested assumption.

**Evidence** — Static ordering proof from the source, interleaving established line by line:

```
admin.py:307  user = await auth_service.create_user(...)                  # DB write, uncommitted
admin.py:315  await auth_service.user_repo.update(force_password_change=True)  # DB write
admin.py:320  retrieval_token = str(uuid4())
admin.py:321  await temp_password_store.store(retrieval_token, temp_password)  # REDIS write, durable now
admin.py:324  await repo.update_status(status=APPROVED, ...)               # DB write
admin.py:330  await db.commit()                                           # one commit for all 3 DB writes
admin.py:339  except Exception: await db.rollback()                        # compensates the DB only
```

The read side is atomic while the write side is not: `TempPasswordStore.retrieve`
(`src/mkobi/core/temp_password_store.py:62-66`) correctly wraps `GET`+`DELETE` in
`pipeline(transaction=True)`, which establishes atomic multi-step Redis use as the intended convention
in this module.

**Consequence** — A failed commit leaves a real credential in Redis for a user that was never created,
with no record of the token that reaches it. The window is bounded by `temp_password_ttl_seconds`
(24 h default, `temp_password_store.py:20`), so the residue is bounded rather than permanent, but during
that window a credential exists that no principal is accountable for and no administrator can
enumerate — the token space is a `uuid4` and the keys are not listed by any endpoint.

**Recommendation** — Move the `temp_password_store.store` call to after `db.commit()` at
`admin.py:330`, and delete the key on any subsequent failure, so the Redis entry becomes reachable
only once the row that justifies it exists. Apply the same reordering to `auth_service.py:581-598`.
No shipped test asserts the current ordering; `tests/` should gain a case that fails the commit and
asserts no `temp_pwd:*` key remains.

**Cross-reference** — **Adjacent, not merged, with Phase 05 DP-001** ("enqueue + file rename before
`db.commit()` with compensation on one edge only"). The shape is the same class of defect — an external
effect made durable before the commit that records it, with compensation on some edges and not others —
but the path, the effect and the residue differ (a Redis credential versus a stored file and an RQ job),
and the two remediations do not touch the same code. The recommendation applies DP-001's
commit-then-publish rule to the admin path; the lead may close both with one convention recorded once
and applied in both places.

### EXT-009 — The startup self-check refuses to start on four libraries the application never imports

**Severity** — LOW

**Zone** — Whether this boundary exists at all, and every mechanism that would carry one

**Observation** — **There is no outbound boundary, and this is a result rather than a skip.** Nothing in
`src/` initiates a connection to a host the project does not control. A search over every `.py` file in
`src/` for `httpx`, `requests`, `aiohttp`, `urllib.request`, `boto3`, `botocore`, `openai`, `anthropic`,
`smtplib`, `paramiko`, `grpc`, `websockets`, `socket.create_connection`, `AsyncClient` and `urlopen`
returns no import and no call site; the only `urllib` imports are `urllib.parse.urlparse` for DSN
parsing (`config.py:6`, `db/starter.py:15`), which performs no I/O. The only absolute URLs in the
package are RFC 7807 `type` identifiers (`utils/exceptions.py:248,277,318,336` — documentation URIs
that RFC 7807 treats as dereferenceable and that no code path fetches), the CORS default origin list
(`config.py:555-558`), and a documentation example (`models/data.py:523`). The shipped configuration
declares no outbound target: no webhook, notification or callback column exists anywhere in the model
layer, and `EmailSettings` is only a domain blocklist (`config.py:354-357`, consumed at
`auth_service.py:432`).

Given that absence, the mechanisms that *would* carry an outbound boundary were each checked for a
reached call site. Four are declared but un-reached, and all four are load-bearing on process startup:
`main.py:10-25` lists them in `REQUIRED_MODULES` and `check_dependencies()` raises `SystemExit(1)` if
any is not importable, so the deployment refuses to start without them.

| Mechanism | Declared | In `REQUIRED_MODULES` | Reached by `src/`? |
|---|---|---|---|
| `httpx` (HTTP client) | `pyproject.toml:25` | yes, `main.py:14` | **no** |
| `tenacity` (retry helper) | `pyproject.toml:35` | yes, `main.py:24` | **no** |
| `requests` (HTTP client) | `pyproject.toml:29` | no | **no** |
| `plotly` (charting, frontend-facing) | `pyproject.toml:22` | yes, `main.py:16` | **no** |
| `rq` (queue client) | `pyproject.toml:34` | yes, `main.py:23` | **no** — the app uses an in-memory `task_queue` (`app.py:129-143`) |

No circuit-breaker wrapper and no retry helper call site exist. The self-check is additionally
self-fulfilling: `check_dependencies()` reaches its verdict by calling `__import__(module_name)` on each
name (`main.py:37`), so the gate is the only thing that ever loads the libraries it certifies.

**Evidence** — The reachability test, run inside the running application image against
`import mkobi.app` (the application alone, *without* `main.py`'s `check_dependencies()`):

```
module       loaded-by-the-application-alone
aiofiles     LOADED
fastapi      LOADED
sqlalchemy   LOADED
httpx        -- never imported --
pydantic     LOADED
polars       LOADED
plotly       -- never imported --
redis        LOADED
bcrypt       LOADED
jose         LOADED
alembic      LOADED
asyncpg      LOADED
rq           -- never imported --
tenacity     -- never imported --
requests     -- never imported --
```

Loading the same modules through `mkobi.main` (which runs the gate) reports all fourteen as `LOADED`,
confirming the gate's `__import__` is the sole loader rather than the application.

**Consequence** — No runtime consequence today: every library is installed, so the process starts. The
operational consequence is that the process refuses to start on libraries it never uses, and the
startup self-check advertises an HTTP and a retry capability the system does not have. A dependency
audit or an `uv lock --upgrade` that drops any of the four produces a `SystemExit(1)` whose message
(`main.py:42-46`) names a module the codebase never touches, sending the operator to the wrong place;
and the gate passing is evidence of nothing beyond the presence of a wheel in the image.

**Recommendation** — Do not delete the libraries — per the dead-code policy, first establish intent.
`httpx` and `tenacity` read as preparation for an outbound integration that was never built; `plotly`
and `rq` are more likely residue. The smallest correct change is to reconcile `REQUIRED_MODULES` with
what the application actually imports — derived from the list in the Evidence artefact — and either
(a) reduce the list to those twelve and record the outbound capability as not implemented, or (b) if the
outbound boundary is on the roadmap, say so in `REQUIRED_MODULES`'s docstring and in `docs/`, so the
gate documents a decision rather than a residue. If the libraries are genuinely unused, remove them from
`pyproject.toml` in the same change. Investigate the intent before removing anything; this finding is
about the gate's claim, not about the libraries' existence.

**Cross-reference** — Adjacent to Phase 01 TOPO-001, which established that the deployed `rq-worker` is
inert because no `rq.Queue.enqueue` exists in `src/`. The `rq` row above is the same residue seen from
the dependency side and is listed only because it appears in the same gate; it is not re-filed.
### EXT-010 — The schema document advertises a version the package has moved past, and only the human-facing half of it is gated by tier

**Severity** — LOW

**Zone** — The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them

**Observation** — The machine-readable description is produced from the running code, not maintained
beside it: FastAPI generates `/openapi.json` from the 11 registered routers and the two health
endpoints, yielding 43 paths and 60 operations, all confirmed against the live instance. Two properties
of it are drift.

First, the version. `app.py:218` passes `version="1.0.0"` to the `FastAPI` constructor and
`config.py:320` carries the same `1.0.0`, while `pyproject.toml:4` declares `version = "1.0.8"`. The
document a consumer builds against therefore reports `1.0.0`, a value the package has moved seven patch
releases past. No other version signal exists for a consumer: no `X-API-Version` header, no `/version`
endpoint, and no reference to `1.0.8` or `API_VERSION` in `docs/` or `frontend/src/` (the only `1.0.8`
occurrences in the repository are build artefacts under `docs/STRUCT.md`). A consumer built against the
previous shape gets no signal when a field changes.

Second, the tier gate is asymmetric. `app.py:220-221` sets `docs_url=None` and `redoc_url=None` when
`config.environment == PRODUCTION`, but `openapi_url` is left at FastAPI's default `/openapi.json`.
In the production tier the human-facing surfaces are switched off and the machine-readable one is not.
Nothing in the application code closes that; it is closed by an accident of the shipped edge —
`docker/nginx/nginx.conf` forwards only `location /api` (line 34) and
`location ~ ^/health(/detailed)?$` (line 43), so `/openapi.json`, `/docs` and `/redoc` fall through to
`location /` and are served the React bundle. In the development tier the same three paths are reachable
with no credential, because the app port is published directly at `${APP_HOST_PORT:-8010}:8000`
(`docker/docker-compose.override.yml:104-108`) and `ENV=development` leaves the docs enabled — measured
at 200 for `/docs` (1004 bytes), `/redoc` (886 bytes) and `/openapi.json` (121,757 bytes).

**Evidence** — Measured against the live dev instance:

```
openapi title=mkobi version=1.0.0  pathCount=43
ANON /docs          -> 200 text/html           1004 bytes
ANON /redoc         -> 200 text/html            886 bytes
ANON /openapi.json  -> 200 application/json  121757 bytes   (60 operations, 7 anonymous)
```

Version anchors:

```
pyproject.toml:4    version = "1.0.8"
config.py:320       version: str = "1.0.0"
app.py:218          version="1.0.0",
app.py:220-221      docs_url=None / redoc_url=None  if PRODUCTION   (openapi_url not set)
```

The production-tier behaviour of `/openapi.json` is established statically from `app.py:215-223`; the
production tier was not booted in this environment (Appendix A), so the claim is that the application
code does not gate the path, not that it was observed serving in production.

**Consequence** — No runtime consequence today in the shipped production topology, where the edge
happens to withhold the path. The consequence is that the protection is a property of an nginx
`location` block rather than of the application: an operator who publishes the app port, drops the
`production` profile, or adds a proxy `location /` that forwards, silently exposes the complete
machine-readable surface — 43 paths, every model schema, every error code — with no credential, in the
tier where the code explicitly disables its two sibling surfaces. Independently, the stale `1.0.0` means
a consumer has no version with which to detect a contract change.

**Recommendation** — Two small changes. Set `openapi_url=None` alongside `docs_url` and `redoc_url` at
`app.py:220-221`, so the tier decision is made once in the place that already owns it rather than
inferred from an nginx block. And source the document's version from a single constant rather than the
literal `"1.0.0"` — reading it from the installed distribution metadata is the one option that needs no
second place to keep in sync. Neither change has a shipped test asserting the current behaviour.

## Distribution

The findings fall on two components and one configuration surface, and the concentration is on the
boundary layer rather than on any business logic. Six of the ten sit in the request/response boundary —
`src/mkobi/app.py` (health probes, version, tier gating), `src/mkobi/api/deps.py` (the revocation read
on the authentication path) and `src/mkobi/api/routes/` (client-errors, auth, admin) — and four sit on
the Redis dependency itself, the single component carrying the most. `src/mkobi/app.py` carries two
(EXT-001, EXT-010); the Redis dependency carries four (EXT-001, EXT-002, EXT-003 via the shared key,
EXT-005); the admin approval path carries two (EXT-005, EXT-008); the inbound budget carries two
(EXT-003, EXT-004); and the validation convention carries one systemic finding (EXT-007) plus the
routing-ordering finding beside it (EXT-006).

- **Redis as a critical path with undeclared failure semantics** — EXT-001, EXT-002, EXT-005, and
  EXT-003's shared key. Four findings, one component, one missing declaration.
- **The health and version surface in `app.py`** — EXT-001, EXT-010.
- **The admin approval sequence in `admin.py`** — EXT-005, EXT-008.
- **Inbound identity and volume model** — EXT-003, EXT-004, EXT-006.
- **Startup dependency gate** — EXT-009, and EXT-007 as the boundary-wide convention gap.

Nothing in this phase falls in the data pipeline, the database layer or the frontend: the boundary
defects are all in the request path and in the configuration of the dependencies that path reaches.

## Cross-Finding Analysis

Two causes are shared across findings.

**Redis is on critical paths whose reported outcome does not depend on it.** EXT-001, EXT-002 and
EXT-005 are one cause seen from three directions: the revocation read is unguarded and the probe does
not cover it (EXT-001, EXT-002), and the credential write fails open while the endpoint reports success
(EXT-005). The common defect is not any single call site — it is that no call site on this dependency
states what happens when it fails, and the application's failure reporting (health probe, HTTP status,
`AppException` code) was written for the database dependency and never extended to the second one. A
single review of "what happens when Redis is unavailable" across `deps.py`, `app.py`, `security.py` and
`temp_password_store.py` closes all three, which is why they are grouped in the roadmap rather than
scheduled as three independent tickets. EXT-008 is a fourth Redis finding but a *different* cause
(write ordering, not failure semantics) and is deliberately not folded in.

**The boundary's identity and volume model was derived for a directly-exposed process and never
re-derived for the shipped topology.** EXT-004 because the caller is collapsed to the proxy's address,
EXT-003 because the volume bound that depends on that address is therefore a shared pool, and EXT-006
because the routing layer answers before the layer that would have identified the caller. Stated once
rather than three times: the `forwarded-allow-ips` change in EXT-004 is a prerequisite for reasoning
about the other two correctly.

EXT-001, EXT-007, EXT-009 and EXT-010 share no cause with any other finding or with each other, and are
independent of the two groups above.

## Roadmap

Grouped by cause rather than by severity, since the two shared causes carry most of the weight.

**Step 1 — Decide and declare what happens when Redis is unavailable. Closes EXT-001, EXT-002, EXT-005.**
Do this as one change, because the three findings are one omission: the failure semantics of the second
critical dependency were never written down. Declare an explicit `socket_timeout` /
`socket_connect_timeout` and disable the implicit retry in `core/redis_client.py` so the per-request
cost belongs to this project; add a `ping` component to `/health` and `/health/detailed`; add a 503-mapped
`ErrorCode` and use it at the two revocation reads in `deps.py`; make `TempPasswordStore.store` report
failure and have the approve path in `admin.py` refuse before `db.commit()`. **Before starting:** confirm
the intended posture, because the two defensible answers differ — fail-closed (refuse, lose
availability, lose no credential) or fail-open on the *read* path only (serve, and accept that revocation
cannot be enforced during the outage). The recommendation above assumes fail-closed on the credential
write and a distinct 503 on the revocation read; the lead should confirm that before coding, because
`tests/test_auth.py:328,365` encode fail-*open* expectations for the rate limiter and the same reasoning
does not transfer to a credential write. **Done when:** the paused-Redis probe in EXT-001 returns
non-200 from `/health`, a 503 (not a 401) from `/auth/me`, and a per-request latency in the seconds
rather than tens of seconds.

**Step 2 — Restore per-caller identity at the edge. Closes EXT-004; unblocks correct reasoning on EXT-003.**
Pass `--forwarded-allow-ips` covering the compose bridge subnet in `docker/Dockerfile:179` and in the dev
command in `docker-compose.override.yml:109`. **Before starting:** decide whether the two authentication
budgets should additionally be keyed on a principal rather than an address, since restoring the address
still leaves one address able to spend the whole budget. **Done when:** the reproduction in EXT-004
produces N distinct Redis keys for N distinct `X-Forwarded-For` values, and the budget table in that
finding is re-derived from the resulting key composition.

**Step 3 — Bound what an anonymous caller can write. Closes EXT-003; depends on Step 2 for its volume
half.** Truncate and constrain the `client-errors` fields before the log call, narrow
`ClientErrorPayload.error` to the fields actually read, and add the `Content-Length` pre-check.
**Before starting:** Step 2, because the 100/hour bound is a shared pool until the address is
meaningful — capping the fields without restoring the address leaves the aggregate volume unbounded in
practice. **Done when:** a 5 MB anonymous body is refused at the boundary and no log record exceeds the
chosen per-field cap.

**Step 4 — Make the approval sequence commit-then-publish. Closes EXT-008.** Move the
`temp_password_store.store` call after `db.commit()` in `admin.py` and add the compensating delete on
failure; mirror it in `auth_service.py`. **Before starting:** Step 1, so the store's failure contract is
already decided rather than re-litigated. **Done when:** a test that fails the commit asserts no
`temp_pwd:*` key remains.

**Step 5 — Make the validation convention executable. Closes EXT-007.** Introduce one strict
request-model base, migrate the 21 request-body models onto it, document it (and either justify or drop
the single `extra="forbid"` exception), then model the two deferred boundaries — the `filters` query
document and the graph `config` document. **Before starting:** nothing; this step is independent and can
run in parallel with Steps 1-4. Expect it to surface client-side 422s that are genuine defects, so
schedule it with the frontend owner rather than as a silent backend change. **Done when:** a wrong field
name returns 422 on every write route.

**Step 6 — Align the served path with the declared path. Closes EXT-006.** Register the collection
routes so the shape in the description is the shape the router matches, and drop or relativise the
redirect. **Before starting:** Step 7, so the path-shape decision is made once. **Done when:**
`GET /api/v1/dashboards` returns 401 rather than 307.

**Step 7 — Make the tier decision in one place. Closes EXT-010.** Set `openapi_url` alongside the other
two URLs at `app.py:220-221` and source the document version from a single constant. **Before starting:**
nothing. Trivial; group it with any other `app.py` touch to avoid two edits to the same constructor.
**Done when:** `/openapi.json` returns 404 in the production tier and reports a version matching
`pyproject.toml`.

**Step 8 — Reconcile the startup gate. Closes EXT-009.** Investigate whether the four libraries are
planned (outbound integration) or residue, then either reduce `REQUIRED_MODULES` to what the application
imports or document the intent. **Before starting:** nothing, but it is the lowest-priority item and
should not block Steps 1-7. **Done when:** every name in `REQUIRED_MODULES` appears in the
loaded-by-the-application list from EXT-009's evidence artefact, or is removed from the gate.

## Rollout Safety

Steps 2, 3, 5 and 6 change observable behaviour, and two of them can surface errors that are currently
invisible. **Step 5 is the one to sequence carefully:** turning `extra="ignore"` into `extra="forbid"`
on 21 request bodies will convert currently-silent field drops into 422s. Any client that is today
sending a field the server does not recognise — including a renamed field it believes is being saved —
will start receiving errors. This is the correct outcome, but it will look like a regression if it
lands without the frontend owner. Roll it out model class by model class behind the existing test
suite, and expect the write routes (`DashboardCreate`/`Update`, `UserCreateRequest`, `FilterBase`,
`GraphBase`, `LayoutBase`, `ProcessingConfig*`) to be where the first 422 appears. Revert is a revert of
the base class; no stored data changes.

**Step 2 is a one-line change with a wide blast radius and should be the first thing verified after
deploy.** Setting `--forwarded-allow-ips` changes the key under every IP-keyed rate limit, so every
existing counter's identity changes at once: counters accumulated under the collapsed key are abandoned
rather than migrated, which is harmless (they are short-TTL integers), but the *effective* budget for
each caller rises from a shared 3 or 5 to a per-caller 3 or 5. That is the intent. The risk is the
opposite: if the allow-list is set too broadly (notably `*`), a caller can rotate `X-Forwarded-For` and
get a fresh budget per request, which converts a rate limit into no rate limit. Verify with the EXT-004
reproduction immediately after deploy, and scope the allow-list to the compose network subnet rather
than `*`. Phase 04 AUTH-001 must be closed by this same change; the two should not ship separately.

**Step 1 is backwards-compatible in shape but changes status codes.** Callers currently receiving
`401 AUTHENTICATION_FAILED` during a Redis outage will receive a 503 instead. That is the point, but any
client that branches on 401 to trigger a token refresh will stop doing so during an outage — which is
correct, since the refresh endpoint depends on the same Redis. The rate limiter's fail-closed direction
(`tests/test_auth.py:365`) is unaffected and must not be changed to match. The 58 s → seconds latency
change is the one most likely to be noticed: it will alter measured request timings in Phase 11's
latency baselines, so re-baseline after this step rather than treating the shift as a regression.

## Appendices

### Appendix A — Block coverage record

Every block was executed. Blocks with no finding are recorded here as coverage, not omitted.

| Block | Method | Artefact | Outcome |
|---|---|---|---|
| 1 — outbound boundary | static search of all 68 `.py` files in `src/` for 15 client/socket mechanisms; module-load probe in the live image; read of `pyproject.toml`, `main.py`, `docker-compose.yml`, `Dockerfile`, `nginx.conf` | EXT-009 evidence; Appendix B | Outbound boundary **does not exist** — recorded as a result. 4 declared mechanisms un-reached, all startup-gated → EXT-009 |
| 2 — derived dependency set | derived from call sites (DB, Redis, temp filesystem, static bundle, RQ), not from docs; live outage probe with Redis paused; per-dependency latency measured before and during | EXT-001, EXT-002 evidence | PostgreSQL + Redis are the two request-path preconditions; Redis failure is total and undeclared → EXT-001, EXT-002 |
| 3 — guard failure direction | read of `security.py:58-152`; enumeration of all 6 `RateLimiter`/`AsyncRateLimiter` construction sites; read of `config.py:461` | Appendix C | Direction is a **declared value**, not a hard-coded branch; code default is fail-closed (`True`); all 5 production call sites pass it. No finding. (The sync `RateLimiter` class is unconstructed — residue, filed as part of the Block-1 gate finding rather than as a guard defect) |
| 4 — aggregate ingress budget | derived the 5-bound inventory from call sites; derived process/replica counts from `Dockerfile:179` and `docker-compose.yml`; reproduced the collapse with a forwarding container on `mkobi_default` | EXT-004 evidence | Counters are Redis-backed and therefore **shared across all 4 workers** (no per-process multiplication). Four of five keys collapse to the proxy address → EXT-004 |
| 5 — degraded vs real result | enumerated every fallback and default on the request path; live probe of the approve path under a write-only Redis failure; live probe of both health endpoints under a full Redis outage | EXT-001, EXT-005 evidence | Health probe blind to Redis → EXT-001; approve returns a dead retrieval handle → EXT-005 |
| 6 — batch isolation and record/effect order | static ordering trace of the 6-step approval; live probe of `/auth/logout` under a Redis outage; read of the atomic read side | EXT-008 evidence | Redis write precedes its commit with no compensation → EXT-008. Logout verified **not** defective (auth dependency fails first) — negative result recorded |
| 7 — inbound surface | derived the surface from the live `/openapi.json` (43 paths / 60 operations), cross-checked against `app.py` router registration; credential requirement read per operation from the generated `security`; refusal bodies captured for 8 paths incl. a caller-chosen `Host`; production edge read from `nginx.conf` | EXT-006, EXT-010 evidence; Appendix D | 7 anonymous operations; 307-before-auth on the collection routes → EXT-006; version and tier-gate drift → EXT-010 |
| 8 — validation convention | enumerated all 112 classes in `src/mkobi/models/` (64 `BaseModel`, 18 `TypedDict`, 18 `Enum`, plus 12 others); searched for every `extra` policy form; traced the two deferred boundaries; searched `docs/` for a documented convention | EXT-007 evidence | 0 of 21 request-body models declare an `extra` policy; no base to inherit; 2 boundaries validate after acceptance |
| 9 — untrusted body as logged | read the anonymous sink and its model; live probe with a newline/credential payload; live probe with a 5,000,073-byte body; measured the resulting log record; read the production log destination | EXT-003 evidence | Body written verbatim at ERROR with no field cap; newlines correctly escaped (passing check, not filed); 5 MB → 5,000,304-char record |

### Appendix B — Outbound-call inventory

Search expression, applied to every `.py` file under `src/`:

```
httpx | requests | aiohttp | urllib | boto3 | botocore | openai | anthropic
smtplib | paramiko | grpc | websockets | socket.create_connection | AsyncClient | urlopen
```

**Result: zero import or call sites.** The 35 textual matches are all false positives — the word
`requests` inside `registration_request(s)` identifiers and docstrings
(`admin.py:247-349`, `db/models/registration_request.py:35-36`, `db/repositories/registration_request_repo.py:171-189`,
`models/…`, `auth.py:8`), and `urllib.parse.urlparse` at `config.py:6` and `db/starter.py:15`, which
parses a DSN and performs no I/O.

Second pass, absolute URLs in `src/`: 11 occurrences, all non-fetching.

| Location | String | Nature |
|---|---|---|
| `utils/exceptions.py:248,318` | `https://api.mkobi.com/errors/{code}` | RFC 7807 `type` identifier |
| `utils/exceptions.py:277,336` | `…/validation_error`, `…/internal_error` | RFC 7807 `type` identifier |
| `models/error_response.py:37` | `…/not_found` | OpenAPI example |
| `config.py:555-557` | `http://localhost:3000/5173`, `https://example.com` | CORS origin defaults |
| `config.py:558` | `https://your-domain.com` | CORS origin placeholder |
| `models/data.py:523` | `https://app.example.com/dashboard/123` | OpenAPI example |

No webhook, notification, callback or egress column exists in any model (`db/models/*.py`), and
`EmailSettings` (`config.py:354-357`) is a domain blocklist only, consumed at
`auth_service.py:432`. Mechanism-by-mechanism verdicts are in EXT-009's table.

### Appendix C — Rate-limit guard verdicts (Block 3)

| Guard | Counter store | Failure direction | Chosen by | Same setting on every surface? |
|---|---|---|---|---|
| `AsyncRateLimiter.check_rate_limit` (`security.py:111-151`) | Redis | **Refuses** when `fail_closed=True` (returns `False, ttl`); permits when `False` | **Declared value** — `config.rate_limiter_fail_closed`, `config.py:461`, code default `True` | Yes — all 5 production call sites pass `fail_closed=config.rate_limiter_fail_closed` explicitly |
| `RateLimiter.check_rate_limit` (sync, `security.py:63-103`) | Redis | Same branch, class default `fail_closed=False` | Declared value, but **no production call site** — unconstructed residue | n/a |
| `is_token_revoked` / `is_user_tokens_revoked` / `is_refresh_token_revoked` (`security.py:492-519`) | Redis | **Raises** — no guard at all; converted to 401 by the catch-all at `deps.py:570` | No declared value; no branch | Yes — but the direction is not a decision (see EXT-002) |
| `TempPasswordStore.store` (`temp_password_store.py:30-48`) | Redis | **Permits** — swallows and logs, returns `None` | Hard-coded branch, documented as intent in the docstring | Single call path (two sites) |
| `TempPasswordStore.retrieve` (`temp_password_store.py:50-75`) | Redis | **Permits** — returns `None`, which the endpoint reports as 404 "already retrieved" | Hard-coded branch | Single call path |

The two guards the block asks about behave as designed and as documented; the three that do *not* go
through a guard are filed as EXT-002 and EXT-005 rather than here, since the block's own scope
excludes the identity a bound is keyed on (04) and the composition of each key (10).

### Appendix D — Inbound surface and refusal matrix (Block 7)

Derived from the live `/openapi.json`, cross-checked against `app.py:245-255` and `app.py:257-316`.
60 operations across 43 paths; 7 anonymous, 53 credential-required.

| Surface | Operations | Credential | Refusal on no credential | Discloses on refusal |
|---|---|---|---|---|
| `/api/v1/auth/login`, `/login/form` | 2 | none | n/a (public by design) | `401 AUTHENTICATION_FAILED "Invalid credentials"` — same body for unknown-email and wrong-password (enumeration-safe) |
| `/api/v1/auth/refresh` | 1 | cookie only | `401 AUTHENTICATION_FAILED "Refresh token not found"` | Distinguishes "no cookie" from "bad token" by `detail` |
| `/api/v1/auth/register-request` | 1 | none | `422 VALIDATION_ERROR`, or `429 RATE_LIMIT_EXCEEDED` | Rate-limit key identity leaks via the `ip` field in the log, not the response |
| `/api/v1/client-errors` | 1 | none | `429 RATE_LIMIT_EXCEEDED` with `Retry-After` | Nothing beyond the rate-limit class |
| `/health` | 1 | none | never refuses | `{"status","database"}` |
| `/health/detailed` | 1 | none | never refuses (returns 200 with `"status":"unhealthy"` on DB failure) | Component map, `type: postgresql`, static path, and on DB failure `error: str(e)` — documented at `docs/05-health/health-api.md:172` |
| `/openapi.json`, `/docs`, `/redoc` | 3 | none (non-production) | n/a | Complete schema: 43 paths, 121,757 bytes |
| Collection routes, slash-less spelling | — | none | **`307` before any credential check** | `Location` built from the caller's `Host` |
| All other 53 operations | 53 | bearer | `401 AUTHENTICATION_FAILED "Not authenticated"` (FastAPI `HTTPBearer` auto-error) | Nothing |

`/health/detailed` was **not** filed for its `error: str(e)` disclosure: the behaviour is documented at
`docs/05-health/health-api.md:172` ("the exception message is included in the detailed health check
response and logged server-side at ERROR level") and the block's own instruction is that design
deliberately asymmetric between surfaces is not a defect on its own — report it only where the code's own
documentation misstates it. The documentation and the code agree here.

### Appendix E — Environment, baseline and limits on this report

**Baseline.** `git rev-parse HEAD` → `c3c0a61bf41cad68bf3a3ac105de91ea63c82268`;
`git status --porcelain` recorded four modified tracked files
(`src/mkobi/config.py`, `src/mkobi/db/starter.py`, `tests/test_config.py`, `tests/test_starter.py`)
plus deletions under `.ai/builders`, `.ai/structure`, `.ai/models`, `.ai/templates` and `.ai/plans`.
Re-verified identical at the end of the phase. No file was edited, staged, committed, reverted or
stashed; all probe artefacts created by this phase were removed, and the working tree shows the four
baseline modifications and no trace of this phase's work. One untracked file,
`_b3_full_out.txt` (117,185 bytes, created 15:07:55, containing captured `mkobi-test` compose output),
appeared during the phase and is **not** an artefact of this audit — it belongs to the concurrent
remediation programme's B3 item. It was left untouched.

**Concurrent-edit check.** `src/mkobi/config.py` was dirty at baseline and is read as an authority by
EXT-002 (Redis client construction, `core/redis_client.py`, unaffected) and by the rate-limit direction
verdict in Appendix C. Every anchor this phase depends on in that file lies **outside** the concurrently
modified hunks — `git diff -U0 src/mkobi/config.py` reports hunks at `@@ -80,0 +81,48`,
`@@ -444,9 +492,10`, `@@ -454,2 +503,2` and `@@ -458,15 +507,15`, while the anchors sit at working-tree
lines 307-310 (`RedisSettings`), 334 (`UploadSettings.max_file_size_mb`), 461
(`rate_limiter_fail_closed: bool = Field(default=True, …)`) and 856 (`max_file_size`) — re-read after
the diff and unchanged in value. `src/mkobi/db/starter.py` was read only for the outbound-call
inventory (`urllib.parse` import at line 15) and is not an authority for any finding. The configuration
state observed at runtime (`ENV=development`, `RATE_LIMITER_FAIL_CLOSED` at its code default `True`)
reflects the dev override, in which the variable is not supplied.

**Runtime environment.** `.\Makefile.ps1 up` brought up `db`, `migrate` (exited 0), `app`, `redis`,
`rq-worker` and `frontend`. Probes were issued from the Windows host against the published
`${APP_HOST_PORT:-8010}` and, for the XFF reproduction, from a container on `mkobi_default` to match the
position nginx occupies in production. All state was restored and verified: Redis returned to
`+@all` (`ACL WHOAMI -> default`), the probe container `mkobi-xffprobe` was removed, `POST
/api/v1/auth/login` and `GET /api/v1/auth/me` returned 200 in 0.028 s, and `/health` returned
`{"status":"healthy","database":"connected"}`.

**What could not be verified here, and why.**

- *The production tier was not booted.* It requires a prior `npm run build` for `frontend/dist` and a
  complete set of production-grade secrets. Consequences: EXT-010's claim about `/openapi.json` in the
  production tier is a static reading of `app.py:215-223` plus a reading of the shipped `nginx.conf`,
  not an observed production response; and the production `RATE_LIMITER_FAIL_CLOSED` value could not be
  read from a live container (the compose default `true` at `docker-compose.yml:127` and the code
  default `True` at `config.py:461` both point fail-closed, and the guard verdict in Appendix C does not
  turn on which of the two applies).
- *No TLS, certificate or external-intermediary behaviour was exercised.* EXT-004's reproduction uses a
  plain HTTP forwarder, which is sufficient because the defect is in the app's trust decision for the
  proxy header, not in transport security.
- *Throughput under sustained load was not measured.* EXT-002's consequence notes that 58 s per request
  across 4 workers implies worker exhaustion; the exhaustion itself is a reasoned projection from the
  measured per-request latency, not a measured saturation point. Phase 11 owns that measurement.
- *The write-only Redis failure in EXT-005 was induced with an ACL on the `default` user rather than by
  removing the service.* This was chosen so the authentication dependency's reads continue to work and
  the approve path is reachable; the resulting fail-open is identical in kind to a `SET` failing on a
  full or read-only replica. The full-outage variant of the same path could not be reached, because
  `get_current_user_dependency` fails first (recorded as a negative result under Block 6).
- *The test suite was not run.* No shipped test asserts any of the ten behaviours, so no finding in this
  phase has a test that encodes the defect; that is stated per finding rather than verified by reading
  every test, and the named candidates (`tests/test_rate_limiting.py:203-243`,
  `tests/test_auth.py:270-376`) were read and confirmed to construct their dependencies directly, which
  is why they cannot detect the collapse or the outage behaviour.
