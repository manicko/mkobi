---
phase: 12-authorization
executed: 2026-09-30
executor: validator
problems-only: true
findings: 5
by-severity:
  CRITICAL: 0
  HIGH: 1
  MEDIUM: 1
  LOW: 3
audited-findings: 9
audited-namespace: AUTZ-
validation-namespace: VAL-12-
baseline: 7342e9e7bae99adf248339bb4a062b67a06fb97c
written-at: 05f2779323c1746c8945f63882b187bcb2d7b608
---

# Phase 12 — Validated Findings

## Summary

The authorization report was re-derived from the executing path at `7342e9e7bae99adf248339bb4a062b67a06fb97c`,
which was `HEAD` throughout the probe window; `HEAD` moved to `05f2779` during the run and the drift was
checked — no authorization-path source file moved, the one changed file on the anchor path
(`src/mkobi/config.py`) leaves `VAL-12-002` unchanged, and the runtime probed was the pre-`bde2ddd`
build, which is stated in the coverage ledger rather than left implicit. Every one of the nine `AUTZ-`
findings was re-anchored mechanically and every load-bearing claim was
re-tested live over HTTP against the dev stack, on a throwaway `viewer` with zero grants and on two
throwaway admin-owned dashboards created for the purpose. All nine reproduce: no finding is a false
alarm, none is stale, and no band is changed. Both CRITICALs were attacked hardest — AUTZ-001's read,
its delete, and the claim that `dashboard_access` is the only ownership record all reproduce, and
AUTZ-002's 200-on-a-foreign-dashboard bind reproduces independently of the 500 the input leans on.
All four deferred-finding rulings are upheld — three confirmed, AUTH-004 not re-filed on corrected
grounds, and AUTH-003's decision not to re-file judged correct. The input's positive ambient-credential
result is upheld, but one of its three supporting sentences is wrong and is recorded as `VAL-12-001`.
Five defects in the input report itself were found: `VAL-12-001` through `VAL-12-005`.

## Disposition Tally

| ID | Band carried | Disposition | Basis |
|---|---|---|---|
| AUTZ-001 | CRITICAL | confirmed | reproduced live; band unchanged |
| AUTZ-002 | CRITICAL | confirmed | reproduced live; inference corrected, effect strengthened |
| AUTZ-003 | HIGH | confirmed | both responses reproduced; authority ordering newly established |
| AUTZ-004 | HIGH | confirmed | reproduced live |
| AUTZ-005 | HIGH | confirmed | reproduced live; roadmap step incomplete (`VAL-12-005`) |
| AUTZ-006 | MEDIUM | confirmed | four renderings reproduced; a fifth omitted by the input |
| AUTZ-007 | MEDIUM | confirmed | static claim and live effect both reproduced |
| AUTZ-008 | LOW | confirmed | tabulated divergences reproduced; one citation wrong |
| AUTZ-009 | LOW | confirmed | always-on disclosure reproduced; error branch unsettled |
| QLT-001 (phase 08) | — | confirmed; extension confirmed and scoped | re-derived to the field level |
| QLT-002 (phase 08) | — | confirmed; extension confirmed | reproduced |
| AUTH-004 (phase 04) | — | not re-filed; ruling upheld on corrected grounds | reproduced |
| AUTH-003 (phase 04) | — | not re-filed; **the decision not to re-file was correct** | re-derived |

Tally: 9 confirmed, 0 re-typed, 0 re-graded, 0 merged, 0 not substantiated, 0 unsettled among the
audited findings. 3 deferred rulings returned. 5 validation-level findings filed (`VAL-12-001`
… `VAL-12-005`), 1 re-graded HIGH, 1 MEDIUM, 3 LOW.

## Findings — audited namespace `AUTZ-` (validated)

### AUTZ-001 — Any authenticated principal reads any dashboard's access-control list and deletes any grant on it, including an owner's

**Verdict** — confirmed. Band carried unchanged at CRITICAL. Every cited anchor resolves at `7342e9e`.
No re-grade.

**Severity** — CRITICAL

**Zone** — "Single-object paths: is the caller consulted, and what the response discloses first"

**Observation** — `src/mkobi/api/routes/dashboards_access.py:130-171` and `:174-227` resolve exactly and
declare only `current_user: CurrentUser`; neither reads it. `DashboardService.get_dashboard_access_list`
(`services/dashboard_service.py:442-478`) and `revoke_access` (`:403-440`) accept `(dashboard_id, db)`
and `(dashboard_id, user_id, db)` and carry no acting identity. `AccessRepository.revoke_access`
(`db/repositories/access_repo.py:89-130`) resolves its target by the bare `(user_id, dashboard_id)`
pair and deletes it. The claim that `dashboard_access` is the only ownership record is reproduced too:
a search for `created_by` over `src/` returns exactly three hits — the write at
`services/dashboard_service.py:88`, the index at `db/models/dashboard.py:37`, the column at
`db/models/dashboard.py:68` — and no predicate, query or response model reads it.

**Evidence** — A throwaway self-registered `viewer` (`role=viewer`, zero `dashboard_access` rows) against
an admin-owned dashboard it had no relationship to:

```
GET    /api/v1/dashboards/aee0198d-.../access   -> 200 [{"user_id":"13a1f341-…",
                                                     "dashboard_id":"aee0198d-…","permission":"admin"}]
DELETE /api/v1/dashboards/aee0198d-.../access/13a1f341-…
                                                   -> 200 {"message":"Access revoked successfully"}
GET    /api/v1/dashboards/aee0198d-.../access   -> 200 []      (as the zero-grant viewer)
GET    /api/v1/dashboards/aee0198d-.../access   -> 200 []      (as the dashboard's own admin)
```

The owner's grant was gone while `dashboards.created_by` still named the owner and nothing consulted
it. One item the input did not record: `GET /dashboards/11111111-…/access` on a non-existent dashboard
also answers `200 []`, so the ACL-read surface has no existence check either.

**Consequence** — As filed. Any of the seven authenticated accounts can read the full ACL of any
dashboard and delete any grant on it, including the owner's; the same endpoint that permits the
removal enumerates the target ids to aim at.

**Recommendation** — Executable as written. The named target exists and is stable
(`api/deps.py:788-829` `require_dashboard_admin_access`, already the pattern at `api/routes/graphs.py:96-101`),
and applying it removes the defect. The input's blocker check is verified rather than accepted: no
shipped test asserts the open behaviour. `tests/test_dashboard_access.py` is the only test naming the
access module and it exercises the repository's cascade delete through `DELETE /dashboards/{id}`,
never the ACL routes; `tests/test_resource_access_control.py` covers `PUT` and `DELETE
/dashboards/{id}` only. Nothing encodes the defect, so nothing blocks. One addition: because the
ACL-read surface also answers `200 []` for an absent dashboard, roadmap step 5 should normalise the
read surface's absence case in the same change.

---

### AUTZ-002 — Filter binding on any dashboard is rewritten by any authenticated principal, and by no decision at all

**Verdict** — confirmed. Band carried unchanged at CRITICAL. The input's inference from the 500 is
corrected below, and the corrected inference strengthens the finding.

**Severity** — CRITICAL

**Zone** — "Mutation entry points that receive no acting identity"

**Observation** — `src/mkobi/api/routes/dashboards_filters.py:32-127` resolves exactly. Both mutating
endpoints declare `current_user: CurrentUser` and never read it; no `check_dashboard_access` call
exists in the file; the only predicate is on the third endpoint at `:140`
(`require_dashboard_read_access`). The module docstring at `:4` and the endpoint descriptions at `:36`
and `:86` do say "All operations require admin role" / "Requires admin role". `bind_filter` and
`unbind_filter` take identifiers only and no actor, as filed; the unbind path never resolves
`dashboard_id` at all.

**Correction to the input's inference.** The 500 is produced by the foreign-key violation on
`dashboard_filters.dashboard_id` (`db/models/filters.py:87`, `ForeignKey("dashboards.id",
ondelete="CASCADE")`, non-deferrable), surfaced by the route's `except Exception` at
`dashboards_filters.py:68-79`. It proves the **existence** check is missing; it does not prove the
**authorization** check is missing, because no authorization check exists on the path that never
reaches the database either. The authorization claim is proved instead by the 200 on an existing
foreign dashboard, exercised independently. Both halves of the input's fused sentence are true and
both are separately evidenced.

**Does the 500 leak existence?** Yes, and the input does not say so: the same request answers `200`
against an existing dashboard and `500` against a non-existent one, so any authenticated principal can
partition the dashboard-id space on this surface. That is a disclosure the input filed as evidence.

**Evidence** — The zero-grant `viewer` against an admin-owned dashboard on which it holds no grant:

```
POST   /api/v1/dashboards/9e7e37e7-.../filters?filter_id=3fd75bcc-...  -> 200 {"message":"Filter bound to dashboard","bound":true}
   psql: dashboard_filters now holds (9e7e37e7-…, 3fd75bcc-…)
GET    /api/v1/dashboards/9e7e37e7-.../filters                         -> 403 PERMISSION_DENIED
DELETE /api/v1/dashboards/9e7e37e7-.../filters/3fd75bcc-...            -> 200 {"message":"Filter unbound from dashboard"}
POST   /api/v1/dashboards/11111111-.../filters?filter_id=3fd75bcc-...  -> 500 INTERNAL_ERROR "Error binding filter"
POST   /api/v1/dashboards/9e7e37e7-.../filters?filter_id=22222222-...  -> 404 FILTER_NOT_FOUND
```

The last line records a fact the input omits: `bind_filter_endpoint` **does** check filter existence
(`dashboards_filters.py:54-58`), so the asymmetry is precise — the filter is existence-checked, the
dashboard is not.

**Consequence** — As filed, plus the existence oracle: any authenticated principal can add or remove a
filter on any dashboard, including one owned by another user, with no trace of who did it
(`dashboard_filters` carries no actor column), and can distinguish existing from non-existent dashboard
ids on the same surface.

**Grading note.** AUTZ-002 is held at CRITICAL while AUTZ-004 is held below it on the stated grounds
that no data values cross. The two are coherent: AUTZ-002 lets a stranger alter another owner's
dashboard configuration; AUTZ-004 reveals only a chart's name, type and rendering config. On the
input's own disclosure axis AUTZ-002 sits above AUTZ-004, so neither band is re-graded.

**Recommendation** — Executable. `require_dashboard_admin_access` exists at `api/deps.py:788-829`; the
dashboard-existence check the input points at already exists at `services/data_service.py:106-116` and
can be copied. The input's split — this phase owns the missing gate, phase 08 owns the
declared-contract contradiction — is the correct seam and pre-empts no other phase. Adding the
existence check also removes the 200/500 oracle.

---

### AUTZ-003 — Two authorities decide the same question and disagree: `users.role` admits one route and refuses the twin route for the identical principal

**Verdict** — confirmed, and extended on the one question the input left open: which authority the
system actually treats as authoritative downstream. Band carried unchanged at HIGH.

**Severity** — HIGH

**Zone** — "The two sources of authority, and which one decides"

**Observation** — Both gates are where the input says they are: `api/routes/graphs.py:96-101` checks
`check_dashboard_access(required_permission="admin")` on `graph.dashboard_id`, and
`api/routes/dashboards_graphs.py:56` installs `dependencies=[Depends(require_admin_role)]`;
`api/routes/upload.py:75` declares `EditorUser` and `services/data_service.py:118-132` then checks the
grant for `edit`. `permissions.py:125-155` and `:86-122` do not consult each other, and no precedence
is written down anywhere in `docs/` or `SPEC.md`.

**Which authority wins downstream — resolved, not left open.** The input records the divergence and
stops. The executing path decides it:

1. The 201-written chart **persists**. In this run the graph created through `POST /graphs/` by a
   `role=viewer` principal holding `dashboard_access=admin` was returned by `GET
   /dashboards/{id}/graphs`, by `GET /graphs/`, accepted by `PUT /graphs/{id}` (rename persisted), and
   was present in the `graphs` table. The 403 from the nested twin wrote nothing at all.
2. Every other graph operation already follows the grant, not the role: `PUT /graphs/{id}` at
   `graphs.py:333` and `DELETE /graphs/{id}` at `graphs.py:443` both call `check_dashboard_access(...,
   required_permission="admin")` against `existing_graph.dashboard_id`. Four of the five graph
   operations use the grant; only the nested create uses the role.
3. The set difference between the two gates is exactly `{dashboard_access=admin ∧ users.role≠admin}`.
   `check_dashboard_access` grants on `role==admin` **or** an `admin` grant
   (`core/permissions.py:176-185`); `require_admin_role` grants on `role==admin` alone
   (`api/deps.py:582-606`). The grant gate is therefore strictly the more permissive of the two, and
   the only principals it admits and the role gate refuses are dashboard administrators whose global
   role is below admin.

Consequence of (3): the divergence can only ever **refuse** a legitimate dashboard administrator. It
is not an escalation path in either direction — no principal gains an operation through the pair that
either gate alone would deny. That is a determined direction, not a neutral absence of precedence, and
it makes the input's recommended change (move the nested routes onto the grant) the only option
consistent with what already persists. This is recorded as `VAL-12-004`.

**Evidence** — One principal, `users.role=viewer`, `dashboard_access.permission=admin`, two identical
create-chart calls on the same dashboard:

```
POST /api/v1/graphs/                        -> 201 {"id":"2adc38be-…","name":"val12-via-global",…}
POST /api/v1/dashboards/aee0198d-.../graphs -> 403 {"code":"INSUFFICIENT_PERMISSIONS","detail":"Admin access required"}
PUT  /api/v1/graphs/2adc38be-...            -> 200 {"name":"val12-renamed-by-viewer",…}
GET  /api/v1/dashboards/aee0198d-.../graphs -> 200 [{"id":"2adc38be-…","name":"val12-renamed-by-viewer",…}]
POST /api/v1/upload/aee0198d-...            -> 403 {"code":"INSUFFICIENT_PERMISSIONS","detail":"Editor access required"}
psql graphs: (2adc38be-…, 'val12-renamed-by-viewer', aee0198d-…)
```

**Consequence** — A principal holding the dashboard's own `admin` grant cannot use the nested
create-chart route or upload data to a dashboard it administers, while it can create, rename and delete
charts on that same dashboard through the global routes. The frontend, the only consumer, calls the
nested routes. The 403 is a false statement about the system's own rules, because the object it
refuses to create is created and served by its own sibling.

**Recommendation** — Executable and now unambiguous in direction. Both named targets exist and are
exported and currently unused for these two paths (`api/deps.py:744-785` `require_dashboard_write_access`,
`:788-829` `require_dashboard_admin_access`). The input's cross-reference to phase 13 for the client-side
consumer is correct and is not pre-empted here.

---

### AUTZ-004 — `/data/aggregated` resolves `graph_id` without constraining it to the `dashboard_id` the access check was performed against

**Verdict** — confirmed. Band carried unchanged at HIGH.

**Severity** — HIGH

**Zone** — "The cross-aggregate boundary: what one aggregate's identifier can reach through another's"

**Observation** — `src/mkobi/api/routes/data.py:39-197` resolves exactly; the single authorization
decision is against the `dashboard_id` query parameter at `:88-93`, and the graph is resolved by its
own identifier at `:120` with nothing constraining `single_graph.dashboard_id` to the authorised
dashboard. The input's qualifier is verified and is the reason this is not higher: the data query
itself is correctly constrained — `services/data_service.py:208-210` passes `dashboard_id=` into
`AggregatedDataRepository.get_by_graph_id`, which filters on both
(`db/repositories/aggregated_data_repo.py:147-155`). Only the graph row crosses.

**Evidence** — A principal authorised on dashboard `aee0198d-…` requesting a chart that belongs to
dashboard `9e7e37e7-…`, on which it holds no grant of any level:

```
GET /api/v1/data/aggregated?dashboard_id=aee0198d-…&graph_id=68420436-…
  -> 200 {"graphs":[{"graph_id":"68420436-…","type":"pie","name":"val12-foreign-chart",
                     "data":[],"layout":null,
                     "config":{"x":"secretDim","y":"secretMetric"}}]}
```

`data: []` confirms the data scope held; `name`, `type` and `config` did not. The control request with
no `graph_id` returned only the authorised dashboard's own chart, so the response shape is not simply
echoing whatever is asked for.

**Consequence** — Any authenticated principal with view on **any** dashboard resolves the identity and
rendering configuration of a chart on a dashboard it cannot see, given the chart UUID. The input's
grading rationale — the identifier is a UUID that no surface enumerates for a foreign dashboard, and
the disclosed fields are name, type and config rather than data values or dashboard configuration — is
re-derived and accepted, so HIGH is not re-graded.

**Recommendation** — Executable. The named anchor `data.py:122` is the `if single_graph is None:` branch
immediately after the unconstrained lookup, and the error code `GRAPH_NOT_FOUND` already exists and is
raised eight lines below. One conditional closes it.

---

### AUTZ-005 — Deactivation reports success, does not deactivate, and cannot be undone

**Verdict** — confirmed in substance. Band carried unchanged at HIGH. One line of quoted evidence did
not reproduce (`VAL-12-003`), and the roadmap step that closes it is incomplete (`VAL-12-005`,
re-graded HIGH).

**Severity** — HIGH

**Zone** — "Account state: which states are consulted, on which surface, and by which resolution"

**Observation** — `src/mkobi/api/routes/admin.py:137-193` resolves exactly and calls
`UserService.update_user_active_status` (`services/user_service.py:248-284`), which executes
`user_repo.update(...)` and returns without committing; neither the service nor the route commits, and
`db/session.py:85-87` shows `get_session()` closing without a commit. The reverse direction is the same
endpoint with no `else` branch, and there is **no code anywhere in `src/` that deletes
`user_tokens_revoked`**: the key appears at `core/security.py:535` (`setex`, the write) and `:552`
(`exists`, the read) and nowhere else. The sibling `PATCH /admin/users/{id}/role`
(`admin.py:62-98`) is inert in the same way, through `update_user_role` at `user_service.py:234`.

**Evidence** — Admin-driven, one account throughout:

```
PATCH /admin/users/fc5727cf-.../active {"is_active":false}
  -> 200 {"is_active":false,"updated_at":"2026-09-30T19:17:30.022956Z",…}
psql:  is_active = t, updated_at = 2026-09-30 19:16:50.892218+00   <- never persisted
POST /auth/login                -> 200 (the "deactivated" account still authenticates)
redis EXISTS user_tokens_revoked:fc5727cf-…  -> 1   (TTL 604798)
GET  /auth/me (pre-deactivation token) -> 401 TOKEN_REVOKED
PATCH /admin/users/fc5727cf-.../active {"is_active":true}
  -> 200 {"is_active":true,"updated_at":"2026-09-30T19:17:32.650120Z",…}
psql:  is_active = t, updated_at = 2026-09-30 19:16:50.892218+00   <- still never persisted
redis EXISTS user_tokens_revoked:fc5727cf-…  -> 1   (unchanged, no code path clears it)
POST /auth/login                -> 200 (fresh access token minted)
GET  /auth/me (post-reactivation token) -> 401 TOKEN_REVOKED
PATCH /admin/users/fc5727cf-.../role {"role":"editor"}
  -> 200 {"role":"editor",…}   psql: role = viewer
```

The permanent lockout is exact: after reactivation the account authenticates successfully and every
token it receives is refused.

**Does the pre-existing state for a never-revoked user differ? — yes, and the boundary is clean.**
For an account no admin ever deactivated, `user_tokens_revoked:{id}` does not exist, so
`deps.get_current_user_dependency` (`api/deps.py:526`) and `/auth/refresh` (`auth.py:368`) do not
refuse it, and its stored `is_active` is `true`, so `deps.py:544` passes. Nothing else is wrong with
such an account. The blast radius today is exactly: any account an admin deactivates is permanently
locked out afterwards, and no other account is affected.

**Consequence** — As filed, with the effect of the missing commit narrowed: today the deactivation
control does nothing except write a key that refuses every token for that account, including tokens
minted afterwards by a successful login, and no path can undo it. The persistence defect and the
missing key deletion are two independent halves; either alone leaves the control unusable.

**Recommendation** — Executable, but the ordering claim must be widened; see `VAL-12-005`. Committing
the unit of work is phase 03's TXN-001 and phase 12 does not re-file it. Adding the reverse-path key
deletion and the two INFO log lines is in-scope here. Nothing shipped asserts the present behaviour
(verified: no test names `update_user_active_status` or `user_tokens_revoked`).

---

### AUTZ-006 — One refusal answered with three error codes and two disclosure levels, with no stated reason on either side

**Verdict** — confirmed. Band carried unchanged at MEDIUM. The input's table is incomplete: a fifth
rendering of the same class exists and was reproduced.

**Severity** — MEDIUM

**Zone** — "What each refusal discloses, and where the shapes disagree"

**Observation** — The four-code spread is real and no construction forces agreement: each call site
raises its own `AppException` inline. Every anchor in the input's table that was re-opened resolves to
the mechanism it is cited for — `dashboards_crud.py:279-283` (ACCESS_DENIED), `:362` (PERMISSION_DENIED),
`:457` (ACCESS_DENIED), `layouts.py:234` (the "Orphaned layout - return 404 to prevent enumeration"
precedent; the source uses a hyphen, not the em dash the input quotes), `layouts.py:242-247`,
`filter_values.py:55`, `users.py:179`. Two rows are off by a few lines and resolve to the surrounding
statement rather than the raise: `graphs.py:265` is `except Exception as e:` (the PERMISSION_DENIED
raise is at `:258`) and `layouts.py:254` is the closing paren of the log call (the raise is at `:255`).

**A fifth rendering the input omits.** `POST /dashboards/{id}/access` against a non-existent dashboard
answers **422 VALIDATION_ERROR** with `detail: "Dashboard with id=… not found"` — raised by
`DashboardService.grant_access` at `services/dashboard_service.py:377-379` as a `ValueError` and mapped
by `dashboards_access.py:110-115`. That contradicts the same endpoint's own docstring at `:61`
("AppException 404: If dashboard not found") and its `responses=admin_responses` at `:36`. Anyone
normalising refusals per this finding needs it in scope or it will survive the change.

**Evidence** — Same principal, zero grants on the target:

```
GET    /dashboards/9e7e37e7-…             -> 403 {"code":"ACCESS_DENIED","detail":"Access denied"}
DELETE /dashboards/9e7e37e7-…             -> 403 {"code":"ACCESS_DENIED","detail":"Access denied"}
GET    /dashboards/9e7e37e7-…/graphs      -> 403 {"code":"PERMISSION_DENIED",…}
GET    /admin/users                       -> 403 {"code":"INSUFFICIENT_PERMISSIONS",…}
GET    /dashboards/11111111-…             -> 404 {"code":"DASHBOARD_NOT_FOUND","details":{…}}
POST   /dashboards/11111111-…/access      -> 422 {"code":"VALIDATION_ERROR","detail":"Dashboard with id=… not found"}
```

**Consequence** — As filed: `GET /dashboards/{id}` is a dashboard-existence oracle for any
authenticated principal (404 versus 403 partitions the id space) while every sibling surface under the
same prefix answers 403 for both; any client switching on `code` must special-case three values for
one meaning, and `frontend/src/shared/api/errorHandler.ts` is one such client.

**Recommendation** — Executable, and the input's phase-13 coordination note is correct and load-bearing:
three codes are consumed client-side today, so phase 13 must be told before the mapping moves. Add the
422 rendering above to the scope. The `layouts.py:234` convention the input nominates is verified as the
one place the codebase already writes the decision down.

---

### AUTZ-007 — Dashboard ownership is written to a column no decision reads, and represented only by a row anyone can delete

**Verdict** — confirmed. Band carried unchanged at MEDIUM.

**Severity** — MEDIUM

**Zone** — "Single-object paths: is the caller consulted, and what the response discloses first"

**Observation** — `dashboards.created_by` (`db/models/dashboard.py:68-72`, indexed at `:37`) is written
once at `services/dashboard_service.py:88` and read by nothing. The input's static evidence is exact:
three hits over `src/`, all accounted for. `get_dashboard_id_for_layout`
(`services/layout_service.py:197-210`) resolves to the **first** associated dashboard, as filed — its
docstring says so — and is correct only because the relation is 1:1 today.

