---
title: Owner rulings — INPUT A (Tech Lead session) — SUPERSEDED
date: 2026-10-03
status: superseded-source
superseded_by: .ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md
ruled_by: Product Owner
scope: business uncertainty only; technical derivations are out of scope and remain with the Tech Lead and Planner
---

> **THIS FILE IS AN INPUT, NOT AN AUTHORITY.**
> It is one of two parallel Product Owner decision sets produced on 2026-10-03. The other is
> `.ai/decisions/PO-2026-10-03-product-owner-rulings.md`. Both were ratified by the Product Owner
> answering "all recommended" to each agent's own question set.
> The single authoritative register is
> **`.ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md`**, which adjudicates every point
> of disagreement between the two and records which was chosen and why.
> Where this file and the adjudication differ, **the adjudication governs.**

# Owner rulings — INPUT A — 2026-10-03

**This file is the single source of truth for owner rulings in plans 07–16.** Every decision ID below
was raised by a Planner as *business* uncertainty — a question no amount of code reading answers,
because the correct answer is a statement about product behaviour, business rules, priorities, user
expectations or acceptance criteria.

The Product Owner was asked 25 questions across 9 clusters and **ruled the recommended option in
every case**. No ruling below is a Planner's choice, and no option was ruled by default because a
question went unanswered.

**What this file is not.** It does not rule any technical question. Decisions about where a bound
lives, which migration revision is retired, which layer enforces a gate, which commit shape is used,
and every `DP-*` record a Planner can settle from the repository remain open and are explicitly
out of scope here. Where a plan's own text says "no option is chosen in this plan", that statement
remains true for the technical records; **only the IDs in the table below are now decided.**

**Precedence.** Where a plan records a recommendation that differs from a ruling below, the ruling
wins and the plan text is amended. Where two plans recorded the same question under different IDs,
the canonical ID is named and the other ID is marked answered by it rather than left open.

---

## Cluster A — Dashboard authorization

| ID | Plan | Ruling | Blocks released |
| -- | ---- | ------ | --------------- |
| **DP-12-A** | 12 | **(a)** Owner **or** administrator on all four write surfaces, **plus an explicit rule for the administrator who is neither owner nor grantee** — that administrator gets the administrative path, and `require_dashboard_admin_access`'s asymmetry is fixed rather than inherited | `AZ-3`, `AZ-4`, `AZ-6`, `AZ-5` |
| **DP-12-H** | 12 | **(a)** `dashboards.created_by` is **authorship**. Authority comes from the grants table or the administrator role; the owner branch in `check_dashboard_access` is a convenience grant created at creation time. No behaviour change, no migration. | `AZ-1`; `AZ-3`'s gate semantics are now fixed rather than dependent on an unstated reading of a column |
| **D-14-J** | 14 | **(a)** A dashboard has **exactly one creator**; the 1:1 multiplicity assumption stands and no co-owner model is planned. `created_by` is provenance only | nothing; records the 1:1 assumption phase 12 handed over as `C12-6` |

**Note on `DP-12-A`'s option (c) vs (a).** Option (a) was ruled, which means the administrator's
administrative path is **granted**, not excluded. A plan must not implement option (a) while leaving
the asymmetry in place — that is option (c) wearing option (a)'s name.

---

## Cluster B — Deactivated accounts

| ID | Plan | Ruling | Blocks released |
| -- | ---- | ------ | --------------- |
| **DP-12-E** / **D-04-I** (joint) | 12 (with 04) | **(a)+(b) as ruled by the owner:** the **behaviour** is (a) — refuse at login and refresh; the **commit shape** is (b) — two commits, sequenced (b) → (c): the reactivation-path marker deletion first, the credential-issuance `is_active` read second. Ordering is the mitigation, not the commit count | `AZ-2`, `AZ-9`, `AZ-10` |
| **DP-12-F** | 12 | **(b)+(i)** Delete the `admin.py` docstring landed by `2174895` (its subject no longer describes the endpoint), in the **same commit** as the code change. Scope stays **(i)** — `login_user` and `refresh_token` only — **and the token-minting census in `AZ-2` must enumerate every other minting path by name and state it out of scope with a reason.** "We only fixed the two the report named" is not an acceptable answer | `AZ-2`, `AZ-9`, `AZ-10` |

**The user-facing half of this ruling, stated once.** A deactivated account receives **401 on login
and 401 on refresh**, and the message must **not** distinguish "deactivated" from "wrong
credentials". The rationale for the non-enumerating message is that an explicit message confirms
the account exists to anyone holding the username; the rationale for refusing at login rather than
at the gate is that login-then-refuse is a locked-out user with a valid token and a diagnostic that
says nothing.

---

## Cluster C — Refusal vocabulary

| ID | Plan | Ruling | Blocks released |
| -- | ---- | ------ | --------------- |
| **DP-12-C** | 12 | **(a)** Normalize the one refusal class to **`PERMISSION_DENIED`**, and leave `NOT_FOUND`-as-refusal as a **deliberate concealment with the reason written down**. Option (c)'s `FORBIDDEN` exception for the layouts branch is **not** adopted: the class normalizes to one code | `AZ-11`; the `C12-1` notice to phase 13 must still be issued **before** the mapping moves |

**What this ruling forecloses.** Option (d) — deliberately splitting grant-refusal and role-refusal
into two codes — is off the table. It is the strongest model and it is not this phase's; it changes
the client's model and cannot land in one change.

---

## Cluster D — Health, diagnostics, and rate-limit posture

| ID | Plan | Ruling | Blocks released |
| -- | ---- | ------ | --------------- |
| **DP-1** (canonical, from the code context) | 07 | **(a)** Liveness stays **database-only**. The store appears as a detailed component that never moves the overall status | `EB-1` |
| **DP-10-2** | 10 | **(a)** Phase 10 co-signs (a) and signs the three facts the ruling depends on: the number of services gating on app health, the dev tier **inheriting** the probe, and the fail-closed store policy being a declared production setting on two services | `B0`'s register |
| **D-15-G** + **D-15-H** (one ruling) | 15 | **(a)** `/health/detailed` **stays reachable without login**, but the body **strips the filesystem path, the raw database driver text, and the reconciler's `lease_state` / `unprotected_ticks`**. A single alive/degraded flag survives. **The "keep the counters as-is" option is not adopted** — the phase-15 default reading is that today's disclosure is *not* assumed safe | `SECB-4` |
| **DP-12-G** | 12 | **Answered by `D-15-H`.** This record is withdrawn as a decision surface per `C12-13` / `C15-18`; `AZ-12` waits on nobody. **The owner is not asked this question twice** | `AZ-12` unblocked |
| **`VAL-09-004` / `C09-3`** | 09 → 04 | **Fail closed everywhere.** The shipped default is correct and is now an **intentional, documented** posture; `docs/01-auth/auth-api.md`'s claim that limiting "fails open by default" is **wrong in the other direction** and must be corrected | nothing was blocked; the absence of an owner is now resolved |

**Note on the duplicate.** `DP-12-G` and `D-15-H` were the same question. Phase 15's is canonical
because phase 15 measured the unauthenticated body against the live stack. They are ruled **once**,
here.

---

## Cluster E — Charts and data volume

| ID | Plan | Ruling | Blocks released |
| -- | ---- | ------ | --------------- |
| **DP-11-B** | 11 | **(a)+(c)** The bound ships as **a per-graph bound plus the untruncated total in the response**, so truncation is **visible** rather than silent. Options (b) silent truncation and (d) server-side aggregation are both rejected — (d) is a semantic change to what a dashboard shows, not a performance fix | `PRF-4`'s response shape |
| **DP-11-A** | 11 | **(b)** The server bound and the client signal land **atomically, in one change**. There is no silent-truncation window and no unbounded interim. Cost accepted: one commit spanning `src/mkobi` and `frontend/src`, two review surfaces, one revert taking both | `PRF-4`; hard requirement on phase 13's `CT-1` + `CT-3` as **one commit** |
| **DP-13-C** | 13 | **(b)** The client renders the server's count as **"showing N of M"**. The client **must not invent the field** (`R-13-4` stands); `CT-3`'s render path consumes `DP-11-B(c)`'s field and ships inert if that field does not land | `CT-3`'s signal half |
| **DP-13-B** | 13 | **(a)** The `queryKey` fix lands **with** the `graphId` threading, in the same commit as `DP-11-A`'s atomic change. Threading `graphId` without adding it to the cache key makes every per-graph fetch collide on one cache entry | `CT-1` + `CT-3` as one commit |
| **D-15-I** | 15 | **(a)** Widen the backend chart-config contract to include **what the client already reads** — `metrics`, `orientation`, `barmode`, `showlegend` — and widen it **additively**. Phase 13 is co-signer. Nothing stored breaks | `SECB-5` |
| **D-16-1** | 16 | **(d)** The surviving key set is the **widened** one, co-signed with `D-15-I`(a). This is an **additive** widening, so the report's hard constraint (a narrowing answer must not ship before `CHTB-2`'s response shape lands) is **satisfied by construction** and does not gate | `CHTB-1` entirely; soft-blocks `CHTB-4`, `CHTB-8` released |
| **D-16-2** | 16 | **(a)** A `range` filter targets a **dimension**. A measure-targeted range is **rejected with a clear message**, not silently ignored and not implemented. No new server capability | the `range` half of `CHTB-6`; the `multiselect` half was independently unblocked and must not wait |
| **D-16-3** | 16 | **(a)** The forced `category` axis **survives as the default** when the converted layout supplies no `type`. No existing dashboard changes visually. The bar branch **merges** `xaxis` — `VAL-16-003` decides that and it is not reopened | `CHTB-3` |

**The load-bearing pairing.** `D-15-I`(a) and `D-16-1`(d) are the **same ruling** seen from two
tiers. They must never be ruled differently. Both name the widened key set, and both make the
measure nameable so a chart stops rendering all-zero values.

---

## Cluster F — What the user is told

| ID | Plan | Ruling | Blocks released |
| -- | ---- | ------ | --------------- |
| **DP-13-D** | 13 | **(a)** **One surface per context.** A persistent inline message carries errors for the main view; the toast is **reserved for background refetches and mutations**, which have no inline surface. A user who currently gets both a toast and a banner gets one | `CT-6` |
| **DP-13-H** | 13 | **(a)** The **server is authoritative** for password rules and the client mirrors it exactly. The client's uppercase-only rule is dropped from the client; it is **not** added to the server. No backend file is edited by a client finding | the `new_password` row of `CT-2`; the suite's red count resolves |
| **D-15-A** + **D-15-B** | 15 | **(a)** A password past the hashing algorithm's **72-byte limit is rejected at the boundary** with a clear message. Verification keeps truncating, so **already-stored credentials continue to verify** — the asymmetry is deliberate and must be written down as such. Option (c), removing truncation, is **forbidden**: it locks every credential already stored | `SECB-10` |

**Why the asymmetry survives.** Minting refuses; verification truncates. If verification also
refused, every credential already stored at or above the ceiling would become unusable — a
self-inflicted outage. The residual risk is stated, not eliminated: a stored credential above the
ceiling has only its 72-byte prefix as effective entropy, and the **inventory of already-stored
credentials is an operator step** (`C15-1`), owned by phase 04's follow-on.

---

## Cluster G — Operational acceptance criteria

| ID | Plan | Ruling | Blocks released |
| -- | ---- | ------ | --------------- |
| **D-15-C** | 15 | **(a)** The delegated store holds **only a random lookup handle**. The credential itself **never persists** in the store. Option (b), AEAD under a `_FILE` key, is **rejected**: the validation found it leaves every outstanding credential recoverable by anyone holding both the store and the environment — which is the reachability that motivated the change | `SECB-12` |
| **`DP-10-7` / `DP-11-H`** (one decision, two IDs) | 10 (owner) + 11 (measurement) | **(a)** A **conservative ceiling, set now**, with the **derivation published** once phase 11's measurement set lands. Every figure must name its procedure and conditions, and the register **supersedes** the retracted `1,036.2 MB / 101.2 %` pair wherever it is cited | phase 06 `C06-4`, phase 05 `C05-7`, `C05-8`, `C06-7`, `PRF-0`, `DP-11-H` — **three phases were blocked on this** |
| **DP-11-D** | 11 | **(a)** **Keep one worker replica.** Publish the measured ceiling with its measurement conditions, and **add a queue-depth alert**. The alert's missing metric source is named as a known gap rather than assumed | `PRF-7`'s disposition; `TOPO-002`/`TOPO-003` are **not** re-opened |
| **RPO / RTO** | 10 | **RPO 24 h · RTO 4 h**, daily backups. Both numbers are **published** in the deployment documentation and **gated on a rehearsed restore against a scratch database**. `backup` and `restore` must not report success unconditionally | `B1`, `B2`; the runbook's restore rehearsal becomes an acceptance criterion |
| **D-15-O** | 15 | **(a)** **Take all three** un-assigned seams: the Redis container's capability drop / read-only filesystem / non-secure default user, the **absent allowed-hostnames policy** (configured from the deployment's real host list), and the **floating `FROM` tags** pinned | `SECB-13` |

**Separation that must not be blurred.** Phase 06 owns the artefact area's **ceiling**; phase 10
owns the **budget**; phase 11 owns the **capacity measurement** underneath both (`C11-7`). The
ruling sets the number and requires the derivation to be published with it. **A wrong number is
worse than no number** — which is why the derivation must ship next to the figure.

---

## Cluster H — Priorities and acceptance criteria

| ID | Plan | Ruling | Blocks released |
| -- | ---- | ------ | --------------- |
| **D-16-5** | 16 | **(a)** **Defer all four** unnamed hand-overs (`H-1` … `H-4`), recorded as **"held by phase 16, deferred by decision"** — explicitly **not** "unowned". Phase 13's `CT-5` and `CT-10` therefore stay blocked on this phase and the blocking state is stated as a decision, not an omission | `CHTB-9`; `C16-1` — **`C13-1` is released by this ruling**, because there is no phase-16 work in those files for phase 13's work to be additive to. Phase 13 must be **told this directly** rather than inferring it from silence |
| **D-16-8** | 16 | **(b)** Frontend coverage thresholds are **enforced after this phase's blocks have landed tests** — the only ordering in which enforcement is meaningful. Not now (they fail: `ChartRenderer.tsx` has zero coverage), not advisory | the gate half of `CHTB-9` |
| **`TST-003`** | 09 | The **65 % backend floor is made live on the main test entry point and the aggregate check**, and it **must not be relaxed**. The floor's value is unchanged; only its reach changes | `TCO-1`'s wiring |
| **DP-09-G** | 09 | **Measure first, then decide.** No coverage-mask ruling is made here. `TCO-7` must produce an uncovered-locator measurement before the mask's disposition is chosen | `TCO-7` remains gated on its own measurement |

---

## Boundary rulings

| ID | Plan | Ruling | Blocks released |
| -- | ---- | ------ | --------------- |
| **DP-11** (07) | 07 | **(a)** An oversized anonymous client-error report is **rejected with 413**, using the status the project already uses for an oversized inbound body. The bound belongs on the **parsed field values**, not on `Content-Length`, because a header-only check does not bind a chunked body | `EB-3` |
| **DP-6** (07) | 07 | **(a)** **Unknown fields in API request bodies are rejected on write routes — but only after the frontend field census lands.** The census is delivered **by symbol** in `EB-5`'s commit body, naming every caller that had to be fixed, **before** any `forbid` lands | `EB-5` |
| **DP-12** (07) | 07 | **(a)** Application-level gate on the schema surface, with **nginx recorded as the real production control** and the gap handed over as a **named** seam. The fact that the change has no shipped effect in production topology must be stated, so no reader over-reads it | `EB-7` |
| **DP-13-I** | 13 | **(a)** Align the client to the create rule **and** add a server validator. No divergence survives the change | additive on `CT-2` |

---

## What remains open by design

The following are **not** decided by this ruling and a plan must not read this file as deciding them:

- Every technical `DP-*` a Planner can settle from the repository — commit shapes, layer placement,
  which revision to retire, which module owns what.
- `DP-09-A` … `DP-09-F` (test-observation seams, timeout budgets, fixture placement, fake-store
  honesty, row containment) — Planner-owned.
- `DP-10-1`, `DP-10-5`, `DP-10-8` — deployment-topology choices with no user-visible behaviour.
- `DP-13-E`, `DP-13-F`, `DP-13-J`, `DP-13-K`, `DP-13-L`, `DP-13-N`, `DP-13-O` — client structure
  and documentation-scope decisions with no business content.
- `D-14-A` … `D-14-I`, `D-15-B`'s caller-discipline variant, `D-16-4`, `D-16-6`, `D-16-7`,
  `D-08-3`, `D-08-7`, `DP-09-H` — technical or sequencing.

**A plan that cites this file for one of the above is misciting it.**