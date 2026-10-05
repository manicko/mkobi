---
phase: 09-test-coverage
executed: 2026-10-05
executor: auditor
problems-only: true
findings: 13
by-severity:
  CRITICAL: 0
  HIGH: 5
  MEDIUM: 5
  LOW: 3
---

# Phase 09 — Findings

## Summary

Examined the assurance the suite carries against the assurance it delivers: the 89 backend
test modules under `tests/`, `tests/conftest.py` as a system, the 30 frontend test files under
`frontend/src/`, `pyproject.toml`'s pytest/coverage block, `frontend/vite.config.ts`'s coverage
block, `Makefile.ps1`'s gate wiring, and `docs/06-backend/testing.md` as the SSOT for the test
harness. The most consequential thing found is that one dashboard-scoped endpoint family —
`GET/PUT/DELETE /processing-configs/{dashboard_id}` — performs its access check **inline in the
handler body** rather than through a dependency, and no test in the suite ever drives it without
a grant, so the boundary is asserted from its admitting side only. Alongside it, the axios
401 refresh-and-replay branch that owns session recovery has no test at all, and the frontend
coverage gate that *is* wired into `Invoke-Check` measures 37 of the 66 non-test source files,
so its four thresholds are read over a population that excludes the entire admin UI, the router,
and the entry point. The suite is otherwise in materially better shape than the earlier pass
recorded: `test-app` now bind-mounts the working tree, `_reset_config_cache` closes the settings
singleton leak, `test_admin_cannot_delete_self` scopes its own state, the enum-consistency module
is two-way, and `/frontend/coverage/` is gitignored — five items the prior pass
filed are confirmed remediated and are recorded as such rather than re-filed.

The remaining nine sit in two places. Seven are backend assertions that cannot fail for the
property they name — a pool that never contends, a rate limit driven from one peer, a 404 posing
as a 500, a `len()` that restates a mock's own return value, a compose file read as text, a skip
guard that cannot fire, a hard rule with no census. Two are frontend: the module that owns
session recovery has no test, and the coverage gate that runs on every `check` measures 37 of the
66 non-test source files.

### Finding-ID namespace disclosure

`.ai/plans/_code-context/09-test-coverage-code-context.md` (frontmatter
`finding_prefix: TST-`, `findings: 18`) and `.kilo/commands/audit/phases/09-audit-test-coverage.md:146`
both name **`TST-`** for this phase; the validated report they describe
(`.ai/audit/99-validation/09-test-coverage-validated-findings.md`, 1324 lines) is **not present in
this repository**. The assignment for this run names **`TEST-`**. To avoid minting into an
occupied namespace without disclosing it, this report uses `TEST-101`+ and records the collision
here. Where a finding below substantiates a `TST-` item that cannot be checked against the absent
report, the item is named inline as a cross-reference.

## Findings

### TEST-101 — The processing-config access check is inline in the handler and no test drives it without a grant

**Severity** — HIGH

**Zone** — "Each boundary, from each side — including the ones every test crosses the same way"

**Observation** — All three handlers of the `processing-configs` router perform their IDOR check
inline in the handler body rather than through a `Depends(require_dashboard_*)` dependency, and no
test in the suite calls any of them as a caller without a grant. `tests/test_processing_config_boundary.py`
exercises `GET` and `PUT` (`tests/test_processing_config_boundary.py:391`, `:411`, `:463`) and every
one of those three tests builds its caller through `_make_dashboard_with_edit_access`
(`tests/test_processing_config_boundary.py:101-120`, used at `:387`, `:407`, `:459`). The only other
callers of the path in the suite are a schema lookup (`tests/test_openapi.py:72`) and a
request-shape test that PUTs to a random UUID and asserts `422`
(`tests/test_request_boundary_extra_forbid.py:151-153`) — body validation runs before the handler
body, so that test never reaches the check. A census of every `403`-bearing assertion in
`tests/` returns 41 sites; none of them targets `/processing-configs/`.

**Evidence** — `src/mkobi/api/routes/processing_configs.py:79-95`:

```python
    try:
        # IDOR protection: verify user has view access to the dashboard
        if not await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=dashboard_id,
            db=db,
            required_permission=DashboardPermission.VIEW,
        ):
            logger.warning(
                "Access denied to processing config: user_id=%s, dashboard_id=%s",
                current_user.id,
                dashboard_id,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="You do not have read access to this dashboard",
            )
```

The same inline shape appears at `:161` (`required_permission=DashboardPermission.EDIT`) and `:246`
(`required_permission=DashboardPermission.EDIT`); `check_dashboard_access` is imported at `:28`.
The admitting side **is** asserted — `tests/test_processing_config_boundary.py:416-419`
(`got = await authenticated_client.get(f"/processing-configs/{dashboard.id}")` /
`assert got.status_code == 200`).

**Consequence** — The declared hard rule "access control is checked on every dashboard request"
(`AGENTS.md` §4) is held for this endpoint family by the code and by nothing in the suite.
Because the check is a statement in the handler body rather than a resolved dependency, it is
invisible to route-shape inspection and to every existing test: deleting the `if not
await check_dashboard_access(...)` block from any one of the three handlers, or inverting the
condition, leaves the whole suite green. The product is correct today — no user is presently able
to read or overwrite another tenant's processing configuration — but the configuration that
becomes readable is the loader/required-columns map, and a regression here is a silent
cross-tenant disclosure that no assertion rejects.

**Recommendation** — Add the missing side to the existing module rather than a new one: one test
per verb that calls the path with a `test_user` holding no grant and asserts
`403` + `ErrorCode.PERMISSION_DENIED`, plus one asserting `GET` for a caller with VIEW is admitted
so the check is not satisfied by always refusing. The larger, non-test change is to move the check
onto `Depends(require_dashboard_read_access)` / `require_dashboard_edit_access` as the other
dashboard routers already do, which makes it structurally un-droppable and lets
`tests/test_router_declarations.py`'s existing operation-enumeration helper prove it for all
operations at once. Cross-reference phase 12 (authorization), which owns the per-request decision;
this finding is only the absence of the test that gates its remediation.

### TEST-102 — The axios 401 refresh-and-replay branch is exercised by no test

**Severity** — HIGH

**Zone** — "What each stand-in removes, and whether any test observes it elsewhere"

**Observation** — `frontend/src/shared/api/axiosInstance.ts:58-147` is a response interceptor that
owns session recovery: the 401 branch decides between inline-handling (`/auth/login`,
`/auth/refresh`), queue-behind-a-refresh, refresh-and-replay, and logout-with-redirect. Across the
30 frontend test files, exactly one imports the real module —
`frontend/src/shared/api/__tests__/errorSurfaces.test.ts:15` — and it installs failure adapters with
statuses 500, 500 and 404 only (`:56`, `:69`, `:88`). `registerRefreshHandler` /
`getRefreshHandler` (`frontend/src/shared/api/refreshHandler.ts:20-28`) are never called from any
test, so the `if (!handler) throw new Error('Refresh handler not registered')` arm at
`axiosInstance.ts:109-111` is also unexercised.

**Evidence** — the untested branch, `frontend/src/shared/api/axiosInstance.ts:91-101`:

```typescript
      // If already refreshing, queue the request
      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        })
          .then((token) => {
            originalConfig.headers.Authorization = `Bearer ${token}`
            return axiosInstance(originalConfig)
          })
          .catch((err) => Promise.reject(err instanceof Error ? err : new Error(String(err))))
      }
```

and the refresh-and-replay tail, `axiosInstance.ts:112-123`:

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
      }
```

**Consequence** — Three concrete defects ship green today. (1) Removing `processQueue({ error:
errorToReject })` at `:119` leaves every request issued during a refresh waiting on a promise that
is never settled — a permanent hang for that tab, with no error and no timeout. (2) Removing
`return axiosInstance(originalConfig)` at `:116` turns every transient 401 into a logout and a
redirect, and the user loses their session mid-task. (3) Any error path that reaches `:122` sets
`window.location.href` — the branch that a user actually experiences when a session expires —
has never executed in a test, so a jsdom navigation throwing, or the toast being emitted twice,
is unobserved. The module is the highest-consequence file in the client tier and it is the only
one with a module-level mutable state machine (`isRefreshing`, `failedQueue`) and no test.

**Recommendation** — Extend the existing harness in
`frontend/src/shared/api/__tests__/errorSurfaces.test.ts`, which already owns the "install a
failing adapter" idiom, with a second describe block that installs a **401** adapter, registers a
`registerRefreshHandler` stub, and asserts three postconditions: the original config is replayed
with the new `Authorization` header; two concurrent 401s produce exactly one `handler()` call and
both requests settle; a rejecting handler rejects both and sets `window.location.href`. No new
file, no new mocking layer.

### TEST-103 — The frontend coverage thresholds are read over 37 of the 66 non-test source files

**Severity** — HIGH

**Zone** — "What a coverage measure can actually see"

**Observation** — `frontend/vite.config.ts:56-65` declares four coverage thresholds and no
`include`, no `exclude` and no `all`. The report it produces therefore covers only the files the
suite imports. The most recent artefact in the working tree,
`frontend/coverage/coverage-final.json` (written 2026-10-05 16:04), contains **37** files; the tree
holds **66** non-test `.ts`/`.tsx` files under `frontend/src`. 29 files are absent from the
measure entirely, and the total over the 37 is 540/732 statements = **73.8 %**, comfortably above
the declared `statements: 50`. Because `Invoke-Check` does chain `Invoke-FeTest`
(`Makefile.ps1:288`), this gate can and does fail a build — it is the only coverage gate in the
project that is actually reachable from the aggregate entry point.

**Evidence** — `frontend/vite.config.ts:56-65`:

```typescript
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      thresholds: {
        statements: 50,
        branches: 40,
        functions: 45,
        lines: 50,
      },
    },
```

Files absent from `coverage-final.json` (derived by comparing the report's key set against a
filesystem walk of `frontend/src`): `app/providers.tsx`, `app/routes.tsx`, `main.tsx`,
`features/admin/api/adminApi.ts`, all six `features/admin/ui/*.tsx` panels, `features/auth/api/authApi.ts`,
`features/dashboards/api/dashboardApi.ts`, `features/dashboards/ui/DashboardList.tsx`,
`features/dashboards/ui/charts/LineChart.tsx`, `features/upload/api/uploadApi.ts`,
`features/upload/ui/UploadModal.tsx`, `features/users/api/userApi.ts`,
`features/users/ui/ChangePasswordPage.tsx`, `features/users/ui/UserProfile.tsx`,
`shared/components/ConfirmDialog.tsx`, `shared/components/NotFound.tsx`,
`shared/components/Layout/{AppLayout,Header,index}.tsx`, `shared/hooks/{useApiError,useConfirmDialog,useDebounce}.ts`,
`shared/types/api.types.ts`, `shared/utils/shortUuid.ts`, `test/setup.ts`.

**Consequence** — A measurement whose effective source selection is narrower than the population it
is read over. 44 % of the client source tree is invisible to the only coverage gate that runs, and
the gate reports 73.8 % while doing so. Concretely: a regression confined to the router
(`app/routes.tsx` — a route that stops rendering, or stops being guarded), to the admin panels
(the entire `RegistrationRequests` / `UserManagement` / `LogViewer` surface, which has **zero**
test files), or to `LineChart.tsx` (the default chart type's renderer) leaves the number unchanged
and `.\Makefile.ps1 check` green. The number currently reads as assurance for a suite that does not
cover the admin tier at all.

**Recommendation** — Set `coverage.all: true` (and an explicit `include: ['src/**/*.{ts,tsx}']` with
the existing `test`/`setup` exclusions) so the four thresholds are read over the population the
number is presented as covering. Expect the thresholds to need re-basing once they are: today's
73.8 % over 37 files will fall once the 29 absent files are counted. Do that in one change, and
re-base the floors in the same commit, so the gate is never red for a reason nobody chose.

### TEST-104 — The pool suite's two contention tests observe neither queueing nor timeout

**Severity** — HIGH

**Zone** — "Decisions the product acts on, and the value of each an assertion would reject"

**Observation** — `tests/test_db_pool.py::TestDbPoolExhaustion` contains the suite's only live
contention tests, and neither of its two contention assertions can fail for the property its test
name states. `test_pool_timeout_on_exhaustion` never makes the pool contend: the "holder" task
signals `first_acquired` and then waits **without issuing a statement**, so no connection is ever
checked out on its behalf — an `AsyncSession` acquires from the pool lazily on first execute.
`test_pool_exhaustion_queued_and_recovers` asserts only a lower bound on elapsed time that both the
queued and the unqueued pool satisfy.

**Evidence** — the never-contended holder, `tests/test_db_pool.py:267-271`:

```python
            async def hold_first_connection() -> None:
                async with async_session_factory():  # noqa: F841
                    first_acquired.set()
                    # Hold until we signal it's OK to finish
                    await can_finish.wait()
```

and the two assertions that close it, `:294-297`:

```python
            # With pool_timeout=1, the second request should succeed after ~wait
            # Since we have pool_timeout=1 and we signal completion before that
            assert second_succeeded, "Second request should have succeeded after waiting"
            assert elapsed_time < 1.0, f"Should not have waited full timeout, waited {elapsed_time}s"
```

The comment's premise is false in this code: `can_finish.set()` is at `:291`, **after** the
measurement at `:288`, so the holder is still holding when the second session asks. The second
session finds the single connection free, succeeds immediately, and the `except
SQLAlchemyTimeoutError: pass` arm at `:285-286` is never entered. The queueing assertion,
`tests/test_db_pool.py:92-97`:

