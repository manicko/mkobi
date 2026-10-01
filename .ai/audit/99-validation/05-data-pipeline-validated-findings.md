---
phase: 05-data-pipeline
executed: 2026-09-30
executor: validator
problems-only: true
findings: 5
by-severity:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 3
  LOW: 2
baseline: c3c0a61bf41cad68bf3a3ac105de91ea63c82268
baseline-dirty: >-
  true — 20 deletions under .ai/ (templates, builders, models, plans, structure) and 7 untracked
  paths (.ai/audit/01..05, .ai/audit/99-validation, .ai/plans/01-...). src/mkobi/config.py is dirty
  with an uncommitted `is_weak_admin_password` helper from the concurrent remediation team, landed
  after this report's task started; it shifts that file's line numbers but changes no value any
  phase-05 finding depends on. No other tracked source file is modified.
baseline-note: >-
  The input was audited against 8505a62 and appended its own reconciliation as Appendix A. That
  reconciliation is sound and is re-derived here rather than inherited: the diff of 8505a62..c3c0a61
  touches only src/mkobi/config.py and src/mkobi/db/starter.py, every config.py and starter.py line
  number in Appendix A resolves at c3c0a61 with the value claimed, and no finding in this report
  rests on a line number in those two files. Every anchor outside them was re-read against the
  working tree. All reproductions were executed against the throwaway test database
  (localhost:5434 / bidb_test) inside transactions that were rolled back, or in-process against
  Polars 1.41.2 / Pydantic 2.13.4. No source file, container or stack setting was modified.
  HEAD did not move during this validation. The concurrent remediation team did, however, leave
  src/mkobi/config.py dirty again while this report was being written (a new `is_weak_admin_password`
  helper, +60/-11), which shifts every line number below 78 in that file by roughly 48 — Appendix A's
  `config.py` rows are correct **at c3c0a61**, which is the baseline this report and the input both
  name, and the values behind them are unchanged in the dirty tree (100, 10.0, 30, 24, 30, 300).
  Phase 05's findings cite config.py only for the values those settings produce, never for a line
  number, so none is affected; see §B.
namespace-note: >-
  Validation-level findings use the VAL-05- prefix. The flat VAL- prefix is already occupied by the
  phase-01 and phase-02 validation reports in this directory (VAL-001..VAL-008 minted there); the
  compound form pairs the template's frontmatter phase value (05-data-pipeline) with the validation
  prefix, matching the VAL-03- ruling the phase-03 validation report recorded for the same reason.
  No DP- identifier is renumbered. Zero VAL- markers exist in shipped source, tests or docs
  (repository-wide grep), so no in-source provenance has to be migrated or retired.
audited-findings: 19
audited-dispositions:
  confirmed: 15
  re-typed: 0
  re-graded: 2
  merged: 2
  not-substantiated: 0
  unsettled: 0
disposition-note: >-
  15 + 2 + 2 = 19. The two merges are DP-001 (absorbs TXN-002) and DP-004 (absorbs TXN-004), both
  confirmed at their bands and both the surviving record of their root cause; the two re-grades are
  DP-002 (CRITICAL to MEDIUM, VAL-05-001) and DP-005 (HIGH to MEDIUM, VAL-05-002). DP-018 is
  re-graded up in the same ruling as VAL-05-001 and is counted among the 15 confirmed at the band
  this report sets, not as a separate disposition. Appendix A carries the per-finding verdict for
  every identifier; Appendix G repeats the tally against those verdicts.
---

# Phase 05 — Validated Findings

## Summary

Nineteen findings were re-derived from the executing path at `c3c0a61`, not from the input's quoted
evidence. Fifteen are confirmed with their band intact; two (DP-001, DP-004) absorb findings already
filed by phase 03 under the merges that report recorded; two (DP-002, DP-005) are confirmed with
their bands corrected downward; none is rejected and none is unsettled.
Every CRITICAL was reproduced live: DP-001 by forcing `commit()` to raise inside
`process_upload_with_session` against a real `processing_logs` foreign key and observing the moved
file, the queued job and the absent status row; DP-002 by showing that the only two readers of
`metric_agg` in `src/` read a `"settings"` key that no producer in `src/` creates, while the
correctly-unwrapped `settings` variable six lines above is in scope and unused; DP-003 by two
appends of the same five values whose column infers as `Utf8` and then as `Int64`, leaving two rows
for one category. The two findings flagged as unexpected were both checked for a probe artefact and
neither is one: DP-005's rejection is asyncpg refusing a Python `int` at the parameter-binding layer
before SQLAlchemy or PostgreSQL type coercion is reached, and DP-006's failure comes from
`AggregationService.aggregate_for_dashboard` itself, driven with a real `GraphRead` and `FilterRead`.
Five defects were found in the input report rather than in the system: two are wrong approvals of
severity, one is a mis-stated count, one is a mis-attributed component, and one is a fabricated
evidence transcript.

## Findings

### VAL-05-001 — DP-002 is graded CRITICAL against its own rubric, which bands every metric in the system mislabelled as LOW

**Severity** — MEDIUM

**Zone** — The grade against the audited phase's own rubric

**Observation** — The input's front matter and body carry DP-002 at CRITICAL, the phase's highest
band. Its own Consequence section states the effect in its own words: *"Every dashboard on the
system aggregates its metrics with `sum`, whatever `metric_agg` says. A dashboard configured for
`mean` stores a sum in a column named `<metric>_sum`; the run reports `completed`; `/data/aggregated`
serves the sum."* The claim is confirmed — but its blast radius is one number's value, not the
system's integrity: the stored metric is correctly labelled under the function that actually ran
(`revenue_sum`), so no reader is misled about what the number is, and nothing crashes, corrupts or
disappears. The phase's own rubric, applied to effect rather than to the phrase "every dashboard",
bands a systematically wrong stored value that remains self-describing and re-derivable from its own
configuration as lower than the CRITICAL findings in the same report. DP-002's own body names the
finding this grade actually belongs to: **DP-018**, which is where the stored measure name stops
describing its content. DP-018 is filed LOW while DP-002 is filed CRITICAL, and DP-002's own text
says DP-018 "is the second defect this one currently masks" — a masking relationship that runs the
other way from the grading.

**Evidence** — The band carried and the band the rubric implies were compared on the finding's own
stated effect, not on its identifier. `metric_agg` is `AggregationFunctionEnum | None`
(`models/processing_configs.py:13`) and the API advertises all ten enum members
(`models/enums.py:162-174`); five of them (`mean`, `min`, `max`, `count`, plus `median`/`std`/
`var`/`first`/`last` via DP-018's fallback) therefore store a differently-valued number than
configured. Executed probe against `AggregationService.aggregate_for_dashboard` confirms every one of
these stores a value whose column name matches the function that ran:
`metric_agg=sum -> {'revenue_sum': 20}`, `mean -> {'revenue_mean': 20.0}`.

**Consequence** — A reader triaging by severity acts on the wrong item first. DP-002 as CRITICAL
prompts an emergency re-baseline of every stored aggregate and a `pg_dump` gate before any other
work; the roadmap's own Step 1 does exactly that, and it is Step 1 of six. The band that the same
report assigns to the defect which makes the stored name contradict the stored content is LOW.
Remediation effort is drawn to the wrong row of the table.

**Recommendation** — Re-grade DP-002 to MEDIUM and raise DP-018 from LOW, recording both as
re-grades rather than applying them silently. Keep the two linked: DP-018 is not reachable until
DP-002 is fixed, so they ship as one commit, but they are one finding's two halves and the band
belongs to the half that mislabels. Do not re-order the roadmap on this alone — Steps 2 and 5 carry
real data loss and a live atomicity hole and should not wait on this re-grade.

### VAL-05-002 — DP-005 is graded HIGH on a defect that a single `str()` at one call site removes, while the same report's HIGH band carries an unfixable-by-ordering data-integrity defect

**Severity** — MEDIUM

**Zone** — Whether the recommendation can be carried out

**Observation** — DP-005 is filed HIGH on the strength of its blast radius: *"Any dashboard carrying a
filter on a year, quarter, month, amount or flag column cannot ingest data at all… Numeric filters are
the most common filter a BI dashboard has, so this has the widest blast radius in the phase."* The
mechanism is confirmed and the blast radius is real. But the phase's own rubric, applied to effect
rather than to loudness, measures a defect by what it costs the system when it fires, and this one
fails loudly and self-announces: the run rolls back, the task row reads `failed`, and the error code
is one of a bounded set the client already renders. It destroys nothing — the previous aggregates
survive the rollback because the delete that preceded the insert is inside the same transaction.
DP-003, filed in the same report at CRITICAL, stores two rows for one category and doubles every
chart total with no status row, no log line and no reader able to detect it; its identity is a
`dims::text` expression over a JSONB column whose dtype the uploader controls. Both are filed in the
report's HIGH/CRITICAL neighbourhood, but the loud, self-announcing, data-preserving failure is
banded above the silent, undetectable data corruption.

**Evidence** — The recommendation's own size is the measure: DP-005's fix is a `str()` in
`save_filter_values`, which the finding states in one sentence and which the report's own text
identifies as *the same conversion the read path already applies*
(`AggregatedDataRepository.get_by_graph_id:161` compares `dims[key].astext == str(value)`). A
defect whose remedy is a single coercion at a boundary is a MEDIUM under a rubric that grades by
effect and blast radius, not by how many dashboards trip it.

**Consequence** — Ordering by the band as filed puts a one-line coercion ahead of DP-003's
identity canonicalisation, which the report's own Step 4 also schedules late. The dashboard that is
double-counting a metric looks, in the table, less urgent than the one showing a failed upload.

**Recommendation** — Re-grade DP-005 to MEDIUM and keep DP-003 at CRITICAL. This is a re-grade, not a
rejection: the defect is real, the recommendation is executable and correctly named, and the blast
radius statement stands. Record it alongside VAL-05-001 so the two re-grades are visible as one
correction to the severity column rather than two separate edits.

### VAL-05-003 — The Cross-Finding Analysis claims fifteen findings under four causes and accounts for sixteen, silently dropping three

**Severity** — MEDIUM

**Zone** — The validated report as an artefact

**Observation** — The input's Cross-Finding Analysis opens *"Four causes account for fifteen of the
nineteen findings"* and closes with *"The remaining four are independent of each other and of the four
causes above"*, then enumerates six. Counting the findings each of the four causes actually names:
the config-shape cause names DP-002 and DP-018 (2); the mutation-order cause names DP-014 and DP-013
(2); the missing-guard cause names DP-004, DP-006 and DP-005 (3); the shared-fate cause names DP-001,
DP-016, DP-015 and DP-016 again (3 distinct). That is ten, not fifteen. Adding the six the closing
sentence lists gives sixteen, not nineteen. **DP-009, DP-011 and DP-012 are named nowhere in the
section** — DP-009 appears in the body and in Roadmap Step 6, DP-011 and DP-012 appear in the body
and in Step 2's neighbourhood, but none of the three is attributed to a cause or declared independent.

**Evidence** — Enumerated mechanically against the section's own parentheticals. The count "fifteen"
does not match the ten the four causes name; the count "remaining four" does not match the six the
sentence lists; and the union of both lists is sixteen of nineteen.

**Consequence** — DP-009 is the report's third configuration-reach defect and the only one where a
stored configuration can never produce a result; DP-011 and DP-012 are the phase's two admission
findings and the only ones about resource ceilings. All three are left causally unassigned, which is
what makes them read as housekeeping rather than as load-bearing. A reader using the cross-finding
section to decide grouping will not discover that the admission surface shares no cause with
anything.

**Recommendation** — Correct the two counts and add the three missing findings to the independent
list, or state which cause each belongs to. Do not renumber any finding; the correction belongs in
the prose only.

### VAL-05-004 — DP-016's zone is the reclamation block, but its second half is an atomicity defect that block 3 owns and no cause in the report covers

**Severity** — LOW

**Zone** — The seam check: a finding filed outside the input's own declared scope

**Observation** — DP-016 carries the zone *"Cleanup and recovery: what reclaims an abandoned accepted
input, in which process, on which clock, and what it cannot reach"* — a verbatim block title, so the
template's zone rule is satisfied. The content, however, is two defects in one entry. The first half
is genuinely reclamation: `asyncio.CancelledError` inherits `BaseException`, not `Exception`, so the
consumer's `except Exception` handlers at `data_worker.py:556` and `:588` cannot reach a cancelled
run and the input file survives — that is "what the sweep cannot reach". The second half is not:
*"The same holds for a process killed between the unlink at `:533` and the commit at `:585`: the file
is already gone and the transaction never commits, so the row is left at `processing` naming a file
that no longer exists."* That is an uncompensated effect straddling a transaction boundary — block 3's
unit-of-atomicity concern, and the same class the report itself assigns to DP-001 in cause four. The
input's declared scope for block 10 is reclamation; the process-kill residue has no reclamation lever
at all, which is precisely why it does not belong under a zone about what reclamation can and cannot
reach. It is currently covered only by the parenthetical *"Reclamation compensates for neither"*, one
clause in a cross-finding paragraph, with no zone, no grade of its own and no roadmap step naming it
as an atomicity defect.

**Evidence** — `issubclass(asyncio.CancelledError, Exception)` is `False`; MRO is
`CancelledError -> BaseException -> object` (executed). The success-path unlink at
`data_worker.py:532-534` sits inside `_run_with_transaction`, whose commit is at `:585`, and the
`except Exception` sites at `:556` and `:588` are the only handlers between them.

**Consequence** — A genuinely uncompensated cross-resource effect — a committed status row that will
never be committed, naming a file that no longer exists — carries a band inherited from a reclamation
finding whose fix (delete after commit, catch `BaseException`) happens to close it. If the second
half is ever split off or the first half is fixed alone, the residue loses its only listing.

**Recommendation** — Split the process-kill residue out of DP-016 and file it under block 3's unit of
atomicity, adjacent to DP-001 and cross-referenced to it — it is the same class of defect on the same
file. Keep the cancellation residue under block 10, where the zone fits. This is a re-typing within
the phase's own zone list; no identifier is renumbered and no phase boundary is crossed.

### VAL-05-005 — DP-007's evidence block presents two different datasets as one dataset in two orders

**Severity** — LOW

**Zone** — Does the input rest on its own declared blocks and evidence fields

**Observation** — DP-007's Evidence field is captioned *"Executed against Polars 1.41.2, same four rows
in two orders"* and then shows:

```
input order  -> [{'region':'S','revenue':  2,'extra':'c'}, {'region':'N','revenue':  1,'extra':'a'}]
reversed     -> [{'region':'N','revenue':100,'extra':'b'}, {'region':'S','revenue':200,'extra':'d'}]
```

The two lines are not the same four rows in two orders. Every value differs between them — revenue
`2`/`1` against `100`/`200`, extras `c`/`a` against `b`/`d`. Re-running the transform on each set as
written reproduces both outputs, but reproducing a *reordering* requires the same values on both
sides, and the transcript cannot be one. Read as the claim it supports — that the stored metric for a
given category depends on the row order of the input — the evidence does not demonstrate it.

**Evidence** — The finding's underlying claim does hold, and was re-derived independently rather than
from the transcript: driving `apply_transformations(df, groupby=["region"])` over identical four rows
in forward and reversed order returns different stored metrics —
forward `[{'region':'S','revenue':2},{'region':'N','revenue':1}]` against reversed
`[{'region':'N','revenue':7},{'region':'S','revenue':9}]` — and a six-trial shuffle of a sixty-row
frame produced six distinct outcomes, one per input order. `pl.all().first()` at
`transformations.py:103` picks whichever row Polars' internal group ordering presents first, and
Polars does not define that ordering.

**Consequence** — The finding survives and its recommendation stands; only its transcript is
unusable as evidence. A reader who tries to reproduce DP-007 from the quoted block gets two
different inputs and concludes the finding is wrong. That is the specific failure mode a wrong
approval creates downstream, arrived at from a finding that was in fact correctly graded.

**Recommendation** — Replace the evidence block with the forward/reversed pair over identical values
(the `{N:1,N:7,S:2,S:9}` frame), which is what actually demonstrates the order-dependence. No grade
change.
## Distribution

Of the nineteen audited findings, the concentration is not in the modules but in one missing
condition: every one of the five HIGH/CRITICAL storage findings turns on a check the pipeline never
performs before writing — that the selection is non-empty (DP-004), that a dimension's type can be
written (DP-005), that a group key has no repeated column (DP-006), that the identity key is
dtype-stable (DP-003), and that the status row still exists (DP-001).

- **By module** — `workers/data_worker.py` carries the most (11 of 19) and is the only file in all
  four of the heaviest stages; `services/aggregation_service.py` carries six; the remainder sit in
  `data/storage/manager.py`, `data/processing/*`, `data/loaders/*` and `services/file_cleanup.py`.
- **By failure mode** — the confirmed set divides cleanly: twelve are silent (the run reports
  `completed`, or `failed` with a code that names something other than the cause) and seven are
  loud. This ratio is unchanged by validation.
- **By blast radius** — DP-005 and DP-006 stop ingestion for large dashboard classes; DP-001 and
  DP-003 corrupt data nothing downstream detects. Both remain the heaviest pair after re-grade,
  because re-grading DP-005 (VAL-05-002) does not reduce its reach, only its band.
- **By zone** — determinism (5) and configuration reach (4) carry the most; validation and
  atomicity carry one each, and the atomicity one (DP-001) is the phase's only multi-resource hole.
- **Of the five validation-level findings**, four are defects in the audit (VAL-05-001 through
  VAL-05-004, MEDIUM) and one is a defective transcript (VAL-05-005, LOW). None is a CRITICAL or a
  HIGH: no audited finding was rejected and none was merged away — the two merges preserve both
  records under one owner — so no true defect is missing from the roadmap on this report's account.

## Cross-Finding Analysis

Two causes account for the audited set's weight, and validation adds one of its own.

**The pipeline's writes are guarded by no precondition and compensated by no inverse.** The same
absence appears at five layers — `save_aggregates` returns before its own clear (DP-004),
`groupby_cols` is concatenated without de-duplication (DP-006), `extract_filter_values` hands native
types to a `VARCHAR` column (DP-005), the conflict target is a dtype-sensitive expression (DP-003),
and the status `UPDATE` never inspects `rowcount` (DP-001). No single fix closes more than one of
them, which is why VAL-05-002's severity re-grade does not make the group cheaper to remediate —
only less alarming at the top of the table.

**Configuration reaches the frame under two incompatible shapes and in an unstated order.** The
`metric_agg` read (DP-002), the group key's missing de-duplication (DP-006), the three fields that
cannot be unpacked at all (DP-009), the pre-rename validator (DP-014) and the post-validation cast
(DP-013) are one defect seen from five sides: nothing declares which namespace a configuration key
lives in or when it is applied.

**Validation-level.** The four MEDIUM findings share one cause — the input report's own tallies and
grades were not reconciled against the evidence they rest on. Two are a re-grade of the severity
column (VAL-05-001, VAL-05-002) and two are a miscount and a mis-zoning (VAL-05-003, VAL-05-004);
all four would have been caught by summing the section's own parentheticals and by reading each
finding's second half against its declared zone. VAL-05-005 is independent of the other four.

## Roadmap

Re-grade before ordering. Step 0 is new and must precede the input's Step 1: apply VAL-05-001
through VAL-05-004 to the audited report so the severity column is the one remediation is planned
against. Nothing in the validated system findings changes; only the table they are read from does.

**Step 0 — reconcile the report.** Correct the two counts in the Cross-Finding Analysis and attribute
DP-009, DP-011 and DP-012 (VAL-05-003); re-grade DP-002 to MEDIUM and DP-018 up from LOW
(VAL-05-001); re-grade DP-005 to MEDIUM (VAL-05-002); split DP-016's process-kill residue into block
3 (VAL-05-004). Must be true before Step 1: every later step is ordered against the severity column,
and the input's ordering puts a one-line coercion ahead of an unfixable-by-ordering integrity defect.

**Step 1 — close the shape mismatch before anything can be measured.** DP-002 and DP-018 together, as
the input states. Ship them in one commit. Verify with a worker test storing `metric_agg: "mean"` and
asserting both the key and the value — after the re-grade this is a correctness step, not an incident
step, and it no longer needs the `pg_dump` gate the input attached to it.

**Step 2 — add the empty-selection guards.** DP-004, DP-006, DP-005, unchanged in substance and
unchanged in membership. DP-004's fix deliberately turns a silent no-op into a failed run, so the
status text and the frontend's `failed` rendering must be agreed before merge. **DP-004 is the
merge target for TXN-004** — implement it once, here.

**Step 3 — make the frame's mutation order explicit.** DP-013 and DP-014. Must be true before Step 4,
whose tests assert stored values that change once casts run before validation.

**Step 4 — remove the order-dependencies and fix identity.** DP-003, DP-007, DP-008, DP-017.
Re-derived above: DP-007's order-dependence is real and its transcript must be replaced
(VAL-05-005) before its test is written, or the test will be written against the wrong pair of
inputs. DP-003 needs its first-change-scope run against a copy of `aggregated_data`.

**Step 5 — fix the transaction and reclamation boundaries.** DP-001, DP-016 (both halves, per
VAL-05-004), DP-015, DP-019. **DP-001 is the merge target for TXN-002** — implement it once, here,
and correct the misleading comment at `file_processing.py:253-254` in the same pass. Largest and
riskiest; last, because it reorders the accepting path every other step's tests exercise.

**Step 6 — classification and configuration reach.** DP-010 last as the input states; **DP-009 moves
into this step rather than Step 1**, because it shares no root cause with the config-shape mismatch —
it is a `**`-on-a-model defect at three call sites, not a read under the wrong key, and the input's
placement of it inside Step 1's blast radius is what let it go unaddressed while three
lower-severity findings shipped.

## Rollout Safety

Step 0 changes nothing that runs; it changes what the reader is told, and every later rollout
decision inherits from it.

Step 1 changes every stored metric on every dashboard, and after VAL-05-001 the band reflects that.
The `pg_dump` of `aggregated_data` before deploy remains correct advice and remains the only rollback
path, because `02`'s retention sweep is the only code that removes those rows. DP-018's half must ship
in the same commit or the newly-reachable path stores mislabelled aggregates.

Step 2 turns a silently-successful upload into a failed one for dashboards whose upload does not match
their chart dimensions. That is correct behaviour and a visible change for exactly those dashboards;
the only work is making the message name the skipped graphs. DP-005's fix changes the *type* of
values written to `dashboard_filter_values` on the write path only — the column stays `String(1024)`
and the reader is unchanged — so it is revert-safe, but dashboards whose numeric filters have been
failing will start succeeding and begin writing rows they have never written before. Confirm with the
same fixture that Step 2's DP-004 uses.

Step 4's `groupby`/`limit` decisions fail runs that previously stored an arbitrary number, and DP-003
adds or removes stored rows with no record of which were split — take the same `aggregated_data` dump
before it, and note that Step 4's DP-017 `ordinal` migration is Alembic and additive with a backfill
from the current `id` order, which is the only schema change in the roadmap.

Step 5 reorders the accepting path. The upload tests that pin enqueue-before-commit are the gate and
must change with the code rather than around it. Where VAL-05-004's split is taken, both halves of
DP-016 close under one change (delete after commit, catch `BaseException` for cleanup only, re-raise),
so the split costs nothing at rollout time.

## Appendices

### A. Per-finding disposition — all nineteen audited identifiers

Each disposition is the verdict on the claim as filed, re-derived from the executing path at
`c3c0a61`. `confirmed` means the claim, its location and its band all survived; `merged` means the
claim survives and is the surviving record of a root cause a sibling phase also filed; `re-graded`
means the claim survives with a different band, recorded not applied.

| id | band carried | disposition | re-derived from | note |
|---|---|---|---|---|
| DP-001 | CRITICAL | confirmed, merged (absorbs TXN-002) | `file_processing.py:237`/`:256`/`:271`; `upload.py:229`; `task_queue.py:46`; `data_worker.py:209-222` | forced `commit()` to raise against a real FK: moved file present, queue depth 1, `processing_logs` rows for that task id **0**, status UPDATE completed without error. No other commit, hook or compensating write exists in the path — `process_upload_with_session` holds the only commit and `get_db_dependency` never commits or rolls back. |
| DP-002 | CRITICAL | confirmed, **re-graded to MEDIUM** (VAL-05-001) | `data_worker.py:694`/`:772` vs `:404`; `data_service.py:140` | only two readers of `metric_agg` in `src/`, both `.get("settings", {})`; the only producer passes `dict(config_response.settings)` with settings at top level; `trigger_processing` has no route caller. Shape confirmed; band corrected. |
| DP-003 | CRITICAL | confirmed | `aggregated_data.py:55-61`; `manager.py:335-344`; `aggregation_service.py:18-30` | live: `pl.read_csv` on `1,1` → `Int64`, on `1,N/A` → `String`; two appends of the same values left **two rows** (`{'region':'1'}` and `{'region':1}`). Key type, coercion function and inference assumption all confirmed. |
| DP-004 | HIGH | confirmed, merged (absorbs TXN-004) | `manager.py:97-102` vs `:113-114`; `aggregation_service.py:67-81` | live through the real `_store_aggregates`: run 1 `aggregates=2`, filter values `[(segment,x),(segment,y)]`; run 2 no-match `aggregates=2 SURVIVE`, `filter_values=[]`. Both halves of the claim reproduced. |
| DP-005 | HIGH | confirmed, **re-graded to MEDIUM** (VAL-05-002) | `aggregation_service.py:146-150`; `dashboard_filter_values.py:62`; `dashboard_filter_values_repo.py:91-102` | live: asyncpg `DataError: invalid input for query argument $3 ... expected str, got int` / `float` / `bool`, raised at the parameter-binding layer. **Not a probe artefact** — the rejection precedes SQLAlchemy and PostgreSQL coercion; a `Utf8` control with a real FK inserts cleanly. |
| DP-006 | HIGH | confirmed | `aggregation_service.py:62`/`:67-71`/`:97` | driven through the real `AggregationService` with a `GraphRead(dimensions=["region"])` and a `FilterRead(name="region")`: `groupby_cols == ['region','region']` and `DuplicateError`. The probe harness is the production function, not a reconstruction. |
| DP-007 | HIGH | confirmed; **evidence transcript defective** (VAL-05-005) | `transformations.py:103`; `data_worker.py:495` | the claim re-derives (six input orders → six distinct stored outcomes); the quoted transcript shows two different datasets and cannot be a reordering. |
| DP-008 | HIGH | confirmed | `transformations.py:94-113`; `data_worker.py:491-516` | re-derived through the worker's own call shape (`groupby=None` when aggregations exist): `head(3)` → `N:6` forward, `S:120` reversed, over identical ten rows. |
| DP-009 | HIGH | confirmed | `models/data.py:126-128`; `aggregate_transforms.py:62`/`:67`/`:74`; `filter_transforms.py:90-91`; `transformation_configs.py:50`/`:84`/`:106` | `TypeError: argument after ** must be a mapping, not YoyConfig` / `not ShareConfig`; `AttributeError: 'CustomMetricConfig' object has no attribute 'get'`; the dict shape succeeds. All three fields are structurally unusable. |
| DP-010 | HIGH | confirmed | `data_worker.py:42-77`; `upload.py:91-123`; `loader.py:166` | reproduced: an `AppException` carrying `ErrorCode.VALIDATION_ERROR` is mapped to `PROCESSING_FAILED` by text; five of six texts classify as `PROCESSING_FAILED`; the `encoding` branch does not match Polars' actual message. |
| DP-011 | MEDIUM | confirmed | `loader.py:122-146`/`:215`/`:234`/`:298`; `data_worker.py:413-416`; `config.py:805-807` | live: a `.csv.gz` whose **compressed** size is 0.00005 MB is read, and `_read_csv_lazy` returns a materialised `pl.DataFrame`, not a `LazyFrame`. |
| DP-012 | MEDIUM | confirmed | `data_worker.py:413`; `loader.py:87`/`:122`/`:253-254`; `models/data.py:278` | live: `CSVLoader().config.max_file_size == 100.0` MB with no configuration supplied. No `MAX_FILE_SIZE_MB` reference exists anywhere under `data/loaders/`. |
| DP-013 | MEDIUM | confirmed | `data_worker.py:420-427`/`:451-469`; `validator.py:134-184` | repository-wide: `validation_result.warnings` has **no consumer in `src/`** — the only three reads of a result are `is_valid` and `errors` at `data_worker.py:426-427`. `_validate_column_types` returns `(errors, warnings)` and only ever appends to `warnings`. |
| DP-014 | MEDIUM | confirmed | `data_worker.py:419-483` | the order validate → decimal → cast → rename → computed → transform holds; the cast guard `col_name in df.columns and col_type != "float"` drops an unmatched key with no `else`. |
| DP-015 | MEDIUM | confirmed | `data_worker.py:312`; `app.py:116`; `db/starter.py:183`/`:188` | `data_worker.py:312` is literally `timedelta(minutes=1)`; `app.py:116` is the sole call site and is not in the periodic loop at `:120-125`. |
| DP-016 | MEDIUM | confirmed; **re-typed, second half** (VAL-05-004) | `data_worker.py:532-534`/`:556`/`:585`/`:588`; `file_cleanup.py:84`/`:89` | `issubclass(asyncio.CancelledError, Exception)` is `False`; MRO `CancelledError -> BaseException -> object`. Both halves confirmed; the process-kill residue is block 3's concern, not reclamation's. |
| DP-017 | MEDIUM | confirmed | `aggregation_service.py:170-176`/`:236`; `aggregated_data.py:64-69`; `aggregated_data_repo.py:128-171` | no `order_by` in `get_by_graph_id`, `get_by_dashboard_id` or `get_dims_values`; `AggregatedData` has only the autoincrement `id`. |
| DP-018 | LOW | confirmed; **re-graded up**, see VAL-05-001 | `aggregation_service.py:84-93`; `enums.py:162-174`; `aggregate_transforms.py:16-27` | live: `median -> {'revenue_median': 10}` and `nonsense -> {'revenue_nonsense': 10}` — a sum under the requested name. The map implements 5 of the enum's 10. |
| DP-019 | LOW | confirmed | `file_cleanup.py:23`/`:46`/`:109`; `db/starter.py:33`/`:183` | repository-wide grep across `src/`: `cleanup_stale_temp_files` has one production caller (`db/starter.py:183`); `cleanup_task_files` and `cleanup_old_processing_logs` have **none**. |

### B. Baseline reconciliation — Appendix A re-derived, not inherited

The input's Appendix A claims every `config.py` / `starter.py` anchor is unchanged across
`8505a62` → `2d23c27` → `c3c0a61`. Independently checked against the working tree and against
`git show 8505a62:src/mkobi/config.py`:

| anchor | input claims at `c3c0a61` | re-derived | value | agrees |
|---|---|---|---|---|
| `UploadSettings.max_file_size_mb` | 286 | 286 | `100` | yes |
| `UploadSettings.lazy_threshold_mb` | 295 | 295 | `10.0` | yes |
| `logs_retention_days` | 407 | 407 | `30` | yes |
| `stale_file_threshold_hours` | 408 | 408 | `24` | yes |
| `stale_processing_timeout_minutes` | 409 | 409 | `30` | yes |
| `stale_processing_cleanup_interval_seconds` | 410 | 410 | `300` | yes |
| `Config.upload_temp_dir` / `allowed_file_types` | 785 / 790 | 785 / 790 | unchanged | yes |
| `Config.max_file_size` | 805 | 805 | `max_file_size_mb * 1024 * 1024` | yes |
| `starter.py` cleanup calls / `def cleanup_old_logs` | 183 / 188 / 402 | 183 / 188 / 402 | unchanged | yes |

`git diff 2d23c27 c3c0a61 -- src/mkobi/db/starter.py` touches one predicate line inside the admin
bootstrap; `git log --stat 8505a62..c3c0a61` shows both commits confined to `config.py` and
`starter.py`. **The reconciliation is sound.** No finding in either report depends on a line number
in either file, and `docs/00-overview/data-flow.md:58`/`:107`/`:112`/`:113` — cited by DP-004, DP-009
and DP-001 — all resolve verbatim against the working tree.

One caveat, recorded so a later run does not mistake it for drift in the input's table: the
remediation team left `config.py` dirty again (`is_weak_admin_password`, +60/-11) while this report
was written, which moves every anchor in that file below line 78 up by roughly 48 — `max_file_size_mb`
from 286 to 334, `logs_retention_days` from 407 to 455, `Config.max_file_size` from 805 to 854. The
values are identical in both states. Appendix A's `config.py` rows are therefore correct **at
`c3c0a61`**, the baseline both reports name, and the input did not need to track a tree that was
clean when it handed off. Phase 05 cites `config.py` only for the values its settings produce
(`max_file_size_mb * 1024 * 1024` at DP-011/DP-012, the three retention defaults at DP-015) and
never for a line number, so no finding moves.

### C. Seam rulings — contested and adjacent claims

Phase 03 (`TXN-001..TXN-012`) was filed immediately before this phase and overlaps two of this
phase's findings. Its own validation report has already recorded both merges; this is the reciprocal
ruling, from the phase that owns the concern. Neither identifier is renumbered, and nothing is written
into `.ai/audit/03-db-concurrency/`.

| contested | rival claim | phase that owns it | ruling |
|---|---|---|---|
| DP-001 | **TXN-002** (CRITICAL) — "the enqueue/commit handoff claims atomicity and has none, so a completed job can be recorded as never started" | 05 | **Same root cause; merge into DP-001.** Both name the same root: the queue submission sits outside the transaction that commits the status row, and `_update_processing_log_status` never checks `rowcount`, so the consumer's writes match zero rows. TXN-002 adds a distinct *reachability* proof (the producer's uncommitted insert is invisible to the consumer because `Queue.put()` releases it at an await point) that DP-001's reproduction does not make; keep that paragraph as corroboration under DP-001. DP-001's edge (commit **fails** after a successful enqueue) is not stated in TXN-002 and is DP-001's alone. **One remediation, in phase 05's area.** |
| DP-004 | **TXN-004** (HIGH) — "an upload that produces no aggregate rows wipes the dashboard's filter values while leaving its old chart rows in place" | 05 | **Same root cause; merge into DP-004.** Identical mechanism (`manager.py:97` early return before `:113`) and identical consequence. The only difference is entry point: TXN-004 reached it by changing `graphs.metrics`, DP-004 by uploading a non-matching column set. Both were reproduced independently here through the real `_store_aggregates`. **One remediation, in phase 05's area.** |
| DP-001 | **TXN-001** (CRITICAL) — sessions yield without commit/rollback; three of four `UserService` writes do not end their own unit of work | 03 | **Adjacency, not merge.** TXN-001's subject is the *session lifecycle contract* for API write paths (`db/session.py:70-88`, `api/deps.py:101-116`, `UserService`). DP-001's subject is one function's *internal effect ordering*. Re-derived and consistent: `get_db_dependency` yields a session that never commits (`api/deps.py:115-116`), `process_upload_with_session` ends its own unit with its own `commit()` at `:271`, and `UserService`'s write methods carry exactly one `await db.commit()` (at `:320`) across four write methods. Same class of defect, different owner, cross-reference only. |
| DP-001 / DP-016 | **TXN-003** (CRITICAL) — the whole run is one transaction, so `processing` is never committed and the 30-minute stale backstop can never fire | 03 | **Adjacency, not merge.** TXN-003 is about the *worker's* transaction scope and the reachability of a recovery sweep; DP-001 is about the *producer's* commit failing after an enqueue. They meet at one line — `_update_processing_log_status` never checks `rowcount` — but the consequence differs (an unattributable dashboard rewrite versus an unrunnable recovery path). Cross-reference from both; remediate the `rowcount` check once, in DP-001's step. |
| DP-004 | **TOPO-001** / phase 01 — inert `rq-worker`, unreachable `FAILED` write, unguarded store drop | 01 | **Adjacent, already filed elsewhere, not contested.** Phase 01's seam was declared and is not duplicated here. The only contact with DP-004 is that a cleanup sweep cannot reclaim what an empty selection leaves; no shared root cause. |
| DP-012 | **CFG-002..CFG-010** / phase 02 — config and secrets | 02 | **Adjacency, not merge.** DP-012 is a code literal inside `LoaderConfig` (`models/data.py:278`) that the environment cannot move; phase 02's surface is environment and compose configuration. The input states this boundary explicitly at DP-012 and does not contest it. |
| DP-017 | phase 14 — schema and migrations | 14 | **Adjacency, declared.** DP-017's *defect* (order never pinned) is 05's; its *remedy* (`ordinal` column, `ORDER BY`) is an Alembic change and phase 14 runs later and owns the DDL surface. Recorded, not contested. |

**Seam check on this input — findings filed outside its declared scope.** One: **DP-016's second
half** is a unit-of-atomicity defect filed under the reclamation block, and is re-typed in
VAL-05-004. No other audited finding leaves its own declared zone: all nineteen `Zone` fields are
verbatim block titles (5 determinism, 4 configuration reach, 3 cleanup, 2 admission, 2 replacement,
1 classification, 1 atomicity, 1 validation), which is the template's zone rule satisfied.

### D. Recommendation executability

Every recommendation was checked for a resolvable target and for what it disturbs. All nineteen
resolve; three carry a named test blocker and three name a consumer that changes with the fix.

| finding | target resolves | depends on | breaks / disturbs |
|---|---|---|---|
| DP-001 | `process_upload_with_session`, `data_worker.py:209-222` | moving the commit ahead of the move and the enqueue | `tests/test_upload_api.py`, `tests/test_file_processing.py` assert enqueue-before-commit — named in the finding |
| DP-002 / DP-018 | `data_worker.py:694`/`:772`, `aggregation_service.py:84-93` | DP-018 must ship in the same commit | every stored metric key changes on dashboards configured for a non-sum function |
| DP-003 | `_coerce_dim_value`, the conflict target in `manager.py` | a canonicalisation rule stated in `docs/09-database/schema-core.md` | stored row counts change with no record of which pairs were split |
| DP-004 | `manager.py:97` vs `:113` | the agreed `failed` status text | turns a silent no-op into a visible failed run; frontend `failed` rendering |
| DP-005 | `save_filter_values` | one `str()`; four dtype tests | `filter_values_service.py` must still receive strings |
| DP-006 | `aggregation_service.py:67-71` | `dict.fromkeys` | none; additive |
| DP-007 | `transformations.py:103` **and** `aggregate_transforms.py:80-107` | a decision on what `groupby`-alone means | both entry points reach the same expression |
| DP-008 | `transformations.py:94-113` **or** `_validate_processing_config` | a decision on `limit` without `sort_by` | either reorders the pipeline or fails previously-succeeding runs |
| DP-009 | three call sites in `aggregate_transforms.py:62`/`:67`/`:74` | `model_dump(exclude_none=True)`; plus `_calculate_yoy`'s own `group_cols` defect | newly-reachable path; three currently-unreachable fields |
| DP-010 | `_map_processing_error_to_code`, `loader.py:166` | six `(exception, expected code)` test rows | error codes change for existing failure classes |
| DP-011 / DP-012 | `data_worker.py:413`, `loader.py:215` | deleting a branch **or** keeping it; one owner per ceiling | the two fixes must land together to avoid two ceilings |
| DP-013 | `data_worker.py:426-427`, `:540` | extending `ProcessingStatusResponse` **or** summarising into `message` (`String(1000)`) | a new status value is a frontend change; message-only is not |
| DP-014 | the ordering at `data_worker.py:419-483`; `models/transformation_configs.py:133` as the `extra="forbid"` precedent | the storage-boundary model | unknown settings keys change from silently ignored to 422 — check `PUT /processing-configs/{id}` callers |
| DP-015 / DP-016 / DP-019 | `app.py:116`/`:120-125`, `data_worker.py:532`/`:556`/`:588`, `file_cleanup.py` | a byte ceiling on the sweep | `tests/test_file_cleanup.py` covers all three helpers and follows whichever way DP-019 goes |

### E. The vacuous-control angle, applied to this input's evidence

Three controls in this input were checked for existence, declared scope, and what they actually
examined — a control that ran and reported clean substantiates nothing.

- **Nine executed probes (declared in the Summary).** Exist, and eight of the nine were independently
  re-derived here. The ninth is DP-007's, and it examined a reordering it did not perform
  (VAL-05-005). Scope declared as covering "the accepted-upload path"; actually reached: five distinct
  claims (DP-001, DP-003, DP-004, DP-005, DP-006), all confirmed, plus DP-008, DP-009, DP-010,
  DP-011, DP-018 re-derived here.
- **Appendix A's reconciliation.** Exists, declares its scope as the two concurrently-edited files,
  and examined exactly those two. It decided correctly on all ten anchors (§B). Not vacuous.
- **Block 7 (caller-supplied expressions).** Declared scope: two expression grammars; the input states
  the limits are "enforced at compile time, in one place" and files **no finding**. A control green
  over a real examination, not over zero items: Appendix H records a measured
  `ColumnNotFoundError` for `revenue / cost` and an argument for why no expression resolves by
  timing. This is the one block where filing nothing is the correct outcome, and it is argued rather
  than asserted.

### F. What the input rests on, and what it does not

Every substantive finding in this input arrives from an angle its ten declared blocks name — there is
no finding here from an unnamed angle, which is worth recording as the phase behaving as declared.
The support is split: thirteen findings rest on an executed probe or a static chain read end to end
(DP-001, DP-002, DP-003, DP-004, DP-005, DP-006, DP-007, DP-008, DP-009, DP-010, DP-011, DP-012,
DP-013), four rest on static reading alone (DP-014, DP-015, DP-016, DP-017), and two are repository
greps (DP-018, DP-019). No finding rests on the input's own declared block list or its own summary
alone. The two that rest on documentation (`data-flow.md:113` for DP-001, `:58`/`:107` for DP-004)
use the documentation as the *contradicted* artefact, with the executing path as the evidence — the
correct direction, and both documentation lines resolve verbatim.

