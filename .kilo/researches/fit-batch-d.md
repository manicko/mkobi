# Fit Analysis — Batch D (phases 13, 14, 15, 99)

Domain-fit review of four phase files against the **verified** shape of this repository (FastAPI +
SQLAlchemy 2.0 + asyncpg + Pydantic v2, PostgreSQL, Polars, RQ + Redis, Alembic, React 19 + Vite + MUI +
TanStack Query + RHF + Zod SPA). Binding references: `phase-set-conventions-analysis.md` (FM1–FM14, §2
anatomy, §4/§5 conventions) and `llm-audit-task-spec-design.md` §2–§7 (B1–B14, D1–D11, C1–C9, RC1–RC7,
AP1–AP19). Nothing in `phases/` was modified.

## 0. Set-wide facts that decide all four rewrites

1. **The renumbering is half-applied.** Filenames are new (`01-audit-process-architecture.md`), but `name:`
   and the findings path are old (`name: 01-entry-architecture`, `.ai/audit/01-entry-architecture/`).
   Verified across all 16 files: 12/16 have `name` ≠ filename stem, and every modern file's findings
   directory equals its `name`, not its stem. FM12/C5 at set scale, not four local defects. *Ruling for this
   batch:* `name` **is** the filename stem; path is `.ai/audit/{stem}/findings.md`. My three legacy files
   become the only three satisfying R12; the other twelve stay non-conformant, and that is a finding for
   `08`/`99` — not something to paper over by matching them. State the rule in each file so a later run
   does not harmonise it back.
2. **Declared prefixes today:** `ENT-` 01, `CFG-` 02, `DB-` 03, `AUT-` 04, `DP-` 05, `MED-` 06, `EXT-` 07,
   `QLT-` 08, `TST-` 09, `OPS-` 10, `PERF-` 11, `AUTZ-` 12, `VAL-` 99. `FE-`, `MIG-`, `SEC-` are free.
   **The sibling claim that `QLT-`/`TST-`/`OPS-`/`PERF-` are "already in use in shipped source" is not
   reproducible** — those strings occur only in the phase files and the analysis report; report it as stale
   and do not design around it. A real near-collision already exists: `AUT-` is a literal prefix of `AUTZ-`,
   and `MED-` now means "file artifacts", not media — exactly what `99` block 7 exists to rule on.
3. **`.ai/audit/templates/audit-findings.md` exists** (72 lines) — FM13 is fixed. Its real contract: front
   matter `phase / executed / executor / problems-only / findings / by-severity`; sections `Summary /
   Findings / Distribution / Cross-Finding Analysis / Roadmap / Rollout Safety / Appendices`; per finding
   exactly six fields — **Severity, Zone, Observation, Evidence, Consequence, Recommendation** — with `Zone`
   quoted verbatim from the block title and the reserved empty string terminating `Summary`. It contains **no
   prefix list, no verification table, no rubric pointer and no `Type` field**; three of `99`'s blocks assume
   otherwise. `.ai/audit/99-validation/` does **not** exist (`.ai/audit/` holds only `templates/`), so the
   validator creates it and its Report Output must say so.
4. **The three legacy files carry no `Scope Boundaries` paragraph at all** (FM8). The stale references they
   do carry: a hardcoded doc path (`docs/11-guides/docker.md`, `13:40`, `14:40`), toolchain assertions
   (`tsconfig.json` strictness `13:55`/`13:168`; "bcrypt, scrypt, or argon2" `15:179`), their own
   `Step R1…R6` numbering, and **implicit** zone claims belonging to now-deleted phases: upload admission
   (was 07-media → **06**), search/full-text index rows (was 08-search-fts → **deleted**; fold into 14 + 11),
   language/locale rows (was 14-i18n → **deleted**; drop). The paragraph must be *authored* and those claims
   repointed.

---

# 1. `13-audit-client-tier.md` — client tier

## 1.1 Current state

Legacy whole-frontend sweep: six check-table dimensions (component architecture, state, rendering, client
security, type safety, accessibility) gated behind seven mandated steps. **Blocks: 6 dimensions + 7 steps +
R5-CROSSCHECK; 202 lines; family M.** `name: 02-frontend` vs stem `13-audit-client-tier` — inconsistent on
both axes, and the path it writes (`.ai/audit/02-frontend/findings.md`) is now phase 02's directory.

## 1.2 Premise audit — per block

