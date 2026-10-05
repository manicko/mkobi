# R3 / `CHTB-2` — served measure and dimension names: research

Block: `R3` (plan queue row 3). Research question: which of (A) re-derive `_{metric_agg}`,
(B) read the names off the payload being served, (C) skip the list, is the best path.

Every claim below was re-derived from the tree at `a306981`. Nothing is taken from the
215-commit-old plan text; §7 lists what that text got wrong.

---

## 1. Recommendation — (B), read off the stored row, computed in the **service**, at the flatten site

**Serve the metric and dimension keys by reading them off the `AggregatedData` rows that
produced the response, inside `DataService.get_bounded_aggregated_data` — the one method
that already holds `record.dims` and `record.metrics` separately and is currently throwing
that split away.**

The decisive reason, and it is stronger than "correct by construction":

> **`metric_agg` is mutable without a re-upload.** `ProcessingConfigService.upsert`
> (`services/processing_config_service.py:138-193`) writes `metric_agg` into the stored
> settings and returns. It triggers no re-aggregation and does not touch `aggregated_data`.
> It is reachable from `PUT /processing-configs/{dashboard_id}`
> (`api/routes/processing_configs.py:114-202`, `metric_agg=config_update.metric_agg` at
> line 186). So the *current* `metric_agg` can disagree with the `metric_agg` the stored
> rows were written under. Any derivation that re-applies the naming rule from config
> therefore produces a name that is on **zero** served rows in a state an operator can
> reach with two API calls. That is `CHT-001` reproduced through a new mechanism — the
> exact failure the original plan warned about, and it makes (A) *actively wrong*, not
> merely fragile.

Reading the keys off the row has no such failure mode, because the row **is** the thing the
client will index. If the row is keyed `revenue_sum`, the served name is `revenue_sum`; if
it is keyed `revenue`, the served name is `revenue`. The naming rule stays in exactly one
place — `aggregation_service.py:141`'s `.alias(f"{m}_{agg_name}")` — and this block never
re-states it.

### Where the derivation must live: the service, not the route

The `R2` precedent (`api/routes/data.py::_chart_layout`, a module-level private helper
projecting an already-loaded column) **does not transfer, and applying it here would make
the block impossible.** Reason, with the symbol:

`services/data_service.py:250-256`

```python
results = [
    ProcessingResultData(
        dashboard_id=record.dashboard_id,
        preview=[{**record.dims, **record.metrics}],   # <- split destroyed here
    )
    for record in records
]
```

`record.dims` and `record.metrics` are merged into one dict **one layer below the route**.
The route's `_flatten_points` (`api/routes/data.py:47-56`) receives only the merged dict and
has no access to the `metrics` JSONB column. A route-module helper cannot see the split, so
it could only recover metric keys as "row keys minus dimension keys" — which requires the
route to re-derive the dimension set (`graph.dimensions` **plus** the dashboard filter
dimension names, `aggregation_service.py:110,118-124`), a list the route does not hold.
`_chart_layout` is precedent for *projecting one stored value the route already has*
(`single_graph.config`); here the value is **discarded before the route runs**. Rejecting
the precedent here is applying its actual criterion, not ignoring it.

The repository already loads the column for free: `_response_columns_only()`
(`db/repositories/aggregated_data_repo.py:52-82`) is `load_only(id, dashboard_id, graph_id,
dims, metrics)` + `noload` on both relationships, and its own docstring says
`ProcessingResultData` "is built solely from `dims`, `metrics` and `dashboard_id`". Zero
extra SQL, zero extra allocation.

### Recommended fields

On `models/data.py::GraphDataResponse`, alongside the existing nine:

| Field | Type | Default | Source |
|---|---|---|---|
| `metrics` | `list[str]` | `Field(default_factory=list)` | union of `record.metrics` keys over the bounded page |
| `dimensions` | `list[str]` | `Field(default_factory=list)` | union of `record.dims` keys over the bounded page |

