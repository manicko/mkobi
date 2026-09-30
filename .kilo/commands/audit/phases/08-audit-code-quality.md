---
name: 08-code-quality
executor: auditor
problems-only: true
---

# Phase 08 — Code Quality

## Purpose

Audits whether the code holds to the conventions the project has adopted, and whether the properties the codebase and its
documentation claim are the properties that actually hold. The lens is the gap between a rule and its enforcement: where each
fixed value lives, which input boundaries validate, what the type checker is configured to catch, how much one unit does, whether
a rule has one implementation, what the declared gates decide, and what would notice if any of it stopped being true. This phase
owns the declared-contract angle — where a contract is declared, whether the declaration is executable, and whether any path
consults it — so any other phase that observes a documented claim contradicted or unenforced defers that observation here. This
file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — owned here: where a fixed value lives and whether the type system constrains it; the constant surface as a
maintained artefact; boundary validation discipline; the configured strictness and the sanctioned-suppression population;
responsibility inside a unit; one rule, one home; the cheap high-volume conventions; the declared-contract angle, as its owner;
and what the declared gates decide and whether anything would notice. Not owned here: settings values, secrets and environment
policy (02); transaction, lock and pooler semantics (03); the mechanism that carries work out of the request path (01); identity
and credential strength (04); what the pipeline derives, writes and replaces (05); artefact lifetime and store-versus-record
reconciliation (06); the inbound surface form, dependency-failure degradation and the mechanism by which an ingress bound is
applied (07); test-suite adequacy and what the suite would notice (09); container, deploy, edge, backup and observability
posture (10); measured cost (11); the access decision and refusal shape (12); the interface's component, state and type
architecture (13); the migration chain's linearity and reversibility, and the index inventory against real query predicates
(14); header, origin, credential and rate-bound policy (15). A codebase need not be clean to be well-made: this phase asks
whether a rule has one home and whether anything checks it, not whether a different design would have been better.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: an inventory
with a stated absence, a static proof that a claimed property does not hold, or a reproduced divergence between two sites; the
method is the auditor's. A passing check is methodology, never a finding. Where a property cannot be settled in the environment
at hand, establish it from what is observable and state plainly what could not be verified and why — an unreachable surface is a
limit on the report, never a finding. Every block's evidence is an artefact that must exist in the report's appendix as a coverage
record, even where the block produced no finding.

### 1. Fixed values: one named home per value, and what bypasses it

*Establish, for every fixed value the system branches on, whether it has exactly one named home, deriving the population rather than assuming it is
complete. Look for a value written as a raw literal at a second site: compared or defaulted as a bare string where a named vocabulary exists, or
repeated inside a surface another tier reads — a declared configuration value, a response shape, a route path, a form field, a persisted column default.
Establish the cross-tier half: a value written once in the serving code and again in the client with nothing keeping the two equal, and whether the
project's own consistency test covers one tier and not the other. Establish which of these values the type system could catch being wrong, and which are
indistinguishable from a plain string at the point of use. A named home that exists and is bypassed is the finding; the literal itself is only the
evidence.*
Evidence: the fixed-value inventory with its named home or its absence; the raw-literal sites grouped by the surface that reads them; one value written in both tiers with no equality check between them.

### 2. The constant surface as a maintained artefact: is anything else maintaining it

*Establish the constant surface as a maintained artefact rather than a registry. Is an identifier family's numbering and ordering documented and
evidently deliberate, or is it a sequence whose only explanation is the sequence itself? Is one vocabulary of fixed values implemented in more than one
structure, and if so whether their memberships agree where they overlap and what the second does with the members the first has and it does not? Is
membership derived outside the vocabulary it belongs to, in a structure the vocabulary's own consumers must know about? Is a private name published in a
public export list? Is a mapping stored inside the vocabulary it belongs to, so reading the vocabulary requires understanding a second structure? Is a
value table constructed inside the function that consumes it, so no second component can consult it and every caller re-derives legality independently?
Is a named vocabulary exported, documented and offered in a surface — a choice list, a constraint, a field — while no code path enforces it? And is a
value's required type enforced where it is declared, or merely assumed where it is read back?*
Evidence: per constant family — numbering convention, membership provenance, export-list contents; every duplicate implementation of one vocabulary with a membership verdict and the fallback its non-members receive; one value table with no reader but its own consumer.

### 3. Boundary validation coverage: which boundaries validate and which do not

*Establish which input boundaries validate and which do not: the transport, the parse, the validation model or its absence, and what reaches persistence.
A boundary is a place where untrusted data becomes a row, and the uncovered ones are the finding, not an exception to be noted. Treat the strictness of
a shared validation base as a claim to verify, not a precondition — a model that does not inherit it, or that sets a permissive unknown-key policy, is a
boundary whose contract differs from the one the base describes, and whether the difference is deliberate must be established from the code and from
whatever records it. Include the boundary whose input is a free-form document that only a later, different process can reject: what the pipeline does
with it is 05's, that the boundary does not reject it is this block's. Where a boundary validates, ask what it validates against — a vocabulary narrower
than the column it guards accepts every value the column would have rejected — and what a field default means when the key is absent, since a default
that is a legal value for "empty" silently overwrites stored content.*
Evidence: the boundary inventory with a per-boundary validation verdict; every model departing from the shared base and the reason recorded for it, or the absence of one; one boundary where an absent key overwrites existing content.

### 4. Type width and the sanctioned-suppression surface: what is enforced, what is silenced

*Establish what the type checker is actually configured to enforce and what it is configured not to: the checking mode, the disabled diagnostic classes,
and the reason the project recorded for each. Never assume a strictness bar the project did not set, and never treat a non-zero diagnostic count as the
finding. The accepted noise is a sanctioned-suppression population, not a zero-error population — establish its size by cause, whether any whole cluster
could be retired by fixing one root cause, and whether each suppression is still warranted at its own site or has outlived the construct it silences.
Then classify every widened annotation as load-bearing or accidental: a parameter typed as a plain string defaulted with a vocabulary member, a
container return with no element type, a variable declared only to satisfy the checker, a cast applied on a read path where the value's type is already
known, a return type broader than every value the function can actually produce. Production code only — a project may legitimately hold its own tests to
a different bar, and a diagnostic in a test file is not this phase's finding.*
Evidence: the checker's configured mode and disabled classes with the project's stated reason; the suppression population by cause; the widened annotations with a load-bearing or accidental verdict each.

### 5. Responsibility inside a unit: how many jobs one unit does, and which is reachable from elsewhere

*Establish, within one unit of work — a handler, a service, a helper, a job function — how many distinct responsibilities it performs: authorization,
locking, validation, business decisions, file work, transformation, persistence, logging — and whether any of them is reachable from anywhere else. A
unit reported only as a line count has not been analysed: report the responsibilities, and ask whether extracting one would change what the tests can
reach. Size is the prompt; the multiplicity is the finding. Include a unit whose bulk is one long literal, one generated block, or one wide data mapping
rather than several responsibilities: a size signal with nothing behind it is not this block's finding, and saying so is as much a result as listing the
responsibilities. The entry-layer boundary and the direction of dependency between layers are 01's; what is examined here is only what happens inside
one unit — and a second copy of one rule inside the same layer is still in scope, however small the layer is.*
Evidence: per oversized unit, the responsibility list; one responsibility with no reachable caller and where the test suite can reach it; one large unit with a single responsibility.

### 6. One rule, one home: whether exactly one implementation exists

*Establish, for each rule more than one component must obey, whether exactly one implementation exists, deriving the rule set from the code rather than
from a list of rules the repository documents. A byte-identical copy is a second site the next change must be made in; a near-copy is one the two have
already begun to disagree on; a second implementation with a different threshold, ordering or tolerance is a live divergence. Include the same operation
written once per session mode, and the same rule expressed as a bare value in one place and as a named vocabulary member in another. Where a site
deliberately does not share the common implementation — a re-export package that exists to keep an import direction, a shared helper kept free of an
error-handling or dependency contract a specific caller cannot take — establish that the reason is recorded where a reader of that site will find it,
and that the reason still holds against the code as it is now. A site that does not share the common implementation is a claim to establish, not a
duplication to file.*
Evidence: the rule-to-implementation-count map with the rule set derived rather than assumed; one rule whose implementations disagree; every deliberate exclusion with its recorded reason and a holds or does-not-hold verdict.

### 7. Convention compliance: the cheap high-volume rules, and which of them are broken

*Establish the mechanical rules that are cheap to check and cheap to violate, and record the corpus behind each so a rate is not mistaken for a method:
standard-output writes on a production path, including a debug-gated one and one reached only at start-up; the language of comments, log records,
docstrings and error text that is not user-facing; naming; import ordering, an import deferred into a function body to dodge a cycle that no longer
exists, and an import-time side effect whose correctness depends on some other module having been imported first. Establish the declared project rules
themselves as artefacts: a per-file or per-directory exception in the configuration naming a path that does not exist, a type stub declared for a
library the project's own rules exclude, a start-up self-check listing a module nothing imports, and a formatter configured separately from the linter
so that running one leaves the other's findings in place. Include code that is present, reachable and referenced by nothing, where the question is what
it was for rather than whether to delete it; the answer may be a feature that is not switched on yet, and that too is a fact to establish. User-facing
text is 13's.*
Evidence: the convention sweep with the corpus behind each rule; the declared-rule inventory with a path-exists verdict each; the unreferenced-definition list with the intent of each.

### 8. Declared contracts and their enforcement point: whether anything checks the claim, and whether anything reaches it

*Establish, for every property the code or its documentation asserts — in a docstring, a comment, a named guard, a validation hook, a checklist, an
endpoint description — whether anything checks it and whether anything reaches it. A declared invariant no reachable caller enforces is documentation; a
documented rule the code contradicts misleads every later reader, including a description of an audience narrower than the path actually admits, a claim
that a sequence of effects is all-or-nothing, and a claim that an operation is free of a race it can still lose. A comment that describes a condition
differently from the condition the executing path applies is itself a finding here, not a source: the answer to "what does this gate check" comes from
the path that runs, never from the prose above it. Also ask whether the project's own guidance is written where the code is being changed, or only in a
rules file no contributor opens at the moment they are making the change. This phase owns that angle: any other phase observing a documented claim
contradicted or unenforced files the observation here.*
Evidence: the declared-property inventory with an enforcement point or its absence; one documented rule the code contradicts; one declared audience narrower than the path admits; one validation hook no caller reaches.

### 9. The gates the project declares: where each is wired, what each decides, and whether it can be run the way the pipeline runs it

*Derive the declared-check inventory from the project's own command surface and configuration — linting, type checking, the test suite, the client-side
gates — and per check establish what it decides, what value it compares against, where it is invoked from, whether it is reachable by a contributor the
way the automated path reaches it, and whether the aggregate entry point that contributors are pointed at invokes every gate the project declares or
only a subset. Establish whether a check present in configuration is actually executed or merely declared, and whether any of these gates is wired into
an automated path at all rather than only run by hand. Do not assume a gate exists until one is found running; its absence is the finding, not a failure
of the block. A threshold expressed as a fixed number rather than a delta is part of the same question. Container and deploy gates are 10's; what a test
suite would notice is 09's; the vacuous-control angle is 99's.*
Evidence: the gate inventory — which checks are declared, where each runs, what it covers, and whether it is reachable; one check present in configuration that nothing invokes; one aggregate entry point that omits a gate the project declares.

### 10. Schema drift: whether anything would notice, and which rows are written by code rather than by a migration

*Establish, for every model change, whether the schema history records it — and then, separately, whether anything would fail if it did not. The claim to
test is not "a migration exists" but "something fails when one is missing": establish whether a drift check runs at all, over which paths, and whether a
check present in configuration is actually executed on every change or declared and never wired in. Establish separately whether a path that mutates schema
or reference data rather than applying a migration is idempotent if run twice, whether it runs where it was not expected, and whether its effect lands
before the process begins answering; the population of such paths is 01's. The chain's linearity and reversibility, and the index inventory against real query
predicates, are 14's.*
Evidence: the drift-check inventory — which exist, where they run, what they cover; one model change with no recorded migration, or the confirmation that none exists; one non-migration row-writing path reproduced on a second run, and whether the effect changed.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed list of mechanisms, so a defect whose mechanism is not named here still lands by the consequence it is producing.

- **CRITICAL** — a wrong or lost value is in storage now, or the only thing that kept a rule true for everyone is gone: a stored value no rule ever constrained, a field default that overwrites stored content when the key is absent, two implementations of one rule whose copies already disagree on a value the system acts on.
- **HIGH** — silent today, and the next change is guaranteed to be made wrongly in the same place: a value with two homes, a declared invariant nothing enforces, a documented audience narrower than the path admits, a rule that must be changed in several places with no single discoverable one, schema drift no gate would notice, an aggregate entry point that silently omits a declared gate.
- **MEDIUM** — a bounded correctness or operability gap with a specific, limited audience: an unvalidated boundary on a non-critical path, a widened type on a value nothing branches on, a duplicated helper with no divergence yet, a constant surface whose conventions are undocumented, a convention rule broken in a narrow surface only, a declared rule whose reason is recorded nowhere.
- **LOW** — documentation, reachability and hygiene drift with no runtime consequence today: a declared rule no caller reaches, a private name in a public export list, a comment restating the code, an unreferenced definition nobody has explained, a linter exception pointing at a path that does not exist.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/08-code-quality/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `QLT-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