| # | Block | Verdict | Offending noun → replacement |
|---|---|---|---|
| S1–S2 | Steps R0 Docker, R1 build | **ADAPTABLE, then drop** | *"Follow the setup instructions in `docs/11-guides/docker.md`"* (FM2/AP2) — delete per Ex. 4, the real concern being 10's. The build is real but *"A build failure is CRITICAL"* is AP11; survives only inside new block 5. |
| S3 | Step R2 `tsc` | **ADAPTABLE** | *"Check `tsconfig.json`: verify `strict: true`"*, *"Count `any` types"* — AP3/B14; a flag is not a property. → new block 10. |
| S4–S5 | Steps R3 lint, R4 tests | **DUPLICATE → 08 / 09** | *"If no linter is configured, that is itself a finding"* is 08 b7 / 09 b7; frontend test execution is 09's harness. Remove both. |
| S6 | Step R5 dead code | **DUPLICATE → 08** | 08 b7 owns dead definitions. Keep only the client-surface residue → new block 11; the CROSSCHECK rule (documented ⇒ not dead) survives. |
| S7 | Step R6 route parity | **DUPLICATE → 07** | Server-side inbound surface is 07 b9–b10; the client half is new blocks 3 and 5. |
| D1 | Component architecture | **ADAPTABLE** | *"No hardcoded URLs or endpoints in components"* is verified violated: the base path is written in `shared/api/axiosInstance.ts:9` **and** again in `shared/components/ErrorBoundary.tsx:40` (raw `fetch`). *"shared API client module"* is a technology noun (B14). → new block 1. |
| D2 | State consistency | **ADAPTABLE** | *"managed through query library"* names the library (AP3). Real content: which server value a cache owns, what retires it, what the user sees after a mutation. → new block 2. |
| D3 | Rendering correctness | **TRUE** | Chart layer exists (`features/dashboards/ui/charts/`, Plotly). *"Config-driven rendering"* is a claim to test, not a row. → new block 7. |
| D4 | Client security | **ADAPTABLE — the important one** | *"Tokens stored securely \| Not in localStorage (XSS-vulnerable)"* **cannot fail**: no `localStorage` reference exists anywhere in `frontend/src` (verified). The real mechanism is `features/auth/model/authToken.ts:74` — store selected by `import.meta.env.PROD` (memory vs `sessionStorage`). → new blocks 4, 5. |
| D5 | Type safety | **ADAPTABLE** | *"Zod/Yup schemas cover all form fields"* names products. Real content: hand-declared response types against a contract nothing checks, plus rule divergence the user experiences. → new blocks 8, 10. |
| D6 | Accessibility | **TRUE** | MUI supplies most semantics, so the honest block is what *this code* adds and overrides. → new block 9. |
| — | — | **FALSE PREMISE, dropped** | No localisation layer, no declarative admin surface, no per-locale client behaviour. Any row implying those is noise. |

## 1.3 Proposed final block set (11)

1. **Slice boundaries: what crosses from shared code into a feature, and back** — *Enumerate* the client's import edges by kind (request plumbing, credential state, feature internals, presentation); for each, which direction the declared layering permits. Shared plumbing reaching into a feature's credential state is a finding, and so is a feature reaching another's internals instead of its published surface. *One-rule-one-home* and dead code defer to 08.
   `Evidence: the edge inventory with an in-permitted / out-of-permitted verdict per edge; one shared module importing feature internals.`
2. **Server-derived values: which component owns each one, and what retires it** — *Derive* the inventory of values the server owns; for each, the cache holding it, the identity of its key, and the mutation that must invalidate it. A mutation leaving a value the user still sees is a finding, as is a value held in both a cache and component state. Key *composition* and hit cost are 11's.
   `Evidence: the value inventory with owner, key shape and invalidating mutation; one mutation with no invalidation; one value owned twice.`
3. **The request path: one path or several, and what each refusal leaves behind** — *Establish* every place a call leaves the client and what it carries: shared client, direct transport, telemetry side channel. Record where target prefix, credential attachment and failure handling are decided once versus restated. A path bypassing shared failure handling, or duplicating a value it also owns, is a finding.
   `Evidence: the request-path inventory with, per path, where target and credential are set; one path bypassing shared failure handling; one duplicated endpoint prefix.`
4. **Session continuity: what the client believes after a full page load** — *Establish* where the caller's credential lives in a shipped build, what survives a hard reload, and what the client decides when the in-page credential is absent but the server session is not. Ask the reverse: what a claim the client itself parses decides — expiry, role — and what an absent or skew-affected claim causes. A boot that discards a valid session is a finding. *Deployed-build provenance* is 10's; *whether a browser-reachable store is acceptable for this credential* is 15 b1's.
   `Evidence: the credential-state inventory with what each event leaves behind; one full reload reproduced with its outcome; one claim the client acts on that the server never confirms.`
5. **The client's declared build-time contract against what the shipped bundle resolves** — `NEW` — *Inventory* every value the client declares it requires at build time and, for each, the consumers found. A declared requirement with no consumer is a finding, and so is a value the request path resolves that no declaration names. (Verified case: `VITE_API_URL` is declared required in production and validated at boot in `main.tsx:7`, yet `shared/config/env.ts:5` has no reader.)
   `Evidence: the declared list with, per entry, the consumers found or none; one entry with no consumer; one resolved value no declaration names.`
6. **Failure surfacing: what the user is shown, per class, and where one class is shown twice** — *Derive* the classes of failure the client can receive; for each, the message path, the surface it reaches, and whether it is reported inline, as a transient notice, or both. A class with no message branch is a finding, as is a failure that both renders an error and leaves a previous result on screen, or that fires two notifications for one occurrence. Message-table duplication is 08's; the *outcome* is here.
   `Evidence: the failure-class inventory with the surface each reaches; one class with no message branch; one class reported on two surfaces for one occurrence.`
7. **Absent, partial and malformed server data** — *Establish*, per surface rendering server data, what it renders for an empty result, an absent optional field, an out-of-type value, and a failed fetch following a successful one. An empty frame indistinguishable from "no data", a throw, and a stale frame left beside a fresh error are findings.
   `Evidence: the surface × state matrix with the rendered outcome per cell; one cell that throws; one empty state indistinguishable from a populated one.`
8. **Form rules: what the client enforces against what the server enforces** — *Compare* the client's declared input rules with the server's field by field, both directions. A field the client accepts and the server refuses, or the reverse, is a finding, as is a client rule existing only to shape the message. Boundary-validation *coverage* is 08's; the client's own rule set is here.
   `Evidence: the field × rule comparison with a matches / diverges verdict; one field accepted in the client and refused by the server.`
9. **Interactive surface semantics: what an assistive technology is told** — *Enumerate* the interactive surfaces the code composes rather than inherits, and for each its accessible name, label association, focus behaviour across a route change, and how a dynamic error is announced. A pointer-only surface, an unannounced input error, and a dialog that does not restore focus are findings.
   `Evidence: the interactive-surface inventory with the name, role and focus path each exposes or lacks; one surface with no accessible name; one focus path that ends nowhere.`
10. **Type width at the client boundary: what crosses as unverified** — *Establish* how each response shape reaches the client (declared by hand, derived, asserted at the call site) and record the suppression and cast sites at that boundary. A boundary where declared and served shapes can differ with nothing that would notice is a finding. The general type gate is 08's.
    `Evidence: the boundary inventory with, per boundary, how the shape is declared and what a mismatch would cost; one boundary with no declared shape.`
11. **Reachability of the client's own declared surfaces** — *Enumerate* every route, lazily loaded chunk, feature module and feature-local message table, and for each the path that reaches it. Do not presuppose the enumeration is complete. A surface with no reaching path, or reachable only by typing a location, is a finding — and where the specification corpus names it, a missing integration, not dead code.
    `Evidence: the surface inventory with a reached / unreached verdict per entry; one unreached surface the specification expects.`

**REMOVED:** all seven Steps as blocks; the localStorage row; "no linter configured is a finding"; the
strictness and "Zod/Yup" rows; the `docs/11-guides/docker.md` instruction; the duplicated `Output Mode`
counterfactual (`13:19`).

## 1.4 Scope Boundaries (exact paragraph, new numbering)

> **Scope Boundaries** — this phase owns the browser-resident application tier: its module layering, the
> values it holds and who retires them, the path a request leaves by, the caller's session as the client
> understands it, the build-time contract the client declares, what the user is shown for each failure
> class, how absent server data renders, the client's own input rules against the server's, the semantics of
> the interactive surfaces the code adds, type width at the network boundary, and the reachability of the
> client's declared surfaces. Other phases own: process topology, entry surfaces and the start-up schema
> gate (01); settings values, secrets and environment policy, including any artefact's build-time
> configuration contract (02); transactions and constraint recovery (03); credential issuance, delivery,
> claim guards and account resolution (04); ingestion and aggregation (05); upload admission, temporary-file
> lifetime and file serving (06); inbound surface form, body bounds, refusal disclosure and retry contracts
> (07); fixed-value homes, one-rule-one-home, boundary-validation coverage, the type gate and dead
> definitions in both tiers (08); test-suite adequacy on this side of the boundary (09); deployment
> provenance, container posture and the edge tier (10); cache-key composition, hit cost and measurable
> latency (11); the access decision a privileged client surface reflects, object-level ownership and
> request-forgery enforcement (12); schema evolution and the index inventory (14); credential storage
> policy, request-rate bounding coverage and failure-response disclosure (15); namespace rulings and
> cross-phase conflict resolution (99). A mechanism another phase owns is recorded as a deferral with its
> owner named, and this phase still covers the client-visible consequence of it.

## 1.5 Finding-ID prefix

**`FE-`** — 2 letters; grep-verified absent from `src`, `frontend/src`, `tests`, `alembic`, `docs` and `.ai`
(no `FE-\d` match anywhere); not among the 13 declared prefixes; continues this phase's own historical
prefix, giving `99` b7 a continuity ruling to make rather than a fresh namespace to invent.

```markdown
## Report Output

- Findings path: `.ai/audit/13-audit-client-tier/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `FE-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
```

---

# 2. `14-audit-schema-migrations.md` — schema and migrations

## 2.1 Current state

Legacy database sweep: migration integrity, indexing, consistency guarantees, transactional safety,
scalability, test isolation, behind seven mandated steps. **Blocks: 6 dimensions + 7 steps; 194 lines;
family M.** `name: 03-database` vs stem `14-audit-schema-migrations` — inconsistent, **and its prefix `DB-`
collides head-on with `03-audit-db-concurrency.md`'s `DB-`** (AP12: two namespaces, one identifier space).

## 2.2 Premise audit — per block

