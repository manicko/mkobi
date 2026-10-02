---
phase: 09-test-coverage
role: phase-1-code-context-auditor
head: cea2d06
report_baseline: b23a9cb
finding_prefix: TST-
findings: 18
defect_prefix: VAL-09-
defects: 12
status: complete
writable_artefact: this file only
---

# Phase 09 — Test Coverage — Code Context

## 1. Scope and method

### 1.1 What was read vs. what was executed

| Class | Items |
|---|---|
| **Read in full** | `.ai/audit/99-validation/09-test-coverage-validated-findings.md` (1324 lines) |
| **Read (anchors)** | `.kilo/rules/project.md`, `.ai/context/commands.md`, `AGENTS.md` via injected instructions; sibling plan frontmatter + hand-over tables for `01`–`07`; `.ai/plans/_code-context/08-code-quality-code-context.md` (D1, D8, VAL-08-007) |
| **Verified by reading** | every anchor in all 18 findings; `tests/conftest.py` (616 lines, complete); `Makefile.ps1` targets; `pyproject.toml`; `docker/docker-compose.test.yml`; `docker/Dockerfile` (test stage); `frontend/vite.config.ts`; `.gitignore`, `frontend/.gitignore` |
| **Verified by execution** | `docker compose -p mkobi-test -f docker/docker-compose.test.yml config` (resolved `test-app` has **no** `volumes:` key); `pytest --co tests/test_rate_limiting.py` → **7 collected**; `pytest tests/test_rate_limiting.py` → **1 failed, 6 passed, 16.41s**; single-test probe of `test_register_request_rate_limit_exceeded` with `-s`; 10-path CI-absence inventory; `docker images` |
| **Deliberately not executed** | full backend suite (≈5 min ×3 runs; the baseline is documented four times over and my one module already updates it), `test-all`, `npm run test` / `npx vitest --coverage` — the last would rewrite tracked files in `frontend/coverage/`, which this role may not restore (that is a tracked-source mutation) |

### 1.2 HEAD-vs-worktree split

`git log --oneline -10` → HEAD **`cea2d06`** `test(users): clean up rows the durable user writes now persist`, on top of `2174895`, `b646ef1`, `9a77625`, `a92b546`, `c4c0b14`, `5b23240`, `2de4156`, `7e37aa2`, `8178610`. The report was written at **`b23a9cb`**; **30 commits** have landed since, across phases 01, 02, 03, 04 and 08.

`git status --short`: **no tracked file is modified.** 30 deleted `.ai` artefact paths and 9 untracked `.ai/audit` / `.ai/plans` / `.ai/tasks` paths — documentation scaffolding only. **Every anchor below is a working-tree fact, and the working tree equals HEAD.**

Material consequence: `git diff --stat b23a9cb..HEAD` over `tests/ frontend/src/ src/ docker/ Makefile.ps1 pyproject.toml .gitignore` lists **39 files, +4192/−599**. Of those, **`tests/conftest.py` is absent** — the single most load-bearing file for this phase has not moved, so TST-005, TST-008, TST-009 and TST-012 anchor exactly as filed. Nine test files the phase cites *have* moved.

### 1.3 Real test baseline (obtained this session)

| Fact | Value | Source |
|---|---|---|
| Canonical runner | `.\Makefile.ps1 test` → `docker compose -p mkobi-test -f docker/docker-compose.test.yml run --rm --no-deps test-app pytest` (bare) | `Makefile.ps1:194-197` |
| Local `uv run pytest` | **not viable** — no test database on `localhost`; all backend tests run in the `mkobi-test` Compose project against `test-db` on host port **5434** | `.ai/context/commands.md`; `tests/conftest.py:16-30` |
| Stack state | `test-db` **running** `0.0.0.0:5434->5432`, `test-redis` **running** `0.0.0.0:6381->6379` (both already up; left running) | `docker compose … ps` |
| Image | `mkobi-test-test-app:latest` = `5b1d9b41d128`, created **2026-10-01 20:16:44 +0200** | `docker images` |
| HEAD commit touching `src/`+`tests/` | **`cea2d06` 2026-10-01 20:27:35 +0200** | `git log -1 -- src/ tests/` |
| ⇒ staleness window | **OPEN, and larger than the report's**: the image is **11 minutes older** than the code it tests. TST-001's timestamp argument reproduces again today (see VAL-09-009) |
| Collection count | `tests/test_rate_limiting.py` → **7 tests** (4 in `TestRateLimitingIntegration`, 3 in `TestAsyncRateLimiterUnit`). Full-suite count **not re-measured** — the report's `1013` is a stale figure at a tree 30 commits old |
| Module run this session | `pytest tests/test_rate_limiting.py` → **`1 failed, 6 passed, 2 warnings in 16.41s`** |
| The one red test | `test_rate_limit_reset_allow_writes` — `AssertionError: Request should succeed after reset, got 429 / assert 429 == 401` at `tests/test_rate_limiting.py:150`, **byte-identical** to the string TST-005 and TST-002 quote |
| Warning that matters | `PytestCacheWarning: could not create cache path /app/.pytest_cache/… [Errno 13] Permission denied` — the container runs as `USER app` (`docker/Dockerfile:150`) and **`/app` is not writable by it**. First concrete instance of the bind-mount risk TST-001 names obliquely |
| Frontend | 13 test files under `frontend/src/**/__tests__/`; `npm run test` = `vitest run --coverage` (`frontend/package.json:10`), forwarded by `Makefile.ps1:237-239` and last-linked by `Invoke-Check` (`:248`) |

### 1.4 What the autouse fixtures genuinely silence — and what they leave live

`tests/conftest.py` (616 lines, read in full) is the phase's whole subject. Read against §3.2 and the per-finding seams:

| Patch point | Silences | Leaves live |
|---|---|---|
| `_auto_mock_redis` (`:295-334`, autouse) — `redis_client_module.get_async_redis_client`/`get_redis_client` (`:318-319`) | Anything reaching Redis **through the module attribute** | Every by-value consumer: `deps.py:40`, `auth_service.py:19` |
| same, also patches `AuthService.__init__` (`:326-332`) to install `check_rate_limit = always_true` returning **`(True, None)`** | Rate limiting **inside `AuthService`** | Every route-owned limiter — `auth.py:84`, `:310`, `:562`. **Proven live this session**: `auth.py:92 "Login rate limit exceeded … ip 127.0.0.1"` |
| `strict_redis` (`:370-397`) — `MockRedis()` `:380`, patch `:388` | Nothing the product reads | The test's own handle on instance **B**; dead in all four integration tests |
| `async_client` (`:522-566`) — `get_db_dependency`→`async_db_session` (`:540-543`), `get_redis_client_dependency`→instance **C** (`:546-549`), `get_temp_password_store`→C (`:552-554`), `ASGITransport` (`:559`), `.clear()` (`:566`) | Commit, rollback, teardown, lifespan, real sockets — **all four**. `:566` also wipes *every* override, not just this fixture's |
| `mock_db` (`:510-519`) — `AsyncMock(spec=AsyncSession)` | SQL emission, constraint evaluation, row writes | Everything a session would catch |
| `async_db_session` (`:468-497`) — `begin_nested()` `:491`, `rollback()` `:496`, `expire_on_commit=False` `:463` | Nothing, once a test calls `commit()` — and `test_user` (`:590`) always does | `Session.commit()` commits the **root**, releasing the savepoint; rows persist for the rest of the session |

---

## 2. Per-finding context

