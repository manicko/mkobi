# Fit Analysis — Batch B (phases 05, 06, 07, 08)

Analysis artefact. Nothing in `.kilo/commands/audit/phases/` was modified (verified by mtime). Read
with `.kilo/researches/phase-set-conventions-analysis.md` (FM1–FM14) and
`.kilo/researches/llm-audit-task-spec-design.md` §2–7 (binding: B1–B14, D1–D11, C1–C9, RC1–RC7,
AP1–AP19).

**Target numbering** (the set the orchestrator will run): 01 process-architecture · 02
configuration-secrets · 03 db-concurrency · 04 authentication · 05 data-pipeline · 06
file-artifacts · 07 external-boundary · 08 code-quality · 09 test-coverage · 10 production-ops · 11
performance · 12 authorization · 13 client-tier · 14 schema-migrations · 15 security-baseline · 99
validate.

**Prefix namespace as it stands** (grep-verified): `ENT-` `CFG-` `DB-` `AUT-` `DP-` `MED-` `EXT-`
`QLT-` `TST-` `OPS-` `PERF-` `AUTZ-` `FE-` `SEC-` `VAL-`; archived `AD-` `PII-` `SRH-` `I18N-`.
**Live collision to report:** 03 and 14 both claim `DB-`. Not this batch's file, but 99's namespace
block will file it; the 14 batch should be told before it writes.

**Orchestrator derivation, confirmed** (`audit-multi-phase.md` §2.1): `NN-audit-name.md` →
`.ai/audit/NN-name/findings.md`. Every file below therefore carries `name: NN-name`, matching the
stem after `NN-audit-`.

---

# 1. `05-audit-data-pipeline.md`

## 1.1 Current state

Legacy M-family sweep: six mandated runtime steps, then five check tables (25 affirmative rows)
scored against them. The zone summary is accurate; the shape is the family's.

- **Block count: 0 `## Audit Blocks`** — 6 steps (`### Step R1`–`R6`) + 5 dimensions, 170 lines.
- **Frontmatter mismatch:** `name: 07-data-processing` vs stem `05-audit-data-pipeline`; Report
  Output writes `.ai/audit/07-data-processing/findings.md`. AP12/FM12 complete: wrong number, wrong
  stem, output directory matching neither.
- **Violations:** `## Output Mode` incl. the counterfactual *"If `problems-only: false` were set,
  you would produce a full report"* (AP9); `## Discovery Stage`; `## Mandatory Runtime Verification`
  — *"Before evaluating any checklist item, you MUST complete these steps"* (AP1); every
  `**Evidence required:**` cites a step number (AP4); no `Scope Boundaries` (AP8); CRITICAL inside
  step prose (AP11); 25 rows phrased as affirmations (AP7).
- **Value:** the only phase owning ingestion. Expect full replacement, not repair.

## 1.2 Premise audit — per step and per dimension

| # | Unit | Verdict | Notes |
|---|---|---|---|
| R1 | Trace the Full Data Pipeline in Code | **TRUE, framing wrong** | The chain exists: route → admission → service → validation → rename + status row + enqueue → worker → parse → validate → cast/rename/computed → transform → per-chart aggregate → store → list rebuild. R1's *method* ("Follow the call chain") must go (AP15). |
| R2 | Verify Resource Cleanup | **TRUE** | A temp file is created under a per-user data dir, renamed to its log identifier, deleted by the consumer on success and on error, then reaped by an age-bounded startup sweep and a per-task delete. "Verify cleanup runs even when processing fails" is the right question, asked generically. |
| R3 | Verify Transactional Boundaries | **ADAPTABLE + partial DUPLICATE** | Two questions are fused. *"All writes in a single transaction"* is 03 block 2. The uncovered half: the **file** and the **enqueue** are not in the transaction at all — rename before commit, compensating unlink on enqueue failure, enqueue before commit. "Which resource is the real unit of atomicity" is 05's; transaction shape is 03's. |
| R4 | Determine Processing Determinism | **TRUE — strongest surviving block** | Live instances: the upsert conflict key is a *text cast* of a document column, so key normalisation decides update-vs-duplicate; `first`/`last` aggregates and a base grouping taking `pl.all().first()`; a year-over-year derived from a positional shift over a sorted frame; float arithmetic; a `<column>_<fn>` metric-naming convention; an unknown function silently falling back to `sum`. R4's own list — *"random values, current timestamp, unordered collections (sets, dicts before Python 3.7)"* — is boilerplate that finds nothing. |
| R5 | Verify Recalculation Completeness | **TRUE** | Overwrite clears by dashboard then bulk-inserts; append upserts on the conflict key. Two stale-data paths R5 cannot reach: the store step returns early when a dashboard has no configured charts, leaving prior rows in place while the task is marked complete; and the per-dimension filter-value list is rebuilt from a *different source* in the two modes. |
| R6 | Test Error Paths with Invalid Input | **ADAPTABLE** | Validation is three vocabularies (declared name, content-derived type, byte budget), with a sniffing branch that degrades to a heuristic when the sniffer is absent. *"Meaningful error is returned to the user"* undersells it: outcome classification is **substring-matching exception text** in two independent places, so a library message change silently re-routes a failure class. |
| D1 | Pipeline Correctness | **ADAPTABLE / partly DUPLICATE** | Rows 1–2 → chain block; row 4 → determinism; row 5 *"Output stored atomically"* → 03; row 6 *"fails fast on invalid data"* → frame-validation block. |
| D2 | Resource Management | **ADAPTABLE** | The file is streamed in fixed-size chunks to disk, then materialised whole as an in-memory frame; writes go out in fixed-size batches. *"No resource leaks in async context"* is 03/11 — a claim about the bridge, not the pipeline. |
| D3 | Atomicity & Consistency | **DUPLICATE → 03** | Transaction boundary, rollback, partial-visibility and upsert idempotency are 03 blocks 2–5. Remove from 05. |
| D4 | Configuration-Driven Processing | **TRUE, under-owned today** | The per-dashboard configuration is a free-form document read through a splat into a model, so an unknown or renamed key surfaces as a worker failure *after* the upload was accepted; a named column absent from the loaded frame is **skipped with a warning**, and a skipped aggregation still yields a successful run. No phase currently asks this. |
| D5 | Background Task Safety | **FALSE PREMISE in part** | The asserted machine *"STARTED → PROCESSING → SUCCESS/FAILED"* does not exist; the shipped vocabulary is `STARTED, UPLOADED, PROCESSING, COMPLETED, FAILED`, with a startup sweep rewriting `UPLOADED` and a periodic sweep rewriting `PROCESSING` to `FAILED`. There is also no durable queue on the request path — work goes to a process-local queue drained inside the web process, while a separate queue-worker service exists in the compose file. *"Users can check task outcome"* is 05's; *"failures logged with context"* is 10's. |

