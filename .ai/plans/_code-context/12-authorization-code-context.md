---
phase: 12-authorization
role: code-context (Phase-1 Auditor)
report: .ai/audit/99-validation/12-authorization-validated-findings.md
phase_findings: .ai/audit/12-authorization/findings.md
finding_prefix: AUTZ-     # verified: `### AUTZ-` appears only in .ai/audit/12-authorization/findings.md
validation_prefix: VAL-12- # phase-qualified; flat `VAL-` is occupied by phases 01-11
findings: 9 (AUTZ-001 … AUTZ-009, no gaps)
report_defects: 5 (VAL-12-001 … VAL-12-005)
source_head: ab76989
report_baseline: 7342e9e
read_at: working tree, 2 production files dirty (see §4)
method: static read + read-only docker compose config; no live HTTP probes, no state mutation
status: context only — no remediation designed, no approach chosen
---

# Phase 12 — Authorization: Code Context

## 1. Scope and method

### What was read

| Artefact | Use |
|---|---|
| `.ai/audit/99-validation/12-authorization-validated-findings.md` (1010 lines) | The report under decomposition. All 9 `AUTZ-` + 5 `VAL-12-` blocks read in full. |
| `src/mkobi/core/permissions.py` (353) · `src/mkobi/api/deps.py` (890) · `src/mkobi/db/repositories/access_repo.py` (259) · `src/mkobi/db/models/access.py` (86) | The two authorities and the grant storage. |
| `src/mkobi/api/routes/dashboards_access.py` (227) · `dashboards_filters.py` (161) · `dashboards_graphs.py` (181) · `graphs.py` · `data.py` (220) · `upload.py` · `admin.py` (439) · `app.py` (460) | Every route an `AUTZ-` finding names. |
| `src/mkobi/services/dashboard_service.py` · `user_service.py` (372) · `data_service.py` · `db/session.py` · `db/models/dashboard.py` | Service and session seams. |
| `.ai/plans/01-…` … `11-…-remediation*.md` | Frontmatter + every `C04-5`, `C10-11`, `D-4`, `C08-*`, `DP-10-8`, `HO-2/3/4`, `C11-*` row naming phase 12. |
| `docs/08-security/access-control.md` · `docs/SPEC.md` · `tests/test_dashboard_access.py` · `tests/test_resource_access_control.py` | The rule as documented, and the tests that pin current behaviour. |

### How claims were verified

| Method | Used for |
|---|---|
| **Direct file read** | Every mechanism claim. 8 of 9 `AUTZ-` findings re-anchored line-for-line against the working tree. |
| **Repository-wide search** (`grep` over `src/`) | `is_active` (23 hits, **1 read**), `required_permission=` (**21** sites), `user_tokens_revoked` (**2** sites), `check_dashboard_access` call sites, `get_current_user` importers. |
| **Static reading, not execution** | The 200/403/500 responses, the 422 `ValueError` mapping, the `str(e)` health branch. No HTTP probe was run. Docker was used **read-only** (`compose config`) and no container was started, stopped or reconfigured. |
| **Refuted by reading** | Phase 08's "only caller of `AccessRepository.grant_access`" (there are two — its own `VAL-08-005` already caught this). |

### HEAD vs worktree

`HEAD` = `ab76989`. The report's baseline is `7342e9e`; **26 commits** separate them, and three of them moved anchors this phase names. Dirty tree: `src/mkobi/db/advisory_lock.py`, `src/mkobi/workers/data_worker.py` (+ two test files, one doc). **Neither dirty production file is on an authorization path** — they are the phase-03 `B2` advisory-lock work. Files on disk are treated as truth throughout; §4 records the split.

---

## 2. Per-finding context

### AUTZ-001 — Any authenticated principal reads any dashboard's ACL and deletes any grant (CRITICAL)

**Verdict: `substantiated`.** Unchanged in the working tree, and the report's zero-blocker check is confirmed.

| Seam | Anchor (verified) |
|---|---|
| Routes | `dashboards_access.py:31-127` grant, `:130-171` list, `:174-227` revoke. All three declare `current_user: CurrentUser` (`:41`, `:139`, `:184`) and **none reads it** — the bodies never reference the name. |
| Gate | **None installed.** No `dependencies=[...]`, no `Depends(require_dashboard_*)` anywhere in the file. Imports are only `CurrentUser`, `get_db_dependency`, `get_dashboard_service` (`:14-18`). |
| Service | `DashboardService.get_dashboard_access_list(dashboard_id, db)` (`dashboard_service.py:442-478`) and `revoke_access(dashboard_id, user_id, db)` (`:403-440`). No acting-identity parameter. |
| Repository | `AccessRepository.revoke_access(user_id, dashboard_id, db)` (`access_repo.py:89-130`) resolves by the bare pair and `db.delete(access_obj)` (`:115`). |
| DB | `dashboard_access` (`db/models/access.py:22-75`): composite PK `(user_id, dashboard_id)` (`:68-72`), `permission` is a native PG enum `dashboard_permission_level` (`:43-52`). |
| Ownership | `dashboards.created_by` (`db/models/dashboard.py:68-72`, index `:37`) — written once at `dashboard_service.py:88`, read by **nothing**. Three `created_by` hits over `src/`, all accounted for. |
| Existence | `get_dashboard_access_list` calls `access_repo.get_by_dashboard` and returns `[]` on zero rows; there is no `dashboard_repo.get`. Hence `200 []` for a non-existent dashboard — the report's addition, confirmed. |
| Candidate gate | `require_dashboard_admin_access` (`deps.py:791-832`) → `check_dashboard_access(required_permission="admin")` (`:817-821`). Exported (`:57-60`), currently **unused on these three paths**. |

**Seams an implementor touches:** the three route decorators (add `dependencies=[Depends(require_dashboard_admin_access)]` or swap the parameter), the module docstring (`:4` "All operations require admin role") and the three `description` strings (`:35`, `:135`, `:178`) which currently assert a rule nothing enforces, `DashboardService.grant_access`'s `ValueError`→422 mapping (`dashboard_service.py:377-379` via `dashboards_access.py:110-115`) if the absence case is normalised with it, and the ACL-read absence behaviour.

**Tests that pin current behaviour: none.** `tests/test_dashboard_access.py` contains exactly one test, `TestDashboardAccessCascadeDelete::test_dashboard_access_cascade_delete` (`:13-19`), exercising the cascade through `DELETE /dashboards/{id}`. `tests/test_resource_access_control.py` covers `PUT`/`DELETE /dashboards/{id}` only (`TestResourceAccessControlUpdate:17`, `TestResourceAccessControlDelete:167`, `TestDashboardOwnerAccess:314`, `TestAccessControlListChecked:407`). **All four classes must stay green unmodified** — they are the only shipped proof the admin bypass survives.

