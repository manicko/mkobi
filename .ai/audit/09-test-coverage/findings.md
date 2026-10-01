---
phase: 09-test-coverage
executed: 2026-09-30
executor: auditor
problems-only: true
baseline: b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd
baseline-dirty: "true (20 deleted .ai files, 9 untracked .ai/audit + .ai/plans paths; no tracked source or test file modified)"
findings: 18
by-severity:
  CRITICAL: 2
  HIGH: 7
  MEDIUM: 7
  LOW: 2
---

# Phase 09 — Test Coverage

## Summary

Both suites were executed in this environment: 1013 backend tests in the `mkobi-test`
Docker project (`.\Makefile.ps1 test`) and 170 frontend tests (`npm run test`, vitest 4.1.7
with `--coverage`). The single most consequential thing found is that the backend gate
executes a Docker image snapshot rather than the working tree — `docker/docker-compose.test.yml`
gives `test-app` no bind mount while `docker/docker-compose.override.yml:99-103` mounts
`../src` and `../tests` for the dev `app` — so a change to `src/` can land on a green run that
never executed it. Compounding it, nothing in the repository invokes any gate: there is no
`.github/` directory, `Makefile.ps1 check` chains ruff, mypy, eslint and vitest but never
pytest, and both suites are **red right now** (5 backend failures in
`tests/test_auth.py::TestRateLimiting`, 1 frontend failure in `formSchemas.test.ts`). Coverage
is not the safety net it appears to be on either side: the backend `--cov-fail-under=65` has no
`--cov` to act on, and the frontend thresholds are computed over an import-driven population
and are suppressed entirely while the suite is red. Eighteen defects follow, four of which are
named as remediation blockers against findings already filed by other phases rather than
re-filed here.

## Findings

### TST-001 — the backend gate tests a baked image, not the working tree

**Severity** — CRITICAL

**Zone** — "What runs before a change lands, and what each gate's scope excludes"

**Observation** — `docker/docker-compose.test.yml` defines `test-app` (`:123-167`) with a
`build:` block and an `environment:` block and **no `volumes:` key at all**. The `test` stage of
`docker/Dockerfile:132-151` bakes the product in at build time (`COPY src/ ./src/` at `:135`,
`COPY tests/ ./tests/` at `:139`). Every test-invoking target in `Makefile.ps1` runs
`docker compose @TestCompose run --rm --no-deps test-app pytest …` (`:196`, `:201`, `:210`)
with no `--build`. The dev `app` service does the opposite: `docker-compose.override.yml:97-103`
binds `../src:/app/src`, `../alembic:/app/alembic` and `../tests:/app/tests`. The suite that
gates changes therefore reads `/app/src` from the image layer, while the running application
reads the mounted host directory. They are two different copies of the product and only one of
them is tested.

**Evidence** — Runtime, in this environment: `docker images` reports
`mkobi-test-test-app … 3a77fb234217 … CREATED 2026-09-30 15:33:38 +0200`, while
`git log -1 --format=%cd --date=iso -- src/` gives `b23a9cb 2026-09-30 15:40:39` — the image
predates HEAD by seven minutes, and `git show --stat b23a9cb` lists `src/mkobi/config.py`
(+118/-…) and `src/mkobi/app.py` among the files that commit changed. `md5sum
/app/src/mkobi/config.py` inside `test-app` and `Get-FileHash src/mkobi/config.py` on the host
both return `99218e341525b1f73ba658c66c9a8e51`, so the two copies agree **today only because a
concurrent remediation programme had already written the file before the image was built**, not
because anything in the test path re-reads the working tree. A full `find` diff of the two
`src` trees returns 115 files on each side with zero differences — a coincidence of timing, not
a property of the harness.

**Consequence** — `.\Makefile.ps1 test`, `test-all` and `test-select` are green or red about the
code as of the last `docker compose build`. A change to `src/mkobi/**` that has not been
rebuilt is not tested at all, and the result is indistinguishable from a run that tested it: the
same green terminal output, the same 1013 collected tests, the same `1013 items`. The window is
not hypothetical — it is exactly the window this audit was executed in.

**Recommendation** — Add `- ../src:/app/src` and `- ../tests:/app/tests` to the `test-app`
service, matching what `docker-compose.override.yml` already does for `app`. That removes the
rebuild step from the inner loop entirely and makes the gate read the same bytes the developer
just wrote. If a bind mount is rejected because `libmagic`/`pyo3` binaries in the image would be
shadowed, mount only `src` and `tests` (not the whole app root) and add `--build` to the three
test targets as the interim fix — but note that `--build` alone still leaves a stale-image
window between builds, so the mount is the fix and the flag is the mitigation.

### TST-002 — no gate is invoked by anything, the aggregate target omits the backend test tree, and both suites are red

**Severity** — CRITICAL

**Zone** — "What runs before a change lands, and what each gate's scope excludes"

**Observation** — Three distinct absences, told apart. (a) *Declared and never loaded:* the
repository contains no `.github/` directory, no workflow file, no pre-commit hook, no
`tox.ini`, `noxfile.py`, or `.pre-commit-config.yaml`; `Get-ChildItem .github -Recurse` returns
nothing. Every gate is an entry point a person must choose to run. (b) *The aggregate entry
point omits a whole process tree:* `Makefile.ps1:241-249` defines `check` as
`Invoke-Lint` → `Invoke-Typecheck` → `Invoke-FeLint` → `Invoke-FeTest` and calls nothing else.
`Invoke-Test` (`:194-197`) and `Invoke-TestAll` (`:199-202`) are never reached from `check`, so
the 1013-test backend suite is outside the scope of the one target the help text at `:81`
describes as "Aggregate gate". (c) *Loaded and red:* both suites fail today.

**Evidence** — Runtime. `.\Makefile.ps1 test` → `collected 1013 items`, finishing
`10 failed, 1003 passed, 23 warnings in 309.23s (0:05:09)`. The ten are
`tests/test_auth.py::TestRateLimiting::{test_rate_limiter_allows_under_limit,
test_rate_limiter_blocks_over_limit, test_rate_limiter_fail_open_on_redis_error,
test_rate_limiter_fail_closed_on_redis_error, test_rate_limiter_different_ips_independent}`,
`tests/test_layouts.py::TestLayoutsAPI::{test_create_layout_missing_name_returns_422,
test_create_layout_missing_definition_returns_422, test_create_layout_duplicate_name_returns_400}`,
`tests/test_pydantic_models.py::TestUserModels::test_user_db_valid` and
`tests/test_rate_limiting.py::TestRateLimitingIntegration::test_rate_limit_reset_allow_writes`.
`npm run test` in `frontend/` → `Test Files 1 failed | 12 passed (13)`,
`Tests 1 failed | 169 passed (170)`, the failure being
`src/shared/types/__tests__/formSchemas.test.ts > changePasswordSchema > accepts matching
passwords`, `AssertionError: expected false to be true` at `:162`. Every one of the eleven is
diagnosed in TST-005, TST-010, TST-011, TST-013 or TST-015.

