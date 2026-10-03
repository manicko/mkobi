# Current state — phase 05 data pipeline

Audit of the CURRENT implementation at `d454603` (branch `feat/react`) against the
plan `.ai/plans/05-data-pipeline-remediation-execution.md` (its own baseline `b646ef1`).
Read-only. No code was changed.

## 1. Anchor resolution

**Every symbol in the plan's anchor table resolves at `d454603`. Nothing is MISSING.** No anchor
row needs to be reported as a finding. Seven anchors are **CHANGED** in the sense that a
behavioural sentence attached to them is now stale or factually wrong — those are starred and
explained in §3.

### 1.1 Anchor table (grouped by finding)

| Finding | Anchor symbols → file | Status | Note |
|---|---|---|---|
| DP-001 | `process_upload_with_session`, `enqueue_processing_job` (`services/file_processing.py`); `enqueue_job`, `get_rq_queue`, `DEFAULT_QUEUE_NAME` (`core/task_queue.py`); `_update_processing_log_status`, `process_csv_background_sync` (`workers/data_worker.py`); "Transaction safety" (`docs/00-overview/data-flow.md`) | EXISTS | Still enqueues pre-commit with the false atomicity comment. |
| DP-002 · DP-018 | `_run_with_transaction`, `_store_aggregates` (`workers/data_worker.py`); `AggregationService.aggregate_for_dashboard` incl. `_agg_fn_map` (`services/aggregation_service.py`); `AggregationFunctionEnum` (`models/enums.py`); `AGG_FUNC_MAP` (`data/processing/aggregate_transforms.py`); `DataService._execute_upload` (`services/data_service.py`) | EXISTS · **CHANGED\*** | `settings` fallback present; both `metric_agg` reads still nested. |
| DP-003 | `AggregatedData.__table_args__` (`db/models/aggregated_data.py`); `StorageManager._bulk_upsert` / `::upsert_aggregate` (`text("((dims)::text)")`), `::_normalize_json_keys` (`data/storage/manager.py`); `_coerce_dim_value` (`services/aggregation_service.py`) | EXISTS | Index uses `text("dims::text")`; both conflict targets use `text("((dims)::text)")`. Unchanged. |
| DP-004 | `StorageManager.save_aggregates` (`data/storage/manager.py`); `_store_aggregates`, `_update_processing_log_status` (`workers/data_worker.py`) | EXISTS | Early return still precedes `delete_by_dashboard`. |
| DP-005 | `_store_aggregates` (`workers/data_worker.py`); `DashboardFilterValuesRepository.save_filter_values(values: list[str])` (`db/repositories/dashboard_filter_values_repo.py`); `FilterValuesResponse` (`models/data.py`) | EXISTS | Both `str_values` coercions present; already fixed in `8953bf7`. |
| DP-006 | `AggregationService.aggregate_for_dashboard` (`services/aggregation_service.py`) | EXISTS | `groupby_cols` built without de-duplication; `dict.fromkeys` absent. |
| DP-007 | `apply_transformations` (`data/processing/transformations.py`) | EXISTS | `pl.all().first()` — sole occurrence repo-wide. |
| DP-008 | `apply_transformations`; `_run_with_transaction` (`limit=config.limit`), `_validate_processing_config` (`workers/data_worker.py`); `ProcessingConfig.limit/.sort_by/.descending` (`models/data.py`); `ProcessingSettingsDict` (`models/types.py`) | EXISTS · **CHANGED\*** | `ProcessingConfig` has **no** `limit`/`sort_by`/`descending`; step order unchanged. |
| DP-009 | `ProcessingConfig.yoy_config/.share_config/.custom_metrics` (`models/data.py`); `calculate_aggregations` / `_calculate_yoy` / `_calculate_share` (`data/processing/aggregate_transforms.py`); `_add_computed_fields` (`data/processing/filter_transforms.py`) | EXISTS · **CHANGED\*** | A **second** `_add_computed_fields` exists in `aggregate_transforms.py`; see note. |
| DP-010 | `_map_processing_error_to_code` (`workers/data_worker.py`); `_handle_value_error` (`api/routes/upload.py`); `CSVLoader.load_csv` (`data/loaders/loader.py`); `_validate_processing_config` (`workers/data_worker.py`) | EXISTS · **CHANGED\*** | Both classifiers substring-only; the blanket wrapper does **not** catch `FileNotFoundError`. |
| DP-011 · DP-012 | `CSVLoader._read_csv_lazy` / `_get_file_size_mb` / `_read_csv` / `_validate_file_size` / `__init__` (`data/loaders/loader.py`); `CSVLoader()` no-arg (`workers/data_worker.py`); `LoaderConfig.max_file_size/.required_columns/.column_types/.strict_schema` (`models/data.py`); `UploadSettings.max_file_size_mb` / `.lazy_threshold_mb` and `Settings.max_file_size` (`config.py`) | EXISTS · **CHANGED\*** | `Settings.max_file_size` is a **derived property**, not a setting. |
| DP-013 | `DataValidator.validate` / `_validate_column_types` / `_validate_data_quality` / `_validate_duplicates` (`data/loaders/validator.py`); `ValidationResult.warnings`, `ProcessingStatusResponse.message` (`models/data.py`); `_run_with_transaction` (`workers/data_worker.py`) | EXISTS · **CHANGED\*** | `warnings` has exactly one `src/` reader, itself uncalled. |
| DP-014 | `_run_with_transaction` (`workers/data_worker.py`); `ProcessingConfigService._validate_settings` (`services/processing_config_service.py`); `ProcessingSettingsDict`, `ProcessingSettingsModel` (`models/types.py`); `ProcessingConfigUpdate` (`models/processing_configs.py`) | EXISTS | `_validate_settings` type-checks exactly 4 keys; `ProcessingSettingsModel` still orphaned. |
| DP-015 | `mark_orphaned_uploaded_logs_failed`, `start_stale_processing_cleanup_task`, `_sleep_with_lease_renewal` (`workers/data_worker.py`); `lifespan` (`app.py`); `ReconcilerLease` (`core/reconciler_lease.py`) | **CHANGED\*** | The `timedelta(minutes=1)` literal is gone. |
| DP-016 | `_run_with_transaction`, `_process_csv_file_async` (`workers/data_worker.py`); `cleanup_stale_temp_files` (`services/file_cleanup.py`) | EXISTS | Unlink still inside the transaction body; both `except Exception` intact. |
| DP-017 | `AggregationService._apply_chart_sorting` (`services/aggregation_service.py`); `AggregatedData` (`db/models/aggregated_data.py`); `AggregatedDataRepository.get_by_graph_id` / `::get_by_dashboard_id` / `::get_dims_values` (`db/repositories/aggregated_data_repo.py`) | EXISTS | No `order_by` anywhere; no `ordinal`; `id` is `autoincrement=True`. |
| DP-019 | `cleanup_task_files` / `cleanup_stale_temp_files` / `cleanup_old_processing_logs` (`services/file_cleanup.py`); `DatabaseStarter.startup` / `::cleanup_old_logs` (`db/starter.py`); `tests/conftest.py` | EXISTS · **CHANGED\*** | The second caller is `pytest_sessionfinish`, a hook, not a fixture. |

\* = a behavioural sentence in the plan is stale or wrong; the symbol itself resolves.

### 1.2 The six "Anchor authority" correction rows — verdict at HEAD

| # | Correction | Verdict at `d454603` |
|---|---|---|
| 1 | DP-001's mechanism is an `asyncio.Queue.put`; in fact `core/task_queue.py::enqueue_job` is RQ (`asyncio.to_thread` + Redis round trip, consumer in another container). | **STILL CORRECT.** `core/task_queue.py` is the RQ seam; the in-memory `TaskQueue` is gone (`tests/test_task_queue.py::TestRetiredSymbolsRemoved` pins it). The conclusion survives. |
| 2 | `tests/test_file_processing.py` does not exist; `tests/test_upload_api.py` pins the path handed to the enqueue, not the commit order. | **STILL CORRECT.** `tests/test_file_processing.py` is absent; `test_upload_submits_job_with_correlated_task_id` exists in `tests/test_upload_api.py`. |
| 3 | DP-007's `pl.all().first()` is the only occurrence in the repository. | **STILL CORRECT — verified repo-wide across `src/` and `tests/`: exactly one hit.** |
| 4 | `ProcessingSettingsDict` is a `TypedDict`; `extra="forbid"` is unavailable on it. | **STILL CORRECT.** It is `TypedDict(..., total=False)`. Consequence for PB-8: adding a second unified model is the only strict option, and `TransformationConfig`'s `extra="forbid"` does not transfer to a `TypedDict`. |
| 5 | DP-005's `str()` landed in `8953bf7`. | **STILL CORRECT — commit exists.** Both `str_values` coercions present. **The plan nonetheless still schedules DP-005 work in PB-3; that work must be verification-only.** |
| 6 | DP-015's boot call has **two** sites, both lease-guarded, with **six** test patch sites. | **HALF WRONG.** Two boot call sites in `app.py::lifespan` — **correct**. Lease-guarded — **correct**. But `tests/test_app_lifespan.py` has **five** `mark_orphaned_uploaded_logs_failed` patch sites, not six. PB-13's verification gate is built on the wrong number. |

### 1.3 Two ambiguities an Implementor could get wrong

- **`_add_computed_fields` exists twice.** `data/processing/filter_transforms.py` (which the plan
  anchors for DP-009) and `data/processing/aggregate_transforms.py`, which is what
  `workers/data_worker.py` actually imports and calls. Same name, different modules, different
  call sites. Any grep-driven change will hit both.
- **`config.py::Settings.max_file_size` is a property** (`return self.upload.max_file_size_mb *
  1024 * 1024`), not an independent env-backed setting. PB-12's step-1 inventory must not treat it
  as a third place to configure the ceiling.

## 2. Phase-03 dependency status

### 2.0 Did the phase-03 blocks land?

**All nine phase-03 commits named by the task are present in history and are ancestors of HEAD.**

| Commit | Title | Landed shape |
|---|---|---|
| `2174895` | B1 — user unit of work | `api/deps.py` (+5/−5), `api/routes/admin.py`, `db/session.py`, `interfaces/service_interfaces.py`, `services/user_service.py` |
| `ab76989` | B2 — aggregate rebuild lock | NEW `db/advisory_lock.py` (+169), `config.py` (+6), `workers/data_worker.py` (+20) |
| `863b81b` | B2 follow-up — non-vacuous `lock_timeout` guard | `db/advisory_lock.py`, `data_worker.py`, `tests/test_advisory_lock.py` |
| `907e052` | B3 — durable processing transitions | `data_worker.py` (+90), plus `docs/00-overview/data-flow.md`, `docs/03-processing/processing-api.md`, `docs/07-frontend/upload-ui.md` |
| `a215a40` | B3 follow-up — sweep-horizon assertions | `data_worker.py` (−7/+7), `tests/test_data_worker.py`, `tests/test_processing_logs.py` |
| `7feb3b6` | B10 — architecture doc | `docs/06-backend/architecture.md` (+151) |
| `09ac709` | B9 — alembic migration lock | NEW `db/migration_lock.py`, `alembic/env.py` |
| `381fabb` / `986e56d` | B4 / B5 | `db/repositories/access_repo.py`, `api/routes/graphs.py` |

**HEAD is clean under `src/`, `tests/` and `docs/`.** `git status --porcelain` (110 entries)
contains only the pre-existing unstaged deletions under `.ai/audit/templates`, `.ai/builders`,
`.ai/structure`, `.ai/models`, `frontend/coverage`, plus untracked `.ai/plans/*.md` and
`.ai/tasks/*.yaml`. `git diff --stat -- src/ tests/ docs/` returns **empty**.

> **This falsifies a premise carried by four blocks.** The plan states that `api/deps.py`,
> `db/session.py` and `interfaces/service_interfaces.py` "carry uncommitted phase-03 B1 work"
> and that `interfaces/service_interfaces.py` "is dirty in the working tree". B1 landed in
> `2174895`. There is nothing uncommitted to preserve. PB-8, PB-10 and PB-14 all list
> "preserve the uncommitted changes" as a definition-of-done item; those items are void.

### 2.1 PB-1 / PB-14 blocker — phase-03 B3

