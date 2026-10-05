---
phase: 04-authentication
executed: 2026-10-05
executor: validator
problems-only: true
findings: 9
by-severity:
  CRITICAL: 0
  HIGH: 1
  MEDIUM: 3
  LOW: 4
---

# Phase 04 — Validated Findings (Authentication)

> **Path note, recorded so a later run does not correct it.** This phase's file stem is
> `{NN}-{phase-name}-validated-findings.md` while its output directory is `99-validation/`. The divergence is
> deliberate and declared by `.kilo/commands/audit/phases/99-audit-validate.md` (Report Output, first bullet).

## Summary

All nine findings were re-derived from the executing path on the working tree as it stands, not from the
report's quotes. Eight survive: four confirmed, four confirmed with the evidence or the impact statement
corrected. One is rejected as filed. Every citation in this report was re-opened at its quoted lines
immediately before composition, and no cited anchor had drifted — which is itself the opposite of phase 01's
and phase 02's experience and is recorded as such rather than assumed. Three runtime claims were reproduced
independently rather than accepted: the expired-token path, `alg: none` rejection on **both** decode paths, and
the revocation-write fault propagation. One band moves: **AUTH-101 HIGH → MEDIUM**, because none of the four
mechanisms phase 04's rubric reserves HIGH for is present, while its MEDIUM band describes the defect
precisely; the mechanism itself is fully confirmed and it stays first in the roadmap. AUTH-104 is corrected
because its force-mode sub-claim is refuted by the same commit that cleared the flag it depends on. AUTH-109 is
rejected: its dead-surface half duplicates the already-validated `TOPO-104`, and its new half is filed outside
this phase's declared scope.

**The most consequential result of this pass is not in the nine findings.** Appendix C records, as an
established absence, that "Verification cost is uniform between a matching and a non-matching identity …
measured at **268.9 ms** median against **283.6 ms** for a real cost-12 verification on this host, a 1.1x
ratio, so the timing defence the comment claims does hold". That measurement is not reproducible and is not
merely imprecise: `bcrypt.checkpw` **raises** `ValueError: Invalid salt` on the placeholder literal, so
`verify_password` returns in **0.1 ms** against **266–273 ms** for a real verification — a ~2,600x oracle on
`POST /auth/login`, defeating a control the code comment at `auth_service.py:196-199` explicitly claims to
provide. It is recorded as `VAL-04-001` in its own section, because it is a defect in the audit, not a
finding of the phase.

**Verdict vocabulary.** The instruction for this pass requires `CONFIRMED / CORRECTED / REJECTED`; the
99-validation phase fixes the vocabulary at `confirmed / re-graded / merged / not substantiated / unsettled`.
The mapping used per finding is: **CONFIRMED** = confirmed · **CORRECTED** = confirmed with the evidence,
the impact or the band re-derived (re-graded where the band moved) · **REJECTED** = not substantiated as
filed.

---

## Findings

Findings appear in descending final severity. Each carries the verdict, the zone quoted verbatim from
`.kilo/commands/audit/phases/04-audit-authentication.md`, and the location inside the observation.

### AUTH-102 — A committed password change whose revocation write faults is answered 500, and every other session of that user survives

**Severity** — HIGH (re-derivation of the audited band, sustained)

**Zone** — "Single-use and lifetime guarantees, in both directions"

**Observation** — CONFIRMED. Both halves of the claim hold, and the contrast with the admin siblings is real,
not rhetorical. `src/mkobi/api/routes/auth.py:671-695` wraps the service call in `try`/`except` and the block
**closes at `:695`**; `revoke_all_user_tokens` at `:704-709` is therefore the security-relevant call outside
every `try` in the handler, and `AuthService.change_password` has already committed at
`src/mkobi/services/auth_service.py:520` (with `force_password_change=False` written at `:518`) before the
handler regains control. `revoke_all_user_tokens` does not absorb the fault: `src/mkobi/core/security.py:684`
is a bare `await redis_client.setex(key, ttl, revoked_at)` with no handler, in contrast to the three readers
`is_token_revoked` / `is_refresh_token_revoked` / `is_user_tokens_revoked`
(`:536-543`, `:560-569`, `:736-747`), which each wrap their store call and raise `RevocationStoreUnavailableError`.

**Evidence** — Reproduced independently, not accepted: with `revoke_all_user_tokens` driven by a client whose
`setex` raises, the call **propagates** `ConnectionError` out of the function — no swallowing at either layer.
The escape path is `src/mkobi/utils/exceptions.py:344-348`, whose `@app.exception_handler(Exception)` logs
`"Unhandled exception: %s"` and answers a bare `500 INTERNAL_ERROR` / `"Internal server error"`
(`:349-356`). The two admin siblings guard the identical seam: `src/mkobi/api/routes/admin.py:309-329`
(password reset — `try` at `:310`, `except Exception as revoke_error` at `:317`, `AppException(INTERNAL_ERROR)`
with `"Password was reset successfully, but revoking the user's sessions failed; a second reset is required."`)
and `src/mkobi/api/routes/admin.py:195-214` (deactivation — same shape, `"User was deactivated successfully,
but revoking the user's tokens failed"`). Both quoted ranges are byte-exact as filed.

**Correction — one overstatement in the observation.** "The only call in the handler that no `try` covers" is
literally false: `get_config()` (`:703`), `logger.info` (`:711`) and `SuccessResponse(...)` (`:712`) are also
outside the guard. The accurate statement is that `revoke_all_user_tokens` is the only unguarded call **whose
failure has a security consequence**. The finding's substance is unaffected.

**Correction — one overstatement in the consequence.** "No log line anywhere names the affected user" is too
strong: the gate logs `"User authenticated: user_id=%s"` at `src/mkobi/api/deps.py:640` on the same request, so
the user id is in the stream. What is true — and what matters — is that nothing records that the **password
write committed while the revocation did not**; `revoke_all_user_tokens`'s own `"All tokens revoked for user:
id=%s"` line (`security.py:685`) is unreachable on the fault path because it follows the `await`.

One further precision the report does not state, recorded because it bounds the exposure: while Redis is
actually down, the access gate itself answers `503` (`deps.py:658-666`), so the surviving sessions become
usable **after** the store recovers, bounded by their own TTL (access 15 min, refresh 7 days —
`docs/01-auth/auth-api.md:560-561`). The window is real; it is not "immediately during the outage".

**Consequence** — Under a Redis fault, `POST /api/v1/auth/change-password` changes the password, clears
`force_password_change` and answers 500. The caller is told the operation failed when it succeeded, and no
pre-existing access or refresh token is withdrawn. A user changing their password in response to a suspected
compromise is left believing the change did not land, while every session they were trying to terminate
survives until it expires. The marker is the shared mechanism for deactivation and admin reset too, so the
operator's model — "the marker is written after every credential change" — is true on two of three routes.

**Rubric hook for HIGH** — "an irreversible write preceding a guard that can still refuse" and "a revocation
marker that does not withdraw what it claims to withdraw". The credential commit is irreversible; the
operation is then refused; and the withdrawal it exists to perform does not happen. No CRITICAL mechanism is
present: no session is established for the wrong identity, no cleartext leaves its boundary, no credential
remains usable after a guard that should have refused it.

**Recommendation** — Executable as filed. The target exists and is stable (`auth.py:704`), the shape to copy
exists (`admin.py:310-329`), and the recommendation's named symbols all resolve: `RevocationStoreUnavailableError`
is imported at `deps.py:53` and mapped to 503 at `deps.py:658-666`, and the `_fault_store` helper the
recommendation names for the new test exists at `tests/test_revocation_store_outage.py:28`. Prefer the 503
shape over `INTERNAL_ERROR`: it is honest about the cause and reuses an established mapping. No shipped test
blocks this — `tests/test_revocation_store_outage.py:1-13` states its own scope and covers only the two
revocation **read** paths (`_fault_store` faults `exists`/`get`; no test faults a **write**).

---

### AUTH-101 — A wrong current password is refused with 401, which the client's own interceptor turns into a refresh-and-replay loop ending in a sign-out

**Severity** — MEDIUM (re-graded from HIGH; the mechanism is confirmed, the band is not)

**Zone** — "Account state the credential cannot carry: the completion path"

**Observation** — CONFIRMED on the mechanism, CORRECTED on the band. The specific doubt raised for this pass —
whether the interceptor's refresh path actually replays the original request — resolves **yes**, and the loop
is real. `frontend/src/shared/api/axiosInstance.ts:112-126` is byte-exact as filed, and line `:116` is
`return axiosInstance(originalConfig)`: the replay goes back through the same instance's response
interceptor. `isRefreshing = true` is set at `:104`, and `finally { isRefreshing = false }` at `:124-126` runs
when the `try` block **returns** the replay promise — i.e. before that promise settles. A replayed 401
therefore re-enters `:69` with `isRefreshing === false`, starts another refresh and another replay.

The skip list is exactly as filed: `:71` exempts `/auth/login` and `:76` exempts `/auth/refresh`; neither
covers `/auth/change-password`. The backend arm is byte-exact: `src/mkobi/api/routes/auth.py:678-686` maps the
`ValueError` from `AuthService.change_password` to `AppException(AUTHENTICATION_FAILED)`, and
`src/mkobi/utils/exceptions.py:39` fixes that at `401`.

**Evidence** — The bounded-loop argument re-derives exactly. Each successful refresh rotates the cookie
(`auth.py:544-552`, `rotated_refresh_token = create_refresh_token(...)` then `set_secure_cookie`), and the
refresh rate limit keys the identifier on `_identifier_digest(refresh_token_value)`
(`auth.py:437-446`, `max_attempts=10`, `peer_max_attempts=100`, `ttl=300`) — so a rotated cookie lands in a
fresh identifier bucket and the per-identifier bound never engages. The registered handler is
`frontend/src/features/auth/api/authApi.ts:11-14`, installed at `:37` via
`frontend/src/shared/api/refreshHandler.ts:20-28`. When the peer ceiling is exhausted the refresh attempt
answers 429; the 429 branch at `axiosInstance.ts:65-67` rejects, `handler()` rejects, and the `catch` at
`:117-123` runs `removeToken()`, `toast.error(SESSION_EXPIRED_MESSAGE)` and `window.location.href = '/login'`.
`frontend/src/shared/api/errorSurfaces.ts:13` is the message verbatim. The consuming screen
(`frontend/src/features/users/ui/ChangePasswordPage.tsx:25-35`) and its caller
(`frontend/src/features/users/api/userApi.ts:9-11`, plain `axiosInstance.post`, no `skipErrorToast`) are
byte-exact as filed, as is the disabled Cancel control in force mode (`:105`).

The precedent that makes this a defect rather than a preference also verifies:
`docs/01-auth/auth-api.md:76` records that `403` is deliberate for `force_password_change` because "the SPA's
axios interceptor answers any `401` with a silent refresh and, on failure, a sign-out back to `/login`, so a
`401` refusal would become a redirect loop". `docs/01-auth/auth-api.md:366` publishes the `401` row as
intended behaviour. The route docstring that must change with it is at `auth.py:669`.

**Consequence, re-derived** — One mistyped current password costs the user their session and the real error
message: the submission ends at `/login` with "Session expired. Please login again." after up to ~100
refresh-and-replay iterations. Two qualifications the report overstates. (1) The iteration count is **derived,
not observed** — the report says so in its own Appendix D, and the derivation holds (each iteration consumes
one of the 100 peer refresh attempts and rotates the identifier), but no browser run witnessed it. (2) The
stated amplification is a **self-inflicted** cost, not an attacker-reachable one: reaching the replay requires
a valid session *and* a wrong current password, and `POST /auth/change-password` carries no rate limiter of its
own. The ~100 replays do each cost one cost-12 bcrypt verification, so a single mistake is worth roughly 25–30
seconds of server CPU, bounded to 100 per peer per 300 s. That is a reliability and messaging defect with a
modest, self-inflicted availability edge — not a security exposure.

**Rubric hook for MEDIUM** — "a refusal whose visible form distinguishes causes it should not." The report's
HIGH rests on the client-side consequence alone, but phase 04's HIGH band is a closed enumeration: an
irreversible write preceding a refusable guard (the password is **not** changed — that is the whole point), one
gate admitting an account state another refuses, a claim binding an unverified identity, and a revocation
marker failing to withdraw. None is present. The MEDIUM item describes it exactly: the refusal's visible form
(`401`, which this client reads as "session dead") misreports a wrong-password cause. Re-graded, not dismissed —
the mechanism is fully confirmed and the roadmap position (step 1) is unchanged.

**Recommendation** — Executable as filed; the symbols it depends on all resolve. `422 VALIDATION_ERROR` and
`403 PERMISSION_DENIED` both fall through to the `status !== 401 && status !== 429` arm at
`axiosInstance.ts:132`, verified. No shipped test blocks the change: `tests/test_auth_api.py:588`
(`test_password_change_mismatch_returns_422`) pins the **confirmation** mismatch, not the current-password one;
`tests/test_auth.py:546` is a Pydantic model test with no HTTP status; and no test anywhere asserts 401 for a
wrong current password. Note that plan 17's row `D9` asserts the opposite — that "the current-password-mismatch
behaviour is pinned by `test_password_change_mismatch_returns_422`" — which the test body at `:619-632`
refutes; the executor of this finding should not treat plan 17's `D9` as a remediation blocker.

---

### AUTH-103 — The access gate answers 404 for a credential whose user no longer exists, while the refresh gate answers 401 for the same condition

**Severity** — MEDIUM (sustained)

**Zone** — "A condition carried inside a credential against the condition read from the stored record"

**Observation** — CONFIRMED. `src/mkobi/api/deps.py:602-610` is byte-exact as filed: a well-formed, correctly
signed access token naming a deleted row raises `USER_NOT_FOUND`, and `src/mkobi/utils/exceptions.py:50` maps
`ErrorCode.USER_NOT_FOUND` to `HTTP_404_NOT_FOUND`. The contrasting arm at
`src/mkobi/api/routes/auth.py:487-494` is byte-exact and raises `AUTHENTICATION_FAILED` for the identical
condition. Every other refusal on the same gate is a 401 (`deps.py:563-567` invalid token, `:578-582` missing
`user_id`, `:596-600` revoked, `:614-618` deactivated), so the 404 is the outlier on its own route as well as
against its sibling.

**Evidence** — The reachability argument verifies and is the part that makes this live rather than
hypothetical. `src/mkobi/api/routes/users.py:281` is `@router.delete(` for `DELETE /api/v1/users/me` and
`users.py:333` is `@router.delete(` for `DELETE /api/v1/users/{user_id}`; both remove the row through
`UserService.delete_user` (`src/mkobi/services/user_service.py:312`, `:342` `user_repo.delete`), and a
`revoke` search of that module returns **zero** hits — the outstanding tokens are left untouched. The client's
handling is `axiosInstance.ts:132-144`, which for a 404 takes the generic-toast branch and calls neither
`removeToken()` nor the redirect. The `WWW-Authenticate: Bearer` challenge on a 404 is real
(`deps.py:609`) and no HTTP client treats it as an authentication failure.

**Correction — one citation is off by one line, harmlessly.** The quoted block begins with the comment
`# Resource errors`, which is `exceptions.py:47`; the three code lines the finding relies on are exactly
`:48-50`. The claim itself is exact.

**Consequence** — A deleted user's in-memory access token is never discarded: every subsequent request in that
tab answers 404, the SPA toasts "User not found", no refresh runs and no sign-out occurs. The declared
contract breaks in two directions — an authentication failure reported with a resource status, and the same
refusal reason carrying two statuses across two surfaces reading the same row. The security direction is safe:
access is refused either way, so this is correctness and client contract, not exposure. That is why MEDIUM and
not higher, and the report's own reasoning ("not an exposure") is the correct basis.

**Recommendation** — Executable as filed: `AUTHENTICATION_FAILED` already exists, is already imported in
`deps.py:61`'s symbol set and is already what `auth.py:490-494` raises. No shipped test blocks it —
`tests/test_auth.py:199-218` (`test_refresh_nonexistent_user`) asserts 401 **on the refresh route only**, so
adding the gate-side counterpart is a pure addition.

---

### AUTH-104 — After a successful password change the SPA signs the user out with the "session expired" notice that cluster 13 `P6` explicitly rejected

**Severity** — MEDIUM (sustained)

**Zone** — "Session continuity: what a captured long-lived credential is worth, and what a revocation marker must be able to express"

**Observation** — CONFIRMED on the mechanism, CORRECTED on the force-mode consequence.
`frontend/src/features/users/ui/ChangePasswordPage.tsx:25-35` is byte-exact as filed: on success it toasts
`'Password changed successfully'` and does `void navigate('/profile')` while still holding the pre-change
access token. The composed failure then runs exactly as filed. `src/mkobi/api/routes/auth.py:544-552` shows
`change_password` rotates **no** cookie, so the presented refresh cookie is the pre-change one; the marker
written at `auth.py:704` dates the credential's `iat`, so the next request is refused `TOKEN_REVOKED`
(`deps.py:596-600`), the interceptor attempts a silent refresh, `auth.py:499-517` refuses that cookie as
`TOKEN_REVOKED` and clears it, `axiosInstance.ts:76-79` short-circuits with `removeToken()`, and
`axiosInstance.ts:117-123` runs `toast.error(SESSION_EXPIRED_MESSAGE)` plus
`window.location.href = '/login'`.

**Evidence** — The adjudicated ruling is quoted correctly and independently located:
`.ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md:741` records `P6` — "The user sees the
**normal login screen with no explanation**" — with the rejected option being exactly "a generic 'session
expired' notice", and `.ai/plans/17-authentication-implementation-execution.md:184` gives the reason the
report paraphrases: "a 'session expired' message would misreport a deliberate, user-initiated action as a
session fault". The commit claim is **confirmed**: `git show --stat 4600e5d` lists 11 files —
`docs/01-auth/auth-api.md`, `docs/06-backend/architecture.md`, `src/mkobi/api/deps.py`,
`src/mkobi/api/routes/admin.py`, `src/mkobi/api/routes/auth.py`, `src/mkobi/core/permissions.py`,
`src/mkobi/core/security.py` and four test files — and **no** file under `frontend/`. The documented contract
is also correct and is not part of the defect: `docs/01-auth/auth-api.md:373` states the caller's own session
is revoked too, "so the SPA must log in again with the new password".

**Correction — the force-mode sub-claim is refuted.** The report asserts that under `?force=true` "the user
lands on `/login`, authenticates successfully, and `useAuth` … immediately redirects them back to the same
change-password screen". The cited code resolves and is quoted correctly
(`frontend/src/features/auth/model/useAuth.ts:69-73` redirects on `user?.force_password_change`), but the
premise does not hold **after a successful change**: the very commit that writes the password also clears the
flag — `src/mkobi/services/auth_service.py:518` sets `force_password_change=False` in the same update that
commits at `:520`, and `tests/test_auth_api.py:586` asserts it. A user who re-authenticates therefore lands on
the normal profile page. There is no redirect loop. The finding's core outcome — two toasts and a hard
redirect for a deliberate action — stands; the "worse under force mode" escalation does not, and it must not
be used to argue the severity.

**Ownership correction.** `P6`'s own ownership column reads "plan 17 (`AB-8`), plan 13"
(`ADJUDICATED-2026-10-03-product-owner-rulings.md:741`). The user-visible half of this ruling is therefore
**phase 13's** (client tier) as much as this phase's, and the report files it here without noting that. This
does not change the verdict — the ruling was recorded against a commit in this phase's plan — but it changes
who executes it.

**Consequence** — Every deliberate self-service password change ends with a success toast, then
"Session expired. Please login again.", then a full-page redirect to `/login`. The user performs an action
intentionally and is told their session faulted. The security direction is correct — the sessions really are
withdrawn — so the defect is the messaging half of `P6` that was never built. MEDIUM, not HIGH: nothing is
exposed and no control is weakened.

**Recommendation** — Executable as filed, and the named helper exists:
`logoutClient()` at `frontend/src/features/auth/api/authApi.ts:31-33` calls `removeToken()`, so no new
mechanism is required. Two corrections to carry into execution. (1) The rollout section's advice — keep the
`toast.success` and add the navigation — is right and must be kept: it is the only confirmation the user gets
that the change landed. (2) If `P6` is descoped rather than implemented, register the outcome as an accepted
residual **and** record that `P6` names plan 13 as co-owner, so the residual is not closed by this phase
alone.

---

### AUTH-105 — No production path can emit `TOKEN_EXPIRED`; the expired-token arm in the gate is unreachable

**Severity** — LOW (sustained)

**Zone** — "Single-use and lifetime guarantees, in both directions"

**Observation** — CONFIRMED, reproduced independently rather than accepted. `src/mkobi/core/security.py:403-405`
is byte-exact as filed — `except JWTError as e: logger.error(...); return None` — and it precedes any other
handler. `src/mkobi/api/deps.py:644-650` is byte-exact as filed. Since `ExpiredSignatureError` is a subclass of
`JWTError`, the gate's dedicated arm can never execute: `decode_token` returns `None`, and the gate takes
`payload is None` at `deps.py:561-567` and refuses with `INVALID_TOKEN`.

**Evidence** — Runtime, re-run here from scratch:
`issubclass(ExpiredSignatureError, JWTError)` = `True`; `decode_token(<access token minted with
expires_delta=-10 min>)` = `None`, with the log line `JWT token decode error: Signature has expired.` The
exception never leaves `decode_token`. The orphan surface verifies line for line:
`src/mkobi/models/enums.py:249`, `src/mkobi/utils/exceptions.py:40`, `src/mkobi/utils/exceptions.py:191`,
`frontend/src/shared/api/errorMessages.ts:20`, `frontend/src/features/auth/model/errorMessages.ts:10`. No
pytest file references the code or the exception. `tests/test_auth_service.py:283` does exercise `verify_token`
with an expired token and passes, consistent with the finding's reasoning that it passes *because*
`decode_token` swallows the expiry.

**Correction — the orphan surface is wider than the finding states.** `TOKEN_EXPIRED` is also the frontend
enum mirror at `frontend/src/shared/types/enums.ts:121`, and it is **pinned by three shipped frontend tests**:
`frontend/src/shared/types/__tests__/enums.test.ts:217`,
`frontend/src/shared/api/__tests__/errorMessages.test.ts:75`,
`frontend/src/features/auth/model/__tests__/errorMessages.test.ts:8` (plus a fixture use at
`__tests__/errorHandler.test.ts:36`). It is further documented as live behaviour in four places —
`docs/99-reference/error-handling-guide.md:107` and `:263`, `docs/08-security/error-format.md:54`, `:118` and
`:264`, and `docs/08-security/security-overview.md:528`. Option (a) of the recommendation ("retire it") is
therefore not a two-file backend edit: it touches the frontend enum, three test files and three documents. The
finding's "no remediation blocker" statement is true for `tests/` and false for the frontend suite.

**Consequence** — An expired access token is refused as `INVALID_TOKEN` rather than `TOKEN_EXPIRED`.
Behaviourally the request is still refused with 401 and the correct `WWW-Authenticate` header, so no control
is weakened; the cost is diagnostic — operators cannot distinguish a forgery from an ordinary expiry, and
the client copy written for expiry is unreachable. Two English guard comments describe the behaviour
accurately, so this is dead logic, not a contract violation. LOW is right.

**Recommendation** — Both directions remain legitimate, but option (a) now carries the frontend and
documentation surface listed above, and option (b) must land together with `tests/test_auth_service.py:283`
changing — that test passes precisely because of the defect. The trap the finding names is real and correctly
flagged.

---

### AUTH-106 — Six `AuthService` methods have no production caller, one of them a credential-minting path

**Severity** — LOW (sustained)

**Zone** — "The two credentials that constitute one session: issuance paths, what each is accepted for, and what distinguishes them"

**Observation** — CORRECTED. The central claim survives intact and was re-derived independently: a
repository-wide search for `auth_service.` across `src/` returns **exactly seven** call sites —
`src/mkobi/api/routes/auth.py:218` (`login_user`), `:343` (`register_user`), `:369` (`create_access_token`),
`:672` (`change_password`), `:779` (`register_request`), and `src/mkobi/api/routes/admin.py:282`
(`reset_password_admin`), `:425` (`approve_registration_request`). None of them is one of the six methods the
finding names, and all six are unreachable from production. Every definition anchor in the table resolves and
is byte-exact: `src/mkobi/services/auth_service.py:232-248`, `:262-287`, `:289-304`, `:306-323`, `:325-344`,
`:346-365`; the reachable `create_user` delegate at `:367-385` is correctly excluded.

**Evidence — four cells of the table are wrong, and the executor must not inherit them.** The table was
written against `src/mkobi/interfaces/service_interfaces.py`, which is **modified in the working tree** and
was re-read before this report; the interface half survives, the "only exercised by" half does not.

| Method | Definition | Interface declaration | Only exercised by |
|---|---|---|---|
| `refresh_token` | `auth_service.py:262-287` | `service_interfaces.py:52-57` | `tests/test_auth_service.py:289` and `:304` (definitions); the **calls are at `:295` and `:310`** — the cited `:301` is not a call site |
| `verify_token` | `auth_service.py:289-304` | `service_interfaces.py:74-77` | `tests/test_auth_service.py:249`, `:293`, `:308` — correct |
| `validate_refresh_token` | `auth_service.py:306-323` | `service_interfaces.py:79-82` | none found — correct |
| `authenticate_user` | `auth_service.py:232-248` | `service_interfaces.py:38-43` | `tests/test_auth_service.py:187-219` — correct |
| `get_user_by_id` | `auth_service.py:325-344` | **`:91-96`, not "—"** | **`test_auth_service.py:320`, `:330`, `:336`, `:340` — not "none found"** |
| `get_user_by_email` | `auth_service.py:346-365` | **`:98-103`, not "—"** | **`test_auth_service.py:346`, `:356`, `:362`, `:366` — not "none found"** |