| # | Block | Verdict | Offending noun → replacement |
|---|---|---|---|
| S1 | Step R0 Docker | **REMOVE** | FM1/FM2; the environment question survives only inside new block 8. |
| S2 | Step R1 chain | **TRUE** | 8 revisions, one head — real work, no procedure. *"Branches are CRITICAL"* is AP11. → new blocks 1, 2, 9. |
| S3 | Step R2 model drift | **ADAPTABLE — the core insight** | *"Run the migration tool's … `check` commands"* names a tool (B14). The real property: this repository's **entire initial schema is hand-written `op.execute` SQL** (`alembic/versions/000000000000_initial_migration.py:22-343`), so the model layer and the chain are two independent declarations and the tool's own diffing cannot see the chain's half. → new block 3. |
| S4 | Step R3 index stats | **ADAPTABLE** | *"query for index usage statistics"* and *"unused indexes … each is a finding"* are methods, and false — no statistics collector is guaranteed enabled. Sharpest instance: `aggregated_data` carries a GIN index on the structured column with the **default operator class** (`src/mkobi/db/models/aggregated_data.py:53`) while the read path issues caller-supplied key predicates (`src/mkobi/api/routes/data.py:54,105-115`). → new block 6. |
| S5 | Step R4 constraints | **TRUE, partly DUPLICATE** | *"Missing FK constraints"* overlaps 03 b4. Keep only the declaration-parity half → new block 7. |
| S6, S7 | Steps R5 transactions, R6 test isolation | **DUPLICATE → 03, 09** | 03 b2/b3/b7 and 09 b4 own these wholesale. Remove; say so in the boundary paragraph. |
| D1 | Migration integrity | **TRUE** | The chain holds a revision whose forward *and* reverse are both `pass` (`000000000001_add_missing_fk_indexes.py:21-28`) and a reverse that deliberately recreates an index a later step removed for cause (`f47ac18b5b9e:39-49`). → new blocks 2, 9. |
| D2 | Indexing strategy | **ADAPTABLE, one false premise** | *"Text search indexes where applicable"* is a **FALSE PREMISE** — no full-text retrieval exists. *"Every common filter has an index"* is unmeasurable. *"GIN indexes where JSONB fields are filtered"* is the one real row and is already satisfied — re-aim it at operator coverage. → new block 6. |
| D3 | Consistency guarantees | **TRUE** | No `CheckConstraint` exists anywhere in the model layer (verified across all 12 model files); referential actions mix CASCADE and SET NULL. → new blocks 5, 7. |
| D4–D6 | Transactional safety, scalability, test isolation | **DUPLICATE → 03, 11, 09** | *"Archival strategy for growing tables"* and *"Connection pooling configured appropriately"* — 11 b7/b10 and 03 b1; growth-bound consequence is 11's. Remove all three. |

## 2.3 Proposed final block set (9)

1. **The chain as a graph: heads, branches, and the order it declares** — *Derive* the revision graph from declared predecessors, not file order; record the head count, every revision whose declared predecessor is not the one naming it, and every revision nothing descends from. A second head, or a step nothing can follow, is a finding.
   `Evidence: the derived graph with its head count; one revision with no reachable successor.`
2. **Each step's reverse against its forward** — *Compare*, per revision, what the forward performs with what the reverse performs, and establish whether downgrading one step and re-upgrading reproduces the schema. A reverse that does nothing, cannot restore a removed value, or leaves behind what the forward created is a finding; so is one re-establishing what a later step removed deliberately.
   `Evidence: the per-revision forward/reverse pairs with an asymmetric verdict; one reverse that does not restore what its forward removed.`
3. **Two declarations of one schema: the model layer against the chain** — *Establish*, per table, column, key and constraint, which declaration states it and where the two disagree. Establish first whether the chain's steps were authored as statements or derived from the models, because a chain authored as statements cannot be diffed by any means the project owns. A column on one side and absent from the other is a finding in both directions.
   `Evidence: the per-object agreement matrix, its authoring method, one object declared on one side only; one declared pair that disagree.`
4. **Schema objects with no counterpart in the model layer** — *Inventory* the objects the chain owns that the model layer cannot express or does not declare: timestamp-maintenance triggers and their function, stored enumerated types, indexes defined over an expression rather than a column. For each, which step creates, alters and drops it, and what outside the chain can change it. An object no step drops, or one whose lifecycle lives in a comment, is a finding.
   `Evidence: the object inventory with a chain-owned / model-owned / unowned verdict; one object no step drops.`
5. **Enumerated-type parity between the process vocabulary and the stored vocabulary** — *Compare* the value set the application declares with the value set the storage engine enforces, both directions. A value the application can emit and the column cannot hold, and a value the column can hold that the application cannot name, are both findings — a step that has already had to remove a value is the pattern, not the exception.
   `Evidence: both value sets with their symmetric difference; one value reachable in one direction only.`
6. **The index inventory against the predicates the code actually issues** — *Derive* the predicate inventory from the queries the application issues, including predicates over structured document columns, then compare with the access paths the engine uses. Ask whether a declared access path can serve the operator actually issued, and whether a hot predicate has none. Measured cost is 11's; the inventory and its accuracy are here.
   `Evidence: the predicate-to-access-path map with the plan shape per predicate; one declared access path that cannot serve the operator issued; one hot predicate with none.`
7. **Referential actions and business keys: what each declaration states** — *Establish*, per relationship, the referential action in the model layer and the action the chain declares, and whether the constraint exists in both. Record what each declared action destroys on delete and what a row naming a missing parent becomes. A relationship constrained on one side only, or an action whose data loss is unstated, is a finding.
   `Evidence: the relationship inventory with action and constraint state per declaration; one relationship constrained on one side only; one delete path that orphans a live row.`
8. **Which environments obtain their schema from the chain, and which obtain it otherwise** — *Establish*, per environment the deployment offers, where its schema comes from: the chain, a pre-existing volume, a restored dump, an object altered outside the tool. A start-up path that mutates its own schema in one environment and not another is a finding, as is a role or grant established outside the chain. The process-level boot gate is 01's; the schema source is here. *(This makes the test schema a first-class case: the suite recreates and migrates it through the same path — 09 owns the suite.)*
   `Evidence: the environment-by-schema-source matrix with a reached / unreached verdict; one environment whose schema the chain does not describe.`
9. **The chain's own residue: steps and statements that assert nothing** — *Inventory* every step whose forward and reverse both perform nothing, every comment claiming a change the step does not make, and every object named in prose but never created. A step existing only to occupy a version is a finding; so is a comment that is the only record of a decision.
   `Evidence: the step inventory with an asserts-nothing verdict; one step whose stated purpose is not performed.`

