# Phase 13 — Client Tier: code context

**Audit phase:** `13-client-tier`
**Report under decomposition:** `.ai/audit/99-validation/13-client-tier-validated-findings.md` (554 lines)
**Upstream provenance:** `.ai/audit/13-client-tier/findings.md` (730 lines, 10 `FE-*` findings)
**Finding-ID prefixes actually used by the report:** two.

| namespace | count | ids | role |
|---|---|---|---|
| `FE-` | 10 | `FE-001` … `FE-010` | the audited phase's own findings, carried in the report's disposition table |
| `VAL-13-` | 6 | `VAL-13-001` … `VAL-13-006` | the report's own report-level defects |

Both namespaces are preserved. **Neither prefix is `FE-` alone** — the brief's phrasing is right that the
prefix had to be determined from the file, and it is a *pair*. Note the frontmatter says
`findings: 6` and `by-severity: CRITICAL:0 HIGH:0 MEDIUM:5 LOW:1`, which counts only the `VAL-13-` half.

**Authority:** this document. Where it and the report disagree about *where* something is or *what it
does*, this document wins. Where they disagree about *identity*, the report's identifier set wins.

---

## 1. Scope and method

### 1.1 HEAD-vs-worktree split

`HEAD` is **`ab76989`** (`fix(worker): give the aggregate rebuild a declared lock and a bounded wait`) —
as the brief stated. Ten commits of context: `cea2d06`, `2174895`, `b646ef1`, `9a77625`, `a92b546`,
`c4c0b14`, `5b23240`, `2de4156`, `7e37aa2`.

| class | paths | phase-13 relevance |
|---|---|---|
| **D** deleted, tracked | `.ai/builders/**` (10 files incl. `front/package.json`, `front/ts_map.ts`), `.ai/structure/**` (6 incl. `front/ts_map.yaml`, `map.md`), `.ai/models/**` (2), `.ai/templates/**` (2), `.ai/plans/audit-fix-plan.md`, `.ai/audit/templates/audit-final-report.md` | none directly; **removes the frontend structure map the old plans were built on** |
| **D** deleted, tracked | `frontend/coverage/**` — all **15** files | **TST-014 / TST-004 (phase 09). Reproduced live: see §1.3** |
| **M** modified | `docs/06-backend/configuration.md`, `src/mkobi/db/advisory_lock.py`, `src/mkobi/workers/data_worker.py`, `tests/test_advisory_lock.py`, `tests/test_config.py` | backend-only; no `frontend/**` source file is dirty |
| **??** untracked | `.ai/plans/00`–`11` (12 files) + `_code-context/` (8 files), `.ai/tasks/B1-*.yaml`, `B2-*.yaml` | sibling plans; see §3.6 |

**No `frontend/src/**` file is dirty. Every anchor below was read from disk at HEAD.**

### 1.2 Frontend gates — real baseline (read-only, host-native)

| gate | command | result at `ab76989` |
|---|---|---|
| `fe-lint` | `npm --prefix frontend run lint` → `eslint .` (`Makefile.ps1:233-235`) | **RED — 9 errors, 0 warnings.** `filter-persistence.test.tsx` :123 `no-unsafe-return`, :188 `no-unsafe-assignment`, :219 `require-await`; `DashboardView.tsx` :57 + :72 `no-unsafe-member-access` on `location.state.preserveFilters`, :65 `react-hooks/set-state-in-effect`; `ChartRenderer.tsx` **:86, :90, :98 `no-unnecessary-type-assertion`** |
| `fe-test` | `npm --prefix frontend run test` → `vitest run --coverage` (`Makefile.ps1:237-239`) | **RED — 1 failed / 169 passed, 13 files, 170 tests, 22.46 s.** The single failure is `src/shared/types/__tests__/formSchemas.test.ts:162` `changePasswordSchema > accepts matching passwords` (`'newpassword123'`, `AssertionError: expected false to be true`) — **TST-015 / `VAL-09-003`** |
| `check` | `Makefile.ps1:241-249` | `lint → typecheck → fe-lint → fe-test`, **short-circuiting** on the first non-zero exit. Today it stops at `fe-lint` and **never reaches `fe-test`**. |
| frontend typecheck | **no target exists** | `Makefile.ps1` declares `fe-install`, `fe-lint`, `fe-test` only. TypeScript is checked **only** by `npm run build` → `tsc -b && vite build` (`package.json:8`), which writes `frontend/dist` — the untracked host directory OPS-003 (phase 10) names. **There is no declared frontend typecheck gate.** |

Consequences the Planner must plan around:

1. **`fe-lint` cannot be used as a pass/fail gate today** — it is red before any phase-13 edit. It is
   only usable as a *delta* gate: "the 9 known errors did not change" / "this block's file gained no new error".
2. **Three of the 9 lint errors are in `ChartRenderer.tsx`, the file FE-007's and FE-008's remedies edit.**
   `ChartRenderer.tsx:86,90,98` are `plotLayout.title as …['title']`, `plotLayout.xaxis as …['xaxis']`,
   `plotLayout.yaxis as …['yaxis']` inside `convertChartLayoutToPlotly` — **a function none of the ten findings
   names.** Any edit to that file must state whether these three pre-existing errors are in or out of scope.
3. **`fe-test` cannot be used as a green gate either** (1 red, and that red is phase 09's test file, which
   FE-006's remedy turns green). Until FE-006/Step 4 lands, "169 passed" is the pass criterion, not "0 failed".
4. **`fe-test` has a side effect on tracked files.** `vite.config.ts:56-65` sets `provider: 'v8'`,
   `reporter: ['text','json','html']`. Running the gate **wiped the 15 tracked `frontend/coverage/` files and
   wrote no replacement** (red suite ⇒ no report). Verified: `Test-Path frontend/coverage` → `False` **after**
   my run; the same 15 `D` entries were already present **before** it. Running `fe-test` therefore **does not
   restore them and does not create new ones**. Phase 09's TST-014 claim is now reproduced twice.

### 1.3 Coverage config and the tracked report

`vite.config.ts:56-65` — `provider: 'v8'`; `reporter: ['text','json','html']`;
`thresholds: { statements: 50, branches: 40, functions: 45, lines: 50 }`. `frontend/coverage/` is **tracked**
(15 files) and `eslint.config.js:9` `globalIgnores(['dist','coverage'])` excludes it from lint — so the
tracked HTML report is invisible to `fe-lint`. Phase 09 TST-014 and TST-004 are substantiated and
in-flight; phase 13 neither owns nor blocks on them, but must not use a coverage number as evidence.

### 1.4 tsconfig strictness and the `any` ban

`frontend/tsconfig.app.json` — `"strict": true` (:3), `target: es2023` (:5), `verbatimModuleSyntax: true`
(:14), `erasableSyntaxOnly: true` (:22), `noUnusedLocals`/`noUnusedParameters: true` (:20-21),
`noFallthroughCasesInSwitch: true` (:23), `noEmit: true`, `include: ["src"]`.

**The `any` ban is a rule, not a gate.**

| source | wording |
|---|---|
| `AGENTS.md` §9 | "Avoid `any` completely" |
| `.kilo/rules/project.md` §9 | "Avoid `any` completely" |
| `.ai/context/react-code-standards.md:11` | "Avoid `any` **unless absolutely necessary and explicitly justified**" — materially weaker |

Enforcement reality: `eslint.config.js` extends only `js.configs.recommended`,
`tseslint.configs.recommendedTypeChecked`, `reactHooks.configs.flat.recommended`,
`reactRefresh.configs.vite`. No `@typescript-eslint/no-explicit-any` entry appears, and a scan of
`frontend/src` for `\bany\b` returns **3 hits, all the English word** (`shortUuid.ts:9` comment,
`authToken.ts:62` comment, `RoleBasedAccess.test.tsx:118` test name). **There is no explicit `any` in the
client today, and nothing would fail if one were added.** What *does* fire is `no-unsafe-*` — i.e. `any`
**leaking through** a typed surface (`location.state` at `DashboardView.tsx:57,72`).

Toolchain friction to plan for: `verbatimModuleSyntax` forces `import type` on type-only changes;
`erasableSyntaxOnly` is why `enums.ts` uses `as const` objects; `noUnusedLocals` means deleting
`ChartRenderer.tsx:21-23` can orphan the `Data` import at `:5` or the `xCol`/`metricCols` bindings.

### 1.5 What I read

Report §Appendices A/B/C/D/E in full; upstream `findings.md` in full; sibling plans `00`–`11`
(frontmatter + scope-ruling tables + cross-phase tables only); `AGENTS.md`, `.kilo/rules/{project,commands}.md`,
`.ai/context/react-code-standards.md`; `docs/07-frontend/{architecture,fsd-structure,pages,auth-flow,frontend-security,upload-ui}.md`,
`docs/06-backend/architecture.md`.

Frontend: all 85 `git ls-files frontend/src` files enumerated; **31 read in full** — every module named
in §2's anchor column, plus all 9 barrel files and `{package.json,tsconfig.app.json,eslint.config.js,vite.config.ts}`.
Backend: `models/{dashboard,data,auth}.py`, `utils/validators.py`, `api/routes/{auth,data,client_errors,admin,upload}.py`,
`core/security.py`, `services/dashboard_service.py`. Root: `Makefile.ps1`, `docker/Dockerfile`.
Sibling plans read: `00`–`11` (frontmatter, scope-ruling tables, cross-phase tables) and the code-contexts
of `08`, `09`, `11`, `12`.

**Docker was not started.** No service was touched; the dev stack was already running and was left alone.
**No production code was modified.** No audit file or existing plan was modified.

---

## 2. Per-finding context

Each finding is anchored by **component / hook / API client function / query key / shared type / enum
mirror / CSS or theme token / vitest test**. Line numbers appear only as drift evidence.

### FE-001 — signed-in user returned to `/login` after N reloads with no message

**Band carried HIGH · verdict `substantiated`, mechanism intact / `stale` on the headline number.**

| anchor | state at `ab76989` |
|---|---|
| hook | `useAuth()` — `features/auth/model/useAuth.ts` |
| the guard | `hasAttemptedRefresh = useRef(false)` at `:14`; boot effect `:64-101`; guard body `:66-69`. **Per-instance, not per-page.** |
| the branch | `getToken()` at `:71`; `!token` → `apiRefreshToken()` at `:76`; `RATE_LIMIT_EXCEEDED` → `removeToken(); setUser(null)` at `:87-90`; the `else` arm at `:91-95` is **byte-identical** to the 429 arm — the class check buys nothing |
| credential store | `authToken.ts` — `USE_MEMORY_STORAGE = import.meta.env.PROD` at `:74`, `memoryToken` at `:66`, `getToken():134`, `getTokenWithExpirationCheck():179`, `useAuthToken():196` |
| mounts | `Header.tsx:21` · `ProtectedRoute.tsx:10` · `RoleBasedAccess.tsx:11` · `RootRedirect` `routes.tsx:46` |
| server budget | `api/routes/auth.py:315` — `check_rate_limit(rate_limit_key, max_attempts=10, ttl=300)`, key `refresh:{client_ip}` `:314` |
| limiter compare | `core/security.py:127` — `int(str(attempts)) >= max_attempts` **before** the `incr` at `:133` |
| toast/redirect bypass | `axiosInstance.ts:62-64` — `if (status === 429) return Promise.reject(error)` |
| redirect | `ProtectedRoute.tsx:21-23` — `<Navigate to="/login" state={{from: location}} replace />` |

**Drift / corrections.**

| claim | reality |
|---|---|
| "returned after **five** page reloads" (title) | **off by one — `VAL-13-004`.** Attempts 1–10 pass `:127`; attempt 11 is refused. `/dashboards` = 2 instances ⇒ reloads 1–5 consume 1–10, **reload 6 takes attempt 11**. `/admin` = 3 instances ⇒ reloads 1–3 consume 1–9, reload 4 takes 10, reload 5 takes 11. **VAL-13-004 substantiated.** |
| "up to three of ten per 5 min" | **drifted downward.** `RootRedirect` at `routes.tsx:46` is a **fourth** `useAuth()` call site. On `/` all four can mount simultaneously (`AppLayout` + `Header` + `RootRedirect` are siblings under `AppLayout`'s subtree — `routes.tsx:78,132`) ⇒ **4 refreshes per hard reload of `/`**. The upstream report listed `RootRedirect` among "the only other call sites" but did not count it toward the budget. |
| `useAuth().accessToken` | **`getToken()` at `:122` is a plain read in render, not `useAuthToken()`** — it subscribes to nothing. `ProtectedRoute.tsx:10` reads `accessToken` from it. Only the query hooks (`dashboardApi.ts:45,54,67,91`) use the reactive `useAuthToken()`. Unnamed in the report. |

**Seams an implementor touches:** `useAuth.ts` boot effect + `authToken.ts` (module-scope guard vs.
per-instance), `authToken.ts:74` storage mode, the 429 branch's missing message, `RoleBasedAccess.tsx:11`
(third `useAuth` copy). **Vitest:** `features/auth/model/__tests__/useAuth.test.tsx` mocks
`registerRefreshHandler` (`useAuth.test.tsx:36`) — the refresh path has a test seam.

### FE-002 — one failed fetch ⇒ toast + inline banner + stale charts, simultaneously

**Band carried HIGH · verdict `substantiated`.**

| anchor | state |
|---|---|
| the one class owner that does not exist | `axiosInstance.ts:55-139` — the whole response interceptor |
| the toast half | `:127-136` — `if (status && status !== 401 && status !== 429)` → `extractApiError` → `getErrorMessage(code)` → `toast.error(`${localizedMessage}: ${message}`)`. **Unconditional for the class.** `/auth/login` is the sole exclusion (`:129`). |
| error-extraction chain | `shared/api/errorHandler.ts:37-102` — L1 legacy 422 array `:46-54` · L2 RFC 7807 `:57-77` · L3 field extraction `:62-70,128-138` · L4 `error.message` `:81-86` · L5 generic `:98-101`. `mapErrorCode:118-123` silently coerces an unknown server code to `INTERNAL_ERROR`. |
| message map | `shared/api/errorMessages.ts:13-54` — 31 `ErrorCode` keys; `getErrorMessage:70-92` resolution order **feature → shared → detail → default** |
| surface 1 (wrong) | `DashboardView.tsx` — skeleton `:177-179` on `dataLoading`; `<Alert severity="error">` `:181-185` on `dataError`; graph list `:187-198` gated **only** on `aggregatedData?.graphs.length > 0`. Three independent conditions. |
| surface 2 (wrong) | `LogViewer.tsx` — `useQuery` `:50-53`; `rows` from retained `logs` `:64-71`; `isError` `<Alert>` `:127-131`; `<DataGrid rows={rows}>` `:133-142` — same pass. |
| surface 3 (correct) | `DashboardList.tsx:22-28` — `if (error) return` replaces the grid. **The pattern is available.** |
| surface 4 (wrong, header) | `DashboardView.tsx:125-131` — `if (dashboardError \|\| !dashboard) return` **replaces** the page, so it is actually *correct* on exclusivity but carries a **fixed string at `:128`**, not `extractApiError`. |
| query options | `providers.tsx:10-17` — `retry: 1`, `staleTime: 5 * 60 * 1000`, **no `placeholderData`**. `dashboardApi.ts:68-77` adds none. `LogViewer.tsx:51` adds none. |

**Drift / corrections.** The validator's TanStack-Query-library reading is correct and load-bearing
(`@tanstack/query-core@5.101.0` keeps `data` and `error` both non-null on a failed refetch;
`isLoading = isPending && isFetching`). Three unnamed surfaces of the same class exist:

| surface | shape |
|---|---|
| `DashboardFilters.tsx:127-130` | `dynamicValues = filterValuesData?.values \|\| []`; on a failed refetch the **retained** list renders with no error, no empty-state, no message |
| `UserManagement.tsx` / `RegistrationRequests.tsx` / `DashboardManagement.tsx` | admin surfaces, same pattern family; each fires its own `invalidateQueries` (`:99,112,123` / `:93,108` / `:72,92,111` per the report) |
| `Header.tsx` + `axiosInstance.ts:83,118` | two **hardcoded English** `'Session expired. Please login again.'` strings bypassing the `ErrorCode` → `getErrorMessage` chain entirely |

**Seams:** `axiosInstance.ts:127-136`; the three rendering sites; `DashboardView.tsx:127-129` and
`DashboardList.tsx:24-26` fixed strings; `errorMessages.ts` as the decision surface — but note **five
sibling `errorMessages.ts` files** exist (`features/{admin,auth,dashboards,upload,users}/model/errorMessages.ts`)
that `axiosInstance.ts` **never passes as the second argument**, so the feature-map tier of
`getErrorMessage` is currently dead on the toast path. **Vitest:** `shared/api/__tests__/{errorHandler,errorMessages}.test.ts`
both exist and cover the chain — the cheapest available evidence in the whole phase.

### FE-003 — a second hard-coded API base in `ErrorBoundary`'s `fetch`

**Band carried MEDIUM · verdict `substantiated` (consequence (2) is `stale`, as the validator weakened it).**

| anchor | state |
|---|---|
| the two transports | `axios.create` at `axiosInstance.ts:8` · `fetch('/api/v1/client-errors'` at `ErrorBoundary.tsx:40`. A `fetch(`/`axios(`/`XMLHttpRequest`/`EventSource` scan of `frontend/src` returns **exactly these two.** |
| the bypass | `ErrorBoundary.tsx:32-45` — `private reportError`. No `Authorization` (bypasses the request interceptor at `axiosInstance.ts:18-30`), no `withCredentials` (`:10`), literal base `:40`, `.catch(() => {})` `:44` |
| the DEV gate | `ErrorBoundary.tsx:24-30` — `if (import.meta.env.DEV) console.error` else `reportError` |
| server contract | `api/routes/client_errors.py:28` — *"Accepts client error details for logging. **No authentication required**."* |
| the escape hatch already present | `shared/api/refreshHandler.ts:1-9` — the registration pattern, written *specifically* to break the shared→feature cycle |
| second mount | `ErrorBoundary` is mounted **twice**: `providers.tsx:43` and `routes.tsx:79` |

**Correction:** the validator's weakening is right and the brief's "no credential = a loss" is
`stale` — the endpoint declares anonymity. The real loss is (a) the duplicated base literal and
(b) `.catch(() => {})` making the reporter unwatchable. **A class-method context is the concrete seam:**
`reportError` is a `private` method on a `React.Component`, so it can call `axiosInstance` but cannot
use hooks — worth stating because the natural refactor (a hook-based reporter) does not fit.

### FE-004 — the credential store is a feature's private module, reached into by shared code and two features

**Band carried MEDIUM · verdict `substantiated`.**

| edge | site | status |
|---|---|---|
| shared → auth internals | `axiosInstance.ts:3` → `features/auth/model/authToken` (`getTokenWithExpirationCheck`, `removeToken`, `setToken`) | confirmed |
| shared → auth internals | `Header.tsx:4` → `features/auth/model/useAuth` | confirmed |
| dashboards → auth internals | `dashboardApi.ts:3` → `features/auth/model/authToken` (`useAuthToken`) | confirmed |
| users → auth internals | `features/users/api/userApi.ts:3` republishes `getProfile` from `../../auth/api/authApi` | confirmed |
| dashboards → upload ui | `DashboardView.tsx:20` (lazy) `→ ../../upload/ui/UploadModal` | confirmed |
| the **documented** rule violated | `docs/07-frontend/fsd-structure.md:165` *"**`shared/` must never import from `features/` or `app/`**"*; `:153` *"Features should not import from each other's `model/` or `ui/`"*; `:151` *"`index.ts` — Public API — only exports that other features may import"* | **the report cites none of these; they are the strongest anchors in the finding** |
| the self-documenting sibling | `refreshHandler.ts:6-7` — *"The shared layer never imports from feature modules"* — contradicted by its own sibling `axiosInstance.ts:3` | confirmed, as the report notes |
| barrel enumeration | `grep "from '(\.\./)*(shared/(api\|components\|hooks)\|features/[a-z]+)'"` over `frontend/src` → **exactly 4 hits, all `../../features/auth`**: `ProtectedRoute.tsx:3`, `RoleBasedAccess.tsx:1`, `ProtectedRoute.test.tsx:26`, `RoleBasedAccess.test.tsx:10` | confirmed exactly |

**New, unnamed by the report — the barrels under-publish in a second direction.**
`features/dashboards/index.ts` exports `dashboardApi, useMyDashboards, useDashboard, useAggregatedData`
but **withholds `useFilterValues` and `useInvalidateDashboard`**, both of which are consumed by internal
paths (`DashboardFilters.tsx:16`, `DashboardView.tsx:12`). Under FE-004's own remedy ("publish what is
actually consumed") these are a **fifth and sixth** credential-adjacent symbols needing a barrel route,
not the three the report names. `features/auth/index.ts` publishes exactly `useAuth`, `login`,
`registerRequest`, `getProfile`, `logoutClient` + 3 types — confirmed, and it omits `logout` too.

### FE-005 — `VITE_API_URL` declared mandatory, consumed by nothing

**Band carried MEDIUM · verdict `substantiated`.**

| anchor | state |
|---|---|
| declaration | `shared/config/env.ts:5` — `REQUIRED_ENV_VARS = ['VITE_API_URL'] as const`; `validateEnv():13-30`; **DEV early-return `:15-17`** |
| the call site | `main.tsx:7` — `validateEnv()` **before** `ReactDOM.createRoot` at `:9`, so a throw escapes `providers.tsx:43`'s `ErrorBoundary` |
| the only consumer of the base | `axiosInstance.ts:9` — `baseURL: '/api/v1'`, a literal |
| dev proxy | `vite.config.ts:9-14` — `/api` → `http://app:8000` |
| the build | `docker/Dockerfile:22` — `RUN npm run build`. The only `ARG`s in the file are `DEBIAN_MIRROR` (`:31,66`) and `UV_VERSION` (`:51,85`). **No `ARG`/`ENV VITE_API_URL` at any stage.** |
| other `import.meta.env` reads | `authToken.ts:74` (`PROD`), `providers.tsx:48` (`DEV`), `ErrorBoundary.tsx:25` (`DEV`), `ErrorPage.tsx:11` (`DEV`) |
| `.env*` files | none in `frontend/` (directory listing: `.gitignore dist eslint.config.js index.html node_modules package-lock.json package.json public README.md src tsconfig*.json vite.config.ts`) |
| the shipped-artefact proof | `frontend/dist/` exists untracked; `assets/index-CP3NT1Oa.js` carries `var $e=['VITE_API_URL']` against a lookup object `{BASE_URL:'/',DEV:!1,MODE:'production',PROD:!0,SSR:!1}` with **no `VITE_API_URL` key** |

**Two drags this phase must not inherit silently.** (a) FE-005's "wire `VITE_API_URL` into
`axiosInstance.ts:9`" and FE-003's "read the base from the single declared source" are the **same
one-line edit**, in the same file, from two findings — a merge seam the report never names.
(b) `docker/Dockerfile` is the file phase 08's `CQLT-4` block and phase 01/07's manifest work also touch;
`vite.config.ts` is not currently owned by any plan.

### FE-006 — client validation rules vs the server's, in three places stricter and one looser

**Band carried MEDIUM · verdict `substantiated` at three of four rows; the fourth row is `refuted` (`VAL-13-001`); a fifth divergence is unnamed.**

| field | client `shared/types/formSchemas.ts` | server | verdict |
|---|---|---|---|
| `description` on **update** | `.max(500)` `:40` | `models/dashboard.py:140` `Field(None, max_length=200)` | **diverges — client looser.** Confirmed. |
| `description` on **create** | `.max(200)` `:31` | `dashboard.py:54` `max_length=200` | matches. Confirmed. |
| `name` on **create** | `.min(3).max(100).regex(/^[a-zA-Z0-9\s-]+$/)` `:25-30` | **`dashboard.py:58-67`, regex at `:65`, identical string at `:66`** | **`refuted` — `VAL-13-001` substantiated. `DashboardCreate` enforces the character rule.** |
| `new_password` | `.min(8).regex(/[A-Z]/).regex(/[0-9]/)` `:56-59` | `utils/validators.py:183-203` — digit `:199`, letter **of any case** `:202`, no uppercase; reached via `models/auth.py:178 ChangePasswordRequest` → `:205 validate_new_password_field` → `:207 validate_password_or_raise(v)`, and `services/auth_service.py:151` for registration | **diverges — client stricter.** Confirmed. |
| register `email` domain | `BLOCKED_DOMAINS = ['tempmail.com','throwaway.email']` `:3`, **case-sensitive** `.includes` `:17` | `settings/app.yaml` `config.email.blocked_domains`, lower-cased on input | **diverges.** Confirmed. |
| **`name` on update** | `.min(1).max(100)`, **no regex, no min(3)** `:39` | `dashboard.py:139` `name: str \| None = None` — **no bound at all**; `dashboard_service.update_dashboard` (`:262`) does **not** re-run `validate_name` | **NOT NAMED BY EITHER REPORT.** Client stricter in two ways (min 3, the character regex) that the server does not enforce on this path. Safe direction (client refuses, server accepts), same class as `new_password`. |
| `user_id` / `permission` / login `email` / login `password` | `z.uuid():47`, `z.enum(['view','edit','admin']):48`, `z.email():7`, `.min(1):8` | UUID param, `DashboardPermission`, `EmailStr`, `str` | matches |

**Test seams — the decisive ones.**

| test | state |
|---|---|
| `formSchemas.test.ts:86-89` — *"rejects description longer than 500 characters"* | **confirmed exactly.** Calls `createDashboardSchema.safeParse({ name:'Valid', description:'a'.repeat(501) })`. Real bound is 200. Fails for the wrong reason; catches neither bound. |
| `formSchemas.test.ts:97-117` — `updateDashboardSchema` | **no description-bound test at all.** Changing `:40` to `.max(200)` breaks nothing and proves nothing. |
| `formSchemas.test.ts:162` — `changePasswordSchema > accepts matching passwords` | **the one red test in the suite.** `'newpassword123'` against `.regex(/[A-Z]/)`. **Landing the `new_password` fix turns this green** — so `fe-test` goes 170/0. This is TST-015 / `VAL-09-003`. |

**Ownership:** the report proposes "pick one owner" per row and, for `new_password`, offers both
"drop the client rule" and "add the uppercase rule to `validate_password_or_raise`". **Those are not
equivalent**: the second edits `utils/validators.py`, a **backend** file, and would change
`change_password` for every caller including admin-initiated resets. That is a backend edit inside a
client finding — a genuine scope leak the report does not flag.

### FE-007 — the chart payload is declared as Plotly traces; the server sends row dicts

**Band carried MEDIUM · verdict `substantiated`.**

| anchor | client | server |
|---|---|---|
| the declaration | `shared/types/api.types.ts:2` `import type { Data } from 'react-plotly.js'` · `:203-216` `GraphDataWithConfig` · **`:207` `data: Data[]`** · `:209-215` five-key optional `config` | `models/data.py:434` `data: list[dict[str, int \| float \| str]]` · `:436` `config: dict[str, Any] \| None` · `:435` `layout: ChartLayoutConfig \| None` |
| the double cast | `ChartRenderer.tsx:48` and `:70` — `for (const row of graph.data as unknown as Record<string, unknown>[])` | — |
| the docstring that caused it | `api/routes/data.py:73` — *"Data for charts in React (Plotly.js) format"* | `:59` — `Response format: {"graphs": [{"graph_id": …, "data": [...]}]}` |
| the population site | — | `data.py:145-160` (single-graph) and `:182-195` (all-graphs): `item.get("preview")` extended into `item_data_points`; `config=graph_item.config` (JSONB) |

**Three corrections the report does not make.**

1. **The `layout` half of `GraphDataWithConfig` is dead on this path.** `GraphDataResponse.layout`
   exists (`data.py:435`) but **neither `data.py` branch ever sets it** (`:150-158`, `:187-194`).
   So `graph.layout` is always `undefined` and `convertChartLayoutToPlotly` (`ChartRenderer.tsx:80-119`)
   always returns `undefined`. Its three `no-unnecessary-type-assertion` lint errors (`ChartRenderer.tsx:86,90,98`)
   are on a function that **can never run with input**. Deleting or keeping it is a real choice.
2. **`GraphType` in `data.py:432` is the backend `GraphType` StrEnum** (`bar/line/pie/table`) mirrored by
   `enums.ts:23-30` — that mirror is **correct** and is the one place the enum hand-off works.
3. **`TableChart.tsx` already takes row dicts, not traces** — `ChartRenderer.tsx:124` passes
   `<TableChart data={{ rows: graph.data }} />` and `TableChart.tsx:5` types them
   `Record<string, unknown>[]`. So **half the file already models the served shape** and the other half
   does not. Any `Data[] → Record<string, …>[]` change makes `TableChart`'s branch type-correct by accident.

**Test seam — the one that will break.** `features/dashboards/__tests__/DashboardView.test.tsx:52-77`
mocks `useAggregatedData` returning
`data: [{ x: ['A','B','C'], y: [1,2,3], type: 'bar' }]` and `[{ x: [1,2,3], y: [10,20,30], type: 'scatter', mode: 'lines' }]`.
**These fixtures are Plotly traces — exactly what the server never sends — i.e. the suite encodes
FE-008's refuted premise as its happy path.** Under `verbatimModuleSyntax` they will not compile against
`Array<Record<string, string | number>>`. `filter-persistence.test.tsx:77-…` has the same fixture shape.

### FE-008 — a dashboard with columns named `x`/`y` renders (per the validator) not blank but wrong

**Band carried MEDIUM · verdict `substantiated` as to mechanism/reachability/remedy; `refuted` as to the asserted cause (`VAL-13-002`).**

| anchor | state |
|---|---|
| the sniff | `ChartRenderer.tsx:21-23` — `if (graph.data.length > 0 && 'x' in graph.data[0] && 'y' in graph.data[0]) return graph.data` |
| presentation defaults in the adaptation layer | `ChartRenderer.tsx:15` `xCol = config.x \|\| 'x'` · `:17` `metricCols = config.metrics \|\| ['y']` · `:18` `orientation` · `:149` `barmode` |
| what is skipped when the sniff fires | the whole `colorCol` grouping `:45-65`, the `makeTrace` builder `:28-43`, `metricCols[0]` at `:26`, the `type` selection `:32-33` |
| the frame | `DashboardView.tsx:190-197` — `<Paper>` + `<Typography variant="h6">{graph.name}</Typography>` + `<Stack sx={{ height: 400 }}>`, rendered unconditionally |
| the `null` interop escape | `shared/components/PlotlyComponent.tsx:20-26` resolves the CJS component · `:34` `if (!PlotComponent) return null` → a bare 400 px `Stack` |
| the sibling empty-state text | `ChartRenderer.tsx:128-134` — `"No data available for this chart"` |
| reachability | from **configuration alone**: the uploaded file's column names are operator-supplied (`data.py:434`, keys of the JSONB row dicts) |

**VAL-13-002's mechanism is confirmed by construction, and it changes the verification, not the fix.**
By the sniff's own guard, `graph.data[0]` carries both `x` and `y` — as **scalars**, not arrays. Plotly
(`plotly.js-dist-min ^3.5.1`, `package.json:25`) declares the trace `type` attribute with `dflt:"scatter"`,
so the traces are typed; they draw **one marker per graph**. The report's remedy (delete `:21-23`) and its
reachability claim stand. **The Rollout-Safety check must be a trace-count/axis-category assertion, not
"a chart appears"** — a one-point plot satisfies the latter. **No browser run was made here either;
the pixel artefact remains unsettled for both reports.**

### FE-009 — the account button and every range filter carry no accessible name; nothing moves focus

**Band carried LOW · verdict `substantiated`; band upheld.**

| surface | state | named? |
|---|---|---|
| account button | `Header.tsx:87-89` — `<IconButton color="inherit" onClick={handleMenuOpen}><AccountCircle /></IconButton>`. No `aria-label`, no `aria-haspopup`, no `aria-expanded`, no `aria-controls`. `anchorEl` state at `:24` already exists, so `aria-expanded={Boolean(anchorEl)}` is a zero-new-state change. Sole route to Profile/Logout at `:97-105`. | **no** |
| range slider | `DashboardFilters.tsx:186` `<Typography variant="caption">{filter.name}</Typography>` — no `id`/`htmlFor`; `:187-193` `<Slider>` — no `aria-label`. Two range filters announce identically. | **no** |
| select / multiselect | `DashboardFilters.tsx:134-148`, `:151-177` — MUI `InputLabel` + `label` | yes |
| date field | `DashboardFilters.tsx:198-209` — `label` prop | yes |
| admin tabs | `AdminPanel.tsx` — `aria-label="Admin panel tabs"` + per-`Tab` `label` | yes |
| dropzone | `FileDropzone.tsx` — `role="button"`, `aria-label`, `aria-describedby`, `aria-live`, own keydown handler | yes |
| data table | `TableChart.tsx:40-42` — `role="grid"`, `aria-label`, visually-hidden `<caption>` `:44-58` | yes |
| confirm dialog | `ConfirmDialog.tsx` — `DialogTitle` + MUI focus trap | yes |
| route-change focus | `routes.tsx:59-137` mounts **no** focus effect; `AppLayout.tsx:12-20` renders `TrailingSlashRedirect` + `Header` + `Outlet` and nothing else | **no** |

**Constraint the Planner must state.** `AppLayout.tsx` currently renders **no DOM element of its own**
— the focus-move remedy requires adding a container with `tabIndex={-1}`, which changes the DOM shape
that `routes.tsx:78` and `routes.tsx:134` (`*` fallback) wrap. Also: `DashboardFilters.tsx:40-43`
already carries `// eslint-disable-next-line react-hooks/set-state-in-effect`, so a focus effect that
sets state in an effect must be written against that established precedent — and
`DashboardView.tsx:65` is the same violation **without** the disable, which is one of the 9 lint errors.

**Theme / CSS tokens: there are effectively none.** `providers.tsx:19-23` — `createTheme({ palette: { mode: 'light' } })`.
No spacing scale, no typography scale, no contrast tokens. `react-code-standards.md:42-45` asks for
"design tokens and reusable spacing/typography systems" and `sx`/`styled()` discipline; neither exists.
Non-MUI styling in the chart path: `ChartRenderer.tsx:130` uses a **Tailwind class string**
(`className="flex items-center justify-center h-64 text-gray-500"`) on a raw `<div>`, and
`TableChart.tsx:36-80` uses raw `<div>/<table>/<th>/<td>` with inline `style` objects — both violate
`react-code-standards.md:43` ("**MUI only**"). **FE-009's remedy has no token to reach for; any contrast
claim must be argued from MUI defaults.**

### FE-010 — six of seven declared entry modules are imported by nothing

**Band carried MEDIUM · verdict `substantiated`; the count is `drifted` — there are eight, not seven.**

| barrel | content | imported by |
|---|---|---|
| `features/auth/index.ts` | `useAuth`, `login`, `registerRequest`, `getProfile`, `logoutClient` + 3 types | **2 production** (`ProtectedRoute.tsx:3`, `RoleBasedAccess.tsx:1`) + 2 test |
| `features/dashboards/index.ts` | `DashboardList`, `DashboardView`, `DashboardFilters`, `PlotlyChart`, `dashboardApi`, `useMyDashboards`, `useDashboard`, `useAggregatedData` + 4 types | **nothing** |
| `features/upload/index.ts` | `FileDropzone`, `UploadModal`, `uploadApi` | **nothing** |
| `features/users/index.ts` | `UserProfile`, `getProfile`, `deleteAccount` | **nothing** |
| `shared/api/index.ts` | 10 types + `ErrorCode` + `axiosInstance` + `extractApiError` + `ErrorExtractionResult` + `sharedErrorMessages`/`getErrorMessage`/`DEFAULT_ERROR_MESSAGE` + `PartialErrorMessages` | **nothing** |
| `shared/components/index.ts` | `AppLayout`, `Header`, `ProtectedRoute`, `RoleBasedAccess`, `AccessDenied`, `ConfirmDialog`, `ErrorBoundary`, `ErrorPage`, `NotFound` | **nothing** |
| `shared/hooks/index.ts` | `useApiError`, `useConfirmDialog`, `useDebounce`, `useDebouncedCallback` | **nothing** |
| **`features/dashboards/ui/charts/index.ts`** | `PlotlyChart`, `ChartRenderer`, `SkeletonChart` | **nothing** — and it is itself only reachable from `features/dashboards/index.ts`, which nothing imports. **This is the eighth barrel; the report counted seven.** |
| **`shared/components/Layout/index.ts`** | `AppLayout`, `Header` | **nothing** — imported by `routes.tsx:6`. **Ninth.** |

`git ls-files frontend/src` = **85** — the report's denominator, confirmed.

### VAL-13-001 — `DashboardCreate` enforces the name character rule; FE-006's row is refuted

**Verdict `substantiated` (the report-level defect is real); it removes one FE-006 target.**

`models/dashboard.py:58-67` — `@field_validator('name')`, `len < 3` `:61`, `len > 100` `:63`,
**`re.match(r'^[a-zA-Z0-9\s-]+$', v)` `:65`**, message `'Name can only contain letters, numbers, spaces, and hyphens'` `:66`.
Character-for-character identical to `formSchemas.ts:28-30` including the message string.

**Consequence for the Planner:** the report's Roadmap **Step 4** instruction *"drop or serverise the
uppercase and name-character rules"* **inverts** the divergence if executed literally. Step 4's surviving
targets are exactly: `updateDashboardSchema.description` (`:40`), `changePasswordSchema.new_password`
(`:56-59`), `BLOCKED_DOMAINS` (`:3,:17`). **Also verified: `formSchemas.ts:25-30` should move to the
"matches" column, and `updateDashboardSchema.name:39` should be added as a newly-named divergence.**

### VAL-13-002 — the traces are not untyped, so they do not render blank

**Verdict `substantiated`; it changes the target's verification, not its remedy.**

By `ChartRenderer.tsx:21`'s own guard the objects carry `x` and `y`; they carry them as scalars.
`plotly.js-dist-min ^3.5.1` (`package.json:25`) + `react-plotly.js ^2.6.0` (`:27`) declare trace `type`
with `dflt:"scatter"`. So: **one marker per graph inside a correctly-labelled `<Paper>`** — a *wrong*
chart, not an empty one. **Remedy unchanged (delete `:21-23`); Rollout Safety must change from
"confirm a chart appears" to "confirm trace count and axis categories match `config.metrics`".**

### VAL-13-003 — `['filterValues', …]` is never invalidated and never refetched

**Verdict `substantiated`; this is a **new** phase-13 target and the most concrete one-line fix in the phase.**

| anchor | state |
|---|---|
| the key | `dashboardApi.ts:90-97` — `queryKey: ['filterValues', dashboardId, filterName]` `:93`, `enabled: !!dashboardId && !!filterName && !!accessToken` `:95` |
| the consumer | `DashboardFilters.tsx:126` `useFilterValues(dashboardId, filter.name)` · `:127` `dynamicValues = config.source === 'data' ? (filterValuesData?.values || []) : []` · `:128-130` the option list |
| every `invalidateQueries` in the client | `dashboardApi.ts:84` `['dashboards', id]` · `dashboardApi.ts:86` `['aggregatedData', dashboardId]` · `UserManagement.tsx:99,112,123` · `RegistrationRequests.tsx:93,108` · `DashboardManagement.tsx:72,92,111`. **Five keys total. None names `['filterValues', …]`.** |
| the upload event | `DashboardView.tsx:215-220` — `onUploadComplete` → `void invalidateAggregatedData(id)` `:218`. **Charts refresh; the filter menu does not.** |
| the server set | `models/data.py:483-491` `FilterValuesResponse { filter_name: str, values: list[str] }`; client `api.types.ts:150-153` `values: string[]` — **types match**, no divergence here |
| `staleTime` | `providers.tsx:14` — 5 minutes. So the cached list survives 5 min *and* then is refetched — **unless nothing ever marks it stale**; with `refetchOnMount` default `true` a remount inside `staleTime` serves cache without a request. The "for the life of the tab" claim holds for the mounted `DashboardFilters` instance. |
| tests | **zero coverage.** `DashboardView.test.tsx:28-30` and `filter-persistence.test.tsx:35-57` both `vi.mock('../ui/DashboardFilters')`; both also `vi.mock('../api/dashboardApi')` (`:38` / `:60`). **Neither the hook nor the key is reachable from any test.** |

**Prefixed-key note (this is why the fix is cheap):** `dashboardApi.ts:86` already uses the **prefix**
`['aggregatedData', dashboardId]`, so one extra `invalidateQueries({ queryKey: ['filterValues', dashboardId] })`
covers every `filterName` under that dashboard. Nothing else has to move.

### VAL-13-004 — FE-001's headline is one reload short; the limiter's `>=` allows the tenth

**Verdict `substantiated`.**

`core/security.py:126-136`: `:127` `if attempts is not None and int(str(attempts)) >= max_attempts: return False, …`
**then** `:132-135` `pipeline.incr` + `expire`. With `auth.py:315` `max_attempts=10, ttl=300`:
attempts 1–10 allowed, **attempt 11 refused**. `/dashboards` (2 instances): reloads 1–5 consume 1–10,
**reload 6** takes 11. `/admin` (3 instances): reloads 1–3 consume 1–9, reloads 4–5 take 10–11.
**And `/` (4 instances, incl. `routes.tsx:46`): reloads 1–2 consume 1–8, reload 3 takes 11** — the
cheapest route to exhaustion, and not in either report.

### VAL-13-005 — `VAL-001`…`VAL-009` each resolve to two findings across the phase-01 and phase-02 reports

**Verdict `substantiated` — but `refuted` as a phase-13 target.**

Enumeration of `^### VAL-` over `.ai/audit/99-validation/*.md`: phases 01 and 02 both use the flat
`VAL-` form and mint the same integers. Phases 03–14 use qualified forms. **The repair is explicitly
declared out of phase 13's write scope by the report itself** (`VAL-13-005` Recommendation), and the
brief forbids me editing any audit file. **Phase 13 owns nothing here; the set-wide namespace block owns it.**
Recorded so the Planner does not open a block for it.

### VAL-13-006 — PERF-001's client half is assigned to phase 13 and was never filed; FE-002 is a different concern

**Verdict `substantiated` — and it is the phase's largest hand-in. `dashboardApi.ts:69` is the defect the report does not name.**

| anchor | state at `ab76989` |
|---|---|
| the hook | `useAggregatedData(dashboardId, filters?, graphId?)` — `dashboardApi.ts:62-78`. `graphId?: string` `:65`. |
| the parameter **is** serialised | `:71-75` — `{ dashboard_id, graph_id: graphId, filters: JSON.stringify(filters) }` |
| **the query key omits it** | **`:69` `queryKey: ['aggregatedData', dashboardId, filters]`** — `graphId` is absent |
| the call site supplies two arguments | `DashboardView.tsx:45-49` — `useAggregatedData(id \|\| '', filters)` |
| the server accepts `graph_id` | `api/routes/data.py:53` `graph_id: UUID \| None = Query(default=None, …)`; the single-graph branch is `:118-160` |
| **the server half is not landed** | `data.py` has **no `LIMIT`** anywhere; the all-graphs loop `:166-195` iterates every graph unbounded. **PERF-001's server fix is still absent at `ab76989`.** |
| the invalidation key is *safe* | `dashboardApi.ts:86` `['aggregatedData', dashboardId]` is a **prefix**, so it covers per-graph entries. **Only the entry key is wrong** — exactly as `C11-8` states. |
| tests | **zero.** `DashboardView.test.tsx:52-77` and `filter-persistence.test.tsx:77-…` both `vi.mock('../api/dashboardApi')`. **`queryKey` is unreachable from any test** — `C11-8`'s "no test covers it" is confirmed. |

**The correctness trap, named.** Threading `graphId` into the hook **without** adding it to `:69` makes
every per-graph fetch collide on one cache entry: graph 2's response overwrites graph 1's, and
`DashboardView.tsx:189-198` maps `aggregatedData.graphs` by `key={graph.graph_id}` over a single-element
array — so the dashboard renders **one chart, silently, with no error**. `invalidateQueries` keeps working
(prefix), so nothing surfaces the collision. **A server `LIMIT` landing before the key is fixed turns a
CRITICAL performance finding into a silent correctness defect.** This is the case where "a frontend fix
disguises a backend correctness bug", in the direction the report itself warns about.

---

## 3. Cross-cutting architecture and constraints

### 3.1 The frontend as it exists

`src/` is 85 tracked files in five directories: `app/` (`providers.tsx` = QueryClient + Router + Theme +
Toaster + `ErrorBoundary`; `routes.tsx` = 9 routes, 7 lazy, 3 guards), `features/{auth,dashboards,upload,users,admin}/`
(each `api/ model/ ui/ index.ts`, dashboards adding `ui/charts/` and `__tests__/`), `shared/`
(`api/ components/ config/ hooks/ types/ utils/`, each with an `index.ts` barrel except `config/`, `types/`, `utils/`),
`main.tsx`, `react-plotly.d.ts`, `test/setup.ts` (**one line**: `import '@testing-library/jest-dom'`).

**Component tree on `/dashboard/:id`:**
`App → QueryClientProvider → BrowserRouter → ThemeProvider → CssBaseline → Toaster → ErrorBoundary(providers) → AppRoutes → Routes → AppLayout → TrailingSlashRedirect + Header(useAuth #1) + Outlet → ErrorBoundary(routes) → Suspense → ProtectedRoute(useAuth #2) → DashboardView(useDashboard, useAggregatedData, DashboardFilters, ChartRenderer, Suspense→UploadModal)`.

### 3.2 The `api` / `types` boundary and how it mirrors backend enums

`shared/types/enums.ts` is a hand-written mirror of `src/mkobi/models/enums.py`: 8 `as const`
objects + derived union types (`UserRole`, `DashboardPermission`, `GraphType`, `FilterType`,
`RegistrationStatus`, `UploadMode`, `ProcessingStatus`, `FileUploadStatus`) plus a 31-member
`ErrorCode` (`:79-122`). `erasableSyntaxOnly` forbids real `enum`. **The mirror is correct today** —
including `ErrorCode`, whose 31 keys match `shared/api/errorMessages.ts:13-54`'s 31 entries exactly,
which is what makes `getErrorMessage` total. `mapErrorCode` (`errorHandler.ts:118-123`) is the one
soft spot: an unrecognised server code degrades to `INTERNAL_ERROR` rather than surfacing.

`shared/types/api.types.ts` (327 lines, 30 interfaces) is **entirely hand-written**. Nothing is
generated from OpenAPI, nothing is validated at runtime (the one `zod` on the boundary,
`authToken.ts:7-12` `JWTPayloadSchema`, validates a JWT payload, not a response). `AGENTS.md` asks for
"share types via OpenAPI" — satisfied in form, not in substance. FE-007 is the chart-boundary
instance; the same gap holds for every other family and **no finding names it beyond FE-007**.

### 3.3 The error-extraction chain (5 layers, 6 message maps)

```
AxiosError
 └─ errorHandler.extractApiError            (errorHandler.ts:37)
     ├─ L1 legacy FastAPI 422 + errors[]    :46-54  → VALIDATION_ERROR + fieldMessages
     ├─ L2 RFC 7807 (code present)          :57-77  → mapErrorCode → ErrorCode
     │    └─ L3 code===VALIDATION_ERROR     :62-70  → extractFieldErrors :128-138
     ├─ L4 error.message                    :81-86  → INTERNAL_ERROR
     ├─ generic Error                       :90-95  → INTERNAL_ERROR
     └─ L5 fallback                         :98-101 → 'An error occurred'
        ↓
 getErrorMessage(code, featureMessages?, detail?)     (errorMessages.ts:70-92)
     feature map → shared map → detail → DEFAULT_ERROR_MESSAGE ('An error occurred', :59)
        ↓
 call sites:
   • axiosInstance.ts:132-135   toast.error(`${localized}: ${message}`)   ← 2nd arg NEVER passed
   • DashboardView.tsx:128     fixed string, no extractApiError
   • DashboardView.tsx:183     fixed string, no extractApiError
   • DashboardList.tsx:25      fixed string, no extractApiError
   • LogViewer.tsx:129         error.message inline (not the chain)
   • ChangePasswordPage / LoginForm / RegisterForm  (via useApiError, the one consumer of the feature tier)
```

**Six copies of the message surface:** `shared/api/errorMessages.ts` plus
`features/{admin,auth,dashboards,upload,users}/model/errorMessages.ts`. `getErrorMessage`'s
feature-map tier exists and is tested (`shared/api/__tests__/errorMessages.test.ts`) but the
interceptor — the only caller that matters for the toast class — **never passes it**. So FE-002's
"record the decision in `errorMessages.ts` or a sibling" has a **six-file** surface, not a one-file
surface, and `shared/hooks/useApiError.ts` is the hook that is supposed to be the per-feature consumer.

### 3.4 Query-key construction and invalidation

No key factory exists. Five hooks in `dashboardApi.ts` plus one inline `useQuery` in `LogViewer.tsx`
build five keys **by hand**:

| key | site | invalidated by |
|---|---|---|
| `['dashboards','my']` | `dashboardApi.ts:47` | **nothing** (no client mutation writes it) |
| `['dashboards', id]` | `:56` | `:84` `invalidateDashboard` |
| `['aggregatedData', dashboardId, filters]` | `:69` — **prefix-valid, `graphId` omitted** | `:86` `invalidateAggregatedData` (prefix ⇒ safe) |
| `['filterValues', dashboardId, filterName]` | `:93` | **nothing** — `VAL-13-003` |
| `['processingStatus', logId]` | `uploadApi.ts:47` | self-terminating via `refetchInterval` `:50-57` |
| `['admin','logs', appliedFilters]` | `LogViewer.tsx:51` | **nothing** |

Defaults: `providers.tsx:10-17` — `retry: 1`, `staleTime: 300_000`, **no `placeholderData`,
no `refetchOnWindowFocus` override, no `gcTime`**. Three hooks add `enabled: !!accessToken`
(`:49,:58,:76,:95`) fed by the reactive `useAuthToken()`. `LogViewer.tsx:50` adds **no `enabled`** and
no token gate — the one query that will fire unauthenticated.

Structural note: **`filters` is a JS object in the key** (`:69`). TanStack Query hashes keys
deterministically, so this is stable, but it means two logically-equal filter objects written in
different key order still hash equal — fine — while `JSON.stringify(filters)` at `:74` is a
**separate** serialisation of the same value that is *not* canonical. Two serialisations of one input,
one for the key and one for the wire.

### 3.5 Client-side gating vs server authority

The client's gates are **visibility, not control**. Verified independently (the validator's ruling,
re-derived):

| client gate | server counterpart |
|---|---|
| `DashboardView.tsx:133` `canEdit = ['edit','admin'].includes(dashboard.permission)` → Upload button `:142-149` | `api/routes/upload.py:241` `PERMISSION_DENIED` |
| `RoleBasedAccess.tsx:13` `roles.includes(user.role)` on `/admin` (`routes.tsx:105`) | all 10 admin routes take `admin_user: AdminUser` — `admin.py:46,73,110,148,241,291,317,374,428` |
| `ProtectedRoute.tsx:21-23` | every endpoint re-checks via dependencies |
| `ProtectedRoute.tsx:13-19` / `RootRedirect` `routes.tsx:48-54` `isLoading` gates | n/a |

`api/routes/data.py:88-102` re-checks `check_dashboard_access(..., required_permission="view", ...)`
and raises `ACCESS_DENIED` — **VAL-13-003's severity ceiling follows from this**: choosing a filter
value only narrows a chart already authorised for this user, so the stale filter list cannot escalate
privilege. **The CRITICAL band is genuinely empty and this is why.** The one structural weakness:
`Header.tsx:57` filters nav items on `user.role` and `ProtectedRoute.tsx:21` on `accessToken`, both
client-side — a viewer can *see* an Upload button they cannot use only if the server's `permission`
field says `edit`, which it derives server-side.

### 3.6 Shared seams with other phases — owner per seam

| seam | files | owner |
|---|---|---|
| **`C11-8`** — `PERF-001` client half; `dashboardApi.ts:69` `queryKey` omits `graphId` | `dashboardApi.ts:62-78`, `DashboardView.tsx:45-49`, `:215-220` | **phase 13** (per plan-11 `:2008`, `:265`); gated on plan-11 `DP-11-A` |
| `DP-11-A(c)` — truncation signal in the UI | same files + a response field | **phase 13**; the count field and `tests/test_openapi.py` are plan-11 `PRF-4`'s |
| `docs/07-frontend/pages.md:151` — documents `GET /data/aggregated` with `graph_id (optional)` | doc only | **phase 13** — plan-11 `:1079` says *raise the truncation requirement here, do not edit* |
| **`C04-4`** — `errorMessages.ts`, 4 `force_password_change` redirect sites, `adminApi.ts::retrieveTempPassword`, `UserManagement.tsx`, `RegistrationRequests.tsx`, `useAuth.ts`'s `RATE_LIMIT_EXCEEDED` branch | `frontend/src/**` | **phase 16**, not phase 13 (plan-04 `:614`, `:589`) — the report's *adjacency* FE-001 ↔ AUTH is real, the *hand-over* is not |
| **`DP-6`** (plan-07) — strict base scope for request bodies | `pyproject.toml` / `models/` + **a frontend field census** | **phase 07's own block `EB-5`** (plan-07 `:253,:387`) — the census is phase 07's Auditor task, **not** a hand-over to phase 13 |
| `DP-6` (plan-09) — worker row containment | `tests/conftest.py` | **phase 09** — note the **identifier collision**: two sibling plans both mint `DP-6` for unrelated decisions |
| `D-6` / `D-7` (plan-08) | `pyproject.toml`, `app.py`, six route modules | **phase 08 — both backend-only.** But `CQLT-4`'s Verification and Definition of Done require **`fe-lint` and `fe-test` to "stay green"** (plan-08 `:514,:515`) — **unsatisfiable at `ab76989`** |
| `TST-015` / `VAL-09-003` — the red `formSchemas.test.ts:162` | test file | **phase 09 owns the test; phase 13 owns the production fix** (`formSchemas.ts:56-59`) — confirmed by plan-09 `:835`, `:1022` |
| `TST-004` / `TST-014` — `vite.config.ts:56-65` thresholds, tracked `frontend/coverage/` | config + 15 tracked files | **phase 09**, hand-over labelled "phase 16" (plan-09 `:13,:213,:745`) |
| `TST-017` — `pyproject.toml:200-203` `slow`/`fast` **pytest** markers | `pyproject.toml` only | **phase 09's `TCO-4` (plan-09 `:745`)**. **There is no frontend half.** The plan-09 frontmatter's *"TST-017's frontend half (phase 16)"* is a mislabel: what phase 16 is handed is *frontend test coverage*, which comes from **TST-004** and **TST-014**. |
| `OPS-003` (phase 10) — served bundle is an untracked host dir | `frontend/dist`, `docker/Dockerfile`, `nginx.conf` | **phase 10**; adjacent to FE-005 |
| `AUTZ-001` / `AUTZ-003` (phase 12) — the 403 the client renders twice | `axiosInstance.ts:127-136` + `DashboardView.tsx:181-185` | **phase 12** owns whether the 403 should exist; phase 13 owns its double rendering |
| **phase 12's code-context (landed, `_code-context/12-…:154,:281`)** — *"three codes consumed today — **phase 13 must be told before the mapping moves**"*: `errorHandler.ts` switches on `code`; `features/admin/model/errorMessages.ts:7-13` (13 lines, 5 codes: `USER_NOT_FOUND`, **`PERMISSION_DENIED` `:9`**, `EMAIL_ALREADY_EXISTS`, **`VALIDATION_ERROR` `:11`**, `INVALID_TRANSITION`) | `features/admin/model/errorMessages.ts` + `errorHandler.ts:57-77,118-123` | **phase 13 (consume) before phase 12 (AUTZ-006 mapping moves)** — a one-way ordering, named in phase 12's own file |
| `AUTZ-006` — `ACCESS_DENIED` on graph collection paths | `routes.tsx` + dashboard screens are the 403 consumer — **UX, not a control** (`_code-context/12-…:68,:105`) | **phase 13 / 16 jointly** |
| Phase 16 — chart **presentation** contract | `ChartRenderer.tsx:15,17,18,149` (`xCol`/`metricCols`/`orientation`/`barmode` defaults), `convertChartLayoutToPlotly:80-119` | **phase 16** — `VAL-13-002`'s ruling hands phase 16 the *consequence*, not the fix |

---

## 4. In-flight and already-landed work

**Landed and intersecting this phase:**

| commit | symbol | effect on phase 13 |
|---|---|---|
| `ab76989` | `db/advisory_lock.py`, `workers/data_worker.py` | none directly; it changes *when* `aggregated_data` is rebuilt, i.e. **when** `['filterValues', …]` goes stale (`VAL-13-003`) |
| `c4c0b14` docs(process-architecture) | docs only | none |
| `5b23240` docs(audit) | added all 16 validated reports | the input under decomposition |
| `2de4156` refactor(auth) | `AuthService` approval transaction | upstream of `useAuth`'s login/refresh paths |

**Dirty and intersecting:** none of the four modified files touches `frontend/**`.
`docs/06-backend/configuration.md` is backend config prose.

**In flight elsewhere, touching phase-13 files:**

| owner | file it will edit | collision with |
|---|---|---|
| plan-08 `CQLT-4` | root `package.json` / `package-lock.json` (absent), `.ai/builders/**` | none in `frontend/src`, but its DoD asserts the frontend gates stay green |
| plan-04 | `frontend/src/**` **only** under `C04-4`, which it assigns to phase 16 | `errorMessages.ts`, `useAuth.ts` — **if `D-04-K` pulls the frontend in, it lands in phase 04 and pre-empts FE-001's 429 branch and FE-002's message surface** |
| plan-07 `EB-5` | `models/` + the frontend field census (read-only) | none |
| plan-09 `TCO-*` | `frontend/src/shared/types/__tests__/formSchemas.test.ts:162` under `VAL-09-003` | **if phase 09 edits `:162` before phase 13 changes `:56-59`, the red test turns green for the wrong reason and then breaks** |

---

## 5. Discrepancies and risks

### 5.1 Stale anchors (drift against the report)

| report anchor | actual | severity |
|---|---|---|
| FE-001 title "after five page reloads" | **six** (`security.py:127`) | LOW band already; changes the roadmap string |
| FE-001 "2 refreshes on `/dashboards`, 3 on `/admin`" | **`/` is 4** (`routes.tsx:46` `RootRedirect`) | the report named `RootRedirect` but never counted it |
| FE-010 "seven entry modules", six unreferenced | **nine barrels, eight unreferenced** (`charts/index.ts`, `Layout/index.ts`) | cosmetic; FE-004's remedy must publish from the right barrels |
| FE-004 "three credential consumers" | **four** with no permitted route — plus `useFilterValues` and `useInvalidateDashboard`, which `features/dashboards/index.ts` withholds | changes the barrel's export list |
| FE-006 `models/dashboard.py:58-64` "no character rule" | `:65` has it | **VAL-13-001**; Step 4 must be narrowed or it inverts the divergence |
| FE-003/validator `ErrorBoundary.tsx:40-44` | exact | — |
| `docs/07-frontend/fsd-structure.md:113,175,184-193` documents `PlaceholderPage` | **`PlaceholderPage.tsx` does not exist** (`Test-Path` → `False`); 10 lines of doc + a whole usage-guidelines section describe a dead component | `[DOC-UPDATE]` |
| `fsd-structure.md:63` "`dashboards/model/` (empty)" | contains `errorMessages.ts` | `[DOC-UPDATE]` |
| `fsd-structure.md:102-128` tree | omits `errorHandler.ts`, `errorMessages.ts`, `refreshHandler.ts`, `shared/config/`, `shared/hooks/{useApiError,useDebounce}.ts`, `shared/utils/formatDate.ts`, `test/setup.ts`, and all five per-feature `model/errorMessages.ts` | `[DOC-UPDATE]` |
| `fsd-structure.md:211` `charts/index.ts` = `PlotlyChart, ChartRenderer` | also exports `SkeletonChart` | `[DOC-UPDATE]` |
| `docs/07-frontend/architecture.md:105` describes the response interceptor as "on `401` … removes token, toast, redirect" | the interceptor has **six** branches; the **unconditional non-401/429 toast at `:127-136`** — FE-002's load-bearing half — is not documented at all | `[DOC-UPDATE]`; this is the doc FE-002's decision should land in |
| `AGENTS.md` / `.kilo/rules/project.md` §9 "avoid `any` completely" vs `react-code-standards.md:11` "unless absolutely necessary and explicitly justified" | two rules of different strength, **neither enforced** | `[DOC-UPDATE]` |

### 5.2 Refuted recommendations

| recommendation | why it cannot be executed as written |
|---|---|
| FE-006 Roadmap **Step 4**: "drop or serverise the uppercase and **name-character** rules" | the server **enforces** the name-character rule (`dashboard.py:65`). Executing it literally **inverts** a closed divergence into a reachable 422. **`VAL-13-001`.** |
| FE-006: "add the uppercase rule to `validate_password_or_raise`" | edits `src/mkobi/utils/validators.py` — a **backend** file — from a client finding, changing `change_password` for **every** caller including admin resets. Scope leak. |
| FE-002 / Step 0 Rollout Safety: "render one such dashboard and confirm the intended chart appears" | **a chart *does* appear** in the broken case. The check must be a **trace-count / axis-category** assertion. **`VAL-13-002`.** |
| FE-010: "either adopt the remaining six barrels or delete them" | there are **eight**; and `features/dashboards/index.ts` **withholds two consumed symbols**, so "adopt as-is" would publish *less* than consumers can reach. |
| FE-003: "route the report through `axiosInstance`" without naming the class-method constraint | `reportError` is a `private` method on a `React.Component` — no hooks. |
| phase 08 `CQLT-4` DoD: "`fe-lint` and `fe-test` stay green" | **both are red at `ab76989`.** Unsatisfiable today. |

### 5.3 Contested ownership

1. **FE-007 ⇄ phase 16.** The validator ruled FE-008 → phase 13 and left the *consequence*
   (`convertToPlotlyData`'s presentation defaults at `ChartRenderer.tsx:15,17,18,149`, and the dead
   `convertChartLayoutToPlotly:80-119`) to phase 16. **Both halves are one function.** If phase 16
   touches `convertToPlotlyData` while phase 13 deletes `:21-23` inside it, two owners, one function.
2. **FE-004 + FE-010 ⇄ phase 16 (`C04-4`).** Phase 16 would own `errorMessages.ts` (FE-002's decision
   surface) and `useAuth.ts`'s `RATE_LIMIT_EXCEEDED` branch (FE-001's 429 branch) — **the two exact
   lines phase 13 must change.** Phase 04 explicitly reserves them (`plan-04:589`). **Unresolved.**
