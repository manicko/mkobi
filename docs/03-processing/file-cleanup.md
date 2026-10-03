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

## Lifecycle: One File, Four Exits

| Exit | When | Where |
| ---- | ---- | ----- |
| **Success** | The pipeline finished and the main transaction **committed** | `workers/data_worker.py::_process_csv_file_async`, in the `else` branch that runs only after the `async with session.begin()` block has exited |
| **Failure** | Anything raised during the run, **including a commit failure** | The `except BaseException` handlers in the same function |
| **Cancellation** | `asyncio.CancelledError` | The same handlers |
| **Abandonment** | The process died, or the file was written but no job ever ran | Two independent age-based mechanisms, below |

### The success-path unlink is *after* the commit

The success path deliberately does **not** unlink inside the transaction body. The file
is unlinked by the caller once `_run_with_transaction` has returned — in production,
after the `async with session.begin()` block has exited, which is after the commit.

The reason is a shared fate. A process killed *before* the commit can now only leave
the file on disk with the row still at `processing`: file and row are never out of step,
so no committed row ever names a file that has been deleted. A process killed *after*
the commit but before the unlink leaves a committed `completed` row and a present file,
which the age-based sweep does reclaim.

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
(`upload_<uuid4>_<original name>`, so its extension still matches the sweep's `*.csv*`
glob), and the upload route's `finally` unlinks it. If the process dies before that
`finally` runs, the file survives until the age-based startup sweep.

So an abandoned accepted input is reclaimed on two independent horizons, by two
different mechanisms, and **the sweep reclaims the row, not the file**.

## The Two Age-Based Mechanisms

They are disjoint by status and share one horizon, so they never contend for the same
row and their notion of "too old" cannot diverge.

| | `cleanup_stale_temp_files` | `mark_orphaned_uploaded_logs_failed` |
| --- | --- | --- |
| Reclaims | **Files** on disk | **Rows** in `processing_logs` |
| Selects on | `upload_temp_dir.glob("*.csv*")` plus file `st_mtime` | rows with `status = uploaded` and `started_at < cutoff` |
| Reads the database | No — it never consults `processing_logs` | Yes |
| Runs | **At startup only** | **On the periodic reconciler loop**, on every tick |
| Age basis | `STALE_FILE_THRESHOLD_HOURS` (default 24) | `STALE_PROCESSING_TIMEOUT_MINUTES` (default 30) |

The stale-file sweep is called once from `db/starter.py` during startup.

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
gate), and the only case that skips is "reached Redis and it is not mine". A row a
consumer is still about to pick up stays `uploaded` until the horizon passes; once it
passes, the row is genuinely stuck and failing it is the intent.

### Horizon and where it is configured

Both sweeps take the **same** horizon, threaded from `Settings` by `app.py::lifespan`
into `start_stale_processing_cleanup_task`, and the orphan sweep falls back to the same
setting when called without an argument.

| Variable | Description | Default |
|----------|-------------|---------|
| `STALE_PROCESSING_TIMEOUT_MINUTES` | Horizon for **both** sweeps: an `uploaded` or `processing` row older than this is failed | 30 |
| `STALE_PROCESSING_CLEANUP_INTERVAL_SECONDS` | Interval between reconciler ticks | 300 |
| `STALE_FILE_THRESHOLD_HOURS` | Age before a temp **file** is considered stale | 24 |
| `LOGS_RETENTION_DAYS` | Retention period for processing logs | 30 |

```python
# src/mkobi/config.py
stale_file_threshold_hours: int = Field(default=24, alias="STALE_FILE_THRESHOLD_HOURS")
logs_retention_days: int = Field(default=30, alias="LOGS_RETENTION_DAYS")
stale_processing_timeout_minutes: int = Field(default=30, alias="STALE_PROCESSING_TIMEOUT_MINUTES")
stale_processing_cleanup_interval_seconds: int = Field(default=300, alias="STALE_PROCESSING_CLEANUP_INTERVAL_SECONDS")
```

The **worst-case horizon** for a stranded input is therefore
`STALE_FILE_THRESHOLD_HOURS` for the file (24 h, and only if a process restart happens,
because that sweep is startup-only) plus up to one tick of
`STALE_PROCESSING_CLEANUP_INTERVAL_SECONDS` for the row.

## What the Sweep Cannot Reach

Stating these is part of the contract; they are the accepted limits, not oversights.

- **It deletes no files.** The orphan sweep is a single `UPDATE` on `processing_logs`. It flips a row to `failed`; it does not remove anything from disk. An abandoned file is reclaimed only by `cleanup_stale_temp_files`, which is age-based and runs at startup only.
- **A file younger than `STALE_FILE_THRESHOLD_HOURS` survives until the next startup**, even when its row has already been failed. The row and the file have separate horizons and separate triggers.
- **`cleanup_stale_temp_files` cannot tell a live file from an abandoned one.** It selects on the directory glob plus `st_mtime` and never reads `processing_logs`, so it will delete the input of a run that is still in flight if that file is older than the threshold. The two horizons are deliberately far apart, which is what keeps this from biting.
- **Only `*.csv*` in the upload temp directory is considered.** A file left anywhere else, or under a name the glob does not match, is outside the sweep entirely.
- **The row sweep is status-scoped.** It reclaims `uploaded` and `processing` rows only. A row already at `completed` or `failed` is never revisited, so a file left behind by a committed run waits for the file sweep alone.
- **Cancellation is not observable to either sweep.** A cancelled run is reclaimed by the worker's own handler at cancellation time; a hard kill is only ever recovered by age.

## Configuration

`cleanup_stale_temp_files(max_age_hours=None)` reads the configured threshold when
called with no argument. `0` deletes every file regardless of age; a negative value is
refused and returns `0` without deleting anything.

```python
deleted_count = cleanup_stale_temp_files()
if deleted_count > 0:
    logger.info("Cleaned up %d orphaned temp files during startup", deleted_count)
```

The `app_data` volume persists across container restarts, so stale files accumulate
until one of these mechanisms reaches them.

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

## Cross-References

- [Processing API](processing-api.md) — Upload endpoint and processing pipeline
- [Task Queue](task-queue.md) — Historical record of the in-process queue and its removal
- [Task Queue Migration](../11-guides/task-queue-migration.md) — The RQ migration decision record and operational documentation
- [Backend Architecture](../06-backend/architecture.md) — Startup lifecycle and Clean Architecture layering
- [Docker Guide](../11-guides/docker.md) — Volume configuration and permission setup