**REMOVED:** Steps R0, R5, R6; dimensions 4, 5, 6 in full; the full-text index row; the "unused index is a
finding" row; the `DB-` prefix.

## 2.4 Scope Boundaries (exact paragraph)

> **Scope Boundaries** — this phase owns the declared schema state and how it evolves: the revision chain as
> a graph, each step against its own reverse, the model layer against the chain as two declarations of one
> schema, the schema objects no declaration owns, enumerated-type parity, the index inventory against the
> predicates the code issues, referential actions and business keys, which environment obtains its schema from
> the chain, and the residue the chain asserts and does not perform. Other phases own: process topology, entry
> surfaces and the start-up schema gate (01); settings values, secrets and environment policy (02); transaction
> boundaries, lock semantics, constraint recovery and connection-pool configuration (03); the pipeline's own
> writes and upload admission (05, 06); the query-cost consequence of a missing or unusable access path,
> unbounded scans and table growth (11); whether a drift gate exists, is loaded and would notice (08); the
> health contract that observes the schema (10); test-suite adequacy and the suite's own database isolation
> (09). No phase owns retrieval: this system has no full-text search, so recall, ranking and per-language
> document questions do not arise anywhere in the set. A mechanism another phase owns is recorded as a
> deferral with its owner named, and this phase still covers the schema-accuracy consequence of it.

## 2.5 Finding-ID prefix

**`MIG-`** — 3 letters; grep-verified absent from `src`, `frontend/src`, `tests`, `alembic`, `docs` and
`.ai`; not among the 13 declared prefixes; **replaces `DB-`, already owned by 03 and the one hard collision
this file carries.** Rejected: `SCH-` (reads as "schedule" in the runbooks 10 owns) and `DB-` (taken). `MIG-`
names the evolution responsibility rather than the tool, so it survives a tool swap.

```markdown
## Report Output

- Findings path: `.ai/audit/14-audit-schema-migrations/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `MIG-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
```

---

# 3. `15-audit-security-baseline.md` — security baseline

## 3.1 Current state

Legacy generic security sweep: authentication, authorization, secrets, input validation, rate limiting,
password security, headers and CORS, behind seven mandated steps. **Blocks: 7 dimensions + 7 steps; 212
lines** — the longest file in the set, covering the least that is unowned. Family M. `name: 04-security` vs
stem `15-audit-security-baseline` — inconsistent, and the path it writes is now phase 04's. Its `Output Mode`
also carries the corrupted shared sentence at `15:20` ("documantation … you mast return", FM9).

## 3.2 Premise audit — per block

| # | Block | Verdict | Offending noun → replacement |
|---|---|---|---|
| S1–S3 | Steps R1 leak, R2 token, R3 access control | **DUPLICATE → 02, 04, 12** | 02 b3/b4 own secret provenance; 04 b1–b3 own issuance, strength and claim guards; 12 b3–b5 own per-surface predicates and object ownership. Remove all three. |
| S4 | Step R4 password lifecycle | **TRUE, retained** | §6.6(a)'s named residual and the only unowned material here. The population is richer than the file assumes: the password record (`src/mkobi/core/security.py:7,37-38`) **and** a short-lived credential stored in plaintext with a 24-hour TTL, returned to a privileged caller (`src/mkobi/core/temp_password_store.py:20,30-49`; surfaced at `frontend/src/features/admin/api/adminApi.ts:71`). → new blocks 1, 2. |
| S5 | Step R5 attack surface | **SPLIT** | *"File upload: verify MIME type checking, file size limit, filename sanitisation"* → **06 b2/b3** (already implemented at `src/mkobi/api/routes/upload.py:129-141,164-196`). *"Search for raw SQL with string interpolation … any user input in SQL is CRITICAL"* → **07 b10**; and no raw interpolated SQL exists (zero `text(f` / `f"SELECT` matches), so the row cannot fail as written. The real instance is caller-supplied *structure*: `src/mkobi/api/routes/data.py:54,105-115` takes a raw JSON string parsed with `json.loads` and no schema. → new blocks 6, 7. |
| S6 | Step R6 rate limiting | **TRUE, widened** | Real, Redis-backed with a fail-closed flag (`src/mkobi/core/security.py:58-147`, `src/mkobi/config.py:366`), applied on login, refresh, register-request, upload and client-errors — and **not** on password change, dashboard reads or the aggregated-data read. → new block 4. Seam: what a request's *body* may contain is 07 b9. |
| S7, D7 | CORS and headers | **SPLIT** | CORS policy and startup fail-fast are **02** (already fail-fast: `src/mkobi/app.py:201-213`). Headers split across tiers and the file says so: the application sets four and delegates framing control to a proxy a development deployment does not run (`src/mkobi/app.py:48-82`, comment at `:51-52`). Edge tier and certificates → **10 b8**; request-forgery → **12 b11**. → new block 8. |
| D1, D2 | Authentication, authorization invariants | **DUPLICATE → 04, 12** | Including *"Existence vs access distinction (404 vs 403)"* → 12 b10. Remove. |
| D3 | Credential & secret management | **DUPLICATE → 02** | Including *"Production refuses defaults or test credentials"* — already implemented in validators (`src/mkobi/config.py:423-431,470-472`) and owned by 02 b3. Remove. |
| D4 | Input validation | **SPLIT** | → 07, 06, 08. The residual *"Error messages don't leak sensitive information"* becomes new block 7, scoped to **undecided failures**, since 12 b10 owns what a *refusal* discloses. Real instance: the unauthenticated detailed health endpoint returns component status and `str(e)` (`src/mkobi/app.py:278-316`). |
| D5, D6 | Rate limiting, password security | **TRUE** | → new blocks 4 and 1. *"bcrypt, scrypt, or argon2"* is AP3/B14; the real question is parameters, policy, comparison. |
| — | Severity | **FIX** | *"A hardcoded secret in production config is CRITICAL. A missing rate limit on login is CRITICAL."* — AP11/FM11, mechanism-keyed, and copied verbatim into every report this phase ever writes. Replace with the effect-keyed four-band rubric. |
| — | — | **FALSE PREMISE, dropped** | No multi-worker rate-limit store question (Redis is the shared store), no WSGI worker model, no declarative admin, no localisation. |

