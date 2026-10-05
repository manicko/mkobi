---
phase: 03-db-concurrency
executed: 2026-10-05
executor: validator
problems-only: true
findings: 12
by-severity:
  CRITICAL: 1
  HIGH: 1
  MEDIUM: 3
  LOW: 7
---

# Phase 03 — Validated Findings

## Summary

All 12 findings in `.ai/audit/03-db-concurrency/findings.md` were re-derived from the executing path at HEAD
`eba2348`, and **every cited anchor resolves and says what the report claims**. That is the single most important
departure from the phase-01 pass, where 9 of 14 anchors were stale: here, **0 of 12 findings had a stale line
anchor**, and every quoted code block is a verbatim excerpt of the lines it cites. The auditor's citation discipline
on this phase was materially better than on phase 01.

**Both runtime claims reproduce independently.** I re-derived `TXN-102` and `TXN-103` with my own probe against the
live development PostgreSQL (not the auditor's), and additionally reproduced `TXN-101`'s partial commit at the
database level — the one claim the auditor had left at static proof. Every probe row was deleted afterwards;
`processing_configs` is at its pre-probe count of 1 row and `dashboards` at 5.

**No finding was rejected.** **Three required correction** — in each case a supportable claim resting on a
false or overstated premise rather than on a wrong anchor — and **one severity was re-graded** (`TXN-107`,
MEDIUM → LOW).

The audited report's own `by-severity` block (findings.md:8-13) — CRITICAL 1 · HIGH 1 · MEDIUM 4 · LOW 6 — matches
its twelve per-finding severities exactly; there is no internal inconsistency to correct. The validated
distribution is **CRITICAL 1 · HIGH 1 · MEDIUM 3 · LOW 7**: the single difference is `TXN-107`, downgraded. Net
effect of validation: one severity downgraded, none upgraded.

The two load-bearing findings both hold. **`TXN-101` (CRITICAL)** is the highest-value result of this pass: the
transaction split is real, it survives into the database, and the consequence is worse than the auditor stated —
the retry does not merely fail, it fails with a *different* error than the first attempt, and the account is left
in a state where the admin who approved it has no way to obtain the temporary password that never landed in Redis.
**`TXN-102` (HIGH)** reproduces exactly as filed, and its remediation blockers are real.

One disclosure fails and one is overstated. **`.ai/plans/03-db-concurrency-remediation.md` does not exist** —
confirmed, and the report is right to say so — but the report's phrasing "its blocks cannot be verified against the
plan" overstates the consequence: the B1–B5/B9 task files carry full inline change records, so the executed work is
independently verifiable. The two "already tracked" analyses built on that missing plan (`TXN-104`, `TXN-106`) still
hold, on independent grounds.

## Findings

### TXN-101 — `AuthService.approve_registration_request` splits one three-row domain write across two transactions

**Severity** — CRITICAL (re-derived; unchanged from filed)

**Zone** — Unit-of-work boundaries: one request performing several writes that must all succeed

**Verdict** — CONFIRMED, with one correction to the stated consequence

**Observation** — The approval path writes a `users` row, a `force_password_change` flag, and a
`registration_requests.status` transition. The first becomes durable inside a nested call, at
`src/mkobi/services/auth_service.py:163`; the other two only become durable at `src/mkobi/services/auth_service.py:689`.
The docstring at `src/mkobi/services/auth_service.py:639-641` and `docs/04-admin/admin-api.md:735-739` both
describe the sequence as one transaction.

**Evidence** — All anchors resolve:

- `src/mkobi/services/auth_service.py:385` — `AuthService.create_user` delegates directly:
  `return await self.register_user(email, password, db, role)`, so `:163` sits inside the approval's own call chain
- `src/mkobi/services/auth_service.py:163` — `await db.commit()` in `register_user`'s `try`, before `return`
- `src/mkobi/services/auth_service.py:672-689` — the sequence, verbatim: `:672` `temp_password =
  self._generate_temp_password()`, `:674-676` `create_user(...)`, `:679` `force_password_change=True`,
  `:686-688` `update_status(...)`, `:689` `await db.commit()`, `:692` `await self.temp_password_store.store(...)`
- `src/mkobi/api/deps.py:126-129` — the session "does not commit and does not roll back: closing the session is not
  a transaction boundary"
- `src/mkobi/api/routes/admin.py:442-447` — `except Exception` → `AppException(code=INTERNAL_ERROR)`, HTTP 500
- `docs/04-admin/admin-api.md:735-739` — the diagram claims `create user ┐ … COMMIT` as a single boundary
- `src/mkobi/services/auth_service.py:639-641` — "Owns the whole transaction: create the user, set the
  force_password_change flag, mark the request approved, commit, and only then hand the temporary password to the store"

**The transaction boundary is where the report says it is, and I reproduced the resulting orphan state against the
live database.** Inducing a failure at `update_status` (the step between the two commits), then closing the session
exactly as `get_db_dependency` does, left this behind:

```
induced failure: injected mid-sequence failure
ORPHAN users row exists: True
  force_password_change: False
  password_hash set: True
  role: viewer
registration_requests.status: pending
store.store call count: 0
```

The flag never landed, the status never landed, and the temporary password never reached Redis — so no
administrator or user can ever obtain it. The account exists, is active, is not flagged for password change, and
has a bcrypt hash of a string nobody knows.

**Correction to the stated consequence.** The report says "every retry then fails with a 500". True, but the retry
fails *differently*, which the report does not say and which is worse than a uniform 500: the first attempt raises
whatever fault occurred mid-sequence, while the retry stops at the pre-check in
`src/mkobi/services/auth_service.py:113-118` (`_check_email_uniqueness` → `ValueError`) and never reaches the write.
`register_request` refuses the same address too (`src/mkobi/services/auth_service.py:419-433` and `:444-447`, both
`ValueError`). Reproduced:

```
RETRY raised: ValueError : User with email 'val03t101-faa3ceb8@example.com' already exists
register_request raised: ValueError : Unable to process registration request
```

So the address is unusable by all three writes — approval, retry, and fresh registration — and none of the three
paths reports which one is wedged or why. Corrected consequence: **the state is terminal and self-blocking across
every write path to that address, not merely retry-hostile.**

**Consequence** — An admin approves a registration; a fault between the nested commit at `:163` and the outer commit
at `:689` yields a live account whose password is unrecoverable and whose registration request is still `pending`.
The admin sees a 500 and re-runs; the re-run 500s again with a different, unrelated error. Only a direct database
edit can resolve it. The route's own comment at `src/mkobi/api/routes/admin.py:424` — "The service owns the create →
flag → status → commit → Redis write sequence" — describes the intent the code does not honour, and
`docs/04-admin/admin-api.md:735-739` documents it as atomic.

**Remediation blockers** — Both verified, and both stronger than stated. `tests/test_auth_service.py:672-717`
(`test_approve_registration_request_failed_commit_leaves_no_credential`) and
`tests/test_auth_service.py:1099-1161` (`test_failed_commit_returns_rfc7807_and_no_credential`) do not merely assert
`store.store.assert_not_called()`; they **count commits and fail on the second one**
(`if call_state["n"] >= 2: raise RuntimeError("commit failed")` at `:702-703` and `:1140-1141`), with comments at
`:696-697` and `:1133-1134` that explicitly document the two-commit shape as *intended* ("register_user performs
the first commit; the final commit (flag + status) is the one forced to fail here"). Widening the boundary changes
the nth-commit semantics these tests encode. Separately, `.ai/tasks/B1-txn-001-transaction-ownership.yaml:609`
rules "Do not touch AuthService — not create_user, not approve_registration_request, not register_user", so no
accepted task file currently authorises the edit — this needs an explicit ownership ruling, not a plan
amendment.

---

### TXN-102 — `ProcessingConfigService.upsert` and `.delete` never commit, so both processing-config endpoints acknowledge writes they discard

**Severity** — HIGH (re-derived; unchanged from filed)

**Zone** — Unit-of-work boundaries: who ends the unit of work on the processing-config write path

**Verdict** — CONFIRMED

**Observation** — The PUT and DELETE routes return success and a body, and nothing is written. `get_db_dependency`
is commit-free by contract, and the service never commits either.

**Evidence** — All anchors resolve, and the reproduction is independent of the auditor's:

- `src/mkobi/services/processing_config_service.py:172-199` — `upsert`'s full body, verbatim; ends `return cast(
  ProcessingConfigRead, ProcessingConfigRead.model_validate({...}))` with no `commit`
- `src/mkobi/services/processing_config_service.py:241-271` — the three interface aliases
  (`create_processing_config`, `update_processing_config`, `delete_processing_config`), each delegating to `upsert`
  or `delete`; none adds a commit
- `src/mkobi/services/processing_config_service.py:241-271` and `:66-154` — a whole-file scan for
  `commit|rollback|flush` over `processing_config_service.py`, `api/routes/processing_configs.py` and
  `db/repositories/processing_config_repo.py` returns **8 hits, all `flush` or `rollback`, zero `commit`**
- `src/mkobi/api/routes/processing_configs.py:182-188` (PUT → `return config`) and `:238-240`
  (DELETE → `return True`); both route handlers contain no `commit`
- `src/mkobi/api/deps.py:126-129` — the commit-free contract, quoted in TXN-101 above
- `src/mkobi/services/user_service.py:345` — `await db.commit()` in `delete_user`, the model the report points to
- `tests/test_services_integration.py:611-619` — `test_create_config_with_db` asserts only
  `result is not None` and `result.dashboard_id == dashboard_id`, so a discarded write passes

**Independent reproduction** (my own probe, real service, real repository, real `get_session`, against the live
development database):

```
UPSERT returned type: ProcessingConfigRead
UPSERT returned dashboard_id: f0f4e2ac-...   updated_at: 2026-10-05T...   metric_agg: sum   settings.encoding: utf-8
UPSERT row visible inside the WRITING session: True
UPSERT row found from a FRESH session: False        ← the write did not persist
DELETE fixture committed; durable count: 1
DELETE returned: True
DELETE row visible inside the DELETING session: False
DELETE row found from a FRESH session: True         ← the delete did not persist
```

Both halves reproduce exactly as filed: a populated response body over a discarded write, and `True` over a delete
that did not happen. Independent corroboration from the server's own view: `pg_stat_activity` shows the `mkobi-app`
pool connections resting in `state = idle` with `query = ROLLBACK`, which is what session close does to an
uncommitted write.

**Consequence** — A PUT returns `200` with a plausible body while writing nothing; the GET that follows returns the
old value or `None`. A DELETE returns `True`/`204` while the row survives. No log line distinguishes either case,
because no error occurred. The report's statement that the SPA never calls these endpoints is confirmed — a
repository-wide search of `frontend/src` for `processing-config` returns **zero hits** — which bounds the exposure
to direct API consumers today and does not reduce it, since the endpoints are live, admin-scoped and documented.

**Remediation blockers** — Verified. The report's recommendation is the right shape (add a commit to `upsert` and
`delete`, matching `UserService.delete_user`), and it correctly warns that `create_processing_config`,
`update_processing_config` and `delete_processing_config` are three more names to carry the same change.
`tests/test_services_integration.py:611-619` will not detect a regression and should be strengthened to the
independent-session re-read the report prescribes.

---

### TXN-103 — A duplicate dashboard name surfaces as 500 `INTERNAL_ERROR`, not 409 `DUPLICATE_RESOURCE`

**Severity** — MEDIUM (re-derived; unchanged from filed)

**Zone** — Invariants enforced only at flush time, and where they are classified

**Verdict** — CONFIRMED

**Observation** — `dashboards.name` carries a unique index. The repository flushes and the driver's
`IntegrityError` escapes the service untouched; the route has no arm for it and the blanket handler answers 500.

**Evidence** — All anchors resolve, and my reproduction goes further than the auditor's by driving the **route
handler itself**, not only the service:

- `src/mkobi/db/repositories/dashboard_repo.py:134` — `await db.flush()`; the constraint is raised here
- `src/mkobi/services/dashboard_service.py:109-121` — `config_obj = DashboardConfig(**config)`,
  `self._validate_config(config_obj, db)`, then `try:` / `dashboard_obj = await self.dashboard_repo.create(
  db=db, name=name, ...)`. There is no `except`; `create_dashboard` is decorated `@staticmethod`, so there is no
  instance to bind and no `self.regenerate_dashboard_graphs` in the path at all
- `src/mkobi/api/routes/dashboards_crud.py:158-173` — `except ValueError` → `VALIDATION_ERROR`, then
  `except Exception` → `INTERNAL_ERROR`/`500`/`"Error creating dashboard"`. **No `IntegrityError` arm**, verified
  against the full route body
- `src/mkobi/api/routes/graphs.py:135-147` and `src/mkobi/api/routes/dashboards_graphs.py:116-127` — the correct
  pattern in the sibling modules, for contrast
- `docs/06-backend/architecture.md:180-182` — the declared rule: repositories flush, "the driver's `IntegrityError`
  is raised at flush time and is classified in the service, which is the layer that knows what the error *means*"
- `src/mkobi/services/layout_service.py:140-142` — the in-tree ruling, verbatim: "No name pre-check: the unique
  index on `layouts.name` detects a rename onto an existing name at flush time via `IntegrityError`, which keeps
  the check atomic and closes the TOCTOU window a read would open"

**Independent reproduction**, driving `create_dashboard_endpoint` directly:

```
SERVICE duplicate raised IntegrityError: asyncpg.exceptions.UniqueViolationError: duplicate key value
ROUTE raised: AppException   code: INTERNAL_ERROR   http status: 500   detail: Error creating dashboard
INDEX: idx_dashboards_name => CREATE UNIQUE INDEX idx_dashboards_name ON public.dashboards USING btree (name)
```

This is **stronger** evidence than the auditor filed, which reached only `IntegrityError` at the service. The route's
own exception chain, executed, produces the 500. `isinstance(exc, ValueError)` is `False`, so the first arm cannot
catch it.

**One correction to the report's consequence.** The report claims "the transaction is left aborted and the
next statement on this session would raise `PendingRollbackError`", citing `graphs.py:136-137`'s comment. That
comment is about a route that *does* rollback, and it does not describe this one. My probe tested it directly:
after the route's handler swallowed the `IntegrityError`, a follow-up `SELECT` on the same session **succeeded** and
returned the row. So the "aborted transaction" amplification is **not** demonstrated for this route; the 500 is the
whole of the damage. The report is right to say the write is correctly refused and nothing is corrupted — that is
now measured, not assumed.

**Consequence** — `POST /api/v1/dashboards/` answers a user error with a 500 and a server-side `logger.error`. The
client cannot distinguish "name taken" from "server broken", and the log records an operator-visible defect for
input the API is supposed to validate. Both sibling write modules already answer `409 DUPLICATE_RESOURCE`, so the
contract is inconsistent across the same phase. `tests/test_dashboards_api.py::TestCreateDashboard` covers only the
201 and the 403 paths; no test asserts anything for the duplicate case.

---

### TXN-104 — The last-admin guard is read-then-act with no lock, so two concurrent admin deletions can leave zero admins

**Severity** — MEDIUM (re-derived; unchanged from filed)

**Zone** — Read-modify-write on shared state: the count-then-delete guard

**Verdict** — CONFIRMED — **and the disclosure is accurate: this is not re-filed `B1` work**

**Observation** — The guard counts admins, then deletes, in one request with nothing serialising the two.

**Evidence** — All anchors resolve:

- `src/mkobi/services/user_service.py:88-99` — `all_users = await self.user_repo.get_all(db)`,
  `admin_count = sum(...)`, `if admin_count <= 1: raise ValueError("Cannot delete the last admin user. Assign
  another admin first.")`, `deleted = await user_repo.delete(user_id, db)`
- `src/mkobi/services/user_service.py:337-345` — `delete_user` calls the guard, then `await db.commit()` at `:345`
- `src/mkobi/db/repositories/user_repo.py:137-144` — the count query: `select(user_model.User)` with `.offset/.limit`,
  no lock clause
- A repository-wide search for `with_for_update` across `src/` returns **zero hits**, so no row-level lock exists
  anywhere in the tree — the report's "no exclusion protects this window" claim is fully confirmed

**Disclosure checked as instructed.** `.ai/tasks/B1-txn-001-transaction-ownership.yaml:516-518` reads, verbatim:
"The last-admin guard (_check_admin_deletion_allowed) — no change. It counts committed admin rows and has been
over-eager because promotions never persisted; after this task it becomes correctly permissive. That direction is
expected, not a bug to fix here." The exclusion is on **over-eagerness grounds** (a count that reads too high),
not on concurrency. This finding is about a count that reads too *low* under concurrency — the opposite failure, on
independent grounds. **The finding is genuinely new work, not re-filed tracked work.** Recording this explicitly
because the audit's own disclosure could not have been checked against the plan it cites.

**Consequence** — Two concurrent `DELETE /api/v1/admin/users/{id}` calls against two different admin ids both read
`admin_count = 2`, both pass, both commit. The deployment is left with zero administrators: `/api/v1/admin/users/`,
role changes and registration approval all become unreachable, and there is no self-service recovery — the guard's
own message, "Assign another admin first", is what an operator must now do against the database directly. The
trigger is a privileged, deliberate action rather than load, which is why this is MEDIUM and not HIGH: it needs an
admin to issue two deletions concurrently, and the outcome is an operator-visible lockout rather than silent
corruption.

---

### TXN-105 — `recreate_test_database` releases its exclusion before the migration it is excluding

**Severity** — MEDIUM (re-derived; unchanged from filed)

**Zone** — Exclusion lifetime: a lock that ends before the work it was taken for

**Verdict** — CONFIRMED

**Observation** — The recreate lock is released in a `finally` at `:394-395`; the migration runs at `:438`, forty
lines later and after several more await points.

**Evidence** — All anchors resolve:

- `src/mkobi/db/starter.py:370` — `await acquire_test_database_recreate_lock(conn, str(db_name))`
- `src/mkobi/db/starter.py:394-395` — `finally:` / `await release_test_database_recreate_lock(conn, str(db_name))`
- `src/mkobi/db/starter.py:437-438` — `# Apply migrations to test database` / `await self._apply_migrations(test_url)`,
  outside the guarded block
- `src/mkobi/db/migration_lock.py:38` — `MIGRATION_ADVISORY_LOCK_KEY = 42`
- `alembic/env.py:135-170` — the migration's own exclusion is `pg_try_advisory_lock(42)`, bounded at 30 attempts ×
  10 s, released in a `finally` — a **different lock key** from the recreate lock, which is derived per database name
  via `test_db_recreate_lock_key` (`src/mkobi/db/test_database_lock.py:118`, a blake2b digest of
  `namespace:db_name`). Neither key excludes the other's work
- `docs/99-reference/run-guide.md:291` — `uv run python -m mkobi.db.starter --recreate-test-db`
- `src/mkobi/db/starter.py:300-305` — the operation admits only under `configured_env == TEST`, bounding it to the
  test tier as claimed
- `tests/conftest.py:80` — `os.environ.setdefault("RECREATE_TEST_DB", "true")`, and `:82-83` set both
  `DATABASE__DBNAME` and `DATABASE__TEST_DBNAME` to the per-run name — so a real invocation path exists

**Severity held at MEDIUM, and the report's own bounding is what holds it there.** The consequence is test-tier
infrastructure damage under a deliberate, documented, developer-invoked command — not production data loss. The
report does not inflate this, and I did not find a path to production: `starter.py:300-305` refuses outright unless
the configured environment is `TEST`, and `_apply_migrations` for the application tier is gated behind
`auto_migrate` (`src/mkobi/db/starter.py:245`), which every compose file sets `"false"`
(`docker/docker-compose.yml:289`, `docker/docker-compose.override.yml:165` and `:245`, and
`src/mkobi/settings/app.yaml:19`).

**Consequence** — Two concurrent recreations of the same database name serialise correctly on the drop/create, then
the loser releases and the winner migrates unprotected; the loser's migration can then be terminated by the
winner's `pg_terminate_backend` sweep. Since `tests/conftest.py:49` derives a **fresh** name per run
(`uuid4().hex[:8]`) unless `MKOBI_TEST_RUN_ID` is set, this fires only when two runs are deliberately pointed at one
name — which is exactly the `MKOBI_TEST_RUN_ID` case the run guide documents, and the case the two host-run limits
in `.kilo/rules/commands.md` describe.

---

### TXN-106 — The retention path has two implementations and the wired one cannot be reached or retested

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Two changes of direction in the same period, and the tests that pin the one that shipped

**Verdict** — CONFIRMED

**Observation** — `cleanup_old_logs` runs a raw `DELETE` at boot on every start; the newer service method that
computes a resolved horizon is unreachable and untested.

**Evidence** — All anchors resolve, and the dead-code census is exact:

- `src/mkobi/db/starter.py:597-613` — the wired path: `await self.cleanup_old_logs()`, a single AUTOCOMMIT
  `text()` `DELETE FROM processing_logs WHERE finished_at < NOW() - INTERVAL '{days} days' AND status IN (...)`
  with `days` interpolated, then `if result.rowcount > 0: logger.info("Cleaned up %d old processing logs", ...)`
- `src/mkobi/db/starter.py:268` — called unconditionally from startup
- `src/mkobi/services/processing_log_service.py:254-258` — `# Production mode - create new session` /
  `count = await self.log_repo.delete_old_logs(cutoff=cutoff, db=db)` / `return count`
- `src/mkobi/db/repositories/processing_log_repo.py:349-364` — the newer predicate, `status.in_([COMPLETED, FAILED])`
  and `finished_at < cutoff`, returning `int`
- A search for `delete_old_logs` across `src/`, `tests/` and `alembic/` returns **exactly 5 hits**: the repository
  definition (`:335`), the interface declaration (`src/mkobi/interfaces/repository_interfaces.py:484`), the service
  definition (`:226`) and its two internal calls (`:251`, `:257`). **`tests/` returns zero.** No call site exists
- `src/mkobi/config.py:77` — `LOGS_RETENTION_DAYS_DEFAULT = 90`; `:732-733` the `logs_retention_days` field
- `docs/06-backend/architecture.md:419-425` — the startup cold-start rationale the f-string interpolation
  undermines
- `docker/Dockerfile:242` — `--workers 4`, establishing the multi-process boot shape

**Correction to the report's premise, and it is a premise the finding gets right.** The report's key observation —
that the *newer* path correctly refuses to interpolate and the *wired* one does — is confirmed. It is worth stating
plainly that this is not merely duplication: the dead path is the only one whose predicate matches a real retention
policy, while the wired one silently keeps nothing the moment `finished_at` is null. At `docker/Dockerfile:242`'s
four workers this is a per-boot truncation event, not a per-install one.

**Consequence** — Rows in a terminal state whose `finished_at` is null are never deleted by the shipped path. No test
exists for either implementation. The remediation is a routine deletion plus a de-duplication of the predicate, and
it closes a real-but-small data-retention gap. LOW is correct: no runtime consequence is observable today beyond
retention drift.

---

### TXN-107 — `task_queue.py` builds the RQ client from the undeclared redis-py 8.0.0 transport defaults that `redis_client.py` deliberately removed

**Severity** — **LOW** (re-derived; **downgraded** from MEDIUM)

**Zone** — Exclusion mechanisms as one system: lifetime, holder, and what is not covered

**Verdict** — CONFIRMED as a fact, **re-graded MEDIUM → LOW**

**Observation** — The health and rate-limit clients declare `socket_timeout` and a pinned retry; the RQ client does
not, so it inherits library defaults.

**Evidence** — All anchors resolve, and I verified the library figures against the installed package rather than
relying on the report's quotation:

- `src/mkobi/core/task_queue.py:41-49` — `config = get_config()`, then
  `redis.Redis(host=config.redis.host, port=config.redis.port, db=config.redis.db,
  password=config.redis.password, decode_responses=True)`
- `src/mkobi/core/task_queue.py:72` — `job = await asyncio.to_thread(queue.enqueue, func, *args, **kwargs)`
- `src/mkobi/core/redis_client.py:13-19` — "A code invariant, not a setting: the transport never retries a failed
  command", and `_NO_RETRY = Retry(NoBackoff(), 0)`
- `src/mkobi/core/redis_client.py:42-51` — both factories passing the two timeouts explicitly
- Library, verified in the running container: `redis.__version__ == 8.0.0`; `redis/_defaults.py:7-8`
  `DEFAULT_SOCKET_TIMEOUT = 5` and `DEFAULT_SOCKET_CONNECT_TIMEOUT = DEFAULT_SOCKET_TIMEOUT`; `:37-39`
  `DEFAULT_RETRY_COUNT = 10`, `DEFAULT_RETRY_BASE = 0.01`, `DEFAULT_RETRY_CAP = 1`;
  `redis/client.py:248-249` and `:259-264` the `Redis.__init__` defaults
- Derived by hand from those constants: `retries = 10` → **11 attempts**, default `Retry.supported_errors` includes
  `redis.exceptions.TimeoutError` and `ConnectionError`, so socket timeouts are retried
- `uv.lock:1817-1818` — `name = "redis"` / `version = "8.0.0"` (pinned `>=6.4.0` at `pyproject.toml:47`)
- The "roughly 59 s" figure is the project's own: `docs/06-backend/configuration.md:102` and `:123`

**Disclosure checked as instructed.** `docs/SPEC.md:236` (row 3.33) ends, verbatim: "Deliberately **not** reached:
`rq_worker_wrapper.py`'s three `Redis.from_url` sites and `core/task_queue.py::get_rq_queue` (both hand-overs,
`HO-9`)." The anchor and the hand-over are both real. **Disclosure confirmed** — and note that `HO-9` being a
*deliberate, documented* deferral, with `rq_worker_wrapper.py`'s three `Redis.from_url` sites in the same row,
is the strongest reason to keep this at LOW rather than escalate.

**Severity re-graded MEDIUM → LOW.** The report's own bounding, checked and found sound, puts it below MEDIUM:

- The rate limiter's `fail_closed` default is `True` (`src/mkobi/config.py:740`, `rate_limiter_fail_closed: bool =
  Field(default=True, ...)`), and the upload route builds `AsyncRateLimiter(..., fail_closed=
  config.rate_limiter_fail_closed)` at `src/mkobi/api/routes/upload.py:178-180` **before** the enqueue — so a total
  outage is caught upstream and the ~59 s path is never entered
- `:72` is `asyncio.to_thread`, so the blocked call occupies one default-executor thread, not the event loop; the
  report says "the upload request does not answer until it gives up", which is accurate and is bounded by the
  60 s `PG_ADMISSION_CONTROL` / rate-limiter path, not unbounded
- The report cites `src/mkobi/core/task_queue.py:86-88` for `disconnect_callback` to argue a reconnect cannot help
  mid-queue. That anchor does **not** resolve — `:86-88` is the `disconnect_callback` function's own docstring and
  signature, which supports the same inference the report draws, so the conclusion stands but the anchor is
  imprecise

MEDIUM requires "degraded operability or a bounded correctness gap". This is a latent divergence on a documented
hand-over, in a path with a fail-closed upstream gate, whose worst case is a bounded delay on one request.
**LOW** — "observability and documentation drift with no runtime consequence today" is the closer fit, with the
caveat that "today" is load-bearing: the defaults become a live problem the moment `HO-9` is picked up, and this
should be closed as part of that hand-over rather than as an independent defect.

---

### TXN-108 — `health-api.md` documents a short-lived Redis client; the code pings the process-wide shared one

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Declared contract vs shipped path

**Verdict** — CONFIRMED

**Evidence** — All anchors resolve:

- `docs/05-health/health-api.md:136` — "| `redis` | Sends a `PING` on a short-lived client from
  `get_async_redis_client()` … |" — the table row
- `docs/05-health/health-api.md:142` — "Redis check: sends a `PING` on a client built fresh from
  `get_async_redis_client()`" — the components prose
- `src/mkobi/app.py:446-450` — the comment and the call: "# client is the process-wide shared one, so this check
  must NOT close it: closing it here would evict the pooled connections every later request depends on. It is closed
  once at lifespan teardown instead." / `await get_async_redis_client().ping()`

The document's two sites contradict each other and both contradict the code. Neither reading of "short-lived" is
false on its own — the function is called once per request — but "built fresh" and "short-lived" both assert
per-call construction, which is exactly what the comment says must not happen.

**Consequence** — An operator reading the components section before changing the health probe would build a fresh
client to match the documentation and reintroduce the pooled-connection eviction that `app.py:446-448` was written
to prevent. Documentation-only, no runtime consequence. The report is right that this is documentation drift and
that the correct fix is a documentation change.

---

### TXN-109 — Three documents still describe the orphan sweep as boot-only after it moved onto the periodic reconciler loop

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Two changes of direction in the same period

**Verdict** — CONFIRMED

**Observation** — The sweep runs on the periodic reconciler loop; three documents describe it as boot-only.

**Evidence** — All anchors resolve:

- `docs/06-backend/architecture.md:367` — "| `mark_orphaned_uploaded_logs_failed()` | `UPLOADED` | **Boot only** —
  once per process, at startup |"
- `docs/06-backend/architecture.md:393-396` — "**The boot-time marker is boot-only, and stays that way.** It runs
  once per process … in practice, up to a full horizon"
- `src/mkobi/workers/data_worker.py:1543-1546` — the reconciler's comment: "Reclaim orphaned UPLOADED rows on the
  same tick and under the same horizon so 'too old' cannot diverge between the two"
- `src/mkobi/workers/data_worker.py:1551-1553` — the call site, inside the periodic path
- `docs/03-processing/file-cleanup.md:117` — "| Runs | **On the periodic reconciler loop**, on every tick |" — this
  document is **correct**, which is what makes the other two wrong rather than merely differently-worded

**Consequence** — Pure documentation drift with a real operational cost: `architecture.md:393-396` tells an operator
a stranded row waits up to a full horizon plus a restart, when the sweep now runs on a clock. That is the opposite
of the deployed behaviour and the wrong direction to be wrong in — an operator relying on it under-reacts.

---

### TXN-110 — The admin bootstrap reaches for the application sessionmaker, not the engine the starter was given

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Where a unit of work should be opened, and on which pool

**Verdict** — CONFIRMED

**Observation** — One start-up call site opens its transaction on the application engine.

**Evidence** — All anchors resolve:

- `docs/06-backend/architecture.md:420-422` — "**require an AUTOCOMMIT connection**, and the starter must not share
  the application engine: putting start-up reads on the request pool would expose them to a pool timeout during cold
  start, the worst possible moment for one."
- `src/mkobi/db/starter.py:510-513` — `SessionLocal = await get_async_sessionlocal()`, then
  `async with SessionLocal() as db:` / `async with db.begin():` — the application sessionmaker, not the starter
  engine the class was constructed with

**Correction to a quoted-code discrepancy.** The report's evidence block quotes
`async with get_async_sessionlocal() as session:` / `user = await UserRepository().get_by_username(...)` /
`await _create_admin_user(...)` at `:510-513`. That text is **not** at those lines. A search for `def get_by_username`
across `src/` returns **zero hits** — the method no longer exists — and `_create_admin_user` exists only as a
fixture-local helper in `tests/test_graphs.py`. The real code at `:510-513` uses the raw-SQL
`INSERT … ON CONFLICT (email) DO NOTHING` form. **The observation is unaffected and independently verified at the
cited lines**: the call site does reach for `get_async_sessionlocal()`. The finding stands; its quoted transcript
does not, and a downstream block copying that snippet would be writing dead code.

**Consequence** — One start-up connection drawn from the request pool's budget during cold start. Narrow, bounded,
and the report is right that the correct fix is the documentation change rather than the coupling — a real engine
is already a class field.

---

### TXN-111 — `core/base_repository.py` is a 204-line generic repository with no importer

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Two changes of direction in the same period: a repository-convention change the generic base was not part of

**Verdict** — CONFIRMED

**Observation** — The file defines a full generic CRUD repository; nothing inherits from or instantiates it.

**Evidence** — All anchors resolve, and the census is exact:

- `src/mkobi/core/base_repository.py:31-39` — `def __init__(self, model: type[T], db: AsyncSession) -> None:` /
  `self.model = model` / `self.db = db`
- The file is **204 lines** and ends at `:204` with `raise` inside `exists()` (`:185-204`), the method the report
  names
- A search for `BaseRepository` across `src/`, `tests/`, `alembic/` and `docs/` returns **exactly one hit**: the
  class declaration at `src/mkobi/core/base_repository.py:20`. No import, no subclass, no instantiation, and no
  documentation mention
- For contrast, `src/mkobi/db/repositories/dashboard_repo.py:118-120` — a concrete repository's `async def create(
  self, db: AsyncSession, **kwargs: Any)` with no base class

**Consequence** — 204 lines of unexercised CRUD surface. The project's dead-code policy makes this a deletion, and
the cost is one file. Worth pairing with TXN-110's reconciliation so the two changes of direction are closed
together rather than separately.

---

### TXN-112 — `FilterService.create_filter` has no transaction owner and no production caller

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Unit-of-work ownership for a write with no route

**Verdict** — CONFIRMED, with two citation corrections and one corrected premise

**Observation** — The same defect shape as TXN-102, in a module nothing routes to.

**Evidence** — The core anchors resolve:

- `src/mkobi/services/filter_service.py:68-80` — `create_filter`: the uniqueness pre-check at `:68-75`, the
  repository `create` at `:77`, the `await db.flush()` and `await db.refresh(filter_obj)` at `:78-79`, the
  `return` at `:80`. **No commit.**
- `src/mkobi/app.py:361-371` — eleven `include_router` calls; `routes.filters` is not among them, confirmed
- `src/mkobi/api/routes/__init__.py` — `filters` is not exported; `dashboards_filters` and `filter_values` are

**Correction 1 — a citation that does not resolve.** The report states "No `await db.commit()` appears anywhere in
`src/mkobi/services/filter_service.py`". It does: `update_filter` commits at `:222` and `delete_filter` at `:246`,
with rollbacks at `:226` and `:256`. The narrow claim — that `create_filter` does not commit — is correct; the
blanket claim is false.

**Correction 2 — a test file that does not exist.** The report says "the only callers are `tests/test_filters.py`".
`tests/test_filters.py` **does not exist**. The real callers are `tests/test_services_integration.py:411-446`
(`TestFilterServiceIntegration`, which asserts only the returned object's fields) and
`tests/test_deps.py:456-461` (`test_get_filter_service_returns_filter_service`, an isinstance check). The
remediation-blocker observation is still correct in substance — no test asserts durability — but a block quoting a
non-existent path would fail.

**Correction 3 — the premise behind the recommendation's second option is false.** The report offers "the module has
no production caller, so delete it" as an alternative. `src/mkobi/api/routes/filters.py` exists and is a six-line
module whose entire content is the docstring "Placeholder module for filters routes - CRUD endpoints removed. …
Filter-binding functionality for dashboards remains in `dashboards_filters.py`". The endpoints were already
**deliberately removed**; this is a recorded decision, not dead code awaiting deletion. That leaves the third option
— `IFilterService` in `src/mkobi/interfaces/__init__.py:24` and `:45` is still exported and still used by
`api/deps.py::get_filter_service` (`:357`, `:368`) — as the only defensible one.

**Consequence** — A write method with no transaction owner on an unmounted module. No production effect today,
which is why this is LOW and not a second HIGH; the finding is real and correctly ranked below TXN-102 on exactly
the grounds the report gives, once its citations are corrected.

---

## Rejected findings

**None.** All 12 findings survived validation. One was re-graded (TXN-107, MEDIUM → LOW), three required correction
without changing their conclusions (TXN-101, TXN-103, TXN-112), and the remainder were confirmed with every anchor
intact.

## Corrections register

| Finding | Correction | Severity effect |
|---|---|---|
| TXN-101 | Consequence corrected: the retry and a fresh `register_request` both fail at the *pre-check*, making the address unusable by all three write paths — terminal, not merely retry-hostile | none (CRITICAL) |
| TXN-102 | none | none (HIGH) |
| TXN-103 | Consequence corrected: the "aborted transaction / `PendingRollbackError`" amplification is **not** demonstrated — a follow-up `SELECT` on the same session succeeded | none (MEDIUM) |
| TXN-104 | none; the `B1` non-overlap disclosure is confirmed accurate | none (MEDIUM) |
| TXN-105 | none | none (MEDIUM) |
| TXN-106 | none; report's core premise (wired path interpolates, dead path does not) confirmed | none (LOW) |
| TXN-107 | Re-graded. Report's own bounding (fail-closed rate limiter at `upload.py:178-180`; `asyncio.to_thread` at `task_queue.py:72`; documented `HO-9` deferral) puts it at LOW. The `task_queue.py:86-88` anchor is imprecise | **MEDIUM → LOW** |
| TXN-108 | none | none (LOW) |
| TXN-109 | none | none (LOW) |
| TXN-110 | Quoted transcript is stale: `get_by_username` does not exist anywhere in `src/`; the real code at `:510-513` is a raw-SQL `INSERT … ON CONFLICT DO NOTHING`. The observation is verified at the cited lines | none (LOW) |
| TXN-111 | none | none (LOW) |
| TXN-112 | Three corrections: the blanket "no `db.commit()` anywhere in the file" is false (`:222`, `:246`); `tests/test_filters.py` does not exist; `routes/filters.py` is a deliberate placeholder, not dead code | none (LOW) |

## Disclosures checked

| Disclosure | Verdict |
|---|---|
| `.ai/plans/03-db-concurrency-remediation.md` **does not exist** | **CONFIRMED.** `Test-Path` returns `False`; `.ai/plans/` holds only `_code-context/`, `00-owner-rulings-2026-10-03.md`, `16-chart-presentation-contract-remediation-execution.md`, `16-phase16-residual-execution.md` and `17-authentication-implementation-execution.md`. The file is referenced by `docs/SPEC.md:217-220` (rows 3.14–3.17), by tasks `B1`(`:13`), `B2`(`:11`,`:442`), `B3`(`:2`,`:762`,`:777`), `B4`(`:10`,`:624`), `B5`(`:11`,`:600`), `B9`(`:11`,`:260`,`:512`,`:701`) and by `.ai/plans/_code-context/04-authentication-code-context.md:20` — the exact set the report names |
| …therefore "its blocks cannot be verified against the plan" | **Overstated.** The B1–B5/B9 task files carry full inline change records, `verification_steps` and `does_not_change` lists. The executed work is independently verifiable; only the plan narrative is missing |
| `TXN-104` is adjacent to `B1`'s `out_of_scope` at `:516-518`, which excluded the guard on **different grounds** | **CONFIRMED — genuinely new work.** The `B1` exclusion is about the guard being *over-eager* (counting too high). This finding is about it reading too *low* under concurrency. Opposite failure, independent ground |
| `TXN-107` is already recorded as hand-over `HO-9` in `docs/SPEC.md` section 3.33 | **CONFIRMED.** `docs/SPEC.md:236` ends: "Deliberately **not** reached: `rq_worker_wrapper.py`'s three `Redis.from_url` sites and `core/task_queue.py::get_rq_queue` (both hand-overs, `HO-9`)" |
| `TXN-102` / `TXN-112` appear in no `.ai/tasks/` file | **CONFIRMED.** A search for `TXN-102` and `TXN-112` across `.ai/tasks/` returns zero hits |
| `TXN-001`…`TXN-012` occupy the low range; `TXN-1xx` is correct | **CONFIRMED.** `docs/SPEC.md:220` names `TXN-001 … TXN-003, TXN-006 … TXN-008, TXN-012`; six task files carry `txn-001`/`003`/`005`/`006`/`007`/`010`. A repository-wide search for `TXN-1[0-9][0-9]` outside this report returns zero hits, so the `TXN-101`…`TXN-112` range is unoccupied |

## Duplicate and overlap analysis

- **One overlap, both retained:** `TXN-102` and `TXN-112` are the same defect shape (a service write with no
  transaction owner) in two modules. The report discloses this. They are **not** merged, and should not be: `TXN-102`
  is HIGH because both endpoints are live and admin-scoped, `TXN-112` is LOW because nothing routes to it. Merging
  them would lose the ranking difference that makes the LOW band honest.
- **No finding duplicates an accepted remediation.** `TXN-101` is blocked by `.ai/tasks/B1-…:609` ("Do not touch
  AuthService") rather than already remediated — the block is a scope rule, not a fix.
- **One near-miss caught:** `TXN-103` is adjacent to `B5`'s graph-name-conflict work and to
  `src/mkobi/api/routes/graphs.py:135-147`, but no accepted task covers the **dashboard** create route. No overlap.
- **Adjacent, not duplicate:** `TXN-110` (admin bootstrap pool) and `TXN-111` (`base_repository.py`) are two
  changes of direction from the same period. Both retained as the report argues — they are separate deletions plus
  one documentation line.

## Rollout and execution validation

- **`TXN-102` (the first HIGH, and the natural first block).** `upsert` is the sole implementation behind three
  interface names, so the commit lands once and the three aliases inherit it — the report is right to enumerate
  them. Two verifications are required before closing: `tests/test_services_integration.py:611-619` must be
  strengthened to an independent-session re-read (it currently cannot fail), and the PUT route's `200` must be
  re-asserted against a **fresh** session rather than a response body. Independent and safe: no shared lock, no
  schema change, no migration.
- **`TXN-103` before `TXN-102` is fine, but not after a blind `upsert` edit** — different files, no ordering
  dependency. The `graphs.py` arm is the in-tree template; `src/mkobi/services/layout_service.py:140-142` is the
  ruling that a name pre-check must *not* be added, so the block must add an `IntegrityError` arm and must not add
  a `get_by_name` check. That constraint is already in the report and must survive into execution.
- **`TXN-101` (CRITICAL) is the sequencing risk and needs an ownership ruling before any code block.** Three
  independent gates, all verified here:
  1. `.ai/tasks/B1-txn-001-transaction-ownership.yaml:609` forbids touching `AuthService` outright.
  2. `tests/test_auth_service.py:672-717` and `:1099-1161` encode the **two-commit** shape as intended behaviour,
     with comments at `:696-697` and `:1133-1134` saying so. Widening the boundary changes nth-commit semantics and
     these tests will fail for the right reason — they must be updated deliberately, not patched.
  3. `.kilo/rules/commands.md` caps parallel subagents at 2 and implementors at 1; a CRITICAL auth block plus a
     concurrent HIGH block is exactly the shape that overruns that.
  The report's own caution holds: `auth_service.py:163` must not be moved alone, because
  `AuthService.create_user` (`:385`) is also the body behind `POST /auth/register` (`auth.py:343`) and
  `UserService.create_user` (`user_service.py:215`) — both of which must keep committing for themselves.
- **`TXN-105` and `TXN-106` are test-tier and startup-tier.** Both are safe to run in parallel with the above; they
  touch `db/starter.py` and `services/processing_log_service.py`, disjoint from `auth_service.py` and
  `processing_config_service.py`. `TXN-105`'s remedy (hold the recreate lock across `_apply_migrations`) does not
  interact with `tests/test_starter.py:697-704`, which asserts the AUTOCOMMIT grant engine is the **second** engine
  created — the migration does not create an engine, so that assertion holds under the change.
- **Rollback** is clean for every confirmed finding: no schema change, no migration, no public contract change
  except `TXN-103`'s status code (500 → 409), which is a tightening of an already-declared `admin_responses` entry
  and matches `graphs.py`/`layouts.py`. `TXN-101`'s remediation changes no published contract either, but it does
  change which account state an interrupted approval leaves behind — the direction of change is strictly better
  (nothing committed rather than a half-committed write).

## Warnings

1. **The missing plan is a live traceability break, not only a citation gap.** `docs/SPEC.md:217-220` and six task
   files reference a file that does not exist. Every "already tracked" claim that cites the plan as its authority
   is unverifiable at HEAD; the two such claims in this report (`TXN-104`, `TXN-106`) happen to hold on other
   grounds, but the pattern will produce false "already remediated" verdicts in later phases. This needs an owner
   decision: restore the plan or re-point the references.
2. **`TXN-101`'s remediation is blocked by an accepted ruling and by two tests that encode the defect as
   intended.** Any block that widens the transaction boundary will fail `tests/test_auth_service.py:672-717` and
   `:1099-1161`. Per the project's own rule (production code is authoritative), the tests are wrong here and must be
   updated with the change — but the update is a deliberate act, not a repair, and it needs the `B1` ownership
   ruling first. Scheduling it as "just another CRITICAL block" will stall.
3. **`TXN-107` should be closed as part of `HO-9`, not independently.** Its severity is LOW *because* it is a
   documented deferral. Lifting it to MEDIUM would misstate the project's position; the correct action is to attach
   it to the hand-over so the transport bound is fixed in one place.
4. **`TXN-112` and `TXN-111` are both deletions and both low-value individually**, but each is a live
   documentation or contract statement that will mislead the next block. Bundling them with `TXN-110` into one
   small "reconciliation" block is cheaper than three separate ones.
5. **Two findings (`TXN-110`, `TXN-112`) quote code and paths that no longer exist.** The conclusions are correct,
   but transcripts copied into execution blocks would introduce dead code. Re-derive at the moment of implementation
   rather than copying the audit's fenced blocks.
6. **Anchor precision degrades in the LOW findings.** `TXN-107`'s `task_queue.py:86-88` and `TXN-110`'s quoted
   snippet are the two soft spots; both conclusions survived independent re-derivation. HIGH/MEDIUM anchors in this
   report are uniformly exact.

## Execution readiness

| Finding | Ready to execute | Precondition |
|---|---|---|
| TXN-102 | **Yes** | Strengthen `tests/test_services_integration.py:611-619` first; verify against a fresh session |
| TXN-103 | **Yes** | Must add an `IntegrityError` arm; must **not** add a name pre-check (`layout_service.py:140-142`) |
| TXN-104 | Yes | `SELECT … FOR UPDATE` over `users`; no `with_for_update` exists in `src/` today, so this is a new precedent — keep it in the repository layer per `architecture.md:180-182` |
| TXN-105 | Yes | Re-read `tests/test_starter.py:697-704` first; the engine-order assertion must still hold |
| TXN-106 | Yes | Delete the dead path and de-duplicate the predicate; add the missing test for whichever survives |
| TXN-107 | Yes | Attach to `HO-9`; do not schedule as an independent defect |
| TXN-108 | Yes | Documentation-only; edit both `health-api.md` sites, add nothing to `app.py` |
| TXN-109 | Yes | Documentation-only; `architecture.md:367` and `:393-396` |
| TXN-110 | Yes | Documentation change; do **not** re-point the bootstrap — and re-derive `:510-513` from the tree, not from the audit's transcript |
| TXN-111 | Yes | Delete `core/base_repository.py`; no importer |
| TXN-112 | Yes | Reconcile `IFilterService` deliberately; `routes/filters.py` is a placeholder to keep, not dead code; correct the test-path reference |
| TXN-101 | **No** | Requires an explicit ownership ruling against `B1-…:609` **and** a deliberate update of `tests/test_auth_service.py:672-717` / `:1099-1161` |

## Summary table

| Finding | Filed | Validated | Verdict | Anchor accuracy | Notes |
|---|---|---|---|---|---|
| TXN-101 | CRITICAL | **CRITICAL** | CONFIRMED | 7/7 exact | Reproduced at DB level; consequence corrected (terminal, not retry-only); blocked by `B1:609` + 2 tests that encode the defect |
| TXN-102 | HIGH | **HIGH** | CONFIRMED | 7/7 exact | Reproduced independently; `processing_configs` unchanged at 1 row |
| TXN-103 | MEDIUM | **MEDIUM** | CONFIRMED | 6/6 exact | Reproduced **through the route handler** (stronger than filed); `PendingRollbackError` amplification refuted |
| TXN-104 | MEDIUM | **MEDIUM** | CONFIRMED | 3/3 exact | `B1` non-overlap disclosure verified; zero `with_for_update` in `src/` |
| TXN-105 | MEDIUM | **MEDIUM** | CONFIRMED | 7/7 exact | Two distinct lock keys confirmed; test-tier only |
| TXN-106 | LOW | **LOW** | CONFIRMED | 8/8 exact | Authored LOW; dead-code census exact (5 hits, 0 tests) || TXN-107 | MEDIUM | **LOW** | CONFIRMED / **re-graded** | 7/7 exact, 1 imprecise | Downgraded; `HO-9` verified at `SPEC.md:236`; fail-closed limiter at `upload.py:178-180` |
| TXN-108 | LOW | **LOW** | CONFIRMED | 3/3 exact | Doc drift; code comment is correct |
| TXN-109 | LOW | **LOW** | CONFIRMED | 5/5 exact | `file-cleanup.md:117` is the correct counter-site |
| TXN-110 | LOW | **LOW** | CONFIRMED | 1/1 exact, 1 stale quote | Quoted symbols no longer exist; observation verified at cited lines |
| TXN-111 | LOW | **LOW** | CONFIRMED | 3/3 exact | 204 lines, exactly 1 reference in the whole repo |
| TXN-112 | LOW | **LOW** | CONFIRMED | 3/4 exact | 3 corrections: false blanket claim, non-existent test file, wrong deletion premise |

## Final severity counts

| Severity | Filed | Validated | Findings |
|---|---|---|---|
| CRITICAL | 1 | **1** | TXN-101 |
| HIGH | 1 | **1** | TXN-102 |
| MEDIUM | 4 | **3** | TXN-103, TXN-104, TXN-105 |
| LOW | 6 | **7** | TXN-106, TXN-107, TXN-108, TXN-109, TXN-110, TXN-111, TXN-112 |
| **Total** | **12** | **12** | |

**Verdicts** — Confirmed 12 · Corrected 3 (TXN-101, TXN-103, TXN-112) · Re-graded 1 (TXN-107) · **Rejected 0**

**Anchor accuracy: 55 distinct `file:line` anchors cited across the twelve findings (61 mentions) — every one
resolves and says what the report claims**, with two soft spots that do not change any conclusion:
`task_queue.py:86-88` (TXN-107, imprecise) and TXN-110's fenced transcript (symbols since removed). **Zero stale
line anchors** — no finding required `git log` archaeology because none pointed past its file's current content.
This is materially better than the phase-01 pass, where 9 of 14 findings had stale anchors.

**Highest-severity confirmed findings** — `TXN-101` (CRITICAL): `approve_registration_request` splits one
three-row domain write across two transactions, and I reproduced the resulting orphan account against the live
database — active user, `force_password_change` false, bcrypt hash of a password that never reached Redis,
registration request still `pending`, and all three write paths to that address now refusing. Then `TXN-102` (HIGH):
`ProcessingConfigService.upsert`/`.delete` acknowledge writes they discard, reproduced independently.

## Validation method

- Every cited `file:line` was re-opened and read at HEAD `eba2348`, in three batches, at the moment of writing this
  report — after all runtime work was complete. A mechanical extraction over the twelve findings yields **55
  distinct anchors across 61 mentions**; all resolve, and the 2 soft spots named in the summary are imprecise
  rather than stale, so no `git log` archaeology was needed for any finding.
- Zero-quorum searches run directly rather than trusted: `commit|rollback|flush` across the three processing-config
  modules; `BaseRepository` across `src/`, `tests/`, `alembic/`, `docs/`; `delete_old_logs` across `src/`, `tests/`,
  `alembic/`; `with_for_update` across `src/`; `get_by_username` across `src/`; `TXN-102`/`TXN-112` across
  `.ai/tasks/`; `processing-config` across `frontend/src/`; `AUTO_MIGRATE` across compose and `src/`.
- Runtime probes were written by me, executed in the `mkobi-app` container against the live development PostgreSQL
  at `localhost:5432`, and are **not** the auditor's transcripts. Three probes: `TXN-102` (upsert/delete
  durability), `TXN-103` (route-handler status code, transaction state, unique index), `TXN-101` (partial-commit
  orphan state, retry, `register_request`).
- redis-py 8.0.0 figures were read from the installed package in the container (`redis/_defaults.py:7-8` and
  `:37-39`, `redis/client.py:248-249` and `:259-264`) rather than quoted from the report.
- `pg_stat_activity` was used as independent server-side corroboration for `TXN-102`.
- **Cleanup verified**: `processing_configs` = 1 row (pre-probe baseline), `dashboards` = 5 rows (pre-probe
  baseline), 0 `val03-probe-%` dashboards, 0 `val03-probe-%` configs, 0 `val03t101-%` users,
  0 `val03t101-%` registration requests, 0 `val03t103-%` dashboards. No production, config, test or migration file
  was modified; this report is the only file written.
