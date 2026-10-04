# Plan 19 — Test Coverage & Validation Remediation (Phase 09)

**Status:** Execution plan — read-only artefact. This file changes no code and no audit-phase file.
**Written:** 2026-10-04
**Tree fact:** commit `f1606f0`.

---

## 1. Header

### 1.1 Purpose

Turn the validated phase-09 audit report into an ordered, dependency-safe set of independently
committable execution blocks, each with an explicit agent requirement set, risk split, acceptance
criteria and verification protocol. Where technical uncertainty exists the plan **presents
alternatives and a recommendation and does not choose**; the choice is delegated to a Researcher
(measurement), an Auditor (contract adjudication) or the Product Owner (ruling).

### 1.2 Sources

| Source | Role |
|---|---|
| `.ai/audit/99-validation/09-test-coverage-validated-findings.md` | **Finding identity.** 18 findings `TST-001`…`TST-018` (2 CRITICAL, 7 HIGH, 7 MEDIUM, 2 LOW) plus 12 validation-level findings `VAL-09-001`…`VAL-09-012`. Referenced, never restated or copied. **Not edited by this phase.** |
| Verified mechanical state at `f1606f0` | All tree facts, baselines and counts in this plan. The report was written at `b23a9cb` — **113 commits ago** — so its line numbers are stale and its counts moved. **Never anchor work to a report line number.** |
| `.kilo/rules/commands.md` | Authoritative command reference. `.ai/context/commands.md` is **stale** — do not use it. |

### 1.3 Supersession

**This plan supersedes `.ai/plans/09-test-coverage-remediation-execution.md` for all phase-09 work.**

Reason — that plan's `TST-*` → block mapping is **wrong for 13 of 18 identifiers**, provable from
its own subjects naming findings the code does not contain:

- its `TCO-2` block is "give the 34 xfail tests a timeout" and its `TCO-10` is "give the skips
  reasons", while **0 `xfail` and 0 `skip` markers exist anywhere in `tests/` or `src/`**;
- its `TCO-3` block discusses a `StrictRedis` **class** while **0 occurrences of that name exist**
  (the lower-case `strict_redis` **fixture** is used 31 times, so the *target name* is wrong, not
  the underlying concern);
- its block inventory therefore cannot be used to decide what is done, and following it would
  produce edits to constructs that do not exist.

**Scope of this plan:**

- This plan touches **no other phase's plan**.
- This plan touches **nothing under `.ai/audit/**`**.
- No block in this plan modifies production code except where a Product Owner ruling explicitly
  authorises an API contract change (TCR-13), and then only in the single place named.

**Namespace note:** block ids use the `TCR-` prefix specifically to avoid colliding with the
`TCO-` ids in the superseded plan and with the audit's `TST-` / `VAL-09-` ids. Block ids are
**ordinal**: `TCR-01` is the first block to execute.

---

## 2. Per-finding disposition table

Severity column: `CRIT` / `HIGH` / `MED` / `LOW` were **mechanically re-verified** in this pass for
11 of 18 ids; the remaining 7 (`TST-005`, `TST-006`, `TST-008`, `TST-010`, `TST-011`, `TST-015`,
`TST-016`) are marked `—` and **must be read from the report**, never inferred. The verified subset
(2 CRIT + 4 HIGH + 3 MED + 2 LOW) is arithmetically consistent with the report's stated totals
(2/7/7/2); the 7 unverified ids are 3 HIGH + 4 MED.

| id | severity | verified status at `f1606f0` | owning block | repository change |
|---|---|---|---|---|
| `TST-001` | CRIT | **Present.** `test-app` has no `volumes:`; Dockerfile `test` stage bakes `src/`+`tests/` then ends `USER app`. 191/192 files byte-identical image↔host; **`tests/test_config.py` differs** (image 1338 / host 1124 lines). A host test edit is invisible to the gate and the run looks identical. | `TCR-01`, `TCR-10` | **yes** (harness) |
| `TST-002` | CRIT | **Present.** `Invoke-Check` never calls `Invoke-Test`; no CI configuration exists anywhere; three `if ($LASTEXITCODE -ne 0) { return }` guards make it first-failure-wins. | `TCR-09`, `TCR-32`, `TCR-33`, `TCR-34` | **yes** (harness) + conditional (CI) |
| `TST-003` | HIGH | **Present.** `pyproject.toml` `[tool.pytest.ini_options] addopts` has `--cov-fail-under=65` with **no `--cov=`**; `fail_under = 65` duplicated in `[tool.coverage.report]`. Floor inert on `test`, live only on `test-all`. | `TCR-27` | **yes** (config) |
| `TST-004` | HIGH | **Present.** `frontend/vite.config.ts` coverage block: v8 provider, `text`/`json`/`html` reporters, thresholds 50/40/45/50, and **no `include` / `exclude` / `all`**. On a red run vitest prints **no coverage table and no threshold verdict**. | `TCR-08`, `TCR-28` | **yes** (config) |
| `TST-007` | HIGH | **Present.** Worker module still branches on injected session (`if db_session is not None:` / `else:`) in three functions; **every** test call site passes a session, so the compensating branch is never exercised. | `TCR-07`, `TCR-19` | **yes** (tests) |
| `TST-009` | HIGH | **Present, counts stale.** `mock_db` is `AsyncMock(spec=AsyncSession)`, now consumed by **four** modules; one (user-service) has **55** test functions. | `TCR-05`, `TCR-22`…`TCR-24` | **yes** (tests) |
| `TST-012` | MED | **Present.** `async_db_session` opens a nested transaction and rolls back, but `Session.commit()` commits the **root**; committed rows survive. `expire_on_commit=False`. Docstring still claims savepoint rollback. Compensating surface = **12** `delete(ProcessingLog)` sites in one module. | `TCR-04`, `TCR-17`, `TCR-25`, `TCR-26` | **yes** (tests) |
| `TST-013` | MED | **Present.** Cached `_settings` singleton, `clear_config_cache()` is the only reset, **no autouse teardown fixture**. Two modules mutate 3 and 11 env vars; **13** files call the reset by hand; **20** modules sort after the mutating one. | `TCR-20`, `TCR-21` | **yes** (tests) |
| `TST-014` | MED | **Present.** **15** files under `frontend/coverage/` are tracked. Root `.gitignore` ignores `htmlcov/`, `.coverage`, `.coverage.*`, `coverage.xml`, `*.cover`, `cover/` — **not** the `coverage/` **directory**; `frontend/.gitignore` does not mention coverage. A **failing** run writes nothing; a run that **emits a report** rewrites the dir. | `TCR-29` | **yes** (vcs/config) |
| `TST-017` | LOW | **Present.** `slow` and `fast` registered in `addopts` under `--strict-markers`; **0** tests use either. `fast`'s description names a `create_all()` schema-build path no test uses (the only `create_all` in the codebase is inside `init_db()`, which no test calls). | `TCR-30` | **yes** (config) |
| `TST-018` | LOW | **Present.** The enum-consistency module's docstring promises a two-way check ("after the DB-001 migration there should be zero extra values") but only the processing-status test is two-way; user-role, permission-level and aggregate tests are one-way, and the aggregate test's own docstring claims the check it does not perform. | `TCR-31` | **yes** (tests) |
| `TST-005` | — | **Partially fixed.** `MockRedis` still instantiated in three places in `tests/conftest.py`, but the autouse Redis fixture now *also* stubs `AuthService.check_rate_limit` and `strict_redis` now *restores* `__init__`. Accurate framing: **one dead store instance with two live side effects**, not three dead instances. The store-reading test now reads the store the route wrote. **Open:** the report also requires covering a second limiter built inside `AuthService.__init__`, but a security-phase report calls that instance *constructed and never called* — it may be dead code. | `TCR-06`, `TCR-18` | **yes** (tests) |
| `TST-006` | — | **Already fixed** — the hard-coded `login:127.0.0.1` key is gone; tests derive keys from production's own key-construction helper. **Residual only:** `tests/test_rate_limiting.py::test_different_ips_have_separate_limits` is still **vacuous** (one IP, one key, a single over-limit assertion). | `TCR-15` | **yes** (tests) |
| `TST-008` | — | **Partially fixed.** The HTTP fixture still overrides the DB dependency and uses an in-process ASGI transport. **But** other phases have since added direct commit-ownership tests that do not depend on that override, so the sibling finding this gated is partially covered by another route. Residual real-DB-dependency work is **owned by the transaction phase**. | — (see §6) | **no** in phase 09 |
| `TST-010` | — | **Present.** `tests/test_auth.py::TestRateLimiting` has 5 test functions and **8 bare-scalar assertion sites**, all `assert result is True/False` against a value that is always a 2-tuple. 3 in `..._allows_under_limit`, 2 in `..._blocks_over_limit`, 1 in `..._fail_open_on_redis_error`, 1 in `..._fail_closed_on_redis_error`, 3 in `..._different_ips_independent`. Three of the eight are inside loops. | `TCR-11` | **yes** (tests) |
| `TST-011` | — | **Present, 3 tests.** `RequestValidationError` handler emits RFC 7807 with `detail` as the **string** `"Request validation failed"` and the field array in a **top-level `errors`** key. The two `..._returns_422` tests read `data["detail"]` and assert it is a `list` → red on shape; their `status_code == 422` assertion **passes**. `test_create_layout_duplicate_name_returns_400` asserts `400` and fails on `422 == 400` — a **status-code contradiction**, not a shape one. | `TCR-03`, `TCR-12`, `TCR-13` | **yes** (tests) + conditional (API) |
| `TST-015` | — | **Out of scope.** The client/server password-policy divergence. Ruled by Product Owner `DP-13-H` (2026-10-03): server authoritative, client mirrors it, uppercase rule dropped **from the client**, **not** added to the server. Owner = phase 13 block `CT-2`, which edits the production client schema. | — (see §6, ordering trap) | **no** |
| `VAL-09-001` … `VAL-09-012` | — | **All 12 are defects in the audit document itself** — bad counts, two wrong cross-references, three mis-attributed causes, one template-contract breach, one namespace collision. **None requires a repository change.** Recorded **closed-no-action**; `.ai/audit/**` must not be edited by this phase. | — (see §6) | **no** |
| *(new, validator cross-finding)* | — | **`tests/test_pydantic_models.py::TestUserModels::test_user_db_valid` is red**: `UserDB` requires `updated_at`, the test payload omits it; the SQLAlchemy model declares `updated_at` as a required `datetime`. **Not in the audit report at all.** Whether the fix is (a) test payload, (b) schema default, or (c) model change is unsettled. | `TCR-02`, `TCR-14` | **yes** (tests or models) |
| *(new, measured)* | — | **Backend baseline: `collected 1410 items` → 9 failed, 1401 passed, 33 warnings in 484.56s.** The 9 are `TST-010` (5), `TST-011` (3), and `test_user_db_valid` (1). **Count is unstable** — the report measured 10, 11 and 12 on identical code. `tests/test_users_api.py::TestDeleteAccount::test_admin_cannot_delete_self` and `tests/test_e2e_upload.py::…::test_e2e_multiple_graphs_same_dashboard` pass today but are **order-dependent**. | `TCR-33` (gate) | **no** |

**Do not redo landed work.** `TST-006`'s key-derivation fix and `TST-016`'s upsert seeder change are
already in the tree. `TST-016` is listed with `TST-005` above only as a residual; the audit's own
severity for it must be read from the report.

---

## 3. Execution blocks

**Conventions used by every block**

- Targets are **semantic** (file, module, class, function, test name, config key, TOML table, Docker
  stage, Compose service key). **Never a line number** — the tree moves and the report's numbers are
  113 commits stale.
- `test-app` image parity is a **precondition of every verification** in this plan. See §8.
- No assertion, skip or marker may be weakened to make a change land. Every test changes *with* the
  behaviour it pins.
- Production code changes are forbidden except in `TCR-13` under an explicit Product Owner ruling.
- Agent requirement **"yes"** means the named agent must run *before or during* the block, as the
  justification states.

---

### Wave A — Measurement and rulings (read-only; no repository change)

#### TCR-01 — Measure whether `test-app` can see the working tree, and decide the harness option
- **Findings closed:** none. **Gates:** `TCR-10`.
- **Exact scope:** Reproduce and characterise the image/host divergence for `test-app`; decide
  between the harness options below. Produce a short written decision record inside this plan's
  block comment or a new `.ai/plans/` note — **no production change**.
- **Semantic-unit targets:** `Makefile.ps1` → `Invoke-Test`, `Invoke-TestAll`, `Invoke-TestSelect`
  (assert the string `--build` is absent from the whole file);
  `docker/docker-compose.test.yml` → service `test-app` (its key set, and the absence of a
  `volumes:` key); `docker/Dockerfile` → stage `test` (its `COPY` set and its terminal `USER app`);
  the resolved uid/gid of the `app` user inside the built image; a host-write probe at the
  corresponding paths.
