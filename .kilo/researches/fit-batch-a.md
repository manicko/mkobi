# Domain-Fit Analysis — Phases 01–04 (batch A)

Analysis artefact. No phase file, source file, or shared report was modified. Evidence for every
project claim below is a file path in `src/mkobi/`, `alembic/`, `docker/`, or the root environment
files, read directly.

---

## 0. Shared preliminaries

### 0.1 What actually exists (verified, not assumed)

| Concern | Verified reality |
|---|---|
| Long-lived processes | request-serving process (ASGI, one application object built by a factory at import of the serving module); a separate queue-consumer process; a periodic sweep loop running **inside** the request-serving process; a dev-only client-asset server. `docker/docker-compose.yml:169-221` starts the consumer as the vendor worker CLI, not the repository's own worker wrapper. |
| One-shot processes | a schema-migration service (`:55-80`); an in-process schema application path behind a configuration flag (`src/mkobi/db/starter.py:153`); a one-shot test-database recreation that terminates backends and drops/creates the database (`:189-292`); a module `main()` for the same (`:423-431`). |
| Config | one settings class, six source classes, process-global cached instance with a reload path (`src/mkobi/config.py:532-564`, `:768-794`). A module-level `get_config()` runs at **import** of the application module (`src/mkobi/app.py:38`), and `Settings.__init__` creates a directory as a side effect (`config.py:584-587`). |
| Auth | email + password, bcrypt, a short-lived credential returned in a response body, a long-lived credential in a cookie, revocation markers in a shared store, per-IP limiting on three surfaces. **No outbound link, no email delivery, no messaging tier.** The genuine one-time-credential handshake is the admin-minted temporary password (`src/mkobi/services/auth_service.py:540-599`, `src/mkobi/api/routes/admin.py:196-241` and `:403-423`, `src/mkobi/core/temp_password_store.py`). |
| Work submission | an in-process async queue consumed by one coroutine (`src/mkobi/core/task_queue.py`), reached by every upload (`src/mkobi/services/file_processing.py:364-373`). The durable-store consumer exists and is started, but nothing is ever submitted to it — the wrapper that enqueues to it is never called. |
| Store | one relational store; a request-scoped unit of work that neither commits nor rolls back by itself (`src/mkobi/db/session.py:70-88`); commit decisions in services and route modules; pool parameters are literals, not settings. |

### 0.2 Number remap — required to fix every cross-reference

The surviving set was renumbered; the four files below still speak the old numbers.

| Old | New | Old | New |
|---|---|---|---|
| 01 entry-architecture | 01 process-architecture | 11 test-coverage | 09 test-coverage |
| 02 config-secrets | 02 configuration-secrets | 12 production-ops | 10 production-ops |
| 03 db-concurrency | 03 db-concurrency | 13 performance | 11 performance |
| 04 auth-login | 04 authentication | 15 authorization | 12 authorization |
| 05 ad-lifecycle | **deleted** | 02 frontend | 13 client-tier |
| 06 pii-consent | **deleted** (archived) | 03 database | 14 schema-migrations |
| 07 data-processing | 05 data-pipeline | 04 security | 15 security-baseline |
| 07 media | 06 file-artifacts | 08 search-fts | **deleted** (archived) |
| 09 external-api | 07 external-boundary | 14 i18n | **deleted** (archived) |
| 10 code-quality | 08 code-quality | | |

Three consequences, each of which must be reflected in the rewritten Purpose of the file that
carries it:
1. **`06` no longer means consent.** Anything deferring "personal data / consent / erasure" to 06
   now points at file-artifacts. The honest move is to **drop the deferral**: this system has no
   personal-data store beyond account email and access rows, and no erasure flow.
2. **`05` no longer means lifecycle.** "Lifecycle correctness (05)" in the sibling files is now the
   data pipeline.
3. **`08`/`09` no longer mean search/test.** `06-audit-file-artifacts.md` and
   `07-audit-external-boundary.md` still say "search visibility (08)", "enum and boundary-DTO
   discipline (10)", "test adequacy (11)", "probes and storage operations (12)" — all now wrong.
   Out of scope for this batch; flagged for the owner of those files.

### 0.3 Finding-ID prefix inventory

In use: `ENT-` (01, retiring), `CFG-` (02), `DB-` (03, retiring), `AUT-` (04, retiring), `MED-` (06),
`EXT-` (07), `QLT-` (08), `TST-` (09), `OPS-` (10), `PERF-` (11), `AUTZ-` (12), `VAL-` (99).
`05-audit-data-pipeline.md` declares none yet (un-rewritten legacy file).

`AUT-` is a strict prefix of `AUTZ-`, which 12 owns — a live mis-attribution hazard in a set where
both exist. `DB-` is claimed by the whole database zone and is needed by 14. Both should be retired
now, while the four files are open.

---

## 1. `01-audit-process-architecture.md`

### 1.1 Current state

