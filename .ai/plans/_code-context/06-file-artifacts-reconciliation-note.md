---
phase: 06-file-artifacts
kind: reconciliation-note
block: FAB-0
role: reconciliation and baseline capture — no remediation design, no production-code change
head_at_capture: 85912d6e25a0f5aa8cd75db4373f130a4371fd47
plan: .ai/plans/06-file-artifacts-remediation-execution.md
code_context: .ai/plans/_code-context/06-file-artifacts-code-context.md
report: .ai/audit/99-validation/06-file-artifacts-validated-findings.md
upstream_findings: .ai/audit/06-file-artifacts/findings.md
authority: >-
  This note is authoritative for how every later FAB-* block reads the upstream report and the
  plan. It records the re-grade, the five evidence defects, the internal contradiction, the
  disposition of VAL-06-008 and the anchor table, so no Implementor sizes a job from the report's
  prose. No file under .ai/audit/ is edited anywhere in this phase (R-06-1).
---

# 06-file-artifacts — Reconciliation Note (FAB-0)

## Purpose

The validated report of phase 06 is an **input, never an implementation target**. Its prose
overstates runtime reach, contains five evidence defects, contradicts itself on one dependency, and
names a `baseline:` tree its anchors were not read from. This note records those corrections once, so
that every succeeding block works against the plan and the code context rather than against a report
whose line numbers drift across four commits.

It is written at `HEAD` `85912d6e25a0f5aa8cd75db4373f130a4371fd47`. Three documents are compared here:
the report, the code context (`.ai/plans/_code-context/06-file-artifacts-code-context.md`) and the
execution plan (`.ai/plans/06-file-artifacts-remediation-execution.md`), against the working tree.

**Precedence, restated.** Where the report and the code context disagree on **where** something is or
**what the code does**, the code context wins. Where they disagree on **identity** — which findings
exist and what they are called — the report's identifier set wins. No `ART-*` or `VAL-06-*`
identifier is renumbered, reused or re-typed by this phase.

---

## 1. The re-grade — `VAL-06-001`

**ART-004 is re-graded to CRITICAL.** This is recorded as a re-grade, not applied silently to the
report.

The report's Summary states the CRITICAL band is empty because *"nothing here … destroys content that
a durable record names."* That sentence is **contradicted by ART-004's own Consequence**: on the
success path the artefact is unlinked **before** the commit of the aggregates derived from it, and on
the failure path it is unlinked, then the transaction rolls back. The file the operator uploaded is
destroyed on every terminal path, and no durable record names it — which is precisely why the loss is
undetectable, not why it is absent.

**Ordering consequence.** ART-004's block (**FAB-2**) is this phase's **first code block**; ART-001
(**FAB-1**) is second. The plan's execution order is
`FAB-0 → FAB-8 → FAB-7 → FAB-4 → FAB-2 → FAB-3 → FAB-1 → FAB-6 → FAB-9`, and ART-004 is the only
block whose subject is *destroying the only copy of ingested input data with no detector and no
reversal*.

---

## 2. The five evidence defects

### `VAL-06-003` — the Summary overstates runtime reach

The report's Summary claims all **eight** report blocks were reached at runtime. In fact **blocks 2,
5 and 8 were discharged by reading and grep only** — no container was started, no database or Redis
key was written. Those are exactly the three blocks where drift is densest: block 2 is where the
`rq-worker` joined the volume, and block 5 is where the one-time-credential store call moved after
the commit. Every prose conclusion in those three blocks must be re-checked against the tree, never
assumed.

### `VAL-06-004` — the gzip branch, re-verified by execution

`CSVLoader._read_csv_lazy` **did not select gzip**. It logged the `.gz` name and handed the *path* to
`pl.scan_csv`, which resolves compression from the bytes. Re-verified by execution at
`2174895` (code-context §1 item 2):

- a **15.26 MB** mislabelled file (plain CSV named `*.csv.gz`) → `LOADED (4000000, 1)`;
- a **6.10 MB** mislabelled file → `pyo3_runtime.PanicException`, with
  `mro=['PanicException','BaseException','object']` and `isinstance(e, Exception) == False`.

The exposure bound is `lazy_threshold_mb` = **10.0 MB**, read from configuration
(`config.py` line 533 default `10.0`; the shipped `src/mkobi/settings/app.yaml` also supplies
`10.0`, line ~49), not hard-coded in any reasoning.

**Renaming note.** That method was renamed `_read_csv_lazy` → **`_read_csv_via_scan`** by commit
`916a021` (`fix(loader): bound the decompressed stream and take the byte ceiling from
configuration`). Both names must be recorded: the report and the code context speak of
`_read_csv_lazy`; the tree carries `_read_csv_via_scan` (`src/mkobi/data/loaders/loader.py` line 199,
called at line 152). The sibling eager branch is `_read_csv` (line 400), the one site that genuinely
opens `gzip.open`.

### `VAL-06-005` — the "declared set differs" claim is dropped

`get_config().allowed_mime_types` is **byte-identical** to `MimeTypeEnum.allowed_values()` — **three**
members (`text/csv`, `application/gzip`, `application/x-gzip`) — and the shipped
`src/mkobi/settings/app.yaml` supplies all three. The report's "declared set differs from the enforced
set" claim, and its documentation consequence, are **dropped**.

`src/mkobi/settings/app.yaml` is the **third declaration site** the report never mentions. The three
sites are: `config.py::UploadSettings.allowed_mime_types` (a **class default of two** members,
`TEXT_CSV` and `APPLICATION_GZIP` only), `config.py::Settings.allowed_mime_types` (an unread
**property**), and `settings/app.yaml` at `upload.allowed_mime_types` (the site that actually decides
the value, three members). The property is doubly dead: `services.file_processing.validate_mime_type`
reads `MimeTypeEnum.allowed_values()` directly, so `UPLOAD__ALLOWED_MIME_TYPES` has no effect.

What survives the re-type (ART-009 becomes a LOW finding): the dead key, and the
`try: import magic / except ImportError` detector whose verdict is platform-dependent.

### `VAL-06-007` — the removal census, two off-by-one citations, and a superseded count

- The report's "there is no other `unlink`/`rmtree` in `src/`" is **false**. At the report's tree the
  census was **nine** removal sites, and the ninth is `utils/file_utils.py::cleanup_temp_dir`, which
  the report's own Appendix E excludes.
- The report's `docker/Dockerfile:81` is **`:80`** (verified: `libmagic1` is at line 80).
- The report's `main.py:10-25` should be **`main.py::check_dependencies`** (a named symbol, distinct
  from the `REQUIRED_MODULES` list at line 10).
- **Now superseded.** Commit `6a2c04a` (`refactor(cleanup): remove the two uncalled file and log
  reclamation helpers`) deleted `cleanup_task_files` and `cleanup_old_processing_logs`. Re-grepping
  at `85912d6`, the **current** census in `src/` is still **nine** sites, but the distribution moved:

  | # | site | note |
  | - | ---- | ---- |
  | 1 | `workers/data_worker.py` success-path unlink | `asyncio.to_thread(file_path.unlink)`, after commit |
  | 2 | `workers/data_worker.py` error-path unlink | retained so a commit failure cannot leak |
  | 3 | `workers/data_worker.py` cancellation/worker-horse unlink | |
  | 4 | `workers/data_worker.py` commit-failure unlink | |
  | 5 | `services/file_processing.py` enqueue-failure compensation | |
  | 6 | `services/file_cleanup.py::cleanup_stale_temp_files` | the sweep's `unlink()` |
  | 7 | `api/routes/upload.py` in-flight `finally` unlink #1 | |
  | 8 | `api/routes/upload.py` in-flight `finally` unlink #2 | |
  | 9 | `utils/file_utils.py::cleanup_temp_dir` | `shutil.rmtree`; the report's Appendix E excludes it |

  The old `file_cleanup.py::cleanup_task_files` site (`file_cleanup.py:40` in the report's
  enumeration) is **gone**; the worker now carries **four** unlinks where the report named three.

  A **tenth caller** the report does not have is `tests/conftest.py` (line 105:
  `cleanup_stale_temp_files(max_age_hours=0)`). Per R-06-9 the count is a **floor, not a ceiling**:
  FAB-4's Auditor re-greps at block start, and a tenth `src/` site is a finding to report.

### `VAL-06-009` — the `baseline:` field names a tree the anchors were not read from