## 1.3 Proposed final block set — 10 blocks

1. **Ingestion admission: which limits exist, which layer enforces each, and what one input can
   pin.** *Derive the limit inventory from the accepting path — declared size, content-derived type,
   name extension, a cumulative byte budget enforced during the transfer — and per limit establish
   the enforcing layer, how many places declare its value, whether a limit declared in one process is
   consulted in another, and what a single admitted input holds in memory.* Evidence: per limit —
   enforcing layer, declaration sites, divergence; one limit nothing consults.
2. **The state of an accepted upload: every transition the executing path can produce, and who writes
   it.** *Establish the state vocabulary actually in use, then per state its writers — accepting
   process, consumer, separate worker, each recovery sweep. A state no committed row ever holds while
   a consumer branches on it is a finding; so is a writer that reaches a state its peers cannot.*
   Evidence: the state inventory with a per-writer verdict; one state a sweep rewrites and a consumer
   also writes.
3. **The unit of atomicity: what commits together, and what a rollback leaves behind.** *Enumerate
   every side effect the accepting path produces — stored file, status row, queued work, derived rows
   — and establish which share a commit and which are reconciled only by compensation; then confirm or
   refute all-or-nothing by inducing a failure between the first and last effect. Transaction shape,
   lock semantics and pool behaviour are 03's.* Evidence: the effect inventory with a
   shared-commit / compensated verdict per effect; one induced mid-sequence failure.
4. **Determinism of the aggregate: what makes identical input produce a different stored row.**
   *Derive the aggregate's identity — the column set deciding whether a new row updates an existing
   one — and establish what normalisation it depends on and whether two value-equal inputs can be
   unequal in it; then establish which configured aggregates depend on row order rather than data,
   which derived measures depend on an ordering the code imposes but does not pin, and which stored
   measure names depend on a function chosen elsewhere. A re-upload producing a second row set beside
   the first is a finding.* Evidence: the identity derivation with the normalisation it needs; one
   value-equal, identity-unequal pair; one aggregate whose result changes with row order.
5. **Replacement semantics: what an overwrite and an append each remove, and what neither removes.**
   *Establish, per write mode, the selection removed, the rows written, and the selection untouched —
   a dashboard with no configured charts, a chart since removed, a dimension absent from the incoming
   data — then establish the secondary list rebuilt alongside and the source each mode reads to build
   it.* Evidence: per mode, the selection removed and the selection left; one configuration causing a
   completed run to leave stale rows; the list rebuilt from a different source in each mode.
6. **Configuration reach: which parts of a stored processing configuration are honoured, which are
   skipped, and which fail the run late.** *Derive the configuration's field set from what the
   executing path reads, and per field establish whether an absent, unknown or malformed value is
   honoured, silently skipped, or late-failing; separately establish whether the document is validated
   at the boundary that accepts it or only later in another process, and whether a renamed field is a
   failure or a silent no-op. A field skipped with a warning while the run reports success is a
   finding.* Evidence: the field inventory with an honoured / skipped / late-failure verdict; the point
   at which an invalid document is first rejected.
7. **Caller-supplied expressions: what a stored formula may name and what it may compute.** *Establish
   the two expression grammars accepted from a stored configuration — an arithmetic grammar over named
   columns and a narrower grammar over a named column's date parts — and per grammar which identifiers
   and functions it admits, what a name matching no column does, and where its limits are enforced: at
   arrival or at compilation.* Evidence: the grammar inventory with the limits enforced at each point;
   one identifier admitted by the grammar and absent from the column store.
8. **Failure classification: how an outcome is categorised, and what each category reaches.**
   *Establish where an exception becomes a machine-readable class, whether by type or by inspecting its
   text, how many places do it independently, and whether the two agree for the same failure.*
   Evidence: the classification sites with the signal each inspects; one failure text the two classify
   differently.
9. **Validation of the loaded frame: what is refused, what is only warned, and whether a warning is
   stored anyway.** *Establish the checks the frame validator runs and, per check, whether a failure
   ends the run or merely annotates it; include the checks that run only when a caller supplies the
   expected shape. An annotation discarded while its rows are kept is a finding.* Evidence: the check
   inventory with a refuse / annotate verdict; one check that only runs when a caller supplies the
   shape.
10. **Cleanup and recovery: what reclaims an abandoned accepted input, in which process, on which
    clock, and what it cannot reach.** *Establish the reclamation set — per-task deletion, an
    age-bounded sweep, a retention sweep over status rows — and per sweep which process runs it, what
    it selects, which clock it reads, whether the bound is on age, count or bytes, and what it
    excludes; then establish the window in which a completed status row outlives the file it names.*
    Evidence: the sweep inventory with a bound-kind verdict per sweep; one row whose file the sweeps
    can remove first.

**REMOVED:** the six steps as procedures (AP1 — deleted wholesale per Ex. 4; what they protected is
restated above). The five check tables (AP7). D3 in full (→ 03). D5's state machine (false premise;
replaced by block 2).
**NOT ADDED — deliberate C6 decision:** a "declared pipeline contracts versus the code" block. That
angle already exists in 06, 07, 10 and 12; 08 owns it (see §4.3). A fifth copy is the set's live
defect.

## 1.4 Scope Boundaries paragraph

