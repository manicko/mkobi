---
phase: 05-data-pipeline
executed: 2026-10-05
executor: auditor
problems-only: true
findings: 11
by-severity:
  CRITICAL: 1
  HIGH: 2
  MEDIUM: 6
  LOW: 2
---

# Phase 05 — Findings

## Summary

Eleven problems are recorded across the ingestion-to-aggregate path: the upload route and its
admission boundary (`api/routes/upload.py`, `services/file_processing.py`), the accepting service
(`services/data_service.py`), the async worker and its reconciler (`workers/data_worker.py`,
`rq_worker_wrapper.py`, `core/task_queue.py`), the Polars load/validate/transform layer
(`data/loaders/*`, `data/processing/*`), the per-chart aggregator (`services/aggregation_service.py`)
and the write boundary (`data/storage/manager.py`, `db/models/aggregated_data.py`), plus the served
read path (`api/routes/data.py`, `db/repositories/graph_repo.py`). Runtime was reached: the live dev
PostgreSQL was queried read-only for the unique-index definition and for its `jsonb` NaN/`Infinity`
rejection, and the production Polars + Pydantic v2 + canonicalisation functions were executed against
real input. The most consequential item is that the canonical form of a dimension value is not
injective — a null and an empty string, and a non-finite float and the literal text naming it, both
collapse to one stored identity, so one group's aggregate can be silently replaced by another's
(DP-103). Immediately behind it, the settings object the worker receives from a stored
`ProcessingSettingsModel` carries `required_columns=None`, and `LoaderConfig` refuses `None`, which
fails every upload to any configured dashboard (DP-101).

**Finding-ID namespace disclosure.** The prefix `DP-` was checked for collisions before minting
identifiers. `DP-001 … DP-019` are occupied by this phase's own earlier audit pass, whose rows remain
referenced from `docs/SPEC.md`, `docs/03-processing/processing-api.md`, `docs/03-processing/file-cleanup.md`,
`.ai/tasks/B3-txn-003-durable-processing-transitions.yaml` and `.ai/audit/_base-context.md:134`. A
separate two-digit `DP-NN` series (e.g. `DP-07-G`, `DP-11-B`) is used for *plan decision records* in
`.ai/decisions/`. `DP-1xx` and above were verified free across `docs/`, `.ai/`, `src/`, `tests/`,
`frontend/`, `alembic/` and `docker/`; this pass therefore starts at `DP-101`. No collision.

## Findings

### DP-101 — Every upload to a dashboard with a stored processing config fails: the settings object carries `required_columns=None` and `LoaderConfig` refuses `None`

**Severity** — HIGH

**Zone** — "6. Configuration reach: which parts of a stored processing configuration are honoured, which are skipped, and which fail the run late"

**Observation** — The producer of the worker's settings mapping is
`services/data_service.py::DataService._execute_upload`, which converts the read model to a plain dict
with `dict(config_response.settings)`. `ProcessingConfigRead.settings` is a `ProcessingSettingsModel`
(`src/mkobi/models/processing_configs.py:12`), whose `required_columns` field is declared nullable with
a `None` default (`src/mkobi/models/types.py:370`):

```python
    required_columns: list[str] | None = None
```

`dict()` on a Pydantic v2 model yields **every** field, so the mapping always contains the key
`required_columns` with value `None` whenever the operator never set it. That mapping travels
`processing_config=processing_config` (`src/mkobi/services/data_service.py:186`) →
`process_upload_with_session` → the enqueued job → `workers/data_worker.py`, where
`_run_with_transaction` reads it at `src/mkobi/workers/data_worker.py:689`:

```python
        if processing_config_dict:
            settings = processing_config_dict.get("settings", processing_config_dict)
```

and constructs the validator's config at `src/mkobi/workers/data_worker.py:776`:

```python
        loader_config = LoaderConfig(
            required_columns=settings.get("required_columns", []) if settings else [],
            column_types=column_types,
        )
```

`dict.get(key, default)` returns `None` when the key is **present** with a `None` value; the `[]`
default is unreachable for a model-derived mapping. `LoaderConfig` declares the field non-nullable
(`src/mkobi/models/data.py:325`):

```python
    required_columns: list[str] = Field(
        default_factory=list,
        description="List of required columns",
    )
```

**Evidence** — The two production types were executed with the exact values the two cited lines
produce (`uv run python`, Polars 1.41.2, SQLAlchemy 2.0.50, pydantic 2.13):

```
required_columns in dict: True None
column_types in dict: {'revenue': 'float'}
separator in dict: None
LoaderConfig RAISED: ValidationError
1 validation error for LoaderConfig
required_columns
  Input should be a valid list [type=list_type, input_value=None, input_type=NoneType]
```

`pydantic.ValidationError` is a `ValueError` subclass, so it reaches the run's `except Exception`
handler, and `_map_processing_error_to_code` finds no `ErrorCode`, no lock timeout, no
`FileNotFoundError`, and none of its message substrings — so the run is classified `processing_failed`
and `_durable_failure_message` stores the fixed sentence `"Processing failed"`
(`src/mkobi/workers/data_worker.py:158`, `:1074`). The exception text, which is the only place the
cause appears, is never written to the row.

Test-gap half of the finding: every worker test hand-builds the mapping and so never carries the
`None` key — `tests/test_data_worker.py:1408` passes `processing_config_dict={"metric_agg": "mean"}`,
and `tests/test_processing_config_boundary.py:185` passes a two-key literal. No test drives
`_run_with_transaction` with a mapping derived from a `ProcessingSettingsModel`.

**Consequence** — As the code stands, any dashboard that has a `processing_configs` row and no
explicit `required_columns` fails every upload deterministically, in the RQ job, after the upload has
already been admitted (`201`), the file written and the job queued. `save_aggregates` is never reached,
so no partial aggregate state is left and the previously stored rows survive — but the feature is
entirely inoperative for exactly the dashboards an operator has configured, and the operator is told
only `error_code: processing_failed` / `"Processing failed"`, with the real cause reachable only from
the worker log (which, per already-reported `TOPO-102`, the `rq-worker` container does not emit).
Dashboards with no `processing_configs` row are unaffected, which is why the defect is invisible in a
bare dev stack.

**Recommendation** — Coerce at the read, not at the use: `settings.get("required_columns") or []`, or
make `LoaderConfig.required_columns` accept `None` and default it. Prefer the former — it keeps the
validator contract non-nullable and fixes the whole class of `dict(model)` nullable-key mismatches
rather than this one instance. Add a worker test whose `processing_config_dict` is
`dict(ProcessingSettingsModel.model_validate({...}))` rather than a hand-built literal; that is the
shape production produces and the shape no test exercises.

### DP-102 — A non-finite metric reaches the `ARRAY(JSONB)` bind unmodified, so a file the loader accepts fails the whole upload with an opaque class

**Severity** — HIGH

**Zone** — "9. Validation of the loaded frame: what is refused, what is only warned, and whether a warning is stored anyway"

**Observation** — `StorageManager._write_set_based` canonicalises `dims` and passes `metrics` through
verbatim (`src/mkobi/data/storage/manager.py:487`):

```python
            dims = [_canonicalize_dims(agg["dims"]) for agg in chunk]
            metrics = [agg["metrics"] for agg in chunk]
```

```python
            dims_param = bindparam("dims", type_=ARRAY(JSONB))
            metrics_param = bindparam("metrics", type_=ARRAY(JSONB))
```

