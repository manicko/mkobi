---
phase: 13-client-tier
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 10
by-severity:
  CRITICAL: 0
  HIGH: 2
  MEDIUM: 6
  LOW: 2
baseline: f107d59aece4316861b91f184eea1d2b6b2373f2
baseline-dirty: true
---

# Phase 13 — Findings

## Summary

The browser-resident tier was examined across all eleven blocks of this phase: its module layering,
the server-derived values it holds and what retires them, its single request path and the one that
bypasses it, the session state a production build survives, its build-time declarations, the failure
classes it surfaces and where, how absent and malformed server data render, its Zod rules against
the server's Pydantic rules, the semantics of the surfaces it composes, the type width of every
response boundary, and the reachability of every route and entry module. The whole surface was
reached statically — all 85 tracked files, every import edge, every route, every barrel — and no
live requests were issued, so no Docker stack was started or disturbed and the dev/prod build was
deliberately not run. Ten findings, concentrated in two files: `shared/api/axiosInstance.ts` and
`shared/types/api.types.ts` + `ChartRenderer.tsx`. The single most consequential is FE-002: because
no layer owns "an API call failed", one `/data/aggregated` failure surfaces three times over — a
toast from the interceptor, an inline banner, and the previous query's charts still drawn — which is
precisely what a user sees at the 30.9 MB / 101 s response size Phase 11 measured for PERF-001. FE-001
is next: in a production build the access token is memory-only, so every hard page reload runs a
silent `/auth/refresh` once per mounted `useAuth()` instance — three of them on `/admin` — against a
server budget of ten per five minutes, after which the client discards a valid session and returns
the user to the login form with no message at all. Two HIGH, six MEDIUM, two LOW; no CRITICAL, because
every gate that protects an effect is enforced server-side — Phase 12's AUTZ findings are the reason,
not a defence found here.

## Findings

### FE-001 — A signed-in user is silently returned to the login page after five page reloads, with no message

**Severity** — HIGH

**Zone** — "Session Continuity: What the Client Believes after a Full Page Load"

**Observation** — In a production build the access token lives only in a module-level variable
(`authToken.ts:74`, `USE_MEMORY_STORAGE = import.meta.env.PROD`), so every hard load starts with no
token and `useAuth`'s boot effect falls through to `apiRefreshToken()` — `POST /auth/refresh`,
authenticated by the `mkobi_refresh_token` HttpOnly cookie that `/auth/login` sets
(`api/routes/auth.py:115-123`). That boot effect is guarded by a `useRef`
(`useAuth.ts:14`, `useAuth.ts:66-69`), so the guard is **per hook instance**, not per page.
`useAuth()` is instantiated independently by `Header` (`Layout/Header.tsx:21`) and by
`ProtectedRoute` (`ProtectedRoute.tsx:10`) on every protected route, and by a third instance,
`RoleBasedAccess` (`RoleBasedAccess.tsx:11`), on `/admin`. Each instance runs its own boot effect and
issues its own `POST /auth/refresh`. `/auth/refresh` is bounded to **10 attempts per client IP per
300 s** (`api/routes/auth.py:315`). Five hard reloads of `/dashboards` (2 refreshes each) or three
of `/admin` (3 each) exhaust the budget. The next boot refresh returns 429; `useAuth.ts:87-90` maps
`RATE_LIMIT_EXCEEDED` to `removeToken(); setUser(null)` with no user-visible branch, and the axios
response interceptor deliberately returns the 429 without a toast or a redirect
(`axiosInstance.ts:62-64`). `ProtectedRoute` then sees `accessToken === null` and issues
`<Navigate to="/login" replace />` (`ProtectedRoute.tsx:21-23`).

**Evidence** — Static, complete: `useAuth.ts:64-101` (per-instance `hasAttemptedRefresh` ref, the
`!token` branch that calls `apiRefreshToken()`, the 429 branch that clears state silently);
`Header.tsx:21` + `ProtectedRoute.tsx:10` + `RoleBasedAccess.tsx:11` (three independent instances
per page, confirmed by a full `useAuth()` call-site enumeration across `src/` — the only other
call sites are `RootRedirect`, `LoginForm`, `RegisterForm`, `UserProfile`);
`api/routes/auth.py:315` (`max_attempts=10, ttl=300`); `axiosInstance.ts:62-64` (429 bypasses both
toast and redirect). Client-side route changes do not remount `Header`, so the cost is per hard
reload only. Not reproduced over the wire: the rate limiter's own side is owned by phase 15, so the
reproduction was settled statically rather than by exhausting a shared Redis quota.

**Consequence** — Every hard reload costs the user 2-3 of a 10-per-5-minutes budget. On the fifth
reload of `/dashboards` inside five minutes the client discards a still-valid 7-day refresh cookie's
session and returns the user to `/login`, showing the plain login form with no toast, no inline
error and no explanation of why they were signed out. Nothing is logged on the client; the only
server-side trace is `Refresh rate limit exceeded` (`auth.py:317`), which is indistinguishable from
a real attacker's traffic. Per Phase 04's AUTH finding, `/auth/refresh` emits no `Set-Cookie`, so
the boot refresh also never rotates the credential it just consumed.

**Recommendation** — Hoist the boot decision out of the hook: run the silent refresh once per page
(load, e.g., in `app/providers.tsx` or a module-level promise in `authToken.ts`) and have
`useAuth` consume the resulting session instead of re-issuing it. The smallest change that removes
the effect without a restructure is a module-level `bootPromise` in `useAuth.ts` guarded by a
module-scope flag rather than a `useRef`, so all instances await one refresh. Separately, give the
429 branch a user-visible outcome (an inline "Session could not be restored, please sign in again"
on `/login`) — currently it is the one failure class in the client with no message branch at all.
`RoleBasedAccess` should read the shared `user` rather than instantiate a third copy.

### FE-002 — One failed chart-data fetch produces a toast, an inline error banner, and the previous charts, all at once

**Severity** — HIGH

**Zone** — "Failure Surfacing: What the User Is Shown, per Class, and Where One Class Is Shown Twice"

**Observation** — For any non-401, non-429 status the response interceptor fires
`toast.error(...)` with the RFC 7807 code's localized message (`axiosInstance.ts:127-136`). TanStack
Query retains the last successful `data` when a refetch fails, so `DashboardView` receives both a
populated `aggregatedData` and a non-null `dataError`. It renders the inline
`<Alert severity="error">Failed to load chart data.</Alert>` (`DashboardView.tsx:181-185`) **and**
maps `aggregatedData.graphs` into a full set of `<Paper>` chart frames
(`DashboardView.tsx:187-199`) in the same render pass, because the two conditions are independent
and neither excludes the other. The same shape holds on `DashboardList.tsx:22-28` for
`/dashboards/my`, and on `DashboardView.tsx:125-131` for the dashboard header fetch. The same shape holds on
`LogViewer.tsx:127-142` for `/admin/logs/`, where `isError` renders an inline `Alert` while `rows`
is derived from the retained `logs` and is handed to the `DataGrid` in the same render.
Because `DashboardView` reads `isLoading` rather than `isFetching`, no pending state is shown at
all once a first successful paint exists. `DashboardList.tsx:22-28` is the one surface that gets
this right — its `if (error) return` replaces the grid rather than rendering beside it — which is
what establishes the pattern as available rather than forced.

**Evidence** — Static, complete: `axiosInstance.ts:127-136` (unconditional toast for the class);
`DashboardView.tsx:177-206` (skeleton gated on `dataLoading`, error Alert gated on `dataError`,
graph list gated only on `aggregatedData?.graphs.length > 0` — no guard ties the three together);
`LogViewer.tsx:50,64-71,127-142` (identical structure); `DashboardList.tsx:14-28` (the correct
variant). The retained-data behaviour is React Query v5's
documented semantics for `useQuery` on a failed refetch. Cross-referenced to Phase 11's PERF-001
measurement (375,000 rows / 101.25 s / 30.9 MB / backend OOM at 101.2 % of a 1 GiB limit): at that
size the client sees a proxy 502/504 or a reset connection, so every occurrence of this class
presents to the user as a toast reading `Internal server error: Request failed with status code
502` beside a chart frame still showing the previous query's plots, with no spinner.

**Consequence** — For the single most common failure on this system's main surface the user is
shown two contradictory notices at once and is left looking at numbers the server has already
replaced or withdrawn. There is no way to tell from the screen whether the charts are current. At
PERF-001's measured response size the user sees the error for a request that never legitimately
completed, and on the loads where the 30.9 MB body does arrive, the surface renders every row of
every graph into Plotly in one synchronous pass on the main thread.

**Recommendation** — Make the three states mutually exclusive at the surface: when `dataError` is
set, render the error and nothing else (`return` before the graph map), or use
`placeholderData`/`keepPreviousData` semantics deliberately and mark the stale frame as such. Drop
`isLoading` in favour of `isFetching` for the skeleton so a refetch shows pending state. Then, to
remove the duplicate notification, either drop the interceptor toast for codes a surface renders
inline, or stop rendering the inline Alert and keep only the toast — one surface per class. Which of
the two to keep is a judgement call for the owning team; the defect is the duplication, not either
half. If the inline form wins, `DashboardView.tsx:127` and `DashboardList.tsx:24` should surface the
`extractApiError` message rather than a fixed string, so PERF-001's 502 is not reported as the same
text as a 403.

### FE-003 — A second, undeclared copy of the API base location is hard-coded into an error-reporting `fetch` that bypasses the shared client

**Severity** — MEDIUM

**Zone** — "The Request Path: One Path or Several, and What Each Refusal Leaves Behind"

**Observation** — The client's single request path is `axiosInstance`
(`baseURL: '/api/v1'`, `withCredentials: true`, `axiosInstance.ts:8-15`); a full
`axios.create`/`axios(`/`fetch(`/`XMLHttpRequest` enumeration across `src/` confirms every API call
funnels through it **except one**. `ErrorBoundary.reportError` issues a raw
`fetch('/api/v1/client-errors', …)` (`ErrorBoundary.tsx:40-44`), restating the base location as a
literal string. That call carries no `Authorization` header (it goes through neither the request
interceptor's token attachment nor `withCredentials`), and its failure handler is
`.catch(() => {})` — no log, no retry, no surface.

**Evidence** — `axiosInstance.ts:8-15` (the declared base) vs `ErrorBoundary.tsx:40-44` (the
second declaration); enumeration of `axios\.create|axios\(|\bfetch\(|new XMLHttpRequest|EventSource`
across `frontend/src` returns exactly these two sites. `ErrorBoundary.tsx:25-29` restricts
reporting to non-DEV builds, so in development the failure is a bare `console.error`.

**Consequence** — Three concrete losses today. (1) Renaming or re-mounting the API under a
different prefix fixes `axiosInstance` and silently breaks client-error reporting, because nothing
ties the two strings together. (2) Client-error reports carry no credential, so the backend's
`/client-errors` handler sees anonymous posts — a client stack trace cannot be attributed to a user
even when the caller is authenticated. (3) This is the one path that cannot use the client-error
channel for its own failure, which matters because the failure it reports is the one that occurs
before anything else exists (see FE-005).

**Recommendation** — Route the report through `axiosInstance` (or a tiny
`shared/api/clientErrorReporter` that uses it) and read the base from the single declared source
rather than restating `/api/v1`. Add `await`-style error logging in the catch so a failed report is
visible in the console. This is a small, self-contained change with no behavioural risk to existing
surfaces; the only observable difference is that `/client-errors` now receives the bearer token.

### FE-004 — The credential store is a feature's private module, reached into by shared plumbing and by two other features

**Severity** — MEDIUM

**Zone** — "Slice Boundaries: What Crosses from Shared Code into a Feature, and Back"

**Observation** — Feature-Sliced Design declares that `features/<slice>/index.ts` is the surface
other slices may import. Across all 85 tracked frontend source files, exactly **two** non-test files
honour that rule (`ProtectedRoute.tsx:3` and `RoleBasedAccess.tsx:1`, both importing `useAuth` from
`../../features/auth`). Everything else that crosses a slice boundary names an internal path. The
import edges, by kind:

| Edge | Site | Permitted direction |
|---|---|---|
| shared → **auth internals** | `shared/api/axiosInstance.ts:3` → `features/auth/model/authToken` (`getTokenWithExpirationCheck`, `removeToken`, `setToken`) | **out of permitted** — shared plumbing reads and writes a feature's credential state |
| shared → **auth internals** | `shared/components/Layout/Header.tsx:4` → `features/auth/model/useAuth` | **out of permitted** — same layer, same slice, two different entry points (cf. `ProtectedRoute.tsx:3`) |
| dashboards → **auth internals** | `features/dashboards/api/dashboardApi.ts:3` → `features/auth/model/authToken` (`useAuthToken`) | **out of permitted** — a feature reaching another feature's internals |
| users → **auth internals** | `features/users/api/userApi.ts:3` re-exports `getProfile` from `../../auth/api/authApi` | **out of permitted** — one feature republishing another's internal through its own API module |
| dashboards → upload UI | `features/dashboards/ui/DashboardView.tsx:20` → `../../upload/ui/UploadModal` (lazy) | in-permitted in direction, but past the published surface |
| feature → shared types/utils | every `*.tsx` → `shared/types/api.types`, `shared/utils/*` | in-permitted |

None of the seven barrels (`features/{auth,dashboards,upload,users}/index.ts`,
`shared/{api,components,hooks}/index.ts`) is imported by anything except
`features/auth/index.ts`, which is reached only by the two lines above. In particular
`features/auth/index.ts` publishes `useAuth`, `login`, `registerRequest`, `getProfile` and
`logoutClient` but **not** `useAuthToken`, `getTokenWithExpirationCheck`, `setToken`, `removeToken`
or `logout` — so the three consumers that need them have no permitted route to the published
surface at all.

**Evidence** — Full enumeration: a grep for
`from '(\.\./)*(shared/api|shared/components|shared/hooks|features/(auth|dashboards|upload|users|admin))'`
across `frontend/src` returns four hits, all `../../features/auth`, two of them in test files. Barrel
contents read directly (`frontend/src/features/*/index.ts`, `frontend/src/shared/{api,components,hooks}/index.ts`).

**Consequence** — What this lets one slice do to another today: `shared/api/axiosInstance.ts` is
the module that decides *whether a request carries a credential at all*
(`axiosInstance.ts:18-30`). It obtains that capability by importing three mutator functions out of
a feature's `model/` directory, so the shared layer's compile-time dependency points at feature
internals, and any move or rename inside `features/auth/model/` breaks the shared HTTP client at
import time rather than at a slice boundary. `useAuth`'s own state is not reachable through the
surface either: `Header.tsx` and `ProtectedRoute.tsx` reach it by two different paths within one
layer, which is why FE-001's duplicated boot effect has no single place to be fixed.

**Recommendation** — Publish what is actually consumed. Add `useAuthToken`,
`getTokenWithExpirationCheck`, `setToken` and `removeToken` to `features/auth/index.ts` and point
`axiosInstance.ts`, `Header.tsx` and `dashboardApi.ts` at the surface; add `logout` to the same
barrel. The one-way alternative — demote `authToken.ts` out of `features/` into
`shared/auth/` — is defensible because it is storage, not feature logic, and is the smaller change
if the team does not want a feature to publish its private token store. Either way one route per
consumer, not two. No behaviour changes; this is a move-and-re-export refactor. Note for whoever
takes it: `shared/api/refreshHandler.ts` already documents the "shared never imports feature modules"
rule it was written to satisfy, and the same rule is currently broken by its sibling.

### FE-005 — The build declares `VITE_API_URL` mandatory in production; nothing reads it, and the one place that would consume it is skipped in development

**Severity** — MEDIUM

**Zone** — "The Client's Declared Build-Time Contract against What the Shipped Bundle Resolves"

**Observation** — `shared/config/env.ts` declares exactly one build-time requirement,
`REQUIRED_ENV_VARS = ['VITE_API_URL']` (`env.ts:5`), enforced by `validateEnv()` (`env.ts:13-29`),
which `main.tsx:7` calls before `ReactDOM.createRoot`. The declared value has **no consumer**: the
request path's base is the literal `'/api/v1'` at `axiosInstance.ts:9`, and a full
`import.meta.env` enumeration across `src/` returns only `env.ts` itself, `authToken.ts:74`
(`import.meta.env.PROD`) and `providers.tsx:48` (`import.meta.env.DEV`). No `.env*` file exists in
`frontend/` (verified by directory listing), and `docker/Dockerfile:22` runs `npm run build`
without an `ARG`/`ENV` for it. So the declaration names a value that the bundle would run identically
without. The reverse shape is also present: `env.ts:15-17` returns early whenever
`import.meta.env.DEV` is true, so the declaration is enforced in exactly one of the two build
variants — the variant that does not use the value — and skipped in the variant that does (the dev
server, which resolves `/api` through the Vite proxy at `vite.config.ts:9-14`). Both variants are
produced by declared npm scripts.

**Evidence** — `env.ts:5,13-29`; `main.tsx:7`; `axiosInstance.ts:9`;
`docker/Dockerfile:12-22` (no `VITE_API_URL` at any build step); directory listing of `frontend/`
showing `.gitignore`, `eslint.config.js`, `index.html`, `package*.json`, `README.md`,
`tsconfig*.json`, `vite.config.ts` and no `.env*`. Vite's documented behaviour is that `vite build`
sets `import.meta.env.PROD = true` / `DEV = false`, so the `DEV` early-return at `env.ts:15` is not
taken in a production bundle and `import.meta.env.VITE_API_URL` is `undefined`, making
`validateEnv()` throw at module evaluation — before `ReactDOM.createRoot` runs and therefore before
any error boundary exists, so `ErrorBoundary.reportError` (FE-003) cannot fire for it and the
client-error channel never receives it. `npm run build` was **not** executed to confirm the browser
side of this: it writes `frontend/dist`, which Phase 10's OPS-003 identifies as the untracked,
unignored host directory nginx serves, and the dev stack may be in use by peers.

**Consequence** — Two live effects. (1) The declaration is a tripwire with nothing behind it: a
production bundle built without `VITE_API_URL` throws at module evaluation and renders a blank page
with no console-free explanation, no error boundary and no client-error report, while a bundle
built *with* it behaves identically. Whatever produces the production bundle today either sets the
variable (in which case the throw never fires and the declaration is pure ceremony) or does not
(whichever image or host build is in use, the SPA renders nothing). (2) `validateEnv()` is dead
weight in development, so a contributor who runs `npm run dev` cannot observe the check that guards
the production build.

**Recommendation** — Decide which of the two shapes is true and make the code say so. If the API
base is meant to be same-origin behind the edge proxy (which `axiosInstance.ts:9` and
`vite.config.ts:9-14` both assume), delete `REQUIRED_ENV_VARS` and `validateEnv()` outright and drop
the `main.tsx:7` call — a declaration nothing consumes is worse than none, because it reads as a
guarantee. If a configurable base is genuinely wanted, make it one: read
`import.meta.env.VITE_API_URL ?? '/api/v1'` at `axiosInstance.ts:9`, keep the check, and set the
value in `docker/Dockerfile` and the dev compose so both variants are exercised. Whichever is
chosen, this phase makes no claim about which artifact nginx currently serves — that is OPS-003's
finding and it should be read alongside this one.

### FE-006 — The client's password and dashboard-name rules are stricter than the server's in three places and weaker in one

**Severity** — MEDIUM

**Zone** — "Form Rules: What the Client Enforces against What the Server Enforces"

**Observation** — Every client rule set lives in `shared/types/formSchemas.ts` and is consumed by
exactly one form each (`DashboardManagement.tsx:50,60`, `LoginForm.tsx:21`, `RegisterForm.tsx:20`,
`ChangePasswordPage.tsx:22`). Field by field against the server's models:

| Field | Client (`formSchemas.ts`) | Server | Verdict |
|---|---|---|---|
| `description` on dashboard **update** | `.max(500)` (`:40`) | `DashboardUpdate.description` `Field(None, max_length=200)` (`models/dashboard.py:140`) | **diverges** — client accepts, server refuses |
| `description` on dashboard **create** | `.max(200)` (`:31`) | `DashboardCreate.description` `Field(None, max_length=200)` (`:54`) | matches |
| `name` on dashboard create | `.min(3).max(100).regex(/^[a-zA-Z0-9\s-]+$/)` (`:25-30`) | `DashboardCreate.validate_name` — length 3..100 only, no character rule (`models/dashboard.py:58-64`) | **diverges** — client refuses, server accepts |
| `new_password` | `.min(8).regex(/[A-Z]/).regex(/[0-9]/)` (`:56-59`) | `validate_password_or_raise` — length >= 8, **one digit**, **one letter of any case** (`utils/validators.py:193-203`) | **diverges** — client refuses, server accepts |
| register `email` domain | hard-coded `['tempmail.com','throwaway.email']`, compared **case-sensitively** (`:3,15-18`) | `config.email.blocked_domains` via `settings/app.yaml:94-96`, lower-cased on both sides (`auth_service.py:65,432`) | **diverges** — an operator-added domain is not enforced client-side; `User@TempMail.com` passes the client and is refused by the server |
| `user_id` on grant access | `z.uuid()` (`:47`) | `UUID` query/path param | matches |
| `permission` on grant access | `z.enum(['view','edit','admin'])` (`:48`) | `DashboardPermission` enum | matches |
| login `email` / `password` | `z.email` / `.min(1)` (`:7-8`) | `EmailStr` / `str` (no min) (`:13-14`) | matches |

The update-description divergence is the only one the client is looser on, and it is the one a user
can walk into: `DashboardManagement.tsx:59-62` wires `updateDashboardSchema` as the edit dialog's
resolver and submits the result to `PUT /dashboards/{id}`, whose body is `DashboardUpdate`.

**Evidence** — The file/line table above, each row verified on both sides; `DashboardManagement.tsx:59-62`
establishes that the update schema is the resolver actually wired to the request. Not reproduced over
the wire: the server-side refusal was settled by reading the model, which is the authoritative
statement of the rule.

**Consequence** — Editing a dashboard description between 201 and 500 characters passes client
validation, is sent, and comes back as a 422 whose `detail` is rendered by the shared interceptor as
`toast.error("Validation error: …")` — the user is told the field is invalid after the form had
already accepted it, with no field-level attachment and nothing pointing at the description box.
In the other direction, a password such as `password12` is refused by the client with "Password must
contain at least one uppercase letter" even though the server would accept it, and a dashboard name
such as `Q1 sales (EMEA)` is refused by the client even though `DashboardCreate` would accept it —
both are rules the client invented, not rules the system enforces. Neither mis-refusal is dangerous,
but together they mean the client's validation is not a preview of the server's, which is the only
thing a user reasonably assumes it is.

**Recommendation** — Make the client's schemas match the server's: change `updateDashboardSchema`
`.max(500)` to `.max(200)` (or raise `DashboardUpdate`'s `max_length` to 500 — pick one owner;
the server's bound is the one that is actually enforced). Drop the `.regex(/[A-Z]/)` from
`changePasswordSchema` or add the uppercase rule to `validate_password_or_raise`; the same applies
to the dashboard-name character rule. Delete the client-side `BLOCKED_DOMAINS` copy entirely: the
server enforces it authoritatively from config, and the client's copy can only ever be a stale
snapshot. Remediation blockers: `shared/types/__tests__/formSchemas.test.ts:86` is named
"rejects description longer than 500 characters" but exercises `createDashboardSchema`, whose real
bound is 200 — the test passes and would not catch a regression of either bound, so it must be
corrected alongside the schema.

### FE-007 — The chart payload is declared as Plotly traces; the server sends flat row dictionaries, and a double cast is what hides the gap

**Severity** — MEDIUM

**Zone** — "Type Width at the Client Boundary: What Crosses as Unverified"

**Observation** — Every response shape at the client boundary is hand-declared in
`shared/types/api.types.ts`; nothing is derived from the server's OpenAPI schema and nothing is
validated at runtime. The chart boundary is where the declaration and the served shape are furthest
apart. `GraphDataWithConfig.data` is declared `Data[]` — i.e. Plotly's own trace type imported from
`react-plotly.js` (`api.types.ts:2,207`). The server declares the same field as
`list[dict[str, int | float | str]]` (`models/data.py:434`, `GraphDataResponse.data`) and populates
it from the JSONB `aggregated_data` rows (`api/routes/data.py:150-195`). `GraphDataWithConfig.config`
is likewise declared as a five-key optional object (`api.types.ts:209-215`) where the server
declares `dict[str, Any] | None` (`models/data.py:436`). The mismatch is absorbed at the consumer
by `graph.data as unknown as Record<string, unknown>[]` in `ChartRenderer.tsx:48` and
`ChartRenderer.tsx:70` — a double assertion that defeats the compiler at exactly the point the
declared type was supposed to protect.

**Evidence** — `api.types.ts:1-2,203-216` against `models/data.py:425-452`;
`ChartRenderer.tsx:48,70` (`as unknown as`). The server's own docstring states the payload is
"Data for charts in React (Plotly.js) format" (`api/routes/data.py:73`) while the field it fills is
a list of row dictionaries, which is the source of the confusion the double cast papers over.

**Consequence** — Nothing at the boundary would notice a change in the served shape. Today that
means two things are already true and neither is caught: the declared `Data[]` is never what
arrives, and `config` is declared narrower than what the server will send, so any additional chart
config key is silently dropped by the type while remaining present at runtime. The boundary
enforcement AGENTS.md asks for ("share types via OpenAPI", "avoid `any` completely") is satisfied in
form — the types are strict — and not in substance, because a strict type that is wrong at the
boundary is worse than `unknown`, since it removes the compiler's help exactly where the data is
least trustworthy.

**Recommendation** — Declare the served shape, not the desired one: change
`GraphDataWithConfig.data` to `Array<Record<string, string | number>>` (matching
`GraphDataResponse.data`), delete the double cast in `ChartRenderer.tsx`, and let `convertToPlotlyData`
be the single, typed place where rows become traces — which is what it already is. Type `config` as
`Record<string, unknown>` until the server's `ChartConfig` is actually used on this path. The larger
step — generating `api.types.ts` from the FastAPI OpenAPI schema — is worth doing once and removes
the whole class, but the declaration fix above is the whole of the immediate defect and can land
first.

### FE-008 — A dashboard whose dimension and metric happen to be named `x` and `y` renders blank charts with no error

**Severity** — MEDIUM

**Zone** — "Absent, Partial and Malformed Server Data"

**Observation** — `ChartRenderer.convertToPlotlyData` opens with a shape sniff
(`ChartRenderer.tsx:21-23`): if the first row has both an `x` and a `y` key it assumes the server
already sent Plotly traces and returns `graph.data` verbatim. The server never sends Plotly traces —
it sends row dictionaries whose keys are **column names taken from the uploaded file's processing
config** (`models/data.py:434`, `api/routes/data.py:166-195`), which are operator-supplied strings,
not a fixed vocabulary. A dashboard whose configured x column is literally named `x` and whose
metric is named `y` therefore takes the sniff branch, and the row dictionaries
`{"x": "A", "y": 1000, "region": "EU"}` are handed to Plotly as trace objects. Plotly receives
objects with no `type`, no `x` array and no `y` array, finds nothing to draw, and renders an empty
plot area inside the correctly-labelled `<Paper>` frame. Nothing throws, no query errors, no console
message, and `ChartRenderer` never reaches its empty-data branch because `graph.data.length > 0`.

**Evidence** — `ChartRenderer.tsx:21-23` (the sniff), `ChartRenderer.tsx:142,155` (the row dicts go
straight to `PlotlyChart`), `shared/components/PlotlyComponent.tsx:38-53` (passed through unmodified),
`DashboardView.tsx:190-197` (the frame and its title are rendered regardless). The failure is
reachable from configuration alone — no malformed data is required, only a legal column name.
A second, narrower instance of the same silence: `PlotlyComponent.tsx:34` returns `null` when the
interop probe fails, which `DashboardView.tsx:194` renders as a bare 400 px `Stack` with no message
— an empty frame that is indistinguishable from a chart that drew nothing.

**Recommendation** — Delete the sniff. The client knows the served shape (see FE-007: rows, never
traces), so the branch is not a fallback, it is an untested second code path that can only ever be
taken by accident. If a genuine Plotly-native path is wanted later, gate it on an explicit field the
server sets, not on key sniffing. For the `null` return in `PlotlyComponent.tsx:34`, render the
same "No data available for this chart" text the sibling branch uses (`ChartRenderer.tsx:128-134`)
rather than nothing.

### FE-009 — The account menu button and every range filter carry no accessible name, and nothing moves focus on a route change

**Severity** — LOW

**Zone** — "Interactive Surface Semantics: What an Assistive Technology Is Told"

**Observation** — The interactive surfaces this code composes, and what each exposes:

| Surface | Accessible name | Focus behaviour |
|---|---|---|
| `Header.tsx:87` account `IconButton` (wraps `<AccountCircle />`, no `aria-label`, no `aria-haspopup`, no `aria-expanded`, no `aria-controls`) | **none** — an empty `<button>` around an untitled SVG | opens a MUI `Menu` on click only; sole route to Profile and Logout (`Header.tsx:97-104`) |
| `DashboardFilters.tsx:186-193` range `Slider` | **none** — `<Typography variant="caption">{filter.name}</Typography>` is a bare caption with no `id`/`htmlFor`; the `Slider` gets no `aria-label` | drag or arrow keys; two range filters on one page announce identically |
| `DashboardFilters.tsx:134-148,152-177` select / multiselect | named — MUI `InputLabel` + `label` establishes the association | platform-supplied |
| `DashboardFilters.tsx:198-209` date `TextField` | named — `label` prop | platform-supplied |
| `AdminPanel.tsx:17-22` tabs | named — `aria-label="Admin panel tabs"` + `label` on each `Tab` | arrow keys, platform-supplied |
| `FileDropzone.tsx:76-103` dropzone | named — `role="button"`, `aria-label`, `aria-describedby`, `aria-live` region, and `useDropzone`'s own keydown handler | Tab-reachable and Enter/Space-activatable |
| `ConfirmDialog.tsx:30-43` | named — `DialogTitle` + MUI focus trap; MUI restores focus to the trigger on close | platform-supplied |
| dynamic errors (`<Alert>` in `DashboardView.tsx:127,182`, `DashboardList.tsx:24`, `LogViewer.tsx:128`) | announced — MUI `Alert` renders `role="alert"` | platform-supplied |

Across a route change there is no focus management at all: `app/routes.tsx` mounts no focus handler
and `AppLayout.tsx` only redirects trailing slashes. Following `/dashboards` → `/dashboard/:id`, the
focused element is a `DataGrid` row that unmounts, so focus falls to `<body>` and the next Tab
starts from the document root rather than the new page's heading. The same applies to every
`<Link>`-driven transition.

**Evidence** — `Header.tsx:87-89` (no accessible name, sole route to two destinations);
`DashboardFilters.tsx:185-193`; `routes.tsx:59-137` and `AppLayout.tsx:12-20` (no focus effect);
contrast with `FileDropzone.tsx:76-103` and `TableChart.tsx:39-58`, which do name their surfaces —
so this is inconsistent within the codebase, not a house style.

**Consequence** — A screen-reader user cannot tell the two range filters apart and gets no
indication which dashboard dimension a given slider adjusts. The account button announces as an
unlabelled button, and because it is the only path to Profile and to Logout, a user who never finds
it has no other route to signing out. On navigation the user is not told that the page changed or
where focus went.

**Recommendation** — Add `aria-label="Account menu"` plus `aria-haspopup="menu"` and
`aria-expanded={Boolean(anchorEl)}` to `Header.tsx:88`; give the range `Slider` an `aria-label`
derived from `filter.name` (`DashboardFilters.tsx:187`) — MUI forwards it to the underlying input.
For focus, add one `useEffect` in `AppLayout` that moves focus to the page container on
`location.pathname` change with `tabIndex={-1}`; this is the standard remedy and is a few lines.
Raising these above LOW would require a claim that assistive technology is blocked from a path
keyboard users still have, which is not the case here.

### FE-010 — Six of the seven declared entry modules are imported by nothing

**Severity** — MEDIUM

**Zone** — "Reachability of the Client's Own Declared Surfaces"

**Observation** — The client declares seven entry modules as its slice surfaces:
`features/{auth,dashboards,upload,users}/index.ts` and `shared/{api,components,hooks}/index.ts`.
An exhaustive import-edge enumeration across `frontend/src` shows that only
`features/auth/index.ts` is imported at all, and then by exactly two files
(`ProtectedRoute.tsx:3`, `RoleBasedAccess.tsx:1`). `features/dashboards/index.ts`,
`features/upload/index.ts`, `features/users/index.ts`, `shared/api/index.ts`,
`shared/components/index.ts` and `shared/hooks/index.ts` are imported by nothing — every consumer
names a concrete file or directory instead. In particular `shared/api/index.ts` re-exports
`axiosInstance` and `extractApiError`, the two things every API call and every error path depends
on, and it is not on any consumer's path.

The route surface is clean and is recorded as such: `/login`, `/register`, `/dashboards`,
`/dashboard/:id`, `/admin`, `/profile`, `/profile/change-password`, `/` and the `*` fallback are
all reached — `/register` from `LoginForm.tsx:5`, `/profile` and Logout from `Header.tsx:97-104`,
`/profile/change-password` from `UserProfile.tsx:101`, `/dashboard/:id` from the `DataGrid` row
handler at `DashboardList.tsx:94-96`, `/` by `RootRedirect`, `*` by `NotFound`. The only lazily
loaded segments are the seven route components and `UploadModal` (`DashboardView.tsx:19-21`),
reached by their routes and by the `canEdit` branch at `DashboardView.tsx:133-149`. No route is
reachable only by a typed location and no route is unreached.

**Evidence** — Enumeration of
`from '(\.\./)*(shared/api|shared/components|shared/hooks|features/(auth|dashboards|upload|users|admin))'`
across `frontend/src`: four hits, two production files and two test files, all
`../../features/auth`. Barrel contents read directly for all seven files. Route reachability traced
through `routes.tsx`, `Header.tsx`, `LoginForm.tsx`, `UserProfile.tsx`, `DashboardList.tsx`.

**Consequence** — The declared layering is advisory, not enforced by anything: nothing would fail if
a barrel drifted out of date with the module it re-exports, because no consumer reads it. That is
the mechanism that lets FE-004's credential-store edges persist unnoticed, and it is why a change
made for the sake of FSD compliance in this codebase can silently have no effect. The route
surface itself is complete, which is the part that would matter to a user.

**Recommendation** — Treat this as one change with FE-004, not a separate one: publish the
credential exports from `features/auth/index.ts`, point the three credential consumers at the
surface, and then either adopt the remaining six barrels or delete them. Leaving unreferenced
barrels in place is what produced the inconsistency; deleting them makes the concrete-path
convention explicit and removes the appearance of an enforced boundary that does not exist.

## Distribution

All ten findings land in the browser tier; none is a server defect. They concentrate in exactly two
files, which is the phase's clearest result: **`shared/api/axiosInstance.ts`** (FE-001, FE-003,
FE-004, and the toast half of FE-002) and **`shared/types/api.types.ts`** together with
`features/dashboards/ui/charts/ChartRenderer.tsx` (FE-007, FE-008). Six of the ten are consequences
of a decision made in one of those files, so a single owner can close most of this phase.

- `shared/api/` — the single request path, its interceptor, and its duplicated base declaration (4)
- `features/auth/model/` — the credential store that three slices import past its surface (2)
- `features/dashboards/ui/` + `shared/components/PlotlyComponent.tsx` — chart rendering and the
  declared/served shape gap (3)
- `shared/types/` — hand-written boundary types and the client's own Zod rule set (3)
- `shared/components/` — interactive semantics and focus (2)

By block: one finding each in the Request Path, Slice Boundaries, Build-Time Contract, Form Rules,
Type Width, Absent/Malformed Data, Interactive Surfaces and Reachability; two each in Failure
Surfacing and Session Continuity (both HIGH). Block 2 (server-derived value ownership) produced
none — see the Appendix for its inventory and why the empty band is the honest result.

## Cross-Finding Analysis

Three causes account for all ten findings, and each cause is a single decision in one file.

**A declared contract that nothing reads.** FE-004, FE-007 and FE-010 share one cause: the client
states boundaries it does not keep. The FSD barrels publish surfaces 100 % of consumers bypass
(FE-010); the credential store is a feature's private module reached into by three slices (FE-004);
`GraphDataWithConfig.data` declares Plotly traces while the server sends row dictionaries (FE-007).
In each case the declaration is load-bearing only as an appearance — a reader would take it for a
guarantee, and nothing at runtime or compile time would contradict it. FE-005 is the fourth instance
of the same shape on the build side: `validateEnv` declares a requirement with no consumer.

**Error state is handled per-component instead of per-class.** FE-002 and the toast half of FE-001
share one cause: there is no single place that owns "an API call failed". The response interceptor
emits a toast for the whole class while each surface independently decides whether to render
something inline, with no shared rule — hence three surfaces with three different answers, two of
them wrong. FE-001's silent logout is the same gap at its extreme: a failure class (429 on refresh)
with no branch anywhere.

**Boundaries are asserted rather than checked.** FE-006, FE-007 and FE-008 share one cause: both
sides maintain their own statement of the same fact — a password rule, a chart payload shape — and
neither checks the other. In FE-006 the two disagree in both directions; in FE-007/FE-008 the
client's statement is simply false and a double cast hides it.

Merge or adjacency, for the 99 validator:

- **FE-002 ↔ PERF-001 (phase 11) — adjacency, do not merge.** PERF-001 is the absent backend
  `LIMIT` and the 101.25 s / 30.9 MB / OOM measurement. FE-002 is what the client does with the
  resulting failure. Different files, different owners, and PERF-001's validator found its own
  recommendation self-contradictory, so the client half is the half that can move independently.
- **FE-002 ↔ AUTZ-001 / AUTZ-003 (phase 12) — merge candidate on the error branch only.** A
  403 from a zero-grant viewer reaches the user as `toast.error("Access denied: …")` plus, on
  `DashboardView`, the inline banner. Phase 12 owns whether the 403 should have been returned; this
  phase owns that the client's rendering of it is duplicated and unlabelled. Recommend merging only
  the "403 has two notification surfaces" observation into AUTZ-001 and keeping the rest of FE-002
  whole.
- **FE-004 ↔ FE-010 — merge.** One change, one file set. Recorded separately because the phase
  blocks are independent and the evidence differs (import edges vs. reachability), but a single fix
  closes both.
- **FE-001 ↔ AUTH (phase 04) — adjacency.** Phase 04 owns that `/auth/refresh` never rotates its
  cookie; this phase owns that the client spends two to three of a ten-per-5-minute budget on
  refreshes per hard reload and silently signs the user out when the budget runs out. Neither is
  true without the other being fixed.
- **FE-005 ↔ OPS-003 (phase 10) — merge candidate.** OPS-003 establishes the served bundle is an
  untracked host directory; FE-005 establishes that the bundle's own mandatory build-time variable
  has no consumer. Both point at "nothing in the build declares which artifact this is". Read
  together; file the ops half once.
- **FE-007 ↔ FE-008 — merge.** FE-007 is the false declaration, FE-008 is the render that follows
  from it. Fixing the declaration removes the reachability of the branch.

No claim is made here about the chart presentation contract; phase 16 owns it.

## Roadmap

Grouped by cause, not by severity. Steps 1-2 must land before step 3, because step 3's removal of
the duplicate toast changes what FE-001's 429 branch should do.

**Step 0 — Settle the chart payload shape (closes FE-007, FE-008).** Change
`GraphDataWithConfig.data` to `Array<Record<string, string | number>>`, delete the `as unknown as`
casts in `ChartRenderer.tsx:48,70`, delete the `'x' in … && 'y' in …` sniff at
`ChartRenderer.tsx:21-23`, and give `PlotlyComponent.tsx:34` the empty-state text its sibling
branch uses. Nothing else in the client can be judged correct while the served shape is misdeclared.
Expected user-visible change: a dashboard with `x`/`y` columns stops rendering blank.

**Step 1 — Give the client one owner for failure state (closes the toast half of FE-002, unblocks
FE-001).** Decide once whether a failure is a toast or an inline surface, record the decision in
`shared/api/errorMessages.ts` or a sibling, and make `axiosInstance.ts:127-136` suppress the toast
for any code a surface declares it renders inline. Then make the three surfaces mutually exclusive:
`DashboardView.tsx:181-199` must not render the graph list beside the error, `LogViewer.tsx:127-142`
must not hand retained rows to the grid beside `isError`, and both should use `isFetching` rather
than `isLoading` so a refetch shows a pending state. Verify by forcing one 500 on `/data/aggregated`
and one on `/admin/logs/` after a successful load, confirming exactly one notification and no stale
frame.

**Step 2 — Fix the session boot (closes FE-001).** Move the silent refresh out of the per-instance
`useRef` into a module-scope guard in `useAuth.ts`, so all three `useAuth()` instances await one
`POST /auth/refresh` per page load. Then give the 429 branch a user-visible outcome on `/login`
instead of a silent redirect. Before this step ships, confirm against Phase 15's rate-limiter
findings that the bound is still 10 / 300 s keyed per client IP; if that has changed, re-derive the
exhaustion threshold.

**Step 3 — Repair the slice boundaries (closes FE-004 and FE-010 together).** Publish
`useAuthToken`, `getTokenWithExpirationCheck`, `setToken`, `removeToken` and `logout` from
`features/auth/index.ts`; repoint `axiosInstance.ts:3`, `Header.tsx:4`, `dashboardApi.ts:3` and
`userApi.ts:3` at surfaces; then adopt or delete the six unreferenced barrels. Must follow step 2,
because step 2's fix lives inside the same module and re-pointing the imports afterwards is cheaper
than doing it twice.

**Step 4 — Reconcile the client's own rules with the server's (closes FE-006).** Align
`updateDashboardSchema.description` with `DashboardUpdate`, drop or serverise the uppercase and
name-character rules, and delete the `BLOCKED_DOMAINS` copy. Fix
`shared/types/__tests__/formSchemas.test.ts:86` in the same change — it currently asserts against a
different schema than its name says and will not catch a regression of either bound.

**Step 5 — Close the build-time contract (closes FE-005).** Delete `REQUIRED_ENV_VARS` /
`validateEnv()` if the API base is same-origin by design, or wire `VITE_API_URL` into
`axiosInstance.ts:9` and set it in `docker/Dockerfile` if it is not. Settle together with Phase
10's OPS-003, because which artifact is served determines which of the two is correct.

**Step 6 — Name the unnamed (closes FE-009).** `aria-label` / `aria-haspopup` / `aria-expanded` on
the account `IconButton`, `aria-label` on the range `Slider`, and one focus-move effect in
`AppLayout`. Independent of everything above; can land at any point.

**Step 7 — Unify the request path (closes FE-003).** Route the `ErrorBoundary` client-error report
through `axiosInstance` so the base location is declared once and the report carries the caller's
credential. Lands after step 3 so it does not have to move again.

## Rollout Safety

Steps 0, 2, 3, 5 and 6 change observable behaviour. Step 1 changes it most and is the one to stage.

**Step 1** removes a toast the user currently sees on every API failure. Anything that relies on
that toast — including any runbook that says "watch for a toast in the top-right" — will change.
The surfaces that render inline keep their message, so the failure class as a whole stays visible;
what disappears is the duplicate. `DashboardView.tsx:127` and `DashboardList.tsx:24` render a fixed
string today (`"Failed to load dashboard. Please try again."`), so if the toast is the one removed,
the user's message gets *worse* unless those switch to `extractApiError` in the same change — do
both or neither. Revert by re-enabling the toast unconditionally at `axiosInstance.ts:127`; no
server state is involved.

**Step 2** changes how many `/auth/refresh` calls a page load makes, from 2-3 to 1. That is a
reduction in load on a Redis-keyed rate limiter, so it cannot cause a new 429 — but it will make the
exhaustion threshold in FE-001's Consequence unreachable, and any monitoring tuned against the
current call volume will read low afterwards. The 429 branch gaining a visible message is the
additive half; if the silent-redirect behaviour is depended on by a shipped test, that test encodes
the defect and must change with it.

**Steps 3 and 7** are pure module moves with no runtime effect if done as moves. The one behaviour
change is that `/api/v1/client-errors` starts receiving the `Authorization` header; confirm
`api/routes/client_errors.py` accepts an authenticated POST and does not log the header.

**Step 0** changes what a dashboard with `x`/`y` columns renders. Before shipping, render one such
dashboard and confirm the intended chart appears — this is the only step that could turn a blank
chart into a wrong chart if the sniff is deleted without checking the conversion path.

**Step 5** is the only step that can turn a working page into a blank one, in the direction where
the value is added rather than removed. If `VITE_API_URL` is wired in, it must be set in both
`docker/Dockerfile` and `docker/docker-compose.yml`, and the dev path must keep working through the
Vite proxy — verify `npm run dev` and the dev compose before merging, not after.

## Appendices

**Block coverage.** All eleven blocks were executed; none was skipped. Block 2 (server-derived value
ownership) produced **no finding** and its inventory is below — the empty band is the honest result,
not an omission.

**Block 2 inventory — server-derived values, owner, key, invalidating mutation.** `dashboards`
list → `useQuery(['dashboards','my'])` (`dashboardApi.ts:47`) — no client mutation writes it.
Dashboard detail → `['dashboards', id]` (`:56`), invalidated by `invalidateDashboard` (`:84`).
Aggregated data → `['aggregatedData', dashboardId, filters]` (`:69`), invalidated only after a
successful upload (`DashboardView.tsx:218`). Filter values → `['filterValues', dashboardId,
filterName]` (`:93`) — never invalidated, and never needs to be. Processing status →
`['processingStatus', logId]` (`uploadApi.ts:47`), self-terminating via `refetchInterval`
(`:50-57`). Two values are genuinely held by two owners: `user` (a `useState` inside each `useAuth`
instance, plus the server on `/auth/me`) and the dashboard `permission` (a server field, re-read on
every `GET /dashboards/{id}`). The one place a mutation leaves a value the user still sees is
FE-002's stale-data cell; it is filed there because the block's own framing puts cache-key
composition with phase 11 and the user-visible residue here, and the residue is the finding. No
server-derived value is treated as authoritative on a refetch the client never issues.

**Surface × state matrix (Block 7).**

| Surface | empty result | absent optional field | failed first fetch | failed after a success |
|---|---|---|---|---|
| `DashboardList` | heading + empty grid + info Alert (`:56-80`) — distinguishable | `shortUuid`/`formatDateForGrid` accept the field | spinner (`:14-20`) then Alert (`:22-28`) | Alert replaces the grid — **correct** |
| `DashboardView` header | Alert "Failed to load dashboard" (`:125-131`) | `description`/`layout` guarded (`:152`) | spinner (`:117-123`) then Alert | Alert replaces the page — correct |
| `DashboardView` charts | info Alert "No data available" (`:200-206`) | `graphs`/`charts` guarded with `?.` | skeleton (`:177-179`) | **error Alert beside stale charts** — FE-002 |
| `ChartRenderer` per graph | "No data available for this chart" (`:128-134`) | `config` defaulted, `layout` optional | n/a (child of the above) | **out-of-type row → blank plot** — FE-008 |
| `PlotlyComponent` | `null` → bare 400 px frame (`:34`) | n/a | n/a | FE-008 |
| `TableChart` | `<p>No data available</p>` (`:32-34`) | `columns` derived from row 0 (`:30`) | n/a | data retained silently |
| `LogViewer` | empty grid, no empty-state text | `message`/`dashboard_name` defaulted (`:66,68`) | grid `loading` prop (`:136`) | **error Alert beside stale rows** — FE-002 |
| `DashboardFilters` | `null`, and `DashboardView:159` already gates on length | `options`/`values` defaulted (`:127-130`) | options render as an empty menu — no message | no distinction |

**Block 3 request-path inventory.** One transport for all API traffic: `axiosInstance`
(`baseURL: '/api/v1'` declared once at `axiosInstance.ts:9`; credential attached once by the request
interceptor at `axiosInstance.ts:18-30`; failure handled once by the response interceptor at
`axiosInstance.ts:55-139`). All five feature API modules (`authApi`, `dashboardApi`, `adminApi`,
`uploadApi`, `userApi`) import it. One bypass: `ErrorBoundary.tsx:40` (FE-003).

**Block 5 build-time declaration inventory.** `VITE_API_URL` — declared at `env.ts:5`, enforced at
`env.ts:21-29` in production only, **consumers found: none** (FE-005). No other build-time value is
declared. `import.meta.env.PROD` (`authToken.ts:74`) and `import.meta.env.DEV` (`providers.tsx:48`,
`ErrorBoundary.tsx:25`, `ErrorPage.tsx:11`) are Vite built-ins, not declarations, and each gates
real behaviour: `PROD` selects memory-vs-`sessionStorage` credential storage, `DEV` gates
devtools, the client-error reporter and the error-page stack trace.

**Cross-references cited, not re-filed.** Phase 04 AUTH (refresh cookie never rotated; adjacent to
FE-001). Phase 09 TST-015 — its remedy edits `frontend/src/shared/types/formSchemas.ts`, which this
phase owns for Block 8, and the concrete divergences in FE-006 are the substance behind that remedy;
Phase 09's finding that 0 of 21 backend request-body models declare `extra` means every divergence
in FE-006 is silent rather than reported, which is why none of them surfaces as a 422 the user can
act on. Phase 10 OPS-003 (served bundle is an untracked host directory; adjacent to FE-005).
Phase 11 PERF-001 (the 30.9 MB / OOM measurement behind FE-002). Phase 12 AUTZ-001 / AUTZ-003 (the
403 the client renders twice; merge candidate on that observation only). Phase 16 owns the chart
presentation contract and is not pre-empted here.

**What was run.** Static analysis only: file reads, targeted grep enumerations, and a directory
listing of `frontend/`. `npm run test`, `npm run lint` and `npm run build` were **not** executed —
`build` writes `frontend/dist`, which OPS-003 identifies as the untracked host directory nginx serves
and which peers may be using. No coverage run was attempted, so the Phase 09 deletion of 15 tracked
files under `frontend/coverage/` was not triggered; `git status --porcelain` is unchanged from the
recorded baseline, and that deletion was already present in it. The dev stack was not started,
stopped or reconfigured, and no user, dashboard, graph, grant or Redis key was created — this phase
issued no requests of any kind.

**Limits on this report.** (1) FE-001's exhaustion threshold is derived statically from
`auth.py:315` and `useAuth.ts:64-101`; it was not reproduced by exhausting a live Redis quota, which
would have consumed a shared limiter other phases depend on. (2) FE-005's production-build throw is
derived from Vite's documented `PROD`/`DEV` substitution and the absence of any `VITE_API_URL` in
`docker/Dockerfile`; the browser-side result was not observed, for the same `frontend/dist` reason.
(3) FE-008's blank-plot outcome is derived from what Plotly does with trace objects carrying no
`type`/`x`/`y`; it was not rendered in a browser. (4) Server-side rules in FE-006 were read from the
Pydantic models, which are authoritative, rather than probed over the wire. (5) The existing
`*.test.tsx` files were read but their assertions were not re-run; the suite's reported
169 passed / 1 failed state was taken as given.