**Verdict: SATISFIED.** (For PB-13's specific claim: UNSATISFIED — see §3 PB-13.)

`907e052` restructured `workers/data_worker.py::_process_csv_file_async`. The landed shape is
**two ordered commits** in the production branch:

1. `await _update_processing_log_status(..., status=ProcessingStatus.PROCESSING, ...)` with
   **no `session=` argument** — it opens its own short-lived session and commits, *before* the
   lock is taken. The in-source comment states the reasoning: the lock is transaction-scoped,
   so a commit after taking it would release the exclusion, and a PROCESSING write inside the
   main transaction would be invisible to every other connection.
2. `async with get_session() as session: async with session.begin():` →
   `acquire_dashboard_rebuild_lock(session, dashboard_id, task_id=task_id)` →
   `_run_with_transaction(session)`, so **COMPLETED commits together with the aggregate write**.

The test branch (`db_session is not None`) mirrors the PROCESSING write but inside the caller's
SAVEPOINT — `907e052` explicitly documents that a durable commit there would release the
SAVEPOINT and defeat the fixture's teardown rollback.

**What B3 did NOT change (and what PB-1 / PB-14 are actually for):**

- `data_worker.py::_update_processing_log_status` still **ignores `rowcount`** and logs
  `"Processing log updated"` unconditionally, for every status including terminal FAILED.
  DP-001 is untouched.
- `services/file_processing.py::process_upload_with_session` still calls
  `enqueue_job(processing_func, ...)` **before** `await db.commit()`, and the comment still
  reads *"Enqueue job BEFORE commit for proper transaction atomicity"* — a statement that is
  self-contradictory (an RQ enqueue is not transactional with Postgres). DP-001 is untouched.
- `data_worker.py::_run_with_transaction` still `unlink()`s the input file inside the
  transaction body, before the `COMPLETED` update. DP-016 is untouched.
- Both `except Exception` handlers in `_process_csv_file_async` are unchanged. DP-016 untouched.
- `app.py::lifespan` still calls `mark_orphaned_uploaded_logs_failed()` at **two** boot sites,
  each lease-guarded, still `logger.warning` on failure.
- `core/reconciler_lease.py::ReconcilerLease` is present and unchanged in shape
  (`LEASE_KEY`, `DEFAULT_LEASE_TTL_SECONDS = 90`, `ACQUIRE_TIMEOUT_SECONDS = 2.0`, owner-checked
  Lua renew/release, fail-open `UNREACHABLE` vs `NOT_ACQUIRED` distinction).

### 2.2 PB-5 blocker — phase-03 B2

**Verdict: SATISFIED.**

`ab76989` landed `db/advisory_lock.py` with `acquire_dashboard_rebuild_lock` and
`is_lock_timeout_error`; `863b81b` hardened the `lock_timeout` guard so it is non-vacuous.
The lock is taken **inside** `session.begin()` in `_process_csv_file_async`, before
`_run_with_transaction`. `tests/test_advisory_lock.py` (212 lines) and `tests/test_migration_lock.py`
(154 lines) both exist.

**PB-5's own premise is unchanged**, and this is the material part: **`_store_aggregates` still
has its `db_session is None` branch**, which opens **its own session** and therefore bypasses the
advisory lock entirely. In that branch the aggregate write and the COMPLETED status update are
two independent transactions on two independent connections. B2 made the *normal* path safe; it
did not close this hole. D-05-H(b) (delete the branch) should be read as a security-relevant
cleanup, not a tidiness option.

### 2.3 PB-16 blocker — phase-03 B3 / B10

**Verdict: SATISFIED for B10. PARTIALLY SATISFIED for B3 — B3 already corrected some of the
documentation PB-16 was written to correct.**

`7feb3b6` landed a +151-line rewrite of `docs/06-backend/architecture.md`. That file exists, is
substantial, and now describes the two-commit worker shape. PB-16's C05-6 "refresh
architecture.md if needed" is a small delta, not the main work.

`907e052` also touched `docs/00-overview/data-flow.md`, `docs/03-processing/processing-api.md`
and `docs/07-frontend/upload-ui.md`. Consequently the plan's PB-16 defect table is **already
partly stale**:

- `docs/03-processing/processing-api.md` — the plan's row says this file shows
  `"started → uploaded → processing → success/failed"` and `ProcessingStatus.SUCCESS`.
  **At HEAD the lifecycle line reads `started → uploaded → processing → completed/failed`,** and
  the status table lists exactly STARTED / UPLOADED / PROCESSING / COMPLETED / FAILED, followed by
  two paragraphs describing B3's own-commit-then-main-commit shape. That row is **corrected**.
- `docs/00-overview/data-flow.md` — the plan's row says the status-tracking bullet is stale.
  **At HEAD it already documents** "The `processing` state is committed in its own transaction
  before the work starts and the terminal state commits with the aggregate write afterwards".
  That sub-claim is **corrected**.

**Still-standing PB-16 defects are listed in §3, PB-16.**

### 2.4 Phase-04 authentication interference

**None detected on the code paths phase 05 owns.** Every phase-04 commit touches
`services/auth_service.py`, `core/security.py`, `core/rate_limit.py`, `api/routes/auth.py`,
`api/routes/admin.py` (password-reset paths only), `services/user_service.py` and auth docs.
`git diff --name-only b646ef1..HEAD -- src/` shows no change to any file phase 05 edits except
the phase-03 ones. The single interaction point is **`docs/SPEC.md`**, whose version-row table has
grown a phase-04 row — PB-16's C05-8 append must merge, not overwrite, that table.

## 3. Per-block reality check (PB-0 … PB-16)

Format: **plan's assumption → what HEAD actually is.** Everything below is read-only verification.

### PB-0 — untracked bookkeeping, no commit

Fully valid. Both audit files named in the plan's frontmatter **exist**:
`.ai/audit/99-validation/05-data-pipeline-validated-findings.md` and
`.ai/audit/05-data-pipeline/findings.md`. `tests/test_file_processing.py` **does not exist**, so
the "delete it if it appears" DoD item is already satisfied. PB-0's governance set
(`.ai/audit/00-reconciliation/session-continuity.md`, `decision-log.md`, `evidence-index.md`,
`validation-index.md`) does not exist and must be created. One note: the template
`.ai/audit/templates/audit-final-report.md` is among the pre-existing deletions;
`.ai/audit/templates/audit-findings.md` survives. PB-0's deliverable is a single findings note,
not a final report, so this is cosmetic. **Executable as written.**

### PB-1 — rowcount guard + enqueue-after-commit

Every premise holds. `data_worker.py::_update_processing_log_status` still discards `rowcount`.
`file_processing.py::process_upload_with_session` still enqueues before `await db.commit()` with
the false "for proper transaction atomicity" comment. `DataService.trigger_processing` still has
**no route caller** — the only references are `interfaces/service_interfaces.py:455` (declaration)
and `services/data_service.py:255` (implementation), verified by repo-wide grep.

**Two corrections to the plan's test table.**
1. The plan says "six enqueue patch sites" in `tests/test_data_service.py`. The count is six but
   the **split matters**: three sites patch `mkobi.services.file_processing.enqueue_job` (the RQ
   seam DP-001 reorders) and three patch `mkobi.services.data_service.enqueue_processing_job`
   (the module-level wrapper, which PB-1 does not touch). Only the first three are PASS_TO_PASS
   hazards.
2. `tests/test_data_worker.py::TestConcurrentAppendUploads` and
   `::TestConcurrentAppendUploadsIntegration` exercise the full production worker path. Whether
   they patch the submission seam at all **must be established before PB-1 starts** — B3 landed
   without breaking them, which suggests they intercept at the job-function level, but the plan
   does not list them and an Implementor would not check.

The three `mock_session.commit.assert_not_called()` sites in `tests/test_data_worker.py` are
intact. **Executable as written, with the test table corrected.**

### PB-2 — `metric_agg` read shape; `ProcessingSettingsDict`; single aggregation function

**Yes** — `_run_with_transaction`'s `settings = processing_config_dict.get("settings", processing_config_dict)`
fallback is still present verbatim. **Yes** — *both* `metric_agg` reads in `_store_aggregates`
are still `(processing_config_dict or {}).get("settings", {}).get("metric_agg", "sum")`.
**Yes** — `models/enums.py::AggregationFunctionEnum` declares exactly 10 members
(`sum, mean, count, min, max, median, std, var, first, last`) and
`data/processing/aggregate_transforms.py::AGG_FUNC_MAP` implements all 10.

**The plan's producer-side story is confirmed, and I can pin it exactly.**
`ProcessingConfigService._merge_metric_agg_into_settings` writes `metric_agg` **into** `settings`
before persisting; `get_by_dashboard_id` extracts it back out to the response's top-level field via
`_extract_metric_agg_from_settings` while leaving it in `settings`; and
`DataService::_execute_upload` does `processing_config = dict(config_response.settings)`. So
`processing_config_dict` **does** carry `metric_agg` at top level, and the correct read is
`.get("metric_agg", "sum")` — exactly the plan's fix. (Note for the Implementor:
`_extract_metric_agg_from_settings` silently drops a non-`str` value, so a hand-written
`settings.metric_agg = 5` survives in the DB but never reaches the response.)

**One test the plan does not list:** `tests/test_aggregation_service.py::TestAggregationService::test_aggregate_for_dashboard_unknown_agg_falls_back_to_sum`
**encodes DP-018's silent fallback as expected behaviour.** Under D-05-H(b) (delete) it must be
rewritten to assert the raise; under D-05-H(c) it stays. The plan says only "update with the
ruling" without naming it — an Implementor will miss it.

**PB-2 executable; D-05-G(b) remains open** — and note `ProcessingSettingsDict` is a
`TypedDict` with `total=False` and **no** `extra="forbid"`, so nothing rejects an unknown key at
the Pydantic boundary.

### PB-3 — `save_aggregates` early return; `save_filter_values` coercion

**Yes** — `data/storage/manager.py::StorageManager.save_aggregates` still early-returns on
`if not aggregates:` **before** its own `delete_by_dashboard`.
**Yes** — both `str_values = [str(value) for value in fvalues]` sites still exist, in
`data_worker.py::_store_aggregates` and `::extract_filter_values`.
**No** — `tests/test_storage_manager.py` has **no** `save_aggregates` coverage. It covers only
`clear_graph_data`, `clear_dashboard_data`, `clear_graph_data_compat`, `clear_dashboard_data_compat`
and `save_aggregated_data` (deprecated).

**Correction:** the plan's framing "a `save_aggregates` unit test on its own, which does not exist
today" is true of that file but **false at repo level**.
`tests/test_data_service.py::TestJsonbKeyNormalization` contains
`test_save_aggregates_dims_keys_are_sorted` and `test_save_aggregates_nested_dims_keys_are_sorted`
— real integration coverage of `save_aggregates` and `_normalize_json_keys`, in a different file.
These are PASS_TO_PASS for PB-3 and PB-5 and are **absent from the plan's PASS_TO_PASS table**.

### PB-4 — `groupby_cols` de-duplication

**Yes** — `services/aggregation_service.py::AggregationService.aggregate_for_dashboard` builds
`groupby_cols` at the graph loop with no de-duplication, then calls
`df.group_by(groupby_cols).agg(...)`. **`dict.fromkeys` does not appear anywhere in the file**
(verified by grep) — the plan's question is answered: it is not there.

Documentation impact confirmed **none**: `docs/11-guides/extend-graphs-filters.md` contains no
claim that dimension names must be distinct. PB-4's Doc impact `None` stands.
`tests/test_aggregation_service.py` has no de-duplication test, so there is no current
characterisation to update. **Executable as written.**

### PB-5 — conflict targets, key canonicalisation, dim typing, status enum

All four anchors are **unchanged**:
- `db/models/aggregated_data.py::AggregatedData.__table_args__` still declares index
  `uq_aggregated_data_dashboard_graph_dims` over `text("dims::text")`, and both
  `text("((dims)::text)")` conflict targets in `data/storage/manager.py::StorageManager.upsert_aggregate`
  and `::_bulk_upsert` are byte-identical.
- `StorageManager._normalize_json_keys` still sorts keys only.
- `StorageManager._coerce_dim_value` still preserves native scalars.
- **`processing_logs.status` is a native PostgreSQL ENUM.** `db/models/processing_logs.py` declares
  `Enum(ProcessingStatus, name="processing_status", values_callable=...)`, and
  `alembic/versions/000000000000_initial_migration.py` creates the type with
  `processing_status_enum.create(op.get_bind(), checkfirst=True)`.

**This answers the open Auditor task in PB-5: D-05-F(a) (new `GRAPH` status) requires an Alembic
migration**, confirming the plan's phase-14 routing and R-05-7. **Executable as written.**

### PB-6 / PB-7 — `pl.all().first()`; step order

**`pl.all().first()` is still the only occurrence in the entire repository** (verified across
`src/` and `tests/`: exactly one hit, `data/processing/transformations.py`, inside
`apply_transformations`'s groupby-without-aggregations branch). Nothing under `tests/` asserts on it.

`apply_transformations`' step order is **unchanged and exactly as the plan states**:
filters → groupby → sort → limit → computed fields → rename → dtypes.
`tests/test_data_transformations.py` contains `TestApplyTransformations::test_transformations_with_groupby`
and `::test_transformations_with_limit`, which is the file PB-6/PB-7 must update. **Executable as written.**

### PB-8 — cast guard; orphan model; `ProcessingSettingsDict`; config

**Yes** — `_run_with_transaction` order is still validate → decimal separator → cast → rename →
computed fields → transform → aggregate. **Yes** — the cast guard
`if col_name in df.columns and col_type != "float":` still has **no `else`** and still skips `float`
unconditionally.
**Yes** — `models/types.py::ProcessingSettingsModel` is still orphaned: zero references outside its
own definition. **Yes** — `ProcessingSettingsDict` is still a `TypedDict`.

**Three corrections.**
1. **"Six references" is understated roughly two-fold.** There are **12 usage sites across 3
   files**: `interfaces/service_interfaces.py` (3), `services/processing_config_service.py` (7),
   `models/processing_configs.py` (2) — 14 lines counting the three imports. The blast radius PB-8
   quotes is wrong; the count an Implementor would budget from is wrong.
2. **`interfaces/service_interfaces.py` is CLEAN.** See §2.0. The whole "preserve the uncommitted
   changes" DoD clause for this block is void.
3. **`config.py` is CLEAN and is not under active phase-01 work.** It gained +62 lines since
   `b646ef1`, but `git diff b646ef1..HEAD -- src/mkobi/config.py` shows the additions are phase-03's
   advisory-lock and migration-lock settings. No phase-01 work is in flight on it.

**One of the plan's own justifications is wrong.** PB-8 argues that a unified
`ProcessingSettingsModel` would be strict "because `TransformationConfig` already uses
`extra='forbid'`". `models/transformation_configs.py::TransformationConfig.model_config` does set
`extra="forbid"` — the precedent is real — but `ProcessingSettingsDict` has no such field, so the
comparison does not by itself make the option safe.

**And the D-05-G(a) tripwire does not exist.** `tests/test_openapi.py` (27 lines) contains exactly
three tests, all about `ErrorResponse` model schema generation. It asserts nothing about route
response declarations, so a new 422 on a documented route would **not** trip it. PB-8 must either
add that assertion or stop citing it as a gate. **Executable after these corrections.**

### PB-9 — `ValidationResult.warnings`

The plan says `warnings` has "no consumer anywhere in `src/`". Precisely: the **only** reader in
`src/` is `data/loaders/validator.py::DataValidator.get_validation_summary` — and that method
itself has **no production caller** (tests only, in `tests/test_data_validator.py`). So the
conclusion holds but the wording does not, and the difference is operationally relevant: PB-9's
"delete the dead path" must **not** delete `get_validation_summary`, which is live public API with
four tests. `_validate_column_types` still only ever `warnings.append` — confirmed. `processing_status`
is a native PG enum — confirmed (see PB-5). **Executable; D-05-F is decided.**

### PB-10 — `calculate_aggregations` call sites; ungrouped YoY

**Yes** — all three call sites in `data_worker.py::_run_with_transaction` pass
`df.transformation_configs` (a Pydantic model). **Yes** — `_calculate_yoy` uses a bare
`pl.col(value_column).shift(shift_lag)` when `group_cols` is falsy, with no `.over(...)`. Confirmed
at `data/processing/aggregate_transforms.py::AggregationTransformer._calculate_yoy`.
`tests/test_data_transformations.py::TestCalculateYoY` has `test_yoy_with_group_cols` but **no
group-less test** — consistent with D-05-P's unreachability argument (the `yoy_config` fields are
absent from `ProcessingSettingsDict`). **Executable as written.**

### PB-11 — error classification

**Both classifiers are still substring-only.** `data_worker.py::_map_processing_error_to_code`
matches on `error_text` membership (`"is being uploaded"`, `"already being processed"`,
`"lock timeout"`); `api/routes/upload.py::_handle_value_error` matches on
`"exceeds maximum allowed"`, `"rate limit"`, `"too large"`, `"permission"`, `"invalid"`.

**Two factual corrections to the plan.**
1. `CSVLoader.load_csv` **does not** destroy the `FileNotFoundError` type. In
   `data/loaders/loader.py::CSVLoader.load_csv`, `_validate_file_type` (which raises
   `FileNotFoundError`) and `_validate_file_size` are called at lines 119 and 122 — **before** the
   blanket `try:` at line 132. So `FileNotFoundError` propagates unwrapped, and
   `_map_processing_error_to_code`'s `isinstance(error, FileNotFoundError)` branch **is reachable**.
   `tests/test_data_csv_loader.py::TestCSVLoaderLoadCSV::test_load_csv_file_not_found` corroborates.
2. D-05-A(b)'s premise is **wrong**: the plan states the consumer "hits `FileNotFoundError`, which
   `_map_processing_error_to_code` currently maps to `"encoding"`". Current code maps
   `FileNotFoundError` → `ErrorCode.FILE_UPLOAD_ERROR`. The `encoding` branch is the
   `UnicodeDecodeError` branch. **PB-11 needs its problem statement corrected before dispatch.**