**Consequence** — Nothing in this repository can prevent a change from landing. The two red
failures are not blocking anything, were not blocking anything when this phase started, and
carry no signal beyond having been read once. A reader of `Makefile.ps1 help` sees
`check — Aggregate gate: lint + typecheck + fe-lint + fe-test` and can reasonably conclude the
suite is covered; the backend suite is not in that list and is not in any other automation.

**Recommendation** — Three separate changes. First, add the backend suite to `Invoke-Check`
(call `Invoke-Test` after `Invoke-Typecheck`; the Docker services are already up by then
because `Invoke-Test` starts them itself). Second, decide what CI is and wire `check` plus
`test-all` to it — a single GitHub Actions workflow running
`test-up && test-all` on the backend and `npm ci && npm run test` on the frontend is enough;
nothing more elaborate is warranted at this size. Third, resolve the 6 red tests as part of that
work, because a gate that is red on day one is a gate that gets disabled. Do not silence them
by relaxing the assertions: TST-013 explains why one of them is red.

### TST-003 — the backend coverage threshold has no measurement to act on

**Severity** — HIGH

**Zone** — "What a coverage measure can actually see"

**Observation** — `pyproject.toml:196` sets
`addopts = "--import-mode=importlib -ra -v --strict-markers --cov-fail-under=65"`. There is no
`--cov` and no `--cov=<path>` in `addopts`, and `pytest-cov` documents `--cov-fail-under` as
having no effect unless `--cov` is also given. `Makefile.ps1:196` — the target the help text at
`:69` calls the "Default gate" — runs bare `pytest`, so the option is inert on the default path.
Only `Invoke-TestAll` (`:201`) adds `--cov=src/mkobi`. Independently, `[tool.coverage.report]
fail_under = 65` (`:212`) restates the same number as a literal in a second file, unbound to
the value it is meant to hold: changing `addopts` alone leaves `fail_under = 65` in force under
a `coverage report` invocation, and changing `pyproject` alone leaves the command line at 65.

**Evidence** — The 1013-test run in this environment emitted no coverage table and no
threshold verdict, despite `--cov-fail-under=65` being present in `addopts` and pytest-cov 7.1.0
being loaded (the run header lists `plugins: xdist-3.8.0, asyncio-1.4.0, cov-7.1.0, anyio-4.13.0,
mock-3.15.1`). `test-all` was not run concurrently with it and so is not characterised here; what
is established is that the default gate measures nothing.

**Consequence** — `.\Makefile.ps1 test` reports a verdict that carries no information about how
much of the product was executed, and the coverage floor that appears in `pyproject.toml` has
never gated a run by default. Anyone reading the file reasonably believes a 65% floor is
enforced. It is not.

**Recommendation** — Add `--cov=src/mkobi` to `addopts` so every pytest invocation is measured,
and delete the duplicated `fail_under` from `addopts`, leaving the single bound value in
`[tool.coverage.report]`. One number, one place. If the floor is meant to be per-module rather
than whole-project, say so in a comment — the current single number is a whole-project floor and
nothing documents that.

### TST-004 — the frontend coverage thresholds measure an import-driven population, and are suppressed entirely while the suite is red

**Severity** — HIGH

**Zone** — "What a coverage measure can actually see"

**Observation** — `frontend/vite.config.ts:56-65` configures `coverage.provider: 'v8'` and four
thresholds (statements 50, branches 40, functions 45, lines 50) with **no `coverage.include`**.
With the v8 provider and no include list, the measured population is whatever the executed tests
happened to import, not the source tree. `frontend/package.json:9` runs
`vitest run --coverage`, and `Makefile.ps1:237-238` (`Invoke-FeTest`) is the last link of
`Invoke-Check`, so this is the only coverage measure the project produces on the client.

**Evidence** — Runtime, two runs in `frontend/`. Running one green file,
`npx vitest run --coverage src/shared/types/__tests__/enums.test.ts`, reports
`Statements : 100% ( 9/9 )`, `Branches : 100% ( 0/0 )`, `Functions : 100% ( 0/0 )`,
`Lines : 100% ( 9/9 )` — **nine statements for the entire project**, because nine statements were
imported. The four thresholds pass against that denominator. Running the full suite,
`npx vitest run --coverage` → `Tests 1 failed | 169 passed (170)`, produces **no coverage table
and no threshold verdict at all**; the same is true of a two-file run mixing one green file with
the red one. A green-only run exits 0 and does print the report.

**Consequence** — Two compounding effects. First, the denominator is whatever the tests import,
so adding a feature no test imports lowers coverage not at all, and adding a test that imports
one more module raises the denominator without the feature being covered. A threshold over that
population is not a project floor. Second, and more urgent today: vitest emits the coverage
report **only when the suite is fully green**, and the suite is not green — so `fe-test` verifies
no coverage whatsoever right now, and the tracked `frontend/coverage/` HTML report is deleted by
the same run (see TST-014).

**Recommendation** — Set `coverage.include: ['src/**/*.{ts,tsx}']` so the denominator is the
source tree rather than the import graph, and move the reporter output to a step that always
runs. The population the measure cannot reach — `src/main.tsx`, every route module, every API
client, every MUI wrapper — is the honest answer to "what is not covered", and it is currently
invisible rather than reported as zero.

### TST-005 — the rate-limit integration tests exhaust a counter on a store they cannot reach, and one of them is red for that reason

**Severity** — HIGH

**Zone** — "What each stand-in removes, and whether any test observes it elsewhere"

**Observation** — The autouse `_auto_mock_redis` fixture creates one `MockRedis` and patches
`get_async_redis_client` / `get_redis_client` to return it (`tests/conftest.py:308-319`). The
`async_client` fixture creates a **second, independent** `MockRedis` (`:546`), overrides
`get_redis_client_dependency` with it (`:547-549`) and stashes it on `app.state.mock_redis`
(`:557`). Production code that reaches Redis through `get_async_redis_client()` sees the first
store; a route that reaches it through the FastAPI dependency sees the second. The two never
share a key. All four integration tests in `tests/test_rate_limiting.py::TestRateLimitingIntegration`
declare the `strict_redis` fixture (`:16`, `:75`, `:107`, `:155`), which binds
`get_async_redis_client` to *its own* third `MockRedis` (`:380`, `:388`) — a store the HTTP path
does not use. The three unit tests in the same file's `TestAsyncRateLimiterUnit` (`:199`, `:212`,
`:230`) construct `AsyncRateLimiter(strict_redis)` directly, so they are unaffected.

**Evidence** — Runtime, from the 1013-test run. `tests/test_rate_limiting.py:138-139` clears
`strict_redis._data.pop("login:127.0.0.1", None)` and `strict_redis._ttls.pop(...)`, then
asserts 401 and gets:
`AssertionError: Request should succeed after reset, got 429 / assert 429 == 401`
(`tests/test_rate_limiting.py:150`). The counter the route incremented is on
`app.state.mock_redis`, not on `strict_redis`, so the pop is a no-op and the rate limit is still
exhausted. The two sibling tests in the same class — `test_login_rate_limit_exceeded` (`:15`)
and `test_different_ips_have_separate_limits` (`:154`) — pass, because they only assert that a
429 occurs, and a 429 does occur, on the other store.

