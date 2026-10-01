---
phase: 16-chart-presentation-contract
executed: 2026-09-30
executor: validator
problems-only: true
findings: 6
by-severity:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 3
  LOW: 3
baseline: d008f555f5a2e1b3adb397c4bc67d95ed9c964c5
baseline-dirty: "69 paths — 34 D (.ai/builders/** 7, .ai/structure/** 5, .ai/models/** 2, .ai/templates/** 2, .ai/plans/audit-fix-plan.md, .ai/audit/templates/audit-final-report.md, frontend/coverage/** 15), 14 M (.dockerignore, docker/Dockerfile, docker/docker-compose.yml, docker/docker-compose.override.yml, src/mkobi/{app,core/task_queue,rq_worker_wrapper,services/data_service,services/file_processing,workers/data_worker}.py, tests/{test_config,test_data_service,test_rq_worker,test_upload_api}.py), 21 ?? (.ai/audit/01..16 + 99-validation, .ai/plans/01-*, .ai/plans/02-*, tests/test_app_lifespan.py, tests/test_task_queue.py). The input recorded 68; the delta is audit directories created by sibling runs after it baselined. frontend/coverage/ is absent on disk; frontend/ is otherwise unmodified."
---

# Phase 16 — Validated Findings

## Summary

`HEAD` is the same commit the input baselined on — `d008f555` — so no anchor drifted, and every
line reference in the input resolves to the line it names. All ten findings were re-derived from the
executing path, and the phase's own declared gap — the one it named as load-bearing and left open —
is now closed. The input could not produce aggregate rows for its probe graph, so CHT-001's
consequence chain stopped at the alias rule. It is now closed end to end with production code on both
sides: `AggregationService.aggregate_for_dashboard` was executed on a real Polars frame and produced
served rows keyed `{category, region, revenue_sum}` carrying `revenue_sum: 20.0`; the real
`convertToPlotlyData` was then executed against those exact rows and produced
`{"x":["North","South"],"y":[0,0],"type":"bar","name":"B","orientation":"v"}` — correct categories,
a flat zero series, and the non-zero measure present in the same row. Every link of CHT-001 verifies
independently, and the phase-16 rubric names this shape in its own CRITICAL clause
(*"a declared measure nothing reads so the frame is drawn from something else"*); the band is
sustained on re-derived evidence, not inherited. Eight of the ten findings reproduce as filed. Six
claims do not survive intact, and every one of them is a mechanism, a proof or a count — not a
finding: CHT-002's evidence conflates `config.layout` with the never-populated
`GraphDataResponse.layout`, and its consequence is therefore attributed to the wrong cause; CHT-006's
line-branch mechanism is stated backwards; CHT-009 mis-anchors the multiselect producer and claims
one of four filter types binds where two do; CHT-010's `invalidateQueries` inventory is ten sites,
not nine; and the deferral's premise that a configured `alias` is discarded is refuted. Two audit-level
defects are recorded: the "merge" declared against phase 13's `FE-007`/`FE-008` is not a merge and
mints nothing, and CHT-010 re-files `VAL-13-003`'s root cause under a second identifier while
prescribing a different implementation at a different site. The empty CRITICAL band for this report is
upheld on re-derived evidence.

## Findings

### VAL-16-001 — The "merge" recorded against `FE-007`/`FE-008` mints nothing and claims a shared cause the input itself denies

**Severity** — MEDIUM

**Zone** — "Cross-Phase Conflict, Ownership and Merge"

**Observation** — The input's *Deferrals and cross-references* section opens with
**"FE-007 / FE-008 (phase 13, ruled) … Merge, not adjacency: this is one defect with one remedy, in
one function, and the phase-13 ruling already assigned it."** No `CHT-` identifier is minted for it.
`CHT-001` through `CHT-010` contain no shape-gap claim, and the input says so:
*"Nothing in CHT-001 to CHT-008 re-files it."* A merge adjudicates a finding that two phases filed
against one root cause, or a finding filed under a phase that does not own it. Here phase 16 filed
nothing, so there is no finding to merge and no identifier in phase 13's space is touched. The label
also contradicts the input's own reasoning in the next sentence: *"the fix for the shape gap would
not by itself close CHT-001"* — which is, by this phase's own fixed vocabulary, the definition of an
adjacent concern.

The underlying non-duplication is real and was re-derived here. Phase 13's ownership ruling 2
(`99-validation/13-client-tier-validated-findings.md:405-414`) says FE-008 stays in phase 13 and that
what phase 16 carries forward is *"the consequence, not the fix … it currently defaults `xCol` to
`'x'` and `metricCols` to `['y']` when `config` is absent (`ChartRenderer.tsx:15,17`)"*. The input
did inherit exactly that and filed it as CHT-001; `ChartRenderer.tsx:15,17` are `const xCol = config.x
|| 'x'` and `const metricCols = config.metrics || ['y']` as cited. Its claim that FE-007's fix does
not close CHT-001 was tested and holds, and holds for a stronger reason than the one given: FE-007's
remedy is to retype `GraphDataWithConfig.data` to `Array<Record<string, string | number>>` and delete
`as unknown as Record<string, unknown>[]` at `ChartRenderer.tsx:48,70`, after which `row[metricCol]`
is *statically typed* as a present value while remaining `undefined` at runtime — the fix removes the
compiler's only leverage over CHT-001.

**Evidence** — `ChartRenderer.tsx:15,17` against `99-validation/13-client-tier-validated-findings.md:405-414`;
the absence of any shape-gap claim across the ten filed findings; `api.types.ts:2,207,209-215` and
`ChartRenderer.tsx:48,70` for the FE-007 remedy as filed.

**Consequence** — A reader scanning for remediations finds a word that promises phase 16 has
superseded phase 13's identifiers on the chart payload, in a section whose own text says phase 16
filed nothing. The risk is not cosmetic: this audit has already had one instance of a phase
adjudicating another phase's finding space (phase 13's VAL-13-006 against phase 11's PERF-001), and
phase 13's validator itself warned that routing one function to two phases *"would put two owners on
one function in one commit and neither would finish it."*

**Recommendation** — Relabel the entry from "merge, not adjacency" to a deferral, and keep the
substantive sentence, which is correct. Remediation ownership of the shape gap stays with **phase 13**
(`FE-007`, `FE-008`); do not renumber, supersede or re-file either identifier from this report.

### VAL-16-002 — CHT-010 re-files `VAL-13-003`'s root cause under a second identifier and prescribes a different fix at a different site

**Severity** — MEDIUM

**Zone** — "Cross-Phase Conflict, Ownership and Merge"

**Observation** — `VAL-13-003`, already sustained in the validated record, is the same defect: the
`['filterValues', dashboardId, filterName]` query key backing every `source:'data'` filter's option
list is named by no `invalidateQueries` site. The input says so in its own CHT-010 — *"This
adjudicates **VAL-13-003** … The validator is correct on both halves and this finding confirms it at
runtime-independent cost"* — and then mints `CHT-010` anyway. Two identifiers now name one root cause,
in two files that are both read as authoritative.

The two reports also prescribe different implementations at different sites. `VAL-13-003` prescribes
*"one `invalidateQueries` call with a `['filterValues', dashboardId]` prefix in
`DashboardView.tsx:218`"*. CHT-010 prescribes adding `invalidateFilterValues` to
`useInvalidateDashboard` (`dashboardApi.ts:80-88`) and calling it from `UploadModal.onUploadComplete`.
Both are one-line fixes; the point is that a team executing the two roadmaps lands the same cache key
invalidated twice, or lands one and inherits a stale docstring from the other.

**Evidence** — CHT-010's own Observation and its second Evidence bullet against
`99-validation/13-client-tier-validated-findings.md:130-171` and its Roadmap insertion at `:439-441`.
Both the finding and the adjudication are correct; only the double filing and the divergent
prescription are the defect.

**Consequence** — One defect, two owners, two roadmaps, neither cross-referencing the other's
implementation. This is the exact hazard phase 13's validator named when it declined to move the
client half of PERF-001 into phase 13's own findings.

**Recommendation** — Keep **CHT-010** as the finding of record — it is the more detailed of the two
and it carries the composition with CHT-009 — and amend the phase-13 roadmap entry to point at
`CHT-010` instead of prescribing a second call site. One identifier, one prescription, one owner.
Phase 16 owns the remediation; `VAL-13-003` is not renumbered.

### VAL-16-003 — CHT-002's proof and its consequence attribute the loss of the x-axis to the overwrite, when the overwrite has nothing to overwrite

**Severity** — MEDIUM

**Zone** — "Which Side Moves: Code or Documentation"

**Observation** — CHT-002's mechanism is correct and was re-derived: `ChartRenderer.tsx:147-151`
builds `{...convertedLayout, barmode, xaxis: {type: 'category'}}`, so the write at line 150 does
replace the object the converter produced at `:89-95`, and the two pie-vs-bar sites do disagree.
Executing the real `convertChartLayoutToPlotly` on a real layout confirms the converted object is
`{"title":{"text":"Region"},"type":"category","range":[0,100]}`.

Two things around that mechanism do not hold. First, the Evidence field says the discarded value is
*"present in the response"* because `config.layout` round-trips. It is not: the renderer reads
`graph.layout` — the response member — at `:146` and `:138`, and the response member is never
populated (CHT-006, confirmed below). `config.layout` is a *different field* that nothing reads. The
executed bar layout is `{"barmode":"group","xaxis":{"type":"category"}}` today, and would be
byte-identical with the recommended merge applied, because `convertChartLayoutToPlotly` returns
`undefined` and `{...undefined}` is empty. Second, the Consequence — *"Every bar chart on every
dashboard loses its configured x-axis title"* — is true of the product but is caused by CHT-006, not
by CHT-002. CHT-002's own contribution is nil today and becomes a second, independent loss the
moment CHT-006 is fixed without it.

**Evidence** — The real `convertChartLayoutToPlotly` executed on `{title:'Configured Layout Title',
xaxis:{title:'Region',type:'category',range:[0,100]}, yaxis:{title:'Revenue'}}` returns
`{"title":{"text":"Configured Layout Title"},"xaxis":{"title":{"text":"Region"},"type":"category","range":[0,100]},"yaxis":{"title":{"text":"Revenue"}}}`;
the same function executed on `undefined` returns `undefined`; the bar branch's object built from
the second is `{"barmode":"group","xaxis":{"type":"category"}}`, and built from the first it is
`{"title":{…},"xaxis":{"type":"category"},"yaxis":{"title":{"text":"Revenue"}},"barmode":"group"}` — the
`xaxis.title` and `xaxis.range` gone, exactly the discard claimed. So the mechanism is real and the
proof is real; what is missing is that the value cannot arrive.

**Consequence** — A reader repairing CHT-002 first will change one line, re-run the dashboard, and
see no difference, and will conclude the fix failed. The roadmap's own sequencing note places this
work in Step 3, which is gated only on Step 1 (the measure name) — so the gate does not hold it, and
a team following the report lands a fix with no observable effect and no recorded reason why.
Reversing the order the other way is what actually matters: **CHT-006 must not ship without CHT-002**,
or populating `layout` converts a latent discard into a live one.

**Recommendation** — Keep CHT-002 at HIGH; the defect and its remedy are unchanged. Correct the
Evidence to say the value is present in `config.layout` and absent from `GraphDataResponse.layout`,
and move CHT-002 out of Step 3 into a hard dependency of the CHT-006 step: the two must land in one
commit, `xaxis` merged, not replaced.

### VAL-16-004 — Four location references in the input do not resolve, and one derived count is wrong

**Severity** — LOW

**Zone** — "The Claim Re-Derived from the Executing Path"

**Observation** — Four references were resolved mechanically and three of them do not resolve to what
the input says they do. (i) `AggregationService.aggregate_graphs`, cited in CHT-001 and CHT-003, does
not exist; the method is **`aggregate_for_dashboard`** (`aggregation_service.py:44`). The cited lines
are correct — `:92-94` is the alias expression and `:69,74` the two comprehensions — so the claims
re-derive and only the symbol name is wrong. (ii) The multiselect array producer CHT-009 places at
`DashboardFilters.tsx:162` is at **`:160`**; line 162 is the `renderValue` `<Box>`. (iii) CHT-010
states the `invalidateQueries` inventory is *"nine call sites"* and then enumerates ten:
`['admin','users']`×3, `['admin','registration-requests']`×2, `['admin','dashboards']`×3,
`['dashboards', id]`, `['aggregatedData', dashboardId]`. The enumeration is correct and complete; the
total is not. (iv) By the same counting slip CHT-009 states that a `select` filter *"is the one type
that binds correctly"*; the `date` branch at `:198-209` also sends a scalar, so two of four types
bind.

**Evidence** — `src/mkobi/services/aggregation_service.py:44` (definition; the name `aggregate_graphs`
returns no hit anywhere in the tree) against CHT-001 and CHT-003; `DashboardFilters.tsx:160` against
CHT-009's `:162`, and `:191` and `:198-209` against its "one type" claim; a ten-hit enumeration of
`invalidateQueries` over `frontend/src` against CHT-010's "nine".

**Consequence** — No claim changes and no band moves. Two of the four sit in load-bearing citations
though: a reader who greps for `aggregate_graphs` finds nothing and may conclude the report was
fabricated rather than that it misnamed a symbol.

**Recommendation** — Correct `aggregate_graphs` to `aggregate_for_dashboard` at both sites, the
multiselect anchor to `:160`, the count to ten, and "the one type" to "two of the four types".

### VAL-16-005 — The deferral's premise that a configured `alias` is discarded is refuted; the deferral itself still holds

**Severity** — LOW

**Zone** — "Which Side Moves: Code or Documentation"

**Observation** — The input defers name derivation to phase 05 on the ground that the
`f"{m}_{metric_agg}"` aliasing *"and the discarding of the configured `alias`"* are name derivation
phase 05 owns. The second half is not what the code does. `_apply_groupby_aggregations`
(`aggregate_transforms.py:126-148`) reads the configured alias and **honours** it —
`alias = agg.get("alias", f"{column}_{func_str}")` at `:131` and
`alias = getattr(agg, 'alias', None) or f"{column}_{func_str}"` at `:135`, applied at `:147`. The
`f"{column}_{func_str}"` form is the *fallback* for an absent alias, not a discard. It is
`aggregate_for_dashboard` — the graph serving path, the only path the worker calls
(`data_worker.py:701,782`) — that never consults an alias at all, because `Graph` has no alias
field on a metric.

**Evidence** — `aggregate_transforms.py:131,135,147` read directly; `data_worker.py:700-702,781-783`
for the only two production call sites, both `aggregate_for_dashboard`; a whole-tree search for
`calculate_aggregations` returns `data_worker.py:509` (the legacy single-file path) and tests
(`tests/test_data_transformations.py`) — no third writer of `aggregated_data`.

**Consequence** — The deferral's reasoning is wrong in a direction that makes phase 16's claim
*stronger*, not weaker: there is now a second naming path in the tree that can emit an
operator-chosen column name into a frame, and phase 16's own renderer cannot name that column
either. The deferral remains correct as a deferral — the name is derived upstream, phase 05 owns it,
and CHT-003's remedy (serve the stored measure names) makes the derivation question moot for the
presentation tier — but the premise sentence should not stand as written.

**Recommendation** — Correct the deferral to say `aggregate_for_dashboard` ignores any configured
alias, and record that the legacy `calculate_aggregations` path honours one where it is reachable.
No re-file: the presentation consequence of an unnameable column is already inside CHT-001 and
CHT-003.

### VAL-16-006 — CHT-006's line-branch mechanism is stated backwards; its stated outcome is right

**Severity** — LOW

**Zone** — "The Claim Re-Derived from the Executing Path"

**Observation** — CHT-006 says the line branch *"passes `undefined` into `LineChart`, whose own
`{title, xaxis, yaxis}` defaults (`LineChart.tsx:19-24`) are then overridden by the spread"*. They
are not overridden; they are **preserved**, because spreading `undefined` is a no-op
(`LineChart.tsx:23` — `...layout` with `layout === undefined`). The outcome the input then states is
correct and is what the merge produces.

**Evidence** — `LineChart.tsx:19-24` with `layout={convertChartLayoutToPlotly(graph.layout)}` at
`ChartRenderer.tsx:138`; executing the same object literal over `undefined` yields
`{"title":{"text":""},"xaxis":{"title":{"text":""}},"yaxis":{"title":{"text":""}}}` — the defaults,
intact. Every field `convertChartLayoutToPlotly` maps is still unreachable, because the function
returns `undefined` at `:81` before it reads anything.

**Consequence** — None to the finding. The line chart's title-less, axis-title-less frame is real
and correctly described; only the word "overridden" misstates why, and the misstatement would
mislead a fixer who concluded the defaults needed re-stating after CHT-006 lands (they do not — the
moment `layout` is populated the declared title simply wins the spread).

**Recommendation** — Replace "overridden by the spread" with "survive the spread of `undefined`
and are then the only titles the frame carries".

## Audited Findings — Dispositions

Identifiers are preserved. The disposition vocabulary is this phase's; the band column is the audited
phase's own rubric, applied by effect and blast radius as it stands at `d008f555`.

| ID | Band carried | Band implied | Disposition | What reproduced it, or refuted it |
|---|---|---|---|---|
| CHT-001 | CRITICAL | CRITICAL | **confirmed, and the input's own declared gap closed** | All four links verified independently. (a) The real `GraphCreate` was executed with a config carrying `metrics`, `orientation` and `barmode` alongside declared `x`, `y`, `color`; it returned `{color, layout, title, x, y}` with the three undeclared keys dropped, no error, no warning. (b) `GraphConfigDict.__annotations__` resolves to 11 keys, none of them `metrics`; the only writers of `graph.config` are the create/update routes through `GraphCreate`/`GraphUpdate`, so nothing else can populate it. (c) `ChartRenderer.tsx:17` is `const metricCols = config.metrics \|\| ['y']` and `:26` is `const metricCol = metricCols[0]`. (d) The real `AggregationService.aggregate_for_dashboard` was executed and produced metric keys `['revenue_sum']`. **Gap closed:** the real `convertToPlotlyData`, extracted from the file and executed on those real served rows, returned `{"x":["North","South"],"y":[0,0],"type":"bar","name":"B","orientation":"v"}` — the frame the report says the product draws. The shape sniff at `:21-23` does not rescue it: it needs a row carrying both `x` and `y`, and served row keys are dimension names plus `{metric}_{agg}`. |
| CHT-002 | HIGH | HIGH | confirmed; **proof and attribution corrected** (VAL-16-003) | The discard is real: `:147-151` spreads then overwrites `xaxis`, and the converter's output at `:89-95` was executed and is `{"title":{"text":"Region"},"type":"category","range":[0,100]}`. The Evidence's premise that the value is in the response is not — `graph.layout` is never populated — and with `undefined` the line changes nothing observable. Band sustained on the rubric's effect clause: a bar chart configured with an x-axis title shows none. |
| CHT-003 | HIGH | HIGH | confirmed | `GraphDataResponse` declares six fields (`data.py:431-436`) and neither `metrics` nor `dimensions`; a whole-tree search for `GraphDataResponse` returns exactly two construction sites (`data.py:152,188`), neither in a test, neither passing either member; `GraphDataWithConfig` (`api.types.ts:203-216`) declares neither. "Never" is sustained. |
| CHT-004 | MEDIUM | MEDIUM | confirmed; count of eight verified | `GraphConfigDict` declares 11; the renderer reads 5 (`x`, `color`, `metrics`, `orientation`, `barmode`); the intersection is 2. 11 − 2 = 9 unrendered, of which `yoy` is deferred, leaving **eight**: `y`, `xaxis`, `yaxis`, `title`, `layout`, `secondary_y`, `sort_x`, `sort_color`. A search over `frontend/src` for `config.title`, `config.xaxis`, `config.yaxis`, `config.layout`, `config.y`, `secondary_y`, `sort_x` and `sort_color` returns nothing. `DashboardView.tsx:191-193` renders `graph.name` as the heading. The LOW band is correctly empty. |
| CHT-005 | HIGH | HIGH | confirmed | Same executed `GraphCreate` readback: `orientation` and `barmode` are absent while `x` and `color` survive. Executed traces carry `"orientation":"v"` and the executed bar layout carries `"barmode":"group"` — the defaults are the only values that can arrive, exactly as claimed. |
| CHT-006 | HIGH | HIGH | confirmed; **line-branch mechanism corrected** (VAL-16-006) | `data.py:435` declares `layout: ChartLayoutConfig \| None = None`; the two construction sites pass five of six fields. Executed: `convertChartLayoutToPlotly(undefined)` returns `undefined` for every chart. All eleven mapped fields are unreachable. Outcome as filed; the word "overridden" is wrong. |
| CHT-007 | HIGH | HIGH | confirmed, **and upgraded from a library-behaviour claim to a shipped-artefact claim** | The shipped typings settle it: `@types/plotly.js` `PieData` (`lib/pie.d.ts:85-105`) picks `labels` from `PlotData` and declares `values`; the only `x`/`y` in the file belong to `PieDomain` (`:58-60`), which the code does not set. Executed pie traces are `{"x":[…],"y":[…],"type":"pie","name":"B"}` — no `labels`, no `values`, for any type. The code's `const trace: Record<string, unknown>` at `:29` is why `tsc` accepts it. Sibling ruling VAL-13-002 (plotly defaults `type` to `scatter`) was checked and does not apply: `type` is set explicitly. The CRITICAL clause was tested and fails its second conjunct — the frame is empty, not complete-looking. |
| CHT-008 | HIGH | HIGH | confirmed by execution | Executed against the real served rows with `config.color` set, `convertToPlotlyData` returns **2** traces (`name:"B"`, `name:"A"`); `ChartRenderer.tsx:138` indexes `[0]`; `LineChart.tsx:26` re-wraps as `[data]`. N−1 dropped, confirmed. The bar branch at `:142` passes the whole array, as filed. |
| CHT-009 | MEDIUM | MEDIUM | confirmed; two corrections (VAL-16-004) | `aggregated_data_repo.py:158-162` is `dims[key].astext == str(value)`. `DashboardFilters.tsx:160` sends an array for `multiselect` and `:191` sends `number \| number[]` for `range`; `str(['North'])` is `"['North']"`. The filter does reach the request (`:48-63` debounce → `DashboardView` state → `dashboardApi.ts:69,74` → `data.py:107-115`). The MEDIUM band is sustained, and the reason the input gives is the right one: `ChartRenderer.tsx:128` renders the explicit text *"No data available for this chart"*, so the CRITICAL clause's second conjunct — nothing on screen distinguishes this from the truth — is not met. That test is recorded because the rubric's CRITICAL bullet names *"a selection the control reports as applied that the request never carries"* almost verbatim, and the differentiator is the visible emptiness, not the absence of a wrong number. |
| CHT-010 | MEDIUM | MEDIUM | confirmed; **double-filed** (VAL-16-002) | `DashboardFilters.tsx:126-127` reads `useFilterValues(dashboardId, filter.name)` and uses the response as the whole option list; the key is `['filterValues', dashboardId, filterName]` (`dashboardApi.ts:93`) with no `staleTime`. The input's enumeration is complete and correct; only its total is wrong (ten, not nine). None of the ten names the key. `DashboardView.tsx:215-220` calls `invalidateAggregatedData` on upload and nothing else. `VAL-13-003` is sustained and this finding is the same root cause. |

**Tally: 10 audited findings — 10 confirmed, 0 re-graded, 0 re-typed, 0 merged, 0 withdrawn, 0
unsettled. 6 validation-level findings — 3 MEDIUM, 3 LOW, 0 CRITICAL.** The two scales are never
mixed: no `VAL-` identifier appears in the table above and no `CHT-` identifier is re-typed,
re-graded or renumbered.

## Distribution

All ten audited findings fall in two files and one repository method: `ChartRenderer.tsx` (six),
`GraphConfigDict` in `models/types.py` (four, with one shared), `GraphDataResponse` and
`data.py` (two), and the filter-binding pair `aggregated_data_repo.py` / `DashboardFilters.tsx`
(two). `ChartRenderer.tsx` is 156 lines, is the sole producer of every trace in the client, and reads
a `config` object whose key set is decided three tiers away in a TypedDict it cannot see — that is
where the presentation contract is either honoured or lost, and six of ten findings land there.

The validation-level findings distribute differently: five of six are defects in the report rather
than in the system — one wrong label on a cross-phase disposition, one double-filed root cause, one
unresolvable proof, and two mechanism/anchor slips. One is a real inherited gap in the input's method
(a control green over zero items), recorded in the coverage ledger rather than as a finding, because
the claim it decided was independently re-derived from the two construction sites.

## Cross-Finding Analysis

*Two causes account for all ten audited findings, and both survive re-derivation unchanged.* The
first is a configuration vocabulary declared in one place and consumed in another with nothing
reconciling them: the renderer names five keys, `GraphConfigDict` names eleven, and the two sets
intersect in two — the input's one-line measurement is exact and I re-derived both sides. The second
is a response model that does not state what the client needs to draw the figure, which is why the
renderer's response to the omission is a guess. CHT-003 is the structural cause under CHT-001, and
this validation closes the loop: with the served measure list present the renderer would have a name
that is correct by construction, and the `_{agg}` suffix would stop mattering to the presentation
tier. That is why the input's roadmap orders the `GraphConfigDict` edit first and the response-shape
edit second, and the order is right.

*The one correction that changes how the roadmap should be read is CHT-002.* The three
per-type defects are not equally independent. CHT-007 and CHT-008 are independent of CHT-006 and
can land whenever. CHT-002 is not: it is a discard of a value that never arrives. The input places
it in Step 3, gated only on Step 1, and a team following the report will land a one-line fix with no
observable effect. CHT-002 must instead ship in the same commit as CHT-006, after the `xaxis`
object is merged rather than replaced — otherwise populating `layout` converts a latent defect into a
live one. This is the one sequencing change the input's roadmap needs.

*The vacuous-control angle found one control green over zero items, and it is the input's own
admitted limit.* The dev-stack probe on `:8010` decided CHT-006's "layout absent from each object"
against a dashboard whose graphs carried empty `data` arrays — the probe examined zero aggregate
rows, and reported clean. The verdict is nonetheless right, because it does not depend on the probe:
a whole-tree search for `GraphDataResponse` returns exactly two construction sites and neither
passes `layout`, which is a static proof over the whole codebase rather than a sample. The control
reached zero items on the part that mattered and the reader would not have known. This is precisely
the gap the input flagged, and executing the real aggregation and the real renderer is what closed
it. No other control in this phase is vacuous: the repository-interpreter probes examined one real
config each and decided real questions, and no shipped test or gate in this phase's scope is leaned
on by any claim.

*No finding in this phase rests on the input's own declared blocks or its own evidence fields as its
support.* All ten arrived from the executing path — the real Pydantic model, the real Polars
aggregation, the real repository comparison, the real renderer function, the shipped Plotly typings
and the real client query keys. The four declared block titles are all used, and every `Zone` field
quotes one of them verbatim.

## Recommendations — Executability

Every recommendation names a target that exists and is stable at `d008f555`, and every one is
executable as written. No recommendation is vague, offers alternatives without a preferred option, or
names no approach. The three worth a note before a team starts:

- **CHT-001's remedy is deliberately not the structural one.** It offers the smallest change (declare
  `metrics`/`orientation`/`barmode`, read `config.y`) and separately names CHT-003 as the direction of
  travel, saying the first does not depend on phase 05's naming question being closed. That
  dependency statement was tested and holds: `aggregate_for_dashboard` always suffixes, and declaring
  `metrics` storable still leaves the renderer unable to name `revenue_sum` unless it also reads the
  served list. The clause that actually works today is the second one — read `config.y`, a declared
  key that round-trips — and it is easy to read past.
- **CHT-007's remedy is correctly ordered after CHT-001** and the input says why: `values` built from
  `Number(row['y'] ?? 0)` is an all-zero pie rather than an empty one. Executing the pipeline
  confirms it — the pie traces come out `y:[0,0]` already.
- **CHT-009's remedy is blocked on a product decision, not on code.** The input says so explicitly and
  correctly: the repository only ever reads `dims`, and whether a `range` filter targets a dimension
  or a measure is recorded nowhere. Fixing the multiselect case alone is unblocked.

## Roadmap

The input's five steps are ordered by cause rather than severity and that ordering survives. Two
changes, one reorder:

