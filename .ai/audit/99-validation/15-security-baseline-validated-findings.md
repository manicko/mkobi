---
phase: 15-security-baseline
executed: 2026-10-01
executor: validator
problems-only: true
baseline: 4a5db549875b8e432720f3775c936f3ef04b299c
baseline-dirty: "53 lines in git status --porcelain at the start of this run, 55 at its end (the delta is the concurrent remediation programme landing, not this run); the input's own baseline was 9c49c20, so every anchor was re-resolved against the current tree; the 15 frontend/coverage/ deletions are pre-existing and untouched"
findings: 9
by-severity:
  CRITICAL: 0
  HIGH: 4
  MEDIUM: 4
  LOW: 1
---

# Phase 15 — Security Baseline — Validated Findings

## Summary

All nine findings were re-derived from the executing path, not from the quoted evidence, at this run's baseline
`4a5db54` (the input's baseline was `9c49c20`; the concurrent remediation programme moved the tree, so every
anchor was re-resolved and the drifted ones are listed in the Appendices). Six are **confirmed** with every
anchor resolving (SEC-001, SEC-004, SEC-005, SEC-006, SEC-007, SEC-009). Two are **confirmed and re-typed**:
SEC-002, whose encoding is genuinely new and which the input was right to defer to phase 04 on every other axis,
and SEC-008, whose mechanism and both live leaks hold while its site count is misattributed. One is **confirmed
on its substance with one clause refuted** — SEC-003, the coordinator's reconciliation: the two-defaults
disagreement is exactly right and is confirmed clause by clause, but the key-derivation claim is the opposite of
what the executing path does, three sibling reports and the input's own cited evidence say so, and the rollout
hazard is characterised backwards. SEC-005 — the most consequential claim in the set — reproduced exactly, in both
sinks, through the project's own handler, and its recommended fix is confirmed to *converge with* the shipped RFC
7807 specification rather than break it, which inverts the risk the report attaches to it. No finding was re-graded
and none was rejected outright; the four defects in the report itself are filed under `VAL-15-`. The flat `VAL-`
namespace is already occupied by the phase-01 and phase-02 validation reports, so this report's validation-level
identifiers carry a `VAL-15-` infix; the deviation is recorded in the Appendices.

## Findings

### SEC-001 — Passwords longer than 72 bytes are silently aliased to their first 72 bytes, so a credential change can leave the previous password usable

**Severity** — MEDIUM

**Zone** — 1. The Stored Password: Encoding, Parameters, and the Policy Around It

**Disposition** — **confirmed**, band unchanged. Anchor re-resolved; the recommendation's reasoning about
character-vs-byte counting is correct, and the named remediation blocker is real.

**Observation** — Every clause re-derived against the current tree. `SALT_ROUNDS: int = 12` and
`MAX_PASSWORD_LENGTH: int = 72` at `src/mkobi/core/security.py:37-38`; `_truncate_password` at
`security.py:154-187`; `hash_password` calls it at `security.py:208` and `verify_password` at `security.py:236`,
so the truncation is applied symmetrically on both sides exactly as filed. `ChangePasswordRequest`
(`src/mkobi/models/auth.py:181-183`) declares `current_password: str`, `new_password: str`,
`confirm_password: str` — all bare `str`, no `max_length`, no `min_length`, no `Annotated` constraint. A
repository-wide search for `max_length` across `src/mkobi/models/` returns **no hit on any field in any request
model**, so the absence is total, not per-model. `validate_password_or_raise` is a lower-bound check only.
`change_password` verifies the current password before writing (`auth_service.py:498-503`) and then compares
`current_password != new_password` at `auth_service.py:505` as a **plain string inequality** — it does not hash
either value, so it cannot notice a 72-byte-prefix collision. All three claims hold.

**Evidence** — Re-derived from the source rather than re-executed: the two truncation call sites
(`security.py:208`, `security.py:236`) are the proof that a 100-byte input and a different 100-byte input sharing
72 leading bytes hash to the same value and verify against the same hash, with no runtime needed. The
string-inequality check at `auth_service.py:505` is the proof that `change_password` reports success for a change
that only edited the discarded tail.

**Consequence** — As filed. The change endpoint accepts a "change" that altered only bytes past 72 and reports
success while the previous password continues to authenticate; the user has no signal, because `_truncate_password`
emits only a `logger.warning`. One refinement from re-derivation: the collision is not confined to the
change endpoint — it is present on the **login** path too, because `verify_password` truncates identically, so
any two long strings sharing a 72-byte prefix are mutually valid credentials on every surface that verifies a
password, including `/api/v1/auth/login` and `/login/form`. That widens the effect from "a change is a no-op" to
"the credential has an effective entropy ceiling of 72 bytes with no user-visible boundary".

**Recommendation** — Executable. The reasoning in the input's recommendation is **correct and worth preserving**:
`max_length=72` on a `str` is a Pydantic *character* count, so a 72-character multi-byte passphrase (216 UTF-8
bytes for a 3-byte-per-character script) would pass a naive `max_length=72` and still be silently truncated —
the `field_validator` on the UTF-8 byte length is required, not a refinement. Two corrections to the plan, both
verified: (a) the recommendation lists `LoginRequest.password` and `ChangePasswordRequest.current_password` under
a `max_length` bound, but a byte-length bound on `current_password` converts a *wrong-credential* login into a
422 with a byte-length complaint, which is a small oracle on nothing and an unnecessary behaviour change — the
bound belongs on the two fields that *create* a credential (`RegisterRequest.password`,
`ChangePasswordRequest.new_password`); verification should keep truncating so existing over-length credentials
continue to authenticate, and the length policy should be enforced at mint time only. (b) Changing
`_truncate_password` to raise is safe for verification precisely because of that asymmetry, and unsafe if applied
symmetrically. **Named remediation blocker, confirmed present:** `tests/` asserts the truncation behaviour, so
those tests encode the defect and must change with the fix — see VAL-15-003 for the exact file set.

### SEC-002 — Delegated credentials are stored in Redis as the credential itself, so anything that reaches the store recovers every outstanding password in the clear

**Severity** — HIGH

**Zone** — 2. Short-Lived Credentials Handed to Another Person: the Store, the Lifetime, the Retrieval

**Disposition** — **confirmed and re-typed**: the encoding claim is real, is not owned by any prior phase, and
stays here. The input was **right** to defer the store's read-path defects to phase 04, and the deferral is
correct on both overlaps. Band unchanged.

**Observation** — Re-derived with fresh anchors. `TempPasswordStore.store` computes
`key = f"{_KEY_PREFIX}{token}"` at `core/temp_password_store.py:39` and calls
`await self._redis.set(key, password, ex=self._ttl)` at `:41`. The `password` parameter is the parameter, and no
transformation of any kind is applied between the call boundary and the Redis value — the *only* transformation
anywhere on this path is `hash_password(temp_password)` in `auth_service.py`, whose output goes to PostgreSQL and
is never related to the Redis value. The stored form is therefore the plaintext, confirmed. `_TTL` defaults to
86400 and is fed from `temp_password_ttl_seconds` (`config.py:581`, `Field(default=86400, alias=…)`), so the
lifetime claim holds. `retrieve` (`:50-75`) does GET+DELETE in one `pipeline(transaction=True)` (`:63-66`), so
the store's own read path is single-read exactly as filed.

The **compose service body was re-derived from scratch**, as instructed, because `docker/docker-compose.yml` was
edited by the concurrent remediation programme. The `redis` service now occupies lines **172-188** (the input
cited `171-176`, so the anchor drifted by one line at the start and the block is longer than filed). Its complete
body is: `image: redis:7.4-alpine`; `volumes: [redis_data:/data]`; `restart: unless-stopped`; a `healthcheck`
running `redis-cli ping`; and a `deploy.resources` block with memory and cpu limits. **There is no `command`
key, no `requirepass`, no `REDISCLI_AUTH`, no TLS and no `ACL` directive** — the service does not even override
the image's own command, so Redis starts with its compiled-in defaults: no password, no TLS, no ACL users. The
substantive claim survives the remediation untouched, and the `deploy.resources` block is in fact the only thing
that changed in that block.

**Evidence** — `core/temp_password_store.py:39-41` is a two-line static proof that the value written and the
value needed to authenticate are the same bytes: the argument to `set` is the parameter. `docker/docker-compose.yml:172-188`
re-read in full this run and enumerated service by service (`db` 16-53, `migrate` 54-92, `app` 93-171, `redis` 172-190,
`rq-worker` 191-268, `nginx` 269-302), which is how the absence of any auth directive was established rather
than assumed from a line range.

