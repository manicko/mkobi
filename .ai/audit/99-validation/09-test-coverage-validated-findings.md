---
phase: 09-test-coverage
executed: 2026-09-30
executor: validator
problems-only: true
baseline: b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd
baseline-dirty: "true (20 deleted .ai paths, 9 untracked .ai/audit + .ai/plans paths; no tracked source or test file modified; identical to the input's own Appendix A)"
findings: 18
by-severity:
  CRITICAL: 2
  HIGH: 7
  MEDIUM: 7
  LOW: 2
---

# Phase 09 — Validated Findings

## Summary

All eighteen findings in `.ai/audit/09-test-coverage/findings.md` were re-derived from the executing path at
commit `b23a9cb`, which is the input's own baseline and, at the time of this validation, still `HEAD`. Sixteen are
substantiated as filed; two are substantiated with a scope correction. The two CRITICAL findings are the strongest
in the phase and both survive on configuration rather than on the runtime observation the input rests them on. TST-001
was re-established mechanically: `docker compose -p mkobi-test -f docker/docker-compose.test.yml config` resolves
`test-app` with `build`, `command`, `depends_on`, `deploy`, `environment`, `healthcheck`, `networks` and **no
`volumes` key at all**, `$TestCompose` (`Makefile.ps1:36`) loads only the test compose file so the dev override's
`../src:/app/src` mount cannot reach it, and `Dockerfile:135` bakes `COPY src/ ./src/` into the `test` stage that
`:196`, `:201` and `:210` run with no `--build`. The input's *timestamp* evidence for TST-001 is no longer
reproducible — the image was rebuilt at 16:00:48, twenty minutes after `HEAD` — and the finding rests on the
configuration instead, as recorded as VAL-09-009.

The load-bearing runtime claims were re-measured rather than re-read. `npx vitest run --coverage` on one green file
reports `Statements : 100% ( 9/9 )` with an empty per-file table, reproducing TST-004 exactly; the same run also
**deleted six tracked files from `frontend/coverage/` and rewrote four more**, which refutes TST-014's asserted cause
while strengthening the finding. `npm run test` gives `Test Files 1 failed | 12 passed (13)`, `Tests 1 failed | 169
passed (170)`, the failure at `formSchemas.test.ts:162`, identical to the input. The input's TST-014 restoration
claim is **verified**: `git status --porcelain -- frontend/` was empty at the start of this validation, and the two
times this validation re-dirtied that directory it restored it.

The backend suite was run three times at `b23a9cb` and the results were **`12 failed, 1001 passed`**, then
**`11 failed, 1001 passed, 2 errors`**, then **`10 failed, 1003 passed`** — the last character-for-character identical
to the input's `10 failed, 1003 passed`, down to the same ten node ids. The input's evidence is therefore real and
reproducible, and it is also a single sample of a figure that moves: the same command on the same commit, with the
image's `src/` and `tests/` hashed against the working tree and proven byte-identical across all 168 Python files,
produced three different answers. That variability is not the concurrent remediation's and not a stale image — it is
the isolation defect the input itself filed as TST-012, surfacing from outside, and the input's Evidence never records
that its own failure count is not stable. Direct runtime proof of TST-012 was obtained: after a pytest process
exited, `bidb_test` still held 2 `users`, 10 `dashboards`, 8 `processing_logs` and 5 `graphs` rows created and
committed by tests inside that process.

The concurrent remediation's own uncommitted edits appeared late in this validation — `src/mkobi/config.py` and
`tests/test_config.py`, `HEAD` still `b23a9cb` — and two anchors this report cites moved as a result. Both are
recorded where they are cited and in Appendix B2; no finding, band or verdict depends on either file's line numbers.

The input's cross-referencing discipline is sound in four of its five instances — TST-006, TST-007, TST-008 and TST-015
each name another phase's finding rather than re-filing it — but two of the five name the **wrong** owning finding:
TST-016 gates **TXN-003** where the seeder defect is filed as **TXN-008**, and TST-010 parks the rate limiter's
fail-open tests on **AUTH-002**, which owns `TempPasswordStore`. Both are recorded as VAL-09-002 and VAL-09-004. One
finding is filed partly outside the phase's own declared scope paragraph: TST-015's recommendation edits
`frontend/src/shared/types/formSchemas.ts`, a production client file the scope paragraph assigns to phase 13.

TST-002 is **merged** with **QLT-003** on their shared root cause — the aggregate entry point omits the backend suite
and no gate is wired to an automated path — with phase 09 owning remediation of that cause, on the strength of its own
scope paragraph. Twelve defects in the audit itself are filed below on the `VAL-09-` namespace; the flat `VAL-` prefix
is already occupied twice, by the phase-01 and phase-02 reports, and that deviation is recorded as VAL-09-012.

Each finding below carries the five fields the shared template mandates plus **Verdict**, which the template does not
enumerate and the validation output contract requires.

## Findings

### TST-001 — the backend gate tests a baked image, not the working tree

**Severity** — CRITICAL

**Verdict** — confirmed; band upheld at CRITICAL

**Zone** — What runs before a change lands, and what each gate's scope excludes

**Observation** — Re-derived from the executing configuration, not from the quoted timestamps. `test-app`
(`docker/docker-compose.test.yml:123-167`) declares `build` (`:124-127`), `environment` (`:128-147`), `ports`
(`:148-150`), `depends_on` (`:151-155`), `healthcheck` (`:156-157`), `restart`, `deploy`, `networks` and `command`
(`:167`) — and no `volumes` key. The only `volumes:` keys in the file are `:39` (test-db) and `:65` (test-redis).
`$TestCompose` (`Makefile.ps1:36`) is `@('-p', $TestProject, '-f', 'docker/docker-compose.test.yml')`, so
`docker-compose.override.yml` — which mounts `../src:/app/src`, `../alembic:/app/alembic` and `../tests:/app/tests`
at `:99-101` for the dev `app` — is not loaded for the test project and cannot contribute a mount. The `test` stage
of `docker/Dockerfile` (`:132-151`) bakes the product in: `COPY src/ ./src/` at `:135`, `COPY tests/ ./tests/` at
`:139`. `Invoke-Test` (`:196`), `Invoke-TestAll` (`:201`) and `Invoke-TestSelect` (`:210`) each run
`docker compose @TestCompose run --rm --no-deps test-app pytest …` with no `--build`.

**Evidence** — `docker compose -p mkobi-test -f docker/docker-compose.test.yml config` was resolved and the printed
`test-app` block contains no `volumes` key: the resolved service is `build`, `command`, `depends_on`,
`deploy.resources`, `environment` (21 variables), `healthcheck.disable` and `networks.test_network`. The
three-target grep over `Makefile.ps1` returns no `--build` anywhere in `Invoke-Test`, `Invoke-TestAll` or
`Invoke-TestSelect`. The input's contrasting runtime evidence — image `3a77fb234217` created `15:33:38` against
`HEAD` at `15:40:39` — no longer reproduces: `docker images` now reports `mkobi-test-test-app … b6d8cd8b1baa …
CreatedAt 2026-09-30 16:00:48 +0200`, twenty minutes *after* `b23a9cb`, because the concurrent remediation rebuilt
the image after the input was filed. As recorded in VAL-09-009, the timestamp argument is superseded; the
configuration argument is not affected by the rebuild.

**Consequence** — Unchanged and re-derived. `.\Makefile.ps1 test`, `test-all` and `test-select` return a verdict
about the code as of the last `docker compose build`, not about the working tree. A change to `src/mkobi/**` that has
not been rebuilt is not tested, and the result is indistinguishable from a run that tested it. The dev `app` service,
which bind-mounts the host tree, is running a different copy of the product from the one under test.

**Recommendation** — Carried out and executable. Add `- ../src:/app/src` and `- ../tests:/app/tests` to `test-app`.
The target resolves (`docker/docker-compose.test.yml:123`), the fix matches a pattern already proven in
`docker-compose.override.yml:99-101`, and the `--build` interim the input offers is correctly identified as a
mitigation rather than the fix. One dependency the input states: a bind mount must be validated against the
`libmagic` and Rust-extension paths inside the image, which is the only reason the input offers two shapes.

### TST-002 — no gate is invoked by anything, the aggregate target omits the backend test tree, and both suites are red

**Severity** — CRITICAL

**Verdict** — merged with QLT-003; band upheld at CRITICAL; its failure count is one sample of an unstable figure

**Zone** — What runs before a change lands, and what each gate's scope excludes

**Observation** — Re-derived, the three absences it tells apart are all real and all correctly distinguished.
(a) *Declared and never loaded:* the repository contains no `.github/`, no `.gitlab-ci.yml`, no `.circleci/`, no
`azure-pipelines.yml`, no `Jenkinsfile`, no `.husky/`, no `.pre-commit-config.yaml`, no `tox.ini`, no `noxfile.py`,
and `.git/hooks/pre-commit` does not exist. (b) *The aggregate omits a process tree:* `Invoke-Check`
(`Makefile.ps1:241-249`) chains `Invoke-Lint` → `Invoke-Typecheck` → `Invoke-FeLint` → `Invoke-FeTest` and calls
nothing else; `Invoke-Test` (`:194-197`) and `Invoke-TestAll` (`:199-202`) are unreachable from it, while the help
text at `:81` reads `check — Aggregate gate: lint + typecheck + fe-lint + fe-test` and the help text at `:69` reads
`test — Default gate`. (c) *Loaded and red:* both suites fail.

**Evidence** — The absence claim is an inventory with a stated absence and it is complete. The red claim is where
this finding needs a qualification. The input records `.\Makefile.ps1 test` → `collected 1013 items`, `10 failed, 1003
passed, 23 warnings in 309.23s`. **This validator ran the equivalent command three times at `b23a9cb`:**

| Run | Result | Delta against the input's ten |
|---|---|---|
| input | `10 failed, 1003 passed, 23 warnings in 309.23s` | — |
| run 1 | `12 failed, 1001 passed, 23 warnings in 316.67s` | + `test_e2e_upload.py::TestE2EUploadWorkflow::test_e2e_multiple_graphs_same_dashboard` (`KeyError: 'task_id'`), + `test_users_api.py::TestDeleteAccount::test_admin_cannot_delete_self` (`AssertionError: Database cleanup failed`, `assert 7 == 0`) |
| run 2 | `11 failed, 1001 passed, 23 warnings, 2 errors in 312.91s` | + `test_admin_cannot_delete_self`; the e2e test absent; 2 errors not seen in run 1 |
| run 3 | `10 failed, 1003 passed, 23 warnings in 294.71s` | none — identical to the input, same ten node ids |

So the input's figure is real and reproducible: run 3 reproduced it exactly, node for node. It is also one sample of a
figure that moves on identical code. The image was hashed against the working tree to exclude the two candidate
explanations: `md5sum` over `find src tests -name '*.py'` inside `test-app` against `Get-FileHash` on the host
returns `img=168 host=168` and **no differences**, so the code under test was byte-identical to `HEAD` in every run,
and `docker compose … config` shows `test-app` has no `volumes` key, so no unmounted host file could have differed.
`npm run test` reproduces exactly: `Test Files 1 failed | 12 passed (13)`, `Tests 1 failed | 169 passed (170)`.
The ten the input names were individually re-diagnosed: five `assert (True, None) is True` / `(False, 300) is False` at
`test_auth.py:278`/`:291`/`:332`/`:369`/`:384` (TST-010), two
`where False = isinstance('Request validation failed', list)` in `test_layouts.py` (TST-011), one
`assert 422 == 400` in `test_layouts.py` (see TST-011 below), one
`ValidationError: 1 validation error for UserDB / updated_at / Field required` in `test_pydantic_models.py`, and one
`AssertionError: Request should succeed after reset, got 429 / assert 429 == 401` at `test_rate_limiting.py:150`,
matching TST-005's quoted string character for character.

