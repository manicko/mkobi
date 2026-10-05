# Audit Base Context — mkobi BI Dashboard

Read this file first. It is the shared contract every audit phase is judged against.

## Environment

- Repo root: `C:\py_dev\mkobi` (Windows 11, PowerShell 7+)
- Canonical entry point: `.\Makefile.ps1 <target>` — there is **no GNU make** and no `make` wrapper.
- Verification commands (from `.ai/context/commands.md`):
  - Lint: `uv run ruff check <path>` (auto-fix incl. import sorting: `uv run ruff check --fix <path>`)
  - Typecheck: `uv run mypy <path>`
  - Full test suite: `.\Makefile.ps1 test` (requires `.\Makefile.ps1 test-up`; test-db on `localhost:5434`)
  - Frontend gates (cwd `frontend/`): `npm run lint`, `npm run test` (vitest), `npm run build` (`tsc -b && vite build`)
  - `.\Makefile.ps1 check` runs every gate
- Host-side `uv run pytest` is allowed but the test stack must be up. `tests/conftest.py` creates,
  migrates and drops its own per-run database `bidb_test_<run token>`. Never reuse a
  `MKOBI_TEST_RUN_ID` across concurrent runs.
- Each pytest process resolves its own test database, so concurrent runs cannot collide.

## Stack (mandatory)

- Backend: FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), asyncpg, Polars, StrEnum, Alembic, uv/ruff/mypy
- Frontend: React 18 + strict TypeScript, TanStack Query, React Hook Form + Zod, Plotly.js React
- DB: PostgreSQL + JSONB

## Declared architecture

- backend `src/mkobi/`: `api/` (HTTP routes + deps) -> `services/` (business logic) -> `db/` (SQLAlchemy models + repositories); `models/` (Pydantic models + enums); `data/` (Polars load/transform/aggregate); `core/` (security, permissions, logging, config); `interfaces/` (DI abstractions); `utils/`; `workers/`
- frontend `frontend/src/`: `app/` (providers, routing), `features/` (auth, dashboards, upload, admin, ...), `shared/` (api, components, types)
- `tests/` = pytest, `alembic/` = migrations, `docker/` + `Dockerfile` + `Makefile.ps1`

## Hard rules — violations are findings

- Strict layering **API -> Service -> Repository**; layers must not be blurred.
- Type hints on every public function/method; **no `any`** on the frontend.
- All constants/statuses via **StrEnum** in `src/mkobi/models/enums.py`.
- **No `print()`**; logging only via `logger = logging.getLogger(__name__)`.
- **No pandas** — Polars only. **No raw SQL via f-strings.**
- All comments, logs, docstrings, error messages, docs in **English only**.
- **Access control is checked on EVERY dashboard request.**
- **Temporary files MUST be cleaned up** after processing.
- Upload pipeline: `POST /upload/{dashboard_id}` -> staging dir
  (`UploadSettings.temp_dir` = `user_data_dir("mkobi","ZOO") / "tmp_uploads"`; per-user upload tree =
  `user_cache_dir("mkobi", appauthor=False) / "uploads" / <user_id>`; neither is a system temp dir)
  -> validate -> parse (Polars) -> transform + aggregate per `processing_configs`
  -> persist into `aggregated_data` (JSONB `dims` + `metrics`) -> frontend reads `GET /data/aggregated`
- Security: **JWT + bcrypt**; rate limiting + MIME-type check + size limit on upload;
  secrets only from environment (**support `_FILE` indirection**)
- Error handling: **ALL** API errors use RFC 7807 Problem Details
  (`type`, `title`, `status`, `detail`, `code`, optional `details`);
  `ErrorCode` StrEnum in `src/mkobi/models/enums.py` (UPPER_SNAKE_CASE);
  single raise mechanism `AppException` in `src/mkobi/utils/exceptions.py`;
  ErrorCode -> HTTP status mapped automatically; handlers via `add_exception_handlers(app)`
- **FORBIDDEN:** raising `HTTPException` directly; hardcoded error-code strings; non-RFC-7807 error responses
- Frontend error extraction chain: `frontend/src/shared/api/errorHandler.ts`
- ruff + mypy must pass clean; small functions, clear names, comments only for non-trivial logic
- All schema changes go through **Alembic** migrations

## Project principles (from AGENTS.md + .kilo/rules/project.md)

- Prefer simplicity, readability, maintainability.
- Avoid overengineering and needless abstractions.
- **Production code is the source of truth** — fix or remove tests, never distort production code for tests.
- Strict separation of concerns; single responsibility; composition over inheritance.
- Follow existing patterns; meaningful and consistent naming.
- Keep documentation continuously updated.
- Small, focused modules and functions.

## Documentation structure (SSOT map)

- `docs/SPEC.md` (spec), `docs/STRUCT.md` (structure), `docs/README.md` (index)
- `docs/00-overview/` (incl. `doc-maintenance-rules.md`)
- `docs/01-auth/`, `02-dashboards/`, `03-processing/`, `04-admin/`, `05-health/`
- `docs/06-backend/` (incl. `testing.md`)
- `docs/07-frontend/`
- `docs/08-security/` (incl. `error-format.md`)
- `docs/09-database/`
- `docs/10-deployment/` (incl. `deployment.md`)
- `docs/11-guides/` (incl. `docker.md`)
- `docs/90-adr/`
- `docs/99-reference/` (incl. `error-handling-guide.md`)

Extra context available on demand: `.ai/structure/map.md`,
`.ai/context/{python,react,frontend-design}-code-standards.md`,
`.ai/decisions/` (product-owner rulings), `.ai/plans/_code-context/` (per-phase code context),
`.ai/plans/*.md` (remediation execution plans).

## Reporting contract (applies to every phase)

- `problems_only = TRUE` — report **only** defects, violations, gaps, risks, inconsistencies,
  dead/duplicated logic and missing coverage. Do **not** summarise what works, do **not** praise,
  do **not** produce a general subsystem overview.
- Follow `.ai/audit/templates/audit-findings.md` exactly. Create the output directory if missing.
- Every finding cites concrete evidence: file path, line number(s), the offending code, why it
  violates the declared contract, and the concrete impact (runtime failure, security exposure,
  data corruption, maintenance cost).
- No speculative or stylistic nitpicks. A finding must be defensible by a reviewer who opens the
  cited lines.
- Severity CRITICAL / HIGH / MEDIUM / LOW, assigned consistently with real impact.
- Areas checked with nothing found get an explicit "no findings" entry — never pad the report.
- **Never** modify, create or delete any file under `src/`, `frontend/src/`, `tests/`, `alembic/`,
  `docker/` or any production/config file. The findings report is the only file that may be written.

## Finding-ID namespaces already occupied

Low ranges are already referenced elsewhere in the repo. **Do not reuse them.** Disclose the
collision in the report and start from the `1xx` range for your phase prefix.

- `TOPO-001 … TOPO-008` — referenced by `docs/SPEC.md:216` and eleven other sites. Phase 01 used `TOPO-101`+.
- `CFG-001 … CFG-010` — referenced by six `.ai/plans/_code-context/` notes and commit `5b23240`.
  Phase 02 used `CFG-101`+.
- `TXN-001 … TXN-012` — referenced by `docs/SPEC.md` and six `.ai/tasks/` files. Phase 03 used `TXN-101`+.
- `AUTH-001 … AUTH-008` — occupied by the previous audit of phase 04. Phase 04 used `AUTH-101`+.
- `DP-001 … DP-019` — phase 05's earlier pass, still referenced from `docs/SPEC.md`,
  `docs/03-processing/*` and `.ai/tasks/B3-txn-003-*.yaml`. A separate two-digit `DP-NN` series
  names plan decisions in `.ai/decisions/`. Phase 05 used `DP-101`+.
- `ART-001 … ART-009` — referenced by `docs/SPEC.md:235`, two `_code-context` notes and
  `.ai/tasks/B3-*.yaml`. Phase 06 used `ART-101`+.
- `VAL-04-001` and `VAL-06-001 … VAL-06-010` — validation-level findings from phases 04 and 06.
  **Phase 07 must start above `VAL-06-016`.**

## Already-reported — do NOT re-file these

Verified by a validation pass. If your phase scope touches one of these, cite it as already-known
and move on rather than reporting it as new.

- **`VAL-04-001` (CRITICAL, auth)** — username-enumeration timing oracle on `POST /auth/login`.
  `bcrypt.checkpw` raises `ValueError: Invalid salt` on the placeholder at
  `src/mkobi/services/auth_service.py:202`, and `verify_password` swallows it at
  `src/mkobi/security.py:258-260`, so the dummy-hash comparison returns in ~0.1 ms against
  266-273 ms for a real hash — a ~2,600x oracle. Source: phase 04 validation.
- **`TXN-101` (CRITICAL, transactions)** — `AuthService.approve_registration_request` commits the
  `users` row at `src/mkobi/services/auth_service.py:163` before `force_password_change` and the
  `registration_requests` status durable at `:689`. **Blocked, not sequenced:**
  `.ai/tasks/B1-txn-001-transaction-ownership.yaml:609` forbids touching `AuthService`, and
  `tests/test_auth_service.py:672-717` / `:1099-1161` encode the two-commit shape as intended
  behaviour. Source: phase 03 validation.
- **`CFG-101` (CRITICAL, config/frontend)** — `validateEnv()` runs at module scope in
  `frontend/src/main.tsx:7` and throws, and no build surface supplies `VITE_API_URL`
  (`env.ts:43-45`, `docker/Dockerfile:28`). Re-verified against current source after the concurrent
  frontend refactor; still live. Source: phase 02 validation.
- **`TOPO-101` (HIGH, architecture)** — the production edge nginx container cannot start:
  `read_only: true` at `docker/docker-compose.yml:385` versus the write to `/etc/nginx/nginx.conf`
  at `docker/nginx/entrypoint-render.sh:14`. Source: phase 01 validation.
- **`DP-101` (CRITICAL, data pipeline)** — `dict(ProcessingSettingsModel)` always carries
  `required_columns=None` (`src/mkobi/workers/data_worker.py:776-777`) and `LoaderConfig` refuses
  `None` (`src/mkobi/services/data_service.py:170`), so **every upload to a configured dashboard
  fails** with `PROCESSING_FAILED`. Reproduced end-to-end by the phase 05 validator against the dev
  stack. Note the derived defect `VAL-05-101`: `UploadMode.APPEND` is reachable from the UI and does
  not perform the full recompute that `AGENTS.md:77` declares unconditional. Resolve the recompute
  semantics **before** fixing `DP-103` — an injective-canonicalisation fix is only correct under
  OVERWRITE.
- **`AUTH-102` (HIGH, auth)** — the post-commit `revoke_all_user_tokens` at
  `src/mkobi/api/routes/auth.py:704` sits outside every `try` in the handler, so a faulting
  revocation surfaces as 500 with the password change already committed.
  `admin.py:309-329` and `admin.py:195-214` guard the identical seam. Source: phase 04 validation.

## Open escalations handed to specific phases

- **Phase 07 (external boundary) — HIGH expected, not yet filed.** The phase 06 validator inferred,
  but could not execute (its `docker exec` was gated), that Starlette spools the multipart body to
  `tempfile.gettempdir()` above **1 MiB** (measured `rollovers=1`), the production `app` service is
  `read_only: true` with **no `/tmp` tmpfs** (`docker/docker-compose.yml:189-193` — `rq-worker` and
  `nginx` both have one, `app` does not), and against a non-writable temp dir the parse returns
  **500** above 1 MiB and 200 below. **Phase 07 must confirm or refute this by execution** and file
  it if real. If confirmed, note it is the same read-only posture as `TOPO-101` in a second service.
- **Phase 08 (code quality)** — `pandas-stubs` at `pyproject.toml:219` is already filed as `TOPO-114`
  by phase 01. No runtime pandas exists, so the "no pandas" rule holds; do not re-file it.

## Broken cross-references found during earlier passes

- `.ai/plans/03-db-concurrency-remediation.md` **does not exist** although `docs/SPEC.md` rows
  3.14-3.17, `B1`-`B5`, `B9` and one code-context note all reference it. Accepted rulings for that
  work are readable inline in the `.ai/tasks/*.yaml` change records instead.
- `.ai/plans/17-authentication-implementation-execution.md` names `services/starter.py`, which does
  not exist. The real path is `db/starter.py`.
- The nginx access-log template is `nginx.conf.template`, not `nginx.conf`.

## Notes on concurrent work

The repository is under **concurrent modification**. Findings that cite the frontend
(`frontend/src/main.tsx`, `env.ts`, `vite.config.ts`, `frontend/src/shared/types/api.types.ts`)
were observed to change mid-audit. Re-verify any frontend citation against the current file
before reporting it, and note in the report if the code moved under you.

## Citation accuracy — apply this or the finding will be rejected

Phase 01's validation pass found **stale line anchors in 9 of 14 findings**, several off by
100–300 lines. Phase 02 found systematic drift across the compose files and two Python modules.
A finding whose `file:line` does not resolve to the code it claims is a rejected finding, so:

- Open the file and read the actual lines **immediately before** citing them. Do not cite a line
  number from memory, from a prior phase's report, or from an earlier point in your own session.
- The quoted code in the finding must be a **verbatim excerpt of the lines you cite**. If you
  cannot paste the exact text at that location, do not cite a line number.
- Never cite a line that "used to" contain something. If you believe a defect was already fixed,
  that is either a rejected finding or an explicit "already remediated" note — never a live finding.
- Verify every quoted line exists at the cited location **as it stands at report-writing time**,
  then re-verify the whole citation list once more just before you finish.
- Prefer citing a stable anchor (function/class/setting name plus line) over a bare line number,
  so the citation survives concurrent edits.

## Severity discipline

- Re-grade severity from **real demonstrated impact**, not from how alarming the defect sounds.
- CRITICAL requires demonstrated production impact, not theoretical risk.
- Check the phase task file for its own severity rubric and apply that rubric's wording.
- Distinguish a defect an operator can observe from one they cannot. An unobservable defect that
  does not disable a control is usually MEDIUM, not HIGH.
- If a recommendation's **premise is false** (e.g. it references a column or function that does not
  exist), the recommendation is not actionable — record that explicitly. A finding with an
  unusable fix is a corrected finding, not a confirmed one.