**Evidence** — Static, three hits. Live: after AUTZ-001's delete, both the zero-grant viewer **and the
dashboard's own admin** read `[]` from `GET /dashboards/{id}/access` while `created_by` still named the
owner. That is the fallback's non-existence demonstrated rather than inferred: there was no surface
left to restore the grant from, and the owner had to re-grant by calling the unguarded grant route.

**Consequence** — As filed. Once the `dashboard_access` row is gone the dashboard has no recorded owner
and no surface can restore one; and because the column is `ON DELETE SET NULL` from `users`, deleting a
user erases the only ownership datum while `dashboard_access` rows cascade away with it.

**Recommendation** — Executable, and correctly split into two separable changes with a documented
choice between them. The input's hand-off of the 1:1 multiplicity question to phase 14 is the right
seam; this phase names the assumption and does not pre-empt the schema ruling.

---

### AUTZ-008 — A second resolution of one identity exists, consults fewer states, and is called by no live path

**Verdict** — confirmed as tabulated. Band carried unchanged at LOW. One citation in the evidence is wrong.

**Severity** — LOW

**Zone** — "The two resolutions of one identity, and whether they agree"

**Observation** — The table reproduces line for line. `deps.get_current_user_dependency`
(`api/deps.py:472-576`) refuses on decode failure with `INVALID_TOKEN` at `:496-501`, consults `jti` at
`:504-512`, consults `user_tokens_revoked` at `:526`, and refuses `is_active == false` at `:544-550`.
`permissions._get_current_user_with_session` (`core/permissions.py:291-353`) has no `is_active` branch
at all — `:331-345` goes straight from the revocation check to `repo.get` — and both revocation checks
are guarded by `redis_client is not None` (`:325` and `:331`), against a `None` default at `:268`.
`dashboard_access.permission` is a native PostgreSQL enum `dashboard_permission_level` holding exactly
`view`, `edit`, `admin` (`db/models/access.py:43-52`), which is why the three implementations agree on
every value that can exist and differ only on the two aliases the enum prevents.

**Correction.** The input states that searching for `get_current_user` over `src/` "returns the
definition at `permissions.py:265` and the docstring reference at `core/permissions.py:38`". Line 38 is
`PERMISSION_LEVELS: dict[DashboardPermission, int] = {` and contains no reference to `get_current_user`.
The substantive claim holds: the only importer anywhere is `tests/test_permissions.py:14`.

**Evidence** — Static, as tabulated, plus the repository-wide searches that establish it. The runtime
demonstration of the live gate is AUTZ-005: `deps.py:544` is reachable and would have refused the
account had the flag persisted, and the live run showed the account authenticating at
`POST /auth/login` while `is_active` remained `true` — which is the same divergence seen from the other
side.

**Consequence** — As filed: no effect today because no live path calls it, which is exactly why it is
LOW. The forward-looking effect stands — the unused resolver is the more permissive of the two, is the
one with a shipped test suite, and is reachable by omission because `deps` does not export a plain
function.

**Recommendation** — Executable. The input's own sequencing note ("AUTZ-003's fix should land first so
there is one resolution before a second is deleted") names a dependency that does not exist — AUTZ-003 is
about which *authorization attribute* decides, not about how a token is resolved to a user, and nothing in
AUTZ-003's change touches `core/permissions.py:265`. Carrying the dependency as written would put a
dead-code deletion behind an unrelated product decision. The phase-09 hand-off for
`tests/test_permissions.py::TestGetCurrentUser` is correct and is not pre-empted.

---

### AUTZ-009 — Unauthenticated `GET /health/detailed` returns a filesystem path, and a raw dependency error when the database is down

**Verdict** — confirmed for the always-on disclosure. Band carried unchanged at LOW. The database-failure
branch remains **unsettled**, for the reason the input itself gives.

**Severity** — LOW

**Zone** — "What each refusal discloses, and where the shapes disagree"

**Observation** — `src/mkobi/app.py:269-307` resolves exactly and is registered with no dependency. Its
`static_files` component unconditionally reports the deployment path at `:303`
(`"path": "frontend/dist"`), status derived from `os.path.isdir`. Its `database` component sets
`components["database"]["error"] = str(e)` at `:296` — the unfiltered driver text — while `/health`
(`app.py:248-267`) is also unauthenticated and returns a fixed two-key body.

**Evidence** — The always-on path was reproduced without a credential: the endpoint answers `200` and
reports `"path":"frontend/dist"` with `static_files.status` derived from the directory probe. The
`str(e)` branch could not be exercised without stopping the dev database, which is out of bounds while
peers may be using the stack; it is named from source and **not** claimed as reproduced here either.

**Consequence** — As filed and as bounded: an anonymous caller receives a deployment path and a yes/no
on the frontend bundle. The branch that would carry the connection target is recorded as a limit, not as
a proven effect, and this validation keeps it that way.

**Recommendation** — Executable; dropping `"path"` is a one-line deletion, and replacing `str(e)` with
the fixed string the failure branch already sets at `:295` keeps the detail in the log line at `:293`.

## Findings — validation namespace `VAL-12-` (defects in the input report)

These are defects **in the audit output**, graded by this phase's own taxonomy on present state. They
are held in their own section because they carry a different scale from the `AUTZ-` findings above and
the two must never share a `Severity` column.

### VAL-12-001 — The ambient-credential positive result rests on one false sentence

**Severity** — LOW

**Zone** — "The claim re-derived from the executing path"

**Observation** — Appendix C states that the refresh cookie `mkobi_refresh_token` "is read by exactly
one surface, `POST /auth/refresh` (`auth.py:297`) and `POST /auth/logout` (`auth.py:441`), **both of
which are non-mutating with respect to server state**". `POST /auth/logout` is not non-mutating. It
reads the cookie at `api/routes/auth.py:441` and then writes two Redis keys — `revoke_refresh_token`
at `:448` (`refresh_token_blacklist:{jti}`, `core/security.py:479-489`) and `revoke_token` at `:459`
(`token_blacklist:{jti}`, `core/security.py:466-476`) — plus `delete_secure_cookie` at `:461`. It is a
mutating surface, and the two writes are precisely the revocation records the rest of the finding set
depends on.

**Evidence** — Static, by the two call sites and the four functions they reach. The rest of the
sentence's enumeration is exact: a search over `src/` for `request.cookies` returns exactly two hits,
`auth.py:297` and `auth.py:441`, so no route accepts the refresh cookie anywhere else.

**Consequence** — None today, and the positive result itself stands. The reason it stands is a different
route than the one given: `/auth/logout` authenticates on
`get_current_user_dependency` (`auth.py:421`), which resolves only the `Authorization` header
(`api/deps.py:448-469`, `HTTPBearer`), so no ambient credential reaches it and no cross-site write
primitive exists. A reader who trusts the sentence as written would conclude the cookie rides on a
read-only surface and would not check that.

**Recommendation** — Replace "both of which are non-mutating with respect to server state" with the
correct statement: `/auth/refresh` is non-mutating on success, `/auth/logout` writes two self-scoped
revocation records and additionally requires the bearer header, so neither is reachable by ambient
credential alone. Everything else in the paragraph needs no change.

---

### VAL-12-002 — Two configuration anchors do not resolve to the mechanisms they are cited for

**Severity** — LOW

**Zone** — "The claim re-derived from the executing path"

**Observation** — Appendix B cites `config.py:676-681` for "`config.py:676-681` refuses `*` in
production". At the input's baseline those lines are the docstring tail and the head of the invalid-origin
comprehension inside `validate_cors_origins_not_placeholder` (`config.py:671-689`), whose set
(`CORS_ORIGINS_PLACEHOLDERS` at `:664-669`) contains `http://localhost:3000`,
`http://localhost:5173`, `https://example.com` and `https://your-domain.com` — **not** the wildcard. The
wildcard refusal is a different function, `validate_cors_origins` at `config.py:767-772`. Appendix B
also cites `config.py:444` for the development override of `cookie_secure`; line 444 is a comment
("In production, always keep True. In development, set APP__COOKIE_SECURE=false…") and the field
default is at `:446-449`.

