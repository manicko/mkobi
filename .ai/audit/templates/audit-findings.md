---
phase: NN-phase-name
executed: YYYY-MM-DD
executor: auditor
problems-only: true
findings: N
by-severity:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 0
  LOW: 0
---

# Phase NN — Findings

## Summary

Three to six sentences. What zone was examined, what was reached at runtime, and the single
most consequential thing found. If the phase produced no findings, state the exact reserved
string `No problems found in this phase.` and stop — do not pad the section.

## Findings

One block per finding, in descending severity. No finding without all five fields.

### PREFIX-001 — <one-line title stating the effect, not the mechanism>

**Severity** — CRITICAL | HIGH | MEDIUM | LOW

**Zone** — the audit block title this finding came from, quoted verbatim.

**Observation** — what is true now, stated as a fact about the system. Concrete: the component,
the value, the path shape, the reproduced behaviour. No hedging.

**Evidence** — the artefact that makes the claim checkable: observed output, a reproduced
behaviour, or a static proof that a stated property does not hold. Name it; do not paste a
transcript of the entire session.

**Consequence** — the exact effect on this system, at its real blast radius, as it stands
today. Not the worst case if triggered again under different conditions; what is true now.

**Recommendation** — the smallest change that removes the effect, and the direction to take
when the fix has more than one reasonable shape. Where a shipped test currently asserts the
behaviour, name it as a remediation blocker: the test encodes the defect and must change with
it.

## Distribution

Which components, tiers, environments or roles the findings fall on, and which single one
carries the most. One short paragraph plus at most five bullets.

## Cross-Finding Analysis

Only when two or more findings in this phase share a cause. Name the cause and the findings
that share it. If every finding is independent, write one line saying so — do not manufacture
a pattern.

## Roadmap

Ordered remediation sequence, each step naming the findings it closes and what must be true
before the next step starts. Group by cause, not by severity, when causes differ.

## Rollout Safety

For any step that changes observable behaviour: what could break, which other zone depends on
the current behaviour, what must be verified afterwards, and how to revert. One or two
paragraphs; omit the section only if no step changes observable behaviour.

## Appendices

Supporting detail that would otherwise dilute the findings: enumeration tables, derived
counts, measurement method, artefacts consulted. Optional.
