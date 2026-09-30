# Designing Durable Audit Task Specifications for LLM Auditor Agents

Research report. Companion to `.kilo/commands/audit/phases/_conventions-analysis.md`, which
describes what the current 25 phase files *are*. This report describes what a phase file
*should be* so that it survives years of code change, and how to write one.

**Scope of evidence.** Three tiers, tagged throughout:
`[A]` attested in external literature or vendor guidance; `[C]` attested in this repo's own
phase set, quoted or line-cited; `[S]` my synthesis / engineering judgement.

- `[A]` Anthropic's context-engineering guidance names the "right altitude" for system prompts as
  the Goldilocks zone between brittle hardcoded logic and vague high-level guidance that "falsely
  assumes shared context", recommends the *smallest set of high-signal tokens* that outlines
  expected behaviour, and holds that "just-in-time" context with progressive disclosure beats
  pre-loading — a phase prompt is a *navigation* artefact, not an archive. It also warns that
  without "proper guidance and heuristics" an agent "will waste context by misusing tools,
  chasing dead-ends, or failing to identify key information": discovery freedom needs a
  hypothesis, not a map.
- `[A]` OWASP ASVS V1–V14 and STRIDE/LINDDUN are capability-named verification requirements that
  survive rewrites precisely because they name *properties and threats*, not implementations.
  CWE renumbering forces refactors; ASVS section names do not.
- `[A]` *Agent READMEs* (2,303 context files / 1,925 repos): architecture descriptions appear in
  68.1% of context files, are the third-most-common instruction type, and are the ones that rot.
  Instruction files evolve append-only, median +57 words per commit — accretion, not pruning.
- `[A]` *How Developers Maintain and Evolve Their Agents' Instructions* (Voria et al. 2026)
  establishes that persistent agent instruction files are governed artefacts whose evolution must
  be related to code evolution — i.e. they need a maintenance discipline, which this report's
  section 8 proposes.
- `[C]` The B-family of the current set already achieves most of what follows. This report does
  not invent a new style; it names the properties the existing style implies and shows where the
  set still leaks (`[C]` FM10: "WSGI", "management-command dispatch", "declarative admin surfaces").

---

## 1. Requirements distilled

Twelve checkable properties. Each is testable by a reviewer without running an auditor.

| # | Property | One-line rationale |
|---|---|---|
| R1 | **Zone, not procedure.** The file states a responsibility and per-block angles; it never orders verification or gates a finding on the phase's own steps. | A prescribed order freezes verification into the prompt, so one impossible step silently invalidates every block citing it `[C]` FM1/FM4. |
| R2 | **Capability-scoped, not artefact-scoped.** Scope is named by what a subsystem *does*, never by which files, directories, tables, endpoints or commands implement it. | Artefact names are the fastest-rotting content in agent instruction files `[A]` (Agent READMEs) and break silently — a stale path is indistinguishable from a missing file `[C]` FM2. |
| R3 | **Discovery is the auditor's job.** The prompt names *kinds* of things ("the test schema", "the freshness token"), and the concrete instances are found at run time. | Progressive disclosure beats pre-loaded context `[A]`; a prompt that names instances forces the auditor to reconcile the prompt against a codebase that no longer matches. |
| R4 | **Every block is independently executable.** One angle, one obligation, one evidence artefact; a subagent can run block 7 with no other block's output. | The framework's own requirement (`audit-phase-refine.md` §1.3) `[C]`; blocks that cite each other cannot be delegated or split across helpers. |
| R5 | **Obligations, not checks.** Each block opens with a state-of-the-world verb (`Establish`, `Enumerate`, `Derive`, `Trace`, `Compare`) and states what a finding *looks like* as a hypothesis. | `Check that…` / `Ensure that…` produce rows that cannot fail and are not tasks `[C]` FM7 / §5.2. |
| R6 | **Evidence is an artefact class with one reproduced observation.** Every block ends in a single `Evidence:` line naming a deliverable, at least one item of which must be reproduced or measured, not merely enumerated. | Evidence that depends on the phase's own procedure is unevaluable in isolation `[C]` FM4; enumeration alone cannot evidence an absence. |
| R7 | **Ownership is declared, not implied.** Every phase names what it owns and what it defers, with phase numbers; splits of one shared question are declared in both files. | Undeclared adjacency produces either duplicate findings or gaps, and forces the validator to arbitrate `[C]` FM6/FM8. |
| R8 | **Severity is graded by effect and blast radius, never by mechanism.** One rubric per file; an empty band is a valid outcome. | Mechanism-keyed labels get copied verbatim into every report the phase ever writes `[C]` FM11. |
| R9 | **The empty state is distinguishable from a non-empty report.** A reserved exact string plus a recorded residual of what could not be verified. | Otherwise "audited and clean" and "never ran" are the same artefact `[C]` §2.5. |
| R10 | **Deliberate asymmetry is pre-declared as non-defect.** The file states which differences between tiers, processes or transports are intended. | Without it, every block becomes a false-positive generator against intentional design `[C]` `01-entry-architecture` Purpose ¶4. |
| R11 | **Density.** 8–13 blocks, 117–140 lines, one-screen Purpose. Length that correlates with the audit's coverage is length that nobody re-reads. | `[C]` §4.16: the M family runs 168–212 lines and covers strictly less; `[A]` context rot with token count. |
| R12 | **Verifiable identifiers.** Filename, frontmatter `name`, findings path and finding-ID prefix agree, and the prefix is unique across the set. | The orchestrator derives the output path from the filename `[C]` `audit-multi-phase.md` §2.1; drift makes one phase write two directories `[C]` FM12. |

