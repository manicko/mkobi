---
phase: 12-authorization
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 9
baseline: 7342e9e7bae99adf248339bb4a062b67a06fb97c
baseline-dirty: true
by-severity:
  CRITICAL: 2
  HIGH: 3
  MEDIUM: 2
  LOW: 2
---

# Phase 12 — Findings

## Summary

The authorization zone was examined end to end: every surface in `src/mkobi/api/routes/`
plus `/health`, `/health/detailed`; every dependency in `src/mkobi/api/deps.py`; the
shared predicates in `src/mkobi/core/permissions.py`; and every dashboard-scoped
mutation in `src/mkobi/services/` and `src/mkobi/db/repositories/`. The access matrix was
driven live over HTTP against the running dev stack (`localhost:8010`) with a
self-registered `viewer` holding zero grants, against admin-owned dashboards, and against
a dashboard the principal had no relationship to; every user, dashboard, graph, layout,
grant, `dashboard_filters` row, `registration_requests` row and Redis key the probes
created has been removed (Appendix C). Two access decisions are reached by an
authenticated principal that holds nothing on the object it acts on: it can read the
complete access-control list of any dashboard and delete any grant on it including an
owner's, and it can rewrite any dashboard's filter bindings. Separately, the system
carries **two independent authorities for one decision** — `users.role` and
`dashboard_access.permission` — with no written precedence, and they disagree: the same
principal may create a chart on a dashboard through one route and is refused the same
operation through another. The single most consequential consequence is AUTZ-001:
`dashboard_access` is the only representation of ownership, it is readable by everyone,
and it is writable and deletable by everyone.

## Findings

### AUTZ-001 — Any authenticated principal reads any dashboard's access-control list and deletes any grant on it, including an owner's

**Severity** — CRITICAL

**Zone** — "Single-object paths: is the caller consulted, and what the response discloses first"

**Observation** — `GET /api/v1/dashboards/{dashboard_id}/access`
(`src/mkobi/api/routes/dashboards_access.py:130-171`) and
`DELETE /api/v1/dashboards/{dashboard_id}/access/{user_id}`
(`src/mkobi/api/routes/dashboards_access.py:174-227`) both declare only
`current_user: CurrentUser`. Neither calls `check_dashboard_access`, nor compares the
target grant's `user_id` with `current_user.id`, nor inspects `current_user.role`. Both
delegate to `DashboardService.get_dashboard_access_list`
(`src/mkobi/services/dashboard_service.py:442-478`) and
`DashboardService.revoke_access` (`:403-440`), which accept only
`(dashboard_id, user_id)` and carry no acting identity. `AccessRepository.revoke_access`
(`src/mkobi/db/repositories/access_repo.py:89-130`) resolves its target by the bare
`(user_id, dashboard_id)` pair and deletes it.

**Evidence** — Live reproduction against the dev stack. A self-registered `viewer`
(`58e988f1-a187-41ca-9802-479e43079d4f`) with **zero** `dashboard_access` rows called
`GET /api/v1/dashboards/ba58425d-799f-4360-b2f5-4df1bc5a6a4c/access` and received
`200` with the owner's row:
`[{"user_id":"13a1f341-f73d-4522-aee9-9b1e9d632736","dashboard_id":"ba58425d-…","permission":"admin"}]`.
The same principal then called
`DELETE /api/v1/dashboards/ba58425d-…/access/13a1f341-f73d-4522-aee9-9b1e9d632736`
and received `200 {"message":"Access revoked successfully"}`; the subsequent
`GET .../access` returned only the viewer's own row. The admin-owned dashboard was left
with no owner-level grant at all. The `views` and `deleted` responses above are the
verbatim probe output.

**Consequence** — `dashboard_access` is the only record of who owns a dashboard:
`dashboards.created_by` exists (`src/mkobi/db/models/dashboard.py:68-72`) but is read by
no decision (AUTZ-007). Any of the seven authenticated accounts in the dev database can
therefore strip the owner grant from any dashboard and become the sole `admin` on it —
and the same endpoint that permits the removal is what enumerates the target user ids
to aim at. Today this is reachable by any account that completed public self-registration
and admin approval, with no precondition beyond holding a valid session.

**Recommendation** — Put one gate in front of all three `/dashboards/{id}/access*`
surfaces rather than three inline copies: require `check_dashboard_access(...,
required_permission="admin")` on the path's `dashboard_id` (system admins keep the
existing bypass), and delete the `CurrentUser`-only signature. The service and repository
should keep taking an acting identity so the check cannot be skipped by a future caller —
`grant_access` and `revoke_access` are the two callees a new endpoint would reach. No
shipped test asserts the open behaviour; `tests/` covers `check_dashboard_access`
directly, not the route gate.

**Cross-reference** — QLT-002 (phase 08) established the same absence of a gate on the
**grant** endpoint. This finding is not that sub-claim; it is the revoke and the ACL-read
paths, which QLT-002's evidence did not cover. See Appendix A.

---

### AUTZ-002 — Filter binding on any dashboard is rewritten by any authenticated principal, and by no decision at all

**Severity** — CRITICAL

**Zone** — "Mutation entry points that receive no acting identity"

**Observation** —
`POST /api/v1/dashboards/{dashboard_id}/filters` and
`DELETE /api/v1/dashboards/{dashboard_id}/filters/{filter_id}`
(`src/mkobi/api/routes/dashboards_filters.py:32-127`) declare `current_user: CurrentUser`
and never read it. No `check_dashboard_access` call exists anywhere in the file; the
only access predicate in the module is installed on the *third* endpoint,
`GET .../filters` (`:140`, `Depends(require_dashboard_read_access)`). The module's own
docstring (`:4`) and both endpoint descriptions (`:36`, `:86`) state "All operations
require admin role" / "Requires admin role", and both responses advertise
`admin_responses`. Neither call site checks that the dashboard exists either:
`DashboardFilterRepository.bind_filter(dashboard_id, filter_id, db)`
(`src/mkobi/db/repositories/dashboard_filter_repo.py`) takes three identifiers and no
actor, and the unbind path never resolves `dashboard_id` at all.

