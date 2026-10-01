---
phase: 08-code-quality
executed: 2026-09-30
executor: auditor
problems-only: true
baseline: b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd
baseline-dirty: true
findings: 10
by-severity:
  CRITICAL: 1
  HIGH: 2
  MEDIUM: 5
  LOW: 2
---

# Phase 08 — Findings

## Summary

This phase examined the gap between the rules the repository declares and what those rules
actually enforce: the fixed-value homes across backend, database and client; the constant
surface as a maintained artefact; boundary validation; the type checker's configured mode and
suppression surface; responsibility inside single units; one-rule-one-home; the cheap
high-volume conventions; declared contracts and their enforcement points; the declared gates;
and whether anything would notice schema drift. The declared contract surface was reached at
runtime: the dev stack (`.\Makefile.ps1 up`, PostgreSQL 18 + Redis + RQ, 4 uvicorn workers) was
started and the live `/openapi.json` and API were driven end to end with an admin token and a
self-registered `viewer` token. The single most consequential thing found is that the
permission-grant endpoint reports a permission change it never performs — a second grant
request returns HTTP 200 with the requested value while the stored row is unchanged — and that
the same endpoint enforces no ownership or role check at all, so any authenticated `viewer`
can mint an `admin` grant on any dashboard. Both were reproduced against the running stack, and
both are properties of *declared* contracts, which is why they are filed here rather than as an
access-control defect.

## Findings

### QLT-001 — The only endpoint that can change a dashboard grant reports a change it does not make, from a value with four bare-string homes and three disagreeing implementations

**Severity** — CRITICAL

**Zone** — Fixed values: one named home per value, and what bypasses it

**Observation** — `DashboardPermission` is the named home for the dashboard-access permission
vocabulary (`src/mkobi/models/enums.py:17-22`) and is what the column is declared from
(`src/mkobi/db/models/access.py:43-52`). Four other sites carry the same value as a bare `str`:
`AccessGrant.permission: str = "view"` (`src/mkobi/models/access.py:30`, the live request body of
`POST /dashboards/{id}/access`), `AccessCheck.required_permission: str = "view"`
(`src/mkobi/models/access.py:11`), `check_dashboard_access(required_permission: str = "view")`
(`src/mkobi/core/permissions.py:125-129`) and
`AccessRepository.grant_access(permission: str = "view")`
(`src/mkobi/db/repositories/access_repo.py:36`). Sixteen production call sites pass the bare
literals `"view"`, `"edit"` and `"admin"`; the type system cannot catch a wrong one at any of
them, and the generated OpenAPI publishes the field as `{"type": "string", "default": "view"}`
with no enum constraint, so neither can a generated client.

Three implementations of one rule exist and they already disagree about the same value.

1. `DashboardService._validate_permission` (`src/mkobi/services/dashboard_service.py:482-496`)
   normalises `"read" → view` and `"write" → edit` into a local, validates, and **discards the
   result**; `grant_access` then passes the un-normalised original to the repository
   (`:374` validates, `:389` passes `permission=permission`).
2. `AccessRepository.grant_access` (`src/mkobi/db/repositories/access_repo.py:57-63`) returns the
   existing row unchanged when one exists. It never writes the requested `permission`. No `PUT`
   or `PATCH` for this resource exists anywhere in the live surface — `/openapi.json` exposes
   only `POST /dashboards/{dashboard_id}/access` and `DELETE /dashboards/{dashboard_id}/access/{user_id}`.
3. `core/permissions.py` carries a third copy. `PERMISSION_LEVELS` at `:38-42` declares the
   view/edit/admin ordering at module scope and is **referenced by nothing**, while
   `_check_access_with_session:215-219` rebuilds the identical three-entry table inside the
   function, alongside a `perm_map` at `:205-211` whose `"read"`/`"write"` entries are
   unreachable because the guard at `:150-151` rejects any value outside `DashboardPermission`
   before they can apply. The comment at `:43-44` — "For backward compatibility also accept
   `read` as `view` and `write` as `edit`" — describes a behaviour the executing path cannot
   perform.

**Evidence** — Reproduced against the running dev stack. Dashboard
`1699406c-3df2-456a-918b-3c1b8e442c4d`, user `aa5fd18a-1385-4e4f-b1c7-b14aac6b5343`, all four
calls made by the administrator:

| request | HTTP | response `permission` | stored `dashboard_access.permission` |
|---|---|---|---|
| grant `edit` (first) | 200 | `edit` | `edit` |
| grant `view` (downgrade) | 200 | `view` | **`edit`** |
| omit `permission` (model default) | 200 | `view` | **`edit`** |
| grant `superuser` | 422 | — | `edit` |

The garbage case proves the boundary *does* validate (`_validate_permission` →
`VALIDATION_ERROR`, 422), so this is not an unvalidated boundary; the defect is that a **legal**
value is accepted, reported as applied, and not written. The app log for the downgrade contains
only `"Access already exists: user_id=aa5fd18a-…, dashboard_id=1699406c-…"` from
`access_repo.grant_access` — no write is attempted. The `read` alias is accepted by this endpoint
(HTTP 200, `"permission": "read"`) while `check_dashboard_access(required_permission="read")`
raises `ValueError` at `core/permissions.py:150-151`; both facts were observed in the same
session. Static proof of the discarded normalisation and the unread table:
`inspect.getsource` on the production methods confirms `normalized` is assigned and never
returned, `grant_access` passes `permission=permission`, and both `perm_map` and the inline
`permission_levels` are defined inside `_check_access_with_session`.

**Consequence** — A dashboard grant's permission can never be changed after it is first created.
The one API surface that could change it returns HTTP 200 with the requested value, so an
administrator who downgrades an editor from `edit` to `view` is told they succeeded while the
stored value is still `edit`. Read paths that consult `check_dashboard_access` therefore keep
admitting `edit` operations for a principal the administrator believes has only `view`. Because
QLT-002 lets any authenticated caller reach this endpoint, the same false success is available
to non-administrators. The `read`/`write` alias is accepted by exactly one of the two paths that
read the same vocabulary, so the two answers already disagree on a value the system acts on.

