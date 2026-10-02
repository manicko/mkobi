---
audit_phase: 07-external-boundary
finding_prefix: EXT-
validation_prefix: VAL-07-
report: .ai/audit/99-validation/07-external-boundary-validated-findings.md
code_context: .ai/plans/_code-context/07-external-boundary-code-context.md
code_context_authority: Phase-1 Auditor (overrides every report anchor)
source_head: cea2d06
blocks: 10 (EB-0 … EB-9)
decisions: 12 (DP-1 … DP-10 carried verbatim from the code context; DP-11, DP-12 raised by this Planner)
findings_owned: 6 whole (EXT-003, EXT-006, EXT-007, EXT-009, EXT-010, EXT-008-verification-only) + 2 halves (EXT-001 probe measurement, EXT-002 residue)
findings_handed_over: EXT-004, EXT-005 whole; EXT-001 deployment half; EXT-002 refusal class
status: planned
---

# Phase 07 — External boundary remediation plan

## Purpose

This plan decomposes the phase-07 external-boundary findings into dependency-safe execution blocks.
It is deliberately **small**: the code context re-derived this phase at `cea2d06` and found that five
of the ten findings are already owned by executed or in-flight sibling plans, one is already fixed,
and the genuinely unowned residue is six findings and two halves.

Every block names a **semantic** target (symbol · module · route · config key · environment variable),
the `EXT-*` and `VAL-07-*` identifiers it discharges, its `blocked_by`, its position in the
single-implementor queue, a risk view across implementation / rollout / regression / compatibility,
the agents it needs, its documentation impact, named verification, and its definition of done.

**It chooses nothing where technical uncertainty exists.** `DP-1` … `DP-10` are carried verbatim from
the code context, each with its alternatives, its chooser and what stays blocked until it is ruled.
Two further decisions — **`DP-11`** and **`DP-12`** — are raised here because a fix genuinely turns
on a fork the code context's list is silent about; each says so, and each is marked *raised by this
Planner*, following phase 04's `D-04-I` … `D-04-L` precedent.

Scope discipline: **the audit corpus is not an implementation target.** No block edits
`.ai/audit/**`, `.ai/plans/_code-context/**`, or any sibling plan. If the owner wants the report
repaired, that is a separate authorised authoring task.

## Anchor authority

> **The report's line numbers are not binding, and neither are the code context's.**
> `VAL-07-009` records nine anchors that moved under the validation itself; the code context §1.1
> records nine more commits landing after the report's `c3c0a61`, of which `2de4156`, `9c49c20` and
> `4a5db54` move or refute `EXT-*` targets outright. The code context resolves against `2174895`;
> `HEAD` is now `cea2d06`.
>
> **Every anchor in this plan is a symbol, a module, a contract, a route, a config key or an
> environment variable.** Implementors resolve targets by symbol at the moment of work. If a symbol
> named below does not exist, that is a finding: stop and report it rather than substituting the
> nearest match.

### Anchor-authority precedence

**`report`** = `.ai/audit/99-validation/07-external-boundary-validated-findings.md`
**`code_context`** = `.ai/plans/_code-context/07-external-boundary-code-context.md`
**`code_context_authority: Phase-1 Auditor (overrides every report anchor)`** — where the two disagree
about *where* something is or *what the code does*, the **code context wins**: the report's coordinate
becomes a **drift-list entry, not a remediation target**. Where they disagree about *identity* (which
finding is which), the **report's identifier set wins** and the code context's numbering is recorded as
a **defect** — no `EXT-*` or `VAL-07-*` identifier is renumbered, re-typed or re-scoped by this plan.

**A runtime or tree observation is current-state evidence, not a third authority.** This plan measured
`/health` and read the container posture **read-only**, and a later implementor who finds the tree has
moved must **re-read the named symbol and record the drift** — never silently re-rule a `DP-1 … DP-12`
record. Precedence is therefore: **code context for fact, report for identity, and a later tree for
neither.**

**Anchors that are dead and must not be spent.** Every `admin.py` approval anchor the report cites
(`admin.py` approval-body lines for `create_user`, `force_password_change`, `uuid4`, `store`,
`update_status(APPROVED)`, `db.commit()` and the rollback arm) **names nothing** — those bodies are
`services/auth_service.py::AuthService.approve_registration_request`. The literal `version="1.0.0"`
is **not** in `app.py`; `app.py::create_app` reads `config.app.version` and the literal lives in
`config.py::AppSettings.version`. A Redis `PING` component **exists on neither** health endpoint
today. Phase 04's `AB-0` (finding `Y-01`) independently reached the same conclusion about the
`admin.py` anchors; two planners, one result.

### Refuted claims this plan does not carry

Each was verified against `cea2d06` while writing this plan. A block that acted on any of them would
be acting on a claim the code context already refuted.

| Refuted claim | Reality at `cea2d06` | Recorded by |
| ------------- | ------------------- | ----------- |
| EXT-001: "`Select-String redis` over `app.py` returns zero matches" | **5 matches** — `app.py` imports `get_async_redis_client`, uses it for the reconciler lease, and names it in three comments | EB-0, EB-1 |
| EXT-001: "the dev override disables the container healthcheck" | **Refuted** — `docker/docker-compose.override.yml` inherits the base healthcheck, with an explicit comment saying so; re-enabled by `9c49c20` | EB-0, EB-1 |
| EXT-001: "no shipped test blocks a Redis component" | **Refuted** — `tests/test_health.py::TestHealthWithRedisDown::test_health_still_healthy_when_redis_down` asserts `response.json() == {"status": "healthy", "database": "connected"}`, an **exact-dict equality** | EB-1, `DP-2` |
| EXT-003: "the one shipped caller is `ErrorBoundary.tsx:40`" | **Refuted** — that file is 47 lines and makes no such call; there is **no** `client-errors` reference anywhere in `frontend/src/` | EB-0, EB-3 |
| EXT-004: "the email branch is unreachable" | **Refuted for `register-request`** — `api/routes/auth.py` declares `client_ip: str \| None = None` and assigns it only under `if request.client:`, so the email branch is reachable exactly when the peer is absent | EB-0 (hand-over note only) |
| EXT-007: "a malformed `filters` yields an empty result set or a later error rather than a 422" | **Refuted for malformed JSON** — `api/routes/data.py` maps `json.JSONDecodeError` to a 422-class `AppException`. What is unvalidated is the **document shape** of a well-formed object | EB-0, EB-5 |
| EXT-009: "`rq` is never imported" | **Refuted** — imported by exactly **two** `src/` modules (`src/mkobi/rq_worker_wrapper.py`, `src/mkobi/core/task_queue.py`), four import statements in all | EB-0, EB-6 |
| EXT-009: "reduce `REQUIRED_MODULES` to the twelve the application imports" | **Refuted** — `REQUIRED_MODULES` is **thirteen** names, and the count of gate-only names is **three**, not four | EB-0, EB-6 |
| EXT-010: "`app.py` passes the literal `version=\"1.0.0\"`" | **Refuted as written** — `app.py::create_app` reads `config.app.version`; the literal is in `config.py::AppSettings.version` | EB-0, EB-8 |
| VAL-07-005: "on a publish failure compensate the committed record (mark the request failed and remove the account)" | **Refuted in effect** — contradicted by a shipped test, two landed docstrings and a shipped doc. **Not scheduled anywhere in this plan** | EB-0, EB-9 |

### Planner-required re-derivations

The code context §6 states, for `EXT-007`: *"The Planner must re-derive the exact set by symbol, not
by count."* The same discipline applies to `EXT-009`, and both were re-derived here. **Two
corrections to the code context follow, and both change what the implementor should do.**

| Subject | Code context's figure | Re-derived at `cea2d06` | Consequence |
| ------- | ---------------------- | ------------------------ | ----------- |
| `EXT-007` — request-body models | 20 regex candidates, "0 of 21" load-bearing | **Unchanged in substance.** Seven `extra` policies exist: one `extra="forbid"` (`models/transformation_configs.py::TransformationConfig`) and six `{"extra": "allow"}` (`models/types.py`'s internal runtime-validation models). Every route-shaped body model resolves with `extra` unset, i.e. Pydantic v2's `extra="ignore"` | The **exact set** is EB-5's Auditor deliverable, enumerated by symbol in the commit body — not by count |
| `EXT-009` — `rq` import sites | "**39 matches**" (a text census) | **4 import statements across 2 `src/` modules**: `import rq`, `from rq.defaults import …`, `from rq.worker_registration import …` in `src/mkobi/rq_worker_wrapper.py`; `import rq` in `src/mkobi/core/task_queue.py` | `rq` is genuinely imported and stays. The "39" was a text count, the same class of error the report made with its own `BaseModel` count |
| `EXT-009` — `httpx` status | "0 `src/` import sites → still gate-only" | **Misfiled tier.** `httpx` has **zero** `src/` import sites but is imported by `tests/conftest.py` (`import httpx`, `from httpx import ASGITransport`) and by **~20** test modules as `AsyncClient`. It is a genuine **test-tier** contract declared in `pyproject.toml` `[project].dependencies` and gated at **application startup** | `httpx` is **not** a certified absence. It is a tier mismatch. This is the sharpest thing in this block and it changes the remedy from "drop the name" to "the name is real but belongs to a different gate" |
| `EXT-009` — `plotly` / `tenacity` status | "still gate-only" | **Genuinely certified absences.** Zero references in `src/`, `tests/`, `docker/` and `alembic/`. `plotly`'s only `src/` mentions are two docstrings; the project's charting is Plotly.js in `frontend/`, an npm dependency, not this wheel. Both are declared **runtime** deps in `pyproject.toml` | Two dead runtime dependencies. Dropping them from `REQUIRED_MODULES` while leaving them declared in `pyproject.toml` is incoherent — see **HO-1** |

`tests/test_task_queue.py::TestServicesDoNotImportRq::test_no_service_module_imports_rq` asserts, by
AST walk, that **no module under `src/mkobi/services/` imports `rq`**. Neither of the two real import
sites is a service module, so that shipped layering rule is satisfied today and **must stay satisfied**
— it is the reason `rq`'s presence in `main.py::REQUIRED_MODULES` is defensible as the *worker*
entrypoint's contract.

### Source tree state at plan time

`git log --oneline -3` → `cea2d06`, `2174895`, `b646ef1`. The tracked working tree carried no
modifications when this plan was written. `2174895` and `cea2d06` are outside every `EXT-*` target.
Commits that **do** intersect this phase's targets, all already landed: `2de4156` (EXT-008 fixed;
EXT-005 anchors dead; VAL-07-005's outcome contradicted), `9c49c20` (dev healthcheck re-enabled;
`health-api.md`'s probe decision added), `4a5db54` (third `/health/detailed` component plus the
blocking shipped test), `3848e7a` (RQ made real), `d008f55` (`app.py` CORS guard moved).

**Two files are the repo's highest-churn and are targets here.** `config.py` is under concurrent
phase-01/02 work and is touched by EB-2 (`DP-3` option b) and EB-8. `app.py` is touched by EB-1 and
EB-7. Any implementor must re-resolve both by symbol immediately before editing, and re-check
`git status`.

## Scope-ruling tables

### IN — owned by this plan

| Finding | Severity | Short name | Block |
| ------- | -------- | ---------- | ----- |
| **EXT-001** (probe-measurement half) | HIGH | The probe reports `healthy` while every authenticated request fails | **EB-1** |
| **EXT-002** (residue only) | HIGH | The Redis transport bound is a library default nobody pinned | **EB-2** |
| **EXT-003** | HIGH | An anonymous 5 MB body is written verbatim into one ERROR record | **EB-3** |
| **EXT-006** | MEDIUM | The credential check runs after the router's slash redirect | **EB-4** |
| **EXT-007** | MEDIUM | No request-body model declares a strictness policy | **EB-5** |
| **EXT-008** | MEDIUM | *(already fixed)* — verification scope and non-scheduling only | **EB-9** |
| **EXT-009** | LOW | The startup self-check certifies libraries the app never imports | **EB-6** |
| **EXT-010** | LOW | The schema document advertises a stale version; half the gate is missing | **EB-7** (tier half), **EB-8** (version half) |

### OUT — not owned here, with the named home

| Item | Home | Note for this phase |
| ---- | ---- | ------------------- |
| **EXT-004** — the whole inbound budget collapses onto the proxy's address | merged → phase 04 **AB-6** (rate-limit key identity) + **AB-7** (proxy trust) | Plan 04 is at `source_head: 2174895` and **has already applied** `VAL-04-001`: option (b)'s `forwarded-allow-ips="*"` is **deleted, not deferred**. `VAL-07-002`'s wildcard prohibition is therefore a **closed decision** and this plan inherits it without re-opening it. See **HO-1**. |
| **EXT-005** — approval returns 200 and a handle for a credential never stored (write side) | merged → phase 04 **AB-1** | The defect survives with a deliberate shape; `VAL-07-005`'s prescribed compensation is refuted in effect. Carried, not re-planned. |
| **EXT-005** (read side) — one 404 for two states | merged → phase 04 **AB-2** | Plan 04 records the same two-state finding (`Z-14`). |
| **EXT-002** (refusal class) — a Redis error on the revocation read becomes `401 AUTHENTICATION_FAILED` | merged → phase 04 **AB-5** | `ErrorCode.SERVICE_UNAVAILABLE` **exists** and is already mapped to 503 (`VAL-07-003` applied). **No new enum member.** See **HO-2**. |
| **EXT-001** (deployment half) — the Docker healthcheck, `start_period`, the worker-count interaction | phase 02 **B3 / TOPO-008** — **landed** as `9c49c20` | Do not re-litigate the dev-vs-prod healthcheck. |
| **EXT-001** (deployed composition: nginx, load balancers, Kubernetes probes) | phase 10, as **co-owner** of the probe contract | Appendix F's ruling stands: co-owned, **not merged**. 07 owns what the probe *measures*; 10 owns the *deployed composition*. |
| **EXT-003** — what credential material reaches any other sink | phase 15 | Appendix F: cross-reference, not merged. The **volume** half is EB-3's; the **sink** question is phase 15's. |
| **EXT-003** — "the volume bound is a shared pool" | phase 04 **AB-6** | This is a *reasoning* dependency, not an edit dependency: EB-3 can ship without it, but the shared-pool half of the consequence cannot be reasoned about until it lands. Recorded as a dotted edge in the block map. |
| **EXT-007** — the frontend's consequence (`422` on a write route) | phase 16, as **co-owner** | Phase 07 owns the model policy; phase 16 owns whether the SPA over-sends. EB-5's Auditor deliverable is the census that makes the co-ownership decidable. |
| **EXT-009** — the `rq-worker` topology row | phase 01 **TOPO-001** | The report itself declines to re-file it. This plan declines it too. |
| **EXT-009** — the `pyproject.toml` dependency residue (`plotly`, `tenacity`, `requests`, `pyjwt` alongside `python-jose`, `asgiref` in a non-Django stack) | phase 01 (dependency surface) | Recorded, not absorbed: EB-6 makes the *gate* coherent, not the manifest. See **HO-1**. |
| **EXT-002** — 4 workers × ~59 s saturation as a measured cost | phase 11 | The report hands the projection to 11 explicitly. |
| **EXT-007** — the repository predicate `AggregatedData.dims[key].astext == str(value)` | phase 03 / phase 05 | `SELECT`-safety is re-confirmed: the predicate is built as a SQLAlchemy expression, with no string interpolation. **No change is proposed and none is needed.** |
| **docker/nginx/nginx.conf` | phase 12 (per plan 04's `C04-5`) / phase 10 | EB-7's production-tier gap lives behind nginx's `location` blocks; the file is not this phase's. |
| `tests/test_rate_limiting.py::TestRateLimitingIntegration::test_different_ips_have_separate_limits` | phase 09 | The test's **name** promises per-IP separation it never exercises. EB-3 touches the same key identity by consequence; it does not fix the test. |
| `tests/test_health.py`'s test **quality** | phase 09, via `DP-2` | EB-1 owns the production change; the assertion's shape is phase 09's ruling. |
| Orphan `temp_pwd:` keys and the five `bidb` rows `VAL-07-011` names | **nobody** — `DP-5`, Coordinator only | A Planner must not create or delete database rows. Recorded, not scheduled. |
| **VAL-07-011** itself | not actionable for this role | It is a claim about the report's own prose. |

### CONFLICT — between report, code context and landed work

| # | Subject | Report | Code context | Ruling |
| - | ------- | ------ | ------------- | ------ |
| **X-01** | EXT-001's remedy feasibility | "Executable as written, and verified to have no shipped test blocker" | `tests/test_health.py` asserts `/health` by **exact dict equality**, and `docs/05-health/health-api.md` argues the probe must stay DB-only | **Code context wins.** The remedy is not executable as written. `DP-1` and `DP-2` gate EB-1, and the documented decision is preserved in the block's constraints. |
| **X-02** | EXT-005's merge ruling | Filed with **no** merge or adjacency ruling at all | Merged into phase 04 **AB-1**/**AB-2**, escalated | **Both agree.** `VAL-07-001` is discharged by the hand-over register. |
| **X-03** | EXT-008's remedy | "Move the store after `db.commit()`" — and, via `VAL-07-005`, compensate the committed record | The ordering half is **already fixed** and pinned by three shipped tests; the compensation half is **contradicted** | **Code context wins.** EB-9 is verification-shaped. `VAL-07-005` is recorded and **not scheduled**. |
| **X-04** | EXT-009's count | "reduce `REQUIRED_MODULES` to the twelve the application imports" | "13 (14 minus `rq`)" | **Planner re-derivation wins.** `REQUIRED_MODULES` has **13** names; **3** certify an absence (`plotly`, `tenacity`, and — per this plan's re-derivation — the report's framing of `httpx` is a tier mismatch, not an absence); `rq` is real. EB-6 prices the four names individually. |
| **X-05** | EXT-010's evidence | "`app.py` passes the literal `version=\"1.0.0\"`" | The literal moved to `config.py`; the drift is unchanged | **Both refuted as written.** The finding's *consequence* (a document seven patch releases behind, no version to detect a contract change) stands, which is why EB-8 exists. |
| **X-06** | EXT-002's retry arithmetic | "three retries of a 5 s timeout" | Measured `retries=10`, `ExponentialWithJitterBackoff(cap=1, base=0.01)`, `socket_timeout=5` | **Code context wins** (`VAL-07-006`). EB-2's bound must be designed against eleven 5-second attempts, not three. |
| **X-07** | EXT-006's surface | "every declared path", "all 43 declared paths" | Four paths | **Code context wins** (`VAL-07-007`). EB-4 is scoped to `/api/v1/users/`, `/api/v1/dashboards/`, `/api/v1/graphs/`, `/api/v1/admin/logs/`. |
| **X-08** | EXT-003's compatibility caveat | "check the one shipped caller, `ErrorBoundary.tsx:40`" | Zero `client-errors` references in `frontend/src/` | **Code context wins, and it is stronger:** `docs/08-security/client-error-reporting.md` documents `error` as *"an object with `message` and `name` fields"* and its "Frontend Integration" section as **aspirational** ("*The React SPA **should** call this endpoint from…*"). There is no first-party caller and the documented contract already names two fields. |

### VERIFICATION FINDING — the report's `VAL-07-*` records

Each is a defect **in the report**, not in the code. **No audit file is edited.** `VAL-07-002` and
`VAL-07-005` alone change what may be scheduled, and `VAL-07-005` changes it by *deleting* an option.

| ID | Band | Subject | Ruling in this plan |
| -- | ---- | ------- | ------------------- |
| **VAL-07-001** | MEDIUM | EXT-005 duplicates AUTH-002 + AUTH-006, filed with no merge ruling | **Substantiated and escalated.** Discharged by the hand-over register (**HO-2**): EXT-005 is registered as merged into phase 04 **AB-1** (write) and **AB-2** (read), naming the owning phase. The report's `admin.py` anchors name nothing; the register records the bodies' real location so a ticket cannot land on a delegation. |
| **VAL-07-002** | MEDIUM | EXT-004's `forwarded-allow-ips="*"` is a caller-chosen bucket | **Substantiated; ALREADY RULED — not re-opened.** Plan 04 records `VAL-04-001` as **applied**: option (b) is deleted. This plan inherits the ruling. **No block in this plan may name `"*"` as an option.** |
| **VAL-07-003** | MEDIUM | EXT-002 claims `SERVICE_UNAVAILABLE` does not exist | **Substantiated. Applied.** `models/enums.py::ErrorCode.SERVICE_UNAVAILABLE` exists and is already mapped to 503 in `utils/exceptions.py`. **No new enum member is created anywhere in this plan.** Phase 04's `AB-5` consumes the existing code. |
| **VAL-07-004** | MEDIUM | EXT-002's refusal class duplicates AUTH-008 at the same sites | **Substantiated, and the site list is larger: six, not two.** The four live sites are `api/deps.py::get_current_user_dependency`'s two revocation reads and `core/permissions.py::_get_current_user_with_session`'s two. Handed to phase 04 **AB-5**. Phase 07 keeps only the blast radius and the undeclared bound (EB-2). |
| **VAL-07-005** | MEDIUM | EXT-005/EXT-008/AUTH-002 prescribe three orderings; the report picks a fourth | **Refuted in its prescribed outcome. Recorded, NOT scheduled.** Adopting it literally reverses a shipped test, two landed docstrings and `docs/04-admin/admin-api.md`. **EB-9 exists to keep this from being scheduled by a later reader.** |
| **VAL-07-006** | MEDIUM | "three retries of a 5 s timeout" is wrong; the library retries ten | **Substantiated, runtime-confirmed. Applied as a wording correction.** EB-2's bound is designed against the measured configuration. |
| **VAL-07-007** | MEDIUM | EXT-006 overstates the enumeration surface ~10× | **Substantiated. Applied.** Four paths; EB-4 is scoped to exactly those four and to no more. |
| **VAL-07-008** | MEDIUM | EXT-005/EXT-008 blocked by two shipped tests both reports deny | **Substantiated verbatim, plus a fourth pin the report missed** (`tests/test_admin_user_management.py`'s admin-reset case). Recorded in **HO-2** so phase 04 inherits the full list. |
| **VAL-07-009** | LOW | Nine anchors moved and are now committed | **Substantiated and superseded.** Its correction table targets an older revision than `HEAD`. **Keep the method (resolve by symbol, re-resolve immediately before editing); discard the numbers.** |
| **VAL-07-010** | LOW | Four evidence anchors and one search characterisation are wrong | **Substantiated for (a)–(c)** (`pyproject.toml`'s version is at line 7; twelve routers carry `redirect_slashes=False`, all verified; twelve names in `REQUIRED_MODULES` was the report's figure and is **13**); **(d) is superseded** by `VAL-07-001`. **A fifth error exists that `VAL-07-010` does not name** — EXT-004's "email branch is unreachable" (see the refuted-claims table). |
| **VAL-07-011** | LOW | The report's restoration claim omits five durable rows it created | **Not actionable for this role.** No block may create or delete database rows. Carried as **DP-5** for the Coordinator and named in the out-of-scope table. |

## Block map

```mermaid
flowchart TD
    EB0["EB-0 · anchor reconciliation, refuted-claim and hand-over registers"]

    DP1{{"DP-1 · what the probe measures"}}
    DP2{{"DP-2 · the exact-dict assertion"}}
    DP3{{"DP-3 · where Redis bounds live"}}
    DP4{{"DP-4 · retry as config or invariant"}}
    DP7{{"DP-7 · register or path-relative"}}
    DP6{{"DP-6 · strict base scope"}}
    DP8{{"DP-8 · the startup gate's shape"}}
    DP9{{"DP-9 · the version source of truth"}}
    DP11{{"DP-11 · reject or truncate an oversized report"}}
    DP12{{"DP-12 · whose control closes the schema surface"}}

    EB1["EB-1 · EXT-001 what the probe measures"]
    EB2["EB-2 · EXT-002 declare the Redis transport bound"]
    EB3["EB-3 · EXT-003 bound the anonymous log write"]
    EB4["EB-4 · EXT-006 align served with declared paths"]
    EB5["EB-5 · EXT-007 request-model strictness"]
    EB6["EB-6 · EXT-009 reconcile the startup gate"]
    EB7["EB-7 · EXT-010 gate openapi_url"]
    EB8["EB-8 · EXT-010 one version source of truth"]
    EB9["EB-9 · EXT-008 closure, VAL-07-005 not scheduled"]

    HO1{{"HO-1 · phase 04 AB-6 / AB-7"}}
    HO2{{"HO-2 · phase 04 AB-1 / AB-2 landed"}}

    EB0 ==> EB1
    EB0 ==> EB2
    EB0 ==> EB3
    EB0 ==> EB4
    EB0 ==> EB5
    EB0 ==> EB6
    EB0 ==> EB7
    EB0 ==> EB8
    EB0 ==> EB9

    DP1 ==> EB1
    DP2 ==> EB1
    DP3 ==> EB2
    DP4 ==> EB2
    DP11 ==> EB3
    DP7 ==> EB4
    DP6 ==> EB5
    DP8 ==> EB6
    DP12 ==> EB7
    DP9 ==> EB8
    HO2 ==> EB9

    EB2 -.-> EB3
    HO1 -.-> EB3
    EB7 -.-> EB8
```

`==>` = hard dependency. `-.->` = recommended sequencing in the single-implementor queue, **not** a
data dependency — the project permits one implementor at a time, so these are ordered for review
coherence. `HO-*` diamonds are hand-over gates owned by another phase, not by this one.

### Coverage ledger

| Block | Findings discharged | Decisions gating it | Agents |
| ----- | -------------------- | -------------------- | ------ |
| **EB-0** | all eleven `VAL-07-*` as rulings; every dead anchor; every refuted claim; the hand-over register | — | Planner (owns the note); Auditor confirms the registers are complete at `cea2d06` |
| **EB-1** | **EXT-001** (probe-measurement half) | `DP-1`, `DP-2` | **Auditor, Researcher, Planner, Validator — all four** |
| **EB-2** | **EXT-002** (residue) · `VAL-07-006` · `VAL-07-003` (recorded) · `VAL-07-004` (recorded) | `DP-3`, `DP-4` | **Auditor, Researcher, Planner, Validator — all four** |
| **EB-3** | **EXT-003** | `DP-11` | **Auditor, Researcher, Planner, Validator — all four** |
| **EB-4** | **EXT-006** · `VAL-07-007` | `DP-7` | Planner, Validator |
| **EB-5** | **EXT-007** | `DP-6` | **Auditor, Researcher, Planner, Validator — all four** |
| **EB-6** | **EXT-009** | `DP-8` | Planner, Validator |
| **EB-7** | **EXT-010** (tier half) | `DP-12` | Planner (short), Validator |
| **EB-8** | **EXT-010** (version half) | `DP-9` | Planner, Validator |
| **EB-9** | **EXT-008** (verification) · **`VAL-07-005`** (recorded, not scheduled) | — | none beyond Implementor; Validator if the ordering has drifted |

**Splits and merges, with reasons.** `EXT-010` is **split** into EB-7 (tier half) and EB-8 (version
half) because the two halves touch different files (`app.py` versus `config.py`), carry different
blockers (none versus `DP-9` *and* a phase-01 hand-over), and have different risk profiles — and
because merging them would leave the ungated half stuck behind a cross-phase decision it does not
depend on. Nothing else is split: `EXT-007`'s three sub-items (`filters` modelling, `GraphBase.config`
modelling, the strict base) share one file family, one review and one regression surface, and the two
DP-6-governed sub-items cannot ship apart from the census that governs them. `EXT-002` is **not**
merged into phase 04's `AB-5` because the two halves have different files, different risk and different
verifiers even though they share one dependency — see **HO-2**.

---

## Execution blocks

### EB-0 — Anchor reconciliation, refuted-claim register and hand-over register

| Field | Value |
| ----- | ----- |
| **Semantic target** | **No production code.** This plan's own "Anchor authority", "Refuted claims", "Planner-required re-derivations" and "Scope-ruling tables" sections are the deliverable, carried forward into each block's `Definition of done`. |
| **Discharges** | `VAL-07-001` (registered as merged → **HO-2**) · `VAL-07-002` (**closed** by phase 04's applied `VAL-04-001`; inherited, not re-opened) · `VAL-07-003` (**applied** — no new `ErrorCode` member anywhere in this plan) · `VAL-07-004` (**applied** — six sites, four live; refusal class handed to **HO-2**) · `VAL-07-005` (**recorded, not scheduled** — see EB-9) · `VAL-07-006` (applied — wording) · `VAL-07-007` (applied — four paths) · `VAL-07-008` (recorded → **HO-2**, with the fourth pin) · `VAL-07-009` (superseded — method kept, numbers discarded) · `VAL-07-010` (applied for (a)–(c); (d) superseded by `VAL-07-001`; the unnamed fifth error recorded) · `VAL-07-011` (**not actionable** — `DP-5`, out-of-scope table) · every dead anchor · every refuted claim · conflicts **X-01 … X-08** |
| **blocked_by** | — |
| **Execution order** | **1.** Nothing else starts without it. |
| **Risk — implementation** | **None.** Nothing executes. |
| **Risk — rollout** | **None.** |
| **Risk — regression** | **None.** |
| **Risk — compatibility** | One real hazard: **this note can be mistaken for authority to edit `.ai/audit/**`.** It is not. Phase 03's `B0` convention — *no audit file is edited* — is inherited verbatim, and phase 04's `VAL-04-001` precedent (an audit record *applied* as a ruling inside a plan, never as an edit to the report) is inherited with it. |
| **Agents** | **Planner** — owns the note. **Auditor** — confirms at `cea2d06` that the refuted-claim table and the hand-over register name every anchor the code context lists as dead or refuted, and that no *new* dead anchor appeared while the register was being written. No Implementor, no Researcher, no Validator: nothing here is a code claim that a green gate could check. |
| **Documentation impact** | **One row** appended to `docs/SPEC.md` **Version History**, naming this plan — house convention, matching sibling plans. **Nothing else.** |
| **Verification** | `git status --porcelain` clean of tracked source at block start · `git rev-parse HEAD` recorded in the commit body · confirm no file under `.ai/audit/`, `.ai/plans/_code-context/` or any sibling `.ai/plans/0[1-6]-*.md` appears in `git status` as modified · **no test run required** |
| **Definition of done** | The note exists and names: the seven dead `admin.py` approval anchors; the dead `version="1.0.0"` anchor in `app.py`; the absent Redis `PING` on both health endpoints; all ten refuted claims with their reality; **the two Planner re-derivations** (four `rq` import statements across two modules; `httpx` as a tier mismatch rather than a certified absence) and their consequences for EB-6; all eleven `VAL-07-*` rulings with `VAL-07-002` marked closed and `VAL-07-005` marked not-scheduled; the two hand-overs (**HO-1**, **HO-2**) with named owner blocks; that **`cea2d06` is HEAD**; that **no audit file, no code context file and no sibling plan is edited**; and that `VAL-07-011` is stated, not dropped. |

---

### EB-1 — Decide what the health probe measures, then make it say so (EXT-001, probe-measurement half)

| Field | Value |
| ----- | ----- |
| **Semantic target** | `app.py::create_app`'s `health_check` and `detailed_health_check` handlers · `core/redis_client.py::get_async_redis_client` (a ping helper, if the ruling needs one) · `app.py`'s reconciler component block inside `detailed_health_check` · `docs/05-health/health-api.md` (the probe-contract section, the component table and the consumer guidance) · `docker/Dockerfile`'s `HEALTHCHECK` and `docker/docker-compose.yml`'s `app` healthcheck **as read-only context — this block does not edit them** |
| **Discharges** | **EXT-001** (probe-measurement half). The deployment half is already landed under phase 02 `B3` / `TOPO-008` and is **not** re-planned. Conflict **X-01**. |
| **blocked_by** | **`DP-1`** (hard — this block *is* its consequence) and **`DP-2`** (hard — the shipped test's shape is part of the definition of done). Soft: EB-0. |
| **Execution order** | **2** |
| **Risk — implementation** | **HIGH, and inverted.** The naive remedy — add a Redis `PING` to `/health`, return 503 on failure — is *blocked by two independent artefacts*, and one of them argues the opposite outcome on purpose. An implementor who has not read both will ship it, because it compiles, passes the detailed-endpoint assertions, and matches the report's recommendation verbatim. |
| **Risk — rollout** | **HIGHEST in the plan.** `docker/nginx/nginx.conf` exposes exactly the two health paths, and at least **three** services in the shipped compose declare `depends_on: … condition: service_healthy` against the app. Under `--workers 4`, a Redis blip makes three of four workers report unhealthy, and the documented consequence is that **the reverse proxy and every dependent service refuse to start**. That converts a degraded background sweep into a total API outage — precisely the inversion `docs/05-health/health-api.md` warns against in prose. This is not a theoretical risk; it is the stated reason the current design exists. |
| **Risk — regression** | **HIGH against a shipped test.** `tests/test_health.py::TestHealthWithRedisDown::test_health_still_healthy_when_redis_down` asserts `response.json() == {"status": "healthy", "database": "connected"}` — an **exact-dict equality** — and its class docstring states the intent being defended ("*A Redis outage must not drag down /health or the overall detailed status*"). Any remedy that adds a key or a non-200 to `/health` breaks it. The `/health/detailed` assertions are membership-only and survive an added component. |
| **Risk — compatibility** | **HIGH, and tier-dependent.** `/health` is a documented load-balancer, uptime-monitor and Kubernetes probe target. Widening it changes what every one of those consumers is told, and `docs/05-health/health-api.md` currently instructs operators to *"alert on non-200 responses"*. A split into a new readiness path is additive to consumers that were not migrated and inert for those that were — the safest shape is also the one that leaves the original defect in place for anyone still polling `/health`, which is why it is a decision and not a fix. |
| **Agents** | **Auditor, Researcher, Planner, Validator — all four.** **Auditor:** the complete census of `/health` consumers — the Docker `HEALTHCHECK`, every `condition: service_healthy` dependent in the base and override compose files, nginx's `location` block, and every operator-facing promise in `docs/05-health/health-api.md` and `docs/10-deployment/deployment.md`; plus whether any shipped test outside `tests/test_health.py` asserts either handler's shape. **Researcher** (narrow, and it is the research that decides this): the liveness-versus-readiness distinction as compose and orchestrators actually implement it — what `service_healthy` and `start_period` do when a dependency the application can degrade without is included in the readiness answer, and why a probe that covers a degradable dependency is a different object from one that does not. **Planner:** the contract shape under whichever `DP-1` option is ruled, including whether `/health/detailed` gains a Redis component, a lease-state field, or a status that can actually go `unhealthy`. **Validator:** that the naive remedy did not ship, that both blocking artefacts are honoured rather than worked around, and that the documentation states the *same* thing the code does. |
| **Documentation impact** | **Required and inseparable from the code.** `docs/05-health/health-api.md` already carries the decision (its "`/health` Is Deliberately Unchanged" section) and its **self-contradiction** — the component-status prose says the overall `status` reflects the worst component, while the same file and `app.py`'s own comment say the reconciler component never changes it. Whichever `DP-1` option is ruled, that contradiction is resolved in the same commit as the code, because a reader following the prose today would conclude the endpoint already does what `EXT-001` asks for. `docs/10-deployment/deployment.md` follows only if the consumer guidance changes. `docs/SPEC.md` gains a version row. |
| **Verification** | `.\Makefile.ps1 test-select -k "TestHealthEndpoint" -v` · `.\Makefile.ps1 test-select -k "TestHealthDetailedEndpoint" -v` · `.\Makefile.ps1 test-select -k "TestDetailedHealthReconcilerComponent" -v` · `.\Makefile.ps1 test-select -k "TestHealthWithRedisDown" -v` · `.\Makefile.ps1 test-select -k "test_health_still_healthy_when_redis_down" -v` (**the blocker; must be green and must not have been weakened**) · **new**, per `DP-1`: a test that a degraded dependency is *reported* by whichever endpoint the ruling names, and that the endpoint named by the ruling returns the status the ruling specifies · `.\Makefile.ps1 test-select -k "test_app_metadata_comes_from_settings" -v` (same file, unrelated assertion, cheap guard against an `app.py` constructor slip) · `uv run ruff check src/mkobi/app.py src/mkobi/core/redis_client.py` · `uv run mypy src/mkobi/app.py src/mkobi/core/redis_client.py` · **a live read of both endpoints** after the change: `GET /health` and `GET /health/detailed` on the dev stack, and the same two reads with `mkobi-redis-1` paused, restoring the container in the same command block |
| **Definition of done** | `DP-1` recorded with its option and its phase-10 co-signature in the commit body · `DP-2` recorded with the fate of the exact-dict assertion · the block's **two blocking constraints are both satisfied in the code and both cited in the commit body** — the shipped test's assertion and the documented probe decision · the `docs/05-health/health-api.md` self-contradiction is resolved in the same commit · no file under `docker/` is edited by this block · a Redis outage's user-visible outcome on each endpoint is stated in the commit body, because that is the release-note line. |

**The two constraints this block must not lose.** They are the whole reason this finding is a
decision rather than a patch, and an implementor who reads only the report will not know either of
them exists.

1. **A shipped test blocks it.** `tests/test_health.py::TestHealthWithRedisDown::test_health_still_healthy_when_redis_down` asserts `/health`'s response by **exact dict equality**. The report's recommendation states it is *"verified to have no shipped test blocker"* — it checked the `/health/detailed` assertions (membership-only, which survive) and not this one. Adding a `redis` key to `/health` breaks it. **Constraint:** the assertion is either updated *with* the code under `DP-2`, or `/health` keeps its exact two-key shape. It is never deleted to make a change land.
2. **A documented decision argues the opposite.** `docs/05-health/health-api.md` states that `/health` *"is what the container healthcheck curls and what `nginx` gates on via `depends_on: app: condition: service_healthy`"*, that under `--workers 4` *"during any Redis blip three of the four workers would report unhealthy and the reverse proxy would refuse to start — turning a degraded background sweep into a total outage of the API"*, and that `/health` *"therefore keeps meaning one thing only: the database is reachable."* `app.py`'s own comment inside the reconciler component says the same. **Constraint:** this decision is **preserved by default**. Any ruling that widens `/health` must say, in the commit body, why the recorded reasoning no longer holds — not merely that a new dependency now exists.

---

### EB-2 — Declare the Redis transport bound (EXT-002, residue)

| Field | Value |
| ----- | ----- |
| **Semantic target** | `core/redis_client.py::get_async_redis_client` (and `::get_redis_client`, which shares the construction) · `config.py::RedisSettings` **and** the `Settings.redis` binding **only if `DP-3` rules option (b) or (c)** · `api/deps.py::get_redis_client_dependency` **only if the bound must be injected rather than constructed** · `docs/06-backend/configuration.md`'s environment-variable table **only if a new key appears** |
| **Discharges** | **EXT-002** (residue: the undeclared bound and the blast radius). `VAL-07-006` (the retry arithmetic, as a design input). `VAL-07-003` and `VAL-07-004` are **recorded**, not discharged here: the former deletes a phantom blocker, the latter is phase 04's `AB-5`. |
| **blocked_by** | **`DP-3`** (hard — where the bound lives) and **`DP-4`** (hard — whether retry is a config value or a code invariant). Soft: EB-0. |
| **Execution order** | **3** |
| **Risk — implementation** | **MEDIUM-HIGH, and low in line count.** The edit is a handful of keyword arguments in one constructor. The risk is that there is **no single seam**: `get_async_redis_client` is the single construction function, but five route sites call it **inline** rather than through `api/deps.py::get_redis_client_dependency`, and `AuthService` builds a private limiter from it as well. A bound placed at the construction function reaches all of them — which is correct — and it also means **any change to the construction reaches every Redis operation in the process at once**, including the rate limiter whose failure direction is a declared fail-closed default. |
| **Risk — rollout** | **HIGH in one direction, LOW in the other.** The per-request cost of a Redis outage is inherited from a library default no code in this project sets: measured `socket_timeout=5`, `retry=Retry(ExponentialWithJitterBackoff(cap=1, base=0.01), retries=10)`, i.e. **eleven 5-second attempts** per request — the report's "three retries" is refuted by `VAL-07-006`. Declaring a bound **shortens** that, which is the intent, and shortening it converts a ~59 s hang into a prompt failure that `AB-5`'s direction will report honestly. There is no path by which declaring a bound makes an outage worse; the risk is choosing a bound so aggressive that ordinary latency under load is reported as an outage. |
| **Risk — regression** | **MEDIUM.** Five surfaces depend on Redis behaviour under failure and none of them is currently exercised for it: the rate limiter (fail-closed default `True`, compose-pinned), the two revocation reads, the temp-password store (fail open), the reconciler lease (fail open by design), and the RQ worker's own connection check — **the only declared retry in `src/`**. A shorter timeout changes what "slow" means for all five. The RQ worker's broker path is the one with its own retry/backoff and must not be silently governed by a client default that was never chosen. |
| **Risk — compatibility** | **LOW for this block; HIGH for the block it hands to.** Declaring a bound changes no status code. But `EXT-002`'s user-visible outcome — a Redis outage surfacing as `401 AUTHENTICATION_FAILED`, which the SPA's interceptor answers with a silent refresh that needs the same Redis — is phase 04's `AB-5` and belongs in **its** release note, not this block's. This block must not touch a refusal class. |
| **Agents** | **Auditor, Researcher, Planner, Validator — all four.** **Auditor:** the complete call-site census of `get_async_redis_client` and `get_redis_client` across `src/`, separating the API process from the RQ worker process, and identifying every Redis operation whose failure semantics are *already declared* somewhere (the rate limiter's `fail_closed`, the store's fail-open, the lease's fail-open, the worker's retry) so the new bound does not contradict a declared contract. **Researcher** (this is the block where external knowledge decides the answer): redis-py 8.0 transport semantics — how `socket_timeout` and `socket_connect_timeout` differ in what they bound, what a `Retry` object's `retries` counts, what `ExponentialWithJitterBackoff`'s `cap` and `base` do to worst-case latency, and whether `Retry(NoBackoff(), 0)` is genuinely equivalent to "no retry" for a blocking client. **Planner:** where the bound lives (`DP-3`) and the bound's shape (`DP-4`), plus the interaction with `RedisSettings`' existing `SECRET_FIELD_REGISTRY` entry. **Validator:** that the measured ~59 s becomes a declared, documented number; that the six revocation-read sites phase 04 must edit are enumerated for **HO-2** rather than edited here; and that no failure direction changed without its owner agreeing. |
| **Documentation impact** | **Conditional and narrow.** If `DP-3` rules for `RedisSettings` fields, `docs/06-backend/configuration.md`'s environment-variable table gains the new keys — a new `REDIS__*` key must appear there, per the project's settings discipline. If it rules for inline literals, **no settings key appears and no configuration doc changes**; the declared bound then lives as a code constant with a comment naming why. Either way the blast radius and the cost figure belong in the commit body and in the release note that phase 04's `AB-5` writes. `docs/SPEC.md` gains a version row. |
| **Verification** | `.\Makefile.ps1 test-select -k "TestAsyncRateLimiterUnit" -v` · `.\Makefile.ps1 test-select -k "TestRateLimitingIntegration" -v` · `.\Makefile.ps1 test-select -k "TestTokenRevocation" -v` · `.\Makefile.ps1 test-select -k "TestUserDeactivationRevocation" -v` · `.\Makefile.ps1 test-select -k "TestTempPasswordStore" -v` · `.\Makefile.ps1 test-select -k "test_store_fail_open_on_error" -v` (**must stay green — the store's fail-open contract is phase 04's, not this block's**) · `.\Makefile.ps1 test-select -k "TestStartRQWorker" -v` and `.\Makefile.ps1 test-select -k "TestCheckWorkerRegistered" -v` (**the worker entrypoint must be unaffected**) · `.\Makefile.ps1 test-select -k "TestLifespanLeaseGuard" -v` (**the reconciler lease must be unaffected**) · **new:** a test that a constructed client carries the ruled bound, reading the client's own connection kwargs rather than mocking the constructor · **new:** a test that a Redis timeout surfaces as a bounded failure rather than a hang · `uv run ruff check src/mkobi/core/redis_client.py src/mkobi/config.py` · `uv run mypy src/mkobi/core/redis_client.py` · `docker exec mkobi-app-1 python -c "…"` reading `connection_pool.connection_kwargs` before and after, to confirm the declared bound is the **effective** one and not merely the passed one |
| **Definition of done** | `DP-3` and `DP-4` recorded with their options in the commit body · the declared bound is observable on a constructed client and the observation is quoted in the commit body · the five declared Redis failure directions are enumerated, each with its owner, and **none was changed** · the six revocation-read sites are listed for **HO-2** and none is edited · `ErrorCode` and `utils/exceptions.py` are **untouched** (`VAL-07-003` applied) · the worker entrypoint and the reconciler lease are demonstrably unaffected · if `RedisSettings` gained a field, the field is in `SECRET_FIELD_REGISTRY` handling **only if** it is secret-bearing — a timeout is not, and adding it to that registry would be a mistake worth naming. |

---

### EB-3 — Bound what an anonymous caller can write to the log (EXT-003)

| Field | Value |
| ----- | ----- |
| **Semantic target** | `api/routes/client_errors.py::report_client_error` (the rate-limit construction, the `client_ip` derivation and the `logger.error` call) · `models/data.py::ClientErrorPayload` (the field bounds and, if `DP-11` rules for it, a strict inner model for `error`) · `docs/08-security/client-error-reporting.md` (the request-field table, the side-effects list and the **false rate-limit row**) |
| **Discharges** | **EXT-003**. Conflict **X-08** (the compatibility caveat is stronger than filed). |
| **blocked_by** | **`DP-11`** (hard — reject or truncate, and whether `error` is narrowed or bounded). Soft: EB-0. Dotted (reasoning only): phase 04's `AB-6`, per the block map. |
| **Execution order** | **4** |
| **Risk — implementation** **LOW-MEDIUM** | One route, one model, one log call. The real implementation risk is **choosing the wrong bound location**: a `Content-Length` pre-check on the route reads like the fix and is insufficient, because a chunked request carries no `Content-Length` and the project's own upload path already established the correct pattern — `tests/test_streaming_size_limit.py::TestStreamingSizeLimit` exists precisely because `file.size` can be `None`, and it proves the project knows a header-only check does not bind a body. The bound that actually holds is on the **parsed field values**, which is also what the report recommends in the same paragraph. |
| **Risk — rollout** | **MEDIUM.** The ceiling is `docker/nginx/nginx.conf`'s `client_max_body_size 100m`, un-overridden by `location /api`, so a single anonymous request can write a ~100 MB log record today, and the rate-limit budget behind it (100/hour) is a **shared** pool keyed on the proxy's address. Capping the record converts an unbounded write into a bounded one; an external caller that has been posting large bodies starts receiving a rejection or a truncated record. |
| **Risk — regression** | **LOW.** No shipped test asserts the current verbatim behaviour, and **no test exercises this endpoint at all** — `POST /api/v1/client-errors` has zero test callers. There is also **no first-party caller**: `frontend/src/` contains no reference to the endpoint, and `docs/08-security/client-error-reporting.md` describes the frontend integration in the subjunctive ("*The React SPA **should** call this endpoint from…*"). So the regression surface is an external browser and nothing else — which is a *risk*, not a safety: there is no in-repo client to run the change against, so the block's tests are its only evidence. |
| **Risk — compatibility** | **HIGH, and irreducible.** This is a public, unauthenticated endpoint whose response is `204` on every accepted body. Any narrowing of `ClientErrorPayload` turns a silently-accepted body into a `422`; any size bound turns an accepted body into a rejection. The documented contract already names `error` as *"an object with `message` and `name` fields"*, so narrowing it to that is defensible against the documentation — but the documentation describes a client that does not exist, so the only evidence for what real callers send is the report's own observation that `ErrorBoundary.tsx` was never wired. **The block must state this explicitly rather than discover it at rollout.** |
| **Agents** | **Auditor, Researcher, Planner, Validator — all four.** **Auditor:** the external-caller question — is `POST /api/v1/client-errors` called by anything outside this repository (a pinned or cached SPA build, a monitoring script, a bookmark), and what is the smallest reversible bound that does **not** require answering that question first. This is scoped deliberately narrowly: the in-repo census is already closed at zero and re-deriving it would be waste. **Researcher** (narrow): how a request-body size bound is expressed when the transport may not declare a length — `Content-Length` presence, chunked transfer encoding, and whether a reverse proxy's own `client_max_body_size` can be relied on as the application-level bound; plus the Pydantic v2 mechanics of `max_length` on a `str` field versus bounding a `dict[str, Any]`. **Planner:** where each bound sits, and the interaction with `DP-11`'s reject-versus-truncate ruling — in particular that the log record must carry the **untruncated length beside the capped value**, which is the only way an investigator can tell a truncation from a short error. **Validator:** that no accepted body can still produce an unbounded record, and that the log-injection negative result the report established still holds (the JSON formatter escapes newlines, so no caller can forge a record boundary — a bound must not change that property). |
| **Documentation impact** | **Required.** `docs/08-security/client-error-reporting.md` carries three statements this block makes false or newly true: its **"Rate limit: None (errors are expected to be rare)"** row is **factually wrong today** and must state the real bound and its key; the **request-field table** must carry the new field bounds; and the **side-effects** bullet naming the log format must carry the capping behaviour. The "Frontend Integration" section must say plainly that no first-party caller exists, because a future implementor reading it will otherwise believe one does. `docs/SPEC.md` gains a version row. |
| **Verification** | **new** `tests/test_client_errors.py` — this endpoint has **no** test module today, so the block creates one · a case asserting an oversized `message`/`url`/`userAgent`/`componentStack` is bounded (rejected or truncated per `DP-11`) · a case asserting the emitted log record's length is within the cap **and** that the untruncated length is logged beside it · a case asserting a body of ordinary size still returns `204` · a case asserting the rate limit still rejects with `RATE_LIMIT_EXCEEDED` (the endpoint's own contract, unchanged) · a case asserting the record is one physical line for a body containing `\n` (the log-injection property) · `.\Makefile.ps1 test-select -k "TestRateLimitingIntegration" -v` (unchanged) · `uv run ruff check src/mkobi/api/routes/client_errors.py src/mkobi/models/data.py` · `uv run mypy src/mkobi/api/routes/client_errors.py src/mkobi/models/data.py` · `.\Makefile.ps1 test-select -k "test_openapi" -v` (the payload's schema is published) |
| **Definition of done** | `DP-11` recorded with its option · no accepted body can produce a record beyond the cap, proven by a test rather than by inspection · the untruncated length is logged beside every capped value · the endpoint's rate limit is unchanged and still tested · `docs/08-security/client-error-reporting.md`'s false rate-limit row is corrected in the same commit as the code · that document states there is no first-party caller · the log-injection property is re-proven by a test, not assumed · the external-caller question is answered in the commit body, or explicitly recorded as unanswered **with the bound chosen so that being wrong is survivable**. |

---

### EB-4 — Align served paths with declared paths on the four collection routes (EXT-006)

| Field | Value |
| ----- | ----- |
| **Semantic target** | The four trailing-slash collection declarations and their handlers: `api/routes/users.py` (`GET "/"`, `POST "/"`), `api/routes/dashboards_crud.py` (`GET "/"`, `POST "/"`, mounted into `api/routes/dashboards.py`'s router), `api/routes/graphs.py` (`GET "/"`, `POST "/"`), `api/routes/processing_logs.py` (`GET "/"` under its `/admin/logs` prefix) · the `redirect_slashes=False` flag on the **twelve** routers that carry it · `docs/99-reference/swagger.md`'s documented paths, where they name any of the four |
| **Discharges** | **EXT-006**. `VAL-07-007` (**applied** — four paths, not 43). Conflict **X-07**. |
| **blocked_by** | **`DP-7`** (hard — register the route or emit a path-relative `Location`). Soft: EB-0. |
| **Execution order** | **5** |
| **Risk — implementation** | **LOW.** Starlette's slash handling runs ahead of route resolution and therefore ahead of every `Depends`, so a declared trailing-slash path requested without its slash answers `307` before any credential is examined. `redirect_slashes=False` suppresses only the opposite direction, which is why the flag's presence on twelve routers does not prevent this. The mechanism is understood and the fix is either a registration change or a response-shape change. |
| **Risk — rollout** | **MEDIUM and asymmetric by option.** Under `DP-7`'s registration option, four declared paths change shape and any client that does not follow redirects on a `307` stops working. Under the path-relative option, nothing observable changes except the `Location` header's host, and the existence oracle **remains** — the finding's measured effect is a bounded disclosure gap plus a caller-echoed `Location`, and the second half is the cheaper one to fix. |
| **Risk — regression** | **LOW-MEDIUM.** No shipped test asserts a `307` anywhere on these paths, so nothing pins the current behaviour — which is a finding in its own right and the reason the block must add a test either way. The four paths each have live test classes (`TestListUsers`, `TestGetDashboardsAdmin`, `TestGraphsAPI`, `TestProcessingLogFilter`) that request the **slash** form today; under the registration option those classes must keep passing **unmodified**, because the slash form is what is being kept. |
| **Risk — compatibility** | **MEDIUM, wire-visible on four declared paths.** The declared shape in the published document is the observable contract. Changing it changes what a generated client and any non-redirect-following caller see. This is a genuine fork with no technically dominant answer, which is why it is `DP-7` and not a choice. |
| **Agents** | **Planner** — required: `DP-7`'s options have different wire footprints, different test shapes and different documentation consequences, and the choice bakes a contract into the published document. **Validator** — required: that the declared shape and the served shape agree afterwards, asserted against the **live** document rather than against the route table. **Auditor / Researcher — not required.** The four-path scope is settled by runtime enumeration, the mechanism is a documented framework behaviour, and the file set is four route modules with no cross-phase premise at risk. |
| **Documentation impact** | **Conditional.** `docs/99-reference/swagger.md` and any `docs/` file that shows one of the four collection paths without its trailing slash must be aligned with whatever shape is declared. `docs/SPEC.md` gains a version row. No other `docs/` file is touched: no endpoint's semantics change, only which path is the declared one. |
| **Verification** | `.\Makefile.ps1 test-select -k "TestListUsers" -v` · `.\Makefile.ps1 test-select -k "TestGetDashboardsAdmin" -v` · `.\Makefile.ps1 test-select -k "TestGraphsAPI" -v` · `.\Makefile.ps1 test-select -k "TestProcessingLogFilter" -v` (**all four must stay green**) · **new:** a case per collection path asserting the no-slash request's outcome matches `DP-7`'s option · **new:** a case asserting the served path set and the published `paths` set agree for these four · `.\Makefile.ps1 test-select -k "test_openapi" -v` · a live `GET /openapi.json` confirming the declared paths · `uv run ruff check src/mkobi/api/routes/users.py src/mkobi/api/routes/dashboards_crud.py src/mkobi/api/routes/graphs.py src/mkobi/api/routes/processing_logs.py` · `uv run mypy src/mkobi/api/routes/users.py src/mkobi/api/routes/dashboards_crud.py src/mkobi/api/routes/graphs.py src/mkobi/api/routes/processing_logs.py` |
| **Definition of done** | `DP-7` recorded with its option · the served shape and the declared shape agree for **exactly** the four named collection paths and for no other path · the twelve `redirect_slashes=False` routers are left as they are unless `DP-7`'s option requires otherwise, and the reason is stated either way · a test pins the new outcome so the `307` cannot silently return · the published document is consistent with the served routes · the block's scope statement names four paths, and a diff touching a fifth path is out of contract. |

---

### EB-5 — Make the inbound validation policy executable (EXT-007)

| Field | Value |
| ----- | ----- |
| **Semantic target** | A strict base for request-body models — **shape undecided**, either a shared base class in `src/mkobi/models/` or per-model `model_config` · the two deferred boundaries: `api/routes/data.py`'s `filters` parameter and its `json.loads` site, and `models/types.py::GraphConfigDict` as typed into `models/graph.py`'s graph config fields · `docs/06-backend/architecture.md` **only if** the project adopts a written inbound-validation convention |
| **Discharges** | **EXT-007**, including all three of its sub-items. Conflict **X-04**'s census re-derivation. |
| **blocked_by** | **`DP-6`** (hard — the strict base's scope). **Not** gated: the `filters`-document modelling sub-item, which is a query-parameter concern `DP-6` does not govern and which may ship first. Soft: EB-0. |
| **Execution order** | **6** |
| **Risk — implementation** | **MEDIUM, and the revert cost is the real number.** The project's only `extra="forbid"` is one model; six internal runtime-validation models declare `{"extra": "allow"}`. Turning `extra="ignore"` into `extra="forbid"` on the route-shaped bodies is a **base-class revert** in every case, which is a low-diff change with a high tail. The two deferred boundaries are genuine work of a different kind: modelling `filters` as a document rather than a string, and replacing a `TypedDict` with a real model — the second touches a field that is **also a response shape**, so its blast radius is wider than a request-body change. |
| **Risk — rollout** | **HIGH, and this is the one everyone under-rates.** Silent field drops become `422`s on **every write surface**. That is correct and it will be reported as a regression. The block must be sequenced with the frontend owner (phase 16) and its rollout note must say what a `422` on a write route now means. Nothing stored changes in any sub-item — the risk is entirely in what callers observe. |
| **Risk — regression** | **HIGH and broad.** Every write-route test class in the suite is a candidate to break, because a suite that sent a field the model ignores today will start getting a `422`. That is not a flaky-test problem; it is the intended behaviour arriving, and the required response is to **find the over-sending caller and fix it**, not to relax the policy. The suite's own test modules build payloads by hand, so a hand-built payload that over-sends is itself the evidence the census needs. |
| **Risk — compatibility** | **HIGH.** A `422` where a `200` was returned is an observable API change for every client. The published schema gains `additionalProperties: false` semantics, which a generated client may surface as a compile-time or runtime difference. The six `{"extra": "allow"}` internal types must **not** be carried along on an inference about their intent — establishing whether each is genuinely open is the same discipline the report applies to the libraries in `EXT-009`, and it is explicitly out of this block. |
| **Agents** | **Auditor, Researcher, Planner, Validator — all four.** **Auditor:** the frontend field census, by symbol — every request body the SPA actually constructs, field by field, so `DP-6`'s scope question is decided on evidence rather than on the report's "0 of 21". Also the exact set of route-shaped body models, **enumerated by symbol in the commit body, not by count**, and the per-field census of the two deferred boundaries. **Researcher** (narrow): Pydantic v2 `extra` semantics under inheritance — whether a shared base's `extra="forbid"` is inherited cleanly by subclasses that declare their own `model_config`, what that does to the existing `json_schema_extra` blocks, and whether bounding a `TypedDict`-typed field means modelling the nested document or constraining it. **Planner:** the base-class-versus-per-model shape, the ordering of the three sub-items so that the census precedes the policy, and the convention statement if one is adopted. **Validator:** that the census was **completed before** `forbid` landed — this is the single sequencing assertion that matters — and that no `{"extra": "allow"}` internal type was changed on an inference. |
| **Documentation impact** | **Conditional and worth writing.** No `docs/` file states a model-strictness convention today — the report's search over the corpus found none — so if the project adopts one, `docs/06-backend/architecture.md` is its home. If it does not, the policy lives in the base class's docstring and `docs/` is untouched. Either way, any doc that shows an example request body must show one that the policy accepts. `docs/SPEC.md` gains a version row. |
| **Verification** | `.\Makefile.ps1 test-select -k "TestUserModels" -v` · `.\Makefile.ps1 test-select -k "TestDashboardModels" -v` · `.\Makefile.ps1 test-select -k "TestAuthModels" -v` · `.\Makefile.ps1 test-select -k "TestDataModels" -v` (**the model layer's own suite**) · `.\Makefile.ps1 test-select -k "TestCreateUser" -v` · `.\Makefile.ps1 test-select -k "TestRegistrationFlow" -v` · `.\Makefile.ps1 test-select -k "TestGraphsAPI" -v` · `.\Makefile.ps1 test-select -k "TestLayoutService" -v` · `.\Makefile.ps1 test-select -k "TestAggregatedDataEndpointContract" -v` (the `filters` sub-item) · `.\Makefile.ps1 test-select -k "TestProcessingConfigUpdate" -v` **if that class exists at execution time** — the implementor resolves the write-route classes by symbol and runs every one whose body model changed · **new:** a case per changed model proving an unrecognised field is rejected · `.\Makefile.ps1 test-select -k "test_openapi" -v` · `uv run ruff check src/mkobi/models src/mkobi/api/routes/data.py` · `uv run mypy src/mkobi/models` |
| **Definition of done** | `DP-6` recorded with its option · **the frontend field census is in the commit body before the policy lands** — not after, and not summarised · the exact set of route-shaped body models is enumerated by symbol, and the six `{"extra": "allow"}` internal types are **unchanged** with the reason stated · the `filters` document is modelled, and malformed JSON still yields the existing 422-class error rather than a new one · `GraphBase.config`'s nested document is modelled and its **response** shape is accounted for, not only its request shape · every write-route test that broke was fixed at the **caller**, and the set of fixed callers is named · `ErrorCode` is untouched: no new validation code is introduced (`VAL-07-003` applied here too). |

---

### EB-6 — Reconcile the startup dependency gate (EXT-009)

| Field | Value |
| ----- | ----- |
| **Semantic target** | `src/mkobi/main.py::REQUIRED_MODULES` and `::check_dependencies` · the two real `rq` import sites (`src/mkobi/rq_worker_wrapper.py`, `src/mkobi/core/task_queue.py`) as the reason `rq` stays · `pyproject.toml`'s `[project].dependencies` **as read-only context — this block does not edit it** (see **HO-1**) |
| **Discharges** | **EXT-009**. Conflict **X-04** and the two Planner re-derivations. |
| **blocked_by** | **`DP-8`** (hard — the gate's shape). Soft: EB-0. |
| **Execution order** | **7** |
| **Risk — implementation** | **LOW in the edit, MEDIUM in the meaning.** `REQUIRED_MODULES` has **thirteen** names and `check_dependencies` is a loop of `__import__` calls ending in `SystemExit(1)`. Changing the list is trivial. What is not trivial is that the gate is the **only** thing that ever loads the libraries it certifies, so a name removed from it stops being installed-checked at startup and nothing else notices — the failure moves from boot to first use, which for a rarely-used library is a long time. |
| **Risk — rollout** | **LOW-MEDIUM, and asymmetric per name.** `httpx` is genuinely required — by `tests/conftest.py` and ~20 test modules — so removing it from a gate the **test tier** depends on would break the suite if that gate serves the test entrypoint. `plotly` and `tenacity` have **zero** references in `src/`, `tests/`, `docker/` and `alembic/`, so removing them from the gate is safe at the gate and leaves their `pyproject.toml` declarations as the incoherence **HO-1** names. `rq` must stay: it is a real contract for the **worker** entrypoint, imported by exactly two modules across four import statements. |
| **Risk — regression** | **LOW, with one hard constraint.** `tests/test_task_queue.py::TestServicesDoNotImportRq::test_no_service_module_imports_rq` is an AST-walk assertion that **no module under `src/mkobi/services/` imports `rq`**. Neither real import site is a service module, so it passes today and must stay passing — that rule is *why* `rq`'s presence in the gate is defensible. `tests/test_rq_worker.py` (`TestStartRQWorker`, `TestCheckWorkerRegistered`) and `tests/test_config.py::TestRqWorkerComposeWiring` must stay green unmodified: they are the evidence that `rq` is a real contract. |
| **Risk — compatibility** | **None on the wire.** No API, schema or response changes. The only compatibility surface is the **startup**: a module removed from the gate is no longer guaranteed present at boot, which is a deployment-surface statement, not a contract. |
| **Agents** | **Planner** — required: the gate's shape is the whole decision (`DP-8`), and the four names are not homogeneous, so a single "trim the list" instruction would be wrong. **Validator** — required: that both entrypoints still start, and that the shipped layering rule is provably intact. **Auditor / Researcher — not required.** The census is closed (§2 of this plan, verified by symbol) and the intent question is an owner decision, not an external-knowledge question. **This block must not pull a Researcher**: the report's own instruction is to *establish intent before touching a library*, and no research substitutes for that. |
| **Documentation impact** | **Conditional and minimal.** `docs/06-backend/architecture.md` (the startup-gate section, if one describes what the gate certifies) · `docs/10-deployment/deployment.md` (only if the deployment doc claims the image's dependencies are all verified at boot) · `docs/SPEC.md` gains a version row. **No** `docs/` file needs a dependency list rewritten — that is `pyproject.toml`'s content and the project's own dependency surface, which is **HO-1**'s. |
| **Verification** | `.\Makefile.ps1 test-select -k "TestServicesDoNotImportRq" -v` (**must stay green unmodified** — the layering rule) · `.\Makefile.ps1 test-select -k "TestStartRQWorker" -v` · `.\Makefile.ps1 test-select -k "TestCheckWorkerRegistered" -v` · `.\Makefile.ps1 test-select -k "TestRqWorkerComposeWiring" -v` · `.\Makefile.ps1 test-select -k "TestQueueReceivesJob" -v` · `.\Makefile.ps1 test-select -k "TestRetiredSymbolsRemoved" -v` · **new:** a test asserting the gate's list matches the ruled shape — that `rq` is present and that each removed name is absent, so the decision is pinned rather than asserted in prose · **new:** an entrypoint test that `import mkobi.main` succeeds with the ruled list · `uv run ruff check src/mkobi/main.py` · `uv run mypy src/mkobi/main.py` · a container start of the `app` service and of the `rq-worker` service, both reaching a healthy/running state |
| **Definition of done** | `DP-8` recorded with its option · **each of the four named libraries has its own recorded disposition** — kept because a real contract exists, moved to a different gate, or removed with intent established — and no name is disposed of by inference · `rq` remains, with the two-module import census in the commit body · `httpx`'s disposition names the **tier mismatch** explicitly, not merely "unused" · `TestServicesDoNotImportRq` is green unmodified · both entrypoints start · `pyproject.toml` is **not** edited by this block and **HO-1** records the manifest incoherence it leaves behind. |

---

### EB-7 — Gate `openapi_url` with the two human-facing URLs (EXT-010, tier half)

| Field | Value |
| ----- | ----- |
| **Semantic target** | `app.py::create_app`'s `FastAPI(...)` constructor — the `docs_url`, `redoc_url` and `openapi_url` arguments · `docs/99-reference/swagger.md` and `docs/10-deployment/deployment.md` **only as they describe the tier's exposure** |
| **Discharges** | **EXT-010** (tier half). Conflict **X-05** is recorded in EB-0 and applies to the *version* half. |
| **blocked_by** | **`DP-12`** (hard — whose control actually closes this surface). Soft: EB-0. |
| **Execution order** | **8** |
| **Risk — implementation** | **LOW.** One constructor argument, matching a pattern already in the same call. |
| **Risk — rollout** | **LOW for the application; the real effect is nil in the shipped production topology, and that is the point of `DP-12`.** `docker/nginx/nginx.conf` forwards only `location /api` and the two health paths; `/openapi.json`, `/docs` and `/redoc` fall through to `location /`, which serves the React bundle. In production today those paths return the **SPA**, not the schema document. Setting `openapi_url=None` makes the application 404 — which nginx never asks it for. The production protection is **topology**, not code, and this block's value is defence in depth plus an honest record. Saying otherwise would overstate the change. |
| **Risk — regression** | **LOW.** `tests/test_openapi.py::TestOpenAPIErrorSchemas` asserts the **error schema's** presence in the document, which a production-tier gate does not affect; the gate is environment-conditional and the test tier is not production. `tests/test_cors.py::TestCreateAppMetadata` constructs the app in a test environment and would see `openapi_url` at its default — no change. |
| **Risk — compatibility** | **LOW-MEDIUM and tier-scoped.** In the development tier nothing changes. In the production tier the machine-readable document disappears from the application surface — which is the intent and which the topology already delivered by accident. Anything that fetches `/openapi.json` for tooling in production stops working, deliberately. |
| **Agents** | **Planner** (short) — the change is one argument; the work is the `DP-12` framing and the documentation accuracy. **Validator** — required because the block's claim is about what a tier exposes, and that claim must be checked against the shipped compose and nginx configuration rather than against the application. **Auditor / Researcher — not required.** No cross-phase premise is at risk and no external knowledge decides anything. |
| **Documentation impact** | **Required, and it is mostly about accuracy.** `docs/99-reference/swagger.md` documents `/docs` as a development-tier workflow, which remains true. `docs/10-deployment/deployment.md` should state where the production protection actually sits — the nginx `location` set — so a reader does not conclude the application is the control. `docs/SPEC.md` gains a version row. |
| **Verification** | `.\Makefile.ps1 test-select -k "TestOpenAPIErrorSchemas" -v` · `.\Makefile.ps1 test-select -k "test_app_metadata_comes_from_settings" -v` · `.\Makefile.ps1 test-select -k "TestCORSPreflight" -v` · **new:** a test asserting that in the production tier the constructor sets all three of `docs_url`, `redoc_url` and `openapi_url` to `None` — the current code sets **two of three**, and a test that asserts only two would let the third regress silently · `.\Makefile.ps1 test-select -k "test_openapi" -v` · `uv run ruff check src/mkobi/app.py` · `uv run mypy src/mkobi/app.py` · a live `GET /openapi.json` and `GET /docs` on the dev stack confirming they still serve (development tier must be unaffected) |
| **Definition of done** | `DP-12` recorded with its option · all three document URLs are gated on the same condition in the constructor, asserted by a test that covers **all three** · the commit body states plainly that the production protection in the shipped topology is nginx's, not the application's, so no reader over-reads the change · `docker/nginx/nginx.conf` is **not** edited by this block, and any escalation `DP-12` rules for is written as a named hand-over with an owner, not as an untracked observation · the development tier's `/docs` and `/openapi.json` are demonstrably unaffected. |

---

### EB-8 — One source of truth for the advertised version (EXT-010, version half)

| Field | Value |
| ----- | ----- |
| **Semantic target** | `config.py::AppSettings.version` — its declaration and its default · the environment alias that reaches it · `app.py::create_app`'s `version=` argument (**read-only**: it already reads `config.app.version` and must keep doing so) |
| **Discharges** | **EXT-010** (version half). Conflict **X-05**. |
| **blocked_by** | **`DP-9`** (hard — the single source of truth). Soft: EB-0. Cross-phase: **HO-1**, because `config.py` is the repo's highest-churn file and is under phase-01/02 work. |
| **Execution order** | **9** |
| **Risk — implementation** | **LOW-MEDIUM.** The wiring is **already half-done and correct**: `app.py::create_app` reads `config.app.version`, and `tests/test_cors.py::TestCreateAppMetadata::test_app_metadata_comes_from_settings` pins that transfer with an environment override, precisely because the default and the old literal happened to be equal. What remains is that the value itself is hand-written. The work is one declaration plus, under option (a), an import. |
| **Risk — rollout** | **LOW.** Under the ruled option the advertised version begins tracking the installed distribution's version, which means a development install and a container build advertise different values where they used to agree. That is the **intent** — a consumer gains a version with which to detect a contract change — and it is also the reason `tests/test_config.py`'s `app.version` assertion is a live hazard rather than trivia. |
| **Risk — regression** | **MEDIUM, and there is a shipped test in the way.** `tests/test_config.py::TestAppSettings` asserts `settings.app.version == "1.0.0"` — the **default literal**. Any option that derives the default from distribution metadata changes that default and breaks that assertion. The block must update the test **with** the code and state whether the default is now "whatever the installed distribution says" or still a literal with an override path. A second live test — `tests/test_cors.py::TestCreateAppMetadata` — asserts the **override** path and must stay green unmodified: an environment override must still win under every option. |
| **Risk — compatibility** | **LOW on the API; MEDIUM on the document.** The published schema's `info.version` changes value. `pyproject.toml` is at `1.0.8` and the document advertises `1.0.0`, so the change is the fix. Anything that pinned the old string — a pinned generated client, a diff of the document — sees a different value, which is the whole point. `1.0.8` appears nowhere in `docs/` or `frontend/src/` outside a build artefact, so the documentation surface is small. |
| **Agents** | **Planner** — required: `DP-9`'s three options have different failure modes (a distribution that is not installed at runtime, a settings layer that reads its own version from itself, a literal that simply stays), and the choice determines whether the version is derivable in every context the app runs in. **Validator** — required: that the override path still wins, that the default is what the ruling says it is, and that the published document and the manifest now agree. **Auditor / Researcher — not required.** The two competing values are known and the mechanics are local. |
| **Documentation impact** | **Conditional.** Any `docs/` file that shows the schema document's version, or that instructs a consumer to detect a contract change from it, gains a corrected statement. `docs/06-backend/configuration.md` gains the environment variable **only if** `DP-9` rules an env-overridable value — the project already reads `APP__VERSION` through the settings layer, so the table row may already exist and must be checked rather than added blindly. `docs/SPEC.md` gains a version row. |
| **Verification** | `.\Makefile.ps1 test-select -k "TestAppSettings" -v` (**the assertion that must be updated with the code, not deleted**) · `.\Makefile.ps1 test-select -k "test_app_metadata_comes_from_settings" -v` (**must stay green unmodified** — the override path) · `.\Makefile.ps1 test-select -k "TestSettingsFromEnv" -v` and `.\Makefile.ps1 test-select -k "TestSettingsPriority" -v` (**the settings layer must still resolve the value by priority**) · `.\Makefile.ps1 test-select -k "TestOpenAPIErrorSchemas" -v` · `uv run ruff check src/mkobi/config.py` · `uv run mypy src/mkobi/config.py` · a live `GET /openapi.json` on the dev stack, with the returned `info.version` compared against `pyproject.toml`'s declared version **and quoted in the commit body** |
| **Definition of done** | `DP-9` recorded with its option · the advertised version has exactly one source and that source is named in the commit body · the environment override still wins, proven by `TestCreateAppMetadata` staying green unmodified · `tests/test_config.py`'s default assertion is updated **with** the code and states the new default's meaning · the live document's version and `pyproject.toml`'s declared version are compared and quoted, and the comparison is the block's acceptance criterion · `config.py` was re-read for concurrent modification immediately before editing. |

---

### EB-9 — Close EXT-008: verify the landed ordering and keep `VAL-07-005` unscheduled

| Field | Value |
| ----- | ----- |
| **Semantic target** | **No production code.** `services/auth_service.py::AuthService.approve_registration_request` and `::reset_password_admin` (**read-only**: their ordering is verified, not changed) · the three shipped tests in `tests/test_auth_service.py` that pin it (**read-only**) · `docs/04-admin/admin-api.md` (**read-only**: it encodes the decision and must keep matching) |
| **Discharges** | **EXT-008** (verification-only; the finding is already fixed) · **`VAL-07-005`** — recorded as refuted in effect and **deliberately not scheduled**. Conflict **X-03**. |
| **blocked_by** | **Nothing.** Soft only: phase 04's **HO-2** (`AB-1` / `AB-2`) should have landed, because both change the store contract and either could move the ordering. The block runs correctly before that too — it would then record a **drift** rather than a confirmation, which is itself the useful output. |
| **Execution order** | **10**, and **last by design**: it verifies that nothing has moved a decision the landed work already made. |
| **Risk — implementation** | **None.** Nothing is implemented. |
| **Risk — rollout** | **None.** |
| **Risk — regression** | **None in code.** The block's real risk is **bookkeeping**: a later reader finding `VAL-07-005`'s prescription in the report, not knowing it was refuted in effect, and implementing a compensation that reverses a shipped test, two landed docstrings and a shipped document. This block is the answer to that risk. |
| **Risk — compatibility** | **None.** |
| **Agents** | **None beyond Implementor**, with one conditional: **Validator** if the ordering has drifted from the landed state, because then the drift is a finding for phase 04 (whose `AB-1` owns the store contract) and not for this block. **Auditor / Researcher — not required and explicitly not wanted:** an Auditor here would re-derive what the shipped tests and docstrings already state in full, and a Researcher would be inventing external best-practice arguments against a decision this repository made on purpose. |
| **Documentation impact** | **None.** The rule the report wanted written is already written twice — in `approve_registration_request`'s and `reset_password_admin`'s docstrings, which argue the ordering **on purpose**, and in `docs/04-admin/admin-api.md`. Writing it a third time would be documentation noise. The only record this block adds is a `docs/SPEC.md` **version row** naming the plan, per house convention. |
| **Verification** | `.\Makefile.ps1 test-select -k "test_approve_registration_request_commit_precedes_store" -v` (**green — it is the pin**) · `.\Makefile.ps1 test-select -k "test_approve_registration_request_failed_commit_leaves_no_credential" -v` · `.\Makefile.ps1 test-select -k "test_approve_registration_request_store_failure_after_commit_keeps_user" -v` (**green — this is the test that refutes `VAL-07-005`'s prescribed outcome, and it is the reason the compensation must not be scheduled**) · `.\Makefile.ps1 test-select -k "test_store_fail_open_on_error" -v` · `.\Makefile.ps1 test-select -k "test_store_failure_after_commit_returns_success" -v` · `.\Makefile.ps1 test-select -k "test_reset_user_password_admin" -v` (**the fourth pin the report missed**) · `uv run ruff check src/mkobi/services/auth_service.py` · `uv run mypy src/mkobi/services/auth_service.py` — both as a **drift check**, since this block edits nothing |
| **Definition of done** | The six named tests are green and the commit body states the verification's outcome as either *confirmation* (the ordering holds as landed) or *drift* (it does not, and the drift is attributed to a named block) · **`VAL-07-005`'s prescribed compensation is explicitly recorded as not scheduled, with the three artefacts that contradict it named** — the shipped test, the landed docstrings and `docs/04-admin/admin-api.md` · no production file is edited by this block · `EXT-008` is marked **already-fixed, verification-only** in the coverage ledger with the landed commit recorded · the report's dead `admin.py` anchors are re-listed so no implementor spends an anchor budget on them. |

---

## Open decisions — owner rulings required

**This plan chooses none of them.** `DP-1` … `DP-10` are carried verbatim from the code context §6,
including its own instruction "I pick none". `DP-11` and `DP-12` are **raised by this Planner**, each
marked as such, following phase 04's `D-04-I` … `D-04-L` precedent. Each record states what stays
blocked until it is ruled. `DP-5` and `DP-10` block nothing by design — they are recorded so they are
not dropped.

### DP-1 — What does the health probe measure?

**Gating:** EB-1 (hard). **Chooser:** Tech Lead, with **phase 10 as co-signer** of the probe contract.

The report's answer — add a Redis `PING` to `/health`, return 503 on failure — is **not executable as
written**: a shipped test asserts `/health`'s body by exact dict equality, and a shipped document
argues the current design on purpose. Both are load-bearing and both are recorded in EB-1's
constraints.

| Option | Shape | Trade-off |
| ------ | ----- | --------- |
| **(a)** | **Drop the `/health` half; extend `/health/detailed` only** | Keeps the documented decision intact and needs no change to any `service_healthy` consumer. A Redis `PING` becomes a detailed component that never moves the overall status — the shape the reconciler component already uses. Leaves `EXT-001`'s core complaint unanswered for anyone polling only `/health`, which `health-api.md` explicitly tells operators to do. |
| **(b)** | **Add Redis to `/health`, 503 on failure** | Closes the finding for every existing consumer. Under `--workers 4` a Redis blip makes three of four workers unhealthy, and at least three services in the shipped compose gate on `condition: service_healthy` — so the reverse proxy and its dependents refuse to start. Converts a degraded background sweep into a total API outage. Requires `DP-2` to change the shipped test. |
| **(c)** | **Split the endpoints** (a new readiness path) | Additive: existing consumers keep their current contract, and a consumer that migrates gets the wider answer. A third path is a new public surface with its own documentation, its own probe configuration and its own `depends_on` wiring, and anything not migrated keeps the old blind spot. |
| **(d)** | **Leave `/health` DB-only and change the documented consumer contract** | Smallest code change. Requires rewriting the operator guidance that tells load balancers and uptime monitors to use `/health` for instance availability — a documentation change that makes the documentation *less* accurate about what the endpoint can tell you. |

### DP-2 — What happens to `test_health.py`'s exact-dict assertion?

**Gating:** EB-1's definition of done. **Chooser:** **phase 09** owns the test-quality ruling;
**phase 07** owns the production change.

| Option | Trade-off |
| ------ | --------- |
| **(a)** Update the test with the code and rewrite its class docstring (which states the opposite intent) | Honest if the intent genuinely changed. The assertion is an *exact* equality, so it is a strong contract, not an incidental one — rewriting it is a decision about the endpoint, not about the test. |
| **(b)** Relax to key-subset membership, matching `/health/detailed` | Makes the two handlers' tests consistent. **Weaker**: the exact-dict assertion is exactly what would have caught this class of change, and relaxing it permanently removes that. |
| **(c)** Add a second test pinning the new intent alongside the existing one | Keeps both contracts visible. Two tests asserting different shapes of the same endpoint is a contradiction, unless the endpoint genuinely has two forms. |

### DP-3 — Where do the Redis transport bounds live?

**Gating:** EB-2 (hard). **Chooser:** **phase 01** owns `config.py`; **phase 07** owns the call.
**Unruled in every existing plan** — the code context records this as a seam that straddles phases 01
and 07 with no ruling anywhere.

| Option | Trade-off |
| ------ | --------- |
| **(a)** Inline literals in `core/redis_client.py` | Smallest diff and no settings-surface change, so no coordination with phase 01. Not operator-tunable: a deployment that needs a different timeout edits code. The value is still discoverable at one site. |
| **(b)** New `RedisSettings` fields with environment aliases | Matches the project's settings discipline; the bound becomes operator-tunable and documented in `docs/06-backend/configuration.md`. Touches `config.py`, the repo's highest-churn file, which is under concurrent phase-01/02 work — a real collision cost. |
| **(c)** Both | Every bound configurable, with an inline floor that a setting cannot go below. Two places to read for one number, which is the ambiguity this plan generally tries to remove. |

### DP-4 — Is retry policy a config value or a code invariant?

**Gating:** EB-2. **Chooser:** Tech Lead — a reliability-versus-latency call across **53 authenticated
operations** that all share one client.

| Option | Trade-off |
| ------ | --------- |
| **(a)** Pin `Retry(NoBackoff(), 0)` — the report's step | Matches the declaration being made explicit: this project does not retry. Collapses the measured ~59 s to one 5-second attempt. A single dropped packet becomes a user-visible failure on the authentication path. |
| **(b)** A small bounded retry to survive one packet loss | Recovers the transient case, at a multiplied worst-case latency. The current default's *eleven* attempts are clearly not intended, but "not eleven" does not imply "zero". |
| **(c)** Timeouts only, leave retry at the library default | Smallest change and it does fix the number that matters most. Leaves the retry count as an undeclared dependency on a version the lockfile pins today and may bump tomorrow — the defect the finding is about, partially. |

### DP-5 — The five `bidb` rows `VAL-07-011` names

**Gating:** nothing. **Chooser:** **Coordinator**, not the Planner.

Two of them are a live instance of the very defect `EXT-005` describes: an account that exists, is
active, is flagged `force_password_change`, whose password is held by nobody, with its registration
request already `approved` and therefore not re-approvable. The other three are pending requests from
the report's own reproductions. **A Planner must not create or delete database rows.** Options —
delete, record as knowingly retained, or leave — are stated in the code context; none is executed
here, and none may be executed silently by any block in this plan.

### DP-6 — Is the strict base applied to all request bodies or only the write bodies?

**Gating:** EB-5's strict-base sub-item. **Chooser:** **phase 07 with phase 16**; needs the frontend
field census first, and that census is EB-5's **Auditor** deliverable.

| Option | Trade-off |
| ------ | --------- |
| **(a)** All request bodies (the report's scope) | Uniform and complete: no boundary is left permissive by accident. Largest `422` surface, and every read-shaped body is affected too, which buys less than the write shapes do. |
| **(b)** Writes only, reads left permissive | Smallest blast radius and the highest value per unit of regression risk, since silent drops on a write are what corrupt state. Leaves an inconsistency a future reader has to reason about, and a read model is still a documented contract. |
| **(c)** All, with a per-model opt-out for fields the frontend demonstrably over-sends | Most honest about reality, and it builds the opt-out mechanism **before** it is needed. Two mechanisms to keep in step, and the census must be re-run whenever a payload changes. |

### DP-7 — Register the route, or emit a path-relative `Location`?

**Gating:** EB-4. **Chooser:** Tech Lead. Option (a) is wire-visible on four declared paths.

| Option | Trade-off |
| ------ | --------- |
| **(a)** Route registration on the four collection paths | Closes both halves of the finding: the declared shape becomes the matched shape, and the anonymous `307` disappears. Changes the published document's four paths and breaks any client that does not follow a redirect. |
| **(b)** Path-relative `Location` | No contract change and the caller-echoed `Host` is gone. The existence oracle **remains** — which is the finding's primary effect, not a secondary one. |
| **(c)** Both | The strongest outcome and the larger change: a new declared shape plus the header fix. Two mechanisms for one four-path problem. |

### DP-8 — What shape should the startup gate have?

**Gating:** EB-6. **Chooser:** **phase 01** (`TOPO-001` owns the residue) with **phase 07**.

| Option | Trade-off |
| ------ | --------- |
| **(a)** Split into app-required and worker-required sets | Most accurate: `rq` is a **worker** contract and `httpx` is a **test** contract, and the API app needs neither. Two lists, two entrypoints to keep in step, and the report's instruction to *establish intent* is deferred rather than satisfied. |
| **(b)** Drop the three gate-only names, keep `rq` | Smallest change and the direction the report names. But this plan's re-derivation says the three are **not homogeneous**: `plotly` and `tenacity` are genuine absences, while `httpx` is a real dependency at the wrong tier. Dropping all three alike discards that distinction. |
| **(c)** Establish intent for `httpx` / `plotly` / `tenacity` first, then defer | The report's own instruction, and the intellectually honest order. Leaves `EXT-009` open, which is the correct outcome when the question is *"is this dependency wanted?"* rather than *"is this code correct?"* — and no external research substitutes for that answer. |

### DP-9 — What is the single source of truth for the advertised version?

**Gating:** EB-8. **Chooser:** **phase 01** owns the settings surface; `config.py` is the repo's
highest-churn file.

| Option | Trade-off |
| ------ | --------- |
| **(a)** `importlib.metadata.version` | One source, and it is the manifest — which is where a release process already bumps it. Requires the distribution to be *installed* in every context the app runs in; a source checkout run without an install has no metadata, which is a real deployment shape to check. Breaks `tests/test_config.py`'s default assertion. |
| **(b)** A new env-overridable `config.app.version` defaulting to the distribution version | Both a default and an override, matching the settings layer's discipline. Two things can express the value again, which is the ambiguity option (a) avoids — but the override path is what `TestCreateAppMetadata` already proves. |
| **(c)** Leave the literal, fix the documentation | Zero risk and closes nothing. The document would then be *correct about being stale*, which is a documentation outcome, not the finding. |

### DP-10 — Does phase 07 re-file what the sibling plans own?

**Gating:** nothing — it is already answered by this plan's evidence, and recorded so the answer is
visible rather than assumed. **Chooser:** **Coordinator** — a recommendation-grade question.

**(a)** Hand-overs only — **this plan's choice, on the code context's evidence**: five of ten
findings are owned by executed or in-flight sibling plans and one is already fixed, so re-filing them
would produce two teams editing one symbol for one reason. **(b)** Re-file the `rq-worker` row despite
`EXT-009` declining it — refused; the report's own reasoning is correct and re-filing would be a
worse duplicate than the hand-over it replaces. **(c)** Re-open the `--forwarded-allow-ips` wildcard
to re-confirm it — **refused**; `VAL-07-002`'s prohibition is a closed decision under phase 04's
applied `VAL-04-001`, and reopening a settled decision is worse than inheriting it silently. If the
Coordinator rules otherwise, this plan's scope tables and block map are the artefacts to amend.

### DP-11 — Reject an oversized anonymous report, or truncate it? *(raised by this Planner)*

**Gating:** EB-3. **Chooser:** Tech Lead, with phase 16 informed as the eventual caller.

The code context's `DP-1` … `DP-10` do not cover this fork, and the report recommends both halves at
once — cap the fields **and** add a `Content-Length` pre-check — without saying what a caller receives.

| Option | Trade-off |
| ------ | --------- |
| **(a)** **Reject** an oversized body with a status the project already uses | Loud and honest; the project has the precedent — `tests/test_streaming_size_limit.py::TestStreamingSizeLimit` pins **413** for an oversized inbound body, including the case where no `Content-Length` is present. A caller whose browser produced a 5 MB component stack learns so immediately. Changes an endpoint whose every accepted answer today is `204`. |
| **(b)** **Truncate** to a cap and log the untruncated length beside the capped value | The endpoint keeps answering `204` for everything, which is the least disruptive possible change and preserves the reporting workflow's tolerance for large payloads. A silently-degraded record is exactly the class of defect `EXT-003` is filed about — traded from the log volume to the log content. |
| **(c)** Reject on a declared header, truncate on the value | Belt and braces: the cheap check refuses the obvious case and the value bound catches the chunked case. Two rules to reason about, and it is the shape the project's own upload path already proves is necessary — a header check alone does not bind a body. |

**Independently of the ruling:** the bound belongs on the **parsed field values**, not on
`Content-Length`. `tests/test_streaming_size_limit.py` exists because `file.size` can be `None`; a
header-only check does not bind a chunked body, and treating it as the fix would repeat the defect one
layer up.

### DP-12 — Whose control actually closes the production schema surface? *(raised by this Planner)*

**Gating:** EB-7. **Chooser:** Tech Lead with phase 10 (or phase 12, who owns `nginx.conf`).

`EXT-010` recommends setting `openapi_url=None` "alongside the other two URLs". In the shipped
production topology the application is **not** what closes that surface: `nginx.conf` forwards only
`location /api` and the two health paths, so `/openapi.json`, `/docs` and `/redoc` fall through to
`location /` and receive the React bundle today. The one-line change is correct and has no shipped
effect — which is worth deciding explicitly rather than discovering later.

| Option | Trade-off |
| ------ | --------- |
| **(a)** App-only gate; record nginx as the real control and hand the gap over | Cheapest, correct as defence in depth, and honest about the topology. The application-level gap is closed but the production behaviour is unchanged, so a reader must be told why the change exists. |
| **(b)** App gate **and** an nginx `location` that refuses the three paths | Closes the surface where it is actually open. `docker/nginx/nginx.conf` is **not** this phase's file (phase 12 per plan 04's `C04-5`, phase 10 on deployed composition), so this option converts a one-line change into a cross-phase edit. |
| **(c)** Neither; record only | Zero code. Leaves the application's `/openapi.json` ungated while the documentation claims the tier gates it — which is the documentation defect `EXT-010` is, in part. |

---

## Cross-phase seam and hand-over register

Every item is a hand-off with a **named owner**. None is a phase-07 deliverable.

| # | Seam | Symbols | Phase 07's half | Owner | What phase 07 owes | What phase 07 must not do |
| - | ---- | ------- | --------------- | ----- | -------------------- | -------------------------- |
| **HO-1** | **Rate-limit key identity and proxy trust** (`EXT-004`, whole) | `api/routes/auth.py`'s login / refresh / register-request limiters · `api/routes/client_errors.py`'s `client_ip` derivation and `client-errors:` key · `api/routes/upload.py`'s `upload:` key (correctly principal-keyed, unaffected) · `docker/Dockerfile`'s production `CMD` · `docker/docker-compose.override.yml`'s dev `command:` | **None.** The collapse is mechanism-confirmed; the remediation is phase 04's. EB-3's *shared-pool* consequence cannot be reasoned about until this lands, which is the block map's dotted edge. | phase 04 — **AB-6** (key identity), **AB-7** (proxy trust) | Inherit `VAL-07-002`'s prohibition as **closed**: no block in this plan may name `--forwarded-allow-ips="*"` as an option. Record that EXT-004's "email branch is unreachable" sub-claim is **refuted for `register-request`** — that route declares `client_ip: str \| None = None` and assigns it only under `if request.client:`, so the email branch is reachable exactly when the peer is absent. | Do not edit `Dockerfile`, the override's `command:`, or any rate-limit key. Do not re-open the wildcard. |
| **HO-2** | **Revocation-read failure direction and the credential-store contract** (`EXT-002`'s refusal class, `EXT-005` both halves) | `api/deps.py::get_current_user_dependency`'s two revocation reads · `core/permissions.py::_get_current_user_with_session`'s two reads (no src-level caller, but a **silent** fifth and sixth edit site for any guard) · `core/security.py::is_token_revoked` / `::is_user_tokens_revoked` · `core/temp_password_store.py::TempPasswordStore.store` / `.retrieve` · `services/auth_service.py::AuthService.approve_registration_request` / `::reset_password_admin` · `api/routes/admin.py::retrieve_temp_password_admin_endpoint` | **Blast radius and cost only.** EB-2 declares the transport bound and enumerates the six sites; it changes no refusal class and no store contract. | phase 04 — **AB-5** (revocation-read direction), **AB-1** (credential issuance reporting), **AB-2** (retrieval refusal semantics) | Enumerate **six** revocation-read sites, not the report's two (`VAL-07-004` applied, and larger than reported). State that `ErrorCode.SERVICE_UNAVAILABLE` **exists** and is already mapped to 503 — **no new enum member** (`VAL-07-003` applied). Carry `VAL-07-008`'s **four** test pins, including the one the report missed. Carry `VAL-07-001`'s escalation and the dead-anchor correction. | Do not edit `deps.py`'s catch-all, `permissions.py`, the store's contract, or the two service methods. Do not add an `ErrorCode` member. Do not implement `VAL-07-005`'s compensation — see EB-9. |
| **HO-3** | **Health probe contract** (`EXT-001`, deployed-composition half) | `docker/Dockerfile`'s `HEALTHCHECK` · `docker/docker-compose.yml`'s `app` healthcheck and its `condition: service_healthy` dependents · `docker/nginx/nginx.conf`'s `location ~ ^/health(/detailed)?$` · `docs/10-deployment/deployment.md`'s probe guidance | **What the probe measures** (EB-1). | phase 10, as **co-owner** — co-owned, **not merged** | Name phase 10 as co-signer of `DP-1` in the commit body. State that at least three compose services gate on `condition: service_healthy` against the app, and that the dev-tier healthcheck is **re-enabled** (`9c49c20`) — the report's "disabled in dev" refinement is refuted and must not be repeated. | Do not edit any `docker/` file. Do not restate the dev-healthcheck claim. |
| **HO-4** | **Schema surface in production** (`EXT-010`, tier half) | `docker/nginx/nginx.conf`'s `location /api` / health `location` / `location /` | **The application's constructor argument** (EB-7), plus the fact that the production control is nginx's. | phase 12 (`nginx.conf`) / phase 10 | Write the topological fact into the commit body so no reader over-reads the application-level change. Escalate as a **named** hand-over under `DP-12` option (b), never as an untracked observation. | Do not edit `nginx.conf`. Do not describe the application as the production control. |
| **HO-5** | **Frontend consequence of strict request bodies** (`EXT-007`) | `frontend/src/**` request construction · the SPA's error interceptor, which also treats a `401` as "refresh the token" | **The model policy and the census that makes it decidable** (EB-5). | phase 16, as **co-owner** | Deliver the frontend field census **by symbol** in EB-5's commit body, before any `forbid` lands, and name every caller that had to be fixed. | Do not edit `frontend/src/`. Do not land a strictness policy without the census. |
| **HO-6** | **Credential material reaching a sink** (`EXT-003`, sink half) | The log sink itself | **The volume bound** (EB-3). | phase 15 | Split the finding explicitly: the unbounded-volume half is EB-3's; the sink question is phase 15's, with a different mechanism and a different owner conversation. | Do not open the sink question. Do not treat the volume cap as a sink fix. |
| **HO-7** | **Manifest dependency residue** (`EXT-009`) | `pyproject.toml`'s `[project].dependencies` | **The gate's coherence** (EB-6). | phase 01 | Record the incoherence EB-6 leaves: `plotly` and `tenacity` are declared runtime dependencies with **zero** references anywhere in `src/`, `tests/`, `docker/` or `alembic/`, and `httpx` is a test-tier contract declared as a runtime dependency. Also recorded and **not** absorbed: `requests`, `pyjwt` alongside `python-jose`, and `asgiref` in a stack that contains no Django. | Do not edit `pyproject.toml`. Do not treat a trimmed gate as a trimmed manifest. |
| **HO-8** | **Test-quality rulings** | `tests/test_health.py`'s exact-dict assertion · `tests/test_rate_limiting.py`'s vacuous per-IP test | **The production changes** (EB-1, and EB-3 by consequence). | phase 09 | State in EB-1's commit body that `DP-2` is phase 09's ruling and that the assertion was not weakened. | Do not relax an assertion to make a change land. Do not fix the rate-limit test — it belongs to the phase that owns test quality. |

## Findings-coverage ledger

Every `EXT-*` and `VAL-07-*` identifier in the report, and where this plan accounts for it.

| ID | Disposition in this plan | Block / home |
| -- | ------------------------ | ------------- |
| **EXT-001** | **Owned in part.** The probe-measurement half is a decision, not a patch, and carries two blocking artefacts. The deployment half is **already landed** under phase 02 `B3` / `TOPO-008`. Co-owned with phase 10. | **EB-1** · **HO-3** |
| **EXT-002** | **Owned in part.** The undeclared transport bound and the 53-operation blast radius are phase 07's. The refusal class is phase 04's — and `ErrorCode.SERVICE_UNAVAILABLE` already exists. | **EB-2** · **HO-2** |
| **EXT-003** | **Owned whole.** Highest-band unowned finding. No first-party caller exists; the documented contract already names two `error` fields. | **EB-3** · **HO-6** |
| **EXT-004** | **Handed over whole.** Merged into phase 04 `AUTH-001`; owned by `AB-6` and `AB-7`. The wildcard prohibition is **closed**. | **HO-1** |
| **EXT-005** | **Handed over whole.** Merged into phase 04 `AUTH-002` (write) and `AUTH-006` (read); owned by `AB-1` and `AB-2`. Every `admin.py` anchor the report cites is dead. | **HO-2** |
| **EXT-006** | **Owned whole**, scoped to the **four** trailing-slash collection paths. `VAL-07-007` applied. | **EB-4** |
| **EXT-007** | **Owned whole**, in three sub-items of which only the strict base is gated by `DP-6`. The six `{"extra": "allow"}` internal types are explicitly **not** carried on an inference. | **EB-5** · **HO-5** |
| **EXT-008** | **Verification-only.** Already fixed (`2de4156`, phase-02 block `B7` / `TOPO-006`) and pinned by three shipped tests. `VAL-07-005`'s prescribed compensation is **refuted in effect and not scheduled**. | **EB-9** |
| **EXT-009** | **Owned whole.** Re-derived: `REQUIRED_MODULES` is **thirteen** names; `rq` is genuinely imported by **two** modules across **four** import statements and stays; `plotly` and `tenacity` are genuine absences; `httpx` is a **tier mismatch**, not an absence. | **EB-6** · **HO-7** |
| **EXT-010** | **Owned whole, split into two blocks.** The tier half is unblocked; the version half waits on `DP-9` and a `config.py` hand-over. | **EB-7** · **EB-8** · **HO-4** |
| **VAL-07-001** | **Applied and escalated** — EXT-005 registered as merged with a named owner per half. | EB-0 · **HO-2** |
| **VAL-07-002** | **Applied and closed** — phase 04's `VAL-04-001` already deleted the option. Inherited, not re-opened. | EB-0 |
| **VAL-07-003** | **Applied** — no new `ErrorCode` member anywhere in this plan. | EB-0 · EB-2 |
| **VAL-07-004** | **Applied** — six sites, not two; the refusal class handed over. | EB-0 · **HO-2** |
| **VAL-07-005** | **Refuted in effect. Recorded and deliberately NOT scheduled.** | EB-0 · EB-9 |
| **VAL-07-006** | **Applied** — the bound is designed against eleven 5-second attempts, not three. | EB-0 · EB-2 |
| **VAL-07-007** | **Applied** — four paths, not 43. | EB-0 · EB-4 |
| **VAL-07-008** | **Applied** — both store tests plus the fourth pin, carried to phase 04. | EB-0 · **HO-2** |
| **VAL-07-009** | **Superseded** — the method is kept, the numbers discarded. | EB-0 |
| **VAL-07-010** | **Applied** for (a)–(c); (d) superseded by `VAL-07-001`. The unnamed **fifth** error is recorded. | EB-0 |
| **VAL-07-011** | **Not actionable for this role** — carried as `DP-5` and named in the out-of-scope table. Not dropped. | `DP-5` |

**Tally.** Ten audited findings: **6 owned whole** (`EXT-003`, `EXT-006`, `EXT-007`, `EXT-008`
verification-only, `EXT-009`, `EXT-010`), **2 owned in part** (`EXT-001`, `EXT-002`), **2 handed over
whole** (`EXT-004`, `EXT-005`). Eleven report-level defects: **9 applied**, **1 closed and inherited**
(`VAL-07-002`), **1 recorded as refuted in effect and not scheduled** (`VAL-07-005`), **1 not
actionable** (`VAL-07-011`), **1 superseded** (`VAL-07-009`, counted inside the applied nine). Twelve
decision records: ten carried verbatim, two raised by this Planner.

## Execution order

One implementor at a time (project rule). The order below is the queue; the block map is the subset
that must hold.

| # | Block | Gate before it starts | Depends on |
| - | ----- | ---------------------- | ---------- |
| 1 | **EB-0** | none | — |
| 2 | **EB-1** | `DP-1` ruled (with phase 10 co-signature) · `DP-2` ruled (with phase 09) | EB-0 |
| 3 | **EB-2** | `DP-3` ruled (with phase 01) · `DP-4` ruled | EB-0 |
| 4 | **EB-3** | `DP-11` ruled | EB-0 (dotted: EB-2) |
| 5 | **EB-4** | `DP-7` ruled | EB-0 |
| 6 | **EB-5** | the frontend field census complete (Auditor), **then** `DP-6` ruled | EB-0 |
| 7 | **EB-6** | `DP-8` ruled (with phase 01) | EB-0 |
| 8 | **EB-7** | `DP-12` ruled | EB-0 |
| 9 | **EB-8** | `DP-9` ruled · `config.py` re-read for concurrent modification | EB-0 (dotted: EB-7) |
| 10 | **EB-9** | — | EB-0 (soft: **HO-2**) |

**EB-7 is first among the executable blocks by a practical measure**: it is the only block with a
one-argument change, no cross-phase edit and a test that does not already exist, so it is the cheapest
evidence that the plan's queue is workable. **EB-9 is last by design** — it verifies that nothing moved
a decision the landed work already made, which is only meaningful after the other blocks have run.

## Verification commands

Tests run in Docker only — there is no test database on `localhost`.

| Purpose | Command |
| ------- | ------- |
| Full suite | `.\Makefile.ps1 test` |
| Targeted | `.\Makefile.ps1 test-select -k <name> -v` |
| Lint | `uv run ruff check <path>` |
| Typecheck | `uv run mypy <path>` |
| Auto-fix (incl. import sorting, `I001`) | `uv run ruff check --fix <path>` |
| Everything | `.\Makefile.ps1 check` |

`ruff check --fix` handles import sorting (`I001`); `ruff format` does not. **A green gate is not a
verification statement for EB-1, EB-2, EB-3 or EB-5** — none of these four defects is visible to `ruff`
or `mypy`. Each block's verification row names the **tests** that carry the evidence, not the gates.

## Tests that will break, and how

| Test | What happens | Required response |
| ---- | ------------ | ----------------- |
| `tests/test_health.py::TestHealthWithRedisDown::test_health_still_healthy_when_redis_down` | Asserts `/health`'s body by **exact dict equality** and its class docstring states the intent being defended. Any remedy adding a key or a non-200 to `/health` breaks it. | **Never delete it to make a change land.** `DP-2` decides: update it with the code, or keep `/health`'s two-key shape. The detailed-endpoint assertions are membership-only and survive. |
| `tests/test_config.py::TestAppSettings` | Asserts `settings.app.version == "1.0.0"` — the **default literal**. Any option that derives the default from distribution metadata changes it. | Update **with** the code, stating the new default's meaning. Not deleted. |
| `tests/test_cors.py::TestCreateAppMetadata::test_app_metadata_comes_from_settings` | Asserts the **override** path (`APP__VERSION=9.9.9`) reaches the application. | **Must stay green unmodified under every `DP-9` option.** An environment override must still win. |
| `tests/core/test_temp_password_store.py::TestTempPasswordStore::test_store_fail_open_on_error` | Encodes fail-open on the credential write **by name**. | **Phase 04's `AB-1`, not this phase's.** EB-2 must not break it; the store's contract is not EB-2's to change. |
| `tests/core/test_temp_password_store.py::TestTempPasswordStore::test_retrieve_fail_graceful_on_error` | Encodes the graceful-refusal contract on the read side. | **Phase 04's `AB-2`.** Recorded for `HO-2`; not touched here. |
| `tests/test_auth_service.py::test_approve_registration_request_commit_precedes_store` | Pins the ordering `2de4156` landed. | Must stay green. Any reordering back to store-before-commit is a regression, not a fix. |
| `tests/test_auth_service.py::test_approve_registration_request_store_failure_after_commit_keeps_user` | Pins "a store failure **keeps** the user and still returns the token". | **This is the test that refutes `VAL-07-005`'s prescribed compensation.** It must stay green, and EB-9 exists to keep it green. |
| `tests/test_admin_user_management.py` — the admin-reset case | Asserts `200` plus a present `retrieval_token`. The **fourth** pin `VAL-07-008` did not name. | Phase 04's `AB-1`. Recorded for `HO-2`. |
| `tests/test_task_queue.py::TestServicesDoNotImportRq::test_no_service_module_imports_rq` | AST-walks `src/mkobi/services/` and asserts no module imports `rq`. Satisfied today and it is **why** `rq` stays in the gate. | **Must stay green unmodified under EB-6.** If an `rq` import appears under `services/`, the block has gone wrong. |
| `tests/test_rq_worker.py`, `tests/test_config.py::TestRqWorkerComposeWiring` | Prove `rq` is a real contract for the worker entrypoint. | Must stay green unmodified. They are EB-6's evidence for keeping `rq`. |
| **Every write-route test** | `extra="forbid"` on the request bodies turns a silently-dropped field into a `422`. | **Fix the caller, not the policy.** Hand-built payloads in the suite that over-send are themselves the census evidence EB-5 needs. |
| `tests/test_rate_limiting.py::TestRateLimitingIntegration::test_rate_limit_reset_allow_writes` | Hard-codes the `login:` key's peer literal. | **Phase 04's `AB-6`**, not this phase's. EB-3 does not change any rate-limit key. |
| `tests/test_rate_limiting.py::TestRateLimitingIntegration::test_different_ips_have_separate_limits` | Its **name** promises per-IP separation it never exercises. | **Phase 09's** test-quality item. Recorded in the out-of-scope table; not fixed here. |

## Rollout safety

**The narrow change that is not narrow.** `EXT-001` is the one place in this plan where a
straightforward-looking remedy inverts the failure mode it targets. `docs/05-health/health-api.md`
already argues this, `app.py`'s own comment already argues it, and at least three services in the
shipped compose gate on `condition: service_healthy` against the app. **A Redis blip that stops making
`/health` return 200 stops the reverse proxy and its dependents from starting** — turning a degraded
background sweep into a total API outage. That is why `DP-1` is a decision with a named co-signer and
not a line in a task list, and why EB-1's definition of done requires both blocking artefacts to be
cited rather than worked around.

**The release note is a deliverable of EB-2, written by phase 04.** During a Redis outage the
user-visible outcome changes from a `401` that the SPA answers with a silent refresh — which needs the
same Redis, so the user sees a sign-out loop — to a `503` that stops the refresh attempt. That is
correct, it is **phase 04's `AB-5`**, and it belongs in `AB-5`'s release note. EB-2 contributes the
input: the per-request cost drops from an undeclared ~59 s to a declared bound, which is the condition
under which `AB-5`'s 503 becomes reachable in a useful timeframe.

**Nothing in this plan changes stored data.** EB-3 bounds what is logged; EB-4 changes four declared
paths; EB-5 changes which bodies are accepted; EB-6 trims a gate; EB-7 and EB-8 change a document
advertisement; EB-2 declares a transport bound. No block writes, deletes or migrates a row, and
`VAL-07-011` and `DP-5` name database hygiene as belonging to nobody in this phase.

**Sequencing with the frontend owner is EB-5's sharpest edge.** Converting `extra="ignore"` to
`extra="forbid"` turns silent field drops into `422`s on every write surface. That is correct and it
will be reported as a regression. The mitigation is not a caveat in a release note — it is the field
census landing **before** the policy, which EB-5's `blocked_by` makes a hard gate.

**`tests/test_health.py` is a shipped test and a documented decision in the same repository, and they
disagree with the report.** Neither is edited by this plan. `DP-2` exists so that a test-quality
question is answered by the phase that owns test quality rather than settled by whichever implementor
reaches the endpoint first.

## Residual risk after the whole plan

- **The probe still cannot tell an operator that Redis is down.** If `DP-1` rules option (a), the
  defect survives for anyone polling `/health` alone — which the documentation tells operators to do.
  The plan makes the trade explicit and recorded; it does not make it disappear.
- **`httpx`, `plotly` and `tenacity` remain declared runtime dependencies.** EB-6 makes the *gate*
  coherent; the *manifest* is phase 01's (`HO-7`). A deployment can still install two libraries no code
  path reaches.
- **`CONFIG` and `APP` are two live churn fronts.** `config.py` (EB-2 under `DP-3` option b, EB-8) and
  `app.py` (EB-1, EB-7) are the repo's highest-churn files and are under concurrent phase-01/02 work.
  Every implementor re-resolves by symbol immediately before editing and re-checks `git status`.
- **The `filters` document and `GraphConfigDict` remain unvalidated at the boundary** unless EB-5's
  non-gated sub-items ship. They are independent of `DP-6` and may land first or may not land at all —
  the plan does not pretend a gated block governs them.
- **The RQ worker's broker path is the only Redis path with a declared retry, and EB-2's bound may
  govern it by accident** if the bound lands at the shared construction function. The block's
  verification explicitly names the worker tests for that reason; it is a residual the implementor
  must confirm rather than assume.
- **Five `bidb` rows and a set of orphan `temp_pwd:` keys remain**, one of which is a live
  unrecoverable account. `VAL-07-011` and `DP-5` state this and schedule nothing: no phase in this set
  owns database row hygiene, and a Planner may not perform it.
- **Report coordinates stay wrong.** EB-0 records that and does not repair the audit corpus. Anyone
  reading the report as a checklist must re-derive locations by symbol — and, per §2 of this plan,
  must re-derive the two figures this Planner found to be counts rather than sites.


