---
phase: 06-file-artifacts
executed: 2026-10-05
executor: auditor
problems-only: true
findings: 8
by-severity:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 5
  LOW: 3
---

# Phase 06 — Findings

## Summary

The stored-file path was examined end to end at `HEAD f8581e0` on all eight blocks: the accepted
upload's identity, the staging area and its bounds, store-versus-record reconciliation in both
directions, the four removal exits and the record of a failed removal, the Redis-backed one-time
secret, the built SPA bundle, the process set that reclaims artefacts, and the returning surfaces.
Most of what a prior phase of this audit recorded has since been remediated — the stored name is
now derived from the detector's verdict, the worker's success unlink sits after the commit, the
sweep is one lease-guarded loop with three separated counts, the bundle's mount and health
component share one predicate, the dead MIME configuration key is gone and libmagic is a hard
dependency, and the one-time secret now reports its own storage outcome to the administrator.
Eight defects remain — five `MEDIUM`, three `LOW` — and none of them is reachable at its full
effect on the running dev stack. The single most consequential is
**ART-104**, where an I/O
error at the success-path unlink writes `FAILED` over a `COMPLETED` row that was already
committed, a transition this codebase's own state machine rejects on every other path. Runtime
evidence was obtained by executing the artefact subsystem inside the `mkobi-test` `test-app`
image, which is the only tier here with `libmagic`; **finding-ID namespace collision is disclosed
in Appendix F** — `ART-001` … `ART-009` are already referenced from `docs/SPEC.md`, two
`_code-context` notes and `.ai/tasks/B3-txn-003-durable-processing-transitions.yaml`, so this
report starts at `ART-101`.

## Findings

### ART-101 — admission refuses a comma-delimited CSV whose last line has no trailing newline

**Severity** — MEDIUM

**Zone** — "The accepted artefact's identity: what it is called, what its name claims, and what its bytes are"

**Observation** — MIME admission is decided by libmagic's own text-type classifier reading only
the first 2048 bytes of the file. That classifier does not answer "is this a CSV?"; it answers
"does this buffer *look like* the CSV shape libmagic recognises", and it requires the final
record to be complete. A byte stream that `pl.read_csv` parses without difficulty is therefore
refused with `415 INVALID_FILE_TYPE` when its last line carries no newline and it is short. The
refusal arrives at `src/mkobi/services/file_processing.py:42-45` → `:69-82`.

**Evidence** — Executed in the `mkobi-test` `test-app` image (libmagic present), calling
`mkobi.services.file_processing.detect_mime_type_from_content` on buffers written to disk:

```text
=== libmagic verdicts (2048-byte prefix) ===
  comma CSV many rows              -> text/csv                   admitted=True
  comma CSV tiny                   -> text/plain                 admitted=False
  semicolon CSV                    -> text/plain                 admitted=False
  single-column text               -> text/plain                 admitted=False
  gzip of comma CSV                -> application/gzip           admitted=True
  plain CSV named .gz              -> text/csv                   admitted=True
  empty file                       -> application/x-empty        admitted=False
=== comma CSV, increasing row count ===
  header only                        len=4     -> text/plain   admitted=False
  header + 1 row                     len=8     -> text/plain   admitted=False
  header + 2 rows                    len=12    -> text/csv     admitted=True
  header + 5 rows                    len=24    -> text/csv     admitted=True
=== 3-row BI aggregate, no trailing newline ===
  a,b / 1,10 / 2,20              len=24  -> text/plain   admitted=False
=== 3-row BI aggregate, trailing newline ===
  ...+ trailing \n              len=25  -> text/csv     admitted=True
```

Two files differing by exactly one trailing byte get opposite verdicts. `validate_mime_type`
of `named.txt` whose bytes *are* a comma CSV returns `text/csv` — the detector is genuinely
content-driven, and the refusal is the classifier's, not the extension check's.

The detector is read once, verbatim, at `src/mkobi/services/file_processing.py:42-45`:

```python
42:     with open(file_path, "rb") as f:
43:         file_buffer = f.read(2048)
44:     detected_mime = magic.from_buffer(file_buffer, mime=True)
45:     return detected_mime or "application/octet-stream"
```

and the refusal at `src/mkobi/services/file_processing.py:69-82`:

```python
69:     detected_mime = detect_mime_type_from_content(file_path)
70: 
71:     allowed_mime_types = MimeTypeEnum.allowed_values()
72:     if detected_mime not in allowed_mime_types:
73:         logger.error(
74:             "Invalid MIME-type detected: %s. Allowed: %s",
75:             detected_mime,
76:             allowed_mime_types,
77:         )
78:         raise AppException(
79:             code=ErrorCode.INVALID_FILE_TYPE,
80:             detail=f"Detected MIME type {detected_mime} not allowed",
81:         )
82:     return MimeTypeEnum(detected_mime)
```

The pipeline the refusal pre-empts would have read the file: `src/mkobi/workers/data_worker.py:703-708`
builds the loader and calls `load_csv` on the stored artefact.

**No shipped test exercises a real libmagic verdict.** Every case in
`tests/test_mime_admission_contract.py` that touches admission replaces the detector —
`:80-102` monkeypatches `file_processing.detect_mime_type_from_content` to return
`"text/plain"`, and `:196-225` parametrizes over the enum by monkeypatching it to return the
member under test. The one test that inspects the real call site,
`tests/test_mime_admission_contract.py:168-185`, installs a `_MagicSentinel` stand-in. The
classifier's behaviour on real bytes is therefore untested by construction.

`docs/03-processing/processing-api.md:60` documents the *semicolon* casualty of moving to
libmagic but does not mention this one: a CSV must actually be comma-delimited **and** long
enough for libmagic to recognise it **and** newline-terminated.

**Consequence** — A dashboard whose data legitimately arrives as a small aggregate CSV (the
`category,value / A,10 / B,20` case above is exactly what a two-category chart is fed) is
refused at the door with `415` and a `detail` that names only the classifier's verdict. The
upload never reaches `data_service.process_upload`, no `processing_logs` row is created, and the
pipeline that would have parsed the file never runs. Neither the RFC 7807 body nor
`docs/03-processing/processing-api.md` tells the uploader that a trailing newline is decisive, so
the failure is not self-diagnosing. There is no data loss and no security exposure — the gate is
strictly tighter than the reader, which is the safe direction — but the error is attributed to
"invalid file type" rather than to what is actually wrong.

**Recommendation** — Keep content sniffing as the gate; it is correct and the previous finding
against it is remediated. Move the *CSV-ness* decision off the generic text classifier: either
admit on `(detected == text/csv | detected in the gzip pair)` **and** `pl.read_csv` a bounded
prefix in the same admission step, or treat `text/plain` as provisional and let the loader's
reader boundary be the single place a malformed CSV is rejected (it already is, at the
`INVALID_FILE_TYPE` row of `docs/03-processing/processing-api.md:196`). Either way the fix needs
a test that calls the **real** detector: add one case per buffer shape in the table above to
`tests/test_mime_admission_contract.py`, so the classifier's real thresholds stop being an
unmeasured dependency. Whichever branch is taken, `docs/03-processing/processing-api.md:60`
must gain the row-count / final-newline clause.

### ART-102 — the artefact area's only reclaimer cannot see four of the eight name shapes the upload route produces

**Severity** — MEDIUM

**Zone** — "Residence of an accepted artefact, and what bounds it"

**Observation** — The accepted artefact's residence has exactly one reclaimer after a hard kill:
`cleanup_stale_temp_files`, which selects with `upload_dir.glob("*.csv*")`. The upload route
names its in-flight file `upload_{uuid4()}_{sanitized_filename}` where `sanitized_filename` is
`Path(file.filename).name` — the caller's basename, verbatim, with no extension imposed. The
sweep's naming rule and the producer's naming rule therefore disagree, and for any client
filename that does not contain `.csv` the sweep can never see the file.

**Evidence** — The producer, `src/mkobi/api/routes/upload.py:199-205`:

```python
199:         filename = file.filename or "unknown"
200:         sanitized_filename = Path(filename).name
201: 
202:         # Create temporary file path with unique name
203:         upload_dir = Path(get_config().upload_temp_dir)
204:         upload_dir.mkdir(parents=True, exist_ok=True)
205:         temp_file_path = upload_dir / f"upload_{uuid4()}_{sanitized_filename}"
```

The only reclaimer, `src/mkobi/services/file_cleanup.py:91-92`:

```python
91:     # Find all CSV files in upload directory
92:     csv_files = list(upload_dir.glob("*.csv*"))
```

Executed in the `test-app` image, creating the eight name shapes the route can produce and then
running the sweep at its most aggressive setting:

```text
=== sweep glob visibility ===
created=8 matched=4
   SEEN      report.csv
   SEEN      report.csv.gz
   INVISIBLE report.txt
   INVISIBLE report
   INVISIBLE 
   INVISIBLE unknown
   SEEN      644b44f8-4731-446d-9b9e-7b9b4fe29f4e.csv
   SEEN      7822ba5f-043e-4809-82df-ad1f5217aa97.csv.gz
=== sweep with max_age_hours=0 ===
CleanupResult: CleanupResult(deleted=4, already_gone=0, failed=0)
still present: ['upload_598fc38e-..._unknown', 'upload_625559a1-..._report',
                'upload_73ef18bb-..._', 'upload_f78d4f90-..._report.txt']
```

`report.txt`, `report`, `` (the result of `Path("..").name` and of an empty filename) and
`unknown` (the result of a multipart part with no `filename`) are the shapes a client produces
with a single ordinary request, and the sweep at `max_age_hours=0` — "delete everything
regardless of age" — leaves all four behind.

The extension check that would reject those names happens *later*, at
`src/mkobi/services/file_processing.py:127-138`, and only for files that reach it:

```python
127:     if filename and not any(
128:         filename.lower().endswith(ext.lower()) for ext in allowed_extensions
129:     ):
```

The documentation states the opposite of what the code does here.
`docs/03-processing/file-cleanup.md:98-102`:

```markdown
98: A failure **before** the commit is simpler: the file is still at the streamed temp path
99: (`upload_<uuid4>_<original name>`, whose extension is still checked against the allowed
100: extensions at admission, so it still matches the sweep's `*.csv*` glob), and the upload
101: route's `finally` unlinks it. If the process dies before that `finally` runs, the file
102: survives until the age-based sweep reaches it.
```

"it still matches the sweep's `*.csv*` glob" is false for the four shapes above, and the file
exists on disk from `upload.py:210` — *before* the admission check that is being relied on. The
same page contradicts itself 131 lines later at `:233`, which is the accurate half:

> **Only `*.csv*` in the upload temp directory is considered.** A file left anywhere else, or
> under a name the glob does not match, is outside the sweep entirely.

**Consequence** — The route's `finally` (`src/mkobi/api/routes/upload.py:260-265`) removes the
in-flight file on every managed exit, so nothing leaks on an ordinary rejection. Only a hard kill
bypasses it — an OOM-killed uvicorn worker, `docker compose restart`, a node reboot — and that is
precisely the event the age sweep exists to recover from. When it happens for a client-chosen
name without `.csv`, the file is **never** reclaimed: not by the sweep (invisible), not by the
route (process gone), not by the worker (it was never enqueued), not by `cleanup_temp_dir`
(`src/mkobi/utils/file_utils.py:41-42`, no production caller). The area has no byte ceiling and no
count ceiling — an accepted limit, `docs/03-processing/file-cleanup.md:262-272`, deferred to
phase 10 under C06-04 — so each such event adds a permanent file. Over a year of restarts this is
an unbounded, silent growth of user-uploaded bytes on `app_data`, invisible to
`/health/detailed`, whose `stale_processing_reconciler` component reports `deleted`, never
"unseen". No occurrence was observed in 40 hours of running-dev-stack logs (Appendix E); the rate
today is zero because no kill happened, not because the path is closed.

**Recommendation** — Make the producer obey the reclaimer rather than widening the reclaimer to
the caller's charset: name the in-flight file from the artefact's identity, not the caller's —
`upload_{uuid4()}{ext}` where `ext` comes from the same `FileExtensionEnum` the admission gate
enforces, keeping the caller's basename out of the path entirely. That both closes the
disagreement and removes the client-controlled string from a filesystem path. Failing that, widen
the sweep to `glob("*")` with an explicit skip for a `.csv`-free name is *not* acceptable — it
would let the sweep unlink a file it does not understand — so the correct widening is to keep the
glob and give the route a startup-time reconcile for its own `upload_*` prefix. Whichever shape is
chosen, `docs/03-processing/file-cleanup.md:99-100` must be corrected; it is currently the
reassuring half of a self-contradiction. Note that `TOPO-111` (phase 01, confirmed) already owns
the dead `get_user_temp_dir` / `cleanup_temp_dir` pair and the fact that a second, un-swept tree
would be created by re-enabling it — do not resolve this finding by moving admission onto
`get_user_temp_dir` without also widening the sweep, which is the trap TOPO-111 names.

### ART-103 — the published reconciler tick excludes removal failures, so a sweep that removed nothing is reported as a healthy tick

**Severity** — MEDIUM

**Zone** — "Removal of an artefact, and the record of a removal that failed"

**Observation** — `cleanup_stale_temp_files` computes three counts and returns all three. Its
only production caller reads one of them. `CleanupResult.failed` is discarded at the call site,
so the single number the system publishes about the reclaimer is a count of successes only.

**Evidence** — The count is computed and logged, `src/mkobi/services/file_cleanup.py:116-122`:

```python
116:         except OSError as e:
117:             # Any other OS-level failure (e.g. EACCES) is a real removal error.
118:             # It is deliberately NOT folded into ``already_gone``: silencing a
119:             # genuine failure as "someone else got it" is the opposite of the
120:             # point of this classification.
121:             failed_count += 1
122:             logger.error("Error removing stale temp file %s: %s", file_path, e, exc_info=True)
```

The only production call site, `src/mkobi/workers/data_worker.py:1562-1564`:

```python
1562:             files = cleanup_stale_temp_files()
1563:             if status is not None:
1564:                 status.record_success(count + orphaned + files.deleted)
```

A repository-wide search for `.failed` in `src/` returns exactly two hits: the increment above and
`record_failure` is never called — `ReconcilerStatus` has no such method
(`src/mkobi/core/reconciler_lease.py:75-98`). The discarded count is described, in the function
that receives it, as work the tick disposed of — `src/mkobi/core/reconciler_lease.py:82-96`:

```python
82:     def record_success(self, swept_count: int) -> None:
83:         """Record a completed sweep tick.
...
86:             swept_count: Work items the tick disposed of, possibly 0. This is
87:                 the **sum** of two distinct kinds of item: processing rows the
88:                 sweep moved to a terminal state (``FAILED``), plus stale temp
89:                 files removed on the same tick. It is published verbatim as the
90:                 client-visible ``last_swept_count`` on ``/health/detailed``, so
91:                 the published integer does **not** mean "rows failed": a tick
92:                 reporting ``137`` may have failed 0 rows and removed 137 files.
```

"Work items the tick disposed of" is false for every removal that raised. The value reaches an
operator through `src/mkobi/app.py:479-486`:

```python
479:             components["stale_processing_reconciler"] = {
480:                 "status": "ok" if last_success is not None else "starting",
481:                 "lease_state": status_snapshot.lease_state.value,
482:                 "last_success_at": last_success.isoformat() if last_success is not None else None,
483:                 "last_swept_count": status_snapshot.last_swept_count,
484:                 "sweep_count": status_snapshot.sweep_count,
485:                 "unprotected_ticks": status_snapshot.unprotected_ticks,
486:             }
```