**Evidence** — Live. The same zero-grant `viewer` issued
`POST /api/v1/dashboards/d1e25768-2723-457b-8606-ad1598b1cacd/filters?filter_id=3fd75bcc-f92e-4bd3-a1c3-cf5c8e6e9326`
against a dashboard it had **no grant on and no relationship to**, and received
`200 {"message":"Filter bound to dashboard","bound":true}`; the subsequent
`DELETE .../filters/3fd75bcc-…` returned `200 {"message":"Filter unbound from dashboard"}`.
`POST` against a non-existent dashboard (`11111111-1111-1111-1111-111111111111`) returned
`500 INTERNAL_ERROR "Error binding filter"` rather than a refusal, confirming no
existence and no authorization decision is reached.

**Consequence** — The filter binding is what makes a filter selectable on a dashboard
and therefore what scopes the values returned by
`GET /dashboards/{id}/filter-values` and the filter keys the aggregation pipeline uses.
Any of the seven authenticated accounts can add or remove a filter on any dashboard in
the system, including one owned by another user, without leaving a trace of who did it —
`dashboard_filters` carries no actor column. This is the only dashboard-scoped write in
`dashboards_filters.py` with no decision at all, and it is the third file in a row whose
module header claims an admin gate that no executing path installs.

**Recommendation** — Install `require_dashboard_admin_access` (already present in
`api/deps.py:788-829` and already the pattern used by `graphs.py:96-101`) on the bind
and unbind routes, and add the dashboard-existence check the crud routes already have
so a missing dashboard answers 404 instead of 500. Then either make the module
docstring true or delete the three `admin_responses` declarations — one of the two must
change; the declared contract is the cheaper edit and phase 08 owns the declaration
contradiction, so this phase owns only the missing gate. Carry `current_user.id` into
`bind_filter`/`unbind_filter` as the acting identity so a future caller cannot repeat
the omission.

---

### AUTZ-003 — Two authorities decide the same question and disagree: `users.role` admits one route and refuses the twin route for the identical principal

**Severity** — HIGH

**Zone** — "The two sources of authority, and which one decides"

**Observation** — Two independent attributes decide access in this system:
the system-wide `users.role` (`UserRole`, `src/mkobi/models/enums.py:9-14`, ordered by
`ROLE_HIERARCHY` in `src/mkobi/core/permissions.py:35`) and the per-dashboard
`dashboard_access.permission` (`DashboardPermission`, native enum
`dashboard_permission_level`, ordered by the inline map at
`src/mkobi/core/permissions.py:215-219`). No precedence between them is documented
anywhere; `check_role` (`permissions.py:86-122`) and `check_dashboard_access`
(`permissions.py:125-155`) do not consult each other. Both are installed, in different
shapes, on surfaces that perform the **same operation**:

- `POST /api/v1/graphs` (`src/mkobi/api/routes/graphs.py:96-101`) gates on
  `check_dashboard_access(required_permission="admin")` — the **grant**.
- `POST /api/v1/dashboards/{dashboard_id}/graphs`
  (`src/mkobi/api/routes/dashboards_graphs.py:56`) gates on
  `dependencies=[Depends(require_admin_role)]` — the **global role**.
- `POST /api/v1/upload/{dashboard_id}` (`src/mkobi/api/routes/upload.py:75`,
  `EditorUser`) gates the route on the **global role** and then gates again inside
  `DataService._execute_upload` (`src/mkobi/services/data_service.py:118-132`) on the
  **grant** — two gates on one request path, reading two different attributes.

**Evidence** — Live. One principal, `users.role=viewer`,
`dashboard_access.permission=admin` on dashboard `ba58425d-799f-4360-b2f5-4df1bc5a6a4c`,
two calls to create a chart on that dashboard:

```
POST /api/v1/graphs/  {"name":"viaGlobal","type":"bar","dashboard_id":"ba58425d-…","config":{"x":"region"},…}
  -> 201 {"name":"viaGlobal","dashboard_id":"ba58425d-…","id":"e25df66c-19c1-432f-8dd4-5505ef65c4f7",…}
POST /api/v1/dashboards/ba58425d-…/graphs  (identical body)
  -> 403 {"code":"INSUFFICIENT_PERMISSIONS","detail":"Admin access required"}
PUT  /api/v1/graphs/e25df66c-…  -> 200 (renamed to "renamedByViewer")
POST /api/v1/upload/ba58425d-…
  -> 403 {"code":"INSUFFICIENT_PERMISSIONS","detail":"Editor access required"}
```

**Consequence** — A principal that holds the *dashboard's own* `admin` grant — the level
the domain defines as "may administer this dashboard" — cannot use the nested
create-chart route or upload data to a dashboard it administers, while the global
`POST /graphs` route lets the same principal create, rename and (per `graphs.py:333`,
`graphs.py:443`) delete and mutate charts on that dashboard. The frontend, which is the
only consumer, calls the nested routes (`/api/v1/dashboards/...`), so in practice a
correctly-granted dashboard administrator is refused the dashboard's own chart
operations. This is not a hypothetical ordering: the agreement between the two
authorities holds only when `users.role=admin`, in which case both routes admit and the
divergence is invisible.

**Recommendation** — Pick one authority for dashboard-scoped surfaces and write the
rule down next to `DashboardPermission`. The grant is the finer and more specific one and
is already the decision on `graphs.py`, `layouts.py:242-247` and `data.py:88-93`; the
minimal change is to replace `dependencies=[Depends(require_admin_role)]` on
`dashboards_graphs.py:56` and `EditorUser` on `upload.py:75` with
`require_dashboard_admin_access` / `require_dashboard_write_access`, which are already
exported from `api/deps.py` and unused for these two paths. The service-level check in
`_execute_upload` then becomes belt-and-braces rather than the second of two
disagreeing gates. If instead the global role is the intended authority for these
paths, that is a product decision — say so in `SPEC.md`, and the nested graph route
still has to agree with the global one.

