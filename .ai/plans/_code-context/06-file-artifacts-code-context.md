---
phase: 06-file-artifacts
executed: 2026-10-01
executor: code-context-auditor (phase 1)
role: analysis only — no remediation design, no production-code change
head: 21748957c7e9a20d6ebd442bb81c74251c490f58
report-under-decomposition: .ai/audit/99-validation/06-file-artifacts-validated-findings.md
upstream-findings: .ai/audit/06-file-artifacts/findings.md
id-note: >-
  The briefing names the per-finding IDs `FA-*`. No `FA-` identifier exists anywhere in
  `.ai/audit/**` (repository-wide grep returns zero hits). The report under decomposition carries two
  identifier families: the audited phase's own findings `ART-001`…`ART-009` and the validation's
  report-level defects `VAL-06-001`…`VAL-06-010`. Every ID of both families is covered below;
  `FA-*` is read as `ART-*`.
anchor-authority: symbols, modules, routes, config keys, tables — line numbers are drift evidence only
---

# 06-file-artifacts — Code Context (Phase 1)

## 1. Scope and method

**Read on disk, not HEAD-assumed.** `services/file_processing.py`, `services/file_cleanup.py`,
`services/auth_service.py`, `services/data_service.py` (anchor sites only), `workers/data_worker.py`,
`core/task_queue.py`, `core/temp_password_store.py`, `app.py`, `db/starter.py`, `db/models/processing_logs.py`,
`api/routes/upload.py`, `api/routes/admin.py`, `api/deps.py`, `config.py`, `settings/app.yaml`,
`data/loaders/loader.py`, `utils/file_utils.py`, `docker/Dockerfile`, `docker/docker-compose.yml`,
the vendored `rq 2.9.1` worker package, and the tests/docs the reports cite.

**Verified by execution (host, `uv run`).**

1. `get_config().allowed_mime_types` → `['text/csv','application/gzip','application/x-gzip']`, byte-identical to
   `MimeTypeEnum.allowed_values()` (`equal = True`). Also: `lazy_threshold_mb=10.0`, `max_file_size=104857600`,
   `stale_file_threshold_hours=24`, `temp_password_ttl_seconds=86400`, `log_file=None`,
   `upload_temp_dir=C:\Users\Om\AppData\Local\ZOO\mkobi\tmp_uploads`.
2. `CSVLoader().load_csv` on plain-CSV bytes named `*.csv.gz`: 0.000 MB and 6.10 MB (eager branch, ≤
   `lazy_threshold_mb`) → `pyo3_runtime.PanicException`, `mro=['PanicException','BaseException','object']`,
   `isinstance(e, Exception) == False`. **15.26 MB (lazy branch) → `LOADED (4000000, 1)`**, no exception of any
   class. This independently reproduces VAL-06-004's bound: `_read_csv_lazy` does not select gzip, it hands the
   path to `pl.scan_csv`, so the largest mislabelled artefacts read correctly and only the small ones panic.
3. `rq 2.9.1` `worker/base.py::perform_job` wraps job execution in a **bare `except:`** (line 1563) catching
   `BaseException`, marking the job `FAILED` and calling `handle_exception` + `handle_job_failure`. The consumer
   process survives a `PanicException`.

**Verified by reading only.** Every runtime claim about the deployed topology, the container filesystem,
the Docker image, and the ASGI route table. No container was started, no database or Redis key was written,
no production code was modified. (The test database is Docker-only per `.kilo/rules/commands.md`.)

**HEAD-vs-worktree split — the briefing's premise is stale.** `HEAD = 2174895`
("fix(user): own the unit of work for user writes and classify the email race"). `git status --porcelain --
src/ tests/ docker/ docs/ alembic/` returns **empty**: the edits the briefing described
(`api/deps.py`, `api/routes/admin.py`, `db/session.py`, `interfaces/service_interfaces.py`,
`services/user_service.py`, `tests/test_admin_user_management.py`, new `tests/test_user_service.py`) were
**committed as `2174895`**, together with `tests/test_token_revocation.py` and `tests/test_users_api.py`.
`git show --stat 2174895` confirms all nine paths. The only dirty tracked paths are 20 deletions under
`.ai/` and 15 under `frontend/coverage/` (generated artefacts) plus untracked `.ai/plans/*` and
`.ai/tasks/B1-txn-001-transaction-ownership.yaml`. **No artifact-subsystem file is dirty.** Every verdict
below is therefore identical at HEAD and in the working tree; there is no in-flight phase-06 work.

**The load-bearing difference from the report's baseline.** The audit ran at `c3c0a61`; the validator read
`c3c0a61` + a dirty tree. Six commits have landed since, three of which restructure the artifact subsystem
out from under the findings:

| commit | subject | phase-06 consequence |
|---|---|---|
| `3848e7a` | RQ replaces the in-process `asyncio.Queue` | **removes ART-001's consumer-death chain and ART-008's "four sweepers in one container" premise**; adds a second container (`rq-worker`) that reads *and removes* the same volume |
| `2de4156` | approval transaction moves into `AuthService`, credential written **after** commit | **reverses the ordering ART-006's recommendation demands** |
| `eeb9a5e` / `14be95c` / `ce537d7` | unread config fields removed, `upload.temp_dir` deleted from `app.yaml` | changes where `upload_temp_dir` resolves on a host process (ART-003) |

## 2. Per-finding context

### ART-001 — renamed upload kills the only process that reclaims artefacts (HIGH)

**Core claim substantiated; consequence refuted by `3848e7a`.**

| element | today |
|---|---|
| stored name derived from the caller's filename | **present** — `file_processing.py::process_upload_with_session` computes `file_ext` from `detect_file_type(filename)`; `loader.py::detect_file_type` lowercases and matches `.csv.gz` / `.csv` |
| admission decided from bytes only, set contains both members | **present** — `file_processing.py::validate_mime_type` reads `MimeTypeEnum.allowed_values()` (three members, verified at runtime); nothing compares it to `file_ext` |
| only `:295-302` selects gzip | **present** — `CSVLoader._read_csv` opens `gzip.open`; `CSVLoader._read_csv_lazy` only logs at the `.gz` test and then calls `pl.scan_csv(file_path, …).collect()` |
| `PanicException` is a `BaseException` | **verified by execution**; `CSVLoader.load_csv`'s `except Exception` misses it |
| `app.py::lifespan` `queue_worker` loop, `asyncio.create_task(queue_worker())` | **gone** — `app.py::lifespan` starts only `start_stale_processing_cleanup_task`; `core/task_queue.py` is a 79-line RQ seam (`get_rq_queue`, `enqueue_job`, `DEFAULT_QUEUE_NAME`) with no `TaskQueue`, no `process_next` |
| consumer death → "a quarter of uploads stop working" | **refuted**: rq 2.9.1 catches `BaseException` per job. The blast radius is now a per-job failure, a job left in the RQ `FailedJobRegistry`, an artefact **retained** on the volume (the unlink at `data_worker.py:546-548` never runs) and a `processing_logs` row rolled back to `uploaded`, repaired only at the next process boot by `mark_orphaned_uploaded_logs_failed` |
| `--workers 4` multiplicity | still true — `docker/Dockerfile` `CMD ["uvicorn", …, "--workers", "4"]` — but it now multiplies API workers, not consumers |

**Seams.** `file_processing.py::validate_mime_type` (return-type change), `::process_upload_with_session`
(`file_ext` derivation), `loader.py::CSVLoader._read_csv` (make the reader boundary total), and
`data_worker.py::_run_with_transaction`'s `except Exception` chain. The report's `app.py` `BaseException`
guard has **no target any more** — the loop it wrapped does not exist.

### ART-002 — neither direction of store-versus-record divergence is detectable (HIGH)

**Substantiated, anchors exact; the remedy's two branches are still mutually exclusive.**

* `ProcessingLog` declares exactly `id`, `dashboard_id`, `status`, `message`, `started_at`, `finished_at`,
  `error_code` plus three indexes. **No name or path column.**
* Three selectors, three rules, all still present: producer `upload_dir / f"{log.id}{file_ext}"`;
  `find_task_file` globs `f"{task_id}.csv*"` and raises on 0 or >1 matches; `cleanup_task_files` globs
  `f"*{task_id}*.csv*"`.
* Reachability unchanged and asymmetric: `find_task_file` has one caller (`data_service.py::trigger_processing`);
  `trigger_processing` has **no route caller**; `cleanup_task_files` has **zero callers in `src/`**.
* `cleanup_stale_temp_files` still runs only from `db/starter.py::DatabaseStarter.startup` — and is **not**
  lease-guarded, unlike `mark_orphaned_uploaded_logs_failed` beside it.
* `ProcessingStatusResponse.filename` is still filled from `log.message` (two sites in `data_service.py`).
* **New:** the identity convention now crosses a **container boundary** — the producer names the artefact in
  the API process, the remover is the `rq-worker` process reading the same volume.

### ART-003 — in-flight area bounded by age only, shares its volume with the app log (MEDIUM)

**Substantiated; one premise now conditional on the tier.**

* Bounds unchanged: `upload.py` declared-`Content-Length` check, cumulative streamed-byte check, rate limiter
  `max_attempts=100, ttl=3600` keyed `upload:{current_user.id}`; `stale_file_threshold_hours=24`. **No count
  and no byte bound on the area**, and the periodic task sweeps `processing_logs` only.
* `app` is `read_only: true` with no tmpfs; `app_data:/app/data` carries `tmp_uploads` **and** `logs/app.log`
  (`LOGGING__LOG_FILE`), 10 MB × 5 rotating handler.
* **New: `LOGGING__LOG_FILE` and `app_data` are now also on `rq-worker`**, which mounts the same volume and can
  unlink artefacts inside it. "One container writes both" became "two containers".
* **Changed premise:** the area is `/app/data/tmp_uploads` **only because compose sets `UPLOAD__TEMP_DIR`**.
  `eeb9a5e` deleted `upload.temp_dir` from `app.yaml`, so a host-run process resolves `UploadSettings.__init__`'s
  absolute `platformdirs` default — verified: `C:\Users\Om\AppData\Local\ZOO\mkobi\tmp_uploads`. A byte ceiling
  must be expressed against the *resolved* dir, not a literal.
* `docker/Dockerfile` still creates `/app/data/uploads` in three stages (now `:95`, `:117`, `:147`); no code writes it.

### ART-004 — artefact destroyed on every terminal path, before the derived work commits (HIGH → re-graded CRITICAL by VAL-06-001)

**Substantiated, fully. This is the phase's highest-band confirmed defect and VAL-06-001's re-grade is correct.**

* Success path: `_run_with_transaction` calls `_store_aggregates`, then `if file_path.exists(): await asyncio.to_thread(file_path.unlink)`,
  then `_update_processing_log_status(COMPLETED)` — all three inside the `async with session.begin():` opened by
  `_process_csv_file_async`'s production branch. `Transaction.__aexit__` is what commits, so the unlink is
  ordered **before** the commit of the aggregates derived from it.
* Failure path: `except Exception as e:` outside the session block unlinks again, then reports `FAILED` on a
  fresh session, then `raise`s. The rollback edge destroys the source.
* Both `except Exception` handlers are unreachable for `asyncio.CancelledError` and for `PanicException`
  (verified: MRO is `PanicException -> BaseException -> object`).
* No detector: `ProcessingLog` cannot name the file; `find_task_file` is unreachable. No reversal:
  `trigger_processing` depends on the artefact surviving a terminal state, which the unlinks forbid.
* **Drift:** the anchors moved (unlinks at `data_worker.py:546-548`, `:576-578`, `:611-613`; `session.begin()`
  at `:603`), and `0717b65` rewrote the production failure handler to report `FAILED` on its own session — an
  improvement the report predates that does **not** touch the unlink ordering.

### ART-005 — a failed removal is a log line and nothing else (MEDIUM)

**Substantiated; the evidence sentence is still wrong by the report's own standard.**

* All four failure handlers terminate in a log call: `file_cleanup.py::cleanup_task_files` and
  `::cleanup_stale_temp_files` (`except Exception` → `logger.error`), plus the worker's two error-path unlinks
  (`logger.warning(..., exc_info=True)`). No column, counter or metric exists in `src/`.
* The reclaimer still runs exactly once per process start, from `DatabaseStarter.startup`, and is **not**
  lease-guarded. A failed removal is not retried.
* **Removal-site enumeration (VAL-06-007 confirmed by re-grep): nine sites** — `data_worker.py:547, 578, 613`;
  `file_cleanup.py:40, 93`; `file_processing.py:266`; `upload.py:183, 231`; `shutil.rmtree` at
  `utils/file_utils.py:42`. The report's "there is no other `unlink`/`rmtree` in `src/`" is false, and its own
  Appendix E already excludes the ninth.
* **New:** `tests/conftest.py` is a second caller of `cleanup_stale_temp_files(max_age_hours=0)`, which the
  report does not have. Named blocker still present: `tests/test_upload_api.py::test_cleanup_task_files_called_during_processing`
  drives `process_csv_background` and asserts on the directory; the function it names has no production caller.

### ART-006 — approval reports a retrievable one-time password regardless (MEDIUM)

**Both halves drifted; the residue is confirmed; the report's remedy for the creation half is refuted.**

* **Creation half — re-derived differently and the recommended ordering is now the opposite.** `admin.py`'s
  approve handler no longer stores anything: it delegates to `AuthService.approve_registration_request`.
  That method creates the user, sets `force_password_change`, marks the request `APPROVED`, **`await db.commit()`**,
  and *only then* calls `temp_password_store.store(retrieval_token, temp_password)`. The docstring states the
  rationale and even names the residue: *"The store fails open by design, so a non-raising call is not proof
  that the credential is retrievable."* ART-006's recommendation — "reordering the `store` call **before** the
  status update and committing only after it succeeds" — is the ordering `2de4156` deliberately replaced.
* The same after-commit pattern now exists on the reset path (`auth_service.py`), so there are **two** `store`
  call sites, not one route site plus one service site.
* `TempPasswordStore.store` is still fail-open (`temp_password_store.py`: `except Exception: logger.error`, no raise).
* **Retrieval half — unchanged.** `retrieve_temp_password_admin_endpoint` calls `retrieve` and maps every
  `None` to `ErrorCode.NOT_FOUND` / "Temporary password not found or already retrieved". `retrieve` still
  returns `None` for absent, already-deleted **and** any Redis error (`except Exception: … return None`).
* **Residue confirmed and now larger:** a repository grep for `temp_pwd` returns exactly one hit — the key
  prefix definition. There is no delete, revoke or invalidate anywhere in `src/`, so the TTL
  (`TEMP_PASSWORD_TTL_SECONDS=86400`, verified) is the sole expiry. `deps.py::get_temp_password_store` is the
  only construction path.
* **VAL-06-002's merge ruling against phase 04 is now stale** for the creation half: AUTH-002's anchors
  (`admin.py:321` store, `:330` commit) no longer resolve to those statements.

### ART-007 — the bundle's presence changes the route table; health calls an unservable bundle "available" (MEDIUM)

**Substantiated, anchors drifted, behaviour identical.**

* `_setup_static_files` still resolves `Path("frontend/dist")` **relative to the process CWD** and registers the
  catch-all mount at `/` only when `static_dir.exists() and index_path.exists()`; otherwise one warning, no mount.
* `/health/detailed` still reports `static_files` from `os.path.isdir("frontend/dist")` **alone** — it never
  checks `index.html`, the condition the mount requires. `/health` (what `HEALTHCHECK` and nginx gate on) never
  mentions the bundle.
* `SPAStaticFiles.get_response` still falls back to `FileResponse(index_path)` for non-`api/` 404s and raises a
  bare 404 for `api/`; it remains the only `FileResponse` in `src/`.