**Consequence** — Unchanged, and still the right consequence: nothing in this repository can prevent a change from
landing, and a reader of `Makefile.ps1 help` can reasonably conclude the backend suite is covered when it is not in
that list or any other automation. One sentence of the input's present-state statement needs narrowing: "both suites
are red with 10 and 1 failures" is true and measured, but the backend figure should read as **10–12 failures across
three runs of identical code**, not as a fixed count. The correct present-state statement is that the backend suite
is red and its failure count is unstable, because the suite's isolation model does not hold. That is TST-012's
finding, and TST-002 does not connect the two.

**Recommendation** — Carried out and executable, with one correction to its ordering. The three changes are all
resolvable targets. The third — resolve the red tests before introducing the gate — is right, and the input's
instruction not to silence them by relaxing assertions is right and is what AGENTS.md requires. The correction is
that the input's failure list is a sample, so a reader following it literally will close Step 0 believing the suite
green while `test_admin_cannot_delete_self` and `test_e2e_multiple_graphs_same_dashboard` are still red in two of
three runs. Both must be treated as red. See VAL-09-001.

### TST-003 — the backend coverage threshold has no measurement to act on

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH

**Zone** — What a coverage measure can actually see

**Observation** — `pyproject.toml:196` reads
`addopts = "--import-mode=importlib -ra -v --strict-markers --cov-fail-under=65"`. There is no `--cov` and no
`--cov=<path>` anywhere in that string, and `--cov-fail-under` is the only coverage option present in `addopts`.
`[tool.coverage.run] source = ["src/mkobi"]` at `:208` is the measurement `--cov=src/mkobi` at
`Makefile.ps1:201` would select, and `[tool.coverage.report] fail_under = 65` at `:212` restates the number as a
literal in a second place. `Invoke-Test` at `:196` — the target the help text at `:69` names "Default gate" — runs
bare `pytest`.

**Evidence** — The resolved `pyproject.toml` and `Makefile.ps1` above. The input's runtime claim that the 1013-test
run emitted no coverage table and no threshold verdict is consistent with the configuration and was not re-measured
separately: this validator's two pytest invocations emitted no coverage section, which is the same absence.
`test-all` was not run, so the measured percentage remains unquoted in both reports — correctly, since quoting a
number nothing has read is the error the finding is about.

**Consequence** — Unchanged. `.\Makefile.ps1 test` returns a verdict carrying no information about how much of the
product ran, and the 65% floor in `pyproject.toml` has never gated the default path.

**Recommendation** — Carried out and executable. Add `--cov=src/mkobi` to `addopts` and delete the duplicated
`fail_under`. Both targets resolve (`pyproject.toml:196` and `:212`). The input correctly identifies its own risk in
Rollout Safety: enabling measurement may put the first measured number under 65, and the correct response is to fix
the coverage rather than the floor.

### TST-004 — the frontend coverage thresholds measure an import-driven population, and are suppressed entirely while the suite is red

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH

**Zone** — What a coverage measure can actually see

**Observation** — `frontend/vite.config.ts:56-65` configures `coverage.provider: 'v8'`,
`coverage.reporter: ['text', 'json', 'html']` and four thresholds — `statements: 50`, `branches: 40`,
`functions: 45`, `lines: 50` — with no `coverage.include`, no `coverage.exclude` and no `coverage.all`. The measured
population is therefore whatever the executed tests imported. `frontend/package.json:10` runs
`vitest run --coverage`, and `Makefile.ps1:237-238` (`Invoke-FeTest`) forwards to it as the last link of
`Invoke-Check`.

**Evidence** — Reproduced in this environment at this commit. `npx vitest run --coverage
src/shared/types/__tests__/enums.test.ts` on vitest 4.1.7 returns `Test Files 1 passed (1)`, `Tests 21 passed (21)`,
then a coverage table whose **per-file body is empty — no rows at all** — followed by
`Statements : 100% ( 9/9 )`, `Branches : 100% ( 0/0 )`, `Functions : 100% ( 0/0 )`, `Lines : 100% ( 9/9 )`. Nine
statements is the entire measured population of a project whose `frontend/src` holds route modules, API clients and
MUI wrappers, and the four thresholds pass against that denominator. The suppression claim reproduces exactly as the
input describes: `npm run test` prints `Coverage enabled with v8` and then, on the red run, **no coverage table and
no threshold verdict at all**.

**Consequence** — Unchanged. Adding a feature no test imports lowers measured coverage not at all; adding a test
that imports one more module raises the denominator without the feature being covered. And today `fe-test` verifies
no coverage whatsoever, because the report is emitted only on a green run and the suite is not green.

**Recommendation** — Carried out and executable. Set `coverage.include: ['src/**/*.{ts,tsx}']` at
`frontend/vite.config.ts:57` and separate report generation from the pass/fail verdict. The input's framing is right
and worth preserving: the population the measure cannot reach is the honest answer to "what is not covered", and it
is currently invisible rather than reported as zero.

### TST-005 — the rate-limit integration tests exhaust a counter on a store they cannot reach, and one of them is red for that reason

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH; one evidence sentence overstates the vacuity

**Zone** — What each stand-in removes, and whether any test observes it elsewhere

**Observation** — Three independent `MockRedis` instances are constructed per test, and the login path can reach none
of the one the test holds. The autouse `_auto_mock_redis` fixture creates instance A at `tests/conftest.py:308` and
patches `get_async_redis_client`/`get_redis_client` on the **source module** at `:318-319`. `strict_redis`
(`:370-397`) creates instance B at `:380` and patches the same source-module attribute at `:388`. `async_client`
creates instance C at `:546`, overrides `get_redis_client_dependency` with it at `:547-549`, and stashes it on
`app.state.mock_redis` at `:557`. The split is not merely "the two never share a key": `src/mkobi/api/deps.py:40`
does `from mkobi.core.redis_client import get_async_redis_client`, binding the name into the `deps` namespace at
import time, so a `monkeypatch.setattr` on `mkobi.core.redis_client.get_async_redis_client` cannot reach
`deps.get_async_redis_client` at all. `src/mkobi/api/routes/auth.py:84-85` builds its **own**
`AsyncRateLimiter(redis_client, …)` from `redis_client: Any = Depends(get_redis_client_dependency)` (`auth.py:146`),
which the fixture has replaced wholesale with instance C. `AuthService.__init__` (`services/auth_service.py:66-67`)
builds a second limiter from `get_async_redis_client()`, and `auth_service.py:19` likewise bound that name by value —
so `_auto_mock_redis`'s patch misses that one too.

**Evidence** — Every anchor resolves as cited: `conftest.py:308`, `:318-319`, `:380`, `:388`, `:397`, `:546`, `:547-549`,
`:557`, `:559`; `test_rate_limiting.py:16`, `:75`, `:107`, `:155` for the four `strict_redis` declarations, and `:199`,
`:203`, `:212`, `:216`, `:230`, `:234` for the three unit tests that construct `AsyncRateLimiter(strict_redis)`
directly and unpack the tuple correctly at `:206`, `:221`, `:225`, `:241`. `MockRedis` (`conftest.py:179-223`) does
expose `_data` and `_ttls`, so `test_rate_limiting.py:138-139` is syntactically valid against instance B and a no-op
against instance C. Runtime: `AssertionError: Request should succeed after reset, got 429 / assert 429 == 401` at
`test_rate_limiting.py:150`, matching the input's quoted string character for character. One correction to the
input's evidence: it says the two passing siblings "pass, because they only assert that a 429 occurs".
`test_login_rate_limit_exceeded` (`test_rate_limiting.py:15-72`) in fact asserts **401 five times** at `:44-46` before
asserting 429 at `:57`, which is a genuine observation of the counter incrementing; what it cannot observe is the
contents of the store it declares. `test_different_ips_have_separate_limits` (`:154-193`) is the one that is wholly
vacuous: one address, one key, and a single 429 assertion.

**Consequence** — Unchanged, and slightly stronger than the input states. The `strict_redis` parameter is dead in all
four integration tests, so the class reads as integration coverage of a store the route never touches. The one test
that tried to read that store is red, which is the correct signal.

**Recommendation** — Carried out and executable, and the input's guard against the tempting wrong fix is correct:
resolve `strict_redis` and `async_client` to one `MockRedis` per test, and do not relax the 429 assertion. One
dependency the input does not name and must: because the route builds its limiter from the FastAPI dependency and
`AuthService` builds a second one from the module-level function, consolidating the fixture alone leaves two limiters
with two stores unless the consolidation also covers `services/auth_service.py:66-67`.

### TST-006 — the rate-limit key the tests hard-code is a client identity no production request can present

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH

**Zone** — Each boundary, from each side — including the ones every test crosses the same way

**Observation** — `tests/test_rate_limiting.py:124` sets `rate_limit_key = "login:127.0.0.1"` and pops that literal at
`:138-139`. The production key is built at `src/mkobi/api/routes/auth.py:89` as `f"login:{client_ip}"`, where
`client_ip` derives from the ASGI request's client address. Under `httpx.ASGITransport` that is `127.0.0.1`; behind
the shipped nginx it is the nginx container's address for every request from every user.

**Evidence** — The anchors resolve: `test_rate_limiting.py:124`, `:138-139`, and the route's key construction at
`auth.py:88-89`. The production half of the claim is phase 04's **AUTH-001** ("Five correct logins lock every user
out of the only login surface for five minutes") and is named, not re-filed — the correct treatment. The input's
claim about `test_different_ips_have_separate_limits` is confirmed by direct reading: `test_rate_limiting.py:154-193`
contains no second IP, no second key and no second login; it repeats `:15-72`'s exhaust-then-429 shape and would pass
unchanged if the limiter were keyed on a single global constant.

**Consequence** — Unchanged. The test binds itself to a key value only the harness can produce, so it can neither
observe the production key nor detect the change that fixes AUTH-001; and it will go red the moment AUTH-001 is
fixed. That makes the file a remediation blocker, which is how the input files it.

**Recommendation** — Carried out, and correctly deferred: the input places this in step 3 rather than ahead of
AUTH-001 because the test must be rewritten *alongside* the fix. Executable as written. One dependency worth
stating: deriving the key from the same expression production uses couples the test to
`auth.py:88-89`'s exact format, so "assert the limiter's own bookkeeping" — the input's first option — is the more
durable of the two it offers.

### TST-007 — every shipped worker test injects the session that makes TOPO-001's compensating write unreachable

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH

**Zone** — Decisions the product acts on, and the value of each an assertion would reject

**Observation** — `src/mkobi/workers/data_worker.py:552` branches on `if db_session is not None:`. The `True` branch
(`:554-581`) calls `_run_with_transaction(db_session)` and, on failure, writes `FAILED` through
`_update_processing_log_status(..., session=db_session, ...)` at `:573-580` and re-raises at `:581`. The `else` branch
(`:582-620`) opens `async with get_session()` at `:584` and `async with session.begin()` at `:585`; its
`except` handler ends at `:603` with `raise`, so the independent FAILED write at `:608-614` and the
`error_msg`/`error_code` it consumes at `:609`/`:612` are unreachable on both paths.

**Evidence** — Every anchor is exact, which is unusual and worth recording: `:552`, `:554-581`, `:573-580`, `:581`,
`:582-620`, `:584`, `:585`, `:603`, `:608-614` all resolve to what the input says they do. The same two-branch shape
is confirmed at `cleanup_stale_processing_logs` (`:254` `if session is not None:` / `:269` `else:`), where the two
branches build byte-identical `update(ProcessingLog)` statements over the same `WHERE` and `.values()` and differ
only in session ownership, and at `mark_orphaned_uploaded_logs_failed` (`:314` / `:330`). **TOPO-001** owns the
defect and is named, not re-filed; phase 01's own report carries it as "A failed background job is recorded as still
awaiting processing until the process restarts", which is the same statement.

