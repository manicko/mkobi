---
name: 02-configuration-secrets
executor: auditor
problems-only: true
---

# Phase 02 — Configuration & Secret Material

## Purpose

Audits how configuration is declared, resolved, guarded and kept separate from the material that must never be read back: the sources and their precedence, the variant each running process resolves, the names the code reads against the names the deployment supplies, the guards that refuse an unusable value, where secret material comes from and every surface it can reach, what must not cross between variants or between co-resident processes, and the defaults a deployment silently inherits. The angle throughout is the resolved value rather than the declaration — two source files can differ and resolve alike, and one can differ and resolve alike in the wrong direction.

This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — owned here: the settings object and its source precedence, the name contract between code, the shipped examples and the deployment definition, guarded preconditions and their refusals, secret provenance and exposure, variant-to-variant and process-to-process parity, posture switches, and defaults whose correctness depends on the environment the process runs in. Not owned here: entry surfaces, process topology and boot ordering (01); the connection, unit-of-work, exclusion and pooler semantics that settings select (03); pipeline admission limits and the shapes they accept (05); the temp-file area's keying and lifetime (06); which surfaces a credential limits and what makes an identity acceptable (04); convention and dead-code discipline in source (08); the container posture, artifact provenance, transport security, probes and backup that consume these values (10); measurable latency (11); which surfaces a request-forgery check reaches and whether it runs on each (12); suite adequacy (09); namespace rulings (99). Deliberate asymmetry between tiers, environments or components is not a defect on its own; report it only where the code's own documentation misstates it.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others.

Evidence is a class, not a check list: observed behaviour, a reproduced divergence, or a static proof that a stated property does not hold; the method is the auditor's. A passing check is methodology, never a finding, and nothing here gates a finding on this phase's own checks. Where a property cannot be settled in the environment at hand, establish it from what is observable and state plainly what could not be verified and why; that residual is a limit on the report recorded in the appendix, never a finding.

### 1. Settings source precedence, and the variant each running process resolves

*Establish the precedence order in which the configuration sources are consulted and the value each running process actually resolves from them, then
establish whether variant selection is a property of the process or of the environment label it is deployed under — a selection made per process and a
selection made once per tier are different things, and the difference is what this block is about. Include any variant that exists only as a convenience
for an automated run, and record the mechanism that selects it. Then establish where the resolved object is obtained: a value re-resolved per request and a
value pinned once when a module is first loaded are two behaviours from one declaration, and a component that changes a setting expecting the next
operation to see it is a finding. Derive the source population from what is consulted rather than from what a list of classes suggests.*
Evidence: the precedence order of the sources; the variant and the resolved values each process sees, with the mechanism that selects it; one setting whose re-resolution differs between its load-time path and its per-use path.

### 2. Name universes: what code reads, what the shipped examples declare, and what the deployment supplies

*Compare every name universe the configuration surface spans, in both directions: names the running code reads, names the shipped example configurations
declare, names the deployment definition supplies, and names any automation or command surface reads. Derive the symmetric difference rather than sampling
for drift, and judge two directions separately — a name supplied that nothing reads, and a name read that nothing supplies — because they have different
owners and different remedies. Then judge whether the drift signal is distinguishable from a legitimately new name. A name declared only in the deployment
definition and never read is a different defect from an example name written in a flattened form the loader ignores, and an alias that resolves only under
a delimiter form the examples never use is a third. Where a nesting delimiter has single-underscore aliases, establish which form each side uses.*
Evidence: the name sets with their symmetric difference in both directions; one name supplied and never read; one name read and never supplied; a verdict on whether the drift signal is actionable.

### 3. Guarded preconditions: presence, strength, and whether the refusal is actionable and secret-free

*Enumerate every guarded value, then for each ask four separate questions: is a guard present at all, is it unconditional or conditional on the environment
label, can any value a hardened variant could legitimately carry disable it, and is the failure actionable for an operator while disclosing nothing of the
value it refused. Treat absent, present-but-empty and malformed as three states, because a guard that accepts an empty value and a guard that accepts
nothing are not the same control, and where one boot precondition is enforced in several places, establish whether the copies agree on the condition, the
skip rules and the source they expect to read — divergent copies of one guard are a finding. A warning emitted where a refusal was documented is a finding.
A bound, a threshold, a limit or a lifetime is a guarded value like any other: establish whether one is declared, whether the value it declares is the one in force,
whether more than one place declares it, and whether what is enforced at runtime is the same bound the configuration states.
The connection and unit-of-work behaviour these values select is 03's.*
Evidence: the guard inventory with, per guard, a verdict on presence, unconditionality, disablement and what the failure message discloses; the three states distinguished for one guarded value; one duplicated guard whose copies disagree; one declared bound against the bound in force; the failure text itself.

### 4. Secret provenance, and every surface the material can reach

*Trace where secret material can enter and leave: files under version control, the context an image is assembled from and the build steps that consume it,
process command lines and standard output, error and traceback paths, and credentials handed to automation. Classify every credential-shaped literal as
real, placeholder or fixture, and confirm the ignore rules cover the build context and not only version control — a file exempted from tracking can still
sit inside the context a build is assembled from. Establish whether constructing the configuration object has side effects beyond reading it: creating a
directory, writing a file, contacting a service. Establish whether any value is written to the log as it is loaded, and whether a loaded value appears in
an exception message. The deployed posture that consumes these values and the transport security in front of them are 10's.*
Evidence: the classified literal inventory with the classification rule applied; the ignore-coverage verdict for the build context as well as version control; one secret-bearing output path, one loaded value observed in output, or one construction side effect observed.

### 5. Tier divergence: which differences are deliberate, and which are unintended

*Establish what must not cross between variants and between co-resident processes, then judge each difference intentional-and-complete rather than merely
different. Take the population from the resolved values per variant per process rather than from the source files, and cover the debug and
exception-exposure switches, the transport-security posture, the migration role, the read-only filesystem, and the cookie attributes and accepted origins
each variant honours. Which origins and cookie attributes are honoured per variant is the policy half and belongs here; which surfaces a request-forgery
check reaches, and whether it runs on each, is 12's. Include whether the co-resident processes see the same required configuration, and whether a value
written into one variant's secret source can reach a process belonging to another. A difference a variant's own comment declares intentional, and which the
code honours, is not a finding; the same comment with different behaviour is.*
Evidence: the effective-configuration diff per variant and per process in resolved values; per variant, the accepted origins and the cookie attributes honoured; one difference declared intentional and not honoured; one value present in one variant's source and absent from another's.

### 6. Automated environments, and the configuration path each can actually exercise

*Establish, for every automated environment, how values reach the process there, which of the guards established earlier it can therefore exercise, and
which required values it supplies none of. Treat the difference in how values arrive — a file read by the process, literals written into a definition,
values inherited from a shell — as a first-class object of analysis, because an environment that cannot exercise the file-based secret path cannot exercise
the guards that depend on it. An automated environment with no configuration source at all cannot fail a guard, which is not the same as passing it, and an
environment whose values are hard-coded literals exercises the interpolation guards only when it in fact interpolates anything. Whether such an environment
can stand in for a deployment is a finding of its own.*
Evidence: per automated environment, how values arrive, the guards exercised and the required values absent; one guard no automated environment can reach; the verdict on whether each can stand in for a deployment.

### 7. Posture switches that can change a running process

*Enumerate the settings whose value alters the security or delivery posture of a process that is already running, and for each establish whether the
substitution is intended, constrained to the cases where it belongs, and re-pinned where a hardened variant is supposed to freeze it. Separate the
documented operator control from configuration that looks like drift, and separate a value honoured at construction from one honoured at every use — a
switch that changes behaviour only for what is built after it is read is not the same control as one read at every use, and one intended for a development
tier that a hardened variant never re-pins is a finding. Whether an aggregate task that is supposed to run the gates actually runs each of them is 08's.*
Evidence: the posture-affecting settings with, per setting, whether the substitution is constrained and when it is re-pinned; one switch whose effect reaches only components built after it is read; one hardened variant where the switch was never re-pinned.

### 8. Assigned, derived and branched configuration that nothing reads

*Derive, per assigned name, a liveness verdict: is it still read by anything reachable, does the value reach a consumer, and is every environment branch
reachable under some selection a real deployment can produce. Where a value is derived rather than read directly, establish whether the derived result
satisfies its consumer's contract and not merely that the derivation exists — including a derivation that recomputes what the object already holds, and a
path that resolves relative to the process working directory while every deployment supplies an absolute one. Establish which role names are configuration
at all and which are fixed by the data layer, since a name a component reads but cannot supply is the same failure from the other side. Whether a
declaration is executable and whether any path consults it is 08's; this block is whether this configuration is read.*
Evidence: per-name liveness verdicts; the unread-name list; derived values checked against the contract of their consumer; one branch no real selection reaches.

### 9. A guard that runs, reports clean, and examines nothing

*The vacuous-control angle is 99's; what a configuration gate examines is this block's. For every validation and gate over configuration, establish what
values it reads, what predicate it applies to them, and whether that predicate can match the form the value takes — a strength rule compared
case-sensitively against values whose producer guarantees a shape, a prohibited-value list holding an entry the form can never produce, a body that
returns its input unchanged. Record separately where each gate is invoked from, since a gate that examines nothing and a gate never invoked are
different defects with different owners of the fix. The connection and unit-of-work behaviour the values behind a guard select is 03's.*
Evidence: the configuration-gate inventory with, per gate, the values it reads, the predicate it applies and the path it is invoked from; one gate whose defining rule is stated in a source no deployment selects; one predicate that cannot match the form its own input takes.

### 10. Defaults that are wrong for the environment the process is deployed into

*Establish, for each value whose default is shaped for a convenient host rather than for a deployment, whether the mismatch is documented where a reader
would find it and whether anything fails when the default survives into a deployed environment. Derive the population from the defaults themselves rather
than from a list someone believes they wrote, and include the case where the deployment definition asserts in a comment that a default is wrong while
nothing checks whether the assertion still holds. A default that is wrong for the environment and documented as such is not a finding; one that is wrong,
undocumented and load-bearing is, and so is a comment whose assertion about a default no longer matches the default's value.*
Evidence: the defaults inventory with, per default, whether it is host-shaped and where any assertion about it lives; one default observed surviving into a deployed environment; one comment whose assertion about a default no longer matches that default.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — secret material obtainable by anyone who can read the artefact carrying it or the history preserving it; a signing or credential value that is empty, malformed, or shared with another variant or process; a guard a deployed configuration can switch off.
- **HIGH** — a production control silently disabled or bypassable, including a validation gate whose body cannot fail; secret values reaching standard output, logs, error paths or command lines; an automated environment that no longer exercises the configuration it stands in for.
- **MEDIUM** — material or policy crossing a variant or process boundary; ineffective cookie, origin or exception-exposure policy in one variant; configuration-name drift, unread configuration, and a value resolving against a different root than every deployment supplies.
- **LOW** — placeholder and example gaps, undocumented switches, and explanatory comments that no longer match the value they describe.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/02-configuration-secrets/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `CFG-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