Corrections, stated plainly: the `—` in the interface column for `get_user_by_id` and `get_user_by_email` is
false — both are `@abc.abstractmethod` members of `IAuthService`
(`service_interfaces.py:91-96` and `:98-103`), so **all six** are declared interface members, not two orphans
and four interface members. The `none found` entries in the last column are false for the same two methods:
four test call sites exist for each. The observation's own framing — that the methods are "declared
`@abc.abstractmethod` on `IAuthService` … rather than an orphan" — is true of all six and should be stated as
such rather than as a property of `refresh_token` alone.

**Consequence** — Unchanged by the corrections, and correctly characterised as maintenance rather than
security. `IAuthService` promises a token-refresh capability the live route bypasses
(`auth.py:544` calls `core.security.create_refresh_token` directly), so a reader trusting the interface looks
in the wrong place; `auth.py:450` imports the `core.security` function while `AuthService.validate_refresh_token`
wraps the same name, and only one of the two appears in the route. The finding is right that
`refresh_token` mints through a path no gate change has been validated against — it emits
`user_id`/`email`/`role`, which the gate does accept, so it is not a latent acceptance bug, but nothing keeps
it that way.

**Recommendation** — Executable, with the correction that the decision covers **six interface members and
eight test call sites**, not "six methods and their tests" in the abstract. Either branch is viable; what must
not ship is the current state. `[DOC-UPDATE]` if the surface stays.

---

### AUTH-107 — `register_request` takes its rate-limit Redis client from a module call, not the DI dependency the other two auth sites use

**Severity** — LOW (sustained)

**Zone** — "The identity an abuse bound is keyed on, and whether the caller can choose it"

**Observation** — CONFIRMED on the observation and evidence; CORRECTED on the recommendation's premise.
`src/mkobi/api/routes/auth.py:758-761` is byte-exact as filed, `src/mkobi/api/routes/auth.py:200-204` is
byte-exact as filed, and the import the argument turns on is exact: `auth.py:38` is
`from mkobi.core import redis_client`, so in `register_request` the bare name resolves to that module and the
call is an attribute lookup at call time. The seam being bypassed, `get_redis_client_dependency` at
`src/mkobi/api/deps.py:147-153`, is real and is exported at `deps.py:113`. The production-harmlessness
argument is right: `get_async_redis_client` is process-wide, so both spellings return the same client today.

**Evidence — the coverage claim is correct, and the report is right not to file it as a coverage gap.**
`tests/test_rate_limiting.py:74` (`test_register_request_rate_limit_exceeded`) asserts the 429 at `:106` and
the `Retry-After` header at `:111` — note the cited range `74-108` stops one line short of the header
assertion, a harmless imprecision. The reason it works for a module-level call is verified at
`tests/conftest.py:513-521`: the fixture imports `mkobi.core.redis_client as redis_client_module` and
monkeypatches the module attribute, which an attribute-at-call-time lookup does see.

**Correction — the recommendation's justification is false, and its fix is unaffected.** The report closes with
"`tests/conftest.py` keeps working because it patches the module the dependency itself calls". It does not:
`src/mkobi/api/deps.py:51` is `from mkobi.core.redis_client import get_async_redis_client` — a from-import that
binds the name in `deps`' namespace — so `conftest`'s module-attribute patch **never reaches**
`get_redis_client_dependency`. The DI path is covered by a different mechanism the report does not mention:
`tests/conftest.py:734` imports the dependency and `:752` sets
`app.dependency_overrides[get_redis_client_dependency] = override_get_redis`, returning
`app.state.mock_redis` (`:749-760`) — the same object `tests/test_revocation_store_outage.py:28-46` documents
when injecting its faults. The proposed change remains correct and is in fact covered by that existing
override, so nothing about the fix moves; only the stated reason does.

**Consequence** — Contained today, exactly as the finding says. A future per-request client, a read-replica
split or a health-gated client would apply to the login and refresh limiters and silently not to the
registration-request limiter, and nothing in the suite would catch the omission — because the register-request
tests reach the module path while the sibling tests reach the override, and no test asserts that all three
sites obtain their client the same way. The helper docstring at `auth.py:93-96` excludes
`client_errors.py` and `upload.py` by name; `register_request` is inside its declared scope and diverges
inside that scope. LOW.

**Recommendation** — Executable as filed: add `redis_client: Any = Depends(get_redis_client_dependency)` to
`register_request` and pass it to `AsyncRateLimiter`. Drop the false parenthetical and replace it with the
override path, which is the mechanism that will actually cover the new parameter.

---

### AUTH-108 — The declared production-default credentials are documented as `admin`/`admin`; the shipped defaults are `admin`/`CHANGE_ME_ADMIN_PASSWORD`

**Severity** — LOW (sustained)

**Zone** — "The identity namespace the handshake writes into, and the privileged entries already in it"

**Observation** — CONFIRMED, every anchor exact. `docs/01-auth/auth-api.md:566` reads verbatim
`- **Production credentials:** Default credentials (`admin`/`admin`) are rejected in production`, against
`src/mkobi/config.py:728-729` where `admin_username` defaults to `"admin"` and `admin_password` to
`"CHANGE_ME_ADMIN_PASSWORD"`. Neither half of the documented pair is a shipped default: `admin` is not a
password this code can produce, and `CHANGE_ME_ADMIN_PASSWORD` is not `admin`.

**Evidence** — The rejection machinery the sentence refers to is real and correctly scoped, and the report's
description of it is exact: `src/mkobi/config.py:775-784` rejects the username via `is_weak_admin_username`
(production-only, inside the `if self.environment == EnvironmentEnum.PRODUCTION` block opening at `:770`),
`config.py:786-803` rejects the password via `is_weak_admin_password`, `config.py:52` is
`WEAK_USERNAMES = {"admin", "administrator", "root", "test", "user", "admin@example.com"}` byte-exact, and
`config.py:53-65` is `WEAK_PASSWORDS`. The claim that the shipped placeholder is rejected **twice over**
verifies: `"change_me_admin_password"` is a member of `WEAK_PASSWORDS` (`config.py:60`) and the default also
matches `PLACEHOLDER_CREDENTIAL_PREFIX = "change_me"` at `config.py:72`. The finding's scoping note is also
verified — a `docs/01-auth/` search for that sentence returns exactly one hit, `:566`.

**Consequence** — Maintenance and audit trail only, and correctly bounded by the report itself: the control
the sentence claims exists does exist, so this is a mis-transcription, not an unbacked promise. A reader
believing the guard list is smaller than it is, or an operator testing `admin`/`admin`, finding it already
refused and concluding the check is untested.

**Recommendation** — Executable as filed. Pointing at `is_weak_admin_username` / `is_weak_admin_password`
rather than quoting a literal pair is the better end state, because it names the single source of truth.
One-line edit, one file.

---

### AUTH-109 — `require_role_dependency` is annotated as returning a session, a user, or None

**Severity** — LOW as a defect · **REJECTED as filed** (duplicate + seam violation)

**Zone** — "The two credentials that constitute one session: issuance paths, what each is accepted for, and what distinguishes them"

**Observation** — The facts are all true; the filing is not. Every anchor resolves byte-exact:
`src/mkobi/api/deps.py:751-753` carries `def require_role_dependency(required_role: UserRole) -> (AsyncSession |
UserRead) | None:` while the function returns the closure `role_checker` (`:775-791`, `return role_checker` at
`:791`). The caller census is correct — a repository-wide search returns only `deps.py:78` (the `__all__`
entry, byte-exact), `deps.py:751` (the definition) and `deps.py:770` (the docstring example,
`user: UserRead = Depends(require_role_dependency(UserRole.ADMIN)),` — byte-exact). No caller in `src/`,
`tests/` or `frontend/src/`. The supporting citations are exact too: `deps.py:123`
(`get_db_dependency() -> AsyncSession`), the three live guards at `deps.py:679`, `:706`, `:733` annotating
`-> UserRead`, and the four aliases at `deps.py:976-979`.

**Why it is rejected as filed — two independent reasons.**

**(1) The dead-surface half is a duplicate of an already-validated finding in another phase.** Phase 01 filed
it as `TOPO-104` — "Entry-layer dependency providers that no route reaches" —
(`.ai/audit/01-process-architecture/findings.md:249`), whose evidence table at `:263` names
`require_role_dependency`, `deps.py:751-791`, the `deps.py:78` re-export and "none (only its own docstring
example at `:770`)" — the identical symbol, identical caller census, identical anchors. That finding was
adjudicated in the prior validation pass and **sustained at LOW** (downgraded from MEDIUM):
`.ai/audit/99-validation/01-process-architecture-validated-findings.md:216-248`, verdict CORRECTED, row `:233`
carrying the same census. Re-filing it under a second phase is a duplicate against an existing validation, not
a new observation.