**Consequence** — Unchanged, and the sharper half is the one the input states: the suite can neither fail on TOPO-001
nor pass on its fix, because no test exercises the production branch.

**Recommendation** — Carried out and executable, with the constraint the input names correctly: a test calling
`process_csv_background` with `session=None` needs the real `get_session()` at `:584`, so it must run against a real
database rather than the fixture's session. The input's instruction to keep the existing session-passing tests for the
`WHERE`/values logic is correct.

### TST-008 — the HTTP fixture substitutes the test's own session for the product's, so commit, rollback and teardown are never under test

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH

**Zone** — Each boundary, from each side — including the ones every test crosses the same way

**Observation** — `tests/conftest.py:540-541` defines `override_get_db()` yielding the test's `async_db_session`,
registered at `:543`; `:559` builds the client over `httpx.ASGITransport(app=app)` at `:560-562`. `api/deps.py`'s
`get_db_dependency` and `db/session.py`'s sessionmaker are therefore replaced for every HTTP test, as is the
transport.

**Evidence** — All anchors resolve. The input's credit to the suite is verified rather than assumed:
`tests/test_deps.py::TestGetDbDependency` contains `test_get_db_yields_session`, which calls the real
`get_db_dependency()` generator outside any request, and `test_get_db_session_usable`, which goes through the
overridden client — so the real generator is exercised, and only outside a request, exactly as claimed. The
cross-reference to **TOPO-004** is correct: phase 01 files "The only path that drops and recreates the whole store
takes no guard, and the one guard in the system is entered after the store is gone", and the ASGI transport's
lifespan bypass is the reason its destructive branch is unreachable from a test.

**Consequence** — Unchanged. **TXN-001** ("Four endpoints return success for a write that is never committed") is
invisible to every API test, and the input names it as made-observable rather than re-filed, which is right.

**Recommendation** — Carried out and executable, and correctly bounded: keep the override and add a small number of
tests that exercise the real `get_db_dependency` through `ASGITransport` without it. The input's estimate of four or
five such tests is a judgement, not a measurement, and is stated as a direction rather than a requirement.

### TST-009 — three whole service modules are asserted only against a mock session that absorbs every constraint

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH

**Zone** — What the harness manufactures by default: identity, store, schema, environment

**Observation** — `conftest.py:510-519` defines `mock_db` as `AsyncMock(spec=AsyncSession)`, returning a `MagicMock`
from every call, so no SQL is issued, no constraint evaluated and no row written.

**Evidence** — Re-derived counts, all exact. A scan for `def test_.*\bmock_db\b` over the three files returns **61**
matches, split **28** in `tests/test_auth_service.py`, **16** in `tests/test_graph_service.py` and **17** in
`tests/test_layout_service.py`; the three files hold **42**, **17** and **17** test functions respectively, so the
input's "61 of 76" and its three per-file fractions are correct. `mock_db` is referenced in exactly four files —
`conftest.py` and those three — so "no other module consumes the fixture" holds. The quoted assertions resolve:
`test_graph_service.py:67` (`assert call_args[0][0] == mock_db` — the input quotes it with `is` where the file has
`==`; recorded as VAL-09-008), `:75` and `test_auth_service.py:478` (`mock_db.commit.assert_called_once()`).

**Consequence** — Unchanged. `AuthService` — behind login, registration, temp-password reset and password change —
is asserted from one side only, and a wrong column name, `WHERE` clause, missing `ON CONFLICT` or misplaced commit
passes all 28 tests.

**Recommendation** — Carried out and executable, and correctly bounded in both directions: convert registration,
login and `reset_password_admin` to the real `async_db_session` and leave the remainder on `mock_db`, which the input
rightly identifies as the right tool for "does this method call its repository with these arguments".

### TST-010 — five shipped rate-limiter tests assert a scalar against an API that returns a tuple

**Severity** — MEDIUM

**Verdict** — confirmed; band upheld at MEDIUM; its AUTH-002 cross-reference names the wrong finding

**Zone** — Decisions the product acts on, and the value of each an assertion would reject

**Observation** — `AsyncRateLimiter.check_rate_limit` is declared `-> tuple[bool, int | None]` at
`src/mkobi/core/security.py:111-113` and returns `(True, None)` at `:88`/`:103`/`:136` or
`(False, ttl_remaining …)` at `:82`/`:97`/`:130`/`:149`. All five tests in `tests/test_auth.py::TestRateLimiting`
assert the bare scalar.

**Evidence** — The five assertion sites are `test_auth.py:277-278`, `:290-291`, `:294-295`, `:331-332`, `:368-369`,
`:387-388` and `:391-392`; the input's list of five ranges omits `:331-332` and duplicates the second test, so it
names five ranges but not five distinct tests — recorded as VAL-09-008. Runtime confirms all five fail on their first
scalar assertion: `assert (True, None) is True` ×3, `assert (False, 300) is False` ×1, and
`assert (True, None) is True` for `IP1 attempt 1 should be allowed`. The input's evidence sentence — "All five fail
on their first assertion with `AssertionError: Attempt 1 should be allowed`" — is accurate for three of the five and
not for `test_rate_limiter_fail_open_on_redis_error` or `test_rate_limiter_fail_closed_on_redis_error`, whose
messages are their own. `tests/test_rate_limiting.py:206`, `:221`, `:225` and `:241` unpack the tuple correctly,
which is what makes the return type unambiguous to the suite.

**Consequence** — Unchanged, and correct: over-limit blocking, the `fail_closed` switch and per-key isolation are
currently unasserted anywhere in the backend suite.

**Recommendation** — Carried out, and the input's sequencing advice is the sound part of the whole report: unpack the
tuple **before** CI is introduced, because a gate introduced red is the first thing disabled. One correction: the
input defers the fail-open tests' *intent* to **AUTH-002**, which is not that finding. AUTH-002 is "A password reset
commits the new credential even when the store that must deliver it refused the value" and owns `TempPasswordStore`
(`core/temp_password_store.py:47-48`). No filed finding owns the rate limiter's fail-open default. See VAL-09-004.

### TST-011 — three shipped layout tests assert the legacy 422 format the project forbids

**Severity** — MEDIUM

**Verdict** — confirmed for two of the three; the third is mis-diagnosed and needs a different fix; band upheld at MEDIUM

**Zone** — Declared test-layer contracts, and whether anything holds them

**Observation** — `src/mkobi/utils/exceptions.py:263-297` registers a `RequestValidationError` handler that returns
an RFC 7807 body with `detail="Request validation failed"` (`:280`), `code=ErrorCode.VALIDATION_ERROR` (`:281`) and a
**top-level** `errors` array (`:291-297`) — the field-level details are not inside `detail`.
`tests/test_layouts.py:366-367` and `:383-384` read `errors = data["detail"]` and assert
`isinstance(errors, list)`. The third test named by the finding, `test_create_layout_duplicate_name_returns_400`
(`:389-409`), does **not** make that assumption: it asserts `status_code == 400` at `:407` and
`"already exists" in data["detail"].lower()` at `:409`, which requires `detail` to be a **string**.

**Evidence** — Runtime, this environment. The two 422 tests fail with
`AssertionError: assert False / + where False = isinstance('Request validation failed', list)`, matching the input's
quote. The third fails with `AssertionError: assert 422 == 400 / + where 422 = <Response [422 Unprocessable
Entity]>.status_code / + and 400 = status.HTTP_400_BAD_REQUEST` — a **status-code** mismatch, not a shape mismatch.
The route explains it: `src/mkobi/api/routes/layouts.py:104-109` catches the duplicate-name `ValueError` and raises
`AppException(code=ErrorCode.VALIDATION_ERROR, …)`, which `_ERROR_CODE_STATUS_MAP`
(`exceptions.py:56`) maps to `HTTP_422_UNPROCESSABLE_CONTENT`.

**Consequence** — The consequence the input states holds for the two 422 tests: three tests currently reject
behaviour the project mandates, and left alone they are a standing instruction to remove RFC 7807 from the validation
path. It does **not** hold for the third, whose actual content is different and arguably worse: a shipped test
asserts a `400` for a duplicate resource while the product has been changed to answer `422` for it, so the test is
pinning a status code the product no longer emits for any reason the input gives.

**Recommendation** — Split. For the two 422 tests, the input's remedy is correct and executable: assert
`data["code"]` is an `ErrorCode`, that `type`/`title`/`status`/`detail` are present, `status == 422`, and read the
field-level list from the **top-level `errors` key** the handler writes at `:295` — not from `detail`. For the third,
the input's remedy is wrong and must not be applied: rewriting it against the RFC 7807 body leaves it asserting 400
against a 422 response. It needs a decision about whether a duplicate layout is a conflict (409, per
`ErrorCode.DUPLICATE_RESOURCE` at `exceptions.py:68`) or a validation failure (422, as coded today), and the test
must follow that decision rather than be restated in the new format.

### TST-012 — `async_db_session.commit()` commits for real, so test data outlives the test

**Severity** — MEDIUM

**Verdict** — confirmed and upgraded from static proof to a direct runtime measurement; band upheld at MEDIUM

**Zone** — Reproduction: what varies per run, and what a shared resource carries forward

**Observation** — `conftest.py:468-497` documents the fixture as "Starts a SAVEPOINT before each test … Automatically
rolls back the SAVEPOINT at the end … No TRUNCATE needed" (`:472-476`). The implementation opens a nested transaction
at `:491` and rolls back in `finally` at `:496`, but the root transaction is auto-begun and SQLAlchemy's
`Session.commit()` commits the root rather than the savepoint. `conftest.py:463` builds the sessionmaker with
`expire_on_commit=False`.

**Evidence** — **Direct runtime measurement, in this environment, at this commit.** After a pytest process had
exited, `psql -d bidb_test` returned: `users` **2** rows (`sole_admin_8f73d1d5@example.com`,
`viewer_7f2f4c82@example.com`, both `created_at 2026-09-30 14:15:23–24`), `processing_logs` **8**, `graphs` **5**,
`dashboards` **10**, `layouts` **0**, `aggregated_data` **0**. The two users were created at
`tests/test_users_api.py:105-120` and committed at `:111` and `:120` — inside the test, inside the fixture's scope,
and still present after the process that created them had terminated, with the fixture's `rollback()` at `:496` long
since executed. `conftest.py:431` sets `recreate_test_db=True` and `:433` calls
`DatabaseStarter.recreate_test_database()`, which unconditionally issues `DROP DATABASE IF EXISTS` /
`CREATE DATABASE` (`src/mkobi/db/starter.py:254-259`), so the rows do not survive into the *next* session — they
accumulate across every test within one session, which is exactly the failure mode the input predicts and the reason
the observed failure count is unstable. The input's static proof is corroborated by the shipped compensating
measures: `tests/test_processing_logs.py:330-338` opens with the comment "Clean up any existing PROCESSING logs with
None dashboard_id for test isolation" and issues `delete(ProcessingLog)` + `commit()`; `:394-403` issues a broader
delete with no `dashboard_id` filter.

**Consequence** — Unchanged, and now measured rather than reasoned. A test that reads a global count is a function of
what ran before it in the same session: `tests/test_users_api.py:101` asserts
`len(remaining) == 0` after deleting every user, and this validator observed it red three times with three different
counts — `assert 7 == 0` in the full suite, `assert 1 == 0` paired with one other test, `assert 3 == 0` alone. The
input's xdist corollary (`PYTEST_XDIST_WORKER` handled at `conftest.py:143-152`, partition deciding the result) is
stated as reasoning and is not separately measured here.

**Recommendation** — Carried out, and the input's two options are correctly ranked: SQLAlchemy's "join an external
transaction" recipe (`connection.begin()` with the session bound to it, so `Session.commit()` nests) is the fix that
also removes the two cross-test `DELETE`s; the honest alternative is to drop the docstring's claim and add explicit
per-module truncation. Either way the docstring at `:472-476` must stop describing behaviour the fixture does not
have.