```python
            # With pool_size=2, max_overflow=0, and 3 concurrent requests:
            # - First 2 acquire immediately
            # - Third waits ~0.5s for pool timeout
            # But since we're using NullPool implicitly in tests, adjust expectation
            # Actually the pool should queue and wait for release
            assert elapsed_time >= hold_duration
```

holds at 1.0 s when the pool queues and at 0.5 s when it does not; the two abandoned comment lines
record that the author knew the expectation was undecided. Executed this session:
`pytest tests/test_db_pool.py::TestDbPoolExhaustion` → **`4 passed in 6.21s`**, so both tests are
green while observing neither property.

**Consequence** — The pool is a production resource with three settings the application reads from
config (`pool_size`, `max_overflow`, `pool_timeout`, wired in
`src/mkobi/db/session.py` and already covered by the zero-connection wiring test at
`tests/test_db_pool.py:345-378`). What the *runtime* consequence of those values is — requests
queue and are eventually served, versus requests time out and surface `TimeoutError` to the
caller — has no assertion. A regression that made the pool unbounded (every caller gets its own
connection, exhausting the PostgreSQL `max_connections` and failing the app under load) passes
`elapsed_time >= hold_duration`. A regression that made `pool_timeout` a no-op — callers waiting
forever instead of raising — passes `elapsed_time < 1.0`, because the second request never waits
at all. Both are green today.

**Recommendation** — In `test_pool_timeout_on_exhaustion`, make the holder actually hold: execute
`text("SELECT 1")` **before** `first_acquired.set()`, then assert the second request *does* raise
`SQLAlchemyTimeoutError` and that `elapsed_time >= 1.0`. In
`test_pool_exhaustion_queued_and_recovers`, delete the two abandoned comment lines and assert the
discriminating fact — `assert elapsed_time >= 2 * hold_duration`, or equivalently that
`engine.pool.checkedout()` never exceeded `pool_size` while the tasks ran. Both changes are
inside the existing tests; no fixture or production change is involved.

### TEST-105 — `test_different_ips_have_separate_limits` drives one peer, so the per-peer key decision is unobserved

**Severity** — HIGH

**Zone** — "Decisions the product acts on, and the value of each an assertion would reject"

**Observation** — `tests/test_rate_limiting.py::TestRateLimitingIntegration` has been substantially
rewritten since the prior pass and eight of its tests now assert *which* bound refused a request by
reading the app's own counter. One test kept its old shape. `test_different_ips_have_separate_limits`
exhausts the limit from a single peer, sends a seventh request from that same peer, and asserts one
`429`. The per-peer key derivation — whether the counter namespace includes the client address at
all — is therefore never observed by any assertion.

**Evidence** — `tests/test_rate_limiting.py:445-466`:

```python
        max_attempts = 5

        # Exhaust rate limit for one IP
        for _ in range(max_attempts + 1):
            await async_client.post(
                "/auth/login",
                json={
                    "email": "rate_limit_ip_test@example.com",
                    "password": "wrong_password",
                },
            )

        # Verify first IP is rate limited
        response = await async_client.post(
            "/auth/login",
            json={
                "email": "rate_limit_ip_test@example.com",
                "password": "wrong_password",
            },
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
```

There is no second address anywhere in the body, and the module's own docstring at
`tests/test_rate_limiting.py:429` still reads "Test that rate limits are tracked per IP address."
The rest of the class documents the hazard in its own words —
`tests/test_rate_limiting.py:196-198`: "A test that only checked for a 429 would pass even if the
peer bound had fired, which is exactly the ambiguity that hid the 5/5 defect."

**Consequence** — Collapsing the peer component of the rate-limit key to a constant would leave this
test green — it asserts exactly the `429` that the identifier bound alone produces. The shipped
effect of such a regression is availability, not correctness: every user behind one egress address
(a corporate NAT, a school, a CI runner) shares one 50-request budget, so one user's credential
stuffing locks out everyone else on that address after 50 failures, and one user's 5 failures lock
out a second user behind the same address. The test named for the property would report it covered.

**Recommendation** — Give the test a second peer by swapping the ASGI transport's client, the same
mechanism `test_malformed_peer_does_not_500` already uses at `tests/test_rate_limiting.py:407-416`:
exhaust address A, assert `429`; then set `transport.client = ("198.51.100.7", 12345)`, send one
login for the same identifier, and assert `401`. Two peers, two assertions, one transport
manipulation that the module has already demonstrated. Cross-reference phase 07's plan, which
hands this test to phase 09 by name, and phase 04's rate-limit key work, which must land with it.

### TEST-106 — The error-format module asserts an `or` that accepts the pre-RFC-7807 shape, and its 500 test never issues a 500

**Severity** — MEDIUM

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — `tests/test_error_response_format.py` is the module whose own docstring claims to
verify the error contract across five status classes. Its per-status assertions accept either the
RFC 7807 member or a legacy `error` key, so the shape the RFC 7807 migration replaced is still an
accepted answer. Its 500 test issues a request that returns `404`, and its second assertion
contains a disjunct that can never be true.

**Evidence** — `tests/test_error_response_format.py:1-4`:

```python
"""Contract tests for standardized error response format.

Verifies all error responses conform to the standard ErrorResponse format
across different endpoint categories (400, 401, 403, 404, 500).
"""
```

and the assertion it applies four times, `:29-31`:

```python
        # Verify standard fields exist (RFC 7807 format)
        assert "detail" in body or "error" in body
        assert "code" in body
```

(the same pair appears at `:40`, `:68`, `:99`). The 500 test, `:105-107` and `:127-132`:

```python
        """Internal errors should return structured error without stack traces.

        Tests by verifying that 404 error responses do not contain stack traces.
        """
```

```python
        assert response.status_code == 404
        body = response.json()
        # Verify no stack trace in response
        body_str = str(body).lower()
        assert "traceback" not in body_str
        assert "exception" not in body_str or "exception" in body.get("error", "").lower()
```

An RFC 7807 body carries no `error` key, so `body.get("error", "")` is always `""` and the second
disjunct is always `False` — the assertion reduces to `"exception" not in body_str`.

**Consequence** — The module's self-description is not held by its own assertions. `type`, `title`
and `status` — three of the five members `AGENTS.md` §"Error Handling" names — are never asserted
here. The strict five-member form *is* asserted elsewhere
(`tests/test_layouts.py:369`, `:391`, `:430`, `:498` loop over
`("type", "title", "status", "detail", "code")`), and `tests/test_openapi.py:32`/`:48` assert the
model, so the gap is endpoint coverage and the module's claim, not the model. Two `500` paths *are*
covered at `tests/test_upload_api.py:704-708` and
`tests/test_auth_service.py::TestApproveRegistrationRouteOrdering::test_failed_commit_returns_rfc7807_and_no_credential`,
so the unhandled-exception handler is the uncovered one: a generic `Exception` escaping a route and
being rendered by Starlette's default handler instead of the registered RFC 7807 one would leave
this module green, and it would reach the client as a non-`application/problem+json` body. No test
in the suite asserts the media type — a census of `tests/` for `application/problem+json` returns
zero hits.