**(2) The new half is filed outside this phase's declared scope.** What phase 04 adds is the wrong return
annotation on a **role-dependency factory**. Its scope paragraph disclaims exactly that surface: "Not owned
here: … the role hierarchy and per-object access decision, and which surfaces a request-forgery check reaches
(12)", and it states the negotiated boundary — "this phase owns identity resolution, binding and the
session-layer consequences; 12 owns the per-request gate". The phase file also lists, among the things it does
**not** own, "the role hierarchy and per-object access decision". A type annotation on a role gate is phase 12's
concern; a reachability census over `deps.__all__` is phase 01's, and already filed there.

**Disposition** — The annotation half is a real LOW defect and is **re-typed to phase 12**, not discarded: it
is recorded as `VAL-04-004` for the coordinator to route. The dead-surface half is **merged** into
`TOPO-104`; nothing is lost from the roadmap, because `TOPO-104` already carries it at LOW and is already
written into the phase-01 remediation path.

**Consequence** — Unchanged from the finding and correctly stated there: no runtime effect, since `Depends()`
erases the annotation and none of the three live guards uses the factory. Two real costs: a maintainer reading
the authentication module is told a dependency factory returns a database session or a user object, and the
annotation survives every refactor because no type check can see it; and `__all__` advertises a role gate that
nothing uses, so a reader adding a role-protected route may reach for an unreviewed path instead of the three
guards actually in use.

**Recommendation** — Split before executing. The annotation fix is trivial and belongs to phase 12: annotate
the callable actually returned, or drop the annotation and state the return in the docstring, consistent with
`deps.py:679`, `:706` and `:733`. Whether the factory should exist at all belongs to `TOPO-104`'s intent
decision in phase 01, where the same question is already open for three of the four symbols it names — and
that decision carries a shipped-test blocker phase 01's validation recorded
(`tests/test_deps.py:599-601` asserts four `deps.__all__` entries), which AUTH-109 does not mention.

---

## Validation-Level Findings (VAL-)

Defects **in the audit report**, graded by the 99-validation taxonomy (effect and blast radius on the report
itself), never on the audited system's scale. They are not interleaved with the findings above because the
two would share a `Severity` column carrying two different scales. Where a VAL item also describes a real
system defect, the system's own band under `.kilo/commands/audit/phases/04-audit-authentication.md` is stated
separately and explicitly.

### VAL-04-001 — The refuted bcrypt hypothesis was refuted on a measurement that cannot be true: the placeholder performs no bcrypt work, and `POST /auth/login` is a ~2,600x user-enumeration oracle

**Severity** — CRITICAL (a wrong approval: an absence recorded as established)

**Underlying system severity, had phase 04 filed it** — MEDIUM (phase 04 rubric, "a refusal whose visible form
distinguishes causes it should not")

**Observation** — Appendix C's block-3 row records a timing defence as **established and clean**:
"Verification cost is uniform between a matching and a non-matching identity … measured at **268.9 ms** median
against **283.6 ms** for a real cost-12 verification on this host, a 1.1x ratio, so the timing defence the
comment claims does hold." That conclusion is false, and the measurement it rests on is not reproducible. The
placeholder literal at `src/mkobi/services/auth_service.py:200-203` is
`"$2b$12$dummy.hash.to.prevent.timing.side.channel.attack.dummy.hash"` (byte-exact, 54 characters, and the
**only** occurrence of that literal in the repository). It is not a functioning cost-12 hash: it is not a valid
bcrypt salt.

**Evidence** — Reproduced here from scratch, not accepted and not re-derived from the report. Against
`src/mkobi/core/security.py` on this tree, with `SALT_ROUNDS = 12` (`security.py:222`, and the constant cited
by the report at `security.py:37`):

- `bcrypt.checkpw(b'anything', <placeholder>.encode('latin-1'))` **raises `ValueError: Invalid salt`**.
- `verify_password` catches it at `security.py:258-260` (`except (ValueError, TypeError)` → `logger.error` →
  `return False`) and returns.
- Median wall time, 10 samples each: **placeholder path 0.1 ms**; real cost-12 hash with a wrong password
  **266.1 ms**; real cost-12 hash with the right password **272.6 ms**.

A 268.9 ms median is therefore impossible for this code path — the placeholder performs no key derivation at
all. `AuthService.login_user` reaches that path at `auth_service.py:196-204`, guarded by a comment that states
the intent explicitly: "Perform dummy bcrypt call to prevent timing side-channel attack. Without this, an
attacker can distinguish 'user not found' (fast) from 'wrong password' (slow bcrypt verify) by measuring
response time." The code does not do what its own comment says, and the audit recorded the opposite as settled.

**Consequence — on the report.** This is the taxonomy's CRITICAL case and not a lesser one: an absence
recorded as established. The audit not only declined to file a finding, it published a measurement that
reassures the reader the control is effective, in the same appendix that declares its limits. Nothing in the
roadmap schedules the work, because no work was ever filed; a reader who trusts the appendix would not look
for it. Phase 04's own block 3 named this exact property and instructed the auditor to "demonstrate the
uniformity rather than assuming it, since a deliberately equal-cost step is exactly the kind of thing whose
implementation quietly stops being one" — the property was named, the instruction was explicit, and the
conclusion was the opposite of the truth. Every other Appendix C row that this pass re-derived independently
(algorithm pinning on both decode paths, credential separation, the 72-byte truncation discipline, the
single-use `GETDEL` atomicity, the bootstrap conflict clause) reproduced correctly, which makes this row an
isolated failure rather than a systemic one — and therefore more likely to be trusted.

**Consequence — on the system.** `POST /auth/login` (`/login` and `/login/form`) answers a non-existent email
in ~0.1 ms and an existing email with a wrong password in ~266 ms, a ~2,600x difference on an endpoint an
unauthenticated caller may reach. The rate limit bounds sampling to 5 attempts per 300 s per identifier and 50
per 300 s per peer (`auth.py:205-214`), which slows enumeration but does not remove it: a single sample
distinguishes the two cases. No credential is exposed, no session is established for the wrong identity and no
control is weakened — the body and status are deliberately uniform (`auth.py:220-226`), so this is MEDIUM under
phase 04's rubric, not CRITICAL.

**Recommendation** — Replace the placeholder with a syntactically valid, non-matching cost-12 hash so
`checkpw` performs the same derivation, and re-measure both paths. Note for the executor that the literal
appears exactly once, so the change is one line plus one measurement; no caller, interface or test asserts the
current value (`tests/` has no reference to it). Correct Appendix C's block-3 row in the same change — it is
currently a false assurance, and a corrected one is worth as much as the fix. If the team prefers to keep the
malformed literal deliberately, the comment at `auth_service.py:196-199` must be replaced with one that says
what the code actually does, and the enumeration oracle must be accepted and documented as a residual.

### VAL-04-002 — Appendix C's refresh-payload measurement omits a claim the payload actually carries

**Severity** — LOW (drift with no remediation consequence today)

**Observation** — The block-2 row states: "Measured: access payload `['email','exp','iat','jti','role','user_id']`,
refresh payload `['email','exp','iat','jti','sub']`." Measured on this tree, the access payload is exactly
that, and the refresh payload is `['email','exp','iat','jti','role','sub']` — it carries `role`. Both minting
paths include it: `auth.py:544-546` (`create_refresh_token(data={"sub": ..., "email": ..., "role": user.role})`)
and `auth.py:232-234` on login.

**Consequence** — The row's conclusion is unaffected and correct: the two credentials are still separated by
claim name (`user_id` vs `sub`), each gate reads the name the other lacks, and the separation resting on a claim
name rather than an explicit `typ` claim remains an observation rather than a defect. The cost is that a
reader reasoning from the measurement concludes refresh tokens carry no role claim, when they do — and role
claims in a credential are precisely the kind of thing a reader needs to be accurate about. It also means the
report's own inventory is inconsistent with `docs/01-auth/auth-api.md:560`, which says the payload contains
`user_id`, `email`, `role`.

**Recommendation** — Correct the measurement in place. No code change.

### VAL-04-003 — A missed dead guard in the authentication dependency, and the Appendix C claim it falsifies

**Severity** — LOW (drift, plus a real LOW system defect the audit did not file)

**Observation** — Appendix C records: "No auth path raises `HTTPException` directly, and every refusal goes
through `AppException` with an `ErrorCode`." The first half is false. `src/mkobi/api/deps.py:120` declares
`security = HTTPBearer()`, and `get_token_from_header` receives it as
`Depends(security)` at `deps.py:473-475`. FastAPI's `HTTPBearer.__call__` raises before the function body ever
runs — both when the `Authorization` header is absent or empty and when its scheme is not `bearer`. Verified on
this tree: `HTTPBearer().make_not_authenticated_error()` returns
`HTTPException(status_code=401, detail="Not authenticated")`. That is a `StarletteHTTPException`, converted to
RFC 7807 by `add_exception_handlers`' handler at `utils/exceptions.py:313-342` (401 → `AUTHENTICATION_FAILED`
at `:325`) rather than raised as an `AppException`.

The consequence for the audit's own claim is nil in observable behaviour — the client still receives a
conformant 401 problem document — but it exposes a **missed finding**: `src/mkobi/api/deps.py:487-493`, the
`if credentials.scheme.lower() != "bearer": … raise AppException(AUTHENTICATION_FAILED, "Invalid
authentication scheme")` arm, **can never execute**. `HTTPBearer` has already rejected every non-`bearer`
scheme upstream, so `credentials.scheme` reaching the body is always `bearer`. Phase 04's block 4 names this
class explicitly — "a guard defined but never reached" is a finding — and no guard in the tree is more
on-topic for this phase than one in the authentication dependency itself.

**Consequence** — On the system: a dead guard in the auth module, with a log line
(`"Invalid authentication scheme: %s"`) and a diagnostic detail string that no caller can ever produce. An
operator grepping that string to explain a rejected scheme will find nothing, because the request never reaches
it. Under phase 04's rubric this is LOW ("unhelpful diagnostic text on a refusal path", dead logic). On the
report: a claim of uniform mechanism that is not uniform, published as an established absence. LOW — unlike
VAL-04-001, no reader would act on this and no remediation depends on it.

**Recommendation** — Either delete `deps.py:487-493` and let the `HTTPBearer` refusal stand as the single
mechanism, or set `HTTPBearer(auto_error=False)` so the handler's own scheme check becomes the live one and the
`AppException` carries its `WWW-Authenticate` header (the `HTTPBearer` path does not add one). Whichever is
chosen, correct the Appendix C row: the accurate statement is that every refusal is returned as RFC 7807 with
an `ErrorCode`, and that most but not all of them are raised as `AppException`.

### VAL-04-004 — Re-typed: the wrong-annotation half of AUTH-109 belongs to phase 12

**Severity** — LOW (defect in the audit: a finding filed under a phase that does not own it)

**Observation** — Recorded here so the re-typed disposition is not lost with the rejection above. The real,
new, un-duplicated half of AUTH-109 is that `src/mkobi/api/deps.py:751-753` annotates
`require_role_dependency` as returning `(AsyncSession | UserRead) | None` when it returns a
`Callable[[UserRead], Awaitable[UserRead]]`. Every anchor verifies (see AUTH-109). This phase does not own it —
its scope paragraph disclaims "the role hierarchy and per-object access decision" to phase 12 — so it is routed
to phase 12 rather than carried here.

**Consequence** — On the report: a reader repairing the phase-04 set must not spend phase 12's budget on it, and
phase 12 must not assume the item was already triaged. The duplicate half is already covered by the validated
`TOPO-104`, so no roadmap entry is lost.

**Recommendation** — Phase 12 to accept the annotation fix, or to fold it into `TOPO-104`'s existing intent
decision in phase 01 if that factory is retired. Either way the decision is made once, in one phase.

---

## Distribution

Eight findings survive, on the same three-component split the input report describes, and the single component
that carries the most is unchanged: `api/routes/auth.py::change_password` together with
`api/deps.py::get_current_user_dependency`.

- **Backend credential issuance and gates** (`api/routes/auth.py`, `api/deps.py`, `api/routes/admin.py`) —
  AUTH-101, AUTH-102, AUTH-103, AUTH-105. Three of the four converge on one route handler; the fourth is that
  route's gate.
- **Backend service and dependency surface** (`services/auth_service.py`, `api/routes/auth.py`,
  `interfaces/service_interfaces.py`, `api/deps.py`) — AUTH-106, AUTH-107. AUTH-109's dead-surface half leaves
  this phase entirely (merged into `TOPO-104`); only its annotation half remains, re-typed to phase 12.
- **Composed client** (`features/users/ui/ChangePasswordPage.tsx`, `shared/api/axiosInstance.ts`,
  `features/auth/model/useAuth.ts`) — AUTH-104, and the client half of AUTH-101. Neither is fixable on the
  backend alone.
- **Declared contract** (`docs/01-auth/auth-api.md`, `src/mkobi/config.py`) — AUTH-108, plus the `401` row that
  travels inside AUTH-101.
- **Login endpoint timing** — `VAL-04-001` only; no input finding lands there, which is the point.

Two bands move in opposite directions from the input's own framing, and both are recorded rather than applied
silently: one HIGH is re-graded down to MEDIUM (AUTH-101, on band only), and one defect the input declined to
file is graded MEDIUM on the system and CRITICAL on the report (`VAL-04-001`).

## Cross-Finding Analysis

The input report's two-cause structure survives validation, with one correction and one addition.

**Cause 1 — the authentication error contract is decided per-route against a 401 interceptor whose scope
nobody wrote down.** AUTH-101, AUTH-103 and AUTH-104 are one defect seen from three ends, and the report's
reasoning is right: `D-04-B` fixed one instance (`force_password_change` → 403, `deps.py:627-638`, with the
reasoning written into `docs/01-auth/auth-api.md:76`) and did not sweep for others. AUTH-101 is the 401 where a
403 or 422 belongs, AUTH-103 is the 404 where a 401 belongs, AUTH-104 is the correct 401 whose *client* treats
it as a fault. The correction: AUTH-104's force-mode escalation is refuted (see its entry), so the three are not
symmetrical in severity, and grouping them in one roadmap step is still correct only because they touch the same
two files — not because they are equally severe.

**Cause 2 — the post-commit revocation seam has three implementations and one was written twice.** AUTH-102
stands, and its supporting asymmetry is stronger than the report states: the two admin sites guard the write
*and* carry a comment naming the failure mode ("Falling through to the blanket handler would claim the whole
operation failed while the password is already reset", `admin.py:305-308`), while `auth.py:697-702` cites that
sibling pattern in its own comment and then does not follow it. A copy divergence, exactly as filed.

**Cause 3 (added by this pass) — a control that was measured rather than executed.** `VAL-04-001` has no cause
in common with the input findings, and it is the only item in this phase that is a *silent* defect: the code
carries a comment asserting a control, the audit carried a measurement asserting the control holds, and neither
was true. It shares only a shape with the others — a stated guarantee that is not implemented — which is
precisely the class phase 04 exists to find, and the class its block 3 named explicitly.

Everything else is independent, as the report says: AUTH-105 (an unreachable exception arm), AUTH-106
(unreachable service methods), AUTH-107 (a DI seam bypass), AUTH-108 (a mis-transcribed default).

## Roadmap

The input's four-step order survives and needs no resequencing; the one change is that AUTH-101 now carries a
MEDIUM band, so step 1 is no longer justified by severity alone — it is justified by **file collision**, which
is the report's actual stated reason and is correct.

1. **Step 1 — close the error-contract cause together (AUTH-101, AUTH-103, AUTH-104).** Unchanged from the
   input. Nothing else may start first: all three change status codes or client handling across the same two
   files, and a partial application leaves the gate and the client disagreeing in a new way. Carry two
   corrections into execution: AUTH-104's force-mode loop must not be used to argue priority, and the
   remediation blocker named by plan 17's `D9` is not real (`test_password_change_mismatch_returns_422` pins the
   confirmation mismatch — `tests/test_auth_api.py:619-632` — not the current-password one).
   **Additionally: fix `VAL-04-001` in this step or file it as an accepted residual.** It is the only defect in
   this phase with no remediation scheduled anywhere, and it sits on the same endpoint as step 1's other work.
   Must be true before step 2: no route in `api/routes/auth.py` answers 401 for a refusal whose cause is not an
   unacceptable credential, and `grep -n "AUTHENTICATION_FAILED" src/mkobi/api/routes/auth.py` shows only the
   rows that mean it.
2. **Step 2 — close the revocation-seam cause (AUTH-102).** Independent of step 1 and parallelisable; it touches
   `auth.py:704-709` only. Unchanged, and the report's preferred 503 shape is the right call — `deps.py:658-666`
   already establishes the mapping. Extend `tests/test_revocation_store_outage.py` with the faulting-**write**
   case using the existing `_fault_store` helper (`:28`) before the change lands, not after.
3. **Step 3 — settle the dead and divergent surface (AUTH-106, AUTH-107).** Unchanged, with the correction from
   AUTH-106's entry: the decision covers **six** `IAuthService` members and eight live test call sites, not six
   methods. AUTH-107's fix is unaffected by its recommendation correction, and AUTH-109 **leaves this step** —
   it is merged into `TOPO-104` (phase 01) and its annotation half is re-typed to phase 12 (`VAL-04-004`).
4. **Step 4 — the low-severity documentation and dead-code items (AUTH-105, AUTH-108).** Unchanged, with one
   scope correction: retiring `TOKEN_EXPIRED` (option (a)) also touches
   `frontend/src/shared/types/enums.ts:121`, three frontend test files and three documents. The port is that a
   "no blocker" claim holds for `tests/` and not for the frontend suite.

## Rollout Safety

The input's rollout analysis survives, and its sharpest warning survives with it: steps 1 and 2 change
observable behaviour in both directions and neither is observable from a backend-only test.

**Step 1** is a wire change on `POST /auth/change-password` — 401 becomes 422 or 403 for the wrong-current-password
cause. Any client keying on 401 to detect a session problem stops signing users out on that route, which is the
intent, but the change is visible in access logs and in any external assertion. `deps.py:606-610` moving 404 →
401 is narrower: the SPA now clears the token and redirects instead of toasting, and a client that distinguished
"row is gone" from "token is bad" by status loses that distinction — which is the point. Keep the
`toast.success` on `ChangePasswordPage` and add the navigation rather than replacing it, or the user loses the
only confirmation that the change landed. Re-run the login → force-change → change-password flow end to end
with the real client: AUTH-101 and AUTH-104 exist only through the composed interceptor.

**Step 2** turns a 500 into a 503 on one route under a Redis fault. Verify that
`POST /api/v1/auth/change-password` still answers 200 with the marker written on a healthy store, and extend
`tests/test_revocation_store_outage.py` **before** the change lands.

**`VAL-04-001`'s fix** is behaviour-preserving from the client's perspective — the status, body and rate limit
are unchanged — but it raises the CPU cost of every login attempt against a non-existent account from ~0.1 ms
to ~266 ms. On a workload that enumerates addresses, that is a deliberate cost transfer: the endpoint becomes
roughly as expensive per failed attempt as a real verification, which is the point, and the 5-per-300 s
identifier bound is what keeps it bounded. Measure before and after.

Every step remains a plain revert: no schema change, no migration, no data-shape change, and the marker
semantics in `core/security.py` are untouched by all four. The one non-revertible thing is operational habit,
as the report says — once AUTH-102 lands, operators may start trusting the post-commit revocation, so the
`C04-5` and `D-04-E` residuals in Appendix B should be re-read as live risk before that trust is extended.

---

## Appendices

### Appendix A — Disposition ledger and final severity counts

| ID | Verdict | Band as filed | Final band | Anchor drift | Independent runtime check |
|---|---|---|---|---|---|
| AUTH-101 | CORRECTED (re-graded) | HIGH | **MEDIUM** | none | interceptor traced; loop derived, not driven |
| AUTH-102 | CONFIRMED | HIGH | **HIGH** | none | **yes** — write fault propagates |
| AUTH-103 | CONFIRMED | MEDIUM | **MEDIUM** | one line (comment) | — |
| AUTH-104 | CORRECTED | MEDIUM | **MEDIUM** | none | — (force-mode claim refuted) |
| AUTH-105 | CONFIRMED | LOW | **LOW** | none | **yes** — expired token → `None` |
| AUTH-106 | CORRECTED | LOW | **LOW** | none | — (4 table cells wrong) |
| AUTH-107 | CORRECTED | LOW | **LOW** | none | — (recommendation premise false) |
| AUTH-108 | CONFIRMED | LOW | **LOW** | none | — |
| AUTH-109 | **REJECTED** as filed | LOW | not carried | none | — (duplicate + seam) |

**Counts by verdict** — CONFIRMED 4 (AUTH-102, AUTH-103, AUTH-105, AUTH-108) · CORRECTED 4 (AUTH-101,
AUTH-104, AUTH-106, AUTH-107) · REJECTED 1 (AUTH-109). Total 9, matching the input's `findings: 9`.

**Final severity counts, surviving system findings** — CRITICAL 0 · **HIGH 1** (AUTH-102) · **MEDIUM 3**
(AUTH-101, AUTH-103, AUTH-104) · **LOW 4** (AUTH-105, AUTH-106, AUTH-107, AUTH-108). One finding is not
carried and is excluded from the bands.

**Validation-level findings, on the report's own scale** — CRITICAL 1 (VAL-04-001) · HIGH 0 · MEDIUM 0 ·
LOW 3 (VAL-04-002, VAL-04-003, VAL-04-004). The system defect VAL-04-001 describes would be MEDIUM under
phase 04's rubric if phase 04 had filed it.

### Appendix B — Citation re-verification

Every citation in this report was opened at its quoted lines immediately before composition, and each cited
file's last-write timestamp precedes that read — no anchor moved under this pass. That is the opposite of
phase 01's result (9 of 14 stale) and phase 02's (systematic compose drift), and it is recorded as a measured
outcome, not as an assumption. Files re-read at their cited ranges in this session:
`src/mkobi/api/routes/auth.py`, `src/mkobi/api/routes/admin.py`, `src/mkobi/api/routes/users.py`,
`src/mkobi/api/deps.py`, `src/mkobi/core/security.py`, `src/mkobi/services/auth_service.py`,
`src/mkobi/services/user_service.py`, `src/mkobi/interfaces/service_interfaces.py`, `src/mkobi/config.py`,
`src/mkobi/utils/exceptions.py`, `src/mkobi/models/enums.py`, `src/mkobi/db/starter.py`,
`src/mkobi/core/temp_password_store.py`, `src/mkobi/api/routes/processing_logs.py`,
`frontend/src/shared/api/axiosInstance.ts`, `frontend/src/shared/api/refreshHandler.ts`,
`frontend/src/shared/api/errorSurfaces.ts`, `frontend/src/features/auth/api/authApi.ts`,
`frontend/src/features/auth/model/useAuth.ts`, `frontend/src/features/users/ui/ChangePasswordPage.tsx`,
`frontend/src/features/users/api/userApi.ts`, `docs/01-auth/auth-api.md`,
`docker/nginx/nginx.conf.template`, `docker/docker-compose.yml`, `docker/docker-compose.override.yml`,
`tests/conftest.py`, `tests/test_auth.py`, `tests/test_auth_api.py`, `tests/test_rate_limiting.py`,
`tests/test_revocation_store_outage.py`, `tests/test_auth_service.py`.

Three citation defects were found in total, all immaterial to the verdicts: `exceptions.py:47-48` (a comment
line the AUTH-103 quote includes but its range omits), `test_rate_limiting.py:111` (the `Retry-After`
assertion one line past AUTH-107's cited range), and `auth_service.py:295`/`:310` (AUTH-106's cited `:301` is
not a call site). One loose-but-resolving range: AUTH-101/104 cite `ChangePasswordPage.tsx:104-108` for a
`disabled` expression at `:105`.

**Concurrent-modification note — recorded because it landed mid-pass.** Commit `eba2348`
("fix(charts): serve the stored metric and dimension keys with the aggregate rows") was created after this
validation began and it **did** touch `src/mkobi/interfaces/service_interfaces.py`, which is the file AUTH-106's
evidence table is written against. The six interface anchors were therefore re-opened **after** the commit and
are unchanged: `authenticate_user` `:38-43`, `refresh_token` `:52-57`, `verify_token` `:74-77`,
`validate_refresh_token` `:79-82`, `get_user_by_id` `:91-96`, `get_user_by_email` `:98-103` — the commit's
9-line change to that module is in a different interface. Every other file cited in this report was confirmed
byte-identical to `HEAD` at the close of the pass (`git diff --name-only HEAD` over the cited set returns
nothing). The base context flags `frontend/src/shared/types/api.types.ts` as moving during the audit; it is
modified in the working tree but is cited by **none** of the nine findings and by none of this report's
evidence, so the flagged risk did not materialise.

### Appendix C — Disclosures checked rather than accepted

**Finding-ID namespace.** The `AUTH-` prefix is declared by
`.kilo/commands/audit/phases/04-audit-authentication.md:129`. The collision disclosure is accurate:
`AUTH-001 … AUTH-008` are occupied by the prior audit of this phase, and
`.ai/plans/17-authentication-implementation-execution.md:9` records
`findings_discharged: 8 AUTH-*, 10 VAL-04-*`. `AUTH-1xx` is the correct free range and no `AUTH-1xx`
identifier existed before this pass. **Accepted as correctly disclosed.**

**Appendix A of the input (eight prior findings discharged).** Spot-checked, and every claim holds on the
current tree: `TempPasswordStore.store` returns `bool` and fails open
(`core/temp_password_store.py:91-123`, `return False` at `:123`); commit-then-store with `credential_stored`
propagated (`services/auth_service.py:596-623`); `force_password_change` enforced at `deps.py:627-638` with the
four-entry allow-list at `deps.py:503-510`; `is_active` authoritative on both issuance paths
(`auth_service.py:209-217`, `auth.py:525-531`); the bootstrap's three distinct log outcomes at
`db/starter.py:545-571` with `created` read from `rowcount` at `:531`; and all three revocation readers raising
`RevocationStoreUnavailableError` (`core/security.py:536-543`, `:560-569`, `:736-747`). **Accepted.**