### G. Coverage ledger

| block | items examined | claims left unsettled | reason |
|---|---|---|---|
| 1. The claim re-derived from the executing path | 19 of 19 | 0 | all anchors resolved; every anchor cited by the input still names the symbol it claims |
| 2. The vacuous-control angle and its bindings | 3 controls | 0 | DP-007's probe examined a reordering it did not perform — recorded as VAL-05-005, a transcript defect, not an unrun control |
| 3. The grade against the audited rubric | 4 bands carried, 3 corrected | 0 | DP-002 and DP-005 re-graded; DP-018 re-graded up; DP-001 and DP-004 confirmed at their bands |
| 4. Which side moves: code or documentation | 5 documentation-contradicting citations | 0 | every cited documentation line resolves; no finding required a doc fix to be correct |
| 5. Whether the recommendation can be carried out | 19 of 19 | 0 | every target resolves; three name test blockers, three name affected consumers |
| 6. Cross-phase conflict, ownership and merge | 7 contested/adjacent claims | 0 | 2 merges (TXN-002→DP-001, TXN-004→DP-004), 3 adjacencies (TXN-001, TXN-003, phase 14), 2 already-seamed (TOPO-001, CFG-002..010) |
| 7. Finding-ID namespace integrity | 1 prefix (`DP-`), 1 validation prefix (`VAL-05-`) | 0 | `VAL-` flat is occupied by phases 01–02; no in-source markers exist to migrate |
| 8. The shared findings template as a controlled artefact | 6 front-matter fields, 5 per-finding fields, zone rule, empty-state | 1 | the empty state does not apply (19 findings); every per-finding field present in all 19 |
| 9. Does the input rest on its own declared blocks | 19 findings | 0 | all thirteen probed findings re-derived independently; no finding from an unnamed angle |
| 10. The validated report as an artefact | 19 dispositions, 5 validation findings | 0 | tally agrees with per-finding verdicts: 15 confirmed + 2 re-graded + 2 merged = 19, 0 rejected, 0 unsettled |
| 11. The shared angles, defined once and bound by name | 2 angles | 0 | this phase binds neither vacuous-control nor cross-resource side-effect in its own words; no angle is cited without a definition |