Nothing between the Polars frame and this bind rejects or substitutes a non-finite `float`. The
canonicalisation docstring states the intent explicitly (`src/mkobi/data/storage/manager.py:88`):
`` ``metrics`` are deliberately NOT canonicalised -- numbers there are the data.`` — which is correct
policy, but it leaves the write as the only place a non-finite value can be caught, and that place is a
driver error rather than a refusal. `DataValidator` (`src/mkobi/data/loaders/validator.py`) contains no
finiteness check, so nothing in the pipeline refuses such a file at any earlier stage. The
`INSERT ... SELECT * FROM unnest(...)` at `src/mkobi/data/storage/manager.py:499` is a plain insert for
the OVERWRITE path (`_bulk_insert`, `:414`, `on_conflict=False`) and an `ON CONFLICT ... DO UPDATE` for
APPEND — both carry the same metric payload, so both fail.

**Evidence** — Each link of the chain was executed, at `uv run python` against Polars 1.41.2 and against
the live dev PostgreSQL 18 (`mkobi-db-1`, read-only `SELECT`s, no rows written):

1. Polars parses non-finite literals out of a plain CSV — `region,revenue` with body `NaN`, `inf`,
   `-inf`, `1e999` yields `csv schema: {'a': Int64, 'b': Float64}` and
   `csv rows: [nan, inf, -inf, inf]`.
2. One non-finite cell poisons **every** aggregate function, not only `sum`. Grouping
   `a,b` on rows `(1, NaN)` and `(2, 5)` gives `b_sum=NaN`, `b_mean=NaN`, `b_min=NaN`, `b_max=NaN`.
3. `json.dumps` emits the bare token: `json.dumps of those: {"ratio": Infinity}`.
4. PostgreSQL refuses it: `SELECT '{"a": NaN}'::jsonb;` →
   `ERROR: invalid input syntax for type json / DETAIL: Token "NaN" is invalid.`, and
   `SELECT '{"a": Infinity}'::jsonb;` → `DETAIL: Token "Infinity" is invalid.`

Not executed: the composed insert against a live `aggregated_data` table. No probe row was written.

**Consequence** — Any upload whose numeric columns contain the token `NaN`, `inf`/`Inf`/`INF`, `-inf`,
or a literal that overflows `Float64` (`1e999`), in any column used as a graph metric, fails the entire
run. The same input reaches `inf` through a configured `custom_metrics` expression dividing by zero —
`pl.DataFrame({'a':[1.0,2.0],'b':[0.0,0.0]}).with_columns((pl.col('a')/pl.col('b')).alias('ratio'))`
yields `[inf, inf]`. The operator sees `error_code: processing_failed` and `"Processing failed"`; the
`jsonb` parse error is discarded by `_durable_failure_message` and is not attributable from the row,
the history list, or the client. Because every aggregation function is poisoned, there is no
`metric_agg` an operator can switch to that avoids it.

**Recommendation** — Refuse non-finite values in the frame, before aggregation, with a code that says
so: a check in `DataValidator.validate` for non-finite values in declared numeric columns, raising
`VALIDATION_ERROR` with the offending column names, is the smallest change and lands in the layer whose
declared job is to refuse the loaded frame. Alternatively sanitize at the write boundary
(`math.isfinite` → `None` or raise) — but that loses the value silently, which is worse. Whichever is
chosen, the `metrics`-are-not-canonicalised docstring at `src/mkobi/data/storage/manager.py:88` should
be extended to state that finiteness is enforced upstream, so the two are not read as independent.

### DP-103 — The canonical form of a dimension value is not injective: a null and an empty string — and a non-finite float and the literal text naming it — collapse into one stored identity

**Severity** — CRITICAL

**Zone** — "4. Determinism of the aggregate: what makes identical input produce a different stored row"

**Observation** — The identity that decides whether an aggregate row updates an existing one is the
unique index `uq_aggregated_data_dashboard_graph_dims` over `(dashboard_id, graph_id, dims::text)`
(`src/mkobi/db/models/aggregated_data.py:55`; confirmed live as
`CREATE UNIQUE INDEX ... ON public.aggregated_data USING btree (dashboard_id, graph_id, ((dims)::text))`).
Identity therefore depends entirely on the canonical form of each `dims` value, which is produced in two
steps. Step one, `AggregationService._coerce_dim_value` (`src/mkobi/services/aggregation_service.py:66`)
maps `None` to the empty string:

```python
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)
```

Step two, `StorageManager._canonicalize_dim_scalar` (`src/mkobi/data/storage/manager.py:90`) stringifies
what step one preserved natively:

```python
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)
```

Both steps map distinct inputs onto one output: `None → ""` while the empty string is already `""`, and
`float('nan') → "nan"` while the literal text `nan` is already `"nan"`. The system's declared null
representation and the empty string are the same value, and no dim value can carry a JSON `null`.

**Evidence** — The production functions were executed against real input. A CSV with an unquoted empty
field (null) *and* a quoted `""` (empty string) in one dimension column produces two distinct Polars
groups that canonicalise to one identity:

```
Schema({'region': String, 'revenue': Int64})
shape: (4, 2)   region: South | "" | North | null
[{'dims': {'region': 'South'}, ...}, {'dims': {'region': ''}, 'metrics': {'revenue_sum': 7}},
 {'dims': {'region': 'North'}, ...}, {'dims': {'region': ''}, 'metrics': {'revenue_sum': 5}}]
[{'region': 'South'}, {'region': ''}, {'region': 'North'}, {'region': ''}]
distinct canonical: 3 of 4
```

The same holds for non-finite floats, executed through both production functions:

```
nan -> coerce nan -> canonical 'nan'      | 'nan'  -> coerce 'nan'  -> canonical 'nan'
inf -> coerce inf -> canonical 'inf'      | 'inf'  -> coerce 'inf'  -> canonical 'inf'
None -> coerce '' -> canonical ''         | ''     -> coerce ''     -> canonical ''
```

The OVERWRITE writer is a plain insert with no conflict clause — `StorageManager._bulk_insert`
(`src/mkobi/data/storage/manager.py:414`) passes `on_conflict=False` to `_write_set_based` (`:428`), so
two records with one identity inside one statement violate the index outright.

**Consequence** — The silent form is in APPEND mode across uploads, which is where it becomes wrong data
rather than a failed run. Upload A stores `{"region": ""}` carrying the aggregate of the rows whose
region cell was **empty**; upload B, whose region cells contain a **literal empty string**, upserts the
same `(dashboard_id, graph_id, dims)` identity and replaces A's metric with B's. The stored row is then
wrong now and nothing downstream can tell: the chart renders one "blank" category whose value belongs to
neither upload, and `GET /data/aggregated` reports it as a single group. The same identity collision
silently merges a `NaN`/`inf` dimension into the literal text naming it whenever the metrics on those rows
are themselves finite (so it survives DP-102). In the loud forms the whole upload fails instead:
OVERWRITE hits the unique index on the second `{"region": ""}` row and APPEND raises *"ON CONFLICT DO
UPDATE command cannot affect row a second time"* — either way classified `processing_failed` and reported
as `"Processing failed"`. The trigger is not exotic: any exporter that writes `""` for an empty string in
a dimension column, next to rows that leave the cell empty, does it.