- **Options to measure (do not pre-select):**
  - **A — bind mount** `src/` and `tests/` (and any config the suite reads at runtime) into
    `test-app` as volumes. A sibling plan records an observed `Errno 13` on write inside the
    container and declares this infeasible *as written*; that is a **measurement to reproduce, not
    a settled verdict** (uid mismatch, Windows Docker Desktop bind semantics, and a read-only
    default mount are all candidate causes).
  - **B — `--build` on every test target.** Proven-simple, no uid problem, costs an image rebuild
    per invocation (minutes) and makes the slow path the default.
  - **C — hybrid:** bind mount for `tests/`+`src/` when the platform permits, `--build` as the
    hermetic fallback for CI.
- **depends_on:** none.
- **Agents:** **Researcher — yes**, this block *is* a measurement and it is cheap and decisive.
  **Auditor — no** (no contract question). **Planner — no** (already planned). **Validator — no**
  (nothing to validate yet).
- **Risks — implementation:** picking A on a platform where bind semantics are unsound reintroduces
  a silent-divergence bug worse than the current one. **rollout:** changing the harness invalidates
  every cached layer; first run after the change is slow. **regression:** none — read-only.
  **compatibility:** the `test-db` / `test-redis` named volumes and the `mkobi-test` project name
  must keep working; `test-app` uses `--no-deps` and must not acquire a dependency on the host
  layout beyond the mount.
- **Acceptance criteria:** a written answer to "can a host edit of `tests/` be observed by
  `Invoke-Test` under option A, yes/no, with the exact error if no"; a named uid/gid; a cost
  estimate per invocation for options B and C; one recommended option with its blast radius.
- **Commit shape:** none (read-only). Decision recorded as `docs(harness): record test-app worktree
  visibility measurement (TCR-01)`.

#### TCR-02 — Adjudicate the `UserDB.updated_at` contract
- **Findings closed:** none. **Gates:** `TCR-14`.
- **Exact scope:** Determine which of the three parties owns `updated_at` and therefore who must
  change. No repository change.
- **Semantic-unit targets:** the Pydantic schema `UserDB` and its `updated_at` requirement; the
  SQLAlchemy `User` model's `updated_at` column declaration (`required datetime`);
  `tests/test_pydantic_models.py::TestUserModels::test_user_db_valid` and its payload dict; every
  other construction site of `UserDB` in `src/` and `tests/`.
- **depends_on:** none.
- **Agents:** **Auditor — yes**, this is a contract-ownership question across the DTO/ORM boundary
  and must not be decided by an Implementor. **Researcher — no.** **Planner — no.**
  **Validator — no.**
- **Risks — implementation:** choosing (c) relaxes a DB-level invariant and could mask a real
  integrity gap; choosing (b) hides a missing field from every caller. **rollout:** (c) would
  require an Alembic migration and is therefore a *schema* change — out of phase-09 minimal scope
  unless the Auditor rules it necessary. **regression:** any other `UserDB` construction site
  changes behaviour. **compatibility:** a schema default changes the OpenAPI contract for
  `updated_at`.
- **Acceptance criteria:** a written ruling naming the owning layer, the minimal change, the
  migration implication (yes/no), and the list of affected construction sites.
- **Commit shape:** none (read-only). `docs(models): record UserDB.updated_at contract ruling
  (TCR-02)`.

#### TCR-03 — Ruling packet for the duplicate-layout status code
- **Findings closed:** none. **Gates:** `TCR-13`.
- **Exact scope:** Assemble the decision and hand it to the Product Owner. No repository change.
- **Semantic-unit targets:** `src/mkobi/utils/exceptions.py` → `_ERROR_CODE_STATUS_MAP`
  (confirm `VALIDATION_ERROR → 422`, `EMAIL_ALREADY_EXISTS`/`FILTER_ALREADY_BOUND`/
  `DUPLICATE_RESOURCE → 409`); `src/mkobi/api/routes/layouts.py` → the duplicate-name `ValueError`
  handler that raises `AppException(code=ErrorCode.VALIDATION_ERROR, …)`;
  `tests/test_layouts.py::TestLayoutsAPI::test_create_layout_duplicate_name_returns_400`; every
  frontend consumer of the layout-create error path; the OpenAPI/error documentation.
- **Facts to state in the packet (do not soften):** the route emits **422** today; three codes
  already map duplicate-class conditions to **409** in the same codebase; two in-flight sibling
  tasks already resolve "duplicate ⇒ conflict"; and the test asserting `400` describes a status
  the route **never emits**.
- **depends_on:** none.
- **Agents:** **Auditor — yes** (enumerate blast radius: consumers, docs, contract tests).
  **Researcher — no.** **Planner — no.** **Validator — no.** **Product Owner — yes**, only the
  Product Owner may rule (open decision OD-3, §5).
- **Risks — implementation:** none yet. **rollout:** a 422→409 change is an **API contract change**
  for clients keying on the status. **regression:** frontend error-extraction chain
  (`frontend/src/shared/api/errorHandler.ts`) must keep producing a usable message for the new code.
  **compatibility:** documented error semantics in `docs/08-security/error-format.md` and
  `docs/99-reference/error-handling-guide.md` would need updating if the ruling is 409.
- **Acceptance criteria:** a ruling of `409` or `422`, recorded, with the blast-radius list
  attached. **If no ruling arrives**, `TCR-13` does not execute and the third layout test stays red
  and is recorded as an owner-blocked item — it is explicitly **not** to be made green by weakening
  the assertion.
- **Commit shape:** none (read-only). `docs(api): record duplicate-layout status ruling packet
  (TCR-03)`.

#### TCR-04 — Adjudicate the session-isolation shape (`TST-012`)
- **Findings closed:** none. **Gates:** `TCR-25`, `TCR-26`.
- **Exact scope:** Choose the isolation shape and the order in which the compensating surface is
  removed. No repository change.
- **Semantic-unit targets:** the `async_db_session` fixture in `tests/conftest.py` (its nested
  transaction, its rollback, `expire_on_commit=False`, its docstring); the **12**
  `delete(ProcessingLog)` call sites in the single test module that carries them; every test that
  relies on committed data surviving a test.
- **Options (all three presented; none pre-selected):**
  - **A — join an external transaction** (SQLAlchemy "join an external transaction" recipe). Makes
    `Session.commit()` nest, so rollback really rolls back. **Whole-suite blast radius.**
  - **B — explicit per-module truncation** at teardown. More code, more lock contention, but a
    contained blast radius per module.
  - **C — correct the misleading docstring only**, defer the rest.
- **Recommendation (advisory):** **A**, executed module-by-module in a fixed order, with C done first
  so the suite stops lying about its own semantics. A is the only shape that removes the root cause
  rather than the symptom; B is the fallback if A destabilises the suite.
- **depends_on:** none.
- **Agents:** **Auditor — yes** (must enumerate every test that depends on the current
  commit-survives-test behaviour; this determines the blast radius). **Planner — yes** (if the
  ruling is A, the per-module migration order is a planning artefact, not an implementation detail).
  **Researcher — no.** **Validator — no.**
- **Risks — implementation:** A changes what many currently-green tests observe — this is the
  second **non-revertible** block class in this plan (§7). **rollout:** a mid-suite behaviour flip
  can look like mass regression. **regression:** the highest risk in the phase; requires ≥2 full
  runs before the gate is trusted. **compatibility:** none external (test-only).
- **Acceptance criteria:** a written ruling, a per-module order, and an explicit statement of which
  currently-green tests are expected to change behaviour.
- **Commit shape:** none (read-only). `docs(tests): record session-isolation shape ruling (TCR-04)`.

#### TCR-05 — Map the `mock_db` consumers and define the real-session seam
- **Findings closed:** none. **Gates:** `TCR-22`.
- **Exact scope:** Replace the audit's stale counts with the real consumer map and specify the seam.
  No repository change.
- **Semantic-unit targets:** the `mock_db` fixture (`AsyncMock(spec=AsyncSession)`) in
  `tests/conftest.py`; its **four** consuming test modules, one of which is the user-service module
  with **55** test functions; the real `AsyncSession` construction path used by
  `async_db_session`.
- **depends_on:** none.
- **Agents:** **Auditor — yes** (the report's counts are stale; the map must be re-derived).
  **Planner — no** (the migration order is fixed in §4). **Researcher — no.** **Validator — no.**
- **Risks — implementation:** a seam that still permits `AsyncMock` lets the mock survive and the
  work is wasted. **rollout:** none (read-only). **regression:** none yet. **compatibility:** none.
- **Acceptance criteria:** a table of consumer module → test count → mocking depth, plus a named
  seam that yields a session bound to the same schema/transaction discipline as the other
  fixtures.
- **Commit shape:** none (read-only). `docs(tests): record mock_db consumer map and seam (TCR-05)`.

#### TCR-06 — Verify whether the `AuthService` limiter instance is live
- **Findings closed:** none. **Gates:** `TCR-18`.
- **Exact scope:** Determine whether the limiter built inside `AuthService.__init__` is ever called.
  **No repository change** — and specifically, **no dead-code removal here**: production dead code
  is the security phase's to remove.
- **Semantic-unit targets:** the limiter instance attribute on `AuthService`; every read/write of
  that attribute across `src/`; `AuthService.check_rate_limit`; the autouse Redis fixture's stub
  of `AuthService.check_rate_limit` in `tests/conftest.py`.
- **depends_on:** none.
- **Agents:** **Researcher — yes** (a liveness question, answerable by static reachability plus a
  cheap runtime probe). **Auditor — no.** **Planner — no.** **Validator — no.**
- **Risks — implementation:** editing the fixtures before this answer risks *removing a mock that
  is masking a live call*. **rollout:** none. **regression:** this is the exact scenario that would
  produce a false green. **compatibility:** if the instance is dead, `TST-005`'s second half is
  **not actionable in phase 09** and is handed to the security phase.
- **Acceptance criteria:** a yes/no on liveness with the call sites listed, or a statement that the
  attribute is written and never read.
- **Commit shape:** none (read-only). `docs(auth): record AuthService limiter liveness (TCR-06)`.

#### TCR-07 — Probe worker-session testability (`TST-007`)
- **Findings closed:** none. **Gates:** `TCR-19`.
- **Exact scope:** Establish how a test can obtain a real session from the worker module's **own**
  session factory (not the test fixture's) so the compensating branch is exercisable.
- **Semantic-unit targets:** the worker module's session factory; the three functions sharing the
  `if db_session is not None:` / `else:` shape; every test call site of those three functions (all
  pass a session today).
- **depends_on:** none.
- **Agents:** **Researcher — yes** (testability of a production factory is a measurement, and the
  answer decides whether `TST-007` is test-only or needs a production seam). **Auditor — no.**
  **Planner — no.** **Validator — no.**
- **Risks — implementation:** if the factory is module-private and non-overridable, a test-only fix
  is impossible and a minimal production seam is required — which would be a scope expansion
  needing a fresh ruling. **rollout:** none yet. **regression:** none yet. **compatibility:** none.
- **Acceptance criteria:** a written statement of the smallest viable injection point, with the
  alternative (monkeypatching the module attribute vs adding a parameter) and a yes/no on whether
  production code must change.
- **Commit shape:** none (read-only). `docs(workers): record worker session injection probe
  (TCR-07)`.

#### TCR-08 — Measure the frontend coverage population and the true baseline
- **Findings closed:** none. **Gates:** `TCR-28`.
- **Exact scope:** Quantify what the coverage gate is *currently* measuring and what it *should*
  measure, and obtain the real numbers. No repository change.
- **Semantic-unit targets:** the `test.coverage` block in `frontend/vite.config.ts` (v8 provider;
  `text`/`json`/`html` reporters; thresholds statements 50 / branches 40 / functions 45 / lines 50;
  absent `include` / `exclude` / `all`); the frontend source tree under `frontend/src`.
- **Confirm in passing:** a green single-file run reports an **empty per-file table** and
  `Statements : 100% ( 9/9 )`; on a red run vitest prints **no coverage table and no threshold
  verdict at all**.
- **depends_on:** none.
- **Agents:** **Researcher — yes** (the numbers gate the threshold values; guessing them is how
  gates get disabled). **Auditor — no.** **Planner — no.** **Validator — no.**
- **Risks — implementation:** adding `all: true` without an `include` can pull in generated or
  type-only files and collapse the percentage to near zero. **rollout:** the first run after the fix
  rewrites `frontend/coverage/` (see `TST-014`, `TCR-29`). **regression:** none.
  **compatibility:** the `json`/`html` reporters are consumed by nobody known to this phase — a
  consumer check belongs in this block.
- **Acceptance criteria:** the real per-metric percentages for the intended population, a proposed
  `include`/`exclude` set, and a proposed threshold set with the delta from current values.
- **Commit shape:** none (read-only). `docs(fe): record frontend coverage population measurement
  (TCR-08)`.

#### TCR-09 — CI workflow ruling (open by design)
- **Findings closed:** none. **Gates:** `TCR-34`.
- **Exact scope:** Obtain a Product Owner ruling on creating a CI workflow now or deferring it. No
  repository change in this block.
- **Semantic-unit targets:** the repository's remote (GitHub `manicko/mkobi`, branch `feat/react`)
  and the confirmed **absence** of any CI configuration: no `.github/`, `.gitlab-ci.yml`,
  `.circleci/`, `azure-pipelines.yml`, `Jenkinsfile`, `.husky/`, `.pre-commit-config.yaml`,
  `tox.ini`, `noxfile.py`, `.git/hooks/pre-commit`.
- **depends_on:** none.
- **Agents:** **Auditor — no.** **Researcher — no.** **Planner — no.** **Validator — no.**
  **Product Owner — yes.**
- **Risks — implementation:** a workflow created now is **red on arrival** because the frontend
  suite cannot be green in this phase (OD-3/`DP-13-H` ordering) and the backend failure count is
  unstable. **rollout:** a red required check can block merges immediately. **regression:** none.
  **compatibility:** the workflow must not duplicate `Invoke-*` logic — it should call
  `.\Makefile.ps1` targets so local and CI behaviour cannot drift.
- **Acceptance criteria:** a ruling of *now* or *defer*. If *defer*, the record states what must be
  true before CI is created.
- **Commit shape:** none. `docs(ci): record CI workflow ruling (TCR-09)`.

---

### Wave B — Measurement foundation (must land first)

#### TCR-10 — Make the backend test target measure the working tree
- **Findings closed:** `TST-001`.
- **Exact scope:** Apply the option chosen in `TCR-01` so that a host edit under `src/` or `tests/`
  is visible to `Invoke-Test` / `Invoke-TestAll` / `Invoke-TestSelect`. Nothing else.
- **Semantic-unit targets:** `Makefile.ps1` → `Invoke-Test`, `Invoke-TestAll`, `Invoke-TestSelect`
  and any shared helper they all call; `docker/docker-compose.test.yml` → service `test-app`'s
  `volumes` (and `user`/`working_dir` if the chosen option needs them); `docker/Dockerfile` → stage
  `test` (only if the chosen option requires touching the terminal `USER app` or stage ordering).
- **Constraint:** `dev` and `prod` stages also end `USER app` — **do not change their final user or
  stage order** as a side effect of editing the `test` stage.
- **depends_on:** `TCR-01`.
- **Agents:** **Researcher — no** (measurement closed in `TCR-01`). **Auditor — no.**
  **Planner — no.** **Validator — yes** — the whole phase rests on this block, so it must be proven
  with a sentinel edit, not inferred from a passing run.
- **Risks — implementation:** a mount that silently falls back to the baked copy reproduces the
  original defect. **rollout:** this is a **harness-level change affecting every backend
  verification in the project** — non-revertible in the §7 sense. **regression:** if bind mounts
  are used, host line endings / file permissions / `__pycache__` writes can produce new failures
  unrelated to any finding. **compatibility:** the named volumes of `test-db` / `test-redis`, the
  `mkobi-test` project name, and the "never pass `--project-directory`" rule from
  `.kilo/rules/commands.md` must all keep working.
- **Acceptance criteria:** (1) a one-line sentinel edit to a `tests/` file is observed by
  `Invoke-Test` in the same invocation; (2) `Invoke-TestAll` and `Invoke-TestSelect` behave
  identically; (3) the `test-db` / `test-redis` healthchecks still pass; (4) the full suite still
  collects **1410** items.
- **Commit shape:** `chore(test-harness): make test-app observe the working tree (TCR-10)`.

---

### Wave C — Test-only assertion repairs (parallel; each depends on `TCR-10`)

#### TCR-11 — Repair the rate-limiter assertions by tuple destructuring
- **Findings closed:** `TST-010`.
- **Exact scope:** Fix the **8** bare-scalar assertion sites in `TestRateLimiting`. Nothing else.
- **Semantic-unit targets:** `tests/test_auth.py::TestRateLimiting::test_rate_limiter_allows_under_limit`
  (3 sites), `::test_rate_limiter_blocks_over_limit` (2), `::test_rate_limiter_fail_open_on_redis_error`
  (1), `::test_rate_limiter_fail_closed_on_redis_error` (1),
  `::test_rate_limiter_different_ips_independent` (3) — the last three sites are **inside loops**.
  Read-only reference: `src/mkobi/core/security.py` → `RateLimiter.check_rate_limit`,
  `AsyncRateLimiter.check_rate_limit`, both returning `tuple[bool, int | None]`.
- **Fix shape:** **tuple destructuring** (`allowed, retry_after = await limiter.check_rate_limit(...)`),
  **not** a truthiness rewrite. A truthiness rewrite would make the assertion pass for the wrong
  reason and would silently drop the `retry_after` half of the contract.
- **Hard constraint:** do **not** change what the two `*_fail_open_*` / `*_fail_closed_*` tests
  assert about the default. `fail_closed: bool = False` as a constructor default belongs to the
  security phase's `SEC-003` and is **out of scope here**. These tests pin that default as intended
  behaviour; this block repairs *how* the return value is read, never *what* is expected.
- **depends_on:** `TCR-10`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — five
  currently-red tests turn green here, and the check is that each asserts the *tuple*, not merely
  that the count went down.
- **Risks — implementation:** three sites sit in loops; a destructuring edit inside a loop can
  rebind the wrong name. **rollout:** test-only, fully revertible. **regression:** none expected;
  these five tests are red today. **compatibility:** none.
- **Acceptance criteria:** all five `TestRateLimiting` tests pass; every one of the 8 sites asserts
  on a destructured `allowed`; at least one site additionally asserts the `retry_after` value
  (including the `None` case) so the second tuple element is genuinely pinned; the asserted
  `fail_closed` default is unchanged.
- **Commit shape:** `test(auth): destructure rate limiter results in TestRateLimiting (TCR-11)`.

#### TCR-12 — Repair the two RFC 7807 shape assertions
- **Findings closed:** `TST-011` (partial — the two shape tests only).
- **Exact scope:** Make the two `…_returns_422` tests assert the **actual** RFC 7807 body produced by
  production. Do **not** touch the duplicate-name test here.
- **Semantic-unit targets:** `tests/test_layouts.py::TestLayoutsAPI::test_create_layout_missing_name_returns_422`
  and `::test_create_layout_missing_definition_returns_422`;
  `src/mkobi/utils/exceptions.py` → the `RequestValidationError` handler, which returns
  `detail` as the **string** `"Request validation failed"` and writes the field-level array to a
  **top-level `errors`** key of the `JSONResponse` content; `_ERROR_CODE_STATUS_MAP` →
  `VALIDATION_ERROR → 422`.
- **Fix shape:** read the field array from the top-level `errors` key and filter by `loc` there;
  assert `detail` is the documented string. **Do not** weaken the assertion to "just check 422" —
  the status assertion already passes and is not the defect. The test must pin the real contract,
  including the `code` field, so a future change to the error envelope is caught.
- **depends_on:** `TCR-10`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — this
  block's whole purpose is to make a red test assert the *right* thing; a Validator must confirm the
  new assertions describe RFC 7807 as `docs/08-security/error-format.md` documents it.
- **Risks — implementation:** a test rewritten to match whatever the handler happens to emit stops
  being a contract test — the handler must be read as the specification here, and the *documented*
  contract checked against it. **rollout:** test-only, fully revertible. **regression:** none
  (both are red today). **compatibility:** none.
- **Acceptance criteria:** both tests pass; each asserts the RFC 7807 `type`/`title`/`status`/
  `detail`/`code` set; each locates the field error via the documented key and filters by `loc`.
- **Commit shape:** `test(layouts): assert RFC 7807 error envelope in layout validation tests
  (TCR-12)`.

#### TCR-13 — Apply the duplicate-layout status ruling — **conditional**
- **Findings closed:** `TST-011` (remainder).
- **Exact scope:** Resolve `tests/test_layouts.py::TestLayoutsAPI::test_create_layout_duplicate_name_returns_400`
  according to the `TCR-03` ruling. Two branches, **not** to be merged or pre-decided:
  - **Ruling = 422 (status quo):** test-only. Rename/re-anchor the test to its real contract
    (422 + RFC 7807 envelope + `VALIDATION_ERROR` code) and pin the duplicate message.
  - **Ruling = 409:** an **API contract change**. `src/mkobi/api/routes/layouts.py` → the
    duplicate-name `ValueError` handler raises `AppException(code=ErrorCode.DUPLICATE_RESOURCE, …)`;
    the test asserts 409; the error documentation is updated. `ErrorCode` is a `StrEnum` in
    `src/mkobi/models/enums.py` and `DUPLICATE_RESOURCE` already maps to 409 in
    `_ERROR_CODE_STATUS_MAP` — **no new code string, no new enum member, no `HTTPException`**.
- **Hard constraint (cross-plan contradiction):** the sibling code-quality-phase plan pins this test
  as "the `ValueError` → `400` path" in a table whose preamble forbids weakening any pin. **That pin
  is factually wrong against the code** — the route emits 422. **Phase 09 must not edit that plan,
  must not conform to it, and must not preserve a 400 the route never emits.** If the ruling is 409,
  the sibling plan's pin is still wrong (it says 400) and the contradiction is escalated, not
  silently absorbed. If no ruling arrives, this block does not execute and the test stays red and
  recorded as owner-blocked.
- **depends_on:** `TCR-03` (ruling) **and** `TCR-10`.
- **Agents:** **Auditor — no** (already done in `TCR-03`). **Researcher — no.** **Planner — no.**
  **Validator — yes** — the 409 branch changes an API contract and needs a consumer sweep
  (frontend error-extraction chain, docs, any contract test).
- **Risks — implementation:** in the 409 branch, changing the route can affect other duplicate-path
  callers. **rollout:** API-visible change; downstream consumers may key on the status.
  **regression:** a consumer expecting 422 for this route. **compatibility:** documented error
  semantics change in the 409 branch.
- **Acceptance criteria:** the test passes and names the behaviour it pins; `ruff` and `mypy` pass;
  in the 409 branch the full backend suite is re-run and the OpenAPI/error docs are consistent.
- **Commit shape:** 422 branch — `test(layouts): pin duplicate layout name as 422 validation error
  (TCR-13)`. 409 branch — `fix(layouts): return 409 duplicate resource for duplicate layout name
  (TCR-13)`.

#### TCR-14 — Apply the `UserDB.updated_at` ruling
- **Findings closed:** none of `TST-001`…`TST-018`; closes the **validator-surfaced** red test
  `tests/test_pydantic_models.py::TestUserModels::test_user_db_valid`.
- **Exact scope:** Implement the `TCR-02` ruling. Test-payload change, schema default, or model
  change — chosen by the Auditor, not here.
- **Semantic-unit targets:** `tests/test_pydantic_models.py::TestUserModels::test_user_db_valid`;
  the Pydantic `UserDB` schema's `updated_at` requirement; the SQLAlchemy `User.updated_at` column;
  any other `UserDB` construction site identified by `TCR-02`.
- **depends_on:** `TCR-02`, `TCR-10`.
- **Agents:** **Auditor — no** (ruling already given). **Researcher — no.** **Planner — no.**
  **Validator — yes** — the chosen branch changes either a test contract or a model contract, and
  the other construction sites must be re-checked.
- **Risks — implementation:** a schema default is the smallest change and also the one most likely
  to hide a genuine missing-field bug. **rollout:** a model change requires an Alembic migration
  and is out of phase-09 minimal scope absent an explicit ruling. **regression:** any other
  `UserDB` construction site. **compatibility:** a schema default alters the OpenAPI contract.
- **Acceptance criteria:** `test_user_db_valid` passes; every construction site listed by `TCR-02`
  still passes; `ruff` and `mypy` pass; no assertion was weakened.
- **Commit shape:** `test(models): align UserDB.updated_at contract per TCR-02 ruling (TCR-14)`.

#### TCR-15 — Make `test_different_ips_have_separate_limits` non-vacuous
- **Findings closed:** `TST-006` (residual only).
- **Exact scope:** Strengthen one vacuous test. **Do not redo the landed fix** — the hard-coded
  `login:127.0.0.1` key is already gone and the tests already derive keys from production's own
  key-construction helper.
- **Semantic-unit targets:** `tests/test_rate_limiting.py::test_different_ips_have_separate_limits`
  — it currently exercises **one** IP, **one** key and a **single** over-limit assertion, so it
  cannot fail if per-IP separation broke.
- **Fix shape:** at least two distinct client identities, each with its own budget, asserting
  (a) identity A is not affected by identity B exhausting its budget, and (b) both share the same
  configured limit. Keys must be derived through the same production helper the landed fix
  introduced, not re-hardcoded.
- **depends_on:** `TCR-10`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — the
  point of the block is that the test must be able to fail; a Validator must confirm it fails when
  the separation is broken (mutation-style sanity check) and not merely that it passes.
- **Risks — implementation:** the test shares `tests/test_rate_limiting.py` with the landed
  `TST-006` fix — do not disturb that helper usage. **rollout:** test-only, fully revertible.
  **regression:** none. **compatibility:** none.
- **Acceptance criteria:** the test uses ≥2 identities; a deliberately broken per-IP key derivation
  makes it fail; it passes as written.
- **Commit shape:** `test(rate-limit): make per-IP separation test non-vacuous (TCR-15)`.

#### TCR-16 — Replace the seeder count assertion with an identity assertion
- **Findings closed:** `TST-016` (residual only).
- **Exact scope:** One assertion in one test. **Do not redo the landed fix** — the seeder now
  upserts instead of deleting, and a survival test already exists.
- **Semantic-unit targets:** the older seeder test that asserts `len(graphs) == 2` (a **count**,
  which stays blind to *which* implementation ran). Keep the existing survival test as-is.
- **Fix shape:** assert **identity** — the specific graph records the upsert path produced are
  present (stable identifiers / distinguishing field values), not merely that two rows exist.
  A count of 2 is satisfied identically by the old delete-and-reinsert behaviour, which is exactly
  what the assertion must now distinguish.
- **depends_on:** `TCR-10`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — must
  confirm the new assertion discriminates upsert from delete-and-reinsert.
- **Risks — implementation:** identifying a stable identity field requires reading the seeder's
  upsert key. **rollout:** test-only, fully revertible. **regression:** none. **compatibility:**
  none.
- **Acceptance criteria:** the assertion is on identity, not cardinality; it fails under
  delete-and-reinsert semantics; the existing survival test still passes.
- **Commit shape:** `test(seeder): assert graph identity instead of count (TCR-16)`.

#### TCR-17 — Correct the `async_db_session` docstring
- **Findings closed:** `TST-012` (honesty only).
- **Exact scope:** Make the fixture's docstring describe what it actually does. No behaviour change.
- **Semantic-unit targets:** the `async_db_session` fixture in `tests/conftest.py` — it opens a
  nested transaction and rolls it back, but `Session.commit()` commits the **root** transaction, so
  committed rows **survive** the test, with `expire_on_commit=False`. Its docstring still claims
  savepoint rollback.
- **Fix shape:** state the real semantics plainly and point at `TCR-04`/`TCR-25` as the pending fix.
  This is deliberately landed **before** `TCR-25` so the suite stops lying about itself while the
  shape decision is open.
- **depends_on:** `TCR-10`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — no** — a
  docstring correction with no behavioural delta needs no contract validation.
- **Risks — implementation:** none. **rollout:** docstring only, fully revertible. **regression:**
  none. **compatibility:** none.
- **Acceptance criteria:** the docstring no longer claims savepoint rollback and mentions the
  commit-survives-test behaviour; no executable line changes.
- **Commit shape:** `docs(tests): correct async_db_session rollback docstring (TCR-17)`.

#### TCR-18 — Consolidate the Redis store fixtures
- **Findings closed:** `TST-005`.
- **Exact scope:** Remove the dead store instance. **Do not** "fix" three dead instances — the
  verified state is **one** dead store instance with **two** live side effects. Keep both live side
  effects: the autouse Redis fixture's stub of `AuthService.check_rate_limit` and the
  `strict_redis` fixture's restoration of the original `__init__`.
- **Semantic-unit targets:** the three `MockRedis` instantiations in `tests/conftest.py` (only the
  dead **store** one is in scope); the autouse Redis fixture; the `strict_redis` fixture (it must
  keep restoring `__init__`); the store-reading test, which must keep reading the store the route
  actually wrote.
- **Hard constraint:** do **not** remove production code. If `TCR-06` shows the `AuthService`
  limiter instance is dead, that removal belongs to the **security phase**, not here.
- **depends_on:** `TCR-06`, `TCR-10`.
- **Agents:** **Researcher — no** (liveness settled in `TCR-06`). **Auditor — no.**
  **Planner — no.** **Validator — yes** — removing a mock that is silently load-bearing converts a
  red suite into a misleading green one; the fixture's live side effects must be re-verified.
- **Risks — implementation:** deleting the wrong instance breaks rate-limiter or auth tests in a
  way that looks like a product bug. **rollout:** test-only, fully revertible. **regression:** tests
  that depend on the autouse stub would fail loudly (good) or pass for the wrong reason (bad) —
  both require review. **compatibility:** none.
- **Acceptance criteria:** exactly one `MockRedis` store instantiation remains (or zero, if the dead
  one is removable outright); the autouse stub and the `strict_redis` restore are intact; the
  store-reading test still reads the route-written store; the full auth suite is green.
- **Commit shape:** `test(fixtures): remove dead Redis store instance (TCR-18)`.

---

### Wave D — Coverage and isolation infrastructure

#### TCR-19 — Cover the worker's compensating session branch
- **Findings closed:** `TST-007`.
- **Exact scope:** Add tests that exercise the `else:` (no injected session) branch of the three
  worker functions. Test-only **unless** `TCR-07` rules that a production seam is unavoidable — in
  which case this block stops and the seam goes to a fresh ruling.
- **Semantic-unit targets:** the worker module's three functions sharing the
  `if db_session is not None:` / `else:` shape; the worker module's own session factory (the
  session must come from **that** factory, not from the test fixture, or the branch is not really
  exercised); every current test call site, all of which pass a session.
- **depends_on:** `TCR-07`, `TCR-10`.
- **Agents:** **Researcher — no** (probe settled in `TCR-07`). **Auditor — no.** **Planner — no.**
  **Validator — yes** — a test that passes without actually entering the branch is worse than no
  test; the branch must be provably taken.
- **Risks — implementation:** a real session from the production factory inside a test can leak
  committed data into the suite — this block interacts with `TST-012`, so it must land **after**
  `TCR-25` or explicitly clean up. **rollout:** test-only, revertible. **regression:** could
  surface real defects in the previously-uncovered branch (that is the point, but it may add to the
  red count temporarily). **compatibility:** none.
- **Acceptance criteria:** all three functions' `else:` branches are executed (provable, e.g. by
  branch coverage, not by assertion alone); no data leaks past the test; no production change
  without a recorded ruling.
- **Commit shape:** `test(workers): cover no-session branch of worker session handling (TCR-19)`.

#### TCR-20 — Add an autouse config-cache reset
- **Findings closed:** `TST-013` (part 1).
- **Exact scope:** Add an autouse teardown fixture that resets the cached settings singleton.
  Introduce it **alongside** the existing manual calls; do not remove them here.
- **Semantic-unit targets:** the config module's cached `_settings` singleton and its
  `clear_config_cache()`; `tests/conftest.py` (new autouse fixture). Two test modules mutate **3**
  and **11** environment variables respectively; **20** modules sort after the mutating one, so the
  leak is order-dependent, not module-local.
- **depends_on:** `TCR-10`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — this
  changes what 20 downstream modules observe; it must be proven not to break any of them.
- **Risks — implementation:** resetting the singleton between tests can break tests that populate
  settings in `session`- or `module`-scoped setup. **rollout:** test-only, revertible, but its
  effect is suite-wide. **regression:** the dominant risk is a module-scoped fixture depending on
  a mutated setting surviving into the next test. **compatibility:** none.
- **Acceptance criteria:** the autouse reset exists; the full suite shows no new failure; the two
  mutating modules still pass **in any order**; `TCR-21` becomes safe.
- **Commit shape:** `test(fixtures): add autouse settings cache reset (TCR-20)`.

#### TCR-21 — Drop the manual `clear_config_cache()` call sites
- **Findings closed:** `TST-013` (part 2).
- **Exact scope:** Remove the now-redundant manual resets. Mechanical, same-class, one class of edit
  — grouped here precisely because it is only safe **after** `TCR-20`.
- **Semantic-unit targets:** the **13** files under `tests/` that call `clear_config_cache()` by
  hand (enumerate by search at execution time — do not hardcode a file list from this plan).
- **depends_on:** `TCR-20`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — each
  removal must be justified by the autouse fixture actually covering that case, not by assumption.
- **Risks — implementation:** a removal that assumed autouse coverage where the scope differs
  (e.g. a class-scoped fixture) re-introduces the leak silently. **rollout:** test-only,
  revertible. **regression:** order-dependent settings leaks returning. **compatibility:** none.
- **Acceptance criteria:** no manual call remains unless a comment states why the autouse fixture
  does not cover it; the suite passes in default order **and** under a shuffled/reversed order.
- **Commit shape:** `test(fixtures): remove manual settings cache resets (TCR-21)`.

#### TCR-22 — Introduce a real-session seam alongside `mock_db`
- **Findings closed:** `TST-009` (part 1).
- **Exact scope:** Add a fixture that yields a **real** `AsyncSession` bound with the same
  schema/transaction discipline as the other fixtures, while leaving `mock_db` in place. **No
  consumer is migrated in this block.**
- **Semantic-unit targets:** the `mock_db` fixture (`AsyncMock(spec=AsyncSession)`) in
  `tests/conftest.py`; the real-session construction path; the seam named by `TCR-05`.
- **Constraint:** the seam must be usable **without** `AsyncMock` anywhere in the chain — a seam that
  still permits the mock leaves the finding open.
- **depends_on:** `TCR-05`, `TCR-10`. Prefer landing **after** `TCR-25` so the seam inherits the
  correct transaction discipline rather than being built on the leaky one.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — a new
  fixture that nothing uses yet must at minimum be proven to work against one real consumer.
- **Risks — implementation:** the new fixture participates in the same commit-leak problem as
  `async_db_session`. **rollout:** test-only; **not independently revertible once consumers migrate**
  — see §7. **regression:** none while unused. **compatibility:** none.
- **Acceptance criteria:** the seam yields a session that really talks to the test database; a
  throwaway proof test using it passes; `mock_db` is unchanged and still used by all four consumers.
- **Commit shape:** `test(fixtures): add real-session seam alongside mock_db (TCR-22)`.

#### TCR-23 — Migrate the largest `mock_db` consumer
- **Findings closed:** `TST-009` (part 2).
- **Exact scope:** Move the user-service module (the consumer with **55** test functions) from
  `mock_db` to the real-session seam. One module only — this is the stop/go gate for the pattern.
- **Semantic-unit targets:** the user-service test module and its 55 test functions; every
  `mock_db`-shaped assumption in it (asserted calls, `AsyncMock` return values, `spec` reliance).
- **depends_on:** `TCR-22`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — 55
  tests changing observation surface is the single largest test-refactor in this phase; it needs a
  full-suite comparison before and after.
- **Risks — implementation:** some of the 55 may have been asserting mock interactions rather than
  behaviour; those assertions must be rewritten against real behaviour, not deleted. **rollout:**
  test-only but **not independently revertible in isolation** if the seam is kept — see §7.
  **regression:** real database semantics can surface genuine product defects that the mock hid;
  those are findings, not failures of this block, and must be recorded rather than mocked away.
  **compatibility:** none.
- **Acceptance criteria:** the module no longer imports or requests `mock_db`; all 55 tests pass
  against a real session; no assertion was deleted to accommodate the change; the full suite shows
  no new failure.
- **Commit shape:** `test(users): migrate user-service module from mock_db to real session
  (TCR-23)`.

#### TCR-24 — Migrate the remaining `mock_db` consumers
- **Findings closed:** `TST-009` (part 3).
- **Exact scope:** Move the remaining consumer modules to the real-session seam, one commit per
  module, following the pattern proven in `TCR-23`. Genuinely mechanical once the pattern exists.
- **Semantic-unit targets:** the remaining consumer modules identified by `TCR-05` (enumerated at
  execution time; the report's counts are stale and must not be trusted).
- **depends_on:** `TCR-23`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — one
  full-suite run per migrated module, not one run at the end.
- **Risks — implementation:** repeating `TCR-23`'s risk across each module. **rollout:** one commit
  per module keeps each independently revertible. **regression:** cumulative; a full run after each
  module is mandatory. **compatibility:** none.
- **Acceptance criteria:** `mock_db` has no remaining consumers in `tests/`, or its remaining use is
  justified in a comment; the full suite is green (or green modulo owner-blocked items) after every
  module commit.
- **Commit shape:** `test(tests): migrate <module> from mock_db to real session (TCR-24)` — one
  commit per module.

#### TCR-25 — Implement the ruled session-isolation shape
- **Findings closed:** `TST-012` (core).
- **Exact scope:** Implement exactly the shape ruled in `TCR-04` (option A, B, or C). If the ruling
  is C, this block is only the docstring follow-up and `TCR-26` is cancelled.
- **Semantic-unit targets:** the `async_db_session` fixture in `tests/conftest.py`;
  `Session.commit()` semantics against the nested/joined transaction; `expire_on_commit=False`;
  every test that currently depends on committed data surviving.
- **Ordering:** the **12** `delete(ProcessingLog)` compensating sites stay until this block lands.
- **depends_on:** `TCR-04`, `TCR-10`. Prefer landing **before** `TCR-22`…`TCR-24` so the new
  fixtures inherit correct semantics. If it must land later, the migrated modules are re-verified
  against it.
- **Agents:** **Researcher — no.** **Auditor — no** (ruling given). **Planner — no** (order given).
  **Validator — yes, mandatory and heavyweight** — this is the highest-risk block in the phase.
- **Risks — implementation:** option A changes what many currently-green tests observe; a wrong
  join strategy deadlocks or leaks connections. **rollout:** **not independently revertible** in the
  §7 sense — reverting restores a leaky fixture while consumers have been rewritten against the
  new semantics. **regression:** the dominant risk of the entire phase; requires ≥2 consecutive
  full runs and a shuffled-order run before it is trusted. **compatibility:** none external.
- **Acceptance criteria:** committed rows no longer survive a test (or, under option C, the ruling's
  stated scope is met); the fixture's docstring matches its behaviour with no pending-note
  reference; ≥2 consecutive full runs with identical results; a shuffled-order run adds no new
  failure; the 12 compensating sites still pass unchanged.
- **Commit shape:** `test(fixtures): isolate committed data per test in async_db_session (TCR-25)`.

#### TCR-26 — Remove the redundant compensating deletes — **conditional**
- **Findings closed:** `TST-012` (compensating surface).
- **Exact scope:** Remove the hand-rolled cleanup that exists only because committed rows survived.
  **Conditional on `TCR-25` having actually fixed the root cause** — if the ruling was C, this block
  is cancelled, not deferred silently.
- **Semantic-unit targets:** the **12** `delete(ProcessingLog)` call sites in the single test module
  that carries them (locate by search at execution time).
- **depends_on:** `TCR-25`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — the
  removal is the proof that the isolation fix works, not just tidying.
- **Risks — implementation:** removing a cleanup that is still needed leaks rows into other tests
  and produces spooky cross-test failures. **rollout:** test-only; revertible together with
  `TCR-25`. **regression:** leaks surfacing as unrelated failures elsewhere. **compatibility:**
  none.
- **Acceptance criteria:** the module passes with zero compensating deletes; the full suite is
  stable across ≥2 runs; no row-leak failure appears.
- **Commit shape:** `test(tests): drop compensating ProcessingLog deletes (TCR-26)`.

---

### Wave E — Coverage measurement correctness

#### TCR-27 — Make the backend coverage floor live and non-duplicated — **conditional on OD-6**
- **Findings closed:** `TST-003`.
- **Exact scope:** Resolve the inert `--cov-fail-under=65` and the duplicated floor. Two
  alternatives, **not** pre-selected:
  - **A — make it live on every test run:** add the missing `--cov=src/mkobi` to
    `[tool.pytest.ini_options] addopts` in `pyproject.toml` and drop the duplicated
    `fail_under = 65` from `[tool.coverage.report]`, leaving one source of truth.
  - **B — make it inert-by-design on `test`:** keep the floor exclusive to `Invoke-TestAll`
    (`--cov=src/mkobi --cov-report=term-missing`) and remove the misleading, non-functional
    `--cov-fail-under=65` from `addopts` so the config stops implying a gate that does not exist.
- **Hard constraint:** the two project documents disagree about whether a **65 %** floor is
  ruled live-and-unrelaxable or returned to open. **This block does not resolve that** — it is OD-6
  (§5). Under option A the real measured coverage must be known first, or the gate is red on
  arrival. Under option B nothing about the ruling is needed, only the removal of the dead flag.
- **Constraint:** `addopts` also registers the `slow` and `fast` markers while `--strict-markers` is
  on — do **not** touch them here; that is `TCR-30`.
- **depends_on:** OD-6 ruling; `TCR-10` (the measurement must see the working tree).
- **Agents:** **Researcher — no** (the real coverage number comes from `Invoke-TestAll`).
  **Auditor — no.** **Planner — no.** **Validator — yes** — the floor's pass/fail behaviour must be
  observed, and the single-source-of-truth property asserted.
- **Risks — implementation:** activating a floor that current coverage does not meet turns every
  backend run red. **rollout:** affects every backend invocation. **regression:** a newly live floor
  can be "fixed" by adding `--no-cov` somewhere — forbidden; the coverage gate is never to be
  bypassed to make a run pass. **compatibility:** `addopts` is read by every pytest entry point,
  including IDE runs.
- **Acceptance criteria:** the floor lives in exactly one place; the chosen option's behaviour is
  observed on a real run; no `--no-cov` / `--no-cov-fail-under` escape hatch is added anywhere.
- **Commit shape:** A — `chore(coverage): make the backend coverage floor effective (TCR-27)`.
  B — `chore(coverage): drop inert coverage flag from pytest addopts (TCR-27)`.

#### TCR-28 — Give the frontend coverage gate a real population
- **Findings closed:** `TST-004`.
- **Exact scope:** Add an explicit `include` / `exclude` (and `all` if the population warrants it) to
  the coverage block, and set thresholds from the measured baseline. **Do not** change thresholds to
  whatever makes the run green.
- **Semantic-unit targets:** the `test.coverage` block in `frontend/vite.config.ts` — v8 provider;
  `text` / `json` / `html` reporters; thresholds statements 50 / branches 40 / functions 45 /
  lines 50; the three absent keys. Population: `frontend/src`.
- **Known behaviour to design around:** a green single-file run today reports an **empty per-file
  table** and `Statements : 100% ( 9/9 )`; on a red run vitest prints **no coverage table and no
  threshold verdict at all** — so today the gate verifies nothing while the suite is red. Options:
  (a) accept the red-run blindness and document it, (b) split coverage into its own always-run step
  so the verdict is always produced, (c) reorder so coverage is evaluated independently of the
  suite's exit status. Present all three; recommend (b) or (c), because a gate that silently stops
  verifying is the defect being fixed.
- **Constraint:** threshold values are governed by **OD-6** alongside the backend floor, because
  fixing the population makes these thresholds live for the first time.
- **depends_on:** `TCR-08`, OD-6 ruling. Recommend landing **after** `TCR-29` so the coverage
  output directory is no longer tracked.
- **Agents:** **Researcher — no** (measurement in `TCR-08`). **Auditor — no.** **Planner — no.**
  **Validator — yes** — must confirm the per-file table is now populated and that a deliberate
  regression actually trips the threshold.
- **Risks — implementation:** adding `all: true` without a tight `include` can pull in generated or
  type-only files. **rollout:** the first reporting run rewrites `frontend/coverage/`.
  **regression:** newly live thresholds may be red on arrival — that is information, not a reason to
  lower them. **compatibility:** if the `json` / `html` reporters have no consumer, removing them is
  in scope only with that confirmed.
- **Acceptance criteria:** the per-file coverage table is non-empty; a deliberate uncovered line
  trips the corresponding threshold; the red-run verdict gap is either closed or explicitly
  documented with a chosen option.
- **Commit shape:** `chore(coverage): define frontend coverage population and thresholds (TCR-28)`.

---

### Wave F — Hygiene

#### TCR-29 — Untrack `frontend/coverage/`
- **Findings closed:** `TST-014`.
- **Exact scope:** Remove the coverage output from version control and ignore it correctly.
  Index-only removal — the files stay on disk.
- **Semantic-unit targets:** the **15** tracked files under `frontend/coverage/` (remove from the
  index, e.g. `git rm -r --cached frontend/coverage`); the root `.gitignore` (add the `coverage/`
  **directory** — it currently ignores `htmlcov/`, `.coverage`, `.coverage.*`, `coverage.xml`,
  `*.cover` and `cover/`, but **not** `coverage/`); `frontend/.gitignore` (exists; does not mention
  coverage — add there or in the root, not both, to keep one source of truth).
- **Corrected cause to preserve in the commit message:** a **failing** run writes nothing; a run
  that **emits a report** rewrites the directory (measured 4 modified + 6 deleted + 1 new). The
  gate dirties the worktree on every reporting run.
- **depends_on:** none (independent of every other block; recommend early so `TCR-28`'s first
  reporting run does not re-dirty the index).
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — no** — a
  mechanical VCS/config change with a directly checkable end state.
- **Risks — implementation:** `git rm --cached` leaves the files on disk (intended); a
  mis-scoped ignore pattern could hide real source. **rollout:** index change; the files stay
  untracked forever, which is the point. **regression:** none. **compatibility:** any tooling that
  expected `frontend/coverage/*.json` to be committed would break — verify no consumer.
- **Acceptance criteria:** `git status` stays clean across a coverage-reporting run; nothing under
  `frontend/coverage/` is tracked; the ignore entry covers the **directory**, not just files.
- **Commit shape:** `chore(gitignore): untrack frontend coverage output (TCR-29)`.

#### TCR-30 — Marker hygiene
- **Findings closed:** `TST-017`.
- **Exact scope:** Resolve the `slow` / `fast` markers — registered in
  `[tool.pytest.ini_options] addopts` under `--strict-markers`, with **0** tests using either, and
  `fast`'s description naming a `create_all()` schema-build path nothing in the test tree uses (the
  only `create_all` in the codebase is inside `init_db()`, which no test calls).
- **Options (not pre-selected):** (a) remove both registrations and their descriptions, since
  nothing uses them and the `fast` description is factually wrong; (b) keep the registrations and
  correct the descriptions to describe real behaviour; (c) start using the markers — **out of scope**,
  it would be speculative work. Recommend (a): with 0 usages and a wrong description, the markers are
  pure noise, and `--strict-markers` stays satisfied because no test references them.
- **depends_on:** none. Deliberately **not** bundled into `TCR-27` even though both touch `addopts`
  — different concern, different commit.
- **Agents:** **Researcher — no** (0 usages already verified repo-wide). **Auditor — no.**
  **Planner — no.** **Validator — yes** — `--strict-markers` must still pass, and the removal must be
  proven safe against the verified 0-usage fact.
- **Risks — implementation:** if any usage exists outside `tests/` and `src/` (e.g. a doctest
  configuration or an out-of-tree runner), `--strict-markers` will fail loudly — acceptable and
  informative. **rollout:** config-only, fully revertible. **regression:** none. **compatibility:**
  none.
- **Acceptance criteria:** no registered marker lacks at least one user, or every registered marker
  has an accurate description; the full suite collects **1410** items and `--strict-markers` passes.
- **Commit shape:** `chore(pytest): remove unused slow and fast markers (TCR-30)`.

#### TCR-31 — Make the enum-consistency module match its docstring
- **Findings closed:** `TST-018`.
- **Exact scope:** One of two things, per test: implement the promised two-way check, or correct the
  docstring. Not both by default — choose per case with the reason recorded.
- **Semantic-unit targets:** the enum-consistency test module (identified by its docstring promising
  the two-way check "after the DB-001 migration there should be zero extra values"); its four tests
  — the **processing-status** test (already two-way), and the **user-role**, **permission-level**
  and **aggregate** tests (all one-way), the last of which has its own docstring claiming the check
  it does not perform.
- **Constraint:** the two-way check requires an authoritative source list per enum. If that source
  is itself unsettled, the **docstring** is the correct fix — do not invent an authority.
- **depends_on:** none.
- **Agents:** **Researcher — no.** **Auditor — yes** — deciding whether a two-way check is
  *possible* for each enum needs the authoritative source identified, and that is a contract
  question. **Planner — no.** **Validator — yes** — a docstring promising a check must either be
  satisfied or removed; no middle state.
- **Risks — implementation:** a two-way check that is too strict will fail on legitimate values and
  block unrelated work. **rollout:** test-only, revertible. **regression:** a new two-way check can
  surface pre-existing enum drift as a red test. **compatibility:** none.
- **Acceptance criteria:** the module docstring's promise matches what the module does; each of the
  four tests is either genuinely two-way or explicitly documented as one-way with a reason.
- **Commit shape:** `test(enums): align enum consistency checks with documented intent (TCR-31)`.

---

### Wave G — Gate wiring (last)

#### TCR-32 — Make `Invoke-Check` report every leg
- **Findings closed:** `TST-002` (partial — the short-circuit only).
- **Exact scope:** Remove the first-failure-wins behaviour so all legs run and all failures are
  reported. **No new leg is added here** — that is `TCR-33`.
- **Semantic-unit targets:** `Makefile.ps1` → `Invoke-Check` and its three
  `if ($LASTEXITCODE -ne 0) { return }` guards; the leg functions it calls —
  `Invoke-Lint`, `Invoke-Typecheck`, `Invoke-FeLint`, `Invoke-FeTest` (unchanged behaviour, only
  the orchestration changes).
- **Motivation, stated precisely:** with the short-circuit, a red `lint` hides `typecheck`, `fe-lint`
  and `fe-test` entirely. This block exists so that the *next* block can wire a leg whose `fe-test`
  half is known-red without the aggregate becoming uninformative on arrival.
- **depends_on:** none; recommend landing **before** `TCR-33`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — the
  acceptance test is that a deliberately failing leg no longer prevents later legs from running.
- **Risks — implementation:** a `check` that runs everything is slower to first signal; a leg that
  was previously skipped may now surface a latent failure. **rollout:** affects every contributor's
  local gate. **regression:** surfacing latent failures is the intended effect, not a regression.
  **compatibility:** the script's exit code must remain non-zero when any leg fails.
- **Acceptance criteria:** all four existing legs execute even when an earlier one fails; all
  failures are reported; the final exit code is non-zero if any leg failed.
- **Commit shape:** `chore(harness): report all check legs instead of short-circuiting (TCR-32)`.

#### TCR-33 — Wire the backend suite into `Invoke-Check`
- **Findings closed:** `TST-002` (remainder).
- **Exact scope:** Add the backend test suite as a leg of `Invoke-Check`. **Landing this earlier
  would produce an aggregate that is red on arrival for a reason this phase does not own** — see the
  ordering constraints in §4.
- **Semantic-unit targets:** `Makefile.ps1` → `Invoke-Check` (add the `Invoke-Test` leg after
  `Invoke-Typecheck`, before the frontend legs) and `Invoke-Test` itself; the coverage decision from
  `TCR-27` determines whether this leg also carries the coverage floor.
- **Constraint — the frontend leg:** `Invoke-FeTest`'s single failure
  (`src/shared/types/__tests__/formSchemas.test.ts > changePasswordSchema > accepts matching
  passwords`) **cannot be fixed in this phase** (OD-2, `DP-13-H`). It is a documented, owner-known
  red, **not** a blocker for this block, and **must not** be made green here. If the wiring makes the
  aggregate exit non-zero for that reason, the aggregate must report it as a known, attributed
  failure — which is exactly what `TCR-32`'s all-legs reporting enables.