**Recommendation** — Tighten the four `"detail" in body or "error" in body` assertions to
`assert "detail" in body` (the legacy `error` shape no longer exists in production —
`src/mkobi/utils/exceptions.py:257-260` emits `response.model_dump()` only), and either rename
`test_500_internal_error_format_no_stack_trace` to what it does or give it a real 500 by making a
handler raise. Add the media-type assertion to whichever of the existing 500 tests is kept. No new
module.

### TEST-107 — `_store_aggregates` builds the `dims`/`metrics` mapping itself and no assertion reads it

**Severity** — MEDIUM

**Zone** — "What each stand-in removes, and whether any test observes it elsewhere"

**Observation** — `_store_aggregates` translates the aggregation service's records into the row
shape the read path consumes, and that translation is its own code. Every unit test of it mocks
`AggregationService`, `StorageManager` and `DashboardFilterValuesRepository` — all three
collaborators — so the record the mock returns is the record under assertion. The one assertion
that touches the translated list asserts its **length**, which is a property of the mock's
configured `return_value`, not of the translation.

**Evidence** — the code under coverage, `src/mkobi/workers/data_worker.py:1218-1222`:

```python
    # Convert records to StorageManager format
    aggregates = [
        {"graph_id": r["graph_id"], "dims": r["dims"], "metrics": r["metrics"]}
        for r in records
    ]
```

and the test, `tests/test_data_worker.py:1213-1222` and `:1250-1257`:

```python
        with patch(
            "mkobi.services.aggregation_service.AggregationService"
        ) as mock_agg_service, patch(
            "mkobi.data.storage.manager.StorageManager"
        ) as mock_storage, patch(
            "mkobi.db.repositories.dashboard_filter_values_repo.DashboardFilterValuesRepository"
        ) as mock_repo:
            mock_service_instance = AsyncMock()
            mock_service_instance.aggregate_for_dashboard = AsyncMock(
                return_value=[{"graph_id": mock_graph.id, "dims": {}, "metrics": {}}]
            )
```

```python
            # Verify save_aggregates called with correct arguments
            save_call = mock_manager_instance.save_aggregates.call_args
            assert save_call is not None, "save_aggregates should have been called"
            assert save_call[1]["dashboard_id"] == dashboard_id, "save_aggregates should receive dashboard_id"
            assert save_call[1]["clear_old"] is True, "OVERWRITE mode should set clear_old=True"
            assert "aggregates" in save_call[1], "save_aggregates should receive aggregates list"
            aggregates_arg = save_call[1]["aggregates"]
            assert len(aggregates_arg) == 1, "aggregates should contain one record"
```

`len(aggregates_arg) == 1` restates `return_value=[{...}]` at `:1222`. No assertion anywhere in
`tests/test_data_worker.py` reads `aggregates_arg[0]["dims"]` or `["metrics"]`.

**Consequence** — The `dims`/`metrics` key names are exactly the contract the recent chart work
changed (`eba2348 fix(charts): serve the stored metric and dimension keys with the aggregate rows`,
`f8581e0 fix(charts): declare the served measure and dimension names on the client graph type`). A
regression that renamed either key, dropped one, or emitted them under `dimensions`/`measures`
would satisfy every assertion in `test_store_aggregates_with_graphs` (`:1244-1257`),
`test_store_aggregates_append_mode` and `test_store_aggregates_concurrent_append` while the rows
written to `aggregated_data` stop matching what the read path serves — charts render empty or with
mismatched axes. The read side is well covered
(`tests/test_aggregated_read_path.py:416-650`); the write side's own translation is not.

**Recommendation** — Keep the mocked collaborators but give the mock a **non-empty, non-round-trip**
payload and assert the translation: seed `aggregate_for_dashboard` with
`{"graph_id": <id>, "dims": {"category": "A"}, "metrics": {"revenue_sum": 7}}` and add
`assert aggregates_arg[0] == {"graph_id": mock_graph.id, "dims": {"category": "A"}, "metrics": {"revenue_sum": 7}}`.
That single equality pins both key names and both values, and it fails on any rename.

### TEST-108 — The harness sweeps and snapshots the developer's real, shared upload staging directory

**Severity** — MEDIUM

**Zone** — "Reproduction: what varies per run, and what a shared resource carries forward"

**Observation** — The suite's temp-file contract is exercised against the production staging
directory, not a per-run one. `UploadSettings.__init__` resolves `temp_dir` to
`platformdirs.user_data_dir("mkobi", "ZOO") / "tmp_uploads"` and nothing in `tests/conftest.py`
overrides it. Two harness sites depend on it: the session-end sweep and one upload test that
snapshots the directory's contents around a request. `docs/06-backend/testing.md:241-247` declares
that a host-side run and a container run may be concurrent, and nothing isolates this directory
between them.

**Evidence** — `src/mkobi/config.py:590-594`:

```python
    def __init__(self, **data: Any) -> None:
        """Initialize with platformdirs temp directory if not provided."""
        if "temp_dir" not in data or not data.get("temp_dir"):
            data["temp_dir"] = str(Path(user_data_dir("mkobi", "ZOO")) / "tmp_uploads")
        super().__init(**data)
```

`tests/conftest.py:154-158`:

```python
        # max_age_hours=0 means delete all files immediately regardless of age.
        # The result is a CleanupResult; read its ``deleted`` count. No ceiling is
        # enforced here (the sweep applies none), so this session cleanup cannot
        # inherit an inherited byte/count limit.
        result = cleanup_stale_temp_files(max_age_hours=0)
```

`tests/test_upload_api.py:691-692` and `:710-713`:

```python
        upload_dir = Path(get_config().upload_temp_dir)
        before = set(upload_dir.glob("*.csv*"))
```

```python
        after = set(upload_dir.glob("*.csv*"))
        assert after == before, (
            f"Orphaned file left in tmp_uploads: {after - before}"
        )
```

The resolved host path, printed with `platformdirs` on this machine, is
`C:\Users\Om\AppData\Local\ZOO\mkobi\tmp_uploads`. Five further modules read the same directory:
`tests/test_e2e_upload.py:132`, `:224`, `:297`, `tests/test_filter_persistence.py:156`, `:289`,
`tests/test_filter_values_consistency.py:157`, `:244`, `tests/test_data_service.py:243`.

