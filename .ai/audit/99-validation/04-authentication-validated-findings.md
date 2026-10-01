---
phase: 04-authentication
executed: 2026-09-30
executor: validator
problems-only: true
findings: 8
by-severity:
  CRITICAL: 0
  HIGH: 3
  MEDIUM: 4
  LOW: 1
validation-findings: 10
by-validation-severity:
  MEDIUM: 5
  LOW: 5
---

# Phase 04 — Validated Findings (Authentication)

## Summary

Every one of the eight `AUTH-` findings was re-derived from the executing path with its
anchors resolved mechanically; **all eight are substantiated, none is re-graded, none is
re-typed, none is merged, none is rejected.** The input's front-matter tally agrees with
its per-finding bodies, all six template fields are present on every finding, and no
identifier is renumbered. Ten defects in the *report* are filed separately under `VAL-04-`
— five MEDIUM, five LOW — of which the load-bearing ones are: the recommendation to fix
AUTH-001 by reading the **left-most** `X-Forwarded-For` entry would install the very
caller-chosen rate-limit bucket the finding is about; AUTH-001's assertion that "no shipped
test asserts the current key shape" is refuted by `tests/test_rate_limiting.py:124`; and
AUTH-006 asserts its concurrency guard's atomicity as fact where the phase's own block 4
required a concurrent observation that was never made. Three anchors drift: Vite is credited
with setting forwarded headers it does not set, a `Select-String` count is 8 and not 11, and
the access-path 401 claim is static-only while being written as observed. The
`force_password_change` search that anchors AUTH-003 was re-run and independently confirms
the finding's conclusion.

One thing changed underneath the report while it was being validated. A phase-02 configuration
remediation rewrote `db/starter.py` and `src/mkobi/config.py` *during* this run, moving eleven
line anchors out from under both documents. Every behaviour under audit survived the rewrite
intact — including AUTH-007, whose subject is the very function that was rewritten — so no claim
above moves and no disposition changes. Appendix K records the renumbering and the two leads it
produced.

## Findings

Identifiers are preserved. Each block carries a disposition inside the Observation field,
because the shared template mandates no disposition field (see Appendix H).

### AUTH-001 — Five correct logins lock every user out of the only login surface for five minutes

**Severity** — HIGH

**Zone** — "The identity an abuse bound is keyed on, and whether the caller can choose it"

**Observation** — Disposition: **confirmed**; asserted cause partly refuted (VAL-04-003).
Re-derived from the executing path at `api/routes/auth.py:83-90`: `client_ip = request.client.host
if request.client else "unknown"` and the key `f"login:{client_ip}"`, charged at `:88-90` **before**
`login_user` at `:101`, so every call it allows consumes the quota regardless of outcome. The
`AsyncRateLimiter` increments inside `core/security.py:132-135`. The collapse is mechanical and
now provable from the installed library, not only from the transcript: uvicorn 0.49.0 resolves
`Config('src.mkobi.main:app').forwarded_allow_ips` to `'127.0.0.1'` and
`.proxy_headers` to `True`; `uvicorn/middleware/proxy_headers.py:34` reads
`if client_host in self.trusted_hosts:` and only then reads `X-Forwarded-For`, so for a peer
of `172.21.0.x` the header is never consulted. No `--forwarded-allow-ips` exists in
`docker/Dockerfile:127,179` or in either compose file. `docker inspect` reproduces the peer
values: `mkobi-frontend-1` = `172.21.0.2`, `mkobi-app-1` = `172.21.0.6`. The three bounds named
are all present with the stated parameters: `auth.py:89` (5/300 s), `auth.py:314-315` (10/300 s),
`auth.py:566-568` (3/3600 s). Doc anchors `docs/01-auth/auth-api.md:46,96` and
`docs/08-security/security-overview.md:44-46,52` resolve and carry the quoted text verbatim.
The false element is the attribution of the header to Vite — see VAL-04-003; the finding
survives, and in the dev tier the collapse is total rather than partial because the Vite
container is the only path to the app.

**Evidence** — Live transcript accepted as filed: six distinct `X-Forwarded-For` values through
the project's own Vite proxy resolving to the single key `login:172.21.0.2`, and six
*successful* logins with correct credentials yielding 200×5 then 429. The mechanism above is a
static proof that reproduces the collapse without touching the dev stack, and the container
IPs were re-read read-only. A `redis-cli --scan` of the live instance finds no `login:*`,
`refresh:*` or `temp_pwd:*` residue, consistent with the input's Appendix F.

**Consequence** — Sustained. One global 5-per-5-minute counter on the only authentication
surface, charged on success, so five legitimate users logging in inside a window deny the
sixth; repeatable indefinitely by any unauthenticated caller with no credentials at all.

**Recommendation** — Executable only after the correction in VAL-04-001: option (b) as written
is a bypass, and option (a) alone is sufficient. Named remediation blocker: see VAL-04-002.
Doc corrections to `auth-api.md:46,96` and `security-overview.md:44-46,52` are correct as
written. The Rollout Safety's open precondition is now settled (see Rollout Safety).

### AUTH-002 — A password reset commits the new credential even when the store that must deliver it refused the value

**Severity** — HIGH

**Zone** — "The one-time credential handshake end to end: issuance, where the cleartext rests, retrieval, and what the retrieval handle is exposed to"

**Observation** — Disposition: **confirmed**. `TempPasswordStore.store`
(`core/temp_password_store.py:40-48`) declares fail-open in its docstring at `:33` and swallows
`Exception` at `:47-48` with no re-raise. `AuthService.reset_password_admin` calls it at
`services/auth_service.py:583`, then writes the hash and `force_password_change=True` at
`:585-589` and commits at `:590`, returning `retrieval_token` at `:595-599` — anchors `:585-590`
and `:595-599` both resolve. The approval path has the same shape and the extra step the
finding names: `admin.py:321` store, `:330` commit, `:335` handle, with the account already
committed inside `register_user` at `auth_service.py:169` (`:307` `create_user` → `:381`
`register_user`). `admin.py:299-303` refuses any status other than `PENDING`. One variant the
report does not mention and that is strictly worse: the store call is guarded by
`if self.temp_password_store is not None` (`auth_service.py:582`), so with no store wired the
reset commits *and* returns a handle unconditionally.

**Evidence** — The in-process reproduction is accepted as filed: cleartext recovered by a spy
subclass pointed at `127.0.0.1:1`, `password_hash` changed, `force_password_change` flipped,
`retrieve()` → `None`, the new cleartext accepted at login, the old one refused, HTTP 200 with
a handle. The shipping code path is fully re-derived above and needs no live store to settle.

**Consequence** — Sustained. A Redis fault at the moment of a reset converts one account into
an account nobody can log into, with one ERROR line naming no user, no admin and no handle.

**Recommendation** — Executable. The named target resolves, the transaction hoist is real, and
the named remediation blockers were verified line-exact: `tests/core/test_temp_password_store.py:164-181`
(`test_store_fail_open_on_error`, carrying `# Should not raise - graceful degradation` at `:176`
and `mock_logger.error.assert_called_once()` at `:180`) and `:184-190`
(`test_retrieve_fail_graceful_on_error`, `assert result is None` at `:190`). Two documentation
sites the recommendation does not name become false when the 503 lands — see VAL-04-010.

### AUTH-003 — `force_password_change` is written by both issuing paths, surfaced to the browser, and enforced by no server path

**Severity** — HIGH

**Zone** — "Account state the credential cannot carry: the completion path"

**Observation** — Disposition: **confirmed**; the evidence's inventory count is wrong
(VAL-04-004) while its conclusion is independently re-derived. Both issuing paths write the
flag — `services/auth_service.py:588` and `api/routes/admin.py:316` — and `change_password`
clears it at `auth_service.py:514`. The column is `NOT NULL DEFAULT FALSE`
(`db/models/user.py:69-74`) and the Pydantic field is `models/user.py:49`. A fresh
enumeration of `force_password_change` across `src/` returns **8** hits, none a comparison:
`admin.py:200` route description, `admin.py:314` comment, `admin.py:316` write,
`db/models/user.py:69` column, `auth_service.py:514` clear, `auth_service.py:549` service
docstring, `auth_service.py:588` write, `models/user.py:49` Pydantic field.
`get_current_user_dependency` (`api/deps.py:472-576`, body `:493-553`) checks the jti blacklist
at `:506`, the user-level marker at `:526`, the user's existence at `:535` and `is_active` at
`:544-550`, and returns — no read of the flag. Client-side consumers confirmed at
`frontend/src/features/auth/model/useAuth.ts:37,81,108` and
`frontend/src/features/auth/ui/LoginForm.tsx:39`. Doc anchors `admin-api.md:204,239`,
`overview.md:72` and `auth-api.md:334` all resolve and carry the quoted text verbatim.

**Evidence** — The live transcript is accepted as filed: an admin-reset account with
`force_password_change = True` logged in, `/auth/me` returning the flag `True`, and
`/admin/users` returning 200 with the account list. The static half is re-derived above
independently of the report's own `Select-String` count.

**Consequence** — Sustained. The admin-issued temp password is a complete, indefinitely
usable credential with full role privileges until the account's own browser chooses to leave
the application; every server path treats it as ordinary. The documentation load-bearingly
describes a control that does not exist server-side, which inverts the posture asserted at
`docs/08-security/security-overview.md:30`.

**Recommendation** — Executable, with two qualifications. The named target resolves and the
`is_active` anchor `:544-550` is exact. The dependency as written takes `(token, db,
redis_client)` and has no `Request`, so the allow-list it describes requires injecting the
request and inspecting the path — one *conditional* is not the whole change. And a second
identity path exists that the report's inventory presents as live but which has no production
caller (VAL-04-009); if it is ever wired, this gate is bypassed silently. The claim that no
shipped test blocks the change is correct: `tests/test_registration_flow.py:104-128` reaches
only `/auth/change-password` while the flag is set, and
`useAuth.test.tsx:343-397` asserts the redirect, which a server-side gate leaves valid.

### AUTH-004 — Password rotation does not withdraw the target's session, and the 7-day refresh credential is never rotated

**Severity** — MEDIUM

**Zone** — "Session continuity: what a captured long-lived credential is worth, and what a revocation marker must be able to express"

**Observation** — Disposition: **confirmed**; one wording imprecision in the evidence (below).
Re-derived: `create_refresh_token` (`core/security.py:299-337`) mints a 7-day value
(`config.py:186`, `refresh_token_expire_minutes=10080`) that is set once at `auth.py:115-123`
and is the only thing `POST /auth/refresh` accepts (`auth.py:297`). The handler `:275-382`
returns `Token(access_token=...)` at `:377-382` and **never calls `set_secure_cookie`** — the
single `set_secure_cookie` call in the file is at `:118`, on the login path — so the presented
credential is neither rotated nor consumed. No device, UA or IP binding exists in the token, the
cookie or the gate. The three revocation writers have exactly one call site each:
`revoke_refresh_token` → `auth.py:448`, `revoke_token` → `auth.py:459`, `revoke_all_user_tokens`
→ `admin.py:176`; the finding's "exactly two call sites each" reads as one per pair, not two
per function, and the substance it carries — only logout and deactivation write any revocation
state — is confirmed by exhaustive search. `change_password` (`auth_service.py:469-519`, route
`auth.py:497`) and `reset_password_admin` touch no revocation state. The user-level marker
expresses `max(access_ttl, refresh_ttl)` at `security.py:535-538` and is honoured on all three
paths (`deps.py:526`, `auth.py:368`, `permissions.py:332`).

**Evidence** — The live transcript is accepted as filed: a pre-reset access token and a
pre-reset refresh cookie both still returning 200 after the admin reset, and
`/auth/refresh` emitting no `Set-Cookie`. The absence of a second `set_secure_cookie` in
`api/routes/auth.py` is a static confirmation that needs no live session.

**Consequence** — Sustained. A captured refresh cookie is a password for its full 7 days;
password reset provably does not revoke it, and because use does not rotate it there is no
turnover that would eventually evict a holder.

**Recommendation** — Executable and precise: `auth.py:118-123` is named as the existing
mechanism and is exactly that, and the `revoke_all_user_tokens` shape at `admin.py:174-181` is
exactly reusable. The 401-retry path the Rollout Safety relies on is real
(`frontend/src/shared/api/axiosInstance.ts:66-124`). One documentation site the
recommendation must add — see VAL-04-010.

### AUTH-005 — The handle that authorises reading a temp password is a URL path segment, and it is written verbatim into the access log

**Severity** — MEDIUM

**Zone** — "The one-time credential handshake end to end: issuance, where the cleartext rests, retrieval, and what the retrieval handle is exposed to"

**Observation** — Disposition: **confirmed**; one imprecise anchor (below). The retrieval route
is `GET /admin/temp-passwords/{retrieval_token}` at `admin.py:403-423`; the handle is minted
uuid4 at `auth_service.py:581` and `admin.py:320`. The claim that `admin.py:332-336` is one of
the two sites that returns a `retrieval_token` is right about the design but wrong about the
route: `:332-336` is the **approval** response; the reset response is `auth_service.py:595-599`,
returned verbatim by `admin.py:226`. The application's own diagnostic truncates correctly at
`admin.py:415-416` (`retrieval_token[:8]`). The application's access log carries the full URI:
`docker/nginx/nginx.conf:10` is `access_log /var/log/nginx/access.log;` with no `log_format`
declared anywhere in the file, so nginx's default `combined` format applies, and
`nginx.conf:34-40` proxies `/api` to `app:8000` with `X-Real-IP`/`X-Forwarded-For` set on the
same location. Doc anchors `admin-api.md:243` and `:396` resolve and carry the quoted sentence.

**Evidence** — The live container-log lines are accepted as filed: two INFO records carrying
the complete 36-character handle in the request line, against the truncated
`token=20e02f0b...` the application writes deliberately at the same level.

**Consequence** — Sustained and correctly bounded. A live 24-hour single-use key to a cleartext
credential reaches the application INFO stream, `docker logs`, and in the production tier
nginx's access log; the cleartext itself never leaves the response body, which is why the
CRITICAL band's "cleartext reaching a surface outside its delivery boundary" is not met.

**Recommendation** — Executable. Both named approaches resolve, the deprecation window is
specified, and the doc corrections at `admin-api.md:243,396` are correct as written.

### AUTH-006 — The retrieval endpoint cannot tell a spent handle from a nonexistent one from an unreachable store

**Severity** — MEDIUM

**Zone** — "Single-use and lifetime guarantees, in both directions"

**Observation** — Disposition: **confirmed** on the conflation; the atomicity half is
asserted, not demonstrated (VAL-04-008). `TempPasswordStore.retrieve`
(`core/temp_password_store.py:50-75`) returns `None` for three distinct states: key absent,
key already deleted, and any exception, the last via the catch-all at `:73-75`. The route
collapses all three into `ErrorCode.NOT_FOUND` with detail
`"Temporary password not found or already retrieved"` at `admin.py:418-422`. The spending
direction's `GET`+`DELETE` are queued inside `pipeline(transaction=True)` at
`temp_password_store.py:63-66` — the anchor resolves and the mechanism is the real MULTI/EXEC.
The claim's own limit is honest: the "exactly one winner" property is *inferred* from the
library's semantics, with no concurrent request in evidence.

**Evidence** — Three sequential observations against the live store, byte-identical responses,
plus the unreachable-store probe returning `None` with its ERROR line — accepted as filed for
the conflation. Nothing in the report exercises two simultaneous claimants, which is what the
phase's own block 4 names as its required evidence for this direction.

**Consequence** — Sustained. Under a Redis outage every in-flight reset is indistinguishable
from a spent handle, and with AUTH-002 the second reset that would fix it produces another
200 and another 404.

**Recommendation** — Executable; the tri-state shape and the 503 mapping are both named at
resolvable anchors. The named remediation blockers were verified: the store one is exact
(`tests/core/test_temp_password_store.py:184-190`); the API one is off by three lines — the
double claim and its assertions are at `tests/api/test_temp_password_retrieval.py:129-136`,
not `:126-130`, and the `"not found"` assertion the finding quotes is at `:136`.

### AUTH-007 — The admin bootstrap reports success for a key it did not create, and leaves the occupant's role untouched

**Severity** — MEDIUM

**Zone** — "The identity namespace the handshake writes into, and the privileged entries already occupying it"

**Observation** — Disposition: **confirmed**; the Zone is a paraphrase, not the block title
quoted verbatim (VAL-04-006), and the finding is filed without discharging the predicate its own
scope paragraph sets, though that predicate is in fact satisfied (VAL-04-007).
`DatabaseStarter.ensure_admin_user` is called unconditionally at `db/starter.py:168`, ahead of
the environment gate at `:171`. Its single statement carries `ON CONFLICT (email) DO NOTHING` at
`:362` — the anchor `:358-370` resolves — and `logger.info("Admin user ensured: %s", admin_email)`
at `:371` fires unconditionally and identically whether the insert created a row or matched one;
it is emitted *after* the `async with db.begin()` block closes, so no `rowcount` is in scope to
distinguish the two. The `admin == "admin"` warning at `:349-352` fires only for that literal, so
a configured-but-occupied address gets no signal. The non-reachability of the default key from
registration is confirmed: the bootstrap default is `config.py:356` (`default="admin"`) and
`EMAIL_REGEX` at `auth_service.py:40,104` rejects any string without `@` and a TLD.

**Anchors moved under this finding during the run; the substance did not.** A phase-02
configuration remediation was executing concurrently and rewrote `ensure_admin_user` while this
validation was in progress. Re-resolved against the post-remediation tree: `ensure_admin_user()`
is called at `db/starter.py:174` (was `:168`), the environment gate is at `:177` (was `:171`),
the transaction is `async with db.begin():` at `:368` (was `:356`), `ON CONFLICT (email) DO
NOTHING` is at `:373` (was `:362`), and `logger.info("Admin user ensured: %s", admin_email)` is
at `:382` (was `:371`) — the file grew 434 → 445 lines. **The two statements this finding is
about are untouched by that change**: the `DO NOTHING` clause and the unconditional success line
both survive verbatim, and the unconditional call still precedes the environment gate. One
supporting sentence needs restating rather than merely renumbering: the weak-username warning is
no longer `admin == "admin"` but `is_weak_credential(admin_email, WEAK_USERNAMES)`, widened to
six values at `config.py:19`. That widening does not touch the finding's point — the predicate is
*weakness*, not *occupancy*, so a configured-but-occupied address outside that six-value set
still produces no signal, which is the defect. The Consequence's "live today" therefore holds
against the post-remediation tree.

**Evidence** — The live reproduction is accepted as filed: a `viewer` row pointed at by
`ADMIN_USERNAME`, `role=viewer is_active=True` before and after, with
`Admin user ensured: probe_ns04@example.com` in between. The conflict clause leaves the
occupant's role untouched by construction, so the observation was inevitable once the clause
was read.

**Consequence** — Sustained. Two operator-visible false readings, both live today, with the log
as the only signal and the log wrong. `DO NOTHING` cannot raise a privilege, which is the
report's stated reason the band is not higher, and that reason holds.

**Recommendation** — Executable; both named shapes resolve, the cheaper `SELECT role` variant
is sound, and no shipped test asserts the current log line (verified by search).

### AUTH-008 — The documentation says the revocation check degrades gracefully at WARNING; it hard-fails every request as a 401 at ERROR

**Severity** — LOW

**Zone** — "Session continuity: what a captured long-lived credential is worth, and what a revocation marker must be able to express"

**Observation** — Disposition: **confirmed**, statically and completely; the runtime
"confirmation" offered in the Evidence field does not exercise this path, and the
Consequence mis-states the client-visible symptom (VAL-04-005). Re-derived: `is_token_revoked`
(`core/security.py:492-504`) and `is_user_tokens_revoked` (`:542-554`) each call
`await redis_client.exists(key)` at `:503` and `:553` with no `try`/`except` — the anchors
`:502-504` and `:552-554` resolve. `is_refresh_token_revoked` (`:507-519`) is the same shape.
The only catcher on the access path is the blanket handler at `api/deps.py:570-576`, which logs
`logger.error("Error getting current user: %s", e, exc_info=True)` and raises
`AppException(code=ErrorCode.AUTHENTICATION_FAILED, detail="Authentication failed")` → 401,
the same answer as a bad token. The refresh path is equally unguarded (`auth.py:341,368`), and
`core/permissions.py:325-334` has the same shape. The direction is fail-closed and therefore
safe. `docs/08-security/security-overview.md:234` resolves and states
*"If Redis is unavailable, the revocation check degrades gracefully (logged at WARNING level)"* —
it degrades neither gracefully nor at WARNING. The sibling claim at `:56-61` about the rate
limiter's fail-closed 429 is accurate, as the finding says.

**Evidence** — Static, and sufficient: an unguarded `exists()` raises, the enclosing `try`
has no Redis-specific arm, and the blanket handler is the only catcher on the path. The
report's stated runtime support — "obtained indirectly by the unreachable-Redis probe in
AUTH-002" — describes `TempPasswordStore.retrieve`'s own catch-all, not this handler, so it
confirms nothing here. The report's own Summary concedes the runtime shape was seen only
"indirectly".

**Consequence** — Sustained. During a Redis outage every authenticated request returns
`401 AUTHENTICATION_FAILED / "Authentication failed"`, indistinguishable at the client from a
rejected token. The user-visible state is **not** silent: `axiosInstance.ts:66-124` answers any
401 by attempting a refresh, and on failure executes `removeToken()`,
`toast.error('Session expired. Please login again.')` and `window.location.href = '/login'`
at `:117-119` — a loud, simultaneous sign-out of every session, landing users on the login page
that AUTH-001 has rate-limited.

**Recommendation** — Executable and well-targeted: the fail-closed decision to keep is right,
the `logger.critical` pattern it points at exists verbatim at `security.py:91-97`, and the
one-line doc correction at `security-overview.md:234` removes the false statement on its own.

## Validation-Level Findings

Separate section, separate scale, separate namespace. The `VAL-` prefix the output contract
assigns is already occupied by two sibling reports; this report's identifiers carry the
`VAL-04-` infix and the deviation is recorded in Appendix G.

### VAL-04-001 — AUTH-001's recommended fix (b) reads the left-most `X-Forwarded-For` entry, which is the caller-supplied one

**Severity** — MEDIUM

**Zone** — Block 5, recommendation executability

**Observation** — Disposition: **substantiated but must be corrected before execution**.
AUTH-001 recommends, as one of two independent changes, to "add a tiny dependency that reads
the left-most `X-Forwarded-For` entry the trusted proxy appended". Each proxy *appends*:
`docker/nginx/nginx.conf:38` sets `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`,
which concatenates `$remote_addr` onto whatever chain the caller sent. The left-most entry is
therefore the first one the caller wrote, not the one the proxy added. uvicorn's own
implementation is the counter-example and shows the correct shape: at
`uvicorn/middleware/proxy_headers.py:162-180`, `get_trusted_client_address` walks
`reversed(x_forwarded_for_hosts)` and returns the first host **not** in `trusted_hosts`,
because — as its own comment at `:172` puts it — "each proxy appends to the header list so check
it in reverse order". The same function shows the trap: under `always_trust` it falls back to
`_parse_host_port(x_forwarded_for_hosts[0])` at `:170`, i.e. the left-most entry, which is only
sound when the edge strips inbound headers.

**Evidence** — Read from the installed library and the shipped nginx config; no live system
touched. The consequence is deterministic, not speculative: implementing (b) turns AUTH-001's
global-lockout defect into a caller-chosen rate-limit bucket, which is a brute-force **bypass**
and strictly worse than the defect it repairs. The finding's own acceptance criterion cannot
detect this: "six logins with distinct `X-Forwarded-For` values through the shipped proxy
produce six distinct Redis keys" passes identically under the fix and under the bypass.

**Consequence** — A remediator who follows the recommendation as written ships a security
regression believing they closed a finding, and the stated verification confirms it.

**Recommendation** — Drop (b) and make (a) the whole fix: set `forwarded_allow_ips` to the
compose network CIDR explicitly. uvicorn then does the right-untrusted-host walk for free, the
result is not attacker-chosen, and no new dependency is needed. If (b) is kept for any reason,
it must read the right-most untrusted entry, not the left-most.

### VAL-04-002 — AUTH-001's "no shipped test asserts the current key shape" is refuted by a test that hardcodes it

**Severity** — MEDIUM

**Zone** — Block 5, recommendation executability

**Observation** — Disposition: **not substantiated as stated**. AUTH-001 closes with "No
shipped test asserts the current key shape, so nothing blocks this." A shipped test does.
`tests/test_rate_limiting.py:124` assigns `rate_limit_key = "login:127.0.0.1"` — a literal
encoding the peer-derived key — and `test_rate_limit_reset_allow_writes` uses it at `:138-139`
to `strict_redis._data.pop(...)` and `strict_redis._ttls.pop(...)` in order to clear the very
bucket the preceding six POSTs exhausted, so that the following request at `:142-145` returns
401 rather than 429. The coupling is exactly the shape the claim denies.

**Evidence** — `tests/test_rate_limiting.py:106-145` read in full. The other key literals in
`tests/test_auth.py:277-391` (`login:test_ip`, `login:ip1`, `login:ip2`) are passed directly
to the limiter as unit arguments and do not couple to the route's key derivation; only
`:124` derives its key from the request. Also note `tests/conftest.py:328-332,361-365`: the
autouse fixture stubs `check_rate_limit` to always-allow, so the shipped suite exercises the
key path only where a test opts out of that stub — which is why this one coupling went unseen.

**Consequence** — The dependency list the remediation plan is built on is short by one test.
Applied as written, the change either fails the suite or, worse, leaves the test green while
it no longer clears the bucket it just filled — the same vacuous-verdict shape this phase
exists to catch.

**Recommendation** — Name `tests/test_rate_limiting.py::test_rate_limit_reset_allow_writes`
as a remediation blocker alongside the two the report already names, and derive its key from
the same helper the route uses rather than a literal.

### VAL-04-003 — AUTH-001 credits Vite with setting the forwarded headers it does not set

**Severity** — MEDIUM

**Zone** — Block 1, asserted cause tested separately

**Observation** — Disposition: **asserted cause refuted; finding confirmed**. AUTH-001 states
that `X-Forwarded-For` / `X-Real-IP` are "set by nginx (`docker/nginx/nginx.conf:37-38`) or by
Vite (`frontend/vite.config.ts` `server.proxy./api`)" and that uvicorn discards them. The nginx
half is correct. The Vite half is not: `frontend/vite.config.ts:9-14` declares
`proxy: { '/api': { target: 'http://app:8000', changeOrigin: true } }` and nothing else. Vite
8.0.10 passes those options through unmodified — `proxyMiddleware` in
`frontend/node_modules/vite/dist/node/chunks/node.js:17806-17815` calls
`createProxyServer(opts)` with no `xfwd` default — and the bundled http-proxy's header writer
begins `function XHeaders(req, _res, options) { if (!options.xfwd) return;` at `:17151-17152`.
A search of the whole bundle finds `xfwd` at exactly those two guard lines and nowhere else, and
`XHeaders` has no call site in the shipped bundle at all.

**Evidence** — Read from the installed Vite 8.0.10 bundle and `vite.config.ts`; no dev server
touched. The consequence is a corrected mechanism, not a corrected verdict: in the dev tier no
component sets the header at all, and the peer is `172.21.0.2` because the Vite container is the
only path to the app. The filed observation `login:172.21.0.2` = `mkobi-frontend-1` is exactly
consistent with that, and the collapse is *more* complete in dev than the finding states, since
every caller shares one bucket rather than "every caller behind either shipped proxy".

**Consequence** — The sentence must be deleted before remediation. A remediator who believes
Vite supplies the header will pick recommendation (b) on the strength of it, test the change
through :5173, and see it fail for a reason the finding never mentions.

**Recommendation** — Restate the dev-tier cause as "no component in the dev path sets a
forwarded header, so the peer is the Vite container for every caller", and keep the nginx and
`forwarded_allow_ips` argument for the production tier, where it is independently correct.

### VAL-04-004 — AUTH-003's evidence characterises a source search whose count and breakdown are both wrong

**Severity** — LOW

**Zone** — Block 1, evidence quality

**Observation** — Disposition: **evidence does not reproduce; conclusion independently
confirmed**. AUTH-003 records `Select-String 'force_password_change' src/` → "11 hits, of which
4 are writes, 1 the clear, 1 the column, 1 the Pydantic field, 1 a route description string, 1 a
service docstring, 3 in `UserRead`-adjacent code" — seven categories summing to twelve against a
stated total of eleven. The actual enumeration returns **8**: three writes
(`admin.py:316`, `auth_service.py:514`, `auth_service.py:588`), one of which is also the clear;
one column (`db/models/user.py:69`); one Pydantic field (`models/user.py:49`); one route
description (`admin.py:200`); one code comment (`admin.py:314`, a category the breakdown omits
entirely); one service docstring (`auth_service.py:549`). There is no "3 in `UserRead`-adjacent
code" — there is one.

**Evidence** — Re-run over every `.py` file under `src/`. The finding's operative conclusion —
that no comparison of the flag exists on any server path — is confirmed independently of the
count, and is the part the finding stands on.

**Consequence** — None for remediation. A reader re-running the stated command gets 8, not 11,
and must redo the classification before trusting it; the guard the finding is about is
nonetheless proven absent.

**Recommendation** — Restate as the eight locations above. No change to the finding, its band,
or its recommendation.

### VAL-04-005 — AUTH-008's runtime support is a probe on a different path, and its Consequence calls a loud sign-out silent

**Severity** — LOW

**Zone** — Block 1, evidence quality

**Observation** — Disposition: **evidence characterisation refuted; claim confirmed statically;
one symptom mis-described**. Two defects in one finding. (a) The Evidence field states "Runtime
confirmation of the shape was obtained indirectly by the unreachable-Redis probe in AUTH-002,
where every Redis fault in that process surfaced as a caught-and-logged error rather than a typed
service-unavailable response." That probe exercised `TempPasswordStore.retrieve`'s own catch-all
at `temp_password_store.py:73-75`; it never entered `get_current_user_dependency`, so it confirms
nothing about AUTH-008. (b) The Consequence describes "a silent sign-out loop across all users at
once". `frontend/src/shared/api/axiosInstance.ts:66-124` does attempt a silent refresh on 401,
and on failure executes `removeToken()` at `:117`, `toast.error('Session expired. Please login
again.')` at `:118` and `window.location.href = '/login'` at `:119`. The user-visible state is
loud.

**Evidence** — The claim itself is re-derived completely from the executing path and needs no
live store: unguarded `exists()` at `security.py:503,553` → exception → the sole catcher at
`deps.py:570-576` → `AUTHENTICATION_FAILED` → 401. The mis-description is read from the
interceptor source. The correction cuts against the finding's own interest: the symptom is worse
than stated, not milder.

**Consequence** — A reader diagnosing a Redis outage is told to expect a quiet failure and will
look for one. AUTH-008 and AUTH-001 should be read together: the 401 storm lands every user on
the login page AUTH-001 has rate-limited.

**Recommendation** — Replace the runtime-support sentence with the static proof, and replace
"silent" with the toast and redirect at `axiosInstance.ts:117-119`.

### VAL-04-006 — AUTH-007's Zone paraphrases block 5's title instead of quoting it

**Severity** — LOW

**Zone** — Block 8, template contract

**Observation** — Disposition: **template rule violated, once**. The template mandates "**Zone**
— the audit block title this finding came from, quoted verbatim." AUTH-007's Zone reads "The
identity namespace the handshake writes into, and the privileged entries already **occupying**
it". The block title at `04-audit-authentication.md:65` is "The identity namespace the handshake
writes into, and the privileged entries already **in** it". Seven of the eight findings quote
their block title exactly, character for character; this is the only deviation, and it is a
two-word paraphrase of the final clause.

**Evidence** — Compared all eight Zone strings against the nine block titles. The other seven
match verbatim, including the two long ones (blocks 1 and 8) where a paraphrase would have been
easy to take.

**Consequence** — None. Block 5 is not ambiguous and the finding is filed in the right block.

**Recommendation** — Replace with the block title quoted verbatim.

### VAL-04-007 — AUTH-007 is filed without discharging the filing predicate its own scope paragraph sets, though the predicate is met

**Severity** — LOW

**Zone** — Block 4, which side moves

**Observation** — Disposition: **evidence gap; finding confirmed and materially strengthened**.
The phase's scope paragraph closes: "Deliberate asymmetry between tiers, environments or
components is not a defect on its own; report it only where the code's own documentation
misstates it." AUTH-007 never cites a documentation claim; its Recommendation instead *proposes*
writing one ("Then note in `docs/06-backend/` …"). The predicate is in fact satisfied, twice over,
and the documentation is worse than the report assumes. `docs/06-backend/logging.md:37-46`
presents a sample structured record whose message is `"Admin user created successfully:
admin@example.com"`, attributed to `"function": "ensure_admin_user"` — a string the code never
emits, asserting a *created* outcome for a statement whose conflict clause does nothing, which
is precisely the false-success defect the finding is about. And `docs/06-backend/architecture.md:125-130`
describes the same step as "Uses a SAVEPOINT (nested transaction) to handle race conditions
cleanly", where `db/starter.py:368-382` uses a plain `async with db.begin()`, and as "Logs a
warning if default credentials are used (development only)", where the warning at
`starter.py:360-363` emits in every environment.

**Evidence** — Both documents read at the cited lines; the SAVEPOINT claim and the
unconditional warning read directly against the shipping code. Neither citation appears
anywhere in the input.

**Consequence** — The finding stands at its band on stronger grounds than it records, and its
documentation half is a real, separately-fixable defect rather than a proposal to create one.

**Recommendation** — Cite `logging.md:42` and `architecture.md:128,130` in AUTH-007's Evidence,
and change the Recommendation from "note in `docs/06-backend/`" to "correct `logging.md:42` and
`architecture.md:128,130`".

### VAL-04-008 — AUTH-006 asserts its concurrency guard's atomicity as established fact where the phase required a concurrent observation

**Severity** — MEDIUM

**Zone** — Block 2, the vacuous-control angle applied to the input

**Observation** — Disposition: **an assertion carrying no observation behind it**. AUTH-006
states that the spending direction "is correct: the `GET`+`DELETE` are queued in
`pipeline(transaction=True)` (`temp_password_store.py:63-66`), so Redis executes them
atomically and two concurrent claimants resolve to exactly one winner — a real MULTI/EXEC, not
a client-side simulation." Phase 04's own block 4 requires as evidence "concurrent-claim and
concurrent-spend outcomes", and the block preamble is explicit that "a passing check is
methodology, never a finding" — here the inverse has happened and a passing check has been
recorded as an established property. Nothing in the report issues two concurrent requests: the
three observations in AUTH-006's Evidence are sequential, and Appendix F describes the probes as
"HTTP calls from inside the app container". The claim is very likely true for `redis-py`'s
transactional pipeline, but it is inferred from a library contract rather than observed here,
and it carries the Summary's CRITICAL-empty justification ("no credential remained usable after
a guard should have refused it").

**Evidence** — The three evidence lines are sequential by construction: a second retrieval after
a first, a never-existed handle, and an unreachable store. The vacuous-control questions for
this control: it exists (`temp_password_store.py:63-66`); it declares a scope (atomic GET+DELETE
against TOCTOU); what it actually examined was one sequential round trip per claimant, never two
claimants at once. The path by which a verdict would have reached a decision exists and is cheap
— two simultaneous `GET /admin/temp-passwords/{token}`.

**Consequence** — A positive safety claim about a single-use credential guard is stated as fact
where it was inferred, and a reader cannot tell from the report that it was not tested. No
roadmap step depends on it, so no remediation turns on it today.

**Recommendation** — Either run the two-claimant reproduction and quote it, or demote the
sentence to a stated expectation with the library contract named as its basis.

### VAL-04-009 — Appendix A lists an access-token gate with no production caller, anchored one line past the end of the file

**Severity** — LOW

**Zone** — Blocks 1 and 8, inventory accuracy

**Observation** — Disposition: **inventory overstates the live surface**. Appendix A's
access-token row lists `permissions.py:291-354` among the "Gate that accepts it".
`permissions.get_current_user` (`core/permissions.py:265`) and the
`_get_current_user_with_session` it delegates to (`:291-353`) have **no production caller**:
searching the tree for `get_current_user` returns the definition at `:265` and four calls, all in
`tests/test_permissions.py:310,320,335,341`. The file ends at line 353, so the row's upper anchor
`:354` does not exist. The same appendix correctly identifies three dead *minters*
(`authenticate_user`, `verify_token`, `refresh_token`) and declines to file them; the identical
observation applied to a dead *gate* was not made. Two consequences follow: an implementer of
AUTH-003's gate would not learn that a second identity-resolution path exists lacking both the
`is_active` check and the proposed `force_password_change` check, and AUTH-008's "the same holds
… in `core/permissions.py:325-334`" describes a path no request reaches.

**Evidence** — Exhaustive search for the symbol across the repository; file length read. The
findings' substantive claims are unaffected: no path reads the flag, and the flag is read by no
server path at all.

**Consequence** — No present-state effect. It is future risk on a path that is exported, tested
and ready to be wired, where the gate would then be silently bypassed.

**Recommendation** — Mark the row test-only in Appendix A, correct the anchor to `:291-353`,
and add one line to AUTH-003 that the same conditional belongs in
`_get_current_user_with_session` if that path is ever given a caller.

### VAL-04-010 — The roadmap's documentation step names four of the seven findings that change documented behaviour

**Severity** — MEDIUM

**Zone** — Block 5, recommendation executability

**Observation** — Disposition: **not substantiated as written; three named omissions**. Roadmap
step 7 schedules "AUTH-008 plus the doc components of AUTH-001, AUTH-003, AUTH-005" for the final
documentation pass. Three other findings change behaviour the corpus states in the opposite
sense, and none appears in that list. AUTH-002's fix turns the reset into a 5xx with an
unchanged account row: `docs/04-admin/admin-api.md:230-234` is an error table listing only
`400 / 400 / 500`, and `:236-243` lists the side effects with no failure mode at all.
AUTH-004's fix makes a password change invalidate the session: `docs/01-auth/auth-api.md:332`
states, in terms, "The user remains logged in after a password change (token is not
invalidated)". AUTH-006's fix makes retrieval return 503 on a transport fault: the same
`admin-api.md` retrieval section and the 404 contract its remediation blocker
(`tests/api/test_temp_password_retrieval.py:133-136`) both encode 404-only.

**Evidence** — Each cited line read and quoted above; each is falsified by the specific change
its finding recommends. AUTH-002's and AUTH-006's Recommendations name no documentation at all.

**Consequence** — A remediator working the roadmap in order leaves three false statements
behind, one of them a security-relevant one (`auth-api.md:332` will assert the opposite of the
new session semantics). The omissions are additive to a step that is already scheduled last,
so the cost is a missed line, not a missed pass.

**Recommendation** — Add `admin-api.md:230-234,236-243` and `auth-api.md:332` to step 7's
inventory, and give AUTH-002 and AUTH-006 a documentation clause in their own Recommendations.

## Disposition Tally

Audited findings, dispositions against the fixed vocabulary:

| Disposition | Count | Identifiers |
|---|---|---|
| confirmed | 8 | AUTH-001, AUTH-002, AUTH-003, AUTH-004, AUTH-005, AUTH-006, AUTH-007, AUTH-008 |
| re-typed | 0 | — |
| re-graded | 0 | — |
| merged | 0 | — |
| not substantiated | 0 | — |
| unsettled | 0 | — (one scoped claim left unsettled and recorded in Appendix K) |

8 = 8 = the per-finding verdicts. Bands are unchanged and carry the phase-04 rubric's scale,
not the validation scale: HIGH 3, MEDIUM 4, LOW 1, CRITICAL 0 — identical to the input's front
matter, which was re-counted against the bodies and found consistent. Validation-level findings
are counted separately and on their own scale: MEDIUM 5 (VAL-04-001, -002, -003, -008, -010),
LOW 5 (VAL-04-004, -005, -006, -007, -009). No identifier was renumbered; no band was silently
applied.