**Consequence** — As filed, with one correction of emphasis. Because `redis_data:/data` is a named volume, the
plaintext is also at rest in the RDB/AOF for the life of the volume, which extends the exposure past the 24 h TTL
for any snapshot taken of that volume. The correction: the input frames the recoverable set as "every account that
has been reset or approved and not yet claimed", which is right, but the **enumeration is a single `KEYS
temp_pwd:*`** rather than a per-token guess, and the same instance also holds the two access-token blacklists and
the reconciler lease, so one read of Redis yields the delegated credentials *and* the means to inspect or poison
the blacklists.

**Recommendation** — Executable, and the input's own preferred shape is the one to take: keep the password only in
the issuing process's memory until it is claimed, and put nothing in Redis but a random per-token key. That
removes the effect without touching the retrieval contract, which is the only part the tests actually pin (one
read, then gone). The AEAD alternative is weaker than the input states and should not be the first choice: a
`Fernet` key sourced from the same `_FILE` secret mechanism as `JWT__SECRET_KEY` still leaves every outstanding
credential recoverable by anyone who reaches Redis **and** the app's environment, which is the same reachability
that motivated the change. Adding `requirepass` and a dedicated ACL user to the `redis` service is a
complementary hardening step, not a substitute for re-encoding. **Rollout hazard the input states correctly and
this validation confirms:** existing `temp_pwd:*` entries are unrecoverable under a new encoding, so the change
requires draining the store or accepting a bounded loss window.

### SEC-003 — The rate limiter is wired to five surfaces, keys on a caller-controlled address, and its fail-closed posture is a class default that the settings default contradicts

**Severity** — HIGH

**Zone** — 4. Attempt-Rate Bounding: Which Surfaces Carry One at All

**Disposition** — **confirmed and re-graded up in scope, refuted on mechanism.** The two-defaults reconciliation —
the coordinator's specific question — is **confirmed clause by clause**. The key-derivation claim is **not
substantiated**: it asserts the opposite of what the executing path does in every shipped deployment, and the
evidence it cites for itself proves the reverse. The finding survives on its surviving substance, which is still
HIGH, and the key claim is **handed to phase 04's AUTH-001, which already owns it and already measured it**. The
rollout hazard is characterised backwards and is filed as VAL-15-001.

**Observation — clause 1, the two defaults, CONFIRMED exactly as filed.** `config.py:578` reads
`rate_limiter_fail_closed: bool = Field(default=True, alias="RATE_LIMITER_FAIL_CLOSED")` — fail-closed in
settings. `core/security.py:107` reads
`def __init__(self, redis_client: aioredis.Redis, fail_closed: bool = False) -> None:` — fail-open in the class.
Both anchors resolved on the first read and neither has the direction reversed. The Redis-error path at
`security.py:137-151` is a bare `except Exception` that returns `True, None` (admit) when `self._fail_closed` is
falsey and `False, ttl` (reject) when truthy, so the class default alone decides the outage posture for any caller
that omits the argument.

**Observation — clause 2, the five call sites, CONFIRMED.** All five pass the settings value explicitly:
`auth.py:84-86`, `auth.py:310-312`, `auth.py:562-564`, `client_errors.py:45-47`, `upload.py:144-146`. The sixth
site the input names is also exactly as filed: `auth_service.py:66-68` constructs
`self._rate_limiter = AsyncRateLimiter(...)` and `fail_closed=config.rate_limiter_fail_closed` is passed — so the
pattern is *not* violated there, but the instance is still constructed and never read: `_rate_limiter` has no
reader anywhere in `auth_service.py`. The input's wording "constructed and never called" is correct, and its
paraphrase "the pattern is not enforced" is a fair characterisation of a dead instance at a site that happens to
pass the flag, though the literal reading ("a site that omits the flag") is not what the code shows.

**Observation — clause 3, environment reach, CONFIRMED.** `RATE_LIMITER_FAIL_CLOSED` appears in exactly three
places in the entire tree: `docker/.env.production:49` (`=true`), `docker/docker-compose.yml:142` (app service,
`${RATE_LIMITER_FAIL_CLOSED:-true}`) and `docker/docker-compose.yml:236` (rq-worker service, same form). It is
**absent from `docker/docker-compose.override.yml` entirely**. So in production the posture is declared twice over
(env file and compose default) and both resolve fail-closed, and in the dev overlay it resolves from the
`Field(default=True)` instead. The resolved value happens to be identical in both tiers, which is why the gap has
gone unnoticed — exactly as filed. Both services that construct a limiter receive it, so the "reaches every
production surface" question answers **yes**.

**Observation — clause 4, the key, NOT SUBSTANTIATED.** This is the refutation, and it is decisive. The input
asserts that `request.client.host` is uvicorn's proxy-header value, that nginx appends rather than overwrites, and
therefore "the caller chooses the key". Every step of that chain is individually true and the conclusion does not
follow, because the chain omits the gate. Re-derived from the installed library: uvicorn **0.49.0**;
`uvicorn/config.py` computes `self.forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")`
when the flag is `None`, and `proxy_headers` defaults to `True`; `uvicorn/middleware/proxy_headers.py:34` reads
`if client_host in self.trusted_hosts:` and **only inside that branch** reads `X-Forwarded-For` and reassigns
`scope["client"]`. The effective trusted set in this deployment is therefore `{"127.0.0.1"}`. A repository-wide
search for `FORWARDED_ALLOW_IPS`, `proxy-headers`, `forwarded-allow-ips` and `forwarded_allow` across `docker/`,
`src/`, `docs/` and the Dockerfiles returns **no hit anywhere**, and the only launch command in the dev overlay is
`["uvicorn", "src.mkobi.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-exclude", "/app/tests/"]`
(`docker/docker-compose.override.yml:119`) — no proxy flag. In the shipped topology the app's TCP peer is the
**nginx container's bridge address in production and the Vite container's bridge address in dev**, neither of which
is `127.0.0.1`. The gate therefore never opens, the header is never read, and `request.client.host` is the
**proxy's** address for every request. Two independent corroborations from the corpus: phase 04's validation
reproduced the effective value `forwarded_allow_ips == '127.0.0.1'` and the gate at `proxy_headers.py:34` from
the installed library, and measured six distinct `X-Forwarded-For` values resolving to the single key
`login:172.21.0.2`; phase 07's measurement, which this input cites as an instance of the *caller-chosen* key, is a
container bridge address serving five distinct callers and is in fact a measurement of the **collapse**.

**Observation — the surface inventory, CONFIRMED and the missing bounds are real.** The five bounded surfaces and
their parameters all resolve: `auth.py:89` `login:{client_ip}` 5/300 s, `auth.py:314` `refresh:{client_ip}`
10/300 s, `auth.py:566` `register-request:{client_ip}` 3/3600 s, `client_errors.py:49` `client-errors:{client_ip}`
100/3600 s, and `upload.py:149` `upload:{current_user.id}` 100/3600 s — the last the only identity-keyed site, and
the only one on an authenticated surface. The unbounded surfaces named are also correct: `/health` and
`/health/detailed` declare no dependency, and `/api/v1/auth/register` is admin-gated with no bound.

**Consequence** — Corrected, and the correction is material because it reverses the effect. Because the proxy
header is ignored, **all production callers behind nginx share one bucket per limiter**, so the five bounds are
present and decide the wrong thing: they are a *global* counter that any unauthenticated caller can exhaust for
everybody, and they do **not** bound a brute-force attempt against a single account, because the attacker does not
need a fresh bucket — the count is already global. The input's consequence sentence, "the login bound is exactly
as drivable as if it were absent", is therefore not the effect: the login bound is not drivable *per caller*; it
is drivable *globally*, which is a denial-of-service surface and a monitoring-noise source, and it is not a
brute-force bypass. The brute-force exposure the input describes would only exist if
`FORWARDED_ALLOW_IPS="*"` were set, and it is not set anywhere.

**Recommendation** — Partly executable, and one of its three changes must be **dropped** before execution.
(1) Make `fail_closed` a required keyword argument, or invert it to `admit_on_redis_error: bool = False`, and
delete the dead `AuthService._rate_limiter`: **executable as written**, and the correct first change because it is
independent of topology. (3) Add `RATE_LIMITER_FAIL_CLOSED` to the dev overlay's app service: **executable as
written**, and the right source to converge on. (2) "Resolve the peer address from `scope["client"]` before any
header middleware has touched it" is **a no-op in the current configuration** — the header middleware never
touches it, because the gate is closed — so implementing it removes nothing and the defect remains. The change
that actually closes the key defect is the one phase 04's validation already reduced to a single item: set
`forwarded_allow_ips` explicitly to the compose network (or the proxy container's address) so the gate opens on
the real proxy and uvicorn's own right-most-untrusted walk produces the true client. The input's parenthetical —
"never `*`" — is correct and must survive into execution.

### SEC-004 — `GraphConfigDict` is a `total=False` TypedDict used as a Pydantic field type, so undeclared chart keys are silently discarded at the boundary instead of refused

**Severity** — MEDIUM

**Zone** — 6. Untrusted Structure That Selects What Is Read

**Disposition** — **confirmed**, band unchanged. Every anchor resolved; the consequence is wider than filed.

**Observation** — `GraphConfigDict` at `src/mkobi/models/types.py:138-152` is a `TypedDict` with `total=False`,
annotated as the type of `GraphBase.config`, `GraphCreate.config` and `GraphUpdate.config` at
`src/mkobi/models/graph.py:15` and `:45`. Pydantic v2 validates a `TypedDict` by checking only the keys it
declares and has no `model_config` on a `TypedDict` to which `extra="forbid"` could be attached, so undeclared
keys are dropped silently and no error is raised. `GraphCreate.model_config` sets only `from_attributes=True`,
confirming that no `extra` policy exists at the model level either. The declared key set is
`x, y, color, xaxis, yaxis, title, layout, yoy, secondary_y, sort_x, sort_color`; `metrics`, `orientation`,
`barmode`, `plot_type`, `stacked` and `showlegend` are **not** in it. This is a property of Pydantic's TypedDict
handling and does not require a runtime reproduction to establish.

**Evidence** — The static proof is the type declaration plus its use as a field annotation; the input's runtime
transcript (three submitted keys dropped, one retained, 201 returned) is consistent with that proof and is
accepted as filed.

**Consequence** — As filed, plus one widening: because the same `config` annotation is on `GraphUpdate` as well
as `GraphCreate`, a **read-modify-write** cycle through the update endpoint compounds the loss — a client that
round-trips a config it previously read will have its undeclared keys dropped on the write, and the config it
reads back differs from the one it sent with no error at any point in the cycle. The failure is invisible at both
ends, which is what makes it more than a cosmetic gap: the stored dashboard and the caller's intent diverge with
no reconcilable signal.

**Recommendation** — Executable, and the input's own caution is the load-bearing part: `extra="forbid"` on
`GraphCreate`/`GraphUpdate` **would not catch this**, because the excess keys are nested inside `config` and a
model-level `extra` policy does not descend into a `TypedDict` value. A `field_validator(mode="before")` on
`config` that raises `AppException(code=ErrorCode.VALIDATION_ERROR)` naming the undeclared key, or replacing the
`TypedDict` with a Pydantic model carrying `extra="forbid"`, are the two shapes that actually close it. The named
pre-check — frontend chart builders that currently send undeclared keys and rely on the silent drop — is a
genuine remediation blocker and is unresolved by the input; see VAL-15-004.

### SEC-005 — A rejected password change writes the plaintext current and new passwords to the log sink and returns them in the response body

**Severity** — HIGH

**Zone** — 3. Credential Material in Everything Else That Persists

**Disposition** — **confirmed**, band unchanged. Reproduced in full at the current tree, in both sinks, through
the project's own handler. The recommended fix is confirmed **not** to break the RFC 7807 contract — and is in
fact a conformance fix.

**Observation** — (a) The handler really does copy `input`. `request_validation_exception_handler`
(`src/mkobi/utils/exceptions.py:263-297`) logs `exc.errors()` at ERROR at `:272-275` and, at `:285-290`, builds
each response entry as `clean_err = dict(err)` — a **shallow copy with no key removed**; the only mutation is
`ctx.error` → `str(...)`. The list is returned verbatim in the `errors` array at `:291-296`. Nothing anywhere in
the handler, the model layer or the `ErrorResponse` schema filters or redacts `input`.

(b) Which password fields land in it, re-derived from Pydantic's own error construction and confirmed at
runtime. A `model_validator(mode="after")` failure carries the **entire validated body dict**; a `field_validator`
failure carries **the offending field's value alone**; a `missing`-field failure carries the **whole body dict**
minus the missing key. `ChangePasswordRequest` (`models/auth.py:178-208`) has three bare `str` password fields
and both a `model_validator(mode="after")` at `:196-201` and a `field_validator` on `new_password` at
`:203-208`, so all three shapes apply to it. Measured against the real model:

| Trigger | `loc` | `input` reaching both sinks |
|---|---|---|
| `new_password != confirm_password` | `('body',)` | the **whole dict** — `current_password`, `new_password`, `confirm_password` |
| `new_password` too short | `('body','new_password')` | the **new password alone** |
| `new_password` / `confirm_password` absent | `('body','new_password')` etc. | the **whole dict** as sent, incl. `current_password` |

(c) The sinks persist it. A real `logging.FileHandler` on the handler's output path captures
`current_password`, `new_password` **and** `confirm_password` in cleartext for the mismatch case, and the record
is `RequestValidationError raised: [{'type': 'value_error', 'loc': ('body',), 'msg': 'Value error, Passwords do
not match', 'input': {'current_password': 'MyOldSecret9', 'new_password': 'NewSecret123', 'confirm_password':
'Mismatch123'}, …}]`. The shipped sink is a `RotatingFileHandler` at `maxBytes` 10 MB with `backupCount` 5
(`src/mkobi/core/logging_config.py:114-122`), and `LOGGING__LOG_FILE=/app/data/logs/app.log` is set on both the
app and rq-worker services (`docker/docker-compose.yml:129` and `:224`). The 422 body carries the same
`errors[0].input` dict back to the client.

(d) The blast radius is the whole request-validation surface, not one route. The mechanism is the *handler*, so
every request model in the codebase that fails validation is affected, present and future. Secret-bearing models
beyond `ChangePasswordRequest` that reach a validation failure on the same path: `RegisterRequest.password`
(`models/auth.py:100`, bare `str`, with the same `validate_password_or_raise` field validator at `:114-119`, so a
strength failure echoes the attempted password alone) and `LoginRequest.password` (`models/auth.py:14`, bare
`str`, which echoes the submitted password alone when the body is not a string — the one such model reachable
without a session). The adjacent leak the input did not name: the frontend's
`extractApiError` returns `details: { validation_errors: validationErrors }` — the **whole errors array including
`input`** — so the plaintext continues past the response body into whatever logs or reports the client-side
extraction result.

**Evidence** — Reproduced in this run: a `FastAPI` app carrying the project's own `auth` router and
`add_exception_handlers`, with the three `change-password` dependency callables overridden, POSTed the three
bodies above and the resulting status, `errors[].input` and log-file contents read back. Status 422 on all
three; `errors[0].input = {"current_password": "MyOldSecret9", "new_password": "NewSecret123",
"confirm_password": "Mismatch123"}` on the mismatch; all three plaintexts present in the log file; the temporary
log directory removed afterwards. The static side is `exceptions.py:272-275` and `:285-296` against
`models/auth.py:196-201` and `:203-208`.

**Consequence** — As filed, and the effect is larger than the response body. The current password is by
definition a working credential at the moment of the failure; it reaches a file that is **rotated rather than
truncated** and is retained for five 10 MB generations, on a path inside the `app_data` volume, and it is echoed
back over HTTP to a browser. The trigger is a **typo in a confirmation field** — no adversary, no malformed
request — so this is a path that ordinary traffic walks into, and the resulting log volume is proportional to
ordinary user error rather than to attack.

**Recommendation** — Executable, and the input's framing of the fix as a possible contract break is **refuted in
its favour**: stripping `input` *converges with* the shipped specification rather than breaking it. Three
independent confirmations, all re-derived this run: (i) `docs/08-security/error-format.md:91-94` documents the
`errors` array entries as `{ "loc", "msg", "type" }` — **`input` is not in the documented shape at all**, so
removing it brings the implementation into line with the spec; (ii) the frontend reads only `err.loc` and
`err.msg` (`extractFieldErrors` in `frontend/src/shared/api/errorHandler.ts`) and its `ValidationFieldError`
interface declares `input?: string` as **optional** — and that declaration is already wrong today, because the
backend sends a **dict** for a whole-body failure, so any code trusting the declared type would already be
reading a string where an object is; (iii) the only shipped test touching the array,
`tests/test_auth_api.py:556-560`, asserts `"do not match" in str(data.get("errors", []))` — it matches on `msg`,
so it **passes unchanged**. The input's Rollout Safety is therefore correct on the frontend path and, unlike the
input, this validation also confirms the test suite is not a blocker. The input's named defence-in-depth step
(`SecretStr` on the password fields) should be kept and taken *first*: it removes the value at the source, so the
handler no longer has anything to leak even if a future error path regresses, and it also fixes the frontend's
`input?: string` type inaccuracy. The input's claim that "any shipped test asserting the current `errors[].input`
shape must change" is **not substantiated** — no such test exists; see VAL-15-002.

### SEC-006 — The unauthenticated `/health/detailed` returns the database driver's exception text, including the database role name, to any caller

**Severity** — MEDIUM

**Zone** — 5. Unauthenticated Inbound Writes: the Surfaces That Accept a Caller's Structure with No Session

**Disposition** — **confirmed**, band unchanged. One factual correction: `/health/detailed` performs no *write*,
so the zone title it is filed under is a paraphrase and the finding is a boundary-disclosure finding, not an
inbound-write finding.

**Observation** — `detailed_health_check` (`src/mkobi/app.py:298-359`) declares no `Depends`, so any caller
reaches it. On database failure it puts `str(e)` into the response at `:320-326` inside a **200** response. The
other disclosures are re-derived and confirmed at the source: a filesystem path (`"path": "frontend/dist"`,
`:330-333`), whether a frontend bundle is present, and the reconciler's internal counters (`sweep_count`,
`unprotected_ticks`, `last_success_at`, `lease_state`, `:349-356`) — the last of which reports whether *this*
replica currently holds the cleanup lease. The two reproduced bodies are accepted as filed: a DNS failure yields
`[Errno 11001] getaddrinfo failed` and an authentication failure yields `password authentication failed for user
"mkobi_app"`, which discloses the database role name from an unauthenticated endpoint in a 200.

**Evidence** — `app.py:320-326` as the interpolation site and the absence of any `Depends` on the route at
`app.py:298` are both re-read this run; the role name in the second body is corroborated independently by
`docker/init-scripts/01-create-app-role.sh`, which creates exactly one such role.

**Consequence** — As filed. The role name is a reconnaissance primitive, the health surfaces are unauthenticated
and carry no attempt bound, and the reconciler state discloses which replica is doing maintenance.

**Recommendation** — Executable. Replace `components["database"]["error"] = str(e)` with a stable reason-free
value; the server-side detail is already logged at `app.py:321`, so nothing operator-facing is lost. The
input's own framing of the two options — gate it with the existing `require_admin_role` if it is for operators,
reduce the body to readiness if it is for everyone — is the right fork and is the reader's to take; this
validation records only that both resolve the finding and that the change is one line in the first case.

### SEC-007 — A 500 produced by the application's own exception handler leaves the process carrying none of the three security headers the application sets

**Severity** — MEDIUM

**Zone** — 8. Response Headers at the Application, and What a Deployment without the Delegating Tier Emits

**Disposition** — **confirmed**, band unchanged. The mechanism is Starlette's, not this project's, and the input
says so.

**Observation** — `SecurityHeadersMiddleware.dispatch` (`src/mkobi/app.py:67-87`) sets
`X-Content-Type-Options`, `X-XSS-Protection` and `Referrer-Policy`, plus `Strict-Transport-Security` and
`Content-Security-Policy` when `ENV=production`. The resolved middleware stack is
`ServerErrorMiddleware → SecurityHeadersMiddleware → GZipMiddleware → CORSMiddleware → ExceptionMiddleware →
routes`, and `ServerErrorMiddleware` is the component that invokes the `Exception` handler registered at
`utils/exceptions.py:330-345` — so the 500 class is produced **outside** the header middleware. The measured
result is accepted as filed: 500 with no `X-Content-Type-Options` and a header set of only `content-length` and
`content-type`, while `/health` in the same process returns 200 **with** the header. The deployment half is also
re-derived: `docker/nginx/nginx.conf:20-30` sets the framing and CSP headers with `always`, and the dev stack runs
no nginx — the dev services are `db`, `migrate`, `app`, `redis`, `rq-worker`, `frontend`, while `nginx` is gated
behind `profiles: [production]` — so in the offered dev deployment no component sets `X-Frame-Options` or CSP at
all, because the application sets `X-Frame-Options` nowhere.

**Evidence** — The middleware ordering and the measured header sets from the running application, plus the
isolated Starlette reproduction that confirms the mechanism is the framework's (`500 has XCTO: False` while
`200 has XCTO: True` on a bare `Starlette` app with one user middleware and an `Exception` handler).

**Consequence** — As filed: nil in production behind nginx, real in the dev deployment, which is the tier an
operator debugs against and a new contributor runs.

**Recommendation** — Executable, three lines. Have `global_exception_handler` stamp the same three headers on the
`JSONResponse` it builds. The input's document-and-decide framing for the missing `X-Frame-Options` is correct
and is deliberately **not** re-litigated here: the middleware's own docstring is accurate, so the documentation is
not over-claiming and the gap is a deployment decision, not a code defect.

### SEC-008 — Failure detail is copied from the Python exception into the response body on ~25 sites, and the worker persists a filesystem path or a Redis endpoint into the durable `processing_logs.message` the status endpoint returns

**Severity** — HIGH

**Zone** — 7. Failure Responses: What an Undecided Failure Puts in the Response

**Disposition** — **confirmed on substance, re-typed on the count.** The mechanism, the two live leaks and the
cross-phase extension all hold. The headline count is wrong in its attribution and is corrected below; the
verdict does not turn on it. Band unchanged.

**Observation — the count, re-derived.** A repository-wide search for `detail=str(` across `src/` returns
**25 occurrences**, and all 25 anchors resolve — so the number is right and the attribution is not. They break
down as: **23 in route modules across 11 files** (`admin.py:91,127,230`; `auth.py:239,510,599`;
`dashboards_access.py:114`; `dashboards_crud.py:151,389`; `dashboards_graphs.py:104`; `data.py:203,209`;
`graphs.py:131,378`; `layouts.py:108,348`; `processing_configs.py:192,265`; `upload.py:242`; `users.py:81,258,312,366`);
**one in `api/deps.py:567`**, which is a dependency, not a route; and **one in `utils/exceptions.py:321`**, which
is not the same construct at all — it reads `detail=str(exc.detail) if exc.detail else get_error_title(code)`,
stringifying the detail the developer supplied to `HTTPException`, not an internal exception, and so is not an
instance of the mechanism the finding describes. `admin.py:230` uses the variable name `exc`, not `e`, which is
why a narrower search misses it. So: 23 sites of the mechanism, 25 occurrences of the token, 11 route modules
rather than the "ten" filed, and one of the 25 is a false member of the set. Two of the 23 need a further note:
`auth.py:510` is `change_password`'s `except ValueError` on the very route SEC-005 is about, so the two findings
touch, and `deps.py:567` is `AuthenticationError` in the auth dependency.

**Observation — the two live leaks, re-derived.** Path A: `enqueue_processing_job` raises
`AppException(code=FILE_PROCESSING_ERROR, detail=f"Failed to enqueue processing job: {e}")` at
`core/task_queue.py:72-77`, interpolating the raw RQ/Redis exception into a response `detail`; the Redis
**service name and port** therefore reach the uploading caller. Path B: on processing failure the worker writes
`message=f"Processing failed: {error_msg}"` with `error_msg = str(e)` at `workers/data_worker.py:571-594` and
`:606-631`; `ProcessingLog` has no name or path column, and `DataService.get_processing_status` returns
`filename=log.message or "unknown"` **and** `message=log.message` at `services/data_service.py:335-341`, so a
container-internal upload path is stored in PostgreSQL and served back as the response's `filename` field on
every status poll.

**Observation — the authentication requirement of each leak, established individually as asked.** Neither leak
is reachable by an unauthenticated caller, so neither is a SEC-006-class exposure. `enqueue_processing_job` is
reached from the upload path, whose dependency is editor-or-above; `/api/v1/upload/status/{task_id}` requires a
session and resolves the task against the requesting user. Both leaks are therefore **authenticated-surface**
disclosures: an editor or above learns the container's absolute upload directory, a UUID, their own supplied
filename, or the internal Redis endpoint with its port. That is a materially smaller blast radius than the
unauthenticated `/health/detailed` leak in SEC-006, and it is the reason the two are not merged.

**Evidence** — `core/task_queue.py:76` as the interpolation site; `workers/data_worker.py:571,590` and
`:606,629` as the persistence sites; `services/data_service.py:335-341` as the read-back; the count derived by
searching `detail=str(` across `src/` and classifying all 25 hits. The measured exception strings
(`Error 11001 connecting to redis:6379`, `The system cannot find the path specified. (os error 3): /app/data/
tmp_uploads/upload_9f2c_deadbeef_sales.csv`) are accepted as filed.

**Consequence** — As filed for the two leaks, with the blast radius corrected: an authenticated editor, on the
normal upload-and-poll failure loop, receives the container's upload directory, a UUID and the caller-supplied
filename in a 200 response's `filename` field, or the internal Redis endpoint with its port. Both values are
durable. The mechanism claim — that the next exception surfacing at any of these 23 sites is returned verbatim
too, because there is no closed vocabulary — is the durable part of the finding and is unaffected by the count
correction.

**Recommendation** — Executable, and the three parts stand as filed with one correction: the two live leaks
(`task_queue.py:76` and the two `data_worker.py` persistence sites) are one-line and two-line changes
respectively, and the `processing_logs.message` change is a durable-schema-neutral change because the column is
free-form text. Change (3) — replacing the 23 sites with a mapping derived from the `ErrorCode` already passed
to `get_error_title` — is the one that closes the class, and the count to plan against is **23**, not 25;
`exceptions.py:321` and `deps.py:567` need separate consideration because neither is the same construct.

### SEC-009 — The access token sits in `sessionStorage` in every non-production build, reachable by any script in the page, gated only by a build flag

**Severity** — LOW

**Zone** — 1. The Stored Password: Encoding, Parameters, and the Policy Around It

**Disposition** — **confirmed**, band unchanged. One note on scope and one correction of the recommendation.

**Observation** — `frontend/src/features/auth/model/authToken.ts:74` sets
`USE_MEMORY_STORAGE = import.meta.env.PROD`; when false the same accessors read and write
`sessionStorage['access_token']` at `:89`, `:124`, `:139` and `:148`, and when true they touch only the
module-level `memoryToken` at `:66`. The dev stack runs the Vite dev server
(`docker/docker-compose.override.yml:37-57`), so the storage path is the live one in every `npm run dev`. The
refresh credential is unaffected — it is an HttpOnly cookie set by `set_secure_cookie`
(`core/security.py:416-441`) and never enters JS. The invariant is asserted by a comment at `authToken.ts:64`
("This mode MUST NEVER be used in production builds") and by nothing mechanical: no assertion, no lint rule, no
test that fails when the storage path is live.

**Evidence** — `authToken.ts:74` and the four `sessionStorage` call sites; the dev frontend service definition;
`core/security.py:416-441` for the HttpOnly refresh cookie.

**Consequence** — As filed, and correctly graded LOW: in the dev deployment any script in the page origin can
read a bearer credential that is short-lived (30 minutes) and dies with the tab. The production build is
unaffected, so the blast radius is one tab on a development machine.

**Recommendation** — Executable. Of the two shapes offered, the `VITE_ALLOW_INSECURE_TOKEN_STORAGE` opt-in
asserted by a unit test is the correct one and the input is right to prefer it over deleting the branch: deleting
the branch removes dev convenience for no security gain in a tier where the storage path is the *intended*
behaviour. The input's remediation note that `authToken.test.ts:11-16` "documents the dev-mode expectation and
would need to be inverted" is **correct in direction but mislabelled** — a test asserting the dev behaviour is
not a defect-encoding test here, because the dev behaviour is the intended one; what must change is the
*assertion that the production build takes the memory path*, which currently has no test at all. That is an
addition to the plan, not a removal from it.

## Validation-Level Findings

Four defects in the report itself. These are graded on the validation scale and counted separately; the audited
phase's identifiers and bands above are untouched.

### VAL-15-001 — SEC-003 asserts a caller-chosen rate-limit bucket that three sibling reports and its own cited evidence refute, offers a no-op and a bypass as the two key fixes, and describes the present state as the post-fix hazard

**Severity** — MEDIUM

**Zone** — Block 6, cross-phase conflict, ownership and merge; asserted cause tested separately

**Disposition** — **substantiated against the report**, merged into phase 04's AUTH-001 for the claim itself.

**Observation** — This is the reconciliation the coordinator asked for, and it resolves in three parts.

*The claim.* SEC-003's Observation asserts that `request.client.host` is uvicorn's proxy-header value, that nginx
appends rather than overwrites, and therefore "the caller chooses the key"; its Consequence then states that "the
five counters are per-callable, not per-caller" and that "the login bound is exactly as drivable as if it were
absent". That chain omits uvicorn's trust gate. Re-derived from the installed uvicorn **0.49.0**:
`uvicorn/config.py` sets `forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")` when the flag
is `None`, and `uvicorn/middleware/proxy_headers.py:34` reads `if client_host in self.trusted_hosts:` and reads
`X-Forwarded-For` **only inside that branch**. `FORWARDED_ALLOW_IPS` appears **nowhere** in this repository — no
compose environment, no Dockerfile, no launch command, no doc — and the only uvicorn launch is
`docker/docker-compose.override.yml:119` with `--host/--port/--reload/--reload-exclude` only. The effective trusted
set is `{"127.0.0.1"}`; the app's TCP peer is the nginx container in production and the Vite container in dev,
neither of which is in it; the gate never opens; and `request.client.host` is the **proxy's** address for every
request. The caller does not choose the key. The defect is the opposite one: all callers behind a given proxy
share one bucket.

*The contradicting corpus.* Three sibling reports say so, and one of them is the evidence SEC-003 cites for
itself. Phase 04's AUTH-001 (HIGH) states that `request.client.host` "is the transport peer, not the caller",
that no forwarded-header trust is installed, that `forwarded_allow_ips='127.0.0.1'` is uvicorn's own default, and
that behind either shipped proxy the value is "one constant for every caller" — then measures six distinct
`X-Forwarded-For` values through the project's own Vite proxy collapsing to the single key `login:172.21.0.2`.
Phase 07's EXT-004 (HIGH) is titled "The whole inbound budget collapses onto the proxy's address: five distinct
callers charged one key". SEC-003 cites that same five-callers measurement as an *instance of the caller-chosen
key*; `172.21.0.7` is a container bridge address, and a bridge address serving five distinct callers is a
measurement of the collapse, not of caller choice. Phase 04's VAL-04-001 (MEDIUM) had already ruled that reading
the left-most `X-Forwarded-For` entry — the shape SEC-003's own recommendation offers — is a brute-force bypass.

*The seam.* `.kilo/commands/audit/phases/15-audit-security-baseline.md:87-90` states, in block 4's own words,
that "What identity a bound is keyed on, and whether the caller can choose it, is **04's**" and that "Whether a
surface is rate-bounded at all is this block's". SEC-003's zone is block 4, and the key clause is the clause
block 4 disclaims. The report half-noted this — "This is phase 04's AUTH-001 …; it is cited, not re-filed" — and
then asserted the mechanism anyway, which makes the finding a wrong approval of a bypass that phase 04 has
already measured to be the opposite defect.

*The recommendation.* Its three parts split cleanly. Part (1), making `fail_closed` a required argument and
deleting the dead `AuthService._rate_limiter`, is correct. Part (3), adding `RATE_LIMITER_FAIL_CLOSED` to the dev
overlay, is correct. Part (2) offers two shapes and **both fail**: "resolve the peer address from
`scope["client"]` before any header middleware has touched it" is a no-op today, because the header middleware
never touches it — the gate is closed — so implementing it removes nothing; and the `forwarded-allow-ips` shape is
correct only when it names the real proxy, which the input states in a parenthetical rather than as the fix. The
change that actually closes the key defect is absent from the report.

*The rollout characterisation.* The Rollout Safety paragraph says the key change "would instead present the nginx
container's address, which means **all production callers would collapse onto one bucket** until nginx is also
trusted correctly. Do not ship the key change alone." That sentence describes the state that **already exists**.
The paragraph warns against a transition whose destination is the present state, and the ordering it prescribes —
trust the proxy first, then take the real peer — is the correct ordering for a transition that is not the one
being contemplated. The genuine hazard, and the one a reader must be told, is the reverse: `forwarded-allow-ips`
is what *introduces* per-caller keying, so a `*` value introduced while fixing the collapse is the bypass, and
enabling the gate is itself a behaviour change that must be verified in a deployed topology.

**Consequence** — A remediator who follows SEC-003 as written implements one of two things, neither of which
fixes the limiter: a no-op, or a caller-chosen bucket. A reader who relies on the Consequence concludes the login
bound is a per-caller brute-force bypass and over-prioritises the wrong remediation, while the defect that is
actually live — a global counter any unauthenticated caller can exhaust for every user — goes unaddressed
because it reads as someone else's finding. The phase-15 report and phase-04's report reach opposite conclusions
about the same subject.

**Recommendation** — Three edits, none of which is a code change. (a) Delete the key-derivation clause from
SEC-003's Observation and Consequence, and replace it with a cross-reference to AUTH-001 and EXT-004 stating that
the bound is present, keyed on the proxy's address, and therefore shared; the surviving substance of SEC-003 — the
two-defaults disagreement, the dead instance, the dev-overlay gap — stays in this phase because block 4 owns
"whether a surface is rate-bounded at all" and because no other phase owns a class default that contradicts the
settings default. (b) Replace recommendation part (2) with phase 04's reduced item: set `forwarded_allow_ips`
explicitly to the proxy container's address or the compose network, so uvicorn's own right-most-untrusted walk
produces the true client, and never `*`. (c) Rewrite the Rollout Safety paragraph for the real transition: the
collapse is today's state, enabling the gate is the change, `*` is the bypass, and the verification must be a
`docker inspect` peer check plus a multi-caller key observation in the deployed topology. **Merge ruling:** the
key-derivation claim is **merged into phase 04's AUTH-001**, which already owns and has already measured it;
AUTH-001 and EXT-004 are not renumbered and this report does not edit either sibling file. **Named remediation
blocker, newly established:** `tests/test_rate_limiting.py:124` hardcodes `rate_limit_key = "login:127.0.0.1"`
and pops that key at `:138-139`, so any change to the key derivation breaks that test; phase 04's VAL-04-002
already records it for AUTH-001 and it applies identically to this phase's step.

### VAL-15-002 — SEC-005 presents its recommended fix as a possible break of the RFC 7807 contract when the shipped specification already omits `input`, and names a remediation blocker that does not exist

**Severity** — MEDIUM

**Zone** — Block 5, whether the recommendation can be carried out

**Disposition** — **substantiated**; the fix is confirmed correct and the risk framing around it is wrong.

**Observation** — The fix the report recommends — drop `input` from `clean_err` before both the log and the
response — is correct, and the report describes its own Rollout Safety with the hedge "removing `input` from the
422 array does not affect either path", which is true but misses the stronger fact: **removing `input` conforms to
the shipped specification.** `docs/08-security/error-format.md:91-94` documents the `errors` array entries as
`{ "loc": [...], "msg": "...", "type": "..." }` — `input` appears nowhere in the documented shape, in either the
422 example or the field table at `:42`. The implementation has been carrying a field the project's own error
format document does not define, so the handler is the deviation, not the fix.

Two corroborations that the fix is contract-neutral. The frontend reads only `err.loc` and `err.msg`
(`extractFieldErrors`, `frontend/src/shared/api/errorHandler.ts`) and its `ValidationFieldError` interface
declares `input?: string` as **optional** — and that declaration is already wrong today, because the backend
sends a **dict** for a whole-body failure and a **string** for a field failure, so any code trusting the declared
type would already be reading an object as a string. And the only shipped test that inspects the array,
`tests/test_auth_api.py:556-560`, asserts `"do not match" in str(data.get("errors", []))`, which matches on `msg`
and therefore **passes unchanged**.

The consequence of the misframing is not the fix (which is right) but the reader: a reviewer told the change
might break the error contract will either defer it or add compensating work, and the report's own "any shipped
test asserting the current `errors[].input` shape must change with it" sends them looking for a blocker that does
not exist. A repository-wide search for consumers of the `input` key across `tests/`, `frontend/src` and `docs`
returns one hit, `frontend/src/features/admin/ui/ResetPasswordResultDialog.tsx:54`, and that is a Material-UI
`slotProps.input` object literal, not a consumer of the error field.

**Evidence** — `docs/08-security/error-format.md:42` and `:91-94` read in full this run;
`frontend/src/shared/api/errorHandler.ts` `extractFieldErrors` and
`frontend/src/shared/types/api.types.ts` `ValidationFieldError` (`input?: string`); the single `tests/` reference
at `tests/test_auth_api.py:556-560`; the consumer search across `tests/`, `frontend/src` and `docs`.

**Consequence** — The correct, specification-mandated, single-line fix carries a recorded risk that does not
exist, and the record omits the two things a remediator actually needs: that `docs/08-security/error-format.md`
should be cited as the authority for the change, and that **no regression test guards the current shape**, so
without an added test the same `input` copy can be reintroduced silently. The absence of a guard is the real
gap and the report does not name it.

**Recommendation** — Restate the recommendation as a conformance fix with `docs/08-security/error-format.md:42`
and `:91-94` cited as the authority; delete the "any shipped test asserting the current `errors[].input` shape"
clause and replace it with the opposite instruction — add a test asserting that a `ChangePasswordRequest` 422
carries no `input` key and that the log record for it contains neither the current nor the new password, since
nothing currently guards either property. Keep the `SecretStr` defence-in-depth step and take it first, as filed:
it removes the value at the source and simultaneously corrects the frontend's `input?: string` declaration.

### VAL-15-003 — The `detail=str(e)` inventory is 25 occurrences of the token but 23 instances of the mechanism, across 11 route modules rather than ten, and includes one non-member

**Severity** — LOW

**Zone** — Block 1, the claim re-derived from the executing path

**Disposition** — **substantiated**; the mechanism claim and both live leaks are unaffected.

**Observation** — SEC-008's headline is "`detail=str(e)` appears on **25 route sites** across **ten route
modules**", immediately followed by an enumeration of 23 anchors and then "plus `deps.py:567` and
`exceptions.py:321`". Re-derived: a search for `detail=str(` across `src/` returns 25 anchors, and they decompose
as **23 in route modules across 11 files** (`admin.py:91,127,230`; `auth.py:239,510,599`;
`dashboards_access.py:114`; `dashboards_crud.py:151,389`; `dashboards_graphs.py:104`; `data.py:203,209`;
`graphs.py:131,378`; `layouts.py:108,348`; `processing_configs.py:192,265`; `upload.py:242`;
`users.py:81,258,312,366`); **one in `api/deps.py:567`**, which is a dependency rather than a route; and **one in
`utils/exceptions.py:321`**, which is a different construct entirely —
`detail=str(exc.detail) if exc.detail else get_error_title(code)`, stringifying the detail a developer supplied
to `HTTPException`, not an internal exception, and therefore not an instance of the mechanism the finding
describes. Two further precision points: `admin.py:230` binds the exception to `exc` rather than `e`, so a search
for the exact token `detail=str(e)` finds 24 and misses it; and `auth.py:510` is `change_password`'s own
`except ValueError`, the same route as SEC-005, and `deps.py:567` is `AuthenticationError` inside the auth
dependency. All 25 anchors resolve, so nothing here is a wrong approval — the numbers are misattributed, and the
finding survives on its mechanism and its two confirmed leaks.

**Consequence** — A remediator planning recommendation (3) — "replace the 25 `detail=str(e)` occurrences with a
mapping from the `ErrorCode`" — sizes the change against two sites that are not instances of the mechanism
(`deps.py:567` is a JWT-library error whose text is already curated upstream, `exceptions.py:321` is a
developer-supplied detail) and against a route-module count that is 11 rather than 10. Neither mis-sizing changes
the fix's shape, and the mechanism claim — that there is no closed vocabulary, so the next exception surfacing at
any of these sites is returned verbatim — rests on the absence of a closed set rather than on the count.

**Recommendation** — Restate the inventory as "23 sites across 11 route modules, plus one dependency site and one
non-member", and plan recommendation (3) against the 23. For `deps.py:567` the decision is separate and should be
taken on its own merits (whether a JWT library message is an acceptable response string); `exceptions.py:321`
should be removed from the inventory rather than changed.

### VAL-15-004 — SEC-004's unresolved pre-check is resolved and the consequence is larger: the shipped frontend read path depends on the two keys the backend guarantees are absent

**Severity** — LOW

**Zone** — Block 5, whether the recommendation can be carried out

**Disposition** — **substantiated**; the finding and its band are unchanged, the remediation blocker is now named.

**Observation** — SEC-004's recommendation closes with a conditional the report never discharges: "Before
changing, check for shipped tests and frontend chart builders that currently send undeclared keys and rely on them
being ignored." That check is answerable in the current tree and its answer is worse than "some tests rely on it".
`frontend/src/shared/types/api.types.ts:209-215` declares
`GraphDataWithConfig.config?: { x?, color?, metrics?, orientation?, barmode? }` — of which `metrics`,
`orientation` and `barmode` are **not** in the backend's `GraphConfigDict`. The read path then depends on two of
them: `frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx:18` reads
`const orientation = config.orientation || 'v'` and applies it at `:37`, and `:149` reads
`barmode: (graph.config?.barmode || 'group')`; `:105-106` reads `layout.showlegend`. So the application ships a
frontend that reads two keys the backend's boundary contract guarantees are not present, and falls back to
defaults on every render. The defect is therefore live today, not a latent acceptance of an unconstrained key
set, and the silent-drop is load-bearing for the frontend's rendering path rather than merely permitted.

**Consequence** — The consequence the input states — "the caller receives 201 and reads back a config that does
not match what it sent, with no way to learn which part was discarded" — is correct but understates the reach: the
discarded keys are keys the *shipped client* expects to read back, so a caller who sets `barmode` and reads the
chart back sees the default `group` and has no signal that the value they stored was removed. Two independently
authoritative components disagree about the same schema and neither is told.

**Recommendation** — Name `frontend/src/shared/types/api.types.ts:209-215` and `ChartRenderer.tsx:18,37,105-106,149`
as the reconciliation surface the fix must cover: the key set has to be agreed between `GraphConfigDict` and
`GraphDataWithConfig` in the same change, in whichever direction the product decides, and a
`field_validator(mode="before")` that refuses an undeclared key will otherwise turn a currently-silent frontend
mismatch into a 422 on a path the client walks.

## Disposition Tally

| Finding | Executing path re-derived | Anchor resolved | Claim on its own terms | Asserted cause, tested separately | Band carried | Band under phase-15 rubric |
|---|---|---|---|---|---|---|
| SEC-001 | `security.py:37-38,154-187,208,236`; `auth.py:100,114-119,181-183,203-208`; `auth_service.py:498-505`; `tests/test_security.py:19-32` | yes, all | **confirmed** | correct; no `max_length` anywhere in `src/mkobi/models/` | MEDIUM | MEDIUM |
| SEC-002 | `temp_password_store.py:39-41,50-75`; `config.py:581`; `auth_service.py:577-583`; `admin.py:320-321`; `docker-compose.yml:172-188` (re-derived) | yes, all | **confirmed, re-typed** (owned here) | correct | HIGH | HIGH |
| SEC-003 | `config.py:578`; `security.py:107,137-151`; `auth.py:84-86,310-312,562-564,89,314,566`; `client_errors.py:45-49`; `upload.py:144-149`; `auth_service.py:66-68`; uvicorn 0.49.0 `config.py` + `proxy_headers.py:34`; repo-wide `FORWARDED_ALLOW_IPS` search = no hit | yes, all | **confirmed on substance; the key clause is not substantiated** | **refuted** — the trust gate is closed, so the key is the proxy's address, not caller-supplied (VAL-15-001) | HIGH | HIGH |
| SEC-004 | `types.py:138-152`; `graph.py:15,45`; `api.types.ts:209-215`; `ChartRenderer.tsx:18,37,105-106,149` | yes, all | **confirmed** | correct; consequence widened (VAL-15-004) | MEDIUM | MEDIUM |
| SEC-005 | `exceptions.py:263-297` (`:272-275`, `:285-296`); `auth.py:178-208,465-523`; `logging_config.py:114-122`; `docker-compose.yml:129,224`; reproduced through the project's own handler | yes, all | **confirmed in both sinks** | correct | HIGH | HIGH |
| SEC-006 | `app.py:299,320-326,330-333,349-356`; `/health` at `:278-297` returns no `str(e)` | yes, all (route at `:299`, filed as `:298`) | **confirmed** | correct | MEDIUM | MEDIUM |
| SEC-007 | `app.py:67-87`, `add_middleware` at `:248,257,263`; `exceptions.py:330-345`; nginx `profiles` gate | yes, all | **confirmed** | correct — Starlette's ordering, as the report says | MEDIUM | MEDIUM |
| SEC-008 | 25 `detail=str(` anchors classified individually; `task_queue.py:72-77`; `data_worker.py:571-594,606-631`; `data_service.py:335-341` | yes, all | **confirmed on substance; count re-typed** (23 + 2) | correct (VAL-15-003) | HIGH | HIGH |
| SEC-009 | `authToken.ts:64,74,89,124,139,148`; `docker-compose.override.yml:37-57`; `security.py:416-441` | yes, all | **confirmed** | correct | LOW | LOW |

**Tally** — 6 confirmed (SEC-001, SEC-004, SEC-005, SEC-006, SEC-007, SEC-009); 2 confirmed and re-typed
(SEC-002, SEC-008); 1 confirmed on its substance with one clause not substantiated (SEC-003); 0 merged away;
0 re-graded; 0 recorded as unsettled; 0 rejected outright. 6 + 2 + 1 = 9, agreeing with the per-finding verdicts
above and with the input's own `findings: 9`. Bands are unchanged and carry the **phase-15** scale, not the
validation scale: HIGH 4 (SEC-002, SEC-003, SEC-005, SEC-008), MEDIUM 4 (SEC-001, SEC-004, SEC-006, SEC-007),
LOW 1 (SEC-009), CRITICAL 0 — identical to the input's front matter, re-counted against the bodies. No identifier
was renumbered and no band was silently applied.

**No re-grades, and why each of the four HIGH bands survives the phase's own rubric.** The phase-15 taxonomy
grades by effect and blast radius anchored to present state, and states that "a mechanism absent from an
enumerated band is not thereby a lower band". Checked clause by clause: SEC-005 is a verbatim match for the HIGH
clause "a real secret reaches a sink that persists it or hands it to something outside the request", and reaches no
CRITICAL clause, because a CRITICAL clause in this rubric is about a caller reaching an *effect*, not a value
reaching a sink. SEC-008 is a verbatim match for "an undecided failure returns internal detail to the caller".
SEC-003 is a verbatim match for "a control that is present, configured and deciding nothing stands exactly where a
decision was required" — and note that the mechanism *as filed* would have pushed it toward the CRITICAL clause
"an authentication surface drivable without limit", which the corrected mechanism shows is not reached: the bound
exists and is counted, it is simply counted on the wrong key. A finding corrected toward a smaller effect does not
need re-grading downward when the rubric's HIGH clause is met by the surviving substance. SEC-002 is a match for
the HIGH clause "a real secret reaches a sink that persists it" rather than for the CRITICAL clause "a stored
credential another identity can read more than once", because the store's own read path is single-read by design
(`GET+DELETE` in one transaction) and the credential is both single-use and 24-hour-bounded; what is broken is the
stored form's recoverability from the store that holds it, which is the HIGH clause. SEC-007 is a verbatim match
for the MEDIUM clause "a response class leaves the process with no header it claims to set". SEC-001, SEC-004 and
SEC-006 fall in no enumerated band and are graded MEDIUM on blast radius, which the taxonomy permits. SEC-009 is
LOW: its production build is unaffected and the invariant is a build flag, which is closest to the LOW clause
"control metadata that does not resolve against the phase or environment it names".

---

## Distribution

The findings fall on the **request-response boundary** rather than on any single tier, and that distribution
survives re-derivation unchanged. Six of the nine live where a Python value is copied out of an internal object
into something a caller or a log can read. `src/mkobi/utils/exceptions.py` carries the most weight and is the
single heaviest component in the phase: it is both the credential-to-log path (SEC-005) and the error-shape
contract for every route (SEC-008 depends on it). The credential tier is split three ways — at rest (SEC-001), in
the delegated store (SEC-002), in the browser (SEC-009). The admission tier is SEC-003 alone, and after this
validation it is narrower than filed: the posture disagreement is real, the key is phase 04's. The health
surface is SEC-006 alone; the header tier SEC-007 alone.

- `src/mkobi/utils/exceptions.py` — SEC-005 (critical path; also the mechanism SEC-008 depends on)
- `src/mkobi/api/routes/auth.py`, `client_errors.py`, `upload.py`, `core/security.py`, `config.py` — SEC-003
  (after validation: the defaults disagreement and the dev-overlay gap; the key is phase 04's AUTH-001)
- `src/mkobi/core/temp_password_store.py`, `services/auth_service.py`, `api/routes/admin.py` — SEC-002
- `src/mkobi/core/task_queue.py`, `workers/data_worker.py`, `services/data_service.py` — SEC-008
- `src/mkobi/app.py` — SEC-006, SEC-007

## Cross-Finding Analysis

Two causes are shared across findings; the rest are independent. The input's analysis of causes holds on
re-derivation, with one correction of emphasis.

**Cause 1 — an internal value is copied into a caller- or log-visible string with no closed set to copy from.**
SEC-005 (Pydantic's `input` dict into both the log and the response), SEC-006 (`str(e)` into an unauthenticated
response) and SEC-008 (`str(e)` into an RFC 7807 `detail` and into `processing_logs.message`) are one defect in
three places, and the mechanism for two of the three is literally the same line. Re-derivation sharpens this: the
shared root is not three habits but **one missing transformation** — nothing in the codebase converts an internal
value into a response-safe value, so every site independently decided the exception's own text was acceptable.
That is why a container path, a Redis endpoint and three plaintext passwords reach callers and logs by the same
route, and it is why fixing any single site leaves the pattern. The correction to the input's framing: this cause
is *not* independent of SEC-003 and SEC-009, both of which are the same shape one tier out — a value chosen at
runtime (`request.client.host`, `import.meta.env.PROD`) used as if it were a property of the system.

**Cause 2 — a security property is expressed as a call-site convention rather than as a type or a validated
boundary.** SEC-001 (no length bound on any password field, so `_truncate_password` decides), SEC-003
(`fail_closed` passed at five sites over a class defaulting to the opposite) and SEC-004 (a `TypedDict` where a
Pydantic model would refuse unknown keys) are the same shape: the invariant exists as prose or as a caller's care
and nothing structural enforces it. SEC-009 is the client-tier instance. VAL-15-004 belongs to this cause too —
the frontend's `GraphDataWithConfig` and the backend's `GraphConfigDict` are two authoritative declarations of
one schema that were never reconciled, which is the boundary-not-enforced shape at its most literal.

SEC-002 and SEC-007 are independent of both causes: SEC-002 is a storage-encoding choice, SEC-007 is a
middleware-ordering fact about Starlette.

## Roadmap

The input's grouping by cause is sound and is preserved; four corrections and three additions are made, each
named to the finding it comes from.

**Step 0 — correct the plan before executing any of it.** Apply VAL-15-001 (drop SEC-003's key clause, replace
its recommendation part (2), rewrite its Rollout Safety paragraph), VAL-15-002 (restate SEC-005's fix as a
conformance fix and name the missing regression test), VAL-15-003 (plan against 23 sites, not 25) and
VAL-15-004 (name the frontend/backend schema reconciliation as part of SEC-004's fix). *Must be true before step
1:* no step below is executed from a plan that asserts a caller-chosen rate-limit bucket, and no step is sized
against a site that is not an instance of the mechanism.

**Step 1 — close the credential leak (SEC-005).** Take `SecretStr` on the password fields first, then drop
`input` from `clean_err` before both the `logger.error` and the response, then add the regression test the input
did not name. Nothing else in steps 2-4 is more urgent than a working password in a rotated log file, and this is
the smallest diff in the set. *Must be true before step 2:* steps 2 and 3 both change response strings in
`utils/exceptions.py` and re-baseline the same tests, and the suite should be re-baselined once, not three times.

**Step 2 — give failures a closed vocabulary (SEC-008, SEC-006).** Requires step 1. Then, in the input's order:
`task_queue.py:76` stops interpolating (chain with `from e`, matching the shape `upload.py:244-249` already
uses); `data_worker.py` persists a stable per-failure-class message and keeps the full text in `logger.exception`;
`/health/detailed` stops returning `str(e)`; and the 23 `detail=str(` sites are replaced with
`get_error_title(code)`-derived strings. *Must be true before step 4:* step 4 changes password-model validation
tests, and both re-baseline the 422 surface.

**Step 3 — make the rate limiter's decisions structural (SEC-003, minus the key).** Independent of steps 1-2 and
runnable in parallel. Make `fail_closed` a required argument (or invert it to `admit_on_redis_error: bool = False`),
delete the dead `AuthService._rate_limiter`, and add `RATE_LIMITER_FAIL_CLOSED` to the dev overlay's app service.
The key derivation is **not** in this step — it is phase 04's AUTH-001 and belongs to whichever deploy changes
`forwarded_allow_ips`, per the Rollout Safety below. *Must be true before step 5:* any test that drives two
requests through `TestClient` to prove a counter trips depends on the key, so the key change lands with its own
tests, not with this step.

**Step 4 — bound the credential at the boundary (SEC-001).** Requires step 2's test re-baselining. Reject
over-length input on `RegisterRequest.password` and `ChangePasswordRequest.new_password` by UTF-8 **byte** length
through `validate_password_or_raise`, and make `_truncate_password` raise on the minting side while verification
keeps truncating. *Must be true before step 6:* an audit of already-stored 72+ byte credentials is an
operational follow-on, not a code step, and it is only meaningful once the minting path is closed.

**Step 5 — close the selection surface, the header gap and the browser storage (SEC-004, SEC-007, SEC-009).**
Independent of the above; sequence by diff size. SEC-007 is three lines in the exception handler. SEC-009 is a
variable plus a new test asserting the production build takes the memory path. SEC-004 is the largest of the
three because it now also requires the `GraphConfigDict` ↔ `GraphDataWithConfig` reconciliation named in
VAL-15-004, and because a `field_validator` that refuses an undeclared key turns today's silent mismatch into a
422 on a path the shipped client walks.

**Step 6 — re-encode the delegated credential (SEC-002).** The largest step: credential re-encoding plus a store
migration, scheduled against a deployment rather than a release. See Rollout Safety.

## Rollout Safety

**Steps 1 and 4 are response-shape changes and the input's analysis of the frontend is correct but
incomplete.** `frontend/src/shared/api/errorHandler.ts` reads the legacy 422 array and the RFC 7807 `code`, and
its field extraction uses only `err.loc` and `err.msg`, so removing `input` from the 422 array does not affect
either path — and the *stronger* fact is that `docs/08-security/error-format.md:42` and `:91-94` do not define
`input` in the `errors` shape at all, so the change is a conformance fix. Rejecting over-length passwords is the
part that does change what a user sees: it produces a new 422 the frontend renders through the existing
`VALIDATION_ERROR` + field-extraction branch, which will show `<field>: <msg>` and is adequate — but the
`details: { validation_errors: … }` object it returns carries the whole errors array, so a new
`input`-shaped field on that path would reach the client again. The `SecretStr` change is the one that makes that
structurally impossible. Changing `_truncate_password` to raise breaks `tests/test_security.py::TestTruncatePassword`
(two tests, `:22-27` and `:29-32`), which encode the defect and must change with it.

**Step 2 changes error strings the frontend may display, and one of them is user-visible in a way the input
understates.** `get_error_title`-derived strings are more generic than the interpolated ones, so a user who
currently sees a specific failure reason sees a fixed message — that is the intent, and it should be checked
against the login and upload screens specifically. Two screens need a look rather than one: the
`processing_logs.message` change alters what `/api/v1/upload/status/{task_id}` returns in `filename`, and
`/api/v1/admin/logs` renders the same column (phase 06's ART-002 territory). Separately, `docs/` may quote an
interpolated detail string in an example; the documentation inventory phase 04's VAL-04-010 already opened
should be extended to cover the 23 sites, since a closed vocabulary is only real if the corpus agrees with it.

**Step 3 is safe as scoped and the genuine hazard is in the step that is *not* in it.** The input's own Rollout
Safety is right that the key change must not ship alone, but for a reason opposite to the one it gives, and
VAL-15-001 records the correction. The present state is that every caller behind a proxy shares one bucket,
because `FORWARDED_ALLOW_IPS` is unset and uvicorn's trust gate never opens. The transition that changes
behaviour is therefore **enabling the gate** — setting `forwarded_allow_ips` to the proxy container's address or
the compose network — and that transition is what must ship alone, in its own deploy, with a `docker inspect`
peer check and a multi-caller key observation to verify it. A `*` value at that moment is the brute-force
bypass phase 04's VAL-04-001 already ruled out, and `tests/test_rate_limiting.py:124` hardcodes
`rate_limit_key = "login:127.0.0.1"` and pops it at `:138-139`, so the key change breaks that test and the test
must change with it. Revert for the trust-gate change is a single environment variable, which is why it belongs
in its own step with its own deploy. Enabling the gate for the compose network is safe in the dev tier because
the host-published app port at `docker/docker-compose.override.yml:114-118` binds with no host-IP restriction
while the trusted set would be the network, and the host-published port arrives from the docker gateway, which is
not in it — the contrast with the deliberate loopback binding on `db` at
`docker/docker-compose.override.yml:178-181` (`127.0.0.1:5432:5432`, with a comment saying to limit exposure to
the local machine only) is the reason this is checkable rather than assumed.

**Step 6 is the one that cannot be reverted by redeploying.** Existing `temp_pwd:*` entries are unrecoverable
under a new encoding, so drain the store or accept the 24-hour loss window during rollout, and coordinate with any
pending admin resets and any approved-but-unclaimed registration requests, which take the identical path
(`admin.py:320-321`). Adding `requirepass` to the `redis` service is independently revertible but not
independently deployable: the app, the worker and any local tooling all need the credential at once, and the
healthcheck at `docker/docker-compose.yml:177-181` currently runs a bare `redis-cli ping` with no
`REDISCLI_AUTH`, so it will start failing the moment a password is set unless the healthcheck is changed in the
same commit.

healthcheck at `docker/docker-compose.yml:177-181` currently runs a bare `redis-cli ping` with no
`REDISCLI_AUTH`, so it will start failing the moment a password is set unless the healthcheck is changed in the
same commit.

## Appendices

### The three notable negatives, re-derived

Each was checked because a wrongly-dismissed candidate is a missed finding, and all three **hold as filed**.

**`register-request` does not enumerate accounts — CONFIRMED, and the mechanism is stronger than filed.**
`create_registration_request` raises the byte-identical `ValueError("Unable to process registration request")` on
four distinct conditions: an existing active request (`auth_service.py:423`), an existing rejected request (`:429`),
a blocked email domain (`:437`), and an existing user row (`:443`). The route wraps all of them through the same
`except ValueError` → `detail=str(e)` site at `auth.py:239`, so all four produce an identical response body
despite the mechanism returning raw exception text. One refinement the input did not state: a **fifth** response
shape is distinguishable — the malformed-address guard at `auth_service.py:402-407` raises
`ValueError("Invalid email format")`, which the same `detail=str(e)` site surfaces. That discriminates on *input
syntax*, not on whether an account exists, so it does not enumerate; the negative stands.

**The global exception handler returns no internal text and no traceback — CONFIRMED.**
`global_exception_handler` (`utils/exceptions.py:330-345`) logs server-side and returns
`detail="Internal server error"` with `details=None` and no `exc_info`; the body carries only `type`, `title`,
`status`, `detail`, `code`, `details`. `debug` defaults to `False` (`config.py:542`) and is refused outright in
production by `validate_debug_mode` (`config.py:658-666`). The input's residual limit (3) — a Starlette debug page
with a traceback when `DEBUG=true` under `ENV=development` — is correctly recorded as a limit rather than a
finding, and the refusal does depend on the setting rather than on the handler, which is the honest framing.

**Response shape does not diverge between environments — CONFIRMED, and the tier label is pinned to the compose
file.** The only environment-conditional behaviour in the response path is the two extra headers SEC-007 is about:
`SecurityHeadersMiddleware.dispatch` adds `Strict-Transport-Security` and `Content-Security-Policy` only when
`config.environment == EnvironmentEnum.PRODUCTION` (`app.py:82-85`). Error shape is environment-independent: the
four handlers in `utils/exceptions.py` read no environment flag, and `get_error_title` is a closed mapping. The
tier label is set as a literal in the compose file, not read from an env file that could drift — `ENV: production`
at `docker/docker-compose.yml:63`, `:114` and `:205` (migrate, app, rq-worker), against `ENV: development` at
`docker/docker-compose.override.yml:19`, `:75` and `:139` — which is the state phase 02 verified and which
re-derives cleanly at the current HEAD. The one asymmetry that is *not* a shape divergence is the `debug` refusal
above, which is refused in production rather than changing the shape.

### Cross-phase ownership, and the seam check

| Phase-15 claim | Rival claim | Owner | Disposition |
|---|---|---|---|
| SEC-002: the delegated credential is stored as the credential itself | AUTH-002 (HIGH) — a reset commits the credential even when the store refused the value; AUTH-006 (MEDIUM) — the retrieval endpoint collapses spent / nonexistent / store-down into one 404 | **phase 04** — `temp_password_store.py:47-48` fail-open write and `:73-75` + `admin.py:418-422` single-404 | **The input's deferral is correct.** Block 2 of the phase-15 command file hands "what a failure of the backing store does to the write" to 04 in terms, and the encoding is not covered by either rival. SEC-002 keeps the encoding and stays in this phase; AUTH-002 and AUTH-006 are not renumbered and this report does not edit them. |
| SEC-003: the rate-limit key | AUTH-001 (HIGH) and EXT-004 (HIGH), both the collapse | **phase 04** for the key; phase 07 for the ingress budget | **Merge** — the key-derivation clause is merged into AUTH-001 per VAL-15-001. Phase 04's command file assigns key identity to 04 in terms, and phase 15's block 4 disclaims it in terms. |
| SEC-008: `processing_logs.message` carries a server path and is returned as `filename` | ART-002 (HIGH) — the record never names the artefact; EXT-003 — an unbounded caller string reaching one ERROR record | **phase 06** for the schema divergence and the field substitution; phase 15 for the disclosure content | **Cross-reference, not a merge** — adjacent concerns with the same root shape and different root causes. ART-002 does establish `get_processing_status` filling `filename` from `log.message` (`data_service.py:336` and `:306`); what ART-002 does not establish is that the column carries *server-side* exception text. The input's characterisation of the boundary is accurate. |
| SEC-005: credential material in the log sink | EXT-003 (anonymous 5 MB body as one ERROR record) | both | **Correctly distinguished as filed** — EXT-003 is a caller-supplied string on a deliberately anonymous surface; SEC-005 is credential material on an authenticated surface via the error handler. Different mechanism, different zone. |
| SEC-002: registration approvals mint through the same path (`admin.py:320-321`) | AUTH-002's registration-request reachability | phase 04, already noted by its own validator | **Confirmed and correctly reported inside SEC-002** — `admin.py:320-321` builds `retrieval_token = str(uuid4())` and calls `temp_password_store.store(retrieval_token, temp_password)` with the same plaintext, immediately after `create_user(..., password=temp_password, ...)` at `:307-312`. |

**Seam check — one finding filed outside the phase's declared scope.** SEC-003's key-derivation clause is filed
under block 4, whose own text (`.kilo/commands/audit/phases/15-audit-security-baseline.md:87-90`) states that
"What identity a bound is keyed on, and whether the caller can choose it, is **04's**" and that "Whether a
surface is rate-bounded at all is this block's". The clause is outside the input's declared scope for the zone it
is filed under; the report acknowledges the ownership in one sentence and then asserts the mechanism anyway. Filed
as VAL-15-001; phase 15's *surviving* SEC-003 content is inside scope, because whether a surface is bounded at all
and what the bound's default posture is are both this block's.

**Does the input rest on its own declared blocks and evidence fields?** Eight of the nine findings rest squarely on
the phase's declared blocks: block 1 → SEC-001 and SEC-009, block 2 → SEC-002, block 3 → SEC-005, block 5 →
SEC-006, block 6 → SEC-004, block 7 → SEC-008, block 8 → SEC-007. The exception is SEC-003: its key clause arises
from an angle block 4 explicitly disclaims, which is the seam above. The declared evidence fields were honoured
throughout — every finding carries an artefact rather than a transcript, and the two findings whose evidence is a
transcript (SEC-004, SEC-008) also carry a static proof that would stand without it.

### Anchor drift resolved during this validation

Every anchor the input cites was resolved mechanically before its claim was tested, and eight had drifted between
the input's baseline (`9c49c20`) and this run's baseline (`4a5db54`) while the concurrent remediation programme
was landing. None is a wrong approval: in every case the cited construct exists at or adjacent to the cited line.

| Input anchor | Resolved anchor at `4a5db54` | Note |
|---|---|---|
| `docker/docker-compose.yml:171-176` (redis, no auth) | `docker/docker-compose.yml:172-188` | block re-read in full; `deploy.resources` added, no auth directive added |
| `docker/docker-compose.yml:293-294` (nginx profile) | nginx service now `269-302` | re-derived by enumerating service line ranges |
| `Dockerfile:127,183` (launch flags) | `docker/Dockerfile` is the only Dockerfile; no proxy flag anywhere | the whole-repo search is the stronger evidence |
| `docker/docker-compose.override.yml:119` | resolves; the only uvicorn launch command | — |
| `app.py:298` (`/health/detailed` route) | `app.py:299` | one line |
| `auth.py:566` vs `:562-564` (limiter site) | `:562-564` is the construction; `:566` is the key | both cited forms resolve |
| `data_service.py:335-341` | resolves; `:336` is the `filename` substitution ART-002 cites | — |
| `task_queue.py:76` | resolves | — |
| `security.py:263-297` vs `:272-296` | handler is `263-297`; log at `272-275`, `errors` loop `285-290`, return `291-297` | the input cites both spans; both are correct |
| `models/auth.py:100` (input's `LoginRequest.password`) | `:100` is `RegisterRequest.password`; `LoginRequest.password` is `:14` | the input's own attribution was correct; the error was mine, corrected in SEC-005 |

### Coverage ledger

| Block | Reached | Item count actually examined | Claims left unsettled |
|---|---|---|---|
| 1 — Stored password and browser-resident tier | yes | 5 password fields across 3 models; 2 truncation call sites; 1 strength validator; 1 client-side store | none |
| 2 — Delegated credential store | yes | 2 mint sites, 1 store, 1 TTL setting, 1 compose service body, 1 retrieval path | none — the recoverability verdict is a static proof from the write site and does not need a live instance |
| 3 — Credential material in persisting sinks | yes | 1 handler, 1 request model with 3 password fields, 3 validation-failure shapes, 1 log sink, 1 rotation config, 2 env declarations | none — reproduced in both sinks |
| 4 — Attempt-rate bounding | yes | 5 construction sites, 6 surfaces bounded or not, 1 dead instance, 3 env declarations, 1 uvicorn trust gate, 0 `FORWARDED_ALLOW_IPS` occurrences | **1 settled negatively**: the key derivation was not re-measured inside a live nginx→uvicorn topology; it is settled from the installed library's own source plus the effective `forwarded_allow_ips` value, which is stronger than a transcript, and is corroborated by two sibling measurements |
| 5 — Unauthenticated inbound surfaces | yes | 6 surfaces, each with method, auth, bound, written shape, disclosure | none |
| 6 — Untrusted structure that selects | yes | 1 `TypedDict`, 3 field annotations, 11 declared keys, 6 undeclared keys of interest, 2 frontend consumers | none |
| 7 — Failure responses | yes | 4 handlers, 25 `detail=str(` anchors classified individually, 2 live leak paths, 1 durable column, 1 read-back | none |
| 8 — Response headers | yes | 3 header classes, 5 `add_middleware`/stack positions, 1 delegating-tier config, 1 profile gate | none |

**Unsettled claims: none.** Every claim in the input was settled in this environment. One claim the *input* itself
recorded as a limit is inherited and still stands: SEC-002's recoverability was not demonstrated by a `KEYS
temp_pwd:*` against a live Redis, because no live Redis was reachable; the encoding argument is a two-line static
proof and does not depend on one. The input's other two residual limits (the `DEBUG=true` Starlette debug page,
refused in production at `config.py:658-666` and recorded rather than filed; and the individual classification of
the 23 `detail=str(` sites) were re-checked and both hold as the input states them.

### Method, and what this run did and did not touch

`git rev-parse HEAD` returned `4a5db549875b8e432720f3775c936f3ef04b299c` and `git status --porcelain` returned
53 lines at the start of this run; the input's own baseline was `9c49c204ad83b26b2b76cf6887c48ad09f79d055`, so
the tree moved during the audit and every anchor above was re-resolved against the current tree. No file in the
repository was created, edited, staged, committed, reverted or stashed by this run. No Docker service was started,
stopped or reconfigured; the dev stack was not touched and the frontend coverage gate was not run, per the
`frontend/coverage/` deletions being pre-existing and out of scope.

Runtime evidence: one `starlette.testclient.TestClient` harness over a `FastAPI` app carrying the project's own
`auth` router and the project's own `add_exception_handlers`, with the three `change-password` dependency
callables overridden so the body-validation path is reached, driven against the real `ChangePasswordRequest`; a
real `logging.FileHandler` writing to a temporary directory to prove the log sink receives the plaintext, with
that directory removed afterwards and its absence verified. Library-level evidence: uvicorn 0.49.0's own
`Config` and `uvicorn.middleware.proxy_headers` source, read from the installed package rather than from
documentation. Everything else is a static proof read from the working tree.

**Artefacts consulted** — `.kilo/commands/audit/phases/15-audit-security-baseline.md` (block titles, scope
boundaries, severity taxonomy); `.ai/audit/templates/audit-findings.md`; the raw reports of phases 04, 06 and
07 and the validation report of phase 04, for the four contested claims; `docs/08-security/error-format.md`; and
`src/`, `tests/`, `docker/`, `frontend/src/` as cited per finding. No file in any sibling phase's directory was
modified.

### Template compliance of the input, as a controlled artefact

The input follows the shared template on every mandated element: all six front-matter fields are present and
honest (the `baseline` and `baseline-dirty` fields are additions this audit's phases require, not template
violations), all six per-finding fields are present on all nine findings with no field renamed, and the
**Zone** field quotes the block title **verbatim** on all nine — including SEC-006, whose zone title reads
"Unauthenticated Inbound **Writes**" for a finding about a read-only disclosure, and which is nevertheless
correctly owned, because block 5's own text (`.kilo/commands/audit/phases/15-audit-security-baseline.md:98`)
states "The health surface's own contract … is 10's; what it discloses is this block's". The report carries the
Summary, Findings, Distribution, Cross-Finding Analysis, Roadmap, Rollout Safety and Appendices sections the
template treats as required, and the reserved empty-state string is correctly absent because findings were
produced. Defects recorded rather than edited: the `detail=str(e)` inventory in SEC-008 (VAL-15-003), and the
four report-level defects in VAL-15-001, -002 and -004.

### Finding-ID namespace ruling

`SEC-` is the prefix declared in the phase-15 report-output contract
(`.kilo/commands/audit/phases/15-audit-security-baseline.md:153`) and the input mints `SEC-001` … `SEC-009` under
it. No other phase report in the set mints a `SEC-` identifier, no `SEC-` marker is embedded in shipped source,
configuration, tests or documentation, and the compound form the template's front-matter `phase:` value pairs with
is `SEC-` + the phase number, which is how the input is ordered. No collision exists, and this validation mints
no identifier in the audited namespace: all nine identifiers are preserved, never renumbered.

For validation-level findings the flat `VAL-` prefix is **not** available. The phase-01 and phase-02 validation
reports hold `VAL-001` … `VAL-008` and `VAL-001` … `VAL-009` respectively — two sibling reports already colliding
with each other — and `VAL-06-` through `VAL-14-` and `VAL-16-` are taken as phase-qualified variants by the
remaining validation reports. Minting into that space would create a third variant of the same identifiers.
This report therefore mints `VAL-15-001` … `VAL-15-004` in its own section, occupying the same `VAL-` namespace
with a phase-qualified infix rather than a second one, and the deviation is recorded here. Per the phase-99
contract the two identifier tables never share a `Severity` column: the table above carries the **phase-15**
scale and the `VAL-15-` section carries the **validation** scale, and the counts are stated separately.