> **Scope Boundaries** — owned here: what an upload is admitted against, what state it is in, what is
> derived from it, what is written, what each write mode replaces, what reclaims an abandoned upload,
> and how a failure is classified. Not owned here: settings values, the file-age and retention
> thresholds, and the queue-broker configuration (02); transaction, lock and pooler semantics, and the
> thread-bridge mechanism (03); identity and acceptance of the caller's credential (04); artefact
> naming, residence, store-versus-record reconciliation and the served interface bundle (06); the
> inbound surface form, the transport-level body bound and dependency-failure degradation (07);
> fixed-value discipline, boundary-model strictness and the declared-contract angle (08); test
> adequacy (09); container, gate, edge and observability posture (10); measured cost per input (11);
> the access decision for an upload or a read (12); the client-side upload experience (13); the
> schema chain and index inventory (14); header, origin and rate-limit *policy* (15). Deliberately
> asymmetric depth between the accepting path and the consumer is not a defect on its own; report it
> only where the code's own documentation misstates it.

## 1.5 Finding-ID prefix

**Keep `DP-`** — already in use from a prior cycle, matches the new stem, and renaming orphans every
identifier already minted. Unique across the live set.

```
## Report Output
- Findings path: `.ai/audit/05-data-pipeline/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `DP-` — check for a collision before minting an ID; a shipped test, comment or report may already carry one from a prior cycle, and report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting current behaviour is a remediation blocker, not a gate
```

---

# 2. `06-audit-file-artifacts.md`

## 2.1 Current state

Modern B-family, 11 blocks, 140 lines. Purpose: *"Audits the media path end to end: what an incoming
image is admitted against, where its bytes are written and under what key, what is derived from them,
what the serving path hands out and on whose word…"* — the best-written file in the batch, and written
about a system that does not exist here.

- **Block count: 11.** `name: 07-media` vs stem `06-audit-file-artifacts`; findings path
  `.ai/audit/07-media/findings.md`; prefix `MED-`.
- **Stale Scope Boundaries:** names (03)(05)(06)(07)(08)(09)(10)(11)(12)(15); of those only 03, 10, 11,
  12, 15 mean the same after renumbering. Block 9 also **refers to itself as "06"** — correct only in
  the old numbering.
- **What is genuinely here:** an accepted tabular file; its residence in a per-user data directory; an
  age-bounded sweep; three independent directory globs over the same space; a per-status-row retention
  sweep; a one-time secret held in a shared cache outside the database; and the built interface bundle
  served from disk by the backend. A real, coherent zone — the structure survives, about half the
  blocks do not.

## 2.2 Premise audit — per block

| # | Block | Verdict | Notes |
|---|---|---|---|
| 1 | Storage-key ownership and what a removal actually guarantees | **ADAPTABLE** | The shared-key half is a **false premise** — no key is shared; each accepted file has exactly one owning status row. The surviving half is stronger than the original: the file is named after its row's identifier, no referential relationship exists from file to row, and *"what duplicating a listing does to the others"* becomes "what removes the file when the naming row is rolled back". |
| 2 | Ingestion admission | **ADAPTABLE — transfers to 05** | *"payload size, pixel dimensions, decode budget, per-ad item count"* → byte budget, derived type, name extension, per-dashboard count. Applicable, but 05 block 1 owns the admission vocabulary. What stays here is what happens to the bytes *after* admission. |
| 3 | Metadata removal: which layer strips, and what the re-encode changes | **FALSE PREMISE** | *"hidden metadata"*, *"a full re-encode changes pixels, compression and colour handling"*, *"derived set"*. Tabular uploads carry no embedded metadata and nothing is re-encoded. **Replacement angle:** file *identity* — the client-supplied name versus the content-derived type versus the extension that decides the parse dialect, and the branch taken when content cannot be sniffed. New block 1. |
| 4 | Derived-file generation: atomicity, partial sets, whether repair reaches them | **ADAPTABLE — transfers to 05** | No derived files exist. The derived artefact is a set of stored rows materialised inside a transaction, so "written one member at a time" is answered by the commit boundary — 05 block 3. Its best sentence, *"a record naming a derived file that was never written"*, is real: a status row can be `COMPLETED` while no artefact of it remains, deliberately. Counter-case moves to new block 8. |
| 5 | The serving gate: which predicates it consults, and both directions of failure | **ADAPTABLE, mostly DUPLICATE → 12** | *"which predicates it consults"* is the access decision, which 12 owns and which this block half-concedes. **The irreducible 06 question is a different one, answerable in a sentence: no accepted file is ever served back to any caller** — yet code reads one from disk to answer a status query. |
| 6 | Exposure of this path relative to the paths served beside it | **DUPLICATE → 10, 15** | The block's own text hands *"transport and header policy"* away and confines itself to a documented control absent from the shipped configuration — 10's block 3 and 15's header angle, both better homes. Remove. |
| 7 | Reconciliation between the store and the records, both directions, and what is exempt | **ADAPTABLE — best block in the file; keep nearly intact** | Both directions exist and are unmonitored: a file no row names (rename succeeded, enqueue failed, compensating delete raced) and a row naming a file that is not there. The live instance is two independent age bounds — a file-age sweep and a status-row retention sweep on different clocks — so a file can go while its completed row is still inside the retention window. *"difference-based tooling is one-sided by default"* survives verbatim and is the block's best sentence. |
| 8 | Capacity of the in-flight area: arrival rate against residence time | **ADAPTABLE — merges into block 2** | *"a time bound does not bound a rate, and a count per flow does not bound bytes"* applies unchanged: the reclamation bound is on file age, not concurrent files or total bytes. *"whether the area shares storage whose exhaustion stops something wider than one upload"* is stronger here than assumed — the served bundle lives on the same filesystem. Merge; do not keep separately. |
| 9 | Removal granularity, and the record of a removal that failed | **ADAPTABLE** | *"What triggers an erasure, and what an account's state means, is 06's"* is now self-referential: the trigger is 12's and 15's, the mechanics 06's. The surviving question is intact and unowned — deletion is best-effort, its failure is logged and never read: no operator surface, no counter, no alert. Natural home for the one-time credential artefact. |
| 10 | Declared media contracts against what the code does | **DUPLICATE → 08 (C6)** | The fourth copy of the declared-contract angle (06, 07, 10, 12, 13). 08 owns it. The irreducible piece — three independent globs over one directory must agree on the naming scheme and nothing enforces that they do — folds into new block 3. Remove. |
| 11 | Cross-process coordination over the shared store | **ADAPTABLE — keep** | The accepting process creates and renames; the in-process consumer deletes; a separate worker may run the same job; a startup sweep in whichever process boots first deletes by age. Nothing is mutually excluded; the age rule is the only exclusion. *"finds its source already absent: is the failure silent"* translates exactly to a second deleter meeting an already-removed artefact. |

**NEW — two zones with no owner anywhere in the set.**
**(a) A one-time secret held outside the database.** A generated temporary credential is written to a
shared cache under a caller-supplied token with a time-to-live, read back through an administrative
endpoint, deleted on read via an atomic read-and-delete. It is stored in cleartext, its creation fails
*open* (error logged, operation continues), and its retention bound is a literal in a constructor
signature rather than a configured value. 04 owns the token machinery, 12 owns who may read it;
neither owns the artefact's lifetime.
**(b) The built interface bundle as a served artefact.** The backend mounts a build output directory
with a catch-all fallback, but only when the directory and its entry document both exist; when they do
not, the process's route table is different and it silently serves no interface. The health probe
reports this as a component status using a path relative to whatever the process's working directory
is. Nobody owns it: 10 owns container posture, 13 owns the client *code*.

## 2.3 Proposed final block set — 8 blocks

1. **The accepted artefact's identity: what it is called, what its name claims, and what its bytes
   are.** *Establish the three identities an accepted artefact carries — the name the caller supplied,
   the name it is stored under, the type derived from its content — and per artefact which of the
   three decides how it is later read; establish the branch taken when content cannot be derived, and
   what that branch accepts.* Evidence: the three-identity inventory with a deciding-identity verdict;
   one artefact whose name and content disagree and what each downstream decision followed.
2. **Residence of an accepted artefact, and what bounds it.** *Establish what limits arrival, what
   reclaims an abandoned artefact, and for each bound whether it is on time, count or bytes — a time
   bound does not bound a rate, and a count per caller does not bound bytes; establish where the
   in-flight area lives and what else shares the storage whose exhaustion stops something wider than
   one upload.* Evidence: the control inventory with each control classified by what it actually
   bounds; the shared-storage consequence of exhausting the area.
3. **Reconciliation between stored artefacts and stored records, in both directions, and what is
   exempt.** *Compute the difference in both directions — an artefact no record names, and, state
   this explicitly because difference-based tooling is one-sided by default, a record naming an
   artefact that is not there — and per direction establish whether anything detects it, whether
   anything repairs it, and every excluded part of the area and why; establish the naming rule each
   component reading the area independently relies on and whether the rules agree. Detection and
   repair are this block's; whether the access decision should notice is 12's.* Evidence: both
   directions with a per-direction detector and repair verdict; the excluded subtrees with their
   reason; two components that select by name and do not agree.
4. **Removal of an artefact, and the record of a removal that failed.** *Establish per audience which
   removal operations exist, whether one artefact can be removed without destroying the record naming
   it, and whether the collection is append-only by construction; then establish whether a failed
   removal is recorded, what reads that record, how long it is kept, and whether an operator can see
   it.* Evidence: per audience, the removal operations that exist; the failure record's readers,
   retention and alerting.
5. **A one-time secret held outside the database: how it is created, how long it lives, what removes
   it, and who can read it.** *Establish the artefact's whole lifetime — who generates it, from what
   source, under what key, for how long, what deletes it before its expiry, and what happens when the
   holding store is unavailable at each of those points; specifically, whether a failure to *create*
   leaves the caller believing one exists, and whether a failure to *read* is distinguishable from one
   that never existed. Credential strength is 04's; release authorisation is 12's; the lifetime is
   this phase's.* Evidence: the lifetime inventory with a bound per stage; one failure in which the
   caller is told a secret exists and it does not.
6. **The built interface bundle as a served artefact: what is served from disk, and what changes when
   it is absent.** *Establish what the serving path reads, under what condition it registers at all,
   what a request for an unmatched path receives, and which component's presence changes the route
   table rather than only its content; establish what an observer is told when it is missing.*
   Cross-origin and header policy are 15's and 10's; the component's own code is 13's. Evidence: the
   serving inventory with a present/absent verdict per path class; one request decided by a
   component's presence rather than by the request.
7. **Which process reclaims an artefact, and what two of them doing it at once produces.** *Establish
   which long-lived processes read, create and remove artefacts and per operation whether it is
   mutually excluded and by what; ask what a second remover meeting an already-removed artefact
   produces — a silent no-op, a logged error, or a raised failure a caller sees — and whether a
   removal can race a consumer that has not yet read what it is about to remove. Locking mechanics
   and repeat-run safety are 03's.* Evidence: the process-by-operation matrix with a mutual-exclusion
   verdict per operation; one operation whose second failure mode is silent.
8. **Whether an accepted artefact is ever returned to a caller, and which code assumes it is.**
   *Establish whether any accepted artefact leaves the system again and which components still read
   one from storage to answer a request; for each, what it concludes when the artefact is absent, and
   whether the caller can distinguish that from processing not yet finished.* Evidence: the
   returning-surface inventory, empty or not; one component whose absent-artefact answer is
   indistinguishable from a pending one.

**REMOVED:** old 3 (metadata/re-encode — false premise, no such machinery) · old 4 (derived files →
05; counter-case retained in new block 8) · old 6 (→ 10, 15) · old 10 (→ 08).
**MERGED:** old 8 into new 2; old 2's admission half into 05.

## 2.4 Scope Boundaries paragraph

> **Scope Boundaries** — owned here: what a stored artefact *is* — an accepted upload, a one-time
> secret, the built interface bundle — how each is named, how long it lives, what reclaims it, how
> store and records are reconciled in both directions, and which process does the reclaiming. Not owned
> here: settings values, the file-age and retention thresholds, and the shared-cache configuration
> (02); transaction, lock and pooler semantics, and sweep repeat-run safety (03); credential strength,
> issuance and the claim guards (04); what is derived from an upload, what is written, and what each
> write mode replaces (05); the inbound surface form and the transport-level body bound (07);
> fixed-value discipline and the declared-contract angle (08); test adequacy (09); container, gate,
> edge, certificate and backup posture, and header policy as a shipped configuration (10); measured
> storage and throughput cost (11); the access decision for an artefact or a status query (12); the
> interface's component and state architecture (13); the schema chain (14); header, origin and
> credential *policy* (15). An artefact that exists in one process and not another is not a defect on
> its own; report it only where the code's own documentation misstates it.

## 2.5 Finding-ID prefix

**`ART-`.** `MED-` names machinery that does not exist here, and no prior-cycle `MED-` identifier is
recorded in the file or in shipped source — the only "media" token in the repository is a *dashboard
name* in a development seeder, which mints no identifiers. `ART-` is unused across live and archived
sets. The collision clause is retained; same check, no cost.

```
## Report Output
- Findings path: `.ai/audit/06-file-artifacts/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `ART-` — check for a collision before minting an ID; a shipped test, comment or report may already carry one from a prior cycle, and report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting current behaviour is a remediation blocker, not a gate
```

