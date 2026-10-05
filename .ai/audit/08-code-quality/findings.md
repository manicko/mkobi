---
phase: 08-code-quality
executed: 2026-10-05
executor: auditor
problems-only: true
findings: 14
by-severity:
  CRITICAL: 0
  HIGH: 3
  MEDIUM: 9
  LOW: 2
---

# Phase 08 — Findings

## Summary

Ten blocks were examined against the declared contract at `HEAD 0ae6ddf`, with the working tree
dirty under `frontend/src/shared/types/api.types.ts`, `src/mkobi/api/routes/data.py`,
`src/mkobi/db/repositories/aggregated_data_repo.py`, `src/mkobi/interfaces/service_interfaces.py`,
`src/mkobi/models/dashboard.py`, `src/mkobi/models/data.py`, `src/mkobi/services/data_service.py`
and seven test files (Appendix E). Both backend gates were executed and are green, so no finding in
this report rests on a red baseline: `uv run ruff check src/ tests/ alembic/env.py` → `All checks
passed!`, and `uv run mypy src/ alembic/env.py` → `Success: no issues found in 121 source files`.
The most consequential thing found is that **two of the ten declared service layers are
unreachable**: `GraphService` and `FilterService` have no production caller, their DI factories are
named in `api/deps.py::__all__` and in `tests/test_deps.py` but in no route, and the six endpoints
of their two domains obtain repositories through `Depends` and own the use case themselves — which
leaves `GraphService._validate_graph_data`, the only non-empty-name check in the graph domain, with
no reachable caller, so `GraphBase.name: str` admits `""` and the repository persists it
(**CQ-101**). The second HIGH is that the email-format and password-strength rules each have two
implementations, and the reachable copy and the test-pinned copy already disagree on the bcrypt byte
budget (**CQ-102**). Thirteen further defects follow — 9 MEDIUM and 2 LOW — and none is CRITICAL: no
wrong or lost value is in storage as a result of any of them today. The mechanical sweeps the phase
inherited (per the earlier decomposition, `docs/SPEC.md:245-246`) came back clean and are recorded in
Appendix A, not filed.