## Distribution

The eight findings fall on the admin credential-reset and approval workflow (AUTH-002, -005,
-006, -007 — four of eight), on session lifecycle and enforcement (AUTH-003, -004) and on the
pre-credential abuse bounds (AUTH-001). One (AUTH-008) is a documentation-accuracy defect on
the session path. The component carrying the most is `TempPasswordStore` and its two callers:
four findings, three of them the same subsystem, and one (AUTH-002) rated HIGH. No finding
landed in the token-minting primitives themselves — `create_access_token`,
`create_refresh_token`, `decode_token`, `validate_refresh_token` and the two blacklist prefixes
behave as documented, and the separation of the two lifetimes by claim name held under the
runtime cross-presentation test the report records. All eight reproduce in the `dev` tier.

The ten validation-level findings cluster in three places: the *recommendation* layer rather
than the claim layer (VAL-04-001, -002, -010 — every one a case where the finding stands and
the plan built on it does not), the *evidence* layer (VAL-04-003, -004, -005, -008), and the
*inventory and template* layer (VAL-04-006, -007, -009). No validation-level finding disputes a
system fact the input established.

## Cross-Finding Analysis

Two causes account for all eight audited findings, and this validation confirms both from the
executing path rather than accepting them.

**Cause 1 — the one-time credential handshake is treated as best-effort on both sides and as
a complete success on the way out.** `TempPasswordStore` is declared to fail open
(`temp_password_store.py:33`) and both callers honour that declaration by committing anyway
(`auth_service.py:583-590`, `admin.py:321-330`), which is AUTH-002. The reading side collapses
three distinct states into one answer (`temp_password_store.py:73-75` → `admin.py:418-422`),
which is AUTH-006. The handle that authorises the read travels in the request line
(`admin.py:403-423`) and lands in two log stores, which is AUTH-005. This cause is confirmed and
is exactly as the report describes it: one optional, silently-degrading side channel wrapped
around an operation the rest of the code treats as mandatory.

**Cause 2 — the server treats credential state transitions as a client-side concern.**
`force_password_change` is written by both issuing paths and read by no server path
(AUTH-003); a password rotation writes no revocation state and use does not rotate the long
credential (AUTH-004); the bootstrap's idempotence message is emitted identically whether it
created a row or matched one (AUTH-007). Confirmed. AUTH-001 and AUTH-008 sit beside this cause
without being instances of it, and the report is right to say so.

The ten validation-level findings reduce to one further cause that the report did not name:
**the report states a great deal more confidently than it measured.** The wrong hit count, the
wrong Vite attribution, the unexercised concurrency claim, the test coupling declared absent,
and the runtime support drawn from a probe on a different path are all the same shape — an
assertion carrying more weight than the observation behind it. That is the single thing to
change about this report, and it is worth more than any single correction in it.

## Roadmap

Ordered, each step naming what it closes and what must be true before the next. This sequence
validates the input's grouping and adds the three corrections that must land with it.

1. **Correct the plan before executing any of it.** Apply VAL-04-001 (drop AUTH-001's option
   (b); make `forwarded_allow_ips` the whole fix), VAL-04-002 (add
   `tests/test_rate_limiting.py::test_rate_limit_reset_allow_writes` as a remediation blocker)
   and VAL-04-010 (extend the documentation inventory). *Must be true before step 2:* the
   remediation plan no longer names a bypass as a fix, and no recommendation asserts a
   dependency that does not exist.
2. **Cause 1, storage — AUTH-002 and AUTH-006 together**, as the input sequences them, with the
   two shipped tests named by the report plus the one named here. *Must be true before step 3:*
   a reset that cannot store returns 5xx and leaves `password_hash` unchanged, proven by a test
   that injects a failing store.
3. **Cause 1, transport — AUTH-005**, behind a one-release deprecation window. *Must be true
   before step 4:* no unredacted `temp-passwords/` URI appears in the application's INFO log.
4. **Cause 2, bootstrap — AUTH-007**, independent of everything below, and now with the
   documentation half it is entitled to (`logging.md:42`, `architecture.md:128,130` per
   VAL-04-007) rather than a note to be written. *Must be true before step 5:* a start-up
   against an occupied key emits a WARNING naming the stored role.
5. **Cause 2, session — AUTH-004 before AUTH-003**, in the order the input gives, with
   `auth-api.md:332` corrected in the same change. *Must be true before step 6:* a session
   issued before a password change is refused by `/auth/refresh` and by the per-request gate.
6. **Cause 2, enforcement — AUTH-003**, with the `Request` injection the dependency needs and
   the note about the second identity path. *Must be true before rollout:* the SPA's redirect
   reaches `/auth/change-password` and completes on a real admin-reset account, verified in a
   browser.
7. **Cause 2, bounds — AUTH-001**, with the Rollout Safety precondition already settled below.
8. **Documentation pass** — the input's step 7, extended by VAL-04-010.
9. **Optional, and worth doing because it is cheap:** the two-claimant reproduction behind
   VAL-04-008, so the report's single-use claim is observed rather than inferred.

AUTH-001 moves later than the input placed it (its step 6 becomes step 7) because its
remediation plan is the one that had to be rewritten first. Nothing else changes order.

## Rollout Safety

The input identifies steps 1, 4 and 5 as behaviour-changing with real blast radius. That is
correct and complete for the shipped system; three things change on the strength of this
validation.

**AUTH-001's hidden precondition is already decided by the shipped compose files, and it fails
in the dev tier.** The input asks the implementer to "verify reachability of `app:8000` from
outside the compose network before enabling". Both answers are readable now. Production holds:
`docker/docker-compose.yml:243-244` publishes only nginx `80:80`, and the `app` service declares
no `ports:` at all, so in the shipped production topology `app:8000` is reachable only from
inside the compose network. Dev fails: `docker/docker-compose.override.yml:104-108` publishes
`${APP_HOST_PORT:-8010}:8000` with **no host-IP restriction** — note the contrast two services
later at `:155-158`, where `db` is deliberately bound to `127.0.0.1` with a comment saying not
to change it. So enabling `forwarded_allow_ips` for the compose network in the dev tier is safe
(the trusted set is the network, and the host-published port arrives from the docker gateway,
which is not in it), while enabling `*` anywhere would be unsafe in dev and must be confined to
production. The report's warning is right and its verification step is now unnecessary.

**A step that is half-done kills every session, and the report's mitigation is correct.**
`axiosInstance.ts:66-124` confirms the retry-on-401 machinery the input relies on, and
`:117-119` confirms what happens when refresh fails: a toast and a hard redirect to `/login`.
The input's sequence — rotate-and-reissue with the old jti not yet revoked, verify a 20-minute
session in a real browser, then add the revoke — is the right one, and the reason it is right is
now sharper than the report states: the failure mode is not a silent hang, it is every user in
the system being bounced to the login page by their own interceptor, and by AUTH-001 that page
may itself be rate-limited.

**Steps that add a 503 or a new gate are visible to the client and the client's handling of
them is already good.** The input asks whether `shared/api/errorHandler.ts` maps 503 to
something better than a generic failure. It does not do the mapping itself — it extracts the
RFC 7807 `code` at `errorHandler.ts:57-58` and the caller resolves the message through
`shared/api/errorMessages.ts`, which already carries
`SERVICE_UNAVAILABLE: 'Service temporarily unavailable'` at `:16`. The concern resolves in the
report's favour; only the file pointer needs correcting.

## Appendices

### Appendix A — Block 1: claim re-derivation ledger

Every location reference was resolved mechanically before the claim was tested. No anchor points
into lines that do not exist except the one recorded in VAL-04-009.

| Finding | Executing path re-derived | Anchor resolved | Claim on its own terms | Asserted cause, tested separately |
|---|---|---|---|---|
| AUTH-001 | `auth.py:83-90`, `:88-90` before `:101`; `security.py:132-135`; `proxy_headers.py:34`; `Config.forwarded_allow_ips == '127.0.0.1'`; peers `172.21.0.2`/`.6` read from `docker inspect` | yes, all | **confirmed** | **partly refuted** — nginx yes, Vite no (VAL-04-003) |
| AUTH-002 | `temp_password_store.py:40-48`; `auth_service.py:582-590,595-599,169,307,381`; `admin.py:299-303,321,330,335` | yes, all | **confirmed** | correct; adds an unreported variant (store `None`) |
| AUTH-003 | 8 occurrences of the flag in `src/`, none a comparison; `deps.py:472-576`; `user.py:69-74`; `models/user.py:49`; `useAuth.ts:37,81,108`; `LoginForm.tsx:39` | yes, all | **confirmed** | n/a — the claim is an absence, and the absence holds |
| AUTH-004 | `security.py:299-337,466-539,535-538`; `auth.py:115-123,275-382,297,448,459,368`; `admin.py:176`; `auth_service.py:469-519`; one `set_secure_cookie` in the file | yes, all | **confirmed** | correct; the "two call sites each" wording is one per function |
| AUTH-005 | `admin.py:403-423,415-416,226,332-336`; `auth_service.py:581`; `nginx.conf:10,34-40`, no `log_format` anywhere in the file | yes, all | **confirmed** | correct; `:332-336` is the approval route, not the reset route |
| AUTH-006 | `temp_password_store.py:50-75,63-66,73-75`; `admin.py:417-422` | yes, all | **confirmed** on the conflation | the atomicity inference is sound reasoning with no observation behind it (VAL-04-008) |
| AUTH-007 | `starter.py:168,171,349-352,356-370,362,371` read pre-remediation; re-resolved to `:174,177,368-382,373,382` post-remediation, `DO NOTHING` and the success line unchanged; `config.py:356` → `:381`; `auth_service.py:40,104` | all resolve, in one tree or the other (see the finding) | **confirmed**, substance survives the concurrent remediation | correct; the doc predicate is met and uncited (VAL-04-007) |
| AUTH-008 | `security.py:492-504,507-519,542-554,503,553`; `deps.py:570-576`; `auth.py:341,368`; `permissions.py:325-334` | yes, all | **confirmed** statically and completely | the probe offered as runtime support is on a different path (VAL-04-005) |