*Pick one when two conflict:* R2 over R3 comfort. Naming an instance reads as helpful and is the
single largest source of rot; an auditor can find a table in one search but cannot un-find a
hallucinated one.

---

## 2. Recommended prompt skeleton

### 2.1 Frontmatter — three load-bearing fields

```yaml
---
name: 07-media          # identity; MUST match the filename stem
executor: auditor       # the only field that changes what the agent does
problems-only: true     # the reporting contract
---
```

Drop `status`, `validated`, `description`, `agent`, `alwaysApply`: they are constants or
placeholders for a lifecycle no component implements `[C]` §2.1. A phase file is a task prompt,
not a ticket; state that can go stale and is never read is pure liability.

### 2.2 Four sections, fixed order, no fifth

```
# Phase NN — <Zone in system nouns>
## Purpose            — zone, angle, ownership contract, discovery rule
## Audit Blocks       — the executable work
### N. <Title Case question, no trailing period>
*<obligation, chained sub-questions, hypothesis-shaped finding rule>*
Evidence: <artefact>; one <reproduced observation>.
## Severity Taxonomy  — four effect-class bullets + two guard sentences
## Report Output      — six fixed bullets
```

No `## Output Mode`, `## Discovery Stage`, `## Mandatory Runtime Verification`, `## Audit
Scope` `[C]` §4.21. A reviewer seeing one of those four in a new file rejects without reading
further — that is the value of having them as a structural signature.

### 2.3 Annotated skeleton (the shape, not a template)

```markdown
# Phase 07 — Media Handling & Access                        <- zone in nouns, never a filename

## Purpose
Audits <the path> end to end: <what is admitted>, <where bytes go>, <what is derived>, <what
the serving path hands out and on whose word>, <what removes them>.     <- zone as a journey
This file names what to examine and under which angle; the executing auditor discovers the
concrete artifacts.                                              <- R3, stated once per file
Scope Boundaries — other phases own: <zone> (03); <zone> (06); <zone> (09); <zone> (15).
                                        <- R7: one paragraph, numbers not names
Design deliberately asymmetric between <tiers> is not a defect on its own.   <- R10

## Audit Blocks
Each block is independent — execute any one with no knowledge of the others. Evidence is a
class, not a check list: observed behaviour, a static proof that a stated property does not
hold, or a reproduced divergence; the method is the auditor's. A passing check is methodology,
never a finding.                                      <- R4, stated once per file, not per block

### 3. <The question, phrased as the thing to establish>
*Establish <state of the world>. Then <the sub-question>. And <the counter-case>. A <shape>
that is not <property> is a finding.*                            <- R5, hypothesis not check
Evidence: <artefact to exist when done>; one <observation actually produced>.   <- R6

## Severity Taxonomy
Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the
worst consequence if triggered.                                    <- R8, four bullets:
- **CRITICAL** — <effect classes>      (bands are effect classes, never mechanisms;
- **HIGH** — <effect classes>           never CRITICAL/HIGH labels inside block bodies)
- **MEDIUM** — <effect classes>
- **LOW** — <effect classes>
An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote
an item for sounding alarming.

## Report Output                                       <- six fixed bullets, always these six
- Findings path: `.ai/audit/07-media/findings.md`     <- R12: derived from the filename stem
- Template: <path> — follow it for <its sections>
- Finding-ID prefix: `MED-`                            <- unique across the set; check before adopting
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime
  evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting current behaviour is a remediation blocker, not a gate    <- R9
```

**What makes it a skeleton and not a template.** Sections, order, frontmatter keys, the `Evidence:`
prefix, the severity bands and the reserved empty-state string are fixed — they are contracts
with the orchestrator and the validator. Everything inside a section is prose the writer must
re-derive from the actual codebase. Ten of sixteen existing files repeat the discovery sentence
in their own words `[C]` §2.2; keep that freedom.

---

## 3. Block formulation rules

The core deliverable. Four parts, in this order: **title → obligation → evidence**. Everything
else is optional decoration.