**Recommendation** — Make the canonical form injective rather than patching one colliding pair. Two
options, in order of preference: (a) keep `null` as a real JSON `null` in `dims` and have
`_coerce_dim_value` stop collapsing `None` to `""`, which requires the read path's
`AggregatedFiltersRequest` comparison (`AggregatedData.dims[key].astext == str(value)`,
`src/mkobi/db/repositories/aggregated_data_repo.py`) to handle JSON null alongside text; or (b) prefix
the empty-string sentinel so it cannot collide with a genuine empty string, at the cost of the read path
agreeing on the prefix. Option (a) is the honest fix and removes the class; option (b) is smaller and
still injective. Do not merge the two records instead — that would silently sum two distinct categories.
Add a regression test over a CSV carrying both an empty field and a quoted `""` in the same dimension
column, asserting the row count and that the two identities stay distinct. Neither
`docs/03-processing/processing-api.md:146` nor `src/mkobi/data/storage/manager.py:76-88` states that the
canonicalisation is lossy, so both need a sentence saying whether the design intends `null` and `""` to
be the same value; that sentence is what decides between (a) and (b).

### DP-104 — The empty-selection guard's diagnostic is discarded, so the failure that names the lost charts reports only "Processing failed"

**Severity** — MEDIUM

**Zone** — "8. Failure classification: how an outcome is categorised, and what each category reaches"

**Observation** — `_store_aggregates` builds a detail naming the graphs the upload produced nothing for
and raises it (`src/mkobi/workers/data_worker.py:1242`):

```python
    if skipped_graph_names:
        detail = _empty_selection_detail(skipped_graph_names)
        logger.error(
            "No aggregates produced for graphs=%s, dashboard_id=%s, task_id=%s",
            skipped_graph_names,
            dashboard_id,
            task_id,
        )
        raise AppException(
            code=ErrorCode.PROCESSING_FAILED,
            detail=detail,
        )
```

Both production handlers then discard `detail` and write a fixed per-class sentence —
`src/mkobi/workers/data_worker.py:977` and `:1074` both pass
`message=_durable_failure_message(e)`, which resolves through `_FAILURE_MESSAGE_BY_CODE`
(`src/mkobi/workers/data_worker.py:158`):

```python
    code = _map_processing_error_to_code(error)
    try:
        return _FAILURE_MESSAGE_BY_CODE[ErrorCode(code)]
    except ValueError:
        return _DEFAULT_FAILURE_MESSAGE
```

`ErrorCode.PROCESSING_FAILED` maps to the literal `"Processing failed"` at
`src/mkobi/workers/data_worker.py:147`. Nothing else carries
the detail: `GET /upload/status/{task_id}` returns `ProcessingStatusResponse`, whose `message` is
`log.message` and which has no field for a detail
(`src/mkobi/models/data.py:148`–`:157`), and `ProcessingResult` returns
`"Processing completed successfully"` only on success. The code's own documentation asserts the opposite
twice — `src/mkobi/workers/data_worker.py:1236`: *"reports the skipped graphs to the client"*, and
`_empty_selection_detail`'s docstring (`src/mkobi/workers/data_worker.py:1094`): *"so a client reading the
failed run knows which charts lost their input"*.

**Evidence** — `AppException.detail` is set at `:1252` and read by no code between the raise and the
row write; both handlers call `_durable_failure_message(e)` and never `str(e)` or `e.detail`. The
durable message table at `src/mkobi/workers/data_worker.py:141`–`:155` has one fixed sentence per code
and `PROCESSING_FAILED` is `"Processing failed"` (`:147`). `docs/03-processing/processing-api.md:200`
documents the detail as bounded for the 1000-character column, which implies it is meant to be stored;
it is not.

**Consequence** — A schema mismatch that affects one chart of a ten-chart dashboard is reported
identically to a totally broken pipeline: `error_code: processing_failed`, `message: "Processing
failed"`. The operator cannot tell which charts lost their input without reading the worker log, which per
already-reported `TOPO-102` the `rq-worker` container does not emit, and without re-uploading the file —
the input is unlinked at the terminal transition
(`docs/03-processing/file-cleanup.md:26`, `:28`), so there is no second attempt from disk. The whole
point of the D-05-N guard — naming the skipped graphs so the failure is actionable — is lost at the last
step. Not graded HIGH because nothing wrong is stored and the failure itself is not misreported: the run
does fail, and `TOPO-102` already carries the observability half.

**Recommendation** — Write the detail where a reader can reach it. The narrowest fix is a dedicated
terminal message for the empty-selection case: `_FAILURE_MESSAGE_BY_CODE` gains a distinct code (a new
`ErrorCode` member, or reuse of an existing one whose message is already graph-specific) so that
`_durable_failure_message` returns the graph names for this class alone, which also keeps the "never
reproduce the exception text" property at `src/mkobi/workers/data_worker.py:161` intact because the
detail is composed from graph names, not from a driver message. `AppException` already carries `details`
for this kind of structured payload, so the alternative is to add that field to `ProcessingStatusResponse`
and return it from `DataService.get_processing_status`. Either way, correct the two docstrings at
`src/mkobi/workers/data_worker.py:945` and `:1236` in the same change, since they currently promise a
behaviour that does not exist.

### DP-105 — A dashboard with no charts completes the run and stores nothing: the zero-graph early return sits above the guard that exists to prevent exactly that

**Severity** — MEDIUM

**Zone** — "5. Replacement semantics: what an overwrite and an append each remove, and what neither removes"

**Observation** — `_store_aggregates` returns on an empty chart set at `src/mkobi/workers/data_worker.py:1191`:

```python
    graph_reads = [_to_graph_read(g) for g in result.scalars().all()]

    if not graph_reads:
        logger.warning("No graphs found for dashboard: %s", dashboard_id)
        return
```

The empty-selection guard that D-05-N added sits 48 lines further down (`:1242`), so the zero-graph shape
never reaches it. `_run_with_transaction` treats `_store_aggregates`' `None` as success and proceeds to
the terminal write at `src/mkobi/workers/data_worker.py:890`:

```python
        completion_message = (
            f"Processing completed successfully: {result_data['rows']} rows processed"
        )
```

and to `ProcessingStatus.COMPLETED` (`:898`). The guard's own comment describes this outcome as the
thing it exists to prevent (`src/mkobi/workers/data_worker.py:1232`):

```python
    # The filter-value clear is what makes an otherwise-harmless overwrite
    # destructive: the previous aggregate rows are kept by save_aggregates'
    # early return while clear_dashboard_values wipes the filter list, and the
    # run then writes COMPLETED. Failing here keeps the previous rows AND the
    # previous filter values, and reports the skipped graphs to the client
```

**Evidence** — Control flow, read in order at the cited lines: the `return` at `:1193` precedes the
`aggregates` construction (`:1219`), `save_aggregates` (`:1257`) and `clear_dashboard_values` (`:1276`),
all three of which are therefore skipped; the caller at `:878` ignores the return and reaches
`ProcessingStatus.COMPLETED` at `:898`. No shipped test asserts either behaviour: the zero-graph path is
not exercised in `tests/test_data_worker.py`, and `tests/test_processing_config_boundary.py::test_t1`
always seeds one graph.

**Consequence** — Uploading a valid file to a dashboard with no charts returns `201`, the run is reported
`COMPLETED` with `"Processing completed successfully: N rows processed"`, and no aggregate row and no
filter value is written or replaced. An operator who configures a dashboard, uploads data, and then adds
charts sees a green run for a dashboard whose data was never computed, with nothing in the history that
distinguishes it from a successful aggregation. The claim is *not* that stale rows survive — with zero
graphs `aggregated_data` rows cascade-delete with their graph
(`ondelete="CASCADE"` at `src/mkobi/db/models/aggregated_data.py:79`) — so nothing wrong is stored, which
is why this is MEDIUM rather than the HIGH band's "reports success while leaving the state it claims to
have replaced".

**Recommendation** — Fold the zero-graph case into the existing guard instead of returning around it: the
zero-chart dashboard *is* the degenerate instance of "a graph is skipped because no dimension or metric
column matched", so `skipped_graph_names` being empty because `graph_reads` is empty should raise the same
`AppException`. The smallest change is to drop the `return` at `:1193` and let `skipped_graph_names` be
`[]` only when the chart set was non-empty — i.e. guard on `graph_reads` being empty explicitly at the
same site and raise the same code, so both shapes fail with one classification. If a graph-less dashboard
is meant to be a no-op rather than a failure, say so in `docs/03-processing/processing-api.md` and have
the run write a message that says the file was stored for later use rather than reporting a row count it
never produced.

### DP-106 — One run reports three different "rows processed" figures across three surfaces, and none of them is the number of rows it stored

**Severity** — MEDIUM

**Zone** — "5. Replacement semantics: what an overwrite and an append each remove, and what neither removes"

**Observation** — The completion sentence a client renders is built from the post-transform frame's row
count (`src/mkobi/workers/data_worker.py:871`):

```python
        result_data = {
            "rows": df.shape[0],
            "columns": df.columns,
            "preview": df.head(10).to_dicts(),
        }
```

```python
        completion_message = (
            f"Processing completed successfully: {result_data['rows']} rows processed"
        )
```

That value is the frame after `filters`, `groupby`, `aggregations`, `sort_by` and `limit`
(`:798`–`:868`) — the *input* to per-chart aggregation, computed at `:871` **before** `_store_aggregates`
is even called (`:878`). The number of rows actually stored is `len(records)` from
`save_aggregates`, which reaches only the log (`:1263`):

```python
    logger.info(
        "Aggregates stored: dashboard_id=%s, records=%d, mode=%s, processed=%d",
        dashboard_id,
        len(records),
        mode,
        processed,
    )
```

The third figure is what the result endpoint reports
(`src/mkobi/services/data_service.py::get_processing_result`, `:403`):

```python
        graphs = await self.graph_repo.get_by_dashboard_id(log.dashboard_id, db)
        rows_processed = 0
        if graphs:
            agg_data = await self.agg_repo.get_by_graph_id(graphs[0].id, db)
            rows_processed = len(agg_data) if agg_data else 0
```

— the stored row count of whichever chart the unordered `get_by_dashboard_id` happens to return first,
with no regard for the dashboard's chart count, the write mode, or any filter. There is no fourth
distinct count, but there are three surfaces and three numbers, and the endpoint's own documentation
declares its field as a processing result (`docs/03-processing/processing-api.md:315` shows
`"rows_processed": 15000` with no definition).

**Evidence** — Read in execution order at the cited lines: `:871` samples the frame, `:878` stores,
`:890` formats the earlier sample, `:1263` logs the stored count, `src/mkobi/services/data_service.py:406`
re-reads one chart's rows. No test ties the two together: `tests/test_data_worker.py` asserts
`log.status == ProcessingStatus.COMPLETED`, not the number in the message, and no test asserts the
`ProcessingResult.rows_processed` value against the stored row count.

**Consequence** — On a ten-chart dashboard the completion message reports a number that is neither the
file's row count, nor the stored aggregate count, nor any chart's count — under a configured `groupby` or
`limit` it diverges from the file by orders of magnitude — while `GET /upload/result/{task_id}` reports a
different number again, being one chart's rows. An operator comparing the message against the file, or the
result endpoint against the message, cannot reconcile them, and a dashboard whose charts were deleted
between the run and the query reports `rows_processed: 0` on a `COMPLETED` run. The number a client
displays is the only thing an operator has to judge whether an upload did what they expected, and it does
not describe what was stored.

**Recommendation** — Pick one figure, make it the stored row count, and reuse it for all three surfaces:
`save_aggregates` already returns it as `processed`, so thread that value into `completion_message` instead
of `result_data['rows']`, and persist it where `DataService.get_processing_result` can read it rather than
re-deriving it by re-reading one arbitrary chart. Keeping `result_data['rows']` is still correct as the
frame's own size — it belongs in `ProcessingResult.data.rows`, the field that exists for it — but it should
not be the number in the run's headline sentence. State which figure is which in
`docs/03-processing/processing-api.md` next to the `rows_processed` example.

### DP-107 — The formula grammar admits every well-formed identifier, so an expression naming no column of the loaded data fails the run in a different process

**Severity** — MEDIUM

**Zone** — "7. Caller-supplied expressions: what a stored formula may name and what it may compute"

**Observation** — Two grammars reach a stored `computed_fields` / `custom_metrics` entry. The dispatcher
is `src/mkobi/data/processing/filter_transforms.py:102`:

```python
            if expr_str.strip().startswith("pl.col("):
                expr = _parse_polars_dt_expr(expr_str)
            else:
                # Parse simple arithmetic formulas
                expr = _parse_formula(expr_str)
            result = result.with_columns(expr.alias(name))
```

`_validate_formula_tokens` accepts any operand matching a bare identifier regex
(`src/mkobi/data/processing/formula_parser.py:176`):

```python
    _VALID_COLUMN_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    _OPERATORS = {"+", "-", "*", "/"}
```

and every non-literal operand is compiled to a column reference with no existence check
(`src/mkobi/data/processing/formula_parser.py:133`):

```python
    def _token_to_expr(token: str) -> pl.Expr:
        """Convert token to appropriate Polars expression."""
        if _is_numeric_literal(token):
            return pl.lit(float(token))
        return pl.col(token)
```

The narrower date-parts grammar is stricter — `_parse_polars_dt_expr` allowlists ten `dt` methods
(`src/mkobi/data/processing/formula_parser.py:15`–`:27`) — but likewise resolves its column by name alone.
Neither grammar is checked against the loaded frame when the configuration is stored:
`ProcessingConfigService._validate_settings` (`src/mkobi/services/processing_config_service.py:79`)
performs only a non-`None` type check and a non-empty check, because the shape is already enforced by
`ProcessingSettingsModel` (`src/mkobi/models/types.py:398`, `extra="forbid"`). A request naming a column
the file does not contain is therefore accepted with `200` and first fails in the RQ job, where
`_add_computed_fields` re-raises (`src/mkobi/data/processing/filter_transforms.py:109`).

**Evidence** — The literal-path caveat in the same family is already recorded in the code's own
documentation: `src/mkobi/data/processing/formula_parser.py:120` returns `pl.lit(float(token))` for a
numeric-only formula, and `_parse_polars_dt_expr` documents at `:206`–`:208` that the operator-supplied
format string is the only argument accepted. The dispatcher's `startswith("pl.col(")` test is exact-match,
so `pl .col('x')` or an expression beginning `pl.col('x')+pl.col('y')` falls to `_parse_formula`, splits on
`[+\-*/]`, and reaches `_validate_formula_tokens` as a bare operand list.

**Consequence** — A typo in a metric name, a rename applied to the CSV but not to the expression, or a
column dropped from one file in a recurring export produces a configuration that saves cleanly and fails
every subsequent run with `processing_failed` / `"Processing failed"` — after the upload was admitted, the
file stored and the job queued, and with the Polars `ColumnNotFoundError` text discarded by
`_durable_failure_message`. Because the expression is applied *after* the frame's namespace is settled by
casts and renames, the operator cannot tell from the failure which side is wrong, and the input is
unlinked at the terminal transition so it cannot be retried from disk. The block's stated finding
condition holds exactly: the grammar admits an identifier the loaded data does not hold.

