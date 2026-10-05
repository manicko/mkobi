---
phase: 09-test-coverage
executed: 2026-10-05
executor: validator
problems-only: true
findings: 13
validation-findings: 2
by-severity:
  CRITICAL: 0
  HIGH: 5
  MEDIUM: 3
  LOW: 5
by-severity-validation:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 2
  LOW: 0
---

# Phase 09 — Validated Findings

## Summary

Adjudicated the thirteen findings of `.ai/audit/09-test-coverage/findings.md` against the working tree,
re-deriving every cited location from the executing path, re-running the one runtime claim that was
reproducible, and executing the mutation test the report itself did not. **Nine CONFIRMED, four
CORRECTED, none REJECTED.** Two census figures are wrong and both understate the gap; every other
derived figure reproduced exactly. The five HIGH findings all survive, one of them strengthened.

The material corrections are of three kinds. **Two consequences that were mis-derived:**
`TEST-102`'s claim that removing `return axiosInstance(originalConfig)` produces a logout-and-redirect
is false — it produces a silent `undefined` resolution; and `TEST-107`'s impact over-reaches, because
`tests/test_e2e_upload.py:196-198` already observes the `dims` key end to end. **Two recommendations
that cannot be carried out as written:** `TEST-104`'s proposed `assert elapsed_time >= 2 * hold_duration`
fails against the shipped test as it stands (measured 0.5134 s with zero connection checkout), and
`TEST-110`'s `docker compose config` rewrite is a multi-class rewrite the report itself places outside
the roadmap. **Two re-grades downward**, both to the audited phase's own rubric bands: `TEST-109` and
`TEST-110` are self-description and configuration-text assertions, which that rubric names as LOW.

`TEST-104` is the strongest finding in the set and was understated: the mutation test shows the shipped
`test_pool_timeout_on_exhaustion` **asserts the opposite of the property its name states** — making the
holder actually hold a connection turns `second_succeeded` false and pushes `elapsed_time` to 1.0155 s,
failing both assertions. Two validation-level findings are added: a dashboard-scoped endpoint asserted
only from its admitting side, and a residual that phase 06's validator preserved and phase 09 examined
without disclosing.

The auditor's four disclosures were checked rather than accepted. The namespace ruling was correct and
necessary but understated the size of the `TST-` occupancy; the libmagic correction is **right** and was
verified independently; all five "remediated" spot-checks hold; `CQ-109`/`CQ-110` were correctly left
unfiled because phase 08's validator had already adjudicated both.

## Findings

### TEST-101 — The processing-config access check is inline in the handler and no test drives it without a grant

**Severity** — HIGH

**Zone** — "Each boundary, from each side — including the ones every test crosses the same way"

**Observation** — **CONFIRMED at HIGH; no correction.** Every cited location resolves and the quoted
blocks are verbatim. This is the only dashboard-scoped router in the repository whose access check is an
inline statement in the handler body *and* whose denying side no test drives — verified by exhausting the
search rather than by reading the three assertions the report names. The literal `processing-configs/`
appears in exactly twelve test lines across four files; four are HTTP call sites, all inside
`tests/test_processing_config_boundary.py` and all reached through `_make_dashboard_with_edit_access`
(`tests/test_processing_config_boundary.py:101-123`, used at `:387`, `:407`, `:459`); one is a body-shape
test that 422s before the handler body runs (`tests/test_request_boundary_extra_forbid.py:151`); three are
OpenAPI path lookups (`tests/test_openapi.py:72`, `tests/test_processing_config_boundary.py:490`, and the
parametrised table entry at `tests/test_request_boundary_extra_forbid.py:86-87`); the rest are docstrings.
There is **no `DELETE /processing-configs/{id}` call site anywhere in `tests/`**.

**Evidence** — `src/mkobi/api/routes/processing_configs.py:79-95` resolves to the quoted `try:` /
`check_dashboard_access(..., required_permission=DashboardPermission.VIEW)` / `AppException(PERMISSION_DENIED)`
block, character for character; the same shape is at `:161` and `:246` (both
`required_permission=DashboardPermission.EDIT`) and the import is at `:28`. The admitting side is asserted
at `tests/test_processing_config_boundary.py:416-419`. Re-derived by AST over `tests/**/*.py`: **54**
`assert` statements contain `403`, spread across nineteen modules — the boundary inventory in the finding's
Observation is right that none targets `/processing-configs/`. Independently, every dashboard-scoped
router was enumerated for its access-check style: `dashboards_access.py`, `dashboards_filters.py`,
`dashboards_graphs.py`, `dashboards_crud.py`, `filter_values.py`, `data.py`, `graphs.py`, `layouts.py` and
`processing_configs.py`. `processing_configs.py` is the only one that is inline **and** has no `403` test;
`graphs.py` (5 inline / 6 `403` sites), `layouts.py` (2 / 4), `dashboards_crud.py` (3 / 8) and `data.py`
(2 / 3) are all covered on the refusing side.

**Consequence** — as filed. The declared rule "access control is checked on every dashboard request"
(`AGENTS.md` §4) is held for this endpoint family by the code and by nothing in the suite. Because the
check is a statement in the handler body, deleting it — or inverting the condition — leaves the suite
green. What becomes readable is the loader/required-columns/renames map, i.e. the internal shape of
another tenant's ingestion pipeline.

**Recommendation** — carried out unchanged; it resolves and it is the smallest change. Both halves are
executable: the three refusal tests land in the existing module, and `tests/test_router_declarations.py:46`
already provides the operation-enumeration helper (`_operations`) the dependency-based option would need —
verified that no test currently consumes it for access control. The Rollout-Safety half is also correct and
material: moving the check onto `Depends` would flip `tests/test_request_boundary_extra_forbid.py:151-153`
from `422` to `403`, which the report names.

### TEST-102 — The axios 401 refresh-and-replay branch is exercised by no test

**Severity** — HIGH

**Zone** — "What each stand-in removes, and whether any test observes it elsewhere"

**Observation** — **CORRECTED; severity held at HIGH.** Every cited location resolves verbatim except one
off-by-one (`refreshHandler.ts` is 29 lines; `getRefreshHandler` ends at `:29`, not `:28`). The finding as
filed says `registerRefreshHandler` / `getRefreshHandler` are "never called from any test" — that is
**accurate, and the qualifier is load-bearing**, so the correction is a strengthening of the sentence
rather than a refutation of it. Re-derived across the whole frontend tree: `registerRefreshHandler` **is**
called in production, at `frontend/src/features/auth/api/authApi.ts:37`, at module scope immediately after
`refreshToken` is defined. A reader who drops the "from any test" qualifier would conclude the handler is
never registered at all, which is false. One **consequence claim is factually wrong** and is replaced
below.

**Evidence** — `frontend/src/shared/api/axiosInstance.ts:91-101` and `:112-123` resolve to the quoted
blocks character for character; `:109-111` is the `if (!handler) { throw new Error('Refresh handler not
registered') }` arm; the interceptor spans `:58-147`. `frontend/src/shared/api/__tests__/errorSurfaces.test.ts:15`
is the only frontend test file importing the real module, and its three failure adapters carry statuses
500 (`:56`), 500 (`:69`) and 404 (`:88`) — no 401 adapter exists anywhere in the tree. Independent
corroboration from the coverage artefact: `axiosInstance.ts` records **2 of 9 functions** and **22 of 66
statements** covered, and `refreshHandler.ts` **0 of 2 functions** and **1 of 3 statements** — the
registration function is the uncovered one.

**Consequence** — replaced for defect (2). Defect (1) holds: `failedQueue` entries are settled only by
`processQueue` (`axiosInstance.ts:46-55`), so removing `processQueue({ error: errorToReject })` at `:119`
leaves every request issued during a refresh pending on a promise nothing will ever settle — a silent hang.
Defect (2) as filed is **false**. The `try` block at `:106-116` contains no `throw` on the success path,
so deleting `return axiosInstance(originalConfig)` at `:116` does not enter the `catch` at `:117`; `finally`
clears `isRefreshing` and the async rejection handler returns `undefined`, which axios resolves to the
caller as a successful response whose payload is `undefined`. There is no `removeToken()`, no toast and no
`window.location.href`. The real failure is a silent `undefined` where the caller expects an
`AxiosResponse` — a `TypeError` at the call site with no session-expired signal, which is a worse diagnostic
outcome than the one filed, not a smaller one. Defect (3) holds as to coverage (`:122` has never executed
in a test) but the stated hazard is overstated: jsdom reports a refused navigation through its virtual
console rather than throwing, so "a jsdom navigation throwing" is not a live risk.

**Recommendation** — carried out, with one addition. The three postconditions proposed are the right three.
Add a fourth: assert that the unregistered-handler arm rejects with `Refresh handler not registered`
rather than falling through, because `authApi.ts:37` is the only thing standing between production and that
arm and nothing pins the registration.

### TEST-103 — The frontend coverage thresholds are read over 37 of the 66 non-test source files

**Severity** — HIGH

**Zone** — "What a coverage measure can actually see"

**Observation** — **CONFIRMED at HIGH; the two headline figures were re-derived independently and both
reproduce exactly.** A filesystem walk of `frontend/src` yields **97** `.ts`/`.tsx` files, of which **31**
are test files (`__tests__/`, `*.test.*`, `*.spec.*`, `test/`), leaving **66** non-test source files.
`frontend/coverage/coverage-final.json` (mtime 2026-10-05 16:04:28) carries exactly **37** keys, all of
them non-test files — so **29** files are outside the measure. Summing the `s` maps over all 37 entries
gives **540 / 732 covered statements = 73.77 %**. Both the 37-of-66 population and the 540/732 = 73.8 %
total are as filed. The absent-file *enumeration*, however, contains two errors that do not change the
count and must be corrected.

**Evidence** — `frontend/vite.config.ts:56-65` resolves to the quoted `coverage` block character for
character and declares `provider: 'v8'`, `reporter: ['text','json','html']` and thresholds
`statements 50 / branches 40 / functions 45 / lines 50`, with **no `include`, no `exclude` and no `all`**.
Gate reachability re-derived independently: `Makefile.ps1:277-279` defines `Invoke-FeTest` as
`npm --prefix frontend run test`, `frontend/package.json` `"test"` is `vitest run --coverage`, and
`Makefile.ps1:281-289` chains it last in `Invoke-Check` behind three short-circuiting gates, `:288` being
the `Invoke-FeTest` call. Enumeration corrections: **`features/dashboards/api/dashboardApi.ts` is PRESENT
in the report, not absent** (it is key 6 of 37) — listing it among the absent is wrong; **`test/setup.ts` is
not in the 66-file population at all** (it is a test file, named at `vite.config.ts:55` as `setupFiles`);
and the genuinely absent file the enumeration omits is `frontend/src/react-plotly.d.ts`. The three errors
cancel: 29 absent either way. Every other listed absence verified — `app/providers.tsx`, `app/routes.tsx`,
`main.tsx`, `features/admin/api/adminApi.ts`, all six `features/admin/ui/*.tsx` panels
(`AdminPanel`, `DashboardManagement`, `LogViewer`, `RegistrationRequests`, `ResetPasswordResultDialog`,
`UserManagement`), `features/auth/api/authApi.ts`, `features/dashboards/ui/DashboardList.tsx`,
`features/dashboards/ui/charts/LineChart.tsx`, `features/upload/{api/uploadApi.ts,ui/UploadModal.tsx}`,
`features/users/{api/userApi.ts,ui/ChangePasswordPage.tsx,ui/UserProfile.tsx}`,
`shared/components/{ConfirmDialog,NotFound}.tsx`, `shared/components/Layout/{AppLayout.tsx,Header.tsx,index.ts}`,
`shared/hooks/{useApiError,useConfirmDialog,useDebounce}.ts`, `shared/types/api.types.ts`,
`shared/utils/shortUuid.ts`.

**Consequence** — as filed, and independently reinforced. 44 % of the client source tree is invisible to the
only coverage gate reachable from `.\Makefile.ps1 check`, and the gate reports 73.8 % while doing so.
Verified: there is **no test file at all** under `frontend/src/features/admin/ui/` (the sole admin test is
`features/admin/model/__tests__/errorMessages.test.ts`, one layer below), so the entire
`RegistrationRequests` / `UserManagement` / `LogViewer` surface moves without moving the number.

**Recommendation** — carried out unchanged. `coverage.all: true` with an explicit
`include: ['src/**/*.{ts,tsx}']` and the existing `test`/`setup` exclusions is the smallest change, and the
report is right that the floors must be re-based in the same commit so the gate is never red for a reason
nobody chose. Add the one exclusion the finding does not name: `react-plotly.d.ts` is a declaration file
with no executable statement, and without excluding it `all: true` will report it as uncovered source.

### TEST-104 — The pool suite's two contention tests observe neither queueing nor timeout

**Severity** — HIGH

**Zone** — "Decisions the product acts on, and the value of each an assertion would reject"

**Observation** — **CONFIRMED at HIGH, and understated.** Every cited location resolves verbatim. The
runtime evidence reproduces: `uv run pytest tests/test_db_pool.py::TestDbPoolExhaustion -p no:cacheprovider -q`
→ **`4 passed in 5.10s`** (the report recorded `4 passed in 6.21s`; the count matches, the wall time does
not and is not load-bearing). The **mutation test the report did not run was run here**, read-only against
the `postgres` maintenance database on the `test-db` container — it creates and drops nothing. It produced
a stronger result than the report claimed, and it invalidates half of the recommendation.

**Evidence** — `tests/test_db_pool.py:267-271` is the quoted `hold_first_connection`, `:294-297` the two
assertions, `:92-97` the queueing assertion with its two abandoned comment lines, `:291` the `can_finish.set()`
that the report places after the measurement at `:288`, `:285-286` the never-entered
`except SQLAlchemyTimeoutError: pass`. Measured, in five probes:

- **Laziness.** `AsyncSession` checks out nothing on `async with`. With `pool_size=1`,
  `pool.checkedout()` is `0` inside `async with factory():`, `0` after it, `0` on entering a second
  session — and `1` only once `execute(SELECT 1)` runs, returning to `0` on session exit. The report's
  premise is exactly right.
- **The shipped test.** Reproducing `test_pool_timeout_on_exhaustion` verbatim: the second request
  **succeeds in 0.0989 s** with `timed_out=False`, so both shipped assertions pass and the
  `SQLAlchemyTimeoutError` arm is never entered.