- **depends_on:** `TCR-32`; `TCR-11`, `TCR-12`, `TCR-13`, `TCR-14` (the four red-test repairs);
  `TCR-25` (session isolation — an unstable failure count cannot certify a green gate);
  `TCR-27` (so the leg's coverage scope is settled); and the two-consecutive-green-runs evidence in
  §4.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — the
  gate is the phase's deliverable; it must be observed green on the backend legs across ≥2
  consecutive full runs and the frontend failure must be shown as attributed, not hidden.
- **Risks — implementation:** a green gate introduced while the suite is unstable is a gate that
  gets disabled — the report's own principle. **rollout:** every contributor's local gate changes.
  **regression:** the wired leg exposes the full ~8-minute backend suite to every `check`.
  **compatibility:** `Invoke-Test` semantics must not change; only the orchestration does.
- **Acceptance criteria:** `Invoke-Check` runs the backend suite; two consecutive full runs produce
  identical results; the frontend failure is reported and attributed to phase 13 `CT-2`; the exit
  code semantics are documented on the aggregate.
- **Commit shape:** `chore(harness): run the backend suite as part of check (TCR-33)`.

#### TCR-34 — Create the CI workflow — **conditional on OD-4**
- **Findings closed:** `TST-002` (CI half).
- **Exact scope:** Only if `TCR-09` returns *now*. A GitHub Actions workflow that calls the
  `.\Makefile.ps1` targets rather than re-implementing them, so local and CI behaviour cannot drift.
  **Do not execute without the ruling.**
- **Semantic-unit targets:** a new `.github/workflows/` entry (no CI configuration exists today: no
  `.github/`, `.gitlab-ci.yml`, `.circleci/`, `azure-pipelines.yml`, `Jenkinsfile`, `.husky/`,
  `.pre-commit-config.yaml`, `tox.ini`, `noxfile.py`, `.git/hooks/pre-commit`); the
  `.\Makefile.ps1` targets it invokes — `test-up`, `test`, `test-down`, `lint`, `typecheck`,
  `fe-install`, `fe-lint`, `fe-test`.
- **depends_on:** `TCR-09` (ruling) **and** `TCR-33`.
- **Agents:** **Researcher — no.** **Auditor — no.** **Planner — no.** **Validator — yes** — a
  required check that is red on arrival blocks merges; its first run must be observed and the
  branch-protection consequence confirmed acceptable.
- **Risks — implementation:** duplicating command logic in YAML instead of calling
  `Makefile.ps1` guarantees drift. **rollout:** a red required check blocks merges immediately —
  the main reason this block is conditional. **regression:** none. **compatibility:** the workflow
  must run on the `feat/react` branch of the GitHub remote with the same Docker-based test path as
  local, not a bare `pytest`.
- **Acceptance criteria:** the workflow invokes only `.\Makefile.ps1` targets; its first run's result
  is recorded; branch-protection impact is stated.
- **Commit shape:** `ci(tests): add GitHub Actions workflow delegating to Makefile.ps1 (TCR-34)`.

---

## 4. Dependency graph and sequence

### 4.1 Ordered execution list

| # | block | title | depends_on |
|---|---|---|---|
| 1 | `TCR-01` | Measure `test-app` worktree visibility, decide harness option | — |
| 2 | `TCR-02` | Adjudicate the `UserDB.updated_at` contract | — |
| 3 | `TCR-03` | Ruling packet: duplicate-layout status code | — |
| 4 | `TCR-04` | Adjudicate the session-isolation shape | — |
| 5 | `TCR-05` | Map `mock_db` consumers, define the real-session seam | — |
| 6 | `TCR-06` | Verify `AuthService` limiter liveness | — |
| 7 | `TCR-07` | Probe worker-session testability | — |
| 8 | `TCR-08` | Measure frontend coverage population + baseline | — |
| 9 | `TCR-09` | CI workflow ruling | — |
| 10 | `TCR-10` | Make the backend test target measure the working tree | `TCR-01` |
| 11 | `TCR-11` | Rate-limiter tuple destructuring | `TCR-10` |
| 12 | `TCR-12` | RFC 7807 shape assertions (2 tests) | `TCR-10` |
| 13 | `TCR-13` | Apply the duplicate-status ruling *(conditional)* | `TCR-03`, `TCR-10` |
| 14 | `TCR-14` | Apply the `updated_at` ruling | `TCR-02`, `TCR-10` |
| 15 | `TCR-15` | Make the per-IP separation test non-vacuous | `TCR-10` |
| 16 | `TCR-16` | Seeder identity assertion | `TCR-10` |
| 17 | `TCR-17` | Correct the `async_db_session` docstring | `TCR-10` |
| 18 | `TCR-18` | Consolidate the Redis store fixtures | `TCR-06`, `TCR-10` |
| 19 | `TCR-19` | Cover the worker no-session branch | `TCR-07`, `TCR-10` |
| 20 | `TCR-20` | Autouse settings-cache reset | `TCR-10` |
| 21 | `TCR-21` | Drop manual `clear_config_cache()` sites | `TCR-20` |
| 22 | `TCR-25` | Implement the ruled session-isolation shape | `TCR-04`, `TCR-10` |
| 23 | `TCR-26` | Remove compensating `ProcessingLog` deletes *(conditional)* | `TCR-25` |
| 24 | `TCR-22` | Add the real-session seam alongside `mock_db` | `TCR-05`, `TCR-10`, `TCR-25` |
| 25 | `TCR-23` | Migrate the 55-test `mock_db` consumer | `TCR-22` |
| 26 | `TCR-24` | Migrate the remaining `mock_db` consumers | `TCR-23` |
| 27 | `TCR-27` | Backend coverage floor *(conditional on OD-6)* | `TCR-10`, OD-6 |
| 28 | `TCR-29` | Untrack `frontend/coverage/` | — |
| 29 | `TCR-28` | Frontend coverage population + thresholds | `TCR-08`, `TCR-29`, OD-6 |
| 30 | `TCR-30` | Marker hygiene | — |
| 31 | `TCR-31` | Enum-consistency docstring vs checks | — |
| 32 | `TCR-32` | `Invoke-Check` reports all legs | — |
| 33 | `TCR-33` | Wire the backend suite into `Invoke-Check` | `TCR-11`…`TCR-14`, `TCR-25`, `TCR-27`, `TCR-32`, two-green-runs |
| 34 | `TCR-34` | CI workflow *(conditional on OD-4)* | `TCR-09`, `TCR-33` |

### 4.2 Dependency edges

```
TCR-01 ──► TCR-10 ──┬──► TCR-11 ──┐
                     ├──► TCR-12 ──┤
TCR-03 ─────────────┼──► TCR-13 ──┤
TCR-02 ─────────────┼──► TCR-14 ──┤
                     ├──► TCR-15 ──┤
                     ├──► TCR-16 ──┤
                     ├──► TCR-17    │
TCR-06 ──────────────┼──► TCR-18    │
TCR-07 ──────────────┼──► TCR-19    ├──► TCR-33
TCR-20 ──► TCR-21    │             │
TCR-04 ──► TCR-25 ───┼──► TCR-26    │
              │      ├──► TCR-22 ──► TCR-23 ──► TCR-24
              └──────┘
TCR-05 ──────────────┼──► TCR-22
TCR-08 ──────────────┼──► TCR-28
TCR-29 ──────────────┴──► TCR-28
OD-6 ─────────────────────► TCR-27, TCR-28
TCR-32 ────────────────────► TCR-33
TCR-09 ────────────────────► TCR-34 ◄── TCR-33
```

**Freely parallel (no shared files, no ordering requirement):** all of Wave A; `TCR-29`, `TCR-30`,
`TCR-31`; `TCR-11`…`TCR-18` (they touch different test modules — `TCR-11` `tests/test_auth.py`,
`TCR-12` `tests/test_layouts.py`, `TCR-15` `tests/test_rate_limiting.py`, `TCR-18`
`tests/conftest.py`; `TCR-11` and `TCR-18` both concern rate limiting but touch different files and
should still be committed separately to avoid merge friction).

### 4.3 Justification against the six ordering constraints

1. **Green before gate.** The report's own principle: *a gate introduced before the suite is green
   is a gate that gets disabled.* Honoured structurally — `TCR-33` (the gate) is block 33 of 34 and
   depends on the four red-test repairs **and** on `TCR-25`, because an unstable failure count
   cannot certify a green gate. `TCR-27` and `TCR-28` also land before it, so the gate's coverage
   scope is decided before it is wired rather than after.
2. **`TST-001` first.** `TCR-10` is block 10, immediately after the measurement that decides its
   shape, and **every** implementation block depends on it. Until the gate measures the working
   tree, `tests/test_config.py` in the image is 1338 lines while the host has 1124 — so a host-side
   test edit is invisible and the run looks identical. **This makes every other block's verification
   evidence unreliable**, which is why nothing else is allowed to start first.
3. **The frontend suite cannot go green in this phase** (ruled `DP-13-H`; owner = phase 13 `CT-2`).
   The exit criterion is therefore **backend-only green**, and the single frontend failure is
   documented as owned elsewhere — neither treated as a blocker nor "fixed" here. See §6 for the
   ordering trap that makes fixing it here actively harmful.
4. **Gate wiring goes last, not second.** `Invoke-Check`'s `fe-test` leg can never be green in this
   phase, so wiring the backend suite mid-program yields an aggregate that is red on arrival for a
   reason this phase does not own. The plan also anticipates that the fix is not merely "append
   `Invoke-Test`": `TCR-32` removes the three `if ($LASTEXITCODE -ne 0) { return }` guards first so
   all legs run and all failures are reported, which is what makes a knowingly-red `fe-test`
   informative rather than opaque.
5. **Session-isolation work precedes gate wiring.** `TCR-25` (block 22) is a hard dependency of
   `TCR-33` (block 33). The backend failure count is unstable — the audit measured 10, 11 and 12 on
   identical code across three runs, and today it is 9 — and two tests
   (`tests/test_users_api.py::TestDeleteAccount::test_admin_cannot_delete_self`,
   `tests/test_e2e_upload.py::…::test_e2e_multiple_graphs_same_dashboard`) are order-dependent.
6. **"Exit 0" must be demonstrated on more than one run.** No gate is declared green on a single
   green run. Required evidence: **two consecutive full backend runs with identical results**, plus a
   shuffled-order run after `TCR-25` and `TCR-20`.

### 4.4 Real exit criterion for the programme

The phase is complete when **all** of the following hold:

1. `.\Makefile.ps1 test` exits 0 — **on two consecutive runs with identical results** — and
   `collected 1410 items` with no failures beyond a documented, owner-attributed list.
2. The four red-test repairs are landed: `TST-010` (5 tests), `TST-011` (3 tests, subject to
   `TCR-13`'s ruling), and `test_user_db_valid`.
3. `TST-001` is proven closed by a **sentinel edit**, not by a passing run.
4. `.\Makefile.ps1 lint` and `.\Makefile.ps1 typecheck` exit 0.
5. The coverage decision is **recorded** (OD-6), and `TST-003` / `TST-004` are either implemented or
   explicitly deferred with the deferral written down.
6. `.\Makefile.ps1 check` reports **all** legs and its backend leg is green. Its `fe-test` leg is
   **red and attributed** to phase 13 `CT-2` — this is an accepted end state for phase 09, not a
   failure of it.
7. `.\Makefile.ps1 fe-test` shows `1 failed | 170 passed (171)` with the single failure being
   `changePasswordSchema > accepts matching passwords` — unchanged, unweakened, and owned elsewhere.
8. No block executed a weakened assertion, skip or marker; no coverage gate was bypassed with
   `--no-cov`; nothing under `.ai/audit/**` or another phase's plan was modified.

**Not** an exit criterion: the frontend suite exiting 0; a CI workflow existing; a stable total
failure count equal to today's 9 before the four repairs land.

---

## 5. Open decisions for the Product Owner

### OD-1 — `test-app` harness: bind mount vs `--build` vs hybrid
- **Options:** **A** bind-mount `src/` + `tests/` into `test-app`; **B** add `--build` to every test
  target; **C** hybrid — bind mount locally, `--build` as the hermetic CI fallback.
- **Recommendation:** **B first, C as the target state.** B is unconditionally correct, cheap to
  reason about, and removes the silent-divergence failure mode immediately. A is faster and is the
  better end state, but a sibling plan records an observed `Errno 13` on write inside the container
  and declares it infeasible *as written*; that is a **measurement to reproduce**, not a settled
  verdict (uid mismatch, Windows Docker Desktop bind semantics, and a read-only default mount are
  all candidate causes).
- **Blast radius:** `Makefile.ps1` test targets and `docker/docker-compose.test.yml` service
  `test-app`. Touches every backend verification in the project.
- **No ruling:** `TCR-10` cannot start and **the entire phase is blocked** — nothing else can be
  trusted. This is the single most decisive item on the list.
- **Owner:** measurement by a **Researcher** (`TCR-01`) — cheap and decisive; the choice between B
  and C is a maintainability call the Planner has made advisory above.

### OD-2 — Client/server password-policy divergence (`TST-015`)
- **Status: already ruled** by `DP-13-H` (2026-10-03): the **server is authoritative**, the client
  mirrors it, and the uppercase rule is dropped **from the client**, **not** added to the server.
  Listed here only because the plan's exit criterion depends on it.
- **Consequence for this phase:** the frontend suite **cannot** exit 0 during phase 09, and the
  `changePasswordSchema` test **must not** be edited here.
- **Blast radius:** none in this phase.
- **Owner of the change:** phase 13 block `CT-2`, which edits the production client schema.
- **This item must not be re-opened.** It is listed because the audit report does not record the
  ruling, so a later agent reading only the report would see an apparently open MEDIUM finding.

### OD-3 — Duplicate-layout status code: 409 or 422
- **Options:** **A — 409** via the existing `DUPLICATE_RESOURCE` code (already mapped to 409 in
  `_ERROR_CODE_STATUS_MAP` and already used **three times** in this codebase for the same class of
  condition; two in-flight sibling tasks already resolve "duplicate ⇒ conflict"); **B — 422** as
  coded today (`AppException(code=ErrorCode.VALIDATION_ERROR, …)` in the duplicate-name `ValueError`
  handler).
- **Recommendation:** **A — 409.** A duplicate is a conflict, not a validation failure, and the
  codebase already says so three times. Advisory only; this is an API contract decision.
- **Blast radius:** an **API contract change**. The route, the OpenAPI/error documentation
  (`docs/08-security/error-format.md`, `docs/99-reference/error-handling-guide.md`), the frontend
  error-extraction chain in `frontend/src/shared/api/errorHandler.ts`, and any client keying on 422
  for this route.
- **No ruling:** `TCR-13` does not execute; `test_create_layout_duplicate_name_returns_400` **stays
  red** and is recorded as owner-blocked. It is **explicitly forbidden** to make it green by
  weakening the assertion or by conforming to the sibling plan's incorrect 400 pin.
- **Owner:** **Product Owner**, on the `TCR-03` packet.

### OD-4 — Create a CI workflow now, or defer
- **Options:** **A — create now**, accepting a red first run; **B — defer** until the backend suite
  is stably green and the frontend failure is resolved by phase 13.
- **Recommendation:** **B — defer.** A required check that is red on arrival blocks merges for a
  reason this phase does not own. When it is created, it must call `.\Makefile.ps1` targets rather
  than re-implementing them, so local and CI behaviour cannot drift.
- **Blast radius:** branch protection and every contributor's merge path. No CI configuration exists
  today at all — no `.github/`, `.gitlab-ci.yml`, `.circleci/`, `azure-pipelines.yml`, `Jenkinsfile`,
  `.husky/`, `.pre-commit-config.yaml`, `tox.ini`, `noxfile.py`, `.git/hooks/pre-commit`.
- **No ruling:** `TCR-34` does not execute; `TST-002`'s CI half remains open and recorded.
- **Owner:** **Product Owner**. Note: this plan may not cite the owner-rulings file for rulings it
  marks as open-by-design, so an absent entry here is itself the record.

### OD-5 — Session-isolation shape
- **Options:** **A** — join an external transaction (SQLAlchemy recipe; makes `Session.commit()`
  nest; **whole-suite blast radius**); **B** — explicit per-module truncation (more code, more lock
  contention, contained per module); **C** — correct the misleading docstring only, defer the rest.
- **Recommendation:** **A, executed module-by-module in a fixed order, with C done first**
  (`TCR-17`) so the suite stops lying about its own semantics while the decision is open. A is the
  only shape that removes the root cause; B is the fallback if A destabilises the suite; C alone
  leaves committed rows surviving and the 12 compensating `delete(ProcessingLog)` sites in place.
- **Blast radius:** every test that currently depends on committed data surviving its test. The
  highest-risk change in the phase, and **not independently revertible** once consumers are
  rewritten against the new semantics (§7).
- **No ruling:** `TCR-25` does not execute; `TST-012` remains open with only the docstring corrected,
  which is an honest but incomplete outcome.
- **Owner:** **Auditor** for the blast-radius map, **Planner** for the per-module order, then
  **Product Owner** if a production change is implied.

### OD-6 — Is the 65 % backend coverage floor ruled live-and-unrelaxable, or returned to open?
- **The contradiction:** two project documents disagree about whether the **65 %** floor is a live,
  unrelaxable ruling or has been returned to open. This plan does not resolve it.
- **Options:** **A — live and unrelaxable:** add the missing `--cov=src/mkobi` to `addopts` so the
  floor is enforced on every run, after measuring the real coverage (which may be red on arrival);
  **B — returned to open:** remove the inert `--cov-fail-under=65` from `addopts` so the config stops
  implying a gate that does not exist, and keep enforcement exclusive to `Invoke-TestAll`.
- **Recommendation:** resolve the contradiction first, then prefer **A with a measured baseline** —
  a floor that only runs on one target is a floor that is routinely bypassed. If real coverage is
  below 65 %, report the gap; **do not lower the floor to make it pass.**
- **Blast radius:** every pytest entry point, including IDE runs, because `addopts` is read
  everywhere. Also governs `TCR-28`'s frontend thresholds (50/40/45/50), which become live for the
  first time once the measured population is fixed.
- **No ruling:** `TCR-27` does not execute and `TST-003` stays open. `TCR-28` may still fix the
  `include`/`exclude` population, but its threshold values then remain provisional.
- **Owner:** **Product Owner**, or a **Validator** if the contradiction is purely documentary.

### OD-7 — `UserDB.updated_at`: test payload, schema default, or model change
- **Options:** **A** — supply `updated_at` in the test payload (smallest, test-only, keeps the
  contract strict); **B** — give the Pydantic schema a default (smallest production change, but hides
  a genuinely missing field from every caller and alters the OpenAPI contract); **C** — relax the DB
  model (largest; requires an Alembic migration and weakens a DB-level invariant).
- **Recommendation:** **A.** The test payload is what is incomplete; production code is the source
  of truth and the SQLAlchemy model already declares `updated_at` as a required `datetime`.
- **Blast radius:** every `UserDB` construction site in `src/` and `tests/`; under **B** or **C**,
  the OpenAPI contract and possibly the database schema.
- **No ruling:** `test_user_db_valid` stays red and is recorded as owner-blocked. Supplying
  `updated_at` in the payload is *not* a default action for an Implementor — the Auditor must
  confirm the owning layer first.
- **Owner:** **Auditor** (contract adjudication), escalating to the Product Owner only if the
  schema's OpenAPI contract would change.

---

## 6. Explicitly out of scope

| Item | Owner | Why it is out of phase 09 |
|---|---|---|
| **`TST-015` — client/server password-policy divergence** | phase 13 block `CT-2` (production client schema) | Ruled by `DP-13-H` (2026-10-03): the **server is authoritative**, the client mirrors it, the uppercase rule is dropped **from the client** and **not** added to the server. |
| **`TST-010`'s rate-limiter fail-open default** (`fail_closed: bool = False` on `RateLimiter` / `AsyncRateLimiter`) | security phase `SEC-003` | `TCR-11` repairs only *how* the returned tuple is read. The two `*_fail_open_*` / `*_fail_closed_*` tests assert the current default as intended behaviour and **must keep asserting it**. Changing the default is another phase's change. |
| **All 12 `VAL-09-001`…`VAL-09-012`** | closed-no-action | They are defects **in the audit document** — bad counts, two wrong cross-references, three mis-attributed causes, one template-contract breach, one namespace collision. **None requires a repository change.** Phase 09 may not edit `.ai/audit/**`. Recorded here so they are not mistaken for open work. |
| **Real-DB-dependency work gated by `TST-008`** | transaction phase | The HTTP fixture still overrides the DB dependency and uses an in-process ASGI transport, but other phases have since added direct commit-ownership tests that do not depend on that override, so the sibling finding this gated is **partially covered by another route**. `TCR-22`…`TCR-24` improve the seam but do not restructure the HTTP fixture. |
| **Worker-session coverage as a cross-phase gate** | topology phase | `TCR-19` closes `TST-007`'s branch coverage, but the *remediation it gates* — stale-log handling — belongs to the topology phase. |
| **Production dead code in `AuthService.__init__`** | security phase | If `TCR-06` shows the limiter instance is constructed and never called, its removal is a production change owned by the security phase. `TCR-18` removes only the dead **test** store instance. |
| **The sibling code-quality plan's `400` pin** | code-quality phase | It pins `test_create_layout_duplicate_name_returns_400` as "the `ValueError` → `400` path" in a table whose preamble forbids weakening any pin. **That pin is factually wrong against the code** — the route emits **422**. Phase 09 **must not edit that plan, must not conform to it, and must not preserve a 400 the route never emits.** The contradiction is escalated via `TCR-03`, not silently absorbed. |
| **A green frontend suite** | phase 13 `CT-2` | Ruled by `DP-13-H`. The phase-09 exit criterion is backend-only green (§4.4). |
| **The stale `.ai/context/commands.md`** | documentation owner | `.kilo/rules/commands.md` is authoritative and correct. The risk is contained because every verification command in §8 comes from the authoritative file. Correcting the stale file is a doc-accuracy task outside phase-09 scope; noted so no agent trusts it. |

### ⚠️ Ordering trap — warning to every later agent

**Phase 09 owns the test. Phase 13 owns the production schema. If phase 09 "fixes"
`src/shared/types/__tests__/formSchemas.test.ts > changePasswordSchema > accepts matching
passwords` first, it goes green for the wrong reason and then breaks when `CT-2` lands.**

The test fails because the payload `'newpassword123'` satisfies the **server's** password rule and
fails the **client's**, which additionally demands an uppercase letter. The correct fix is to make
the client match the server. Editing the test to accept a weak password would encode the divergence
into the test suite, and the eventual `CT-2` change would then contradict it.

**Do not edit that test file in phase 09. Do not add the uppercase rule to the server. Do not treat
the red frontend suite as a phase-09 blocker.** Backend-only green is the exit criterion.

---

## 7. Risks and rollback

### 7.1 Per-block revertibility

| block | revertibility | notes |
|---|---|---|
| `TCR-01`, `TCR-02`…`TCR-09` | n/a | read-only; no repository change |
| `TCR-10` | **single commit, revertible in principle — but NOT independently revertible in practice** | see 7.2 |
| `TCR-11`, `TCR-12`, `TCR-15`, `TCR-16`, `TCR-17` | single commit, cleanly revertible | test-only, contained modules |
| `TCR-13` | single commit, revertible | 422 branch test-only; **409 branch is an API contract change** — reverting restores the old status, which is a client-visible behaviour change |
| `TCR-14` | single commit, revertible | unless the Auditor rules a model change, which brings an Alembic migration |
| `TCR-18` | single commit, revertible | test-only, but removing a load-bearing mock converts red into misleadingly green |
| `TCR-19` | single commit, revertible | test-only, unless `TCR-07` rules a production seam is required |
| `TCR-20` | single commit, revertible in principle — **suite-wide effect** | may break module-scoped fixtures downstream |
| `TCR-21` | single commit, cleanly revertible | mechanical, only safe after `TCR-20` |
| `TCR-22` | single commit, revertible while unused | **not independently revertible once `TCR-23`/`TCR-24` land** — see 7.2 |
| `TCR-23`, `TCR-24` | one commit per module, individually revertible | 55 tests in `TCR-23`; revert restores `mock_db` for that module only |
| `TCR-25` | **NOT independently revertible** | see 7.2 |
| `TCR-26` | single commit, revertible **only together with `TCR-25`** | the compensations are required again if the isolation fix is reverted |
| `TCR-27`, `TCR-28` | single commit, revertible | config-only, but affects every invocation |
| `TCR-29` | single commit, revertible | index-only removal; re-adding 15 files is mechanical |
| `TCR-30`, `TCR-31` | single commit, cleanly revertible | contained |
| `TCR-32`, `TCR-33` | single commit each, revertible | gate orchestration only; no test semantics change |
| `TCR-34` | single commit, revertible | CI only |

### 7.2 Blocks that are NOT independently revertible

**1 — `TCR-10`, the harness-level change.** Reverting restores a gate that silently measures a baked
image, and **every subsequent verification claim in the repository becomes suspect** — the revert is
not a local regression, it invalidates the evidence base of all other work. Because 191 of 192
`src/`/`tests/` files are currently byte-identical between image and host, the failure is
**undetectable from a run**: it looks identical either way.
- **Must be verified before moving on:** a sentinel edit to a `tests/` file is observed by
  `Invoke-Test` in the same invocation; `Invoke-TestAll` and `Invoke-TestSelect` behave identically;
  `test-db` / `test-redis` healthchecks pass; the suite still collects **1410** items; `dev` and
  `prod` Dockerfile stages still end `USER app` unchanged.

**2 — `TCR-22` + `TCR-25`, the session-fixture changes.** These alter **what many currently-green
tests observe**. `TCR-25` changes the meaning of `Session.commit()` inside the test suite;
`TCR-22` introduces a seam that consumers are then rewritten against. Reverting `TCR-22` after
`TCR-23`/`TCR-24` would break those migrated modules; reverting `TCR-25` restores a leaky fixture
while `TCR-26`'s compensating deletes have already been removed.
- **Must be verified before moving on:** two consecutive full runs with identical results; a
  shuffled-order run adding no new failure; the 20 modules that sort after the settings-mutating one
  verified specifically; committed rows confirmed not to survive a test; every module migrated in
  `TCR-23`/`TCR-24` re-verified against the final isolation semantics.

### 7.3 Programme-level risks

- **The phase is blocked behind one cheap measurement.** If `TCR-01` is skipped, or its verdict is
  assumed, every other block's verification is untrustworthy and the whole programme's evidence is
  void. This is the highest-leverage item in the plan.
- **Gate adoption risk.** A gate that fails intermittently will be bypassed, not fixed. Hence
  constraint 6 (§4.3): no gate is declared green on one run.
- **Scope creep into redesign.** `TCR-19` and `TCR-22` both have a plausible production-seam branch.
  Both stop and escalate rather than proceeding — production changes are out of phase-09 scope
  except under `TCR-13`'s explicit ruling.
- **Stale-report risk.** The report is 113 commits old; its counts, severities and line numbers have
  moved. Every count in this plan was re-verified at `f1606f0`; anything not re-verified is either
  marked `—` (severity) or explicitly described as "enumerate at execution time" (file lists).
  **No Implementor may quote a line number or a count from the report.**
- **Documentation.** No separate documentation block is created. This plan file, the `TCR-*` block
  comments, and the commit messages of `TCR-29` and `TCR-30` are the record. Creating docs in
  `.ai/audit/**` is forbidden, and adding a parallel doc elsewhere would be noise that the next
  agent must reconcile — the opposite of the goal.

---

## 8. Verification protocol

### 8.1 The image-parity rule (applies to every backend block)

> **`.\Makefile.ps1 test` must NOT be reported as evidence of a test-side change unless `test-app`
> was rebuilt — or the working tree was mounted — in the same change.**

The backend suite measures a **baked image**: `docker/docker-compose.test.yml`'s `test-app` has no
`volumes:` key, and `docker/Dockerfile`'s `test` stage copies `src/` and `tests/` in and then ends
`USER app` before `CMD ["pytest", "tests/", "-v"]`. The string `--build` appears **nowhere** in
`Makefile.ps1`. Proven: 191 of 192 `src/`+`tests/` files are byte-identical between image and host,
but **`tests/test_config.py` differs** (image 1338 lines, host 1124). A host-side test edit is
invisible to the gate until the image is rebuilt, **and the run looks identical either way**.

**Protocol per backend block:**

1. Apply the block's change on the host.
2. Rebuild `test-app` — or confirm the `TCR-10` mount makes the change visible. The exact mechanism
   is `TCR-01`'s output; `TCR-10` lands it.
3. Prove visibility with a **sentinel**: a deliberately failing assertion must appear in the run. If
   it does not, the harness is still blind and the block's evidence is void.
4. Run the subset, then the full suite per §8.2.
5. Record in the commit message which mechanism was used.

**Corollary:** a block that reports "all tests pass" without step 3 has proved nothing.

### 8.2 Commands

`.kilo/rules/commands.md` is authoritative. `.ai/context/commands.md` is stale — do not use it.
Windows 11 · PowerShell 7+ · `.\Makefile.ps1` is the canonical entry point. Never pass
`--project-directory`. Never run `uv run pytest` locally — there is no test database on `localhost`.

**Per-block subsets (seconds to ~1 min) — the primary evidence for a single test change:**

```powershell
# TST-010 (TCR-11) — five tests
.\Makefile.ps1 test-select -k "TestRateLimiting" -q

# TST-011 (TCR-12 / TCR-13)
.\Makefile.ps1 test-select -k "TestLayoutsAPI" -q

# UserDB.updated_at (TCR-14)
.\Makefile.ps1 test-select -k "TestUserModels" -q

# TST-006 residual (TCR-15)
.\Makefile.ps1 test-select -k "test_different_ips_have_separate_limits" -q

# TST-005 (TCR-18) — fixtures, exercise the whole auth surface
.\Makefile.ps1 test-select -k "auth" -q

# TST-007 (TCR-19)
.\Makefile.ps1 test-select -k "worker" -q

# TST-009 (TCR-23 / TCR-24) — per module, one full-suite run after each
.\Makefile.ps1 test-select -k "users" -q

# TST-012 (TCR-25 / TCR-26)
.\Makefile.ps1 test-select -k "ProcessingLog" -q

# TST-013 (TCR-20 / TCR-21) — cross-module, needs the FULL suite
.\Makefile.ps1 test
```

**Per-block quality gates (any block touching Python):**

```powershell
uv run ruff check src/ tests/          # ~20 s
uv run mypy src/                       # ~60 s
```

Use `uv run ruff check --fix <path>` to auto-fix including import sorting (`I001`).
`ruff format` only reformats and does **not** sort imports.

**Full-suite evidence (≈8 min) — required at these checkpoints:**

```powershell
.\Makefile.ps1 test        # full backend suite, no coverage
.\Makefile.ps1 test-all    # full backend suite + --cov=src/mkobi --cov-report=term-missing
```

- After `TCR-10` (harness proof).
- After each of `TCR-11`…`TCR-14` (the four red-test repairs).
- After `TCR-20` and `TCR-21` (settings cache — order-dependent across 20 modules).
- After `TCR-23` and after **each** module commit in `TCR-24`.
- After `TCR-25` and `TCR-26` — **twice, consecutively, with identical results** (§4.3 constraint 6).
- Before `TCR-33` is declared green.

**Order-dependence check — required once `TCR-25` and `TCR-20` land:**

```powershell
.\Makefile.ps1 test-select -k "test_admin_cannot_delete_self or test_e2e_multiple_graphs_same_dashboard" -q
.\Makefile.ps1 test-select -p no:randomly -q     # if a random-order plugin is present
```

Both of these tests pass today but are **order-dependent**; they are the first canary for a
regression in isolation.

**Frontend (host-native; requires `.\Makefile.ps1 fe-install` once):**

```powershell
.\Makefile.ps1 fe-test    # ~15 s
.\Makefile.ps1 fe-lint
```

Expected result for the whole of phase 09: `Tests 1 failed | 170 passed (171)`,
`Test Files 1 failed | 12 passed (13)` — the single failure being
`src/shared/types/__tests__/formSchemas.test.ts > changePasswordSchema > accepts matching passwords`
with `AssertionError: expected false to be true`. **This is the expected end state of the phase.**
It is owned by phase 13 `CT-2`, it is **not** a phase-09 blocker, and it **must not** be edited here
(§6, ordering trap).

For `TCR-28` / `TCR-29`, also verify the per-file coverage table is non-empty (today a green
single-file run reports an **empty** table and `Statements : 100% ( 9/9 )`) and that `git status` is
clean after a coverage-reporting run.

**Aggregate gate (only after `TCR-32` and `TCR-33`):**

```powershell
.\Makefile.ps1 check
```

All legs must execute even when an earlier one fails; all failures must be reported; the exit code
must be non-zero if any leg failed. The `fe-test` leg is expected red and attributed.

### 8.3 Environment note — recursive delete

`Remove-Item -Recurse -Force` is **denied by policy** in this environment. Use
`cmd /c rmdir /s /q <path>` where a recursive removal is genuinely required — e.g. clearing
`frontend/coverage` or a vitest cache directory before re-measuring in `TCR-08` / `TCR-28`. Do not
work around the policy any other way, and do not substitute a per-file delete loop.

### 8.4 Evidence standard

For every block, the Implementor records: the exact command run, the rebuild-or-mount confirmation
per §8.1, the sentinel result, and the collected/failed counts. A count without its
`collected 1410 items` denominator, or a green run without a sentinel, is not accepted as evidence.

---

## 9. Block index by finding

| finding | blocks |
|---|---|
| `TST-001` | `TCR-01` → `TCR-10` |
| `TST-002` | `TCR-09` → `TCR-34`; `TCR-32` → `TCR-33` |
| `TST-003` | `TCR-27` |
| `TST-004` | `TCR-08` → `TCR-28` |
| `TST-005` | `TCR-06` → `TCR-18` |
| `TST-006` | `TCR-15` (residual only) |
| `TST-007` | `TCR-07` → `TCR-19` |
| `TST-008` | — out of scope (§6) |
| `TST-009` | `TCR-05` → `TCR-22` → `TCR-23` → `TCR-24` |
| `TST-010` | `TCR-11` (test half); `SEC-003` owns the default (§6) |
| `TST-011` | `TCR-03` → `TCR-12`, `TCR-13` |
| `TST-012` | `TCR-04` → `TCR-17`, `TCR-25`, `TCR-26` |
| `TST-013` | `TCR-20` → `TCR-21` |
| `TST-014` | `TCR-29` |
| `TST-015` | — out of scope (§6, ordering trap) |
| `TST-016` | `TCR-16` (residual only) |
| `TST-017` | `TCR-30` |
| `TST-018` | `TCR-31` |
| `VAL-09-001`…`012` | — closed-no-action (§6) |
| `test_user_db_valid` (validator-surfaced) | `TCR-02` → `TCR-14` |
