# Phase 04 — Authentication Reconciliation and Phase Baseline

**Audit phase:** 04-authentication
**Execution plan:** `.ai/plans/04-authentication-remediation-execution.md`
**Validated findings report:** `.ai/audit/99-validation/04-authentication-validated-findings.md`
**Plan `source_head`:** `cea2d06`
**Re-verified at HEAD:** `29683df`
**Status:** record only

This note records what was verified at HEAD. It **supersedes nothing**. Every claim below was
re-derived against the tree at `29683df`, not carried from the report or the plan's original
`source_head`. The report's findings stand at their bands and no identifier is renumbered.

**No audit-phase file is edited by this phase.** This note is a record, not authority to modify
`.ai/audit/**`. In particular, `.ai/audit/99-validation/04-authentication-validated-findings.md`
and every other audit-phase artefact are left byte-identical.

---

## 1. Dead and stale anchors in the validated findings report

These anchors were recorded, never renumbered, and no audit file was edited. Where the plan's
zone table (`Z-01` … `Z-14`) already ruled a realignment, that ruling is repeated here as the
verified-at-HEAD result.

- **`AUTH-002` anchors do not exist.** The report anchors `AUTH-002` on `src/mkobi/api/routes/admin.py`
  (4 sites) and `src/mkobi/services/user_service.py` (1 site). None of those bodies is there. The
  bodies live in `src/mkobi/services/auth_service.py::AuthService.reset_password_admin` and
  `::AuthService.approve_registration_request`.

- **`api/routes/admin.py:43` `AdminUser` import anchor is wrong.** `AdminUser` is not an import
  site. It is a dependency alias defined in `src/mkobi/api/deps.py`.

- **`src/mkobi/core/permissions.py:354` anchor is past EOF.** The module is **353 lines** long, so
  the cited line does not exist. The claim attached to it is half right and half wrong at HEAD:
  `core/permissions.py::get_current_user` **does exist**, but it and
  `_get_current_user_with_session` have **zero src-level callers** — the only importers are in
  `tests/test_permissions.py`. The finding is real; the anchor is dead.

- **Retrieval-endpoint symbol is `api/routes/admin.py::retrieve_temp_password_admin_endpoint`.**
  The report's and code context's alternate names do not resolve.

- **The "not found" test is
  `tests/api/test_temp_password_retrieval.py::TestTempPasswordRetrievalEndpoint::test_retrieve_temp_password_nonexistent_token`.**
  The report's `test_retrieve_temp_password_not_found` does not exist.

- **`AUTH-006`'s three-state `retrieve` return is two collapsed states at HEAD.**
  `TempPasswordStore.retrieve` returns `str | None`: absent-or-already-spent (`None`) and
  store-fault (`None`) are the same value. The store has **no expiry concept of its own**, so a
  third "expired" state does not exist to distinguish.

- **`api/routes/auth.py::confirm_registration_endpoint` does not exist anywhere in the repository.**
  No such symbol is defined or referenced.

## 2. Identity divergences between the report and the phase-1 code context

Where the two disagree about *identity* (which finding is which), **the report's identifier set
wins**. The code context's numbering is recorded as a defect and is not edited. The findings are
recorded without renumbering:

- **`AUTH-005` is the transport/logging finding** — the retrieval handle is a URL path segment
  written verbatim into the access log. The code context had re-pointed `AUTH-005` at the
  client-IP rate-limit subject. That subject is **`AUTH-001`'s cause half**, never a separate
  finding.

- **`AUTH-004` is password rotation withdraws no session and the refresh cookie is never
  rotated.** The code context added two substantiated sub-claims, which are honoured as a
  **content union** rather than a replacement:
  - `is_active` is untested on the token-issuing paths — this is this phase's work item 2.
  - The admin endpoint's commit-then-revoke split is deliberate and landed.

## 3. Miscounts in the report

Recorded without renumbering. Each was re-derived independently at HEAD.

- **`VAL-04-004` claims `revoke_all_user_tokens` has "only one caller" — verified correct.** At
  HEAD it has **exactly one** src-level caller:
  `api/routes/admin.py::update_user_active_admin_endpoint`, in the deactivation branch.
  `revoke_refresh_token` and `revoke_token` likewise have exactly one caller each
  (`api/routes/auth.py::logout`). **The report's count was correct**; the finding's substance is
  unaffected.

- **`VAL-04-002`'s stated mechanism is wrong; its conclusion stands.** There is no `StrictRedis`
  class and no `testclient` peer string in the tree. The `127.0.0.1` in
  `tests/test_rate_limiting.py::test_rate_limit_reset_allow_writes` comes from httpx's
  `ASGITransport` default client. The conclusion — that the hard-coded key literal
  (`rate_limit_key = "login:127.0.0.1"`) is a remediation blocker for the rate-limit work —
  **stands**.

## 4. Struck, not handed to another phase

- **`Y-02` / `C04-6` recorded `update_user_active_admin_endpoint`'s `await db.rollback()` docstring
  as "factually wrong". Verified accurate.** The endpoint has a separately guarded revoke block
  that raises `AppException`, and an `except AppException: raise` arm precedes the
  `except Exception` arm, so the `AppException` never reaches the rollback. **The clause is
  correct and is not a defect. No hand-over is raised.**

## 5. Also recorded

- **`D-04-H` is answered by the tree.** Plan-03 `B1` has landed; the worktree is clean of tracked
  source changes owned by this programme's phases. (`git status --porcelain` shows only deletions
  of untracked-by-design `.ai/**` and coverage artefacts and untracked plan/task files belonging
  to sibling phases, none of them this phase's tracked source.)
- **No audit-phase file is edited by this phase.** This note is a record only.

---

## Phase baseline at `29683df`

| Field | Value |
| ----- | ----- |
| HEAD | `29683df` — *"docs(architecture): reconcile the unconstrained pool figure and the engine grounds"* |
| Plan `source_head` | `cea2d06` (re-verified at HEAD `29683df`) |
| `D-04-H` | Answered: plan-03 `B1` landed; worktree clean of tracked source |
| Audit-phase files edited | **None** |
| Findings renumbered | **None** |
| This phase's files | `.ai/audit/00-reconciliation/04-authentication-reconciliation.md` (new, this note); one `docs/SPEC.md` Version History row |