### TST-013 — one test's config mutation leaks into every test that follows it in the same worker

**Severity** — MEDIUM

**Verdict** — confirmed on its primary anchor; one secondary anchor is stale and the affected-module list is incomplete; band upheld at MEDIUM

**Zone** — Reproduction: what varies per run, and what a shared resource carries forward

**Observation** — `tests/test_rq_worker.py:148-165` monkeypatches eleven environment variables (`REDIS__HOST`,
`REDIS__PORT`, `REDIS__DB`, `ENV`, five `DATABASE__*`, `JWT__SECRET_KEY`, `DATABASE__TEST_DBNAME`) at `:150-160` and
calls `clear_config_cache()` at `:164`. `src/mkobi/config.py` holds `_settings: Settings | None = None` at `:975`
(this validator: `:969`), `get_config(*, reload: bool = False)` at `:978` (this validator: `:972`) which returns the
cached instance whenever it is not `None`, and `clear_config_cache()` at `:997` (this validator: `:991`) as the only
reset. `monkeypatch` restores `os.environ` at teardown; nothing clears `_settings`.

**Evidence** — The primary anchor resolves exactly and has not moved. The mechanism is confirmed statically and the
leak window is narrower than the input states: the input lists eight modules after `test_rq_worker.py` in collection
order, and the actual sorted order of `tests/` puts **ten** modules after it — `test_security.py`,
`test_services_integration.py`, `test_starter.py`, `test_storage_manager.py`, `test_streaming_size_limit.py`,
`test_time_utils.py`, `test_token_revocation.py`, `test_upload_api.py`, `test_users_api.py`, `test_validators.py` —
of which `test_starter.py:68` and `:91` call `clear_config_cache()`, bounding the real exposure to
`test_security.py` and `test_users_api.py`. The input's second and third call-site anchors do not hold:
`tests/test_cors.py:19-24` does resolve (`:20-21` `os.environ.setdefault`, `:24` `clear_config_cache()`), but
**`tests/test_config.py:30-70` does not** — that file was rewritten by the concurrent remediation and now carries 67
`clear_config_cache()` calls, the first at `:528`. Recorded as VAL-09-008. **Anchor movement under this validation:**
`src/mkobi/config.py` and `tests/test_config.py` were edited in the working tree by the concurrent remediation team
*during* this validation — `git status --porcelain` changed from the Appendix A baseline to include
` M src/mkobi/config.py`, ` M tests/test_config.py` and `?? .tmp/`, with `HEAD` still `b23a9cb`. The `config.py` edit
adds a `model_fields` guard to `_secret_field_env_names` at `:365` and shifts everything below it by **+6 lines**,
which is why the three anchors the input cites (`:969`, `:972-988`, `:991-998`) now read `:975`, `:978-994`,
`:997-1004`. The mechanism, the singleton and the absence of a teardown are unchanged, so the finding and its band
stand; the line numbers are recorded here rather than silently re-resolved.

**Consequence** — Unchanged in kind: every test between a `clear_config_cache()` call and the next one reads
configuration built from a previous test's throwaway values, including a different JWT secret from the one
`conftest.py:27` installs. The suite does not fail today, which is the finding.

**Recommendation** — Carried out and executable: an autouse function-scoped fixture in `conftest.py` that calls
`clear_config_cache()` on teardown. It closes the three call sites the input names and any future one, and it is the
only remedy that survives the concurrent remediation's own additions to `tests/test_config.py`.

### TST-014 — the declared frontend gate deletes fifteen tracked files from the repository

**Severity** — MEDIUM

**Verdict** — confirmed and strengthened; its asserted cause is refuted; band upheld at MEDIUM

**Zone** — What runs before a change lands, and what each gate's scope excludes

**Observation** — `frontend/coverage/` is a **tracked** directory: `git ls-files frontend/coverage` returns exactly the
fifteen files the input enumerates, from `index.html` and `coverage-final.json` to per-module HTML and the istanbul
assets. `.gitignore:39-52` covers `htmlcov/`, `.coverage`, `.coverage.*`, `coverage.xml` and `*.cover` but **not**
`coverage/`; `frontend/.gitignore` exists and does not mention coverage at all. `frontend/package.json:10` runs
`vitest run --coverage`, which `Makefile.ps1:237-238` (`Invoke-FeTest`) forwards to.

**Evidence** — Reproduced twice, and the input's asserted cause is refuted by the reproduction. The input states that
vitest deleted the fifteen tracked files "and no coverage report to replace them, **because the run was red**". This
validator ran `npx vitest run --coverage src/shared/types/__tests__/enums.test.ts` — a **green, single-file** run that
exited 0 and printed its coverage summary — and `git status --porcelain -- frontend/` then reported **6 deletions,
4 modifications and 1 new untracked file**: deleted `features/auth/model/index.html`,
`features/auth/model/useAuth.ts.html`, `shared/api/errorHandler.ts.html`, `shared/api/index.html`,
`shared/types/enums.ts.html`, `shared/types/index.html`; modified `base.css`, `coverage-final.json`, `index.html`,
`prettify.css`; created `frontend/coverage/enums.ts.html`. The wipe is unconditional — it is the reporter's
clean-the-output-directory step, not a consequence of failure — and a green run is *worse*, because it replaces
part of the directory and leaves the tree dirty in a way that reads as a partial edit. A subsequent full
`npm run test` left all **15** paths dirty, matching the input's count.

**Restoration — verified.** The input claims the tree was returned to baseline. It was: at the start of this
validation `git status --porcelain -- frontend/` was **empty**, identical to the input's Appendix A assertion. This
validator re-dirtied it by running the gate twice, and restored it with `git checkout -- frontend/coverage` plus
removal of the one newly generated untracked file, re-verified as empty. The repository-wide `git status --porcelain`
is now byte-for-byte the baseline: 20 deleted `.ai` paths and 9 untracked `.ai/audit` / `.ai/plans` paths, no tracked
source or test file modified.

**Consequence** — Unchanged, and slightly broader than the input states: running the project's own gate dirties the
working tree on **every** run, green or red, so `git add -A` after any `fe-test` commits the removal or the
rewrite of a tracked report. Because the report is what a reader consults for "how much of the frontend is covered",
the artefact that would have exposed TST-004 is the artefact the gate destroys.

**Recommendation** — Carried out and executable, and the ordering the input gives is the right one: `git rm --cached`
the fifteen files and add `coverage/` to `frontend/.gitignore` **in one commit**, so no intermediate commit records a
mass deletion. No shipped test breaks.

### TST-015 — the client and the server enforce different password policies, and the one test that shows it is the red one

**Severity** — MEDIUM

**Verdict** — re-typed: the observation and the red test are this phase's; the product-side divergence and its remedy are filed outside this phase's declared scope

**Zone** — Each boundary, from each side — including the ones every test crosses the same way

**Observation** — The server's rule is `validate_password_or_raise` (`src/mkobi/utils/validators.py:183-205`): at
least `min_length` (8) characters, at least one digit (`:199-200`), at least one letter in either case (`:202-203`).
It governs `POST /auth/change-password` through `ChangePasswordRequest.validate_new_password_field`
(`src/mkobi/models/auth.py:203-208`). The client's rule is `changePasswordSchema.new_password`
(`frontend/src/shared/types/formSchemas.ts:56-59`): at least 8 characters, at least one **uppercase** letter, at
least one digit. The client's rule is a strict superset.

**Evidence** — Both anchors resolve and the divergence is exactly as stated. `npm run test` reproduces the input's
failure character for character:
`src/shared/types/__tests__/formSchemas.test.ts > changePasswordSchema > accepts matching passwords`,
`AssertionError: expected false to be true` at `:162`, with `confirm_password: 'newpassword123'` at `:160` — 14
characters, a digit and lowercase letters, which satisfies the server's rule and fails the client's for want of an
uppercase letter. The reverse direction is closed: anything the client accepts satisfies the server's rule.

**Consequence** — Unchanged. A user who reads the server's policy and complies with it cannot change their password
through the product, and the message they see is one the server never sent and cannot produce.

**Recommendation** — Split, and the split is the substance of this verdict. The input's chosen direction — relax the
client's `new_password` to match the server's existing `validate_password_or_raise`, keeping the test's current
expectation — is correct on the merits and is the smaller change, because the server already has one implementation
and the registration path already uses it (`services/auth_service.py:151`). But that remedy **edits a production
frontend file**, and phase 09's own scope paragraph assigns "client-side component, state and accessibility behaviour"
to **phase 13**. What is this phase's is the red test: a shipped assertion that encodes a divergence, which by
AGENTS.md is a remediation blocker that must change with the fix rather than a gate. See VAL-09-003.

### TST-016 — no test observes whether a seeder run destroys uploaded data

**Severity** — MEDIUM

**Verdict** — confirmed; its cross-reference gates the wrong finding; band upheld at MEDIUM

**Zone** — Decisions the product acts on, and the value of each an assertion would reject

**Observation** — `src/mkobi/db/seeders/test_media_dash.py:128-129` runs
`await db.execute(delete(Graph).where(Graph.dashboard_id == dashboard_id))` on every invocation, under the comment
"Delete existing graphs for this dashboard (idempotent - ensures clean state)". `aggregated_data.graph_id` is
`ForeignKey("graphs.id", ondelete="CASCADE")` (`src/mkobi/db/models/aggregated_data.py:77-81`), so the delete takes
every uploaded dataset for the seeded dashboard with it. `src/mkobi/db/starter.py:176-177` calls `run_dev_seeders()`
on every development start.

**Evidence** — The seeder anchors resolve exactly, and the cascade is confirmed at the FK. The test-side gap is
confirmed: `tests/test_dev_seeders.py:70` asserts `len(graphs) == 2  # Should still be 2, not 4`, which holds
identically whether the seeder updates the two graphs in place or deletes and recreates them; and
`tests/test_dev_seeders.py` contains **zero** references to `AggregatedData`, so no test in the file creates an
upload before running the seeder. The input's call-site count is wrong — a scan of `tests/*.py` for
`ensure_test_media_dash` and `run_dev_seeders` returns **30** matches, not 12 — but all 30 are in
`test_dev_seeders.py`, which is the part the claim turns on.

**Consequence** — Unchanged. The decision "does re-seeding a dashboard preserve its data" is made on every
development start and is asserted in neither direction.

**Recommendation** — Carried out and executable, and the second half of it is the better half: tighten `:70` to assert
graph **identity** (`id`s unchanged) rather than count, so the test stops being blind to which implementation ran.
One correction the reader must apply: the input states that **TXN-003** owns the defect. TXN-003 is "The documented
stale-processing backstop can never fire, because no committed log row is ever in `processing`", which is the worker
sweep, not the seeder. The finding that owns the seeder is **TXN-008**, "The development seeder deletes the seeded
dashboard's graphs on every process start, and the cascade takes every uploaded dataset with them". A test gate
attached to TXN-003 would not gate TXN-008's remediation. See VAL-09-002.

### TST-017 — the `slow` and `fast` markers are registered, used by zero tests, and `fast` describes a path the harness does not have

**Severity** — LOW

**Verdict** — confirmed; band upheld at LOW

**Zone** — The harness as a system: schema build, isolation model, marker wiring

**Observation** — `pyproject.toml:200-203` registers `slow` and `fast`, and `addopts` at `:196` carries
`--strict-markers`, so an unregistered marker is a hard error and a registered one is silent. No `coverage` marker is
applied by any test: a scan of `tests/` for `pytest.mark.slow` and `pytest.mark.fast` returns **no files found**. The
`fast` description names a schema-build strategy the repository does not use — `conftest.py:433` always calls
`DatabaseStarter.recreate_test_database()`, and the only `create_all` in the codebase is
`src/mkobi/db/session.py:110` inside `init_db()`, which nothing in the test path calls.

**Evidence** — Every anchor resolves, and the `create_all` census is exhaustive: the only occurrence of
`create_all` in `src/` or `tests/` is `src/mkobi/db/session.py:110`; the only other occurrences are the marker's own
description at `pyproject.toml:202` and the input's report text.

**Consequence** — Unchanged, and the input's framing of it is right: the LOW band is correct because the defect is
the false model, not a runtime effect. A maintainer who reads `pyproject.toml:202` has a reasonable but false model
of how the schema can be built, and no test failure will correct it.

**Recommendation** — Carried out and executable: delete the `fast` marker, and keep `slow` only if a `-m slow` split
is actually intended — in which case mark the handful of tests that deserve it and add `-m "not slow"` to `addopts`.
The input offers this as a choice; the template requires one direction, and deleting both is the one that matches the
evidence, since no test is slow-marked today either.

### TST-018 — the enum-consistency module claims a two-way check it performs one way for two of three enums

**Severity** — LOW

**Verdict** — confirmed; band upheld at LOW

**Zone** — Declared test-layer contracts, and whether anything holds them

**Observation** — All three enums are native PostgreSQL types: `Enum(UserRole, name="user_role", …)` at
`src/mkobi/db/models/user.py:52-54`, `Enum(DashboardPermission, name="dashboard_permission_level", …)` at
`access.py:44-46`, and `Enum(ProcessingStatus, name="processing_status", …)` at `processing_logs.py:44-46`.
`tests/test_enum_db_consistency.py:1-7` states the module "Verifies that Python StrEnum values match PostgreSQL ENUM
types defined in migrations" and "After DB-001 migration, there should be zero extra values in the database."

**Evidence** — Every anchor resolves and the asymmetry is exactly as claimed.
`test_processing_status_values_match` (`:169`) is the only two-way check: `missing_in_db` at `:179`/`:182-184` and
`extra_in_db = db_values - python_values` at `:187`/`:188-191`. `test_user_role_values_match` (`:66-77`) asserts
`missing_in_db` alone (`:73`, `:75-77`); `test_dashboard_permission_values_match` (`:107-120`) likewise (`:116`,
`:118-120`); and `test_all_enums_consistent` (`:230`) computes only `python_values - db_values` (`:248`) — while its
own docstring at `:233-235` claims it fails "if DB has extra values (indicates schema drift)". The module docstring's
promise is therefore contradicted by its own code in two places.

**Consequence** — Unchanged. A value added to `user_role` or `dashboard_permission_level` by a migration and left
behind after the Python enum is narrowed is invisible to the only place in the suite that looks at `pg_enum`, and a
PostgreSQL enum type cannot drop a label without recreating the type — so a stale label is the realistic failure mode,
which is precisely the one the module says it guards.

**Recommendation** — Carried out and executable: extract the two-way comparison already written at `:179-191` into a
helper and call it from all three classes. Four lines, and it makes both docstrings true.

## Distribution

The findings fall on the boundary between the test layer and the product, and on the harness that owns that boundary.
**The `async_client` fixture and the persistence session it substitutes carry the most** — six findings across
TST-005, TST-006, TST-008, TST-012, TST-013 and TST-015 — and every one of the six is a consequence of that one
fixture substituting `get_db_dependency`, the Redis dependency, the temp-password store and the transport.

- **The gates and their invocation** — TST-001, TST-002, TST-003, TST-004, TST-014. Nothing in the repository can
  stop a change, both suites are red, and neither coverage measure measures what it appears to.
- **The harness's session lifecycle** — TST-007, TST-009, TST-016, TST-017, TST-018. The session-parameter branch
  every worker test takes, the mock session three service modules assert against, the marker and contract surfaces.
- **Stale shipped assertions** — TST-010, TST-011, TST-013. Five written against a changed return type, three against
  a format the project forbids, one config mutation with no teardown.

## Cross-Finding Analysis

The input names two causes and states that they account for thirteen of eighteen findings. **The tally does not
agree with the enumeration** and is recorded as VAL-09-005: counting the identifiers the two causes actually name
gives seven (TST-007, TST-010, TST-011 under the first; TST-005, TST-009, TST-012, TST-013 under the second), plus a
fourth item described but never given an identifier — `UserDB.updated_at`, which is
`tests/test_pydantic_models.py::TestUserModels::test_user_db_valid`, one of the ten red tests — while five findings
(TST-002, TST-006, TST-008, TST-015, TST-016) are attributed to no cause at all. The input's own second clause, that
TST-002 is "why the other twelve are silent", uses twelve, not thirteen, and is the arithmetically consistent figure.

The two causes it names are nonetheless real and do carry the phase:

**Cause one — a test-layer decision was made once and never re-derived when the thing it stood in for changed.**
The `session: AsyncSession | None` parameter chose the branch that works and every shipped test takes it (TST-007).
`check_rate_limit` changed from `bool` to `tuple[bool, int | None]` and five assertions were not revisited
(TST-010). The error format moved to RFC 7807 and three assertions were not revisited — two of them correctly, one
of them for the wrong reason (TST-011). In each case the production change was right, the test was left behind, and
nothing flags it red because nothing runs the suite.

**Cause two — a shared fixture makes a decision invisible by resolving it before the code under test can.** Three
`MockRedis` instances where the route reads one (TST-005). A `mock_db` that absorbs every constraint (TST-009). A
savepoint rollback that a `commit()` releases (TST-012), now measured rather than reasoned. A config singleton that
survives a `monkeypatch` teardown (TST-013). Different fixtures, same shape: the harness answers a question the test
was supposed to ask.

TST-001, TST-003, TST-004, TST-014, TST-017 and TST-018 are independent of both and of each other, exactly as the
input states.

**One cause the input's own analysis contains but never names.** The red-test list is unstable: this validator ran
identical code three times and the runs differ. That is not a separate finding — it is TST-012 observed from the
outside — but the input presents `10 failed, 1003 passed` as a reproducible fact and builds its Step 0 roadmap on the
figure, without recording that the suite's isolation defect makes the figure move. That is VAL-09-001, and it is the
most consequential defect in the audit, because it is the one that makes the input's own remediation plan
non-deterministic.

**Overlaps with sibling reports, ruled on the merits.** Six sibling reports were compared: the raw reports of phases
01 through 07, the raw report of phase 08, and the validated reports of phases 01 through 07.

- **TST-002 × QLT-003 — merge.** Identical root cause on two claims. Both state that `Invoke-Check` (`:241-249`)
  chains lint → typecheck → fe-lint → fe-test and does not reach the backend suite, and both state that nothing wires
  a gate to an automated path. QLT-003's Recommendation ("add a `test` invocation to `Invoke-Check` so the aggregate
  matches the declared gate list") is TST-002's first recommendation in the same words. The claims that remain are
  **adjacent, not merged**: QLT-003 owns ruff `F401` and two mypy `arg-type` errors being red and the short-circuit
  hiding `typecheck`/`fe-lint`/`fe-test`; TST-002 owns the eleven backend and frontend *test* failures. **Phase 09 owns
  remediation of the merged root cause**, on the strength of its own scope paragraph: "The merge-blocking question —
  whether a change can reach a deployed system at all — is this phase's for the suite and the aggregate entry point."
  Phase 08 retains the lint/typecheck-red half. Neither identifier is renumbered; the merge is recorded here and in
  TST-002's verdict rather than applied to either report.
