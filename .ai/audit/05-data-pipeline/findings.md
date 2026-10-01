---
phase: 05-data-pipeline
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 19
baseline: 8505a621dc5d3001470b4da9b6e210c05f351544
baseline-dirty: src/mkobi/config.py, src/mkobi/db/starter.py, tests/test_config.py, tests/test_starter.py (+ deletions under .ai/)
baseline-note: >-
  HEAD moved twice while this phase was executing, to 2d23c27 (credential predicates) and then to
  c3c0a61 (CHANGE_ME_ADMIN_USERNAME predicate); src/mkobi/config.py and src/mkobi/db/starter.py were
  dirty at task start and are clean at hand-off, tests/test_starter.py reverted and was re-modified.
  Every config.py / starter.py anchor cited below was re-verified against both commits - all values
  and all quoted line numbers are unchanged from 2d23c27 (see Appendix A).
by-severity:
  CRITICAL: 3
  HIGH: 7
  MEDIUM: 7
  LOW: 2
---

# Phase 05 — Ingestion and Aggregation

## Summary

The zone examined is the accepted-upload path: the admission limits on `POST /upload/{dashboard_id}`,
the `processing_logs` state each writer can produce, the atomicity of the accepting sequence, the
identity that decides whether a new aggregate row updates an existing one, per-mode replacement,
the field set of a stored processing configuration, the two caller-supplied expression grammars,
failure classification, frame validation, and the reclamation sweeps. Evidence was gathered by
static reading plus nine executed probes: six in-process against Polars 1.41.2 / Pydantic 2.13.4,
and three live against the throwaway test database (`bidb_test`, port 5434) inside transactions
that were rolled back.

The single most consequential thing found is that the stored metric aggregation function is never
read: the worker looks for `metric_agg` under a `settings` key that the accepting path never adds,
so every dashboard on the system stores `sum` under the name `<metric>_sum` regardless of the
configured aggregation, and every run reports `completed`. Immediately behind it sit two more
stored-result defects of the same family — an `append` that silently splits one logical group into
two rows because the identity is `dims::text`, and an `overwrite` that returns `completed` while
leaving the previous aggregate rows in place — plus one atomicity hole in which a failed `COMMIT`
leaves a queued job that replaces a dashboard's data with no status row anywhere to attribute it.
Nineteen findings: 3 critical, 7 high, 7 medium, 2 low.

## Findings

### DP-001 — A failed COMMIT leaves a queued job that replaces a dashboard's data with no status row to attribute it

**Severity** — CRITICAL

**Zone** — The unit of atomicity: what commits together, and what a rollback leaves behind

**Observation** — `services/file_processing.py::process_upload_with_session` produces five effects in
this order: the temp file (`upload.py:171`), the `processing_logs` row (`file_processing.py:215`),
the rename to `{log.id}.csv` (`:237`), the queue submission (`:256`), and `await db.commit()` (`:271`).
Only the status row is inside a transaction. The rename and the queue submission are not, and the
compensations that exist are one-directional: a failed rename rolls back (`:243`), a failed enqueue
unlinks the moved file and rolls back (`:266-267`). There is no compensation on the reverse edge — a
failure at `:271` rolls the row back and leaves both the moved file and the queued job in place. The
queue is `asyncio.Queue.put` (`core/task_queue.py:46`), which no database failure can retract. The
consumer that eventually runs the job never checks whether its task id exists:
`_update_processing_log_status` (`workers/data_worker.py:209-222`) executes an `UPDATE ... WHERE id = :id`
and never inspects `rowcount`, then `_store_aggregates` runs with `clear_old=True` and replaces the
dashboard's aggregates. `docs/00-overview/data-flow.md:113` states the opposite design: *"File move to
final path occurs after DB commit to prevent orphan files. On commit failure, the file remains at the
temp path for cleanup."* `[SPEC-DEVIATION]` — the code is the worse of the two.

**Evidence** — Executed against `bidb_test` with a session proxy that raises at `commit()` and a real
`asyncio.Queue`. Output:

```
process_upload_with_session raised: RuntimeError simulated failure at COMMIT
files left in upload_temp_dir   : ['c24e2012-3f4c-40a4-982f-3b8d564bf922.csv']
queue depth (queued work)       : 1
queued job task_id              : c24e2012-3f4c-40a4-982f-3b8d564bf922
processing_logs rows for that id: 0   <-- the status row the enqueued job will UPDATE
consumer status UPDATE with no row: completed without error (rowcount never checked)
```

The route's `finally` (`api/routes/upload.py:229`) does not reclaim the file either: `temp_file_path`
no longer exists because it was renamed, so the `exists()` guard is false and the moved file survives.

**Consequence** — For the dashboard named in the request, `overwrite` mode deletes every existing
`aggregated_data` row and replaces it with aggregates from an upload the operator was told failed with
HTTP 500. No `processing_logs` row exists for that task, so `/upload/status/{task_id}`,
`/upload/result/{task_id}` and `/processing-logs` cannot attribute those rows to any run: there is
no record that the dashboard was ever reloaded, and no record of the data that is now in it. The
operator sees a failed upload and a dashboard whose numbers silently changed.

**Recommendation** — Make the order match the documented one and make the queue the last thing that
happens. Commit the status row first, then move the file, then enqueue; and on enqueue failure write a
compensating `failed` status update in a fresh session rather than relying on the rolled-back
transaction. Independently, make `_update_processing_log_status` raise when `rowcount == 0` — a status
update against a non-existent task is the cheapest available detector for this whole class of orphan.
`tests/test_upload_api.py` and `tests/test_file_processing.py` currently assert the enqueue-before-commit
ordering; name them as remediation blockers and update them with the fix.

### DP-002 — The stored metric aggregation function is never read, so every dashboard sums

**Severity** — CRITICAL

**Zone** — Configuration reach: which parts of a stored processing configuration are honoured, which are skipped, and which fail the run late

**Observation** — `metric_agg` is a first-class field of the configuration boundary:
`models/processing_configs.py:13` types it `AggregationFunctionEnum | None`,
`ProcessingConfigService.upsert` merges it into `settings` (`services/processing_config_service.py:53`),
and it is documented in `models/types.py:191`. The worker reads it at
`workers/data_worker.py:694` and `:772` as
`(processing_config_dict or {}).get("settings", {}).get("metric_agg", "sum")`. But the dictionary it
receives is `dict(config_response.settings)` (`services/data_service.py:140`) — the settings *are* the
top level, so there is no `"settings"` key and `.get("settings", {})` always returns `{}`. Compare the
seven lines above at `data_worker.py:404`, which read the same dictionary with the correct fallback:
`processing_config_dict.get("settings", processing_config_dict)`. The read at `:694`/`:772` omits the
fallback. Nothing logs, warns or fails; the run reaches `completed`.

**Evidence** — Executed against `bidb_test` with the exact dictionary shape
`DataService._execute_upload` builds:

```
settings shape {metric_agg: mean}      -> [({'region':'N','segment':'x'}, {'revenue_sum': 10.0}), ...]
nested shape  {settings:{...}}         -> [({'region':'N','segment':'x'}, {'revenue_mean': 10.0}), ...]
```

Only the nested shape — which no caller in `src/` produces; `trigger_processing`, the one function
that accepts a caller-supplied config, has no route caller — produces `revenue_mean`.

**Consequence** — Every dashboard on the system aggregates its metrics with `sum`, whatever
`metric_agg` says. A dashboard configured for `mean` stores a sum in a column named
`<metric>_sum`; the run reports `completed`; `/data/aggregated` serves the sum. The configuration is
accepted, persisted, echoed back by `GET /processing-configs/{dashboard_id}`, and has no effect on any
stored row. See also DP-018 for the second defect this one currently masks.

**Recommendation** — Change both reads to `(processing_config_dict or {}).get("metric_agg", "sum")`,
or better, pass the already-unwrapped `settings` variable that `:404` computes so both sites read one
shape. Add a worker test that stores `metric_agg: "mean"` and asserts the stored metric key, and fix
DP-018 in the same change so the newly-reachable path is correct.

### DP-003 — Value-equal uploads in append mode split one group into two stored row sets

**Severity** — CRITICAL

**Zone** — Determinism of the aggregate: what makes identical input produce a different stored row

**Observation** — A row's identity is the unique index
`uq_aggregated_data_dashboard_graph_dims (dashboard_id, graph_id, dims::text)`
(`db/models/aggregated_data.py:55-61`), which is the index both `_bulk_upsert` and `upsert_aggregate`
target (`data/storage/manager.py:335-344`, `:179-188`). `_normalize_json_keys` sorts the keys, so key
*order* is normalised — but value *type* is not. `_coerce_dim_value`
(`services/aggregation_service.py:18-30`) deliberately preserves `int`, `float` and `bool` and only
falls back to `str`, and `None` collapses to `""`. Polars infers a column's dtype per file from its
content, so the same logical category arrives as `Utf8` in one upload and as an integer in the next as
soon as one file contains a non-numeric value in that column (`pl.read_csv` on `1,2` yields `Int64`; on
`1,N/A` it yields `Utf8`). `"1"` and `1` serialise to different `dims::text`, so the upsert misses and
inserts a second row.

