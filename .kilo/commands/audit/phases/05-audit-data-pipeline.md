---
name: 05-data-pipeline
executor: auditor
problems-only: true
---

# Phase 05 — Ingestion and Aggregation

## Purpose

Audits the path an accepted file takes from admission to stored result: what it is admitted against and by which layer, what state
it is left in and which process writes that state, what is derived from its contents, what is written and what each write mode
replaces, how a failure is classified, and what reclaims an input nobody finished. One angle is owned here alone: side effects
that span a record and the file it names, written by different processes. This file names what to examine and under which angle;
the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — owned here: what an upload is admitted against, what state it is in, what is derived from it, what is written,
what each write mode replaces, what reclaims an abandoned upload, and how a failure is classified. Not owned here: settings
values (02) and the configured bound a sweep reads (02's b3 guard inventory); transaction, lock and pooler semantics (03);
the mechanism that carries work out of the request path (01); identity and acceptance of the caller's credential (04); artefact
naming, residence, store-versus-record reconciliation and the served interface bundle (06); the inbound surface form, the
transport-level body bound and dependency-failure degradation (07); fixed-value discipline, boundary-model strictness and the
declared-contract angle (08); test adequacy (09); container, gate, edge and observability posture (10); measured cost per input
(11); the access decision for an upload or a read (12); the client-side upload experience (13); the schema chain and index
inventory (14); header, origin and rate-bound policy (15). Deliberately asymmetric depth between the accepting path and the
consumer is not a defect on its own; report it only where the code's own documentation misstates it.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed
behaviour, a static proof that a stated property does not hold, or a reproduced divergence between two paths; the method is the
auditor's. A passing check is methodology, never a finding. Where a property cannot be settled in the environment at hand,
establish it from what is observable and state plainly what could not be verified and why — an unreachable surface is a limit on
the report, never a finding. Every block's evidence is an artefact that must exist in the report's appendix as a coverage record,
even where the block produced no finding.

### 1. Ingestion admission: which limits exist, which layer enforces each, and what one input can pin

*Derive the admission inventory from the path that accepts an upload rather than from its documentation — the declared size ceiling, the type derived
from the content, the extension in the caller-supplied name, and the cumulative byte budget enforced while the transfer is still running — and derive
the site count rather than assuming it. Per limit establish the enforcing layer and the long-lived process it runs in, every place its value is
declared, and whether the declarations agree. Then establish what one admitted input holds at once, at what point a transfer becomes a whole in-memory
structure, and what a single caller can pin while it is held. A limit no reachable path consults is a finding; so is a limit declared in one process and
absent from another that writes the same store.*
Evidence: the admission inventory with, per limit, the enforcing layer, its declaration sites and any divergence; one declared limit no reachable path consults; one admitted input and the size it holds at once.

### 2. The state of an accepted upload: every transition the executing path can produce, and who writes it

*Establish the state vocabulary the executing path actually uses, deriving it from the committed rows rather than from the vocabulary's own declaration,
then per state its writers — the accepting process, the in-process consumer, the separate worker, and each recovery sweep. Establish which transitions
each writer can reach and whether a state a consumer branches on is ever a state a committed row holds. Then ask what each sweep rewrites, on what
evidence it rewrites it, and what it announces. A state no committed row ever holds while a consumer branches on it is a finding; so is a writer that
reaches a state its peers cannot. Whether a declared transition table is enforced by its writers is 08's angle; what the writers can actually produce is
this block's.*
Evidence: the state inventory with a per-writer verdict on which transitions it can produce; one state a sweep rewrites that a consumer also writes directly; the answer to which declared transitions no code enforces.

### 3. The unit of atomicity: what commits together, and what a rollback leaves behind

*Enumerate every side effect the accepting path produces — the stored file, the status row, the queued work, the derived rows — and establish which of
them share a commit and which are reconciled only by compensation, naming the compensating step for each. Then confirm or refute all-or-nothing by
inducing a failure between the first effect and the last, and record what each surviving effect looks like afterwards. A rollback that leaves a stored
file or a queued job behind is a finding: the record it left names an effect that no longer exists. Transaction shape, lock semantics and pooler
behaviour are 03's; what commits together is this phase's.*
Evidence: the effect inventory with a shared-commit or compensated verdict per effect; one induced mid-sequence failure and the residue of each effect.

### 4. Determinism of the aggregate: what makes identical input produce a different stored row

*Derive the aggregate's identity — the column set that decides whether a new row updates an existing one — and establish what normalisation that identity
depends on and whether two value-equal inputs can be unequal in it. Then establish which configured aggregates depend on row order rather than on the
data's own values, which derived measures depend on an ordering the code imposes but never pins, and which stored measure names depend on a function
chosen somewhere other than the aggregate itself. Produce one pair of inputs equal in value and unequal in identity, and one aggregate whose result
changes when the row order does. A re-upload that produces a second row set beside the first is a finding.*
Evidence: the identity derivation with the normalisation it requires; one value-equal, identity-unequal pair; one aggregate whose result changes with row order.

### 5. Replacement semantics: what an overwrite and an append each remove, and what neither removes

*Establish per write mode the selection removed, the rows written, and the selection left untouched — a dashboard with no configured charts, a chart
since removed, a dimension absent from the incoming data — deriving the selections from the executing path rather than from the mode's name. Then
establish the secondary list rebuilt alongside the stored rows and, per mode, the source each reads to build it. A configuration that produces a
completed run while leaving rows in place is a finding; so is a secondary list built from a different source in each mode, since the two modes then
disagree about what exists.*
Evidence: per mode, the selection removed and the selection left; one configuration causing a completed run to leave stale rows; the source each mode reads to rebuild the secondary list.

### 6. Configuration reach: which parts of a stored processing configuration are honoured, which are skipped, and which fail the run late

*Derive the field set of a stored processing configuration from what the executing path reads, and per field establish whether an absent, unknown or
malformed value is honoured, silently skipped, or fails the run after it has begun. Separately establish whether the document is validated at the
boundary that stores it or only later, in a different process, and whether a renamed field is a failure or a silent no-op. Include the fields whose
absence changes the stored result without changing the run's outcome. A field skipped with a warning while the run reports success is a finding: the
operator is told the run succeeded and the result is missing something the configuration asked for.*
Evidence: the field inventory with an honoured, skipped or late-failure verdict per field; the point at which an invalid document is first rejected, or the confirmation that nothing rejects it.

### 7. Caller-supplied expressions: what a stored formula may name and what it may compute

*Establish the expression grammars a stored configuration may carry — an arithmetic grammar over named columns, and a narrower grammar over one named
column's date parts — and per grammar establish which identifiers and which functions it admits, what a name matching no column of the loaded data does,
and whether the limits are enforced when the expression arrives or when it is compiled. Then establish what the compiled expression can reach beyond the
loaded columns: any other source of values it can name, and any way a name can be made to resolve where it should not. An identifier the grammar admits
and the loaded data does not hold is a finding, and an identifier that resolves differently depending on when the expression is compiled is a finding of
its own.*
Evidence: the grammar inventory with the limits enforced at each point; one identifier admitted by the grammar and absent from the loaded columns; one expression whose resolution depends on when it is compiled.

### 8. Failure classification: how an outcome is categorised, and what each category reaches

*Establish where an exception becomes a machine-readable outcome class, whether by its type or by inspecting its text, and derive the classification
sites rather than assuming there is one. Per site record the signal it inspects and the categories it can produce. Then establish whether independent
sites classify the same failure the same way, and what a caller is told when a failure matches neither. A classification that depends on the
wording of an underlying library's message is a finding: a change upstream re-routes a failure class without changing any code here.*
Evidence: the classification sites with the signal each inspects; one failure whose text the independent sites classify differently.

### 9. Validation of the loaded frame: what is refused, what is only warned, and whether a warning is stored anyway

*Establish the checks applied to the loaded data before it is stored, deriving the check set from the executing path, and per check whether a failure
ends the run or merely annotates it; include the checks that run only when a caller supplies the expected shape. Then establish what an annotation
records, where it is kept, how long it is kept, and whether the rows it describes are stored regardless of it. An annotation whose rows are kept and
whose record no reader consults is a finding: the run is reported as successful over data it has already recorded as doubtful.*
Evidence: the check inventory with a refuse or annotate verdict; one check that runs only when a caller supplies the shape; one annotation stored alongside the rows it describes.

### 10. Cleanup and recovery: what reclaims an abandoned accepted input, in which process, on which clock, and what it cannot reach

*Establish the reclamation set — per-task deletion, an age-bounded sweep, a retention sweep over status rows — deriving it rather than assuming it is
exhaustive, and per sweep establish which process runs it, what it selects, which clock it reads, and whether the bound is on age, on count or on bytes.
Then establish what each sweep cannot reach, and the window in which a completed status row outlives the file it names. A sweep whose bound is a code
literal rather than a configured value is an operability finding, not a finding about the bound itself. The configured value each sweep's bound reads is
02's b3; lock and repeat-run semantics are 03's.*
Evidence: the sweep inventory with a bound-kind verdict per sweep; one status row whose named file a sweep can remove first; the clock each sweep reads.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — a stored result that is wrong now and nothing downstream can tell: aggregate rows that silently accumulate across successive uploads of the same data, so two answer the same question differently; a completed status row whose derived rows are a mixture of two inputs; a committed record naming an effect that no longer exists.
- **HIGH** — a silent correctness failure with no self-healing path: an operation reports success while leaving the state it claims to have replaced; a configuration field or an aggregate function skipped in a way the run's outcome does not reflect; a failure class that re-routes when an underlying library's message changes; a reclaimed input whose status row still names it as complete.
- **MEDIUM** — a bounded resource or operability gap: an admission limit nothing consults, or consulted in one process only; a sweep bounded by age where the area is unbounded in count or in bytes; an input left behind when reclamation itself fails; an expression admitted by the grammar and absent from the loaded data.
- **LOW** — documentation and observability drift with no runtime consequence today: a state in the declared vocabulary that no committed row holds; a warning annotation no reader consults; a fixed value declared in more than one place with no divergence yet; a declared transition no code enforces.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/05-data-pipeline/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `DP-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
