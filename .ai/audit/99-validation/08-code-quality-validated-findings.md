---
phase: 08-code-quality
executed: 2026-10-05
executor: validator
problems-only: true
findings: 15
by-severity:
  CRITICAL: 0
  HIGH: 2
  MEDIUM: 10
  LOW: 3
---

# Phase 08 — Validated Findings

## Summary

The input's evidence base is the strongest of any phase validated so far: **not one of the 71
distinct code citations opened in this pass was stale or non-resolving**, at a tree that has moved
two commits (`0ae6ddf` → `7568a21`) past the baseline the report declares. Both backend gates were
re-executed and reproduce byte-for-byte — `uv run ruff check src/ tests/ alembic/env.py` →
`All checks passed!`, `uv run mypy src/ alembic/env.py` →
`Success: no issues found in 121 source files`, preceded by
`pyproject.toml: note: unused section(s): module = ['tests.*']` — so no finding rests on a red
baseline. Six of the eight inherited negative sweeps reproduce exactly: `print()` in `src/` = 0,
FastAPI `HTTPException` imports = 0, hardcoded error-code strings = 0, untyped defs = 0 in 120 files
under `--disallow-untyped-defs`, `any` / `@ts-ignore` / `@ts-expect-error` in `frontend/src/` = 0 with
`strict: true` at `tsconfig.app.json:3` and no path-scoped relaxation, and layer direction clean in all
five directions. Two sweeps are false and are filed as `VAL-08-011`.

Of the three HIGHs, one is confirmed and one is confirmed with its scope **corrected upward**
(`CQ-101` → `CQ-101a`/`CQ-101b`), one is confirmed with a **false consequence clause refuted**
(`CQ-102`), and one is **re-graded down** to MEDIUM (`CQ-103`): the fail-open branch is real and
reproduces, but it needs a non-default configuration to reach and its consequence — a warning that
does not fire, plus a role-existence probe that grants nothing — is below the phase rubric's HIGH
band, which grades by *effect and blast radius, not mechanism*. Two MEDIUMs are re-graded to LOW, one
MEDIUM is split with its coverage half rejected as a duplicate of an already-validated finding, and
one MEDIUM (`CQ-111`) is corrected on a claim that execution refutes. `CQ-114` is corrected to LOW:
its evidence seam is the same one already validated as tracked open work as `C04-5`, and the
docstring sentence it attacks is scoped to the application's own log line and is therefore true.
---

## Findings

Re-derived from the executing path alone. The audited phase's identifiers are preserved verbatim and
never renumbered; one identifier (`CQ-101`) is split into two suffixed halves because its title claims
two domains whose defects have different mechanisms, different bands, and different owners.

### CQ-101a — The graph domain writes and commits inside two route handlers, so the only non-empty-name rule in the domain has no reachable caller

**Verdict** — CORRECTED (split, re-scoped upward) · **Final severity: HIGH** (band unchanged)

**Zone** — "Responsibility inside a unit: how many jobs one unit does, and which is reachable from elsewhere"

**Observation** — The unreachability claim is **confirmed and is not destroyed by any missed call
site**. An independent census of every reference to `GraphService`, `FilterService`, `graph_service`
and `filter_service` across `src/`, `tests/`, `alembic/` and `frontend/` returns references in exactly
three production files: `api/deps.py` (the two DI factories, their `__all__` entries, and the
in-body imports), `services/graph_service.py` and `services/filter_service.py` themselves, and
`interfaces/__init__.py` / `interfaces/service_interfaces.py`. **No route file names either factory.**
Of the ten `def get_*_service` factories in `api/deps.py` (`:305`, `:324`, `:340`, `:357`, `:372`,
`:387`, `:402`, `:417`, `:432`, `:447`), the eight that routes do name are
`get_auth_service`, `get_user_service`, `get_dashboard_service`, `get_filter_values_service`,
`get_layout_service`, `get_processing_config_service`, `get_processing_log_service`,
`get_data_service`. `get_filter_service` (`:357-359`) and `get_graph_service` (`:387-389`) are the
only two, and both are named in `__all__` at `:104` and `:107`.

The consequence reproduces exactly as filed for the path the report named:

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

(`src/mkobi/api/routes/dashboards_graphs.py:97-106`; `graph_repo` injected at `:68`, zero services
injected by either handler in the module.) The unreachable rule:

```python
64:         if not data.name or not data.name.strip():
65:             raise ValueError("Graph name cannot be empty")
```

(`src/mkobi/services/graph_service.py:64-65`, inside `_validate_graph_data`, whose only caller is
`GraphService.create` at `:94` — itself unreachable.) The boundary declares no counter-rule:

```python
44: class GraphBase(BaseModel):
45:     """Base model for charts."""
46: 
47:     name: str
48:     type: GraphType
```

(`src/mkobi/models/graph.py:44-48`.) `GraphCreate` (`:69-89`) adds `extra="forbid"` and a
`config`-key validator at `:85-89`; neither constrains `name`. The column is
`String(255), nullable=False` with no `CHECK` (`src/mkobi/db/models/graphs.py:50-53`); the only
integrity on the column is the unique index `idx_graphs_dashboard_name` at `:105`. So `""` and
whitespace-only names are accepted at the boundary and committed.

**Correction — the scope is larger than filed, not smaller.** The report attributes the graph
write-through to one module and "the six endpoints of those two domains". There is a **second**
graph-create path the census missed, because it does not *inject* a repository — it calls the
container factory inside the handler body:

```python
114:         graph_repo = get_graph_repository()
115:         result = await graph_repo.create(
116:             db=db,
117:             name=graph.name,
...
124:         await db.commit()
```

(`src/mkobi/api/routes/graphs.py:114-124`, in `create_graph_endpoint`, declared at `:50` with the
signature at `:66`; the same inline `get_graph_repository()` at `:201`, `:260`, `:347`, `:457`.) The
graph domain therefore spans **two route modules and seven endpoints** (`graphs.py` 5 operations,
`dashboards_graphs.py` 2), and the graph name crosses **two independent commit sites**. That is why
the report's Appendix C row "Repository-injected parameters in `api/routes/` | 9 across 3 modules …
no other route module injects a repository at all" is true as written and misleading as a census: it
counts `Depends`-shaped declarations only, and therefore omits five inline repository acquisitions.
The real repository-acquisition population in `api/routes/` is **14 across 4 modules**.

**Correction — the remediation blocker is false.** `tests/test_deps.py:442-446` is **not** "the only
thing currently covering the graph service". `tests/test_graph_service.py` is **253 lines with 17
tests**, including `test_create_graph_empty_name_raises` (`:77`) and
`test_create_graph_invalid_type_raises` (`:91`) — the two that exercise `_validate_graph_data`
directly, the first through `graph_service.create` (`:89`), the second through the validator itself
(`:94`). `tests/test_services_integration.py:279-476` adds **38 further tests** covering
`GraphService` (`:282-405`) and `FilterService` (`:411-475`) against a live database, and six more
test modules construct `GraphService(GraphRepository())` as a fixture builder
(`tests/test_aggregate_row_caps.py:41`, `tests/test_aggregated_read_path.py:64,123`,
`tests/test_data_endpoint.py:66,116`, `tests/test_data_service.py:318,345,891,948,1052-1054,1061,1163`,
`tests/test_filter_payload_bounds.py:395`, `tests/test_filter_persistence.py:56`,
`tests/test_filter_values_consistency.py:57`). `tests/test_deps.py:442-446` is a two-line
`isinstance` check on the factory's return type and is the *weakest* of the coverage, not the only
coverage. The consequence is favourable to the finding: routing the handlers through `GraphService`
is **not** blocked by test coverage, and the report's warning that "a reviewer should not read the
green suite as evidence that the service works" is unfounded — `test_graph_service.py` is direct
unit coverage of precisely the code the route would begin to call.

**Evidence** — Static proof by exhaustive reference census (no `src/` caller of either service, no
route naming either factory) plus an AST sweep of every `@router.<method>(` decorator in
`src/mkobi/api/routes/` counting `Depends`-injected repository/service parameters:
`dashboards_filters.py` 6/0, `dashboards_graphs.py` 2/0, `data.py` 1/1, and no other module injects
either — matching the report's Appendix C exactly. The inline-acquisition half
(`graphs.py:114,201,260,347,457`) is found by symbol search for `get_graph_repository()` in the
handler bodies. Test population derived by counting `def test_` in each cited file.

**Consequence** — Two of ten declared service layers are off every request path. For the graph
domain the gap is behavioural and reachable today: `graphs.name` has **no** effective non-empty rule
on any of its seven endpoints, and the write is committed by handler code rather than by the unit
that owns the use case. Nothing else about the layer is a live fault — the other 12 methods of
`GraphService` duplicate correct repository behaviour.

**Recommendation** — Executable as filed; two corrections to its blockers. Adopt the services
(`graph_service: GraphService = Depends(get_graph_service)` on the seven graph handlers,
`filter_service: FilterService = Depends(get_filter_service)` where a filter write exists) and move
each `db.commit()` into the service. Drop the report's `tests/test_deps.py:442-446` blocker note and
replace it with the real one: `tests/test_graph_service.py` and
`tests/test_services_integration.py::TestGraphServiceIntegration` both assert current service
behaviour and will need re-reading if `create` gains the commit it already owns. Independently of
which shape is chosen, give `GraphBase.name` a `min_length=1` at `models/graph.py:47` — the boundary
should not depend on a service being wired for the rule to hold, and this edit alone closes the
reachable half.

---

### CQ-101b — `FilterService` and `IFilterService` survived the retirement of their own domain's HTTP surface

**Verdict** — CORRECTED (re-scoped, re-graded down) · **Final severity: MEDIUM** (filed HIGH)

**Zone** — "Convention compliance: the cheap high-volume rules, and which of them are broken" (block 7,
whose evidence clause requires "the unreferenced-definition list with the intent of each"). The
input filed this half under block 5; per block 7's own text, "code that is present, reachable and
referenced by nothing, where the question is what it was for rather than whether to delete it", the
mechanism is dead code with an established intent, not an unreachable layer.

**Observation** — The input's framing is "the graph and filter domains run route-to-repository". For
the filter domain that is **false, and the truth is a different defect**. `dashboards_filters.py`
holds three handlers — `bind_filter_endpoint` (`:48`), `unbind_filter_endpoint` (`:118`),
`get_dashboard_filters_endpoint` (`:183`) — which are the *binding* domain, and a binding operation
legitimately touches repositories. The filter **CRUD** domain has no route at all:

```python
1: """Placeholder module for filters routes - CRUD endpoints removed.
2: 
3: The global filter CRUD endpoints (/api/v1/filters) have been removed as they were
4: orphaned - no frontend code consumed them. Filter-binding functionality for dashboards
5: remains in dashboards_filters.py and uses FilterRepository directly.
6: """
```

(`src/mkobi/api/routes/filters.py:1-6`, the entire file.) The removal is a **recorded ruling**, not an
accident: `docs/02-dashboards/dashboards-api.md:526-527` states "**The global filter CRUD routes are
removed.** Endpoints 16–20 below (`GET/POST/PUT/DELETE /api/v1/filters`) no longer exist: they were
orphaned", and `docs/11-guides/create-dashboard.md:239` repeats it. So `FilterService` is
unreachable because **its domain was deliberately retired**, and `services/filter_service.py` (331
lines, 6 public methods), `interfaces/service_interfaces.py::IFilterService` (`:387`) and its public
export at `interfaces/__init__.py:24,45` all outlived the retirement.

A search of every reference confirms the consequence: `FilterRepository` in `src/` resolves only at
`api/deps.py:230-237`, the two imports and three `Depends` uses in `dashboards_filters.py`
(`:53`, `:124`, `:187`), the class definitions, and the interface module. The only production read of
a filter row is `dashboards_filters.py:79` inside the bind handler. **No route creates, updates or
deletes a filter.**