**Consequence** — On a tick in which the sweep found 40 candidates and every `unlink` raised
(`EACCES` after a permission change on the `app_data` volume, `EROFS` after a read-only remount,
`EIO`), `/health/detailed` reports `status: "ok"`, `last_swept_count` equal to the row sweeps'
contribution only, and `sweep_count` advancing. The tick looks healthier than an idle one, which
is the most common state. An operator reading the only published signal of the sole reclaimer of
`app_data/tmp_uploads` cannot distinguish "there was nothing to remove" from "nothing could be
removed", and nothing else in the system reports it: `ProcessingLog` has seven columns and none
of them is a removal outcome (`src/mkobi/db/models/processing_logs.py:43-72`). The area then
grows silently — which is the same unbounded-growth exposure ART-102 describes, reached through a
second door.

`docs/03-processing/file-cleanup.md:237-242` accepts the *record* half of this precisely and
hands the DDL to phase 14 under C06-3:

> **A failed removal is not yet a fact with a reader.** `failed` is counted and logged at ERROR
> with a traceback, and retried on the next tick — but there is **no column on `processing_logs`
> for it and no persisted record**.

That acceptance covers persistence. It says nothing about the health surface, which is the one
reader that exists today and which is fed a count from which the failures were already removed.

**Recommendation** — Fold `files.failed` into the value the reconciler publishes; that is the
whole fix for the observable half, needs no migration, and makes the existing `CleanupResult`
field live. The honest shape is to keep the two kinds apart rather than sum a failure into a
"disposed of" count: either add `last_failed_count: int` to `ReconcilerStatus` and publish it
beside `last_swept_count` in `src/mkobi/app.py:479-486`, or change `record_success` to take the
whole `CleanupResult`. `ReconcilerStatus`'s docstring at `src/mkobi/core/reconciler_lease.py:86-92`
must then be corrected either way, because it currently asserts a meaning the number does not
have. Neither adjacent seam blocks the change: phase 03's B3 touches `data_worker.py` but not the
two call sites above, and phase 14's `cleanup_error` column is only needed for the *persisted*
record this finding deliberately does not require.

### ART-104 — an I/O error at the success-path unlink writes FAILED over a COMPLETED row that was already committed

**Severity** — MEDIUM

**Zone** — "Removal of an artefact, and the record of a removal that failed"

**Observation** — The worker's production branch removes the accepted artefact *after* the main
transaction has committed, which is the correct order and the fix the prior finding demanded. The
removal itself is the only unlink in the function with no exception guard, and it sits inside the
same `try:` whose `except BaseException` handler is the failure path. Any `OSError` from it is
therefore caught as a processing failure, and the handler writes `FAILED` over the `COMPLETED` row
the commit already made durable — a transition this codebase's own state machine declares illegal.

**Evidence** — The success edge, `src/mkobi/workers/data_worker.py:1027-1038`. The `try:` opens at
`:997`; the `async with session.begin():` block ends at `:1027`; the unlink has no guard:

```python
1027:                     result = await _run_with_transaction(session)
1028:             # Deletion site 3 of 4 (success, production path). Reached only after
...
1035:             if file_path.exists():
1036:                 await asyncio.to_thread(file_path.unlink)
1037:                 logger.info("Temp file deleted: %s", file_path)
1038:             return result
```

The handler that `:1036` falls into, `src/mkobi/workers/data_worker.py:1039-1048` and `:1056-1077`:

```python
1039:         except BaseException as e:
...
1046:             error_msg = str(e)
1047:             error_code = _map_processing_error_to_code(e)
1048:             logger.exception("Processing failed: task_id=%s, error=%s, code=%s", task_id, error_msg, error_code)
...
1056:             if file_path.exists():
1057:                 try:
1058:                     await asyncio.to_thread(file_path.unlink)
1059:                 except BaseException:
...
1070:             try:
1071:                 await _update_processing_log_status(
1072:                     task_id=task_id,
1073:                     status=ProcessingStatus.FAILED,
1074:                     message=_durable_failure_message(e),
1075:                     finished_at=datetime.now(UTC),
1076:                     error_code=error_code,
1077:                 )
```

By the time `:1056` runs the file is already gone, so `exists()` is `False`, the reclaim is
skipped, and `:1071` writes `FAILED` on a fresh session. `_update_processing_log_status` is an
unconditional `UPDATE` — `src/mkobi/workers/data_worker.py:418-431`:

```python
418:         stmt = (
419:             update(ProcessingLog)
420:             .where(ProcessingLog.id == UUID(task_id))
421:             .values(**values)
422:         )
```

— and never consults the state machine, which the codebase declares as
`src/mkobi/models/enums.py:71-79`:

```python
71:         State machine: STARTED -> UPLOADED -> PROCESSING -> COMPLETED/FAILED.
72:         Terminal states (COMPLETED, FAILED) cannot transition to any other state.
...
78:             cls.COMPLETED: set(),
79:             cls.FAILED: set(),
```

That machine is enforced elsewhere and refused on the other route:
`src/mkobi/services/processing_log_service.py:36` calls
`ProcessingStatus.valid_transitions()` and `:37-44` raises
`AppException(code=ErrorCode.INVALID_TRANSITION, …)` for `COMPLETED → FAILED`. The worker's own
helper, which is the only writer of terminal transitions on the pipeline path, has no equivalent
check — so the same transition is a 400 on the API route and a silent overwrite on the worker.

`FileNotFoundError` is one concrete trigger, and it is the race ART-102's sibling design already
anticipates: the sweep and the worker are different processes on the same volume, and the sweep's
`already_gone` counter exists because that race is considered ordinary
(`src/mkobi/services/file_cleanup.py:108-115`). A file is only eligible once its `st_mtime` is
older than `stale_file_threshold_hours` (default 24, `src/mkobi/config.py` —
`stale_file_threshold_hours`), so under the shipped default the race needs a job still running
24 hours after its upload — which no shipped configuration produces. Set that threshold below the
job's wall clock and it is immediately live; the test tier already sets the equivalent knob to
zero at `tests/conftest.py:154-158` (`cleanup_stale_temp_files(max_age_hours=0)`).

**Consequence** — When it fires, the dashboard's aggregates have already been replaced and
committed, and the processing log for that run is rewritten to `FAILED`. Nothing downstream
distinguishes the two: `src/mkobi/services/data_service.py:397-402` returns
`ProcessingResult(success=False, …, message="Processing not complete. Status: failed")` for the
run whose aggregates are in fact committed and current, and the dashboard renders the older
committed data as if the upload had failed. There is no reversal path: the artefact is gone (that
is what the unlink was for), and the aggregates are unreproducible without the caller's file. The
failure is silent in the sense that matters — the log line at `:1048` reads as an ordinary
processing failure, and the `error_code` recorded is derived from an `OSError` the operator will
read as a worker fault rather than as "the run succeeded and the tidy-up did not".

**Severity justification** — MEDIUM, not HIGH, and deliberately so: the trigger is an `OSError`
at one `unlink`, and **no such error occurred in 40 hours of the running dev stack's logs**
(Appendix E). The rubric's HIGH band is reserved for defects producing wrong results now; this one
produces them only if the filesystem misbehaves. A reviewer who wants this at HIGH needs one
observed occurrence; the code evidence above is what makes it a real defect rather than a
hypothetical.

