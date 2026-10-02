# Reconciliation note — phase 05 data pipeline

Plan phase: **`05-data-pipeline`** / data pipeline remediation.
Programme plan: `.ai/plans/18-data-pipeline-implementation-execution.md`.
Audit plan discharged: `.ai/plans/05-data-pipeline-remediation-execution.md`.
Audit inputs: `.ai/audit/05-data-pipeline/findings.md` (`DP-001` … `DP-019`) and
`.ai/audit/99-validation/05-data-pipeline-validated-findings.md` (`VAL-05-001` … `VAL-05-005`).

This note is written so that a later reader or Implementor can work from it **without** reading the
upstream plan and **without** trusting its line numbers. It records the anchor authority, the
severity re-grades, the two audit miscounts, two evidence re-types, the Coordinator's decision
rulings, the test baseline, the verification entry points, and the gates that cannot be used as
evidence in this phase.

---

## A. Anchor authority

This phase is anchored to **symbols, not coordinates**. Any coordinate in the upstream plan
`.ai/plans/05-data-pipeline-remediation-execution.md` is a **research pointer only** and must be
re-derived by symbol before an edit. The current-state fact report
`.ai/plans/_code-context/05-data-pipeline-current-state.md` is **authoritative on every factual
question about what the code does** — it overrides the upstream plan on all such questions. The
upstream plan remains authoritative **only** for the defect analysis and its option sets.

---

## B. Severity re-grades applied

The following re-grades are **applied** by this programme. They are recorded here as re-grades; the
audit corpus under `.ai/audit/**` is **not edited** by any block.

| Finding | Band as ruled | Reason (one line) |
| ------- | ------------- | ----------------- |
| `DP-002` | **MEDIUM** (re-graded; `VAL-05-001`) | The stored metric is self-describing — a dashboard configured for `mean` stores a sum under `revenue_mean` — so the value is re-derivable from the dashboard's own configuration. |
| `DP-018` | **LOW**, raised from the report (new finding; `VAL-05-001`) | Unrecognised `metric_agg` is stored under its own name holding a sum. |
| `DP-005` | **MEDIUM** (re-graded; `VAL-05-002`) | Already fixed by commit `8953bf7`, which landed the `str_values` coercion at both `save_filter_values` call sites as a mypy repair, **after** the validation baseline. |

