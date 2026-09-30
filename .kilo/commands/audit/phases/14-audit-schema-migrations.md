---
name: 14-schema-migrations
executor: auditor
problems-only: true
---

# Phase 14 — Schema And Migration Integrity

## Purpose

Audits the declared schema state and how it evolves: the revision chain read as a graph, each revision against its own reverse, the
object layer against the chain as two independent declarations of one schema, the objects neither declaration owns, the enumerated
vocabulary the process and the store disagree about, the index inventory against the predicates the code issues, the referential
actions and business keys, the source each deployed environment's schema actually comes from, and the residue the chain asserts and
does not perform.

This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — this phase owns the declared schema state and how it evolves: the revision chain as
a graph, each step against its own reverse, the model layer against the chain as two declarations of one
schema, the schema objects no declaration owns, enumerated-type parity, the index inventory against the
predicates the code issues, referential actions and business keys, which environment obtains its schema from
the chain, and the residue the chain asserts and does not perform. Other phases own: process topology, entry
surfaces and the start-up schema gate (01); settings values, secrets and environment policy (02); transaction
boundaries, lock semantics, constraint recovery and connection-pool configuration (03); the pipeline's own
writes and upload admission (05, 06); the query-cost consequence of a missing or unusable access path,
unbounded scans and table growth (11); whether a drift gate exists, is loaded and would notice (08); the
health contract that observes the schema (10); test-suite adequacy and the suite's own database isolation
(09); namespace rulings and cross-phase conflict resolution (99). No phase owns retrieval: this system has no
full-text search, so recall, ranking and per-language document questions do not arise anywhere in the set. A mechanism another phase owns is
recorded as a deferral with its owner named, and this phase still covers the schema-accuracy consequence of it.

A chain is a record of what a past change did, not a catalogue of what the system needs today. An access path or an object the chain
retains while no live predicate uses it is therefore not a defect on its own; report it where a live predicate has none at all,
and leave the measurable cost of a redundant one to the phase that measures.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed
behaviour, a static proof that a stated property does not hold, or a reproduced divergence; the method is the auditor's. A
passing check is methodology, never a finding. Where a property cannot be settled in the environment at hand, establish it from
what is observable and record it in the report's residual footer as a limit on this report, never as a finding.

### 1. The Revision Chain as a Graph: Heads, Branches, and the Order It Declares

*Derive the revision graph from declared predecessors rather than from the order files happen to sit in, and record the head count, every revision
whose declared predecessor is not the one naming it, and every revision nothing descends from. Do not presuppose the enumeration is complete: a
revision whose predecessor is declared by a name that resolves to nothing is an edge the ordering cannot follow. A second head, or a revision nothing
can follow, is a finding.*
Evidence: the derived graph with its head count; one revision with no reachable successor; one declared predecessor that resolves to nothing.

### 2. Each Revision's Reverse against Its Forward

*Compare, per revision, what the forward performs with what the reverse performs, and establish whether downgrading one revision and re-upgrading it
reproduces the schema it started from. A reverse that performs nothing, cannot restore a removed value, or leaves behind what the forward created, is
a finding; so is one re-establishing what a later revision removed deliberately. Whether the chain as a whole replays onto an empty store is 09's;
one revision measured against its own forward is this block's.*
Evidence: the per-revision forward and reverse pairs with an asymmetric verdict; one reverse that does not restore what its forward removed; one
reverse that recreates what a later revision dropped, and one downgrade reproduced on a store.

### 3. Two Declarations of One Schema: the Model Layer against the Chain

*Establish, per table, column, key and constraint, which declaration states it and where the two disagree. Establish first whether the chain's
revisions were authored as statements or derived from the object layer, because a chain authored as statements cannot be diffed by any means the
project owns. A column on one side and absent from the other is a finding in both directions. Whether a declared contract is executable, and whether
any path consults it, is 08's; the agreement between two declarations of one schema is this block's.*
Evidence: the per-object agreement matrix and its authoring method; one object declared on one side only; one declared pair that disagree, and one
direction of that disagreement reproduced against a live store.

### 4. Schema Objects with No Counterpart in the Model Layer

*Inventory the objects the chain owns that the object layer cannot express or does not declare — timestamp-maintenance triggers and their function,
stored enumerated types, and access paths defined over an expression rather than a column. For each one, which revision creates, alters and drops it,
and what outside the chain can change it. An object no revision drops, or one whose lifecycle lives only in a comment, is a finding.*
Evidence: the object inventory with a chain-owned, model-owned or unowned verdict; one object no revision drops; one object whose lifecycle is
described in prose only.

### 5. Enumerated-Type Parity between the Process Vocabulary and the Stored Vocabulary

*Compare the value set the application declares with the value set the storage engine enforces, in both directions. A value the application can emit
and the column cannot hold, and a value the column can hold that the application cannot name, are both findings — a revision that has already had to
remove a value is the pattern, not the exception. Ask specifically which way each divergence fails at runtime: a rejected write, a value silently
defaulted, or a row the application never returns.*
Evidence: both value sets with their symmetric difference; one value reachable in one direction only; one divergence reproduced with the runtime
failure it produced.

### 6. The Index Inventory against the Predicates the Code Actually Issues

*Derive the predicate inventory from the queries the application issues, including predicates over structured document columns and predicates whose
shape the caller supplies, then compare it with the access paths the engine can use for them. Ask whether a declared access path can serve the
operator actually issued, and whether a hot predicate has none. An access path retained with no live predicate behind it is not this block's finding;
the measurable cost of one is 11's.*
Evidence: the predicate-to-access-path map with the plan shape per predicate; one declared access path that cannot serve the operator issued; one hot
predicate with no access path at all.

### 7. Referential Actions and Business Keys: What Each Declaration States

*Establish, per relationship, the referential action the object layer declares and the action the chain declares, and whether the constraint exists in
both. Record what each declared action destroys on delete, and what a row naming a missing parent becomes. A relationship constrained on one side
only, or a delete action whose data loss is stated nowhere, is a finding. Lock semantics and constraint recovery at runtime are 03's; what
each declaration says is this block's.*
Evidence: the relationship inventory with action and constraint state per declaration; one relationship constrained on one side only; one delete path
leaving a live row naming no parent.

### 8. Which Environments Obtain Their Schema from the Chain, and Which Obtain It Otherwise

*Establish, per environment the deployment offers, where its schema comes from: the chain replayed at start-up, a pre-existing volume, a restored
dump, or an object altered outside the tool. A start-up path that mutates its own schema in one environment and not another is a finding, as is a
role, an owner or a grant established outside the chain. The process-level boot gate, meaning whether the process declares itself ready before it can
serve, is 01's; the source of the schema is this block's.*
Evidence: the environment × schema-source matrix with a reached or unreached verdict; one environment whose schema the chain does not describe; one
grant or role established outside the chain.

### 9. The Chain's Own Residue: Revisions and Statements That Assert Nothing

*Inventory every revision whose forward and reverse both perform nothing, every comment claiming a change the revision does not make, and every object
named in prose but never created. A revision existing only to occupy a position in the chain is a finding, as is a comment that is the only record of
a decision. Whether a drift gate exists, is loaded and would notice is 08's; the residue itself is this block's.*
Evidence: the revision inventory with an asserts-nothing verdict; one revision whose stated purpose is not performed; one comment that is the only
record of a decision.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — the store and the application disagree about the same data in a way that destroys or corrupts a record: an
  enumerated value the application can emit and the column refuses, a delete action that removes rows no declaration says it
  removes, or a relationship held by one declaration and absent from the other, so a row survives with nothing naming it.
- **HIGH** — a live predicate has no access path that can serve it, a declared access path cannot serve the operator the code
  actually issues against a structured column, or the two declarations of one table disagree on a column the application writes.
- **MEDIUM** — the schema state depends on something outside the chain's record: an environment whose schema the chain does not
  describe, a revision whose reverse cannot restore what its forward removed, a second head nothing descends from, or a grant
  established where no revision declares it.
- **LOW** — a revision that asserts nothing, a comment that is the only record of a decision, and an access path or object the chain
  retains with no live predicate behind it.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/14-schema-migrations/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `MIG-` — check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate
