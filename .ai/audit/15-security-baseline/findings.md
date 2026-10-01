---
phase: 15-security-baseline
executed: 2026-10-01
executor: auditor
problems-only: true
baseline: 9c49c204ad83b26b2b76cf6887c48ad09f79d055
baseline-dirty: "65 lines in git status --porcelain (concurrent remediation programme in flight; frontend/coverage/ deletions pre-existing and untouched)"
findings: 9
by-severity:
  CRITICAL: 0
  HIGH: 4
  MEDIUM: 4
  LOW: 1
---

# Phase 15 — Security Baseline

## Summary

All eight blocks were executed. The zone examined is the cross-cutting security baseline: what each credential is at rest and under what policy, what credential material reaches any other sink, which inbound surfaces carry an attempt bound, what an unauthenticated caller can reach, what untrusted structure may select, what an undecided failure discloses, and which headers this process itself emits. Seven findings were reproduced at runtime against the unmodified modules and application (`TestClient` on the real `create_app()` output); no Docker service was started or reconfigured. The most consequential finding is SEC-005: a mismatch in a password-change confirmation — an ordinary typo — writes the user's current working password and intended new password in cleartext into `/app/data/logs/app.log` and its rotated backups, and echoes both back in the 422 body, because the shared validation-error handler copies Pydantic's `input` dict verbatim into both the log record and the response. That same "copy the internal value out" habit produces SEC-006 (the database role name, from `str(e)`, to an unauthenticated caller on `/health/detailed`), SEC-008 (a container upload path and a Redis endpoint persisted into `processing_logs.message` and served back as `filename`), and the two-thirds of SEC-003's substance: all five rate-limit counters are keyed on a caller-supplied `X-Forwarded-For` entry, so the bound exists in configuration and decides nothing. Reconciling the question the coordinator flagged — the limiter is **fail-closed in the settings and fail-open in the class**, the two disagree, `RATE_LIMITER_FAIL_CLOSED` reaches production but is absent from the dev overlay, and the live posture is fail-closed only because five call sites remember to pass a flag the constructor defaults the other way. SEC-002 answers the question no prior phase asked: the delegated credential is stored in Redis **as the credential itself**, not a derivation, in an instance with no `requirepass`, no TLS and no ACL, so it is recoverable in the clear by anything that reaches `redis:6379` for up to 24 hours.

## Findings

### SEC-001 — Passwords longer than 72 bytes are silently aliased to their first 72 bytes, so a credential change can leave the previous password usable

**Severity** — MEDIUM

**Zone** — 1. The Stored Password: Encoding, Parameters, and the Policy Around It

**Observation** — The stored record is bcrypt at cost 12 (`SALT_ROUNDS: int = 12`, `src/mkobi/core/security.py:37`), returned as a 60-character `$2b$12$…` string and held in `users.password_hash String(255)` (`src/mkobi/db/models/user.py:46-49`) — encoding and column width are correct. The minimum-length policy is 8 characters plus one digit plus one ASCII letter (`validate_password_or_raise`, `src/mkobi/utils/validators.py:183-205`), applied on `RegisterRequest.password` (`src/mkobi/models/auth.py:114-119`) and `ChangePasswordRequest.new_password` (`:203-208`) and again inside `register_user` (`src/mkobi/services/auth_service.py:151`). Changing a credential does require the current one: `change_password` verifies `verify_password(current_password, user_obj.password_hash)` before writing (`auth_service.py:498-503`), and the comparison is a single `bcrypt.checkpw` so its cost does not depend on how much of the input matches. **No maximum accepted input length exists anywhere.** No Pydantic field declares `max_length` on any password field (`LoginRequest.password`, `RegisterRequest.password`, `ChangePasswordRequest.current_password` / `new_password` are all bare `str`), and `validate_password_or_raise` checks only a lower bound. Instead of rejecting over-length input, `_truncate_password` (`security.py:154-187`) drops everything past 72 **bytes** at a character boundary and emits only a `logger.warning` — the caller receives HTTP 201 and has no signal that the tail of their new password was discarded. The same truncation is applied identically on the verification side, so the aliasing is symmetric and stable.

**Evidence** — Executed against the real `hash_password` / `verify_password` at this baseline:

```
orig len bytes 100
trunc len bytes 72
hash prefix $2b$12$ len 60
verify long vs short-truncated-hash: True
verify long+DIFFERENT-tail (y) vs same hash: True
```

A 100-byte password and a *different* 100-byte password sharing only its first 72 bytes produce the same accepted credential. `_truncate_password` is the sole length handling, and no schema field constrains length. Phase 04's 40-sample timing work established that the dummy-hash comparison is cost-uniform; that property holds here and is not re-litigated — the length cap, which no prior phase examined, is absent.

**Consequence** — A user who sets a 72+ byte password (passphrase, password-manager generated, or any long phrase) believes they have established a credential with entropy past byte 72. In reality every string sharing their first 72 bytes is an equally valid credential for the account, and the change endpoint's `current_password != new_password` check (`auth_service.py:505`) does not notice the collision — a "change" that appends or edits only the tail is accepted and reported as success while leaving the prior secret working. The 72-byte tail of every long credential is dead weight that the user has no way to observe is being discarded, and any future hash-migration that lifts the limit will silently split these accounts' credentials.

**Recommendation** — Bound the field, not the hash: declare `max_length=72` (in bytes — `max_length=72` on a `str` counts characters, so use a `field_validator` that rejects anything whose UTF-8 encoding exceeds 72 bytes) on `RegisterRequest.password`, `ChangePasswordRequest.new_password`, and `LoginRequest.password`/`current_password`, raising through the existing `validate_password_or_raise` so the refusal is an RFC 7807 `AppException`. Then change `_truncate_password` from truncate-and-warn to raise, so a caller can never reach `hash_password` with an input that will be silently shortened. If long passphrases are a product requirement, the correct route is changing the KDF (Argon2id / scrypt, no 72-byte ceiling), not restoring the truncation. Grep for shipped tests asserting the truncation warning before changing it — `tests/` coverage of `_truncate_password` asserts the current behaviour and must change with the fix.
### SEC-002 — Delegated credentials are stored in Redis as the credential itself, so anything that reaches the store recovers every outstanding password in the clear

**Severity** — HIGH

**Zone** — 2. Short-Lived Credentials Handed to Another Person: the Store, the Lifetime, the Retrieval