## 3.3 Proposed final block set (9)

1. **The stored password: encoding, parameters, and the policy around it** — *Establish* what the password record is at rest, with what work factor and maximum input length, how verification compares, what minimum the policy enforces, and whether changing a credential requires the current one. A record whose encoding reveals the input, a non-constant-time comparison, and a change needing no current value are findings. *Issuance, delivery and lifetime of the session credential* are 04's; this is the record that outlives it.
   `Evidence: the stored-credential inventory with encoding, work factor and comparison path; one record whose parameters or comparison are weaker than the policy claims.`
2. **Short-lived credentials handed to another person: the store, the lifetime, the retrieval** — `NEW` — *Establish* every place a credential is issued to someone who is not the account holder and then persisted: stored as what, for how long, what a read does to it, what a backing-store failure does. A stored credential readable more than once by design, or readable indefinitely, is a finding; so is a store that fails open on the write side.
   `Evidence: the delegated-credential inventory with encoding, lifetime and read semantics; one stored value readable more than once.`
3. **Credential material in everything else that persists** — *Trace* every credential-bearing value into the log sink, into any structure returned to a caller, and into the browser-telemetry path. A credential, a hash, or an unbounded caller-supplied string able to carry credential material into a log is a finding. *What an integration writes to logs* is 07 b12's; *operational observability* is 10 b11's.
   `Evidence: the value-to-sink trace; one credential-bearing value reaching a sink; one sink receiving an unbounded caller-supplied string.`
4. **Attempt-rate bounding: which surfaces have one, and what the counter's own failure means** — *Derive* the inventory of surfaces that admit a caller; for each, whether a bound exists, what it is keyed on (address, account, global), and whether the bound's backing store being unavailable admits or refuses. A surface drivable without limit, and a bound that silently admits on store failure, are both findings. Login-surface limiting is 04's; body bounds 07's; the store's semantics 03's.
   `Evidence: the surface × bound matrix with a bound / unbounded verdict; one surface with no bound; one bound whose store failure admits silently.`
5. **Unauthenticated inbound writes: the surfaces that accept a caller's structure with no session** — *Enumerate* every surface reachable with no authenticated identity, and for each what it accepts, what it writes, what bounds it, and what acceptance and refusal each say. A write of caller-supplied content into a durable log with no session and no content validation is a finding. The health endpoint's *contract* is 10's; *what it discloses* is this phase's.
   `Evidence: the unauthenticated-surface inventory with bound, written shape and disclosure; one surface writing caller content unauthenticated.`
6. **Untrusted structure that selects what is read** — *Establish* every payload whose *content* — not whose presence — chooses a stored expression, a column, a key or a handler, and for each whether the key set is constrained to a declared set before use. Caller-supplied JSON consumed as a key set against a structured document column is the pattern to establish; an unconstrained key reaching storage is a finding. *Whether a boundary validates at all* is 07's and 08's.
   `Evidence: the selection-payload inventory with the declared key set each is checked against, or its absence; one key reaching storage unconstrained.`
7. **Failure responses: what an undecided failure puts in the response** — *Establish* every path returning no access decision — an unhandled exception, a rejected dependency, a validation fault — and for each what the caller learns: internal text, a trace, a query shape, a filesystem path — and whether the same value reaches the log. A path returning internal detail, and a response whose shape differs by environment, are findings. *Refusals* are 12 b10's; *failures* are this block's.
   `Evidence: the failure-path inventory with the response shape each returns; one path returning internal detail; one response whose content differs by environment.`
8. **Response headers at the application, and what a deployment without the delegating tier emits** — *Inventory* the headers the application sets, the ones its own documentation assigns to another component, and the response classes — including error and asset responses — carrying none of them. A header asserted only in a comment is a finding, as is a response class leaving the application with no header it claims to set. Origin and cookie policy is 02's; edge tier and transport 10's.
   `Evidence: the header matrix per response class; one class carrying none; one header asserted only in documentation.`
9. **Controls in this zone that exist, load, and decide nothing** — *Apply the vacuous-control angle as defined in 99* to this zone: for each control, three questions — does it exist, what scope does it declare, what did it actually examine — and the fourth, whether running is not deciding. A startup warning skipped entirely in the environment that matters is the shape to test (`src/mkobi/config.py:591-596` returns early for production).
   `Evidence: the control inventory with existence, declared scope, items actually examined and the path a verdict would have taken; one control green over zero items.`

**REMOVED:** Steps R1, R2, R3, R5, R7; dimensions 1, 2, 3; the "bcrypt, scrypt, or argon2" row; the
mechanism-keyed severity paragraph; the corrupted `Output Mode` sentence; the duplicated counterfactual.

## 3.4 Scope Boundaries (exact paragraph)

> **Scope Boundaries** — this phase owns the cross-cutting security baseline no other phase answers: what
> each persisted credential is at rest and under what policy, what credential material reaches any other sink,
> which inbound surfaces are attempt-bounded and what the counter's own failure means, what an
> unauthenticated write path accepts, what untrusted structure is allowed to select, what an undecided
> failure discloses, which response headers the application actually emits, and whether the controls in this
> zone examined anything. Other phases own: process topology, entry surfaces and the start-up schema gate
> (01); settings values, secret provenance, environment parity, origin and cookie policy, and the production
> fail-fast validators (02); transaction boundaries and the cross-process serialisation registry (03);
> credential issuance, delivery, claim guards, lifetime and account resolution, and limiting on the login
> surfaces (04); upload admission, temporary-file lifetime and file serving (06); inbound surface form, body
> bounds, retry contracts and what integration telemetry carries (07); boundary-validation coverage,
> fixed-value homes and the type gate (08); the test harness and the suite's own isolation (09); container
> posture, the edge tier, transport security, certificates, probes and operational observability (10); the
> measurable cost of a bound (11); the access decision itself, object-level ownership, the privileged-surface
> inventory and request-forgery enforcement (12); the client-visible consequence of a policy decided here
> (13); schema evolution, referential actions and the index inventory (14); namespace rulings and cross-phase
> conflict resolution (99). A mechanism another phase owns is recorded as a deferral with its owner named,
> and this phase still records the security consequence of it.

## 3.5 Finding-ID prefix

**`SEC-`** — 3 letters; grep-verified absent from `src`, `frontend/src`, `tests`, `alembic`, `docs` and
`.ai`; not among the 13 declared prefixes; identical to this file's own historical prefix, so identifier
continuity across cycles is preserved and `99` b7 has a continuity ruling to make.

```markdown
## Report Output

- Findings path: `.ai/audit/15-audit-security-baseline/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `SEC-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence
- Empty state, exactly: `No problems found in this phase.`
```

---

# 4. `99-audit-validate.md` — validator

## 4.1 Current state

Adjudicates another auditor's findings and the audit tooling's own artefacts, producing a disposition
record. **Blocks: 10; 130 lines; family V.** `executor: validator` — **keep**. `name: 99-validate` vs stem
`99-audit-validate` — the set's one intentional deviation, but undeclared, so a later run "fixes" it and
breaks the output directory. This is the only file here already in the target style: its work is premise
repair plus one new block, not restructuring.

## 4.2 Premise audit — per block

| # | Block | Verdict | Note |
|---|---|---|---|
| Preamble, b9 | *"the input report's own verification table"* | **FALSE PREMISE** | The template has no verification section; two further copies at `:109` and in b9. Replace the noun with "the input's own evidence fields and its declared blocks" — the guard is sound, the artefact is not. |
| 1 | Claim re-derived | **TRUE** | Keep verbatim; the strongest block in the set. |
| 2 | Green-control support | **TRUE** | Keep, and make this the canonical *definition site* for the vacuous-control angle (C6, D5 option (c)) so the other four copies can cite it. |
| 3, 5 | Grade against the rubric; recommendation viability | **TRUE** | Keep both verbatim. |
| 4 | Code vs documentation | **ADAPTABLE** | *"the Type the finding carries"* — no `Type` field exists; the disposition vocabulary is the real axis. Re-point to `re-typed` / `merged` / `not substantiated`. Otherwise keep: the dead-code policy belongs here, not in an auditor phase. |
| 6 | Cross-phase conflict | **TRUE, strengthen** | Add the seam check C9 requires and nothing performs: *a finding filed outside the input's own declared scope paragraph is a defect in the input report*, not a merge. |
| 7 | Namespace integrity | **ADAPTABLE** | *"a controlled template's own list of prefixes"* is a **FALSE PREMISE** — the template enumerates no prefixes. Replace that shape with the compound form the template does carry: the front-matter `phase:` value paired with the prefix. Record that the four "already in use in shipped source" notes in 08/09/10/11 are not reproducible in the working tree, so the block must re-derive and never inherit a sibling's note. Flag `AUT-` vs `AUTZ-` and `MED-`-means-file-artifacts. |
| 8 | Template as artefact | **TRUE premise, wrong question** | The template **exists** now (FM13 fixed), so the premise inverted from "does it exist" to "does what it mandates survive into the reports" — but three of its four questions are false premises (no prefix enumeration, no rubric pointer pattern, no per-field count). Re-aim at the real contract: six front-matter fields, six per-finding fields, the `Zone`-quoted-verbatim rule, the reserved empty string, optional appendices. Keep *"never repair the template from inside a per-phase run."* |
| 10 | Validated report as artefact | **ADAPTABLE** | *"carries a verdict, its own identifier and **location**"* — no location field exists; location lives inside `Observation`. Re-point to the six mandated fields; add the coverage ledger to the appendices. |
| — | Scope paragraph | **FIX** | *"the fifteen content phases"* is accidentally still correct (01–12 + 13,14,15) but a hard count (B13/D10). Write "the other phases" and require the count to be derived. |
| — | Report Output | **TRUE, mostly accurate** | The section list in the template bullet matches the real template exactly. Three corrections: the output directory does not exist and must be created; the validated report's front matter must carry the **audited** phase and `executor: validator`; add the coverage-ledger and residual-footer rules (RC5, RC7) this file lacks as an output contract. |
| — | Front matter | **TRIM** | `status: draft` and `validated: no` have no reader anywhere in the framework (§2.1, R12). |