1. **Move CHT-002 out of Step 3 and make it a hard co-requisite of the CHT-006 work.** The two must
   land in one commit, with `xaxis` merged (`{type: 'category', ...convertedLayout?.xaxis}`) rather
   than replaced. Step 3 as written ships a fix with no observable effect (VAL-16-003).
2. **Make the Step 2 verification quantitative.** Re-running the CHT-001 probe is right; the pass
   condition must be explicit, because this defect produces a complete-looking frame. After Step 1 the
   probe readback must contain `metrics`, `orientation` and `barmode`; after Step 2
   `/data/aggregated` must carry a non-empty `metrics` per graph **and** a bar graph's trace `y`
   array must contain a value greater than zero. A green page load is not the test.

Steps 1, 4 and 5 are unaffected. The `VAL-16-002` remedy — point the phase-13 roadmap entry at
CHT-010 instead of at a second call site — is one line and can be done at any point.

## Rollout Safety

The input's Rollout Safety section is the strongest part of the report, and every risk it names was
checked against the code. Confirmed as written: nothing backfills `metrics`, `orientation` or
`barmode` on existing graphs and the renderer's current defaults are what those graphs are already
being drawn with, so Step 1 is render-neutral; the `Literal` constraints will start rejecting values
that were previously stripped-and-ignored, which is the intended direction but is a behaviour change;
`GraphDataResponse` additions are additive in JSON terms; and the step-5 hazard — a 422 from
`/data/aggregated` failing the **whole** dashboard rather than one filtered graph, because
`DashboardView.tsx:181-185` renders the error at dashboard scope — is real, and the input's
prescription to move the rejection to filter-change time is the right call.

Two additions this validation makes:

- **The combined CHT-002 + CHT-006 commit is not independently revertible by half.** Populating
  `GraphDataResponse.layout` from `graph.config["layout"]` is additive and safe; the risk is entirely
  in the second half of the same commit. Reverting the server half alone leaves the client half inert
  *if* the merge is present and live if it is absent, so the commit reverts whole or not at all.
- **The input's pre-ship check for Step 1 has now been made, and it came back clean.** There is no
  graph editor anywhere in `frontend/src` that writes `config` — a search for the keys it would send
  returns nothing outside `ChartRenderer.tsx` — so the `Literal` tightening is currently unreachable
  from the shipped UI and no caller is relying on the old silence. Re-make the check if a graph editor
  is added.

## Appendices

### A1 — Coverage ledger

| Phase-99 block | What was examined | Item count reached | Left unsettled |
|---|---|---|---|
| 1. The claim re-derived from the executing path | All 10 findings, every cited file re-read at the cited line | 10 of 10 | 0 — but 4 location references do not resolve as written (VAL-16-004): a citation defect, not an unsettled claim |
| 2. Vacuous-control angle | Every control a claim leans on: the `:8010` HTTP probe, the repository-interpreter probes, the shipped Plotly typings | 3 controls; 1 reached **0** aggregate rows | 0 |
| 3. The grade against the audited phase's own rubric | All 10 bands against `.kilo/commands/audit/phases/16-chart-presentation-contract.md:93-106` | 10 of 10 | 0 — no band moved; two (CHT-007, CHT-009) were tested *upward* against the CRITICAL clause and both failed its second conjunct, recorded rather than assumed |
| 4. Which side moves | Corpus intent for every component named as unread or dead: `GraphConfigDict`, `GraphDataResponse.layout`, `AxisConfig.label`, `LineChart` label props, the FE-007 shape gap, `config.title` | 6 components, all declared or documented and reachable — none is dead code | 0 |
| 5. Whether the recommendation can be carried out | All 10 recommendations | 10 of 10, all executable | 1 product decision blocks part of CHT-009 — named by the input and upheld here |
| 6. Cross-phase conflict, ownership and merge | Contested claims: `FE-007`/`FE-008` (phase 13), `VAL-13-003` (phase 13 validation), `DP-002`/`DP-009`/`DP-018` (phase 05), phase 08 b1/b2, phase 13 b7, phase 11 b4/b9. Compared against all 14 sibling validation reports and the phase-05 and phase-13 reports | 7 contested claims | 0 |
| 7. Finding-ID namespace | `CHT-` declared at `16-chart-presentation-contract.md:114`; `CHT-001`…`CHT-010` minted; markers searched across `src/`, `frontend/src`, `tests/`, `alembic/`, `docs/` | declared 1, minted 10, in-source markers **0**, compound form resolves, reuse across phases **0** | 0 — see A2 |
| 8. The shared template as a controlled artefact | Six front-matter fields, five per-finding fields, the zone-verbatim rule, the reserved empty state, the required sections | 6 of 6 front-matter fields present and honest; 50 of 50 per-finding field slots present; 10 of 10 zones verbatim block titles; empty state correctly not used; all 8 sections present | 0 |
| 9. Does the input rest on its own declared blocks | Per finding, whether support is a declared block, an evidence field, or an independent observation | 10 of 10 rest on independent observation; 4 of 4 declared blocks produced findings; 0 rest on the input's own evidence fields | 0 |
| 10. The report as an artefact, and what was not settled | The tally, the identifier set, the two namespaces, and every claim that could not be settled here | 10 dispositions, 6 validation findings, 0 identifiers renumbered, namespaces disjoint | **2 claims unsettled, recorded in A3 and neither recorded as confirmed** |
| 11. The shared angles, defined once and bound by name | Whether phase 16 binds the vacuous-control angle or the cross-resource side-effect angle in its own words | 0 bindings declared by this phase | 0 — nothing to drift, and no angle is cited that no phase defines |

### A2 — Namespace ruling

Phase 16 declares `CHT-` at `.kilo/commands/audit/phases/16-chart-presentation-contract.md:114`.
Ten identifiers were minted, `CHT-001`…`CHT-010`. A whole-tree search for `CHT-` across `src/`,
`frontend/src`, `tests/`, `alembic/` and `docs/` returns **no in-source markers**, so the prefix is
not load-bearing provenance anywhere and nothing needs migrating — a remediation retires it by
finishing the phase. The compound form pairs the template's front-matter `phase:
16-chart-presentation-contract` with `CHT-`, as this phase's block 7 requires. No other phase in the
set uses `CHT-`, and no `CHT-` identifier is held by any of the fourteen sibling validation reports.
Ruling: reuse the declared namespace, mint no second one, and no collision report is required.

Validation-level findings use **`VAL-16-`**, a deviation from the flat `VAL-` the phase-99 output
contract names, because the flat namespace is already occupied by the phase-01 and phase-02 reports —
phase 13's VAL-13-005 records the resulting collision — and phases 03 through 14 have each adopted a
phase-qualified form. `VAL-16-001`…`VAL-16-006` collide with nothing. No file in
`.ai/audit/99-validation/` other than this one was created, edited or removed, and no `CHT-` or `FE-`
identifier was renumbered.

### A3 — Unsettled

Recorded as unsettled, and never as confirmed:

1. **Whether the shipped `plotly.min.js` warns on a `pie` trace carrying `x`/`y`.** The input declared
   this limit and it stands. The shipped `@types/plotly.js` settles *which* attributes a pie trace is
   populated by, which is the claim CHT-007 needs; whether the runtime additionally emits a console
   warning for the unexpected keys was not established, and CHT-007 does not depend on it.
2. **The rendered pixels.** No headless-browser render was performed, and none was needed for any
   verdict here: the renderer was executed and its trace output captured, which is the object Plotly
   receives. Whether `plotly.min.js` draws an all-zero bar trace as a visible flat line at the axis or
   suppresses it is library behaviour not traced into the bundle. The input's chain — wrong name →
   `0` → a frame carrying correct categories and a zero measure — is complete at the trace, which is
   where the claim ends.

### A4 — Method and artefacts

Read: `frontend/src/features/dashboards/ui/charts/{ChartRenderer,LineChart,PlotlyChart,TableChart}.tsx`,
`frontend/src/features/dashboards/ui/{DashboardView,DashboardFilters}.tsx`,
`frontend/src/features/dashboards/api/dashboardApi.ts`, `frontend/src/shared/types/api.types.ts`,
`src/mkobi/models/{types,graph,data,__init__}.py`, `src/mkobi/api/routes/data.py`,
`src/mkobi/services/{aggregation_service,data_service}.py`,
`src/mkobi/db/repositories/aggregated_data_repo.py`,
`src/mkobi/data/processing/aggregate_transforms.py`, `src/mkobi/workers/data_worker.py`,
`frontend/vite.config.ts`, `frontend/package.json`,
`frontend/node_modules/@types/plotly.js/lib/pie.d.ts`; the phase-99 output contract, the phase-16 and
phase-99 command files, the shared template, the phase-05, phase-13 and phase-16 reports, and all
fourteen sibling validation reports.

Executed: the real `GraphCreate` and `GraphConfigDict` under the repository interpreter; the real
`AggregationService.aggregate_for_dashboard` on a synthetic four-row Polars frame; and the real
`convertToPlotlyData` / `convertChartLayoutToPlotly`, extracted verbatim from
`ChartRenderer.tsx:11-119` and executed on the served rows that aggregation actually produced.

No source file was modified. No test, lint, build or coverage command was run — in particular the
declared frontend gate (`npm run test` = `vitest run --coverage`) was not invoked, so the known
`frontend/coverage/` deletion was not repeated. No dev-stack service was started, stopped or
reconfigured, no HTTP request was issued and no database row was created; the four runtime artefacts
the input created (dashboard `CHT16-probe`, graph `cht16-probe-bar`) remain deleted as it left them.
This run created no file other than this report.
