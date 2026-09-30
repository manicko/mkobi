---
name: 99-validate
executor: validator
problems-only: true
---

# Phase 99 — Findings Adjudication

## Purpose

Audits audit **output** rather than the system: another auditor's claims, the support behind each of them, the band each was given,
the recommendation attached to it, the finding-ID namespace across the whole set, the shared findings template as a controlled
artefact, and the seams between phases. It is also where two angles are defined once for the set — the vacuous-control angle and
the cross-resource side-effect angle — and where the bindings other phases declare of them are adjudicated. It never modifies
source code, never renumbers an existing finding identifier, and never repairs a shared artefact from inside a per-phase run.

This file names what to examine and under which angle; the executing validator discovers the concrete artifacts.

**Scope Boundaries** — this phase audits **output** and the audit tooling's own artefacts: another
auditor's claims, the support behind them, the band each was given, the recommendation attached to it, the
finding-ID namespace across the set, the shared findings template as a controlled artefact, and the seams
between phases. The other phases audit the system; no content phase's concern is this phase's, except where
a finding's validity depends on a cross-phase claim. This phase never modifies source code, never renumbers
an existing finding identifier, and never repairs a shared artefact from inside a per-phase run; the only
documents it writes are its own validated reports and the residual footer they carry. It defines the shared
angles it owns — the vacuous-control angle and the cross-resource side-effect angle — and adjudicates the
bindings other phases declare of them; it does not audit the system to decide whether a control is any
good. The namespace ruling is this phase's, and every other phase in the set currently carries such a note;
their stated provenance must be re-derived here, not inherited. The seam check — a finding filed outside the
input's own declared scope — is this phase's, and no other phase performs it. The drift gate that would
have caught a claim's drift before its report was written is 08's; this phase adjudicates the claim as
filed. The findings-template contract is now the artefact under validation rather than a path that resolves
to nothing: its six front-matter fields, its six per-finding fields, its rule that the zone be the block
title quoted verbatim, and its reserved empty-state string are each in scope; and because it enumerates no
finding-ID prefixes, the namespace ruling rests on the phases' own declarations paired with the template's
front-matter `phase:` value.

An input report and the validated report derived from it are deliberately different artefacts: different namespaces, different
disposition vocabulary, and a re-grade recorded rather than applied silently. That difference is the product of this phase and is
not itself a defect.

## Audit Blocks

Each block is independent — execute any one with no knowledge of the others, and each carries its own evidence, which here is a
disposition record: what was re-derived, what reproduced the claim, what refuted it, or what could not be settled and why. The
disposition vocabulary is fixed — confirmed, re-typed, re-graded, merged, not substantiated, and unsettled — and no verdict is
withheld. A passing row in the input's own evidence fields is methodology, never a verdict, and no adjudication is gated on the
input's declared blocks. A claim that cannot be settled in the environment at hand is recorded as unsettled with its reason; it is
never recorded as confirmed.

### 1. The Claim Re-Derived from the Executing Path

*Confirm or refute the claim from the executing path alone. Ignore the quoted snippet, the comment and the line anchor. Does the path still do what
the claim says, at the location it says, after the drift? Resolve every location reference mechanically first — a reference into lines that do not
exist is a wrong approval by default, not a formatting slip. A comment, docstring or runbook line that contradicts the executing path is itself a
finding, never a source of truth; so is the asserted cause, which can be false while the finding it supports survives. The drift gate that would have
caught the drift before the report was written is 08's; adjudicating the claim as filed is this block's.*
Evidence: per finding — the executing path, whether the anchor resolved, the claim tested on its own terms, and the asserted cause tested separately.

### 2. The Vacuous-Control Angle, and Its Bindings: Does It Exist, What Scope Does It Declare, What Did It Examine

*Establish the vacuous-control angle once, here, for the whole set: for each control, three separate questions — does it exist, what scope does it
declare, what did it actually examine — and a fourth kept apart from the three, because whether it ran at all is not whether it decided anything. A
control that ran and reported clean substantiates nothing, however central it is to an argument. For every check, gate or shipped regression a claim
leans on, apply the angle. Then apply it to the angle: establish which phases bind it in their own words and whether each binding still asks the
three questions. A control that is present, configured and deciding nothing is a finding in the audit itself, not a pass; so is a phase that binds
the angle in words no longer asking it.*
Evidence: per control — existence, declared scope, the item count actually examined, and the path by which a verdict would have reached a decision;
per binding phase — the wording used and whether the three questions survive; one control green over zero items.

### 3. The Grade against the Audited Phase's Own Rubric

*Compare the band a finding carries against the band the audited phase's own rubric assigns, since that phase's severity section is the rubric of
record, and grade by effect and blast radius anchored to present state. A mechanism absent from an enumerated band is not thereby a lower band, and a
band left empty is a valid outcome rather than a gap. Grade the finding, not the mechanism: a real defect whose asserted cause is factually wrong is
not thereby mis-graded, and a claim that cannot fail is either vacuous or real and graded too low. A finding this phase re-grades keeps the band its
own rubric implies and the re-grade is recorded as such; it is never silently applied.*
Evidence: per finding — the band the audited rubric assigns, the band carried, and the mechanism it was downgraded on, if any.

### 4. Which Side Moves: Code or Documentation

*Judge from which artefact is load-bearing and which the rest of the corpus depends on. No verdict is reserved in advance for any finding class, and
re-typing runs in both directions. A dead-code label is not substantiated until the specification corpus has been asked whether the component is
intended: a component no code path reaches, but that the specification or a configuration surface expects, is a missing integration, not dead code.
The disposition recorded is re-typed — the finding re-filed under the phase that owns the concern — or merged, where the same root cause already has
a filing; not substantiated is available here too and must be argued rather than assumed. What the specification corpus asserts about a component's
intent is not this phase's to confirm against production code; this block asks what the corpus claims and adjudicates the label against it.*
Evidence: per finding — which artefact is load-bearing, the specification-corpus answer, and the disposition after adjudication: re-typed, merged, or
not substantiated.

### 5. Whether the Recommendation Can Be Carried Out

*Record whether the recommendation can be carried out: does it name a target that exists and is stable, does applying it remove the defect it claims
to remove, what does it depend on, and what else breaks — and in which order. A recommendation that is vague, offers alternatives, or names no
implementation approach is substantiated but unusable: a distinct outcome from rejection, recorded as such rather than passed over or counted as a
failure. What the smallest change would in fact be is the reader's to accept, not this phase's to redesign; this block establishes only whether the
recommendation can be executed and what executing it would disturb.*
Evidence: per recommendation — target resolved, dependencies, what fixing it breaks, and its order in the roadmap.

### 6. Cross-Phase Conflict, Ownership and Merge

*Enumerate the contested claims across the set: ownership decisions accumulate across the family, so a claim filed under a phase that does not own
it, or two phases claiming the same concern, is a defect in the audit, and detecting it is a first-class obligation, not an optional extra. Compare
against whatever sibling reports exist, declare which are raw and which already validated, and record rather than silently edit a merge whose target
sits in a phase already written out. Same root cause is a merge; an adjacent concern is a cross-reference; two phases reaching opposite conclusions
about the same subject is a conflict. The seam check this phase owns: a finding filed outside the input's own declared scope paragraph is a defect in
the input report, not a merge, and no other phase performs it.*
Evidence: per contested finding — the rival claim, the phase that owns the concern, the disposition, and the set of sibling reports compared against;
one finding whose zone falls outside the input's own declared scope.

### 7. Finding-ID Namespace Integrity — The Ruling This Phase Owns

*Establish per phase: the prefix the phase declares in its own report-output contract; the identifiers past runs minted; markers embedded in shipped
code, configuration, tests and documentation; the compound form the template's front-matter phase value pairs with the prefix; and one namespace
reused across phases. Then render a ruling rather than only counting collisions — whether a new run reuses the declared namespace or mints a second
one beside it, and whether the in-source markers are load-bearing provenance to be migrated by a follow-up or drift to be retired. Every provenance
claim must be re-derived from the working tree: a sibling phase asserting that a prefix is already in use in shipped source is a claim to test, never
an inherited fact, and a claim that cannot be reproduced is itself a defect in that report. A validator that enumerates a collision and stops has not
done this block.*
Evidence: per prefix — declared, minted, in-source markers found or none, the compound form resolved, reuse across phases, and the ruling applied; one
provenance claim that could not be reproduced.

### 8. The Shared Findings Template as a Controlled Artefact

*Inventory the mandates the shared template carries and establish whether each survives into the reports written under it. The template this phase
produces against is itself under validation, and it resolves. The front-matter fields a report must set and whether each is present and honest; the
fields every finding must carry and whether any is omitted or renamed; the rule that the zone be the block title quoted verbatim and whether any
finding's zone is a paraphrase or absent; the reserved empty-state string and whether any report both omits it and pads a summary in its place; and
the sections the template treats as required against those the reports actually carry. It enumerates no finding-ID prefixes, so the namespace ruling
rests on the front-matter phase value paired with the prefix, which is the preceding block's. Record the defects — never repair the template from
inside a per-phase run.*
Evidence: per mandated element — present, omitted, or renamed across the reports written under it; one finding whose zone is not the block title
quoted verbatim; one report whose front matter states a phase other than the phase that wrote it; each defect recorded, not edited.

### 9. Does the Input Rest on its Own Declared Blocks and Evidence Fields

*Establish across this family whether the executed phases have shared one signature: their own named blocks pass while their real findings arrive from
an angle the phase never names — in some phases the pre-pass states as expected the very mechanism that produced a finding, and in one the
admissibility rule would have excluded every finding the run reported. Ask of this input whether any substantive finding rests on its own phase's
declared block list or its own evidence fields as its support, and whether the report contains at least one angle the declared blocks never named.
The answer is what it is; this block asks, it does not conclude.*
Evidence: per finding — whether its support is the input's declared blocks, its own evidence fields, an independent observation, or none of these; and
any finding arising from an angle the declared blocks do not name.

### 10. The Validated Report as an Artefact, and What Was Not Settled

*Establish the validated report as an artefact in its own right. Every finding in scope carries a verdict, its own identifier, and the re-derivation
behind it; the disposition tally agrees with the per-finding verdicts; identifiers are preserved, never renumbered; the audited namespace and the
validation namespace never share a table. Every field the template mandates per finding is present, with location carried inside the observation
field rather than as a field of its own. The report is readable on its own, which requires the anchor and the evidence rather than their removal.
Every claim that could not be settled in this environment is listed with the reason and is never recorded as confirmed; where only a stated sample
could be re-derived, record the sample and the rate. The coverage ledger — blocks examined, the item count each reached, and every claim left
unsettled with its reason — belongs in the appendices as a fixed residual footer, never in the findings body.*
Evidence: the disposition tally against the per-finding verdicts; each unresolvable or missing mandatory field; each claim left unsettled and why; the
coverage ledger with the item count each examined block reached.

### 11. The Shared Angles, Defined Once and Bound by Name

*Establish the angles this phase holds as definitions rather than as instantiations: the vacuous-control angle, defined in the second block, and the
cross-resource side-effect angle — an effect spanning more than one resource, together with which resource is the real unit of atomicity. For each
one, which phases bind it in their own words and whether the bindings still ask the same question; the live cross-resource instance itself belongs to
the phase that owns it, and this block does not audit the system to decide whether any control is any good. Two bindings drifted into different
questions, and an angle claimed by a phase that does not bind it, are findings; so is an angle named by a phase that no phase defines.*
Evidence: both angle definitions with the phases binding each and the wording drift per binding; one angle bound by two phases asking different
questions; one angle cited with no definition anywhere in the set.

## Severity Taxonomy

Two scales are in play and they are never mixed. A finding under validation keeps the band its own phase's rubric gave it, and this
phase may re-grade it only against that rubric. A defect **in the audit** is graded by effect and blast radius below, anchored to
present state: rate what is true now, not the worst consequence if triggered.

- **CRITICAL** — a wrong approval: a claim confirmed that the system does not support, or an absence recorded as established. A
  reader acts on it, remediation is built on it, and nothing downstream can distinguish it from a correct report.
- **HIGH** — a real defect released: a true finding rejected, merged away, or graded below what its own rubric implies, so work that
  must be done never reaches the roadmap.
- **MEDIUM** — a report the reader must repair before acting: a finding filed under a phase that does not own it, two claims about
  the same subject that disagree, a disposition tally that does not match the per-finding verdicts, an identifier resolving to more
  than one finding, or a shared angle bound by two phases in words that ask different questions.
- **LOW** — drift with no remediation consequence today: template metadata that does not resolve, a phase note that cannot be
  reproduced against the working tree, and a naming or wording inconsistency between two phases of the set.

An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming.

## Report Output

- Findings path: `.ai/audit/99-validation/{NN}-{phase-name}-validated-findings.md` — one validated report per phase, carrying the audited phase's own prefix and identifiers; the directory is created by this run, and the deliberate divergence between this phase's file stem and its output directory is recorded here so a later run does not correct it
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter (with `phase:` set to the audited phase and `executor: validator`), summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: the audited phase's own prefix, preserved. Validation-level findings discovered *during* validation use `VAL-` and occupy a separate section — never interleaved into the findings table, because the two would share a `Severity` column carrying two different scales. Re-derive the audited phase's prefix from that phase's own declaration; check for a collision before minting an identifier; report the collision rather than creating a second namespace
- Incremental append, ≤100 lines per pass — never write the entire report in a single call
- `problems-only: true` — suppress commentary about the validation itself, **not** dispositions; every disposition is a deliverable row, and a confirmed finding still carries one
- Empty state, exactly: `No problems found in this phase.` — and the coverage ledger goes in the appendices, never in the findings body: the blocks examined, the item count each actually reached, and every claim left unsettled with its reason, as a fixed residual footer