### 3.1 Rules

**B1 — The title names the subject and the question, never the mechanism and never the file.** A
reader who has never seen the repository must be able to say what will be examined.
✅ `### 2. Ingestion admission: which limits exist and where each is actually applied`
❌ `### 5. Scalability Invariants` (a category) · `### Step R1 — Run the Full Test Suite` (a command) `[C]` FM1.

**B2 — The title may be long and must contain a colon or a relative clause when the block has two
halves.** Half the failures in audit output come from one half of a two-part question being
answered: `### 3. Metadata removal: which layer strips, which processes reach it, and what the
re-encode changes` `[C]` `07-media` b3 disambiguates three obligations in the title alone.

**B3 — Open with a state-of-the-world verb from a closed set: Establish · Enumerate ·
Inventory · Derive · Trace · Compare · Confirm or refute · Measure · Record · Judge.**
Never `Verify that X` (names no object), `Check that…`, `Ensure that…`, `Make sure…` `[C]` §5.2.
`Measure` only where a number is genuinely expected.

**B4 — Chain sub-questions with "and establish / and compare / confirm or refute / ask whether /
and record", so each is separately answerable and the block can be split across helpers without
losing the thread.** `[C]` `03-db-concurrency` b5.

**B5 — Include the counter-case explicitly.** Every block should contain one construction that
names the thing an auditor would otherwise skip: the direction no tool checks, the surface listed
as privileged only in intent, the declaration no path consults, the second gate on one path `[C]`
`07-media` b7 ("difference-based tooling is one-sided by default"); `15-authorization` b4 ("Do not
presuppose the enumeration is complete"). This is where most of the audit's real findings live.

**B6 — State the finding rule as a hypothesis with a shape, not as an instruction.** ✅ "treat Z
as a finding candidate until its persistence is demonstrated"; "a `X` that is not `Y` is a
finding"; "a time bound does not bound a rate, and a count per flow does not bound bytes" `[C]`
`07-media` b8. ❌ "Check that limits are enforced" — unfalsifiable.

**B7 — Forbid the count assumption.** Where a population exists, demand it be derived:
"derive the site count rather than assuming it", "Derive, do not assume: inventory every…"
`[C]` `07-media` b2, `06-pii-consent` b3. This is the cheapest defence against an auditor
accepting a plausible-looking enumeration.

**B8 — Exactly one `Evidence:` line, last in the block, literal prefix, semicolon-separated
fragments.** No file path, no command, no "N/A".

**B9 — At least one evidence fragment must name a reproduced or measured observation**
(`one …`, `an induced mid-write failure`, `one request authorised for a resource that is not
there`). Enumeration alone cannot evidence a defect that *is* an absence.

**B10 — When the block's target is an absence, the evidence line names the absence**, plus a
reached/un-reached verdict: "with its named home **or its absence**"; "with a reached/un-reached
verdict" `[C]` §4.6.

**B11 — Say once per file how an unverifiable property is handled, and require the residual to be
recorded as a limit on the report, never as a finding.** "an unreachable suite is a limit on the
report, never a finding" `[C]` `11-test-coverage`.

**B12 — One in-block deferral clause where the block strays into another zone.** One sentence,
naming the phase number. "Locking and repeat-run safety are another phase's." `[C]` `07-media` b7.
Never a whole deferral paragraph — that is what `## Purpose` is for.

**B13 — No counts about the system, no counts about method.** "Enumerate every entry surface" is
fine; "check all 8 dimensions" is not.

**B14 — Ban these words outright:** `Verify that` (as an entire block) · `Check` · `Ensure` ·
`Make sure` · `MUST` · `Step` · any path-looking string (`/`, `.md`, `.py`, `.json`) · any
framework or product noun (`WSGI`, `ASGI`, `Django`, `FastAPI`, `React`, `ORM`, `Swagger`,
`OpenAPI`, `admin`, `templates`, `bcrypt`, `localStorage`, `tsconfig`) · any count attached to
the audited system.

*Where two practices conflict — capability name versus parenthetical example:* parenthetical
technology examples **hurt** and should be banned even though they feel clarifying. The auditor
is a strong pattern-matcher; a technology name is read as "the instance is here", and after a
framework swap the prompt simultaneously anchors the auditor to the wrong artefact and licenses a
finding against a component that no longer exists `[C]` FM3, FM10. Exception, used sparingly: a
*vocabulary* of roles named as a list, not a mapping — "process bootstraps, serving entry
points, background-loop entry points" tells the auditor the *kinds* to look for without claiming
one exists `[C]` `01-entry-architecture` b2, minus its WSGI/management-command nouns.

### 3.2 Before/after, from files in this repo

**Ex. 1 — legacy check-table row → block.** `01-audit-backend.md`, `### 3. Access Control &
Security`, one of eight rows:

```
| Audit Trail | Security-relevant events (login, permission changes, data access) are logged
              | for forensic analysis. |
```

It names a property, not a task: the auditor cannot tell what to enumerate, cannot resolve
"security-relevant", and cannot tell whether "logged" means emitted or queryable. The dimension's
`**Evidence required:**` sends the auditor to a linter step about credential leaks — unrelated.

> **Audit trail — what an event must be recorded to be reconstructable**
>
> *Establish every security-relevant state change the system records — identity changes,
> privilege changes, and access to a resource whose owner is another party — and for each, what
> the record names: who, what, which resource, and when. Then establish whether the record can be
> *read back* as a reconstruction: a reader with access to the recorded fields, a stable
> correlation handle across the steps of one event, and a clock the reader can order by. An event
> that is emitted but not queryable is a finding; so is one whose recorded fields cannot identify
> which resource was touched.*
>
> Evidence: the event inventory with the fields each record names; one event reconstructed from
> the recorded fields alone; one event that cannot be ordered against its neighbours.

**Ex. 2 — legacy dimension table → blocks.** `01-audit-backend.md` `### 5. Code Quality &
Maintainability` is eight rows (Type Safety, Dependency Clarity, Consistent Conventions,
Documentation Clarity, Testability, Async Correctness, Observability, Dependency Hygiene) whose
evidence is *"Linter and type-checker output IS the evidence"* — i.e. eight angles, one pass,
gated on a toolchain the prompt prescribes. The set already re-derives these as eight independent
blocks in `10-audit-code-quality.md` (QLT 1–8) `[C]` §6.5. Rewrite pattern, using the one row
most likely to be misread:

> **Rule 7 — Dead definitions and unreachable registrations**
>
> *Establish every definition, registration, route and periodic operation that no live path
> reaches — not called outside tests, guarded by a condition that cannot vary, or registered on a
> surface nothing dispatches to. Do not presuppose the enumeration is complete: a definition
> reachable only from another definition that is itself unreachable is still dead. Treat a
> shipped test asserting a dead path as a remediation blocker, not as a reachability argument.*

**Ex. 3 — modern block that still leaks framework nouns → durable rewrite.**
`01-audit-entry-architecture.md` block 2, current text:

> *Enumerate every entry surface — process bootstraps, the WSGI serving module, container and
> command-line entry scripts, background-loop entry points, management-command dispatch — and for
> each establish what work happens at import versus what is deferred.*

"WSGI serving module" and "management-command dispatch" are Django constructs. This repository is
FastAPI: `src/mkobi/main.py`, no `manage.py`, no `admin.py`, no `templates/` `[C]` FM10. The
prompt survives the framework swap it was written against only by accident.

> *Enumerate every surface the system can be started or entered through — the process bootstrap
> for each long-lived component, any container entry declaration, one-shot administrative or
> maintenance invocations, and any registration made outside a request. For each, establish what
> work happens when the surface is loaded versus what is deferred to first use.*

Same angle, same evidence, no technology named; the vocabulary is the *kinds* of entry surface
that exist in any stack. The same rewrite applies to `15-audit-authorization.md` block 3, whose
enumeration head reads *"the framework's own administrative interface, the per-model overrides
inside it"* — "framework" is a placeholder noun naming nothing durable; it becomes *"any
administrative surface exposed by the platform or its libraries, the narrower overrides layered
on it, a privileged path that hands off to a second gate, and any surface described as privileged
only in its documentation."* The counter-case is preserved, because it was the valuable part and
it is technology-free.

**Ex. 4 — prescribed procedure → capability block.** `01-audit-backend.md` `Step R0 — Ensure
Docker Environment is Running` (duplicated in six files at line 40, all pointing at
`docs/11-guides/docker.md`) `[C]` FM2. It is not an audit block: it prescribes an operation on
the *auditor's* environment, hardcodes a documentation path, and its failure invalidates every
block that would cite it. There is no durable rewrite of a step — **the block is deleted**, and
what it was protecting is restated as a capability:

> *Establish what the deployment requires in order to be exercised at all — the services, the
> migration state, and the seeded reference data — and which of them the repository documents as
> prerequisites rather than assuming. Record which prerequisite could not be satisfied, and treat
> every finding that depends on it as unverified rather than absent.*

The zone the step was implicitly protecting (boot-time schema availability) is already owned by
`01-audit-entry-architecture.md` b6 `[C]` §6.5.

**Ex. 5 — mechanism-keyed check row → rubric entry.** `03-audit-database.md`
`| No missing indexes on large tables | Query analysis shows no full table scans. |` `[C]` FM7: the
row cannot fail (it asserts the absence of a defect as its own check), and its evidence is a
method. Restated as a block:

> **Index inventory against real query predicates**
>
> *Derive the predicate inventory from the queries the application actually issues, then compare
> against the access paths the storage engine actually uses for those queries. Ask whether a
> predicate is declared without a supporting access path, and whether an access path serves
> queries its columns no longer discriminate between.*
>
> Evidence: the predicate inventory with, per predicate, the access path used or the measured
> full-scan; one predicate with no supporting access path.

---

## 4. Durability techniques

Each technique is a way to make a sentence outlive the code it describes.

**D1 — Capability-scoped, not artefact-scoped.** Name what the subsystem *does*; the
implementation is discovered. *Before:* "the tests under `tests/unit/`". *After:* "the test
population whose assertions about this domain would fail if the property were broken."

**D2 — Describe behaviour, not components.** A component can be renamed, split, or replaced by
three components; the behaviour cannot. *Before:* "the JWT validator". *After:* "the code that
decides whether a presented credential is acceptable, and what it returns when it is not."

**D3 — Define the zone by its responsibility *and* its trust boundary.** The pair survives any
stack. *After:* "the boundary that mediates untrusted input between the caller and business logic,
plus the decision it makes about each input." Trust boundaries are architectural, not technological;
`[A]` OWASP ASVS V1.4 asks for exactly this ("clearly separates trusted and untrusted components")
in words that outlive any framework.

**D4 — Name the *kind* of thing, never the instance.** "the freshness/version token", "the
selection predicate", "the trust anchor", "the test schema" `[C]` §4.7. Rule of thumb: if you can
prefix the noun with a hyphen and still have a meaningful phrase, you have named a kind.

**D5 — Use "discover the concrete instance" explicitly, once per file, as a licence.** Without it,
an un-named artefact reads as "forgotten to include". *After:* "This file names what to examine and
under which angle; the executing auditor discovers the concrete artifacts." `[C]` the sharpest
sentence in the set.

**D6 — Prefer invariants over implementations.** An invariant is a property that must hold after any
refactor: "dependencies point inward; the domain does not import the transport"; "an operation that
reads, decides, then writes re-asserts the predicate its selection used". These survive renames and
moves and fail usefully. `[C]` `01-backend` §1's Layer Isolation / Dependency Direction rows are the
best rows in the legacy family precisely because they are invariants — they just need to become blocks.

**D7 — Mark deliberate asymmetry as a non-defect in `## Purpose`, once.** Otherwise every block below
it becomes a false-positive source. *After:* "Design deliberately asymmetric between processes, tiers
or transports is not a defect on its own. Report it only where the code's own documentation
misstates it." `[C]` `01-entry-architecture`. The second sentence is the important one — it converts
a suppressed class of findings into a sharper one.

**D8 — Express "there may be several" without assuming how many.** Conditional existence is the main
rot vector in a multi-process prompt: "the bot tier" becomes false and everything about it is skipped.
*Before:* "an asynchronous event-driven bot tier". *After:* "any event-driven inbound component, if
the deployment has one" `[S]`.

**D9 — Make the absence path explicit and cheap.** Most rot is silent because a prompt pointed at
something that moved and the auditor could not tell a stale reference from a missing file `[C]` FM2.
*After:* "Where a property cannot be settled in the environment at hand, establish it from what is
observable and state plainly what could not be verified and why" `[C]` `12-production-ops`.

**D10 — Encode the count as "derive it".** Absolute numbers in the prompt become false the moment the
codebase grows. *Before:* "the four background jobs". *After:* "the job registry" + "derive the site
count rather than assuming it" `[C]` `07-media` b2.

**D11 — Anchor the vocabulary to consequences, not to names.** A severity band phrased in effects
("bytes destroyed while a live record still names them") survives the framework swap that breaks a
band phrased in mechanisms ("an unhandled ORM error"). `[C]` `07-media` CRITICAL vs `01-backend`
"A broken import is CRITICAL".

---

## 5. Composition rules for a phase set

N phase prompts must divide the architecture without overlap, and without each one embedding the
whole map. `[A]` context-engineering argument: each phase is a separate context window with its
own finite attention budget; repeating the architecture in all 20 files costs 20× the budget and
buys nothing the auditor cannot read from the repository in one grep.

**C1 — The unit of ownership is a *responsibility*, not a directory.** Ownership is assigned by
"which question does this phase answer", never "which folder does it read". A phase whose zone is
a folder dies the day a module moves.

**C2 — Ownership vocabulary is a closed list, reused verbatim.** The set already has one
(`[C]` §5.1): process/topology · data/state · decision/gate · contract · verification posture. A
new phase picks from it rather than inventing. The practical test: can you write the phase's
Purpose using only those nouns? If not, the zone is not yet understood.

**C3 — Declare boundaries in `## Purpose`, one paragraph, in a fixed order: *owned here →
deferred, with numbers*.** Three precision levels, in increasing order of preference: zone
deferral → split ownership of one question → transfer log when a zone is absorbed from a deleted
phase `[C]` §2.6. The 08×13×14 cache-key split is the model: three files, one paragraph,
identical wording, no drift.

**C4 — Adjacent zones are negotiated, not partitioned.** Where two questions genuinely share one
decision, name the seam in *both* files with the same words — `[C]` the 04×15 auth split is
negotiated in both directions. Rule: if A defers to B, B must not defer to A on the same seam.
This is the only reliable way to detect a bot's mistake during review.

**C5 — Numbering is stable identity.** Keep the filename; migrate in place `[C]` §4.17 (the
`99` file is the precedent). Derive the findings path from the filename stem, and never let
frontmatter `name`, filename and output path disagree `[C]` FM12 — the orchestrator computes the
output path from the filename, so drift means a phase writes two directories. Assign numbers by
*retiring* them, never by re-sorting by topic: topic-sorted renumbering breaks every Scope
Boundaries paragraph in the set.

**C6 — Shared angles are defined once and referenced, never re-instantiated per phase.** This is
the set's live defect. Two angles are currently copied:

- *"A control that runs, reports clean, and examines nothing"* appears five times — `11` b7,
  `12` b3, `13` b2, `14` b9, `99` b2 — as five near-verbatim paragraphs differing only in the
  domain noun. `[C]` §2.6 item 2.
- *Cross-resource / multi-resource side effects* are claimed three times with no mutual deferral:
  `01` b7 ("everything the processes coordinate through"), `03` b10 ("which resource is the real
  unit of atomicity"), `07` b11 ("per operation whether it is mutually excluded"). `[C]` §2.6
  item 1. A single multi-writer race is currently filed three times or zero times depending on
  which block the auditor reaches first.

Fix, without adding a new file to the phases directory `[S]`: give each shared angle a **name and
a single canonical one-line definition** (e.g. *the vacuous-control angle: for each control, three
separate questions — does it exist, what scope does it declare, what did it actually examine*),
state it once in the phase set's shared conventions file, and have each phase reference it with
its own binding in one clause. The duplication is only defensible if the instantiations are
*deliberate domain bindings of one angle* — which is what the five instantiations claim to be but
have not written down.

**C7 — One phase per first-class subsystem; refuse a phase whose zone is a cross-cutting theme.**
`90-audit-integration.md` is the cautionary case: six steps that map 1:1 onto 02+04+09+15 and
whose unique coverage is empty `[C]` §6.2. If a phase's blocks can be filed under other phases'
prefixes without loss, the phase is a merge, not a phase.

**C8 — Prefer many narrow phases to few broad ones, down to the point where a block can be
delegated.** `[C]` FM5: an M dimension bundling six to eight questions cannot be split across
helpers and produces one undifferentiated pass.

**C9 — Validator owns the seams.** Phase 99 adjudicates *between* phases — merge, namespace
collision, code-vs-doc ruling. Every C4 seam should have a corresponding validator block, so a
missed deferral is caught once centrally rather than by N auditors guessing.

---

## 6. Reporting contract

**RC1 — A finding = location, invariant, evidence, consequence, fix.** All five or it is not a
finding. "Violates invariant X" is explicitly not a finding: name the exact role that violates the
property and the exact consequence `[C]` §2.5.

**RC2 — Evidence must be reproducible by someone who did not run the audit.** This is the
discipline that distinguishes an auditor from a reciter, and it is why B9 (one reproduced
observation per block) is the load-bearing rule. A finding whose evidence cannot be re-derived is
either a guess or a design opinion; both should be rejected.

**RC3 — A shipped test asserting the current behaviour is a remediation blocker, not a gate.**
State it in `## Report Output` (it is already there in eight files `[C]` §2.5) — otherwise the
auditor silently downgrades a real defect to "working as intended, tested".

**RC4 — The empty state is a reserved exact string, and the report must distinguish "clean" from
"not run".** `No problems found in this phase.` `[C]` is the corpus's one shared constant and
should be protected verbatim. Pair it with a **residual line**: what was not verifiable and why
(RC5). Without the residual, an unreachable environment produces a byte-identical artefact to a
genuinely clean one, and the two are indistinguishable forever.

**RC5 — "Cannot be verified here" is a *limit on the report*, never a finding.** Stated once per
file `[C]` §4.13. But note the tension honestly `[S]`: `problems-only: true` plus "record the
residual" is the one place the contract contradicts itself — the residual is not a problem, so it
is not "only problems". Resolve it in favour of the residual, because the alternative (silent
skip) is strictly worse and unrecoverable. Put the residual in a fixed footer, not among the
findings.

**RC6 — Answer the false-positive/false-negative trade deliberately.** `problems-only` already
biases toward silence. That is the right default for an audit whose output is *consumed by a
human deciding what to fix*: a false finding costs a reviewer more than a missed low-severity item,
because it burns trust in the whole report `[S]`, and repeated false positives cause reviewers to
skim (the "alarm fatigue" failure documented across monitoring and, by extension, any alerting
channel). Counter it with three mechanisms rather than with hedging language:
- severity anchored to effect *and* present state (`rate what is true now, not the worst
  consequence if triggered`) `[C]` — the single most effective anti-inflation device;
- "an empty band is a valid outcome" `[C]` — removes the incentive to fill bands;
- "do not promote an item for sounding alarming" `[C]` — names the specific failure.

Do **not** add "be conservative", "only report high-confidence issues". Hedging instructions make
an agent either silently narrow its scope or silently self-censor, and neither is visible in the
output `[S]`. The falsifiable filter is RC2.

**RC7 — Never let a clean block write itself out of the record.** Because the report is
problems-only, an auditor that examined block 5 thoroughly and found nothing produces no trace of
block 5 at all. Over a phase set this is indistinguishable from never running the phase `[S]`.
Cheapest fix that preserves the problems-only contract: the phase's `Evidence:` obligations are
artefacts that must exist *somewhere* — require them in an appendix or a coverage ledger rather
than in the findings body. Without this, coverage is unauditable and a reviewer cannot tell a
thin audit from a clean one.

---

## 7. Anti-pattern catalogue

Each with a one-line detection heuristic — a reviewer should be able to apply it without running
an auditor. AP1–AP14 are observed in this repo's current set `[C]` (analysis report §3); AP15–AP19
are extrapolations from them `[S]`.

| # | Anti-pattern | Detection heuristic |
|---|---|---|
| AP1 | **Mandated procedure gates the audit** | The file contains "Before evaluating…" / "you MUST complete these steps", or a block's evidence cites a step number. |
| AP2 | **Hardcoded path used as an instruction** | Grep the file for a path-shaped token (`/`, `.md`, `.py`) — one hit in prose is a finding. |
| AP3 | **Toolchain assumption as universal truth** | The prompt states an expectation that is a product fact ("verify `strict: true`", "bcrypt, scrypt, or argon2", "not in `localStorage`") rather than a property. |
| AP4 | **Blocks depend on each other** | Any block whose Evidence line names another block, a step, or a phase-wide variable. |
| AP5 | **Block too broad to execute in one pass** | A block whose title names a *category* ("Security", "Scalability") rather than a question, or whose body bundles three unrelated enumerations. |
| AP6 | **Duplicated coverage across files** | Take any sentence from a block and grep the phases directory; a second hit in a different phase is a declared-or-undeclared overlap. |
| AP7 | **Row that cannot fail** | Any check phrased as an affirmative ("No missing…", "Everything is aligned") — in a problems-only report it is dead weight at best. |
| AP8 | **No boundary declaration** | The Purpose lacks a `Scope Boundaries` paragraph naming phase numbers, and the file's zone appears in another file's block. |
| AP9 | **Boilerplate bloat / counterfactual** | The same paragraph appears verbatim in ≥2 files, or the file describes a document it forbids producing. |
| AP10 | **Framework noun leak** | Grep for any of: WSGI, ASGI, Django, FastAPI, React, ORM, admin, template, Swagger, OpenAPI, manager, app, migration-tool names. One hit means the prompt is framework-bound. |
| AP11 | **Mechanism-keyed severity** | A CRITICAL/HIGH label appears inside a block body rather than in the rubric; or a rubric band names a mechanism ("a broken import") rather than an effect. |
| AP12 | **Name / path / number drift** | Filename stem ≠ frontmatter `name` ≠ findings directory, or two files share a phase number or a finding-ID prefix. |
| AP13 | **Referenced shared artefact does not exist** | Every `Template:` path in the set resolves to nothing. Currently true for all 25 files `[C]` FM13 — the highest-leverage defect in the framework and invisible inside the phase set. |
| AP14 | **Report Output stated in a bespoke shape** | The section is not the six-bullet form; count how many shapes exist across the set — more than one is a finding. |
| AP15 | **Instruction implies a specific action ("step")** | A block body contains a command-shaped imperative ("run", "start", "follow the instructions in", "compare against X's spec"). The auditor is being told what to do, not what to establish. |
| AP16 | **Implicit architecture assumption in Purpose** | Purpose names a component as existing ("an async bot tier", "a search subsystem") rather than conditionally ("any event-driven inbound component, if the deployment has one"). |
| AP17 | **Audit-of-the-auditor missing** | The set contains a block that examines whether controls examine anything, but no requirement that the auditor record what it covered. Vacuous controls and vacuous audits are the same defect `[S]`. |
| AP18 | **Reflexive use of "verify"** | Any block opening with "Verify that…". It names no object and is the M family's verb. |
| AP19 | **Asymmetry treated as defect by default** | Purpose lacks the deliberate-asymmetry sentence, and ≥2 blocks compare two peers (two tiers, two transports, two paths) — the prompt will generate a finding for every intentional difference. |

---

## 8. Open questions and where I disagree with the current set

**D1 — I disagree with `audit-phase-refine.md` §1.3's "checklist style".** A checklist is the wrong
metaphor for an audit prompt and it is the direct ancestor of the legacy tables: a checklist row
is a *thing to verify*, an audit block is a *question to answer*. Every legacy failure in the set
comes from treating the phase as a checklist. Keep "concise"; drop "checklist". Recommended edit:
"Make each block short, independent, and phrased as a question" — one word changes the output.

**D2 — I disagree that the framework noun leak (FM10) is a cosmetic issue to be cleaned later.**
`_conventions-analysis.md` calls it "the single most important forward-looking finding" but its
verdicts are all "keep as reference". That is inconsistent. A prompt naming WSGI in a FastAPI
repository is not a reference implementation of the modern style; it is an instance of the
anti-pattern. `01-audit-entry-architecture`, `05-ad-lifecycle`, `06-pii-consent`, `14-audit-i18n`
and `15-audit-authorization` should be "refine in place" for this reason alone. My prior:
**these five files contain 100% of the residual framework nouns in the modern family**, and the
rewrite is mechanical (B2 example above is the template).

**D3 — The `problems-only` contract and the residual requirement contradict each other, and I
resolve it in favour of the residual** (RC5). The current set states both and never reconciles
them. Fix in one place: `## Report Output` should say the report contains findings plus a fixed
residual footer. This is a real change to the contract and should be argued for, not slipped in.

**D4 — I do not accept "keep the block count at 8–13" as a *rule*.** `[C]` §4.16 gives it as
best practice, but the observable is correlational — the 8–13 files are the ones that were
written well. A better invariant: **every block must carry at least one evidence fragment that no
other block in the set carries**. That is checkable by diffing the evidence lines, and it is the
property the count is proxying for. Same for file length: the real rule is one-screen Purpose.

**D5 — Open question: should the shared angles (C6) live in a new file?** The set needs one
canonical definition of the vacuous-control angle and one of the cross-resource angle. Options:
(a) a shared conventions file the phases reference — one more artefact to rot, but the analysis
report already wants a shared artefact; (b) keep the instantiations and accept drift; (c) give each
angle a stable name and define it once in the validator phase, which already audits the
namespace. I lean (c) — it uses a file that exists, is already the owner of cross-phase seams
(C9), and adding one concept to it costs nothing structurally. This is a judgement call the team
should make explicitly.

**D6 — Open question: is a 30–60-word severity band still one band?** `07-media` CRITICAL is
three effect classes in 45 words `[C]`. That is at the limit. Beyond ~60 words a band stops being
a decision procedure and becomes prose; my view is that the fix is to cap bands at three effect
classes and move the rest into blocks, but I have no evidence for where the cap sits.

**D7 — Open question: nothing in the set evals a phase prompt.** There is no way to know whether a
refined phase is better than the original. Cheap probes, in increasing cost:
1. **Coverage probe** — grep every phase for the AP1–AP19 patterns; count. This is nearly free
   and catches eight of the fourteen observed failures.
2. **False-premise probe** — hand a phase to an auditor together with a codebase that violates one
   of its *implicit* assumptions and check whether it reports the assumption's absence or files a
   finding against the assumed component. This is the only probe that catches AP16, and it is the
   one nobody runs.
3. **Reviewer re-derivation** — have the validator independently re-derive one finding's evidence;
   a finding the validator cannot reproduce is a prompt defect as much as an auditor defect.

(1) should be a step in `audit-phase-refine.md`'s final consistency check. It is mechanical and
would have caught FM1–FM14 automatically.

**D8 — Where the analysis report and I agree, for the record.** Zone-not-steps, one question per
block, artefact-not-command evidence with one reproduced observation, effect-keyed severity, the
protected empty-state string, in-place migration keeping the filename, and the three coverage gaps
(client tier, ingestion pipeline, schema/index integrity) are all right. This report adds the
properties behind them (§1), the rules that generate them (§3), and five extrapolated
anti-patterns the analysis did not name (AP15–AP19).

---

## Appendix — rule index

Frontmatter → R12 (AP12, AP13) · `## Purpose` → R2, R3, R7, R10, R11 (AP8, AP9, AP16, AP19) ·
blocks preamble → R4, R6, RC3 (AP4, AP17) · `### N.` title → B1, B2 (AP5, AP18) · block body →
B3–B7, B11–B14, D1–D11 (AP3, AP7, AP10, AP15) · `Evidence:` line → R6, B8–B10, RC2 (AP4, AP11) ·
`## Severity Taxonomy` → R8, RC6 (AP11) · `## Report Output` → R9, RC1, RC3–RC5, RC7 (AP14).