3. **FE-001 ⇄ phase 04 (`AUTH`, refresh-cookie rotation).** Real adjacency; distinct files. But
   `C04-4`'s reservation of `useAuth.ts`'s 429 branch overlaps FE-001's remedy verbatim.
4. **`TST-015` ⇄ FE-006.** Phase 09 owns the test at `formSchemas.test.ts:156-163`; phase 13 owns
   `formSchemas.ts:56-59` which turns it green (`_code-context/09-…:234` names the governing server path
   `models/auth.py:178,205,207`). Correctly split, but **sequenced wrongly if either moves alone.**
5. **Phase 12 → phase 13, one-way.** Phase 12's code-context `:154,:281` requires phase 13 to be told
   **before** AUTZ-006's error-code mapping moves, because `errorHandler.ts` switches on `code` and
   `features/admin/model/errorMessages.ts:9,:11` are the consuming side. **Phase 13 owns no edit here;
   it owns the notification.**
6. **`VAL-13-005`** — the `VAL-` namespace collision is explicitly **not phase 13's**. No block.

### 5.4 Tests that will break

| test | breaks when | how |
|---|---|---|
| `DashboardView.test.tsx:59,65` fixtures | FE-007's remedy | fixtures are `[{x:[…],y:[…],type:'bar'}]` — Plotly traces, not row dicts; incompatible with `Array<Record<string, string\|number>>` under `verbatimModuleSyntax` |
| `filter-persistence.test.tsx:79-…` fixture | same | same shape |
| `DashboardView.test.tsx:52-77`, `:75` (`isLoading: false, error: null`) | FE-002's remedy | mocks carry **no `isFetching`**. Switching `isLoading`→`isFetching` makes `dataLoading` `undefined`; `DashboardView.tsx:201`'s `!dataLoading` guard flips truthy. Tests still pass (nothing asserts the skeleton) — **so the breakage is silent.** |
| `formSchemas.test.ts:86-89` | FE-006 Step 4 | the test name says 500, the schema says 200; renaming/correcting it is a **named blocker** on the roadmap |
| `formSchemas.test.ts:162` | FE-006 Step 4 | turns **green** — `fe-test` 170/0 |
| `useAuth.test.tsx`, `ProtectedRoute.test.tsx`, `RoleBasedAccess.test.tsx`, `authFlow.test.tsx`, `errorHandler.test.ts`, `errorMessages.test.ts`, `enums.test.ts`, `PlotlyChart.test.tsx`, `authToken.test.ts`, `FileDropzone.test.tsx` | FE-001/003/004/007/010 | all mock their subjects; FE-004's barrel repointing changes `ProtectedRoute.test.tsx:26` and `RoleBasedAccess.test.tsx:10` **if** the barrel's export names change |
| **`queryKey` / `useFilterValues`** | VAL-13-003, `C11-8` | **no test exists at any level.** Both need a *new* test, not a fixed one. |

### 5.5 Where a frontend fix could disguise a backend correctness bug

1. **★ `dashboardApi.ts:69` `queryKey` omits `graphId` (VAL-13-006 / `C11-8`).** Threading `graphId`
   into the hook without adding it to the key makes every per-graph fetch **collide on one cache
   entry**; `DashboardView.tsx:189` maps `key={graph.graph_id}` over a **one-element** array, so the
   dashboard renders **one chart, silently**, with no error, no toast and no console message. If
   PERF-001's server `LIMIT` lands first, the symptom a user sees is *"my dashboard lost a chart"* —
   and the natural response is to look at the server, not the key. **This is the single highest-risk
   item in the phase** and the only one where the failure mode is a **wrong number on screen**.
2. **`data.py` has no `LIMIT` at `ab76989`.** A frontend-only "render partial graph set" change would
   then signal a truncation that the server is not performing — a fix for a bug that does not exist
   yet, and a mask on the one that does.
3. **`GraphDataResponse.data` is `list[dict[…]]`; the client declares `Data[]`.** Any FE-007 remedy that
   narrows the *server* type to match the client's declared trace shape would make the double cast
   honest and the pipeline wrong.
4. **`'x' in row && 'y' in row` (§ FE-008) is a silent-wrong-render, not a loud failure** — the same
   class: the screen shows a *plausible* chart. Combined with (1), a phase that "verifies charts render"
   catches neither.