Both are **optional with an empty default**, not required. Reasoning: the response already
declares `rows_truncated: bool = False`, `layout: ... | None = None`,
`config: dict | None = None` with defaults; making these required would force every
construction site — including any future one — to thread them, and would put them in the
OpenAPI `required` list, which is a stronger published contract than the field needs. An
empty list is the honest value for a graph with no served rows, and it is the value that
makes the wire-level invariant in §6 hold without a special case.

Naming: `metrics` and `dimensions` (not `measure_names` / `row_keys`) because they mirror
`GraphRead.metrics` / `GraphRead.dimensions` (`models/graph.py:52`) and the two JSONB columns
they come from — same words, same meaning, so a reader does not have to learn a synonym.
Note the deliberate asymmetry with `config["metrics"]`: that one holds **pre-alias**
operator input, this one holds **post-alias** served keys. The docstring must say so
explicitly, because the collision is the entire trap this block exists to close.

Order: preserve first-seen insertion order (the aggregator builds `agg_exprs` in
`graph.metrics` order, and Polars preserves it), so the list is deterministic and the
primary measure stays first. Derive over the **whole page** with an order-preserving union,
not `page[0]` — same result today (every row of a graph is built from the same `agg_exprs`
in one `result.to_dicts()`), but the union does not depend on that invariant holding.

---

## 2. Rejected alternatives

**(A) Re-derive `f"{m}_{metric_agg}"` at the response site.** Rejected on two independent
grounds, either sufficient.
1. *Correctness:* the `metric_agg` drift above. Rows written under `sum`, config since
   flipped to `mean`, no re-upload → served `revenue_mean`, absent from every row, client
   renders all zeros under correct labels. Reachable in two HTTP calls.
2. *It cannot know what survived.* `aggregation_service.py:127` computes
   `metric_cols = [m for m in graph.metrics if m in df.columns]`; unmatched metrics are
   dropped, and `:130-134` `continue`s the whole graph. Re-deriving over `graph.metrics`
   lists names for metrics that never reached a row.
   It also requires the route to fetch the processing config — it currently does not — for a
   value the rows already answer.

**(C) Skip the served list; rely on `config["metrics"]` round-tripping.** Rejected: it
covers *specifiability* only. An operator writing `["revenue"]` when the row is keyed
`revenue_sum` round-trips perfectly and still renders as a flat zero chart. That is `CHT-001`
with the guess moved from the renderer into the stored config. It is also already declared
(`models/types.py:196`), so there is nothing left for this block to do.

**A fourth path, considered and rejected: keep the row split on the wire** (serve
`{dims: {...}, metrics: {...}}` per row instead of a flat dict). Rejected as a breaking
change to `data`'s element shape for `ChartRenderer`, `LineChart`, `TableChart` and the
pie branch, all of which read flat records — a much larger blast radius than an additive
field, and it forecloses the flat-row contract the current response docstring commits to.

**A fifth path, considered and rejected: a `SELECT DISTINCT jsonb_object_keys(metrics)`.**
Authoritative and independent of the page, but it adds a second query per graph to the read
path — and `tests/test_aggregated_read_path.py::TestAggregateReadStatementCount` is an
engine-level statement-count tripwire (`_StatementCounter` at line 320-321). Free is
available; take it.

---

## 3. Answers, by symbol

### Q1 — What does `Graph.metrics` actually hold?

**Always a `list[str]` of pre-alias column names. Never a keyword, never an expression.**

- `db/models/graphs.py:76-80` — `metrics: Mapped[list[str]] = mapped_column(JSONB, ...)`.
- `models/graph.py:52` — `GraphBase.metrics: list[str]`; `GraphRead` inherits it (`:122`).
- `workers/data_worker.py:1170` — `_to_graph_read` copies `metrics=g.metrics or []`
  verbatim. Nothing in `src/` rewrites the list: the only writers are
  `services/graph_service.py:234` and `:283`, both pass-through.

**On `yoy` / `share` / custom metrics — the brief's hypothesis is mechanically wrong but its
consequence is right.** They are not semantic markers inside `Graph.metrics`; they are
**dashboard-level processing-config transforms that add ordinary columns to the uploaded
frame before aggregation** (`workers/data_worker.py:821-859` → `calculate_aggregations`;
`data/processing/aggregate_transforms.py::_calculate_yoy` writes a column named by
`alias` (default `"yoy"`, `:159`), `_calculate_share` likewise (`alias="share"`, `:248`),
custom metrics via `_add_computed_fields`). After that, `"yoy"` **is** a real entry in
`df.columns`.

So an operator legitimately puts `"yoy"` or a custom metric's `name` into `Graph.metrics`,
and `aggregate_for_dashboard` treats it as an ordinary metric and aliases it `yoy_sum`.
Consequence: `graph.metrics` entries are never served keys, and the `_sum` suffix applies to
them too. Path (A) would have to know this to be right; path (B) never does.

### Q2 — What are the actual metric keys on a served row? *(the pivot)*

`{m}_{agg_name}` where `agg_name` is the resolved aggregation — and **the row dict in
`data` carries those keys, and the row also carries them separately in storage.**

- `services/aggregation_service.py:140-142` —
  `[AGG_FUNC_MAP[agg_enum](m).alias(f"{m}_{agg_name}") for m in metric_cols]`.
- `:160-163` — the `metrics` dict is every row key that is **not** a group key and does not
  start with `_` (so `_color_total`, added by `_apply_chart_sorting`, is excluded).
- `db/models/aggregated_data.py:89-93` — **`metrics: Mapped[dict[str, Any]]` is a real
  JSONB column, distinct from `dims` (`:83-87`).** Confirmed.
- `data/storage/manager.py:88` — "``metrics`` are deliberately NOT canonicalised -- numbers
  there are the data." Stored verbatim: `:310`, `:488`, `:522-523`. Confirmed.
- `db/repositories/aggregated_data_repo.py:52-82` — `load_only(..., dims, metrics)`: the
  bounded read already materialises the column. Confirmed.

**Therefore (B) is available and (A) is unnecessary.** The row *is* self-describing; the
route is simply downstream of where the self-description is destroyed.

### Q3 — How can the two lists be distinguished on a row?

**Authoritatively, by column, one layer below the route.** `dims` and `metrics` are separate
JSONB columns; `{**record.dims, **record.metrics}` (`data_service.py:213` and `:253`) is the
merge. The service can therefore name both halves without inferring anything.

The brief's alternative worry — "if `data` is a flattened dict, the client cannot tell a
dimension key from a metric key without a list" — is **correct and is itself the strongest
argument for the block**. The flattened `data` is genuinely ambiguous (nothing in
`{"category": "A", "revenue_sum": 100}` marks `revenue_sum` as the measure and `category` as
the axis). Note that `config["x"]` names the axis, but `config` is `None`-able and optional,
and `x` is not validated against the row. So the two served lists are not a convenience;
they are the only unambiguous description of the row's own shape.

### Q4 — Where should the derivation live?

**`DataService.get_bounded_aggregated_data`, folded into the existing comprehension that
already reads `record.dims` / `record.metrics`; the route passes the list straight into
`GraphDataResponse` at both construction sites.** Rationale in §1. Layering respected:
API → Service → Repository is intact — the service reads the repository's already-loaded
column and the route does no derivation at all, which is *stricter* than the `R2` precedent.

Signature change: `get_bounded_aggregated_data` returns
`tuple[list[ProcessingResultData], int]` today (`services/data_service.py:225`). It must
become a 3-tuple. The abstract declaration is
`interfaces/service_interfaces.py:496-505` and `repository_interfaces.py` is untouched.
**This is the block's only structural cost** — see §5 Risks, where its measured size is
stated (two call sites in `src/`, **zero** in `tests/`).

Alternative that avoids the signature change: add the names to `ProcessingResultData`
(`models/types.py:264-270`, a `TypedDict` with `preview`). That leaks response shape into a
type shared with the worker's processing-result payload (`data_worker.py:871-875` writes
`preview=df.head(10).to_dicts()` — raw source rows, no `dims`/`metrics` split). Rejected as
worse coupling than a 3-tuple.

### Q5 — Zero rows and the absent graph

Served values:

| State | `metrics` / `dimensions` |
|---|---|
| Graph with rows | the row keys, in first-seen order |
| Graph with zero served rows | `[]` / `[]` |
| Graph absent from the response | n/a — nothing is served |

**The brief's premise for this question is wrong, and the correction matters.** The
`continue` at `aggregation_service.py:134` makes an unmatched graph absent from the
**aggregate write**, not from the response. The endpoint enumerates graphs from the
`graphs` table (`api/routes/data.py:238` `graph_repo.get_by_dashboard_id`), so a graph with
no stored rows **still appears**, carrying `data: []`, `returned_rows: 0`, `total_rows: 0`.
`models/data.py:634-636` already documents this: "a graph whose rows were not returned at
all still appears, carrying its counts and an empty ``data`` list."

Under path (B) that state is free: no rows → no keys → `[]`. Under path (A) it is the
failure case: `graph.metrics` is non-empty while no row exists, so the served name is
unbacked by any row — the plan's own wire-level criterion is unsatisfiable there. **This is
the second independent reason to prefer (B).**

Reachable zero-row states (verified):
- **A graph created after the last successful upload** (`POST /graphs` writes no aggregates).
  The common one.
- **Filters matching nothing** — the `filters` query param is applied to both the bounded
  read and the count (`data_service.py:244-249`), so both go to zero together.

Note also that a *skipped* graph can hardly survive an upload at all:
`workers/data_worker.py:1238-1253` computes `produced_graph_ids` and raises
`PROCESSING_FAILED` naming the skipped graphs — **unconditionally, not gated on OVERWRITE**.
So after any successful upload every graph has ≥1 stored row.

