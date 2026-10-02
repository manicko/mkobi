---
phase: 05-data-pipeline
executed: 2026-10-01
executor: code-context-auditor (phase 1)
role: analysis only — no remediation design, no production-code change
head: b646ef1
report-under-decomposition: .ai/audit/99-validation/05-data-pipeline-validated-findings.md
upstream-findings: .ai/audit/05-data-pipeline/findings.md
anchor-authority: symbols, modules, routes, config keys, tables — line numbers are evidence of drift only
---

# 05-data-pipeline — Code Context (Phase 1)

## 1. Scope and method

**Read on disk (not HEAD-assumed):** `workers/data_worker.py`, `services/file_processing.py`,
`services/aggregation_service.py`, `services/processing_config_service.py`, `services/file_cleanup.py`,
`services/data_service.py`, `core/task_queue.py`, `rq_worker_wrapper.py`, `app.py`, `db/starter.py`,
`db/session.py`, `db/models/aggregated_data.py`, `db/repositories/{aggregated_data_repo,
dashboard_filter_values_repo}.py`, `data/storage/manager.py`, `data/loaders/{loader,validator}.py`,
`data/processing/{transformations,aggregate_transforms,filter_transforms}.py`,
`models/{data,types,enums,transformation_configs,processing_configs}.py`,
`api/routes/upload.py`, `api/deps.py`, `config.py`, plus the three sibling execution plans, the
upstream findings file, the validation report, and the pipeline-facing docs and tests.

