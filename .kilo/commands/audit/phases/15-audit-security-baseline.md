---
name: 15-security-baseline
executor: auditor
problems-only: true
---

# Phase 15 — Security Baseline

## Purpose

Audits the cross-cutting baseline no other phase answers: what each persisted credential is at rest and under what policy, what credential
material reaches any other sink, which inbound surfaces carry an attempt bound at all, what an unauthenticated write accepts, what
untrusted structure is allowed to select, what an undecided failure discloses, and which response headers the application itself emits.

This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — this phase owns the cross-cutting security baseline no other phase answers: what
each persisted credential is at rest and under what policy, what credential material reaches any other sink,
which inbound surfaces carry an attempt bound at all, what an unauthenticated write path accepts, what
untrusted structure is allowed to select, what an undecided failure discloses, and which response headers
the application actually emits. Other phases own: process topology, entry surfaces and the start-up schema
gate (01); settings values, secret provenance, environment parity, origin and cookie policy, and the production
fail-fast validators (02); transaction boundaries and the cross-process serialisation registry (03);
credential issuance, delivery, claim guards, lifetime and account resolution, and limiting on the login
surfaces (04); upload admission, temporary-file lifetime and file serving (06); inbound surface form, body
bounds, retry contracts and what integration telemetry carries (07); boundary-validation coverage,
fixed-value homes and the type gate (08); the test harness and the suite's own isolation (09); container
posture, the edge tier, transport security, certificates, probes and operational observability (10); the
measurable cost of a bound (11); the access decision itself, object-level ownership, the privileged-surface
inventory and request-forgery enforcement (12); the client-visible consequence of a policy decided here
(13); schema evolution, referential actions and the index inventory (14); namespace rulings and cross-phase
conflict resolution (99). On the shared transient store the seam is split three ways and each half is asked once: the composition of every key in
the store and each marker's lifetime is 10's; what a revocation marker must be able to express is 04's; whether a surface is rate-bounded at all,
and what credential material the store holds, is 15's. A mechanism another phase owns is recorded as a deferral with its owner named,
and this phase still records the security consequence of it.

The response headers the application emits and the framing controls its own documentation assigns to another component are
deliberately not the same set, and a deployment that runs no delegating component is a supported deployment rather than a defect.
Report the resulting gap only where a deployment the project offers is actually running with the header still absent.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed
behaviour, a static proof that a stated property does not hold, or a reproduced divergence; the method is the auditor's. A
passing check is methodology, never a finding. Where a property cannot be settled in the environment at hand, establish it from
what is observable and record it in the report's residual footer as a limit on this report, never as a finding.

### 1. The Stored Password: Encoding, Parameters, and the Policy Around It

*Establish what the password record is at rest, with what work factor and what maximum accepted input length, how verification compares, what minimum
the policy enforces, and whether changing a credential requires the current one. Then establish where the caller's own credential rests in the
browser-resident tier: whether a store reachable by script running in the page holds it, what that store is bound to, and whether it outlives the
session that created it. A record whose encoding reveals the input, a comparison whose work
depends on how much of it matches, a change that needs no current value, and a client-side store any script in the page can read, are findings.
Issuance, delivery and lifetime of the session credential
are 04's; the record that outlives them, in the server's store and in the browser-resident tier, is this block's.*
Evidence: the stored-credential inventory with encoding, work factor and comparison path; the client-side store inventory with, per entry, what the
page's own scripts can read from it; one password record created through the real issuance path
and read back at rest; one credential change attempted without the current value, and the outcome; one credential held where script running in the
page can read it.

### 2. Short-Lived Credentials Handed to Another Person: the Store, the Lifetime, the Retrieval

*Establish every place a credential is issued to someone who is not the account holder and is then persisted elsewhere: what it is stored as, for how
long, what a read does to it, what a failure of the backing store does to the write, and whether the stored form can be recovered from the store that
holds it — read back in the clear, derived from what
the store also holds, or decrypted by anything already in the store's operators' reach. A stored credential readable more than once by design, or
readable indefinitely, is a finding, as is a store that fails open on the write side and reports success, and as is a stored form that comes back out
of the store it rests in. The composition of every key in the shared
transient store and each marker's lifetime is 10's, and what a revocation marker must be able to express is 04's; the
credential material that store holds is this block's.*
Evidence: the delegated-credential inventory with encoding, lifetime, read semantics and a recoverable or not verdict; one stored value read twice and
the outcome; one stored value recovered in the clear from the store that holds it.

### 3. Credential Material in Everything Else That Persists

*Trace every credential-bearing value into the log sink, into any structure returned to a caller, and into the outbound telemetry path. A credential,
a hash, or an unbounded caller-supplied string able to carry credential material into a log is a finding. What an outbound integration writes to its
own logs is 07's, operational observability is 10's, and the browser-side sink is 13's; what reaches any
server-side sink is this block's.*
Evidence: the value-to-sink trace; one credential-bearing value reaching a sink; one sink receiving an unbounded caller-supplied string.

### 4. Attempt-Rate Bounding: Which Surfaces Carry One at All

*Derive, do not assume, the inventory of surfaces that admit a caller, and for each one whether any bound is applied to it at all. Record the
surfaces that reach the request path with no bound on them, and the ones whose bound is reached only by a layer the surface does not actually cross.
A surface drivable without limit, and a bound applied to some surfaces in this zone and silently absent from others in it, are findings. What
identity a bound is keyed on, and whether the caller can choose it, is 04's; what the counter's own store being unavailable does to it, and what a
request body may contain, is 07's; and the composition of every key in the shared transient store is 10's. Whether a surface is rate-bounded at all is
this block's.*
Evidence: the surface × bound matrix with a bound or no bound verdict per surface; one surface admitting repeated attempts with no refusal; one
bound shared across unrelated surfaces so the first to reach it exhausts it for the rest.

### 5. Unauthenticated Inbound Writes: the Surfaces That Accept a Caller's Structure with No Session

*Enumerate every surface reachable with no authenticated identity, and for each one what it accepts, what it writes, what bounds it, and what
acceptance and refusal each say. A write of caller-supplied content into a durable log with no session and no content validation is a finding. The
health surface's own contract — whether the process is ready and what it depends on — is 10's; what it discloses is this block's. Do not
presuppose the enumeration is complete: a surface exempted from the gate by its method or its path shape is still reachable without a session.*
Evidence: the unauthenticated-surface inventory with bound, written shape and disclosure; one surface writing caller content with no session; one
unauthenticated read returning internal component state.

### 6. Untrusted Structure That Selects What Is Read

*Establish every payload whose content, not whose presence, chooses a stored expression, a column, a key or a handler, and for each one whether the
key set is constrained to a declared set before use. A payload whose content selects an unconstrained key set is the shape to establish; an
unconstrained key reaching storage is a finding. Whether the boundary validates at all is 08's; what the
caller is permitted to select is this block's.*
Evidence: the selection-payload inventory with the declared key set each is checked against, or its absence; one key reaching storage unconstrained;
one rejected key set reproduced with the refusal it produced.

### 7. Failure Responses: What an Undecided Failure Puts in the Response

*Establish every path that returns no access decision — an unhandled exception, a rejected dependency, a validation fault — and for each one what the
caller learns: internal text, a trace, a query shape, a filesystem path — and whether the same value reaches the log. A path returning internal
detail, and a response whose shape differs between environments, are findings. What a refusal discloses is 07's; what a failure discloses
is this block's.*
Evidence: the failure-path inventory with the response shape each returns; one path returning internal detail to the caller; one failure response
whose content differs between environments.

### 8. Response Headers at the Application, and What a Deployment without the Delegating Tier Emits

*Inventory the headers the application sets, the ones its own documentation assigns to another component, and the response classes — including error
responses and asset responses — carrying none of them. A header asserted only in a comment is a finding, as is a response class leaving the
application with no header the application claims to set. Origin and cookie policy is 02's, and the delegating tier, transport and
certificates are 10's; which headers this process emits is this block's.*
Evidence: the header matrix per response class; one class carrying none; one header asserted only in documentation.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — a caller reaches an effect the system never decided to allow: an authentication surface drivable without limit, a
  stored credential another identity can read more than once, or unauthenticated caller-supplied content written into durable state.
- **HIGH** — a real secret reaches a sink that persists it or hands it to something outside the request; an undecided failure returns
  internal detail to the caller; or a control that is present, configured and deciding nothing stands exactly where a decision was
  required, so the property it names is unprotected.
- **MEDIUM** — a bound exists but one counter is shared across unrelated surfaces, a counter admits silently when its store is
  unavailable, a delegated credential is readable within its stated lifetime but its retrieval path is wider than the issuance that
  created it, or a response class leaves the process with no header it claims to set.
- **LOW** — refusals that leave no operator-visible trace or carry no stable reason code, a header asserted only in documentation,
  and control metadata that does not resolve against the phase or environment it names.

A finding another phase establishes against a zone this phase owns is still graded here by its effect on this baseline; the grading is this phase's
even where the establishing is not.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/15-security-baseline/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `SEC-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate
