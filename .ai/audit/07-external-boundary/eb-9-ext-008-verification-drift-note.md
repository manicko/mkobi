# EB-9 — `EXT-008` verification: drift note

**Block:** phase 07 `EB-9` (verification-only) · **Finding:** `EXT-008` · **Related:** `VAL-07-005`,
`VAL-07-008`, `EXT-004`, `EXT-005`, `HO-2`
**Author:** Implementor (verification-only block; no production code edited)
**Date:** 2026-10-03
**Plan anchor:** `1a57bf3`; **verification HEAD:** `2f3cc1a` (10 commits ahead of the anchor, 9 of them
the sibling EB-1…EB-8 blocks)
**Method:** re-derived from the tree by reading code and by running the Docker test path
(`docker compose -p mkobi-test -f docker/docker-compose.test.yml run --rm --no-deps test-app pytest`).
Collection counts are recorded, not exit codes.

---

## Headline

**The outcome is DRIFT, and the drift is wider than the plan's own `F3` correction anticipated.** Nine
of the block's factual premises do not hold against the HEAD tree, and three of them are **dead
selectors/classes the task brief itself named as green**. The most important single result is that the
**four `test_cross_worker_revocation_*` / `test_publish_*` tests do not exist** — `-k` collects **0** —
so cross-worker consistency is **not pinned by any test in this repository**, and the plan's premise
that defect (c) might already be mitigated by those tests is refuted: there is nothing there to mitigate
it.

Three of the four claimed defects are **disproven from the tree** (there is no revocation cache, so (a)
and (b) have no mechanism; and all revocation reads/writes share Redis, so (c) is inherently consistent
across workers). One — the drift in the store contract — is **confirmed** and owned by phase 04 `AB-1`.

---

## 1. Plan claims vs the tree

