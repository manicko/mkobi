---
title: ADJUDICATED Product Owner decision register — 2026-10-03
date: 2026-10-03
status: single-authority
supersedes:
  - .ai/decisions/PO-2026-10-03-product-owner-rulings.md
  - .ai/plans/00-owner-rulings-2026-10-03.md
ruled_by: Product Owner (both inputs)
adjudicated_by: Tech Lead
baseline_head: b009eb9
consuming_plans: [07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18]
---

# ADJUDICATED Product Owner decision register — 2026-10-03

## Why this file exists

Two agents independently produced a Product Owner decision register on 2026-10-03. Both are
ratified: the Product Owner answered **"all recommended"** to each agent's own question set. They
overlap heavily and **disagree on eleven points**, six of them behavioural.

- **INPUT B** — `.ai/decisions/PO-2026-10-03-product-owner-rulings.md` — 54 forks across 12 plans.
- **INPUT A** — `.ai/plans/00-owner-rulings-2026-10-03.md` — 25 forks across 10 plans.

**This file is the single authority.** It merges both inputs, adjudicates every disagreement on
merit, and records which input won and why. Neither input file may be cited as authority after
this file exists; both are retained as provenance.

## How to read a ruling here

- A ruling names the **chosen behaviour in words**. Option letters from the input registers are
  **not** carried across — the letters referred to different tables. Always implement the words.
- **`A`** = INPUT A won · **`B`** = INPUT B won · **`A+B`** = merged, each contributing a distinct
  part · **`NEW`** = neither input covered it; adjudicated here on the Product Owner's standing
  instruction ("all recommended") plus the plans' own evidence.
- **Choosers.** Where an input reserved a decision to the Planner or Coordinator and the other
  ruled it, the ruling **stands** and the record's chooser becomes the Product Owner, with this
  adjudication as the record of why. A plan must not re-open it.

## Rules that bind every implementor

1. A ruled option is a **DECISION**. Any plan text calling the same option a *recommendation*, or
   saying the plan "chooses none", is superseded and must be updated in the same edit.
2. **No audit file is edited.** These rulings are applied inside the plans.
3. **Resolve every target by symbol at edit time.** Plans were written at `cea2d06` / `df35d09` /
   `ab76989`; `HEAD` is `b009eb9`. Record drift; never renumber a finding identifier.
4. **Never weaken an assertion, tolerance or verification requirement** to land a ruling.
5. Where a ruling has a **release-note consequence**, the consequence is part of the ruling and
   appears in the owning block's definition of done.

---

# Cluster 1 — Authorization

### `DP-12-A` (plan 12) — dashboard access-management audience · **`B`**

Owner **or** administrator on all four write surfaces, **plus an explicit rule that an administrator
who is neither owner nor grantee may still manage access.** `AZ-3` **must** correct — or explicitly
account for — `require_dashboard_admin_access`'s asymmetry, which currently 403s such an
administrator where `check_dashboard_access` grants access. `DashboardService.create_dashboard`'s
owner grant is **covered** — a co-signature, not an exemption.

Unblocks `AZ-3`, `AZ-4`, transitively `AZ-6` and `AZ-5`.

**Both inputs agreed on the content**; INPUT B additionally named the create path and `C12-2`'s
resolution, which is strictly more complete and is adopted.

**Not negotiable:** implementing the audience while leaving the asymmetry in place is option (c)
wearing this option's name.

### `C12-2` (plan 12) / `D-08-4` (plan 08) — enforcement point and ownership · **`B`**

The collision resolves **in favour of plan 12**: plan 12 installs (`AZ-3`), plan 08 **co-signs**.
Plan 08's `CQLT-2` is the co-signature, not a second install. The **enforcement point is the
shared dependency `api/deps.py::require_dashboard_admin_access`**, and the create path is in scope.

INPUT A left the enforcement point open. INPUT B's is better: it names one point, settles a
two-owner collision, and a shared dependency is the only option that cannot be bypassed by a new
call site.

**Release note:** 200 → 403 on three documented endpoints. Wrongly-created `dashboard_access` rows
and filter bindings **persist and require operator reconciliation** — the fix rewrites no stored row.

### `DP-12-H` (plan 12) — `created_by` is authorship · **`B`**

Authorship only. Ownership lives as an **explicit grant row**; the creator receives an automatic
owner grant at creation; **a later administrator may revoke it**. No schema change, no migration.
`AZ-1`'s deliverable is **documentation**.

INPUT B's addition — *a creator must be removable from their own dashboard, including to remove
sensitive data* — is the reason this is the correct reading, and it is absent from INPUT A's
formulation.

### `D-14-J` (plan 14) — one creator · **`B`**

Exactly one creator. **No rename migration and no backfill.** Plan 14 records this as a **settled
question, not a block**; the 1:1 multiplicity assumption is unchanged and stays plan 14's.

### `DP-12-D` (plan 12) — `graphs.py`'s inline access set · **`A`**

**In scope.** Replace the inline computation with the shared dependency and delete the inline code
and the stale comment **in the same commit** — **conditioned on the Auditor's code comparison
answering first** (does an administrator see a different graph set under the two paths?). Per
`CQLT-3`, the before/after administrator-visibility assertion must be proven to fail once, before
merge. If the Auditor finds a divergence that is not the asymmetry, that divergence is a **finding**
and the replacement is deferred until it is understood.

### `DP-12-C` (plan 12) — one refusal code · **`B`**

All same-class 403s normalise to **`PERMISSION_DENIED`**. **No `NOT_FOUND`-on-user-lookup site is
folded in** — it is a deliberate concealment signal and stays, with that reason recorded. **The
`layouts` role branch is folded in with the rest; no exception site survives.** **No HTTP status
changes.**

Unblocks `AZ-11`. The `C12-1` one-way notice to phase 13 is issued **before** the mapping moves,
carrying exact codes, sites and client cost, with its text and date recorded in the commit body.

Deliberate splitting of grant-refusal from role-refusal stays off the table: it is the strongest
model and it cannot land in one change.

### `DP-12-B` (plan 12) — ACL-read absence case · **`B`**

**200 with an empty list, unchanged.** `AZ-5` ships **the record and the tests, not a status-code
change**: its deliverable is that the chosen signal is stated in the route's `description` and in
`docs/02-dashboards/dashboards-api.md`, and that both signals remain distinguishable.

**Hard constraint:** never change the status code without the same-commit prose change. Option (c)
`403` stays off the table — it contradicts the dual-signal rule and discloses more.

---

# Cluster 2 — Deactivated accounts and revocation reads

### `DP-12-E` / `D-04-I` — behaviour · **`B`** · commit shape · **`A`**

**Behaviour (`B`, stronger).** Deactivation kills **all** existing sessions **immediately**, enforced
on **every authenticated request** — not only at login and refresh — returning
`401 AUTHENTICATION_FAILED`. **No new `ErrorCode` member is created.**

INPUT A ruled refusal at login and refresh only. INPUT B is better: it closes the mid-session
deactivation hole, which login-only enforcement leaves open, and it is the same rule enforced at
the one place every authenticated request passes.

**Commit shape (`A`).** Two commits, sequenced: the reactivation-path marker deletion first, the
credential-issuance `is_active` read second. **Ordering is the mitigation, not the commit count.**

**Non-enumerating message (`A`, free).** The chosen code `AUTHENTICATION_FAILED` is already the
generic authentication failure, so the response does not distinguish *deactivated* from *wrong
credentials*. This is a property to assert, not a coincidence to rely on.

### `DP-12-F` (plan 12) — docstring and scope · **`A`**

Delete the `admin.py` docstring landed by `2174895` — its subject no longer describes the endpoint —
**in the same commit** as the code change. Scope stays on `login_user` and `refresh_token`, **and
`AZ-2`'s token-minting census must enumerate every other minting path by name** and state it out of
scope with a reason. "We only fixed the two the report named" is not an acceptable answer.

### `D-04-F` (plan 17) — revocation-read failure · **`B`**

**Fail OPEN, with a logged degraded mode.** The degraded mode **must be logged at WARNING or above
on every revocation-read failure** — a silent fail-open is not the ruling, it is the defect the
ruling forbids. Availability wins over strictness, because failing closed produces a mass logout
that reads as a mass credential compromise.

