---
phase: 08-code-quality
executed: 2026-09-30
executor: validator
problems-only: true
baseline: b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd
baseline-dirty: >-
  D .ai/builders/**, D .ai/structure/**, D .ai/models/**, D .ai/plans/**, D .ai/templates/**,
  D .ai/audit/templates/audit-final-report.md; ?? .ai/audit/0*/ , ?? .ai/audit/99-validation/,
  ?? .ai/plans/01-configuration-secrets-remediation-execution.md. During the run the concurrent
  remediation programme added " M src/mkobi/config.py" and a peer agent added an untracked
  .tmp/b4/ tree; neither is this run's work and neither touches an audited file.
baseline-note: >-
  HEAD at this validation equals the input's recorded baseline, b23a9cb — the concurrent remediation
  series has stopped there, so no anchor in the input moved under this run and no re-anchor table is
  required. The _b3_full_out.txt named in the phase brief is NOT present in git status at this
  baseline. src/, tests/, frontend/, pyproject.toml, Makefile.ps1, alembic/ and docker/ are clean.
findings: 10
by-severity:
  CRITICAL: 0
  HIGH: 4
  MEDIUM: 4
  LOW: 2
validation-findings: 9
by-validation-severity:
  CRITICAL: 1
  HIGH: 1
  MEDIUM: 6
  LOW: 1
namespace-deviation: >-
  This report's validation-level findings use VAL-08-. The flat VAL- prefix is already occupied by
  the phase-01 and phase-02 validation reports (VAL-001..VAL-008 and VAL-001..VAL-009); the
  compound form VAL-0N- was established by the phase-03..07 validation reports and is continued
  here. The audited prefix QLT- is preserved verbatim and is never interleaved with VAL-08-.
---

# Phase 08 — Validated Findings (Code Quality)

## Summary

All ten `QLT-` findings were re-derived from the executing path with every location reference
resolved mechanically first; **ten confirmed, none rejected, none unsettled**, with two bands
re-graded, one finding re-typed against the specification corpus, one merged in part into a
sibling phase's finding, and one claim inside a confirmed finding refuted. The CRITICAL band does
not survive: **QLT-001 is re-graded CRITICAL → HIGH**, because the CRITICAL predicate's anchor — "a
wrong or lost value is in storage now" — cannot be established for this defect. The storage tier is
a native PostgreSQL enum: `SELECT 'read'::dashboard_permission_level` returns
`ERROR: invalid input value for enum dashboard_permission_level: "read"`, and the live type holds
exactly `view,edit,admin`. No endpoint can change an existing grant's permission, and no
out-of-vocabulary value can be stored. The defect is real and reproduced from source: the one
surface that reports a permission change writes nothing and answers HTTP 200 — which is phase 08's
own HIGH clause, "a declared invariant nothing enforces".

Both backend gates are red at this baseline, re-run here and matching the input verbatim: `ruff
check src/ tests/` → 1 `F401` at `services/processing_log_service.py:13`; `mypy src/` → 2
`arg-type` at `workers/data_worker.py:740` and `:818`. `Invoke-Check` (`Makefile.ps1:241-249`)
does short-circuit, and — confirming phase 09's stronger TST-002 claim — it never invokes pytest at
all, so **QLT-003 and TST-002 are one finding split across two reports with no merge ruling on
either side** (VAL-08-007). QLT-004 is re-graded MEDIUM → HIGH: phase 08's own rubric assigns HIGH
verbatim to "schema drift no gate would notice", which is the finding's title.

Of the input's two dismissed candidates, **one dismissal is sound and one is a wrong approval**. The
Cyrillic at `filter_service.py:299` is confirmed to be the character class
`^[a-zA-Zа-яА-Я0-9\s\-_.]+$` inside a filter-name validator — data, not prose — and the dismissal
holds. The 65 % coverage floor is **inert**: `pytest_cov/plugin.py:202-204` registers `CovPlugin`
only `if early_config.known_args_namespace.cov_source`, and `--cov-fail-under` populates
`cov_fail_under`, not `cov_source`. The input read `CovPlugin.__init__` (`:225-254`) and the
fail-under evaluation (`:369-376`) — both reachable only inside a plugin that is never
constructed. Phase 09's TST-003 is correct and this input contradicts it in a delivered appendix
row (VAL-08-001).

Three further adjudications the reader should not have to discover mid-report. QLT-009's census is
right but its label is not: `docs/SPEC.md:118` and `docs/09-database/enums.md:48-49` state exactly
what both families were created for, so this is a missing integration rather than a dead export, and
the recommendation asks a question the corpus has already answered (VAL-08-006). QLT-010's second
claim is refuted — no `APIRouter`-level `redirect_slashes` declaration reaches the behaviour, because
`include_router` discards it and the decision belongs to the application's `FastAPI(...)`
constructor, so its recommendation's second half would change nothing (VAL-08-004). And QLT-001's
evidence records the `read` alias as "accepted by this endpoint" on the strength of a 200 that the
no-op branch produced; the same input on a row that does not yet exist reaches PostgreSQL and returns
**500**, so the endpoint's answer to one legal-looking value depends on prior state (VAL-08-008).

## Findings

Identifiers are preserved; none was renumbered. Each block carries its disposition inside the
Observation field, because the shared template mandates no disposition field (Appendix H). Bands
are recorded after re-grade.

### QLT-001 — The only endpoint that can change a dashboard grant reports a change it does not make

**Severity** — HIGH (re-graded from CRITICAL; the competing reading is recorded in the Observation)

**Zone** — Fixed values: one named home per value, and what bypasses it

**Observation** — Disposition: **confirmed**, band **re-graded CRITICAL → HIGH**. Re-derived from
the executing path alone; the quoted transcript was not relied on. The write path is closed to
every caller: `AccessRepository.grant_access` selects the existing row and returns it unchanged at
`db/repositories/access_repo.py:57-63` (`logger.warning("Access already exists…")`, then
`return cast(..., existing)`) and reaches `DashboardAccess(...)` only at `:65`; a search of
`src/mkobi` for `\.permission\s*=` and `DashboardAccess\(` returns those as the only write and
construction sites; `@router.(put|patch)` appears at seven places in `api/routes/` and **none of
them is the access resource** — the resource exposes POST and DELETE only. `DashboardService.grant_access`
validates at `services/dashboard_service.py:374` and passes the un-normalised original at `:389`,
and `_validate_permission` (`:482-501`) assigns `normalized` and never returns it, so the `read`
and `write` branches at `:485-488` cannot reach the repository. `PERMISSION_LEVELS`
(`core/permissions.py:38-42`) has exactly one occurrence in `src/` — its own declaration. The four
bare-`str` homes all resolve: `models/access.py:11` and `:30`, `core/permissions.py:129`,
`db/repositories/access_repo.py:36`. The live `/openapi.json` publishes
`AccessGrant.permission` as `{"type":"string","default":"view"}` with no enum.

**Band.** The CRITICAL predicate is *"a wrong or lost value is in storage now … a stored value no
rule ever constrained … two implementations of one rule whose copies already disagree on a value
the system acts on."* The storage anchor cannot be established: `db/models/access.py:43-52`
declares the column as `Enum(DashboardPermission, name="dashboard_permission_level")`,
`alembic/versions/000000000000_initial_migration.py:27-30,152` creates it as a native PostgreSQL
enum, and the live type in `bidb` holds exactly `view,edit,admin`. A value outside the vocabulary is
unrepresentable, so neither "a stored value no rule ever constrained" nor a wrong stored value can
arise. The second clause is satisfied only for the two aliases `read`/`write`, which by that same
constraint can never reach a decision path — all three implementations agree on `view`/`edit`/`admin`.
What remains is HIGH's own vocabulary: a declared invariant nothing enforces (the operation
declares that it grants access; on an existing row nothing is performed and 200 is returned with
the requested value) and a value with two homes (four bare-`str` declarations, no enum in the
published schema). **The competing reading, stated so a reader may overrule it:** the defect's
Consequence is that read paths keep admitting `edit` operations for a principal the administrator
believes has only `view`, which is an authorization outcome produced by a decision the API recorded
as applied — on a reading of "a lost value in storage" the CRITICAL band holds. This validation
does not sustain that reading, because the value in storage is the one the system created under a
live constraint and what was lost is the operator's *intent*, not a value the system wrote. Had the
column been a plain `VARCHAR`, the CRITICAL band would have been correct, and the input's own
recommendation — type the four `str` declarations — assumes a looser column than the schema has.

**Refinement of the headline.** "The only endpoint that can change a dashboard grant" is imprecise
in the endpoint's favour: *no* endpoint can change an existing grant. DELETE followed by POST is the
only sequence that produces a different stored permission, and POST alone is the only one that
reports having changed it. The finding's Consequence states this correctly; the title does not.

**Evidence** — Static proof from the executing path, plus the live schema and live published
contract:

| claim | test | result |
|---|---|---|
| an existing row is returned unwritten | `access_repo.py:56-63` — `scalar_one_or_none()`, `if existing: return cast(…, existing)` | no `UPDATE`, no assignment |
| normalisation is discarded | `dashboard_service.py:484-491` (`normalized` assigned) vs `:389` (`permission=permission`) | confirmed |
| no second surface | `\.permission\s*=` and `DashboardAccess\(` over `src/mkobi`; `@router.(put\|patch)` over `api/routes/` | 0 write sites, 0 access-resource PUT/PATCH |
| `PERMISSION_LEVELS` unread | `Select-String PERMISSION_LEVELS` over the repository | 1 hit, the declaration |
| `read` is not storable | `SELECT 'read'::dashboard_permission_level` on `bidb` | `ERROR: invalid input value for enum dashboard_permission_level: "read"` |
| published field is unconstrained | `GET /openapi.json` → `components.schemas.AccessGrant` | `{"type":"string","default":"view"}`, no `enum` |

**Consequence** — A grant's permission cannot be changed after it is first created, and the only API
surface that appears to change it answers 200 with the requested value, so an administrator who
downgrades an editor from `edit` to `view` is told they succeeded while the stored value is still
`edit` and the read paths that consult `check_dashboard_access` keep admitting `edit` operations for
that principal. Because QLT-002 admits any authenticated caller, the same false success is available
to non-administrators.

**Recommendation** — Usable as written, and unblocked: no shipped test exercises
`POST /dashboards/{id}/access` or asserts the no-op (`tests/` contains no route-level grant test and
no assertion on the "already exists" branch), so the input's hedge that "any shipped test asserting
the current no-op must change with the fix" resolves to *there is no such test*. Two corrections
apply to the recommendation's own diagnosis (VAL-08-008): the `read`/`write` entries at
`permissions.py:209-210` are dead because of **both** the guard at `:150-151` and the storage
constraint, so deleting them is correct but the comment at `:43-44` describes a behaviour that is
unreachable for a different and stronger reason than the input gives; and the input's "sixteen
production call sites" understates — a search for `required_permission="…"` over `src/mkobi` returns
**21** bare-literal call sites, before any `permission=` site is counted (VAL-08-009).

### QLT-002 — The dashboard access-grant endpoints declare an audience that no executing path enforces

**Severity** — HIGH (upheld)

**Zone** — Declared contracts and their enforcement point: whether anything checks the claim, and whether anything reaches it

**Observation** — Disposition: **confirmed**; band upheld at HIGH; **ownership ruled phase 08's**;
the recommendation carries a refuted premise (VAL-08-005). The three declarations resolve verbatim:
module docstring `api/routes/dashboards_access.py:4` "All operations require admin role.", route
description `:35` "Grants user access to dashboard. Available only to owners.", handler docstring
`:47`. The live `/openapi.json` operation carries `"security": [{"HTTPBearer": []}]` — no role or
ownership constraint — and the description as written. `DashboardService.grant_access`
(`services/dashboard_service.py:356-401`) performs `_validate_permission`, a dashboard-existence
check, a repository write and a commit: no ownership test, no role test.

**One correction, and it strengthens the finding.** The input says the handler "uses it only as a log
field (`:65-70`)". It does not: the log statement at `:65-70` interpolates `access_grant.user_id`,
not `current_user`. The parameter `current_user` (`:41`) is **never referenced anywhere in the
handler body** — the route authenticates the caller and then discards the identity. The same is
true of the GET handler (`:138-171`) and the DELETE handler (`:181-227`), neither of which mentions
`current_user` at all.

**Evidence** — Executing path read at every anchor; live published contract read from the running
dev stack (`GET http://localhost:8010/openapi.json`); the three handler bodies read in full and
searched for `current_user` with zero hits inside each body.

**Consequence** — Any authenticated account, of any role, can insert an `admin` grant for itself or
any other user on any dashboard in the database, including dashboards owned by the administrator,
and the grant is immediately effective on the read paths that consult `check_dashboard_access`. The
three published descriptions tell an integrator the opposite, so the contract an operator reads is
narrower than the audience the path admits.

**Recommendation** — Usable with one correction (VAL-08-005). The input justifies placing the check
inside `DashboardService.grant_access` on the ground that it "is the only caller of
`AccessRepository.grant_access`". That is **false**: `services/dashboard_service.py:104` is a second
production caller, inside `create_dashboard`, granting `DashboardPermission.ADMIN` to the new
dashboard's owner. The rule belongs on the three handlers as a route dependency (which covers the
dashboard-creation grant site as well, harmlessly, since that grant names the owner), or in
`DashboardService.grant_access` with the create path stated as an intentional second exemption. A
reader who enforces it "at the only call site" will find a second call site.

**Ownership ruling** (Block 6). Phase 08's own scope paragraph claims the declared-contract angle
explicitly (`.kilo/commands/audit/phases/08-audit-code-quality.md:20-21`, block 8 at `:126,133`:
"This phase owns that angle: any other phase observing a documented claim contradicted or unenforced
files the observation here") and defers "the access decision and refusal shape" to phase 12 (`:27`).
Phase 12 has not run — `.ai/audit/` contains phases 01–09 and `99-validation` only. **Phase 08 owns
the declaration-versus-enforcement finding; phase 12 owns whether owner-or-admin is the correct rule
and what a refusal discloses.** The input's split is the correct one; this is a cross-reference, not
a merge, and the "must not be closed until phase 12 has reviewed the whole decision surface" caveat
in the recommendation is upheld.

### QLT-003 — Both declared backend gates are red at HEAD, so the aggregate entry point cannot reach the frontend gates, and no declared gate is wired to an automated path

**Severity** — HIGH (upheld)

**Zone** — The gates the project declares: where each is wired, what each decides, and whether it can be run the way the pipeline runs it

**Observation** — Disposition: **confirmed**; band upheld at HIGH; **merged in part into TST-002**
(VL-08-007), with the split named below. Both gates were re-run at this baseline, on unmodified
code, and the output matches the input's characterisation exactly:

| gate | command | result at `b23a9cb` |
|---|---|---|
| `lint` | `uv run ruff check src/ tests/` | **1 error** — `F401 'sqlalchemy.text' imported but unused` at `src/mkobi/services/processing_log_service.py:13` |
| `typecheck` | `uv run mypy src/` | **2 errors** — `arg-type` on `Argument 3 to "save_filter_values"`, at `src/mkobi/workers/data_worker.py:740` and `:818`; plus `pyproject.toml: note: unused section(s): module = ['tests.*']` |

`git status --porcelain -- src/` was empty before and after both runs, so neither failure is
produced by the concurrent remediation programme. `Invoke-Check` (`Makefile.ps1:241-249`) reads:

```
Invoke-Lint ; if ($LASTEXITCODE -ne 0) { return }
Invoke-Typecheck ; if ($LASTEXITCODE -ne 0) { return }
Invoke-FeLint ; if ($LASTEXITCODE -ne 0) { return }
Invoke-FeTest
```

The short-circuit claim is **correct**, and because ruff is red, `typecheck`, `fe-lint` and
`fe-test` are unreachable through the entry point contributors are pointed at. Independently
confirmed here, and **it strengthens phase 09's TST-002 rather than competing with it**: no
`Invoke-Test` appears anywhere in `Invoke-Check`, so the backend suite is not in the aggregate at
all, in addition to being short-circuited behind a red lint.

The absence of an automated path is an inventory with a stated absence, and every item the input
lists is confirmed absent: `.github`, `.pre-commit-config.yaml`, `.gitlab-ci.yml`,
`azure-pipelines.yml` and `.circleci` all return `False`.

**Evidence** — Both gates executed at this baseline, on unmodified code, with
`git status --porcelain -- src/` empty before and after, so neither failure is produced by the
concurrent remediation programme:

```
ruff check src/ tests/  →  F401 'sqlalchemy.text' imported but unused
                            src/mkobi/services/processing_log_service.py:13
                            Found 1 error.
mypy src/              →  src/mkobi/workers/data_worker.py:740: error: Argument 3 to
                            "save_filter_values" … incompatible type
                            "list[str | int | float | bool]"; expected "list[str]"  [arg-type]
                          src/mkobi/workers/data_worker.py:818: error: (same)
                          pyproject.toml: note: unused section(s): module = ['tests.*']
                          Found 2 errors in 1 file (checked 115 source files)
```

`Makefile.ps1:221-249` read in full for the four gate bodies and the aggregate's guard structure;
the five CI/hook paths tested with `Test-Path`, all `False`. The two failing files last changed in
commits older than the remediation series that begins at `8505a62`, so both are properties of
committed code.

**Merge split** (Block 6). The claim "no gate is wired to an automated path" and "the aggregate
entry point does not reach the gates the project declares" is one concern with one root cause at one
site (`Makefile.ps1:241-249`), already filed by phase 09 as TST-002 — **phase 09 owns the
remediation** of that half, and its `Invoke-Test` recommendation supersedes this report's. The
claim that is **distinct and not in TST-002** is the gate redness itself: TST-002's "both suites
are red today" means pytest and vitest, and its coverage table rows for ruff and mypy read
"not run (phase 08)". The three diagnostics, with their exact locations, are phase 08's to
discharge. Neither report records the merge, which is the defect (VAL-08-007).

**Consequence** — The repository's stated quality surface is unpassable today; a contributor running
the documented aggregate learns nothing about the type errors, the ESLint result or the vitest
result, and may believe a change is fully checked when three gates never ran. Nothing runs any gate
automatically, so the green/red state depends entirely on a contributor choosing to run the command.

**Recommendation** — Usable as written, with the `test` half transferred to TST-002's ownership.
The three diagnostics are ordinary fixes; the one caveat is ordering, already stated in the input's
own roadmap: a gate that is red on day one is a gate that gets disabled, so the diagnostics should
land before the aggregate is rewired.

### QLT-004 — No schema-drift check exists, so a model change shipped without a migration would fail nothing

**Severity** — HIGH (re-graded from MEDIUM)

**Zone** — Schema drift: whether anything would notice, and which rows are written by code rather than by a migration

**Observation** — Disposition: **confirmed**; band **re-graded MEDIUM → HIGH** (VAL-08-002). The
absence is confirmed by inventory: `alembic check` and `command.check` appear nowhere in
`Makefile.ps1`, `docker/Dockerfile` or any compose file; the only alembic invocations in the
repository are `upgrade head` (three compose files' one-shot `migrate` service), `revision
--autogenerate` (`Makefile.ps1:260`) and `current` (`:264`). `alembic/env.py` sets
`compare_type=True`, which affects `--autogenerate` diffing only.

**Band.** Phase 08's own HIGH band enumerates *"schema drift no gate would notice"* verbatim, and
the finding's title is that sentence. The input's MEDIUM is not supported by the rubric, and the
rubric's HIGH preamble — "silent today, and the next change is guaranteed to be made wrongly in the
same place" — is satisfied exactly: no drift exists today, and a model column changed without a
revision fails per-column at runtime with nothing reporting it. The gap between MEDIUM and HIGH is
the difference between "a bounded correctness or operability gap with a specific, limited audience"
and a gate that is declared nowhere and would notice nothing.

**Evidence** — Absence established by search over `Makefile.ps1`, `docker/Dockerfile` and the
three compose files: no `alembic check`, no `command.check`. The positive half of the input's
evidence (`alembic check` → `No new upgrade operations detected.` against the dev database) was not
re-executed here — it requires entering the app container — and it is not what the finding rests on;
the finding is the absence, which is independently established. Recorded as unsettled in
Appendix K, not as confirmed.

**Consequence** — AGENTS.md rule 13 ("use database migrations for all schema changes") is enforced
only by the author remembering to run `.\Makefile.ps1 migration-new`. A model change that forgets
the revision ships silently: the app starts, and each model-derived query touching the new column
fails at runtime for that column alone, which is the worst shape for diagnosis.

**Recommendation** — Usable as written. Two of its three placement options are executable today;
the third — asserting at start-up beside `starter.py:160-169` — touches a file under active
remediation and should be sequenced after that programme lands. The input's own exclusion is correct
and load-bearing: `alembic check` must not be added to the `migrate` service, which has to be able
to run against a drifted database in order to repair it.

### QLT-005 — The declared toolchain carries artefacts for tools nothing invokes, one for a library the project forbids, and one exception naming a path that does not exist

**Severity** — MEDIUM (upheld)

**Zone** — Convention compliance: the cheap high-volume rules, and which of them are broken

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM; one enumeration error recorded
(VAL-08-009). Every anchor resolves exactly as cited: `[tool.black]` at `pyproject.toml:70-82`,
`[tool.isort]` at `:85-88`; dev dependencies black `:217`, isort `:218`, flake8 `:227`, autopep8
`:231`; `pandas-stubs==3.0.0.260204` at `:224`; the dead per-file ignore
`"src/mkobi/interfaces_old/*.py" = ["UP046"]` at `:143`, with `Test-Path src/mkobi/interfaces_old`
returning `False`. The root `package.json` is 11 lines, `devDependencies` only, **no `scripts` key**,
declaring `@types/js-yaml`, `@types/node`, `js-yaml`, `ts-morph`, `ts-node`, `tsx`, `typescript` —
**seven** names where the input says six. A search for `\bpandas\b` across `src/mkobi` returns 0
matches, so the forbidden library has no import to contradict the stub.

**Evidence** — `Test-Path src/mkobi/interfaces_old` → `False`; `Select-String "\bpandas\b"` over
`src/mkobi/**/*.py` → 0 hits; the root `package.json` read in full; `pyproject.toml` read in full at
every cited line.

**Consequence** — Four of the five declared Python quality tools can be run by a contributor and
will produce a different answer from the one the gate produces, with no record of which is
authoritative. The dead ruff exception and the dead root npm manifest each cost nothing at runtime
and each is a place a future contributor will look and find nothing; `pandas-stubs` puts a forbidden
library's type surface into the resolution path for a project that has no pandas.

**Recommendation** — Usable as written, and this is the one recommendation in the report that is
pure deletion with no gate result changing. One caveat the input does not state: deleting the root
`package.json` and `package-lock.json` is safe only while `.ai/builders/` is gone. It is deleted in
the working tree at this baseline but is a tracked deletion, not a commit — a checkout would restore
both the manifest and the tooling that needs it. Sequence the deletion after that tree is committed
as removed, or delete both in the same commit.

### QLT-006 — Ten of twelve repository providers in `deps.py` are annotated `-> Any` because their imports are deferred into the function body, and no cycle exists to require that

**Severity** — MEDIUM (upheld)

**Zone** — Type width and the sanctioned-suppression surface: what is enforced, what is silenced

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM; every one of the twelve
anchors resolves verbatim. `src/mkobi/api/deps.py` declares twelve repository factories; two are
typed — `get_user_repository() -> UserRepository` (`:152`) and
`get_dashboard_filter_values_repository() -> IDashboardFilterValuesRepository` (`:265`) — and ten
are `-> Any` at `:165, :175, :185, :195, :205, :215, :225, :235, :245, :255`, each deferring its
class import into the body at `:171, :181, :191, :201, :211, :221, :231, :241, :251, :261`.
`get_user_repository` carries the identical in-body import at `:161` and is typed anyway, which is
the input's own proof that the widening is accidental. `pyproject.toml:158 follow_imports = "skip"`
resolves the mechanism: a name that exists only inside a function body is `Any`, so the annotation
follows the placement rather than the class.

**Evidence** — All twelve factory signatures and all ten in-body imports read at the cited lines;
`pyproject.toml:152-169` read for the checker configuration; `uv run mypy src/` run in this
validation returns 2 errors and **none in `deps.py`**, which confirms the `Any` annotations satisfy
the checker rather than being forced on it — the input's claim, re-derived rather than inherited.

**Consequence** — Every route that takes a repository through `Depends` receives a value mypy treats
as untyped, so a renamed method, a changed argument order or a wrong keyword at a call site inside a
route is invisible to the checker. The checker does run over these modules, so the silence is
specific and permanent rather than incidental, and a reader comparing `:152` with `:165` has no way
to tell which is the intended house style.

**Recommendation** — Usable as written, and self-verifying: it names `uv run mypy src/` before and
after with the correct acceptance criterion (no new diagnostic). The `I*Repository` protocol
already exists in `mkobi.interfaces.repository_interfaces`, so the annotation half needs no new
abstraction — worth noting because that protocol is the sanctioned answer to "annotate with what",
and the input found it.

### QLT-007 — The client mirrors the server's fixed values in a second home with no equality check, and one mirrored value has already diverged

**Severity** — MEDIUM (upheld)

**Zone** — Fixed values: one named home per value, and what bypasses it

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM; all three anchors verified
independently. `tests/test_enum_db_consistency.py:223-227` declares exactly the three pairs claimed
(`user_role`/`UserRole`, `dashboard_permission_level`/`DashboardPermission`,
`processing_status`/`ProcessingStatus`) and never opens the client file.
`frontend/src/shared/types/__tests__/enums.test.ts` contains no reference to `src/mkobi`, to
"backend", or to `Barmode` — the client's only enum test compares literals against the same file
they are written in. `BarmodeEnum` (`src/mkobi/models/enums.py:148-151`) has exactly two members,
`GROUP` and `STACK`, while `frontend/src/features/dashboards/ui/charts/ChartRenderer.tsx:149`
casts the same field to `'group' | 'overlay' | 'relative' | 'stack'`, admitting two values the
server cannot produce. The server side of that field is typed, not free-form:
`src/mkobi/models/data.py:369` declares `barmode: BarmodeEnum = BarmodeEnum.GROUP`, so the two
admitted values are rejected at the request boundary rather than reaching storage.

**Evidence** — `BarmodeEnum` read from source (two members); `ChartRenderer.tsx:149` read;
`Select-String` over `enums.test.ts` for `src/mkobi|backend|Barmode` → 0 matches;
`ENUM_MAPPINGS` read at `:223-227`. The live `/openapi.json` was not re-read per-family for this
finding — the server-side shapes are established by the source read, and the barmode divergence is
a source-level fact on both sides.

**Consequence** — The client and server each hold a copy of the same fixed values and the only test
that names them checks one copy against itself. The barmode cast is the failure the duplication
produces in practice: a client author who writes `barmode: 'overlay'` gets a clean `tsc -b` and a
422 from the server, and the divergence is invisible in review because each side looks correct
locally. (The 422 shape is now the project's RFC 7807 `VALIDATION_ERROR`, not FastAPI's default,
since the graph model types `barmode` from the enum — the outcome is unchanged.) The six server
families with no client counterpart are the opposite direction: nothing states that their absence
is deliberate.

**Recommendation** — Usable, and the two halves have different costs, which the input already
separates. The narrow barmode cast is a one-line change with no build risk. The cross-tier check it
offers as the alternative to codegen — "one test that reads `backend/src/mkobi/models/enums.py`" —
names a path that does not exist in this repository: the backend lives at `src/mkobi/models/enums.py`
(there is no `backend/` directory). Correct that path before implementing; as written the test
cannot be written.

### QLT-008 — The accessible-dashboard rule has two inline implementations, and a comment names a third that the code never calls

**Severity** — MEDIUM (upheld)

**Zone** — One rule, one home: whether exactly one implementation exists

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM; all four anchors resolve.
`api/routes/graphs.py:173` reads "# Admin bypass is handled inside
`check_dashboard_access"`, and the three lines that follow test `current_user.role !=
UserRole.ADMIN` and build the accessible set inline (`:174-183`) without calling it.
`api/routes/layouts.py:154-166` is the near-copy in the same layer, and the same file calls the
shared helper at `:242` and `:246` — so the file already demonstrates the shared path and the
duplication is not a deliberate exclusion with an unrecorded reason.

**Evidence** — Both blocks read in full at the cited lines; the comment at `graphs.py:173` read
verbatim and compared against the three lines beneath it. The input's duplicate-scan figures (zero
byte-identical 8-line windows, five at 5 lines, this pair among the twelve at 4) were not
reproduced; they are a method description, not a load-bearing claim, and the pair it identifies is
confirmed directly. The input's two recorded false positives are accepted without re-derivation.

**Consequence** — A change to how the accessible set is computed has to be made in three places and
nothing names the other two. The comment at `graphs.py:173` is worse than a bare duplicate: a reader
who trusts it concludes the admin bypass is centralised, so a fix applied to `check_dashboard_access`
looks complete while two list endpoints still bypass it.

**Recommendation** — Usable as written, and its dependency discipline is correct: `api/deps.py:700`
already declares `require_dashboard_read_access` and its siblings, so the shared dependency has a
home rather than needing one invented. One ordering note the input omits — deleting the two inline
blocks removes the admin check from those two list endpoints unless the new dependency reproduces
it, so the replacement must be specified as "admin bypass included" before the old code is deleted,
not after.
### QLT-009 — Two exported StrEnum families are referenced by nothing in the repository

**Severity** — LOW (upheld)

**Zone** — The constant surface as a maintained artefact: is anything else maintaining it

**Observation** — Disposition: **confirmed, re-typed**; band upheld at LOW; the recommendation is
recorded **substantiated but unusable** (VAL-08-006). The census is correct: `ButtonVariant`
(`src/mkobi/models/enums.py:120-130`) and `ComponentSize` (`:133-138`) are defined, re-exported and
`__all__`-published (`models/__init__.py:65-66`, `:146-147`), and a search over `src/mkobi`,
`tests/` and `frontend/src/` returns **zero** references to either name outside `enums.py` and
`models/__init__.py`.

**Re-typed, because the specification corpus answers the question the finding leaves open.** The
input's Consequence rests on the families being unexplained — the rubric's LOW phrase is "an
unreferenced definition nobody has explained". They are explained, explicitly and twice:
`docs/SPEC.md:118` states that these two "are defined in the backend to support server-side
validation of dashboard layout configurations stored in the `layouts.definition` JSONB column …
where frontend concepts leak into the backend for validation purposes only", and
`docs/09-database/enums.md:48-49` records both with the intended use "Layout config validation
(JSONB)". A component no code path reaches that the specification expects is a **missing
integration, not dead code**, so the label changes: the defect is a documented intent with no
implementation, which is phase 08's declared-contract angle and therefore stays in this phase —
not a dead export. Supporting read: `layouts.definition` is unconstrained JSONB
(`db/models/layout.py:44-47`, `definition: dict[str, object]`) and
`LayoutService.create_layout` (`services/layout_service.py:36-66`) takes `definition: dict[str,
Any]` and passes it to `layout_repo.create` with no check against either enum, so the declared
validation is genuinely absent. **No runtime consequence today**, because nothing consults the
enums — the LOW band is correct.

**Evidence** — The census re-run: `Select-String "ButtonVariant|ComponentSize"` over the repository
returns 19 hits, of which the only code hits are `enums.py:120,133` and
`models/__init__.py:65,66,146,147`; the remainder are `docs/09-database/enums.md`,
`docs/SPEC.md` and this audit set. `docs/SPEC.md:118` and `docs/09-database/enums.md:48-49` read
verbatim. `db/models/layout.py:44-47` and `layout_service.py:36-66` read.

**Consequence** — Two public exports invite callers to use a vocabulary the server never consults,
while the specification asserts a validation they were created for that no code path performs. The
constant surface overstates what the system constrains, and the specification overstates what the
code does — in opposite directions, which is worse than either alone.

**Recommendation** — **Substantiated but unusable**, recorded as such rather than passed over. The
recommendation offers a choice between two answers ("If they are reserved for a component API not
yet built… if they are leftovers…") when the corpus has already given one: they are reserved, and
the reservation is recorded. A reader who executes it as written performs a fact-finding step the
repository has already completed, and may land on the wrong branch. Executable form: treat the
validation `docs/SPEC.md:118` describes as the unimplemented feature and either implement it or
amend the specification line and the `enums.md` rows; either way the two families stop being an
unexplained export.

### QLT-010 — The `dashboards` router tag is declared on the parent router and on every child router, so the published schema carries it twice

**Severity** — LOW (upheld)

**Zone** — Fixed values: one named home per value, and what bypasses it

**Observation** — Disposition: **confirmed on the tag claim, half refuted on the `redirect_slashes`
claim**; band upheld at LOW; the recommendation is not executable as written (VAL-08-004). The tag
duplication is confirmed against the live contract: `GET /openapi.json`, operation
`POST /api/v1/dashboards/{dashboard_id}/access`, returns `"tags": ["dashboards", "dashboards"]`.
The mechanism is `APIRouter.include_router`, which re-registers each child route with
`tags=current_tags` (`fastapi/routing.py:1767`) — the parent's tags concatenated with the child's.
`api/routes/dashboards.py:28` declares the tag and is the only `dashboards` router registered
directly on the application; the five children each declare the same literal again.

**The `redirect_slashes` half is refuted.** The input states that `dashboards_crud.py:28` sets
`False`, the other four omit it, "leaving FastAPI's default of `True`", and draws from that the
consequence that "the same subtree answers the two spellings of a trailing-slash URL differently
depending on which module owns the route". No such split exists, for two independent reasons.
First, `APIRouter.include_router` calls `self.add_api_route(...)` (`fastapi/routing.py:1762-1796`)
and passes **no** `redirect_slashes` argument at all, so every re-registered route takes
`add_api_route`'s default of `True` (`fastapi/routing.py:1125-1133`) whatever the child declared.
Second, and decisively, the slash-redirect decision is not per-route: `APIRoute` has **no**
`redirect_slashes` attribute in this FastAPI version (`AttributeError: 'APIRoute' object has no
attribute 'redirect_slashes'`, re-derived here), and the decision is made once by the application's
router from its own attribute (`starlette/routing.py:695`). `create_app` constructs
`FastAPI(...)` at `app.py:206-213` without a `redirect_slashes` argument, so the effective value is
Starlette's default `True` for the entire application. The `redirect_slashes=False` written on
`dashboards.py:28` is inert, and so is the one on `dashboards_crud.py:28`.

**Evidence** — Live `/openapi.json` read from the running dev stack for the tag. Static proof for
the rest, read from the installed packages: `fastapi/routing.py:1125-1133` (the default),
`:1762-1796` (the re-registration, no argument), `:1767` (the tag concatenation);
`fastapi/applications.py` — `FastAPI.include_router` has **no** `redirect_slashes` parameter;
`starlette/routing.py:570` (the default), `:579`, `:695` (the single global decision);
`src/mkobi/app.py:206-213` (the `FastAPI(...)` constructor, no argument). The `AttributeError` above
is the empirical confirmation, obtained by constructing the app in-process read-only.

**Consequence** — The published contract that clients generate from carries a duplicated tag on every
dashboard operation, and the tag grouping in generated docs shows each dashboard operation twice.
That is the whole of it: the `redirect_slashes` divergence the input also claims does not exist, so
the subtree answers both spellings of a trailing-slash URL the same way — uniformly, by redirect.

**Recommendation** — The first half is executable as written: delete `tags=["dashboards"]` from the
five child routers, keep it on the parent, verify by re-reading `/openapi.json`. The second half is
not executable and should be dropped from the recommendation: setting `redirect_slashes=False` on
any `APIRouter` changes nothing, because the value is discarded at `include_router` and the
decision belongs to the application's `FastAPI(...)` constructor. If the intent is to disable slash
redirecting, the only site that decides it is `app.py:206`.
## Validation-Level Findings

These are defects in the audited report itself, graded on phase 99's scale (effect and blast radius
anchored to present state), not on phase 08's. They occupy a separate section and are never
interleaved into the table above, because the two sections carry two different `Severity` scales.
Identifiers use `VAL-08-`; see the front-matter namespace note.

### VAL-08-001 — The input discharges its coverage-floor candidate on a plugin that is never constructed, and the delivered report contradicts phase 09's TST-003

**Severity** — CRITICAL

**Zone** — The Vacuous-Control Angle, and Its Bindings: Does It Exist, What Scope Does It Declare, What Did It Examine

**Observation** — Appendix B, row 9 ("The gates the project declares") records a **clean discharge**:
*"the 65 % coverage floor is live, not inert — `pyproject.toml:196` passes `--cov-fail-under=65`
without `--cov`, but pytest-cov 7.1.0 constructs its `CovController` at `pytest_configure`
regardless of `--cov` and sources measurement from `[tool.coverage.run] source = ["src/mkobi"]`, so
`pytest` under `Makefile.ps1:196` does enforce it (`pytest_cov/plugin.py:225-254`, `:369-376`)."*

Every one of those four steps is a non sequitur, and the mechanism is one screen above the lines
cited. `pytest_cov/plugin.py:190-204`:

```python
def pytest_load_initial_conftests(early_config, parser, args):
    ...
    if early_config.known_args_namespace.cov_source:
        plugin = CovPlugin(options, early_config.pluginmanager)
        early_config.pluginmanager.register(plugin, '_cov')
```

`CovPlugin` is instantiated and registered **only if `cov_source` is truthy**, and `cov_source` is
populated exclusively by `--cov` / `--cov=<path>`. `--cov-fail-under` is a different option: it sets
`cov_fail_under`. With the project's `addopts` — `--import-mode=importlib -ra -v
--strict-markers --cov-fail-under=65` (`pyproject.toml:196`), no `--cov` — the condition is false,
the plugin is never registered, and every line the input cites becomes unreachable: the
`__init__` at `:225-254` never runs; the `pytest_runtestloop` wrapper at `:324-383`, which calls
`cov_controller.finish()`, `cov_controller.summary()` and `should_fail_under` at `:373`, is never
invoked; and `pytest_terminal_summary` returns at `:398-399` on `cov_controller is None`. The
control that emits the floor's verdict is not merely examining nothing — it does not exist in the
run.

**Evidence** — The installed plugin at pytest-cov 7.1.0, read at the lines above; `pyproject.toml`
read in full, `addopts` at `:196` and `[tool.coverage.run]` at `:207-208`; `Makefile.ps1:196` read
(`pytest`, bare). Independent corroboration inside the set: phase 09's TST-003 records the same
conclusion from a **1013-test runtime run in which the header listed `cov-7.1.0` as loaded and no
coverage table and no threshold verdict were emitted**. Two phases in this audit set therefore
state opposite conclusions about one control, and this input's is the false one.

**Consequence** — A wrong approval, recorded as an established clean result rather than as an
omission, in a delivered report. A reader who trusts Appendix B concludes the backend coverage
floor is enforced, and therefore has no reason to act on TST-003's recommendation to add
`--cov=src/mkobi` to `addopts` — which is precisely the change that makes the floor real. Because
the same report's remediation for the gate area (QLT-003) is about wiring, not about the floor, a
reader who accepts both halves concludes the coverage surface needs nothing. The mitigating fact,
recorded so the reader can weigh it: phase 09 filed the true finding independently, so the defect
reaches the roadmap through TST-003 and no work is lost. What is wrong **now** is the delivered
statement.

**Recommendation** — Delete the Appendix B row 9 claim and replace it with the refutation, naming
`pytest_cov/plugin.py:202-204` as the reason; the two other discharged items in that row (the
vitest thresholds and the pytest floor being fixed numbers rather than deltas) are separately
owned by TST-004 and TST-003 and should be cross-referenced rather than asserted. Do not
re-derive the plugin behaviour from `__init__` or from the fail-under evaluation alone: both live
inside a class that is conditionally constructed, and the condition is the whole answer.

### VAL-08-002 — QLT-004 is banded MEDIUM where phase 08's own rubric assigns HIGH verbatim, so the roadmap carries the drift risk at the wrong weight

**Severity** — HIGH

**Zone** — The Grade against the Audited Phase's Own Rubric

**Observation** — QLT-004 is filed MEDIUM. Phase 08's severity section
(`.kilo/commands/audit/phases/08-audit-code-quality.md:162`) assigns **HIGH** to, verbatim,
*"schema drift no gate would notice"*, under a HIGH preamble of *"silent today, and the next change
is guaranteed to be made wrongly in the same place"*. QLT-004's title is *"No schema-drift check
exists, so a model change shipped without a migration would fail nothing"* — the rubric sentence
in the finding's own words. Both halves of the preamble are met: the report establishes there is no
drift today, and a column added to a model without a revision fails per-column at runtime with no
gate reporting anything. No MEDIUM clause covers it: MEDIUM is *"a bounded correctness or
operability gap with a specific, limited audience"*, and a schema change affects every request that
touches the changed column.

**Evidence** — The audited rubric read at `:157-164`; QLT-004 read in full. The gap is visible
inside the report itself: QLT-003, which carries the same rubric's other verbatim HIGH clause
("an aggregate entry point that silently omits a declared gate"), **is** banded HIGH, so the two
gate findings share a cause (Cross-Finding Analysis, second group) and one is banded a level above
the other. Re-grade applied as **HIGH**, recorded here rather than silently.

**Consequence** — A real defect released below the weight its own rubric implies. The report groups
QLT-003, QLT-004 and QLT-005 as one cause and orders them as *step 3* of six, behind the two
behavioural fixes; at MEDIUM the drift risk carries less scheduling weight than the pure-deletion
QLT-005 in *step 4*'s company, and it is the one in that group whose failure mode is a runtime
error per column rather than a stale configuration file.

**Recommendation** — Re-band QLT-004 to HIGH and re-order step 3 ahead of step 4 in the Roadmap,
or record why the drift risk is deliberately sequenced behind the deletions. No code change; the
finding's content and its recommendation are both sound.

### VAL-08-003 — QLT-001's CRITICAL band rests on a storage claim the schema refutes, and the input's own recommendation contradicts it

**Severity** — MEDIUM

**Zone** — The Grade against the Audited Phase's Own Rubric

**Observation** — QLT-001 is the only finding carrying CRITICAL, and it is the only place the band is
claimed. It does not survive. Phase 08's CRITICAL is *"a wrong or lost value is in storage now, or
the only thing that kept a rule true for everyone is gone"* — and the storage half is refuted by the
schema: `dashboard_access.permission` is a **native PostgreSQL enum**
(`db/models/access.py:43-52`; `alembic/versions/000000000000_initial_migration.py:27-30,152`), the
live type in `bidb` holds exactly `view,edit,admin`, and
`SELECT 'read'::dashboard_permission_level` returns
`ERROR: invalid input value for enum dashboard_permission_level: "read"`. A value outside the
vocabulary cannot be stored, and after a downgrade attempt the stored value is the one the system
created under that constraint — not a wrong one. The rubric's third clause, "two implementations of
one rule whose copies already disagree on a value the system acts on", is satisfied only for the
aliases `read` and `write`, which by the same constraint never reach a decision path; the three
implementations agree on all three real values. What remains lands on HIGH's own clauses: *"a
declared invariant nothing enforces"* and *"a value with two homes"*.

The report is internally inconsistent on this point, and the inconsistency is the tell: QLT-001's
Recommendation says to "give the value one typed home … change … to `DashboardPermission`, delete
the `str = "view"` defaults", which is the correct remedy **for a column nothing constrains**. A
column nothing constrains is a premise the schema refutes. The report never mentions the enum.

**Evidence** — The live enum type read from `bidb` (`SELECT t.typname, string_agg(e.enumlabel, ',')
FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid WHERE t.typname = 'dashboard_permission_level'`
→ `dashboard_permission_level|view,edit,admin`); the cast rejection above; the model and migration
declarations read; the audited rubric read at `:161`. Re-grade applied as **HIGH**, with the
competing reading recorded inside QLT-001's Observation so the reader may overrule it.

**Consequence** — The audit set's only CRITICAL band is unoccupied, and the finding that occupied it
is a HIGH. That is a report the reader must repair before acting: phase 08's CRITICAL band reads as
the set's top authorization-risk item, and the remediation ordering in the Roadmap (step 1 before
step 2) is justified partly on it. Banded at MEDIUM rather than CRITICAL because the taxonomy's
CRITICAL band is reserved for a wrong *approval*, and an over-stated band is not one — it inflates
the roadmap without hiding anything. The finding itself is real and reaches the roadmap.

**Recommendation** — Re-band QLT-001 to HIGH and add one sentence to its Observation recording the
storage constraint, because the constraint is what makes the remediation a typing change rather
than a data-integrity repair, and because it is the ground on which a future reader will test the
CRITICAL claim again.

### VAL-08-004 — QLT-010's second claim is refuted by the framework, and its recommendation's second half would change nothing if executed

**Severity** — MEDIUM

**Zone** — Whether the Recommendation Can Be Carried Out

**Observation** — QLT-010 makes two claims and recommends two changes. The first (a duplicated
`tags` literal on the parent and five child routers) is confirmed live. The second is refuted:
`APIRouter.include_router` re-registers each child route without passing `redirect_slashes`
(`fastapi/routing.py:1762-1796`), so every route takes `add_api_route`'s default of `True`
(`:1125-1133`); `APIRoute` carries no per-route `redirect_slashes` attribute at all; and the
decision is made once from the application's router attribute
(`starlette/routing.py:695`, default at `:570`), which `create_app` leaves unset
(`app.py:206-213`). The two `redirect_slashes=False` declarations in the repository are therefore
both inert, and there is no per-module split. The recommendation's second half — *"set
`redirect_slashes=False` explicitly on all five so the subtree answers uniformly"* — is aimed at a
behaviour those declarations cannot reach; executing it leaves the subtree exactly as it is.

**Evidence** — The installed `fastapi/routing.py`, `fastapi/applications.py` and
`starlette/routing.py` read at the lines cited; `src/mkobi/app.py:206-213` read; the
`AttributeError` on `APIRoute.redirect_slashes` obtained by constructing the app in-process,
read-only. The tag claim re-derived from the live `/openapi.json`.

**Consequence** — Half a recommendation the reader must repair before acting. A reader who executes
it in full will believe the subtree's slash behaviour is now uniform by declaration, when the
subtree was uniform already and the real decision site is the `FastAPI(...)` constructor. The
refutation is worth more than the finding's remaining half, because it identifies a live
**declared contract with no enforcement point** (`redirect_slashes=False` written twice, honoured
nowhere) which is phase 08's own block-8 angle and which the report noticed only as a consequence.

**Recommendation** — Delete the `redirect_slashes` half of QLT-010's Observation, Consequence and
Recommendation, and keep the tag half, which stands. If the slash behaviour is worth a finding in
its own right, the honest one is: two routers declare `redirect_slashes=False`, neither declaration
reaches the behaviour, and the application's router default is `True`.
### VAL-08-005 — QLT-002's recommendation selects its enforcement site on a premise the working tree refutes

**Severity** — MEDIUM

**Zone** — Whether the Recommendation Can Be Carried Out

**Observation** — QLT-002's recommendation opens: *"Make the declared audience executable at the
single place the rule belongs: resolve the caller's `admin` permission on the target dashboard
inside `DashboardService.grant_access` (**it is the only caller of
`AccessRepository.grant_access`**)…"*. The parenthetical is false. `AccessRepository.grant_access`
has **two** production callers: `services/dashboard_service.py:385` inside
`DashboardService.grant_access`, and `services/dashboard_service.py:104` inside
`create_dashboard`, which grants `DashboardPermission.ADMIN` to the new dashboard's owner
(`:102-109`). The stated justification for placing the check at the service method does not hold.

**Evidence** — `grant_access` call sites enumerated across `src/mkobi`: exactly two
(`dashboard_service.py:104`, `:385`) plus the two protocol declarations in
`interfaces/service_interfaces.py:227` and `interfaces/repository_interfaces.py:86`. Both bodies
read in full.

**Consequence** — A reader who executes the recommendation as justified will enforce the rule at one
site, find the second caller they were told did not exist, and have to decide again what to do with
it. The second site is benign — it grants to the owner of a dashboard being created in the same
call — so the repair is small, but the report asserts a uniqueness that is not there and a reader
who trusts it has been misdirected about the blast radius of their own change. The finding's core
claim (declared audience, no enforcement) is unaffected and remains confirmed at HIGH.

**Recommendation** — Correct the parenthetical to name both callers, and state which site the rule
belongs at. `DashboardService.grant_access` remains a defensible choice provided the
create-dashboard grant is named as a deliberate second exemption or covered by the same check.

### VAL-08-006 — QLT-009 asserts two families nobody has explained; the specification explains both, which makes its recommendation a question already answered

**Severity** — MEDIUM

**Zone** — Which Side Moves: Code or Documentation

**Observation** — QLT-009's Consequence and Recommendation both rest on the families being
unexplained: *"Two public exports invite callers to use a vocabulary the server never consults"*
and *"Establish which of the two answers the question is for. If they are reserved … if they are
leftovers …"*. The specification corpus answers it in two places: `docs/SPEC.md:118` states these
enums "are defined in the backend to support server-side validation of dashboard layout
configurations stored in the `layouts.definition` JSONB column", and
`docs/09-database/enums.md:48-49` lists both with the intended use "Layout config validation
(JSONB)". A component no code path reaches that the specification expects is a missing integration,
not dead code. The report never asks the corpus.

**Evidence** — `docs/SPEC.md:118` and `docs/09-database/enums.md:48-49` read verbatim; the census
re-run (zero references to either family in `src/mkobi`, `tests/`, `frontend/src/` outside
`enums.py` and `models/__init__.py`); the absence of the declared validation confirmed —
`db/models/layout.py:44-47` stores `definition` as unconstrained JSONB and
`LayoutService.create_layout` (`services/layout_service.py:36-66`) passes `definition: dict[str,
Any]` through to `layout_repo.create` unchecked.

**Consequence** — A report the reader must repair before acting. Two directions of drift are in
play and the report names only one: the constant surface advertises a vocabulary nothing consults,
*and* the specification advertises a validation the code does not perform. The executable half of
the defect — implement the declared validation, or amend the two documents that declare it — is
invisible to a reader who believes the families are unexplained leftovers and deletes them, because
deleting them removes the named vocabulary of a validation the specification still claims exists.

**Recommendation** — Replace the two-branch recommendation with the single action the corpus
supports: implement the `layouts.definition` validation `docs/SPEC.md:118` describes, or amend that
line and the two `enums.md` rows. Retain the census — 0 references is correct and is the evidence
that the validation is unimplemented.

### VAL-08-007 — QLT-003 and TST-002 claim the same concern from two phases with no merge ruling on either side, and neither report is complete

**Severity** — MEDIUM

**Zone** — Cross-Phase Conflict, Ownership and Merge

**Observation** — Two reports claim the same root cause at the same site. Phase 08's QLT-003: "no
declared gate is wired to an automated path" and "`Invoke-Check` short-circuits on the first
failure, so `typecheck`, `fe-lint` and `fe-test` are unreachable through the entry point
contributors are pointed at". Phase 09's TST-002: "nothing in the repository invokes any gate:
there is no `.github/` directory, `Makefile.ps1 check` chains ruff, mypy, eslint and vitest but
never pytest". Both resolve to `Makefile.ps1:241-249` and to the same absence inventory. **Neither
report records the overlap** — phase 08's Appendix C lists phase 09 only as "QLT-003 | Phase 09 —
test coverage | QLT-003 files only that the declared gates are red and unreachable through the
aggregate entry point; what the suite would notice is phase 09's", and phase 09's report does not
name QLT-003.

The overlap is not total, and the correct ruling is a partial merge rather than a wholesale one:
TST-002's "both suites are red today" means pytest and vitest, and its coverage table rows for ruff
and mypy read "not run (phase 08)" — so the three backend diagnostics, their exact locations, and
their proof that they are properties of committed code rather than of the concurrent remediation
programme, appear **only** in QLT-003. Conversely TST-002's stronger claim — that the aggregate
never invokes pytest at all, which is independent of the short-circuit and confirmed here at
`Makefile.ps1:241-249` — appears **only** in TST-002, and QLT-003's recommendation proposes
"add a `test` invocation to `Invoke-Check`", which TST-002 also proposes.

**Evidence** — Both reports read; `Invoke-Check` read at `Makefile.ps1:241-249` (no `Invoke-Test`);
`.github`, `.pre-commit-config.yaml`, `.gitlab-ci.yml`, `azure-pipelines.yml` and `.circleci`
confirmed absent; both backend gates re-run here and red with the input's exact diagnostics.
Phase 09's report is raw (auditor), not validated; no sibling validation report for phase 09 exists.

**Consequence** — Two phases claiming one concern, with the split not drawn by either: a reader who
remediates QLT-003 alone reorders the aggregate without wiring pytest; a reader who remediates
TST-002 alone fixes the wiring without clearing the three diagnostics that make the backend gates
red on day one — and a gate that is red when introduced is a gate that gets disabled, which both
reports state independently.

**Recommendation** — **Phase 09 owns remediation of the entry-point and automation half** (TST-002
and its `Invoke-Test` recommendation); phase 08 retains the gate-redness half, which TST-002's own
coverage table defers to it. QLT-003 is not renumbered. The aggregate rewiring must land after the
three diagnostics are cleared — this validation's ordering, from re-running both gates at
`b23a9cb`.

### VAL-08-008 — QLT-001's evidence records a value the storage tier rejects as "accepted by this endpoint", and the resulting 200/500 divergence reaches no finding

**Severity** — MEDIUM

**Zone** — The Claim Re-Derived from the Executing Path

**Observation** — QLT-001's Evidence states: *"The `read` alias is accepted by this endpoint (HTTP
200, `"permission": "read"`) while `check_dashboard_access(required_permission="read")` raises
`ValueError` at `core/permissions.py:150-151`; both facts were observed in the same session."* The
first half does not show what it is offered as evidence for. `DashboardService._validate_permission`
(`services/dashboard_service.py:482-501`) does accept the alias — it normalises and validates
`DashboardPermission(normalized)`, which succeeds — so the request passes the boundary. The 200 is
produced by a different mechanism: `AccessRepository.grant_access` returns the **existing** row at
`access_repo.py:57-63` before any write is attempted, and the handler echoes the request body at
`dashboards_access.py:99-104`. The alias is accepted; it is never applied, and it could not be.

The unfiled divergence follows from the two facts the report already holds but does not connect. On
a `(user_id, dashboard_id)` pair that **already** has a row, `permission="read"` skips the write and
returns **200** echoing `"permission":"read"`. On a pair that **does not**, the same request reaches
`access_obj = DashboardAccess(..., permission="read")` at `access_repo.py:65-69`, PostgreSQL rejects
the value (`ERROR: invalid input value for enum dashboard_permission_level: "read"`), the
`SQLAlchemyError` is re-raised at `:80-87`, and the handler's catch-all at
`dashboards_access.py:118-127` converts it to `AppException(code=ErrorCode.INTERNAL_ERROR)` — **500**.
One legal-looking input, two status codes, decided by prior state, neither of them correct.

**Evidence** — The two code paths read in full; the enum rejection reproduced against `bidb` with
`SELECT 'read'::dashboard_permission_level`; the error-to-status path read at `access_repo.py:80-87`
and `dashboards_access.py:110-127`. The 500 was derived from those three artefacts rather than
executed, and is recorded as derived in Appendix K rather than as measured.

**Consequence** — A reader acting on the filed evidence would conclude `read` is a grantable
permission, and would carry that belief into the remediation: QLT-001's recommendation deletes the
`read`/`write` branches and re-types the field, which happens to be the right fix, but for the
wrong stated reason. The 500-on-new-row behaviour reaches no finding, no roadmap step and no
rollout note, and it is the shape an integrator hits first: a client that sends `read` once gets
200 and believes it works, and then gets 500 on the next dashboard.

**Recommendation** — Correct the Evidence sentence to state that the 200 is the no-op branch rather
than acceptance, and file the 200/500 divergence as a third element of QLT-001 (it is the same
boundary and the same root cause, so it needs no new identifier): the boundary accepts a value the
storage tier cannot hold, and whether the failure surfaces as a false success or as a 500 depends on
whether the row already exists.
### VAL-08-009 — Two census counts in the input are wrong, and both understate

**Severity** — LOW

**Zone** — The Claim Re-Derived from the Executing Path

**Observation** — Two enumeration errors, neither of which changes a disposition.

QLT-001's Observation states *"Sixteen production call sites pass the bare literals `"view"`, `"edit"`
and `"admin"`"*. A search for `required_permission\s*=\s*"(view|edit|admin)"` over `src/mkobi`
returns **21** sites — `deps.py:729, 773, 817, 872, 878, 884`; `dashboards_crud.py:354, 449`;
`data.py:91`; `graphs.py:100, 249, 337, 447`; `layouts.py:246`;
`processing_configs.py:85, 165, 249`; `data_service.py:122, 267, 331, 365` — before any `permission=`
site is counted. The claim understates by at least five.

QLT-005's Observation states the root `package.json` declares *"six devDependencies
(`@types/js-yaml`, `@types/node`, `js-yaml`, `ts-morph`, `ts-node`, `tsx`, `typescript`)"*. The
enumeration lists **seven**.

**Evidence** — `Select-String` for `required_permission\s*=\s*"(view|edit|admin)"` over
`src/mkobi/**/*.py` → 21 matches, listed above; the root `package.json` read in full (11 lines,
seven entries in `devDependencies`, no `scripts` key).

**Consequence** — Drift with no remediation consequence today: both counts err in the direction that
understates the population, so no reader is sent to a site that does not exist and no remediation is
scoped wrongly. Recorded because the same arithmetic style is load-bearing elsewhere in the audit
set — a count that supports a "sixteen call sites" blast-radius claim is exactly the kind of number
a reader does not re-derive.

**Recommendation** — Correct both counts to 21 and seven, or drop the numerals and cite the search
that produces them.

## Disposition Tally

| Disposition | Count | Findings |
|---|---|---|
| confirmed, no change to disposition or band | 5 | QLT-002, QLT-005, QLT-006, QLT-007, QLT-008 |
| confirmed, **band re-graded** | 2 | QLT-001 (CRITICAL → HIGH), QLT-004 (MEDIUM → HIGH) |
| confirmed, **re-typed** | 1 | QLT-009 (dead export → missing integration) |
| confirmed, **merged in part** | 1 | QLT-003 (entry-point half → TST-002; phase 09 owns remediation) |
| confirmed, **one claim refuted** | 1 | QLT-010 (`redirect_slashes` half) |
| not substantiated | 0 | — |
| unsettled | 0 | — |
| renumbered | 0 | none |

The rows are mutually exclusive: each finding appears once, under its primary disposition. Ten in
total. Four findings carry a secondary annotation — QLT-001 (asserted cause partly wrong), QLT-002
(strengthened: `current_user` is unused), QLT-007 (recommendation names a non-existent path) and
QLT-005 (recommendation carries an unstated sequencing constraint) — and each is recorded inside
that finding's Observation rather than as a separate disposition.

Bands after re-grade: **CRITICAL 0 / HIGH 4 / MEDIUM 4 / LOW 2** (10). Bands as filed:
CRITICAL 1 / HIGH 2 / MEDIUM 5 / LOW 2. The two movements are QLT-001 down (VAL-08-003) and QLT-004
up (VAL-08-002). The front matter carries the post-re-grade tally; the audited identifiers and
their as-filed bands are recoverable from the input report and are not restated here as the tally.

Validation-level tally: **CRITICAL 1 / HIGH 1 / MEDIUM 6 / LOW 1** (9).

Negative results tested rather than accepted — the input's two dismissed candidates and its four
"discharged with no finding" appendix claims:

| Claim | Test | Verdict |
|---|---|---|
| block 7: no `print(` in `src/mkobi` | accepted without re-derivation; not load-bearing for any finding | as filed |
| block 7: `sys.stdout` is the logging target | accepted without re-derivation | as filed |
| block 7: **Cyrillic at `filter_service.py:299` is a deliberate character class** | line read: `re.match(r'^[a-zA-Zа-яА-Я0-9\s\-_.]+$', name)` inside `_validate_filter_name` | **dismissal sound** — a permitted input range, not prose; AGENTS.md's English-only rule covers comments, logs, docstrings and messages |
| block 9: **the 65 % coverage floor executes without `--cov`** | `pytest_cov/plugin.py:202-204`, plus `:324-383`, `:398-399`; corroborated by phase 09's 1013-test run | **dismissal refuted** — VAL-08-001, CRITICAL |
| block 9: both thresholds are fixed numbers, not deltas | `pyproject.toml:196` and `:212` both state 65 | as filed; now cross-referenced to TST-003/TST-004 |
| block 10: no drift exists today | `alembic check` not re-executed here (see Appendix K); the absence claim is what the finding rests on and is confirmed | as filed, not re-run |

## Distribution

The findings fall on four surfaces, and the two that matter are the same three lines of
`dashboards_access.py`. `src/mkobi/api/` plus `core/permissions.py` carry four findings
(QLT-001, QLT-002, QLT-006, QLT-008) and the declared gate/toolchain surface
(`Makefile.ps1`, `pyproject.toml`, root `package.json`, `alembic/env.py`) carries three
(QLT-003, QLT-004, QLT-005); after re-grade those three are the only HIGH-band non-authorization
findings in the phase, because both gate-redness and drift-absence sit in the same band. The client
tier carries one (QLT-007) and the constant surface one (QLT-009). The validation-level findings
concentrate on the input's **negative** results rather than its findings: eight of the nine concern
discharged blocks, refuted premises or band arithmetic, and only VAL-08-007 and VAL-08-009 touch a
finding's own content.

- Authorization value and enforcement surface — QLT-001 (HIGH), QLT-002 (HIGH), QLT-008 (MEDIUM)
- Declared gates, drift and toolchain — QLT-003 (HIGH), QLT-004 (HIGH), QLT-005 (MEDIUM)
- Fixed-value homes and type width — QLT-006 (MEDIUM), QLT-007 (MEDIUM), QLT-010 (LOW)
- Constant-surface hygiene — QLT-009 (LOW)
- The input's own discharged blocks, premises and bands — VAL-08-001 (CRITICAL) … VAL-08-009 (LOW)

## Cross-Finding Analysis

The input's two causes hold, and both are confirmed from the executing path rather than inherited.

**The dashboard-access rule has no single enforcement point** (QLT-001, QLT-002, QLT-008) stands,
with one amendment this validation makes: the fourth member the input's own Consequence does not
name is not another enforcement gap but a **storage constraint**. The value those endpoints write is
held by a native PostgreSQL enum, which is why QLT-001's false success cannot corrupt a row and why
its band falls to HIGH. That constraint is also why QLT-002's blast radius is narrower than the
report states: an escalated `admin` grant is effective on the read paths (that part is confirmed),
but it cannot be given a value outside the three the read paths recognise.

**Declared rules maintained as configuration rather than enforcement** (QLT-003, QLT-004, QLT-005,
and QLT-006 inside one file) stands and strengthens. QLT-004 joins QLT-003 in the HIGH band on the
rubric's own wording, and the input's Appendix B row 9 is an instance of the same shape at the level
of the report: a control recorded as deciding something when it decides nothing.

QLT-007, QLT-009 and QLT-010 remain independent of each other and of the two groups. QLT-009's
re-type is worth noting against the second cause rather than the first: a declaration in
`docs/SPEC.md` that no code path implements is the same configuration-not-enforcement shape, in the
specification tier rather than the toolchain tier.

## Roadmap

Ordered by cause, as the audited rubric's phase requires a re-grade to reach the roadmap. Phase 08's
own ordering is preserved where this validation did not re-band; the two changes below are the only
additions.

**Step 0 — correct the report before any of it is scheduled.** Fix the four items a reader must
repair before acting, in this order because one blocks the others: VAL-08-001 (delete the
coverage-floor discharge — TST-003 already owns the finding); VAL-08-002 and VAL-08-003 (re-band
QLT-004 up, QLT-001 down, so the CRITICAL band reads correctly); VAL-08-006 (replace QLT-009's
two-branch recommendation with the single action the specification already implies). Nothing in step
0 changes the product; everything after it is scheduled against a report that no longer
contradicts a sibling.

**Step 1 — close the false success before closing the authorization gap** (phase 08's own step 1).
Unchanged and confirmed: fix QLT-001's write path, then type the four `str` declarations, delete the
`read`/`write` branches. Two corrections ride along: add the 200/500 divergence (VAL-08-008) to the
finding, and correct the call-site count to 21 (VAL-08-009). No shipped test blocks this — no test
exercises the grant endpoint or asserts the no-op. **Must be true before step 2:** the refusal path
has a typed permission value to report.

**Step 2 — make the declared audience executable** (phase 08's own step 2). Unchanged, with
VAL-08-005's correction applied: the check must cover `create_dashboard`'s grant at
`dashboard_service.py:104` as well, or that site must be named as an intentional exemption.
Coordinate with phase 12 before either change touches `dashboards_access.py`; phase 12 has not run.

**Step 3 — make the gates say what they decide** (phase 08's own step 3, now the highest band in the
phase). Clear the three diagnostics first (QLT-003), then the aggregate rewiring — which phase 09
owns under TST-002, not phase 08 — and then `alembic check` (QLT-004, now HIGH). **Ordering
constraint added by VAL-08-007:** the rewiring must not land before the diagnostics are cleared, or
the new gate is red on introduction. This step is independent of steps 1-2.

**Step 4 — the toolchain deletions** (QLT-005, QLT-009, QLT-010). One correction: QLT-010's
`redirect_slashes` half is dropped (VAL-08-004) and its tag half is kept; QLT-005's deletion of the
root `package.json` must land after `.ai/builders/` is committed as removed. Pure deletion.

**Steps 5-6 — unchanged** (QLT-007's cross-tier check and barmode cast; QLT-006 and QLT-008's
cleanups), with the two ordering notes already recorded in their blocks: the enums test reads
`src/mkobi/models/enums.py`, not `backend/…`; and QLT-008's shared dependency must include the admin
bypass before the two inline blocks are deleted.

## Rollout Safety

Only steps 1-3 change observable behaviour, and this validation's re-grading changes what each is
worth watching.

**Step 1** turns a silent no-op into a real write on the re-grant path. A deployment that depended
on the no-op starts applying downgrades it previously ignored; grep `dashboard_access` for grants
that must stay elevated before merging. Typing the four `str` declarations narrows what the endpoint
accepts, and the 200/500 divergence (VAL-08-008) means a client sending `read` currently gets 200 on
an existing row and 500 on a new one — after the fix it gets 422 on both, which is the change most
worth announcing. No stored row is rewritten by the fix and no data migration is involved; revert by
reverting the commit.

**Step 2** turns a 200 into a 403 for every caller that is neither owner nor administrator. That is
the intended correction and the one change that can break a working client flow; treat any such
caller as a defect to fix rather than a client to accommodate. It now also covers the
create-dashboard grant path (VAL-08-005), so the surface that changes is one call site wider than
phase 08's own rollout note assumed. Verify by replaying QLT-002's Evidence: the `viewer`-token
grant must return 403 and `dashboard_access` must gain no row.

**Step 3** changes what the contributor sees. The added constraint from this validation: the
aggregate rewiring is phase 09's to make and must not precede the three diagnostics, or the gate is
introduced red and gets disabled — the failure mode both phase 08 and phase 09 name independently.
`alembic check` returns clean at `b23a9cb`, so adding it introduces no failure on this revision;
keep it out of the `migrate` service, which must be able to run against a drifted database in order
to repair it.

Steps 4-6 change no runtime behaviour. Step 4's remaining choice — which formatter is authoritative —
is safe today because no gate invokes black or isort, and unsafe the moment someone adds one.
## Appendices

### Appendix A — Block 1: claim re-derivation ledger

Every anchor resolved mechanically before its claim was tested. `HEAD` equals the input's recorded
baseline, so no anchor moved.

| Finding | Anchor set resolved | Claim tested on the executing path | Result |
|---|---|---|---|
| QLT-001 | all 14 cited anchors resolve at `b23a9cb` | write path, discarded normalisation, four `str` homes, unread `PERMISSION_LEVELS`, no second surface, published schema | core claim confirmed; headline imprecise; asserted cause partly wrong; band re-graded |
| QLT-002 | all 6 resolve | three declarations, published `security`, handler body, service body | confirmed and strengthened — `current_user` is unused, not a log field |
| QLT-003 | all 5 resolve | both gates re-run; `Invoke-Check` read | confirmed verbatim; short-circuit correct; TST-002's stronger claim also confirmed |
| QLT-004 | 3 of 4 resolve (`alembic check` result not re-run) | absence of any drift check | confirmed; band re-graded |
| QLT-005 | all 8 resolve | dead path, forbidden stub, root manifest | confirmed; one count wrong |
| QLT-006 | all 12 resolve | ten `-> Any`, two typed, ten in-body imports, `follow_imports = "skip"` | confirmed verbatim; `mypy src/` re-run, `deps.py` clean |
| QLT-007 | 3 of 3 resolve | `ENUM_MAPPINGS`, tautological client test, barmode cast | confirmed; alternative recommendation names a path that does not exist |
| QLT-008 | all 4 resolve | two inline copies, the misleading comment, the same-file shared calls | confirmed verbatim |
| QLT-009 | both resolve; census re-run | zero references | census confirmed, label re-typed |
| QLT-010 | both resolve | duplicated tag (live); `redirect_slashes` split | tag confirmed; `redirect_slashes` claim refuted |

### Appendix B — Block 2: the vacuous-control angle, applied to this input

Existence, declared scope, what was actually examined, and the path by which a verdict could have
reached a decision — kept apart from "did it run", which is not "did it decide".

| Control | Exists | Declared scope | Actually examined | Verdict path | Verdict |
|---|---|---|---|---|---|
| `ruff check src/ tests/` (`Makefile.ps1:222`) | yes | `src/` + `tests/` | 1 item, re-run here | `Invoke-Lint`; first link of `Invoke-Check` | **decides** — 1 error, red |
| `mypy src/` (`:230`) | yes | `src/` only (`tests/`, `alembic/` excluded at `pyproject.toml:169,184`) | 2 errors, re-run here | `Invoke-Typecheck`; **unreachable** behind a red lint | decides, but unreachable through the aggregate |
| `addopts --cov-fail-under=65` (`pyproject.toml:196`) | the flag exists | whole-project coverage floor | **nothing** — `CovPlugin` never registered (`pytest_cov/plugin.py:202-204`) | none: no plugin, no report, no threshold verdict | **vacuous — VAL-08-001** |
| `[tool.ruff.lint.per-file-ignores] src/mkobi/interfaces_old/*.py` (`:143`) | yes | one path | 0 items — the path does not exist | `ruff` loads the config and matches nothing | **vacuous, correctly recorded** by QLT-005 |
| `alembic/env.py compare_type=True` (`:79,:91`) | yes | `--autogenerate` diffing only | n/a by design | not a gate; no invocation | **not a gate, correctly recorded** by QLT-004 |
| `PERMISSION_LEVELS` (`core/permissions.py:38-42`) | yes | a permission-ordering table | 0 readers | none | **vacuous, correctly recorded** by QLT-001 |
| `Invoke-Check` aggregate (`:241-249`) | yes | 4 declared gates | 1 of 4 reachable today | returns on the first non-zero exit | **partially vacuous** |

Three controls are vacuous and the input records two of them correctly; the third is the coverage
floor, and that is the error this validation rates CRITICAL. The angle's own test — a control that ran
and reported clean substantiates nothing — is what the input applied correctly to the ruff exception
and to `PERMISSION_LEVELS`, and then failed to apply to itself.

### Appendix C — Block 3: each band against phase 08's own rubric

The rubric of record is `08-audit-code-quality.md:157-164`.

| Finding | Rubric clause that fits | Band as filed | Band after adjudication | Movement |
|---|---|---|---|---|
| QLT-001 | HIGH: *"a declared invariant nothing enforces"*, *"a value with two homes"* | CRITICAL | **HIGH** | down — the CRITICAL storage anchor is refuted by the native enum (VAL-08-003) |
| QLT-002 | HIGH: *"a documented audience narrower than the path admits"* | HIGH | HIGH | none |
| QLT-003 | HIGH: *"an aggregate entry point that silently omits a declared gate"* | HIGH | HIGH | none |
| QLT-004 | HIGH: *"schema drift no gate would notice"* — verbatim | MEDIUM | **HIGH** | up — the input's band has no clause (VAL-08-002) |
| QLT-005 | MEDIUM: *"a declared rule whose reason is recorded nowhere"*; *"a convention rule broken in a narrow surface only"* | MEDIUM | MEDIUM | none |
| QLT-006 | MEDIUM: *"a widened type"* | MEDIUM | MEDIUM | none |
| QLT-007 | MEDIUM: bounded correctness gap with a specific audience | MEDIUM | MEDIUM | none |
| QLT-008 | MEDIUM: *"a duplicated helper with no divergence yet"* | MEDIUM | MEDIUM | none |
| QLT-009 | LOW: *"an unreferenced definition nobody has explained"* — the second half is refuted | LOW | LOW | none (re-typed, not re-banded) |
| QLT-010 | LOW: documentation drift with no runtime consequence today | LOW | LOW | none |

Three tension points recorded rather than acted on. (1) QLT-006's rubric clause is *"a widened type
on a value nothing branches on"*, and routes **do** branch on these values — they call methods on
them; what the type system cannot check is those calls. The bands are effect classes and not a closed
list of mechanisms (`08:159`), so MEDIUM is the right home and no re-grade is warranted.
(2) QLT-008 bundles a duplication (MEDIUM) with a comment that misnames the implementation (LOW);
MEDIUM carries it. (3) QLT-010's `redirect_slashes` half claimed a behavioural difference and would
have been MEDIUM had it held; it does not hold, and the remaining claim is documentation drift.

### Appendix D — Block 4: which side moves

| Finding | Load-bearing artefact | What the specification corpus claims | Disposition |
|---|---|---|---|
| QLT-009 | the **code** — the enums are what `SPEC.md:118` says they are for | `docs/SPEC.md:118` and `docs/09-database/enums.md:48-49` both name the intended use | **re-typed** — a missing integration, not a dead export; stays in phase 08 (block 8) |
| QLT-001 | the **code** | nothing in the corpus declares that a re-grant changes the permission | confirmed; the corpus does not rescue the endpoint |
| QLT-002 | the **code** | no corpus document declares the audience, so the contract under dispute is the route's own prose | confirmed; the declaration is what moves |
| QLT-005 | **configuration** | no corpus document claims black or isort is authoritative | confirmed; the deletion recommendation is the fix |
| QLT-004 | **the gate configuration** | `AGENTS.md` rule 13 states migrations are mandatory; nothing executes it | confirmed; the corpus asserts the rule, the configuration must enforce it |
| QLT-010 | the **code** | nothing depends on the tag | confirmed |
| QLT-003, QLT-006, QLT-007, QLT-008 | the **code** | no corpus claim is in dispute | confirmed, no re-typing |

One finding changed label rather than owner, and the test that changed it is the one phase 99 asks
for: a component no code path reaches that the specification expects is a missing integration.
QLT-009's recommendation was written as if the specification had never been consulted, which is the
reason the label needed changing.

### Appendix E — Block 5: whether each recommendation can be carried out

| Finding | Target resolves | Dependencies | Executable? | What executing it disturbs |
|---|---|---|---|---|
| QLT-001 | yes — four declarations, two branches, one repository method | none | **yes**, unblocked | endpoint accepts a narrower set; no stored row rewritten; no shipped test blocks it |
| QLT-002 | yes — `dashboard_service.py:356-401` or a route dependency | step 1 merged first; coordinate with phase 12 | yes, after correcting the "only caller" premise | turns 200 into 403 for non-owner/non-admin callers, on one call site more than phase 08 assumed |
| QLT-003 | yes — three diagnostics, then `Invoke-Check` | diagnostics must land first | yes; the rewiring half is **phase 09's** | gate reachability; nothing in the product |
| QLT-004 | yes — `Invoke-Check`, or `db/starter.py:160-169` | the start-up option touches a file under active remediation | yes | gate turns red on a branch where models and chain already disagree; must stay out of `migrate` |
| QLT-005 | yes — four config entries, four dev deps, one manifest | deletion of the root manifest must follow a commit that removes `.ai/builders/` | yes | none; no gate result changes |
| QLT-006 | yes — ten imports, ten annotations | `mkobi.interfaces.repository_interfaces` already declares the protocols | yes | route layer sheds ten concrete-class imports |
| QLT-007 | **partly** — the cast resolves; the alternative test names `backend/src/mkobi/models/enums.py`, which does not exist | codegen or one cross-tier test | yes after correcting the path | client type surface narrows by two values |
| QLT-008 | yes — two blocks, `api/deps.py:700` | the replacement must carry the admin bypass | yes, with that ordering note | two list endpoints change which code computes their accessible set |
| QLT-009 | yes | **offers a choice the corpus has already answered** | **substantiated but unusable** | deleting the families would remove the named vocabulary of a validation `SPEC.md:118` still claims |
| QLT-010 | tag half: yes. `redirect_slashes` half: **no** | none | tag half yes; second half **cannot be carried out** | none; setting `redirect_slashes` on any `APIRouter` changes nothing |

Seven usable as written, two usable after correction, one substantiated but unusable, one half
refuted. `tests/` contains no test of the grant endpoint and no assertion on the "already exists"
branch, so nothing in QLT-001's fix path is a remediation blocker.

### Appendix F — Block 6: cross-phase comparison, ownership, and the seam check

Sibling reports compared: phase 01 (TOPO-001..008, raw), phase 02 (CFG-001..010, raw), phase 03
(TXN-001..012, raw), phase 04 (AUTH-001..008, raw), phase 05 (DP-001..019, raw), phase 06
(ART-001..009, raw), phase 07 (EXT-001..010, raw), phase 09 (TST-001..018, raw). Validation reports
already written for 01-07 were read for the namespace question only.

| Contested item | Rival claim | Owner | Disposition |
|---|---|---|---|
| Grant-endpoint authorization | phase 12 has not run; phase 08's scope paragraph `:20-21,:27` claims the declared-contract angle and defers the access decision to 12 | **phase 08** for the declaration contradiction; **phase 12** for the decision and refusal shape | cross-reference, not a merge; the input's split upheld |
| Gate wiring and automation | TST-002, phase 09 | **phase 09** for the entry-point half | merged in part (VAL-08-007) |
| Gate redness (ruff, mypy) | TST-002's coverage table defers it: "not run (phase 08)" | **phase 08** | distinct, retained |
| Backend coverage floor | TST-003 (phase 09) says inert; phase 08's Appendix B says live | **phase 09** — TST-003 is correct | **conflict resolved against this input** (VAL-08-001) |
| `alembic/env.py` outside both gates | TOPO-007 (phase 01) | **phase 01** owns the widening decision | cross-reference upheld; anchors re-derived and exact |
| Request-body `extra` policy | EXT (phase 07) | phase 07 | adjacent, not merged — phase 08 correctly declined to re-file |
| `DashboardAccess` concurrent-insert behaviour | TXN (phase 03) | phase 03 | adjacent; phase 08's QLT-001 concerns the re-grant path, phase 03's the create path |
| Migration-chain linearity | phase 14 has not run | phase 14 | complementary; nothing to adjudicate |

**Seam check — 0 seams.** Phase 08's scope paragraph (`:19-29`) claims fixed-value homes, the constant
surface, boundary validation, type strictness and suppressions, responsibility in a unit, one rule
one home, the cheap conventions, **the declared-contract angle as its owner**, and what the declared
gates decide and whether anything would notice. Every finding falls inside one of those: QLT-001
(block 1), QLT-002 (block 8, claimed at `:126,133`), QLT-003 (block 9), QLT-004 (block 10), QLT-005
(block 7), QLT-006 (block 4), QLT-007 (block 1, cross-tier), QLT-008 (block 6), QLT-009 (block 2),
QLT-010 (block 1). The one finding a reader might suspect is a seam — QLT-002, an authorization
defect — is the one the phase explicitly claims by name and explicitly defers half of. **No finding
is filed outside this input's declared scope.**

### Appendix G — Block 7: finding-ID namespace integrity, and the ruling

| Prefix | Declared | Minted | In-source markers | Compound form | Reuse across phases | Ruling |
|---|---|---|---|---|---|---|
| `QLT-` | `08-audit-code-quality.md:172`, checked for collision and reported | `QLT-001`..`QLT-010` — 10 identifiers, no gap, no duplicate | **0** — a search for `QLT-` across `src/`, `tests/`, `frontend/src/`, `alembic/`, `docker/`, `docs/` returns 0 matches | `phase: 08-code-quality` + `QLT-` | none | preserved; no collision; the "migrate or retire" half of the ruling has nothing to act on and is recorded as a null result |
| `VAL-` | required by `99-audit-validate.md:189` | this report mints 9 | 0 | — | **occupied** by phases 01 and 02 (flat `VAL-001..VAL-009`) and continued as `VAL-0N-` by phases 03-07 | collision reported, not resolved by minting a third form: this report uses `VAL-08-`, continuing the 03-07 convention, and records the deviation in the front matter |

The audited prefix is never renumbered, and the two namespaces occupy separate sections because the
`Severity` column carries two different scales. A provenance claim a sibling makes about a prefix
being present in shipped source would have been tested here against the working tree; no sibling
made one, and the re-derivation found no in-source markers for `QLT-` in any tier.

### Appendix H — Block 8: the shared findings template as a controlled artefact

The template resolves at `.ai/audit/templates/audit-findings.md` and mandates the following. Not
repaired from inside this run.

| Mandated element | Present? | Note |
|---|---|---|
| front matter `phase:` | yes | `08-code-quality`, the audited phase, not this run's |
| front matter `executed:` / `executor:` / `problems-only:` | yes | `2026-09-30` / `validator` / `true` |
| front matter `findings:` / `by-severity:` | yes, but **the contract and the template disagree** | the template's four-band tally describes the audited findings; the output contract additionally requires validation-level findings, whose scale differs. Phase 02's VAL-001 recorded the same collision. Resolved here with `findings:`/`by-severity:` for the audited set and `validation-findings:`/`by-validation-severity:` for the second |
| front matter `baseline:` / `baseline-dirty:` | **absent from the template** | required by the phase brief and present in phases 03-07's validation reports; recorded here |
| five per-finding fields (Severity, Zone, Observation, Evidence, Consequence, Recommendation) | all six present in 10 of 10 findings and in 9 of 9 validation findings | the template says "five fields" and enumerates six — the same wording defect phase 01's VAL-008 recorded; not repaired |
| zone = the block title quoted verbatim | **yes — 10 of 10** | every `Zone` line was compared against the block titles at `08-audit-code-quality.md:41,56,72,76,88,99,111,124,136,147`; all ten match a block title verbatim, so there is no paraphrase and nothing to file. One inconsistency of a different kind is recorded below |
| reserved empty-state string | not applicable | the phase produced ten findings; the string is not used and no summary pads in its place |
| sections: Summary, Findings, Distribution, Cross-Finding Analysis, Roadmap, Rollout Safety, Appendices | all seven present, plus Disposition Tally and Validation-Level Findings | the two additions are required by the validation output contract, which the template does not describe |

Zone check, since it is the one element with a mechanical test: each of the ten `Zone` lines was
compared character-for-character against the ten block titles in `08-audit-code-quality.md`
(`:41, :56, :72, :76, :88, :99, :111, :124, :136, :147`). **All ten match a block title verbatim** —
QLT-001, QLT-007 and QLT-010 all declare block 1; QLT-002 block 8; QLT-003 block 9; QLT-004 block 10;
QLT-005 block 7; QLT-006 block 4; QLT-008 block 6; QLT-009 block 2. There is no paraphrase and no
absent zone. Recorded as a **null result**, which is a valid outcome rather than a gap.

The one inconsistency the check surfaced is between a finding's zone and the input's own coverage
record: **QLT-008 declares block 6 as its zone, while Appendix B attributes it to blocks 5 *and* 6.**
Block 5 is "Responsibility inside a unit", and the finding is about duplicated implementations of
one rule, which is block 6 — so the `Zone` field is the correct one and the Appendix B row is the
loose one. This is a LOW drift item with no remediation consequence; it is recorded here rather than
filed, since the phase's own output contract forbids repairing a shared artefact from inside a run
and the input report is not mine to edit. The template's "five fields" wording defect, which phase
01's VAL-008 already recorded, stands unchanged and is likewise not repaired here.
### Appendix I — Block 9: does the input rest on its own declared blocks

| Finding | Support | Angle the declared blocks do not name |
|---|---|---|
| QLT-001 | block 1 (declarative) + own evidence | the storage-tier constraint that decides its band is block 1's "which of these values the type system could catch being wrong", extended to the database tier — the report never asked it |
| QLT-002 | block 8 (declarative) + own evidence | — |
| QLT-003 | block 9 (declarative) + own evidence | — |
| QLT-004 | block 10 (declarative) + own evidence | — |
| QLT-005 | block 7 (declarative) + own evidence | — |
| QLT-006 | block 4 (declarative) + own evidence | — |
| QLT-007 | block 1 (declarative) + own evidence | — |
| QLT-008 | block 6 (declarative) + own evidence; Appendix B also attributes it to block 5 | — |
| QLT-009 | block 2 (declarative) + own evidence | **the specification corpus** — the declared-intent question is block 2's "code that is present, reachable and referenced by nothing … the question is what it was for", and the report asked only "is it referenced" |
| QLT-010 | block 1 (declarative) + own evidence | — |

Nine of ten rest on their own declared blocks and their own evidence fields. **QLT-009 is the
exception**, and it is the one finding whose declared-intent question its own block names and the
report left unasked. The signature phase 99 describes — substantive findings arriving from an angle
the declared blocks never name — is present once, in a mild form: no finding arrived from outside
the declared blocks, but one arrived from inside a declared block whose question was not asked.

### Appendix J — the CRITICAL band, tested rather than accepted

Phase 08's CRITICAL predicate is *"a wrong or lost value is in storage now, or the only thing that
kept a rule true for everyone is gone"*, illustrated by a stored value no rule ever constrained, a
field default that overwrites stored content when the key is absent, and two implementations of one
rule whose copies already disagree on a value the system acts on. QLT-001 was the sole claimant.

| Illustrative clause | Test | Verdict |
|---|---|---|
| a stored value no rule ever constrained | the column is a native PostgreSQL enum; `SELECT 'read'::dashboard_permission_level` is rejected by the database | **fails** — storage is constrained |
| a field default that overwrites stored content when the key is absent | `AccessGrant.permission: str = "view"` is a default, but the re-grant path performs no write at all, so nothing is overwritten | **fails** — the default never reaches an existing row |
| two implementations already disagreeing on a value the system acts on | they agree on `view`/`edit`/`admin`; they disagree only on `read`/`write`, which the enum prevents from being stored or acted on | **fails at the storage and decision tiers**; holds only at the response tier, which is where the false success lives and which is a HIGH consequence |
| "the only thing that kept a rule true for everyone is gone" | the rule is enforced nowhere; nothing was removed | **fails** — this is a defect of omission, not a regression |

The band is **genuinely empty**, not merely unclaimed. The near-miss is real and consequential —
QLT-001 is a false success on an access-control write — but the rubric's CRITICAL anchor is a value in
storage, and there is no such value here. The competing reading, under which a lost operator decision
counts as a lost value in storage, is recorded inside QLT-001's Observation for a reader who prefers
it; this validation does not sustain it.

### Appendix K — environment, restoration, and what was not settled here

**Baseline.** `git rev-parse HEAD` → `b23a9cbe6cd4a535c69eb5d752b242b1ee9578cd`, **identical to the
input's recorded baseline**. The concurrent remediation series the phase brief describes
(`8505a62 → 2d23c27 → c3c0a61 → 5a2cfb6 → b23a9cb`) has stopped at `b23a9cb`, so **no anchor in the
input moved under this run** and no re-anchor table is required. `git status --porcelain` showed the
same deleted `.ai/` scaffolding the input recorded, plus untracked audit output directories and
`.ai/plans/01-configuration-secrets-remediation-execution.md`. **The `_b3_full_out.txt` named in the
phase brief is not present in `git status` at this baseline** — the input also records its absence,
so the two observations agree.

**No drift in the audited files.** `git status --porcelain -- src/ frontend/ tests/ pyproject.toml
Makefile.ps1 alembic/ docker/` returned **empty at the start of this run**, and returned empty again on
the second check, which was taken before the concurrent programme's next write landed. At
completion the same command reports one modification, ` M src/mkobi/config.py`, whose mtime is inside
this run's window and which belongs to the concurrent remediation programme — `config.py` is outside
every finding audited here and this validation read it zero times. The only other peer artefact to
appear during the run is an untracked `.tmp/b4/` tree (three files), belonging to another agent. Both
were left untouched. No file was edited, staged, committed, reverted or stashed by this run; the
only artefact it wrote is this report, inside the already-untracked `.ai/audit/99-validation/`.

**Gates executed, and their effect on the tree.** `uv run ruff check src/ tests/` and
`uv run mypy src/` were run (host-native, `uv`, no container). Neither writes to the repository.
**No frontend gate was run**, so the `frontend/coverage/` deletion hazard phase 09 disclosed
(TST-014) was not incurred; `git status --porcelain -- frontend/` was checked and is empty.
`uv run ruff check alembic/versions/` was run read-only to re-derive TOPO-007's count.

**The dev stack was not touched.** `docker compose -p mkobi ps` was read once to confirm the peer
left `app`, `db`, `frontend`, `redis` and `rq-worker` running; nothing was started, stopped or
reconfigured. Two read-only queries were issued against the `bidb` dev database — the
`dashboard_permission_level` label list and the `'read'::dashboard_permission_level` cast — and
**no row was created, modified or deleted by this run**. `GET /openapi.json` and `GET /health` were
read from the running app. The `create_app()` introspection that produced the `APIRoute`
`AttributeError` constructed the application object in-process and wrote nothing.

**What could not be settled here, and why.**

- *QLT-001's runtime reproduction was not re-executed.* HEAD is identical to the input's baseline,
  so the executing path re-derived here is bit-identical to the one it ran against, and the static
  proof is unconditional. Re-running it would have added rows to a shared dev database to confirm a
  claim already established from source.
- *The 500-on-new-row half of VAL-08-008 was derived, not measured.* Three artefacts establish it —
  the enum rejection (executed), the repository's `SQLAlchemyError` re-raise at `access_repo.py:80-87`,
  and the handler's catch-all at `dashboards_access.py:118-127` — but no request was issued.
- *QLT-004's positive half was not re-run.* `alembic check` against the dev database requires
  entering the app container; the finding rests on the absence, which is independently established.
- *QLT-007's per-family reference census was not re-run* (18 families × 3 trees). The three claims it
  supports were verified individually: the mapping, the tautological client test, and the barmode
  cast. The census figures themselves are the input's and are accepted as method.
- *QLT-008's duplicate-scan figures were not re-run* (0 identical 8-line windows, five at 5 lines,
  the pair among twelve at 4). They are method, not load-bearing; the pair is confirmed directly.
- *`.\Makefile.ps1 check` was not invoked end to end.* Its four constituent steps were read, the two
  backend gates were executed, and the short-circuit that prevents the other two from running was
  confirmed from the script — which is the finding. Executing the aggregate would have run the
  frontend gates and incurred the `frontend/coverage/` hazard.
- *Neither Docker test stack nor `.\Makefile.ps1 test` was run.* Nothing in this validation's
  dispositions depends on a test run; QLT-001's remediation-blocker question was answered by search
  over `tests/`.

### Appendix L — Block 11: the shared angles, and their bindings

Re-derived from the phase files themselves, not inherited from a sibling's validation report: a
search for `cross-resource` and `vacuous` across all sixteen files in
`.kilo/commands/audit/phases/`.

**The vacuous-control angle**, defined once at `99-audit-validate.md:60-69`: does the control exist,
what scope does it declare, what did it actually examine — with "did it run" kept apart from "did it
decide anything".

| Binding phase | Wording used | Do the three questions survive? |
|---|---|---|
| 02 (`:107`) | "The vacuous-control angle is 99's; what a configuration gate examines is this block's. For every validation and gate over configuration, establish what … a gate that examines nothing and a gate never invoked are different defects" | **yes** |
| 09 (`:100`) | "Bind the shared vacuous-control angle here … for every control that can emit a verdict on this repository, establish what it is configured to examine and what it actually examined" | **yes**, verbatim in substance |
| 10 (`:64`) | "bind the shared vacuous-control angle here in … " a control whose declared and actual scope differ is a finding however green it is | **yes** |
| **08 (`:144`)** | "Container and deploy gates are 10's; what a test suite would notice is 09's; **the vacuous-control angle is 99's**" | **no** — a single clause inside a *not owned here* list. It disclaims ownership; it does not bind the angle. Phase 08's block-9 evidence instead asks its own question ("which checks are declared, where each runs, what it covers, and whether it is reachable"), which is 08's reachability angle, not the three questions |

The consequence is not cosmetic and this report has the evidence for it: phase 08 declared a control
live in its own Appendix B without asking what it examined, which is the exact failure the angle
exists to catch, in the phase that mentions the angle in order to give it away (VAL-08-001). The
angle was defined, bound by three phases and given away by the one phase whose gates it would have
caught.

**The cross-resource side-effect angle** — an effect spanning more than one resource, together with
which resource is the real unit of atomicity — is defined at `99-audit-validate.md:160-161` and is
bound by **no phase in its own words**: the search across all sixteen phase files returns the
definition in 99 and no binding anywhere else. Recorded as a set-level observation with no
disposition claimed from this lane, because it affects no phase-08 finding: QLT-001 is a
single-resource question about one table's column, and QLT-004's `alembic check` recommendation
concerns the model-versus-chain comparison rather than a multi-resource effect. The live
cross-resource instances in this corpus belong to phase 03 (TXN-001's session and commit
boundaries) and are not displaced by the angle's absence from the bindings.

### Appendix M — Coverage ledger

The fixed residual footer. Blocks examined and the item count each actually reached.

| Block | Items reached | Result |
|---|---|---|
| 1 — the claim re-derived from the executing path | 10 findings, anchors resolved mechanically first | 10 dispositions; 1 headline refined, 2 asserted causes corrected, 1 claim refuted, 2 counts corrected, 0 anchors moved |
| 2 — the vacuous-control angle | 7 controls | 3 vacuous (1 wrongly discharged, 2 correctly), 1 partially vacuous, 2 deciding |
| 3 — the grade against the audited phase's own rubric | 10 findings | 2 re-grades (1 up, 1 down); 3 rubric tensions recorded and not acted on |
| 4 — which side moves | 10 findings | 10 dispositions; 1 re-typed against the specification corpus |
| 5 — whether the recommendation can be carried out | 10 recommendations | 7 usable as written, 2 usable after correction, 1 substantiated but unusable, 1 half not executable |
| 6 — cross-phase conflict, ownership, merge, seam | 8 contested items + 1 seam check | 1 conflict resolved against the input, 1 partial merge, 3 cross-references, 3 complementary, **0 seams** |
| 7 — finding-ID namespace integrity | 1 declared prefix, 10 minted, 2 sibling namespaces | ruling recorded; `VAL-` collision reported and continued as `VAL-08-`; 0 in-source markers |
| 8 — the shared findings template | 7 mandated elements across 19 blocks | zone verbatim in 10 of 10 (null result); 1 zone-vs-appendix inconsistency; template not repaired |
| 9 — whether the input rests on its own declared blocks | 10 findings | 1 finding (QLT-009) rests on a question its own block names and the report left unasked |
| 10 — the validated report as an artefact | front matter, 10 + 9 blocks, tally, namespace separation | tally agrees with the per-finding verdicts; zones verbatim; identifiers preserved |
| 11 — the shared angles and their bindings | 4 bindings + 1 unbound angle | 3 bindings sound, 1 disclaimed (08), cross-resource unbound set-wide |
| Claimed negative results | 6 (2 dismissed candidates + 4 discharged claims) | 1 dismissal **refuted** (VAL-08-001), 1 dismissal sound, 4 accepted |
| CRITICAL band | 4 clauses tested against the sole claimant | genuinely empty, not merely unclaimed |

**Every claim left unsettled, with its reason.** (1) QLT-001's runtime reproduction was not
re-executed: HEAD is identical to the input's baseline, so the executing path is bit-identical, and
the static proof is unconditional. (2) VAL-08-008's 500-on-new-row half is derived from three
artefacts, one of them executed, rather than from an issued request. (3) QLT-004's `alembic check`
result was not re-run — it requires the app container, and the finding rests on the absence, which
is confirmed. (4) QLT-007's 18-family census and QLT-008's duplicate-scan figures are the input's
method; the claims they support were verified individually and the figures were not reproduced.
(5) `.\Makefile.ps1 check` was not invoked end to end, to avoid running the frontend gates and
incurring the `frontend/coverage/` deletion hazard phase 09 disclosed; its short-circuit is the
finding and is confirmed from the script. (6) No Docker test run was made; nothing in these
dispositions depends on one.