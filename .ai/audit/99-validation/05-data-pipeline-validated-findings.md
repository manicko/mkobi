---
phase: 05-data-pipeline
validated: 2026-10-05
validator: validator
validated-findings: 11
verdicts:
  CONFIRMED: 8
  CORRECTED: 3
  REJECTED: 0
by-severity:
  CRITICAL: 1
  HIGH: 1
  MEDIUM: 7
  LOW: 2
---

# Phase 05 — Validated Findings

## Summary

All eleven findings survive validation. Eight are confirmed exactly as filed, three are confirmed with a
corrected citation or a corrected overreach. Nothing is rejected. Every citation was re-opened against the
current working tree. The auditor's account of the two mid-pass commits (`f8581e0`, `cfab3e0`) was checked
independently rather than accepted, and **HEAD advanced twice more during this validation** (to `cfab3e0` and
then `0ae6ddf`). `git diff --stat f8581e0..0ae6ddf` touches only `frontend/src/features/dashboards/ui/charts/*`
and `.ai/plans/16-phase16-residual-execution.md` — **no file cited by any finding in this phase** — so every
anchor below was re-checked against the tree as it stands at `0ae6ddf` and still resolves.

**DP-101 reproduces, and it reproduces further than the auditor claimed.** The auditor recorded that the
end-to-end upload was *not* executed for DP-101 and graded the type-level reproduction only. I executed the
real `process_csv_background` against a live PostgreSQL row and the live dev database's stored
`processing_configs` payload. The run raised
`ValidationError: 1 validation error for LoaderConfig / required_columns / Input should be a valid list`, and
the durable row it left behind read `status=failed`, `error_code=PROCESSING_FAILED`,
`message="Processing failed"` — the exact terminal state the finding predicts, with the cause absent from the
row. The trigger is not hypothetical: the dev database's own seeder-written config row (dashboard
`a5214e7a-…`) has no `required_columns`, so the shipped dev stack reproduces it on demand.

Three corrections, all in the direction of *understating* rather than inflating:

- **DP-102's severity is downgraded HIGH → MEDIUM.** The chain is real and the driver refusal is real, but
  the claim that "one non-finite cell poisons **every** aggregate function" is false, and the finding's own
  evidence for it does not show what it claims. Executed: in a group holding both `NaN` and `5.0`, Polars
  returns `min=5.0`, `max=5.0`, `last=5.0` — finite. Only `sum`, `mean`, `median`, `std`, `var`, `first`
  propagate; `count` is an integer and always finite. The consequence paragraph's claim that "there is no
  `metric_agg` an operator can switch to that avoids it" is therefore false — `count` avoids it, and `min`/`max`
  survive a `NaN` in a mixed group. Under the phase taxonomy's MEDIUM band ("an expression admitted by the
  grammar and absent from the loaded data" — the identical shape, already filed as DP-107 at MEDIUM), a
  non-finite cell admitted by the loader and absent from what JSONB accepts is MEDIUM, not HIGH.
- **DP-104's recommendation cites two docstrings, one of which does not exist.** `data_worker.py:945` is a
  comment explaining why the handler catches `BaseException`; it says nothing about client reporting. The
  two real promises are at `:1236` and `:1101`.
- **DP-105's evidence overstates its own test gap.** `tests/test_data_worker.py:1151`
  (`test_store_aggregates_no_graphs`) does exercise the zero-graph path. The finding's *point* — no test
  asserts the *outcome* — survives; the sentence "the zero-graph path is not exercised" does not.

Two phase-level claims checked and upheld, one refuted and one gap-filled:

- **The `DP-1xx` namespace choice is correct.** Verified free across `docs/`, `.ai/`, `src/`, `tests/`,
  `frontend/`, `alembic/`, `docker/`; `DP-0xx` is occupied by the earlier pass and `DP-NN` by the
  `.ai/decisions/` series. No collision.
- **`TOPO-103` and DP-104 are genuinely different defects.** Verified by predicate, not by assertion:
  `TOPO-103` is the sweep's `status == UPLOADED AND started_at < cutoff` (`data_worker.py:586-596`, no queue
  handle in scope); DP-104 is the *writer* discarding `AppException.detail` at `:977`/`:1074`. One flips a
  healthy row, the other loses a diagnostic on a row that was correctly failed.