---

# 3. `07-audit-external-boundary.md`

## 3.1 Current state

Modern B-family, 12 blocks, 137 lines. Purpose: outbound third-party calls plus the public inbound
surface. `name: 09-external-api` vs stem `07-audit-external-boundary`; prefix `EXT-`.

**The central premise of the file is false.** Grep-verified: no module under `src/` initiates an
outbound network call — no client library, no retry wrapper, no timeout, no breaker, no fan-out to a
third party. Two HTTP client libraries are *declared* as dependencies and one of them is asserted
importable by the startup self-check, making a declared capability load-bearing at boot for a
capability nothing uses. The real external boundary is the database, the shared cache, the
filesystem, the queue broker and the browser.

**What remains is not a consolation prize.** Blocks 9, 10, 12 apply fully to the inbound surface, and
6, 7, 8 apply verbatim once "dependency" reads as "a thing the service talks to" rather than "a
vendor". Roughly 40 % deletion plus a reframing.

## 3.2 Premise audit — per block

| # | Block | Verdict | Notes |
|---|---|---|---|
| 1 | The credential seam: where a secret enters a request | **FALSE PREMISE as written** | *"Derive the outbound call set"* — there is none. Live residue: the credentials that leave the process boundary anyway (database DSN, cache URL, signing key) and the one credential that genuinely travels a wire. Both 02's and 04's. The one 07-shaped question inside is *"who may reach a surface with no credential at all"* — block 9's. Remove. |
| 2 | How a caller-supplied payload is encoded for the receiving parser | **FALSE PREMISE, inverted** | No receiving parser, no far side. Its inverse is real — the service parses the client's body, the interface parses the response — but the first half is 08's boundary-validation block and the second is 13's. Nothing survives that 9 and 10 do not own. Remove. |
| 3 | Retry contract: what is replayed, what bounds the total | **FALSE PREMISE** | No retries, no timeouts, no replay-eligible class. A retry library is *declared* and never imported — a real observation, but it belongs to new block 1. Remove. |
| 4 | The aggregate request budget one third party sees across processes | **ADAPTABLE, inverted — keep** | Read inward it becomes one of the strongest blocks in the phase. The rate limiter is a shared counter keyed by an identity the caller chooses on one surface and by a network address on another. Two findings the original's shape would miss: the two surfaces recognise one caller differently, and a proxy in front makes the address-keyed budget one the caller does not control. The original's multiplier (replicas × per-process limits) resolves *positively* here because the counter is shared — establishing that is as much a result as a finding. |
| 5 | The blocking-work bridge, in both directions | **DUPLICATE → 03, and the file contradicts itself** | Its own Purpose defers *"the event-loop bridge mechanism"* to a phase numbered 09 — this file. 03 block 9 already claims it. The reverse direction (*"network work pushed out of a request thread onto a pool whose result nobody retrieves"*) has no counterpart; the bridge is synchronous columnar work offloaded to a thread pool inside an async handler. Remove; 03's scope paragraph should name it. |
| 6 | Degradation: what each dependency's failure takes down, and how a guard fails | **ADAPTABLE, strongly TRUE — keep** | Real dependency set: the database (every read and the health probe), the shared cache (which serves the rate-limit counters *and* the queue *and* the one-time secrets), the filesystem holding accepted uploads and the interface bundle, the migration state. The guard question is exact: the limiter has an explicit fail-open/fail-closed switch, and its counter store is the same store carrying queued work — one outage reaches upload admission, job execution and secret retrieval through features meant to be independent. |
| 7 | A degraded result the consumer cannot tell from a real one | **ADAPTABLE, TRUE — keep** | Real instances: the limiter failing open returns "allowed" and records nothing; the sweep marking abandoned work failed and the sweep reclaiming its files are separate and neither reports a count; the health probe's "static files" component is a directory-existence test on a path relative to the process's working directory, reporting the same two words for "absent" and "present but wrong". |
| 8 | Isolation of failure inside a fan-out, and the record's order against the effect | **ADAPTABLE, TRUE — keep, narrowed** | The fan-out is real: fixed-size batches, each logging its own count, a failure mid-loop leaving earlier batches inside the transaction. The ordering half — *"a row written before the send is a record of an intention and is read afterwards as a record of an outcome"* — has a precise local translation: rename, then queue, then commit. The interleaving itself is 05's; keep a one-clause deferral. |
| 9 | Inbound surface form: method guards, body bounds, what a refusal discloses | **TRUE — keep, expand, becomes the phase's centre** | Real surface: eleven route groups under one prefix; an anonymous sink that answers anyone with success; two health probes, one returning per-component detail and a filesystem path to any caller; interactive schema documents enabled by default and disabled only in production; and a catch-all mount answering *any* unmatched path with the interface's entry document, including paths a client reads as API paths and unknown prefixes. The original's enumeration is correct for this system. |
| 10 | Which inbound boundaries validate, and which documented exceptions are load-bearing | **ADAPTABLE, TRUE — keep, expand** | The strongest single finding in the phase lives here: a per-dashboard processing configuration is accepted as a free-form document at the boundary that stores it, and validated only later, in a different process, after the upload is accepted and a status row written. A document the boundary cannot reject but the pipeline requires is a boundary finding. Add the secondary case: a query parameter carrying a hand-parsed document outside the model layer. The declared split with 08 (*"this block owns the inbound integration boundary"*) is already correct and must survive in both files. |
| 11 | Declared dependency and declared mechanism against the code | **DUPLICATE → 08** | Third copy of the declared-contract angle. Remove; 08 owns it. |
| 12 | What the integration surface writes into logs, and whether failure state is measurable | **ADAPTABLE, TRUE — keep** | Sharp and real: the anonymous sink writes a caller-supplied message, location and component stack verbatim into the application log at error level, from anyone, with no sanitiser in the path — and the volume is bounded by a counter the caller can trip from behind. *"Where no counter exists, a quiet dependency is indistinguishable from a working one"* survives verbatim. |

**NEW — block 1.** The phase is named for a boundary the system does not have. Under RC5/B10 the
absence must be *established and evidenced*, not assumed either way: **Whether this boundary exists at
all, and every mechanism that would carry one.** *Establish whether any component initiates a
connection to a host it does not control; if none does, establish that from both the call sites and the
shipped configuration and record it as a result, not a skip. Then establish, per mechanism that would
carry one — a declared client library, a retry helper, a breaker, a self-check requiring a client
library to be importable — whether anything reaches it, and whether its presence is a decision or
residue. A library the deployment refuses to start without, and nothing uses, is a finding: the blast
radius is the process and the capability is absent.*

## 3.3 Proposed final block set — 9 blocks

1. **Whether this boundary exists at all, and every mechanism that would carry one.** *As above.*
   Evidence: the outbound-call inventory, empty or not, with the search that produced it; one declared
   mechanism nothing reaches and the reason it is still load-bearing.
2. **The derived dependency set: what the request path cannot answer without, and what each one's
   failure takes down.** *Derive the set yourself rather than inheriting it from documentation,
   including shared state — a cache, a store, a queue, a filesystem the request path reads — and per
   dependency establish what its unavailability takes down, whether the blast radius is one feature or
   every page, and which dependencies are genuinely independent versus merely looking so.* Evidence:
   the derived dependency list with a per-dependency blast radius and independence verdict; one
   outage probe and what survived it.