**Docs describing the rule:** `docs/08-security/access-control.md:140-146` ("Access Management Endpoints", stating "Admin only / Revokes access"), `docs/SPEC.md:123` (admin bypass) and `:124` (403/404 dual-signal). **Frontend:** the SPA has no access-management surface; `RoleBasedAccess` (`frontend/src/shared/components/RoleBasedAccess.tsx`, routed at `app/routes.tsx:105`) gates `/admin` on role only. It is UX, not a control.

---

### AUTZ-002 — Filter binding is rewritten by any authenticated principal (CRITICAL)

**Verdict: `substantiated`.** Anchors resolve exactly; the report's corrected inference is confirmed by reading.

| Seam | Anchor (verified) |
|---|---|
| Routes | `dashboards_filters.py:32-79` bind, `:82-127` unbind. Both declare `current_user: CurrentUser` (`:42`, `:90`), neither reads it. `no check_dashboard_access call exists in the file` — confirmed. |
| The one predicate | `:140` `current_user: UserRead = Depends(require_dashboard_read_access)` on the **GET** endpoint only. |
| Declared contract | Module docstring `:4` "All operations require admin role"; descriptions `:36`, `:86` "Requires admin role". Not enforced on either mutating path. |
| Asymmetry | `bind_filter_endpoint` **does** check filter existence (`:54-58`, `FILTER_NOT_FOUND`); the dashboard is never resolved. The unbind path never resolves `dashboard_id` at all. |
| 500 mechanism | `dashboard_filters.dashboard_id` FK `ondelete="CASCADE"` (`db/models/filters.py:87`, non-deferrable), surfaced by `except Exception` at `:68-79` → `INTERNAL_ERROR`. Existence oracle, not an authorization proof — as the report says. |
| Service | `DashboardFilterRepository.bind_filter` / `unbind_filter` take identifiers only. |
| Existence-check precedent | `services/data_service.py:106-116` raises `AppException(DASHBOARD_NOT_FOUND)` — the shape the report points at to copy. |
| Candidate gate | `require_dashboard_admin_access` (`deps.py:791-832`), same as AUTZ-001. |

**Seams:** the two mutating decorators, the module docstring and two `description` strings, and — separately — the absence of a dashboard-existence check (which also removes the 200/500 oracle). **Tests:** none name this module's mutating paths. **Docs:** `access-control.md:126-131` "Filter Endpoints" states an auth level the mutating rows do not enforce.

---

### AUTZ-003 — Two authorities decide the same question and disagree (HIGH)

**Verdict: `substantiated`, with one refinement the report does not have.** The report's resolved direction (the grant is de facto authoritative for chart lifecycle) is confirmed by reading; the count of `check_dashboard_access` sites in `graphs.py` is **four**, and one of the five graph operations uses a *third* mechanism.

| Seam | Anchor (verified) |
|---|---|
| Gate A (grant) | `check_dashboard_access` → `_check_access_with_session` (`permissions.py:125-155`, `:158-246`); admin bypass at `:179` returns `True` before any grant is read. |
| Gate B (role) | `require_admin_role` (`deps.py:585-609`) → `check_role` (`permissions.py:86-122`) over `ROLE_HIERARCHY` (`:35`). Grants on `role==ADMIN` **alone**. |
| Installed at | `dashboards_graphs.py:56` `dependencies=[Depends(require_admin_role)]` on `POST /{dashboard_id}/graphs` — the **only** endpoint in the file with it; its twin GET at `:151` uses `require_dashboard_read_access`. `upload.py:75` `current_user: EditorUser` (`require_editor_role`, `deps.py:612`). |
| The other four | `graphs.py:96-101` create (`admin`), `:245-250` read (`view`), `:333-338` update (`admin`), `:443-448` delete (`admin`). **A fifth mechanism at `:174-186`**: the list endpoint branches on `current_user.role != UserRole.ADMIN` inline and calls `AccessRepository().get_user_dashboards` — it never calls `check_dashboard_access` at all. |
| Service | `data_service.py:118-132` re-checks `required_permission="edit"` for the upload path, so `upload.py` enforces **both** authorities; `dashboards_graphs.py` enforces only the role. That asymmetry is why the live `POST /upload` 403 reads "Editor access required" while the nested chart create reads "Admin access required". |
| Set difference | `{dashboard_access=admin ∧ users.role≠admin}` — admissible only by the grant gate, refused only by the role gate. Direction is determinate: the divergence can only **refuse** a legitimate dashboard administrator. Never an escalation. |
| Precedence in docs | **Absent.** `access-control.md:65-84` describes roles and permissions and the admin bypass but never says which wins; `SPEC.md:123` states the bypass without ordering. No file in `docs/` resolves it. |

**Seams:** `dashboards_graphs.py:56` → the grant dependency; `upload.py:75` → `EditorUser` vs a grant; `graphs.py:174-186` → the un-named third mechanism (a collection-shaped question `require_dashboard_read_access` cannot answer, since it takes a `dashboard_id` path parameter — phase 08's `CQLT-3` names the same code). **Docs:** `SPEC.md` needs the precedence written down; `access-control.md:133-138` "Graph Endpoints" currently states the rule the two gates disagree about. **Frontend:** `app/routes.tsx` and the dashboard screens call the nested routes, so the frontend is the consumer of the 403 — this is phase 13/16's surface, not a control.

---

### AUTZ-004 — `/data/aggregated` resolves `graph_id` unconstrained to the authorised `dashboard_id` (HIGH)

**Verdict: `substantiated`.** The load-bearing claim — the *data* is correctly constrained, only the graph row crosses — is confirmed.

| Seam | Anchor (verified) |
|---|---|
| Route | `data.py:39-197` (the file is 220 lines; the endpoint body ends at `:220`). Single authorization decision at `:88-93` against the `dashboard_id` **query parameter**. |
| The gap | `:120` `single_graph = await graph_repo.get(id=graph_id, db=db)` — no constraint against `dashboard_id`. `:122` is the `if single_graph is None:` branch, and `GRAPH_NOT_FOUND` is raised at `:124-127`, immediately below. |
| Disclosed fields | `GraphDataResponse(type=single_graph.type, name=single_graph.name, config=single_graph.config)` (`:152-158`) — the exact three fields the report names. `data` comes back `[]`. |
| Why it is not higher | `data_service.py:208-210` passes `dashboard_id=dashboard_id` into `agg_repo.get_by_graph_id`, which filters on both columns (`aggregated_data_repo.py:147-155`). Verified. |
| Control case | `:163` `graph_repo.get_by_dashboard_id(dashboard_id, db)` for the no-`graph_id` path — correctly scoped, so the response is not echoing. |
| Error code | `GRAPH_NOT_FOUND` already exists; no new `ErrorCode` member is needed. |

**Seams:** one conditional at `data.py:120-122` comparing `single_graph.dashboard_id` to the authorised `dashboard_id`. **Tests:** `tests/test_data_service.py` exists and `tests/test_upload_api.py` was touched by drift, but nothing asserts the cross-dashboard `graph_id` case. **Docs:** `access-control.md:110-116` states "Validates dashboard access before returning data" — true, and silent on the child-lookup scope.

---

### AUTZ-005 — Deactivation reports success, does not deactivate, cannot be undone (HIGH)

**Verdict: `drifted` — one half now landed, the other two halves are confirmed still open.** This is the finding the working tree has moved furthest on.

| Half | Report's claim (at `7342e9e`) | State at `ab76989` | Anchor |
|---|---|---|---|
| (a) write does not persist | `user_service.py:248-284` returns without committing; `admin.py:137-193` does not commit; `db/session.py:85-87` closes without commit | **`already-fixed`** by `2174895` ("own the unit of work for user writes"). | `user_service.py:259` (`update_user_role`) and `:301` (`update_user_active_status`) both `await db.commit()`. Docstrings at `:241-242`, `:282-283` now state the commit contract. `admin.py:177-178` and the class docstring rely on it. |
| (b) `user_tokens_revoked` never cleared | key appears only at `core/security.py:535` (`setex`) and `:552` (`exists`) | **`substantiated` — unchanged.** Still two sites, no `delete` anywhere. | `security.py:522-539` `revoke_all_user_tokens` writes; `:542-554` `is_user_tokens_revoked` reads. `admin.py:192-214` calls the write **only when `not user_data.is_active`**. The reactivate branch has no `else`. |
| (c) `is_active` read nowhere useful | read in exactly one place, `deps.py:544` | **`substantiated`, anchor shifted +3.** | `deps.py:547` is still the **only** read of `user.is_active` in `src/`. `auth_service.py` has **no** reference to `is_active`; `auth.py:358-375` (`/auth/refresh`) checks `is_user_tokens_revoked` (`:368`) and the refresh-jti blacklist, never `user.is_active`. |

**Net effect today — the finding's *shape* inverted.** With (a) landed, deactivation now persists and `deps.py:547` genuinely refuses. The permanent-lockout half is now *worse in a different way*: reactivation flips the column but cannot clear the Redis marker, so the account authenticates successfully and every token it receives is refused. The `admin.py:153-167` docstring **states this deliberately** — "the login routes consult neither `is_active` nor the marker, so a deactivated user can still obtain freshly signed tokens at login, but each of those is then rejected at the gate" — and frames the Redis marker as the authority for `/auth/refresh` and the gate. That docstring is the load-bearing artefact for whoever rules (b) and (c).

**Seams:** `user_service.py` (a — done), the reverse-path key deletion in `admin.py:192-214` (b), `auth_service.py::login_user` and `auth.py::refresh` (c). **Tests:** `tests/test_admin_user_management.py` and `tests/test_token_revocation.py` were **rewritten by `2174895`** (367 and 124 changed lines) and `cea2d06` added cleanup — the report's "no shipped test names `update_user_active_status`" is **no longer true**. Read those two modules before designing (b) or (c). **Docs:** `access-control.md:157-167` "Admin Endpoints"; `admin.py`'s own docstring.

---

### AUTZ-006 — One refusal, three error codes, two disclosure levels (MEDIUM)

**Verdict: `substantiated`, with the anchors corrected.** The four-code spread is real; the report's two off-by-a-few-lines rows resolve to the surrounding statement, as it says.

| Code | Anchor (verified) | Note |
|---|---|---|
| `ACCESS_DENIED` | `dashboards_crud.py:279-283` and `:457` | as cited |
| `PERMISSION_DENIED` | `dashboards_crud.py:362` · `layouts.py:255-258` · `deps.py:740-743`, `:784-787`, `:828-831` | the report's `layouts.py:254` is the log call's closing paren; the raise is `:255` |
| `INSUFFICIENT_PERMISSIONS` | `deps.py:605-608` (role gates) | `admin.py` and `users.py:179` reach it through `AdminUser` |
| `DASHBOARD_NOT_FOUND` | `dashboards_crud.py` GET path | 404 vs 403 = the existence oracle |
| **`VALIDATION_ERROR` 422** | `dashboard_service.py:377-379` raises `ValueError`; `dashboards_access.py:110-115` maps it to 422 | **The fifth rendering.** Contradicts that endpoint's own docstring `:61` ("AppException 404") and `responses=admin_responses` at `:36`. |
| Precedent for the fix | `layouts.py:234` "Orphaned layout - return 404 to prevent enumeration" | the one place the codebase writes the decision down. Note the source uses a **hyphen**, not the em dash the input quoted. |
| Frontend consumer | `frontend/src/shared/api/errorHandler.ts` switches on `code`; `features/admin/model/errorMessages.ts:7-11` maps `PERMISSION_DENIED` | three codes consumed today — **phase 13 must be told before the mapping moves.** |

**Seams:** each call site raises its own `AppException` inline — there is no shared constructor, so "normalise" means editing each site or introducing one. That is a design question, not a refactor; it is left open in §6. **Tests:** `tests/test_error_format.py`-shaped assertions, if any, pin the current per-site codes.

---

### AUTZ-007 — Ownership is written to a column no decision reads (MEDIUM)

**Verdict: `substantiated`.** Unchanged.

| Seam | Anchor (verified) |
|---|---|
| Column | `dashboards.created_by` (`db/models/dashboard.py:68-72`), indexed `:37`, `ON DELETE SET NULL` from `users`. |
| The only write | `dashboard_service.py:88` `created_by=owner_id` inside `create_dashboard`. |
| Zero reads | Three `created_by` hits over `src/` — the write, the index, the column. No predicate, query or response model consults it. |
| The 1:1 fallback | `LayoutService.get_dashboard_id_for_layout` (`services/layout_service.py:197-210`) resolves to the **first** associated dashboard; its docstring says so. Correct only because the relation is 1:1 today. |
| Compounding | Once the `dashboard_access` row is gone (AUTZ-001's delete), no surface can restore an owner, and deleting the user erases the only datum while the grant rows cascade. |
| Candidate gate | `require_dashboard_admin_access` again — same dependency as AUTZ-001/002. |

**Seams:** the column itself, the `create_dashboard` write, and the 1:1 multiplicity assumption in `layout_service.py`. **Docs:** `docs/09-database/` schema-access pages describe the column; the multiplicity question is **phase 14's** (schema ruling) — this phase names the assumption and does not pre-empt it. **Tests:** `tests/test_resource_access_control.py::TestDashboardOwnerAccess` (`:314`) exercises ownership through the *grant*, not the column — it will not break, and it also will not catch a regression here.

---

### AUTZ-008 — A second identity resolution consults fewer states and has no caller (LOW)

**Verdict: `substantiated` as tabulated; the report's own correction is confirmed.**

| Mechanism | Live path: `deps.get_current_user_dependency` | Unused path: `permissions._get_current_user_with_session` |
|---|---|---|
| Decode failure | `deps.py:498-504` → `INVALID_TOKEN` | `permissions.py:312-314` → `AuthenticationError` |
| `jti` revocation | `deps.py:507-515` (unconditional) | `permissions.py:325-328` — **guarded by `redis_client is not None`** |
| `user_tokens_revoked` | `deps.py:529-535` (unconditional) | `permissions.py:331-334` — **same guard** |
| `is_active` | `deps.py:547-553` → `AUTHENTICATION_FAILED` | **absent** — `:336-345` goes from the revocation check straight to `repo.get` |
| Redis default | `get_redis_client_dependency` (`:125`) | `redis_client: aioredis.Redis \| None = None` (`:268`) — a `None` default makes both checks **silently skip** |
| Importers | route dependencies | `get_current_user` at `permissions.py:265`; the **only** importer anywhere is `tests/test_permissions.py:14` |

The report's correction stands: `core/permissions.py:38` is `PERMISSION_LEVELS: dict[DashboardPermission, int] = {` and contains no reference to `get_current_user`. **Line numbers shifted +3** in `deps.py` from `2174895`; `permissions.py` did not move.

`dashboard_access.permission` being a native enum with exactly `view`/`edit`/`admin` (`db/models/access.py:43-52`) is why the three implementations agree on every storable value and differ only on the `read`/`write` aliases the enum cannot hold — the report's reasoning, confirmed.

**Sequencing claim: the report is right to drop it.** Its stated dependency on AUTZ-003 ("so there is one resolution before a second is deleted") names a dependency that does not exist — AUTZ-003 is about *which authorization attribute* decides, not how a token becomes a user, and nothing in an AUTZ-003 change touches `core/permissions.py:265`. Carrying it would put a dead-code deletion behind an unrelated product decision.

**Seams:** `permissions.py:265-353` (the two functions), `deps.py:451-472` (`get_token_from_header` is not re-exported as a plain function — the report's note that the dead path is "reachable by omission"), and the `redis_client is not None` guards. **Tests:** `tests/test_permissions.py::TestGetCurrentUser` is the only shipped suite for the dead path — **phase 09's** hand-off, not pre-empted. **Docs:** `access-control.md:171-182` describes `check_dashboard_access` only; nothing documents the second resolver, which is part of why nothing explains it.

---

### AUTZ-009 — Unauthenticated `/health/detailed` leaks a path and raw driver errors (LOW)

**Verdict: `substantiated`, with an extension the report could not have seen.** The always-on disclosure reproduces; the database-failure branch remains **unsettled** and is not claimed as reproduced.

| Seam | Anchor (verified) |
|---|---|
| Route | `app.py:318-379`, registered with **no dependency** — `@application.get("/health/detailed", tags=["health"])` at `:318`, a plain `Request` parameter at `:319`. The report cited `:269-307`; the endpoint has moved **+49 lines** since the baseline. |
| Always-on leak | `components["static_files"] = {"status": "available" if os.path.isdir("frontend/dist") else "unavailable", "path": "frontend/dist"}` at `:350-353`. The report cited `:303`; +49 drift, same statement. |
| Error branch | `except Exception as e: … "error": str(e)` at `:340-346` (report: `:296`). Unfiltered driver text. **Named from source only** — exercising it needs the dev database stopped, which is out of bounds. |
| Sibling | `/health` (`app.py:297-316`) is also unauthenticated and returns a fixed two-key body. |
| **Extension** | `:360-376` — a `stale_processing_reconciler` component added by `4a5db54` (`app.py` moved in the drift window). It reports `lease_state`, `last_success_at`, `last_swept_count`, `sweep_count` and **`unprotected_ticks`** to an anonymous caller. The report's inventory predates it. |

**Seams:** `app.py:350-353` (drop `"path"` — a one-line deletion), `app.py:345` (replace `str(e)` with the fixed string the same branch already sets at `:344`, keeping the detail in the log line at `:341`), and the new `:360-376` component. **Tests:** `tests/test_health.py` exists and asserts the payload shape — it will need updating for the removed key. **Docs:** `docs/05-health/health-api.md` describes both endpoints and **is this phase's to edit**; note phase 07 `HO-3` and phase 10 `B9` both treat the health *probe contract* as theirs, so the two must not edit the same doc row in parallel. **nginx:** `docker/nginx/nginx.conf:43-46` proxies `^/health(/detailed)?$` with no auth — the disclosure is reachable through the production fronting tier unchanged.

---

### Report-level defects `VAL-12-001` … `VAL-12-005`

| ID | Claim | Verdict | Anchor today |
|---|---|---|---|
| `VAL-12-001` | `/auth/logout` is **not** non-mutating; it writes two Redis revocation records | **`substantiated`** | `auth.py:441` reads the cookie; `revoke_refresh_token` at `:448`, `revoke_token` at `:459`, `delete_secure_cookie` at `:461`. `request.cookies` has exactly two hits over `src/` (`:297`, `:441`), so the rest of the paragraph is exact. The positive result still stands on the other route: `/auth/logout` authenticates on `get_current_user_dependency` (`deps.py:451-472`, `HTTPBearer`), so no ambient credential reaches it. |
| `VAL-12-002` | Two `config.py` anchors do not resolve to their mechanisms | **`stale` — the anchors have moved again** | The report already re-pointed them (`767-772` → wildcard refusal, `docker/docker-compose.override.yml` → the dev override) and re-checked post-drift. `config.py` is the repo's highest-churn file (phase 01's, `C11-12`) and moved **+4** again after `8953bf7`/`8953bf7`-era work. **This defect changes no phase-12 target**: both mechanisms exist and behave as claimed, and neither is on an authorization path. Documentation-only. |
| `VAL-12-003` | One line of AUTZ-005's evidence did not reproduce; the annotation misattributes the inertness | **`substantiated`, and now moot in its original form** | The DB `updated_at` never moved in either direction — which is the artefact that proves inertness. With `2174895` the write *does* persist, so this evidence line can no longer be reproduced at all. The defect was in the report's evidence, not in the code. |
| `VAL-12-004` | AUTZ-003 stops one step short of the fact that decides its own direction | **`substantiated`** | The set difference is `{dashboard_access=admin ∧ users.role≠admin}` and is **refuse-only**. Confirmed by reading `permissions.py:179` versus `deps.py:599-608`. Adds the argument, not a new finding. |
| `VAL-12-005` | Roadmap step 1 followed as written leaves the deactivation control inert | **`substantiated` — and materially worse now** | (a) TXN-001 has **landed** (`2174895`), so half the widening is already done. (b) the reactivate-path key deletion is **still missing** (`admin.py:192-214` has no `else`). (c) `is_active` is still read in exactly one place, `deps.py:547`, and `auth_service.py` still has no reference to it. **The consequence is now inverted and more severe**: a correctly-persisted `is_active=false` no longer fails silently — the account authenticates at `/auth/login` and `/auth/refresh` and is refused at the gate on every subsequent request, which `admin.py:153-167` documents as intended. |

**`VAL-12-*` defects that change a target: two.** `VAL-12-005` reshapes AUTZ-005 from "the write does not persist" to "the write persists and the control still has two open halves", which changes what an implementor must touch. `VAL-12-003` removes one of the report's own evidence lines. `VAL-12-001`, `VAL-12-002` and `VAL-12-004` are documentation-only or argument-only.

---

## 3. Cross-cutting architecture and constraints

### The dependency chain, per route family

| Family | Chain | Authority |
|---|---|---|
| Dashboard CRUD | `dashboards_crud.py` → `check_dashboard_access` inline (`:352-355` `edit`, `:447-450` `admin`) | grant (+ admin bypass) |
| Dashboard access mgmt | `dashboards_access.py` → `DashboardService` → `AccessRepository` | **none** |
| Dashboard filters (mutate) | `dashboards_filters.py` → `DashboardFilterRepository` | **none** |
| Dashboard filters (read) | `:140` `require_dashboard_read_access` → `deps.py:729-734` | grant |
| Graph lifecycle (global) | `graphs.py` inline `check_dashboard_access` ×4 (`:96`, `:245`, `:333`, `:443`) | grant |
| Graph list (global) | `graphs.py:174-186` inline role branch + `AccessRepository().get_user_dashboards` | **third mechanism** |
| Graph create (nested) | `dashboards_graphs.py:56` `require_admin_role` | **role** |
| Graph read (nested) | `dashboards_graphs.py:151` `require_dashboard_read_access` | grant |
| Upload / status / result | `upload.py:75`/`:262`/`:319` `EditorUser` **and** `data_service.py:122`/`:267`/`:331`/`:365` `check_dashboard_access` | **both**, role first |
| Data aggregated | `data.py:88-93` `check_dashboard_access` | grant |
| Layouts | `layouts.py:80`/`:314`/`:396` inline `UserRole.ADMIN`; `:230-256` role + grant | **role**, inconsistently |
| Processing configs | `processing_configs.py:85`/`:165`/`:249` `check_dashboard_access` | grant |
| Admin | `admin.py` — every endpoint `admin_user: AdminUser` | role |

### Permission / role model and storage

- `users.role`: `UserRole` `StrEnum` (`models/enums.py`), `ROLE_HIERARCHY` ordered `viewer < editor < admin` (`permissions.py:35`), compared by `check_role` (`:86-122`).
- `dashboard_access.permission`: **native PostgreSQL enum** `dashboard_permission_level`, values `view`/`edit`/`admin` only (`db/models/access.py:43-52`). Composite PK `(user_id, dashboard_id)` (`:68-72`); two FKs, both `CASCADE`.
- **21 `required_permission=` call sites** over `src/`: `deps.py` ×6, `dashboards_crud.py` ×2, `layouts.py` ×1, `data.py` ×1, `graphs.py` ×4, `processing_configs.py` ×3, `data_service.py` ×4. All bare string literals.
- `check_dashboard_access` (`permissions.py:125-155`) validates the required level, then `_check_access_with_session` (`:158-246`) does the **admin bypass first** (`:179`) and only then reads the grant. The `perm_map` alias table (`:205-211`) and the `permission_levels` ladder (`:215-219`) are duplicated from `PERMISSION_LEVELS` (`:38-42`), which has **one hit repo-wide: its own declaration**.
- `dashboard_access` is the **only** ownership record. `dashboards.created_by` is written and never read.

### Ownership vs administration vs the tier model

Three audiences are documented and none is enforced consistently: the module docstring says "admin role" (`:4`), the grant description says "dashboard owner" (`:35`, `:47`), and `access-control.md:140-146` says "Admin only". `docs/SPEC.md:123` states the admin bypass as a decision; `:124` states the 403/404 dual-signal, which `layouts.py:234` is the only place that reasons about in code.

**Tier model** (`config.py` `EnvironmentEnum`): `access-control.md` and `nginx.conf` are the two places tiers change *authorization* behaviour — `app.py:250-253` disables `/docs` and `/redoc` in production, `nginx.conf` exists only under the `production` profile, and `access-control.md`'s dual-signal rule is written for the application tier. Phase 02 owns the per-tier key set; nothing in phase 12 introduces a key.

### The second identity path

`permissions.get_current_user` (`:265-288`) → `_get_current_user_with_session` (`:291-353`). No production importer; only `tests/test_permissions.py:14`. More permissive than `deps.get_current_user_dependency` in two ways: no `is_active` branch, and both revocation reads guarded by `redis_client is not None` against a `None` default. `deps` does not export a plain token→user function, so the path is reachable by omission rather than by import.

### nginx's own auth-adjacent behaviour

`docker/nginx/nginx.conf` (94 lines) sets **no `log_format`** at all — it inherits nginx's `combined`, which logs the full request line. It proxies `location /api` (`:34-40`) with `X-Real-IP`, `X-Forwarded-For` and `X-Forwarded-Proto`, and `location ~ ^/health(/detailed)?$` (`:43-46`) with **no auth**, which is what makes AUTZ-009 reachable in production. It performs **no** authorization decision of its own. `docker-compose.yml:272-291` mounts it read-only under the `production` profile only; the `default` network at `:310-312` declares **no `ipam`/`subnet`**, so there is no CIDR in the file for phase 04's `D-04-E` option (a) to name.

### Shared seams and their owner phase

| Seam | Owner | This phase's obligation |
|---|---|---|
| `docker/nginx/nginx.conf` `log_format` / `access_log` / `client_max_body_size` / `location` blocks / mount path | **phase 12** (format directives) · **phase 10** (destinations, `B9`) | `C04-5`: add URI redaction if phase 04's `D-04-K` rules option (b); keep the forwarded-header set intact if `D-04-E` rules option (a). Phase 04 may request; it may not edit. Phase 10's `C10-11` bars a relocation without written notice (`DP-10-8` option (a)). |
| `dashboard_access` grant semantics — `AccessRepository.grant_access`'s existing-row no-op, `DashboardService.grant_access`, the four bare-`str` homes, the 21 literal call sites | **phase 08** (`CQLT-1`) | Read-only here. The report's Appendix A confirms `QLT-001` stays phase 08's. |
| The **rule** for the access-management surface — who may grant/revoke, and what a refusal discloses | **phase 12** (this phase) | Phase 08's `CQLT-2` fixes the *enforcement point* and hands the rule here (`C08-2`: "phase 12 must be informed before the rule is fixed"; `D-4` must be ruled with phase 12). Phase 08 covers **one call site more** than the phase-12 report assumed — `DashboardService.create_dashboard`'s owner-grant is a second caller. |
| `core/permissions.py`'s `required_permission` typing and the ladder literals | **phase 08** (`CQLT-1`, which records a disposition for `PERMISSION_LEVELS`) | Do not consolidate in parallel. |
| `api/routes/graphs.py`'s list endpoint inline block and `layouts.py`'s equivalent | **phase 08** (`CQLT-3`, `QLT-008`) | AUTZ-003 must not re-fix it; the nested-create change touches a different decorator. |
| Client-side error-code consumption (`ACCESS_DENIED` / `PERMISSION_DENIED` / `INSUFFICIENT_PERMISSIONS` / `VALIDATION_ERROR`) | **phase 13 / 16** | **Tell phase 13 before the AUTZ-006 mapping moves.** |
| Layout ↔ dashboard multiplicity (1:1 assumption) | **phase 14** | Name the assumption; do not settle it. |
| TXN-001 user-write transaction ownership | **phase 03** — **landed** as `2174895` | Do not re-file. |
| `is_active` on the token-issuing surfaces | **phase 04** (`D-04-I`, `AB-4`, decision record `C-7`) | VAL-12-005 part (c) is **the same missing-consumer class** on this phase's side. The landed `admin.py:153-167` docstring names the marker as the authority for exactly these two paths, so phase 04's block **cannot start without** the ruling — read it before scheduling. |
| `/health/detailed` payload | **phase 12** (the payload) · **phase 07** `HO-3` / **phase 10** `B9` (the probe contract) | Edit `docs/05-health/health-api.md` in coordination; do not restate the probe contract. |
| Compose network CIDR | **phase 12** owns the value if the subnet ever changes | `docker-compose.yml:310-312` has no `ipam`; the Researcher in phase 04's `AB-7` must establish the actual subnet. |
| `core/security.py` revocation read direction | **phase 04** (`AB-5`), via phase 07's `HO-2` | The six revocation-read sites include the two in `permissions.py` — silent edit sites for any guard this phase adds. |

---

## 4. In-flight and already-landed work

### Landed, on this phase's anchors (`7342e9e` → `ab76989`)

| Commit | Files | Symbol | Effect on phase 12 |
|---|---|---|---|
| `2174895` | `services/user_service.py`, `api/routes/admin.py`, `api/deps.py`, `db/session.py`, `interfaces/service_interfaces.py` | `UserService.update_user_active_status` / `update_user_role`; `update_user_active_admin_endpoint` | **AUTZ-005 (a) already-fixed.** Both services now commit (`user_service.py:259`, `:301`); the endpoint docstring documents the two-effect ordering. `deps.py` shifted **+3** lines throughout. Rewrote `tests/test_admin_user_management.py` (+367) and `tests/test_token_revocation.py` (+124). |
| `2de4156` | `api/routes/admin.py`, `services/auth_service.py` | `AuthService.approve_registration_request` / `reset_password_admin`; `IAuthService` | Reordered create → flag → status → **commit** → Redis write. Adds no `is_active` read, so AUTZ-005 (c) is unchanged. Its commit body records "other routes still commit in the transport layer" as a known inconsistency. |
| `cea2d06` | `api/routes/admin.py`, `services/user_service.py` | test cleanup only | Follow-up; no new authorization surface. |
| `4a5db54` | `app.py` | `stale_processing_reconciler` component | **Extends AUTZ-009's scope** (`app.py:360-376`): lease state, sweep counts and `unprotected_ticks` to an anonymous caller. |
| `3848e7a` | `core/task_queue.py`, `app.py` | — | No authorization surface. |

### Dirty in the working tree

| File | Phase | On an authorization path? |
|---|---|---|
| `src/mkobi/db/advisory_lock.py` | 03 `B2` | **No** |
| `src/mkobi/workers/data_worker.py` | 03 `B2` | **No** |
| `tests/test_advisory_lock.py` | 03 `B2` | No |
| `tests/test_config.py` | 01 | No |
| `docs/06-backend/configuration.md` | 01 | No |

**The peer's "five dirty production files, three in the set-based write region" does not match the tree.** `git status --short` shows **four** modified files, of which **two** are production source (`advisory_lock.py`, `data_worker.py`) and **neither** is an authorization path; the rest of the modified set is two test files and one doc. Files on disk were read as truth regardless. No authorization file is dirty, so **no phase-12 finding is affected by uncommitted work**.

---

## 5. Discrepancies and risks

### Stale anchors

| Anchor in the report | Today | Note |
|---|---|---|
| `api/deps.py:472-576`, `:496`, `:504`, `:526`, `:544` | `:475-579`, `:501`, `:508`, `:529`, `:547` | uniform **+3** from `2174895` |
| `api/deps.py:582-606`, `:744-785`, `:788-829`, `:448-469` | `:585-609`, `:747-788`, `:791-832`, `:451-472` | uniform **+3** |
| `app.py:269-307`, `:296`, `:303`, `:248-267` | `:318-379`, `:345`, `:352`, `:297-316` | uniform **+49** from `4a5db54` |
| `services/user_service.py:248-284`, `:234` | `:271-310`, `:227-269` | +23 from `2174895` |
| `config.py:767-772`, `:448`/`:450-453` | moved again (+4) | phase 01's highest-churn file; `VAL-12-002` only |
| `core/permissions.py`, `dashboards_access.py`, `dashboards_filters.py`, `graphs.py`, `data.py`, `dashboards_graphs.py`, `upload.py`, `access_repo.py`, `db/models/*` | **unchanged** | these are the load-bearing anchors, and all resolve exactly |

### Refuted or contested

| Claim | Source | Verdict |
|---|---|---|
| "`grant_access` has exactly two callers" (phase-12 Appendix A / phase 08 `VAL-08-005`) | both reports | **Substantiated** — `dashboards_access.py:85` and `dashboard_service.py:104` (create path). The older phase-08 input's "only caller" was already refuted by its own validator. |
| "AUTZ-008 should land after AUTZ-003" | phase-12 report's own recommendation | **Refuted by the report's validator** (`VAL-12-*` note) and confirmed here: no dependency exists. |
| "Four of the five graph operations use the grant" | phase-12 report | **Refined:** four `check_dashboard_access` sites, yes — but the fifth (`graphs.py:174-186`) uses a **third** mechanism (inline role branch + `get_user_dashboards`), not the role gate. "Only the nested create uses the role" is true of the two *named* gates; the list endpoint is a third path. |
| "`upload.py:75` declares `EditorUser`" — implies one site | phase-12 report | **Extended:** three sites (`:75`, `:262`, `:319`). All three are `EditorUser`; the service re-checks the grant on each (`data_service.py:267`, `:331`, `:365`). |
| "the dev tier disables the health probe" | phase-11 report | Refuted by phase 07 (`HO-3`, `9c49c20`); the dev healthcheck is **re-enabled**. |
| "Docker is available for read-only verification; start services" | task framing | **Not done, deliberately.** No container was started, stopped or reconfigured. Every claim here is static; the report's own live probes remain the only runtime evidence. |

### Tests that will break

| Test | Breaks on | Why |
|---|---|---|
| *none* for AUTZ-001/002/003/004 | — | No shipped test asserts the open behaviour. Confirmed: `test_dashboard_access.py` has **one** test and it is the cascade case. |
| `tests/test_resource_access_control.py` — `TestResourceAccessControlUpdate:17`, `TestResourceAccessControlDelete:167`, `TestDashboardOwnerAccess:314`, `TestAccessControlListChecked:407` | AUTZ-001/002 gate install | Must stay **green unmodified** — they are the only shipped proof the admin bypass survives. |
| `tests/test_admin_user_management.py`, `tests/test_token_revocation.py` | AUTZ-005 (b) | Rewritten by `2174895` + `cea2d06`; read before designing the key deletion. |
| `tests/test_health.py` | AUTZ-009 | Asserts the payload shape; drops `"path"`, changes the reconciler component. |
| `tests/test_permissions.py::TestGetCurrentUser` | AUTZ-008 | The only suite for the dead resolver; **phase 09's** hand-off. |
| `tests/test_data_service.py` | AUTZ-004 | Cross-dashboard `graph_id` case is unasserted today. |

### The privilege-escalation risk of any change here

**This is the highest-risk surface in the programme.** A gate installed in the wrong place, or with the wrong permission level, is an escalation; a gate installed with the right predicate in the wrong *direction* is a lockout. Three concrete vectors:

1. **AUTZ-001/002 gate install — 200 → 403.** A behaviour change, not a refactor. Any caller that is neither owner nor administrator of the target dashboard starts receiving 403 on three documented endpoints. The pre-existing wrongly-created grants persist and are **not** rewritten by the fix; an operator must reconcile them. A viewer who today reads an ACL because nothing stopped them will see 403 — and the frontend has no access-management surface to absorb it gracefully.
2. **AUTZ-003 — moving the nested routes onto the grant is strictly *more permissive*.** The set difference is `{grant=admin ∧ role≠admin}`; no principal gains an operation that either gate alone would deny. This is the one authorization change in the set that cannot escalate — but it does widen the surface for any principal who was **wrongly granted** `admin` on a dashboard, which AUTZ-001 makes reachable today. **Order is load-bearing: the AUTZ-001 gate must land first**, or the widened path is unguarded.
3. **AUTZ-005 (b) — adding a `delete` on the reactivate path** is safe in itself. **AUTZ-005 (c) — adding an `is_active` read to `login_user` and `/auth/refresh`** converts a 200 into a 401 on two credential-issuing surfaces. Every account carrying a stale `user_tokens_revoked` key (TTL 604 798 s ≈ 7 days) will fail at **login** rather than at first use — a strictly larger blast radius than the current "fails at the gate" behaviour, and it needs an operator runbook line.

**Where a fix converts a 200 into a 403, stated plainly:** AUTZ-001 (all three ACL routes), AUTZ-002 (bind + unbind, plus the 500→404 existence normalisation), AUTZ-003 (403 → 200 on the nested chart create and on upload, for a dashboard administrator whose global role is below admin — the *reverse* direction), AUTZ-004 (200 → 404 for a foreign `graph_id`), AUTZ-005 (200 → 401 on `/auth/login` and `/auth/refresh` for a deactivated account).

---

## 6. Decision points for the Planner

Genuine technical uncertainty, with alternatives and the chooser named. **None is picked here.**

| ID | Question | Alternatives | Chooser | Blocked until ruled |
|---|---|---|---|---|
| **DP-12-A** | For AUTZ-001/002, is the audience *dashboard owner or admin-grant* or *global `users.role == admin`*? The module docstring says one, the grant description says another, `access-control.md:140-146` a third. | (a) `require_dashboard_admin_access` — grant, with admin bypass; (b) `require_admin_role` — global role only, matching the docstring; (c) owner-checked-by-`created_by` — needs the AUTZ-007 schema ruling first | **Tech Lead with phase 08's `D-4`** (`C08-2`) | The gate install itself. This is the rule phase 08 explicitly hands here. |
| **DP-12-B** | AUTZ-001's ACL-read absence case: normalise to 404 (matching `layouts.py:234`'s stated convention) or leave `200 []`? | (a) 404 + `DASHBOARD_NOT_FOUND`; (b) 200 `[]` preserved | Tech Lead | Only the read endpoint's refinement; the gate install is separable. |
| **DP-12-C** | AUTZ-006: normalise by editing each call site, or introduce one shared refusal constructor? | (a) per-site edits; (b) a shared helper (new abstraction — the project's rules discourage it) | Tech Lead | The AUTZ-006 block's shape. Must be coordinated with **phase 13**'s client-side consumption first. |
| **DP-12-D** | AUTZ-003: is the *global* graph list endpoint (`graphs.py:174-186`) in scope, given it uses a third mechanism no shared dependency can answer? | (a) in scope here; (b) left to phase 08's `CQLT-3`; (c) in scope, requiring a new **set-shaped** dependency | Tech Lead with phase 08 | Whether `deps.py` gains a collection-shaped helper. **Do not duplicate `CQLT-3`.** |
| **DP-12-E** | AUTZ-005 (b)+(c): are the reactivate-path key deletion and the `is_active` read on `login_user`/`/auth/refresh` one block or two? | (a) one block; (b) two blocks (b is small and self-contained, c changes two status codes) | **Tech Lead with phase 04's `D-04-I`** (which owns the same `is_active` question) | Both halves. Phase 04's `AB-4` is hard-blocked on the same ruling; the two phases must not each rule it. |
| **DP-12-F** | AUTZ-005: does the landed `admin.py:153-167` docstring's "the marker is the authority for `/auth/refresh` and the gate" survive, or is it a documented lie to correct? | (a) preserve the design as written (marker is the authority; `is_active` need not reach the login paths); (b) correct the docstring and add the `is_active` reads | **Tech Lead** — this is a **security-boundary** decision, and the docstring is the only place the current intent is written down | Whether (c) is a code change or a doc change. |
| **DP-12-G** | AUTZ-009: is the new `stale_processing_reconciler` component (`:360-376`) inside AUTZ-009's scope, or a separate LOW item? | (a) in scope — same endpoint, same disclosure class; (b) separate | Tech Lead | Whether the reconciler fields are redacted in the same change as `"path"`. |
| **DP-12-H** | AUTZ-007: does this phase only *name* the `created_by` / multiplicity assumption (leaving the ruling to phase 14), or does it change who is considered an owner? | (a) name only, no behaviour change; (b) make `created_by` authoritative | **Tech Lead with phase 14** | Nothing in this phase; it is a scoping decision. If (b), AUTZ-001's gate cannot be installed before the schema ruling, which is a hard ordering consequence. |

---

## 7. Coverage ledger

| Finding | Severity | Verdict | Primary evidence anchor (verified today) |
|---|---|---|---|
| `AUTZ-001` | CRITICAL | **substantiated** | `dashboards_access.py:31/130/174` — three `current_user: CurrentUser` declarations, zero predicates; `access_repo.py:89-130`; `deps.py:791-832` (gate, unused) |
| `AUTZ-002` | CRITICAL | **substantiated** | `dashboards_filters.py:32-127` (no `check_dashboard_access`); `:140` the sole predicate; `:54-58` filter-existence check; `:68-79` the 500; `db/models/filters.py:87` |
| `AUTZ-003` | HIGH | **substantiated** | `dashboards_graphs.py:56` (`require_admin_role`) vs `graphs.py:96/245/333/443` (`check_dashboard_access`); `upload.py:75`+`data_service.py:122`; third mechanism `graphs.py:174-186`; set difference `{grant=admin ∧ role≠admin}` |
| `AUTZ-004` | HIGH | **substantiated** | `data.py:88-93` (the only decision) · `:120` (unconstrained) · `:122` (the branch) · `:152-158` (disclosed fields); `data_service.py:208-210` |
| `AUTZ-005` | HIGH | **drifted** — (a) `already-fixed` by `2174895`; (b) and (c) `substantiated` | `user_service.py:301` (commit, new) · `admin.py:192-214` (revoke on deactivate only, no `else`) · `security.py:535`/`:552` (two sites, no delete) · `deps.py:547` (sole `is_active` read) · `auth.py:368` (refresh: no `is_active`) |
| `AUTZ-006` | MEDIUM | **substantiated** (anchors corrected) | `dashboards_crud.py:279-283`/`:362`/`:457` · `layouts.py:234` (the stated convention) /`:255` · `dashboard_service.py:377-379` → `dashboards_access.py:110-115` (the 422 fifth rendering) · `errorHandler.ts` |
| `AUTZ-007` | MEDIUM | **substantiated** | `db/models/dashboard.py:68-72` + index `:37`; the single write `dashboard_service.py:88`; `layout_service.py:197-210` (first-match, 1:1 assumption) |
| `AUTZ-008` | LOW | **substantiated** | `permissions.py:265`/`:291-353` (no `is_active`; `redis_client is not None` at `:325`/`:331`; `None` default `:268`) vs `deps.py:498/507/529/547`; sole importer `tests/test_permissions.py:14`; `db/models/access.py:43-52` |
| `AUTZ-009` | LOW | **substantiated**, extended | `app.py:318` (no dependency) · `:350-353` (`"path"`, +49 drift) · `:340-346` (`str(e)`, unsettled) · `:360-376` **new reconciler component** · `nginx.conf:43-46` (proxies it unauthenticated) |
| `VAL-12-001` | LOW | **substantiated** | `auth.py:441`/`:448`/`:459`/`:461`; `request.cookies` → exactly `auth.py:297`, `:441` |
| `VAL-12-002` | LOW | **stale** (anchors moved again) | `config.py` is phase 01's `C11-12` file, +4 drift; both mechanisms exist; **changes no phase-12 target** |
| `VAL-12-003` | LOW | **substantiated** (evidence line now unreproducible) | `user_service.py:301` — the write persists, so the DB-`updated_at` reading can no longer be produced |
| `VAL-12-004` | LOW | **substantiated** | `permissions.py:179` (bypass) vs `deps.py:599-608` (role); refuse-only direction |
| `VAL-12-005` | HIGH | **substantiated** — (a) landed, (b)+(c) open, consequence **inverted** | `deps.py:547` sole read · `auth_service.py` zero `is_active` references · `auth.py:358-375` · `admin.py:153-167` docstring states the current intent |
| `QLT-001` (ph 08) | — | confirmed, **not re-filed** | `access_repo.py:50-63` (existing-row return); `dashboard_service.py:374-392` |
| `QLT-002` (ph 08) | — | confirmed, **not re-filed**; rule handed here | `dashboards_access.py:85`; `dashboard_service.py:104` — **two** callers |
| `AUTH-003` (ph 04) | — | not re-filed, upheld | `admin.py` writes, zero server-side reads |
| `AUTH-004` (ph 04) | — | not re-filed, upheld on corrected grounds | `deps.py:507/529` (`token_blacklist`/`user_tokens_revoked`) vs `auth.py:368` (`refresh_token_blacklist`) — **disjoint namespaces** |