**Evidence** — Both claims are nonetheless true on the executing path, which is why this is LOW and not
a wrong approval. `validate_cors_origins` refuses `"*"` outright in production at `config.py:767-772` and
drops it with a warning in every other tier at `:773-783`, so `allow_origins` is never `"*"`.
Verified live: a request carrying `Origin: https://evil.example.com` receives **no**
`access-control-allow-origin` header at all, while `Origin: http://localhost:5173` receives exactly
`access-control-allow-origin: http://localhost:5173` with `access-control-allow-credentials: true` and
`vary: Origin` — the configured list is
`["http://localhost:3000","http://localhost:5173"]` (dev `.env:21`). Starlette reflects nothing
arbitrary, as claimed.

**Drift re-checked after the baseline moved.** `config.py` is the one source file on this report's
anchor path that changed in `7342e9e..05f2779`. Both validators were re-read against the current tree
and are unchanged in substance — the same two functions, the same placeholder set without `*`, the same
per-tier wildcard behaviour — with line numbers shifted by four: the wildcard refusal is now
`config.py:771-776` and the comment/default pair is now `config.py:448` / `:450-453`. **The finding is
not a product of the drift:** at the input's baseline the cited lines already failed to resolve to the
claimed mechanisms, and they still do.

**On the explicit question of whether `Secure` is really set in the dev profile.** It is not, and the
flow does not break. The live login response sets
`mkobi_refresh_token=…; HttpOnly; Max-Age=604800; Path=/; SameSite=strict` with **no `Secure`
attribute**, because the running app container carries `APP__COOKIE_SECURE=false`. The input's
Appendix C does not claim otherwise — it correctly attributes `secure` to `config.app.cookie_secure`
rather than asserting the flag — so this is not a defect in the input; it is recorded here because it is
the question the positive result turns on.

**Consequence** — No remediation consequence today; both mechanisms exist and behave as claimed. A reader
checking only the cited lines would find a different refusal in each case and could conclude the claims
are unsupported.

**Recommendation** — Repoint the two anchors (`config.py:767-772` for the wildcard,
`docker/docker-compose.override.yml` for the dev override) and note in Appendix B that the wildcard
refusal is per-tier rather than universal.

---

### VAL-12-003 — One line of AUTZ-005's quoted evidence did not reproduce, and the annotation misattributes the inertness

**Severity** — LOW

**Zone** — "The claim re-derived from the executing path"

**Observation** — AUTZ-005's evidence block records the reactivation call as
`200 {"is_active":true,"updated_at":"2026-09-30T18:27:08Z"}` annotated "the pre-deactivation
timestamp", and the consequence paragraph builds on it. Re-run at `7342e9e`, the reactivation response
carried a **fresh** `updated_at` (`2026-09-30T19:17:32.650120Z`), not a stale one; the *database* row
retained the pre-deactivation `19:16:50.892218+00` across both the deactivate and the reactivate call.
The response body does not show the inertness — only the database does.

**Evidence** — The observed pair, from the live run:

```
PATCH .../active {"is_active":false} -> 200 updated_at 19:17:30.022956Z ; psql updated_at 19:16:50.892218+00
PATCH .../active {"is_active":true}  -> 200 updated_at 19:17:32.650120Z ; psql updated_at 19:16:50.892218+00
```

**Consequence** — None for the finding: the load-bearing parts reproduced exactly — the write does not
persist in either direction, `EXISTS user_tokens_revoked` stays `1` through the reactivate, a re-login
returns `200` with a fresh token and that token is refused `401 TOKEN_REVOKED`. The defect is that the
cited line would have been read as evidence of the response body's unreliability, which is not what
happens; the response reflects the in-memory model the finding already describes at
`admin.py:184`.

**Recommendation** — Replace that one evidence line with the database reading, which is the artefact
that actually shows the write is inert.

---

### VAL-12-004 — AUTZ-003 stops one step short of the fact that decides its own remediation direction

**Severity** — LOW

**Zone** — "Whether the recommendation can be carried out"

**Observation** — AUTZ-003 records that two authorities disagree with no documented precedence and
leaves the choice open, then recommends moving the nested routes onto the grant. The executing path
determines which authority the system already treats as authoritative, and the input does not state it:
the 201-written chart persists and is served by `GET /dashboards/{id}/graphs`, `GET /graphs/`,
`GET /graphs/{id}`, `PUT /graphs/{id}` and `DELETE /graphs/{id}`, while the 403 twin writes nothing.
The full derivation is under AUTZ-003 above.

**Evidence** — The live create/serve sequence and the two gate implementations
(`core/permissions.py:176-185` versus `api/deps.py:582-606`), whose set difference is exactly
`{dashboard_access=admin ∧ users.role≠admin}`.

**Consequence** — None today, because the input reaches the same recommendation anyway. The omission
costs the reader the argument: a reader who has to decide whether the nested route or the global route
is wrong has to re-derive it, and may reasonably reach the opposite answer from "no documented
precedence" alone.

**Recommendation** — Add one sentence to AUTZ-003's consequence: the grant is the de facto authority for
chart lifecycle, and the divergence can only refuse a legitimate dashboard administrator, never admit
one who should be refused.

---

### VAL-12-005 — The roadmap's first step, followed as written, leaves the deactivation control inert

**Severity** — HIGH (re-graded; this validator's band for a defect in the audit, not the audited
phase's band)

**Zone** — "Whether the recommendation can be carried out"

**Observation** — The roadmap opens with "Close TXN-001 first (phase 03). AUTZ-005 is a consequence of
it and cannot be verified as fixed until the role and `is_active` writes actually persist", and Rollout
Safety says step 1 "means `PATCH /admin/users/{id}/role` and `.../active` start persisting". Both are
directionally right and incomplete, because persisting the write does not restore the control.
`is_active` is read in **exactly one place in the whole codebase** — `api/deps.py:544`. A
repository-wide search over `src/` for `is_active` returns 19 hits, and the only one that reads the
value is `deps.py:544`: `services/auth_service.py` contains no reference to it at all, so `login_user`
has no branch that can refuse a deactivated account, and `POST /auth/refresh`
(`api/routes/auth.py:358-375`) checks `is_user_tokens_revoked` and the refresh-jti blacklist but never
`user.is_active`.

**Evidence** — The live run: a principal the admin had just "deactivated" received `200` with a working
access token from `POST /auth/login`, and the response body carried the user object with
`"is_active":true`, because the write never persisted. The static proof is what makes this load-bearing
rather than incidental: with the write persisted, the same request would still answer `200` and hand
back a token that `deps.py:544` then refuses on every subsequent request.

**Consequence** — Following roadmap step 1 alone produces a system where an account marked
`is_active=false` in PostgreSQL can still authenticate, still obtain access tokens from both
`/auth/login` and `/auth/refresh`, and still receives a `200` from both, while every other surface
refuses it with a message about the flag. The operator-visible outcome is a control that appears
persisted and is not, on the one surface where an operator would check. That is work that must be done
and would not reach the roadmap as written.

**Recommendation** — Widen step 1 to three parts and keep TXN-001 as its first element: (a) TXN-001, so
the write persists; (b) delete `user_tokens_revoked:{user_id}` on the reactivate path, without which a
correct deactivation becomes a permanent lockout; (c) consult `user.is_active` in `login_user` and in
`POST /auth/refresh`, without which a correct deactivation is not enforced on either credential-issuing
surface. Part (b) is already AUTZ-005's own recommendation; parts (a) and (c) are the additions. Record
the dependency rather than re-filing: (a) stays phase 03's TXN-001 and (c) is the same missing-consumer
class as AUTH-003, which phase 04 already owns.

## Distribution

The nine findings fall on the dashboard access-control surface and the two authority predicates, with
one low-band item each on the health payload and the token resolvers. `api/routes/dashboards_access.py`
is 227 lines with three endpoints and **zero** authorization predicates installed across all three —
that single file is AUTZ-001 and the whole of it. `api/routes/dashboards_filters.py` is the same
failure one layer out (AUTZ-002). The second concentration is the inline re-implementation of refusals
in route modules, which is AUTZ-006 and feeds AUTZ-003. By role: both CRITICALs and the HIGH in
AUTZ-003 are reachable by the lowest role the system admits, and nothing in the set requires a system
administrator.

- `api/routes/dashboards_access.py`, `services/dashboard_service.py`, `db/repositories/access_repo.py` — AUTZ-001, AUTZ-007
- `api/routes/dashboards_filters.py`, `db/repositories/dashboard_filter_repo.py` — AUTZ-002
- `core/permissions.py`, `api/deps.py`, `api/routes/graphs.py`, `api/routes/dashboards_graphs.py`, `api/routes/upload.py` — AUTZ-003, AUTZ-008
- `api/routes/data.py`, `services/data_service.py` — AUTZ-004
- `api/routes/admin.py`, `services/user_service.py` — AUTZ-005
- `api/routes/dashboards_crud.py` and nine sibling surfaces — AUTZ-006
- `app.py` — AUTZ-009

By role of the reviewer-facing effect: eight of nine findings are about what a non-admin principal can
reach; the ninth (AUTZ-009) is about what an anonymous caller can read.

## Cross-Finding Analysis

Three findings share one cause, and the input is right about it. `dashboard_access` is treated as an
ordinary user-writable collection rather than as the authorization decision itself, and nothing above it
treats mutating that collection as privileged. That mis-framing produces **AUTZ-001** (the collection is
readable and mutable by anyone), **AUTZ-007** (it is therefore the sole ownership record, with no
fallback column), and contributes to **AUTZ-002** (the sibling filter-binding collection, which nobody
guards at all). The input's proposed single fix — one dependency answering "may this principal
administer this dashboard", installed on every path that mutates dashboard state — is verified
executable: the dependency already exists at `api/deps.py:788-829` and is already used in this shape at
`api/routes/graphs.py:96-101`, so no new abstraction is required. AUTZ-005 and **VAL-12-005** are a
fourth instance of the same shape one layer out — an account state that is written and read by nobody
on the surface that matters — which strengthens the input's grouping rather than contradicting it.

AUTZ-003, AUTZ-004, AUTZ-006, AUTZ-008 and AUTZ-009 are independent of that group and of each other:
they are about *which* predicate is consulted, *how far* its scope reaches, *how* a refusal is rendered,
*how many times* a token is resolved, and *what an anonymous caller sees* — not about whether one is
consulted. The input's statement that AUTZ-003 and AUTZ-006 are independent of the group is verified.

## Roadmap

The input's six-step order is executable and its two explicit ordering constraints are correct. Three
corrections and one widening:

1. **Widen step 1** (per `VAL-12-005`). TXN-001 first, then the reactivate-path key deletion, then an
   `is_active` check in `login_user` and `POST /auth/refresh`. Closing only TXN-001 leaves the control
   inert on both credential-issuing surfaces. Closes AUTZ-005. Phase 03 owns TXN-001; the other two
   parts are this phase's.
2. **Install one dashboard-administration gate** on `dashboards_access.py` (all three),
   `dashboards_filters.py` (bind, unbind) and — pending step 3 — `dashboards_graphs.py`. Closes AUTZ-001
   and AUTZ-002. Verified executable: the dependency exists and is already used. Nothing shipped blocks
   it. Must precede step 4.
3. **Settle the authority question** (AUTZ-003) and write the precedence into `SPEC.md`. Now decidable
   rather than open: the grant is the de facto authority for chart lifecycle (`VAL-12-004`), so moving
   `dashboards_graphs.py:56` and `upload.py:75` onto the grant is the only direction consistent with what
   already persists. Tell phase 13 first — the frontend calls the nested routes.
4. **Constrain the child lookup** at `data.py:120` and decide the ownership column (AUTZ-007). Both are
   single-site changes, safe in either order after step 2. The 1:1 layout multiplicity question stays
   phase 14's; name the assumption, do not settle it here.
5. **Normalise the refusal** (AUTZ-006), with phase 13 told first, and **add the fifth rendering** the
   input's table omits: `POST /dashboards/{id}/access` on an absent dashboard answers 422, not 404. This
   step should also settle the ACL-read surface's `200 []`-for-absent case from AUTZ-001, or it will
   reappear.
6. **Remove the second token resolution** (AUTZ-008) and slim the health payload (AUTZ-009). Cleanup;
   neither blocks anything. Drop AUTZ-008's stated dependency on AUTZ-003 — it is not a real dependency
   and would put a dead-code deletion behind an unrelated product decision.

The input's cross-references are correctly assigned and are not duplicated here: TXN-001 stays phase 03,
the declared-contract contradictions stay phase 08, `force_password_change` stays phase 04, the client-side
error-code consumption stays phase 13, the layout↔dashboard multiplicity stays phase 14, and the
`Secure`-cookie transport requirement stays phase 10.

## Rollout Safety

Steps 1 and 2 are the only ones that change what a legitimate caller can do, and that is where the
risk sits.

**Step 1, widened.** Making `PATCH /admin/users/{id}/role` and `.../active` start persisting is the
highest-consequence step in either report: any operational habit built around the current behaviour — a
role change appearing to succeed and reverting — stops holding, and every account currently wedged by
`user_tokens_revoked` will recover only on its next explicit reactivation call, not automatically. The
`is_active` check added to `login_user` and `/auth/refresh` is the part most likely to surprise: an
account deactivated earlier and reactivated through the current buggy path will have a stale
`user_tokens_revoked` key, will still fail every request until the key is cleared, and will now *also*
fail at login instead of at first use. That is the intended direction but it needs an operator runbook
line. Existing access tokens remain valid across step 1, so nobody is logged out by it.

**Step 2.** It starts refusing calls that currently succeed, and the first callers to notice will be the
frontend's own dashboard screens — `/dashboards/{id}/access`, `/dashboards/{id}/filters` — for any
principal whose `users.role` is not admin. Verify after step 2 that both AUTZ-001 and AUTZ-002 probe
sequences return 403 for a zero-grant viewer and 200 for a system administrator, and that the
dashboard-administrator persona still works against the frontend if step 3 keeps the global role on those
two routes. Revert by reverting the commit: no data written by these steps is transformed, only newly
refused, so a revert restores the previous behaviour with no cleanup.

**Ordering is load-bearing in one place only.** Step 3 must not land before step 2, or the two gates on
`/dashboards/{id}/graphs` will still disagree and the AUTZ-003 verification will be ambiguous. Nothing
else in the sequence is order-sensitive.

## Appendices

### Appendix A — Assessment of the findings deferred into this phase

**QLT-001** (`POST /dashboards/{id}/access` returns 200 with the requested permission while writing
nothing on an existing row) — **confirmed and extended, and the extension's scope is now pinned to the
field.** Re-derived to the executing path: `AccessGrant` (`src/mkobi/models/access.py:25-30`) declares
exactly three fields — `user_id`, `dashboard_id`, `permission` — and `AccessRepository.grant_access`
(`db/repositories/access_repo.py:31-87`) looks the target up by the `(user_id, dashboard_id)` pair at
`:50-56` and returns the existing object unchanged at `:57-63`. So the no-op is **not** a whole-row
no-op and it is **not** limited to "the permission column" in the sense the question implies: the other
two fields are the lookup key of the branch itself, so changing either creates a *different* row rather
than mutating this one. The no-op therefore blocks exactly one field, and that field is the only
mutable one. The extension claim — "a self-granted principal can never be demoted through the interface
either" — is true, and precisely bounded to the permission value.

Reproduced live, in order, on an existing admin grant:

```
POST .../access {"permission":"view"}   -> 200 {"message":"Access granted",…,"permission":"view"}   DB: admin
POST .../access {"permission":"read"}   -> 200 {"message":"Access granted",…,"permission":"read"}   DB: admin
POST .../access (NEW pair) "read"       -> 500 {"code":"INTERNAL_ERROR","detail":"Access grant error"}
POST .../access "superadmin"            -> 422 {"code":"VALIDATION_ERROR",…}
POST .../access on absent dashboard     -> 422 {"code":"VALIDATION_ERROR","detail":"Dashboard with id=… not found"}
```

The third line reproduces the phase-08 validator's `read`-on-a-new-row 500 and confirms the phase-12
reading of why: the existing-row branch returns before PostgreSQL is ever consulted with the new value.
The last line is new — the service raises `ValueError` at `services/dashboard_service.py:377-379`, which
`dashboards_access.py:110-115` maps to 422, contradicting the endpoint's own docstring at `:61` and its
`responses=admin_responses`; it is folded into the AUTZ-006 disposition above. **Ruling: QLT-001 remains
phase 08's; no re-filing, no merge, no renumbering. Phase 12 owns only the unguarded surrounding surface
(AUTZ-001) and now the 422 rendering.**

**QLT-002** (declared "All operations require admin role" / "Available only to owners", neither enforced)
— **confirmed, extension confirmed by direct reproduction.** The phase-08 validator's correction is
itself verified: `grant_access` has exactly two callers, `api/routes/dashboards_access.py:85` and
`services/dashboard_service.py:104`. A self-registered `viewer` with zero grants obtained
`200 {"message":"Access granted",…,"permission":"admin"}` on an admin-owned dashboard and the row landed
in `dashboard_access`. The extension — that the revoke and ACL-read endpoints of the same module carry
the identical defect — is AUTZ-001 and is reproduced above. **Ruling: no re-filing; the
declared-contract contradiction stays phase 08 as ruled; no identifier is duplicated.**

**AUTH-004** (password rotation withdraws nothing; `/auth/refresh` emits no `Set-Cookie`) — **not owned
by this phase, and the ruling is upheld, on corrected grounds.** Reproduced live end to end on one
account:

```
GET  /auth/me with the pre-rotation access token   -> 200     (before the reset)
POST /auth/refresh with the pre-rotation cookie    -> 200     (before the reset)
POST /admin/users/{id}/reset-password              -> 200     (password rotated)
GET  /auth/me with the SAME pre-rotation token     -> 200     <- withdrawn nothing
POST /auth/refresh with the SAME cookie            -> 200 {"access_token":"eyJ…"}   with NO Set-Cookie header
redis KEYS "*revoked*" / "*blacklist*"             -> (empty)
```

The defect is exactly as phase 04 filed it. The input's stated *reason* for the ruling, however, is
weaker than the ruling itself and is corrected here: the input rests it on "`deps.get_current_user_dependency`
consults both `jti` revocation and `user_tokens_revoked` on every request, and `/auth/refresh`
independently consults `is_user_tokens_revoked`." Both statements are true (`api/deps.py:504-532`,
`auth.py:368`) but they describe **disjoint namespaces**: `deps` reads `token_blacklist:{jti}` via
`is_token_revoked` (`core/security.py:492-504`) while `/auth/refresh` reads
`refresh_token_blacklist:{jti}` via `is_refresh_token_revoked` (`:507-519`). A logout revocation on an
access-token jti is therefore invisible to the refresh path and vice versa. The only mechanism that
covers both credential classes is `user_tokens_revoked`, and the reset path never writes it. So the
input's conclusion — "the omission is a missing call rather than a missing capability" — is **more**
strongly supported by this validation than by the reason the input gave, and the disposition is
unchanged: **not re-filed; phase 04's issuance/withdrawal boundary owns it.** One item for phase 04
that is visible only from this side and is not in AUTH-004's framing: `/auth/refresh` never consults
`user.is_active` (`auth.py:358-375`), which is the same gap `VAL-12-005` records on this phase's side.