3. **A guard built to bound abuse: what it does when its own store is unavailable, and whether the
   choice is recorded.** *Establish what the guard bounds, which counter it keeps, where that counter
   lives, and which of the three failure modes it takes when the counter cannot be read — permits,
   refuses, or raises; a guard that raises where it was meant to bound turns a dependency outage into
   a total one. Establish whether that direction is a declared value or a hard-coded branch, and
   whether it is recorded where an operator would look.* Evidence: per guard — the bound, the
   counter's home, the unavailable-store behaviour; one outage probe whose outcome differed from the
   guard's intended direction.
4. **The aggregate ingress budget: what bounds arrival, on which caller identity, and whether one
   caller is recognised the same way on every surface.** *Establish every bound on inbound volume —
   per principal, per network address, per surface, per window — and per bound which identity it is
   keyed on, whether the caller chooses it or it is derived from the connection, and whether the
   counter is shared across processes or per process. A limit correct inside one process is an
   unbounded budget in the deployed system; so is a limit keyed on a value the caller chooses.*
   Evidence: the bound inventory with the scope and identity of each; the process and replica counts
   from the shipped configuration; one arithmetic path from a caller-controlled value to the aggregate
   count.
5. **A degraded result the consumer cannot tell from a real one.** *Establish, for every fallback and
   default, whether what it returns can be told apart from a real result by whatever stores or
   consumes it — the row written, the probe's reported component, the status a caller polls; include
   the case where a guard, limiter or breaker is open and nothing counts or logs it.* Evidence: per
   fallback — the substituted value, its consumer, and one stored state a reader cannot distinguish
   from success.
6. **Isolation of failure inside a batch, and the order of a durable record against the effect it
   describes.** *Establish what happens when one member of a batched write fails — abort, continue, or
   complete — and whether any reader can tell how far it got; establish the order of a durable record
   against the effect it describes and what a repeat of the batch re-does. The interleaving of file,
   row and queue is 05's.* Evidence: one failed batch member and the fate of its siblings; the
   write/queue ordering on the same path; the residue a re-run meets.
7. **The inbound surface: which paths answer an anonymous caller, what each discloses, and what the
   published description promises about them.** *Derive the surface — machine-readable reads,
   state-changing writes, anonymous sinks, monitoring endpoints, schema documents, the catch-all
   serving path — and per endpoint establish whether a credential is required, what it discloses on
   refusal, and whether the disclosure level differs between the machine-readable and human-facing
   surfaces for the same decision; establish whether a machine-readable description is produced from
   the running code or maintained beside it, what it omits, and what a consumer built against the
   previous shape meets when a field changes without a version.* Evidence: the derived endpoint list
   with a credential requirement and disclosure verdict each; a refusal-class-by-surface matrix; the
   consumer list and the change each would break.
8. **Which inbound boundaries validate, which defer validation past acceptance, and which documented
   exceptions are load-bearing.** *Establish the validation convention at the request boundary — the
   strict-by-default base every client-input model should inherit, and how many inherit it — and for
   each that does not, whether the exception is documented, load-bearing or accidental, and whether
   the boundary rejects, ignores or coerces what it does not recognise. Separately derive the
   boundaries whose validation happens *after* the request supplying the input was already accepted
   and recorded.* 08 owns the production-code boundary surface; this block owns the inbound
   integration boundary. Evidence: the boundary-by-model inventory with an inherits / does-not-inherit
   verdict and, per boundary, the point at which its input is first rejected.
9. **The untrusted body as it is logged.** *Establish what the anonymous ingress path writes about a
   body it accepted from anyone — which fields, verbatim or transformed, at what severity, through
   which sanitiser and whether it masks — and the volume bound on that path and whether the bound is
   keyed on an identity the caller controls; then establish whether a dependency's failure state is
   measurable at all.* Where no counter exists, a quiet dependency is indistinguishable from a working
   one. Evidence: per direction, the fields logged and the sanitiser's masking verdict; the failure
   states with a counter, a log, or neither.

**REMOVED:** blocks 1, 2, 3, 5, 11 — the outbound transport, the encoding question, the retry
contract, the bridge (→ 03) and the declared-contract angle (→ 08).
**NEW:** block 1. Old 4 → new 4; old 6 → new 2.

## 3.4 Scope Boundaries paragraph

> **Scope Boundaries** — owned here: whether an outbound boundary exists at all; the derived runtime
> dependency set and what each dependency's failure takes down; the aggregate ingress budget and the
> identity it is keyed on; the anonymous ingress surface and what each refusal discloses; which
> boundaries validate and which defer validation past acceptance; what an untrusted body is written to
> the log as. Not owned here: settings values, secrets, origins and cookie policy (02); transaction,
> lock, pooler semantics and the thread-bridge mechanism (03); identity, credential issuance and claim
> guards (04); the upload pipeline and the derived-artefact lifecycle (05); artefact naming,
> residence, the one-time secret and the served bundle (06); fixed-value discipline, boundary-model
> strictness and the declared-contract angle (08); test adequacy (09); container, gate, edge,
> certificate, backup and observability posture (10); measured latency, cache cost and throughput (11);
> the access decision, refusal-shape equivalence between two surfaces, and which surfaces a
> request-forgery check reaches (12); the interface's own code and its type expectations (13); the
> schema chain (14); header, origin, credential and rate-limit *policy*, this phase owning only the
> mechanism by which a policy is applied (15). Design deliberately asymmetric between surfaces is not a
> defect on its own; report it only where the code's own documentation misstates it.

## 3.5 Finding-ID prefix

**Keep `EXT-`** — matches the new stem, claimed by no other live or archived phase. The current file
carries a seventh bullet for the collision clause; fold it onto the prefix bullet to restore the
canonical six-bullet form (AP14).

