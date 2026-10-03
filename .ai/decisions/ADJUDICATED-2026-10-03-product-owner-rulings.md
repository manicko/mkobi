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

### `D-04-F` (plan 17) — revocation-read failure · ~~**`B`**~~ · **⚠ STRUCK — SUPERSEDED BY CLUSTER 14**

> **⚠ THIS RULING IS STRUCK, 2026-10-03, by cluster 14 (`Q-1`).** It is **not deleted** — a register that
> erases its own reasoning is a register that re-litigates — and the text below is left standing as the
> ruling that was made. **Read it as history: cluster 14 ruled the opposite, and the cluster-14 ruling is
> the one in force.**
>
> **What cluster 2 got wrong, and it is worth recording because the reasoning was sound and the
> conclusion was still wrong.** Cluster 2 reasoned that *"failing closed produces a mass logout that reads
> as a mass credential compromise."* **That diagnosis is correct and it is not the whole trade**: a mass
> logout that reads as a compromise is **visible**, and a degraded mode that admits revoked tokens is
> **silent**. Cluster 14's ruling rests on the asymmetry — **the session store is the session boundary, and
> a refusal is visible while a bypass is not.** The mass logout is an operational annoyance with a
> timestamp; the bypass is a security defect with no symptom. Availability does not win a question where
> the thing being bought with it is the user's own revocation.
>
> **What survives from cluster 2, and it is not nothing:** the WARNING-or-above logging requirement. **A
> fail-closed store fault still has to be logged at WARNING or above on every occurrence** — "fail loud"
> means the operator is told, not only that the user is refused. Cluster 14 carries this forward
> explicitly.

**The struck ruling, retained verbatim:**

**Fail OPEN, with a logged degraded mode.** The degraded mode **must be logged at WARNING or above
on every revocation-read failure** — a silent fail-open is not the ruling, it is the defect the
ruling forbids. Availability wins over strictness, because failing closed produces a mass logout
that reads as a mass credential compromise.

**Accepted, stated as a commitment:** a user deactivated mid-session retains access for the duration
of a Redis outage. Release note. **— NO LONGER ACCEPTED. This commitment is withdrawn by cluster 14;
a user deactivated mid-session is refused for the duration of a Redis outage.**

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
revocation-read path (`D-04-F`, plan 17) are separate. INPUT B's **revocation-read** ruling is **STRUCK
by cluster 14** - it applied to the revocation read only, and it no longer says what it said. It
never extended to the rate limiter, and **cluster 14's fail-closed ruling does not either.**
Both surfaces now fail closed, **for different reasons and by different routes**: the limiter is
an intentional documented default (`D-15-M`), the revocation read is a boundary (`cluster 14`). **Both
being fail-closed is a coincidence of direction, not a shared decision**, and a later reader
must not cite one as precedent for the other.
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

**> SUPERSEDED IN PART — amended 2026-10-03 (second session).** This cluster was written as a
> catch-all for records "not owner business decisions". **That blanket is no longer true.** Clusters
> **11**, **12** and **13**, appended below, rule a material part of the list below — the `D-05-*`
> domain-owner set (plans 05 and 18), `D-08-3`, `D-16-7`, `C12-4`, `DP-10-12`, `D-04-D`, `D-04-C`,
> `D-04-J`, `D-04-L` and the `D-04-*` records plan 17 inherits. **A plan must not read this cluster
> as deciding any record that cluster 12 now rules, and must not read it as *declining* to rule one.**
> A second fact of the same kind: several records this cluster lists as open were **already ruled and
> landed** in commits that predate this file — `D-04-B` (`1fd6e69`), `D-04-E` (`01ea7e4`), `D-04-I`
> (`62b859a`), `D-04-K` (`be0d779`) and the whole `D-05-*` set (see cluster 11 and plan 18 §1.3).
> **Production code is king: where the tree shows a record landed, this cluster's "open" is wrong and
> the plan is corrected to the tree, not the reverse.**

What remains true of the list below: every record **not** named in clusters 11–13 is still Planner or
Coordinator technical authority, still unpicked by the owner, and a block that needs one names the gap
in its commit body and proceeds without inventing the answer.

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

# Cluster 11 — Landed corrections (Tech Lead, 2026-10-03)

Two decisions in this corpus were ruled **and shipped**. Several plans and code-context files still
record them as open. **Correct every occurrence; do not schedule the work.** Both are corrections, not
rulings: they settle what the code already does.

**A third fact belongs here and is recorded once, because a plan must not be corrected against one
commit and left stale against its seventeen siblings.** **The whole of phase 04 and the whole of phase
05 have landed.** Every `AB-0`…`AB-11` block and every `PB-0`…`PB-18` block is in the tree, and each
commit body names the `D-04-*` / `D-05-*` ruling it executed. Plan 17 and plan 18 are therefore
**records of a completed phase, not queues**, and their decision registers read **RULED + LANDED**
rather than open. The per-record mapping is in plan 18 §1.3 and plan 17 §(f); a plan cites the commit,
never this file, for that table. **Two of those landed rulings contradicted this file** — `D-04-F` and
`D-04-L` — and both divergences were recorded verbatim where they were found rather than reconciled
here. **BOTH ARE NOW ARBITRATED: cluster 14 (2026-10-03) rules both, and this file has been amended to
match.** `D-04-F`'s cluster-2 entry is **struck in place** and points at cluster 14; `D-04-L`'s cluster-12
entry now records that the shipped `34c9459` is **reversed by a scheduled correction**. **This
paragraph is retained in its original tense deliberately: it records that a divergence existed and was
put to the owner rather than silently reconciled by a planner, which is the fact a later reader needs
most.**

### `D-05-E` (plans 05, 18) — dimension value canonicalisation · **RULED (a) and LANDED as `d865f2c`**

*"fix(storage): canonicalise dimension values so one category is one row"*

The rule **as implemented**, in `src/mkobi/data/storage/manager.py::_canonicalize_dim_scalar`:

| Input | Stored form |
| ----- | ----------- |
| `None` | `""` |
| `date` / `datetime` | ISO string, **keeping the `T` separator** |
| `int` / `float` / `bool` | `str(value)` |
| anything else | `str(value)` |

**`metrics` are deliberately not canonicalised** — the defect this record concerns is *dimension*
identity, and canonicalising a measure would re-key the aggregate on a value no chart filters by.

**Applied at all three write surfaces** (`manager.py:281`, `:407`, `:438`).

**Why the storage layer and not the writer.** The conflict target `text("((dims)::text)")` is evaluated
by PostgreSQL **on the value about to be inserted**, so the storage layer is the only placement where
the index key and the stored value are *provably* identical — and the only one covering all three write
surfaces, including a hand-built `save_aggregates` call that bypasses the service. Canonicalising in
the reader would hide the symptom and leave every stored row wrong.

**Residual, stated not eliminated:** already-split rows are **not** repaired; they are corrected by the
next overwrite-mode upload for that dashboard. A one-off remediation query is not in scope. The
`aggregated_data.ordinal` DDL and the canonicalisation index line remain a phase-14 hand-over (`C05-5`).

**Why `D-05-E` is on this cluster and not cluster 13.** Cluster 13's `P11` changes what a canonicalised
value *looks like* to a user and constrains how it *orders*. `P11-constraint` is explicit that it **does
not reopen `D-05-E` or the index identity**: the canonical text is the identity and storage
representation; ordering is derived from the semantic type of the source column, not from the stored
text. Two presentation surfaces are therefore new work and are named where they are owned — plan 18
(`extract_filter_values`, the option list, the read path) and plan 16 (axis labels and tooltips).

### `D-05-N` (plans 05, 18) — empty selection · **RULED (a) and LANDED as `ed644e7`**

*"fix(processing): fail an empty overwrite selection and guard the filter-value write"*

Implemented at `src/mkobi/workers/data_worker.py:1184-1213`:

- A graph is **"skipped"** when `AggregationService.aggregate_for_dashboard` returns no records for it.
- The guard raises `AppException(code=ErrorCode.PROCESSING_FAILED)` with a detail from
  `_empty_selection_detail` naming **up to `_MAX_SKIPPED_GRAPH_NAMES = 20` graphs**.
- The detail is **bounded** because `processing_logs.message` is `String(1000)`.
- The guard sits **before both clears**: `StorageManager.save_aggregates`' internal `delete_by_dashboard`
  **and** `DataService.clear_dashboard_values`. Guarding only one still loses data, and that is the
  whole correctness argument.

**No new `ProcessingStatus` member and no Alembic migration**: `FAILED` already exists with a frontend
renderer. This is the asymmetry with `D-05-F`(a), whose cost *is* a migration and is therefore a
hand-over to phase 14.

**Residual work, and it belongs to cluster 13.** The product-experience half is `P3` below, which
ratifies the shipped reason-naming message, forbids the settings link, and adds nothing to the shipped
text. **No finding is renumbered.**

---

# Cluster 12 — Technical rulings (Tech Lead owns these; the Product Owner was not asked)

**All fixed at option (a).** Record the ruling, its rationale in one or two sentences, and its residual
cost. **Do not re-open the alternatives** — a rejected option stays in its plan's table, marked
rejected, with the reason.

| Record | Plan(s) | Ruling | Rationale and residual |
| ------ | ------- | ------ | ---------------------- |
| **`D-05-C`** | 18 (`PB-6`) | `groupby` **without** `aggregations` keeps working, under an **explicit, written, deterministic rule**: collapse duplicate category rows **by first occurrence, after a deterministic sort**. The stored number changes; it becomes **reproducible**. **(b)** (reject the configuration) and **(c)** (delete the branch) are **rejected**. | Reproducibility is the finding; rejection and deletion both convert a working configuration into a new failure class. **Residual:** stored values change for every dashboard configured this way, and the "recalculates on first upload" note is `P4`'s obligation. **Landed `d4acdbd`.** |
| **`D-05-D`** | 18 (`PB-7`) | `limit` applies **after** aggregation, so it means **"top N by the aggregated metric"**. Stored values change; this is the meaning every reader already assumes. **(b)** reject `limit` without `sort_by`, and **(c)** require `sort_by` whenever `limit` is set, are **rejected**. | Both rejections create a new failure class for configurations that work today, and (b) rejects on a key the settings type did not declare. **Residual:** the value change, announced by `P4`. **Landed `67e28fa`.** |
| **`D-05-F`** | 18 (`PB-9`) | Data-quality warnings are **summarised into `processing_logs.message`** (`String(1000)`) under an **explicit cap and truncation rule**. **No new `ProcessingStatus` value and no migration.** The never-true `column_types` check **is fixed so it can become true**. | The status column is a native PostgreSQL ENUM, so option (a) is a migration and therefore phase 14's. **Residual:** a client rendering `processing_logs.message` now sees warning text where it saw only the completion sentence — and `P2` makes that text a first-class user-visible state. **Landed `b63589c`.** |
| **`D-05-G`** | 18 (`PB-8`) | The settings boundary is validated at the **worker edge, not at the API**. An unrecognised key is reported **naming the key**. **Existing stored payloads keep loading.** Option (a) (API-side `extra="forbid"`) is **rejected**: it applies a documented 422 **retroactively** to stored JSONB across every dashboard. **The fate of `ProcessingSettingsModel` is recorded explicitly.** | Retroactive rejection of stored data is not a fix, it is a migration without a migration. **Residual:** one runtime consumer must remember the key set, which is why `P5` requires the key to be named and linked. **Landed `31397db`, as an option (a′) — a fifth option forced by a real constraint: a `TypedDict` cannot emit `additionalProperties: false`, so the OpenAPI tripwire the plan demanded is unwritable against one.** `P5` supersedes the user-visible half of this ruling — see the note after the table. |
| **`D-05-P`** | 18 (`PB-10`) | The group-less `yoy` case **is fixed inside `PB-10`**, not filed. | Filing it would **ship a known order-dependent defect onto a newly-reachable path** — the same defect class `PB-6` and `PB-7` exist to remove. **Landed `a6ad7d2`.** |
| **`D-04-D`** | 17 (inherited from 04) | The abuse bound is keyed **per identifier as the primary bound, plus a generous per-IP ceiling**. **Per-IP-only is rejected**: an office NAT or a shared egress would lock out many legitimate users. | The availability hazard is half of `AUTH-001`; removing the IP bound abandons the other half. **Residual:** a deployment behind one egress has a ceiling that must be tuned, and the ceiling is deliberately generous. **Landed `659734e` then corrected by `5ac2ea3`, which raised the peer ceiling to 10× the identifier bound at every site** — the landed shape is exactly this ruling, which is why it is recorded as confirmed rather than new. `P7` adds only what the user is shown. |
| **`D-04-J`** | 17 (inherited from 04) | Ruled **per sub-question**: changing one's own password **does** end that user's other sessions; an administrative reset **does** end **all** of that user's sessions; refresh **does not** rotate the cookie. | The first two close a live window; the third would need reuse detection, whose cross-tab false-positive risk is the frontend's call. **Residual:** the presented refresh token stays valid until its own TTL. **Landed `4600e5d`, which also raised `D-04-M`** — a thirteenth record absent from this file. `P6` adds only what the user is shown. |
| **`D-04-C`** | 17 (inherited from 04) | A credential-store fault reports **503** and **fails loudly**. **404 is rejected** — it reads as "no temporary password exists" and hides an outage. | A status a client cannot distinguish from absence is a lie the administrator cannot detect. **Residual:** a 503 is indistinguishable from any other upstream outage by status alone; the detail string is the only discriminator. **Landed `478015b`.** `P9` adds only what the user is shown. |
| **`D-04-L`** | 17 (inherited from 04) | A non-admin account occupying the configured admin address logs a **WARNING naming the account and its role**, and **startup continues**. **Refusing to start is rejected.** | A boot failure on a configuration that is wrong *today and wrong invisibly* converts a misconfiguration into an outage. **⚠ SUPERSEDED IN ITS TREE-FACING HALF BY CLUSTER 14, which confirms this ruling and reverses the shipped `34c9459`, which raises `ValueError` in production.** The direction of travel is unchanged and the shipped code is now the thing that must move; the remaining open questions were the implementation shape and `P10`'s surface, and cluster 14 answers both. |
| **`D-16-3`** | 16 | Bar charts keep `'category'` as the **default** when the converted layout supplies **no** `xaxis.type`. Stored values are honoured; **no existing dashboard changes visually.** **Product sign-off given.** | The constant is removable on library grounds alone, and nothing in the repository asserts a bar trace needs a categorical axis — but honouring stored values is the direction `D-16-1` already chose, and a rendering change to every existing bar chart is a cost no product owner has agreed to pay. **Residual: none visual. The axis type becomes editable in graph settings instead — `P12`.** |
| **`D-16-7`** | 16 | `filterValues` freshness: invalidate on upload **and** pin an explicit **`staleTime: Infinity`**, so refresh is **event-driven** and the contract is legible. **Product sign-off given.** | An inherited finite default makes the invalidation redundant and hides that a list's freshness depends on every writer being remembered. **Residual:** `Infinity` makes the invalidation load-bearing — a second writer becomes a visible bug instead of a silent one. That is the intended dependency direction. |
| **`C12-4`** | 12 | The client-facing error-code vocabulary is assigned a **single registry owner: the Coordinator**, as a **cross-tier contract**. **Phase 12 files requests and does not edit the register.** | Three phases have claimed fragments of one vocabulary and none owns it; a register with three owners is three registers. **Residual:** the Coordinator must actually maintain it, and `AZ-11`'s notice is the first entry. |
| **`D-08-3`** | 08 (`CQLT-9`) | **Amend both documents.** The `ButtonVariant` / `ComponentSize` vocabulary is **presentation-side only and is not server-enforced**. **No stored layout can be rejected.** "Implement the declared validation" is **rejected** on the grounds that the accepted shape is **not derivable from the repository** and enforcement would reject existing stored layouts. | An implementor who guesses produces a validator that rejects the product's own layouts, against twenty live `definition=` call sites. **Residual:** the *integration* half of the finding stays open and must stay open until someone writes the shape down. |
| **`DP-10-12`** | 10 | The worker's liveness detection gets a **faster second probe plus a stop grace period**, keeping the existing slow proof-based check. **Retuning the single threshold alone is rejected** — faster detection, more false restarts. | The shipped wrapper judges a worker on a proof window of roughly eight minutes; moving one threshold trades detection speed for restarts of healthy workers. Two probes plus a grace period improve detection **without** that trade. |

### Two of these are superseded in part, not complete

- **`D-05-G` is superseded in its user-visible half by cluster 13 `P5`, and `P5`'s affordance is settled
  by cluster 14.** The boundary **stays at the
  worker edge** and the stored-payload compatibility is unchanged. What changes is what the user is
  shown: the message **names the exact key** — shipped in `31397db` — *and* the run must offer a route to
  remove it. **Cluster 14 rules the shape, and this paragraph is superseded on that point: the setting
  name travels as structured data in the RFC 7807 body, and the interface renders the control itself.
  The message text stays readable prose and carries no link-shaped string** — a link inside a
  1000-character `processing_logs.message` is the rejected option and must not reappear. Emitting side:
  plan 18's `PB-8`. Rendering side: plan 13's `DP-13-P`. **A plan that records `D-05-G` as "complete with
  nothing more to do" is wrong about the surface and right about the boundary.**
- **`D-04-D` is superseded in its user-visible half by cluster 13 `P7`.** The **bound is unchanged** —
  per-identifier primary with a per-IP ceiling. What changes is what the throttled user is shown.

---

# Cluster 13 — Product-experience rulings (Product Owner, 2026-10-03)

These answer questions **no phase previously owned**. Each is recorded in the plan that owns the
surface, with **the user-visible outcome stated as the acceptance criterion**. Where a ruling adds to a
cluster-12 ruling rather than replacing it, the addition is named — a plan must not record either half
alone.

| # | Surface and owner | Ruled — the user-visible outcome is the acceptance criterion | Rejected |
| - | ------------------ | ----------------------------------------------------------- | -------- |
| **P1** | **Upload completion** · plan 13 (the status renderer), plan 18 (`C05-11`) | After a successful upload the user **stays on the dashboard**. A **confirmation toast** appears, and the dashboard itself carries a **persistent status line** progressing **"Processing…" → "Updated at &lt;time&gt;"**. | redirect to a separate processing-history page · toast-only with no persistent indicator |
| **P2** | **A distinct warnings state exists** · plan 13 (the status renderer), plan 16 (`CHTB-5`) | **"Completed with warnings" is a distinct amber state, separate from the green "Updated".** The user can **open it to see what the warnings were**. | no separate state with an expandable warning link · log-only with nothing in the interface |
| **P3** | **Empty selection** · plan 18 (`PB-3`), ratified | The failed run shows the **reason naming the skipped graphs** and **no link** to the dashboard's graph or filter settings. Existing data is preserved. **Already implemented by `ed644e7`; this ruling ratifies it and adds nothing.** | adding a link to the settings screen · a generic message with no reason |
| **P5** | **An unrecognised setting key** - plan 18 (`PB-8`) to **EMIT**, plan 13 (`DP-13-P`) to **RENDER** | The run fails with a message **naming the exact key**, and the run **offers a route to remove it**. **This is cluster 13's addition to `D-05-G`; the boundary does not move.** **The affordance's shape is settled by cluster 14: the setting name is STRUCTURED DATA in the RFC 7807 body, and the interface renders the control itself - the message text carries no link-shaped string** | a message naming the key with no route to fix it (the user knows what is wrong and cannot do anything) - a generic validation message - **(cluster 14) an instruction in the message text with manual navigation**: it works once and then the user is guessing the path - **(cluster 14) literal link syntax in the message**: a link-shaped string inside a 1000-character log column is prose another surface has to parse |
| **P6** | **Session ended by a password change** · plan 17 (`AB-8`), plan 13 | The user sees the **normal login screen with no explanation**. | "Your session was ended because your password was changed" · a generic "session expired" notice |
| **P7** | **Rate limiting** · plan 17 (`AB-6`), plan 13 | The throttled user sees **"Too many attempts. Try again later"** — **no countdown, no remaining-attempts display**. **This is cluster 13's addition to `D-04-D`; the bound is unchanged.** | a countdown · a remaining-attempts display |
| **P8** | **Forced password change** · plan 17 (`AB-3`), plan 13 | After login the user lands on a **single reachable screen, "Set a new password", which states the reason. The rest of the application is inaccessible.** | a dashboard banner with the app still usable · login blocked with an error until an administrator resets the password |
| **P10** | **Non-admin occupying the admin address** - plan 17 (`AB-10`, and the `34c9459` reversal), plan 13 for the administration-area surface | A **startup log entry and a persistent warning in the administration area**, until it is resolved. **Its precondition is settled by cluster 14: startup NEVER blocks, in any environment, so the administration area is always reachable and this surface can exist at all** | startup log only (an operator not watching logs at boot never learns the deployment is misconfigured) - nothing surfaced (the current behaviour) - **(cluster 14) refuse in production only** - it makes a misconfiguration an outage in the environment that matters most - **(cluster 14) refuse in every environment** - same objection, uniformly |
| **P11** | **Dimension value presentation — one canonical value everywhere** · plan 18 (options, read path), plan 16 (axis labels, tooltips) | Dropdown options, chart axis labels and tooltips all show the **same canonical text form**, so a category supplied two different ways appears **once**, and **the value a user picks is exactly the value that is stored**. | preserve the native type for display · preserve the native type and de-duplicate silently · defer entirely |
| **P11-constraint** | **Canonical text is identity and storage, not ordering or presentation type** - plan 18 (ordering), plan 16 (axis order), and **plan 14 for the persisted type (cluster 14 hand-over)** | After canonicalisation, `"1"`, `"2"`, `"10"`, `"20"` must present and order as **1, 2, 10, 20** - **never** in text order as 1, 10, 2, 20. **Ordering is derived from the semantic type of the source column, not from the stored text.** Read this as a **constraint on the presentation layer only**: it does **not** reopen `D-05-E` or the index identity. **WHERE THE TYPE COMES FROM is settled by cluster 14: the declared type is PERSISTED alongside each stored aggregate, so already-uploaded data keeps its order permanently and editing the upload configuration does not retroactively reorder stored rows** | ordering by the stored text - **(cluster 14) deriving the type from the processing configuration at display time**, because an edit to that configuration would then change the order of data already uploaded |
| **P12** | **Chart axis type** · plan 16 | **Nothing in the chart interface.** The **graph settings screen shows the axis type explicitly and allows editing it**. | a one-off notice per graph on first render with a new axis type · nothing at all |
| **P13** | **Failure and recovery on the dashboard** · plan 16 (`CHTB-5`), plan 13 | The dashboard **keeps its last good data** with a marker **"data may be out of date — last updated &lt;time&gt;"**, and **a transient failure never leaves a chart empty**. | clearing the charts and showing an error · leaving the data with no marker |

### Edge cases the constraint implies, and who pins them

`P11-constraint` is only implementable once three answers exist, and **they are not assumptions** — the
owning block's **Researcher** pins them and the Implementor writes them down:

1. A value with **leading zeros** (`"007"`) must **not** be reordered as the number `7`.
2. **Scientific notation** (`"1e-07"`, which the shipped `D-05-E` rule produces **deliberately**) must
   **not** be reordered as a float.
3. The **empty string** must sort in a **defined** position.

### Known surfaces to verify and state, not to assume

Cluster 13 does not assert what a file does. Each of the following is **work to verify**, named so a
later reader can tell an assumption from a measurement:

- `services/aggregation_service.py::extract_filter_values` sorts with
  `key=lambda v: (isinstance(v, str), v)`, which places **all non-strings before all strings**. Once
  option values are derived from the canonical form this becomes **text ordering** — the exact defect
  `P11-constraint` forbids. **This is the primary work item for `P11`.**
- The **option list** is built in memory from **native-typed** records (`workers/data_worker.py:1246`)
  and saved to `dashboard_filter_values`. `P11` requires it to be **derived from the canonical form**
  instead. That is the work, stated as work.
- **Chart axis order** is set upstream by `AggregationService._apply_chart_sorting` on the Polars frame
  **before** coercion (`aggregation_service.py:61-62`), so it should already be native-ordered.
  **Verify this and record the finding. Do not assert it.**
- **Read-path ordering** currently falls back to `ORDER BY id`
  (`db/repositories/aggregated_data_repo.py:205`). Note the interaction with plan 18 `PB-15` / `D-05-K`
  (interim ordering) and plan 14 `MIGB-4`, so the same question is **not decided twice**.

### ~~Four questions that could not be applied without a further owner decision~~ — **ALL CLOSED, answered 2026-10-03**

> **This table is RETAINED as history and is fully superseded by cluster 14.** It records what was asked
> and what was known at the time; **the answers are in cluster 14**, and each row below names its ruling.
> **No row here is an open question any more.** It is kept because a register that erases what it asked
> cannot show whether an answer was an answer or a guess, and because the divergence paragraphs in
> the plans point at these identifiers.

**All four were answered on 2026-10-03, all at the recommended option, and all now superseded by cluster 14.**

| # | Divergence as it stood | The question as asked | Now |
| - | ----------------------- | ------------------- | --- |
| **Q-1** | **`D-04-F`.** Cluster 2 ruled the revocation read **fail OPEN, with a logged degraded mode**. The tree ships **fail CLOSED with a distinct outcome**: `5b6cceb` raises a co-located `RevocationStoreUnavailableError`, mapped to **503 `SERVICE_UNAVAILABLE`** on protected requests and on `POST /auth/refresh`, reasoning that a blanket fail-closed turns a Redis degradation into a mass sign-out. | **Which behaviour is authoritative — the register's fail-open, or the shipped fail-closed-with-503?** | **ANSWERED — (a).** Accept the shipped behaviour; **cluster 2 struck in place**, its reasoning retained and its reasoning's flaw named: the session store is the session boundary, and a refusal is visible while a bypass is silent. **Cluster 14.** |
| **Q-2** | **`D-04-L` with `P10`.** Cluster 12 rules a **WARNING naming the account and its role, and startup continues** — refusing to start is **rejected**. `P10` additionally requires a **persistent warning in the administration area**. The tree ships the opposite: `34c9459` **raises `ValueError` in production**. | **Should a non-admin occupant of the admin address be a startup log entry plus an administration-area warning in EVERY environment including production?** | **ANSWERED — (a).** Warn in every environment; **never block startup**. `34c9459`'s production branch is **reversed by scheduled correction** owned by plan 17's `AB-10`; `P10`'s surface is owned by plan 13's `CT-11` and is blocked by nothing but that reversal. **Cluster 14.** |
| **Q-3** | **`P5`'s remediation affordance.** `P5` requires the message to **name the exact key** (shipped in `31397db`) **and carry a route to remove it** (not shipped). The message is written into `processing_logs.message`, a `String(1000)` rendered by the client. | **Should the route be carried as structured data rather than as link syntax inside a 1000-character log message? And which phase owns emitting it?** | **ANSWERED — (a).** Structured data in the RFC 7807 body; **the interface renders the control**. Emitting: plan 18's `PB-8`. Rendering: plan 13's `DP-13-P`, **extended, not duplicated**. **Cluster 14.** |
| **Q-4** | **`P11-constraint`'s ordering source.** Ordering must come from the **source column's semantic type**, and nothing carries it alongside the stored value. `ordinal` supplies **position, not type**. | **Should the declared type be persisted with the aggregate, or derived at read time from the processing config's `column_types`?** | **ANSWERED — (a).** **Persisted.** It is a **schema change and therefore a hand-over to plan 14** at `MIGB-4`, kept separate from the `ordinal` question. **Cluster 14.** |

---

### The four open questions are CLOSED — all answered, all at the recommended option

**Raised 2026-10-03 by this file; answered 2026-10-03 by the Product Owner, all four at option (a).**
**The questions are retained, because a register that erases what it asked cannot show whether the
answers were answers or guesses.** Each row points at its cluster-14 ruling.

| # | What was asked | Status | Answered by |
| - | -------------- | ------ | ----------- |
| **Q-1** | `D-04-F`: cluster 2 ruled the revocation read fail-open; the tree ships fail-closed-with-503. Which is authoritative? | **CLOSED — (a).** Accept the shipped fail-closed behaviour and **amend cluster 2**. Cluster 2's entry is struck in place above, with its reasoning retained and its reasoning's flaw named. | **Cluster 14** |
| **Q-2** | `D-04-L` + `P10`: cluster 12 rules warn-and-continue; `34c9459` raises `ValueError` in production; `P10` needs a reachable administration area. Which startup behaviour? | **CLOSED — (a).** **Warn in every environment including production; never block startup.** The production branch is **reversed by scheduled correction**, not by an edit to `src/` in these documents. | **Cluster 14** |
| **Q-3** | `P5`: the remediation affordance — link syntax in the message, structured data, or text instruction? | **CLOSED — (a).** **Structured data in the RFC 7807 body; the interface renders the control; the message text stays readable prose.** Two homes, both recorded. | **Cluster 14** |
| **Q-4** | `P11-constraint`: where does the ordering type come from — persisted, or read from the processing configuration? | **CLOSED — (a).** **Persisted alongside each stored aggregate.** It is a schema change, therefore **a hand-over to plan 14**, and it is **not** satisfied by `aggregated_data.ordinal`. | **Cluster 14** |

---

# Cluster 14 — The four answers (Product Owner, 2026-10-03)

Four rulings, each closing a question this file raised. **All are option (a), and in each case that is
the option the report recommended — which is worth stating plainly, because a register where every
open question resolves to the suggested answer is a register someone should read sceptically. The
scepticism is warranted here in one direction only: option (a) was recommended because it was the
*least destructive to stored data and the least lossy of information*, not because it was the safest
default. Q-1 in particular **reverses** an earlier Product Owner ruling rather than confirming it, and
Q-2 **reverses shipped code**. A pattern of "recommended accepted" that never once rejects a
recommendation would be a signal; this set reverses two earlier positions and rejects two plausible
alternatives in each case.**

---

### Q-1 · `D-04-F` — revocation-read failure · **RULED: fail CLOSED, with a dedicated 503**

**The ruling.** **Accept the shipped behaviour** — `5b6cceb`, a co-located
`RevocationStoreUnavailableError` mapped to **503 `SERVICE_UNAVAILABLE`** on protected requests and on
`POST /auth/refresh` — **and amend cluster 2**, which is struck in place above rather than overwritten.
A revocation read over a healthy store still answers 401 `TOKEN_REVOKED`, so the genuinely-revoked case
is unchanged and **only the unreachable case is in scope here**.

**The reason, and it is the whole ruling.** **The session store is the session boundary, and a refusal
is visible while a bypass is silent.** Cluster 2's reasoning — that failing closed produces a mass
logout reading as a credential compromise — is correct about the *symptom* and silent about the
alternative one: a degraded mode that admits revoked tokens has **no symptom at all**. **The mass logout
is an operational annoyance with a timestamp; the bypass is a security defect with none.** Availability
does not win a question where the thing being bought with it is the user's own revocation.

**What survives from cluster 2 and is carried forward: the logging requirement.** **Every revocation-read
store fault must be logged at WARNING or above**, fail-closed or not. "Fail loud" means the operator is
told, not only that the user is refused — and this is the one part of cluster 2 that cluster 14 does not
discard, because a 503 with no log line is an outage nobody can diagnose.

| Option | Disposition |
| ------ | ----------- |
| **(a) Accept the shipped fail-closed with a dedicated 503, amend cluster 2** | **RULED.** Already implemented; the ruling is a confirmation plus a register correction, which is why it is cheap. |
| **(b) Fail open with a logged degraded mode** | **REJECTED — and it is the rejected option that a reader is most likely to reach for**, because it is what cluster 2 said and because availability arguments are intuitive. Its cost is silent: a deactivated or revoked user keeps access for the duration of an outage and nothing anywhere says so. |
| **(c) Fail closed *plus* a bounded degraded mode** | **REJECTED, and the report flagged it as acceptable, so the reason must be stated rather than assumed.** It was put to the owner because it honours both cluster 2's stated reason and `5b6cceb`'s: refuse when the store is unreachable, but admit during a **short bounded** window so a Redis restart is not a mass logout. **It is rejected because the bound has to be a TTL on the revocation marker, and a TTL is exactly the defect `D-04-M` exists to fix.** `D-04-M` (cluster 12, plan 17) exists because a bare existence marker cannot distinguish an already-issued credential from one minted afterwards; a degraded mode reintroduces precisely that ambiguity, with a window in which it is exploitable. **Option (c) is not rejected as a bad idea — it is rejected as a collision with a ruling this same register made two hours earlier, and that collision is the reason.** |

**Residual work: none in code.** The behaviour shipped in `5b6cceb`; `87dd36d` added the OpenAPI half and
removed the 503 `407d770` had wrongly added to `auth_public_responses`. **What remains is documentation
and one record:** plan 17's `D-04-F` row, plan 04's `D-04-F` row and `AB-5`'s options table must stop
describing the fail-open default, and any document asserting it must be corrected in plan 04's `AB-11`
documentation scope. **No new `ErrorCode`** — `SERVICE_UNAVAILABLE` already exists and needed no frontend
entry.

---

### Q-2 · `D-04-L` with `P10` — non-admin occupant of the admin address · **RULED: warn in every environment; never block startup**

**The ruling.** **A non-admin account occupying the configured admin address logs a WARNING naming the
account and its role, and startup continues — in production, in development, and in every environment
between them. Refusing to start is rejected outright.** This **confirms cluster 12's ruling** and
**reverses the shipped `34c9459`**, which raises `ValueError` in production and warns only in
development.

**Why the reversal is scheduled work and not an edit.** `src/` is outside the scope of this document
pass, and a register that narrates a code change without scheduling it is how a ruling dies. The
correction is therefore recorded in **plan 17** as a named, owned, blocked-on-nothing item, and
`34c9459`'s own commit body — which says *"the boot path can now fail where it previously continued
silently"* — becomes the description of the defect being corrected rather than of the intended state.

**The reason, which is cluster 12's and is not re-argued.** A boot failure on a configuration that is
wrong *today and wrong invisibly* converts a misconfiguration into an outage. **The stronger reason is
`P10`:** a persistent warning in the administration area is **unreachable in a deployment that refuses
to boot**, so a production refusal and `P10` are mutually exclusive. Cluster 14 chooses `P10`, and the
startup behaviour follows it rather than the other way round.

| Option | Disposition |
| ------ | ----------- |
| **(a) Warn in every environment, never block startup** | **RULED.** The only option under which `P10`'s administration-area warning can exist at all. |
| **(b) Refuse in production only** | **REJECTED.** It has the objection in its most concentrated form: the environment that matters most is the one that refuses to boot, and a development environment that continues would teach an operator that the check is advisory. |
| **(c) Refuse in every environment** | **REJECTED.** Same objection, uniformly — and it is strictly worse than (b), because it also removes the operator's chance to fix the misconfiguration from inside the running system. |

**Residual work — scheduled, not performed.**
- **The reversal itself**, owned by **plan 17's `AB-10`** (`ensure_admin_user` in
  `services/starter.py`): the production branch of `34c9459` becomes a warning. **It is a one-branch
  change and it touches no stored row**, which is why it is cheap and why it was not worth a migration
  debate.
- **`P10`'s administration-area warning**, owned by **plan 13** (`CT-11`, the administration area). **Its
  blocker is the reversal above and nothing else**: once startup never blocks, the surface exists and can
  be built. **Recording that dependency explicitly is the point of this ruling** — before it, `P10` was
  blocked by an unbuildable precondition, and the two looked like one unresolved question rather than a
  ruling and its consequence.
- **The `rowcount` branch and the minimal `SELECT` are unchanged** — `role` and `id` only, no
  `password_hash` read, no credential logged. Cluster 14 rules a log line, not a query.

---

### Q-3 · `P5` — the remediation affordance · **RULED: structured data, interface-rendered control**

**The ruling.** **The failure response carries the setting name as structured data, and the interface
renders the control itself. The message text stays readable inside the 1000-character
`processing_logs.message`.**

**The boundary, stated explicitly because it is the ruling's substance: the backend supplies the fact,
the client owns the affordance.** The backend's obligation is to make the offending key *machine-
readable*; the client's is to present a way to remove it. Neither is asked to do the other's job, and
the sentence is written here because the two homes were previously recorded as one ambiguous sentence
("the message carries a link") that quietly assigned the affordance to whichever surface happened to be
reading the message.

**Two homes, both recorded, and neither is optional.**

| Home | Owner | What it owes |
| ---- | ----- | ------------ |
| **Emitting** | **Plan 18, `PB-8`** — the worker/settings boundary | The **RFC 7807 body** carries an `ErrorCode` **plus the offending key** as a named field, so nothing link-shaped is embedded in a log message. **Note that `31397db` shipped the naming as prose inside `processing_logs.message`, which is the half that stays and is correct; what cluster 14 adds is the machine-readable field alongside it, not a replacement for the prose.** |
| **Rendering** | **Plan 13, `DP-13-P`** — the existing status-renderer record, **extended rather than duplicated** | The client renders the **control** — a control that navigates to the settings screen and names the key — from the structured field. **`DP-13-P` is extended; no second record is created**, because the renderer is the same component and a second record would split one surface across two plans. |

| Option | Disposition |
| ------ | ----------- |
| **(a) Structured data in the RFC 7807 body; the interface renders the control** | **RULED.** The message stays prose, the affordance becomes a control, and **no surface has to parse another surface's output.** |
| **(b) An instruction in the message text, with manual navigation** | **REJECTED.** It works exactly once — the first time the user reads the sentence — and after that the user is guessing the path to the settings screen. **It also pushes the cost of an affordance onto prose, where it cannot be tested.** |
| **(c) Literal link syntax in the message** | **REJECTED, and it is the option that must not reappear.** A link-shaped string inside a 1000-character log column is **prose that another surface has to parse**: it must survive escaping, truncation, log aggregation that strips markup, and a reader that renders the column as plain text. **The 1000-character bound is what makes this concrete rather than theoretical** — a message long enough to be useful is long enough to be truncated, and a truncated link is worse than no link. |

**Residual work.** Both halves are unbuilt and both are named. **The boundary does not move**: `D-05-G`
remains validated at the worker edge with existing stored payloads still loading, and cluster 14 changes
only what travels in the failure response and what the client does with it.

---

### Q-4 · `P11-constraint` — the ordering type source · **RULED: persisted alongside each stored aggregate**

**The ruling.** **The dimension's declared type is persisted alongside each stored aggregate.** Two
properties follow, and they are the ruling: **the order of already-uploaded data stays correct
permanently**, and **editing the upload configuration afterwards does not retroactively reorder stored
rows.**

| Option | Disposition |
| ------ | ----------- |
| **(a) Persist the declared type alongside each stored aggregate** | **RULED.** The order is a property of **the data**, not of **the configuration that happened to produce it**, and only a persisted source makes that true for rows that already exist. |
| **(b) Derive the type from the processing configuration at display time** | **REJECTED, and the reason is a single sentence: an edit to that configuration would change the order of data already uploaded.** A user who corrects a `column_types` entry would silently see every previously-uploaded category list reshuffle — **with no upload, no run, and no entry in any history to explain it.** That is the same class of defect as `P4`'s "recalculates on first upload", except there the change is attributable to a run and here it is attributable to nothing. |

**This ruling is a schema change, and that is its most important consequence.** By the project's
migration rule it is therefore **a hand-over to plan 14** — recorded there at `MIGB-4`, alongside the
existing `MIGB-*` blocks and the `C05-5` / `C06-3` discipline already described in that plan. **No
migration is authored in this document pass, and none may be authored in plan 18 or plan 16.**

**What this ruling does *not* do, and the distinction is load-bearing.**

- **It does not satisfy itself via `aggregated_data.ordinal`.** The two must **not** be merged.
  `ordinal` supplies **position**; `P11-constraint` requires **type**. A column that says *where a value
  sits in the order* cannot tell a reader *how to order the next value*, and the three edge cases cluster
  13 named — leading zeros, scientific notation, the empty string — are all cases where a position and a
  type give different answers.
- **It does not reopen `D-05-E` or the index identity.** Canonical text remains the identity and storage
  representation. The persisted type is **additional data about how to present that identity**, not a
  change to what the identity is.
- **It does not collide with `P11-sub`.** `1` and `1.0` remain **distinct categories**, so **a numeric
  type must not collapse them**: `"1"` sorts before `"1.0"` as two values of one numeric type, and any
  implementation that normalises `1.0` to `1` on the strength of "it is a number" violates `P11-sub` while
  claiming to satisfy `P11-constraint`. **This is the most likely way to get this ruling wrong**, and it
  is recorded in the hand-over so the implementer meets it before writing the column, not after.