**Recommendation** — The grammar cannot be validated at the storage boundary — the file has not been seen
yet — so the check belongs where the frame and the expression meet: resolve each identifier in
`_add_computed_fields` against `df.columns` and raise a message naming the offending identifier and the
columns that *are* present, instead of letting `pl.col` raise. That converts an opaque
`processing_failed` into an actionable one at no structural cost. Separately, make the dispatcher's
membership test tolerant (`expr_str.strip().startswith("pl.col")`) so a spacing variant does not silently
change grammar, and add the resolved-identifier error to `_map_processing_error_to_code`'s
`VALIDATION_ERROR` arm so the classification says what happened. Note in
`docs/03-processing/processing-api.md`'s Custom Metrics limitations that identifiers are resolved against
the post-rename, post-cast frame.

### DP-108 — The all-charts read has no pinned chart order and hands out a shared row budget in that order, so the same request can serve different charts

**Severity** — MEDIUM

**Zone** — "4. Determinism of the aggregate: what makes identical input produce a different stored row"

**Observation** — With no `graph_id` the route iterates the dashboard's charts and spends one shared
budget across them (`src/mkobi/api/routes/data.py:242`):

```python
        graphs = await graph_repo.get_by_dashboard_id(dashboard_id, db)
        graph_responses: list[GraphDataResponse] = []
        remaining_budget = caps.max_rows_total
        any_truncated = False

        for graph_item in graphs:
            records, total_rows, metric_keys, dimension_keys = (
                await data_service.get_bounded_aggregated_data(
                    dashboard_id=dashboard_id,
                    graph_id=graph_item.id,
                    db=db,
                    max_rows=min(caps.max_rows_per_graph, remaining_budget),
                    filters=parsed_filters,
                )
            )
            data_points = _flatten_points(records)
            returned_rows = len(data_points)
            remaining_budget -= returned_rows
```

The chart list carries no ordering (`src/mkobi/db/repositories/graph_repo.py:69`):

```python
            query = select(graph_model.Graph).where(
                graph_model.Graph.dashboard_id == dashboard_id
            )
            if limit is not None:
                query = query.offset(skip).limit(limit)
```

Individual aggregate rows *are* pinned — `AggregatedDataRepository.get_by_graph_id_limited` orders by
`AggregatedData.id` (`src/mkobi/db/repositories/aggregated_data_repo.py:53`) — and that is what makes
OVERWRITE reads deterministic; the chart order above them is not. With `max_rows_total` at 20 000 and
`max_rows_per_graph` at 2 000 (`src/mkobi/config.py:615`, `:617`), a dashboard of eleven or more charts
can exhaust the budget, after which `max_rows=min(..., 0)` yields `LIMIT 0` for every remaining chart and
they are reported with `data: []` and `rows_truncated: true`.

**Evidence** — Static: no `order_by` in `GraphRepository.get_by_dashboard_id`
(`src/mkobi/db/repositories/graph_repo.py:68`–`:75`); the budget arithmetic at
`src/mkobi/api/routes/data.py:244`–`:259` is order-dependent by construction. The single-chart path
(returns at `src/mkobi/api/routes/data.py:221`) has no such interaction. Not executed: reproducing a different plan order requires a
live plan change, so the claim here is the absence of a guarantee, not an observed divergence.

**Consequence** — Two identical requests against an unchanged database can return different charts'
rows and a different `truncated` flag, because which charts fit inside the budget is a function of a
row order PostgreSQL does not promise. A dashboard whose charts were never all intended to fit in one
response will show some charts populated and some empty, and which ones is not stable across requests,
cache layers or replicas. `aggregated_data` holds the true total per chart (`GraphDataResponse.total_rows`
comes from `COUNT(*)`), so the data is not wrong — the served page is not reproducible.

**Recommendation** — `order_by` the chart query by `Graph.id` in
`GraphRepository.get_by_dashboard_id`; it is the same stable key the row query already uses, and it makes
budget exhaustion deterministic and testable. Note the dependency: `DataService.get_processing_result`
also reads `graphs[0]` from this method (`src/mkobi/services/data_service.py:406`), so the ordering fix
simultaneously makes that figure deterministic — it does not by itself resolve DP-106, which is about the
figure being the *wrong* count rather than an unstable one. The mode in which the budget is spent
(first-N-charts rather than a fair share) is a separate policy question and is out of scope here.

### DP-109 — An append upload rebuilds the dashboard's filter list from every stored aggregate row, unbounded, inside the transaction that holds the dashboard's exclusion

**Severity** — MEDIUM

**Zone** — "5. Replacement semantics: what an overwrite and an append each remove, and what neither removes"

**Observation** — The secondary list is the filter-value list, and the two modes read different sources
(`src/mkobi/workers/data_worker.py:1281`):

```python
        if mode == UploadMode.APPEND:
            combined_records = await manager.get_aggregates(dashboard_id)
        else:
            combined_records = records
```

The APPEND source is `StorageManager.get_aggregates`, which has no row bound
(`src/mkobi/data/storage/manager.py:336`):

```python
    async def get_aggregates(
        self,
        dashboard_id: UUID,
        graph_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve aggregated data."""
        query = select(
            AggregatedData.id,
            AggregatedData.graph_id,
            AggregatedData.dims,
            AggregatedData.metrics,
        ).where(
            AggregatedData.dashboard_id == dashboard_id,
        )
```

Every row's full `dims` document is materialised into Python, then `extract_filter_values` builds a set per
filter name over them. This runs inside the main transaction that holds the dashboard's rebuild exclusion
(`acquire_dashboard_rebuild_lock`, `src/mkobi/workers/data_worker.py:1021`), and it runs *after*
`save_aggregates` has already written and set-based-inserted the new rows (`:1257`). The read path, by
contrast, is bounded by configuration — `max_rows_per_graph` / `max_rows_total`
(`src/mkobi/config.py:615`, `:617`) — and the worker's own rebuild has no equivalent bound.

**Evidence** — Read in order at the cited lines: the lock is taken at `:1021` inside
`async with session.begin()` (`:1013`); `save_aggregates` at `:1257`; the APPEND branch at `:1281`; the
query it calls at `src/mkobi/data/storage/manager.py:342`–`:349` with no `limit`/`offset`. No test grows
a dashboard's stored row count between appends, so the growth shape is untested.

**Consequence** — Each append upload's cost and peak memory scale with everything the dashboard has ever
accumulated rather than with the file being uploaded, and the cost is paid while the dashboard is
exclusively locked, so the next upload for the same dashboard queues behind it and then fails with
`processing_in_progress` if it outlasts `lock_timeout`. A dashboard fed by many small appends therefore
gets progressively slower uploads until one times out, with the refusal naming a lock rather than the
row count. Bounded by the dashboard's lifetime total rather than by the input — an operability gap, not a
correctness one: the values written are right.

**Recommendation** — Bound the read the way the read path is bounded. Either extract the distinct dimension
values in SQL (`SELECT DISTINCT dims ->> key`) rather than materialising whole rows, or cap the rebuild's
input and say so in the run's message when it is capped, so a capped list is distinguishable from a
complete one as `total_rows` already is for the response. The first is preferable and also removes the
per-row JSONB parse. Whichever is chosen, note in `docs/03-processing/processing-api.md` step 8 which
source each mode reads, so the two-mode asymmetry is documented rather than inferred from the code.