* `frontend/dist` still reaches two consumers by two routes — the image-baked copy for `app`, and a host bind
  `../frontend/dist:/usr/share/nginx/html:ro` on the production-profile `nginx` service. Two copies, one health
  surface. Dockerfile anchors moved (`HEALTHCHECK` at `:180`; `libmagic1` at `:46` and `:80`, confirming
  VAL-06-007's correction that the report's `:81` was one line past).

### ART-008 — concurrent reclaimers log the loser's collision as ERROR (LOW)

**Drifted: the mechanism survives, the process set is wrong, and the shape is now worse.**

* `cleanup_stale_temp_files` still lists `upload_dir.glob("*.csv*")`, `stat()`s and `unlink()`s each file in a
  `try` whose `except Exception` logs at ERROR; `FileNotFoundError` is indistinguishable from a genuine
  `EACCES`. `deleted_count` still counts only the files that process won.
* **Premise changed.** The multiplicity is no longer only `--workers 4` lifespans in one container: it is now
  those four *and* the `rq-worker` container, which mounts the same volume and unlinks the same artefacts while
  holding a job. rq forks a work horse per job, so remover and sweeper can genuinely run in different processes
  at once. The report's own Recommendation anticipated this ("make the sweep tolerant before wiring RQ rather
  than after") and RQ is now wired.
* **What improved:** `mark_orphaned_uploaded_logs_failed` and the periodic reconciler are lease-guarded
  (`ReconcilerLease`); `cleanup_stale_temp_files` is **not** — the two sweeps are guarded differently in the same
  function, a new inconsistency. The report's count (5 spurious ERROR lines) was an interleaving artefact; the
  validator's re-runs (7, 7, 8) are consistent with that.

### ART-009 — declared allowed-MIME set is not the one enforced (LOW)

**Central claim refuted (VAL-06-005 confirmed by execution today); both surviving halves substantiated.**

* **Refuted:** `get_config().allowed_mime_types` is byte-identical to `MimeTypeEnum.allowed_values()` — three
  members. The shipped `settings/app.yaml` `upload.allowed_mime_types` supplies all three. The declared and
  enforced sets do **not** differ as shipped. `docs/06-backend/configuration.md` is a table row with no values
  enumerated, so the documentation consequence is unsupported.
* **Survives:** `Settings.allowed_mime_types` (a property) is read by nothing — `validate_mime_type` reads
  `MimeTypeEnum.allowed_values()` directly. `UPLOAD__ALLOWED_MIME_TYPES` therefore has no effect.
  `config.py::UploadSettings.allowed_mime_types` is a *class default* of two members that the shipped YAML
  overrides with three; the property is doubly dead.
* **Survives:** the `try: import magic / except ImportError` module-scope branch pair. The two branches return
  different verdicts for the same bytes — the fallback's `b"\n" in buffer and (b"," in … or b";" in …)` heuristic
  accepts a semicolon file `text/csv`, a libmagic build returns `text/plain`. Both `docker/Dockerfile` stages
  install `libmagic1`, so the deployed container and a host run disagree.

### VAL-06-001 — re-grade ART-004 to CRITICAL

**Correct and actionable.** The three elements the rubric's CRITICAL clause names are all present in the code
today: the unlink precedes the commit on the success edge; the failure edge unlinks then rolls back; nothing
detects the loss and nothing reverses it. The re-grade changes no code, only triage order. **Caveat the Planner
must carry:** the finding's *severity* is confirmed while its *Consequence* sentence ("the operator's only
recourse is to ask the uploader for the file again") is now slightly stronger than before, because the
after-commit store reordering in `auth_service.py` has not changed the artefact side.

### VAL-06-002 — split ART-006; the two named-but-unlisted test blockers

**Test blockers confirmed present.** `tests/core/test_temp_password_store.py::test_store_fail_open_on_error`
and `::test_retrieve_fail_graceful_on_error` both exist; `tests/api/test_temp_password_retrieval.py` has five
tests including `test_retrieve_temp_password_single_use`. **The ownership ruling is now stale**: the creation
half's code moved out of `admin.py` into `auth_service.py::approve_registration_request`, so phase 04's
AUTH-002 anchors no longer describe it. The residue (no revocation path) is phase 06's and is confirmed.

### VAL-06-003 — the Summary overstates runtime reach

**Prose-only, still valid, and now more misleading.** The report's Summary claims all eight blocks were
reached at runtime; blocks 2, 5 and 8 were discharged by reading and grep. This matters more now, because the
three blocks that were *not* executed are exactly where the drift is densest: block 2 (area/bounds) is where
`rq-worker` joined the volume, and block 5 (one-time secret) is where the store call moved after the commit.

### VAL-06-004 — the `:211-215` citation does not select gzip; the trigger is bounded

**Confirmed and independently reproduced today** (see §1 item 2). `_read_csv_lazy` logs and then hands the
path to `pl.scan_csv`; a 15.26 MB mislabelled artefact loads, a 6.10 MB one panics. The finding stands at
HIGH; only its *exposure shape* narrows to files at or below `lazy_threshold_mb` (10.0 MB, verified).

### VAL-06-005 — ART-009's central claim refuted

**Confirmed by execution** (identical three-member sets). The re-typed finding is the dead property plus the
platform-dependent detector, exactly as the validation says.

### VAL-06-006 — the analysis says ART-002 is separable; the roadmap gates on ART-004

**Still an internal contradiction, and the stakes rose.** The dependency is now also *physical*: phase 03's
B3 restructures the same `session.begin()` block that ART-004's unlink sits inside, and phase 03's B2 adds an
advisory lock inside the same transaction. ART-002's shape (column vs scratch space) is downstream of both.