**Not settled in this environment, and why.** Three items the input also could not settle, carried
forward rather than silently confirmed: a real end-to-end HTTP upload was not driven (the dev stack is
under other agents' control), so DP-001's residue composition — aggregates replaced with no status row
— is established by reading `_store_aggregates` under the same transaction, not by observing a second
write; `libmagic` raises `ImportError` at import on this host, so `file_processing.py`'s MIME branch
was reviewed statically in both its forms rather than executed; and no 24-hour or 30-minute clock was
waited out, so DP-015 and DP-016's timing consequences rest on the code and on Python's exception
hierarchy. All three are recorded in the input's own Appendix J and are re-confirmed here rather than
inherited. Additionally, one aggregate-observation caveat applies to this run as well: every
aggregate-storage observation is single-writer, because concurrent-upsert semantics are phase 03's
angle, not this phase's.

**Hygiene.** Every live probe ran against the throwaway test database (`bidb_test`, port 5434) inside
a transaction that was rolled back, or committed one synthetic dashboard and deleted it on the way out
(probe-created rows remaining: 0 — one `val05-` graph row survived the rolled-back aggregate probe
and was deleted explicitly, verified afterwards). Two throwaway temp directories, one throwaway gzip
directory and four in-process queue entries created by the DP-001 probe were removed; the probe's
`upload_temp_dir` property override was confined to its own process. No container was started,
stopped or reconfigured; no Redis key was written; the dev stack was not touched. The untracked
`probe_upload.csv` at repo root was left alone, and nothing in the repository was edited, staged,
committed, reverted or stashed — the only file this run wrote is this report.
