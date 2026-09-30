---
name: 13-client-tier
executor: auditor
problems-only: true
---

# Phase 13 — Client Tier

## Purpose

Audits the browser-resident application tier end to end: how its modules are layered, which server-owned value it holds and what
retires that value, the path a request leaves by, the caller's session as the client itself understands it, the contract the client
declares at build time, what the user is shown for each class of failure, how absent or malformed server data renders, the input
rules the client enforces against the server's, what an assistive technology is told by the surfaces this code adds, what crosses
the network boundary unverified, and whether the client's own declared surfaces can be reached at all.

This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — this phase owns the browser-resident application tier: its module layering, the
values it holds and who retires them, the path a request leaves by, the caller's session as the client
understands it, the build-time contract the client declares, what the user is shown for each failure class and the user-facing
text behind it, how absent server data renders, the client's own input rules against the server's, the semantics of
the interactive surfaces the code adds, type width at the network boundary, and the reachability of
client's declared surfaces. Other phases own: process topology, entry surfaces and the start-up schema
gate (01); settings values, secrets and environment policy, including any artefact's build-time
configuration contract (02); transactions and constraint recovery (03); credential issuance, delivery,
claim guards and account resolution (04); ingestion and aggregation (05); upload admission, temporary-file
lifetime and file serving (06); inbound surface form, body bounds, refusal disclosure and retry contracts
(07); fixed-value homes, one-rule-one-home, boundary-validation coverage, the type gate and dead
definitions in both tiers (08); test-suite adequacy on this side of the boundary (09); deployment
provenance, container posture and the edge tier (10); cache-key composition, hit cost and measurable
latency (11); the access decision a privileged client surface reflects, object-level ownership and
request-forgery enforcement (12); schema evolution and the index inventory (14); credential storage
policy, request-rate bounding coverage and failure-response disclosure (15); namespace rulings and
cross-phase conflict resolution (99). A mechanism another phase owns is recorded as a deferral with its
owner named, and this phase still covers the client-visible consequence of it.

Where the client stores the caller's credential differently in a development build than in a production build, and where its
presentation is richer than the response it renders, the difference is intentional and is not a defect on its own. Report
either only where the code's own documentation misstates which of the two applies.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed
behaviour, a static proof that a stated property does not hold, or a reproduced divergence; the method is the auditor's. A
passing check is methodology, never a finding. Where a property cannot be settled in the environment at hand, establish it from
what is observable and record it in the report's residual footer as a limit on this report, never as a finding.

### 1. Slice Boundaries: What Crosses from Shared Code into a Feature, and Back

*Enumerate the client's import edges by kind — request plumbing, credential state, feature internals, presentation — and for each one, which direction
the declared layering permits. Shared plumbing reaching into a feature's credential state is a finding, and so is a feature reaching another's
internals instead of the surface that feature publishes. Do not presuppose the enumeration is complete: an edge created only inside a lazily loaded
segment, or one created for a build variant the other variant never loads, is still an edge. The rule that each fixed value has exactly one home, and
the reachability of a definition nothing calls, are 08's; this block records the layering violation and what it lets one slice do to
another.*
Evidence: the edge inventory with an in-permitted or out-of-permitted verdict per edge; one shared module reaching feature internals; one feature
reaching another's internals in place of its published surface.

### 2. Server-Derived Values: Which Component Owns Each One, and What Retires It

*Derive, do not assume, the inventory of values the server owns: for each one, the cache holding it, the identity of its key, and the mutation that
must invalidate it. A mutation leaving a value the user still sees is a finding, as is a value held both in a cache and in component state, and as is
a value the client treats as authoritative on a refetch it never issues. Key composition, hit cost and measurable latency are 11's; what
the user is left looking at after a write is this block's.*
Evidence: the value inventory with owner, key shape and invalidating mutation; one mutation with no invalidation; one value held by two owners; one
value still on screen after the mutation that changed it.

### 3. The Request Path: One Path or Several, and What Each Refusal Leaves Behind

*Establish every place a call leaves the client and what it carries: the shared client, a direct transport call, a side channel that reports on
failures. Record where the target location, the credential attachment and the failure handling are decided once versus restated. A path bypassing
shared failure handling, and a base location declared in more than one place, are findings. Whether a declaration is consulted by any path is 08's;
this block records the duplication and the divergence it produces.*
Evidence: the request-path inventory with, per path, where the target and the credential are set; one path bypassing shared failure handling; one base
location declared in more than one place, and the request it changes.

### 4. Session Continuity: What the Client Believes after a Full Page Load

*Establish where the caller's credential lives in a shipped build, what survives a hard reload, and what the client decides when the in-page
credential is absent but the server session is not. Then ask the reverse: what a claim the client itself parses decides — expiry, privilege — and
what an absent or skew-affected claim causes. A boot that discards a valid session is a finding. Deployed-build provenance is 10's, and
whether a store reachable by script running in the page is acceptable for this credential is 15's.*
Evidence: the credential-state inventory with what each event leaves behind; one full reload reproduced with its outcome; one claim the client acts on
that the server never confirms.

### 5. The Client's Declared Build-Time Contract against What the Shipped Bundle Resolves

*Inventory every value the client declares it requires at build time and, for each one, the consumers found. A declared requirement with no consumer
is a finding, and so is a value the request path resolves that no declaration names. A value resolved from the ambient environment with no
declaration at all is the third shape to look for, and a declaration enforced in one build variant and skipped in another is the fourth. Whether the
declaration is executable at all is 08's.*
Evidence: the declared list with, per entry, the consumers found or none; one entry with no consumer; one resolved value no declaration names; one
build variant produced where the declaration would have refused the other.

### 6. Failure Surfacing: What the User Is Shown, per Class, and Where One Class Is Shown Twice

*Derive the classes of failure the client can receive; for each one, the message path, the surface it reaches, and whether it is reported inline, as a
transient notice, or both. A class with no message branch is a finding, as is a failure that both renders an error and leaves a previous result on
screen, or that fires two notifications for one occurrence. A class whose user-facing text is defined in more than one place is 08's
fixed-value question; the outcome the user reaches is this block's.*
Evidence: the failure-class inventory with the surface each reaches; one class with no message branch; one occurrence reproduced producing two
notifications, or an error rendered beside a result the server has already replaced.

### 7. Absent, Partial and Malformed Server Data

*Establish, per surface rendering server data, what it renders for an empty result, an absent optional field, an out-of-type value, and a failed fetch
following a successful one. An empty frame indistinguishable from a populated one, a thrown render, and a stale frame left beside a fresh error are
findings. Do not presuppose the surface enumeration is complete: a surface composed by a shared widget inherits the state handling of the widget, not
of the page that places it.*
Evidence: the surface × state matrix with the rendered outcome per cell; one cell that throws; one empty state indistinguishable from a populated one;
one failed fetch reproduced after a successful one on the same surface.

### 8. Form Rules: What the Client Enforces against What the Server Enforces

*Compare the client's declared input rules with the server's, field by field and in both directions. A field the client accepts and the server
refuses, or the reverse, is a finding, as is a client rule that exists only to shape the message. Whether the boundary validates at all, and whether
its declared contract is executable, are 08's; the client's own rule set and where the two rule sets diverge is this block's.*
Evidence: the field × rule comparison with a matches or diverges verdict; one field accepted in the client and refused by the server; one field
refused in the client and accepted by the server.

### 9. Interactive Surface Semantics: What an Assistive Technology Is Told

*Enumerate the interactive surfaces the code composes rather than inherits, and for each one its accessible name, its label association, its focus
behaviour across a route change, and how a dynamic error is announced. A pointer-only surface, an unannounced input error, and a dialog that does not
restore focus are findings. A surface the platform already supplies named is not this block's concern; what the code adds to it, and what it
overrides on top of it, is.*
Evidence: the interactive-surface inventory with the name, role and focus path each exposes or lacks; one surface with no accessible name; one focus
path followed through a route change and where it ended.

### 10. Type Width at the Client Boundary: What Crosses as Unverified

*Establish how each response shape reaches the client — declared by hand, derived, or asserted at the call site — and record the suppression and cast
sites at that boundary. A boundary where the declared shape and the served shape can differ with nothing that would notice is a finding. The general
type gate across both tiers is 08's; what crosses the network boundary unverified is this block's.*
Evidence: the boundary inventory with, per boundary, how the shape is declared and what a mismatch would cost; one boundary with no declared shape;
one served response differing from the shape the client declared for it.

### 11. Reachability of the Client's Own Declared Surfaces

*Enumerate every route, every lazily loaded segment and every feature module the client declares, and for each one the path that reaches it. Do not
presuppose the enumeration is complete. A surface with no reaching path, or reachable only by typing a location, is a finding — and where the
specification corpus names that surface, a missing integration rather than dead code. The reachability of an individual definition nothing calls is
08's; a whole declared surface nothing reaches is this block's.*
Evidence: the surface inventory with a reached or unreached verdict per entry; one unreached surface the specification expects; one route reachable
only by a typed location.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — the client acts on, or withholds, something the server never decided: a privilege claim the client trusts without
  the server confirming it, or a protected surface whose only gate is in the client, so that nothing server-side stands between a
  caller and the effect.
- **HIGH** — the user is shown something the system has already decided against: a value the server replaced still on screen after
  the mutation that changed it, an error rendered beside a result the server has withdrawn, or a whole class of failure with no
  branch at all, so every occurrence of it is silent.
- **MEDIUM** — the client's declared contract and its behaviour diverge without immediate user effect: a declared requirement no
  consumer reads, a base location declared in more than one place, a response shape declared by hand that the server may not
  serve, or an input rule the two sides do not share.
- **LOW** — a surface that composes or overrides semantics more weakly than the platform beneath it, an interactive element with
  no accessible name where nothing depends on the pointer path, and a message whose owning home cannot be identified from the
  shipped code.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/13-client-tier/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `FE-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate
