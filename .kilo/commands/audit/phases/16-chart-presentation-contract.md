---
name: 16-chart-presentation-contract
executor: auditor
problems-only: true
---

# Phase 16 — Chart Presentation Contract

## Purpose

Audits the presentation contract a served figure is described by, following that contract from its declaration outward to the rendered
frame: which fields the serving tier declares it will populate, which of those a response actually carries, which declared measures and
dimensions the renderer reads and which it passes over, what a declared chart type lets the renderer discard, and whether a configured filter
reaches the query the figure is drawn from. The two things compared throughout are the figure the configuration describes and the figure the
reader is shown: each declared field carries a populated or never-populated verdict, and each declared measure or dimension an honoured,
discarded or coerced one, rather than an impression of agreement.

This file names what to examine and under which angle; the executing auditor discovers the concrete artifacts.

**Scope Boundaries** — this phase owns the presentation contract as the serving tier declares it, as it is populated into the
response, and as the renderer consumes it: measure and dimension selection, per-chart-type interpretation, and filter-to-figure
binding. Other phases own: how a measure name is derived, and whether an aggregation is skipped while the run still reports success
(05 b4 / b6); whether a fixed value or a vocabulary has one named home, and a value written in both tiers with nothing keeping
them equal (08 b1 / b2); whether a served response matches the client's declared type, or an optional field is simply absent
(13 b7 / b10); what the shipped bundle resolves against the build-time inputs the client declares (13 b5), and what is served from
disk as a built artefact (06 b6); whether absent data renders distinguishably (13 b7); whether the product decisions examined here have
any assertion that would reject them (09 b1); response payload and per-process ceilings (11 b4 / b9); finding-ID namespace rulings and
cross-phase ownership conflict (99). Client bundle composition is assigned by deferral in 10 but is enumerated by no active phase's
scope paragraph; its nearest claimants are 13 b5 and 06 b6, neither of which examines what the renderer reads from a served response.
This phase does not take it. A mechanism another phase owns is recorded as a deferral with its owner named, and this phase still
records the consequence the reader is left with.

The contract is examined from the declaration outward, not from the renderer inward. A field the client honours that no tier declares is a
different question — it asks what the client invented rather than what the configuration lost — and it belongs to the served-shape
comparison (13 b10) and to the declared-contract angle (08 b8).

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others. Evidence is a class, not a check list: observed
behaviour, a static proof that a stated property does not hold, or a reproduced divergence; the method is the auditor's. A
passing check is methodology, never a finding. Where a property cannot be settled in the environment at hand, establish it from
what is observable and record it in the report's residual footer as a limit on this report, never as a finding.

### 1. The declared presentation contract: which declared fields the served response never populates

*Derive the field set the serving tier declares it will populate for a served figure, from the declaration rather than from the data seen
in a response. Per field establish whether any construction site supplies it, and whether it is supplied unconditionally, under a
condition, or never. Then ask what a value is drawn from when the field is absent — a default, whatever the surrounding code happened to
hold, or nothing — and whether a configuration naming that field can be stored with no effect at all. A declared field no construction
site supplies is a finding; so is one whose value is filled from whatever was in hand rather than from what was declared. Whether the
response shape as a whole is checked at the boundary is 13 b10's, and what the build resolves those declared fields against is 13 b5's;
which declared fields are ever populated is this block's.*
Evidence: the declared-field inventory with a populated or never-populated verdict per field; one declared field no construction site
supplies.

### 2. Declared measures and dimensions: which are honoured, which are silently discarded, and which depend on a name the two tiers must agree on

*Derive the inventory of declared measures and dimensions from what the renderer actually reads, not from what a configuration may name;
per entry record whether a selection made of it reaches the frame, reaches it under a different name, or never reaches it. Establish
whether any member of a declared list past the first is read by anything, and whether a name crossing the boundary is resolved by
agreement between the tiers or by anything that would keep them equal. A measure the configuration selects and the frame never draws is a
finding; so is a selection narrowed to a leading part of what was declared. Whether a fixed value or a vocabulary has one named home is
08 b1 / b2, and how such a value is derived in the first place is 05 b4 / b6; whether the disagreement changes what the reader sees
is this block's.*
Evidence: per declared measure an honoured or discarded verdict; one declared measure array whose later members no code reads; one name
resolved by agreement between the tiers with nothing keeping them equal.

### 3. Per chart type: what the rendered figure is derived from, and what the declared type permits the renderer to discard

*Enumerate the chart types a configuration may declare, and per type establish what the frame is actually built from and which part of the
declared settings reaches it. Establish where a setting is converted or defaulted and then written a second time in the same path, and
which of the two writes survives to the frame. Establish where a branch consumes only a leading part of the collection it is handed —
whether the remainder is dropped, defaulted, or carried forward unread — and what the declared type permits the renderer to ignore of what
was declared for it. A declared type whose frame is drawn from something other than its declared source is a finding; so is a converted
setting overwritten before anything reads it.*
Evidence: the per-type derivation record; one type where a converted presentation setting is overwritten; one branch taking only a leading
part of what it was given.

### 4. Filter binding: whether the configured selection reaches the query the figure is drawn from, and what the user sees when it does not

*Establish per configured filter where the selection is stored, where it becomes something the data path can see, and whether the frame
is drawn from the request that carries it. Establish what the reader is left looking at when the selection reaches the control but not the
request — a frame answering a wider question than the one asked, with nothing on screen saying so — and where a filter narrows a quantity
other than the one the frame is labelled with. A control reporting itself applied while the frame does not carry the restriction is a
finding; so is a filter that narrows no query and changes no frame. Whether a figure is drawn at all over an empty result is 13 b7's;
whether the figure drawn is the figure the selection implies is this block's.*
Evidence: the filter-to-request binding record; one configured filter that changes no query and no frame.

## Severity Taxonomy

Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — the reader is shown a figure that is not the figure the configuration describes, and nothing on screen or in the response
  distinguishes the two: a selection the control reports as applied that the request never carries, a declared measure nothing reads so the
  frame is drawn from something else, or a declared type rendering from a source other than the one declared for it. A reader acting on a
  confident wrong number is the outcome, and that is worse here than an error or a refusal would be, because the product never invites
  doubt in what it drew.
- **HIGH** — the frame is complete-looking and wrong in one respect the configuration asked for: a declared field no construction site
  supplies, so its setting is silently absent from every figure; a presentation setting converted and then overwritten before it is read;
  a branch consuming only a leading part of what it was given, leaving part of what was asked for absent from an otherwise correct figure.
- **MEDIUM** — the contract and the frame diverge where the figure itself stays true: a declared measure or dimension the renderer
  discards while drawing from a broader selection, a filter narrowing the request but not the axis the frame is labelled with, a
  configured filter that reaches neither the request nor the frame, or a declared field populated only under an arrangement the
  product does not ship.
- **LOW** — drift with no figure consequence today: a coercion that happens to yield the declared value, a declared field no shipped
  arrangement ever populates, or a filter recorded more than once where no code reads the two records together.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/16-chart-presentation-contract/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `CHT-` — check it against the active phase namespace before minting an identifier; a finding whose identifier is already held in that namespace is re-identified, never merged into the finding that holds it, and a prefix already in use elsewhere is reported rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate
- The two tiers disagreeing about a name is not by itself a finding here: name the rendered consequence on the screen, or record it as a deferral to 08 b1 / b2; a disagreement that reaches no figure belongs to the owning phase