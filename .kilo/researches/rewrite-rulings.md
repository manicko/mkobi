# Phase Rewrite — Cross-Batch Rulings

Binding decisions for the rewrite of the 16 phase files in `.kilo/commands/audit/phases/`.
Issued by the tech lead after reading `.kilo/researches/fit-batch-{a,b,c,d}.md`.
Where a fit report asked for a ruling, this file gives it. **Do not re-open a ruling.**

---

## R1 — Identity and output path

`audit-multi-phase.md:62-63` derives the output path from the **filename**:
`{PHASE_NUMBER}-{PHASE_NAME}` parsed from `NN-audit-name.md`.

Therefore, for every file:

- frontmatter `name:` == `NN-name` — that is, the stem with `audit-` removed.
  Example: `01-audit-process-architecture.md` → `name: 01-process-architecture`.
- Report Output findings path == `.ai/audit/NN-name/findings.md` — the same string.
- The `# Phase NN — …` heading may carry a human title; the path may not.

Phase 99 is the single exception, by design: its output is
`.ai/audit/99-validation/{NN}-{phase-name}-validated-findings.md`, written per audited phase.

## R2 — Frontmatter: three fields, no more

Keep `name`, `executor`, `problems-only`. Delete `status` and `validated` — no component of
the framework reads them, and 99 audits namespace continuity rather than ticket state.

`executor` is `auditor` for 01–15 and `validator` for 99.

## R3 — Report template now exists

`.ai/audit/templates/audit-findings.md` has been created. Every phase must reference it in
Report Output and must not describe a template of its own. Its contract is: front matter
(`phase`, `executed`, `executor`, `problems-only`, `findings`, `by-severity`), Summary,
Findings (six fields per finding: Severity, Zone, Observation, Evidence, Consequence,
Recommendation), Distribution, Cross-Finding Analysis, Roadmap, Rollout Safety, Appendices.

## R4 — Prefix namespace (final, no further renaming)

| Phase | Prefix | Note |
|---|---|---|
| 01 process-architecture | `TOPO-` | retires `ENT-`; the phase is no longer entry-led |
| 02 configuration-secrets | `CFG-` | retained |
| 03 db-concurrency | `TXN-` | `DB-` released to 14 |
| 04 authentication | `AUTH-` | fixes the live `AUT-` / `AUTZ-` mis-attribution hazard |
| 05 data-pipeline | `DP-` | retained |
| 06 file-artifacts | `ART-` | replaces `MED-`, which read as "media" |
| 07 external-boundary | `EXT-` | retained |
| 08 code-quality | `QLT-` | retained; **owner of the declared-contract angle** (see R7) |
| 09 test-coverage | `TST-` | retained |
| 10 production-ops | `OPS-` | retained |
| 11 performance | `PERF-` | retained |
| 12 authorization | `AUTZ-` | retained |
| 13 client-tier | `FE-` | |
| 14 schema-migrations | `MIG-` | takes the released `DB-` |
| 15 security-baseline | `SEC-` | |
| 99 validate | the audited phase's own prefix | `VAL-` for validation-level findings, in a separate section |

No two prefixes share a stem. `AUT-` no longer exists.

Every Report Output prefix bullet carries the collision clause: *check for a collision before
minting an identifier; report the collision rather than creating a second namespace.* Phrase it
as a re-derivation obligation — **never** assert that a prefix is or is not already present in
shipped source. The four "already in use in shipped source" notes in the current files are not
reproducible in the working tree.

## R5 — Four sections, fixed order

`## Purpose` → `## Audit Blocks` → `## Severity Taxonomy` → `## Report Output`.
Nothing else. `## Output Mode`, `## Discovery Stage`, `## Mandatory Runtime Verification` and
`## Audit Scope` are the legacy signature and must not reappear.

Block bodies are a single italic `*…*` span, hard-wrapped at roughly 130–170 columns,
followed by exactly one `Evidence:` line.

## R6 — Ownership of the two angles the set duplicated

The original set instantiated "a control that reports clean and examines nothing" five times
and "side effects across resources" three times, with no mutual deferral. Resolved as follows:

- **Vacuous-control angle** — defined **once**, in `99`. Phases 09 (test-coverage) and 10
  (production-ops) reference it with their own binding in one clause each. Phase 11
  (performance) does **not** carry it: this repository has no latency, query-shape or load
  gate, so the instantiation would be vacuous by construction.
- **Cross-resource side-effect angle** — owned by **05 (data-pipeline)**. It has exactly one
  live instance: a job record and the temporary file it names, written by different processes.
  Phases 01, 03 and 06 defer to 05.

## R7 — The declared-contract angle

Phase **08 (code-quality)** owns it: where a contract is declared, whether the declaration is
executable, and whether any path consults it. Phases 05, 06, 07, 10 and 12 defer to 08 rather
than restating it.

## R8 — The shared transient store: three-way split, identical wording required

Redis-backed transient state (revocation markers, rate-limit counters, the one-time secret,
queue hand-off) is touched by three phases. Each owns exactly one question, and all three
phases must use the same wording for the seam:

- **04 (authentication)** — what a revocation marker must express to actually revoke.
- **10 (production-ops)** — the composition of every key in the store and each marker's
  lifetime; the store as a load-bearing operational dependency.
- **15 (security-baseline)** — whether a surface is rate-bounded at all, and the credential
  material the store holds.

Phase 11 (performance) does not own any of it.

## R9 — Frontmatter-free status markers

`validated: yes` appears in the current 04. It is removed (R2). Continuity of identifiers is
preserved by the prefix table, not by a front-matter flag.

## R10 — What the auditors found that must survive into the text

These are verified live defects the fit reports surfaced. They are **not** to be written into
the phase files as findings — a phase states the angle, not the answer. They are listed here
so the rewritten phases demonstrably *cover* them, and so nobody mistakes a phase for a bug
report:

- The queue-consumer service is deployed and health-checked but never receives work; the
  wrapper that would enqueue to it is never called, and the compose file starts the vendor
  worker CLI rather than the repository's own wrapper.
- Fail-fast configuration checks run in the application factory, while schema application,
  version probe, account upsert, seeding, temporary-file cleanup and log retention all run in
  the lifespan — after the server begins answering.
- The access-management surface declares a required privileged role in its module docstring and
  in every endpoint description, and installs no such guard; the service methods it calls check
  nothing.
- The shared identity test fixture creates its user at the top role, short-circuiting every
  object-level access check.
- A temporary password is stored cleartext in the transient store and returned to a privileged
  caller; the retrieval handle travels as a request-path segment.
- The aggregate `check` target omits the backend suite; no automation directory exists.
- The declared index over a document-valued column cannot serve the predicate the read path
  actually issues.

## R11 — Language and register

English only, including the reserved strings `Evidence:` and `No problems found in this phase.`
Declarative, no second person, no imperative aimed at the reader except block openers. No
emoji, no exclamation marks.