**Evidence** — Executed against `bidb_test`, two appends of the same five values with the same
`region` category, differing only in whether the column parses as text or as an integer:

```
upload region = Utf8 ['1','1'] : [({'region': '1', 'segment': 'a'}, {'revenue_sum': 15.0})]
upload region = i64  [ 1 , 1 ] : [({'region': '1', 'segment': 'a'}, {'revenue_sum': 15.0}),
                                  ({'region':  1 , 'segment': 'a'}, {'revenue_sum': 15.0})]
```

**Consequence** — After the second append, one category occupies two rows and
`AggregatedDataRepository.get_by_graph_id` returns both. Any chart summing that metric now reports
`30.0` for a category whose real total is `15.0`; the filter UI offers `1` and `"1"` as separate
options. Nothing in the row, the status row or the log records that the two are the same category.

**Recommendation** — Make identity independent of the inferred dtype: canonicalise dimension values
before they reach the conflict target — one rule for all dimension columns, e.g. render every scalar
dim through the same string conversion that the read path already assumes
(`AggregatedDataRepository.get_by_graph_id:161` compares `dims[key].astext == str(value)`, and
`FilterValuesResponse.values` is `list[str]`). Keep the native value in `metrics` where sorting needs
it; change only the `dims` that form the key, and state the rule in `docs/09-database/schema-core.md`
so the index is no longer dtype-sensitive.

### DP-004 — An overwrite that matches no graph dimension reports completed and leaves the previous rows in place

**Severity** — HIGH

**Zone** — Replacement semantics: what an overwrite and an append each remove, and what neither removes

**Observation** — `_store_aggregates` selects graphs by `Graph.dashboard_id` and returns early when
there are none (`workers/data_worker.py:680`, `:758`). Otherwise `AggregationService.aggregate_for_dashboard`
drops a graph whose dimensions or metrics are absent from the frame — `if d in df.columns`,
`if m in df.columns` (`services/aggregation_service.py:67-74`) — logging only
`"Skipping graph ... - no valid groupby or metric columns"` (`:78`). If *every* graph is skipped the
record list is empty, and `StorageManager.save_aggregates` returns `0` at its very first branch,
`if not aggregates:` (`data/storage/manager.py:97-102`), **before** reaching
`if clear_old: await self.delete_by_dashboard(...)` at `:113-114`. The overwrite therefore deletes
nothing. The secondary list is rebuilt unconditionally afterwards
(`data_worker.py:726`, `:804`): `clear_dashboard_values` wipes every row for the dashboard, then
`extract_filter_values` over the empty record list produces nothing to write back. The status row is
then set to `completed` (`:537-543`). `docs/00-overview/data-flow.md:58` and `:107` both state
*"Full recalculation (all aggregates rebuilt)"*.

**Evidence** — Executed against `bidb_test`; graph dimensions `["region"]`, metrics `["revenue"]`,
one dashboard filter named `segment`. Second run is a two-column upload matching neither:

```
  after run 1 (good data, overwrite) : (2, [('segment','x'), ('segment','y')],
                                         [({'region':'N','segment':'x'}, {'revenue_sum': 10.0}),
                                          ({'region':'S','segment':'y'}, {'revenue_sum': 20.0})])
  after run 2 (overwrite, no match)  : (2, [],
                                         [({'region':'N','segment':'x'}, {'revenue_sum': 10.0}),
                                          ({'region':'S','segment':'y'}, {'revenue_sum': 20.0})])
```

Run 2 is the overwrite of run 1. Both aggregate rows survive; both filter values are gone.

**Consequence** — A re-upload after a column rename typo, a schema change, or an edit to a chart's
dimensions leaves the dashboard showing the previous upload's numbers while its filter controls are
empty. The new task's status row reads `completed`, so the operator has no signal that nothing was
replaced.

**Recommendation** — Move the empty check after the clear: under `clear_old=True`, an empty
`aggregates` list must still run `delete_by_dashboard`. Return an explicit outcome from
`_store_aggregates` (rows written, graphs skipped) and refuse to write `completed` when an overwrite
deleted rows but wrote none — that combination is always an error, never a no-op. Fixing this alone
converts DP-004 from "silently keeps stale data" into "fails the run", which is correct; the status
message should name the graphs that were skipped.

### DP-005 — A filter on a numeric or boolean column makes every upload fail

**Severity** — HIGH

**Zone** — Replacement semantics: what an overwrite and an append each remove, and what neither removes

**Observation** — The secondary list (`dashboard_filter_values`) is rebuilt from the same records that
produced the aggregates. `AggregationService.extract_filter_values` builds its sets from
`record["dims"]` (`services/aggregation_service.py:146-150`), and those values are
`_coerce_dim_value` outputs, which by design keep `int`, `float` and `bool`. They are handed to
`DashboardFilterValuesRepository.save_filter_values` (`workers/data_worker.py:739`, `:817`), which
writes them straight into `DashboardFilterValue.filter_value`, declared `String(1024)`
(`db/models/dashboard_filter_values.py:62`). asyncpg binds the insert parameter as `VARCHAR` and
rejects a non-string Python value; the `DataError` propagates out of `_store_aggregates`, out of
`_run_with_transaction`, and rolls back the whole worker transaction — including the aggregates already
inserted and, in overwrite mode, the `delete_by_dashboard` that preceded them. The failure is
classified `PROCESSING_FAILED`.

**Evidence** — Executed against `bidb_test`, one graph and one filter per run:

```
Int64 filter dim   quarter=[1,2]       -> RAISED DBAPIError DataError: invalid input for query argument
                                         $3 ... sequence: 1 (expected str, got int)
Float64 filter dim share=[0.5,0.25]    -> RAISED DBAPIError ... 0.25 (expected str, got float)
Boolean filter dim active=[True,False] -> RAISED DBAPIError ... False (expected str, got bool)
Utf8 filter dim    brand=['a','b']     -> OK, dashboard_filter_values: [('brand','a'), ('brand','b')]
```

**Consequence** — Any dashboard carrying a filter on a year, quarter, month, amount or flag column
cannot ingest data at all. The aggregates the run had already computed roll back with it, so the
dashboard keeps its previous numbers and the task row reads `failed` with `PROCESSING_FAILED` — a code
that points at the file, not at the filter definition. Numeric filters are the most common filter a BI
dashboard has, so this has the widest blast radius in the phase.

**Recommendation** — Convert at the boundary, not in the data: in `save_filter_values`, render each
value with the same `str()` the read path already applies
(`AggregatedDataRepository.get_by_graph_id:161` compares `dims[key].astext == str(value)`), which makes
the store agree with the reader and with the declared `list[str]` response model. Add a test per Polars
dtype for a filter dimension — int, float, bool, Utf8 — because the current suite only exercises text.

### DP-006 — A dashboard filter named like a graph dimension aborts the entire aggregation

**Severity** — HIGH

**Zone** — Configuration reach: which parts of a stored processing configuration are honoured, which are skipped, and which fail the run late

**Observation** — `aggregate_for_dashboard` builds its group key by concatenating the graph's dimensions
with the dashboard's filter names and keeping the names present in the frame
(`services/aggregation_service.py:62`, `:67-71`):

```python
groupby_cols = [d for d in (graph.dimensions + dashboard_filter_dim_names) if d in df.columns]
```

There is no de-duplication. When a graph groups by `region` and the dashboard has a filter named
`region` — the ordinary case of filtering a chart by the axis it is grouped on — the list is
`["region", "region"]` and `df.group_by(groupby_cols).agg(...)` at `:97` raises. Polars rejects
duplicate output names. The exception is uncaught, so the run fails; because it is raised before
`_store_aggregates` writes anything, no aggregate row is produced and no partial state survives.

**Evidence** — Executed against `bidb_test`, graph `dimensions=["region"]`, dashboard filter
`name="region"`, upload `region,segment,revenue`:

```
-> RAISED DuplicateError : group_by keys contained duplicate output name 'region'. It's possible
   that multiple expressions are returning the same default column name.
-> worker classifies as: PROCESSING_FAILED
```

**Consequence** — The dashboard silently stops accepting data. Chart and filter are both configured
correctly; the operator receives a 201 and then a `failed` task carrying `PROCESSING_FAILED`, which names
neither the graph nor the filter as the cause. Because the failure is inside the per-graph loop, one such
graph fails the whole dashboard's aggregation, including the graphs that were fine.

**Recommendation** — De-duplicate while preserving order: build the key with `dict.fromkeys(graph.dimensions
+ dashboard_filter_dim_names)` and filter by frame membership, so a name that is both a dimension and a
filter contributes one column. Add tests for a filter whose name equals a graph dimension and for two
filters sharing a name.

### DP-007 — A configured groupby without aggregations stores an arbitrary row from each group

**Severity** — HIGH

**Zone** — Determinism of the aggregate: what makes identical input produce a different stored row

**Observation** — `workers/data_worker.py:495` passes
`groupby=config.groupby if not config.aggregations else None` to `apply_transformations`. With a
`groupby` and no `aggregations`, that function reduces the frame with
`result = result.group_by(groupby).agg(pl.all().first())`
(`data/processing/transformations.py:103`). `pl.all().first()` collapses every non-key column to the
first row *of that group in the group's internal order*, which Polars does not define. When the
configured `groupby` is a superset of a graph's dimensions, each of that graph's output groups
contains exactly one row, so the graph's metric becomes that arbitrary row rather than any aggregate of
the group. Polars itself does not return groups in key order — the same input returned `S` before `N`
in the probe below.

**Evidence** — Executed against Polars 1.41.2, same four rows in two orders:

```
input order  -> [{'region':'S','revenue':  2,'extra':'c'}, {'region':'N','revenue':  1,'extra':'a'}]
reversed     -> [{'region':'N','revenue':100,'extra':'b'}, {'region':'S','revenue':200,'extra':'d'}]
```

**Consequence** — A dashboard whose processing configuration sets `groupby` but no `aggregations`
stores a different metric for the same input depending only on the row order of the CSV. Because the
row set is unchanged, nothing in the row, the status row or the log distinguishes the two runs, and a
re-upload of a byte-identical file is enough to move the number.

**Recommendation** — Decide what `groupby` alone is meant to mean. If it is a de-duplication step, the
reduction must be deterministic and explicit — name every surviving column and pick it by a stated rule
(`min`, `first` after an explicit `sort_by`, or a configured aggregate) rather than by `pl.all().first()`.
If it is not a supported configuration, validate against it in `_validate_processing_config` so the run
fails at the boundary instead of storing an arbitrary pick. The same expression is reached by
`aggregate_data` (`data/processing/aggregate_transforms.py:80-107`), so fix it in one place.

### DP-008 — limit is applied before aggregation, so a configured sum is a function of CSV row order

**Severity** — HIGH

**Zone** — Determinism of the aggregate: what makes identical input produce a different stored row

**Observation** — `apply_transformations` orders its steps filters → groupby → sort → limit
(`data/processing/transformations.py:94-113`), and the worker calls `calculate_aggregations` *after* it
(`workers/data_worker.py:491-516`). So `limit` truncates the raw frame before any `sum`, `mean`, `min`,
`max` or `count` is computed. With `limit` set and no `sort_by`, `head(n)` takes the first `n` rows in
file order; the aggregate is then a function of that selection. `limit` is a first-class field of both
`ProcessingConfig` (`models/data.py:125`) and `ProcessingSettingsDict` (`models/types.py` does not
list it, so it is settable only through `ProcessingConfig`), and `_validate_processing_config` checks
only that `sort_by` has no empty entries — it never pairs `limit` with `sort_by`.

**Evidence** — Executed against Polars 1.41.2 with `groupby=["region"]`,
`aggregations=[{column: revenue, function: sum}]`, `limit=3`, over the same ten rows
(`N×1..5`, `S×10..50`):

```
after head(3):                     [{'region':'N','revenue':1},{'region':'N','revenue':2},{'region':'N','revenue':3}]
aggregate of truncated frame:      [{'region':'N','revenue_sum':6}]
reversed source, same data:        [{'region':'S','revenue_sum':120}]
```

**Consequence** — Reordering the rows of the input file changes a stored aggregate from `6` to `120`
for the same data. In this example the truncated frame also lost a whole region, so the dashboard shows
one region where the source has two — and the status row reads `completed`.

**Recommendation** — Move the limit after aggregation, or reject the pair: if `limit` is supplied
without a `sort_by` that fully determines the selection, fail the run in `_validate_processing_config`
rather than silently summing an arbitrary prefix. Whichever is chosen, add a test that runs the same
values in two row orders and asserts one stored result.

### DP-009 — yoy_config, share_config and custom_metrics cannot be stored on a working dashboard

**Severity** — HIGH

**Zone** — Configuration reach: which parts of a stored processing configuration are honoured, which are skipped, and which fail the run late

**Observation** — All three are declared on `ProcessingConfig` (`models/data.py:126-128`), validated
by `_validate_processing_config` (`workers/data_worker.py:126-163`), and forwarded to
`calculate_aggregations`, which unpacks them with `**` into functions that take keyword parameters
(`data/processing/aggregate_transforms.py:62`, `:67`) and passes `custom_metrics` straight to
`_add_computed_fields` (`:74`). `yoy_config` and `share_config` are Pydantic models
(`models/transformation_configs.py:50`, `:84`) and `custom_metrics` is a list of
`CustomMetricConfig` models (`:106`). `**` requires a mapping and `_add_computed_fields` reads
`field.get("name")` (`data/processing/filter_transforms.py:90-91`), so all three fail. `_add_computed_fields`
itself re-raises rather than skipping (`filter_transforms.py:109-111`), so there is no degradation path.
Nothing rejects the document earlier: `ProcessingConfigService._validate_settings` type-checks only
`separator`, `decimal_separator`, `column_types` and `date_format`
(`services/processing_config_service.py:90-103`), and `ProcessingConfig(**processing_config_dict)`
first runs at `data_worker.py:487` — after the file has been read, validated and transformed.

**Evidence** — Executed against Polars 1.41.2 / Pydantic 2.13.4:

```
_calculate_yoy(df, **YoyConfig(year_column="year", value_column="v"))
  RAISED TypeError _calculate_yoy() argument after ** must be a mapping, not YoyConfig
_calculate_share(df, **ShareConfig(value_column="v"))
  RAISED TypeError _calculate_share() argument after ** must be a mapping, not ShareConfig
_add_computed_fields(df, [CustomMetricConfig(name="p", expr="v / v")])
  RAISED AttributeError 'CustomMetricConfig' object has no attribute 'get'
_add_computed_fields(df, [{"name":"p","expr":"v / v"}])     # dict shape
  OK -> columns ['year', 'v', 'p']
```

**Consequence** — A dashboard that configures any of the three fields accepts the upload with HTTP 201
and then fails every task with `PROCESSING_FAILED`. The configuration is stored, echoed by
`GET /processing-configs/{dashboard_id}`, and never produces a result. `custom_metrics` is the field
`docs/00-overview/data-flow.md:112` names as the reason the config is "automatically fetched and passed
through the upload pipeline … ensuring transformations use the correct loader settings and custom
metrics".

**Recommendation** — Convert at the call site with `model_dump()`:
`result = _calculate_yoy(result, **yoy_config.model_dump(exclude_none=True))`, the same for
`share_config`, and `_add_computed_fields(result, [m.model_dump() for m in custom_metrics])`. Then add
one worker test per field, since each of the three is currently unreachable. Fix `_calculate_yoy`'s own
defect in the same change: with no `group_cols` it computes `pl.col(value).shift(1)` over a frame
sorted only by `year` (`aggregate_transforms.py:181`, `:200`), which crosses group boundaries — a
`year`/`brand` frame with `groupby` set and `yoy_config.group_cols` omitted yields a `yoy` column whose
values depend on row order, exactly as DP-008 does. Require `group_cols` whenever the frame carries more
than the year column.

### DP-010 — Failure class is decided by substring-matching the message, and the exception's own ErrorCode is discarded

**Severity** — HIGH

**Zone** — Failure classification: how an outcome is categorised, and what each category reaches

**Observation** — Two independent sites classify the same exceptions. `api/routes/upload.py::_handle_value_error`
(`:91-123`) lower-cases `str(e)` and tests for `mime`, then `format`/`extension`, then
`size`/`exceeds`/`max`, then `limit`/`rate limit`. `workers/data_worker.py::_map_processing_error_to_code`
(`:42-77`) tests `isinstance(error, FileNotFoundError)` and then lower-cases `str(error)` for
`encoding`, `csv`+`read|parse`, `missing required columns`, `validation failed`, `too large`/`size`.
Neither site looks at `AppException.code`, even though `AppException` carries an `ErrorCode` that
`_update_processing_log_status` writes straight into `processing_logs.error_code`
(`db/models/processing_logs.py:69-72`, read back by `models/data.py:98`). `_validate_processing_config`
raises `AppException(code=ErrorCode.VALIDATION_ERROR, ...)` for every configuration defect
(`data_worker.py:98-172`); the worker then overwrites that with the substring result.

**Evidence** — Executed against Pydantic 2.13.4, both sites applied to the same six exception texts:

```
exception                                                             worker site          upload site
Processing config has invalid aggregation: column name is missing...  PROCESSING_FAILED    (not ValueError)
Invalid transformation config: 1 validation error for Transformation PROCESSING_FAILED    INVALID_FILE_TYPE
Failed to load file /data/x.csv.gz: utf8 invalid bytes                PROCESSING_FAILED    VALIDATION_ERROR
Missing required columns: region                                     VALIDATION_ERROR     VALIDATION_ERROR
File 'a.csv' exceeds maximum size (200000000 > 104857600 bytes)      FILE_TOO_LARGE       FILE_TOO_LARGE
DataFrame is empty (no rows)                                          PROCESSING_FAILED    VALIDATION_ERROR

AppException carries a code, but the worker maps by text
  error.code       = VALIDATION_ERROR
  str(e)           = 'Processing config has invalid aggregation: column name is missing or empty'
  worker assigns   = PROCESSING_FAILED
```

Also measured against real Polars 1.41.2 messages: `ComputeError: invalid utf-8 sequence` and
`NoDataError: empty data from BytesIO` both classify as `PROCESSING_FAILED`, so the first branch of the
classifier — `"encoding" in error_msg`, written for encoding failures — does not match the message
Polars actually emits.

**Consequence** — Two effects. First, every configuration-validation failure is recorded on the status
row as `PROCESSING_FAILED` even though the code that raised it said `VALIDATION_ERROR`, so the client
renders a generic processing error for what is a configuration error the operator can fix. Second, the
class of an outcome is pinned to the wording of upstream libraries: `CSVLoader.load_csv` wraps every
failure as `ValueError(f"Failed to load file {path}: {e}")` (`data/loaders/loader.py:166`), destroying
the exception type, so the text is all that remains — a Polars release that changes one message
re-routes a whole failure class with no change to any code in this repository. Two of the six rows show
the two sites disagreeing about the same text, which means the same exception would be labelled two
different things depending on which process caught it.

**Recommendation** — Classify by type first and message second: in `_map_processing_error_to_code`, take
`error.code` from `AppException` before any substring test, and use `isinstance`/`PolarsError` for the
rest. Stop wrapping in `loader.py:166` — re-raise the original after logging, or raise a typed
`FileProcessingError` carrying the cause, so the text is not the only signal left. Add a table-driven
test over `(exception, expected code)`; the six rows above are the test cases.

### DP-011 — The byte ceiling bounds the compressed form, and the "lazy" read branch collects the whole frame

**Severity** — MEDIUM

**Zone** — Ingestion admission: which limits exist, which layer enforces each, and what one input can pin

**Observation** — The admission inventory derived from `POST /upload/{dashboard_id}` is: a declared size
ceiling (`config.max_file_size` = `max_file_size_mb * 1024 * 1024`, `config.py:805-807`), enforced twice
in the request process — once against the client-declared `Content-Length` (`upload.py:129`) and once as
a cumulative counter over 8 KiB chunks while the transfer runs (`upload.py:181`) — a third time in the
service layer (`services/file_processing.py:150`) and a fourth time in the loader
(`data/loaders/loader.py:256`); a content-derived type from libmagic, enforced in the request process
only (`file_processing.py:73-94`, `MimeTypeEnum`); an extension check on the caller-supplied name
(`file_processing.py:136-147`). The transfer is genuinely chunked — at most `CHUNK_SIZE` = 8192 bytes
of the request body is resident at a time — so the transfer itself pins little. The whole-file residency
starts at `CSVLoader.load_csv`, in the worker process, in a `asyncio.to_thread` call
(`data_worker.py:413-416`). The branch that claims to bound it does not: above `lazy_threshold_mb`
(10 MiB by default) the loader takes `_read_csv_lazy`, which ends in
`pl.scan_csv(file_path, **kwargs).collect()` (`loader.py:215`) — `collect()` materialises the entire
frame, so the two branches differ only in how the frame is built. For a `.csv.gz` the ceiling is
measured on the *compressed* file (`_get_file_size_mb` → `stat().st_size`, `loader.py:234`) while the
frame is built from the decompressed stream (`gzip.open` at `:298`); nothing bounds the expansion ratio.

**Evidence** — Static: `loader.py:133-146` selects the branch, `:215` collects it, `:234` measures the
compressed size, `:298` decompresses. Executed: the "lazy" path was exercised through the same call
`CSVLoader.load_csv` makes and returned a fully materialised `pl.DataFrame`, not a `LazyFrame`.

**Consequence** — One admitted input becomes one whole in-memory DataFrame in a worker thread, held for
the duration of load, validate, transform and aggregate, with no bound between 10 MiB and the ceiling.
Because prod runs four uvicorn workers (TOPO-005) and the in-process queue is per-process (TOPO-002),
four such frames can be resident at once. For a gzipped upload the resident frame is bounded by the
decompression ratio of the compressed bytes, not by the configured ceiling at all — a 100 MiB `.csv.gz`
under the default ceiling can expand to well over a gigabyte of CSV rows.

**Recommendation** — Bind the ceiling to what is actually held: for `.csv.gz`, cap the *decompressed*
byte count while reading rather than the file size, and apply the ceiling to the expanded frame. If the
lazy branch is meant to bound memory, keep the `LazyFrame` and push the aggregate into the query plan
instead of collecting; if it is not, delete the branch and the `lazy_threshold_mb` setting rather than
keeping a switch that changes nothing. Fixing DP-012 in the same change keeps one ceiling with one owner.

### DP-012 — The worker consults a hardcoded 100 MiB ceiling that MAX_FILE_SIZE_MB does not control

**Severity** — MEDIUM

**Zone** — Ingestion admission: which limits exist, which layer enforces each, and what one input can pin

**Observation** — `_process_csv_file_async` constructs the loader with no configuration:
`loader = CSVLoader()` (`workers/data_worker.py:413`). `CSVLoader.__init__` then takes
`LoaderConfig()`, whose `max_file_size` defaults to `100 * 1024 * 1024`
(`models/data.py:278-283`). `CSVLoader._validate_file_size` reads `self.config.max_file_size` when no
explicit maximum is passed (`loader.py:253-254`) and raises `ValueError("File too large: ... (max: ...)")`
(`:263`). So the ceiling the worker enforces is a literal in a Pydantic model, while the ceiling the
request process enforces is `max_file_size_mb * 1024 * 1024` from the environment (`config.py:805-807`).
The same applies to `required_columns`, `column_types` and `strict_schema` on `LoaderConfig`: the loader's
own `_apply_type_transformations` and `_validate_required_columns` are gated on `self.config.*`
(`loader.py:155-160`) and never run, because the worker constructs a default config and does both jobs
itself later (`data_worker.py:419-425`, `:450-469`). Three declared limits are therefore in force at
different values in the two processes, and two of them are never consulted at all.

**Evidence** — Static chain above, read end to end in this audit: `data_worker.py:413` → `loader.py:81`
→ `models/data.py:278`. No `MAX_FILE_SIZE_MB` reference exists anywhere under `data/loaders/`.