```
## Report Output
- Findings path: `.ai/audit/07-external-boundary/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `EXT-` — check for a collision before minting an ID; a shipped test, comment or report may already carry one from a prior cycle, and report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting current behaviour is a remediation blocker, not a gate
```

---

# 4. `08-audit-code-quality.md`

## 4.1 Current state

Modern B-family, 9 blocks, 134 lines. `name: 10-code-quality` vs stem `08-audit-code-quality`;
findings path `.ai/audit/08-code-quality/findings.md`; prefix `QLT-`.

**The best-fitted file in the batch.** Its Purpose is technology-free, its blocks open with
state-of-world verbs, and nearly every block's hypothesis matches a live instance. The work is
surgical: fix the stale Scope Boundaries paragraph, designate this phase as the owner of the
declared-contract angle so the other four files can defer to it, split one over-broad block, and hand
the migration chain to 14.

Instances already visible, each of which an existing block reaches correctly: one vocabulary for
aggregation functions implemented in **two** maps, one with ten members and one with five, the second
falling back to `sum` for the five it lacks; presentation vocabulary living in the server model package
and mirrored by the client; the error taxonomy maintained as **three parallel tables** keyed by the
same enumeration in another module, one falling back silently; a linter per-file-ignore entry for a
directory that does not exist; a type stub declared for a library the project rules forbid; a startup
self-check requiring a network client library nothing imports; a "Compatibility API" section holding
three deprecated wrappers that re-derive decisions the instance methods already make; the storage
routine written out twice, once per session mode; a defaulted string parameter later compared against
an enumeration.

## 4.2 Premise audit — per block

| # | Block | Verdict | Notes |
|---|---|---|---|
| 1 | Fixed values: one named home per value | **TRUE — keep, strengthen** | The declared home is a single vocabulary module and it is genuinely bypassed. *"A named home that exists and is bypassed is the finding; the literal itself is only the evidence"* is the correct rule, and the two-maps-one-vocabulary instance satisfies it exactly. Add the cross-tier half: a value written once on the server and again in the client with nothing keeping them equal, and the project's own consistency test that covers one tier and not the other. |
| 2 | The constant surface as a maintained artefact | **TRUE — keep, retarget** | The block's questions (numbering convention, membership provenance, export lists, a mapping inside the vocabulary, a value table built in its consumer) are all answerable here, and the real shape is specific: one flat module holding domain vocabularies, error codes *and* presentation vocabulary, plus three parallel tables keyed by one of them in another module. |
| 3 | Boundary validation coverage | **TRUE — keep** | The declared split with 07 is already correct and must survive verbatim in both files. Add: the boundary whose input is a free-form document only a later, different process can reject — 05 block 6 covers what happens to it; this block covers that the boundary does not. |
| 4 | Type width and the sanctioned-suppression surface | **TRUE — keep** | Real configuration: the checker is not in its strictest mode, several packages are silenced wholesale with recorded reasons, the coverage floor is a number. The widened-annotation classification has at least three live instances, including a defaulted string parameter compared against an enumeration and a cast used to satisfy the checker on a read path. The production-only exclusion is correct and must stay. |
| 5 | Responsibility inside a unit | **TRUE — keep** | The background job function performs status transitions, file work, parsing, validation, casting, renaming, computed fields, transformation, aggregation, storage, list derivation and logging — and a second copy of the storage routine exists for a different session mode. The block's counter-rule (*"a size signal with nothing behind it is not this block's finding"*) is right and should be retained verbatim. |
| 6 | One rule, one home | **TRUE — keep** | The duplicated storage routine, the twice-written model-to-read-model mapping, the mode rule expressed as a string in one place and an enumeration in another, and the deprecated wrappers are four live instances. The rule that a non-sharing site is a *claim to establish*, not a duplication to file, is the correct discipline. |
| 7 | Convention compliance: the cheap high-volume rules | **TRUE — keep, retarget** | The enumeration survives wholesale; the instances are a linter and a separate formatter configured in the project manifest, a per-file-ignore entry pointing at a nonexistent path, a declared type stub for a forbidden library, a startup self-check listing a module nothing imports, and an import-time side effect whose correctness depends on a module imported first. The unreferenced-definition clause (*"the answer may be a feature that is not switched on yet"*) is the dead-code policy this project's rules require — keep it. |
| 8 | Declared contracts and their enforcement point | **TRUE — keep, and designate ownership** | Live instances: a module docstring asserting "no race condition" beside a path that is not race-free; a function docstring asserting a single atomic transaction beside a rename and a queue handoff that are not in it; a route description asserting an audience narrower than the dependency it uses. **This is the fourth copy of the angle across the set (06, 07, 10, 12).** This phase should declare itself owner in its Purpose and the other four files defer in one clause — the cheapest C6 fix available, and this file's to make. |
| 9 | Migration discipline and schema drift | **ADAPTABLE, partial DUPLICATE → 14** | The block already asks the right question (*"a gate fails when one is missing"*) and 14 will own the chain, reversibility and index inventory. The residue that is this phase's: whether anything fails when a model change ships without a migration; whether the boot path that applies migrations is the only thing that would notice; and the several places writing rows as a side effect of starting or seeding, each needing an idempotency verdict. |
| — | *(absent)* The declared gates | **NEW** | The project defines lint, typecheck, test and frontend gates, each with a value that decides pass or fail. Nothing in the set asks where each gate is wired, whether a check present in configuration is actually executed, or whether a contributor can run it the way the pipeline runs it. 10 owns container and deploy gates, 09 owns what the suite would notice; nothing owns the declared-gate surface. The highest-value uncovered angle in the file. |

## 4.3 Proposed final block set — 10 blocks

Blocks 1–8 keep their titles and obligations with the retargetings above. New:

9. **The gates the project declares: where each is wired, what each decides, and whether it can be run
   the way the pipeline runs it.** *Derive the declared-check inventory from the project's own command
   surface and configuration, and per check establish what it decides, what value it compares against,
   where it is invoked from, whether a check present in configuration is actually executed or merely
   declared, and whether a contributor can run it locally the way the automated path does. Do not
   assume a gate exists until one is found running; its absence is the finding. A threshold that is a
   fixed number rather than a delta is part of the same question. Container and deploy gates are 10's;
   what a test suite would notice is 09's.* Evidence: the gate inventory — which checks are declared,
   where each runs, what it covers, whether it is reachable; one check present in configuration that
   nothing invokes; one gate whose local and automated invocations differ.
10. **Schema drift: whether anything would notice, and which rows are written by code rather than by
    a migration.** *Establish, for every model change, whether the schema history records it — then,
    separately, whether anything would fail if it did not. Establish whether schema or reference data
    is mutated from a code path rather than a migration: a boot-time bootstrap, a development seeder, a
    test-data seeder, a repair run — and whether each is idempotent if run twice and whether it runs
    where it was not expected. The chain's linearity, reversibility and the index inventory against
    query predicates are 14's.* Evidence: which drift checks exist, where they run, what they cover;
    one model change with no recorded migration, or the confirmation that none exists; every
    non-migration row-writing path with an idempotency verdict.

## 4.4 Scope Boundaries paragraph

> **Scope Boundaries** — owned here: where a fixed value lives and whether the type system constrains
> it; the constant surface as a maintained artefact; boundary validation discipline; the configured
> strictness and the sanctioned-suppression population; responsibility inside a unit; one rule, one
> home; the cheap high-volume conventions; **the declared-contract angle, as its owner — any other
> phase establishing that a documented claim is contradicted or unenforced defers to this one**; and
> what the declared gates decide and whether anything would notice. Not owned here: settings values,
> secrets and environment policy (02); transaction, lock and pooler semantics, and the thread-bridge
> mechanism (03); identity and credential strength (04); what the pipeline derives, writes and
> replaces (05); artefact lifetime and store-versus-record reconciliation (06); the inbound surface
> form, dependency-failure degradation and the ingress budget (07); test-suite adequacy and what the
> suite would notice (09); container, deploy, edge, backup and observability posture (10); measured cost
> (11); the access decision and refusal shape (12); the interface's component, state and type
> architecture (13); the migration chain's linearity and reversibility, and the index inventory
> against real query predicates (14); header, origin, credential and rate-limit policy (15). A codebase
> need not be clean to be well-made: this phase asks whether a rule has one home and whether anything
> checks it, not whether a different design would have been better.

## 4.5 Finding-ID prefix

**Keep `QLT-`** with the existing collision clause. Already in use from a prior cycle; renaming orphans
identifiers that shipped code and reports already carry. R12 asks for uniqueness, which `QLT-` has.

```
## Report Output
- Findings path: `.ai/audit/08-code-quality/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `QLT-` — already in use in shipped source from a prior cycle, with at least one identifier already resolving to two different findings; check for a collision before minting an ID and report it rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting current behaviour is a remediation blocker, not a gate
```

---

# 5. Cross-batch notes

1. **`DB-` is claimed twice** (03 db-concurrency, 14 schema-migrations). 99 will file it as a namespace
   ruling; the 14 batch should be told before it writes.
2. **The declared-contract angle has five instances** (06 b10, 07 b11, 08 b8, 10 b3, 12 b12) and the
   "control that examines nothing" angle five more (09 b7, 10 b3, 11 b2, 99 b2, plus the declared-gate
   block proposed above). 08 is the natural owner of the first, 10 of the second. Both ownership
   statements belong in those files' Purpose, not in every block.
3. **Three files in this batch still carry the old numbering in their Scope Boundaries paragraphs**
   (06, 07, 08); 05 carries it in its frontmatter, its Report Output path and its state machine. The
   paragraphs above are the corrected text and use the new numbering throughout.
4. **AP13 is resolved.** `.ai/audit/templates/audit-findings.md` now exists (verified) — the first time
   in the set that the template pointer resolves.
5. **No block in this batch may name a file, port, command, library or product.** The sketches above are
   written to that rule: the nouns are *"the accepted artefact"*, *"the shared cache"*, *"the queue
   broker"*, *"the column store"*, *"the one-time secret"*, *"the built interface bundle"*, *"the
   conflict key"*. Real instances are named in this analysis as evidence for the writer, not in the
   phase files.