**Evidence** — The stub file read in full; the ruling quote read at
`docs/02-dashboards/dashboards-api.md:526-527`; a symbol census of `FilterRepository` /
`get_filter_repository` / `FilterCreate` across `src/mkobi/api/routes/` returning only the binding
uses. `FilterBase.name: str` (`src/mkobi/models/filters.py:12`) is likewise unconstrained and
`filters.name` is `String(255), nullable=False` (`db/models/filters.py:41-44`), so
`_validate_filter_name`'s three rules (`services/filter_service.py:291-297`) are unreachable **and**
currently unreachable in fact — no HTTP path writes a filter row, so the gap is latent rather than
live.

**Consequence** — 331 lines of service, one published ABC and one public export name remain after the
domain they served was retired by decision. A reader of `deps.py::get_filter_service`, of
`__all__`, or of `interfaces/__init__.py` sees a first-class service with a live-looking DI factory
and no route. The cost is discoverability and a standing invitation to reintroduce a surface the
project already ruled out; it is not a behavioural fault, which is why the band is MEDIUM and not
HIGH. The latent `FilterBase.name` gap becomes live the moment any filter write route is added.

**Recommendation** — Two decisions, both small, neither a code change today. Delete
`services/filter_service.py`, `IFilterService` and its export, and `get_filter_service` with its
`__all__` entry — the retirement ruling already answers the question the report asked. If the service
is kept deliberately as the future home of a filter surface, record that in
`deps.py::get_filter_service`'s docstring and in `docs/STRUCT.md`, so the next reader does not have to
re-derive the history. Given `filter_service.py:299` is also the tree's only Cyrillic-regex site,
removal closes that too.

---

### CQ-102 — The email-format and password-strength rules each have two implementations, and the two password copies already disagree

**Verdict** — CONFIRMED, with one false clause in the Consequence refuted · **Final severity: HIGH** (band unchanged)

**Zone** — "One rule, one home: whether exactly one implementation exists"

**Observation** — Every citation resolves exactly. `validators.py:16` and `auth_service.py:38` are
byte-identical:

```python
16: EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
38: EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
```

`auth_service.py:98` reads it inside `_validate_email_format` (`:86`), called from `:144`;
`validators.py:38` is read only by `validate_email` (`:19`), which has **zero** callers in `src/` — the
only other references are its own two doctests at `:29`/`:31` and `tests/test_validators.py:17,32-72`.

The password divergence is exactly as filed:

```python
145: def validate_password(password: str, min_length: int = 8) -> bool:
183: def validate_password_or_raise(password: str, min_length: int = 8) -> None:
221:     if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
222:         raise ValueError(
223:             f"Password is too long: at most {MAX_PASSWORD_LENGTH} bytes are allowed"
224:         )
```

`validate_password` ends at `:180` after the digit and letter checks and carries no byte clause;
`validate_password_or_raise` carries it at `:221-224` and documents the reason at `:186-197`
(bcrypt cannot represent more than `MAX_PASSWORD_LENGTH` bytes, so a longer value would be silently
truncated at mint time). The budget is real, not theoretical: `core/security.py:38`
`MAX_PASSWORD_LENGTH: int = 72` and `_truncate_password` (`:166-199`) truncates at a character
boundary before hashing (`:220`) and before verification (`:248`).

Reachability census: `validate_password_or_raise` has **7** production call sites —
`models/auth.py:136,225`, `models/user.py:46,128,154`, `auth_service.py:145,588` — matching the
report. `validate_password` has **0** production callers and 9 test call sites
(`tests/test_validators.py:80,84,88,92,96,100,104,108,109`).

**Refuted clause.** The Consequence asserts: "the copy a reader finds first, and the copy the only
test file exercises, is the one that does not run; **the copy that does run is the one with no
test**." The second half is **false**. `tests/test_validators.py` carries two whole classes for the
reachable copy — `TestValidatePasswordOrRaise` (`:237-266`, five tests) and `TestPasswordByteBudget`
(`:269-303`, three tests, annotated `SECB-10`), the last three exercising exactly the clause the
dead copy lacks: a 72-byte ASCII password accepted (`:276-280`), a 73-byte password refused
(`:282-290`), and a 72-character/141-byte multibyte password refused (`:292-303`). The reachable copy
is the *better*-tested one. The report's other count in the same sentence, "its five call sites are
all in `tests/test_validators.py:76-109`", is 9, not 5.

**Evidence** — Both bodies read in full (`validators.py:145-180` and `:183-226`); caller census over
`src/`, `tests/` and `alembic/`; the truncation mechanism read at `core/security.py:166-199`.

**Consequence** — The credential-strength rule has no single discoverable home, and the two copies
differ on a value the system acts on: only the reachable copy enforces the bcrypt byte budget, so
the divergence already exists. The specific failure the report predicts is therefore **not** "a
maintainer edits the untested copy" — they would edit `validate_password` because that is where the
tests are, but the tests are nine trivial shape assertions while the enforced copy has eight
including the byte budget. The real failure mode is narrower and worth stating precisely: a future
tightening of the rule written into `validate_password` (the only copy whose name matches its
behaviour) would be invisible to production **and** would add a ninth shape test that passes.

**Recommendation** — Executable as filed, with the blocker corrected. Delete `validate_password` and
`validate_email`; repoint `auth_service.py:38` at `validators.EMAIL_REGEX`. The import direction is
safe as the report states — `validators.py:11` imports only `mkobi.models.enums`, and
`auth_service` is reached during `mkobi.config`'s import. Replace the stated blocker
(`tests/test_validators.py:76-109`, nine assertions on the dead copy) with the true one: the eight
assertions at `:237-303` cover the copy being kept and must be *extended*, not changed — when
`validate_password` disappears, the four shape assertions at `:80-104` migrate to
`validate_password_or_raise` and duplicate `:242-266` exactly, so the net suite shrinks by five and
the byte-budget coverage must be left intact.
---

### CQ-103 — The application role name has two homes, and the raw-SQL one silently disables the least-privilege check

**Verdict** — CONFIRMED, re-graded down · **Final severity: MEDIUM** (filed HIGH)

**Zone** — "Fixed values: one named home per value, and what bypasses it"

**Observation** — Every citation resolves and the literal census is exact: **13** `mkobi_app`
occurrences in `src/`, of which 7 sit inside executable SQL, 4 are log/docstring text, and 1 is the
configured default.

```python
254: class DatabaseSettings(BaseModel):
255:     """Database connection settings."""
256: 
257:     host: str = "localhost"
258:     port: int = 5432
259:     dbname: str = "bidb"
260:     user: str = "mkobi_app"
```

(`src/mkobi/config.py:254-260`.) The seven SQL sites are `db/starter.py:392` (inside `DDL(...)`,
`GRANT CONNECT`), `:420`, `:422`, `:424`, `:426`, `:427` (all inside `text(...)`), and `:579`
(`SELECT`). The fail-open branch reproduces exactly:

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

(`src/mkobi/db/starter.py:577-586`; docstring "defense-in-depth" at `:574`; called on the start-up
path at `:249`.) A `SELECT` against `pg_roles` for an absent role returns zero rows, `fetchone()`
yields `None`, `if row and row[0]` is False, and the function returns having emitted nothing. **The
failure mode is confirmed.**

**Evidence** — Read at the cited lines; `13`-occurrence census reproduced exactly; the branch
semantics derived from the SQL and the `if row` guard. `_verify_role_privileges` has exactly one
caller (`:249`) and no test covers it.

**Consequence, and why the band moves** — In the declared default configuration the check runs and
works; the fail-open branch requires `DATABASE__USER` to name a role other than `mkobi_app`, which is
a supported but non-default deployment. What the operator loses there is **one warning line**. It is
not a privilege escalation and not an authentication bypass: the query selects a single boolean
column and grants nothing, and `_verify_role_privileges`'s return value is discarded at `:249`. The
`recreate_test_database` half is the one with a visible failure, and that half does **not** fail open —
a role that does not exist makes `GRANT` raise `UndefinedObjectError`, caught at `:432-435`, which
logs at `error` and re-raises. Under this phase's rubric — "Grade by **effect and blast radius**, not
by mechanism name; rate what is true now, not the worst consequence if triggered" — a diagnostic that
silently answers "clean" is a real operability defect on a specific configuration, which is the
MEDIUM band's "bounded correctness or operability gap", not HIGH. The HIGH band requires that "the
next change is guaranteed to be made wrongly in the same place"; here the next change — a maintainer
reading `DatabaseSettings.user` and trusting the grant statements — is possible but not guaranteed,
because the literals are visible in the same file.

**Recommendation** — Executable and correct as filed; the parameter-binding half is unchanged and
`DDL(... context={...})` at `:392` is the pattern already established in the function. The
`if row is None:` warning the report adds is the half that carries the whole finding and should land
first — it is a three-line edit with no schema consequence. Note one constraint the report does not
name: `recreate_test_database` runs against the **admin** connection, so the role it grants must be
the *application* role read from `self._config`, not the admin role at `config.py:264`; binding
`user` and `admin_user` to the same name would break the grant.

---

### CQ-104 — `_get_alembic_revision` returns "schema not initialized" for every possible fault, and its sweep claim is false

**Verdict** — CONFIRMED, with a false Evidence claim corrected · **Final severity: MEDIUM** (band unchanged)

**Zone** — "Declared contracts and their enforcement point: whether anything checks the claim, and whether anything reaches it"

**Observation** — The defect and every citation resolve:

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

(`src/mkobi/db/starter.py:201-205`, `:217-218`; the `try` spans `:208-216` and issues
`SELECT version_num FROM alembic_version LIMIT 1` at `:212`.) Its single caller turns that `None`
into a start-up abort at `:251-256`, naming the wrong remedy for a permission denial or a refused
connection. There is no log record anywhere in the function, and the default level is `INFO`
(`src/mkobi/core/logging_config.py:73`), so even a `debug` record would not surface in a default
deployment.

**Refuted clause.** The Observation states this is "the only bare `except:` in `src/` that emits **no
log record at all** — all 49 other `except Exception` handlers in the tree log before returning or
raising", and Appendix A gives the corpus as "50 handlers in `src/`". An AST sweep over every
`except` handler in `src/` finds **323 handlers, of which 54 are silent**. The 53 others are: 30
`except AppException: raise` pass-throughs (`dashboards_graphs.py:114`, `dashboards_filters.py:91,159`,
`graphs.py:126,288,405,493`, `layouts.py:289,394,465`, `admin.py:245,339,440`, and 13 more); 15
deliberate `ValueError` → `AppException` translations that *do* name an error code in the raise
(`dashboard_service.py:58,150`, `aggregation_service.py:44`, `formula_parser.py:48`,
`data_worker.py:103,174`, `exceptions.py:111`, `upload.py:84,267,270`, `client_errors.py:44`,
`config.py:43`, `startup.py:66`, `rq_worker_wrapper.py:185`, `filter_service.py:94`); 1
`except asyncio.CancelledError` (`app.py:236`); 1 `except HTTPException` (`app.py:577`); 1
`except TempPasswordStoreUnavailableError` (`admin.py:529`); 1
`except PermissionDeniedException` (`dashboards_crud.py:300`); and 5
`except (RedisError, OSError, TimeoutError)` in `core/reconciler_lease.py:141,184,197,228,253`. The
Observation and Appendix A also disagree with each other about the size of the corpus, and both
disagree with the tree.

**Evidence** — The cited lines read directly; the handler census produced by AST walk over
`src/**/*.py`, classifying each handler's body for a `logger.*` attribute access.

**Consequence** — Unchanged and confirmed: a start-up failure from any cause is reported as
`SchemaNotFoundError: Database schema not initialized - no alembic revision found`, the remedy that
message implies does not clear it, and nothing in the process names the real fault. The false sweep
does **not** create a missed finding — all 53 other silent handlers are either deliberate re-raises,
deliberate translations that name an `ErrorCode` at the raise, or documented decisions whose outcome
is observable: the five `reconciler_lease.py` handlers each carry an explanatory comment and return
a distinct lease state (`UNREACHABLE` at `:143`, `UNPROTECTED` at `:186,198,229,254`) that
`/health/detailed` publishes at `app.py:479-486`. That is why the error is filed against the report's
evidence rather than against the tree.

**Recommendation** — Executable as filed. `except Exception as e:` + `logger.warning("Could not read
alembic_version: %s", e)` + `return None` is the whole change and preserves the abort. The report's
alternative — raising on the read and letting `_check_db_connection` (`:242`) own connectivity —
changes start-up ordering and is correctly deferred; note that adopting it would make the
`SchemaNotFoundError` message *more* accurate, since the only remaining `None` would then be the
genuine "table absent" case.

---

### CQ-105 — One 32-member vocabulary is maintained by hand in four structures, and every miss is silent

**Verdict** — CONFIRMED · **Final severity: MEDIUM** (band unchanged)

**Zone** — "The constant surface as a maintained artefact: is anything else maintaining it"

**Observation** — All four structures verified, all row counts exact: `ErrorCode` members at
`src/mkobi/models/enums.py:243-288` = **32**; `_ERROR_CODE_STATUS_MAP` at
`src/mkobi/utils/exceptions.py:33-74` = **32** rows; the `titles` local inside `get_error_title` at
`:184-225` = **32** rows; the `status_to_code` local inside the Starlette handler at `:323-329` =
**5** rows. Both complete tables are currently exhaustive, which the report states and which this
pass confirms.

```python
121:         self.status_code = (
122:             status_code if status_code is not None
123:             else _ERROR_CODE_STATUS_MAP.get(code, HTTP_500_INTERNAL_SERVER_ERROR)
124:         )
```

```python
226:     return titles.get(code, "Error")
```

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

(`exceptions.py:121-124`, `:226`, `:323-330`.) The reverse table is a function-local, so no second
component can consult it — verified.

**Evidence** — Row counts derived from source, not inherited. A search of every file in `tests/`
(88 `.py` files; 90 including the `api/` and `core/` subdirectories) for `_ERROR_CODE_STATUS_MAP`,
`get_error_title` and `status_to_code` returns **zero hits** — confirmed, and stronger than the
report's "all 60 test files", which understates the corpus it searched. `tests/test_error_response_format.py`
asserts one status per test and never iterates the vocabulary.

**Consequence** — Unchanged. Adding one `ErrorCode` member requires three edits across two files; the
first forgotten ships a live wrong-status response with a green suite and a body whose `title` is the
literal `"Error"`; the second ships that `"Error"` title alone. In the reverse direction every
Starlette-raised status outside the five listed is labelled `INTERNAL_ERROR` while `status` keeps its
true value, so a client routing error is reported to the operator as a server fault.

**Recommendation** — Executable as filed, and the smallest closing change is the one the report lists
last: `assert set(_ERROR_CODE_STATUS_MAP) == set(ErrorCode)` plus the `titles` equivalent. That one
assertion converts three hand-maintained tables into a maintained artefact with no refactor; the
status/title co-location refactor can follow without pressure. For the reverse table, the report's
list of statuses to add (405, 413, 429, 503) should be taken from the imports already present at
`exceptions.py:13,16,18` — those three constants are imported and unmapped today.

---

### CQ-106 — One raise site in `src/` bypasses the declared single raise mechanism

**Verdict** — CONFIRMED, with a wrong count in its own Evidence corrected · **Final severity: MEDIUM** (band unchanged)

**Zone** — "Convention compliance: the cheap high-volume rules, and which of them are broken"

**Observation** — Every citation resolves verbatim:

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

(`src/mkobi/app.py:534-536`, `:582-584`.) Independently re-run: an exhaustive search for
`HTTPException` across every `.py` under `src/` returns **8** hits in exactly two files — the
function-body import at `app.py:536`, the `except HTTPException as exc` at `:577`, the raise at
`:584`, and five in `utils/exceptions.py` (`:7,234,313,315,318`) which is the registered handler, not
a raise site. **Zero** imports of FastAPI's `HTTPException` anywhere in `src/`. The registered
`StarletteHTTPException` handler at `exceptions.py:313-342` does convert the raise, and its
`status_to_code` maps 404 to `ErrorCode.NOT_FOUND` at `:324`, so today's response conforms by
coincidence of the status value. The handler logs at `error` (`:317-321`), so an unauthenticated
client requesting a nonexistent `/api/` path produces an ERROR-level record.

**Refuted count.** The Observation says the sweep "finds … 34 `raise AppException` sites"; Appendix A
says "42 `raise AppException` sites plus 1 `raise` of a named subclass". The two statements are in the
same report, about the same sweep, and disagree. The tree has **210**, distributed across 25 files
(`deps.py` 17, `admin.py` 25, `auth.py` 18, `dashboards_crud.py` 14, `upload.py` 19, `users.py` 15,
`graphs.py` 17, `layouts.py` 17, `processing_configs.py` 10, `dashboards_access.py` 6,
`dashboards_filters.py` 7, `data.py` 7, `processing_logs.py` 3, `client_errors.py` 2,
`dashboards_graphs.py` 4, `filter_values.py` 1, `core/task_queue.py` 1, `data/loaders/loader.py` 3,
`services/aggregation_service.py` 1, `services/dashboard_service.py` 2, `services/data_service.py` 4,
`services/file_processing.py` 1, `services/processing_log_service.py` 2, `utils/time_utils.py` 2,
`workers/data_worker.py` 12). The second clause is also wrong: the tree contains at least seven
distinct named `AppException` subclasses raised directly, not one —
`PermissionDeniedException` (`services/dashboard_service.py:212`), `DashboardPermissionError`
(`services/data_service.py:160,466,503`), `RevocationStoreUnavailableError` (4 sites in
`core/security.py`), `TempPasswordStoreUnavailableError` (`core/temp_password_store.py:156`),
`SchemaNotFoundError` / `DatabaseNotFoundError` / `UnsafeTestDatabaseRecreationError`
(`db/starter.py`).

**Evidence** — `HTTPException` symbol census over `src/**/*.py`; `raise AppException` census by
occurrence and by file; the handler body read at `exceptions.py:313-342`.

**Consequence** — Unchanged and confirmed. The single-raise rule has one exception, and it is
invisible to a reader who checks the rule the obvious way (search for the FastAPI import, find
nothing). A future raise of a different status from this class answers `code=INTERNAL_ERROR` through
the default branch at `exceptions.py:330`, and the unbounded ERROR-level log for an ordinary 404 on a
public path is an unauthenticated log-volume lever.

**Recommendation** — Executable and correct as filed. `raise AppException(code=ErrorCode.NOT_FOUND,
detail="Not found")` at `app.py:584` produces the same status and the same `code` on the wire; note
that the `except HTTPException` at `:577` must then catch the 404 it raises itself or the SPA fallback
branch at `:578-580` breaks, which is the one ordering constraint the report's trivial-effort label
does not mention.
---

### CQ-107 — The health surface's status vocabulary has no named home, and its 503 is not an RFC 7807 body

**Verdict** — CONFIRMED, and the population is understated · **Final severity: MEDIUM** (band unchanged)

**Zone** — "Fixed values: one named home per value, and what bypasses it"

**Observation** — The cited block resolves verbatim:

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

(`src/mkobi/app.py:380-392`.) The 503 body carries no `type`, `title`, `code` or `detail`, so the
client extraction chain at `frontend/src/shared/api/errorHandler.ts:37-102` finds no `code` field and
falls through to the literal at `:100`, `'An error occurred'` — verified at that line.

**Understated population.** The report counts "eight bare string literals" and Appendix C lists nine
line numbers for the count 8. An independent sweep of the status family in `app.py` finds **11
sites**: `:385`, `:391`, `:408`, `:419`, `:426`, `:428`, `:438`, `:452`, `:461`, plus `:473`
(`"not_started"`) and `:480` (`"ok"` / `"starting"`) — the reconciler component the report does not
mention. Seven distinct values across the family: `healthy`, `unhealthy`, `connected`,
`disconnected`, `available`, `unavailable`, `not_started`/`starting`. The report's count is
conservative, so the finding is stronger than filed.

