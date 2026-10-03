---
id: task-queue
domain: processing
tags:
  - task-queue
  - redis
  - rq
  - background-processing
  - history
  - asyncio
related:
  - processing-api
  - file-cleanup
  - backend-architecture
  - deployment
  - security-overview
---

# Task Queue: Historical Record

## Purpose

This page is a **historical record**. It describes a design that no longer exists in
this repository and explains why it was replaced. It is not operational guidance and
must not be followed as a procedure.

For the decision record and the operational documentation of the current system, see
[Task Queue Migration](../11-guides/task-queue-migration.md).

---

## Status

**The in-process queue was removed. Background work runs on Redis/RQ.**

| | |
| --- | --- |
| Direction | RQ is the single submission **and** execution path |
| Decision date | 2026-09-30, commit `3848e7a` |
| Audit linkage | `TOPO-002` / `TOPO-003` (process-architecture phase); `OPS-002` recorded the same defect as a duplicate |

A test asserts the absence of the retired surface. `tests/test_task_queue.py::TestRetiredSymbolsRemoved`
checks that `TaskQueue`, `default_queue` and `get_task_queue` are no longer attributes
of the module, and `tests/test_app_lifespan.py` asserts `app.py` never mentions them.
A symbolic absence is maintained deliberately: nothing re-introduces a local queue.

---

## What Exists Now

`src/mkobi/core/task_queue.py` is a thin **RQ submission seam**. It is the only place
an RQ enqueue is written, so no service module imports `rq`:

| Symbol | Role |
|---|---|
| `DEFAULT_QUEUE_NAME` | The single shared queue name, `"default"`. Imported by `rq_worker_wrapper.py` so producer and consumer cannot diverge onto different queues. |
| `get_rq_queue()` | `functools.cache`-d factory building one `rq.Queue` from `Settings.redis` (host, port, db, password), so a request does not open a new Redis connection per submission. |
| `enqueue_job(func, *args, **kwargs)` | `async`; submits through `asyncio.to_thread` and returns the RQ job id. |

`enqueue_job` **raises** `AppException` with `FILE_PROCESSING_ERROR` on failure. The
pre-migration wrapper returned `None` and logged; the current contract is fail-loud,
because a silently dropped job is indistinguishable from a job that is still queued.

The executor is the `rq-worker` container. `app.py::lifespan` runs no queue worker.

---

## What Was Removed

The removed implementation was a `TaskQueue` class in
`src/mkobi/core/task_queue.py` built on `asyncio.Queue`. It exposed a module-level
`default_queue` singleton, a `get_task_queue()` accessor, an `enqueue_job()`
compatibility wrapper around `default_queue.enqueue()`, and a `process_next()` method
that popped one task and ran it in-process.

Its state lived in three Python dictionaries:

```python
self._queue: asyncio.Queue[dict[str, Any]]   # pending tasks
self._statuses: dict[str, ProcessingStatus]  # task_id -> status
self._results: dict[str, Any]                # task_id -> result
self._errors: dict[str, str | None]          # task_id -> error message
```

Its lifecycle was: `enqueue()` generated a UUID and set the status to `STARTED` and
pushed to the queue; `process_next()` popped, set the status to `PROCESSING` and ran
the task function; on success the status went to `SUCCESS` and the result landed in
`_results`; on failure it went to `FAILED` with the message in `_errors`.

**`ProcessingStatus.SUCCESS` does not exist.** The enum's five members are `STARTED`,
`UPLOADED`, `PROCESSING`, `COMPLETED` and `FAILED`. The old lifecycle's terminal
success state was `SUCCESS`; the current terminal success state is `COMPLETED`. The
retired database value was removed by a landed migration, so the old spelling is not
accepted as a status anywhere — including as an admin `status_filter` value.

## Why It Went

The reasons below are the historical argument. They were true of the removed code and
they are the reason it was not kept.

1. **Task loss on restart.** `asyncio.Queue` is pure in-memory. Any restart, crash or
   graceful shutdown lost every pending task. Tasks not yet dequeued were
   irrecoverable.
2. **No persistence.** Status, results and errors were Python dictionaries, so a
   restart erased the history and every poll for a previously enqueued task answered
   `FAILED`.
3. **No horizontal scaling.** Each application instance had its own isolated queue, so
   a separate worker process could not consume from it and the API could not be scaled
   independently of its worker.
4. **No retry on crash.** A process dying inside `process_next()` lost the task
   outright: no dead-letter queue, no retry counter, no re-enqueue.
5. **Single-threaded execution.** One task at a time on the single async loop; a long
   CSV blocked everything behind it.
6. **No visibility.** No queue depth, worker health, throughput, or failure history.

The MVP rationale at the time was to avoid an external dependency and keep the
deployment simple. The module docstring said so explicitly: *"For production, replace
with Redis/RabbitMQ and integrate with processing_logs."*

---

## The Status Vocabulary Today

`processing_logs` is the single source of truth for a run's fate; RQ's own job status
is not surfaced by the API. The transitions are:

```
started -> uploaded -> processing -> completed / failed
```

| `ProcessingStatus` | Meaning |
|---|---|
| `STARTED` | Task row created, upload initiated |
| `UPLOADED` | File in place, not yet picked up by a worker |
| `PROCESSING` | Pipeline running; committed on its own short transaction before the work starts |
| `COMPLETED` | Aggregates written; commits **with** the aggregate write |
| `FAILED` | The run failed; the recorded `error_code` says why |

`UPLOADED` and `PROCESSING` are the two classes the reconciler sweeps, and it reclaims
them by age — see [Temp File Cleanup](file-cleanup.md).

---

## Cross-References

- [Task Queue Migration](../11-guides/task-queue-migration.md) — The decision record and the migration history. Cross-referenced, not duplicated.
- [Processing API](processing-api.md) — The pipeline contract: submission, statuses, and error classification
- [Temp File Cleanup](file-cleanup.md) — File reclamation and the age-based reconciler sweeps
- [Backend Architecture](../06-backend/architecture.md) — Startup lifecycle and Clean Architecture layering
- [Deployment](../10-deployment/deployment.md) — The `rq-worker` service