### VAL-06-007 — the removal enumeration is incomplete; two off-by-one citations

**Re-verified by grep: nine removal sites, not eight-plus-nothing.** The `Dockerfile:81` and `main.py:10-25`
corrections both check out (`libmagic1` at `:80`; `check_dependencies` distinct from `REQUIRED_MODULES`).

### VAL-06-008 — five recommendations offer a choice where one is required

**Still open, and one branch has since been closed by someone else.** ART-002 and ART-004 remain mutually
exclusive; ART-001's `app.py BaseException` guard now has **no target** (the loop is gone), so one of its two
halves is moot; ART-003, ART-007 and ART-009 remain bundles.

### VAL-06-009 — the `baseline:` field names a tree the anchors were not read from

**Now a three-commit problem.** Anchors resolve against `c3c0a61`'s parent differently from `c3c0a61`, from the
dirty tree, from `5a2cfb6`, and from today's `2174895` — where `data_worker.py`, `app.py`, `config.py`,
`admin.py`, `auth_service.py`, `task_queue.py`, `docker/Dockerfile` and both compose files all have moved
substantially, and two of the report's named symbols no longer exist.

### VAL-06-010 — the `VAL-001` namespace collision

**Unchanged, out of scope for this phase, prose only.**

## 3. Cross-cutting architecture and constraints

**The artifact subsystem as it exists now.**

| concern | owner today | anchor |
|---|---|---|
| path resolution | `Settings.upload_temp_dir` → `UploadSettings.temp_dir`; `__init__` substitutes an absolute `platformdirs` path when unset; `Settings._ensure_upload_dir` creates it at settings construction | `config.py::UploadSettings`, `::Settings.upload_temp_dir`, `::_ensure_upload_dir` |
| in-flight area | `upload_{uuid4}_{basename}` streamed in chunks into `upload_temp_dir`, `finally` unlink guarded by `exists()` | `api/routes/upload.py::upload_file_endpoint` |
| accepted artefact | `{ProcessingLog.id}.csv` or `.csv.gz` on the shared `app_data` volume | `file_processing.py::process_upload_with_session` |
| broker | RQ `DEFAULT_QUEUE_NAME`; the sole record of accepted work | `core/task_queue.py::get_rq_queue` / `::enqueue_job` |
| consumer | separate container, forked work horse per job | `rq_worker_wrapper` → `data_worker.py::process_csv_background_sync` |
| removal | nine sites — success + two failure unlinks in the worker, the enqueue-failure compensation, the route's `finally`, two sweeps, one dead `platformdirs` tree | see ART-005 |
| retention | age only (`stale_file_threshold_hours`), startup only, **not** lease-guarded | `file_cleanup.py::cleanup_stale_temp_files` ← `db/starter.py::DatabaseStarter.startup` |
| record identity | none — no name/path column | `db/models/processing_logs.py::ProcessingLog` |
| DB columns holding paths | **zero** — no table stores a path or a retrieval token | verified by reading the models |
| traversal defences | none needed, none present: the only user-supplied component reaching the filesystem is `Path(filename).name`, and every selector is a glob on a caller-typed UUID | `upload.py`; `file_processing.py::find_task_file`; `file_cleanup.py::cleanup_task_files` |
| filesystem permission/ownership | `app` runs `read_only: true` with no tmpfs; `app_data` is the only writable space; no `user:` directive, so the container runs as image root and files are root-owned | compose (`read_only: true`, `app_data:/app/data`) |

**Volume topology (changed since the report).** `app_data:/app/data` is mounted on **two** services:
`app` and `rq-worker`. Both set `UPLOAD__TEMP_DIR=/app/data/tmp_uploads` and
`LOGGING__LOG_FILE=/app/data/logs/app.log`; `migrate` sets the former. The artefact area and the rotating log
therefore have **two writers and two removers**, and the report's single-container reasoning understates both.

**Shared seams and their owners** (owner = the phase that must change it).

| seam | owner | why |
|---|---|---|
| `data_worker.py::_run_with_transaction` transaction scope; the unlink's position inside it | **03** (B3) then **06** (ART-004) | B3 restructures the same `session.begin()`; the two cannot land independently |
| advisory lock as first statement of the worker transaction | **03** (B2) | same transaction |
| enqueue/commit/rename ordering in `file_processing.py` | **05** (DP-001) | adjacent to ART-004; different file, different process |
| `ProcessingLog` schema change (an artefact-name column, a `cleanup_error` column) | **14** (DDL) with 06 owning the requirement | any ART-002 / ART-005 column route needs a migration |
| upload temp dir as a shared volume across two containers; byte ceiling on the area; log volume separation | **06** (defect) / **10** (volume layout, backup, disk budget) | compose ownership and operational alerting |
| loader memory ceiling, `.csv.gz` expansion ratio, worker replica count | **11** | ART-001's exposure bound and the volume's capacity |
| MIME admission / libmagic as a hard dependency; `force_password_change` consumer | **15** (security baseline) / **04** | ART-009's detector half; ART-006's residue |
| temp-password revocation path and the retrieval token's home | **04** (AUTH-002/AUTH-006) / **06** (residue) | contested today, split by VAL-06-002 |
| `get_user_temp_dir` / `platformdirs` documentation surface | **02** (CFG) / **08** (docs) | the report's Appendix E exclusion is still correct |

