# Audit Phase Conventions — Analysis of the Current Phase Set

Analysis artefact. Not a phase file. Nothing in `.kilo/commands/audit/phases/` was modified.

---

## 0. Method and evidence base

- All 25 files in `.kilo\commands\audit\phases\` were read in full.
- The 5 sibling commands (`audit-phase-gaps.md`, `audit-phase-refine.md`, `audit-orphaned.md`, `audit-refine.md`, `audit-multi-phase.md`) were read for framing only.
- Structural claims below are grep-verified over the whole set; counts are quoted inline where they matter.
- Git facts: 10 of the 25 files are tracked (`git ls-files`). The 15 modern files are **untracked** working-tree additions; `99-audit-validate.md` is tracked and modified — its committed version is legacy-style (`## Step 0 — Ensure Docker Environment is Running`, `## Discovery Stage`, `## Workflow`), its working-tree version is the modern style. That single diff is the framework's own in-place migration precedent and is cited as such.
- Project shape, verified only for scope plausibility: FastAPI entry point (`src/mkobi/main.py`, docstring "Main FastAPI application file"), package `src/mkobi/{api, db/repositories, services, data, workers, settings, core, interfaces}`, RQ worker wrapper (`src/mkobi/rq_worker_wrapper.py`), Alembic, a React 19 + Vite + MUI + TanStack Query + zod SPA (`frontend/package.json`), compose files under `docker/` (not the repo root), PostgreSQL, `.env` / `.env.docker` at the root.
  The brief described this as "Django + HTMX with an async Telegram bot". The repository is FastAPI + React SPA. This matters for the verdicts: several *modern* files carry Django-shaped nouns (§3 FM10), while several *legacy* files are closer to the real architecture. Verdicts below follow the repository, not the brief.

### 0.1 Conclusions at a glance

- The 25 files are **two families, not a spectrum**. 9 files (family M) prescribe a runtime procedure and gate their content on it; 16 files (families B + V) declare an audit zone and independent blocks. The two sets share exactly one convention — the empty-state string.
- **The current style is the 16-file B/V family**, and it is untracked in git; `99-audit-validate.md` is the one tracked file that has been migrated in place, which is the framework's own precedent for the migration the other 8 need.
- **Verdicts**: 16 keep as reference, 4 refine in place, 4 obsolete-but-superseded, 1 obsolete with no unique coverage.
- **The single most important forward-looking finding**: the modern files removed *file paths* but retained *framework nouns* ("WSGI", "management-command dispatch", "declarative admin surfaces", "the framework's own administrative interface", "compiled catalogs"). The codebase is FastAPI + React, so the architecture-agnostic goal is only half-achieved (§3 FM10).
- **Three coverage gaps** that the deletions must not widen: the client tier (`02-audit-frontend.md` is its only owner), the ingestion/aggregation pipeline (`07-audit-data-processing.md`), and global schema/migration/index integrity (residual of `03-audit-database.md`).
- **One framework-level defect blocks every phase**: the template `.ai/audit/templates/audit-findings.md`, referenced by all 25 files, does not exist in the repository (§3 FM13).

---

## 1. Taxonomy of the existing phase files

### 1.1 Style families

| Family | Label | Defining shape | Files |
|---|---|---|---|
| **M** | Prescribed-methodology checklist | `## Output Mode` boilerplate → `## Discovery Stage` (4 numbered discoveries) → `## Mandatory Runtime Verification` (`Step R0…Rn`) → `## Audit Scope` → `## Audit Dimensions` (check tables + one `**Evidence required:**` per dimension) → `## Report Output`. No `Audit Blocks`, no `Severity Taxonomy`, no scope boundaries. | 9 |
| **B** | Independent-block domain phase | `## Purpose` (incl. Scope Boundaries) → `## Audit Blocks` (`### N.` title, `*Establish…*` body, `Evidence:` line) → `## Severity Taxonomy` → `## Report Output`. | 15 |
| **V** | Validator phase | B skeleton, plus disposition vocabulary and a separate validation severity scale. | 1 (`99`) |

Counts: 9 + 15 + 1 = 25. Structural grep: `## Audit Blocks` present in 16 files, `## Severity Taxonomy` in 16, `## Discovery Stage` in 9, `## Mandatory Runtime Verification` in 9, `## Audit Scope` in 9. The two sets are disjoint.

### 1.2 Per-file classification

Verdicts use: `keep as reference` / `refine in place` / `obsolete — superseded by X` / `obsolete — no unique coverage`.

| File | Family | Purpose (one line) | Verdict |
|---|---|---|---|
| `01-audit-backend.md` | M | Whole-backend sweep: layer integrity, API contract, access control, data processing, code quality, preceded by 6 mandated runtime steps. | **obsolete — superseded by `01-audit-entry-architecture.md`, `03-audit-db-concurrency.md`, `07-audit-data-processing.md`, `10-audit-code-quality.md`** |
| `01-audit-entry-architecture.md` | B | Entry surfaces, process topology, boot/stop lifecycle, schema gate, cross-process shared state, route wiring. | **keep as reference** |
| `02-audit-config-secrets.md` | B | Settings variant selection, env-var name contract, secret guards and provenance, environment/process parity. | **keep as reference** |
| `02-audit-frontend.md` | M | React client tier: component/state architecture, rendering, client security, TS types, accessibility. | **refine in place** — the only client-tier owner in the set |
| `03-audit-database.md` | M | Migration chain, schema drift, index health, constraints, transactions, test DB isolation. | **refine in place** — narrow to the schema/index/referential-integrity residual |
| `03-audit-db-concurrency.md` | B | Transaction boundaries, in-transaction error handling, constraint recovery, read-modify-write, lock registry, background-run safety, schema mutation windows. | **keep as reference** |
| `04-audit-auth-login.md` | V-adjacent B | The deep-link login handshake end to end: issuance, delivery, claim, identity binding, post-linking gate, state transfer, abuse limiting. | **keep as reference** |
| `04-audit-security.md` | M | Generic security sweep: JWT handling, authorization, secrets, input validation, rate limiting, password hashing, CORS/headers. | **refine in place** — shrink to two residual blocks |
| `05-audit-ad-lifecycle.md` | B | Ad lifecycle state model, write-path parity, lifecycle clocks, publish gate, classification tree, photo collection, cleanup sweeps. | **keep as reference** |
| `05-audit-docker.md` | M | Container reproducibility, secrets, isolation, resilience, container security, deployment safety. | **obsolete — superseded by `12-audit-production-ops.md`** (+ `01-audit-entry-architecture.md`, `02-audit-config-secrets.md`) |
| `06-audit-pii-consent.md` | B | Consent semantics, erasure completeness, identifier fields, residue, content hiding, egress basis, cross-process consent. | **keep as reference** |
| `06-audit-tests.md` | M | Test anti-patterns, critical-path coverage, isolation, type safety in tests. | **obsolete — superseded by `11-audit-test-coverage.md`** (one clause to fold, see §6) |
| `07-audit-data-processing.md` | M | Ingestion pipeline: trace, temp-file cleanup, transactional store, determinism, full recalculation, error paths. | **refine in place** — the only pipeline owner in the set |
| `07-audit-media.md` | B | Media path end to end: key ownership, admission controls, metadata stripping, derived sets, serving gate, reconciliation, capacity. | **keep as reference** |
| `08-audit-deployment-config.md` | M | Configuration management, startup lifecycle, production readiness, overengineering check. | **obsolete — superseded by `02-audit-config-secrets.md`, `01-audit-entry-architecture.md`, `12-audit-production-ops.md`** (residual to fold into `10-audit-code-quality.md`) |
| `08-audit-search-fts.md` | B | Unauthenticated search path: match predicate agreement, index maintenance, per-language documents, query input, abuse control, filter composition, cached sets. | **keep as reference** |
| `09-audit-external-api.md` | B | Outbound third-party calls and the public inbound surface: credentials on the wire, encoding, retries, aggregate budgets, bridge, degradation, validation boundaries. | **keep as reference** |
| `10-audit-code-quality.md` | B | Convention vs enforcement: fixed values, boundary validation, type width, unit responsibility, one-rule-one-home, dead definitions, declared contracts, migration gates. | **keep as reference** |
| `11-audit-test-coverage.md` | B | Test suite as a distributed system: decisions exercised vs reachable, doubles, fixture contract, boundary sides, harness, reproducibility, merge gates. | **keep as reference** |
| `12-audit-production-ops.md` | B | Deployed-system composition: container posture, artifact provenance, controls that examine nothing, gates, deploy/revert, health contract, edge tier, backup/restore, observability, runbooks. | **keep as reference** |
| `13-audit-performance.md` | B | Measurable cost: response budgets, gates, harness coverage, cache keys and hit cost, query cost under caller input, per-object work, per-tier ceilings. | **keep as reference** |
| `14-audit-i18n.md` | B | Language selection, consumers, locale activation, localized storage and fallback, format localization, cache tiers, translation pipeline, catalogue integrity, script representability. | **keep as reference** |
| `15-audit-authorization.md` | B | What an access decision returns: level representation, privileged surfaces, ownership single/multi-object, callee trust seam, account state, cross-process parity, disclosure, CSRF coverage. | **keep as reference** |
| `90-audit-integration.md` | M | Cross-cutting: route contract both sides, auth flow both sides, end-to-end data flow, schema alignment, env consistency, error propagation. | **obsolete — no unique coverage** (distributed over `02`, `04`, `09`, `15`) |
| `99-audit-validate.md` | V | Adjudicate another auditor's findings: re-derivation, green-control support, rubric re-grade, code-vs-doc ruling, recommendation viability, cross-phase merge, namespace ruling, template as artefact. | **keep as reference** |

