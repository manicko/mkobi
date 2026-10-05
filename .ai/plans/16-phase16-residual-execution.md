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