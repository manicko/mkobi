# Phase 16 — Chart Presentation Contract · Code Context (Phase 1)

**Auditor:** Phase-1 code-context · **Date:** 2026-10-01
**HEAD:** `907e052` — `fix(worker): make the processing-log transitions durable`
**Report baselined:** `d008f555` (report frontmatter) / `863b81b` (brief)
**Finding-ID prefix in use:** **`CHT-`** (`CHT-001`…`CHT-010`), report-level defects **`VAL-16-001`**…**`VAL-16-006`**

---

## 1. Scope and method

### 1.1 What was read

| Group | Files read in full |
|---|---|
| Client chart tree | `charts/ChartRenderer.tsx` (156 L), `charts/LineChart.tsx` (27 L), `charts/PlotlyChart.tsx` (2 L), `charts/TableChart.tsx` (82 L) |
| Client dashboard | `ui/DashboardView.tsx` (225 L), `ui/DashboardFilters.tsx` (214 L), `api/dashboardApi.ts` (97 L) |
| Shared types | `shared/types/api.types.ts` (327 L; L175-234 read) |
| Client config | `vite.config.ts`, `package.json`, `tsconfig.json`, `tsconfig.app.json`, `eslint.config.js` |
| Backend model | `models/types.py` (L95-164), `models/data.py` (L418-457), `api/routes/data.py` (220 L, all) |
| Backend service/repo | `services/aggregation_service.py` (L40-109), `services/data_service.py` (L185-244), `db/repositories/aggregated_data_repo.py` (L135-184) |
| Backend data path | `data/processing/aggregate_transforms.py` (L120-159), `workers/data_worker.py` (L765-887) |
| Reports | `.ai/audit/99-validation/16-chart-presentation-contract-validated-findings.md` (472 L), `.ai/audit/16-chart-presentation-contract/findings.md` (365 L) |
| Sibling plans | `04`, `09`, `11`, `12`, `13` frontmatter + scope-ruling tables (`C0*-*`, `TST-*`, `PRF-*`/`DP-11-*`, `AZ-*`, `CT-*`) |
| Docs naming the contract | `docs/00-overview/data-flow.md:71-75`, `docs/02-dashboards/dashboards-api.md:356-359,941-972`, `docs/03-processing/processing-api.md:257-261`, `docs/07-frontend/pages.md:149-153`, `docs/08-security/access-control.md:114-117`, `docs/09-database/schema-core.md:193-197`, `docs/11-guides/extend-graphs.md:126-226`, `docs/99-reference/swagger.md:163-165` |

**Not read:** plans 01, 02, 03, 05, 06, 07, 08, 10, 14 (no phase-16 seam claimed in the brief); `docs/SPEC.md` beyond L61-64 and the changelog.

### 1.2 Gates run, and the real baseline

| Gate | Command | Result at `907e052` | Moved from peer? |
|---|---|---|---|
| `fe-lint` | `npm --prefix frontend run lint` | **RED — 9 errors** | **No.** Reproduced exactly. |
| `fe-test` | `npm --prefix frontend run test` (`vitest run --coverage`) | **RED — 1 failed / 169 passed (170), 13 files** | **No.** Reproduced exactly. |
| `check` | `lint → typecheck → fe-lint → fe-test` | Short-circuits at `fe-lint`; never reaches `fe-test` (`Makefile.ps1:241-249`) | No |
| `fe-typecheck` | — | **Target does not exist** (`Makefile.ps1:411-433`); no `typecheck` script in `frontend/package.json` | No |

`fe-lint` — 9 errors, distribution:

| File | Lines | Rule |
|---|---|---|
| `charts/ChartRenderer.tsx` | **86, 90, 98** | `@typescript-eslint/no-unnecessary-type-assertion` |
| `ui/DashboardView.tsx` | 57, 72 | `no-unsafe-member-access` (`.preserveFilters` on inferred `any`) |
| `ui/DashboardView.tsx` | 65 | `react-hooks/set-state-in-effect` |
| `__tests__/filter-persistence.test.tsx` | 123, 188, 219 | `no-unsafe-return`, `no-unsafe-assignment`, `require-await` |

`fe-test` — the single red is `src/shared/types/__tests__/formSchemas.test.ts:162` (`changePasswordSchema > accepts matching passwords`). Phase 09's. **Not** a phase-16 test.

**Correction to the brief's framing.** The 3 `ChartRenderer.tsx` errors are *not* "in a function no finding names". They sit in `convertChartLayoutToPlotly` (`ChartRenderer.tsx:80-119`), which **CHT-002** names at `:89-95` and **CHT-006** names at `:81` plus "eleven unreachable branches". What no finding names is the **redundant type assertion** — `as Partial<Layout>['title' | 'xaxis' | 'yaxis']` at `:86, :90, :98`. Plan-13 `:2460` repeats the same claim ("three of the nine are in a function no finding names"); it is wrong on the function, right on the assertion. Every fix that repopulates `layout` must remove or keep these three assertions deliberately.

**`frontend/coverage/` — confirmed destroyed, and the destruction predates this run.** The 15 ` D` deletions were present in the *first* `git status --short` taken before any gate ran. After running `fe-test`: still ` D` for all 15, and **0 files on disk** — the run wrote **no replacement**. This is not restored. `vite.config.ts:56-65` configures reporter `['text','json','html']` against the v8 default `reportsDirectory` (`frontend/coverage`); the reporters do not emit while the run is red. `eslint.config.js:9` globalIgnores `coverage`, so `fe-lint` is unaffected.

**The `any`-ban claim, resolved.** `eslint.config.js:14` extends `tseslint.configs.recommendedTypeChecked`, which **does** enable `@typescript-eslint/no-explicit-any`, and `tsconfig.app.json:3` sets `"strict": true`. Both are on. The ban is still not enforced **in substance**, because no source file writes a literal `any`: `ChartRenderer.tsx:48,70` uses `as unknown as Record<string, unknown>[]`, and every observed violation is an **inferred** `any` (`useLocation().state`, untyped test params). The `no-unsafe-*` rules catch the inference; the `any`-ban does not. Enforcement is a lint-config change → **phase 08** (`C13-9`).

### 1.3 HEAD-vs-worktree split

| Layer | State |
|---|---|
| `HEAD` | `907e052` — **one commit past the brief's `863b81b`**, and two past the report's `d008f555`. Ten commits of phase-02/03 worker, tx, lease and lifespan remediation landed. |
| Dirty, tracked (34 ` D`) | `.ai/builders/**` 7 · `.ai/structure/**` 5 · `.ai/models/**` 2 · `.ai/templates/**` 2 · `.ai/plans/audit-fix-plan.md` · `.ai/audit/templates/audit-final-report.md` · **`frontend/coverage/**` 15** |
| Dirty, untracked | 14 sibling plans (`01`–`14`) · `.ai/plans/_code-context/` · 3 `.ai/tasks/*.yaml` |
| **`src/mkobi/**`** | **clean** — no backend file in this phase's scope is dirty |
| **`frontend/src/**`** | **clean** — every file this phase's findings name is at its committed state |

**Split verdict: every anchor in this phase resolves against committed content.** No phase-16 file has been modified in the worktree. The only drift is *positional* (§5.1).

### 1.4 Findings already owned by another phase

| Owned elsewhere | Mechanism | Phase-16 exposure |
|---|---|---|
| **CHT-001's shape half** — `GraphDataWithConfig.data` typed `Data[]` against a `list[dict]` payload | `FE-007` / `FE-008`, ruled to **phase 13**; `C13-6` files the presentation *consequence* with phase 16 | **Contested.** §5.3 |
| **CHT-010** — `['filterValues', …]` never invalidated | `VAL-13-003`, same root cause, two IDs | **Contested by `VAL-16-002`.** §5.4 |
| **`errorMessages.ts`** (six files) + `useAuth.ts`'s `RATE_LIMIT_EXCEEDED` branch + four `force_password_change` redirects + `adminApi.ts::retrieveTempPassword` + `UserManagement.tsx` + `RegistrationRequests.tsx` | plan-04 **`C04-4`** reserves `frontend/src/**` to phase 16 | **Phase-16-held, unclaimed.** No CHT finding names any of these (§5.2) |
| **`errorHandler.ts` switch, `features/admin/model/errorMessages.ts` code map, 403 toast+inline double render** | plan-12 **`O-05` / `C12-1`** assigns the client half to phase 13 / phase 16 | **Phase-16-held, unclaimed.** No CHT finding names these |
| **Chart presentation of a bounded / aggregated response** (`DP-11-B`) | plan-11 OUT row → **phase 16** | **Phase-16-held, unclaimed** by any CHT finding |
| **Frontend test coverage** | plan-09 OUT row → **phase 16**, **unnumbered** | **Phase-16-held, unclaimed.** §5.5 |
| **`GraphDataResponse` + `/data/aggregated` endpoint** | plan-12 **`AZ-8`** (`AUTZ-004`) holds `models/data.py`'s aggregated schema **read-only** and edits `data.py` | **Direct collision with CHT-003.** §5.6 |
| **`docs/07-frontend/pages.md`** (`graph_id` optional) | plan-11 `C11-8` / plan-12 `C12-7` / plan-13 `C13-5` → **phase 13** | Read-only for phase 16 |

**Count: 4 of 10 CHT findings carry a contested or foreign owner (CHT-001 partial, CHT-003, CHT-008 partial, CHT-010); 6 are unowned by any sibling plan.**

---

## 2. Per-finding context

> Anchor convention: symbol first, line numbers only as drift evidence.

### CHT-001 — Measure name unnameable → flat zero series (CRITICAL)

| Aspect | Reality at `907e052` |
|---|---|
| Component | `convertToPlotlyData` (`ChartRenderer.tsx:11-75`) |
| Chart-config type | `GraphConfigDict` (`models/types.py:138-152`) — `total=False` TypedDict, **11 keys**: `x, y, color, xaxis, yaxis, title, layout, yoy, secondary_y, sort_x, sort_color`. **No `metrics`.** |
| Config read | `const metricCols = config.metrics \|\| ['y']` (`:17`); `const metricCol = metricCols[0]` (`:26`) |
| Aggregate payload shape | `aggregation_service.py:93` → `agg_fn(pl.col(m)).alias(f"{m}_{metric_agg}")`; `data_service.py:216` → `preview=[{**record.dims, **record.metrics}]`. Row keys = dimension names **+ `{metric}_{agg}`**. |
| Failure | `row['y']` is `undefined` on every row; `Number(undefined ?? 0)` → `0` (`:57`, `:72`) |
| Rescue attempt | Shape sniff `:21-23` needs a row carrying **both** `x` and `y`. Served rows are `{**dims, **metrics}` — a dimension named `x` *could* exist, but no measure is ever named `y`. Sniff does not fire. |
| Shared type | `GraphDataWithConfig.config?` (`api.types.ts:209-215`) **declares** `metrics?: string[]` — the client mirror asserts a key the server strips |

**Verdict: `substantiated`** (mechanism and effect). The one clause the validator added is **not reproducible from source alone**: the executed `convertToPlotlyData` result `{"x":["North","South"],"y":[0,0],"type":"bar","name":"B"}` came from running extracted code, not from a shipped test — there is no such fixture in the repo.

**Owner:** split. The **shape** half (`FE-007`) is **phase 13**; the **measure-name** half is phase 16.

**Seams an implementor touches:** `models/types.py::GraphConfigDict` (add `metrics`/`orientation`/`barmode`); `ChartRenderer.tsx:17,26` (read `config.y`); `api.types.ts:209-215` (mirror); `frontend/src/**` **test fixture** (none exists). `tests/test_openapi.py` is the schema tripwire. Hard gate: nothing here is observable in a browser — there is no browser-render harness in the repository (plan-13 `DP-13-K` option (b): "not executable at all").

### CHT-002 — Bar branch overwrites the converted `xaxis` (HIGH)

| Aspect | Reality |
|---|---|
| Converter | `convertChartLayoutToPlotly` (`:80-119`); maps `title` (`:86`), `xaxis{title,type,range}` (`:89-95`), `yaxis{…}` (`:97-103`), `showlegend` (`:106`), `height` (`:109`), `width` (`:112`), `template` (`:115`) |
| Overwrite | `barLayout` = `{...convertedLayout, barmode: config?.barmode \|\| 'group', xaxis: {type:'category'}}` (`:147-151`) — `xaxis` written **after** the spread, replacing the object wholesale |
| Survives | `yaxis` (nothing writes it after), `showlegend`, `height`, `width`, `template`, `title` |
| Input is unreachable | `convertChartLayoutToPlotly` returns `undefined` at `:81` on every chart today — `GraphDataResponse.layout` is never populated (**CHT-006**) |
| Pie branch | `:155` passes the converted layout straight through — keeps `xaxis` |

**Verdict: `substantiated` as a latent defect; `refuted` as a present-observable effect** (`VAL-16-003`). The mechanism is real and `config.layout` genuinely round-trips — but the renderer reads `graph.layout` (`:146`, `:138`), a **different field** on the response. With `undefined` the `:150` write changes nothing.

**Seams:** `ChartRenderer.tsx:150` (merge `{type:'category', ...convertedLayout?.xaxis}`); the three lint assertions at `:86,90,98` sit in the same function. **Hard sequencing:** `VAL-16-003` — must land in the same commit as CHT-006, after the merge, or populating `layout` converts a latent discard into a live one.

### CHT-003 — `metrics` / `dimensions` never served (HIGH)

| Aspect | Reality |
|---|---|
| Response model | `GraphDataResponse` (`models/data.py:425-452`), fields at `:431-436`: `graph_id, type, name, data, layout, config`. **No `metrics`, no `dimensions`.** `model_config` at `:438` with a `json_schema_extra` example at `:440-451` |
| Construction sites | Exactly **two**, both in `api/routes/data.py`: `:152-158` (single-graph) and `:188-194` (all-graphs). Neither passes `layout` (CHT-006) and neither passes a measure list |
| Whole-tree | `GraphDataResponse` appears at **2** construction sites; `AggregatedDataResponse(graphs=…)` at `:150` and `:197` |
| Source of truth | `Graph.dimensions` / `Graph.metrics` (`db/models/graphs.py:70-80`) are required on create/update (`models/graph.py:16-17,46-47`) and consumed by `aggregate_for_dashboard` (`aggregation_service.py:69,74`) |
| Client mirror | `GraphDataWithConfig` (`api.types.ts:203-216`) — no `metrics`/`dimensions` |

**Verdict: `substantiated`.**

**Owner: COLLIDED.** Plan-12 **`AZ-8`** names `models/data.py`'s aggregated-response schema as **read-only** and edits `api/routes/data.py::get_aggregated_data_endpoint`; its contract suite `tests/test_data_endpoint.py::TestAggregatedDataEndpointContract` **must stay green unmodified**. CHT-003's remedy edits the same model, the same two construction sites, and changes the shape that suite pins.

**Seams:** `models/data.py:431-436`; `api/routes/data.py:152-158,188-194`; `api.types.ts:203-216`; `tests/test_openapi.py`; `TestAggregatedDataEndpointContract`. See §5.6.

### CHT-004 — Eight declared keys read by nothing (MEDIUM)

| Declared (`GraphConfigDict`) | Read by renderer | Served? |
|---|---|---|
| `x` | `:15` | yes |
| `color` | `:16`, consumed `:45-65` | yes |
| `y` | **no** | yes |
| `xaxis` | **no** | yes (mirrored in `layout`, never populated) |
| `yaxis` | **no** | yes (ditto) |
| `title` | **no** | yes |
| `layout` | **no** (`:81` short-circuits) | yes |
| `yoy` | **no** — deferred to phase 05 `DP-009` | yes |
| `secondary_y` | **no** | yes |
| `sort_x` | **no** | yes |
| `sort_color` | **no** | yes |

`DashboardView.tsx:191-193` renders `graph.name` as the `<Typography variant="h6">` heading. Whole-tree search over `frontend/src` for `config.title`, `config.xaxis`, `config.yaxis`, `config.layout`, `config.secondary_y`, `config.sort_x`, `config.sort_color`: **no match**.

**Verdict: `substantiated`** — 11 declared, 5 read, **intersection 2**, nine unrendered, `yoy` deferred, **eight** live.

**Seams:** `models/types.py::GraphConfigDict` (narrow) or renderer promotion of `title`+`y`; `DashboardView.tsx:191-193` for the heading. The remedy is explicitly a **product decision** (which keys survive) — see §6.1. Documentation is the sharp edge: `docs/02-dashboards/dashboards-api.md:356-359` and `docs/09-database/schema-core.md:193-197` both document a `config` schema containing **`y_axis`**, **`colors`**, **`orientation`**, **`barmode`** — of which `y_axis` and `colors` are **not** `GraphConfigDict` keys at all and `orientation`/`barmode` are stripped at write.

### CHT-005 — `orientation` / `barmode` read but unstoreable (HIGH)

`ChartRenderer.tsx:18` `const orientation = config.orientation || 'v'` → `trace.orientation` (`:36-38`, bar only); `:149` `barmode: (config?.barmode || 'group')`. Neither key is in `GraphConfigDict`, so `GraphCreate`/`GraphUpdate` validation (`models/graph.py:15,45`) drops both. The defaults are the **only** values that can ever arrive.

**Verdict: `substantiated`.** Note `makeTrace:36-38` applies `orientation` **only** when `graph.type === 'bar'` — a line graph's orientation is not read either.

**Seams:** same `GraphConfigDict` edit as CHT-001 step 1; `Literal` narrowing turns previously-silent drops into **422s**. Verified pre-ship condition holds: there is **no graph editor** in `frontend/src` — a search for the keys it would send returns nothing outside `ChartRenderer.tsx`, so the `Literal` tightening is currently unreachable from the shipped UI.

### CHT-006 — `GraphDataResponse.layout` declared, never populated (HIGH)

`models/data.py:435` `layout: ChartLayoutConfig | None = None`; `json_schema_extra` advertises `"layout": {"title": "Sales Chart"}` at `:449`; docstring at `:428` promises "graph metadata (id, type, name) and Plotly.js data". Two construction sites, neither passes it ⇒ resolves to `None` on every response ⇒ `convertChartLayoutToPlotly` returns `undefined` at `:81` ⇒ **all eleven mapped fields unreachable**.

**Verdict: `substantiated`.** `VAL-16-006` corrects one mechanism: the line branch's `{title, xaxis, yaxis}` defaults (`LineChart.tsx:19-24`) are **preserved**, not overridden — `{...undefined}` is a no-op, so the frame carries the empty defaults and they win nothing.

**Twelfth dead field:** `AxisConfig.label` (`models/types.py:105`, mirrored `api.types.ts:188`) — the converter reads `title` only.

**Seams:** `api/routes/data.py:152-158,188-194`; `ChartRenderer.tsx:80-119`; `ChartRenderer.tsx:86,90,98` (the three lint assertions); `models/types.py:105` + `api.types.ts:188`. **Hard co-requisite with CHT-002** (`VAL-16-003`).

### CHT-007 — `pie` handed a scatter-shaped trace (HIGH)

`makeTrace` (`:28-43`) unconditionally sets `x: xVals, y: yVals` (`:30-31`), then `type: graph.type === 'pie' ? 'pie' : …` (`:32-33`). No `labels` and no `values` is assigned **anywhere** in the file. `const trace: Record<string, unknown>` at `:29` is why `tsc` accepts it.

**Verdict: `substantiated`, and upgraded from a library claim to a shipped-artefact claim.** `@types/plotly.js` `PieData` populates from `labels` + declares `values`; the only `x`/`y` in that file belong to `PieDomain`, which the code never sets. **Ordering constraint, independently confirmed:** pie traces come out `y: [0,0]` because of CHT-001 — so fixing CHT-007 alone yields an **all-zero pie**, which is worse than an empty one.

**Seams:** `ChartRenderer.tsx:28-43` (pie-specific trace builder), `:29` (the `Record<string, unknown>` escape hatch), `api.types.ts:212` (`config.metrics` is declared here and stripped server-side).

### CHT-008 — Line branch drops N−1 traces (HIGH)

`convertToPlotlyData` returns `Data[]`. With `config.color` set, `:64` returns one trace per distinct colour via `Object.entries(groups).map(...)`; without, `:74` one trace. `ChartRenderer.tsx:138` indexes `[0]`; `LineChart.tsx:5` types the prop `Data` (not `Data[]`); `LineChart.tsx:26` re-wraps `data={[data]}`. The bar branch at `:142` passes the whole array.

**Verdict: `substantiated`.** The surviving trace is whichever colour key was **first inserted** into `groups` (`:58-64`) — insertion order over `graph.data`, which itself comes back from an unordered `SELECT` (see §3.6).

**Owner: CONTESTED.** Plan-13 `CT-7` (`FE-007`/`FE-008`) widens this same function's typing; `C13-6` names the *presentation* half as phase 16's and blocks `CT-7` on "phase 16's read".

**Seams:** `ChartRenderer.tsx:138`; `LineChart.tsx:4-10` (props), `:26`; `ChartRenderer.tsx:45-65` (the grouping loop). **Note the second, unfiled truncation:** the served rows are unordered, so the `[0]` index is nondeterministic across requests, not merely arbitrary.

### CHT-009 — `multiselect` / `range` compared with `str()` (MEDIUM)

Binding path, all confirmed live: `DashboardFilters.handleFilterChange` `:48-63` (300 ms debounce, `:57-60`) → `DashboardView` `filters` state `:35-37` → `useAggregatedData(id \|\| '', filters)` `:49` → `dashboardApi.ts:69` query key, `:74` `JSON.stringify` → `data.py:107-115` parse → `aggregated_data_repo.py:158-162`:

```
AggregatedData.dims[key].astext == str(value)
```

Producers: `DashboardFilters.tsx:160` multiselect `onChange(e.target.value)` → array; `:191` range `onChange((_, newValue) => …)` → `[number, number]`. `str(['North'])` is `"['North']"`; `str([0,100])` is `"[0, 100]"`.

**Verdict: `substantiated`.** `VAL-16-004` corrections both confirmed: the multiselect producer is at **`:160`**, not `:162` (`:162` is the `renderValue` `<Box>`); and **two of four** filter types bind, not one — `select` (`:140`, scalar) and `date` (`:206`, scalar) both send scalars. `range` additionally cannot work as equality even if scalarised.

**Seams:** `aggregated_data_repo.py:158-162` (shape-branching `==` / `.in_([])` / `BETWEEN`, unevaluable → 422); `DashboardFilters.tsx:160,191`; `data.py:107-115`. **Blocked on an unwritten product decision** — whether `range` targets a dimension or a measure; the repository only ever reads `dims`. See §6.2.

**The blast-radius trap (`Rollout Safety`, re-verified):** a 422 from `/data/aggregated` renders at **dashboard** scope — `DashboardView.tsx:181-185` `<Alert severity="error">Failed to load chart data.</Alert>` — not per graph. One bad filter blanks every chart. Prescribed placement is filter-*change* time, not the combined data request.

### CHT-010 — `filterValues` option list never invalidated (MEDIUM)

`FilterField` calls `useFilterValues(dashboardId, filter.name)` **unconditionally** (`DashboardFilters.tsx:126`) and, for `source === 'data'`, uses the response as the entire option list (`:127-130`). Key `['filterValues', dashboardId, filterName]` (`dashboardApi.ts:93`), **no `staleTime`**.

Complete `invalidateQueries` inventory over `frontend/src` — **ten** sites, none naming that key:

| Key | Sites |
|---|---|
| `['admin','users']` ×3 | `UserManagement.tsx:99,112,123` |
| `['admin','registration-requests']` ×2 | `RegistrationRequests.tsx:93,108` |
| `['admin','dashboards']` ×3 | `DashboardManagement.tsx:72,92,111` |
| `['dashboards', id]` | `dashboardApi.ts:84` |
| `['aggregatedData', dashboardId]` | `dashboardApi.ts:86` |

Upload path: `DashboardView.tsx:215-220` → `invalidateAggregatedData(id)` → `dashboardApi.ts:85-86`. Frames refresh; options do not.

**Verdict: `substantiated`; count is ten, not nine** (`VAL-16-004`).

**Owner: DOUBLE-FILED.** `VAL-13-003` names the same root cause and prescribes a second call site (`DashboardView.tsx:218`); CHT-010 prescribes `invalidateFilterValues` in `useInvalidateDashboard` (`dashboardApi.ts:80-88`). `VAL-16-002` rules CHT-010 is the finding of record. See §5.4.

**Seams:** `dashboardApi.ts:80-88` (add the method), `:93` (the key), `DashboardView.tsx:215-220` (the caller), `UploadModal.onUploadComplete`. Composes with CHT-009: a stale option list hands the user a value the current data lacks, and selecting it produces CHT-009's empty frame.

### VAL-16-001 — The "merge" against `FE-007`/`FE-008` mints nothing (MEDIUM)

The report's deferral section opens "FE-007 / FE-008 (phase 13, ruled) … **Merge, not adjacency**", mints no `CHT-` ID, and in the next sentence states "the fix for the shape gap would not by itself close CHT-001" — which by the phase's own vocabulary is the definition of adjacent.

**Verdict: `substantiated`, and the underlying non-duplication is real.** Phase 13's ruling (`99-validation/13-…:405-414`) keeps `FE-008` in phase 13 and hands phase 16 the *consequence*. The report's stronger argument re-verified: `FE-007`'s remedy retypes `GraphDataWithConfig.data` to `Array<Record<string, string \| number>>` and deletes the two casts at `ChartRenderer.tsx:48,70` — after which `row[metricCol]` is **statically typed present** while still `undefined` at runtime. The retyping removes the compiler's only leverage over CHT-001.

**Effect on targets:** none. Remediation ownership of the shape gap stays with phase 13.

### VAL-16-002 — CHT-010 double-files `VAL-13-003` (MEDIUM)

Same root cause, two IDs, two prescriptions, two roadmaps. Both findings are individually correct.

**Verdict: `substantiated`.** **Effect on targets:** CHT-010 is the finding of record and phase 16 owns the remediation; the phase-13 roadmap entry at `99-validation/13-…:439-441` should point at CHT-010 instead of naming a second call site. **Phase 16 may not edit that file** — the correction is a write into phase 13's space. See §5.4.

### VAL-16-003 — CHT-002's proof attributes the loss to the wrong cause (MEDIUM)

Mechanism correct; the Evidence's premise ("present in the response") is **not** — `config.layout` round-trips, `GraphDataResponse.layout` does not. With `undefined`, `{...undefined}` is empty and the `:150` write is a **no-op today**.

**Verdict: `substantiated`.** **Effect on targets — the only sequencing change in the report:** CHT-002 moves out of Step 3 into a **hard co-requisite of CHT-006**, both landing in one commit with `xaxis` merged. Reverting the pair by half leaves the client half inert-or-live depending on the merge.

### VAL-16-004 — Four location references do not resolve; one count wrong (LOW)

| Ref | As filed | Reality | Status |
|---|---|---|---|
| `AggregationService.aggregate_graphs` | CHT-001, CHT-003 | `aggregate_for_dashboard` (`aggregation_service.py:44`) | **Wrong symbol name**; `aggregate_graphs` returns no hit tree-wide |
| `aggregation_service.py:92-94`, `:69,74` | cited | `:93`, `:69`, `:74` | **Correct** |
| `DashboardFilters.tsx:162` | multiselect producer | **`:160`** | **Wrong line** |
| "nine call sites" | CHT-010 | **ten** | **Wrong count** |
| "the one type that binds correctly" | CHT-009 | **two of four** (`select`, `date`) | **Wrong count** |

**Verdict: `substantiated`** (all four re-derived). **Effect on targets:** none — no band moves, no claim changes. Two sit in load-bearing citations: grepping `aggregate_graphs` returns nothing.

### VAL-16-005 — The deferral's "discarded alias" premise is refuted (LOW)

`aggregate_transforms.py::_apply_groupby_aggregations` **honours** a configured alias: `:131` `alias = agg.get("alias", f"{column}_{func_str}")`, `:135` `alias = getattr(agg, 'alias', None) or f"{column}_{func_str}")`, applied at `:147`. The `_{func}` form is the **fallback** for an absent alias, not a discard. The path that ignores alias entirely is `aggregate_for_dashboard` — `Graph` carries no alias field on a metric.

**Verdict: `substantiated`.** **Drift found against the validator's own anchors:** the report cites the two production call sites as `data_worker.py:700-702,781-783`; they are at **`:781-783` and `:862-864`** (HEAD moved). Substance holds — both call `aggregate_for_dashboard` and both read `metric_agg` from `processing_config_dict["settings"]["metric_agg"]` with default `"sum"` (`:780`, `:861`). `calculate_aggregations` is reachable only from `data_worker.py:545` (legacy single-file path) plus tests — no third writer of `aggregated_data`.

**Effect on targets:** none. The deferral stands; the premise sentence is wrong **in the direction that strengthens phase 16** — a second naming path exists that can emit an operator-chosen column name the renderer also cannot name.

### VAL-16-006 — CHT-006's line-branch mechanism stated backwards (LOW)

"overridden by the spread" is wrong; spreading `undefined` is a no-op, so `LineChart.tsx:19-24`'s defaults are **preserved** and become the only titles the frame carries.

**Verdict: `substantiated`.** **Effect on targets:** none — the outcome as filed is correct. The misstatement would mislead a fixer who concluded the defaults needed re-stating after CHT-006 lands. They do not: the moment `layout` is populated the declared title wins the spread.

---

## 3. Cross-cutting architecture and constraints

### 3.1 `processing_configs` → aggregate shape

| Step | Symbol | Behaviour |
|---|---|---|
| 1. Config in | `data_worker.py:780` / `:861` — `metric_agg = processing_config_dict["settings"].get("metric_agg", "sum")` | The **only** thing that decides the `{agg}` half of every measure name |
| 2. Aggregate | `aggregation_service.py:44` `aggregate_for_dashboard` → `:67-71` groupby cols (`graph.dimensions` + filter dims ∩ `df.columns`) · `:74` metric cols (`graph.metrics` ∩ `df.columns`) · `:77-81` **skips the graph entirely** if either is empty · `:93` `.alias(f"{m}_{metric_agg}")` · `:97` `group_by` · `:100-106` `_apply_chart_sorting` | Row shape: dimension names + `{metric}_{agg}` |
| 3. Persist | `data_worker.py:786-797` → `StorageManager.save_aggregates` | `dims` / `metrics` as two JSONB columns (`db/models/aggregated_data.py`) |
| 4. Read | `aggregated_data_repo.py:147-162` `select(...)` — `graph_id`, optional `dashboard_id`, optional `dims[key].astext == str(value)` | **No `ORDER BY`. No `LIMIT`.** |
| 5. Flatten | `data_service.py:208-219` `preview=[{**record.dims, **record.metrics}]` | One `ProcessingResultData` **per row**; `columns` at `:213` is a per-row key list, not a schema |
| 6. Serve | `data.py:146-148` / `:183-185` `extend(item["preview"])`; `:152-158` / `:188-194` `GraphDataResponse(...)` | `response_model=AggregatedDataResponse` (`:41`) |
| 7. Query | `dashboardApi.ts:69` `['aggregatedData', dashboardId, filters]` → `:26-28` `/data/aggregated` | `graphId` **omitted from the key** (plan-11 `C11-8`) |
| 8. Render | `ChartRenderer.tsx:11-75` → `PlotlyChart` / `LineChart` / `TableChart` | Sole producer of every trace in the client |

**Load-bearing consequence:** step 2's **skip** at `:77-81` means a graph whose metric has no matching source column is **absent from the response entirely** — not zero-filled, not errored. The client sees a missing graph, and `DashboardView.tsx:187-206` renders it as nothing at all (the `graphs.length > 0` gate falls to the "No data available for this dashboard" alert at `:202-204` if **all** graphs skip).

### 3.2 Chart type → Plotly trace

| `graph.type` | Path | Trace built by | Discarded |
|---|---|---|---|
| `table` | `ChartRenderer.tsx:123-125` → `TableChart` **directly** | none (`convertToPlotlyData` never called) | every `config` key. This is why the table view shows real values beside a zeroed chart. |
| `line` | `:138` `convertToPlotlyData(graph)[0]` → `LineChart` → `:26` `[data]` → `PlotlyChart` | `makeTrace:39-40` `mode:'lines'`, `type:'scatter'` | traces `[1..N-1]` (CHT-008); `LineChartProps.title/xAxisLabel/yAxisLabel` (`LineChart.tsx:7-9`) never passed — always `''` |
| `bar` | `:142` whole array → `:145-152` `barLayout` | `makeTrace:36-38` `orientation` | `xaxis.title/type/range` after conversion (CHT-002); `layout` (CHT-006) |
| `pie` | `:155` whole array, no layout decoration | `makeTrace:32` `type:'pie'` **with `x`/`y`** | `labels`/`values` never emitted (CHT-007) |

### 3.3 The transform / format layer — and how thin it is

There is **none**. The only client-side formatting is `TableChart.getDisplayValue` (`TableChart.tsx:13-27`): null/undefined → `''`, object → `JSON.stringify`, `^\d{4}-\d{2}-\d{2}` strings → `formatDate(...)`, else `String(value)` (with an `eslint-disable` for `no-base-to-string`). **No number formatting, no locale, no unit, no percent, no currency, no null-vs-zero distinction anywhere.** `ChartRenderer` has none either. Consequence: a measure stored as `null` in JSONB and a measure of `0` are both coerced to the same `0` by `Number(row[metricCol] ?? 0)` — the chart cannot distinguish "no value" from "zero".

### 3.4 Empty / zero / null dataset handling — three states, one message

| State | Where | What the reader sees |
|---|---|---|
| `graphs.length === 0` | `DashboardView.tsx:200-205` | Alert "No data available for this dashboard. Upload data to see charts." |
| `graph.data.length === 0` | `ChartRenderer.tsx:128-133` | `h-64` div, grey text "No data available for this chart" |
| Rows present, measure missing | `ChartRenderer.tsx:57`/`:72` | **A frame with correct categories and a flat zero series.** The only one of the three that looks like data. |
| Error from `/data/aggregated` | `DashboardView.tsx:181-185` | "Failed to load chart data." — **dashboard scope**, all charts |
| No error, but `graph_id` absent from response | (step-3 skip, §3.1) | the graph renders as **nothing** — no placeholder card at all |

The third row is the CRITICAL: it is the only state with no honest signal. Rows 2 and 5 are **indistinguishable from each other** on screen — which is exactly what CHT-009 and CHT-010 both terminate in. Plan-13's `CT-7`/`DP-13-G` option (c) treats this as phase 13's "absent data rendering distinguishably"; phase 16's report treats it as nobody's.

### 3.5 Where a server-side `LIMIT` would silently truncate

**Today: nowhere — the read is unbounded.** Verified: no `limit`/`LIMIT`/`head(`/`max_rows` token anywhere in `aggregated_data_repo.py`; no pagination query parameter on `GET /data/aggregated` (`data.py:52-54` — `dashboard_id`, `graph_id`, `filters` only). Plan-11 `C13-3` states the same at `ab76989`.

**The boundary that would break, in order of arrival:**

1. `PRF-4` adds `LIMIT` to `get_by_graph_id` → `data.py` response shortens → `ChartRenderer` has **no count field, no "showing N of M", no truncation flag** (`GraphDataResponse` declares six fields; none is a total) → the chart renders the first N categories as if complete. **No client-side code path could detect it.**
2. Plan-11 `C11-16` adds `ORDER BY` to the read → today rows come back in whatever order the index scan yields → the `[0]` in CHT-008 and the `groups` insertion order in `:58-64` both change → **series membership becomes nondeterministic across requests**, and `DP-11-B(a)`'s `ORDER BY` is itself a semantics change the response never made.
3. `DP-11-B(c)` adds a total count → `GraphDataResponse` gains a field → **`tests/test_openapi.py`** is the tripwire and plan-12 `AZ-8` holds that model read-only.

**Ownership today:** `PRF-4` + `DP-11-A` + `DP-11-B` = **phase 11** (chooser: Tech Lead + product). The client truncation signal = **phase 13** (`C11-8`, `C13-4`). The **presentation** of a bounded/aggregated response = **phase 16** by plan-11's OUT row — **and no CHT finding names it.**

### 3.6 Row ordering is already nondeterministic (unfiled)

`aggregated_data_repo.py:147-162` issues a bare `select(...)` with **no `ORDER BY`**; `storage_manager.save_aggregates` does a set-based UPSERT, and phase 05's `PB-15` pins the *stored* row order (plan-11 `C11-16`). The client then relies on that order twice: `ChartRenderer.tsx:61-62` `groups[color].x.push(x)` (per-trace category sequence) and `:71-72` (`xVals.push`). **Consequence:** two identical requests can produce differently-ordered series. Not filed by any CHT finding; recorded here because CHT-008's remedy ("the surviving trace is whichever group happened to be first") is a symptom of it.

### 3.7 Shared-type mirror — three declarations, none derived

| Layer | Symbol | Declares |
|---|---|---|
| Server write | `models/types.py::GraphConfigDict` `:138-152` | 11 keys, `total=False` |
| Server read | `models/data.py::GraphDataResponse` `:431-436` | 6 fields; `config: dict[str, Any] \| None` — **untyped** |
| Client mirror | `api.types.ts::GraphDataWithConfig` `:203-216` | 5 config keys (incl. the stripped `metrics`/`orientation`/`barmode`), `data: Data[]` (**wrong shape**), no `metrics`/`dimensions` |

**Measurement (the one-liner the report's cross-analysis rests on, re-derived both sides): renderer names 5 config keys · declaration names 11 · intersection 2.** Nothing reconciles the three. `AGENTS.md`'s "share types via OpenAPI" is aspirational — no generator exists (plan-13 `DP-13-J` option (c): "recorded, not built").

### 3.8 Error and empty states — the chain

`AGENTS.md` L1-L3 chain: `models/enums.py` (`ErrorCode`) → `utils/exceptions.py` (`AppException`, `add_exception_handlers`) → route raises. Client: `shared/api/axiosInstance.ts` interceptor (`:62-64` 429 bypass, `:66` 401, `:126-131` 403+ toast with a login-path exemption) → `shared/api/errorHandler.ts::extractApiError` → `useAuth.ts:85-89` (429 ⇒ `removeToken()`, no toast) → per-feature `errorMessages.ts` (**six** files: `shared/api/`, `features/{auth,admin,dashboards,upload,users}/model/`).

`data.py:99-102` raises `ACCESS_DENIED` 403; `:112-115` `VALIDATION_ERROR` on unparseable `filters`. **`DashboardView.tsx:181-185` is the second renderer** of the same 403 the interceptor toasts — the double-render plan-12 `O-05` and plan-13 record. Plan-12's `AZ-8` will turn the absent-dashboard case from a `500` (generic client fallback) into a `404` with an RFC 7807 body (code-aware branch) — a client-visible change with no authorization content, which plan-12 explicitly assigns to **phase 16's extraction chain**.

### 3.9 Shared seams, named to their owner phase

| Seam | Owner | Phase-16 exposure |
|---|---|---|
| `ChartRenderer.tsx:11-75` adaptation layer + presentation defaults (`:15,17,18`, `:149`) | **phase 13** types it (`FE-007`, `CT-7`); **phase 16** owns the defaults (`C13-6`) | **Two owners, one function.** `CT-7` is blocked on "phase 16's read" |
| `errorMessages.ts` (6 files) + `useAuth.ts:85-89` 429 branch + 4 redirect sites + `adminApi.ts::retrieveTempPassword` + `UserManagement.tsx` + `RegistrationRequests.tsx` | **phase 16** via plan-04 `C04-4` | Phase-16-held, **no CHT finding claims it** |
| `errorHandler.ts` switch + `features/admin/model/errorMessages.ts` code map + 403 double-render | **phase 13 / phase 16** via plan-12 `O-05`, `C12-1` | Phase-16-held, **no CHT finding claims it** |
| `GraphDataResponse` + `data.py` two construction sites | **phase 12 `AZ-8`** (read-only pin) | **CHT-003 collides.** §5.6 |
| `['aggregatedData', …]` query key / `graphId` threading | **phase 13** `CT-1`/`CT-3`, plan-11 `C11-8` | Read-only for phase 16 |
| Server `LIMIT` / total-count field | **phase 11** `PRF-4`, `DP-11-B` | Presentation of it = phase 16, unclaimed |
| `errorMessages.ts` / any-ban enforcement / lint config | **phase 08** `CQLT-*`, `C13-9` | `fe-lint` stays red on arrival |
| Security of the payload (`check_dashboard_access` at `data.py:88-93`) | **phase 12** | Read-only; **`GraphDataResponse` additions become payload surface** |
| `frontend/coverage/**` (15 tracked files) + coverage thresholds | **phase 16** (plan-09 OUT, unnumbered) | Phase 16 owns the gate question |
| Measure **name derivation** (`_{agg}` aliasing) | **phase 05** `DP-002`/`DP-018`/`b4` | CHT-001 leans on it as evidence, not as a target |
| `yoy` / `secondary_y` structural unusability | **phase 05** `DP-009` | Counted in CHT-004's inventory only |

**Phase 15 could not be checked.** `.ai/plans/` held `01`–`14` at read time; no `15-*.md` was on disk (phase 15's plan was being authored concurrently). The brief's "phase 15 owns security" is therefore **unverified, not refuted** — nothing in phase 16's scope was reconciled against it, and the Planner should re-run this seam check once `15-*` lands.

---

## 4. In-flight and already-landed work

| Ref | Symbol / path | Intersects this phase? |
|---|---|---|
| `HEAD` `907e052` | `fix(worker): make the processing-log transitions durable` | **No.** `processing_logs` only |
| `863b81b` | `test(advisory-lock): make the lock_timeout leak guard non-vacuous` | No |
| `ab76989` | `fix(worker): give the aggregate rebuild a declared lock and a bounded wait` | **Yes, adjacent** — wraps the `aggregate_for_dashboard` / `save_aggregates` path (`data_worker.py:781-797`, `:862-878`). Its **line shift** is what invalidated `VAL-16-005`'s `:701,782` anchors |
| `2174895`, `cea2d06`, `b646ef1`, `9a77625`, `a92b546`, `c4c0b14`, `5b23240` | user tx, lifespan, lease, topology docs, audit corpus | No |
| Dirty (34 ` D`) | `frontend/coverage/**` 15 files | **Yes** — destroyed, unrestored, 0 on disk (§1.2) |
| Dirty (34 ` D`) | `.ai/builders/**` 7, `.ai/structure/**` 5, `.ai/models/**` 2, `.ai/templates/**` 2, `.ai/plans/audit-fix-plan.md`, `.ai/audit/templates/audit-final-report.md` | No — **note**: `.ai/structure/map.md` and the `ts_anchors.yaml` / `py_anchors.yaml` maps are deleted, so any anchor table they held is unavailable |
| Untracked | 14 sibling plans + `.ai/tasks/{B1,B2,B3}*.yaml` | Plans 04/09/11/12/13 read (§1.4) |

**No production file in phase 16's scope is dirty.** Every finding's anchor resolves against committed content.

---

## 5. Discrepancies and risks

### 5.1 Stale / drifted anchors

| Anchor | Report says | `907e052` says | Severity |
|---|---|---|---|
| `data_worker.py` call sites | `:701,782` / `:700-702,781-783` | **`:781`, `:862`** | Medium — `VAL-16-005`'s evidence bullets |
| `AggregationService.aggregate_graphs` | CHT-001, CHT-003 | `aggregate_for_dashboard` `:44` | Medium — grep returns nothing |
| `DashboardFilters.tsx` multiselect producer | `:162` | **`:160`** | Low |
| `invalidateQueries` count | "nine" | **ten** | Low |
| "one type binds correctly" | CHT-009 | **two of four** | Low |
| `ChartRenderer.tsx` line refs (all 6 findings) | — | **all resolve exactly** | — |
| `LineChart.tsx:5,19-24,26`, `types.py:105,138-152`, `data.py:425-452`, `data.py:152-158/188-194`, `aggregation_service.py:69,74,93`, `data_service.py:216`, `aggregated_data_repo.py:158-162`, `aggregate_transforms.py:131,135,147`, `api.types.ts:203-216`, `dashboardApi.ts:69,74,80-88,93`, `DashboardView.tsx:35-37,181-185,191-193,215-220`, `DashboardFilters.tsx:48-63,126-130,160,191,198-209,132-213` | — | **all resolve exactly** | — |

### 5.2 Refuted claims and unattributed scope

| Claim | Status |
|---|---|
| "three of the nine lint errors are in a function no finding names" (plan-13 `:2460`, and the brief) | **Wrong on the function.** `convertChartLayoutToPlotly` is named by CHT-002 (`:89-95`) and CHT-006 (`:81`). Right on the *assertion*. |
| "the project's `any` ban is not enforced" | **Half right.** `no-explicit-any` **is** on (`recommendedTypeChecked`); the ban fails because no source writes a literal `any`. The observable symptom is `no-unsafe-*` on inferred `any`. |
| "phase 09 hands phase 16 frontend coverage via `TST-004` and `TST-014`" (plan-13 `C13-8`, and the brief) | **Wrong IDs.** `TST-004` = 34 pytest `xfail` timeouts; `TST-014` = `test_auth_service.py::test_register` tautology. **Both backend.** See §5.5. |
| `docs/07-frontend/data-api.md` (named by plan-12 `AZ-8`'s documentation impact) | **Does not exist.** `docs/07-frontend/` holds `architecture, auth-flow, frontend-security, fsd-structure, pages, upload-ui`. **There is no data-API doc for phase 16 to correct** — a new one is required, per `doc-maintenance-rules.md`. |
| `phase 15 owns security` | **No `15-*.md` was on disk at `907e052`** — `.ai/plans/` held `01`–`14` only, and phase 15's plan was being written concurrently. Nothing in phase 16's scope was checked against it; the seam is **unverified, not absent**. |

### 5.3 Contested ownership — `ChartRenderer.tsx`, two owners

`C13-6` (plan-13) and `VAL-16-001` point the same way and should be reconciled as **one ruling**, not two: the *typing* of the payload (`FE-007`) is phase 13's; the *presentation defaults* (`:15` `'x'`, `:17` `['y']`, `:18` `'v'`, `:149` `'group'`) are phase 16's. `CT-7` is blocked pending "phase 16's read". **This document is that read.** The concrete risk: `CT-7` option (a) *deletes the dead layout converter* — which is exactly the function CHT-006 requires to start working. Deleting it would convert phase 16's HIGH into unimplementable.

### 5.4 Contested ownership — `CHT-010` / `VAL-13-003`

Two IDs, one root cause, two prescriptions (`VAL-16-002`). `VAL-16-002` rules CHT-010 is the record and phase 16 owns the remedy. **But the correction it asks for is a write into phase 13's file** (`99-validation/13-…:439-441`), which phase 16 must not make. Realistic failure: both prescriptions land, `['filterValues', …]` is invalidated from two call sites, and the redundancy is never recorded.

### 5.5 The frontend-coverage hand-over has **no finding ID**

| Source | Says |
|---|---|
| plan-09 frontmatter `:13` | "TST-017's frontend half (phase 16)" — **mislabel**; `TST-017` is "missing integration boundaries", a backend router/service/repository list (`TCO-4`) |
| plan-09 OUT table `:213` | "**Frontend test coverage** \| **phase 16**" — **no ID attached** |
| plan-09 `:745` | "**Frontend coverage is phase 16's** and is not scheduled" — again, no ID |
| plan-13 `C13-8` | "phase 16 is handed … via **`TST-004` and `TST-014`**" — **both backend** |
| brief | "phase 09 hands phase 16 frontend test coverage via `TST-004` and `TST-014`" — **inherits plan-13's error** |

**Net:** the hand-over is real in substance and **unnumbered in form**. There is no `TST-*` identifier a phase-16 block can discharge. Empirically: **13 test files, 170 tests; zero files touch `ChartRenderer.tsx`, `LineChart.tsx` or `TableChart.tsx`.** The nearest neighbours are `PlotlyChart.test.tsx` (the 2-line re-export) and `DashboardView.test.tsx`. `vitest` is configured at `vite.config.ts:52-66` with v8, `jsdom`, thresholds 50/40/45/50 — **and those thresholds have never gated anything, because the run has been red and the coverage tree is deleted.**

### 5.6 `CHT-003` collides with plan-12 `AZ-8`

| | CHT-003's remedy | plan-12 `AZ-8` (`AUTZ-004`, HIGH) |
|---|---|---|
| `models/data.py` aggregated schema | **edits** (adds `metrics`, `dimensions`) | **read-only pin** |
| `api/routes/data.py::get_aggregated_data_endpoint` | **edits** both construction sites | **edits** (adds the cross-dashboard `graph_id` authorization check) |
| `tests/test_data_endpoint.py::TestAggregatedDataEndpointContract` | changes what it pins | **must stay green unmodified** |
| Release risk | additive in JSON | **HIGH** — "`GET /data/aggregated` renders every chart" |

Two HIGH findings from two phases, one endpoint, one model, one contract suite. This is the "two owners in one commit" hazard the phase-13 validator warned about, on the **server** side rather than the client side.

### 5.7 Tests that will break

| Test | Breaks when | Owner of the break |
|---|---|---|
| `formSchemas.test.ts:162` | already red | phase 09 |
| `tests/test_data_endpoint.py::TestAggregatedDataEndpointContract` | CHT-003 adds response fields; `AZ-8` changes 200→403/500→404 | phase 16 **and** phase 12 |
| `tests/test_openapi.py` | CHT-003 / CHT-006 / `DP-11-B(c)` change a published schema | phase 16, phase 11 |
| `tests/test_data_service.py::TestDataServiceIntegration`, `tests/test_services_integration.py::TestDataServiceIntegration` | a `range`/`multiselect` 422 path in `aggregated_data_repo.py` | phase 16 (CHT-009) |
| `filter-persistence.test.tsx` (3 lint errors) | any `DashboardFilters`/`DashboardView` edit | phase 16 if it touches either |
| `useAuth.test.tsx` | only if `C04-4`'s 429 branch is changed | phase 16 **via plan-04**, not via any CHT finding |

### 5.8 Where a "presentation" fix is a data-correctness fix in disguise

| Case | Where | Why it is not a styling change |
|---|---|---|
| **Truncated series drawn as complete** | `ChartRenderer.tsx:142` bar branch takes **all** traces with no count check; `:138` line branch takes `[0]` | A future server `LIMIT` (§3.5) shortens `data[]` and **nothing in the client can detect it**. Today the client's *own* `[0]` is the truncation. |
| **Empty result drawn as zeros** | `ChartRenderer.tsx:57`/`:72` `Number(row[metricCol] ?? 0)` | An unevaluable filter (CHT-009) and a metric that failed to match a source column (CHT-009/CHT-001) both render as **a zero series**, not as "no data". `?? 0` is where "absent" becomes "zero". |
| **Graph silently omitted** | `aggregation_service.py:77-81` `continue` | The graph is **absent from the response**, not empty. The dashboard shows no card and no message. |
| **Nondeterministic series order** | `aggregated_data_repo.py:147` no `ORDER BY` → `:61-62`, `:71-72` | The same data can plot differently on two requests. Nothing in the UI can say so. |
| **N−1 series drawn as one** | `ChartRenderer.tsx:138` | The legend shows 1 entry for N groups; nothing says 2 are missing. |
| **Correct categories over a zero measure** | the CHT-001 chain end-to-end | The frame is *complete-looking*. A page-load check proves nothing — the report's own Step-2 gate must be **quantitative**: the trace `y` array must contain a value `> 0`. |

### 5.9 Documentation that describes a contract that does not exist

| Doc | Says | Reality |
|---|---|---|
| `docs/11-guides/extend-graphs.md:177` | "Bar, line, and pie graphs **all work** with the default `ChartRenderer.convertToPlotlyData()` logic, which **extracts x values from the first dimension column and y values from the first metric column**" | **Doubly false.** The renderer reads `config.x` (defaulting to the literal `'x'`) and `config.metrics[0]` (defaulting to the literal `'y'`) — never "the first dimension/metric column". And bar/line/pie are exactly the three types broken (CHT-001, CHT-007, CHT-008). |
| `docs/02-dashboards/dashboards-api.md:356-359` | graph `config` example with `y_axis`, `orientation`, `barmode`, `colors` | `y_axis` and `colors` are **not** `GraphConfigDict` keys; `orientation`/`barmode` are **stripped at write**. `docs/09-database/schema-core.md:193-196` repeats it. |
| `models/data.py:449` (`json_schema_extra`) | `"layout": {"title": "Sales Chart"}` | Never emitted (CHT-006) |
| `models/data.py:428` (docstring) | "…and Plotly.js data" | It is row dicts, not Plotly traces (`FE-007`) |
| `docs/07-frontend/pages.md:151` | `graph_id` optional on `/data/aggregated` | The client never sends it (`C11-8`) — **phase 13's doc** |
| `docs/08-security/access-control.md:116` | "Validates dashboard access before returning data" | True but **incomplete** — `AZ-8` finds `graph_id` unchecked |
| `docs/03-processing/processing-api.md:257-261`, `docs/00-overview/data-flow.md:73-75`, `docs/99-reference/swagger.md:164` | endpoint surface | Accurate |

**None of these is named by any CHT finding.** Per `doc-maintenance-rules.md`, a doc correction is required in the same commit as the code it describes.

---

## 6. Decision points for the Planner

> Genuine technical or product uncertainty. **No option is selected here.**

### 6.1 `CHT-004` — which config keys survive?

| Option | Shape | Cost |
|---|---|---|
| (a) **Narrow** `GraphConfigDict` to `x`, `y`, `color` | API rejects the other eight with a 422 | Removes the false affordance immediately; **breaking** for any stored graph and any caller |
| (b) **Promote** `title` and `y` to honoured keys, delete the other six | smaller blast radius | Two real changes; `y` alone does not close CHT-001 (the name is still `revenue_sum`) |
| (c) **Keep all, document as reserved** | no code change | Keeps eight accepted-and-ignored keys — the finding's own subject |

**Chooser:** Tech Lead + product. **Constraint:** must not ship before `CHT-003`'s response shape lands (report Step 4 gate), or narrowing turns a silently-ignored key into a rejected one exactly when the client loses its only workaround.

### 6.2 `CHT-009` — does a `range` filter target a dimension or a measure?

Unrecorded anywhere in the repository; `aggregated_data_repo.py` only ever reads `dims`. `BETWEEN` on a JSONB dimension is not expressible as a numeric range test.

| Option | Shape |
|---|---|
| (a) `range` targets a **dimension** | Needs a documented string-range encoding, or is rejected as unevaluable |
| (b) `range` targets a **measure** | Repository must read `metrics` too — a **new capability**, not a fix |
| (c) **`range` is removed from the client switch** | `DashboardFilters.tsx:179-196` and the `FilterConfigDict` type lose the case |

**Chooser:** Tech Lead + product. **Independently unblocked:** the `multiselect` list case (`.in_([])`) needs no decision and should not wait for one.

### 6.3 `CHT-002` + `CHT-006` — merge or drop the forced `category`?

`{type:'category', ...convertedLayout?.xaxis}` vs dropping the constant. The report prefers the merge and notes the forced `category` may be load-bearing for the bar renderer — **the code contains no comment saying so**, so that is unverified.

**Chooser:** Planner, after a one-line check of whether `PlotlyChart`/`react-plotly.js` depends on a categorical axis for bar rendering. **Constraint from `VAL-16-003`:** one commit, merge present, never revert by half.

### 6.4 Where does the empty state live — and who owns it?

Three states collapse into one message (`§3.4`). The three candidate owners each already hold a different claim: phase 13 (`b7`/`CT-7` "absent data rendering distinguishably"), phase 11 (`DP-11-B(c)` count field), phase 16 (`CHT-009`/`CHT-010` terminate there). **No CHT finding claims the empty-state rendering itself.**

**Chooser:** Coordinator. This is the seam where three phases' blocks meet and none of them names it.

### 6.5 Does phase 16 accept the four hand-overs no CHT finding names?

`C04-4` (plan-04), `O-05`/`C12-1` (plan-12), `DP-11-B` presentation (plan-11), unnumbered frontend coverage (plan-09). Accepting them roughly **doubles** the phase's scope beyond its 10 findings; declining them leaves plan-13's `CT-5`/`CT-10` hard-blocked and plan-04's `C04-4` unexecuted.

**Chooser:** Coordinator. **The factual input to that ruling:** phase 16's own report names **none** of the reserved symbols — `errorMessages.ts` (all six files), `useAuth.ts:85-89`, `errorHandler.ts`, `adminApi.ts::retrieveTempPassword`, `UserManagement.tsx`, `RegistrationRequests.tsx` — so the contention with `C13-1` is **nominal for the chart work** and real only if the hand-overs are accepted.

### 6.6 `CHT-003` vs `AZ-8` — serialise or coordinate?

Same model, same endpoint, same contract suite. Options: serialise (phase 12 first, then phase 16), or one joint commit, or phase 16 defers `CHT-003` to phase 12's block.

**Chooser:** Coordinator. **Note:** `CHT-001`'s "smallest change" (`config.y` + `Literal`s) is **independent** of `CHT-003` and needs no ruling, so nothing about `AZ-8` blocks it.

### 6.7 The `filter-values` staleness window

`['filterValues', …]` has **no `staleTime`** (`dashboardApi.ts:90-97`), so TanStack applies its global default. If that default is finite, the option list also self-refreshes on a timer and the "session-scoped defect" framing in CHT-010's Consequence is conditional on a global default the report never read.

**Chooser:** Planner — read the `QueryClient` default (`app/` providers) before sizing the finding. **Constraint:** an explicit `staleTime: Infinity` would make `invalidateFilterValues` load-bearing; a finite default would partially mask it.

### 6.8 Coverage: gate or not?

`vite.config.ts:59-64` declares thresholds 50/40/45/50. They have never gated anything. Options: enforce them (they will fail — `ChartRenderer.tsx` has **zero** test coverage and 6 of 10 findings land there), lower them, or record them as advisory. **Chooser:** Planner, jointly with §6.5's coverage hand-over, which has no finding ID to discharge.

---

## 7. Coverage ledger

| ID | Verdict | Evidence anchor(s) |
|---|---|---|
| **CHT-001** | substantiated | `ChartRenderer.tsx:17,26,57,72`; `models/types.py:138-152` (11 keys, no `metrics`); `models/graph.py:15,45`; `aggregation_service.py:93`; `data_service.py:216`; `api.types.ts:212` (client declares the stripped key); shape sniff `:21-23` does not fire |
| **CHT-002** | substantiated (latent); observable effect **refuted** by `VAL-16-003` | `ChartRenderer.tsx:147-151` overwrite after `:148` spread; converter `:89-95`; pie `:155` keeps it; `graph.layout` never populated (`data.py:152-158,188-194`) |
| **CHT-003** | substantiated; **owner collision** | `models/data.py:431-436` (6 fields, no `metrics`/`dimensions`); exactly 2 construction sites `data.py:152-158,188-194`; `db/models/graphs.py:70-80`; `api.types.ts:203-216`; plan-12 `AZ-8` read-only pin |
| **CHT-004** | substantiated | 11 declared × 5 read × **intersection 2**; `DashboardView.tsx:191-193` renders `graph.name`; no `config.{title,xaxis,yaxis,layout,secondary_y,sort_x,sort_color}` in `frontend/src` |
| **CHT-005** | substantiated | `ChartRenderer.tsx:18,36-38` (bar-only), `:149`; neither key in `GraphConfigDict`; no graph editor in `frontend/src` to be broken by `Literal` tightening |
| **CHT-006** | substantiated | `models/data.py:435`, `:449` example, `:428` docstring; 2 sites pass 5 of 6 fields; converter early return `ChartRenderer.tsx:81`; `LineChart.tsx:19-24` defaults **preserved** (not overridden); `types.py:105` `AxisConfig.label` dead |
| **CHT-007** | substantiated; **upgraded** to a shipped-artefact claim | `ChartRenderer.tsx:28-43`, `:30-33`; no `labels`/`values` assignment anywhere in file; `:29` `Record<string, unknown>`; `@types/plotly.js` `PieData`; pie `y:[0,0]` from CHT-001 |
| **CHT-008** | substantiated; **owner contested** | `ChartRenderer.tsx:64,74,138,142`; `LineChart.tsx:5` `data: Data`, `:26` `[data]`; insertion-order dependence `:58-64`; plus no `ORDER BY` upstream |
| **CHT-009** | substantiated; 2 corrections applied | `aggregated_data_repo.py:158-162` `str(value)`; `DashboardFilters.tsx:160` (not `:162`) array, `:191` range, `:140`/`:206` scalars ⇒ **2 of 4**; chain `:48-63`→`:49`→`dashboardApi.ts:69,74`→`data.py:107-115`; dashboard-scope error `DashboardView.tsx:181-185` |
| **CHT-010** | substantiated; count is **ten**; **double-filed** | 10 `invalidateQueries` sites verified (`DashboardManagement.tsx:72,92,111`; `RegistrationRequests.tsx:93,108`; `UserManagement.tsx:99,112,123`; `dashboardApi.ts:84,86`); key `dashboardApi.ts:93` no `staleTime`; caller `DashboardView.tsx:215-220`; backend `filter_values.py:38-58` reads the same rows |
| **VAL-16-001** | substantiated | Report defers `FE-007`/`FE-008` under "Merge, not adjacency" while minting no ID and stating adjacency in the next sentence; `ChartRenderer.tsx:48,70` casts; `99-validation/13-…:405-414` |
| **VAL-16-002** | substantiated | CHT-010's own Observation names `VAL-13-003`; two prescriptions, two sites (`dashboardApi.ts:80-88` vs `DashboardView.tsx:218`); `99-validation/13-…:130-171,439-441` |
| **VAL-16-003** | substantiated | `ChartRenderer.tsx:146,138` read `graph.layout`; `data.py` never populates it; `{...undefined}` empty ⇒ `:150` is a no-op today |
| **VAL-16-004** | substantiated (4 refs) | `aggregation_service.py:44`; `DashboardFilters.tsx:160`; 10 vs 9; 2 of 4 vs 1 |
| **VAL-16-005** | substantiated; **its own anchors drifted** | `aggregate_transforms.py:131,135,147` honours alias; `graphs.py` has no alias field; call sites are `data_worker.py:781,862` (report: `:701,782`); `calculate_aggregations` only `data_worker.py:545` |
| **VAL-16-006** | substantiated | `LineChart.tsx:19-24` + `:23` `...layout` with `layout===undefined`; converter returns `undefined` at `:81` |

**Tally — 16 IDs: 16 substantiated · 0 stale · 0 refuted · 0 drifted (as findings) · 0 already-fixed.** Two claims are *narrowed* rather than sustained: CHT-002's observable effect (→ latent) and CHT-009's "one type binds" (→ two of four). `VAL-16-005` is substantiated with its **evidence line numbers** corrected.

**Already fixed since the baseline: none.** No CHT or VAL-16 finding has been closed by the ten commits between `d008f555` and `907e052` — all ten touch worker, transaction, lease or lifespan code, and `src/mkobi/**` and `frontend/src/**` are both clean in the worktree.