**Accepted, stated as a commitment:** a user deactivated mid-session retains access for the duration
of a Redis outage. Release note.

---

# Cluster 3 — Health, diagnostics and rate limiting

### `DP-1` (plan 07) / `DP-10-2` (plan 10) — the liveness contract · **`B`**

`/health` stays **database-only** and keeps its **exact two-key shape**. Redis is stored as a
**detailed** component that never moves the liveness status. Both inputs agreed.

`DP-10-2` records phase 10's co-signature: the liveness/readiness split, the number of services
gating on the application's health state, the dev tier **inheriting** the probe, and the fail-closed
store policy being a declared production setting on two services.

**`DP-2` is closed by this ruling, not by a Planner's preference.** Because `/health` does not
change, `test_health_still_healthy_when_redis_down`'s exact-dict assertion is green
**unmodified**. Relaxing it to key-subset membership is **closed by name**: that exact check is what
catches this class of change. Unblocks `EB-1`.

### `D-15-G` + `D-15-H` (plan 15) — `/health/detailed` disclosure · **`A+B` — MERGED**

This is the one point where the two inputs chose genuinely different products, and neither is
sufficient alone.

| | INPUT A | INPUT B |
| - | - | - |
| Reachability | stays anonymous | **gated behind the existing admin role** |
| Reduction | strips path, raw driver text, lease counters | removes reconciler counters from the anonymous body |

**Ruling: do both, in the same change.** `/health/detailed` **becomes admin-gated using the
existing `require_admin_role`** — which is the stronger posture and which the route's own docstring
already claims, so the code contradicting the docstring *is* the defect — **and** the body is
reduced regardless: the filesystem path, the raw database driver text, and the reconciler's
`lease_state` / `unprotected_ticks` all leave the anonymous payload, with a single alive/degraded
flag surviving.

**Why merged rather than either.** INPUT B alone leaves a stated hazard the plan itself names: a
probe which gains a 401/403 **reads as an outage**. INPUT A alone leaves an unauthenticated surface
whose docstring already says it should be admin-facing. Doing both means that **if the gate causes
a false outage, the fallback surface has already been reduced** — the failure mode is survivable
rather than merely documented. `/health` remains unauthenticated and database-only, so **no load
balancer, compose dependent or external monitor ever gets a 401.**

**Release note:** an unauthenticated external monitor can no longer use `/health/detailed` — it must
poll `/health` or authenticate. State this.

Unblocks `SECB-4`. `docs/05-health/health-api.md` is edited **in the same commit**, because the
document currently specifies the disclosure as intended behaviour. `tests/test_health.py`'s
`TestHealthDetailedEndpoint` cases are updated **with** the code, never weakened;
`TestDetailedHealthReconcilerComponent` moves as one unit with the component's comment.

### `DP-12-G` (plan 12) — **withdrawn** · **`B`**

Withdrawn as a decision surface. Canonical record is plan 15's `D-15-H`. `AZ-12` waits on nobody.
The owner is not asked this question twice.

### Rate-limiter posture — `VAL-09-004` / `C09-3` (plan 09 → 04) and `D-15-M` (plan 15) · **`A`**

**Fail CLOSED.** The shipped `fail_closed=True` default is now an **intentional, documented**
posture. `docs/01-auth/auth-api.md`'s claim that limiting "fails open by default" is **wrong in the
other direction** and must be corrected — its home is phase 04's `AB-6` documentation row.

**Do not conflate two different surfaces.** The rate limiter (`D-15-M`, plan 15) and the
revocation-read path (`D-04-F`, plan 17) are separate. INPUT B's fail-open ruling applies to the
**revocation read** only; it does **not** extend to the rate limiter.

---

# Cluster 4 — Data volume and charts

### `DP-11-B` (plan 11) — row cap and truncation honesty · **`B`** = **`A`**

**Per-graph cap plus a total count**, with the chart stating **"showing N of M"**. Both inputs
converged on this substance. The **count field is mandatory, not optional** — a cap without a total
is the closed option, because a truncation a client cannot detect is a silent data-loss contract.

Unblocks `PRF-4`. `AggregatedDataResponse` gains a field, so `tests/test_openapi.py` is the
tripwire, and `docs/02-dashboards/dashboards-api.md` plus `docs/07-frontend/pages.md` move with it.

### `DP-11-A` (plan 11) — rollout ordering · **`A`**

**Atomic: the server cap and the client signal land in one change**, spanning `src/mkobi` and
`frontend/src`. No silent-truncation window, no unbounded interim. Accepted cost: two owners in one
commit, two review surfaces, one revert taking both.

The alternative orderings are both worse: client-first leaves the unbounded read in place between the
two landings, and a flag means a bound nobody sets is a bound that never lands. This makes phase
13's `CT-1` and `CT-3` **one commit**, and `C11-8` (`queryKey` omitting `graphId`) a hard
requirement inside it.

### `DP-13-C` (plan 13) — the client signal · **`B`** = **`A`**

Render **"showing N of M"** from the server's count field. **The client must not invent a competing
signal**; the wording is designed against plan 11's count field by name. Unblocks `CT-3`.

### `DP-13-B` (plan 13) — `queryKey` · **`A`**

The `queryKey` fix lands **with** the `graphId` threading, in the same commit as `DP-11-A`'s atomic
change. Threading `graphId` without adding it to the cache key makes every per-graph fetch collide
on one cache entry — a defect *introduced by the fix*, presenting as wrong chart data, covered by no
test. The key-fix-must-fail-first requirement stands.

### `D-15-I` (plan 15) + `D-16-1` (plan 16) — chart-config key set · **`B`**

**One ruling seen from two tiers; the backend becomes the superset.** Accept and honour
`metrics`, `orientation`, `barmode`, `title`, `x`, `y`, `color`; **refuse genuinely unknown keys
with a message naming the key.**

INPUT A ruled the widening only, additively. INPUT B is better: widening alone leaves the
silent-discard defect standing for every key outside the widened set, which is the whole `SEC-004`
class. Refusing unknown keys **by name** converts silent data loss into a visible 422.

`CHT-004`'s remaining declared-but-unread keys (`yoy`, `secondary_y`, `xaxis`, `yaxis`, `layout`,
`sort_x`, `sort_color`) are **reclassified as reserved and documented as such** — not silently
ignored, or they become the next silent-ignore set.

**Acceptance criteria.** A declared key set **survives create → read → update → read unchanged**,
and a bar graph's trace `y` array **contains a value greater than zero** on a fixture whose measure
is non-zero.

**The client half is not a removal.** `metrics` / `orientation` / `barmode` become **honoured**, so
charts begin honouring stored values instead of falling back to defaults.

**Standing constraint:** re-make the "no graph editor exists in the shipped UI" pre-check
immediately before editing and **record its date**. Re-make it if a graph editor is ever added,
because the refusal path is only unreachable while that stays true.

**Release note:** existing charts that stored `orientation` / `barmode` change their rendering. This
is the intended direction and must be announced. Separately: dashboards that have been quietly
drawing flat zeros will show warnings for the first time — the number of affected dashboards is
**unknown and must be stated as an unknown, not estimated.**

Unblocks `SECB-5` and `CHTB-1` entirely; soft-blocks `CHTB-4` and `CHTB-8`.

### `D-16-2` (plan 16) — `range` filter · **`B`**

**`range` is removed from the filter control, and any stored `range` filter is rejected with a
message naming the reason**, until a definition exists.

INPUT A ruled dimension-only. INPUT B is better: there is no working definition of a range filter in
this product, and "dimension-only" invents a semantics nobody confirmed — a string-range encoding on
a dimension, lexicographic, is a guess. **Do not ship a control that either does nothing or silently
fails.** Stored `range` filters are a **phase-14 participation**, named in the hand-over register.

**The `multiselect` half of `CHTB-6` is independently unblocked and must not wait** — it is the
type dashboards actually use.

### `D-16-3` (plan 16) — bar axis default · **`B`** = **`A`**

**`'category'` survives as the bar chart's default axis type** unless a stored layout overrides it.
No existing dashboard changes visually. The settled half stands unchanged: the bar branch **merges
`xaxis`** (`{type: 'category', ...convertedLayout?.xaxis}`) per `VAL-16-003`.

### `D-16-4` (plan 16) — empty states · **`B`**

Phase 16 owns **all four** empty/absent states now, **distinguishes absent from zero on the wire**,
and adds an absent-graph card. Unblocks `CHTB-5`.

**Acceptance criteria:** a `null` measure and a `0` measure are distinguishable **on the wire**; an
empty `data` array still reaches the empty branch; an absent graph is distinguishable from an empty
one.

INPUT A's split (phase 13 takes the absent-graph state) left the actual requirement — four mutually
distinguishable states — unmet by either phase.

---

# Cluster 5 — What the user is told

### `DP-13-D` (plan 13) — error surface · **`A`**

**One surface per context.** A persistent inline message carries errors for the main view; the
toast is **reserved for background refetches and mutations**, which have no inline surface. A user
who currently gets a toast *and* a banner gets one.

The report itself calls this a judgement call and is right that it is a product decision. The
exemption list must be **per-surface, not per-class**, because the interceptor cannot see which
surface is displaying a request. Unblocks `CT-6`.

### `DP-13-H` (plan 13) — password rules authority · **`A`**

The **server is authoritative**; the client mirrors it exactly. The client's uppercase-only rule is
dropped **from the client**; it is **not** added to the server. **No backend file is edited by a
client finding** — this closes `C13-2`'s "nobody owns the backend option" row; no new backend
finding is needed because the backend is not being changed. Unblocks the `new_password` row of
`CT-2`.

### `DP-13-I` (plan 13) — update-`name` divergence · **`A`**

Align the client to the create rule **and** add a server validator. No divergence survives. Additive
on `CT-2`.

### `D-15-A` + `D-15-B` (plan 15) — passwords past 72 bytes · **`A`**

**Rejected at the boundary on minting, with a clear message.** Verification keeps truncating, so
**already-stored credentials continue to verify**. The asymmetry is deliberate and is written down as
such.

**Why the asymmetry survives:** if verification also refused, every credential already stored at or
above the ceiling would become unusable — a self-inflicted outage. Removing truncation is
**forbidden**: it locks every credential already stored.

**Residual, stated not eliminated:** a stored credential above the ceiling has only its 72-byte
prefix as effective entropy. The inventory of already-stored credentials is an **operator step**
(`C15-1`), owned by phase 04's follow-on — **not** a phase-15 deliverable.

Unblocks `SECB-10`. `SALT_ROUNDS` is unchanged.

---

# Cluster 6 — Operational acceptance criteria

### `D-15-C` + `D-15-D` (plan 15) — delegated credential store · **`B`**

The store holds **only a random per-token key**; the credential itself **never enters Redis**.
Retrieval is routed to the issuing process. Options (b) AEAD and (c) derivation-plus-second-channel
are **closed** — AEAD leaves every outstanding credential recoverable by anyone holding both the
store and the environment, which is the reachability that motivated the change.

**Rollout:** the **bounded loss window is accepted (no drain)**, and authenticated Redis lands as
**one** commit spanning app, worker and healthcheck. The accepted loss window must be **stated as a
numeric commitment in the release note, derived from the current TTL** — not left implicit.

Unblocks `SECB-12`. Approved-but-unclaimed registration requests take the identical path and must be
named in the release note.

### `DP-10-7` (plan 10) + `DP-11-H` (plan 11) — the disk budget · **`A+B` — MERGED**

**One decision under two IDs, ruled together.** **50 GB** for the artefact and log volume, enforced
**before accepting** an upload that would exceed it. Retention: temporary files **24 hours**,
processing logs **90 days**.

**INPUT B supplied the number; INPUT A supplied the requirement that makes the number trustworthy.**
INPUT B alone would commit a figure with no derivation — and a number with no derivation is worse
than no number, because it is unfalsifiable. So: the number is committed **now** (unblocking three
blocked phases), **and** plan 11's derivation — measured expansion factors × the retention horizon,
every factor sourced — must be **published next to it**, with the number **revised if the derivation
contradicts it**. The register **supersedes** the retracted `1,036.2 MB / 101.2 %` pair wherever it is
cited.

**Separation that must not be blurred (`C11-7`):** phase 06 owns the artefact area's **ceiling**;
phase 10 owns the **budget**; phase 11 owns the **capacity measurement** underneath both.