**Consequence** — Three tests named as integration coverage of the login rate limit are green
without ever touching the store whose contents they claim to verify, and the fourth is red
precisely because it is the only one that tried. A developer reading the class sees a passing
rate-limit integration suite and a flaky-looking reset test; the truth is that the integration
path is unobserved and the one real observation is failing.

**Recommendation** — Make the `strict_redis` and `async_client` fixtures resolve to the *same*
`MockRedis` instance per test, by having `async_client`'s `override_get_redis` return the
autouse instance rather than constructing a new one. That single change makes the three passing
tests meaningful and is a precondition for fixing the fourth. Do not "fix" the red test by
relaxing the assertion — the 429 is correct given the store it is reading; the store is wrong.

### TST-006 — the rate-limit key the tests hard-code is a client identity no production request can present

**Severity** — HIGH

**Zone** — "Each boundary, from each side — including the ones every test crosses the same way"

**Observation** — `tests/test_rate_limiting.py:124` sets `rate_limit_key = "login:127.0.0.1"`
and pops that literal at `:138-139`. The `"127.0.0.1"` component is the `request.client.host`
that httpx's `ASGITransport` manufactures in-process; it is not a value any deployed request can
present. In the shipped topology nginx (`docker/nginx/nginx.conf:35-39`) proxies to the app and
sets `X-Real-IP` and `X-Forwarded-For`, while `docker/Dockerfile:179` starts
`uvicorn … --workers 4` with no `--proxy-headers` argument and no `FORWARDED_ALLOW_IPS` in any
compose file or env file in the repository.

**Evidence** — Runtime, in the test image:
`uvicorn 0.49.0`, `Config.__init__` reports `proxy_headers: bool = True` and
`forwarded_allow_ips: list[str] | str | None = None`, and the constructor body contains
`self.forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")`, wired as
`ProxyHeadersMiddleware(self.loaded_app, trusted_hosts=self.forwarded_allow_ips)`. A
`Select-String` for `FORWARDED_ALLOW_IPS` across `docker/*.yml`, `docker/Dockerfile`,
`docker/Dockerfile.frontend.dev`, `.env`, `.env.example`, `.env.docker` and `docker/.env.*`
returns no match. nginx runs in a separate container, so its source address is a bridge-network
address and is never `127.0.0.1`; the forwarded headers are therefore never trusted.

**Consequence** — In production, `request.client.host` is the nginx container's address for
every request from every user, so the login rate limit is one global counter for the whole
installation. That production defect is **AUTH-001** and is not re-filed here. What is this
phase's to name is the test side: the suite binds itself to a key value that only the harness
can produce, so it can neither observe the production key nor detect the change that fixes
AUTH-001. `tests/test_rate_limiting.py` is a **remediation blocker for AUTH-001** — it must be
rewritten to obtain the key from the code under test (assert on the limiter's own bookkeeping,
or drive two distinguishable client addresses through `ASGITransport`) rather than from a
literal, and it will otherwise go red the moment AUTH-001 is fixed.

**Recommendation** — Replace the literal with a key derived from the same expression production
uses, or better, delete the manual reset step and assert the reset through a public seam. Then
add the test the class is named for and does not have: two distinct client addresses through
`ASGITransport`, asserting the counters are independent. `test_different_ips_have_separate_limits`
(`:154-193`) contains no second IP and no second key; it is a duplicate of
`test_login_rate_limit_exceeded` and would pass unchanged if the limiter were keyed on a single
global constant.

### TST-007 — every shipped worker test injects the session that makes TOPO-001's compensating write unreachable

**Severity** — HIGH

**Zone** — "Decisions the product acts on, and the value of each an assertion would reject"

**Observation** — `workers/data_worker.py:552` branches on `if db_session is not None:`. The
`True` branch (`:554-581`) updates the log to `FAILED` inside the caller's transaction and
re-raises. The `else` branch (`:582-620`) creates its own session, and its FAILED write at
`:608-614` sits after a `raise` at `:603` that the enclosing `async with session.begin()` block
re-raises out of — so the compensating write cannot run on either path. **TOPO-001** owns the
defect; it is not re-filed. Every shipped test passes a session: `tests/test_data_worker.py:174,
188, 200, 217, 230` pass an `AsyncMock`, and the `_store_aggregates` tests in the same file pass
one too. No test anywhere calls `process_csv_background` without `db_session`.

**Evidence** — The `else` branch at `:582-620` is the only code that would exercise
`get_session()` at `:584` and the independent FAILED write at `:608`, and no test reaches it.
The same shape appears in `cleanup_stale_processing_logs` (`:254` vs `:269`) and
`mark_orphaned_uploaded_logs_failed` (`:314` vs `:330`), where the two branches build identical
SQL and differ only in session ownership — so the transaction-management half of both sweeps is
also unobserved, though that is a smaller gap.

**Consequence** — The suite cannot fail on TOPO-001, and it cannot pass on TOPO-001's fix
either: no test exercises the production branch, so the change that makes the compensating write
reachable would land with a green suite whether or not it worked. `tests/test_data_worker.py` is
a **remediation blocker for TOPO-001** in the specific sense that the fix needs a test that
calls the worker without a session, and no such test can be written against the current
signature without also changing what "test mode" means.

**Recommendation** — Add one test per recovery function that calls it with `session=None`
against a real database and asserts a planted stale row becomes `FAILED` in a session the caller
does not own. That is the only shape that observes `get_session()` and `session.begin()`. Keep
the existing session-passing tests for the WHERE/values logic, which they do cover.

### TST-008 — the HTTP fixture substitutes the test's own session for the product's, so commit, rollback and teardown are never under test

**Severity** — HIGH

**Zone** — "Each boundary, from each side — including the ones every test crosses the same way"

**Observation** — `tests/conftest.py:540-543` overrides `get_db_dependency` with a generator that
yields the test's `async_db_session`, and `:559` builds the client over
`httpx.ASGITransport(app=app)`. Two boundaries are crossed in process rather than as the product
crosses them. The session boundary: `api/deps.py`'s `get_db_dependency` and
`db/session.py`'s `get_async_sessionlocal()` are replaced, so the request-scoped session, its
`begin`/`commit`/`rollback` and its `dispose` on generator exit are the fixture's business.
`tests/test_deps.py:TestGetDbDependency` does assert the real generator yields a usable session,
which is worth crediting, but it does so outside any request. The transport boundary: no socket,
no TLS, no HTTP/1.1 framing, no `X-Forwarded-*` handling — which is what makes TST-006's
`127.0.0.1` fiction reachable in the first place.

**Evidence** — `conftest.py:559` is the `ASGITransport` construction; the phase input cites this
line as the reason `recreate_test_database`'s destructive branch and the startup preconditions are
never exercised (**TOPO-004**, already validated and not re-filed). The lifespan is bypassed, so
`app.py`'s `starter.startup()`, `mark_orphaned_uploaded_logs_failed()` and
`start_stale_processing_cleanup_task` are absent from every test.

**Consequence** — **TXN-001** (sessions yielded without commit/rollback, three of four
`UserService` writes never commit) is invisible to every API test, because in the harness the
route's writes land in a session the test then rolls back. The two cross-test DELETEs in
`tests/test_processing_logs.py:332-337` and `:397-402` exist to compensate for the same thing and
are themselves order-sensitive (TST-012). Every test in the suite shares one persistence
session with the code under test; the product's own transactional lifetime is asserted from no
side at all.

**Recommendation** — Keep the override — it is what makes 1000 fast integration tests possible —
and add a small number of tests that exercise the real `get_db_dependency` through
`httpx.ASGITransport` without the override, asserting that a request's writes are visible to a
second, independent session after the response and that an exception mid-request leaves no
partial state. Four or five such tests would close the transaction boundary without slowing the
suite.

### TST-009 — three whole service modules are asserted only against a mock session that absorbs every constraint

**Severity** — HIGH

**Zone** — "What the harness manufactures by default: identity, store, schema, environment"

**Observation** — `conftest.py:510-519` defines `mock_db` as `AsyncMock(spec=AsyncSession)`. It
is the sole database collaborator for 61 of the 76 tests in `tests/test_auth_service.py` (28 of
42), `tests/test_graph_service.py` (16 of 17) and `tests/test_layout_service.py` (17 of 17).
`spec=AsyncSession` makes the call signature legal and every call a no-op returning a
`MagicMock`, so no SQL is issued, no constraint is evaluated and no row is ever written. The
assertions that follow are about plumbing: `test_graph_service.py:67` asserts
`call_args[0][0] is mock_db`, `:75` asserts `mock_db.commit.assert_called_once()`,
`test_auth_service.py:478` the same for `reset_password_admin`, and `:574` asserts
`mock_db.commit.assert_not_called()`.

**Evidence** — A `Select-String` for `def test_.*\bmock_db\b` over the three files returns 61
matches; `conftest.py:511` is the only definition and no other module consumes the fixture.
`test_auth_service.py` is the *only* module in the suite that asserts `AuthService` behaviour,
and 28 of its 42 tests run against a session that cannot fail.

**Consequence** — `AuthService` — the component behind login, registration, temp-password
reset and password change — is asserted from one side only. A wrong column name, a wrong `WHERE`
clause, a missing `ON CONFLICT`, or a commit placed on the wrong side of a branch passes all 28
tests. The suite's apparent density on the auth path is largely density on argument forwarding.

**Recommendation** — Convert the highest-value subset — registration, login, and
`reset_password_admin` — to the real `async_db_session` fixture. Those are the three paths with
persistence semantics worth asserting, and the integration tests that already exist for them
(`tests/test_auth_api.py`, `tests/test_registration_flow.py`) show the pattern is available.
Leave the remainder on `mock_db`; a mock session is the right tool for "does this method call
its repository with these arguments", and that is a real question worth answering cheaply.

### TST-010 — five shipped rate-limiter tests assert a scalar against an API that returns a tuple

**Severity** — MEDIUM

**Zone** — "Decisions the product acts on, and the value of each an assertion would reject"

**Observation** — `AsyncRateLimiter.check_rate_limit` returns `tuple[bool, int | None]`
(`src/mkobi/core/security.py:111-113`). All five tests in `tests/test_auth.py::TestRateLimiting`
assert the bare scalar: `:277-278` and `:290-291` write `result = await limiter.check_rate_limit(...)`
followed by `assert result is True`, and `:294-295`, `:368-369` and `:387-392` do the same.
`tests/test_rate_limiting.py:199-243` and `tests/test_rate_limiting.py` get it right
(`allowed, retry_after = await limiter.check_rate_limit(...)`), which shows the tuple contract is
known to the suite.

**Evidence** — Runtime. All five fail on their first assertion with
`AssertionError: Attempt 1 should be allowed / assert (True, None) is True` at
`tests/test_auth.py:278`. The limiter returned the correct value; the assertion was written
against a signature the method no longer has.

**Consequence** — The rate limiter has **zero** effective backend coverage today: all five of its
unit tests abort on the first line of their loop and never reach the over-limit, fail-open,
fail-closed or per-key assertions those tests exist to make. The behaviour those four tests were
written to pin — over-limit blocking, the `fail_closed` switch, per-key isolation — is currently
unasserted anywhere in the backend suite. Note the *intent* behind two of them: `:298-332`
(`test_rate_limiter_fail_open_on_redis_error`) and `:334-369`
(`test_rate_limiter_fail_closed_on_redis_error`) encode the fail-open default as intended
behaviour, which is **AUTH-002**'s territory and not re-filed here.

**Recommendation** — Unpack the tuple: `allowed, retry_after = await …` and assert on `allowed`.
Five one-line edits turn five red tests into five real ones. Do this before adding CI (TST-002),
because a gate introduced red will be the first thing someone disables.

### TST-011 — three shipped layout tests assert the legacy 422 format the project forbids

**Severity** — MEDIUM

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — `AGENTS.md` mandates RFC 7807 Problem Details for all API errors and lists
"Do NOT return non-RFC 7807 error responses" as forbidden; `docs/08-security/error-format.md`
and `src/mkobi/utils/exceptions.py` implement it. Three tests in
`tests/test_layouts.py::TestLayoutsAPI` assert the FastAPI legacy shape instead:
`test_create_layout_missing_name_returns_422` and
`test_create_layout_missing_definition_returns_422` do
`errors = data["detail"]; assert isinstance(errors, list)` (`:365-367`), and
`test_create_layout_duplicate_name_returns_400` makes the same assumption about the conflict
path.

**Evidence** — Runtime. Both 422 tests fail with
`AssertionError: assert False / + where False = isinstance('Request validation failed', list)`
— the server returns `"detail": "Request validation failed"`, the mandated string form, and the
test demands the forbidden array form.

**Consequence** — Three tests currently reject the behaviour the project mandates. Left as-is
they are a standing instruction to remove RFC 7807 from the validation path. The rest of the suite
reads the RFC 7807 shape correctly — `tests/test_error_response_format.py`,
`tests/test_rate_limiting.py:70-72` — so these three are the outliers, not the convention.

**Recommendation** — Rewrite the three assertions against the RFC 7807 body: assert
`data["code"]` is a member of `ErrorCode`, that `type`, `title`, `status` and `detail` are
present, and that `status` is 422. This is the "fix the test, not the code" case AGENTS.md
anticipates, and the test is what is wrong.

### TST-012 — `async_db_session.commit()` commits for real, so test data outlives the test

**Severity** — MEDIUM

**Zone** — "Reproduction: what varies per run, and what a shared resource carries forward"

**Observation** — `conftest.py:468-497` documents the fixture as "Starts a SAVEPOINT before
each test … Automatically rolls back the SAVEPOINT at the end … No TRUNCATE needed". The
implementation opens a nested transaction (`:491`) and rolls back in `finally` (`:496`). But the
root transaction is auto-begun, and SQLAlchemy's `Session.commit()` commits the **root**, not
the savepoint — so every `await async_db_session.commit()` in a test releases the savepoint and
`COMMIT`s to PostgreSQL. The `after_transaction_end` listener (`:484-488`) then opens a fresh
savepoint, and the teardown rollback discards only what came after the last commit. The fixture's
own `test_user` does it (`conftest.py:590`), and so do the tests: `tests/test_rate_limiting.py:31`,
`tests/test_permissions.py:72`, and dozens more.

**Evidence** — Static proof from the fixture body plus the tests' own compensating measures.
`tests/test_processing_logs.py:330-338` opens with a comment reading "Clean up any existing
PROCESSING logs … for test isolation" and issues
`delete(ProcessingLog).where(status == PROCESSING, dashboard_id.is_(None))` followed by
`commit()`; `tests/test_processing_logs.py:394-403` issues a broader
`delete(ProcessingLog).where(status == PROCESSING, started_at < now - 1min)` with no
`dashboard_id` filter. Neither is a rollback; both are manual cleanups for data a previous test
committed. `test_cleanup_no_stale_entries` deletes rows it did not create, across every dashboard
in the database.

**Consequence** — State accumulates in `bidb_test` for the whole pytest session and persists into
the next invocation in the same volume — `.\Makefile.ps1 test` twice in a row is not the second
run against a clean database. `test_cleanup_no_stale_entries` is a test that depends on being
early: whether it sees 0 stale rows depends on what ran before it, so its result is a function
of collection order, and under `pytest-xdist` (`pytest-xdist>=3.0.0` is in the dev group and
`PYTEST_XDIST_WORKER` is handled at `conftest.py:143-152`) the partition decides. Under a
different `-n` or a different distribution algorithm the count it asserts can change.

**Recommendation** — Either wrap each test in a real outer transaction and roll *that* back
(`connection.begin()` with the session bound to it, so `Session.commit()` nests instead of
committing — SQLAlchemy's "join an external transaction" recipe), or drop the rollback claim from
the docstring and add an explicit per-module `TRUNCATE … RESTART IDENTITY CASCADE` where a test
needs a known-empty table. The first is the better fix and makes the two cross-test DELETEs
unnecessary; the second is honest and cheaper. Do not leave the docstring describing behaviour the
fixture does not have.

### TST-013 — one test's config mutation leaks into every test that follows it in the same worker

**Severity** — MEDIUM

**Zone** — "Reproduction: what varies per run, and what a shared resource carries forward"

**Observation** — `tests/test_rq_worker.py:148-165` monkeypatches eleven environment variables
(`REDIS__HOST=confighost`, `REDIS__PORT=6380`, `REDIS__DB=1`, `ENV=test`, five `DATABASE__*`,
`JWT__SECRET_KEY=test_secret_key_for_testing_32_chars`, `DATABASE__TEST_DBNAME`) and then calls
`mkobi.config.clear_config_cache()` at `:163-164`. `get_config()` memoises into the module
global `_settings` and is repopulated on the next call from `os.environ`. `monkeypatch` restores
`os.environ` at teardown, but **nothing clears the config cache afterwards**, so the rebuilt
`Settings` object — carrying `confighost`, port 6380 and a different JWT secret — remains the
singleton for every subsequent test in that worker. `tests/test_cors.py:19-24` performs the same
`setdefault` + `clear_config_cache()` sequence in a fixture, and `tests/test_config.py:30-70`
hand-rolls its own env save/restore around a `clear_config_cache()`.

**Evidence** — Static proof: `src/mkobi/config.py` `get_config(*, reload: bool = False)` sets
`global _settings` and returns the cached instance when it is not `None`; `clear_config_cache()`
is the only thing that resets it, and the three call sites above are all *pre*-test or
in-test. Collection order is alphabetical by path and there is no `pytest-randomly` in the dev
group, so `tests/test_rq_worker.py` deterministically precedes every module sorting after
`test_rq_worker` — `test_security.py`, `test_services_integration.py`, `test_storage_manager.py`,
`test_time_utils.py`, `test_token_revocation.py`, `test_upload_api.py`, `test_validators.py`,
`test_streaming_size_limit.py`.

**Consequence** — Every test after `test_rq_worker.py` reads its configuration from a
`Settings` built out of a test's throwaway values, including a JWT secret that differs from the
one `conftest.py:27` installs. Any of those tests that mints a token and any that later decodes
it can disagree, and any that reads `get_config().redis.host` sees `confighost`. The suite does
not fail today, which is the problem: the leak is invisible, and the day one of those tests
becomes sensitive to config it will fail for a reason 300 lines away from its own file.

**Recommendation** — Add an autouse function-scoped fixture in `conftest.py` that calls
`clear_config_cache()` on teardown, next to the `_auto_mock_redis` fixture that already
re-establishes process-wide state per test. One fixture closes the leak for all three call sites
and for any future one.

### TST-014 — the declared frontend gate deletes fifteen tracked files from the repository

**Severity** — MEDIUM

**Zone** — "What runs before a change lands, and what each gate's scope excludes"

**Observation** — `frontend/coverage/` is a **tracked** directory: `git ls-files
frontend/coverage` returns 15 files, including `index.html`, `coverage-final.json`,
`base.css`, `prettify.js` and per-file HTML. `.gitignore:39-48` ignores `htmlcov/`, `.coverage`,
`.coverage.*` and `coverage.xml` but not `coverage/`; `frontend/.gitignore` does not mention
coverage at all. Vitest cleans its report directory before writing, and
`frontend/package.json:9` runs `vitest run --coverage` — the command behind `Invoke-FeTest`
(`Makefile.ps1:237-238`), which is the last step of `Invoke-Check`.

**Evidence** — Runtime, observed and then reversed. Running `npm run test` in `frontend/` in
this repository left `git status --porcelain` reporting 15 deletions under `frontend/coverage/`
(`base.css`, `block-navigation.js`, `coverage-final.json`, `favicon.png`,
`features/auth/model/index.html`, `features/auth/model/useAuth.ts.html`, `index.html`,
`prettify.css`, `prettify.js`, `shared/api/errorHandler.ts.html`, `shared/api/index.html`,
`shared/types/enums.ts.html`, `shared/types/index.html`, `sort-arrow-sprite.png`, `sorter.js`),
and no coverage report to replace them, because the run was red. The working tree was returned to
its baseline state with `git checkout -- frontend/coverage` plus removal of the one newly
generated untracked file; see Appendix A.

**Consequence** — Running the project's own gate dirties the working tree, and on any red run
leaves it dirty in a way that looks like an intentional deletion. A `git add -A` after a failed
`fe-test` commits the removal of the tracked report. Because the report is what a reader consults
to answer "how much of the frontend is covered", the artefact that would have exposed TST-004 is
the artefact the gate destroys.

**Recommendation** — Untrack `frontend/coverage/` and add `coverage/` to `frontend/.gitignore`,
in that order, so no commit in between records a mass deletion. The report is reproducible from
`npm run test`; it does not belong in version control.

### TST-015 — the client and the server enforce different password policies, and the one test that shows it is the red one

**Severity** — MEDIUM

**Zone** — "Each boundary, from each side — including the ones every test crosses the same way"

**Observation** — The server's rule is `validate_password_or_raise`
(`src/mkobi/utils/validators.py:183-205`): at least 8 characters, at least one digit, at least
one letter in either case. It is reached from `ChangePasswordRequest.validate_new_password_field`
(`src/mkobi/models/auth.py:203-208`), so it governs `POST /auth/change-password`. The client's
rule is `changePasswordSchema.new_password`
(`frontend/src/shared/types/formSchemas.ts:56-59`): at least 8 characters, at least one
**uppercase** letter, at least one digit. The client's rule is a strict superset of the server's
requirements.

**Evidence** — Runtime, in this environment. `npm run test` fails
`src/shared/types/__tests__/formSchemas.test.ts > changePasswordSchema > accepts matching
passwords` with `AssertionError: expected false to be true` at `:162`; that test supplies
`new_password: 'newpassword123'`, which satisfies the server's rule (14 chars, a digit, letters)
and is rejected by the client's for want of an uppercase letter. The reverse direction is closed
— anything the client accepts satisfies the server's rule — so the divergence is one-way:
**every password the server would accept that lacks an uppercase letter is blocked in the UI
before a request is made**, with a validation message the server never sent and cannot produce.

**Consequence** — A user who reads the server's policy and complies with it cannot change their
password through the product. The rule is stated in two places, neither derives from the other,
and no test compares them. The test that would have caught this is the test that is failing, and
because nothing invokes `fe-test` (TST-002) it has stayed red unnoticed.

**Recommendation** — Pick one policy and state it once. The server already has
`validate_password_or_raise` as the single implementation and the registration path already uses
it (`auth_service.py:151`), so the smaller change is to relax the client's `new_password` to
"8 characters, one digit, one letter in either case" to match, and keep the test's current
expectation — which is then correct. If the stricter rule is the intent, the server must adopt it
too and the test's expectation is what changes; either way, one side must change and the
divergence must not survive. This is a boundary phase 12 and phase 13 also touch; the assertion
level fix belongs here because the red test is the evidence.

### TST-016 — no test observes whether a seeder run destroys uploaded data

**Severity** — MEDIUM

**Zone** — "Decisions the product acts on, and the value of each an assertion would reject"

**Observation** — `src/mkobi/db/seeders/test_media_dash.py:128-129` runs
`await db.execute(delete(Graph).where(Graph.dashboard_id == dashboard_id))` on every invocation,
under the comment "Delete existing graphs for this dashboard (idempotent - ensures clean state)".
Graphs are the parent of `aggregated_data`, so this cascades away every uploaded dataset for the
seeded dashboard on each run. **TXN-003** owns the defect; it is not re-filed. The gap this
phase owns is the test side: all ten tests in `tests/test_dev_seeders.py` assert the seeder's
*outputs* (dashboard created, graphs created, filters bound, config created, `run_dev_seeders`
callable) and one asserts idempotence. None creates an upload before running the seeder.

**Evidence** — `tests/test_dev_seeders.py:70` asserts `len(graphs) == 2  # Should still be 2, not
4` after a second seeder run. That assertion holds identically whether the seeder updates the two
graphs in place or deletes and recreates them, so it is invariant under both the defect and its
fix. A `Select-String` for `ensure_test_media_dash` and `run_dev_seeders` across `tests/*.py`
returns 12 call sites, all in `test_dev_seeders.py`, none of which writes an
`AggregatedData` row first.

**Consequence** — The decision "does re-seeding a dashboard preserve its data" is made on every
application start in the development tier and is asserted by no test in either direction.
`test_dev_seeders.py:70` looks like a guard on that decision and is not one: it will stay green
after TXN-003's fix, stay green if the fix is reverted, and would not notice the difference
today.

**Recommendation** — Add one test: create a dashboard, upload a small CSV so an `aggregated_data`
row exists, run `ensure_test_media_dash` twice, then assert the row is still there. That is the
assertion TXN-003's remediation needs as its gate, and it is the one thing the current
idempotence test cannot express. Tighten `:70` while you are there — assert graph identity
(`id`s unchanged), not just count, so the test stops being blind to which implementation ran.

### TST-017 — the `slow` and `fast` markers are registered, used by zero tests, and `fast` describes a path the harness does not have

**Severity** — LOW

**Zone** — "The harness as a system: schema build, isolation model, marker wiring"

**Observation** — `pyproject.toml:200-203` registers `slow: marks tests as slow (use -m slow to
run)` and `fast: marks tests that use Base.metadata.create_all() instead of full migrations`.
`addopts` (`:196`) carries `--strict-markers`, so an unregistered marker is a hard error and a
registered one is silent. A `Select-String` for `pytest.mark.slow` and `pytest.mark.fast` across
`tests/**` returns no match: both markers are applied by no test. The `fast` description names a
schema-build strategy the repository does not use — `conftest.py:433` always calls
`recreate_test_database()`, which drops the database and applies Alembic via
`db/starter.py:294`; the only `create_all` in the codebase is `init_db()` at
`src/mkobi/db/session.py:101-110`, which nothing in the test path calls.

**Consequence** — No runtime consequence today, and that is the finding: the harness has no fast
path, and the marker that advertises one is inert. A maintainer who reads `pyproject.toml:202`
has a reasonable but false model of how the schema can be built, and no test failure will correct
it.

**Recommendation** — Delete the `fast` marker; there is no `create_all` path to select. Keep
`slow` only if a `-m slow` split is actually intended — if it is, mark the handful of tests that
deserve it (`tests/test_e2e_upload.py`, `tests/test_db_pool.py`) and add
`addopts = … -m "not slow"` so the default gate is the fast subset, which is what the marker
exists for. Otherwise delete both and the `--strict-markers` flag stays useful for catching typos.

### TST-018 — the enum-consistency module claims a two-way check it performs one way for two of three enums

**Severity** — LOW

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — `tests/test_enum_db_consistency.py:1-7` states "Verifies that Python StrEnum
values match PostgreSQL ENUM types defined in migrations" and "After DB-001 migration, there
should be zero extra values in the database." All three enums are native PostgreSQL types —
`src/mkobi/db/models/user.py:52-54` (`user_role`),
`access.py:44-46` (`dashboard_permission_level`) and `processing_logs.py:44-46`
(`processing_status`). Only `TestProcessingStatusEnumConsistency.test_processing_status_values_match`
checks both directions: `:182-191` asserts `missing_in_db` is empty and then
`extra_in_db = db_values - python_values` is empty. `TestUserRoleEnumConsistency.test_user_role_values_match`
(`:66-77`) and `TestDashboardPermissionEnumConsistency.test_dashboard_permission_values_match`
(`:107-120`) assert only `missing_in_db`. `TestAllMappedEnumsConsistent.test_all_enums_consistent`
(`:229-254`) also checks only `python_values - db_values`.

**Consequence** — A value added to the `user_role` or `dashboard_permission_level` type by a
migration and left behind after the Python enum is narrowed is invisible to this module, which is
the only place in the suite that looks at `pg_enum`. A Postgres enum type cannot drop a label
without recreating the type, so a stale label is the realistic failure mode here — precisely the
one the module docstring says the suite guards against.

**Recommendation** — Extract the two-way comparison already written at `:179-191` into a helper
and call it from all three test classes. Four lines, and it makes the module's own description
true.

## Distribution

The findings fall almost entirely on the boundary between the test layer and the product, not on
either side of it. Fourteen of eighteen concern what the harness substitutes, manufactures or
declares; four concern the gates that run the suite at all. No finding is a defect in the product
code that belongs to this phase, and none is a style or structure matter belonging to phase 08.

- **The gates and their invocation** — TST-001, TST-002, TST-003, TST-004, TST-014. Carries the
  most: nothing in this repository can stop a change, and both suites are red today.
- **The `async_client` fixture and the session it substitutes** — TST-005, TST-006, TST-008,
  TST-012, TST-015. The single fixture that overrides `get_db_dependency`, the Redis dependency
  and the transport is responsible for more than half the phase.
- **Stale shipped assertions** — TST-010, TST-011. Five tests written against a changed return
  type, three written against a format the project forbids.
- **The mock-session service tests** — TST-009. 61 tests across three modules.
- **Worker and seeder recovery paths** — TST-007, TST-016. Cross-referenced to TOPO-001 and
  TXN-003 rather than re-filed.

## Cross-Finding Analysis

Two causes account for thirteen of the eighteen findings.

**Cause one — a test-layer decision was made once and never re-derived when the thing it stood in
for changed.** The `session: AsyncSession | None` parameter threaded through
`data_worker.py`, `cleanup_stale_processing_logs` and `mark_orphaned_uploaded_logs_failed` chose
the branch that works, and every shipped test takes it (TST-007). The `check_rate_limit` return
type changed from `bool` to `tuple[bool, int | None]` and five assertions were not revisited
(TST-010). The error format moved to RFC 7807 and three assertions were not revisited (TST-011).
`UserDB.updated_at` became required and one test was not revisited. In each case the production
change was right, the test was left behind, and nothing red flags it because nothing runs the
suite. That last clause is the shared root: TST-002 is why the other twelve are silent rather
than loud.

**Cause two — a shared fixture makes a decision invisible by resolving it before the code
under test can.** The `async_client` Redis override builds a second `MockRedis` (TST-005), which
is why the rate-limit integration tests pass against a store they cannot read. The `mock_db`
fixture hands three service modules a session that cannot fail (TST-009). The `async_db_session`
fixture's rollback-to-savepoint does not undo a `commit()` (TST-012), and the compensating
cross-test DELETEs it produces are themselves order-sensitive. The config singleton survives a
`monkeypatch` teardown (TST-013). Different fixtures, same shape: the harness answers a question
the test was supposed to ask.

TST-001, TST-003, TST-004, TST-014, TST-017 and TST-018 are independent of both and of each
other.

## Roadmap

**Step 0 — unblock the suite (TST-010, TST-011).** First, before any gate is introduced,
because a gate added red will be the first thing disabled. Unpack the tuple in the five
`test_auth.py::TestRateLimiting` assertions; rewrite the three `test_layouts.py` assertions
against the RFC 7807 body. Must be true before step 1: `.\Makefile.ps1 test` exits 0 and
`npm run test` exits 0, so that a new gate has a green baseline to protect.

**Step 1 — close the vacuous paths (TST-005, TST-007, TST-009, TST-016).** One `MockRedis` per
test instead of three; one test per recovery function that calls it with `session=None`; the
auth/graph/layout service subset moved to the real session; one test that an upload survives a
seeder run. Grouped because they share a shape: each adds the first assertion of a decision that
is currently made and unobserved. Must be true before step 2: each of the four decisions above is
observed from a failing-direction test, so that a later regression in any of them is red.

**Step 2 — make the gates real (TST-001, TST-002, TST-014, and the coverage halves of TST-003,
TST-004).** Bind-mount `src` and `tests` into `test-app`; add `Invoke-Test` to `Invoke-Check`;
untrack `frontend/coverage/` and ignore it; add `--cov=src/mkobi` to `addopts` and delete the
duplicated `fail_under`; add `coverage.include` to `vite.config.ts`; add one CI workflow running
`test-all` and `npm run test`. Ordered after steps 0 and 1 deliberately: a gate introduced
before these would be red, and a red gate gets disabled rather than fixed. Must be true before
step 3: a change that breaks the product cannot reach a deployed system, because the suite that
would say so is now measuring the right code.

**Step 3 — settle the reproduction and hygiene items (TST-006, TST-008, TST-010's sibling
rework, TST-012, TST-013, TST-015, TST-017, TST-018).** Low risk, no ordering constraints among
them, and each is independently revertible. TST-006 belongs here rather than earlier because it
must be rewritten alongside AUTH-001's fix, not ahead of it.

**Cross-phase dependencies.** TST-006 gates **AUTH-001** and must land with it.
TST-007 gates **TOPO-001**. TST-016 gates **TXN-003**. TST-008 makes **TXN-001** observable and
should be done before phase 03's remediation so that remediation has something to fail against.
TST-015 straddles the phase 12 and phase 13 boundary; the assertion fix is here, the policy
decision needs whoever owns authentication.

## Rollout Safety

Step 0 is the only step that changes what the suite asserts without changing what the product
does, and it is the step most likely to be misread. Making five tests pass by unpacking a tuple
is not "weakening the assertion" — the same value is asserted, just destructured. Making three
tests pass by rewriting them against the RFC 7807 body *does* change what they accept: a response
that returns a bare-string `detail` will now fail them. That is the intended direction, and it
means these three tests become the first thing to catch a regression back to the legacy format,
which is what the project wants. If any of the three turns out to have been documenting an
intentional exception to RFC 7807, the exception needs to be written down rather than inferred
from a passing test.

Step 1 adds tests and changes two fixtures. The `MockRedis` consolidation in TST-005 is the one
to watch: it will change what three currently-passing rate-limit tests observe, because they will
start reading the store the route actually wrote to. If any of them fails after the change, that
is the test doing its job for the first time, not a regression — investigate before relaxing
anything. Adding `session=None` coverage for the worker sweeps (TST-007) will create and commit
rows in `bidb_test` on paths that previously ran against a mock; combined with TST-012's
commit-persists behaviour, budget for cross-test interference and fix the fixture in the same
change.

Step 2 changes the harness the whole suite runs in. The bind mount in TST-001 is the highest-risk
single change in this report: it swaps the `test` target from a known-good image to live host
files, so for the first time the suite will read whatever is currently in the working tree —
including uncommitted work. Expect a first run to fail in ways it never has. That is the point,
and it is why step 2 follows step 0. Untracking `frontend/coverage/` is a single `git rm --cached`
plus a `.gitignore` line; do both in one commit so no intermediate commit records a mass
deletion. Adding `--cov=src/mkobi` to `addopts` will turn coverage measurement on for every
pytest invocation, which is a measurable slowdown on a 5-minute suite and may push the first
measured number under the 65 floor — read that number before deciding it is a problem, and fix
the coverage rather than the floor.

Every step reverts by a single commit revert. No step touches production code; the only step that
touches a production file is TST-015, and there the production file is not changed — the
recommended direction is to change the client's schema to match the server, which is a frontend
file and phase 13's decision to make.

## Appendices

### Appendix A — working-tree state

Baseline recorded before any read: `git rev-parse HEAD` → `b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd`,
`git status --porcelain` → 20 deleted paths under `.ai/` and 9 untracked paths
(`.ai/audit/01-…` through `99-validation/`, plus `.ai/plans/01-configuration-secrets-remediation-execution.md`).
No tracked source or test file was modified at baseline.

During this audit the declared frontend gate was executed (TST-014). Vitest deleted the 15
tracked files under `frontend/coverage/` and, because the run was red, wrote no replacement.
The tree was returned to baseline with `git checkout -- frontend/coverage` followed by removal of
the single newly generated untracked file `frontend/coverage/enums.ts.html` produced by a
subsequent green-file-only run. `git status --porcelain -- frontend/` is now empty and the
20-plus-9 baseline delta is unchanged. No other file was created, edited, staged, committed,
reverted or stashed by this audit.

### Appendix B — concurrency during the audit

The concurrent credential-predicate remediation moved `HEAD` through `2d23c27` → `c3c0a61` →
`5a2cfb6` → `b23a9cb` while this phase ran, and the first three of those touched
`tests/test_config.py` and `tests/test_starter.py`. Every test anchor cited above was re-verified
against the working tree at the time of citation, after the last observed commit. Specifically:
`tests/conftest.py` (616 lines, all anchors at `:308-334`, `:540-566`, `:590`) is unmodified
against `HEAD`; `tests/test_rate_limiting.py:124, :138-139, :150` was re-read and the `:150`
failure is quoted from the live 1013-test run; `tests/test_data_worker.py`, `tests/conftest.py`
line numbers for the worker branch, `Makefile.ps1`, `pyproject.toml`, `docker/Dockerfile` and both
compose files were all re-read after `b23a9cb` landed. The 1013-test run and the
`npm run test` run both executed against the `b23a9cb` working tree.

**Effect on conclusions: none.** The only finding that touches a file the concurrent programme
edited is TST-001 itself, and its evidence is structural — a missing `volumes:` key in a compose
file and a missing `--build` in a Makefile target, neither of which the credential work touches.
Its *runtime* observation (image `CreatedAt` 15:33:38 versus commit time 15:40:39) is in fact an
artefact of that concurrency: the remediation team wrote `src/mkobi/config.py` into the working
tree before building the image, which is why the two copies agree today. Read without the
concurrency, the images would have been 7 minutes staler and the finding sharper. The finding
stands on the configuration, not on the timestamp.

### Appendix C — what was executed, and what could not be

Executed in this environment: `.\Makefile.ps1 test-up` (both services healthy);
`.\Makefile.ps1 test` — **1013 collected, 1003 passed, 10 failed, 23 warnings in 309.23s**, with
the full failure list in TST-002/TST-010/TST-011; `npm run test` — **170 collected, 169 passed,
1 failed**; `npx vitest run --coverage` on one green file, on the failing file, and on the full
suite; `uvicorn 0.49.0` configuration introspection in the test image; `md5sum` of
`/app/src/mkobi/{main,config,app}.py` and `/app/tests/test_config.py` against host hashes; a full
`find`-based diff of the image `src` tree against the working tree (115 files each side, no
difference); `docker images`, `docker compose … config`, `git log`/`git show --stat`.

Not executed, and therefore not characterised: `.\Makefile.ps1 test-all` (the measured backend
coverage percentage is **not** quoted anywhere in this report, because running it concurrently
with `test` would have had `setup_test_database` drop the database the other run was using, and
it was not run afterwards); `.\Makefile.ps1 check` end-to-end (its four constituent steps are each
analysed statically and `fe-test` was run directly, but the aggregate was not invoked);
`.\Makefile.ps1 lint` / `typecheck` (out of scope for this phase — phase 08 owns ruff and mypy);
any xdist-parallel run (pytest-xdist is installed and supported by the conftest worker-suffix
logic, but every run in this audit was serial, so the isolation claims in TST-012 are reasoned
from the code and from the two cross-test DELETEs, not from an observed parallel failure);
browser-level or accessibility testing of the 13 frontend test files.

### Appendix D — declared gate inventory

| Gate | Loaded by | Configured to examine | Actually examined | Verdict |
|---|---|---|---|---|
| `pytest` (`pyproject.toml` `addopts`) | `Makefile.ps1 test`, `test-all`, `test-select` — all manual | `testpaths = ["tests"]` | all 1013 collected tests | 10 red; no coverage measured (TST-003) |
| `ruff check src/ tests/` | `Makefile.ps1 lint`, `check` — manual | both trees | not run (phase 08) | out of scope |
| `mypy src/` | `Makefile.ps1 typecheck`, `check` — manual | `src/` only | not run (phase 08) | `tests/` excluded by design |
| `eslint .` | `Makefile.ps1 fe-lint`, `check` — manual | `frontend/` | not run | out of scope |
| `vitest run --coverage` | `Makefile.ps1 fe-test`, `check` — manual | import-driven (TST-004) | 170 tests | 1 red; no report emitted |
| CI / pre-commit / pre-push hook | **nothing** | — | — | absent from the repository |

The two entries that matter for this phase are the last two rows and the absence of a CI row:
every gate is an entry point a person must choose to run, and `Invoke-Check` does not include the
backend suite at all.

### Appendix E — marker wiring

| Marker | Registered | Applied by | Described behaviour exists? |
|---|---|---|---|
| `slow` | `pyproject.toml:201` | 0 tests | n/a — no `-m` split in any target |
| `fast` | `pyproject.toml:202` | 0 tests | **no** — no test calls `Base.metadata.create_all`; the schema is always built by `recreate_test_database()` → Alembic |

`--strict-markers` (`pyproject.toml:196`) is what makes both rows silent: an unregistered marker
would be a hard error, so a registered-but-unused one produces no diagnostic at all.
