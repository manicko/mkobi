---
phase: 13-client-tier
executed: 2026-09-30
executor: validator
problems-only: true
findings: 6
by-severity:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 5
  LOW: 1
baseline: d008f555f5a2e1b3adb397c4bc67d95ed9c964c5
baseline-dirty: "yes — D .ai/builders/**, D .ai/structure/**, D .ai/models/**, D .ai/templates/**, D .ai/plans/audit-fix-plan.md, D .ai/audit/templates/audit-final-report.md, D frontend/coverage/** (15 tracked files); M .dockerignore, docker/Dockerfile, docker/docker-compose.yml, docker/docker-compose.override.yml, src/mkobi/{app,core/task_queue,rq_worker_wrapper,services/data_service,services/file_processing,workers/data_worker}.py, tests/{test_config,test_data_service,test_rq_worker,test_upload_api}.py; untracked .ai/audit/**, .ai/plans/*, tests/test_app_lifespan.py, tests/test_task_queue.py. frontend/coverage/ is absent on disk; frontend/dist exists untracked."
---

# Phase 13 — Validated Findings

## Summary

The input was re-derived at `d008f555` — one commit past the `f107d59` baseline it records, and against
the concurrent remediation's own uncommitted changes to `docker/`, `.dockerignore`, six backend modules and four
test files. All ten findings were re-derived from the executing path rather than from the quoted text, and
each load-bearing behavioural claim was settled against the code that would actually run: the per-instance
refresh guard in `useAuth.ts`, the three independently-mounted `useAuth()` call sites, the
`max_attempts=10, ttl=300` limiter at `auth.py:315`, the response interceptor's 429 bypass, the three
independent render conditions in `DashboardView`, and TanStack Query's own `error` reducer in the installed
`@tanstack/query-core@5.101.0`, read from `node_modules` rather than assumed. Eight of the ten findings
reproduce as filed. Two carry claims that do not survive: FE-006 asserts the server has no dashboard-name
character rule, and the server has one, character-for-character identical to the client's; FE-008 asserts a
blank plot area, which the payload the sniff selects cannot produce. Both defects are recorded as `VAL-13-`
findings rather than as re-grades, because in each case the finding survives and only the asserted cause is
wrong. The empty CRITICAL band is upheld and argued rather than accepted. The `FE-` namespace carries no
collision anywhere in the set; this report's own findings use `VAL-13-`, recorded as a deviation because the
flat `VAL-` namespace is already occupied by the phase-01
and phase-02 reports.

## Findings

### VAL-13-001 — FE-006 states the server has no dashboard-name character rule; `DashboardCreate` enforces the identical one

**Severity** — MEDIUM

**Zone** — "Which Side Moves: Code or Documentation"

**Observation** — FE-006's rule table carries the row *"name on dashboard create — client
`.min(3).max(100).regex(/^[a-zA-Z0-9\s-]+$/)` (`:25-30`) | server `DashboardCreate.validate_name` — length
3..100 only, no character rule (`models/dashboard.py:58-64`) | diverges — client refuses, server accepts"*, and
its Consequence repeats it: *"a dashboard name such as `Q1 sales (EMEA)` is refused by the client even though
`DashboardCreate` would accept it — … rules the client invented, not rules the system enforces"*. Both halves
are false. `models/dashboard.py:58-67` reads:

```
58:    @field_validator('name')
60:    def validate_name(cls, v: str) -> str:
61:        if len(v) < 3: raise ValueError('Name must be at least 3 characters')
63:        if len(v) > 100: raise ValueError('Name must be at most 100 characters')
65:        if not re.match(r'^[a-zA-Z0-9\s-]+$', v):
66:            raise ValueError('Name can only contain letters, numbers, spaces, and hyphens')
```

Line 65 is the character rule, character-for-character the same regex, with the same error string, as
`formSchemas.ts:28`. `DashboardCreate` rejects `Q1 sales (EMEA)` for the same reason the client does. The
cited anchor `:58-64` resolved to a real range and stopped one line short of the code it claims is absent —
a range that exists but does not say what the report says it says.

**Evidence** — `src/mkobi/models/dashboard.py:58-67` against `frontend/src/shared/types/formSchemas.ts:25-30`;
both read in full at `d008f555`. The finding's other three rows reproduce (`DashboardUpdate.description`
`max_length=200` at `dashboard.py:140` against the client's `.max(500)` at `formSchemas.ts:40`;
`validate_password_or_raise` at `utils/validators.py:193-203` requiring a digit and a letter of any case
against the client's `[A-Z]` at `formSchemas.ts:58`; `auth_service.py:410` lower-casing the submitted domain
against the client's case-sensitive `BLOCKED_DOMAINS.includes(domain)` at `formSchemas.ts:17`), so FE-006 is
confirmed at three of four rows and is not withdrawn.

**Consequence** — The reader is told a rule is client-invented that the server in fact enforces, and the
report's own Roadmap inherits the error: **Step 4** instructs the team to *"drop or serverise the uppercase and
name-character rules"*. A team that executes that instruction literally deletes `formSchemas.ts:28` while
`dashboard.py:65` stays, which does not fix a divergence — it **inverts** it. A dashboard named
`Q1 sales (EMEA)` would then pass client validation, be submitted, and come back as a server 422 the user
cannot act on, which is the exact failure mode FE-006's surviving update-description row already describes.
This is the finding's most consequential effect and it points the wrong way.

**Recommendation** — Strike the `name`-on-create row and the `Q1 sales (EMEA)` example from FE-006; treat
that field as a verified match and move it into the table's "matches" set with `models/dashboard.py:58-67`
cited. Narrow Roadmap Step 4 to the two rules that really diverge (`updateDashboardSchema.description` and
`changePasswordSchema.new_password`) plus the `BLOCKED_DOMAINS` copy, and state the direction for each rather
than "drop or serverise" — in all three surviving cases the server's rule is the enforced one, and the client
is the side that must move. Do not renumber FE-006 or any other phase-13 identifier.

### VAL-13-002 — FE-008's asserted cause is refuted by the shipped Plotly build: the traces are not untyped, so they do not render blank

**Severity** — MEDIUM

**Zone** — "The Vacuous-Control Angle, and Its Bindings: Does It Exist, What Scope Does It Declare, What Did It Examine"

**Observation** — FE-008's Observation states that the row dictionaries handed to Plotly are handed over as
*"objects with no `type`, no `x` array and no `y` array, [so Plotly] finds nothing to draw, and renders an
empty plot area"*. The premise is self-defeating before the bundle is consulted. The sniff at
`ChartRenderer.tsx:21-23` fires **only** when `'x' in graph.data[0] && 'y' in graph.data[0]` — so by
construction the objects handed over carry both `x` and `y`. They carry them as **scalars**, which is a
different claim from "absent". The `type` leg is refuted outright by the artefact that would execute:
`frontend/node_modules/plotly.js-dist-min/plotly.min.js` declares the trace `type` attribute as
`{valType:"enumerated", values:[], dflt:"scatter", editType:"calc+clearAxisTypes", _noTemplating:!0}`. A
trace object with no `type` is a **`scatter`** in this build, and a scatter over one x/y pair draws one
marker.

**Evidence** — `ChartRenderer.tsx:21-23` (the sniff, read in full); `plotly.min.js` at offset 174830 of a
4 842 485-character bundle, the `type` attribute schema with `dflt:"scatter"`; `package.json:25`
(`plotly.js-dist-min ^3.5.1`) and `:27` (`react-plotly.js ^2.6.0`) pinning the versions that bundle ships.
The precise rendered artefact — a single-point scatter in the graph's own `<Paper>` frame, not a blank one —
was **not** observed, because doing so needs a browser and a seeded `x`/`y` column pair; see the coverage
ledger. That residual is recorded as unsettled and is not the load-bearing part of this finding: the claim
that the trace is untyped, and the consequence drawn from it, are both refuted.

**Consequence** — The mechanism, the reachability and the remedy all survive: the sniff is a second code
path taken by accident, it is reachable from configuration alone with no malformed data, nothing on the
surface distinguishes its output from a correct render, and deleting it is the right fix. What does not
survive is the user-visible characterisation. A reader who believes "the charts render blank" will scope the
fix as a rendering failure and will size its verification as *"confirm a chart appears"*. The real symptom is
that a correctly-labelled frame shows one arbitrary point, which reads as a **wrong chart** rather than an
empty one — a materially worse outcome to miss in verification, and the one the input's Rollout Safety
(*"confirm the intended chart appears"*) would not catch, because a single point *is* a chart appearing.

**Recommendation** — Keep FE-008 and its recommendation as filed; correct the Observation's mechanism to
"a `scatter` trace built from row scalars, drawing one marker where the dashboard should draw N", and
restate the reachability as "the first row's `x`/`y` keys satisfy the sniff, so every row is rendered as a
one-point trace and the `config.x` / `config.metrics` mapping is never applied". Re-derive the phase-13
Rollout Safety verification from "confirm a chart appears" to "confirm the trace count and the axis
categories match `config.metrics`", since a one-point plot satisfies the former.

### VAL-13-003 — Block 2's empty band is not empty: `['filterValues', …]` is a server-derived value the client never refetches and never invalidates

**Severity** — MEDIUM

**Zone** — "Does the Input Rest on its Own Declared Blocks and Evidence Fields"

**Observation** — The input's Appendix asserts, as the conclusion of Block 2's cache/key/invalidation
inventory, that *"No server-derived value is treated as authoritative on a refetch the client never issues"*,
and discharges `['filterValues', dashboardId, filterName]` in one clause: *"never invalidated, and never needs
to be."* The second half is the finding. `useFilterValues` (`dashboardApi.ts:90-97`) is the query behind
`DashboardFilters.tsx:126`, where `config.source === 'data'` selects
`dynamicValues = filterValuesData?.values || []` as the **entire option list** of that filter's menu. The
value is a server-computed set of distinct column values. A client-wide enumeration of every
`invalidateQueries` call returns four sites — `dashboardApi.ts:84` (`['dashboards', id]`),
`dashboardApi.ts:86` (`['aggregatedData', dashboardId]`), `UserManagement.tsx:99,112,123`,
`RegistrationRequests.tsx:93,108` and `DashboardManagement.tsx:72,92,111` — and **none of them names
`['filterValues', …]`**. The one event that provably changes the answer is a completed upload, and
`DashboardView.tsx:215-220` reacts to exactly that event by invalidating `aggregatedData` and nothing else.
So after any upload that introduces a new value in a `source: 'data'` column, the charts render the new
value and the filter menu cannot select it, silently, for the life of the tab.

**Evidence** — `dashboardApi.ts:90-97` (the key and the absence of any invalidation), `DashboardFilters.tsx:126-127`
(the option list's only source), `DashboardView.tsx:215-220` (the upload completion handler), and the
exhaustive `invalidateQueries` enumeration above; all read at `d008f555`. The input's own inventory line
already names the key correctly and then declines to follow it.

**Consequence** — A cache-staleness class the phase declared absent is present, user-visible, and has no
error path: there is no toast, no inline message and no empty-state text, because from the client's point of
view the list is valid. It is not CRITICAL and cannot become one — choosing a filter value only narrows a
chart the server has already authorised for this user (`data.py:91`, `required_permission="view"`), and no
client-only authorization decision rests on it. It is MEDIUM: a server-derived value is served from cache
indefinitely, the user cannot reach data they can see, and the defect never self-heals because nothing in
the client ever issues the refetch.

**Recommendation** — Promote this to a phase-13 finding and correct Block 2's conclusion: the inventory was
built correctly and its last line was drawn in the wrong place. Add
`invalidateQueries({ queryKey: ['filterValues', dashboardId] })` alongside the existing
`invalidateAggregatedData` in `DashboardView.tsx:218`, or give `useFilterValues` a matching
`['filterValues', dashboardId]` prefix so one `invalidateQueries` call covers the filter surface with the
chart surface. Strike the *"and never needs to be"* clause. Do not renumber FE-001..FE-010; the new finding
takes a fresh `FE-` identifier from phase 13's namespace.

### VAL-13-004 — FE-001's headline counts one reload fewer than its own body and the limiter's comparison allows

**Severity** — LOW

**Zone** — "The Grade against the Audited Phase's Own Rubric"

**Observation** — FE-001's title reads *"A signed-in user is silently returned to the login page after five
page reloads"*, and its Observation reads *"Five hard reloads of `/dashboards` (2 refreshes each) or three of
`/admin` (3 each) exhaust the budget. The next boot refresh returns 429."* Those two sentences disagree, and
the limiter settles which is right. `AsyncRateLimiter.check_rate_limit` (`core/security.py:126-136`) reads
the counter first and refuses **only** when `int(attempts) >= max_attempts`, incrementing otherwise. With
`max_attempts=10` the first ten attempts are allowed and the **eleventh** is refused. On `/dashboards` that
is five reloads consuming attempts 1-10 and the **sixth** reload taking attempt 11; on `/admin` it is three
reloads consuming attempts 1-9 and the **fourth** taking attempt 10 and attempt 11.

**Evidence** — `core/security.py:126-136` (the `>=` compare ahead of the increment) against
`api/routes/auth.py:315` (`max_attempts=10, ttl=300`), and `useAuth.ts:14,66-69` for the two-and-three
instances per page. The mechanism, the per-instance guard, the budget numbers and the silence all reproduce
exactly as filed; only the threshold sentence is off by one.

**Consequence** — Drift with no remediation consequence: the finding's band (HIGH) and its recommendation are
unchanged by a one-reload difference, and a reader sizing the fix will not be misled about the mechanism.
It is recorded because the number appears in the title, which is the string a roadmap is built from, and
because an off-by-one in a threshold is exactly the class of claim a later phase re-derives from the title
instead of the body.

**Recommendation** — Restate the title as "after six hard reloads" and the Observation as "five reloads
exhaust the budget; the sixth is bounced". Leave every other sentence of FE-001 and every identifier
unchanged.

### VAL-13-005 — `VAL-001`…`VAL-009` each resolve to two different findings across the phase-01 and phase-02 validation reports

**Severity** — MEDIUM

**Zone** — "Finding-ID Namespace Integrity — The Ruling This Phase Owns"

**Observation** — A namespace enumeration over `.ai/audit/99-validation/*.md` returns 114 validation-level
identifiers across fourteen reports. Two of them use the **flat** `VAL-` form, and every one of those
identifiers is minted in both files:

| Identifier | phase-01 report | phase-02 report |
|---|---|---|
| `VAL-001` … `VAL-008` | 8 headings | 9 headings (`VAL-001` … `VAL-009`) |
| `VAL-009` | — | 1 heading |

`VAL-001` through `VAL-008` therefore each name **two distinct findings** in two distinct reports, and
`VAL-009` names one. Phases 03 through 14 each adopted a phase-qualified form (`VAL-03-001` …
`VAL-14-005`) and collide with nothing; phases 01 and 02 did not, and their two runs overlapped on the same
plain integers. This report follows the qualified form and mints `VAL-13-001`…`VAL-13-005` for that reason,
which is the deviation recorded by the phase-99 output contract.

**Evidence** — Heading enumeration `^### VAL-` over the fourteen files in `.ai/audit/99-validation/`, run at
`d008f555`; per-file counts 01 = 8, 02 = 9, and 8 identical identifier strings across the pair. The audited
phase's own prefix is unaffected: `FE-` is declared by `13-client-tier/findings.md` and minted nowhere else
in the set — an enumeration of `FE-` headings across all fourteen validation reports returns only this file's
references.

**Consequence** — An identifier resolving to more than one finding is a MEDIUM defect in the audit: a reader
who cites `VAL-004` from a merged roadmap gets two unrelated remediations and cannot tell which is meant,
and any later pass that tries to renumber one of the two has no way to disambiguate. Nothing downstream can
detect it, because each report is internally consistent. The consequence today is citation ambiguity, not a
lost remediation.

**Recommendation** — The ruling belongs to the set-wide namespace block, not to phase 13, and this run does
not repair it: `01-process-architecture-validated-findings.md` and `02-configuration-secrets-validated-findings.md`
are outside this run's write scope and were not edited. The coordinating validator should re-key one of the
two reports into its own qualified form in a single pass that updates every cross-reference to the affected
identifiers inside those two files, and should not renumber the qualified identifiers already minted by
phases 03-14. Do not renumber `VAL-13-001`…`VAL-13-005` or any `FE-` identifier.

### VAL-13-006 — The client half of PERF-001's remediation is assigned to phase 13 by phase 11's validator and was never filed; FE-002 is a different concern

**Severity** — MEDIUM

**Zone** — "Cross-Phase Conflict, Ownership and Merge"

**Observation** — The input records *"FE-002 ↔ PERF-001 (phase 11) — adjacency, do not merge"*, on the
reasoning that PERF-001 is the backend unbounded `select` and *"FE-002 is what the client does with the
resulting failure"*. Phase 11's validator reached the same neighbourhood from the other side and assigned the
remediation explicitly: `11-performance-validated-findings.md:121-128` records that *"the client half of this
fix belongs to phase 13"*, names `useAggregatedData` at the `DashboardView` call site, and warns that
*"landing only the server half is the silent-truncation case"*. That client half is real, small, and
**unfiled**. `useAggregatedData(dashboardId, filters?, graphId?)` already accepts `graphId` and already sends
`graph_id` in the request body (`dashboardApi.ts:62-78`), and `DashboardView.tsx:49` calls it with two
arguments, so the server-side bounded response would be requested graph-by-graph by a one-line change that
exists in the client's own API layer and was not taken up.

FE-002 does not cover it. FE-002 is about what the client does when the request **fails**: toast, inline
banner, retained frames. PERF-001's step 1 is about what the client does when the request **succeeds and
returns fewer rows** — no error, no toast, no banner, `aggregatedData.graphs.length > 0`, charts rendered as
normal. The adjacency label is therefore correct in kind (the concern is phase 13's, not phase 11's) and
wrong in instance: FE-002 is a sibling of the client half, not the client half.

**Evidence** — `dashboardApi.ts:62-78` (the third parameter and the `graph_id` it already serialises) against
`DashboardView.tsx:45-49` (two arguments supplied); `11-performance-validated-findings.md:90` (VAL-11-002,
band HIGH) and `:121-128` for the assignment and the silent-truncation warning; the input's own Cross-Finding
Analysis at `13-client-tier/findings.md:542-545`. Neither file was edited by this run.

**Consequence** — Phase 11's roadmap step 1 is unimplementable as written for the reason its own validator
gave, and the half that would make it implementable has no owner. A remediation team reading the two reports
finds a server `LIMIT` to add and a client file nobody has claimed; the natural reading is that the server
half is self-contained, which is the silent-truncation case VAL-11-002 warns about. This is an ownership gap
in the audit set, not a defect in either report's system findings, and it is MEDIUM because the reader can
repair it in one sentence once it is named.

**Recommendation** — File the client half as a new phase-13 finding: `DashboardView` must request
`/data/aggregated` per `graph_id` (or per graph) once the server bounds the response, and must render a
partial graph set with a stated bound rather than presenting a truncated response as complete. Keep FE-002 as
filed and keep its adjacency with PERF-001 — the two are distinct and both should survive. Phase 11 retains
ownership of PERF-001; **phase 13 owns the client half**; neither identifier is renumbered.

## Validated Findings — the audited phase's own identifiers

Every phase-13 identifier is preserved exactly as minted. This table is the audited namespace and carries no
`VAL-` row; the two tables never share a `Severity` column because they carry two different scales. Bands are
the audited phase's own, re-graded only against the audited phase's rubric, and no re-grade was applied.

| ID | Band carried | Band implied | Disposition | What reproduced it, or refuted it |
|---|---|---|---|---|
| FE-001 | HIGH | HIGH | confirmed | `useAuth.ts:14,66-69` is a per-instance `useRef`; `Header.tsx:21`, `ProtectedRoute.tsx:10`, `RoleBasedAccess.tsx:11` are three independent mounts on `/admin` and two elsewhere; `auth.py:315` is `max_attempts=10, ttl=300`; `axiosInstance.ts:62-64` returns the 429 with no toast and no redirect; `useAuth.ts:87-90` clears state silently; `ProtectedRoute.tsx:21-23` navigates to `/login`. Threshold in the **title** is off by one — see VAL-13-004. |
| FE-002 | HIGH | HIGH | confirmed | All three surfaces verified independently: `axiosInstance.ts:127-136` toasts every non-401/429 status; `DashboardView.tsx:181-185` renders the inline `Alert`; `DashboardView.tsx:187-199` maps `aggregatedData.graphs` with no guard against `dataError`. The behavioural claim was settled **in the installed library**, not assumed: `@tanstack/query-core@5.101.0` `query.js:375-388` returns `{...state, status:"error"}` on the `error` action, so `data` and `error` are simultaneously non-null; `queryObserver.js:308-310` derives `isLoading = isPending && isFetching`, so a refetch after a success shows no pending state. The query's own options were read: `providers.tsx:10-17` sets `retry: 1, staleTime: 300000` with no `placeholderData`, and `dashboardApi.ts:68-77` adds none. Toast text re-derived: a non-JSON 502 body falls through `errorHandler.ts:81-86` to `INTERNAL_ERROR`, and `errorMessages.ts:15` maps that to `Internal server error`. |
| FE-003 | MEDIUM | MEDIUM | confirmed | Transport enumeration over `frontend/src` returns exactly two sites — `axios.create` at `axiosInstance.ts:8` and `fetch('/api/v1/client-errors'` at `ErrorBoundary.tsx:40` — matching the input. The call bypasses the request interceptor and `withCredentials`, and its failure handler is `.catch(() => {})`. **Weakened:** Consequence (2) frames the missing credential as a loss, but `api/routes/client_errors.py:28` documents the endpoint as *"No authentication required"*, so the anonymity is the endpoint's declared contract rather than an accident. The finding and its remedy stand. |
| FE-004 | MEDIUM | MEDIUM | confirmed | Barrel-import enumeration returns exactly four hits, two production (`ProtectedRoute.tsx:3`, `RoleBasedAccess.tsx:1`) and two test, all `../../features/auth` — as filed. `axiosInstance.ts:3` imports three mutators from `features/auth/model/authToken`; `Header.tsx:4` imports `useAuth` by internal path while `ProtectedRoute.tsx:3` imports it from the barrel; `userApi.ts:3` republishes `../../auth/api/authApi`. `features/auth/index.ts` exports exactly `useAuth`, `login`, `registerRequest`, `getProfile`, `logoutClient` and none of the five the consumers need. |
| FE-005 | MEDIUM | MEDIUM | confirmed, and **upgraded from derivation to reproduction** | `env.ts:5` declares `['VITE_API_URL']`, `env.ts:15-17` returns early under `DEV`, `main.tsx:7` calls it before `createRoot`, `axiosInstance.ts:9` hard-codes `'/api/v1'`, `Dockerfile:22` runs `npm run build` with no `ARG`/`ENV`. The input listed this as unobserved because it declined to build. **No build was run here either — and none was needed.** The untracked `frontend/dist/` already on disk contains the compiled production bundle, and `assets/index-CP3NT1Oa.js` carries the literal `var $e=['VITE_API_URL']` with the lookup `({BASE_URL:'/',DEV:!1,MODE:'production',PROD:!0,SSR:!1})[t]` — an object with no `VITE_API_URL` key. A production bundle built without the variable **does** throw at module evaluation, exactly as claimed. The finding is confirmed against a shipped artefact rather than against Vite's documented substitution rules. |
| FE-006 | MEDIUM | MEDIUM | confirmed at three of four rows | `DashboardUpdate.description` `max_length=200` at `dashboard.py:140` against the client's `.max(500)` at `formSchemas.ts:40` — confirmed. `validate_password_or_raise` at `validators.py:196-203` against the client's `[A-Z]` at `:58` — confirmed. `auth_service.py:410` lower-casing the submitted domain against the client's case-sensitive `BLOCKED_DOMAINS.includes(domain)` at `formSchemas.ts:17` — confirmed, and the input's citation of `:65,432` misses the lower-casing of the **input**, which is at `:410`. The remediation blocker `formSchemas.test.ts:86-89` is confirmed: the test named *"rejects description longer than 500 characters"* exercises `createDashboardSchema`, whose bound is 200, so `'a'.repeat(501)` fails for the wrong reason and catches neither bound. **Refuted:** the `name`-on-create row and its `Q1 sales (EMEA)` example — see VAL-13-001. |
| FE-007 | MEDIUM | MEDIUM | confirmed | `api.types.ts:2` imports `Data` from `react-plotly.js` and `:207` declares `data: Data[]`; `models/data.py:434` declares `list[dict[str, int \| float \| str]]` and `:436` `dict[str, Any] \| None` against the client's five-key optional object at `:209-215`. Both double casts are present verbatim at `ChartRenderer.tsx:48,70`. The `Plotly.js format` docstring the input cites sits at `api/routes/data.py:73`. |
| FE-008 | MEDIUM | MEDIUM | confirmed as to mechanism, reachability and remedy; **asserted cause refuted** | The sniff is verbatim at `ChartRenderer.tsx:21-23`; row dictionaries keyed by operator-supplied column names are what `models/data.py:434` and the aggregation populate; `PlotlyComponent.tsx:34`'s `null` return and `DashboardView.tsx:190-197`'s unconditional frame are as filed. The claim that the traces are untyped and render an empty plot area is refuted by `plotly.min.js`, which declares `type` with `dflt:"scatter"` — see VAL-13-002. Phase ownership ruled below: **phase 13, not phase 16.** |
| FE-009 | LOW | LOW | confirmed | `Header.tsx:87-89` is an `IconButton` wrapping `<AccountCircle />` with no `aria-label`, no `aria-haspopup`, no `aria-expanded`, and `Header.tsx:97-104` is its sole route to Profile and Logout. `DashboardFilters.tsx:186-193` is a bare `<Typography variant="caption">{filter.name}</Typography>` with no `id`/`htmlFor` and a `Slider` with no `aria-label`. No focus management: `AppLayout.tsx:12-18` renders `TrailingSlashRedirect` and `Header` only, and `routes.tsx` mounts no focus effect. The band is correctly LOW — no path is blocked from keyboard users. |
| FE-010 | MEDIUM | MEDIUM | confirmed | The same four-hit barrel enumeration as FE-004 settles it: only `features/auth/index.ts` is imported anywhere, by two production files. The route-surface paragraph was checked independently and is accurate — `/register` from `LoginForm.tsx`, `/profile` and Logout from `Header.tsx:97-104`, `/profile/change-password` from `UserProfile.tsx`, `/dashboard/:id` from the `DataGrid` row handler, `/` by `RootRedirect`, `*` by `NotFound`. `git ls-files frontend/src` returns exactly 85 files, matching the input's denominator. |

**Disposition tally — confirmed 10, re-typed 0, re-graded 0, merged 0, not substantiated 0, unsettled 0.**
Two findings carry a refuted asserted cause and one carries an off-by-one in its headline; all three are
recorded as `VAL-13-` findings above rather than as dispositions against the finding, because in each case the
finding itself reproduces and only its explanation does not. No identifier was renumbered.

**Grades against the audited phase's own rubric.** `.kilo/commands/audit/phases/13-audit-client-tier.md`
assigns bands by user-visible effect, and every band the input carried is the band that rubric implies: the
two HIGHs are the only two findings whose effect is a signed-in user losing their session with no message and
a user being shown contradictory information about data currency; the six MEDIUMs are contract and
correctness gaps with a bounded blast radius; the single LOW is an accessibility-surface gap with no blocked
keyboard path, which the input itself reasons through in its Consequence rather than asserting. **No
re-grade is warranted and none was applied.** The empty CRITICAL band is upheld below, on re-derived
evidence rather than on inheritance.

## Distribution

All ten audited findings fall in the browser tier, exactly as the input states, and they re-concentrate where
the input says: `shared/api/axiosInstance.ts` carries the request path, the toast half of FE-002, FE-001's
429 exposure and FE-004's most consequential edge; `shared/types/api.types.ts` and `charts/ChartRenderer.tsx`
carry the declared/served chart gap and everything that follows from it. The single heaviest file is
`shared/types/formSchemas.ts` once the phase-09 and phase-13 observations are combined — it is the client's
entire input-validation surface, it diverges from the server's models, and one of its shipped tests asserts a
bound the schema does not have.

- `shared/api/` — the single request path, its interceptor, its duplicated base, the credential edges into a feature (4)
- `features/auth/model/` — the per-instance refresh guard and the private credential store (2)
- `features/dashboards/ui/` + `shared/components/PlotlyComponent.tsx` — the chart path and the shape gap (3)
- `shared/types/` — hand-written boundary types and the client's Zod rules (3)
- `shared/components/` — interactive semantics, focus, the error boundary's own transport (2)

The validation-level findings concentrate elsewhere: two in `models/dashboard.py` as the server's side of a
client-rule comparison (VAL-13-001), and three in the audit set's own bookkeeping — a library default read out
of `node_modules` (VAL-13-002), a cache key no `invalidateQueries` names (VAL-13-003), and the identifier
namespace itself (VAL-13-005, VAL-13-006).

## Cross-Finding Analysis

**The input's own blocks do not produce its substantive findings.** Asked whether any finding rests on the
declared block list, the answer is yes for four and no for six. FE-003, FE-004 and FE-010 each rest on an
explicit block (Request Path, Slice Boundaries, Reachability). FE-005, FE-006, FE-007 and FE-008 arrived from
an angle the declared blocks never name: **cross-checking the client against the server model layer**, field by
field and type by type. Nothing in the eleven declared blocks asks "does the server agree?" — and six of the
ten findings, plus the input's most useful artefact (FE-006's rule table), exist only because the run performed
that comparison anyway. The same holds for FE-002's decisive step: the claim that a failed refetch leaves
retained data is a question about the client's **configured** TanStack Query options, which no declared block
asks. A reader who treats the declared blocks as the coverage map will understate this phase by roughly half.
The input was honest about this — it put the server comparisons in an evidence column rather than a block —
but the block-to-finding mapping it publishes in its Distribution section does not reflect where the findings
came from.

**The vacuous-control angle, applied to this input's two claimed empty bands.** Both were tested on the merits
rather than accepted, and they resolve differently.

*The empty CRITICAL band is load-bearing, and the reasoning behind it survives re-derivation.* The rubric's
CRITICAL clause is narrow: a privilege claim the client trusts without the server confirming it, or a protected
surface whose only gate is in the client. Every candidate client-side gate in this tier has a server-side
counterpart, verified directly rather than inherited from phase 12: `canEdit` at `DashboardView.tsx:133` gates
only the visibility of the Upload button, and `upload.py:238-241` raises `PERMISSION_DENIED` independently;
`RoleBasedAccess` gates the `/admin` UI, and every admin route takes `admin_user: AdminUser` as a dependency
(`api/routes/admin.py:46`); `/data/aggregated` carries `required_permission="view"` (`api/routes/data.py:91`);
`ProtectedRoute` gates route rendering while every endpoint re-checks. So the conclusion holds — and it holds
for a **stronger** reason than the one the input gave. The input says Phase 12's AUTZ findings are the reason
no client-only gate exists here; that is a claim about a sibling report, and under this phase's rules such a
claim must be re-derived rather than inherited. Re-derived, the gates are present in the code and the
conclusion does not depend on phase 12's report at all. **The band is genuinely empty, and the vacuous-control
risk here is in the *justification*, not the verdict.**

*Block 2's empty band is not empty.* See VAL-13-003. The input built the inventory correctly, named
`['filterValues', dashboardId, filterName]` correctly, and then discharged it with the clause *"never
invalidated, and never needs to be"* — which is the finding, asserted away. The block's closing sentence, *"No
server-derived value is treated as authoritative on a refetch the client never issues"*, is a well-formed
sentence that happens to be false: `DashboardFilters.tsx:126-127` reads the distinct values of an
operator-named column out of a cache that no `invalidateQueries` in the client names, and renders them as the
complete option list, indefinitely, after the upload that changed them. This is the one place where the input's
evidence discipline worked against it — the inventory was strong enough to find the value and the conclusion
was not strong enough to keep it.

**Does FE-002 show that PERF-001's truncation is not silent? No, and the distinction decides phase 11's step 1.**
Asked directly: FE-002's mechanism engages only when the request **fails** — the toast at
`axiosInstance.ts:127-136` requires a non-2xx status, the banner at `DashboardView.tsx:181-185` requires
`dataError`. PERF-001's roadmap step 1 is a `LIMIT` that makes the request **succeed** with fewer rows. No
error, no toast, no banner, `aggregatedData.graphs.length > 0`, charts drawn as though complete. The truncation
is silent, phase 11's VAL-11-002 stands unchanged, and FE-002 does nothing to soften it. This is recorded as
VAL-13-006 because the input's adjacency label pointed phase 11's reader at FE-002 as though it covered the
client half, and the client half — threading `graph_id` through `useAggregatedData`, which already accepts it at
`dashboardApi.ts:62-78` — was never filed.

**Ownership ruling 1 — TST-015's remedy editing `formSchemas.ts` is not a double-file and drops nothing.** The
phase-09 validator flagged TST-015's recommendation as reaching into a production file phase 13 owns. Correct,
and correctly not a merge, because the two findings are about **different artefacts with different remedies**:
TST-015 owns a shipped red test (`formSchemas.test.ts:162`, `changePasswordSchema > accepts matching
passwords`, asserting `newpassword123` succeeds against a schema that requires an uppercase letter), and its
remedy is in the test file; FE-006 owns the client's rule set diverging from the server's, and its remedy is in
the production schema. The two are causally linked — landing FE-006's `new_password` fix turns that test green
— but neither subsumes the other, and the input was right to own the file rather than re-file. Checked for
overlap in the remediation blockers: TST-015 names `:162`, and phase 13's Roadmap Step 4 names `:86` — two
different tests, both named, no gap. Checked for double-filing of the substance: the `new_password` divergence
is named in both reports, but TST-015's validator explicitly framed its own finding as a test defect
("the client's rule is a strict superset") rather than re-arguing the rule set, so the audit states it once and
references it once. **Nothing was double-filed; nothing was dropped.** One correction applies inside phase 13:
FE-006's own name-on-create row is refuted (VAL-13-001), so the input's claim that "FE-006 is the substance
behind that remedy" holds for three of FE-006's four rows and not the fourth.

**Ownership ruling 2 — FE-008 belongs to phase 13, not phase 16, and phase 16 should be told what it inherits.**
Phase 16's declared subject is the chart **presentation contract**. FE-008's root cause is not a presentation
decision: it is the FE-007 declared/served shape gap, and its remedy is deleting three lines from
`convertToPlotlyData` — the same function whose second cast FE-007 deletes. Routing it to phase 16 would put
two owners on one function in one commit and neither would finish it. **FE-008 stays in phase 13.** What phase
16 should carry forward is the consequence, not the fix: once the sniff is gone, `convertToPlotlyData` becomes
the single, untyped adaptation point through which every server row becomes a trace, and it currently defaults
`xCol` to `'x'` and `metricCols` to `['y']` when `config` is absent (`ChartRenderer.tsx:15,17`) — presentation
defaults living in the adaptation layer. That is phase 16's material and is not pre-empted by keeping FE-008
where it is filed.

**Adjacencies accepted as filed.** FE-001 ↔ phase 04's refresh-cookie finding: accepted, distinct files,
neither true without the other. FE-005 ↔ OPS-003: accepted as an adjacency rather than the merge the input
proposed — OPS-003 owns which artefact is served, FE-005 owns a declaration with no consumer, and the input's
own Step 5 already sequences them together, which is what an adjacency is for. FE-002 ↔ AUTZ-001/003: the
input recommends merging only the "403 has two surfaces" observation into phase 12 and keeping FE-002 whole;
that is sound, and phase 12's report is already validated and was not edited.

## Roadmap

This is the validation's execution ruling, not a redesign. It orders what has to be true before what, and
records where the input's own ordering is unsafe. Phase-13's seven steps survive with three corrections.

**Correction to Step 4 before it is executed.** The input's Step 4 instructs the team to *"drop or serverise
the uppercase and name-character rules"*. The name-character rule is enforced server-side at
`models/dashboard.py:65`, and dropping it client-side inverts the divergence rather than closing it (VAL-13-001).
Step 4 must be narrowed to the two rules that genuinely diverge plus the `BLOCKED_DOMAINS` copy, with the
server's rule named as the owner in each case. Nothing else about Step 4 changes, including its remediation
blocker on `formSchemas.test.ts:86`.

**Correction to Step 0's verification.** Step 0 says *"confirm the intended chart appears"*. After
VAL-13-002, a chart *does* appear in the broken case — a one-point scatter. The verification must be *"confirm
the trace count and the axis categories match `config.metrics`"*, or the step ships with its own defect intact.

**Insertion between Steps 0 and 1 — the filter-value cache (VAL-13-003).** One `invalidateQueries` call with a
`['filterValues', dashboardId]` prefix in `DashboardView.tsx:218`. It is independent of everything in the
input's roadmap and can land at any point; it is placed here only because it is one line in a file Step 1
already touches.

**Ordering otherwise upheld.** Steps 1-2 must precede Step 3 for the reason the input gives (Step 3's import
repointing touches the module Step 2 rewrites), and Step 7 follows Step 3 for the same reason. Step 0 remains
first: nothing in the client can be judged correct while the served chart shape is misdeclared, and Steps 0 and
6 are the only two that need nothing else first.

**Ownership of the roadmap's largest step is unresolved and is not phase 13's to resolve.** Phase 11's step 1
needs the client change described in VAL-13-006, which is filed under phase 13 but appears nowhere in the input's
roadmap. It must be sequenced **with** phase 11's server `LIMIT`, not after it.

## Rollout Safety

The input's Rollout Safety section is carried forward unchanged; every claim in it was checked and holds.
Step 1 is correctly identified as the one to stage, and its warning is the sharpest thing in the input —
`DashboardView.tsx:127` and `DashboardList.tsx:24` render fixed strings today
(`"Failed to load dashboard. Please try again."`), so *"if the toast is the one removed, the user's message
gets worse unless those switch to `extractApiError` in the same change — do both or neither."* Verified:
`DashboardView.tsx:127-129` is a literal string, and the toast path it would replace is
`errorHandler.ts:132-135` carrying the real message. The instruction is correct and load-bearing.

Two additions to what was filed:

- **Step 0's revert is not clean.** Deleting the `'x' in … && 'y' in …` sniff is correct for the served shape,
  and it is the only step that can turn a working chart into a wrong one if the conversion path is wrong in a
  way the deleted branch was accidentally compensating for. The input names this risk but scopes it to
  "render one such dashboard"; after VAL-13-002 the check has to distinguish a **correct** render from a
  **plausible** one, which is the trace-count check above, not an eyeball.
- **Step 4 acquires a new risk from nothing in the input.** Because the input told the team the server has no
  name-character rule, executing Step 4 literally makes a previously-impossible 422 reachable
  (VAL-13-001). No rollback note covers this because the input does not know the hazard exists. Correct the
  step before it ships rather than after.

## Appendices

**A. The tree-cleanliness claim, adjudicated.** The input states it ran no live requests, touched no stack,
ran no `npm run build` / `npm run test` / `npm run lint` / coverage, and that `git status --porcelain --
frontend/` is byte-identical to its baseline, including that the 15 tracked `frontend/coverage/` deletions were
already present at its baseline. **Every part of that claim is substantiated, and the true state is worse than
"already present".**

Current state at `d008f555`: `frontend/coverage/` **does not exist on disk at all**. `git ls-files
frontend/coverage` returns the same 15 files, all 15 appear as unstaged deletions in `git status`, and there is
no untracked replacement and no partially rewritten file. That is the signature of the v8 coverage reporter's
clean-output-directory step having run with the report never being written — the same state phase 09's validator
recorded for a **red** full run. Phase 09's validator restored the directory with `git checkout -- frontend/
coverage` after each of its two runs and its report says so; its baseline, and phase 08's validator, both record
the tree clean of these deletions at `b23a9cb`. The deletions are therefore **not** phase 09's residue.

The input's baseline is `f107d59` (22:04:13). The deletions are recorded independently at two earlier or
contemporaneous baselines by other runs: `14-schema-migrations-validated-findings.md:16` lists
`D frontend/coverage/**` in its baseline-dirty at `0717b65` (21:40:45), and
`15-security-baseline/findings.md:7` lists `deleted … frontend/coverage/*` at the same `f107d59`. **The input's
claim that the deletions pre-date its baseline is confirmed by two independent records, not by its own
assertion.** Naming the run that caused them is **unsettled**: the window between 16:34 (phase 09's validator
restored the directory) and 21:40 (phase 14's baseline already showed the deletions) contains phases 10, 11, 12
and 14 and the concurrent remediation team, and no report in that window records a frontend gate invocation. A
host `frontend/dist/` also exists, untracked and fully written, which is a separate host-side `npm run build`
artefact from the same window; nothing in the set records who produced it either. **The tree was not modified,
staged, committed, reverted or stashed by this validation, and it was not repaired** — repairing it would
destroy the evidence the remediation team needs.

**B. What was re-derived from the executing path, per audited finding.** Ten findings, each traced through the
code that would run, with every line anchor resolved before the claim was tested: FE-001 through
`useAuth.ts`/`Header.tsx`/`ProtectedRoute.tsx`/`RoleBasedAccess.tsx`/`auth.py`/`core/security.py`; FE-002
through `axiosInstance.ts`/`DashboardView.tsx`/`LogViewer.tsx`/`DashboardList.tsx`/`errorHandler.ts`/
`errorMessages.ts` and `@tanstack/query-core@5.101.0` in `node_modules`; FE-003 through a full transport
enumeration; FE-004 and FE-010 through a full barrel-import enumeration plus the seven barrel files; FE-005
through `env.ts`/`main.tsx`/`vite.config.ts`/`Dockerfile` and the compiled bundle in `frontend/dist`; FE-006
field-by-field against `models/dashboard.py`, `utils/validators.py`, `services/auth_service.py` and
`settings/app.yaml`; FE-007 and FE-008 through `api.types.ts`, `ChartRenderer.tsx`, `PlotlyComponent.tsx`,
`models/data.py`, `api/routes/data.py` and `plotly.min.js`; FE-009 through `Header.tsx`,
`DashboardFilters.tsx`, `routes.tsx` and `AppLayout.tsx`.

**C. Claims left unsettled, with the reason.** (1) **The exact artefact FE-008 renders** — a one-point scatter,
a scatter with the scalar `x`/`y` broadcast, or something else. `plotly.min.js` settles the `type` question
(`dflt:"scatter"`) and refutes the input's stated cause, but the pixel-level outcome needs a browser and a
seeded `x`/`y` column pair; neither the input nor this run rendered it. No verdict rests on it — the finding's
band survives on the silent-wrong-render characteristic, which both outcomes share. (2) **The run that deleted
`frontend/coverage/`** — bounded to the 16:34-21:40 window and unattributable from the artefacts; see
Appendix A. (3) **Who produced the host `frontend/dist/`** — same window, same reason. (4) **FE-001's
exhaustion over the wire** — the limiter's own behaviour was read from `core/security.py:126-136` and the
threshold arithmetic derived from it, but exhausting a live Redis quota other phases depend on was not done and
is not proposed. (5) **FE-006's server-side refusals over the wire** — read from the Pydantic models, which are
authoritative, and not probed. Nothing in this report is recorded as confirmed on the strength of an unsettled
item.

**D. Coverage ledger — blocks executed and the item count each reached.** Phase 13 declares eleven blocks,
numbered here as `.kilo/commands/audit/phases/13-audit-client-tier.md` numbers them, with the block's own title
quoted so the mapping is checkable rather than inferred.

| Block (declared title) | Items actually reached | What it produced |
|---|---|---|
| 1. Slice Boundaries: What Crosses from Shared Code into a Feature, and Back | 7 import edges across all 85 tracked files in `frontend/src` (`git ls-files frontend/src` = 85) | FE-004 |
| 2. Server-Derived Values: Which Component Owns Each One, and What Retires It | 7 cache keys, every `invalidateQueries` site in the client, and every read of a query result at a render site | **VAL-13-003 — the input reached 0** |
| 3. The Request Path: One Path or Several, and What Each Refusal Leaves Behind | 1 transport funnel, 1 bypass; a full `axios.create\|axios(\|fetch(\|XMLHttpRequest\|EventSource` enumeration over `src/` | FE-003 |
| 4. Session Continuity: What the Client Believes after a Full Page Load | 6 `useAuth()` call sites, 3 mounted simultaneously on `/admin` and 2 on every other protected route | FE-001 |
| 5. The Client's Declared Build-Time Contract against What the Shipped Bundle Resolves | 1 declared build-time variable, 3 `import.meta.env` reads, 0 consumers, plus the compiled bundle already in `frontend/dist` | FE-005 |
| 6. Failure Surfacing: What the User Is Shown, per Class, and Where One Class Is Shown Twice | 4 API-reading surfaces plus the interceptor; 3 defective, 1 correct | FE-002 |
| 7. Absent, Partial and Malformed Server Data | 7 rendering surfaces enumerated; 1 renders silently wrong, 1 renders an unnamed empty frame | FE-008 |
| 8. Form Rules: What the Client Enforces against What the Server Enforces | 8 client fields compared against 8 server rules; 3 diverge, 4 match, 1 claimed-divergent that does not | FE-006 |
| 9. Interactive Surface Semantics: What an Assistive Technology Is Told | 8 interactive surfaces and the route-change focus path | FE-009 |
| 10. Type Width at the Client Boundary: What Crosses as Unverified | 1 response family examined in detail at the chart boundary; the declared/served gap located and the double cast found | FE-007 |
| 11. Reachability of the Client's Own Declared Surfaces | 7 declared entry modules (2 reached, 5 reached by nothing) and 9 routes (all 9 reached) | FE-010 |

**E. This report as an artefact.** Six validation findings, each carrying an identifier, a verdict and its own
re-derivation. The disposition tally — confirmed 10, re-typed 0, re-graded 0, merged 0, not substantiated 0,
unsettled 0 — agrees with the ten per-finding verdicts above. Phase-13 identifiers are preserved exactly as
minted and none was renumbered. The audited namespace and the validation namespace are in two sections that
never share a `Severity` column. `baseline` and `baseline-dirty` are recorded in the front matter against the
commit actually examined. Namespace deviation recorded: this report mints `VAL-13-` rather than the flat `VAL-`
the phase-99 output contract names, because the flat namespace is already occupied by two reports that collide
with each other (VAL-13-005); no other file in `.ai/audit/99-validation/` was created, edited, or removed.