### PB-12 — lazy loading and the ceiling

**Yes** — `CSVLoader._read_csv_lazy` still ends with `pl.scan_csv(...).collect()`, so there is no
lazy mode at all. **Yes** — `data_worker.py` still constructs `CSVLoader()` with **no argument**,
so the worker's ceiling is the `LoaderConfig.max_file_size` default. **Yes** — that default is
still the literal `100 * 1024 * 1024` in `models/data.py::LoaderConfig`.

**`config.py` keys relevant to upload size / lazy threshold, at HEAD:**
`UploadSettings.max_file_size_mb = 100`, `UploadSettings.lazy_threshold_mb = 10.0`,
`UploadSettings.allowed_file_types`; plus `logs_retention_days`, `stale_file_threshold_hours`,
`stale_processing_timeout_minutes = 30`, `settings.stale_processing_cleanup_interval_seconds`,
and the phase-03 advisory/migration lock settings. **PB-12 executable as written.**

### PB-13 — orphan sweep and its new caller

**The plan's central premise here is FALSE at HEAD.** The `timedelta(minutes=1)` literal
`a215a40`/`907e052` replaced is **gone**. `data_worker.py::mark_orphaned_uploaded_logs_failed`
now computes `horizon = timeout_minutes if timeout_minutes is not None else
get_config().stale_processing_timeout_minutes` and then
`cutoff = datetime.now(UTC) - timedelta(minutes=horizon)`, with a new keyword-only
`timeout_minutes: int | None = None` override and a rewritten docstring explaining that the
UPLOADED marker and the periodic PROCESSING sweep must share one horizon.

**Consequences.**
- R-05-3 ("PB-13 must not touch the literal, must not re-apply the change") is **moot** — the
  change phase-03 C-3 authorised has already been applied. Phase 03 option (a) (read the key) is
  now the only live option; (b) (dedicated `STALE_UPLOADED_TIMEOUT_MINUTES`) is moot;
  (c) (document the key's other consumer) is partially discharged — the key now has two consumers
  and the docstring already says so.
- The sweep is no longer "boot-time only": the periodic reconciler
  (`start_stale_processing_cleanup_task` → `cleanup_stale_processing_logs`) also runs. `907e052`
  plus `a215a40` landed two new tests pinning the horizon
  (`test_mark_orphaned_uploaded_logs_failed_uses_the_configured_stale_processing_horizon`,
  `test_mark_orphaned_uploaded_logs_failed_explicit_override_wins`).
- **The plan's hard verification requirement is wrong.** It says `tests/test_app_lifespan.py` has
  **six** `mark_orphaned_uploaded_logs_failed` patch sites and instructs the Implementor to "verify
  the count is six before and after". The file has **five** (the `TestLifespanTeardown`,
  `TestLifespanLeaseGuard` and `TestLifespanTeardownFailIsolation` cases). A Implementor following
  this literally reports a false discrepancy.

**PB-13 needs rewriting before dispatch.** The block is still meaningful — the production caller
is still boot-only, which R-05-4 says is correct — but its problem statement, its ruling options
and its verification gate are all written against a tree that no longer exists.

### PB-14 — file lifetime and the uncalled helpers

All four anchors hold.
`data_worker.py::_run_with_transaction` still `unlink()`s the input file **inside** the
transaction body, before the `COMPLETED` update. Both `except Exception` handlers in
`_process_csv_file_async` are unchanged. `services/file_cleanup.py::cleanup_task_files` and
`::cleanup_old_processing_logs` have **zero production callers** (verified repo-wide: the only
references are `tests/` and audit documents); `cleanup_stale_temp_files` has exactly two —
`db/starter.py::DatabaseStarter.startup` and `tests/conftest.py`.

Two precision notes. `tests/conftest.py::pytest_sessionfinish` is a **pytest hook**, not a
session-scoped fixture — same net effect, wrong mechanism to hand an Implementor. And
`tests/test_upload_api.py::test_cleanup_task_files_called_during_processing` exists and drives
`process_csv_background` while asserting on the directory; it names a function with **no
production caller**. The phase-05 plan does not mention it at all; the phase-06 plan names it and
assigns it to **phase 05 under D-05-J**. **PB-14 executable, but D-05-J must be extended to
include that test, and the "preserve the uncommitted changes" DoD item dropped.**

### PB-15 — deterministic read order

Confirmed unchanged. `db/repositories/aggregated_data_repo.py` — `get_by_dashboard_id`,
`get_by_graph_id` and `get_dims_values` all issue `select(...)` with a `where` and **no
`order_by`**. `db/models/aggregated_data.py::AggregatedData` has **no `ordinal` column**; its
`id` is an autoincrementing primary key. **Executable as written** — this is the cleanest block
in the plan.

### PB-16 — documentation defects

**Still wrong, and the set is larger than the plan's table.**

| File | Defect at HEAD |
|---|---|
| `docs/00-overview/data-flow.md` | Diagram line: "Processing task queued (TaskQueue)"; bullet: "in-memory `TaskQueue` for MVP; Redis + RQ for production"; "Transaction safety: File move to final path occurs **after** DB commit ... On commit failure, the file remains at the temp path" (contradicted by `process_upload_with_session`); "Full recalculation (all aggregates rebuilt)" (two occurrences) |
| `docs/09-database/enums.md` | Claims `ProcessingStatus` = `started, uploaded, processing, success, failed, completed` (member list ×2, code block, lifecycle table, summary table). Actual: 5 members, **no `success`**. *Phase 14's by C05-6.* |
| `docs/09-database/schema-processing.md` | `processing_status` ENUM listing includes `success`; lifecycle chain `started → uploaded → processing → success → completed`. *Phase 14's by C05-6.* |
| `docs/04-admin/admin-api.md` | `status_filter` documents `success` as accepted; example response `"status": "success"`; capabilities list repeats it. *PB-16's — the plan names the file but this is the specific content.* |
| `docs/03-processing/task-queue.md` | Entire file describes the in-memory `TaskQueue`, `default_queue`, `get_task_queue()`, `process_next()`, `ProcessingStatus.SUCCESS`. **CONFLICT — see below.** |
| `docs/03-processing/processing-api.md` | "The current implementation uses an in-memory `TaskQueue` (MVP)" (line ~158) and an example response `"status": "success"` — **neither is in the plan's table.** The status table and lifecycle line the plan *does* list were already corrected by `907e052`. |
| `docs/SPEC.md` | line ~121: "**Background task queue** — In-memory `TaskQueue` (MVP) with a documented migration path to Redis/RQ"; line ~104 links the migration guide. **Not in the plan's table at all.** |

**Cross-phase conflict.** `docs/SPEC.md`'s version-row 3.13 (landed by phase 02) states that the
now-obsolete plan text in `docs/03-processing/task-queue.md` "**is owned by audit phase 10**
(`OPS-002` … phase 01 owns the architectural decision, **phase 10 owns the documentation
correction**)". The phase-05 plan's C05-3 assigns that same file to **PB-16**. Two committed plans
now claim the same file. This is a Coordinator-level routing decision, not an Implementor's.

**PB-16's grep DoD is unsatisfiable as written.** It requires the repository-wide grep to return
"only the two historical files". At HEAD it also matches `docs/SPEC.md` and
`docs/03-processing/processing-api.md`, and — because C05-6 correctly routes
`docs/09-database/enums.md` and `docs/09-database/schema-processing.md` to phase 14 — the
`ProcessingStatus.SUCCESS` grep returns those two files too. The DoD contradicts the plan's own
routing decision. **PB-16 needs rewriting.**

## 4. Test-surface census

All 28 files the plan names **exist**, except `tests/test_file_processing.py`, which the plan
requires to be absent — **it is absent**. 62 `test_*.py` files exist in `tests/` in total.

| File | Exists | Current coverage, as read at HEAD |
|---|---|---|
| `tests/test_upload_api.py` | yes (878) | Upload route incl. `test_upload_submits_job_with_correlated_task_id`, `test_upload_submission_failure_is_rfc7807`, and `test_cleanup_task_files_called_during_processing` — which names a function with **no production caller**. |
| `tests/test_rq_worker.py` | yes (277) | `TestRQWorkerRetry`, `TestQueueNameAgreement`, `TestStartRQWorker`, **`TestRegisteredJobCallable`** (source-inspects `enqueue_processing_job` for `process_csv_background_sync` and matches kwargs to the sync callable's signature), `TestCheckWorkerRegistered`. |
| `tests/test_data_service.py` | yes (979) | `TestDataServiceIntegration`, `TestProcessingStatusLifecycleIntegration`, `TestFileValidation`, **`TestJsonbKeyNormalization`** (two real `save_aggregates` tests), `TestConcurrentAppendUploads`. 6 enqueue patch sites, split 3 `file_processing.enqueue_job` / 3 `data_service.enqueue_processing_job`. |
| `tests/test_data_worker.py` | yes (1160) | `TestReconcilerLoop`, `TestReconcilerLeaseOwnership`, `TestDataWorker` (incl. exactly **three** `mock_session.commit.assert_not_called()`), `TestProcessingErrorClassification`, `TestValidateProcessingConfig`, `TestStoreAggregates`, `TestConcurrentAppendUploads(+Integration)`. **New in B3:** two horizon tests for `mark_orphaned_uploaded_logs_failed`. |
| `tests/test_e2e_upload.py` | yes (288) | `TestE2EUploadWorkflow` — 3 tests: overwrite mode, log status transitions, multiple graphs on one dashboard. |
| `tests/test_storage_manager.py` | yes (176) | **Only** `clear_graph_data`, `clear_dashboard_data`, both `*_compat` deprecation shims, `save_aggregated_data` (deprecated). **No `save_aggregates` coverage.** |
| `tests/test_aggregation_service.py` | yes (430) | `aggregate_for_dashboard` across mean/min/max/count, chart sorting, `extract_filter_values`. **Includes `test_aggregate_for_dashboard_unknown_agg_falls_back_to_sum`, which encodes DP-018 as expected behaviour.** No `groupby_cols` de-duplication test. |
| `tests/test_filter_values_consistency.py` | yes (282) | 2 tests: filter values after overwrite, after append. |
| `tests/test_filter_persistence.py` | yes (280) | 3 tests: endpoint returns available values, persistence across navigation, cleared on new upload. |
| `tests/test_enum_db_consistency.py` | yes (198) | `TestUserRoleEnumConsistency`, `TestDashboardPermissionEnumConsistency`, **`TestProcessingStatusEnumConsistency`** (queries the live `processing_status` type), `TestAllMappedEnumsConsistency`. This is the file that makes D-05-F(a)'s migration mandatory. |
| `tests/test_app_lifespan.py` | yes (246) | `TestLifespanSourceHasNoQueueWorker`, `TestLifespanTeardown`, `TestLifespanLeaseGuard`, `TestLifespanTeardownFailIsolation`. **Five** `mark_orphaned_uploaded_logs_failed` patch sites. |
| `tests/test_health.py` | yes (194) | Health endpoint shape. Untouched by phase 05. |
| `tests/test_file_cleanup.py` | yes (540) | Grew by +141/+2 lines in `907e052`/`a215a40`; includes `TestProcessingFailureReportedOnOwnSession`. |
| `tests/test_data_transformations.py` | yes (621) | 8 classes: formula parsing, `ApplyFilters`, `AddComputedFields`, `ApplyDtypes`, **`ApplyTransformations`** (incl. `test_transformations_with_groupby`, `..._with_limit`), `CalculateAggregations`, `CalculateYoY` (grouped only), `CalculateShare`, `AggregateData`. |
| `tests/test_mime_validation.py` | yes (279) | Genuine/spoofed CSV and gzip, empty file, binary-with-csv-extension, plus unit tests for detection and validation. |
| `tests/test_streaming_size_limit.py` | yes (314) | 5 tests: within limit, exceeds → 413, temp file cleaned after rejection, cumulative check when no content-length, client-declared size honoured. |
| `tests/test_task_queue.py` | yes (115) | `TestQueueReceivesJob` (live RQ round-trip), **`TestRetiredSymbolsRemoved`** (parametrised over `TaskQueue`, `default_queue`, `get_task_queue`), `TestServicesDoNotImportRq` (AST scan). |
| `tests/test_error_response_format.py` | yes (163) | RFC 7807 shape across 400/401/403/404/500. |
| `tests/test_openapi.py` | yes (27) | **Only 3 tests, all about `ErrorResponse` schema generation.** Asserts nothing about route response declarations — see §3 PB-8. |
| `tests/test_pydantic_models.py` | yes (418) | Pydantic v2 model validation. |
| `tests/test_data_csv_loader.py` | yes (379) | 8 classes incl. `test_load_csv_lazy_threshold_respected`, `test_load_csv_file_not_found`, `_validate_file_size` within/over limit. |
| `tests/test_data_validator.py` | yes (317) | `validate`, each `_validate_*`, and **`get_validation_summary`** (4 tests) — the only reader of `ValidationResult.warnings`. |
| `tests/test_validators.py` | yes (198) | Filter/validator unit coverage. |
| `tests/test_processing_logs.py` | yes (724) | Grew by +257/+118 in `907e052`/`a215a40`. |
| `tests/test_data_endpoint.py` | yes (169) | `/data/aggregated` route. |
| `tests/test_repositories.py` | yes (578) | Repository-level coverage. |
| `tests/test_config.py` | yes (1085) | Settings/env parsing. Clean at HEAD. |
| `tests/conftest.py` | yes (616) | **`async_session_maker` EXISTS** (`scope="session"`). Also `pytest_sessionfinish` → `cleanup_stale_temp_files(max_age_hours=0)`; `_auto_mock_redis` is `autouse` and patches Redis for every test by default. |
| `tests/test_file_processing.py` | **no** | Correctly absent — PB-0's DoD item is satisfied. |
| `tests/test_advisory_lock.py` | yes (212) | Phase-03 B2. Not named by the plan; relevant as PB-5's sibling evidence. |
| `tests/test_migration_lock.py` | yes (154) | Phase-03 B9. |

## 5. Test baseline feasibility

**Docker is reachable in this environment.** Server `29.8.0`, linux. The `mkobi-test` project is
already up and healthy (`mkobi-test-test-db-1`, `mkobi-test-test-redis-1`, both 10h healthy); the
dev stack (`mkobi-app-1`, `mkobi-db-1`, `mkobi-redis-1`, `mkobi-rq-worker-1`, `mkobi-frontend-1`) is
also running. **No blocker found.** The suite was **not** run, per instruction.

**Entry points** (`Makefile.ps1`, single `switch` dispatch, no GNU `make`):

| Purpose | Target |
|---|---|
| Start test services | `.\Makefile.ps1 test-up` |
| Full suite | `.\Makefile.ps1 test` (also `test-all`, `test-fresh`, `test-select -k <expr>`, `test-shell`) |
| Stop / reset | `test-down`, `test-reset`, `test-ps`, `test-logs` |
| Gates | `lint`, `format`, `typecheck`, `fe-lint`, `fe-test`, `check` |
| Dev stack | `up`, `down`, `restart`, `ps`, `logs`, `shell`, `exec`, `build`, `rebuild`, `dev-watch` |
| Migrations / DB | `migrate`, `migration-new`, `migration-status`, `psql`, `psql-c`, `backup`, `restore`, `prune-backups` |
| Diagnostics | `doctor`, `config`, `config-test`, `open` |
| Cleanup | `clean`, `fullclean`, `nuke` |

Practical notes for the Coordinator: `tests/conftest.py` creates and migrates the test schema
itself, so there is no separate migrate step on the test path; the `mkobi_app` role must pre-exist
(if pytest reports `role "mkobi_app" does not exist`, run `test-reset`); and because
`_auto_mock_redis` is autouse, any new test that needs a real broker must opt out explicitly.

**`models/enums.py::ProcessingStatus` — current members (5):**
`STARTED = "started"`, `UPLOADED = "uploaded"`, `PROCESSING = "processing"`,
`COMPLETED = "completed"`, `FAILED = "failed"`.
**There is no `SUCCESS`.** `valid_transitions()` documents `STARTED → UPLOADED → PROCESSING →
COMPLETED/FAILED`. `processing_logs.status` is backed by a native PostgreSQL `processing_status`
ENUM created in `alembic/versions/000000000000_initial_migration.py` and reshaped in
`4479eb53fd4e_remove_unused_success_value_from_.py` — that migration's title is the strongest
single piece of evidence that DP-014's `success` documentation drift is long-standing.

## 6. Decision-record status

| Record | Status at HEAD | Note |
|---|---|---|
| **D-05-A** | **Open** — mechanism decision | But the sub-premise (b) is factually wrong: `FileNotFoundError` maps to `FILE_UPLOAD_ERROR`, not `"encoding"`, and it is *not* wrapped by `CSVLoader.load_csv`. Fix the premise, then rule. |
| **D-05-B** | **Open** | Nothing landed. |
| **D-05-C** | **Open** | Nothing landed. |
| **D-05-D** | **Open** | Nothing landed. |
| **D-05-E** | **Open** | Nothing landed. |
| **D-05-F** | **Decided by the tree** — `processing_status` is a native PG ENUM and `4479eb53fd4e` already removed `success` | The PB-5/PB-9 "Auditor" task is discharged: any new member (e.g. `GRAPH`) needs an Alembic migration. Routing to phase 14 is correct. |
| **D-05-G** | **Open**, and the stated tripwire does not exist | `tests/test_openapi.py` tests `ErrorResponse` schema only. PB-8 must add a route-declaration assertion or drop the gate. |
| **D-05-H** | **Open**, and now **more urgent** | The `db_session is None` branch in `_store_aggregates` bypasses B2's advisory lock and splits the aggregate write from the COMPLETED update across two connections. D-05-H(b) (delete) should be preferred over (a) (fix both). |
| **D-05-I** | **Partially moot** | (b) dedicated `STALE_UPLOADED_TIMEOUT_MINUTES` and the `timedelta(minutes=1)` premise are moot — `907e052` already reused `Settings.stale_processing_timeout_minutes`. Only (c) "document the key's other consumer" survives, and the docstring already does it. |
| **D-05-J** | **Open, and under-scoped** | The ruling must also cover `tests/test_upload_api.py::test_cleanup_task_files_called_during_processing`, which phase 06's plan assigns to phase 05 but phase 05's plan never names. |
| **D-05-K** | **Open** | Nothing landed. |
| **D-05-L** | **Open** | Nothing landed. |
| **D-05-M** | **Open** | Nothing landed. |
| **D-05-N** | **Open** | Nothing landed. |
| **D-05-O** | **Open** | Nothing landed. |
| **D-05-P** | **Open** — unreachability argument **strengthened** | `ProcessingSettingsDict` still declares no `yoy_config` / `share_config` / `metrics` fields, and `ProcessingConfig` has `yoy_config` but `models/types.py` does not. `tests/test_data_transformations.py::TestCalculateYoY` still has grouped-only coverage. |

## 7. Discrepancies and risks (prioritised)

Ordered by how much damage an Implementor trusting the plan blindly would do.

**P1 — PB-13's central premise is void; the block would undo or double-apply landed work.**
`907e052` replaced `timedelta(minutes=1)` with `get_config().stale_processing_timeout_minutes`
plus a `timeout_minutes` override. R-05-3 ("PB-13 must not touch the literal, must not re-apply
the change") protects against a change that has already landed; the block's ruling options (b) and
the premise of (c) are moot. Separately, the block's hard verification gate — "verify the count is
six before and after" — is wrong: `tests/test_app_lifespan.py` has **five**
`mark_orphaned_uploaded_logs_failed` patch sites. An Implementor following this literally reports
a phantom discrepancy or, worse, patches a sixth site into existence to make the gate pass.

**P2 — `docs/03-processing/task-queue.md` is claimed by two phases.** Phase-05 C05-3 assigns it to
PB-16. The committed `docs/SPEC.md` version row 3.13 (landed by phase 02) says the same file
"is owned by audit phase 10 (`OPS-002` … phase 10 owns the documentation correction)". Two live
plans claim one file. This is a Coordinator/owner ruling, not an Implementor's to guess.

**P3 — PB-16's grep DoD is unsatisfiable and, followed literally, would take phase 14's work.**
The DoD requires the retired-symbol grep to return "only the two historical files". At HEAD it also
matches `docs/SPEC.md` (lines ~104, ~121) and `docs/03-processing/processing-api.md` (~158) —
neither is in the plan's defect table. The `ProcessingStatus.SUCCESS` grep returns
`docs/09-database/enums.md` and `docs/09-database/schema-processing.md`, which C05-6 *correctly*
routes to phase 14. The gate as written cannot pass without stealing another phase's work.

**P4 — PB-16 would revert documentation phase 03 just corrected.** The plan's defect row for
`docs/03-processing/processing-api.md` says the file shows `"started → uploaded → processing →
success/failed"`. It does not: `907e052` already replaced that with the correct
`completed/failed` chain, a correct five-row status table, and two paragraphs describing B3's own
commit. Same for the `data-flow.md` status-tracking bullet. An Implementor "correcting" these to
the plan's text would re-introduce the `success` error into a file that is currently right.

**P5 — PB-11's problem statement is wrong about the mechanism, and D-05-A(b) is built on it.**
In `data/loaders/loader.py::CSVLoader.load_csv`, `_validate_file_type` (which raises
`FileNotFoundError`) and `_validate_file_size` are called **before** the blanket `try:`, so
`FileNotFoundError` is *not* wrapped — the `isinstance(error, FileNotFoundError)` branch in
`_map_processing_error_to_code` is reachable. The plan also states that branch "currently maps to
`encoding`"; it maps to `ErrorCode.FILE_UPLOAD_ERROR`. D-05-A(b) would be ruled against a false
model.

**P6 — PB-1's PASS_TO_PASS table is both incomplete and mis-split.** Only three of the six enqueue
patch sites in `tests/test_data_service.py` cross the RQ seam (`file_processing.enqueue_job`); the
other three patch `data_service.enqueue_processing_job`, which PB-1 does not touch. And
`tests/test_data_worker.py::TestConcurrentAppendUploads` / `::TestConcurrentAppendUploadsIntegration`
are not listed anywhere — they drive the full production worker path and are the most likely
collateral damage from moving the enqueue.

**P7 — PB-8's cited tripwire does not exist.** `tests/test_openapi.py` is 27 lines of three
`ErrorResponse` schema tests. It asserts nothing about route response declarations, so D-05-G(a)'s
"a new 422 on a documented route is OpenAPI-visible" gate will not trip. Either add the assertion
or stop citing it.

**P8 — PB-2 omits the test that encodes DP-018 as correct behaviour.**
`tests/test_aggregation_service.py::TestAggregationService::test_aggregate_for_dashboard_unknown_agg_falls_back_to_sum`
asserts the silent fallback. Under D-05-H(b) it must be rewritten to expect the raise; the plan
only says "update with the ruling" without naming the file.

**P9 — PB-3's "no `save_aggregates` test exists today" is true of one file but false repo-wide.**
`tests/test_data_service.py::TestJsonbKeyNormalization::test_save_aggregates_dims_keys_are_sorted`
and `::test_save_aggregates_nested_dims_keys_are_sorted` are real integration coverage of
`save_aggregates` and `_normalize_json_keys`. They are PASS_TO_PASS for PB-3 and PB-5 and are
absent from the plan's table.

**P10 — Four DoD items across PB-8, PB-10 and PB-14 are void.** "Preserve the uncommitted changes
in `api/deps.py` / `db/session.py` / `interfaces/service_interfaces.py`" describes phase-03 B1,
which landed in `2174895`. `git diff --stat -- src/ tests/ docs/` is empty. "`src/mkobi/config.py`
is under active phase-01 work" is also false — config.py is clean and its +62 lines since
`b646ef1` are phase-03's advisory/migration lock settings. Harmless in itself, but it implies a
merge hazard that does not exist and invites an Implementor to skip a real check.

**P11 — PB-8 understates `ProcessingSettingsDict`'s blast radius by roughly half.** There are
**12 usage sites across 3 files** (`interfaces/service_interfaces.py` ×3,
`services/processing_config_service.py` ×7, `models/processing_configs.py` ×2), not six. The
single most likely outcome of an under-budgeted refactor is a missed call site.

**P12 — PB-9's "zero consumers" wording would license the wrong deletion.** The only `src/` reader
of `ValidationResult.warnings` is `DataValidator.get_validation_summary`. It has no *production*
caller, so the conclusion holds — but it is a public method with four tests in
`tests/test_data_validator.py`. The correct finding is "reaches no production path", not "dead".

**P13 — PB-14 reasons about a transaction shape that B3 changed.** There are now **two** ordered
commits; the success-path unlink happens inside the second, *after* the first has already
published PROCESSING on its own connection. The rollback-safety argument is unaffected (nothing
overwrites the file), but the ordering context in which the unlink must be deferred has changed and
PB-14's text does not reflect it.

**P14 — PB-14/D-05-J is under-scoped.** `tests/test_upload_api.py::test_cleanup_task_files_called_during_processing`
names a function with no production caller. Phase 06's plan assigns it to **phase 05 under D-05-J**;
phase 05's plan never mentions it. Whichever way D-05-J rules, that test must follow.

**P15 — Name collision: `_add_computed_fields` exists in two modules.**
`data/processing/filter_transforms.py` (which the plan anchors for DP-009) and
`data/processing/aggregate_transforms.py` (which `workers/data_worker.py` imports and calls). Any
grep-driven edit hits both.

**P16 — `config.py::Settings.max_file_size` is a derived property, not a setting.** It returns
`self.upload.max_file_size_mb * 1024 * 1024`. PB-12's step-1 inventory lists it as a third
configurable ceiling; adding a knob there would create two sources of truth.

**P17 — `.ai/structure/` is deleted from the working tree.** `AGENTS.md` opens every agent with
`.ai\structure\map.md` and `.ai\structure**`; neither resolves. Any Implementor told to consult the
project structure map cannot. Not a phase-05 finding, but it is a live onboarding hazard while the
deletions persist.

**No phase-04 interference on code.** Every phase-04 commit touches auth surfaces only; none of
the files phase 05 edits were changed by phase 04. The one shared surface is `docs/SPEC.md`, whose
version table now carries a phase-04 row — C05-8 must merge rather than overwrite.

## 8. Net verdict: which blocks are executable as written, which need rewriting, which are blocked

| Block | Verdict | Reason |
|---|---|---|
| **PB-0** | **Executable as written** | Both audit files exist; `tests/test_file_processing.py` correctly absent. |
| **PB-1** | **Needs correction** | Premises all hold, but PASS_TO_PASS is mis-split (3 of 6) and `TestConcurrentAppendUploads(+Integration)` are missing. |
| **PB-2** | **Needs correction** | Code premise fully confirmed; the unknown-agg fallback test is not in the break table. D-05-G(b) still open. |
| **PB-3** | **Needs correction** | Code premise confirmed; `TestJsonbKeyNormalization` is unlisted PASS_TO_PASS; DP-005 work is verification-only. |
| **PB-4** | **Executable as written** | `groupby_cols` un-deduped, `dict.fromkeys` absent, no doc impact, no existing test to update. |
| **PB-5** | **Executable as written** | All four anchors byte-identical; `processing_status` confirmed a native PG ENUM. |
| **PB-6 / PB-7** | **Executable as written** | `pl.all().first()` sole repo occurrence; step order exactly as stated. |
| **PB-8** | **Needs correction** | Code premises hold; tripwire absent, reference count understated 2×, `service_interfaces.py` clean, config.py claim false. |
| **PB-9** | **Needs correction (light)** | Conclusions hold; "zero consumers" must become "no production path" or the wrong deletion follows. D-05-F decided. |
| **PB-10** | **Needs correction (light)** | All premises confirmed; only the void "preserve uncommitted" DoD item must be dropped. |
| **PB-11** | **Needs rewriting** | Problem statement is factually wrong on `FileNotFoundError` wrapping and on the `encoding` mapping. D-05-A(b) cannot be ruled until fixed. |
| **PB-12** | **Executable as written** | Lazy path, no-arg construction, and the 100 MB literal all confirmed; `Settings.max_file_size` is derived (see P16). |
| **PB-13** | **Blocked — needs rewriting** | Premise void (literal already replaced), ruling options (b)/(c) largely moot, and the six-patch-site gate is wrong (five). |
| **PB-14** | **Needs correction** | All four anchors hold; transaction context changed, D-05-J is under-scoped, "preserve uncommitted" is void. |
| **PB-15** | **Executable as written** | Cleanest block: no `order_by` on all three reads, no `ordinal` column. |
| **PB-16** | **Blocked — needs rewriting** | Cross-phase ownership of `docs/03-processing/task-queue.md`; unsatisfiable grep DoD; already-corrected doc rows would be reverted. |

**Aggregate: 8 executable as written (PB-0, 4, 5, 6, 7, 12, 15), 7 executable after a written
correction (PB-1, 2, 3, 8, 9, 10, 14), 2 blocked pending an owner decision (PB-13, PB-16).**

**Blocking decisions only the Coordinator/owner can take, in priority order:**
1. Which phase owns `docs/03-processing/task-queue.md` — this plan's PB-16 or phase 10's `OPS-002`.
2. Whether PB-16's grep DoD is rewritten to be satisfiable, or whether PB-16 is allowed to take
   `docs/09-database/*` (contradicting its own C05-6 routing to phase 14).
3. Whether PB-13 is re-scoped (production-caller documentation only) or deferred, given its
   stated problem no longer exists.

**Phase-03 verdict in one line: all nine phase-03 commits landed; B1, B2, B3 and B10 blockers are
**SATISFIED** (PB-16's B10 arm is satisfied and its B3 arm is half-discharged by documentation
phase 03 already corrected), and none of them fixed the four defects phase 05 exists to fix —
DP-001, DP-004, DP-016 and DP-015 are all still live exactly as the plan describes them, except
that DP-015's `timedelta(minutes=1)` anchor no longer exists.**