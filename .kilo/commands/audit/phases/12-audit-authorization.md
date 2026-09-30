---
name: 12-authorization
executor: auditor
problems-only: true
---
# Phase 12 — Authorization

## Purpose

Audits what an access decision returns: where the level an identity holds is decided and which source of it wins, what the vocabulary can and cannot distinguish, which
surfaces are reachable only by an elevated identity, whether a caller is consulted on every path that reads or mutates something they could own, which account states
are enforced by the server and which are merely returned to it, whether two resolutions of one identity agree, what one aggregate's identifier can reach through
another's, what each refusal discloses, and what a browser attaches to a request without a script presenting it. This file names what to examine and under which angle;
the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — this phase owns what an access decision returns, on which surface, and the disclosure a refusal carries. Other phases own: identity resolution and
binding, token issuance and expiry, and password and one-time-credential handling (04), this phase owning the per-request gate and neither phase filing the same
decision; which origins and which cookie attributes are honoured, per environment, and the transport-security policy (02), this phase owning only whether the server
re-checks what the browser already enforced; the client-side route guard and role-conditional rendering, and whether the client treats a refusal as authoritative (13);
the correctness and the resource cost of the data an access decision protects (05, 11); the deployed posture of the elevated surface and the secret material it may
read (10); the transaction boundary around a decision and its write (03);
the constraints and indices backing a grant (14); the inbound request form and the external integration contracts (07); production-code convention and dead code (08);
namespace rulings and cross-phase conflict resolution (99). A mechanism another phase owns is recorded as a deferral with its owner named, and this block still covers
the decision this phase makes. The deferrals this file previously carried — to a content-lifecycle phase, a consent phase, a media phase and an external-boundary phase
for media ownership — are withdrawn: none of those subsystems exists in this system.

A surface that admits every identity and a surface that admits only an elevated one are deliberate differences between endpoints, not defects on their own. Report one
only where the code's own description of the arrangement in force is contradicted by what the executing path admits.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: a matrix of surfaces against predicates, a
reproduced divergence between two paths reached with one credential, or an observed refusal whose disclosure differs from its sibling's; the method is the auditor's. A
passing check is methodology, never a finding, and nothing here conditions a finding on this phase's own list. Enumerate the surfaces, then ask whether each is gated.
Where a property cannot be settled in the environment at hand — a decision reachable only behind a fronting tier, a state that can only be produced by a path not
exercised — establish it from what is observable and state plainly what could not be verified and why; an unreachable surface is a limit on the report, never a finding.
A proposed change that would make two decisions agree is judged against whatever one of them deliberately refuses.

### 1. The two sources of authority, and which one decides

*Establish whether an access level is stored, granted or derived: which attributes decide it, which surfaces consult the representation, and which read those attributes
directly instead. Where more than one independent source of the same level coexists, establish which wins, at what point in the request, and whether that precedence is
written down anywhere. Where two surfaces reach the same verdict, establish whether a construction forces the agreement or it only follows from the same attributes
being read twice — both are questions and they have different answers. Derive, do not assume, the implementations of the level ordering that exist and establish whether
they agree; an implementation nothing consults is not a disagreement but is part of the answer.*
Evidence: the site the level is decided at, with the precedence rule and whether it is recorded; the attribute set each elevated surface reads, compared; the ordering implementations and any disagreement.

### 2. What the vocabulary can and cannot express, and which gates are declared but never installed

*Establish the granularity actually available: whether anything finer than the declared levels can be expressed, whether an assignment layer exists that the
representation ignores, and how many guards are declared for the same decision against how many sites install one. Derive both counts rather than assuming them: a read
gate, a write gate and an administrative gate can be written for the same aggregate while only one is installed, and every write surface then re-implements the decision
inline. A control returning a constant where a decision is expected is a finding; a gate correct at the granularity it has is not, and neither is one whose whole body
is a pass-through. Establish each inline re-implementation's agreement with the shared one rather than assuming it, and record a gate that is correct for the decision
it makes and wrong for a decision it is relied on to make.*
Evidence: the distinctions the vocabulary can express; guards declared per decision against those installed; the gates whose body returns its input; the inline re-implementations and their divergence from the shared one.

### 3. Elevated-privilege surfaces, and the predicate each one actually evaluates

*Enumerate every surface reachable only by an elevated identity: the administrative request surface, a privileged path that hands off to a second gate, a one-shot
maintenance invocation, and any surface described as privileged only in its own documentation. Establish which of them are reachable over a request at all — a one-shot
task has no caller to authorise, and a surface every identity may reach is not privileged merely by being listed — and record where each decision sits, and where no
decision sits at all. Establish a decision reached after the first irreversible step it was supposed to precede, and the service methods such a surface calls that
perform no caller check of their own. Where the privilege is declared rather than enforced, whether the declaration is executable and whether any path consults it is
08's; whether the privilege is enforced is this block's.*
Evidence: the surface inventory with the predicate each evaluates against what admits a caller; a decision reached after the first irreversible step it guards; two gates on one request path; one surface whose documented privilege no executing path enforces.

### 4. Single-object paths: is the caller consulted, and what the response discloses first

*Enumerate the object types an identity owns — including the collections, derived rows and history rows a user accrues without ever being told it owns them — then every
path that reads or mutates one of them by identifier, and judge each for an owner or grant comparison. Record what the response discloses before the decision is made.
Do not presuppose the enumeration is complete: a path that resolves an object without consulting its caller is a path, not an exception to the rule; a path that
resolves a child by its own identifier without constraining it to the parent named in the request is one; an ownership column written at creation and read by no
decision anywhere is one.*
Evidence: the owned-type inventory; the path-by-owner-comparison matrix; the paths carrying no owner comparison; the child-resolved paths whose parent constraint is absent, with what each still returns.

### 5. List paths: the restriction in the query, and one identity receiving two answers

*Establish the surfaces where one call names many objects, and establish whether a multi-object mutation surface exists at all — where none does, say so rather than
enumerating an empty set. For each list surface, establish whether the restriction is part of the query or applied row by row, whether each named item is re-resolved
under it, and whether a bound on the number of rows exists. Then, for one identity and one object, compare what the list surface and the single-object surface return,
and where a list deliberately takes a different branch for an elevated level, whether the single-object path takes the same branch. A per-object judgement cannot
express any of these.*
Evidence: the multi-object surfaces with a per-object or per-call verdict and a row bound or its absence; the scoping of each list query; one identity whose list answer and its single-object answer disagree.

### 6. Mutation entry points that receive no acting identity

*For every service, helper or job that creates, updates or deletes a row, establish whether the caller supplies an acting identity alongside the target identifier and
whether the callee consults it: a creation path handed an owner value it never reads, a deletion path resolving its target by a bare identifier with no owner
constraint, a privilege-management path whose only inputs are the target and the level to apply. The inventory of such callees is the finding — a callee that trusts its
caller by construction is only as safe as every caller, and a small caller set today is not a guarantee for tomorrow. Establish each such entry point's callers rather
than assuming the surface above it is the only one. Where a decision precedes a write, whether both are evaluated in the same indivisible operation is 03's; the
in-module precedent for carrying an identity is this block's.*
Evidence: the mutation entry points with the identity parameter each accepts and whether it is read; the entry points carrying none; a privilege-management path with no caller check at any layer; a decision separated from its write.

### 7. Account state: which states are consulted, on which surface, and by which resolution

*Establish which account states exist, which are consulted, on which surfaces, and whether a read surface consults the states a mutating one does. For each state,
establish whether it is enforced by the server or merely returned to the caller — a flag whose enforcement is delegated to the client is enforced only as far as the
client cooperates — and whether a state set by one path is cleared by the reverse path. Establish what an unauthenticated caller reaches and what a caller can influence
there. A credential's own issuance, binding and expiry is 04's, as is the limit's keying and the identity it derives from; where an account state is consulted, and by
whom, is this block's.*
Evidence: the state-by-surface coverage matrix, with server-enforced against caller-delegated each; the states set by one path and never cleared; the unauthenticated surface inventory with what each lets a caller influence.

### 8. The two resolutions of one identity, and whether they agree

*Compare by decision and not by name: for one presented credential and one account, what each resolution refuses, which states each consults, and whether any state one
refuses is admitted by the other. Establish whether they are independent implementations or one delegating to the other, and which surfaces call which. A predicate
specified or exported but that no live path calls is part of the answer, as is one re-derived inline where a shared one exists. Where a surface exists in one resolution
and has no counterpart, say so rather than inferring symmetry. Issuance, binding and expiry are 04's; the per-request gate and every ownership and account-state surface
are this phase's.*
Evidence: the state-by-resolution refusal table; the states one consults and the other ignores; the surfaces calling each; exported predicates with no live caller; one state admitted by one resolution and refused by the other.

### 9. The cross-aggregate boundary: what one aggregate's identifier can reach through another's

*For every path taking both a parent and a child identifier, establish whether the child is constrained to the parent and what is returned when the child's own lookup
succeeds while the constrained lookup returns nothing: its name, its type, its configuration, its derived fields, its private annotations. Establish the unit a stored
data row is authorised against, and whether a stored document carries fields belonging to the aggregate rather than to the row it describes — a document that crosses
the boundary carries its owner's fields with it. Storage-artifact ownership is 06's; only reach across aggregates is this block's.*
Evidence: the parent-by-child path matrix with a constrained or unconstrained verdict; the fields each unconstrained path returns; the authorisation unit per data row; one document carrying another aggregate's field.

### 10. What each refusal discloses, and where the shapes disagree

*For each refusal class, establish what the response discloses on each surface, whether one underlying decision is answered at a different disclosure level on a
machine-readable surface than on a human-facing one, and whether the identifier being refused is echoed back. A deliberately reduced disclosure is a decision to read,
not a defect. The finding is one decision answered inconsistently across two surfaces with no stated reason, a refusal describing a scheme the system does not
implement, or a signal answering healthy or unreachable to an unauthenticated caller while disclosing a filesystem path or a raw dependency failure.*
Evidence: the refusal-class-by-surface matrix; the pairs where the same decision is disclosed differently; the stated reason for each divergence or its absence; the unauthenticated signals with what each discloses.

### 11. Ambient credentials: what the browser attaches, what decides it, and what the server re-checks

*Establish every credential the browser attaches automatically, without a script presenting it, and which decision attaches it: an attribute on the credential, a
transport requirement, or a server-side check on the request's declared origin. For each surface reachable with an ambient credential, establish what another origin's
page can cause a signed-in browser to do there and whether any server-side re-check backs the browser-side decision. Whether the deployed transport can carry a
credential whose declared transport requirement is stricter than what the deployment offers is 10's. Include no ambient credential on a surface as a positive result
rather than a skipped question. Which origins and which credential attributes are honoured, per
environment, is 02's; which surfaces carry an ambient credential and whether anything re-checks it is this phase's.*
Evidence: the ambient-credential inventory with the decision that attaches each; the surfaces reachable with one and the server-side re-check each has or lacks; the surfaces carrying no ambient credential.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed
list of mechanisms, so a defect whose mechanism is not named here still lands by the consequence it is producing.

- **CRITICAL** — an identity reaches an object or a surface that is not its own, in the state the system is in now: through an indirect reference, through a path that
  resolves a child without constraining it to its parent, or through a path that resolves an object without consulting its caller.
- **HIGH** — a decision reached after the first irreversible step it should have preceded; an access level resolved differently by two surfaces with no construction
  forcing the agreement; a state one resolution refuses and the other admits; a control that decides nothing where a decision is required.
- **MEDIUM** — one underlying refusal answered at different disclosure levels on two surfaces with no stated reason; a correctly granular gate that reads the wrong
  attribute, refusing a legitimate subject while admitting a stronger one; a real defect whose only entry point is not currently reachable; a description of a decision
  the code does not make.
- **LOW** — refusals that leave no operator-visible trace, or a trace carrying no stable reason code; refusals recorded under a different convention on each surface
  that produces them; documentation drift on a gate.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/12-authorization/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `AUTZ-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