5. **`updateDashboardSchema.name:39` has no regex/min-3 while `DashboardUpdate.name:139` has no bound.**
   The client is stricter, so nothing breaks — but a future server-side `validate_name` on the update
   path would silently introduce a 422 the client already prevents. Cheap to align now.

---

## 6. Decision points for the Planner

Genuine technical uncertainty only. **No option is chosen here.**

| # | question | alternatives | chooser |
|---|---|---|---|
| **DP-13-A** | **Is `fe-lint` in or out of scope for phase 13?** It is red (9 errors) *before* any phase-13 edit, and 3 of the 9 are in `ChartRenderer.tsx:86,90,98` — a function no finding names. | (a) delta-gate only: record the 9 and require "no new error"; (b) own the 3 `ChartRenderer` errors and land `fe-lint` green as part of this phase; (c) own all 9; (d) declare `fe-lint` not-a-gate for this phase and rely on `fe-test` | **Tech Lead** (it collides with plan-08 `CQLT-4`'s "must stay green") |
| **DP-13-B** | **Does the `queryKey` fix land with `graphId` threading, or before it?** | (a) one commit: `graphKey = ['aggregatedData', dashboardId, graphId, filters]` + thread `graphId` together; (b) key-only first, threading second; (c) abandon per-graph fetching for a total-count signal | **Planner**, hard-ordered against plan-11 `DP-11-A` |
| **DP-13-C** | **How does the client signal truncation?** | (a) fixed `Alert` when `graphs.length < config.charts.length`; (b) a count field from the server (plan-11 `DP-11-A(c)`) rendered as "showing N of M"; (c) per-graph `useQuery` with `isError` per card | **Planner + plan-11's `DP-11-A`** |
| **DP-13-D** | **FE-002: which surface survives the class — toast or inline?** | (a) drop the interceptor toast for codes a surface renders inline; (b) drop all inline `<Alert>`s and keep the toast; (c) keep both, label the stale frame | **Tech Lead** — the report calls it a judgement call and the answer changes `errorMessages.ts` (6 files) |
| **DP-13-E** | **FE-001: where does the single boot refresh live?** | (a) module-scope `bootPromise` in `useAuth.ts`; (b) `app/providers.tsx` effect before routes; (c) demote `authToken.ts` to `shared/auth/` and own the session there | **Planner**; (c) is FE-004's alternative and the two interact |
| **DP-13-F** | **FE-004: publish upward, or demote the credential store?** | (a) add `useAuthToken`/`getTokenWithExpirationCheck`/`setToken`/`removeToken`/`logout` + `useFilterValues`/`useInvalidateDashboard` to the barrels; (b) move `authToken.ts` to `shared/auth/`; (c) both barrels and `docs/07-frontend/fsd-structure.md` rewritten to match | **Tech Lead** — (b) is smaller and is the only option that removes the class |
| **DP-13-G** | **FE-005 + FE-003: is the API base configurable?** | (a) delete `REQUIRED_ENV_VARS` + `validateEnv` + the `main.tsx:7` call, keep the literal, delete `ErrorBoundary`'s second literal; (b) wire `VITE_API_URL` in `axiosInstance.ts:9`, set it in `docker/Dockerfile`, have `ErrorBoundary` import the base | **Tech Lead + phase 10 (`OPS-003`)** — (b) makes the Docker frontend build a phase-13 dependency |
| **DP-13-H** | **FE-006 `new_password`: which side moves?** | (a) drop `.regex(/[A-Z]/)` from `formSchemas.ts:58`; (b) add the uppercase rule to `utils/validators.py` (**backend file**); (c) leave it and re-grade | **Tech Lead** — (b) is a backend edit inside a client finding and touches admin resets |
| **DP-13-I** | **FE-006 update-`name`: newly named divergence, in or out?** | (a) align `formSchemas.ts:39` to `DashboardCreate`'s 3..100 + regex and add the server-side validator to `DashboardUpdate`; (b) align client to server (drop min-3 and the regex — server enforces nothing); (c) leave it, record only | **Planner** — no finding requires it; it is unnamed |
| **DP-13-J** | **FE-007: what replaces `Data[]`, and what happens to `convertChartLayoutToPlotly`?** | (a) `Array<Record<string, string \| number>>` + delete both casts + **delete the dead layout converter** (the server never sets `layout`); (b) as (a) but keep the converter for a future server field; (c) generate `api.types.ts` from OpenAPI | **Planner + phase 16** — (a) touches phase 16's material |
| **DP-13-K** | **FE-008's rollout evidence, given no browser run?** | (a) add a vitest assertion on `convertToPlotlyData`'s **trace count and x categories** for a fixture with `x`/`y` column names; (b) a Playwright render check; (c) rely on the trace-count test alone and label the pixel artefact unsettled | **Planner** — (a) is the only automated option and is the one `VAL-13-002` demands |
| **DP-13-L** | **FE-010: adopt or delete the eight unreferenced barrels?** | (a) repoint consumers at barrels (largest diff, largest enforcement); (b) delete the unreferenced ones, keep `features/auth` and `Layout`; (c) delete all, keep concrete paths, and rewrite `fsd-structure.md` | **Planner** — (b)/(c) change the documented FSD contract |
| **DP-13-M** | **Does `VAL-13-005` (the `VAL-` namespace collision) get a phase-13 block?** | (a) no — the set-wide namespace block owns it, as the report says; (b) yes, as a one-line coordination note | **Coordinator.** The report rules (a); the brief forbids editing audit files either way. |
| **DP-13-N** | **Does phase 13 fix `docs/07-frontend/` (dead `PlaceholderPage`, missing files, the `:105` interceptor description) or leave it to phase 16?** | (a) phase 13 corrects `fsd-structure.md` + `architecture.md:105` as part of FE-004/FE-010's doc impact; (b) hand to phase 16 | **Tech Lead** — `doc-maintenance-rules.md` requires docs to follow the code |

---

## 7. Coverage ledger

| ID | verdict | evidence anchors (all read at `ab76989`) |
|---|---|---|
| `FE-001` | **substantiated** (mechanism) · **stale** (headline: six, not five) · **drifted** (4 instances on `/`, not 2–3) | `useAuth.ts:14,64-101,87-90,122` · `authToken.ts:66,74,134,179,196` · `Header.tsx:21` · `ProtectedRoute.tsx:10,21-23` · `RoleBasedAccess.tsx:11` · `routes.tsx:46` · `auth.py:314-315` · `security.py:127,133` · `axiosInstance.ts:62-64` · `useAuth.test.tsx:36` |
| `FE-002` | **substantiated** | `axiosInstance.ts:55-139,127-136,132-135` · `errorHandler.ts:37-102` · `errorMessages.ts:13-54,70-92` · `providers.tsx:10-17` · `DashboardView.tsx:125-131,177-198` · `DashboardList.tsx:22-28` · `LogViewer.tsx:50-53,64-71,127-142` · `DashboardFilters.tsx:127-130` · `errorHandler.test.ts`, `errorMessages.test.ts` |
| `FE-003` | **substantiated**; consequence (2) **stale** (endpoint declares anonymity) | `axiosInstance.ts:8-15,18-30` · `ErrorBoundary.tsx:24-30,32-45` (2 mounts: `providers.tsx:43`, `routes.tsx:79`) · `client_errors.py:28` · `refreshHandler.ts:1-9` |
| `FE-004` | **substantiated**; **understated** (4 credential symbols + 2 withheld dashboard hooks) | `axiosInstance.ts:3` · `Header.tsx:4` · `dashboardApi.ts:3` · `userApi.ts:3` · `DashboardView.tsx:20` · `features/auth/index.ts` (3 lines) · `features/dashboards/index.ts` (withholds `useFilterValues`, `useInvalidateDashboard`) · `fsd-structure.md:151,153,165` · 4-hit barrel grep |
| `FE-005` | **substantiated** | `env.ts:5,13-30` · `main.tsx:7,9` · `axiosInstance.ts:9` · `vite.config.ts:9-14` · `Dockerfile:22` (ARGs only at `:31,51,66,85`) · `authToken.ts:74` · `providers.tsx:48` · `ErrorBoundary.tsx:25` · `ErrorPage.tsx:11` · `frontend/dist/assets/index-CP3NT1Oa.js` |
| `FE-006` | **substantiated** 3/4 rows · **refuted** 1 row (`VAL-13-001`) · **1 further divergence unnamed** (`updateDashboardSchema.name`) | `formSchemas.ts:3,17,25-30,31,39,40,47-48,56-59` · `dashboard.py:54,58-67,65,139,140` · `validators.py:183-203` · `dashboard_service.py:262` · `formSchemas.test.ts:86-89,97-117,162` · `DashboardManagement.tsx:59-62` |
| `FE-007` | **substantiated**; **understated** (`layout` is dead on the server path) | `api.types.ts:2,203-216,207,209-215` · `data.py:59,73,425-436,435` · `ChartRenderer.tsx:5,48,70,80-119,124` · `TableChart.tsx:5` · `DashboardView.test.tsx:52-77,59,65` |
| `FE-008` | **substantiated** (mechanism/reachability/remedy) · **refuted** (asserted cause, `VAL-13-002`) · **verification must change** | `ChartRenderer.tsx:15,17,18,21-23,26,28-43,45-65,128-134,142,149,155` · `PlotlyComponent.tsx:20-26,34` · `DashboardView.tsx:190-197` · `package.json:25,27` · `DashboardView.test.tsx:59,65` |
| `FE-009` | **substantiated**; band LOW upheld | `Header.tsx:24,87-89,97-105` · `DashboardFilters.tsx:134-148,152-177,186-193,198-209,40-43` · `AppLayout.tsx:12-20` · `routes.tsx:59-137` · `FileDropzone.tsx` · `ConfirmDialog.tsx` · `TableChart.tsx:40-58` · `providers.tsx:19-23` (**no theme tokens**) · `ChartRenderer.tsx:130` (Tailwind class string) |
| `FE-010` | **substantiated**; count **drifted** (9 barrels, 8 unreferenced) | 9 barrels read in full · `ProtectedRoute.tsx:3` · `RoleBasedAccess.tsx:1` · `ProtectedRoute.test.tsx:26` · `RoleBasedAccess.test.tsx:10` · `routes.tsx:6` · `git ls-files frontend/src` = 85 |
| `VAL-13-001` | **substantiated** — removes the name-character half of Roadmap Step 4 | `dashboard.py:58-67` (regex `:65`, message `:66`) vs `formSchemas.ts:28-30` |
| `VAL-13-002` | **substantiated** — changes FE-008's rollout verification | `ChartRenderer.tsx:21-23` · `plotly.js-dist-min ^3.5.1` `package.json:25` (`dflt:"scatter"`) · `DashboardView.tsx:190-197` |
| `VAL-13-003` | **substantiated** — new phase-13 target, zero test coverage | `dashboardApi.ts:90-97` (key `:93`) · `DashboardFilters.tsx:126-130` · `DashboardView.tsx:215-220` · 5 `invalidateQueries` sites enumerated · `data.py:483-491` vs `api.types.ts:150-153` (types match) · `DashboardView.test.tsx:28-30,38` · `filter-persistence.test.tsx:35-57,60` |
| `VAL-13-004` | **substantiated** — six, not five; `/` is three, not six | `security.py:127,133` vs `auth.py:315` · `useAuth.ts:14,66-69` |
| `VAL-13-005` | **substantiated but out of scope** — no phase-13 block | `^### VAL-` enumeration across `.ai/audit/99-validation/*.md` (phases 01, 02 flat; 03–14 qualified) |
| `VAL-13-006` | **substantiated** — the phase's largest hand-in | `dashboardApi.ts:62-78`, **key `:69` omits `graphId`** · `DashboardView.tsx:45-49` · `data.py:53,118-160,166-195` (**no `LIMIT` at `ab76989`**) · `plan-11:2008,265,369` (`C11-8`) · `DashboardView.test.tsx:52-77` |

**Symbols the report names that do not exist today:** `PlaceholderPage.tsx`
(`fsd-structure.md:113,175,184-193`) — no such file and no such import anywhere in `frontend/src`.
**No `FE-*` or `VAL-13-*` identifier names a non-existent symbol**; every symbol in §2 resolves.