The plan's front-matter `baseline_read: 21748957c7e9a20d6ebd442bb81c74251c490f58` names a tree the
report's anchors were **not** read from. Four trees were in play when this note was written:

| tree | who read it |
| ---- | ----------- |
| `c3c0a61` (+ dirty tree) | the **audit** ran here |
| `c3c0a61` and `5a2cfb6` | the **validation** read here |
| `2174895` | the **code context** (Phase-1 auditor) read here |
| `85912d6` | the **plan** and this note are written here (current `HEAD`) |

So anchors resolve against four commits, not one. The plan's own anchor authority rule follows: where
the report and the code context disagree on **where** something is, the code context wins; line
numbers are drift evidence only, never binding.

---

## 3. The internal contradiction — `VAL-06-006`

The report's Cross-Finding Analysis calls ART-002's remediation **"separable"**, while four of its own
roadmap steps **gate on ART-004**. Both statements cannot hold.

**Correct statement: ART-002 is contingent on ART-004's retention decision.** ART-002's shape — a
name/path column versus scratch space — is downstream of whether an accepted artefact survives a
terminal state. That is why the plan gates FAB-3 on **D-06-A** and **FAB-2** (`blocked_by`), and why
`VAL-06-001`'s clause names the detector and the reversal as FAB-3's, not FAB-2's.

The stakes are higher than the report knew: phase-03 `B3` restructures the same `session.begin()`
block ART-004's unlink sits inside, and phase-03 `B2` adds an advisory lock inside the same
transaction. ART-002's shape is downstream of all of that.

---

## 4. `VAL-06-008`'s disposition

Five recommendations offered a **choice where one was required** (ART-002/ART-004, ART-001's
`app.py` guard, ART-003, ART-007, ART-009). Every such fork is now a **numbered decision record** with
a chooser and a blocked block. All sixteen decisions (`D-06-A` … `D-06-P`) are **ruled** in the plan's
"Coordinator rulings of 2026-10-03" section. **No block starts without its ruling.** The rulings are
reproduced in §7 below so this note is self-contained.

One of the five forks was closed by others before this phase began: ART-001's `app.py` `BaseException`
guard has **no target** — the in-process consumer loop it wrapped was removed by `3848e7a`, and
`tests/test_task_queue.py::TestRetiredSymbolsRemoved` asserts the retired surface stays gone.

---

## 5. `VAL-06-010` — the `VAL-001` collision, out of scope

`VAL-001` appears in two files under `.ai/audit/99-validation/` (a namespace collision). This is a
property of **the directory**, not a system defect, and it is **out of scope for remediation**. It is
handed to whoever consolidates `.ai/audit/99-validation/` — decision **D-06-M**. No file under
`.ai/audit/` is edited by any block in this phase.

---

## 6. Anchor table — resolved against the current `HEAD`

The plan's nine-row semantic anchor table, re-resolved at `85912d6`. Legend: **resolves** = the symbol
exists and is the named thing; **moved** = the symbol exists but not where a report line number says;
**absent** = the symbol does not exist today and no block may target it.

| Finding | Anchor | State at `85912d6` |
| ------- | ------ | ------------------ |
| **ART-001** | `services/file_processing.py::detect_mime_type_from_content` (two module-scope defs under `try: import magic` / `except ImportError`) | **resolves** (lines 30, 46) |
| | `::validate_mime_type` (reads `MimeTypeEnum.allowed_values()`) | **resolves** (line 73) — see ambiguity note below |
| | `::validate_file` | **resolves** (line 97) |
| | `::process_upload_with_session` (`file_ext` from `detect_file_type(filename)`) | **resolves** (line 166) |
| | `data/loaders/loader.py::detect_file_type` | **resolves** |
| | `::CSVLoader.load_csv` (`except Exception` → `ValueError`) | **resolves** (line ~177) |
| | `::CSVLoader._read_csv` (the genuine `gzip.open` branch) | **resolves** (line 400) |
| | `::CSVLoader._read_csv_lazy` (a debug log, then `pl.scan_csv(...).collect()`) | **moved → renamed** to `::CSVLoader._read_csv_via_scan` (line 199; `916a021`) |
| | `::CSVLoader.__init__` / `LoaderConfig` | **resolves** |
| | `models/enums.py::FileExtensionEnum` / `::MimeTypeEnum` | **resolves** |
| | `workers/data_worker.py::_process_csv_file_async` (its `except Exception` chain) | **resolves** |
| | vendored `rq/worker/base.py::perform_job` | **resolves** |
| **ART-002** | `db/models/processing_logs.py::ProcessingLog` (seven columns; no name or path column) | **resolves** |
| | `services/file_processing.py::process_upload_with_session` | **resolves** |
| | `::find_task_file` (`f"{task_id}.csv*"` glob) | **resolves** (line 293) |
| | `services/file_cleanup.py::cleanup_task_files` (`f"*{task_id}*.csv*"` glob) | **absent** — deleted by `6a2c04a` |
| | `services/data_service.py::trigger_processing` (no route caller) | **resolves** |
| | `::get_processing_status` / `::get_processing_result` | **resolves** |
| | `ProcessingStatusResponse` | **resolves** |
| | `db/starter.py::DatabaseStarter.startup` (the production sweep call) | **moved** — the sweep now runs from the periodic lease-guarded task (`ee0f0f5`); `startup` no longer owns it |
| **ART-003** | `api/routes/upload.py::upload_file_endpoint` | **resolves** |
| | `config.py::UploadSettings.temp_dir` / `::Settings.upload_temp_dir` / `::_ensure_upload_dir` / `::UploadSettings.__init__` | **resolves** |
| | `::stale_file_threshold_hours` | **resolves** |
| | `core/logging_config.py`'s `RotatingFileHandler` (10 MB × 5) | **resolves** |
| | `docker/docker-compose.yml` (`app_data:/app/data` on `app` **and** `rq-worker`; `read_only: true`; the two env vars) | **resolves** |
| | `docker/Dockerfile`'s three `mkdir -p … /app/data/uploads` stages | **moved** (line numbers drift; three stages remain) |
| **ART-004** | `workers/data_worker.py::_process_csv_file_async` (`_run_with_transaction`: success unlink now **after** the `session.begin()` block) | **resolves — shape changed** by `5e73e37`: the success unlink moved after the commit and the handler widened to `except BaseException` |
| | both `except Exception` handlers and their unlinks | **resolves** — the failure-path unlink is retained |
| | the own-session `FAILED` compensation (`0717b65`) | **resolves** |
| | `services/file_processing.py::find_task_file` (the unreachable reversal) | **resolves** (unreachable) |
| | `db/models/processing_logs.py::ProcessingLog` | **resolves** |
| **ART-005** | `services/file_cleanup.py::cleanup_task_files` | **absent** — deleted by `6a2c04a` |
| | `::cleanup_stale_temp_files` (glob `*.csv*`, `stat()`, `unlink()`, `except Exception` → `logger.error`) | **resolves** (line 15; `unlink` at line 62) |
| | `::cleanup_old_processing_logs` (zero production callers) | **absent** — deleted by `6a2c04a` |
| | `workers/data_worker.py`'s two error-path unlinks | **resolves** — now **four** unlinks in the worker |
| | `db/starter.py::DatabaseStarter.startup` | **moved** (see ART-002) |
| | `tests/conftest.py` (the second sweep caller) | **resolves** (line 105) |
| **ART-006** | `services/auth_service.py::approve_registration_request` (commit **then** `store`) | **resolves** |
| | `::reset_password_admin` (the second `store` site) | **resolves** |
| | `core/temp_password_store.py::TempPasswordStore.store` (fail-open) / `::retrieve` | **resolves** — `store` now returns `bool` (`7cf0623`); `retrieve` now raises `TempPasswordStoreUnavailableError` (`478015b`) |
| | `_KEY_PREFIX` (the only `temp_pwd` occurrence in `src/`) | **resolves** (line 10) |
| | `api/routes/admin.py::approve_registration_request_admin_endpoint` (delegates) | **resolves** |
| | `::retrieve_temp_password_admin_endpoint` | **resolves** |
| | `api/deps.py::get_temp_password_store` | **resolves** |
| | `config.py`'s `temp_password_ttl_seconds` (86400) | **resolves** |
| | the registration-request model | **resolves** |
| **ART-007** | `app.py::_setup_static_files` (CWD-relative `frontend/dist`; two-part condition; catch-all mount) | **resolves** |
| | `app.py::SPAStaticFiles.get_response` | **resolves** |
| | `app.py`'s `/health/detailed` `static_files` component | **resolves** |
| | `docker/Dockerfile`'s `HEALTHCHECK` | **moved** (line number drifts) |
| | `docker/docker-compose.yml`'s nginx bind | **resolves** |
| **ART-008** | `services/file_cleanup.py::cleanup_stale_temp_files` (`except Exception` at `stat`/`unlink`) | **resolves** |
| | `db/starter.py::DatabaseStarter.startup` (the unguarded call beside two lease-guarded ones) | **moved** — `cleanup_stale_temp_files` is still **not** lease-guarded, but the periodic task that now calls it (`ee0f0f5`) **is** |
| | `app.py::lifespan` | **resolves** |
| | `core/reconciler_lease.py::ReconcilerLease` | **resolves** |
| | `docker/docker-compose.yml`'s `rq-worker` (`app_data` read-write) | **resolves** |
| **ART-009** | `config.py::UploadSettings.allowed_mime_types` (a class default of **two** members) | **resolves** (line 529) |
| | `::Settings.allowed_mime_types` (an unread property) | **resolves** (line 1052); read by nothing |
| | `settings/app.yaml`'s `upload.allowed_mime_types` (the site that decides the value) | **resolves** (`src/mkobi/settings/app.yaml`, line 44; three members) |
| | `services/file_processing.py::detect_mime_type_from_content` (both branches) | **resolves** |
| | `models/enums.py::MimeTypeEnum` | **resolves** |
| | `utils/file_utils.py::validate_mime_type` (a third, unrelated symbol) | **resolves** (line 69) |
| | `docker/Dockerfile`'s two `libmagic1` installs | **resolves** (one at line 80, per `VAL-06-007`) |
| | `main.py::check_dependencies` (the hard-dependency precedent) | **resolves** (line 28) |
| | `docs/06-backend/configuration.md`'s `allowed_mime_types` table row | **resolves**; enumerates no values |

**The ambiguous anchor.** `validate_mime_type` resolves to **three** distinct symbols:

| symbol | signature | role |
| ------ | --------- | ---- |
| `services/file_processing.validate_mime_type` | `(file_path: Path) -> None` | **the phase-06 target** (the admission site) |
| `utils/file_utils.validate_mime_type` | `(mime_type: str) -> bool` | not a phase-06 target; separate owner |
| `data/loaders/validator.validate_mime_type` | `(mime_type: str) -> bool` | not a phase-06 target; separate owner |

Every block that names this anchor must write `services.file_processing.validate_mime_type` in every
commit body, issue and test name. `detect_file_type` is unambiguous by contrast: it exists once, in
`data/loaders/loader.py`, with exactly one production caller
(`services/file_processing.py::process_upload_with_session`).

---

## 7. The rulings that apply to this phase — self-contained

Every decision is **ruled**. Nine were pre-empted or made moot by commits that landed after the plan
was written at `2174895`. Rulings were made against `HEAD` `85912d6`.

| # | Ruling | Basis — what actually landed |
| - | ------ | ---------------------------- |
| **D-06-A** | **(b)** — the artefact is **scratch space, deleted on every terminal state**, a *designed* property that must be written down. The unreachable `find_task_file` / `trigger_processing` pair is removed as the false claim it is. | `5e73e37` made all three deletion paths unconditional (success-after-commit, failure, enqueue-failure). Option (a) would need an unbounded area **and** a re-run path with no owner and no authorization decision; `trigger_processing` still has **no route caller**. |
| **D-06-B** | **(b) PRE-EMPTED.** Remaining scope is the **naming rule** and the **reader boundary** only. | `5e73e37` widened the worker's handler to `except BaseException`. |
| **D-06-C** | **(a)** — move `cleanup_stale_temp_files` into the **existing** lease-guarded `start_stale_processing_cleanup_task`. **One** loop, not two. | D-05-I already chose the lease-guarded periodic loop in `ee0f0f5`, and moved the orphan sweep into it. Option (b) would create the second lease loop C06-1 warns about. |
| **D-06-D** | **(c)** — retry-only, no record. `cleanup_stale_temp_files` returns `deleted` / `failed` / `already_gone` so the count is a contract the periodic task's status consumes. **ART-005's recording half is NOT closed.** | Phase 14 owns all DDL (C06-3) and the frontend consumes `ProcessingStatusResponse`; a column cannot ship in this phase. |
| **D-06-E** | **Open — carried by FAB-5.** The area's byte ceiling and the log-sharing-the-volume question. FAB-5 is **DEFERRED to phase 10** (C06-04, the disk budget). | A ceiling without a number is a guess. |
| **D-06-F** | **PRE-EMPTED — no phase-06 block.** `util/file_utils.py`'s `platformdirs` pair stays with phase 02/08 (C06-12). | `6a2c04a` deleted `cleanup_task_files` and `cleanup_old_processing_logs`. |
| **D-06-G** | **(c)** — accept the TTL and document the window as a **written risk acceptance**. | The token is minted (`uuid4`) **after** the commit and `RegistrationRequest` persists **no** token, so option (a) needs a second transaction or a pre-commit mint — the "strictly worse state" FAB-6's own risk table names. |
| **D-06-H** | **PRE-EMPTED — (c).** `store` returns `bool`, commit-then-store. | `2de4156` + `7cf0623` + `478015b`. |
| **D-06-I** | **(a)** — one configured, **resolved** bundle path consumed by both the mount and the health component, through **one shared predicate**. **`HEALTHCHECK` is NOT touched.** | Two disagreeing predicates exist today: health uses `os.path.isdir`, the mount uses `exists() and index.exists()`. Leaving `HEALTHCHECK` alone removes the "passing container turns unhealthy" rollout hazard. |
| **D-06-J** | **(a)** — libmagic is a hard startup dependency; the `except ImportError` fallback is deleted. | Every shipped image already carries `libmagic1`, and the test image inherits it (`FROM base AS test`). `main.py::check_dependencies` is the project's own precedent. |
| **D-06-K** | **(a)** — `app_data` stays read-write on `app` and `rq-worker`. | Smallest; no deploy-time named-volume migration and no rollback story to invent. D-06-E's log half stays open under C06-04. |
| **D-06-L** | **MOOT — resolved by fact.** Option (b)'s shape is the only one available; there is no concurrent editor left. | `907e052` (B3), `5e73e37` (PB-14), `916a021` (PB-12) all landed. |
| **D-06-M** | **Routing only** — the `VAL-001` collision in `.ai/audit/99-validation/` and the report-prose corrections (VAL-06-003/006/007/008/009) go to whoever consolidates `99-validation/`. No code impact; no `.ai/audit/` file is edited by this phase. | Directory property, not a system defect. |
| **D-06-N** | **MOOT.** No `artifact_filename` column exists under D-06-A(b), so there is no divergence check to place; option (b) already collapsed into (a) when `ee0f0f5` moved the orphan sweep into the periodic task. | |
| **D-06-O** | **(c) refuted; (b) deferred with FAB-5.** No `ErrorCode` member covers storage, disk or quota — `models/enums.py` has 30 members and zero matches. The cheapest honest code if FAB-5 ever lands is `SERVICE_UNAVAILABLE`; a new member is authorised only by an explicit ruling, which this phase does not make. | |
| **D-06-P** | **(a)** — the stored extension is derived from the **detector's verdict at admission**. `services.file_processing.validate_mime_type` returns the detected type and raises `AppException(ErrorCode.INVALID_FILE_TYPE)` instead of a bare `ValueError`. | One rule; the stored name can never disagree with the bytes. The `ValueError` is also a live deviation from AGENTS.md's error layer. |

**FAB-5 is DEFERRED to phase 10, not dropped.** Its code half is a ceiling whose number is phase 10's
disk budget (C06-04); the compose half is D-06-K(a) — no change; the error contract is D-06-O,
unresolved. Shipping a bound with a guessed number is worse than shipping none.

---

## 8. Baseline captured at FAB-0 (rule: **do not regress**, not *make it green*)

Captured at `HEAD` `85912d6e25a0f5aa8cd75db4373f130a4371fd47`. The test services were already up
(`docker compose -p mkobi-test -f docker/docker-compose.test.yml ps`: `test-db` healthy on `:5434`,
`test-redis` healthy on `:6381`), so `.\Makefile.ps1 test-up` was a no-op.

### 8.1 Full suite — `.\Makefile.ps1 test`

```text
============================= test session starts ==============================
platform linux -- Python 3.12.15, pytest-9.1.0, pluggy-1.6.0 -- /app/.venv/bin/python
configfile: pyproject.toml
testpaths: tests
collected 1297 items

=========== 9 failed, 1288 passed, 33 warnings in 308.42s (0:05:08) ============
```

**Exact counts: 9 failed, 1288 passed, 0 skipped, 0 errors, 0 xfailed/xpassed, 33 warnings.**
The suite is **already red** at this baseline; the rule is **do not regress**, not *make it green*.

The nine pre-existing failures, all outside the artefact subsystem and none touched by this phase:

| # | test |
| - | ---- |
| 1 | `tests/test_auth.py::TestRateLimiting::test_rate_limiter_allows_under_limit` |
| 2 | `tests/test_auth.py::TestRateLimiting::test_rate_limiter_blocks_over_limit` |
| 3 | `tests/test_auth.py::TestRateLimiting::test_rate_limiter_fail_open_on_redis_error` |
| 4 | `tests/test_auth.py::TestRateLimiting::test_rate_limiter_fail_closed_on_redis_error` |
| 5 | `tests/test_auth.py::TestRateLimiting::test_rate_limiter_different_ips_independent` |
| 6 | `tests/test_layouts.py::TestLayoutsAPI::test_create_layout_missing_name_returns_422` |
| 7 | `tests/test_layouts.py::TestLayoutsAPI::test_create_layout_missing_definition_returns_422` |
| 8 | `tests/test_layouts.py::TestLayoutsAPI::test_create_layout_duplicate_name_returns_400` |
| 9 | `tests/test_pydantic_models.py::TestUserModels::test_user_db_valid` |

Five are the auth rate-limiter class (Redis-backed), three the layouts-API validation shape, and one a
`UserDB` pydantic-model fixture — all properties that already held before any FAB-* block runs.
**None of the artifact-subsystem test files** named in the plan (`test_data_worker`, `test_file_cleanup`,
`test_upload_api`, `test_data_service`, `test_data_csv_loader`, `test_mime_validation`,
`test_task_queue`, `test_rq_worker`, `test_e2e_upload`) is red at this baseline.

### 8.2 Quality gates — `.\Makefile.ps1 check`

`.Makefile.ps1 check` runs, in order: `ruff check src/ tests/` + the named `alembic/env.py`, `mypy`, then
`fe-lint` (eslint). Result:

| Gate | Result |
| ---- | ------ |
| `ruff check` (Python lint) | **PASS** — `All checks passed!` |
| `mypy` (Python typecheck) | **PASS** — `Success: no issues found in 119 source files` (one note: `pyproject.toml: unused section(s): module = ['tests.*']`) |
| `eslint` (frontend lint) | **FAIL — pre-existing, not phase-06** — 9 errors in `frontend/src/features/dashboards/**` |

**`check` therefore does not pass as a whole**, but the failure is **entirely in front-end files that
this block does not touch and that the phase does not own**. The nine eslint errors:

- `frontend/src/features/dashboards/__tests__/filter-persistence.test.tsx` — 3 errors
  (`no-unsafe-return`, `no-unsafe-assignment`, `require-await`);
- `frontend/src/features/dashboards/ui/DashboardView.tsx` — 3 errors (`no-unsafe-member-access` ×2,
  `react-hooks/set-state-in-effect`);
- `frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx` — 3 errors
  (`no-unnecessary-type-assertion` ×3).

For every later phase-06 block the relevant rule is the same as the test rule: **do not regress the
Python gates** (both were green here) and **do not touch the frontend** (no block in this phase edits
`frontend/`, per R-06-7).

### 8.3 Artefact-subsystem dirty check

`git status --porcelain -- src/ tests/ docker/ docs/ alembic/`:

```text
(empty — no output)
```

**Confirmed: no artefact-subsystem file is dirty.** The tree at this baseline carries only other
agents' deletions under `.ai/` and `frontend/coverage/`, and untracked `.ai/plans/*` /
`.ai/tasks/*.yaml`. Those are **not staged, restored, deleted or cleaned** by this block.

**Rule for every later block: do not regress.** The phase-01 programme left the suite red at its own
baseline; this phase inherits that tree. A block that changes only files the baseline did not measure
will report a misleading delta, which is why the baseline records the **full** suite counts, not a
sample.