Summary: **16 keep as reference** (the 15 B files plus `99`), **4 refine in place**, **4 obsolete — superseded**, **1 obsolete — no unique coverage**. 16 + 4 + 5 = 25.

### 1.3 Pairs covering the same audit zone

Declared overlap — one file's zone is inside another's:

| Zone | Overlapping files | Where the overlap sits |
|---|---|---|
| Layer discipline, dependency direction, route surface | `01-audit-backend.md` × `01-audit-entry-architecture.md` | legacy "### 1. Architectural Integrity" (Layer Isolation, Dependency Direction, No Business Logic in Transport) vs ENT blocks 8 and 9 |
| Code-quality sweep | `01-audit-backend.md` × `10-audit-code-quality.md` | legacy "### 5. Code Quality & Maintainability" (8 rows) vs QLT blocks 1–8 |
| Data-processing sweep | `01-audit-backend.md` × `07-audit-data-processing.md` | legacy "### 4. Data Processing Correctness" (Deterministic Processing, Full Recalculation, Resource Safety, Transactional Integrity) vs DP dimensions 1–3 |
| Transactional integrity | `01-audit-backend.md` × `03-audit-db-concurrency.md` | legacy "Transactional Integrity" row vs DB-CON blocks 2, 3, 7 |
| API contract both sides | `01-audit-backend.md` Step R5 × `02-audit-frontend.md` Step R6 × `90-audit-integration.md` Step R1 | three copies of route↔client comparison; modern owner is `09-audit-external-api.md` blocks 9–11 |
| Transactional safety / pool config | `03-audit-database.md` × `03-audit-db-concurrency.md` × `13-audit-performance.md` | legacy "### 4. Transactional Safety" + "Connection pooling configured appropriately" vs DB-CON 2/6/9 and PERF 11 |
| Migration chain vs model drift | `03-audit-database.md` × `10-audit-code-quality.md` | legacy "### 1. Migration Integrity" vs QLT block 9 ("whether a gate fails when one is missing") — QLT owns the gate, legacy owns the chain; partially complementary |
| Authentication invariants | `04-audit-security.md` × `04-audit-auth-login.md` | legacy "### 1. Authentication Invariants" (token validation, expiry, constant-time compare) vs AUT blocks 2, 3, 5 |
| Authorization / IDOR / refusal shape | `04-audit-security.md` × `15-audit-authorization.md` | legacy "### 2. Authorization Invariants" + "Existence vs access distinction (404 vs 403)" vs AUTZ blocks 4, 5, 10 |
| CSRF and origin/cookie policy | `04-audit-security.md` × `02-audit-config-secrets.md` × `15-audit-authorization.md` | legacy "### 7. Security Headers & CORS"; the modern pair declares the split explicitly (CFG block 5 policy half, AUTZ block 11 enforcement half) |
| Credential and secret material | `04-audit-security.md` × `02-audit-config-secrets.md` × `12-audit-production-ops.md` | legacy "### 3. Credential & Secret Management" vs CFG blocks 3–4 and OPS block 1 |
| Container posture, reproducibility, resilience, deploy safety | `05-audit-docker.md` × `12-audit-production-ops.md` | all six legacy dimensions map 1:1 onto OPS blocks 1–12 (see §6) |
| Docker environment bring-up as a precondition | all 9 M files × `audit-multi-phase.md` | legacy `Step R0 — Ensure Docker Environment is Running` duplicates orchestration the orchestrator already owns |
| Test anti-patterns, coverage, isolation | `06-audit-tests.md` × `11-audit-test-coverage.md` | legacy dimensions 1–4 vs TST blocks 1, 2, 4, 6, 7 |
| Test database isolation | `03-audit-database.md` "### 6. Test Isolation" × `06-audit-tests.md` "### 3. Test Isolation" × `11-audit-test-coverage.md` block 4 | three copies; modern owner is TST block 4 |
| Configuration management and fail-fast | `08-audit-deployment-config.md` × `02-audit-config-secrets.md` | legacy "### 1. Configuration Management" + "### 3. Production Readiness" vs CFG blocks 1, 3, 7, 8 |
| Startup and shutdown lifecycle | `08-audit-deployment-config.md` × `01-audit-entry-architecture.md` × `12-audit-production-ops.md` | legacy "### 2. Startup Lifecycle" vs ENT blocks 1–3, 6 and OPS blocks 5–7 |
| Pipeline transaction boundary | `07-audit-data-processing.md` Step R3 × `03-audit-db-concurrency.md` block 2 | DP R3 ("Identify all database write operations in the pipeline… single transaction") vs DB-CON block 2 |
| Inbound surface form and validation boundaries | `90-audit-integration.md` Steps R1/R4 × `09-audit-external-api.md` blocks 9, 10 × `10-audit-code-quality.md` block 3 | three copies; modern split is EXT 9/10 (inbound integration boundary) vs QLT 3 (production-code boundary) |
| "A control that reports clean and examines nothing" | `11` block 7, `12` block 3, `13` block 2, `14` block 9, `99` block 2 | five near-verbatim instantiations of one angle, differing only in the domain noun |
| Multi-resource / cross-resource side effects | `01-audit-entry-architecture.md` block 7 × `03-audit-db-concurrency.md` block 10 × `07-audit-media.md` block 11 | three framings of the same question, none deferring to the others (see §2.6) |
| Cache-key ownership | `08-audit-search-fts.md` block 10 × `13-audit-performance.md` block 4 × `14-audit-i18n.md` block 6 | a deliberate three-way split, declared identically in all three — the set's one model of a clean shared boundary |
| Publish-gate propagation vs predicate agreement | `05-audit-ad-lifecycle.md` block 4 × `08-audit-search-fts.md` block 1 × `15-audit-authorization.md` block 9 | AD owns propagation to readers, SRH owns predicate agreement, AUTZ owns owner/public; declared in both AD and SRH |

Deliberate, non-overlapping adjacencies worth keeping as they are: `04`×`15` (identity binding vs per-request gate, negotiated in both files), `10`×`11` (production-code convention vs test-layer self-description), `03`×`13` (lock semantics vs measured consequence), `06`×`09` (identity data vs credentials in telemetry).

### 1.4 Coverage gaps the classification exposes

These are not file-level verdicts; they are the reason three "obsolete" files must be refined rather than dropped.

1. **Client tier has no modern owner.** `02-audit-frontend.md` is the only phase covering component architecture, client state, client-side type safety, rendering and accessibility. Nothing in the 16 B/V files does. The React SPA is ~15 of the repository's top-level surface.
2. **Ingestion and aggregation pipeline has no modern owner.** `src/mkobi/data/{loaders,processing,storage}` (Polars) is covered only by `07-audit-data-processing.md`. No B/V file owns upload admission, parse/transform/aggregate determinism, temp-file lifetime, or full-recalculation-after-re-upload.
3. **Global schema/migration/index integrity has no modern owner.** `03-audit-db-concurrency.md` owns concurrency; `10-audit-code-quality.md` block 9 owns *whether a drift gate runs*; neither owns the migration chain's linearity, `downgrade` reversibility, migration idempotency, or the index inventory against query predicates.