**Consequence** — Raising `MAX_FILE_SIZE_MB` above 100 — the documented way to admit a larger export —
does not raise what the worker accepts: the request admits and stores the file, returns 201, and the task
then fails in the worker with `FILE_TOO_LARGE` (its message contains `too large`, matching
`_map_processing_error_to_code`'s fourth branch). Lowering it below 100 leaves the loader's bound
looser, which is harmless only because the request process is stricter. The operator cannot raise the
admission limit above 100 MiB without editing a code literal.

**Recommendation** — Give the loader the configured ceiling: `CSVLoader(LoaderConfig(max_file_size=config.max_file_size))`
at `data_worker.py:413`, or delete `_validate_file_size` and the `LoaderConfig.max_file_size` /
`required_columns` / `column_types` / `strict_schema` fields and keep one enforcement point per limit.
`02`'s b3 guard inventory does not cover this literal — it is a per-dashboard-class code constant, not a
secret — so it is filed here.

### DP-013 — Validation warnings are computed, then discarded; the rows they describe are stored anyway

**Severity** — MEDIUM

**Zone** — Validation of the loaded frame: what is refused, what is only warned, and whether a warning is stored anyway

**Observation** — The check set applied before storage is `DataValidator.validate`
(`workers/data_worker.py:420-425`), configured with `required_columns` from `settings` and
`column_types` from the parse config. Per check: an empty frame is an **error** (`validator.py:55-65`);
missing required columns is an **error** (`:105-132`) but only when a caller supplied
`required_columns`, which `ProcessingSettingsDict` does not list (`models/types.py:172-191`), so an
unconfigured dashboard runs no schema check at all; declared-vs-actual column type, nulls in required
columns, empty strings in text columns and duplicate rows are all **warnings** (`:134-260`) — and
`_validate_column_types` can only ever append to `warnings`, never to `errors` (`:145`, `:184`). The
worker reads only `is_valid` and `errors` (`data_worker.py:426-427`). `validation_result.warnings` has no
consumer anywhere in `src/`: the only other readers are `get_validation_summary` and
`validate_dataframe` (`validator.py:293`, `:333`), which the pipeline never calls. Nothing is written to
`processing_logs.message`, which carries only the completion sentence (`:540`).

**Evidence** — Executed: the declared-vs-actual check is unreachable as a check because the type cast
that would make the declared type true runs *after* validation — `column_types` is compared at `:424`
against Polars' inferred dtypes, while the cast loop at `:451-469` skips `float` outright
(`if col_name in df.columns and col_type != "float"`) and casts only when `date_format` is present for
`date`. A config declaring `{"revenue": "float"}` over an all-integer column therefore warns on every
run and never becomes true. Grep for `validation_result` and `.warnings` across `src/` returns only the
two lines that read `errors`.

**Consequence** — A run over data the validator itself annotated — duplicate rows, a declared type that
does not hold, nulls in a required column — completes with `status=completed` and
`Processing completed successfully: N rows processed`, and the annotation exists only in the
`logger.warning` lines of `DataValidator`. Duplicate rows are silently summed into the metrics; the
operator has no way to learn the input was doubtful.

**Recommendation** — Persist the annotation: append `validation_result.warnings` to the completion
message (the column is `String(1000)`, so summarise and cap), or store them in `details` and extend
`ProcessingStatusResponse`. At minimum, promote duplicate-row and declared-type warnings to a distinct
`completed_with_warnings` outcome the client can render. Separately, run the type cast before the
validator, or drop `column_types` from the validator's inputs so a check that can never be true stops
firing.

### DP-014 — Validation runs before renames, so a configuration key naming a renamed column is silently skipped

**Severity** — MEDIUM

**Zone** — Configuration reach: which parts of a stored processing configuration are honoured, which are skipped, and which fail the run late

**Observation** — The worker applies a stored configuration in a fixed order: validate
(`data_worker.py:419-437`), decimal separator (`:439-448`), column casts (`:450-469`), renames
(`:471-475`), computed fields (`:477-483`), then transformations and aggregations (`:485-516`). The
validator therefore sees the *pre-rename* frame, while every consumer downstream — graph dimensions,
dashboard filters, `metric_agg` — matches *post-rename* names. A `required_columns` entry naming the
target name fails against a column that does not exist yet; a `column_types` entry naming the target name
is dropped by the cast loop's `if col_name in df.columns` guard (`:454`) with no `else` branch and no
warning. The renames map itself has the same weakness: `df.rename(rename_map)` raises on a missing
source column, so a typo fails the run, but a *misspelled key* — `rename` instead of `renames` —
matches nothing at `settings.get("renames")` (`:472`) and is a silent no-op.

**Evidence** — Static: the four sites in the order above, with `settings.get("renames")`,
`settings.get("computed_fields")` and `settings.get("decimal_separator")` each gated by a bare
`.get(...)` whose miss is unlogged. `ProcessingConfigService._validate_settings`
(`services/processing_config_service.py:73-103`) validates four field types and none of the three
expressions, the rename map, `required_columns` or `computed_fields`.

**Consequence** — One stored configuration names its columns in two different namespaces without saying
so. Declaring `renames: {"amount": "revenue"}` with `column_types: {"revenue": "float"}` produces a run
that reports `completed`, applies no cast, and stores whatever Polars inferred — with no warning
anywhere. Declaring `required_columns: ["revenue"]` alongside the same `renames` fails the run with
`Missing required columns: revenue`, which names a column the operator believes exists.

**Recommendation** — Move the validator after the renames and casts, so every configuration key is
matched in the same namespace as everything downstream; and reject unknown keys at the storage boundary
by typing `settings` as a Pydantic model with `extra="forbid"` (the pattern
`models/transformation_configs.py:133` already uses for `TransformationConfig`), so a misspelled field
is a 422 at the API instead of a no-op in the worker.

### DP-015 — The orphan sweep's bound is a one-minute code literal and it runs only at process startup

**Severity** — MEDIUM

**Zone** — Cleanup and recovery: what reclaims an abandoned accepted input, in which process, on which clock, and what it cannot reach

**Observation** — The reclamation set, derived from the callers, is six items:

| sweep | process | selection | clock | bound | bound source |
|---|---|---|---|---|---|
| `cleanup_stale_temp_files` | each app process, at startup (`db/starter.py:183`) | `upload_temp_dir.glob("*.csv*")` | file `mtime` | age (h) | `stale_file_threshold_hours`, default 24 (`config.py:408`) |
| `cleanup_old_logs` | each app process, at startup (`db/starter.py:188`) | terminal status rows | `finished_at` | age (d) | `logs_retention_days`, default 30 (`config.py:407`) |
| `cleanup_stale_processing_logs` | background task per app process, every `stale_processing_cleanup_interval_seconds` (300) | `status = PROCESSING` | `started_at` | age (min) | `stale_processing_timeout_minutes`, default 30 (`config.py:409`) |
| `mark_orphaned_uploaded_logs_failed` | each app process, **startup only** (`app.py:116`) | `status = UPLOADED` | `started_at` | age (**min**) | **hardcoded `timedelta(minutes=1)`** (`data_worker.py:312`) |
| per-task unlink on success | queue consumer (`data_worker.py:532-534`) | the job's own path | — | — | — |
| per-task unlink on failure | queue consumer (`data_worker.py:562-566`, `:593-598`) | the job's own path | — | — | — |

The orphan sweep is the only one that reclaims a `UPLOADED` row, and it is invoked exactly once per
process lifetime, from `lifespan` (`app.py:116`). It marks rows older than one minute; a row created
ninety seconds before a restart survives the sweep and is not examined again until the next restart.

**Evidence** — `data_worker.py:312` is `cutoff = datetime.now(UTC) - timedelta(minutes=1)`, a literal
with no configuration read anywhere in the module; the module's other two bounds are parameters
threaded from `config` at `app.py:120-125`. `app.py:116` is the sole call site. Grep for the three
`file_cleanup` functions across the repository returns test call sites and `starter.py:183` only.

**Consequence** — The window in which an orphaned `uploaded` row survives is "until the next restart",
not "one minute". An operator who restarts the app immediately after a batch of uploads gets rows
younger than the cutoff skipped, and they stay `uploaded` — reported to the client as
`progress: 0, status: uploaded` — for as long as the process stays up. TOPO-001 files the same residue
from the mechanism side (the unreachable `FAILED` write); this entry files the bound and its trigger,
which is a different lever: the bound is not configurable and the sweep is not periodic.

**Recommendation** — Move `mark_orphaned_uploaded_logs_failed` into the existing periodic loop next to
`cleanup_stale_processing_logs` so it runs every interval rather than once per boot, and read its cutoff
from `config` beside `stale_processing_timeout_minutes` rather than from a literal. One-minute is a
reasonable default; a code literal is not, because nothing can widen it for a slow queue.

### DP-016 — Worker-side file deletion is uncompensated on cancellation, and the temp-dir sweep is bounded on age only

**Severity** — MEDIUM

**Zone** — Cleanup and recovery: what reclaims an abandoned accepted input, in which process, on which clock, and what it cannot reach

**Observation** — On the success path the consumer deletes the input file *inside* the open transaction
(`data_worker.py:532-534`) and sets `completed` afterwards (`:537-543`); on the failure path it deletes
the file inside `except Exception` (`:562-566`, `:593-598`). `asyncio.CancelledError` inherits from
`BaseException`, not `Exception` — verified: `issubclass(asyncio.CancelledError, Exception)` is `False`,
MRO `CancelledError -> BaseException -> object`. A cancelled run therefore skips both handlers: the file
survives and the row stays `processing` until `cleanup_stale_processing_logs` marks it `failed` after
30 minutes. The same holds for a process killed between the unlink at `:533` and the commit at `:585`:
the file is already gone and the transaction never commits, so the row is left at `processing` naming a
file that no longer exists. `cleanup_stale_temp_files` cannot close either gap, because it selects on
`upload_temp_dir.glob("*.csv*")` and an `mtime` comparison (`services/file_cleanup.py:84`, `:88-99`) and
never consults `processing_logs`. Its bound is age only: the upload directory is unbounded in count and
in bytes over a 24-hour window, and the per-user rate limit on the endpoint is 100 uploads per hour
(`api/routes/upload.py:148-152`).

**Evidence** — Inheritance check executed as quoted above. The `except Exception` sites are
`data_worker.py:556` and `:588`; there is no `except BaseException` / `finally` unlink on the success
branch. `cleanup_stale_temp_files` reads only `st_mtime` (`file_cleanup.py:89`).

**Consequence** — Two residues. On shutdown or drain, in-flight inputs stay on disk for at least the
24-hour sweep threshold with their rows reading `failed` or `processing`. And because the sweep's only
signal is file age, the upload directory's steady-state size is `rate × ceiling × window` — with the
default 100 MiB ceiling and 100 uploads/hour/user, each editor can hold roughly 2.4 GB per day in the
shared temp volume, with no count or byte ceiling anywhere in the system.

**Recommendation** — Delete the file *after* the transaction commits, not before, and keep the delete in
a `finally` that also runs on `CancelledError` (catch `BaseException` for the cleanup only, then
re-raise). That removes both residues: a crash before the commit leaves the file for the sweep, and a
crash after it leaves neither. Add a byte ceiling to the sweep — reclaim when the directory exceeds a
configured total size, oldest first — so the area is bounded in bytes as well as in age.

### DP-017 — The stored row order is never pinned: the sort runs before the insert and the read has no ORDER BY

**Severity** — MEDIUM

**Zone** — Determinism of the aggregate: what makes identical input produce a different stored row

**Observation** — `AggregationService._apply_chart_sorting` is the only place row order is decided, and
its docstring says why: *"In stacked bar charts in Plotly, the trace order determines stacking. The
first trace appears at the bottom."* It sorts the aggregated frame (`:236`) and `_store_aggregates` then
inserts the rows in that order. Nothing persists the order: `AggregatedData` has an autoincrement
`BigInteger` primary key and no other ordering column (`db/models/aggregated_data.py:64-69`), and
`AggregatedDataRepository.get_by_graph_id` (`:146-163`) — the query behind `/data/aggregated` — has no
`ORDER BY`. In `append` mode the upsert rewrites `metrics` in place (`manager.py:335-344`), which writes
a new heap tuple and moves the row to the end of the heap, so rows that were re-upserted come back after
rows that were not.

**Evidence** — Static: absence of `order_by` in `get_by_graph_id`, `get_by_dashboard_id` and
`get_dims_values`; `_apply_chart_sorting`'s own statement of what the order is for
(`services/aggregation_service.py:170-176`). Executed: Polars does not return `group_by` results in key
order — the probe in DP-007 returned `S` before `N` — so even the insert order is not derived from the
dimensions.

**Consequence** — The trace order a stacked bar chart depends on is whatever the heap happens to yield.
After any `append` re-upload, the traces for re-upserted dimension values move to the end, so the same
dashboard renders the same numbers with a different stack order than it did before, with no change to
the data and no record of the change. The sort is also applied to the insert, not to the read, so it is
overwritten by the first write that touches a row.

**Recommendation** — Persist the order the chart needs: add an `ordinal` column to `aggregated_data`
populated from the sorted frame's row position, and add `ORDER BY ordinal` to `get_by_graph_id` and
`get_by_dashboard_id`. That is an Alembic migration (`alembic/versions/`), and it keeps the display
contract in one place instead of relying on heap order. If the migration is not wanted now, add
`ORDER BY id` to the reads as an interim measure and record the limitation in
`docs/09-database/schema-core.md`.

### DP-018 — An unrecognised metric aggregation is stored under its own name holding a sum

**Severity** — LOW

**Zone** — Determinism of the aggregate: what makes identical input produce a different stored row

**Observation** — `AggregationService.aggregate_for_dashboard` looks the aggregation up with
`_agg_fn_map.get(metric_agg, lambda c: c.sum())` (`:84-91`) and then names the output column after the
*requested* function regardless of which one ran:
`pl.col(m).alias(f"{m}_{metric_agg}")` (`:93`). `AggregationFunctionEnum` declares ten members —
`sum, mean, count, min, max, median, std, var, first, last` (`models/enums.py:162-174`) — and the map
implements five. This is currently masked: `metric_agg` is never read on the executing path (DP-002),
so the parameter is always `"sum"` and the mismatch cannot fire. It becomes reachable the moment DP-002
is fixed.

**Evidence** — Executed against Polars 1.41.2 with a frame whose `N` group sums to `15.0`:

```
  metric_agg=sum       -> {'revenue_sum': 15.0}
  metric_agg=median    -> {'revenue_median': 15.0}
  metric_agg=nonsense  -> {'revenue_nonsense': 15.0}
```

**Consequence** — Once DP-002 lands, a dashboard configured for `median` — a value the API accepts and
the OpenAPI schema advertises — stores a sum in a column named `revenue_median`, and the run reports
`completed`. The stored measure name would contradict its content permanently, and nothing downstream
could tell.

**Recommendation** — Resolve the function by enum, not by string lookup: pass
`AggregationFunctionEnum` rather than `str`, and either extend `AGG_FUNC_MAP`
(`data/processing/aggregate_transforms.py:16-27`, which already implements all ten) or reject the
unsupported ones. Alias the column from the function that actually ran, not from the request. Fix in
the same change as DP-002.

### DP-019 — Two of the three reclamation helpers in file_cleanup.py have no production caller

**Severity** — LOW

**Zone** — Cleanup and recovery: what reclaims an abandoned accepted input, in which process, on which clock, and what it cannot reach

**Observation** — `services/file_cleanup.py` presents itself as the cleanup module and defines
`cleanup_task_files` (`:23`), `cleanup_stale_temp_files` (`:46`) and `cleanup_old_processing_logs`
(`:109`). Only the middle one has a production caller (`db/starter.py:183`). `cleanup_task_files` — the
per-task deletion the module's docstring advertises — is called from `tests/test_file_cleanup.py` and
`tests/test_upload_api.py` only; the deletion the pipeline actually performs is the two inline
`file_path.unlink()` calls in the consumer. `cleanup_old_processing_logs` is likewise test-only, and is
duplicated by `DatabaseStarter.cleanup_old_logs` (`db/starter.py:402`), which runs the same
retention delete as parameterised SQL against the same bound.

**Evidence** — Repository-wide grep for all three names returns: the definitions in `file_cleanup.py`,
the call in `db/starter.py:33`/`:183`, and test call sites. No route, service or worker reference.

**Consequence** — The module's documented reclamation set overstates what the system does, and the
retention sweep exists twice with two implementations that can drift. No runtime effect today, because
the two uncalled functions are not load-bearing — but a reader sizing the reclamation story from
`file_cleanup.py` will over-count it, which is how DP-015's gap stays hidden.

**Recommendation** — Investigate purpose before removing anything, as the dead-code policy requires:
these are plausibly the intended home for the per-task deletion (see DP-016) and the retention sweep.
Either wire `cleanup_task_files` into the consumer as the single deletion helper and delete
`cleanup_old_processing_logs` in favour of the starter's, or delete both and correct the module
docstring and `docs/03-processing/file-cleanup.md` to list the two sweeps that actually run.
`tests/test_file_cleanup.py` covers all three and will need to follow whichever way it goes.

## Distribution

Every finding lands on the ingestion-and-aggregation path, and nine of nineteen sit in the two modules
that do the work: `workers/data_worker.py` (DP-001, DP-002, DP-004, DP-005, DP-009, DP-010, DP-011,
DP-013, DP-014, DP-015, DP-016) and `services/aggregation_service.py` (DP-003, DP-004, DP-006, DP-007,
DP-017, DP-018). `data/storage/manager.py` carries DP-004 and DP-017, `data/processing/*` carries
DP-007, DP-008 and DP-009, `services/file_cleanup.py` carries DP-016 and DP-019, `api/routes/upload.py`
carries DP-011 and DP-016, `config.py` only supplies the bounds.

- **By severity** — 3 CRITICAL, 7 HIGH, 7 MEDIUM, 2 LOW.
- **By stage of the path** — admission 2, accepting path and atomicity 2, aggregate identity and
  determinism 5, replacement and the secondary list 3, configuration reach 5, classification 1,
  validation 2, reclamation 3.
- **By failure mode** — 12 findings are silent (the run reports `completed`, or `failed` with a code
  that misdirects); 7 are loud failures.
- **By blast radius** — DP-005 and DP-006 stop ingestion entirely for a large class of dashboards;
  DP-001 and DP-003 corrupt data that nothing downstream can detect; DP-002 mislabels every metric the
  system stores.
- **Single heaviest component** — `workers/data_worker.py`, at 11 of 19, and the only file that appears
  in all four of the heaviest stages.

## Cross-Finding Analysis

Four causes account for fifteen of the nineteen findings.

**One cause — the worker's own `processing_config_dict` is read under two different shapes.** `data_worker.py:404`
unwraps with `processing_config_dict.get("settings", processing_config_dict)`; `:694` and `:772` do not.
The second shape has no producer, so `metric_agg` never reaches the aggregator (DP-002) and the fallback
in the aggregation map is what will run once it is fixed (DP-018). Fixing the shape without fixing the map
converts a dead field into a mislabelled one.

**One cause — the frame is mutated by configuration before any check runs, in an order nothing states.**
The sequence validate → decimal separator → cast → rename → computed fields → transform → aggregate
(`data_worker.py:419-516`) puts the validator in the pre-rename namespace while every consumer is
post-rename (DP-014), and puts the type cast after the check that is supposed to verify it, so the
declared type can never become true (DP-013).

**One cause — nothing in the accepting or storing path ever asks whether the selection it is about to
write is empty.** `save_aggregates` returns before the clear (`manager.py:97`), so an overwrite that
matches nothing keeps the previous rows (DP-004); `aggregate_for_dashboard` builds a group key by
concatenation without de-duplication, so an ordinary filter/dimension overlap aborts everything
(DP-006); `extract_filter_values` hands native types to a `VARCHAR` column, so a numeric filter fails
every run (DP-005). All three are the same missing guard at three layers, and all three are reachable
from ordinary dashboard configuration.

**One cause — the pipeline trusts that its effects share a fate, and they do not.** The queue submission
and the file rename sit outside the transaction that commits the status row, with compensation on one
edge only (DP-001); the file unlink sits inside the transaction it cannot roll back and outside every
`except` clause a cancellation can reach (DP-016). Reclamation compensates for neither, because it
selects on file age and never consults `processing_logs` (DP-015, DP-016).

The remaining four are independent of each other and of the four causes above: DP-003 (identity is
dtype-sensitive), DP-007 and DP-008 (two separate order-dependencies in the same configuration
surface), DP-010 (classification by message text), DP-017 (order not persisted), DP-019 (uncalled
helpers).

## Roadmap

Grouped by cause. Each step names what must be true before the next begins.

**Step 1 — close the shape mismatch before anything can be measured.** DP-002 and DP-018 together.
Must be true before Step 2: dashboards that were silently summing now produce their configured
aggregate, so every downstream number moves and the fixture data used by Steps 2-4 must be re-baselined
first. Ship DP-018 in the same commit so the newly-reachable path is not a mislabelled one. Verify with
a worker test that stores `metric_agg: "mean"` and asserts the stored metric key and its value.

**Step 2 — add the empty-selection guards.** DP-004, DP-006, DP-005. Independent of each other but they
share a test fixture: one dashboard, one graph, one filter, four uploads (matching, non-matching,
filter-named-like-dimension, numeric-filter). DP-004's fix deliberately turns a silent no-op into a
failed run, so the status text and the frontend's `failed` rendering must be agreed before merge.
DP-005's fix touches the `dashboard_filter_values` write path, which `filter_values_service.py` also
reads; confirm that reader still gets strings.

**Step 3 — make the frame's mutation order explicit.** DP-013 and DP-014. Must be true before Step 4:
Step 4's tests assert stored values, and those values change once casts run before validation. Move the
validator after casts and renames, then add the `extra="forbid"` settings model at the storage boundary
— which changes the API's response to an unknown field from silently-ignored to 422, so check
`PUT /processing-configs/{dashboard_id}` callers and the frontend form first.

**Step 4 — remove the order-dependencies.** DP-003, DP-007, DP-008. DP-003 is the only one that changes
stored row counts, so run it against a copy of `aggregated_data` first to size how many dashboards
already hold duplicate identity pairs. DP-007 and DP-008 need a decision on what `groupby`-alone and
`limit`-without-`sort_by` are meant to mean before any code changes; both default to failing the run
rather than storing an arbitrary result. DP-017's `ORDER BY ordinal` migration lands here because it
depends on DP-003's canonicalisation of `dims`.

**Step 5 — fix the transaction and reclamation boundaries.** DP-001, DP-016, DP-015, DP-019. Largest and
riskiest; do it last because it reorders the accepting path that every other step's tests exercise.
DP-001 requires moving the commit ahead of the move and the enqueue, which changes the failure semantics
the upload tests currently pin. DP-015 and DP-016 are independent of DP-001 and can ship in either
order. DP-019 is documentation plus whichever direction the investigation lands on.

**Step 6 — classification, last.** DP-010. Only worth doing once DP-009 and DP-002 have stopped
producing failures whose text is misleading; a better classifier on top of today's failure population
produces better codes for the wrong reasons.

## Rollout Safety

Steps 1, 2 and 4 change observable behaviour on dashboards that are running today.

**Step 1** changes every stored metric on every dashboard: anything configured for `mean`, `min`, `max`
or `count` will serve a different number the day it ships, and dashboards configured for `median`,
`std`, `var`, `first` or `last` will start storing correctly-labelled aggregates instead of mislabelled
sums. Nothing in the system records the old values, so take a `pg_dump` of `aggregated_data` before the
deploy and be prepared to restore it. `02`'s retention sweep is the only path that removes those rows,
so the backup is the only rollback. Step 4's DP-003 likewise adds or removes stored rows without a
record of which were split.

**Step 2** turns a silently-successful upload into a failed one for any dashboard whose upload does not
match its chart dimensions. That is the correct behaviour but it is a visible outage for those
dashboards: the client already renders `failed` with a message, so the only additional work is making
the message name the skipped graphs. DP-005's fix changes the type of `dashboard_filter_values.filter_value`
on the write path only — the column stays `String(1024)` and the reader is unchanged — so it is
revert-safe, but dashboards whose numeric filters have been failing will start succeeding and will
begin writing rows they have never written before.

**Step 4's** `groupby`/`limit` decisions fail runs that previously stored an arbitrary number, which is
a visible change for exactly the dashboards that were silently wrong. Step 5 reorders the accepting
path; the upload tests that pin enqueue-before-commit are the gate, and they must change with the code
rather than be weakened around it. Every step is a pure code change — no schema migration is required
except DP-017's `ordinal` column, which is Alembic and additive with a backfill from the current
`id` order.

## Appendices

### A. Baseline and concurrent-edit reconciliation

Recorded at task start: `HEAD 8505a621dc5d3001470b4da9b6e210c05f351544`, dirty tree on
`src/mkobi/config.py`, `src/mkobi/db/starter.py`, `tests/test_config.py`, `tests/test_starter.py`
(plus deletions under `.ai/`). HEAD moved twice during execution, to
`2d23c27f929133f6ff88cfb8bbda1ca1cb200db3` (*"reject shipped credential placeholders and empty admin
credentials in production"*) and then to `c3c0a61bf41cad68bf3a3ac105de91ea63c82268` (*"reject the shipped
CHANGE_ME_ADMIN_USERNAME placeholder in production"*). `c3c0a61` touched `src/mkobi/config.py` (+39/-5)
and `src/mkobi/db/starter.py` (+3/-1) and left `tests/test_starter.py` clean; at hand-off both source
files are committed and the working tree carries only this report. Every anchor cited in this report
from those two files was re-read against `2d23c27` and again against `c3c0a61`: values *and* quoted line
numbers are identical across all three commits, because both commits changed only the
credential-predicate region near the top of `config.py` and the admin bootstrap in `starter.py`.

| anchor | at `8505a62` | at `2d23c27` / `c3c0a61` | value |
|---|---|---|---|
| `UploadSettings.max_file_size_mb` | 264 | 286 | `100` |
| `UploadSettings.lazy_threshold_mb` | 273 | 295 | `10.0` |
| `logs_retention_days` | 385 | 407 | `30` |
| `stale_file_threshold_hours` | 386 | 408 | `24` |
| `stale_processing_timeout_minutes` | 387 | 409 | `30` |
| `stale_processing_cleanup_interval_seconds` | 388 | 410 | `300` |
| `Config.max_file_size` | 776 | 805 | `max_file_size_mb * 1024 * 1024` |
| `Config.upload_temp_dir` / `allowed_file_types` | 756 / 761 | 785 / 790 | unchanged |
| `starter.py` `cleanup_stale_temp_files()` / `cleanup_old_logs()` | 182 / 187 | 183 / 188 | unchanged |
| `starter.py` `def cleanup_old_logs` | 401 | 402 | unchanged |

No finding depends on a line number alone. Nothing in `src/mkobi/data`, `src/mkobi/workers`,
`src/mkobi/services`, `src/mkobi/models` or `src/mkobi/db/repositories` was touched by the concurrent
programme. The only file this audit created is this report.

### B. Coverage record — one row per audit block

| # | block | artefact in this report |
|---|---|---|
| 1 | Ingestion admission | DP-011, DP-012; inventory below |
| 2 | State of an accepted upload | inventory below; `STARTED` never committed; declared transitions unenforced (08's angle) |
| 3 | Unit of atomicity | DP-001; effect inventory below |
| 4 | Determinism of the aggregate | DP-003, DP-007, DP-008, DP-017, DP-018 |
| 5 | Replacement semantics | DP-004, DP-005; per-mode table below |
| 6 | Configuration reach | DP-002, DP-006, DP-009, DP-014; field inventory below |
| 7 | Caller-supplied expressions | inventory below; no finding filed (limits are enforced at compile time, in one place) |
| 8 | Failure classification | DP-010; site table in the finding |
| 9 | Validation of the loaded frame | DP-013, DP-014; check inventory below |
| 10 | Cleanup and recovery | DP-015, DP-016, DP-019; sweep table in DP-015 |

### C. Admission inventory (block 1)

| limit | declared in | enforcing layer | process | consulted on every path? |
|---|---|---|---|---|
| size ceiling (declared `Content-Length`) | `MAX_FILE_SIZE_MB`, `config.py:286`/`:805` | route | request | yes |
| size ceiling (cumulative, 8 KiB chunks) | same | route | request | yes |
| size ceiling (service layer) | same | `file_processing.py:150` | request | yes |
| size ceiling (loader) | `LoaderConfig.max_file_size`, `models/data.py:278` — **code literal** | `loader.py:256` | worker | yes, at a fixed 100 MiB → DP-012 |
| MIME from content | `MimeTypeEnum`, `enums.py:92` | `file_processing.py:85-94` | request | yes — but not re-checked in the worker |
| extension on caller-supplied name | `allowed_extensions`, `config.py:287` | `file_processing.py:136` | request | yes |
| rate limit, 100/hour/user | literal at `upload.py:149-151` | route | request | yes — 15 is header/origin policy's angle |

Residency: at most `CHUNK_SIZE` = 8192 bytes of the request body is resident during transfer. The whole
input becomes one in-memory `pl.DataFrame` at `CSVLoader.load_csv`, reached from `data_worker.py:413-416`
inside `asyncio.to_thread`, and is held through validate, transform and aggregate. The `scan_csv(...).collect()`
branch (`loader.py:215`) does not change this.

### D. State inventory (block 2)

| state | can a committed row hold it? | writers |
|---|---|---|
| `started` | **no** — `create_log(STARTED)` and the `update_status(UPLOADED)` that follows are in one transaction (`file_processing.py:215-231`), so `STARTED` is never visible to another session | — |
| `uploaded` | yes | `process_upload_with_session` (request); `mark_orphaned_uploaded_logs_failed` → `failed` (startup only) |
| `processing` | yes | consumer (`data_worker.py:390`); `DataService.trigger_processing:280` — **no route caller, unreachable**; `cleanup_stale_processing_logs` → `failed` |
| `completed` | yes | consumer only (`data_worker.py:537`) |
| `failed` | yes | consumer (`:573`, `:608`); `DataService.trigger_processing:293` (unreachable); both recovery sweeps |

No writer reaches a state its peers cannot. The one overlap the block asks about: `cleanup_stale_processing_logs`
rewrites `processing → failed`, and the consumer writes the same transition directly. Both run in the
serving process (`app.py:120-125`), which is also where the consumer runs (TOPO-002, TOPO-005).
`started_at` is set at `create_log` (`processing_log_repo.py:56`) and overwritten when the consumer
claims the task (`data_worker.py:394`), so the two sweeps read the clock they mean.
`ProcessingStatus.valid_transitions()` (`enums.py:67-80`) is referenced by no writer and no test in
`src/`; whether a declared transition table is enforced is 08's angle and is not filed here.

### E. Effect inventory (block 3)

| # | effect | shares a commit? | compensation |
|---|---|---|---|
| 1 | temp file `upload_{uuid}_{name}` | no | route `finally`, `upload.py:229` |
| 2 | `processing_logs` row (`uploaded`) | **the only one** | `rollback` on rename/enqueue failure |
| 3 | stored file `{log.id}.csv[.gz]` | no | unlinked on enqueue failure only → DP-001 |
| 4 | queue submission | no | none → DP-001 |
| 5 | derived rows + filter values + `completed` | yes (worker's single transaction, `data_worker.py:584-585`) | transaction rollback; file unlinked at `:533` before the commit → DP-016 |

Induced failure and residue, executed (`COMMIT` forced to raise): effect 1 gone, **2 absent**, **3
present**, **4 present and pointing at 3**, and the consumer's status write against 2 matching zero rows
without error.

### F. Replacement semantics (block 5)

| mode | selection removed | rows written | selection left untouched |
|---|---|---|---|
| `overwrite`, non-empty selection | all rows for the dashboard (`manager.py:113-114`) | all graphs that produced ≥1 group | graphs that produced none — but their rows were already deleted |
| `overwrite`, **empty** selection | **nothing** (`manager.py:97-102`) | none | everything → DP-004 |
| `append` | none | upserted on `(dashboard_id, graph_id, dims::text)`; `metrics` replaced wholesale | rows whose dims the new frame does not produce → their metric keys are the old ones → DP-003, DP-018 |
| either, dashboard with no graphs | nothing; `_store_aggregates` returns at `data_worker.py:680`/`:758` | none | everything |

Secondary list: cleared unconditionally before the rebuild (`data_worker.py:726`, `:804`), then rebuilt
from `records` (the in-memory result of this run) in `overwrite` mode, and from
`manager.get_aggregates(dashboard_id)` (the table, after the upsert) in `append` mode. The two sources
agree only while the selection is non-empty; in the empty-selection case the table still holds the
previous rows while the rebuild is handed an empty list, which is how DP-004 leaves rows in place and
filter values at zero.

### G. Configuration field inventory (block 6)

Read from the executing path (`data_worker.py:403-516`, `:694`, `:772`):

| field | absent | unknown value | malformed |
|---|---|---|---|
| `separator`, `encoding` | ignored by the loader (absent key ⇒ Polars default) | passed to Polars ⇒ fails late | fails in Polars, late |
| `column_types` | no cast | unknown type name ⇒ no branch matches, silent | cast failure caught and logged, run continues → DP-013 |
| `date_format` | `date` becomes a **silent no-op** (`:456`) | n/a | strptime failure, late |
| `decimal_separator` | `float` columns never cast | only `","` has a branch | n/a |
| `required_columns` | no schema check at all | n/a | fails the run, but before renames → DP-014 |
| `renames` | no rename | misspelled field name ⇒ silent no-op → DP-014 | missing source column ⇒ late failure |
| `computed_fields` | no field | misspelled field name ⇒ silent no-op | bad expression ⇒ run fails |
| `metric_agg` | **`sum` always** — the field is read under the wrong shape → DP-002 | falls back to `sum`, aliased with the requested name → DP-018 | non-`str` ⇒ `_extract_metric_agg_from_settings` returns `None` |
| `groupby` | no reduction | unknown column ⇒ Polars error | silent |
| `aggregations` | no aggregation | unknown function ⇒ `logger.warning` + `continue` (`aggregate_transforms.py:140-141`), run continues | `_validate_processing_config` fails the run, at `:487`, after the file is read |
| `filters` | none applied | unknown operator ⇒ warning + skip | missing column ⇒ warning + skip |
| `sort_by`, `descending`, `limit` | none | unknown column ⇒ Polars error | late |
| `yoy_config`, `share_config`, `custom_metrics` | — | **`**` on a Pydantic model ⇒ `TypeError`; `.get` on a model ⇒ `AttributeError`** → DP-009 | same |

Boundary validation: `ProcessingConfigService._validate_settings`
(`processing_config_service.py:73-103`) type-checks four fields and nothing else. The first rejection of
an invalid document is `ProcessingConfig(**processing_config_dict)` at `data_worker.py:487` — in the
worker, after the file has been loaded, validated and transformed. `_validate_processing_config` runs
immediately after it. Nothing rejects the document at the API.

### H. Expression grammars (block 7)

Two grammars, both in `data/processing/formula_parser.py`, both enforced **at compile time in the worker**
— no limit is applied when the expression arrives, because `ProcessingConfigService._validate_settings`
does not look at `custom_metrics` or `computed_fields` at all.

- **Arithmetic** — `_parse_formula` (`:52-160`). Operands must match `[a-zA-Z_][a-zA-Z0-9_]*` or be a
  numeric literal; operators `+ - * /`; no parentheses, no precedence, no unary minus (documented at
  `:66-75`).
- **Date parts** — `_parse_polars_dt_expr` (`:203-285`). Only `pl.col('x').dt.<method>()`, method drawn
  from `_ALLOWED_DT_METHODS` (12 names, `:15-27`), format string for `strftime` required to be quoted.

Both build `pl.col(...)` / `pl.lit(...)` objects directly; there is no `eval`, no attribute lookup by
string, and no route from a stored string to any source of values other than the loaded frame's own
columns and literals. The identifier the grammar admits and the loaded data does not hold was measured:
`revenue / cost` compiles cleanly (`[(col("revenue")) / (col("cost"))]`) and raises
`ColumnNotFoundError: unable to find column "cost"` at evaluation, which fails the run and classifies as
`PROCESSING_FAILED` (DP-010). That is a loud failure at a defined point rather than a silent wrong
answer, so no finding is filed here; the boundary recommendation is DP-014's `extra="forbid"` plus
validating expression identifiers against `df.columns` once, in `_add_computed_fields`, so the error
names the field instead of arriving as a Polars `ColumnNotFoundError`. No expression whose resolution
depends on *when* it is compiled was found: `_add_computed_fields` applies fields in list order and a
later field can read an earlier field's output by design (`:107`), which is order-dependence by
configuration, not by timing.

### I. Validation check inventory (block 9)

| check | verdict | gated on |
|---|---|---|
| non-empty frame | **refuse** (`validator.py:55-65`) | always |
| required columns present | **refuse** (`:105-132`) | `settings.required_columns` — absent by default ⇒ never runs |
| declared vs actual column type | annotate | `settings.column_types`; can never be true, see DP-013 |
| nulls in required columns | annotate | `required_columns` |
| empty strings in text columns | annotate | always |
| duplicate rows (all columns / key columns) | annotate | always |
| per-column cast | annotate and continue (`data_worker.py:468-469`) | `column_types` |
| `strict_schema` extra/missing columns | **never called** — `validate_schema` (`validator.py:262`) has no caller in `src/` | — |

Annotations are produced by `DataValidator` and logged there; the worker reads only `errors` and
`is_valid`. Nothing is persisted and no reader exists (DP-013).

### J. What could not be verified in this environment

- **libmagic behaviour.** `python-magic` raises `ImportError` at *import* on this host (no libmagic), so
  `file_processing.py`'s `try: import magic / except ImportError` correctly selects the gzip/CSV-sniff
  fallback, and the Docker images install `libmagic1` (`docker/Dockerfile:46`, `:80`). The content-type
  limit was therefore reviewed statically in both branches, not executed against libmagic. The fallback
  admits anything whose first 2048 bytes contain a newline and a comma or semicolon as `text/csv`; the
  extension check still requires `.csv`/`.csv.gz`, and production does not take this path, so no finding
  is filed.
- **A real end-to-end upload through the HTTP route** was not exercised: the dev stack's data volume
  holds live data and the test stack's `bidb_test` is in use by a concurrent run. Every live probe ran
  inside a transaction that was rolled back, and DP-001's queue/file residue was observed on the
  filesystem and in the in-process queue rather than by letting the real consumer run to completion. The
  composition of the residue — aggregates written, no status row — follows from reading
  `_store_aggregates` under the same transaction, not from an observed second write.
- **Concurrent writers.** Every aggregate-storage observation here is single-writer. `INSERT ... ON
  CONFLICT` under two concurrent appends is transaction and lock semantics, which is 03's angle.
- **Timing.** DP-015 and DP-016 were established from the code and from Python's exception hierarchy;
  no 24-hour or 30-minute clock was waited out.
