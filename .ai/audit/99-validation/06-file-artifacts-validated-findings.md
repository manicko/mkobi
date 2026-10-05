---
phase: 06-file-artifacts
executed: 2026-10-05
executor: validator
problems-only: true
findings: 8
by-severity:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 4
  LOW: 4
---

# Phase 06 — Validated Findings (Stored File Artefacts)

> **Path note, recorded so a later run does not correct it.** This phase's file stem is
> `{NN}-{phase-name}-validated-findings.md` while its output directory is `99-validation/`. The
> divergence is deliberate and declared by `.kilo/commands/audit/phases/99-audit-validate.md`
> (Report Output, first bullet). Audited namespace `ART-` is preserved; validation-level findings
> minted here are `VAL-06-011 … VAL-06-016` and occupy their own section, never the findings table.

## Summary

All eight findings were re-derived from the executing path, not from the report's quotes, and every
citation was re-opened at its quoted lines. **No citation in this input had drifted**: the two
commits made since the auditor's `HEAD f8581e0` (`git diff --name-only f8581e0 HEAD` →
`0ae6ddf`, `cfab3e0`) touch only `frontend/src/features/dashboards/ui/charts/**` and
`.ai/plans/16-phase16-residual-execution.md`, so no backend, documentation, compose or Dockerfile
anchor moved. That is the opposite of phase 01's and phase 02's experience and is recorded as such
rather than assumed. Verdicts: **2 CONFIRMED · 6 CORRECTED · 0 REJECTED**, with one half-finding
merged into the already-validated `CFG-107` and one recommendation (ART-106's) recorded as
substantiated but not executable. One band moves: **ART-103 MEDIUM → LOW**. Final counts:
**CRITICAL 0 · HIGH 0 · MEDIUM 4 · LOW 4**.

Three runtime claims were reproduced independently in the `mkobi-test` `test-app` container rather
than accepted, and all three reproduced **exactly**: the libmagic trailing-newline refusal
(`category,value\nA,10\nB,20` → `text/plain`; the same buffer plus one `\n` → `text/csv`); the
sweep's glob visibility (`created=8 matched=4`, `CleanupResult(deleted=4, already_gone=0,
failed=0)`, four files surviving `max_age_hours=0`); and the 255-byte per-name limit
(`len 255 OK` / `len 256 OSError [Errno 36]`).

**The most consequential result inside the findings is the severity premise, not any mechanism.**
Two
MEDIUM bands are argued from "no crash or upload error in 40 hours of `mkobi-app-1` logs". That
scan reproduces at **37 hours** and returns zero — but the window contains **zero uploads at all**
(`File upload started` 0, `File streamed to disk` 0, `Task enqueued` 0, `Temp file deleted` 0,
against 4,726 INFO lines). The success-path unlink that ART-104 is about was therefore never
executed once in the window being offered as evidence about it. A control green over zero items
substantiates nothing; the bands survive on other grounds, which are stated per finding, and the
premise is filed as `VAL-06-011`.

Six validation-level items are filed in their own section, and a seventh matter is recorded as a
**cross-phase escalation rather than filed**: two defects in this input (`VAL-06-011` the vacuous
severity premise, `VAL-06-012` a refuted coverage claim and a recommendation aimed at the wrong
module, `VAL-06-013` an undisclosed namespace collision on `VAL-06-001 … VAL-06-010` from this same
phase's own history), two missed system findings inside this phase's declared scope (`VAL-06-014` the
runbook still describes the file sweep as a startup cleanup; `VAL-06-015` the route's `finally` unlink
has no guard and masks the exception in flight), and one evidence-quality item (`VAL-06-016`); the
escalation is a production-tier failure of the upload endpoint itself that phase 07 owns, so it is
recorded with evidence and deliberately not filed under this phase. **Of everything in this report,
that escalation is the one with the largest expected consequence** — on the evidence gathered it
breaks the product's primary operation on the production tier for every body above ~1 MiB — and it is
also the one with the least evidence behind its headline, because its last mile needs a container this
permission set cannot open. Both statements are meant to be read together.

**Verdict vocabulary.** The instruction for this pass requires `CONFIRMED / CORRECTED / REJECTED`;
`.kilo/commands/audit/phases/99-audit-validate.md` fixes the vocabulary at
`confirmed / re-graded / merged / not substantiated / unsettled`. Mapping used per finding:
**CONFIRMED** = confirmed · **CORRECTED** = confirmed with the evidence, the impact statement or
the band re-derived (re-graded where the band moved) · **REJECTED** = not substantiated as filed.
A `merged` disposition is recorded inside the finding that carries it.

---

## Findings

Findings appear in descending final severity. Each carries the verdict, the zone quoted verbatim
from `.kilo/commands/audit/phases/06-audit-file-artifacts.md`, and the location inside the
observation field.

### ART-104 — An I/O error at the success-path unlink writes `FAILED` over a `COMPLETED` row the commit already made durable

**Severity** — MEDIUM (audited band sustained on a re-derived basis; the filed basis is rejected)

**Zone** — "Removal of an artefact, and the record of a removal that failed"

**Observation** — CORRECTED. The mechanism is fully confirmed and every quoted line is byte-exact
at the line cited. `src/mkobi/workers/data_worker.py:1035-1037` is an unlink with no guard, it sits
inside the `try:` that opens at `:997`, and that `try`'s handler at `:1039` is
`except BaseException`. The `async with session.begin():` block ends at `:1027`, so by `:1035` the
aggregate write and the `COMPLETED` transition are committed. The handler's `_update_processing_log_status`
call at `:1070-1077` opens its **own** session and commits (`:429-431`), so the `FAILED` row
survives independently of the transaction that committed `COMPLETED`. The transition is genuinely
illegal per the enum: `ProcessingStatus.valid_transitions()` returns `cls.COMPLETED: set()`
(`src/mkobi/models/enums.py:78`, docstring `:71-72`), and
`src/mkobi/services/processing_log_service.py:36-44` raises
`AppException(ErrorCode.INVALID_TRANSITION)` for `COMPLETED → FAILED` on every route that goes
through `_validate_transition`. The worker's helper does not consult it:
`src/mkobi/workers/data_worker.py:418-422` is a bare `update(ProcessingLog).where(id == …).values(…)`.

**Evidence** — Re-derived line by line; the finding's quoted excerpts are verbatim.

- `data_worker.py:1035-1038` — `if file_path.exists():` / `await asyncio.to_thread(file_path.unlink)`
  / `logger.info("Temp file deleted: %s", file_path)` / `return result`. No `try`.
- `data_worker.py:1039` — `except BaseException as e:`; `:1046-1048` classify and log;
  `:1056-1064` re-attempt the unlink behind its own `try/except BaseException` → WARNING;
  `:1070-1077` write `ProcessingStatus.FAILED`; `:1085` re-raises.
- The filed claim that the file "is already gone, so `exists()` is `False`" and the reclaim at
  `:1056` is skipped is true **only for a `FileNotFoundError`**. For every other `OSError` the file is
  still present — that is what the exception meant — so `:1035`'s `exists()` returned `True`, the
  unlink raised, and the handler's own guarded retry at `:1056-1064` **does** run; if it fails too,
  all that survives is a WARNING at `:1060-1063` and the flow proceeds to the `FAILED` write. So for
  the general case the mechanism that actually runs is *two* failed unlinks followed by a status
  overwrite, not one unlink followed by a silent overwrite. The correction does not weaken the
  finding — the `FAILED` write at `:1071` happens either way — but the filed description is not the
  one that executes.
- No self-healing exists downstream: `src/mkobi/core/task_queue.py:72` enqueues with
  `queue.enqueue(func, …)` and no `Retry`, so the re-raise at `:1085` fails the job outright; the
  reconciler only ever touches rows at `UPLOADED` / `PROCESSING`
  (`cleanup_stale_processing_logs`, `data_worker.py:481-492`), never a `FAILED` one.
- The trigger is reachable but not routine. Under the shipped default
  `stale_file_threshold_hours: int = Field(default=24, …)` (`src/mkobi/config.py:735`) the sweep
  race needs a job still running 24 h after its upload, which no shipped configuration produces
  (`data_worker.py:1440-1442` reconciles on a 300 s tick with a 30-minute row horizon); a
  non-`ENOENT` `OSError` from the volume (`EROFS`, `EIO`) is the realistic trigger, and the `app`
  service runs with a read-only root and `app_data` as its only writable mount
  (`docker/docker-compose.yml:189-193`).

**Correction — the "only one of nine" claim is false.** The observation says the success-path unlink
is "the only unlink in the function with no exception guard" (true for that function's production
branch) and the summary says "the only one of nine removal sites with no exception guard" (false).
Two of the nine are unguarded: `data_worker.py:941` (test path) and `data_worker.py:1036`
(production). The report's own Appendix D row 4 says so, so the finding contradicts its own
appendix. `missing_ok=True` at `upload.py:217` and `upload.py:265` and the `try` arms at
`file_cleanup.py:108-122` do guard their sites — but `missing_ok` suppresses `ENOENT` only, which
is the seam `VAL-06-015` is about.

**Correction — the consequence overstates what the caller sees.** "the dashboard renders the older
committed data as if the upload had failed" is not what is true. The aggregates were **replaced and
committed** before the overwrite, so the dashboard's data is the new, correct data; a refetch shows
it. What is wrong is the record and the two surfaces built on it: `GET /upload/status/{task_id}`
returns `status: failed`, and `src/mkobi/services/data_service.py:504-509` returns
`ProcessingResult(success=False, …, message="Processing not complete. Status: …")` for a run
whose aggregates are current. The client is told the upload failed when it succeeded, with no field
anywhere that distinguishes the two, and the remedy is a re-upload — the aggregates are not lost and
the artefact is not needed to reproduce them.

**Severity hook.** MEDIUM, re-derived rather than inherited. Phase 06's HIGH band is "a silent
correctness failure with no self-healing path", and each of its four enumerated items was checked
and none fits: the row does not name a missing artefact (the `processing_logs` row names none at
all), the removal was not "reported as performed and left in place", no two components disagree
about a name in one area, and no artefact's absence is reported as a pending state. What remains is
one wrong column value in one row, with the data itself correct and an ERROR-level log line with a
traceback at `:1048` as the operator's evidence — the opposite of silent. The MEDIUM band
("a bounded resource or operability gap") fits. **The filed justification is rejected**: "no such
error occurred in 40 hours of the running dev stack's logs" cannot support the band, because that
window contains no upload at all (`VAL-06-011`).

**Recommendation** — Executable as filed, and the reasoning about not touching
`_update_processing_log_status` is correct and load-bearing: a `COMPLETED → FAILED` refusal there
would leave a committed-`COMPLETED` run whose job the broker believes failed. The target
(`data_worker.py:1035-1037`) exists and is stable, the shape to copy is already in the same
function at `:1056-1064`. Two amendments: (a) close `VAL-06-015` in the same pass — the route's
`finally` unlink at `upload.py:263-265` has the same missing guard and a worse consequence, and
guarding one while leaving the other would leave the class half-open; (b) the new test the finding
asks for must also pin the *other* direction — that a raising unlink leaves the file for the sweep,
which is what `docs/03-processing/file-cleanup.md:64-70` already describes. No shipped test blocks
the change: nothing in `tests/test_file_cleanup.py` or `tests/test_data_worker.py` makes the
success-path `unlink` raise.

---

### ART-102 — The artefact area's only reclaimer cannot see four of the eight in-flight name shapes the upload route produces

**Severity** — MEDIUM (audited band sustained on a re-derived basis; the filed consequence is bounded)

**Zone** — "Residence of an accepted artefact, and what bounds it"

**Observation** — CORRECTED. The disagreement is real, the citations are byte-exact, and the
runtime reproduction is exact. `src/mkobi/api/routes/upload.py:199-205` builds the in-flight name as
`upload_{uuid4()}_{Path(file.filename or "unknown").name}` with **no extension imposed**, and the
only reclaimer selects with `upload_dir.glob("*.csv*")`
(`src/mkobi/services/file_cleanup.py:91-92`). For any client basename without `.csv` in it, the
producer's name and the reclaimer's rule cannot agree.

**Evidence** — Reproduced independently in `mkobi-test` `test-app`, with `UPLOAD__TEMP_DIR`
redirected to a throwaway path so no live volume was touched:

```text
=== B sweep glob visibility ===
  created=8 matched=4
    SEEN      'upload_…_report.csv'
    SEEN      'upload_…_report.csv.gz'
    INVISIBLE 'upload_…_report.txt'
    INVISIBLE 'upload_…_report'
    INVISIBLE 'upload_…_'
    INVISIBLE 'upload_…_unknown'
    SEEN      'upload_…_<uuid4>.csv'
    SEEN      'upload_…_<uuid4>.csv.gz'
  CleanupResult: CleanupResult(deleted=4, already_gone=0, failed=0)
  still present: ['…_report.txt', '…_report', '…_', '…_unknown']
```

Identical in shape and in every count to the report's block (UUIDs abbreviated here only), including
the four survivors at `max_age_hours=0`.
Supporting citations verified: `file_cleanup.py:101` is the guarded `unlink`;
`docs/03-processing/file-cleanup.md:98-102` contains the claim *"whose extension is still checked
against the allowed extensions at admission, so it still matches the sweep's `*.csv*` glob"*
verbatim, and `docs/03-processing/file-cleanup.md:233` is the accurate half (*"under a name the glob
does not match, is outside the sweep entirely"*) — so the page contradicts itself, as filed. The
file does exist before admission: `upload.py:210` opens it and the extension veto runs later at
`src/mkobi/services/file_processing.py:127-138`.

**Correction — the exposure is narrower than filed, in two ways that matter.**

1. **Only *rejected* uploads can strand an invisible file.** Admission enforces the extension veto
   (`file_processing.py:127-129`) *after* the body has been streamed, so any basename without
   `.csv`/`.csv.gz` is refused — `_handle_value_error` classifies it as `INVALID_FILE_TYPE`
   (`upload.py:98-106`). Every **accepted** artefact is stored as `{log_id}{ext}`
   (`file_processing.py:206`, `:242`) with `ext` from `MimeTypeEnum.extension`, which is `.csv` or
   `.csv.gz` only (`enums.py:138-149`) — so every accepted artefact, and every accepted file's
   stranded form, matches the glob. The residue the sweep cannot see is composed of **in-flight
   files for uploads that were never accepted**.
2. **"Unbounded, silent growth" is bounded.** A stranded file requires a hard kill (OOM-killed
   worker, `docker compose restart`, reboot) to bypass the route's `finally`
   (`upload.py:260-265`), and one kill strands at most the uploads in flight at that instant in the
   `app` process — not the whole history. The growth rate is therefore
   *(hard kills) × (concurrent in-flight uploads) × (≤ `max_file_size` each)*, and it still never
   shrinks, because no reclaimer can see those names. That is a real permanent leak with a small
   per-event cost, not unbounded growth. Both corrections bound the finding; neither refutes it.

**Correction — one prose error in the evidence.** The finding says the empty-name shape is "the
result of `Path(\"..\").name`". It is not: `Path("..").name == ".."` (verified on POSIX and on
CPython's `pathlib`), so `..` yields the *invisible* name `upload_{uuid}_..` — a single filename,
not a traversal component, and correctly not a directory escape. The empty component comes from
`Path(".").name` (`""`) and from an empty filename; the report's own probe table row
(`raw='..' → name='..'`) is right and its prose contradicts it.

**Severity hook.** MEDIUM. The phase rubric's HIGH band does enumerate "two components selecting by
name in the same area under rules that disagree", which is this finding's mechanism, so the band
was argued in both directions. It stays MEDIUM because the band is led by "a silent correctness
failure": nothing here produces a wrong result, the surviving files belong to uploads that correctly
failed, and the residue is bounded per kill event as derived above. The MEDIUM band's own first item
— "an area reclaimed by age but unbounded in count or in bytes" — is the accurate description of the
artefact area (the byte ceiling is a written deferral owned by phase 10 under C06-04,
`docs/03-processing/file-cleanup.md:262-272`). The filed justification ("no occurrence was observed
in 40 hours of running-dev-stack logs") is rejected for the reason in `VAL-06-011`.

**Recommendation** — Executable, and the producer-side fix is the right one: name the staging file
from the artefact's identity (`upload_{uuid4()}{ext}`) so the client's basename never becomes a path
component — that closes `ART-105` as well, which is the correct order. The report is also right that
`glob("*")` must not be the answer. One correction to the roadmap's dependency claim: step 1 is
*not* a prerequisite for step 3 (`ART-104`'s guard). `ART-104`'s trigger involves the **accepted**
artefact at `{log_id}.csv`, which the glob matches today and would still match after step 1; nothing
in `ART-104` depends on which in-flight names the sweep can see. The two can land in either order.
Correct `docs/03-processing/file-cleanup.md:99-100` in the same pass as the code, and keep the
`TOPO-111` warning: resolving this by moving admission onto `get_user_temp_dir` creates a second,
un-swept tree.

---

### ART-101 — Admission refuses a comma-delimited CSV the loader can read, when the file is small and its last line is unterminated

**Severity** — MEDIUM (audited band sustained; the trigger class is narrower than the title states)

**Zone** — "The accepted artefact's identity: what it is called, what its name claims, and what its
bytes are"

**Observation** — CORRECTED. The mechanism is real and reproduced; the *generalisation* in the
title and in one sentence of the observation is not. MIME admission is decided by libmagic reading
the first 2048 bytes (`src/mkobi/services/file_processing.py:42-45`) and refused when the verdict is
outside `MimeTypeEnum` (`file_processing.py:69-82`). For a comma CSV the classifier needs enough
evidence lines, and an unterminated final record removes one.

**Evidence** — Reproduced independently; the filed example reproduces to the byte:

```text
  category,value/A,10/B,20 (no trailing \n)   len=24  text/plain  polars:read_csv OK rows=2  REFUSED 415
  same + trailing \n                          len=25  text/csv    polars:read_csv OK rows=2  ADMITTED
```

and the boundary was mapped rather than assumed:

```text
  header + 0 rows, last \n cut   len=4    text/plain  REFUSED      header + 2 rows, trailing \n  len=12  text/csv  ADMITTED
  header + 1 row,  last \n cut   len=7    text/plain  REFUSED      header + 3 rows, trailing \n  len=16  text/csv  ADMITTED
  header + 2 rows, last \n cut   len=11   text/plain  REFUSED      500-row CSV, last byte cut  len=3783 text/csv ADMITTED
  header + 3 rows, last \n cut   len=15   text/csv    ADMITTED
```

`pl.read_csv` read **every** refused buffer without error and with the correct row count, which is
the finding's central claim ("a byte stream that `pl.read_csv` parses without difficulty is
refused"), now measured rather than asserted.

**Correction — the trigger class is small files, not unterminated files.** The title says "a
comma-delimited CSV whose last line has no trailing newline", and the observation says the classifier
"requires the final record to be complete". Both are too broad: a comma CSV of **header + 3 rows**
with the final newline cut is **admitted** (`len=15 → text/csv`), and a 500-row CSV with its last
byte cut is admitted, because only the first 2048 bytes are ever read. The rule that reproduces is
a *conjunction*: fewer than three data records with an unterminated last line, or fewer than two
data records with a terminated one, is refused. The filed consequence ("a dashboard whose data
legitimately arrives as a small aggregate CSV … is refused at the door") survives intact — the
`category,value / A,10 / B,20` case is exactly that — but the class is *small* files, and the fix's
blast radius is correspondingly smaller. `docs/03-processing/processing-api.md:60` is confirmed to
document only the semicolon casualty, and `:196` is confirmed to be the loader's reader boundary.

**Correction — the coverage claim is refuted, and with it part of the recommendation.** The finding
states "**No shipped test exercises a real libmagic verdict.** Every case in
`tests/test_mime_admission_contract.py` that touches admission replaces the detector". The scoped
clause is true — `:88-92` and `:199-216` monkeypatch the detector, and `:168-185` installs the
`_MagicSentinel` stand-in. The bolded claim is false: **seven shipped tests call the real detector on
real bytes with no monkeypatch**, and the finding never looked at them —
`tests/test_mime_validation.py:278-286` (`text/csv`), `:288-296` (`application/gzip`), `:298-309`
(`application/octet-stream`), `:311-321` (`text/plain`), `:332-342` and `:344-354`
(`validate_mime_type` end to end), and `tests/test_data_service.py:778-829`. It is worth noting what
those tests do and do not cover: every admitted buffer in them is terminated and has at least three
records (`test_mime_validation.py:283` writes `b"name,value\nfoo,1\nbar,2\n"`), so they all sit on
the safe side of the boundary — the *threshold* is unmeasured, but "no real verdict is ever
exercised" is wrong. Filed as `VAL-06-012`.

**Severity hook.** MEDIUM. No rubric band names "a valid upload is refused by a stricter gate", so
the grade is by effect: an upload that cannot succeed for any reason the client can see, on a real
input class, with no in-product hint — bounded, client-recoverable only by guessing (add a trailing
newline), no data loss and no exposure. That is the same class as `ART-105` and one step above the
LOW band's "documentation and observability drift with no runtime consequence today", which this is
not.

**Recommendation** — Executable in direction, wrong in target. The substantive proposal — move the
CSV-ness decision off the generic text classifier, either by admitting on
`(text/csv | gzip pair) ∧ pl.read_csv` or by letting the loader's reader boundary be the single
rejection point — stands, and the second branch is the smaller change. The instruction to add
real-detector cases to `tests/test_mime_admission_contract.py` should go to
**`tests/test_mime_validation.py`**, which is where the real-detector cases already live and where
this module's own docstring (`:1-10`) states the deliberate "host-independent, never rely on the
host's libmagic presence" rule. Add the boundary cases there (header + 0/1/2 rows unterminated,
header + 3 rows unterminated, terminated at 0/1/2 rows), so the threshold becomes a measured
dependency rather than an unrecorded one. `docs/03-processing/processing-api.md:60` still needs the
row-count / final-newline clause.

---

### ART-105 — A client filename over ~211 bytes answers 500 where a validation error is correct

**Severity** — MEDIUM (audited band sustained)

**Zone** — "Residence of an accepted artefact, and what bounds it"

**Observation** — CONFIRMED. Every citation is byte-exact and the mechanism reproduced on the first
attempt. `src/mkobi/api/routes/upload.py:205` concatenates `upload_` (7) + a 36-character `uuid4` +
`_` (1) = **44** bytes of fixed prefix with the caller's basename, with no length or character
validation anywhere between `:200` (`sanitized_filename = Path(filename).name`) and `:210`
(`async with aiofiles.open(temp_file_path, "wb")`). The blanket handler at `:278-283` converts the
resulting `OSError` into `AppException(ErrorCode.INTERNAL_ERROR)` → **500**.

**Evidence** — Reproduced independently against the same staging shape:

```text
=== ENAMETOOLONG threshold ===
  name len 200 OK      name len 255 OK
  name len 256 OSError: [Errno 36] File name too long
  name len 300 OSError: [Errno 36] File name too long
=== 300-character client basename ===
  raw='aaaa…' name='aaaa…' WRITE FAILED OSError: [Errno 36] File name too long
```

so the per-name limit is 255 bytes, the fixed prefix is 44, and **any client filename over 211 bytes
fails the request** — the derivation in the finding is correct, and 211 is a legal multipart
`filename` and a legal CSV name. The negative results on the other path-safety axes also reproduce
exactly, and they are the reason this is MEDIUM and not a security finding: `../../etc/passwd`,
`/etc/passwd`, `\\server\share\evil.csv`, `C:\Windows\…\evil.csv`, `..`, `.`, `""`, `NUL`, `CON`,
`PRN`, `COM1`, `CON.csv`, `trailing.csv.`, `  spaced.csv  `, `Ünïcødé.csv` and `emoji😀.csv` all
collapse to a single harmless component (created, never escaping the directory), and the un-sanitised
name is never used as a path anywhere else — it reaches `file_processing.py:127` only as
`filename.lower().endswith(...)`, confirmed at `:127-129`.

**One evidence note (does not affect the finding).** Two rows of the filed probe table are not what
their own header says. The row `raw='..\..\windows\system32\cmd.exe' → name='..\..\windows\system'`
is a **Windows-host** artefact of `pathlib`'s separator handling; on POSIX — the deployed tier, and
the tier the table's header claims — the value is the whole string
`'..\..\windows\system32\cmd.exe'` (reproduced). And the UNC / drive-letter rows are absent from the
table entirely. The conclusion — backslashes are not separators on the deployed platform, so the
value stays one component — is unaffected, and is now measured rather than assumed. Recorded as
`VAL-06-016`.

**Severity hook.** MEDIUM. No rubric band names it either; by effect it is a bounded operability
gap: a client-chosen, legal value is answered with a server-fault class, one ERROR log line with a
traceback per request (`upload.py:279`), and an error body with nothing actionable. The request is
recoverable by the client (a shorter name succeeds), nothing leaks — the file is never created, so
the `finally` at `:260-265` correctly finds nothing — and the rate is bounded by the per-user upload
rate limit at `:182-186` (100/hour). An automated 500-budget therefore pages on a rejected request.
That is operability, not correctness, and not a control that is disabled.

**Recommendation** — Executable as filed, three lines next to `upload.py:200`, and the ordering call
is right: drop the caller's basename from the staging name (ART-102's step 1) and this finding closes
with it. The one addition: the cap must be enforced on the **byte** length of the encoded component,
not the character count, since `Ünïcødé.csv` and `emoji😀.csv` are multi-byte in UTF-8 and the limit
the filesystem applies is bytes. `tests/test_upload_api.py` has no over-long-filename case; add one.

---

### ART-103 — `CleanupResult.failed` is computed, logged, and dropped before it reaches the only reader

*Title amended on reading: the **count** has no reader, but the **failure** has one — the ERROR log.
The mechanism is confirmed; the phrasing "the only reader" is the part this pass corrects, and the
correction is what moves the band. The input's wording is preserved in the observation so a reader can
match it against the report.*

**Severity** — LOW (re-graded from MEDIUM; the re-grade is recorded here, not applied silently)

**Zone** — "Removal of an artefact, and the record of a removal that failed"

**Observation** — CORRECTED, and re-graded. The mechanism is confirmed exactly as filed:
`cleanup_stale_temp_files` computes and returns three counts
(`src/mkobi/services/file_cleanup.py:131-135`, incremented at `:107`, `:112`, `:121`), and its only
production caller reads one of them — `src/mkobi/workers/data_worker.py:1562-1564` is
`files = cleanup_stale_temp_files()` / `if status is not None:` /
`status.record_success(count + orphaned + files.deleted)`. A repository-wide search confirms no other
production reader of `CleanupResult.failed` (the only `failed` assertions in the tree are
`tests/test_file_cleanup.py:73`, `:105`, `:135`, `:271`, `:289`, `:350`), and
`ReconcilerStatus` (`src/mkobi/core/reconciler_lease.py:75-98`) has no failure-recording method. The
published surface is `src/mkobi/app.py:479-486`, whose `"status": "ok" if last_success is not None
else "starting"` is independent of any count, so a tick in which every candidate failed to be
removed is reported as a healthy tick with `sweep_count` advancing.

**Evidence** — All four quoted ranges are byte-exact: `file_cleanup.py:116-122` (the `OSError` arm
and `failed_count += 1`), `data_worker.py:1562-1564`, `reconciler_lease.py:82-96` (the docstring that
calls the published integer "work items the tick disposed of"), `app.py:479-486`.

**Correction — "the only published signal" is false, and it is what moves the band.** The finding
says the health payload is "the only published signal of the sole reclaimer" and that an operator
"cannot distinguish 'there was nothing to remove' from 'nothing could be removed'". The primary
signal exists and is unfiltered: `file_cleanup.py:122` logs
`"Error removing stale temp file %s: %s"` at **ERROR with `exc_info=True`**, and `:126-129` adds
`"Stale temp file sweep finished with %d failure(s)"` at ERROR. The sweep runs in the **`app`**
process (`app.py:201-207` → `data_worker.py:1562`), which streams to stdout with handlers installed —
unlike the `rq-worker`, which phase 01 filed as `TOPO-102` — so those lines are in the app container's
log stream today. `docs/03-processing/file-cleanup.md:237-242` says exactly this and is accurate:
*"nothing queries it; only the log carries it"*.

The finding also omits the one piece of evidence that makes this a decision rather than an oversight:
the exclusion is **written down** as intentional, in the docstring of the very structure that
publishes it. `src/mkobi/core/reconciler_lease.py:88-92`: *"``last_swept_count``: … the file-sweep
term is ``files_deleted`` only; ``already_gone`` and ``failed`` are excluded."* So the defect is
precisely what the recommendation says it is — the count is deliberately kept out of the one field that
is published, and no field was added to carry it — and the correction is the one line the docstring
itself would need. What is missing is a **second** reader, and the `/health/detailed` payload is that
reader carrying a value from which the failures were removed.

**Severity hook — why this is LOW, not MEDIUM.** Phase 06's MEDIUM band item that fits this shape is
"a removal whose failure is recorded with no reader, no retention and no alert". That clause is
**not** satisfied: the failure is recorded *and* read (ERROR + traceback, plus the repeat attempt on
the next tick, which is why the residue is self-limiting for transient causes). What remains is a
health component that under-reports a count it already has — observability drift whose runtime
consequence today is nil: nothing consumes the payload (`/health/detailed` is admin-gated at
`app.py:397` via `Depends(require_admin_role)`, and the container healthcheck and the nginx edge both
gate on `/health`, `app.py:465-469`), and the file itself is retried on the next tick. The LOW band's
lead-in — "documentation and observability drift with no runtime consequence today" — describes it
precisely. The re-grade is recorded here because the coordinator may hold the opposite view; if the
coordinator sustains MEDIUM, the only argument it needs is that a health verdict is machine-read, and
that argument is not answered by this report.

**Recommendation** — Executable as filed and the best-shaped recommendation in the input: fold
`files.failed` into what the reconciler publishes, which needs no migration, keeps the two kinds of
item apart (`last_failed_count` beside `last_swept_count`) rather than summing a failure into a
"disposed of" count, and makes the existing `CleanupResult` field live.
`src/mkobi/core/reconciler_lease.py:86-92`'s docstring must be corrected with it. Verified
adjacency: phase 03's B3 touches `data_worker.py` but neither call site
(`data_worker.py:1562-1564`, `app.py:479-486`), and phase 14's `cleanup_error` column is only needed
for the *persisted* record, which this finding deliberately does not require. One correction to the
roadmap: because the band is LOW and the fix touches no migration, this is the cheapest item in the set
and should not be sequenced behind anything.

---

### ART-106 — The field named `filename` in the status response carries a prose sentence in every state

**Severity** — LOW (audited band sustained)

**Zone** — "The accepted artefact's identity: what it is called, what its name claims, and what its
bytes are"

**Observation** — CORRECTED (the observation holds; the evidence base and the recommendation do
not). `src/mkobi/services/data_service.py:467-480` builds
`ProcessingStatusResponse(…, filename=log.message or "unknown" …)` at `:472`, and the three writers of
that column on the pipeline path all write sentences, not names. All citations verified byte-exact:
`src/mkobi/services/file_processing.py:223` — `message=f"File uploaded successfully, awaiting
processing. mode={mode}"`; `src/mkobi/workers/data_worker.py:930` — `message="Processing started"`;
`data_worker.py:890-892` — `f"Processing completed successfully: {result_data['rows']} rows
processed"`. The contrast surface is real and verified: `data_service.py:189-196` returns
`UploadResponse(…, filename=filename or "unknown", …)` at `:191`, i.e. the caller's own basename under
the same field name.

**Evidence** — The declared type confirms the name is a name and nothing else
(`frontend/src/shared/types/api.types.ts:256-258`, re-verified in the working tree, which is dirty
for this file), and the consumption claim reproduces exactly: a search for `filename` across
`frontend/src` returns **two** hits, both type declarations — `:96` and `:258` — and nothing renders
it. The comment at `data_service.py:469-471` states the constraint accurately (under D-06-A = (b) no
durable filename exists, so the value is display-only), which is why the field name, not the value, is
the defect.

**Correction — three artefacts the finding did not engage with, one of which blocks its fix.**

1. **The contract is documented, not silent.** `docs/03-processing/processing-api.md:280-293` carries
   a subsection titled *"`filename` is display-only"*: *"display text, not a locator"*, *"Its value
   is filled from the processing log's `message` column"*, *"**No code may use this field to open,
   locate or re-process a file.** It names nothing on disk"*, and *"The field's **name and `str`
   type are unchanged** … That is the whole of its contract: wire compatibility."* The finding's
   consequence — "the field promises a locator the system explicitly does not provide" — is therefore
   contradicted by the documentation, which states the opposite in the field's own name. The report
   noticed and approved the equivalent code comment at `data_service.py:469-471` and missed the
   stronger artefact one page away in the same document family.
2. **The model's own field docstring states it too** —
   `src/mkobi/models/data.py:136-145`, verified present at `HEAD` (not a working-tree addition), not
   merely at the read time: *"`filename` carries a deliberate, narrow contract … This field is
   therefore **display-only** best-effort text … it names no artefact on disk and **no code may use it
   to open or locate a file**. It is kept, with its name and ``str`` type unchanged, purely for wire
   compatibility with existing clients"*. So the narrowest reading of "the field's contract is
   documented" is the one a developer hits first, on the class.
3. **A shipped test pins the field's name and type.**
   `tests/test_openapi.py:83-111`, `class TestProcessingStatusResponseWireShape`, asserts
   `ProcessingStatusResponse.model_fields["filename"]` is required and annotated `str`, and that the
   generated OpenAPI component exposes `filename` as a required string — with a docstring naming the
   reason: *"a rename, a type change, or an emitted `null` would be a breaking change for the
   frontend that consumes the payload"*, citing FAB-3 / ART-002. Under the template's own rule
   ("where a shipped test currently asserts the behaviour, name it as a remediation blocker"), this
   test is a blocker the report does not mention.

**Severity hook.** LOW, and the phase rubric has the slot almost verbatim: "an artefact's three
identities disagree with no downstream consequence today". No component reads the field, no artefact
is located with it, and nothing can be: the stored name `{log_id}{ext}` is not derivable from any
record, by design. The corrections above are what keep the band here rather than moving it: they
remove the "a client may reasonably read it as a locator" premise the consequence rested on and
replace it with a documented, tested, deliberate compatibility decision — a decision this pass does
not dispute, only refuses to relabel as an unnoticed defect.

**Recommendation** — **Nothing remains to do**, and that is the finding about the recommendation. The
rename and the field removal both break `tests/test_openapi.py:94-111` and both reverse a decision
that is documented in two places (`processing-api.md:280-293`, `models/data.py:136-145`), commented
(`data_service.py:469-471`) and tested under D-06-A = (b). The one action this pass originally
proposed — carrying the "display text, not a locator" note on the model field — is **already
implemented** at `models/data.py:136-145`, so there is no fallback action left. Whether an inaccurate
field name is worth reversing a deliberate, documented and tested compatibility decision is a
product-owner call, and it should be recorded as a decision question rather than as roadmap work. The
auditor's report should be amended to say so, because a remediation planner reading it today would
either break a test or duplicate existing documentation.

---

### ART-107 — The bundle resolver's docstring promises CWD-independence the code does not provide

**Severity** — LOW (audited band sustained for the docstring half; the alias half is MERGED into
`CFG-107`)

**Zone** — "The built interface bundle as a served artefact: what is served from disk, and what
changes when it is absent"

**Observation** — CORRECTED, and split in two. **Half one is confirmed.** `resolve_frontend_bundle`
resolves the configured directory with `Path(...).resolve()`
(`src/mkobi/app.py:520`), which makes the path absolute **relative to the process working
directory** — not independent of it — while its docstring at `:504-507` says *"resolved to an
absolute path, so the reported location is meaningful regardless of the process working directory"*.
Both halves of the contradiction are byte-exact: `src/mkobi/config.py:629-630` says *"Defaults to
the CWD-relative value that was hard-coded before, so the container's working directory and the
served bundle are unchanged"*, and `:631` is
`dist_dir: str = Field(default="frontend/dist", alias="dist_dir")`. No compose file sets
`FRONTEND__DIST_DIR` — a search across every `*.yml` in the repository returns zero hits — so the
shipped deployment satisfies the relative literal by working directory alone:
`docker/Dockerfile:82` (`WORKDIR /app`), `:229`
(`COPY --from=frontend-builder /app/frontend/dist ./frontend/dist`) and `:242`
(`CMD [… "--workers", "4"]`). The finding is also right that the drift risk is closed: the mount and
the health component both call this one predicate (`app.py:436` and `:538`), so they cannot disagree.

**Half two is merged.** The unread `frontend_dist_dir` alias (`config.py:1156-1159`, byte-exact) is
**already filed by phase 02 as `CFG-107` (MEDIUM)**, which names it in its inventory —
`.ai/audit/02-configuration-secrets/findings.md:425`:
`| Settings.frontend_dist_dir | :1159 (region) | 0 | none — app.py:520 reads
get_config().frontend.dist_dir |` — and which phase 02's validation **sustained on a corrected
inventory**: `.ai/audit/99-validation/02-configuration-secrets-validated-findings.md:312-321`
records five unread properties including `frontend_dist_dir` with a reader count of 0, re-derived by
introspection over `Settings.__dict__`. Same root cause, same file, same line, phase that owns the
concern, already validated. Re-filing it here would create a second namespace for one dead property.
Disposition: **merged into `CFG-107`**; the reader count of 0 is independently re-confirmed here
(the only occurrence in `src/` is the definition itself).

One correction to the merged half's supporting claim: "a repository-wide search for
`frontend_dist_dir` returns exactly one hit" is not true of the repository — phase 02's report, phase
02's validation report and this report all name it, and this report adds to that count as it is
written. It is true of the shipped tree (`src/`, `tests/`, `docker/`, `frontend/`, `docs/`,
`alembic/`), which is the claim that matters, and the reader count that carries the finding — zero
consumers in `src/` — is unaffected.

**Severity hook.** LOW for the docstring half: documentation drift with no runtime consequence today,
exactly as the LOW band states, and the LOW band's "a limit declared in more than one place with no
divergence yet" is the same shape. The alias half keeps `CFG-107`'s MEDIUM, which is a property of
that finding's inventory (nine unread aliases, one documented as a supported entry point), not of this
one-line accessor.

**Recommendation** — Executable for the docstring half, with no behaviour change: correct
`src/mkobi/app.py:504-507` to say the directory is resolved against the process working directory,
which is what `Path.resolve()` does and what `config.py:629-630` already says. The alias half's
recommendation ("route the predicate through the alias, or delete the alias") is **withdrawn as
duplicated** — the decision belongs to `CFG-107`'s single pass over the alias block, and routing one
consumer through one alias would split the block it is trying to close. `docs/11-guides/docker.md`
does not describe the app image's bundle location (its own drift is `ART-108`), and
`docs/03-processing/processing-api.md` claims no CWD-independence — both statements verified.

---

### ART-108 — The runbook still describes the production bundle carrier that was removed

**Severity** — LOW (audited band sustained)

**Zone** — "The built interface bundle as a served artefact: what is served from disk, and what
changes when it is absent"

**Observation** — CONFIRMED. `docs/11-guides/docker.md:453-459` is byte-exact as quoted and describes
a service that no longer exists: it lists `docker/nginx/nginx.conf` as a mounted read-only file and
`frontend/dist` as a mounted read-only directory, states that a **prior frontend build** is required
because "the dist directory is mounted, not built", and lists a `/var/log/nginx` tmpfs. The compose
file records the removal in the very service the paragraph describes
(`docker/docker-compose.yml:342-347`, byte-exact), and the bundle is baked at
`docker/Dockerfile:212` (`COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html`),
with `:213-214` failing the build when `index.html` is absent — the same way the app image does it
(`:229`). The service's real volume set is two files and no directory:
`docker-compose.yml:378-379` mounts `nginx.conf.template` and `entrypoint-render.sh`, both `:ro`, and
`nginx.conf` is *rendered at startup* (`:367-375`).

**Evidence** — Each of the four stale claims verified against the resolved service:

| runbook line | claim | resolved service |
| --- | --- | --- |
| `:453` | `docker/nginx/nginx.conf` mounted (ro) | `nginx.conf.template` mounted (ro) at `:378`; `nginx.conf` is generated by the entrypoint at `:375` |
| `:453` | `frontend/dist` mounted (ro) | no bundle mount; baked at `Dockerfile:212` |
| `:454` | requires a prior frontend build | build-time step inside the image |
| `:457-458` | tmpfs `/tmp`, `/var/cache/nginx`, `/var/run`, `/var/log/nginx` | `/tmp`, `/var/cache/nginx`, `/var/run` only (`docker-compose.yml:386-389`); `/var/log/nginx` is "intentionally absent" because both logs stream to stdout/stderr (`:383-384`) |

**Correction — "wrong on four of its seven lines" counts one line twice.** Lines `:456`
(`read_only: true`), `:459`'s `:ro` attribute claim and `:460` (the healthcheck claim) are all
**correct**; both mounted volumes do carry `:ro` (`:378-379`). Three of the seven lines are wrong
(`:453` twice, `:454`, `:457-458`), and `:459` is true but attaches to the wrong list above it. The
finding's operational conclusion is unaffected: an operator following this paragraph concludes that a
missing or stale host `frontend/dist` can break the edge and that a host `npm run build` is a
prerequisite, and both send them to a directory no service reads.

The secondary note is also confirmed: `docs/11-guides/docker.md:916` lists `uploads` at
`/app/data/uploads` as "Potential permanent file storage"; the directory is created by the Dockerfile
(`docker/Dockerfile:132`, `:154`, `:184`) and written by nothing. The finding is right to leave that
row to `TOPO-111`'s owner, because the per-user upload tree the row half-describes is that finding's
subject.

**Severity hook.** LOW: documentation drift with no runtime consequence today, which is the LOW
band's lead-in. The shipped configuration is the image copy, the build fails loudly on an empty
bundle, and nothing in the running system reads the runbook. The cost is operational — an operator
debugging a host directory — and `docs/00-overview/doc-maintenance-rules.md` is the rule the drift
violates.

**Recommendation** — Executable, and the ordering is right: rewrite
`docs/11-guides/docker.md:453-459` from the resolved compose file, in the same pass as `ART-107`'s
one-sentence docstring correction, since both are a documentation surface that outlived the change it
described. When doing it, fix the two lines this pass verified as *stale in the artefact area and not
yet claimed by any finding*: `docs/11-guides/docker.md:915` ("startup cleanup for stale files") and
`:927-928` ("Orphaned files (24h or older) cleaned **on startup** by `cleanup_stale_temp_files()`").
The sweep has not run at startup since it moved onto the lease-guarded reconciler tick
(`data_worker.py:1440-1442`, every 300 s), `docs/03-processing/file-cleanup.md:120-122` says so
explicitly, and a shipped test pins it — `tests/test_starter.py:836-843` asserts
`"cleanup_stale_temp_files" not in source` and that the starter module does not even import it. Filed
as `VAL-06-014`.

---

## Validation-Level Findings (`VAL-06-`)

Defects in the audit input itself, and system findings this pass missed inside the phase's declared
scope. They occupy their own section and never the findings table, because the two carry two
different severity scales. **Namespace: `VAL-06-011 …`** — `VAL-06-001 … VAL-06-010` are occupied by
this same phase's own history (see `VAL-06-013`).

### VAL-06-011 — The band argument for ART-102 and ART-104 rests on a 37-hour log window in which not one upload ran

**Severity** — MEDIUM · **Zone** — evidence quality / a control green over zero items

The input grades `ART-104` "MEDIUM, not HIGH, and deliberately so" on the ground that "**no such
error occurred in 40 hours of the running dev stack's logs** (Appendix E)", and uses the same
argument in `ART-102` ("No occurrence was observed in 40 hours of running-dev-stack logs"). The scan
reproduces — `docker logs mkobi-app-1` over `Killed|OOM|out of memory|File name too long|Errno 36|
Error during file upload|Temp file deleted` returns **0** hits — and it is a live log, not a silent
one: 4,726 INFO, 481 DEBUG, 18 WARNING and 16 ERROR records over the window, including the
reconciler's own `DEBUG` line *"No stale PROCESSING entries to mark (timeout=30m)"* every 300 s. The
figure is also wrong: `docker ps` reports `mkobi-app-1` **Up 37 hours**, not 40.

The scan is worthless for the two findings it is offered for, because the window contains no upload
at all: `File upload started` **0**, `File streamed to disk` **0**, `Task enqueued` **0**,
`Processing log updated` **0**, `Temp file deleted` **0**. The success-path unlink that `ART-104` is
about therefore executed **zero** times in the window offered as evidence about it; `ART-102`'s
orphaned in-flight file requires a hard kill, and none is visible either. Applying the
vacuous-control angle the validation phase defines: the control exists, its declared scope is
"40 hours of the dev stack", and the item count it actually examined is **zero** — so it decided
nothing and substantiates nothing. It is not evidence for MEDIUM *or* for HIGH.

Both bands survive on other grounds, and each finding records the ground that actually carries it:
`ART-104` on the rubric-hook argument (no HIGH clause fits; the aggregates are correct and an
ERROR-with-traceback line is the operator's evidence) and `ART-102` on the bounded-residue argument
(residue is rejected-upload staging files, bounded per kill event). The bands are therefore
sustained **without** this premise, and the premise should be struck from both findings and from
Appendix E rather than left to be quoted by a reader.

### VAL-06-012 — ART-101's "no shipped test exercises a real libmagic verdict" is refuted, and its test recommendation targets the module that deliberately has none

**Severity** — MEDIUM · **Zone** — evidence quality / an unusable remediation target

`ART-101` states in bold: "**No shipped test exercises a real libmagic verdict.**", supporting it
with three citations that are all true *of `tests/test_mime_admission_contract.py` alone*
(`:88-92` and `:199-216` monkeypatch `file_processing.detect_mime_type_from_content`; `:168-185`
installs the `_MagicSentinel` stand-in). The bolded claim is false of the suite. Seven shipped tests
call the real detector on real bytes with no monkeypatch, in two other modules the report's
repository-wide search list never mentions:
`tests/test_mime_validation.py:278-286` (`b"name,value\nfoo,1\nbar,2\n"` → `text/csv`),
`:288-296` (`application/gzip`), `:298-309` (`application/octet-stream`), `:311-321` (`text/plain`),
`:332-342` and `:344-354` (the real `validate_mime_type` end to end), and
`tests/test_data_service.py:778-829` (real detection through `validate_file`).

Two consequences. First, a claim of a coverage gap that does not exist is exactly the kind of
evidence a remediation planner acts on: it invites either skipping the measurement or duplicating
seven tests. Second, the recommendation's actionable half — "Either way the fix needs a test that
calls the **real** detector: add one case per buffer shape in the table above to
`tests/test_mime_admission_contract.py`" — names the wrong module. That module's docstring
(`:1-10`) states its purpose: *"These tests are host-independent: they never rely on the host's
libmagic presence"*. Putting real-libmagic cases there would break the module's stated contract;
they belong in `tests/test_mime_validation.py`, which already holds them.

What survives, and is worth keeping: the *threshold* is genuinely unmeasured. Every admitted buffer
in the real-detector tests is newline-terminated with at least three records, so all of them sit on
the safe side of the boundary this pass mapped (unterminated: refused at ≤ 2 data records, admitted
at 3; terminated: refused at ≤ 1, admitted at 2). The correction is to the claim and the target, not
to the finding.

### VAL-06-013 — The undisclosed namespace collision: `VAL-06-001 … VAL-06-010` are occupied by this same phase's own remediation record

**Severity** — MEDIUM · **Zone** — finding-ID namespace integrity

The input's Appendix F discloses one collision (`ART-001 … ART-009`) and it is verified — see
Appendix F of this report. It does not disclose the second one, on the very same evidence row.
`docs/SPEC.md:235` (change-log row 3.32) reads: *"audit findings `ART-001` … `ART-009`; **validation
defects `VAL-06-001` … `VAL-06-010`**"*, and every one of those ten identifiers is load-bearing in
`.ai/plans/_code-context/06-file-artifacts-reconciliation-note.md` (`:14`, `:39`, `:61`, `:70`,
`:91`, `:108`, `:139`, `:157`, `:165`, `:173`, `:187`) — they record the phase's re-grade of `ART-004`
to CRITICAL (`VAL-06-001`), the exposure narrowing (`VAL-06-004`), the dropped `ART-009` claim
(`VAL-06-005`), the contingent status of `ART-002` (`VAL-06-006`) and the corrected removal census
(`VAL-06-007`). They are provenance for shipped remediation work, not free identifiers.

A validator that minted `VAL-06-001` here would silently collide with a record the SPEC depends on,
and the collision would be invisible to any tooling that resolves findings by identifier — the
failure mode phase 01 already recorded for the split `TOPO-` namespace. The ruling applied by this
pass: **validation-level findings for this phase start at `VAL-06-011`**, and no `VAL-06-0xx`
identifier at or below 010 is reused. The input should have disclosed this alongside the `ART-`
collision; the omission is a disclosure defect in the report, not a defect in the tree.

### VAL-06-014 — Missed system finding: the runbook still describes the file sweep as a startup cleanup

**Severity** — LOW · **Zone** — "Which process reclaims an artefact, and what two of them doing it at
once produces" (block 7) and "Residence of an accepted artefact, and what bounds it" (block 2)

The input's block-7 coverage row says "no findings", and its block-2 row files two — but it examined
the **nginx** paragraph of `docs/11-guides/docker.md` (ART-108) and not the **upload-directory**
section of the same page, which is the phase's own artefact area and is wrong in the same class:

- `docs/11-guides/docker.md:915` — the `tmp_uploads` row's Lifecycle column ends
  *"Auto-cleanup on success or failure; **startup cleanup for stale files**"*.
- `docs/11-guides/docker.md:927-928` — step 4 of the same page's lifecycle list:
  *"Orphaned files (24h or older) cleaned **on startup** by `cleanup_stale_temp_files()`"*.

Both are false. The sweep has not run at startup since it moved onto the lease-guarded periodic
reconciler tick — `src/mkobi/workers/data_worker.py:1440-1442` (`interval_seconds: int = 300`) with
its own docstring at `:1458-1461` ("the temp-file sweep used to run only from
`DatabaseStarter.startup` … It now shares this loop"), `docs/03-processing/file-cleanup.md:120-122`
("The file sweep used to be called once from `db/starter.py` during startup. It no longer is"), and a
shipped test that pins it: `tests/test_starter.py:836-843` asserts `"cleanup_stale_temp_files" not in
source` **and** that the starter module does not import it. So the operator reading this page is told
a failed removal is retried only by a human restarting a process — which is the exact statement the
code change was made to falsify, and the same false claim phase 03 filed for the *row* sweep against
a different document (`TXN-109`, `architecture.md`). That is why this is a miss rather than a merge:
the subject is the **file** sweep, the document is different, and `TXN-109` does not cover it.

Consequence today: an operator debugging artefact residue restarts the application expecting the
sweep to run, when in fact it has been running every five minutes all along — and an operator
trusting the page cannot tell a reclaimer that is retrying from one that is not.

Recommendation: correct `:915` and `:927-928` to name the lease-guarded reconciler tick and its
300 s cadence, in the same documentation pass as `ART-108` and `VAL-06-016`. No code change, no
migration, nothing that reads the page at runtime.

### VAL-06-015 — Missed system finding: the route's `finally` unlink has no guard, so a failed cleanup masks the exception in flight

**Severity** — MEDIUM · **Zone** — "Removal of an artefact, and the record of a removal that failed"

`src/mkobi/api/routes/upload.py:260-265` is the eighth removal site in the input's own census and is
the only one whose failure changes the **HTTP answer**: the `finally` calls
`temp_file_path.unlink(missing_ok=True)` with no `try`. `missing_ok=True` suppresses `FileNotFoundError`
and nothing else, and an exception raised inside a `finally` block replaces the exception already in
flight. Verified in the `test-app` container by driving the route's exact shape with a failing
unlink:

```text
  MASKED -> OSError 30 EROFS
  __context__ = AppErr
```

So when the staging file cannot be removed, the correctly classified admission failure the request
was about to answer — `415 INVALID_FILE_TYPE`, `403 PERMISSION_DENIED`, `429 RATE_LIMIT_EXCEEDED`,
`413 FILE_TOO_LARGE` — is discarded and the blanket handler at `:278-283` answers
**`500 INTERNAL_ERROR`**, with `logger.error("Error during file upload", exc_info=True)` writing a
stack trace per request. The original exception survives only as `__context__`, which nothing reads.
The residue compounds `ART-102`: the file that failed to be removed is one the sweep may not be able
to see, so the same event both misreports the request and leaves the file behind.

Two precisions, both verified. `Path.exists()` cannot be the trigger: it swallows `OSError` **and**
`ValueError` (checked on a path with an embedded NUL — it returns `False`), so the `finally` reaches
the `unlink` and the `unlink` raises. And the realistic trigger class is narrow — POSIX `unlink`
needs write permission on the **parent directory**, not on the file, so a read-only file is still
removed (a chmod-based reproduction does not raise, confirmed); the reachable causes are an `EROFS`
volume remount, `EIO`, or a lost `app_data` mount. That is the same trigger class as `ART-104`, which
is why the two are graded the same and should be closed in the same pass.

Recommendation: wrap `:263-265` in `try/except OSError` logging at WARNING, exactly as
`data_worker.py:1056-1064` already does for the identical seam, so a failed tidy-up is a log line and
never an HTTP status. Add a route test that makes the unlink raise `OSError` and asserts the original
status code survives — there is none today. This is the second of the two sites `ART-104`'s
recommendation should cover; closing one and leaving the other leaves the class half-open.

### VAL-06-016 — Evidence quality: two rows of ART-105's probe table are not what their header claims

**Severity** — LOW · **Zone** — evidence quality

`ART-105`'s evidence block is headed `=== Path(filename).name on POSIX (the deployed tier) ===`, and
one row under it is not a POSIX result: `raw='..\..\windows\system32\cmd.exe'` is shown mapping to
`'..\..\windows\system'`, which is `pathlib`'s **Windows** separator handling (it splits on the
backslash and truncates at 20 characters). On POSIX — the deployed platform, and the tier the header
names — the same input maps to the whole string `'..\..\windows\system32\cmd.exe'`, reproduced. Two
further axes the header implies were probed (a UNC path `\\server\share\evil.csv` and a Windows drive
path `C:\Windows\System32\evil.csv`) do not appear in the table at all; both were run in this pass
and both collapse to a single harmless component.

The finding's conclusion is unaffected and is now measured rather than assumed — backslashes are not
separators on the deployed platform, so a Windows-shaped basename stays one path component and cannot
escape the staging directory. Recorded because a table whose rows do not match its own header is the
kind of evidence a reader stops checking, and because the phase's most security-adjacent claim (no
path traversal through the caller's basename) deserves evidence that is exactly what it says it is.

---

## Cross-Phase Escalation — recorded, not filed

**This is deliberately not a finding and deliberately not in the table above.** The defect below is
outside phase 06's declared scope: `.kilo/commands/audit/phases/06-audit-file-artifacts.md:11-19`
assigns "the inbound surface form and the transport-level body bound" to **phase 07**, and the input
declines it correctly and with the right reason (Appendix E, and this pass's Appendix E agrees). The
validate phase's own rule is that a finding filed under a phase that does not own it is a defect in the
report, so this pass will not commit that mistake in order to surface a defect of this size. It is
recorded for the coordinator and for phase 07, with the evidence, because dropping it would leave a
product-tier failure unowned.

**The mechanism, reproduced.** The multipart body is parsed in full before the endpoint runs, and
Starlette's parser holds a part's bytes in a `SpooledTemporaryFile` whose spill threshold is 1 MiB.
Instrumented in the `test-app` container (Starlette 1.3.1, python-multipart 0.0.32, running as uid
100 — not root, so permissions bind):

```text
  small 12 B   HTTP 200  rollovers=0  TemporaryFile_calls=0
  ~4 MB        HTTP 200  rollovers=1  TemporaryFile_calls=1
```

and with the temp directory pointed at a path that exists but is **not writable** — which is what a
read-only root filesystem presents for `/tmp`:

```text
  small 12 B (in memory)       -> HTTP 200 {"size":12}
  ~4 MB (spills to tempdir)    -> HTTP 500 Internal Server Error
```

**Why the production tier supplies exactly that condition.** The base compose file's `app` service
mounts `app_data` and sets `read_only: true` (`docker/docker-compose.yml:189-193`) and mounts **no
tmpfs** — a search for `tmpfs` in that file returns three hits, and none of them is in the `app`
service: `rq-worker` gets `/tmp:rw,size=128m` (`:303-305`) and `nginx` gets `/tmp` (`:386-389`). The
dev override relaxes the app service with `read_only: false`
(`docker/docker-compose.override.yml:195`), so the development tier cannot exhibit the failure — which
is exactly why nothing in the input's evidence or in `mkobi-app-1`'s 37-hour log window would show it.

**The two conditions, composed, mean this** (not verified end to end, and the last mile is the open
part): on the production tier, an upload whose body exceeds ~1 MiB — i.e. essentially every real BI
CSV, and far below the application's own 100 MB ceiling — cannot create its parser spill file in the
read-only `/tmp`, the parser raises before the endpoint is entered, and the request is answered by the
generic `Exception` handler (`src/mkobi/utils/exceptions.py:344-356`) with a bare **500**, outside every
`try` in the route and outside the streaming size check that `upload.py:211-230` performs.

**What is not established.** Reading a container's filesystem or its mounts needs `docker exec`, which
this permission set marks `ask`, and standing up the production compose profile is outside a
validation pass. So the two claims above are established — the spill threshold is measured, the
production service's mount set is read from the resolved compose file, and the failure mode against a
non-writable temp directory is reproduced — and the composition of the two is **inferred**, not
executed. One escape hatch was considered and does not survive: `tempfile` prefers `O_TMPFILE` on
Linux, but `O_TMPFILE` also requires write permission on the directory, so the overlay filesystem
question does not change the outcome.

**Routing.** Phase 07 owns the surface and should verify the composition against a `read_only: true`
container before filing; the band to expect is **HIGH**, and CRITICAL if confirmed against a live
production profile, because the operation the product exists to perform fails for every input above
1 MiB. The two candidate fixes are both one line — a `tmpfs` on the app service's `/tmp`, or an
explicit `TMPDIR` pointed into `app_data` — and either is better than re-ordering the parser. This
pass records the escalation and takes no other action: no code, compose or documentation file was
touched.

---

## Distribution

Five of the eight findings sit on the boundary between the upload path and the filesystem
(`src/mkobi/api/routes/upload.py` plus the staging-directory naming rules), and that boundary carries
the most: ART-102, ART-105 and, from this pass, `VAL-06-015`. Two sit on the removal path inside the
worker and on what the reconciler publishes (`data_worker.py`, `file_cleanup.py`) — ART-104 and
ART-103, which are the same defect seen from two sides. The remaining three are surface drift:
ART-101 on the admission verdict, ART-106 on a response field, and ART-107/ART-108 on the built
bundle's documentation.

- `src/mkobi/api/routes/upload.py` — ART-102 (staging name shape), ART-105 (name length), `VAL-06-015` (`finally` unlink)
- staging naming vs. the reclaimer's rule (`upload.py:205` vs `file_cleanup.py:92`) — ART-102
- `src/mkobi/workers/data_worker.py` — ART-104 (unguarded success unlink), ART-103 (discarded `failed`)
- `src/mkobi/services/file_processing.py` — ART-101 (the detector's verdict), ART-106 (via `data_service.py:467-480`)
- `src/mkobi/app.py`, `src/mkobi/config.py`, `docker/` vs `docs/11-guides/docker.md` — ART-107, ART-108, `VAL-06-014`
- `src/mkobi/config.py:1156-1159` — merged into the already-validated `CFG-107` (phase 02)

## Cross-Finding Analysis

Two causes, not eight independent defects — and this pass sharpens both.

**The caller's basename is used as a filesystem component where the system's own naming rule says it
should not be.** ART-102 (the name shape decides whether the reclaimer can see the file), ART-105
(the name's byte length decides whether the request 500s) and `VAL-06-015` (the cleanup of that same
file can overwrite the request's status) are three consequences of one decision at
`src/mkobi/api/routes/upload.py:205`. Naming the staging file from the artefact's identity
(`upload_{uuid4()}{ext}`, `ext` from the `FileExtensionEnum` the admission gate already enforces)
closes all three and removes a client-controlled string from every path in the staging area.

**A removal outcome is computed and then dropped before it reaches any reader.** ART-103
(`CleanupResult.failed` discarded at `data_worker.py:1564`) and ART-104 (the success unlink's failure
reported as a processing failure rather than as a removal failure) are the same defect from two
sides, and `VAL-06-015` is the third instance of the shape on the request path. The system has three
removal sites whose outcome is not reported as a removal outcome. ART-104 additionally violates
`ProcessingStatus.valid_transitions()` on a path where `processing_log_service.py:36` enforces it
everywhere else.

ART-101, ART-106 and ART-107/ART-108 are independent of each other and of both causes, with one
pairing: ART-107 and ART-108 are the built bundle's documentation surface lagging the change that
fixed it, and `VAL-06-014` is a third instance of the same class on the same page.

## Roadmap

Ordered by cause, not by severity, with this pass's amendments marked. The input's dependency
structure is mostly right; two edges are corrected.

1. **Close ART-102, ART-105 and `VAL-06-015` together — stop letting the caller's basename be a path
   component, and guard its cleanup.** Name the staging file from the artefact's identity at
   `src/mkobi/api/routes/upload.py:205` (`upload_{uuid4()}{ext}`), cap any residual caller-supplied
   component on its **byte** length if one remains, and wrap the `finally` unlink at `:263-265` in
   `try/except OSError` → WARNING. Correct `docs/03-processing/file-cleanup.md:99-100` in the same
   step. Must be true before step 3's test is written, because it changes which names the sweep can
   see. Do **not** resolve it by moving admission onto `get_user_temp_dir` — `TOPO-111` names that
   trap, and the finding is right to defer to it.
   *Amended:* `VAL-06-015` joins this step (same file, same defect class, same pass); ART-105's
   ordering preference is confirmed; ART-102's consequence is restated as bounded residue rather
   than unbounded growth.
2. **Close ART-103 — publish `failed`.** Add `last_failed_count` to `ReconcilerStatus`, publish it
   beside `last_swept_count` in `src/mkobi/app.py:479-486`, and correct
   `reconciler_lease.py:86-92`'s docstring. Needs no migration, blocks nothing, and is the cheapest
   item in the set. *Amended:* now banded LOW, so it no longer needs to be sequenced behind anything
   — it can land first.
3. **Close ART-104 — guard the success-path unlink.** Wrap `data_worker.py:1035-1037` in its own
   `try/except OSError` at WARNING; add a test that makes the success-path `unlink` raise once and
   asserts the row stays `COMPLETED` **and** the file survives for the sweep. Do not add a
   state-machine check to `_update_processing_log_status`. *Amended:* the input's dependency on step 1
   is **removed** — ART-104's trigger involves the accepted artefact at `{log_id}.csv`, which the
   glob matches today and would still match after step 1. The two steps are independent and either
   order works; the test in step 3 should simply be written last, against the final naming.
4. **Close ART-101 — move the CSV-ness decision off the generic text classifier,** and add the
   **boundary** cases (unterminated at 0/1/2/3 data records, terminated at 0/1/2) to
   `tests/test_mime_validation.py`. *Amended:* the target module changes —
   `tests/test_mime_admission_contract.py` is deliberately host-independent and must not receive
   them. `docs/03-processing/processing-api.md:60` gains the row-count / final-newline clause.
5. **Close ART-107 (docstring half only), ART-108 and `VAL-06-014` in one documentation pass** against
   the resolved compose file and the reconciler's actual cadence. No runtime behaviour changes.
   *Amended:* the alias half of ART-107 leaves this step entirely — it is `CFG-107`'s.
6. **Decide ART-106, do not schedule it.** The rename/drop is blocked by
   `tests/test_openapi.py:94-111` and reverses a decision documented in two places
   (`docs/03-processing/processing-api.md:280-293` and `src/mkobi/models/data.py:136-145`). Route it to
   the product owner as a decision question. *Amended:* the one unconditional action this pass
   originally proposed — a "display text, not a locator" note on the model field — is **already
   implemented** at `models/data.py:136-145`, so step 6 carries no work at all unless the owner
   reverses the ruling; there is no fallback action left to schedule.

`VAL-06-011`, `VAL-06-012`, `VAL-06-013` and `VAL-06-016` are edits to the audit report itself and
enter no remediation sequence.

## Rollout Safety

Step 1 changes staging file names and adds a guard on the request path's cleanup. Nothing outside the
staging directory selects a file by name: `cleanup_stale_temp_files` globs (it will simply see the
new names, which is the point), the worker receives its path as a job-payload string
(`file_processing.py:263-269`) and never reconstructs it, and the route's `finally` holds the same
`temp_file_path` object. No migration is needed and no artefact written before the change is affected,
because a file's *age*, not its name, decides the sweep. The one thing to verify afterwards is that
the new names still match `*.csv*` for every admitted MIME type — `MimeTypeEnum.extension` maps to
`.csv` or `.csv.gz` only, so this holds, but assert it in a test rather than by reading the enum.
**One correction to the input's revert advice:** it states that "in-flight files written under the old
names become invisible to the sweep, so on revert drain `app_data/tmp_uploads` manually". That is
backwards. The proposed name `upload_{uuid4()}{ext}` is `upload_<uuid>.csv` or `upload_<uuid>.csv.gz`,
and **both** match `*.csv*` before *and* after the change; it is the old scheme's four
non-`.csv`-suffixed shapes that are invisible, and those are exactly the ones step 1 removes. No drain
is required on revert. `VAL-06-015`'s guard is the one behavioural change on the request path that a client can
observe: requests that today answer `500` on a failed cleanup will answer their correct class. That is
the fix's purpose; it is also the only way this step can change a status code, so it is the one to
watch in the error budget.

Step 4 changes which uploads are admitted, which is externally observable: some uploads that today
return `415` will be accepted. That is the intended direction and it can only admit files the loader
can already read, but if any client has come to depend on the current refusal as a validation signal,
it will stop firing. Verify by replaying the buffer shapes in `ART-101`'s evidence table through the
running stack before deploying, and keep the refusal for genuinely malformed input — the loader's
reader boundary is where that belongs.

Steps 2, 3 and 5 change no externally observable behaviour beyond one added key in an **admin-gated**
health response (step 2; `/health/detailed` requires `require_admin_role`, `app.py:397`) and a
docstring. Step 3 does not touch `data_worker.py`'s transaction scope, so it does not collide with
phase 03's B3 — it edits only the unlink at `:1035-1037` and its surroundings, not the
`async with session.begin():` block B3 restructures; if B3 lands first, step 3 re-applies cleanly.
Nothing here depends on the unlink's position relative to the commit, only relative to the `try:`.
Step 6 is a decision, not a rollout.

---

## Appendices

### Appendix A — Disposition ledger and final severity counts

| ID | Filed band | Verdict | Final band | What moved |
| --- | --- | --- | --- | --- |
| ART-104 | MEDIUM | CORRECTED | **MEDIUM** | Band sustained on the rubric hook, not on the filed "40 h of clean logs" premise; "only one of nine unguarded" refuted; consequence corrected (the aggregates are correct, the status is wrong) |
| ART-102 | MEDIUM | CORRECTED | **MEDIUM** | Mechanism and runtime reproduction exact; consequence bounded (rejected-upload staging files only; ≤ in-flight-per-kill); `Path("..").name` prose error corrected |
| ART-101 | MEDIUM | CORRECTED | **MEDIUM** | Mechanism reproduced; trigger class narrowed to small buffers; coverage claim refuted (`VAL-06-012`); test target corrected to `tests/test_mime_validation.py` |
| ART-105 | MEDIUM | CONFIRMED | **MEDIUM** | Nothing in the mechanism moves; one evidence-table row is a host artefact (`VAL-06-016`) |
| ART-103 | MEDIUM | CORRECTED · **re-graded** | **LOW** | "The only published signal" refuted — the ERROR-with-traceback log is the primary one; no runtime consequence; the health payload is admin-gated and nothing consumes it |
| ART-106 | LOW | CORRECTED | **LOW** | Observation stands; the contract is documented twice (`processing-api.md:280-293`, `models/data.py:136-145`) and pinned by `tests/test_openapi.py:94-111`, so the recommendation is **not executable** and its fallback action is **already implemented** — nothing remains to schedule; it becomes a product-owner decision |
| ART-107 | LOW | CORRECTED · half merged | **LOW** (docstring half) | Docstring contradiction confirmed; the unread `frontend_dist_dir` alias is **merged into the validated `CFG-107`**; the alias recommendation is withdrawn as duplicated |
| ART-108 | LOW | CONFIRMED | **LOW** | All four stale claims verified; "wrong on four of its seven lines" corrected to three (`:459`'s `:ro` claim is true) |

**Final severity counts** — CRITICAL **0** · HIGH **0** · MEDIUM **4** · LOW **4** (8 audited findings,
0 rejected, 1 half merged away). Validation-level findings recorded separately: **6**, of which
CRITICAL 0 · HIGH 0 · MEDIUM 4 (`VAL-06-011`, `-012`, `-013`, `-015`) · LOW 2 (`VAL-06-014`, `-016`),
plus **1 escalation recorded and not filed** (the cross-phase section) whose band, if phase 07
confirms the composition against a `read_only: true` container, is HIGH.

Two of the four MEDIUM bands were argued in both directions against this rubric and are recorded as
sustained: `ART-102` (the HIGH band's "two components selecting by name … under rules that disagree"
clause fits the mechanism; it does not lift the band, because nothing produces a wrong result and the
residue is bounded per kill event) and `ART-104` (none of the four HIGH clauses fits; what remains is
one wrong column value in one row, with the data itself correct). One band moved down and the
mechanism survives intact, which is the distinction the validation phase's block 3 requires: the grade
is recorded, not silently applied.

### Appendix B — Citation re-verification

Every citation in the input was re-opened at its quoted lines. Method: read the file at the cited
range immediately before writing this entry, and compare the quoted text byte-for-byte.

| Citation | Result |
| --- | --- |
| `upload.py:199-205` (producer naming) | byte-exact, 7/7 lines |
| `upload.py:210` (`aiofiles.open`) · `:260-265` (`finally`) · `:278-283` (blanket handler) · `:217` (size-ceiling unlink) | byte-exact |
| `file_cleanup.py:91-92` (glob) · `:116-122` (`failed_count`) · `:47` (signature) | byte-exact |
| `data_worker.py:997` (`try:`) · `:1027` (commit edge) · `:1035-1038` (unguarded unlink) · `:1039` · `:1046-1048` · `:1056-1064` · `:1070-1077` · `:1085` | byte-exact |
| `data_worker.py:418-422` (unconditional UPDATE) · `:429-431` (own session + commit) · `:383` | byte-exact |
| `data_worker.py:1562-1564` (discarded `failed`) · `:1565` (tick `try`) · `:1440-1442` (300 s tick) | byte-exact |
| `data_worker.py:930` · `:890-892` · `:703-708` (the three `log.message` writers; the `CSVLoader`) | byte-exact |
| `enums.py:71-79` (`COMPLETED: set()`) · `:138-149` (`MimeTypeEnum.extension`) | byte-exact |
| `processing_log_service.py:36-44` (`_validate_transition`) | byte-exact |
| `file_processing.py:42-45` (detector) · `:69-82` (refusal) · `:127-129` (extension veto) · `:206` (stored ext) · `:223` · `:242-244` (move) · `:263-269` (enqueue) · `:272` | byte-exact |
| `data_service.py:181` · `:189-196` · `:467-480` · `:504-509` | byte-exact (see the drift note below: this file moved +109 lines mid-pass and every `data_service.py` anchor was re-resolved against the post-edit state) |
| `app.py:397` (admin gate) · `:436` · `:479-486` · `:501-522` (`:504-507`, `:520`) · `:538` | byte-exact |
| `config.py:629-631` · `:735` · `:1156-1159` · `:577-594` · `:1006` · `:1020-1023` | byte-exact |
| `reconciler_lease.py:75-98` · `:82-96` | byte-exact |
| `processing_logs.py:30-72` (seven columns: `id`, `dashboard_id`, `status`, `message`, `started_at`, `finished_at`, `error_code`) | byte-exact |
| `rq_worker_wrapper.py:192-238` (no reconciler in `rq-worker`) | range resolves; claim verified — `main()` is the healthcheck and `start_rq_worker` runs `worker.work()` |
| `file_utils.py:18` · `:29` · `:34` · `:42` (per-user tree, `rmtree`, no production caller) | byte-exact |
| `tests/conftest.py:152-158` (`max_age_hours=0`) · `tests/test_mime_admission_contract.py:88-92`, `:168-185`, `:199-216` · `tests/test_file_cleanup.py:73/105/135/271/289/350` · `tests/test_starter.py:836-843` · `tests/test_openapi.py:83-111` | byte-exact |
| `docs/03-processing/file-cleanup.md:64-70` · `:98-102` · `:115` · `:120-122` · `:233` · `:237-242` · `:262-272` | byte-exact |
| `docs/03-processing/processing-api.md:58-60` · `:196` · `:280-293` | byte-exact |
| `docs/11-guides/docker.md:453-459` · `:915` · `:916` · `:927-928` | byte-exact |
| `docker/docker-compose.yml:189-193` · `:342-347` · `:367-375` · `:378-379` · `:383-389` · `:303-305` | byte-exact |
| `docker/Dockerfile:82` · `:132/154/184` · `:212-214` · `:229` · `:242` | byte-exact |
| `frontend/src/shared/types/api.types.ts:96` · `:256-258` | byte-exact (file dirty in the working tree; re-verified there) |
| `docs/SPEC.md:235` · `.ai/tasks/B3-txn-003-durable-processing-transitions.yaml:505` | byte-exact |
| `core/task_queue.py:72` (`queue.enqueue`, no `Retry`) — cited by this pass, not by the input | byte-exact |
| `data_worker.py:481-492` (the row sweep's `UPLOADED`/`PROCESSING` filter) — cited by this pass | byte-exact |

**Defects found in the citations themselves** — three, none of which invalidates its finding:

1. `ART-102`'s evidence table row `raw='..' → name='..'` is **right** and the prose sentence beside it
   (which says the empty component comes from `Path("..").name`) is **wrong**: `Path("..").name` is
   `".."`, `Path(".").name` is `""`.
2. `ART-105`'s `Path(filename).name` table is headed "on POSIX (the deployed tier)" but one row is a
   Windows-host result, and the UNC / drive-letter axes are absent (`VAL-06-016`).
3. `ART-103`'s "a repository-wide search for `.failed` in `src/` returns exactly two hits" is a
   malformed sentence — `.failed` matches nothing in `src/`, and the second "hit" it names
   (`record_failure`) is stated as never existing. The substantive claim it supports (the count is
   discarded at its only call site) is independently confirmed.

No anchor was off by one, and no cited line "used to" contain something. That is the one respect in
which this input differs from phases 01 and 02.

**Drift disclosure — the tree moved during this pass, and one file moved enough to invalidate line
anchors.** A concurrent worker committed nothing but did rewrite the working tree while this
validation was in progress: `git diff --stat` at the end of the pass shows
`src/mkobi/services/data_service.py` **+109/-5**, `src/mkobi/models/data.py` **+41/-2**,
`tests/test_openapi.py` **+32**, plus `src/mkobi/api/routes/data.py`,
`src/mkobi/db/repositories/aggregated_data_repo.py`, `src/mkobi/interfaces/service_interfaces.py`,
`src/mkobi/models/dashboard.py`, `tests/test_dashboards_api.py`,
`tests/test_filter_payload_bounds.py` and `frontend/src/shared/types/api.types.ts`. Every anchor this
report cites into those files was **re-resolved and re-read after the change**, and the quoted text is
unchanged; only the line numbers moved. Two anchors moved materially and are corrected above:
`ART-104`'s `data_service.py:397-402` → `:504-509`, and `ART-106`'s `data_service.py:360-365` →
`:467-480`. `ART-106` also gained a third corroborating artefact in the process —
`src/mkobi/models/data.py:136-145` — which this pass verified **at `HEAD`**, so it existed when the
auditor filed the finding. The auditor's own `data_service.py` anchor (`ART-106`: `360-365`) is
therefore one that has drifted, and a reader must add 107 lines to reach the current construction.
Nothing else this report cites moved: `upload.py`, `file_cleanup.py`, `data_worker.py`,
`file_processing.py`, `app.py`, `config.py`, `enums.py`, `reconciler_lease.py`,
`processing_log_service.py`, `docker-compose.yml`, `Dockerfile` and every `docs/` page are unchanged
from the state the auditor read.

### Appendix C — Disclosures checked rather than accepted

- **`ART-001 … ART-009` occupancy — CONFIRMED.** `docs/SPEC.md:235` names them verbatim
  (*"audit findings `ART-001` … `ART-009`"*); `.ai/plans/_code-context/06-file-artifacts-code-context.md`
  carries a section per identifier (`ART-001` at `:71`, `ART-002` at `:90`, `ART-003` at `:107`,
  `ART-004` at `:124`); `.ai/plans/_code-context/06-file-artifacts-reconciliation-note.md` keys its
  `D-06-*` rulings to them; `.ai/tasks/B3-txn-003-durable-processing-transitions.yaml:505` says
  *"phase 06's ART-007 owns that"*. Starting at `ART-101` is correct and collides with nothing.
- **`VAL-06-001 … VAL-06-010` occupancy — DISCLOSED BY THIS PASS.** The same SPEC row names them, and
  all ten are load-bearing in the reconciliation note. The input disclosed only the `ART-` half.
  Ruling: validation-level identifiers for this phase start at `VAL-06-011` (`VAL-06-013`).
- **`TOPO-111` — not re-filed by `ART-102`.** Read both. `TOPO-111`
  (`.ai/audit/01-process-architecture/findings.md:594-615`, LOW, kind `risk`) is the *dead helpers*
  finding: `get_user_temp_dir` / `cleanup_temp_dir` plus the synchronous Redis client, both
  re-exported and neither called, with the recommendation "investigate the purpose, not delete".
  `ART-102` is the *glob-versus-name* disagreement between a producer and its reclaimer — a different
  object, a different file pair, a different consequence — and it names `TOPO-111` twice, in the
  recommendation and in the roadmap, precisely to prevent the one resolution that would merge them
  (moving admission onto `get_user_temp_dir` would create a second, un-swept tree). Cross-reference,
  not duplicate. Verified independently: `user_cache_dir` occurs only inside `get_user_temp_dir`, and
  neither helper is called from `src/` outside its own definition and `mkobi/utils/__init__.py:9,13,14`.
- **The 40-hour premise — REJECTED** (`VAL-06-011`): 37 hours, and zero uploads inside it.
- **`ART-101`'s coverage claim — REFUTED** (`VAL-06-012`): seven shipped tests call the real detector.
- **Removal census — RE-VERIFIED, nine sites, exactly as Appendix D states.** `unlink|rmtree` across
  `src/` returns `upload.py:217`, `upload.py:265`, `file_processing.py:272`, `data_worker.py:941`,
  `:962`, `:1036`, `:1058`, `file_cleanup.py:101`, `file_utils.py:42`. One move
  (`file_processing.py:244`, `Path.replace`), one non-production caller
  (`tests/conftest.py:158`). The census is correct; the *characterisation* of two of its rows is not
  (`missing_ok=True` is not a guard for non-`ENOENT` errors — see `ART-104` and `VAL-06-015`).
- **Process inventory — RE-VERIFIED.** `docker ps` shows `mkobi-app-1` and `mkobi-rq-worker-1` both
  `Up 37 hours`; `rq_worker_wrapper.py:205-238` runs `worker.work()` with no reconciler task, so
  exactly one sweeper exists, under the lease, in the app process.
- **"The only production call site" claims — RE-VERIFIED.** `cleanup_stale_temp_files` has exactly one
  production caller (`data_worker.py:1562`) plus one test-tier caller (`tests/conftest.py:158`); the
  report is right that `db/starter.py` no longer references it and right that
  `tests/test_starter.py:836-843` pins that.

### Appendix D — Runtime reproductions (independent, in `mkobi-test` `test-app`)

Every probe ran through
`docker compose -p mkobi-test -f docker/docker-compose.test.yml run -T --rm --no-deps test-app python -`
with `UPLOAD__TEMP_DIR` redirected to a `/tmp` path so no live volume and no repository file was
touched. libmagic is present only in this tier, per `.kilo/rules/commands.md`.

| Probe | Result | Serves |
| --- | --- | --- |
| libmagic trailing-newline boundary | `len=24 → text/plain` refused / `len=25 → text/csv` admitted; boundary mapped (unterminated ≤ 2 rows refused, ≥ 3 admitted; terminated ≤ 1 refused, ≥ 2 admitted; 500-row cut admitted) | ART-101 |
| `pl.read_csv` on every refused buffer | reads cleanly, correct row count, on **all** of them | ART-101 |
| sweep glob visibility over 8 in-flight name shapes | `created=8 matched=4`; `CleanupResult(deleted=4, already_gone=0, failed=0)`; four survivors at `max_age_hours=0` | ART-102 |
| per-name byte limit | `200/250/255` OK, `256/300` → `OSError [Errno 36]` | ART-105 |
| `Path(filename).name` over 15 client basenames | traversal, absolute, UNC, drive-letter, `..`, `.`, `""`, `NUL`, `CON`, `PRN`, `COM1`, `CON.csv`, trailing dot, padded, unicode, emoji — all collapse to one harmless component; only the 300-byte name fails | ART-105, `VAL-06-016` |
| symlink traversal | a symlink named `upload_<uuid>_link.csv` **is** matched by `*.csv*`, `is_file()` is `True` and `open()` follows it to a target outside the directory | negative result, below |
| `finally`-block exception masking | `MASKED -> OSError 30 EROFS`, `__context__ = AppErr` | `VAL-06-015` |
| `Path.exists()` on a NUL-containing path | returns `False` (swallows `ValueError`), so the `finally` reaches the `unlink` | `VAL-06-015` |
| POSIX `unlink` on a read-only *file* | succeeds (permission is on the parent directory), so `chmod` is not a trigger | `VAL-06-015` |
| multipart parser spill (Starlette 1.3.1, python-multipart 0.0.32, uid 100) | `12 B → rollovers=0 TemporaryFile_calls=0`; `~4 MB → rollovers=1 TemporaryFile_calls=1`; with a non-writable temp dir: `12 B → 200`, `~4 MB → 500` | cross-phase escalation |

**Missed-valuation sweep — negative results, recorded so a later pass does not re-open them.** These
are the phase's two declared rules, checked directly and not merely sampled:

- **Path traversal — none.** The only client-controlled string that becomes a filesystem component is
  `upload.py:205`, and `Path(...).name` reduces every traversal, absolute, UNC, drive-letter and
  separator form to a single component on the deployed platform. No user id or dashboard id reaches
  a path anywhere in `src/`: `file_processing.py:242` builds `{log.id}{ext}` from a DB-generated UUID,
  `file_utils.py:28` is the only `user_id`-derived path and has no caller, and the remaining path
  constructions (`config.py:246`, `logging_config.py:113`) take operator-supplied configuration.
  Reserved device names (`NUL`, `CON`, `PRN`, `COM1`) are neutralised by the `upload_{uuid}_` prefix;
  trailing dots and spaces are created verbatim and are harmless as intermediates.
- **Symlink following — present but not reachable by a user.** `open`, `exists`, `is_file` and `stat`
  all follow symlinks, and the sweep's glob matches a symlink (proved). It is not a finding because
  planting one requires write access to the `app_data` volume inside the container, and every name the
  producer writes carries a fresh `uuid4` or a DB-generated log id, so a pre-planted link cannot be
  aimed at a target the attacker chose. `Path.replace` (`file_processing.py:244`) replaces a symlink
  rather than following it.
- **Over-broad cleanup — none.** The sweep globs one directory and unlinks only what it matches;
  `shutil.rmtree` (`file_utils.py:42`) has no production caller and is owned by `TOPO-111`. The
  `glob("*.csv*")` widening the input rejects is rejected here for the same reason: it would let the
  sweep remove files it does not understand.
- **Cleanup completeness — no absent purge.** `upload.py:260-265` removes the staging file on every
  managed exit; `file_processing.py:272` removes the moved file when the enqueue fails; the worker
  removes the artefact on both terminal edges; the age sweep reclaims the residue. There is **no**
  purge of the per-user `user_cache_dir("mkobi", appauthor=False)/uploads/<user_id>` tree — and none
  is owed, because no production code creates that tree: `get_user_temp_dir` has no caller, which is
  `TOPO-111`'s subject and the code that would create it. The `AGENTS.md` §5 claim that this tree is
  the upload path is a documentation defect owned by phases 02/08 (C06-15), not a missing purge. The
  one real completeness gap in this area is `ART-102`'s glob disagreement, already filed.
- **Size-limit enforcement timing — enforced while streaming, with one seam that is not this phase's.**
  `upload.py:211-230` checks `total_bytes` per 8 KB chunk and unlinks at the ceiling, so the endpoint's
  own check is streaming. The seam: the ASGI server receives and parses the whole multipart body before
  the endpoint runs, so the first write happens above the check. The input declines this correctly —
  the phase task assigns "the inbound surface form and the transport-level body bound" to phase 07 —
  and phase 07 has not run. This pass went past the input and measured the seam, and the measurement
  produced the cross-phase escalation above: the parser spills to `tempfile.gettempdir()` above
  **1 MiB**, and the production `app` service has a read-only `/tmp`
  (`docker-compose.yml:189-193`; `rq-worker` gets a tmpfs at `:303-305`, `nginx` at `:386-389`, the
  `app` service gets none) while the dev tier relaxes it (`docker-compose.override.yml:195`). Phase
  07 must not read "enforced during streaming" as "bounded before buffering", and must verify the
  composition before filing.

### Appendix E — Coverage ledger (residual footer)

| Block | Input verdict | This pass |
| --- | --- | --- |
| 1 — the accepted artefact's identity | 2 findings | every claim re-derived at its cited lines; one claim refuted (`VAL-06-012`); the mechanism reproduced and its boundary mapped |
| 2 — residence and what bounds it | 2 findings | every claim re-derived; both runtime tables reproduced; the consequence bounded |
| 3 — reconciliation, both directions | no findings | re-verified and **sustained**: `processing_logs.py:30-72` carries seven columns and names no artefact, and a search for `\.glob\(|rglob|iterdir|os.listdir|scandir` across `src/` returns exactly one hit — the age sweep at `file_cleanup.py:92` — so there is no second reader of the area |
| 4 — removal and the record of a failed removal | 2 findings | the nine-site census re-verified by re-grep; one site's characterisation corrected and a tenth site found unguarded (`VAL-06-015`) |
| 5 — the one-time secret outside the database | no findings | **sustained**, verified rather than inherited: `credential_stored` is computed from the store's own `bool` at `auth_service.py:601-605` and `:694-698` and returned at `:628` / `:722`; `admin.py:332` and `:439` return the service result verbatim; `retrieve` consumes the handle in one transactional pipeline (`temp_password_store.py:144-147`) and fails loud (`:154-158`), which `admin.py:527-533` maps to `503 SERVICE_UNAVAILABLE`. No defect found; nothing re-litigated |
| 6 — the built interface bundle | 2 findings | every claim re-derived against the compose file and Dockerfile; one same-class documentation surface missed by the input (`VAL-06-014`) |
| 7 — which process reclaims an artefact | no findings | the process set re-verified; the missed doc claim found (`VAL-06-014`) |
| 8 — is an accepted artefact returned | no findings | **sustained**: one `FileResponse` in `src/` (`app.py:580`, the SPA index) and three `filename` population sites (`upload.py:244`, `data_service.py:181`, `:467-480`) |

**Claims left unsettled, with the reason.** (1) The **contents of the live `app_data` volume were not
listed**, so no finding here is supported by observed residue in a running deployment — every artefact
finding is filed from the executing path plus a reproduced mechanism, and the input says the same.
Reading a container filesystem needs `docker exec`, which this permission set marks `ask`.
(2) **`ART-104`'s state-machine violation was not provoked end to end through HTTP**; it is proven
statically (an unconditional `UPDATE` on a row the commit already made `COMPLETED`) plus a reproduced
`finally`-masking demonstration of the same class, and the `unlink` fault class is a documented
`OSError`. (3) Whether an operator's monitoring actually consumes `/health/detailed` is outside the
repository; `ART-103`'s re-grade assumes it does not, which is the only assumption that could move
that band back up. (4) The **contents of the live `mkobi-app-1` log before its current 37-hour
container** were not available, so `VAL-06-011` measures the window that exists rather than the
deployment's whole life — which is enough, because the window's item count is zero.

### Appendix F — Finding-ID namespace ruling

Re-derived from the working tree, not inherited from the input's disclosure.

| Prefix | Declared by | Minted in this input | In-source markers | Compound form | Reuse across phases | Ruling applied |
| --- | --- | --- | --- | --- | --- | --- |
| `ART-` | `.kilo/commands/audit/phases/06-audit-file-artifacts.md:125` (*"Finding-ID prefix: `ART-`"*) | `ART-101 … ART-108` | **none** — a search for `ART-[0-9]` across `src/`, `tests/`, `alembic/`, `docker/`, `frontend/`, `docs/` returns hits only in `docs/SPEC.md:235` and `.ai/` planning artefacts, never in shipped code, configuration, tests or product documentation | `06-file-artifacts` + `ART-1xx`, from the template's front-matter `phase:` paired with the declared prefix | **none** — no sibling phase declares or mints `ART-` | `ART-101 …` is correct and collides with nothing; the in-source markers are **provenance for a completed remediation record**, not load-bearing code, so nothing needs migrating — but the historical `ART-001 … ART-009` block must never be renumbered into this range |
| `VAL-06-` | this phase, per `.kilo/commands/audit/phases/99-audit-validate.md:189` (`VAL-` for validation-level findings, own section) | `VAL-06-011 … VAL-06-016` | none in shipped source; the ten historical ids **are** load-bearing (`docs/SPEC.md:235` + eleven references in `.ai/plans/_code-context/06-file-artifacts-reconciliation-note.md`) | `06-file-artifacts` + `VAL-06-0xx` | the historical `VAL-06-001 … VAL-06-010` belong to the **previous** validation run of this same phase | start at **011**; the input's Appendix F disclosed only the `ART-` half of the collision its own evidence row records (`VAL-06-013`) |
| `VAL-06-001 … VAL-06-010` | the prior validation run of phase 06 | — | load-bearing provenance (SPEC row 3.32) | — | — | **occupied; not reused, not renumbered** |

**One provenance claim that could not be reproduced.** The input's Appendix F states that the
`ART-001 … ART-009` report is *"previously deleted from the working tree"* and is *"referenced by the
two notes above but is **not present on disk**"*. Reproduced: `.ai/audit/06-file-artifacts/` contains
only `findings.md`, whose own namespace is `ART-101+`. The claim holds. What could **not** be
reproduced is any trace of the prior report's own text or its ten verdicts — the identifiers survive
only as references, so this pass could re-derive each prior finding's *status* only from the
reconciliation note's and code-context note's summaries, exactly as the input did. No third family
(`ART-0xx` beyond 009, `ART-01x`) exists anywhere in the tree.