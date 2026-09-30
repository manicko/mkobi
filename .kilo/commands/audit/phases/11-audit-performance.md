---
name: 11-performance
executor: auditor
problems-only: true
---
# Phase 11 — Performance

## Purpose

Audits what this system costs and what bounds it: what a request costs and what a caller can make that cost, what is materialised whether or not the caller asked for
it, what the chosen storage shape costs on both the write and the read side, what a batch run and a periodic maintenance run cost against production data rather than a
fixture's, what deferred work costs the tier that accepted it, what each decision backed by the shared transient store costs a request, and what ceiling each long-lived
process imposes. This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — this phase owns the measurable consequence of latency, throughput and capacity, and the cost of a storage and processing shape already in place. It
owns nothing else. Owned elsewhere: the connection pooler's configuration semantics, lock and transaction semantics, and whether a maintenance run is safe to run twice
(03); whether the deployed path applies the resource declarations it makes, the store's availability as an operational dependency, and the health, liveness and
readiness endpoint and probe contract (10); the mechanism that defers work and the process topology it hands it to (01); parse, transform, aggregate determinism, full
recalculation after re-upload and temporary-file lifetime (05); the schema chain, index inventory against query predicates, and schema drift (14); per-request
authorization decisions and what a refusal discloses (12); production-code convention and dead code (08); the settings that bound any of the above (02). With 04, 10 and
15: this phase owns none of the shared transient store's key composition,
marker lifetime, revocation semantics, bound coverage or operational standing — 10 owns the key composition, the lifetime of each marker and the store as a load-bearing
operational dependency, 04 owns what a revocation marker must be able to express, and 15 owns bound coverage and the credential material the store holds. The two
deferrals this file previously carried — to a full-text search path and to a per-language key component — are withdrawn: neither subsystem exists in this system, and if
either is introduced, the result set and its measured cost are this phase's while key composition follows 10.

A cost that is negligible at the scale a shipped fixture creates is not a defect on its own. Report it only where the cost is unbounded by design rather than small by
data volume, or where a configuration the product does not deploy would price the same work differently.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed behaviour, a measured cost curve, or a
static proof that a stated bound does not hold; the method is the auditor's. A passing check is methodology, never a finding, and nothing here conditions a finding on
this phase's own list. Where a property cannot be settled in the environment at hand — a measurement at production data volume, or any measurement under real traffic —
establish it from what is observable, the declared constant, the plan shape, the statement and parameter counts and the per-request statement inventory, and state
plainly what could not be verified and why; a measurement that could not be taken is a limit on the report, never a finding.

### 1. Stated objectives, and what acts on them

*Establish which request paths carry real traffic and which carry a budget: a declared target nothing measures, a constant written once and read in more than one place,
and a threshold compared against a literal restated beside the value it should track. Establish whether any measurement behind a stated target is a distribution rather
than a single sample, and whether the value a consumer compares against is the value the system declares. Where no target is declared at all, that absence is the
finding, stated as such rather than omitted from the inventory. A target that exists and that nothing acts on is a different defect from a target nothing measures, and
neither is a defect in the value chosen against the traffic it covers.*
Evidence: the objective inventory with the path each covers against the paths carrying traffic, or its absence; the declared constant against the value each consumer compares; one target nothing acts on.

### 2. What the shipped performance instrumentation measures, and where it does not reach

*Establish what the shipped performance instruments cover: which request shapes a load profile reaches and whether each target resolves to a route, what dataset volume
they require, and which production query shapes a profiling path builds and omits. A harness requiring a volume no shipped environment reaches, one spending much of its
journey on responses that return early, and no harness at all are each a discipline in name only. Where no instrument reaches a production query shape at all, record the
absence with a reached or un-reached verdict rather than omitting the question.*
Evidence: the instrument inventory with a reached or un-reached verdict; the load profile's target inventory with a resolves verdict each where one exists; the volume any harness requires against the volume any shipped environment creates.

### 3. Query cost under caller-controlled input

*Establish the shape of what a statement does as the caller widens a filter: whether a caller-supplied selection becomes one equality predicate per key, whether those
predicates reach a document-valued column through a scalar extraction, and whether any bound on key count, key length or value length is in force. Establish whether
growth is additive or multiplicative — a predicate list
whose element count is caller-controlled and whose per-element cost is not constant is not readable from any single plan node — and whether the declared access paths on
that column are the ones the code's queries can actually use, or whether one is declared over the whole document where the read path extracts a single field. Establish
the bound in force on the selection, or record its absence with a reached or un-reached verdict. The index inventory against query predicates is 14's; what a
caller-controlled predicate costs is this block's.*
Evidence: the cost curve against a widening filter with the item count at each point; the bound in force on the caller-supplied selection or its absence; one predicate the declared access paths do not serve.

### 4. Per-request materialisation: eagerly loaded collections and unpaginated result sets

*Establish what is pulled regardless of how much the caller asked for: every collection configured to load eagerly on the aggregate the request touches, whether the
request needs it, and the row count each carries; a conversion run per row; a set fetched twice on one path. Establish what a request transfers per page view — payload,
element count, repeated records — and, on every surface that returns many objects, whether a bound on the number of rows exists at all. Establish the same for the
request that answers a probe: what it materialises per call, and whether the result the client sees is computed on each call or held constant — the health endpoint's
effect on the result the client sees, which is this block's, while the health contract itself is 10's. Establish whether a cost negligible at a shipped fixture's
scale is bounded by design or bounded only by an assumption about the data that will not hold.*
Evidence: the per-request materialisation volume with the row count each eagerly loaded collection carries; a set fetched more than once on one request; per-page-view payload and element counts; the list surfaces with a row bound and those without; what a probe-responding request materialises per call, and whether the result it returns is computed or held constant; the fixture's scale against the bound, if any.

### 5. The cost of the stored document shape

*Establish what the chosen storage shape costs on both sides: the write cost of replacing a whole aggregate's rows inside one transaction, the read cost of returning
document-valued columns per row, the storage cost of a uniqueness constraint expressed as a serialised form of a dimension document, and the index cost of a declared
access path over that column. Establish whether the declared access paths are the ones the queries can use, and whether a constraint expressed as a serialised form
compares whole documents to decide uniqueness. This is the consequence of a decision already made and not a defect to attribute: the finding is a cost that is real and
unmeasured, and a measured cost is better evidence than an argument from the shape alone.*
Evidence: the storage-shape inventory with the write, read, storage and index cost of each element; the access paths the code's queries can use against the ones declared; the measured cost of one aggregate at two volumes.

### 6. Background and batch work: cost, transaction width, and lock hold

*Establish what a batch run costs against production data volume rather than a fixture's: the work performed per unit of data, whether it is expressible as a set
operation or issued per row, and whether the resulting statement count scales linearly with the table. Establish how wide the transaction it runs in is — a delete
followed by an insert against the whole of one aggregate — what it holds for its duration, and what a live request does while it holds it. Establish what the periodic
maintenance run costs, how often it fires, and what it competes with while it does. Whether such a run is safe to run twice is 03's; its cost is this block's.*
Evidence: per run — statements issued, wall time, and the item count the cost scales with; the transaction's width and the locks held; one run whose duration competes with a live request.

### 7. Work that executes inside the request tier

*Establish which work the system defers to a background process and where it actually runs: the deferral mechanism, the consumer, and the process each consumer belongs
to. Establish what that costs the tier that serves requests — whether the deferred work occupies the same execution context as request handling, whether it is bounded,
and what a restart or a redeploy does to work already accepted, including what a client is told to expect while it is pending. Establish whether a component deployed to
take that work receives any, and treat a deployed component nothing feeds as a finding rather than as headroom. The mechanism carrying work across the loop boundary is
01's, and whether the deployed path starts the consumer at all is 10's; the consequence in latency, memory and lost work is this block's.*
Evidence: the deferral mechanism with its consumer and the process each belongs to; one accepted unit of work lost on restart; one deployed component with nothing enqueued to it.

### 8. What a store-backed decision costs a request, and what an outage does to it

*Establish what the request path pays for each decision that consults the shared transient store: the round trips, whether they are sequential or overlapped, and where
they sit relative to the rest of the request. Establish what happens to that path when the store is unreachable, and whether the admission decision a setting makes in
that case is the same one it makes when the store answers — an outage that admits a request the system would otherwise have refused is a different defect from one that
refuses a request it would otherwise have admitted, and the two must be told apart. Establish what a slow store costs the same path, which is a different question again
from what an absent one costs. Key composition and marker lifetime, what a revocation marker must be able to express, bound coverage and the store's standing as an
operational dependency are 10's, 04's and 15's; this block prices only the request-path consequence of each decision the store backs.*
Evidence: per store-backed decision — the round trips it adds to a request and where they sit; the request-path behaviour with the store unreachable, admitting against refusing; the request-path behaviour with the store slow.

### 9. The ceiling each tier imposes

*Establish, per long-lived process, what bounds concurrent work: the worker model, whether the worker count derives from the declared allocation or is a literal, and
whether that allocation is one the deployment engine in use actually applies. Establish what a representative request's cost implies, and whether that request is
CPU-bound or I/O-bound, because only one answer responds to more workers. Establish the same for the background process, including the concurrency model it actually
uses and what bounds how long work waits for it, since an unbounded wait is a latency property rather than a mechanism question. Multiply the connection ceiling one
process reaches by the process count and compare it with the store's own ceiling, which may be configured nowhere. Not how the connection pooler is configured (03's),
and not whether the production path enables it (10's).*
Evidence: per process — the worker model, the ceiling it implies, the source of the worker count against the declared allocation, and whether that allocation is applied; the CPU or I/O split of a representative request; the concurrency point in the background process and any bound on the wait; the connection count the serving tier can reach against the store's declared ceiling.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered. The bands are effect classes, not a closed
list of mechanisms, so a defect whose mechanism is not named here still lands by the consequence it is producing.

- **CRITICAL** — cost that exhausts a resource the whole system depends on, reached by an input a caller controls on a path that is on, so that one request can deny the
  service to every other caller.
- **HIGH** — cost that is real now and scales with a quantity the caller or the data controls, on a path that is on: one input able to multiply a statement's work
  without bound, or a cost linear in a production table that runs unattended against live traffic.
- **MEDIUM** — a cost demonstrated but conditional on volume or on a configuration not yet in effect, where the design is unbounded rather than the present value being
  large; materialisation a request pays for without needing it; a wait whose length nothing bounds.
- **LOW** — a stated objective with nothing that measures it; a description or runbook line that no longer prices the behaviour beside it; a discipline whose declared
  scope is wider than its coverage.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/11-performance/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `PERF-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