- **TST-002 × TOPO-007 — cross-reference, distinct.** TOPO-007 ("The migration entry surface is outside both
  automated quality gates") is about one command (`alembic upgrade`) being outside the gate list. TST-002 is about
  the whole backend test tree being outside it. Adjacent, same parent, neither duplicates the other. Phase 01 keeps
  TOPO-007; TST-002's recommendation does not address it and should not be read as doing so.
- **TST-015 × QLT-007 — adjacent, distinct.** QLT-007 is "The client mirrors the server's fixed values in a second
  home with no equality check", and its subject is `frontend/src/shared/types/enums.ts` mirroring eight StrEnum
  families, with `BarmodeEnum`'s `ChartRenderer.tsx:149` cast as the live divergence. TST-015's subject is
  `frontend/src/shared/types/formSchemas.ts` mirroring a validation *regex*, not an enum. Different files, different
  rule, different symptom; the shared root cause is a pattern, not an identity. No merge. Both remain; QLT-007 keeps
  the enum mirror, TST-015 keeps the password policy and is re-typed as VAL-09-003 directs.
- **TST-009 × QLT-006 — adjacent, distinct.** QLT-006 is about ten providers in `src/mkobi/api/deps.py` annotated
  `-> Any`; TST-009 is about `tests/conftest.py`'s `mock_db` being `AsyncMock(spec=AsyncSession)`. The shared subject
  is the DI layer's type width, but TST-09's finding is that the *test double* absorbs constraints, which no
  annotation in `deps.py` causes. No merge.
- **QLT-001, QLT-002 — no overlap.** Neither TST-009 nor any other phase-09 finding examines
  `POST /dashboards/{id}/access` or the grant endpoints. QLT-001's zone is "Fixed values: one named home per value"
  and QLT-002's is "Declared contracts and their enforcement point"; phase 09 never entered either zone. Distinct,
  and phase 12 owns the access decision QLT-002 deferred to it. No phase-09 finding contests or duplicates either.
- **No phase-09 finding re-files a defect another phase owns.** This was checked claim by claim, because it is the
  input's own claim and the seam check is this validation's: TST-006 names AUTH-001 and asserts its production
  consequence in order to establish a test-side one; TST-007 names TOPO-001 and cites `data_worker.py:552-620`;
  TST-008 names TOPO-004 and TXN-001; TST-016 names TXN-003 and cites `test_media_dash.py:128-129`; TST-010 names
  AUTH-002. Four of those five point at the right finding and one does not (VAL-09-002), and one points at a finding
  that does not cover its subject (VAL-09-004). No duplicate filing was found.

## Roadmap

The input's four-step ordering is sound and this validator keeps it, with five corrections established above. The
ordering principle it states — a gate introduced before the suite is green is a gate that gets disabled — is the
right reason for the sequence and nothing else should reorder it.

**Step 0 — unblock the suite (TST-010, TST-011).** Unpack the tuple in the five `test_auth.py::TestRateLimiting`
assertions. Rewrite the two 422 assertions in `test_layouts.py` against the RFC 7807 body, reading field-level
details from the **top-level `errors` key** `exceptions.py:295` writes. **Correction:** do not apply the same
rewrite to `test_create_layout_duplicate_name_returns_400` — it fails on `422 != 400`, and needs the conflict-versus-
validation decision first (see TST-011). **Correction:** this step also clears
`test_users_api.py::TestDeleteAccount::test_admin_cannot_delete_self` and
`test_e2e_upload.py::TestE2EUploadWorkflow::test_e2e_multiple_graphs_same_dashboard`, which are red in two of three
runs of identical code and are in no list the input gives (VAL-09-001). Must be true before step 1:
`.\Makefile.ps1 test` and `npm run test` exit 0 — and, until TST-012 is fixed, "exit 0" has to be demonstrated on
more than one run.

**Step 1 — close the vacuous paths (TST-005, TST-007, TST-009, TST-016).** One `MockRedis` per test instead of three —
covering `services/auth_service.py:66-67` as well as the fixture, or the route and the service keep two stores. One
test per recovery function calling it with `session=None`. The auth/graph/layout subset moved to the real session.
One test that an upload survives a seeder run. **Correction:** that last test is the gate for **TXN-008**, not
TXN-003 (VAL-09-002). Must be true before step 2: each of the four decisions is observed from a failing-direction
test.

**Step 2 — make the gates real (TST-001, TST-002, TST-014, and the coverage halves of TST-003, TST-004).** Bind-mount
`src` and `tests` into `test-app`; add `Invoke-Test` to `Invoke-Check`; `git rm --cached frontend/coverage` and
ignore it in one commit; add `--cov=src/mkobi` to `addopts` and delete the duplicated `fail_under`; add
`coverage.include` to `vite.config.ts`; add one CI workflow running `test-all` and `npm run test`. **Correction:**
this step must be reached from a *stable* baseline, and it cannot be while the failure count moves — step 0 and
step 1's fixture work are what make the count stable, so the TST-012 remedy belongs here rather than in step 3.
**Correction:** the `Invoke-Test` addition is shared with **QLT-003**; phase 09 owns it, and phase 08 retains the
lint/typecheck-red half.

**Step 3 — settle the reproduction and hygiene items (TST-006, TST-008, TST-012, TST-013, TST-015, TST-017, TST-018).**
Low risk, independently revertible. TST-006 belongs here rather than earlier because it must be rewritten alongside
AUTH-001's fix, not ahead of it. TST-015's *test* belongs here and its *remedy* belongs to phase 13 (VAL-09-003).

**Cross-phase dependencies, restated.** TST-006 gates **AUTH-001** and must land with it. TST-007 gates **TOPO-001**.
TST-016 gates **TXN-008**, corrected from TXN-003. TST-008 makes **TXN-001** observable and should precede phase 03's
remediation so that remediation has something to fail against. TST-015's policy decision needs phase 13, or whoever
owns authentication; the assertion fix is here. **Newly owned by no one:** the rate limiter's fail-open default,
which TST-010 defers to AUTH-002 in error (VAL-09-004) — it needs an owner before it can be scheduled.

## Rollout Safety

Step 0 is the only step that changes what the suite asserts without changing what the product does, and it is the
step most likely to be misread. Unpacking a tuple is not weakening an assertion — the same value is asserted, just
destructured. Rewriting the two 422 assertions against the RFC 7807 body *does* change what they accept: a response
returning a bare-string `detail` without the top-level `errors` array will now fail them. That is the intended
direction and makes these two the first thing to catch a regression back to the legacy format. The third layout test
must not be swept along with them: rewriting it into the RFC 7807 shape while leaving `assert status == 400` would
convert a currently-loud failure into a differently-worded loud failure, and deciding whether a duplicate layout is a
409 or a 422 is a product decision that changes the API contract.

Step 1 adds tests and changes two fixtures. The `MockRedis` consolidation is the one to watch: it will change what
three currently-passing rate-limit tests observe, because they will start reading the store the route actually wrote
to. If any of them fails after the change, that is the test doing its job for the first time, not a regression —
investigate before relaxing anything. Adding `session=None` coverage for the worker sweeps will create and commit
rows in `bidb_test` on paths that previously ran against a mock; combined with TST-012's commit-persists behaviour,
budget for cross-test interference and fix the fixture in the same change.

Step 2 changes the harness the whole suite runs in. The bind mount in TST-001 is the highest-risk single change in
this report: it swaps the `test` target from a known-good image to live host files, so for the first time the suite
will read whatever is currently in the working tree, including uncommitted work. Expect a first run to fail in ways
it never has. That is the point, and it is why step 2 follows step 0. Untracking `frontend/coverage/` is a single
`git rm --cached` plus a `.gitignore` line; do both in one commit so no intermediate commit records a mass deletion.
This validator established that the current gate dirties that directory on **every** run, so after the change the
tree stops moving — which is worth verifying in the same commit. Adding `--cov=src/mkobi` to `addopts` turns
coverage measurement on for every pytest invocation, a measurable slowdown on a 5-minute suite, and may push the
first measured number under the 65 floor; read that number before deciding it is a problem, and fix the coverage
rather than the floor.

Every step reverts by a single commit revert. Only TST-015 touches a production file, and there the production file
is on the client and is phase 13's to change.

## Appendices

**A. Coverage ledger.** Nine blocks are declared by `.kilo/commands/audit/phases/09-audit-test-coverage.md`. Blocks
examined: 9 of 9, each reached by at least one finding — block 1 by TST-007/010/016, block 2 by TST-005, block 3 by
TST-009, block 4 by TST-006/008/015, block 5 by TST-017, block 6 by TST-012/013, block 7 by TST-001/002/014, block 8
by TST-003/004, block 9 by TST-011/018. Zone-verbatim check: 17 of 18 findings quote their block title exactly;
TST-017's Zone truncates block 5's title at "marker wiring" and drops ", and the separately executed suites"
(VAL-09-010).

Item counts each block actually reached: block 1 — three findings plus one described defect with no identifier;
block 2 — one; block 3 — one; block 4 — three; block 5 — one; block 6 — two; block 7 — five findings plus two red
gates; block 8 — two, with both coverage measures executed at runtime; block 9 — two, plus one test-layer comment
found to contradict its own code inside TST-018's own evidence.

**B. What was executed in this validation, and at which tree.** `git rev-parse HEAD` → `b23a9cb`; `git status
--porcelain` → 20 deleted `.ai` paths and 9 untracked `.ai/audit` / `.ai/plans` paths, no tracked source or test file
modified — identical to the input's Appendix A. `_b3_full_out.txt`, named in the task brief as belonging to the
concurrent team, **is not present** at this tree and does not appear in `git status --porcelain`. `HEAD` did not move
during this validation: the series `8505a62 → 2d23c27 → c3c0a61 → 5a2cfb6 → b23a9cb` named in the task brief is the
same series the input's Appendix B describes, and its last element is both the input's baseline and the tree this
validation read. The `mkobi-test-test-app` image is `b6d8cd8b1baa`, created `2026-09-30 16:00:48 +0200`, i.e. **after**
`b23a9cb` (`15:40:39`) — a rebuild by the concurrent team, which is why TST-001's timestamp evidence no longer
reproduces (VAL-09-009). `md5sum` over `find src tests -name '*.py'` inside `test-app` against `Get-FileHash` on the
host: `img=168 host=168`, no differences. Executed: `docker compose … config` (resolved `test-app`), the full backend
suite **three times** (`12 failed / 1001 passed`, `11 failed / 1001 passed + 2 errors`, `10 failed / 1003 passed`),
three targeted backend re-runs, `npm run test` once, `npx vitest run --coverage` on one green file once,
`psql -d bidb_test` row counts and contents after process exit, and `git ls-files frontend/coverage`.

**B2. Files that moved under this validation.** Late in the run the concurrent remediation team's uncommitted changes
appeared: `git status --porcelain` gained ` M src/mkobi/config.py`, ` M tests/test_config.py` and `?? .tmp/`, with
`HEAD` still `b23a9cb`. The `config.py` change is a `model_fields` guard added to `_secret_field_env_names` at `:365`
(`+51 insertions, −3 deletions` across the two files), which shifts every `config.py` anchor below it by **+6 lines**.
Two consequences, both recorded in place: TST-013's three `config.py` anchors moved from `:969`/`:972-988`/`:991-998`
to `:975`/`:978-994`/`:997-1004` — mechanism unchanged, finding and band unaffected; and `tests/test_config.py`'s
first `clear_config_cache()` moved from `:486` to `:528` while its count rose to 67, which sharpens VAL-09-008's
anchor 2. No finding, band, verdict or remediation step in this report depends on either file's line numbers. Nothing
in `src/mkobi/**` that the report's verdicts rest on was touched after the byte-comparison above was taken, so the
`img=168 host=168` equality remains the correct statement of what the three suite runs executed; the two files that
moved afterwards were moving *uncommitted* and are therefore not in that image either.

**C. Not executed, and therefore not characterised.** `.\Makefile.ps1 test-all` — so the measured backend coverage
percentage is unquoted here exactly as it is in the input. `.\Makefile.ps1 check` end-to-end. `.\Makefile.ps1
lint` / `typecheck` — phase 08 owns ruff and mypy. Any `pytest-xdist` parallel run, so TST-012's partition corollary
rests on the code and on the shipped compensating `DELETE`s rather than on an observed parallel failure. Any browser,
lifespan, TLS or real-socket test, so the transport boundary TST-008 describes is reasoned from
`conftest.py:559` rather than measured.

**D. Restoration.** This validator ran the declared frontend gate twice, which deleted and rewrote
`frontend/coverage/` both times. It restored the tree with `git checkout -- frontend/coverage` and removal of the one
newly generated untracked file, and confirmed `git status --porcelain -- frontend/` **empty** on every subsequent
check. The repository status is the Appendix A baseline **plus** the concurrent remediation's own two modified files
and one untracked directory recorded in Appendix B2; no entry in it was produced by this validation. No source file,
test, configuration or documentation file was created, edited, staged, committed, reverted or stashed by this
validation; the only writes are this report and temporary log files outside the repository. Rows this validation's
test runs committed into `bidb_test` were left in place: `conftest.py:433` drops and recreates that database at the
start of every session (`src/mkobi/db/starter.py:254-259`), so they cannot affect a subsequent run, and truncating
them would be a data mutation outside this validation's remit. The `mkobi` dev stack was not started, stopped or
reconfigured; the `mkobi-test` stack was already running and was left running.

## Validation-Level Findings

Defects in the audit itself, on the validation scale, in a separate section because the two scales share a
`Severity` column and would be read as one. The flat `VAL-` prefix is already occupied **twice** — by the phase-01
report (`VAL-001` … `VAL-008`) and the phase-02 report (`VAL-001` … `VAL-009`) — so this report mints the compound
`VAL-09-` form established by the phase-03 through phase-07 reports. That deviation from the flat prefix is the
ruling, recorded as VAL-09-012.

### VAL-09-001 — TST-002 presents one sample of a moving figure as a fixed count, and does not connect it to TST-012

**Severity** — MEDIUM

**Verdict** — new; the reader must repair TST-002's Evidence before acting on it

**Observation** — TST-002's Evidence presents `collected 1013 items` and `10 failed, 1003 passed, 23 warnings in
309.23s` as a runtime fact, and the Summary, the Distribution and the entire Step 0 roadmap are built on the ten named
failures. That figure is a sample. TST-012 states the mechanism that makes it move: `Session.commit()` inside the
fixture's savepoint commits to PostgreSQL, so a test that reads a global count depends on what ran before it in the
same session. The report never connects the two, and its present-state sentence — "both suites are red with 10 and 1
failures" — reads as a fixed inventory.

**Evidence** — Four runs of the same command at `HEAD` = `b23a9cb`, with the image's `src/` and `tests/` proven
byte-identical to the working tree across all 168 Python files (`md5sum` vs `Get-FileHash`, `img=168 host=168`, no
differences) and the resolved `test-app` service proven to have no `volumes` key — so neither the concurrent
remediation nor a stale image can account for the difference:

| Run | Result | Failures beyond the input's list |
|---|---|---|
| input | `10 failed, 1003 passed, 23 warnings in 309.23s` | — |
| this validation, run 1 | `12 failed, 1001 passed, 23 warnings in 316.67s` | `test_e2e_upload.py::TestE2EUploadWorkflow::test_e2e_multiple_graphs_same_dashboard` (`KeyError: 'task_id'`), `test_users_api.py::TestDeleteAccount::test_admin_cannot_delete_self` (`assert 7 == 0`) |
| this validation, run 2 | `11 failed, 1001 passed, 23 warnings, 2 errors in 312.91s` | `test_admin_cannot_delete_self`; the e2e test absent; 2 errors not present in run 1 |
| this validation, run 3 | `10 failed, 1003 passed, 23 warnings in 294.71s` | none — identical to the input, same ten node ids |

**The input is not wrong here; it is one sample short of its own claim.** Run 3 reproduced the input's figure
exactly, which establishes the input's evidence as real. Runs 1 and 2 establish that it is not a constant. The ten
the input names are a strict subset that always fails, plus two that fail depending on what ran before them:
`test_admin_cannot_delete_self` was red in two of three runs with three different counts (`assert 7 == 0`, `assert 1
== 0`, `assert 3 == 0`), and `test_e2e_multiple_graphs_same_dashboard` was red once and passes when run alone, so it
is order-dependent. `psql -d bidb_test` after a process exited returned 2 `users`, 10 `dashboards`, 8
`processing_logs` and 5 `graphs` rows that the tests had created and committed.

**Consequence** — A reader who takes TST-002's figure as the definition of "red" will close Step 0 with the suite
green on one run and two tests silently red on the next, and with no signal that those two exist — they are not in
any list the report gives. The report's own CRITICAL finding rests on a number it did not measure to be stable, while
the report itself files the mechanism that makes it unstable.

**Recommendation** — Restate TST-002's Evidence as "10 failures reproduce exactly; 12 were observed on a second run of
identical code, and the two extra are isolation-dependent" and state that the figure is not stable until TST-012 is
fixed. Add `test_admin_cannot_delete_self` and `test_e2e_multiple_graphs_same_dashboard` to Step 0 as red, and note in
TST-002 that `test-all` will not be reproducible until TST-012's remedy lands.

### VAL-09-002 — TST-016 gates TXN-003, but the seeder defect is filed as TXN-008

**Severity** — MEDIUM

**Verdict** — new; the cross-reference resolves to a finding that does not cover the subject

**Observation** — TST-016 states "**TXN-003** owns the defect; it is not re-filed", and its Roadmap and
Cross-Phase-Dependencies sections both make the recommended upload-survival test the gate for TXN-003's remediation.
Phase 03's own report files TXN-003 as "The documented stale-processing backstop can never fire, because no committed
log row is ever in `processing`" — the worker sweep, not the seeder. The finding that owns the seeder is **TXN-008**,
"The development seeder deletes the seeded dashboard's graphs on every process start, and the cascade takes every
uploaded dataset with them", whose title is the same statement TST-016 makes.

**Evidence** — `.ai/audit/03-db-concurrency/findings.md`: the TXN-003 and TXN-008 headers above. The seeder code the
reference is meant to cover is `src/mkobi/db/seeders/test_media_dash.py:128-129` with
`aggregated_data.py:77-81`'s `ondelete="CASCADE"`, reached from `src/mkobi/db/starter.py:176-177` — which is TXN-008's
subject and not TOPO-001's or TXN-003's.

**Consequence** — A remediation blocker attached to the wrong identifier gates nothing. TXN-008's fix would land
without the test TST-016 prescribes, and the input's own reasoning about that test — that it is "the assertion TXN-003's
remediation needs as its gate" — is exactly right about a finding that is not the one at fault.

**Recommendation** — Correct both occurrences of TXN-003 to TXN-008 in TST-016, its Roadmap and its cross-phase
dependencies.

### VAL-09-003 — TST-015's remedy edits a production client file this phase's scope paragraph assigns to phase 13

**Severity** — MEDIUM

**Verdict** — new; seam check — part of the finding is filed outside the input's own declared scope

**Observation** — Phase 09's Scope Boundaries paragraph owns "whether the suite would notice a wrong product decision,
the fidelity of what it asserts once it does, the harness as a system, and the gates that run before a change lands",
and assigns "client-side component, state and accessibility behaviour and that suite's own architecture" to **phase
13**. TST-015's title, Observation and Consequence are all a product-side statement: a server/client policy
divergence whose user-visible effect is that a compliant user cannot change their password. Its Recommendation is to
"relax the client's `new_password` … to match" — that is, to edit
`frontend/src/shared/types/formSchemas.ts:56-59`, a production client file phase 13 owns.

**Evidence** — The two anchors resolve and the divergence is real (`src/mkobi/utils/validators.py:183-205` versus
`frontend/src/shared/types/formSchemas.ts:56-59`); the seam is in the remedy, not the observation. Phase 09's scope
paragraph is explicit that the merge-blocking question is "this phase's for the suite and the aggregate entry point",
and it names no ownership of a client/server policy decision.

**Consequence** — A remediation plan built from this report alone will edit a file another phase owns, and the other
phase's own audit of the client tier has not been asked about it. Phase 12 also has not run; the input names "phase 12
and phase 13" without saying which of them decides the policy, which leaves the decision unowned twice over.

**Recommendation** — Split TST-015. Keep in phase 09: the red test at
`frontend/src/shared/types/__tests__/formSchemas.test.ts:162`, as a remediation blocker under whichever finding owns
the policy decision. Re-file the policy divergence and the client-side remedy to phase 13, or to phase 04 if the
server's rule is judged to be the one that must change. Name which.

### VAL-09-004 — TST-010 defers the rate limiter's fail-open tests to AUTH-002, which owns a different store

**Severity** — MEDIUM

**Verdict** — new; a real defect is parked on an identifier that does not cover it, so no phase owns it

**Observation** — TST-010 states that `:298-332` and `:334-369` "encode the fail-open default as intended behaviour,
which is **AUTH-002**'s territory and not re-filed here". AUTH-002 is "A password reset commits the new credential
even when the store that must deliver it refused the value"; its Observation is entirely about
`TempPasswordStore.store` failing open at `core/temp_password_store.py:47-48` and
`AuthService.reset_password_admin` committing regardless at `services/auth_service.py:585-590`. It says nothing about
the rate limiter. A scan of phase 04's ten finding headers returns no rate-limiter fail-open finding.

**Evidence** — `.ai/audit/04-authentication/findings.md`'s AUTH-002 Observation, quoted above. The tests in question
are `tests/test_auth.py:298-332` (`test_rate_limiter_fail_open_on_redis_error`, asserting `result is True` against a
`FailingRedisClient`) and `:334-369` (`test_rate_limiter_fail_closed_on_redis_error`, asserting `result is False`).
`src/mkobi/core/security.py:91-103` shows the switch: `fail_closed` defaults to `False`, and the fail-open branch
returns `True` on any `Exception`. The deployment-side control is phase 02's **CFG-006**, which covers
`RATE_LIMITER_FAIL_CLOSED` not being supplied by any deployment — a different question from whether fail-open is the
right default.

**Consequence** — Whether a login rate limiter should fail open or closed is a security decision the report
identifies, pins in two shipped tests, and assigns to nobody. Deferring it to a finding that does not cover it is how
a question disappears from the roadmap.

**Recommendation** — Either file the fail-open default as this phase's own finding — two shipped tests assert it as
intended behaviour, which is the template's remediation-blocker predicate — or correct the reference to the finding
that actually owns it. If CFG-006 is the intended owner, say so and state why the question is the same one.

### VAL-09-005 — the Cross-Finding Analysis claims thirteen findings under two causes and accounts for seven

**Severity** — MEDIUM

**Verdict** — new; the tally disagrees with the enumeration, as the template requires it to

**Observation** — "Two causes account for thirteen of the eighteen findings." Counting the identifiers the two causes
actually name gives **seven**: TST-007, TST-010, TST-011 under cause one; TST-005, TST-009, TST-012, TST-013 under
cause two. Cause one names a fourth item with no identifier at all — "`UserDB.updated_at` became required and one test
was not revisited", which is `tests/test_pydantic_models.py::TestUserModels::test_user_db_valid`, one of the ten red
tests the report itself enumerates in TST-002. Five findings are attributed to no cause: TST-002, TST-006, TST-008,
TST-015, TST-016. The input's own next paragraph uses a different figure — "TST-002 is why the other **twelve** are
silent" — and 18 minus the six it declares independent is twelve, so twelve is the consistent number.

**Evidence** — The two causes and the independent list are quoted verbatim in Cross-Finding Analysis above; the
identifier tally is the arithmetic above. The unfiled `UserDB.updated_at` item is confirmed as a real red test:
`pydantic_core._pydantic_core.ValidationError: 1 validation error for UserDB / updated_at / Field required`, observed
in this environment's run.

**Consequence** — The tally is the report's index. A reader reconciling it against the eighteen findings finds five
unattributed and one described-but-unnumbered, and cannot tell whether the omission is a numbering mistake or a
deliberate exclusion. It also means the report has one red test and one cause with no identifier behind it.

**Recommendation** — Restate as "seven findings under two named causes, plus one described defect with no
identifier, plus five findings belonging to neither", or attribute the five. Give the `UserDB.updated_at` defect an
identifier or drop it from the analysis.

### VAL-09-006 — TST-014 attributes the tracked-file deletion to a red run; the wipe is unconditional

**Severity** — LOW

**Verdict** — new; asserted cause refuted while the finding survives, and the finding is understated

**Observation** — TST-014's Evidence states that vitest "deleted the 15 tracked files … and no coverage report to
replace them, **because the run was red**". Running the gate on a green, single-file selection that exited 0 and
printed its coverage summary deleted tracked files too.

**Evidence** — After `npx vitest run --coverage src/shared/types/__tests__/enums.test.ts` (green, `Tests 21 passed
(21)`, exit 0), `git status --porcelain -- frontend/` reported 6 deletions (`features/auth/model/index.html`,
`features/auth/model/useAuth.ts.html`, `shared/api/errorHandler.ts.html`, `shared/api/index.html`,
`shared/types/enums.ts.html`, `shared/types/index.html`), 4 modifications (`base.css`, `coverage-final.json`,
`index.html`, `prettify.css`) and 1 untracked addition (`frontend/coverage/enums.ts.html`). The red full run left all
15 paths dirty, matching the input's count. The mechanism is the coverage reporter's clean-output-directory step,
which runs before it knows whether the suite passed.

**Consequence** — The finding's stated scope is too narrow in the safe direction. The gate dirties the tree on every
run, so a green `fe-test` is as destructive as a red one and the dirty state looks like a partial edit rather than a
mass deletion. The input's Rollout Safety and Recommendation are unaffected and remain correct.

**Recommendation** — Change "because the run was red" to "on every run, green or red", and note that a green run is
the worse case because it rewrites part of the directory.

### VAL-09-007 — TST-005 overstates the vacuity of `test_login_rate_limit_exceeded`

**Severity** — LOW

**Verdict** — new; one evidence sentence claims less coverage than the test performs

**Observation** — TST-005 says the two passing siblings "pass, because they only assert that a 429 occurs".
`test_login_rate_limit_exceeded` asserts 401 five times before asserting 429, so it does observe the counter
incrementing; what it cannot observe is the contents of the store it declares.

**Evidence** — `tests/test_rate_limiting.py:44-46` asserts
`response.status_code == status.HTTP_401_UNAUTHORIZED` inside the exhaust loop, and `:57-59` asserts 429 afterwards.
`test_different_ips_have_separate_limits` (`:154-193`) has no such inner assertion and is the genuinely vacuous one.

**Consequence** — Overstated vacuity invites a reader to rewrite a test that is doing real work, and makes the
recommendation look like it applies to three tests when it applies to one.

**Recommendation** — Attribute the vacuity to `test_different_ips_have_separate_limits` only, and describe the other
as asserting the transition rather than the store.

### VAL-09-008 — six anchors and counts in the input do not resolve against the tree the report was written at

**Severity** — LOW

**Verdict** — new; recorded, not repaired

**Observation** — Six, of which one is materially stale.

1. `frontend/package.json:9` — `"test": "vitest run --coverage"` is at **`:10`**.
2. `tests/test_config.py:30-70` — cited by TST-013 for "its own env save/restore around a
   `clear_config_cache()`". That file was rewritten by the concurrent remediation; it now carries **67**
   `clear_config_cache()` calls, the first at `:528`. **The range resolves to lines that exist and contain something
   else.**
3. TST-013's list of affected modules names eight modules sorting after `test_rq_worker.py`; the actual sorted order
   of `tests/` places **ten** there, and it omits `test_starter.py` and `test_users_api.py`. It also lists
   `test_streaming_size_limit.py` last, though `st` sorts before `ti`.
4. TST-010's list of five assertion ranges names five ranges but not five distinct tests: `:294-295` is the second
   test's over-limit assertion and `:331-332`, the fail-open test's only assertion, is absent.
5. TST-016's "12 call sites" for `ensure_test_media_dash` / `run_dev_seeders` across `tests/*.py` is **30**; all 30
   are in `test_dev_seeders.py`, which is the claim's load-bearing half.
6. TST-009 quotes `test_graph_service.py:67` as `assert call_args[0][0] is mock_db`; the file has `==`.
7. TST-013's three `src/mkobi/config.py` anchors (`:969`, `:972-988`, `:991-998`) resolved exactly when this
   validation read the file, and shifted **+6** mid-validation when the concurrent remediation added a
   `model_fields` guard at `:365`. They now read `:975`, `:978-994` and `:997-1004`. Recorded under TST-013's
   Evidence as well; the mechanism is unchanged and the band stands.

**Evidence** — Each was resolved mechanically against `b23a9cb`. Anchor 2 is the one that matters: TST-013's
mechanism does not depend on it — `tests/test_rq_worker.py:148-165` alone carries the finding — but a reader checking
the third call site finds nothing there. Anchor 7 was produced by the concurrent remediation after the first six were
resolved, and is recorded so a later validator does not read it as a citation the phase got wrong.

**Consequence** — None of the seven changes a verdict. Two of them, anchors 2 and 7, were produced by the concurrent
remediation and will read to a later validator as citation errors.

**Recommendation** — Correct the five mechanical items; for anchor 2, replace the `test_config.py` citation with the
`tests/conftest.py:410-413` session-scope `clear_config_cache()` that the file's rewrite left in place.

### VAL-09-009 — TST-001's timestamp evidence no longer reproduces; the finding stands on configuration

**Severity** — LOW

**Verdict** — new; a point-in-time observation superseded, recorded because it is the evidence the finding leads with

**Observation** — TST-001's Evidence leads with "image … `CREATED 2026-09-30 15:33:38 +0200`, while `git log -1
-- src/` gives `b23a9cb 2026-09-30 15:40:39` — the image predates HEAD by seven minutes". The image has since been
rebuilt and is now **newer** than `HEAD`.

**Evidence** — `docker images mkobi-test-test-app` reports `b6d8cd8b1baa … CreatedAt 2026-09-30 16:00:48 +0200`
against `git log -1 --format='%h %cd' --date=iso -- src/` → `b23a9cb 2026-09-30 15:40:39 +0200`. The rebuild is the
concurrent remediation's, and its effect is visible in the image ID changing from the `3a77fb234217` the input
recorded. The input's Appendix B already anticipated this class of interference and correctly identified the
timestamp as an artefact of concurrency rather than the finding.

**Consequence** — A reader re-running the evidence today finds the image *newer* than `HEAD` and may conclude the
staleness window is closed. It is not: the window is structural, not temporal.

**Recommendation** — Lead with the configuration facts — the resolved `test-app` service has no `volumes` key,
`$TestCompose` (`Makefile.ps1:36`) excludes the dev override, `Dockerfile:135` bakes `src/`, and none of `:196`,
`:201`, `:210` passes `--build` — and keep the timestamp as an illustration rather than as evidence.

### VAL-09-010 — TST-017's Zone paraphrases block 5's title instead of quoting it verbatim

**Severity** — LOW

**Verdict** — new; template-contract defect

**Observation** — The shared template requires the Zone be "the audit block title this finding came from, quoted
verbatim". Seventeen of eighteen findings comply. TST-017's Zone is `"The harness as a system: schema build,
isolation model, marker wiring"`, which truncates block 5's declared title.

**Evidence** — Block 5's title in `.kilo/commands/audit/phases/09-audit-test-coverage.md:76` is "The harness as a
system: schema build, isolation model, marker wiring, **and the separately executed suites**". The truncated half is
the part covering the frontend suite's separate execution model, which is the block's third subject.

**Consequence** — None for this finding's substance; a zone-index across the set loses the clause that would let a
reader find the half of block 5 about the separately executed suites.

**Recommendation** — Quote the full title.

### VAL-09-011 — TST-011's remedy, applied to all three tests, breaks the third

**Severity** — LOW

**Verdict** — new; a recommendation that is correct for two of its three subjects

**Observation** — TST-011's Recommendation is to "rewrite the three assertions against the RFC 7807 body: assert
`data["code"]` is a member of `ErrorCode`, that `type`, `title`, `status` and `detail` are present, and that `status`
is 422". Two of the three tests are red on a `detail`-shape assumption and the third is not.

**Evidence** — `tests/test_layouts.py:407-409`: `test_create_layout_duplicate_name_returns_400` asserts
`status_code == 400` and `"already exists" in data["detail"].lower()` — `detail` must be a **string**, the opposite
of the array assumption the finding attributes to it. Its runtime failure is `assert 422 == 400`, because
`src/mkobi/api/routes/layouts.py:104-109` raises `AppException(code=ErrorCode.VALIDATION_ERROR, …)` and
`exceptions.py:56` maps that to 422.

**Consequence** — Applied as written, the remedy converts a correctly-reported failure into a test that asserts 400
against a 422 response and hides a genuine contract question — whether a duplicate layout is a conflict (409) or a
validation failure (422).

**Recommendation** — Scope the rewrite to the two 422 tests, and route the third to a product decision. See the
TST-011 verdict above.

### VAL-09-012 — the namespace ruling this report was told to apply is forced by a collision that already exists

**Severity** — LOW

**Verdict** — new; recorded, not repaired — the collision is in two reports this validation may not edit

**Observation** — The output contract for this phase specifies the flat `VAL-` prefix for validation-level findings.
That namespace is already occupied twice: `.ai/audit/99-validation/01-process-architecture-validated-findings.md`
mints `VAL-001` … `VAL-008`, and `02-configuration-secrets-validated-findings.md` mints `VAL-001` … `VAL-009`. Phase
06's report records the same collision as VAL-06-010 and both of those reports carry it forward.

**Evidence** — A scan of `.ai/audit/99-validation/*.md` for `^### VAL-` returns eight identifiers from phase 01 and
nine from phase 02, with `VAL-001`, `VAL-002`, `VAL-003`, `VAL-004`, `VAL-005`, `VAL-006`, `VAL-007` and `VAL-008`
each naming **two different findings**. Phases 03 through 07 use the compound form (`VAL-03-` … `VAL-07-`).

**Consequence** — The collision is recorded rather than fixed, since repairing it means editing two reports already
written out, which this phase may not do. The compound form this report mints avoids extending it.

**Recommendation** — Renumber one of the two existing reports to a compound form, or accept the overlap and let the
phase number in the path disambiguate. Until then `VAL-001` … `VAL-008` are not unique identifiers in this set.

## Residual

*Fixed residual footer, carried by every validated report in this set.*

- **Blocks examined:** 9 of 9 declared blocks of the audited phase, each reached by at least one finding. Zone-verbatim
  compliance is 17 of 18 (VAL-09-010).
- **Findings adjudicated:** 18 of 18. Disposition tally — 7 confirmed with no qualification (TST-003, TST-004, TST-006,
  TST-007, TST-008, TST-012, TST-018), 9 confirmed with a recorded correction (TST-001, TST-005, TST-009, TST-010,
  TST-011, TST-013, TST-014, TST-016, TST-017), 1 merged (TST-002, with QLT-003), 1 re-typed (TST-015); 0 re-graded,
  0 not substantiated, 0 unsettled. Every finding's verdict matches its row above. No identifier was renumbered.
- **Validation-level findings:** 12 (VAL-09-001 … VAL-09-012), of which 5 MEDIUM and 7 LOW. The `VAL-09-` prefix is
  used because the flat `VAL-` namespace is already occupied twice, by the phase-01 and phase-02 reports
  (VAL-09-012).
- **Claims left unsettled, with reason.** (a) Run 2 of the backend suite reported **2 errors** alongside its 11
  failures and no equivalent appeared in runs 1 or 3; this validation's log filter for that run selected
  `^FAILED|passed|failed|error` and therefore did not capture the `ERROR` node ids, so the two are unidentified.
  Runs 1 and 3 produced none. (b) The mechanism behind
  `tests/test_users_api.py::TestDeleteAccount::test_admin_cannot_delete_self` asserting `len(remaining) == 0` after
  deleting every visible user was not established from the executing path. The symptom was measured three times with
  three different counts (`7`, `1`, `3`), and the rows it reports as remaining include ones the test creates later in
  its own body (`sole_admin_*`, `viewer_*`), which the code at `:94-102` runs before. Establishing the mechanism would
  need session-level SQLAlchemy instrumentation, which this validation did not add; the observation is recorded as a
  lower bound and no verdict rests on it. (c) `.\Makefile.ps1 test-all` was not run, so the measured backend coverage
  percentage is unquoted — as it is in the input, for the same reason. (d) No `pytest-xdist` parallel run was made, so
  TST-012's partition corollary rests on the code and on the shipped compensating `DELETE`s rather than on an observed
  parallel failure. (e) The lifespan, TLS and real-socket boundaries TST-008 describes were not exercised; no tier
  other than `mkobi-test` was started, and the `mkobi` dev stack was left as a peer agent left it. All five are limits
  on this validation's evidence, not on the input's verdicts.

---

*Fixed footer required by the validation output contract. No sibling report in this set carries one; it is appended
here because this report's output contract requires it.*

- **What this report is** — the validation of `.ai/audit/09-test-coverage/findings.md`, re-derived from the executing
  path at `b23a9cb`, with a disposition and a recorded verdict on each of its eighteen findings, a coverage ledger
  over the phase's nine declared blocks, a seam check against every report filed in this audit set, and defects in
  the audit itself on the `VAL-09-` namespace.
- **Real defects it confirms** — all eighteen of the phase's findings, without exception. Two CRITICAL (a gate that
  tests a baked image; no gate wired to anything and the aggregate omitting the backend suite), seven HIGH, seven
  MEDIUM, two LOW. Seven are confirmed with no qualification at all.
- **What it refutes** — three of the input's asserted causes, each while its finding survives: TST-014's "because the
  run was red" (a green single-file run deletes tracked files too); TST-011's attribution of
  `test_create_layout_duplicate_name_returns_400` to a `detail`-shape assumption (it fails on `422 != 400`); and
  TST-005's "they only assert that a 429 occurs" (the first sibling asserts 401 five times). It also supersedes
  TST-001's timestamp evidence, which a rebuild has overtaken.
- **What it adds** — direct runtime proof of TST-012 that the input reasoned from the fixture's own docstring: after a
  pytest process exited, `bidb_test` held 2 `users`, 10 `dashboards`, 8 `processing_logs` and 5 `graphs` rows that
  the tests had committed. It establishes that TST-014's gate dirties `frontend/coverage/` on **every** run, having
  run it twice. It measures four backend suite runs showing the failure count moving between 10 and 12 on identical
  code, one of which reproduced the input's figure exactly. Twelve defects in the audit itself, five of them MEDIUM,
  including two cross-references that name the wrong owning finding (TST-016 → TXN-003 where TXN-008 owns it; TST-010
  → AUTH-002, which owns a different store).
- **What it cannot settle** — the mechanism behind `test_admin_cannot_delete_self`'s intermittent `len(remaining) == 0`
  failure; the identity of the two errors run 2 reported; the measured backend coverage percentage (`test-all` not
  run); TST-012's xdist corollary (no parallel run); and the lifespan, TLS and real-socket boundaries TST-008
  describes (no tier other than the test stack was started). Each is stated with its reason above and none of them
  carries a verdict.
- **Named sibling reports compared** — phases **01** (TOPO-001, TOPO-004, TOPO-007), **02** (CFG-006),
  **03** (TXN-001, TXN-003, TXN-008), **04** (AUTH-001, AUTH-002), **08** (QLT-003, QLT-006, QLT-007, and QLT-001
  and QLT-002, found not to overlap), and phases 12 and 13, whose ownership TST-015 crosses. Phases **05**, **06**
  and **07** were compared by identifier and by zone and produced no overlap. No identifier belonging to another phase
  was renumbered, contested or edited.