Unblocks phase 06 `FAB-5`/`C06-4`, phase 05 `C05-7`/`C05-8`/`C06-7`, `PRF-0` and `PRF-11`. Phase 06
and phase 05 must be told the number as a **named hand-over** in the same edit that changes their own
ceiling.

### RPO / RTO (plan 10) · **`NEW`**

Neither input covered this. **RPO 24 h · RTO 4 h**, daily backups. Both numbers are **published** in
`docs/10-deployment/deployment.md` and **gated on a rehearsed restore against a scratch database**.
`backup` and `restore` **must not report success unconditionally**. Release `B1` / `B2`.

A deployment story with no RPO/RTO statement has no restore acceptance criterion at all, which is
the state both plans were written to fix.

### `DP-11-D` (plan 11) — worker throughput · **`A`**

**Keep one worker replica.** Publish the measured ceiling **with its measurement conditions** — a
replica count quoted without the CPU share it was measured under is not a measurement — and **add a
queue-depth alert**.

**Stated caveat:** the alert has **no metric source yet**, because `PERF-009`'s instrumentation gap
is filed and not built. **A depth alert with no metric reads zero**, and the release note must say so.
This is the smallest thing that converts a silent ceiling into a reported one, and it matches the
project's rule against premature optimisation.

`TOPO-002` / `TOPO-003` are **not** re-opened, and `PRF-7` **must not assert the worker receives
work** as a precondition.

---

# Cluster 7 — Priorities, coverage and scope

### `DP-09-G` (plan 09) — the coverage mask · **`B`**, with INPUT A's precondition attached

**Remove the coverage mask entirely and publish the real number**, accepting a visible drop.

INPUT A ruled "measure first, decide later". That leaves the mask hiding the untested, which *is* the
defect, so deferring the decision defers the fix. INPUT B subsumes INPUT A's concern: the drop must
be stated in the release note **as a number**, and producing that number requires exactly the
uncovered-locator measurement INPUT A asked for. **The measurement is therefore a precondition of
the release note, not a precondition of the ruling.** Every newly visible line becomes an obligation.

Unblocks `TCO-7`.

### `TST-013` / `TCO-10` (plan 09) — skips · **`B`**

**Convert every skip to a named marker, then schedule removal with a named owner and a date.**
Option (c) — add the missing coverage now — is closed as unbounded. Deleting assertions is not a
disposition.

**Obligation:** the coordinator-level disposition lists **25 skips → 25 owners/dates**, not a
grouped summary. Where a group has no natural owner, record it as **unowned** rather than assigning
it to a phase that does not own it.

### `TST-003` (plan 09) — the 65 % floor · **`A`**

The floor becomes **live on the main test entry point and the aggregate check**. **The value is
unchanged and must not be relaxed** — only its reach widens. A gate that runs on one entry point and
is inert on the main one is not a gate.

### `D-16-5` (plan 16) — four unnamed hand-overs · **`A`**

**Defer all four** (`H-1` … `H-4`), recorded as **"held by phase 16, deferred by decision"** —
explicitly **not** "unowned". Accepting all four roughly doubles the phase and pulls in four other
plans' open decisions; the honest state is a recorded deferral.

**This ruling releases phase 13's `CT-5` and `CT-10`.** `C16-1`'s finding is that phase 16 executed
its ten `CHT` findings and **none names a single one of those symbols** — the reservation is held by
a plan-04 out-of-scope row, not by phase-16 work. Phase 13 is blocked on a **ruling**, not on
**work**, and the block is released now. **Phase 13 must be told this directly rather than inferring
it from silence.** The `C13-1` register entry is **retained**, recording that the contention existed
and how it was resolved.

Unblocks `CHTB-9`.

### `D-16-8` (plan 16) — frontend coverage thresholds · **`A`**

**Enforced after this phase's blocks have landed tests** — the only ordering in which enforcement is
meaningful. Not now (`ChartRenderer.tsx` has zero coverage and holds six of the ten findings); not
advisory. No block may restore `frontend/coverage/` — that is phase 13's `CT-15`.

---

# Cluster 8 — Security posture

### `D-15-O` (plan 15) — three un-assigned seams · **`A`**