**R6 boundary:** the absent-vs-zero distinction is R6's (`D-16-4`). This block serves `[]`
for zero rows and says nothing about absence, which is strictly weaker than what R6 needs and
therefore cannot make R6 worse. **R6 will read `metrics` to distinguish the states** (the
plan's R6 row: "the expected measure comes from the served list") — so R6 must not assume a
non-empty list means "data exists"; the two are independent signals. That coupling should be
stated in R6's brief.

### Q6 — The published-schema consequence

Verified against the tree. Exactly **one** test breaks.

1. `tests/test_aggregated_read_path.py::TestAggregateResponseShape::test_single_graph_response_has_expected_shape`
   — **line 366-369** asserts `set(graph.keys()) == {...}` exactly. Fails on two new keys.
   **Must be updated in the same commit**, adding `"metrics"` and `"dimensions"` to the set.
   That is the whole change; the rest of the test (lines 370-391) is unaffected.

2. `tests/test_openapi.py::TestAggregatedDataResponseCarriesTruncationContract` — **3 tests,
   lines 152-207. Needs no change.** Verified each: they assert `is_required()` and
   `annotation is int` on `total_rows` (`:157-161`), `returned_rows` (`:181-185`), and
   `AggregatedDataResponse.total_rows` / `truncated` (`:198-207`), then check named properties
   in the schema. **None asserts an exhaustive property set**, so adding properties cannot
   break them. The brief's framing ("two pins must survive") overstates this class — it
   survives untouched, which is the stronger result.

3. `tests/test_data_endpoint.py::TestAggregatedDataEndpointContract` — **4 tests. Stays green
   unmodified. Confirmed by reading all four**: `:50-51`, `:97-101` and `:145-150` use
   membership assertions (`"graphs" in data`, `"graph_id" in graph_data`), never a key set;
   the fourth (`:152-…`) asserts 403 on access. Phase 12's `AZ-8` critical pin is safe.

**No OpenAPI pin anywhere asserts an exhaustive `GraphDataResponse` property set** — the
`GraphDataResponse.model_fields` grep returns hits only in `test_openapi.py:157` and `:181`,
both field-specific.

### Q7 — Compatibility and rollout

The JSON change is additive, and `metrics`/`dimensions` were previously absent from the
response, so no existing client can be reading them. Old clients ignore the keys.

**What makes a stale name impossible rather than unlikely:** the served name is not a
*prediction* of a key, it **is** a key — read from the same `AggregatedData.metrics` value
whose keys were merged into the `data` rows one line earlier. There is no second producer
and no rule to drift. Path (A) cannot make this claim; it re-states a rule in a second place.

**The on-the-wire assertion the plan asked for** — and the existing fixture already
discriminates the two paths, which is the cheapest possible proof:

`tests/test_aggregated_read_path.py::_setup_dashboard_with_aggregates` (lines 40-93) stores
rows with `metrics={"revenue": 100 + i}` (line 82) — key `revenue`, **not** `revenue_sum` —
while `graph.metrics == ["revenue"]` (line 64). So:

- path (B) serves `metrics == ["revenue"]` → appears in `data[0]` → **passes**;
- path (A) serves `metrics == ["revenue_sum"]` → appears in **no** row → **fails**.

```python
# The plan's requirement, made executable.
served = set(graph["metrics"])
assert served, "a graph with rows must name its measure"
assert served <= set(graph["data"][0]), (
    f"served measure names {served} are not keys on any served row"
)
assert graph["metrics"] == ["revenue"]        # not "revenue_sum"
```

That last line is the discriminating half: it fails today (the field does not exist), fails
under (A), passes under (B).

Rollout: purely additive, no migration, no backfill — the field is computed per response
from rows already loaded. Old rows need nothing. The one behaviour change is that a client
*may* start trusting `metrics`, which is the point.

### Q8 — Any reason NOT to do this block?

**No. Do it.** `CHT-003` is the HIGH finding whose structural half closes `CHT-001`, and
`CHT-001` is a live silent-data-loss defect: `ChartRenderer.tsx:73`
`const metricCol = config.metrics?.[0] ?? 'y'` with `:45` and `:63`
`Number(metric ?? 0)` renders **every point as `0` under correct category labels** — a chart
that looks right and is wrong, which is worse than an error.

`D-16-6` is genuinely moot as the brief states: `AZ-8` landed as `d059b16` and touched only
`api/routes/data.py` (verified — `AZ-8` is the dashboard-scoping assertion at
`api/routes/data.py:176-187`, pinned by `TestAggregateGraphScoping`,
`test_aggregated_read_path.py:472-481`). The model file and both construction sites are
untouched by it, so there is no merge or ordering conflict.

Deferral would also break R6: the plan's R6 row states the expected measure "comes from the
served list", so R6 is downstream and would have to invent the signal itself.

**One scope correction for the planner:** the plan's R3 row frames the researcher's job as
"the `_{agg}` derivation". The researcher's answer is that **there should be no derivation**.
The plan's own word for the requirement — "correct by construction" — is the right one, and
(B) is its only implementation.

---

## 4. Tests required

Each stated so it **discriminates**: fails against today's code, fails against (A) or (C),
passes against (B).

1. **Update in the same commit** —
   `test_aggregated_read_path.py:366-369`: add `"metrics", "dimensions"` to the exact key
   set. Not a new test; a surgical edit to the one assertion that enumerates keys.
2. **`TestServedRowKeys` (new class, `test_aggregated_read_path.py`)** —
   `test_served_measure_name_is_a_key_on_the_served_row`: the §7 assertion on the existing
   fixture. Serves `["revenue"]`; asserts membership on `data[0]`; asserts
   `!= ["revenue_sum"]`. *Fails today* (no field); *fails under (A)*; passes under (B).
3. **Same class** — `test_served_measure_does_not_depend_on_metric_agg`: write a processing
   config with `metric_agg="mean"` **after** storing rows keyed `revenue`. Assert the served
   name is still `revenue`. *Passes under (B); fails under (A)* (`revenue_mean`). This is the
   §1 decisive reason, as a regression guard against someone "simplifying" the block back to
   (A) later.
4. **Same class** — `test_served_dimension_keys_are_the_row_keys`: assert
   `graph["dimensions"] == ["category"]` and that it is a key on every served row. Pins the
   symmetric half the renderer also guesses (`config.x ?? 'x'`, `ChartRenderer.tsx:71`).
5. **Same class** — `test_zero_row_graph_serves_empty_lists`: create a graph, store no rows,
   request it. Assert `data == []` **and** `metrics == []` and `dimensions == []`, and that
   the graph **is still present** in `graphs`. Pins the §5 correction (present-with-empty,
   not absent) and the `[]` rule. *Fails today*; fails under (A)* (which would serve
   `["revenue_sum"]`).
6. **Same class** — `test_both_branches_serve_the_same_names`: one dashboard, two graphs with
   rows, no `graph_id` (all-graphs) then with `graph_id` (single-graph). Assert identical
   `metrics` / `dimensions` from both. The plan requires both construction sites; without
   this a change to only one site is invisible.
7. **Same class** — `test_measure_name_survives_a_multi_metric_graph`: one graph with two
   stored metric keys. Assert both are served and the order matches the rows. Guards against
   an implementation that serves `metrics[0]` only.
8. **`test_openapi.py`, new test in the truncation class (or a sibling)** —
   `test_graph_response_declares_the_served_row_keys`: assert
   `"metrics" in GraphDataResponse.model_fields`,
   `model_fields["metrics"].annotation == list[str]`, the schema property is
   `{"type": "array", "items": {"type": "string"}}`, and `"metrics" not in required`.
   Pins the *published* type and the optionality decision. Discriminates on the wire schema,
   not the Python object.
9. **Service level, `test_data_endpoint.py` or a service test** — a unit test that
   `get_bounded_aggregated_data`'s 3rd element equals the union of stored `metrics` keys.
   Cheap, and it is where the derivation actually lives.

`tests/test_data_endpoint.py::TestAggregatedDataEndpointContract` (4) and
`tests/test_openapi.py::TestAggregatedDataResponseCarriesTruncationContract` (3) stay green
unmodified — verified in §Q6, and worth running explicitly as a guard rather than assuming.

---

## 5. Risks

**Implementation.** The only structural cost is the return-type change
`tuple[..., int]` → `tuple[..., int, list[str]]` on
`DataService.get_bounded_aggregated_data` (`data_service.py:218-257`) plus its abstract
declaration (`interfaces/service_interfaces.py:496-505`).
**Measured size: two call sites in `src/` (`api/routes/data.py:189` and `:244`) and
zero anywhere in `tests/`** — a grep for `get_bounded_aggregated_data` across `tests/`
returns no matches, so no `AsyncMock(return_value=(records, 5))` can break on the unpack.
Nor is the method mocked indirectly: `tests/conftest.py::authenticated_client` (`:773`) is
plain `async_client` + auth headers with no `get_data_service` override, so the endpoint
tests already run the real service against the real repository. The new tests in §4
therefore exercise the real derivation end to end — no mock scaffolding required, and none
of the eight tests needs updating for the signature change.
Second, smaller risk: `get_aggregated_data` (the unbounded sibling, `:187-216`) has the
identical `{**record.dims, **record.metrics}` merge at `:213`. Decide explicitly whether it
also gains the keys — it is not on the endpoint's path, so **no** is the answer, but leaving
the two methods with divergent shapes invites drift.

**Rollout.** None needed. No migration, no backfill, no feature flag: the field is computed
per response from rows already in hand. Deploy backend first; a frontend that ignores
`metrics` is unaffected, so the two halves of `CHT-001` can land in either order. That is
the property that makes this block safe to ship ahead of R4.

**Regression.** The two branch construction sites must both be filled or the endpoint
silently returns `[]` on one branch — an asymmetry a client cannot distinguish from "no
measure". Test 6 is the guard. Separately: `_flatten_points` merges records across the page,
so the derived list must come from the *records*, not from `data_points`, or a record whose
`preview` was falsy would drop its keys.

**Compatibility.** Additive in JSON; no existing client reads the field. The one semantic
hazard is the **name collision with `config["metrics"]`** — pre-alias operator input versus
post-alias served keys, in the same response object. The field docstrings must state the
difference in those words, or a future reader will "fix" the derivation to match `config`.

---

## 6. What the original plan got wrong about this block

1. **`metric_agg` location.** The plan says
   `processing_config_dict["settings"]["metric_agg"]`. That was fixed by `1e869f6`;
   `workers/data_worker.py:1208` now reads the **top level**
   (`(processing_config_dict or {}).get("metric_agg", "sum")`), with the reason in the
   comment at `:1204-1207` (DP-002). Any re-derivation written from the plan text would read
   the wrong key.
2. **The absent-graph premise is wrong.** Q5 assumes an unmatched graph is "absent from the
   response entirely". It is absent from the *write*; the endpoint enumerates the `graphs`
   table (`api/routes/data.py:238`), so it appears with an empty `data` list — as
   `models/data.py:634-636` already states. Designing the zero-row case as "not served"
   would have produced the wrong field type.
3. **"The graph's config now accepts `metrics`" (§C) is true but the inference is not.**
   That is path (C) and it is not sufficient: it makes the measure *nameable*, not *correct*.
4. **It understates the `metric_agg`-drift hazard.** The plan frames (A)'s problem as
   duplication and fragility ("two naming paths for one value"). The stronger problem is
   that (A) is **wrong today** in a reachable state (§1) — that is what should have decided
   the block.
5. **It mis-scopes the test damage.** It implies the OpenAPI class is a pin that must
   survive *alongside* an update to `TestAggregateResponseShape`. Verified: the OpenAPI class
   asserts named fields only and needs **no** change; exactly one assertion in the whole
   backend suite enumerates `GraphDataResponse`'s keys.
6. **It frames the researcher's deliverable as "the `_{agg}` derivation."** The answer is
   that there must be none.
7. **It does not mention `dimensions` as a first-class output**, though its own R3 row lists
   it. The symmetric derivation is free from the same column read and closes the axis-name
   half of the same guess.

---

## 7. Confidence

| Claim | Confidence | Basis |
|---|---|---|
| `AggregatedData.metrics` is a distinct JSONB column, loaded by the bounded read | **HIGH** | read directly: model `:89-93`, loader `repo:52-82` |
| `data` rows = `{**dims, **metrics}`, flattened in the service | **HIGH** | `data_service.py:213, 253` |
| `metric_agg` is mutable without re-upload ⇒ (A) is actively wrong | **HIGH** | `processing_config_service.py:138-193`; `processing_configs.py:182-187`; no re-aggregation call on that path |
| `Graph.metrics` is always pre-alias column names; yoy/share/custom are frame columns | **HIGH** | `data_worker.py:821-859`, `aggregate_transforms.py:153-279`; no writer rewrites the list |
| Zero-row graphs appear in the response with an empty `data` | **HIGH** | `data.py:238`, `models/data.py:634-636` |
| Exactly one backend assertion enumerates `GraphDataResponse` keys | **HIGH** | grepped `set(graph.keys())` / `model_fields` across `tests/` |
| The 3-tuple signature change has a small blast radius | **HIGH** | 2 call sites in `src/` (`data.py:189,244`); grep for `get_bounded_aggregated_data` across `tests/` returns **no matches**; `authenticated_client` (`conftest.py:773`) applies no `get_data_service` override |

No blocking uncertainty. Every recommendation-relevant claim is read from the tree at
`a306981`.