---
phase: 04-authentication
executed: 2026-10-05
executor: auditor
problems-only: true
findings: 9
by-severity:
  CRITICAL: 0
  HIGH: 2
  MEDIUM: 2
  LOW: 5
---

# Phase 04 — Findings

## Summary

This phase re-audited credential lifecycle on the post-remediation tree (HEAD `716c755`), after the
twelve-block remediation recorded in `.ai/plans/17-authentication-implementation-execution.md` landed.
All nine audit blocks were examined against production code: `core/security.py`,
`core/temp_password_store.py`, `core/permissions.py`, `api/deps.py`, `api/routes/{auth,admin,users}.py`,
`services/auth_service.py`, `db/starter.py`, `config.py`, `utils/exceptions.py`, the composed client
(`shared/api/axiosInstance.ts`, `features/users/ui/ChangePasswordPage.tsx`,
`shared/auth/tokenStore.ts`) and the declared contract in `docs/01-auth/auth-api.md` /
`docs/08-security/security-overview.md`. The prior audit's `AUTH-001 … AUTH-008` all no longer reproduce
and are recorded as discharged in Appendix A, which is also why this report uses the free `AUTH-1xx`
range.

Nine findings, clustered on one route. `api/routes/auth.py::change_password` and
`api/deps.py::get_current_user_dependency` account for three of them, and all three are about how a
credential-changing operation's outcome crosses the HTTP boundary rather than about its logic: the
post-commit revocation is neither guarded nor reported truthfully, so a Redis fault answers a
*committed* password change with a generic 500 while every other session of that user survives
(AUTH-102) — the two admin siblings at the same seam report the committed-but-unrevoked outcome
correctly, which is what makes the third copy a defect rather than a tier difference; the
wrong-current-password refusal uses a status the SPA's own interceptor answers with a silent refresh,
turning one mistyped password into a loop of refresh-cookie rotations that ends in a sign-out
(AUTH-101); and the gate answers 404 where the refresh gate answers 401 for the same missing row, so a
deleted user's in-memory token is never discarded (AUTH-103). The remediation hardened the marker
semantics and left the operation's *reporting* and *client contract* untouched — the same three errors
recur at AUTH-104 on the client side, and the adjudication that `P6` records for AUTH-104's outcome was
never implemented because the owning commit touched no frontend file.

The remaining five (AUTH-105 … AUTH-109) are independent: an unreachable exception arm that leaves
`TOKEN_EXPIRED` unproducible, six `AuthService` methods with no production caller, one auth rate-limit
site that bypasses the DI seam its two siblings use, one mis-transcribed default in the declared
contract, and one dependency factory annotated with the wrong return type. The CRITICAL band is empty:
nothing demonstrated a session established for the wrong identity, a credential cleartext outside its
delivery boundary, or a credential usable after a guard should have refused it. Three items already
tracked as open work in `.ai/plans/` are disclosed in Appendix B rather than re-filed, and the areas
examined with nothing to report are registered in Appendix C.

## Findings

### AUTH-101 — A wrong current password is refused with 401, which the client's own interceptor turns into a refresh-and-replay loop that ends in a sign-out

**Severity** — HIGH

**Zone** — "Account state the credential cannot carry: the completion path"

**Observation** — `POST /api/v1/auth/change-password` maps a wrong current password to
`401 AUTHENTICATION_FAILED`. The SPA's single axios response interceptor exempts exactly two URLs from
its 401 branch — `/auth/login` and `/auth/refresh` — and `/auth/change-password` is not one of them,
so a rejected password change is treated as a dead session. The interceptor then refreshes, replays
the original request, and on the replay's 401 does the same thing again, because `isRefreshing` is
reset in a `finally` that runs before the replay settles. Each refresh rotates the cookie, so each
iteration presents a different cookie and therefore lands in a different per-identifier rate-limit
bucket; the loop is bounded only by the per-peer ceiling of 100 per 300 s. When that ceiling is
exhausted the refresh attempt answers 429, the interceptor treats the failed refresh as a dead
session, clears the token, toasts "Session expired. Please login again." and hard-navigates to
`/login`. The user never sees "current password is incorrect".

**Evidence** — `src/mkobi/api/routes/auth.py:678-686`:

```python
    except ValueError as e:
        logger.warning(
            "Password change failed",
            extra={"user_id": str(current_user.id), "error": str(e)},
        )
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail="Password change failed",
        ) from e
```

`frontend/src/shared/api/axiosInstance.ts:69-79` — the skip list is login and refresh only:

```typescript
    if (status === 401) {
      // Skip redirect/toast for login endpoint - let inline form error handle it
      if (error.config?.url?.includes('/auth/login')) {
        return Promise.reject(error)
      }

      // Skip retry for refresh endpoint - prevents infinite loop when no refresh cookie exists
      if (error.config?.url?.includes('/auth/refresh')) {
        removeToken()
        return Promise.reject(error)
      }
```

`frontend/src/shared/api/axiosInstance.ts:112-126` — replay, then the sign-out on a failed refresh:

```typescript
        const newToken = await handler()
        setToken(newToken.access_token)
        processQueue({ token: newToken.access_token })
        originalConfig.headers.Authorization = `Bearer ${newToken.access_token}`
        return axiosInstance(originalConfig)
      } catch (err) {
        const errorToReject = err instanceof Error ? err : new Error(String(err))
        processQueue({ error: errorToReject })
        removeToken()
        toast.error(SESSION_EXPIRED_MESSAGE)
        window.location.href = '/login'
        return Promise.reject(errorToReject)
      } finally {
        isRefreshing = false
      }
```

The identifier bound does not stop the loop because the cookie it digests changes each iteration —
`src/mkobi/api/routes/auth.py:544-552` mints and sets a new cookie on every successful refresh, and
`src/mkobi/api/routes/auth.py:437-446` keys the site at 10/300 s per digest against 100/300 s per peer.
The consuming screen is `frontend/src/features/users/ui/ChangePasswordPage.tsx:25-39`, which calls
`changePassword` (`frontend/src/features/users/api/userApi.ts:9-11`, plain `axiosInstance.post`, no
`skipErrorToast`) and renders `err.message` on failure. `frontend/src/shared/api/errorSurfaces.ts:13`
supplies the message: `export const SESSION_EXPIRED_MESSAGE = 'Session expired. Please login again.'`

The declared contract publishes the 401 as intended behaviour — `docs/01-auth/auth-api.md:366`:
`| `401`  | Current password incorrect | `AUTHENTICATION_FAILED` | Error message |` — while the same
document, at `docs/01-auth/auth-api.md:76`, records that the identical 401-on-a-refusal shape was
**rejected** for `force_password_change` for this precise reason: "the SPA's axios interceptor answers
any `401` with a silent refresh and, on failure, a sign-out back to `/login`, so a `401` refusal would
become a redirect loop". That precedent (decision `D-04-B`, `AUTH-101`'s sibling operation) is why this
is a defect and not a client-side preference.

**Consequence** — A user who mistypes their current password is signed out and lands on `/login` having
been told "Session expired. Please login again.", and the loop drives roughly 100 refresh-cookie
rotations and 100 replays of the doomed request from one submission (each replay costs one
cost-12 bcrypt verification, measured at 283 ms median on this host). This is the only route that
clears `force_password_change`, and the change-password screen disables its Cancel control in force
mode (`frontend/src/features/users/ui/ChangePasswordPage.tsx:104-108`, `disabled={isSubmitting || isForceMode}`),
so a flagged user who mistypes is confined to a screen that cannot tell them what is wrong and that
sends them away when they try again. Because the refresh identifier is a digest of the rotated cookie,
the per-identifier bound is bypassed on this path and the effective bound is the peer ceiling.

**Recommendation** — Change the wrong-current-password refusal to a status the interceptor does not
treat as a session fault. `422 VALIDATION_ERROR` (or `403 PERMISSION_DENIED`) both fall through to the
`status !== 401 && status !== 429` arm at `axiosInstance.ts:132` and render the real message. Keep
`AUTHENTICATION_FAILED` for genuinely unauthenticated cases only. If the 401 must stay for wire
compatibility, the alternative is a third skip in `axiosInstance.ts` — but that treats the symptom and
leaves every future 401 on `/auth/change-password` (e.g. a future lockout) exposed to the same loop, so
the backend status is the better place to fix it. Either way `docs/01-auth/auth-api.md:366` and the
route's own docstring (`auth.py:669`, `AppException 401: If current password is incorrect.`) must change
with it. No shipped test asserts the current status: `grep TOKEN_EXPIRED|change_password_mismatch`
over `tests/` returns nothing, and `tests/test_auth.py` has no change-password status assertion, so
there is no remediation blocker.

### AUTH-102 — A committed password change whose revocation write faults is reported as a generic 500 and every other session of that user survives

**Severity** — HIGH

**Zone** — "Single-use and lifetime guarantees, in both directions"

**Observation** — `AuthService.change_password` commits the new password and returns before
`change_password` writes the user-level revocation marker, so the marker write is deliberately last.
That last step is the only thing that enforces "changing your own password ends your other sessions",
and on this route it is the one call in the handler that no `try`/`except` covers. A Redis fault at that
point therefore escapes to the global exception handler, which answers a bare RFC 7807
`500 INTERNAL_ERROR` / "Internal server error". Both admin siblings at the identical seam wrap the
same call and state the truth; this one does not. Three effects follow: the caller is told the
operation failed when it succeeded, the security guarantee it performed does not hold, and no log line
anywhere names the affected user or says the password was committed.

**Evidence** — `src/mkobi/api/routes/auth.py:697-712`, verbatim, with the commit already done and the
marker write bare:

```python
    # The service has committed the new password, so the old credential is now
    # stale. Revoke every outstanding token for this user. The marker is a
    # non-transactional Redis write and is therefore placed after the commit,
    # following the pattern in admin.py::update_user_active_admin_endpoint: a
    # revocation before the commit would leave a live marker on a password
    # change that could still roll back.
    settings = get_config()
    await revoke_all_user_tokens(
        redis_client=redis_client,
        user_id=current_user.id,
        access_ttl=settings.jwt.access_token_expire_minutes * 60,
        refresh_ttl=settings.jwt.refresh_token_expire_minutes * 60,
    )

    logger.info("Password changed successfully", extra={"user_id": str(current_user.id)})
    return SuccessResponse(message="Password changed successfully")
```

Compare the admin reset at the same seam, `src/mkobi/api/routes/admin.py:309-329`:

```python
        settings = get_config()
        try:
            await revoke_all_user_tokens(
                redis_client=redis_client,
                user_id=user_id,
                access_ttl=settings.jwt.access_token_expire_minutes * 60,
                refresh_ttl=settings.jwt.refresh_token_expire_minutes * 60,
            )
        except Exception as revoke_error:
            logger.error(
                "Password reset committed but token revocation failed: id=%s: %s",
                user_id,
                revoke_error,
            )
            raise AppException(
                code=ErrorCode.INTERNAL_ERROR,
                detail=(
                    "Password was reset successfully, but revoking the user's "
                    "sessions failed; a second reset is required."
                ),
            ) from revoke_error
```

and the deactivation twin at `src/mkobi/api/routes/admin.py:195-214`, which uses the same guarded shape
and the message "User was deactivated successfully, but revoking the user's tokens failed". The handler
the exception actually lands in is `src/mkobi/utils/exceptions.py:344-348`:

```python
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception,
    ) -> JSONResponse:
        logger.error("Unhandled exception: %s", exc, exc_info=True)
```

— a traceback with no user id and no statement that the write was durable. Coverage gap:
`tests/test_revocation_store_outage.py` states its own scope in its module docstring — "A protected
request … `POST /auth/refresh` …" — and faults the two revocation **read** paths only. No test
exercises a faulting revocation **write**.

**Consequence** — Under a Redis fault, `POST /api/v1/auth/change-password` changes the password, clears
`force_password_change`, and answers 500. Every pre-existing access and refresh token for that user
remains valid, so the sessions the operation exists to terminate survive it. A user who changed their
password in response to a suspected compromise is told the change failed and is not — and neither the
operator nor the user can tell from the response or the log that the change landed. Because
`revoke_all_user_tokens` is the shared marker for deactivation and admin reset too, the operator's
mental model ("the marker is written after every credential change") is true on two of three routes
and false on the third.

**Recommendation** — Wrap the call at `auth.py:704` in the same guarded shape the two admin routes
already use, and keep the three messages distinguishable as the admin routes do: the self-service case
is not a "second reset is required" situation, it is "your other sessions are still signed in". Two
reasonable shapes: raise `AppException(INTERNAL_ERROR)` with a detail that says the password was changed
but sessions were not revoked (matching the siblings), or raise `SERVICE_UNAVAILABLE`/503 and treat it
as the dependency outage the revocation-read arm already treats it as (`RevocationStoreUnavailableError`
is the established signal and `deps.py:658-666` already maps it to 503). Prefer the second: a 503 is
honest about the cause and matches `D-04-F`'s ruling that "a refusal is visible while a bypass is
silent". Either way, log at ERROR naming `user_id`, and add the faulting-write case to
`tests/test_revocation_store_outage.py` using the existing `_fault_store` helper so the two read paths
and the write path are asserted together. The commit-then-marker ordering itself is correct and should
not move.

### AUTH-103 — The authentication gate answers 404 for a credential whose user no longer exists, while the refresh gate answers 401 for the same condition

**Severity** — MEDIUM

**Zone** — "A condition carried inside a credential against the condition read from the stored record"

**Observation** — When the token is well-formed and correctly signed but the row it names is gone,
`get_current_user_dependency` raises `ErrorCode.USER_NOT_FOUND`, which the status map assigns
`404 NOT_FOUND`. Every other credential refusal on the same gate is a 401, and `POST /auth/refresh`
refuses the identical condition with `401 AUTHENTICATION_FAILED`. 404 is outside the client's
session-remediation vocabulary: the axios interceptor treats only 401 as a session fault, so a deleted
user's in-memory access token is never discarded, no silent refresh runs, and no redirect to `/login`
happens — the SPA surfaces a "User not found" toast and continues holding a permanently useless
credential.