**Take all three:** the Redis container's capability drop / read-only filesystem / non-secure default
user; the **absent allowed-hostnames policy**, configured from the deployment's real host list; and
the **floating `FROM` tags** pinned. Recording a seam as unowned is the only wrong-by-default option.

**Verification consequence:** taking the allowed-hosts seam means every module that drives the app
through `http://testserver` fails wholesale — that count **is** `SECB-13`'s verification.

Unblocks `SECB-13`.

### `D-15-N` (plan 15) — access-token storage · **`A`**

Production asserts **memory-only** token storage. The development branch is retained behind an
explicit, named opt-in flag, not deleted. The shipped development-branch test is **not** a
defect-encoding test to invert. The **corrected 15-minute token lifetime** ships with this.

Unblocks `SECB-11`.

---

# Cluster 9 — External boundaries

### `DP-11` (plan 07) — oversized anonymous error reports · **`B`**

**Reject on the declared content length; truncate on the parsed field values.** Both halves are
implemented and both are proven by a test.

INPUT A ruled 413-reject on parsed values. INPUT B is better: truncation on the value half preserves
the diagnostic — a browser component stack is legitimately megabytes and is the report's reason to
exist, so rejecting it loses the report entirely — while the cheap header check still refuses the
obvious case immediately. `tests/test_streaming_size_limit.py::TestStreamingSizeLimit` already proves
a header check does not bind a body, so the **header-only option is closed**.

**Requirements:** the untruncated length is logged beside every capped value; the cap is named; the
endpoint's rate limit is unchanged and still tested. Unblocks `EB-3`.

### `DP-6` (plan 07) — request-body strictness · **`B`**

**Strict on write bodies** (unknown fields rejected), **permissive on read bodies** so documented
query shapes keep working. Strict on all bodies is **closed**. Catch a typo before it becomes silent
data loss, without breaking documented read shapes.

**The frontend field census remains a hard input** and the policy must not be applied before it is
complete. The census is delivered **by symbol**, naming every caller fixed. Phase 16 is informed.

### `DP-12` (plan 07) — the production schema surface · **`A`**

Application-level gate on the schema surface, with **nginx recorded as the real production control**
and the gap handed over as a **named** seam. The fact that the change has no shipped effect in the
production topology must be stated so no reader over-reads it. Unblocks `EB-7`.

---

# Cluster 10 — Rulings that remain open

Both inputs agree these are **not** owner business decisions. They are Planner or Coordinator
technical authority and stay open. A plan may not read this file as deciding them.

`07` `DP-2`(closed by consequence — see Cluster 3), `DP-3`, `DP-4`, `DP-5`, `DP-8`, `DP-9`, `DP-10` ·
`08` `D-08-1`, `D-08-2`, `D-08-3`, `D-08-5`…`D-08-8`, `D-08-11` · `09` `DP-09-A`…`DP-09-F`, `DP-09-H` ·
`10` `DP-10-1`, `DP-10-3`, `DP-10-4`, `DP-10-5`, `DP-10-6`, `DP-10-8`…`DP-10-12` · `11` `DP-11-C`
… `DP-11-J` · `12` `DP-12-F`'s census-detail half, `C12-4`, `C12-5`, `O-26` · `13` `DP-13-A`,
`DP-13-E`, `DP-13-F`, `DP-13-J`, `DP-13-K`, `DP-13-L`, `DP-13-M`, `DP-13-N`, `DP-13-O` · `14`
`D-14-A`…`D-14-I` · `15` `D-15-E`, `D-15-F`, `D-15-J`, `D-15-K`, `D-15-L` · `16` `D-16-6`, `D-16-7` ·
`17` `D-04-B`, `D-04-E`, `D-04-G`, `D-04-K` · `18` `D-05-B`, `D-05-H`, `D-05-I`, `D-05-K`, `D-05-L`,
`D-05-M`, `D-05-O`, `D-05-P`, `D-05-Q`, `D-05-R`.

**If a block needs one of these to proceed, it names the gap in its commit body and proceeds without
inventing the answer.**

---

# Adjudication summary

| Decision | INPUT A | INPUT B | Ruled | One-line reason |
| -------- | ------- | ------- | ----- | --------------- |
| `DP-12-A` audience | (a) | C | **B** | Same content; B additionally covers the create path |
| `D-08-4` enforcement point | open | shared dep | **B** | Names one point; settles the two-owner collision |
| `DP-12-H` created_by | (a) | A | **B** | B states the removal requirement that makes it right |
| `DP-12-C` refusal code | (a) | A | **B** | B folds the layouts branch; no exception survives |
| `DP-12-B` ACL absence | (b) seq. | A | **B** | B ships the record and tests, not a status change |
| `DP-12-D` graphs inline | (a) | Planner | **A** | In scope, conditioned on the Auditor's comparison |
| `DP-12-E`/`D-04-I` behaviour | login+refresh | every request | **B** | Closes the mid-session hole |
| `DP-12-E` commit shape | two commits | Planner | **A** | Ordering is the mitigation |
| `DP-12-F` docstring/scope | (b)+(i) | Planner | **A** | Census must enumerate every minting path |
| `D-04-F` revocation read | — | fail open | **B** | Availability; WARNING log makes it non-silent |
| `DP-1` / `DP-10-2` liveness | (a) | A | **B** | Both agreed |
| `D-15-G`+`H` detailed health | strip, stay public | admin-gate | **A+B** | Gate **and** reduce, so a false outage is survivable |
| rate limiter posture | fail closed | Planner | **A** | Keep the shipped default; ≠ `D-04-F`'s surface |
| `DP-11-B` cap + count | (a)+(c) | C | **both** | Converged; count mandatory |
| `DP-11-A` ordering | atomic | Coordinator | **A** | No silent-truncation window, no unbounded interim |
| `DP-13-C` client signal | (b) | (b) | **both** | Converged |
| `DP-13-B` queryKey | one commit | Planner | **A** | Compelled by `DP-11-A` |
| `D-15-I` / `D-16-1` keys | widen only | widen + refuse | **B** | Refusal by name kills the silent-discard class |
| `D-16-2` range filter | dimension-only | remove | **B** | No confirmed semantics exists; do not invent one |
| `D-16-3` bar axis | (a) | (a) | **both** | Converged |
| `D-16-4` empty states | split | all four in 16 | **B** | Only B leaves all four distinguishable |
| `DP-13-D` error surface | (a) | Planner | **A** | Product decision; per-surface exemption |
| `DP-13-H` password authority | server | Planner | **A** | Client-only change; (b) has no owner |
| `DP-13-I` update-name | align+validate | Planner | **A** | No divergence survives |
| `D-15-A`+`B` 72 bytes | reject on mint | Planner | **A** | Only option that stops minting aliases |
| `D-15-C`+`D` credential store | (a) | A | **B** | Adds the numeric loss-window commitment |
| `DP-10-7`/`DP-11-H` budget | derive later | 50 GB | **A+B** | Number now **and** derivation published with it |
| RPO / RTO | 24 h / 4 h | — | **NEW** | Neither input covered restore acceptance |
| `DP-11-D` worker replicas | (a) | Coordinator | **A** | Ceiling published; alert reads zero until instrumented |
| `DP-09-G` coverage mask | measure first | remove | **B** | Measurement becomes a release-note precondition |
| `TST-013` skips | — | marker+owner/date | **B** | A skip is a commitment, not a deletion |
| `TST-003` 65 % floor | live on main | — | **NEW** | Makes a dead gate live; value unchanged |
| `D-16-5` hand-overs | defer 4 | Coordinator | **A** | Releases phase 13; states the honest state |
| `D-16-8` frontend coverage | after tests | Planner | **A** | Only ordering where enforcement is meaningful |
| `D-15-O` three seams | take all | Planner | **A** | Unowned-by-default is wrong |
| `D-15-N` token storage | memory-only prod | Planner | **A** | Dev opt-in flag retained |
| `DP-11` oversize reports | 413 on values | header+value | **B** | Preserves the diagnostic the endpoint exists for |
| `DP-6` body strictness | writes only | B | **B** | Same content; reads stay permissive |
| `DP-12` schema surface | app+hand-over | Planner | **A** | Records nginx as the real control |

**Count: 37 decisions adjudicated — 15 INPUT B, 16 INPUT A, 4 merged, 2 new.**