Two documentation claims that contradict the executing path, found while re-deriving AUTH-007
and both **inside its own subsystem** rather than newly filed: `docs/06-backend/architecture.md:128`
asserts a SAVEPOINT the bootstrap does not use, and `:130` scopes a warning to development that
`starter.py:349-352` emits unconditionally. Both belong to AUTH-007's documentation half; see
VAL-04-007.

### Appendix B — Block 2: the vacuous-control angle, applied to the input

The angle asks three separate questions per control and keeps a fourth apart: does it exist,
what scope does it declare, what did it actually examine — and, separately, whether it ran at
all. Every check, gate or shipped regression a claim leans on was put through it.

| Control a claim leans on | Exists | Declared scope | Actually examined | Reached a decision? |
|---|---|---|---|---|
| `AsyncRateLimiter` + `RATE_LIMITER_FAIL_CLOSED` (AUTH-001) | yes, `security.py:106-151`, `config.py:366` | per-attempt bound per key | the transcript's 200×5 then 429 | **yes** — the limiter returned 429; armed and deciding |
| `TempPasswordStore.store` (AUTH-002) | yes, `temp_password_store.py:30-48` | accept or fail open | a subclass pointed at `127.0.0.1:1` | **yes** — the swallow and the committed write were both observed |
| `TempPasswordStore.retrieve` atomic GET+DELETE (AUTH-006) | yes, `temp_password_store.py:63-66` | exactly one winner under concurrency | one sequential round trip per claimant; never two claimants at once | **no** — the claim that it reached a decision is an inference from `redis-py` semantics (VAL-04-008) |
| The store's tri-state refusal (AUTH-006) | yes, `admin.py:417-422` | distinguish spent / absent / unreachable | three sequential states, all observed to collide | **yes** — the collision is the finding |
| The `force_password_change` guard (AUTH-003) | yes, the column and the two writes | force a change before ordinary use | nothing: no consuming path is searched or reached | **no** — present, configured, deciding nothing; this is the finding |
| The revocation reads (AUTH-008) | yes, `security.py:503,553` | distinguish revoked from not | none — static only, and the offered runtime probe is on another path | **no** — the control's failure mode is asserted (VAL-04-005) |
| The shipped rate-limit test (AUTH-001's dependency claim) | yes, `tests/test_rate_limiting.py:106-145` | reset the exhausted bucket | a hardcoded key literal at `:124` | **yes** — and the report recorded it as absent (VAL-04-002) |

One control green over zero items: the `force_password_change` flag is set by two issuing paths,
exposed on two API responses, documented as enforced in three places, exercised positively by
two shipped backend test files (`tests/test_force_password_change_backend.py`,
`tests/test_auth_api.py:403-459`) and two frontend test files — and consulted by no server path
whatsoever. Every one of those tests passes. This is the cleanest instance of the shape in the
whole set, and AUTH-003 found it.

### Appendix C — Block 3: each band against the phase's own rubric

The rubric of record is the severity section at `04-audit-authentication.md:116-123`. Bands are
graded by effect and blast radius anchored to present state, and a mechanism absent from an
enumerated band is not thereby a lower band.

| Finding | Band carried | Band the rubric implies | Mechanism it would be downgraded on | Verdict |
|---|---|---|---|---|
| AUTH-001 | HIGH | HIGH | none. No enumerated band fits a *collapse* of the limiter's key to a single constant; MEDIUM's "a caller identity for limiting that is asserted rather than observed" describes a caller-*supplied* value, which this is not | **upheld**, on effect: a system-wide, self-inflicted and attacker-triggerable outage of the only authentication surface |
| AUTH-002 | HIGH | HIGH | none. The rubric's HIGH names it almost exactly: "an irreversible write preceding a guard that can still refuse" | **upheld** |
| AUTH-003 | HIGH | HIGH | none. HIGH's "one gate admitting an account state another refuses" needs two gates disagreeing; here one gate admits everything. The rubric enumerates no band for "a guard set at issuance that no path consults", which block 6 names as a finding class | **upheld**, on effect |
| AUTH-004 | MEDIUM | MEDIUM | none. MEDIUM names it exactly: "a bearer credential with no binding to the client that obtained it" | **upheld** |
| AUTH-005 | MEDIUM | MEDIUM | none. CRITICAL is "a credential's cleartext reaching a surface outside its delivery boundary" — the cleartext does not; only the handle does. The report's stated reason for not claiming CRITICAL is the rubric's own letter | **upheld** |
| AUTH-006 | MEDIUM | MEDIUM | none, but MEDIUM's wording is the *inverse* polarity — "a refusal whose visible form distinguishes causes it should not", where this is a refusal that fails to distinguish causes it should | **upheld**, on effect, with the polarity mismatch recorded |
| AUTH-007 | MEDIUM | MEDIUM | none. The rubric's LOW is "unhelpful diagnostic text on a refusal path"; this is not a refusal path, and the operator's *only* signal is wrong | **upheld**, on effect |
| AUTH-008 | LOW | LOW | none. LOW names it exactly: "unhelpful diagnostic text on a refusal path" | **upheld** |

No re-grades. Three rubric gaps are recorded as observations rather than as bands: no band
covers a limiter whose key collapses to a constant; no band covers a guard that decides
nothing; and MEDIUM's wording is stated in the opposite direction from the defect block 4
actually asks about. A reader grading by mechanism rather than by effect would mis-file
AUTH-001 and AUTH-003 downward. The empty CRITICAL band is a positive result and is
substantiated: no path mints a session for an identity other than the verified one
(`/auth/refresh` resolves `sub` and reads `email` and `role` back off the row at
`auth.py:349-379`), no credential cleartext is logged anywhere on the issuing or retrieval
paths, and no credential survives a guard that should have refused it.

### Appendix D — Block 4: which side moves

No verdict is reserved in advance for any finding class, and re-typing runs in both directions.
The load-bearing artefact was identified for each finding, and where a component is labelled
dead the specification corpus was asked whether it is intended.

| Finding | Load-bearing artefact | The other side | Disposition |
|---|---|---|---|
| AUTH-001 | the code — a rate-limit key is a security decision the documentation cannot make | `auth-api.md:46,96` and `security-overview.md:44-46,52` misstate the granularity | **re-typed: code moves**, docs follow; the report already sequences it that way |
| AUTH-002 | the code — a committed credential nobody can claim is unrecoverable regardless of prose | `admin-api.md:236-243` describes side effects with no failure mode | **code moves**; docs gain the failure mode (VAL-04-010) |
| AUTH-003 | the code — the guard either exists server-side or it does not | `admin-api.md:204,239` and `overview.md:72` assert a control the server does not have | **code moves**; docs follow. `auth-api.md:334` is the one place the corpus is already accurate and must not be "corrected" |
| AUTH-004 | the code — session withdrawal is a server decision | `auth-api.md:332` states the opposite of the recommended behaviour | **code moves**; `auth-api.md:332` must change with it (VAL-04-010) |
| AUTH-005 | the code — a credential key in the request line is a design decision | `admin-api.md:243,396` claim the mechanism keeps secrets out of logs, which is true of the password and silent about the handle | **code moves**; the doc sentence is narrowed, not deleted |
| AUTH-006 | the code — three refusals collapsed into one answer is an operator-safety defect | no doc asserts the 404 contract; the shipped test does | **code moves** |
| AUTH-007 | the code — a false success line is a defect whichever side you blame | `logging.md:42` and `architecture.md:128,130` misstate the bootstrap, which is the predicate the phase's own scope requires | **code moves**, and the docs it already misstates get corrected (VAL-04-007) |
| AUTH-008 | the code is correct and fail-closed; the doc is wrong | `security-overview.md:234` | **documentation moves**; the code change is explicitly optional |

The dead-code question, asked properly: the corpus *expects* all three dead minters.
`interfaces/service_interfaces.py:39,53,75` declares them on `IAuthService`, the report found
that, and the verdict is **not a missing integration** — they are reachable through a declared
interface and their absence from `src/` is a completeness gap in the call graph, not an
unimplemented feature. Correctly not filed. The same question applied to
`permissions.get_current_user` gives the opposite answer for the report: nothing in the corpus
expects that gate, yet Appendix A presents it as live (VAL-04-009).

### Appendix E — Block 5: whether each recommendation can be carried out

| Finding | Target resolves and is stable? | Does applying it remove the defect? | Depends on | What else it breaks | Order | Verdict |
|---|---|---|---|---|---|---|
| AUTH-001 | yes, `auth.py:83-90` | **only via option (a)**; option (b) as written installs a bypass | the edge appending to, not replacing, the XFF chain; `app:8000` reachability | `tests/test_rate_limiting.py:106-145` (VAL-04-002) | last, after the plan is corrected | **substantiated, unusable as written** — correct then execute |
| AUTH-002 | yes, `auth_service.py:582-590` and `admin.py:321-330` | yes | hoisting the commit out of `register_user`, which every registration path shares | `test_temp_password_store.py:164-181`; `test_auth_service.py`, `test_admin_user_management.py`, `test_auth_api.py` assert the current commit placement | first | **usable** |
| AUTH-003 | yes, `deps.py:544-550` | yes | injecting `Request` into the dependency — the named "one conditional" is not the whole change — plus an allow-list the SPA's own flow needs | the second identity path at `permissions.py:291-353` (VAL-04-009); any flag set during the window stays set | fifth | **usable, with two named additions** |
| AUTH-004 | yes, `auth.py:377-382` and `:118-123` | yes | none beyond what already ships | `auth-api.md:332` becomes false (VAL-04-010) | fourth | **usable** |
| AUTH-005 | yes, `admin.py:403-423` | yes | a one-release deprecation window | the retrieval URL stops working for any client that cached it | third | **usable** |
| AUTH-006 | yes, `temp_password_store.py:73-75`, `admin.py:417-422` | yes, for the store fault; the spent/absent split is correctly deferred | nothing | `test_temp_password_store.py:184-190`; `test_temp_password_retrieval.py:129-136`, cited at the wrong three lines | first, with AUTH-002 | **usable** |
| AUTH-007 | yes, `starter.py:358-371` | yes | nothing | nothing | any point | **usable** |
| AUTH-008 | yes, `security.py:502-504,552-554` | yes, and the doc fix alone removes the false statement | nothing | nothing | last | **usable** |

All eight recommendations name a documentation site that must change with the fix. Only two
name a shipped test — AUTH-002 and AUTH-006 — and both name the right test, one of them three
lines off. No recommendation offers a menu of alternatives without a chosen default, which is
the failure mode phases 01 and 02 both recorded; AUTH-001's "(a) and/or (b)" is the only
instance here, and it is the one that is unsafe.

### Appendix F — Block 6: cross-phase comparison, ownership, and the seam check

Sibling reports compared against: `.ai/audit/01-process-architecture/findings.md` (raw) and
`.ai/audit/99-validation/01-process-architecture-validated-findings.md` (validated);
`.ai/audit/02-configuration-secrets/findings.md` (raw) and
`.ai/audit/99-validation/02-configuration-secrets-validated-findings.md` (validated). Phase 03
was still executing against the shared dev stack and has no report to compare; nothing in this
appendix contests it.

**AUTH-002 ↔ TOPO-006 — adjacent concern, cross-reference, not a merge and not a conflict.**
TOPO-006 (phase 01) files the admin approval route at `admin.py:305-345` as four cross-store
effects with a non-transactional Redis write before `db.commit()`. AUTH-002 names the same
route and the same ordering as part of the temp-password handshake. The mechanism is the same;
the defect is not. TOPO-006 is about the unit of work and what a rollback cannot undo;
AUTH-002 is about the store *declaring* its own failure and being obeyed — the write would land
even with a single store, in one transaction, if the store did not swallow. Same lines,
different root cause, so a cross-reference. Phase 04's scope paragraph assigns "the exclusion
and unit-of-work semantics behind the account" to phase 03, which raises a live ownership
question about TOPO-006's filing; that question is **not** contested here — it belongs to the
coordinator and to phase 03, and TOPO-006 is left exactly as filed.

**No conflict with phase 01 or phase 02 on any subject.** No two claims in the set disagree
about the same subject.

**No duplicate.** Phase 04's deferrals are clean and verifiable, and each names the right
owner: `CFG-001/002/003` for the signing secret (Appendix B); `CFG-007` for
`APP__COOKIE_SECURE` (Appendix G); CFG-001 for the production-tier label (Appendix G, as a
reliance rather than a re-file, and accurate); phase 15 for hash cost and at-rest policy;
phase 10 for store key lifetime; phase 07 for the bound's own store unavailability; phase 09 for
suite adequacy. Nothing phase 04 declined to file on those grounds is recoverable from its own
evidence, and the three it does file carry no other phase's prefix.

**The phase-12 boundary is respected, and respected explicitly.** The instruction to phase 04
was to defer the per-request gate fix seams to phase 12. Two findings touch that line and both
stay on the correct side of it. AUTH-003's recommendation is confined to the identity
dependency, and its evidence uses the 403/404 shapes observed for a viewer on business routes
only as proof that the identity gate had already admitted the session — Appendix G states that
"no authorization decision is evaluated here", which is the correct reading. AUTH-004's Rollout
Safety goes further and routes the concern outward: "Zone 12 owns the per-request gate, so if a
revocation check is to be added to the access path rather than only to `/auth/refresh`, route it
through 12 rather than widening this phase." Neither finding files a per-request authorization
decision, and no finding's recommendation requires widening phase 04's scope to land.

**The seam check — one finding whose zone falls outside the input's own declared scope: none.**
All eight findings map to an owned concern in the scope paragraph: AUTH-001 to "the identity an
abuse bound is keyed on and whether the caller can choose it"; AUTH-002, -005 to "issuance,
storage, single use"; AUTH-004, -008 to "what a revocation marker must be able to express to
withdraw a credential"; AUTH-006 to "single use, lifetime and refusal"; AUTH-007 to "the
identity namespace the handshake writes into"; AUTH-003 to the completion path, which the
scope paragraph covers through "refusal of every credential" and the Purpose paragraph covers
directly as "the session-layer consequences". All eight Zone strings also name a real block of
this phase's own nine. One zone is not quoted verbatim (VAL-04-006), which is a template defect
rather than a seam.

### Appendix G — Block 7: finding-ID namespace integrity, and the ruling

Every provenance claim was re-derived from the working tree, not inherited.

| Property | Result |
|---|---|
| Prefix declared by the phase's own report-output contract | `AUTH-`, at `04-audit-authentication.md:129` |
| Identifiers minted past runs | `AUTH-001` … `AUTH-008`, contiguous, no gap, no duplicate, none renumbered |
| In-source markers in shipped code, configuration, tests and documentation | **none**. A search for `AUTH-0dd` across `src/`, `tests/`, `alembic/`, `docker/`, `docs/` and `frontend/src/` returns zero hits |
| Compound form the template's front-matter `phase:` pairs with the prefix | `phase: 04-authentication` + `AUTH-` → `04/AUTH`. The input writes the bare prefix under a phase-named directory, which is the same convention `TOPO-` and `CFG-` used, so the form is consistent across the set rather than divergent |
| Namespace reused across phases | **none**. All sixteen active phase contracts and four archived ones declare twenty distinct prefixes: `TOPO-`, `CFG-`, `TXN-`, `AUTH-`, `DP-`, `ART-`, `EXT-`, `QLT-`, `TST-`, `OPS-`, `PERF-`, `AUTZ-`, `FE-`, `MIG-`, `SEC-`, `CHT-`, `AD-`, `PII-`, `SRH-`, `I18N-`. `AUTH-` belongs to exactly one phase |

**Ruling applied: reuse `AUTH-`.** A new run reuses the declared namespace rather than minting a
second one beside it, no identifier is renumbered, and — because there are no in-source markers
— there is no load-bearing provenance for a follow-up to migrate and no drift to retire.

**Deviation from the literal output contract, recorded as required.** The contract assigns the
flat `VAL-` prefix to validation-level findings. That space is **already occupied**: the phase-01
validation report holds `VAL-001` … `VAL-008` and the phase-02 validation report holds
`VAL-001` … `VAL-009`, so two sibling reports already collide with each other. This report does
not renumber into that space and does not touch either sibling file. Its validation-level
findings carry the `VAL-04-` infix, `VAL-04-001` … `VAL-04-010`, in their own section, and the
collision is reported here rather than resolved by minting a third variant of the same
identifiers.

### Appendix H — Block 8: the shared findings template as a controlled artefact

The template resolves and is the artefact under validation. It is not repaired from inside this
run; its defects are recorded.

| Mandated element | Status across this report | Verdict |
|---|---|---|
| Front matter `phase:` | `04-authentication` — the phase that wrote the input, honestly stated | present and honest |
| Front matter `executed:`, `executor:`, `problems-only:`, `findings:`, `by-severity:` | all present; `findings: 8` and `by-severity` HIGH 3 / MEDIUM 4 / LOW 1 / CRITICAL 0 both re-counted against the bodies and **agree** | present and honest |
| The six per-finding fields | all six present on all eight findings, none omitted, none renamed | compliant |
| The rule that the Zone be the block title quoted verbatim | seven of eight verbatim; AUTH-007 paraphrases the final clause | **one violation** (VAL-04-006) |
| The reserved empty-state string | not applicable — the phase produced findings and did not pad | compliant |
| The required sections | front matter, Summary, Findings, Distribution, Cross-Finding Analysis, Roadmap, Rollout Safety, Appendices — all eight present | compliant |
| The template's own "No finding without all five fields" | the template enumerates **six** fields (Severity, Zone, Observation, Evidence, Consequence, Recommendation) | **defect in the template** |

The last row is a duplicate of `VAL-008` in the phase-01 validation report, which recorded the
same off-by-one. This is a **merge into that finding's root cause**, not a new identifier: the
defect is unrepaired, correctly, because no per-phase run repairs a shared artefact. Recorded
rather than edited.

A second template gap is relevant here and is likewise already filed: the template mandates no
`Disposition` and no `Location` field, while this phase's output contract requires a verdict on
every finding and requires the location to be carried inside the Observation field. This report
complies by carrying the disposition as a bolded lead inside Observation and the anchor in the
same field. Cross-reference: `VAL-009` in the phase-02 validation report.

One deviation from the template's front matter is declared: the keys `validation-findings:` and
`by-validation-severity:` are added so that the two severity scales — the phase-04 rubric's for
the eight adjudicated findings and the 99 rubric's for the ten validation-level findings — are
never summed into one column. The template's own `findings: 8` and `by-severity` continue to
describe the audited findings alone, which keeps the tally honest.

### Appendix I — Block 9: does the input rest on its own declared blocks and evidence fields

| Finding | Support: declared block / own evidence / independent observation | Angle the declared blocks do not name |
|---|---|---|
| AUTH-001 | block 9 + own evidence | none — and the one angle it *does* name is the one that produced it |
| AUTH-002 | block 1 + own evidence | none |
| AUTH-003 | block 6 + own evidence + an independent `Select-String` | none |
| AUTH-004 | block 8 + own evidence | none |
| AUTH-005 | block 1 + own evidence (the access-log line) | none |
| AUTH-006 | block 4 + own evidence | none |
| AUTH-007 | block 5 + own evidence (the live reproduction) | none |
| AUTH-008 | block 8 + **static proof only**; the runtime support offered is from a different path (VAL-04-005) | none |

Every substantive finding rests on its own declared block list and its own evidence fields. No
finding arises from an angle the declared blocks fail to name — this input is unusually
well-aligned, and the alignment is not a defect. The observation belongs in the negative
direction instead: the report's *assertions* run ahead of its declared evidence in three places
(VAL-04-003, -004, -008), which is the same finding a mis-aligned phase produces by accident,
arrived at here by a different route.

Two of the phase's own evidence items produced no finding and no appendix entry. Block 4's
"concurrent-claim and concurrent-spend outcomes" is the one that matters, and it is VAL-04-008.
Block 6's "the cause-by-response matrix for refusals" and "an account state left behind by a
refused attempt" produced nothing, though the same ground is covered from block 4's direction by
AUTH-006 and AUTH-002; the block-6 items are narrower duplicates rather than gaps.

### Appendix J — Block 11: the shared angles and their bindings

**The vacuous-control angle**, defined at `99-audit-validate.md:60-69`, asks three questions per
control — does it exist, what scope does it declare, what did it actually examine — with a
fourth kept apart: whether it ran at all. Four phases bind it.

| Binding phase | Wording used | Do the three questions survive? |
|---|---|---|
| 09, `09-audit-test-coverage.md:100-103` | "Bind the shared vacuous-control angle here, in the gate-and-suite form: for every control that can emit a verdict on this repository, establish what it is configured to examine and what it actually examined" | **yes, all three** — existence at `:97` ("whether it is loaded"), declared scope and actual scope verbatim, and the fourth question at `:97` ("what invokes it"). `:104` even requires "the controls with the item count each examined", the exact evidence 99 asks for. The most faithful binding in the set |
| 10, `10-audit-production-ops.md:61-68` | block title "Controls in the deployed surface: existence, declared scope, and what they examined"; body "establish what it is configured to examine and what it actually examined" | **yes, all three** — all three named in the block title itself, and the fourth question kept apart at `:67-68` ("one that gates the boot order by success rather than by completion") |
| 02, `02-audit-configuration-secrets.md:107-111` | "The vacuous-control angle is 99's; what a configuration gate examines is this block's. For every validation and gate over configuration, establish what values it reads, what predicate it applies to them, and whether that predicate can match the form the value takes" | **partly** — existence and actual examination are asked in the phase's own words; the *declared* scope question is only implicit, and the invocation-site question at `:110-111` substitutes for it. A binding that has drifted slightly, not into a different question |
| 08, `08-audit-code-quality.md:144` | "the vacuous-control angle is 99's" — a deferral with no restatement | **the angle is claimed but not bound.** The three questions are nevertheless performed at `:138-143` in the phase's own words: "what it decides, what value it compares against, where it is invoked from, whether it is reachable by a contributor the way the automated path reaches it, and whether the aggregate entry point … invokes every gate". A claim without a binding, honoured in substance |

**No binding asks a different question from the one 99 defines, and no binding is claimed by a
phase that does not perform it.** The one drift in the set is phase 02's silent substitution of
declared scope for invocation site, which is noted rather than filed: it narrows the angle
without inverting it.

**The cross-resource side-effect angle**, defined at `99-audit-validate.md:160-163` — an effect
spanning more than one resource, together with which resource is the real unit of atomicity — is
**bound by no phase in the set.** Not one of the sixteen active or four archived contracts names
it or restates it. The question is nonetheless live and owned twice, in each phase's own words:
phase 03's Purpose at `03-audit-db-concurrency.md:11` asks "what an effect that spans more than
one resource leaves in between" and its rubric at `:118` grades units of work, while phase 05's
block 3 at `05-audit-data-pipeline.md:57-59` asks "The unit of atomicity: what commits together,
and what a rollback leaves behind" and `:13` claims "One angle is owned here alone: side
effects". Phases 05 and 06 then route the record-and-file instance to 05
(`06-audit-file-artifacts.md:26,97`). So the set has an angle defined once by 99, claimed by
nobody, and a question owned by two phases with no adjudication path between them. That is a
set-level ownership observation for the coordinator, not a defect in this input; phase 04 binds
neither angle and correctly leaves the live instance to the phase that filed it first (TOPO-006)
and to itself only for the narrower fail-open half (AUTH-002).

### Appendix K — Coverage ledger

Blocks examined and the item count each reached.

| Block | Items reached | Notes |
|---|---|---|
| 1 — claim re-derived from the executing path | 8 findings, 8 anchors fully resolved, 8 asserted causes tested separately; 1 anchor overshooting the file end; 2 documentation claims found contradicting code inside AUTH-007's subsystem | all read-only; no request issued against the dev stack |
| 2 — vacuous-control angle | 7 controls a claim leans on; 1 control green over zero items | 3 controls did not reach a decision; all 3 filed |
| 3 — grade against the phase's own rubric | 8 findings, 8 bands, 0 re-grades | 3 rubric gaps recorded as observations |
| 4 — which side moves | 8 findings; plus the specification-corpus question on 3 dead minters and 1 dead gate | no finding re-typed, merged or rejected |
| 5 — recommendation executability | 8 recommendations; 8 shipped test files read (6 named tests), 19 documentation sites read | 1 unusable as written, 3 with missing dependencies |
| 6 — cross-phase conflict, ownership, seam | 8 findings against 2 raw and 2 validated sibling reports; 1 cross-reference (AUTH-002 ↔ TOPO-006); 0 merges; 0 conflicts; 1 seam check run with 0 violations | phase 03 had no report to compare |
| 7 — namespace integrity | 20 declared prefixes across 20 contracts; 8 identifiers; 6 source trees searched for in-source markers | ruling: reuse `AUTH-`; collision found in `VAL-` and reported |
| 8 — the template as a controlled artefact | 7 mandated elements; 8 findings; 8 report sections | 1 zone violation; 2 template defects, both merges into sibling reports |
| 9 — declared blocks and evidence fields | 8 findings; 2 undischarged evidence items in the phase's own block list | 1 undischarged item filed |
| 10 — the validated report as an artefact | 8 verdicts, tally reconciled, identifiers preserved, two scales separated, 2 declared deviations | see the record below |
| 11 — the shared angles and their bindings | 2 angles; 4 vacuous-control bindings; 0 cross-resource bindings | 1 drift, 1 unbound angle |

Every claim left unsettled, with its reason.

1. **AUTH-001's production-tier blast radius.** The finding states the production consequence
   ("in the production topology … every login from every user of the system lands in one bucket")
   as a deduction, and its own Appendix G declares that the production tier was never started.
   It was not started here either: it needs a populated `.env` and a prior `npm run build`, and
   the instruction for this run forbids reconfiguring the shared dev stack. The deduction is
   sound on the shipped configuration — `nginx.conf:34-40` sets the forwarded headers,
   `Dockerfile:179` runs uvicorn with no trust setting, and `proxy_headers.py:34` discards them
   for a non-loopback peer — and the *mechanism* was re-derived end to end without the
   production tier, so the claim as filed is recorded as **confirmed**. The observation of the
   production tier itself is **unsettled**, and its rate is not a sample: zero observations were
   taken, against the 1 dev-tier observation and 1 static derivation the mechanism rests on.
2. **The unexercised single-use concurrency claim.** Whether two simultaneous claimants against
   one retrieval token resolve to exactly one winner was not observed on this system
   (VAL-04-008). Recorded as **unsettled** on the runtime question and argued as a library
   contract; the sampled rate is 0 of the 1 required concurrent observation.
3. **The two live transcripts.** AUTH-002's and AUTH-004's reproductions were not re-run. They
   were accepted on the executing path, which settles both claims completely without them — the
   fail-open swallow and the absent revocation write are static facts — and re-running them
   would have required the account and Redis state they create. Recorded as **unsettled on
   reproduction, confirmed on the path**, with 0 of 2 transcripts re-run.
4. **Nothing was disturbed.** No dev or test container was started, stopped or reconfigured; no
   row was written; no Redis key was created, altered or removed. The only Redis interaction was
   three read-only `redis-cli --scan` calls, which found no `login:*`, `refresh:*` or `temp_pwd:*`
   residue and the single `user_tokens_revoked:4cac4366-…` key the input's Appendix F already
   identified as predating its run. Two `mkobi-app-run-*` ephemeral containers belonging to
   another phase's probes were left untouched. No file in the repository was created, modified
   or deleted by this validation, and the untracked `probe_upload.csv` at the repo root was not
   read or removed.
5. **Anchor drift during the run, from another agent's work — two files, not one.** A phase-02
   configuration remediation executed concurrently with this validation
   (`.ai/plans/01-configuration-secrets-remediation-execution.md` is newly untracked; `git status`
   shows `src/mkobi/config.py`, `src/mkobi/db/starter.py`, `tests/test_config.py` and
   `tests/test_starter.py` modified). No file of the four was touched by this validation.
   **Every behaviour under audit is unchanged**, so no claim in this report is affected and no
   disposition moves; what moved is *line position*. `src/mkobi/config.py` gained 25 lines:
   `admin_username` `:356` → **`:381`**, `rate_limiter_fail_closed` `:366` → **`:391`**,
   `temp_password_ttl_seconds` `:369` → **`:394`**, `refresh_token_expire_minutes` `:186` →
   **`:211`**, `blocked_domains` `:262` → **`:287`**. `src/mkobi/db/starter.py` grew 434 → 445
   lines and `ensure_admin_user` was rewritten: the call site `:168` → **`:174`**, the
   environment gate `:171` → **`:177`**, `db.begin()` `:356` → **`:368`**, `ON CONFLICT (email)
   DO NOTHING` `:362` → **`:373`**, the success line `:371` → **`:382`**, the weak-username
   warning `:349-352` → **`:360-363`**. **AUTH-007 survives in full** — the `DO NOTHING` clause
   and the unconditional `Admin user ensured` line are byte-identical after the rewrite, the
   call still precedes the environment gate, and the rewrite only widened the weak-username
   predicate from one literal to `WEAK_USERNAMES` (a *weakness* test, not an *occupancy* test, so
   the finding's defect is untouched). One support sentence is restated rather than renumbered in
   the AUTH-007 block above. Recorded rather than corrected in place, because the files are
   mid-edit and a renumbering now would be stale again by the time it was written. Any triage
   following these anchors must re-resolve them against the post-remediation tree; the
   post-remediation values are the ones given above.
6. **Two observations about that in-flight remediation, recorded as leads for its owner and not
   adjudicated here** (both are outside phase 04's declared scope, and no finding is filed on
   either). First, `config.py:657` still carries the pre-remediation inline form
   `self.admin_username.lower() in {u.lower() for u in WEAK_USERNAMES}` while `:423` and `:449`
   now call `is_weak_credential(self.admin_username, WEAK_USERNAMES)` — the de-duplication this
   validation's sibling phase recorded as `VAL-003` appears partially applied. Second, the
   rewritten tier test moved from `!= EnvironmentEnum.DEVELOPMENT` to
   `== EnvironmentEnum.PRODUCTION`, so the `TEST` tier now raises on a weak admin password where
   it previously did not; the rewrite also added `change_me*`, blank and length checks, and a
   `WEAK_USERNAMES` import that the old code did not use.