- **The pandas no-findings entry is FALSE and is refuted.** The auditor's coverage record claims no pandas
  anywhere; `pandas-stubs==3.0.0.260204` is declared at `pyproject.toml:219` and resolved in `uv.lock`, and
  the base context lists "**No pandas** — Polars only" as a hard rule. No *runtime* pandas exists — nothing
  in `src/`, `tests/` or `frontend/src/` imports it and `pandas` is not installed. But phase 01 already filed
  exactly this as **TOPO-114** (LOW, "The declared dev toolchain includes stubs for a dependency the project
  forbids"), citing the same `pyproject.toml:219`. So it is a **cross-phase duplication and a false
  no-findings entry**, not a missed finding of this phase's own — see *Rejected Claims* below.
- **GAP FOUND — append mode violates the declared full-recompute contract, and neither phase filed it.**
  `AGENTS.md:77` requires "**полный пересчёт** агрегатов для дашборда" on every upload, and
  `docs/03-processing/processing-api.md:134-135` states it in stronger, explicitly unconditional terms:
  *"Each upload triggers a **full recalculation** … There is no incremental aggregation. The claim is
  unconditional…"*. `UploadMode.APPEND` is reachable from the production UI
  (`frontend/src/features/upload/ui/UploadModal.tsx:226-228`) and the route
  (`api/routes/upload.py:145`, `:246`), and it is not a full recomputation: `clear_old=False` selects
  `_bulk_upsert`, which keeps every prior row and merges into it
  (`data_worker.py:1259`, `manager.py:202-211`). Filed here as **VAL-05-101**.

---

## Validated findings

### DP-101 — Every upload to a dashboard with a stored processing config fails

**Verdict** — CONFIRMED (reproduced beyond the auditor's own evidence)

**Severity** — HIGH (unchanged)

**Observation** — Unchanged and independently re-derived: `dict(ProcessingSettingsModel)` yields every
declared field, `required_columns` carries `None`, the worker's `settings.get("required_columns", [])`
returns that `None` rather than the default, and `LoaderConfig` refuses it.

**Evidence** — Every citation resolves exactly at the tree as it stands (`0ae6ddf`; the cited files are
untouched by the two commits that landed after `f8581e0`):

- `src/mkobi/models/processing_configs.py:12` — `settings: ProcessingSettingsModel`.
- `src/mkobi/models/types.py:370` — `required_columns: list[str] | None = None`.
- `src/mkobi/services/data_service.py:170` — `processing_config = dict(config_response.settings) if config_response else None`;
  passed at `:186`.
- `src/mkobi/workers/data_worker.py:689` — `settings = processing_config_dict.get("settings", processing_config_dict)`.
- `src/mkobi/workers/data_worker.py:776-777` — the `LoaderConfig` construction.
- `src/mkobi/models/data.py:325` — `required_columns: list[str] = Field(default_factory=list, …)`, non-nullable.
- `src/mkobi/workers/data_worker.py:158` (definition of `_durable_failure_message`), `:1074` (production call),
  `:147` (`PROCESSING_FAILED: "Processing failed"`).

**New evidence — the auditor's own limit is closed.** The report recorded "Not verified in this environment:
an end-to-end upload against the dev stack for DP-101". I ran it.

*Type level.* `ProcessingSettingsModel.model_validate({"column_types": {...}, "metric_agg": "mean"})` →
`dict(...)` → 22 keys, `required_columns` present and `None` → `LoaderConfig` raises `ValidationError`
(`ValueError` subclass confirmed).

*Against the live dev database's own stored config.* The single `processing_configs` row in `mkobi-db-1`
(dashboard `a5214e7a-4884-4d2c-a7c9-98f27d42e0a8`) stores 8 keys, none of them `required_columns`. Running
that exact JSONB through the production read path:

```
stored keys: ['column_types', 'computed_fields', 'date_column', 'date_format',
              'decimal_separator', 'encoding', 'renames', 'separator']
dict keys after model_validate: 22
required_columns present: True value: None
LoaderConfig RAISED: ValidationError | ValueError: True
```

The shipped dev stack reproduces this without any operator action.

*End to end.* Driving `process_csv_background` with `processing_config_dict = dict(ProcessingConfigRead.settings)`
(the shape `_execute_upload` produces), against a real `processing_logs` row:

```
RAISED: ValidationError  1 validation error for LoaderConfig / required_columns
        Input should be a valid list [input_value=None, input_type=NoneType]
DURABLE status: failed | error_code: PROCESSING_FAILED | message: Processing failed
```

Both probe rows were deleted; `processing_logs` returned to its pre-probe count of 5.

**Test-gap half — CONFIRMED.** `tests/test_data_worker.py:1408` passes
`processing_config_dict={"metric_agg": "mean"}`; `tests/test_processing_config_boundary.py:185` builds a
two-key literal. Neither carries the `None` key, and no test anywhere passes a `ProcessingSettingsModel`-derived
mapping to the worker. The `_run_processing` helper at `:344-367` flattens `{"settings": settings, **settings}`,
which would have carried a real `None` had the literal come from a model — the test chose a literal.

**Consequence** — Confirmed as filed, with the blast radius confirmed as total: the feature is inoperative for
every configured dashboard, deterministically, and the cause is unreachable from the row. Dashboards with no
`processing_configs` row are unaffected — verified: `data_service.py:170` yields `None`, the worker's
`if processing_config_dict:` is falsy, and `LoaderConfig` is built with `[]`.

**Recommendation** — Upheld. `settings.get("required_columns") or []` at the read is the right fix; it closes
the whole `dict(model)` nullable-key class rather than this instance. The proposed test shape
(`dict(ProcessingSettingsModel.model_validate({...}))`) is the correct one and closes the gap this validation
reproduced through.

---

### DP-102 — A non-finite metric reaches the `ARRAY(JSONB)` bind unmodified

**Verdict** — CORRECTED (severity downgraded; one claim refuted by execution)

**Severity** — **MEDIUM** (downgraded from HIGH)

**Observation** — The chain is confirmed link by link. `_write_set_based` canonicalises `dims` and passes
`metrics` verbatim; nothing between the Polars frame and the bind refuses a non-finite float; `DataValidator`
has no finiteness check; both write modes carry the same payload.

**Evidence** — Citations resolve:

- `src/mkobi/data/storage/manager.py:487-488` — `dims = [_canonicalize_dims(agg["dims"]) …]` /
  `metrics = [agg["metrics"] for agg in chunk]`.
- `src/mkobi/data/storage/manager.py:496-497` — both `bindparam(…, type_=ARRAY(JSONB))`.
- `src/mkobi/data/storage/manager.py:499` — the `INSERT … SELECT * FROM unnest(…)` composition.
- `src/mkobi/data/storage/manager.py:88` — the "metrics are deliberately NOT canonicalised" docstring.
- `src/mkobi/data/loaders/validator.py` — full read; `validate()` is a column-name/aggregate call check only.

**New evidence — the auditor's DB probe is superseded.** The report probed `SELECT '{"a": NaN}'::jsonb` in
`psql`, which proves PostgreSQL's *parser* rejects the token but not that the *driver* emits it. I closed that
gap through the application's own SQLAlchemy asyncpg engine:

```
SQLAlchemy JSONB bind of inf -> {"ratio": Infinity}
SQLAlchemy JSONB bind of nan -> {"ratio": NaN}
OK    [{'ratio': 1.5}]                 -> ({'ratio': 1.5},)
FAIL  [{'ratio': inf}]  -> InvalidTextRepresentationError: Token "Infinity" is invalid
FAIL  [{'ratio': nan}]  -> InvalidTextRepresentationError: Token "NaN" is invalid
FAIL  [{'r': -inf}]     -> InvalidTextRepresentationError: Token "-Infinity" is invalid
OK    [{'region': '', 'revenue_sum': 3}]
```

`SELECT`s only. This closes the report's own "Not verified: the composed `INSERT` for DP-102" limitation for
the bind leg.

**CORRECTION 1 — the aggregate-poisoning claim is false as written.** The report's evidence item 2 states
*"One non-finite cell poisons **every** aggregate function, not only `sum`. Grouping `a,b` on rows `(1, NaN)`
and `(2, 5)` gives `b_sum=NaN`, `b_mean=NaN`, `b_min=NaN`, `b_max=NaN`."*

Executed against Polars 1.41.2, both groupings:

- The report's own grouping, `group_by("a","b")`, puts **each row in its own group**, so the group containing
  `NaN` contains nothing else. `min`/`max` over a single-element group are that element. This shows a lone
  non-finite value survives every function, not that one cell poisons a group.
- The mixed group — `a=1` holding both `NaN` and `5.0` — gives
  `sum=nan`, `mean=nan`, `median=nan`, `std=nan`, `var=nan`, `first=nan`, but **`min=5.0`, `max=5.0`,
  `last=5.0`** and `count=2`. With `-inf` and `5.0`: `min=-inf`, `max=5.0`.

Six of ten functions propagate; `min`, `max`, `last` and `count` do not. **CORRECTION 2 — the consequence
"there is no `metric_agg` an operator can switch to that avoids it" is therefore false.** `count` returns an
integer and is always finite, including on an all-non-finite group; `min`/`max` survive a `NaN` in a mixed
group. Both claims are struck.

**Severity reasoning** — MEDIUM, not HIGH. The taxonomy reserves HIGH for *"a silent correctness failure with
no self-healing path"* and CRITICAL for *"a stored result that is wrong now"*. This failure is neither: the run
fails loudly, nothing wrong is stored, and the previous rows survive — the same shape the taxonomy assigns
MEDIUM and which DP-107 (this phase) already grades MEDIUM for the same reason ("an expression admitted by the
grammar and absent from the loaded data"). A non-finite cell admitted by the loader and absent from what JSONB
accepts is the identical structure. The two corrections remove the finding's only argument for HIGH, which was
blast radius across the whole `metric_agg` surface. The finding is real and worth fixing; it is an operability
gap, not a correctness one.

**Recommendation** — Upheld. A finiteness check in `DataValidator.validate` raising `VALIDATION_ERROR` naming
the columns is the smallest correct change and lands in the layer whose declared job is to refuse the frame.
The report's own alternative — sanitise at the write, which "loses the value silently" — remains the wrong
one.

---

### DP-103 — The canonical form of a dimension value is not injective

**Verdict** — CONFIRMED (reproduced in all three forms against a live database)

**Severity** — CRITICAL (unchanged)

**Observation** — Unchanged and re-derived independently. Row identity is the unique index over
`(dashboard_id, graph_id, dims::text)`; identity therefore depends entirely on a two-step canonicalisation
in which both steps collapse distinct inputs onto one output.

**Evidence** — Citations resolve, and the index definition was read live:

- `src/mkobi/db/models/aggregated_data.py:55-61` — `uq_aggregated_data_dashboard_graph_dims`; `:59` is the
  `text("dims::text")` expression. (Re-verified at `0ae6ddf`.)
- Live: `CREATE UNIQUE INDEX … ON public.aggregated_data USING btree (dashboard_id, graph_id, ((dims)::text))`.
- `src/mkobi/services/aggregation_service.py:66-67` — `if value is None: return ""`; `:72` — `return str(value)`.
- `src/mkobi/data/storage/manager.py:90-91` — `if value is None: return ""`; `:96` — `return str(value)`.
- `src/mkobi/data/storage/manager.py:414` / `:428` — `_bulk_insert`, `on_conflict=False`.

**New evidence — all three failure forms executed against `mkobi-db-1`, inside rolled-back transactions.**

*Canonicalisation collapse.* Executed through both production functions:

```
float nan  value=nan   coerce=nan   canonical='nan'
text 'nan' value='nan' coerce='nan' canonical='nan'
float inf  value=inf   coerce=inf   canonical='inf'
text 'inf' value='inf' coerce='inf' canonical='inf'
None       value=None  coerce=''    canonical=''
empty str  value=''    coerce=''    canonical=''
```

The `NaN`/`"nan"` and `inf`/`"inf"` pairs the report names are confirmed. The CSV shape is confirmed too: a
column holding `South`, `""`, `North` and a null parses as String with those four values, and the four
canonicalise to **3 distinct identities of 4**.

*Loud form, OVERWRITE.* Two records with one identity through `_bulk_insert`:

```
OVERWRITE plain insert -> RAISED IntegrityError / UniqueViolationError:
    duplicate key value violates unique constraint "uq_aggregated_data_dashboard_graph_dims"
```

*Loud form, APPEND.* The same pair through `_bulk_upsert`:

```
APPEND upsert -> RAISED CardinalityViolationError: ON CONFLICT DO UPDATE command cannot affect row a second time
```

This closes the report's "Not verified: the unique-index violation for DP-103 in DP-103's loud forms" — the
index definition and the absent `ON CONFLICT` had been checked, but the statement had not been run. It now has.

*Silent form, APPEND across uploads.* This is the CRITICAL half and the one that matters. Upload A stores
`{"region": ""}` with `revenue_sum: 100` from rows whose region cell was empty; upload B, whose cells contain
a literal empty string, upserts the same identity:

```
after upload A: rows=1 [('{"category": ""}', {'revenue_sum': 100})]
after upload B: rows written A=1 B=1
stored rows:    [('{"category": ""}', {'revenue_sum': 999})]
A's 100 survives: False
residue after rollback: 0
```

One group's aggregate was silently replaced by another's, in a single stored row, with no trace of A. This is
the taxonomy's CRITICAL band verbatim — "aggregate rows that silently accumulate across successive uploads of
the same data, so two answer the same question differently."

**APPEND reachability — confirmed.** `UploadMode.APPEND` is reachable from the production UI
(`frontend/src/features/upload/ui/UploadModal.tsx:226-228`, "Append (Add new rows)") and the route
(`src/mkobi/api/routes/upload.py:145`, threaded at `:246`), and the worker's branch selects it at
`data_worker.py:1281`. This is not a test-only mode.

**Recommendation** — Upheld, with one ordering note. Option (a) (a real JSON `null`) is the honest fix, and the
read-path dependency it names is real: `src/mkobi/db/repositories/aggregated_data_repo.py:245` and `:241`
compare with `dims[key].astext == str(value)`, and `->>` on a JSON `null` yields SQL `NULL`, so every existing
filter comparison would need a null arm. That is a wider change than option (b) and the report's preference
order already says so. The regression test the report asks for is the right one, and this validation confirms
it would have caught the defect: it should assert **both** the null/empty-string pair *and* the
`NaN`/`"nan"` pair, since both are confirmed collapses.

---

### DP-104 — The empty-selection guard's diagnostic is discarded

**Verdict** — CONFIRMED (one citation in the recommendation corrected)

**Severity** — MEDIUM (unchanged)

**Observation** — Unchanged. `_store_aggregates` composes a detail naming the skipped graphs and raises it;
both production handlers then write a fixed per-class sentence instead.

**Evidence** — Citations resolve:

- `src/mkobi/workers/data_worker.py:1242-1253` — the guard; `detail = _empty_selection_detail(...)` at `:1243`,
  `detail=detail` at `:1252`.
- `:977` and `:1074` — `message=_durable_failure_message(e)`, the test and production handlers respectively.
- `:158` — `def _durable_failure_message(error: BaseException) -> str`.
- `:146-155` — the message table; `:147` — `PROCESSING_FAILED: "Processing failed"`.
- `src/mkobi/models/data.py:148-157` — `ProcessingStatusResponse`; eight fields, none carrying a detail.
- `src/mkobi/workers/data_worker.py:1101-1102` — `_empty_selection_detail`'s docstring:
  *"so a client reading the failed run knows which charts lost their input"*.
- `src/mkobi/workers/data_worker.py:1236` — *"…and reports the skipped graphs to the client"*.
- `docs/03-processing/processing-api.md:200-201` — documents the detail as bounded to fit the 1000-character
  column, which presumes it is stored.

`AppException` does carry `details` (`src/mkobi/utils/exceptions.py:88`, `:119`) and the RFC 7807 handler
returns it (`:253`), so the report's alternative is available. The status path does not surface it.

**CITATION CORRECTION.** The recommendation says *"correct the two docstrings at
`src/mkobi/workers/data_worker.py:945` and `:1236`"*. **`:945` is not a docstring and makes no promise about
client reporting.** It is a six-line comment explaining why the handler catches `BaseException` rather than
`Exception` (`asyncio.CancelledError` inherits from the former). The two genuine promises are at `:1236`
(the guard comment) and `:1101-1102` (`_empty_selection_detail`'s docstring). Corrected in place.

**Consequence** — Confirmed. The run does fail and nothing wrong is stored, so MEDIUM is correct and HIGH is
correctly declined — the finding says so itself.

**Recommendation** — Upheld. A distinct terminal message for this class is the narrowest fix and preserves the
"never reproduce the exception text" property, because the detail is composed from graph names.

---

### DP-105 — A dashboard with no charts completes the run and stores nothing

**Verdict** — CONFIRMED (one evidence sentence corrected)

**Severity** — MEDIUM (unchanged)

**Observation** — Unchanged. The zero-graph `return` sits above the empty-selection guard, so the degenerate
case is the one shape the guard never sees.

**Evidence** — Citations resolve, and the offset is exact:

- `src/mkobi/workers/data_worker.py:1191-1193` — `if not graph_reads:` / `logger.warning(…)` / `return`.
  The guard is at `:1242`, i.e. **51 lines** after the `return` (the report says "48 lines further down" —
  a harmless imprecision in prose, not a citation error; the `:1242` anchor itself is correct).
- `:1219` (`aggregates` construction), `:1257` (`save_aggregates`), `:1276` (`clear_dashboard_values`) — all
  three are after the `return` and are therefore skipped.
- `:878` — the `_store_aggregates` call, whose return value is ignored.
- `:890-892` — the completion sentence; `:898` — `_update_processing_log_status(…, status=ProcessingStatus.COMPLETED, …)`.
- `:1232-1237` — the guard comment, which describes exactly this outcome as the thing it exists to prevent.
- `src/mkobi/db/models/aggregated_data.py:79` — `ondelete="CASCADE"` on the graph FK, so with zero graphs
  `aggregated_data` rows cascade-delete with their graph. Nothing wrong is stored. Correct, and correctly
  graded MEDIUM for that reason.

**EVIDENCE CORRECTION.** The report states *"No shipped test asserts either behaviour: the zero-graph path is
not exercised in `tests/test_data_worker.py`"*. The second clause is false.
`tests/test_data_worker.py:1151-1172` (`test_store_aggregates_no_graphs`) constructs exactly this shape — a
mock session whose `scalars().all()` returns `[]` — and calls `_store_aggregates` with an empty chart set. The
path **is** exercised. What is true, and what the finding needs, is that the test asserts only
`mock_session.execute.assert_called()`: it pins that the chart query ran, and says nothing about what the run
then reports, so it locks in neither the COMPLETED status nor the absence of stored rows. The first clause of
the finding's sentence stands; the second is struck. The finding's own recommendation to assert the outcome is
the correct remedy.

The second half of the evidence claim — `tests/test_processing_config_boundary.py::test_t1` always seeds one
graph — is confirmed: `_seed_dashboard` (`:133-166`) creates a graph unconditionally.

**Consequence** — Confirmed. `201`, `COMPLETED`, `"… N rows processed"`, nothing written or replaced.

**Recommendation** — Upheld. Folding the zero-graph case into the same guard is the right shape, and the
report's alternative (state in the docs that a graph-less dashboard is a no-op, and say so in the run message)
is the correct second option.

---

### DP-106 — One run reports three different "rows processed" figures

**Verdict** — CONFIRMED

**Severity** — MEDIUM (unchanged)

**Evidence** — Citations resolve:

- `src/mkobi/workers/data_worker.py:871` — `result_data = {"rows": df.shape[0], …}`, sampled from the
  post-transform frame.
- `:890-892` — `completion_message` formats `result_data['rows']`.
- `:878` — `_store_aggregates` is called *after* `:871`.
- `:1263` — `logger.info("Aggregates stored: … records=%d …", len(records), …)` — the stored count, log-only.
- `src/mkobi/services/data_service.py:403-407` — `rows_processed = len(agg_data) if agg_data else 0`, where
  `agg_data` comes from `get_by_graph_id(graphs[0].id, db)`.
- `docs/03-processing/processing-api.md:315` — shows `"rows_processed": 15000` with no definition.

Three surfaces, three numbers, none of them the stored row count. Confirmed. `graphs[0]` picks an arbitrary
chart from an unordered query (see DP-108), so this figure is also unstable — the report correctly notes that
DP-108's ordering fix makes it deterministic but does not make it right.

**Recommendation** — Upheld. Threading `processed` from `save_aggregates` into `completion_message` and
persisting it for `get_processing_result` is correct; keeping `result_data['rows']` in
`ProcessingResult.data.rows`, the field that exists for it, is the right separation.

---

### DP-107 — The formula grammar admits every well-formed identifier

**Verdict** — CONFIRMED

**Severity** — MEDIUM (unchanged — and this is the taxonomy's own MEDIUM example)

**Evidence** — Citations resolve:

- `src/mkobi/data/processing/filter_transforms.py:102-105` — the `startswith("pl.col(")` dispatcher and the
  `_parse_formula` fallback; `:109` — the re-raise.
- `src/mkobi/data/processing/formula_parser.py:176` — `_VALID_COLUMN_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")`,
  with `_OPERATORS` at `:177`.
- `src/mkobi/data/processing/formula_parser.py:133-137` — `_token_to_expr` returning `pl.lit(float(token))` for
  a numeric literal (`:135`) and `pl.col(token)` otherwise (`:137`), with no existence check.
- `src/mkobi/data/processing/formula_parser.py:15-27` — the ten allowlisted `dt` methods.
- `src/mkobi/data/processing/formula_parser.py:206-209` — the docstring listing the accepted forms.
- `src/mkobi/services/processing_config_service.py:79` — `_validate_settings`, a non-`None` type check and a
  non-empty check; the shape is enforced only by `extra="forbid"` (`src/mkobi/models/types.py:398`).

The module contains no `eval`, and `_parse_polars_dt_expr`'s regex anchors the whole expression, so no
additional value source is reachable — confirmed by full read.

**Consequence** — Confirmed. A saved configuration that names no column of the loaded frame fails every
subsequent run, with the `ColumnNotFoundError` text discarded.

**Recommendation** — Upheld. Resolving each identifier against `df.columns` where the frame and the expression
meet is the correct and only place the check can live, since the file has not been seen at the storage
boundary. The `startswith("pl.col")` tolerance fix is right.

---

### DP-108 — The all-charts read has no pinned chart order and hands out a shared row budget

**Verdict** — CONFIRMED

**Severity** — MEDIUM (unchanged)

**Evidence** — Citations resolve:

- `src/mkobi/api/routes/data.py:242` — `graphs = await graph_repo.get_by_dashboard_id(dashboard_id, db)`.
- `:244` — `remaining_budget = caps.max_rows_total`; `:256` — `max_rows=min(caps.max_rows_per_graph, remaining_budget)`;
  `:259` — `remaining_budget -= returned_rows`. The arithmetic is order-dependent by construction.
- `src/mkobi/db/repositories/graph_repo.py:68-71` — `select(graph_model.Graph).where(dashboard_id == …)` with
  no `order_by`; the `:72-73` `offset`/`limit` is the only ordering-relevant clause and it applies only when
  `limit is not None`, which the route does not pass.
- `src/mkobi/config.py:615` — `max_rows_per_graph: int = Field(default=2000, …)`;
  `src/mkobi/config.py:617` — `max_rows_total: int = Field(default=20000, …)`.
- `src/mkobi/db/repositories/aggregated_data_repo.py:309` — `get_by_graph_id_limited` **does** order by
  `AggregatedData.id`. Individual rows are pinned; the chart order above them is not.
- `src/mkobi/api/routes/data.py:221` — the single-chart path returns before the budget loop.

The report is candid that no observed divergence was reproduced, and that is the honest framing: the absence
of a guarantee is the finding, not an observed wrong answer. Correct.

**Recommendation** — Upheld. `order_by(Graph.id)` is the right fix and it is the same stable key the row query
already uses.

---

### DP-109 — An append upload rebuilds the filter list from every stored aggregate row, unbounded

**Verdict** — CONFIRMED

**Severity** — MEDIUM (unchanged)

**Evidence** — Citations resolve:

- `src/mkobi/workers/data_worker.py:1281-1283` — `if mode == UploadMode.APPEND: combined_records = await manager.get_aggregates(dashboard_id)`.
- `src/mkobi/data/storage/manager.py:336-349` — `get_aggregates`; the `select` names four columns and the
  `where` is a single equality. **No `limit`, no `offset`.** Confirmed by full read of the function.
- `src/mkobi/workers/data_worker.py:1013` — `async with session.begin():`; `:1021` — `acquire_dashboard_rebuild_lock`;
  `:1257` — `save_aggregates` runs *before* the APPEND read at `:1281`.
- `src/mkobi/config.py:615`, `:617` — the read path's two bounds, which the worker's rebuild has no equivalent of.

The unbounded read runs while the dashboard is exclusively locked and after the new rows are written. Confirmed.

**Consequence** — Confirmed as an operability gap, and the report is right to stop short of HIGH: the values
written are correct. Cost and peak memory scale with the dashboard's lifetime total rather than with the input.

**Recommendation** — Upheld. `SELECT DISTINCT dims ->> key` in SQL is preferable and also removes the per-row
JSONB parse.

---

### DP-110 — `AggregatedDataRepository.bulk_insert` is a second aggregate write surface

**Verdict** — CONFIRMED

**Severity** — LOW (unchanged)

**Evidence** — Citations resolve, and unreachability was verified independently:

- `src/mkobi/data/storage/manager.py:66-69` — the invariant docstring, including "every write surface".
- `src/mkobi/interfaces/repository_interfaces.py:193` — `async def bulk_insert(...)` on the interface.
- `src/mkobi/db/repositories/aggregated_data_repo.py:93` — the implementation;
  `:132-145` — the loop building `insert_data` with `item["dims"]` passed through untouched, then
  `await db.execute(insert(AggregatedData), insert_data)`. No `_canonicalize_dims`, no `ON CONFLICT`.
- `:89` — the class docstring's "All operations are performed within a separate database session with automatic
  transaction management", which the method does not perform.
- `src/mkobi/data/storage/manager.py:414`, `:428` — `StorageManager`'s own, differently-named `_bulk_insert`.

**Unreachability re-verified.** A repository-wide grep for `.bulk_insert(` (the call form, excluding the
declarations) across `src/` and `tests/` returns **no production caller**. The only references are the
interface declaration, the implementation, `StorageManager`'s private method of the same name, and test/prose
mentions. Nothing un-canonicalised is stored today.

**Consequence** — Confirmed as LOW: no runtime consequence, real maintenance risk, and a docstring that is
false of the repository's surface as it stands.

**Recommendation** — Upheld, including the instruction to investigate phase ownership before deleting rather
than assuming the surface is dead.

---

### DP-111 — `processing-api.md` reverses the post-commit unlink

**Verdict** — CONFIRMED (one supporting citation corrected)

**Severity** — LOW (unchanged)

**Evidence** — The contradiction is real and both sides were re-read:

- `docs/03-processing/processing-api.md:244-248` — *"A `completed` or `failed` row is also the **end of the
  file's life**: the input was removed before the transition was written, so a terminal status and an absent
  artefact are the same fact."*
- `src/mkobi/workers/data_worker.py:1035-1037` — the success-path unlink, which follows the commit that
  writes the terminal row. The `async with session.begin():` block opens at `:1013` and exits at `:1028-1032`.
- `docs/03-processing/file-cleanup.md:58-70` — the sibling document states it correctly under *"The
  success-path unlink is *after* the commit"*, and `:69-70` describes the very window
  (`processing-api.md:244`) declares impossible: *"a committed `completed` row with the file still present."*

**CITATION CORRECTION.** The report says *"The failure path does unlink inside the transaction body
(`src/mkobi/workers/data_worker.py:960`)"*. **`:960` is the test-path handler**, reached only when `db_session`
is supplied; the production failure-path unlink is at `:1056`, inside the `except BaseException` handler, which
runs *after* the transaction has exited and rolled back — the code says so at `:1066-1069`. The report's
conclusion ("the two paths genuinely differ and the claim is only half wrong") survives unchanged: on the
failure path the unlink does precede the terminal row write, which is exactly what `processing-api.md:244`
asserts; the half that is wrong is the `completed` half. The supporting anchor moves from `:960` to `:1056`.

**Consequence** — Confirmed as LOW. The code is correct and `file-cleanup.md` is correct; the cost is that the
page a developer reads first states the opposite of the invariant, and anyone writing a reconciliation check
from it would write the wrong one.

**Recommendation** — Upheld. Rewriting `:244-248` to match `file-cleanup.md:58-70` is right, and the report is
correct that the window belongs on this page too rather than only in the page it links to.

---

## Merged findings

None. DP-101 and DP-104 share a code path (`_durable_failure_message`) but are distinct defects: one is a
missing coercion at the producer/consumer boundary, the other is a discarded diagnostic at the terminal write.
Neither subsumes the other and neither is fixed by fixing the other. The report's own cross-finding analysis
groups them under a common cause, which is an observation about the file, not a merge.

`DP-102` and `DP-103` are likewise adjacent — both concern non-finite values — but one is about the metric
payload and the other about the dimension identity, and both fixes are independent. `DP-103`'s recommendation
already notes the interaction ("whenever the metrics on those rows are themselves finite (so it survives
DP-102)"), which is correct.

---

## Rejected claims

Three claims in the report are rejected. None is a finding; two are evidence defects inside confirmed findings
and one is a false no-findings entry.

**REJECTED — the "no pandas" no-findings entry (coverage record, block 9).** The report's coverage record
claims, in effect, that pandas is absent. **`pandas-stubs==3.0.0.260204` is declared at `pyproject.toml:219`
and resolved at `uv.lock:1312` (specifier at `:1121`), and `_base-context.md:38` lists "**No pandas** — Polars only" among the
hard rules. The claim is false as stated.

However, the substantive fact is *not* a missed finding of this phase. Phase 01 already filed it:
**`TOPO-114`** (LOW, "The declared dev toolchain includes stubs for a dependency the project forbids"),
citing the same `pyproject.toml:219`, validated and confirmed in
`.ai/audit/99-validation/01-process-architecture-validated-findings.md`. Re-filing it here would duplicate an
already-validated finding.

Independently re-verified, and worth recording because the base context makes pandas hard-prohibited:
**no runtime pandas exists.** `grep` for `pandas` across `src/`, `tests/` and `frontend/src/` returns no
matches; `importlib.util.find_spec('pandas')` returns `None`; pandas is not in any dependency group. The only
trace in the tree is the dev-group stub package. So the rule is respected at runtime and violated only in the
manifest — exactly as `TOPO-114` states. The correct action is to correct this report's coverage-record entry
to point at `TOPO-114`, not to mint a new ID.

**REJECTED — DP-102 evidence item 2, "one non-finite cell poisons every aggregate function".** Refuted by
execution. In a mixed group (`NaN` and `5.0`), Polars returns `min=5.0`, `max=5.0`, `last=5.0`; `count` returns
an integer on any input. The report's own supporting example groups by `(a, b)`, which puts each row in its own
group and therefore cannot demonstrate the claim. See the DP-102 correction above.

**REJECTED — DP-102 consequence, "there is no `metric_agg` an operator can switch to that avoids it".** Refuted
by the same execution. `count` is always finite; `min`/`max` survive a `NaN` in a mixed group. This claim was
the finding's main argument for HIGH, and it is false.

---

## Missed findings

### VAL-05-101 — `UploadMode.APPEND` is not a full recomputation, contradicting the declared contract

**Severity** — MEDIUM (new; recommended for filing)

**Zone** — Block 5, "Replacement semantics: what an overwrite and an append each remove"

**Observation** — The project's declared hard rule requires a full recomputation of the dashboard's aggregates
on every upload. `AGENTS.md:77`: *"При загрузке файла — **полный пересчёт** агрегатов для дашборда"*.
`docs/03-processing/processing-api.md:134-139` states it in stronger terms and explicitly rules out the
exception: *"Each upload triggers a **full recalculation** — both `aggregated_data` and
`dashboard_filter_values` are rebuilt from scratch. There is no incremental aggregation. **The claim is
unconditional** because an upload whose selection matches no graph is a **failed run**, not a silent success…"*.

`UploadMode.APPEND` is reachable in production and does not perform a full recomputation:

- `src/mkobi/api/routes/upload.py:145` — `mode: UploadMode = UploadMode.OVERWRITE` is an endpoint parameter,
  defaulted but fully caller-selectable; threaded to the service at `:246`.
- `frontend/src/features/upload/ui/UploadModal.tsx:226-228` — a first-class UI toggle, *"Append (Add new rows)"*.
- `src/mkobi/workers/data_worker.py:1259` — `clear_old = mode == UploadMode.OVERWRITE`, so `clear_old` is
  `False` in APPEND.
- `src/mkobi/data/storage/manager.py:202-211` — `clear_old=False` selects `_bulk_upsert`, which upserts the
  new records and **leaves every prior row in place**, i.e. merges into the accumulated history rather than
  rebuilding from the uploaded file.
- `src/mkobi/workers/data_worker.py:1281-1283` — the APPEND branch then rebuilds the filter list from the
  union of the new and all prior rows, confirming the mode's intent is accumulation.

`UploadMode` is a `StrEnum` with both members (`src/mkobi/models/enums.py`), so the mode is a first-class,
fully reachable, user-selectable part of the contract.

**Evidence** — Executed: `clear_old` is derived from the mode at `data_worker.py:1259` and selects the upsert
path, and the same run's filter rebuild reads `manager.get_aggregates(dashboard_id)` at `:1282`, i.e. the
accumulated total rather than the file's own rows. Both cited lines were re-read; the chain from the UI toggle
to the writer was followed end to end with no gap.

**Consequence** — The declared invariant is false for one of two documented, user-selectable modes. The stored
state after an APPEND upload answers a different question from the state after an OVERWRITE upload of the same
file: the first is the aggregate of every file ever appended, the second is the aggregate of this file. The
contract text asserts there is no such mode. This is also the enabling condition for DP-103's silent form —
APPEND's merge semantics are what let one upload's identity replace another's — so the two are not independent
in effect even though their mechanisms differ.

**Recommendation** — Decide which is true and make the other match; do not leave both. Either (a) treat APPEND
as a deliberate, documented exception and correct `AGENTS.md:77` and `processing-api.md:134-135` to scope the
claim to OVERWRITE, stating plainly what APPEND accumulates; or (b) if full recomputation is genuinely
required, remove or gate `UploadMode.APPEND`, which also closes DP-103's silent-cross-upload form and DP-109's
unbounded rebuild at the source. Option (a) is the smaller change and should land regardless: the current text
asserts something the code does not do, which is the same class of defect as DP-111.

---

## Rollout analysis

**Sequencing is unchanged and the report's roadmap order is correct**, with one addition.

- **DP-101 first.** It is the only finding that disables a shipped feature entirely, it is reachable from the
  dev stack without operator action, and the fix is one line at the read. Everything else is cheaper to reason
  about once the primary path works.
- **DP-103 second, as the report says** — and this validation strengthens that ordering. The silent APPEND form
  is now reproduced against a live database rather than argued, and the loud forms were verified to raise
  rather than merely to be predicted. The report's warning that step 2 needs a backfill plan for
  `aggregated_data.dims` before any revert is correct and should not be relaxed.
- **VAL-05-101 should be decided before DP-103 is implemented**, not after. DP-103's recommended fix
  (injective canonicalisation) is only the right fix under OVERWRITE semantics; under APPEND semantics an
  injective identity still merges two uploads' rows into one identity by design. Deciding the contract question
  first removes that dependency. This inverts the report's ordering for one step and costs nothing otherwise.
- **DP-102's downgrade does not change its position.** It remains worth fixing before aggregation, in the
  validator, and its fix is independent of every other finding.

**Risks.**

- DP-101's one-line fix (`or []`) changes no schema and no contract; revert is clean.
- DP-103's option (a) requires a read-path change in `aggregated_data_repo.py:241-246` and a backfill. Its
  option (b) is smaller but leaks a sentinel into the read path. Neither is safe to ship without the backfill
  plan the report already demands.
- DP-104's fix must not reproduce raw exception text; the narrow graph-name-only message is the safe shape.
- DP-110's recommendation correctly requires a phase-ownership answer before deleting the interface. Do not
  delete on the strength of "no caller today" alone.
- VAL-05-101 option (b) removes a user-facing feature; that is a product decision, not a code change.

**Rollback feasibility** — unchanged. Only DP-103 carries a rollback hazard, and it is a data-migration
hazard rather than a code one.

---

## Execution validation

**Applicability** — All eleven findings were re-verified against the working tree and every one still applies.
The auditor's disclosure that commits `f8581e0` and `cfab3e0` landed mid-pass was checked independently, and
their post-hoc re-verification holds. HEAD then advanced twice more during this validation, to `cfab3e0` and
`0ae6ddf`; `git diff --stat f8581e0..0ae6ddf` touches only `frontend/src/features/dashboards/ui/charts/` and
`.ai/plans/16-phase16-residual-execution.md`, neither of which any finding in this phase cites. I re-opened every
citation against the tree as it stands at `0ae6ddf` rather than trusting that, and all resolve. The two
citations that had drifted are named above (DP-104 `:945`, DP-111 `:960`); both are in recommendations or
supporting evidence, not in a finding's core claim.

**Evidence class** — DP-101, DP-102 and DP-103 are now stronger than filed: each was executed against the live
`mkobi-db-1` rather than argued from source. DP-101 was driven through the real worker entry point, closing the
report's own stated gap. DP-103's loud forms were run, closing its stated gap. DP-102's bind leg was exercised
through the application's own engine, replacing a `psql` parser probe that could not have shown driver
behaviour. DP-104 through DP-111 are static findings whose citations all resolve; DP-105's claim is a
control-flow reading that the corrected evidence does not weaken.

**Database hygiene** — Every probe ran inside a transaction that was rolled back, or against probe rows that
were explicitly deleted. Baseline counts `processing_logs=5, aggregated_data=0, processing_configs=1,
dashboards=5, graphs=2, dashboard_filter_values=0` were recorded before the first write and re-verified as
identical after the last delete. No file under `src/`, `frontend/src/`, `tests/`, `alembic/` or `docker/` was
modified; this validation report is the only file written.

**Not verified** — Stated so it is not mistaken for a clean bill: no job was dispatched through RQ and Redis,
so the enqueue→worker hop was read rather than executed; the composed `INSERT` for DP-102 was not run against a
table (its `ARRAY(JSONB)` bind was exercised through the same engine and dialect, which is the failing link,
but the full statement was not); and no plan-order divergence was observed for DP-108, whose finding is
correctly framed as the absence of a guarantee.

---

## Warnings

**Architectural.** The worker reads its configuration through `dict.get(key, default)` against a mapping
produced by `dict(pydantic_model)`. `dict.get`'s default only applies when the key is *absent*, so every
nullable model field becomes a latent crash at the consumer. DP-101 is one instance of a class, not a one-off;
the report's recommendation to coerce at the read is the right class-level fix, and it is worth noting that the
same pattern appears at `data_worker.py:689` for the whole settings object.

**Data model.** `dims` is JSONB whose identity is `dims::text`, so the identity is a *rendering* of the value,
not the value. Any change to a column's native type changes its rendering and therefore its identity —
`manager.py:70-72` documents this and DP-103's class is its direct consequence. Making identity depend on a
canonical form is right; the defect is that the canonical form is not injective, and the model's index has no
way to detect that.

**Contract.** Two documents assert behaviour the code does not have: `processing-api.md:244` (DP-111) and
`processing-api.md:134-135` / `AGENTS.md:77` (VAL-05-101). The first is drift from a fixed change; the second is
a live contradiction reachable from the UI. `docs/00-overview/doc-maintenance-rules.md` governs both.

**Observability.** TOPO-102 (rq-worker does not emit logs) is load-bearing for three findings in this phase —
DP-101, DP-104 and DP-107 all rely on "the cause is only in the worker log". If TOPO-102 is fixed, all three
become materially easier to diagnose; if it is not, they are close to unfixable operationally. This coupling is
under-stated in the report and is worth surfacing to the coordinator.

**Maintainability.** DP-110's dormant second write surface is a live trap: it is the discoverable name, it is
declared on the interface, and its docstring promises transaction management it does not perform.

---

## Final severity counts

| Severity | Filed | Validated | Δ |
| --- | --- | --- | --- |
| CRITICAL | 1 | 1 | 0 |
| HIGH | 2 | 1 | **−1** (DP-102 → MEDIUM) |
| MEDIUM | 6 | 7 | **+1** (DP-102 in; VAL-05-101 new) |
| LOW | 2 | 2 | 0 |
| **Total** | **11** | **11 + 1 new** | — |

**Verdicts:** CONFIRMED 8 (DP-101, DP-103, DP-104, DP-105, DP-106, DP-107, DP-108, DP-109, DP-110, DP-111 —
of which DP-104, DP-105 and DP-111 carry corrected citations/evidence), CORRECTED 1 finding (DP-102: severity
downgraded and two claims struck), REJECTED 0 findings / 3 claims. The three findings with corrected citations
are counted as CONFIRMED because the defect, its severity and its consequence all survive; the corrections are
to supporting material, not to the claim.

**No finding duplicates an already-validated finding.** DP-101 through DP-111 are distinct from every ID in
`.ai/audit/_base-context.md` and from the validated sets of phases 01-04. The only cross-phase overlap found is
the pandas-stubs item, which is **already filed as `TOPO-114`** by phase 01 and is deliberately not re-filed
here.

**Namespace.** `DP-1xx` was verified free across `docs/`, `.ai/`, `src/`, `tests/`, `frontend/`, `alembic/` and
`docker/`; `DP-001 … DP-019` remain occupied by this phase's earlier pass (referenced from `docs/SPEC.md:234`,
`:245`, `docs/03-processing/processing-api.md`, `docs/03-processing/file-cleanup.md`, and
`.ai/tasks/B2-txn-005-rebuild-exclusion.yaml` / `B3-txn-003-durable-processing-transitions.yaml`), and the
two-digit `DP-NN` series names plan decisions in `.ai/decisions/`. `DP-101` onward was the correct choice.
`VAL-05-101` follows this report's `VAL-` convention and is likewise free.