**Citation defect.** `tests/test_health.py:51` is cited twice as the place that "pins the exact
two-key body of the 200". Line 51 is the docstring `"""/health keeps its exact two-key body; SECB-4
does not touch it."""`; the assertion is at `:54`
(`assert response.json() == {"status": "healthy", "database": "connected"}`). Three lines off, same
file, same fact — a reader following the anchor lands on the right test but not the right line.

**Evidence** — The cited block read; a regex sweep of the status-family literals in `app.py`;
`errorHandler.ts:37` and `:97-101` read at their cited lines; `tests/test_health.py:48-54` read;
`docker/docker-compose.yml:201` confirmed as `test: ["CMD", "curl", "-f",
"http://localhost:8000/health"]` — the report's line is right. The `/health/detailed` scope
asymmetry is documented in prose at `app.py:441-448` as the report states.

**Consequence** — Unchanged. A non-RFC-7807 error body on a published endpoint, and an
eleven-site value family with no single home, no `StrEnum` and a test suite that pins two of the
values. Blast radius bounded: the only in-repo consumer of the status code is `curl -f`, and no
frontend code references `/health` or any of these literals.

**Recommendation** — Executable as filed, with one addition: `ReconcilerLeaseState` already exists as
a `StrEnum` and `app.py:481` reads `status_snapshot.lease_state.value`, so two of the eleven sites
already have a named home and the vocabulary is demonstrably derivable rather than free-form. Fold
`:473` and `:480` into the same `StrEnum` in the same pass. The 503 decision — conform, or record the
exemption in `AGENTS.md` §4 and `docs/08-security/error-format.md` — is a decision the phase file
cannot make for the project, and the report is right to present it as one.

---

### CQ-108 — Two declared lint rules apply to nothing

**Verdict** — CONFIRMED · **Final severity: MEDIUM** (band unchanged)

**Zone** — "Convention compliance: the cheap high-volume rules, and which of them are broken"

**Observation** — Verified verbatim:

```toml
142: "src/mkobi/core/permissions.py" = ["F821"]  # FastAPI Depends(get_db) pattern
143: "src/mkobi/interfaces_old/*.py" = ["UP046"]  # Old interfaces, not used
```

(`pyproject.toml:142-143`.) `Test-Path src/mkobi/interfaces_old` → `False`, confirmed.
`src/mkobi/core/permissions.py` is **223 lines** (the report's figure is right) and its complete
import block is `logging` (`:13`), `uuid.UUID` (`:14`), `sqlalchemy.ext.asyncio.AsyncSession`
(`:16`), `AccessRepository` (`:18`), `UserRepository` (`:19`), `DashboardPermission, UserRole`
(`:20`) — no FastAPI import, and a search for `Depends` and `fastapi` in that file returns **0**
hits. `uv run ruff check src/ tests/ alembic/env.py` returns `All checks passed!` without either
waiver, which is consistent with both being inert.

**Evidence** — The two lines read; `Test-Path` for the glob target; the import block read at
`:13-22`; a symbol search for `Depends` and `fastapi` returning zero; the green baseline
re-executed in this pass.

**Consequence** — Unchanged. `F821` — undefined name — is waived for the one module that implements
the authorization decision, on a stated reason that is false, in the file where an undefined name has
the highest blast radius. The `UP046` waiver matches nothing.

**Recommendation** — Executable as filed. Deleting both lines keeps `ruff` green, which is the proof
the waiver was never needed. This is the only finding in the phase whose fix is provably
behaviour-neutral and requires no decision; it is the cheapest item on the roadmap.

---

### CQ-109 — The aggregate gate omits two gates the project declares, stops at the first failure, and runs from no automated path

**Verdict** — CONFIRMED, but one third of it duplicates an already-validated finding · **Final severity: MEDIUM** (band unchanged)

**Zone** — "The gates the project declares: where each is wired, what each decides, and whether it can be run the way the pipeline runs it"

**Observation** — Verified verbatim:

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

(`Makefile.ps1:281-289`.) Both omitted gates exist and are wired to their own targets:
`Invoke-Test` at `:227-230`, `Invoke-TestAll` at `:232-235`, `Invoke-MigrationCheck` at `:315-317`
(documented in the help text at `:108` as "Detect model/schema drift (alembic check, test DB)").
`Invoke-Typecheck` at `:270` is `mypy src/ alembic/env.py`. The eight CI paths are **all absent**,
independently re-checked: `.github`, `.gitlab-ci.yml`, `azure-pipelines.yml`, `.circleci`, `.gitea`,
`.woodpecker.yml`, `Jenkinsfile`, `.pre-commit-config.yaml` → `False` for each.

**Duplicate third.** The `Invoke-Test` half is already-validated work.
`.ai/plans/_code-context/08-code-quality-code-context.md:295` records `VAL-08-007` as
"**substantiated**; its ordering constraint it adds is now satisfied by history", and `:458` records
its remediation state as "`Invoke-Check` still omits `Invoke-Test`" — the same defect, the same
function, the same omission. `:374` of that note assigns the wiring half to **phase 09**, and
`.ai/plans/_code-context/09-test-coverage-code-context.md:95` agrees ("`QLT-003` merge, phase 09 owns
the wiring"). The input does not acknowledge `VAL-08-007` anywhere.

**Evidence** — `Makefile.ps1` read at `:255-289`, `:218-240`, `:305-317`; help text read at `:96-109`;
`Test-Path` over the eight CI paths; the code-context note read at `:289-297` and `:452-460`.

**Consequence** — Unchanged for the parts that are new. A contributor running the documented
aggregate learns nothing about whether the test suite passes or whether the ORM models still match
the migration chain, and the first-failure-wins shape means a red lint gate returns before the other
three report anything. Nothing would notice a failing test or an unrecorded model change without a
human running two extra commands by name.

**Recommendation** — Executable as filed, and the report is right that the absence of any automated
path is a deployment-posture decision owned by phase 10 and should not be scheduled here. On the
merge: `Invoke-Test`'s omission has an owner (phase 09) and an adjudicated history (`VAL-08-007`);
adding it again under a phase-08 identifier creates a second claim on one remedy. Record it here as
a cross-reference and let phase 09 close it, while `Invoke-MigrationCheck`'s omission — which no
adjudicated note covers — stays phase 08's.

---

### CQ-110a — The 65 % coverage floor is inert on the canonical test path

**Verdict** — **REJECTED** as a new finding; duplicate of already-validated `VAL-08-001` · **not carried** as a separate finding

**Zone** — "The gates the project declares: where each is wired, what each decides, and whether it can be run the way the pipeline runs it"

**Observation** — The claim is true and the citation is exact:

```toml
196: addopts = "--import-mode=importlib -ra -v --strict-markers --cov-fail-under=65"
```

(`pyproject.toml:196`; `pytest-cov` constructs its plugin only when `--cov` names a source, and
`Invoke-TestAppPytest` at `Makefile.ps1:222-225` forwards only `@PytestCacheArgs @PyArgs` with
`$PyArgs` empty, while `Invoke-TestAll` at `:234` passes `--cov=src/mkobi`.)

**Why it is rejected as new.** `.ai/plans/_code-context/08-code-quality-code-context.md:289` records
`VAL-08-001` as "the 65 % coverage floor is inert (no `--cov` in `addopts`)", verdict
"**substantiated**", with evidence `pyproject.toml:196` and the *identical* nuance: "`Makefile.ps1::
Invoke-TestAll` runs `pytest --cov=src/mkobi`, so the *floor is real* on the `test-all` path and
inert on the `test` path. The defect is a per-entry-point inconsistency, not a universal absence."
`pyproject.toml:202-208` and `Makefile.ps1:227-235` are re-read and unchanged from that baseline.
This is not a near-duplicate: it is the same defect, the same anchor, the same mechanism and the same
nuance, already adjudicated **substantiated** by a validation pass whose authority the code-context
note declares at `:7` ("overrides every report anchor"). The base context's rule applies —
already-validated, cite and move on.

**Recommendation** — None carried. The two coherent positions the report offers (make the floor real
on every path, or remove the flag and leave measurement to `test-all`) remain the right options; they
belong to `VAL-08-001`'s remediation.

---

### CQ-110b — The `tests.*` mypy override is reached by no command

**Verdict** — CONFIRMED (new; the half of `CQ-110` that `VAL-08-001` does not cover) · **Final severity: MEDIUM**

**Zone** — "The gates the project declares: where each is wired, what each decides, and whether it can be run the way the pipeline runs it"

**Observation** —

```toml
183: [[tool.mypy.overrides]]
184: module = ["tests.*"]
185: disallow_any_generics = false
186: warn_return_any = false
```

(`pyproject.toml:183-186`.) No command passes `tests/` to mypy — `Invoke-Typecheck` is
`mypy src/ alembic/env.py` (`Makefile.ps1:270`) — so the block applies to nothing. This is distinct
from the coverage half and is **not** in `VAL-08-001`, which is scoped to `--cov`.

**Evidence** — **Executed**: `uv run mypy src/ alembic/env.py` prints
`pyproject.toml: note: unused section(s): module = ['tests.*']` on every run, then
`Success: no issues found in 121 source files`. The checker reports the condition itself; no
independent inference is needed.

**Consequence** — A declared relaxation that reads as a deliberate lowering of the test tree's typing
bar when it is inert configuration. It costs a reader a debugging detour on the first run — the note
is unexplained — and it will silently start applying the moment someone extends `Invoke-Typecheck`
to the test tree, which is the change this finding's sibling recommends.

**Recommendation** — Pick one position and make the configuration match it: extend `Invoke-Typecheck`
to `mypy src/ tests/ alembic/env.py`, which makes the relaxation real and deliberate, or delete
`pyproject.toml:183-186`. Note that `warn_unused_configs = true` at `pyproject.toml:156` is what
surfaces the note, so leaving it costs nothing at runtime and only costs comprehension.
---

### CQ-111 — 17 of 59 route operations declare no `response_model`, and the report's account of what that publishes is refuted

**Verdict** — CONFIRMED, evidence and named consequence corrected · **Final severity: MEDIUM** (band unchanged)

**Zone** — "Type width and the sanctioned-suppression surface: what is enforced, what is silenced"

**Observation** — The census is **exact**. An AST sweep over every `@router.<method>(` decorator in
`src/mkobi/api/routes/` reaches **59 route operations across 15 modules** and finds **17** with no
`response_model=` keyword. The per-module distribution is precisely as filed: `admin.py` 5,
`users.py` 2, `dashboards_access.py` 2, `dashboards_filters.py` 2, and one each in
`dashboards_crud.py`, `filter_values.py`, `graphs.py`, `layouts.py`, `processing_configs.py` and
`client_errors.py`. (The report says "13 route modules"; the correct figure is **15** — the 59 is
right.) The credential operations are among them, verbatim:

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

(`src/mkobi/api/routes/admin.py:567-582`; the deprecated GET twin at `:542-558`; the shared body at
`:515-539` returning `{"temp_password": password}` at `:539`.) The contrast set is also exact:
`response_model=list[UserRead]` at `:47`, `=UserRead` at `:79` and `:156`,
`=list[RegistrationRequestItem]` at `:355`, `=SuccessResponse` at `:452`.

**Two refuted claims, established by execution.**

1. *"The widened return annotation is `dict[str, Any]` in every case."* It is not. Of the 17:
   **9** are annotated `-> dict[str, Any]`; **8 declare no return annotation at all**
   (`admin.py:117`, `client_errors.py:81`, `dashboards_crud.py:422`, `graphs.py:416`,
   `layouts.py:404`, `processing_configs.py:205`, `users.py:281`, `users.py:333`); and **1**
   (`filter_values.py:38`) is annotated `-> FilterValuesResponse`, a real type that FastAPI therefore
   *does* use as the response model — that operation should not have been counted at all.

2. *"The OpenAPI document publishes `{}` for it: no generated client type can carry the field."*
   **Refuted.** FastAPI uses the return annotation as the response model when `response_model=` is
   absent. Verified by execution against the framework itself, on this project's installed FastAPI
   build (`get_openapi` over a four-route app reproducing the exact patterns):

   | annotation | published 2xx schema |
   |---|---|
   | `-> dict[str, str]` | `{"additionalProperties": {"type": "string"}, "type": "object"}` |
   | `-> dict[str, Any]` | `{"additionalProperties": true, "type": "object"}` |
   | *(none)* | `{}` |
   | *(none, decorated)* | `{}` |

   So the two credential operations publish a string-map schema, not `{}`.

**Evidence** — AST sweep over all 59 decorators, recording per-operation `response_model` presence
and the unparsed return annotation; `get_openapi` run against a minimal app carrying the four
patterns. The full app could not be imported on the Windows host — `src/mkobi/services/file_processing.py:11`
→ `ImportError: failed to find libmagic`, the limitation already recorded in `.kilo/rules/commands.md`
— so the framework behaviour was established in isolation and the operation set by AST rather than by
walking the live document. That limitation is recorded in Appendix F as a limit, not as a finding.

**Consequence, restated honestly.** The finding survives and is in one respect stronger than filed:
**the 8 operations with no return annotation publish `{}`** — an empty object schema, exactly the
defect the report describes, and eight endpoints rather than two. The 9 `dict[str, Any]` operations
publish `additionalProperties: true` and are unfiltered, so a field added to a handler's return
reaches the client untyped. What is *not* true is the claim that no generated client type can carry
`temp_password`: the published string map admits it. The real credential-shaped gap is that no
*named* field exists in the document, so `frontend/src/shared/types/api.types.ts` (327 lines, no
`temp_password` reference — confirmed, including against its current 2-line working-tree diff) has
nothing to mirror.

**Recommendation** — Executable, and the priority within it should be inverted from the report's.
Declare a two-field model (`temp_password: str`) on the two credential operations as the report says,
but note that adding `response_model=` to an operation that already has a return annotation **narrows**
the schema from a string map to a named object — the wire response is unchanged and
`tests/test_temp_password_retrieval.py` asserts by value, so nothing breaks. Handle the **8
unannotated** operations first: they are the ones that actually publish `{}`, and the cheapest fix is
a return annotation, not a `response_model=`. Drop `filter_values.py:38` from the count.

---

### CQ-112 — The dashboard admin-bypass refusal is written four times, and the copies return three different strings

**Verdict** — CONFIRMED · **Final severity: LOW** (band unchanged)

**Zone** — "One rule, one home: whether exactly one implementation exists"

**Observation** — Every citation resolves. The decision has one home:

```python
170:         # Admin bypass: admins can access any dashboard
171:         user_repo = UserRepository()
172:         user = await user_repo.get(id=user_id, db=db)
173:         if user and user.role == UserRole.ADMIN:
```

(`src/mkobi/core/permissions.py:170-173`, inside `_check_access_with_session` at `:152`.) The
inline copies are byte-exact as quoted:

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

(`src/mkobi/api/routes/dashboards_crud.py:367-386`; both handlers take `current_user: CurrentUser`
at `:337` and `:438`, which resolves to `get_current_user_dependency` via
`deps.py:976` `CurrentUser = Annotated[UserRead, Depends(get_current_user_dependency)]`, **not** to
the write/admin gate.) The shared dependency's refusal:

```python
878:         raise AppException(
879:             code=ErrorCode.PERMISSION_DENIED,
880:             detail="You do not have write access to this dashboard",
881:         )
```

(`src/mkobi/api/deps.py:878-881`, in `require_dashboard_write_access` at `:841`; the read gate is at
`:797`, the admin gate at `:885`, the collection wrapper at `:929` with its docstring at `:942-944`.)

**Two corrections, both widening the finding.** The delete twin is cited at
`dashboards_crud.py:463-476`; the block actually runs `:463-481` — the cited range ends inside the
`logger.warning` at `:473-477` and omits the raise at `:478-481`. And that twin's refusal string is
`"Access denied"` (`:480`), which is **neither** of the two the report names. The divergence is
therefore into **three** strings for one rule: "You don't have access to this dashboard" (update),
"Access denied" (delete), "You do not have write access to this dashboard" (shared dependency).

**Evidence** — All four sites read at their cited lines; the string literals compared directly.

**Consequence** — Unchanged and confirmed. Access is checked on every dashboard request, so no control
is bypassed; the cost is discoverability plus an existing cosmetic divergence across three strings.
LOW is correct under this phase's band ("documentation, reachability and hygiene drift with no
runtime consequence today") rather than MEDIUM, because MEDIUM's nearest clause — "a duplicated
helper with no divergence yet" — does not reach a divergence that is purely a response-body string on
a correctly-enforced decision.

**Recommendation** — Executable as filed, with the ordering constraint the report names being the
whole of the risk: `user_permission` at `dashboards_crud.py:390` reads `has_edit_access`, so the
dependency must be declared and the permission recomputed after the gate, not before. Also confirm
which of the three strings any test asserts before changing the delete twin, since `:480` is a
different literal from either one the report examined.

---

### CQ-113 — `auth.py` is the only route that constructs its own repository, and the only one that names its session `session`

**Verdict** — CONFIRMED, with one wrong count · **Final severity: LOW** (band unchanged)

**Zone** — "Responsibility inside a unit: how many jobs one unit does, and which is reachable from elsewhere"

**Observation** — Both citations resolve verbatim:

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

(`src/mkobi/api/routes/auth.py:392-397`, `:487`; `UserRepository` imported at `auth.py:35`, and the
container exposes `get_user_repository` — `UserRepository` is imported at `deps.py:60`.)

**Confirmed by census.** A search for `\w+Repository\(` across `api/routes/*.py` returns exactly one
constructor call, `auth.py:487`; the other six hits are DI-factory *calls*
(`graphs.py:114,201,260,347,457` and `processing_logs.py:116` are `get_*_repository()`), not
constructions.

**Corrected count.** The Consequence says "58 of the 59 route operations name the injected session
`db`". An AST sweep over all 59 route handlers, matching on the annotation text, gives: **53** named
`db`, **5 declare no session parameter at all**, and **1** — `auth.py:395` — named `session`. The
qualitative claim ("this one is the only outlier") is exactly right; the denominator is not.

**Evidence** — Symbol census for repository constructors and for `session:` / `db:` parameters;
AST sweep over the 59 route handlers for an `AsyncSession` / `get_db_dependency` annotation and its
argument name.

**Consequence** — Unchanged. One route reaches past the container to a concrete repository, so its
dependencies are not visible in its signature and a test overriding `get_user_repository` does not
affect the refresh path. Nothing breaks today — the concrete class is the same one the container
returns.

**Recommendation** — Executable as filed. `user_repo: UserRepository = Depends(get_user_repository)`
in the signature and `await user_repo.get(UUID(user_id), session)` at `:487` is the whole fix; the
`session` → `db` rename is optional, as the report says. The report's "58 of the 59" should read "53
of the 54 handlers that take one".

---

### CQ-114 — The shared temp-password docstring versus the edge access log

**Verdict** — CORRECTED (re-graded down, and cross-referenced to already-validated work) · **Final severity: LOW** (filed MEDIUM)

**Zone** — "Declared contracts and their enforcement point: whether anything checks the claim, and whether anything reaches it"

**Observation** — Every citation resolves verbatim:

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

(`src/mkobi/api/routes/admin.py:519-526`.) The GET twin carries the handle as a path segment at
`:543` (`"/temp-passwords/{retrieval_token}"`), is marked `deprecated=True` at `:552`, and schedules
removal for `1.0.9` at `:549` while `pyproject.toml:7` declares `version = "1.0.8"`. The edge format
logs `$uri`:

```nginx
21:     log_format mkobi_redacted '$remote_addr - $remote_user [$time_local] '
22:                               '"$request_method $uri $server_protocol" '
23:                               '$status $body_bytes_sent "$http_referer" '
24:                               '"$http_user_agent"';
25:     access_log /dev/stdout mkobi_redacted;
```

(`docker/nginx/nginx.conf.template:21-25`; `$uri` at `:22`, with the template's own rationale at
`:14-20`.) So `GET /admin/temp-passwords/<handle>` writes the complete handle to `/dev/stdout`.
**That much is confirmed.**

**Why the band moves.** The docstring's claim is **scoped to the application's own log line** — "the
full handle never appears in **the application access log** via **a log line**" — and `:526` delivers
exactly that, on both operations, because the truncation is in the shared body. The finding reads the
sentence as an unqualified guarantee about any access log; as written it is not one, and the qualifier
"via a log line" is what makes the scoping legible. Two further facts cut against the MEDIUM band:

1. **The same module already discloses the exposure.** The deprecated operation's own OpenAPI
   description at `admin.py:546-549` states "the retrieval handle travels in the request line, where it
   **can reach the access log**". A reader who consults the operation's documentation — the primary
   surface for it — is told the truth, 20 lines below the sentence the finding attacks. The docstring's
   silence is a phrasing ambiguity, not a contradiction.
2. **The substantive exposure is already-validated tracked work.** The phase-04 validation report at
   `.ai/audit/99-validation/04-authentication-validated-findings.md:874-881` records `C04-5` as
   "**Genuinely already-tracked**", citing `admin.py:567-584`, `admin.py:542-564`, the truncation at
   `admin.py:526`, and the same `nginx.conf.template:21-25` edge format — and accepts it with an
   anchor correction (that correction still holds: `docker/nginx/` contains `entrypoint-render.sh` and
   `nginx.conf.template` only). That record predates this validation and is refuted nowhere in the
   tree.

**Ownership.** This is **not** a cross-phase duplicate. Phase 08 declares ownership of
"the declared-contract angle" in its own scope paragraph, and the finding correctly confines itself
to the declaration while assigning the exposure to phases 07 and 10 — the right seam, and the same
seam the phase-04 validator drew. The residual is that the wording is ambiguous, not that the
exposure is undiscovered.

**Evidence** — Both citations read; the docstring's own scoping clause read verbatim; the operation's
`description` at `:546-549` read; the phase-04 validated report read at `:874-881`; `docker/nginx/`
listed.

**Consequence** — A reader consulting only the shared body's docstring does not learn that the
deprecated operation's handle reaches the edge access log; they will learn it from the operation's own
description. The window is bounded by a release number in prose (`1.0.9`) with no tracking artefact,
which is the one residual the finding names and which is phase 10's scheduling posture.

**Recommendation** — The report's documentation-only remedy is correct and remains the whole of it:
state the truncation as a property of the application log record and either drop or qualify the
sentence to the POST operation. Do **not** change the edge log format — redacting a path segment the
edge must route on is phase 10's decision, as the report says. The durable remedy (retiring the GET)
is `C04-5`'s, not this finding's; record the cross-reference rather than opening a second claim on it.
---

## Validation-level findings

Graded on this phase's own scale: effect and blast radius of a defect **in the audit**, anchored to
present state. CRITICAL is a wrong approval — a claim confirmed that the system does not support, or
an absence recorded as established. Nothing here is CRITICAL: every finding the input filed was
re-derived on its own terms, no system absence was recorded as clean, and the two false sweeps are
corrected rather than relied upon. `VAL-08-` numbering starts at **010**; see Appendix D for the
collision that forces it.

### VAL-08-010 — `VAL-08-001 … VAL-08-009` are already occupied, and the input did not check

**Severity** — MEDIUM

**Observation** — The base context instructs every phase to check for a collision before minting an
identifier and to report it rather than creating a second namespace. The `CQ-` collision was checked
and disclosed. The `VAL-` namespace was not: the input states only that "this pass mints no `VAL-08-*`
(validation is not this role's)", which is true and also leaves the range unverified.
`.ai/plans/_code-context/08-code-quality-code-context.md:22` declares
`Report-level defects | **VAL-08-**, VAL-08-001 … VAL-08-009 (9)` for a validated report at
`.ai/audit/99-validation/08-code-quality-validated-findings.md` — the very file this pass writes. Those
nine identifiers are **load-bearing provenance**, referenced from five artefacts:
`08-code-quality-code-context.md:22,289-297,452-460`,
`09-test-coverage-code-context.md:95`, `12-authorization-code-context.md:39,334`,
`.ai/tasks/B4-txn-006-access-grant-conflict.yaml:135,171,576` and
`.ai/tasks/CQLT-2-enforce-dashboard-access-audience.yaml:22,100,702`.

**Evidence** — The front-matter row read at `:22`; a search of every `.md` and `.yaml` under `.ai/`
for `VAL-08-00\d` returning nine distinct identifiers and the five citing artefacts above. The
validated report those identifiers came from is **absent from the working tree** —
`.ai/audit/99-validation/` contains reports for phases 01–06 only.

**Consequence** — A validation pass that started at `VAL-08-001` would have silently reused nine live
identifiers across five artefacts, including two `.ai/tasks/` change records that would then cite the
wrong text. The absence of the earlier validated report from the tree compounds it: the provenance is
asserted by a code-context note that declares itself authoritative (`:7`), and cannot be checked
against the artefact it describes.

**Recommendation** — Mint from `VAL-08-010` (done). Separately, either restore
`.ai/audit/99-validation/08-code-quality-validated-findings.md` from history or add a note to
`08-code-quality-code-context.md` recording that its `VAL-08-001…009` rows are attested rather than
present, so a later reader does not treat the note as a substitute for the report.

---

### VAL-08-011 — Two of the eight inherited negative sweeps are false

**Severity** — MEDIUM

**Observation** — The Summary states the inherited mechanical sweeps "came back clean and are
recorded in Appendix A, not filed". Six of the eight reproduce exactly. Two do not.

**1. The `except` sweep.** Appendix A: "Bare `except:` / `except Exception` swallowing without logging
| 50 handlers in `src/` | 49 log before returning or raising. **1** silent: `starter.py:217`."
Re-run by AST walk over every handler: **323 handlers, 54 silent.** The 53 others are 30
`except AppException: raise` pass-throughs, 15 deliberate `ValueError` → `AppException` translations
that name an `ErrorCode`, 1 `except asyncio.CancelledError`, 1 `except HTTPException`, 1
`except TempPasswordStoreUnavailableError`, 1 `except PermissionDeniedException`, and 5
`except (RedisError, OSError, TimeoutError)` in `core/reconciler_lease.py`. `CQ-104`'s Observation
independently repeats the same wrong claim, so the error is load-bearing on a filed finding's evidence.

**2. The `dict[str, Any]` census.** Appendix C: "`dict[str, Any]` / `list[dict[str, Any]]` in `src/`
| 107 | CQ-111 is the named consequence, not the count". Re-run with the identical pattern over the
identical tree: **165 occurrences across 107 lines**. The figure is therefore *ambiguous rather than
simply wrong* — which is itself the defect, because a census number that resolves to two values under
two readings of the same pattern cannot be checked by the reader it is written for.

**Also mis-stated, in the same appendix:** "all 60 test files" in `CQ-105`'s Evidence — the corpus is
**88** `.py` files (90 including `tests/api/` and `tests/core/`). The conclusion drawn from that
search (zero hits) is unaffected.

**Evidence** — AST walk over `src/**/*.py` classifying each `except` handler for a `logger.*`
attribute access; regex count of the `dict[str, Any]` pattern over the same tree by line and by
occurrence; `Get-ChildItem tests` count.

**Consequence** — An audit's negative claims are the load-bearing half of its "no findings" entries. A
sweep that scanned 50 of 323 handlers and reported 49/50 clean reads as a complete census and is not
one; a reader who trusts it concludes the tree has one silent handler when it has 54. The consequence
is bounded here — all 53 other silent handlers are documented decisions, pure re-raises, or
translations that name an error code, and the five lease handlers surface their outcome through
`/health/detailed` (`app.py:479-486`) — so **no system finding was lost**. The defect is in the
report's claim of coverage, which is what an absence recorded as established looks like.

**Recommendation** — Correct the two rows in Appendix A with the real populations (323 / 54, and "165
occurrences across 107 lines", stated as such), or drop the `except` row and say plainly that the
silent-handler population is dominated by deliberate re-raises and was not a defect worth counting.
Do not leave a census row whose number resolves two ways.

---

### VAL-08-012 — `raise AppException` is counted twice, differently, and neither count is right

**Severity** — LOW

**Observation** — `CQ-106`'s Observation says the sweep finds "**34** `raise AppException` sites";
Appendix A says "**42** `raise AppException` sites plus 1 `raise` of a named subclass". The two
figures are in the same report, about the same sweep, and disagree. The tree has **210**, across 25
files. The second clause is also wrong: the tree contains at least seven distinct named
`AppException` subclasses raised directly (`PermissionDeniedException` at
`services/dashboard_service.py:212`, `DashboardPermissionError` at `services/data_service.py:160,466,503`,
`RevocationStoreUnavailableError` ×4 in `core/security.py`, `TempPasswordStoreUnavailableError` at
`core/temp_password_store.py:156`, `SchemaNotFoundError` / `DatabaseNotFoundError` /
`UnsafeTestDatabaseRecreationError` in `db/starter.py`), not one.

**Evidence** — Occurrence census of `raise AppException` over `src/**/*.py`, grouped by file; a
census of `^\s*raise [A-Za-z_]+` excluding `AppException`.

**Consequence** — Drift with no remediation consequence today: `CQ-106`'s finding is real and its
citations are exact, and neither count appears in its Recommendation. But a reader who uses the
Observation's "34" to judge how thoroughly the sweep ran is being given a number wrong by a factor of
six, and cannot tell which of the two internal figures to believe.

**Recommendation** — Replace both with `210` and cite the per-file breakdown, or drop the count and
keep the two substantive claims (no FastAPI `HTTPException` import; exactly one Starlette raise site at
`app.py:584`), which are the parts the finding rests on.

---

### VAL-08-013 — `CQ-` is a second namespace for one phase, against the phase file's stated remedy

**Severity** — LOW

**Observation** — The phase file's Report Output says: "Finding-ID prefix: `QLT-` — check for a
collision before minting an identifier; **report the collision rather than creating a second
namespace**". The input reported the collision and then created a second namespace anyway. Both
underlying facts it relies on are **verified true**: `QLT-001 … QLT-010` are spent and remediated
(`docs/SPEC.md:246`, row 3.43, enumerates `audit findings QLT-001 … QLT-010` and describes each
block's remediation; `:245`, row 3.42, records `QLT-009`), and
`.ai/plans/_code-context/08-code-quality-code-context.md:5` declares `finding_prefix: QLT-`, with
`:21` recording the ten as minted with no gap. `CQ-` itself collides with nothing: every `CQ-\d`
occurrence in the repository is inside `.ai/audit/08-code-quality/findings.md`.

The phase file's remedy was available and unused: continue the series at `QLT-011+`. The dispatching
instruction mandated `CQ-`, which is outside the report's control, and the report says so plainly —
which is why this is LOW and not MEDIUM. The cost is the same one phase 01's validation recorded for
`TOPO-`: two disjoint ranges for one subject, where a lookup for `QLT-004` and a lookup for `CQ-104`
mean different things and only one of them appears in the shipped corpus.

**Evidence** — `docs/SPEC.md:245-246` read; the code-context note read at `:5` and `:21`; `CQ-\d`
searched across `src/`, `tests/`, `frontend/`, `docs/`, `.ai/`, `alembic/`, `docker/` and the root
config files, returning hits only inside the report itself; the phase file read at `:172`.

**Consequence** — Naming and wording inconsistency between two phases of the set, with no remediation
consequence today. The disclosure is accurate, the correction inside it (the doubled
`08-code-context/` path segment) is accurate, and the identifiers are collision-free and stable.

**Recommendation** — Keep `CQ-`. Recorded so that a later run does not "correct" it back to `QLT-` and
collide with ten remediated identifiers. If the audit family wants one namespace per phase going
forward, that is a coordinator decision recorded once for all phases, not a per-run choice.

---

### VAL-08-014 — MISSED FINDING: the documentation corpus publishes three removed filter routes, one as an instruction

**Severity** — MEDIUM (on the audit's scale; on phase 08's own rubric it is `DOC-UPDATE`, LOW)

**Observation** — The input's sweep row for "declared guarantees contradicted by the path that runs"
reports exactly one site (`admin.py:522-524`, filed as `CQ-114`) and concludes the category is
otherwise clean. It is not. `src/mkobi/api/routes/filters.py:1-6` is a six-line stub declaring the
filter CRUD surface removed, and `docs/02-dashboards/dashboards-api.md:526-527` agrees. Three other
documents still publish it:

- `docs/08-security/access-control.md:130-131` — a permissions table listing
  `GET /api/v1/filters` (Editor+) and `GET /api/v1/filters/:id` (Editor+) as served endpoints.
- `docs/11-guides/create-dashboard.md:502` — an operator instruction: "Modify filter configuration via
  `PUT /api/v1/filters/{id}`". This one is actionable guidance pointing at a route that does not exist.
- `docs/03-processing/processing-api.md:522`, `docs/04-admin/admin-api.md:891`,
  `docs/07-frontend/pages.md:337` — three "related documentation" links describing the dashboards API
  as "Dashboard, graph, and **filter CRUD**".

**Evidence** — The stub file read in full; a search of every `.md` under `docs/` for
`/api/v1/filters`, `filter CRUD` and `CRUD endpoints removed`, returning eight hits across five
files; a symbol census confirming no route registers a `/filters` path.

**Consequence** — The security document is the surface an auditor or a reviewer reads to learn a
route's required audience, and it lists two routes that answer 404. The guide gives an instruction a
reader will follow and fail. Three cross-reference lines advertise a CRUD surface the project removed
by ruling. This is the same defect class `CQ-114` was filed under, in the same corpus, and the input's
sweep recorded the class as exhausted after one hit.

**Recommendation** — Delete the two rows from `docs/08-security/access-control.md:130-131`, delete or
re-point the instruction at `docs/11-guides/create-dashboard.md:502`, and drop "filter CRUD" from the
three cross-reference lines. Ordering constraint: this should land **with** or **after** `CQ-101b`'s
removal of `FilterService`, so the documents and the tree move together.

---

## Distribution

The findings fall on six surfaces, and the two that carry the most are the route/service wiring seam
and the gate/configuration seam.

- **Route and service wiring** — CQ-101a, CQ-101b, CQ-112, CQ-113. The densest surface and the only one
  with a reachable behavioural defect: seven graph endpoints commit inside handlers, and the only
  non-empty-name rule in the domain has no caller.
- **Declared constants and configuration** — CQ-103, CQ-105, CQ-107, CQ-108. One role name in two
  homes, one 32-member vocabulary in four hand-maintained structures, an eleven-site response value
  family with no home, and two lint waivers that match nothing.
- **Gates and declared thresholds** — CQ-109, CQ-110b (with CQ-110a rejected as a duplicate). An
  aggregate that omits two declared gates and returns on the first failure, and one inert mypy override.
- **Error and response boundary** — CQ-106, CQ-111. One raise site outside the single raise mechanism;
  seventeen operations with no declared response shape.
- **Declared contracts with no true enforcement point** — CQ-104, CQ-114. A start-up message that names
  the wrong remedy, and a docstring whose scoping is ambiguous.
- **The audit's own artefacts** — VAL-08-010 … VAL-08-014, on a separate scale and in a separate
  section.

Backend-only: no finding lands on `frontend/src/`, whose type-safety bar the sweep re-confirmed at
zero `: any` / `as any` / `@ts-ignore` / `@ts-expect-error` with `strict: true` and no path-scoped
relaxation. The only frontend citation in the report
(`frontend/src/shared/api/errorHandler.ts:37-102`) is a read the sweep made, and it resolves.

## Cross-Finding Analysis

Six findings share one cause, and it is the phase's most consequential pattern: **a rule that is
written in a discoverable place and enforced in a different one.** CQ-101a's graph-name check,
CQ-102's password byte budget, CQ-104's `None` contract, CQ-110b's inert mypy override, CQ-112's
refusal wrapper and CQ-114's log-redaction claim are all cases where the copy or the claim a reader
opens is not the one that runs. The mechanism is uniform and the input names the pattern correctly —
but two of its six members did not survive their own evidence: CQ-102's "the copy that runs has no
test" is refuted by `tests/test_validators.py:237-303`, and CQ-101a's "the only coverage" is refuted
by `tests/test_graph_service.py` plus 38 integration tests. The pattern holds; two of the proofs
offered for it do not.

CQ-109 and CQ-110 were filed as one shape and are **not** one finding: CQ-110 splits into a coverage
half that duplicates an already-validated `VAL-08-001` and a mypy half that is new. That is the
clearest evidence that the input treated a pairing as a unit without splitting it, and it is the one
place where the report over-reports rather than under-reports.

CQ-105, CQ-107 and CQ-108 share a smaller shape: a declared structure — a vocabulary, a response value
family, a per-file ignore table — that nothing keeps in agreement with the tree. They differ in
whether a miss is currently silent, and only CQ-105's is fully silent today.

CQ-103 and CQ-110b share one cause with CQ-109: **a gate or diagnostic declared in configuration that
the path a contributor actually walks never executes.** mypy is the only one that reports its own
inertness, on every run.

## Roadmap

Grouped by cause, not by severity. Ordering constraints are stated where one exists.

1. **Put each rule in the home that runs** — CQ-102, CQ-101a, CQ-104, CQ-112, CQ-113, CQ-114. All
   independent; none blocks another. They share a review shape, so one pass lets a reviewer check
   "is the copy or the claim I am editing the one that executes?" six times. Start with CQ-102 — two
   deletions and one import — then CQ-114, which is documentation-only and removes an ambiguous
   sentence. **CQ-101a needs a scope decision before any code moves** (adopt the services, or rule
   that the graph domain has none) and is the largest item in this step. Its `min_length=1` edit at
   `models/graph.py:47` is independent of that decision and can land first.
2. **Retire what the tree already ruled out** — CQ-101b, VAL-08-014. These must land together or in
   that order: VAL-08-014 removes three documents' claims about `/api/v1/filters`, and CQ-101b removes
   the service and DI factory those documents implicitly described. Landing VAL-08-014 first leaves
   the tree briefly documenting a surface with no route; landing CQ-101b first leaves the documents
   describing a service that is gone. Either order is safe; one commit is not required.
3. **Close the configuration-to-runtime gaps** — CQ-103, CQ-110b, CQ-105. CQ-103's `if row is None:`
   warning first: three lines, no schema consequence, and it carries the whole finding. CQ-110b is a
   two-way configuration decision. CQ-105's two membership assertions close the correctness gap on their
   own; the table co-location refactor can follow without pressure.
4. **Make the declared gates mean what they say** — CQ-109, CQ-108. CQ-109's `Invoke-Test` half is
   already owned by phase 09 (`VAL-08-007`); only `Invoke-MigrationCheck` and the
   accumulate-rather-than-return shape are phase 08's, and `Invoke-Test` needs a decision about whether
   `check` may require the test stack. CQ-108 is independent of everything and can land at any point —
   it is the cheapest edit in the phase and needs no decision.
5. **Declare the response shapes** — CQ-111, CQ-106, CQ-107. Independent of the above. Within CQ-111,
   handle the **8 unannotated** operations first: they are the ones that publish `{}`, and a return
   annotation is the smaller edit. Drop `filter_values.py:38` from the count. CQ-106's `AppException`
   swap needs the raise site at `app.py:584` to be caught by the `except` at `:577` in the same commit
   or the SPA fallback breaks. CQ-107 needs the 503 decision — conform or record the exemption —
   before any code moves.
## Rollout Safety

Steps 1, 2 and 5 change observable behaviour. Three of those changes should be announced rather than
merged quietly.

**CQ-101a is a behaviour change disguised as a wiring change.** Routing the seven graph handlers
through `GraphService` moves each `db.commit()` out of the handler and into the service, which moves
the transaction boundary relative to the handler's remaining work, and it activates
`GraphService._validate_graph_data` for the first time on a request path — so a graph whose name is
empty or whitespace-only starts returning `422` where it previously returned `200` and stored the
row. That is the intended effect and belongs in the commit message. **The exposure to check before
merging:** any client flow that creates a graph with a blank name will start failing, and there is no
route-level test for `POST /graphs` or `POST /dashboards/{id}/graphs`, so the suite will not catch a
regression. Note that the *service* is covered — `tests/test_graph_service.py` (17 tests) and
`tests/test_services_integration.py::TestGraphServiceIntegration` — so the service side is tested even
though the route side is not; that is the actual gap, and it is the opposite of what the input
recorded. Revert is a revert of the handler signatures; no stored row is rewritten, and graph names
already persisted as blank remain a separate operator question this change does not address.

**CQ-102 is the only step that can change an API response, and it does so only on the import line.**
Deleting `validate_password` and `validate_email` changes nothing at runtime — neither has a production
caller — but `tests/test_validators.py` asserts all three functions, so the suite must change with the
removal. Repointing `auth_service.py:38` at `validators.EMAIL_REGEX` is the one edit on a live path,
and it is safe only because `validators.py:11` imports nothing but `mkobi.models.enums` while
`auth_service` is reached during `mkobi.config`'s own import. Verify before merging by asserting that
a registration with a malformed address is still refused; `tests/test_validators.py:237-303` must
survive intact, because the eight assertions there are the *only* coverage of the byte budget the
reachable copy enforces. Revert is a single-file revert of `validators.py` plus the import line.

**Step 5's CQ-106 replacement changes what is caught, and CQ-111's changes what is published.**
Swapping `HTTPException` for `AppException` at `app.py:584` produces the same status and the same
`code` on the wire, and both handlers log at `error`, so the log volume is unchanged today; the
report's advice to drop the 404 to `info` is what would change it. The constraint is that the raise
must be caught by the `except` at `:577` in the same commit or the SPA fallback at `:578-580` breaks.
Verify with one request to a nonexistent `/api/` path before and after. CQ-111's `response_model=`
additions *narrow* the published schema on four operations; the wire bodies are unchanged and
`tests/test_temp_password_retrieval.py` asserts by value.

**Steps 3 and 4 are configuration and declaration work with no runtime effect**, except that CQ-103's
parameter binding touches SQL executed against a live admin connection — bind `DatabaseSettings.user`
and **not** `admin_user` (`config.py:264`), or the grant grants the wrong role. CQ-109's decision about
whether `check` may require the test stack is a workflow change for every contributor who currently
runs it; make it explicit in the help text at `Makefile.ps1:102` in the same commit.

Nothing in this sequence involves a schema change, a migration, or a data-shape change, so every step
remains a plain revert.

## Appendices

### Appendix A — Disposition ledger and final severity counts

| ID | Verdict | Band as filed | Final band | Anchor drift | Independent check |
|---|---|---|---|---|---|
| CQ-101a | CORRECTED (split; scope widened) | HIGH | **HIGH** | none | unreachability re-derived by exhaustive census |
| CQ-101b | CORRECTED (split; re-owned, re-graded) | HIGH | **MEDIUM** | none | retirement ruling read at `dashboards-api.md:526-527` |
| CQ-102 | CONFIRMED (consequence clause refuted) | HIGH | **HIGH** | none | caller census; budget read at `security.py:166-199` |
| CQ-103 | CONFIRMED (re-graded down) | HIGH | **MEDIUM** | none | 13-occurrence census; fail-open branch read |
| CQ-104 | CONFIRMED (evidence clause refuted) | MEDIUM | **MEDIUM** | none | 323/54 handler census |
| CQ-105 | CONFIRMED | MEDIUM | **MEDIUM** | none | 32/32/32/5 counts; zero test hits |
| CQ-106 | CONFIRMED (count refuted) | MEDIUM | **MEDIUM** | none | 210 occurrences across 25 files |
| CQ-107 | CONFIRMED (population widened; anchor off by 3) | MEDIUM | **MEDIUM** | one line | 11-site sweep |
| CQ-108 | CONFIRMED | MEDIUM | **MEDIUM** | none | `Test-Path`; import block; green baseline |
| CQ-109 | CONFIRMED (one third duplicates `VAL-08-007`) | MEDIUM | **MEDIUM** | none | `Makefile.ps1` read; 8 CI paths absent |
| CQ-110a | **REJECTED** (duplicate of `VAL-08-001`) | MEDIUM | not carried | none | code-context note `:289`, `:452` |
| CQ-110b | CONFIRMED (new) | MEDIUM | **MEDIUM** | none | **executed** — mypy prints the unused-section note |
| CQ-111 | CONFIRMED (2 claims refuted by execution) | MEDIUM | **MEDIUM** | none | AST sweep + `get_openapi` |
| CQ-112 | CONFIRMED (2 corrections) | LOW | **LOW** | one range under-covers | 4 sites read; 3 strings |
| CQ-113 | CONFIRMED (one count refuted) | LOW | **LOW** | none | AST census 53/5/1 |
| CQ-114 | CORRECTED (re-graded down; cross-ref `C04-5`) | MEDIUM | **LOW** | none | phase-04 validation `:874-881` read |

**Counts by verdict** — CONFIRMED 11 (CQ-102, CQ-104, CQ-105, CQ-106, CQ-107, CQ-108, CQ-109,
CQ-110b, CQ-111, CQ-112, CQ-113) · CORRECTED 4 (CQ-101a, CQ-101b, CQ-103, CQ-114) · REJECTED 1
(CQ-110a). **16 dispositions covering the input's 14 identifiers**: `CQ-101` split into two halves and
`CQ-110` split into a rejected half and a carried half.

**Final severity counts, surviving system findings** — CRITICAL 0 · **HIGH 2** (CQ-101a, CQ-102) ·
**MEDIUM 10** (CQ-101b, CQ-103, CQ-104, CQ-105, CQ-106, CQ-107, CQ-108, CQ-109, CQ-110b, CQ-111) ·
**LOW 3** (CQ-112, CQ-113, CQ-114). **15 findings carried.** One disposition (`CQ-110a`) is not
carried and is excluded from the bands.

**Movement against the input** — 1 HIGH re-graded down (CQ-103), 1 MEDIUM re-graded down (CQ-114), 1
MEDIUM split with one half rejected, 1 HIGH split into HIGH + MEDIUM. **Nothing was promoted.** The
input's front matter (`findings: 14`, `CRITICAL 0 / HIGH 3 / MEDIUM 9 / LOW 2`) is internally
consistent with its own 14 findings; the divergence is entirely in the bands, not in the tally.

**Validation-level findings, on the report's own scale** — CRITICAL 0 · HIGH 0 · **MEDIUM 3**
(VAL-08-010, VAL-08-011, VAL-08-014) · **LOW 2** (VAL-08-012, VAL-08-013). VAL-08-014 describes a
defect that would be `DOC-UPDATE` / LOW on phase 08's own rubric had the phase filed it.

### Appendix B — Citation re-verification

Every citation in this report was opened at its quoted lines immediately before composition. The
input's citation quality is itself the finding: **of 71 distinct code citations opened in this pass,
none was stale, none failed to resolve, and three ranged one-to-five lines off the block they
describe** (`dashboards_crud.py:463-476` → block ends `:481`; `tests/test_health.py:51` → assertion at
`:54`; Appendix A's "60 test files" → 88). This is the opposite of phase 01's result (9 of 14 stale)
and phase 02's systematic compose drift, and it is recorded as a measured outcome. Contrast with the
input's own *derived counts*, which is where the errors concentrate: **9 of the 15 census figures
re-derived in this pass came back wrong or ambiguous** — see `VAL-08-011`, `VAL-08-012`, and the
corrections inside CQ-106, CQ-107, CQ-110a and CQ-113.

Files re-read at their cited ranges in this session: `src/mkobi/api/deps.py`,
`src/mkobi/api/routes/admin.py`, `src/mkobi/api/routes/auth.py`,
`src/mkobi/api/routes/client_errors.py`, `src/mkobi/api/routes/dashboards.py`,
`src/mkobi/api/routes/dashboards_access.py`, `src/mkobi/api/routes/dashboards_crud.py`,
`src/mkobi/api/routes/dashboards_filters.py`, `src/mkobi/api/routes/dashboards_graphs.py`,
`src/mkobi/api/routes/filter_values.py`, `src/mkobi/api/routes/filters.py`,
`src/mkobi/api/routes/graphs.py`, `src/mkobi/api/routes/layouts.py`,
`src/mkobi/api/routes/processing_configs.py`, `src/mkobi/api/routes/processing_logs.py`,
`src/mkobi/api/routes/upload.py`, `src/mkobi/api/routes/users.py`, `src/mkobi/app.py`,
`src/mkobi/config.py`, `src/mkobi/core/logging_config.py`, `src/mkobi/core/permissions.py`,
`src/mkobi/core/reconciler_lease.py`, `src/mkobi/core/security.py`,
`src/mkobi/core/temp_password_store.py`, `src/mkobi/db/models/filters.py`,
`src/mkobi/db/models/graphs.py`, `src/mkobi/db/starter.py`, `src/mkobi/interfaces/__init__.py`,
`src/mkobi/interfaces/service_interfaces.py`, `src/mkobi/models/dashboard.py`,
`src/mkobi/models/enums.py`, `src/mkobi/models/filters.py`, `src/mkobi/models/graph.py`,
`src/mkobi/services/auth_service.py`, `src/mkobi/services/dashboard_service.py`,
`src/mkobi/services/filter_service.py`, `src/mkobi/services/graph_service.py`,
`src/mkobi/utils/exceptions.py`, `src/mkobi/utils/validators.py`,
`frontend/src/shared/api/errorHandler.ts`, `frontend/tsconfig.app.json`,
`frontend/tsconfig.node.json`, `pyproject.toml`, `Makefile.ps1`,
`docker/nginx/nginx.conf.template`, `docker/docker-compose.yml`, `docs/SPEC.md`,
`docs/02-dashboards/dashboards-api.md`, `docs/08-security/access-control.md`,
`docs/11-guides/create-dashboard.md`, `docs/03-processing/processing-api.md`,
`docs/04-admin/admin-api.md`, `docs/07-frontend/pages.md`, `tests/test_validators.py`,
`tests/test_health.py`, `tests/test_deps.py`, `tests/test_graph_service.py`,
`tests/test_services_integration.py`, `.ai/plans/_code-context/08-code-quality-code-context.md`,
`.ai/audit/99-validation/04-authentication-validated-findings.md`.

**Concurrent-modification note — recorded because `HEAD` moved during the pass.** The input declares
`HEAD 0ae6ddf`. Current `HEAD` is **`7568a21`** — two commits ahead: `8f22377` ("fix(filters): evaluate
a multiselect filter value and refuse an unevaluable declared type") and `7568a21`
("fix(dashboard-filters): retire the range control and drop an unevaluable restored value").
`git diff --stat 0ae6ddf..HEAD` touches 12 files; **none of them is cited by any finding in this
report.** The two filter-route commits touch `frontend/src/features/dashboards/ui/`,
`src/mkobi/api/routes/data.py`, `src/mkobi/db/repositories/aggregated_data_repo.py`,
`src/mkobi/interfaces/service_interfaces.py`, `src/mkobi/models/dashboard.py`,
`src/mkobi/models/data.py`, `src/mkobi/services/data_service.py` and four test files — and
`dashboards_filters.py`, `filters.py`, `graph_service.py`, `filter_service.py`, `models/graph.py` and
`models/filters.py`, the files `CQ-101a`/`CQ-101b` turn on, are byte-identical to the baseline the
input read. Working-tree modifications at validation time are
`frontend/src/shared/types/api.types.ts` (the file the base context flags as moving),
`src/mkobi/api/routes/data.py`, `src/mkobi/models/dashboard.py`, `src/mkobi/models/data.py`,
`.ai/plans/16-phase16-residual-execution.md`, and the deletion of `.kilo/plans/PLAN_01.md` /
`PLAN_RECOVERY.md`. Of these, only `api.types.ts` is cited by any finding (`CQ-111`, for its size and
its absence of a `temp_password` reference — both stable properties, not line anchors), and its
2-line working-tree diff adds no `temp_password` key. **A second concurrent change landed after that
check and before this report was closed**: `frontend/src/features/dashboards/ui/DashboardView.tsx`,
`frontend/src/features/dashboards/__tests__/DashboardView.test.tsx` and a new
`frontend/src/features/dashboards/__tests__/aggregated-stale-data.test.tsx` appeared as modified and
untracked. None is cited by any finding in this report or by the input, so no citation was
re-opened on their account; they are recorded because the tree moved twice under this pass and a later
reader reconciling against `HEAD` will see them.

**Scratch files outside the repo could not be deleted.** Five analysis scripts were written to
`C:\Users\Om\AppData\Local\Temp\kilo\` (`cq111_scan.py`, `sess_scan.py`, `except_scan.py`,
`oapi_check.py`, `fastapi_rm_check.py`). Cleanup was refused by this agent's
`external_directory: deny` permission rule, so they remain on disk and are named here rather than left
silently. **No file under `src/`, `frontend/src/`, `tests/`, `alembic/` or `docker/`, and no
production or configuration file, was modified, created or deleted by this pass** — the validation
report is the only repository file written.
### Appendix C — Gates re-executed and independent checks

**Both backend gates, re-executed on this tree at `HEAD 7568a21`:**

| Gate | Command | Output | Input's claim |
|---|---|---|---|
| ruff | `uv run ruff check src/ tests/ alembic/env.py` | `All checks passed!` | **matches exactly** |
| mypy | `uv run mypy src/ alembic/env.py` | `note: unused section(s): module = ['tests.*']`, then `Success: no issues found in 121 source files` | **matches exactly, including the file count** |
| mypy (strict defs) | `uv run mypy src/ --disallow-untyped-defs` | `Success: no issues found in 120 source files` | **matches exactly** |

The count 121 is confirmed to the file, and the unused-section note the input reports is present on
every run. **No finding in the input or in this report rests on a red baseline.**

**Independent re-runs of the eight inherited negative sweeps.** Six reproduce, two do not:

| Sweep | Input's result | Re-run | Verdict |
|---|---|---|---|
| `print()` on a production path in `src/` | 0 | 0 | **confirmed** |
| FastAPI `HTTPException` imports | 0 | 0 (8 `HTTPException` hits total, all Starlette's, in `app.py` and `exceptions.py`) | **confirmed** |
| hardcoded error-code strings | 0 | 0 | **confirmed** |
| untyped definitions under `--disallow-untyped-defs` | 0 in 120 files | 0 in 120 files | **confirmed** |
| `any` / `@ts-ignore` / `@ts-expect-error` in `frontend/src/` | 0 production | 0; one production `as unknown as` at `chartConversion.ts:127` + 9 in tests, exactly as filed | **confirmed** |
| `tsconfig` strictness | `strict: true`, no path relaxation | `strict: true` at `tsconfig.app.json:3`; `noUnusedLocals`/`noUnusedParameters` at `:20-21`; `tsconfig.node.json` covers `vite.config.ts` only; no `@ts-nocheck` anywhere | **confirmed** |
| layer direction in the import graph | 5 directions clean | `services/→api` 0, `db/→services\|workers\|api` 0, `data/→services\|api` 0, `workers/→api` 0 | **confirmed** |
| silent `except` handlers | 1 of 50 | **54 of 323** | **FALSE — `VAL-08-011`** |

**Derived counts re-derived.** Exact match: 10 service factories in `deps.py`, 8 named by routes; 59
route operations; 17 without `response_model=` and its per-module distribution; `Any` in
`src/mkobi/interfaces/` = **51**; `mkobi_app` in `src/` = **13**; `redirect_slashes` in `api/routes/`
= **0**; `Depends`/`fastapi` in `core/permissions.py` = **0**; `src/mkobi/interfaces_old` absent; the 8
CI paths all absent; `validate_password_or_raise` production call sites = **7**; `ErrorCode` / status
map / title rows = 32 / 32 / 32; reverse table = 5; `permissions.py` = 223 lines;
`graph_service.py` = 291; `filter_service.py` = 331; `Any`-free count in `deps.py` = 1 (at `:147`).

Corrected or ambiguous: `dict[str, Any]` / `list[dict[str, Any]]` = **165 occurrences across 107
lines** (input reports 107); `raise AppException` = **210** across 25 files (input reports 34 in one
place and 42 in another); route modules = **15** (input says 13); session parameters across the 59
handlers = **53 `db` / 5 none / 1 `session`** (input says "58 of the 59 name it `db`"); health status
literals in `app.py` = **11 sites, 7 values** (input says 8, listing 9 lines); test-file corpus = **88**
(input says 60); `validate_password` test call sites = **9** (input says five).

**Framework behaviour, established by execution.** FastAPI infers the response model from the return
annotation when `response_model=` is absent. `get_openapi` was run against a four-route app carrying
the four patterns on the project's own installed build and returns
`{"additionalProperties": {"type": "string"}, "type": "object"}` for `-> dict[str, str]`,
`{"additionalProperties": true, "type": "object"}` for `-> dict[str, Any]`, and `{}` for an
unannotated operation. This is the refutation of `CQ-111`'s two central claims.

### Appendix D — Namespace ruling

**The `CQ-` prefix is accepted.** The phase file mandates `QLT-`
(`.kilo/commands/audit/phases/08-audit-code-quality.md:172`) and
`.ai/plans/_code-context/08-code-quality-code-context.md:5` declares `finding_prefix: QLT-`. The
input's collision disclosure is **accurate on both facts**: `QLT-001 … QLT-010` are spent and
remediated (`docs/SPEC.md:246` enumerates them and describes each block's remediation; `:245` records
`QLT-009`), and `CQ-` collides with nothing in the repository. It also corrects a doubled path segment
in the code-context citation, and that correction is right —
`.ai/plans/_code-context/08-code-context/` does not exist. **Ruling:** keep `CQ-`, recorded in
`VAL-08-013` so a later run does not "correct" it back into ten remediated identifiers. The deviation
from the phase file's stated remedy is recorded, not endorsed.

**The `VAL-08-` prefix starts at 010.** `VAL-08-001 … VAL-08-009` are declared occupied by
`08-code-quality-code-context.md:22` and are load-bearing across five artefacts; see `VAL-08-010`. The
audited phase's own identifiers (`CQ-101 … CQ-114`) are preserved verbatim and never renumbered, and
the audited namespace and the validation namespace occupy separate tables.

**"Not re-filed" claims — all three verified.** `TOPO-106` and `TOPO-114` exist in
`.ai/audit/01-process-architecture/findings.md` (`:359`, `:756`) and `CFG-113` in
`.ai/audit/02-configuration-secrets/findings.md` (`:644`); the input names all three in Appendix A as
already-filed and files none of them. Its supporting anchors also hold: `pyproject.toml:219`
`pandas-stubs==3.0.0.260204` is present, and `app.py:361-371` carries the `/api/v1` prefix as eleven
literals, which the phase-02 validation independently confirms at
`.ai/audit/99-validation/02-configuration-secrets-validated-findings.md:906` ("the backend prefix is
eleven literals at `app.py:361-371`"). **No re-file of the remediated `QLT-*` set either:** the input
names `ButtonVariant`/`ComponentSize` (`enums.py:167`, `:180`, zero code references beyond
`models/__init__.py`) and the `redirect_slashes` declarations (0 remaining in `api/routes/`) as
already-remediated and files neither.

**One disclosure now superseded.** The input states that
`.ai/audit/07-external-boundary/` "does not exist at write time, so phase 07 has minted no `VAL-07-*`".
That was true at the input's write time — the directory's timestamp is 14:53:15 against the input's
14:22:22 — and phase 07's report now exists, filed under `EXT-101 … EXT-109`, which collides with
nothing here. The disclosure is correct as filed and superseded by history.

### Appendix E — Ownership and merge map

| Concern | Owner | Disposition |
|---|---|---|
| unreachable `GraphService`; graph name rule with no reachable caller | **08** | `CQ-101a`, HIGH, carried |
| `FilterService` orphaned by a recorded domain retirement | **08** (block 7, dead code with established intent) | `CQ-101b`, MEDIUM, re-owned from block 5 |
| credential-strength / email-format duplication | **08** | `CQ-102`, HIGH, carried |
| `mkobi_app` role-name duplication and the fail-open privilege probe | **08** | `CQ-103`, MEDIUM, re-graded |
| deprecated GET handle reaching the edge access log | **07 / 10**, already tracked as `C04-5` | **not re-filed** by `CQ-114`; `CQ-114` carries only the ambiguous docstring wording, at LOW, with a cross-reference |
| `Invoke-Test` omitted from the aggregate | **09**, per `VAL-08-007` and `09-test-coverage-code-context.md:95` | `CQ-109` carries the `Invoke-MigrationCheck` omission and the first-failure shape; the `Invoke-Test` half is a cross-reference, not a second claim |
| absence of any automated gate path | **10** (deployment posture) | recorded in `CQ-109`, not scheduled — the input's call, upheld |
| coverage floor inert on `test` | already validated as `VAL-08-001` | `CQ-110a` REJECTED as a duplicate |
| documents publishing the removed `/api/v1/filters` surface | **08** (declared-contract angle) | `VAL-08-014` — missed by the input's sweep, filed here |

No contested claim was found where two phases reach opposite conclusions about the same subject. The
one genuine cross-phase overlap (`CQ-114` / `C04-5`) is resolved by scoping, not by merging, and the
one genuine ownership seam (`CQ-109`'s `Invoke-Test` half / phase 09) is resolved by deferral.

### Appendix F — What was not settled, and why

- **The full OpenAPI document could not be generated on this host.** Importing `mkobi.app` fails at
  `src/mkobi/services/file_processing.py:11` with `ImportError: failed to find libmagic` — the
  limitation already recorded in `.kilo/rules/commands.md` for host-side runs. The set of undeclared
  operations was therefore derived by AST walk over the 59 decorators rather than by reading the
  served document, and the FastAPI annotation-to-schema behaviour was established in isolation against
  the project's own installed build. Both substitutions are exact for the question asked; neither
  would detect an operation registered by a route the AST walk classifies differently.
- **CQ-105's 405 claim was not re-derived by observation.** The input states it as a derivation from
  Starlette's routing behaviour plus the default branch at `exceptions.py:330`, not from a response.
  That derivation is accepted as derivation and is not restated here as observed fact; it also does
  not enter any recommendation.
- **CQ-103's fail-open branch was not reproduced against a live PostgreSQL.** The branch is read from
  the cited lines and the semantics of `fetchone()` on a zero-row result are unambiguous, but no
  database was started. The claim is recorded as read-and-derived, not as executed.
- **CQ-101a's blank-name write was not driven end-to-end.** The absence of any reachable non-empty
  rule and the absence of a column `CHECK` are established by reading `models/graph.py:44-52`,
  `db/models/graphs.py:50-53,103-108` and the two commit sites; no request was issued and no row was
  written.
- **The gate inventory's `npm run build` row** (`frontend/package.json`, not wired into `check`) was
  not re-executed; the frontend gates this pass ran were the read-only sweeps in Appendix C, and
  `ruff` / `mypy` are the only two gates the input's baseline claim rests on.

### Appendix G — Coverage ledger

| Block | Population reached | Method | Finding |
|---|---|---|---|
| 1 — Fixed values: one named home | 4 values derived | literal census per value | CQ-103, CQ-105, CQ-107, CQ-111 |
| 2 — Constant surface as a maintained artefact | 4 `ErrorCode` structures | row counts from source | CQ-105 |
| 3 — Boundary validation coverage | 4 request boundaries (`GraphCreate`, `FilterCreate`, `FilterUpdate`, the credential models) | model read + caller census | CQ-101a, CQ-101b |
| 4 — Type width and the suppression surface | 59 route operations | AST sweep for `response_model` presence and return annotation | CQ-111 |
| 5 — Responsibility inside a unit | 10 service layers, 2 unreachable | exhaustive reference census + `Depends` parameter sweep | CQ-101a, CQ-101b, CQ-113 |
| 6 — One rule, one home | 8 rules derived | implementation-count map | CQ-102, CQ-112 |
| 7 — Convention compliance | 8 mechanical rules; 2 declared rules | symbol sweeps + `Test-Path` + AST handler census | CQ-106, CQ-107, CQ-108, CQ-101b; `VAL-08-011` |
| 8 — Declared contracts and their enforcement point | 5 declared properties | declaration read against the executing path | CQ-104, CQ-114, `VAL-08-014` |
| 9 — The declared gates | 8 gates | inventory: where declared, where wired, automated path | CQ-109, CQ-110a, CQ-110b |
| 10 — Schema drift | **0 — not reached** | `alembic check` is `QLT-004`'s remediated half and `TOPO-106`'s subject; not re-examined | none |

Item counts are the populations each block actually reached, not the populations it assumed. Every
claim left unsettled is listed in Appendix F with its reason.