**AUTH-003** (`force_password_change` written by both issuing paths, read by nothing server-side) — **the
decision not to re-file was correct.** Re-derived: `git grep -n force_password_change -- src/` returns
nine hits — two writes (`api/routes/admin.py:316`, `services/auth_service.py:588`), one reset-to-false
(`services/auth_service.py:514`), one model column (`db/models/user.py:69`), one Pydantic field
(`models/user.py:49`), and three in docstrings and route descriptions (`admin.py:200`,
`services/auth_service.py:549`, `admin.py:314`'s comment). **Zero reads.** Live: the freshly approved
account's `GET /auth/me` returned `"force_password_change": true` and the account was fully usable. The
phase is right that a flag with no server-side consumer is an authorization control that does not
control — and it is right not to have minted an `AUTZ-` identifier for it. AUTH-003 is already filed by
phase 04, which owns the concern; re-filing it under a second prefix would have created exactly the
duplicate the seam check exists to prevent, and the account-state matrix row the input records —
"`force_password_change` | approve + reset | **nothing** | no — returned to the caller only" — states
the finding honestly and completely. **Ruling: upheld, no re-filing, no merge, no renumbering.** The one
thing owed to the roadmap is a dependency, recorded here rather than as a finding: no remediation step in
either report may assume a reset account is contained until phase 04 closes AUTH-003, and `VAL-12-005`
part (c) is the same missing-consumer class on this phase's side of the boundary.

### Appendix B — The ambient-credential positive result, adjudicated

The input records a clean result "so it is not re-asked". It is clean, and it is re-derived here so the
question does not recur. The enumeration is exact: a search for `request.cookies` over `src/` returns
two hits, `api/routes/auth.py:297` (`POST /auth/refresh`) and `:441` (`POST /auth/logout`); no route
accepts the refresh cookie as a credential anywhere else, and every mutating surface authenticates
through `CurrentUser`/`AdminUser`/`EditorUser`/`ViewerUser`, which all resolve
`get_token_from_header` (`api/deps.py:448-469`, `HTTPBearer`). The cookie attributes the input claims
are what the server sets, and `Secure` is **not** among them in the dev profile — the live login response
is `mkobi_refresh_token=…; HttpOnly; Max-Age=604800; Path=/; SameSite=strict`, with the running app
container carrying `APP__COOKIE_SECURE=false`, so the dev refresh flow does not break. The one sentence
of the input's supporting argument that is false is recorded as `VAL-12-001`. CORS never reflects an
arbitrary origin: `allow_origins` is a configured list (`app.py:218-224`) and an unknown
`Origin: https://evil.example.com` receives no `access-control-allow-origin` header at all, while the
configured `http://localhost:5173` is echoed exactly. Which origins are honoured per environment is
phase 02's and is not re-opened.

### Appendix C — Hygiene of the input's probes, verified

The input claims every user, dashboard, graph, layout, grant, `dashboard_filters` row,
`registration_requests` row and Redis key its probes created was removed and pre-existing state
restored. Verified by counting before and after, against the dev database `bidb` and the dev Redis:

| Object | Count observed before this validation's probes | Count after cleanup | Verdict |
|---|---|---|---|
| `users` | 7 | 7 | input's probe user `58e988f1-…` absent; restored |
| `dashboards` | 8 | 8 | input's probe dashboard `ba58425d-…` absent; restored |
| `graphs` | 2 | 2 | restored |
| `layouts` | 0 | 0 | restored |
| `dashboard_access` | 10 | 10 | restored, including the grant AUTZ-001 deleted during the input's own probe |
| `dashboard_filters` | 2 | 2 | both pre-existing rows still bound to `a5214e7a-…`; restored |
| `filters` | 2 | 2 | untouched |
| `registration_requests` | 9 | 9 | input's probe row absent; restored |
| `processing_configs` | 1 | 1 | untouched |
| `aggregated_data` | 0 | 0 | untouched |
| Redis keys | 4 (`rq:worker:*`, `rq:workers`, `rq:workers:default`, `upload:*`) | 4 (same set) | no residue: no `user_tokens_revoked:*`, no `login:*`, no `refresh:*`, no `register-request:*`, no `temp_password:*` |

**The input's hygiene claim is substantiated.** The only observed difference in Redis across the session
is the `rq:worker:<id>` member name, which changed because the `app` and `rq-worker` containers restarted
mid-session; that is not a probe artefact and no container was started, stopped or reconfigured by this
validation. This validation's own artefacts — one viewer account, two dashboards, two graphs, one
`dashboard_filters` binding (bound and unbound), one `registration_requests` row and the four Redis keys
it created — were removed and the counts above are the post-cleanup figures. Two probe dashboards were
created rather than reusing existing ones, specifically so that the AUTZ-001 delete — which is
destructive — was exercised against this validation's own data and never against pre-existing rows.

### Appendix D — Finding-ID namespace

`AUTZ-` is declared by this phase, minted `AUTZ-001`…`AUTZ-009` with no gaps, and appears nowhere else:
a search for `### AUTZ-` across every file in `.ai/audit/*/*.md` returns only
`.ai/audit/12-authorization/findings.md`. There are **no in-source markers** to migrate — the prefix
appears in no file under `src/`, `tests/`, `alembic/`, `docs/` or `docker/`. The compound form is
`AUTZ-<NNN>` paired with the template's front-matter `phase: 12-authorization`. No reuse across phases.
**No collision, and the audited prefix is preserved verbatim.**

The validation namespace required a ruling. The flat `VAL-` prefix is occupied: the phase-01 and
phase-02 reports mint `VAL-001`…`VAL-009` between them, and phases 03 through 11 mint phase-qualified
variants `VAL-03-001`…`VAL-11-007`. **This report therefore mints `VAL-12-001`…`VAL-12-005`**, recorded
as a deviation from the phase command's flat-`VAL-` instruction. The two tables are kept in separate
sections because the `AUTZ-` rows carry the audited phase's bands and the `VAL-12-` rows carry this
validator's bands; interleaving them would put two scales in one `Severity` column.

### Appendix E — The shared template as a controlled artefact

| Mandated element | Result |
|---|---|
| `phase:` set to the audited phase | present and correct — `12-authorization` |
| `executor: validator` | present and correct |
| `executed`, `problems-only`, `findings`, `by-severity` | all present; the `findings: 5` and `by-severity` counts cover the `VAL-12-` rows only, with the audited set carried separately in `audited-findings` / `audited-namespace` so the two scales are not summed |
| Six per-finding fields on every finding | present on all nine `AUTZ-` blocks and all five `VAL-12-` blocks |
| Location carried inside the observation, not as a field of its own | honoured throughout |
| Zone = the block title quoted verbatim | **unverifiable from the report** — see the ledger |
| Sections: Summary, Findings, Distribution, Cross-Finding Analysis, Roadmap, Rollout Safety, Appendices | all seven present and none padded |
| Reserved empty-state string | not applicable; the phase produced findings |

### Appendix F — Coverage ledger (residual footer)

**Blocks this run reached, and how many items each actually examined.**

| Block | Items reached | Result |
|---|---|---|
| 1 — Claim re-derived from the executing path | 9 of 9 `AUTZ-` findings; every cited anchor resolved mechanically before the claim was tested | 9 confirmed; 3 anchor slips recorded (`VAL-12-002` ×2, `VAL-12-003` ×1), 2 table rows off by a few lines noted under AUTZ-006 |
| 2 — Vacuous-control angle, and its bindings | 6 controls the findings lean on: `require_dashboard_admin_access`, `require_dashboard_write_access`, `require_dashboard_read_access`, `check_dashboard_access`, `get_current_user_dependency`, `permissions.get_current_user` | 5 installed and deciding; `permissions.get_current_user` green over **zero** live callers and recorded as vacuously clean by AUTZ-008 — correctly, at LOW |
| 3 — Grade against the audited phase's own rubric | 9 bands | all 9 carried unchanged; the rubric itself is absent from the input, so no band could be independently re-derived — recorded as a limitation below |
| 4 — Which side moves: code or documentation | 9 findings | load-bearing artefact is production code in all 9; 2 carry a documentation component (`VAL-12-002`, and the 422/404 contradiction folded into AUTZ-006) |
| 5 — Whether the recommendation can be carried out | 9 recommendations + 4 cross-references | 9 executable, targets resolved and present in the tree; 0 vague, 0 unusable; 1 sequencing dependency found spurious (AUTZ-008 → AUTZ-003), 1 found incomplete (`VAL-12-005`) |
| 6 — Cross-phase conflict, ownership and merge | 4 deferred rulings + 6 declared cross-references | 4 rulings returned, 0 merges, 0 conflicts; every cross-reference correctly assigned and none duplicated. The seam check could not be run — see below |
| 7 — Finding-ID namespace | `AUTZ-` declared / 9 minted / 0 in-source markers / 1 compound form / 0 reuse | no collision; `VAL-12-` minted with the deviation recorded |
| 8 — The shared template as a controlled artefact | 8 mandated elements | 7 verified present; 1 (zone = block title verbatim) unverifiable |
| 9 — Whether the input rests on its own declared blocks | 9 findings | the input declares **no** block list, so the block-resting question cannot be posed; 4 findings nonetheless cite runtime evidence outside any declared block |
| 10 — The validated report as an artefact | this document | tally agrees with the per-finding verdicts; identifiers preserved; no renumbering; the two namespaces are in separate sections |
| 11 — The shared angles | vacuous-control, cross-resource side-effect | phase 12 binds neither by name in the input report; no binding to adjudicate |

**Claims left unsettled, and why.**

1. **The database-failure branch of `/health/detailed`** (AUTZ-009, `app.py:296`). Forcing it requires
   stopping the dev database, which is out of bounds while peers may be using the stack. The always-on
   path disclosure was observed; the `str(e)` branch is named from source and is **not** recorded as
   reproduced here, in this report or in the input's Appendix B.
2. **The zone-quoting rule of the template.** The input's report contains no block list, so its five zone
   strings cannot be checked against the declaring phase's own block titles. Appendix C of the input
   references "Block 5", "Block 6", "Block 7" and "Block 11", which implies an eleven-block phase
   definition that the report does not reproduce. Recorded as unverifiable rather than as a violation.
3. **The seam check.** This requires the input's own declared scope paragraph. The input states none, so
   no finding can be shown to fall outside it. Subject matter was inspected instead: all nine findings are
   uniformly about authorization decisions on the executing path, and the two that lean on another
   phase's concern (TXN-001, the declared contracts) cross-reference rather than re-file.
4. **Band re-derivation.** The input carries `by-severity` counts but no severity rubric, so "the band the
   audited rubric assigns" cannot be reconstructed for any finding. Every band is therefore carried
   unchanged and the dispositions above are confirmations of the mechanism, not of the grade. This is a
   limitation of the input as an auditable artefact, not a finding against it: the shared template
   mandates no rubric section.
5. **A non-admin `users.role=editor` account in production.** Not constructible through the API here,
   because TXN-001 prevents role promotion — the input records the same limit in its Appendix B. AUTZ-003's
   divergence is stated for the grant-holding-`viewer` case, which **was** exercised.

**Environment of record.** This validation was re-derived statically against the working tree at the
input's baseline `7342e9e7bae99adf248339bb4a062b67a06fb97c`, which was `HEAD` for the whole probe
window. `HEAD` moved during the run: the concurrent remediation landed
`bde2ddd … c938008 … f411c06 … ce537d7 … a026c47 … 8953bf7 … 541457c … 05f2779`, so the tree this report
was finally written against is `05f2779323c1746c8945f63882b187bcb2d7b608`. Two things follow and both
were checked rather than assumed:

- **No authorization-path source file moved.** `git diff --name-only 7342e9e 05f2779` touches
  `docker/.env.production`, `docker/docker-compose.yml`, five `docs/` files, `src/mkobi/config.py`,
  `src/mkobi/services/processing_log_service.py`, `src/mkobi/settings/app.yaml`,
  `src/mkobi/workers/data_worker.py`, `tests/test_config.py` and `tests/test_cors.py`. Not one of them
  is on `api/`, `core/permissions.py`, `core/security.py`, `db/`, `services/dashboard_service.py`,
  `services/user_service.py`, `services/data_service.py`, `db/session.py`, `app.py` or `models/` — every
  file that carries an `AUTZ-` anchor. `config.py` is the only source file on this report's anchor path
  that changed, and it is re-checked under `VAL-12-002` with the finding unchanged.
- **The runtime probed was the pre-`bde2ddd` build.** The running `app` image was created at 18:09 UTC
  and the container started at 19:00 UTC; the first of the new commits landed at 19:01 UTC. Every live
  probe ran between 19:03 and 19:18 UTC against that build. Because none of the eight commits changes a
  file on the authorization path, the runtime evidence remains valid for all nine `AUTZ-` findings and
  for all four deferred-finding rulings; it is stated here rather than left implicit.

No file was created, edited, staged, committed, reverted or stashed by this validation, and no container
was started, stopped or reconfigured.