## 4. In-flight and already-landed work

**Nothing is in flight.** Every file the briefing named as dirty is committed in `2174895`; no
artifact-subsystem file is modified. The work that already landed *into* this phase's territory:

| commit | symbol touched | bearing |
|---|---|---|
| `3848e7a` | `core/task_queue.py` (rewritten as an RQ seam), `file_processing.py::enqueue_processing_job`, `data_worker.py::process_csv_background_sync`, `rq_worker_wrapper.py`, `docker/docker-compose*.yml` (worker gains `UPLOAD__TEMP_DIR`, `LOGGING__LOG_FILE`, `app_data`) | **refutes ART-001's consequence**; creates the two-container two-remover topology reshaping ART-003 and ART-008; makes ART-001's `app.py` guard targetless |
| `2de4156` | `admin.py::approve_registration_request_admin_endpoint`, `auth_service.py::approve_registration_request` and the admin password-reset path | **inverts the ordering ART-006's remedy demands**; adds an in-code acknowledgement of the fail-open residue; moves AUTH-002's anchors |
| `eeb9a5e`, `14be95c`, `ce537d7` | `config.py` (unread fields removed), `settings/app.yaml` (`upload.temp_dir` deleted; `logging.log_file` nulled), `.env.example` | changes where `upload_temp_dir` resolves outside a container (ART-003); leaves ART-009's divergence claim refuted |
| `0717b65` | `data_worker.py` production failure path — `FAILED` reported on its own session after rollback | improves TOPO-001; **does not touch the unlink ordering** ART-004 targets |
| `4a5db54`, `a92b546`, `3856f27`, `9a77625`, `b646ef1` | `app.py::lifespan`, `data_worker.py::start_stale_processing_cleanup_task`, `core/reconciler_lease.py` | lease-guards the orphan repair and the periodic reconciler; **leaves `cleanup_stale_temp_files` unguarded** — the gap ART-005 and ART-008 need |
| `eeb9a5e` | `utils/file_utils.py` untouched | `get_user_temp_dir` / `cleanup_temp_dir` remain dead code, still re-exported from `mkobi.utils` |

## 5. Discrepancies and risks

**Symbols the reports name that do not exist today.**

| named | reality |
|---|---|
| `app.py::queue_worker`, `asyncio.create_task(queue_worker())`, shutdown reap | **gone** with the in-process queue |
| `TaskQueue`, `process_next`, `default_queue`, `get_task_queue` | **gone**; `tests/test_task_queue.py` asserts their absence |
| `admin.py:321` store / `:330` commit | the approve handler no longer stores |
| `config.py:174`-era anchors, `docker/Dockerfile:179`, `compose.yml:113-247` | all moved; `config.py` now exceeds `:1000` |
| `app.py:328` (the `FileResponse` site) | moved into the nested `SPAStaticFiles` class |

**Findings whose recommended fix is refuted or overtaken**

1. **ART-001** — the `app.py` `BaseException` guard has no target; rq already reaps `BaseException`. The
   content-based extension derivation and the total reader boundary remain valid.
2. **ART-006 creation half** — "store before commit" is the ordering the code deliberately replaced.
3. **VAL-06-002** — the merge into AUTH-002 names anchors that no longer resolve; the coordination target is
   `auth_service.py`, where both `store` call sites live.
4. **ART-003** — "/app/data/tmp_uploads" is a compose-tier fact, not a property of the code.
5. **ART-008** — "four sweepers in one container" is no longer the process set.

**Contested ownership after the drift**

| seam | claimants | status |
|---|---|---|
| the worker transaction containing ART-004's unlink | 03 (B3/B2) vs 06 (ART-004) | overlapping and inseparable in ordering; phase 03's plan is the one already written, so 06 must sequence after it |
| `ProcessingLog` new columns | 06 (ART-002/ART-005 requirement) vs 14 (DDL) | requirement vs migration, uncontested if stated |
| temp-password fail-open | 04 (AUTH-002) vs 06 (residue) | the merge ruling's anchors are stale; the residue is uncontested |
| the artefact volume's layout and budget | 06 (ART-003) vs 10 (production ops/backup) | the byte ceiling needs 10's disk budget; splitting `app_data` is 10's compose edit |
| the shared log+artefact volume | 06 (defect) vs 10 vs 11 (capacity) | three-way; nobody has filed the backup implication |

**Tests that will break, and tests that will not**

| test | why |
|---|---|
| `tests/test_upload_api.py::test_cleanup_task_files_called_during_processing` | names a function with no production caller; ART-005 and ART-002 both touch it |
| `tests/test_data_service.py::test_validate_file_spoofed_gzip_rejected` (+ siblings at `:618`, `:643`) | encodes the intent ART-001 changes; passes only because its sample body detects as `text/plain` |
| `tests/core/test_temp_password_store.py::test_store_fail_open_on_error`, `::test_retrieve_fail_graceful_on_error` | both break under ART-006's remedy; neither is named in the report |
| `tests/api/test_temp_password_retrieval.py::test_retrieve_temp_password_single_use` | breaks if a Redis error stops mapping to `NOT_FOUND` |
| `tests/test_mime_validation.py` (three classes) | ART-009's detector change alters its verdicts on libmagic-bearing hosts |
| `tests/test_file_cleanup.py` (four classes, incl. `TestProcessingFailureReportedOnOwnSession`) | follows whichever way `cleanup_task_files` and the sweep move |
| `tests/test_task_queue.py` | asserts the retired queue surface stays gone — a guard against reintroducing the mechanism ART-001's remedy might invite |
| `tests/test_rq_worker.py::TestRegisteredJobCallable` | asserts the **source text** of `enqueue_processing_job`; a signature change breaks it silently |
| `tests/test_data_worker.py` | 3 × `commit.assert_not_called()`; any move of the unlink across the commit boundary crosses it |
| `tests/conftest.py` session cleanup | a second caller of `cleanup_stale_temp_files`; a new byte budget would be inherited by this fixture |

**Data-loss and security regression risk**

| risk | where |
|---|---|
| **Retaining the artefact on the failure path (ART-004's remedy) grows the area unboundedly** — the only bound is 24h age, and the ceiling that would bound it (ART-003) is unbuilt | `data_worker.py`, `file_cleanup.py` |
| **Moving the unlink after the commit leaks the file when the commit fails** unless the failure path still unlinks; the halves must move together | same |
| **A byte ceiling interacts with the shared log volume**: rejecting an upload because the *log* filled the volume is a new failure mode nobody has filed | `upload.py`, `logging_config.py` |
| **A new `ProcessingLog` column changes the status payload's shape** (`ProcessingStatusResponse` is a shared Pydantic model the frontend consumes) | `models/`, `frontend/src/shared/types` |
| **The RQ queue is now the only record of accepted work** — losing the Redis volume loses queued jobs whose artefacts the 24h sweep then reclaims, leaving `uploaded` rows with no file | `core/task_queue.py`, compose volumes; acknowledged in `3848e7a` as an OPS edge |
| **`rq-worker` gaining write access to the artefact area is a new privilege** in a container that previously only ran the `rqworker` CLI | `docker/docker-compose.yml` |

## 6. Decision points for the Planner (must be left open)

| # | question | alternatives | who chooses |
|---|---|---|---|
| **D-06-A** | Is an accepted artefact re-runnable after a terminal state? (closes ART-002, ART-004, VAL-06-006, VAL-06-008 for both) | (a) retain past terminal state + explicit retention + user-initiated removal; (b) delete on every terminal path, remove `trigger_processing` / `find_task_file` | Tech Lead; **precondition for phase 03 B3 sequencing** |
| **D-06-B** | Given rq reaps `BaseException`, what is ART-001's remaining remedy? | (a) content-derived extension + total reader boundary; (b) also widen the worker's handlers to `BaseException`; (c) both | owner; the report's `app.py` guard is dead |
| **D-06-C** | ART-005's "move the sweep onto the periodic task" — which task, and does it inherit the lease? | (a) inside the lease-guarded `start_stale_processing_cleanup_task`; (b) a separate periodic task; (c) make the boot-only sweep lease-guarded like the orphan repair | owner; it is the only unguarded sweep of the three |
| **D-06-D** | Where does a removal-failure record live? | (a) nullable `cleanup_error` on `ProcessingLog` (migration + status-payload change); (b) metric/log-only; (c) retry-only, no record | owner; phase 14 owns the DDL |
| **D-06-E** | The area's byte ceiling: what bounds, and what happens to the log sharing the volume? | (a) per-directory size check before accept, reject `FILE_TOO_LARGE`; (b) dedicated log volume (phase 10); (c) stdout-only logging; (d) all three | owner + phase 10; needs a real disk budget |
| **D-06-F** | `cleanup_task_files` and `utils/file_utils.py::get_user_temp_dir` / `cleanup_temp_dir` | (a) wire the first into the consumer; (b) delete both and correct the tests; (c) leave and document | owner; **dead-code policy — investigate purpose first** |
| **D-06-G** | ART-006's residue: build a revocation path, or accept the TTL? | (a) persist `retrieval_token` on the registration request + add revoke; (b) shorten the TTL; (c) accept the TTL and document the window | owner; phase 04 owns the two merged halves |
| **D-06-H** | ART-006's creation half: the report's "store before commit" is refuted — is the shipped after-commit order accepted, or is the report wrong? | (a) keep it, change nothing (the residue is the only live defect); (b) make `store` raise and re-order back; (c) make `store` return a bool checked after commit | owner; the docstring already argues for (a) |
| **D-06-I** | ART-007: is the bundle's location configurable, or is the CWD contract accepted? | (a) new `FRONTEND__DIST_DIR` with an absolute default; (b) keep CWD-relative, fix the health check only; (c) refuse to start when the bundle is absent in a production tier | owner; a stricter `HEALTHCHECK` can turn a passing container unhealthy |
| **D-06-J** | ART-009's detector: libmagic required, or the heuristic kept? | (a) make libmagic a hard startup dependency, delete the fallback; (b) keep the fallback, test both branches; (c) invert the validator to read `config.allowed_mime_types` so the dead key becomes live | owner; (a)/(b) change the semicolon-CSV verdict on libmagic hosts |
| **D-06-K** | Does `rq-worker` keep a read-write mount of the artefact area, given it is the component that unlinks? | (a) keep `app_data` read-write; (b) split the artefact area onto its own volume shared only by `app` and `rq-worker`; (c) move the removal into the API process | coordinator; interacts with D-06-E and phase 10 |
| **D-06-L** | Sequencing against phase 03 (B2/B3) and phase 14 (migrations) | 06 after 03 B3 with migrations via 14; or interleave | coordinator |
| **D-06-M** | The `VAL-001` namespace collision and the report-prose corrections (VAL-06-003/006/007/008/009) | fix in place; or a consolidation pass over `99-validation/` | coordinator; no code impact |

## 7. Coverage ledger

| id | verdict | evidence anchors |
|---|---|---|
| ART-001 | substantiated (core) / **refuted (consequence)** | `file_processing.py::validate_mime_type`, `::process_upload_with_session` `file_ext`; `loader.py::_read_csv_lazy` (no gzip), `::_read_csv` (`gzip.open`), `::load_csv` `except Exception`; rq 2.9.1 `worker/base.py::perform_job` bare `except:`; `Dockerfile` `CMD --workers 4` |
| ART-002 | substantiated | `ProcessingLog` (7 columns, no path); `file_processing.py::find_task_file`; `file_cleanup.py::cleanup_task_files`; `data_service.py::trigger_processing` (no route); `db/starter.py::DatabaseStarter.startup` |
| ART-003 | substantiated (tier-conditional) | `upload.py` size checks + rate limiter; `config.py::stale_file_threshold_hours`; compose `app_data`, `read_only: true`, `LOGGING__LOG_FILE` (app **and** rq-worker); `config.py::UploadSettings.__init__` |
| ART-004 | **substantiated (highest band)** | `data_worker.py::_run_with_transaction` unlink → `COMPLETED` inside `session.begin()`; both `except Exception` unlink paths; `find_task_file` unreachable; `ProcessingLog` has no name column |
| ART-005 | substantiated (evidence sentence false) | `file_cleanup.py::cleanup_task_files` / `::cleanup_stale_temp_files`; worker's two error unlinks; nine removal sites incl. `utils/file_utils.py::cleanup_temp_dir`; `tests/conftest.py` second caller; `test_cleanup_task_files_called_during_processing` |
| ART-006 | **drifted (both halves)**; residue confirmed | `auth_service.py::approve_registration_request` (store **after** commit) + reset path; `temp_password_store.py::store` (fail open) / `::retrieve` (catch-all `None`); `admin.py::retrieve_temp_password_admin_endpoint`; `temp_pwd:` sole occurrence |
| ART-007 | substantiated (anchors drifted) | `app.py::_setup_static_files` (CWD-relative, two-part condition) + `SPAStaticFiles.get_response`; `/health/detailed` `os.path.isdir` alone; `Dockerfile` `HEALTHCHECK`; compose nginx bind |
| ART-008 | **drifted** (mechanism holds, process set wrong) | `file_cleanup.py::cleanup_stale_temp_files` `except Exception`; `db/starter.py` unguarded sweep vs lease-guarded orphan repair; `app.py::lifespan`; rq-worker mounts `app_data` and unlinks |
| ART-009 | **refuted centrally**; two halves substantiated | runtime `allowed_mime_types == MimeTypeEnum.allowed_values()`; `app.yaml` three entries; `config.py::Settings.allowed_mime_types` unread; `file_processing.py` `try: import magic`; `Dockerfile` `libmagic1` ×2 |
| VAL-06-001 | confirmed; actionable | ART-004 anchors above |
| VAL-06-002 | test blockers confirmed; **ownership ruling stale** | `tests/core/test_temp_password_store.py` (`test_store_fail_open_on_error`, `test_retrieve_fail_graceful_on_error`); `tests/api/test_temp_password_retrieval.py::test_retrieve_temp_password_single_use`; `auth_service.py` store sites |
| VAL-06-003 | still valid; more material now | report Summary vs its own Evidence; blocks 2 and 5 are where the drift is densest |
| VAL-06-004 | **confirmed by execution today** | 15.26 MB mislabelled `.csv.gz` → `LOADED`; 6.10 MB → `PanicException`, `isinstance(e, Exception) == False` |
| VAL-06-005 | **confirmed by execution today** | identical three-member sets; `app.yaml` three entries; `configuration.md` row enumerates no values |
| VAL-06-006 | still contradictory; stakes rose | report analysis vs Roadmap steps 2–5; phase 03 B3 targets the same `session.begin()` |
| VAL-06-007 | **re-verified by grep** | nine removal sites; `Dockerfile` `libmagic1` at `:80`; `main.py::check_dependencies` ≠ `REQUIRED_MODULES` |
| VAL-06-008 | still open; one branch closed by others | ART-001's `app.py` guard targetless; ART-006's ordering inverted; ART-002/003/004/007/009 unresolved |
| VAL-06-009 | now a three-commit problem | `c3c0a61` vs dirty tree vs `5a2cfb6` vs `2174895` for `config.py`, `data_worker.py`, `app.py`, `task_queue.py`, `Dockerfile`, compose |
| VAL-06-010 | unchanged, out of scope | `VAL-001` in two files under `99-validation/` |

**Tally:** substantiated 5 (ART-002, ART-003, ART-004, ART-005, ART-007) · substantiated-core-with-refuted-consequence 1 (ART-001) · drifted 2 (ART-006, ART-008) · refuted-as-central-claim 1 (ART-009) · already-fixed 0 · stale 0.
**VAL-06 defects that change a target: 3** (VAL-06-002's ownership ruling is stale because the store call moved; VAL-06-008's ART-001 branch is moot because the loop is gone; VAL-06-009's baseline is now four trees deep).
VAL-06-001, 004, 005, 006, 007, 010 are confirmed and actionable as written.