| # | The plan/brief claims | Verified at HEAD | Verdict |
| - | --------------------- | ---------------- | ------- |
| 1 | Six revocation sites: `deps.py::get_current_user_dependency` ×2 · `auth.py::refresh` ×2 · `permissions.py::_get_current_user_with_session` ×2 | Exactly these six, by symbol: `deps.py:556` (`is_token_revoked`), `deps.py:578` (`is_user_tokens_revoked`); `auth.py:463` (`is_refresh_token_revoked`), `auth.py:501` (`is_user_tokens_revoked`); `permissions.py:326` (`is_token_revoked`), `permissions.py:335` (`is_user_tokens_revoked`) | **CONFIRMED** |
| 2 | `core/security.py` has three revocation readers used across the six sites | Three present: `is_token_revoked:521`, `is_refresh_token_revoked:545`, `is_user_tokens_revoked:603` | **CONFIRMED** |
| 3 | No entry point is bypassed | Reset/approval flows issue cookies only on `login`/`refresh`; the refresh path runs **both** revocation reads before minting. No reset/approval route mints a session without a revocation read; see §3 | **CONFIRMED (with drift — see §3)** |
| 4 | `reset_password_admin` sets **three** reset cookies | **No reset route sets any cookie.** The tree has exactly **one** cookie, `COOKIE_NAME="mkobi_refresh_token"` (`core/security.py:45`), set only by `auth.py::_handle_login:235` and `auth.py::refresh:547`. `reset_user_password_admin_endpoint` (`admin.py:249`) sets none; `AuthService.reset_password_admin` sets none | **REFUTED** |
| 5 | `tests/test_temp_password_store.py::test_store_fail_open_on_error` — present, 1 collected, green | `-k` collects **1**, PASSED in the 8-selector batch | **CONFIRMED** |
| 6 | `tests/test_auth_service.py` — three `approve_registration_request` ordering pins + `test_reset_user_password_admin`; green | All four live and green: `test_approve_registration_request_commit_precedes_store`, `…_failed_commit_leaves_no_credential`, `…_store_failure_after_commit_keeps_user`, and `test_reset_user_password_admin` (in `tests/test_admin_user_management.py::TestResetUserPassword`, not `test_auth_service.py`) | **CONFIRMED (file location drifts)** |
| 7 | `tests/test_config.py::TestRevocationMarkerTtlValidation` — green | **The class does not exist.** `git grep` → 0 hits; `-k TestRevocationMarkerTtlValidation` → **0 collected, exit 5**. `test_config.py` contains no revocation test and no `temp_password_ttl` test | **REFUTED** |
| 8 | `tests/test_task_queue.py::TestServicesDoNotImportRq::test_no_service_module_imports_rq` — green, unmodified | `-k` collects **1**, PASSED | **CONFIRMED** |
| 9 | "The revocation-consistency tests exist — 4 tests named `test_cross_worker_revocation_*` / `test_publish_*`, all green" | **They do not exist.** `git grep` → 0 hits; `-k "test_cross_worker_revocation or test_publish_"` → **0 collected, 1410 deselected** | **REFUTED — the most important verification of the block** |
| 10 | `TempPasswordStore.store` is `async def store(...) -> bool`, fails open; `retrieve` fails loud raising `TempPasswordStoreUnavailableError` | Exactly so: `store:91` returns `bool`, never raises; `retrieve:125` raises `TempPasswordStoreUnavailableError:156`; class docstring argues the split | **CONFIRMED** |
| 11 | `EXT-005` write side already landed in `478015b`, an ancestor of the anchor; `docs/SPEC.md` row 3.20 records it as phase 04 `AB-1` | `git merge-base --is-ancestor 478015b 1a57bf3` → **exit 0** (ancestor). `SPEC.md:226` row **3.20** records `AB-1`. The plan's OUT table "in flight" entry is stale | **CONFIRMED (stale entry noted)** |
| 12 | Dead selector `test_retrieve_fail_graceful_on_error` does not exist; live test is `test_retrieve_raises_on_store_fault` | `git grep test_retrieve_fail_graceful_on_error` → **0 hits in `tests/`** (only in `.ai/` corpus); live test at `tests/core/test_temp_password_store.py:237`. Dead `-k` → **0 collected, exit 5** | **CONFIRMED** |
| 13 | A dead `-k` "exits 0 with 0 collected … returns green and verifies nothing" (plan's standing rule) | A dead `-k` exits **5** (`NO_TESTS_COLLECTED`), loudly red. Measured: `-k test_retrieve_fail_graceful_on_error` → exit **5** | **REFUTED (mechanism); the discipline to read counts stands** |
| 14 | "nine `credential_stored` assertions" (brief, and plan `F3`) | **Seven** `assert ... credential_stored` lines in `tests/test_auth_service.py` (760, 879, 918, 972, 1013, 1055, 1216), plus one in `test_admin_user_management.py` if counted. `git grep assert.*credential_stored -- tests/` → **7** | **DRIFT (figure overstated; direction — "more than the historical four" — holds)** |
| 15 | `VAL-07-005`'s prescribed compensation is contradicted by four artefacts incl. the landed `credential_stored` return | Confirmed: `credential_stored` is a second return artefact from both `reset_password_admin` and `approve_registration_request`, contradicting "mark the request failed and remove the account" (report line 685). `test_approve_registration_request_store_failure_after_commit_keeps_user` pins the opposite | **CONFIRMED** |
| 16 | `EXT-004`: "if the TTL is set to 0, the value stays forever" is false; real gap is `must_change_password` cleared in Postgres but not Redis | `config.py:712-728` refuses `temp_password_ttl_seconds < 60` (includes 0 and −1). Field is `force_password_change`, **not** `must_change_password` (0 hits for the latter). `force_password_change` is a Postgres column only; Redis never stores it | **CONFIRMED (brief's field name wrong; see §6)** |

---

## 2. The three defects

### Defect (a) — "reset flow clears the database marker but not the in-memory cache"

**DISPROVEN.** There is **no in-memory revocation cache anywhere in the tree**:
- `core/permissions.py::_decode_token_cached:249` is documented "Caching removed to ensure token
  revocation checks always run"; it delegates straight to `decode_token`.
- `git grep lru_cache|cache|memory` over `core/security.py`, `core/redis_client.py`, `api/deps.py`
  returns only the config-singleton docstring.
- The revocation state is a **Redis** key (`user_tokens_revoked:{user_id}`, `token_blacklist:{jti}`,
  `refresh_token_blacklist:{jti}`), not a database marker, and not an in-process cache.

There is nothing to be stale. The described window has no mechanism in this tree.

### Defect (b) — "the cache write has no TTL, and `TTL = -1` is not refused at validation"

**DISPROVEN.** No revocation cache exists (see (a)). The only TTL validator is
`config.py::Settings.validate_temp_password_ttl` (`:712-728`), which raises for any value `< 60` —
so `0` and `-1` are both **refused**. The claimed test pin `TestRevocationMarkerTtlValidation` does
not exist (0 collected, exit 5).

### Defect (c) — "invalidation is not published across workers; a token revoked on worker A stays accepted on worker B"

**DISPROVEN.** Cross-worker consistency is **inherent** in the design, not mitigated by a test:
- Every revocation **write** (`revoke_token:504`, `revoke_refresh_token:517`,
  `revoke_all_user_tokens:599`) is a Redis `setex` on the shared Redis instance.
- Every revocation **read** (`is_token_revoked:536`, `is_refresh_token_revoked:560`,
  `is_user_tokens_revoked:627`) is a Redis `exists`/`get` on the same shared instance.
- No worker holds a local copy. A revocation on worker A is therefore visible to worker B on its next
  request, because both read the same Redis.

**And the test the plan hoped would pin it does not exist.** `-k "test_cross_worker_revocation or
test_publish_"` collects **0** of 1410. Cross-worker consistency is **not pinned by any test** — but the
defect it was meant to guard against is also **absent**, because there is no cache to publish into. The
correct finding is: *no publication mechanism is needed; no test pins the shared-store property.*

### Why the plan described these defects

The three defects describe a **cache-backed revocation design** (in-memory cache + TTL + pub/sub
invalidation) that this branch does not implement. The plan's finding was authored against an older
tree/branch. On this line the revocation state is direct-to-Redis with caching explicitly removed, so
(a), (b) and (c) have no referent. This is the drift the block exists to record.

---

## 3. The six revocation sites — callers and error handling

| # | Site (member) | Containing function | `src/` caller | Error handling of `RevocationStoreUnavailableError` |
| - | ------------- | ------------------- | ------------- | --------------------------------------------------- |
| 1 | `is_token_revoked` @ `deps.py:556` | `get_current_user_dependency` | **Yes** — the universal auth dependency (`CurrentUser` alias and every role/dashboard dep) | Caught by the dedicated arm `deps.py:644-652` → `AppException(SERVICE_UNAVAILABLE)` → **503** |
| 2 | `is_user_tokens_revoked` @ `deps.py:578` | `get_current_user_dependency` | **Yes** (same function) | Same arm → **503** |
| 3 | `is_refresh_token_revoked` @ `auth.py:463` | `refresh` | **Yes** — `POST /api/v1/auth/refresh` | Local `try/except` `auth.py:462-469` → `AppException(SERVICE_UNAVAILABLE)` → **503** |
| 4 | `is_user_tokens_revoked` @ `auth.py:501` | `refresh` | **Yes** | Local `try/except` `auth.py:500-509` → **503** |
| 5 | `is_token_revoked` @ `permissions.py:326` | `_get_current_user_with_session` (via `get_current_user:265`) | **NO `src/` caller** — `get_current_user` has zero callers; `deps.py` imports only `check_dashboard_access, check_role, AuthenticationError` from `permissions` | **None** — the bare `except Exception` at `permissions.py:357` re-raises; the function is uncalled |
| 6 | `is_user_tokens_revoked` @ `permissions.py:335` | `_get_current_user_with_session` | **NO `src/` caller** (same) | Same |

Sites 5 and 6 are **dead code** at HEAD (the module note at `permissions.py:332` says so). They remain
edit sites for any future guard, but no shipped request reaches them.

---

## 4. No entry point is bypassed

`reset_user_password_admin_endpoint` (`admin.py:249`) and `register-request`/approval flows do not mint
a session cookie and are guarded by `AdminUser` (`require_admin_role` → `get_current_user_dependency`),
which runs the six-site revocation reads. The only routes that set the refresh cookie are
`login`/`login/form` and `refresh`; `refresh` runs **both** revocation reads (`auth.py:463`, `:501`)
before minting. **No shipped path issues a session without a revocation read.** This part of the brief's
`EXT-008` premise holds — but it holds for the **single-cookie** flow that exists, not for the
three-cookie flow the brief describes.

---

## 5. Cookies — actual names and flags

The brief asks for three reset cookies. **There is exactly one cookie in the tree.**

| Symbol | Value | Where set |
| ------ | ----- | --------- |
| `core/security.py::COOKIE_NAME` | `"mkobi_refresh_token"` | `auth.py::_handle_login:235` (login), `auth.py::refresh:547` (rotation) |

Flags are applied by `core/security.py::set_secure_cookie:445`:

| Flag | Value | Source |
| ---- | ----- | ------ |
| `httponly` | `True` | `COOKIE_HTTPONLY` (`security.py:43`) |
| `secure` | `config.app.cookie_secure` — **default `True`** | `config.py:566-569`; `APP__COOKIE_SECURE=false` for dev |
| `samesite` | `"strict"` | `COOKIE_SAMESITE` (`security.py:44`) |
| `max_age` | `refresh_token_expire_minutes * 60` | caller |

So the one cookie that exists **does** carry `HttpOnly`, `Secure` and `SameSite=Strict`. The
**three-cookie reset flow does not exist** — not on `feat/react` (HEAD), and not on `feat/jwt`, whose
`admin.py` reset route also sets no cookie. `reset_password_admin` never touches `Response.set_cookie`.

---

## 6. `EXT-004` — the real retention gap, corrected

- The plan/task claim *"if the TTL is set to 0, the value stays forever"* is **false**.
  `config.py::validate_temp_password_ttl` refuses `< 60`, so `0` and `-1` both raise at validation.
- The field the brief calls `must_change_password` does **not exist** (0 hits). The real symbol is
  **`force_password_change`** (`models/user.py:49`, `db/models/user.py:69`, `services/auth_service.py`
  clear/set at `:524`, `:600`, `:687`).
- **Real gap:** `force_password_change` is written and cleared **only in Postgres**. Redis stores the
  temp credential (`temp_pwd:{token}`) and the revocation markers, never this flag. The flag is read
  fresh from the DB on every request (`deps.py:613` off the loaded `UserRead`).
- **The dependency's true shape:** it is **one-way**, not "mutual". Postgres is the **sole** authority
  for `force_password_change`; Redis never backs it and cannot. Redis is authoritative for the
  *credential's retrievability* and for *revocation*, which Postgres never stores. The two stores hold
  **disjoint** state that the flows happen to sequence together (commit password+flag, then store the
  credential), but neither can reconstruct the other's fact. Calling it "mutual dependence" overstates
  it: there is no read of one that consults the other.

---

## 7. `HO-2`'s stale premise and `VAL-07-005`'s second artefact

**`HO-2`.** The hand-over register instructs a receiver *"do not edit the store's contract"*. That guard
now protects a contract phase 04 **already changed**: `478015b` (`AB-1`, `SPEC.md` 3.20) inverted both
contracts **before** the plan anchor. `store` is now `-> bool` (fail-open); `retrieve` now **raises**
`TempPasswordStoreUnavailableError` (fail-loud). A receiver reading `HO-2` as a description of the
current contract would guard the wrong shape. The plan's `F3` notes this in the drift table; this block
**confirms it against the tree** and records it so the register does not mislead its receiver.

**`VAL-07-005`.** The report's prescribed compensation — *"commit the durable record first, then publish
the credential, and on a publish failure compensate the committed record (mark the request failed and
remove the account)"* (report line 683-688) — is contradicted by a **second** return artefact the plan
did not originally name: the landed **`credential_stored`** key on both
`AuthService.reset_password_admin` and `AuthService.approve_registration_request`. `credential_stored`
**reports** a failed handoff (`200`, per `SPEC.md` 3.20) rather than **preventing** it or removing the
account. `VAL-07-005`'s four-pin enumeration is therefore incomplete; the live set is seven
`credential_stored` assertions (plan `F3` said nine — overstated), plus `test_store_fail_open_on_error`
and `test_store_returns_true_on_success`. **Recorded, not resolved** — the contradiction belongs to
phase 04, which owns the store contract.

---

## 8. Collection counts (every selector run)

Test total at HEAD: **1410 collected**.

| Selector | Collected | Result |
| -------- | --------- | ------ |
| `test_cross_worker_revocation or test_publish_` | **0** (1410 deselected) | **NOTHING VERIFIED** |
| `TestRevocationMarkerTtlValidation` | **0** (1410 deselected) | **NOTHING VERIFIED** |
| `test_retrieve_fail_graceful_on_error` (dead) | **0** (1410 deselected) | exit **5** |
| 8-selector EB-9 batch (store fail-open, store true-on-success, retrieve-raises, reset_user_password_admin, 3 approve pins, store_failure_after_commit_returns_success) | **8** | 8 PASSED |
| 6-selector batch (reset ordering + 3 credential_stored + approve credential_stored + no_service_module_imports_rq) | **6** | 6 PASSED |
| `tests/test_token_revocation.py` (`--co`) | **8** | collected |
| `tests/test_user_token_revocation_marker.py` (`--co`) | **10** | collected |
| `tests/test_revocation_store_outage.py` (`--co`) | **4** | collected |
| Full suite (`-p no:randomly`) | **1410** | **9 failed, 1401 passed** |

**Pre-existing failures — count unchanged:** the 9 are exactly
`tests/test_auth.py::TestRateLimiting` (5) · `tests/test_layouts.py` (3) ·
`tests/test_pydantic_models.py::TestUserModels::test_user_db_valid` (1). **Confirmed; not increased.**

---

## 9. What the `-` must be handed to

- **Defect (a)/(b)/(c):** no owner needed — **disproven**; the described mechanism is absent. The plan's
  finding was written against a different (cache-backed) design. This drift belongs to the **phase that
  owns the plan** (phase 07 planner), not to production code.
- **Store contract inversion:** phase 04 `AB-1` (already landed `478015b`). `HO-2` corrected.
- **`VAL-07-005` contradiction:** phase 04 (owns the store contract). Recorded, not resolved.
- **Dead selectors/classes named in the task brief (`test_cross_worker_revocation_*`,
  `test_publish_*`, `TestRevocationMarkerTtlValidation`):** a plan-correctness defect — the plan's
  verification rows and the task brief cite tests that do not exist. Recorded here.
</content>
</invoke>
