---
name: 10-production-ops
executor: auditor
problems-only: true
---
# Phase 10 — Production Operations

## Purpose

Audits the deployed system as a thing that must run and must be recovered: what each long-lived service actually carries once every layer of the deployment is merged,
what decides the content of the artifact it runs, which controls decide what may land, what the topology defines against what the deployment path enables, what a
restart and a partial restart must re-establish, what an observer is told when something is wrong, what the shared transient store holds and what its loss stops, what
the fronting tier exposes, what a backup protects and whether anything proves it restores, which signals reach an operator, and whether the procedures a responder
follows would run as written. This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — taken in: the health, liveness and readiness endpoint and probe contract (from 01), and the fronting tier, transport security and certificate
lifecycle (from 07, 02). This phase owns the deployed composition: effective container posture, artifact provenance, the controls that decide what lands, service
coverage, restart, the health contract, the shared transient store, the edge tier, backup and restore, the operator's signal stream, and the operational corpus.
Deferred: which origins and which cookie attributes are honoured, per environment → 02; which surfaces a per-request gate reaches and what it returns, and whether the
server re-checks what the browser already enforced → 12; the schema chain, index inventory and drift → 14, this phase owning only the one-shot step's completion
condition; secret values and settings provenance → 02; pooler configuration semantics → 03, owning only whether the production path enables the pooler at all; measured
latency, per-request cost and the ceiling each tier implies → 11; how a component the deployed topology runs is configured and sized → 11; production-code convention and
dead code → 08; suite adequacy and a gate's scope-as-test-coverage → 09, this phase owning only whether a control exists and runs in the deployed path; client bundle
composition and client-side security posture → 13; outbound and inbound integration contracts → 07; namespace rulings and cross-phase conflict resolution → 99. Neither
this phase nor 09 files the other's verdict on a gate.

With 04 and 15: this phase owns the composition of every key in the store and each marker's lifetime, and the store as a load-bearing operational dependency; 04
owns what a revocation marker must be able to express; 15 owns whether a surface is rate-bounded at all, and the credential material the store holds.

A service enabled by one topology and not another, a probe present in one configuration and disabled in another, and a restriction tightened only in the deployed
definition are deliberate asymmetries, not defects on their own. Report each only where the code's own description of the arrangement in force is contradicted by the
arrangement actually deployed.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed behaviour, a static proof that a stated
property does not hold, or a reproduced divergence between the resolved configuration and the layered one; the method is the auditor's. A passing check is methodology,
never a finding, and nothing here conditions a finding on this phase's own list. Where a property cannot be settled in the environment at hand — standing up a separate
stack to restore into end to end, inducing a dependency outage to probe a signal, recreating a component behind a fronting tier — establish it from what is observable
and state plainly what could not be verified and why; an environment that cannot be induced is a limit on the report, never a finding.

### 1. Effective runtime posture per service, after every layer is merged

*Establish, per long-lived service, the identity it runs as and the capability, filesystem, privilege and resource restrictions it actually carries in the merged
production definition rather than in one layer alone — an inherited directive and a restated one are not the same evidence, and a restriction absent from a later layer
may still be present in an earlier one. Establish what the runtime boundary publishes, and which image-level defaults every service silently inherits, including
one-shot containers that never open a port a default probe polls. Establish whether the deployment engine in use applies the resource declarations the topology makes,
and establish which service receives the broadest credential set, since a one-shot step that runs before the gates holds the largest privilege in the topology. A
restriction that survives only in the development overlay is a finding however deliberate the development arrangement is.*
Evidence: per service — effective identity and restrictions after merge, published ports, inherited defaults; one restriction present in only one of the layered definitions; one declared resource limit the deployment engine does not apply.

### 2. What decides the artifact's content, per input class

*Enumerate every input that can change the built artifact without a source change — base images and their versions, tools fetched during the build, and components
pulled at automation time — and for each establish whether it is pinned, whether its integrity is verified before use, and whether an automated updater covers that
class of input at all. Establish whether one build target is built more than once with different inputs, whether the coordinates used to publish, to deploy and to pull
name the same object, and whether any artifact that a revert could select exists at all. An artifact nothing versions is a choice to record, not a defect; a floating
input with no integrity check and no updater covering its class is a finding.*
Evidence: the external-input inventory with a pin verdict and an integrity verdict each; the build invocations that disagree on an input for one target; the mutability of the revert target.

### 3. Controls in the deployed surface: existence, declared scope, and what they examined

*Take every control in the deployed system that produces a pass/fail signal on the running deployment — a per-service probe, a rehearsal job, a scanner, a one-shot
schema step acting as a start-order gate, and a setting that decides whether a dependency outage denies or admits — and bind the shared vacuous-control angle here in
its deployed-surface form: for each, establish what it is configured to examine and what it actually examined. Establish what is configured to be enforced and which
suppressions are sanctioned before judging any result; never infer a missing tool, and never treat a non-zero issue count as a defect by itself. A control whose
declared and actual scope differ is a finding however green it is, and one that gates the boot order by success rather than by completion is a different control from
one that verifies a property.*
Evidence: per control — whether it is present, the scope it declares, the item count it actually examined, and whether any shipped guard would notice a change in that scope.

### 4. What can prevent a change from landing, and what the aggregate entry point omits

*Establish which checks can prevent something from happening, as distinct from which report. What triggers the automation, what ordering or dependency makes a verdict
reach the artifact, whether the artifact can be published or deployed regardless of a verdict, whether credentials reach components that run before the gates, and what
overlapping or re-entrant runs do to shared state. Where several checks are chained behind one entry point, establish which of them it omits; a target that chains
several checks while leaving a whole process tree outside every one of them is the case to find, and the absence of any automation that triggers on a change is a
separate finding from an entry point a person must choose to run. A shipped test asserting the behaviour a gate reports is 09's question about the suite, not this
one's.*
Evidence: per check — trigger, the dependency that would make it blocking, and the path by which a change proceeds with the check failing or never having run; the chained entry point with the check it omits.

### 5. Service coverage and provenance: what the deployment defines, starts, and actually runs

*Establish which artifact a deployment actually runs and whether that derivation is a verified one or a mutable reference. Then compare the service set the topology
defines against the set the deployment path enables: a component defined and health-checked but never started, a component gated behind a profile the canonical path
never turns on, and a component the forward path updates but the revert path does not. Establish whether a single built output has two sources of truth, one of them
outside version control, and what a second copy means for a change made in one of them. Whether a component is gated by design is a decision to read, not a defect; the
question is whether the production path enables it at all. How such a component is configured and sized is 11's.*
Evidence: the resolved production service list against the list the deployment path enables, with each profile-gated component; the artifact identity per path; one component defined and started by neither path; one output with two sources of truth.

### 6. Restart and partial restart: ordering, address resolution, and one-shot steps

*Establish what a full restart of the stack requires to be re-established, in what order, and what an external observer experiences while it happens; then establish
what a partial restart re-establishes and what it silently leaves. Establish whether a fronting tier re-resolves the address it forwards to, or keeps the one it
resolved when the component behind it was recreated. Establish what a success gate actually exercises relative to the path a client takes: a gate run from inside the
component being verified cannot observe the tiers in front of it. Establish what a completion-gated one-shot step does when only part of the stack is recreated —
whether the stack can report itself healthy while the step never completed, and whether a step that fails leaves the components behind it running anyway. What any of
this costs in latency and memory is 11's.*
Evidence: the boot-order and address-resolution dependency chain after a full and a partial restart; the components outside the success gate; the partial restart with what each leaves unre-established.

### 7. The health contract an observer can act on

*Establish the endpoints and probes an observer acts on: which signals exist, which gate, which merely inform, and whether each is enabled in the deployed configuration
rather than merely available. Where a dependency's liveness is staged into readiness before the hard one, establish its default and freshness rule against the shipped
configuration: does the default hide a real failure, and does the staging have a defined end state? Establish whether a wedged process is distinguishable from a healthy
idle one, whether a restart threshold can flap the boot chain, what an unauthenticated caller learns from each signal, and what a default probe reports for a container
that never serves the probed port. A probe that tests its dependency's reachability rather than its own liveness answers healthy for a process that is not doing any
work.*
Evidence: per signal — endpoint, gating or informational, enabled state in the deployed configuration, the disclosure a caller receives; one condition that answers healthy for a broken process.

### 8. The shared transient store: every key it holds, every marker's lifetime, and what its loss stops

*Establish what every key the shared transient store holds encodes and omits, which job owns each key, and each marker's lifetime against the lifetime of the thing it
retires: a marker expiring while the credential it retired is still live restores a state already left behind, and a marker whose lifetime is the longer of two
configured lifetimes is a choice rather than a property of what it retires. Establish whether a key carrying caller-supplied segments varies wherever a caller can vary
it, and establish the single failure domain: which of the store's distinct jobs stop working together when it is unreachable, and what each one's failure mode is, so
that one outage either denies a request or admits it per job. Claims that a marker makes a retired entry unreachable rather than globally withdrawn are claims to
confirm or refute, not the design to assume. What a revocation marker must be able to express is 04's; whether a surface is rate-bounded at all, and what credential
material the store holds, are 15's; the composition of every key in the store and each marker's lifetime, and the store's standing as a load-bearing operational
dependency, are this phase's.*
Evidence: the key inventory with the encoded and omitted components and the owning job; each marker's lifetime against the lifetime of what it retires; one outage that stops two jobs whose failure modes differ.

### 9. The fronting tier: transport security, certificate lifecycle, and what is exposed

*Establish how the fronting tier resolves the address it forwards to and whether that resolution survives the address changing. Establish which requests reach a control
and which bypass it, including a limit declared in one tier and coupled to a setting in the other by nothing stronger than a comment, and whether any monitoring path is
restricted in a way the documented consumption model cannot reach. Establish how transport is negotiated, and the certificate lifecycle end to end: where material comes
from, how long it lives, what happens on expiry, whether expiry is observable before it happens, and what the tier does when the material is absent. Establish where the
configuration declares a transport requirement stricter than the only transport the deployed topology offers, and what a credential requiring that transport then
experiences.*
Evidence: the resolution model and its behaviour when the address behind it changes; the request-path-by-control matrix; the cross-tier limits with what couples them; the certificate's origin, lifetime, renewal path, and behaviour when missing or never provisioned.

### 10. Backup: consistency, durability, and what each option changes

*Establish whether each artifact the backup produces is internally consistent at the moment it was taken, and separately whether it survives the loss of what it
protects: where it physically lives, on which device, and whether the loss event it exists for also destroys it. Establish what each option passed to the backup tool
actually does, judged by what it changes rather than by what its name suggests, and establish whether the copy-out's result is examined at all. Establish whether the
effective interval matches the nominal one, whether old artifacts are removed, whether a job that stops is noticed, and which durable state has no backup at all —
including a directory that is itself inside the working tree the loss would take.*
Evidence: per artifact — what it is taken from, what it is written to, the location relative to the thing it protects; each backup option with the behaviour it changes; the effective interval and the retention mechanism; the durable state with no backup.

### 11. Evidence that a restore works

*Establish whether any path exercises a backup artifact that was actually taken, rather than one generated moments earlier from a database it also just created. A
rehearsal that restores its own input proves nothing about recovering from a real one, and an artifact that survives the loss of what it protects is not by itself
evidence that it restores. Establish whether the restore path examines its own result, what options it passes to the underlying tool judged by what they change against
the live database, and what would have to be true for the stated recovery objectives to hold — and whether those objectives are stated anywhere at all. The absence of a
rehearsal path is the finding; an entry point that reports success without reading what it restored is a different one, and the sharper.*
Evidence: for the rehearsal path — the origin of the artifact and the origin of the data inside it; whether the restore's outcome is examined; the recovery objectives with the state of each precondition.

### 12. Signals produced, signals consumed, and the log paths that bypass the structured output

*Establish which signals the deployed system produces, which are consumed, and whether anything in it consumes them: an alert expression over a series no component
emits is not an alert, and where the system exposes no metrics surface at all, the absence of one is itself the finding rather than an omission from the inventory.
Establish whether the documented collection path is reachable from where a collector would actually sit, whether a condition that matters has any signal, and whether an
operator has a channel that would tell them. Establish whether every log path reaches the same structured output, including an unauthenticated intake surface that
accepts caller-supplied text and caller-supplied structured fields, the fronting tier's own access and error streams, and whether the formatter performs any redaction;
and establish the log file's lifecycle inside a container that is restarted rather than drained. Measuring latency is 11's.*
Evidence: the signal inventory with produced and consumed verdicts; one alert expression against a series the system does not emit; the paths by which a log line can bypass the structured output or inject into it.

### 13. Operational claims as testable artefacts

*Establish whether the procedures a responder is told to follow would run as written on the host they would run on: required state, required credentials, required
files, assumed tool versions, and whether any step's own output is examined before the next step trusts it. Then establish whether each operational claim in the
deployment, rollback, restore and incident corpus — a control that is live, a cadence, a value, a path, a mechanism documented as being migrated away from — is still
true of the system as deployed. Treat a comment, a description and a runbook line as claims to be tested against the executing path, and record a document describing a
different system as a finding in its own right. Where the claim is a declaration made in production source, whether it is executable and whether any path consults it is
08's; the external integration surface is 07's.*
Evidence: the operational-claim inventory with a true or false verdict each; one procedure with the step that fails on the deployed host and why.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed
list of mechanisms, so a defect whose mechanism is not named here still lands by the consequence it is producing.

- **CRITICAL** — a control believed to be active that is not, on the path that decides what may reach a running system, so that nothing distinguishes a vetted subject
  from an unvetted or unexamined one for a reviewer or for the system's own records.
- **HIGH** — a state the system is in now where the failure is neither survivable nor observable: a recovery path that does not restore a whole-stack known-good state, a
  protection that does not survive the operation it exists for, a signal produced and never consumed so that nothing distinguishes a quiet system from a broken one, a
  store whose loss silently stops decisions the system believes it is making.
- **MEDIUM** — degraded operability with a workaround: a control present and effective in part; a documented procedure or claim that is inaccurate, but whose
  consequence an operator can work around; a gap visible only on a path the operator would have to know to look for.
- **LOW** — documentation and hygiene drift with no runtime consequence today.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/10-production-ops/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `OPS-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