**Evidence** — `src/mkobi/api/deps.py:602-610`:

```python
        repo = UserRepository()
        user = await repo.get(id=user_id, db=db)
        if user is None:
            logger.warning("User not found: user_id=%s", user_id)
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
```

`src/mkobi/utils/exceptions.py:48-50` fixes the status:

```python
    # Resource errors
    ErrorCode.NOT_FOUND: HTTP_404_NOT_FOUND,
    ErrorCode.DASHBOARD_NOT_FOUND: HTTP_404_NOT_FOUND,
    ErrorCode.USER_NOT_FOUND: HTTP_404_NOT_FOUND,
```

The response carries a `WWW-Authenticate: Bearer` challenge on a 404, which no HTTP client treats as an
authentication failure. The refresh gate's contrasting arm, `src/mkobi/api/routes/auth.py:487-494`:

```python
    user = await UserRepository().get(UUID(user_id), session)
    if user is None:
        logger.warning("User not found during refresh", extra={"user_id": user_id})
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

The condition is reachable: `src/mkobi/api/routes/users.py:281` (`DELETE /api/v1/users/me`) and
`src/mkobi/api/routes/users.py:333` (`DELETE /api/v1/users/{user_id}`) both remove the row while leaving
outstanding tokens untouched. The client's handling is `frontend/src/shared/api/axiosInstance.ts:132-144`,
which for a 404 takes the generic-toast branch and calls neither `removeToken()` nor the `/login`
redirect. `tests/test_auth.py:199-218` asserts 401 for this condition **on the refresh route only**
(`test_refresh_nonexistent_user`); no test asserts the gate's status, so there is no remediation blocker.

**Consequence** — A user deleted by an administrator, or one who used `DELETE /users/me`, keeps a live
in-memory access token and receives 404 on every subsequent request for the rest of the tab's life. No
sign-out occurs, so the failure is presented as a server-side "User not found" rather than as the end of
that session. It also breaks the declared contract in two directions: an authentication failure is
reported with a resource status, and the same refusal reason carries two different statuses on the two
surfaces that consult the same row. The security direction is safe — access is refused either way — so
this is a correctness and client-contract defect, not an exposure.

**Recommendation** — Raise `AUTHENTICATION_FAILED` here, matching `auth.py:490-494`, so the two gates
refuse the same condition identically. `USER_NOT_FOUND` on an authentication gate is a category error:
the row's absence is the *cause* of the refusal, not the refused resource. If the distinction is worth
keeping for operators, keep it in the log line (which already says `User not found: user_id=%s`) rather
than in the status. Add the gate-side counterpart to `tests/test_auth.py::test_refresh_nonexistent_user`
so the two surfaces are asserted together and cannot drift again.

### AUTH-104 — After a successful password change the SPA signs the user out with the "session expired" notice that cluster 13 P6 explicitly rejected

**Severity** — MEDIUM

**Zone** — "Session continuity: what a captured long-lived credential is worth, and what a revocation marker must be able to express"

**Observation** — The post-commit revocation is correct, but the client is not prepared for the
consequence it was told to expect. `ChangePasswordPage` treats a successful change as a completed
operation, shows "Password changed successfully" and navigates to `/profile` while still holding the
now-revoked access token. The next request fails with `401 TOKEN_REVOKED`, the interceptor attempts a
silent refresh with the pre-change cookie, the refresh gate refuses it (`TOKEN_REVOKED`, and it clears
the cookie), and the interceptor resolves that failed refresh by removing the token, toasting
"Session expired. Please login again." and hard-navigating to `/login`. The user therefore sees a
success toast and then a session-fault toast for an action they just completed on purpose. The
adjudicated ruling for this exact outcome (`P6`, cluster 13, recorded against `AB-8`/`D-04-J`) requires
the normal login screen with no explanation and rejects the generic notice, because it "would misreport
a deliberate, user-initiated action as a session fault". `AB-8` shipped in `4600e5d`, which touches
eleven files and **no** frontend file, so the user-visible half of the ruling was never implemented.

**Evidence** — `frontend/src/features/users/ui/ChangePasswordPage.tsx:25-35`:

```typescript
  const onFormSubmit = async (data: ChangePasswordFormData) => {
    try {
      setError(null)
      setIsSubmitting(true)
      await changePassword(data)
      toast.success('Password changed successfully')
      void navigate('/profile')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to change password'
      setError(message)
      toast.error(message)
```

`frontend/src/shared/api/axiosInstance.ts:76-79` — the refresh attempt's own 401 short-circuits to
`removeToken()` with no retry:

```typescript
      // Skip retry for refresh endpoint - prevents infinite loop when no refresh cookie exists
      if (error.config?.url?.includes('/auth/refresh')) {
        removeToken()
        return Promise.reject(error)
      }
```

and `axiosInstance.ts:117-123` turns the rejected refresh into the sign-out:

```typescript
      } catch (err) {
        const errorToReject = err instanceof Error ? err : new Error(String(err))
        processQueue({ error: errorToReject })
        removeToken()
        toast.error(SESSION_EXPIRED_MESSAGE)
        window.location.href = '/login'
```

`frontend/src/shared/api/errorSurfaces.ts:13` is the rejected string:
`export const SESSION_EXPIRED_MESSAGE = 'Session expired. Please login again.'` The declared contract
does document the outcome correctly — `docs/01-auth/auth-api.md:373`: "**The caller's own session is
revoked too** — including the one that made the change — so the SPA must log in again with the new
password" — so the defect is the client's handling, not the documentation. Commit evidence:
`git show --stat 4600e5d` lists `docs/01-auth/auth-api.md`, `docs/06-backend/architecture.md`,
`src/mkobi/api/deps.py`, `src/mkobi/api/routes/admin.py`, `src/mkobi/api/routes/auth.py`,
`src/mkobi/core/permissions.py`, `src/mkobi/core/security.py` and four test files — no file under
`frontend/`.

**Consequence** — Every deliberate self-service password change ends with two toasts ("Password changed
successfully", then "Session expired. Please login again.") and a full-page redirect to `/login`. Under
`?force=true` the sequence is worse: the user lands on `/login`, authenticates successfully, and
`useAuth` (`frontend/src/features/auth/model/useAuth.ts:69-73`) immediately redirects them back to the
same change-password screen, so the user-visible story of a flagged user's first login is a session
expiry they did not cause. The security direction is correct — the sessions really are withdrawn — so
this is the messaging half of `P6` that was left unbuilt.

**Recommendation** — Treat a completed credential change as an intentional sign-out. The smallest
correct change is in `ChangePasswordPage.onFormSubmit`: after success, clear the token and navigate to
`/login` directly, instead of navigating to `/profile` and letting the next request discover the
revocation. A shared helper is already available for the first half — `logoutClient()` in
`frontend/src/features/auth/api/authApi.ts:31-33` calls `removeToken()` — so no new mechanism is needed.
The deeper fix, which also closes AUTH-101, is to stop routing a *client-known* outcome through the
interceptor's generic 401 branch; but the page-level change is worth landing on its own because it is
the only place that knows the revocation was intentional. Register the outcome as an accepted residual
if `P6` is formally descoped rather than implemented.

### AUTH-105 — No production path can emit `TOKEN_EXPIRED`; the expired-token arm in the gate is unreachable

**Severity** — LOW

**Zone** — "Single-use and lifetime guarantees, in both directions"

**Observation** — `get_current_user_dependency` carries a dedicated arm for an expired token, and it
can never execute. `decode_token` calls `jose.jwt.decode`, which raises `ExpiredSignatureError` — a
subclass of `JWTError` — but `decode_token` catches `JWTError` first and returns `None`. The gate then
takes its `payload is None` arm and refuses with `INVALID_TOKEN`, so `TOKEN_EXPIRED` is unreachable from
production. The enum member, its 401 entry in the status map, its RFC 7807 title, and two frontend
message-map entries all exist for a code no server path produces.

**Evidence** — `src/mkobi/core/security.py:403-405`, verified as the arm that intercepts it:

```python
    except JWTError as e:
        logger.error("JWT token decode error: %s", e)
        return None
```

`src/mkobi/api/deps.py:644-650`, the unreachable arm:

```python
    except ExpiredSignatureError as e:
        logger.warning("Token expired")
        raise AppException(
            code=ErrorCode.TOKEN_EXPIRED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
```

Runtime confirmation on this tree (`uv run python`, `jwt.decode` with the configured `HS256`): `issubclass(ExpiredSignatureError, JWTError)` is `True`, and `decode_token(<token minted with expires_delta=timedelta(minutes=-10)>)` returns `None` after logging `JWT token decode error: Signature has expired.` — the exception never leaves `decode_token`. The orphan surface: `src/mkobi/models/enums.py:249`
(`TOKEN_EXPIRED = "TOKEN_EXPIRED"`), `src/mkobi/utils/exceptions.py:40`
(`ErrorCode.TOKEN_EXPIRED: HTTP_401_UNAUTHORIZED,`), `src/mkobi/utils/exceptions.py:191`
(`ErrorCode.TOKEN_EXPIRED: "Token expired",`), `frontend/src/shared/api/errorMessages.ts:20`
(`[ErrorCode.TOKEN_EXPIRED]: 'Token expired',`) and
`frontend/src/features/auth/model/errorMessages.ts:10`
(`[ErrorCode.TOKEN_EXPIRED]: 'Session expired. Please log in again.',`). No test references the code or
the exception: `grep 'TOKEN_EXPIRED|ExpiredSignature' tests/` returns nothing, so there is no remediation
blocker — but `tests/test_auth_service.py:283` exercises `verify_token` with an expired token and passes,
which is consistent: `verify_token` sees `decode_token`'s `None`.

**Consequence** — An expired access token is refused as `INVALID_TOKEN` rather than `TOKEN_EXPIRED`.
Behaviourally the request is still refused with 401 and the correct `WWW-Authenticate` header, so no
control is weakened; the cost is diagnostic. Operators reading a 401 cannot distinguish a forged token
from an ordinary expiry, and the client-facing copy written for expiry is unreachable, so the SPA
cannot show the message that was designed for it. Two English-only guard comments elsewhere describe
this behaviour accurately, so the code's own documentation does not misstate it — this is dead logic,
not a contract violation.

**Recommendation** — Pick one direction and make the code match. Either (a) delete the
`ExpiredSignatureError` arm and the import at `deps.py:20`, and retire `TOKEN_EXPIRED` from the enum,
status map, title map and both frontend message maps; or (b) keep the distinction by moving the
classification into the security layer — have `decode_token` surface *why* it failed (for example by
raising, or by returning a sentinel the gate maps), which also restores the ability to tell a client
"your session expired" versus "your token is not valid". Option (b) is more useful and is what the
existing enum and frontend copy were built for; option (a) is cheaper. Do not leave the arm in place
believing it is reachable. Note the trap when taking (b): `tests/test_auth_service.py:283` currently
passes *because* `decode_token` swallows the expiry, so it must change with the fix rather than be
read as a regression.

### AUTH-106 — Six `AuthService` methods have no production caller, one of them a credential-minting path

**Severity** — LOW

**Zone** — "The two credentials that constitute one session: issuance paths, what each is accepted for, and what distinguishes them"

**Observation** — The credential inventory has seven minting/verification entry points. Only two are
reachable from a route or from another service method; the other six are reachable only from the test
suite. `refresh_token` is the notable one: it mints an access token through the same
`create_access_token` the live `POST /auth/refresh` route does not use, and nothing in `src/` calls it.
It is declared `@abc.abstractmethod` on `IAuthService`, so it is part of the declared interface rather
than an orphan, and `tests/test_auth_service.py` exercises it — the dead-code policy therefore calls
this "investigate before removing", not "delete".

**Evidence** — `src/mkobi/api/routes/auth.py:218` and `auth.py:369` are the only two production call
sites that mint a token through the service (`login_user`, `create_access_token`); the other two routes
that mint credentials call `core/security.py` directly (`auth.py:232`, `auth.py:544`). The unreachable
implementations, with no `src/` caller:

| Method | Definition | Interface declaration | Only exercised by |
| --- | --- | --- | --- |
| `refresh_token` | `src/mkobi/services/auth_service.py:262-287` | `src/mkobi/interfaces/service_interfaces.py:52-57` | `tests/test_auth_service.py:289`, `:301` |
| `verify_token` | `auth_service.py:289-304` | `service_interfaces.py:74-77` | `tests/test_auth_service.py:249`, `:293`, `:308` |
| `validate_refresh_token` | `auth_service.py:306-323` | `service_interfaces.py:79-82` | none found |
| `authenticate_user` | `auth_service.py:232-248` | `service_interfaces.py:38-43` | `tests/test_auth_service.py:187-219` |
| `get_user_by_id` | `auth_service.py:325-344` | — | none found |
| `get_user_by_email` | `auth_service.py:346-365` | — | none found |

A repo-wide search for `auth_service.` across `src/` returns exactly seven call sites —
`auth.py:218` `login_user`, `auth.py:343` `register_user`, `auth.py:369` `create_access_token`,
`auth.py:672` `change_password`, `auth.py:779` `register_request`, `admin.py:282`
`reset_password_admin`, `admin.py:425` `approve_registration_request` — none of which is one of the six.
`AuthService.create_user` (`auth_service.py:367-385`) is a one-line delegate to `register_user` and is
called internally by `approve_registration_request` (`auth_service.py:673`), so it is reachable and is
excluded from the table.

**Consequence** — Two risks, both maintenance rather than security. The interface promises a token
refresh capability that the live refresh route bypasses, so a reader who trusts `IAuthService` will look
in the wrong place for how sessions are refreshed; and `refresh_token` mints credentials through a path
no gate change has been validated against (it emits `user_id`/`email`/`role`, which the gate does
accept, so it is not a latent acceptance bug — but nothing keeps it true). The duplicated
`validate_refresh_token` wrapper is the sharper hazard: `auth.py:450` imports the `core.security` function
directly while the service method wraps the same function, and only one of the two names appears in the
route. Because these are abstract interface members with tests, no finding here is a security defect.

**Recommendation** — Establish intent before changing anything, then make it one answer. Either delete
the six from `IAuthService` and `AuthService` and their tests, which is the cheapest end state and
removes the duplicate `validate_refresh_token` name; or, if the service-level surface is deliberate
future-proofing, document it in `docs/01-auth/auth-api.md` with an explicit note that no route uses it
and that the live refresh path is `core/security.create_refresh_token` via `auth.py:544`. What should
not ship is the current state, where the interface asserts a capability and the documentation says
nothing about it. `[DOC-UPDATE]` if the surface stays; dead-code removal if it does not.

### AUTH-107 — `register_request` takes its rate-limit Redis client from a module call, not the DI dependency the other two auth sites use

**Severity** — LOW

**Zone** — "The identity an abuse bound is keyed on, and whether the caller can choose it"

**Observation** — All three auth rate-limit sites now share one key-derivation helper, one identifier
digest, and one 10x peer-to-identifier ratio, but they do not share one source for the Redis client.
`_handle_login` and `refresh` receive `redis_client` as a FastAPI dependency; `register_request` has no
such parameter and calls `redis_client.get_async_redis_client()` on the imported module instead. In
production this is harmless — `get_async_redis_client` is `lru_cache`d, so both spellings return the
same process-wide client — but it means the suite's documented override seam does not reach this site,
and a future per-request Redis client, a read-replica split or a health-gated client would apply to two
auth rate limits and silently not to the third.

**Evidence** — `src/mkobi/api/routes/auth.py:758-761`:

```python
    rate_limiter = AsyncRateLimiter(
        redis_client.get_async_redis_client(),
        fail_closed=get_config().rate_limiter_fail_closed,
    )
```

against `src/mkobi/api/routes/auth.py:200-204`, the same construct one function above:

```python
    client_ip = _resolve_client_ip(request)
    rate_limiter = AsyncRateLimiter(
        redis_client,
        fail_closed=get_config().rate_limiter_fail_closed,
    )
```

Here `redis_client` is the route parameter declared in `_handle_login`'s signature; in
`register_request` no such parameter exists, so the name resolves to the module imported at
`src/mkobi/api/routes/auth.py:38` (`from mkobi.core import redis_client`). The seam being bypassed is
`get_redis_client_dependency` at `src/mkobi/api/deps.py:147-153`, which is exported in `deps.__all__`
and is the suite's substitution point. Coverage is nevertheless real:
`tests/test_rate_limiting.py:74-108` (`test_register_request_rate_limit_exceeded`) asserts the 429 and
the `Retry-After` header, because `tests/conftest.py:515-521` patches the module attribute itself — so
this is a seam-divergence finding, **not** a coverage gap, and it should not be reported as one.

**Consequence** — Contained today. The observable risk is that a future change to how Redis is supplied
per request will be applied to the login and refresh limiters and not to the registration-request
limiter, and nothing in the test suite would catch the omission because the tests patch the module
rather than the dependency. The helper docstring at `auth.py:93-96` already draws the line — it excludes
`client_errors.py` and `upload.py` by name as another phase's surface — but `register_request` is inside
its declared scope and diverges inside that scope.

**Recommendation** — Add `redis_client: Any = Depends(get_redis_client_dependency)` to
`register_request`'s signature and pass it to `AsyncRateLimiter`, matching the two siblings. One
parameter, no behaviour change, and it makes the three auth rate-limit sites uniform in how they obtain
their client. Nothing else needs to move; `tests/conftest.py` keeps working because it patches the
module the dependency itself calls.

### AUTH-108 — The declared production-default credentials are documented as `admin`/`admin`; the shipped defaults are `admin`/`CHANGE_ME_ADMIN_PASSWORD`

**Severity** — LOW

**Zone** — "The identity namespace the handshake writes into, and the privileged entries already in it"

**Observation** — The security-constraints list of the auth contract names the rejected production
default credential pair as `admin`/`admin`. Neither half is a shipped default: the username default is
`admin`, and the password default is a placeholder that `WEAK_PASSWORDS` and the `change_me` prefix
test both reject. A reader checking whether the guard covers the real defaults has to go and read
`config.py` to find out, and a reader trusting the document would test `admin`/`admin`, which is not a
case any code path can produce.

**Evidence** — `docs/01-auth/auth-api.md:566`:

```
- **Production credentials:** Default credentials (`admin`/`admin`) are rejected in production
```

against `src/mkobi/config.py:728-729`:

```python
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="CHANGE_ME_ADMIN_PASSWORD", alias="ADMIN_PASSWORD")
```

The rejection machinery the sentence refers to is real and correct —
`src/mkobi/config.py:786-803` (`validate_admin_credentials`, production-only) rejects the password via
`is_weak_admin_password`, and `src/mkobi/config.py:775-784` rejects the username via
`is_weak_admin_username`; `src/mkobi/config.py:52` is the list
`{"admin", "administrator", "root", "test", "user", "admin@example.com"}` and
`src/mkobi/config.py:53-65` the password list. So this is documentation only: the control it claims
exists does exist and is correctly scoped.

**Consequence** — Maintenance and audit-trail only. The defect class this phase exists to find is an
*unbacked* promise; this promise is backed and merely mis-transcribed. The risk is a future reader
believing the guard list is smaller than it is, or an operator testing the documented pair, finding it
already refused, and concluding the check is untested.

**Recommendation** — `[DOC-UPDATE]`: quote the shipped defaults verbatim
(`admin` / `CHANGE_ME_ADMIN_PASSWORD`) or, better, drop the literal pair and point at
`is_weak_admin_username` / `is_weak_admin_password` in `config.py`, which is the single source of truth
and cannot drift. The same sentence appears nowhere else in `docs/01-auth/`, so this is a one-line edit.

### AUTH-109 — `require_role_dependency` is annotated as returning a session, a user, or None

**Severity** — LOW

**Zone** — "The two credentials that constitute one session: issuance paths, what each is accepted for, and what distinguishes them"

**Observation** — The universal role-dependency factory in the authentication dependency module carries
a return annotation that does not describe what it returns. It returns a single-argument async callable
(`role_checker`); the annotation claims `AsyncSession | UserRead | None`. Nothing enforces it, because
`mypy` only checks what the body returns and this is a nested function definition, so the gates stay
green while the annotation misleads every reader. The factory also has no caller anywhere in `src/`,
`tests/` or `frontend/src/` — it is exported in `__all__` (`deps.py:78`), so it reads as part of the
module's public dependency surface, but the only reference to it beyond its own definition is the usage
example inside its own docstring.

**Evidence** — `src/mkobi/api/deps.py:751-753`, verbatim:

```python
def require_role_dependency(
    required_role: UserRole,
) -> (AsyncSession | UserRead) | None:
```

The body returns the closure — `src/mkobi/api/deps.py:775-791`:

```python
    async def role_checker(
        user: UserRead = Depends(get_current_user_dependency),
    ) -> UserRead:
```

and the factory is the last statement of the function, so the value the annotation describes is never
produced. `AsyncSession` is imported for this annotation and for `get_db_dependency`'s own
`-> AsyncSession` (`deps.py:123`), so removing it from this signature does not orphan the import. The
caller census is exactly three hits, all inside the definition itself: `deps.py:78` (the `__all__`
entry), `deps.py:751` (the `def`) and `deps.py:770` (the docstring example
`user: UserRead = Depends(require_role_dependency(UserRole.ADMIN)),`).

**Consequence** — No runtime effect: the three sibling role guards (`deps.py:679`,
`deps.py:706`, `deps.py:733`) and the four typed aliases (`deps.py:976-979`) do not use this factory,
and `Depends()` erases the annotation anyway. Two costs: a maintainer reading the authentication module
is told this returns a database session or a user object, and the annotation survives every refactor
because no test or type check can see it; and the module advertises a role gate in `__all__` that
nothing uses, so a reader adding a new role-protected route may reasonably reach for it and inherit an
unreviewed path instead of the three guards that are actually in use. This is the base context's
"type hints on every public function" rule producing an actively wrong hint rather than a missing one,
and it overlaps the dead-surface question raised in AUTH-106.

**Recommendation** — Annotate the callable it actually returns, e.g.
`-> Callable[[UserRead], Awaitable[UserRead]]`, or drop the annotation and note the return in the
docstring, consistent with the three sibling role guards (`deps.py:679`, `:706`, `:733`) which annotate
`-> UserRead` on the dependency itself and do not use a factory. Decide separately whether the factory
should exist at all, together with AUTH-106; if it is kept, the annotation must be correct, and if it is
removed the `__all__` entry goes with it. Trivial effort.

## Distribution

The nine findings split into one component that carries three of them, one cross-component pair, and
five independent items:

- **Backend credential issuance and gates** (`api/deps.py`, `api/routes/auth.py`,
  `api/routes/admin.py`) — AUTH-101, AUTH-102, AUTH-103, AUTH-105. The largest cluster and the
  component that carries the phase. Three of the four converge on the single route
  `api/routes/auth.py::change_password`; the fourth is the gate's own expired-token arm.
- **Backend service and dependency surface** (`services/auth_service.py`, `api/deps.py`) —
  AUTH-106, AUTH-107, AUTH-109. Dead or divergent surface, no security effect, one shared cause.
- **Cross-cutting** — AUTH-101 and AUTH-104 each straddle the backend and the composed client: neither
  is fixable on one side alone, and each is listed once only. AUTH-108 is a declared-contract
  transcription error, and the mis-transcribed `401` row at `docs/01-auth/auth-api.md:366` travels inside
  AUTH-101.

So the single component that carries the most is `api/routes/auth.py::change_password` together with
`api/deps.py::get_current_user_dependency`: three findings (AUTH-101, AUTH-102, AUTH-103) and one
tracked residual (Appendix B, `C04-5`) all converge there. That is the phase's structural result — the
remediation hardened the marker semantics thoroughly and left the operation's *reporting* and *client
contract* untouched.

## Cross-Finding Analysis

Two causes, each shared by more than one finding.

**Cause 1 — the authentication error contract is decided per-route against a 401 interceptor whose
scope nobody wrote down.** AUTH-101 (a wrong password refused with 401) and AUTH-104 (a successful
change followed by a 401-driven sign-out) are the same defect seen from two ends: every auth refusal
and every auth success is routed through one interceptor that treats 401 as "session dead", and the
routes decide their statuses without accounting for it. `D-04-B` already found and fixed one instance
of this (`force_password_change` → 403, `deps.py:620-638`, with the reasoning written into
`docs/01-auth/auth-api.md:76`) and did not sweep for others. AUTH-103 is a third instance with the
opposite shape: a 404 where the same gate should have produced a 401, so the interceptor's remediation
never runs. Fixing any one of the three leaves the other two, which is why the roadmap treats them as
one step.

**Cause 2 — the post-commit revocation seam has three implementations and one of them was written
twice.** AUTH-102 is the unguarded third copy. Its siblings (`admin.py:195-214` and `admin.py:309-329`)
were written with an explicit comment naming the failure mode they guard against — "Falling through to
the blanket handler would claim the whole operation failed while the password is already reset" — which
is precisely the comment `auth.py:697-702` lacks, even though it cites the sibling pattern two lines
earlier. The defect was a copy divergence, not a misunderstanding.

Everything else is independent: AUTH-105 (an unreachable exception arm), AUTH-106 (unreachable service
methods), AUTH-107 (a DI seam bypass), AUTH-108 (a mis-transcribed default) and AUTH-109 (a wrong
annotation) share no cause beyond all being consequences of the same thing — the surface was built
route-by-route and each route's author resolved the local question without a shared inventory.

## Roadmap

Grouped by cause, as the causes differ.

**Step 1 — close the error-contract cause together (AUTH-101, AUTH-103, AUTH-104).** *No other step may
start before this one finishes*, because all three change status codes or client handling on the same
two files and a partial application leaves the gate and the client disagreeing in a new way. Decide
the status vocabulary first: `401` means "your credential is not acceptable" and only that;
"your credential is fine but the request is refused" is `403` or `422`; "your credential is fine and the
request was honoured" never becomes a `401`. Then: (a) `auth.py:683-686` → a non-401 status and update
`auth-api.md:366` and the route docstring at `auth.py:669`; (b) `deps.py:606-610` →
`AUTHENTICATION_FAILED`, with `tests/test_auth.py::test_refresh_nonexistent_user`'s gate-side
counterpart added so the two surfaces are asserted together; (c) `ChangePasswordPage.onFormSubmit`
clears the token and navigates to `/login` on success instead of navigating to `/profile` and letting
the next request discover the revocation. Must be true before step 2: no route in `api/routes/auth.py`
returns 401 for a refusal whose cause is not an unacceptable credential, and
`grep -n "AUTHENTICATION_FAILED" src/mkobi/api/routes/auth.py` shows only the two rows that mean it.

**Step 2 — close the revocation-seam cause (AUTH-102).** Independent of step 1 and can run in
parallel; it touches `auth.py:704-709` only. Wrap the write in the shape `admin.py:310-329` already
uses, prefer the 503 mapping that `deps.py:658-666` already establishes for a revocation-store outage,
log at ERROR naming `user_id`, and extend `tests/test_revocation_store_outage.py` with the faulting-write
case. Must be true before step 3: all three post-commit revocation sites have the same guarded shape and
three distinguishable messages.

**Step 3 — settle the dead and divergent surface (AUTH-106, AUTH-107, AUTH-109).** One investigation,
three small edits; sequence last because both of the first two steps edit `api/routes/auth.py` and
`api/deps.py`, the same two files all three findings live in. Requires a decision, not code: which
`AuthService` methods exist. `AUTH-107` and `AUTH-109` are mechanical once that decision is taken.

**Step 4 — the low-severity documentation and dead-code items (AUTH-105, AUTH-108).** Independent of
everything above; can ship at any time. `AUTH-105` needs a direction chosen first (keep `TOKEN_EXPIRED`
and make it reachable, or retire it), and `AUTH-108` is a one-line doc edit.

## Rollout Safety

Step 1 changes observable behaviour in two directions that must both be checked before it is considered
done. Raising the status on a wrong current password from 401 to 422/403 is a **wire change**: any
client keying on 401 to detect a session problem — the SPA does, and so might anything outside this
repo — will stop signing users out on that route, which is the intent, but the change is visible in
access logs and in any API-level assertion elsewhere. `deps.py:606-610` moving from 404 to 401 is
narrower: the only caller-visible effect is that the SPA now clears the token and redirects instead of
toasting, and a client that was distinguishing "row is gone" from "token is bad" by status loses that
distinction — which is the point, since the row's absence is not a distinguishable resource for a
credential. `ChangePasswordPage` navigating to `/login` on success removes the `toast.success` the user
currently sees; keep the toast and add the navigation rather than replacing it, or the user loses the
only confirmation that the change landed.

Step 1 must be verified by re-running the login → force-change → change-password flow end to end with
the real client, because the two findings only manifest through the composed interceptor; a
backend-only test cannot observe either. Step 2 changes a 500 into a 503 on a Redis fault on one route,
so verify that `POST /api/v1/auth/change-password` still answers 200 with the marker written on a healthy
store — `tests/test_revocation_store_outage.py` does not currently cover the write and must be extended
before, not after, the change lands. Every step is a plain revert: no schema change, no migration, no
data-shape change, and the marker semantics in `core/security.py` are untouched by all four steps. The
one non-revertible thing to watch is operational habit — once AUTH-102 lands, operators may start
trusting the post-commit revocation to have happened, so the `C04-5` and `D-04-E` residuals in
Appendix B should be re-read as live risk rather than as background before that trust is extended.

## Appendices

### Appendix A — Finding-ID namespace, and what was already discharged

`AUTH-` is the prefix this phase owns (`.kilo/commands/audit/phases/04-audit-authentication.md:129`).
**Collision disclosed:** `AUTH-001` … `AUTH-008` are occupied by the previous audit of this phase. A
repository search over `docs/` and `.ai/` returns exactly those eight and no others, and they are
referenced by name in `.ai/plans/17-authentication-implementation-execution.md:9`
(`findings_discharged: 8 AUTH-*, 10 VAL-04-*`). This report therefore starts at `AUTH-101`, the free
range the base context designates. No `AUTH-1xx` identifier existed before this pass.

All eight prior findings were re-checked and **do not reproduce**:

| Prior | Prior title | State on this tree |
| --- | --- | --- |
| AUTH-001 | Password reset writes an unretrievable credential | discharged — `TempPasswordStore.store` returns `bool` (`core/temp_password_store.py:91-123`) and both services propagate it as `credential_stored` (`auth_service.py:600-629`, `:693-722`) |
| AUTH-002 | Approval/reset commit ordering vs the temp-password store | discharged — commit-then-store is deliberate and documented (`auth_service.py:637-645`, `docs/04-admin/admin-api.md`) |
| AUTH-003 | `force_password_change` documented but never enforced | discharged — enforced in `deps.py:627-638` with the four-entry allow-list at `deps.py:503-510` |
| AUTH-004 | Token revocation unusable as a deactivation mechanism | discharged — `is_active` is authoritative on both issuance paths (`auth_service.py:213-217`, `auth.py:525-531`) and reactivation clears the marker (`admin.py:216-242`) |
| AUTH-005 | Rate limiting keyed on an untrusted header | discharged for the header-spoofing half — `FORWARDED_ALLOW_IPS` is set through compose (`docker/docker-compose.yml:182`) and the peer key is derived, not read from the header (`auth.py:124-138`) |
| AUTH-006 | `GET /admin/temp-passwords/{token}` is an oracle | superseded — the handle moved to a body field (`admin.py:567-584`) with the GET deprecated (`admin.py:542-564`); the access-log half remains, tracked below |
| AUTH-007 | Admin bootstrap logs "ensured" for every startup | discharged — `created` is read from `rowcount` and three outcomes are logged distinctly (`db/starter.py:531`, `:545-571`) |
| AUTH-008 | Redis degradation is fail-open at the revocation boundary | discharged — all three readers raise `RevocationStoreUnavailableError` (`core/security.py:522-569`) and callers map it to 503 (`deps.py:658-666`, `auth.py:464-469`, `:504-509`) |

### Appendix B — Items already tracked as open work in `.ai/plans/`, reported not re-filed

These were found during this pass and are **not** new findings. They are listed because the phase
requires disclosure rather than silence.

1. **`D-04-L` reversal has not landed.** `.ai/plans/17-…md:172` records the Product Owner's cluster-12/14
   ruling (warn naming the account and its role, and continue in **every** environment including
   production) and states the shipped production branch "is REVERSED BY SCHEDULED WORK". The reversal
   is still outstanding at `src/mkobi/db/starter.py:562-565`, which raises `ValueError` in production
   when the admin address is occupied by a non-admin user. **Anchor correction for whoever executes it:**
   plan 17 names the site `services/starter.py::ensure_admin_user`; there is no `services/starter.py` in
   this tree — the real site is `db/starter.py::ensure_admin_user`, lines 465-571, and the branch to
   reverse is the single `if self._config.env == EnvironmentEnum.PRODUCTION:` at line 562. The
   rowcount-based `created`/`already existed` distinction the plan expects to preserve has already
   landed at `db/starter.py:531`.
2. **`C04-5` — the retrieval handle still reaches the edge access log.** The POST body form landed
   (`admin.py:567-584`) and the deprecated GET is scheduled for removal in 1.0.9 (`admin.py:546-550`),
   but while the GET exists its path parameter is written by the redacted log format at
   `docker/nginx/nginx.conf.template:21-25`, which logs `$uri` (the query string is redacted; the path
   is not). The application itself logs only `retrieval_token[:8]` (`admin.py:526`,
   `auth_service.py:622`), which is 32 bits of a 122-bit `uuid4()` and not a usable leak. Note for the
   next executor: plan 17's anchor `docker/nginx/nginx.conf` does not exist — the file is
   `docker/nginx/nginx.conf.template`, rendered by `docker/nginx/entrypoint-render.sh`.
3. **`D-04-E` residual — the trusted-proxy subnet is still auto-assigned.** `docker/docker-compose.yml:182`
   still carries the default `"${FORWARDED_ALLOW_IPS:-172.21.0.0/16}"` and no `ipam` block exists in
   any compose file, so the value is a property of the reference host. A mismatch fails *safe* (uvicorn
   trusts no peer, so one bucket engages) and produces no log output. The development override
   deliberately trusts nothing (`docker/docker-compose.override.yml:144`, `"127.0.0.1"`).

### Appendix C — Areas examined with no finding

Recorded explicitly, per the reporting contract. Each was examined by reading the cited production
code, and none is padded.

| Block | Property established | Anchor |
| --- | --- | --- |
| 2 | Algorithm pinning is present and effective on both decode paths; a hand-crafted `alg: none` token is refused by both. Runtime check on this tree. | `core/security.py:396-400`, `:431-435` |
| 2 | The two credential kinds are separated — access tokens carry `user_id`, refresh tokens carry `sub`, and each gate reads the name the other lacks, so neither credential is accepted where the other is expected. Measured: access payload `['email','exp','iat','jti','role','user_id']`, refresh payload `['email','exp','iat','jti','sub']`. The separation rests on the claim name rather than on an explicit `typ` claim, which is an observation rather than a defect since no cross-acceptance exists. | `auth.py:478-485`, `deps.py:575-584` |
| 3 | Verification cost is uniform between a matching and a non-matching identity. The placeholder value at `auth_service.py:200-203` is a malformed-looking but *functioning* cost-12 bcrypt hash — measured at **268.9 ms** median against **283.6 ms** for a real cost-12 verification on this host, a 1.1x ratio, so the timing defence the comment claims does hold. Recorded because the literal looks invalid and a reader may reasonably suspect it is a no-op; it is not. | `auth_service.py:196-207`, `core/security.py:228-260` |
| 3 | bcrypt cost is 12 and passwords are truncated at a character boundary to 72 bytes before both hashing and verification, consistently, so no prefix-collision path exists. The 72-byte ceiling is additionally enforced at admission. | `core/security.py:37`, `:166-199`, `:220-223`, `:248-249`; `utils/validators.py:221-224` |
| 4 | The one-time temporary credential is spent atomically: `retrieve` issues GET+DELETE inside a single `pipeline(transaction=True)`, which Redis executes as one indivisible MULTI/EXEC. The failure direction is also established — `store` fails open and returns `False`, `retrieve` raises `TempPasswordStoreUnavailableError` and the route maps it to 503, so "cannot answer" is never blurred into "already claimed". | `core/temp_password_store.py:143-158`, `admin.py:529-533` |
| 5 | The conflict clause on the admin bootstrap is `ON CONFLICT (email) DO NOTHING`, so it overwrites no privilege and no live credential; on conflict the code reads only `id` and `role` and never `password_hash`. No collision is reachable between the operator-provisioned row and a registrable identity: the username default `admin` is not an email address, `AuthService.register_request` requires an `@` (`auth_service.py:406-411`), and `register_user`'s regex rejects it (`auth_service.py:38`, `:98`). | `db/starter.py:513-543`, `auth_service.py:98-101`, `:406-411` |
| 7 | Every condition the handshake encodes is read from the stored record on every surface: `is_active` on login, refresh and the gate; `role` from the freshly loaded row rather than from the token, so a role change takes effect immediately; `force_password_change` read from the loaded `UserRead` at no extra query cost. The tokens' `role` and `email` claims are inert — no gate reads them — which fails safe. | `auth_service.py:213-226`, `auth.py:533-535`, `deps.py:602-641` |
| 9 | The peer identity is derived from the connection, not from a caller-set header. `X-Forwarded-For` is set by the edge (`nginx.conf.template:60-61`) and consumed by uvicorn's proxy-headers middleware, which walks the list from the right — a caller-appended leftmost entry is never selected. `_resolve_client_ip` handles a missing or non-IP peer with a sentinel that still rate-limits rather than bypassing. | `auth.py:74-76`, `:124-138`; `nginx.conf.template:60-61` |
| 9 | All three auth rate-limit sites share one key derivation, one SHA-256 identifier digest, and one 10:1 peer-to-identifier ratio, and both bounds are charged before the credential is checked. | `auth.py:79-109`, `:141-177` |
| — | Authentication is present on every data-bearing route. A mechanical sweep of all 59 route decorators in `api/routes/` found five without an auth dependency, and all five are the documented public set: `POST /auth/login`, `/auth/login/form`, `/auth/refresh`, `/auth/register-request` and `POST /client-errors`. `processing_logs.py:33` was a false positive of the sweep's window, not a gap — it declares `Depends(require_admin_role)` at line 68. | `api/routes/*.py` |
| — | No cross-tenant reach: the system is single-tenant with role hierarchy plus per-dashboard ACLs. The authenticated identity is resolved from the token on every request and every access decision is keyed on `user.id`; the one route taking a caller-supplied `user_id` compares it against the authenticated id and refuses the mismatch. | `users.py:184`; `deps.py:797-838`; `core/permissions.py:152-212` |
| — | Access tokens are held in a module-level variable in production builds and never written to browser storage; `sessionStorage` is the development fallback only, gated on `import.meta.env.PROD`. The refresh cookie is `HttpOnly` + `SameSite=Strict` with `Secure` defaulting to true. | `tokenStore.ts:66-75`, `:84-90`, `:142-154`; `core/security.py:43-45`, `:446-471`; `config.py:571-574` |
| — | No auth path raises `HTTPException` directly, and every refusal goes through `AppException` with an `ErrorCode`; the validation handler strips the offending raw value so a submitted plaintext password cannot reach the log record or the response body. | `utils/exceptions.py:229-368`; `app.py:492-493` |
| — | The `force_password_change` allow-list matches the mounted router exactly: all four entries resolve to real `(method, path)` pairs under the `/api/v1` prefix applied in `app.py:361`, and no route outside the list is reachable while the flag is set. | `deps.py:503-532`; `app.py:361` |

### Appendix D — Method and limits

**Verified by execution on this tree:** `decode_token` on an expired token returns `None` (AUTH-105);
`issubclass(ExpiredSignatureError, JWTError)` is `True`; a hand-crafted `alg: none` token is refused by
both `decode_token` and `validate_refresh_token`; the access and refresh payload shapes; the bcrypt cost
measurement in the block-3 row above (20 samples each, bcrypt 5.0.0); the `git show --stat 4600e5d`
frontend-absence claim (AUTH-104); the caller censuses for `AuthService` methods and
`require_role_dependency`. All run read-only via `uv run python -c` and `git`; no repository file was
modified.

**Not verified, and why.** The end-to-end behaviours in AUTH-101 and AUTH-104 were established by
tracing the composed client from source — interceptor control flow, cookie rotation, rate-limit key
derivation — rather than by driving a browser, because this pass did not bring up the dev stack. The
control flow is unambiguous and each hop is cited, but the *count* of loop iterations (~100, bounded by
the peer ceiling rather than the per-identifier bound) is derived from the configured thresholds and
the fact that each iteration rotates the cookie; it was not observed running. The genuine two-claimant
race on `TempPasswordStore.retrieve` was not re-run here — `D-04-C` records it as demonstrated against
live Redis and committed as `test_retrieve_concurrent_claimants_single_winner_real_redis`; that test
skips without a reachable server and therefore carries no weight in this pass. Per the phase contract,
both are limits on the report and are recorded here rather than filed as findings.

**Concurrent-modification note.** The base context flags the frontend as moving during the audit. The
frontend files cited in this report (`axiosInstance.ts`, `ChangePasswordPage.tsx`, `userApi.ts`,
`authApi.ts`, `useAuth.ts`, `tokenStore.ts`, `errorMessages.ts`, `errorSurfaces.ts`) were each opened
and read at the line numbers quoted, in this session, after the last write to them; no drift was
observed between reading and writing. The backend files were re-read at their cited ranges immediately
before this report was composed.