---
name: 06-file-artifacts
executor: auditor
problems-only: true
---

# Phase 06 — Stored File Artefacts

## Purpose

Audits the stored-file path end to end: what an accepted upload is called and what its name claims, where it lives and what
bounds it, what reclaims it, how what is stored is reconciled against what is recorded, and what a secret held outside the
database or a built bundle served from disk does for its whole life. This file names what to examine and under which angle; the
executing auditor discovers the concrete artifacts.

**Scope Boundaries** — owned here: what a stored artefact is — an accepted upload, a one-time secret, the built interface bundle —
how each is named, where it lives, what reclaims it, how store and records are reconciled in both directions, and which process
does the reclaiming. Not owned here: settings values (02); transaction, lock and pooler semantics, and sweep repeat-run safety
(03); what a marker must express to revoke, and credential strength and issuance (04); what is derived from an upload, what is
written, and what each write mode replaces (05); the inbound surface form and the transport-level body bound (07); fixed-value
discipline and the declared-contract angle (08); test adequacy (09); container, gate, edge, certificate and backup posture, and
header policy as a shipped configuration (10); measured storage and throughput cost (11); the access decision for an artefact or
a status query (12); the interface's component and state architecture (13); the schema chain (14); header, origin and
credential policy (15). The composition of every key in the store and each marker's lifetime is 10's, what a revocation marker
must be able to express is 04's, and whether a surface is rate-bounded at all, and what credential material the store holds, is
15's. Side effects spanning a record and the file it names, written by different processes, are 05's. An artefact that exists
in one process and not another is not a defect on its own; report it only where the code's own documentation misstates it.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed
behaviour, a static proof that a stated property does not hold, or a reproduced divergence between two paths; the method is the
auditor's. A passing check is methodology, never a finding. Where a property cannot be settled in the environment at hand,
establish it from what is observable and state plainly what could not be verified and why — an unreachable surface is a limit on
the report, never a finding. Every block's evidence is an artefact that must exist in the report's appendix as a coverage record,
even where the block produced no finding.

### 1. The accepted artefact's identity: what it is called, what its name claims, and what its bytes are

*Establish the three identities an accepted artefact carries — the name the caller supplied, the name it is stored under, and the type derived from its
content — deriving the artefact classes rather than assuming the set, and per class establish which of the three decides how it is later read. Then
establish the branch taken when a type cannot be derived from the content, what that branch accepts, and what an artefact whose name and its content
disagree is treated as at each later decision. A name that decides parsing while the content decides admission is a finding; so is an artefact whose
stored name claims a type its bytes do not support, carried through every later read as though the claim were established.*
Evidence: the three-identity inventory with, per artefact class, the deciding identity; the branch taken when a type cannot be derived; one artefact whose name and content disagree and what each downstream decision followed.

### 2. Residence of an accepted artefact, and what bounds it

*Establish what limits arrival, what reclaims an abandoned artefact, and for each bound whether it is on time, on count or on bytes — a time bound does
not bound a rate, and a count per caller does not bound bytes. Derive the bound inventory rather than assuming one bound per stage. Establish where the
in-flight area lives and what else shares the storage whose exhaustion stops something wider than one upload. The admission controls themselves are
05's; where an admitted artefact lives and what bounds it is this block's.*
Evidence: the control inventory with each control classified by what it actually bounds; the shared-storage consequence of exhausting the area.

### 3. Reconciliation between stored artefacts and stored records, in both directions, and what is exempt

*Establish the difference between what the store holds and what the records name, and derive it in both directions: an artefact no record names, and —
state this one explicitly, because difference-based tooling is one-sided by default — a record naming an artefact that is not there. Per direction
establish whether anything detects it, whether anything repairs what it detects, and every part of the area excluded from the comparison together with
the reason. Establish the naming rule each component that reads the area independently relies on, and whether the rules agree: components that select by
name are written against different assumptions and nothing enforces their agreement. Detection and repair are this block's; whether the access decision
should notice the missing artefact is 12's; where a contract is declared, whether the declaration is executable and whether any path consults it is
08's. Locking and repeat-run safety are 03's.*
Evidence: both directions with a per-direction detector verdict and repair verdict; the excluded subtrees with their reason; two components that select by name and do not agree.