**Observation** — Two surfaces mint a credential for someone who is not the account holder: `AuthService.reset_password_admin` (`src/mkobi/services/auth_service.py:577-583`) and `approve_registration_request_admin_endpoint` (`src/mkobi/api\routes\admin.py:306-321`). Both generate a 16-char password from `secrets.choice` (`_generate_temp_password`, `auth_service.py:521-538` — generator quality is fine, ~95 bits), hash it into `users.password_hash`, and then store **the plaintext** into Redis under `temp_pwd:<uuid4>` with `SET key password EX 86400` (`src\mkobi\core\temp_password_store.py:39-48`, TTL from `TEMP_PASSWORD_TTL_SECONDS`, default 86400). **The stored form is the credential itself, not a derivation of it** — no hash, no AEAD, no envelope key. It is recoverable in the clear from the store that holds it by any principal with read access to Redis: `GET temp_pwd:<token>` returns the working password for the account, and `KEYS temp_pwd:*` enumerates every outstanding one. Redis in this deployment is `redis:7.4-alpine` with a `redis_data` volume and **no `requirepass`, no TLS and no ACL** (`docker/docker-compose.yml:171-176` — the service body sets only `volumes`, `restart`, `healthcheck`, `deploy`), so the RDB on that volume and anything with network reach to `redis:6379` on the compose bridge reads every delegated credential in the deployment at once. `retrieve` does GET+DELETE atomically in one pipeline (`temp_password_store.py:63-66`), so the *store's own API* is single-read; the recoverability is entirely a property of the stored encoding, not of the read path. Recovery is **indefinite within the 24 h TTL** and the value survives a process restart because it is server state, not process memory. Registration requests take this identical path — phase 12's `registration_requests` approval mints through `admin.py:320-321`, so a freshly approved user and a freshly reset user are the same exposure.

Consequence for the store's own defects is deferred and already filed: the fail-open write (`temp_password_store.py:47-48`, asserted by `tests/core/test_temp_password_store.py:164-181`) is phase 04's AUTH-002, and the single-404 collapse across spent / never-existed / store-down is AUTH-006. What is new here is the encoding, which neither owns.

**Evidence** — `TempPasswordStore.store` at `core/temp_password_store.py:41` passes `password` (the plaintext) as the Redis *value*; the only transformation anywhere on this path is `hash_password(temp_password)` at `auth_service.py:579`, whose output goes to PostgreSQL and is never related to the Redis value. `docker/docker-compose.yml:171-176` shows the redis service with no auth directive. `redis_data:/data` is a named volume, so the credential is on disk in RDB form for the life of the volume. Static proof is sufficient here: the value written and the value needed to authenticate are the same bytes.

**Consequence** — Any principal who reaches Redis — a compromised `rq-worker` or `app` container (both hold a live client by construction), a snapshot of the `redis_data` volume, or anyone with bridge-network access — reads the plaintext password for every account that has been reset or approved and not yet claimed, in one `KEYS` call, up to 24 hours old. Because these are the *only* copy (the user never receives them; delivery is out of band through the retrieval token), this is the sole point at which the credential exists outside the account holder, and the store is where it lives for a full day. Redis also holds the token blacklist and the reconciler lease on the same instance, so this is not a segregated store.

**Recommendation** — Store a derivation, not the credential, and make retrieval the only way to learn it. The retrieval path is already token-keyed and single-read, so the shape that removes the effect without changing the API is: keep a per-token random key in the store (`temp_pwd:key:<uuid4>`), return **the key** from the store to the admin as today, and keep the password itself only in memory on the issuing process until it is claimed; a retrieval that misses the store then fails loudly rather than returning a value nobody can reconstruct. If the value must remain server-side (surviving a restart between mint and claim), encrypt it with an AEAD key sourced from the same `_FILE` secret mechanism as `JWT__SECRET_KEY` — `Fernet` over the plaintext is sufficient here, since the requirement is only that a Redis-only reader learns nothing. Independently: add `requirepass` and a dedicated ACL user to the redis service definition, and put the two auth token blacklists on their own keyspace database from the reconciler lease, so one read does not yield both. Tests asserting that `store()` followed by `retrieve()` round-trips a plaintext will have to change; the retrieval contract the tests actually care about — one read, then gone — can be preserved.

### SEC-003 — The rate limiter is wired to five surfaces, keys on a caller-controlled address, and its fail-closed posture is a class default that the settings default contradicts

**Severity** — HIGH

**Zone** — 4. Attempt-Rate Bounding: Which Surfaces Carry One at All

**Observation** — Reconciling phase 07's "direction is declared and defaults fail-closed, wired on all five surfaces" against phase 09's "the fail-open default is owned by no phase": **the posture is fail-closed in the settings and fail-open in the class, and the two disagree.** `config.py:578` declares `rate_limiter_fail_closed: bool = Field(default=True)` — fail-closed — and every one of the five construction sites passes it explicitly (`auth.py:86`, `auth.py:312`, `auth.py:564`, `client_errors.py:47`, `upload.py:146`). The `AsyncRateLimiter` constructor itself still defaults `fail_closed: bool = False` (`core/security.py:107`), and on the Redis-error path `security.py:137-151` returns `True, None` (admit) unless that flag was passed. So the direction that actually decides is correct everywhere today, but it is decided by five call sites remembering to pass a flag, and the constructor's own default is the unsafe value. `RATE_LIMITER_FAIL_CLOSED` reaches production through `docker/docker-compose.yml:142` and `:236` (`${RATE_LIMITER_FAIL_CLOSED:-true}`) and `docker/.env.production:49`; **it is absent from `docker/docker-compose.override.yml` entirely**, so the dev overlay resolves it from the `Field(default=True)` rather than from the environment. That is currently the same answer, which is why it has not been noticed — but the dev overlay is the deployment where a limiter regression is least likely to be caught.

Keying: all five sites key on the address string, never on an account. `login:{client_ip}` (`auth.py:89`), `refresh:{client_ip}` (`auth.py:314`), `register-request:{client_ip}` (`auth.py:566`), `client-errors:{client_ip}` (`client_errors.py:49`), `upload:{current_user.id}` (`upload.py:149` — the only site keyed on an identity, and it is authenticated). `client_ip` is `request.client.host`, which is uvicorn's **proxy-header** value, not the TCP peer: uvicorn's default `--proxy-headers` is on and its `ProxyHeadersMiddleware` returns the **left-most** `X-Forwarded-For` entry when `--forwarded-allow-ips` matches — and the app is launched with no such flag at all (`Dockerfile:127`, `Dockerfile:183`, `docker-compose.override.yml:119` pass only `--host`/`--port`/`--workers`/`--reload`). nginx appends rather than overwrites (`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`, `docker/nginx/nginx.conf:38`), so the left-most entry is whatever the caller sent. **The caller therefore chooses the key**, which makes the counter per-callable: appending a fresh left-most entry per request yields a fresh bucket per request. This is phase 04's AUTH-001 and phase 07's measured `register-request:172.21.0.7`-for-five-callers instance; it is cited, not re-filed. The reason it is graded here: the property this phase owns is *that the surface is bounded at all*, and a bound keyed on a caller-supplied string does not bound a caller.

Surfaces with **no bound reaching them**, derived from the route inventory rather than assumed:

| Surface | Method | Auth | Bound |
|---|---|---|---|
| `/api/v1/auth/login`, `/login/form` | POST | none | 5 / 300 s, key `login:<addr>` |
| `/api/v1/auth/register-request` | POST | none | 3 / 3600 s, key `register-request:<addr>` |
| `/api/v1/client-errors` | POST | none | 100 / 3600 s, key `client-errors:<addr>` |
| `/api/v1/upload/{dashboard_id}` | POST | editor+ | 100 / 3600 s, key `upload:<user_id>` |
| `/api/v1/auth/refresh` | POST | cookie | 10 / 300 s, key `refresh:<addr>` |
| `/health`, `/health/detailed` | GET | none | **none** |
| `/api/v1/auth/register` | POST | admin | **none** |
| `/api/v1/*` CRUD (dashboards, graphs, layouts, filters, processing-configs, access, users) | * | session | **none** |
| SPA static mount `/` | GET | none | **none** |

The two health surfaces and `/auth/register` are the ones worth naming. `/health` and `/health/detailed` (`app.py:277`, `:298`) declare no dependency and execute `SELECT 1` against PostgreSQL plus an `os.path.isdir` on every call, so they are an unauthenticated, unbounded database-query surface; phase 07 established both return 200 with Redis paused, and phase 10 owns the contract. `/auth/register` is admin-gated so its absence of a bound is an availability note rather than a credential one, but it is the one surface that creates a `users` row and it has no bound at all.

**Evidence** — Five `AsyncRateLimiter(...)` construction sites, confirmed by grep across `src/` (`auth.py:84,310,562`, `client_errors.py:45`, `upload.py:144`) plus one dead instance in `auth_service.py:66` that is constructed and never called — `self._rate_limiter` has no reader anywhere in `auth_service.py`. `docker/docker-compose.override.yml` has no `RATE_LIMITER_FAIL_CLOSED` key (grep over the file returns nothing; only the production `docker-compose.yml` and `.env.production` carry it). No `--forwarded-allow-ips` or `--proxy-headers` argument exists in any launch command.

**Consequence** — Two effects stand today. First, the five counters are per-callable, not per-caller, so the bound exists in configuration and decides nothing against a caller who varies the header — the login bound is exactly as drivable as if it were absent. Second, the fail-closed posture that makes Redis outage safe is a constructor argument passed at five call sites over a class whose default is the opposite; the sixth site (`auth_service.py:66`) demonstrates the pattern is not enforced, and the dev overlay shows the environment variable is not part of the dev contract even though the currently-resolved value happens to match production. A future limiter added without the flag fails open, silently, in exactly the outage the flag exists for.

**Recommendation** — Three separable changes, smallest first. (1) Remove the fail-open possibility from the constructor: make `fail_closed` a required keyword argument, or invert it to `admit_on_redis_error: bool = False`, so an omitted argument cannot mean "admit". Delete the unused `AuthService._rate_limiter` rather than fixing it. (2) Key on something the caller does not supply: since `request.client.host` is a proxy-header value here, either pass `--forwarded-allow-ips` explicitly with the proxy's own address (never `*` — that would let a direct caller forge the header and make the brute-force bypass explicit), or, better, resolve the peer address from `scope["client"]` before any header middleware has touched it. The counter may stay keyed on IP alone; it just has to be the real IP. (3) Add `RATE_LIMITER_FAIL_CLOSED: "${RATE_LIMITER_FAIL_CLOSED:-true}"` to the dev overlay's app service so the two deployments resolve the posture from the same declared source rather than from a class default. Note the constraint on (2): a `forwarded-allow-ips="*"` fix is a **bypass, not a fix** — it would make every caller able to pick its own bucket.

---

### SEC-004 — `GraphConfigDict` is a `total=False` TypedDict used as a Pydantic field type, so undeclared chart keys are silently discarded at the boundary instead of refused

**Severity** — MEDIUM

**Zone** — 6. Untrusted Structure That Selects What Is Read

**Observation** — `GraphConfigDict` (`src/mkobi/models/types.py:138-152`) is a `TypedDict` with `total=False`, used as the annotation of `GraphBase.config`, `GraphCreate.config` and `GraphUpdate.config` (`src/mkobi/models/graph.py:15,45`). Pydantic validates a `TypedDict` by checking the keys it declares and **ignores everything else**; it does not apply `extra="forbid"` to a TypedDict because a TypedDict has no `model_config`. `GraphCreate.model_config` sets `from_attributes=True` and nothing else. The declared key set is `x, y, color, xaxis, yaxis, title, layout, yoy, secondary_y, sort_x, sort_color` — and `metrics`, `orientation`, `barmode`, `plot_type`, `stacked`, `showlegend` are **not** in it. A caller supplying any of those gets HTTP 201 and a stored row with the key gone, and the read-back is indistinguishable from a row the caller never asked for.

Confirmed at this baseline against the real model:

```
GraphCreate(config={'metrics':['a'],'orientation':'h','barmode':'group','x':'region'}, ...)
STORED config: {'x': 'region'}
metrics key present: False
orientation present: False
barmode present: False
x present: True
```

Phase 16 filed this as CHT-001's sibling; the grading here is this phase's, because the property is a selection surface accepting an unconstrained key set.

**Evidence** — The `TypedDict` declaration and its use as a field annotation (`types.py:138`, `graph.py:15`), and the runtime confirmation above showing three submitted keys dropped and one retained, with no error raised and no rejection recorded.

**Consequence** — A graph created with a key the backend does not declare is persisted with that key absent and reports success. The caller receives 201 and reads back a config that does not match what it sent, with no way to learn which part was discarded — the failure is invisible at both ends. Where the key would have selected an axis, an orientation or a bar mode, the chart renders from a config the caller never expressed, so the stored dashboard and the caller's intent diverge with no error to reconcile them. This is the counterpart to the dynamic-selection defects phase 05 (DP: `dims[key].astext == str(value)`, a `groupby_cols == ["region","region"]` duplicate) and phase 16 (`dims` read as `row['y']`): those select a key at read time from an already-stored structure, this one discards an undeclared key at write time. Same root shape, opposite direction — the write side drops what it cannot interpret instead of refusing it, so nothing downstream ever learns the key was requested.

**Recommendation** — Make the selection closed at the boundary. Wrap the TypedDicts in Pydantic models with `model_config = ConfigDict(extra="forbid")` and keep the TypedDicts only as the internal representation if something still needs them; the smallest change preserving the current public shape is to declare `config: GraphConfigDict` with a `field_validator(mode="before")` that raises `AppException(code=ErrorCode.VALIDATION_ERROR)` naming the undeclared key. `extra="forbid"` on `GraphCreate`/`GraphUpdate` would not by itself catch this, since the excess keys are nested inside `config`, not at the model level. Before changing, check for shipped tests and frontend chart builders that currently send undeclared keys and rely on them being ignored — those encode the defect and must change with it.

### SEC-005 — A rejected password change writes the plaintext current and new passwords to the log sink and returns them in the response body

**Severity** — HIGH

**Zone** — 3. Credential Material in Everything Else That Persists

**Observation** — `ChangePasswordRequest` (`src/mkobi/models/auth.py:178-208`) carries three password fields and validates with a `model_validator(mode="after")` at `:196-201`. A Pydantic `model_validator` failure attaches the **entire validated input dict** to the error as `input`. `add_exception_handlers`'s `request_validation_exception_handler` (`src/mkobi/utils/exceptions.py:263-297`) copies each error verbatim into the response's `errors` array (`:285-296`) and, at `:272-275`, logs `exc.errors()` — the same dicts — at ERROR. So the two most ordinary outcomes of this endpoint both put all three plaintext passwords into both sinks. The field-level validator on `new_password` (`:203-208`) has the same shape: it echoes the new password alone.

Reproduced through the project's own handler, against the real `ChangePasswordRequest` and the real `add_exception_handlers`:

```
STATUS 422
LOG has current_password plaintext: True
LOG has new_password plaintext: True
LOG: RequestValidationError raised: [{'type': 'value_error', 'loc': ('body',), 'msg': 'Value error,
     'Passwords do not match', 'input': {'current_password': 'MyOldSecret9', 'new_password': 'NewSecret123', 'c...
BODY errors[0].input: {'current_password': 'MyOldSecret9', 'new_password': 'NewSecret123', 'confirm_password': 'Mismatch123'}
```

The log sink is durable and duplicated: `LOGGING__LOG_FILE=/app/data/logs/app.log` on both the app and worker services (`docker/docker-compose.yml:129,224`) backed by a `RotatingFileHandler` at 10 MB × 5 backups (`src/mkobi/core/logging_config.py:114-122`), plus the console handler, plus phase 10's OPS-008 duplication of each record across five rotating handlers on the same path. A mismatch in the confirmation field is a typo, not an attack, and it writes three working-or-intended secrets to disk.

This is distinct from phase 07's EXT-003 (an unbounded anonymous body reaching a single ERROR record): that is a caller-supplied *string* on a deliberately anonymous surface. This is **credential material** on an authenticated surface, and the mechanism is the error handler, not the route.

**Evidence** — The reproduction above; `models/auth.py:196-201` (the `model_validator` whose failure sets `input` to the whole body); `utils/exceptions.py:272-275` (logs `exc.errors()`) and `:285-296` (returns them in `errors`); `models/auth.py:203-208` (the field validator that echoes `new_password`).

**Consequence** — Any mismatch between `new_password` and `confirm_password`, or any new password failing the strength rule, writes the user's current password and intended new password in cleartext into `/app/data/logs/app.log` and every rotated backup, and echoes both back in the 422 body. The current password is by definition a working credential at that moment. Both sinks then persist it well past its usefulness: the log file is rotated rather than truncated and is reachable by anything that can read the container filesystem or the backup volume, and the HTTP response body travels through every proxy and client between the browser and the app. The strength-validator case additionally means a user who typed a too-short password has it recorded.

**Recommendation** — Strip `input` from the error before it reaches either sink, once, at the handler: in `request_validation_exception_handler`, drop the `input` key from `clean_err` (or replace it with the field name only) before both the `logger.error` and the `serializable_errors` list. That single change covers every model in the codebase, present and future, including any model that carries a secret field. As defence in depth, give the password fields `SecretStr` or exclude them from serialization so a future error path cannot echo them even if the handler regresses. Any shipped test asserting the current `errors[].input` shape for password-bearing models must change with it — it encodes the defect.

### SEC-006 — The unauthenticated `/health/detailed` returns the database driver's exception text, including the database role name, to any caller

**Severity** — MEDIUM

**Zone** — 5. Unauthenticated Inbound Writes: the Surfaces That Accept a Caller's Structure with No Session

**Observation** — `detailed_health_check` (`src/mkobi/app.py:298-359`) declares no dependency, so any caller reaches it. On database failure it returns `"error": str(e)` (`:320-326`) — the raw exception from SQLAlchemy/asyncpg — in a 200 response body. Reproduced against the real app with the database unreachable in two distinct ways:

```
# wrong host
{"status":"unhealthy","components":{"database":{"status":"disconnected","error":"[Errno 11001] getaddrinfo failed"},...}}

# correct host, wrong password
{"status":"unhealthy","components":{"database":{"status":"disconnected","error":"password authentication failed for user \"mkobi_app\""},...}}
```

The second form discloses the **database role name** verbatim, from an unauthenticated endpoint, in a 200. The response also discloses a filesystem path (`"path": "frontend/dist"`, `:330-333`), whether a frontend bundle is present, and the reconciler's internal counters (`sweep_count`, `unprotected_ticks`, `last_success_at`, `lease_state`, `:349-356`) — the last of which reports whether this replica currently holds the cleanup lease, i.e. which replica is doing maintenance.

The full unauthenticated inventory, derived from the route table rather than assumed:

| Surface | Accepts | Writes | Bounded | Discloses on refusal |
|---|---|---|---|---|
| `POST /api/v1/auth/login`, `/login/form` | email + password | nothing (token + redis counter) | yes, 5/300 s | uniform `AUTHENTICATION_FAILED` (phase 04 AUTH-006) |
| `POST /api/v1/auth/register-request` | email | `registration_requests` row | yes, 3/3600 s | uniform `"Unable to process registration request"` — does not enumerate |
| `POST /api/v1/client-errors` | free-form `error` dict, `url`, `userAgent`, `componentStack` | one ERROR log record | yes, 100/3600 s | 204 only; no DB write (phase 07 EXT-003) |
| `GET /health` | nothing | nothing | **no** | 200 or 503 with a database verdict |
| `GET /health/detailed` | nothing | nothing | **no** | 200 carrying component state and driver text |
| `GET /` (SPA mount, when `frontend/dist` exists) | any path | nothing | **no** | serves `index.html` for any unmatched path |

`register-request` deserves one note in the positive direction and is not filed: its refusal is a single message for existing-request / blocked-domain / existing-user alike (`auth_service.py:414-443`), so it does not enumerate accounts.

**Evidence** — The two reproduced `/health/detailed` bodies above, from `TestClient` against the unmodified app; `app.py:320-326` as the source of `str(e)`; absence of any `Depends` on the route at `app.py:298`.

**Consequence** — An unauthenticated caller polling `/health/detailed` learns the database role name, whether the database is reachable, whether a frontend bundle is mounted, the internal path of that mount, and the live state of the background reconciler including which replica holds its lease. The role name is a real reconnaissance primitive: it names the account whose credential would authenticate to the database, and the deployment's own init script creates exactly one such role (`docker/init-scripts/01-create-app-role.sh`). The two health surfaces are also the only unauthenticated surfaces that execute a `SELECT 1` against the database on every call and carry no attempt bound, so this is an unauthenticated, unbounded database-query surface that hands back its own internal detail.

**Recommendation** — Do not return `str(e)` from an unauthenticated endpoint; return the status only and log the detail server-side, which `app.py:321` already does. Replace `components["database"]["error"] = str(e)` with a stable, reason-free value (`"unavailable"`). The same argument applies, more weakly, to `path` and to the reconciler counters — if `/health/detailed` is meant to be reachable without a session, its body should describe readiness, not topology; if it is meant for operators, gate it with the existing `require_admin_role` dependency and keep the detail. The block-5 contract question of whether the reconciler state belongs in the response at all is phase 10's; what a no-session caller learns from it is this block's.

### SEC-007 — A 500 produced by the application's own exception handler leaves the process carrying none of the three security headers the application sets

**Severity** — MEDIUM

**Zone** — 8. Response Headers at the Application, and What a Deployment without the Delegating Tier Emits

**Observation** — `SecurityHeadersMiddleware.dispatch` (`src/mkobi/app.py:67-87`) sets `X-Content-Type-Options`, `X-XSS-Protection` and `Referrer-Policy` on every response that passes back through it, plus `Strict-Transport-Security` and `Content-Security-Policy` when `ENV=production`. The application's middleware stack, resolved from the running app, is:

```
ServerErrorMiddleware → SecurityHeadersMiddleware → GZipMiddleware → CORSMiddleware → ExceptionMiddleware → routes
```

`ServerErrorMiddleware` is **outside** the middleware that adds the headers, and it is the component that invokes the `Exception` handler registered at `utils/exceptions.py:330-345`. Reproduced against the unmodified application by adding one route that raises:

```
STATUS 500
BODY {"type":"...internal_error","title":"Internal server error","status":500,"detail":"Internal server error",...}
has XCTO: False
headers: {'content-length': '171', 'content-type': 'application/json'}
```

`GET /health` in the same process returns 200 **with** `X-Content-Type-Options`. So the 500 class is the one response class in this application that leaves the process with no header the application claims to set — and 500 is precisely the class a client should be least able to render. The generic message itself is correct (`detail="Internal server error"`, no internal text, no trace, no environment divergence — `debug` is `False` by default at `config.py:542` and is refused outright in production at `:659-666`), so this is the header gap only.

Header inventory by response class, against the running app:

| Class | `XCTO` / `X-XSS` / `Referrer` | HSTS / CSP | Source |
|---|---|---|---|
| 200 / 4xx from a route | yes | production only | `app.py:78-85` |
| RFC 7807 error from `AppException`, validation, Starlette handlers | yes | production only | handlers are inside `ExceptionMiddleware`, so headers applied |
| **500 from the `Exception` handler** | **none** | **none** | `ServerErrorMiddleware`, outside the header middleware |
| SPA asset responses (`/assets/*`, `index.html`) | yes | production only | measured on the live mount |

The deployment framing: `docker/nginx/nginx.conf:20-30` sets `X-Content-Type-Options`, `X-Frame-Options SAMEORIGIN`, `X-XSS-Protection`, `Referrer-Policy` and a full CSP with `always`. But **the dev stack runs no nginx** — `docker/docker-compose.override.yml` defines `db`, `migrate`, `app`, `redis`, `rq-worker` and `frontend`, and `nginx` carries `profiles: [production]` (`docker/docker-compose.yml:293-294`). The dev frontend is Vite on `:5173` proxying `/api` to `app:8000` (`frontend/vite.config.ts:9-12`) and Vite's `server` block sets no headers at all. So in the offered dev deployment every response the browser sees for API traffic comes straight from the app process with the app's own three headers and no `X-Frame-Options` and no CSP — the application sets `X-Frame-Options` nowhere, only the delegating tier does, and that tier is absent.

**Evidence** — The middleware-stack ordering and the measured 500 header set, both from the running application; the reproduction of the Starlette mechanism in isolation (a bare `Starlette` app with one user middleware and an `Exception` handler gives `500 has XCTO: False` while `200 has XCTO: True`) which confirms the mechanism is Starlette's, not this project's; `docker-compose.override.yml` service list and `docker-compose.yml:293` profile gate.

**Consequence** — Two effects. In production, behind nginx, the 500 class is fully covered by `add_header ... always` at the nginx tier, so the practical gap there is nil — this is why the severity is not higher. In the dev deployment, where nginx is genuinely absent, every response carries no `X-Frame-Options` and no CSP at all, and — for the 500 class — no header whatsoever, because the application's own handler produces the response outside its own header middleware. The dev deployment is the one an operator debugs against and the one a new contributor runs by default.

