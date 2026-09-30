---
name: 09-test-coverage
executor: auditor
problems-only: true
---
# Phase 09 — Test Coverage

## Purpose

Audits the assurance the suite appears to carry against the assurance it delivers: what the product decides that an assertion would reject, what a test substitutes for
the real thing and what that substitution makes unobservable, what the shared setup manufactures by default, what each boundary is asserted from, how the harness
isolates and what it cannot host, what varies between runs, and what stands between a change and a landing. This file names what to examine and under which angle; the
executing auditor discovers the concrete artifacts.

**Scope Boundaries** — this phase owns whether the suite would notice a wrong product decision, the fidelity of what it asserts once it does, the harness as a system, and
the gates that run before a change lands together with their effective scope. Other phases own: production-code convention, fixed-value discipline and dead code (08);
the deployed container, its health contract, backup and restore, the operator's log stream and the operational runbooks (10); measured latency, throughput and
per-request cost (11); per-request authorization decisions and what a refusal discloses (12); transaction, lock and pooler semantics (03); the migration chain, index
inventory and schema drift (14); parse, aggregate, full recalculation and temporary-file lifetime (05); settings values, secret provenance and environment policy,
including the configuration the harness supplies (02); client-side component, state and accessibility behaviour and that suite's own architecture (13); namespace
rulings and cross-phase conflict resolution (99). The merge-blocking question — whether a change can reach a deployed system at all — is this phase's for the suite and
the aggregate entry point, and 10's for the deployment path; neither files the other's verdict.

A stand-in deliberately installed for every test, and a suite deliberately separated from another by an execution model, are harness decisions to read rather than
defects on their own. Report each only where the property it removes is observed by no test, or where the test layer's own description of itself is contradicted by how
the layer behaves.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: a derived inventory with a stated absence, a
reproduced divergence between two sites, or an observed pass against a decision the test purports to cover; the method is the auditor's. A passing check is methodology,
never a finding, and nothing here conditions a finding on this phase's own list. Where a property cannot be settled in the environment at hand — a suite that cannot be
reached, a real counterpart that cannot be stood up beside its stand-in — establish it from what is observable and state plainly what could not be verified and why; an
unreachable suite is a limit on the report, never a finding.

### 1. Decisions the product acts on, and the value of each an assertion would reject

*Derive, do not assume, the set of decisions the product acts on — a value chosen, a transition permitted or refused, a record selected or excluded, a limit applied, a
derived figure computed — and for each, name the value that would make an existing assertion fail. A decision whose effect no assertion can observe, a returned value
nothing inspects, a refusal whose absence no test would notice, and an assertion holding for every value the decision can take each read as coverage and are not; a
table that enumerates inputs while asserting one shared postcondition discriminates no more than an empty assertion, and a chain in which any one assertion would fail
for a reason unrelated to the property it names proves the chain rather than the property. Include a mechanism whose stated purpose is to fire on one path, and
establish what tests the paths it must not fire on. A branch whose effect nothing observes is a finding.*
Evidence: the derived decision set with a per-decision verdict; one decision whose effect no assertion can observe; one test whose assertions survive the decision being inverted.

### 2. What each stand-in removes, and whether any test observes it elsewhere

*Inventory what the tests actually replace, derived from the substitution itself rather than from any declared convention about what ought to be replaced, and for each
establish what property of the real thing can no longer be observed and whether any test anywhere observes it. Standing in for an external transport is correct, cheap,
and is not this block's finding; standing in for the mechanism that exists to enforce an ordering, a lifetime or a decision leaves that property untested while making
it look tested. Establish which substitutions are installed for every test by default and which are opt-in, and treat a default substitution that a single test
contradicts as a finding about the default rather than about the test. An assertion reduced to matching the shape of source observes the source text rather than the
behaviour.*
Evidence: the stand-in inventory with the property each removes and its install scope; one property observed by no test; one stand-in installed globally that a single test contradicts.

### 3. What the harness manufactures by default: identity, store, schema, environment

*Establish what states, values and configuration the shared fixtures supply by default, whether the product can produce each, and what stays green precisely because it
cannot. A default that silently produces a surprising value turns every consumer into a test of a fiction, and a helper that absorbs a constraint means no test ever has
to satisfy it. Establish the manufactured identity and the manufactured store separately from the schema: a default identity whose level short-circuits the per-object
comparison means no test observes that class of decision at all, and a store that ignores the lifetime its real counterpart enforces makes an ordering untested while
the assertions stay green. Establish separately whether a fixed value the production vocabulary already names is restated as a bare literal by a helper, and whether the
environment the harness supplies at import is a value the product can ever read.*
Evidence: the default-state inventory with a producible or unproducible verdict each; the restated fixed values; the constraints the fixture layer absorbs; one class of decision the default identity cannot observe, and one test observed to pass on it.

### 4. Each boundary, from each side — including the ones every test crosses the same way

*Establish, for each boundary the architecture creates, what is asserted from each side and what from one side only — including the boundary every test crosses in
process rather than over a connection, and the boundary between the test's own persistence session and the one the product manages for itself, where a shared session
means the product's own commit, rollback and teardown are never the ones under test. A behaviour that exists only because two components agree is covered only where
both are exercised, and a boundary crossed in production but substituted in every test is a boundary with no test. Establish first whether a stand-in for a shared
resource is in use: presupposing one produces a false pass, and so does presupposing its absence. Where the defect behind the boundary belongs to another phase, record
the cross-reference and the test that gates its remediation rather than re-filing it.*
Evidence: the boundary inventory with a per-side assertion verdict; the boundaries asserted from one side only; one child-resolved path returning its object with no parent constraint; the cross-references to findings owned elsewhere, each with the test that gates their remediation.

### 5. The harness as a system: schema build, isolation model, marker wiring, and the separately executed suites

*Establish how the test schema is built, what reference state is restored, how parallel execution partitions and isolates, what bounds a runaway query, what each
registered marker is wired to, and what the invocation's substitution semantics cost a caller that overrides them. Then treat the deliberate arrangements as claims to
verify rather than defects: a step excluded from the fast path where nothing detects the failures it would otherwise surface, helper universes separated by an execution
model neither can cross, and a shim retained so an existing patch target still resolves. Establish what each costs, what still holds it in place, and what a change
would have to preserve. Establish which tests the harness cannot currently host and which gap each explains, and what a data-level schema change does to the run — its
effect, not only whether the migration applies cleanly and twice — since a schema built by a strategy other than the migration path cannot see it.*
Evidence: the schema, reference-state, isolation and marker-wiring facts; the override-substitution delta; the deliberate arrangements with what holds each in place; one test the harness cannot host, and the gap its absence names.

### 6. Reproduction: what varies per run, and what a shared resource carries forward

*Given a red run in automation, establish whether it can be reproduced: what varies per run and whether the variation is recorded where a reader of the log will find
it, what is unbounded while a test runs, what a parallel run does that a serial run does not, and what a reused resource carries forward into the next run — including a
resource shared between runs whose contents are cleared by age rather than by ownership. Do not settle for running the suite twice and comparing: order-independence is
a per-test property and not a suite property, so establish which tests depend on a resource another test left behind and which depend on being first. A test that reads
the same clock, the same ambient environment or the same process-wide state as the code it exercises is not isolated from the code it tests.*
Evidence: the per-run variable inventory with what is recorded and where; the unbounded resources and their owners; the process-wide state a test shares with production code; one resource observed to carry state from one run into the next; the recovery procedure for a red automated run.

### 7. What runs before a change lands, and what each gate's scope excludes

*Establish, for each declared gate, whether it is loaded, whether it is green, what its scope excludes, and what invokes it — an entry point a person must choose to run
is a report, not a gate. Distinct absences must be told apart: a gate declared and never loaded, a gate loaded and red, a gate whose scope omits a whole process tree,
and a configuration sitting in the repository that is never read from the directory the gate runs in. Where several checks are chained behind one entry point, establish
which of them it omits; a target that chains several checks while leaving a whole process tree outside its scope is the case to find. Bind the shared vacuous-control
angle here, in the gate-and-suite form: for every control that can emit a verdict on this repository, establish what it is configured to examine and what it actually
examined, and never infer a missing tool or treat a diagnostic count as a defect by itself. The population of diagnostics in production code and its sanctioned
suppressions is 08's.*
Evidence: the declared-gate inventory, loaded or not, green or not, scope, and what invokes it; the gates whose scope excludes a process tree; the aggregate entry point with the check it omits; the controls with the item count each examined.

### 8. What a coverage measure can actually see

*Establish, for each coverage measure the repository produces, what it can actually see: which configuration it read, from which working directory, what it omitted, and
which process trees are absent from the report. Establish whether the threshold it is compared against is a per-language floor or a whole-project one, and whether that
threshold is bound to the value it is meant to hold or restated beside it as a literal. A measure whose effective source selection is narrower than the population it is
read over is a finding whatever the number says; record the population it cannot reach as a limit on the report rather than a defect in the product.*
Evidence: each coverage artefact with its effective source selection, its threshold, and one population it cannot reach.

### 9. Declared test-layer contracts, and whether anything holds them

*Establish whether each property the test layer asserts about itself — in a helper's own description, a settings comment, an entry-point comment, a marker description,
a test that asserts the text of a configuration file — is true of the code it describes, and whether anything holds it there. A comment describing the harness
differently from how the harness behaves is a finding in this layer, and a description of a limitation the layer never exercises is evidence about the system rather
than a defence of it. A test whose subject is the text of a configuration file passes when the text matches and fails when a line is reformatted: establish which
property of the running system a change to that text would have to break, and whether that is the property it is relied on for. A registered marker is not evidence of
use and a used marker is not evidence of justification; a helper nothing calls is a question of purpose, not of deletion. Where a declaration is made in production
source rather than in the test layer, whether it is executable and whether any path consults it is 08's.*
Evidence: the declared-property inventory with a holds or does-not-hold verdict; one comment the code contradicts; one assertion about configuration whose failure modes are not the ones it appears to guard.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed
list of mechanisms, so a defect whose mechanism is not named here still lands by the consequence it is producing.

- **CRITICAL** — the suite's green is affirmatively false today: a decision the system acts on whose effect no assertion anywhere can observe, where the unobserved
  effect reaches a user, or a shipped assertion the product cannot satisfy.
- **HIGH** — a gap that will be mistaken for coverage and is silent today: a decision exercised only through a stand-in for the thing it decides, a boundary asserted
  from one side only, a property the harness depends on that nothing holds it to, a check that can never stop a change, a measurement whose effective scope is narrower
  than the population it is read for.
- **MEDIUM** — bounded and real, with a specific audience: a check loaded and red over a known accepted-noise class, a resource left unbounded so that one test can
  take the run down, state carried forward between runs, a cost that makes a check get disabled.
- **LOW** — self-description and hygiene with no runtime consequence today: a test-layer comment that misdescribes the harness, a duplicated helper with no divergence
  yet, a marker registered and inert, a test whose subject is configuration text it cannot actually detect a change in.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/09-test-coverage/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `TST-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
