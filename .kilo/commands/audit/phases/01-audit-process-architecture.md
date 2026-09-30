---
name: 01-process-architecture
executor: auditor
problems-only: true
---

# Phase 01 — Process Topology & Lifecycle

## Purpose

Audits how the system comes up, serves, and goes down as a set of cooperating processes rather than one program: a request reaches a serving process that was assembled before the first byte was accepted, a periodic operation fires from inside that same process, submitted work is picked up by a mechanism that may or may not be the one intended, schema and reference data are meant to be ready before any of it, and every one of those components must stop without leaving behind state the system cannot explain. The angle throughout is the declared shape against the actual one — what the deployment says, what the process does, and what an observer would see.

This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — owned here: entry surfaces, process topology, startup and termination lifecycle across the request-serving, work-consuming, periodic and one-shot components, and the schema and reference-data bootstrap guarantee. Not owned here: the health, liveness and readiness endpoint and its probe contract (10); connection, unit-of-work, exclusion and pooler semantics (03); the settings that select a variant and the secret values behind it (02); the health endpoint's effect on the result the client sees (11); the ingestion and aggregation pipeline the submitted work enters (05); the temp-file area's admission, keying and lifetime (06); which surfaces a credential or a token must limit and how the request is authorised (04, 12); the deployed container posture, artifact provenance and backup contract (10); suite adequacy (09). Two processes of different roles are deliberately asymmetric; a difference between them is not a defect on its own — report it only where the code's own documentation or comments misstate it.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others.

Evidence is a class, not a check list: observed behaviour, a reproduced divergence, or a static proof that a stated property does not hold; the method is the auditor's. A passing check is methodology, never a finding, and nothing here gates a finding on this phase's own checks. Where a property cannot be settled in the environment at hand, establish it from what is observable and state plainly what could not be verified and why; that residual is a limit on the report recorded in the appendix, never a finding.

### 1. Component inventory, and the topology that differs between deployment tiers

*Enumerate every component that runs for the life of a deployment and every component that runs once and exits, separately per tier, and derive that
population from what each tier actually starts rather than from what its definition declares — a component can be declared and never launched, and one can
be launched by something other than its declared entry. Record per component whether it is unconditional, conditional on a setting, or present in one tier
only. Then trace the declared ordering and readiness edges between them: what each component states it requires before it can work, and what the tier
actually guarantees. A component that is enabled, monitored and reached by no request and no submitted work is a finding; so is a declared edge that does
not match a component's real boot requirement, and a dependency satisfied by exactly one tier. Record what an observer outside the process sees when a
dependency is unavailable at boot and again in steady state — a clean refusal, a restart loop, or silence. The health and readiness surfaces and what a
probe is contractually promised are 10's.*
Evidence: the per-tier component inventory with each component's lifetime and the condition that enables it; each declared ordering edge against the component's real boot requirement; one component observed enabled and never reached, or one unavailable dependency with what an outside observer saw.

### 2. Entry surfaces: what is constructed when a surface loads, and what is deferred

*Enumerate every surface the system can be started or entered through — the bootstrap for each long-lived component, any declared container entry, any
one-shot operational or maintenance invocation, and any registration made outside a request — and derive the population rather than accepting the declared
entry points as complete. For each, establish what work happens when the surface is loaded against what waits for first use, and whether loading it can
reach the database, the network, or the filesystem before anything has been asked of it. Establish whether the ordering of configuration loading, logging
setup, connection setup and first store use is deliberate on every surface or incidental on one, and whether a surface that pins its configuration at load
differs from one that re-resolves it per use. Then establish what the automated lint and static-typing gates actually include: an entry surface they never
analyse is invisible risk, and an aggregate gate that omits part of the surface is a finding in its own right.*
Evidence: the entry-surface inventory with load-time against deferred work per surface; the resource, if any, a load can reach; the surfaces the automated gates never analyse, or a gate that omits a part of the surface.

### 3. Startup order, and the interval in which the process answers before it can serve

*Establish the order in which boot preconditions are satisfied against the first moment the process is reachable by a caller, and separate work performed
while the application object is being built from work deferred to the startup lifecycle proper. A precondition that can fail after the process has begun
answering is a finding, and so is a version or state probe whose failure is logged rather than fatal. Then reproduce the interval: drive a request into the
process during the window between first acceptance and completion of the preconditions, and record what the caller observes — a refusal, an answer derived
from state that does not exist yet, or an answer that varies with where in the window it landed. A check documented as fail-fast that is in fact a warning
is a finding; so is a precondition whose completion nothing awaits anywhere, so that no observer can tell whether it has happened.*
Evidence: the ordered precondition list against the moment of first acceptance; one request driven into the startup window with what the caller observed; one precondition that nothing awaits, or one fail-fast check observed only warning.

### 4. Termination: what an in-flight operation leaves behind

*Establish, per long-lived component, what a stop signal interrupts, what is drained before exit, what is cancelled mid-operation, and what the component
itself documents as lost — then compare what each declares it loses against what it actually abandons, including the periodic loop and any work in flight.
Ask the question the declarations usually skip: which half-finished work does no component reconcile on the next start, and does any record of it survive
at all to permit reconciliation. A cancellation with neither a resumption path nor a compensating action is a finding; so is a component that exits before
the resources it opened are released, and state that leaks across a restart because a marker never left the process.*
Evidence: per component, the interrupt point, the drain, the cancellations and the declared losses; one stop signal observed mid-operation; one piece of half-finished work with no reconciliation path on the next start.