`DP-002` and `DP-018` ship as one commit (they are one finding's two halves). `DP-005`'s production
fix is already landed; the remaining phase-05 work is verification-only (the dtype-matrix test and a
record of the residual gap).

---

## C. `VAL-05-003` — two miscounts in the audit report, recorded here

The report's Cross-Finding Analysis claims **"four causes account for fifteen of the nineteen
findings"** and closes with **"the remaining four are independent"**, then enumerates six. The four
causes name **ten** findings; the closing list covers **sixteen**. **`DP-009`, `DP-011` and `DP-012`
are named in no cause at all.**

The audit corpus is **not edited by this programme** — `.ai/audit/**` is an input, never a target.
The substantive consequence is carried by the **block structure**: `PB-10` (`DP-009`), `PB-12`
(`DP-011`, `DP-012`) and `PB-8` each group findings that **share no cause with anything else**. A
reader must not conclude that the admission-surface defects (`DP-011`, `DP-012`) or the
configuration-reach defect (`DP-009`) were folded into one of the four named causes; they were left
causally unassigned, and this programme schedules them as the independent items they are.

---

## D. `VAL-05-004` and `VAL-05-005` — two evidence re-types

### `VAL-05-004` — `DP-016`'s second half is a unit-of-atomicity defect

`DP-016`'s second half is re-typed from "a leaked file" to a **unit-of-atomicity** defect: a process
killed between the file unlink and the transaction commit leaves the row stranded at `processing`
naming a file that no longer exists. It stays **in** scope for `PB-14`, and it is cross-referenced to
`PB-1` as the same defect class on the same table (the consumer's status row and the file it names do
not share a fate). **No finding is dropped** — only the type of evidence changes.

### `VAL-05-005` — `DP-007`'s transcript is unusable

`DP-007`'s evidence in the report shows **two different datasets** presented as one dataset in two
orders. The finding survives; the transcript does not.

**The test for `DP-007` must use identical four rows — `{N: 1, N: 7, S: 2, S: 9}` — in forward and
reversed input order**, asserting *different* stored metrics. A test copied from the report's
transcript would pass against the unfixed code and would prove nothing.

---

## E. Coordinator rulings

These rulings are **decisions already taken**. They are recorded faithfully and are not re-opened
here. Each entry gives the record ID, its subject, the **RULING** (option letter plus one-line
shape), who resolved it, and a one-line rationale.

| ID | Subject | RULING | Resolved by | Rationale (condensed) |
| -- | ------- | ------ | ----------- | --------------------- |
| `D-05-A` | Order of commit / move / enqueue | **(a)** order = `commit` → `file move` → `enqueue` | Coordinator | Matches the design `docs/00-overview/data-flow.md` already promises; keeps `test_upload_api.py::test_upload_submits_job_with_correlated_task_id` green unmodified. Option (b) was re-costed: enqueue-before-move lets a consumer pick the job up before the move completes, which is a **race**, not a deterministic failure. Residual failure of (a): a failure between the commit and the move leaves a committed `uploaded` row with no file and no job, reclaimed by the orphan sweep — which `PB-13` makes periodic. That residual must be stated in `PB-1`'s commit body. |
| `D-05-A.2` | What a zero-row status `UPDATE` means | **Raise.** A zero-row status `UPDATE` is a loud failure, not a warning. | Coordinator | "Warn and continue" lets the aggregate replace unattributably — the defect survives. Raise using an **existing, already-mapped `ErrorCode`**; this phase adds no `ErrorCode` member. The existing own-session `FAILED` compensation (commit `0717b65`) is what reports it. |
| `D-05-B` | Where the file unlink goes | **(c)** both halves in one change: unlink **after** the commit, catching `BaseException` **for cleanup only** and re-raising, with the **existing failure-path unlink retained**. | Coordinator | One unlink, one place, one rule, and it closes the re-typed process-kill residue at the same time. Retaining the failure-path unlink is mandatory: moving the unlink after a commit that can fail otherwise **leaks a file on every commit failure**. |
| `D-05-C` | What `groupby` without `aggregations` means | **(a)** deterministic de-duplication with an explicitly named rule. | Domain owner | Previously-succeeding runs keep succeeding and become reproducible. Rejection (b) turns a run that stored a number into a visible failure, and depends on `PB-11` for the error to be reported as what it is. The rule must be stated precisely enough that a later reader can distinguish deliberate de-duplication from a new arbitrary pick. |
| `D-05-D` | `limit` without a fully-determining `sort_by` | **(a)** move the limit to **after** aggregation. | Domain owner | It makes `limit` mean what every reader already takes it to mean — top N by this metric. Rejection (b) and "require `sort_by`" (c) each create a **new failure class** for configurations that work today. Under (a) the change alters stored **values**, not just row counts. |
| `D-05-E` | The `dims` identity canonicalisation rule | **(a)** `str()` every scalar dimension value, as the single canonicalisation point. | Domain owner + phase 14 for the index implication | It makes write and read agree by construction: the read path already compares `dims[key].astext == str(value)`. `None` → `""` is unchanged. Python's `str()` keeps `True` → `"True"` distinct from `1` → `"1"`, so a boolean dimension does not collide with a 0/1 dimension. Reverses `_coerce_dim_value`'s deliberate native-type preservation — that cost is accepted and the rule statement is mandatory. Canonicalise at the **write** path only; canonicalising in the reader would hide the symptom and leave every stored row wrong. |
| `D-05-F` | Where validation warnings land | **(b)** summarise warnings into `processing_logs.message` (`String(1000)`) with an explicit cap and truncation rule. | Domain owner | No enum, no migration, no frontend change. Option (a) — a new status value — is **not available**: `processing_logs.processing_status` is a **native PostgreSQL ENUM**, so a new value requires an Alembic migration, which this phase forbids. Record (a) as a **hand-over to phase 14**, not a rejection. Separately, fix the never-true `column_types` check so it can become true. |
| `D-05-G` | Where the settings boundary lives | **OPEN — a prerequisite, not a blocker.** | Coordinator, on the `PB-8` Auditor/Researcher chain | The ruling requires the `PUT /processing-configs/{dashboard_id}` caller and frontend-form census to exist **first**. `PB-8`'s own Auditor/Researcher chain produces it; the Coordinator confirms the ruling from that evidence. Do not guess the option now. |
| `D-05-H` | The `db_session is None` branch in `_store_aggregates` | **(b)** delete the `db_session is None` branch **after proving it has no caller**, and make `db_session` a required parameter. | Domain owner + Coordinator | Upgraded from a dead-code-policy question. That branch opens its **own session**, which **bypasses the phase-03 rebuild advisory lock** (`ab76989`) and **splits the aggregate write from the `COMPLETED` update**. Making the parameter required removes the hazard by construction rather than by convention. The caller proof is `DataService::trigger_processing` having no route caller — prove it, do not assume it. |
| `D-05-I` | Orphan-sweep placement | **(a)** move the sweep **into** the lease-guarded periodic loop. | Domain owner | One loop, one cancellation path, one thing to reason about at shutdown; both sweeps share one horizon and one failure class, and consolidating removes the second place where they can race. The key question is **moot**: `907e052` already wired the configured `stale_processing_timeout_minutes`. **The commit body must state that the fail-open direction changes** — today every replica sweeps when Redis is unreachable; under a lease one does. |
| `D-05-J` | `cleanup_task_files` and `cleanup_old_processing_logs` | **OPEN — investigation first.** | Domain owner, on `PB-14`'s Auditor | The project's dead-code rule is binding: investigate the purpose of `cleanup_task_files` and `cleanup_old_processing_logs` via git history before any removal is proposed. `PB-14`'s Auditor produces that; the Coordinator then rules. Note the open question for the investigator: `tests/test_upload_api.py::test_cleanup_task_files_called_during_processing` asserts the helper **is** called during processing. |
| `D-05-K` | `aggregated_data.ordinal` migration, or an interim ordering | **(b)** interim `ORDER BY id` on the three read methods, with the append-mode limitation **documented**, plus a written hand-over of the `aggregated_data.ordinal` DDL to phase 14. | Domain owner + phase 14 sequencing | This phase authors no migration. `ORDER BY id` is correct for overwrite mode (rows are deleted and re-inserted, so the order regenerates) and **wrong for append mode**, which is exactly the divergence the column exists to solve. The limitation ships with the change; it is not discovered later. |
| `D-05-L` | Who owns the `success` documentation | **(b)** split ownership by file — **confirmed**. | Coordinator | Phase 14 owns `docs/09-database/**` (it owns `4479eb53fd4e`, the migration that removed the retired `success` value). Phase 05 owns the pipeline narrative: `docs/00-overview/`, `docs/03-processing/`, `docs/04-admin/`. |
| `D-05-M` | Sequencing against phase 03 | **(b)** interleave — **confirmed and now moot.** | Coordinator | The unblocked blocks were run first; phase-03 B1, B2, B3 and B10 have all landed, so nothing is gated on them any more. B3's and B2's commits are a **read-first obligation** for `PB-1`, `PB-14` and `PB-5`, not a start gate. |
| `D-05-N` | What an empty selection reports | **(a)** fail the run, naming the graphs that were skipped. | Domain owner + the frontend's `failed` renderer | A silently-successful upload that changed nothing is the defect itself. `FAILED` already exists as a status and already has a renderer, so **no new status and no migration** are needed — unlike option (a) under `D-05-F`. The guard must sit **before both** clears: `StorageManager.save_aggregates`' own `delete_by_dashboard` **and** `_store_aggregates`' `clear_dashboard_values`, because the filter-value list is wiped independently of the aggregate rows. |
| `D-05-O` | Byte-ceiling ownership and the "lazy" branch | **Policy ruling, mechanism to Researcher.** Three parts: (i) one ceiling owner; (ii) ceiling applies to the decompressed `.csv.gz` stream; (iii) keep two `LoaderConfig`s. | Domain owner + phase 11 for the cost side | (i) **One ceiling owner**: reuse `UploadSettings.max_file_size_mb` through the derived `Settings.max_file_size` — no new environment key, no default change, and it avoids serialising an edit against phase 01's environment-variable table. (ii) The ceiling applies to the **decompressed** stream for `.csv.gz`; a small gzip of a large CSV must be rejected. (iii) Keep **two** `LoaderConfig`s as today — unifying them would make the loader's `required_columns` / `column_types` / `strict_schema` checks run **and** double-cast. The Researcher supplies the bounded-mechanism evidence for (ii). The `_read_csv_lazy` branch's name must stop claiming laziness. One owner per ceiling is the report's own Appendix D requirement. (ii) is a correctness fix, not a preference: the current check measures `st_size`, so a 50 KiB gzip of a multi-gigabyte CSV passes. (iii) avoids introducing a double-cast while fixing the ceiling. The memory cost, the expansion ratio and the worker replica count remain **phase 11's**. |
| `D-05-P` | Is the group-less `yoy` case fixed here or filed? | **(a)** fix the group-less `yoy` case inside `PB-10`. | Domain owner | `_calculate_yoy` with no `group_cols` sorts by the year column and applies an **ungrouped** `shift(1)`, so year-over-year is computed against the globally preceding row. Filing it instead would **ship a known order-dependent defect onto a newly-reachable path** — the same defect class `PB-6` and `PB-7` exist to remove, and the same grading error `VAL-05-001` criticises in the report. |
| `D-05-Q` | Where does `PB-0`'s reconciliation note live? | The reconciliation note lives at `.ai/plans/_code-context/05-data-pipeline-reconciliation-note.md`. | Coordinator | `.ai/structure/**` and the older reconciliation set are deleted from the working tree, so the planned note path does not exist. It sits with the phase's code context, is not an audit file, not a plan, and not a task. |
| `D-05-R` | Is the phase's final validation pass a block or a gate? | The final independent validation is the programme's **validation gate**, not an implementation block. | Coordinator | It produces no commit and no coverage-ledger entry; it runs after the documentation block. |

### E.1 Two facts the ruling set depends on

**`processing_status` is a native PostgreSQL ENUM.** `ProcessingStatus` has exactly **five** members —
`STARTED`, `UPLOADED`, `PROCESSING`, `COMPLETED`, `FAILED` — with **no `SUCCESS`**; the DB value was
removed by `4479eb53fd4e`. Therefore **any option whose cost is a migration is a hand-over, not a
phase-05 change** (`D-05-A.2`, `D-05-F`(a) and `D-05-N`(a) all resolve to no new status value for
this reason).

**`tests/test_app_lifespan.py` has five `mark_orphaned_uploaded_logs_failed` patch sites**, not the
six the upstream plan states. `PB-13`'s regression gate is **five before and five after**.

---

## F. Test baseline

Every later block compares against this baseline. The rule is in bold: **do not regress — not "make
it green".** The suite is red at this baseline for reasons that have nothing to do with the data
pipeline.

| Metric | Value |
| ------ | ----- |
| Command | `.\Makefile.ps1 test` |
| Collected | 1192 items |
| Passed | 1183 |
| **Failed** | **9** |
| Warnings | 33 |
| Duration | 429.68s (7m09s), measured at HEAD `297b1c9` |
| Commit | `297b1c9` |

**Reconciliation with the plan's stated counts.** The plan and `PB-0`'s brief state 1189 collected /
1180 passed / 571.82s. That figure is the **pre-`PB-4`** baseline; `PB-4` (`297b1c9`) added 3 tests,
which is the collection delta the plan records (1189 + 3 = 1192). The table above is the baseline
**measured at HEAD `297b1c9`**, after `PB-4` landed, and is the number every later block compares
against. The pass/fail/warning composition is otherwise unchanged.

The nine pre-existing failures, verbatim:

```
FAILED tests/test_auth.py::TestRateLimiting::test_rate_limiter_allows_under_limit
FAILED tests/test_auth.py::TestRateLimiting::test_rate_limiter_blocks_over_limit
FAILED tests/test_auth.py::TestRateLimiting::test_rate_limiter_fail_open_on_redis_error
FAILED tests/test_auth.py::TestRateLimiting::test_rate_limiter_fail_closed_on_redis_error
FAILED tests/test_auth.py::TestRateLimiting::test_rate_limiter_different_ips_independent
FAILED tests/test_layouts.py::TestLayoutsAPI::test_create_layout_missing_name_returns_422
FAILED tests/test_layouts.py::TestLayoutsAPI::test_create_layout_missing_definition_returns_422
FAILED tests/test_layouts.py::TestLayoutsAPI::test_create_layout_duplicate_name_returns_400
FAILED tests/test_pydantic_models.py::test_user_db_valid
```

These belong to the **authentication** and **layout** work of other phases; **none is a
data-pipeline test**. Note specifically that `tests/test_pydantic_models.py` is red at baseline and
`PB-8` verifies against it — that block must distinguish its own regression from the inherited
failure.

**Collection delta caused by each landed block.** `PB-4` added 3 tests (`297b1c9`), the only
landed phase-05 implementation block at the time of this baseline. Later blocks state their own
delta in their commit bodies.

---

## G. Verification commands

The canonical entry points, copied from `.kilo/rules/commands.md`, so one reader does not need three
files:

| Purpose | Command |
| ------- | ------- |
| Full suite (the baseline and every high-risk gate) | `.\Makefile.ps1 test` |
| Selected tests, forwarded verbatim to pytest | `.\Makefile.ps1 test-select -k <name> -v` |
| Lint | `uv run ruff check <paths>` (auto-fix: `uv run ruff check --fix <paths>`, which also sorts imports / `I001`) |
| Typecheck | `uv run mypy <paths>` |
| Everything | `.\Makefile.ps1 check` |

**Tests run in Docker only.** There is no test database on `localhost`.

**The test image bakes `src/` and `tests/` at build time.** A `test-app` image rebuild is required
for a verification run to see a local edit. This cost one agent real time; every later Implementor
needs it.

---

## H. Gates that cannot be used as evidence in this phase

Two bullets, because blocks will otherwise claim them:

- **`uv run mypy src/mkobi/workers/data_worker.py` is clean today and stays clean through `DP-009`.**
  The `asyncio.to_thread` boundary erases the argument types. **A green `mypy` is not a verification
  statement** for `PB-2`, `PB-6`, `PB-7`, `PB-9`, `PB-10` or `PB-14`.
- **`ruff` sees none of this phase's defects** — they are type, ordering and data-contract defects.
  Its only role here is import ordering and syntax.

**A regression test that passes against the unfixed code is worse than no test.** Where a block
writes a test for a currently-broken behaviour, it must **prove** the test fails before the fix,
temporarily and locally, and record the evidence in its commit body.