**Recommendation** — Give the success-path unlink its own narrow guard so a removal fault cannot
be reported as a processing fault: wrap `:1035-1037` in `try/except OSError` and log at WARNING
with `exc_info=True` rather than letting it propagate into `:1039`, matching how the two removal
sites that already have a guard are written. The file then survives a failed removal and the age
sweep reclaims it on a later tick — which is exactly the state `docs/03-processing/file-cleanup.md:64-70`
already describes for "killed after the commit but before the unlink". Do **not** extend the fix to
a state-machine check inside `_update_processing_log_status`: the helper is the worker's
compensation path, and a `COMPLETED → FAILED` refusal there would leave a committed-`COMPLETED`
run whose job the broker believes failed, which is the same split-brain by another route. No
shipped test blocks this change —
`tests/test_file_cleanup.py::TestAcceptedArtefactTerminalStateRule` asserts the artefact is absent
and exactly one `FAILED` write per failure, but nothing in `tests/test_file_cleanup.py` makes the
success-path `unlink` raise, so this needs a **new** test (a `unlink` that raises once, asserting
the row stays `COMPLETED` and the file survives) rather than a changed one.

### ART-105 — a client filename longer than the filesystem's name limit produces HTTP 500

**Severity** — MEDIUM

**Zone** — "Residence of an accepted artefact, and what bounds it"

**Observation** — The caller's filename reaches the staging path with no length bound, and the
staging path's component is built by concatenation, not by a filesystem-safe truncation. When the
concatenated component exceeds the filesystem's per-name limit, `aiofiles.open` raises `OSError`,
which the route's blanket handler converts into `AppException(INTERNAL_ERROR)` — a 500 for a
value the client chose.

**Evidence** — `src/mkobi/api/routes/upload.py:205` builds the name (quoted in full in ART-102)
and `:210` opens it:

```python
210:             async with aiofiles.open(temp_file_path, "wb") as f:
```

There is no length or character validation of `sanitized_filename` anywhere between `:200` and
`:210`. The blanket handler is `src/mkobi/api/routes/upload.py:278-283`:

```python
278:     except Exception as e:
279:         logger.error("Error during file upload", exc_info=True)
280:         raise AppException(
281:             code=ErrorCode.INTERNAL_ERROR,
282:             detail="Error during file upload",
283:         ) from e
```

Executed in the `test-app` image against the resolved staging directory, writing
`upload_{uuid4()}_{raw_name}` for a range of client-supplied basenames:

```text
=== Path(filename).name on POSIX (the deployed tier) ===
  raw='../../etc/passwd'                       name='passwd'        -> CREATED len=50
  raw='/etc/passwd'                            name='passwd'        -> CREATED len=50
  raw='..\\..\\windows\\system32\\cmd.exe'     name='..\\..\\windows\\system' -> CREATED len=74
  raw='NUL'                                    name='NUL'          -> CREATED len=47
  raw='CON'                                    name='CON'          -> CREATED len=47
  raw='PRN'                                    name='PRN'          -> CREATED len=47
  raw='COM1'                                   name='COM1'         -> CREATED len=48
  raw='..'                                     name='..'           -> CREATED len=46
  raw='.'                                      name=''              -> CREATED len=44
  raw=''                                       name=''              -> CREATED len=44
  raw='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' name='aaaaaaaa...'  -> WRITE FAILED OSError: [Errno 36] File name too long
  raw='  spaced.csv  '                         name='  spaced.csv  '  -> CREATED len=58
  raw='trailing.csv.'                          name='trailing.csv.'   -> CREATED len=57
  raw='Ünïcødé.csv'                            name='Ünïcødé.csv'     -> CREATED len=55
  raw='emoji😀.csv'                             name='emoji😀.csv'     -> CREATED len=54
  raw='CON.csv'                                name='CON.csv'        -> CREATED len=51
=== ENAMETOOLONG threshold on this fs ===
  name len 200  OK
  name len 250  OK
  name len 255  OK
  name len 256  OSError
  name len 300  OSError
```

The component limit is 255 bytes and the fixed prefix `upload_` + a 36-character `uuid4` + `_` is
44, so **any client filename over ~211 bytes fails the request**. That is a legal multipart
`filename` and a legal CSV name; nothing in the request is malformed.

The same probe is the negative result for the traversal and reserved-name axes: `../../etc/passwd`,
`/etc/passwd` and the Windows UNC/drive forms all collapse to a single harmless component
(`Path(filename).name`), the reserved device names are harmless because the `upload_{uuid}_` prefix
makes them non-reserved, and unicode, emoji and trailing-dot names are all created. The un-sanitised
name is never used as a path component anywhere: `filename` reaches
`src/mkobi/services/file_processing.py:127` only as `filename.lower().endswith(...)`.

**Consequence** — An ordinary malformed-for-the-filesystem client value answers `500
INTERNAL_ERROR` with an `ERROR`-level log line and a traceback per request, where the correct RFC
7807 class is `VALIDATION_ERROR` (422). Three costs, none of them a security exposure: the 500
lands in the same error budget as real server faults and will page someone; `logger.error(...,
exc_info=True)` at `:279` writes a stack trace for what is a rejected request, so the log volume
scales with client behaviour; and the error body tells the client nothing actionable, so the same
request repeats. There is no leak — the file is never created, so the `finally` at
`src/mkobi/api/routes/upload.py:260-265` finds nothing to remove and is a correct no-op.

**Recommendation** — Bound the caller's contribution before it becomes a path, in the same
statement that already sanitises it: cap `sanitized_filename` to a length that leaves room under
255 bytes for the 44-byte prefix, truncating on a character boundary, and treat an over-long
`Content-Disposition` filename as a validation failure rather than truncating silently. This is
one branch next to `src/mkobi/api/routes/upload.py:200` and costs three lines. The preferred fix
overlaps ART-102's: dropping the caller's basename from the staging name entirely (recommended
there) removes this finding too, which is the argument for doing that first. Either way add the
case to `tests/test_upload_api.py`, which currently has no over-long-filename test.

### ART-106 — the field named `filename` in the status response carries a prose status sentence in every state

**Severity** — LOW

**Zone** — "The accepted artefact's identity: what it is called, what its name claims, and what its bytes are"

**Observation** — The accepted artefact has three identities: the caller's name (used for
admission's extension veto only), the stored name `{processing_log_id}{ext}` (derived from the
detector's verdict), and the served name. The served name is the third one that is wrong: the
status response's `filename` field is populated from `processing_logs.message`, so in every
status it holds a sentence rather than a name.

**Evidence** — `src/mkobi/services/data_service.py:360-365`:

```python
360:         return ProcessingStatusResponse(
361:             task_id=task_id,
362:             # Display-only: under D-06-A = (b) no durable filename exists, so this
363:             # best-effort text is derived from the log message and must never be
364:             # used to open or locate an artefact (see ProcessingStatusResponse).
365:             filename=log.message or "unknown",
```

The substituted values, verbatim from the three writers of that column on the pipeline path:

| status | `log.message` | served as `filename` |
| --- | --- | --- |
| `UPLOADED` | `"File uploaded successfully, awaiting processing. mode={mode}"` — `src/mkobi/services/file_processing.py:223` | that whole sentence |
| `PROCESSING` | `"Processing started"` — `src/mkobi/workers/data_worker.py:930` | `"Processing started"` |
| `COMPLETED` | `"Processing completed successfully: {rows} rows processed"` — `src/mkobi/workers/data_worker.py:891` | that whole sentence |

The same contract's upload response carries a real name in the same field —
`src/mkobi/services/data_service.py:189-196` ends with
`filename=filename or "unknown"`, i.e. the caller's own basename. The declared type agrees on the
name and nothing else — `frontend/src/shared/types/api.types.ts:256-258`:

```typescript
256: export interface ProcessingStatusResponse {
257:   task_id: string
258:   filename: string
```

and `frontend/src` contains exactly two occurrences of `filename`, both in type declarations —
nothing renders it.

**Consequence** — No runtime consequence in this deployment: no component reads the field, and the
value is never used to locate an artefact (nothing can — the stored name is not derivable from
any record, by design under D-06-A = (b)). The consequence is to the contract: an API consumer
that stores `filename` from the upload response as an artefact's identity and later reconciles
against the status response finds two different meanings under one field name, and the field
promises a locator the system explicitly does not provide. The comment at `:362-364` states the
constraint accurately, which makes the field name the remaining defect.

**Recommendation** — Rename the field to what it is (`display_name`), or drop it from the status
payload and let clients read `message`, which already carries the same text under an honest name.
It is a declared response model, so the change is visible in OpenAPI and in
`frontend/src/shared/types/api.types.ts` — a coordinated rename, not a silent one, and not a
behavioural change any current consumer depends on. `docs/03-processing/processing-api.md`'s
"Check Processing Status" section must move with it.

### ART-107 — the bundle resolver's docstring promises CWD-independence the code does not provide, and the alias its ruling introduced is unread

**Severity** — LOW

**Zone** — "The built interface bundle as a served artefact: what is served from disk, and what changes when it is absent"

**Observation** — The prior finding here is remediated: the mount and the `/health/detailed`
component now share one predicate, so the route table and the health verdict cannot drift, and a
missing or index-less bundle reports `unavailable` in the same component that would report a
broken one. What remains is a documentation contradiction and an accessor nobody reads.
`resolve_frontend_bundle` resolves the configured directory with `Path(...).resolve()`, which makes
it absolute *relative to the process working directory* — not independent of it — and says
otherwise.

**Evidence** — `src/mkobi/app.py:501-522`:

```python
501: def resolve_frontend_bundle() -> tuple[Path, bool]:
502:     """Resolve the configured SPA bundle directory and its servability.
...
504:     The single source of truth for where the built frontend lives and whether it
505:     can be served. The directory is the configured ``FRONTEND__DIST_DIR``
506:     (default ``frontend/dist``) resolved to an absolute path, so the reported
507:     location is meaningful regardless of the process working directory. The
...
520:     static_dir = Path(get_config().frontend.dist_dir).resolve()
```

The same repository states the opposite property of the same default,
`src/mkobi/config.py:629-631`:

```python
629:     # Defaults to the CWD-relative value that was hard-coded before, so the
630:     # container's working directory and the served bundle are unchanged.
631:     dist_dir: str = Field(default="frontend/dist", alias="dist_dir")
```

No compose service sets `FRONTEND__DIST_DIR` (verified by grep across
`docker/docker-compose.yml`), so the shipped deployment satisfies the relative literal by working
directory alone: `docker/Dockerfile:82` (`WORKDIR /app`), `docker/Dockerfile:229`
(`COPY --from=frontend-builder /app/frontend/dist ./frontend/dist`) and `docker/Dockerfile:242`
(`CMD ["uvicorn", "src.mkobi.main:app", …, "--workers", "4"]`).

The ruling that introduced the shared predicate also introduced an alias for it,
`src/mkobi/config.py:1156-1159`:

```python
1156:     @property
1157:     def frontend_dist_dir(self) -> str:
1158:         """Alias for FRONTEND__DIST_DIR; the built SPA bundle location."""
1159:         return self.frontend.dist_dir
```

A repository-wide search for `frontend_dist_dir` returns exactly one hit — this definition. The
predicate reads `get_config().frontend.dist_dir` directly, so the alias is unread.

**Consequence** — No runtime consequence in the shipped image, and no drift risk: both the mount
and the health component call the one helper, so they always agree — a process started from a
directory other than `/app` reports `static_files: unavailable` and registers no catch-all mount,
consistently. The cost is that a reader of `app.py` believes the location is CWD-independent and
a reader of `config.py` knows it is not, and a reader of the settings surface finds an alias that
no consumer uses. The ruling's stated goal — "one configured, **resolved** bundle path consumed by
both the mount and the health component" — is met for the predicate and unmet for the accessor.

**Recommendation** — Correct `src/mkobi/app.py:504-507` to say the directory is resolved against
the process working directory, which is what `Path.resolve()` does and what `config.py:629-630`
already says; that is a one-sentence fix with no behaviour change and it removes the
self-contradiction. Separately, either route the predicate through the existing
`Settings.frontend_dist_dir` alias or delete the alias — an accessor that exists to be the single
read path for a value and is read by nobody is a second, unwritten contract. No other file needs a
change for *this* finding: `docs/11-guides/docker.md` does not describe the app image's bundle
location at all (its own drift is ART-108's), and `docs/03-processing/processing-api.md` claims no
CWD-independence.

### ART-108 — the runbook still describes the production bundle carrier that was removed

**Severity** — LOW

**Zone** — "The built interface bundle as a served artefact: what is served from disk, and what changes when it is absent"

**Observation** — The bundle's carrier changed: it now ships *inside* the `mkobi/nginx` image and
the host bind mount was deleted. The production-edge section of the deployment runbook was not
updated with it and still tells the operator that `frontend/dist` is mounted into the edge and
that a prior host build is its prerequisite. It also names a template as a mounted file and claims
a tmpfs the compose file deliberately omits.

**Evidence** — The runbook, `docs/11-guides/docker.md:453-459`:

```markdown
453: - **Volumes:** `docker/nginx/nginx.conf` (read-only), `frontend/dist` (read-only)
454: - **Requires a prior frontend build** — the dist directory is mounted, not built
455: - **Security hardening:**
456:   - `read_only: true` — immutable root filesystem
457:   - `tmpfs` for runtime-writable paths: `/tmp`, `/var/cache/nginx`, `/var/run`,
458:     `/var/log/nginx`
459:   - All volumes mounted read-only (`:ro`)
```

The compose file records the removal at `docker/docker-compose.yml:342-347`:

```yaml
342:   # The production edge. Ruling B6 (OPS-003 / VAL-10-006): the client bundle
343:   # ships INSIDE this image, built from the ``frontend-nginx`` stage in
344:   # docker/Dockerfile, which copies the SPA out of the same ``frontend-builder``
345:   # stage the app image uses. The host ``../frontend/dist`` bind mount is gone:
346:   # that directory is git-ignored twice and unversioned, so a host directory was
347:   # the production carrier and the edge served whatever happened to be on disk.
```

and the build now bakes it: `docker/Dockerfile:212` —
`COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html`, with `:213-214` failing
the build if `index.html` is absent. Three further claims in the same runbook paragraph are stale
for the same reason: `docker/nginx/nginx.conf` is `docker/nginx/nginx.conf.template`; the
`/var/log/nginx` tmpfs is "intentionally absent: both logs stream to stdout/stderr"
(`docker/docker-compose.yml:383-384`); and "all volumes mounted read-only" no longer describes the
service's volume set at all.

**Consequence** — No runtime consequence today: the shipped configuration is the image copy, the
build fails loudly on an empty bundle, and the app's own copy is baked the same way
(`docker/Dockerfile:229`). The cost is operational. An operator following this runbook concludes
(a) a missing or stale host `frontend/dist` can break the production edge, when the removal's own
rationale was that exactly that indirection is the hazard, and (b) a host-side `npm run build` is a
prerequisite for bringing the edge up, when it is a build-time step inside the image. Both
conclusions send the operator to debug a host directory that no service reads. The same paragraph
also tells them to expect a `/var/log/nginx` tmpfs and a `nginx.conf` file, neither of which the
service has, so the runbook's production-edge section is wrong on four of its seven lines.

**Recommendation** — Rewrite `docs/11-guides/docker.md:453-459` from the resolved compose file
rather than from memory: the service mounts `docker/nginx/nginx.conf.template` (rendered at
startup) and no bundle directory, the bundle is baked at `docker/Dockerfile:212` with the build
failing on an empty one, and the tmpfs set is `/tmp`, `/var/cache/nginx`, `/var/run` per the
service definition. Do this in the same pass as ART-107's `app.py:504-507` correction — both are
the same class of drift (a documentation surface that outlived the change it described), and
`docs/00-overview/doc-maintenance-rules.md` is the rule the pair violates. `docs/11-guides/docker.md:916`
(`/app/data/uploads`, "Potential permanent file storage") is stale in the same way — no code writes
that directory — but the per-user upload tree it half-describes is `TOPO-111`'s, so it is left to
that finding's owner rather than duplicated here.

## Distribution

Five of the eight findings sit on the upload path's boundary with the filesystem
(`src/mkobi/api/routes/upload.py` and the staging-directory naming rules), and that is where the
phase's weight is. Two more sit on the removal path inside the worker and the reconciler's
published output. Nothing in this phase is a data-store or a schema defect: `ProcessingLog`
carries no name and no path, which is what makes ART-102 and ART-104's detector gaps possible but
also what keeps the reconciliation question (block 3) structurally empty. The three `LOW` findings
are documentation-surface drift, and two of the three (ART-107, ART-108) are the same class on the
same subsystem: a documentation surface that outlived the change it described.

- `src/mkobi/api/routes/upload.py` — ART-102 (staging name shape), ART-105 (name length)
- staging-directory naming rules (`upload.py:205` vs `file_cleanup.py:92`) — ART-102
- `src/mkobi/workers/data_worker.py` — ART-104 (unguarded success unlink), ART-103 (discarded `failed`)
- `src/mkobi/services/file_processing.py` — ART-101 (detector), ART-106 (served name, via `data_service.py`)
- `src/mkobi/app.py`, `src/mkobi/config.py`, `docker/` vs `docs/11-guides/docker.md` — ART-107, ART-108

## Cross-Finding Analysis

Two causes, not eight independent defects.

**The caller's basename is used as a filesystem component when the system's own naming rule says
it should not be.** ART-102 (the name shape decides whether the reclaimer can see the file) and
ART-105 (the name length decides whether the request 500s) are the same decision at
`src/mkobi/api/routes/upload.py:205`. One change — naming the staging file from the artefact's
identity instead of the caller's basename — closes both, and it also removes a client-controlled
string from every path in the staging area.

**A count is computed for a failure mode and then dropped before it reaches any reader.** ART-103
(`CleanupResult.failed` discarded at `data_worker.py:1564`) and ART-104 (the success unlink's
failure reported as a processing failure rather than as a removal failure) are the same defect
from two sides: the system has exactly one removal site whose outcome is not reported as a removal
outcome. ART-104 additionally violates `ProcessingStatus.valid_transitions()`, which
`processing_log_service.py:36` enforces on every other path.

ART-101, ART-106, ART-107 and ART-108 are independent of each other and of both causes, with one
pairing: ART-107 and ART-108 are both the built bundle's documentation surface lagging the change
that fixed it, and should be corrected in one pass.

## Roadmap

Ordered by cause, not by severity. Steps 1 and 2 are independent of each other and of step 3.

1. **Close ART-102 and ART-105 together — stop letting the caller's basename be a path component.**
   Name the staging file from the artefact's identity (`upload_{uuid4()}{ext}`, `ext` from the
   `FileExtensionEnum` the admission gate already enforces) at
   `src/mkobi/api/routes/upload.py:205`. Must be true before step 3: the glob-versus-name
   disagreement that ART-103's sibling depends on disappears with it, and re-testing the sweep's
   visibility afterwards is meaningless if the producer's names changed. Do **not** resolve this by
   moving admission onto `get_user_temp_dir` — `TOPO-111` names that trap. Correct
   `docs/03-processing/file-cleanup.md:99-100` in the same step; it is currently the wrong half of a
   self-contradiction.
2. **Close ART-103 — publish `failed`.** Add `last_failed_count` to `ReconcilerStatus` and include
   it in the `/health/detailed` component, or pass the whole `CleanupResult` to `record_success`,
   and fix `reconciler_lease.py:86-92`'s docstring either way. Independent of step 1 and safe to land
   first; it needs no migration, so it does not wait on phase 14's C06-3 or on phase 03's B3.
3. **Close ART-104 — guard the success-path unlink.** Wrap `data_worker.py:1035-1037` in its own
   `try/except OSError` at WARNING so a removal fault cannot be reported as a processing fault, and
   add a test that makes the success-path `unlink` raise once and asserts the row stays `COMPLETED`
   and the file survives for the sweep. Do not add a state-machine check to
   `_update_processing_log_status` — see the finding. Because step 1 changes which files the sweep
   can see, run this step's test after step 1.
4. **Close ART-101 — move the CSV-ness decision off the generic text classifier,** and add the real-
   detector cases to `tests/test_mime_admission_contract.py` so the thresholds are measured. Whichever
   branch is taken, `docs/03-processing/processing-api.md:60` gains the row-count / final-newline
   clause. Independent of steps 1-3; sequence it after them only because it changes an externally
   visible 415 condition and is easier to attribute on its own.
5. **Close ART-107 and ART-108 — documentation-surface corrections for the built bundle,** one
   docstring, one dead accessor and one stale runbook paragraph. Do them in one pass against the
   resolved compose file: `app.py:504-507` and `docs/11-guides/docker.md:453-459` are the same
   drift, and ART-108's paragraph additionally misnames a template as a mounted file and claims a
   tmpfs the service omits. No runtime behaviour changes in either.
6. **Close ART-106 — one response-model field.** Rename `filename` to `display_name` or drop it from
   the status payload. It is a coordinated contract change: `src/mkobi/models/`, OpenAPI, and
   `frontend/src/shared/types/api.types.ts` move together.

## Rollout Safety

Step 1 changes staging file names. Nothing outside the staging directory selects a file by name:
`cleanup_stale_temp_files` globs (it will simply see the new names, which is the point), the worker
receives its path as a job-payload string (`enqueue_processing_job`, `file_processing.py:263-269`)
and never reconstructs it, and the route's `finally` holds the same `temp_file_path` object. No
migration is needed and no artefact written before the change is affected, because a file's *age*,
not its name, decides the sweep. The one thing to verify afterwards is that the new names still match
`*.csv*` for every admitted MIME type — `MimeTypeEnum.extension` maps to `.csv` or `.csv.gz` only,
so this holds, but assert it in a test rather than by reading the enum. Revert is a one-line revert
plus a restart; in-flight files written under the old names become invisible to the sweep, so on
revert drain `app_data/tmp_uploads` manually before rolling back.

Step 4 changes which uploads are admitted, which is externally observable: some uploads that today
return `415` will be accepted. That is the intended direction and it can only admit files the
loader can already read, but if any client has come to depend on the current refusal as a
validation signal, it will stop firing. Verify by replaying the buffer shapes in ART-101's evidence
table through the running stack before deploying, and keep the refusal for genuinely malformed
input — the loader's reader boundary at `docs/03-processing/processing-api.md:196` is where that
belongs.

Steps 2, 3, 5 and 6 change no externally observable behaviour beyond one added key in an
admin-only health response (step 2) and one renamed response field (step 6, which is a coordinated
contract change and must land in the backend and the frontend together). Steps 2 and 3 do not touch
`data_worker.py`'s transaction scope, so they do not collide with phase 03's B3 — the second does
edit `data_worker.py`, but only the unlink at `:1035-1037` and its immediate surroundings, not the
`async with session.begin():` block that B3 restructures. If phase 03's B3 lands first, this step
re-applies cleanly; nothing here depends on the unlink's current position relative to the commit,
only on its position relative to the `try:`.

## Appendices

### Appendix A — Block coverage ledger

| Block | Verdict | Evidence anchors |
| --- | --- | --- |
| 1 — the accepted artefact's identity | **2 findings** (ART-101, ART-106) | `file_processing.py:42-45`, `:48-82`, `:127-138`, `:206`; `MimeTypeEnum.extension` `enums.py:138-149`; runtime verdict table; `data_service.py:189-196`, `:360-365` |
| 2 — residence and what bounds it | **2 findings** (ART-102, ART-105) | `upload.py:163-230`, `:260-265`; `file_cleanup.py:73-101`; `config.py:577-594`, `:1006`, `:1020-1023`; runtime glob-visibility and name-length tables |
| 3 — reconciliation, both directions | **no findings** | `ProcessingLog` has seven columns and no name/path (`processing_logs.py:30-72`); `find_task_file`, `DataService.trigger_processing` and the `IDataService` declaration are gone (grep: zero hits); the only `glob(` in `src/` is the age sweep (`file_cleanup.py:92`). Neither direction can diverge because no record names an artefact, and that is the ruled, documented state (D-06-A = (b)); the naming-rule disagreement that does exist is filed as ART-102 under block 2 |
| 4 — removal and the record of a failed removal | **2 findings** (ART-103, ART-104) | `file_cleanup.py:47-135`; `data_worker.py:935-1085`, `:1562-1564`; `reconciler_lease.py:82-96`; `app.py:479-486`; `enums.py:71-79` vs `processing_log_service.py:36-44` |
| 5 — the one-time secret outside the database | **no findings** | Both creation paths compute `credential_stored` from `store`'s `bool` (`auth_service.py:601-619`, `:694-712`) and both admin endpoints return the service result verbatim (`admin.py:439`, `:332`), so the administrator is told when the credential is not retrievable. `retrieve` fails loud (`temp_password_store.py:154-158`) and both retrieval operations map it to `503 SERVICE_UNAVAILABLE` (`admin.py:529-533`), so an outage is no longer indistinguishable from an absent token. Single use holds: `GET`+`DELETE` share one `MULTI/EXEC` (`temp_password_store.py:144-147`). The TTL is wired from configuration (`deps.py:168-171`), so no dead key remains. The absence of a revocation path is a written, deliberate acceptance (D-06-G = (c)) stated in the class docstring `temp_password_store.py:42-69`; re-filing it would re-report a documented decision, not a defect |
| 6 — the built interface bundle as a served artefact | **2 findings** (ART-107 documentation/accessor, ART-108 runbook drift; the mount/health divergence itself is remediated) | `app.py:501-522`, `:543-590`, `:436-439`; `config.py:620-633`, `:1156-1159`; `docker/Dockerfile:82`, `:212-214`, `:229`, `:242`; `docker/docker-compose.yml:342-347`, `:383-384`; `docs/11-guides/docker.md:453-459` |
| 7 — which process reclaims an artefact | **no findings** | Process set derived in Appendix C. `rq-worker` does not run the reconciler (`rq_worker_wrapper.py:192-238`), so exactly one sweeper exists under the lease (`app.py:201-207` → `data_worker.py:1562`). A second remover meeting an already-removed artefact is a silent no-op on the worker side (`data_worker.py:1035`'s `exists()` guard) and a `DEBUG`-level `already_gone` on the sweep side (`file_cleanup.py:108-115`), and both are recorded rather than logged as errors — the one removal outcome that *is* recorded |
| 8 — is an accepted artefact ever returned to a caller | **no findings** | The returning-surface inventory is **empty**. No endpoint serves an accepted artefact: grep for `content_disposition|Content-Disposition|FileResponse|StreamingResponse|attachment;` across `src/` returns exactly one `FileResponse` — `app.py:580`, the SPA `index.html` — plus three `filename` reads that are response-model population (`upload.py:244`, `data_service.py:181`, `:365`). No component reads an artefact from storage to decide what a caller hears. ART-106 is filed under block 1 because the defect is in a name's identity, not in a returning surface |

### Appendix B — The three identities, and which one decides each later read

| Identity | Value | Decides |
| --- | --- | --- |
| caller's name | `UploadFile.filename`, verbatim | the extension veto at `file_processing.py:127-138` and the staging filename at `upload.py:205`; **nothing else** — never the stored name, never the reader |
| stored name | `{processing_log_id}{ext}`, `ext` from `MimeTypeEnum.extension` (`file_processing.py:206`) | the reader: the worker is handed the whole path in its job payload (`file_processing.py:263-269`) and opens it with `CSVLoader` (`data_worker.py:703-708`); also what the `*.csv*` sweep must be able to see |
| type from content | `magic.from_buffer` over the first 2048 bytes (`file_processing.py:42-45`) | admission only (`file_processing.py:69-82`) and, through `MimeTypeEnum.extension`, the stored name |

All three admitted MIME types map to `.csv` or `.csv.gz`, so the stored name always matches the
sweep's glob — verified by execution (`text/csv → .csv`, `application/gzip → .csv.gz`,
`application/x-gzip → .csv.gz`). The prior finding that the caller's name decided parsing while the
content decided admission is remediated: nothing selects a reader by name any more.

### Appendix C — Process inventory (block 7)

| Process | Reads artefacts | Creates artefacts | Removes artefacts |
| --- | --- | --- | --- |
| `app` (4 uvicorn workers, `docker/Dockerfile:242`) | the staged file, for validation (`file_processing.py:194`) | the in-flight staged file (`upload.py:205`) and the accepted artefact by `Path.replace` (`file_processing.py:242-244`) | the staged file, in the route's `finally` (`upload.py:265`) and on the size ceiling (`upload.py:217`); the moved file on enqueue failure (`file_processing.py:272`); and it runs the single lease-guarded age sweep (`app.py:201-207` → `data_worker.py:1562`) |
| `rq-worker` | the accepted artefact, to load it (`data_worker.py:703-708`) | — | the accepted artefact, on the success and failure edges of both the test path (`:941`, `:962`) and the production path (`:1036`, `:1058`) |
| `migrate` | — | — | — (sets `UPLOAD__TEMP_DIR` at `docker/docker-compose.yml:102` only so `Settings._ensure_upload_dir()` has a writable path; the service mounts no volume and writes only SQL) |

Both `app` and `rq-worker` mount `app_data` read-write and run as the image's `app` user
(verified: `docker inspect mkobi-app-1` and `docker inspect mkobi-rq-worker-1` both report
`Config.User = app`, `volume mkobi_app_data → /app/data rw=true`). Neither mounts a tmpfs over the
artefact area; `rq-worker` mounts `/tmp` as a 128 MB tmpfs (`docker/docker-compose.yml:303-305`),
which is unrelated to the artefact area. `LOGGING__LOG_FILE` is deliberately unset on both
(`docker/docker-compose.yml:159-161`), so the earlier "artefacts and the rotating log share one
volume" coupling is gone — logs stream to stdout.

### Appendix D — Removal census (block 4)

Nine removal sites in `src/`, re-grepped at `HEAD f8581e0` (the previous census's ninth site has
not moved and the retired `cleanup_task_files` / `cleanup_old_processing_logs` are still absent):

| # | Site | Guard |
| --- | --- | --- |
| 1 | `src/mkobi/api/routes/upload.py:217` | `unlink(missing_ok=True)`, on the streaming size ceiling |
| 2 | `src/mkobi/api/routes/upload.py:265` | `exists()` + `unlink(missing_ok=True)`, in the route's `finally` |
| 3 | `src/mkobi/services/file_processing.py:272` | `unlink(missing_ok=True)`, the enqueue-failure compensation |
| 4 | `src/mkobi/workers/data_worker.py:941` | `exists()` only — **no `try`** around the `unlink` (ART-104) |
| 5 | `src/mkobi/workers/data_worker.py:962` | `exists()` + `try/except BaseException` → WARNING |
| 6 | `src/mkobi/workers/data_worker.py:1036` | `exists()` only — **no `try`** around the `unlink` (ART-104) |
| 7 | `src/mkobi/workers/data_worker.py:1058` | `exists()` + `try/except BaseException` → WARNING |
| 8 | `src/mkobi/services/file_cleanup.py:101` | `try` with `FileNotFoundError` and `OSError` arms separated |
| 9 | `src/mkobi/utils/file_utils.py:42` | `shutil.rmtree` — **no production caller**; already owned by `TOPO-111` |

Plus one move: `src/mkobi/services/file_processing.py:244` (`Path.replace`). One non-production
caller: `tests/conftest.py:158` (`cleanup_stale_temp_files(max_age_hours=0)`). Sites 4 and 6 are
the same shape; only the production one (6) has a committed transaction behind it, and it is the one
ART-104 is about.

### Appendix E — Method, and what could not be verified here

**Executed.** Three read-only probes inside the `mkobi-test` `test-app` container
(`docker compose -p mkobi-test -f docker/docker-compose.test.yml run -T --rm --no-deps test-app python -`),
which is the only tier in this environment with `libmagic1` (the host venv raises
`ImportError: failed to find libmagic`, per `.kilo/rules/commands.md`): the resolved
configuration surface; the `MimeTypeEnum` → extension mapping; sixteen libmagic verdicts over
written buffers; the `*.csv*` sweep's visibility over the eight in-flight name shapes; sixteen
filename-sanitisation and traversal cases; and the filesystem's per-name limit. Probes wrote only
to `/tmp` inside a throwaway container; no repository file was created, modified or deleted, and
no database, Redis key or Docker volume was written.

**Read in full.** `src/mkobi/api/routes/upload.py`, `src/mkobi/services/file_processing.py`,
`src/mkobi/services/file_cleanup.py`, `src/mkobi/workers/data_worker.py` (artefact regions),
`src/mkobi/core/temp_password_store.py`, `src/mkobi/core/task_queue.py`,
`src/mkobi/core/reconciler_lease.py`, `src/mkobi/rq_worker_wrapper.py`,
`src/mkobi/utils/file_utils.py`, `src/mkobi/services/data_service.py`,
`src/mkobi/services/processing_log_service.py`, `src/mkobi/db/models/processing_logs.py`,
`src/mkobi/app.py` (bundle and health regions), `src/mkobi/config.py` (upload, frontend, stale and
upload-dir regions), `src/mkobi/models/enums.py` (MIME/extension/status/error enums),
`docs/03-processing/file-cleanup.md`, `docs/03-processing/processing-api.md` (admission, naming
and failure-classification sections), `docker/docker-compose.yml` (artefact services),
`docker/Dockerfile` (bundle and data-directory stages), and the artefact-relevant regions of
`tests/conftest.py`, `tests/test_file_cleanup.py`, `tests/test_mime_admission_contract.py`,
`tests/test_upload_api.py`.

**Repository-wide searches.** `unlink|rmtree|mkdtemp|NamedTemporaryFile|TemporaryDirectory|gettempdir|tempfile`;
`glob(|.csv*|rglob`; `get_user_temp_dir|cleanup_temp_dir|validate_file_extension|file_utils`;
`upload_temp_dir|_ensure_upload_dir|temp_dir`; `content_disposition|FileResponse|StreamingResponse`;
`files.failed|.failed|record_failure|record_success`; `frontend_dist_dir`; `valid_transitions`;
`ProcessingLogService|_validate_transition|INVALID_TRANSITION`; `frontend_dist_dir`; `filename` in
`frontend/src`; `ART-[0-9]` across `docs/` and `.ai/`.

**Runtime verification against the running dev stack.** `docker inspect` on `mkobi-app-1` and
`mkobi-rq-worker-1` (user and volume mounts); 40 hours of `mkobi-app-1` logs scanned for
`Killed|OOM|out of memory|File name too long|Errno 36|Error during file upload|Temp file deleted`
— **zero hits**; `mkobi-rq-worker-1` logs showing a single long-lived worker
(`87ea90a14ac2409f86b84a5329505e76`) cycling registry cleanups, i.e. no restarts and no crashes.

**Not verified, and why.** (a) The *contents* of the live `app_data` volume were not listed —
reading a container filesystem needs `docker exec`, which the auditor permission set marks `ask`;
ART-102 and ART-104 are therefore filed from the code path plus reproduction of the mechanism, not
from an observed residue in a running deployment, and both say so. (b) The
`STALE_FILE_THRESHOLD_HOURS`-below-job-lifetime race in ART-104 was not provoked end to end
through the HTTP surface; the state-machine violation it produces is proven statically and the
`unlink` fault class is a documented `OSError`. (c) No finding was raised about the transport-level
request-body bound: the whole body is received by the ASGI server before the endpoint runs, and the
phase task assigns that surface to phase 07. (d) The repository is under concurrent modification;
`frontend/src/shared/types/api.types.ts` is currently dirty in the working tree (six modified chart
files plus this type file), and ART-106's citation to it was re-verified against the current file
at report-writing time.

### Appendix F — Finding-ID namespace collision (disclosed as required)

The phase task assigns the prefix `ART-`. **`ART-001` … `ART-009` are already occupied** and must
not be reused. Verified by grep:

| Referencing site | What it says |
| --- | --- |
| `docs/SPEC.md:235` (change-log row 3.32) | "audit findings `ART-001` … `ART-009`; validation defects `VAL-06-001` … `VAL-06-010`" |
| `.ai/plans/_code-context/06-file-artifacts-code-context.md` | the per-finding context for `ART-001` … `ART-009` and their validation verdicts |
| `.ai/plans/_code-context/06-file-artifacts-reconciliation-note.md` | the `D-06-*` rulings keyed to `ART-001` … `ART-009`, plus the anchor table |
| `.ai/tasks/B3-txn-003-durable-processing-transitions.yaml:505` | "phase 06's ART-007 owns that" |
| `.ai/audit/06-file-artifacts/findings.md` (this report's own path) | previously deleted from the working tree; the `ART-001` … `ART-009` report is referenced by the two notes above but is **not present on disk** |

The prior findings are therefore *referenced* but not *filed here*. Each was re-derived against the
current tree before being excluded, because most have been remediated: `ART-001` (name-derived
stored extension) — remediated, `file_processing.py:206`; `ART-002` (no per-record artefact selector)
— remediated, `find_task_file` / `trigger_processing` gone and `ProcessingLog` still carries no
path; `ART-003` (area bounded by age only, sharing a volume with the log) — the log coupling is
remediated (`docker/docker-compose.yml:159-161`) and the missing byte ceiling is a written,
deferred acceptance owned by phase 10 under C06-04, so it is not re-filed here; `ART-004` (artefact
destroyed before the derived work commits) — remediated, `data_worker.py:1027-1038`, with its
residual filed fresh as ART-104; `ART-005` (a failed removal is a log line and nothing else) — the
counting half is remediated and the health-surface residual is filed fresh as ART-103;
`ART-006` (approval reports a retrievable one-time password regardless) — remediated,
`credential_stored` is surfaced on both admin endpoints and `retrieve` fails loud; `ART-007` (the
bundle's presence changes the route table; health calls an unservable bundle available) — remediated
by the shared predicate at `app.py:501-522`, with the residual filed fresh as ART-107; `ART-008`
(concurrent reclaimers log the loser's collision as ERROR) — remediated, `file_cleanup.py:108-122`
separates the two and the sweep is lease-guarded; `ART-009` (the declared allowed-MIME set is not
the one enforced) — remediated, the key is absent from `config.py` and `settings/app.yaml` and
libmagic is a hard dependency. Also excluded as already-owned: **`TOPO-111`** (phase 01, confirmed
— the unused `get_user_temp_dir` / `cleanup_temp_dir` pair and the per-user upload tree
`AGENTS.md` §5 declares), which ART-102's recommendation must not duplicate.

This report uses `ART-101` … `ART-108`. No identifier from either occupied family is reused.