**Consequence** — Two effects today, one destructive and one flaky. (1) Every host-side pytest run
deletes every file in the developer's real upload staging directory at session end, with no age
threshold — a staged upload that has not yet been submitted is removed by running the tests.
(2) `test_upload_submission_failure_is_rfc7807` asserts set equality over a directory that a
concurrent host or container run is writing into, so a file the other run stages between `before`
and `after` fails the test with "Orphaned file left in tmp_uploads" — a false failure whose message
names the wrong culprit. The two runs delete each other's staged files as well.

**Recommendation** — Point the harness at a per-run directory: `os.environ.setdefault("UPLOAD__TEMP_DIR",
...)` in `_apply_test_environment()` (`tests/conftest.py:58-83`), derived from `TEST_DB_NAME` so it
is unique per run and per worker exactly as the database name is. The session-end sweep then
touches only files the run created, and `before`/`after` compares a directory no other process
writes to. This is one line in `conftest.py` and one import; no test file changes.

### TEST-109 — `strict_redis` and `mock_redis` describe a rate-limit bypass that no longer exists

**Severity** — MEDIUM

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — All three Redis fixtures and the SSOT describe a distinction the code no longer
makes. `_auto_mock_redis`'s docstring says it patches `AuthService` "to bypass rate limiting by
default"; `strict_redis`'s says "this does NOT patch `check_rate_limit`"; `mock_redis`'s says it
"Applies a patched `AuthService` that always allows login attempts". No fixture patches
`check_rate_limit` and none installs an always-allow limiter — the service-owned limiter was
removed (SECB-2), as the body of `_auto_mock_redis` itself records. `strict_redis` and the autouse
default therefore install the same kind of stand-in and differ only in which `MockRedis` instance
the test is handed.

**Evidence** — the docstring that contradicts its own body, `tests/conftest.py:500-507`:

```python
    """Auto-mock Redis client for all tests to avoid requiring a real Redis server.

    This fixture is always active and patches get_async_redis_client and
    get_redis_client to use an in-memory MockRedis instance. It also
    patches AuthService to bypass rate limiting by default, so existing
    tests don't break. Tests that need real rate limiting behavior should
    use the strict_redis fixture.
    """
```

against the body, `tests/conftest.py:524-527`:

```python
    # The service previously constructed a limiter that no production path read;
    # it has been removed (SECB-2). Route rate limiting is built per request from
    # get_async_redis_client(), which this fixture already mocks, so no AuthService
    # patching is needed to bypass it for ordinary tests.
```

`tests/conftest.py:572-575` (`strict_redis`): "Unlike the default autouse mock, this does NOT patch
check_rate_limit — the AsyncRateLimiter will actually count attempts and block excess requests."
`tests/conftest.py:540-543` (`mock_redis`): "Applies a patched AuthService that always allows login
attempts." A census of `check_rate_limit` across `src/` and `tests/` returns two definitions
(`src/mkobi/core/security.py:75`, `:123`) and nineteen call sites, every one of them a test
exercising the method as the subject — never a patch target. The SSOT repeats the void distinction
at `docs/06-backend/testing.md:99-101`: `_auto_mock_redis` "Auto-mocks Redis for all tests (rate
limiting bypassed)", `mock_redis` "Opt-in Redis mock that bypasses rate limiting", `strict_redis`
"In-memory Redis mock with real rate limiting".

**Consequence** — A maintainer reading the SSOT concludes that rate limiting is bypassed by default
and that `strict_redis` is what makes it real, so the eight integration tests in
`tests/test_rate_limiting.py` that request `strict_redis` look like they are testing something the
default does not. They are not: all eight read the app's own instance instead, as
`tests/test_rate_limiting.py:159-164` records in its own comment — "the `strict_redis` fixture is a
different instance, so popping from it would clear nothing". The parameter is requested and unused
in every one of them. The cost is not a defect shipping today; it is that the harness's own
description of its guarantees is wrong in three places plus the SSOT, which is what makes the next
coverage judgement about rate limiting an uninformed one — and TEST-105 is exactly that judgement.

**Recommendation** — Update the three docstrings and `docs/06-backend/testing.md:99-101` to what the
code does: all three fixtures install an in-memory `MockRedis`; the autouse one is the default and
`strict_redis` exists to hand the test its own instance for seeding and inspection. Then either
drop `strict_redis` from the eight signatures that ignore it, or keep it and say why. Documentation
and comment work, no behaviour change; ask why the parameter is there before removing it.

### TEST-110 — Twenty-four of `test_config.py`'s 123 tests assert on the text of configuration files

**Severity** — MEDIUM

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — A quarter of `tests/test_config.py` reads `docker-compose.yml`,
`docker-compose.override.yml`, `docker/Dockerfile`, `docker/nginx/nginx.conf.template` or
`Makefile.ps1` with `read_text()` and asserts on substrings of the result, using two hand-rolled
parsers whose delimiters are exact-match literals. These tests pass iff the tokens are present in
the file text. The same repository contains a module that states the opposite standard for its own
layer.

**Evidence** — the compose parser, `tests/test_config.py:1618-1633`:

```python
    @staticmethod
    def _service_block(text: str, service: str) -> str:
        """Return one top-level service block from a compose file's text."""
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.rstrip() == f"  {service}:":
                start = index
                break
        assert start is not None, f"{service} service not found"
        block = [lines[start]]
        for line in lines[start + 1:]:
            if line.startswith("  ") and not line.startswith("    ") and line.strip():
                break
            block.append(line)
        return "\n".join(block)
```

and the PowerShell parser, `tests/test_config.py:1707-1719`:

```python
    lines = makefile_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith(f"function {function_name} "):
            start = index
            break
    assert start is not None, f"function {function_name} not found"
    body = [lines[start]]
    for line in lines[start + 1:]:
        body.append(line)
        if line.rstrip() == "}":
            break
    return "\n".join(body)
```

Counted by AST: **24** test functions of **123** in classes in that module call `read_text`/`open`.
Their assertions look like `tests/test_config.py:1684-1685`
(`assert "--no-deps tools " in body` / `assert "--no-deps app " not in body`). The contrast is
stated in the repository itself at `tests/test_router_declarations.py:19-21`: "These tests observe
the generated document and the served behaviour rather than the source text."

**Consequence** — Two failure modes, both live. (1) False failure on a no-op edit: `_service_block`
requires the line to be exactly `  <service>:` and ends a block at any `  `-prefixed non-`    `
line, so re-indenting the override, adding a YAML anchor, or wrapping the compose array across
lines fails the gate with no behavioural change — the class of failure that gets a whole test
deleted. (2) False pass on a real change: these tests read exactly two files. `Invoke-Lint` runs
`docker compose @DevCompose ruff check …` (`Makefile.ps1:262`), where `$DevCompose` is the `-f`
array at `Makefile.ps1:33-35`; appending a third `-f` override that relaxes `read_only` or injects
a credential into `tools` leaves every one of the 24 tests green, because the function body still
contains `--no-deps tools `. `docker compose config` is available in the same environment and would
have resolved the same facts.