**Finding-ID namespace collision, disclosed.** The phase task file
(`.kilo/commands/audit/phases/08-audit-code-quality.md:172`) and the code-context note
(`.ai/plans/_code-context/08-code-context/08-code-quality-code-context.md:5` — actual path
`.ai/plans/_code-context/08-code-quality-code-context.md:5`) both mandate the `QLT-` prefix, and
`QLT-001 … QLT-010` are already spent: `docs/SPEC.md:245-246` records all ten as **remediated** in
phase `08-code-quality-remediation`. The instruction that dispatched this pass mandates `CQ-`, so
this report uses `CQ-101 … CQ-114` and creates a second namespace rather than reusing spent `QLT-`
identifiers. `.ai/audit/07-external-boundary/` does not exist at write time, so phase 07 has minted
no `VAL-07-*`; this pass mints no `VAL-08-*` (validation is not this role's).

## Findings

### CQ-101 — The graph and filter domains run route-to-repository, leaving their service layers and their name rule unreachable

**Severity** — HIGH

**Zone** — "Responsibility inside a unit: how many jobs one unit does, and which is reachable from elsewhere"

**Observation** — `GraphService` (`src/mkobi/services/graph_service.py`, 291 lines, 14 methods) and
`FilterService` (`src/mkobi/services/filter_service.py`, 331 lines, 6 public methods) have **zero
production call sites**. A search for `graph_service.<method>` and `filter_service.<method>` across
every file in `src/` returns nothing; the only references to either class name outside their own
module are the two DI factories and their `__all__` entries. Those factories are named in no route:

```python
357: def get_filter_service(
358:     filter_repo: FilterRepository = Depends(get_filter_repository),
359: ) -> FilterService:
```
```python
387: def get_graph_service(
388:     graph_repo: GraphRepository = Depends(get_graph_repository),
389: ) -> GraphService:
```

(`src/mkobi/api/deps.py:357-359`, `:387-389`). Of the ten service factories in `deps.py`, these two
are the only ones no route file names. What runs instead is the route layer holding the use case:
`src/mkobi/api/routes/dashboards_filters.py` injects **six** repository parameters across its three
handlers and **zero** services, and `src/mkobi/api/routes/dashboards_graphs.py` injects two repository
parameters and zero services. The create-graph handler performs the write and the commit itself:

```python
 97:         result = await graph_repo.create(
 98:             db=db,
 99:             name=graph.name,
100:             type=graph.type,
101:             dashboard_id=dashboard_id,
102:             config=graph.config,
103:             dimensions=graph.dimensions,
104:             metrics=graph.metrics,
105:         )
106:         await db.commit()
```

(`src/mkobi/api/routes/dashboards_graphs.py:97-106`). The consequence inside the service is that its
validation never executes:

```python
64:         if not data.name or not data.name.strip():
65:             raise ValueError("Graph name cannot be empty")
```

(`src/mkobi/services/graph_service.py:64-65`, inside `_validate_graph_data`, called only from
`GraphService.create` at `:94`). The request model it would have guarded declares no constraint:

```python
44: class GraphBase(BaseModel):
45:     """Base model for charts."""
46: 
47:     name: str
48:     type: GraphType
```

(`src/mkobi/models/graph.py:44-48`).

**Evidence** — Static proof of unreachability: zero `graph_service.<method>` / `filter_service.<method>`
matches in `src/`; the per-module injection census (Appendix C) gives `dashboards_filters.py` 6
repository parameters / 0 services, `dashboards_graphs.py` 2 / 0, `data.py` 1 / 1, and no other
route module injects a repository at all. The graph name path is read directly:
`GraphCreate` (`src/mkobi/models/graph.py:69-89`) declares `name: str` inherited from `GraphBase` with
no `min_length`, no `field_validator`, and no `extra`-based guard on `name`; the sole emptiness check
in the domain is the unreachable one at `graph_service.py:64-65`; and `POST /dashboards/{id}/graphs`
reaches `graph_repo.create` without passing through it.

**Consequence** — Two of the ten declared service layers, 622 lines plus the two `I*Service`
protocols, are not on any request path. The declared direction API → Service → Repository is skipped
end-to-end for two of twelve route modules, and the six endpoints of those modules own their
transaction inside the handler. The observable defect is the one the unreachable rule was written to
prevent: a graph whose `name` is the empty string, or whitespace only, is accepted at the request
boundary, passes `GraphCreate`, and is written to the `graphs` table — the rule that refuses it has no
reachable caller. Everything else about the layer is a maintenance cost rather than a live fault.

**Recommendation** — Two shapes, and the choice is a scope decision, not a technical one. The
smaller change is to route the six handlers through the services that already exist: declare
`graph_service: GraphService = Depends(get_graph_service)` on the two graph handlers and
`filter_service: FilterService = Depends(get_filter_service)` on the filter handlers, and delete the
in-handler `db.commit()` calls so the commit moves into the service that owns the unit of work. That
makes `_validate_graph_data` reachable with no new code and no new file. The larger change is to
admit that the graph and filter domains have no service and delete both modules and both protocols —
but that must be a deliberate ruling, because the interfaces are published in
`src/mkobi/interfaces/__init__.py` and deleting them is a wider change than the first option.
Independently of which shape is chosen, give `GraphBase.name` a `min_length=1` at the boundary: the
boundary should not depend on a service being wired for the rule to hold. **Remediation blocker:**
`tests/test_deps.py:442-446` (`test_get_graph_service_returns_graph_service`) pins the factory's
runtime identity. It breaks on neither option, but it is the *only* thing currently covering the
graph service, so a reviewer should not read the green suite as evidence that the service works.

### CQ-102 — The email-format and password-strength rules each have two implementations, and the two password copies already disagree

**Severity** — HIGH

**Zone** — "One rule, one home: whether exactly one implementation exists"

**Observation** — `mkobi/utils/validators.py` is a second home for two credential rules, and neither
of its two copies is the one production runs. The email pattern is byte-identical in two modules:

```python
16: EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
```
```python
38: EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
```

(`src/mkobi/utils/validators.py:16` and `src/mkobi/services/auth_service.py:38`.) Only the second is
read: `auth_service.py:98` uses it inside `_validate_email_format`, called from `:144`; the first is
read only by `validators.py:38` inside `validate_email`, which has **no caller in `src/`**.

The password rule is worse, because the two copies live in the same module and disagree:

```python
145: def validate_password(password: str, min_length: int = 8) -> bool:
```
```python
183: def validate_password_or_raise(password: str, min_length: int = 8) -> None:
```
```python
221:     if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
222:         raise ValueError(
223:             f"Password is too long: at most {MAX_PASSWORD_LENGTH} bytes are allowed"
224:         )
```

(`src/mkobi/utils/validators.py:145`, `:183`, `:221-224`.) Only `validate_password_or_raise` runs —
it is the validator behind `models/auth.py:136` and `:225`, `models/user.py:46`, `:128` and `:154`,
and `auth_service.py:145` and `:588`. `validate_password` has no caller in `src/`, and the byte
budget at `:221` is the divergence: the reachable copy refuses a value the dead copy accepts.

**Evidence** — Caller census over `src/mkobi/**/*.py` and `tests/*.py` (Appendix C): `validate_email`
appears at its own definition plus `tests/test_validators.py` (13 call sites) and never in
production; `validate_password` appears at its own definition plus `tests/test_validators.py:76-109`
and never in production; `validate_password_or_raise` has 7 production call sites. The disagreement is
read directly from the two bodies: `validate_password` ends at `:180` after the digit and letter
checks and has no byte-budget clause; `validate_password_or_raise` carries it at `:221-224` and
documents why at `:186-197`. The `MAX_PASSWORD_LENGTH` constant is owned by `mkobi.core.security` and
imported lazily at `validators.py:207` with the circular-import reason recorded — that reason holds,
and the remedy is not to move the constant.

**Consequence** — The credential-strength rule has no single discoverable home. The copy a reader
finds first, and the copy the only test file exercises, is the one that does not run; the copy that
does run is the one with no test. A maintainer tightening the rule — adding a symbol requirement, a
length change, a breach-list check — will most plausibly edit `validate_password`, because that is
where the tests are, and production will not change. The email rule has the same shape with the
stakes lower: two byte-identical patterns, one reachable, so a fix to the reachable one silently
leaves the other behind. The two password copies have already begun to disagree on a value the system
acts on, which is the divergence the one-rule-one-home property exists to prevent.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**. Make
`utils/validators.py` the single home and delete the two dead functions: remove `validate_password`
(its five call sites are all in `tests/test_validators.py:76-109`, which then tests
`validate_password_or_raise` through the same assertions), and remove `validate_email` plus
`validators.py:16` so the pattern has one definition. `utils/validators.py` is then four live
functions (`validate_role`, `validate_uuid`, `validate_string`, `raise_if_invalid`) — note that
`validate_role` is the only other one with a production caller, at `auth_service.py:65`, `:143` and
`user_service.py:29`; the remaining three are in the same position as the two being removed and
`tests/test_validators.py` is the only thing that reaches any of them, which is worth one decision
about the module as a whole rather than six separate ones. Point `auth_service.py:38` at
`validators.EMAIL_REGEX` rather than deleting the reachable copy — `auth_service` is imported during
`mkobi.config`'s own import, and `validators.py` imports only `mkobi.models.enums`, so the direction
is safe. **Remediation blocker:** `tests/test_validators.py:76-109` encodes the dead copy as
intended behaviour; those tests must change with the removal, or the project's "production code is
the source of truth" rule requires keeping both.

### CQ-103 — The application role name has two homes, and the raw-SQL one silently disables the least-privilege check

**Severity** — HIGH

**Zone** — "Fixed values: one named home per value, and what bypasses it"

**Observation** — The PostgreSQL role the application connects as is a declared configuration value:

```python
254: class DatabaseSettings(BaseModel):
255:     """Database connection settings."""
256: 
257:     host: str = "localhost"
258:     port: int = 5432
259:     dbname: str = "bidb"
260:     user: str = "mkobi_app"
```

(`src/mkobi/config.py:254-260`, overridable as `DATABASE__USER`.) The same value is written as a raw
literal into **seven** executable statements in `src/mkobi/db/starter.py`, none of which the type
system can check and none of which reads `DatabaseSettings`:

```python
420:                         await conn.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO mkobi_app"))
422:                         await conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mkobi_app"))
424:                         await conn.execute(text("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO mkobi_app"))
426:                         await conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mkobi_app"))
427:                         await conn.execute(text("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO mkobi_app"))
```
```python
577:             async with self._main_engine.connect() as conn:
578:                 result = await conn.execute(
579:                     text("SELECT rolcreatedb FROM pg_roles WHERE rolname = 'mkobi_app'")
580:                 )
581:                 row = result.fetchone()
582:                 if row and row[0]:
583:                     logger.warning(
584:                         "mkobi_app has CREATEDB privilege - violates least-privilege. "
585:                         "Run: ALTER ROLE mkobi_app NOCREATEDB;"
586:                     )
```

(`src/mkobi/db/starter.py:420`, `:422`, `:424`, `:426`, `:427`, `:577-586`; the seventh site is the
`GRANT CONNECT` in the test-database recreation at `:392`.)

**Evidence** — Static: the literal census (Appendix C) gives 13 `mkobi_app` occurrences in `src/`, of
which these 7 are inside SQL string literals and 4 more are in log and docstring text; the only
non-literal occurrence is the configured default at `config.py:260`. The fail-open behaviour is read
from the branch: `row = result.fetchone()` at `:581`, then `if row and row[0]:` at `:582`. A
`SELECT` against `pg_roles` for a role name that does not exist returns zero rows, not an error, so
`row` is `None` and the function returns having emitted nothing.

**Consequence** — A deployment that sets `DATABASE__USER` to anything other than `mkobi_app` — which
the configuration explicitly supports, and which is the normal way to run this image against a
managed PostgreSQL with pre-provisioned roles — loses two things silently. `_verify_role_privileges`,
whose docstring at `db/starter.py:574` declares it "defense-in-depth" for least privilege, resolves
to zero rows and returns having checked nothing: a role that *does* hold `CREATEDB` is never
reported. And `recreate_test_database` issues its six `GRANT` statements against a role that may not
exist, so test-database setup fails with a PostgreSQL `UndefinedObjectError` naming a role the
operator never configured. Neither failure is a type error, a lint error, or a test failure; both
appear only at start-up in a configuration the declared gates never execute.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**. Read the role
name from the one home: `DatabaseSettings.user` is already resolved in the starter's config (it reads
`self._config.main_database_url` and `get_config().DATABASE_URL` at `db/starter.py:225`), so
`_verify_role_privileges` should compare against that value and the `GRANT` statements should bind it
as a parameter — `text("GRANT USAGE, CREATE ON SCHEMA public TO :role")` with
`{"role": self._config.user}` — rather than interpolating a literal. The `GRANT CONNECT` at `:392`
uses `DDL(...)` with a `context` mapping already, so the pattern is established in the same function.
Separately, make `_verify_role_privileges` distinguish "checked, no violation" from "could not check":
`if row is None:` should log at `warning` that the configured role was not found, because a
least-privilege check that silently answers "clean" when it did not run is worse than no check.

### CQ-104 — `_get_alembic_revision` returns "schema not initialized" for every possible fault, and the caller then names the wrong remedy

**Severity** — MEDIUM

**Zone** — "Declared contracts and their enforcement point: whether anything checks the claim, and whether anything reaches it"

**Observation** — The function declares one meaning for its `None` return and the code gives it
another:

```python
201:     async def _get_alembic_revision(self) -> str | None:
202:         """Get current alembic revision from database.
203: 
204:         Returns revision hash if schema is initialized, None otherwise.
205:         """
...
217:         except Exception:
218:             return None
```

(`src/mkobi/db/starter.py:201-205`, `:217-218`.) This is the only bare `except:` in `src/` that
emits **no log record at all** — all 49 other `except Exception` handlers in the tree log before
returning or raising (Appendix A). Its single caller turns that `None` into a start-up abort:

```python
251:         # Check if schema is properly initialized via alembic
252:         current_rev = await self._get_alembic_revision()
253:         if not current_rev:
254:             raise SchemaNotFoundError(
255:                 "Database schema not initialized - no alembic revision found"
256:             )
```

(`src/mkobi/db/starter.py:251-256`.)

**Evidence** — Read in full; the `try` spans `:208-216` and contains a `SELECT version_num FROM
alembic_version` (`:212`), so a permission denial, a statement timeout, a dropped connection, a
missing table and an uninitialised schema all produce the identical bare `return None` at `:218`.
The caller census shows exactly one call site, `:252`. The default log level is `INFO`
(`src/mkobi/core/logging_config.py:73`, `log_level: str = "INFO"`), so even a `debug`-level record
would not appear in a default deployment.

**Consequence** — A start-up failure caused by anything other than an unrun migration is reported to
the operator as `SchemaNotFoundError: Database schema not initialized - no alembic revision found`,
and no log record anywhere in the process names the actual fault. The remedy the message implies —
run the migrations — is the wrong one for a `SELECT` that failed on permissions or a connection
that was refused, and applying it does not clear the failure. This is the first thing an operator
sees on a misconfigured deployment, and it costs a diagnosis cycle to discover it is misleading. The
blast radius is bounded: it is a start-up-path message, not a wrong stored value.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**. Log before
returning and keep the abort:

```python
        except Exception as e:
            logger.warning("Could not read alembic_version: %s", e)
            return None
```

A `warning` rather than an `error`, because the caller still refuses to start and the abort message
is unchanged. If the distinction matters operationally, the cleaner shape is to return a sentinel the
caller can separate — `raise` on the read and let `_check_db_connection` at `:242` own connectivity —
but that changes start-up ordering and belongs with the phase that owns the starter's transaction
shape, so the log line is the change recommended here.

### CQ-105 — One 32-member vocabulary is maintained by hand in four structures, and every miss is silent

**Severity** — MEDIUM

**Zone** — "The constant surface as a maintained artefact: is anything else maintaining it"

**Observation** — `ErrorCode` is the declared central vocabulary. Its membership must be mirrored in
three hand-written tables in a second module, plus one partial table in the reverse direction:

| Structure | Location | Rows |
|---|---|---|
| `ErrorCode` members | `src/mkobi/models/enums.py:243-288` | 32 |
| `_ERROR_CODE_STATUS_MAP` | `src/mkobi/utils/exceptions.py:33-74` | 32 |
| `titles` local to `get_error_title` | `src/mkobi/utils/exceptions.py:184-225` | 32 |
| `status_to_code` local to the Starlette handler | `src/mkobi/utils/exceptions.py:323-329` | 5 |

All three complete tables are currently exhaustive, which is worth stating because it is the only
reason this is not CRITICAL. Nothing keeps them that way. The two lookups both fall back silently:

```python
121:         self.status_code = (
122:             status_code if status_code is not None
123:             else _ERROR_CODE_STATUS_MAP.get(code, HTTP_500_INTERNAL_SERVER_ERROR)
124:         )
```
```python
226:     return titles.get(code, "Error")
```

(`src/mkobi/utils/exceptions.py:121-124`, `:226`.) The reverse table is a different shape of gap: it
covers 404, 401, 403, 400 and 422, and everything else defaults:

```python
323:         status_to_code: dict[int, ErrorCode] = {
324:             HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
325:             HTTP_401_UNAUTHORIZED: ErrorCode.AUTHENTICATION_FAILED,
326:             HTTP_403_FORBIDDEN: ErrorCode.PERMISSION_DENIED,
327:             HTTP_400_BAD_REQUEST: ErrorCode.VALIDATION_ERROR,
328:             HTTP_422_UNPROCESSABLE_CONTENT: ErrorCode.VALIDATION_ERROR,
329:         }
330:         code = status_to_code.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
```

(`src/mkobi/utils/exceptions.py:323-330`.) The value table is also built inside the function that
consumes it, so no second component can consult it.

**Evidence** — Row counts derived mechanically from the source (Appendix C): 32 `ErrorCode`
assignments inside the class body, 32 `ErrorCode.X: HTTP_…` rows, 32 `ErrorCode.X: "…"` rows. A
search of all 60 test files for `_ERROR_CODE_STATUS_MAP`, `get_error_title` and `status_to_code`
returns **zero** hits — nothing in the suite asserts that the three agree. `tests/test_error_response_format.py`
has seven tests, and each asserts the shape of a response for one status it triggers; none iterates
the vocabulary.

**Consequence** — Adding one `ErrorCode` member requires three edits across two files, and forgetting
the third ships a live defect with a green suite: `_ERROR_CODE_STATUS_MAP.get` returns 500, so the
member answers with the wrong status, while `titles.get` returns the literal string `"Error"`, so the
RFC 7807 body's `title` is `Error` and its `type` is derived from the code. A reader cannot tell from
the response that the mapping is missing. In the other direction, every Starlette-raised status outside
the five listed is labelled `INTERNAL_ERROR` while `status` keeps its true value — a `405` from a
wrong method on a declared path, which Starlette raises as `HTTPException(405)`, produces a body whose
`code` is `INTERNAL_ERROR` and whose `title` is `Internal server error`, so a client routing error is
reported to the operator as a server fault.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**. Make the two
complete tables derived rather than written. Storing the status on the member's own value
(`ERROR = "ERROR|500"`) and parsing it in one helper, or moving both tables onto the `ErrorCode`
class as a single `STATUS` mapping plus a `TITLE` mapping, collapses three hand-maintained structures
to one and makes a missing row an `AttributeError` at import time instead of a wrong response at
runtime. For the reverse table, add the statuses the framework can actually raise on this app —
405, 413, 429, 503 — and make the default branch log the unmapped status so a future gap is visible.
Whichever shape is chosen, add one test that asserts `set(_ERROR_CODE_STATUS_MAP) == set(ErrorCode)`
and `set(titles) == set(ErrorCode)`; that single assertion is what turns three hand-maintained tables
into a maintained artefact.

### CQ-106 — One raise site in `src/` bypasses the declared single raise mechanism

**Severity** — MEDIUM

**Zone** — "Convention compliance: the cheap high-volume rules, and which of them are broken"

**Observation** — `AGENTS.md` §4 forbids raising `HTTPException` directly and names
`AppException` as the single raise mechanism. A mechanical sweep of `src/` finds **no** use of
FastAPI's `HTTPException` and 34 `raise AppException` sites — but it finds one raise that is neither,
declared by a function-body import that exists only for this:

```python
534:     from starlette.staticfiles import StaticFiles as BaseStaticFiles
535:     from starlette.responses import FileResponse
536:     from starlette.exceptions import HTTPException
```
```python
582:                 # For API routes, return 404 to let FastAPI's exception handler format it
583:                 # This prevents SPA fallback for API routes
584:                 raise HTTPException(status_code=404, detail="Not found")
```

(`src/mkobi/app.py:534-536`, `:582-584`.) The response is still RFC 7807 — the registered
`StarletteHTTPException` handler at `src/mkobi/utils/exceptions.py:313-342` converts it — but the
`code` is recovered from a status table rather than declared at the raise site, and the `detail` is a
bare literal with no `ErrorCode` behind it.

**Evidence** — Read of `app.py:525-596` and of `utils/exceptions.py:313-342`. The handler's
`status_to_code` maps 404 to `ErrorCode.NOT_FOUND`, so today's response is conforming by coincidence
of the status value, not by construction. The raise site logs nothing; the handler logs the 404 at
`ERROR` (`exceptions.py:317-321`), so every unmatched path under `/api/` that reaches the SPA mount
produces an ERROR-level record.

**Consequence** — The single-raise rule has one exception, and it is invisible from the rule's own
text: a reader checking `HTTPException` usage with the FastAPI import finds nothing and concludes the
rule holds. A future change that raises a different status from this class — 403 for a forbidden
static path, say — produces `code=INTERNAL_ERROR` by the default branch at `exceptions.py:330` rather
than the intended code, and nothing in the raise site says which code was meant. The ERROR-level log
for what is an ordinary 404 on a public path is a smaller operability cost: an unauthenticated client
can generate unbounded ERROR records by requesting nonexistent `/api/` paths.

**Recommendation** — `[SPEC-DEVIATION]`, **priority: recommended**, **effort: trivial**. Raise
`AppException(code=ErrorCode.NOT_FOUND, detail="Not found")` at `app.py:584` instead. The registered
`AppException` handler produces the same status and the same `code`, so the wire response is
unchanged, and the raise site then names its own code. Two secondary points, both in the same handler
and both optional: log the Starlette 404 at `info` rather than `error` (a missing static path is
routine), and keep the `starlette.exceptions` import at module scope if the class no longer needs it.

### CQ-107 — The health surface's status vocabulary has no named home, and its 503 is not an RFC 7807 body

**Severity** — MEDIUM

**Zone** — "Fixed values: one named home per value, and what bypasses it"

**Observation** — `/health` and `/health/detailed` publish a status vocabulary as **eight** bare
string literals across two handlers, with no `StrEnum`, no module constant, and no validation:

```python
380:         try:
381:             # Quick DB connectivity check
382:             async with get_session() as db:
383:                 await db.execute(text("SELECT 1"))
384:             return JSONResponse(
385:                 content={"status": "healthy", "database": "connected"}
386:             )
387:         except Exception as e:
388:             logger.error("Health check failed: %s", e)
389:             return JSONResponse(
390:                 status_code=503,
391:                 content={"status": "unhealthy", "database": "disconnected"},
392:             )
```

(`src/mkobi/app.py:380-392`; the same six values recur at `:408`, `:419`, `:426`, `:428`, `:438`,
`:452`, `:461`.) The 503 branch is an API error response that is not RFC 7807: it carries no `type`,
`title`, `code` or `detail`, so the declared client extraction chain in
`frontend/src/shared/api/errorHandler.ts:37-102` finds no `code` field and falls through to the
generic `An error occurred` at `:100`. The two handlers also disagree on scope by design — `/health`
is database-only and `/health/detailed` adds four components — and the asymmetry is documented in
prose at `app.py:441-448` rather than in a type.

**Evidence** — Read of `app.py:373-392` and `:394-470`. The value crosses a tier: the container
healthcheck consumes the status code (`docker/docker-compose.yml:201`,
`test: ["CMD", "curl", "-f", "http://localhost:8000/health"]`), and `tests/test_health.py:51` pins the
exact two-key body of the 200. No frontend code references `/health` or any of the six values, and
`tests/test_health.py` asserts the literals, not a vocabulary — so a rename would be caught for
`/health` and not for the four `components[*].status` values, which only `tests/test_static_bundle.py`
touches.

**Consequence** — Two declared rules are bypassed by the same two functions, and both are the price
of the surface having been built outside the error and constant architecture. The 503 is a
non-conforming error body on a published endpoint; the eight-value family has no single home, so a
change to the vocabulary is eight edits with a type checker that sees eight `str`s and a test suite
that pins two of them. The blast radius is bounded: the only in-repo consumer of the status code is
`curl -f`, and nothing branches on the body.

**Recommendation** — Two changes, both small. Declare the vocabulary as a `StrEnum` next to the
existing `EnvironmentEnum` in `src/mkobi/models/enums.py` and use its members at all eight sites, so
a typo becomes a type error and the family has one home. For the 503, either raise
`AppException(code=ErrorCode.SERVICE_UNAVAILABLE, ...)` and let the registered handler format it, or —
if the two-key body is load-bearing for the healthcheck contract — record the exemption in
`AGENTS.md` §4 and in `docs/08-security/error-format.md` with the reason, so the next reader knows the
deviation is decided rather than forgotten. `tests/test_health.py:51` pins the current 200 body and
does not obstruct either change; a 503-body assertion does not exist, so adding the RFC 7807 shape is
not a test-breaking change.

### CQ-108 — Two declared lint rules apply to nothing

**Severity** — MEDIUM

**Zone** — "Convention compliance: the cheap high-volume rules, and which of them are broken"

**Observation** — `pyproject.toml` declares two per-file exceptions that cannot apply to any file in
the repository:

```toml
142: "src/mkobi/core/permissions.py" = ["F821"]  # FastAPI Depends(get_db) pattern
143: "src/mkobi/interfaces_old/*.py" = ["UP046"]  # Old interfaces, not used
```

(`pyproject.toml:142-143`.) The first names a path that exists but a reason that does not:
`src/mkobi/core/permissions.py` is 223 lines and its complete import block is `logging`, `uuid.UUID`,
`sqlalchemy.ext.asyncio.AsyncSession`, `AccessRepository`, `UserRepository`, `DashboardPermission` and
`UserRole` — there is no FastAPI import and no `Depends` anywhere in the file, and the declared
`Depends(get_db)` pattern is not what it does. The second names a path that does not exist:
`Test-Path src/mkobi/interfaces_old` returns `False`.

**Evidence** — `pyproject.toml:142-143` read directly. `src/mkobi/core/permissions.py:1-22` read in
full for the import block; a search for `Depends` and `fastapi` in that file returns zero hits. Path
existence confirmed by `Test-Path`. `uv run ruff check src/ tests/ alembic/env.py` returns
`All checks passed!`, which is consistent with both waivers being inert rather than with their being
needed.

**Consequence** — `F821` (undefined name) is waived for the one module that implements the
authorization decision, on a stated reason that is false. That is the diagnostic class that would
catch a typo in a branch no test exercises, in the file where a typo has the highest blast radius, so
the waiver removes exactly the check that file most needs. The `UP046` waiver is harmless but is a
second signal that the per-file table is not maintained against the tree: an exception that matches
nothing is indistinguishable, to a reader, from one that is quietly load-bearing.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**. Delete line
143 outright, and delete line 142 as well — `ruff check` stays green without it, which is the proof
that the waiver was never needed. If a future change really does put a `Depends(get_db)` default in
that module, re-add the waiver with that change, where the reason is true. The generalisable fix, if
the table grows again, is a check that every glob in `per-file-ignores` matches at least one file;
no such check exists and none is recommended here for a two-entry table.

### CQ-109 — The aggregate gate omits the two gates the project declares, stops at the first failure, and runs from no automated path

**Severity** — MEDIUM

**Zone** — "The gates the project declares: where each is wired, what each decides, and whether it can be run the way the pipeline runs it"

**Observation** — `.\Makefile.ps1 check` is the entry point the project's own rules file publishes as
the aggregate (`.kilo/rules/commands.md:153`, "All of the above | `.\Makefile.ps1 check`"). It runs
four gates, returns on the first failure, and never invokes the test suite or the schema-drift check:

```powershell
281: function Invoke-Check {
282:     Invoke-Lint
283:     if ($LASTEXITCODE -ne 0) { return }
284:     Invoke-Typecheck
285:     if ($LASTEXITCODE -ne 0) { return }
286:     Invoke-FeLint
287:     if ($LASTEXITCODE -ne 0) { return }
288:     Invoke-FeTest
289: }
```

(`Makefile.ps1:281-289`.) Both omitted gates exist and are wired to their own targets —
`Invoke-Test` at `:227-230` and `Invoke-MigrationCheck` at `:315-317`, the latter documented in the
help text at `:108` as "Detect model/schema drift (alembic check, test DB)". No automated path invokes
any of them: `.github`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `.circleci`, `.gitea`,
`.woodpecker.yml`, `Jenkinsfile` and `.pre-commit-config.yaml` are all absent.

**Evidence** — `Makefile.ps1` read at `:261-289` (the five gate functions and the aggregator),
`:220-239` (`Invoke-Test`, `Invoke-TestAll`), `:315-317` (`Invoke-MigrationCheck`), and `:1000-1046`
(the target dispatch table, which does map `test` and `migration-check`). The help text at `:96-108`
lists `check` as "lint + typecheck + fe-lint + fe-test" and lists `migration-check` on its own line.
`Test-Path` over the eight CI paths returns `False` for all eight. The declared command surface in
`.kilo/rules/commands.md:146-153` and the help text agree with each other and both omit pytest and
the drift check from the aggregate — so this is not a documentation mismatch, it is a gate that is
reachable only by remembering its name.

**Consequence** — A contributor who runs the documented aggregate learns nothing about whether the
test suite passes or whether the ORM models still match the migration chain; both must be run
separately, by name, and neither is run by anything. The first-failure-wins shape compounds it: when
lint is red, the aggregate returns before typecheck, frontend lint and frontend tests, so a
contributor fixing one problem at a time gets one problem's worth of information per invocation and no
summary of the rest. Nothing would notice a model change that no migration records, and nothing would
notice a failing test, without a human running two extra commands by hand on every change.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**. Add
`Invoke-MigrationCheck` and `Invoke-Test` to `Invoke-Check` and accumulate rather than return early,
so one invocation reports every gate's verdict. Two things to decide explicitly rather than by
omission: `Invoke-Test` needs the test stack up, so either have `check` call `Invoke-TestUp` first or
document that `check` requires it; and `Invoke-MigrationCheck` is deliberately kept out of the
`migrate` service (`Makefile.ps1:307-314` records why), which is a different concern from the
aggregate. The absence of any automated path is a larger decision than this phase should make —
wiring `check` into a CI runner is a deployment-posture change that belongs to phase 10, and this
finding records only that no such path exists today.

### CQ-110 — The 65 % coverage floor is inert on the canonical test path, and the `tests.*` mypy override is reached by no command

**Severity** — MEDIUM

**Zone** — "The gates the project declares: where each is wired, what each decides, and whether it can be run the way the pipeline runs it"

**Observation** — Two declared thresholds are not in force on the paths contributors are pointed at.

The coverage floor is declared in `addopts` without the flag that activates the plugin:

```toml
196: addopts = "--import-mode=importlib -ra -v --strict-markers --cov-fail-under=65"
```

(`pyproject.toml:196`.) `pytest-cov` constructs its plugin only when `--cov` names a source, so
`--cov-fail-under` alone measures nothing. The canonical target passes no `--cov`:

```powershell
227: function Invoke-Test {
228:     docker compose @TestCompose up -d --wait --wait-timeout $UpTimeout test-db test-redis
229:     Invoke-TestAppPytest
230: }
232: function Invoke-TestAll {
233:     docker compose @TestCompose up -d --wait --wait-timeout $UpTimeout test-db test-redis
234:     Invoke-TestAppPytest -PyArgs @('--cov=src/mkobi', '--cov-report=term-missing')
235: }
```

(`Makefile.ps1:227-230`, `:232-235`.) The floor is therefore live on `test-all` and inert on `test`.

The mypy override for the test tree is never applied:

```toml
183: [[tool.mypy.overrides]]
184: module = ["tests.*"]
185: disallow_any_generics = false
186: warn_return_any = false
```

(`pyproject.toml:183-186`.) No command passes `tests/` to mypy — `Invoke-Typecheck` is
`mypy src/ alembic/env.py` (`Makefile.ps1:270`) — so this block is inert configuration.

**Evidence** — Executed: `uv run mypy src/ alembic/env.py` prints
`pyproject.toml: note: unused section(s): module = ['tests.*']` on every run and then
`Success: no issues found in 121 source files`. The checker itself reports the second half of this
finding. The coverage half is read from the two quoted blocks: `Invoke-TestAppPytest` (`:222-225`)
forwards only `@PytestCacheArgs @PyArgs`, and the default `$PyArgs` is empty, so the `test` target's
pytest invocation is `pytest -o cache_dir=/tmp/pytest_cache` with no coverage flag. The
`[tool.coverage.run]` (`pyproject.toml:202-204`) and `[tool.coverage.report]` (`:206-208`) sections are
present and equally unreachable on that path.

**Consequence** — The number a reader takes from `addopts` — 65 % — is not a floor on the run they are
most likely to perform. A change that drops coverage below the threshold passes `.\Makefile.ps1 test`
and is caught only by someone choosing `test-all`, which is not named in the aggregate (CQ-109) and
not in the quality-gates table of the project's own rules file. The `tests.*` override is a second
declared rule that no command applies; it is harmless today because the checker already reports the
condition on every run, but it is the kind of entry that reads as a deliberate relaxation of the test
tree's typing bar when it is in fact a leftover.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**. Pick one of
two coherent positions and make the configuration match it. Either the floor is real — add
`--cov=src/mkobi` to `addopts` so every pytest invocation measures, and accept that `test` becomes
slower; or the floor is aspirational — remove `--cov-fail-under=65` from `addopts` and leave the
measurement to `test-all`, which already passes it, so no configuration line claims a gate that does
not run. Do not leave the flag in `addopts` describing a path it does not govern. For the mypy
override, either extend `Invoke-Typecheck` to `mypy src/ tests/ alembic/env.py` — which makes the
relaxation real and deliberate — or delete `pyproject.toml:183-186`; the third option, leaving it, is
the one that costs a reader a debugging detour when they first see the checker's own note.

### CQ-111 — 17 of 59 route operations declare no response shape, including the two that return a cleartext credential

**Severity** — MEDIUM

**Zone** — "Type width and the sanctioned-suppression surface: what is enforced, what is silenced"

**Observation** — 59 `@router.<method>(` decorators exist across the 13 route modules; **17** declare
no `response_model` (Appendix C). The widened return annotation is `dict[str, Any]` in every case, so
the annotation constrains nothing and the OpenAPI document publishes an empty object schema for the
operation. The two operations that return a live credential are among them:

```python
567: @router.post(
568:     "/temp-passwords",
569:     status_code=status.HTTP_200_OK,
570:     summary="Retrieve temporary password (admin)",
571:     description=(
572:         "Returns a one-time temporary password. Admin only. The retrieval handle "
573:         "is carried in the request body, so it does not appear in the request line "
574:         "or the application access log. The password is deleted after retrieval."
575:     ),
576:     responses={**admin_responses, 503: error_503},
577: )
578: async def retrieve_temp_password_post_admin_endpoint(
579:     body: TempPasswordRetrievalRequest,
580:     admin_user: AdminUser,
581:     temp_password_store: TempPasswordStore = Depends(get_temp_password_store),
582: ) -> dict[str, str]:
```

(`src/mkobi/api/routes/admin.py:567-582`; the deprecated GET twin is `:542-558`, and the shared body
is `_retrieve_temp_password` at `:515-539`, which returns `{"temp_password": password}` at `:539`.)
The other 15 are distributed across `admin.py` (5), `users.py` (2), `dashboards_access.py` (2),
`dashboards_filters.py` (2), and one each in `dashboards_crud.py`, `filter_values.py`, `graphs.py`,
`layouts.py`, `processing_configs.py` and `client_errors.py`.

**Evidence** — Decorator census over the 13 route modules with a 450-character window per decorator
(Appendix C). The undeclared credential response is read at `admin.py:539` and `:582`. For contrast,
the same module declares `response_model=list[UserRead]` at `:47`, `response_model=UserRead` at `:79`
and `:156`, `response_model=list[RegistrationRequestItem]` at `:355` and
`response_model=SuccessResponse` at `:452` — so the omission is per-operation, not a house style.
The client's shape mirror is hand-written (`frontend/src/shared/types/api.types.ts`, 327 lines) and
contains no reference to `temp_password`, so the field name is discoverable only by reading the Python.

**Consequence** — The response that carries a cleartext one-time password is the response with no
declared shape, so the OpenAPI document publishes `{}` for it: no generated client type can carry the
field, and the repo's own hand-written mirror does not. Nothing filters the body, so a field added to
whatever the handler returns later reaches the client untyped. This is a widened-annotation finding
with a named consequence rather than a count: the bar the project set for itself is declared per
operation, and it is switched off on the two operations where an undeclared body carries a
credential.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**. Declare a
response model for both credential operations — a two-field Pydantic model carrying
`temp_password: str` — and add `response_model=` to both decorators. That puts the field in the
OpenAPI document, gives the client mirror something to match, and makes the credential response
filterable like every other. The remaining 15 operations are the same fix at lower stakes and are
worth doing in the same pass so the count reaches zero; `tests/test_temp_password_retrieval.py`
asserts the body by value, so a `response_model` that permits the same key breaks nothing.

### CQ-112 — The dashboard admin-bypass refusal is written four times, and the two inline copies return a different string from the shared dependency

**Severity** — LOW

**Zone** — "One rule, one home: whether exactly one implementation exists"

**Observation** — The access *decision* has exactly one home, which is the right shape:
`core/permissions.py::_check_access_with_session` loads the user, tests the role and returns:

```python
170:         # Admin bypass: admins can access any dashboard
171:         user_repo = UserRepository()
172:         user = await user_repo.get(id=user_id, db=db)
173:         if user and user.role == UserRole.ADMIN:
```

(`src/mkobi/core/permissions.py:170-173`.) The *wrapper* — the admin short-circuit plus the refusal —
is written four times. Two are shared dependencies (`deps.py:797` `require_dashboard_read_access`,
`:841` `require_dashboard_write_access`, `:885` `require_dashboard_admin_access`, and `:929`
`get_accessible_dashboard_ids` for the collection shape). Two are inline in the same route module,
and both re-derive the short-circuit and the refusal:

```python
367:     # Check resource-level access: admin role or edit permission on dashboard
368:     # Admin users bypass resource-level checks
369:     has_edit_access = False
370:     if current_user.role != UserRole.ADMIN:
371:         has_edit_access = await check_dashboard_access(
372:             user_id=current_user.id,
373:             dashboard_id=dashboard_id,
374:             db=db,
375:             required_permission=DashboardPermission.EDIT,
376:         )
377:         if not has_edit_access:
378:             logger.warning(
379:                 "Access denied for update: user_id=%s, dashboard_id=%s",
380:                 current_user.id,
381:                 dashboard_id,
382:             )
383:             raise AppException(
384:                 code=ErrorCode.PERMISSION_DENIED,
385:                 detail="You don't have access to this dashboard",
386:             )
```

(`src/mkobi/api/routes/dashboards_crud.py:367-386`; the delete twin is `:463-476`.) The shared
dependency's refusal for the same rule is a different string:

```python
878:         raise AppException(
879:             code=ErrorCode.PERMISSION_DENIED,
880:             detail="You do not have write access to this dashboard",
881:         )
```

(`src/mkobi/api/deps.py:878-881`.) Neither inline copy declares the dependency it reimplements: both
handlers take `current_user: CurrentUser`, which resolves to `get_current_user_dependency`
(`deps.py:976`), not to `require_dashboard_write_access` or `require_dashboard_admin_access`.

**Evidence** — Read of `core/permissions.py:152-212` (the decision), `api/deps.py:797-926` (the three
per-dashboard wrappers) and `api/deps.py:929-969` (the collection wrapper, whose docstring at
`:942-944` records why its bypass cannot arrive through `check_dashboard_access`). The inline copies
are read at `dashboards_crud.py:367-386` and `:463-476`; both handlers' signatures are
`current_user: CurrentUser` at `:337` and `:438`. The two detail strings are quoted above from
`dashboards_crud.py:385` and `deps.py:880`.

**Consequence** — Access is checked on every dashboard request, so no control is bypassed. The cost is
discoverability and a small divergence that already exists: a caller refused write access to a
dashboard receives "You don't have access to this dashboard" from `PUT /dashboards/{id}` and "You do
not have write access to this dashboard" from any route that uses the shared dependency, for the same
decision. A maintainer looking for "how is write access enforced on dashboard update" finds no
dependency on the handler and must read twenty lines of inline code; a change to the refusal wording
or the log message has to be made in four places. LOW because nothing is unprotected and the
divergence is cosmetic.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**. Replace the
inline blocks with the dependency that already exists and already carries the admin bypass:
`require_dashboard_write_access` on `update_dashboard_endpoint` and
`require_dashboard_admin_access` on `delete_dashboard_endpoint`. The `user_permission` computation at
`dashboards_crud.py:390` needs `has_edit_access`, so compute it after the gate from
`check_dashboard_access` rather than from the short-circuit — the two are not interchangeable, and
that is the one ordering detail to get right. Any test asserting the current refusal string for
`PUT /dashboards/{id}` must change with it; the string is a response body, not a contract anyone has
published.

### CQ-113 — `auth.py` is the only route that constructs its own repository, and the only one that names its session `session`

**Severity** — LOW

**Zone** — "Responsibility inside a unit: how many jobs one unit does, and which is reachable from elsewhere"

**Observation** — The refresh handler obtains its session from the container and then instantiates a
repository itself, bypassing the DI layer every other route uses:

```python
392: async def refresh(
393:     request: Request,
394:     response: Response,
395:     session: Annotated[AsyncSession, Depends(get_db_dependency)],
396:     redis_client: Any = Depends(get_redis_client_dependency),
397: ) -> Token:
```
```python
487:     user = await UserRepository().get(UUID(user_id), session)
```

(`src/mkobi/api/routes/auth.py:392-397`, `:487`.) `UserRepository` is imported at
`auth.py:35` and `deps.py:60`; the container exposes `get_user_repository` for this, and no other
handler in `api/routes/` calls a repository constructor. The parameter name is the same outlier: 58 of
the 59 route operations name the injected session `db`; this one names it `session`, which is why
`:487` reads `..., session)` where a reader's eye expects `..., db)`.

**Evidence** — Constructor census over `api/routes/*.py` for `Repository()` finds exactly one call
site, `auth.py:487`. The per-module injection census (Appendix C) shows every other route module
obtaining repositories through `Depends`. The parameter name is confirmed by the `Depends(
get_db_dependency)` signature census: `db: AsyncSession = Depends(get_db_dependency)` in
`dashboards_crud.py:186`, `:253` and elsewhere, against `session:` at `auth.py:395`.

**Consequence** — One route reaches past the container to a concrete repository, so the route's
dependencies are no longer visible in its signature and a test that overrides `get_user_repository`
does not affect the refresh path. Nothing breaks today — the concrete class is the same one the
container returns — but the handler is the one place in the route layer where the DI contract does not
hold, and the parameter naming makes the outlier invisible at a glance. LOW: the cost is
inconsistency, not a fault.

**Recommendation** — `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**. Add
`user_repo: UserRepository = Depends(get_user_repository)` to the signature and change `:487` to
`await user_repo.get(UUID(user_id), session)`. Renaming `session` to `db` is optional and would touch
the body at several sites, so it is worth doing only if the module is being read anyway — the
signature change is the part that matters, because it makes the dependency visible.

### CQ-114 — The shared temp-password handler documents that the full handle never reaches the access log; the deprecated path it also serves writes it there in full

**Severity** — MEDIUM

**Zone** — "Declared contracts and their enforcement point: whether anything checks the claim, and whether anything reaches it"

**Observation** — One docstring serves two operations and makes a claim that is true of one and false
of the other:

```python
519:     """Retrieve a temporary password by its retrieval token (one-time, admin only).
520: 
521:     Shared body for the deprecated GET and the POST. The caller must already have
522:     passed the admin dependency. Only the first eight characters of the handle are
523:     logged, so the full handle never appears in the application access log via a
524:     log line.
525:     """
526:     logger.info("Admin: retrieving temp password: token=%s...", retrieval_token[:8])
```

(`src/mkobi/api/routes/admin.py:519-526`.) The first clause holds: `:526` truncates to eight
characters. The second does not, for the GET. That operation carries the handle as a **path segment**:

```python
542: @router.get(
543:     "/temp-passwords/{retrieval_token}",
544:     status_code=status.HTTP_200_OK,
545:     summary="Retrieve temporary password (admin, deprecated)",
546:     description=(
547:         "Deprecated: the retrieval handle travels in the request line, where it "
548:         "can reach the access log. Use POST /admin/temp-passwords instead. Removed "
549:         "in release 1.0.9."
550:     ),
```

(`src/mkobi/api/routes/admin.py:542-550`.) The edge's access log records the path in full:

```nginx
21:     log_format mkobi_redacted '$remote_addr - $remote_user [$time_local] '
22:                               '"$request_method $uri $server_protocol" '
23:                               '$status $body_bytes_sent "$http_referer" '
24:                               '"$http_user_agent"';
25:     access_log /dev/stdout mkobi_redacted;
```

(`docker/nginx/nginx.conf.template:21-25`.) `$uri` is the path with the query string removed, not the
path redacted, so `GET /admin/temp-passwords/<handle>` writes the complete handle to `/dev/stdout`. The
route's own `description` at `:546-549` says so; the shared body's docstring two lines into the same
module says the opposite. The POST's own description at `admin.py:571-575` makes the same claim and is
correct for that operation, because the handle is in the body.

**Evidence** — Read of `admin.py:515-550` and `:567-582`; the truncation at `:526` and the
path-parameter declaration at `:543` are both quoted above. The edge format is read from
`docker/nginx/nginx.conf.template:21-25`; the `mkobi_redacted` name refers to the omitted query
string, and the rendered line includes `$uri` verbatim, which the template's own comment at `:19-20`
insists on preserving. The GET operation is reachable and not disabled: it carries
`deprecated=True` (`:552`) and its own deprecation note at `:549` schedules removal for release
`1.0.9`, while `pyproject.toml:7` declares `version = "1.0.8"`.

**Consequence** — The docstring a reader consults before touching either operation states a
guarantee the deprecated path does not provide, and it is the guarantee a security reviewer would
check. Truncating the application's own log record is real but irrelevant to the edge's, which is
where the handle actually lands. The removal is scheduled in a comment rather than tracked by
anything, so the window in which the claim is false is bounded only by a release number in prose. The
substantive exposure — a one-time credential handle in an access log — is phase 07's inbound-surface
question and phase 10's logging-posture question; what belongs to this phase is the contradiction
between the declaration and the path it runs on.

**Recommendation** — `[SPEC-DEVIATION]`, **priority: recommended**, **effort: trivial**, and the
documentation half is the whole of it. Split the claim so each operation carries a true one: state
the truncation as a property of the application log record (which it is) and drop the sentence
claiming the handle cannot reach the access log, or qualify it to the POST. Do not "fix" this by
changing the log format — redacting a path segment the edge must route on is phase 10's decision.
The durable remedy is to retire the GET, and the cheapest way to make its retirement date real rather
than aspirational is to delete the operation rather than schedule it; that is a deliberate product
decision about whether any caller still uses it, and phase 04 owns the caller census. **Remediation
blocker:** `tests/test_temp_password_retrieval.py` exercises the retrieval path; check whether it
covers the GET operation specifically before removing it.

## Distribution

The findings fall on five surfaces, and one carries the most. **Service and route wiring** holds four
(CQ-101, CQ-102, CQ-112, CQ-113) and is the densest: the declared API → Service → Repository direction
is intact in the dependency graph — zero `services/` → `api/` imports, zero `db/` → `services/`
imports, zero `api/`-importing `db/` modules (Appendix A) — but two of ten service layers have no
caller, so the direction is skipped at runtime in the two domains those services cover. **The
declared constant and configuration surface** holds three (CQ-103, CQ-105, CQ-107): two role-name
literals in raw SQL, one 32-member vocabulary mirrored by hand in four structures, one eight-value
response family with no home. **The gate and tooling surface** holds three (CQ-108, CQ-109, CQ-110):
two lint waivers that match nothing, an aggregate that omits two of its own gates, and two declared
thresholds that are not in force on the paths contributors are pointed at. **The error and response
boundary** holds two (CQ-106, CQ-111), and **declared contracts with no true enforcement point** holds
two across the start-up and the admin surface (CQ-104, CQ-114). Backend-only: no finding lands on
`frontend/src/`, whose type-safety bar the mechanical sweep found already met.

## Cross-Finding Analysis

Five findings share one cause, and it is the most consequential pattern in this phase: **a rule that
is written down in a discoverable place and enforced in a different one.** CQ-101's graph-name check,
CQ-102's password byte budget, CQ-104's `None` contract, CQ-112's refusal wrapper and CQ-114's
log-redaction claim are all cases where the copy or the claim a reader opens is not the one that runs.
The mechanism is uniform — the reachable copy is the one that was wired into a route, and the
discoverable copy is whichever one a later edit or a test file touched, or whichever docstring was
written for the operation that was added second — and it is why the fix for each is "move the rule,
or the claim, to the home that is actually executed" rather than "add a check". CQ-101 and CQ-102 also
share a second property worth naming: in both, the test suite is the reason the dead copy is
discoverable, so the green suite reads as coverage of a path production does not take.

CQ-109 and CQ-110 share a cause distinct from the first group: **a gate declared in configuration that
nothing invokes on the path a contributor actually walks.** The coverage floor, the `tests.*` mypy
override and the aggregate's own gate list are all in force somewhere and silent everywhere else, and
mypy reports one of them itself on every run. CQ-105 and CQ-108 are the same shape at a smaller scale —
declared structures (a vocabulary, a per-file ignore list) that nothing keeps in agreement with the
tree — and CQ-107 is the boundary case where a whole response family was built outside both the
constant and the error architecture.

## Roadmap

1. **Put each rule in the home that runs** — CQ-102, CQ-101, CQ-104, CQ-112, CQ-113, CQ-114. These are
   independent and none blocks another, but they share a review shape, so doing them in one pass lets
   a reviewer check one property — "is the copy or the claim I am editing the one that executes?" —
   six times. Start with CQ-102: it is the smallest edit (delete two functions, repoint one import) and
   it carries a credential rule. CQ-114 is the smallest of all and is documentation-only, so it can go
   first to remove a false guarantee from the tree. CQ-101 is the largest and is gated on a scope
   decision (adopt the services, or rule that the domains have none); make that call before starting
   it, not during.
2. **Close the configuration-to-runtime gaps** — CQ-103, CQ-105, CQ-107. CQ-103 is the only one with a
   silent-failure branch, so it goes first within the step; it needs no decision, only the parameter
   binding. CQ-105 needs a shape decision (derive the tables, or add the two membership assertions) and
   the assertions alone would close the correctness gap while the derivation is deferred. CQ-107 needs
   the 503 decision (conform, or record the exemption) before any code moves.
3. **Make the declared gates mean what they say** — CQ-110, CQ-109, CQ-108. CQ-110 first: it is two
   one-line configuration decisions and the checker already reports half of it. CQ-109 next, and its
   `Invoke-Test` half needs the decision about whether `check` may require the test stack. CQ-108 is
   independent of both and can be done at any point. The absence of an automated path is **not** in
   this sequence — it is a deployment-posture decision owned by phase 10, and CQ-109 records it
   without scheduling it.
4. **Declare the response shapes** — CQ-111. Independent of everything above; do it after step 1 so the
   credential operation's model is written once, and so CQ-114's deprecation ruling is known before the
   GET operation's response model is written at all. CQ-106 folds in here: it is the same two functions
   in `app.py` and the same decision about whether the health surface is inside the error contract.

## Rollout Safety

Steps 1 and 2 change observable behaviour, and two of the changes are behavioural in a way a
reviewer should announce rather than merge quietly.

**CQ-102 is the only step that can change an API response.** Deleting `validate_password` and
`validate_email` changes nothing at runtime, because neither has a production caller — but the
shipped tests assert both, so `tests/test_validators.py:76-109` and the thirteen `validate_email`
assertions must change with the removal or the project's "production code is the source of truth"
rule requires keeping the dead copies. Repointing `auth_service.py:38` at `validators.EMAIL_REGEX` is
the one edit that touches a live path; it is safe only if the import direction is right, which is why
the recommendation names the constraint (`validators.py` imports only `mkobi.models.enums`, and
`auth_service` is reached during `mkobi.config`'s import). Verify by asserting that a registration
with a malformed address is still refused — the existing auth tests cover this, so the gate is
already in place. Revert is a single-file revert of `validators.py` plus the import line.

**CQ-101 is a behaviour change disguised as a wiring change.** Routing the six handlers through the
services moves each `db.commit()` out of the handler and into the service, which changes when the
transaction boundary sits relative to the handler's remaining work, and it activates
`GraphService._validate_graph_data` for the first time — so a graph whose name is empty or whitespace
starts returning 422 where it previously returned 200 and stored the row. That is the intended
effect and it is worth announcing in the commit message. The exposure to check before merging: any
client flow that creates a graph with a blank name will start failing, and there is no route-level test
for `POST /dashboards/{id}/graphs`, so the suite will not catch a regression here. Revert is a revert
of the handler signatures; no stored row is rewritten, and the graph names already persisted as blank
are a separate operator question this change does not address.

**Steps 3 and 4 are configuration and declaration work with no runtime effect**, except that CQ-110's
choice between measuring coverage on every run and only on `test-all` changes how long `test` takes,
and CQ-106's replacement of `AppException` for `HTTPException` at `app.py:584` must be verified to
produce the same status and `code` on the wire — the registered handlers differ in their `logging`
level, so the log volume for unmatched `/api/` paths will change. Check that with one request to a
nonexistent `/api/` path before and after.

## Appendices

### Appendix A — Convention sweep: corpus and result

Each rule was swept mechanically over its whole population, so a rate is not mistaken for a method.

| Rule | Corpus | Result |
|---|---|---|
| `print()` on a production path | every `.py` under `src/` | **0 occurrences.** No finding. |
| Hardcoded error-code strings | `code="UPPER_SNAKE"`, `error_code="…"` over `src/` | **0 occurrences**; 42 `raise AppException` sites plus 1 `raise` of a named subclass, all typed via `ErrorCode`. No finding. |
| `HTTPException` raised directly | `src/mkobi/**.py` | 0 imports of FastAPI's `HTTPException`; **1** use of Starlette's, `app.py:584`. Filed as CQ-106. |
| Bare `except:` / `except Exception` swallowing without logging | 50 handlers in `src/` | 49 log before returning or raising. **1** silent: `starter.py:217`. Filed as CQ-104. |
| `any` / `@ts-ignore` / `@ts-expect-error` in `frontend/src/` | all `.ts`/`.tsx` | **0** `: any`, `as any`, `@ts-ignore`, `@ts-expect-error`. 1 production `as unknown as` at `chartConversion.ts:127`, with the reason recorded at `:116-124`; the other 9 are in `__tests__`/`.test.tsx`. No finding. |
| `tsconfig` strictness | `tsconfig.app.json` | `"strict": true` at `:3`; `noUnusedLocals` and `noUnusedParameters` at `:20-21`; no path-scoped relaxation. No finding. |
| Non-English text in code, comments, logs, docstrings | `src/mkobi/**.py` | **1** site, `filter_service.py:299`, and it is a Cyrillic range inside a regex character class, in a module CQ-101 establishes is unreachable. Not filed. |
| Untyped definitions | `src/` | `uv run mypy src/ --disallow-untyped-defs` → **0 errors in 120 files**. `pyproject.toml:157` sets `disallow_untyped_defs = false`, so the relaxation currently has an empty population; recorded, not filed. |
| Layer direction | `src/mkobi/{services,db,data,workers}` | `services/` → `api/`: 0. `db/` → `services/` or `workers/`: 0. `db/` → `api/`: 0. `data/` → `services/` or `api/`: 0. `workers/` → `api/`: 0. No finding; the only layering defect is the runtime skip in CQ-101. |
| StrEnum violations on status/type comparisons | `src/mkobi/**.py` | 8 bare `"float"`/`"date"`/`"int"`/`"str"`/`"bool"` comparisons at `workers/data_worker.py:714-759`. These are Polars dtype names, an external vocabulary with no `StrEnum` in `models/enums.py`, and the code that reads them is phase 05's. Not filed. |
| Declared guarantees contradicted by the path that runs | docstrings and comments across `src/mkobi/**.py` | 1 found, `admin.py:522-524`. Filed as CQ-114. The two other declared-contract items the earlier decomposition recorded are already remediated per `docs/SPEC.md:245-246` (`ButtonVariant`/`ComponentSize` are now documented as unenforced; the collection-route admin bypass now resolves through `deps.py:929`). |
| `alembic/versions/` outside both gates | `pyproject.toml:169`, `Makefile.ps1:262`, `:270` | Already filed as `TOPO-106`. Not re-filed. |
| `pandas-stubs` for a forbidden library | `pyproject.toml:219` | Already filed as `TOPO-114`. Not re-filed. |
| `/api/v1` prefix as eleven literals | `src/mkobi/app.py:361-371` | Already filed as `CFG-113`. Not re-filed. |
| `ButtonVariant` / `ComponentSize` unreferenced | `models/enums.py:167`, `:180` | Zero code references beyond `models/__init__.py`. `docs/SPEC.md:118` and `docs/09-database/enums.md:371`, `:386` now state explicitly that the server does not enforce them and that validation is "a stated intent, not a capability", with the open half assigned to the Product Owner. The documentation half of the earlier `QLT-009` is closed; not re-filed. |
| `redirect_slashes=False` on routers | `api/routes/*.py` | The inert declarations are gone; `docs/SPEC.md:246` records the removal and the deliberate application-level alternative. Not re-filed. |

### Appendix B — Gate inventory

| Gate | Declared at | Reachable how | Wired into `check`? | Automated path? |
|---|---|---|---|---|
| ruff | `Makefile.ps1:261-263` | `.\Makefile.ps1 lint` | yes (`:282`) | none |
| mypy | `Makefile.ps1:269-271` | `.\Makefile.ps1 typecheck` | yes (`:284`) | none |
| eslint | `Makefile.ps1:273-275` | `.\Makefile.ps1 fe-lint` | yes (`:286`) | none |
| vitest | `Makefile.ps1:277-279` | `.\Makefile.ps1 fe-test` | yes (`:288`) | none |
| pytest | `Makefile.ps1:227-230` | `.\Makefile.ps1 test` | **no** — CQ-109 | none |
| pytest + coverage | `Makefile.ps1:232-235` | `.\Makefile.ps1 test-all` | **no** | none |
| `alembic check` | `Makefile.ps1:315-317` | `.\Makefile.ps1 migration-check` | **no** — CQ-109 | none |
| `npm run build` (`tsc -b && vite build`) | `frontend/package.json` | `npm run build` from `frontend/` | **no** | none |

Both backend gates were executed on this tree and are green: `uv run ruff check src/ tests/
alembic/env.py` → `All checks passed!`; `uv run mypy src/ alembic/env.py` → `Success: no issues found
in 121 source files`, preceded by `pyproject.toml: note: unused section(s): module = ['tests.*']`
(CQ-110). Because the baseline is green, no finding in this report uses gate redness as its premise.

### Appendix C — Derived counts

| Count | Value | Method |
|---|---|---|
| Route decorators in `api/routes/` | 59 | regex over all 13 route modules |
| …without a `response_model` | 17 | per-decorator 450-character window; CQ-111 |
| Service factories in `api/deps.py` | 10 | `def get_*_service` |
| …named by no route file | 2 | `get_filter_service`, `get_graph_service`; CQ-101 |
| Repository-injected parameters in `api/routes/` | 9 across 3 modules | `(\w+_repo\w*):\s*\w*Repository\s*=\s*Depends\(`; CQ-101 |
| Repository constructors called in `api/routes/` | 1 | `Repository()`; `auth.py:487`; CQ-113 |
| `-> Any` provider annotations left in `deps.py` | 1 | `deps.py:147`; the ten at `:168-258` are gone |
| `dict[str, Any]` / `list[dict[str, Any]]` in `src/` | 107 | CQ-111 is the named consequence, not the count |
| `Any` in `src/mkobi/interfaces/` | 51 (33 `repository_interfaces.py`, 18 `service_interfaces.py`) | inside the two modules `pyproject.toml:175-181` sets `ignore_errors = true` for |
| `ErrorCode` members / status-map rows / title rows | 32 / 32 / 32 | CQ-105 |
| `mkobi_app` literal occurrences in `src/` | 13 (7 in SQL literals, 4 in text, 1 configured) | CQ-103 |
| Health status literals in `app.py` | 8 | `:385`, `:391`, `:408`, `:419`, `:426`, `:428`, `:438`, `:452`, `:461`; CQ-107 |
| CI paths checked | 8, all absent | `.github`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `.circleci`, `.gitea`, `.woodpecker.yml`, `Jenkinsfile`, `.pre-commit-config.yaml`; CQ-109 |
| `src/mkobi/interfaces_old` | does not exist | `Test-Path`; CQ-108 |
| `Depends` / `fastapi` in `core/permissions.py` | 0 | CQ-108 |

### Appendix D — Method and limits

**Verified by execution on this tree:** `uv run ruff check src/ tests/ alembic/env.py` (`All checks
passed!`); `uv run mypy src/ alembic/env.py` (`Success: no issues found in 121 source files`, plus the
unused-section note); `uv run mypy src/ --disallow-untyped-defs` (`Success: no issues found in 120
source files`). All read-only; no repository file was modified other than this report.

**Verified by reading, not by execution:** every finding. The unreachability claims (CQ-101, CQ-102,
CQ-113) are static: a caller census over `src/mkobi/**.py` and `tests/*.py` for each symbol, reported
in full in Appendix C. CQ-103's fail-open branch, CQ-104's swallowed exception, CQ-105's four
structures and CQ-107's eight literals are read from the cited lines. No container was started and no
request was issued.

**Not verified, and why.** The 405-label claim inside CQ-105 — that a wrong method on a declared path
produces a body with `code=INTERNAL_ERROR` — is derived from Starlette's routing behaviour
(`Route.handle` raises `HTTPException(405)`) and from the handler's default branch at
`exceptions.py:330`, not from an observed response; this pass did not bring up the dev stack. The
claim is stated as a derivation and the recommendation does not depend on it. CQ-102's claim that the
two password copies disagree rests on reading both bodies, not on submitting an over-budget password
to each; phase 04 established the reachable copy's behaviour directly and the finding only asserts
that the *other* copy lacks the clause. CQ-111's response-model census uses a 450-character window
per decorator, which is sufficient for every decorator in these 13 modules but is a heuristic and not
a parse; the 17 undeclared operations were each confirmed by reading their decorators.

**Not in scope, recorded so it is not lost.** CQ-114 stops at the declaration: the exposure of a
one-time credential handle in the edge access log is phase 07's inbound-surface question and phase
10's logging-posture question, and this finding claims only that the docstring's guarantee does not
hold on the path the deprecated operation takes. Nothing else in this phase's scope was deferred for
ownership reasons.

### Appendix E — Concurrency note

The working tree was dirty at write time under `frontend/src/shared/types/api.types.ts`,
`src/mkobi/api/routes/data.py`, `src/mkobi/db/repositories/aggregated_data_repo.py`,
`src/mkobi/interfaces/service_interfaces.py`, `src/mkobi/models/dashboard.py`,
`src/mkobi/models/data.py`, `src/mkobi/services/data_service.py`, `tests/test_dashboards_api.py`,
`tests/test_filter_payload_bounds.py`, `tests/test_openapi.py` and `.ai/plans/16-phase16-residual-execution.md`.
No finding in this report cites any of those files except `frontend/src/shared/types/api.types.ts`
(CQ-111, cited for its size and for the absence of a `temp_password` reference, both of which are
stable properties of the file rather than line anchors), and every other citation was re-read at the
cited line immediately before this report was written. `HEAD` was `0ae6ddf`.