---

### AUTZ-004 — `/data/aggregated` resolves `graph_id` without constraining it to the `dashboard_id` the access check was performed against

**Severity** — HIGH

**Zone** — "The cross-aggregate boundary: what one aggregate's identifier can reach through another's"

**Observation** — `GET /api/v1/data/aggregated`
(`src/mkobi/api/routes/data.py:39-197`) performs its single authorization decision
against the query parameter `dashboard_id` (`data.py:88-93`,
`check_dashboard_access(required_permission="view")`). When `graph_id` is also
supplied it then resolves that graph with `graph_repo.get(id=graph_id, db=db)`
(`data.py:120`) — by its own identifier, with no constraint that the graph's
`dashboard_id` equals the one just authorised — and returns the graph's `type`, `name`
and `config` in the `GraphDataResponse` (`data.py:150-160`). The data query itself *is*
correctly constrained: `DataService._get_aggregated_data_with_session`
(`src/mkobi/services/data_service.py:208-210`) passes `dashboard_id=` into
`AggregatedDataRepository.get_by_graph_id`, which filters on both
(`src/mkobi/db/repositories/aggregated_data_repo.py:147-155`). Only the graph row
crosses the boundary.

**Evidence** — Live. A principal authorised on dashboard
`ba58425d-799f-4360-b2f5-4df1bc5a6a4c` requested
`GET /api/v1/data/aggregated?dashboard_id=ba58425d-…&graph_id=26fd8f1e-3e85-4f43-9b41-f240158510ac`,
where `26fd8f1e-…` is a chart on dashboard `d1e25768-2723-457b-8606-ad1598b1cacd` on
which the principal holds **no grant of any level**:

```
200 {"graphs":[{"graph_id":"26fd8f1e-3e85-4f43-9b41-f240158510ac",
               "type":"pie","name":"autzG2","data":[],"layout":null,"config":{}}]}
```

`data: []` confirms the data scope held; `name`, `type` and `config` did not. The same
call with the authorised dashboard's own graph returns `config":{"x":"region"}`, so the
config dict is genuinely carried across.

**Consequence** — Any authenticated principal with view on **any** dashboard can resolve
the identity and rendering configuration of a chart belonging to a dashboard it cannot
see, provided it knows the chart UUID. That reveals the existence, naming and chart
configuration of another owner's analysis surface; it is the only path in the codebase
where a `graphs` row is returned without a decision against the graph's own parent. It
is not rated CRITICAL because the identifier is a UUID that no surface enumerates for a
foreign dashboard, and the disclosed fields are the chart's `name`, `type` and `config`
rather than data values or dashboard configuration.

**Recommendation** — One line, in the same place the decision already is: reject
`single_graph.dashboard_id != dashboard_id` with `GRAPH_NOT_FOUND` before building the
response (`data.py:122`), so the unconstrained lookup can only ever succeed for the
authorised parent. Alternatively resolve the graph through
`graph_repo.get_by_dashboard_id(dashboard_id, db)` and select from that set. The first
is smaller.

---

### AUTZ-005 — Deactivation reports success, does not deactivate, and cannot be undone

**Severity** — HIGH

**Zone** — "Account state: which states are consulted, on which surface, and by which resolution"

**Observation** — `PATCH /api/v1/admin/users/{user_id}/active`
(`src/mkobi/api/routes/admin.py:137-193`) calls
`UserService.update_user_active_status`
(`src/mkobi/services/user_service.py:248-284`), which executes
`user_repo.update(id=user_id, db=db, is_active=is_active)` and never commits; the
route does not commit either. The route then writes the Redis key
`user_tokens_revoked:{user_id}` and returns the in-memory model. The reverse path,
`PATCH .../active {"is_active": true}` (`admin.py:159-193`), does not delete that key —
there is no code anywhere in `src/` that clears `user_tokens_revoked`.

**Evidence** — Live, admin-driven, same account throughout:

```
PATCH /admin/users/58e988f1-…/active {"is_active":false}
  -> 200 {"role":"viewer","is_active":false,"updated_at":"2026-09-30T18:37:44Z",…}
GET /admin/users -> stored is_active = True
POST /auth/login  -> 200            (the "deactivated" account still authenticates)
redis EXISTS user_tokens_revoked:58e988f1-…  -> 1
GET /auth/me with the freshly minted token -> 401 TOKEN_REVOKED
PATCH /admin/users/58e988f1-…/active {"is_active":true}
  -> 200 {"is_active":true,"updated_at":"2026-09-30T18:27:08Z"}   (the pre-deactivation timestamp)
redis EXISTS user_tokens_revoked:58e988f1-…  -> 1   (unchanged)
POST /auth/login -> 200 ; GET /auth/me -> 401 TOKEN_REVOKED
```

**Consequence** — The administrative deactivation control performs no deactivation.
The account keeps `is_active=true` in PostgreSQL, keeps passing `login_user`, and keeps
a usable session; the only thing the call changed is that a key was written which makes
*every* token for that account — including ones minted afterwards by a successful login
— fail `get_current_user_dependency` with `TOKEN_REVOKED`. Reactivation restores the
database flag but cannot clear the key, so the account is then permanently locked out
with no in-product recovery path and no operator-visible record of why. The same defect
applies to `PATCH /admin/users/{id}/role` (`admin.py:62-98`), which returned
`role:"editor"` while `GET /admin/users` continued to read `viewer`.

**Recommendation** — Commit the unit of work: `await db.commit()` at the end of
`update_user_active_status` and `update_user_role`, or — better and consistent with the
rest of the layer — move the commit into the `get_db_dependency`/`get_session`
teardown so no write path has to remember it. That is phase 03's TXN-001 and it must
land first; this finding records the authorization consequence, which disappears with
it. Independently and in the same change: make the reverse path delete
`user_tokens_revoked:{user_id}` before writing `is_active=true`, and log both
transitions at INFO with the acting admin id. The shipped tests do not assert the
present behaviour here.

**Cross-reference** — TXN-001 (phase 03) filed the missing commit as a transaction
defect. This finding is its authorization consequence: the two write paths whose
rollback leaves an authorization control inert, and the account-state asymmetry no
reverse path clears. AUTZ-005 closes with TXN-001 and must not be remediated
separately from it.

---

### AUTZ-006 — One refusal answered with three error codes and two disclosure levels, with no stated reason on either side

**Severity** — MEDIUM

**Zone** — "What each refusal discloses, and where the shapes disagree"

**Observation** — The single decision "this caller holds no access to this dashboard"
is rendered four different ways across surfaces, from three `ErrorCode` members and two
different HTTP semantics. No construction forces the agreement: the four call sites each
raise their own `AppException` inline.

| Surface | Code | Absent dashboard | Existing dashboard, no grant |
|---|---|---|---|
| `GET /dashboards/{id}` (`dashboards_crud.py:279-283`) | `ACCESS_DENIED` | **404** `DASHBOARD_NOT_FOUND` | 403 |
| `DELETE /dashboards/{id}` (`dashboards_crud.py:457`) | `ACCESS_DENIED` | 404 | 403 |
| `GET /data/aggregated` (`data.py:99-102`) | `ACCESS_DENIED` | 403 | 403 |
| `PUT /dashboards/{id}` (`dashboards_crud.py:362`) | `PERMISSION_DENIED` | 403 | 403 |
| `GET /dashboards/{id}/graphs`, `/filters`, `/filter-values` | `PERMISSION_DENIED` | 403 | 403 |
| `GET|PUT|DELETE /processing-configs/{id}` | `PERMISSION_DENIED` | 403 | 403 |
| `GET /graphs/{id}` (`graphs.py:265`), `GET /layouts/{id}` (`layouts.py:254`) | `PERMISSION_DENIED` | 403 | 403 |
| `GET /users/{id}` (`users.py:179`) | `PERMISSION_DENIED` | 403 | 403 |
| `POST /layouts` (`layouts.py:86`), `POST /upload/{id}` | `PERMISSION_DENIED` / `INSUFFICIENT_PERMISSIONS` | — | 403 |
| `POST /dashboards/{id}/graphs`, all `/admin/*`, `/users/`, `/auth/register` | `INSUFFICIENT_PERMISSIONS` | — | 403 |

The codebase contains a stated convention for exactly this question and applies it in
one place: `layouts.py:234` comments *"Orphaned layout — return 404 to prevent
enumeration"* and does so. `dashboards_crud.py` takes the opposite decision on the same
question with no comment.

**Evidence** — Live, same principal, zero grants on the target:

```
GET /dashboards/ba58425d-…            403 {"code":"ACCESS_DENIED","detail":"Access denied"}
DELETE /dashboards/ba58425d-…         403 {"code":"ACCESS_DENIED","detail":"Access denied"}
GET /data/aggregated?dashboard_id=…   403 {"code":"ACCESS_DENIED","detail":"You do not have access to this dashboard"}
PUT /dashboards/ba58425d-…            403 {"code":"PERMISSION_DENIED","detail":"You don't have access to this dashboard"}
GET /dashboards/ba58425d-…/graphs     403 {"code":"PERMISSION_DENIED","detail":"You do not have read access to this dashboard"}
GET /processing-configs/ba58425d-…    403 {"code":"PERMISSION_DENIED",…}
GET /users/{other-admin}              403 {"code":"PERMISSION_DENIED",…}
POST /dashboards/ba58425d-…/graphs     403 {"code":"INSUFFICIENT_PERMISSIONS","detail":"Admin access required"}
GET /admin/users                      403 {"code":"INSUFFICIENT_PERMISSIONS","detail":"Admin access required"}

GET /dashboards/11111111-1111-1111-1111-111111111111
                                    404 {"code":"DASHBOARD_NOT_FOUND","details":{"dashboard_id":"11111111-…"}}
GET /dashboards/11111111-1111-1111-1111-111111111111/graphs
                                    403 {"code":"PERMISSION_DENIED",…}
```

**Consequence** — `GET /dashboards/{id}` is a dashboard-existence oracle for any
authenticated principal: 404 versus 403 partitions the whole dashboard-id space, while
every sibling surface under the same prefix answers 403 for both and is safe. Any client
that switches on `code` — the frontend's `errorHandler.ts` does — must special-case
three values for one meaning. The three-way split has no stated reason on any of the
three branches.

**Recommendation** — Pick the safer convention, the one already written down at
`layouts.py:234`, and apply it uniformly: answer 403 `PERMISSION_DENIED` from the shared
gate for every "no access" case including an absent dashboard, and keep 404 only for a
dashboard the caller *may* see but which does not exist (unreachable, so simply drop it).
Centralise the mapping by letting `check_dashboard_access` be the only place a refusal is
raised, and derive `ErrorCode` from it. Update `frontend/src/shared/api/errorHandler.ts`
in the same change — phase 13 owns the client side and should be told before the code
moves, since three codes are currently consumed.

---

### AUTZ-007 — Dashboard ownership is written to a column no decision reads, and represented only by a row anyone can delete

**Severity** — MEDIUM

**Zone** — "Single-object paths: is the caller consulted, and what the response discloses first"

**Observation** — `dashboards.created_by` (`src/mkobi/db/models/dashboard.py:68-72`,
`ForeignKey("users.id", ondelete="SET NULL")`, indexed at `:37`) is written once by
`DashboardService.create_dashboard` (`src/mkobi/services/dashboard_service.py:88`,
`created_by=owner_id`) and is read by **no** predicate, query or response model anywhere
in `src/`. A repository-wide search for `created_by` returns three hits: the model
declaration, the index, and the single write. Ownership is therefore expressed in the
system solely as a `dashboard_access` row with `permission=admin`, and AUTZ-001
establishes that such a row can be deleted by any authenticated principal. `layouts`
has no owner column at all; `GET /layouts/{id}` resolves ownership through
`get_dashboard_id_for_layout` (`src/mkobi/services/layout_service.py:197-210`), which
returns the **first** dashboard associated with the layout — correct only because the
constraint holds 1:1 today.

**Evidence** — Static: `grep created_by src/mkobi` → `src/mkobi/services/dashboard_service.py:88`,
`src/mkobi/db/models/dashboard.py:37`, `src/mkobi/db/models/dashboard.py:68`. Live: the
four probe dashboards all carried `created_by = 13a1f341-…` (the admin) and the column
was never consulted by any of the ~40 authorisation decisions exercised — including
`POST /dashboards/{id}/filters` on a dashboard the caller had no grant on (AUTZ-002)
and `DELETE /dashboards/{id}/access/{admin}` on the owner's own row (AUTZ-001).

**Consequence** — Two effects. First, there is no owner to fall back on: once the
`dashboard_access` row is removed (AUTZ-001) the dashboard has no recorded owner at
all, and no surface can restore one. Second, the column is a live trap — it is
populated, indexed, and `ON DELETE SET NULL` from `users`, so deleting a user silently
erases the only ownership datum while `dashboard_access` rows cascade away with it,
leaving dashboards that no principal can administer and no code path will repair.

**Recommendation** — Two small, separable changes. Either make `created_by` the
authority — compare `current_user.id` against it on the delete, revoke and grant paths,
and treat `dashboard_access` as the sharing layer rather than the ownership layer — or
delete the column and the index and say in `SPEC.md` that an `admin` grant *is* the
ownership record. The second is fewer lines and is what the code currently does; the
first is what the column's presence implies. Do not leave both written and unread.
`get_dashboard_id_for_layout` deserves a comment recording that its correctness depends
on the layout↔dashboard relation being 1:1, or a constraint that enforces it (phase 14).

---

### AUTZ-008 — A second resolution of one identity exists, consults fewer states, and is called by no live path

**Severity** — LOW

**Zone** — "The two resolutions of one identity, and whether they agree"

**Observation** — Two implementations resolve a bearer token to a `UserRead`:
`deps.get_current_user_dependency` (`src/mkobi/api/deps.py:472-576`), used by every
route in the application, and `permissions.get_current_user` /
`permissions._get_current_user_with_session`
(`src/mkobi/core/permissions.py:265-353`). They are independent implementations, not a
delegation. They differ on states:

| State | `deps` | `permissions` |
|---|---|---|
| JWT decode failure | `INVALID_TOKEN` 401 | `AuthenticationError` |
| `jti` revoked in Redis | refused | refused |
| `user_tokens_revoked` | refused | refused **only when `redis_client is not None`** |
| `user.is_active == false` | **refused** (`deps.py:544-550`) | **not consulted** |
| user row absent | refused | refused |

`permissions.get_current_user` additionally defaults `redis_client` to `None`
(`permissions.py:268`), in which case **both** revocation checks are skipped
unconditionally. No production module imports it: `grep get_current_user` over `src/`
returns the definition at `permissions.py:265` and the docstring reference at
`core/permissions.py:38`; the only importer is `tests/test_permissions.py:14`.

**Evidence** — Static, as tabulated. The `is_active` divergence is visible at
`deps.py:544-550` against the absence of any equivalent branch between
`permissions.py:337` and `:345`. Runtime demonstration of the live gate is in AUTZ-005:
the `is_active` check at `deps.py:544` is reachable and would have refused the account
had the flag persisted.

**Consequence** — No effect today, because no live path calls it — which is precisely
why it is LOW rather than higher. The effect is forward-looking and concrete: the
`permissions` variant is the more permissive of the two, it is the one with a shipped
test suite (`tests/test_permissions.py::TestGetCurrentUser`), and it is the one a
developer reaches for when adding a route because `deps` does not export a plain
function. The next caller gets a resolver that skips `is_active` and can be handed
without a Redis client.

**Recommendation** — Delete `permissions.get_current_user` and
`_get_current_user_with_session` and let `deps.get_current_user_dependency` be the only
resolution, moving its `AuthenticationError`/`DashboardPermissionError` module into
`utils/exceptions.py` for `check_role`'s remaining callers. If it must stay, rename it
to make the gap unmissable (`resolve_user_unchecked`) and drop the `redis_client=None`
default so the permissive path cannot be reached by omission. Phase 09 owns the test
that would need to move with it. AUTZ-003's fix should land first so there is one
resolution before a second is deleted.

---

### AUTZ-009 — Unauthenticated `GET /health/detailed` returns a filesystem path, and a raw dependency error when the database is down

**Severity** — LOW

**Zone** — "What each refusal discloses, and where the shapes disagree"

**Observation** — `/health/detailed` (`src/mkobi/app.py:269-307`) is registered with no
dependency. Its `static_files` component unconditionally reports the deployment
filesystem path `components["static_files"]["path"] = "frontend/dist"` with a
`status` derived from `os.path.isdir`, so an unauthenticated caller learns whether the
SPA bundle is present and where it is looked for. Its `database` component, on failure,
sets `components["database"]["error"] = str(e)` — the unfiltered exception text from
the driver, which for an asyncpg/SQLAlchemy connection failure carries the host, port,
database and role. `/health` (`app.py:248-267`) is also unauthenticated but returns a
fixed two-key body with no path and no error text.

**Evidence** — Live, no credential presented:

```
GET /health/detailed -> 200 {"status":"healthy","components":
   {"database":{"status":"connected","type":"postgresql"},
    "static_files":{"status":"unavailable","path":"frontend/dist"}}}
GET /health          -> 200 {"status":"healthy","database":"connected"}
```

**Consequence** — An anonymous caller receives a deployment path and a yes/no on the
frontend bundle. The database-failure branch could not be exercised in this environment
without taking the dev database down, which the brief forbids; what is verified is the
always-on path disclosure, and the error branch is named from its source, not from
observation. Rated LOW because the verified disclosure is a single relative build path
with no credential or host in it; the branch that would carry the connection target is
recorded as a limit in Appendix B, not as a proven effect.

**Recommendation** — Drop `"path"` from the response (or gate the whole endpoint behind
`require_admin_role`, which is the smaller change if the payload is wanted). Whatever is
kept, replace `str(e)` with the fixed `"status": "disconnected"` string — the driver
message belongs in the log line that already accompanies it at `app.py:293`, not in a
body reachable without a credential.

---

## Distribution

The findings land on one component more than any other: the dashboard access-control
surface. `dashboards_access.py` is 227 lines with three endpoints, and all three are
gated identically — by authentication alone — which produces AUTZ-001. The next heaviest
concentration is the *inline* authorisation re-implementation in route modules: eleven
call sites raise their own `AppException` with a locally chosen `ErrorCode`, which is the
single cause behind AUTZ-006 and contributes to AUTZ-003. Everything else is a single
site. By role: every CRITICAL is reachable by the lowest role the system admits
(`viewer`), and nothing in this phase requires a system administrator.

- `src/mkobi/api/routes/` — AUTZ-001, 002, 003, 004, 006 (and AUTZ-008's live half)
- `src/mkobi/core/permissions.py`, `src/mkobi/api/deps.py` — AUTZ-003, AUTZ-008
- `src/mkobi/services/user_service.py` via `api/routes/admin.py` — AUTZ-005
- `src/mkobi/app.py` — AUTZ-009
- `src/mkobi/db/models/dashboard.py`, `db/repositories/access_repo.py` — AUTZ-007

## Cross-Finding Analysis

Three findings share one cause. `dashboard_access` is treated as an ordinary
user-writable collection rather than as the authorisation decision itself, and nothing
in the layer above it treats changing that collection as a privileged act. That single
mis-framing produces **AUTZ-001** (the collection is readable and mutable by anyone),
**AUTZ-007** (it is therefore the sole ownership record, with no fallback column), and
contributes to **AUTZ-002** (the sibling filter-binding collection, which nobody guards
at all). Fixing the framing once — one dependency that answers "may this principal
administer this dashboard", installed on every path that mutates dashboard state —
closes all three together; fixing them separately leaves the same hole open on the next
route someone adds.

AUTZ-003 and AUTZ-006 are independent of each other and of the group above: they are
about *which* predicate is consulted and *how* a refusal is rendered, not about whether
one is consulted.

## Roadmap

1. **Close TXN-001 first** (phase 03). AUTZ-005 is a consequence of it and cannot be
   verified as fixed until the role and `is_active` writes actually persist. Must be
   true before: any claim that deactivation works.
2. **Install one dashboard-administration gate** and put it on every dashboard-state
   mutation path: `dashboards_access.py` (all three), `dashboards_filters.py` (bind,
   unbind), `dashboards_graphs.py` (replace `require_admin_role`). Closes AUTZ-001 and
   AUTZ-002 together and is the step AUTZ-003 and AUTZ-007 both depend on. Must be true
   before: step 4 can be verified without a self-grant shortcut.
3. **Settle the authority question** (AUTZ-003) and write the precedence into `SPEC.md`.
   Must be true before: step 4, or the two gates will still disagree.
4. **Constrain the child lookup** in `data.py:120` (AUTZ-004) and decide the ownership
   column (AUTZ-007). Both are single-site changes and are safe to land in either order
   after step 2.
5. **Normalise the refusal** (AUTZ-006), with phase 13 told first — the client's
   `errorHandler.ts` consumes three codes for one meaning today.
6. **Remove the second token resolution** (AUTZ-008) and slim the health payload
   (AUTZ-009). Both are cleanup; neither blocks anything.

## Rollout Safety

Steps 1 and 2 are the only ones that change what a legitimate caller can do. Step 1
makes `PATCH /admin/users/{id}/role` and `.../active` start persisting — any
operational habit built around the current behaviour (a role change appearing to succeed
and then reverting) will now hold, and the reactivation key deletion in step 1 means
accounts currently wedged by `user_tokens_revoked` will recover on their next
reactivation call. Existing access tokens remain valid across step 1, so nobody is
logged out by it. Step 2 will start refusing the calls that currently succeed, and the
first callers to notice will be the frontend's own dashboard screens
(`/dashboards/{id}/filters`, `/dashboards/{id}/graphs`) for any principal whose
`users.role` is not `admin` — if AUTZ-003's precedence decision keeps the global role as
the authority for those two routes, verify the dashboard-administrator persona against
the frontend before release. Verify after step 2: the AUTZ-001 and AUTZ-002 probe
sequences both return 403 for a zero-grant `viewer`, and the same two sequences still
return 200 for a system administrator. Revert by reverting the commit; no data written by
these steps is transformed, only newly refused, so a revert restores the previous
behaviour with no cleanup.

## Appendices

### Appendix A — Assessment of the findings deferred into this phase

**QLT-001** (`POST /dashboards/{id}/access` returns HTTP 200 with the requested
permission while writing nothing on an existing row) — **confirmed and extended.**
Re-verified live on dashboard `ba58425d-…`: with `admin` already stored, a request for
`view` returned `200 {"permission":"view"}` and `GET /dashboards/{id}/access` still read
`admin`; a request for `read` returned `200` on the existing row (the no-op branch
returns before PostgreSQL is touched) and `superadmin` was rejected at
`_validate_permission` with 422 `VALIDATION_ERROR`. The validator's `read`-on-a-new-row
500 is consistent with this: the row existed here, so `grant_access` returned at
`access_repo.py:57-63` without ever reaching the enum. This phase adds the access
consequence the deferral was for: because `grant_access` returns the existing row
unchanged, and because AUTZ-001 establishes that the same route also *deletes* and
*lists* these rows without consulting the caller, a principal that has self-granted once
can never be demoted by the interface either. QLT-001 remains phase 08's; this phase
owns only that the surrounding surface is unguarded (AUTZ-001).

**QLT-002** ("All operations require admin role" / "Available only to owners" declared,
neither enforced) — **confirmed.** Re-verified live: a self-registered `viewer` with zero
grants obtained `200 {"permission":"admin"}` on an admin-owned dashboard from
`POST /dashboards/{id}/access`, and the row landed in `dashboard_access`. The
validator's correction is accepted: `grant_access` has two callers, the route and
`dashboard_service.py:104`. This phase's extension is the other two endpoints of the same
module, which carry the identical defect and were not in QLT-002's evidence — see
AUTZ-001. The declared-contract contradiction stays with phase 08 as ruled.

**AUTH-004** (password rotation withdraws nothing; `/auth/refresh` emits no `Set-Cookie`
so the 7-day credential is never rotated) — **not owned by this phase, and it should
not be.** The per-request gate is correct: `deps.get_current_user_dependency`
consults both `jti` revocation and `user_tokens_revoked` on every request
(`deps.py:504-532`), and `/auth/refresh` independently consults
`is_user_tokens_revoked` (`auth.py:368`). What is missing is that nothing ever writes
the revocation on a password reset and that no re-issue path rotates the refresh cookie
— that is the issuance of a credential and the withdrawal of one, which phase 04's scope
boundary reserves (`token issuance and expiry, and password and one-time-credential
handling`). One consequence is worth phase 04's attention because it is only visible
from this side: AUTZ-005 shows the gate already has a working withdrawal mechanism
(`user_tokens_revoked`) that the deactivation path uses and the reset path does not, so
the omission is a missing call rather than a missing capability.

**AUTH-003** (`force_password_change` written by both issuing paths, read by nothing
server-side) — **acknowledged as phase 04's; recorded here in the account-state matrix
because Block 7 asks which states are enforced against returned.** Live confirmation:
after `POST /admin/registration-requests/{id}/approve`, `GET /auth/me` for the new
account returned `200` with `"force_password_change":true`, and the same account passed
`GET /admin/users` and `GET /admin/registration-requests` as an admin because its role
was separately set to `admin`. Not re-filed.

### Appendix B — What this environment could not settle

- **The database-failure branch of `/health/detailed`** (AUTZ-009). Forcing it means
  stopping the dev database, which the brief forbids while peers may be using the stack.
  The always-on path disclosure was observed; the `str(e)` branch is asserted from its
  source (`app.py:296`) and is not claimed as reproduced.
- **The transport requirement of the refresh cookie.** `cookie_secure` defaults to
  `True` (`config.py:446`) and is overridden to `false` for HTTP development
  (`config.py:444`). Whether the *deployed* tier can carry a `Secure` cookie is phase
  10's; this phase verified only what the server sets.
- **`layout_id → dashboard_id` multiplicity.** `get_dashboard_id_for_layout` returns the
  first row. The relation is 1:1 in the dev data, so the "first" is also the only one;
  a layout attached to two dashboards would resolve to one of them arbitrarily. Whether
  the schema permits that is phase 14's; it is named here as the assumption AUTZ-007's
  recommendation depends on.
- **Whether a non-`admin` `users.role=editor` account exists in production.** Every
  account the probes could create had role `viewer`, because AUTZ-005/TXN-001 prevent
  role promotion through the API. AUTZ-003's consequence is stated for the
  grant-holding-`viewer` case, which *was* exercised, and not for the
  role-`editor`-without-grant case, which could not be constructed in this environment.

### Appendix C — Surfaces enumerated and their predicate

`✓` = decision present and correct at its granularity; `✗` = none installed.

| Surface | Predicate | Verdict |
|---|---|---|
| `GET /dashboards/` , `POST /dashboards/` | `AdminUser` | ✓ |
| `GET /dashboards/my` | grant, in-query (`dashboard_repo.get_by_user`) | ✓ |
| `GET /dashboards/{id}` | grant (`get_dashboard`, admin bypass) | ✓ (AUTZ-006 on disclosure) |
| `PUT /dashboards/{id}` | grant `edit` | ✓ |
| `DELETE /dashboards/{id}` | grant `admin` | ✓ (AUTZ-006) |
| `POST|GET|DELETE /dashboards/{id}/access*` | — | ✗ **AUTZ-001** |
| `POST|DELETE /dashboards/{id}/filters*` | — | ✗ **AUTZ-002** |
| `GET /dashboards/{id}/filters` | `require_dashboard_read_access` | ✓ |
| `POST /dashboards/{id}/graphs` | `require_admin_role` | ✓ but wrong authority (AUTZ-003) |
| `GET /dashboards/{id}/graphs` | `require_dashboard_read_access` | ✓ |
| `GET /dashboards/{id}/filter-values` | `require_dashboard_read_access` | ✓ |
| `GET /graphs/` | grant, in-query | ✓ |
| `GET|PUT|DELETE /graphs/{id}` | grant via the graph's own `dashboard_id` | ✓ |
| `POST /graphs/` | grant `admin` on `graph.dashboard_id` | ✓ (AUTZ-003) |
| `GET /layouts/` | grant, in-query | ✓ |
| `GET /layouts/{id}` | grant, with orphan→404 | ✓ |
| `POST|PUT|DELETE /layouts` | `role == admin` inline | ✓ |
| `GET /processing-configs/{id}` | grant `view` | ✓ |
| `PUT|DELETE /processing-configs/{id}` | grant `edit` | ✓ |
| `GET /data/aggregated` | grant `view` on `dashboard_id` | ✓ (AUTZ-004 on the child) |
| `POST /upload/{id}` | `require_editor_role` **and** grant `edit` | ✓ (AUTZ-003) |
| `GET /upload/status|result/{task_id}` | grant `view` on `log.dashboard_id` | ✓ |
| `GET /users/`, `POST /users/`, `PUT|DELETE /users/{id}` | `AdminUser` | ✓ |
| `GET /users/{id}` | self or `AdminUser` | ✓ |
| `DELETE /users/me` | `current_user.id` only | ✓ |
| all `/admin/*` (8 endpoints) | `AdminUser` | ✓ |
| `POST /auth/register` | `require_admin_role` | ✓ |
| `POST /auth/login`, `/refresh`, `/register-request` | — (public) | n/a |
| `GET /auth/me`, `/logout`, `/change-password` | `get_current_user_dependency` | ✓ |
| `GET /processing-logs/` (2) | `require_admin_role` | ✓ |
| `POST /client-errors` | — (public, rate-limited) | see below |
| `GET /health`, `/health/detailed` | — (public) | AUTZ-009 |

**Ambient credentials (Block 11) — positive result, recorded so it is not re-asked.**
The only credential a browser attaches without a script presenting it is
`mkobi_refresh_token`, set by `set_secure_cookie` with `httponly=True`,
`COOKIE_SAMESITE="strict"` (`src/mkobi/core/security.py:43-45`) and `secure` from
`config.app.cookie_secure`. It is read by exactly one surface, `POST /auth/refresh`
(`auth.py:297`) and `POST /auth/logout` (`auth.py:441`), both of which are non-mutating
with respect to server state. Every other surface authenticates on the `Authorization`
header, which a browser does not attach automatically, and every mutating surface is on
that header only. No server-side Origin or CSRF re-check exists on any route — none is
needed while `SameSite=strict` holds, and the refresh response sets no cookie, so there
is no cross-site write primitive. CORS is `allow_credentials=True` with
`allow_origins=config.cors_origins` (`app.py:218-224`); the dev `.env` lists two explicit
localhost origins and `config.py:676-681` refuses `*` in production, so Starlette never
reflects an arbitrary origin. Which origins are honoured per environment is phase 02's.

**Mutation entry points carrying no acting identity (Block 6).**
`AccessRepository.grant_access` / `revoke_access` (only `user_id`, `dashboard_id`,
`permission`); `DashboardFilterRepository.bind_filter` / `unbind_filter`; 
`FilterRepository`, `GraphRepository`, `LayoutRepository` methods (correctly reached only
through routes that do decide); `DataService.process_upload` accepts `user_id` and does
consult it (`data_service.py:118-132`), as do `get_processing_status` (`:328`) and
`get_processing_result` (`:362`) — the `user_id` argument is read in all three, which is
the in-module precedent the missing actor parameters should copy.

**List paths (Block 5).** Six list surfaces: `GET /admin/users`, `GET /users/`,
`GET /processing-logs/`, `GET /graphs/`, `GET /layouts/`, `GET /dashboards/my`. All six
scope by the predicate in the query, not row by row; none carries a row bound other than
`processing-logs`' `limit` (max 1000). **No multi-object mutation surface exists** —
every mutating endpoint in the application names exactly one target, so the empty set is
stated rather than enumerated. For one identity and one object the list and
single-object answers agreed on every pair exercised (`/dashboards/my` vs
`/dashboards/{id}`; `/graphs/` vs `/graphs/{id}`; `/layouts/` vs `/layouts/{id}`), except
where AUTZ-003 records the deliberate divergence for the elevated level.

**Account-state matrix (Block 7).**

| State | Written by | Read by | Server-enforced? | Cleared by reverse path? |
|---|---|---|---|---|
| `users.role` | `PATCH /admin/users/{id}/role` | `require_admin_role`, `require_editor_role`, inline `role != ADMIN` | yes, but the write never persists (AUTZ-005) | n/a |
| `users.is_active` | `PATCH /admin/users/{id}/active` | `deps.py:544` | **no** — write never persists (AUTZ-005) | n/a |
| Redis `user_tokens_revoked` | `PATCH .../active` (only) | `deps.py:526`, `auth.py:368` | yes | **no** (AUTZ-005) |
| Redis `revoked:{jti}` | `/auth/logout` only | `deps.py:506`, `auth.py:447` | yes | logout-only |
| `force_password_change` | approve + reset | **nothing** | no — returned to the caller only | no (AUTH-003, phase 04) |
| `dashboard_access.permission` | `POST /dashboards/{id}/access` | `check_dashboard_access`, `get_dashboard` | yes | only by the unguarded `DELETE` (AUTZ-001) |
| `registration_requests.status` | approve / reject | `admin.py:299` | yes | n/a |

**Baseline.** `git rev-parse HEAD` = `7342e9e7bae99adf248339bb4a062b67a06fb97c`,
working tree dirty, both recorded before any file was read. `src/mkobi/config.py` and
`docker/docker-compose.yml` were modified under this phase by the concurrent
remediation programme; every anchor those files contribute (`cookie_secure` at
`config.py:446`, `cors_origins` at `:559`, `COOKIE_*` at `core/security.py:43-45`,
`allow_origins`/`allow_credentials` at `app.py:218-224`) was re-read against the working
tree afterwards and is quoted from the current text. No file was created, edited, staged,
committed, reverted or stashed by this phase.

**Runtime evidence method.** The access matrix was driven over HTTP against the running
dev stack on `http://localhost:8010` (`docker compose -p mkobi`, services `app`/`db`/
`redis` left in the state they were found). One admin session and one
self-registered `viewer` (`58e988f1-a187-41ca-9802-479e43079d4f`, created via the
public `POST /auth/register-request` → admin approve → `GET /admin/temp-passwords/{token}`
path) drove every probe. The `login:{ip}` rate-limit key was deleted twice between probe
batches because AUTH-001 (phase 04) keys the limiter on the proxy address and the
counter had a 300-second TTL. Cleanup, verified against zero rows afterwards: 4 probe
dashboards, 4 probe graphs, 1 layout, 1 user, 1 `dashboard_filters` row and 1
`registration_requests` row removed; the Redis keys `user_tokens_revoked:58e988f1-…`,
`login:172.21.0.1` and any temp-password entry deleted. Nothing created by another
agent was touched; the two pre-existing `filters` rows were bound and unbound by API and
returned to their original state. Rate limiting is autouse-stubbed in
`tests/conftest.py:328-332`, so every 429 seen here was live and none of these results
would appear in the suite — relevant to phase 09's coverage verdict.
