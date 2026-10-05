---
phase: 16-chart-presentation-contract
role: residual execution map (supersedes the block graph of 16-chart-presentation-contract-remediation-execution.md)
plan_of_record: .ai/plans/16-chart-presentation-contract-remediation-execution.md
code_context:
  - .ai/plans/_code-context/16-phase16-drift-backend.md
  - .ai/plans/_code-context/16-phase16-drift-frontend.md
plan_authored_at: 907e052
tree_at_audit: d6505b1
drift_commits: 215
status: residual map derived — the original 10-block graph no longer describes the tree
---

# Phase 16 — residual execution map

## Why this file exists

`16-chart-presentation-contract-remediation-execution.md` was authored at `907e052`. The tree has
since moved **215 commits** to `d6505b1`, and a large part of the plan's cross-phase dependencies
**have landed**. The plan's block graph, its baselines and several of its premises no longer
describe the repository. This file records what is actually left, in dependency order, and nothing
else. The plan of record stays where it is as the historical artefact; **this file is the execution
map**.

Two drift audits re-derived every anchor by symbol:
`.ai/plans/_code-context/16-phase16-drift-backend.md` and
`.../16-phase16-drift-frontend.md`.

## What already landed — do not re-implement

| Plan block | State | Evidence |
| --- | --- | --- |
| **`CHTB-1` backend contract** | **LANDED** | `3f01601` — `GraphConfigDict` widened 11 → **15** keys; `GraphCreate`/`GraphUpdate` refuse undeclared nested keys **by name**. `2f3cc1a` added `extra="forbid"` at the model top level. |
| **`CHT-002`'s deletion hazard (`C16-2`)** | **VOID** | `f500d1f` took phase 13's `CT-7` option (b) — narrow the types. `convertChartLayoutToPlotly` **still exists**. |
| **`CHTB-3`'s three lint assertions** | **VOID** | `f500d1f` replaced them with one `as unknown as Template` in a new `chartConversion.ts`. **`fe-lint` is green (0 errors)**, baseline was 9. |
| **`CHTB-5` truncation half** | **LANDED, schema-pinned** | `5ca453f`, `05a06a0`, `c01bacd` — `GraphDataResponse.returned_rows` / `.total_rows` / `.rows_truncated` + dashboard-wide `AggregatedDataResponse.total_rows` / `.truncated`; `DashboardView` renders "Showing N of M". Pinned by `tests/test_openapi.py::TestAggregatedDataResponseCarriesTruncationContract`. |
| **`CHTB-4`'s `[0]`-nondeterminism rationale** | **VOID** | `660b6d5` added `ORDER BY aggregated_data.id` to all three read methods. |
| **`CHTB-9`** | **NO WORK** | `D-16-5` and `D-16-8` are both ruled; a ruling records, it does not build. |
| **`D-16-6`** | **MOOT** | `d059b16` (phase 12's `AZ-8`) touched `api/routes/data.py` only — **neither `models/data.py` nor a construction site**. The premise it arbitrated no longer exists. |

## Premises that were wrong

1. **`CHT-009` does not "silently return zero rows" today.** `a34b56b` introduced
   `models/data.py::AggregatedFiltersRequest` with `filters: dict[str, str | int | float | bool]` and
   `extra="forbid"`. `DashboardFilters.tsx` sends `string[]` for `multiselect` and `[number, number]`
   for `range`. **The live defect is a dashboard-scope 422 that blanks every chart on the page**, and a
   repository-level shape branch is **unreachable** until the boundary model widens.
2. **`GraphDataResponse` has nine declared fields, not six.** The count fields landed.
3. **`fe-lint` is green**, so `check` no longer short-circuits at `fe-lint`.
4. **`frontend/coverage/` is untracked *and* gitignored** (`e4bd273`, anchored by `9d39218`). It is a
   normal build artefact; phase 13's `CT-15` "must stay deleted" instruction is meaningless now.
5. **The frontend baseline is 24 files / 196 tests**, and `ChartRenderer.test.tsx` **exists**. A green
   `fe-test` is still not evidence — `LineChart.tsx` and `TableChart.tsx` have **zero** coverage.
6. **`tests/test_aggregated_read_path.py::TestAggregateResponseShape` uses an exact key-set assertion.**
   It is the one backend test that **must** change for `CHTB-2`, and the plan never names it.
7. **The audit corpus is gone** (`d6505b1` committed `.ai/audit/**`'s deletion). Every plan anchor
   pointing at `.ai/audit/16-…` is dangling. No finding may be re-derived from it.

## Residual blocks — the queue

| # | Block | Discharges | Depends on | Agents |
| --- | --- | --- | --- | --- |
| **1** | **R1 — `CHTB-1` residual**: round-trip acceptance assertion (`create → read → update → read` **unchanged**), the **reserved** reclassification in `GraphConfigDict`'s docstring for `yoy / secondary_y / xaxis / yaxis / layout / sort_x / sort_color`, the client mirror parity for `api.types.ts::GraphDataWithConfig.config`, and `OrientationEnum` out of `SERVER_ONLY_FAMILIES` | `CHT-001`'s acceptance criterion (i), `CHT-004`'s reserved half | — | Planner (short) · Implementor · Validator |
| **2** | **R2 — `CHTB-3`**: populate `layout` at **both** construction sites, merge `xaxis` in the bar branch, correct the false `json_schema_extra` and class docstring, **one commit, never revertible by half** (`VAL-16-003`) | `CHT-006`, `CHT-002` | — | Planner (commit shape) · Implementor · Validator |
| **3** | **R3 — `CHTB-2`**: `metrics` / `dimensions` on `GraphDataResponse`, populated at both sites, **correct by construction** | `CHT-003`, the structural half of `CHT-001` | Researcher (the `_{agg}` derivation) · Planner · Implementor · Validator |
| **4** | **R4 — `CHTB-4`**: pie `labels`/`values` and no `x`/`y`; the line branch renders **all** traces; `LineChartProps.data: Data[]`; wire or delete `title`/`xAxisLabel`/`yAxisLabel`; deterministic group order | `CHT-007`, `CHT-008` (presentation half) | **R1 and R3** (hard — an all-zero pie is worse than an empty one) | Planner · Implementor · Validator |
| **5** | **R5 — `CHTB-6`**: `multiselect` binding (boundary widened **or** the contract deliberately refused — Researcher decides), `range` **removed** per `D-16-2`(B) with a stored-filter rejection naming the reason, no dashboard-scope blast radius | `CHT-009` | Researcher (JSONB membership, PG 18, GIN) · Planner · Implementor · Validator |
| **6** | **R6 — `CHTB-5`**: **absent distinguishable from zero on the wire**; the four empty/absent states (`D-16-4`); `P13`'s stale marker as a **fifth** state, not an empty state | the `?? 0` collapse; three empty states | R3 (soft — the expected measure comes from the served list) | Planner · Implementor · Validator |
| **7** | **R7 — `CHTB-7`**: invalidate `['filterValues', …]` on upload **and** pin `staleTime: Infinity`; **exactly one** invalidation site names the key | `CHT-010`, `D-16-7`(B) | — | Planner (short) · Implementor · Validator |
| **8** | **R8 — `CHTB-8`**: the documentation, written once against final code | the documentation halves of `CHT-004`, `CHT-006`, `CHT-001` | R1 … R7 | Doc-specialist |

`CHTB-0`'s rulings and `CHTB-9`'s rulings are already applied — recorded in the two drift audits and
in the plan of record. Neither is work.

## The one business question this phase cannot answer for itself

**`P12` presupposes a screen that does not exist.** The ruling reads *"the graph settings screen shows
the axis type explicitly and allows editing it."* `frontend/src` has **no graph write path at all**:
no route, no API client, no form. `app/routes.tsx::AppRoutes` declares `/login`, `/register`,
`/dashboards`, `/dashboard/:id`, `/admin`, `/profile`, `/profile/change-password`. Every one of the 31
`graph_id` references in the frontend is a **read**.

Building one is greenfield UI plus a new API client — a scope this remediation phase does not have and
the project rules discourage. **`P12` is recorded as a hand-over, not built.** The consequence is
stated rather than hidden: `D-16-3`'s `'category'` default becomes effectively permanent in-tree,
because a stored value a user cannot set is a constant with extra steps.

## Execution log

| Block | Commit | Validator verdict |
| --- | --- | --- |
| **R1** — `CHTB-1` residual | `716c755` | **ACCEPT** — round-trip assertion is non-vacuous (hand-written vocabulary literal); reserved classification verified true against the tree |
| **R2** — `CHTB-3` | `a306981` | **ACCEPT** — both halves in one commit; neither half can be dropped silently (probe-verified) |

## Corrections to the plan's tooling — binding on every remaining block

**The plan's frontend test command does not work in this environment.** Verified by R2's validator:

```powershell
# BROKEN - vitest resolves its root to the REPO ROOT, never loads frontend/vite.config.ts,
# runs in the node environment, and every test (including untouched files) fails on
# ReferenceError: document is not defined
npm --prefix frontend exec -- vitest run <path>

# CORRECT - minimal edit, working directory unchanged
npm --prefix frontend exec -- vitest run --root frontend <path>
```

The jsdom environment lives in `frontend/vite.config.ts`; there is no `vitest.config.ts` anywhere.
`npm exec --prefix` does not change the child's cwd. The plan repeats the broken form in at least
six places. **A 38/39 red from that form is a tooling artefact, not a regression.**

**Full frontend suite:** `.\Makefile.ps1 fe-test` — **24 files / 198 passed** at `a306981`.
**Frontend typecheck:** no target exists; `npm --prefix frontend run build` (writes the gitignored
`frontend/dist`). **Full backend suite:** 1644 passed at `a306981`. **`fe-lint`: 0 errors.**

## Findings filed for later blocks

- **→ `R4`.** `ChartRenderer.test.tsx`'s `VAL-16-006` tripwire inspects `lastLineProps().layout`, so
  re-stating the defaults as **props** (`<LineChart xAxisLabel="Category" />` — the idiomatic way to
  write the mistake) survives. Assert on `lastLineProps()` itself. No defect ships today; the
  protection is weaker than the test's shape implies.
- **→ `R6`.** A graph whose metric matches no source column is **not** absent from the response: the
  endpoint enumerates the `graphs` table, so it **appears with `data: []`**. The plan's "no card at
  all" premise for the absent-graph state must be re-derived before that block is designed.
- **→ general.** `ProcessingConfigService.upsert` writes `metric_agg` **without re-aggregating**, so a
  naming rule derived from the current config can disagree with the stored rows. Names must be read
  off the data that is actually served.
- **→ `R8`.** `tests/test_request_boundary_extra_forbid.py` carries a docstring claiming the ORM
  `Graph` supplies `updated_at`; it does not.

## Standing constraints for every residual block

- **One implementor at a time.** Each block commits on its own.
- **Never `git reset` / `git checkout`.** `frontend/src/shared/types/api.types.ts` carries an
  **uncommitted change by another agent** (`FilterValuesResponse.total_values`); the server already
  serves it (`api/routes/filter_values.py::get_filter_values_endpoint`). Do not edit that line; do not
  commit it.
- **Do not restore, delete or commit `frontend/coverage/`.** It is now gitignored and normal.
- **No browser-render claim.** There is no render harness; evidence stops at the emitted trace and
  layout objects.
- **`D-16-4`'s release note must state the affected-dashboard count as UNKNOWN, never estimated.**
- **`docs/00-overview/doc-maintenance-rules.md` governs R8** — frontmatter is contract, one source
  of truth, no silent dropping, English only, flat kebab-case placement.

## Block log

### 2026-10-05 — R1 (`CHTB-1` residual), Planner decisions

Scope executed: the two items the block names — criterion (i) of `D-16-1` and the **reserved**
reclassification. Criterion (ii) stays with `R4`.

1. **Criterion (i) lands in `tests/test_graphs.py`, in a NEW class `TestGraphConfigRoundTrip`** —
   not beside its siblings in `TestGraphConfigNestedVocabulary`, and not appended to
   `TestGraphsAPI`. Three reasons, in order of weight:
   * `POST /graphs/` commits (`api/routes/graphs.py::create_graph_endpoint`), so the round trip is
     **durable**. `tests/conftest.py::async_db_session`'s own docstring says committed rows survive
     teardown and cleanup is the test's job; the two helpers that do it,
     `tests/test_graphs.py::_delete_committed_graph` and `::_count_committed_graphs`, exist **only**
     in that module. `TestGraphConfigNestedVocabulary` has no durable-write harness — its one route
     test ends in a 422, so nothing is ever committed.
   * The property is **persistence + serialization**, not *boundary refusal*. That module's stated
     subject is the `extra="forbid"` request-boundary policy; a round trip does not belong to it.
   * A named class keeps it independently reviewable and re-runnable, matching the module's existing
     two-class layout and `TestDashboardGraphCreateAudience`'s precedent.
   `TestGraphConfigNestedVocabulary` keeps its six refusal/acceptance tests and is **not touched**:
   "which keys are accepted" and "does a config survive the cycle" are two different questions.

2. **The vocabulary literal lives in the same new class.** `TestGraphConfigRoundTrip` declares a
   literal fifteen-name frozenset and asserts it equals `frozenset(GraphConfigDict.__annotations__)`
   and `set(GraphConfigModel.model_fields)`. Without that literal the round-trip assertion would
   shrink with the vocabulary and prove nothing; this is the same anti-drift pattern the boundary
   module already uses for `DECLARED_GRAPH_CREATE_KEYS`.

3. **The reserved statement's home is `GraphConfigDict`'s docstring, and nowhere else.**
   `GraphConfigDict` is the SSOT for the declared vocabulary, so the full **RESERVED** statement
   goes there; `GraphConfigModel`'s docstring gets one pointer sentence, **not** a duplicated list
   (single source of truth). Each reserved key additionally carries a `RESERVED:` inline comment, so
   the statement is visible at the declaration and not only in a header. The two sets the wording
   must name are fixed by the adjudicated register: contract = `x, y, color, metrics, orientation,
   barmode, title, showlegend`; reserved = `yoy, secondary_y, xaxis, yaxis, layout, sort_x,
   sort_color`. **No annotation is added, removed or retyped** — `_DECLARED_GRAPH_CONFIG_KEYS` stays
   as computed.

4. **Filed, not done: the client mirror.** `frontend/src/shared/types/api.types.ts::GraphDataWithConfig.config`
   still declares five keys and needs the same reserved wording. Out of scope here — that file
   carries another agent's uncommitted edit (`FilterValuesResponse.total_values`). Owner: `R8`,
   alongside the `CHTB-1` documentation half.

5. **Gap flagged: `OrientationEnum` is still in `SERVER_ONLY_FAMILIES`.** The R1 row of the queue
   table above lists "and `OrientationEnum` out of `SERVER_ONLY_FAMILIES`" as part of R1, but this
   block's brief scopes R1 to the two items above and fences all client-side work as a filed
   coordination item. **Not performed.** It is a genuine residual with no owner now: the change is
   `frontend/src/shared/types/enums.ts` (add the `OrientationEnum` mirror, drop the name from
   `SERVER_ONLY_FAMILIES`) plus `shared/types/__tests__/enums.test.ts`, whose exact-set assertions
   are what force the placement to be declared. Neither file is `api.types.ts`, so the edit is not
   blocked — it is simply not this block. Recommend `R4`, which owns the renderer's `orientation`
   handling and is the block that would consume the mirror, or `R8`. **This row needs correcting
   before the queue is worked.**

### 2026-10-05 — R1 (`CHTB-1` residual), Implementor decisions

Scope executed: exactly three files — `src/mkobi/models/types.py` (docstrings and `#`-comments
only), `tests/test_graphs.py` (new constants and the new class `TestGraphConfigRoundTrip`), and this
entry. No annotation, validator, `model_config`, route, service or repository changed; production
behaviour is unchanged.

1. **Criterion (i) landed in `tests/test_graphs.py::TestGraphConfigRoundTrip`, as planned.** The
   round trip drives `POST /graphs/` → `GET` → `PUT` → `GET` over HTTP with `authenticated_client`,
   because `POST /graphs/` commits and the cleanup helpers (`_delete_committed_graph`,
   `_count_committed_graphs`) live only in that module. Every leg asserts deep equality against
   `FULL_GRAPH_CONFIG` and the exact key set against the hand-written
   `EXPECTED_GRAPH_CONFIG_KEYS` literal; the `PUT` sends the config the preceding `GET` returned.
   `TestGraphsAPI` and `TestDashboardGraphCreateAudience` are byte-unchanged.

2. **The vocabulary literal is the anti-drift pin.** `test_declared_vocabulary_is_the_published_graph_config_contract`
   asserts `frozenset(GraphConfigDict.__annotations__)` and `frozenset(GraphConfigModel.model_fields)`
   both equal `EXPECTED_GRAPH_CONFIG_KEYS`, that
   `EXPECTED_GRAPH_CONFIG_KEYS - RESERVED_GRAPH_CONFIG_KEYS` is the eight contract keys, and the
   `GraphConfigDict`/`GraphConfigModel` mirror invariant. Hand-writing the set is what stops the
   round-trip test from shrinking with the source it guards (the `f500d1f` failure shape).

3. **The seven unrendered keys are reclassified RESERVED in `GraphConfigDict`'s docstring**, with the
   classification attributed to `D-16-1`; each reserved key carries a `RESERVED:` inline comment;
   `GraphConfigModel`'s docstring gains one pointer sentence only, not a duplicated list. Named
   server/client readers: `aggregation_service` reads `x`/`color`; `ChartRenderer` reads `x`, `color`,
   `metrics`, `orientation`, `barmode`. `layout` and `xaxis` are owned by `R2`; the rest have no
   consumer yet. `title`/`showlegend` are config-level twins of `ChartLayoutConfig.title`/`.showlegend`,
   which the renderer reads off the response's `layout` field (populated by `R2`).

4. **Discrimination probes — actual outcomes.**
   - **Probe 1 (narrowing: delete `barmode`): both tests FAIL.** Round trip `assert 422 == 201`; the
     vocabulary test reports `barmode` as an extra item in the literal. Discriminates as predicted.
   - **Probe 2 (update-side asymmetry: `GraphUpdate` accepts everything while `GraphCreate` still
     refuses): the round-trip test PASSES.** Honest negative result, as the plan itself predicted:
     5.1 sends a server-produced, all-declared config, so an update-side refusal cannot fire on it.
     Symmetry is pinned from the refusal side by `test_declared_vocabulary_*` and the sibling
     boundary tests, not by 5.1.
   - **Probe 3 (read-side: `extra="forbid"` on `GraphRead`): the round-trip test PASSES — the plan's
     prediction did not hold.** FINDING. The forbid **does** propagate into the nested
     `GraphConfigDict` (verified directly: `GraphRead(**{..., "config": {"x": "a",
     "undeclared_key": "boom"}})` raises `extra_forbidden` at `config.undeclared_key`), and without
     the forbid an undeclared stored key **is** silently dropped (verified directly:
     `undeclared_key not in model.config()` is `True`). But the round-trip test stores only the
     fifteen declared keys, so a read-side forbid has nothing to reject and the test still passes.
     The probe therefore does not demonstrate the test protecting the read path; it only confirms the
     model-level hazard the plan describes. The plan instructed "stop and report" if probe 3 does not
     fail; the test is not adjusted, and this is reported as the finding. `GraphRead` keeps no forbid
     (reverted; `git diff --stat src/mkobi/models/graph.py` is empty).

5. **Criterion (ii) stays with `R4`** (`ChartRenderer.test.tsx`); it was not written or stubbed.

6. **Client mirror parity remains filed for `R8`**, not done:
   `frontend/src/shared/types/api.types.ts::GraphDataWithConfig.config` needs the same reserved
   wording. That file carries another agent's uncommitted edit and is **not staged** by this block.

### 2026-10-05 — R2 (`CHTB-3`), Planner decisions

Scope executed: populate `models/data.py::GraphDataResponse.layout` at both construction sites,
merge the bar branch's axis object, **one commit, never revertible by half** (`VAL-16-003`).

1. **The served `layout` is `graph.config["layout"]` as stored. `config.xaxis` / `config.yaxis` are
   NOT lifted into it.** Reasons, in order of weight:
   * Lifting means inventing a precedence rule among five sibling config keys (`title`, `showlegend`,
     `xaxis`, `yaxis`, `layout`) that carries the same meaning. Nothing in the repository exercises
     such a rule and no ruling covers it; writing one is the speculative redesign this phase forbids.
   * It would create a **second naming path for the same value** — `config.xaxis` *and*
     `config.layout.xaxis` — and `D-16-1` deliberately kept these keys RESERVED, i.e. kept and
     unwired. Wiring one of them re-opens an adjudicated decision from inside a different block.
   * `P12`'s consequence decides it: nothing in this repository can write `config.xaxis` (there is no
     graph write path at all), so lifting wires a path with no producer — a constant with extra steps.
     `models/types.py::GraphConfigDict`'s docstring is the honest place for that, and this block
     updates it because R2 is what makes its `layout` clause true or false.
   * **Trade-off accepted, stated not hidden:** a graph whose stored config carries `xaxis`/`yaxis`
     but no `layout` still has them ignored after R2. That is pinned by a test on purpose, so a later
     block that *does* lift fails loudly instead of silently changing what a chart draws.

2. **The derivation lives in a module-level private helper in `src/mkobi/api/routes/data.py`, beside
   `_flatten_points` — not in a service, not in a repository.** Reasons:
   * It is a projection of a column that is **already loaded** on the `Graph` ORM entity both
     construction sites already read (`config=` is passed from it). No SQL, no query, no business rule.
   * `API → Service → Repository` governs data access and business logic. A `DataService` method here
     would have to accept the `Graph` **ORM entity** as input — pushing an ORM object down a layer and
     adding a hop for no access — and the repository is plainly wrong (it owns `aggregated_data` reads).
   * The **precedent is in this very file**: `_flatten_points` is exactly this kind of
     response-shaping transform and already lives in the route module. Following the established
     pattern beats inventing a layer.
   * "Written twice or factored once" resolves to a **helper**, not a service: one small function, two
     call sites. If a later block's layout ever depends on server-computed state (`R5`'s filter-driven
     `range`, `R6`'s empty-state marker), the derivation **moves** to the service — filed as a
     coordination note for those blocks, not built here.

3. **Two traps found while deriving this, both of which change the required work:**
   * **The ruled literal `{type: 'category', ...convertedLayout?.xaxis}` does not work as written.**
     `chartConversion.ts::toLayoutAxis` emits `type` **unconditionally** (`type: toAxisType(...)`),
     so a stored axis with no `type` yields `{type: undefined}` and the spread **overwrites the
     `'category'` default with `undefined`** — the exact thing `D-16-3` rules must survive. The fix is
     at the root: `toLayoutAxis` omits absent members instead of emitting explicit-`undefined` ones.
     On the wire this is a no-op (undefined members never serialise); it only decides whether a
     default written before a spread survives. **No cast, no `any`;** if the compiler refuses the
     inline literal, bind the merged axis to a typed `const` first.
   * **`tests/test_graphs.py::RESERVED_GRAPH_CONFIG_KEYS` pins the classification as a literal**, and
     its comment states the seven keys are "read by nothing in `src/` or `frontend/src/` today". R2
     makes that false for `layout`, so the literal loses `layout` and the expected contract set in
     `test_declared_vocabulary_is_the_published_graph_config_contract` gains it (nine keys). That
     pin was installed by `R1` precisely so a classification change fails loudly — using it is the
     design working, not a regression. `GraphConfigDict`'s docstring moves in the same commit.

4. **No client mirror change is needed at all.** `api.types.ts::GraphDataWithConfig` already declares
   `layout?: ChartLayoutConfig`, and `ChartLayoutConfig` already declares the seven members. R1's
   "client mirror parity" filing is about the *reserved wording* on `config`, not this block. The file
   stays untouched and unstaged. `AxisConfig.label` is named RESERVED in the backend docstring with
   its reason; its `api.types.ts` mirror is filed for `R8`.

5. **Filed for `R8`, not done here:** `api/routes/data.py::get_aggregated_data_endpoint`'s own
   `Response format:` sketch still omits `layout` (and `config` and the count fields — it is an
   abbreviated line, not a false one, and completing it is a documentation pass); the `docs/` halves of
   `CHT-006`; `api.types.ts::AxisConfig.label`'s mirror. No `docs/` file is edited by this block.

### 2026-10-05 — R3 (`CHTB-2`), Planner decisions

Scope executed: serve the **stored** measure and dimension names with the aggregate rows —
`GraphDataResponse.metrics` / `.dimensions`, read off the `AggregatedData` rows that produced the
response, in `DataService.get_bounded_aggregated_data`. Executed per
`.ai/plans/_code-context/16-phase16-r3-naming-research.md`.

1. **Return shape: a plain 4-tuple `tuple[list[ProcessingResultData], int, list[str], list[str]]`.**
   The method already returns a positional 2-tuple for the same "payload + true total" reason, and the
   exact semantic sibling `FilterValuesService.get_filter_values -> tuple[list[str], int]` feeds an
   additive response model the same way; `data/loaders/validator.py` already returns same-typed
   `list[str]` pairs positionally. **Rejected:** a `NamedTuple` (zero occurrences in `src/` — a new
   type for two call sites, against "no new abstractions without strong justification"); a dataclass
   (heavier than a `NamedTuple` for a pure return record, and Pydantic models here are response DTOs);
   `dict[str, list[str]]` (project rule: no dicts where a type belongs); adding the names to
   `ProcessingResultData` (leaks response shape into the worker payload type, which has no
   `dims`/`metrics` split). The one ambiguity a 4-tuple introduces — two same-typed `list[str]` slots —
   is caught by this block's own tests, which assert `metrics == ["revenue"]` and
   `dimensions == ["category"]` **separately**, so a swap is a red test, not a silent green.

2. **`dimensions` IS in scope.** It is free from the same already-loaded `record.dims` read, it closes
   the axis-name half of the identical guess (`config.x ?? 'x'`), and the `R3` row of the queue table
   above already names both fields — so this is the block as specified, not an extension. The
   acceptance criterion is symmetric: a served dimension list must likewise appear as keys on a served
   row, and that symmetry is pinned by its own test.

3. **Both fields are optional with an empty default** (`Field(default_factory=list)`), so they stay out
   of the OpenAPI `required` list. The default is **not** the zero-row mechanism: the derivation
   produces `[]` and both route sites pass it explicitly.

4. **Filed, not done:** `frontend/src/shared/types/api.types.ts::GraphDataWithConfig` needs
   `metrics?: string[]` / `dimensions?: string[]` before `R4` can consume them — that file carries
   another agent's uncommitted change and is **not** edited or staged here. Owner: `R4` (the consumer),
   with `R8` for the wording.
5. **Filed, not done:** `get_aggregated_data_endpoint`'s own `Response format:` sketch omits the two
   new names (and `layout` / `config` / the count fields). Owner: `R8`, per `R2`'s precedent.
6. **Drift note for later blocks:** the unbounded sibling `DataService.get_aggregated_data` merges the
   same two columns at the same spot and is deliberately left byte-unchanged (it has **no** `src/`
   caller). If a later block routes it into a response, it must reuse `R3`'s helper, not re-derive.
7. **`R6` coupling, stated in `R3`'s brief:** a non-empty served `metrics` list does **not** mean
   "this graph has data" — the two are independent signals. `R6` must not use list non-emptiness as a
   proxy for the absent-vs-zero distinction.

### 2026-10-05 — R4 (`CHTB-4`), Planner decisions

Scope executed: `chartConversion.ts::makeTrace`'s per-type trace shape, the line branch's trace set,
`LineChartProps`, and `convertToPlotlyData`'s consumption of `R3`'s served names. Hard-ordered after
`R1` and `R3`; both landed (`716c755`, `eba2348`) and are ACCEPTED.

1. **Three per-type builders behind `makeTrace`, not one builder with a `type` branch.** The split is
   forced by the shipped types, not by taste: `Partial<Data>` **cannot** carry `labels`/`values`.
   `@types/plotly.js` `PlotData` declares no `labels` and no `values`; both live on `PieData`
   (`values: Array<number | string>`, plus `"labels"` through its
   `Pick<PlotData, … | "labels" | …>`), and the only `x`/`y` in `lib/pie.d.ts` belong to `PieDomain`,
   which this code never sets. A pie trace must therefore be built as `Partial<PieData>` and a
   bar/scatter trace as `Partial<PlotData>`. `makeTrace` keeps its current signature and stays the only
   exported entry point, so **both `ChartRenderer.tsx` call sites are unchanged**; the three builders
   are module-private. `makeTrace`'s parameter type is lifted into one exported
   `ChartTraceType = 'pie' | 'scatter' | 'bar'` alias, which `traceTypeFor` also returns — four
   repetitions of the literal union is duplication a named type exists to remove. **Rejected:** a
   single builder with a `type` branch — its parameter names (`xVals`, `yVals`) would have to lie for
   the pie case, and that lie is the defect itself.

2. **The line branch renders every trace: `LineChartProps.data` widens to `Data[]`,**
   `LineChart` stops re-wrapping, and the `[0]` index is deleted. **User-visible consequence, stated
   not hidden:** a grouped-colour line graph gains one line and one legend entry per distinct colour
   value; for a high-cardinality colour column the figure becomes materially busier, and this block
   introduces **no cap** — a cap is a new policy with no adjudicated owner, and silently capping would
   recreate the "N−1 series disappear" lie at a different threshold. **Rejected:** one chart per
   trace — it changes the page's layout for a local defect and is not what the operator's stored
   `config.color` asked for. Note the bar branch already renders every group, so this makes the two
   branches consistent rather than introducing a new convention.

3. **`title` / `xAxisLabel` / `yAxisLabel` on `LineChart` are DELETED, not wired.** No file in
   `frontend/src` ever passes them; `ChartRenderer.tsx`'s line branch passes exactly `data` and
   `layout`, and the `LineChart` call sites in the three test files are mocks. Wiring them would mean
   inventing a second naming path for a title the served `layout` already carries (`R2`), i.e.
   re-opening an adjudicated decision from inside a different block; and a props surface nobody passes
   is a lie a reader will trust. **Consequence, stated:** `LineChart` reduces to a pass-through to
   `PlotlyChart`. It is **kept** regardless — `DashboardView.test.tsx` and
   `features/dashboards/__tests__/filter-persistence.test.tsx` both `vi.mock` it **by path**, so
   deleting the file would drag two out-of-scope test files into this block, and `R2`'s `VAL-16-006`
   tripwire is written against `lastLineProps()`, which requires the component to stay.
   `LineChart.tsx::convertDataToPlotlyFormat` — named in this block's brief as still hardcoding
   `type: 'bar'` — **does not exist in the tree**; `f500d1f` reduced the file to a 27-line
   pass-through. There is no typing half to decide here.

4. **The served names win, and the rule is one small helper.** `resolveColumnName(configured, served)`
   in `ChartRenderer.tsx`, private to that module: an **empty or absent** served list carries **no
   authority** (use `configured`, exactly as today); a configured name that **is** among the served
   names is used (operator intent, still correct by construction); a configured name that is **not**
   among them is **unresolved**. Then:
   * measure → `resolve(config.metrics?.[0], graph.metrics) ?? graph.metrics?.[0] ?? 'y'`
   * axis → `resolve(config.x, graph.dimensions) ?? graph.dimensions?.[0] ?? 'x'`
   * colour → `resolve(config.color, graph.dimensions)`, and **`undefined` means no grouping**
   * **Consequences, stated:** a graph whose stored `config.metrics` names the pre-alias `revenue`
     while its rows carry `revenue_sum` now draws real values instead of zeros — this is
     `D-16-1`'s **second** acceptance criterion, still outstanding; and a graph whose stored
     `config.color` names a column no served row carries stops grouping instead of emitting one
     zeroed `'unknown'`-named trace (same trace count, correct data — a strict improvement, not a new
     policy). **The colour deliberately has no served-first fallback:** guessing a different colour
     column would split the chart by a dimension the operator never chose.
   * **What an empty served list does:** nothing changes. The configured chain applies unchanged, and
     the served list's emptiness is **not** read as "no data" — `R3`'s coordination item is honoured
     literally, and `R6` owns the empty/absent states. This block must not pre-empt `R6` and must not
     change the `?? 0` fallback's semantics; it changes **which column** is read, nothing else.

5. **The empty-`data` crash is LATENT, not live — the brief's premise is refuted by symbol.**
   `ChartRenderer` returns the empty-state `div` at its `graph.data.length === 0` guard, which
   **precedes** the line branch, and `convertToPlotlyData` returns `[]` **only** under that same
   condition: the already-Plotly-shaped passthrough returns `graph.data`, the colour branch yields one
   `Map` entry per record, and the single-series branch always returns one trace — so for non-empty
   `data` it returns at least one trace. No `TypeError` is reachable at the `[0]` today. The fix is
   still correct and still in scope: the line branch stops indexing, so a function contract that now
   permits `[]` no longer has a caller that cannot tolerate it. Its test is labelled a **tripwire**, not
   a regression test, and the commit body says so.

6. **`api.types.ts` staging — resolved by construction, no escalation.** The peer's hunk
   (`FilterValuesResponse.total_values`, declared near the top of the file) and this block's hunk
   (`GraphDataWithConfig.metrics` / `.dimensions`) are roughly sixty lines apart, so the two hunks are
   independent and index-staging separates them exactly. **Primary recipe:** snapshot
   `git diff -- frontend/src/shared/types/api.types.ts` **before** editing, `git add` the file, then
   `git apply --cached -R <snapshot>` — this removes precisely the peer hunk **from the index only** and
   never touches the working tree. **Fallback if that refuses** (the file is CRLF/LF-normalised, so it
   may): `git add -p` on the file, `n` to the `total_values` hunk and `y` to the
   `GraphDataWithConfig` hunk. **Verification is mandatory either way:** `git diff --cached` shows only
   the two new members; `git diff` still shows only the peer's hunk.
   **Rejected:** deleting and restoring the peer lines — it puts another agent's uncommitted work at
   risk for a purely cosmetic convenience. **Rejected:** a separate commit that also declares
   `total_values` — that field is `R7`'s work; committing it here would put another agent's change in
   this block's diff and make it look authored and reviewed by `R4`. **Rejected:** escalation — there
   is no contention to adjudicate, the file is not a barrier to anything, and escalating would block
   the block for nothing. **Never** `git add -A` / `git add .` / `git add -- <path>` together with a
   commit: `.kilo/plans/PLAN_01.md` and `.kilo/plans/PLAN_RECOVERY.md` are deleted-but-unstaged in the
   working tree and would be swept in. Stage by explicit path and verify with `git status`.

7. **The reversed-fixture test is VOID in the plan's original form and must not be written as
   planned.** `660b6d5` made the read order server-determined
   (`aggregated_data_repo.py` orders all three read methods by ascending `AggregatedData.id`), so
   `groupByColor`'s `Map` follows the **first-seen** order of the served rows: a reversed fixture
   yields a reversed trace order, and the plan's "identical trace set **and identical first trace**"
   assertion fails against a *correct* implementation. The `CHTB-4` `[0]`-nondeterminism rationale is
   therefore void for a second reason beyond the row above's, and the fix is **render every trace**,
   not "make the order stable". The replacement pins the **count** and the **sorted** name set across
   two renders — which is what actually guards against a dropped series.

8. **Two brief premises refuted, both verified against the tree.**
   * There is **no** comment on `makeTrace` — or anywhere in `frontend/src` or in history
     (`git log -S`) — asserting that the server's flat records "always carry both". The gap is the
     opposite one: `makeTrace`'s docstring says nothing about trace shape, which is exactly why a
     reader believes `x`/`y` is universal. So this block **adds** the per-type statement and adds one
     sentence to the module docstring naming `lib/pie.d.ts` as the reason; it deletes nothing.
   * `LineChart.tsx::convertDataToPlotlyFormat` is not a real symbol (see item 3). Nothing to decide.

9. **Filed, not done.** → **`R6`**: the "configured colour/measure names a key no served row carries"
   state renders here as *no colour split* with **no message** — `D-16-4` owns the string set, and the
   empty-vs-absent split is `R6`'s; → **`R6`/`R8`**: a pie graph with a configured colour still emits
   N pie traces in Plotly's default single domain, which overlap; → **`R8`**:
   `docs/11-guides/extend-graphs.md`'s "all work" / "first dimension column, first metric column" claim;
   `api.types.ts::GraphDataWithConfig.config`'s RESERVED wording (`R1`'s filing) plus wording for the
   **new** `metrics` / `dimensions` members, written so they cannot be confused with `config.metrics`;
   `api/routes/data.py::get_aggregated_data_endpoint`'s abbreviated `Response format:` line (which omits
   `metrics`, `dimensions`, `layout`, `config` and the count fields); whether `LineChart` should
   survive as a pass-through wrapper; → **`R1`'s queue row correction**: `OrientationEnum` out of
   `SERVER_ONLY_FAMILIES` is still unowned — this block reads `config.orientation` as a `string` and
   does not touch the mirror, so the row still needs reassigning.

## 2026-10-05 — R4 (`CHTB-4`), Implementor decisions

Two commits, both local-validated before committing.

1. **Commit 1 (`f8581e0`).** `GraphDataWithConfig` gains optional `metrics?: string[]` /
   `dimensions?: string[]`, each with a docstring stating the served/post-alias meaning and naming
   `config.metrics` / `config.x` as the *pre-alias* field they are NOT. Staged by `git add -p`:
   `y` to the `GraphDataWithConfig` hunk, `n` to the peer's `FilterValuesResponse.total_values` hunk.
   `git diff --cached` showed **only** the two new members; `git diff` still showed the peer's
   `total_values` hunk afterwards. The primary recipe (`git apply --cached -R`) was attempted but the
   snapshot file could not be produced reliably through the PowerShell/cmd pipeline in this
   environment (`cmd /c "... > file"` yielded a 0-byte file), so the documented fallback was used.
   The peer's edit is **uncommitted and unstaged** in the tree after both commits.

2. **`chartConversion.ts`.** `ChartTraceType = 'pie' | 'scatter' | 'bar'` exported; three private
   builders (`makePieTrace → Partial<PieData>`, `makeBarTrace → Partial<PlotData>`,
   `makeLineTrace → Partial<PlotData>`) each declaring only their own accepted members;
   `makeTrace` dispatches, signature and exported surface unchanged. `Data` import retained, `PieData`
   / `PlotData` type-imports added. No `Record<string, unknown>`, no `as unknown as`, no
   `eslint-disable` added.

3. **`ChartRenderer.tsx`.** `traceTypeFor` returns `ChartTraceType` (body unchanged); private
   `resolveColumnName(configured, served)` added; the three `const` defaults replaced by the D-4
   chains (`measure → resolve(...) ?? served[0] ?? 'y'`, `axis → ... ?? 'x'`,
   `colour → resolve(config.color, dimensions)` with `undefined` = no grouping). The line branch passes
   the whole `Data[]`; `[0]` deleted. Bar branch, layout conversion, `isPlotlyShaped`, `collectSeries`,
   `groupByColor` untouched — including `R6`'s `?? 0` collapse.

4. **`LineChart.tsx`.** `LineChartProps.data: Data → Data[]`; `title` / `xAxisLabel` / `yAxisLabel`
   and their `chartLayout` merge **deleted**; component now a pass-through of `data` and `layout`.

5. **`ChartRenderer.test.tsx`.** Local `PlotProps.data` narrowed to `Data[]`. The 7 existing tests
   were run **before** writing any new test and stayed green unchanged — first checkpoint, verified.
   9 tests added. One iteration fix: test #7 does two `render` calls, so two `line` testids coexist —
   switched to `getAllByTestId`; and the row fixtures were typed `Data[]` (one cast at the fixture
   boundary, consistent with `makeGraph`) to satisfy `tsc` in the build.

6. **Acceptance (observed).** `ChartRenderer.test.tsx` **16 passed / 0 failed**; `fe-lint` **0 errors**
   (one `require-await` error in a new test was fixed by removing the stray `async`); `npm run build`
   **exit 0**; `fe-test` **24 files / 207 passed / 0 failed**; backend `.\Makefile.ps1 test`
   **1654 passed** — untouched. `git status` after both commits still shows the two `.kilo/plans/*.md`
   deletions unstaged and `node_modules/.vite/` untracked.

7. **Discrimination probe — verbatim outcome.** With `resolveColumnName` temporarily forced to
   `return configured`, the run reported: tests
   *"resolves the served metric for a pie so its values are not all zero"* (**test #2**) and
   *"resolves the served metric for a bar so y is not all zero"* (**test #3**) went **red**; **test #5**
   (*"does not let an empty served list override a configured name"*) stayed **green** under that
   probe. This is expected, not a defect: test #5's fixture supplies an **empty** served list, which the
   probe's `always return configured` rule happens to satisfy, so a change confined to the *resolved*
   served branch cannot move it. Test #5 remains a valid precedence pin against a future
   "served position 0 always wins" rule; it is not a discriminator of *this* change. Tests #1, #6, #7
   discriminate the shape/widening change directly and went red under the corresponding reverts.
   No test labelled "discriminating" remained green under its own probe.

8. **No browser-render claim anywhere.** The evidence is the emitted trace and layout objects plus the
   component props captured by the spies.

### 2026-10-05 — R4 (`CHTB-4`), corrective pass

A documentation/hygiene correction on the accepted block (`f8581e0`, `cfab3e0`). **No behaviour change;
the code is unchanged.** Three edits, one commit.

1. **F1 — the per-type split's *stated reason* was false, and is corrected in the two docstrings.**
   The old claims — `chartConversion.ts`'s module docstring ("`PlotData` carries `x`/`y` only") and
   `makePieTrace`'s docstring ("`Partial<PlotData>` declares neither of the former") — were checked
   against the installed `frontend/node_modules/@types/plotly.js` and are **wrong**: `index.d.ts`
   declares `values: Datum[]` (line 1698) and `labels: Datum[]` (line 1699) **inside `PlotData`**
   (interface opened at line 1514, closed at 1742), alongside `x`/`y` (1516–1517). The corrected text
   states the genuine type-level facts: `PieData` declares no top-level `x`/`y` — the only `x`/`y` in
   `lib/pie.d.ts` belong to `PieDomain` (lines 58–63), reachable solely through `domain`, which this
   code never sets — and each shipped trace type pins its own `type` literal (`PieData.type: "pie"` at
   `lib/pie.d.ts:103`; bar/scatter pin theirs through the `PlotType` union at `index.d.ts:1448`), so the
   split is what stops a builder pairing the wrong trace type with the wrong payload. The false claim
   is dropped; the split would NOT have been a compile error, and that is not claimed. The accepted
   commit's body (`cfab3e0`) repeats the same false statement, but history is not rewritten; this entry
   and the corrective commit record the correction.

2. **F2 — the fixture cast stays; removing it does not work, verified against `tsc`.** The premise was
   that the ONE `as unknown as Data[]` in `ChartRenderer.test.tsx`'s reversed-fixture test exists only
   because of a self-imposed `Data[]` annotation. Dropping the annotation and typing the row helper
   `(data: unknown[])` compiles the raw literals, but then the annotation-less `rows` is inferred as the
   flat-record type and `graph(rows)` passes it into `makeGraph`, where the intersection
   `Partial<GraphDataWithConfig> & { data?: unknown[] }` narrows the override to `Data[] & unknown[]`
   and `npm run build` reports **TS2322** at the `graph(rows)` argument. Typing the helper `Data[]`
   instead makes every other raw-literal fixture fail **TS2353** ("'category' does not exist in type
   'Data'") — 22 diagnostics in total. The `as unknown as Data[]` is therefore load-bearing under this
   file's own helper design. Rather than force it, **the cast was restored** and the file is
   byte-identical to the accepted commit for this item.

3. **F3 — the tripwire comment is narrowed; no assertion added.** Chose to narrow the test #9 comment
   to state precisely that the key set pins the **call site's** prop set, and that re-stating defaults
   inside `LineChart` leaves the key set unchanged and is covered by no assertion here. Reason: R4's
   scope is the renderer's emitted trace/layout and call site, `R6` owns the empty/absent states and the
   `LineChart` pass-through's fate is filed for `R8` (see item 9 of the implementor decisions above), so
   pinning `LineChart`'s internal shape belongs to whichever block finalizes `LineChart`, not to this
   corrective pass. The comment now makes no claim the test cannot defend.

4. **Gates, all observed on the corrected tree.** Focused `ChartRenderer.test.tsx` **16 passed / 16**;
   `fe-lint` **0 errors**; `npm run build` **exit 0**; `fe-test` **24 files / 207 passed / 0 failed**;
   backend `.\Makefile.ps1 test` **1654 passed** — untouched. `api.types.ts`'s peer hunk
   (`FilterValuesResponse.total_values`) is left unstaged, as before.

### 2026-10-05 — R5 (`CHTB-6`), Planner decisions

Scope executed: make a filter value something the repository can evaluate (`multiselect` → membership
predicate) and retire the `range` **control** per `D-16-2`. Executed per
`.ai/plans/_code-context/16-phase16-r5-filter-research.md`, with two corrections below that the research
does not contain.

1. **TWO commits, in this order — server, then client.** The four server pieces (write-boundary
   vocabulary, boundary union widening, repository membership branch, read backstop) land **together**;
   the client pair (`range` control removal, `number[]` restore-drop) lands second. **The ordering
   constraint: the backstop must not be deferred past the union widening.** A server split would open a
   window in which `{"price": ["0","100"]}` returns **silent zero rows** — strictly worse than today's
   loud 422 — so the split is refused, not merely discouraged. A standalone backstop commit is refused
   for a second reason: while the union is scalar-only no list reaches the service, so that commit's
   code cannot fire.

2. **`DashboardConfig.filters` typing is IN scope, but NOT as one shared typed element — the research's
   §4.2 shape is unsafe.** Executed: `DashboardRead.model_validate` **succeeds today** with a stored
   `{"field": "price", "type": "range", …}` filter, and `DashboardRead.config` **is** `DashboardConfig`.
   A `Literal`/`StrEnum` on the shared element therefore converts every already-stored `range` dashboard
   into a **`GET /dashboards/{id}` failure** — `DashboardView`'s `DASHBOARD_LOAD_FAILED_MESSAGE`, the
   whole page — a strictly larger blast radius than the 422 this block closes. Split by direction
   instead: `DashboardConfig.filters` stays `list[dict[str, Any]] | None` (the storage + read shape); a
   new write-only `DashboardWriteConfig(DashboardConfig)` narrows **only** `filters` to a new
   `DashboardFilterConfig` (`extra="allow"`, `field: str`, `type: EvaluableFilterType`, `source`,
   `multi`), used by `DashboardCreate` and `DashboardUpdate`.

3. **"Ignore unknown keys" is NOT acceptable for the storage shape — it is data loss.** Executed:
   `DashboardService.create_dashboard` stores `DashboardConfig(**config).model_dump()`, and a typed
   element under the default `extra="ignore"` dumps `{'field', 'type'}`, silently deleting `options`,
   `min`, `max` and anything else an operator stored. This phase has no dashboard write path and
   `C14-17` owns stored-row cleanup, so silent mutation of stored configs is out.

4. **The vocabulary is a NEW `EvaluableFilterType(StrEnum)` in `models/dashboard.py`** — not
   `models/enums.py` (out of scope) and not `FilterType`. It must not alias the storage enum: aliasing
   the two would recreate the exact trap this block closes. Verified that Pydantic's message is
   identical to a bare `Literal`'s (`Input should be 'select', 'multiselect' or 'date'`, `loc=('type',)`),
   so nothing is lost and the published schema gains a named component. **`FilterType.RANGE` stays**,
   and gains a second job the research does not name: it is the backstop's **named sentinel**, so
   keeping it is what lets the service compare a declared type against a constant instead of a bare
   `"range"` string.

5. **The value union discriminates `number[]` for us.** `list[str]` (not `list[str | int | float]`)
   means the live slider output `[0, 100]` is refused by the model itself, because the only list
   producer the application has is `<Select multiple>` over `FilterValuesResponse.values: list[str]`.
   The **ambiguous** case is therefore only `["0", "100"]` — exactly what an unvalidated
   `sessionStorage` cast produces. That is what the client restore-drop cannot decide from the value
   alone and what the backstop exists for.

6. **Backstop permissiveness, exactly:** undeclared key → permissive; declared `range` → refuse **by
   name whatever the value's shape**; declared non-`multiselect` + `list` value → refuse; otherwise
   permit. A dashboard declaring **no** `filters` at all that receives `["0", "100"]` is **permitted**
   and matched as a membership test. That residual is recorded as a **bound, not a closed hole**.

7. **Filed, not done:** every `docs/**` `range` table, plus `docs/09-database/indexes.md`'s **false**
   `@>` claim (measured — `@>` and `@@` both reach the GIN index; only `->>` does not) → `CHTB-8`;
   `models/dashboard.py`'s `"multi_select"` example is **in this block**, because it would otherwise
   publish a value the new boundary refuses; `FilterConfig.min` / `.max` in `api.types.ts` become
   unreferenced client declarations in a peer-owned file → its owner / `R8`;
   `DashboardView.tsx::filterDetails` forwards no `min`/`max`, so `config.min || 0` always fell back —
   a **filed observation**, not work, because the control is removed; enum-label removal + stored-row
   migration → `C14-17`; the `a3db812` `aria-labelledby` deletion is recorded as *in name only* (the
   control never bound to anything real); `DataService.get_aggregated_data`, the unbounded sibling, gets
   **no** backstop — it has no `src/` caller, and any future caller must reuse it.

8. **Test count: 18, all additions, no existing test modified.** The brief's 17 = the research's 16
   written (its #13, `FilterService._validate_filter_type`, is **not** written — unreachable over HTTP)
   plus 2 this plan adds, because they discriminate decisions the research's set does not cover: a
   stored-`range` dashboard still **reads back 200**, and an undeclared filter-element key survives a
   create→read round trip. Both fail against the research's §4.2 shape.

### 2026-10-05 — R6 (`CHTB-5`), Planner decisions

Scope executed: the client half of "absent is not zero" — the `Number(metric ?? 0)` collapse in
`ChartRenderer`'s two series builders, the state census `D-16-4` owns, and `P13`'s stale marker. The
server half is landed and **not re-touched**. Two corrections to the brief are recorded first, because
both change the design.

1. **CORRECTION — the brief's "the backend serves NO job id, so there is nothing to poll" is FALSE.**
   Verified in the tree: `api/routes/upload.py::upload_file_endpoint` is `response_model=UploadResponse`
   (not a bare `UploadOut`) and `models/data.py::UploadResponse` declares `task_id: UUID`;
   `api/routes/upload.py::get_status_endpoint` serves `GET /upload/status/{task_id}` as
   `ProcessingStatusResponse`; and the client already consumes both — `uploadApi.uploadFile` returns
   `UploadResponse`, `uploadApi.useProcessingStatus` polls that id every 2 s, and
   `UploadModal::UploadModal` calls `onUploadComplete()` **only** when `statusData.status ===
   'completed'`. So a job id and a poll both exist, and the dashboard's `invalidateAggregatedData` is
   already ordered **after** processing finished. Consequence for `P13`: the reachable "flip to empty"
   is **not** an upload/processing race, and no polling design is needed or permitted. The genuinely
   missing piece is that `onUploadComplete` is a **bare callback** — the completed status never reaches
   `DashboardView` — so "the new data is ready" is not an input the view can be given without changing
   the upload feature's prop contract. **That is filed, not built** (see item 10).

2. **CORRECTION — `GraphDataResponse.metrics` emptiness is NOT an independent signal.** Precise
   statement, from `services/data_service.py::_served_row_keys` and
   `services/aggregation_service.py::aggregate_for_dashboard`: `metrics` is the first-seen union of the
   keys of the stored `metrics` JSONB column over the served page, and the writer `continue`s unless
   **both** `groupby_cols` and `metric_cols` are non-empty, so **every written row carries at least one
   metric key** and every `dims` key. Therefore, on the current server, `metrics.length > 0` **iff**
   `data.length > 0` (and likewise for `dimensions`) — the two are the *same* signal, so
   `metrics.length === 0` can never be a state distinct from `data.length === 0`, and a predicate built
   on it would be unreachable-and-lying. `R3`'s "rows exist but their metrics are all absent" is a
   *hypothetical* the current writer cannot produce. `R4`'s reading of the brief was correct and this
   block does not build on the alternative.

3. **The four states are two dashboard-scope and two graph-scope predicates, plus one age state.**
   Over the served `GraphDataWithConfig` `G` (`R` is the `AggregatedDataResponse`,
   `measureColumn := resolveColumnName(G.config?.metrics?.[0], G.metrics) ?? G.metrics?.[0]`, i.e. exactly
   the column `convertToPlotlyData` reads, moved to one function so the marker and the trace cannot
   disagree):

   | state | scope | predicate | signal |
   | --- | --- | --- | --- |
   | `NO_CHARTS` | dashboard | `R.graphs.length === 0` | the served graph list |
   | `NO_ROWS` | graph | `G.data.length === 0` | the served row list |
   | `MEASURE_ABSENT` | graph | `G.data.length > 0 && measureColumn !== undefined && !G.data.some(row => isChartRecord(row) && readScalar(row, measureColumn) !== undefined)` | the rows themselves |
   | `RENDERED` | graph | `G.data.some(row => isChartRecord(row) && readScalar(row, measureColumn) !== undefined)` | the rows themselves |
   | `STALE` (`P13`) | query | `error !== null && data !== undefined && data.graphs.length > 0 && dataUpdatedAt > 0` | the query result, **not** the response |

   **No two can hold at once:** `NO_CHARTS` needs an empty graph list while `NO_ROWS`/`MEASURE_ABSENT`/
   `RENDERED` each need one graph; `NO_ROWS` needs `data.length === 0` while the other two need
   `data.length > 0`; `MEASURE_ABSENT` and `RENDERED` are complementary on the same `some`/`every`
   question. `rows_truncated` is deliberately **not** a state predicate — it is a status line
   (`DashboardView`, landed), and a truncated response is still one of the four. **A present-but-`0`
   measure is `RENDERED`, never `MEASURE_ABSENT`** — that is the block's whole point. `STALE` is
   orthogonal to the other four by construction: it is the only predicate over the query result.

4. **`D-16-4`'s absent-graph card is satisfied by construction — no card is added.** Per `R3`'s
   verified finding, the endpoint enumerates the `graphs` table, so a graph the writer skipped appears
   with `data: []` and already gets a card. The four states are therefore four *content* states, and the
   "graph absent from the response" situation has no reachable instance. The residual — a graph skipped
   at write time is still **skipped on every future read** for that dataset — is the upstream
   `continue`, which is phase 05's pipeline behaviour; **filed, not touched** (a backend change is out
   of this block's scope).

5. **The absent value is `null`, and only a real finite number becomes a number.** One exported
   `toMeasureValue(value: unknown): number | null` in `chartConversion.ts` replaces the two
   `Number(metric ?? 0)` coercions (in `collectSeries` **and** in `groupByColor` — both sites, or the
   grouped branch keeps the defect): `number` and finite → itself (**including `0`**); `null`,
   `undefined`, non-finite (`NaN`/`Infinity`), and every non-numeric value → **`null`**. No `Number()`
   call survives anywhere on the measure path. Non-numeric-but-present becomes `null` rather than `0`
   because coercing a garbage value to a number is the *same* defect as `?? 0` wearing a different hat;
   numeric **strings** are not accepted, because the served measure values are Polars numerics
   (`_coerce_dim_value` canonicalises dims to strings, and a string in a measure position is a contract
   violation, not a number to guess at). `ChartElement` splits into a label type
   (`string | number | boolean`) and a measure type (`number | null`), and `makeTrace` plus the three
   per-type builders take the measure type. `connectgaps` is **not** set: Plotly's default is `false`,
   which is what produces the gap.

6. **`isChartRecord` is itself part of the defect and must widen.** It currently accepts only
   `string | number` values, so a row carrying a **`null` measure** (a Polars `sum` over an all-null
   group is `None` on the wire) or a **boolean dim** (`_coerce_dim_value` preserves `bool`) fails the
   guard and makes `readScalar` return `undefined` for **every** field of that row — blanking the
   category *and* forcing the measure to `0`. The record type widens to
   `Record<string, string | number | boolean | null>`. A present-but-`null` key and an absent key stay
   distinguishable inside `readScalar` (`null` vs `undefined`) but **deliberately render the same gap**:
   Plotly's `y` has no second channel, and the visual result is identical.

7. **One string home: `ui/charts/chartStates.ts` (new, co-located with `chartConversion.ts`).** It
   holds both state enums, the three predicates, `resolveColumnName` (**moved verbatim** out of
   `ChartRenderer` — a move, not a rewrite; R4's 16 tests assert behaviour, not location), the
   `toMeasureValue`-adjacent absent test, and every string. A `model/` module was rejected because the
   predicate needs `isChartRecord`/`readScalar`, which live in `ui/charts/`, and `model/` must not import
   `ui/`; the folder's existing convention (`chartConversion.ts`, `resolveColumnName`) already places
   pure chart logic in `ui/charts/`. Strings — five, exact, this block decides them
   (`CHTB-5`'s "the string set is a product artefact"):

   - `NO_CHARTS_MESSAGE` = `This dashboard has no charts to display.` — **the one changed string.**
     Today's "No data available for this dashboard. Upload data to see charts." is false advice for the
     state it names: uploading data creates no graphs. Rejected: keeping it (a wrong instruction is the
     same class of defect as a wrong figure).
   - `NO_ROWS_MESSAGE` = `No data available for this chart` — **unchanged verbatim**; the existing
     `ChartRenderer.test.tsx` assertion pins it, and it is accurate. `TableChart`'s empty case adopts
     the same constant (today it says `No data available`, a second sentence for one situation).
   - `MEASURE_ABSENT_MESSAGE` = `The measure "{column}" is not in the served data, so this chart shows a
     gap instead of a value.` — per graph, in the card, **names the column**.
   - `DASHBOARD_MEASURE_ABSENT_MESSAGE` = `One or more charts have a measure that is not in the served
     data. Those charts are drawn as gaps, not zeros.` — `D-16-4`'s warning, **once per dashboard**,
     at dashboard scope, `severity="warning"`.
   - `STALE_DATA_MESSAGE` = `Data may be out of date — last updated {time}` — **`P13`'s ruled text**,
     `time` interpolated with `shared/utils/formatDate.ts::formatDateTime`. Cause-free by necessity:
     TanStack's `refetchOnWindowFocus` can trigger the same refetch with no upload at all, so the
     marker may not name a cause.

8. **Placement, and the two failure kinds stay apart.** The per-graph marker renders in
   `DashboardView`'s existing `Paper` **beside the truncation caption** — same element, same place, so
   the card's status lines stay visually consistent and nothing new is wrapped inside the fixed-height
   `Stack sx={{ height: 400 }}` (a marker inside `ChartRenderer` would need a fragment there and
   squeeze the chart). `ChartRenderer` keeps only the trace-level consequence. The `D-16-4` warning
   renders **once, above the graphs `Stack`**, gated on `R.graphs.some(g => classify(g) === MEASURE_ABSENT)`.
   It cannot collide with `R5`'s in-panel filter warning (different component, different subject, and
   that one names a filter and a declared type) nor with the two failure Alerts (severity `warning` vs
   `error`). **A real double-message bug is closed here**: today a `dataError` with no cached data
   renders *both* `CHART_DATA_LOAD_FAILED_MESSAGE` and the empty-state Alert, asserting a false "no
   data" on a failed load. The empty-state Alert now requires `!dataError`.

9. **`P13`'s mechanism: `dataUpdatedAt` + `error` from the existing query result. No `placeholderData`,
   no snapshot ref, no change to `dashboardApi.ts`.** `placeholderData: keepPreviousData` is **rejected**:
   it only supplies data while a query has *no* cached data for its key, so it does nothing on the path
   `P13` is about (a refetch of a key that already has data), and it would additionally mask a *filter
   change* by showing the previous filter's data — a new lie for an old one. The last-good payload is
   whatever the query already retains on a failed background refetch; `dataUpdatedAt` supplies the
   timestamp the ruled marker text needs, which the response cannot (`GraphDataResponse` serves no
   generation timestamp — see item 10). When `STALE` holds, the view renders the retained data **and**
   the marker, and **suppresses** `CHART_DATA_LOAD_FAILED_MESSAGE`, because "what you see is old" and
   "the load broke" must not both be asserted. With no retained data there is no stale state, the
   existing error Alert is the only available truth, and the marker is absent — which is also the
   first-load case the ruling names. **One precondition must be verified before the code is written**:
   that a failed background refetch leaves `data` populated. The implementor runs that probe with a
   real `QueryClient`; if it fails, the **only** sanctioned fallback is a `useRef` last-good snapshot in
   `DashboardView` (plus the test that proves the snapshot path), and the deviation is reported, not
   absorbed.

10. **Limits, stated as limits.** (a) The upload's completed status is **not** an input the view can
    receive without changing `UploadModal`'s `onUploadComplete` prop contract — **filed**. (b) A
    *successful* response with no rows is shown as the truthful empty state, never as stale: the client
    cannot distinguish "the server is mid-rewrite" from "the server has no data", and no served field
    says a response is provisional. (c) `dataUpdatedAt` is when the data reached the **browser**, not
    when it was computed; an honest "as of" time needs a server field, which is a backend change —
    **filed**. (d) Beyond TanStack's `gcTime` there is no retained data, so no marker is possible and
    the error Alert is all there is. (e) `R7`'s `staleTime: Infinity` **narrows** this trigger to
    upload-driven refetches (focus no longer refetches a never-stale query) and does not collide:
    **zero edits to `dashboardApi.ts`**.

11. **Leave alone.** No `src/mkobi/**` edit; **no** `api.types.ts` edit — every state predicate reads
    fields it already declares (`metrics?`, `dimensions?`, the three counts), so the peer's
    uncommitted `FilterValuesResponse.total_values` hunk is not at risk. `shared/types/enums.ts` is
    untouched, which matters: `shared/types/__tests__/enums.test.ts` pins `CLIENT_ONLY_FAMILIES` at
    exactly `['FileUploadStatus']`, so the two new enums are **feature-local**. `shared/api/errorSurfaces.ts`,
    `DashboardFilters.tsx`, `DashboardList.tsx` (its `No dashboards available…` string is already correct
    and distinct), `SkeletonChart.tsx`, `PlotlyChart.tsx`, `LineChart.tsx`, `upload/**`, `docs/**`, and
    this file's other entries — all untouched. `P13` touches `DashboardView` only.

12. **Test target: 3 new files, ~26 new tests, no existing test rewritten or deleted.** One per state
    plus a pairwise-exclusivity matrix (`ui/charts/chartStates.test.ts`); the `null`/`0`/garbage/second-
    coercion-site/widening assertions on the **emitted trace** in `ChartRenderer.test.tsx`;
    `getDisplayValue`'s first ever tests in a new `TableChart.test.tsx`; the marker, the once-per-dashboard
    warning, the `dataError`-without-empty-state fix and `P13` in `DashboardView.test.tsx`; the
    `P13` precondition probe in its own file. `fe-test` goes 25 files / 211 passed → **28 files / 237
    passed**. `ChartRenderer.test.tsx`'s 16 existing tests must pass **unmodified** — they are the
    regression net for the `resolveColumnName` move. No test may claim pixels: there is no
    browser-render harness, so evidence stops at the emitted trace/layout objects and component props.

## 2026-10-05 — `R5` corrective pass (documentation accuracy)

A single corrective pass on the **accepted** `R5` (`8f22377`, `7568a21`). No behaviour defect; three
findings, all documentation or defensive tightening.

- **C1 — the value-bound rationale was false, and is corrected.** `AggregatedFiltersRequest.validate_filter_bounds`
  was justified as *"a list evades `MAX_FILTER_VALUE_LENGTH` element-wise because `len(str(value))` measures
  the repr"*. That is false: `len(repr(list)) >= max(len(element))` always, so an over-long element was
  never evadable — the repr bound already refused it with the same `VALIDATION_ERROR`. The corrected
  comment states what the change is actually worth: it **attributes** the violation (names the offending
  key and element length where the scalar message omits the key) and **widens** acceptance for
  multi-element lists the repr bound refused (`["a"*200,"b"*200]`, repr 408 → now accepted) on a path
  previously unreachable because the union refused lists first. `MAX_FILTER_PAYLOAD_BYTES` still caps the
  total. The `8f22377` commit message cannot be rewritten; this entry records the correction.
  - **C1 endpoint half — removed, not tightened.** The endpoint assertion 422s before *and* after (the old
    repr bound already refused the payload), so it was a pin, not a discriminator, and the route wraps the
    model's `ValidationError` into a generic 422 that discards the message — the attribution cannot be
    observed at the endpoint. The model-level assertion (`"category" in message`) is the discriminator and
    is kept; a second model-level test now pins the acceptance side of the widening.
- **C2 — publication names corrected.** `TestAggregatedFiltersRequestPublishesListValues` →
  `...ValidatesListValues`, and `test_filters_query_schema_publishes_a_string_array_branch` →
  `...validates...`, with the docstring stating plainly that `AggregatedFiltersRequest` is built inside the
  route and is **not** in the published OpenAPI document. The assertion against `model_json_schema()` is
  not vacuous and is kept; the test is not relocated.
- **C3 — the restore predicate now matches its name.** `isRestorableFilterValue` in `DashboardView.tsx`
  admitted `boolean[]`, nested arrays and object arrays, which serialise into the `filters` payload and are
  refused by `list[str]` with a 422 rendered as a dashboard-scope alert. It is now a type predicate that
  admits a list only when **every element is a string**; the `as FilterState[string]` cast is gone; the
  scalar and "is an object, is not an array" behaviour is unchanged. `R5`'s
  `preserves a restored string-array filter byte-identical` stays green; a new test pins the boolean-array
  drop.
- **Optional ordering — left, recorded.** `validate_filter_values` still runs before the `graph_id`
  ownership check (422-before-404 for a cross-dashboard `graph_id` with a bad filter). The call is
  deliberately one call covering both response shapes before the branch; moving it would force a second
  call or a restructure for a disclosure-only ordering that is not a hole (access is checked above). A
  one-line comment in the route records it.

`fe-lint` 0 errors; `fe-test` 30 files / 242 passed; `pytest tests/test_filter_payload_bounds.py tests/test_openapi.py`
30 passed. No `docs/**`; no `src/mkobi/models/dashboard.py` change.