### 5. The periodic loop and the work-submission mechanisms inside the request-serving process

*Establish the periodic operation set: its cadence model, how many instances of it a deployment with several replicas runs, the per-operation bound, whether
one failing operation prevents or delays the others, and the liveness signal an operator outside the process can see. A loop whose only evidence of running
is its own output line is a finding, and so is an operation no replica is elected to run, where each runs it. Then enumerate every mechanism work can be
submitted to, derive that population rather than assuming the obvious mechanism is the one, and establish which one a given operation actually reaches —
including mechanisms that exist, are started, and never receive anything. For each, establish what state a repeat run or a restart finds: whether status
and outcome live in the process, whether a repeat is safe, and what a restart does to work already accepted. What the submitted work does once accepted,
and the pipeline it enters, are 05's.*
Evidence: the cadence, instance count, per-operation bound and failure isolation with the outside observer's liveness signal; the submission mechanisms with a reached/un-reached verdict per operation; one mechanism started and never receiving work; one repeat run or restart observed against the state it found.

### 6. The schema and reference-data bootstrap gate, and whether any of its steps can destroy a schema

*Enumerate every path that can mutate the schema or the reference data — the orchestrated one-shot, the in-process path behind a setting, an ad-hoc
invocation, automation, and the test harness — and derive the population rather than accepting the declared set. For each, record which guard it takes and
whether it takes one at all. Establish each guard's acquisition semantics: whether it waits or skips, whether the wait is bounded and can time out, and
whether the holder is the process that does the work or a coordinating process that dispatches it. Ask where the once-only guarantee actually comes from —
declared ordering, the guard, or neither — and whether the guard's documented semantics match what it does. Establish whether a path that drops and recreates
the whole store is among those paths, and if it is, where in the order it sits, what its acquisition semantics are, and what it does to connections other
components already hold and to work in flight on them. The change chain's linearity, reversibility and index inventory are 14's. The exclusion covering work
a coordinating process dispatches is 03's, and the once-only guarantee at the process level is this block's.*
Evidence: every schema- or reference-mutating path with the guard it takes or none; that guard's acquisition semantics against the holder and the worker; one path observed reaching the destructive branch; the actual source of the once-only guarantee.

### 7. Shared state across processes, and what is per-process by construction

*Establish everything the components coordinate through — the shared relational store, the working area on a volume more than one component writes, and the
shared transient store behind limiting counters, revocation markers and one-time material — and derive that population rather than assuming the relational
store is the only one. Separate what is genuinely shared from what is per-process or per-restart by construction, and treat any in-memory marker as a
finding candidate until its persistence across restart is demonstrated. What a revocation marker must be able to express is 04's; the composition of
every key in the store and each marker's lifetime is 10's; and every effect spanning more than one resource, together with the live instance where a
work record and the temporary file it names are written and deleted by different processes, is 05's. What remains this block's is the inventory and
the per-process classification.*
Evidence: the shared-surface inventory marked genuinely shared against per-process or per-restart; one in-memory marker whose persistence across restart could not be demonstrated; one surface two components write whose coordination is asserted nowhere.

### 8. Entry-layer discipline and dependency direction

*Establish the transport modules — the request-entry modules and any declared entry surface — and the layers each is meant to delegate to. Establish whether
the entry layer parses, delegates and responds and nothing more: no domain rule, no multi-step persistence work, no stateful normalisation of input that a
lower layer should own. Enumerate the domain and persistence operations found inside an entry module, every import that points back from a lower layer into
the entry layer, and every cycle in the graph. Then compare the transports against one another: where more than one implements the same contract, establish
whether the implementation is shared or duplicated, and treat duplication as the question — a deliberate difference between transports is not a defect on
its own, and is reportable only where the code's own description of it misstates the behaviour.*
Evidence: the transport-to-layer map; the domain or persistence operations found inside an entry module; every back-import and every import cycle; one contract implemented more than once.

### 9. Route surface assembly and reachability

*Establish the assembled route surface: every route, every surface registered outside the route set, and every periodic operation registered at startup,
with each one's downstream path. Derive the population rather than accepting the aggregation as complete, and record the namespacing and the collisions
across inclusions. Identify any mount that intercepts a path nothing else resolves, and any surface reachable only because it sits where the fallback does
— the fallback answering a path no route declares is a finding. Any registered entry no inbound trigger reaches is a finding; so is an alias retained
without a caller. Which guard a route carries, whether it runs on every request, and whether a route's own description matches what it installs are 12's
decision and are not filed here.*
Evidence: the assembled route and registration surface with each entry's downstream path; collisions and namespacing across inclusions; one mount observed answering a path no route declares; every registered entry with a reached/un-reached verdict.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — data loss or corruption; a once-only guarantee that is not actually guaranteed; a store whose contents are not protected against loss while more than one component can reach it; a process that accepts and answers work before a precondition it depends on has completed.
- **HIGH** — service unavailability, or an answer a caller acts on that is wrong because the process was not ready; work silently abandoned at termination with nothing reconciling it on the next start; a declared ordering, readiness or liveness contract that does not hold.
- **MEDIUM** — degraded operability: a component enabled and monitored that nothing reaches, or a defect an operator cannot distinguish from normal behaviour; a divergence between tiers that nothing documents as intentional.
- **LOW** — documentation-only drift about topology or lifecycle with no runtime consequence today.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/01-process-architecture/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `TOPO-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