**Verified by execution:** `uv run mypy src/mkobi/workers/data_worker.py` → **clean, zero errors** (this
is the load-bearing execution result: DP-009's defect is invisible to the type gate). `git log -S` to
date the `str()` filter-value coercion. Repository-wide symbol greps (`pl.all().first()`,
`trigger_processing`, `enqueue_processing_job`, `save_filter_values`, all three `file_cleanup`
helpers, `STARTED`/`success` in docs).

**Verified by reading only:** every runtime claim about the accepting path, the RQ topology, the
Polars step order, the JSONB conflict target, and the retention clocks. No container was started; no
database was written. The test database is Docker-only (`.kilo/rules/commands.md`).

**HEAD-vs-worktree split.** `HEAD = b646ef1`. The uncommitted edits are
`api/deps.py`, `api/routes/admin.py`, `db/session.py`, `interfaces/service_interfaces.py`,
`services/user_service.py`, `tests/{test_admin_user_management,test_token_revocation,test_users_api}.py`
(+ new `tests/test_user_service.py`). **No pipeline file is dirty.** Every `DP-*` verdict below is
therefore identical at HEAD and in the working tree. Two shared seams *are* dirty and matter:
`api/deps.py::get_db_dependency` (the session contract DP-001's Appendix C cites) and
`db/session.py` — both are phase-03 B1 territory and neither is a phase-05 edit target.

**The load-bearing difference from the report's baseline.** The validation ran at `c3c0a61`
(2026-09-30 14:13). Commit **`8953bf7`** ("fix(gates): restore green ruff and mypy baselines",
2026-09-30 21:20) landed *after* that baseline, on this branch, and added the `str()` coercion at
both `save_filter_values` call sites — the exact remedy DP-005 recommends. It was a **mypy
`arg-type` fix, not a phase-05 remediation**, and nothing records the intent. This single fact
reshapes one finding and must not be missed by the Planner.

## 2. Per-finding context

### DP-001 — failed COMMIT leaves a queued job with no status row (CRITICAL; absorbs TXN-002)

| claim | verdict today | anchor |
| --- | --- | --- |
| effect order validate → `STARTED` row → `UPLOADED` update → rename → enqueue → commit | **substantiated** | `file_processing.py::process_upload_with_session` — `create_log` → `update_status(UPLOADED)` → `file_path.replace(final_file_path)` → `enqueue_processing_job` → `await db.commit()` (the commit is last) |
| the queue is `asyncio.Queue.put` at `core/task_queue.py:46`, "which no database failure can retract" | **refuted** | `core/task_queue.py::enqueue_job` → `asyncio.to_thread(queue.enqueue, …)` on an **RQ** queue; `DEFAULT_QUEUE_NAME = "default"`. The window is now a thread hop + a Redis round trip, and the consumer is in a **different container** (`rq-worker`). The *conclusion* (irreversible once the enqueue returns) survives; the mechanism does not |
| the false "proper transaction atomicity" comment | **substantiated — C-1 verified TRUE** | `file_processing.py` still reads `# Enqueue job BEFORE commit for proper transaction atomicity` / `# If enqueue fails, we rollback and clean up the moved file` |
| consumer's status UPDATE never inspects `rowcount` | **substantiated** | `data_worker.py::_update_processing_log_status` — `update(ProcessingLog).where(id == UUID(task_id))`, `await session.execute(stmt)`, result discarded; logs "Processing log updated" unconditionally |
| `docs/00-overview/data-flow.md` states the opposite design | **substantiated** | `data-flow.md` "**Transaction safety**: File move to final path occurs **after** DB commit … On commit failure, the file remains at the temp path" — resolves verbatim, and the code is the worse of the two |
| blocker: `tests/test_file_processing.py` asserts enqueue-before-commit | **refuted — the file does not exist** | `tests/` has no `test_file_processing.py` |
| blocker: `tests/test_upload_api.py` asserts enqueue-before-commit | **drifted** | it does **not** assert commit order. `test_upload_submits_job_with_correlated_task_id` patches `mkobi.core.task_queue.get_rq_queue` and asserts `call.kwargs["file_path_str"].endswith(f"{task_id}.csv")` — it pins the *path passed to the enqueue* (i.e. rename-before-enqueue), plus `call.args[0].__name__ == "process_csv_background_sync"`. `test_upload_submission_failure_is_rfc7807` pins the 500 + `FILE_PROCESSING_ERROR` on enqueue failure |

**Seams.** Producer: `file_processing.py::process_upload_with_session`, `::enqueue_processing_job`;
broker: `core/task_queue.py::enqueue_job` / `::get_rq_queue`; consumer entry:
`data_worker.py::process_csv_background_sync` (contract pinned by
`tests/test_rq_worker.py::TestRegisteredJobCallable`, which asserts the **source text** of
`enqueue_processing_job` contains each `process_csv_background_sync` kwarg name). Six enqueue patch
sites in `tests/test_data_service.py`. Second producer: `DataService::trigger_processing`
(**no route caller** — interface declaration + tests only).

### DP-002 — `metric_agg` read under a shape no producer creates (re-graded MEDIUM, VAL-05-001)

**substantiated.** `data_service.py::_execute_upload` builds `processing_config = dict(config_response.settings)` — settings at top level. `data_worker.py` reads it correctly once (`settings = processing_config_dict.get("settings", processing_config_dict)`) and wrongly twice:
`metric_agg = (processing_config_dict or {}).get("settings", {}).get("metric_agg", "sum")` in **both**
branches of `_store_aggregates`. `_agg_fn_map` therefore always receives `"sum"`.

**New fact the report does not have:** the *second* read sits in the `db_session is None` branch of
`_store_aggregates`, which the production path never reaches — `_run_with_transaction` always calls
`_store_aggregates(..., db_session=session)`. The two branches are near-duplicate copies. "Fix both
reads" is therefore one live fix plus one dead mirror; the Planner must decide whether the dead
branch is repaired, deleted, or left (a *dead-code* question, not a bug fix).

### DP-003 — dtype-sensitive row identity splits one category into two rows (CRITICAL)

**substantiated, anchors exact.** Unique index `uq_aggregated_data_dashboard_graph_dims` on
`(dashboard_id, graph_id, text("dims::text"))` — `db/models/aggregated_data.py`. Conflict target
`text("((dims)::text)")` in `StorageManager._bulk_upsert` **and** `StorageManager.upsert_aggregate`.
`_normalize_json_keys` sorts keys only. `AggregationService._coerce_dim_value` deliberately preserves
`int`/`float`/`bool` and collapses `None → ""`. No canonicalisation rule exists anywhere.

### DP-004 — empty overwrite reports `completed`, keeps stale rows, wipes filter values (HIGH; absorbs TXN-004)

**substantiated, anchors exact.** `StorageManager.save_aggregates` returns `0` at its
`if not aggregates:` branch **before** `if clear_old: await self.delete_by_dashboard(...)`. The
secondary list is cleared unconditionally then rebuilt from the (empty) record list —
`data_worker.py` `_store_aggregates`, both branches. Status is then written `COMPLETED` with
`Processing completed successfully: N rows processed`. `data-flow.md` twice promises
"Full recalculation (all aggregates rebuilt)". **No test covers `save_aggregates` at all** —
`tests/test_storage_manager.py` exercises only `clear_graph_data` / `clear_dashboard_data`.

### DP-005 — numeric/bool filter column makes every upload fail (re-graded MEDIUM, VAL-05-002) → **already-fixed**

`str_values = [str(value) for value in fvalues]` is present at **both** `save_filter_values` call
sites in `_store_aggregates`, with the comment "the filter value column is String-backed, so `str()`
here keeps that contract honest". Landed in `8953bf7`, *after* the validation baseline — which is why
the validator re-derived the failure at the **repository** layer and correctly called it "not a probe
artefact" while never exercising the production call site.

Residual: `DashboardFilterValuesRepository.save_filter_values(..., values: list[str], ...)` performs no
coercion of its own. The `list[str]` annotation plus a green mypy gate is now the only guard.
Validation's claim that "the current suite only exercises text" is unverified here; the
recommendation's second half (a dtype-matrix test) is **not** satisfied by the landed commit.

### DP-006 — filter named like a graph dimension aborts aggregation (HIGH)

**substantiated, anchors exact.** `AggregationService.aggregate_for_dashboard` builds
`groupby_cols = [d for d in (graph.dimensions + dashboard_filter_dim_names) if d in df.columns]` with
no de-duplication, then `df.group_by(groupby_cols).agg(agg_exprs)`. `dict.fromkeys` is nowhere in the
method.

### DP-007 — `groupby` without `aggregations` stores an arbitrary row (HIGH)

**Claim substantiated; recommendation partly refuted.** `transformations.py` step 2 is
`result.group_by(groupby).agg(pl.all().first())` — the *only* occurrence of that expression in the
repository. The recommendation's "the same expression is reached by `aggregate_data`
(`aggregate_transforms.py`), so fix it in one place" is **wrong**: `aggregate_data` calls
`calculate_aggregations`, which contains no `pl.all().first()`. There is one site, not two. The
validator's replacement transcript (identical values, forward vs reversed) is the correct evidence
and must be the basis of the test (VAL-05-005).

### DP-008 — `limit` applied before aggregation (HIGH)

**substantiated.** `apply_transformations` orders filters → groupby → sort → **limit**; the worker
calls `calculate_aggregations` afterwards. `ProcessingConfig.limit` exists;
`ProcessingSettingsDict` (`models/types.py`, a `TypedDict(total=False)`) does **not** list `limit`,
`sort_by`, `descending`, `required_columns` or `metrics` — those keys are settable only by passing
`ProcessingConfig(**dict)`, which the worker does after the frame is built.
`_validate_processing_config` never pairs `limit` with `sort_by`.

### DP-009 — `yoy_config` / `share_config` / `custom_metrics` cannot be stored and used (HIGH)

**substantiated.** `ProcessingConfig.yoy_config: YoyConfig | None`, `share_config: ShareConfig | None`,
`custom_metrics: list[CustomMetricConfig] | None`. The worker forwards the **models** into
`calculate_aggregations`, which does `_calculate_yoy(result, **yoy_config)`,
`_calculate_share(result, **share_config)`, `_add_computed_fields(result, custom_metrics)`; the last
reads `field.get("name")` and re-raises. `_calculate_yoy` with no `group_cols` sorts by
`[year_column]` then applies an ungrouped `shift(1)` — the report's second, order-dependent defect.

**New, load-bearing:** `mypy src/mkobi/workers/data_worker.py` is **clean**. The `asyncio.to_thread`
boundary erases the argument types, so neither ruff nor mypy can see this. A regression test is the
only available detector — the Planner should not assume a gate will catch a regression here.

### DP-010 — classification by substring; `AppException.code` discarded (HIGH)

**substantiated, both sites unchanged.** `data_worker.py::_map_processing_error_to_code`
(`isinstance(FileNotFoundError)` → `"encoding"` → `"csv" and ("read"|"parse")` →
`"missing required columns"` → `"validation failed"` → `"too large"|"size"` → default
`PROCESSING_FAILED`) never reads `error.code`. `api/routes/upload.py::_handle_value_error`
(`"mime"` → `"format"|"extension"` → `"size"|"exceeds"|"max"` → `"limit"|"rate limit"` → else
`VALIDATION_ERROR`) never reads it either. `CSVLoader.load_csv` still wraps every failure as
`ValueError(f"Failed to load file {file_path}: {e}")`, destroying the type. `_validate_processing_config`
raises `AppException(VALIDATION_ERROR)` for every config defect; the worker overwrites the code with the
substring result.

### DP-011 — byte ceiling on the compressed form; "lazy" branch collects (MEDIUM)

**substantiated, anchors exact.** `CSVLoader._read_csv_lazy` ends `pl.scan_csv(...).collect()`;
`_get_file_size_mb` measures `st_size`; `_read_csv` opens `gzip.open(file_path, "rb")` for `.gz`.
`lazy_threshold_mb` (default `10.0`) selects a branch that changes only how the frame is built.

### DP-012 — worker consults a hard-coded 100 MiB ceiling (MEDIUM)

**substantiated.** `data_worker.py` constructs `loader = CSVLoader()` with no argument;
`CSVLoader.__init__` takes `config or LoaderConfig()`; `LoaderConfig.max_file_size` default is
`100 * 1024 * 1024` in `models/data.py`. `CSVLoader._validate_file_size` reads
`self.config.max_file_size` when no explicit maximum is passed and raises
`ValueError("File too large: … (max: …)")`, which `_map_processing_error_to_code` maps to
`FILE_TOO_LARGE`. Same is true of `LoaderConfig.required_columns` / `column_types` /
`strict_schema`: the loader's own checks are gated on `self.config.*` and never run, because the
worker builds its own `LoaderConfig` for the validator separately and does the casting itself.
No `MAX_FILE_SIZE_MB` reference exists under `data/loaders/`.

### DP-013 — validation warnings computed then discarded (MEDIUM)

**substantiated.** `DataValidator._validate_column_types` returns `(errors, warnings)` and only ever
`warnings.append(...)`; `_validate_data_quality` and `_validate_duplicates` are warning-only. The
worker reads **only** `validation_result.is_valid` and `validation_result.errors` and writes
`processing_logs.message` with the completion sentence. `required_columns` is absent from
`ProcessingSettingsDict`, so an unconfigured dashboard runs no schema check at all. The cast loop
skips `float` and only casts `date` when `date_format` is present — so a declared
`{"revenue": "float"}` warns on every run and can never become true.

### DP-014 — validation runs before renames/casts (MEDIUM)

**substantiated, order exact:** validate → decimal separator → cast → rename → computed fields →
transform → aggregate, all inside `_run_with_transaction`. The cast guard
`if col_name in df.columns and col_type != "float":` has no `else` and logs nothing.
`settings.get("renames")` / `"computed_fields"` / `"decimal_separator"` misses are silent.
`ProcessingConfigService._validate_settings` type-checks four keys only.

**New constraint on the remedy:** `ProcessingSettingsDict` is a **`TypedDict`**, not a Pydantic
model, so `extra="forbid"` is not available on it as written. The precedent
(`TransformationConfig` with `model_config = ConfigDict(extra="forbid")`) exists in
`models/transformation_configs.py`. The `**` on `TransformationConfig(**config)` call already
converts a misspelled key into a `ValueError` → `PROCESSING_FAILED` in the worker, not a 422 at the
API — so the report's "unknown settings keys change from silently ignored to 422" only holds if the
settings model becomes a Pydantic model at the *storage* boundary. That is a real design fork.

### DP-015 — orphan sweep's bound is a one-minute literal, boot-only (MEDIUM) → **drifted**

| element | today |
| --- | --- |
| the literal | **still present** — `data_worker.py::mark_orphaned_uploaded_logs_failed`: `cutoff = datetime.now(UTC) - timedelta(minutes=1)`, no config read in the module |
| periodicity | still **boot-only**; `start_stale_processing_cleanup_task` calls `cleanup_stale_processing_logs` and nothing else |
| call sites | **two**, both inside `lifespan` and both lease-guarded: the `ACQUIRED` branch and the `UNREACHABLE` (fail-open) branch. The report's "`app.py:116` is the sole call site" no longer resolves |
| "exactly once per process lifetime" | **drifted**: once per lease holder, or on *every* replica when Redis is unreachable (fail-open by design) |
| the other two bounds | threaded from config in `lifespan` into the cleanup task (`interval_seconds`, `timeout_minutes`) |
| tests | `tests/test_app_lifespan.py` patches `mark_orphaned_uploaded_logs_failed` at **six** sites and pins boot-only invocation; `tests/test_data_worker.py` pins the function's own `UPDATE` shape |

### DP-016 — worker-side unlink uncompensated on cancellation (MEDIUM; second half re-typed by VAL-05-004)

**substantiated, anchors drifted +14.** Success path: the file is unlinked *inside*
`_run_with_transaction` **before** the `COMPLETED` update and before the commit (the commit is the
`session.begin()` exit in the production branch). Failure paths: the two `except Exception` handlers
that also unlink are unreachable for `asyncio.CancelledError` (`BaseException`). The
`cleanup_stale_temp_files` sweep selects on `upload_temp_dir.glob("*.csv*")` + `st_mtime` and never
consults `processing_logs`; bound is age only, no byte or count ceiling.
Process-kill residue (file gone, transaction never commits, row left at `processing`) is
unchanged and is the half VAL-05-004 re-types.

### DP-017 — stored row order never pinned (MEDIUM)

**substantiated.** `AggregationService._apply_chart_sorting` is the only ordering decision and its
docstring states the Plotly rationale; it sorts the aggregated frame, then `_store_aggregates`
inserts in that order. `AggregatedData` has an autoincrement `BigInteger` `id` and no `ordinal`
column. `AggregatedDataRepository.get_by_graph_id`, `get_by_dashboard_id` and `get_dims_values` have
**no `order_by`**. The remedy is an Alembic migration — **phase 14 owns the DDL surface**; phase 05
owns the defect and the rule statement.

### DP-018 — unrecognised `metric_agg` stored under its own name holding a sum (LOW; raised by VAL-05-001)

**substantiated.** `AggregationService.aggregate_for_dashboard` looks up
`_agg_fn_map.get(metric_agg, lambda c: c.sum())` — a 5-entry `dict` — and aliases
`f"{m}_{metric_agg}"` from the *requested* name. `AggregationFunctionEnum` declares ten members
(`enums.py`; the report's `:162-174` is now `:190-202`). `AGG_FUNC_MAP` in
`aggregate_transforms.py` already implements all ten, keyed by the enum. Masked today by DP-002;
reachable the moment DP-002 lands.

### DP-019 — two of three reclamation helpers have no production caller (LOW) → **drifted**

| helper | production callers today |
| --- | --- |
| `cleanup_task_files` | **none** (tests only) |
| `cleanup_stale_temp_files` | `DatabaseStarter.startup` — **plus a new second caller in `tests/conftest.py`** (session-scoped, `max_age_hours=0`) |
| `cleanup_old_processing_logs` | **none** (tests only); duplicated by `DatabaseStarter.cleanup_old_logs`, which is called from `startup` and whose definition has moved |

Dead-code policy applies: **investigate purpose before proposing removal** — `cleanup_task_files` is
the plausible home for DP-016's deletion, and `cleanup_old_processing_logs` duplicates a live sweep.

## 3. Cross-cutting architecture and constraints

**End-to-end path as it exists today.**

| stage | owner | anchor |
| --- | --- | --- |
| HTTP admission | route | `api/routes/upload.py::upload_file_endpoint` — declared-size check, Redis rate limit (100/hour/user, literal), 8 KiB chunked stream into `upload_temp_dir/upload_{uuid}_{name}`, `finally` unlink guarded by `exists()` |
| accept + transaction | service | `file_processing.py::process_upload_with_session` — MIME/extension/size validation, `STARTED` row, `UPLOADED` update, rename to `{log.id}.csv[.gz]`, RQ enqueue, **commit last** |
| submission | broker | `core/task_queue.py::enqueue_job` → RQ `DEFAULT_QUEUE_NAME`; consumer in a **separate container** |
| worker entry | worker | `rq_worker_wrapper.py::start_rq_worker` → `data_worker.py::process_csv_background_sync` → `process_csv_background` → `_process_csv_file_async` |
| parse | loader | `CSVLoader.load_csv` in `asyncio.to_thread`; one materialised `pl.DataFrame`; one `session.begin()` wraps the whole job |
| validate/transform | worker | `DataValidator.validate`, then decimal separator → casts → renames → computed fields → `apply_transformations` → `calculate_aggregations` |
| aggregate | service | `AggregationService.aggregate_for_dashboard` → records `{dashboard_id, graph_id, dims, metrics}` |
| persist | storage | `StorageManager.save_aggregates` → `aggregated_data` JSONB `dims`+`metrics`; unique index on `(dashboard_id, graph_id, dims::text)` |
| read | repo/route | `AggregatedDataRepository.get_by_graph_id` (filter compare `dims[key].astext == str(value)`), no `ORDER BY` |
| status | worker | `_update_processing_log_status` (no `rowcount` check); sweeps `cleanup_stale_processing_logs` (periodic, lease-guarded), `mark_orphaned_uploaded_logs_failed` (boot, lease-guarded, 1-minute literal), `DatabaseStarter.cleanup_old_logs` (boot, retention) |

**Reconciler/lease machinery already landed by phase 01/02** (`4a5db54`, `a92b546`, `3856f27`,
`9a77625`): `core/reconciler_lease.py` (`ReconcilerLease` / `ReconcilerStatus` /
`DEFAULT_LEASE_TTL_SECONDS`), the guarded loop in `data_worker.py::start_stale_processing_cleanup_task`,
`/health/detailed` reporting. **Fail-open by design.** Any phase-05 move of `mark_orphaned_uploaded_logs_failed`
into the periodic loop inherits that guard and its skip case.

**Shared seams and their owners.**

| seam | owner phase | why |
| --- | --- | --- |
| `_process_csv_file_async` transaction scope; `_update_processing_log_status` commit boundary; the `processing` state becoming committed | **03** (TXN-003 / B3) | B3 restructures the same `session.begin()` DP-016's file unlink sits inside, and must keep that unlink and the own-session `FAILED` compensation |
| advisory-lock placement as the first statement of the worker transaction | **03** (TXN-005 / B2) | shares the transaction B3 moves boundaries inside |
| `enqueue`/commit/move ordering; the false atomicity comment; `rowcount` check | **05** (DP-001; C-1) | C-1 is phase 05's outstanding debt from 03 |
| empty-overwrite boundary; the secondary-list rebuild | **05** (DP-004; C-2) | TXN-004 merged here |
| one-minute orphan horizon | **03** (B3, authorised by C-3) | the literal itself; **phase 05 must not apply it twice** |
| periodic-loop placement of the orphan sweep + its config key | **05** (DP-015 remainder) | not absorbed by C-3 |
| `aggregated_data.ordinal` DDL + `ORDER BY` | **14** (schema) | 05 owns the defect and the rule, 14 owns the migration |
| upload temp dir as a shared volume across `app` and `rq-worker`; byte ceiling on the sweep | **06** (file artifacts) / **10** (production ops) | compose ownership of the volume; alert/operational side |
| loader memory ceiling, `.csv.gz` expansion ratio, worker replica count | **11** (performance) | DP-011's cost measurement and the pool/residency budget |
| `ProcessingStatus.SUCCESS` removal already migrated (`4479eb53fd4e`) but still documented | **14** (`docs/09-database/`) vs **05** (pipeline narrative) | unassigned — see §5 |

## 4. In-flight and already-landed work

| change | symbol touched | bearing on this phase |
| --- | --- | --- |
| `8953bf7` (landed, ancestor of HEAD) | `data_worker.py::_store_aggregates` — `str_values` at both `save_filter_values` sites | **closes DP-005's recommended fix**; landed as a mypy `arg-type` repair, undocumented as a remediation |
| `3848e7a` | `core/task_queue.py` (in-process queue removed, RQ in), `file_processing.py::enqueue_processing_job`, `rq_worker_wrapper.py`, `data_worker.py::process_csv_background_sync` | **voids DP-001's `asyncio.Queue.put` mechanism**; creates a cross-container producer/consumer split the report predates |
| `0717b65` | `data_worker.py` production failure path — `FAILED` reported on its own session | DP-016's failure-path half must not regress it; B3 explicitly preserves it |
| `4a5db54`, `a92b546`, `3856f27`, `9a77625`, `b646ef1` | `data_worker.py::start_stale_processing_cleanup_task`, `_sleep_with_lease_renewal`, `core/reconciler_lease.py`, `app.py::lifespan`, `rq_worker_wrapper.py` | **DP-015 drift**: the boot orphan call is now lease-guarded and duplicated across two branches; six lifespan test patch sites |
| `c4c0b14` | docs for TOPO-001..008 | `docs/06-backend/architecture.md` updated; `docs/03-processing/task-queue.md` and `data-flow.md` **not** |
| working tree (uncommitted) | `api/deps.py`, `db/session.py`, `services/user_service.py`, `api/routes/admin.py`, `interfaces/service_interfaces.py` | phase-03 B1 in flight. Shares `deps.py::get_db_dependency` with DP-001's Appendix C adjacency. **No pipeline file dirty** |
| phase-03 plan | `C-1` owed by 05 — **still present in the tree**; `C-2` (status-contract confirmation) and `C-5` — **not recorded anywhere in the phase-05 corpus** | §5 |

## 5. Discrepancies and risks

**Symbols the reports name that do not exist today**

| named | reality |
| --- | --- |
| `tests/test_file_processing.py` (DP-001 recommendation, validation Appendix D) | **does not exist** |
| `asyncio.Queue.put` in `core/task_queue.py` (DP-001, TXN-002) | **gone** — `enqueue_job` → RQ |
| `TaskQueue` / `default_queue` / `get_task_queue` (referenced by `docs/03-processing/task-queue.md`, `data-flow.md`) | **gone**; `tests/test_task_queue.py` actively asserts their absence |
| `ProcessingStatus.SUCCESS` (in `docs/09-database/enums.md`, `schema-processing.md`, `admin-api.md`) | **not a member** — the enum has five; a migration already dropped the DB value |
| `processing_logs.status = success` (`data-flow.md`, `enums.md`, `admin-api.md`) | unreachable; `started_at→uploaded→processing→completed/failed` |
| `pl.all().first()` in `aggregate_data` (DP-007 recommendation) | exists in exactly one place |

**Findings whose recommended fix is refuted or overtaken**

1. **DP-005** — the fix is in the tree (`8953bf7`); the block's content changes from "add a `str()`" to "close the remaining test/annotation gap or record as closed".
2. **DP-007** — "fix it in one place" names a second site that does not exist.
3. **DP-014** — `extra="forbid"` is not available on `ProcessingSettingsDict` (a `TypedDict`); the "422 at the API" outcome does not follow from the current call chain.
4. **DP-001** — the named test blocker does not exist; the existing blocker pins a *path*, not a *commit order*; the named mechanism is RQ, not `asyncio.Queue`.
5. **DP-002** — "change both reads" reaches one dead copy.
6. **VAL-05-002**'s premise ("one `str()` at one call site removes it") is now history.

**Seams where two phases both claim ownership**

| seam | claimants | status |
| --- | --- | --- |
| the one-minute orphan horizon | 03 B3 (C-3, option (b), ruled) vs 05 DP-015 | **ruled in 03, not implemented**; 05 must not re-apply it. The remaining DP-015 half (periodic placement + config key) is uncontested |
| the worker transaction boundary | 03 B2/B3 vs 05 DP-016 | overlapping; B3 preserves the file unlink, DP-016 moves it after the commit. **The two cannot land independently** — the Planner must sequence 05 after 03 B3 |
| `processing_logs` status vocabulary in docs | 03 B10 vs 05 vs 14 | three files (`data-flow.md`, `enums.md`, `schema-processing.md`) still say `success`; 03 B3 claims `data-flow.md`'s status line only |
| `_store_aggregates` duplicate branch | 05 DP-002/DP-004 vs 03 B3 | B3 does not touch `_store_aggregates`; low risk, but the dead branch must not be "fixed" and then removed by a second phase |

**Documentation defects with no owner (DOC-UPDATE candidates)**

| file | claim | reality |
| --- | --- | --- |
| `docs/00-overview/data-flow.md` | "Processing task queued (**TaskQueue**)"; "in-memory `TaskQueue` for MVP; Redis + RQ for production" | RQ only since `3848e7a` |
| `docs/03-processing/task-queue.md` | documents `TaskQueue`, `default_queue`, `enqueue_job` as a wrapper, `get_task_queue`, `process_next`, `ProcessingStatus.SUCCESS` | none exist; the file is a migration plan for work already done |
| `docs/09-database/enums.md`, `schema-processing.md`, `04-admin/admin-api.md` | `success` is a `ProcessingStatus` | five members; `4479eb53fd4e` removed the DB value |
| `docs/00-overview/data-flow.md` | "File move … occurs **after** DB commit" | the opposite; DP-001's contradicted artefact |

**Tests that will break, and tests that will not**

| test | why |
| --- | --- |
| `tests/test_upload_api.py::test_upload_submits_job_with_correlated_task_id` | pins `file_path_str.endswith(f"{task_id}.csv")` — a DP-001 reorder that enqueues before the rename breaks it |
| `tests/test_upload_api.py::test_upload_submission_failure_is_rfc7807` | pins the enqueue-failure compensation shape |
| `tests/test_rq_worker.py::TestRegisteredJobCallable` (2 tests) | asserts the **source text** of `enqueue_processing_job` contains `process_csv_background_sync` and each kwarg name — a rename breaks it silently until runtime |
| `tests/test_data_worker.py` — 3 × `commit.assert_not_called()` | a real contract on `_update_processing_log_status`; phase 03 B3's chosen shape preserves it |
| `tests/test_app_lifespan.py` — 6 × `mark_orphaned_uploaded_logs_failed` patch | pins boot-only invocation; moving the sweep into the periodic loop needs new coverage and must not silently change these |
| `tests/test_data_service.py` — 6 enqueue patch sites | cross the seam DP-001 reorders |
| `tests/test_task_queue.py::TestRetiredSymbolsRemoved` | asserts the retired queue surface stays gone — a guard against reintroducing the old mechanism |
| `tests/test_file_cleanup.py` | covers all three helpers; follows whichever way DP-019 goes |
| `tests/test_storage_manager.py` | has **no** `save_aggregates` coverage — DP-004 currently has no test to break, and none to lean on |

**Data-loss and double-processing regression risk**

| risk | where |
| --- | --- |
| orphaned queued job replaces a dashboard's data with no attributable run (DP-001) | live; cross-container now, so the orphan is also invisible to the producer's process |
| DP-003 canonicalisation **changes stored row counts**; DP-002 changes **every stored metric**; DP-004 turns silent success into a **failed** run; DP-005-reverted would re-break numeric filters for dashboards that now succeed | all four are irreversible-in-one-direction or visibly breaking on deploy |
| double-processing: two rebuilds of one dashboard interleave; phase 03 owns the lock, but DP-003's canonicalisation changes *which* rows collide, so a 03→05 order puts 05's write-path change on top of a lock that does not yet exist | sequence 05 **after** 03 B2 |
| DP-016's unlink-after-commit leaks a file when the commit fails unless the failure path still unlinks (it does today, in `except Exception`) | both halves must move together |

## 6. Decision points for the Planner (must be left open)

| # | question | alternatives | who chooses |
| --- | --- | --- | --- |
| **D-05-A** | DP-001 order | (a) commit → move → enqueue (matches `data-flow.md`); (b) commit → enqueue → move; (c) keep the order and add a compensating `failed` write on enqueue-after-commit | Tech Lead; B3's transaction boundary is a precondition |
| **D-05-B** | DP-016 unlink placement | (a) unlink in a `finally` that catches `BaseException`, after the commit; (b) unlink after commit on success, keep the failure-path unlink where it is; (c) both halves in one change (the validator's own claim) | Tech Lead; constrained by B3 |
| **D-05-C** | DP-007: what does `groupby` without `aggregations` *mean*? | (a) deterministic de-duplication with a named rule; (b) reject at `_validate_processing_config`; (c) delete the branch | owner; changes which dashboards keep working |
| **D-05-D** | DP-008: `limit` without a fully-determining `sort_by` | (a) move limit after aggregation; (b) reject the pair at validation; (c) require `sort_by` | owner |
| **D-05-E** | DP-003 canonicalisation rule for `dims` identity | (a) `str()` every scalar dim (matches the read path's `astext == str(value)`); (b) preserve native values in `metrics`, canonicalise only the key; (c) a cast at parse time | owner + phase 14 (index DDL implication) |
| **D-05-F** | DP-013: where warnings land | (a) new status value (frontend change); (b) summarise into `message` (`String(1000)`, cap); (c) drop the never-true `column_types` check instead | owner; frontend involvement differs |
| **D-05-G** | DP-014: the settings boundary | (a) replace `ProcessingSettingsDict` with a Pydantic model + `extra="forbid"` (changes unknown keys to 422); (b) keep the `TypedDict` and validate in the worker; (c) type `ProcessingConfig` only | owner; needs `PUT /processing-configs/{dashboard_id}` caller + frontend-form inventory |
| **D-05-H** | DP-002/DP-005: the dead `_store_aggregates` branch | (a) fix both copies; (b) delete the unreachable branch; (c) leave it | owner; dead-code policy applies |
| **D-05-I** | DP-015 remainder: does the orphan sweep join the lease-guarded periodic loop, and under which config key? | (a) into `start_stale_processing_cleanup_task` (inherits the lease guard); (b) a separate periodic task; (c) a new `STALE_UPLOADED_TIMEOUT_MINUTES` key vs reuse of `stale_processing_timeout_minutes` | owner; must not re-apply C-3's horizon change |
| **D-05-J** | DP-019: investigate-then-decide on two uncalled helpers | wire `cleanup_task_files` into the consumer / delete both / correct the docs | owner; **investigate purpose first** |
| **D-05-K** | DP-017 `ordinal`: ship the Alembic migration, or ship `ORDER BY id` as an interim | (a) full migration (phase 14); (b) interim ordering + documented limitation | owner; phase 14 sequencing |
| **D-05-L** | orphaned `success` documentation across three docs | one owner, or split by file | coordinator |
| **D-05-M** | sequencing against phase 03: 05 after B2/B3, or interleave | B3 rewrites the transaction DP-016's unlink lives inside; B2's lock changes DP-003's collision surface | coordinator |

## 7. Coverage ledger

| finding | verdict | primary evidence anchors |
| --- | --- | --- |
| DP-001 | substantiated (mechanism refuted; C-1 comment present; one named blocker absent) | `file_processing.py::process_upload_with_session`; `core/task_queue.py::enqueue_job`; `data_worker.py::_update_processing_log_status`; `data-flow.md` "Transaction safety"; `tests/test_upload_api.py` |
| DP-002 | substantiated (second read site is dead) | `data_service.py::_execute_upload`; `data_worker.py::_run_with_transaction` (settings fallback) vs `_store_aggregates` (both `metric_agg` reads) |
| DP-003 | substantiated | `aggregated_data.py` unique index; `manager.py` `text("((dims)::text)")` ×2; `aggregation_service.py::_coerce_dim_value` |
| DP-004 | substantiated | `manager.py::save_aggregates` (`if not aggregates` before `delete_by_dashboard`); `data_worker.py::_store_aggregates`; `data-flow.md` "Full recalculation" |
| DP-005 | **already-fixed** (`8953bf7`, post-baseline) | `data_worker.py::_store_aggregates` `str_values` ×2; `dashboard_filter_values_repo.py::save_filter_values(values: list[str])` |
| DP-006 | substantiated | `aggregation_service.py::aggregate_for_dashboard` (`groupby_cols`, `df.group_by`) |
| DP-007 | substantiated; recommendation partly refuted | `transformations.py` `pl.all().first()` (single occurrence); `aggregate_data` does not reach it |
| DP-008 | substantiated | `transformations.py` step order; `data_worker.py` `limit=config.limit`; `models/types.py::ProcessingSettingsDict` |
| DP-009 | substantiated; **invisible to both gates** (`mypy` clean) | `models/data.py::ProcessingConfig`; `aggregate_transforms.py::calculate_aggregations`; `filter_transforms.py::_add_computed_fields` |
| DP-010 | substantiated | `data_worker.py::_map_processing_error_to_code`; `upload.py::_handle_value_error`; `loader.py::load_csv` wrapper |
| DP-011 | substantiated | `loader.py::_read_csv_lazy` (`.collect()`), `_get_file_size_mb`, `_read_csv` (`gzip.open`) |
| DP-012 | substantiated | `data_worker.py` `CSVLoader()`; `models/data.py::LoaderConfig.max_file_size` |
| DP-013 | substantiated | `validator.py` warnings-only appends; `data_worker.py` reads only `is_valid`/`errors` |
| DP-014 | substantiated; remedy constrained (TypedDict) | `data_worker.py` mutation order + cast guard; `processing_config_service.py::_validate_settings`; `types.py::ProcessingSettingsDict` |
| DP-015 | **drifted** (literal present; two lease-guarded boot sites; 6 test patch sites) | `data_worker.py::mark_orphaned_uploaded_logs_failed`; `app.py::lifespan`; `tests/test_app_lifespan.py` |
| DP-016 | substantiated (anchors +14) | `data_worker.py::_run_with_transaction` unlink-before-commit; two `except Exception`; `file_cleanup.py::cleanup_stale_temp_files` |
| DP-017 | substantiated | `aggregation_service.py::_apply_chart_sorting`; `aggregated_data.py` (no `ordinal`); `aggregated_data_repo.py` (no `order_by`) |
| DP-018 | substantiated | `aggregation_service.py` `_agg_fn_map` + alias; `enums.py::AggregationFunctionEnum` (10); `aggregate_transforms.py::AGG_FUNC_MAP` (10) |
| DP-019 | substantiated (2 of 3); **drifted** (new `conftest` caller) | `file_cleanup.py` ×3 helpers; `db/starter.py::cleanup_old_logs`; `tests/conftest.py` |

**Tally:** substantiated 16 · drifted 3 (DP-015, DP-016, DP-019) · already-fixed 1 (DP-005) ·
refuted-as-written 0 findings (but 1 recommendation fragment in DP-007 and 1 mechanism in DP-001 are
refuted) · stale 0. **VAL-05 defects that change a target: 2** (VAL-05-002 changes DP-005's block
content; VAL-05-004 re-routes DP-016's second half). VAL-05-003 is a Step-0 precondition on the report
prose, not a code target; VAL-05-001 and VAL-05-005 change ordering and test evidence only.
