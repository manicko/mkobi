---
phase: 06-file-artifacts
executed: 2026-09-30
executor: validator
problems-only: true
findings: 10
by-severity:
  CRITICAL: 0
  HIGH: 1
  MEDIUM: 1
  LOW: 8
baseline: c3c0a61bf41cad68bf3a3ac105de91ea63c82268
baseline-dirty: >-
  true for source at the start of this validation, false for source at the end. Before the first
  file was read: `git rev-parse HEAD` -> c3c0a61bf41cad68bf3a3ac105de91ea63c82268 and
  `git status --porcelain` -> 20 deletions under .ai/ (templates, builders, models, plans,
  structure), 4 modified tracked source/test files (src/mkobi/config.py, src/mkobi/db/starter.py,
  tests/test_config.py, tests/test_starter.py) and 8 untracked paths (.ai/audit/01..07,
  .ai/audit/99-validation, .ai/plans/01-configuration-secrets-remediation-execution.md). The
  concurrent remediation team committed those four files mid-run as 5a2cfb6 ("fix(config): hoist the
  admin credential guard so both call sites share one implementation"), so HEAD at the end of this
  validation is 5a2cfb608ec117e6669c77eac04ae7e43f8e676f and no tracked source or test file is
  modified. The 20 `.ai/` deletions and the untracked audit paths are unchanged from the start.
  `git diff 5a2cfb6 -- src/` is empty, and every config.py and starter.py anchor this report cites
  resolves at the same line number in 5a2cfb6 as in the tree that was audited, so no finding moves
  and none was re-derived. The baseline named above is the commit phase 06 filed its findings
  against, which is the commit its own front matter names; the tree that was actually read is
  c3c0a61 plus that team's uncommitted edit, which is now 5a2cfb6. The briefed untracked
  `_b3_full_out.txt` at the repo root does not exist in this tree. No file, container, stack
  setting, row, Redis key or stack service was created, edited, staged, committed, reverted or
  stashed by this run; the only file written is this report.
namespace-note: >-
  Validation-level findings use the VAL-06- prefix. The flat VAL- prefix is already occupied twice
  over: the phase-01 and phase-02 validation reports each minted VAL-001..VAL-008 and
  VAL-001..VAL-009 respectively, so VAL-001 resolves to two different findings in this directory
  (recorded as VAL-06-010). VAL-03-, VAL-04- and VAL-05- are the compound form the later reports
  established, pairing the template's frontmatter phase value with the validation prefix; VAL-06-
  follows it. No ART- identifier is renumbered. Zero ART- and zero VAL- markers exist in shipped
  source, tests, docs, alembic or the frontend (repository-wide grep), so no in-source provenance
  has to be migrated or retired.
audited-findings: 9
audited-dispositions:
  confirmed: 6
  re-typed: 1
  re-graded: 1
  merged: 1
  not-substantiated: 0
  unsettled: 0
disposition-note: >-
  6 + 1 + 1 + 1 = 9. ART-004 is confirmed with its band corrected upward (VAL-06-001). ART-006 is
  merged into phase 04's AUTH-002 and AUTH-006; the surviving residue — that nothing but collection
  and the TTL ever removes the secret — is the only part of it that is not already filed
  (VAL-06-002). ART-009 is re-typed: the dead-property half survives, the "declared set differs
  from the enforced set" half and its documentation consequence are refuted (VAL-06-005). The six
  confirmations are ART-001, ART-002, ART-003, ART-005, ART-007 and ART-008, each at the band the
  input carried, two of them with a citation narrowed (VAL-06-004, VAL-06-007). Appendix A carries
  the per-finding verdict for all nine; Appendix G repeats the tally against those verdicts.
---

# Phase 06 — Validated Findings

## Summary

Nine findings were re-derived from the executing path at `c3c0a61` and its dirty tree, not from the
input's quoted evidence. Six are confirmed at the band they carry; one (ART-004) is confirmed and
re-graded **up, to CRITICAL**; one (ART-006) merges into two findings phase 04 already filed; one
(ART-009) is re-typed because its central claim is refuted by the shipped `app.yaml`. None is
rejected and none is unsettled. The headline result is the empty CRITICAL band: it is **not empty,
it is unclaimed**. Phase 06's own rubric names "an artefact removed with no detection of the loss
and no path that reverses it" as a CRITICAL, and ART-004's Observation, Consequence and Evidence
each state that condition in the rubric's own terms — the worker unlinks the only copy of the
uploaded data on the success path *inside* the transaction, before the commit that stores what was
derived from it, and again on the failure path before the rollback, while `find_task_file` — the
only code that would reverse it — is unreachable. The Summary's stated reason for the empty band
("nothing here ... destroys content that a durable record names") is contradicted by ART-004's own
Consequence paragraph. The three claims flagged as load-bearing were re-derived independently and
all three hold: `PanicException`'s MRO is `PanicException -> BaseException -> object` and
`isinstance(e, Exception)` is `False`; no `except` handler anywhere in
`loader.py`/`data_worker.py`/`task_queue.py`/`app.py` names a `BaseException` superclass; and the
verbatim `app.py` consumer loop terminates on the first poisoned job with a second job left in the
queue, unprocessed. The concurrent-reclaimer probe is not an artefact — three independent trials
reproduced the same mechanism with a different spurious-error count each time. Ten defects were
found in the input report rather than in the system: one mis-grade, one cross-phase duplication,
one overstated coverage claim, three citation defects (one of which carries two anchors), one
internal contradiction, one unusable recommendation class, one baseline-field ambiguity and one
namespace collision.

## Findings

### VAL-06-001 — The empty CRITICAL band is unclaimed, not empty: ART-004 meets phase 06's own CRITICAL clause verbatim, and the Summary's reason for the emptiness is contradicted by ART-004 itself

**Severity** — HIGH

**Zone** — "3. The Grade against the Audited Phase's Own Rubric"

**Observation** — Phase 06's severity taxonomy is the rubric of record, and its CRITICAL band's
third enumerated mechanism is, in full: *"an artefact removed with no detection of the loss and no
path that reverses it."* ART-004 is filed **HIGH**. Every element of that clause is present in the
finding's own text rather than supplied by this validation. On removal: the worker's success path
unlinks the accepted artefact at `workers/data_worker.py:532-534`, inside the `async with
session.begin()` block opened at `:585`, before the status write at `:537` and before the commit
that happens on block exit; the failure path unlinks it again at `:593-602` and then `raise`s, so
the source is destroyed on the rollback path too. On detection: nothing in `src/` compares the
store against the records in that direction — the only component that would notice a record
naming an absent artefact is `find_task_file` (`services/file_processing.py:284-309`), which the
input's own ART-002 establishes is reachable only from `DataService.trigger_processing`
(`services/data_service.py:279`), and `trigger_processing` has no route caller. On reversal: the
same two unlinks make the artefact's presence impossible for any task that has reached a terminal
state, and the input's Consequence says so in its own words — *"the operator's only recourse is to
ask the uploader for the file again."* The band the rubric implies is CRITICAL; the band carried
is HIGH. The report does not merely omit the band — it argues for the omission. The Summary
states: *"no CRITICAL band is claimed, because nothing here exposes credential material or destroys
content that a durable record names."* The `processing_logs` row is a durable record, it still
names the task, and the uploaded bytes it describes are gone. The report's own ART-004 Evidence
records the observation that closes it: the artefact for task `9f87bd09-…` was gone from
`/app/data/tmp_uploads` after the worker ran.

**Evidence** — Both halves re-derived from the executing path, not from the quoted snippet.
Ordering: `_run_with_transaction` holds the unlink at `data_worker.py:532-534` and the COMPLETED
status update at `:537-543`; its only call site is `data_worker.py:587`, one line inside
`async with session.begin()` at `:585`, and `session.begin()`'s `__aexit__` is what commits. The
failure branch is `except Exception as e:` at `:588` → unlink at `:594-596` → `raise` at `:603`,
so the file is destroyed on the rollback edge as well. Reachability: a repository-wide grep of
`src/` for `trigger_processing` returns three hits — the protocol declaration
(`interfaces/service_interfaces.py:404`), the implementation (`services/data_service.py:255`) and
its internal call to `find_task_file` (`:279`) — and no route. `cleanup_task_files` has zero
callers in `src/`. Record model: `ProcessingLog` declares `id`, `dashboard_id`, `status`,
`message`, `started_at`, `finished_at`, `error_code` (`db/models/processing_logs.py:30-72`) and no
name or path column, so nothing downstream can name the file that is missing.

**Consequence** — The report's front matter is the triage signal a reader acts on before reading
anything else, and it reads `CRITICAL: 0`. Remediation is built on that column: the Roadmap
sequences ART-001 first and ART-004 second, and treats ART-004 as one change set of three rather
than as the report's top item. A reader who trusts the band triages a queue-consumer denial of
service (ART-001, self-announcing to anyone reading the container log, and recoverable by a
restart) above the one finding in the phase that destroys the only copy of ingested data with no
detection and no reversal.

**Recommendation** — Re-grade ART-004 from HIGH to CRITICAL and record it as a re-grade rather
than applying it silently. Rewrite the Summary's reason for the empty band, or delete the reason
once the band is populated. **This is deliberately not promoted to the validation CRITICAL band**,
and the reasoning is recorded so a later run does not re-open it: the validation CRITICAL requires
that "nothing downstream can distinguish it from a correct report", and here ART-004's body, its
Evidence and its Consequence all state the destruction plainly, and its remediation already sits at
Roadmap step 2. The wrong signal is a severity error in a report that is otherwise correct about
the system — the HIGH definition's "a true finding ... graded below what its own rubric implies",
verbatim — not a fabricated confirmation. Phase 06 owns this remediation; nothing is renumbered.

### VAL-06-002 — ART-006 restates as its own claim the two defects phase 04 already filed as AUTH-002 and AUTH-006, cross-references only the first, and names neither test its own recommendation breaks

**Severity** — MEDIUM

**Zone** — "6. Cross-Phase Conflict, Ownership and Merge"

**Observation** — ART-006 carries the zone "5. A one-time secret held outside the database ...", so
it is filed inside phase 06's own declared scope and no seam violation is claimed. But two of its
three claims are already filed by phase 04, on the same code, for the same mechanism, with the
same consequence. The first is AUTH-002 (HIGH), whose Observation reads: *"`TempPasswordStore.store`
is declared fail-open by design ... (`core/temp_password_store.py:47-48`) ... The
registration-approval path has the same shape (`api/routes/admin.py:321` store, `:330` commit,
`:335` returns the handle)"* — which is ART-006's creation half line for line, including the
three anchors ART-006 re-derives in full. The second is AUTH-006 (MEDIUM), whose Observation reads:
*"`TempPasswordStore.retrieve` returns `None` for three distinct states — key absent, key deleted
by a previous `GET+DELETE` ... and any exception from Redis (`:73-75`) ... The route collapses that
into one answer: `ErrorCode.NOT_FOUND` with the detail `"Temporary password not found or already
retrieved"` (`admin.py:418-422`)"* — which is ART-006's retrieval half, including the claim that a
collection that failed on a Redis error reports a spent token while the secret is still present and
still collectable. ART-006's Evidence cross-references only AUTH-002, and does so as *"Phase 04's
finding, cross-referenced here for the residue rather than re-filed"* — a framing the finding's own
body does not honour, because it re-derives the approve endpoint's whole lifecycle
(`api/routes/admin.py:305-336`) and restates the consequence rather than pointing at it. AUTH-006
is not mentioned anywhere in ART-006. What phase 06 owns and phase 04 has not filed is the
residue: nothing removes the secret at any event other than collection — not user deletion, not
request rejection, not a password change — so only the 24-hour TTL ends it. The input's blocker
list is also incomplete against its own recommendation: ART-006 asks for a Redis error during
collection to surface as `SERVICE_UNAVAILABLE` rather than `NOT_FOUND`, which breaks
`tests/core/test_temp_password_store.py:184-190` (`test_retrieve_fail_graceful_on_error`, which
asserts `result is None` on Redis failure) and `tests/api/test_temp_password_retrieval.py:126-130`
(`test_retrieve_temp_password_single_use`). Neither is named; the only blocker ART-006 lists is
`test_store_fail_open_on_error` (`:164-181`), which is AUTH-002's.

**Evidence** — The residue claim re-derived: a repository-wide grep of `src/` for
`temp_password_store` / `TempPasswordStore` returns eleven hits, of which exactly two are calls —
`store` at `services/auth_service.py:583` and at `api/routes/admin.py:321`, and `retrieve` at
`api/routes/admin.py:417`. There is no delete, revoke or invalidate call anywhere in `src/`, so the
TTL (`config.py:464`, default 86400) is the only expiry. The two named-but-unlisted blockers were
read at their lines: `tests/core/test_temp_password_store.py:183-190` constructs a
`FailingRedis` and asserts `result is None`;
`tests/api/test_temp_password_retrieval.py:88-136` drives a single-use claim and asserts
`"not found" in body["detail"].lower()`. Note the CRITICAL clause was tested and is **not** met:
the rubric's "a one-time secret still recoverable from the store that holds it after the window in
which it may be collected" does not apply, because the TTL bounds that window and Redis evicts
inside it. That is why the residue stays MEDIUM, where the rubric's own words —
"a secret the caller is told exists and that no failure path ever reports as absent" — place it.

**Consequence** — Two phases now carry the same remediation against the same two functions, with
different blocker lists and different owners. Phase 04's AUTH-002 recommendation is the executable
one and names both of its tests; phase 06's step 6 would edit `store` and `retrieve` again and
would break a test it never inspected. A reader planning from phase 06 alone will ship a change
that turns `tests/core/test_temp_password_store.py:184-190` red and will not know why.

**Recommendation** — Split ART-006. Merge the creation half into **AUTH-002** and the retrieval
half into **AUTH-006**; both are same-root-cause merges, and **phase 04 owns their remediation**.
Neither AUTH- identifier is renumbered. Reduce ART-006 to the residue phase 06 uniquely owns — no
revocation path other than collection and the TTL — and add the two tests its own recommendation
breaks to whatever remains of the blocker list. **No seam violation is recorded**: block 5 of
phase 06's command file is about the artefact's observable lifecycle, which is exactly where the
residue sits, so the finding is inside its own declared scope even where its content duplicates a
sibling's.

### VAL-06-003 — The Summary claims all eight blocks were reached at runtime; the report's own Evidence fields show two of the eight were never executed

**Severity** — LOW

**Zone** — "2. The Vacuous-Control Angle, and Its Bindings: Does It Exist, What Scope Does It Declare, What Did It Examine"

**Observation** — The Summary opens: *"All eight blocks were reached at runtime against the dev
stack (`.\Makefile.ps1 up`, project `mkobi`): artefacts were uploaded over HTTP ... the loader and
the queue were driven directly, the bundle was exercised in three presence states through the real
ASGI app, and the reclaimer was run four times concurrently over the shared volume."* Three
questions apply to that control: does it exist, what scope does it declare, what did it actually
examine. It exists and it declared the scope of all eight blocks. What it examined is five blocks
and a half. Block 5's Evidence field opens *"The approve handler and the retrieval handler were
read at the lines cited"* — a static read, and the finding it produced, ART-006, rests on no
runtime observation anywhere in the report. Block 8's Evidence is *"Swept `src/` for
`FileResponse`, `StreamingResponse`, `Content-Disposition`, `download` and `export`"* — a
repository grep. Block 2's Evidence is *"Read from the running container: `UPLOAD__TEMP_DIR` ..."*
and the field itself adds *"Admission controls were read, not exercised"*; ART-003 is therefore a
static inventory. Five of the seven reported findings (ART-001, ART-002, ART-004, ART-007, ART-008)
do rest on executed probes, and Appendix B's per-block evidence column is accurate where Appendix B
covers it. The defect is the one sentence in the Summary, and it overstates runtime reach for
blocks 2, 5 and 8.

**Evidence** — Set against the report itself, not against an external standard. The Summary
enumerates four runtime activities — HTTP uploads, direct loader and queue driving, three ASGI
presence states, four concurrent sweeps — and none of them touches block 5 or block 8. Appendix B
row 5 lists its evidence artefact as *"approve handler; store/retrieve implementations; the TTL;
the retrieval handler's single `None` mapping"*, four of which are source reads; row 8 lists
*"sweep for `FileResponse`/`StreamingResponse`/..."*. Block 2's Evidence says in its own words
*"Admission controls were read, not exercised."*

**Consequence** — The coverage record is the artefact a later run uses to decide which blocks need
re-execution, and this report declares all eight discharged. A reader trusting the Summary will not
re-execute block 5 before acting on ART-006, and will assume the one-time secret's failure residue
was observed rather than inferred — which matters precisely because ART-006 turned out to be
two-thirds duplicate and its surviving residue is the part that was never run. No remediation
follows from the defect itself, which is why the band is LOW.

**Recommendation** — Correct the Summary to name the five blocks reached at runtime and to state
that blocks 2, 5 and 8 were discharged by reading and by grep. No finding changes band; ART-003
and ART-006 are both legitimate on static proof, which phase 06's own command file admits as an
evidence class.

### VAL-06-004 — ART-001 cites a second gzip-selecting site that does not select gzip, so the trigger condition is stated more broadly than the code supports

**Severity** — LOW

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — ART-001's Observation states that the stored name chooses the reader "purely from
the stored name (`data/loaders/loader.py:295-302` and `:211-215`)". The second anchor resolves, but
it does not do what the claim says. `_read_csv_lazy` at `loader.py:211-215` tests
`file_path.suffix == ".gz" or file_path.name.endswith(".csv.gz")` only to emit a debug log line; it
then calls `pl.scan_csv(file_path, **read_kwargs).collect()` at `:215`, handing Polars the *path*,
not a `gzip.open` handle. Polars resolves the compression from the bytes, so the lazy branch reads
a mislabelled artefact successfully. The genuine gzip branch is `:295-302` only. The consequence
is a real narrowing of the finding's trigger: `CSVLoader.load_csv` selects the lazy branch when
`file_size_mb > lazy_threshold_mb` (`loader.py:133`), and that threshold is
`UploadSettings.lazy_threshold_mb`, default **10.0 MB** (`config.py:343`, read at runtime as
`get_config().lazy_threshold_mb == 10.0`). A plain CSV above 10 MB renamed `.csv.gz` is stored under
a false gzip claim and read correctly; a plain CSV at or below 10 MB renamed `.csv.gz` is stored
under a false gzip claim and panics. The finding's Consequence — "One upload named `*.csv.gz` whose
body is not gzip disables background processing in the uvicorn process that served it" — is
therefore true of the small-file case and false of the large-file case, and states no bound.

**Evidence** — Executed against the real `CSVLoader` in a throwaway directory. A 12.21 MB file of
plain CSV bytes named `big2.csv.gz` → `LOADED (1600000, 2)`, and `CSVLoader()._read_csv_lazy` on
the same path → `LOADED (1600000, 2)`; no exception of any class. A 5.72 MB file of the same bytes
named `big.csv.gz` → `RAISED pyo3_runtime.PanicException, isException=False`, because 5.72 MB
falls under the 10.0 MB threshold and takes the eager branch. The rest of ART-001's chain
re-derived exactly as filed: `process_upload_with_session` derives the stored extension from the
caller's filename (`services/file_processing.py:208-212`) and writes `{log.id}{file_ext}` (`:235`);
`MimeTypeEnum.allowed_values()` is `['text/csv', 'application/gzip', 'application/x-gzip']`; the
same bytes stored as `.csv` load; real gzip stored as `.csv` also loads, so the reverse mismatch
really is benign.

**Consequence** — The defect, the mechanism, the MRO, the handler chain and the consumer death are
all confirmed; the finding stands at HIGH. What moves is the shape of the exposure. As written the
finding implies every mislabelled upload panics, which is false for the largest such uploads — and
the largest are the ones a 100 MB ceiling exists to admit. A reader who sizes the incident by
"any renamed file" over-reports, and a remediation scoped by "the lazy branch also selects gzip"
would be written against a branch that needs no change.

**Recommendation** — Keep ART-001 at HIGH and amend its Observation to drop the `:211-215`
citation and to state the bound: the failure requires an artefact at or below
`lazy_threshold_mb` (10.0 MB by default), because the lazy branch hands the path to Polars rather
than opening `gzip`. The recommended remedy is unaffected — deriving the stored extension from the
detected content and making the eager reader boundary total both still apply — and the
`app.py` `BaseException` guard is still needed for any other base-class escape from the worker.

### VAL-06-005 — ART-009's central claim is refuted by the shipped `app.yaml`, which supplies all three members; the dead-property half and a lesser claim survive

**Severity** — LOW

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — ART-009 is titled *"The declared allowed-MIME set is not the one enforced"* and
its Observation asserts, in its own words, that *"`UploadSettings.allowed_mime_types` declares
`[TEXT_CSV, APPLICATION_GZIP]`"* and that *"the declared set and the enforced set already differ by
one member — `application/x-gzip` ... is accepted by the code and forbidden by the
configuration."* Only the first half of that is true, and it is true of a *class default* rather
than of the shipped configuration. `Settings.settings_customise_sources` registers
`YamlConfigSettingsSource(settings/app.yaml)` as source 4 (`config.py:679-690`), and
`src/mkobi/settings/app.yaml:40-43` declares `allowed_mime_types: [text/csv, application/gzip,
application/x-gzip]` — all three. Read at runtime, `get_config().allowed_mime_types` is
`['text/csv', 'application/gzip', 'application/x-gzip']`, byte-identical to
`MimeTypeEnum.allowed_values()`. The two sets do not diverge; they can only diverge if `app.yaml`
is deleted, which is not the shipped state. The Consequence's documentation half is also
unsupported: `docs/06-backend/configuration.md:174` is a single table row —
`| allowed_mime_types | upload.allowed_mime_types | Allowed MIME types |` — that enumerates no
values, so a reader cannot be told from it that `application/x-gzip` is refused. Two claims
survive. The property `Settings.allowed_mime_types` (`config.py:844-846`) is read by nothing: a
repository-wide grep of `src/` for `allowed_mime_types` returns the definition at `:339`, the
property at `:844`/`:846`, one unrelated local in `utils/file_utils.py:78-79` that also builds
from the enum, and the enforcement site at `services/file_processing.py:87-88` — which reads
`MimeTypeEnum.allowed_values()`. So `UPLOAD__ALLOWED_MIME_TYPES` has no effect. And the two
detection branches still return different verdicts for the same bytes: on this host `import magic`
raises `ImportError: failed to find libmagic`, the `except ImportError` heuristic at
`file_processing.py:44-70` is what runs, and a semicolon-delimited file is classified `text/csv`
and admitted, where a libmagic build would return `text/plain` and reject it.

**Evidence** — Executed against the real settings stack and the real detection function, not read
from the source. `get_config().allowed_mime_types` → `['text/csv', 'application/gzip',
'application/x-gzip']`; `MimeTypeEnum.allowed_values()` → the same three. On the host branch:
`detect_mime_type_from_content('semi.txt')` (bytes `category;sales\nA;1\n`) → `text/csv`;
`('comma.txt')` → `text/csv`; `('real.gz')` → `application/gzip`; and `import magic` →
`ImportError: failed to find libmagic. Check your installation`, matching the input's own
observation. The dead property was established by the grep above, not inherited.

**Consequence** — The band is right and stays LOW, but the report overstates the divergence it
exists to record, and it does so in the direction that makes the fix look urgent: a reader
compares `config.py:339-342` against the enforced set, sees one member missing, and concludes the
declared and enforced sets disagree. They do not, as shipped. The genuinely live halves — a
configuration key with no consumer, and a detector whose verdict depends on whether the image
happens to have `libmagic1` — are both narrower than the finding states, and the fix the input
recommends (delete the dead key, or invert the validator to read it) is still correct for the
dead-key half and unnecessary for the divergence half.

**Recommendation** — Re-type ART-009 onto what survives: the dead `Settings.allowed_mime_types`
property and the platform-dependent detection branch. Delete the "the declared set and the
enforced set already differ by one member" sentence and the documentation consequence that
depends on it, and add the third declaration site the finding does not mention —
`src/mkobi/settings/app.yaml:40-43`, which is the one that actually decides the value. No band
change. Cross-reference phase 02's CFG-006 rather than re-arguing it: phase 02 filed
`UPLOAD__ALLOWED_MIME_TYPES` as a documented production control no deployment supplies, which is
the same dead key seen from the configuration surface. Adjacency, not merge — phase 02's subject is
the deployment's environment, this one is a property in the settings graph with no reader.

### VAL-06-006 — The Cross-Finding Analysis says ART-002's remediation is separable; the Roadmap makes step 3 conditional on a decision only step 2 can make

**Severity** — LOW

**Zone** — "10. The Validated Report as an Artefact, and What Was Not Settled"

**Observation** — The Cross-Finding Analysis groups ART-001, ART-004 and ART-005 under one cause —
the worker treats the artefact as scratch space while the rest of the system treats it as an
addressable object — and then writes of ART-002: *"`ART-002` is the recording half of the same
cause and is listed separately only because its remediation is separable."* The Roadmap contradicts
this on the same artefact. Step 2 (ART-004) carries the gate *"decide explicitly whether a task is
re-runnable, because that decision determines whether step 3 is a column or a deletion"*, and Step 3
(ART-002, plus the recording half of ART-005) carries *"step 2's decision is made; if the column
route is taken, the Alembic revision lands here"*. Step 4 then gates on Step 3, and the Rollout
Safety section gates step 2 on step 5's disk budget. So the plan is ordered on the very dependency
the analysis says does not exist. The "separable" claim is the one place in the report where the
analysis and the plan describe different systems, and it is the place a reader planning a migration
would act on.

**Evidence** — Both statements are in the input at Cross-Finding Analysis and at Roadmap steps 2,
3, 4 and 5 respectively; no third statement reconciles them. The dependency is real and was
re-derived independently rather than taken from either section: ART-002's own Recommendation offers
"one nullable column" *or* "declare the artefact scratch space, delete the two name-based
selectors", and ART-004's remedy — retain the artefact past the terminal state, or unlink on every
terminal path — is the same decision stated from the other side. The Rollout Safety section
compounds it: "unlinking after the commit means an artefact now survives a run that failed" is
true only under the first branch.

**Consequence** — The Cross-Finding Analysis is the section a reader uses to decide what can be
remediated in parallel, and it is the section the Roadmap contradicts. Read together they give two
different answers to "can ART-002 be scheduled independently of ART-004?", and the wrong answer is
the one in the analysis. No band moves and no finding is affected.

**Recommendation** — Amend the Cross-Finding Analysis sentence to state that ART-002's remediation
is *contingent* on ART-004's retention decision, and cross-reference the Roadmap's own gate rather
than restating the relationship differently. Prose only; no identifier is renumbered.

### VAL-06-007 — ART-005's Evidence says no other `unlink`/`rmtree` exists in `src/`; its own Appendix E names the one that does, and two further citations resolve one line past or outside their target

**Severity** — LOW

**Zone** — "1. The Claim Re-Derived from the Executing Path"

**Observation** — ART-005's Evidence asserts that the four removal-failure handlers it enumerates
are the whole population, and supports that with a quoted command: *"there is no other
`unlink`/`rmtree` in the project outside tests (`grep 'unlink|rmtree|shutil\.' src/`)"*. The
assertion is false. That grep returns eight `unlink` sites and one `shutil.rmtree`, and the
report's own Appendix E records the ninth: *"`platformdirs.user_cache_dir("mkobi", appauthor=False)
/ "uploads" / {user_id}` (`utils/file_utils.py:18-31`) — a second, differently-rooted temp area
created by `get_user_temp_dir`, which has no caller in `src/`."* The `rmtree` is at
`utils/file_utils.py:42`, inside `cleanup_temp_dir`, which is not a private helper — it is
re-exported from the package's public surface at `utils/__init__.py:9` and `__init__.py:13`. Two
further citations in the same class were found while resolving anchors and are recorded here
because they are the same defect rather than new ones. ART-009 cites
`docker/Dockerfile:46` and `:81` for the two stages that install `libmagic1`: `:46` is correct
(`FROM … AS base` opens at `:28`), and the `prod-base` stage opens at `:64` with `libmagic1` at
**`:80`** — `:81` is the next line, `curl`. And ART-009 cites `main.py:10-25` as "the way
`main.check_dependencies` already does" a hard-dependency check: `:10-25` is the module-level
`REQUIRED_MODULES` list, and `check_dependencies` is defined at `:28-38` and called at `:50`. The
claim is wrong in the direction that matters for a reader verifying it: the sentence reads as "I
ran this and there was nothing else", and running it produces a ninth removal site that the
report itself has already written down.

**Evidence** — The grep run against the working tree returns, in `src/`: `unlink` at
`services/file_cleanup.py:40` and `:93`; `services/file_processing.py:266`;
`api/routes/upload.py:183` and `:231`; `workers/data_worker.py:533`, `:564` and `:596`; and
`shutil.rmtree` at `utils/file_utils.py:42`. `cleanup_temp_dir` and `get_user_temp_dir` are both
importable from `mkobi.utils` (`utils/__init__.py:9`). For the two Dockerfile citations,
`Select-String docker/Dockerfile -Pattern libmagic` returns exactly two hits, `:46` and `:80`,
against six `FROM` lines at `:10`, `:28`, `:64`, `:102`, `:132` and `:156`. For `main.py`,
`REQUIRED_MODULES` is at `:10-25` and `check_dependencies` at `:28`. The input's substantive
claim is nonetheless correct and was re-derived: every removal-failure path in the project
terminates in a log call and nothing else — `file_cleanup.py:42-43` and `:100-101`,
`data_worker.py:565-570` and `:594-600` — with no column, counter or metric anywhere, and
`cleanup_stale_temp_files` has exactly one production caller (`db/starter.py:180`), so a failed
removal is never retried until a human restarts a process.

**Consequence** — The finding stands at MEDIUM and its recommendation stands. What is wrong is the
evidence: a reader who re-runs the quoted command finds a removal site the report has already
excluded, and has to work out whether the exclusion invalidates the enumeration. It does not — the
ninth site removes a directory no production path creates — but the report's own text contradicts
its own Evidence field, which is the same class of defect VAL-05-005 recorded for phase 05. The
two off-by-one citations are individually harmless — both claims are true, and both are in
findings whose band does not move — but they are the third and fourth instances of a report
citing a line it did not read, and they are the reason the anchor ledger was built mechanically
rather than by spot check.

**Recommendation** — Amend the Evidence sentence to scope the claim: the four failure handlers are
the complete population *for the accepted-artefact area*, and the ninth site
(`utils/file_utils.py:42`) removes the `get_user_temp_dir` tree, which no production path creates —
a conclusion Appendix E already reaches. Correct `Dockerfile:81` to `:80` and `main.py:10-25` to
`main.py:28-38` (or restate the claim as being about `REQUIRED_MODULES`). No band changes, and no
change to any recommendation.


### VAL-06-008 — Five of the nine recommendations offer a choice of directions where the shared template requires one, so none of the five is executable as written

**Severity** — LOW

**Zone** — "5. Whether the Recommendation Can Be Carried Out"

**Observation** — The shared template requires, per finding: *"the smallest change that removes the
effect, and the direction to take when the fix has more than one reasonable shape."* Phase 06's own
Report Output repeats the contract. Five of the nine recommendations name the shape of two
directions without choosing one, which the 99 rubric classes as *"substantiated but unusable: a
distinct outcome from rejection, recorded as such rather than passed over or counted as a
failure."* ART-001: make `CSVLoader` total **and** wrap `app.py` in `BaseException` (or supervise
the task). ART-002: "Pick one of the two coherent models" — a nullable column *or* scratch space
with the selectors deleted. ART-003: a byte ceiling **or** a dedicated log volume **or** moving the
sweep to the periodic task, bundled without a priority. ART-004: keep the file when retryable
**and** delete `trigger_processing` and `find_task_file` if it is not. ART-007: resolve from a
configured path **and** add `index.html` to the `HEALTHCHECK` **and** "Consider refusing to start
... when the bundle is absent in a production tier". ART-009 adds a sixth: delete the dead key **or**
invert the validator. Three of the nine — ART-005, ART-006, ART-008 — do name one action. The
defect is systemic rather than per-finding, and it is not new to this corpus: phase 01 filed
VAL-005 for two recommendations offering alternatives, and phase 02 filed VAL-008 for one.

**Evidence** — Counted against the template's own sentence and re-read in the input's own words.
The two load-bearing cases are distinguished because they differ in kind from the other four.
ART-001's alternatives are complementary and both executable today — the `BaseException` guard is
needed regardless of which extension rule is chosen. ART-002's are mutually exclusive and
irreversible in one direction: the column route adds an Alembic revision, the scratch-space route
deletes two functions and one shipped test's subject, and the input's own Roadmap makes every
later step wait on that choice without making it. ART-003, ART-004, ART-007 and ART-009 bundle
independent actions whose order matters — ART-004's own Rollout Safety says step 5's disk budget
must be known before step 2 ships, and nothing in the Recommendation says so.

**Consequence** — No finding is rejected and no band moves; every target named in all nine resolves
and the reasoning behind each direction is sound. The effect is on planning rather than on
correctness: a reader who schedules from the Recommendation fields alone gets five parallel tracks
whose contents are undetermined, and a reader who schedules from the Roadmap gets the ordering
without the decision, which is the VAL-06-006 defect seen from the other end.

**Recommendation** — Rewrite the five recommendations as one action each, with the discarded
direction recorded as a rejected alternative and one clause of rationale. ART-002 needs the
retention decision moved out of the recommendation and into a named precondition of the roadmap —
which the roadmap already has — so that step 3's shape is settled before step 2 is scheduled.

### VAL-06-009 — The `baseline:` field names a commit whose `config.py` line numbers differ by roughly 48 from the tree every `config.py` anchor in the report was resolved in, and the report never says which tree it read

**Severity** — LOW

**Zone** — "8. The Shared Findings Template as a Controlled Artefact"

**Observation** — The report's front matter declares `baseline: c3c0a61bf41cad68bf3a3ac105de91ea63c82268`
and `baseline-dirty: true`, which is honest but incomplete, and Appendix A then makes a stronger
claim it does not support: *"Both modified source files are cited in this report, so their anchors
were re-verified after all evidence was gathered: `config.py:332` (`temp_dir`), `:334`
(`max_file_size_mb`), `:339` (`allowed_mime_types`), `:464` (`temp_password_ttl_seconds`) and
`starter.py:180` (the sweep call) ... are unchanged from the values read at the start. No anchor
cited in this report moved."* Every one of those `config.py` line numbers is a line in the **dirty**
working tree, not in the commit the `baseline:` field names. At `c3c0a61` the same declarations
are at `:284`, `:286`, `:291` and `:416` — a shift of +48. So "no anchor moved" is true only
against the tree the report read, and a reader who resolves `config.py:339` against the commit the
report names lands on a different statement and concludes the report's anchors are wrong. The
report is not drifting and the values are identical in both states — `max_file_size_mb = 100`,
`temp_password_ttl_seconds = 86400`, `stale_file_threshold_hours = 24`, `lazy_threshold_mb = 10.0`,
`max_file_size = 104857600`, all read at runtime — so nothing here misleads about the system. The
defect is that the front matter names a commit the anchors were not resolved against, and the
template's front-matter fields are exactly where a reader looks for that. **This has since become
a standing hazard rather than a transient one**: the concurrent remediation team committed that
dirty `config.py` as `5a2cfb6` while this validation was running, so the tree the report read is
now the current `HEAD` and the `baseline:` field names its parent. The line numbers resolve
identically in both commits — `git show 5a2cfb6:src/mkobi/config.py` places `temp_dir` at 332,
`max_file_size_mb` at 334, `allowed_mime_types` at 339 and `temp_password_ttl_seconds` at 464, the
same as the tree that was audited — so a reader who resolves against the named baseline still lands
48 lines away, while a reader who resolves against `HEAD` gets the right line. The report now has
two commits it can legitimately be read against and names neither explicitly.

**Evidence** — Compared the two trees mechanically. `git show c3c0a61:src/mkobi/config.py` places
`temp_dir` at 284, `max_file_size_mb` at 286, `allowed_mime_types` at 291,
`temp_password_ttl_seconds` at 416, `Settings.upload_temp_dir` at 785 and
`Settings.allowed_mime_types` at 795. The working tree — and `5a2cfb6`, which the team committed
from it — places them at 332, 334, 339, 464, 834 and 844, the exact numbers the report cites.
`git log --oneline c3c0a61..HEAD` returns one commit, `5a2cfb6`, and
`git diff --stat c3c0a61..HEAD` shows it touches exactly `src/mkobi/config.py`,
`src/mkobi/db/starter.py`, `tests/test_config.py` and `tests/test_starter.py` — the four files that
were dirty when this validation began, and no other tracked source file. `db/starter.py` anchors
happened not to move: `cleanup_stale_temp_files` is at `:180` and `cleanup_old_logs` at `:395` in
`c3c0a61`, in the dirty tree and in `5a2cfb6` alike, so the report's `starter.py` citations are
correct against every state. The runtime values were read from the live settings stack, not from
any file.

**Consequence** — The report's Appendix A asserts a stronger invariant than it established, and a
reader who checks it against the named commit finds a 48-line discrepancy in the two files the
report says it re-verified. Nothing about the system is misreported and no remediation changes, so
the band is LOW — but a later run that trusts the `baseline:` field to resolve anchors will record
a false drift, and this is the second report in the set to hit the same collision (the phase-05
validation report recorded it for the same commit pair and the same two files).

**Recommendation** — Add one line to Appendix A stating that the anchors were resolved in the dirty
working tree, that the concurrent remediation's `config.py` edit shifts every line below 78 by
about 48, and that the values behind each cited anchor are identical in `c3c0a61` and in the
`5a2cfb6` that later committed it — the form the phase-05 validation report used. Record both
commits explicitly rather than only the baseline, so a reader can resolve against either. A
`baseline-note` front-matter field carrying the same sentence would put it where a reader looks
first. No finding changes.

### VAL-06-010 — The namespace ruling this report was told to apply is forced by a collision that already exists and that neither prior report records: `VAL-001` names two different findings

**Severity** — LOW

**Zone** — "7. Finding-ID Namespace Integrity — The Ruling This Phase Owns"

**Observation** — This phase was instructed to mint validation identifiers under `VAL-06-`
because "the flat `VAL-` prefix is already occupied by the phase-01 and phase-02 validation
reports". Re-derived rather than inherited, the occupation is worse than the instruction states:
the flat prefix was occupied **twice over**. The phase-01 report minted `VAL-001` through
`VAL-008`; the phase-02 report independently minted `VAL-001` through `VAL-009`. `VAL-001` in
`.ai/audit/99-validation/` therefore resolves to two findings with two different subjects — "TOPO-006
asserts that the dependency-injection layer executes a query; the cited lines are a docstring
example" in one file and "The front-matter severity tally contradicts the report's own
per-finding bands, and the Summary repeats the stale classification" in the other. Neither report
records the collision, and the 99 rubric's MEDIUM band names exactly this — "an identifier
resolving to more than one finding". The later reports then established the compound form on their
own initiative: `VAL-03-001`, `VAL-04-001` … `VAL-04-010`, `VAL-05-001` … `VAL-05-005`. The
audited phase itself is clean: `ART-` was declared by phase 06's command file, `ART-001` through
`ART-009` were minted in one run with no duplication, and the compound form pairs the template's
front-matter `phase:` value (`06-file-artifacts`) with the prefix, resolving to `ART-06-…` for any
future phase-local series.

**Evidence** — Enumerated across the whole directory. Six validated reports exist; the `###`
headings in the five completed ones yield `TOPO-001`…`TOPO-008` plus `VAL-001`…`VAL-008` (phase
01), `CFG-001`…`CFG-010` plus `VAL-001`…`VAL-009` (phase 02), `TXN-001`…`TXN-012` plus `VAL-03-001`
and `VAL-03-002` (phase 03), `AUTH-001`…`AUTH-008` plus `VAL-04-001`…`VAL-04-010` (phase 04),
`DP-001`…`DP-019` plus `VAL-05-001`…`VAL-05-005` (phase 05). `VAL-001` and `VAL-002`…`VAL-008`
each appear twice; `VAL-009` appears once. A repository-wide grep of `src/`, `tests/`, `docs/`,
`alembic/` and `frontend/src/` for `\b(ART|VAL)-\d` returns nothing, so there is no in-source
provenance marker to migrate and none to retire — the 99 rubric's question about markers resolves
to "none found" for every prefix in the set.

**Consequence** — The collision is a set-level defect, not a defect in this input, and this run
does not write into `.ai/audit/99-validation/01-*` or `02-*`; it is recorded here so it is not
inherited silently by a seventh run. A reader who greps `VAL-001` across the directory gets two
unrelated findings and no way to tell which one a citation meant. The ruling applied to phase 06
is unaffected: `VAL-06-` is minted, no `ART-` identifier is renumbered, and the compound form is
now the convention for four consecutive reports.

**Recommendation** — Apply the ruling as instructed — `VAL-06-`, recorded in this report's
`namespace-note` — and record the `VAL-001` duplication here as the reason the flat prefix must
not be reused. Whoever consolidates the directory should disambiguate the two `VAL-001` entries
(one bare, one suffixed per phase) before a sixth report is written; this validation changes
neither file, since both are already written out and repairing a sibling report is outside a
per-phase run.

## Distribution

Of the ten validation-level findings, the concentration is not in the modules but in one habit:
**the report's own supporting text asserts more than the artefact behind it sustains.** Five of the
ten (VAL-06-003 through VAL-06-007, and VAL-06-009) are the same defect seen from five sides — a
coverage claim that overstates runtime reach, a citation that names a branch which does not do what
the claim says, a central claim refuted by a third declaration site the finding never mentions, an
enumeration that its own appendix contradicts, and a baseline field that names a tree the anchors
were not read from. None of the five changes a band.

- **By defect class** — evidence defect 5 (VAL-06-003, 004, 005, 007, 009); report-internal
  contradiction 1 (VAL-06-006); unusable recommendation 1 (VAL-06-008); cross-phase duplication 1
  (VAL-06-002); namespace integrity 1 (VAL-06-010); severity mis-grade 1 (VAL-06-001).
- **By band effect** — one band moves, upward (ART-004, HIGH to CRITICAL). No band moves down. No
  finding is rejected and none is left unsettled, so no true defect leaves this report's account.
- **By anchor** — of the 70 line references the input cites, 64 resolve and name the symbol they
  claim, 4 resolve but name something else, and 6 resolve only in the dirty tree. The failures
  cluster in three places: the two files the concurrent remediation team is editing, one branch
  inside `loader.py`, and two single-line slips in `docker/Dockerfile` and `src/mkobi/main.py`.
- **By rubric fit** — six of the nine audited findings map to a phase-06 rubric clause almost
  verbatim (ART-002 to the HIGH clause on store-versus-record divergence, ART-003 to the MEDIUM
  clause on an age-reclaimed area unbounded in count or bytes, ART-005 to the MEDIUM clause on a
  removal failure with no reader, ART-006's residue to the MEDIUM clause on a secret the caller is
  told exists, ART-007 to the MEDIUM clause on a served component whose absence changes the route
  table, ART-004 to the CRITICAL clause on undetectable irreversible removal). That the input
  applied the rubric correctly five times out of six is why VAL-06-001 is a single re-grade and not
  a re-grading of the report's severity discipline.

## Cross-Finding Analysis

Two causes account for nine of the ten validation-level findings, and one finding is independent.

**The report's supporting prose was not reconciled against the artefacts it cites.** The
enumeration is the same in all five cases: a sentence asserts an invariant stronger than the
evidence establishes, and the assertion is what a reader trusts. The runtime-coverage claim names
eight blocks and its own Evidence fields discharge five and a half (VAL-06-003). The gzip-branch
citation names two sites and the second one only logs (VAL-06-004). The allowed-MIME claim names
two declaration sites and a third one in `app.yaml` decides the value (VAL-06-005). The removal
enumeration claims completeness and the ninth site is in the report's own Appendix E, alongside
two citations one line past their target (VAL-06-007). The baseline reconciliation claims no anchor
moved and the moved anchors are the `config.py` ones (VAL-06-009). All five would have been caught
by running the quoted commands one more time and by reading each finding's Evidence field against
the sentence that summarises it.

**The report's plan and its analysis describe two different systems.** VAL-06-006 records the
Cross-Finding Analysis calling ART-002's remediation separable while four consecutive Roadmap steps
gate on it; VAL-06-008 records five recommendations that defer to a decision the roadmap also
defers, so the report never settles the direction for its own highest-band finding. The one
independent finding is VAL-06-010, the `VAL-001` namespace collision, which is a property of the
directory rather than of this input — and which is also the reason the phase-06 ruling is what it
is.

## Roadmap

**Step 0 — reconcile the report before anything is scheduled against it.** Apply VAL-06-001:
re-grade ART-004 from HIGH to CRITICAL and correct or delete the Summary's stated reason for the
empty band. This must precede the input's own Roadmap, because that Roadmap's ordering and its
Rollout Safety both assume the band it is replacing. Nothing in the system's behaviour changes; only
the table remediation is read from does.

**Step 1 — settle the retention decision the report defers in five places.** One decision: is an
accepted artefact re-runnable after it reaches a terminal state? It closes VAL-06-008 for ART-002
and ART-004, closes the input's Roadmap gates at steps 2, 3, 4 and 5, and converts two
mutually-exclusive recommendations into one executable action each. Must be true before Step 0's
re-grade is acted on, because the CRITICAL finding's remedy is one branch of the decision.

**Step 2 — split ART-006 and hand each half to its owner.** Phase 04 owns AUTH-002 (creation
fail-open) and AUTH-006 (retrieval `None`-collapse) and their two test blockers; phase 06 keeps the
residue — no revocation path other than collection and the TTL — and adds the tests its own
recommendation breaks (VAL-06-002). Coordinate with phase 04 rather than editing `store` and
`retrieve` from two plans; the input's step 6 and phase 04's AUTH-002/AUTH-006 remediation touch the
same two functions and the same two test modules.

**Step 3 — correct the five evidence defects (VAL-06-003, 004, 005, 007, 009).** One pass over the
report's Summary, four Observations, three Evidence fields and Appendix A — including the two
single-line slips at `Dockerfile:81` and `main.py:10-25` that ride along with VAL-06-007. No code
changes, no band changes beyond Step 0's; but the corrections must land before the report is used to
size ART-001's exposure, ART-009's divergence, or the count of blocks that were executed.

**Step 4 — fix the report-internal contradiction and the namespace record (VAL-06-006, 010).** The
Cross-Finding Analysis sentence about separability; the `VAL-001` collision, recorded here and left
for whoever consolidates the directory. Prose only.

The input's own steps 1–6 follow unchanged in substance and in membership. What changes is the
entry order: after the Step 0 re-grade, ART-004 is the phase's top item and the input's step 1
(ART-001, HIGH) becomes the second. ART-001's `app.py` `BaseException` guard should still ship
first of the two code changes if the two must land separately, because it is the only defence that
holds for base-class escapes from the worker other than the gzip mismatch — but that is an
execution preference inside step 1, not a band.

## Rollout Safety

This validation changes no code, no configuration, no schema and no behaviour. Everything in it
is a report edit, so the only thing that can break is a reader acting on the report as it stands —
which is why Step 0 is sequenced first.

Step 0 is the highest-leverage and the cheapest: raising ART-004 to CRITICAL changes what a reader
does first and changes nothing about what any code does. The risk to manage is double-counting —
phase 05 filed DP-001 against the producer-side of the same class of defect, and a reader who sees
two CRITICALs may merge them by reflex. They are not the same defect: DP-001 is the *rename* against
the *record commit* on the acceptance path in the API process; ART-004 is the *unlink* against the
*derived-data commit* plus unconditional removal on the rollback path in the worker. The input's
ruling of adjacency rather than merge is correct on the merits and this report confirms it (§C);
phase 05 owns DP-001, phase 06 owns ART-004, and the input's advice that they be coordinated in one
change is sound even though they are edits to two different files in two different processes — the
input's phrasing "the same commit to the worker's ordering" describes only one of the two.

Step 2 is the only step with a live coordination hazard, because two independently-owned plans
target the same functions. Resolve ownership with phase 04 before either ships; the technical change
itself is small and phase 04's AUTH-002 recommendation is already the executable form with both
blockers named.

Steps 3 and 4 touch prose only and revert with no trace. Nothing in this roadmap requires a test
run, a migration gate, a data dump or a deployment window.

## Appendices

### A. Per-finding disposition — all nine audited identifiers

Each disposition is the verdict on the claim **as filed**, re-derived from the executing path at
`c3c0a61` and its dirty tree. `confirmed` means the claim, its location and its band all survived;
`confirmed, re-graded` means the claim survived with a different band, recorded not applied;
`merged` means the claim survives and is already filed elsewhere under the same root cause;
`re-typed` means the finding is re-filed on the part of its claim that survives.

| id | band carried | band after | disposition | re-derived from | note |
|---|---|---|---|---|---|
| ART-001 | HIGH | HIGH | confirmed, trigger narrowed (VAL-06-004) | `file_processing.py:208-212`/`:235`; `loader.py:295-302`/`:133`/`:211-215`/`:164`; `data_worker.py:556`/`:588`; `task_queue.py:96`/`:104`; `app.py:131-141`/`:143`/`:169`; `Dockerfile:179` | `PanicException` MRO `PanicException -> BaseException -> object`, `isinstance(e, Exception) == False`; a real `TaskQueue` driven by the verbatim `app.py` loop shape ended on the first poisoned job with `consumer_raised: pyo3_runtime.PanicException`, `queue_depth_remaining: 1`, `second_job_processed: False`. An AST walk of the four files shows no handler naming a `BaseException` superclass. Narrowing: files above `lazy_threshold_mb` (10.0 MB) take the lazy branch and load a mislabelled artefact successfully. |
| ART-002 | HIGH | HIGH | confirmed | `processing_logs.py:30-72`; `file_processing.py:235`/`:284-309`; `file_cleanup.py:36`; `data_service.py:255`/`:279`/`:306`/`:337`; `db/starter.py:180` | `ProcessingLog` declares `id, dashboard_id, status, message, started_at, finished_at, error_code` and no name or path column. Three selectors, three rules: `{log.id}{ext}` (`:235`), `f"{task_id}.csv*"` (`:299`), `f"*{task_id}*.csv*"` (`file_cleanup.py:36`). `find_task_file` has one caller (`data_service.py:279`) and `trigger_processing` has none outside the protocol and the implementation; `cleanup_task_files` has none. `ProcessingStatusResponse.filename` is filled from `log.message` at `:306` and `:337`. Rubric clause matched verbatim. |
| ART-003 | MEDIUM | MEDIUM | confirmed | `upload.py:129-141`/`:148-152`/`:171`/`:181-196`/`:229-231`; `file_cleanup.py:46-106`; `config.py:343`; `compose.yml:113`/`:114`/`:132`/`:135`/`:142-143`; `Dockerfile:95`/`:117`/`:143`/`:176-177`; `logging_config.py:111-122` | Control inventory re-derived and correctly classified: bytes per request (declared `Content-Length` at `:129`, cumulative streamed bytes at `:181`), count per caller per hour (`max_attempts=100, ttl=3600`, key `upload:{user_id}`), time (`stale_file_threshold_hours = 24`), and nothing for the in-flight area. `read_only: true` at `:135` with no tmpfs on the `app` service (the tmpfs at `:252` is nginx's). `app_data` carries `tmp_uploads` and `logs/app.log` together. No code writes `/app/data/uploads`. Rubric clause matched verbatim. |
| ART-004 | HIGH | **CRITICAL** | confirmed, **re-graded up** (VAL-06-001) | `data_worker.py:532-534`/`:537-543`/`:561-571`/`:585`/`:587`/`:593-602`/`:603`; `file_processing.py:284-309`; `data_service.py:255`/`:279`; `processing_logs.py:30-72` | The unlink at `:532-534` and the COMPLETED write at `:537-543` are both inside the `session.begin()` block opened at `:585` and entered at `:587`; `Transaction.__aexit__` is what commits. The failure branch unlinks at `:594-596` and re-raises at `:603`, so the rollback path destroys the source too. No detector in that direction; no reversing path. Phase 06's rubric CRITICAL clause — "an artefact removed with no detection of the loss and no path that reverses it" — is met in the finding's own words. |
| ART-005 | MEDIUM | MEDIUM | confirmed, one evidence sentence narrowed (VAL-06-007) | `file_cleanup.py:42-43`/`:100-101`; `data_worker.py:565-570`/`:594-600`; `db/starter.py:180`; `app.py:120-125`; `file_utils.py:42` | Every removal-failure path terminates in a log call; no column, counter or metric anywhere in `src/`. `cleanup_stale_temp_files` has exactly one production caller. `cleanup_task_files` has none. The Evidence sentence "there is no other `unlink`/`rmtree` in `src/`" is false — `utils/file_utils.py:42` is one — and Appendix E already excludes it. Rubric clause matched verbatim. |
| ART-006 | MEDIUM | MEDIUM (residue only) | **merged** into AUTH-002 and AUTH-006 (VAL-06-002) | `temp_password_store.py:47-48`/`:63-75`; `admin.py:305-336`/`:321`/`:330`/`:417-422`; `auth_service.py:583`; `config.py:464`; `app.yaml` / `deps.py:134-143` | Creation half is AUTH-002 (same function, same two call sites, same consequence). Retrieval half is AUTH-006 verbatim, including the `:73-75` catch-all and the `NOT_FOUND` collapse at `admin.py:418-422`. Neither AUTH- identifier is renumbered; phase 04 owns both. Phase 06's own residue confirmed independently: the only calls on the store in `src/` are two `store` calls and one `retrieve`, with no delete, revoke or invalidate anywhere, so the TTL is the sole expiry. The CRITICAL clause was tested and not met — the TTL bounds the collectible window. |
| ART-007 | MEDIUM | MEDIUM | confirmed | `app.py:308-313`/`:328`/`:340-344`/`:361-385`/`:387-391`/`:392-397`; `Dockerfile:176-177`; `compose.yml:142-143` | Three presence states driven through `create_app()` + `TestClient`. *Absent*: no mount, `static_files: unavailable`, `/` and `/dashboards/abc` 404 `application/json`. *Present but wrong* (`dist` without `index.html`): **no mount**, byte-identical route table, `static_files: available`. *Correct*: `/` 200 `text/html`, `/dashboards/abc` 200 `text/html`, `/assets/index-x.js` 200 `text/javascript`, `/assets/missing.js` 200 `text/html` (the SPA fallback swallows a missing asset). One divergence is platform-scoped and does not affect the finding — see §G. Rubric clause matched verbatim. |
| ART-008 | LOW | LOW | confirmed, probe re-derived independently | `file_cleanup.py:84`/`:86-101`/`:100-101`; `db/starter.py:180`/`:181-182`; `Dockerfile:179`; `compose.yml:181` | **Not a probe artefact.** Three independent trials, four concurrent sweepers over three 72-hour-old files: 3 successful deletions every time, returns `[2,0,1,0]`, `[2,0,1,0]`, `[3,0,0,0]`, and **7, 7 and 8** spurious `ERROR … no read/file` lines from the losing sweepers — same mechanism, a different count each run, so the input's specific figure of 5 is one interleaving rather than a constant. `FileNotFoundError` is caught by `except Exception` at `file_cleanup.py:100` and logged at ERROR, indistinguishable in shape from a genuine `EACCES`. `deleted_count` covers only the files that process won. |
| ART-009 | LOW | LOW | **re-typed** (VAL-06-005) | `config.py:339-342`/`:344-346`/`:679-690`/`:844-846`; `settings/app.yaml:40-43`; `file_processing.py:26-70`/`:67`/`:85-94`; `enums.py:92-102`; `file_utils.py:78-79`; `configuration.md:174` | `get_config().allowed_mime_types` → `['text/csv', 'application/gzip', 'application/x-gzip']`, byte-identical to `MimeTypeEnum.allowed_values()`; the shipped `app.yaml` supplies all three, so the "declared set differs by one member" claim is refuted as shipped, and `configuration.md:174` enumerates no values so the documentation consequence is unsupported. Survives: the property is read by nothing, so `UPLOAD__ALLOWED_MIME_TYPES` has no effect; and the two detection branches disagree — host `import magic` → `ImportError`, and the `;` heuristic at `:67` classifies a semicolon file `text/csv` where libmagic would return `text/plain`. |

### B. Anchor ledger — every line reference the input cites, resolved mechanically

Resolution was performed before adjudication, in two states: the working tree (which is what the
input read, and which the concurrent remediation team has since committed as `5a2cfb6` with
identical line numbers) and `git show c3c0a61:` for the two files that team was editing.
"R" = resolves and names the symbol claimed. "R*" = resolves but names something other than the
claim. "M" = the symbol is at that line only in the tree that was read, not in `c3c0a61`.

| anchor | tree | verdict | symbol at that line |
|---|---|---|---|
| `file_processing.py:85-94` | working | R | `validate_mime_type`, content detection then `MimeTypeEnum.allowed_values()` |
| `file_processing.py:26-70` | working | R | the `try: import magic` / `except ImportError` module-scope branch pair |
| `file_processing.py:67` | working | R | `b"\n" in file_buffer and (b"," in ... or b";" in ...)` |
| `file_processing.py:208-212` | working | R | `file_ext` derived from `detect_file_type(filename)` |
| `file_processing.py:235` | working | R | `final_file_path = upload_dir / f"{log.id}{file_ext}"` |
| `file_processing.py:237` | working | R | `file_path.replace(final_file_path)` |
| `file_processing.py:253-254` | working | R | the "Enqueue job BEFORE commit" comment the input quotes elsewhere |
| `file_processing.py:266` | working | R | `final_file_path.unlink(missing_ok=True)` — the enqueue-failure compensation |
| `file_processing.py:299-307` | working | R | `find_task_file`'s `f"{task_id}.csv*"` glob, zero-match and multi-match raises |
| `loader.py:44-67` | working | R | `detect_file_type` |
| `loader.py:133` | working | R (added) | the `file_size_mb > lazy_threshold_mb` branch selection |
| `loader.py:164` | working | R | `except Exception as e:` in `load_csv` |
| `loader.py:211-215` | working | **R\*** | the lazy branch's debug log — it does **not** open `gzip` (VAL-06-004) |
| `loader.py:295-302` | working | R | the eager `gzip.open` branch, the genuine gzip-selecting site |
| `data_worker.py:405-406` | working | R | `settings.get("separator")` into `csv_parse_config` |
| `data_worker.py:532-534` | working | R | success-path unlink, inside the transaction |
| `data_worker.py:556` | working | R | `except Exception as e:` (test-mode branch) |
| `data_worker.py:565-570` | working | R | the error-path unlink's `except Exception` + warning |
| `data_worker.py:585` | working | R | `async with session.begin():` |
| `data_worker.py:588` | working | R | `except Exception as e:` (production branch) |
| `data_worker.py:593-602` | working | R | the error-path unlink plus `raise` |
| `task_queue.py:96` | working | R | `except Exception as e:` around the task call |
| `app.py:116` | working | R | `await mark_orphaned_uploaded_logs_failed()` |
| `app.py:120-125` | working | R | the periodic `start_stale_processing_cleanup_task` task |
| `app.py:131-141` | working | R | the `queue_worker` loop, `CancelledError` + `Exception` only |
| `app.py:143` | working | R (added) | `asyncio.create_task(queue_worker())` — created once |
| `app.py:169` | working | R (added) | shutdown reaps the task only `if not queue_worker_task.done()` |
| `app.py:308-313` | working | R | `/health/detailed`'s `static_files` from `os.path.isdir` alone |
| `app.py:340-344` | working | R | `static_dir`, `index_path`, the two-part existence condition |
| `app.py:361-385` | working | R | `SPAStaticFiles.get_response` and the `API_PREFIXES` guard |
| `app.py:381` | working | R | the `FileResponse(index_path)` fallback — the only one in the project |
| `app.py:387-391` | working | R | the catch-all mount at `/` |
| `app.py:392-397` | working | R | the single `else` warning branch |
| `upload.py:129-141` | working | R | the declared-`Content-Length` size check |
| `upload.py:148-152` | working | R | the rate limiter, `max_attempts=100`, `ttl=3600` |
| `upload.py:171` | working | R | `upload_{uuid4}_{sanitized_filename}` |
| `upload.py:181-196` | working | R | the cumulative streamed-bytes ceiling |
| `upload.py:226-231` | working | R | the `finally` unlink of the in-flight file |
| `file_cleanup.py:36` | working | R | `cleanup_task_files`'s `f"*{task_id}*.csv*"` glob |
| `file_cleanup.py:42-43` | working | R | its `except Exception` + `logger.error` |
| `file_cleanup.py:46-106` | working | R | `cleanup_stale_temp_files` end to end |
| `file_cleanup.py:100-101` | working | R | its `except Exception` + `logger.error` |
| `file_cleanup.py:109-165` | working | R | `cleanup_old_processing_logs` — the dead duplicate |
| `data_service.py:255` / `:279` | working | R | `trigger_processing` and its `find_task_file` call |
| `data_service.py:306` / `:336-337` | working | R (minor) | `filename=log.message or "unknown"` in both responses; `:336` is the opening line of the `ProcessingStatusResponse(` call, the expression is at `:337` |
| `processing_logs.py:30-72` | working | R | all seven mapped columns; no name or path column |
| `enums.py:92-102` | working | R | `MimeTypeEnum`, three members |
| `temp_password_store.py:47-48` | working | R | the fail-open `except Exception` + `logger.error` |
| `temp_password_store.py:63-75` | working | R | the MULTI/EXEC pipeline and the `except` returning `None` |
| `admin.py:305-336` | working | R | the approve handler, store at `:321`, commit at `:330` |
| `admin.py:417-422` | working | R | the retrieval handler's `None` → `NOT_FOUND` mapping |
| `auth_service.py:583` | working | R (added) | the second `store` call, in the reset path |
| `deps.py:134-143` | working | R (added) | `get_temp_password_store` |
| `db/starter.py:180` | **all three states** | R | `cleanup_stale_temp_files()` — identical line in `c3c0a61`, the read tree and `5a2cfb6` |
| `db/starter.py:181-182` | read tree / `5a2cfb6` | R | the partial-count summary line |
| `db/starter.py:395-418` | **all three states** | R | `cleanup_old_logs` — identical line in `c3c0a61`, the read tree and `5a2cfb6` |
| `db/starter.py:400` | read tree / `5a2cfb6` | R | inside `cleanup_old_logs` |
| `config.py:332` / `:334` / `:339-342` / `:464` | read tree and `5a2cfb6` only | **M** | `temp_dir` / `max_file_size_mb` / `allowed_mime_types` / `temp_password_ttl_seconds` — at `c3c0a61` these are `:284` / `:286` / `:291` / `:416` (VAL-06-009) |
| `config.py:347-351` | read tree / `5a2cfb6` | **M** | `UploadSettings.__init__`'s `temp_dir` fallback — `:349-350` now |
| `config.py:844-846` | read tree / `5a2cfb6` | **M** | `Settings.allowed_mime_types` — `:795-797` at `c3c0a61` |
| `Dockerfile:46` | committed | R | `libmagic1` inside `FROM … AS base` (stage opens at `:28`) — the claim that both stages install it is true |
| `Dockerfile:81` | committed | **R\*** | `curl`. The `libmagic1` line inside `FROM … AS prod-base` (stage opens at `:64`) is `:80` — the claim holds, the anchor is one line past its target |
| `Dockerfile:95` / `:117` / `:143` | committed | R | the three `mkdir -p … /app/data/uploads …` lines |
| `Dockerfile:176-177` | committed | R | the `HEALTHCHECK` against `/health` |
| `Dockerfile:179` | committed | R | `CMD [… "--workers", "4"]` |
| `compose.yml:113` / `:114` | committed | R | `UPLOAD__TEMP_DIR` / `LOGGING__LOG_FILE`, both under `/app/data` |
| `compose.yml:132` | committed | R | the `app_data:/app/data` mount |
| `compose.yml:142-143` | committed | R | the `curl -f …/health` healthcheck |
| `compose.yml:181` | committed | R | the `rqworker` CLI command |
| `compose.yml:247` | committed | R | the nginx `../frontend/dist:/usr/share/nginx/html:ro` bind |
| `logging_config.py:111-122` | working | R | the `RotatingFileHandler`, 10 MB × 5 |
| `main.py:10-25` | working | R\* (added) | the module-level `REQUIRED_MODULES` list; `check_dependencies` is at `:28-38` and calls it from `:50` — the precedent ART-009 cites is the list, not the function |
| `utils/file_utils.py:18-31` | working | R (added) | `get_user_temp_dir`'s `platformdirs` cache root |
| `test_data_service.py:641-657` | working | R | the body of `test_validate_file_spoofed_gzip_rejected` (def at `:637`) |
| `test_upload_api.py:731` | working | R | `test_cleanup_task_files_called_during_processing` |
| `test_temp_password_store.py:164-181` | working | R | `test_store_fail_open_on_error` |
| `test_temp_password_store.py:184-190` | working | R (added) | `test_retrieve_fail_graceful_on_error` — the blocker ART-006 omits |
| `test_temp_password_retrieval.py:126-130` | working | R (added) | the single-use 404 assertion — the second blocker ART-006 omits |
| `configuration.md:174` | working | **R\*** | a table row with no values enumerated (VAL-06-005) |
| `settings/app.yaml:40-43` | working | R (added) | the declaration that actually decides the value — a third site the input does not mention |

### C. Seam rulings — contested and adjacent claims

Phase 04 and phase 05 are the phases that overlap this input. Both filed before it; both have been
validated. Nothing is written into `.ai/audit/04-authentication/` or `.ai/audit/05-data-pipeline/`,
and no `AUTH-` or `DP-` identifier is renumbered.

| contested | rival claim | phase that owns it | ruling |
|---|---|---|---|
| ART-006 (creation half) | **AUTH-002** (HIGH) — `store` fails open at `temp_password_store.py:47-48`; the approval path stores at `admin.py:321`, commits at `:330` and returns the handle at `:335`; the account is left holding a password no live store holds | 04 | **Same root cause; merge into AUTH-002.** Identical function, identical two call sites, identical consequence; phase 04's finding is the more complete statement and carries the executable recommendation. Phase 06 keeps no part of this half. |
| ART-006 (retrieval half) | **AUTH-006** (MEDIUM) — `retrieve` returns `None` for absent, already-deleted and any Redis error (`:73-75`); the route collapses all three into `NOT_FOUND` (`admin.py:418-422`) | 04 | **Same root cause; merge into AUTH-006.** Verbatim overlap, including the claim that a failed collection reports a spent token while the secret is still present. Phase 04's recommendation already names both tests this half breaks, which ART-006 does not. |
| ART-006 (residue) | none | 06 | **Phase 06 keeps this half.** Nothing in `src/` deletes, revokes or invalidates the secret on user deletion, request rejection or password change; the 24-hour TTL is the only expiry. This is the artefact's whole life, which is block 5's own subject. |
| ART-004 | **DP-001** (CRITICAL) — the *rename* and the *enqueue* happen before the record's `commit()` on the acceptance path, with compensation on one edge only, and `_update_processing_log_status` never checks `rowcount` | 05 | **Adjacency, not merge — the input's ruling is correct on the merits.** Different resource ordering (`rename` vs `unlink`), different transaction, different process (the API worker that served the upload vs the consumer worker), different failure edge, different function to edit. The shared class is "a file operation ordered before the commit of the record that describes it"; phase 06's own scope paragraph already carves that class out to 05 only where the two effects are "written by different processes", which is not the case inside ART-004. **Phase 05 owns DP-001's remediation; phase 06 owns ART-004's.** One qualification on the input's own advice: DP-001 is an edit to `file_processing.py`, so the two cannot be "the same commit to the worker's ordering" — coordinate them, do not merge them. |
| ART-001 / ART-002 | **TOPO-001** (a failed job stays `uploaded` until the process restarts) and the unreachable `FAILED` write | 01 | **Adjacent, already filed elsewhere, correctly cross-referenced by the input.** Re-derived and confirmed: the `except Exception` at `data_worker.py:588` re-raises at `:603` inside `session.begin()`, so the `FAILED` write at `:608-614` — placed after the `async with get_session()` block — is unreachable, and a `PanicException` skips the handler entirely. The input names TOPO-001 in ART-001's Consequence and files nothing against it. No duplication. |
| ART-008 | **TOPO-005** (four workers each run the boot preconditions) | 01 | **Adjacent, not contested.** TOPO-005 owns the multiplicity; ART-008 owns what two reclaimers do to each other once the multiplicity exists, which is block 7's own subject. The input states this dependency in ART-008's Recommendation. |
| ART-009 | **CFG-006** (`UPLOAD__ALLOWED_MIME_TYPES` is a documented production control no deployment supplies) | 02 | **Adjacency, not merge.** Phase 02's subject is the deployment's environment; ART-009's surviving subject is a property in the settings graph with no reader in `src/`. Same dead key, two surfaces. Cross-reference only; no identifier is renumbered. |

**Seam check on this input — findings filed outside its declared scope: none.** All nine `Zone`
fields are verbatim block titles from `.kilo/commands/audit/phases/06-audit-file-artifacts.md`
(block 1 ×2, block 2 ×1, block 3 ×1, block 4 ×2, block 5 ×1, block 6 ×1, block 7 ×1, block 8 ×0), so
the template's zone rule is satisfied for all nine. Each also sits inside the phase's own scope
paragraph, which was checked clause by clause for the two that come closest to another phase's
territory. ART-003 inventories the upload rate limiter and the size ceiling, which the scope
paragraph assigns to 05 as "the admission controls" — but block 2's own text requires the
inventory be classified by what each control *bounds*, and the input reads rather than exercises
those controls and says so. ART-004's record-and-file ordering is the class the scope paragraph
carves out to 05 "written by different processes"; inside ART-004 both effects are written by the
same worker, so the carve-out does not reach it. **No seam violation is recorded, and the one
finding that duplicates a sibling (ART-006) duplicates content, not scope.**

### D. Recommendation executability

All nine recommendations were checked for a resolvable target and for what each disturbs. All nine
targets resolve. Five are substantiated but unusable as written (VAL-06-008); the four that are
executable are listed with their dependencies and their disturbance.

| finding | target resolves | depends on | breaks / disturbs | verdict |
|---|---|---|---|---|
| ART-001 | `validate_mime_type`, `process_upload_with_session`, `CSVLoader.load_csv`, `app.py:queue_worker` | the `BaseException` guard is independent of the extension rule and can land first | `tests/test_data_service.py:637-659` must be re-pointed at a comma-containing body (named); consistent uploads are byte-identical in behaviour | executable once the `:211-215` citation is dropped (VAL-06-004) |
| ART-002 | `ProcessingLog` + `file_processing.find_task_file` + `file_cleanup.cleanup_task_files` | ART-004's retention decision, which the roadmap already gates on | one nullable column is an Alembic revision; the other branch deletes two functions and `tests/test_upload_api.py:731`'s subject | **not executable — two mutually exclusive directions** (VAL-06-008) |
| ART-003 | `upload.py` before-accept check, `LOGGING__LOG_FILE`, the periodic task, `Dockerfile:95`/`:117`/`:143` | a production disk budget, which the input says must be known first | a new directory-size stat per upload; dropping the `uploads` dirs changes three image layers | **not executable — three bundled actions, no order** (VAL-06-008) |
| ART-004 | `data_worker.py:532-534` and `:593-602` | the retention decision | the area's occupancy grows after the fix; bounded only by ART-003's ceiling, which is step 5 | **not executable — two branches of one decision** (VAL-06-008) |
| ART-005 | one `cleanup_error` column + `GET /upload/status/{task_id}` + the periodic task | ART-002's record shape (step 3) — the input gates this correctly | `tests/test_file_cleanup.py` and `tests/test_upload_api.py:731` follow whichever way `cleanup_task_files` goes | executable; target and dependencies correct |
| ART-006 | `TempPasswordStore.store`/`.retrieve`, `admin.py:321`/`:330`/`:417-422` | phase 04's AUTH-002/AUTH-006 own both halves | **not executable as written** — two of the three tests it breaks are unnamed (VAL-06-002) | merged; the residue is phase 06's |
| ART-007 | `app.py:308-313` + `:340-344` + a new `FRONTEND__DIST_DIR` | nothing | a stricter `HEALTHCHECK` can turn a passing container unhealthy — the input says this and is right | **not executable — three actions plus an optional fourth** (VAL-06-008) |
| ART-008 | `file_cleanup.py:100-101` | none | none; additive | executable and complete |
| ART-009 | `config.allowed_mime_types` / `MimeTypeEnum` / the `except ImportError` branch | ART-001's extension rule reads the same detector | the semicolon-CSV admission verdict changes on libmagic-bearing hosts; two branches must not both survive silently | **not executable — delete or invert, plus choose one detector** (VAL-06-008) |

### E. The vacuous-control angle, applied to this input's own evidence

Three controls the input leans on were put through the three questions — does it exist, what scope
does it declare, what did it actually examine. A control that ran and reported clean substantiates
nothing; a control that did not run and is reported as having run substantiates less.

- **The eight-block runtime coverage claim** (the Summary). Exists; declares a scope of all eight
  blocks; examined five and a half. Five findings rest on executed probes — ART-001 (loader
  four-case, consumer-death), ART-002 (a live status read), ART-004 (a live end-to-end run), ART-007
  (three ASGI presence states), ART-008 (four concurrent sweeps) — and all five were re-derived
  here independently. ART-003, ART-006 and block 8 rest on reading and grep, and the Summary says
  otherwise (VAL-06-003).
- **The four-sweeper transcript** (ART-008's Evidence and Appendix C). Exists; declares its scope
  as "one operation whose second remover produced an outcome nothing records"; examined exactly that,
  and the effect is real. **Not vacuous and not an artefact** — re-run three times here with the
  same three deletions and a different spurious-error count each run. The only defect is that the
  count is presented as a constant when it is an interleaving outcome (recorded in Appendix A).
- **The anchor re-verification** (Appendix A). Exists; declares its scope as the two concurrently
  edited source files; examined those two and decided correctly on `db/starter.py` and incorrectly on
  the tree question for `config.py` (VAL-06-009). Not vacuous — it examined items and got half of
  them wrong, which is the opposite failure from a green control over zero items.
- **Block 8's returning-surface inventory**, filed as no finding. Exists, declares the sweep terms,
  and the sweep was re-run here: the only `FileResponse` in `src/` is the bundle fallback at
  `app.py:381`, and there is no `StreamingResponse`, `Content-Disposition` or `download` anywhere.
  A control green over a real examination, not over zero items — filing nothing was the correct
  outcome and Appendix D argues it.

No binding of the vacuous-control angle was found in this input's own words, and this phase binds
neither shared angle by name — recorded here because the 99 rubric asks which phases bind each
angle. The other five reports in the directory were surveyed for the same binding and none binds
either angle either; the angles remain defined here and unbound in practice, which is recorded as
a set-level observation in Appendix G rather than as a finding against this input.

### F. What the input rests on, and what it does not

Every substantive finding in this input arrives from an angle its eight declared blocks name —
there is no finding from an unnamed angle among the nine, which is worth recording as the phase
behaving as declared. The support splits three ways. **Five rest on an executed probe or an
end-to-end run** (ART-001, ART-002, ART-004, ART-007, ART-008), and all five were re-derived here
from the executing path; three of the five reproduced exactly, one reproduced with a narrowed
trigger (VAL-06-004), and one reproduced with a variable count (ART-008). **Three rest on static
reading or a repository grep** (ART-003, ART-005, ART-006), which phase 06's own command file
admits as an evidence class — "a static proof that a stated property does not hold" — so this is
not a defect in itself, but ART-006 is the one whose support turned out to be a duplicate
(VAL-06-002). **One is a live read of the deployed configuration** (ART-009's effective
allowed-MIME set), and that read is what refuted the finding's central claim (VAL-06-005).

No finding rests on the input's own declared block list or on its own Summary as support, and no
finding was accepted here on the strength of a passing check. Against the 99 rubric's question —
does the report contain at least one angle the declared blocks never name — it does, twice, and
both are recorded: the **phase-level absence claim** in the Summary ("no CRITICAL band is claimed,
because …"), which is an angle about what the phase as a whole does *not* contain rather than an
angle about any block's subject, and which is where the mis-grade lives (VAL-06-001); and the
**baseline and drift reconciliation** in Appendix A, which is a discipline about the audit's own
artefact rather than about stored artefacts, and which is the one piece of the report the declared
blocks never authorised (VAL-06-009). Both are legitimate additions; the first is wrong.

### G. Coverage ledger

| block | items examined | claims left unsettled | reason |
|---|---|---|---|
| 1. The claim re-derived from the executing path | 9 of 9 | 0 | every anchor resolved mechanically (§B): of 70 line references the input cites, 64 resolve and name the symbol claimed, 4 resolve but name something else (`loader.py:211-215`, `configuration.md:174`, `Dockerfile:81`, `main.py:10-25`), and 3 rows covering 6 references resolve only in the dirty tree |
| 2. The vacuous-control angle and its bindings | 4 controls | 0 | the eight-block coverage claim overstates runtime reach (VAL-06-003); the other three controls examined real items |
| 3. The grade against the audited rubric | 9 bands carried, 1 corrected | 0 | ART-004 re-graded HIGH → CRITICAL; the other eight map to a phase-06 rubric clause, six of them almost verbatim |
| 4. Which side moves: code or documentation | 3 documentation-contradicting citations | 0 | `configuration.md:174` contradicts the finding rather than the code (VAL-06-005); `AGENTS.md` §5 step 2's "platformdirs" is contradicted by the code, correctly excluded in Appendix E and phase 02 owns the `temp_dir` value |
| 5. Whether the recommendation can be carried out | 9 of 9 | 0 | all nine targets resolve; five name no direction (VAL-06-008); one names two of the three tests it breaks (VAL-06-002) |
| 6. Cross-phase conflict, ownership and merge | 7 contested/adjacent claims | 0 | 2 merges (AUTH-002, AUTH-006 → ART-006), 2 adjacencies to phase 05 (DP-001, TOPO-001/TOPO-005), 1 adjacency to phase 02 (CFG-006), 1 residue retained by phase 06, 0 seam violations (§C) |
| 7. Finding-ID namespace integrity | 1 audited prefix (`ART-`), 1 validation prefix (`VAL-06-`) | 0 | the flat `VAL-` prefix is occupied twice over — `VAL-001` resolves to two findings (VAL-06-010); zero in-source markers exist for any prefix in the set |
| 8. The shared findings template as a controlled artefact | 6 front-matter fields, 5 per-finding fields, the zone rule, the empty-state string | 1 | the empty state does not apply (9 findings); every per-finding field is present in all nine and every zone is a verbatim block title; the `baseline:` field names a tree the anchors were not read from (VAL-06-009) |
| 9. Does the input rest on its own declared blocks | 9 findings | 0 | five probed findings re-derived independently, three rest on static proof, one on a live configuration read; two angles the declared blocks never name, one of them wrong (VAL-06-001) |
| 10. The validated report as an artefact | 9 dispositions, 10 validation findings | 0 | the tally agrees with the per-finding verdicts: 6 confirmed + 1 re-graded + 1 merged + 1 re-typed = 9, 0 rejected, 0 unsettled; identifiers preserved; `ART-` and `VAL-06-` never share a table |
| 11. The shared angles, defined once and bound by name | 2 angles across 6 reports | 0 | neither the vacuous-control angle nor the cross-resource side-effect angle is bound in its own words by any report in the directory, and no report cites an angle that is not defined — an observation about the set, not a defect in this input |

**Not settled in this environment, and why.** Four items are recorded as limits rather than
confirmed. (1) **The consumer-death reproduction ran on the host, not in the container.** The
mechanism, the MRO, the handler chain and the queue outcome are platform-independent and were
reproduced; the four-process multiplicity in ART-001 and ART-008 is still derived from
`Dockerfile:179` rather than observed, exactly as the input's own Appendix F states, and the
production stack was not started. (2) **The four-sweeper probe ran against a throwaway directory on
the host**, so the errors surface as `FileNotFoundError`/`WinError 2` rather than the container's
`errno 2`; the class, the handler and the counting are identical, and the observed spurious-error
count was 7–8 where the input recorded 5 — the count is an interleaving outcome, not a constant.
(3) **No live end-to-end HTTP upload was driven.** The 201-under-a-false-gzip-claim half of
ART-001's Evidence is the input's own observation and was not re-run here, because the dev stack is
under other agents' control and this validation may not start, stop or reconfigure it; the
admission path behind it was re-derived statically instead (`file_processing.py:85-94` reads
`MimeTypeEnum.allowed_values()`, which contains both `text/csv` and `application/gzip`, and nothing
compares that verdict to the filename-derived extension at `:208-212`). (4) **`libmagic` raises
`ImportError` on this host**, so only the fallback branch of the MIME detector could be executed;
the libmagic branch's verdict is the input's own container observation and was not re-derived here,
which is why the refutation in VAL-06-005 rests on the *settings graph* (readable and executed) and
not on the libmagic verdict. One divergence is recorded as this run's own methodology limit rather
than as a defect: in the `correct` presence state, `GET /api/v1/nope` returned **200 `text/html`**
on the host rather than the input's 404 JSON, because Starlette's `StaticFiles` hands
`SPAStaticFiles.get_response` a path built with `os.path.join`, which is backslash-separated on
Windows, so `API_PREFIXES = {"api/"}` never matches. On Linux — the shipped runtime, and where the
input drove its probe — the guard matches and the 404 is correct. ART-007's finding is unaffected;
it rests on the absent-versus-present-but-wrong divergence, which reproduced identically.

**Hygiene.** Every probe ran in-process against the project's own classes, in a throwaway directory
under `%TEMP%\kilo\`, and the three directories that run created were removed afterwards (verified
absent). No row was written to any database, no Redis key was created, no upload was performed, no
container was started, stopped or reconfigured, and the dev stack was not touched. The dev stack and
the `mkobi-test` stack were observed read-only (`docker ps`); the `mkobi-app-1`,
`mkobi-rq-worker-1` and `mkobi-test-test-app-run-*` containers seen at the start are other agents' or
the platform's and were left alone, and the other agents' probe artefacts in the dev volume were
neither read into a finding nor removed. The untracked `.ai/` audit directories were read only. The
two files the concurrent remediation team had dirty — `src/mkobi/config.py` and
`src/mkobi/db/starter.py` — were read and diffed, never written; that team committed them as
`5a2cfb6` during this run, and the `baseline-dirty` front matter above records the movement and the
anchor re-verification that followed it. `git rev-parse HEAD` returned
`c3c0a61bf41cad68bf3a3ac105de91ea63c82268` before the first read and
`5a2cfb608ec117e6669c77eac04ae7e43f8e676f` after the last probe, the only change being that one
commit, and `git diff 5a2cfb6 -- src/` is empty. The only file this run wrote is this report.











