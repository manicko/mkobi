---
record_type: product-owner-decision-register
decided_by: Product Owner
decision_date: 2026-10-03
consumed_by: planner
consuming_plans:
  - .ai/plans/07-external-boundary-remediation-execution.md
  - .ai/plans/08-code-quality-remediation-execution.md
  - .ai/plans/09-test-coverage-remediation-execution.md
  - .ai/plans/10-production-ops-remediation-execution.md
  - .ai/plans/11-performance-remediation-execution.md
  - .ai/plans/12-authorization-remediation-execution.md
  - .ai/plans/13-client-tier-remediation-execution.md
  - .ai/plans/14-schema-migrations-remediation-execution.md
  - .ai/plans/15-security-baseline-remediation-execution.md
  - .ai/plans/16-chart-presentation-contract-remediation-execution.md
  - .ai/plans/17-authentication-implementation-execution.md
  - .ai/plans/18-data-pipeline-implementation-execution.md
baseline_head: b009eb9
note: >-
  Every decision below was taken by the Product Owner on 2026-10-03 in response to a
  consolidated question set covering all 54 business-level decision forks found across the
  twelve plans. The Product Owner answered "all recommended", i.e. option A on every question
  unless the question's recommended option was labelled differently. This register is the
  single source of truth: the Planner MUST fold these into the plans as CLOSED decision
  records and MUST NOT re-open, re-derive, or substitute any option.
---

# Product Owner decision register — 2026-10-03

## How to read this register

- Each entry names the **ruled option**, the **verbatim product intent**, and the **blocks it unblocks**.
- A ruled option is a **DECISION**, not a recommendation. Any text in a plan that calls the
  same option a *recommendation*, or that says the plan "chooses none", is now superseded by
  this register and must be updated in the same edit.
- **No audit file is edited.** These rulings are *applied inside the plans*, following phase 04's
  `VAL-04-001` precedent (an audit record applied as a ruling, never edited).
- Where a ruling has a **release-note consequence**, the consequence is part of the ruling and
  must appear in the owning block's definition of done.
- **Anchor drift:** every plan in scope was written at `cea2d06` / `df35d09` / `ab76989`; `HEAD`
  is now `b009eb9`. Resolve every target **by symbol** at edit time, record any drift, and never
  renumber a finding identifier.

---

## Q1 — Health endpoint contract

**Ruled: option A.** `/health` stays **database-only**. `/health/detailed` keeps all its
components but **requires an administrator**. The reconciler lease counters
(`lease_state`, `unprotected_ticks`) are **removed from the anonymous body** and are shown only
to an authenticated administrator.

**Verbatim intent:** a Redis blip must never be able to stop the reverse proxy or dependent
services from starting. Anonymous callers must not learn which replica holds the cleanup lease.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 07 | `DP-1` | Ruled option A. Unblocks `EB-1`. `/health` keeps its exact two-key shape, so `tests/test_health.py::TestHealthWithRedisDown::test_health_still_healthy_when_redis_down` **keeps its exact-dict assertion unmodified** — `DP-2` is consequently answered as **option (a)-adjacent: the test needs no weakening and must not be relaxed to key-subset membership**. `docs/05-health/health-api.md` must gain the admin-gating sentence and its self-contradiction about overall status must be resolved. |
| 10 | `DP-10-2` | Ruled option A, as phase-07 co-signer. Confirms the liveness/readiness split: liveness DB-only; Redis stored as a detailed component that never moves the liveness status. |
| 15 | `D-15-G` | Ruled: **gate `/health/detailed` with the existing admin role requirement** — this is the reduction half and it is now decided together with `D-15-H`. Unblocks `SECB-4`. |
| 15 | `D-15-H` | Ruled: **remove the reconciler counters from the anonymous payload**; expose them on the admin-gated endpoint only. Canonical for `12/`DP-12-G. |
| 12 | `DP-12-G` | **WITHDRAWN as a decision surface.** Canonical record is phase 15's `D-15-H`. Plan 12 must not ask for or record a separate ruling. |

**Release-note consequence:** an unauthenticated external monitor can no longer use
`/health/detailed`; it must poll `/health` or authenticate. State this.

---

## Q2 — Disk budget and retention

**Ruled: option A.** An explicit ceiling of **50 GB** for the artefact and log volume, enforced
**before accepting** an upload that would exceed it. Retention: temporary files **24 hours**,
processing logs **90 days**.

**Verbatim intent:** the budget is a commitment, enforced at the point of admission, and the
retention windows are policy rather than implementation detail.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 10 | `DP-10-7` | Ruled option A with the number **50 GB**. Unblocks `B14`'s volumes budget row and `B10`'s ceiling. **This is the single number** every downstream phase cites. |
| 11 | `DP-11-H` | Ruled option A with **50 GB**, not option (b) "wait for production observation". Unblocks `PRF-11`'s number, which feeds phase 06 `FAB-5` and phase 05 `C05-7`. |
| 18 | `D-05-J` | Ruled: **`cleanup_task_files` is wired into the consumer** with a **24 h** retention; **`cleanup_old_processing_logs` is retained with a 90-day** window and must actually run. Neither function may be deleted. Unblocks `PB-14`. |

**Cross-phase:** phase 06 `FAB-5` and phase 05 `C05-7` must be told the number in the same edit
that changes their own ceiling, as a named hand-over note — this plan does not edit them.

---

## Q3 — Dashboard access-management audience

**Ruled: option C.** Owner **or** administrator, **plus an explicit rule that an administrator
who is neither owner nor grantee may still manage access.**

**Verbatim intent:** the documented rule "an owner can grant what they cannot do themselves"
survives, the administrator bypass survives, and the never-executed gate's narrower admin path
is closed deliberately rather than by accident.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 12 | `DP-12-A` | Ruled option C. Unblocks **`AZ-3`, `AZ-4`**, and transitively `AZ-6` and `AZ-5`. `AZ-3` **must** correct or explicitly account for `require_dashboard_admin_access`'s asymmetry (it currently 403s an admin who is neither owner nor grantee where `check_dashboard_access` grants access). The rule decision also settles the deliberate exemption on `DashboardService.create_dashboard`'s owner-grant: **the create path is covered** — a co-signature, not an exemption. |
| 08 | `D-08-4` | Ruled as a consequence: the **enforcement point is a shared dependency** (`api/deps.py::require_dashboard_admin_access`), and the create path is in scope for the check. The *audience rule* is now fixed by `DP-12-A`, so `CQLT-2` no longer chooses one. |
| 12 | `C12-2` | The two-prospective-owner collision is **resolved in favour of plan 12**: plan 12 installs (`AZ-3`), plan 08 co-signs. Plan 08's `CQLT-2` becomes the co-signature, not a second install. |

**Release-note consequence:** 200 → 403 on three documented endpoints. **Wrongly-created
`dashboard_access` rows and filter bindings persist and require operator reconciliation** — the
fix rewrites no stored row. This belongs in the release note of `AZ-3`, `AZ-4` and `AZ-6`.

---

## Q4 — Dashboard ownership versus authorship

**Ruled: option A.** `dashboards.created_by` is **authorship only**. Ownership lives as an
explicit grant row; the creator receives an automatic owner grant at creation; a later
administrator may revoke it. **No schema change and no migration.**

**Verbatim intent:** a dashboard's creator must be removable from it, including to remove
sensitive data, and this must be achievable without a migration.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 12 | `DP-12-H` | Ruled option A. `AZ-1`'s deliverable is documentation; the 1:1 multiplicity assumption stays **phase 14's**, unchanged. |
| 14 | `D-14-J` | Ruled option A. Confirms **no rename migration and no backfill**. Plan 14 records this as a settled question, not a block. |

---

## Q5 — ACL-read absence case

**Ruled: option A.** The endpoint returns **`200` with an empty list**, unchanged, and its
published description states explicitly that this is also what a caller with no visibility
receives.

**Verbatim intent:** prefer API stability; the disclosure difference between the options is
small.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 12 | `DP-12-B` | Ruled option A. Unblocks `AZ-5`. **`AZ-5` ships the record and the tests, not a status-code change** — its deliverable is that the chosen signal is stated in the route's `description` and in `docs/02-dashboards/dashboards-api.md`, and that both signals remain distinguishable. |

**Hard constraint carried forward:** never change the status code without the same-commit prose
change. Option C (`403`) remains off the table — it contradicts `docs/SPEC.md`'s dual-signal
rule and discloses more.

---

## Q6 — Refusal error-code normalisation

**Ruled: option A.** All same-class `403`s normalise to **`PERMISSION_DENIED`**.

**Verbatim intent:** one refusal class, one code, one user-facing message.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 12 | `DP-12-C` | Ruled option A. Unblocks `AZ-11`. **No `NOT_FOUND`-on-user-lookup site is folded in** — it is a deliberate concealment signal and stays, with that reason recorded. The `layouts` role branch is folded in with the rest; no exception site survives. **No HTTP status changes.** |

**Obligation:** the one-way notice to phase 13 (`C12-1`) is issued **before** the mapping moves,
carrying the exact codes, sites and client cost, and its text and date are recorded in the
commit body.

---

## Q7 — Registration/login abuse bound

**Ruled: option A.** **Dual bound: ≤5 per IP *and* ≤5 per submitted identifier.**

**Verbatim intent:** a legitimate user behind shared office NAT is not throttled by their
neighbours, and a distributed attacker is still bounded.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 17 | `D-04-D` | Ruled option A. Unblocks `AB-6`. The per-IP half's correctness still depends on `D-04-E` (proxy trust), which is a **technical** ruling the Planner makes; option A is the only bound that stays safe under either resolution. |

---

## Q8 — Session invalidation on credential change

**Ruled: option A.** Self-service password change **revokes all sessions**. Admin password
reset **revokes all sessions**. The refresh cookie is **not rotated** on ordinary refresh.

**Verbatim intent:** resetting a compromised account must actually kill the attacker's live
session; concurrent tabs must not log each other out.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 17 | `D-04-J` | Ruled option A on all three sub-answers. Unblocks `AB-8` and the `AB-4` revocation-marker half. `AB-8` must assert that an admin reset revokes every live session, not only the presenting one. |

**Dependency:** the revocation mechanism's Redis behaviour is `D-04-F` (see Q9). `AB-8` must not
be scheduled until `AB-5`'s direction is fixed.

---

## Q9 — Deactivated accounts and revocation-read failure

**Ruled: option A.** Deactivation kills **all** existing sessions **immediately** — enforced on
every authenticated request, not only on login and refresh — returning
`401 AUTHENTICATION_FAILED`. A **revocation-read failure fails OPEN with a logged degraded
mode**.

**Verbatim intent:** availability wins over strictness, because failing closed produces a mass
logout that reads as a mass credential compromise.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 17 | `D-04-I` | Ruled option A on both halves. Unblocks `AB-4`. The rule is enforced at the shared dependency, and the chosen code is **`AUTHENTICATION_FAILED`** — no new `ErrorCode` member is created. |
| 17 | `D-04-F` | Ruled option A: **fail open with a logged degraded mode.** Unblocks `AB-5`. The degraded mode **must be logged at WARNING or above on every revocation-read failure** — a silent fail-open is not the ruling, it is the defect the ruling forbids. |

**Accepted, stated as a commitment:** a user deactivated mid-session retains access for the
duration of a Redis outage. Record this in the release note.

---

## Q10 — Delegated credential store and its rollout

**Ruled: option A.** The store holds **only a random per-token key**; the credential itself
never enters Redis. Rollout order: **accept the bounded loss window first**, then enable
authenticated Redis as **one** change covering app, worker and healthcheck.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 15 | `D-15-C` | Ruled option A. Unblocks `SECB-12`. Option B (AEAD) and option C (derivation plus a second channel) are **closed** — retrieval is routed to the issuing process. |
| 15 | `D-15-D` | Ruled option A on both halves: the **bounded loss window is accepted** (no drain), and authenticated Redis lands as **one** commit spanning app, worker and healthcheck. The accepted loss window must be **stated as a numeric commitment in the release note**, derived from the current TTL, not left implicit. |

---

## Q11 — Chart configuration key set

**Ruled: option C.** **Widen the contract to what the product uses**: accept and honour
`metrics`, `orientation`, `barmode`, `title`, `x`, `y`, `color`; **refuse genuinely unknown
keys with a message naming the key**.

**Verbatim intent:** charts must render correctly without a user hand-writing a suffixed column
name, and a typo must still be caught rather than silently discarded.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 16 | `D-16-1` | Ruled option C. Unblocks `CHTB-1` entirely, soft-blocks `CHTB-4` and `CHTB-8`. The block's product-level deliverable is now the acceptance criterion: a declared key set **survives create → read → update → read unchanged**, and a bar graph's trace `y` array **contains a value greater than zero** on a fixture whose measure is non-zero. `CHT-004`'s remaining declared-but-unread keys (`yoy`, `secondary_y`, `xaxis`, `yaxis`, `layout`, `sort_x`, `sort_color`) are **reclassified as reserved** and must be documented as such, not silently ignored. |
| 15 | `D-15-I` | Ruled option (a) — the **backend becomes the superset** matching `D-16-1` option C. Unblocks `SECB-5`. The client half is *not* a removal: `metrics`/`orientation`/`barmode` become **honoured**, so charts begin honouring stored values instead of falling back to defaults. |

**Release-note consequence:** existing charts that stored `orientation`/`barmode` change their
rendering. This is the intended direction and must be announced.

**Standing constraint carried forward:** re-make the "no graph editor exists in the shipped UI"
pre-check immediately before editing, and record its date; it must be re-made if a graph editor
is ever added, because the refusal path is only unreachable while that stays true.

---

## Q12 — `range` filter semantics

**Ruled: option C.** **`range` is removed from the filter control, and any stored `range` filter
is rejected with a message naming the reason**, until a definition exists.

**Verbatim intent:** do not ship a control that either does nothing or silently fails.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 16 | `D-16-2` | Ruled option C for the `range` half only. Unblocks the `range` half of `CHTB-6`. **The `multiselect` half is independently unblocked and must not wait** — it is the type dashboards actually use. Stored `range` filters must be handled as a **phase-14 participation**, named in the hand-over register. |

---

## Q13 — Server row cap and truncation honesty

**Ruled: option C.** **Per-graph cap plus a total count**, with the chart stating
**"showing N of M"**.

**Verbatim intent:** nothing may be silently wrong; the user must be able to narrow the filter.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 11 | `DP-11-B` | Ruled option C. Unblocks `PRF-4`. The count field is **mandatory**, not optional — a cap without a total is option (a) and is closed. |
| 13 | `DP-13-C` | Ruled option (b): the client renders **"showing N of M"** from the server count field. Unblocks `CT-3`. **The client must not invent a competing signal**; the wording is designed against phase 11's count field by name. |

---

## Q14 — Chart empty states and the bar axis default

**Ruled: option A.** Phase 16 owns **all four** empty/absent states now, **distinguishes absent
from zero on the wire**, and adds an absent-graph card. **`'category'` remains the bar chart's
default axis type** unless a stored layout overrides it.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 16 | `D-16-4` | Ruled option A. Unblocks `CHTB-5`. All four states (no graphs, no rows, measure missing, graph absent) are in **phase 16**. Acceptance criteria: a `null` measure and a `0` measure are distinguishable **on the wire**; an empty `data` array still reaches the empty branch; an absent graph is distinguishable from an empty one. |
| 16 | `D-16-3` | Ruled **option (a)** for the open half: `'category'` survives as the default. The settled half stands unchanged — the bar branch **merges** `xaxis` (`{type: 'category', ...convertedLayout?.xaxis}`), per `VAL-16-003`. |

**Release-note consequence:** dashboards that have been quietly drawing flat zeros will show
warnings for the first time. The number of affected dashboards is **unknown** and must be stated
as an unknown in the release note, not estimated.

---

## Q15 — Request-body strictness

**Ruled: option B.** Strict on **write** bodies (unknown fields rejected), permissive on **read**
bodies so documented query shapes keep working.

**Verbatim intent:** catch a typo before it becomes silent data loss, without breaking
documented read shapes.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 07 | `DP-6` | Ruled option B. Unblocks the strict-base sub-item of `EB-5`. The **frontend field census remains a hard input** and the policy must not be applied before it is complete. Phase 16 is informed; `DP-6` option (a) (strict on all bodies) is **closed**. |

---

## Q16 — Oversized anonymous error reports

**Ruled: option C.** **Reject on the declared content length; truncate on the parsed field
values.**

**Verbatim intent:** handle both the header-present and chunked cases correctly — a header-only
check is known to be insufficient in this codebase.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 07 | `DP-11` | Ruled option C. Unblocks `EB-3`. Both halves must be implemented: the declared-length rejection **and** the value-level truncation. The header-only option is **closed** — `tests/test_streaming_size_limit.py::TestStreamingSizeLimit` already proves a header check does not bind a body. |

---

## Q17 — Processing-configuration backward compatibility

**Ruled: option A.** `groupby` without `aggregations` becomes a **named deterministic
de-duplication rule** (keeps working, documented). `limit` without a determining `sort_by` is
**rejected at save time** with a message naming the field.

**Verbatim intent:** catch a bad configuration when the dashboard is saved, rather than after
the upload as an unexplained failed run.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 18 | `D-05-C` | Ruled option A. Unblocks `PB-6`. The de-duplication rule must be **named and documented**, not an emergent consequence of code. |
| 18 | `D-05-D` | Ruled option (b) — **reject the pair at validation**. Unblocks `PB-7`. Options (a) (move the limit after aggregation, which changes stored values in users' dashboards) and (c) (require `sort_by` unconditionally) are **closed**. |

---

## Q18 — Empty selection and zero-row status update

**Ruled: option A for the selection; option A for the status update.**

- A processing run whose selection matched nothing **fails, naming the graphs that were
  skipped**.
- A status `UPDATE` affecting **zero rows** **warns and completes normally** — a rebuild that
  legitimately changed nothing is not a failure.

**Verbatim intent:** a run that silently matched nothing and reported success is the more
dangerous outcome; a genuine no-op is not.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 18 | `D-05-N` | Ruled option A. Unblocks `PB-3`. Option (c) (delete stale rows) is **closed** — it destroys data on a mis-typed upload. The failed-run wording must be updated in the frontend's `failed` renderer, named as a phase-13 hand-over. |
| 18 | `D-05-A.2` | Ruled option A. Unblocks `PB-1`, `PB-3`. |

---

## Q19 — Where validation warnings surface

**Ruled: option B**, plus the related ruling: a misspelled processing setting is **rejected at
configuration time with a `422` naming the field**.

**Verbatim intent:** no new status value and therefore no migration; operators still see the
problem.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 18 | `D-05-F` | Ruled option B. Unblocks `PB-9`. Option (a) (a new status value) is **closed**, and therefore **no phase-14 migration hand-over is created**. The never-true `column_types` check is retained and its summary lands in `processing_logs.message`. |
| 18 | `D-05-G` | Ruled option (a) — a strict settings boundary producing a `422` at save time. Unblocks `PB-8`. **The `PUT /processing-configs/{id}` caller and frontend-form inventory remain a hard input.** |

---

## Q20 — Coverage bar and skipped-test commitment

**Ruled: option A.** **Remove the coverage mask entirely and publish the real number**, accepting
a visible drop. Convert **every skip to a named marker**; schedule removal with a **named owner
and a date** rather than deleting assertions.

**Verbatim intent:** the published number must mean what it says, and a skip is a commitment
with an owner, not a silent deletion.

| Plan | Decision ID | Effect |
| ---- | ----------- | ------ |
| 09 | `DP-09-G` | Ruled option A. Unblocks `TCO-7`. The mask is removed; every newly visible line becomes an obligation and the drop must be stated in the release note as a number, not a surprise. |
| 09 | `TST-013` / `TCO-10` | Ruled option **(b) plus (d)**: convert every skip to a named marker, then schedule removal with a **named owner and a date**. Option (c) (add the missing coverage now) is closed as unbounded. Each skip group must name its owner explicitly — a skip with no owner and no date is not a disposition. |

**Obligation:** the coordinator-level disposition must list **25 skips → 25 owners/dates**, not a
grouped summary. Where a group has no natural owner, record it as **unowned** rather than
assigning it to a phase that does not own it.

---

## Recorded, not scheduled — Coordinator and deployment items

These were **not** put to the Product Owner and are **not** decided by this register. Each plan
records them as recorded-and-unowned; none may be silently absorbed by a block.

| Item | Plan / ID | Why it is not decided here |
| ---- | --------- | -------------------------- |
| Five orphaned `bidb` rows in the dev database | 07 `DP-5`, inherited by 08 `O-17` and 12 `O-19` | Data-row hygiene. "A Planner must not create or delete database rows." Chooser: **Coordinator**. |
| Whether production Redis is authenticated | 10 `DP-10-4` | Deployment-topology and production security posture. Chooser: **Coordinator**. Not filed by the report; no phase owns it. |
| Which carrier holds the frontend bundle | 10 `DP-10-6` | Deployment topology. Chooser: **Tech Lead + Coordinator**. |
| The worker's liveness window | 10 `DP-10-12` | Operator trade-off between detection speed and false positives. Chooser: **Tech Lead + phase 10**. |
| Test-image / fresh-tree ownership | 09 `DP-09-H` | Deployment topology, not a test choice. Chooser: **Tech Lead + Coordinator**. |
| Cross-phase sequencing calls | 11 `DP-11-A`, `DP-11-D`; 14 `D-14-C`; 16 `D-16-5`, `D-16-6` | Topology and ownership routing. Chooser: **Coordinator**. |
| The error-code register, `tests/test_permissions.py`, `docs/07-frontend/data-api.md` | 12 `C12-4`, `C12-5`, `O-26` | Explicitly recorded as having no phase owner. Chooser: **Coordinator** / documentation owner. |

**If a block needs one of these to proceed, it names the gap in its commit body and proceeds
without inventing the answer.**

---

## Technical forks the Product Owner did not rule — Planner's own authority

These remain open and are the **Planner's** to close inside each plan. They are listed so the
Product Owner's register is not mistaken for having closed them:

`07` `DP-2`, `DP-3`, `DP-4`, `DP-8`, `DP-9`, `DP-10`, `DP-12` · `08` `D-08-1`, `D-08-2`, `D-08-5`,
`D-08-6`, `D-08-7`, `D-08-8`, `D-08-9`, `D-08-10`, `D-08-11` · `09` `DP-09-A` … `DP-09-F` · `10`
`DP-10-1`, `DP-10-3`, `DP-10-8`, `DP-10-9`, `DP-10-10`, `DP-10-11`, plus un-IDed `B3`, `B4`, `B7`,
`B13` · `11` `DP-11-C` … `DP-11-J`, `DP-11-I`, `DP-11-J`, plus un-IDed `PRF-2`, `PRF-5`, `PRF-6`,
`PRF-10` · `12` `DP-12-E`, `DP-12-F` (its *scope* half only), `DP-12-D` · `13` `DP-13-A`, `DP-13-B`,
`DP-13-E` … `DP-13-O` · `14` `D-14-A` … `D-14-I` · `15` `D-15-A`, `D-15-B`, `D-15-E`, `D-15-F`,
`D-15-J`, `D-15-K`, `D-15-M`, `D-15-N`, `D-15-O` · `16` `D-16-5` … `D-16-8` · `17` `D-04-B`,
`D-04-E`, `D-04-G`, `D-04-K` · `18` `D-05-B`, `D-05-H`, `D-05-I`, `D-05-K`, `D-05-L`, `D-05-M`,
`D-05-O`, `D-05-P`, `D-05-Q`, `D-05-R`.

**Two exceptions where the Product Owner's ruling constrains a technical fork and the Planner
must record the link, not decide the fork:** `07` `DP-2` (constrained by Q1 — the exact-dict
assertion stands and must not be relaxed) and `08` `D-08-4` (constrained by Q3 — the audience is
fixed, only the enforcement point is the Planner's).