Verdict vocabulary: `substantiated` (claim holds against the tree) · `drifted` (mechanism holds, cited anchors moved or a figure is stale) · `refuted` (the claim does not hold) · `already-fixed` · `stale`.

### TST-001 — the backend gate tests a baked image, not the working tree

**Verdict: substantiated — and its refuted timestamp evidence reproduces again today.**

| Claim | Anchor at `cea2d06` | Note |
|---|---|---|
| `test-app` declares no `volumes` | `docker/docker-compose.test.yml:123-167` (`build` `:124`, `depends_on` `:151`, `healthcheck` `:156`, `command` `:167`); resolved `config` shows no `volumes:` between `test-app:` and `test-db:` | **Re-executed. Confirmed.** The only `volumes:` keys are `:39` and `:65` |
| `$TestCompose` loads only the test file | `Makefile.ps1:36` | unchanged |
| `test` stage bakes the product | `docker/Dockerfile:132` `FROM base AS test`, `:135` `COPY src/ ./src/`, `:139` `COPY tests/ ./tests/`, `:155` `CMD ["pytest","tests/","-v"]` | unchanged; `WORKDIR /app` inherited from `:55` |
| No target passes `--build` | `Makefile.ps1:196`, `:201`, `:210` | unchanged — grep returns no `--build` anywhere |
| Timestamp evidence superseded (VAL-09-009) | image `5b1d9b41d128` @ `20:16:44` vs `cea2d06` @ `20:27:35` | **Refuted-back.** The image is 11 min **older**; the staleness window is open. `docker/Dockerfile:145` also bakes `docker/docker-compose.yml` + `.override.yml` into the image, so `tests/test_config.py`'s compose assertions read baked copies |

**Seams an implementor touches.** `docker/docker-compose.test.yml:123` (`test-app` service) and `docker/Dockerfile:132-155`. **No test file changes.** Two untested production symbols stand behind the mount: nothing in `src/` — the change is pure harness. **Assertion style: none; this is a configuration change verified by `.\Makefile.ps1 test` behaving differently, not by a new test.** Hard blocker discovered this session: `USER app` + `/app` not writable (observed `Errno 13`).

### TST-002 — no gate is invoked; the aggregate omits the backend tree; both suites are red

**Verdict: substantiated; the failure count is a stale sample and one module's count is now measured.**

| Sub-claim | Anchor | Verdict |
|---|---|---|
| Declared and never loaded | 10-path inventory re-run: `.github`, `.gitlab-ci.yml`, `.circleci`, `azure-pipelines.yml`, `Jenkinsfile`, `.husky`, `.pre-commit-config.yaml`, `tox.ini`, `noxfile.py`, `.git/hooks/pre-commit` — all `False` | substantiated |
| Aggregate omits the tree | `Makefile.ps1:241-249` `Invoke-Check` = `Invoke-Lint` → short-circuit → `Invoke-Typecheck` → short-circuit → `Invoke-FeLint` → short-circuit → `Invoke-FeTest`; no `Invoke-Test` | substantiated; help text `:81` and `:69` unchanged |
| Both suites red | `pytest tests/test_rate_limiting.py` → 1 failed / 6 passed | substantiated; full-suite figure **not re-measured** |
| The named ten failures | `test_auth.py:278/291/295/332/369/384/388/392`, `test_layouts.py:367/384/407`, `test_pydantic_models.py:100`, `test_rate_limiting.py:150` | all eight rate-limiter assertion sites **exact**; `test_rate_limiting.py:150` reproduced verbatim |
| QLT-003 merge, phase 09 owns the wiring | `08-code-quality-code-context.md:295` (VAL-08-007) and `:426` (D1) agree | substantiated |

**Seams.** `Makefile.ps1:241-249` and a new CI file. **Existing test module for the area: none — this finding adds no test; it adds the invoker.** QLT-003's gate-redness half is **already-fixed** by `8953bf7` (ancestor of HEAD), so any block premised on "the gates are red" is unfounded.

### TST-003 — the backend coverage threshold has no measurement to act on

**Verdict: substantiated, byte-exact, zero drift.**

`pyproject.toml:196` `addopts = "--import-mode=importlib -ra -v --strict-markers --cov-fail-under=65"` — no `--cov`. `[tool.coverage.run] source = ["src/mkobi"]` at `:208`; `[tool.coverage.report] fail_under = 65` at `:212` (the duplicate). `Invoke-Test` (`:194-197`) runs bare `pytest`; `Invoke-TestAll` (`:199-202`) passes `--cov=src/mkobi --cov-report=term-missing`. **Seams:** `pyproject.toml:196` and `:212` only. **No test symbol under test; no fixture.** Assertion style: the gate's exit code.

### TST-004 — frontend thresholds measure an import-driven population, suppressed while red

**Verdict: substantiated, byte-exact, zero drift.**

`frontend/vite.config.ts:56-63` — `provider: 'v8'`, `reporter: ['text','json','html']`, `thresholds: {statements:50, branches:40, functions:45, lines:50}`; no `include`, no `exclude`, no `all`. `frontend/package.json:10`. **Seams:** `vite.config.ts:56-65`. **Not re-executed** — `vitest --coverage` rewrites 15 tracked files (§5, R3). Frontend test module for the area: `frontend/src/shared/types/__tests__/enums.test.ts` is the 21-test file the report measured against.

### TST-005 — rate-limit integration tests exhaust a counter on a store they cannot reach

**Verdict: substantiated on the dead-`strict_redis` mechanism; one sentence in the report needs narrowing, and a fourth Redis resolution path exists that the report does not name.**

| Claim | Anchor | Verdict |
|---|---|---|
| Three `MockRedis` instances | A `:308`, B `:380`, C `:546` — all exact | substantiated |
| `deps.py:40` binds by value | `src/mkobi/api/deps.py:40` `from mkobi.core.redis_client import get_async_redis_client`; `:125-131` `get_redis_client_dependency` calls it | exact; **not in the report** — this is *why* the module patch misses |
| `auth.py` builds its own limiter | `:83-89` (`client_ip`, `AsyncRateLimiter(redis_client, …)`, key `f"login:{client_ip}"`), `:146` `redis_client: Any = Depends(get_redis_client_dependency)` | exact |
| `AuthService` builds a second | `services/auth_service.py:19` by-value import, `:50 __init__`, `:66-67 AsyncRateLimiter(get_async_redis_client(), …)` | exact |
| "the login path can reach none of them" | — | **drifted.** Runtime log this session: `Login rate limit exceeded … auth.py:92 … "ip": "127.0.0.1"`. The route limiter **is live** and reaches **instance C** through the dependency override. What is dead is the test's handle on **B** |
| "Two passing siblings only assert a 429" (VAL-09-007) | `test_rate_limiting.py:44-46` asserts 401 ×5, `:57-59` asserts 429 | VAL-09-007 substantiated |
| **New, unreported** | `auth.py:562-563` builds a **third** limiter from `redis_client.get_async_redis_client()` — a method `MockRedis` (`:176-223`) does not define; `:310-314` a fourth (`refresh:`); `:566` a fifth key form | **three route-owned limiters + one service-owned = four**, not two. See §6 DP-1 for the unresolved resolution mechanism |

**Seams.** `tests/conftest.py:295-334` / `:370-397` / `:546` and `src/mkobi/api/routes/auth.py:562-563`. **Existing test module: `tests/test_rate_limiting.py`** (7 tests; 4 integration carry a dead `strict_redis` parameter, 3 unit tests unpack the tuple correctly at `:206`, `:221`, `:225`, `:241`). **Assertion style: status-code constants (`status.HTTP_429_TOO_MANY_REQUESTS`) and header presence; the unit tests use tuple unpacking — that style is already correct and is the model.**

### TST-006 — the hard-coded rate-limit key is a client identity no production request can present

**Verdict: substantiated, exact, and now contested in ownership.**

`tests/test_rate_limiting.py:124` `rate_limit_key = "login:127.0.0.1"`, popped at `:138-139`. Production key at `src/mkobi/api/routes/auth.py:83` `client_ip = request.client.host if request.client else "unknown"` and `:89`. Confirmed at runtime: the log line carries `"ip": "127.0.0.1"`. `test_different_ips_have_separate_limits` (`:154-193`) still contains one address, one key, one 429 assertion at `:193` — **still vacuous.**

**Seams and contested ownership:** phase 04's plan names this test as its hard blocker `VAL-04-002` / `AB-6` and states the fix must land *with* the key change; phase 07's plan hands `test_different_ips_have_separate_limits` to phase 09 by name (`07-…-execution.md:146`, `:644` HO-8, `:737`). Phase 09 must not rewrite either test ahead of phase 04's landing.

### TST-007 — every shipped worker test injects the session that makes TOPO-001 unreachable

**Verdict: substantiated; anchors drifted by ≈14 lines and the function under test moved ≈300.**

| Symbol | Report | Tree at `cea2d06` |
|---|---|---|
| `process_csv_background` | `:552` branch | **`:855`** (def) · branch at `:566` |
| `_update_processing_log_status` | `:554-581` | `:181` (def) |
| `cleanup_stale_processing_logs` | `:254` / `:269` | **`:241`** (def) · `:260` / else branch |
| `mark_orphaned_uploaded_logs_failed` | `:314` / `:330` | **`:310`** (def) · `:328` / else |
| `process_csv_background_sync` | — | `:899` (unreported; a fourth entry point) |

Mechanism unchanged. **Executed census:** `Select-String tests/*.py "session=None|db_session=None"` returns **three** hits — `test_data_worker.py:110` (a *test-local* `sweep(…, session=None)` stub inside `TestReconcilerLoop`), and `test_file_cleanup.py:382`/`:435`, which pass `session=None` to `_process_csv_file_async` (`:371`) — **not** one of the three branching functions. So the `else` branch remains undriven; and the one place the suite *signatures* `session=None` is a fake.

**Seams.** `src/mkobi/workers/data_worker.py:241`, `:310`, `:855`. **Existing test module: `tests/test_data_worker.py`** — which has **grown by 370 lines** since baseline and now carries `TestReconcilerLoop` (`:90`), `TestReconcilerLeaseOwnership` (`:336`), `TestReconcilerLoopTask` (`:386`) and `TestDataWorker` (`:391`, `AsyncMock` sessions at `:395-400`, three `commit.assert_not_called()` at `:443`/`:485`/`:508`). Those three assertions are named **must-stay-green** by phases 05 (`:1886`) and 03 (`:1434`). The other coverage lives in `tests/test_processing_logs.py::TestStaleProcessingCleanup` and the six `delete(ProcessingLog)` sites below. **Assertion style: `AsyncMock.execute.assert_called_once()` + `call_args` inspection of the `update()` statement's `.values()`.**

### TST-008 — the HTTP fixture substitutes the test's own session for the product's

**Verdict: substantiated, byte-exact; `tests/conftest.py` has not moved.**

`tests/conftest.py:540-541` `override_get_db`, `:543` registered, `:559` `ASGITransport(app=app)`, `:566` `app.dependency_overrides.clear()`. Production side: `src/mkobi/api/deps.py:101 async def get_db_dependency()`. The report's credit to the suite is verifiable: `tests/test_deps.py::TestGetDbDependency` calls the real generator outside a request. **Seams:** `tests/conftest.py:522-566` (a *second* client fixture is the natural home; `authenticated_client` at `:569-573` derives from it). **Assertion style: none of the four TXN-001 endpoints is currently asserted through a real session; the suite's style for this area is `response.status_code` plus repository re-reads through the same session.**

### TST-009 — three whole service modules are asserted only against a mock session

**Verdict: substantiated; the counts drifted and one supporting claim is refuted.**

| Claim | Report | Tree |
|---|---|---|
| `mock_db` is `AsyncMock(spec=AsyncSession)` | `conftest.py:510-519` | `:510-519` exact |
| 61 of 76 tests across 3 files (28/16/17) | — | **drifted**: `test_auth_service.py` now holds **50** test functions (+8 from phase 04's landed work) and **63** `mock_db` lines; `test_graph_service.py` 17 fns / 33 lines; `test_layout_service.py` 17 fns / 34 lines |
| "referenced in exactly four files" | — | **refuted**: a fifth consumer exists — `tests/test_user_service.py:50,59,63,66,…,146`, 15 sites, asserting `mock_db.commit.await_count` / `not_awaited` |
| `test_graph_service.py:67` uses `is` | — | still `==` (VAL-09-008 item 6 stands) |
| `test_auth_service.py:478` `commit.assert_called_once()` | — | file rewritten; anchor moved |

**Seams.** `tests/conftest.py:510-519`; **existing test modules** `tests/test_auth_service.py`, `tests/test_graph_service.py`, `tests/test_layout_service.py`, `tests/test_user_service.py`. **Fixture that must change: `async_db_session`, not `mock_db`.** **Assertion style: repository call-argument inspection for the mock half; for the real-session half the suite's established idiom is create-then-re-read-through-the-same-session (`repo.create(db=async_db_session, …)` then `repo.get_all(async_db_session)`), never `assert result.x is None`.**

### TST-010 — five shipped rate-limiter tests assert a scalar against a tuple API

**Verdict: substantiated, byte-exact; VAL-09-008 item 4 stands.**

`src/mkobi/core/security.py:111-113` `async def check_rate_limit(...) -> tuple[bool, int | None]`; returns `(True, None)` at `:88`/`:103`/`:136`, `(False, ttl…)` at `:82`/`:97`/`:130`. All **eight** assertion sites in `tests/test_auth.py::TestRateLimiting` (class at `:264`) resolve: `:278`, `:291`, `:295`, `:332`, `:369`, `:384`, `:388`, `:392` — five tests, and the report's omission of `:331-332` plus its duplicated range are confirmed. Contrast: `tests/test_rate_limiting.py:206`/`:221`/`:225`/`:241` unpack correctly. **Seams:** `tests/test_auth.py:264-393` only. **Assertion style: `assert result is True, f"Attempt {i+1} should be allowed"` — destructure, keep the message.** Note `tests/conftest.py:330` already returns `(True, None)`, so the fixture is written against the tuple API and the five tests are the outliers.

### TST-011 — three shipped layout tests assert the legacy 422 format

**Verdict: substantiated for two; the third is mis-diagnosed — and `test_layouts.py` has not moved.**

| Test | Anchor | Failure mode |
|---|---|---|
| `test_create_layout_missing_name_returns_422` | `tests/test_layouts.py:354-370`; `errors = data["detail"]` `:366`, `assert isinstance(errors, list)` `:367` | `detail` is the string `"Request validation failed"` → shape mismatch |
| `test_create_layout_missing_definition_returns_422` | `:372-387`; `:383-384` | same |
| `test_create_layout_duplicate_name_returns_400` | `:389-409`; `assert status_code == status.HTTP_400_BAD_REQUEST` `:407`, `"already exists" in data["detail"].lower()` `:409` | **`assert 422 == 400`** — status mismatch, and `detail` must be a **string** here |

Production side exact: `src/mkobi/utils/exceptions.py:263-297` handler; `:280` `detail="Request validation failed"`; `:281` `code=ErrorCode.VALIDATION_ERROR`; **`:295` top-level `"errors"`**; `:56` `VALIDATION_ERROR → HTTP_422_UNPROCESSABLE_CONTENT`; `:69` `DUPLICATE_RESOURCE → HTTP_409_CONFLICT`. `src/mkobi/api/routes/layouts.py:104-109` catches `ValueError` → `AppException(code=ErrorCode.VALIDATION_ERROR)`. **Seams:** `tests/test_layouts.py:366-367`, `:383-384`; `:407-409` **must not** be swept along (VAL-09-011). **Assertion style: `response.json()` + key presence + `status.HTTP_*` constants; the RFC-7807 assertions this phase needs must read `data["errors"]`, not `data["detail"]`.** Related: phase 01's plan (`:1788-1793`) already names `tests/test_layouts.py` and `test_pydantic_models.py::test_user_db_valid` among 12 pre-existing failures it must not regress.

### TST-012 — `async_db_session.commit()` commits for real, so test data outlives the test

**Verdict: substantiated; the compensating-measure surface is 3× larger, and the report's residual (b) mechanism is refuted by the tree.**

`tests/conftest.py:468-497` docstring `:472-476`; `begin_nested()` `:491`; `rollback()` `:496`; `expire_on_commit=False` `:463`. Live proof that the suite commits: **`tests/conftest.py:590`** — the `test_user` fixture calls `await async_db_session.commit()` after creating a user, so every test that touches `test_user`, `auth_headers` or `authenticated_client` writes a durable row.

| Claim | Tree |
|---|---|
| Two shipped compensating `DELETE`s (`test_processing_logs.py:330-338`, `:394-403`) | **six** sites: `:122-126`, `:155-159`, `:240-244`, `:330-333`, `:394-398` — each commented `… for test isolation` |
| `test_users_api.py:101` asserts `len(remaining) == 0` | now `:165` in `class TestDeleteAccount` (`:108`), method at `:146` |
| Residual (b): the remaining rows are ones the test creates "later in its own body … code at `:94-102` runs before" | **refuted.** `sole_admin_*` is created at `:168-173` and `viewer_*` at `:177-182` — both **after** the assertion at `:165`. They cannot explain `assert 7 == 0`. The only remaining explanation is the commit-persists leak itself |
| `conftest.py:431`/`:433` recreate per session | `:431 recreate_test_db=True`, `:433 recreate_test_database()`; `src/mkobi/db/starter.py:207` (def), guards `:230-236` (env) and `:250-256` (name), `DROP`/`CREATE DATABASE` `:308`/`:311` |
| xdist corollary `conftest.py:143-152` | `:143 _get_worker_db_suffix`, `:155 _build_worker_isolated_test_db_url`, `:417-418` per-worker DB name — unchanged |
| `commit users): clean up rows the durable user writes now persist` (`cea2d06`) | touched `admin.py` (+7/−… ), `user_service.py` (+3), `test_admin_user_management.py` (+67/−…), `test_user_service.py` (2), `test_users_api.py` (2 — **docstring only**) |

**Seams.** `tests/conftest.py:459-497`; **existing test modules that would be affected by a fixture change: every one of them** — the blast radius is the whole suite. **Fixture that must change: `async_session_maker` (`:459-465`) + `async_db_session` (`:468-497`), i.e. the external-transaction recipe binds the session to a `connection.begin()`.** **Assertion style: unchanged for implementors; the risk is that the six compensating `DELETE`s in `test_processing_logs.py` become redundant and their removal is a second-order edit.**

### TST-013 — one test's config mutation leaks into every test after it in the worker

**Verdict: substantiated on the mechanism; the primary anchor is stale and a larger leak site now exists.**

| Claim | Report | Tree |
|---|---|---|
| Primary anchor: 11 env vars + `clear_config_cache()` | `test_rq_worker.py:148-165`, vars `:150-160`, cache `:164` | **stale**: `:148` is now `test_worker_subscribes_to_the_shared_queue_name`, patching **3** vars at `:152-154`, `clear_config_cache()` at `:158` — rewritten by `9a77625` |
| **New, larger site** | — | `test_rq_worker.py:189-205 test_start_rq_worker_uses_config_url_when_none` monkeypatches **10** vars (`:191-201`) and calls `clear_config_cache()` at `:205`, **no teardown** |
| No autouse teardown exists | — | confirmed: `clear_config_cache()` appears only at `conftest.py:60`, `:80`, `:413` and `test_rq_worker.py:156/158/203/205` |
| `_settings` singleton | `config.py:975` | **drifted → `:1032`** |
| `get_config` | `config.py:978` | **drifted → `:1035`** |
| `clear_config_cache` | `config.py:997` | **drifted → `:1054`** |
| `tests/test_config.py:30-70` | cited as a call site (VAL-09-008 item 2) | **drifted again**: **77** `clear_config_cache` occurrences, first import `:495`, first call `:496` (was 67 / `:528`) |
| `tests/test_cors.py:19-24` | resolves | **confirmed**: `:19-24` present (file grew by 26 lines since baseline) |
| Replacement anchor named by VAL-09-008 | `conftest.py:410-413` session-scope `clear_config_cache()` | **confirmed exact** |

**Seams.** `tests/conftest.py` (add one autouse function-scoped fixture) — no production symbol changes. **Existing test module: `tests/test_config.py` (77 call sites) and `tests/test_rq_worker.py` are the exposure surface; the modules sorted after `test_rq_worker.py` are now ten.** **Assertion style: none; this is a teardown fixture, verified by ordering, not by a new assertion.**

### TST-014 — the declared frontend gate deletes fifteen tracked files

**Verdict: substantiated; cause refuted by the report and re-confirmed by reading.**

`git ls-files frontend/coverage` → **exactly 15**. `.gitignore:39-47` covers `htmlcov/`, `.coverage`, `.coverage.*`, `coverage.xml` — **not** `coverage/`. `frontend/.gitignore` contains only `node_modules` (`:10`), `dist` (`:11`), `dist-ssr` (`:12`) — no coverage mention. `frontend/package.json:10`. **Not re-executed** — running it would dirty tracked files this role may not restore. **Seams:** 15 tracked paths + `frontend/.gitignore`. **No test symbol; no fixture; no assertion.** The report's ordering constraint stands: one commit, `git rm --cached` + ignore, so no intermediate commit records a mass deletion.

### TST-015 — client and server enforce different password policies; the showing test is red

**Verdict: substantiated and re-typed; the client-side remedy is out of scope (VAL-09-003).**

Server: `src/mkobi/utils/validators.py:183-205` — `:196-197` length ≥ 8, `:199-200` a digit, `:202-203` a letter in either case; `return None` at `:205`. Client: `frontend/src/shared/types/formSchemas.ts:56-59` — length + `:58` **uppercase** regex + `:59` digit regex. Strict superset. Governing server path: `src/mkobi/models/auth.py:178 class ChangePasswordRequest`, `:205 validate_new_password_field`, `:207 validate_password_or_raise(v)`. Registration already uses it: `src/mkobi/services/auth_service.py:151`.

**Red test, exact:** `frontend/src/shared/types/__tests__/formSchemas.test.ts:156-163` — `:159 new_password: 'newpassword123'`, `:162 expect(result.success).toBe(true)`. 14 chars, digit, lowercase → satisfies server, fails client. **Seam:** the test file (phase 09) and `formSchemas.ts` (phase 13 or 04). **Assertion style: `safeParse()` + `expect(result.success).toBe(true|false)`** — Zod's parse-result idiom, not `toThrow`.

### TST-016 — no test observes whether a seeder run destroys uploaded data

**Verdict: substantiated, byte-exact.**

`src/mkobi/db/seeders/test_media_dash.py:129` `await db.execute(delete(Graph).where(Graph.dashboard_id == dashboard_id))` — the report's `:128-129`; `aggregated_data.py:77-81` FK `ondelete="CASCADE"`; `src/mkobi/db/starter.py:190-191` calls `run_dev_seeders()`. Test side: `tests/test_dev_seeders.py:70` `assert len(graphs) == 2  # Should still be 2, not 4`; **0** `AggregatedData` references in the file (re-measured). Call-site count still wrong in the report's favour: 30 matches, all in `test_dev_seeders.py`. That file also carries two in-suite gate tests — `:185 test_seed_script_ruff_mypy`, `:211 test_dev_seeders_module_ruff_mypy` — a pattern worth reusing. **Seam:** `tests/test_dev_seeders.py` (add an upload-then-re-seed assertion; tighten `:70` to identity). **Assertion style: `len(graphs) == 2` — the report's identity-based tightening is the correct style.** Cross-reference must be **TXN-008**, not TXN-003 (VAL-09-002).

### TST-017 — the `slow` and `fast` markers are registered, used by zero tests

**Verdict: substantiated, byte-exact.**

`pyproject.toml:200-202` registers `slow` and `fast`; `addopts` `:196` carries `--strict-markers`. `fast`'s description names `Base.metadata.create_all()`, which the repository does not use — `conftest.py:433` always calls `recreate_test_database()` and the only `create_all` in `src/` is `src/mkobi/db/session.py:110` inside `init_db()`. **Census re-run: zero `pytest.mark.slow` / `pytest.mark.fast` in `tests/`.** **Seam:** `pyproject.toml:200-202` and, if `-m "not slow"` is adopted, `:196`. **No test symbol; no fixture.** VAL-09-010 is a template-contract defect with no code consequence.

### TST-018 — the enum-consistency module claims a two-way check it performs one way

**Verdict: substantiated, byte-exact.**

`tests/test_enum_db_consistency.py:1-7` module docstring; `:66 test_user_role_values_match` (`missing_in_db` `:73`, assert `:75-77`) — one-way; `:107 test_dashboard_permission_values_match` (`:116`, `:118-120`) — one-way; `:169 test_processing_status_values_match` (`missing_in_db` `:179`/`:182-184`, `extra_in_db = db_values - python_values` `:187`/`:188-191`) — the only two-way check; `:230 test_all_enums_consistent`, `missing = python_values - db_values` `:248`, while its own docstring `:233-235` promises an extra-values failure. `:50-53` reads `pg_enum JOIN pg_type`. Production types: `db/models/user.py:52-54`, `access.py:44-46`, `processing_logs.py:44-46`. **Seam:** `tests/test_enum_db_consistency.py` only — extract the `:179-191` comparison into a helper. **Assertion style: `assert not missing_in_db, f"Values in UserRole but not in PostgreSQL: {missing_in_db}"` — set-difference with an f-string message.**

### Validation-level defects `VAL-09-001` … `VAL-09-012`

| ID | Verdict | Evidence at `cea2d06` |
|---|---|---|
| `VAL-09-001` | **substantiated, reinforced** | Both extra failures remain in the tree: `tests/test_users_api.py:146` and `tests/test_e2e_upload.py::TestE2EUploadWorkflow::test_e2e_multiple_graphs_same_dashboard` (`task_id` reads at `:144-145`, `:236-239`). Full-suite count not re-measured |
| `VAL-09-002` | substantiated | Seeder defect is TXN-008; `test_media_dash.py:129` + `starter.py:190-191` are TXN-008's subject, not the stale-log sweep's |
| `VAL-09-003` | substantiated | `frontend/src/shared/types/formSchemas.ts:56-59` is a production client file; phase 09's own scope paragraph assigns the client tier to phase 13 |
| `VAL-09-004` | substantiated; **still unowned** | `src/mkobi/core/security.py:107 fail_closed: bool = False`; the fail-open branch `:98-103`. Shipped tests pinning it: `test_auth.py:298-332`, `:335-369`. No `AUTH-*` header names the rate limiter |
| `VAL-09-005` | substantiated | Tally arithmetic unchanged; the unidentified defect is `tests/test_pydantic_models.py:100 def test_user_db_valid` in `class TestUserModels` (`:46`) |
| `VAL-09-006` | substantiated (not re-executed) | Mechanism is the reporter's clean-output step; independent support: `git ls-files frontend/coverage` = 15 and `frontend/.gitignore` has no coverage line |
| `VAL-09-007` | substantiated | `test_rate_limiting.py:44-46` 401 ×5 then `:57-59` 429; `:154-193` has no inner assertion — the genuinely vacuous one |
| `VAL-09-008` | **substantiated; two items drifted further** | Item 2: `tests/test_config.py` now **77** `clear_config_cache` occurrences, first import `:495`, first call `:496` (report: 67, `:528`). Item 7: `config.py` anchors now `:1032` / `:1035` / `:1054` (report: `:975` / `:978` / `:997`). Item 1 (`:10`) and item 6 (`==`) stand |
| `VAL-09-009` | **refuted-back / stale** | Image `5b1d9b41d128` @ `20:16:44` is **older** than `cea2d06` @ `20:27:35`. The staleness window is open again, so the timestamp argument reproduces. The configuration argument is unaffected |
| `VAL-09-010` | substantiated | Template defect; no code consequence |
| `VAL-09-011` | substantiated | `test_layouts.py:407-409`; `layouts.py:104-109`; `exceptions.py:56` |
| `VAL-09-012` | substantiated | `VAL-001`…`VAL-008` still collide across the phase-01 and phase-02 reports. Not repairable from this phase |

---

## 3. Cross-cutting architecture and constraints

### 3.1 The test architecture as it exists

| Dimension | Reality |
|---|---|
| Backend layout | One flat `tests/` directory, **no subpackages**, one module per concern (`test_<subject>.py`). Naming is `<production-symbol-or-feature>.py`; there is no `unit/` vs `integration/` split on disk |
| Integration-vs-unit split | **By fixture, not by directory.** A module mixes both: `tests/test_rate_limiting.py` has `TestRateLimitingIntegration` (4 tests, `async_client`) and `TestAsyncRateLimiterUnit` (3 tests, no client). `tests/test_auth.py` mixes HTTP tests and `TestRateLimiting` (pure-limiter tests at `:264-393`). `tests/test_data_worker.py` mixes `TestReconcilerLoop*` (patched module functions) with `TestDataWorker` (`AsyncMock` sessions) |
| Naming conventions | Test classes `Test<Thing>`; methods `test_<behaviour>` as a sentence (`test_admin_cannot_delete_self`, `test_rate_limit_reset_allow_writes`); docstring on nearly every test stating the intent |
| Assertion style (backend) | `status.HTTP_*` constants over bare ints; `response.json()` + key presence; tuple unpacking for multi-value returns; repository re-read through the *same* session to verify a write; `AsyncMock.assert_called_once()` + `call_args` inspection for repository-call contracts; set-difference with f-string messages for enum drift; `pytest.raises` for value objects. `print()` is absent; JSON-formatted log lines go to captured stdout |
| Assertion style (frontend) | Vitest `describe`/`it`; Zod tested via `safeParse()` + `expect(result.success).toBe(...)`; `render` + `screen` for components. 13 test files, all under `src/**/__tests__/` |
| Execution | **Docker-only.** `.\Makefile.ps1 test` → `docker compose -p mkobi-test -f docker/docker-compose.test.yml run --rm --no-deps test-app pytest`. `uv run pytest` cannot work: no test database on `localhost`. `test-select` forwards args verbatim (`Makefile.ps1:209-210`) and is the only targeted runner |
| Schema build | `tests/conftest.py:400-437` session-scoped `setup_test_database` → `DatabaseStarter.recreate_test_database()` (`:433`) → drop + create + Alembic upgrade. xdist per-worker DB naming at `:143-152`, `:417-418` |
| Coverage (backend) | `--cov-fail-under=65` in `addopts` with **no** `--cov` (`pyproject.toml:196`); `source = ["src/mkobi"]` (`:208`); duplicated `fail_under = 65` (`:212`). Live only on `test-all` (`Makefile.ps1:201`), inert on `test` (`:196`) |
| Coverage (frontend) | `vite.config.ts:56-63`, four thresholds, no `include`/`exclude`/`all`; suppressed entirely on a red run |
| CI | **None.** Ten-path inventory all `False` |
| In-suite gate tests | A pattern already in use: `tests/test_dev_seeders.py:185`, `:211` run ruff/mypy over the seeder module from inside pytest. `test_config.py` (77 cache calls) asserts on compose file *text* |

### 3.2 The limit of the autouse patches — the phase's central technical fact

§1.4 tabulates what each patch silences. Two consequences the report does not state, both load-bearing:

| Fact | Consequence |
|---|---|
| `src/mkobi/api/deps.py:125-131` — `get_redis_client_dependency` calls the **by-value-bound** name from `deps.py:40` | This is *why* `_auto_mock_redis`'s module patch misses every consumer. It is absent from the report's evidence chain, which starts from the import at `:40` and stops |
| `AuthService.__init__` under `strict_redis` | `strict_redis` restores the original `__init__` (`:394-395`), which builds its limiter from the **real** by-value-bound factory (`auth_service.py:67`) — an object no fixture patched. So "restoring real rate limiting" does not mean "pointing at instance B" |


### 3.3 Shared test seams and their owner phase

| Seam | Owner | Evidence in the sibling plan |
|---|---|---|
| `tests/test_rate_limiting.py::test_rate_limit_reset_allow_writes` | **04** (`VAL-04-002`/`AB-6`), phase 09 must follow | `04-…:380`, `:739` — "hard blocker; update **with** the key, and prove the six attempts still exhaust the limit" |
| `tests/test_rate_limiting.py::test_different_ips_have_separate_limits` | **09** (quality), handed over by 07 | `04-…:381`, `:741`; `07-…:146`, `:644` (HO-8), `:737` |
| `tests/test_rate_limiting.py::test_x_forwarded_for_spoofing_ignored` | **09** (re-read), premise moved by 07's EB-7 | `04-…:740`; `07-…:644` |
| `tests/test_health.py`'s exact-dict assertion | **09** (quality) | `07-…:644` (HO-8) |
| `tests/test_data_worker.py` — 3 × `commit.assert_not_called()` | **05** + **03** must stay green; 02 **edits** the file | `05-…:1323`, `:1886`; `03-…:1434`; `02-…:257`, `:1628`, `:1848-1860` |
| `tests/test_data_worker.py` — new lease/sweep classes | **02** (already landed: `TestReconcilerLoop`/`TestReconcilerLeaseOwnership`) | `02-…:1628`, `:1838-1860`; `git diff` shows +370 lines |
| `tests/test_auth_service.py` — 4 tests pinning `2de4156` ordering | **07** (EB-9) / **04** (AB-1) | `07-…:730-732`, `:455`; `04-…:247`, `:730-732` |
| `tests/conftest.py::async_client` — the `get_db_dependency` override | **09** (TST-008); **03** observes it as a constraint | `03-…:212`, `:375`, `:642` |
| `tests/conftest.py::setup_test_database` / `recreate_test_db` | **01** (CFG), guard already landed `8178610` | `01-…:126`; `starter.py:230-256` |
| `tests/conftest.py::async_session_maker` | **05** (a second session-scoped caller of `cleanup_stale_temp_files`) | `05-…:310`, `:1291` |
| `tests/test_layouts.py`, `test_pydantic_models.py::test_user_db_valid` | **09** — phase 01 names them pre-existing, must-not-regress | `01-…:1788-1793` |
| `frontend/src/shared/types/__tests__/formSchemas.test.ts` | **09** (test) / **13 or 04** (`formSchemas.ts`) | VAL-09-003 |
| `httpx` as a gate-declared test-tier dependency | **07** (reclassified, not dropped) | `07-…:90` |
| `Invoke-Check` shape | **09** owns adding `Invoke-Test`; **08**'s D1 leaves the short-circuit shape open | `08-…:137-140`, `:426` |

---

## 4. In-flight and already-landed work

`git status --short`: **nothing tracked is dirty.** All 30 commits since `b23a9cb` are landed. The intersections with this phase:

| Commit | Lands | Intersects |
|---|---|---|
| `cea2d06` `test(users): clean up rows the durable user writes now persist` | `admin.py` (+7), `user_service.py` (+3), `test_admin_user_management.py` (+67/−…), `test_user_service.py` (2), `test_users_api.py` (2, docstring only) | **TST-012** — the intermittent `test_admin_cannot_delete_self` target; **TST-009** — makes `test_user_service.py` a fifth `mock_db` consumer |
| `2174895` `fix(user): own the unit of work for user writes and classify the email race` | `user_service.py`, `admin.py` | TST-012 (durable writes) |
| `b646ef1` `fix(lifespan): make teardown fail-isolated` | `app.py` | TST-008 (lifespan already bypassed) |
| `9a77625` `fix(rq-worker): correct the liveness diagnosis; pin the shared queue name` | `rq_worker_wrapper.py` (+124), `test_rq_worker.py` (+185) | **TST-013** — rewrote the report's primary anchor to 3 env vars |
| `a92b546`, `4a5db54` `fix(lease)` | `core/reconciler_lease.py` (new, 264 lines), `test_data_worker.py` | TST-007's test-module home now carries phase-02 tests |
| `c4c0b14` `docs(process-architecture)` | docs only | — |
| `5b23240` `docs(audit)` | the 16 validated reports | provenance |
| `2de4156` `refactor(auth): own the approval transaction` | `auth_service.py` (+96), `test_auth_service.py` (+378) | **TST-009** — 42 → 50 tests |
| `9c49c20`, `d008f55`, `bde2ddd`, `5f1d9ee`, `c55550b` (docker/compose) | `docker-compose.yml` (+52), `.override.yml` (+35), `Dockerfile` (+4), `.env.production` | **TST-001** — the override at `:99-101` is the mount pattern the recommendation copies |
| `8178610` `fix(starter): guard destructive test-database recreation` | `starter.py` (+68) | TST-012 / TST-017 — `recreate_test_database` now guarded at `:230-236` and `:250-256` |
| `8953bf7` `fix(gates): restore green ruff and mypy baselines` | `processing_log_service.py`, `data_worker.py`, `config.py` | **QLT-003's gate-redness half: already-fixed.** Ancestor of HEAD; recorded in `08-…:36`, `:129-130`, `:392` |
| `c938008`, `f411c06`, `14be95c`, `8747be7`, `eeb9a5e`, `f107d59`, `183056d`, `ce537d7`, `a026c47`, `7e37aa2`, `3848e7a`, `0717b65`, `3856f27`, `4a5db54` (config/auth/task-queue/worker) | `config.py` (+165), `models/enums.py` (+28), `task_queue.py` (−191/+…) | **TST-013** — moved `config.py` anchors again to `:1032/:1035/:1054`; `enums.py` grew, which is what `test_enum_db_consistency.py` reads |

Dirty-but-untracked: 9 `.ai` plan/audit/task paths and 30 deleted `.ai` artefacts. No code, test, or configuration file is dirty.

---

## 5. Discrepancies and risks

| ID | Risk | Evidence | Severity for the Planner |
|---|---|---|---|
| R1 | **`VAL-09-009` is now stale, not settled.** The report records the timestamp argument as superseded by a rebuild; today the image is 11 min **older** than `cea2d06`, so the window is open again and the configuration argument is the only durable one | image `5b1d9b41d128` @ `20:16:44` vs `cea2d06` @ `20:27:35` | HIGH — any block premised on "the image is fresh" is unfounded; **TST-001 must be led with configuration** |
| R2 | **Contested analysis between phase 09 and phase 04.** TST-005 says the login path reaches none of the three stores; phase 04's Z-12 says the route limiter is *live* and the autouse patch does not silence it. Runtime supports phase 04 | `auth.py:92` log line, this session | HIGH — the fix surface is *which* store the test must observe, not *whether* the limiter runs |
| R3 | **Running the frontend gate mutates tracked files**, and this role may not restore them. My non-execution of `vitest --coverage` is deliberate, not an omission | 15 tracked paths; `git ls-files` count | MEDIUM — the Planner should treat the frontend baseline as inherited, not re-measured, unless it accepts a restore step |
| R4 | **The bind-mount remedy has a live blocker the report only gestures at.** `USER app` (`Dockerfile:150`) cannot write `/app` — observed `PytestCacheWarning … Errno 13`. A `../src:/app/src` mount puts host-owned, host-permissioned files where `uv sync` baked the venv | observed this session; `Dockerfile:132-150` | HIGH — the highest-risk single change, now with a concrete failure mode |
| R5 | **Failure count remains unmeasured at HEAD.** I ran one module (1 failed / 6 passed). The report's four runs (10/11/12) are at a tree 30 commits old, and 9 test files this phase cites have changed | §1.3 | MEDIUM — the roadmap's "Step 0 green" gate has no current figure to close against; TST-012's instability means one green run proves nothing |
| R6 | **Adding `session=None` worker coverage will commit real rows into `bidb_test`** on paths that previously ran against `AsyncMock`, compounding TST-012. The report says so; nothing in the tree mitigates it | `test_data_worker.py:395-400`; the 13 `process_csv_background` drivers all pass a session | HIGH — sequencing constraint between TST-007 and TST-012 blocks |
| R7 | **`test_config.py` and `config.py` moved again** (77 cache calls, first at `:495`/`:496`; `config.py` `:1032`/`:1035`/`:1054`). The report's `VAL-09-008` items 2 and 7 will read as citation errors | re-measured | LOW — mechanism unchanged |
| R8 | **`test_rq_worker.py`'s primary anchor is stale** (3 vars, not 11) and a *larger* 10-var leak site now exists at `:189-205` | re-measured | MEDIUM — a block written from the report's anchor would patch the wrong test |
| R9 | **Meta-risk: tests asserting current wrong behaviour.** Four live instances: `test_create_layout_duplicate_name_returns_400` asserts `400` against a `422` product (TST-011); `test_admin_cannot_delete_self` asserts a global count it cannot control (TST-012); `test_rate_limiter_fail_open_on_redis_error` pins fail-open as intended (`security.py:98-103`, unowned per VAL-09-004); `test_different_ips_have_separate_limits` passes under a global-constant limiter (TST-006). Making these green without a decision re-encodes the defect | §2, per-finding seams | HIGH — the single largest correctness hazard in this phase |
| R10 | **`Invoke-Check` short-circuits on first failure.** Adding `Invoke-Test` as a fifth link inherits that shape, so a red `lint` still hides the test result. Phase 08's D1 leaves this open | `Makefile.ps1:241-249`; `08-…:426` | MEDIUM |
| R11 | **Sibling plans name tests that will break.** Phase 04 rewrites the rate-limit key derivation (`AB-6`); phase 07's `EB-3`/`EB-7` change the peer identity the hard-coded `127.0.0.1` literal assumes. Both name `test_rate_limit_reset_allow_writes` as a hard blocker | §3.3 | HIGH — a phase-09 rewrite of that file races two live plans |
| R12 | **`VAL-09-004`'s subject has no owner.** `security.py:107 fail_closed: bool = False` is pinned as intended behaviour by `test_auth.py:298-332` and `:335-369` and deferred to `AUTH-002`, which owns `TempPasswordStore` (`auth_service.py:595-596`, `:668-669` store *after* the `:590`/`:663` commits — landed `2de4156`). A block that "unpacks the tuple" will silently bless the fail-open default | `security.py:98-103`; `auth_service.py:590`/`:595-596` | MEDIUM — a decision, not a code change |

---

## 6. Decision points for the Planner

Genuine uncertainty only. **I pick none.**

| ID | Question | Alternatives | Chooser |
|---|---|---|---|
| **DP-1** | **What object does `redis_client.get_async_redis_client()` at `auth.py:563` resolve to under `async_client`?** Static reading says `MockRedis` (`:176-223`) has no such method, so the third limiter's construction would raise `AttributeError` **outside** `check_rate_limit`'s `try` and the endpoint would 500. Runtime refutes the prediction: `test_register_request_rate_limit_exceeded` **passed**, and the log shows `Registration request rate limit exceeded … "ip": "127.0.0.1"`. I could not close this without instrumenting the container | (a) treat the third limiter as covered and leave TST-005 at "two stores"; (b) spend one probe run (`-s` with a patched dependency, or reading the FastAPI signature resolution for that route) before fixing anything; (c) treat the register-request limiter as a separate TST-005 sub-item regardless of mechanism | Planner — needs a 2-minute probe before any TST-005 block is scoped |
| **DP-2** | **Does phase 09 own `test_different_ips_have_separate_limits` and `test_x_forwarded_for_spoofing_ignored` now, or wait for phase 04's `AB-6`?** Phase 04 says phase 09 owns their *quality*; phase 07 hands the per-IP test over by name. Phase 04 also says any change to key derivation must land *with* the test | (a) phase 09 rewrites both now and phase 04 adjusts; (b) phase 09 marks them skipped/blocked pending `AB-6`; (c) phase 09 rewrites only the assertions that do not depend on the key derivation | Planner, coordinated with phase 04's plan owner |
| **DP-3** | **Is `test_create_layout_duplicate_name_returns_400` a phase-09 test fix or a phase-09 product decision?** The report routes it to a 409-vs-422 decision, which changes the API contract. `ErrorCode.DUPLICATE_RESOURCE → 409` already exists (`exceptions.py:69`) and is unused here | (a) phase 09 asserts 422 and defers the contract; (b) phase 09 raises `DUPLICATE_RESOURCE` and asserts 409; (c) leave red and record as an intentional gate failure | Planner with the API-contract owner |
| **DP-4** | **Who owns the rate limiter's fail-open default** (`VAL-09-004`)? Unpack-the-tuple work will make `test_auth.py:332` and `:369` green and thereby *ratify* fail-open | (a) file it in phase 09; (b) assign to `CFG-006` and state why it is the same question; (c) treat the two tests as blocking and hand them to phase 02 | Planner |
| **DP-5** | **Does `Invoke-Check` keep first-failure-wins when `Invoke-Test` is added?** Phase 08's D1 (`08-…:426`) explicitly leaves this to phase 09's plan owner | (a) keep the shape, minimal diff; (b) phase 08 takes the aggregator shape, phase 09 only adds the link; (c) aggregate runs all and reports a combined verdict | Planner with phase 08's plan owner |
| **DP-6** | **Is `[[tool.mypy.overrides]] module = ["tests.*"]` in phase 09's scope?** Phase 08's D8 (`08-…:433`) leaves it explicitly to phase 09 | (a) include as a "declared rule nothing applies" block; (b) leave to phase 08 | Planner |
| **DP-7** | **Does `test-all`'s coverage gate land with or after `test`?** `test-all` was never run, so the measured percentage is unquoted; enabling `--cov=src/mkobi` may put the first number under 65 | (a) enable on `addopts` (affects `test` too); (b) enable on `test-all` only; (c) enable, read the number, then decide | Planner |
| **DP-8** | **Should the failing tests be repaired against the *product* or against a pending decision?** Nine of the eighteen findings name shipped tests that encode current behaviour. Repairing them first (report's Step 0) makes the gate real; repairing them after the product changes risks asserting a bug | (a) Step 0 before any gate (report's order); (b) gate first, accept red; (c) split — gate infrastructure in parallel, red-test repair after TST-012 | Planner |

---

## 7. Coverage ledger

| Finding | Verdict | Primary evidence anchors at `cea2d06` | Drift |
|---|---|---|---|
| `TST-001` | substantiated | `docker/docker-compose.test.yml:123-167` (no `volumes`); `Makefile.ps1:36`; `docker/Dockerfile:132-155` (`:135`, `:139`, `:150`, `:155`); `Makefile.ps1:196`/`:201`/`:210` | none |
| `TST-002` | substantiated | `Makefile.ps1:241-249`; 10-path CI inventory all `False`; `pytest tests/test_rate_limiting.py` → 1 failed/6 passed | full-suite figure stale |
| `TST-003` | substantiated | `pyproject.toml:196`, `:208`, `:212`; `Makefile.ps1:196`/`:201` | none |
| `TST-004` | substantiated | `frontend/vite.config.ts:56-63`; `frontend/package.json:10`; `Makefile.ps1:237-239` | none |
| `TST-005` | substantiated (one sentence narrowed) | `conftest.py:308`/`:318-319`/`:380`/`:388`/`:546`/`:547-549`; `deps.py:40`/`:125-131`; `auth.py:83-89`/`:146`/`:562-563`; `auth_service.py:19`/`:66-67`; `test_rate_limiting.py:16`/`:75`/`:107`/`:155` | +1 limiter path unreported; DP-1 open |
| `TST-006` | substantiated | `test_rate_limiting.py:124`/`:138-139`/`:154-193`; `auth.py:83`/`:89` | none |
| `TST-007` | substantiated | `data_worker.py:241`/`:260`/`:310`/`:328`/`:855`/`:566`/`:899`; 0 production `session=None` drivers | +14 … +303 lines |
| `TST-008` | substantiated | `conftest.py:540-543`/`:559`/`:566`; `deps.py:101` | none |
| `TST-009` | substantiated (one claim refuted) | `conftest.py:510-519`; `test_auth_service.py` 50 fns; **5th consumer `test_user_service.py:50-146`** | counts moved; "four files" → five |
| `TST-010` | substantiated | `security.py:111-113`/`:88`/`:103`; `test_auth.py:264`/`:278`/`:291`/`:295`/`:332`/`:369`/`:384`/`:388`/`:392` | none |
| `TST-011` | substantiated (2 of 3) | `exceptions.py:263-297`/`:280`/`:281`/`:295`/`:56`/`:69`; `test_layouts.py:366-367`/`:383-384`/`:407-409`; `layouts.py:104-109` | none |
| `TST-012` | substantiated | `conftest.py:468-497`/`:463`/`:590`/`:431-433`; 6 compensating `DELETE`s at `test_processing_logs.py:122-398`; `test_users_api.py:165`; `starter.py:207`/`:230-256`/`:308-311` | 3× more compensators; residual (b) refuted |
| `TST-013` | substantiated (anchor stale) | `test_rq_worker.py:148-158` (3 vars) **and `:189-205` (10 vars)**; `config.py:1032`/`:1035`/`:1054`; `conftest.py:60`/`:80`/`:413` | primary anchor rewritten by `9a77625` |
| `TST-014` | substantiated | 15 tracked paths; `.gitignore:39-47`; `frontend/.gitignore:10-12`; `package.json:10` | none (not re-executed) |
| `TST-015` | substantiated (re-typed) | `validators.py:183-205`; `models/auth.py:178`/`:205`/`:207`; `formSchemas.ts:56-59`; `formSchemas.test.ts:156-163` | none |
| `TST-016` | substantiated | `test_media_dash.py:129`; `aggregated_data.py:77-81`; `starter.py:190-191`; `test_dev_seeders.py:70` (0 `AggregatedData`) | none |
| `TST-017` | substantiated | `pyproject.toml:196`/`:200-202`; 0 marker uses; `session.py:110` only `create_all` | none |
| `TST-018` | substantiated | `test_enum_db_consistency.py:1-7`/`:66`/`:107`/`:169`/`:179-191`/`:230`/`:248` | none |
| `VAL-09-001` | substantiated | `test_users_api.py:146`; `test_e2e_upload.py:144-145` | — |
| `VAL-09-002` | substantiated | TXN-008 owns `test_media_dash.py:129` + `starter.py:190-191` | — |
| `VAL-09-003` | substantiated | `formSchemas.ts:56-59` is client-tier | — |
| `VAL-09-004` | substantiated; unowned | `security.py:107`/`:98-103`; `test_auth.py:298-332`/`:335-369` | — |
| `VAL-09-005` | substantiated | `test_pydantic_models.py:100` in `TestUserModels` (`:46`) | — |
| `VAL-09-006` | substantiated (not re-executed) | 15 tracked paths; `frontend/.gitignore` has no coverage line | — |
| `VAL-09-007` | substantiated | `test_rate_limiting.py:44-46`/`:57-59` vs `:154-193` | — |
| `VAL-09-008` | substantiated; items 2 & 7 drifted further | `test_config.py` **77** calls, first `:495`/`:496`; `config.py` `:1032`/`:1035`/`:1054` | yes |
| `VAL-09-009` | **stale (refuted-back)** | image `5b1d9b41d128` @ `20:16:44` **older** than `cea2d06` @ `20:27:35` | yes — reversed |
| `VAL-09-010` | substantiated | template contract only | — |
| `VAL-09-011` | substantiated | `test_layouts.py:407-409`; `exceptions.py:56` | — |
| `VAL-09-012` | substantiated | `VAL-001`…`VAL-008` collision across phases 01/02 | — |

**Not covered by any finding ID, surfaced here:** `auth.py:310-317` (`refresh:` limiter, a fourth rate-limit site) and `auth.py:899 process_csv_background_sync` (a fourth worker entry point, alongside `:855`). Neither is asserted anywhere in the suite.
