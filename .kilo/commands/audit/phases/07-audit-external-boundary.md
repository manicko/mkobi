---
name: 07-external-boundary
executor: auditor
problems-only: true
---

# Phase 07 — External Boundary

## Purpose

Audits the boundary with the outside: whether an outbound boundary exists at all and what would carry one; what the request path
cannot answer without, and what each dependency's failure takes down; what bounds arrival and on which identity a caller is
recognised; what the public surface accepts from anyone, refuses and reveals; and what an untrusted body is written to the log
as. This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — owned here: whether an outbound boundary exists at all; the derived runtime dependency set and
what each dependency's failure takes down; the mechanism by which an inbound bound is applied; the anonymous ingress
surface and what each refusal discloses; which boundaries validate and which defer validation past acceptance; what an
untrusted body is written to the log as. Not owned here: settings values, secrets, origins and cookie policy (02);
transaction, lock and pooler semantics (03); the mechanism that carries work out of the request path (01); identity,
credential issuance, claim guards, and what a marker must express to revoke (04); the identity an inbound bound is keyed
on, and whether the caller can choose it (04); the upload pipeline, the derived-artefact lifecycle, and the
record-and-file side effect written by different processes (05); artefact naming, residence, the one-time secret and the
served bundle (06); fixed-value discipline, boundary-model strictness and the declared-contract angle (08); test
adequacy (09); container, gate, edge, certificate, backup and observability posture (10); measured latency, cache cost
and throughput (11); the access decision, refusal-shape equivalence between two surfaces, and which surfaces a
request-forgery check reaches (12); the interface's own code and its type expectations (13); the schema chain (14);
header, origin and credential policy, and what value a bound takes (15). The composition of every key in the store and
each marker's lifetime is 10's, what a revocation marker must be able to express is 04's, and whether a surface is
rate-bounded at all, and what credential material the store holds, is 15's. Design deliberately asymmetric between
surfaces is not a defect on its own; report it only where the code's own documentation misstates it.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed
behaviour, a static proof that a stated property does not hold, or a reproduced divergence between two paths; the method is the
auditor's. A passing check is methodology, never a finding. Where a property cannot be settled in the environment at hand,
establish it from what is observable and state plainly what could not be verified and why — an unreachable surface is a limit on
the report, never a finding. Every block's evidence is an artefact that must exist in the report's appendix as a coverage record,
even where the block produced no finding.

### 1. Whether this boundary exists at all, and every mechanism that would carry one

*Establish whether any component initiates a connection to a host it does not control. If none does, establish that from both the call sites and the
shipped configuration and record it as a result rather than a skip: an absence established is evidence, an absence assumed is not. Then establish, per
mechanism that would carry one — a declared client library, a retry helper, a circuit-breaker wrapper, a self-check that requires such a library to be
importable — whether anything reaches it, and whether its presence is a decision or residue. A library the deployment refuses to start without, and
nothing uses, is a finding: the blast radius is the whole process and the capability is absent.*
Evidence: the outbound-call inventory, empty or not, with the search that produced it; per candidate mechanism a reached or un-reached verdict; one declared mechanism nothing reaches together with the reason it is still load-bearing.

### 2. The derived dependency set: what the request path cannot answer without, and what each one's failure takes down

*Derive the set yourself rather than inheriting it from documentation, including shared state — a cache, a store, a queue, a filesystem the request path
reads — not only named third parties, and derive the site count rather than assuming it. Per dependency establish what its unavailability takes down,
whether the blast radius is one feature or every page, and whether the dependencies are genuinely independent or merely look so. Ask whether one outage
reaches the same outcome through more than one layer with the same root cause each time. Where a dependency's failure cannot be induced, establish it
from the code path that would run and record what that evidence does not cover.*
Evidence: the derived dependency list with a per-dependency blast radius and an independence verdict; one outage probe and what survived it.

### 3. A guard built to bound abuse: what it does when its own store is unavailable, and whether the choice is recorded

*Establish which counter the guard keeps, where that counter lives, and which of three failure modes it takes when the counter cannot be
read — permits, refuses, or raises. A guard that raises where it was meant to bound turns a dependency outage into a total one. Establish whether that
direction is a declared value or a hard-coded branch, whether it is recorded where an operator would look, and whether every surface reaching the same
guard reaches it with the same setting. What identity a bound is keyed on and whether the caller can choose it are 04's; the composition of every key in
the store and each marker's lifetime is 10's; whether a surface is rate-bounded at all, and what credential material the store holds, is 15's.*
Evidence: the per-guard failure-direction verdict — permits, refuses or raises — with a declared-value or hard-coded-branch verdict each; one direction chosen by a branch rather than by a declared value.

### 4. The aggregate ingress budget: what bounds arrival, how its scope is shared, and whether one caller is recognised the same way on every surface

*Establish every bound on inbound volume that exists — per principal, per network address, per surface, per window — deriving the set rather than
assuming one per surface, and per bound establish whether the counter is shared across processes or held per process. Derive the process and replica
counts from the shipped configuration rather than assuming them: a limit correct inside one process is an unbounded budget in the deployed system. What
identity a bound is keyed on and whether the caller can choose it are 04's. Establish whether one caller is recognised identically on every surface,
and whether an intermediary in front makes an address-keyed budget one the caller does not control. What value each bound should take is 15's; the way
the budget aggregates across the deployed topology is this block's.*
Evidence: the bound inventory with the scope of each and whether the counter is shared or held per process; the process and replica counts derived from the shipped configuration; one arithmetic path from a per-process limit to the budget the deployed topology permits.

### 5. A degraded result the consumer cannot tell from a real one

*Establish, for every fallback and every default, whether what it returns can be told apart from a real result by whatever stores or consumes it — the
row written, the component a probe reports, the status a caller polls — deriving the fallback set rather than assuming one per dependency. Include the
case where a guard, a limiter or a circuit is open and nothing counts or logs it, and the case where a probe reports the same words for more than one
underlying state. A fallback that returns a value where the caller needed a status writes a plausible answer into a field thereafter read as
authoritative, permanently, and nothing alerts because the operation succeeded.*
Evidence: per fallback — the substituted value, its consumer, and one stored state a reader cannot distinguish from success; one probe answer that covers more than one underlying state.

### 6. Isolation of failure inside a batch, and the order of a durable record against the effect it describes

*Establish what happens when one member of a batched write fails — abort, continue, or complete — and whether any reader can tell how far the batch got.
Establish the order of a durable record against the effect it describes, what a repeat of the batch re-does, and what a partially applied batch leaves
behind for a later run to meet. The interleaving of a stored file, a status row and queued work is 05's; what one member of a batch does to its siblings
is this block's.*
Evidence: one failed batch member and the fate of its siblings; the record-and-effect ordering on the same path; the residue a re-run meets.

### 7. The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them

*Derive the surface — machine-readable reads, state-changing writes, anonymous sinks, monitoring endpoints, schema documents, the catch-all serving path
— and per endpoint establish whether a credential is required, what it discloses on refusal, and whether the disclosure level differs between the
machine-readable and the human-facing surface for the same underlying decision. Establish whether a machine-readable description is produced from the running code
or maintained beside it, what it omits, and what a consumer built against the previous shape meets when a field changes without a version. Which refusal
class an endpoint should return is 12's, what the edge does with a bound is 10's, and where a contract is declared, whether the declaration is executable
and whether any path consults it is 08's.*
Evidence: the derived endpoint list with a credential requirement and a disclosure verdict each; a refusal-class-by-surface matrix; one endpoint class reached anonymously where the classes beside it in the same group require a credential; the consumer list and the change each would break.

### 8. Which inbound boundaries validate, which defer validation past acceptance, and which documented exceptions are load-bearing

*Establish the validation convention at the request boundary — the strict-by-default base every client-input model should inherit, and how many
boundaries inherit it — and for each that does not, establish whether the exception is documented, load-bearing or accidental, and whether the boundary
rejects, ignores or coerces what it does not recognise. Include a boundary whose input is a free-form document only a later, different process can
reject, and a query parameter carrying a hand-parsed document outside the model layer. Then derive the boundaries whose validation happens after the
request supplying the input was already accepted and recorded, and the point at which each is first rejected. 08 owns the production-code boundary
surface; this block owns the inbound integration boundary.*
Evidence: the boundary-by-model inventory with an inherits or does-not-inherit verdict and, per boundary, the point at which its input is first rejected.

### 9. The untrusted body as it is logged

*Establish what the anonymous ingress path writes about a body it accepted from anyone — which fields, verbatim or transformed, at what severity, through
which sanitiser and whether it masks — and the volume bound on that path and whether that bound is keyed on an identity the caller controls. Then
establish whether a dependency's failure state is measurable at all, or whether it exists only as an unlogged exception. Where no counter exists, a
quiet dependency is indistinguishable from a working one.*
Evidence: per direction, the fields logged and the sanitiser's masking verdict; the failure states with a counter, with a log, or with neither.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — a live capability reachable with no gate at all, or credential material exposed irreversibly, where the exposure cannot be withdrawn without rotating it.
- **HIGH** — a silent correctness failure with no self-healing path: a guard that permits where it was meant to bound, with the direction a hard-coded branch rather than a decision; a bound correct per process and unbounded once the deployed topology multiplies it; one dependency's failure taking down a surface rather than a feature; a refusal disclosing more on one surface than the other discloses for the same decision; a body written to the log verbatim from anyone, with no bound on the volume.
- **MEDIUM** — a bounded resource or operability gap: a fallback that returns a value where the caller needed a status; a batch failure that stops or skips the remainder without recording how far it got; a probe reporting the same words for different underlying states; a failure state with a log but no counter; a document accepted at a boundary only a later process can reject.
- **LOW** — documentation and observability drift with no runtime consequence today: a published description omitting a surface the running code serves; one caller recognised differently on two surfaces with no record of the choice; a declared dependency or capability the code does not implement.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/07-external-boundary/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `EXT-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