### 4. Removal of an artefact, and the record of a removal that failed

*Establish per audience which removal operations exist, whether one artefact can be removed without destroying the record that names it, and whether the
collection is append-only by construction. Then establish what a failed removal leaves behind: whether the failure is recorded, what reads that record,
how long it is kept, and whether an operator can see it or act on it. What triggers a removal, and what an account's state means to it, are 12's and
15's; the physical removal mechanics and the record of a removal that failed are this block's.*
Evidence: per audience, the removal operations that exist; the failure record's readers, its retention, and whether anything alerts on it.

### 5. A one-time secret held outside the database: how it is created, how it is collected once, and what a failure at each step leaves behind

*Establish the artefact's observable lifecycle — who generates it, from what source, under what handle a caller presents to collect it, and what removes it
at the moment of collection. Then establish what each failure leaves behind:
whether a failure to create leaves the caller believing one exists, whether a failure to read is distinguishable from one that never existed, and
whether a collection that returns nothing still consumes the handle. The composition of every key in the store and each marker's
lifetime is 10's; what a revocation marker must be able to express is 04's; whether a surface is rate-bounded at all, and what credential material the
store holds, is 15's; who may collect it is 12's.*
Evidence: the lifecycle inventory with the residue of each failure point; one failure in which the caller is told a secret exists and it does not.

### 6. The built interface bundle as a served artefact: what is served from disk, and what changes when it is absent

*Establish what the serving path reads, under what condition it registers at all, what a request for an unmatched path receives, and which component's
presence changes the route table rather than only its content. Establish what an observer is told when the component is missing, and whether the answer
it gives is the same for absent and for present-but-wrong. Cross-origin and header policy are 15's and 10's; the component's own code and state
architecture are 13's.*
Evidence: the serving inventory with a present or absent verdict per path class; one request decided by a component's presence rather than by the request; the words a monitoring observer receives for absent and for present-but-wrong.

### 7. Which process reclaims an artefact, and what two of them doing it at once produces

*Establish which long-lived processes read, create and remove artefacts, deriving the process set rather than assuming it. Ask what a second remover meeting
an already-removed artefact produces — a silent no-op, a logged error, or a failure
a caller sees — and whether a removal can race a consumer that has not yet read what it is about to remove. Whether each operation is mutually excluded and
by what is 03's; the record-and-file side effect written by
different processes is 05's; what two reclaimers do to each other is this block's.*
Evidence: the process inventory with the operations each performs; one operation whose second remover produced an outcome nothing records.

### 8. Whether an accepted artefact is ever returned to a caller, and which code assumes it is

*Establish whether any accepted artefact leaves the system again and which components still read one from storage to answer a request, deriving the
returning-surface inventory rather than assuming it is empty. For each such component establish what it concludes when the artefact is absent, and
whether the caller can distinguish that from processing not yet finished. A component that reads an artefact from storage and lets its absence decide
what the caller hears is a finding even where no artefact is ever served, because the decision the caller receives depends on a file that may not be
there.*
Evidence: the returning-surface inventory, empty or not, with the components that read storage without serving it; one component whose absent-artefact answer is indistinguishable from a pending one.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — credential material or stored content exposed irreversibly, or destroyed while a live record still names it: a one-time secret still recoverable from the store that holds it after the window in which it may be collected; an artefact handed to a caller the access decision is meant to refuse; an artefact removed with no detection of the loss and no path that reverses it.
- **HIGH** — a silent correctness failure with no self-healing path: a record naming an artefact that is not there, or an artefact no record names, with nothing detecting it in that direction; a removal reported as performed and left in place; two components selecting by name in the same area under rules that disagree; an artefact whose absence the caller is told is a pending state.
- **MEDIUM** — a bounded resource or operability gap: an area reclaimed by age but unbounded in count or in bytes; a removal whose failure is recorded with no reader, no retention and no alert; a served component whose absence changes the route table and is reported the same way as one present but wrong; a secret the caller is told exists and that no failure path ever reports as absent.
- **LOW** — documentation and observability drift with no runtime consequence today: a stated naming rule one component does not follow; an artefact's stored name claiming a content type its bytes do not support; a limit declared in more than one place with no divergence yet; an artefact whose three identities disagree with no downstream consequence today.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/06-file-artifacts/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `ART-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