Purpose: entry surfaces, process topology, startup/stop lifecycle, schema bootstrap guarantee —
written for a "multi-process Django deployment". **9 blocks.** Frontmatter `name: 01-entry-architecture`
vs filename stem `01-audit-process-architecture` → mismatch; findings path
`.ai/audit/01-entry-architecture/findings.md` therefore does not match what
`audit-multi-phase.md:62-63` derives from the filename (`.ai/audit/01-process-architecture/findings.md`).
AP12/FM12 violation. Also carries `status: draft` / `validated: no`, which §2.1 of the design report
says to drop.

### 1.2 Premise audit

| # | Title (current) | Verdict | Evidence / replacement |
|---|---|---|---|
| 1 | Deployment Topology and Startup Dependencies | **TRUE** | Per-tier component inventory is real and the tiers genuinely differ: the migration service runs as the superuser in the base compose (`:64`) but sets no role at all in the development override (`docker-compose.override.yml:19-25`, falling through to the code default); `read_only: true` in base, `false` in the override; the client-asset server exists only in the override. "A component enabled but used by nothing" is live: the queue consumer is enabled, health-checked, and never receives work. Keep, re-nouned. |
| 2 | Entry-Surface Inventory and Import-Time Behaviour | **ADAPTABLE** | `the WSGI serving module` and `management-command dispatch` are **false premises** — no such constructs exist. Real equivalents: the application object built by a factory at import of the serving module; each service's container `command:`; a module-invoked one-shot; the reload/poll flags the development tier needs. The import-time half is richly applicable: dependency probing, logging configuration, and a cached configuration with a directory-creating side effect all run at import. Keep, de-Django'd. |
| 3 | Web Serving Tier — Worker Model and Shutdown Contract | **ADAPTABLE** | `arbiter`, `preloading`, `worker recycling` are foreign nouns and there is exactly one serving process type with no worker count, request timeout, or grace period declared anywhere in the repository — which is itself the finding, not the block's vocabulary. The live content: what happens to in-flight background work on termination. The lifespan cancels two tasks and disposes the engine, but the queue's own "pending tasks will be lost" warning is never invoked. Rewrite. |
| 4 | Async Bot Runtime — Dispatch Chain and Per-Update Lifecycle | **FALSE PREMISE** | No event-driven inbound component, no update dispatch, no per-update lifecycle. **Delete.** Its one live clause — "the process does not claim readiness before it can actually serve work" — is not hypothetical: the fail-fast configuration checks run in the factory, but schema application, the schema-version probe, the account upsert, reference seeding, temp-area cleanup and log retention all run in the lifespan *after* the server starts answering. Promote that clause to its own block. |
| 5 | Background Job Loop — Cadence, Dispatch and Restart Safety | **ADAPTABLE** | Real and stronger than written. The periodic sweep runs inside the request-serving process, once per process, with no election between replicas and no heartbeat; its only liveness signal is its own log line. The submitted-work path is an in-process queue with one consumer, in-memory status/result/error maps, and a documented "these will be lost" on restart — while a second, durable mechanism exists and is never reached. Re-nouned from "job registry / dedupe" to "which mechanism an operation actually reaches". |
| 6 | Schema and Reference-Bootstrap Gate | **TRUE** | The strongest block in the file. Real: a one-shot gate service, an in-process gate behind a flag, a destructive whole-database drop/create, and a version probe that refuses to serve without one. Guards: a session-level exclusion lock around the migration run with a single global key. The "once-only guarantee from ordering, guard, or neither" question is genuinely open — two services can both reach the migration path. Keep, sharpened. |
| 7 | Cross-Process Shared State and Side-Effect Coordination | **ADAPTABLE** | `the media filesystem` → the shared temp-file area on a volume both processes write; `the shared cache` → the one store backing limiter counters, revocation markers and one-time credentials. The `in-memory dedupe or idempotency marker` clause is live by construction (task status/result/error maps). Trim the media/photo framing. |
| 8 | Entry-Layer Discipline and Dependency Direction | **ADAPTABLE** | `bot handlers` is a false premise; the two real transports are the request-entry modules and the container entry declarations. The substance holds and is violated: several route modules call repositories directly, and repository factories are constructed inside dependency functions rather than resolved through the session. Keep, re-nouned. |
| 9 | Route Surface Wiring and Entry-Point Reachability | **ADAPTABLE** | `assembled at project and per-app level`, `handler routers` → router aggregation under one versioned prefix; a client-asset mount whose fallback intercepts unresolved non-API paths; health probes registered outside the router set; periodic operations registered in the lifespan. The guard each route carries is **not** this block's — 12 owns that. Add that clause explicitly. |

### 1.3 Proposed final block set (9)

1. **Component inventory, and the topology that differs between deployment tiers** — Enumerate every
   long-lived, one-shot and conditionally-enabled component per tier, and the ordering and readiness
   edges declared between them. A component enabled and health-checked that nothing ever reaches is a
   finding; a declared edge that does not match a component's real boot requirement is a finding.
2. **Entry surfaces: what is constructed when a surface loads, and what is deferred** — Enumerate
   every surface the system is started or entered through, including container entry declarations and
   one-shot maintenance invocations, and for each establish what runs on load versus first use — with
   the filesystem, network and store reachable at load time, and the surfaces the automated gates
   never analyse.
3. **Startup order, and the interval in which the process answers before it can serve** *(NEW, replaces
   old 4)* — Establish the order of boot preconditions against the first moment the process is
   reachable, and reproduce the interval in which a request is accepted against a precondition that has
   not completed.
4. **Termination: what an in-flight operation leaves behind** *(replaces old 3)* — Establish, per
   long-lived component, what a stop signal interrupts, what the process drains before exit, what it
   cancels mid-operation, and which half-finished work no component reconciles on the next start.
5. **The periodic loop and the work-submission mechanisms inside the request-serving process** — Establish
   cadence, multiplicity across replicas, per-operation bound, failure isolation, and the liveness signal
   as an outside observer sees it; then the submission mechanisms, which one a given operation reaches,
   and what state a repeat run or a restart finds.
6. **The schema and reference-data bootstrap gate, and the path that can destroy a schema** — Every path
   that can mutate schema or reference data, the guard each takes, the guard's acquisition semantics, where
   the once-only guarantee actually comes from, and the window each ordered step opens for concurrent readers.
7. **Shared state across processes, and what is per-process by construction** — What the components
   coordinate through, marked genuinely shared against per-process or per-restart; which multi-resource
   effects interleave; every in-memory marker whose persistence across restart is unproven.
8. **Entry-layer discipline and dependency direction** — Parse, delegate, respond: which domain or
   persistence work is found inside an entry module, every back-import and cycle, and each transport
   contract implemented more than once.
9. **Route surface assembly and reachability** — The assembled route and registration surface with each
   entry's downstream path, namespacing and collisions, mounts that intercept unresolved paths, and every
   registered entry no inbound trigger reaches. Which guard a route carries is 12's.

**REMOVED:** old 4 entirely (false premise). Old 3 and 4's live clauses become new 3 and 4. No block
count change.

### 1.4 Scope Boundaries

> **Scope Boundaries** — owned here: entry surfaces, process topology, startup and termination lifecycle
> across the request-serving, work-consuming, periodic and one-shot components, and the schema and
> reference-data bootstrap guarantee including the destructive path. Not owned here: the health, liveness
> and readiness endpoint and its probe contract (10); connection, unit-of-work, exclusion and pooler
> semantics (03); the settings that select a variant and the secret values behind it (02); the health
> endpoint's effect on the result the client sees (11); the ingestion and aggregation pipeline the
> submitted work enters (05); the temp-file area's admission, keying and lifetime (06); which surfaces a
> credential or a token must limit and how the request is authorised (04, 12); the deployed container
> posture, artifact provenance and backup contract (10); suite adequacy (09). Two processes of different
> roles are deliberately asymmetric; a difference between them is not a defect on its own — report it only
> where the code's own documentation or comments misstate it.

### 1.5 Finding-ID prefix and Report Output

**Prefix: `TOPO-`** — 4 letters, zero collisions in `src/`, `tests/`, `frontend/`, `docs/`; retires
`ENT-`, which no longer leads the file's name.

```markdown
## Report Output

- Findings path: `.ai/audit/01-process-architecture/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `TOPO-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
```

---

## 2. `02-audit-configuration-secrets.md`

### 2.1 Current state

Purpose: how configuration and secrets are declared, resolved, validated and kept separate — written
for a "dual-process Django system". **8 blocks.** Frontmatter `name: 02-config-secrets` vs stem
`02-audit-configuration-secrets` → findings path drift (AP12). Deferral line carries **five** stale
numbers (10, 11, 12, 15, and "01/03/04" which happen to be stable). Report Output is a bespoke
six-item shape (FM14/AP14) and the severity rubric is the retired 3-file table form.

### 2.2 Premise audit

| # | Title (current) | Verdict | Evidence / replacement |
|---|---|---|---|
| 1 | Settings surface & variant-selection topology | **TRUE** | One settings class, six source classes, a process-global cached instance with a reload path, and one environment value selecting the variant — but the selection is per-process, not per-environment-label, and the value is also a container-vs-host question (the deployment definition says so in a comment). Add the dimension the block misses: the cached instance is re-fetched per request on some paths and pinned at import on others. |
| 2 | Env-var name-contract reconciliation | **TRUE**, richer | The project has **six** name universes, not four: names the code reads; two shipped example templates; two compose environment definitions; the defaults file shipped inside the package; and names the orchestrator script reads. Plus a nesting delimiter with single-underscore aliases. Real drift already visible: a variable that exists only in the deployment definition and is never read by code; example-template names in flat form that the loader silently ignores; list-valued example names the parser must coerce. Keep, widened. |
| 3 | Secret validation & fail-fast behaviour | **TRUE** | Guards exist and differ in kind: one required unconditionally; several conditional on the environment label; one duplicated at the point of consumption; several warning-only outside production. Live findings: a validator whose body returns its input unchanged while its docstring claims a check, with a comment deferring the real check elsewhere; a weak-value list containing entries whose case can never match the form compared against it. The `production secret file can disable it` clause survives verbatim. |
| 4 | Secret provenance & exposure surface | **TRUE** | Root env file (git-ignored), three shipped templates, a build context that includes the repository root, and secrets expanded into the deployment definition's environment blocks. The block's `ignore coverage spans version control and the build context, not only the former` clause is the sharp one: the build context is the repository root, and the ignore rules exempt named templates. Add: a configuration object that creates a directory as a side effect of being constructed, and a value logged at load time. |
| 5 | Environment separation & process parity | **ADAPTABLE** | `backend substitution` and `host allow-lists` are false premises. Survives and is live: two co-resident processes, a development tier that ships a default origin the production guard class rejects, a cookie-secure flag flipped only in development, a migration role that differs between tiers, a read-only filesystem that differs. The origin/cookie **policy** half stays; renumber the request-forgery **enforcement** half to 12. |
| 6 | Automation env-parity vs guarded configuration | **ADAPTABLE** | "Containerised vs natively executed" survives. The test stack is a separate project with hard-coded literals and **no template file at all**, so it can exercise neither the file-based secret path nor the interpolation guards. Real: the production-only guards are exercised by no automated environment. Keep, re-nouned. |
| 7 | Env-overridable production posture | **TRUE** | Live list: the debug switch, the cookie-secure switch, the limiter fail-closed switch, the schema-application switch, the wildcard-origin switch, the temp-area path. Each can change a running process's posture; some are re-pinned only at construction time, some only for one variant. Keep. |
| 8 | Dead, ineffective & unconsumed configuration | **TRUE**, and it should carry the vacuous-guard clause | Real: a guard that examines nothing; a value that resolves to a path relative to the process working directory while every deployment supplies an absolute one; alias properties that re-derive what the object already holds; a settings field no shipped template mentions; a role name that is a constant in the schema rather than configuration. Split this into two blocks so the vacuous-control question gets its own obligation. |

### 2.3 Proposed final block set (9)

1. **Settings source precedence, and the variant each running process resolves** — Establish the
   precedence order of the source classes, the value each process actually resolves, and whether the
   selection is per-process or per-environment-label; treat a variant that exists only as a test
   convenience as a variant, and record the mechanism that selects it.
2. **Name universes: what code reads, what templates declare, and what the deployment supplies** —
   Reconcile in both directions, derive the symmetric difference rather than sampling it, and judge
   whether the drift signal is distinguishable from a legitimately new name.
3. **Guarded preconditions: presence, strength, and whether the refusal is actionable and secret-free** —
   Per guarded value, four questions: is a guard present, is it unconditional, can any value reachable
   in a hardened variant disable it, and is the failure actionable without disclosing the value. Absent,
   present-but-empty, and malformed are three states.
4. **Secret provenance, and every surface the material can reach** — Committed files, build contexts and
   build steps, process command lines and standard output, error and traceback paths, and automation-supplied
   credentials. Classify every credential-shaped literal as real, placeholder, or fixture; confirm ignore
   coverage spans the build context, not only version control.
5. **Tier divergence: which differences are deliberate, and which are unintended** — What must not cross
   between variants and between co-resident processes, each judged intentional-and-complete rather than
   merely different. Which origins and cookie attributes are honoured per variant is the policy half and is
   this phase's; which surfaces a request-forgery check reaches is 12's.
6. **Automated environments, and the configuration path each can actually exercise** — For every automated
   environment, how values reach the process, which guards it exercises, and which required values it
   supplies none of; treat the difference in how values arrive as a first-class object.
7. **Posture switches that can change a running process** — Identify the settings whose value alters the
   security or delivery posture of a live process, and for each whether the substitution is intended,
   constrained, and re-pinned where a hardened variant is supposed to freeze it.
8. **Assigned, derived and branched configuration that nothing reads** — Per name, a liveness verdict;
   every value that is derived rather than read, checked against its consumer's contract and not merely
   for the existence of the derivation; every variant branch reachable under some real selection.
9. **A guard that runs, reports clean, and examines nothing** *(split from old 8)* — For every validation
   and gate over configuration, three separate questions: does it exist, what scope does it declare, and
   what did it actually examine; a check whose body cannot fail on the value it claims to test is a finding.
10. **Defaults that are wrong for the environment the process is deployed into** *(NEW)* — For each value
    whose default is host-shaped rather than deployment-shaped, establish whether the mismatch is
    documented where a reader would find it, and whether anything fails when the default survives into a
    deployed environment. The deployment definition itself carries comments asserting two such defaults are
    wrong; nothing checks that the assertion still holds.

*(Blocks 1–8 are old 1–8 re-nouned and reordered; 9 and 10 are the split and the new one. Total 10.)*

### 2.4 Scope Boundaries

> **Scope Boundaries** — owned here: the settings object and its source precedence, the name contract
> between code, templates and the deployment definition, guarded preconditions and their refusals, secret
> provenance and exposure, variant-to-variant and process-to-process parity, posture switches, and defaults
> whose correctness depends on the environment the process runs in. Not owned here: entry surfaces, process
> topology and boot ordering (01); the connection, unit-of-work, exclusion and pooler semantics that settings
> select (03); pipeline admission limits and the shapes they accept (05); the temp-file area's keying and
> lifetime (06); which surfaces a credential limits and what makes an identity acceptable (04); convention
> and dead-code discipline in source (08); the container posture, artifact provenance, transport security,
> probes and backup that consume these values (10); measurable latency (11); which surfaces a request-forgery
> check reaches and whether it runs on each (12); suite adequacy (09); namespace rulings (99).

### 2.5 Finding-ID prefix and Report Output

**Prefix: `CFG-`** — retained. Zero collisions in source, tests, frontend, and docs; semantically exact;
no competing claimant in the set.

```markdown
## Report Output

- Findings path: `.ai/audit/02-configuration-secrets/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `CFG-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- "Violates invariant X" is not a finding: name the exact role that violates the property and the exact consequence; a shipped test asserting the current behaviour is a remediation blocker, not a gate, and what could not be verified in this environment is a limit on the report recorded in the appendix, not a finding
```

---

## 3. `03-audit-db-concurrency.md`

### 3.1 Current state

Purpose: transaction boundaries, row-level locking, the cross-process serialisation registry, background
safety, derived values, cross-resource consistency — for a "dual-process Django system". **10 blocks.**
Frontmatter `name: 03-db-concurrency` vs stem `03-audit-db-concurrency` → **the only one of the four
whose stem and name agree**; findings path `.ai/audit/03-db-concurrency/findings.md` is correct. Deferrals
cite `09` (now 07) and `13` (now 11). Structure, block preamble, rubric bullets and six-bullet Report
Output are already the modern shape — this is the best-formed of the four and the rewrite is a
re-nouning, not a rebuild.

### 3.2 Premise audit

| # | Title (current) | Verdict | Evidence / replacement |
|---|---|---|---|
| 1 | Persistence access surface and configuration-path divergence | **ADAPTABLE** | The bypass clause is **TRUE** and rich: the bootstrap account insert, the retention delete, the role-privilege probe and the whole-database DDL are all hand-written, three of them raw statements. The `alternative configuration branches` clause is **FALSE** — there are no branches; the pool parameters are literals in the engine construction and no setting can change them, which is the sharper finding. "Connection lost mid-request" is live (`pool_pre_ping` is on). Add: a client is constructed per call on one path and once per process on another. |
| 2 | Transaction boundaries of multi-row writes | **TRUE** | The live shape: a request-scoped unit of work that never commits or rolls back itself, so the commit decision lives in services *and* in route modules; a background job that opens one transaction and deletes its input file inside it; a retention delete that commits on a bare connection. Keep. |
| 3 | Error handling inside a transaction boundary | **TRUE** | Real: two functions deliberately accept an outer unit of work and decline to commit so the caller owns the boundary, with a comment saying so. That is a real pattern with a real failure mode — a caller that forgets. The `swallowed error leaves the transaction abortable` clause is live. Keep. |
| 4 | Constraint-enforced invariants and recovery paths | **TRUE** | Real: a uniqueness constraint on the identity column used with a conflict clause on one path and a plain insert on another; a uniqueness constraint on one child row per parent; the cascade question on delete. Keep. |
| 5 | Read-modify-write, destructive ops, derived values | **TRUE**, strongest after 2 | Real: derived values are cleared and rebuilt on every submission; an append mode reads back everything it just wrote inside the same unit of work; a delete acts by identifier and ignores the predicate the caller selected on. `Which paths take a row-level lock?` — no path does; that absence is the finding. Keep. |
| 6 | Cross-process serialisation registry | **ADAPTABLE** | `where identifiers are allocated` is a foreign noun; `advisory-lock` survives and is real (one session-level lock, one global key, around the migration run); `row-level locking` does not exist anywhere in the repository; `caller-released lifetime` is a WSGI/ORM-era concept with no counterpart. Replace the whole enumeration with: every exclusion mechanism that exists, its lifetime and holder, and the operations that must be exclusive and have none — including the process-local queue whose single consumer is an exclusive right nobody declares. |
| 7 | Background and one-shot operation safety | **TRUE**, strong | Real: a job that is not atomic by design and can be repeated; dedupe that is a status column and nothing else; a periodic sweep any replica may run; a queue that documents task loss on restart. `Hold duration is measurable` survives. Keep. |
| 8 | Schema and reference-data mutation under concurrent load | **TRUE**, sharper than written | Real and unusual: a whole-database drop/create executed from inside the application process, terminating other backends first; a retention delete running on every start; a migration run guarded by a lock. `a child process inherits nothing` survives. Keep. |
| 9 | Database work in the asynchronous process | **FALSE PREMISE** | There is no event-driven tier. The request-serving process *is* async; the consumer process runs its async work on its own loop with `asyncio.run`. No contention funnel, no bounded shared worker, no sync-call-reaches-the-loop question. **Delete.** Its two live clauses — one contended resource degrading a whole process, and a wait that is not bounded — fold into blocks 1 and 6, where the pool literals and the absent lock timeouts already live. |
| 10 | Consistency across the shared-state boundary | **ADAPTABLE** | `a row and a file it names` is **TRUE and sharp**: the derived-value rows, the status row, and a temp file on a volume both processes write, deleted in different orders by different subsystems. `a row and a cached value` is TRUE (revocation markers, limiter counters, one-time credentials). `out-of-band marker state` is a false premise. Keep, trimmed. |

