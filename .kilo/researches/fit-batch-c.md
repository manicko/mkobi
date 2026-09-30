# Domain-Fit Report — Batch C (Phases 09, 10, 11, 12)

Fit analysis of four phase files against the **actual** mkobi codebase, before rewrite. Binding
standards: `llm-audit-task-spec-design.md` §2–§7 (B1–B14, D1–D11, C1–C9, RC1–RC7, AP1–AP19).
No phase file, source file, or shared report was modified.

## 0. Set-level findings applying to all four files

**F-1 — Numbering/frontmatter drift (AP12).** All four files were renamed to the new stems but kept the
old frontmatter and old findings directory. The orchestrator derives the path from the stem, so each
currently writes to a directory its filename does not name. Required:

| File | frontmatter `name` now | findings path now | required |
|---|---|---|---|
| `09-audit-test-coverage.md` | `11-test-coverage` | `.ai/audit/11-test-coverage/` | `09-test-coverage` → `.ai/audit/09-test-coverage/findings.md` |
| `10-audit-production-ops.md` | `12-production-ops` | `.ai/audit/12-production-ops/` | `10-production-ops` → `.ai/audit/10-production-ops/findings.md` |
| `11-audit-performance.md` | `13-performance` | `.ai/audit/13-performance/` | `11-performance` → `.ai/audit/11-performance/findings.md` |
| `12-audit-authorization.md` | `15-authorization` | `.ai/audit/15-authorization/` | `12-authorization` → `.ai/audit/12-authorization/findings.md` |

**F-2 — Cross-batch defect, not mine.** The already-renamed siblings `01`, `03`, `06`, `07`, `08` also
carry stale findings paths (`01-entry-architecture`, `07-media`, `09-external-api`, `10-code-quality`)
and stale Scope-Boundary numbers. Reported to `main`; not actionable in this batch.

**F-3 — Template now exists.** `.ai/audit/templates/audit-findings.md` is present (FM13/AP13 resolved);
all four `Template:` bullets become true statements.

**F-4 — Prefixes.** In use: `ENT-`, `DB-`, `MED-`, `EXT-`, `QLT-`, `TST-`, `OPS-`, `PERF-`, `AUTZ-`,
`VAL-`. Phases 02/04/05/13/14/15 have not declared one. **`TST-`, `OPS-`, `PERF-`, `AUTZ-` are unique —
keep all four.** Changing them would break the continuity claim the current files make (identifiers
already minted in a prior cycle, at least one resolving to two findings), which is a live namespace
hazard 99 needs to keep.

**F-5 — C6 shared angles.** "A control that runs, reports clean, examines nothing" is instantiated in
09 b7, 10 b3, 11 b2, 99 b2. Ruling proposed: **10 owns the deployed-surface instantiation, 09 owns the
gate-and-suite instantiation, 11's is deleted** (no performance control exists); each references the
angle by name rather than restating the three questions. The cross-resource angle (01 b7 / 03 b10 /
06 b11) has one genuine live instance nobody owns — **a job record and the temporary file it names,
written by two processes** — assigned to **05**, with 01/03/06 deferring.

---

# 1. `09-audit-test-coverage.md` → Phase 09 — Test Coverage

## 1.1 Current state

Audits whether the suite would notice if the product made the wrong decision, and the fidelity of what
it asserts once it does. **8 blocks.** `name: 11-test-coverage` ≠ stem `09-audit-test-coverage` — F-1.

Least foreign of the four: no bot/Django nouns, architecture-neutral angle. The gap is coverage, not
premise — the suite's two decisive fidelity defects (the default test identity, the global store
substitute) are named nowhere, and the merge-gate block is written for automation that does not exist.

## 1.2 Premise audit

| # | Block | Verdict | Evidence / replacement |
|---|---|---|---|
| 1 | Exercised, not merely reachable | **TRUE** | Strongest block, and a decisive instance it does not name: the shared identity fixture creates its user at the **top role**, and the object-level check short-circuits for that role — so every test authenticating through it is structurally unable to observe any per-object decision. "A branch whose effect nothing observes" is exactly right. |
| 2 | What the doubles remove | **TRUE** | The shared store substitute **ignores the expiry argument on write**, records no timeout on the expiry-by-name path, returns a fixed timeout on read; the autouse fixture additionally replaces the rate-limit decision with constant-allow for **every** test; the fixture that restores real behaviour is opt-in. "A stand-in standing in for a mechanism that exists to enforce an ordering" is live — the substitute removes expiry-based revocation. |
| 3 | The fixture data contract | **ADAPTABLE** | "Key space helper" and "helper universes" are foreign. Equivalent: the manufactured **identity**, the manufactured **store**, the session-scoped schema rebuild, and the environment defaults a fixture silently supplies that the product never ships. "A fixed value the production vocabulary already names restated as a bare literal" is **TRUE** — the shared error-code vocabulary is restated in route modules. Cut the "production code is king" metadiscussion. |
| 4 | Both sides of every boundary | **ADAPTABLE** | The interesting boundary is not in the list: **every test crosses the transport in-process** (no socket, no real connection semantics) and **the test and the application share one database session**, so the application's own session lifecycle, commit and rollback are never the ones under test. "Presupposing a stand-in produces a false pass, and so does presupposing its absence" is TRUE. |
| 5 | The harness as a system | **TRUE** | The three-question preamble is already the best in the file. Live: the session-scoped schema fixture only runs if requested; per-worker isolated databases are built from an env var the canonical invocation never sets, so that branch is never taken; loop scopes are pinned to one loop per session; the dev overlay **disables both health probes and the read-only root**, so the configuration most tests see is not one the product ships. "Two helper universes separated by an execution model neither can cross" is TRUE and stronger: the two suites share no fixture, no assertion vocabulary, no coverage measure. |
| 6 | Reproducibility and debuggability | **TRUE** | "Order-independence is a per-test property, not a suite property" applies to the module-level engine / session-factory / work-queue singletons plus the session-scoped loop. The session-finish hook **deletes every file in a shared temporary directory at zero age** — a test mutating state another test depends on. "A test that reads the same clock, the same ambient environment … as the code it exercises" — the suite sets a dozen env defaults at import; a test asserting on configuration reads what the fixture just wrote. |
| 7 | What actually blocks a merge | **ADAPTABLE** — highest-value block | **FALSE PREMISES:** "translation completeness" and "scheduled suites" (neither exists); the scanner exists only as a host script needing an externally installed tool, invoked by nothing. **TRUE and large:** there is no automation directory at all, so nothing is a merge gate in any enforced sense; the aggregate gate chains lint, type check, client lint and client tests and **omits the backend suite entirely**. The four-absence list is the right list — keep it, re-derived. |
| 8 | Declared test-layer contracts | **TRUE** | Live: the opt-in fixture's docstring claims it does not patch the rate-limit decision — true, but it uses the same substitute whose expiry is inert, so a test asserting expiry behaviour asserts against a store that cannot expire. A substitute's asynchronous close where the real client's is synchronous. A fixture whose docstring says it exists "to satisfy the type checker" — a double serving the checker, not a behaviour. |

## 1.3 Proposed final block set (9 blocks)

1. **Decisions the product acts on, and the value of each an assertion would reject** — derive the
   decision set from the code, not from any list; for each, name the input value that would make an
   existing assertion fail. A shared assertion holding for every value the decision can take
   discriminates nothing, and a parameterised table asserting one shared postcondition is the same as
   an empty assertion.
   *Evidence: the derived decision set with a per-decision verdict; one decision whose effect no assertion can observe; one test whose assertions survive the decision being inverted.*
2. **What each stand-in removes, and whether any test observes it elsewhere** — build the inventory from
   what tests actually replace, not from a declared convention. Standing in for an external transport is
   correct; standing in for the mechanism that enforces an ordering, a lifetime or a decision leaves that
   property untested while looking tested. Include the substitute installed for every test by default and
   the opt-in one that contradicts it.
   *Evidence: the stand-in inventory with the property each removes and its install scope; one property observed by no test; one stand-in installed globally that a single test contradicts.*
3. **What the harness manufactures by default: identity, store, schema, environment** — establish what
   states, values and configuration the shared fixtures supply, whether the product can produce each, and
   what stays green precisely because it cannot. Cover the manufactured identity (its role, and whether
   the access decision short-circuits for that role) and the manufactured store separately from the
   schema: a default identity that bypasses a whole class of decisions means no test observes that class.
   *Evidence: the default-state inventory with a producible/unproducible verdict; the restated fixed values; the constraints the fixture layer absorbs; the decisions the default identity cannot observe.*
4. **Each boundary, from each side — including the ones every test crosses the same way** — establish
   what is asserted from each side of each boundary, including the in-process transport and the shared
   database session. Establish first whether a stand-in for a shared resource is in use: presupposing one
   produces a false pass and so does presupposing its absence.
   *Evidence: the boundary inventory with a per-side assertion verdict; the boundaries asserted from one side only; cross-references to findings owned elsewhere, each with the test that gates remediation.*
5. **The harness as a system: schema build, isolation model, marker wiring, and the two suites** — how
   the schema is built, what reference state is restored, how parallel execution partitions and isolates,
   what bounds a runaway query, what each registered marker is wired to, and what the invocation's
   substitution semantics cost. Then the deliberate arrangements as claims to verify, and which tests the
   harness cannot currently host.
   *Evidence: the schema, reference-state, isolation and marker-wiring facts; the override-substitution delta; the deliberate arrangements with what holds each in place; the tests the harness cannot host and the gap each names.*
6. **Reproduction: what varies per run, and what a shared resource carries forward** — what varies and
   whether the variation is recorded where a reader of the log finds it, what is unbounded while a test
   runs, what a parallel run does that a serial run does not, what a reused resource carries into the next
   run. Do not settle for running the suite twice and comparing; order-independence is per-test.
   *Evidence: the per-run variable inventory with what is recorded and where; the unbounded resources and their owners; the process-wide state a test shares with production code; what a reused resource carries between runs; the recovery procedure for a red automated run.*
7. **What runs before a change lands, and what each gate's scope excludes** — for each declared gate,
   whether it is loaded, whether it is green, what its scope excludes, **and what invokes it**. Four
   absences are distinct (declared and never loaded, loaded and red, scope omits a whole process tree,
   configuration never read from the directory it runs in), and an aggregate entry point a person must
   choose to run is a report, not a gate — a target chaining several checks while omitting one is the case
   to find. The population of production-code diagnostics is 08's.
   *Evidence: the gate inventory — loaded or not, green or not, scope, and what invokes it; the gates whose scope excludes a process tree; the aggregate entry point with the check it omits.*
8. **What a coverage measure can actually see** — before a coverage number is quoted, establish which
   configuration it read, from which working directory, what it omitted, which process trees are absent,
   and whether the threshold it is compared against is a per-language floor or a whole-project one.
   *Evidence: each coverage artefact with its effective source selection, its threshold, and the population it cannot reach.*
9. **Declared test-layer contracts, and whether anything holds them** — whether each property the test
   layer asserts about itself is true of the code it describes and whether anything checks it. A comment
   describing the harness differently from how the harness behaves is a finding here. A registered marker
   is not evidence of use and a used marker is not evidence of justification; a helper nothing calls is a
   question of purpose, not of deletion. Production-code convention and dead code are 08's.
   *Evidence: the declared-property inventory with a holds/does-not-hold verdict; one comment the code contradicts; one assertion about configuration whose failure modes are not the ones it appears to guard.*

**REMOVED / MERGED.** No block deleted outright. Old b3 folded into new b3 with the foreign nouns
replaced. Old b7 **split** into new b7 and b8 — the gate inventory and the measurement's effective scope
produce different artefacts and are independently executable. **REMOVED:** "translation completeness" and
"scheduled suites" as gate classes (no translation catalogue, no scheduled suite); their absence is 08's
and 10's.

## 1.4 Scope Boundaries paragraph (exact text)

> Scope Boundaries — this phase owns whether the suite would notice a wrong product decision, the fidelity
> of what it asserts once it does, the harness as a system, and the gates that run before a change lands
> together with their effective scope. Other phases own: production-code convention, fixed-value discipline
> and dead code (08); the deployed container, its health contract, backup and restore, the operator's log
> stream and the operational runbooks (10); measured latency, throughput and per-request cost (11);
> per-request authorization decisions and what a refusal discloses (12); transaction, lock and pooler
> semantics (03); the migration chain, index inventory and schema drift (14); parse, aggregate, full
> recalculation and temporary-file lifetime (05); settings values, secret provenance and environment
> policy, including the configuration the harness supplies (02); client-side component, state and
> accessibility behaviour and that suite's own architecture (13); namespace rulings and cross-phase
> conflict resolution (99). The merge-blocking question — whether a change can reach a deployed system at
> all — is this phase's for the suite and the aggregate entry point, and 10's for the deployment path;
> neither files the other's verdict.

## 1.5 Prefix and Report Output

Prefix: **`TST-`** (unique; keep).

```
## Report Output

- Findings path: `.ai/audit/09-test-coverage/findings.md` — cumulative: a new run appends or supersedes, it does not restart
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `TST-` — already minted in a prior cycle, with at least one identifier resolving to two different findings; check for a collision before minting an ID and report it rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting the current behaviour as intended is still filed as a finding, with the test recorded as a remediation blocker
```

---

# 2. `10-audit-production-ops.md` → Phase 10 — Production Operations

## 2.1 Current state

What the deployed system is made of, what decides its content, what a restart and a revert must
re-establish, what an observer is told when something is wrong, and what a failure costs in data.
**12 blocks.** `name: 12-production-ops` ≠ stem `10-audit-production-ops` — F-1. Title carries
"Security & Observability" — the security half belongs to 15; drop it.

## 2.2 Premise audit

| # | Block | Verdict | Evidence / replacement |
|---|---|---|---|
| 1 | Container runtime posture | **TRUE** | Exact match. "Merged production definition rather than in one manifest alone" is load-bearing and correct: the dev overlay **disables both health probes and the read-only root and relaxes the privilege posture**, so the stack a developer and an auditor run is materially less restricted than the deployed one. The one-shot schema step receives the administrative credential — the largest privilege in the topology, granted deliberately with a comment. |
| 2 | What decides the artifact's content | **TRUE** | Two classes locked (lockfile-enforced installs for both ecosystems); base images and the toolchain bootstrapper are floating tags and an argument with a default. Sharpest instance: **the same build target is built twice with different build arguments** — the app service passes the toolchain version, the one-shot and worker services build the same target without it. "Whether an automated updater covers that class": one host script, externally-installed scanner, invoked by nothing. |
| 3 | A control that runs, reports clean, examines nothing | **TRUE** (C6 — F-5) | Discipline right, population different. The deployed surface's controls are: the per-service probe declarations, the one-shot migration acting as a start-order gate, the host scanner script, the backup and restore entry points, and a setting that decides whether a dependency outage denies or admits. Bind to the deployed surface; reference the shared angle by name. |
| 4 | What makes a check a gate | **TRUE** | Applies verbatim and is the file's sharpest block. No automation directory exists; every gate is an entry point a person must invoke. The aggregate entry point chains several checks and **omits the backend suite**. "Whether credentials reach components that run before the gates" — the one-shot step receives the full credential set. |
| 5 | Deployment provenance and service coverage | **TRUE** | Strong: the fronting service is **profile-gated** and never started by the canonical bring-up, and the app service publishes **no host port in the production definition**, so the only ingress is the profile-gated one. Also: the built client bundle exists **twice** — baked into the app image *and* bind-mounted into the fronting service from the host tree, which is not versioned. "Updated by the forward path but not the revert path" is TRUE and total: no artifact is ever tagged. |
| 6 | Rollout and rollback under a real restart | **ADAPTABLE** | "Fronting tier re-resolves the address … or keeps the one it resolved when the component behind it was recreated" is **TRUE and exactly this repo's failure mode**. "A success gate run from inside the component being verified cannot observe the tiers in front of it" is TRUE. **FALSE PREMISE** in the rollback half — no versioned artifact exists to revert to. Replacement: what a **partial** restart re-establishes, and what a completion-gated one-shot step does when only part of the stack is recreated. |
| 7 | The health contract | **TRUE** | Real divergences: the serving probe consults one dependency and nothing else; the worker's probe tests its **store's** reachability, not its own liveness, so a dead worker is healthy; the detailed variant is reachable with no credential and returns a filesystem path plus, on failure, a raw dependency exception string; the dev overlay disables both probes. |
| 8 | Edge tier: transport, certificates, exposure | **TRUE** | The TLS block exists only as a commented template; the listening socket is plaintext-only. "What the tier does when the material is absent" resolves to: no material, no negotiation — and the configuration declares a credential transport attribute whose production default is **stricter than the only transport the deployed topology offers**. The upload body ceiling in the fronting config is coupled to a backend setting by a **comment** and nothing else. |
| 9 | Backup consistency and durability | **TRUE** | The dump is written inside the database container's own filesystem, copied into a directory inside the working tree, and **the copy's result is not examined**. "Where it physically lives … and whether the loss event it exists for also destroys it" — the copy-out is the mitigation and lives where a workstation loss takes it. "Judged by what it changes rather than by what its name suggests" — the owner-restoring defaults. "Whether the effective interval matches the nominal one": there is no interval; the entry point is invoked by hand. |
| 10 | Evidence that a backup restores | **TRUE** | Sharpest block in the file. No rehearsal path exists, and the restore entry point **does not examine its own result**, so a failed restore reports success; it also runs object-dropping options against the live database. The recovery objectives are nowhere stated. |
| 11 | Observability end to end | **TRUE** | "An alert expression over a series no component emits is not an alert" generalises to: there is **no metrics surface at all**. "Whether every log path reaches the same structured, redacting output" — the formatter has **no redaction step**, and one unauthenticated intake surface writes caller-supplied text *and* caller-supplied structured fields straight into the error stream. **FALSE PREMISE**: "the tracking client's own initialisation" — no tracking client. Replace with the fronting tier's access/error streams and the log file's lifecycle inside a restartable container. "Measuring latency belongs to the performance phase" — keep, now 11. |
| 12 | Runbooks and operational documentation | **TRUE** | Richest instance in the set: ~45 documentation files include a guide for migrating a work queue off the in-process mechanism that is actually live, while a second container runs a different persistent mechanism **that nothing feeds**. A documented entry point that "prints resolved config" emits credentials. "Claims about the integration surface are another phase's" — repoint 09 → 07. |

## 2.3 Proposed final block set (12 blocks)

1. **Effective runtime posture per service, after every layer is merged** — establish per long-lived
   service the identity it runs as and the capability, filesystem, privilege and resource restrictions it
   **actually** carries in the merged production definition; an inherited directive and a restated one are
   not the same evidence. Establish what the runtime boundary publishes, which image-level defaults every
   service silently inherits including one-shot containers that never open a probed port, and whether the
   deployment engine in use applies the resource declarations it makes.
   *Evidence: per service — effective identity and restrictions after merge, published ports, inherited defaults; one restriction present in only one of the layered definitions; one declared resource limit the deployment engine does not apply.*
2. **What decides the artifact's content, per input class** — every input that changes the built artifact
   without a source change, with a pin verdict, an integrity verdict, and whether an automated updater
   covers that class at all. Establish whether the same build target is built more than once with different
   inputs, whether the coordinates used to publish, deploy and pull name the same object, and whether an
   artifact that can be reverted to exists at all.
   *Evidence: the external-input inventory with a pin verdict and an integrity verdict each; the build invocations that disagree on an input for one target; the mutability of the revert target.*
3. **Controls in the deployed surface: existence, declared scope, and what they examined** *(shared
   vacuous-control angle, F-5 — do not restate the three questions)* — take every control producing a
   pass/fail signal on the deployed system — a probe, a rehearsal job, a scanner, a schema step acting as a
   start-order gate, a setting that decides whether a dependency outage denies or admits — and establish
   what each is configured to examine and what it examined. Establish what is configured to be enforced
   and which suppressions are sanctioned before judging any result; never infer a missing tool, never
   treat a non-zero issue count as a defect by itself.
   *Evidence: per control — existence, declared scope, the item count it actually examined, and whether any shipped guard would notice a change in that scope.*
4. **What can prevent a change from landing, and what the aggregate entry point omits** — which checks can
   prevent something as distinct from which report: what triggers the automation, what ordering makes a
   verdict reach the artifact, whether the artifact can proceed regardless of a verdict, whether credentials
   reach components that run before the gates, and what overlapping or re-entrant runs do to shared state.
   Where several checks are chained behind one entry point, establish which of them it omits.
   *Evidence: per check — trigger, the dependency that would make it blocking, the path by which a change proceeds with the check failing or never having run; the chained entry point with the check it omits.*
5. **Service coverage and provenance: what the deployment defines, starts, and actually runs** — compare
   the service set the topology defines against the set the deployment path enables: a component defined
   and never started, one gated behind a profile, one the forward path updates but nothing versions. Establish
   which artifact a deployment runs and whether a single built output has two sources of truth, one outside
   version control. Whether a component is gated by design is a decision to read, not a defect.
   *Evidence: the resolved production service list against the list the deployment path enables, with each profile-gated component; the artifact identity per path; any output with two sources.*
6. **Restart and partial restart: ordering, address resolution, and one-shot steps** — what a full and a
   partial restart require to be re-established, in what order, and what an external observer experiences;
   whether a fronting tier re-resolves the address it forwards to or keeps the one it resolved when the
   component behind it was recreated; what a success gate exercises relative to the path a client takes;
   what a completion-gated one-shot step does when only part of the stack is recreated.
   *Evidence: the boot-order and address-resolution dependency chain after a full and a partial restart; the components outside the success gate; whether a revert target exists.*
7. **The health contract an observer can act on** — which signals exist, which gate, which merely inform,
   and whether each is **enabled in the deployed configuration** rather than merely available. Where a
   dependency's liveness is staged before the hard one, establish its default and freshness rule against
   the shipped configuration. Establish whether a wedged process is distinguishable from a healthy idle
   one, whether a restart threshold can flap the boot chain, what an unauthenticated caller learns from
   each signal, and what a default probe reports for a container that never serves the probed port.
   *Evidence: per signal — endpoint, gating or informational, enabled state in the deployed configuration, the disclosure a caller receives; one condition that answers healthy for a broken process.*
8. **The fronting tier: transport security, certificate lifecycle, and what is exposed** — how the tier
   resolves the address it forwards to and whether that survives the address changing; which requests reach
   a control and which bypass it, including limits declared in one tier and coupled to a setting in the
   other by nothing stronger than a comment; how transport is negotiated, and the certificate lifecycle end
   to end, including the case where the configuration declares a material that is never provisioned.
   *Evidence: the resolution model and its behaviour when the address behind it changes; the request-path × control matrix; the cross-tier limits with what couples them; the certificate's origin, lifetime, renewal path, and behaviour when missing or never provisioned.*
9. **Backup: consistency, durability, and what each option changes** — whether each artifact is internally
   consistent when taken, and separately whether it survives the loss of what it protects: where it
   physically lives, on which device, and whether that loss event also destroys it. Establish what each
   option passed to the backup tool does **judged by what it changes**, whether the effective interval
   matches the nominal one, whether old artifacts are removed, whether a job that stops is noticed, and
   which durable state has no backup at all.
   *Evidence: per artifact — what it is taken from, what it is written to, the location relative to the thing it protects; each backup option with the behaviour it changes; the effective interval and retention mechanism; the durable state with no backup.*
10. **Evidence that a restore works** — whether any path exercises a backup artifact that was actually
    taken rather than one generated moments earlier from a database it also just created; a rehearsal that
    restores its own input proves nothing, and surviving the loss of what it protects is not evidence that
    it restores. Establish whether the restore path examines its own result, and what would have to be
    true for the stated recovery objectives to hold.
    *Evidence: for the rehearsal path — the origin of the artifact and the origin of the data inside it; whether the restore's outcome is examined; the recovery objectives with the state of each precondition.*
11. **Signals produced, signals consumed, and the log paths that bypass the structured output** — which
    signals are produced, which consumed, and whether anything in the deployed system consumes them; an
    alert expression over a series no component emits is not an alert. Establish whether the documented
    collection path is reachable from where a collector would sit, whether a condition that matters has any
    signal, and whether an operator has a channel that would tell them. Establish whether every log path
    reaches the same structured output, including an intake surface accepting caller-supplied text and
    caller-supplied structured fields, the fronting tier's own access and error streams, and the redaction
    question the formatter does not currently answer. Measuring latency is 11's.
    *Evidence: the signal inventory with produced/consumed verdicts; one alert expression against a series the system does not emit; the paths by which a log line can bypass the structured output or inject into it.*
12. **Operational claims as testable artefacts** — whether the procedures a responder follows would run as
    written on the host they would run on: required state, credentials, files, assumed tool versions. Then
    whether each operational claim in the deployment, rollback, restore and incident corpus — a control that
    is live, a cadence, a value, a path, a mechanism documented as being migrated away from — is still true
    of the system as deployed. Treat a comment, a docstring and a runbook line as claims to test against
    the executing path; documentation describing a different system is itself a finding. The external
    integration surface is 07's.
    *Evidence: the operational-claim inventory with a true/false verdict each; one procedure with the step that fails on the deployed host and why.*

**REMOVED.** Nothing deleted; two obligations rewritten. Block 6's rollback half is **REMOVED as phrased**
("whether a revert restores a whole-stack known-good state" — no versioned artifact exists to revert to) and
replaced by the revert-target question in b2 and b6. Block 11's tracking-client failure mode is **REMOVED**
(no such client) and replaced by the fronting tier's log streams and the intake surface. Block 3's
three-question paragraph becomes a reference to the shared angle (F-5).

## 2.4 Scope Boundaries paragraph (exact text)

> Scope Boundaries — taken in: the health, liveness and readiness endpoint and probe contract (from 01),
> and the fronting tier, transport security and certificate lifecycle (from 07, 02). This phase owns the
> deployed composition: effective container posture, artifact provenance, the controls that decide what
> lands, service coverage, restart, the health contract, the edge tier, backup and restore, the operator's
> signal stream, and the operational corpus. Deferred: which origins and which cookie attributes are
> honoured, per environment → 02; which surfaces a per-request gate reaches and what it returns, and
> whether the server re-checks what the browser already enforced → 12; the schema chain, index inventory
> and drift → 14, this phase owning only the one-shot step's completion condition; secret values and
> settings provenance → 02; pooler configuration semantics → 03, owning only whether the production path
> enables the pooler at all; measured latency, per-request cost and the ceiling each tier implies → 11;
> production-code convention and dead code → 08; suite adequacy and a gate's scope-as-test-coverage → 09,
> this phase owning only whether a control exists and runs in the deployed path; client bundle composition
> and client-side security posture → 13; outbound and inbound integration contracts → 07; namespace rulings
> and cross-phase conflict resolution → 99. Neither this phase nor 09 files the other's verdict on a gate.

## 2.5 Prefix and Report Output

Prefix: **`OPS-`** (unique; keep).

```
## Report Output

- Findings path: `.ai/audit/10-production-ops/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `OPS-` — already minted in a prior cycle, with at least one identifier resolving to two different findings; check for a collision before minting an ID and report it rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting the current behaviour as intended is still filed as a finding, with the test recorded as a remediation blocker
```

---

# 3. `11-audit-performance.md` → Phase 11 — Performance

## 3.1 Current state

What the system costs per request, per event and per scheduled run, whether those costs are bounded, and
whether the numbers the system believes about itself are measured or asserted. **11 blocks.**
`name: 13-performance` ≠ stem `11-audit-performance` — F-1.

Most foreign of the four. Written around a **read-through cache** (b4, b5, b6), an **event-driven inbound
process** (b8, b10, b11), a **full-text search path** (b1) and a **second web tier** — none exist. Two
blocks are false premises outright, and the two blocks describing machinery this project genuinely has
(b7, b8) carry the vaguest prose.

## 3.2 Premise audit

| # | Block | Verdict | Evidence / replacement |
|---|---|---|---|
| 1 | Response budgets | **ADAPTABLE** | "A declared target no alert watches" survives and is true — no latency objective is declared anywhere. "An alert pinned to one path while a busier path has none" is **FALSE PREMISE**: no alerting exists. Rephrase as the absence with a reached/un-reached verdict, and merge b2 in. |
| 2 | A gate that reports green and decides nothing | **TRUE premise, vacuous population** | No latency gate, no query-shape gate, no load gate exists. The discipline is right; the subject is empty, so the finding is the emptiness. Per F-5 the shared angle here is **removed** (10 and 09 own the live instantiations) and merged into b3. |
| 3 | What the performance discipline actually exercises | **TRUE** | Best-fitted block as written. Live: no load profile, no profiling harness, no benchmark plugin; the suite's registered markers mean something else entirely. "A harness requiring a volume no shipped environment reaches" has a direct instance — the test store recreates a schema per run and the largest fixture is a ten-row CSV. |
| 4 | What a cache key encodes and what a version token retires | **ADAPTABLE** — full reframe needed | There is **no read-through cache**. The equivalent is precise and real: one shared transient store simultaneously holding the persistent work queue, the per-credential revocation list, the per-identity revocation set, one-time credential material and rate-limit counters. Key-composition and lifetime questions transfer and are sharper: each marker's lifetime is set from a token lifetime, and the per-identity marker is written with the longer of two configured lifetimes — a choice, not a property of what it retires. **Add** the single failure domain: one outage disables revocation, rate limiting and one-time credential retrieval simultaneously, and their failure modes differ. **Delete** the three-way split with the old 08 and 14 (neither subsystem exists). |
| 5 | Cache behaviour across processes and backends | **ADAPTABLE** | Stronger than written. "What the deployed backend provides that the environment the shipped guards run in does not" is TRUE and decisive: the suite substitutes the store unconditionally, and **the deployed application service does not declare the store's address in the production definition at all**. "An invalidation utility behind a capability guard is a working invalidation in one environment and a logged no-op in the other" maps onto the fail-open/fail-closed setting. |
| 6 | What a hit and a miss cost | **FALSE PREMISE** | No read path is served from a cache, so there is no hit path, no stampede, no single-flight, no loser instruction. **REMOVE** — nothing in this project has an equivalent. |
| 7 | Query cost under caller-controlled input | **TRUE** — strongest block, weakest wording | The real mechanism is a **document-valued column** and a **caller-supplied selection parsed into an unbounded number of equality predicates**, one per key, ANDed together. "A join tree whose inner scan stays constant while the rows above it multiply is not readable from any single plan node" is the right judgement rule; the shape is a predicate list, not a join tree. "Whether a bound exists … and whether growth is additive or multiplicative" is the right ask, and no bound exists on key count, key length or value length. The declared access path is over the whole document, which a scalar extraction cannot use. |
| 8 | Per-object and per-event work | **TRUE** | "Prefetch detection that cannot fire for the relation shape it tests" is **FALSE PREMISE** (no prefetch API in use). The equivalent is stronger: **every collection on the primary aggregate is eagerly loaded on every read of it**, including the document-valued rows and the processing-log history, regardless of what the caller asked for, and a list conversion runs per row. "Whether a per-object cost is paid once per rendered row" is the right ask. |
| 9 | Serialisation and materialisation per request | **TRUE** | "A reference set materialised into every request by shared context" is TRUE via the eager-loading configuration. "A hierarchy rebuilt per request where a cached rendering already exists" is **FALSE PREMISE** (no cached rendering). The surviving strong question — unstated anywhere in the file — is **pagination**: no list surface bounds its result, and one returns every document-valued row for an aggregate. |
| 10 | Background and batch work | **ADAPTABLE** | "Expressible as a set operation or issued per row" applies to the batch write that deletes an aggregate's rows and inserts the replacement in one transaction; "how wide the transaction is, and what it holds" applies. **FALSE PREMISE** in the premise sentence: no scheduled or one-shot run competes with live traffic — the periodic maintenance is an in-process coroutine. "Safe to run twice" → 03, correct. |
| 11 | The ceiling each tier imposes | **TRUE** — should lead the file | Live and severe: the serving worker count is a literal in the start command; the connection pool is four literals in the engine factory with no setting behind them; the topology's declared CPU and memory allocations are the only numbers a derivation could read, and the deployment engine in use does not apply them; the store's own connection ceiling is nowhere configured. "Whether that request is CPU-bound or I/O-bound" is the right ask. **FALSE PREMISE**: "one shared bounded worker thread" — there is no thread pool; the concurrency model is one execution context per process, which makes the same question sharper in a different direction (see NEW b8). |

## 3.3 Proposed final block set (10 blocks)

1. **Stated objectives, and what acts on them** — which request paths carry real traffic and which carry a
   budget: a declared target nothing measures, a constant written once and read in more than one place, a
   threshold compared against a literal restated beside the value it should track. Establish whether any
   measurement behind a stated target is a distribution rather than a single sample. Where no target is
   declared at all, that is the finding, stated as such.
   *Evidence: the objective inventory with the path each covers against the paths carrying traffic, or its absence; the declared constant against the value each consumer compares; one target nothing acts on.*
2. **The performance discipline that exists, and the one that does not** — what the shipped instruments
   cover: which request shapes a load profile reaches and whether each target resolves to a route, what
   dataset volume they require, which production query shapes a profiling path builds and omits. A harness
   requiring a volume no shipped environment reaches, one spending its journey on responses that return
   early, and no harness at all are each a discipline in name only; where no such control exists, record the
   absence with a reached/un-reached verdict rather than omitting the question.
   *Evidence: the instrument inventory with a reached/un-reached verdict; the load profile's target inventory with a resolves verdict each where one exists; the volume any harness requires against the volume any shipped environment creates.*
3. **The shared transient store: what each key encodes, who owns its lifetime, what retires it** — what
   every key encodes and omits, and each marker's lifetime against the lifetime of what it retires: a marker
   expiring while the credential it retired is still live restores a version already left behind, and a
   marker whose lifetime is the longer of two configured lifetimes is a choice, not a property. Establish
   whether a key carrying caller-supplied segments varies wherever a caller can vary it, whether two
   concurrent readers resolve one key differently, and the single failure domain — which of the store's
   distinct jobs stop working together when it is unreachable and what each one's failure mode is. Claims
   that bump-based invalidation makes retired entries unreachable rather than globally wiped are claims to
   confirm or refute, not the design to assume. **Split declared identically in 04, 10 and 11: this phase
   owns key composition, marker lifetime and concurrent resolution; 04 owns what a revocation key must be
   able to express; 10 owns the store as an operational dependency and its unavailability mode.**
   *Evidence: the key inventory with encoded and omitted components and the owning job; each marker's lifetime against the lifetime of what it retires; one outage that disables two jobs whose failure modes differ.*
4. **The store in the deployed configuration, against the one the shipped guards run under** — what the
   deployed store provides that the environment the shipped guards run in does not, and whether the
   invariants are regression-locked only under the substitute; a test's fidelity to the deployed
   configuration is part of what it proves, and a guard's own description of a limitation it never exercises
   is evidence about the system, not a defence of it. Establish what the production path actually points
   the store client at and what each process declares. *(Targeted deferral: fixture substitution as such is
   09 b2; this block asks only what the deployed path resolves to.)*
   *Evidence: the deployed store address and connection settings per process against the substitute's capabilities; one guard asserting a behaviour the deployed store cannot exhibit.*
5. **Query cost under caller-controlled input** — what a statement does as the caller widens a filter: a
   caller-supplied selection parsed into one equality predicate per key with no bound on key count, key
   length or value length, applied to a document-valued column through a scalar extraction no declared
   access path on that column serves. Establish whether growth is additive or multiplicative — a predicate
   list whose element count is caller-controlled and whose per-element cost is not constant is not readable
   from any single plan node — and whether the declared access paths are the ones the code's queries use.
   *Evidence: the cost curve against a widening filter with the item count at each point; the bound in force on the caller-supplied selection or its absence; one predicate the declared access paths do not serve.*
6. **Per-request materialisation: eagerly loaded collections and unpaginated result sets** — what is pulled
   regardless of page size: every collection configured to load eagerly on the aggregate the request
   touches, whether the request needs it, and the row count each carries; a conversion run per row; a set
   fetched twice on one path. Establish what a request transfers per page view, and on every list surface
   whether a bound on the number of rows exists at all. Establish whether a cost negligible at a shipped
   fixture's scale is bounded by design or only by an assumption that will not hold.
   *Evidence: per-request materialisation volume with the row count each eagerly loaded collection carries; a set fetched more than once on one request; per-page-view payload and element counts; the list surfaces with a row bound and those without; the fixture's scale against the bound, if any.*
7. **Background and batch work: cost, transaction width, and lock hold** — what a run costs against
   production data volume rather than a fixture's, whether the work is expressible as a set operation or
   issued per row, and whether the statement count scales linearly with the table. Establish how wide the
   transaction is — a delete-then-insert against the whole of one aggregate in a single transaction — what
   it holds, and what a live request does while it holds it. What the periodic maintenance run costs is
   this phase's; whether it is safe to run twice is 03's.
   *Evidence: per run — statements issued, wall time, and the item count the cost scales with; the transaction's width and the locks held; one run whose duration competes with a live request.*
8. **`NEW` — Work that executes inside the request tier** — establish which work the system defers to a
   background process and where it actually runs: the deferral mechanism, the consumer, and the process each
   consumer belongs to. Establish what that costs the tier that serves requests — whether the deferred work
   occupies the same execution context as request handling, whether it is bounded, what a restart or a
   redeploy does to work already accepted, and what state a client is told to expect while it is pending.
   Establish whether a component deployed to take that work receives any, and treat a deployed component
   nothing feeds as a finding, not as headroom. The mechanism carrying work across the loop boundary is
   01's; the consequence in latency, memory and lost work is this one's.
   *Evidence: the deferral mechanism with its consumer and the process each belongs to; one accepted unit of work lost on restart; one deployed component with nothing enqueued to it.*
9. **`NEW` — The cost of the stored document shape** — what the chosen storage shape costs on both sides:
   the write cost of replacing a whole aggregate's rows inside one transaction, the read cost of returning
   two document-valued columns per row, the storage cost of a uniqueness constraint expressed as a
   serialised form of the dimension document, and the index cost of a declared access path over that column.
   Establish whether the declared access paths are the ones the queries can use and whether a constraint
   expressed as a serialised form compares whole documents to decide uniqueness. This is the consequence of
   a decision already made, not a defect to attribute; the finding is a cost that is real and unmeasured.
   *Evidence: the storage-shape inventory with the write, read, storage and index cost of each element; the access paths the code's queries can actually use against the ones declared; the measured cost of one aggregate at two volumes.*
10. **The ceiling each tier imposes** — per long-lived process, what bounds concurrent work: the worker
    model, whether the worker count derives from the declared allocation or is a literal, and whether that
    allocation is one the deployment engine in use actually applies. Establish what a representative
    request's cost implies and whether it is CPU-bound or I/O-bound, because only one answer responds to
    more workers. Establish the same for the background process, including the concurrency model it
    actually uses and what bounds how long work waits for it, since an unbounded wait is a latency property
    rather than a mechanism question. Multiply the connection ceiling by the process count and compare it
    with the store's own ceiling. Not how the pooler is configured (03's), and not whether the production
    path enables it (10's).
    *Evidence: per process — worker model, the ceiling it implies, the source of the worker count against the declared allocation, and whether that allocation is applied; the CPU/I-O split of a representative request; the concurrency point in the background process and any bound on the wait; the connection count the serving tier can reach against the store's declared ceiling.*

**REMOVED.** Old b6 ("What a hit and a miss cost") is **REMOVED — false premise**: no read path is served
from a cache, so hit cost, stampede and single-flight have no subject. Old b2 is **REMOVED as a
standalone** and folded into new b2, because the population is empty and a block whose target is empty must
evidence the absence (B10) rather than enumerate nothing. The three-way cache-key split with the old 08 and
14 is **REMOVED — both refer to subsystems this project does not have** — replaced by the two-way split with
04 and 10 declared in new b3.

## 3.4 Scope Boundaries paragraph (exact text)

> Scope Boundaries — this phase owns the measurable consequence of latency, throughput and capacity, and the
> cost of a storage and processing shape already in place. It owns nothing else. Owned elsewhere: the
> connection pooler's configuration semantics, lock and transaction semantics, and whether a maintenance run
> is safe to run twice (03); whether the deployed path applies the resource declarations it makes, and the
> store's availability as an operational dependency (10); the mechanism that defers work and the process
> topology it hands it to (01); parse, transform, aggregate determinism, full recalculation after re-upload
> and temporary-file lifetime (05); the schema chain, index inventory against query predicates, and schema
> drift (14); per-request authorization decisions and what a refusal discloses (12); production-code
> convention and dead code (08); the settings that bound any of the above (02). With 04 and 10: this phase
> owns the composition of every key held in the shared transient store and the lifetime of each marker; 04
> owns what a revocation key must be able to express; 10 owns the store as a dependency an operator must
> know is load-bearing. The two deferrals this file previously carried — to a full-text search path and to a
> per-language key component — are withdrawn: neither subsystem exists in this system, and if either is
> introduced, this phase takes key composition and measured cost and the other phase takes the result set.

## 3.5 Prefix and Report Output

Prefix: **`PERF-`** (unique; keep).

```
## Report Output

- Findings path: `.ai/audit/11-performance/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `PERF-` — already minted in a prior cycle, with at least one identifier resolving to two different findings; check for a collision before minting an ID and report it rather than creating a second namespace
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting the current behaviour as intended is still filed as a finding, with the test recorded as a remediation blocker
```

---

# 4. `12-audit-authorization.md` → Phase 12 — Authorization

## 4.1 Current state

What an access decision returns — which surfaces an identity may reach, what each refuses, and where two
processes agree or do not. **11 blocks.** `name: 15-authorization` ≠ stem `12-audit-authorization` — F-1.
Title "Authorization & Access Control" — the second half is redundant.

Least foreign in premise, most dangerous in practice: it names the right questions, and this codebase
contains a live instance of its b3 counter-case (a surface whose own documentation claims a privilege the
executing path does not enforce) and of its b4/b6 (a mutation entry point receiving no acting identity).
What is foreign is the nouns: the framework's own administrative interface, the two processes, the
event-driven pre-action gate, the media unit, the request-forgery exemption set.

## 4.2 Premise audit

| # | Block | Verdict | Evidence / replacement |
|---|---|---|---|
| 1 | The access-level representation, and where decided | **TRUE** | Exact match. Two independent sources of authority coexist — a **global role attribute** and a **per-aggregate grant row**, same three levels — and the role wins outright, short-circuiting the grant lookup for the top level. **Three** implementations of the same ordering coexist (an ordered list indexed by position, an unused module mapping, a mapping redefined inside the check). Several surfaces re-derive the verdict inline rather than calling the shared check. |
| 2 | What the representation can and cannot distinguish | **ADAPTABLE** | "Whether the framework's own permission machinery connects to that representation or bypasses it" is **FALSE PREMISE** — no declarative permission layer; the guards are hand-written dependency functions. Replacement: what the vocabulary cannot express, and **which guards are declared and never installed** — a read gate, a write gate and an administrative gate are defined for the same aggregate and only the read gate is installed, every write surface re-implementing inline. "A class that overrides no permission at all" is live: the lowest-privilege gate's whole body is a pass-through. |
| 3 | The privileged surfaces, and the predicate each | **ADAPTABLE** | "The framework's own administrative interface, the per-model overrides inside it" is **FALSE PREMISE** — no administrative UI or registry. Replacement: the administrative API surface, a privileged path that hands off to a second gate, a maintenance invocation, and **any surface whose own description claims a privilege the executing path does not enforce**. That counter-case is the most valuable sentence in the block and this codebase is a textbook instance: the access-management surface declares in its module docstring and in every endpoint description that it requires the top role or the owner, installs no such guard, and the service methods it calls perform no caller check either. |
| 4 | Ownership on every single-object path | **TRUE** | Best-fitted block. Live: the aggregate's creator column is nullable and **no access decision consults it** — ownership exists only as a grant row written once at creation; and one read path resolves a child by its own bare identifier **without constraining it to the parent named in the path**, then returns that child's name, type and configuration to a caller authorised only for a different aggregate. "A path that resolves an object without consulting its caller is a path, not an exception" is exactly right. |
| 5 | Ownership on collection and multi-object paths | **ADAPTABLE**, mostly empty | "Bulk actions, batch endpoints" are **FALSE PREMISE** — no multi-object mutation surface exists; establishing that is worth stating. Surviving questions are live: whether the restriction is part of the query or applied row by row, and whether the **same identity** gets different answers from a list and from a single read — which happens, because one branch of the list deliberately takes a different path for the top role while the single read short-circuits earlier. |
| 6 | The seam that receives an identity it does not read | **TRUE** | Sharpest block, and live: the service layer's mutation methods take **no acting-identity parameter at all** — the caller's identity reaches them only when a route has pre-checked, making every callee trust its caller by construction. "A creation path handed an owner value it never reads" — the creator column is written and never read. A nominally private member is called from outside its module. |
| 7 | Which account state is consulted, where, in which process | **TRUE**, process noun removed | Real states: active/inactive, the pending-password-change flag, per-credential and per-identity revocation. Live: the pending-password-change flag is returned to the client and **no server-side surface enforces it** — the decision is delegated to the browser; and the per-identity revocation marker written at deactivation is never cleared on reactivation. Small unauthenticated set: health signals, the client-error intake, login and registration, credential redemption. "A sender authenticated where they arrive over a network" adapts to: the abuse-limit key on intake and redemption is derived from the immediate peer, which behind a fronting tier is the proxy for every caller. |
| 8 | Whether the two processes reach the same verdict | **ADAPTABLE** — retitle, do not delete | "The two processes" is **FALSE PREMISE** — no second process makes access decisions. But the question is real and sharper: the codebase has **two parallel implementations of identity resolution**, differing on whether account activity is consulted and on whether revocation is mandatory when the store is unreachable. "Compare them by decision and not by name" survives verbatim. "A predicate specified or exported but that neither process calls is part of the answer" is live — the unused write and administrative gates. |
| 9 | The public/owner boundary in both directions | **ADAPTABLE** | "The unit a media object is authorised against" and the whole media half are **FALSE PREMISE** — no media, no listing images, no shared storage reference. Replacement: the **derived-data boundary**. "Whether derived or annotated data on a public object carries owner-private fields" is TRUE and is exactly the live instance from b4 — a chart's configuration and metadata cross the aggregate boundary even where the data rows do not. |
| 10 | What each refusal discloses | **TRUE** | Live and precise: one underlying "no access" verdict is surfaced as **three different error codes** depending on which layer raised it; the handler collapses several to one status; one path embeds the resolved identifier in the body while a sibling does not; the detailed health signal returns a filesystem path plus a raw dependency exception string to an unauthenticated caller. "A deliberately reduced disclosure is a decision to read" is retained. |
| 11 | Cross-site request forgery: what covers which surface | **ADAPTABLE** — keep the block | Not a false premise: a **real ambient credential** exists — a long-lived, script-inaccessible, strict-same-site refresh cookie — and a request redeems it to mutate authentication state. **FALSE PREMISE** in half the body: "which surfaces the check covers, which are exempt" presumes a check that does not and need not exist, because the access-token surface carries no ambient credential at all; the exemption set is that whole surface. Replacement: what the browser attaches and what decides it; whether any server-side origin re-check backs it up; whether the deployed transport can carry the credential when its declared transport requirement is stricter than what the deployment offers. |

## 4.3 Proposed final block set (11 blocks)

1. **The two sources of authority, and which one decides** — establish whether an access level is stored,
   granted or derived: which attributes decide it, which surfaces consult the representation, which read
   those attributes directly. This system has two independent sources, so establish which wins, at what
   point, and whether that precedence is written down anywhere. Where two surfaces reach the same verdict,
   establish whether a construction forces the agreement or it only follows from the same attributes being
   read twice; and how many implementations of the level ordering exist and whether they agree.
   *Evidence: the site the level is decided at, with the precedence rule and whether it is recorded; the attribute set each elevated surface reads, compared; the ordering implementations and any disagreement.*
2. **What the vocabulary can and cannot express, and which gates are declared but never installed** — the
   granularity actually available, whether anything finer than the declared levels can be expressed, whether
   an assignment layer exists that the representation ignores, and how many guards are *declared* for the
   same decision at how many sites are *installed*. A control returning a constant where a decision is
   expected is a finding; a gate correct at its granularity is not. Include a gate whose whole body is a
   pass-through and each inline reimplementation's agreement with the shared one.
   *Evidence: the distinctions available; guards declared per decision against those installed; the gates whose body returns its input; the inline reimplementations and their divergence from the shared one.*
3. **Elevated-privilege surfaces, and the predicate each one actually evaluates** — enumerate every surface
   reachable only by an elevated identity: the administrative API surface, a privileged path that hands off
   to a second gate, a maintenance invocation, and **any surface whose own description or documentation
   claims a privilege the executing path does not enforce**. Establish which are reachable over a request at
   all — a one-shot task has no caller to authorise, and a surface every identity may reach is not
   privileged merely by being listed. Record where each decision sits, and where no decision sits at all.
   *Evidence: surface inventory with the predicate each evaluates, against what admits a caller; a decision reached after the first irreversible step it guards; two gates on one request path; one surface whose documented privilege no executing path enforces.*
4. **Single-object paths: is the caller consulted, and what the response discloses first** — enumerate the
   object types an identity owns, including the collections, derived rows and history rows a user accrues
   without ever being told it owns them, then every path that reads or mutates one by identifier, and judge
   each for an owner or grant comparison. Record what the response discloses before the decision. Do not
   presuppose the enumeration is complete: a path resolving an object without consulting its caller is a
   path; a path resolving a child by its own identifier without constraining it to the parent named in the
   request is one; a creator column written and never read is one.
   *Evidence: owned-type inventory; path × owner-comparison matrix; the paths carrying no owner comparison; the child-resolved paths whose parent constraint is absent, with what each still returns.*
5. **List paths: the restriction in the query, and one identity receiving two answers** — the surfaces where
   one call names many objects, whether the restriction is part of the query or applied row by row, and on
   each list surface whether a bound on the number of rows exists. Then, for one identity and one object,
   compare what the list surface and the single-object surface return, and where a list deliberately takes a
   different branch for an elevated role, whether the single-object path takes the same branch.
   *Evidence: multi-object surfaces with a per-object or per-call verdict and a row bound or its absence; the scoping of each list query; one identity whose list answer and single-object answer disagree.*
6. **Mutation entry points that receive no acting identity** — for every service, helper or job that creates,
   updates or deletes a row, establish whether the caller supplies an acting identity alongside the target
   identifier and whether the callee consults it: a creation path handed an owner value it never reads, a
   deletion path resolving its target by a bare identifier with no owner constraint, a privilege-management
   path whose only inputs are the target and the level to apply. The inventory of such callees is the
   finding. Where a decision precedes a write, the indivisibility question is 03's; the in-module precedent
   is this block's.
   *Evidence: mutation entry points with the identity parameter they accept and whether it is read; the entry points carrying none; a privilege-management path with no caller check at any layer; a decision separated from its write, and the in-module precedent.*
7. **Account state: which states are consulted, on which surface, and by which resolution** — which
   account states exist, which are consulted, on which surfaces, and whether a read surface consults the
   states a mutating one does. For each state, establish whether it is enforced by the server or merely
   returned to the caller, and whether a state set by one path is cleared by the reverse path. Establish what
   an unauthenticated caller reaches and what a caller can influence there, including where the abuse-limit
   key is derived from a peer address a fronting tier makes identical for every caller.
   *Evidence: state × surface coverage matrix, with server-enforced against caller-delegated each; the states set by one path and never cleared; the unauthenticated surface inventory with what each lets a caller influence, and the abuse-limit key each derives.*
8. **The two resolutions of one identity, and whether they agree** — compare by decision, not by name: for
   one presented credential and one account, what each resolution refuses, which states each consults, and
   whether any state one refuses is admitted by the other. Establish whether they are independent
   implementations or one delegating to the other, and which surfaces call which. A predicate specified or
   exported but that no live path calls is part of the answer, as is one re-derived inline where a shared one
   exists. Where a surface exists in one resolution and has no counterpart, say so rather than inferring
   symmetry. Issuance, binding and expiry are 04's.
   *Evidence: state × resolution refusal table; the states one consults and the other ignores; the surfaces calling each; exported predicates with no live caller; one state admitted by one resolution and refused by the other.*
9. **The cross-aggregate boundary: what one aggregate's identifier can reach through another's** — for every
   path taking both a parent and a child identifier, whether the child is constrained to the parent and what
   is returned when the child's own lookup succeeds while the constrained lookup returns nothing: the
   child's name, type and configuration, its derived fields, its private annotations. Establish the unit a
   data row is authorised against and whether a stored document carries fields belonging to the aggregate
   rather than to the row. Storage-artifact ownership is 06's; only reach across aggregates is this one's.
   *Evidence: the parent × child path matrix with a constrained/unconstrained verdict; the fields each unconstrained path returns; the authorisation unit per data row; one document carrying another aggregate's field.*
10. **What each refusal discloses, and where the shapes disagree** — for each refusal class, what the
    response discloses on each surface, whether one underlying decision is answered at different disclosure
    levels on a machine-readable surface than a human-facing one, and whether the identifier being refused is
    echoed back. A deliberately reduced disclosure is a decision to read, not a defect. The finding is one
    decision answered inconsistently across two surfaces with no stated reason, a refusal describing an
    unimplemented scheme, or a signal answering healthy or unreachable while disclosing internals to an
    unauthenticated caller.
    *Evidence: refusal class × surface matrix; the pairs where the same decision is disclosed differently; the stated reason for each divergence or its absence; the unauthenticated signals with what each discloses.*
11. **Ambient credentials: what the browser attaches, what decides it, and what the server re-checks** —
    establish every credential the browser attaches automatically, without a script presenting it, and which
    decision attaches it: an attribute on the credential, a transport requirement, or a server-side check on
    the request's declared origin. For each surface reachable with an ambient credential, establish what an
    attacker's page can cause a signed-in browser to do there and whether any server-side re-check backs the
    browser-side decision. Establish whether the deployed transport can carry the credential at all when its
    declared transport requirement is stricter than what the deployment offers. Which origins and which
    cookie attributes are honoured, per environment, is the policy half and belongs to 02; which surfaces
    carry an ambient credential and whether anything re-checks it is this phase's. Include "no ambient
    credential" as a positive result, not a skipped question.
    *Evidence: the ambient-credential inventory with the decision that attaches each; the surfaces reachable with one and the server-side re-check each has or lacks; the transport requirement against what the deployed path offers; the surfaces carrying no ambient credential.*

**REMOVED.** No block deleted; six retitled with foreign nouns replaced. **REMOVED as false premises:**
"the framework's own administrative interface, the per-model overrides inside it" (b3 — no declarative
permission layer, no administrative UI); "the event-driven process's pre-action gate … how events enter"
(b7 — the background process makes no access decisions); "the unit a media object is authorised against" and
the media half of b9 (no media, no listing images, no shared storage reference); "which surfaces the check
covers, which are exempt" in b11 (no such check exists and none is needed on the header-credential surfaces —
the exemption set is that whole surface). The Scope-Boundary deferrals to the old 05 (content lifecycle),
06 (consent), 07 (media ownership) and 09 (inbound surface form) are **all dropped**: none of those
subsystems exists.

## 4.4 Scope Boundaries paragraph (exact text)

> Scope Boundaries — this phase owns what an access decision returns, on which surface, and the disclosure a
> refusal carries. Other phases own: identity resolution and binding, token issuance and expiry, and
> password and one-time-credential handling (04), this phase owning the per-request gate and neither phase
> filing the same decision; which origins and which cookie attributes are honoured, per environment, and the
> transport-security policy (02), this phase owning only whether the server re-checks what the browser
> already enforced — one paragraph, identical in 02 and 12, the policy half in 02 and the enforcement half
> here; the client-side route guard and role-conditional rendering, and whether the client treats a refusal
> as authoritative (13); the correctness and the resource cost of the data an access decision protects (05,
> 11); the deployed posture of the elevated surface and the secret material it may read (10); the
> transaction boundary around a decision and its write (03); the constraints and indices backing a grant
> (14); the inbound request form and the external integration contracts (07); production-code convention
> and dead code (08); namespace rulings and cross-phase conflict resolution (99). A mechanism another
> phase owns is recorded as a deferral with its owner named, and this block still covers the decision this
> phase makes. The deferrals this file previously carried — to a content-lifecycle phase, a consent phase,
> a media phase and an external-boundary phase for media ownership — are withdrawn: none of those
> subsystems exists in this system.

## 4.5 Prefix and Report Output

Prefix: **`AUTZ-`** (unique; keep).

```
## Report Output

- Findings path: `.ai/audit/12-authorization/findings.md`
- Template: `.ai/audit/templates/audit-findings.md` — follow it for front matter, summary, findings, distribution, cross-finding analysis, roadmap, rollout safety, appendices
- Finding-ID prefix: `AUTZ-`
- Incremental append, ≤100 lines per pass
- `problems-only: true` — findings only, omit passing checks; every finding needs runtime evidence and the exact consequence; empty state, exactly: `No problems found in this phase.`
- A shipped test asserting the current behaviour as intended is still filed as a finding, with the test recorded as a remediation blocker
```

---

## 5. Decisions requested from the coordinator

1. **F-2** — `01`, `03`, `06`, `07`, `08` carry stale findings paths and stale Scope-Boundary numbers after
   their renames. Not actionable in batch C; needs the same frontmatter/path fix in their own pass.
2. **C6 ruling (F-5)** — name the vacuous-control angle once in `99` (already the namespace owner) and have
   09 b7 and 10 b3 reference it with their own binding in one clause; 11 b2 deleted. Assign the
   row-plus-file cross-resource angle to **05**, with 01/03/06 deferring.
3. **Two-way split to be declared identically in three files** — 11 b3 / 04 / 10 on shared-store key
   composition, marker lifetime and store availability. Needs 04's and 10's rewrites to adopt the same
   wording or the split will drift exactly as the deleted 08/13/14 split would have.
