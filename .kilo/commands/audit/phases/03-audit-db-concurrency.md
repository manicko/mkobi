---
name: 03-db-concurrency
executor: auditor
problems-only: true
---

# Phase 03 — Transaction & Concurrency Semantics

## Purpose

Audits the store as a shared, concurrent resource: every path that reaches it and what a connection there costs, who opens a unit of work and who decides it ends, where a transaction boundary sits relative to the invariant it is supposed to hold, what a tolerated database error does to the work around it, which invariants are carried by constraints rather than by code, which destructive operations destroy another writer's work, what mutual exclusion exists and what it does not cover, what an interrupted background or one-shot run leaves behind, which windows ordered schema steps open for concurrent writers, and what an effect that spans more than one resource leaves in between. The angle throughout is the boundary as a property rather than as a wrapper: who can end it, when, and what survives if they do not.

This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — owned here: how the store is reached from every process and path, unit-of-work boundaries, tolerated-error handling inside them, constraint-enforced invariants and their recovery, read-modify-write and derived-value recomputation, exclusion mechanisms and their lifetimes, background and one-shot operation safety, and schema-mutation windows. Not owned here: entry surfaces, topology, boot ordering and the schema bootstrap gate at the process level, and the component that runs a destructive database path (01); the mechanism that defers work out of the request path (01); the settings and secrets that select a connection (02); the ingestion and aggregation pipeline this phase's transaction boundary protects (05); the record-and-file effect written by different processes (05); the temp-file area whose lifetime that effect depends on (06); outbound transport, retry and failure isolation (07); pool sizing as a measured cost and the tier's ceiling (11); the connection pooler's place in the topology and whether the deployed path enables it (10); the migration chain's linearity, reversibility and index inventory (14); suite adequacy (09). Three separable claims are one rule here: any concurrency guard is judged by whether it would fail if the protection it names were removed. Deliberate asymmetry between tiers, environments or components is not a defect on its own; report it only where the code's own documentation misstates it.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others.

Evidence is a class, not a check list: observed behaviour, a reproduced divergence, or a static proof that a stated property does not hold; the method is the auditor's. A passing check is methodology, never a finding, and nothing here gates a finding on this phase's own checks. Where a property cannot be settled in the environment at hand, establish it from what is observable and state plainly what could not be verified and why; that residual is a limit on the report recorded in the appendix, never a finding.

### 1. How the store is reached, by which process, and what each connection costs

*Enumerate every path the store is reached from, including the maintenance invocations that run outside any request, and every place a unit of work's client
is constructed per operation where another path constructs it once per process. Establish which connection parameters are literals in the construction and
therefore no setting can change, and treat the difference between a pool parameter that is configurable and one that is not as a finding in its own right
rather than as an omission. Record every write that bypasses the persistence layer in hand-written statements — including the ones that run at startup, the
ones that create the schema, and the ones that delete on a timer — and compare what each does about transaction scope and error reporting against what the
layered paths do. Then reproduce what a connection lost mid-operation leaves behind: the unit of work's state, the rows written before the loss, and
whether the next operation reuses anything. Whether the pooler sits in the deployed path and what the pool costs as a measurement are 10's and 11's.*
Evidence: the access-path inventory with the client lifetime each path yields; the connection parameters that are literals against the ones a setting can change; the hand-written statement paths with their transaction scope; one connection lost mid-operation with the state it left.

### 2. Who opens the unit of work, and who decides it ends

*Establish whether the request-scoped unit of work commits, rolls back, or does neither on its own, and therefore which layer owns the decision that a piece
of work ends. Then enumerate every helper that accepts a caller's unit of work and deliberately declines to end it, and every caller of such a helper that
also declines to end it — the pattern is correct in isolation and its failure mode is a caller that forgets, so derive the caller population rather than
assuming the helper's own callers honour the contract. A path that opens a second unit of work inside a request that already has one is a finding; so is a
path whose ending is decided by a caller that nothing reaches. What a domain write does inside this boundary, and the pipeline whose boundary it protects,
are 05's.*
Evidence: the unit-of-work lifecycle per path with the layer that decides its end; the helpers that decline to end a caller's unit of work with, per helper, whether every reachable caller ends it; one reachable path opening a second unit of work inside a request.

### 3. Multi-row and multi-resource domain writes: does the boundary sit where the invariant is

*Establish which domain operations change more than one row, or a row and something that only means anything beside it, and whether the boundary sits where
the invariant does. Derive the population from the write sites rather than from the operations' names, since an operation described as a single write can
fan out. A partial commit is reachable when writes straddle boundaries, when the boundary is narrower than the invariant it protects, and when the failure
the boundary exists for is one the surrounding code converts into a success — that third case is the one usually missed. Include a write that removes what
an earlier write created, and a write that updates a row to a value computed from the row being updated. The record-and-file effect written by different
processes is 05's; what this block holds is the writes that reach one store.*
Evidence: the boundary map per multi-row operation; one induced mid-write failure, all-or-nothing or not; one operation whose failure path converts the error into a success.

### 4. Tolerated database errors: what happens to the enclosing unit of work

*Establish, for every database error the code intends to tolerate, what happens to the unit of work around it. Establish whether the failing statement is
isolated in a nested unit so the enclosing work stays usable, or whether absorbing the error leaves that work unusable for every subsequent statement — a
difference an operator experiences as an unrelated failure further down the same request. Then establish whether a helper that promises never to affect its
caller is ever invoked from inside another operation's work, and whether an error swallowed at one layer is observable at any other. An error path that
cannot fire, because the condition it guards is already impossible, is a finding; so is a swallowed error that leaves the caller's work aborted with
nothing said.*
Evidence: one induced failure per tolerated path with the enclosing unit of work's state afterwards; the helpers promising isolation with every reachable caller; one helper invoked inside another unit of work.

### 5. Constraint-enforced invariants and their recovery paths

*Establish, for every constraint that carries a business invariant, its callers rather than treating it as a declaration. For every writer that can reach
it, establish what the outcome is: a correct recovery, a defined no-op, or an error that reaches the user. A constraint that is both the last line of
defence and the user-visible outcome is a finding; so is one whose documented recovery the code cannot reach, and one enforced on one write path and not on
another — including the same logical insert expressed once as a conflict-tolerant write and once as a plain insert. Establish whether a delete leaves child
rows in a state the readers do not expect, and whether the cascade behaviour is written down anywhere the writer would look.*
Evidence: the constraint inventory mapped to the invariant each enforces; per writer, the observed outcome for one conflicting write; one constraint enforced on some paths and bypassed on others.

### 6. Read-modify-write, destructive operations, and derived values

*Establish every operation that reads state, decides, and then writes or deletes, and every row value maintained away from the write that changes its input.
For each destructive operation, compare the predicate the selection used against the condition the mutation applies — a mutation acting by identifier and
ignoring the condition that justified those rows is a finding. Establish which paths take a row-level lock, and treat the empty answer as the finding
rather than as an omission, since a correctly serialised operation can still destroy another writer's work when the serialisation does not cover the read.
Then examine derived values: establish whether a value cleared and rebuilt on every submission reads its own inputs back from what it is rebuilding, and
whether a rebuild that fails part-way leaves the derived value absent rather than partial. What the pipeline then computes from the result is 05's.*
Evidence: the selection predicate against the mutation condition per destructive path; a two-writer case per path without a lock; one derived value cleared and rebuilt, with what the rebuild read.

### 7. Exclusion mechanisms as one system: lifetime, holder, and what is not covered

*Enumerate every mutual-exclusion mechanism in the system as one inventory and derive it rather than accepting the mechanisms a caller already knows about.
For each, record its lifetime, its holder, its acquisition point and its release path, and what it does not cover: work dispatched to another process, a
second identifier standing for one resource, a nested acquisition of the same key. Establish whether each lifetime matches the path the operation actually
runs on, and whether the stated motivation for a split is enforced anywhere. Then enumerate the operations that must be exclusive and hold no mechanism at
all, and treat a single process-local consumer as an exclusive right nobody declares — including the case where two processes each believe they hold it.
Where a wait is unbounded, treat the absent bound as the finding; a mechanism that works and can be held indefinitely is not a clean mechanism.*
Evidence: the exclusion inventory with lifetime, holder, acquisition point and release path per mechanism; the operations that must be exclusive and hold none; one operation observed waiting without a bound.

### 8. Background and one-shot operation safety

*Establish how each background and one-shot operation is invoked, bounded and interrupted, and what an interrupted run leaves: an open unit of work, a held
row, a held long-lived exclusion, or an already-committed batch. Then ask the repeat question in both directions — is an operation that is not atomic by
design safe to run twice, and does a half-applied run resume, restart, or double-apply. Establish what actually performs de-duplication for each operation
and whether that is a stored status value, an in-memory marker, or nothing at all. Include the operation a periodic schedule can run on more than one
replica, and record whether any mechanism decides which replica runs it. A hold duration is measurable: a mechanism that works and is held too long is a
finding.*
Evidence: per operation, the bound, the state a mid-run interruption leaves, the repeat-run outcome and the measured hold duration; one operation with no de-duplication beyond a stored status value; one operation several replicas can run.

### 9. Schema and reference-data mutation, and the window each step opens

*Establish the ordered steps by which the schema and the reference data are mutated, and the window each step opens for concurrent writers: a replacement
applied before the constraint that would enforce it exists, a drop before the create, a backfill over a live table, a destructive path that runs on every
start. Establish whether an exclusion held by a coordinating component covers the work it dispatches, since a child process inherits nothing. Then
establish whether more than one component can reach the same path, and whether the once-only guarantee comes from ordering, from a guard, or from neither.
Establish whether a path that drops and recreates the whole store is among those steps, and if it is, where in the order it sits. The acquisition semantics of
that path, and what it does to connections other components already hold and to the work in flight on them, are 01's; the mechanism that defers work out
of the request path is 01's; the windows the ordered steps open around it are this block's.*
Evidence: the ordered mutating steps with the window each opens; the exclusion holder against the session doing the work; one destructive step observed with concurrent connections present.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — a unit of work that is neither all-or-nothing nor usable after a tolerated error: a domain write that can partially commit, an error-absorption path that aborts its caller's work, a backstop whose advertised recovery can never execute.
- **HIGH** — availability loss or silently wrong results: store work serialised behind a single unbounded resource so one blocked operation degrades a whole process; live work destroyed by an operation that is correctly serialised but wrongly scoped; an invariant violated with nothing surfaced to anyone.
- **MEDIUM** — degraded operability or a bounded correctness gap: a mutation acting on rows its own selection predicate excluded; an exclusion that does not cover the work dispatched under it; a window in which concurrent writes go unmaintained; a multi-resource effect leaving a dangling reference or an orphan.
- **LOW** — observability and documentation drift with no runtime consequence today: a hold or release event an operator cannot see; work performed inside an exclusion only to log a count; a comment about locking that the code does not implement.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/03-db-concurrency/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `TXN-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- Verification-table entries are a methodology record, not a filter; a shipped test contradicting a finding is recorded as a remediation blocker, and what could not be reproduced under concurrency is a limit on the report recorded in the appendix, not a finding
