---
phase: 04-authentication
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 8
by-severity:
  CRITICAL: 0
  HIGH: 3
  MEDIUM: 4
  LOW: 1
---

# Phase 04 — Findings

## Summary

The credential-lifecycle zone was examined end to end: the one-time temp-password
handshake (issuance, storage, single use, retrieval, expiry), the access/refresh
credential pair, the login and refresh gates, the per-request identity resolution in
`api/deps.py`, the pre-credential abuse bounds, and the admin bootstrap that writes
into the identity namespace. Every claim below was reproduced against the live dev
stack (`mkobi-app-1` on :8010, PostgreSQL `bidb`, Redis) or proved statically from the
shipped code; the reproductions and the two probes that could not be run are recorded
in the Appendices. The single most consequential thing found is that the pre-login
abuse bound is keyed on the transport peer address, which behind the project's own
shipped proxy is a single constant for every caller, **and** it counts successful
logins — five correct logins from anyone lock out the login surface for the whole
system for five minutes, and the cycle repeats without an attacker. The CRITICAL band
is empty and that is a positive result, not an omission: no session was established
for an identity other than the one the credential was verified against, no credential
cleartext was found outside its delivery boundary, and no credential remained usable
after a guard should have refused it.

## Findings

### AUTH-001 — Five correct logins lock every user out of the only login surface for five minutes

**Severity** — HIGH

**Zone** — "The identity an abuse bound is keyed on, and whether the caller can choose it"

**Observation** — `_handle_login` (`api/routes/auth.py:83-90`) builds its bucket as
`f"login:{client_ip}"` where `client_ip = request.client.host`, and the comment above
it states the intent: *"Apply rate limiting for login attempts based on client IP …
prevents email enumeration via rate limit side-channel"*. `request.client.host` is the
**transport peer**, not the caller. Neither `app.py` nor the compose command installs
any forwarded-header trust, so behind either shipped proxy the value is the proxy
container's address — one constant for every caller. uvicorn 0.49 is constructed with
`proxy_headers=True` and `forwarded_allow_ips='127.0.0.1'` (its own default), so
`X-Forwarded-For` / `X-Real-IP` set by nginx (`docker/nginx/nginx.conf:37-38`) or by
Vite (`frontend/vite.config.ts` `server.proxy./api`) are **discarded**: the peer is a
`172.21.0.x` container address, not loopback. The bucket is also charged before
authentication, and `AsyncRateLimiter.check_rate_limit` increments the counter on every
call it allows (`core/security.py:132-135`), so **successful logins consume the quota
just like failed ones**. `docs/01-auth/auth-api.md:46,96` and
`docs/08-security/security-overview.md:44-46,52` all describe the scope as
"5 attempts per 5 minutes **per IP**" and claim this "maintain[s] effective
brute-force protection"; the code delivers a single global 5-per-5-minutes counter.

**Evidence** — Live, through the project's own Vite proxy on :5173, six requests
carrying six different `X-Forwarded-For`/`X-Real-IP` values (`1.1.1.1` … `6.6.6.6`):

```
XFF=1.1.1.1 -> HTTP 401      XFF=4.4.4.4 -> HTTP 401
XFF=2.2.2.2 -> HTTP 401      XFF=5.5.5.5 -> HTTP 401
XFF=3.3.3.3 -> HTTP 401      XFF=6.6.6.6 -> HTTP 429
login:* keys after:  login:172.21.0.2      (single key; 172.21.0.2 = mkobi-frontend-1)
```

Six self-identified callers, one bucket. Separately, six **successful** logins with the
correct admin credentials from one peer address:

```
attempt 1..5: HTTP 200 OK - access token issued
attempt 6   : HTTP 429 RATE_LIMIT_EXCEEDED
redis: GET login:127.0.0.1 -> 5     TTL -> 299
```

`docker exec mkobi-app-1 python -c "Config('src.mkobi.main:app')"` →
`proxy_headers=True, forwarded_allow_ips='127.0.0.1'`;
`docker inspect` → app `172.21.0.6`, frontend `172.21.0.2`. The rate limit is fail-closed
by default (`RATE_LIMITER_FAIL_CLOSED=true`, verified live), so the limiter is fully
armed — it is the key that is wrong.

**Consequence** — In the production topology (`nginx` → `app:8000`,
`docker/Dockerfile:179`) every login from every user of the system lands in one bucket.
Five successful logins by five legitimate users within any five-minute window make the
sixth login return `429 RATE_LIMIT_EXCEEDED` for the rest of the window; the same is
reachable deliberately, without credentials, and repeatable indefinitely by any
unauthenticated caller. The result is a self-inflicted and attacker-triggerable outage
of the only authentication surface, with a `Retry-After` that is the only remedy. The
same keying defect applies to `/auth/refresh` (10 per 300 s, `auth.py:309-315`) and to
`/auth/register-request` (3 per 3600 s, `auth.py:566-569`), so a session refresh storm
from any five users also denies everyone their access tokens. The brute-force
protection the documentation claims does not exist at the documented granularity: the
bound is a global counter, not a per-caller one.

**Recommendation** — Make the bound's key the caller's address as observed through the
proxy, and stop charging the quota on success. Two independent changes, both small:
(a) run the app with an explicit trusted-proxy setting, e.g. `--forwarded-allow-ips`
covering exactly the compose network CIDR (or `*` only if the app is unreachable except
through that proxy), so `request.client.host` becomes the originating caller; and/or
(b) add a tiny dependency that reads the left-most `X-Forwarded-For` entry the trusted
proxy appended, and use it for the key while logging the peer separately for diagnosis.
Whichever is chosen, set it explicitly — the current value is an accident of uvicorn's
default. Separately, move the `check_rate_limit` call to *after* `login_user` returns
`None`, or add a distinct counter for failures, so the documented "5 **attempts**" is
either what the code does or the doc is changed to say "5 failed attempts". Then correct
`docs/01-auth/auth-api.md:46,96` and `docs/08-security/security-overview.md:44-46,52`
to describe the granularity that is actually enforced. No shipped test asserts the
current key shape, so nothing blocks this.

### AUTH-002 — A password reset commits the new credential even when the store that must deliver it refused the value

**Severity** — HIGH

**Zone** — "The one-time credential handshake end to end: issuance, where the cleartext rests, retrieval, and what the retrieval handle is exposed to"