### DP-110 — `AggregatedDataRepository.bulk_insert` is a second aggregate write surface that skips the canonicalisation its sibling enforces

**Severity** — LOW

**Zone** — "5. Replacement semantics: what an overwrite and an append each remove, and what neither removes"

**Observation** — `StorageManager` states the invariant that makes aggregate identity work
(`src/mkobi/data/storage/manager.py:66`): *"Row identity on `aggregated_data` is the unique index
`uq_aggregated_data_dashboard_graph_dims` on `(dashboard_id, graph_id, dims::text)`, and every write
surface names the"*. The repository layer declares and implements a second such surface —
`IAggregatedDataRepository.bulk_insert` (`src/mkobi/interfaces/repository_interfaces.py:193`,
implemented at `src/mkobi/db/repositories/aggregated_data_repo.py:93`) — whose insert path passes `dims`
through untouched (`src/mkobi/db/repositories/aggregated_data_repo.py:132`):

```python
            insert_data = []
            for item in records:
                insert_data.append({
                    "dashboard_id": dashboard_id,
                    "graph_id": item["graph_id"],
                    "dims": item["dims"],
                    "metrics": item["metrics"],
                })

            await db.execute(
                insert(aggregated_data_model.AggregatedData),
                insert_data,
            )
```

There is no `_canonicalize_dims` on that path, no `ON CONFLICT` clause, and no transaction management
despite the class docstring's claim that *"All operations are performed within a separate database session
with automatic transaction management"* (`:89`). The production worker reaches none of it: every write
goes through `StorageManager.save_aggregates` → `_bulk_insert` / `_bulk_upsert` →
`_write_set_based` (`src/mkobi/data/storage/manager.py:414`, `:428`).

**Evidence** — Repository-wide grep for `bulk_insert` across `src/` returns only the interface declaration
(`src/mkobi/interfaces/repository_interfaces.py:193`), the implementation
(`src/mkobi/db/repositories/aggregated_data_repo.py:93`), `StorageManager`'s own differently-named private
`_bulk_insert` (`src/mkobi/data/storage/manager.py:414`), and prose in `.ai/plans/` and
`tests/test_storage_manager.py`. No route, service or worker calls it.

**Consequence** — No runtime consequence today: the method is unreachable from any production path, so
nothing un-canonicalised is stored. The cost is maintenance and the risk of a later wiring. The next
caller that reaches for the repository's `bulk_insert` — the name that suggests the obvious thing — stores
raw `dims` and either violates the unique index on a mixed-type dimension or splits one category into two
rows, the exact divergence `src/mkobi/data/storage/manager.py:70`–`:72` was written to describe. The
docstring's "every write surface" claim is false of the repository's surface as it stands.

**Recommendation** — Investigate before deleting: the interface declaration and the implementation may be
intended for the phase that owns repository-level writes. If that intent is gone, remove both, and the
"every write surface" clause at `src/mkobi/data/storage/manager.py:66`–`:69` becomes true rather than
aspirational. If it is not gone, the narrowest safe change is to have `bulk_insert` delegate to
`StorageManager`'s set-based writer, or to apply `_canonicalize_dims` to each record's `dims` and add an
`ON CONFLICT` clause, so a future caller cannot bypass the rule by accident. Either way the docstring at
`:89` should stop promising transaction management the method does not perform.

### DP-111 — `processing-api.md` still states that the input is removed *before* the terminal transition, which is the reverse of the code and of its sibling document

**Severity** — LOW

**Zone** — "10. Cleanup and recovery: what reclaims an abandoned accepted input, in which process, on which clock, and what it cannot reach"

**Observation** — `docs/03-processing/processing-api.md:244`:

```markdown
A `completed` or `failed` row is also the **end of the file's life**: the input was
removed before the transition was written, so a terminal status and an absent artefact
are the same fact. A run that was **hard-killed** mid-job is the exception — it reaches
no terminal state and no removal, so its file survives until the age-based sweep. See
[Temp File Cleanup](file-cleanup.md#the-terminal-state-rule).
```

The success path removes the input **after** the commit that writes the terminal row
(`src/mkobi/workers/data_worker.py:1035`):

```python
            if file_path.exists():
                await asyncio.to_thread(file_path.unlink)
                logger.info("Temp file deleted: %s", file_path)
            return result
```

which is the corrected shape D-05-B / DP-016 landed. The sibling document
`docs/03-processing/file-cleanup.md:58`–`:70` states it correctly under its own heading *"The
success-path unlink is *after* the commit"* and spells out the reason (a rollback must not destroy the
only copy the aggregates were derived from). The failure path does unlink inside the transaction body
(`src/mkobi/workers/data_worker.py:960`), so the two paths genuinely differ and the claim is only half
wrong — but the half that is wrong is the safety-critical half.

**Evidence** — Read in order: the `async with session.begin()` block at
`src/mkobi/workers/data_worker.py:1013` exits (committing) before the unlink at `:1035`; the failure-path
unlink at `:960` is inside the block. Both documents were read at the cited lines.

**Consequence** — No runtime consequence — the code is correct and `file-cleanup.md` is correct. The cost is
that the page a developer reads first for upload lifecycle states the opposite of the invariant the
terminal-state rule now rests on: that a `completed` row implies the artefact is already gone. Under the
real order there is a window — a process killed between the commit and the unlink — in which a
`completed` row and a present file coexist, which is exactly the window
`docs/03-processing/file-cleanup.md:70` describes and which this page declares impossible. Anyone writing a
reconciliation check from this page would write the wrong one.

**Recommendation** — Rewrite lines 244-248 to match `file-cleanup.md:58`–`:70`: removal follows the commit
on the success path and precedes the terminal write only on the failure path, and a `completed` row with a
present file is an expected intermediate state reclaimed by the age sweep, not a contradiction. Because the
block's scope explicitly owns "the window in which a completed status row outlives the file it names", the
window belongs in this page too, not only in the cleanup page it links to.

## Distribution

The findings fall on four components, and one carries most of the weight: **the async worker's settings
contract and its terminal reporting** (DP-101, DP-104, DP-105, DP-106) — four of eleven, spanning the
single most consequential and three diagnosability defects. **The write boundary and the identity it
defines** (DP-102, DP-103, DP-110) is next, and it holds the only CRITICAL. **The Polars derivation layer**
(DP-107) and **the served read path** (DP-108, DP-109) contribute one and two. By phase, the declared
pipeline's mid-section — parse, transform, aggregate, persist — carries nine of eleven; the admission and
cleanup ends carry one each (DP-111, and nothing else: see the coverage record). By severity the spread is
one CRITICAL, two HIGH, six MEDIUM, two LOW, and no finding is a duplicate of an
already-validated one.

- Worker settings contract and terminal reporting — `workers/data_worker.py`, `services/data_service.py` (4)
- Write boundary and aggregate identity — `data/storage/manager.py`, `db/models/aggregated_data.py`, `db/repositories/aggregated_data_repo.py` (3)
- Polars derivation layer — `data/processing/formula_parser.py`, `data/processing/filter_transforms.py`, `data/loaders/validator.py` (1)
- Served read path and its ordering — `api/routes/data.py`, `db/repositories/graph_repo.py` (2)
- Documentation drift — `docs/03-processing/processing-api.md` (1)

## Cross-Finding Analysis