---

## 2. The anatomy of a well-written phase

Derived from the 15 B files plus `99-audit-validate.md`. Every point below is instantiated at least three times in that set.

### 2.1 Frontmatter fields actually used

| Field | Values in use | Meaningful or noise |
|---|---|---|
| `name` | `01-entry-architecture` … `99-validate`; legacy used `01-backend`, `02-frontend` | **Meaningful** — the phase's identity; the orchestrator (`audit-multi-phase.md` 2.1) derives the output directory from the *filename*, not from this, which is a live divergence (§3 FM12) |
| `executor` | `auditor` in 15 files, `validator` in `99` | **Meaningful** — the only field that changes what the agent does |
| `problems-only` | `true` in all 25 | **Meaningful** — the reporting contract |
| `status` | `draft` in all 16 B/V files | **Noise** — a constant; nothing reads it |
| `validated` | `no` in 15 files, `yes` in `04-audit-auth-login.md` | **Noise** — 15/16 identical, the single exception has no reader anywhere in the framework |
| `description` | legacy only, 9 files | **Noise for B/V** — the Purpose section already carries it, in prose the auditor reads |
| `agent` | legacy only, `auditor` | **Superseded** by `executor` |
| `alwaysApply` | legacy only, `false` | **Noise** — CLI-invoked phase specs, never auto-applied |

Recommendation: `name`, `executor`, `problems-only` are load-bearing. `status` and `validated` are placeholders for a lifecycle the orchestrator does not implement (`audit-multi-phase.md` has no status branch; `audit-refine.md` reads only `.ai/audit/99-validation`).

### 2.2 Section skeleton and what each section is for

```
# Phase NN — <Zone in Nouns>
## Purpose            — the zone, the angle, and the ownership contract
## Audit Blocks       — the executable work
### N. <Question as title>
*<obligation>*
Evidence: <artefact to produce>
## Severity Taxonomy  — how to grade what the blocks produce
## Report Output      — where it lands, under which prefix, under which contract
```

- **`## Purpose`** — two jobs. First, name the audit zone in nouns the auditor will recognise in the codebase ("entry surfaces", "process topology", "the cross-process serialisation registry"). Second, carry the ownership contract: what this phase owns, what it defers, and to which phase number. It ends with the standing instruction that names are the auditor's to discover — 01-entry-architecture states it most sharply: *"Concrete artifacts — services, files, modules, commands, identifiers, values — are discovered by the executing auditor, never named here."* Ten of sixteen files repeat this sentence in some form.
- **`## Audit Blocks`** — one angle per block, numbered, each self-contained. The preamble states the independence contract once: *"Each block is independent — execute any one with no knowledge of the others."*
- **`## Severity Taxonomy`** — a single rubric, keyed to **effect and blast radius** and anchored to **present state**, never to mechanism. Every B/V file opens it with the identical sentence *"Grade by **effect and blast radius**, not by mechanism name; rate what is true now, not the worst consequence if triggered."* and closes it with *"An empty band is a valid outcome — do not populate it with a hypothetical."* (12 files; `15` and `99` add "and do not promote an item for sounding alarming").
- **`## Report Output`** — findings path, template, finding-ID prefix, incremental-append rule, the problems-only restatement, and the exact empty-state string.

No B/V file has an `## Audit Scope` section, a `## Discovery Stage`, a `## Mandatory Runtime Verification`, or a `## Output Mode` section. That is the structural signature of the family.

### 2.3 How blocks are formulated

A block has four parts: a title, an obligation, a chain of sub-questions, and an evidence line. Five devices make it executable in isolation:

1. **The title names the subject and the question, never the mechanism.** `### 4. The gate's inputs, policy and decision record`; `### 6. Cross-process shared state and Side-Effect Coordination`; `### 7. A control that runs, reports clean, and examines nothing`. A reader who has never seen the repository can tell what will be examined. Compare the legacy alternative, a check-table row: `| Cascade/SET NULL behavior is intentional | No accidental data loss on delete. |` — that is a conclusion, not a task.
2. **The obligation opens with a state-of-the-world verb, not an action.** `*Establish…*`, `*Enumerate…*`, `*Derive, do not assume…*`, `*Inventory…*`, `*Treat…as a claim to test, not a precondition.*`, `*Ask both directions explicitly…*`. Nothing says which tool, which file, or which order.
3. **The sub-questions are chained with "and establish / and compare / confirm or refute / ask whether"** so that each is separately answerable and the auditor can split the block across helpers without losing the thread. `03-audit-db-concurrency.md` block 5 is a clean instance: *"Establish every operation that reads state, decides, then writes or deletes, and every row value maintained away from the write changing its input. Does the mutation re-assert the predicate the selection used…?"*
4. **Hypothesis-shaped prose tells the auditor what a finding looks like without telling it what to run.** The recurring constructions are:
   - *"a X that is not Y is a finding"* — 05-ad-lifecycle: *"a state no committed row ever holds, while features branch on it, is a finding"*;
   - *"treat Z as a finding candidate until its persistence is demonstrated"* — 01-entry-architecture block 7;
   - *"a passing check is methodology, never a finding"* (block preamble, all 16);
   - *"pick no winner"* where sources conflict — 06-pii-consent block 1, 08-search-fts block 2;
   - *"Do not presuppose the enumeration is complete"* — 15-authorization block 4.
5. **In-block deferrals.** Where a block touches another zone it says so in one clause rather than expanding: 07-media block 7 *"Locking and repeat-run safety are another phase's."*; 05-ad-lifecycle block 10 *"Constant discipline in general is another phase's — this is reachability and statement-truth in this domain only."*; 11-test-coverage block 7 *"the population of diagnostics in production code and its sanctioned suppressions is another phase's."*

Two smaller devices worth keeping: the **bidirectional ask** ("Ask both directions explicitly: what it refuses, and — the one that is easy to miss — whether it authorises anything it should not.", 07-media block 5) and the **derived-count insistence** ("derive the site count rather than assuming it", 07-media block 2; "Derive, do not assume: inventory every column…", 06-pii-consent block 3). Both exist to stop the auditor from accepting a plausible-looking enumeration.

### 2.4 The `Evidence:` line

One line per block, always the last line of the block, always starting with the literal `Evidence:`. Verified complete in all 16 B/V files: 9/9, 8/8, 10/10, 8/8, 10/10, 11/11, 11/11, 13/13, 12/12, 9/9, 8/8, 12/12, 11/11, 11/11, 11/11, 10/10.

The convention is **artefact, not command**. The line names what must exist in the report when the block is done:

- inventory + verdict set — `Evidence: the consumer inventory with the definition each consults; one row two consumers treat differently.` (08-search-fts block 1)
- inventory + a reproduced counter-example — `Evidence: the key inventory with encoded and omitted components; the token's lifetime against the data's; one key two concurrent readers resolve differently.` (13-performance block 4)
- matrix + the one-sided cells — `Evidence: the boundary × model inventory with an inherits / does-not-inherit verdict…` (09-external-api block 10)
- observed outcome, not inferred — `Evidence: one induced mid-write failure, all-or-nothing or not.` (03-db-concurrency block 2)

Three rules are applied consistently and are what make the line useful:
1. **At least one item must be reproduced or measured, not merely enumerated.** Every block's line contains an `one …` clause naming an observation the auditor must actually produce.
2. **Enumeration alone is insufficient when the finding is an absence.** Blocks whose target is a missing thing invert the requirement: `Evidence: the fixed-value inventory with its named home or its absence…` (10-code-quality block 1); `Evidence: the declared-machinery inventory with a reached/un-reached verdict…` (05-ad-lifecycle block 10); `Evidence: the gate inventory — which drift checks exist, where they run, and what they cover…` (10-code-quality block 9).
3. **Unverifiable-in-environment is named as residual, not omitted.** `Where no live external service can be reached, establish each control from a constructed payload … and record what that evidence does not cover.` (07-media block 2); `Where no counter exists, a quiet dependency is indistinguishable from a working one.` (09-external-api block 12). 11-test-coverage states it once for the whole file: *"an unreachable suite is a limit on the report, never a finding."*

The legacy family has **zero** `Evidence:` lines. It has 41 occurrences of `**Evidence required:**`, one per *dimension*, and those are pointers into the phase's own procedure — `**Evidence required:** Step R1 output for chain integrity. Step R2 comparison for drift detection.` (03-audit-database, dimension 1); `Step R6 (API contract alignment) feeds the mismatch check.` (02-audit-frontend, dimension 5); `**Evidence required:** Step R4 results. Step R6 analysis.` (06-audit-tests, dimension 3). Legacy evidence therefore cannot be evaluated without executing the mandated step list.

### 2.5 The problems-only reporting contract

The B/V set states the contract three times, each time preventing a different failure:

| Placement | Text (representative) | Failure it prevents |
|---|---|---|
| Block preamble | *"A passing check is methodology, never a finding, and any sound evidence is admissible — nothing here gates a finding on this phase's own checks."* | The auditor filing "verified" rows, and the phase's own checklist becoming an admission criterion |
| Severity Taxonomy | *"An empty band is a valid outcome — do not populate it with a hypothetical, and do not promote an item for sounding alarming."* | Severity inflation and hypotheticals promoted to fill the CRITICAL band |
| Report Output | *"`problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`"* | Empty and non-empty reports being indistinguishable |

The **exact empty-state string** is a set-wide constant: `No problems found in this phase.` appears in all 16 B/V files and in all 9 M files. It is the one convention shared by the whole corpus and should be protected.

Two further rules in the same section, both traceable: *"Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence* (01-entry-architecture, 12-production-ops); and *"If a shipped test asserts the current behaviour as intended, still file the finding and record the test as a remediation blocker"* (02-config-secrets, 03-db-concurrency, 06-pii-consent, 07-media, 08-search-fts, 09-external-api, 10-code-quality, 11-test-coverage).

### 2.6 Cross-phase boundary declaration and internal consistency

**Declaration.** All 16 B/V files carry one; all 9 M files carry none (verified: zero matches for any boundary phrasing in the M family). The mechanism is a `Scope Boundaries` paragraph inside `## Purpose`, with three levels of precision in use:

- **Zone deferral** — `Other phases own: entry/bootstrap process (01), connection pooling and runtime DB concurrency (03), authentication (04), … test-suite quality and coverage (11), TLS and certificate lifecycle and health probes (12).` (02-config-secrets)
- **Split ownership of one question** — `Which origins and which cookie attributes are honoured, per environment, is the policy half and is this phase's; which surfaces a request-forgery check reaches, and whether it runs on each, is the enforcement half and belongs to 15.` (02-config-secrets block 5, restated verbatim in 15-authorization block 11 and referenced from 04-auth-login's Purpose)
- **In-block deferral** — `Serialisation granularity, pooler sizing and latency are 03's and 13's.` (09-external-api block 5)

`12-audit-production-ops.md` adds a fourth, useful form: an explicit **transfer log** — *"taken in: the health, liveness and readiness endpoint and probe contract (from 01), and the edge tier, transport security and certificate lifecycle (from 09, 02)"* — which is how a phase that absorbs zones from now-deleted files records it.

**Consistency.** The set is largely self-consistent and unusually careful:

- The three-way cache-key split is declared **identically** in `08` (block 10), `13` (block 4) and `14` (Purpose, plus block 6). Three files, one paragraph, no drift.
- The 04/15 auth split is negotiated in **both** directions: 04 says *"With 15: this phase owns identity resolution and binding … 15 owning the per-request gate, and neither phase files the same middleware decision"*; 15 says *"identity resolution and binding, and the session-layer consequences, this phase owning the per-request gate, and neither phase filing the same middleware decision (04)"*.
- Publish-gate propagation vs predicate agreement is declared in both `05` (block 4) and `08` (block 1).
- `10` and `11` both exclude each other's territory explicitly (`10` block 4: *"Production code only … a diagnostic in a test file is not this phase's finding"*; `11` block 8: *"production-code convention and dead code are another phase's"*).

Two inconsistencies remain:

1. **Cross-resource side effects are claimed three times with no mutual deferral.** `01-audit-entry-architecture.md` block 7 ("everything the processes coordinate through: the shared database, the media filesystem, the shared cache … which multi-resource side effects can interleave"), `03-audit-db-concurrency.md` block 10 ("effects that span more than one resource — a row and a file it names, a row and a cached value … which resource is the real unit of atomicity"), and `07-audit-media.md` block 11 ("which long-lived processes read and mutate the shared store, and per operation whether it is mutually excluded"). None of the three names the others. A single multi-writer race will be filed three times or zero times depending on which block the auditor reaches first.
2. **The "control that examines nothing" angle is instantiated five times** — `11` block 7, `12` block 3, `13` block 2, `14` block 9, `99` block 2 — opening with near-identical sentences (*"separate three questions per control: does it exist, what scope does it declare, what did it actually examine"*). This is defensible (each owns the controls of its own domain) but is currently maintained as five independent copies of one paragraph rather than one angle referenced five times, so it will drift.

### 2.7 One block, written both ways

The single most useful thing a later writer can take from this set. Same zone, same auditor, both formulations:

**Not acceptable** — family M, `01-audit-backend.md`, `### 3. Access Control & Security` (one of eight rows):

```
| Audit Trail | Security-relevant events (login, permission changes, data access) are logged for forensic analysis. |
```

Why it fails: it names a property, not a task. The auditor cannot tell what to enumerate, cannot tell which events count as "security-relevant", and cannot tell whether "logged" means emitted or queryable. It is also un-evidenced — the dimension's `**Evidence required:**` line sends the auditor to `Step R1` output, which is about credential leaks.

**Acceptable** — family B, `15-audit-authorization.md`, `### 3. The privileged surfaces, and the predicate each one evaluates`:

> *Enumerate every surface reachable only by an elevated identity, in either process: the framework's own administrative interface, the per-model overrides inside it, a privileged path that hands off to a second gate, and any surface listed as privileged only in intent. Establish which of them are reachable over a request at all — a one-shot task has no caller to authorise, and a surface every identity may reach is not privileged merely by being listed. Record where each decision sits.*
> **Evidence:** surface inventory with the predicate each evaluates, against what admits a caller; a decision reached after the first irreversible step it guards; two gates on one request path.

Why it works: the title states the question; the obligation opens with an enumeration verb; the enumeration names *kinds* (never artefacts) and includes the counter-case ("listed as privileged only in intent") that the auditor would otherwise skip; the middle sentence supplies the judgement rule that turns an inventory into findings; the evidence line names three artefacts, one of which is a defect to be reproduced rather than counted. It contains no file path, no command, and no dependency on any other block.

---

## 3. Failure modes present in the current set

Each anti-pattern below was observed in at least one named file and block. Nothing here is hypothesised.

### FM1 — The phase dictates a runtime procedure and gates its content on it

Nine files open with `## Mandatory Runtime Verification` and the sentence *"Before evaluating any checklist item, you MUST complete these steps."* The phase then declares its own acceptance gate: a finding is admissible only after steps R0…Rn have run. This converts a zone prompt into a fixed procedure, and it breaks in three ways. It freezes the *order* of verification into the prompt, so a code change that makes step R3 impossible silently invalidates every dimension that cites it. It duplicates orchestration that `audit-multi-phase.md` already owns (Step 0 selects phases, 2.1 computes the output path, 2.3 verifies the output exists). And it makes the phase's dimensions non-independent in the strongest sense: they are defined as functions of the procedure.
Examples: `05-audit-docker.md` `### Step R1 — Build All Container Images` … `### Step R8 — Graceful Shutdown Behavior` (eight mandated steps); `06-audit-tests.md` `### Step R1 — Run the Full Test Suite` … `### Step R6 — Verify Test Database Isolation`; `01-audit-backend.md` `### Step R0` … `### Step R5 — Verify API Contract Matches Source`.
The B/V family's replacement is one sentence per file: 12-production-ops, *"Where a property cannot be settled in the environment at hand — standing up a separate stack to restore into end to end, or inducing a dependency failure to probe an endpoint — establish it from what is observable and state plainly what could not be verified and why."*

### FM2 — Hardcoded documentation path used as an instruction

Six files tell the auditor to follow a literal path: `01-audit-backend.md:40`, `02-audit-frontend.md:40`, `03-audit-database.md:40`, `06-audit-tests.md:41`, `08-audit-deployment-config.md:40`, `90-audit-integration.md:40` — all *"Follow the setup instructions in `docs/11-guides/docker.md`."* The path exists today, which is exactly the problem: the prompt will keep pointing at it after it moves, and the failure is silent (the auditor cannot tell a stale instruction from a missing file). The B/V family replaces it with *"Use the commands provided in the project's commands file"* — no, that is the M family's phrasing too; the B/V family says nothing at all about commands and instead says *"Skip a runtime check only when the environment makes it genuinely impossible, and record why."*

### FM3 — Toolchain assumptions presented as universal truths

The M family states framework-specific facts as the audit's expectations, so a project that differs produces false findings. Verified against this repository, several are wrong:
- `02-audit-frontend.md` `### Step R2 — TypeScript Compilation Check`: *"Check `tsconfig.json`: verify `strict: true` and other strict flags."* and dimension 1 rows *"No hardcoded URLs or endpoints in components | All endpoints should come from a shared API client module."*
- `02-audit-frontend.md` dimension 4: `| Tokens stored securely | Not in localStorage (XSS-vulnerable). |` — this project's client holds no JWT; `04-audit-auth-login.md` describes a bot-minted deep-link credential. The row audits a component that does not exist.
- `04-audit-security.md` `### Step R2`: *"verify signing algorithm is NOT `none` or weak"*; dimension 6: `| Passwords hashed with secure algorithm | bcrypt, scrypt, or argon2. |`
- `03-audit-database.md` `### Step R1`: *"Run the migration tool's history, current, and check commands"* — a named tool interface.
- `01-audit-backend.md` `### Step R5`: *"Compare declared routes against the OpenAPI/Swagger spec (if auto-generated)"*.
The B/V family strips the tool and keeps the property: `10-audit-code-quality.md` block 4 — *"Never assume a strictness bar the project did not set, and never treat a non-zero diagnostic count as the finding."*

### FM4 — Blocks that are not independent

The M family's dimensions are not executable alone, because their evidence requirement is a reference into the phase's own step list: `03-audit-database.md` `**Evidence required:** Step R1 output for chain integrity. Step R2 comparison for drift detection.`; `02-audit-frontend.md` `**Evidence required:** Reference specific file:line. Use build/lint/test output from Steps R1-R4 as supporting evidence. Dead code from Step R5 feeds this section.`; `06-audit-tests.md` `**Evidence required:** Step R3 results for tautological tests. Step R4 for isolation issues.`; `90-audit-integration.md` `**Evidence required:** Step R1 route-by-route comparison.` This directly contradicts the framework's own requirement in `audit-phase-refine.md` §1.3 — *"Each block remains an independent task that a separate auditor can execute."*

### FM5 — Blocks too broad to be actionable or split

An M dimension bundles 6–8 unrelated questions into one pass. `01-audit-backend.md` `### 3. Access Control & Security` covers eight rows spanning secret management, password hashing, injection, secure defaults, audit trail, environment parity and privilege separation — four separate modern blocks' worth of work behind one table. `03-audit-database.md` `### 5. Scalability Invariants` bundles archival strategy, table growth, full-scan risk, query efficiency, batch operations and connection pooling. Such a block cannot be delegated, cannot be split across helpers, and produces one undifferentiated pass.

### FM6 — Duplicated coverage across files

Fifteen declared overlaps, tabulated in §1.3. The sharpest cases: `05-audit-docker.md`'s six dimensions map 1:1 onto `12-audit-production-ops.md` blocks 1–12; `01-audit-backend.md`'s five dimensions map onto ENT + DB-CON + DP + QLT; `90-audit-integration.md`'s six steps map onto 02 + 04 + 09 + 15. Consequence: the same root cause is filed by two phases under two prefixes, and `99-audit-validate.md` block 6 then spends a block adjudicating a merge that should never have been contested.

### FM7 — Check rows that cannot fail

In a problems-only report a row whose text is an affirmative is dead weight at best and a false finding at worst. `90-audit-integration.md` dimension 4: `| No schema drift detected | Everything is aligned. |`. `05-audit-docker.md` dimension 1: `| Configuration files version-controlled | No manual config drift. |`. `03-audit-database.md` dimension 2: `| No missing indexes on large tables | Query analysis shows no full table scans. |` — unmeasurable as written.

### FM8 — No cross-phase boundary declaration

All nine M files declare zero boundaries. `04-audit-security.md` files authorization findings while `15-audit-authorization.md` owns the same zone, with no deferral protocol in either, so `99` must arbitrate. `03-audit-database.md` and `03-audit-db-concurrency.md` are the same phase number for a reason nobody documented.

### FM9 — Instruction bloat and corrupted English

The same 6-bullet `## Output Mode` block, the same 4-item `## Discovery Stage`, and the same `**problems-only: true** rules:**` block appear verbatim in nine files (verified: 9 occurrences each). The Output Mode block includes a counterfactual paragraph — *"If `problems-only: false` were set, you would produce a full report with compliance statements"* — that describes a document the phase forbids producing. A six-line sentence with two typographical errors and a grammar break is duplicated into six files: `01-audit-backend.md:20`, `04-audit-security.md:20`, `05-audit-docker.md:20`, `06-audit-tests.md:20`, `08-audit-deployment-config.md:20`, `90-audit-integration.md:20` — *"If you need to start or stop docker environment to check functional or run test you should run it following the documantation instruction in dev mode BUT you mast return it to the same status as before - running or stopped"*. This violates the project's own English-only rule and, worse, encodes an operational instruction in a phase file.

### FM10 — Residual framework identity inside the "architecture-agnostic" files

The B/V family removed file paths but kept framework nouns, so a FastAPI + React codebase is described in Django vocabulary. Verified instances: `01-audit-entry-architecture.md` Purpose *"a synchronous WSGI web tier"* and block 2 *"the WSGI serving module … management-command dispatch"*; `05-audit-ad-lifecycle.md` block 1 *"declarative admin surfaces"* and block 4 *"the index maintained at the database layer"*; `15-audit-authorization.md` block 3 *"the framework's own administrative interface, the per-model overrides inside it"*; `06-audit-pii-consent.md` block 1 *"the query and template filters deciding visibility"*; `14-audit-i18n.md` block 8 *"the extraction → catalog → compiled-catalog chain"*. None of these exist in `src/mkobi/` (no `manage.py`, no `admin.py`, no `templates/`). This is the most important forward-looking finding in this report: the stability goal is half-achieved, because names of *tools* were removed while names of *framework constructs* were kept.

### FM11 — Mechanism-keyed severity with no rubric

The M family scatters CRITICAL/HIGH labels inside prose, keyed to mechanism rather than effect: `05-audit-docker.md` *"A build failure is CRITICAL — the app cannot be deployed"* and *"Any error in the log is a finding"*; `02-audit-frontend.md` *"A build failure is CRITICAL — the frontend does not work"*; `06-audit-tests.md` *"If the test suite cannot run at all (import errors, config errors), that is CRITICAL."* A build failure or a log line is not a CRITICAL band by effect and blast radius; these labels will be reproduced verbatim in every report the phase produces. The B/V family replaces nine scattered labels with one rubric opened by *"Grade by effect and blast radius … rate what is true now, not the worst consequence if triggered."*

### FM12 — Naming, path and numbering drift between a phase and the orchestrator

`audit-multi-phase.md` §2.1 computes `OUTPUT_PATH = .ai/audit/{PHASE_NUMBER}-{PHASE_NAME}/findings.md` from the **filename**. Three files disagree with that:
- `05-audit-docker.md` frontmatter `name: 05-docker`, but Report Output says `.ai/audit/05-infrastructure/findings.md` — neither the filename nor the frontmatter.
- `90-audit-integration.md` frontmatter `name: 09-integration` — so phase 09 is claimed by two files (`09-audit-external-api.md`, `name: 09-external-api`, and `90-audit-integration.md`), and the orchestrator's 09 filter can select either.
- `01-audit-backend.md` writes to `.ai/audit/01-backend/findings.md` while `01-audit-entry-architecture.md` writes to `.ai/audit/01-entry-architecture/findings.md` — two outputs for one phase number, one of them for a file that should not exist.

### FM13 — A shared artefact every phase depends on does not exist

All 25 phases name the template `.ai/audit/templates/audit-findings.md`. That file is not in the repository: `.ai/audit/` contains only `99-validation/` and `validated/`, and the historical template lived at `.kilo/commands/audit/templates/` (added in commit `3d85860`, since removed). Every B/V Report Output section therefore instructs the auditor to follow a template that is not there. This is not a phase-file style problem, but it is the single highest-leverage defect in the framework and it is invisible in the phase set.

### FM14 — Report Output rules stated as three different shapes

Three mutually inconsistent Report Output shapes coexist: M files use prose (`Write findings to: … using template …`); `02-config-secrets.md` and `04-audit-auth-login.md` use a mixed bullet list with prose paragraphs inside bullets; the other 14 B/V files use a flat bullet list with the findings path, template, prefix, incremental-append, problems-only and empty-state on six fixed bullets. `audit-multi-phase.md` supplies a seventh rule set (retry policy, output verification). A later writer has no single form to imitate.

---

## 4. Best practices distilled

Each item is traceable to files that already do it.

1. **One angle per block, named as a question.** `## Audit Blocks` → `### N. <subject> and <what is asked>` — 07-media block 5, 12-production-ops block 3, 13-performance block 2. Never a category ("Security"), never a mechanism ("Check N+1 queries").
2. **Open every block with `*Establish…*` / `*Enumerate…*` / `*Derive…*` and never with a command.** 03-db-concurrency blocks 1–10; 05-ad-lifecycle blocks 1–10.
3. **Chain sub-questions with "and establish / and compare / confirm or refute / ask whether",** so a block can be split across helpers and each answer is separately admissible. 04-auth-login block 5; 10-code-quality block 3.
4. **State what a finding looks like as a hypothesis, not as a check.** "a X that is not Y is a finding"; "treat Z as a candidate until its persistence is demonstrated"; "A passing check is methodology, never a finding." 01-entry-architecture block 7 and every block preamble; 12-production-ops block 3.
5. **Give every block exactly one `Evidence:` line naming an artefact, and require at least one reproduced observation in it.** 100 % coverage in all 16 B/V files; `one row two consumers treat differently` (08 block 1), `one induced mid-write failure` (03 block 2).
6. **When the block's target is an absence, the evidence line names the absence.** "with its named home **or its absence**" (10 block 1), "with a reached/un-reached verdict" (05 block 10), "whether it is loaded, whether it is green" (11 block 7).
7. **Never name a file, module, directory, command, port, environment variable or identifier in a phase.** 01-entry-architecture Purpose states the rule; every B/V file observes it. Where a concrete noun seems unavoidable, name the *kind* — "the test schema", "the trust anchor", "a freshness/version token" — not the artefact.
8. **Declare cross-phase ownership in `## Purpose`, in one paragraph, naming the owning phase by number, and split ownership where a single question is genuinely shared.** 04 × 15 (identity vs per-request gate), 02 × 15 (cookie/origin policy vs CSRF enforcement), 08 × 13 × 14 (cached result set vs key composition vs language component).
9. **Restate the deferral inside any block that strays, in one clause.** "Locking mechanics are another's." (07 block 7); "Constant discipline in general is another phase's" (05 block 10).
10. **Keep one rubric, opened by the effect-and-blast-radius sentence and closed by the empty-band sentence.** 12 of 16 files use the bullet form (`- **CRITICAL** — …`); prefer it over the 3-file table form, which wraps badly for the long conditions the modern set writes.
11. **State the problems-only contract in exactly three places** — block preamble, severity rubric, Report Output — and nowhere else. This replaces nine files' worth of boilerplate with three sentences.
12. **Reserve the exact empty-state string `No problems found in this phase.`** It is the only convention shared by all 25 files; protect it.
13. **Say how to handle an unverifiable property once per file, and require the residual to be recorded.** "establish it from what is observable and state plainly what could not be verified and why" (12, 13, 15); per-block variants in 07 blocks 2/3/6/11 and 09 blocks 1/4.
14. **Forbid the phase's own checklist from gating a finding, and forbid promoting hypotheticals.** "nothing here gates a finding on this phase's own checks" (all 16); "An empty band is a valid outcome — do not populate it with a hypothetical" (12 files).
15. **Standardise the six-bullet Report Output.** findings path · template · finding-ID prefix · incremental append · problems-only · empty state. Take it from 12-production-ops or 13-performance, not from the M family.
16. **Keep the block count where it is (8–13) and the file length where it is (117–140 lines).** Every B/V file sits in that band; every M file exceeds it (168–212 lines) while covering strictly less.
17. **Migrate in place, keep the filename, fix the frontmatter.** 99-audit-validate.md is the precedent: same file, same path, rewritten from Step/Workflow structure to Purpose/Blocks/Rubric/Report Output, with its `executor` flipped to `validator`.
18. **When a zone is absorbed, record the transfer in the receiving phase.** 12-production-ops's *"taken in: … (from 01) … (from 09, 02)"* is the model; it is what makes a deletion of 05-audit-docker.md safe.
19. **Keep the Purpose to one paragraph plus the boundary paragraph.** Every B/V Purpose is 3–6 sentences: what the zone is, what the angle is, who owns what. `10-audit-code-quality.md` and `01-audit-entry-architecture.md` are the longest and still fit one screen. A Purpose that grows into a Discovery Stage is the first symptom of regression to family M.
20. **Write each severity band as effect classes, not as mechanisms.** *"a transaction that is neither all-or-nothing nor usable after a tolerated error"* (03), *"the suite's green is affirmatively false today"* (11), *"a reader acts on a value that is wrong for their language and cannot tell"* (14). A mechanism belongs in a block, never in a band.
21. **Never reintroduce an `## Output Mode`, `## Discovery Stage`, `## Mandatory Runtime Verification` or `## Audit Scope` section.** Those four sections are the entire difference between the two families; a reviewer seeing one of them in a new phase should reject the file without reading further.
22. **Keep every finding-ID prefix unique across the set and assert it in one place.** The B/V set already has three prefixes flagged as colliding with identifiers minted into shipped source by earlier cycles (`QLT-`, `TST-`, `OPS-`, `PERF-`, `I18N-`); `99-audit-validate.md` block 7 exists to rule on that. Any new phase must check the prefix list before adopting one.

---

## 5. Vocabulary and tone conventions

### 5.1 How a zone is named

Zones are named in **system nouns, plural, and never after a file**. The recurring nouns, as used:

- **process/topology** — entry surface, process topology, long-lived, one-shot, conditionally-enabled, boot requirement, grace period, drain, recycle, arbiter, dispatch chain, serialisation granularity, per-update lifecycle
- **data/state** — shared state, cross-resource effect, unit of atomicity, dangling reference, orphan, residue, intermediate state, derived value, denormalised copy, read-modify-write, selection predicate
- **decision/gate** — access decision, eligibility predicate, visibility predicate, publish gate, guard, the enforcement half, the policy half, decision record
- **contract** — declared contract, documented rule, statement to test, control, claim to test, enforced point, named home
- **verification posture** — effective state after merge, declared scope vs actual scope, enabled in the deployed configuration, residual unverified, limit on the report

**Forbidden in a zone name**: a filename, a directory, a class, a command, a port, a container name, an env-var name, a table name. `docker-compose.yml`, `admin.py`, `wsgi.py`, `tsconfig.json` are all absent from the B/V set.

### 5.2 How obligations are phrased

The verb set is small and stable. Use these, and nothing else, as the opening word of a block or a sub-question:

| Verb | Meaning in this corpus | Example |
|---|---|---|
| **Establish** | bring the state of the world into the report; the default opener | *"Establish, per environment/deployment tier, which components are long-lived…"* |
| **Enumerate** | produce the list, completeness not presumed | *"Enumerate every entry surface — process bootstraps, the WSGI serving module…"* |
| **Inventory** | produce the list as a countable artefact | *"Inventory every destination outside this system that receives personal data."* |
| **Derive** | compute it rather than read it off a declaration | *"Derive, do not assume: inventory every column, table, file, and derived value…"* |
| **Trace** | follow it end to end | *"Trace every path from a request-supplied string to the query."* |
| **Compare** | two sites against each other, never one against a rule | *"Compare the two processes' eligibility predicates over the same subject — by the flags consulted and the identity resolved, not by name."* |
| **Confirm or refute** | a stated claim is the object | *"Confirm or refute that a state claimed as terminal is terminal on every path."* |
| **Measure** | only where a number is expected | *"Measure drain/stop latency and exit code against the orchestrator's termination grace period."* |
| **Record** | the output obligation | *"Record what a supervisor observes when a dependency is unavailable…"* |
| **Judge / separate / classify** | an analytic act over an already-produced set | *"Judge the credential as an unguessable bearer value, not a bit count."* |

Phrasings to imitate verbatim, because they encode the method without prescribing it:
- *"Treat single-source-of-truth as a claim to test, not a precondition."* (08 block 1)
- *"Do not presuppose the enumeration is complete: a path that resolves an object without consulting its caller is a path, not an exception to the rule."* (15 block 4)
- *"Grade by effect and blast radius, not by mechanism name; rate what is true now, not the worst consequence if triggered."* (all 16)
- *"Evidence is a class, not a check list: observed output, a reproduced behaviour, or a static proof that a stated property does not hold; the method is the auditor's."* (01 block preamble)
- *"Pick no winner."* / *"Record which source is authoritative when two disagree, without picking a winner in the report."* (06 block 1, 07 block 10)

Phrasings to avoid: *"Verify that X"* as a whole block (it names no object), *"Check that…"* (the M family's verb, and the reason its rows are unfalsifiable), *"Ensure that…"*, *"Make sure…"*.

### 5.3 Formatting conventions

- **Headings**: exactly four `##` sections in a fixed order — Purpose, Audit Blocks, Severity Taxonomy, Report Output. Blocks are `### N. <Title Case, no trailing period>`; no `####` anywhere; no deeper nesting.
- **Block body**: wrapped in a single `*…*` italic span, hard-wrapped at roughly 130–170 columns. 14 of 16 files do this. Two exceptions: `01-audit-entry-architecture.md` writes plain text and breaks **one sentence per line**; `99-audit-validate.md` writes plain text, width-wrapped. Pick one and standardise — the majority (italic, width-wrapped) is the safer default because the italic span is what visually separates obligation from evidence.
- **Evidence line**: literal `Evidence: ` at the start of the last line of the block, semicolon-separated fragments, at least one of which begins `one …` and names a reproduced observation. Never a file path, never a command, never "N/A".
- **Severity Taxonomy**: `- **CRITICAL** — …` bullets, blank line after the rubric sentence, four bands in fixed order, each band a semicolon-separated list of *effect classes*, never of mechanisms. The 3-file table form (`| Severity | Conditions |`) should be retired: the modern conditions are 30–60 words each and do not fit a table cell.
- **Scope Boundaries**: bolded run-in label (`**Scope Boundaries** — …` or `Scope boundary — …`), placed inside `## Purpose` as its last paragraph, always in the order *owned here → deferred, with phase numbers*.
- **Line length feel**: ~110–170 columns in block bodies, ~100 in Purpose, short one-liners in Report Output. A phase that reads as a wall of 80-column text is in the M family's style.
- **Tone**: declarative, no second person, no imperative mood aimed at the reader except the block openers. No emoji, no headers in prose, no exclamation. "You" appears nowhere in the B/V set; "you MUST" appears in all nine M files.
- **Language**: English only, including the reserved strings `Evidence:` and `No problems found in this phase.`

---

## 6. Obsolete / removal candidates

Conservative. A file is listed only where its unique coverage is empty, or is fully distributed across named owners, or is a strict subset of a named owner. Each entry names the residual explicitly so the owner can decide to fold it before deleting.

### 6.1 `05-audit-docker.md` — delete, superseded by `12-audit-production-ops.md`

| Legacy dimension | Modern owner |
|---|---|
| 1. Reproducibility (pinned base images, pinned deps, no manual deploy steps) | 12 block 2 ("base images and their versions, tools fetched during the build … whether it is pinned") |
| 2. Secrets Management (compose secrets, `_FILE`, prod fail-fast) | 12 block 1 (runtime posture after merge) + 02 blocks 3, 4 |
| 3. Isolation (dev/prod separate, test DB separate, port exposure, no shared code volumes) | 12 block 1 + 11 block 4 |
| 4. Resilience (health checks, restart policy, graceful shutdown, stale-file cleanup) | 12 block 7 + 01 block 3 ("drain/stop latency and exit code against the orchestrator's termination grace period") |
| 5. Container Security (`USER`, minimal images, multi-stage) | 12 block 1 |
| 6. Deployment Safety (debug off, log level, migration strategy, rollback) | 12 blocks 5, 6, 12 |
| Steps R1–R8 (build, start, logs, health, connectivity, ports, secret injection, shutdown) | 12 blocks 1, 3, 7 |

Residual: none beyond image-size/build-time nits, which 12 block 2 covers as part of artifact provenance. The file also self-contradicts on its output path (`name: 05-docker` vs `.ai/audit/05-infrastructure/findings.md`) — FM12.

### 6.2 `90-audit-integration.md` — delete, no unique coverage

| Legacy step / dimension | Modern owner |
|---|---|
| R1 + dim 1 route contract both sides | 09 blocks 9, 10, 11 |
| R2 + dim 2 auth flow both sides | 04 (all 8 blocks) + 15 blocks 7, 8 |
| R3 + dim 3 end-to-end data flow | 03 blocks 2, 5 + the retained pipeline phase |
| R4 + dim 4 schema alignment | residual folded into the refined `03-audit-database.md` |
| R5 + dim 5 env consistency | 02 blocks 2, 6 |
| R6 + dim 5 error propagation | 09 block 9 + 15 block 10 |
| Step R0 Docker bring-up | orchestrator + 12 blocks 1, 6 |

Every dimension maps. It also claims phase number 09 (`name: 09-integration`) while `09-audit-external-api.md` holds 09 — FM12. Delete.

### 6.3 `08-audit-deployment-config.md` — delete after one clause is folded into `10-audit-code-quality.md`

| Legacy dimension | Modern owner |
|---|---|
| 1. Configuration Management | 02 blocks 1, 3, 8 |
| 2. Startup Lifecycle | 01 blocks 1, 2, 3, 6 |
| 3. Production Readiness | 12 blocks 1, 5 + 02 block 7 |
| Steps R1–R4, R6 | 02 blocks 1, 3, 6 + 01 block 1 |
| 4. Overengineering Check | **residual** |

Residual: the complexity-budget angle — *"Is the abstraction level appropriate for the project size? Are there unnecessary layers? Do the chosen libraries/services have clear justification?"* This has no modern owner: `10` block 5 owns multiplicity *inside one unit* and explicitly excludes configuration abstraction depth. Fold it into `10-audit-code-quality.md` as one block (a natural sibling of block 5), then delete the file.

### 6.4 `06-audit-tests.md` — delete after one clause is folded into `11-audit-test-coverage.md` block 7

| Legacy dimension | Modern owner |
|---|---|
| 1. Test Anti-Patterns (mock tree, tautological, order dependence) | 11 blocks 1, 2, 6 |
| 2. Critical Path Coverage | 11 block 1 + block 7 |
| 3. Test Isolation | 11 blocks 4, 5, 6 |
| Steps R1–R6 | 11 blocks 5, 6, 7 |
| 4. Type Safety in Tests | **residual** |

Residual: one row — the population of type diagnostics *inside the test tree* and their sanctioned suppressions. `11` block 7 owns only "whether the test tree is inside that gate's scope and whether the gate is currently red"; `10` block 4 explicitly excludes test files (*"a diagnostic in a test file is not this phase's finding"*). So one clause is genuinely unowned. Add it to `11` block 7, then delete the file.

### 6.5 `01-audit-backend.md` — delete, superseded by four files

| Legacy dimension / step | Modern owner |
|---|---|
| 1. Architectural Integrity | 01 blocks 8, 9 |
| 2. API Contract Safety (input validation, error handling, auth enforcement, authz granularity, rate limiting, idempotency) | 10 block 3 + 09 blocks 9–11 + 15 blocks 3–7 + 04 block 8 |
| 3. Access Control & Security | 02 blocks 3, 4 + 04 blocks 1–3 + 15 |
| 4. Data Processing Correctness | 03 blocks 2, 7 + retained pipeline phase |
| 5. Code Quality & Maintainability | 10 blocks 1, 4, 5, 6, 7 |
| Steps R0, R1 | 12 blocks 1, 3 + 10 block 4 + 11 block 7 |
| Step R2 import verification | 01 block 2 |
| Step R3 + R3-SPEC dead code | 10 block 7 |
| Step R4 run tests | 11 |
| Step R5 API contract | 09 blocks 9, 10 |

Unique coverage: empty. This file is the union of four modern phases plus an orchestrator pre-flight. Delete.

### 6.6 Refine, do not delete — `04-audit-security.md`

Despite heavy overlap (§1.3), two blocks have no modern owner: (a) **credential-at-rest policy** — hashing algorithm, cost factor, plaintext never logged or serialised, minimum length, re-auth on change — which `04-audit-auth-login.md` block 2 covers only for the handshake bearer token; and (b) **generic request bounding** on surfaces other than login (`04` block 8), public search (`08` block 7) and outbound calls (`09` block 4). Shrink the file to those two blocks in the modern style and renumber; discard dimensions 1, 2, 3, 4, 5, 7.

### 6.7 Refine in place — the three files that own unclaimed zones

- **`02-audit-frontend.md`** — the sole owner of the client tier (§1.4 gap 1). Rewrite in the modern style: drop `tsconfig.json`, "shared API client module", and the localStorage row (all false premises for this project, FM3), and replace the six dimension tables with 8–11 independent blocks over component boundaries, server-state ownership, form validation, request lifecycle, credential handling as it actually exists, error and empty states, rendering of partial or missing data, client-side type safety, and accessibility. Renumber above 15.
- **`03-audit-database.md`** — shrink from six dimensions to the three residuals: migration-chain linearity and reversibility, the index inventory against real query predicates, and referential-integrity parity (ORM relationship ↔ DB constraint, cascade behaviour). The transactional-safety, pooling and test-isolation dimensions are fully owned by `03-audit-db-concurrency.md`, `13-audit-performance.md` and `11-audit-test-coverage.md`. Renumber.
- **`07-audit-data-processing.md`** — the sole owner of the ingestion/aggregation pipeline (§1.4 gap 2), and the pipeline is a first-class subsystem here (`src/mkobi/data/{loaders,processing,storage}`). Keep dimensions 1–3 as blocks; move the transactional-boundary material into `03-audit-db-concurrency.md`'s vocabulary and cross-reference it rather than restating it (they currently duplicate). Renumber above 15.

### 6.8 Not a phase file, but blocking every phase

`.ai/audit/templates/audit-findings.md` — referenced by all 25 phases, absent from the repository (FM13). Every phase's Report Output is currently unfollowable. Fixing this is a precondition for any refactor of the set, and `99-audit-validate.md` block 8 already audits it as a controlled artefact — meaning the framework expects the template to exist and does not notice that it does not.

### 6.9 Resulting set, if every recommendation above is applied

| # | Phase file | Action | Covers |
|---|---|---|---|
| 01 | `01-audit-entry-architecture.md` | keep | entry surfaces, topology, boot/stop, schema gate, shared state, route wiring |
| 02 | `02-audit-config-secrets.md` | keep | settings variants, env-var contract, secret guards, environment parity |
| 03 | `03-audit-db-concurrency.md` | keep | transactions, locks, run safety, schema-mutation windows |
| 04 | `04-audit-auth-login.md` | keep | the login handshake end to end |
| 05 | `05-audit-ad-lifecycle.md` | keep | ad lifecycle, clocks, publish gate, cleanup family |
| 06 | `06-audit-pii-consent.md` | keep | consent, erasure, egress basis |
| 07 | `07-audit-media.md` | keep | media ingestion, serving, reconciliation |
| 08 | `08-audit-search-fts.md` | keep | search predicate, index, per-language documents, cached sets |
| 09 | `09-audit-external-api.md` | keep | outbound integrations and the inbound surface |
| 10 | `10-audit-code-quality.md` | keep + **add** the complexity-budget block from `08-audit-deployment-config.md` | convention vs enforcement |
| 11 | `11-audit-test-coverage.md` | keep + **amend** block 7 with test-tree diagnostics from `06-audit-tests.md` | would the suite notice |
| 12 | `12-audit-production-ops.md` | keep | deployed system, gates, deploy/revert, observability, runbooks |
| 13 | `13-audit-performance.md` | keep | measurable cost and ceilings |
| 14 | `14-audit-i18n.md` | keep | language, locale, format, catalogues |
| 15 | `15-audit-authorization.md` | keep | what an access decision returns |
| 16 | *(from `02-audit-frontend.md`)* | **refine** | client tier |
| 17 | *(from `07-audit-data-processing.md`)* | **refine** | ingestion and aggregation pipeline |
| 18 | *(from `03-audit-database.md`)* | **refine** | migration chain, index inventory, referential integrity |
| 19 | *(from `04-audit-security.md`)* | **refine** | credential-at-rest policy; generic request bounding |
| 99 | `99-audit-validate.md` | keep | adjudication of findings |

Deleted: `01-audit-backend.md`, `05-audit-docker.md`, `06-audit-tests.md`, `08-audit-deployment-config.md`, `90-audit-integration.md` — 25 files become 20, all in the B family, with the three §1.4 gaps closed rather than widened. The set's remaining internal inconsistencies to close at the same time are the un-deferred cross-resource claim (§2.6 item 1, `01` b7 × `03` b10 × `07` b11) and the five copied control-scope paragraphs (§2.6 item 2).

---

## Appendix A — Evidence index

| Claim | How verified |
|---|---|
| 9 files carry `## Discovery Stage`, `## Mandatory Runtime Verification`, `## Audit Scope` | grep over `.kilo/commands/audit/phases/*.md`, count 9 each |
| 16 files carry `## Audit Blocks` and `## Severity Taxonomy` | same grep, count 16 each; sets are disjoint |
| `## Output Mode` boilerplate and the "problems-only: false" counterfactual | `Select-String 'If `problems-only: false` were set'` → 9 |
| `Evidence:` lines | one per block in all 16 B/V files (9/9, 8/8, 10/10, 8/8, 10/10, 11/11, 11/11, 13/13, 12/12, 9/9, 8/8, 12/12, 11/11, 11/11, 11/11, 10/10); 0 in all 9 M files |
| `**Evidence required:**` | 41 occurrences across the 9 M files, one per dimension, all cross-referencing R-steps |
| `docs/11-guides/docker.md` hardcoded | `01:40, 02:40, 03:40, 06:41, 08:40, 90:40` |
| "documantation … you mast return" duplicated | `01:20, 04:20, 05:20, 06:20, 08:20, 90:20` |
| No scope boundaries in the M family | boundary-phrase grep → 0 matches in all 9; ≥1 in all 16 |
| Severity rendered as a table in 3 files, bullets in 13 | `^\| Severity \| Conditions \|` → 02-config-secrets, 04-auth-login, 06-pii-consent |
| Block bodies in italics | block count == italic-opener count in 14 of 16; `01-audit-entry-architecture.md` and `99-audit-validate.md` use plain paragraphs |
| 15 modern files untracked | `git status --porcelain` lists all 15 as `??`; `git ls-files` lists only the 9 M files and `99` |
| 99 migrated in place | `git show HEAD:.kilo/commands/audit/phases/99-audit-validate.md` headings = `Step 0 … Output Mode … Discovery Stage … Workflow … Step 5`; working tree = Purpose/Blocks/Rubric/Report Output |
| Django vocabulary does not match the code | `src/mkobi/main.py` docstring "Main FastAPI application file"; no `manage.py`; no `templates/` directory under `src/mkobi` |
| Compose files are under `docker/`, not the root | directory listing |
| Template absent | `.ai/audit/` contains only `99-validation/` and `validated/`; `.kilo/commands/audit/templates/` no longer exists |
