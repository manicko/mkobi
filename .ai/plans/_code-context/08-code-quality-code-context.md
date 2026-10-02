---
id: 08-code-quality-code-context
audit_phase: 08-code-quality
report: .ai/audit/99-validation/08-code-quality-validated-findings.md
finding_prefix: QLT-
validation_prefix: VAL-08-
code_context_authority: Phase-1 Auditor (overrides every report anchor)
baseline_read: cea2d06
status: complete
---

# Phase 08 — Code quality: code context (Phase-1 Auditor)

## 1. Scope and method

| Item | Value |
|---|---|
| Report under decomposition | `.ai/audit/99-validation/08-code-quality-validated-findings.md` (1413 lines, 108 619 B) |
| Report's own baseline | `b23a9cb` |
| **Baseline read for this context** | **`cea2d06`** (HEAD, worktree clean under `src/`, `tests/`, `frontend/`, `pyproject.toml`, `Makefile.ps1`, `alembic/`, `docker/`) |
| Finding-ID prefix actually used | **`QLT-`**, `QLT-001` … `QLT-010`, no gap, no collision; preserved verbatim (report front matter `:34`) |
| Report-level defects | **`VAL-08-`**, `VAL-08-001` … `VAL-08-009` (9) |
| Upstream phase findings (provenance only) | `.ai/audit/08-code-quality/findings.md` — same ten `QLT-*` IDs, no renumbering |
| Verified **by execution** | `uv run ruff check src/ tests/`; `uv run ruff check src/ tests/ alembic/env.py`; `uv run mypy src/`; `uv run mypy src/ alembic/env.py`; `git log`/`git status`/`git merge-base`; `Test-Path` over the CI-path inventory |
| Verified **by reading** | every symbol, anchor, test, doc line, router constructor, pyproject key and Makefile.ps1 body below |
| **Not** re-run | `alembic check` (needs the app container); the live `/openapi.json` read (dev stack not started this run — every claim it underpins has a source-level equivalent recorded); `.\Makefile.ps1 check` end to end (would run the frontend gates and the `frontend/coverage/` deletion hazard) |
| Docker | available but not started; no runtime claim in this context depends on a container |

### 1.1 HEAD-vs-worktree split

The report's baseline is five commits behind HEAD, and **one of those commits discharges the report's
highest-band gate finding.**

| Commit | Subject | Effect on phase 08 |
|---|---|---|
| **`8953bf7`** | **fix(gates): restore green ruff and mypy baselines** | **QLT-003's gate-redness half is already-fixed.** Touches `src/mkobi/config.py` (10 lines), `src/mkobi/services/processing_log_service.py` (−1, the `F401` `sqlalchemy.text` import), `src/mkobi/workers/data_worker.py` (+11/−2, the two `arg-type` sites now pass `[str(value) for value in fvalues]` into `save_filter_values`) |
| `7e37aa2` | chore(gates): put the alembic entry surface under lint and typecheck | `Invoke-Lint`/`Invoke-Typecheck` now name `alembic/env.py` — a phase-02 B6 block already landed, and it narrows the QLT-004 adjacency |
| `2de4156`, `2174895`, `b646ef1`, `9a77625`, `a92b546`, `c4c0b14`, `5b23240` | auth transaction, user unit-of-work, lifespan, rq-worker, lease, docs, validated-reports | outside every `QLT-*` target |
| `cea2d06` | test(users): clean up rows the durable user writes now persist | test-only; no `QLT-*` anchor moved |

`8953bf7` is an ancestor of HEAD (`git merge-base --is-ancestor` → 0). No dirty tracked file under
`src/`, `tests/`, `frontend/`, `pyproject.toml`, `Makefile.ps1`, `alembic/`, `docker/`.

Untracked: the six sibling plans, `.ai/plans/_code-context/`, `.ai/tasks/B1-txn-001-transaction-ownership.yaml`.
Deleted-but-uncommitted tracked trees: `.ai/builders/**`, `.ai/structure/**`, `.ai/models/**`,
`.ai/templates/**`, `.ai/plans/audit-fix-plan.md`, `.ai/audit/templates/audit-final-report.md`,
`frontend/coverage/**`. **These deletions are staged as worktree state, not commits** — a `git checkout`
restores them. This is load-bearing for QLT-005's sequencing caveat, which is therefore still live.

**Anchor drift.** Of the ~90 cited line anchors: **~55 resolve exactly, ~30 resolve to the same symbol
at a shifted line, 0 name a symbol that no longer exists.** Line numbers below are drift evidence only;
the Planner must resolve by symbol.

### 1.2 Gate baseline at `cea2d06`

| Command | Result |
|---|---|
| `uv run ruff check src/ tests/` | **0 errors** — `All checks passed!` |
| `uv run ruff check src/ tests/ alembic/env.py` | **0 errors** — `All checks passed!` |
| `uv run mypy src/` | **0 errors** — `Success: no issues found in 116 source files` |
| `uv run mypy src/ alembic/env.py` | **0 errors** — `Success: no issues found in 117 source files` |
| both mypy runs | `pyproject.toml: note: unused section(s): module = ['tests.*']` — emitted on every run |

**Neither backend gate is evidence for or against any block in this phase any more.** A block in this
phase can use "gates stay green" as its acceptance criterion; a block cannot use "gates are red" as a
premise. The two remaining gate-shaped defects (the `Invoke-Check` short-circuit, and the absence of any
automated path) are structural, not diagnostic, and remain provable from `Makefile.ps1` and the
`Test-Path` inventory alone.

Residual note the Planner should carry: the `[[tool.mypy.overrides]] module = ["tests.*"]` block
(`pyproject.toml:183-185`) is **never reached by any command the project runs**, because no command
passes `tests/` to mypy. That is a live "declared rule nothing applies" instance inside the very
artefact QLT-003 and QLT-005 are about.

---

## 2. Per-finding context

### QLT-001 — the grant endpoint reports a change it does not make

**Verdict: substantiated** (report's two corrections confirmed; band already re-graded HIGH by the report).

| Claim | Current behaviour, by symbol | Status |
|---|---|---|
| existing row returned unwritten | `AccessRepository.grant_access` → `select(...)` → `scalar_one_or_none()` → `if existing: logger.warning(...); return cast(DashboardAccess \| None, existing)`; the only construction site is `DashboardAccess(user_id=…, dashboard_id=…, permission=permission)` in the same method, reached only when `existing is None` | confirmed; drift: report's `:57-63`/`:65` now `:56-63`/`:65-68` |
| normalisation discarded | `DashboardService.grant_access` calls `self._validate_permission(permission)` then `await self.access_repo.grant_access(..., permission=permission)`; `DashboardService._validate_permission` assigns `normalized` and never returns it, so the `read`/`write` branches are unreachable at the repository | confirmed |
| no second write surface | repo-wide search for `\.permission\s*=\|`DashboardAccess\(` over `src/mkobi` → **2** hits, both in `access_repo.py`; the access resource exposes POST and DELETE only, no PUT/PATCH | confirmed |
| `PERMISSION_LEVELS` unread | exactly **1** hit in `src/`+`tests/`: its own declaration in `core/permissions.py` | confirmed |
| four bare-`str` homes | `models/access.py` (`required_permission: str = "view"`, `permission: str = "view"`), `core/permissions.py::check_dashboard_access(required_permission: str = "view")`, `db/repositories/access_repo.py::grant_access(permission: str = "view")` | confirmed |
| blast radius | `required_permission="view"/"edit"/"admin"` bare literals: **21** sites — `api/deps.py` ×6, `api/routes/dashboards_crud.py` ×2, `api/routes/layouts.py` ×1, `api/routes/data.py` ×1, `api/routes/graphs.py` ×4, `api/routes/processing_configs.py` ×3, `services/data_service.py` ×4 | confirmed (VAL-08-009's corrected count) |
| 200/500 divergence (VAL-08-008) | both paths still present: no-op branch returns the existing row → handler echoes `access_grant.permission` → 200; new-row path constructs `DashboardAccess(permission="read")` → PostgreSQL enum rejects → `SQLAlchemyError` re-raised → handler's `except Exception` → `AppException(code=ErrorCode.INTERNAL_ERROR)` → 500 | substantiated, still live |

**Seams an implementor touches**

- Owner module: `db/repositories/access_repo.py::AccessRepository.grant_access` (the no-op branch is the defect) and `services/dashboard_service.py::DashboardService.grant_access` / `::_validate_permission` (the discarded normalisation and the second `grant_access` call site at the dashboard-creation grant).
- Callers of the repository method: exactly two production sites — `DashboardService.create_dashboard` (grants `DashboardPermission.ADMIN` to the new owner) and `DashboardService.grant_access`.
- Protocol declarations (no change needed, they already exist): `interfaces/repository_interfaces.py::IAccessRepository`, `interfaces/service_interfaces.py`.
- Tests that pin current behaviour: **none at route level.** No test in `tests/` issues `POST /dashboards/{id}/access`; the only `grant_access` callers in tests are `tests/test_dashboard_access.py` and `tests/test_dashboards_api.py`, both calling the **repository** on fresh rows (so they do not touch the no-op branch) and both passing `DashboardPermission.*` values. `tests/test_deps.py` pins `check_dashboard_access` behaviour, not the grant path. **Nothing breaks.**
- Docs describing it: `docs/09-database/enums.md` (enum vocabulary), `docs/08-security/*` (access model). No doc states that a grant can be downgraded.
- Rules it touches: `.kilo/rules/project.md` #10 (StrEnum for all constants) and #9 (type safety); `AGENTS.md` §4 backend layering.

### QLT-002 — the grant endpoints declare an audience nothing enforces

**Verdict: substantiated, and the report's strengthening correction is confirmed.**

| Claim | Current behaviour, by symbol | Status |
|---|---|---|
| three declarations | `api/routes/dashboards_access.py` module docstring "All operations require admin role."; `grant_dashboard_access_endpoint` description "Grants user access to dashboard. Available only to owners."; its docstring "Available only to dashboard owner (user with admin permission)." — plus the GET and DELETE descriptions ("Requires admin role.") | confirmed, verbatim |
| no enforcement | `grant_dashboard_access_endpoint` performs only a path/body `dashboard_id` match, then `DashboardService.grant_access` (validate permission → dashboard existence → repository write → commit). No ownership test, no role test, on any of the three handlers | confirmed |
| `current_user` unused | read the handler bodies in full: `current_user` is a declared parameter on `grant_dashboard_access_endpoint`, `get_dashboard_access_endpoint` and `revoke_dashboard_access_endpoint` and is **referenced nowhere in any body**. The grant handler's `logger.info` interpolates `access_grant.user_id`, not the caller | **confirmed — the report's correction to the input is right** |
| "only caller" premise (VAL-08-005) | `AccessRepository.grant_access` has **two** production callers: `DashboardService.grant_access` and `DashboardService.create_dashboard`'s owner-grant | **refuted premise, confirmed by the report** |

**Seams.** Owner module: `api/routes/dashboards_access.py` (all three handlers) plus
`services/dashboard_service.py::DashboardService.grant_access` if the check lands in the service layer.
The candidate shared dependency already exists: `api/deps.py::require_dashboard_read_access` /
`::require_dashboard_write_access` / `::require_dashboard_admin_access` (declarations at `:703`, `:747`,
`:791`). Tests: **no route-level test exists for any of the three endpoints**, so no test breaks — and
no test currently enforces the declared rule either. `tests/test_resource_access_control.py` covers
*dashboard CRUD* access, not the access-management surface. Docs: the OpenAPI descriptions are the
documented contract; `docs/SPEC.md` and the security docs state the owner/admin rule. Rules: `AGENTS.md`
§6 "Access control проверяется на каждом запросе к дашборду".

### QLT-003 — declared backend gates red + aggregate entry point + no automated path

**Verdict: split — the gate-redness half is `already-fixed`; the structural half is `substantiated`.**

| Half | State at `cea2d06` | Evidence |
|---|---|---|
| ruff red on `F401` at `services/processing_log_service.py:13` | **already-fixed** | `8953bf7` removed the import; file now imports `logging`, `datetime/UTC/timedelta`, `typing.cast`, `uuid.UUID`, SQLAlchemy, interfaces, enums, models, exceptions — no `sqlalchemy.text`. `ruff check src/ tests/` → `All checks passed!` |
| mypy red on two `arg-type` at `workers/data_worker.py:740` and `:818` | **already-fixed** | `8953bf7` changed the call sites; they now read `str_values = [str(value) for value in fvalues]` then `save_filter_values(dashboard_id, fname, str_values, db_session)` — the sites have moved to `:762` and `:844`. `mypy src/` → 0 errors |
| `Invoke-Check` short-circuits | **substantiated** | `Makefile.ps1::Invoke-Check` reads `Invoke-Lint; if ($LASTEXITCODE -ne 0) { return }` / `Invoke-Typecheck; if (...) { return }` / `Invoke-FeLint; if (...) { return }` / `Invoke-FeTest` — four sequential guards, no aggregation |
| pytest never invoked by the aggregate | **substantiated** | no `Invoke-Test` inside `Invoke-Check`; `Invoke-Test` exists in the script and is not called from it |
| no automated path | **substantiated** | `Test-Path` → `.github` `False`, `.pre-commit-config.yaml` `False`, `.gitlab-ci.yml` `False`, `azure-pipelines.yml` `False`, `.circleci` `False` |
| report's own footnote | now stale | the report notes the lint/typecheck commands as `ruff check src/ tests/` and `mypy src/`; the script now also names `alembic/env.py` (`7e37aa2`) |

**Merge status (VAL-08-007):** the report's ordering constraint — "clear the diagnostics before the
aggregate is rewired, or the gate is introduced red" — is **satisfied by history**. Phase 09's
`TST-002` half (wiring pytest, automation) is untouched and remains phase 09's. The residual
phase-08 contribution is the *observed* consequence: with lint green, `Invoke-Check` now reaches
`typecheck`/`fe-lint`/`fe-test` and is a real evidence source again — which **removes** QLT-003's
strongest present-tense consequence ("a contributor running the documented aggregate learns nothing
about the type errors, the ESLint result or the vitest result") and replaces it with a weaker one
(the aggregate still stops at the first failure and still omits pytest).

**Seams.** Owner: `Makefile.ps1` only. Tests: none. Docs: `.ai/context/commands.md` publishes the
`check` target; `docs/…/run-guide.md` publishes `uv run mypy src/mkobi/` and `uv run ruff check .`
(two spellings that match neither the script nor each other — a documentation-drift seam this finding
can carry).

### QLT-004 — no schema-drift check

**Verdict: substantiated; no code change since the report.**

| Claim | State | Evidence |
|---|---|---|
| no `alembic check` / `command.check` anywhere | confirmed | search over `Makefile.ps1` + all three compose files + `docker/Dockerfile`: the only alembic invocations are `upgrade head` (the one-shot `migrate` service in `docker-compose.yml`, `docker-compose.override.yml`, `docker-compose.test.yml`), `revision --autogenerate` (`Makefile.ps1::Invoke-MigrationNew`) and `current` (`::Invoke-MigrationStatus`) |
| `compare_type=True` affects autogenerate only | confirmed | `alembic/env.py` sets it in both the offline and online `context.configure` calls; it shapes `--autogenerate` diffing, not any check |
| positive half (`alembic check` returns clean) | **not re-run** | requires the app container; the report itself records it as unsettled, and the finding rests on the absence, which is confirmed |
| placement option 3 (`starter.py` start-up assertion) | still open | `db/starter.py` exists; the report's line range is drift evidence only |

**Seams.** Owner: `Makefile.ps1` (new target) and/or `db/starter.py`. Adjacent and already-landed:
`7e37aa2` put `alembic/env.py` under both gates, so the "alembic is uninspected" half of this finding
is now narrower than filed. Tests: none pin this. Docs: `AGENTS.md` rule 13 is the rule the absence
leaves unenforced; `docs/14-schema-migrations/*` describes the manual workflow.

### QLT-005 — declared toolchain carries artefacts for tools nothing invokes

**Verdict: substantiated; every anchor resolves; the sequencing caveat is still live.**

| Item | State | Evidence |
|---|---|---|
| `[tool.black]` | present, `pyproject.toml:70-82` | confirmed |
| `[tool.isort]` | present, `pyproject.toml:85-88`, `profile = "black"` | confirmed |
| dev deps black / isort / flake8 / autopep8 | present at `:217`, `:218`, `:227`, `:231` | confirmed |
| `pandas-stubs` for a forbidden library | present at `:224`; repo-wide `\bpandas\b` over `src/` → **0 hits** | confirmed |
| dead ruff exception | `pyproject.toml:143` `"src/mkobi/interfaces_old/*.py" = ["UP046"]`; `Test-Path src/mkobi/interfaces_old` → `False` | confirmed |
| root `package.json` | 11 lines, `devDependencies` only, **no `scripts` key`, **7** names (`@types/js-yaml`, `@types/node`, `js-yaml`, `ts-morph`, `ts-node`, `tsx`, `typescript`) | confirmed (VAL-08-009's corrected count) |
| sequencing caveat | **still live** | `.ai/builders/**` is a *tracked deletion in the worktree*, not a commit; `git checkout` restores both the manifest and the tooling that needs it |

**Seams.** Owner: `pyproject.toml` and the root `package.json` + `package-lock.json`. Tests: none — no
test reads the manifest. Docs: `docs/…/run-guide.md` and `.ai/context/commands.md` publish the lint
commands; no doc names black/isort/flake8/autopep8. Rules: `AGENTS.md` §3 forbids pandas — the
`pandas-stubs` dev dependency is the artefact that contradicts the rules file it lives beside.

### QLT-006 — ten of twelve repository providers annotated `-> Any`

**Verdict: substantiated; the census is exact today.**

`src/mkobi/api/deps.py` (890 lines) declares twelve repository factories. Two are typed —
`get_user_repository() -> UserRepository` (`:155`, with the same in-body import at `:164`) and
`get_dashboard_filter_values_repository() -> IDashboardFilterValuesRepository` (`:268`, in-body import
at `:274`). Ten are `-> Any` at `:168, :178, :188, :198, :208, :218, :228, :238, :248, :258`, each
deferring its repository import into the body at `:174, :184, :194, :204, :214, :224, :234, :244, :254, :264`.
The report's line numbers (`:165…:255`, `:152`, `:265`) are uniformly 3 lines low — pure drift.

`pyproject.toml:158 follow_imports = "skip"` is the mechanism, and `mypy src/` returns **0 errors in
`deps.py`**, which confirms the `Any` annotations satisfy the checker rather than being forced on it.

**Seams.** Owner module: `src/mkobi/api/deps.py` only. The protocols already exist in
`interfaces/repository_interfaces.py` — `IUserRepository`, `IDashboardRepository`, `IAccessRepository`,
`IAggregatedDataRepository`, `ILayoutRepository`, `IFilterRepository`, `IGraphRepository`,
`IDashboardFilterValuesRepository`, `IProcessingConfigRepository`, `IProcessingLogRepository`,
`IRegistrationRequestRepository` — **but that module is under `[[tool.mypy.overrides]] module =
["mkobi.interfaces.*"] ignore_errors = true` (`pyproject.toml:178-180`)**, so importing a protocol as
the annotation gives the reader a type the checker does not verify. That is a real constraint on the
remedy and belongs to the Planner, not to this context. Tests: `tests/test_deps.py` pins the **runtime
identity** of ten providers (`test_get_dashboard_repository_returns_dashboard_repository` etc.) via
`isinstance`-style assertions; narrowing the annotations changes no runtime behaviour and breaks no
test. Note `deps.py` also has a `get_redis_client_dependency() -> Any` (`:125`) and a further `-> Any`
at `:321` — outside the finding's twelve but the same shape.

### QLT-007 — client mirrors server fixed values, one value diverged

**Verdict: substantiated; both halves confirmed; the recommendation's alternative still names a path that does not exist.**

| Claim | State | Evidence |
|---|---|---|
| `ENUM_MAPPINGS` checks only the server half | confirmed | `tests/test_enum_db_consistency.py` declares exactly the three pairs (`user_role`/`UserRole`, `dashboard_permission_level`/`DashboardPermission`, `processing_status`/`ProcessingStatus`) and never opens a client file |
| client test is tautological | confirmed | `frontend/src/shared/types/__tests__/enums.test.ts` imports from `'../enums'` and compares literals against the same file; **0** references to `src/mkobi`, "backend" or "Barmode" |
| barmode divergence | confirmed | `BarmodeEnum` in `src/mkobi/models/enums.py` has exactly two members, `GROUP = "group"` and `STACK = "stack"`; `frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx` builds its layout object with `barmode: (graph.config?.barmode \|\| 'group') as 'group' \| 'overlay' \| 'relative' \| 'stack'` — a four-value cast against a two-value server enum |
| server side is typed | confirmed | `src/mkobi/models/data.py` declares `barmode: BarmodeEnum = BarmodeEnum.GROUP` on the graph config model, so `'overlay'` is rejected at the request boundary |
| recommendation's cross-tier test path | **still wrong** | the report's alternative names `backend/src/mkobi/models/enums.py`; there is no `backend/` directory. The real path is `src/mkobi/models/enums.py` |
| six server families with no client counterpart | direction unchanged | `frontend/src/shared/types/enums.ts` mirrors 9 families (`UserRole`, `DashboardPermission`, `GraphType`, `FilterType`, `RegistrationStatus`, `UploadMode`, `ProcessingStatus`, `FileUploadStatus`, `ErrorCode`); `BarmodeEnum`, `OrientationEnum`, `YoyModeEnum`, `EnvironmentEnum`, `MimeTypeEnum`, `FileExtensionEnum`, `FilterOperatorEnum`, `ButtonVariant`, `ComponentSize` have none |

**Seams.** Owner modules: `frontend/src/shared/types/enums.ts` (+ its test) and
`frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx`; the test-side home for a cross-tier
check is `tests/test_enum_db_consistency.py`. Tests that break: **none** — nothing asserts the cast's
wider union. Docs: `docs/09-database/enums.md` is the authoritative client/server table and does not
mention a client mirror; `docs/16-chart-presentation-contract/` (phase 16's territory) governs the
barmode field's presentation contract — the barmode cast touches a phase-16-owned surface.

### QLT-008 — the accessible-dashboard rule has two inline implementations

**Verdict: substantiated; all four anchors resolve.**

| Claim | State | Evidence |
|---|---|---|
| comment names a helper the code never calls | confirmed, verbatim | `api/routes/graphs.py` — `# Admin bypass is handled inside check_dashboard_access` followed immediately by `if current_user.role != UserRole.ADMIN:` and an inline `AccessRepository().get_user_dashboards(...)` comprehension. The file *does* call `check_dashboard_access` elsewhere (`:96`, `:245`, `:333`, `:443`), so the comment is wrong only for this block |
| near-copy in the same layer | confirmed | `api/routes/layouts.py` — `if current_user.role == UserRole.ADMIN: get_all_layouts(...)` `else:` inline `get_user_dashboards(...)`; and the same file calls the shared helper at `:242` |
| shared dependency already has a home | confirmed | `api/deps.py::require_dashboard_read_access` (+ write/admin siblings) |
| ordering note | still load-bearing | the two inline blocks are the **only** admin bypass on those two list endpoints; the replacement must reproduce it |

**Seams.** Owner modules: `api/routes/graphs.py`, `api/routes/layouts.py`, `api/deps.py`. Tests that
break: **none directly** — no test names `get_user_dashboards`, `list_graphs` or `list_layouts`. The
behavioural risk is admin visibility: `tests/test_dashboards_api.py` has admin-sees-everything tests
for the *dashboard* list endpoint, not for graphs or layouts, so a replacement that drops the admin
bypass would go uncaught by the suite. Docs: none describe the rule's implementation site; the rule
lives in `core/permissions.py::check_dashboard_access`.

### QLT-009 — two exported StrEnum families referenced by nothing

**Verdict: substantiated and re-typed — this is a missing integration, not dead code. Recommend investigating purpose and choosing between implementing the declared validation and amending the spec; do not recommend deletion.**

| Claim | State | Evidence |
|---|---|---|
| census: 0 references | confirmed | repo-wide search for `ButtonVariant\|ComponentSize` over `src/mkobi`, `tests/`, `frontend/src` → only `models/enums.py` (declarations) and `models/__init__.py` (import + two `__all__` entries). All other hits are documentation |
| they are documented as intended | confirmed, verbatim | `docs/SPEC.md` states these UI-concept enums "are defined in the backend to support server-side validation of dashboard layout configurations stored in the `layouts.definition` JSONB column … rather than being treated as shared types across layers"; `docs/09-database/enums.md` lists both with intended use "Layout config validation (JSONB)" |
| the declared validation is genuinely absent | confirmed | `db/models/layout.py` stores `definition` as unconstrained JSONB (`Mapped[dict[str, object]]`); `LayoutService.create_layout` takes `definition: dict[str, Any]` and passes it straight to `layout_repo.create` with no check against either enum |

**Seams.** Owner modules: `db/models/layout.py`, `services/layout_service.py`,
`models/processing_configs.py` (the sibling validation surface). Tests that break: `tests/test_layouts.py`
and `tests/test_layout_service.py` all pass `definition={"grid": []}` — **any** validation added here
must decide whether that payload is legal, and roughly a dozen call sites in those two files would be
exposed. Docs: `docs/SPEC.md` and `docs/09-database/enums.md` are the two documents the two branches of
the decision edit in opposite directions. **Note the framing conflict with the project's dead-code
policy** (below, §3.4): these families are documented as intended, so the finding's original
"unreferenced definition nobody has explained" label does not hold and deleting them is not the
default reading.

### QLT-010 — `dashboards` tag declared on parent and every child

**Verdict: split — tag half `substantiated`; `redirect_slashes` half `refuted` (already refuted by the report).**

| Claim | State | Evidence |
|---|---|---|
| tag duplication mechanism | confirmed | `api/routes/dashboards.py` declares `APIRouter(prefix="/dashboards", tags=["dashboards"], redirect_slashes=False)` and then `include_router`s five children; each child re-declares the same tag literal: `dashboards_crud.py`, `dashboards_access.py`, `dashboards_filters.py`, `dashboards_graphs.py`, `filter_values.py`. `app.py` registers only the parent `routes.dashboards.router` |
| `redirect_slashes` declarations | **the report understates their number** | not two — **twelve** routers declare `redirect_slashes=False`: `dashboards`, `dashboards_crud`, `auth`, `users`, `upload`, `data`, `layouts`, `graphs`, `processing_configs`, `processing_logs`, `admin`, `client_errors` |
| `redirect_slashes` is inert | confirmed (the report's refutation stands) | the decision is the application's router's, made once; `app.py::create_app` constructs `FastAPI(...)` with no `redirect_slashes` argument, so Starlette's default `True` governs the whole application. Every one of the twelve declarations is decorative |
| second half of the recommendation | **not executable** | setting the value on any `APIRouter` changes nothing; the only site that decides is the `FastAPI(...)` constructor |

**Seams.** Owner modules: the five child routers for the tag half; `app.py::create_app` for the
`redirect_slashes` observation. Tests: `tests/test_openapi.py` exists but asserts only the RFC 7807
`ErrorResponse` model shape — it never reads tags, so nothing breaks either way. Docs: none.

### Report-level defects (`VAL-08-*`)

| ID | Claim | Verdict at `cea2d06` | Effect on a target |
|---|---|---|---|
| `VAL-08-001` | the 65 % coverage floor is inert (no `--cov` in `addopts`) | **substantiated** | `pyproject.toml:196` `addopts = "--import-mode=importlib -ra -v --strict-markers --cov-fail-under=65"` — no `--cov`; `[tool.coverage.run] source = ["src/mkobi"]` exists but is never reached without the plugin being constructed. One nuance the report does not have: `Makefile.ps1::Invoke-TestAll` runs `pytest --cov=src/mkobi --cov-report=term-missing`, so the *floor is real* on the `test-all` path and inert on the `test` path. The defect is a per-entry-point inconsistency, not a universal absence. No phase-08 code target changes; the report row is the defect |
| `VAL-08-002` | QLT-004 banded MEDIUM where the rubric says HIGH | **substantiated** (documentation-only) | reorders roadmap step 3 ahead of step 4; no code effect |
| `VAL-08-003` | QLT-001's CRITICAL band rests on a storage claim the schema refutes | **substantiated**; the report already re-graded it to HIGH | documentation-only; the finding is real at HIGH |
| `VAL-08-004` | QLT-010's `redirect_slashes` half refuted by the framework | **substantiated, and the count is worse than filed** — twelve declarations, not two | the honest finding is "twelve routers declare a flag the application-level router decides"; still documentation + optional `app.py` observation |
| `VAL-08-005` | QLT-002's "only caller" premise is false | **substantiated** — two production callers, the second being the dashboard-creation owner-grant | decides whether the check is a route dependency or a service check with a named exemption |
| `VAL-08-006` | QLT-009's two-branch recommendation is a question the spec already answered | **substantiated** | collapses QLT-009's remediation to *implement the declared validation, or amend two documents* |
| `VAL-08-007` | QLT-003 and TST-002 claim one concern with no merge ruling | **substantiated; the ordering constraint it adds is now satisfied by history** (`8953bf7`) | phase 09 still owns the wiring half; phase 08's residual is the aggregate's first-failure-wins shape |
| `VAL-08-008` | QLT-001's evidence records a storage-rejected value as "accepted"; the 200/500 divergence reaches no finding | **substantiated; both paths still present in the code** | adds a third element to QLT-001's target: the boundary accepts a value the storage tier cannot hold, and the failure shape depends on prior state |
| `VAL-08-009` | two census counts wrong, both understating | **substantiated** — 21 `required_permission` sites and 7 `devDependencies`, both confirmed | scope numbers only; no target changes |

---

## 3. Cross-cutting architecture and constraints

### 3.1 Module size and responsibility (against `.kilo/rules/project.md` #15, `.ai/context/python-code-standards.md`)

No project rule states a numeric line ceiling; the rule is "small and focused on one thing". The
largest backend modules and what they hold:

| Module | Lines | Responsibility count observed | Note |
|---|---|---|---|
| `workers/data_worker.py` | 1090 | processing, transaction boundaries, filter-value extraction, session lifecycle | QLT-003's two former mypy sites live here; **phase 05's** territory (DP-014 names `_run_with_transaction`) |
| `config.py` | 1055 | every settings family | **phase 01/02's**; also carries the `UploadSettings` platformdirs default the phase-06 plan contests (C06-15) |
| `api/deps.py` | 890 | 12 repository factories, 12 service factories, Redis, auth, 3 dashboard-access dependencies | QLT-006's whole target; single-responsibility violation on its face |
| `interfaces/service_interfaces.py` | 681 | one ABC per service | under `ignore_errors = true` |
| `services/auth_service.py` | 679 | — | **phase 04's** |
| `api/routes/auth.py` | 619 | — | **phase 04's** |
| `services/dashboard_service.py` | 555 | CRUD, access grant/revoke, config validation, permission validation | QLT-001's second target and QLT-002's alternative enforcement site |
| `api/routes/graphs.py` | 476 | — | QLT-008 |
| `app.py` | 460 | lifespan, middleware, 11 router registrations, startup guard | QLT-004's placement option 3 and QLT-010's `redirect_slashes` decision site |

Frontend's largest non-test modules are 327 (`shared/types/api.types.ts`) and 323
(`features/admin/ui/DashboardManagement.tsx`) — well inside the rule. **The size problem is
backend-only and concentrated in four files**, three of which another phase owns.

### 3.2 Duplication

| Pair | Location | Owner |
|---|---|---|
| accessible-dashboard set built inline, twice | `api/routes/graphs.py`, `api/routes/layouts.py` | **phase 08** (QLT-008) |
| permission-level ladder, three copies | `core/permissions.py::PERMISSION_LEVELS` (unread), a literal `perm_map` + a literal `permission_levels` dict inside `_check_access_with_session`, and `DashboardService._validate_permission`'s `read`/`write` branches | **phase 08** (QLT-001), with the authz-decision half flagged to **phase 12** |
| `tags=["dashboards"]` on parent + 5 children | `api/routes/dashboards*.py`, `filter_values.py` | **phase 08** (QLT-010) |
| backend enum vocabulary vs `frontend/src/shared/types/enums.ts` | 9 mirrored families, 0 equality check | **phase 08** (QLT-007) |
| `uv run ruff check .` vs `ruff check src/ tests/ alembic/env.py` vs the `pyproject.toml` `ignore = ["E501"]` "because Black enforces it" comment | `docs/…/run-guide.md`, `Makefile.ps1`, `pyproject.toml` | **phase 08** (QLT-005 seam) |

### 3.3 Typing gaps

| Gap | Count / anchor | Note |
|---|---|---|
| `deps.py` providers annotated `-> Any` | 10 (`:168`…`:258`) | QLT-006 |
| other `-> Any` in the same module | `:125` `get_redis_client_dependency`, `:321` | same shape, outside the finding |
| `dict[str, Any]` / `-> Any` across `src/mkobi` | ~148 occurrences | concentrated in route signatures and `models/` |
| untyped route responses | `dashboards_access.py` returns `dict[str, Any]` and `list[dict[str, Any]]` — **the access resource is one of the few routers with no `response_model`**, while `admin.py`/`auth.py`/`dashboards_crud.py` declare theirs | QLT-001/QLT-002 live in the least-typed router in `api/routes/` |
| Pydantic-vs-dict boundary | `db/models/layout.py` `definition: Mapped[dict[str, object]]` (unconstrained JSONB) ← `LayoutService.create_layout(definition: dict[str, Any])` | QLT-009's missing validation sits exactly on this boundary |
| `mypy` suppressions | `follow_imports = "skip"` (`pyproject.toml:158`); `ignore_errors = true` for `mkobi.interfaces.*` and `mkobi.db.models.*`; `[[tool.mypy.overrides]] module = ["tests.*"]` never reached by any command the project runs | the `tests.*` block is a fourth "declared rule nothing applies" in the two files QLT-003/QLT-005 are about |
| frontend `any` | **0** occurrences of `: any` / `as any` across `frontend/src` (only the word inside comments and one string) | the frontend type-safety bar is already met; QLT-007's cost is a *widened literal union*, not `any` |

### 3.4 Dead code (project policy applied)

Policy from `AGENTS.md` §6 and this programme's rule: **a component that is documented as intended is
future-proofing, not dead code; recommend investigating purpose, not deletion.**

| Candidate | Documented as intended? | Verdict under policy |
|---|---|---|
| `ButtonVariant`, `ComponentSize` | **yes** — `docs/SPEC.md` and `docs/09-database/enums.md` both name the use | **future-proofing / missing integration.** Investigate purpose; do not delete. This is exactly the case the policy exists for, and the report's own re-type agrees |
| `PERMISSION_LEVELS` (`core/permissions.py`) | **no** — the comment above it says "use DashboardPermission", i.e. it is superseded on purpose | stale constant, not documented intent. Lowest-risk deletion in the phase, but still a *constant surface* removal rather than a documented-intent one |
| `utils/file_utils.py::get_user_temp_dir` / `::cleanup_temp_dir` | **no** — re-exported from `mkobi.utils`, no caller in `src/` | **contested.** Phase 06 hands the `platformdirs` pair to "phase 02 (configuration surface) and **phase 08 (documentation surface)**". Confirmed in code: `file_utils.py` imports `platformdirs` and roots the tree at `Path(platformdirs.user_cache_dir("mkobi", appauthor=False))`; callers are only its own definitions and the three `mkobi/utils/__init__.py` re-export lines. **The documentation half is phase 08's** — `AGENTS.md` §5 step 2 claims the data flow uses `platformdirs`, while the code that actually runs is `UploadSettings`'s own default in `config.py` (`class UploadSettings(BaseModel)`, which imports `platformdirs.user_data_dir` at module level but resolves its own temp root). **The AGENTS.md claim is contradicted by the code and is phase 08's to correct** (C06-15) |
| `models/types.py::ProcessingSettingsModel` | **no** doc claims it is used; it is a `BaseModel` with six fields, `extra="allow"` | **confirmed unreferenced** — exactly 1 occurrence repo-wide, its own declaration. Phase 05 names it as an artefact for its own decision DP-014 ("orphan"); **not phase 08's to remove**, and under the dead-code policy the recommendation is to establish intent, not delete |
| `httpx` in `pyproject.toml [project].dependencies` | **no** | **phase 07 owns it** (EB-6 / HO-7, handed to phase 01 for the manifest). Confirmed: `httpx` has **0** imports in `src/`, and is imported by `tests/test_temp_password_retrieval.py`; `tests/conftest.py` uses `ASGITransport`. Phase 07's "tier mismatch, not an absence" claim is **true in the code today**. Phase 08 has no target here |
| `requests` (`pyproject.toml:29`), `pyjwt` alongside `python-jose`, `asgiref` in a Django-free stack | no | confirmed as manifest residue with 0 `src/` imports; phase 07 records them as **not absorbed**; they remain available to phase 08's toolchain block (QLT-005) if the Planner chooses to widen it — that would be a scope decision, not a discovery |
| the two `required_permission`-ladder literals in `core/permissions.py` | no | duplicated constants, covered by QLT-001's typing target |

### 3.5 Error-handling layer conformance

| Rule (`AGENTS.md` §4) | State | Evidence |
|---|---|---|
| never raise `HTTPException` directly | **clean** — 0 occurrences in `src/mkobi` | — |
| `AppException` + `ErrorCode` only | **clean** — 35 `raise AppException`, 153 `ErrorCode.` uses across `api/routes/` | — |
| RFC 7807 responses | enforced centrally; `tests/test_openapi.py` and `tests/test_error_response_format.py` pin the model shape | QLT-010's tag change is orthogonal |
| the one place where a documented outcome and the code diverge | `dashboards_access.py` converts a `ValueError` from the service to `VALIDATION_ERROR` (422) and a DB error to `INTERNAL_ERROR` (500) — so VAL-08-008's 200/500 divergence is produced by a *conforming* error layer over a *wrong* boundary | QLT-001 + VAL-08-008 |

### 3.6 Seams shared with other phases (owner named for each)

| Seam | Symbols | Owner phase |
|---|---|---|
| `make check` / gate wiring, pytest in the aggregate, CI automation | `Makefile.ps1::Invoke-Check`, `Invoke-Test` | **09** (TST-002), per VAL-08-007 |
| rq-worker entrypoint import gate, `pyproject.toml` manifest coherence | `httpx`, `plotly`, `tenacity`, `requests`, `pyjwt`, `asgiref` | **07** (EB-6 → HO-7 to 01) |
| `data_worker.py` transaction shape and its former mypy sites | `workers/data_worker.py::_run_with_transaction` | **05** (DP-014) |
| `models/types.py::ProcessingSettingsModel` | `models/types.py` | **05** (DP-014) |
| `ProcessingConfigService._validate_settings` and the settings Pydantic boundary | `services/processing_config_service.py` | **05** (DP-014) |
| temp-dir roots and cleanup | `utils/file_utils.py::get_user_temp_dir` / `::cleanup_temp_dir`, `UploadSettings` | **02** (configuration) · **06** (FAB-3) · **08** (the `AGENTS.md` §5 documentation claim, C06-15) |
| `AGENTS.md` MIME claims | `AGENTS.md` | **08** (C06-15) — no code owner named by phase 06 |
| `starter.py` start-up drift assertion (QLT-004 placement option 3) | `db/starter.py` | **08**, sequenced after the phase-03/04 `starter.py` remediation series |
| dashboard-access authorization decision and refusal shape | `core/permissions.py::check_dashboard_access`, `DashboardAccess.permission` | **12** (not yet run) — phase 08 owns the declaration-vs-enforcement half, phase 12 owns the decision |
| barmode / graph-config presentation contract | `BarmodeEnum`, `ChartRenderer.tsx` | **16** (chart-presentation-contract) |
| Alembic model-vs-chain comparison | `alembic/env.py`, `db/models/*` | **14** (schema-migrations) — QLT-004's absence is phase 08's; the drift question itself is phase 14's |

---

## 4. In-flight and already-landed work

| Commit / state | Symbol | Effect on this phase |
|---|---|---|
| `8953bf7` (landed) | `services/processing_log_service.py` import block; `workers/data_worker.py` `save_filter_values` call sites; `config.py` (10 lines) | **QLT-003 gate-redness: already-fixed.** Both gates green at HEAD |
| `7e37aa2` (landed) | `Makefile.ps1::Invoke-Lint` / `::Invoke-Typecheck` now name `alembic/env.py` | narrows QLT-004's "alembic is uninspected" adjacency; phase-02 B6 |
| `2de4156`, `2174895`, `b646ef1`, `9a77625`, `a92b546` | auth transaction, user unit of work, lifespan teardown, rq-worker liveness, reconciler lease | outside every `QLT-*` target |
| `c4c0b14`, `5b23240` | docs + validated reports | provenance only |
| `cea2d06` (HEAD) | `tests/*` cleanup for durable user writes | no anchor moved |
| dirty, uncommitted | `.ai/builders/**` deletion (tracked) | **QLT-005's sequencing caveat is live**: the root `package.json` deletion must land in or after the commit that removes `.ai/builders/`, or `git checkout` restores a manifest the tooling needs |
| dirty, uncommitted | `.ai/structure/**`, `.ai/models/**`, `.ai/templates/**`, `frontend/coverage/**` deletions, `.ai/plans/audit-fix-plan.md`, `.ai/audit/templates/audit-final-report.md` | pre-audit; not targets, but `.ai/structure/map.md` and `AGENTS.md`'s link to it are now broken links in a rules file the project mandates — a documentation seam adjacent to QLT-005 |

---

## 5. Discrepancies and risks

| # | Risk | Evidence | Consequence for a block |
|---|---|---|---|
| R1 | **Both backend gates are green**, so the report's HIGH-band QLT-003 is two-thirds discharged by history | `ruff`/`mypy` → 0 errors at `cea2d06`; `8953bf7` is an ancestor | a block premised on "the gates are red" is unfounded. Any block that rewires `Invoke-Check` gains a *green* baseline it can actually use as evidence |
| R2 | `VAL-08-007`'s ordering constraint ("diagnostics before rewiring") is already satisfied; the finding's own strongest consequence is now weaker | lint is green, so the aggregate reaches typecheck/fe-lint/fe-test | the residual phase-08 value is "first-failure-wins + no pytest", both structural |
| R3 | **QLT-002's fix changes an authorization outcome**: 200 → 403 for every caller that is neither owner nor admin, and covers `create_dashboard`'s grant too | `DashboardService.create_dashboard` calls `grant_access(permission=DashboardPermission.ADMIN)`; no test hits the endpoints | a "quality" fix here is a **behavioural** change in disguise. Any working client flow relying on the unenforced rule is a defect, not a client to accommodate |
| R4 | **QLT-001's fix is also behavioural**: a silent no-op becomes a real write; `read`/`write` go 200-or-500 → 422 | `AccessRepository.grant_access` returns the existing row unchanged; `DashboardPermission(normalized)` accepts the aliases | the 422 narrowing is the change most worth announcing. Grep `dashboard_access` for grants that must stay elevated before merging |
| R5 | **QLT-008's fix can silently drop the admin bypass** | the two inline blocks are the only admin check on `graphs` and `layouts` list endpoints; no test names them | the replacement must be specified with "admin bypass included" *before* deletion, or an admin loses visibility on two list endpoints with a green suite |
| R6 | **QLT-009's "implement the validation" branch will break tests** | `tests/test_layouts.py` + `tests/test_layout_service.py` pass `definition={"grid": []}` in ~12 places; `definition` is unconstrained JSONB today | the implement-validation branch is not a pure addition; the amend-the-docs branch is. This is the widest blast radius of any LOW/MEDIUM finding in the phase |
| R7 | **QLT-006's obvious remedy is undermined by a mypy suppression** | `[[tool.mypy.overrides]] module = ["mkobi.interfaces.*"] ignore_errors = true` covers the very protocols the finding points at | annotating with `I*Repository` types a module the checker does not verify is a documentation improvement, not a checked one. This is a genuine technical uncertainty, not a discoverable fact |
| R8 | Report line anchors are systematically low by 2-3 in `deps.py` and `core/permissions.py`, and high in `workers/data_worker.py` | `:168` vs cited `:165`; call sites at `:762`/`:844` vs cited `:740`/`:818` | resolve by symbol; do not trust any line number in the report |
| R9 | `VAL-08-004` understates its own finding: **twelve** routers declare `redirect_slashes=False`, not two | confirmed across `api/routes/` | the honest finding is bigger and cheap; but it is documentation, and `app.py`'s constructor is the only decision site |
| R10 | The 65 % coverage floor is inert on `test` and **live** on `test-all` | `pyproject.toml:196` has no `--cov`; `Makefile.ps1::Invoke-TestAll` passes `--cov=src/mkobi` | any phase-08 block that claims "the coverage floor is dead" is half-wrong; the defect is per-entry-point |
| R11 | Phase 08's QLT-002/QLT-001 both land in `api/routes/dashboards_access.py`, the least-typed router in `api/routes/` (no `response_model`, three `dict[str, Any]` returns) | `dashboards_access.py` | the two HIGH blocks and the QLT-006 typing block all touch `api/deps.py`; a single file becomes a merge point for three blocks |
| R12 | Phase 12 has not run, and phase 08's own rubric defers the access decision and refusal shape to it | report's Block 6 ownership ruling | QLT-002's *rule* (owner-or-admin) is not phase 08's to choose; only the *enforcement point* is |
| R13 | Phase 14 owns schema-migrations; QLT-004's `alembic check` touches the same comparison phase 14 audits | phase split by report | a `check` target added by phase 08 and a drift-detection story by phase 14 must not diverge |

---

## 6. Decision points for the Planner (leave open — I pick none)

| # | Uncertainty | Alternatives | Chooser |
|---|---|---|---|
| D1 | QLT-003's target: is the phase's gate work now *only* the structural half (short-circuit + no pytest + no automation), and is that half phase 08's at all given VAL-08-007 assigns it to phase 09? | (a) phase 08 keeps the first-failure-wins shape as a small `Makefile.ps1` change; (b) phase 08 records phase 08 as having nothing to schedule and hands the whole item to phase 09; (c) split: phase 08 takes the aggregator, phase 09 takes `Invoke-Test` | Planner, with phase 09's plan owner |
| D2 | QLT-006's annotation target: the concrete class, the `I*Repository` protocol, or a `TYPE_CHECKING` import? | (a) concrete class at module level (may introduce a cycle — the report says none exists, unverified at runtime); (b) `I*Repository` protocol (documented-only value, see R7); (c) `TYPE_CHECKING` + string annotation (checker-visible, runtime-safe, and it makes the placement question moot) | Planner; R7 must be weighed |
| D3 | QLT-009: implement the declared `layouts.definition` validation, or amend `docs/SPEC.md` + `docs/09-database/enums.md`? | (a) implement (breaks ~12 test call sites, R6); (b) amend the two docs; (c) both, phased | Planner; under the project's dead-code policy "delete the enums" is **not** on the table without a new argument |
| D4 | QLT-002: route dependency vs service check, and whether `create_dashboard`'s owner-grant is a named exemption or covered by the same rule? | (a) `Depends` on the three handlers (covers the create path harmlessly); (b) service check with the create path named as an intentional exemption; (c) service check that also runs on create (would need an explicit owner parameter) | Planner, coordinated with **phase 12** (R12) |
| D5 | QLT-001: does the fix land the write path first and the typing second, or together? | (a) two commits, write path then typing — the typing change is what makes VAL-08-008's 422 real; (b) one commit | Planner; the report's ordering note ("the refusal path must have a typed permission value to report") points at (a) |
| D6 | Does phase 08 widen QLT-005 to the manifest residue phase 07 declined (`requests`, `pyjwt`, `asgiref`, `pandas-stubs`)? | (a) keep QLT-005 to its filed scope; (b) widen to the whole declared-toolchain surface | Planner; widening collides with phase 07's HO-7 hand-over to phase 01 |
| D7 | QLT-010: fix only the tag duplication, or also act on the twelve inert `redirect_slashes` declarations? | (a) tags only (the report's executable half); (b) tags + delete the twelve decorative flags; (c) tags + set the flag deliberately on the `FastAPI(...)` constructor | Planner; (c) is a behaviour change, so it is a separate decision from (a) |
| D8 | Is the `[[tool.mypy.overrides]] module = ["tests.*"]` block in scope? | (a) fold into a QLT-005-style "declared rule nothing applies" block; (b) leave to phase 09 | Planner — no `QLT-*` finding names it, so including it is a scope extension |
| D9 | Ordering of QLT-001 and QLT-002, both HIGH, both in `dashboards_access.py` | (a) 001 then 002 (the report's step 1 → 2); (b) 002 then 001 | Planner; R11 makes this a merge-point question, not just an ordering one |

---

## 7. Coverage ledger

| Finding | Verdict | Evidence anchors (symbols; lines are drift evidence) |
|---|---|---|
| `QLT-001` | **substantiated** | `AccessRepository.grant_access` (no-op branch `:56-63`); `DashboardService.grant_access` `:356-401`; `DashboardService._validate_permission` `:482-501`; `DashboardService.create_dashboard` owner-grant; `core/permissions.py::PERMISSION_LEVELS` (1 hit = declaration); `models/access.py` ×2; 21 `required_permission=` literal sites |
| `QLT-002` | **substantiated** (report's strengthening confirmed) | `api/routes/dashboards_access.py` — 3 declarations verbatim, `current_user` unreferenced in all 3 bodies, no ownership/role check; 0 route-level tests |
| `QLT-003` | **already-fixed** (gate redness) / **substantiated** (`Invoke-Check` shape, no pytest, no CI) | `8953bf7`; `ruff`/`mypy` → 0 errors; `Makefile.ps1::Invoke-Check` (4 sequential guards, no `Invoke-Test`); `Test-Path` ×5 all `False` |
| `QLT-004` | **substantiated** | 0 occurrences of `alembic check`/`command.check` in `Makefile.ps1`, 3 compose files, `docker/Dockerfile`; `alembic/env.py` `compare_type=True` ×2; `7e37aa2` adjacency |
| `QLT-005` | **substantiated** | `pyproject.toml:70-82`, `:85-88`, `:143`, `:217`, `:218`, `:224`, `:227`, `:231`; root `package.json` (11 lines, 7 devDeps, no `scripts`); 0 `pandas` hits in `src/`; `Test-Path src/mkobi/interfaces_old` → `False`; `.ai/builders` deletion uncommitted |
| `QLT-006` | **substantiated** | `api/deps.py` — 2 typed (`:155`, `:268`) vs 10 `-> Any` (`:168`…`:258`) with in-body imports; `pyproject.toml:158`; `mypy src/` → 0 errors in `deps.py`; `pyproject.toml:178-180` `mkobi.interfaces.* ignore_errors` |
| `QLT-007` | **substantiated** | `BarmodeEnum` (2 members); `ChartRenderer.tsx` 4-value cast; `frontend/src/shared/types/enums.ts` (9 mirrored families); `enums.test.ts` tautological; `tests/test_enum_db_consistency.py::ENUM_MAPPINGS` (3 pairs, server-only); `models/data.py` `barmode: BarmodeEnum` |
| `QLT-008` | **substantiated** | `api/routes/graphs.py` comment + inline block, and 4 real `check_dashboard_access` calls in the same file; `api/routes/layouts.py` inline block + real call at `:242`; `api/deps.py::require_dashboard_read_access` `:703`; 0 tests name the two endpoints |
| `QLT-009` | **substantiated, re-typed** (missing integration, not dead code) | 0 code references; `docs/SPEC.md` + `docs/09-database/enums.md` document the intended use; `db/models/layout.py` `definition: Mapped[dict[str, object]]`; `LayoutService.create_layout(definition: dict[str, Any])` unchecked |
| `QLT-010` | **substantiated** (tags) / **refuted** (`redirect_slashes` — and 12 declarations, not 2) | `api/routes/dashboards.py:20` + 5 children re-declaring the tag; `app.py` registers only the parent; `app.py::create_app` `FastAPI(...)` has no `redirect_slashes`; 12 routers declare it |
| `VAL-08-001` | **substantiated, with a nuance** | `pyproject.toml:196` (no `--cov`); `Makefile.ps1::Invoke-TestAll` passes `--cov=src/mkobi` → floor live on that path only |
| `VAL-08-002` | **substantiated** (documentation only) | QLT-004 banded MEDIUM in the report; rubric assigns HIGH verbatim |
| `VAL-08-003` | **substantiated** (documentation only) | report already re-graded QLT-001 to HIGH |
| `VAL-08-004` | **substantiated, understated** | 12 inert `redirect_slashes=False` declarations, not 2 |
| `VAL-08-005` | **substantiated** | 2 production callers of `AccessRepository.grant_access` |
| `VAL-08-006` | **substantiated** | `docs/SPEC.md` + `docs/09-database/enums.md` answer the question the recommendation re-asks |
| `VAL-08-007` | **substantiated; ordering constraint already satisfied** | `8953bf7` cleared the diagnostics; `Invoke-Check` still omits `Invoke-Test` |
| `VAL-08-008` | **substantiated, still live in code** | no-op branch → 200; new-row branch → enum rejection → `AppException(INTERNAL_ERROR)` → 500 |
| `VAL-08-009` | **substantiated** | 21 `required_permission=` sites; 7 `devDependencies` |

**Sibling-plan hand-over claims, checked against the code today**

| Claim | Source plan | True in the code? |
|---|---|---|
| the `platformdirs` temp-dir pair is "phase 02's configuration surface and **phase 08's documentation surface**" | 06 (C06-12, R-06-4) | **True.** `utils/file_utils.py` defines both, roots at `platformdirs.user_cache_dir`, and has no caller in `src/` beyond its own `mkobi/utils/__init__.py` re-exports. The *documentation* half — `AGENTS.md` §5 step 2's `platformdirs` claim, which the running code contradicts — is confirmed unaddressed |
| `AGENTS.md`'s MIME and `platformdirs` claims are phase 08's (C06-15) | 06 | **True as a documentation owner.** `AGENTS.md` §5 names `platformdirs`; the code path that runs is `config.py::UploadSettings`. No phase-08 finding names it today, so it is a scope decision, not an inherited item (see D6/D8 territory) |
| `models/types.py::ProcessingSettingsModel` is unused | 05 (DP-014) | **True.** Exactly 1 occurrence repo-wide — its own declaration. **Phase 05 owns it; phase 08 has no target** |
| `httpx` is a tier mismatch, not an absence | 07 (EB-6, HO-7) | **True.** 0 imports in `src/`; imported by `tests/` (`conftest.py` `ASGITransport`, `test_temp_password_retrieval.py`); declared in `[project].dependencies`. **Phase 07 owns it; phase 01 receives the manifest residue** |