- **The mutation.** Adding the single line the recommendation proposes — `await s.execute(text("SELECT 1"))`
  before `first_acquired.set()` — makes the second request **raise `SQLAlchemyTimeoutError` after 1.0155 s**.
  `assert second_succeeded` becomes false and `assert elapsed_time < 1.0` fails. **The shipped test does not
  merely fail to observe the property; it asserts the opposite of it.**
- **The queue test.** Reproducing `test_pool_exhaustion_queued_and_recovers` verbatim (3 tasks,
  `pool_size=2`, `hold_duration=0.5`): **`pool.checkedout()` peaks at 0** and elapsed is 0.5134 s. With the
  tasks actually executing, the peak is 2 and elapsed 1.1994 s. `assert elapsed_time >= hold_duration` holds
  in **both** shapes, so it cannot discriminate.

**Consequence** — strengthened. Beyond what is filed: `acquire_and_hold` (`tests/test_db_pool.py:65-72`)
also issues no statement, so **no connection is checked out by any of the three tasks** — the pool in that
test never contends at all, and `assert checked_out == 0` at `:111` is trivially true. The report frames
the defect as an assertion that holds for two outcomes; the stronger truth is that the assertion is
exercised in exactly one outcome, the non-contended one. The blast radius claim also needs one correction:
these two tests build their own engines from literal kwargs, so nothing in `src/mkobi/db/session.py` can
affect them at all — the gap is not "the pool's runtime behaviour is unpinned", it is "the pool's runtime
behaviour is unpinned **by the only two tests that claim to pin it**", while
`TestApplicationPoolWiring` (`tests/test_db_pool.py:345-378`) pins the *wiring* and nothing pins the effect.

**Recommendation** — **half unusable as written; corrected.** The first half is exactly right and is the
mutation this pass executed: make the holder actually hold, then assert the second request *does* raise
`SQLAlchemyTimeoutError` and `elapsed_time >= 1.0`. The second half **cannot be applied to the test as it
stands**: `assert elapsed_time >= 2 * hold_duration` fails at the measured 0.5134 s, because no task checks
out a connection. It requires `acquire_and_hold` to execute a statement before `await asyncio.sleep(...)`
in addition to the assertion change. Both edits stay inside the existing test; no fixture or production
change is involved.

### TEST-105 — `test_different_ips_have_separate_limits` drives one peer, so the per-peer key decision is unobserved

**Severity** — HIGH

**Zone** — "Decisions the product acts on, and the value of each an assertion would reject"

**Observation** — **CONFIRMED at HIGH; one descriptive overstatement corrected.** Every cited location
resolves verbatim. The test drives exactly one peer, exhausts that peer's budget and asserts the single
`429` at `:466`; there is no second address anywhere in the body. The module docstring at `:429` still reads
"Test that rate limits are tracked per IP address" and the class's own comment at `:196-198` names the exact
ambiguity. One sentence in the Observation overstates: **four** of the class's eight integration tests read
the app's counter (`:164`, `:246`, `:313`, `:374`); the other four — `test_login_rate_limit_exceeded`,
`test_register_request_rate_limit_exceeded`, `test_malformed_peer_does_not_500` and
`test_different_ips_have_separate_limits` — do not. This has no bearing on the finding.

**Evidence** — `tests/test_rate_limiting.py:445-466` resolves to the quoted block character for character.
The production side is correct and is the reason this is a coverage finding rather than a defect:
`src/mkobi/api/routes/auth.py:108-109` returns `f"{site}:{resolved_peer}", f"{site}:id:{identifier}"`, so
the peer **is** in the key, and the contract is declared in two places — `docs/SPEC.md:229` ("Rate limiting
bounds identity as well as peer … a per-identifier key in addition to the per-peer key") and
`docs/01-auth/auth-api.md:563` ("Every auth site enforces two bounds at different thresholds: one keyed on
the client peer (IP) and one keyed on an identifier"). No test anywhere drives two distinct peers and
observes separation: the only test that manipulates the transport peer,
`test_malformed_peer_does_not_500` (`:407-416`), asserts only "not a 500". The mutation was re-derived:
collapsing `resolved_peer` to a constant leaves all eight integration tests green, because the four
counter-reading tests compute the key with `_rate_limit_keys` — the *same* function the production path
uses — and so are self-referential. `assert int(app_redis._data[peer_key]) == 50` at `:314` and `:375`
survives a constant peer key unchanged.

**Consequence** — as filed. One user's five failures behind a shared egress address consume that address's
identifier budget for a second user; fifty failures consume the peer ceiling for everyone behind it. The
test named for the property would report it covered. Rate what is true now: the shipped key derivation is
correct, so nothing reaches a user today — which is precisely why this is HIGH and not CRITICAL under this
phase's rubric, whose CRITICAL band requires the suite's green to be affirmatively false today.

**Recommendation** — carried out unchanged; it resolves and the mechanism is already demonstrated in the
same module at `:407-416`.

### TEST-106 — The error-format module asserts an `or` that accepts the pre-RFC-7807 shape, and its 500 test never issues a 500

**Severity** — MEDIUM

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — **CONFIRMED at MEDIUM.** Every cited location resolves verbatim and the logical claim
holds. The four `"detail" in body or "error" in body` assertions accept the shape RFC 7807 replaced; the
500 test issues a request that returns `404`; the second assertion's disjunct can never be true.

**Evidence** — `tests/test_error_response_format.py:1-4` is the quoted docstring; `:29-31` the quoted pair,
repeated at `:40`, `:68`, `:99`; `:105-107` the quoted 500 docstring that names `404`; `:127-132` the quoted
body ending in the vacuous disjunct. The disjunct is provably dead because
`src/mkobi/utils/exceptions.py:257-260` returns `JSONResponse(content=response.model_dump(), ...)` from an
`ErrorResponse` model whose fields are `type`, `title`, `status`, `detail`, `code`, `details` — there is no
`error` key, so `body.get("error", "")` is `""` and `"exception" in ""` is always `False`. Every
cross-reference resolves: `tests/test_layouts.py:369`, `:391`, `:430`, `:498` each loop over
`("type","title","status","detail","code")`; `tests/test_openapi.py:32` and `:48` assert the same five as
`required_fields`; `tests/test_upload_api.py:704-708` asserts a real `500` with
`body["code"] == ErrorCode.FILE_PROCESSING_ERROR.value`. The media-type census reproduces: **zero** files
under `tests/` contain `application/problem+json`.

**Consequence** — as filed. The module's self-description is not held by its own assertions; `type`,
`title` and `status` are never asserted in it; and no test in the suite asserts the media type, so an
unhandled `Exception` rendered by Starlette's default handler instead of the registered RFC 7807 one would
leave the suite green and reach the client as a non-`application/problem+json` body.

**Recommendation** — carried out unchanged. Severity note recorded rather than applied: the 404-as-500 half
matches the rubric's HIGH phrase "a check that can never stop a change", but the same finding states that
two real `500` paths *are* covered elsewhere, which caps the aggregate effect at MEDIUM. Re-grading upward
on a clause the finding itself supplies would be inconsistent with rating what is true now.

### TEST-107 — `_store_aggregates` builds the `dims`/`metrics` mapping itself and no assertion reads it

**Severity** — MEDIUM

**Zone** — "What each stand-in removes, and whether any test observes it elsewhere"

**Observation** — **CORRECTED; severity held at MEDIUM.** The core claim is right and reproduces: the
translation at `src/mkobi/workers/data_worker.py:1218-1222` is its own code, all three collaborators are
mocked, and the only assertion that touches the translated list asserts its **length**, which restates the
mock's configured `return_value` at `tests/test_data_worker.py:1222`. Two things must be corrected: a
**fabricated test name**, and a **consequence that over-reaches into territory already covered**.

**Evidence** — `tests/test_data_worker.py:1213-1222` and `:1250-1257` resolve verbatim; `assert
len(aggregates_arg) == 1` at `:1257` restates `return_value=[{"graph_id": ..., "dims": {}, "metrics": {}}]`
at `:1222`. Re-derived by AST and by text search across all of `tests/`: **no assertion anywhere reads
`aggregates_arg[0]["dims"]` or `["metrics"]`**, and `aggregates_arg` appears nowhere outside this module.
The fabricated name: **`test_store_aggregates_concurrent_append` does not exist** — not in the file, whose
five tests are `test_store_aggregates_{no_graphs, with_graphs, append_mode,
reads_metric_agg_from_producer_shape, logs_processed_count}`, and not in history either (`git log -S
"test_store_aggregates_concurrent_append" -- tests/` returns empty).

**Consequence** — narrowed. The report asserts a rename of *either* key would satisfy every assertion; the
`dims` half is **refuted**. `tests/test_e2e_upload.py:196-198` drives a real background upload through
`_store_aggregates` and `StorageManager`, reads the result back over `GET /data/aggregated` and asserts
`{row.get("category") for row in graph_data["data"]} == {"Alpha","Beta","Gamma","Delta","Epsilon"}` — the
dimension key name is therefore observed end to end, in production shape, today. The `metrics` key name and
`graph_id` are **not** observed on the write side: the e2e test asserts only `len(graph_data["data"]) > 0`
at `:193` and never inspects a served measure name, and the read-path tests that do assert
`graph["metrics"] == ["revenue"]` (`tests/test_aggregated_read_path.py:503`, `:646`) write rows directly
rather than through the comprehension. So the corrected impact is: renaming or dropping `metrics` in the
comprehension, or emitting it under `measures`, satisfies every shipped assertion while the served measure
list stops matching the stored keys — and the recent chart work (`eba2348`, `f8581e0`) moved exactly these
key names.

**Recommendation** — carried out, and it is the right fix: seed the mock with a non-round-trip payload and
assert equality on the whole record, which pins both key names and both values. It also closes the `dims`
half for the unit level; the e2e coverage noted above is real but incidental.

### TEST-108 — The harness sweeps and snapshots the developer's real, shared upload staging directory

**Severity** — MEDIUM

**Zone** — "Reproduction: what varies per run, and what a shared resource carries forward"

**Observation** — **CONFIRMED at MEDIUM; the concurrency claim is narrowed.** Every cited location resolves
verbatim and the destructive half is real. The claim that a *container* run shares the developer's host
directory is wrong: the container resolves its own `platformdirs` path, so the collision is between two
**host** runs.

**Evidence** — `src/mkobi/config.py:590-594` resolves to the quoted `__init__` character for character;
`tests/conftest.py:154-158` to the quoted comment block and `cleanup_stale_temp_files(max_age_hours=0)`;
`tests/test_upload_api.py:691-692` and `:710-713` to the quoted `before`/`after` set comparison. All eight
secondary sites resolve: `tests/test_e2e_upload.py:132`, `:224`, `:297`,
`tests/test_filter_persistence.py:156`, `:289`, `tests/test_filter_values_consistency.py:157`, `:244`,
`tests/test_data_service.py:243`. Confirmed by text search that **`tests/conftest.py` contains no
`temp_dir`, `UPLOAD__TEMP_DIR` or `upload_temp` occurrence at all** — nothing overrides it. The resolved
host path was computed on this machine and matches the report:
`C:\Users\Om\AppData\Local\ZOO\mkobi\tmp_uploads`, which exists (currently empty). The narrowing:
`docker/Dockerfile` sets no `XDG_DATA_HOME` and both tiers run as `USER app` (`:159`, `:187`, `:235`), so
the container resolves `/home/app/.local/share/ZOO/mkobi/tmp_uploads` — a different directory from the
host's. Note for the reader: the narrow run executed for `TEST-104` in this very pass triggered that
session-end sweep against the real host directory.

**Consequence** — as filed for the destructive half: every host-side pytest run deletes every file in the
developer's real staging directory with no age threshold, and that directory is the same one the running
dev app stages uploads into, so a staged upload is removed by running the tests. For the flaky half,
narrowed: `test_upload_submission_failure_is_rfc7807` compares set equality over a directory that a
**concurrent host** run writes into; a container run cannot perturb it. The two host runs do also delete
each other's staged files.

**Recommendation** — carried out unchanged; it resolves and is a single `setdefault` in
`_apply_test_environment()`.

### TEST-109 — `strict_redis` and `mock_redis` describe a rate-limit bypass that no longer exists

**Severity** — LOW (re-graded from MEDIUM)

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — **CORRECTED; re-graded MEDIUM → LOW** against the audited phase's own rubric, which names
this finding class verbatim in its LOW band: "a test-layer comment that misdescribes the harness". The
finding is factually right in every particular; the census figure attached to it is wrong.

**Evidence** — `tests/conftest.py:500-507` resolves to the quoted `_auto_mock_redis` docstring claiming it
"patches AuthService to bypass rate limiting by default"; `:524-527` is the contradicting body comment
recording that the service-owned limiter "has been removed (SECB-2)"; `:540-543` and `:572-575` resolve to
the `mock_redis` and `strict_redis` docstrings. Read against the bodies, the finding holds: all three
fixtures construct a `MockRedis` and `monkeypatch.setattr(redis_client_module, "get_async_redis_client", ...)`,
and **none** of them patches `check_rate_limit` or installs an always-allow limiter — the three differ only
in which instance the test is handed (`strict_redis` yields it at `:594`). The eight integration
signatures at `tests/test_rate_limiting.py:16`, `:75`, `:116`, `:187`, `:267`, `:329`, `:390`, `:428`
request `strict_redis` and none uses the value, which the module's own comment at `:159-164` records.
`docs/06-backend/testing.md:99-101` resolves verbatim to the three table rows. **Census correction:** the
report's "21 (2 definitions, 19 test call sites, 0 patch targets)" is wrong on the middle number. Measured:
**5** occurrences in `src/` (two definitions at `core/security.py:75` and `:123`, three production call sites
at `api/routes/upload.py:182`, `api/routes/client_errors.py:108`, `api/routes/auth.py:168`) and **22** raw
occurrences in `tests/`, of which one is the `conftest.py:573` docstring, three are
`def test_check_rate_limit_*` names and three are docstrings — leaving **15** actual call sites (eight in
`test_auth.py`, seven in `test_rate_limiting.py`). The load-bearing half, **zero patch targets**, is
confirmed.

**Consequence** — as filed and confined to what the finding itself says: no runtime defect ships today, and
the cost is that the harness's description of its guarantees is wrong in three places plus the SSOT. That is
the rubric's LOW definition, not MEDIUM's. `TEST-105` remains the coverage judgement it spoils, and it stands
on its own evidence.

**Recommendation** — carried out; it is documentation and comment work with no behaviour change, and the
finding is right to ask why the parameter is there before removing it.

### TEST-110 — Twenty-four of `test_config.py`'s 123 tests assert on the text of configuration files

**Severity** — LOW (re-graded from MEDIUM)

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — **CORRECTED; re-graded MEDIUM → LOW.** The audited rubric's LOW band names this class
verbatim: "a test whose subject is configuration text it cannot actually detect a change in". The census is
the most exact in the input report and reproduces byte for byte.

**Evidence** — `tests/test_config.py:1618-1633` resolves to the quoted `_service_block` parser and
`:1707-1719` to the quoted PowerShell function parser, both character for character; `:1684-1685` to the
quoted `--no-deps tools ` / `--no-deps app ` assertions. **Census re-derived by AST over the module: 30
classes, 123 test methods in classes, 0 top-level tests, and exactly 24 of the 123 call `read_text`/`open`.**
Matches the report exactly. `tests/test_router_declarations.py:19-21` resolves verbatim to the contrast
quote. The false-pass half of the consequence was re-derived independently and holds:
`Makefile.ps1:261-263` runs lint through `@DevCompose`, the `-f` array declared at `Makefile.ps1:33-35`, so
appending a third `-f` override leaves all 24 assertions green because the function body still contains
`--no-deps tools `.

**Consequence** — as filed for the false-failure half (re-indentation, a YAML anchor, or a wrapped compose
array fails the gate with no behavioural change — the class of failure that gets a whole test deleted) and
as filed for the false-pass half.

**Recommendation** — **substantiated but unusable as a single step; corrected.** The direction is right and
`docker compose config` is available in the same environment, but this is a rewrite of 24 tests across at
least six classes, several of which assert facts `docker compose config` does not surface verbatim
(`test_image_tag_is_not_latest`, `test_compose_images_are_digest_pinned`,
`test_all_built_services_receive_the_same_uv_version` are image-tag and build-argument assertions, not
resolved-config assertions). Executing it as one change would replace 24 weak-but-green checks with a
partial rewrite and a red gate. Take it one class at a time, and keep the two pure-text assertions
(`test_image_tag_is_not_latest`, the digest-pinning test) on the resolved document rather than deleting them.

### TEST-111 — Four `pytest.skip` guards in `test_db_pool.py` cannot fire

**Severity** — LOW

**Zone** — "What the harness manufactures by default"

**Observation** — **CONFIRMED at LOW.** Every cited location resolves verbatim and the logical claim holds:
`if db_url is None` can never be true after `db_url = str(config.TEST_DATABASE_URL)`, because
`str()` never returns `None`.

**Evidence** — `tests/test_db_pool.py:37-41` resolves to the quoted three lines; the identical triple is at
`:128-132`, `:187-191` and `:243-247`, and the URL is passed straight to `create_async_engine` at `:47-54`,
`:135`, `:194` and `:250-257`. `tests/conftest.py:82-83` assigns `DATABASE__DBNAME` and
`DATABASE__TEST_DBNAME` unconditionally, so the URL is always present and the guards are unreachable today.

**Consequence** — as filed: no runtime consequence today; the signal is the defect, because a reader of the
module believes it can run without a database and would get an `ArgumentError` naming a URL instead.

**Recommendation** — carried out; it resolves and is a four-line change.

### TEST-112 — The SSOT's test inventory lists 16 of 89 modules and omits three fixtures

**Severity** — LOW

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — **CONFIRMED at LOW.** Every cited location resolves and both counts are right.

**Evidence** — `docs/06-backend/testing.md:34-53` resolves verbatim to a tree listing sixteen modules ending
at `test_users_api.py  # User management API tests` (`:52`). The suite holds **89** test modules: a
filesystem walk yields **90** `.py` files under `tests/` (88 at the root, one each in `tests/core/` and
`tests/api/`, no `__init__.py` anywhere), minus `conftest.py`. The fixture table at `:96-109` resolves and
omits the three named fixtures, all of which exist — `baseline_data` at `tests/conftest.py:704`,
`mock_db` at `:714`, `valid_csv_content` at `:812`. The report cites `:703`, `:713` and `:811`, one line
above each `def` in every case; those are the `@pytest.fixture` decorators, so the citation is to the
fixture block rather than the signature and resolves. The "understates rather than misstates" judgement on
the bind-mount note holds: `docs/06-backend/testing.md:234-239` names three mounts and
`docker/docker-compose.test.yml:162-182` declares **seven**, each with a comment naming the test that needs
it.

**Consequence** — as filed: documentation cost only, and it is the cost this document exists to remove.

**Recommendation** — carried out; it resolves.

### TEST-113 — No test holds the "no pandas" rule

**Severity** — LOW

**Zone** — "Declared test-layer contracts, and whether anything holds them"

**Observation** — **CONFIRMED at LOW.** Every cited location resolves verbatim and the census reproduces.

**Evidence** — `pyproject.toml:219` resolves to `"pandas-stubs==3.0.0.260204"`. A filesystem+text scan of
`tests/**/*.py` for `pandas` returns **zero** files. The model the recommendation points at exists and is
exactly the right shape: `tests/test_api_layering.py:41-42` is the `_route_modules()` walker, `:55-63` the
`ast`-based census with its `assert offenders == []`, and `:86-91` the anti-vacuity floor the report quotes
verbatim (`assert len(modules) >= 11`, plus the `data.py` and `upload.py` name checks).

**Consequence** — as filed, and the boundary to `TOPO-114` is correctly drawn: phase 08 covers the stub
declaration, this finding covers the absence of a rule-level census, and a new runtime dependency on pandas
would ship undetected because no gate in `Invoke-Lint` or `Invoke-Typecheck` reads for it.

**Recommendation** — carried out; it resolves and the ordering after `TOPO-114` is right.

## Validation-level findings

These are defects **in the audit**, discovered during validation. They carry a separate scale and occupy
this section, never the findings table above.

### VAL-09-101 — `GET /{dashboard_id}/filter-values` is asserted only from its admitting side, and no test drives it without a grant

**Severity** — MEDIUM

**Zone** — Each boundary, from each side (the audited phase's block 4, unexamined at this endpoint)

**Observation** — The audited phase established that `processing-configs` is the only dashboard-scoped
router whose access check is inline *and* unrefused-side tested (`TEST-101`). The other half of that same
enumeration — a dashboard-scoped endpoint with **no** test on its refusing side at all — was not run, and it
has a hit. `GET /dashboards/{dashboard_id}/filter-values` is called from exactly three places in `tests/`,
and all three are admitting.

**Evidence** — `src/mkobi/api/routes/filter_values.py:52-57` declares the endpoint with
`current_user: UserRead = Depends(require_dashboard_read_access)` at `:55`, and the module docstring at `:4`
states "Read operations use dashboard access control (require_dashboard_read_access)". The three call sites
are `tests/test_filter_persistence.py:187` and `:194` (asserting `HTTP_200_OK` and the returned value sets),
`tests/test_filter_persistence.py:256` (asserting `HTTP_200_OK`) and
`tests/test_collection_route_bounds.py:269` (asserting `200` after `AccessRepository().grant_access(...,
DashboardPermission.VIEW)` at `:250-255`). A repository-wide text search for `filter-values` returns no
other test call site, and re-deriving the `403`-assertion map over all `tests/**/*.py` shows the nearest
neighbours are `test_dashboards_api.py` (dashboard CRUD), `test_dashboards_access_api.py` (access grants),
`test_dashboards_filters_api.py` (filter bind/unbind) and `test_refusal_code_normalisation.py` (`DELETE
/dashboards/{id}`, `GET /data/aggregated`, `DELETE .../access/{user_id}`) — none on this path. The endpoint
is documented as a client-facing read: `docs/SPEC.md:177` and `docs/02-dashboards/dashboards-api.md:740`.

**Consequence** — the same class as `TEST-101` and one step further from it: not one-sided but absent. No
shipped test would fail if `require_dashboard_read_access` were dropped from this operation. Graded MEDIUM
rather than HIGH for a reason that is a property of the code, not of the audit: the check here is a resolved
dependency, so unlike `processing-configs` it cannot be dropped by editing a handler body, and
`tests/test_router_declarations.py:46`'s `_operations` helper can prove it for every dashboard-scoped
operation at once without a single new endpoint test. The residual risk is a refactor that inlines it.

**Recommendation** — do not add endpoint tests route by route. Consume the existing enumeration helper once:
walk every operation whose path carries `{dashboard_id}`, assert each resolves
`require_dashboard_read_access` / `require_dashboard_edit_access` (or a stricter one), and carry the
anti-vacuity floor `test_api_layering.py:89-91` already models. That closes this endpoint, closes
`TEST-101`'s inline checks against the same sweep, and survives the next router someone adds.

### VAL-09-102 — The input records "no gap" for the MIME admission surface without disclosing the residual phase 06 preserved

**Severity** — MEDIUM

**Zone** — The template's honesty requirement / the cross-phase seam

**Observation** — The input's Appendix D entry *"Temp-file cleanup on failure paths … No gap found"* and the
Summary's assertion that the libmagic question was checked and correctly not filed are both right about the
**claim**. The defect is in the record: the phase examined `tests/test_mime_validation.py` and
`tests/test_data_service.py`, concluded "no gap", and did not cite the one thing that survives on that
surface.

**Evidence** — `.ai/audit/99-validation/06-file-artifacts-validated-findings.md:731-735` (`VAL-06-012`) ends
with the residual it deliberately preserved: *"What survives, and is worth keeping: the **threshold** is
genuinely unmeasured. Every admitted buffer in the real-detector tests is newline-terminated with at least
three records, so all of them sit on the safe side of the boundary this pass mapped (unterminated: refused
at ≤ 2 data records, admitted at 3; terminated: refused at ≤ 1, admitted at 2)."* Independently confirmed
against the tree: every real-detector buffer in `tests/test_mime_validation.py` is comfortably terminated —
`b"name,value\nfoo,1\nbar,2\n"` (`:283`), the gzip header (`:293`, `:350`), the 16-byte ELF header (`:303`),
`b"just some plain text without csv structure"` (`:316`) — so the admission *threshold* itself, the decision
`src/mkobi/services/file_processing.py` makes on buffer shape, has no shipped test. The base context
requires a phase that touches an already-validated item to cite it as already-known; the input cites neither
`VAL-06-012` nor the boundary.

**Consequence** — a reader of Appendix D concludes the MIME boundary is fully settled. It is not: the
verdicts are covered and the threshold is not. Phase 09 owns the coverage verdict (the measurement itself is
phase 06's), so this is the phase that must carry it, and it must say which half it is not filing.

**Recommendation** — add one entry to Appendix D naming `VAL-06-012` and stating exactly what remains: the
newline-termination and minimum-record-count thresholds at the MIME admission boundary are unmeasured, and
the fix is boundary buffers in `tests/test_mime_validation.py` — which, per `VAL-06-012:726-729`, is the
correct module, not `test_mime_admission_contract.py`, whose docstring declares it host-independent. No new
finding ID is needed for the coverage question itself; it belongs to `ART-101`'s remediation.

## Distribution

The findings fall on three surfaces, and the distribution is unchanged by validation — what changed is that
one of the three is now stronger and two items on it moved a band down. **The backend test assertions
themselves** carry the most: eight findings, of which four are HIGH or the reason a HIGH holds
(`TEST-101`, `TEST-102`, `TEST-104`, `TEST-105`) — every one is code that is correct today behind an
assertion that cannot fail, which is the shape this phase exists to find and the shape that produces false
confidence. **The frontend suite** carries two HIGH findings plus the largest uncovered surface in the
project: a module-level mutable state machine with no test (`TEST-102`) and a coverage gate that reads
50 / 66 files (`TEST-103`), against an admin tier with no test file at all. **The shared harness and its
declarations** carry five findings, three of which are documentation-versus-behaviour mismatches
(`TEST-108`, `TEST-109`, `TEST-112`) and two of which are self-description at the LOW band
(`TEST-109`, `TEST-110`).

- Backend assertion quality: TEST-101, TEST-102*, TEST-104, TEST-105, TEST-106, TEST-107, TEST-110*, TEST-111, TEST-113 (9)
- Frontend: TEST-103 (1) · Harness and its declarations: TEST-108, TEST-109*, TEST-112 (3)
- Validation-level: VAL-09-101, VAL-09-102 (2)

\* moved band, or reached by validation rather than as filed.

## Cross-Finding Analysis

Three causes account for eleven of the thirteen findings, and validation sharpened two of them.

**The assertion is written against the shape of the input it was handed rather than against the value the
product produced.** `TEST-104` (two contention tests, one of which measures zero connection checkouts),
`TEST-105` (one peer, with the counter-reading tests self-referentially keyed), `TEST-106` (an `or` plus a
`404` posing as a `500`), `TEST-107` (`len()` of a mock's own return value) and `TEST-110` (compose and
PowerShell text substrings) are one failure mode at five sites. Validation added the decisive datum for the
first: the mutation test shows `TEST-104`'s test does not merely fail to observe the property, it **asserts
its negation**.

**A declared contract is written down and nothing holds it.** `TEST-109` (three fixture docstrings plus the
SSOT describe a bypass `SECB-2` removed), `TEST-112` (the SSOT's inventory is stale) and `TEST-113` (a hard
rule with no census) are the same pattern at three strengths. `TEST-103` is the fourth member seen from the
gate side — a threshold declared with no statement of what it is read over. `VAL-09-101` is the fifth and the
sharpest: a dependency declared as a contract, correct in the code, with no test on its refusing side.

**A measurement or a census that is narrower than the thing it is read over.** `TEST-103` is the load-bearing
case, and it now carries a verified number rather than an asserted one: **37 of 66 files, 540/732 statements,
73.77 %**. `TEST-109`'s `check_rate_limit` census and `TEST-101`'s `403`-site census were the two figures
that did not reproduce, and both undercounted — which is the safe direction for a coverage report but still
means the report's own numbers cannot be quoted without re-derivation.

`TEST-102` and `TEST-108` stand alone: the first is the only untested state machine in the client tier, the
second is the only finding whose blast radius is the developer's own machine rather than a decision the
product takes.

## Roadmap

Ordered by what unblocks the rest. Validation changed three entries from the input's plan: `TEST-104`'s
second half is rewritten so it is executable, `TEST-107` is narrowed to the `metrics` key, and `TEST-109`
and `TEST-110` drop to the LOW band and leave the numbered sequence.

**Step 1 — close the one-sided authorization boundaries (`TEST-101`, `VAL-09-101`), as one sweep rather than
two.** `TEST-101` is the only item here with a cross-tenant consequence and `VAL-09-101` is the same class
one endpoint over; doing them separately means writing endpoint tests that the sweep makes redundant.
Execute the operation-enumeration sweep in `VAL-09-101` first, add `TEST-101`'s three refusal tests, then
move the `processing-configs` check onto `Depends`. **Before starting Step 2:** confirm with phase 12 that
the authorization decision itself is not being changed, because the second half alters where the check lives.

**Step 2 — repair the assertions that cannot fail (`TEST-104`, `TEST-105`, `TEST-106`, `TEST-107`).** Four
independent edits across four files, no shared dependency, any order. `TEST-104` is the only one whose fix
was executed here rather than reasoned, so start there and keep the measured numbers as the acceptance
criterion: `elapsed_time` must reach ≥ 1.0 s and `second_succeeded` must become false under the corrected
holder; the queue test's `checkedout()` peak must become 2 before `>= 2 * hold_duration` is asserted.
**Before starting Step 3:** run the four modules and confirm each new assertion fails when its property is
inverted — a repaired assertion that cannot be made to fail has replaced one gap with another.

**Step 3 — make the measures mean what they say (`TEST-103`, `VAL-09-102`).** `TEST-103` first, because
re-basing the frontend floors is the only step that turns a gate red for a reason nobody chose; do it in one
commit, exclude `react-plotly.d.ts` in the same change, and record the new numbers in `vite.config.ts`. Then
`VAL-09-102`, which is one Appendix D entry and a handful of boundary buffers in an existing module.
**Before starting Step 4:** the frontend gate is green with the new floors.

**Step 4 — cover the untested client state machine (`TEST-102`).** Second `describe` block in
`errorSurfaces.test.ts`, which already owns the install-a-failing-adapter idiom. Four postconditions, not
three. The one to get right is the unregistered-handler arm: `authApi.ts:37` is the only thing standing
between production and it.

**Step 5 — isolate the shared staging directory (`TEST-108`).** Deliberately last: one `setdefault` in
`_apply_test_environment()`, but it changes the directory every upload test writes into.

**Outside the sequence.** `TEST-109`, `TEST-110`, `TEST-111`, `TEST-112`, `TEST-113` are LOW-band
documentation and hygiene work; take them in one pass over `tests/conftest.py`'s description
(`TEST-109` + `TEST-112` together, as the input's plan also pairs them), `TEST-113` after `TOPO-114`, and
`TEST-111` with whichever step next touches `tests/test_db_pool.py`. `TEST-110` is the one that must **not**
be taken as a single change — it is a rewrite of 24 tests across at least six classes and belongs one class
at a time.

## Rollout Safety

**Step 1's dependency move is the only step that changes production behaviour.** Moving the `processing-configs`
check from the handler body onto `Depends` changes the order in which a refusal is produced: a request with
both an invalid body and no grant flips from `422` to `403`, and
`tests/test_request_boundary_extra_forbid.py:145-153` asserts `422` for exactly that combination. That test
must change with the move, and `tests/test_openapi.py:72`'s path lookup must be re-checked against the
regenerated document. The refusal code, status and detail are unchanged, so no client contract moves.
`VAL-09-101`'s sweep is assertion-only and moves no behaviour; running it before Step 1's move means the
sweep reports the three inline handlers as failures first, which is the intended signal. Revert is a
single-file revert of `processing_configs.py` plus the new tests.

**Step 3 turns the frontend coverage gate red, and that is the point of the change.** It lands in
`.\Makefile.ps1 check`, which `Makefile.ps1:281-289` chains short-circuit-first, so a red `fe-lint` will
hide a red `fe-test` — re-baseline the four floors in the same commit as the `coverage.all` change so the
gate is never red for an unchosen reason, and confirm `frontend/coverage/` stays gitignored
(`.gitignore:53`, verified present and `git ls-files frontend/coverage` empty). With `all: true` the report
also gains the 29 currently-absent files, several of which are `.tsx` components the suite never imports;
expect the per-file HTML report to grow sharply and the text summary to reorder.

**Step 2 changes no production code and no assertion other than the ones named — with one exception the
input's plan does not flag.** `TEST-104`'s corrected holder adds `await s.execute(text("SELECT 1"))` to a
test that currently opens no connection. `pool_pre_ping=True` is set on that engine, so the mutation adds a
round trip per checkout inside a 6-second test module; measured cost is under 100 ms. No other test in the
module shares the engine.

**Step 5 is the one to watch.** It moves every upload test's staging directory, so a test that asserts on a
*path string* rather than on a file's presence needs its expectation updated. `tests/test_config.py:401`
(`test_upload_temp_dir_is_absolute_without_env`) constructs its own `Settings(_env_file=None)` and is
unaffected. `tests/test_upload_api.py:274-282` overrides `upload_temp_dir` with a mock config pointing at
`tempfile.gettempdir() / "mkobi_test_uploads"` — note that is a **system temp directory**, so it survives
Step 5 unchanged and will remain the one test in the module writing outside a per-run directory.
`tests/test_streaming_size_limit.py` overrides `upload_temp_dir` to `tmp_path` at five sites
(`:103`, `:157`, `:212`, `:272`, `:332`) and is likewise unaffected. Revert is one line in
`tests/conftest.py`.

**One hazard this pass introduced into the environment rather than into the code:** every host-side pytest
run in this session executed `tests/conftest.py`'s session-end sweep against
`C:\Users\Om\AppData\Local\ZOO\mkobi\tmp_uploads`, the developer's real staging directory (`TEST-108`). The
directory was empty before and after, so nothing was lost here — but that is the defect, not a mitigation.

## Appendices

### A. Disposition tally against the per-finding verdicts

| Verdict | Count | Identifiers |
|---|---|---|
| CONFIRMED | 9 | TEST-101, TEST-103, TEST-104, TEST-105, TEST-106, TEST-108, TEST-111, TEST-112, TEST-113 |
| CORRECTED | 4 | TEST-102, TEST-107, TEST-109, TEST-110 |
| REJECTED | 0 | — |
| MERGED | 0 | — |
| **Total dispositions** | **13** | against **13** identifiers filed — the tally agrees with the per-finding verdicts |

Identifier integrity: no input identifier was renumbered; every one of the thirteen carries a verdict, a
re-derivation and a final band. The `TEST-` namespace and the `VAL-` namespace are in separate sections and
never share a table.

### B. Severity movement

| Identifier | Filed | Final | Mechanism |
|---|---|---|---|
| TEST-101 | HIGH | **HIGH** | none |
| TEST-102 | HIGH | **HIGH** | none (consequence (2) replaced) |
| TEST-103 | HIGH | **HIGH** | none |
| TEST-104 | HIGH | **HIGH** | none (strengthened) |
| TEST-105 | HIGH | **HIGH** | none |
| TEST-106 | MEDIUM | **MEDIUM** | none |
| TEST-107 | MEDIUM | **MEDIUM** | none (impact narrowed) |
| TEST-108 | MEDIUM | **MEDIUM** | none (concurrency claim narrowed) |
| TEST-109 | MEDIUM | **LOW** | audited rubric LOW band: "a test-layer comment that misdescribes the harness" |
| TEST-110 | MEDIUM | **LOW** | audited rubric LOW band: "a test whose subject is configuration text it cannot actually detect a change in" |
| TEST-111 | LOW | **LOW** | none |
| TEST-112 | LOW | **LOW** | none |
| TEST-113 | LOW | **LOW** | none |

**Final counts — CRITICAL 0 · HIGH 5 · MEDIUM 3 · LOW 5** (13 findings), plus **2 validation-level findings**
at MEDIUM.

### C. Namespace ruling

**`TST-` is occupied far beyond the disclosure.** The input discloses that `.ai/plans/_code-context/09-test-coverage-code-context.md`
and `.kilo/commands/audit/phases/09-audit-test-coverage.md:146` name `TST-` and that the corresponding
validated report is absent. Verified true: `.ai/audit/99-validation/09-test-coverage-validated-findings.md`
did not exist before this run. But `TST-001 … TST-018` are **load-bearing provenance** across
`.ai/decisions/PO-2026-10-03-product-owner-rulings.md:395` (`TST-013`),
`.ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md:481`, `:491`, `:1013-1014`
(`TST-013`, `TST-003`), `.ai/plans/00-owner-rulings-2026-10-03.md:158`,
`.ai/plans/16-chart-presentation-contract-remediation-execution.md:729`, `:752`, `:756-759`, `:1010`, `:1040`,
`.ai/plans/_code-context/{13,14,16}-*.md` and `.ai/tasks/CQLT-2-enforce-dashboard-access-audience.yaml:284`.
The input's choice of `TEST-101`+ was therefore **correct and necessary**, not merely cautious.

**`TEST-` collides with nothing.** A repository-wide search for `TEST-NNN` returns hits only inside
`.ai/audit/09-test-coverage/findings.md` itself.

**A collision the input could not have disclosed, ruled here.** The absent phase-09 validation report used
`VAL-09-001 … VAL-09-012`, declared at `.ai/plans/_code-context/09-test-coverage-code-context.md:8`
(`defect_prefix: VAL-09-`) and referenced in
`.ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md:245` and
`.ai/plans/00-owner-rulings-2026-10-03.md:92`. Those twelve are provenance for shipped remediation work —
exactly the situation `VAL-06-013` ruled on for phase 06 (`99-validation/06-file-artifacts-validated-findings.md:737-754`),
where `VAL-06-001 … VAL-06-010` were found occupied and the phase's own numbering was moved to `VAL-06-011`.
**Ruling applied here: this phase's validation-level findings start at `VAL-09-101`.**

### D. Census spot-checks — every derived figure re-measured

| Figure | Filed | Independently measured | Verdict |
|---|---|---|---|
| test modules | 89 (87 + 1 + 1) | 90 `.py` files − `conftest.py` = 89 (88 at root, 1 `core`, 1 `api`) | ✓ |
| `test_*` functions / methods | 1585 | 1585 excluding `conftest.py`; 1586 including it | ✓ |
| `assert <bool literal>` | 0 | 0 | ✓ |
| `pytest.mark.xfail` | 0 | 0 | ✓ |
| `pytest.skip` / `skipif` | 5 | 5 | ✓ |
| `time.sleep` | 0 | 0 | ✓ |
| `tests/` files mentioning `pandas` | 0 | 0 | ✓ |
| `tests/` files mentioning `application/problem+json` | 0 | 0 | ✓ |
| `403` assertion sites in `tests/` | 41 | **54** (52 `==`, 2 `!=`; 42 carry the `HTTP_403_FORBIDDEN` literal; 19 modules) | ✗ corrected — immaterial to `TEST-101`, whose load-bearing claim ("none targets `/processing-configs/`") reproduces |
| `check_rate_limit` occurrences | 21 (2 defs, 19 test call sites) | 27 raw (5 in `src/`, **22** in `tests/`); **15** actual test call sites after removing 1 docstring, 3 `def` names and 3 docstrings | ✗ corrected — "0 patch targets" reproduces |
| frontend test files | 30 | 30 | ✓ |
| `test_config.py` tests reading file text | 24 of 123 | **24 of 123** (30 classes, 0 top-level tests) | ✓ exact |
| non-test `.ts`/`.tsx` under `frontend/src` | 66 | **66** (97 total − 31 test files) | ✓ exact |
| files in `coverage-final.json` | 37 | **37**, all non-test | ✓ exact |
| statements over the measure | 540/732 = 73.8 % | **540 / 732 = 73.77 %** | ✓ exact |

**Reading of the two errors.** Every figure that requires an AST walk came out exact — six of six,
including the two the report's own method section calls AST-derived. The two that came out wrong are the two
that a substring count would also produce, and both undercount. This is consistent with the input's claim
that its census is AST-derived, and it is why every count in its Observation that carries a *verdict* was
re-derived here rather than accepted.

### E. Coverage ledger — what each block of the validation method actually reached

| Check | Items reached | Result |
|---|---|---|
| Cited locations re-opened | 13 findings, **86** distinct `file:line` citation groups | **86 of 86 resolve.** Two defects found, neither in a `file:line` anchor: 1 off-by-one (`refreshHandler.ts:20-28` — the function ends at `:29`) and 1 fabricated bare test name (`test_store_aggregates_concurrent_append`, absent from the file and from history) |
| Runtime claims reproduced | 1 of 1 reproducible (`pytest tests/test_db_pool.py::TestDbPoolExhaustion`) | reproduced: **4 passed in 5.10s** against the filed 6.21s |
| Mutation tests executed | 1 (`TEST-104`) | executed read-only; shipped assertions **fail** under the mutation |
| Independent measurements | 14 census figures, 1 pool probe (5 sub-probes), 1 router-enumeration sweep | see Appendix D and `TEST-104`'s Evidence |
| Disclosures checked | 4 | namespace ruling upheld and extended; libmagic correction **upheld**; 5 remediated items spot-checked (**5 of 5 hold**); `CQ-109`/`CQ-110` correctly unfiled |
| Zones quoted verbatim | 13 of 13 | all thirteen match the audited phase's block titles exactly |

### F. Claims left unsettled, with reasons

- **`vitest run --coverage` was not executed.** It rewrites `frontend/coverage/`, the working-tree artefact
  every `TEST-103` figure is computed from. All `TEST-103` numbers are therefore as-of the artefact's mtime
  (2026-10-05 16:04:28), re-derived from that file rather than from a fresh run. The **37-of-66 file-set
  comparison is unaffected** — it is made against the current filesystem walk. Whether the 37 files'
  *per-file percentages* still reflect the tree after the nine most recent commits is **unsettled**.
- **The full backend suite was not run**, by instruction: the test database is shared with concurrent phases.
  Exactly one narrow selection was executed. No verdict in this report rests on suite-wide redness or
  greenness.
- **`/home/app/.local/share/ZOO/mkobi/tmp_uploads` was not read.** The container-side path was derived from
  `docker/Dockerfile` (no `XDG_DATA_HOME`; `USER app` at `:159`, `:187`, `:235`) rather than executed, so
  `TEST-108`'s narrowing is reasoned from configuration, not measured. It does not depend on the container
  path being *different* from the host's for the destructive half, which is the load-bearing half and is
  measured.
- **No scratch file was created.** `external_directory` is `deny`, so the pool probe was piped to
  `uv run python -` on stdin instead of written to `C:\Users\Om\AppData\Local\Temp\kilo`. **Nothing remains
  to clean up and no leftover path exists.** The per-run test database `bidb_test_*` created and dropped by
  the one pytest process is dropped by that process's own session-end teardown. This report is the only file
  this pass wrote.