**Recommendation** — Move the header assignment so it cannot be bypassed: have `global_exception_handler` (`utils/exceptions.py:330-345`) set the same three headers on the `JSONResponse` it builds, or register the headers as an outer middleware above `ServerErrorMiddleware`. The smallest correct change is to have the handler stamp the headers explicitly — three lines, no reordering, and it makes the class's contract explicit rather than dependent on where Starlette happens to place things. For the deployment gap, the phase's own framing applies: a deployment with no delegating tier is supported, so report it as a document-and-decide item rather than a code defect — either add `X-Frame-Options` to the app's own set (the nginx value is `SAMEORIGIN`, chosen for iframe compatibility during a Dash migration per the docstring at `app.py:56-57`, so the app should carry the same value to stay consistent), or record in `docs/10-deployment/` that the dev stack sets no framing or CSP control and that the Vite dev server sets none either. Note that `SecurityHeadersMiddleware`'s own docstring is accurate — it does say nginx handles `X-Frame-Options` — so the documentation is not over-claiming; the gap is that the development deployment it describes inherits nothing.

### SEC-008 — Failure detail is copied from the Python exception into the response body on ~25 sites, and the worker persists a filesystem path or a Redis endpoint into the durable `processing_logs.message` the status endpoint returns

**Severity** — HIGH

**Zone** — 7. Failure Responses: What an Undecided Failure Puts in the Response

**Observation** — The failure-path inventory. Every RFC 7807 body is produced by one of four handlers in `src/mkobi/utils/exceptions.py`; none of them varies by environment, and none of them returns a traceback, so the project's stated contract holds on the shape axis. The gap is in **what the `detail` string is populated from**.

`detail=str(e)` appears on **25 route sites** across ten route modules (`admin.py:91,127,230`; `auth.py:239,510,599`; `dashboards_access.py:114`; `dashboards_crud.py:151,389`; `dashboards_graphs.py:104`; `data.py:203,209`; `graphs.py:131,378`; `layouts.py:108,348`; `processing_configs.py:192,265`; `upload.py:242`; `users.py:81,258,312,366`) plus `deps.py:567` and `exceptions.py:321`. Each is inside an `except ValueError` / `except AppException`-family block, so today the string is a curated message — this is **not** a blanket claim that all 25 leak. The finding is that the mechanism makes internal text reachable by construction: any exception type that later inherits from `ValueError` inside those blocks, or any `ValueError` raised deeper with an interpolated value, is returned to the caller verbatim with no allow-list. Two paths already cross that line.

**Path A — Redis endpoint returned to the caller.** `enqueue_processing_job` raises `AppException(code=FILE_PROCESSING_ERROR, detail=f"Failed to enqueue processing job: {e}")` (`src/mkobi/core/task_queue.py:72-77`), interpolating the raw exception from the RQ enqueue into a response `detail`. Measured on the real `redis` client: `Error 11001 connecting to redis:6379. getaddrinfo failed.` and `Timeout connecting to server` — the Redis **service name and port**, i.e. internal topology, into an RFC 7807 body returned to the uploading caller.

**Path B — a filesystem path persisted to a durable column and read back.** On processing failure the worker writes `message=f"Processing failed: {error_msg}"` where `error_msg = str(e)` (`src\mkobi/workers/data_worker.py:571-594` and `:606-631`). `ProcessingLog` has no name or path column at all, and `DataService.get_processing_status` returns `filename=log.message or "unknown"` **and** `message=log.message` (`src\mkobi\services/data_service.py:335-341`), so this column is the response's filename field. Reproduced against the real Polars reader: a read failure yields `The system cannot find the path specified. (os error 3): /app/data/tmp_uploads/upload_9f2c_deadbeef_sales.csv`, and the persisted value becomes `Processing failed: The system cannot find the path specified. (os error 3): /app/data/tmp_uploads/upload_9f2c_deadbeef_sales.csv`. The container-internal upload path — including the UUID prefix and the user-supplied filename — is stored in PostgreSQL and served back on every status poll.

Phase 06's ART-002 established that the status endpoint returns `filename=log.message` and that `ProcessingLog` has no name/path column; phase 07 established the unbounded caller-supplied string reaching a log record. Neither established that this column also carries the **server-side** exception text — a container path on a filesystem fault, an RQ/Redis error on a queue fault — or that it is returned to the caller as the filename. That is what is new here.

The `global_exception_handler` itself is clean: `detail="Internal server error"`, `details=None`, no traceback, no environment divergence (`debug` defaults `False` at `config.py:542` and is refused in production at `:659-666`). Measured with `DEBUG=true` under `ENV=development`, the *unhandled-exception* path does return a Starlette debug page with a traceback; this is refused at settings validation in production, so it does not reach a production deployment, and the project's `add_exception_handlers` `Exception` handler overrides it for any exception FastAPI routes rather than letting the debug page through. Not filed on its own; recorded in the residual footer.

**Evidence** — `core/task_queue.py:76` as the interpolation site with the measured Redis exception strings; `workers/data_worker.py:571,590` and `:606,629` as the persistence sites with the reproduced Polars message; `services/data_service.py:335-341` as the read-back; `utils/exceptions.py:263-297` establishing that the validation handler is the one that also writes to the log (SEC-005).

**Consequence** — An authenticated editor who uploads a file and polls `/api/v1/upload/status/{task_id}` — the normal failure loop — receives, in the `filename` field of a 200 response, the container's absolute upload directory, a UUID, and the caller-supplied filename, or the internal Redis endpoint with its port, depending on which internal component failed. Both values are durable: the path is in a `processing_logs` row that phase 06 established has no retention path for this content, and the topology string is in every RFC 7807 body. For the caller this converts an internal fault into a filesystem map of the container; for anyone with read access to `processing_logs` (which the admin surface exposes at `/api/v1/admin/logs`) it converts the table into a record of every failure the system has had, with paths. The `detail=str(e)` pattern is the mechanism that makes this repeatable: the next exception that surfaces here is returned verbatim too.

**Recommendation** — Three separable changes. (1) At `task_queue.py:76`, stop interpolating: `detail="Failed to enqueue processing job"` with the exception chained (`from e`) so the log keeps it and the response does not — the same shape `upload.py:246-251` already uses. (2) In `data_worker.py`, persist a stable, caller-useful message rather than `str(e)`: the `error_code` column already carries the machine-readable classification, and the human message can be a fixed string per failure class. Keep the full `str(e)` in `logger.exception` at `:573` and `:608`, which is where operator-facing detail belongs. (3) Replace the 25 `detail=str(e)` occurrences with a mapping from the `ErrorCode` already being passed to `get_error_title`, so the response string is drawn from a closed set. That last change is the durable fix; the first two are the two current leaks. Any shipped test asserting the interpolated detail must change with it.

### SEC-009 — The access token sits in `sessionStorage` in every non-production build, reachable by any script in the page, gated only by a build flag

**Severity** — LOW

**Zone** — 1. The Stored Password: Encoding, Parameters, and the Policy Around It

**Observation** — `frontend/src/features/auth/model/authToken.ts:74` sets `USE_MEMORY_STORAGE = import.meta.env.PROD`. When true (a production build) the access token lives only in the module-level `memoryToken` (`:66`) and `getToken`/`setToken` never touch browser storage (`:84-90`, `:119-125`, `:134-140`, `:142-154`). When false — **every `npm run dev` invocation, which is what `docker/docker-compose.override.yml:37-57` runs** — the same functions read and write `sessionStorage['access_token']` (`:89`, `:124`, `:139`, `:148`). The store is bound to the tab's origin and is discarded when the tab closes (`:60-63` states this correctly), so it does not outlive the session. The refresh credential is unaffected: it is set as an HttpOnly cookie by `set_secure_cookie` (`core/security.py:416-441`) and never enters JS. The same storage tier also holds dashboard filter state (`DashboardView.tsx:62,79`), which is not credential material.

The property that decides this is not enforced anywhere but a build flag and a comment. `authToken.ts:64` reads `This mode MUST NEVER be used in production builds` — a comment. There is no assertion, no lint rule, and no test that fails when the dev storage path is the live one.

**Evidence** — `authToken.ts:74` and the four `sessionStorage` call sites; `docker-compose.override.yml:37-57` defining the dev frontend as the Vite dev server; `core/security.py:416-441` for the HttpOnly refresh cookie.

**Consequence** — In the dev deployment — which is what an operator runs by default and what a new contributor runs — any script executing in the page origin can read the access token, which is a bearer credential for every API surface behind `CurrentUser`. The token is short-lived (30 minutes by default) and dies with the tab, so the blast radius is one tab on a development machine rather than a production session. The production build is unaffected. The finding is that the separation between the two is asserted only in prose.

**Recommendation** — Make the invariant mechanical rather than documented. Either delete the `sessionStorage` branch and accept losing the dev refresh convenience, or gate it on an explicit opt-in that cannot be true by accident — a `VITE_ALLOW_INSECURE_TOKEN_STORAGE` variable that is unset in `.env.production` and asserted in a unit test, so a production build that fell through to the storage path fails the suite. Phase 13's FE-004 already covers the module-boundary problem in this same file; this finding is only the storage choice. No shipped test asserts the current behaviour — `authToken.test.ts:11-16` documents the dev-mode expectation and would need to be inverted.

## Distribution

Findings cluster on the **request-response boundary**, not on any single tier: six of nine live where a Python value is copied out of an internal object and into something a caller or a log can read. The **server-side boundary handlers** carry the most — `utils/exceptions.py` (SEC-005), `core/task_queue.py` and `workers/data_worker.py` (SEC-008) — and the single heaviest component is `src/mkobi/utils/exceptions.py`, which is both the credential-to-log path and the error-shape contract for every route. The **credential tier** is split: one finding each at rest (SEC-001), in the delegated store (SEC-002), and in the browser (SEC-009). The **admission tier** is entirely SEC-003, the one finding that concerns whether a control decides anything. The **health surface** is SEC-006 alone, and the **header tier** SEC-007 alone.

- `src/mkobi/utils/exceptions.py` — SEC-005 (critical path; also the mechanism SEC-008 depends on)
- `src/mkobi/api/routes/auth.py`, `client_errors.py`, `upload.py`, `core/security.py`, `config.py` — SEC-003
- `src/mkobi/core/temp_password_store.py`, `services/auth_service.py`, `api/routes/admin.py` — SEC-002
- `src/mkobi/core/task_queue.py`, `workers/data_worker.py`, `services/data_service.py` — SEC-008
- `src/mkobi/app.py` — SEC-006, SEC-007

## Cross-Finding Analysis

Two causes are shared across findings; the rest are independent.

**Cause 1 — an internal value is copied into a caller- or log-visible string with no closed set to copy from.** SEC-005 (the Pydantic error's `input` dict into both the log and the response), SEC-006 (`str(e)` into an unauthenticated response), and SEC-008 (`str(e)` into an RFC 7807 `detail` and into `processing_logs.message`) are one defect in three places. Each site independently decided that the exception's own text was an acceptable response value. The absence of a closed vocabulary for "what may a failure say" is what lets a container path, a Redis endpoint and a plaintext password all reach a caller by the same route. Fixing any one site closes one leak and leaves the pattern; fixing the vocabulary closes the class.

**Cause 2 — a security property is expressed as a call-site convention rather than as a type or a validated boundary.** SEC-001 (no length bound on any password field, so `_truncate_password` decides), SEC-003 (`fail_closed` passed at five sites over a class defaulting to the opposite, and a key taken from a proxy header), and SEC-004 (a `TypedDict` where a Pydantic model would refuse unknown keys) are the same shape: the invariant exists as prose or as a caller's care, and the type system or the boundary does not enforce it. SEC-009 is the same shape in the client tier — a comment asserting what a build flag decides.

SEC-002 and SEC-007 are independent of both: SEC-002 is a storage-encoding choice, SEC-007 is a middleware-ordering fact about Starlette.

## Roadmap

Grouped by cause. Each step states what must be true before the next begins.

**Step 1 — close the credential leaks before anything else (SEC-005).** One change in `request_validation_exception_handler`: drop `input` from the error before both the log and the response. Everything else in steps 2 and 3 is lower urgency than a plaintext password in a rotated log file. Nothing depends on this step; it is first because its blast radius is the largest and its diff is smallest.

**Step 2 — give failures a closed vocabulary (SEC-008, SEC-006).** Requires step 1 to have landed, because both change `utils/exceptions.py` and the tests around it. Then: replace `detail=str(e)` with `get_error_title(code)`-derived strings at all 25 sites; stop interpolating at `task_queue.py:76`; stop persisting `str(e)` into `processing_logs.message` while keeping it in `logger.exception`; remove `str(e)` from `/health/detailed`. Must be true before step 4: each of these changes an observable response string, so the test suite has to be re-baselined once, not four times.

**Step 3 — make the rate limiter's decisions structural (SEC-003).** Independent of steps 1–2 and can run in parallel. First: make `fail_closed` a required argument (or invert it) and delete the unused `AuthService._rate_limiter`. Then: resolve the peer address from `scope["client"]` rather than the post-proxy header. Then: add `RATE_LIMITER_FAIL_CLOSED` to the dev overlay. Must be true before step 5: any test that drives two requests through `TestClient` to prove a counter trips depends on the key derivation, so change the key before the tests that assert trip behaviour.

**Step 4 — bound the credential at the boundary (SEC-001).** Requires step 2's test re-baselining to be done, since both touch password-model validation tests. Reject over-length input in the field validators and make `_truncate_password` raise. Only after this is a per-account audit of already-stored 72+ byte credentials possible — which is an operational follow-on, not a code step.

**Step 5 — close the selection surface and the header gap (SEC-004, SEC-007, SEC-002, SEC-009).** Independent of the above; sequence by diff size. SEC-007 is three lines in the exception handler. SEC-009 is a variable plus a test inversion. SEC-004 needs a check for frontend chart builders currently relying on silent drop. SEC-002 is the largest (credential re-encoding plus a store migration) and should be scheduled against a deployment, not a release.

## Rollout Safety

**Steps 1 and 4 are response-shape changes and will break the frontend's error extraction.** `frontend/src/shared/api/errorHandler.ts` reads the legacy 422 array and the RFC 7807 `code`; removing `input` from the 422 array does not affect either path, but rejecting over-length passwords produces a new 422 the frontend does not currently render distinctly — verify the "validation field-level errors" branch still shows something useful when a user submits a long passphrase. Changing `_truncate_password` to raise will also break any test asserting the truncation warning; those tests encode the defect and must change with it.

**Step 2 changes error strings that the frontend may display.** `get_error_title`-derived strings are more generic than the interpolated ones — a user who currently sees "Password authentication failed for user mkobi_app" will see a fixed message. That is the intent, but it is user-visible and should be checked against the login and upload screens specifically. The `processing_logs.message` change alters what `/api/v1/upload/status/{task_id}` returns in `filename`, and `/api/v1/admin/logs` — phase 06's ART-002 territory — renders the same column, so both screens need a look.

**Step 3 is the one with a genuine rollback hazard.** Keying the limiter on the real peer address instead of the proxy header changes which requests share a counter: in production behind nginx, every request currently presents the left-most `X-Forwarded-For` entry and would instead present the nginx container's address, which means **all production callers would collapse onto one bucket** until nginx is also trusted correctly. Do not ship the key change alone. The safe order is: pass an explicit `--forwarded-allow-ips` listing the proxy's own address (never `*`), confirm with `TestClient` what `scope["client"]` resolves to in the deployed topology, and only then remove the header-derived key. Revert is a single environment variable if the collapse is observed — which is why this belongs in its own step with its own deploy.

**Step 5's SEC-002 change is the one that cannot be reverted by redeploying.** Existing `temp_pwd:*` entries would be unrecoverable under a new encoding. Drain or accept the 24-hour loss window during rollout, and coordinate with any pending admin resets.

## Appendices

**Blocks executed — all eight.** Block 1 (SEC-001, SEC-009), Block 2 (SEC-002, with AUTH-002/AUTH-006 deferred to phase 04 as instructed), Block 3 (SEC-005; Block 3's own instruction — start at `data_worker.py:532-534` / `:594-603` — was covered by reading `:560-631` and both unlink sites, which sit inside the read range), Block 4 (SEC-003), Block 5 (SEC-006, with the full unauthenticated inventory in the finding), Block 6 (SEC-004), Block 7 (SEC-008), Block 8 (SEC-007).

**Method.** No Docker service was started, stopped or reconfigured. Runtime evidence came from `uv run python` against the real modules and, where noted, `starlette.testclient.TestClient` against the unmodified `create_app()` output with `JWT__SECRET_KEY` and `ENV` supplied inline. Reproductions: the 72-byte aliasing (SEC-001); the plaintext-password log and response echo through the project's own handler (SEC-005); `/health/detailed` under two distinct database failure modes (SEC-006); the 500 header set versus the 200 header set in the same process, plus the isolated Starlette mechanism check and the resolved middleware ordering (SEC-007); the `GraphConfigDict` silent drop (SEC-004); the Redis and Polars exception texts that reach response and durable column (SEC-008).

**Cited, not re-filed.** AUTH-001 (rate-limit key collapse) and AUTH-002/AUTH-006 (temp-store fail-open, single-404) — phase 04. EXT-003 (anonymous 5 MB body as one ERROR record) — phase 07. OPS-008 (five rotating handlers duplicating records) — phase 10, noted in SEC-005. ART-002 (`filename=log.message`, no name/path column on `ProcessingLog`) — phase 06, extended in SEC-008 rather than repeated. AUTH-002's registration-request reachability was checked: `admin.py:320-321` takes the identical path as the reset path, and is reported inside SEC-002.

**Residual limits on this report.** (1) The key derivation in SEC-003 was established from the launch commands, uvicorn's documented default and phase 04's and phase 07's measurements, not from a fresh reproduction inside a running nginx→uvicorn topology; the *consequence* (caller-chosen key) is corroborated by phase 07's `register-request:172.21.0.7`-for-five-callers result, not independently re-measured here. (2) No live PostgreSQL or Redis was reachable, so the Redis-plaintext recoverability verdict in SEC-002 is a static proof from the write site and the compose service definition, not a `KEYS temp_pwd:*` executed against a live instance; the encoding argument does not depend on a live instance. (3) With `DEBUG=true` under `ENV=development` an unhandled exception returns a Starlette debug page containing a traceback. This is refused at settings validation in production (`config.py:659-666`) and is overridden by the project's own `Exception` handler for route-raised exceptions, so it is recorded here as a limit rather than filed — but the refusal depends on the `debug` setting rather than on the handler, and a deployment that set `DEBUG` in a tier where the production check does not apply would emit it. (4) The 25 `detail=str(e)` sites in SEC-008 were individually classified as catching curated `ValueError` messages; only two were confirmed to carry internal text today. The finding is the mechanism, and the mechanism claim rests on the absence of a closed set rather than on 25 demonstrated leaks.

**Prefix check.** `SEC-` was free across all fourteen existing phase reports before this run; no collision, no second namespace created.