## 4.3 Proposed final block set (11)

Blocks 1, 3, 5 kept verbatim. Block 2 renamed to **"The vacuous-control angle, and its bindings: does it
exist, what scope does it declare, what did it examine"** so it is the definition site other phases cite.
Blocks 4, 6, 7, 8, 9, 10 rewritten as tabled above. **Block 11 — `NEW` — the shared angles, defined once
and bound by name**: *Establish the two angles this phase owns as definitions, not instantiations — the
vacuous-control angle (does the control exist, what scope does it declare, what did it examine, and
separately whether it ran at all) and the cross-resource side-effect angle (an effect spanning more than one
resource, and which resource is the real unit of atomicity). For each, which phases bind it in their own
words and whether the bindings still say the same thing. Two bindings drifted into different questions, and
an angle claimed by a phase that does not bind it, are findings; record which phases cite an angle no phase
defines.* `Evidence: both angle definitions with the phases binding each and the wording drift per binding;
one angle bound by two phases with different questions.` **This one block is what stops the set's five
control-scope paragraphs and three cross-resource claims from drifting — the C9/D5 mechanism for both, at
the cost of a block and no new file.**

## 4.4 Scope Boundaries (exact paragraph)

> **Scope Boundaries** — this phase audits **output** and the audit tooling's own artefacts: another
> auditor's claims, the support behind them, the band each was given, the recommendation attached to it, the
> finding-ID namespace across the set, the shared findings template as a controlled artefact, and the seams
> between phases. The other phases audit the system; no content phase's concern is this phase's, except where
> a finding's validity depends on a cross-phase claim. This phase never modifies source code, never renumbers
> an existing finding identifier, and never repairs a shared artefact from inside a per-phase run; the only
> documents it writes are its own validated reports and the residual footer they carry. It defines the shared
> angles it owns — the vacuous-control angle and the cross-resource side-effect angle — and adjudicates the
> bindings other phases declare of them; it does not audit the system to decide whether a control is any
> good. The namespace ruling is this phase's, and 08, 09, 10 and 11 currently carry such notes; their stated
> provenance must be re-derived here, not inherited. The seam check — a finding filed outside the input's own
> declared scope — is this phase's, and no other phase performs it. The findings-template contract is now the
> artefact under validation rather than a path that resolves to nothing: its six front-matter fields, its six
> per-finding fields, its rule that the zone be the block title quoted verbatim, and its reserved empty-state
> string are each in scope; and because it enumerates no finding-ID prefixes, the namespace ruling rests on
> the phases' own declarations paired with the template's front-matter `phase:` value.

## 4.5 Finding-ID prefix and output path

**`VAL-`** for validation-level findings, in a separate section from the audited findings table (already
correct — keep); the audited phase's own prefix is preserved unchanged. No new prefix required. The output
directory `.ai/audit/99-validation/` **does not exist** and is created by the run; this is the one place in
the set where stem and output directory deliberately differ (`99-audit-validate` → `99-validation`), which
must be stated so it is not "corrected".

```markdown
## Report Output

- Findings path: `.ai/audit/99-validation/{NN}-{phase-name}-validated-findings.md` — one validated report per phase, carrying the audited phase's own prefix and identifiers; the directory is created by this run
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter (with `phase:` set to the audited phase and `executor: validator`), summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: the audited phase's own prefix, preserved. Validation-level findings discovered *during* validation use `VAL-` and occupy a separate section — never interleaved into the findings table, because the two would share a `Severity` column carrying two different scales.
- Incremental append, ≤100 lines per pass — never write the entire report in a single call
- `problems-only: true` — suppress commentary about the validation itself, **not** dispositions; every disposition is a deliverable row, and a confirmed finding still carries one
- Empty state, exactly: `No problems found in this phase.` — and the coverage ledger goes in the appendices, never in the findings body: the blocks examined, the item count each actually reached, and every claim left unsettled with its reason, as a fixed residual footer
```

---

## 5. Items the other owners must resolve

1. **Ruling needed: stem vs `name` for the findings path.** My three files follow the brief and match;
   01–12 do not. The `08` and `99` owners should record the ruling once — `99` b8 is where it will otherwise be
   rediscovered as a per-file defect.
2. **Siblings' Scope Boundaries still cite deleted phases**: 07 cites "search recall (08)", "enum and
   boundary-model discipline (10)", "measurable latency (13)", "authorization (15)"; 06 cites "the platform
   download client and transport (09)", "search visibility (08)"; 11 cites "the language component of a key
   (14)". Under the new numbering these resolve to 11, 08, 11, 12 / 07, (none) / (none). All stale; my
   paragraphs already use the new numbers, so those owners need only repoint their own.
3. **`01-audit-process-architecture.md` block 4, "Async Bot Runtime — Dispatch Chain and Per-Update
   Lifecycle"**, is a false premise for this system: there is no bot tier. The long-lived set is the async web
   tier, the background job queue and the cleanup loop, and the "two processes agree on a verdict" seams that
   04, 12 and 11 keep referring to collapse to a single process. Flagged for the `01` owner — it changes
   several cross-references across the set. The four "already in use in shipped source" prefix notes are also
   not reproducible in the working tree; `99` must re-derive, not inherit.