**Observation** — `TempPasswordStore.store` is declared fail-open by design: its
docstring says *"Fails open on Redis errors - logs the error but does not raise"*, and
the body catches `Exception`, logs at ERROR and returns (`core/temp_password_store.py:47-48`).
`AuthService.reset_password_admin` then proceeds regardless — it writes the new hash and
`force_password_change=True` to the user row and calls `await db.commit()`
(`services/auth_service.py:585-590`), and returns `retrieval_token`
(`:595-599`) — so `POST /admin/users/{id}/reset-password` answers **HTTP 200 with a
handle that can never resolve**. The registration-approval path has the same shape
(`api/routes/admin.py:321` store, `:330` commit, `:335` returns the handle), with one
extra step: `register_user` commits the new account at `auth_service.py:169` *before*
the store is touched at all. In every case the account is left holding a password whose
cleartext existed only inside the request process and was then discarded. Nothing
inverts the commit when the store could not accept the value.

**Evidence** — Reproduced in-process against the live `bidb` database, with a
`TempPasswordStore` subclass that records its argument and forwards to a genuinely
unreachable Redis (`127.0.0.1:1`):

```
reset_password_admin returned: {'message': 'Password reset successfully',
  'user_id': '418889e3-...', 'retrieval_token': '6d58b017-afd8-4a3f-a1f6-0b7b78d04008'}
cleartext handed to the store (recovered by the spy): cz1No7DOEkhjaDh7
Failed to store temp password in Redis: Error 111 connecting to 127.0.0.1:1
DB password_hash CHANGED : True
DB force_password_change : False -> True
committed account still verifies the cleartext that no live store holds: True
retrieve(handle) on the unreachable store -> None
login with that cleartext -> ACCEPTED
login with the ORIGINAL password -> refused
```

The user's original password is refused, the new password is reachable only by whoever
generated it inside the discarded request, and the operator was told 200 OK.

**Consequence** — Today, a Redis outage or eviction at the moment of an admin password
reset silently converts one account into an account nobody can log into. The admin
receives a retrieval token, calls `GET /admin/temp-passwords/{token}`, receives
`404 "Temporary password not found or already retrieved"` (see AUTH-006) and cannot
distinguish an outage from a token they already spent. Recovery requires a second reset,
which fails the same way for as long as the store is unreachable. The only
operator-visible trace is one ERROR log line naming no user, no admin and no handle. The
same applies to approving a registration request: the request is marked `APPROVED`, the
`viewer` account exists with an unknown password, and the request can never be
re-approved because `admin.py:299-303` refuses any status other than `PENDING`.

**Recommendation** — Make the store's write failure fail the request before the account
change is committed. The smallest shape: give `TempPasswordStore.store` a strict
variant (or change `store` to re-raise) and have both callers do the store write *after*
the `user_repo.update` but *before* `db.commit()`, wrapping it so a failure rolls the
session back and surfaces as `ErrorCode.SERVICE_UNAVAILABLE` (503). In
`auth.py:169` the account insert commits inside `register_user`, so the approval path
needs the commit hoisted out of `register_user` to the route so the two writes can share
one transaction boundary. Also log the store outcome with `user_id` and `admin_user_id`
so the failure is attributable. **Remediation blocker**:
`tests/core/test_temp_password_store.py:164-181` (`test_store_fail_open_on_error`)
asserts the current behaviour by name — *"Should not raise - graceful degradation"* and
`mock_logger.error.assert_called_once()` — and must be replaced with a test that asserts
the raise.

### AUTH-003 — `force_password_change` is written by both issuing paths, surfaced to the browser, and enforced by no server path

**Severity** — HIGH

**Zone** — "Account state the credential cannot carry: the completion path"

**Observation** — Both credential-issuing paths set the flag on the stored record:
`auth_service.py:588` (`force_password_change=True`) and `admin.py:316` (approval).
`change_password` clears it (`auth_service.py:514`). The column is `NOT NULL` with a
`false` default (`db/models/user.py:69-73`), it is exposed on `UserRead`
(`models/user.py:49`) and returned by `/auth/login` and `/auth/me`. The only consumers
are client-side: `frontend/src/features/auth/model/useAuth.ts:37,81,108` and
`ui/LoginForm.tsx:39` read it and redirect the browser to
`/profile/change-password?force=true`. There is **no server-side read**: a
`for`/comparison of `force_password_change` appears nowhere in `src/` — the only
occurrences are the two writes, the one clear, the column definition, the Pydantic field
and `admin.py:200`'s docstring string. `get_current_user_dependency`
(`api/deps.py:493-553`) checks the jti blacklist, the user-level revocation marker, the
user's existence and `is_active` — and returns. `docs/04-admin/admin-api.md:204,239`
and `docs/00-overview/overview.md:72` describe the flag as *"requiring the user to change
their password on next login"* and *"Forces password change on next login"*;
`docs/01-auth/auth-api.md:334` is accurate that the *frontend* performs the redirect and
the *backend* clears the flag after a successful change.

**Evidence** — Live, on a `viewer` promoted to `admin`, reset by the real admin and then
logged into with the admin-issued temp password:

```
promoted probe to admin: 200 admin
user row after reset: force_password_change = True | is_active = True
login with the temp password: 200
  /auth/me     -> 200 | role: admin | force_password_change: True
  /admin/users -> 200 | accounts listed: 5
  /admin/registration-requests -> 200
```

The account the system declares must not be used until its password is replaced is
issuing and consuming full administrative tokens, including the user list. Static
confirmation that no gate consults it: `Select-String 'force_password_change' src/` →
11 hits, of which 4 are writes, 1 the clear, 1 the column, 1 the Pydantic field, 1 a
route description string, 1 a service docstring, 3 in `UserRead`-adjacent code — none a
comparison.

**Consequence** — The temp password an admin hands over is the account's real, complete
credential until the account's *browser* voluntarily leaves the app and calls
`/auth/change-password`. Every server path treats it as an ordinary credential. Anyone
holding it — the intended recipient, or a third party who saw it pasted into a ticket,
chat or email, which is the entire purpose of an admin-issued password — can use the
account indefinitely and is never forced off it. The only thing that ends it is a second
admin reset, which under AUTH-002 may itself fail. The flag is decorative on the server
and load-bearing in the documentation, which is the inverse of the project's own stated
posture at `docs/08-security/security-overview.md:30` (*"Security constraints are
enforced on the backend … must never be relied upon as a security boundary"*).

**Recommendation** — Enforce the flag in the identity dependency, not in the SPA. The
smallest change: in `get_current_user_dependency` (`api/deps.py`, alongside the existing
`is_active` check at `:544-550`), when `user.force_password_change` is true, permit only
the identity endpoints the user needs in order to change the password —
`/auth/change-password`, `/auth/me`, `/auth/logout`, `/auth/refresh` — and refuse
everything else with a dedicated `ErrorCode`. That keeps the redirect working while
making the server the boundary. If a full gate is more than wanted, a narrow
intermediate step is a bounded expiry on the reset itself (store a reset timestamp in
Redis next to the temp password and refuse sessions older than it), which is smaller but
weaker. Then correct `docs/04-admin/admin-api.md:204,239` and
`docs/00-overview/overview.md:72` to say what is actually enforced. No shipped test
asserts the unenforced behaviour; the frontend tests in
`features/auth/model/__tests__/useAuth.test.tsx:343-397` assert the redirect and stay
valid.

### AUTH-004 — Password rotation does not withdraw the target's session, and the 7-day refresh credential is never rotated

**Severity** — MEDIUM

**Zone** — "Session continuity: what a captured long-lived credential is worth, and what a revocation marker must be able to express"

**Observation** — Two credentials constitute a session. The access token
(`security.py:251-296`, 15 min live) is presented as a bearer; the refresh token
(`:299-337`, 10080 min = 7 days) lives in the `mkobi_refresh_token` httpOnly cookie
(`COOKIE_NAME`, `security.py:45`) and is the only thing that can mint a new access token
(`auth.py:377-382`). Three properties hold at once. (a) **Use does not rotate the long
credential**: `POST /auth/refresh` returns a fresh access token and never issues a new
cookie, so the same 7-day value is presented on every request for its whole life.
(b) **The long credential is not bound to the client that obtained it** — nothing in the
token, the cookie, or the gate references a device, a UA hash, or an IP.
(c) **No credential-rotation path withdraws it**: `revoke_token`,
`revoke_refresh_token` and `revoke_all_user_tokens` (`security.py:466-539`) have exactly
two call sites each — `auth.py:448,459` (logout) and `admin.py:176` (deactivation).
`change_password` (`auth.py:497`) and `reset_password_admin`
(`admin.py:215`) write a new hash and touch no revocation state. The user-level marker
that *is* written expresses only "everything for this id, until
`max(access_ttl, refresh_ttl)`" (`security.py:535-538`) and is honoured on both the
per-request gate (`deps.py:526-532`) and the refresh path (`auth.py:368-375`) — that
half of the design is sound.

**Evidence** — Live, on a `viewer` account with a session in hand, then reset by the
admin:

```
== 2. admin resets probe password ==
reset: 200 | retrieval_token: 20e02f0b-...
user row after reset: force_password_change = True
== 3. does the PRE-RESET session survive the rotation? ==
old ACCESS token  after reset -> 200
old REFRESH cookie after reset -> 200 | NEW access token minted
   minted token /auth/me -> 200 | email: probe_auth04e@example.com
```

and on the rotation property itself, for the refresh endpoint:

```
refresh token as refresh     -> 200 | /auth/refresh Set-Cookie: False
```

No `Set-Cookie` header is emitted, so the presented credential is not consumed or
narrowed. The docstring at `auth_service.py:544-550` is the only place the rotation's
scope is described, and it mentions the flag and the store but not the session.

**Consequence** — A captured refresh cookie is equivalent to a password for the full
7 days from the moment it was issued, and nothing the system offers short of
deactivating the account shortens that window. The standard incident response — reset
the password — provably does not revoke the attacker's session, as the transcript
above shows. The credential is also presented in full on every request, so it is
exposed at least as often as an access token, while living 28× longer. Since use does
not rotate it, an observer who captures it once holds it for the whole remaining
lifetime; there is no natural turnover that would eventually evict them.

**Recommendation** — Rotate the refresh credential on use. In `POST /auth/refresh`
(`auth.py:377-382`), after minting the new access token, revoke the presented jti with
`revoke_refresh_token(redis_client, jti, remaining_ttl)` and re-issue the cookie via
`set_secure_cookie(..., max_age=refresh_token_expire_minutes * 60)` — the machinery and
the TTL calculation are already present at `auth.py:118-123`. This makes a captured
cookie worth one refresh interval instead of 7 days, and it also converts the refresh
token from a replayable bearer value into a rotating one, which addresses the missing
client binding without needing device records. Second, make the rotation paths withdraw
the session: after a successful `change_password` and after `reset_password_admin`, call
`revoke_all_user_tokens` with the target's id — the same call `admin.py:174-181` already
makes on deactivation, so no new mechanism is needed; the target re-authenticates with
the password they just set. This is the one finding here with a genuine client-visible
behaviour change, so sequence it after AUTH-006 (see Rollout Safety). `docs/01-auth/auth-api.md`
§Logout and `docs/08-security/security-overview.md` "Token Revocation" list only logout
and deactivation as revocation triggers and are not wrong today — update them to name
password change and admin reset as well.

### AUTH-005 — The handle that authorises reading a temp password is a URL path segment, and it is written verbatim into the access log

**Severity** — MEDIUM

**Zone** — "The one-time credential handshake end to end: issuance, where the cleartext rests, retrieval, and what the retrieval handle is exposed to"

**Observation** — The design deliberately withholds the cleartext from the reset
response: `admin.py:332-336` and `auth_service.py:595-599` return a `retrieval_token`
(uuid4, 122 bits), and the cleartext is fetched separately by
`GET /api/v1/admin/temp-passwords/{retrieval_token}` (`admin.py:403-423`). The stated
purpose, quoted twice in the project's own documentation, is
`docs/04-admin/admin-api.md:243` and `:396`: *"This ensures the plaintext password
never appears in API response logs."* That goal is met — the cleartext is not in the
access log. But the substitute the design chose puts the **authorising handle** into the
request line, and the request line is what the access log records. The application
emits uvicorn's access log at INFO into the structured logger
(`core/logging_config.py`, `log_level` default INFO), so the full URI lands in the log
stream verbatim. The application's own diagnostic at `admin.py:416` truncates correctly
(`token[:8]`), which shows the handle was understood to be sensitive — the access log
is the surface that was not considered. In production the same URI is additionally
written by nginx's `combined` access log (`docker/nginx/nginx.conf:10`) with
`proxy_set_header X-Forwarded-For` on the same `location` block (`:34-40`), so the
handle reaches two log stores and any browser history or proxy record along the way.

**Evidence** — The live container log, with the handle from a real admin reset
(`f53a1c4a-…`, `20e02f0b-…`) and a control:

```
{"level":"INFO","message":"127.0.0.1:43432 - \"GET /api/v1/admin/temp-passwords/f53a1c4a-482f-4f1a-ab68-489d11ade73a HTTP/1.1\" 200","module":"h11_impl","function":"send"}
{"level":"INFO","message":"127.0.0.1:49092 - \"GET /api/v1/admin/temp-passwords/20e02f0b-5900-4a3a-9fe6-0510d577f620 HTTP/1.1\" 200","module":"h11_impl","function":"send"}
```

Contrast the same request as the application records it deliberately
(`admin.py:415-416`): `"Admin: retrieving temp password: token=20e02f0b..."` — truncated
to 8 characters, the log line at INFO while the access line at the same level carries
all 36.

**Consequence** — Anyone who can read the application's INFO log, the container's
`docker logs`, or nginx's access log holds a live handle to a cleartext credential for
up to 24 hours (`TEMP_PASSWORD_TTL_SECONDS=86400`, confirmed live) with no further
authentication — the retrieval endpoint is admin-gated, but the handle has already
crossed the log boundary and the log is not access-controlled per-record. In the
production tier that is two log stores rather than one, and the log volume is where
credentials are conventionally rotated out slowest. The exposure is bounded (single-use,
24 h, requires the reader to be an admin or to have admin credentials) which is why this
is MEDIUM rather than CRITICAL — the cleartext itself never leaves the response body.
What the documentation asserts, however, is that this mechanism keeps secrets out of
logs, and it keeps the password out while putting the key to the password in.

**Recommendation** — Move the handle out of the URL, which also removes it from
`Referer` headers, browser history and any intermediary's request log. Smallest change
with no route-contract break: accept the handle in a request body —
`POST /admin/temp-passwords/retrieve` with `{"retrieval_token": "..."}` — and keep the
`GET` as a deprecated alias for one release. Failing that, keep the path but redact the
segment in the access log, which means replacing uvicorn's default access logger with a
`LoggingProtocol`/filter that rewrites `scope["path"]` for that prefix. Whichever route
is taken, correct `docs/04-admin/admin-api.md:243,396` so the claim matches what the
mechanism achieves; the current wording is true about the password and silent about the
handle.

### AUTH-006 — The retrieval endpoint cannot tell a spent handle from a nonexistent one from an unreachable store

**Severity** — MEDIUM

**Zone** — "Single-use and lifetime guarantees, in both directions"

**Observation** — `TempPasswordStore.retrieve` returns `None` for three distinct states
— key absent, key deleted by a previous `GET+DELETE` in the same MULTI/EXEC block, and
*any exception from Redis* (`core/temp_password_store.py:73-75`, catch-all returning
`None`). The route collapses that into one answer: `ErrorCode.NOT_FOUND` with the detail
`"Temporary password not found or already retrieved"` (`admin.py:418-422`). The
spending direction itself is correct: the `GET`+`DELETE` are queued in
`pipeline(transaction=True)` (`temp_password_store.py:63-66`), so Redis executes them
atomically and two concurrent claimants resolve to exactly one winner — a real
MULTI/EXEC, not a client-side simulation. The issuing direction's failure to be
distinguishable is AUTH-002; this finding is the reading side's.

**Evidence** — All three states observed against the live store, byte-identical
responses:

```
2nd retrieval (genuine double claim) -> 404 NOT_FOUND 'Temporary password not found or already retrieved'
never-existed handle                 -> 404 NOT_FOUND 'Temporary password not found or already retrieved'
retrieve(handle) on the unreachable store -> None   (with:)
Failed to retrieve temp password from Redis: Error 111 connecting to 127.0.0.1:1
```

**Consequence** — An operator holding a reset response cannot tell an outage from their
own earlier click. Under a Redis outage every in-flight reset looks like an expired or
spent handle, and the correct response — retry once Redis is back, or escalate — is
indistinguishable from "give up and reset again". Combined with AUTH-002 this is the
mechanism by which a store outage becomes silent account lockout: the second reset that
would fix it produces another 200 + another handle, and another 404 here.

**Recommendation** — Separate the store fault from the lookup miss. Give
`TempPasswordStore.retrieve` a tri-state return (value / `None` / raise on transport
error) — the catch-all at `:73-75` becomes a re-raise, or a distinct sentinel — and have
`admin.py:417-422` map the error to `ErrorCode.SERVICE_UNAVAILABLE` (503) while keeping
404 for the genuine miss. Distinguishing *spent* from *never existed* needs one extra
field on the stored value (write `"spent"` instead of deleting, so a second `GET` sees
the marker) and is a separate, smaller step; do it only if the operator workflow needs
it. **Remediation blocker**: `tests/core/test_temp_password_store.py:184-190`
(`test_retrieve_fail_graceful_on_error`) asserts `result is None` on Redis failure, and
`tests/api/test_temp_password_retrieval.py:126-130` (`test_retrieve_temp_password_single_use`)
asserts the double claim is a 404 whose detail contains `"not found"` — both must change
with the fix.

### AUTH-007 — The admin bootstrap reports success for a key it did not create, and leaves the occupant's role untouched

**Severity** — MEDIUM

**Zone** — "The identity namespace the handshake writes into, and the privileged entries already occupying it"

**Observation** — `DatabaseStarter.ensure_admin_user` runs unconditionally at every
process start in every environment (`starter.py:168`, inside `startup()`), before the
environment gate at `:171`. It executes a single raw statement whose conflict clause is
`ON CONFLICT (email) DO NOTHING` (`starter.py:358-370`) and then logs
`"Admin user ensured: %s"` (`starter.py:371`) at INFO, unconditionally and identically
whether the insert created a row or matched one. So the identity namespace's privileged
key is a single string — `ADMIN_USERNAME` — and when it is already occupied, the clause
leaves the occupant's `role` exactly as it is and the log claims the account was
ensured. The collision the phase asks about is not reachable from registration:
`ensure_admin_user`'s default key is the literal `"admin"` (`config.py:356`), and
`AuthService._validate_email_format`'s regex (`auth_service.py:40,104`) rejects any
string without `@` and a TLD, so a registrable identity cannot occupy the default key.
A *configured* address, however, can be occupied by anything already in the table.

**Evidence** — Reproduced against the live `bidb` database by registering a `viewer`
and then running the exact call `startup()` makes, with the bootstrap pointed at that
row's key:

```
BEFORE  role=viewer is_active=True
LOG> INFO Admin user ensured: probe_ns04@example.com
AFTER   role=viewer is_active=True
=> conflict clause left the account at role=viewer while the bootstrap logged 'Admin user ensured'
```

Live `ADMIN_USERNAME` is `admin@example.com` (`admin` role, present in the table), and
`starter.py:349-352` emits a second INFO line — *"Using default admin username"* — only
for the literal `"admin"`, so a configured-but-occupied address gets no warning at all.

**Consequence** — Two operator-visible false readings, both live today. (a) An operator
whose `ADMIN_USERNAME` already belongs to a non-admin account starts every process and
sees `Admin user ensured: <address>` while the account it names is a `viewer`; the
bootstrap will never grant the role, and the only surface that could show the
discrepancy (`/admin/users`) is unreachable with those credentials. (b) An operator who
demotes the only admin through the UI gets the same success line on the next restart
while the account stays demoted. In both directions the log is the only signal, and it
is wrong. There is no privilege escalation — `DO NOTHING` cannot raise a role — which is
why this is MEDIUM; the damage is a system whose operator believes it has an admin
account reachable at a known key and does not.

**Recommendation** — Make the log reflect what the statement did, and make a mismatch
loud. Change the statement to `ON CONFLICT (email) DO NOTHING RETURNING email` and log
`Admin user created` versus, on an empty result, `Admin key already occupied; existing
role left unchanged` at WARNING with the stored role read back in the same transaction.
Cheaper still and equally effective: after the insert, `SELECT role FROM users WHERE
email = :e` and log at WARNING when it is not `admin`, keeping the INFO line for the
created case. Either way the two outcomes stop sharing one message. Then note in
`docs/06-backend/` (or the deployment guide) that `ADMIN_USERNAME` must name an address
that is either free or already an admin, because the bootstrap will not reconcile it.
No shipped test asserts the current log line.

### AUTH-008 — The documentation says the revocation check degrades gracefully at WARNING; it hard-fails every request as a 401 at ERROR

**Severity** — LOW

**Zone** — "Session continuity: what a captured long-lived credential is worth, and what a revocation marker must be able to express"

**Observation** — `is_token_revoked` and `is_user_tokens_revoked` call
`redis_client.exists(key)` with no `try`/`except` (`core/security.py:502-504`,
`:552-554`). When Redis is unreachable the exception propagates out of
`get_current_user_dependency`, where the blanket handler at `api/deps.py:570-576` logs
`logger.error("Error getting current user: %s", e, exc_info=True)` and converts it to
`AppException(code=ErrorCode.AUTHENTICATION_FAILED, detail="Authentication failed")` —
HTTP 401, the same answer as a bad token. The same holds on the refresh path
(`auth.py:341,368`, unguarded) and in `core/permissions.py:325-334`. The direction is
fail-closed, which is the safe one, but
`docs/08-security/security-overview.md:234` states: *"If Redis is unavailable, the
revocation check degrades gracefully (logged at WARNING level)"* — it degrades neither
gracefully nor at WARNING. The same document's sibling claim at `:56-61` about the
rate limiter's fail-closed mode returning 429 is accurate; this one is not.

**Evidence** — Static: no exception handling on any of the four revocation read sites;
`Select-String` for `except` inside `is_token_revoked`/`is_refresh_token_revoked`/
`is_user_tokens_revoked` returns nothing, and `deps.py:570` is the only catcher on the
access path. Runtime confirmation of the shape was obtained indirectly by the
unreachable-Redis probe in AUTH-002, where every Redis fault in that process surfaced
as a caught-and-logged error rather than a typed service-unavailable response.

**Consequence** — During a Redis outage every authenticated request in the system
returns `401 AUTHENTICATION_FAILED / "Authentication failed"`, indistinguishable at the
client from a rejected token. The SPA's axios interceptor answers 401 by attempting a
silent refresh, which also fails 401, so the user-visible state is a silent sign-out
loop across all users at once, while the operator's log is a wall of ERROR lines with
Redis connection errors and the documentation asserts a graceful WARNING-level
degradation that will never appear. The security posture is correct; the diagnosis is
misleading at exactly the moment it is needed.

**Recommendation** — Pick one and make the code match the chosen statement. Prefer
keeping fail-closed and making it *legible*: wrap the two existence reads so a transport
error is distinguishable from a negative lookup, and map it to
`ErrorCode.SERVICE_UNAVAILABLE` (503) with a `logger.critical` naming the dependency —
which is what the rate limiter already does at `security.py:91-97`, so the pattern
exists in the codebase. Then correct `docs/08-security/security-overview.md:234` to
describe the behaviour actually implemented. The documentation fix alone is enough to
remove the false statement and is a one-line change; the code change is what makes the
failure mode diagnosable.

## Distribution

The findings concentrate on the **admin credential-reset workflow and the pre-credential
abuse bounds** — the two places where this system both mints and hands out credentials —
and on the absence of any server-side session-lifecycle enforcement. Nothing landed in
the token-minting primitives themselves: `create_access_token` / `create_refresh_token` /
`decode_token` / `validate_refresh_token` and the two blacklist prefixes behaved as
documented in every test run, and no finding is a mechanism defect in
`core/security.py`'s signing or revocation helpers. Of the eight:

- **Pre-credential bounds** — AUTH-001 (login, refresh, register-request share one
  collapsed bucket). Single cause, single zone, single fix site.
- **Admin reset / approval handshake** — AUTH-002 (fails open into a committed
  irreversible write), AUTH-005 (the handle in the URL and the access log), AUTH-006
  (the reading side cannot tell three causes apart), AUTH-007 (the bootstrap's
  conflict clause and its unconditional success log). Four findings, one subsystem.
- **Session lifecycle** — AUTH-003 (the change-required flag lives only in the client),
  AUTH-004 (rotation does not withdraw; the long credential is never rotated).
- **Documentation vs. behaviour** — AUTH-008, and AUTH-001/AUTH-003/AUTH-005 also carry
  a documentation component. Six of eight findings are, at minimum, partially a case
  where the project's own documentation misstates what the code does.

No finding landed in the dev-only seeders, the worker, the upload path, or the role
hierarchy; those were out of scope for this phase. All eight reproduce in the `dev`
tier and none depends on a production-only configuration.

## Cross-Finding Analysis

Two causes account for all eight findings.

**Cause 1 — the temp-password handshake is treated as best-effort on both sides and as
a complete success on the way out.** AUTH-002 (the write fails open into a committed
account change), AUTH-006 (the read conflates three causes) and AUTH-005 (the handle
travels in the request line) are one design: `TempPasswordStore` is an optional,
silently-degrading side channel wrapped around an operation the rest of the code treats
as mandatory. Its docstring declares the fail-open as intentional
(`temp_password_store.py:33`), and both callers honour that declaration by committing
anyway. Fixing the three symptoms separately would leave the shape intact, which is why
the roadmap groups them.

**Cause 2 — the server treats every credential state transition as a client-side
concern.** AUTH-003 (the change-required flag is enforced only by the SPA), AUTH-004
(rotation does not withdraw the session and the long credential is never rotated) and
AUTH-007 (the bootstrap's unconditional success log) share this: a state the server
owns — `force_password_change`, "this session predates the last password change", "this
admin key was not created by me" — is recorded in the database and acted on only by the
browser or by a log line. AUTH-001 and AUTH-008 are not instances of it, but they share
the neighbouring habit of a security-relevant fact being assumed rather than observed
and then asserted in prose (`docs/08-security/security-overview.md:30,44-52,234`;
`docs/01-auth/auth-api.md:46,96`; `docs/04-admin/admin-api.md:204,239,243,396`), which is
why six of the eight carry a documentation component.

## Roadmap

Grouped by cause, in dependency order. Nothing in step 2 may begin before step 1 is
landed and its shipped tests updated, because both change the same contract.

1. **Cause 1, storage — AUTH-002 and AUTH-006 together.** Make the store write strict
   and move it inside the transaction boundary of both issuing paths
   (`auth_service.reset_password_admin`, `admin.approve_registration_request_admin_endpoint`),
   which requires hoisting the commit out of `register_user`; make the read tri-state and
   map the transport fault to 503. Update `tests/core/test_temp_password_store.py:164-190`
   and `tests/api/test_temp_password_retrieval.py:126-130` in the same change — they
   encode the current behaviour. *Must be true before step 2:* a reset that cannot store
   returns 5xx and leaves the account row untouched, verified by a test that injects a
   failing store and asserts both the response and the unchanged `password_hash`.

2. **Cause 1, transport — AUTH-005.** Move the retrieval handle out of the URL path
   (`POST` with a body, `GET` deprecated for one release), or redact the path segment in
   the access log if the route contract must not change. *Must be true before step 3:*
   no `temp-passwords/` URI appears unredacted in the application's INFO log.

3. **Cause 2, bootstrap — AUTH-007.** Distinguish created from already-occupied in
   `ensure_admin_user` and log the two cases at different levels with the stored role.
   Independent of everything below; can ship at any point. *Must be true before step 4:*
   a start-up against an occupied key emits a WARNING naming the stored role.

4. **Cause 2, session — AUTH-004 before AUTH-003.** Rotate the refresh credential on use
   in `POST /auth/refresh` first, and add `revoke_all_user_tokens` to
   `change_password` and `reset_password_admin`. Both change client-visible behaviour
   (see Rollout Safety), so they ship before the next step's semantics are layered on top
   of them. *Must be true before step 5:* a session issued before a password change is
   refused by `/auth/refresh` and by the per-request gate, proven by a test that logs in,
   changes the password, and replays the old cookie.

5. **Cause 2, enforcement — AUTH-003.** Gate the API on `force_password_change` in
   `get_current_user_dependency`, allowing only the identity endpoints needed to change
   the password. *Must be true before rollout:* the SPA's existing redirect
   (`useAuth.ts:37,81,108`) reaches `/auth/change-password` and completes on a real
   admin-reset account, verified end to end in the browser, not by unit test alone.

6. **Cause 2, bounds — AUTH-001.** Set the forwarded-proxy trust explicitly and stop
   charging the login quota on success; then correct the three documentation sites that
   state the scope as "per IP". *Must be true before rollout:* six logins with distinct
   `X-Forwarded-For` values through the shipped proxy produce six distinct Redis keys,
   and six successful logins do not exhaust any bucket.

7. **Documentation — AUTH-008 plus the doc components of AUTH-001, AUTH-003, AUTH-005.**
   A single pass over `docs/08-security/security-overview.md`, `docs/01-auth/auth-api.md`,
   `docs/04-admin/admin-api.md` and `docs/00-overview/overview.md` to match the shipped
   behaviour. Cheap, and it belongs last because steps 1–6 each change what the docs
   should say. AUTH-008's code change (distinguishing the Redis fault from a negative
   lookup, mirroring `security.py:91-97`) is optional and can ride along with step 1's
   503 work.

## Rollout Safety

Steps 1, 4 and 5 change observable behaviour and carry real blast radius.

**Step 1 (strict store + tri-state read).** Anything that depends on the current
fail-open behaviour is an admin in the middle of a password reset during a Redis blip —
that person loses the reset and must retry, which is the intended outcome but will look
like a regression in the admin UI. The 503 on retrieval is the visible change: a client
that treats any non-200 as "not found" will now show the wrong thing during an outage.
`frontend/src/features/admin/ui/UserManagement.tsx:44` and
`ui/RegistrationRequests.tsx:36` both call `retrieveTempPassword` and surface
`data.temp_password`; check `shared/api/errorHandler.ts` maps 503 to something better
than a generic failure, or the operator sees a worse message than today's 404. The
hoisted commit in `register_user` touches every registration path — the test suite
(`tests/test_auth_service.py`, `test_admin_user_management.py`,
`test_auth_api.py`) asserts the current commit placement and must be re-read, not just
re-run. Revert: the store change is one `try`/`except`; the commit hoist is the riskier
half and should land as its own commit so it can be reverted alone.

**Step 4 (refresh rotation + revoke on password change).** This is the one change that
will break clients if it is half-done. The frontend attaches the refresh cookie
automatically and retries on 401 (`docs/08-security/security-overview.md` "Axios
interceptors … attempting a silent refresh"), so if the server rotates the cookie and
the browser fails to store the new one — any `SameSite`/`Path`/`Secure` mismatch, or a
client that strips `Set-Cookie` — every session dies at the first refresh, 15 minutes
after login, for every user at once. `COOKIE_SAMESITE` is `strict` and
`max_age = refresh_token_expire_minutes * 60` is already used at `auth.py:118-123`, so
reuse exactly that call. Ship it as: rotate-and-reissue first with the old jti **not**
yet revoked, verify in a real browser that a 20-minute session survives, then add the
revoke of the presented jti. The revoke-on-password-change half is the safer of the two
and can ship independently — the only client-visible effect is that a user who changes
their password is signed out and must log in again, which is the conventional
expectation, but say so in the release note because the SPA's silent-refresh path will
otherwise show an unexplained sign-out. Zone 12 owns the per-request gate, so if a
revocation check is to be added to the access path rather than only to `/auth/refresh`,
route it through 12 rather than widening this phase.

**Step 5 (enforce `force_password_change` server-side).** A user whose flag is set and
who is relying on any endpoint outside the allow-list will be cut off mid-session, and
the flag is currently never cleared except by `/auth/change-password`
(`auth_service.py:514`) — so the allow-list must include every endpoint that change flows
through, including `/auth/refresh` (an expired access token must be renewable so the
user can reach the change-password page) and `/auth/me` (the SPA reads the flag from it).
Before shipping, run the whole browser flow against a real admin-reset account: the
frontend tests at `features/auth/model/__tests__/useAuth.test.tsx:343-397` only prove
the redirect fires, not that the change completes. Revert: the dependency change is one
conditional in `get_current_user_dependency` and reverts cleanly, but any flag set
during the window stays set, so the revert must be paired with
`UPDATE users SET force_password_change = false` for the accounts created under it.

**Steps 2, 3, 6, 7.** Step 2 is additive behind a deprecation window. Step 3 changes
one log line. Step 6 is the one with a hidden dependency: enabling forwarded-header trust
means the app will start believing `X-Forwarded-For`, so it must be deployed *after* the
proxy is confirmed to be the only path to port 8000 — if the app port is reachable
directly in the target environment, an attacker can now choose their own rate-limit
bucket, converting a global-lockout defect into a bypass. Verify reachability of
`app:8000` from outside the compose network before enabling, and re-run the
six-distinct-`X-Forwarded-For` check after.

## Appendices

### Appendix A — Credential inventory (block 2)

| Credential | Minted at | Lifetime (live) | Gate that accepts it | Client binding |
|---|---|---|---|---|
| Access token (bearer) | `security.py:251-296`; issued by `auth_service.login_user:218`, `auth_service.create_access_token:256`, `auth.py:377` | 15 min (`access_token_expire_minutes=15`) | `deps.py:493-553` (`get_current_user_dependency`), `permissions.py:291-354` | none |
| Refresh token (cookie) | `security.py:299-337`; issued by `auth.py:115` only | 7 days (`refresh_token_expire_minutes=10080`) | `auth.py:329-382` (`/auth/refresh`), reading `sub` | none |
| Temp password (cleartext) | `auth_service._generate_temp_password:521-538` (16 chars, `string.ascii_letters + string.digits`, `secrets.choice`); issued by `auth_service.reset_password_admin:577` and `admin.py:306` | becomes the account password until changed | `POST /auth/login` (bcrypt) | n/a |
| Retrieval handle (uuid4) | `auth_service.reset_password_admin:581`, `admin.py:320` | 24 h (`temp_password_ttl_seconds=86400`) | `admin.py:403-423` | admin bearer token only |

Neither credential carries a type/kind claim. The separation between the access and
refresh lifetimes rests entirely on the *claim name* each gate happens to read
(`user_id` in `deps.py:514` and `permissions.py:316`; `sub` in `auth.py:349`).
Verified at runtime that neither is accepted where the other is expected:

```
refresh token as Bearer  -> 401 INVALID_TOKEN Invalid token
access  token as refresh -> 401 INVALID_TOKEN Invalid token
refresh token as refresh -> 200
access  token as Bearer  -> 200
```

The observed property holds, so no finding is filed; the fragility is recorded here
because a future edit that adds `sub` to an access token, or `user_id` to a refresh
token, silently opens the crossover.

`AuthService.authenticate_user:228`, `verify_token:285` and `refresh_token:258` mint or
verify credentials but have no production caller — only `tests/test_auth_service.py`.
`AuthService.create_access_token:246` has exactly one (`auth.py:252`). These are
reachable through the declared `IAuthService` interface
(`interfaces/service_interfaces.py:39,75`) and are not filed as dead code.

### Appendix B — Verification-cost measurement (block 3)

`login_user` calls `verify_password(password, "$2b$12$dummy.hash.to.prevent.timing.side.channel.attack.dummy.hash")`
for an unknown identity (`auth_service.py:203-209`). The placeholder is **not** a
well-formed bcrypt hash: 66 characters where a real one is 60, with a salt whose
trailing bits bcrypt 5.0.0 rejects for other inputs
(`"$2b$12$" + "a"*53` → `ValueError: Invalid salt`; `"$2b$12$" + "."*53` → `False`).
Its acceptance therefore depends on the parser's leniency, so the uniformity was
measured rather than assumed — 40 interleaved samples per arm, inside the app container:

```
A existing-user / correct pw   n=40 mean=408.05ms  median=372.83ms  stdev=129.82
B existing-user / wrong pw     n=40 mean=414.08ms  median=384.76ms  stdev=114.86
C NONEXISTENT-user path        n=40 mean=419.67ms  median=416.49ms  stdev=118.22
D control: real placeholder    n=40 mean=402.24ms  median=378.21ms  stdev=107.44
```

The non-existent-identity path performs the same 12-round work as a real verification
(419.67 ms vs 408.05/414.08 ms, against a 402.24 ms control built from a genuine
bcrypt hash of an unrelated value), and `bcrypt.checkpw` on the placeholder returns
`False` rather than raising. The stated intent holds for this library version; the
placeholder's shape does not guarantee it across versions, which is why it is recorded
here rather than filed. Both refusals also return the identical body
(`AUTHENTICATION_FAILED` / `"Invalid credentials"`), so no visible form distinguishes
the causes. Secret sources and windows: passwords are operator-chosen and checked by
`validate_password_or_raise`; temp passwords are `secrets.choice` over 62 characters ×16
(≈95 bits) with a 24 h window; the retrieval handle is `uuid4` (122 bits) with a 24 h
window and single use; the JWT signing secret is phase 02's (CFG-001/002/003) and is
not re-filed.

### Appendix C — Conditions: claim-carried vs. stored-record (block 7)

| Condition | Carried in the claim | Read from the stored record | Consulted by |
|---|---|---|---|
| identity | `user_id` (access), `sub` (refresh) | resolved to the row by `deps.py:523-535` | both gates |
| role | `role` in both tokens | `user.role` from the row, via `require_admin_role`/`check_role` | **only the stored record** — the claim is never read |
| email | `email` in both tokens | `user.email` from the row | **only the stored record** — the claim is never read |
| `is_active` | absent | the row | `deps.py:544-550` |
| `force_password_change` | absent | the row | **the SPA only** — see AUTH-003 |

There is no drift to report: privilege is read live from the stored record on every
request, so a stale or forged `role`/`email` claim in a token has no effect. The
divergence is the reverse of a drift — two claims (`role`, `email`) are minted, carried
on every request, and read by nothing. That is dead weight in the token rather than a
defect, so it is recorded and not filed.

### Appendix D — Identity namespace and privileged occupants (block 5)

The namespace is `users.email`, unique via `idx_users_email` (`db/models/user.py:30`).
Privileged occupants and the keys they hold: the startup bootstrap holds whatever
`ADMIN_USERNAME` resolves to (live: `admin@example.com`, role `admin`) — see AUTH-007
for what the conflict clause does to that row. No other principal is provisioned: there
is no service account, no API key, and no seeded user (`db/dev_seeders.py` seeds a
dashboard only; `db/seeders/test_media_dash.py` is the sole seeder). Registrable
identities come from `/auth/register-request`, whose only format guard is `'@' in email`
(`auth_service.py:402`), with the full regex applied later at approval
(`auth_service.py:104`) — so the default bootstrap key `"admin"` cannot be claimed by a
registrable identity, and no collision between an operator-provisioned entry and a
registrable identity was found. Domain blocking (`config.email.blocked_domains`,
`auth_service.py:432`) is an allow-by-exclusion list and is phase 02's concern, not
re-filed here.

### Appendix E — Revocation marker inventory (block 8)

| Marker | Key | Expresses | TTL | Honoured by |
|---|---|---|---|---|
| `revoke_token` | `token_blacklist:{jti}` | one access token, by jti | access remaining lifetime | `deps.py:506`, `permissions.py:326` |
| `revoke_refresh_token` | `refresh_token_blacklist:{jti}` | one refresh token, by jti | refresh remaining lifetime | `auth.py:341` only |
| `revoke_all_user_tokens` | `user_tokens_revoked:{user_id}` | every token of one identity, for a window | `max(access, refresh)` = 7 d from the write | `deps.py:526`, `auth.py:368`, `permissions.py:332` |

Each marker's expressiveness matches what its gate looks up, and the user-level marker
is honoured on all three paths — no mismatch to file. What is missing is a writer: only
logout (`auth.py:448,459`) and deactivation (`admin.py:176`) write any of them, which is
AUTH-004. The blacklist's key composition and per-marker lifetime are phase 10's.

### Appendix F — Reproduction method and residue

Live target: `mkobi-app-1` (:8010, uvicorn with `--reload`), PostgreSQL `bidb` on
:5432, Redis on the compose network. Credentials came from the container's own
environment via `docker exec … printenv`; no secret is reproduced here. Probes were
HTTP calls from inside the app container (`127.0.0.1:8000`) and, for the rate-limit key,
from the host through the project's own Vite proxy on :5173. The store-unavailability
reproduction used a `TempPasswordStore` subclass forwarding to `127.0.0.1:1`; the
`ensure_admin_user` reproduction pointed `config.admin_username` at a probe row and
invoked the shipped `starter.ensure_admin_user()` against the live database. Every
probe user was deleted, and the `login:*`, `refresh:*` and `temp_pwd:*` keys created
during the run were removed; the only remaining `user_tokens_revoked:` key
(`4cac4366-…`) predates this phase. No file in the repository was created, modified or
deleted by this audit.

### Appendix G — Limits on this report

- **The production tier was not started.** CFG-001 records that the production compose
  file resolves to `ENV: development` under the documented `--env-file`, and starting
  it needs a populated `.env` and a prior `npm run build`. Every finding is stated
  against the `dev` tier and the shipped compose/Dockerfile configuration; the
  production-tier statements (nginx access log, the `app:8000` peer address) are static
  deductions from `docker/nginx/nginx.conf:10,34-40` and `docker/Dockerfile:179`, both
  of which are unambiguous. AUTH-001's production blast radius in particular is a
  deduction from the topology, not an observation of the production nginx.
- **No TLS or certificate surface was examined** (phase 10's). `APP__COOKIE_SECURE` is
  `False` in the live dev environment, which is the documented development setting
  (`config.py`, `docs/08-security`) and phase 02's CFG-007 — not re-filed.
- **The hash cost and the at-rest policy** are phase 15's; AUTH-002's consequence is
  stated in terms of recoverability of the *account*, not of the stored hash.
- **Per-request authorization** — who may read which dashboard, and which surfaces a
  forged-request check reaches — is phase 12's. AUTH-003's allow-list recommendation is
  confined to the identity dependency; the 403/404 shapes observed for a viewer on
  business routes were recorded only as evidence that the identity gate had already
  admitted the session, and no authorization decision is evaluated here.
- **Nothing at rest was inspected.** The `backups/` directory and its dumps were not
  opened (CFG-005's territory), and no claim about how stored credentials are protected
  on disk is made or refuted here (phase 15's).
- **Abandoned-handshake residue was not swept.** A `temp_pwd:` entry written by a reset
  whose response never reached its client stays readable for up to 24 h; that is the
  documented TTL bound rather than a defect, but the volume of such entries in a live
  deployment was not measured.
