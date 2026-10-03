---
id: file-cleanup
domain: processing
tags:
  - cleanup
  - temp-files
  - lifecycle
  - crash-recovery
related:
  - task-queue
  - task-queue-migration
  - processing-api
  - backend-architecture
  - docker-guide
---

# Temp File Cleanup Architecture

## Purpose

An uploaded CSV is a **transient input**: it is written to a temporary directory, read
once by the worker, and unlinked. This page describes what reclaims it on every path —
success, failure, cancellation — and, separately, what reclaims the *database row* of an
accepted upload that no worker ever ran, and what that reclamation cannot reach.

## The Terminal-State Rule

**Once a job reaches a terminal state — `COMPLETED` or `FAILED` — the input file is
removed. This is a designed property of the system, not an accident.**

Two consequences follow from it, and both are intended:

- The artefact is **not retained** past a terminal state.
- It therefore **cannot be reprocessed** from disk. An operator whose run failed has no
  retry path against the stored file: the only recourse is to ask the uploader for the
  file again. There is no re-run endpoint, and none is planned for this phase.

The rule is stated where it is owned — the `_process_csv_file_async` docstring in
`workers/data_worker.py` — and asserted by `tests/test_file_cleanup.py`. Nothing else
retains the input: the `processing_logs` row stores **no** name and **no** path, so
there is no durable record from which the file could be found even in principle. See
[Processing API → What a stored artefact is called](processing-api.md#what-a-stored-artefact-is-called)
for the naming rule and [Processing API → Check Processing Status](processing-api.md#check-processing-status)
for why `ProcessingStatusResponse.filename` names nothing on disk.

## Lifecycle: One File, Four Exits

| Exit | When | Where |
| ---- | ---- | ----- |
| **Success** | The pipeline finished and the main transaction **committed** | `workers/data_worker.py::_process_csv_file_async`, in the `else` branch that runs only after the `async with session.begin()` block has exited |
| **Failure** | Anything raised during the run, **including a commit failure** | The `except BaseException` handlers in the same function |
| **Cancellation** | `asyncio.CancelledError` | The same handlers |
| **Abandonment** | The process died, or the file was written but no job ever ran | Two independent age-based mechanisms, below |

Every one of the first three exits removes the file. Only the fourth leaves it, and it is
reclaimed by age rather than by the job.

### The success-path unlink is *after* the commit

The success path deliberately does **not** unlink inside the transaction body. The file
is unlinked by the caller once `_run_with_transaction` has returned — in production,
after the `async with session.begin()` block has exited, which is after the commit.

The reason is a shared fate. Success removes the file **only after** the main
transaction commits, so a rollback can never destroy the only copy the aggregates were
derived from: the data would be gone and the aggregates would not exist. A process
killed *before* the commit can now only leave the file on disk with the row still at
`processing`: file and row are never out of step, so no committed row ever names a file
that has been deleted. A process killed *after* the commit but before the unlink leaves a
committed `completed` row and a present file, which the age-based sweep does reclaim.

The **failure-path unlink is retained**, and is load-bearing rather than redundant. A
commit failure makes `session.begin()`'s `__aexit__` re-raise, so the success-path line
is never reached; without the retained failure-path unlink the file would be deleted
neither way and would leak on every commit failure.

Both handlers catch **`BaseException`**, not `Exception`. `asyncio.CancelledError`
inherits `BaseException`, so an `except Exception` clause cannot reach a cancellation and
a cancelled run used to keep its file. The handlers are not bare `finally` blocks — they
`await` the threaded unlink and the compensation write — so the fix is the `except`
clause's type plus an unconditional re-raise; a swallowing handler would let a cancelled
job fall through to a normal return and report success.

### An accepted upload that no worker ran

Two things happen on the accepting path (`services/file_processing.py::process_upload_with_session`),
in this order: **commit → move the file → enqueue**. The commit is the transaction
boundary. A failure before it leaves no job in RQ and no file at a final path, and
neither effect can be retracted by a rollback.

The residual runs the other way:

| Failure between | Leaves | Reclaimed by |
| --------------- | ----- | ------------ |
| commit and move | a committed `uploaded` row with **no file** and no job | the orphan sweep (row) |
| move and enqueue | a file at a final path with **no job**; the enqueue handler unlinks the moved file, so the file is normally gone | the orphan sweep (row); `cleanup_stale_temp_files` (file) |

A failure **before** the commit is simpler: the file is still at the streamed temp path
(`upload_<uuid4>_<original name>`, whose extension is still checked against the allowed
extensions at admission, so it still matches the sweep's `*.csv*` glob), and the upload
route's `finally` unlinks it. If the process dies before that `finally` runs, the file
survives until the age-based sweep reaches it.

So an abandoned accepted input is reclaimed on two independent horizons, by two
different mechanisms, and **the sweep reclaims the row, not the file**.

## The Two Age-Based Mechanisms

They are disjoint by status and share one horizon, so they never contend for the same
row and their notion of "too old" cannot diverge.

| | `cleanup_stale_temp_files` | `mark_orphaned_uploaded_logs_failed` |
| --- | --- | --- |
| Reclaims | **Files** on disk | **Rows** in `processing_logs` |
| Selects on | `upload_temp_dir.glob("*.csv*")` plus file `st_mtime` | rows with `status = uploaded` and `started_at < cutoff` |
| Reads the database | No — it never consults `processing_logs`, and uses **no record identifier at all** | Yes |
| Runs | **On the periodic reconciler loop**, on every tick | **On the periodic reconciler loop**, on every tick |
| Age basis | `STALE_FILE_THRESHOLD_HOURS` (default 24) | `STALE_PROCESSING_TIMEOUT_MINUTES` (default 30) |

The file sweep used to be called once from `db/starter.py` during startup. It no longer
is: it moved onto the existing lease-guarded periodic loop, so there is **one** loop and
not two. See below.

### The `*.csv*` glob is an age sweep, not a selector

`cleanup_stale_temp_files` globs `*.csv*` over the whole upload temp directory and takes
**every** candidate the glob returns. It names no record: it has no task id, no log id and
no database lookup, so it cannot tell one accepted upload's artefact from another's. That
is the point — it is an **age** sweep over a directory, not a per-record removal.

Nothing in the codebase does the opposite any more. `find_task_file`,
`DataService.trigger_processing` and the `IDataService.trigger_processing` protocol
declaration were **deleted**: they re-derived a path from a record that carries no name
and no path, so a removal could not name its target. **No name or path column is being
added** to `processing_logs`, and none exists — a removal therefore still cannot name
what it removed. `tests/test_file_cleanup.py::TestNoArtefactSelectorGlobRemains` asserts
that no `*.csv*` glob survives anywhere in `src/` except this age sweep.

### One periodic loop, lease-guarded — not boot-only

`cleanup_stale_temp_files` runs as the **third** sweep on the tick driven by
`workers/data_worker.py::start_stale_processing_cleanup_task`, after
`cleanup_stale_processing_logs` and `mark_orphaned_uploaded_logs_failed`. All three run
on the same tick, under one horizon and one cancellation path, and their counts are folded
into the same `record_success`.

It used to run only from `DatabaseStarter.startup`. A removal that failed there was never
retried until **a human restarted a process**. On the loop it is retried every tick.

The loop is **lease-guarded** by `core/reconciler_lease.py`, so among several replicas
only the single lease holder sweeps — one elected sweeper, not one per worker. The guard
**fails open**, and the direction is deliberate:

- **Redis unreachable → every replica sweeps.** Redis is a load-and-observability
  optimisation, never a correctness gate; skipping would silently disable the only
  sweeper of stale files and stuck rows.
- **Lease held by another replica → only the holder sweeps.** Reaching Redis and finding
  it is not mine is proof that a live sweeper exists.

### The sweep's result is a `CleanupResult`

`cleanup_stale_temp_files()` returns a `CleanupResult` frozen dataclass with three counts
kept deliberately distinct:

| Field | Meaning | Log level |
| ----- | ------- | --------- |
| `deleted` | Candidates **this** process removed. Concurrent sweepers' `deleted` values sum to the number of files removed exactly once — no file is counted twice. | INFO |
| `already_gone` | Candidates that had already disappeared when this sweep reached them — the **ordinary** outcome of two reclaimers racing over one file | **DEBUG** |
| `failed` | A genuine removal failure: any `OSError` other than `FileNotFoundError`, e.g. `EACCES` | **ERROR** with a traceback |

`FileNotFoundError` is **no longer an ERROR**. Losing that race is the expected outcome of
several sweepers, not a fault, and folding it into one count with a real failure hid the
failures. A genuine `OSError` still is.

### The orphan sweep is on the periodic loop, not only at boot

`mark_orphaned_uploaded_logs_failed` runs as the **second** sweep on the tick driven by
`workers/data_worker.py::start_stale_processing_cleanup_task`, immediately after
`cleanup_stale_processing_logs`, and both counts are folded into the same
`record_success` tick. The `PROCESSING` sweep runs first; the sweeps are disjoint by
status.

It used to run only from `app.py::lifespan` at boot. A process that died an hour after
boot therefore left its `uploaded` row stranded until the next restart. On the loop it
is reclaimed on a clock.

The loop is **lease-guarded** by `core/reconciler_lease.py`, so among several replicas
only the single lease holder sweeps. The guard **fails open**: an unreachable Redis
still sweeps (Redis is a load-and-observability optimisation, never a correctness
gate), and the only case that skips is "reached Redis and it is not mine". On a
periodic sweep against a shared horizon the sweep **cannot distinguish a stranded row
from a merely backlogged one**: a row the `rq-worker` has simply not picked up yet
passes the same horizon as a genuinely abandoned one and is flipped to `FAILED`. A
long queue delay can therefore produce a **transient false failure** in a dashboard's
processing history, which the job overwrites to `PROCESSING` / `COMPLETED` when it
finally runs. The horizon bounds **time to first report**, not job lifetime.

### Horizon and where it is configured

The row sweeps take the **same** horizon, threaded from `Settings` by `app.py::lifespan`
into `start_stale_processing_cleanup_task`, and the orphan sweep falls back to the same
setting when called without an argument. The **file** sweep carries its own, separate
horizon (`STALE_FILE_THRESHOLD_HOURS`) and is *not* bounded by the reconciler's
`timeout_minutes`.

| Variable | Description | Default |
|----------|-------------|---------|
| `STALE_PROCESSING_TIMEOUT_MINUTES` | Horizon for the two **row** sweeps: an `uploaded` or `processing` row older than this is failed | 30 |
| `STALE_PROCESSING_CLEANUP_INTERVAL_SECONDS` | Interval between reconciler ticks; all three sweeps ride it | 300 |
| `STALE_FILE_THRESHOLD_HOURS` | Age before a temp **file** is considered stale | 24 |
| `LOGS_RETENTION_DAYS` | Retention period for processing logs | 30 |

```python
# src/mkobi/config.py
stale_file_threshold_hours: int = Field(default=24, alias="STALE_FILE_THRESHOLD_HOURS")
logs_retention_days: int = Field(default=30, alias="LOGS_RETENTION_DAYS")
stale_processing_timeout_minutes: int = Field(default=30, alias="STALE_PROCESSING_TIMEOUT_MINUTES")
stale_processing_cleanup_interval_seconds: int = Field(default=300, alias="STALE_PROCESSING_CLEANUP_INTERVAL_SECONDS")
```

The **worst-case horizon** for a stranded input is therefore `STALE_FILE_THRESHOLD_HOURS`
for the file (24 h) plus up to one tick of `STALE_PROCESSING_CLEANUP_INTERVAL_SECONDS`
before the next sweep reaches it. The file figure no longer needs a process restart: the
sweep runs on every tick.

## What the Sweep Cannot Reach

Stating these is part of the contract; they are the accepted limits, not oversights.

- **It deletes no files.** The orphan sweep is a single `UPDATE` on `processing_logs`. It flips a row to `failed`; it does not remove anything from disk. An abandoned file is reclaimed only by `cleanup_stale_temp_files`.
- **A file younger than `STALE_FILE_THRESHOLD_HOURS` survives until a later tick** that finds it past the horizon, even when its row has already been failed. The row and the file have separate horizons.
- **`cleanup_stale_temp_files` cannot tell a live file from an abandoned one.** It selects on the directory glob plus `st_mtime` and never reads `processing_logs`, so it will delete the input of a run that is still in flight if that file is older than the threshold. The two horizons are deliberately far apart, which is what keeps this from biting.
- **Only `*.csv*` in the upload temp directory is considered.** A file left anywhere else, or under a name the glob does not match, is outside the sweep entirely.
- **The row sweep is status-scoped.** It reclaims `uploaded` and `processing` rows only. A row already at `completed` or `failed` is never revisited, so a file left behind by a committed run waits for the file sweep alone.
- **It cannot tell a stranded row from a merely backlogged one.** On a periodic clock the sweep selects on age alone, so an `uploaded` row the `rq-worker` has not yet picked up — ordinary queue depth, not a crash — passes the horizon and is marked `FAILED`, producing a **transient false failure in the processing history** that the job later overwrites to `PROCESSING` / `COMPLETED`. The horizon bounds **time to first report**, not job lifetime.
- **Cancellation is not observable to either sweep.** A cancelled run is reclaimed by the worker's own handler at cancellation time; a hard kill is only ever recovered by age.
- **A failed removal is not yet a fact with a reader.** `failed` is counted and logged at
  ERROR with a traceback, and retried on the next tick — but there is **no column on
  `processing_logs` for it and no persisted record**. Nothing queries it; only the log
  carries it. The DDL that would make it addressable (`ProcessingLog.cleanup_error`) is
  **phase 14's** (hand-over **C06-3**) and did not land here. Stated plainly so the
  `failed` count is not read as an operator-visible ledger.

## Configuration

`cleanup_stale_temp_files(max_age_hours=None)` reads the configured threshold when
called with no argument. `0` deletes every file regardless of age; a negative value is
refused, logged, and returns an all-zero `CleanupResult` without deleting anything. A
missing upload directory is likewise an all-zero result, not an error.

```python
result = cleanup_stale_temp_files()
if result.deleted > 0:
    logger.info("Cleaned up %d stale temp files", result.deleted)
```

The function returns a `CleanupResult`; it does not return a bare count.

The `app_data` volume persists across container restarts, so stale files accumulate
until one of these mechanisms reaches them.

### Deferred: no ceiling on the artefact area's size

The artefact area is bounded **by age only** — `STALE_FILE_THRESHOLD_HOURS` decides when a
file is removed, and nothing in the application caps how much disk the directory may
consume or how many artefacts may be in flight at once. That remains true, and no ceiling
is documented here because none has been chosen.

Bounding the area was **deferred, not dropped**: it is owned by **phase 10** under
**C06-04** (volume layout, disk budget, backup story and alerting), whose budget is the
hard input a ceiling would need. A number written before that budget exists would be a
guess presented as a bound.

## Retired Helpers

`services/file_cleanup.py` once held three functions. Two have been removed because no
production caller existed: a task-file reclaimer that read the in-memory queue's own
status registry (deleted along with that queue, so it lost its only data source and
re-derived a path from a loose glob that swallowed every failure), and a duplicate of
the startup log-retention sweep that arrived later as a drive-by paste and was never
wired.

This page **never named either helper**, so no claim here needed retracting. The live
retention sweep is `DatabaseStarter.cleanup_old_logs`, called from startup; it is the
copy with the `<= 0` retention guard and the deliberate engine separation.

Three further selectors were removed outside this module and are documented above under
[The `*.csv*` glob is an age sweep, not a selector](#the-csv-glob-is-an-age-sweep-not-a-selector):
`find_task_file`, `DataService.trigger_processing` and the `IDataService.trigger_processing`
protocol declaration. None of them had a route caller, and each re-derived a path from a
record that carries no name — so each promised a per-record removal that could not exist.
The age sweep they left behind is the only `*.csv*` glob in `src/`.

## Cross-References

- [Processing API](processing-api.md) — Upload endpoint and processing pipeline
- [Task Queue](task-queue.md) — Historical record of the in-process queue and its removal
- [Task Queue Migration](../11-guides/task-queue-migration.md) — The RQ migration decision record and operational documentation
- [Backend Architecture](../06-backend/architecture.md) — Startup lifecycle and Clean Architecture layering
- [Docker Guide](../11-guides/docker.md) — Volume configuration and permission setup