**Recommendation** — Keep the intent, change the observation: resolve the compose files with
`docker compose -f docker/docker-compose.yml -f docker/docker-compose.override.yml config` (the
`tools` service already runs with an empty credential set, `Makefile.ps1:254-260`) and assert on the
resolved document; assert on `Makefile.ps1` behaviour by invoking `.\Makefile.ps1` targets in the
test rather than by substring. Do this incrementally — one class at a time, starting with
`TestQualityGateToolsService` — so no single commit has to rewrite 24 tests.

### TEST-111 — Four `pytest.skip` guards in `test_db_pool.py` cannot fire

**Severity** — LOW

**Zone** — "What the harness manufactures by default"

**Observation** — Each of the module's four live-database tests guards itself with
`pytest.skip("TEST_DATABASE_URL not configured")` behind a comparison against `str(...)`, which
never yields `None`. The guard is unreachable in all four places, so the module presents itself as
degrading gracefully when it does not.

**Evidence** — `tests/test_db_pool.py:37-41`:

```python
        config = get_config()
        db_url = str(config.TEST_DATABASE_URL)

        if db_url is None:
            pytest.skip("TEST_DATABASE_URL not configured")
```

The identical three lines appear at `:128-132`, `:187-191` and `:243-247`. The URL is then passed
straight to `create_async_engine(db_url, ...)` (`:47-54`, `:135`, `:194`, `:250-257`).

**Consequence** — No runtime consequence today, because `conftest.py:82-83` assigns
`DATABASE__DBNAME` and `DATABASE__TEST_DBNAME` unconditionally and the URL is therefore always
present. If it were ever absent, `str(None)` yields the four-character string `"None"` and
`create_async_engine` raises `ArgumentError` — a red test whose message names a URL, against four
guards whose stated purpose was to turn exactly that case green. The signal is the defect: a reader
of this module believes it can run without a database.

**Recommendation** — Compare the value, not its stringification: `if not config.TEST_DATABASE_URL:`
before the `str()` call, in all four places, or drop the guards and let the engine raise once.

### TEST-112 — The SSOT's test inventory lists 16 of 89 modules and omits three fixtures

**Severity** — LOW

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — `docs/06-backend/testing.md` is the SSOT for the harness. Its "Test Structure"
tree enumerates the suite, and its fixture table is the inventory a new contributor reads first.
were compiled. Both are stale, while the document's *substantive* claims — per-run database
naming, the SAVEPOINT caveat, the bind-mount note at `:234-239` — hold: the compose file mounts
seven paths and the document names three of them, which understates rather than misstates.

**Evidence** — `docs/06-backend/testing.md:34-53` lists sixteen modules ending at
`test_users_api.py  # User management API tests`. The suite holds **89** modules; the tree contains
none of the contract suites a reader would need to know about — `test_rate_limiting.py`,
`test_file_cleanup.py`, `test_error_response_format.py`, `test_mime_validation.py`,
`test_db_pool.py`, `test_api_layering.py` — and neither of the two subpackages `tests/core/` and
`tests/api/`. The fixture table at `docs/06-backend/testing.md:96-109` omits `mock_db`,
`baseline_data` and `valid_csv_content`, all three of which exist in `tests/conftest.py` (`:713`,
`:703`, `:811`).

**Consequence** — Documentation cost only, but it is the cost this document exists to remove: the
"Coverage Areas" table at `:254-264` and the fixture table together read as a complete picture of
what the suite covers, and a contributor sizing a change would take the sixteen-module list as the
surface. The two subpackages also break the flat `tests/` layout the tree implies, which matters
because `--import-mode=importlib` (`pyproject.toml:196`) is what makes the same basenames safe.

**Recommendation** — Regenerate the tree from the filesystem rather than maintaining it by hand, and
add `mock_db`, `baseline_data` and `valid_csv_content` to the fixture table. Small; do it in the
same change as TEST-109 so the harness description is corrected once.

### TEST-113 — No test holds the "no pandas" rule

**Severity** — LOW

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — "No pandas — Polars only" is a declared hard rule in `AGENTS.md` §3 and in the
base contract. No test anywhere in `tests/` mentions `pandas`. The only trace of the library in the
repository is a stub declaration, which phase 08 has already filed as `TOPO-114`.

**Evidence** — `pyproject.toml:219`:

```toml
    "pandas-stubs==3.0.0.260204",
```

A census of `tests/**/*.py` for the string `pandas` returns **zero** hits. The pattern needed to
hold the rule already exists in the suite, in the same shape, one directory over:
`tests/test_api_layering.py:41-63` walks `src/mkobi/api/routes`, parses each module with `ast`, and
asserts no offender, followed by `tests/test_api_layering.py:86-91` as an anti-vacuity check that
the census never came back empty:

```python
    def test_the_census_covers_every_route_module(self) -> None:
        """Anti-vacuity: fail if the route set ever comes back empty."""
        modules = _route_modules()
        assert len(modules) >= 11, f"route census went empty: {modules}"
        assert any(p.name == "data.py" for p in modules)
        assert any(p.name == "upload.py" for p in modules)
```

**Consequence** — A new runtime dependency on pandas ships undetected: nothing in the suite or in
`Invoke-Lint`/`Invoke-Typecheck` rejects an `import pandas`, so the library is added to the runtime
image and to every container built from `docker/Dockerfile`, against a declared rule, with no gate
reporting anything. Phase 08's `TOPO-114` covers the *stub*; it does not cover the rule.

**Recommendation** — Add the census `tests/test_api_layering.py` already models, over
`src/mkobi/**` rather than the routes directory, asserting no module imports `pandas` and carrying
the same anti-vacuity floor. One test, no fixture, and it makes the rule enforceable rather than
aspirational. Resolve it after `TOPO-114` so the stub and the rule land together.

## Distribution

The findings fall on three surfaces. The **shared harness and its declarations** carry the most:
TEST-108, TEST-109 and TEST-112 all describe `tests/conftest.py` or the SSOT that documents it, and
all three would be closed by one review of what the harness actually installs versus what it says
it installs. The **frontend suite** carries TEST-102, TEST-103 and the largest single uncovered
surface in the project — no test at all for the module that owns session recovery, measured by a
gate that sees 56 % of the source tree. The **backend test assertions themselves** carry the rest:
TEST-101, TEST-104, TEST-105, TEST-106, TEST-107, TEST-110, TEST-111, TEST-113 — eight findings
where the code under test is correct and the assertion is not, which is the shape this phase exists
to find.

- Harness self-description and shared resources: TEST-108, TEST-109, TEST-112 (3)
- Frontend: TEST-102, TEST-103 (2)
- Backend assertion quality: TEST-101, TEST-104, TEST-105, TEST-106, TEST-107, TEST-110, TEST-111, TEST-113 (8)

## Cross-Finding Analysis

Two causes account for nine of the thirteen findings.

**The suite asserts what a stand-in returns, or what a string contains, instead of what the product
does.** TEST-104 (both contention tests), TEST-105 (one peer), TEST-106 (`or` plus a 404 posing as
a 500), TEST-107 (`len()` of a mock's own return value) and TEST-110 (compose and PowerShell text
substrings) are one failure mode at five sites: the assertion is written against the *shape* of the
input it was handed rather than against the value the product produced. Each is individually
fixable by rewriting one assertion, and none requires touching production code.

**A declared contract is written down somewhere and nothing holds it.** TEST-109 (three fixture
docstrings plus the SSOT describe a rate-limit bypass that SECB-2 removed), TEST-112 (the SSOT's
inventory is five modules out of date) and TEST-113 (a hard rule with no census) are the same
pattern at three strengths: a statement with no enforcement. TEST-103 is a fourth member of this
family seen from the gate side — a threshold declared with no statement of what it is read over.

TEST-101 stands alone: it is the only finding where a boundary is genuinely untested on its
refusing side rather than tested weakly, and it is the only one with a cross-tenant disclosure
behind it.

## Roadmap

**Step 1 — close the one-sided authorization boundary (TEST-101).** Nothing else in this plan is
worth doing first: it is the only finding with a cross-tenant consequence, and the two follow-on
options (add the three refusal tests, or move the check onto a dependency) both need the same
review of `src/mkobi/api/routes/processing_configs.py`. **Before starting Step 2:** confirm with
phase 12 that the authorization decision itself is not being changed, because the recommendation's
second half alters where the check lives.

**Step 2 — repair the assertions that cannot fail (TEST-104, TEST-105, TEST-106, TEST-107).** These
are four independent edits across four files with no shared dependency; they can proceed in any
order or in parallel. Grouped here because each one is a shipped assertion encoding "we do not know
what happened", and the batch converts four silent gaps into four real ones. **Before starting
Step 3:** run `.\Makefile.ps1 test-select` on the four modules and confirm the new assertions fail
when the property is inverted — a repaired assertion that cannot be made to fail has replaced one
gap with another.

**Step 3 — make the measures and declarations mean what they say (TEST-103, TEST-109, TEST-112,
TEST-113).** TEST-103 first, because re-basing the frontend floors is the only step that turns a
gate red for a reason nobody chose; do it in one commit and record the new numbers in
`vite.config.ts`. Then TEST-109 and TEST-112 together (one pass over the harness's description),
then TEST-113 once `TOPO-114` lands. **Before starting Step 4:** the frontend gate is green with the
new floors, or the aggregate `Invoke-Check` is red for a reason the team has accepted.

**Step 4 — isolate the shared staging directory (TEST-108).** One `setdefault` in
`_apply_test_environment()`. Deliberately last: it changes the directory every upload test writes
into, so it is cheapest to land once the other changes have stopped moving those tests.

TEST-110 and TEST-111 sit outside the sequence — TEST-110 is a multi-class rewrite best done one
class at a time alongside the deployments it describes, and TEST-111 is a four-line fix to take with
whichever of Steps 2–4 next touches `tests/test_db_pool.py`.

## Rollout Safety

Step 1 is the only step that changes production behaviour, and only under its second option. Moving
the access check from the handler body onto `Depends(require_dashboard_read_access)` /
`require_dashboard_edit_access` changes the order in which the refusal is produced: a request with
both an invalid body *and* no grant would change from `422` to `403`, and
`tests/test_request_boundary_extra_forbid.py:145-153` asserts `422` for exactly that combination
(`PUT /processing-configs/{uuid4()}` with an undeclared key). If that option is taken, that test
must change with it, and `tests/test_openapi.py:72`'s path lookup must be re-checked against the
regenerated document. The refusal code, status and detail are unchanged, so no client contract
moves. Revert is a single-file revert of `processing_configs.py` plus the new tests.

Step 3 turns the frontend coverage gate red. That is the point of the change, but it lands in
`.\Makefile.ps1 check`, which `Makefile.ps1:281-289` chains short-circuit-first, so a red
`fe-lint` will hide a red `fe-test`. Re-baseline the four floors in the same commit as the
`coverage.all` change so the gate is never red for an unchosen reason, and confirm
`frontend/coverage/` stays gitignored (`.gitignore:53`) — the report is a build artefact and must not
re-enter the index.

Steps 2 and 4 change no production code and no assertion other than the ones named. Step 4 is the
one to watch: it moves every upload test's staging directory, so a test that asserts on a *path
string* rather than on a file's presence will need its expectation updated. `tests/test_config.py:401`
(`test_upload_temp_dir_is_absolute_without_env`) constructs its own `Settings(_env_file=None)` and is
unaffected; `tests/test_streaming_size_limit.py` and `tests/test_upload_api.py:280` already override
`upload_temp_dir` to a `tmp_path`. Revert is one line in `tests/conftest.py`.

## Appendices

### A. Declared gates — what is loaded, what is green, what each omits

| Gate | Invoker | Reachable from `Invoke-Check`? | Scope note |
|---|---|---|---|
| `pytest` | `Makefile.ps1:222-230` (`.\Makefile.ps1 test`) | **no** — `CQ-109`, not re-filed | runs in `test-app`, which now bind-mounts `src/`, `tests/`, `docker/`, `pyproject.toml`, `alembic/`, `Makefile.ps1`, `docs` (`docker/docker-compose.test.yml:161-182`) |
| `pytest --cov` | `Makefile.ps1:232-235` (`test-all`) | **no** | the only path where the 65 % floor has a measurement; **CQ-110**, not re-filed |
| `ruff check src/ tests/ alembic/env.py` | `Makefile.ps1:261-263` | yes (first) | runs on `tools`, which mounts the working tree (`docker/docker-compose.override.yml:51-54`); omits `alembic/` except `env.py` |
| `mypy src/ alembic/env.py` | `Makefile.ps1:269-271` | yes | never reaches `tests/`; the `tests.*` override is `CQ-110` |
| `eslint .` | `Makefile.ps1:273-275` | yes | host-native |
| `vitest run --coverage` | `Makefile.ps1:277-279` | yes (last) | the only coverage gate reachable from the aggregate; scope is **TEST-103** |
| `alembic check` | `Makefile.ps1:315-317` | **no** — `CQ-109` | runs against `bidb_test`, never the dev database |

### B. Coverage artefacts and their effective source selection

| Artefact | Configured source selection | Threshold | Population it cannot reach |
|---|---|---|---|
| backend `coverage` | `[tool.coverage.run] source = ["src/mkobi"]` (`pyproject.toml:203`), `omit = ["*/tests/*", "*/migrations/*"]` (`:204` — note `migrations` is not a directory in this repo; `alembic` is) | `fail_under = 65` in **two** places: `addopts` (`:196`) and `[tool.coverage.report]` (`:207`) | none at the module level, but the run only exists on `test-all`; **CQ-110** |
| frontend `coverage` | `provider: 'v8'`, no `include`/`exclude`/`all` (`frontend/vite.config.ts:56-58`) → files the suite imports | 50/40/45/50 (`:59-64`) | 29 of 66 files; enumerated in TEST-103 |

Backend coverage was deliberately not measured: `test-all` runs the full suite, which the
assignment forbids because the test database is shared with concurrent phases.

### C. Derived counts, all by AST walk over `tests/**/*.py`

| Quantity | Value |
|---|---|
| test modules | 89 (87 at `tests/`, 1 each at `tests/core/`, `tests/api/`; no `__init__.py` anywhere) |
| `test_*` functions/methods | 1585 |
| `assert <literal constant>` | **0** |
| `pytest.mark.xfail` | **0** |
| `pytest.skip` / `skipif` | 5, all with a reason (`tests/core/test_temp_password_store.py:317`, `tests/test_db_pool.py:41`, `:132`, `:191`, `:247`) |
| `time.sleep` | **0** (8 `asyncio.sleep`, 6 of them 5 ms or 100 ms pacing in the reconciler-loop tests) |
| functions with no `assert`, `pytest.raises` or mock assertion | 46; 12 are `@pytest.fixture`s misnamed `test_*` (e.g. `tests/test_data_service.py:69`), the rest are "should not raise" smoke tests whose pass/fail is the absence of an exception |
| `tests/` references to `pandas` | 0 |
| `tests/` references to `application/problem+json` | 0 |
| `403` assertion sites in `tests/` | 41, none against `/processing-configs/` |
| frontend test files (any `*.test.*` / `*.spec.*` under `frontend/`) | 30; exactly one imports the real `axiosInstance` |
| `check_rate_limit` occurrences in `src/` + `tests/` | 21 (2 definitions at `src/mkobi/core/security.py:75`, `:123`; 19 test call sites; 0 patch targets) |

### D. Areas examined with no finding

- **`xfail`, `flaky`, retry-as-test, `pytest-rerunfailures`.** None present. No test retries itself
  and no marker stands for one.
- **Assertion on a bare `assert True` / `assert False`.** Zero, by AST over all 1585 test functions.
- **The five-step frontend error-extraction chain.** `frontend/src/shared/api/errorHandler.ts:37-102`
  is covered step by step by `frontend/src/shared/api/__tests__/errorHandler.test.ts`: legacy
  422-without-`code` (`:90-105`), RFC 7807 with `code` (`:6-26`), `title` fallback when `detail` is
  absent (`:28-45`), the `VALIDATION_ERROR` + `errors[]` branch (`:47-70`), the empty-`errors`
  fallback (`:72-88`), the `error.message` fallback (`:107-117`), the generic `Error` branch
  (`:119-126`) and the unknown/null fallbacks (`:128-138`). No gap found.
- **The `async_db_session` durable-commit leak.** `tests/conftest.py:668-680` and its docstring
  state it correctly; `docs/06-backend/testing.md:305-331` documents the compensating pattern; and
  `tests/test_users_api.py:200-249` demonstrates it — it scopes its assertion to its own uuid-suffixed
  rows and restores the foreign admin rows it deletes. The prior pass's residual is remediated.
- **The settings-singleton leak between tests.** Closed by the autouse `_reset_config_cache`
  (`tests/conftest.py:428-463`), which snapshots the environment at setup and restores it at
  teardown, and by `_clear_redis_client_caches` (`:466-484`). A direct `os.environ` write in a test
  body is reverted; a `monkeypatch` change is undone after this fixture runs and lands on the same
  values. No ordering dependence found.
- **`test-app` grading a baked image.** Remediated: `docker/docker-compose.test.yml:161-182`
  bind-mounts `../src`, `../tests`, `../docker`, `../pyproject.toml`, `../alembic`, `../Makefile.ps1`
  and `../docs`, each with a comment naming the test that needs it. `docs/06-backend/testing.md:234-239`
  describes three of the seven and is not wrong, only incomplete.
- **`/frontend/coverage/` tracked in git.** Remediated: `git ls-files frontend/coverage` returns
  empty and `.gitignore:53` carries `/frontend/coverage/`.
- **`slow` / `fast` markers.** Remediated: no `markers` key remains in
  `[tool.pytest.ini_options]`, so `--strict-markers` (`pyproject.toml:196`) has nothing to reject and
  no test is marked.
- **Two-way enum consistency.** Remediated: `tests/test_enum_db_consistency.py:273` compares through
  a `compare_enum_values` helper and `:287-290` asserts the extra-values direction, matching the
  module docstring at `:6`.
- **Temp-file cleanup on failure paths.** Covered from both sides —
  `tests/test_upload_api.py::TestTempFileCleanup` (`:936`, `:1029`, `:1111`),
  `tests/test_file_cleanup.py::TestTempFileCleanupOnProcessingFailure`, and
  `tests/test_streaming_size_limit.py::test_temp_file_cleaned_after_rejection`. No gap found.

### E. Limits on this report

- **The full backend suite was not run**, by instruction: the test database is shared with concurrent
  phases. One module was executed —
  `pytest tests/test_db_pool.py::TestDbPoolExhaustion` → `4 passed in 6.21s` — which is the evidence
  for TEST-104's claim that both tests are green while observing neither property. No claim in this
  report rests on gate-wide redness or greenness.
- **`vitest run --coverage` was not executed**, because it rewrites `frontend/coverage/`. The
  frontend coverage figures come from the artefact already in the working tree
  (`frontend/coverage/coverage-final.json`, mtime 2026-10-05 16:04) and from the configuration. If
  that artefact predates the most recent commits in `git log`, the per-file percentages may be
  slightly stale; the **37-of-66 file-set** comparison was made against the current filesystem walk
  and is not affected.
- **No claim is made about pass/fail counts for the suite as a whole.** The prior pass's figures are
  stale (the tree has moved ~30 commits since `cea2d06`), and this phase had no reason to
  re-establish them.
- **`tests/core/` and `tests/api/` hold no `__init__.py`.** With `--import-mode=importlib`
  (`pyproject.toml:196`) this is safe today and no basename collision exists across the 89 modules,
  but it is an untested assumption rather than an enforced one. Recorded as an observation, not a
  finding, because no defect follows from it as things stand.
- **No scratch files were written.** The environment denies writes outside the repository, so every
  census in Appendix C was produced by piping a script to `uv run python -` on stdin. Nothing
  remains to clean up; this findings file is the only file this audit created.