**Appendix B item 1 — `D-04-L` reversal outstanding.** Genuinely already-tracked open work, not a re-file:
`.ai/plans/17-authentication-implementation-execution.md:172` records the Product Owner's cluster-12/14 ruling,
states the shipped branch "is REVERSED BY SCHEDULED WORK", names `AB-10` as the reversal's owner, and — as the
auditor's anchor correction says — names the site `services/starter.py::ensure_admin_user`, **which does not
exist**. The real site is `db/starter.py::ensure_admin_user`, and the branch to reverse is exactly the single
`if self._config.env == EnvironmentEnum.PRODUCTION:` at `db/starter.py:562` raising `ValueError` at `:563-565`;
the rowcount-based `created` distinction the plan expects to preserve has already landed at `db/starter.py:531`.
**Accepted, and the anchor correction is itself accurate.**

**Appendix B item 2 — `C04-5`, deprecated GET handle in the access log.** Genuinely already-tracked:
`admin.py:567-584` is the shipped POST body form and `admin.py:542-564` is the deprecated GET with removal named
for release 1.0.9 in its own `description` (`:546-550`); the application logs only `retrieval_token[:8]`
(`admin.py:526`, `auth_service.py:622`); and the redacted edge format at
`docker/nginx/nginx.conf.template:21-25` logs `$uri` — path yes, query string no — so a legacy GET path does
reach the access log. **The anchor correction is accurate:** `docker/nginx/` contains exactly
`entrypoint-render.sh` and `nginx.conf.template`; there is no `nginx.conf`, so plan 17's `D-04-K` anchor does
not resolve. **Accepted, not a re-file.**

**Appendix B item 3 — `D-04-E` trusted-subnet residual.** Accurate on both halves:
`docker/docker-compose.yml:182` carries `"${FORWARDED_ALLOW_IPS:-172.21.0.0/16}"` byte-exact, a search of
`docker/` finds **no** `ipam` block in any compose file, and
`docker/docker-compose.override.yml:144` pins `"127.0.0.1"`. **Accepted.**

**The refuted bcrypt hypothesis — the disclosure that did not hold.** The input reports this as a clean
refutation with a measurement, and no finding filed. The refutation is correct in its conclusion and false in
its evidence: `VAL-04-001` above. Nothing real was dropped *because* the hypothesis was refuted — something
real was dropped *by* it, and it is restored here. Two further Appendix C rows that this pass re-derived
independently rather than accepting — algorithm pinning on both decode paths, and the credential separation —
both reproduced correctly, the first by confirming that a hand-crafted `alg: none` token is refused by
`decode_token` **and** `validate_refresh_token` ("The specified alg value is not allowed" on each path), with
`security.py:396-400` and `:431-435` the only two `jwt.decode` call sites in `src/` and both pinned to
`config.jwt.algorithm`.

**Route-auth sweep re-run independently.** The input's "no missing auth dependency" claim was not taken on
trust: an AST sweep over every route decorator in `src/mkobi/api/routes/` (annotations **and** `Depends`
default values, which a naive arg-name sweep gets wrong) reaches **59 route handlers, 5 without an auth
dependency** — byte-identical to the input's figures — and the five are exactly `POST /auth/login`,
`POST /auth/login/form`, `POST /auth/refresh`, `POST /auth/register-request` and `POST /client-errors`, the
documented public set. The input's note that `processing_logs.py:33` was a false positive of its sweep window
is also correct: the guard is declared at `processing_logs.py:68`
(`_current_user: UserRead = Depends(require_admin_role)`). **No missing auth dependency on a sensitive route
exists.** The independent spot-checks found no tenant bleed either — `users.py:184` compares the
caller-supplied `user_id` against the authenticated id and refuses the mismatch, `role` is read from the loaded
row rather than the token (`deps.py:641`), and there is no third, unverified decode path anywhere in `src/`.

### Appendix D — Coverage ledger (residual footer)

| Block of `.kilo/commands/audit/phases/99-audit-validate.md` | Item count reached | Outcome |
|---|---|---|
| 1 — Claim re-derived from the executing path | 9 of 9 findings + 3 runtime claims | 8 substantiated, 1 rejected; all anchors re-opened |
| 2 — Vacuous-control angle | 4 controls the report leans on | Applied to the three "verified by execution" claims and to the refuted-hypothesis disclosure. **One control green over zero items: the refuted bcrypt hypothesis decided nothing and its measurement was not reproducible** (`VAL-04-001`). The angle's other controls held |
| 3 — Grade against the audited rubric | 9 of 9 | 1 re-graded (AUTH-101 HIGH → MEDIUM); 8 sustained. Bands re-derived from `.kilo/commands/audit/phases/04-audit-authentication.md:114-121`, not from the input's framing |
| 4 — Which side moves | 2 candidates (AUTH-108 doc, AUTH-104 client) | AUTH-108 confirmed doc-side; AUTH-104 confirmed client-side, with ownership corrected to include phase 13 |
| 5 — Whether the recommendation can be carried out | 9 of 9 | All executable; two false premises corrected (AUTH-107's seamechanism, AUTH-105's "no blocker" scope); every named symbol re-resolved |
| 6 — Cross-phase conflict, ownership, merge | 1 contested finding (AUTH-109 vs `TOPO-104`) + 1 seam violation + 1 ownership gap (AUTH-104 / `P6` → plan 13) | 1 merge, 1 re-type, 1 ownership correction; `TOPO-104` is already validated, so the ruling rests on a validated sibling |
| 7 — Finding-ID namespace integrity | 1 prefix (`AUTH-`) | Declared at phase file `:129`; `AUTH-001…008` occupied and reproducible from plan 17; `AUTH-1xx` minted; no in-source markers of any `AUTH-` id found in `src/`, `tests/`, `frontend/src/` or `alembic/`; no reuse across phases |
| 8 — Shared template as a controlled artefact | 6 front-matter fields, 6 per-finding fields, zone rule | Front matter correct and honest (`phase:` names the audited phase, `executor: validator`). All nine findings carry all five mandated fields (`Severity`, `Zone`, `Observation`, `Evidence`, `Consequence`, `Recommendation`). **No zone defect: all nine zone strings were checked against `.kilo/commands/audit/phases/04-audit-authentication.md:23-112` and every one is its block title quoted verbatim.** The reserved empty-state string is correctly absent (the phase produced findings) and no summary is padded in its place |
| 9 — Does the input rest on its declared blocks | 9 of 9 | Resting on the declared blocks: **7** — AUTH-101 (block 6), AUTH-102 (block 4), AUTH-103 (block 7), AUTH-104 (block 8), AUTH-105 (block 4, "a guard defined but never reached"), AUTH-106 (block 2, "including the service-layer paths and any path no caller reaches"), AUTH-108 (block 5). Resting on an angle **no** declared block names: **2** — AUTH-107 (a DI-seam divergence; block 9 asks what *identity* a bound is keyed on, not where its client comes from) and AUTH-109 (a type annotation, which is the base context's "type hints" rule rather than any phase-04 block). Both undeclared-angle items are maintenance-surface findings and both were graded LOW, so no admissibility conflict arises — but AUTH-109's is also the seam violation recorded in block 6 |
| 10 — The validated report as an artefact | 9 of 9 verdicts, 4 VAL items | Tally agrees with the per-finding verdicts; identifiers preserved, none renumbered; `AUTH-*` and `VAL-*` never share a table |
| 11 — Shared angles | 2 angles | Not exercised by this input: it binds neither the vacuous-control angle nor the cross-resource side-effect angle in its own words, so there is no wording drift to adjudicate here |

**Left unsettled, with the reason.** (1) The **iteration count** in AUTH-101 (~100 refresh-and-replay cycles)
is derived from the configured thresholds and the cookie-rotation fact, not observed running: this pass did not
bring up the dev stack or drive a browser. The control flow is unambiguous and each hop is cited; the number is
arithmetic. This does not gate the verdict, which rests on the refusal shape, not the count. (2) AUTH-102's
**post-recovery exposure window** is bounded by the access and refresh TTLs quoted from
`docs/01-auth/auth-api.md:560-561`; the TTL values were taken from the declared contract and not re-measured
against `Settings`. (3) The **genuine two-claimant race** on `TempPasswordStore.retrieve` was not re-run — no
live Redis — and carries no weight here; the input discloses the same limit and `D-04-C` already records it as
demonstrated against a live store. (4) The frontend files cited by this report were checked for concurrent
modification at composition time and none had changed; `frontend/src/shared/types/api.types.ts` is modified in
the working tree but is **not** cited by any of the nine findings, so the flagged risk did not materialise.