**Recommendation** — Make the re-grant path real first: either write `permission` on an existing
row in `AccessRepository.grant_access`, or rename the operation to `create_access` and have the
endpoint return 409 when a grant already exists, so a no-op can never be reported as a grant.
Then give the value one typed home: change `AccessGrant.permission`,
`AccessCheck.required_permission`, `check_dashboard_access(required_permission)` and
`AccessRepository.grant_access(permission)` to `DashboardPermission`, delete the `str = "view"`
defaults, and delete the `"read"`/`"write"` branches in `_validate_permission` together with the
comment at `core/permissions.py:43-44` — the `perm_map` entries at `:205-211` and
`PERMISSION_LEVELS` at `:38-42` are then dead and go with them. Any shipped test asserting the
current no-op must change with the fix. Phase 12 owns the access decision; this finding owns the
value's homes and the false success report.

### QLT-002 — The dashboard access-grant endpoints declare an audience that no executing path enforces

**Severity** — HIGH

**Zone** — Declared contracts and their enforcement point: whether anything checks the claim, and whether anything reaches it

**Observation** — `src/mkobi/api/routes/dashboards_access.py` declares three audiences that
nothing in the executing path applies. The module docstring at `:4` states "All operations
require admin role." The route description at `:35` states "Grants user access to dashboard.
Available only to owners." The handler docstring at `:47` repeats "Available only to dashboard
owner (user with admin permission)." The handler body `:38-127` resolves `current_user:
CurrentUser` and then uses it only as a log field (`:65-70`); it calls
`dashboard_service.grant_access` at `:85-90`, whose implementation
(`src/mkobi/services/dashboard_service.py:356-401`) performs `_validate_permission`, a
dashboard-existence check, and a repository write — no ownership test and no role test. The
live OpenAPI confirms the contract as published: `security` on the operation is exactly
`[{HTTPBearer: []}]`, with no role or ownership constraint. The same module's `GET` (`:138`) and
`DELETE` (`:181`) handlers likewise carry no authorization check.

**Evidence** — Reproduced against the running dev stack. An admin created dashboard
`7b58b790-ae1e-474e-b1e9-b5806f004852`; the sole `dashboard_access` row was the owner's
(`13a1f341-… admin`), verified by direct `psql` query against `bidb`. A user with `role=viewer`,
id `63c7f3cc-4f95-4116-90bf-defa7ac3c67c`, obtained a token through the ordinary
`register-request → admin/approve → admin/temp-passwords → login` flow and then issued:

```
POST /api/v1/dashboards/7b58b790-ae1e-474e-b1e9-b5806f004852/access
{"user_id":"63c7f3cc-…","dashboard_id":"7b58b790-…","permission":"admin"}
→ HTTP 200 {"message":"Access granted", … "permission":"admin"}
```

`dashboard_access` afterwards held two rows, `13a1f341-… admin` and `63c7f3cc-… admin`.
`GET /api/v1/dashboards/my` then returned that dashboard at `permission=admin` for the viewer.
The app log line `"Granting access: dashboard_id=7b58b790-…, user_id=63c7f3cc-…, permission=admin"`
(`module: dashboards_access`) is emitted from `:65-70`, inside the handler that performed no
authorization.

**Consequence** — Any authenticated account, of any role, can insert an `admin` grant for itself
or any other user on any dashboard in the database, including dashboards owned by the
administrator. The grant is immediately effective on the read paths that consult
`check_dashboard_access`. The defect is not merely an omission: the three published descriptions
tell an integrator the opposite, so the contract an operator reads is narrower than the audience
the path admits.

**Recommendation** — Make the declared audience executable at the single place the rule belongs:
resolve the caller's `admin` permission on the target dashboard inside
`DashboardService.grant_access` (it is the only caller of `AccessRepository.grant_access`), or as
a route dependency on the three handlers, refusing before the repository call. Then delete the
prose from the module docstring and the two descriptions the enforcement makes true, so there is
one statement of the rule rather than four. Phase 12 owns the access-decision review; this
finding covers only the contradiction between the declared audience and the executing path, and
should not be closed until phase 12 has reviewed the whole decision surface.

### QLT-003 — Both declared backend gates are red at HEAD, so the aggregate entry point cannot reach the frontend gates, and no declared gate is wired to an automated path

**Severity** — HIGH

**Zone** — The gates the project declares: where each is wired, what each decides, and whether it can be run the way the pipeline runs it

**Observation** — The repository declares five quality gates (`Makefile.ps1:75-81`, `:194-249`):
`lint` (`ruff check src/ tests/`, `:222`), `typecheck` (`mypy src/`, `:230`), `fe-lint` (`:234`),
`fe-test` (`:238`) and `test` (`:196`). `Invoke-Check` (`:241-249`) runs lint → typecheck →
fe-lint → fe-test, returning after the first non-zero exit. At the audit baseline, on
unmodified code, both backend gates fail:

* `ruff check src/ tests/` → 1 error, `F401 'sqlalchemy.text' imported but unused` at
  `src/mkobi/services/processing_log_service.py:13`.
* `mypy src/` → 2 errors, both `Argument 3 to "save_filter_values" … incompatible type
  "list[str | int | float | bool]"; expected "list[str]"` at
  `src/mkobi/workers/data_worker.py:740` and `:818`, plus the note
  `pyproject.toml: note: unused section(s): module = ['tests.*']`.

Because `Invoke-Check` short-circuits on the first failure, `typecheck`, `fe-lint` and `fe-test`
are unreachable through the entry point contributors are pointed at, and the two type errors sit
outside any gate that runs. Separately, no gate is wired to an automated path: there is no
`.github/` directory and no pre-commit configuration anywhere in the repository, and neither
`ruff` nor `mypy` appears in `docker/Dockerfile`. The only build-time check that runs is the
frontend `npm run build` at `Dockerfile:22`, which includes `tsc -b`.

**Evidence** — `uv run ruff check src/ tests/` and `uv run mypy src/` at HEAD `b23a9cb`, with
`git status --porcelain -- src/` empty before and after, so neither failure is produced by the
concurrent remediation programme; the two files last changed in `40866f1` and `c15707b`, both
older than the remediation series beginning at `8505a62`. The absence of an automated path is an
inventory with a stated absence: `Get-ChildItem -Force` on the repo root lists no `.github`, no
`.pre-commit-config.yaml`, no `.gitlab-ci.yml`; no `Makefile.ps1` target invokes a gate from
`up`, `build` or `rebuild`; `Dockerfile` has 41 `RUN`/`CMD`/`HEALTHCHECK` lines, none of which
is `ruff` or `mypy`.

**Consequence** — The repository's stated quality surface is unpassable today. `.\Makefile.ps1
check` stops at the first ruff error, so a contributor running the documented aggregate gate
learns nothing about the type errors, the ESLint result or the vitest result and may believe a
change is fully checked when three gates never ran. Nothing runs any gate automatically, so the
green/red state of the repository depends entirely on a contributor choosing to run the command.

**Recommendation** — Fix the three diagnostics first: remove the unused import, and widen or
convert the `save_filter_values` value type so the declared contract matches what the worker
passes. Then stop short-circuiting before the client gates so one failing backend gate does not
hide them, and add a `test` invocation to `Invoke-Check` so the aggregate matches the declared
gate list. Wiring the five gates into a CI workflow is the only change that makes them a gate
rather than a convention; until one exists, the `Makefile.ps1` help text is the sole statement
that they are mandatory.

### QLT-004 — No schema-drift check exists, so a model change shipped without a migration would fail nothing

**Severity** — MEDIUM

**Zone** — Schema drift: whether anything would notice, and which rows are written by code rather than by a migration

**Observation** — The model layer and the migration chain are two independent declarations and
nothing compares them. `alembic/env.py:79` and `:91` set `compare_type=True`, which affects
`--autogenerate` diffing only; it is not a drift gate. There is no `alembic check` invocation
anywhere: not in `Makefile.ps1` (all 38 targets read), not in `docker/Dockerfile` (41 lines
read), not in any compose file, and not in the absent CI configuration. The one automated path
that applies the chain is the one-shot `migrate` service, which runs `upgrade head` and exits; it
never diffs the models. There is no other schema-drift check of any kind.

**Evidence** — A repository-wide search for `alembic check|command.check` returns no matches
outside documentation prose. Running the check by hand against the dev database,
`alembic check` from inside the app image reports `No new upgrade operations detected.`
(`alembic check`, dev stack at baseline; 43 paths live in `/openapi.json`). The absence is the
finding, not the drift: there is no drift today, and nothing would notice if a model column,
index or enum value changed without a revision.

**Consequence** — The rule "Alembic for all schema changes" (AGENTS.md rule 13) is enforced only
by the author remembering to run `.\Makefile.ps1 migration-new`. A model change that forgets the
revision ships silently: the app starts, and every model-derived query that touches the new
column fails at runtime for that column alone, with no declared gate reporting anything. The
failure surfaces per-column rather than at start-up, which is the worst shape for diagnosis.

**Recommendation** — Add `alembic check` to `Invoke-Check` — it exits non-zero on drift and
returns clean today, so it costs one command and nothing else — or, better, assert it at
start-up in `db/starter.py` beside the revision check at `starter.py:160-169`, so the process
refuses to answer if the chain and the models disagree. Keep it out of the `migrate` service:
that service must be able to run against a drifted database in order to repair it.

### QLT-005 — The declared toolchain carries artefacts for tools nothing invokes, one for a library the project forbids, and one exception naming a path that does not exist

**Severity** — MEDIUM

**Zone** — Convention compliance: the cheap high-volume rules, and which of them are broken

**Observation** — Four declared toolchain artefacts are inert, mis-declared, or point at nothing.

* `pyproject.toml:70-88` configures **black** (`line-length = 88`) and **isort**
  (`profile = "black"`) as separate tools, and black, isort, flake8 and autopep8 are all
  installed as dev dependencies (`:217`, `:218`, `:228`, `:231`). The project's declared
  formatter is ruff: the project rules record that "`ruff format` … does **NOT** sort imports —
  `.\Makefile.ps1 format` runs `ruff check --fix src/ tests/`, not `ruff format`", and
  `Invoke-Format` (`Makefile.ps1:225-227`) invokes ruff. Five formatters/linters are configured;
  one is wired. Running black or isort leaves ruff's findings in place and vice versa.
* `pandas-stubs==3.0.0.260204` (`pyproject.toml:224`) is a type stub for pandas, a library
  AGENTS.md lists under "**Запрещено:** pandas" and replaces with Polars. No pandas import exists
  anywhere in `src/mkobi/`.
* `pyproject.toml:143` declares `"src/mkobi/interfaces_old/*.py" = ["UP046"]  # Old interfaces,
  not used`. That path does not exist; the live package is `src/mkobi/interfaces/`. The exception
  can never apply to anything.
* The repository root carries a `package.json` and `package-lock.json` declaring six
  devDependencies (`@types/js-yaml`, `@types/node`, `js-yaml`, `ts-morph`, `ts-node`, `tsx`,
  `typescript`) with **no `scripts` block at all** and no importer anywhere in the repository.
  They are the toolchain of `.ai/builders/` (a `ts_map.ts`, a `py_map.py`, a `build.bat`), all of
  which are deleted in the working tree at this baseline.

**Evidence** — `Test-Path src/mkobi/interfaces_old` returns `False`; the root `package.json` was
read in full (11 lines, `devDependencies` only); a search for `ts-morph|ts-node|\btsx\b|js-yaml`
across `src/`, `frontend/src/`, `tests/`, `alembic/` and every `*.ps1` returns no importer; a
search for `\bpandas\b` across `src/mkobi/` returns no import.

**Consequence** — Four of the five declared Python quality tools can be run by a contributor and
will produce a different answer from the one the gate produces, with no record of which is
authoritative. The dead ruff exception and the dead root npm manifest cost nothing at runtime but
each is a place a future contributor will look and find nothing, and `pandas-stubs` puts a
forbidden library's type surface into the resolution path for a project that has no pandas.

**Recommendation** — Delete `pandas-stubs`, the `interfaces_old` per-file-ignore entry and the
root `package.json`/`package-lock.json` (the tooling that needed them is already gone). Decide
which formatter is authoritative: if it is ruff, delete the `[tool.black]` and `[tool.isort]`
sections and the black, isort, flake8 and autopep8 dev dependencies so the configuration states
one rule; if black is still wanted, wire it into `Invoke-Format`. This is deletion and no gate
result changes.

### QLT-006 — Ten of twelve repository providers in `deps.py` are annotated `-> Any` because their imports are deferred into the function body, and no cycle exists to require that

**Severity** — MEDIUM

**Zone** — Type width and the sanctioned-suppression surface: what is enforced, what is silenced

**Observation** — `src/mkobi/api/deps.py` declares twelve repository factories. Two are typed:
`get_user_repository() -> UserRepository` (`:152`) and
`get_dashboard_filter_values_repository() -> IDashboardFilterValuesRepository` (`:265`). Ten are
annotated `-> Any`: `get_dashboard_repository` (`:165`), `get_access_repository` (`:175`),
`get_aggregated_data_repository` (`:185`), `get_layout_repository` (`:195`),
`get_filter_repository` (`:205`), `get_dashboard_filter_repository` (`:215`),
`get_processing_config_repository` (`:225`), `get_processing_log_repository` (`:235`),
`get_registration_request_repository` (`:245`) and `get_graph_repository` (`:255`). Each of the
ten defers its class import into the function body (`:171`, `:181`, `:191`, `:201`, `:211`,
`:221`, `:231`, `:241`, `:251`, `:261`). The widening is **accidental, not load-bearing**:
`get_user_repository` carries the identical in-body import at `:161` and is annotated with the
class name, because that module is already imported at module scope at `:45`; and
`get_dashboard_filter_values_repository` is annotated with an interface the project already
declares in `mkobi.interfaces.repository_interfaces`. There is no import cycle to justify the
deferral — no module under `src/mkobi/db/` or `src/mkobi/services/` imports `mkobi.api` at all.
The type checker's `follow_imports = "skip"` (`pyproject.toml:158`) means a name that exists only
inside a function body resolves to `Any`, so the annotation follows the placement rather than the
class.

**Evidence** — An AST walk of `src/mkobi/` listing every `Import`/`ImportFrom` inside a function
body returns 23 such imports in `deps.py` alone. A search for `from mkobi.api|import mkobi.api`
across every file under `src/mkobi/db/` and `src/mkobi/services/` returns no matches, so no cycle
exists. `uv run mypy src/` reports zero diagnostics in `deps.py`, confirming the `Any`
annotations satisfy the checker rather than being forced on it. Per the block's production-only
rule, the wider `Any` population elsewhere was not classified individually: `mkobi.db.models.*`
and `mkobi.interfaces.*` are switched off wholesale by `pyproject.toml:176-177` and `:180-181`,
so their internals sit outside the sanctioned surface by configuration rather than by annotation.

**Consequence** — Every route that takes a repository through `Depends` receives a value mypy
treats as untyped, so a renamed repository method, a changed argument order or a wrong keyword at
a call site inside a route is invisible to the type checker. The checker does run over these
modules, so the silence is specific and permanent rather than incidental: the ten annotations are
why the gate cannot see those call sites, and a reader comparing `:152` with `:165` has no way to
tell which is the intended house style.

**Recommendation** — Move the ten imports to module scope beside the existing `:45` and annotate
each factory with the repository class, or with the `I*Repository` protocol already declared in
`mkobi.interfaces.repository_interfaces` where one exists — which also removes ten concrete-class
dependencies from the route layer. Leave the in-body import at `:161` alone or delete it; the
module-scope import at `:45` is what makes that annotation resolvable. Verify with
`uv run mypy src/` before and after: the change must not add diagnostics.

### QLT-007 — The client mirrors the server's fixed values in a second home with no equality check, and one mirrored value has already diverged

**Severity** — MEDIUM

**Zone** — Fixed values: one named home per value, and what bypasses it

**Observation** — `frontend/src/shared/types/enums.ts` restates eight of the server's StrEnum
families and adds one of its own, in a second tier, with nothing keeping the two equal. The
project's own consistency test on this vocabulary (`tests/test_enum_db_consistency.py`) covers
the server-to-database tier and never opens the client file: its `ENUM_MAPPINGS` (`:223-227`)
lists three pairs — `user_role`/`UserRole`, `dashboard_permission_level`/`DashboardPermission`,
`processing_status`/`ProcessingStatus` — and asserts both directions only for `processing_status`
(`:186-191`). `RegistrationStatus` is a fourth mapped enum and is absent from the mapping. The
client's own test (`frontend/src/shared/types/__tests__/enums.test.ts`) is a tautology: it
asserts hardcoded string literals against `enums.ts` and would pass unchanged if the server moved.
One family has already diverged. `BarmodeEnum` (`src/mkobi/models/enums.py:148-151`) has two
members, `group` and `stack`;
`frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx:149` casts the same field to
`'group' | 'overlay' | 'relative' | 'stack'`, admitting two values the server cannot produce.
`FileUploadStatus` (`enums.ts:66-73`) is a client-only vocabulary for the concept the server
names `ProcessingStatus`, and `enums.test.ts:93-100` covers it as if it were shared.

**Evidence** — A per-family reference census over `src/mkobi/`, `tests/` and `frontend/src/`
(excluding `enums.ts` and `enums.test.ts`) establishes the client counterpart per family:
`UserRole` 91 server / 5 client, `DashboardPermission` 51 / 5, `GraphType` 21 / 4, `FilterType` 16
/ 3, `RegistrationStatus` 21 / 2, `UploadMode` 23 / 4, `ProcessingStatus` 90 / 7, `ErrorCode` 320
/ 183; and no client counterpart at all for `EnvironmentEnum`, `MimeTypeEnum`, `FileExtensionEnum`,
`ButtonVariant`, `ComponentSize`, `OrientationEnum`, `BarmodeEnum`, `YoyModeEnum`,
`AggregationFunctionEnum`, `FilterOperatorEnum`. The live OpenAPI confirms the server side:
`GraphBase.type` is a `GraphType` enum in the generated schema. A search confirms
`enums.test.ts` contains no reference to `src/mkobi/models/enums.py` or to any backend artefact.

**Consequence** — The client and server each hold a copy of the same fixed values and the only
test that names them checks one copy against itself. The barmode cast is the failure the
duplication produces in practice: a client author who writes `barmode: 'overlay'` gets a clean
`tsc -b` and a 422 from the server, and the divergence is invisible in review because each side
looks correct locally. The six server families with no client counterpart are the opposite
direction: nothing states that their absence is deliberate.

**Recommendation** — Generate `frontend/src/shared/types/enums.ts` from the OpenAPI schema at
build time (FastAPI already emits `GraphType`, `DashboardPermission`, `RegistrationStatus` and
every `ErrorCode` as enums), or, if generation is too heavy, replace the literals in
`enums.test.ts` with one test that reads `backend/src/mkobi/models/enums.py` and asserts
membership equality per family — that converts a tautology into a cross-tier check for the cost
of one file. Independently, drop `'overlay'` and `'relative'` from the cast at
`ChartRenderer.tsx:149`; the two the server can produce are the two the type should admit.

### QLT-008 — The accessible-dashboard rule has two inline implementations, and a comment names a third that the code never calls

**Severity** — MEDIUM

**Zone** — One rule, one home: whether exactly one implementation exists

**Observation** — The rule "which dashboards may this user see" has one named implementation,
`core.permissions.check_dashboard_access`, and two inline re-implementations in the same layer.
`api/routes/graphs.py:174-183` and `api/routes/layouts.py:154-166` each test `current_user.role`
against `UserRole.ADMIN` themselves and then build the accessible set by comprehending
`access_repo.get_user_dashboards(...)` — the same five lines in both modules. `layouts.py:230-258`
in the same file does use `check_dashboard_access`, so the file already demonstrates the shared
path. The comment at `graphs.py:173` reads "Admin bypass is handled inside
check_dashboard_access", naming the implementation the following three lines do not call.
Neither inline copy is a deliberate exclusion: no record of a reason exists at either site, and
no import cycle or error-contract constraint separates them from the shared helper
(`permissions.py` imports only repositories, models and the security module, none of which
import `api`).

**Evidence** — A normalised cross-module duplicate scan over `src/mkobi/` found zero
byte-identical 8-line windows, five at 5 lines, and this pair among the twelve at 4 lines:
`graphs.py` ⇄ `layouts.py`, identical across `access_repo = AccessRepository()` and
`accessible_dashboards = [d.id for d in await access_repo.get_user_dashboards(user_id=…)]`. Both
call sites of `check_dashboard_access` in `layouts.py` (`:242`, `:246`) sit in the same file as
the inline copy at `:158`. The scan also surfaced two false positives, recorded here so a later
pass does not re-file them: the `db/models/dashboard.py` ⇄ `db/models/__init__.py` window is a
`TYPE_CHECKING` block versus a real import and serves different purposes, and the
`interfaces/service_interfaces.py` ⇄ services windows are protocol declarations matching their
implementations' signatures.

**Consequence** — A change to how the accessible set is computed — adding a condition, or
changing what "accessible" means for a viewer — has to be made in three places and nothing names
the other two. The comment at `graphs.py:173` is worse than a bare duplicate: a reader who trusts
it concludes the admin bypass is centralised, so a fix applied to `check_dashboard_access` looks
complete while two list endpoints still bypass it.

**Recommendation** — Delete the inline blocks at `graphs.py:174-183` and `layouts.py:154-166` and
add one shared dependency in `api/deps.py` (which already declares `require_dashboard_read_access`
at `:700` and its siblings) returning the accessible dashboard-id set, then have both endpoints
call it. Correct or delete the comment at `graphs.py:173` in the same change.

### QLT-009 — Two exported StrEnum families are referenced by nothing in the repository

**Severity** — LOW

**Zone** — The constant surface as a maintained artefact: is anything else maintaining it

**Observation** — `ButtonVariant` (`src/mkobi/models/enums.py:120-130`, eight members) and
`ComponentSize` (`:133-138`, three members) are defined, re-exported and `__all__`-published
(`src/mkobi/models/__init__.py:65-66` and `:146-147`) — and referenced nowhere. No model field,
no service, no route, no repository and no test names either. The other families are each either
used as a field type (`OrientationEnum`, `BarmodeEnum`, `YoyModeEnum`, `AggregationFunctionEnum`,
`FilterOperatorEnum`, `UserRole`, `DashboardPermission`, `GraphType`, `FilterType`,
`RegistrationStatus`, `UploadMode`, `ProcessingStatus`) or consumed as a constant
(`EnvironmentEnum`, `MimeTypeEnum`, `FileExtensionEnum`). The header comment at `:117` reads
"# Additional enums used in dashboards", which asserts a use the census does not find.

**Evidence** — A per-family reference census over `src/mkobi/` (definition and export sites
excluded), `tests/` and `frontend/src/` returns `ButtonVariant` = 0 references and
`ComponentSize` = 0 references outside `enums.py` and `models/__init__.py`; the same census
returns 91 for `UserRole` and 320 for `ErrorCode`. Export lists were also checked for private
names as block evidence: `models/__init__.py` (67 entries), `interfaces/__init__.py` (16),
`utils/__init__.py` (5) and `core/__init__.py` (0) contain no underscore-prefixed entries, so that
clause of this block is discharged and is not filed.

**Consequence** — Two public exports invite callers to use a vocabulary the server never
consults: a caller that sets `ComponentSize.SMALL` on a field has changed nothing, because no
field, column or branch reads it. The cost is documentary — the constant surface overstates what
the system constrains — and it grows silently, since nothing fails when a member is added to an
unused family.

**Recommendation** — Establish which of the two answers the question is for. If they are reserved
for a component API not yet built, say so in the class docstring and record the intent in
`docs/SPEC.md` so they are future-proofing rather than an unexplained export; if they are
leftovers, delete the classes and their four export entries. Either answer is cheap; leaving
them unremarked is the only wrong one.

### QLT-010 — The `dashboards` router tag is declared on the parent router and on every child router, so the published schema carries it twice

**Severity** — LOW

**Zone** — Fixed values: one named home per value, and what bypasses it

**Observation** — `api/routes/dashboards.py:28` declares
`APIRouter(prefix="/dashboards", tags=["dashboards"], redirect_slashes=False)` and is the only
`dashboards` router registered directly on the application (`src/mkobi/app.py:238`). Its five
child routers — `dashboards_crud.py:28`, `dashboards_access.py:28`, `dashboards_filters.py:28`,
`dashboards_graphs.py:28` and `filter_values.py:28` — each declare the same `tags=["dashboards"]`
literal again. FastAPI concatenates parent and child tags, so every operation under
`/dashboards/**` publishes `"tags": ["dashboards", "dashboards"]`. The child routers also disagree
with each other on `redirect_slashes`: `dashboards_crud.py` sets `False` and the other four omit
it, leaving FastAPI's default of `True`.

**Evidence** — The live `/openapi.json` served by the running app, operation
`POST /api/v1/dashboards/{dashboard_id}/access`, returns `"tags": ["dashboards", "dashboards"]`.
A scan of every `APIRouter(...)` declaration in `src/mkobi/api/routes/` returns fifteen routers;
the five duplicated tags and the `redirect_slashes` split are visible in that output. No other
router in the set is included by a parent that shares its tag, so the duplication is confined to
the dashboards subtree.

**Consequence** — The published contract that clients generate from carries a duplicated tag on
every dashboard operation, and the tag grouping in generated docs shows each dashboard operation
twice. The mechanism is a fixed value written in six places with nothing keeping the six equal;
the `redirect_slashes` split means the same subtree answers the two spellings of a trailing-slash
URL differently depending on which module owns the route.

**Recommendation** — Delete `tags=["dashboards"]` from the five child routers and keep it on the
parent, which already covers every operation it includes, then set `redirect_slashes=False`
explicitly on all five so the subtree answers uniformly. Verify by re-reading `/openapi.json` and
confirming each dashboard operation lists `["dashboards"]` once.

## Distribution

Findings fall on four components, and the access-control area carries the most:
`src/mkobi/api/` and `src/mkobi/core/permissions.py` account for four findings (QLT-001, QLT-002,
QLT-008 and the route half of QLT-006), three of which concern the same three lines of
`dashboards_access.py`. The declared gate and toolchain surface (`Makefile.ps1`, `pyproject.toml`,
`package.json`, `alembic/env.py`) carries three (QLT-003, QLT-004, QLT-005). The client tier
carries one (QLT-007). The constant surface itself carries one (QLT-009) and is the least
consequential area examined.

- Access-control value and authorization surface — QLT-001 (CRITICAL), QLT-002 (HIGH)
- Declared gates, toolchain and drift — QLT-003 (HIGH), QLT-004 (MEDIUM), QLT-005 (MEDIUM)
- Fixed-value homes across tiers — QLT-007 (MEDIUM), QLT-010 (LOW)
- Rule duplication and type width — QLT-008 (MEDIUM), QLT-006 (MEDIUM)
- Constant-surface hygiene — QLT-009 (LOW)

## Cross-Finding Analysis

QLT-001, QLT-002 and QLT-008 share one cause: **the dashboard-access rule has no single
enforcement point.** The audience that may call the grant endpoint is described in three places
and enforced in none (QLT-002); the value that endpoint writes is described in four signatures
and three implementations that already disagree (QLT-001); the rule that decides which dashboards
a user may see is implemented once by name and twice inline (QLT-008). A change to any one of
these can be made completely and still leave the other two untouched, which is why the three
compound: QLT-001's false success is only reachable because QLT-002 lets a non-administrator reach
it, and QLT-008's inline copies mean a fix applied to `check_dashboard_access` looks complete
while two list endpoints still bypass it.

QLT-003, QLT-004 and QLT-005 share a second, independent cause: **declared rules are maintained
as configuration rather than as enforcement.** A gate that is red but unenforced, a drift check
that is configured but never invoked, five formatters of which one is wired, a stub for a
forbidden library and an exception naming a path that does not exist are all the same shape: the
configuration states a rule and no executing path consults it. QLT-006 is that shape inside a
single file — ten annotations that disable checking where it would otherwise apply.

QLT-007, QLT-009 and QLT-010 are independent of each other and of the two groups above; they share
only the vocabulary theme of blocks 1 and 2.

## Roadmap

Grouped by cause, not by severity.

**Step 1 — close the false success before closing the authorization gap.** Fix QLT-001's write
path: `AccessRepository.grant_access` must either update `permission` on an existing row or the
endpoint must refuse a re-grant with 409. Then type the four `str = "view"` declarations to
`DashboardPermission`, delete the `read`/`write` branches and the comment at
`core/permissions.py:43-44`. This lands first because until it is fixed an administrator's
attempt to downgrade a grant is silently discarded, so any test written for step 2 against the
current behaviour would encode the defect. `uv run mypy src/` must show no new diagnostic.

**Step 2 — make the declared audience executable.** Fix QLT-002 by enforcing owner-or-admin on the
three access endpoints, then delete the three prose statements the enforcement makes true.
Requires step 1 to be merged first so the refusal path has a typed permission value to report.
Phase 12's access-decision review must reach the same code; coordinate before either changes
`dashboards_access.py`.

**Step 3 — make the gates say what they decide.** Fix QLT-003's three diagnostics, then add
`alembic check` (QLT-004) and `test` to `Invoke-Check` and stop short-circuiting before the client
gates. Nothing in step 3 is gated on steps 1-2; it is independent.

**Step 4 — the toolchain deletions.** Apply QLT-005 in full (delete `pandas-stubs`, the
`interfaces_old` ignore and the root `package.json`; delete either the black/isort configuration
or the ruff formatter) and QLT-009 (either document or delete the two unused enum families).
Pure deletion; verify that `uv run ruff check src/ tests/` still reports the same single
diagnostic it does today, and nothing more. QLT-010's tag fix belongs here too.

**Step 5 — the client-tier fix.** QLT-007: replace the tautological `enums.test.ts` with a
cross-tier membership check and narrow the barmode cast at `ChartRenderer.tsx:149`. Verify with
`npm run lint && npm run build && npm run test` from `frontend/`.

**Step 6 — the type-width and duplication cleanups.** QLT-006 (module-scope imports plus real
annotations in `deps.py`) and QLT-008 (delete the two inline accessible-set blocks, add one shared
dependency). Both are mechanical and change no behaviour; run last so they are not interleaved with
the behavioural fixes in steps 1-2, which touch adjacent files.

## Rollout Safety

Steps 1, 2 and 3 change observable behaviour and are the ones needing care.

**Step 1** changes what `POST /dashboards/{id}/access` does on a second call for the same
`(user_id, dashboard_id)` pair. Today any deployment in which a grant was changed after creation is
running with the old permission stored, and any operator who believed they had downgraded a grant
has been wrong; step 1 makes the API honest and does not retroactively change any stored row. The
risk runs the other way: if a deployment did depend on the no-op, step 1 starts applying downgrades
it previously ignored. Grep `dashboard_access` for grants that must stay elevated before merging.
Typing the four `str` declarations to `DashboardPermission` narrows what the endpoint accepts, so
any client sending `read`/`write` — accepted today on this endpoint only — will start receiving
422; the frontend sends none (QLT-007's census puts `DashboardPermission` at five client
references, all three canonical values). Revert by reverting the commit; no data migration is
involved and no stored row is rewritten by the fix.

**Step 2** turns a 200 into a 403 for every caller that is not the owner or an administrator. That
is the intended correction, but it is the one change that can break a working client flow: any
workflow that provisions dashboard access with a non-admin token will start failing. That path is
already a privilege escalation, so treat any such caller as a defect to fix rather than a client to
accommodate. Verify by replaying QLT-002's Evidence after the change: the `viewer`-token grant must
return 403 and `dashboard_access` must gain no row. Revert by reverting the commit.

**Step 3** changes only what the contributor sees, not what the application does — except that
adding `alembic check` to `Invoke-Check` makes the gate fail on any branch where the models and the
chain already disagree. That is the gate doing its job; `alembic check` is clean at this baseline,
so on `b23a9cb` and every commit leading to it it adds no failure. Do not add it to the `migrate`
service: that service must remain able to run against a drifted database in order to repair it.

Steps 4, 5 and 6 change no runtime behaviour. Step 4's formatter decision is the only one with a
choice: deleting the black and isort configuration is safe today because no gate invokes them, and
unsafe the moment someone adds one.

## Appendices

### A — Baseline and drift reconciliation

`git rev-parse HEAD` at the start of the phase: `b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd`.
`git status --porcelain` showed a dirty tree consisting only of deleted `.ai/` scaffolding
(`D .ai/builders/**`, `D .ai/structure/**`, `D .ai/models/**`, `D .ai/plans/**`,
`D .ai/templates/**`, `D .ai/audit/templates/audit-final-report.md`) and untracked audit output
directories. The `_b3_full_out.txt` named in the phase brief was not present in `git status` at
this baseline.

Re-verified after all runtime work: HEAD unchanged, and
`git status --porcelain -- src/ frontend/ pyproject.toml Makefile.ps1 alembic/` returned empty.
**No file this phase audited changed under it**, so every anchor in this report resolves at the
recorded baseline. The two failing gates in QLT-003 are therefore properties of committed code, not
of the concurrent remediation programme; both files (`services/processing_log_service.py`,
`workers/data_worker.py`) last changed in `40866f1` and `c15707b`, both older than the remediation
series that begins at `8505a62`.

The dev stack was started with the documented `.\Makefile.ps1 up` (dev project `mkobi`, app on host
port 8010) and was **left running**; `.\Makefile.ps1 down` stops it. Probe data created during
reproduction — dashboards named `audit-probe-*`, `audit-clean-*`, `audit-x-*`, `audit-q-*`, users
`audit-viewer-*@example.com` and `audit-*-@example.com`, and the `dashboard_access` rows for them —
remains in the `bidb` development database. `.\Makefile.ps1 fullclean` removes the volume.

### B — Per-block coverage record

Every block was executed; blocks that produced no finding are recorded with the evidence that
discharged them, as the phase requires.

| Block | Method | Result |
|---|---|---|
| 1 — Fixed values | Reference census over all 18 StrEnum families × {`src/`, `tests/`, `frontend/src/`}; raw-literal grouping by surface; cross-tier equality search; live `/openapi.json` for the published shapes | QLT-001, QLT-007, QLT-010 |
| 2 — Constant surface | Numbering and membership read of `models/enums.py`; membership provenance per family; export-list contents of four `__init__.py` files; duplicate-implementation search for each mapping; value-table placement search | QLT-009. **Discharged with no finding:** no private name in any export list (67 / 16 / 5 / 0 entries checked); `ProcessingStatus.valid_transitions()` has one caller (`services/processing_log_service.py:37`) and one implementation; `AGG_FUNC_MAP` (`data/processing/aggregate_transforms.py:16`) is module-level and not rebuilt inside its consumer |
| 3 — Boundary validation | Inventory of every request-body model and its validation verdict; absent-key semantics traced for all five update paths; free-form document boundary identified | QLT-001 (boundary half). **Discharged with no finding:** every update path preserves absent keys — `dashboards_crud.py:373` uses `model_dump(exclude_unset=True)`, `layout_service.py:147-150` uses it plus a `None` filter, `filter_service.py:204-214` rebuilds the dict from `is not None` checks, `graph_service.py:145-156` likewise, and the fifth (`users`) takes a required single field. No model declares `extra` — that is EXT's finding (phase 07), cross-referenced and not re-filed. The upload boundary's free-form CSV is phase 05's |
| 4 — Type width and suppressions | mypy configuration read and each disabled class given the project's recorded reason; suppression population enumerated; annotation census over all 676 functions and classes in `src/mkobi/` | QLT-006. **Discharged with no finding:** the inline `# type: ignore` population is 3, all `prop-decorator`/`name-defined` on SQLAlchemy relationships and each still warranted; the untyped-def population is 1 of 676 (`db/models/aggregated_data.py:32`, an SQLAlchemy dialect hook), so `disallow_untyped_defs = false` silences nothing measurable; `mkobi.db.models.*` and `mkobi.interfaces.*` are off by configuration, not by annotation, and were therefore not classified individually |
| 5 — Responsibility inside a unit | Size ranking of all backend and frontend modules; responsibility enumeration for the four largest in scope | QLT-008. **Discharged with no finding:** `api/deps.py` (701 lines, 35 symbols) is 35 single-purpose dependency providers of 10-15 lines each — a size signal with nothing behind it, recorded as a result rather than a finding. `config.py` (820) and `db/starter.py` (368) were excluded from the responsibility enumeration because both are under active edit by the concurrent programme |
| 6 — One rule, one home | Rule set derived from the code (access authorization, permission vocabulary, permission ordering, role ordering, processing-status transitions, aggregation-function dispatch, layout lookups, available-dashboard filtering); normalised duplicate scan at 8, 5 and 4 lines over all of `src/mkobi/` | QLT-001 (alias and ordering rules), QLT-008. **Discharged with no finding:** two scan hits were classified false positives (`TYPE_CHECKING` vs real imports; protocol declaration vs implementation signature) and are named in QLT-008's evidence so a later pass does not re-file them |
| 7 — Convention compliance | Sweep of `print(`, `sys.stdout`, Cyrillic in `src/` and `frontend/src/`, and every function-level import; declared-rule inventory with a path-exists verdict for each | QLT-005. **Discharged with no finding:** zero `print(` in `src/mkobi/`; the only `sys.stdout` reference is the legitimate `ext://sys.stdout` handler target at `core/logging_config.py:107`; both Cyrillic hits are false positives — `services/filter_service.py:299` is a deliberate Cyrillic character class `а-яА-Я` inside a filter-name validator (data, not prose) and `frontend/src/shared/api/__tests__/errorMessages.test.ts:132` is the project's own English-only guard. `api/routes/filters.py` is a 6-line tombstone whose removal reason is recorded in its own docstring |
| 8 — Declared contracts | Inventory of every docstring, route `description`, guard comment and startup self-check, each resolved to an enforcement point or its absence | QLT-002. **Discharged with no finding:** `ProcessingStatus.valid_transitions()` is reached from `processing_log_service.py:37` and raises `INVALID_TRANSITION`; the all-or-nothing claim is genuinely honoured on the paths that use `session.begin()` (the paths that do not are phase 03's TXN-001). `REQUIRED_MODULES` is EXT's finding (phase 07) |
| 9 — Declared gates | Gate inventory from `Makefile.ps1:194-249`, `frontend/package.json:6-13`, `pyproject.toml:189-212`, `frontend/vite.config.ts:52-66` and `docker/Dockerfile`; each executed or read to establish what it decides | QLT-003. **Discharged with no finding:** the 65 % coverage floor is live, not inert — `pyproject.toml:196` passes `--cov-fail-under=65` without `--cov`, but pytest-cov 7.1.0 constructs its `CovController` at `pytest_configure` regardless of `--cov` and sources measurement from `[tool.coverage.run] source = ["src/mkobi"]`, so `pytest` under `Makefile.ps1:196` does enforce it (`pytest_cov/plugin.py:225-254`, `:369-376`). Both vitest thresholds and the pytest floor are fixed numbers rather than deltas — recorded here as the block's threshold observation, not filed, because what the suite would notice is phase 09's |
| 10 — Schema drift | Drift-check inventory; `alembic check` executed against the dev database; idempotency of every boot-time row-writing path tested by row counts across a restart | QLT-004. **Discharged with no finding:** no drift exists today (`alembic check` → `No new upgrade operations detected.`), and the boot-time writers are idempotent — row counts across `.\Makefile.ps1 restart` were identical before and after (`users=6 dashboards=7 access=8 regreq=8 logs=3`), so the admin bootstrap and the dev seeders neither duplicate nor mutate on a second run. The *population* of such paths is phase 01's; the chain's linearity and reversibility are phase 14's |

### C — Cross-phase cross-references

| This report | Cross-reference | Relationship |
|---|---|---|
| QLT-001 (boundary half) | Phase 07 — 0 of 21 request-body models declare `extra` | Same subject, different claim. EXT establishes the unknown-key policy; QLT-001 establishes that the one boundary whose field carries a bare `str` with a legal-value default accepts a value and reports a write it does not perform. Adjacent, not merged |
| QLT-005 (`pandas-stubs`) | AGENTS.md "**Запрещено:** pandas" | The project rule names the library; the finding is that a stub for it is installed |
| QLT-004 | Phase 14 — migration chain linearity and reversibility | Complementary. QLT-004 owns whether anything compares the models to the chain; phase 14 owns the chain itself |
| QLT-001, QLT-002 (authorization half) | Phase 12 — the access decision and refusal shape | QLT-002 files only the contradiction between the declared audience and the executing path; phase 12 owns whether the access decision itself is correct and what a refusal should disclose |
| QLT-003 | Phase 09 — test coverage | QLT-003 files only that the declared gates are red and unreachable through the aggregate entry point; what the suite would notice is phase 09's |
| QLT-005 (`interfaces_old` ignore), QLT-003 gate reachability | TOPO-007 — `alembic/env.py` sits outside both quality gates | Same subject, adjacent. TOPO-007 established that widening the ruff gate lands red on four pre-existing `UP007`/`UP035` violations in `alembic/versions/` while `mypy alembic/env.py` is clean. QLT-003 observes the same `pyproject.toml:169` exclusion from the gate's side and does not re-file the widening decision |
| QLT-007 (`RegistrationStatus` absent from the mapping) | Phases 01 and 06 | No overlap; cited only to record that the census was checked against those phases' scopes and nothing was duplicated |

### D — Artefacts consulted

`pyproject.toml`; `Makefile.ps1` (all 38 targets and the dispatch table); `docker/Dockerfile` (41
`RUN`/`CMD`/`HEALTHCHECK` lines); `alembic/env.py`; `frontend/package.json`;
`frontend/eslint.config.js`; `frontend/tsconfig.app.json`; `frontend/vite.config.ts`;
`src/mkobi/models/enums.py`; `models/{user,access,dashboard,graph,layout,processing_configs,filters}.py`;
`core/permissions.py`; `core/logging_config.py`; `services/dashboard_service.py`;
`db/repositories/access_repo.py`; `db/models/access.py`; `db/starter.py`; `api/deps.py`;
`api/routes/{dashboards,dashboards_access,graphs,layouts,admin,auth,filters}.py`;
`api/routes/__init__.py`; `frontend/src/shared/types/enums.ts`;
`frontend/src/shared/types/__tests__/enums.test.ts`;
`frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx`;
`tests/test_enum_db_consistency.py`; `pytest_cov/plugin.py:225-254` and `:369-376`;
live `GET /openapi.json` (43 paths, 60 operations); live `GET /health`; and the
`dashboard_access` and row-count queries run against `bidb`.