**Residual work, in three places, all named.**
- **Plan 14, at `MIGB-4`** — the persisted-type DDL hand-over, kept separate from the `ordinal` question
  (`D-05-K`, plan 18's `PB-15`).
- **Plan 18, from `PB-5`** — the write-side hand-over: what the aggregate store must persist alongside
  each dimension value. **Plan 18 authors no migration** (`R-05-12`); it names the obligation and hands it
  over.
- **Plan 13 and plan 16** — the read and presentation side, which render an order they are given and
  **compute none**.

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
| ~~`D-04-F` revocation read~~ → **cluster 14** | — | ~~fail open~~ → **fail closed, 503, shipped `5b6cceb`** | ~~**B**~~ → **A (cluster 14)** | **Cluster 2's availability rationale is struck: the session store is the session boundary, and a refusal is visible while a bypass is silent. The WARNING-or-above logging requirement survives** |
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

**Count: 37 decisions adjudicated — 15 INPUT B, 16 INPUT A, 4 merged, 2 new.** *(Clusters 1–10
only. Clusters 11–13 are counted separately below and are **not** merged into this table: clusters
11–13 are corrections and fresh rulings, not reconciliations of two inputs.)*

**Clusters 11–13 at a glance.**

| Cluster | Records | Nature |
| ------- | ------- | ------ |
| **11** | `D-05-E`, `D-05-N` | **Corrections.** Ruled *and already shipped*; plans and code-context files that still record them as open are stale and must be corrected, not scheduled. |
| **12** | `D-05-C`, `D-05-D`, `D-05-F`, `D-05-G`, `D-05-P`, `D-04-D`, `D-04-J`, `D-04-C`, `D-04-L`, `D-16-3`, `D-16-7`, `C12-4`, `D-08-3`, `DP-10-12` | **Technical rulings**, Tech Lead's authority, the Product Owner not asked. All option (a). Two — `D-05-G`, `D-04-D` — are **superseded in their user-visible half** by cluster 13. |
| **13** | `P1`…`P13`, with `P11-sub` and `P11-constraint` | **Product-experience rulings.** Each answers a question no phase previously owned; each is recorded in the plan that owns the surface, with the user-visible outcome as the acceptance criterion. |

| **14** | **Q-1** `D-04-F`, **Q-2** `D-04-L`+`P10`, **Q-3** `P5`, **Q-4** `P11-constraint` | **The four answers.** All at option (a). Two reverse earlier positions — cluster 2's `D-04-F` (struck in place) and the shipped `34c9459` (reversed by scheduled correction). Two are **schema-touching hand-overs with named owners**, not code changes. |

**Cluster 11–14 total: 34 records** — 2 corrections, 14 technical rulings, 14 product-experience
rulings, 4 answers. **Combined with clusters 1–10: 71 records of record in this file.**

**Reconciled open-record count — updated 2026-10-03 after cluster 14. TWO CATEGORIES, DELIBERATELY NOT
MERGED, because they belong to different people.**

### A. Awaiting the **Product Owner** — **ZERO.**

**No record in this file awaits an owner decision.** All four questions this register raised are answered
(cluster 14), and the two earlier rulings that disagreed with the tree have been arbitrated rather than
left open: `D-04-F`'s cluster-2 entry is **struck in place** and replaced by cluster 14, and `D-04-L`'s
cluster-12 entry is **confirmed with the shipped code reversed by scheduled correction**. **Two schema
consequences were created by cluster 14 and both are hand-overs with named owners, not open questions:
`P5`'s structured error body (plan 18 `PB-8` to emit, plan 13 `DP-13-P` to render) and `P11-constraint`'s
persisted type (plan 14 at `MIGB-4`, from plan 18's `PB-5`).**

### B. Open with a **technical** chooser — these are the Tech Lead's, not the Product Owner's.

| Count | Records | Chooser |
| ----- | ------- | ------- |
| **1** | `D-16-6` (`CHT-003` vs phase 12's `AZ-8`: serialise, co-commit, or defer) | **Coordinator** |
| **9** | plan 08 `D-08-1`, `D-08-2`, `D-08-5`, `D-08-6`, `D-08-7`, `D-08-8`, `D-08-9`, `D-08-10`, `D-08-11` | **Tech Lead**, one with **phase 14** and one with **phase 03/04** informed |
| **1** | `D-04-G` (what lands first: the docstring correction or the core block — largely moot by block order, retained deliberately) | **Planner** |
| **plan 09's own** | `VAL-09-004` / `C09-3` (the rate limiter's `fail_closed=True` default, after the 2026-10-03 ruling was withdrawn) · `DP-09-A` … `DP-09-H` | **Planner** |
| **plan 13's own** | the **ten** unpicked `DP-13-*` — `A`, `E`, `F`, `G`, `J`, `K`, `L`, `M`, `N`, `O` | **Tech Lead / Planner / Coordinator** as each row states |
| **plan 11's own** | `DP-11-A` … `DP-11-H`, `DP-11-J` and the rest of its register | as each row states |

### C. Ruled and closed, but **found in the tree and absent from a plan's declared set**

| Count | Record | Why it is listed separately |
| ----- | ------ | --------------------------- |
| **1** | `D-04-M` | **RULED and LANDED** in `4600e5d`, raised by the Tech Lead during `AB-8` because the first `D-04-J` implementation could not express credential rotation. **It is now recorded in plan 17's register *and* plan 04's**, so the two agree. **Not a divergence and not open** — a correctly-ruled record that no plan had declared. |

### Movement across this pass

| Pass | Movement |
| ---- | -------- |
| Clusters 11–13 | plan 18 **−16 open**; plan 17 **−10 open** and its register section **restored**; plan 16 **−1 open**. **+25 rulings applied, +1 record found.** |
| Cluster 14 | **−4 owner questions, all closed.** **+2 hand-overs created** (both schema-touching, both with named owners). **+2 reversals scheduled** (`34c9459`'s production branch; cluster 2's `D-04-F` entry struck in place). **+1 record added to plan 04.** |
| **Net, all passes** | **Owner-decision queue: 4 → 0. Technical-chooser queue: 22 → 20.** |