### 3.3 Proposed final block set (10)

1. **How the store is reached, by which process, and what each connection costs** *(was 1)* — Enumerate
   every path the store is reached from, including the maintenance invocations, and every place a unit of
   work's client is constructed per operation rather than per process. Establish which connection parameters
   are literals no setting can change, and reproduce what a connection lost mid-operation leaves behind.
2. **Who opens the unit of work, and who decides it ends** *(NEW emphasis, split out of 2 and 3)* — Establish
   whether the request-scoped unit of work commits, rolls back, or does neither on its own, and therefore
   which layer owns the commit decision; then every helper that accepts a caller's unit of work and declines
   to end it, and every caller of such a helper that does not end it either.
3. **Multi-row and multi-resource domain writes: does the boundary sit where the invariant is** *(was 2)* —
   Which operations change more than one row, or a row and something only meaningful beside it; a partial
   commit is reachable when writes straddle boundaries or the failure the boundary is built for never arrives.
4. **Tolerated database errors: what happens to the enclosing unit of work** *(was 3)* — Is the failing
   statement isolated so the surrounding work stays usable; does a helper promising never to affect its
   caller get invoked from inside another's work; does a swallowed error leave the caller's work aborted?
5. **Constraint-enforced invariants and their recovery paths** *(was 4)* — A constraint that is both the last
   line of defence and an unhandled user-facing failure is a finding; so is one whose documented recovery is
   unreachable, and one enforced on one write path and not on another.
6. **Read-modify-write, destructive operations, and derived values** *(was 5)* — Does the mutation re-assert
   the predicate its selection used; a correctly serialised operation can still destroy another writer's work;
   a derived value cleared and rebuilt on every submission is a finding when the rebuild's inputs are read
   back from what it is rebuilding.
7. **Exclusion mechanisms as one system: lifetime, holder, and what is not covered** *(was 6)* — Every
   mutual-exclusion mechanism that exists, its lifetime, its acquisition point and release path, and the
   operations that must be exclusive and have none. Where an exclusive right is held by a single process-local
   consumer or by a lock nobody times out, treat the absent bound as the finding.
8. **Background and one-shot operation safety** *(was 7)* — How each is invoked, bounded and interrupted, and
   what an interrupted run leaves: an open unit of work, a held row, or an already-committed batch. Is an
   operation not atomic by design safe to repeat, and does a half-applied run resume or double-apply?
9. **Schema and reference-data mutation, and the window each step opens** *(was 8)* — The ordered mutating
   steps, the window each opens for concurrent writers, whether a lock held by a coordinating component covers
   the work it dispatches, and whether more than one component can reach the same destructive path.
10. **Effects that span more than one resource: commit order and intermediate state** *(was 10)* — Which
    writer assumes it is alone, which resource is the real unit of atomicity, and whether the intermediate
    state leaves a dangling reference or an orphan nothing repairs.

**REMOVED:** old 9 (false premise; its two live clauses folded into new 1 and new 7). Old 1's dead
"configuration branch" clause and old 6's foreign nouns are re-nouned, not deleted as angles. No block
count change; the rewrite is re-nouning plus one new emphasis in block 2.

### 3.4 Scope Boundaries

> **Scope Boundaries** — owned here: how the store is reached from every process and path, unit-of-work
> boundaries, tolerated-error handling inside them, constraint-enforced invariants and their recovery,
> read-modify-write and derived-value recomputation, exclusion mechanisms and their lifetimes, background and
> one-shot operation safety, schema-mutation windows, and effects spanning more than one resource. Not owned
> here: entry surfaces, topology, boot ordering and the schema bootstrap gate at the process level, and the
> component that runs a destructive database path (01); the settings and secrets that select a connection
> (02); the ingestion and aggregation pipeline this phase's transaction boundary protects (05); the
> temp-file area whose lifetime the cross-resource effect depends on (06); outbound transport, retry and
> failure isolation (07); pool sizing as a measured cost and the tier's ceiling (11); the connection pooler's
> place in the topology and whether the deployed path enables it (10); the migration chain's linearity,
> reversibility and index inventory (14); suite adequacy (09). Three separable claims are one rule here: any
> concurrency guard is judged by whether it would fail if the protection it names were removed.

### 3.5 Finding-ID prefix and Report Output

**Prefix: `TXN-`** — 3 letters, zero collisions in source, tests, frontend, and docs. Retires `DB-`, which
is the prefix the whole database zone claims and which 14-schema-migrations needs; reserving `DB-` for 14
and giving this phase `TXN-` removes the ambiguity at the source. **Orchestrator must confirm**, because it
is a namespace ruling.

```markdown
## Report Output

- Findings path: `.ai/audit/03-db-concurrency/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `TXN-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- Verification-table entries are a methodology record, not a filter; file a finding a shipped test contradicts and record that test as a remediation blocker; what could not be reproduced under concurrency is a limit on the report recorded in the appendix, not a finding
```

---

## 4. `04-audit-authentication.md`

### 4.1 Current state

Purpose: the deep-link login handshake end to end — "one process mints the credential, a bot spends it,
the web opens the session". **8 blocks.** Frontmatter `name: 04-auth-login` vs stem
`04-audit-authentication` → drift; findings path `.ai/audit/04-auth-login/findings.md` does not match
`.ai/audit/04-authentication/findings.md`. Carries `validated: yes`, the only non-default value in the set,
which nothing reads. Deferral cites `06` (PII/consent — **now deleted**) and `15` (now 12). Severity
rubric is the retired table form; Report Output is the bespoke shape.

**The single most important finding of this analysis:** the handshake this file is about **does exist**,
but it is not the deep-link login. It is the admin-minted temporary password — minted at a privileged
endpoint, hashed into the account row, cleartext left in a shared store, a separate retrieval handle
returned to the caller, cleartext read back by a second privileged call. The file's subject is right; its
nouns are all wrong. Every block below is judged against that real handshake.

### 4.2 Premise audit

| # | Title (current) | Verdict | Evidence / replacement |
|---|---|---|---|
| 1 | Credential issuance and delivery boundary | **ADAPTABLE** → TRUE on a different subject | `where the outbound link is built` is a **false premise**: there is no email sender, no link, no messaging. The delivery channel is the caller's own authenticated response. Real and sharp: the retrieval handle travels as a **request path segment**, so every access log, proxy log and browser history records it; and the minting call returns the handle in a response body. The per-surface mapping clause survives verbatim. |
| 2 | Credential strength and unguessability | **ADAPTABLE** | Two subjects the block half-names (the retrieval handle, the temporary password) plus a third it misses: whether verification of a submitted secret costs the same whether or not the account exists. There is a deliberate equal-cost step whose effect must be demonstrated, not assumed — and the shipped dummy value's shape is exactly the kind of thing that makes the demonstration fail. `safe-to-carry is not unpredictable` survives. |
| 3 | Claim guards — atomicity, single use, lifetime | **ADAPTABLE** → the strongest block after 6 | The single-use guarantee is a get-and-delete pair in a pipeline against the shared store. Real: the **issuance** side fails open — a store failure is logged and the account change is committed anyway, so the pair can be unredeemable while the account is already changed. The retention bound is a time-to-live with no persistence or eviction guarantee, and at the read end a store failure is indistinguishable from "already claimed". `any guard defined but never reached` is live. |
| 4 | Account resolution and identity binding | **ADAPTABLE** | `whether both processes resolve one account` is a **false premise** — there is no second identity-resolving process. `a seller's handshake binds a privileged row` survives as the **placeholder collision** question and is sharper here: the bootstrap administrator is created in the same identity namespace as real accounts, keyed on a non-address default value, with a conflict clause that leaves a pre-existing account's own role and secret untouched. Also live: the role carried inside the credential is not the role the per-request gate uses. |
| 5 | Handshake completion on the consuming side | **ADAPTABLE** | The consuming side is the password-change operation. Every clause survives: whether every guard that can refuse precedes the irreversible write, whether the visible failure is uniform across its causes, whether "not yet" is distinguishable from "no such credential", whether the credential is bound to the client that obtained it. The live instance: the account carries a change-required flag, set at both issuance points, that no consuming path consults. |
| 6 | Post-linking gate and eligibility agreement | **ADAPTABLE** | The best mapping in the file. `Compare the two processes' eligibility predicates over the same subject` becomes: compare the account state a record carries against the account state a request gate consults, and reproduce any account state one admits and the other refuses. Three such conditions exist and are checked at different points, one of them nowhere. |
| 7 | Anonymous-to-authenticated state transfer | **FALSE PREMISE** in its nouns, real in its content | `a short-lived per-identity cache of a pre-login choice`, `conversational state` — none exist. But one logical session here is carried by **two credentials in two channels with two lifetimes**, and the long-lived one is neither replaced when used nor bound to the client that obtained it. That is the block's replacement. |
| 8 | Abuse limiting on the login surfaces | **ADAPTABLE** → strong | Four live findings: the limiter's read-then-increment is not a single indivisible step; the caller identity is whatever the serving process believes the peer address to be, which behind the reverse proxy is the proxy, so every caller shares one bucket; one surface's key falls back to a caller-supplied value when the address is unknown, sharing a key namespace with the address namespace; and the limiter's own failure mode is a configuration switch that can turn a security control into a no-op. Every clause of the block survives. |

### 4.3 Proposed final block set (9)

1. **The one-time credential handshake end to end: issuance, where the cleartext rests, retrieval, and
   what the retrieval handle is exposed to** — Establish both issuance points, the state the account is
   left in, the store the cleartext rests in, and the single-use read. Map every surface the handle and the
   cleartext reach and rule each inside or outside the confidentiality boundary before calling it a leak.
2. **The two credentials that constitute one session: issuance paths, what each is accepted for, and what
   distinguishes them** *(NEW, split from old 2 and old 7)* — Enumerate every place a credential is minted,
   including the service-layer minting paths and any no-longer-reached one; establish whether anything in
   the credential itself separates the two lifetimes, or whether separation rests entirely on which claim
   name a given gate happens to read. A credential accepted where the other is expected is a finding.
3. **What makes a secret acceptable, and whether acceptance costs the same in every case** *(was 2)* — Judge
   each secret as an unguessable bearer value against its issuance and its acceptance window; separately
   judge the equal-cost property of the verification path, including the branch taken when no account
   matches, and demonstrate rather than assume it.
4. **Single-use and lifetime guarantees, in both directions** *(was 3)* — Is the guard evaluated in the
   same indivisible step as the state change; what happens when issuance cannot reach the store the
   redemption depends on; what the retention bound is and what its own unavailability does; whether a
   refusal distinguishes "never existed" from "already claimed" from "cannot be checked now".
5. **The identity namespace the handshake writes into, and the privileged entries already in it** *(was 4)* —
   Whether claiming creates an account, whether the namespace real identities resolve into can already be
   occupied by an operator-provisioned privileged placeholder, and what a conflict clause does to an account
   that already holds that name.
6. **Account state the credential cannot carry: the completion path** *(was 5)* — Whether every guard that
   can refuse precedes the irreversible write, whether the visible failure is uniform across its causes, and
   what a refused attempt leaves behind.
7. **Account state the request path does not consult** *(was 6)* — Enumerate every condition an account
   record carries, and which of them a gate evaluates, on which surface. Reproduce any account state one
   gate admits and another refuses. The per-request gate itself — absent payload, unresolvable identity, a
   raising check — is 12's decision, not this phase's.
8. **Session continuity: what a captured long-lived credential is worth** *(was 7, re-nouned)* — What
   survives a rotation, what is replaced when it is used, whether the longer-lived credential is bound to
   the client that obtained it, and what an observer who captures it can do for its whole lifetime.
9. **Abuse limiting on the unauthenticated surfaces** *(was 8)* — Per surface and per layer, what identifies
   the caller and whether it is observed or merely asserted; whether the limiting step is indivisible under
   real concurrency; what the limiter does when its store is unavailable or its key expires; and the key
   namespaces, which must not be shared between an observed value and a caller-supplied one.

**REMOVED:** nothing at block level. Old 4's and old 7's foreign premises are replaced in place, not
deleted, because both hide a live finding.

### 4.4 Scope Boundaries

> **Scope Boundaries** — owned here: issuance, storage, single use, lifetime and refusal of every
> credential; what separates the two credentials that constitute one session; the identity namespace the
> handshake writes into; account state a credential carries and a request path does not consult; and abuse
> limiting on the surfaces that do not yet hold a credential. Not owned here: entry surfaces, topology and
> the settings that select a signing secret (01, 02); the exclusion and unit-of-work semantics behind the
> account and its revocation markers (03); the retrieval token's key lifetime as a store-expiry question,
> and the temp-file area (06); outbound transport and any third-party call (07); the role hierarchy and
> per-object access decision, and which surfaces a request-forgery check reaches (12); the client tier's
> handling of the two channels and its own storage of them (13); the transport security and certificate
> lifecycle in front of the edge (10); hashing cost and password-at-rest policy as a general control (15);
> suite adequacy (09). This phase and 12 are negotiated, not partitioned: this phase owns identity
> resolution, binding and the session-layer consequences; 12 owns the per-request gate; neither files the
> same gate decision. There is no consent, personal-data or erasure zone in this system, so no deferral is
> declared for one.

### 4.5 Finding-ID prefix and Report Output

**Prefix: `AUTH-`** — 4 letters. The only matches in the repository are `01-auth/…` doc-path substrings,
not finding identifiers. Retires `AUT-`, which is a strict prefix of `AUTZ-` (12-authorization) and would
mis-attribute findings across the two files.

```markdown
## Report Output

- Findings path: `.ai/audit/04-authentication/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `AUTH-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A refusal observed without a live store is recorded as a limit on the report, not a finding; a shipped test asserting the current behaviour is a remediation blocker, not a gate
```

---

## 5. Cross-file observations for the orchestrator

1. **Two of the three retired prefixes need a ruling.** `AUT-` → `AUTH-` is a collision fix I recommend
   outright. `DB-` → `TXN-` is a namespace reservation for 14 and should be confirmed before 14 picks.
2. **Every findings path in these four files is wrong except 03's.** The orchestrator derives the path
   from the filename (`audit-multi-phase.md:62-63`); 01, 02 and 04 will each write to a directory the
   orchestrator will not look in.
3. **The four files need the same mechanical pass**: drop `status` and `validated`, rename the frontmatter
   `name` to the stem, convert the 02 and 04 severity tables to four bullets, convert their bespoke Report
   Output to the six-bullet form.
4. **Two sibling files outside this batch carry stale cross-references** (06 and 07 both still cite the
   pre-renumber numbers, and 08/09/10/11/12 all cite a "lifecycle (05)" that is now the data pipeline).
   Not mine to fix; flagged.
5. **The 04 rewrite is the highest-value single change in this batch.** It is the only file whose subject
   is real but entirely mis-nouned, and the handshake it should describe is currently unexamined by any
   phase in the set.