Four findings share one cause: **the value the pipeline derives is not validated or fixed at the point it is
produced, and is instead discovered to be unusable at the point it is consumed.** `dict(model)` puts a
nullable `None` into the worker's settings mapping and the consumer refuses it (DP-101); Polars produces a
non-finite metric and the JSONB driver refuses it (DP-102); `_coerce_dim_value` plus
`_canonicalize_dim_scalar` produce two values with one identity and the unique index refuses the second
(DP-103); a formula names an identifier the frame does not hold and Polars refuses it at
`with_columns` (DP-107). In each case the refusal lands in the RQ job as `processing_failed` /
`"Processing failed"`, because `_durable_failure_message` (`src/mkobi/workers/data_worker.py:158`) is
what converts every one of them into the same opaque sentence — DP-104 is the reporting half of the same
cause, not an independent one. DP-105 and DP-111 are independent: one is a guard bypassed by an earlier
return, the other a document that contradicts its own sibling. DP-108 and DP-109 are also independent of
each other and of the group above, and of each other — one is about which charts are served, the other
about what the append path must read to rebuild a list.

## Roadmap

Ordered by cause, since the causes differ.

1. **Stop the total upload failure first (DP-101).** One-line coercion at
   `src/mkobi/workers/data_worker.py:777`, plus the worker test that drives
   `dict(ProcessingSettingsModel.model_validate({...}))`. Nothing else in this list matters while every
   configured dashboard fails.
2. **Make the aggregate identity injective (DP-103).** The decision between a real JSON `null` and a
   prefixed sentinel must be taken and documented *before* code changes, because it determines whether the
   read path's `->>` comparison changes. Add the both-an-empty-field-and-a-quoted-`""` regression test
   first so the current failure is pinned. Re-run every append and overwrite test afterwards, because the
   stored `dims` shape changes for any dashboard that holds a null or empty-string dimension.
3. **Refuse rather than crash (DP-102, DP-107).** Both land in the derivation layer's own contract: a
   finiteness check in `DataValidator` and identifier resolution in `_add_computed_fields`, with the two new
   failures classified as `VALIDATION_ERROR` so they stop sharing the opaque class. Independent of step 2
   and can run in parallel with it.
4. **Restore diagnosability (DP-104, DP-105, DP-106).** One terminal message per failure class so the
   empty-selection detail survives; one guard covering the zero-graph shape so it fails instead of
   reporting a row count it never produced; one figure — the stored row count — across the completion
   sentence and `ProcessingResult`. Step 4's message change is a client-visible behaviour change, so
   sequence it after 1-3 and re-check `docs/03-processing/processing-api.md:200` and `:315`, which both
   describe the current wording.
5. **Bound and pin the read side (DP-108, DP-109).** `order_by` on the chart query is trivial and makes
   both DP-108 and the `graphs[0]` half of DP-106 deterministic; the APPEND filter rebuild's source is a
   design decision (SQL-side `DISTINCT` versus a bounded read) and can follow once step 4 has fixed what
   the run's message claims.
6. **Close the documentation and the dormant surface (DP-110, DP-111).** Independent of everything above;
   DP-111's rewrite should land with whichever step last touches
   `docs/03-processing/processing-api.md`, and DP-110 needs the phase-ownership answer before it can be
   scheduled at all.

## Rollout Safety

Steps 1, 3 and 4 change observable behaviour on the upload path. Step 1 is strictly an improvement — a
run that could only fail now completes — so the only exposure is that dashboards previously failing with
`processing_failed` will now proceed and *reach* the next defect, which makes step 2 or 3 look like a
regression if they are not deployed together; ship step 1 with step 3, and treat any new failure class
appearing after step 1 as DP-102 or DP-107 finally surfacing. Step 2 is the risky one: it changes the
stored `dims` shape for dashboards holding null or empty-string dimensions, and the read path compares
`dims[key].astext == str(value)` against the filter-value list, so a half-applied step 2 (new writer, old
reader) silently returns no rows for those dimensions. If the prefixed-sentinel option is chosen over a real
JSON `null`, the writer and the reader must move in the same release and existing rows need a backfill —
decide that before coding, not during. Step 4's message changes break any client or operator tooling that
parses `"Processing completed successfully: N rows processed"` as a fixed string; grep the frontend for that
prefix before shipping. Revert is clean for steps 1, 3 and 4 (single-file, no schema change); step 2
requires a backfill plan for `aggregated_data.dims` before any revert, which is the strongest argument for
deciding the null representation explicitly in step 2 rather than empirically.

## Appendices

### Coverage record

Every audit block in the phase file, with what was examined and what evidence class it produced.

| Block | Examined | Evidence | Outcome |
| --- | --- | --- | --- |
| 1. Ingestion admission | `api/routes/upload.py` (streaming write, byte budget, MIME, rate limit), `services/file_processing.py::validate_file`, `data/loaders/loader.py::_validate_file_size`, `config.py:577`–`:617` | Static proof that the decompressed-size budget is enforced through `gzip.open`; runtime confirmation that the dev stack serves the declared route | **No findings.** Admission limits are declared once each, enforced in the request process, and re-checked in the worker; no limit is declared in one process and consulted in another, and nothing under `src/` or `tests/` admits an unpinned size. The `has_header` key the loader reads is never set by the worker, so it is always the Polars default — recorded as a limit on this report rather than a finding, because no declared contract names it. |
| 2. State of an accepted upload | `workers/data_worker.py` (both paths), `services/file_processing.py`, the three reconciler sweeps, `rq_worker_wrapper.py`, `core/task_queue.py` | State inventory derived from committed writes: `STARTED`/`UPLOADED` from the route, `PROCESSING`/`COMPLETED`/`FAILED` from the worker, `FAILED` from two sweeps. Every `ProcessingStatus` member is reachable from a committed row | **No findings.** The reconciler's age-cutoff behaviour is `TOPO-103` (MEDIUM, confirmed, phase 01) and is **not** re-filed; `docs/03-processing/file-cleanup.md:235` already records it as an accepted limit. The separate defect found in the same file is DP-104 (the terminal message discards the detail), which is a different predicate — the writer, not the sweep. |
| 3. Unit of atomicity | `services/file_processing.py::process_upload_with_session`, `workers/data_worker.py:984`–`:1085`, `core/task_queue.py`, `rq_worker_wrapper.py` | Effect inventory: row commit (shared with nothing), file move and enqueue (compensated — the enqueue handler unlinks the moved file at `rq_worker_wrapper.py:225`), aggregates and filter values plus the terminal row (one commit at `:1013`), file unlink (compensated on failure, ordered after the commit on success) | **No findings.** Every compensating step is named and executed; the commit ordering is asserted by the module's own comment at `:1000`–`:1005` and holds. Transaction and lock semantics are phase 03's; this block produced no finding of its own. |
| 4. Determinism of the aggregate | `db/models/aggregated_data.py:49`–`:62`, `data/storage/manager.py:63`–`:96`, `services/aggregation_service.py:66`–`:72`, `db/repositories/graph_repo.py`, `api/routes/data.py:241`–`:259` | **Executed**: the production coercion + canonicalisation functions against real Polars frames; **live**: the index definition read from `pg_indexes`; **static**: the unpinned chart order | **DP-103** (CRITICAL), **DP-108** (MEDIUM) |
| 5. Replacement semantics | `workers/data_worker.py:1184`–`:1300`, `data/storage/manager.py` (all three write paths), `db/models/aggregated_data.py:71`–`:80`, `db/repositories/aggregated_data_repo.py:93`–`:160` | Static proof of the per-mode selections, plus the control-flow read at the cited lines for the zero-graph shape | **DP-105**, **DP-106**, **DP-109** (MEDIUM), **DP-110** (LOW) |
| 6. Configuration reach | `models/types.py:343`–`:398`, `models/processing_configs.py`, `services/processing_config_service.py:79`–`:99`, `workers/data_worker.py:686`–`:869`, `data/processing/transformations.py` | Field inventory over the 22 declared keys, with an honoured / skipped / late-failure verdict per key; **executed** reproduction of the `required_columns` path against the production types | **DP-101** (HIGH). Verdict summary: every key is read; `separator`, `encoding`, `column_types`, `decimal_separator`, `date_format`, `renames`, `computed_fields`, `metric_agg`, `filters`, `groupby`, `aggregations`, `sort_by`, `descending`, `limit`, `yoy_config`, `share_config`, `custom_metrics` are honoured; `required_columns` fails the run late (**DP-101**); `metrics` is read by nothing in `src/`; `loader`, `date_column`, `timezone` are read by nothing and are declared as such at `src/mkobi/models/types.py:359`. Nothing rejects an expression's identifiers at this boundary (**DP-107**). |
| 7. Caller-supplied expressions | `data/processing/formula_parser.py` (both grammars, full read), `data/processing/filter_transforms.py:75`–`:112`, `data/processing/aggregate_transforms.py`, `workers/data_worker.py:796`–`:801`, `:851`–`:858` | Grammar inventory: arithmetic over `[a-zA-Z_][a-zA-Z0-9_]*` operands and numeric literals, or a `pl.col('x').dt.<allowlisted>()` form; limits enforced at compile time only, and the date-parts grammar's allowlist read at `formula_parser.py:15`–`:27`. `_parse_polars_dt_expr`'s regex anchors the whole expression, so no additional value source is reachable — the module contains no `eval` | **DP-107** (MEDIUM). The "identifier resolves differently depending on when it is compiled" half of the block is **not** filed: `_add_computed_fields` is a single implementation (re-exported at `aggregate_transforms.py:73`), both call sites resolve against the same post-transform frame, and no shipped test pins a divergent resolution. |
| 8. Failure classification | `workers/data_worker.py:56`–`:175` (the code-then-substring mapper, the fixed-sentence table), `services/file_processing.py:221`–`:238`, `api/routes/upload.py:229`–`:238`, `utils/exceptions.py:229` (`add_exception_handlers`) | Classification sites derived, not assumed: three — `_map_processing_error_to_code` (type first, then a message-substring table), the upload route's `ValueError` keyword table, and `_durable_failure_message`'s fixed-sentence table. Each signal and each reachable class recorded | **DP-104** (MEDIUM). The block's stated finding condition (two sites classifying one failure differently) is **not** filed: the tables were compared class by class and the only divergences are unreachable in practice (a `ValueError` raised on the upload path never reaches the worker's table, and vice versa). The live substring dependence on driver wording is real and is recorded as a limit on this report, because the wording that would re-route a class is upstream library text this pass cannot change. |
| 9. Validation of the loaded frame | `data/loaders/validator.py` (full read), `workers/data_worker.py:770`–`:793`, `:890`–`:897` | Check inventory with a refuse/annotate verdict: empty frame, required columns, column types, null rate, duplicate keys, empty strings — the last four annotate. Warnings reach `processing_logs.message` through `_compose_completion_message` (`:178`) and are readable on `GET /upload/status/{task_id}` | **DP-102** (HIGH). No warning annotation without a reader was found: warnings are stored on the row, returned by the status endpoint, and bounded at the column's 1000 characters with the truncation made explicit — so the block's stated condition is satisfied by the code and is recorded as a passing check rather than a finding. |
| 10. Cleanup and recovery | `services/file_cleanup.py` (full read), `workers/data_worker.py:1035`–`:1085` (all four unlink sites), `:341`–`:396` (all three periodic sweeps), `db/starter.py:590`–`:614` (the retention sweep), `app.py:128`–`:210`, `config.py:732`–`:737`, `docs/03-processing/file-cleanup.md` | Sweep inventory with a bound-kind verdict: **every** bound is a configured value and **none** is a code literal — the file sweep reads `stale_file_threshold_hours` (`config.py:735`), the two periodic row sweeps read `stale_processing_timeout_minutes` threaded from `app.py:204` (`config.py:736`), and the retention sweep reads `logs_retention_days` (`config.py:732`) and deletes on `finished_at` (`db/starter.py:595`, `:601`), scoped to terminal statuses (`:602`). All four unlink sites located; the reconciler loop is lease-guarded and fails open, verified at `app.py:175`–`:202` | **DP-111** (LOW). The block's other condition — "one status row whose named file a sweep can remove first" — is **not** filed: the row sweep's 30-minute horizon is strictly shorter than the file sweep's 24-hour horizon (`config.py:735`, `:736`), and `docs/03-processing/file-cleanup.md:232` states the ordering and its reason, so no completed row outlives its artefact in the reachable direction. The window in the other direction — a committed `completed` row with the file still present — is real, and its documentation is DP-111. |

### Method and artefacts

- Repository state at citation time: HEAD `cfab3e0`, working tree clean under `src/`. Two commits
  (`f8581e0`, `cfab3e0`) landed while this pass was in progress; **every citation was re-read and
  re-verified against the current files after that point**, which is why `settings = ...` is cited at
  `src/mkobi/workers/data_worker.py:689` and the `LoaderConfig` construction at `:776`.
- Runtime probes executed on the host with `uv run python` (project venv, Polars 1.41.2,
  SQLAlchemy 2.0.50, pydantic 2.13): the `required_columns` reproduction (DP-101); the
  null-versus-empty-string and non-finite canonicalisation probes (DP-103); the CSV non-finite literal and
  aggregate-poisoning probes (DP-102); the `json.dumps` token probe (DP-102).
- Runtime probes against the live dev PostgreSQL 18 (`mkobi-db-1`, database `bidb`): read-only `SELECT`s
  only — `SELECT indexdef FROM pg_indexes WHERE indexname='uq_aggregated_data_dashboard_graph_dims'`,
  `SELECT '{"a": NaN}'::jsonb`, `SELECT '{"a": Infinity}'::jsonb`, `SELECT '{"region":""}'::jsonb::text`.
  **No row was written to any table; no probe rows were left behind.**
- Not verified in this environment, and therefore not claimed: an end-to-end upload against the dev stack
  for DP-101 (the crash was reproduced against the production types at the values the two cited lines
  produce, and the control flow from the enqueue to the `LoaderConfig` call was read, but no job was
  dispatched); the composed `INSERT` for DP-102 (each link of the chain was executed separately, the
  insert itself was not); the unique-index violation for DP-103 in DP-103's loud forms (the index
  definition and the absence of an `ON CONFLICT` clause were verified, the statement was not run); and a
  plan-order divergence for DP-108 (the absent `ORDER BY` is verified, an observed divergence is not).
- `.ai/tasks/B2-txn-005-rebuild-exclusion.yaml` and `.ai/tasks/B3-txn-003-durable-processing-transitions.yaml`
  were searched for each candidate finding; neither tracks any of DP-101 … DP-111, so none of these is
  already-tracked work re-filed as new.
- `TOPO-103` (MEDIUM, confirmed, phase 01) — the reconciler reporting a still-queued upload as `FAILED` —
  is **not** re-filed, and `docs/03-processing/file-cleanup.md:235` already records it as an accepted
  limit. No finding in this report has an ID that duplicates an already-validated finding.
