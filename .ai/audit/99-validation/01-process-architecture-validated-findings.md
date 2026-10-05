---
phase: 01-process-architecture
executed: 2026-10-05
executor: validator
problems-only: true
findings: 14
by-severity:
  CRITICAL: 0
  HIGH: 1
  MEDIUM: 2
  LOW: 11
---

# Phase 01 — Validated Findings

## Summary

All 14 findings in `.ai/audit/01-process-architecture/findings.md` were re-derived from the executing path at
HEAD `716c755`, and every cited anchor was resolved mechanically before the claim was tested. **No finding was
rejected outright**, but **9 of 14 required correction** and **5 were re-graded down** against
`.kilo/commands/audit/phases/01-audit-process-architecture.md:119-128`, which is the rubric of record for this
phase. Three findings whose severity depended on a rubric clause the auditor did not test were re-graded:
TOPO-102 (HIGH → MEDIUM), TOPO-107 and TOPO-108 (MEDIUM → LOW).

The evidence base is sound where it matters most: **TOPO-101, TOPO-102, TOPO-105 and TOPO-106 reproduce
exactly**, and the TOPO-101 reproduction was re-run independently with an added control run that isolates the
read-only root filesystem as the sole cause. **TOPO-102's quoted evidence block contains three lines that have
never existed in the cited file at any commit** (verified with `git log -S`), and **TOPO-106's third quoted gate
line does not exist in `Makefile.ps1` at all** — no `--strict` mypy invocation is present anywhere in the file.
Both conclusions nonetheless survived independent re-derivation, so the audit's conclusions are correct while its
transcripts are not. A systemic defect runs underneath: **line anchors are stale in 9 of 14 findings**, several by
100–300 lines, which is why five HIGH/MEDIUM anchors did not resolve.

The single highest-severity surviving defect is **TOPO-101**: the production edge container provably cannot start,
reproduced on the base image it declares.

## Findings

### TOPO-101 — The production edge container cannot start: its entry point writes into a root filesystem the service declares read-only

**Severity** — HIGH (re-derived; unchanged from filed)

**Zone** — Component inventory, and the topology that differs between deployment tiers

**Verdict** — CONFIRMED

**Observation** — The `nginx` service's entry point redirects `envsubst` output into `/etc/nginx/nginx.conf`, a
regular file in the image layer, while the same service declares `read_only: true` with only `/tmp`,
`/var/cache/nginx` and `/var/run` mounted as tmpfs. `set -eu` turns the redirection failure into exit 1, so the
edge never reaches a serving state.

**Evidence** — All three anchors resolve and say what is reported:

- `docker/docker-compose.yml:375` — `entrypoint: ["/etc/nginx/entrypoint-render.sh"]`
- `docker/docker-compose.yml:385` — `read_only: true`; tmpfs at `:386-389` (`/tmp`, `/var/cache/nginx`, `/var/run`)
- `docker/nginx/entrypoint-render.sh:14` — `envsubst '${NGINX_CLIENT_MAX_BODY_SIZE}' < "$TEMPLATE" > "$RENDERED"` with `RENDERED=/etc/nginx/nginx.conf` at `:12` and `set -eu` at `:9`

Reproduction re-run independently, with the auditor's exact command:

```
/etc/nginx/entrypoint-render.sh: line 14: can't create /etc/nginx/nginx.conf: Read-only file system
EXIT=1
```

Control run with identical mounts and env **minus** `--read-only` renders successfully and reaches the stock
entrypoint (`Configuration complete; ready for start up`), failing only afterwards with `host not found in
upstream "app"` — a throwaway-container artefact, which establishes the read-only root filesystem as the sole
cause rather than the script. `/etc/nginx/nginx.conf` confirmed a regular file in the base image
(`-rw-r--r-- 1 root root 644`), and the base image's own digest matches the one the Dockerfile pins
(`nginx@sha256:65645c7bb6a0…`, `docker/Dockerfile:207`). The proxy paths depend on it:
`docker/nginx/nginx.conf.template:57` (`location /api`) and `:73` (`location /`).

**Two citation corrections, neither load-bearing.** The documented production invocation is
`docs/10-deployment/deployment.md:231` (line 230 is its comment), not `:230`; and
`docker/docker-compose.yml:5` documents the production command **without** `--profile production`, so under that
documented header `nginx` is not created at all. The exposure is reached through the `deployment.md` command.

**Consequence** — `docker compose … --profile production up -d` leaves `nginx` restart-looping under
`restart: unless-stopped` (`:380`) with one shell line per attempt and nothing bound to port 80. The application
tier behind it stays healthy, so probes that bypass the edge keep passing while the documented production entry
point is down.

**Recommendation** — Executable as filed. Either add `/etc/nginx` to the tmpfs list, or render to
`/tmp/nginx.conf` and start nginx with `-c`. The first is the smaller diff. No shipped test asserts either
posture.

---

### TOPO-102 — The background worker installs no log handler: every application record from the component that performs all data processing is discarded

**Severity** — MEDIUM (re-derived; **downgraded from HIGH**)

**Zone** — Entry surfaces: what is constructed when a surface loads, and what is deferred

**Verdict** — CORRECTED (defect confirmed and reproduced; evidence transcript partly unsound; one impact
statement struck; severity re-graded)

**Observation** — `setup_logging()` has exactly one call site in the repository, and the worker entry point is
not it. The component that performs all data processing therefore emits no application log record at all.

**Evidence** — Core claim independently reproduced:

- Repository-wide search: `setup_logging` appears only at `src/mkobi/app.py:24` (import), `:44` (the sole call
  site) and `src/mkobi/core/logging_config.py:72` (the definition). No call site in `tests/`, `alembic/`, `docker/`,
  `Makefile.ps1` or `pyproject.toml`.
- `src/mkobi/rq_worker_wrapper.py` read in full: no `basicConfig`, no `dictConfig`, no handler installation on the
  path from `start_rq_worker()` (`:205`) to `worker.work()` (`:238`).
- Reproduction inside the live `mkobi-rq-worker-1`, replicating `start_rq_worker()` and calling RQ's own
  `Worker.bootstrap()`: `root handlers: [] root level: 30` · `rq.worker.handlers: [ColorizingStreamHandler
  <stdout>, ColorizingStreamHandler <stderr>]` · `rq.job.handlers: [same]` · `mkobi.workers.data_worker effective
  level: 30 isEnabledFor(INFO): False` — the INFO record is emitted nowhere and the WARNING record reaches stderr
  bare, unformatted, through `logging.lastResort`.
- The worker's **entire** log stream contains **zero** JSON application records
  (`docker logs mkobi-rq-worker-1 | Select-String '"service"'` → `0`). Every line is RQ's own logger.

**Mechanism correction.** The audit implies RQ installs nothing. In RQ 2.9.1
(`rq/worker/base.py:930-955`) `Worker.bootstrap()` calls `setup_loghandlers(..., name='rq.worker')` and
`name='rq.job'`. Handlers are therefore installed — but only on those two loggers, never on root and never on
`mkobi.*`. The conclusion is unchanged; the mechanism as stated was wrong.

**Evidence defects recorded.** Three of the five quoted lines **never existed in the cited file at any commit** —
`git log -S` returns nothing for `with_scheduler`, `stop_event` or `cleanup_stale_temp_files` in
`src/mkobi/rq_worker_wrapper.py`. Actual content at the cited lines: `:221 check_dependencies(
WORKER_REQUIRED_MODULES)` (not `REQUIRED_MODULES`), `:225 asyncio.run(check_redis_connection(redis_url))` (no
`stop_event`), `:231 import mkobi.workers.data_worker  # noqa: F401` (not a `cleanup_stale_temp_files` import),
`:238 worker.work()` (not `worker.work(with_scheduler=True)`). `src/mkobi/app.py:45-47` reads
`config.log_level` / `config.log_file` / `config.logging.json_logging`, not `config.LOGGING.*`.
`docker/docker-compose.yml:288` is `LOGGING__JSON_LOGGING: ${LOGGING__JSON_LOGGING:-true}`, not `"true"`.
`docker/docker-compose.yml:275` and `docker/docker-compose.override.yml:244` match exactly.

**Impact correction — one of the two stated invariant breaches is struck.**
`docs/06-backend/logging.md:143-148` does list "Processing start / result / failure" as INFO/ERROR, and none of
those records exist in the worker's stream — that half holds. But the finding cites
`docs/06-backend/logging.md:166-173` as a second breach, claiming it "counts `app` and `rq-worker` among them" as
opening a `RotatingFileHandler`. The current text says the **opposite**, in the past tense: *"It is **not set by
any compose service by default**: the docker services **previously** set it for `app` and `rq-worker` … With the
per-process default removed the ceiling is **zero** by default."* That citation is stale and the breach is not
present.

**Consequence** — `docker compose logs rq-worker` cannot show that a job started, what it parsed, how many rows it
produced, or why it failed. With one worker replica (no `replicas` or scale target anywhere in `docker/`), a wedged
or crashing job is indistinguishable from an idle queue. Job execution itself is unaffected.

**Severity re-derivation (HIGH → MEDIUM).** The phase rubric at `:124` reserves HIGH for service unavailability,
an answer a caller acts on that is wrong because the process was not ready, work silently abandoned at
termination, or "a declared **ordering, readiness or liveness** contract that does not hold". A logging contract
is none of those three. The rubric's MEDIUM clause at `:125` is a verbatim match: "degraded operability … a
defect an operator cannot distinguish from normal behaviour". The alternative reading — that "the sole executor
emits no application telemetry" is a liveness-contract failure — would sustain HIGH; recorded here so the
coordinator can take it either way. The finding must not be dropped.

**Recommendation** — Executable as filed: call `setup_logging(...)` from `start_rq_worker()` before
`worker.work()`, reading the same `LoggingSettings` the app reads. Note that doing so also makes the currently
inert `LOGGING__LEVEL` / `LOGGING__JSON_LOGGING` variables start working, which is an operator-visible behaviour
change.

---

### TOPO-103 — The periodic reconciler reports an accepted, still-queued upload as FAILED

**Severity** — MEDIUM (re-derived; unchanged from filed)

**Zone** — The periodic loop and the work-submission mechanisms inside the request-serving process

**Verdict** — CONFIRMED (recommendation corrected: its stated dependency does not exist)

**Observation** — Admission commits the `UPLOADED` row before the job is enqueued, and the periodic sweep fails
that row on age alone. The sweep cannot consult the queue: its signature admits no queue handle.

**Evidence** — Anchors resolving exactly:

- `src/mkobi/services/file_processing.py:236` — `await db.commit()`, with the enqueue after it at `:263-269`.
- `src/mkobi/db/repositories/processing_log_repo.py:56` — `"started_at": datetime.now(UTC)` set at creation, so
  the row is immediately eligible for the sweep.
- `src/mkobi/workers/data_worker.py:530-607` — `mark_orphaned_uploaded_logs_failed`. Static proof of the claim:
  the production UPDATE predicate at `:586-591` is `status == UPLOADED AND started_at < cutoff` and the function
  signature (`:532-533`) takes only `timeout_minutes` and `session`. There is no reference to the queue anywhere
  in the statement.
- `src/mkobi/config.py:736` — `stale_processing_timeout_minutes: int = Field(default=30, alias=…)`; passed through
  at `src/mkobi/app.py:203-204`; the sweep runs every `stale_processing_cleanup_interval_seconds` (300 s default).
  No compose service overrides either.
- `src/mkobi/api/routes/upload.py:294-321` — `get_status_endpoint` returns the row's status to the polling client.

**Citation corrections.** The quoted `select(...)` block is a paraphrase: the production path is an `update(...)`
at `:586-596` (the `"Worker restart: orphaned UPLOADED entry detected"` message at `:594`, not `:583-584`). The
quoted `enqueue_processing_job` kwargs are stale — actual is
`file_path=str(final_file_path), dashboard_id=dashboard_id, task_id=log.id, mode=str(mode),
processing_config=processing_config`. The cited `:1547-1550` is a **comment**, not a docstring (and the audit
mis-attributes the elided "the two markers share the same horizon" sentence from `:1545-1546` to that range); the
actual docstring is `:535-557`, and it independently states the same defect at `:540-542`: *"otherwise a restart
would flip queued-but-unstarted rows to FAILED and the still-queued job would then move them back to completed,
which reads as a false failure."* `config.py:741` is wrong for the interval — actual `:737`.

**Recommendation defect — the primary branch depends on something that does not exist.** The recommendation offers
an existence test against the queue "because the RQ job registry already records the queue job id in
`processing_logs.metadata`, so the decision can be made from a key that actually exists". **It does not.**
`queue_job_id` is a local variable at `src/mkobi/services/file_processing.py:263`, used only in a log line at
`:276-277`; it is never persisted. `src/mkobi/db/models/processing_logs.py` has **no** `metadata` column, and
`grep metadata` over that model and over `alembic/versions/` returns nothing. The finding is substantiated; this
recommendation branch is not executable as written. Either branch must change the premise — a distinct `QUEUED`
status the age sweep excludes, or a newly persisted key (a schema change, so an Alembic migration).

**Consequence** — Whenever the queue holds a job longer than 30 minutes, `docker compose logs app` reports the row
`FAILED` with a message that is factually wrong (no worker restarted), while the job sits in Redis; the client is
told its upload failed and may re-submit; and if the worker later drains, `_process_csv_file_async` writes
`PROCESSING` then `COMPLETED` over the same row, replacing the dashboard's `aggregated_data` from the older file.

**Recommendation** — Carry a distinct `QUEUED` status that the age sweep excludes and that
`get_processing_status` maps to "awaiting processing", or add the persisted job id first. Correct the comment at
`data_worker.py:1543-1550` in the same change — it is the sentence that made the gap look closed. Rollout must
reconcile existing `UPLOADED` rows older than the horizon before deploying, and the frontend status mapping must be
checked.

---

### TOPO-104 — Entry-layer dependency providers that no route reaches

**Severity** — LOW (re-derived; **downgraded from MEDIUM**)

**Zone** — Route surface assembly and reachability

**Verdict** — CORRECTED (anchors exact; caller count undercounted; a shipped test is an undeclared remediation
blocker; severity re-graded)

**Observation** — Four authorization providers in `src/mkobi/api/deps.py` are re-exported in `__all__` and bound
to nothing.

**Evidence** — Every declared anchor resolves and every caller claim re-derived by repository-wide search:

| Symbol | Declared | Re-exported | Callers (re-derived) |
|---|---|---|---|
| `get_dashboard_permissions` | `deps.py:982` | `deps.py:87` | none |
| `require_role_dependency` | `deps.py:751` | `deps.py:78` | none — only its own docstring example at `:770` |
| `require_viewer_role` | `deps.py:733` | `deps.py:77` | only `ViewerUser` at `:979` |
| `ViewerUser` | `deps.py:979` | `deps.py:86` | none |

`get_dashboard_permissions` is a real resolver, not a stub: `deps.py:1009`, `:1015`, `:1021` issue the
`can_read` / `can_write` / `can_admin` `check_dashboard_access` calls. `docs/` contains no reference to any of the
four symbols (searched, zero hits).

**Correction — the contrast figure is wrong.** The three live aliases are bound at **39** route signatures across
the eight named files, not 24: `admin.py` ×10, `dashboards_crud.py` ×6, `users.py` ×6, `layouts.py` ×5,
`graphs.py` ×5, `upload.py` ×3, `processing_configs.py` ×3, `data.py` ×1.

**Correction — undeclared remediation blocker.** `tests/test_deps.py:599-601` asserts
`("CurrentUser", "AdminUser", "EditorUser", "ViewerUser")` are all present in `deps.__all__`. The finding
recommends establishing intent and possibly deleting the aliases; `require_viewer_role` and `ViewerUser` cannot be
removed without that shipped test changing with them.

**Consequence** — No runtime failure today. The maintenance cost is real: `get_dashboard_permissions` encodes the
read/write/admin triple in one place that nothing executes, so it can drift from the live
`check_dashboard_access` usage at `deps.py:823`, `:867`, `:911` without any signal, and a reader cannot tell
whether it is the live permission path, a retired one, or a migration in progress.

**Severity re-derivation (MEDIUM → LOW).** The phase rubric's MEDIUM band at `:125` covers "a component enabled
and monitored that nothing reaches". These four are not enabled in any deployment surface and are not monitored —
they are uncalled functions in a module. The rubric's LOW band, "no runtime consequence today", is a verbatim
match, and the finding itself states "No runtime failure today."

**Recommendation** — Executable in principle, but it must name `tests/test_deps.py:599-601` as a blocker: the
test encodes the current export surface. Establish intent first; if `get_dashboard_permissions` is residue, delete
it and the three aliases together and update that test.

---

### TOPO-105 — The catch-all mount answers every undeclared path with 200 and the SPA index

**Severity** — MEDIUM (re-derived; unchanged from filed, blast radius narrowed)

**Zone** — Route surface assembly and reachability

**Verdict** — CORRECTED (reproduced exactly; one citation wrong; route count stale; consequence overstated)

**Observation** — With a bundle present, a `StaticFiles` mount registered last at `/` answers every path that no
route claims with `200 text/html` and the SPA index. The `api/` guard is a literal prefix test, so `/apifoo` also
falls through to the index.

**Evidence** — Reproduction re-run independently with `FRONTEND__DIST_DIR` pointed at a bundle stub and lifespan
not started; **byte-for-byte identical** to the auditor's transcript:

```
MOUNTS: [('', 'Mount')]
REQ /                          -> 200 text/html; charset=utf-8 :: 'SPA-INDEX'
REQ /nonexistent-route-zzz     -> 200 text/html; charset=utf-8 :: 'SPA-INDEX'
REQ /apifoo                    -> 200 text/html; charset=utf-8 :: 'SPA-INDEX'
REQ /api/v1/nope               -> 404 application/json :: {"type":"https://api.mkobi.com/errors/not_found",…}
REQ /api/v2/nope               -> 404 application/json :: {"type":"https://api.mkobi.com/errors/not_found",…}
```

Anchors resolving exactly: `app.py:543` (`if bundle_available:`), `:548` (`API_PREFIXES = frozenset({"api/"})`),
`:586-590` (`application.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="static")`).
`docker/Dockerfile:229` (`COPY --from=frontend-builder /app/frontend/dist ./frontend/dist`) confirms the bundle
ships in the production image, so the mount is registered there.

**Citation corrections.** `app.py:448-451` does **not** carry the `/docs` / `/redoc` / `/openapi.json`
registration — those lines are the Redis component check inside `/health/detailed`. The quoted `:570-584` guard is
a paraphrase; the real code is a single expression, `is_api_route = any(path.startswith(prefix) for prefix in
API_PREFIXES)` at `app.py:572`, with a bare `raise HTTPException(status_code=404, detail="Not found")` at `:584`.
The live route table is **65** entries (61 `APIRoute` + 4 `Route`), not 68, and `/docs/oauth2-redirect` was
omitted from the enumeration: the full non-`/api/v1` set is `/openapi.json`, `/docs`,
`/docs/oauth2-redirect`, `/redoc`, `/health`, `/health/detailed`.

**Consequence correction — the stated blast radius does not hold today.** The finding claims the app's own port is
reachable "from the compose network **and from the host port mapping**". The base compose file publishes exactly
one host port: `nginx` `80:80` (`docker/docker-compose.yml:365-366`). The `app` service has **no** `ports:`
mapping. The only host mapping for it is in the dev override (`docker/docker-compose.override.yml:186-190`,
`${APP_HOST_PORT:-8010}:8000`) — and in the dev tier the mount is **not** registered, because the dev image ships
no bundle (`resolve_frontend_bundle()` returns `False` and `app.py:591-596` logs the warning instead; confirmed
live: the running `mkobi-app-1` logs `Static directory '/app/frontend/dist' not found or missing index.html`).
So the "external monitoring infers endpoint existence from the status code" scenario is unreachable in both tiers
today: in production the app port is unpublished and the only network peer with external exposure is `nginx`,
which cannot start (TOPO-101); in dev the mount does not exist. What remains is a real protocol defect shipped in
the production image, observable from inside the compose network and from any future host mapping.

**Severity re-derivation (MEDIUM, unchanged).** The rubric's MEDIUM clause "a defect an operator cannot
distinguish from normal behaviour" still fits: the response cannot distinguish "the SPA exists" from "this
endpoint exists". Not HIGH — no service is unavailable and no caller receives a wrong answer it acts on for
correctness. Not LOW — the behaviour ships in the production image.

**Recommendation** — Executable as filed: resolve the fallback only for paths the SPA owns, and make the guard
segment-aware so `/apifoo` stops being answered with `200 text/html`. Any client or probe relying on `200` from a
mistyped path will start receiving `404`.

---

### TOPO-106 — The declared lint and typecheck gates do not cover the migration scripts, which carry lint errors today

**Severity** — LOW (re-derived; **downgraded from MEDIUM**, and **re-typed**)

**Zone** — Entry surfaces: what is constructed when a surface loads, and what is deferred

**Verdict** — CORRECTED (observation and ruff measurement exact; one quoted gate line does not exist; the finding
re-files a closed, deliberate ruling and recommends the exact edit that ruling excluded; severity re-graded)

**Observation** — `alembic/versions/` (10 migration scripts) is named by neither quality gate and is excluded from
mypy's directory discovery, and it carries four lint errors today.

**Evidence** — Gate measurement re-run independently on the host:

- `uv run ruff check src/ tests/ alembic/env.py` → `All checks passed!`
- `uv run ruff check alembic/ --output-format concise` → `Found 4 errors.` — `UP035` at
  `alembic\versions\82739c97fde1_add_error_code_column_to_processing_.py:8:1`, `UP007` at `:16:16`, `:17:16`,
  `:18:13`. **Exact match** to the auditor's transcript.
- `uv run mypy alembic/env.py --no-incremental` → `Success: no issues found in 1 source file`, confirming
  `exclude = ["alembic/"]` (`pyproject.toml:169`) applies to directory discovery and not to named files.
- `Makefile.ps1:262` — `ruff check src/ tests/ alembic/env.py` (exact); `Makefile.ps1:270` —
  `mypy src/ alembic/env.py` (exact); `alembic/versions/` holds exactly **10** scripts.

**Evidence defect.** The third quoted gate line — `270: Invoke-InContainer tools "mypy --strict
src/mkobi/interfaces/ services/ db/repositories/ models/"` — **does not exist**. `Makefile.ps1` contains **no**
`--strict` mypy invocation anywhere, and it does not invoke gates through `Invoke-InContainer`; the real form is
`docker compose @DevCompose run --rm --no-deps tools …`. Line `:266` is `ruff check --fix src/ tests/
alembic/env.py`, not a mypy call.

**Duplicate and ruling conflict — the reason for the re-typing.** `docs/SPEC.md:216` records **TOPO-007 as a
closed, deliberate decision**: *"`Makefile.ps1` lint, format and typecheck now name that file individually rather
than the `alembic/` directory, **whose applied migration must stay byte-identical**"*, and the same change-log row
already names this residual: *"**Also still open:** `alembic/versions/` stays outside both gates"*.
`.ai/plans/_code-context/14-schema-migrations-code-context.md:318` (`VAL-14-002`) had already re-measured the
identical four ruff errors and already prescribed `ruff check --fix alembic/`. TOPO-106 therefore (a) re-files a
documented, deliberate exclusion as a MEDIUM gap, (b) recommends the precise edit the recorded ruling excluded on
byte-identity grounds, and (c) duplicates an already-adjudicated item. This is a **re-type**, not a rejection: the
observation is true and the directory is genuinely outside the quality contract.

**Consequence** — Four auto-fixable style errors are invisible to `.\Makefile.ps1 lint`, `typecheck` and `check`.
The durable exposure is the absence of any signal for a directory that executes DDL on every deploy — but that
exposure is already recorded in `docs/SPEC.md`, so nothing is silently wrong today.

**Severity re-derivation (MEDIUM → LOW).** The rubric's LOW band is "documentation-only drift … with no runtime
consequence today". The gate/manifest disagreement is known and written down, the four errors are style-only, and
extending the gates as recommended would contradict a standing byte-identity ruling rather than fix a defect.

**Recommendation** — **Not executable as filed.** Any change here needs the product owner to reopen the TOPO-007
byte-identity decision first. If it is reopened, prefer adding `alembic/versions/` as an explicit path and
excluding it from auto-fix over `ruff check --fix`, so an applied migration is never rewritten in place.

---

### TOPO-107 — The declared console-script entry point names an attribute that does not exist

**Severity** — LOW (re-derived; **downgraded from MEDIUM**)

**Zone** — Entry surfaces: what is constructed when a surface loads, and what is deferred

**Verdict** — CORRECTED (reproduced; one anchor wrong; the claim is strengthened beyond what was filed; severity
re-graded)

**Observation** — `pyproject.toml` declares a console script resolving to `mkobi.app:app`. `src/mkobi/app.py`
exposes no module-level `app`, so the shim fails at import.

**Evidence** — Reproduced inside the live application container:

```
mkobi.app has app attr: False
has create_app: True
ImportError: cannot import name 'app' from 'mkobi.app (/app/src/mkobi/app.py)
```

`pyproject.toml:54` — `[project.scripts]`; `pyproject.toml:55` — `mko-get-mediascope = "mkobi.app:app"` (both
exact). The application factory is `create_app()`; the ASGI instance lives in a different module.

**Strengthened beyond the filed claim.** The finding *asserted* the broken shim is installed in every shipped
image, reasoning from `Dockerfile:207`. Verified directly: `/app/.venv/bin/mko-get-mediascope` exists in the
running `mkobi/app` image, and its contents are

```python
#!/app/.venv/bin/python
import sys
from mkobi.app import app
…
sys.exit(app())
```

— a shim that cannot even import, calling a non-existent `app()` if it could.

**Citation correction.** `src/mkobi/main.py` is **24 lines**, not 29-36; the module-level `app = create_app()` is at
**`:17`**. The substance the finding draws from it — the instance is built as a side effect of import, which is
what makes a `module:app` entry point look plausible enough to survive review — holds.

**Consequence** — No current failure: no compose service, Makefile target or Dockerfile `CMD` invokes
`mko-get-mediascope`. The cost is a permanently broken shim in every image plus a manifest entry that sends a
reader looking for an object that does not exist. `mko-get-mediascope` matches no module in this repository.

**Severity re-derivation (MEDIUM → LOW).** Nothing invokes the shim and the effect today is zero; the rubric's LOW
band is "no runtime consequence today". The finding is a declaration/code mismatch in the entry-surface
declaration — topology drift — rather than an operational defect. The alternative reading, that a broken artefact
shipped into every image is more than documentation, would sustain MEDIUM.

**Recommendation** — Executable as filed: delete `[project.scripts]` from `pyproject.toml`. If a console entry is
wanted later, point it at `mkobi.main:app` (`main.py:17`) under a name that matches this repository. Removing the
table requires no test change — no shipped test asserts the entry point.

---

### TOPO-108 — The test harness's session-end `DROP DATABASE` path carries no store-level guard and duplicates the guarded one

**Severity** — LOW (re-derived; **downgraded from MEDIUM**)

**Zone** — The schema and reference-data bootstrap gate, and whether any of its steps can destroy a schema

**Verdict** — CORRECTED (substance confirmed; every `starter.py` anchor wrong by 100–300 lines; severity re-graded)

**Observation** — Two code paths drop a test database. One goes through `DatabaseStarter` and takes a tier gate, a
name gate and a per-name advisory lock. The other re-implements the drop inline and takes none of them.

**Evidence** — Test-harness anchors all resolve exactly:

- `tests/conftest.py:169` — `def _drop_test_database_if_owned()`; `:182-183` — `if not _test_db_created: return`
- `tests/conftest.py:203-205` — `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :name …`
- `tests/conftest.py:216-221` — `DDL("DROP DATABASE IF EXISTS %(name)s", context={"name": quoted_db_name})`
- `tests/conftest.py:626-632` — `DatabaseStarterConfig(… recreate_test_db=True)` then
  `await DatabaseStarter(starter_config).recreate_test_database()`; `:634` — `_test_db_created = True` (the audit
  says `:633`)
- `tests/conftest.py:93` — `_test_db_created = False`; `:43-47` — the `MKOBI_TEST_RUN_ID` warning; `:49-51` —
  `f"bidb_test_{run_token}{worker_id}"`

Substance confirmed by call-site census: `assert_safe_test_database_name` has exactly **one** call site
(`src/mkobi/db/starter.py:321`, defined at `:87`) and `acquire_test_database_recreate_lock` exactly **one**
(`src/mkobi/db/starter.py:370`). **Neither is called anywhere in `tests/`.**
`src/mkobi/db/test_database_lock.py:93-144` resolves as cited (single-statement `pg_advisory_lock` at `:130`,
bounded by a transaction-scoped `lock_timeout`).

**Citation defect — every `starter.py` anchor is stale.** The audit cites `:397-620` for `recreate_test_database`
(actual `def` at **`:276`**), the tier gate at `:401-409`, the name gate at `:411-430` "enforced at `:500`, `:556`,
`:597`, `:613`" (actual: one call, `:321`), and the advisory lock at `:559-580` (actual call, `:370`).

**Consequence** — The blast radius today is bounded. The database name is **constructed**, not read as a bare
target — `bidb_test_<token><worker_id>` (`tests/conftest.py:49-51`) — and the identifier is bound through
`conn.dialect.identifier_preparer.quote` (`:213-215`), so no `MKOBI_TEST_RUN_ID` value can address a non-test
database. Reaching another run's data requires the caller to deliberately reuse a token, which both the code's own
warning (`:43-47`) and `.kilo/rules/commands.md` forbid. The flag guard is deliberate and documented in the
function's own docstring: *"an unguarded session-end drop would destroy another process's database"* (`:172-178`).
What remains is a duplicated statement with a weaker guard set — a maintenance gap, not a live exposure.

**Severity re-derivation (MEDIUM → LOW).** The rubric's MEDIUM band requires degraded operability, an
indistinguishable defect, or an undocumented tier divergence. None applies: the exposure requires the caller to
violate a documented constraint, and no tier divergence exists. LOW — no runtime consequence today.

**Recommendation** — Executable as filed and the right direction: reduce to one implementation by having
`_drop_test_database_if_owned()` call the guarded path in `src/mkobi/db/starter.py`, expressing ownership as the
flag plus the per-name advisory lock. No shipped test asserts the inline drop's shape.

---

### TOPO-109 — Import cycle: the error layer imports back into the entry module that imports it

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Entry-layer discipline and dependency direction

**Verdict** — CONFIRMED

**Observation** — `mkobi.app` imports the error layer to register handlers; the error layer's unhandled-500 handler
imports `mkobi.app` back for the security-header policy.

**Evidence** — `src/mkobi/utils/exceptions.py:357-362` matches the quoted block **character for character**,
including the comment and the local import at `:362`. `src/mkobi/app.py:491` carries the comment
`# Register exception handlers before static files` and `:492-493` the deferred import and
`add_exception_handlers(application)` (the audit attributed the comment to `:492`). `src/mkobi/main.py:14` is the
only forward import; a repository-wide search for `from mkobi.api` / `import mkobi.api` outside `api/` returns no
matches, confirming this is the only back-import into the entry layer.

**Consequence** — No runtime failure; the deferred import is correct for a cycle and the comment says why. The cost
is that the security-header policy has its single definition in the highest layer with no lower-layer owner, so any
lower-layer component needing it must either repeat the header set or grow the same back-import.

**Recommendation** — Executable as filed: move `build_security_headers` (defined at `app.py:53`) and
`SecurityHeadersMiddleware` (defined at `app.py:72`, registered at `:358`) into a lower layer; `core/` already owns
security concerns. Minor drift: the audit cites `app.py:96-101` for the middleware.

---

### TOPO-110 — The entry layer performs a repository query directly, bypassing the service layer

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Entry-layer discipline and dependency direction

**Verdict** — CONFIRMED (one citation corrected)

**Observation** — The current-user dependency constructs a repository and issues a lookup itself.

**Evidence** — `src/mkobi/api/deps.py:602` — `repo = UserRepository()`; `:603` — the lookup. `deps.py:823`, `:867`,
`:911` — the three `check_dashboard_access` calls, exact. `deps.py:1009`, `:1015`, `:1021` — the
`can_read` / `can_write` / `can_admin` triple, exact.

**Citation correction.** The quoted call `repo.get(str(current_user.id), db)` is stale; the actual is
`repo.get(id=user_id, db=db)`. `get_current_user_dependency` is defined at `deps.py:535`, not `:539-546`.

**Consequence** — The user lookup has no service to own it, so it has no place to be tested as business behaviour
and no place for a caching or normalisation rule to land without moving it. One query today; the pattern is what
generalises badly.

**Recommendation** — Executable as filed: move the fetch behind `AuthService`, which is already provided at
`deps.py:309-321`.

---

### TOPO-111 — Unused shared-surface helpers left behind by the queue removal: the per-user upload tree and the synchronous Redis client

**Severity** — LOW (re-derived; unchanged from filed; **finding split — one half rejected**)

**Zone** — Shared state across processes, and what is per-process by construction

**Verdict** — CORRECTED (per-user upload tree CONFIRMED; the Redis-pair half **REJECTED as filed**)

**Observation** — `get_user_temp_dir` / `cleanup_temp_dir` implement the per-user upload tree that `AGENTS.md` §5
declares, and nothing calls them.

**Evidence — surviving half, anchors quoted line for line exactly:**

- `src/mkobi/utils/file_utils.py:18` — `def get_user_temp_dir(user_id: UUID | str) -> Path:`; `:27` —
  `cache_dir = Path(platformdirs.user_cache_dir("mkobi", appauthor=False))`; `:28` —
  `temp_dir = cache_dir / "uploads" / str(user_id)`; `:29` — `temp_dir.mkdir(parents=True, exist_ok=True)`;
  `:34` — `def cleanup_temp_dir(temp_dir: Path) -> None:`. All five exact.
- Re-exported at `src/mkobi/utils/__init__.py:9`, `:13`, `:14` — exact.
- **No caller anywhere.** `user_cache_dir` occurs only inside `get_user_temp_dir` itself, and neither helper is
  referenced in `src/` or `tests/`.
- Upload admission uses the other path: `src/mkobi/api/routes/upload.py:203` and
  `src/mkobi/services/file_processing.py:199`, both `Path(get_config().upload_temp_dir)`.
- The sweep globs exactly one directory — `src/mkobi/services/file_cleanup.py:73-74` — so a tree under
  `user_cache_dir` would fall outside every sweep. Correct and material.
- `AGENTS.md` §5 names the per-user tree explicitly.

**Rejected half, with reason.** The finding files `core/redis_client.py`'s `get_redis_client()` (`:23`) and
`close_redis_client()` (`:87`) under the same heading — "unused shared-surface helpers left behind by the queue
removal" — and attributes both remainders to TOPO-002/003. The first clause is literally true (no caller in
`src/`; the live paths use the async pair). **The attribution and the dead-code label are not substantiated.** The
specification-and-test corpus says these are intended, exercised surface:

- `tests/conftest.py:491` imports `get_redis_client as _REAL_SYNC_REDIS_FACTORY`; `:503` documents it;
  `:522` monkeypatches it.
- `tests/test_redis_client_sharing.py:21`, `:23`, `:52`, `:82`, `:233`, `:238` import and call both functions,
  and its module docstring at `:3` names the defect those functions pin.
- `tests/test_redis_client_bound.py:20` imports `get_redis_client`.

Under the phase-99 rule that a dead-code label is not substantiated until the corpus is asked, these are a
**tested public surface, not queue-removal residue** — and deleting them would break three shipped test modules,
which the finding names nowhere.

**Consequence** — Surviving half: no runtime failure, but `AGENTS.md` §5, `utils/__init__.py`'s public surface and
`file_cleanup.py`'s sweep width all describe a topology that is not the running one, and re-enabling the helper
without widening the sweep would create an un-swept temp area.

**Recommendation** — Executable as filed for the per-user tree, with the dead-code-policy caveat the finding
already carries: establish intent, then either move upload admission and the sweep onto `get_user_temp_dir`, or
delete the two helpers and correct `AGENTS.md` §5. **Do not apply the same treatment to `get_redis_client` /
`close_redis_client`**: three shipped test modules bind them.

---

### TOPO-112 — `SPEC.md` describes a worker command line and a configuration coupling that no longer exist

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Component inventory, and the topology that differs between deployment tiers

**Verdict** — CORRECTED (the documentation claim is verbatim exact; every code anchor is stale)

**Observation** — `docs/SPEC.md:185` tells an operator the `rq-worker` receives its Redis target from an explicit
`--url` on the command line and reads no Redis configuration. Both halves are false against the shipped
configuration.

**Evidence** — `docs/SPEC.md:185` contains the sentence **verbatim**: *"The `rq-worker` service does not need
these variables — it receives its target from the explicit `--url redis://redis:6379/0` command line, and its
worker code reads no Redis configuration."*

- **No `--url` on the command line.** `docker/docker-compose.yml:247` —
  `command: ["/app/.venv/bin/python", "-m", "mkobi.rq_worker_wrapper"]`. (The audit cites `:250`.)
- **The worker does read Redis configuration.** `src/mkobi/rq_worker_wrapper.py:218-219` —
  `if redis_url is None:` / `redis_url = _build_redis_url()`, and `_build_redis_url()` at `:45-64` resolves
  `get_config().redis.host / .port / .db / .password`. `RedisSettings` is at `src/mkobi/config.py:419`, not
  `:639-650`. The base compose supplies those variables to the worker at `docker/docker-compose.yml:281-283`, not
  `:277-280`.
- The audit's quoted failure surface — `raise RuntimeError("REDIS__HOST / REDIS__PORT / REDIS__DB /
  REDIS__PASSWORD must be set")` at `:226-228` — does not exist in the file; the actual failure is the
  `ConnectionError` raised by `check_redis_connection` (`:111-113`).

**Consequence** — An operator reading `SPEC.md` to decide whether the worker needs `REDIS__HOST` gets the wrong
answer, in an otherwise-correct and easy-to-trust paragraph. A worker pointed at the wrong Redis never picks jobs
up, silently, while its process and registry-probe healthcheck stay green.

**Recommendation** — Executable as filed: rewrite the last sentence of `docs/SPEC.md:185` to say the worker
derives its URL from the same `RedisSettings` as `app` via `_build_redis_url()`, and that a wrong host there
leaves the worker silent with a healthy process. The second half is the operationally useful one.
`.ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md:462` already flags this sentence (`PRF-7`), so the
correction is known and unmade.

---

### TOPO-113 — The development tier's aggregate readiness gate cannot observe the frontend component

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Component inventory, and the topology that differs between deployment tiers

**Verdict** — CORRECTED (substance confirmed; every line anchor stale by 100–260 lines)

**Observation** — `\.\Makefile.ps1 up` is documented as blocking until healthy, but the dev `frontend` service is
the only long-lived component that declares no `healthcheck`, so `docker compose up --wait` cannot observe it.

**Evidence** — Substance re-derived:

- `Makefile.ps1:71` — `Write-Host "  up             Start dev stack and block until healthy"` (the audit's quoted
  spacing differs; the wording is exact).
- `Invoke-Up` is defined at **`Makefile.ps1:138-149`** (the audit cites `:397-400`, which is inside the `backup`
  function). Its body is `docker compose @DevCompose rm -sf migrate` then
  `docker compose @DevCompose up -d --wait --wait-timeout $UpTimeout`. The quoted body —
  `Invoke-DownMigrate`, `Invoke-InHost "docker compose -p $DevProject … up -d --wait"` — **does not exist in the
  file**. `--wait` is present, so the finding's conclusion holds.
- `frontend` (`docker/docker-compose.override.yml:93-113`) declares **no** `healthcheck`; it is the only such
  component in the dev tier. Healthchecks exist at `docker/docker-compose.yml:37` (`db`), `:200` (`app`), `:222`
  (`redis`), `:313` (`rq-worker`) and `:390` (`nginx`) — the audit cites `:106-110`, `:189-195`, `:171-176` and
  `:268-273`.
- `docker/Dockerfile.frontend.dev:15` — `RUN npm ci`; `:28` — `CMD ["npm", "run", "dev", "--", "--host",
  "0.0.0.0"]`. Both exact. Port 5173 is exposed at `docker-compose.override.yml:97-98` (the audit cites `:100-101`).
- The intent comment the audit quotes at `:81-83` is at `docker-compose.override.yml:192-193`: *"Inherit the base
  healthcheck so the dev tier has a real /health readiness signal; `up --wait` then waits for the app's boot
  instead of returning on start."*
- Live confirmation: `docker ps` shows `mkobi-frontend-1  Up 34 hours` with **no** health status, while
  `mkobi-app-1`, `mkobi-db-1`, `mkobi-redis-1` and `mkobi-rq-worker-1` all report `(healthy)`.

**Consequence** — `\.\Makefile.ps1 up` returns, the developer opens `http://localhost:5173`, and Vite may still be
scanning dependencies — a connection refused that reads as a broken setup and is not. Dev-only, no production
impact; the cost is a recurring false alarm on the project's most-used command.

**Recommendation** — Executable as filed: add a `healthcheck` to `frontend` in
`docker/docker-compose.override.yml` probing 5173 (`wget -qO- http://localhost:5173/ >/dev/null 2>&1 || exit 1`,
or a TCP probe via `nc -z`), sized to cover the install/startup window on first run.

---

### TOPO-114 — The declared dev toolchain includes stubs for a dependency the project forbids

**Severity** — LOW (re-derived; unchanged from filed)

**Zone** — Entry surfaces: what is constructed when a surface loads, and what is deferred

**Verdict** — CONFIRMED

**Observation** — The dev dependency group ships `pandas-stubs`, the type-stub package for a library the project
prohibits, plus six formatters/linters no target invokes.

**Evidence** — `pyproject.toml:210-231` is the `[dependency-groups] dev` list. `pyproject.toml:219` —
`"pandas-stubs==3.0.0.260204",` (exact). The six unused tools resolve at `:212` (`black`), `:213` (`isort`),
`:222` (`twine`), `:224` (`flake8`), `:226` (`autopep8`), `:228` (`libcst`). `Makefile.ps1:262-270` holds the only
three quality targets — `lint`, `format`, `typecheck` — and all three are `ruff` / `mypy`. A repository-wide search
for `^\s*(import pandas|from pandas)` over `src/` returns zero matches. `AGENTS.md` §3 lists pandas under
**Запрещено** and names Polars as the only dataframe library.

**Consequence** — No runtime effect. Contract ambiguity plus install weight, and a reader checking whether pandas
is banned here gets two answers.

**Recommendation** — Executable as filed: remove `pandas-stubs` from the dev group. The unused linters may be
removed in the same change or kept deliberately — but if kept, the toolchain line in `AGENTS.md` §3 should say so,
or the manifest and the documented toolchain will keep disagreeing.

---

## Validation-level findings (defects in the audit report itself)

Separate section: these carry the `VAL-` prefix and a different severity scale, and are never interleaved into the
table above.

### VAL-01-001 — TOPO-102's evidence block quotes three lines that have never existed in the cited file

**Severity** — MEDIUM

**Observation** — The code transcript in TOPO-102 presents five lines as quoted source. Three of them do not
appear in `src/mkobi/rq_worker_wrapper.py` and have never appeared there.

**Evidence** — `git log -S "with_scheduler" -- src/mkobi/rq_worker_wrapper.py`, `-S "stop_event"` and
`-S "cleanup_stale_temp_files"` each return **no commit**. The file's only recent commit (`136bfe3`, 2026-10-05)
touches `_build_redis_url` alone. Actual content at the cited lines: `:221` `check_dependencies(
WORKER_REQUIRED_MODULES)`, `:225` `asyncio.run(check_redis_connection(redis_url))`, `:231` `import
mkobi.workers.data_worker`, `:238` `worker.work()`.

**Consequence** — A reader who opens the cited lines cannot match the transcript and must re-derive the whole
finding. The conclusion is independently correct, so no wrong approval results, but the report's own verification
section claims these were read.

### VAL-01-002 — TOPO-106 quotes a third quality gate that does not exist in `Makefile.ps1`

**Severity** — MEDIUM

**Observation** — The finding's evidence block quotes three gate invocations. The third,
`mypy --strict src/mkobi/interfaces/ services/ db/repositories/ models/` at line `270`, is absent: `Makefile.ps1`
contains no `--strict` mypy invocation anywhere, and it invokes gates as `docker compose @DevCompose run --rm
--no-deps tools …`, not through `Invoke-InContainer`. Line `:270` is `mypy src/ alembic/env.py`; line `:266` is
`ruff check --fix src/ tests/ alembic/env.py`.

**Consequence** — The quoted line, read as evidence, would lead a reviewer to believe a strict-typed second gate
covers a subset of the tree. It does not exist. The two real gate lines the finding does cite are exact.

### VAL-01-003 — Line anchors are stale in 9 of 14 findings, several by 100–300 lines

**Severity** — MEDIUM

**Observation** — The report's anchors resolve for the load-bearing claims but not for most of the supporting ones.

**Evidence** — Non-resolving anchors, re-derived: TOPO-107 `main.py:29` → `:17`; TOPO-105 `app.py:448-451` (the
`/docs` registration, actually the Redis health check) and route count `68` → `65` with `/docs/oauth2-redirect`
missing; TOPO-112 `docker-compose.yml:250` → `:247`, `rq_worker_wrapper.py:226-228` → `:218-219`, `config.py:
639-650` → `:419`, `docker-compose.yml:277-280` → `:281-283`; TOPO-113 `Makefile.ps1:397-400` → `:138-149` and
every healthcheck anchor by 100-260 lines; TOPO-108 **all** `starter.py` anchors by 100-300 lines;
TOPO-103 `config.py:741` → `:737`; TOPO-102 `config.LOGGING.*` → `config.log_level` / `config.log_file` /
`config.logging.json_logging`.

**Consequence** — Nine findings require the reader to re-locate their supporting evidence. Six of the fourteen
load-bearing top-level anchors (TOPO-101 ×3, TOPO-104's four declarations, TOPO-106 ×2, TOPO-114, TOPO-109 ×2)
resolve exactly, which is why the findings' conclusions survive — but the report cannot be spot-checked.

### VAL-01-004 — TOPO-106's recommendation contradicts a standing ruling and duplicates an already-adjudicated item

**Severity** — LOW

**Observation** — The finding recommends `ruff check src/ tests/ alembic/` and `ruff check --fix alembic/`,
re-filing as a MEDIUM gap a condition that `docs/SPEC.md:216` records as deliberately ruled.

**Evidence** — `docs/SPEC.md:216` (change log 3.13): *"**TOPO-007 — `alembic/env.py` under both gates** —
`Makefile.ps1` lint, format and typecheck now name that file individually rather than the `alembic/` directory,
**whose applied migration must stay byte-identical**"*, followed by *"**Also still open:** `alembic/versions/`
stays outside both gates"*. `.ai/plans/_code-context/14-schema-migrations-code-context.md:318` (`VAL-14-002`)
already re-measured the identical four ruff errors and already prescribed `ruff check --fix alembic/`.

**Consequence** — Executing the recommendation as written would rewrite applied migration files, which the
recorded ruling forbids. The finding must not reach the roadmap without reopening that decision.

## Disposition summary

| ID | Filed | Final | Verdict | Primary correction |
|---|---|---|---|---|
| TOPO-101 | HIGH | **HIGH** | CONFIRMED | two documentation anchors (`:230`→`:231`, header lacks `--profile`) |
| TOPO-102 | HIGH | **MEDIUM** | CORRECTED | 3 quoted lines never existed; RQ installs `rq.worker`/`rq.job` handlers; one doc breach struck; **re-graded** |
| TOPO-103 | MEDIUM | **MEDIUM** | CONFIRMED | recommendation's stated key (`processing_logs.metadata`) does not exist |
| TOPO-104 | MEDIUM | **LOW** | CORRECTED | caller count 24→39; `tests/test_deps.py:599` is an undeclared blocker; **re-graded** |
| TOPO-105 | MEDIUM | **MEDIUM** | CORRECTED | reproduced exactly; `app.py:448-451` wrong; routes 68→65; blast radius overstated; **re-typed** |
| TOPO-106 | MEDIUM | **LOW** | CORRECTED | third gate line does not exist; re-files a closed ruling; **re-typed + re-graded** |
| TOPO-107 | MEDIUM | **LOW** | CORRECTED | `main.py:29`→`:17`; shim confirmed installed in the image; **re-graded** |
| TOPO-108 | MEDIUM | **LOW** | CORRECTED | every `starter.py` anchor stale by 100–300 lines; **re-graded** |
| TOPO-109 | LOW | **LOW** | CONFIRMED | — |
| TOPO-110 | LOW | **LOW** | CONFIRMED | one stale call signature |
| TOPO-111 | LOW | **LOW** | CORRECTED | Redis-pair half **rejected**; three shipped test modules bind it |
| TOPO-112 | LOW | **LOW** | CORRECTED | 4 stale anchors; quoted `RuntimeError` does not exist |
| TOPO-113 | LOW | **LOW** | CORRECTED | all anchors stale by 100–260 lines; quoted `Invoke-Up` body does not exist |
| TOPO-114 | LOW | **LOW** | CONFIRMED | — |

**Verdict tally** — CONFIRMED 5 · CORRECTED 9 · REJECTED 0 · MERGED 0 · UNSETTLED 0. Agrees with the per-finding
verdicts above.

**Final severity counts** — CRITICAL **0** · HIGH **1** · MEDIUM **2** · LOW **11** (total 14).
Filed for comparison: CRITICAL 0 · HIGH 2 · MEDIUM 6 · LOW 6. **Five re-grades, all downward** (TOPO-102,
TOPO-104, TOPO-106, TOPO-107, TOPO-108); **no upgrade**. No finding was promoted. No finding was dropped.

**Rejected items, listed in full** — no finding was rejected at finding level. Four sub-claims were rejected:

1. TOPO-102's quoted `check_redis_connection(redis_url, stop_event)`, `from mkobi.workers.data_worker import
   cleanup_stale_temp_files` and `worker.work(with_scheduler=True)` — never present in the file at any commit.
2. TOPO-102's second invariant breach, that `docs/06-backend/logging.md:166-173` counts `rq-worker` as opening a
   `RotatingFileHandler` — the current text says the opposite, in the past tense.
3. TOPO-106's third quoted gate line and the `Invoke-InContainer` invocation form — neither exists.
4. TOPO-111's attribution of `get_redis_client` / `close_redis_client` to queue-removal residue, and the
   dead-code label for them — `tests/conftest.py:491,522`, `tests/test_redis_client_sharing.py:21,23,52,82,233,238`
   and `tests/test_redis_client_bound.py:20` bind both functions.

## Distribution

Both HIGH/MEDIUM findings that survive unchanged and the single HIGH that survives sit on the same two components:
the **production edge** (TOPO-101) and the **route surface of the production app image** (TOPO-105). The nine
LOW-band findings spread across five surfaces — the declared-surface triad (`Makefile.ps1` gate list,
`pyproject.toml` scripts and dev group: TOPO-106, TOPO-107, TOPO-114), the entry layer
(TOPO-104, TOPO-109, TOPO-110), shared state (TOPO-111), and the topology documentation plus dev-tier readiness
(TOPO-112, TOPO-113). No finding falls on the database tier or on the test tier's own schema-migration path
beyond TOPO-108.

## Cross-Finding Analysis

Two causes are real and both are already named by the input report:

**The declared surface has drifted from the running surface, with no gate asserting either direction.** TOPO-102
(declared `LOGGING__*` for a component that reads none of them), TOPO-106 (gate path list vs. the migration
directory), TOPO-107 (`[project.scripts]` naming a non-existent attribute), TOPO-114 (dev group declaring a
forbidden library's stubs) and TOPO-113 (`up`'s help text promising a readiness guarantee the tier does not
provide). One check that enumerates each declared entry point, confirms it resolves, and confirms each declared
path is analysed would close the class. The correction to TOPO-102 sharpens this: the worker tier does not merely
drift, it declares configuration it structurally cannot consume.

**Stale anchors are the audit's own systemic defect** and are the direct cause of the nine corrections and of
VAL-01-003. Two independent workers reading the same files today get different line numbers; a report written
against one reading cannot be spot-checked against another.

One pairing the input report does **not** draw is worth recording: **TOPO-101 removes the external path to
TOPO-105's observable behaviour.** With `nginx` crash-looping, the production app's unpublished port has no
network peer, so the `200`-for-anything surface is not externally observable today. Fixing TOPO-101 without fixing
TOPO-105 makes TOPO-105 observable for the first time. Sequence TOPO-105's tightening before or with the edge fix,
not after.

## Roadmap

1. **TOPO-101** — unblock the production edge. Nothing else in the production tier can be exercised while the
   documented entry point cannot start. Must be true before step 3 can be validated.
2. **TOPO-105** — segment-aware API guard and an SPA-owned-path allow-list. Sequence **with or before** step 1's
   rollout (see Cross-Finding Analysis), and verify no probe depends on `200` from an undeclared path.
3. **TOPO-102** — one `setup_logging(...)` call in `start_rq_worker()`. Independent of every other step; do it
   first among the operational fixes, because it is what makes TOPO-103 and any future worker failure diagnosable.
4. **TOPO-103** — decide between a distinct `QUEUED` status and a persisted job id. The second requires an Alembic
   migration and must be sequenced after the migration-schema decision in step 5. Reconcile existing `UPLOADED`
   rows older than the horizon before deploying.
5. **TOPO-106** — blocked on the product owner reopening the TOPO-007 byte-identity ruling at
   `docs/SPEC.md:216`. Do not execute the filed recommendation.
6. **TOPO-104, TOPO-107, TOPO-108** — establish intent, then either delete or wire. All three name shipped tests
   that must change with them: `tests/test_deps.py:599-601` (TOPO-104); none for TOPO-107 or TOPO-108.
7. **TOPO-112** — correct `docs/SPEC.md:185`. Trivial, and it is the sentence an operator will otherwise trust.
8. **TOPO-113** — add the dev `frontend` healthcheck.
9. **TOPO-109, TOPO-110, TOPO-111, TOPO-114** — layering moves and dead-surface decisions; no ordering
   dependencies.

## Rollout Safety

**TOPO-101** changes only the edge's writable path. No API, schema or client-visible contract moves. Revert by
removing the tmpfs entry; the failure mode is loud (one shell line per restart attempt), not silent.

**TOPO-105** changes observable responses: any client, test or external probe relying on `200` from a mistyped or
undeclared path starts receiving `404`. This is the one step whose blast radius is uncertain and must be measured
against real traffic before rollout — and it becomes observable only once TOPO-101 is fixed.

**TOPO-103** changes status semantics and the client-visible string; the frontend's status mapping must be checked,
and rows already older than the horizon must be drained or reconciled before deploy, or the next sweep fails them.

**TOPO-102** adds a stdout stream where there is none and makes the currently-inert `LOGGING__LEVEL` /
`LOGGING__JSON_LOGGING` start working — a behaviour change an operator may want to stage.

**TOPO-106, TOPO-112** are documentation/gate changes with no runtime contract; **TOPO-106** is the only one that
can rewrite applied migration files, which is why it is blocked behind a ruling rather than behind an ordering
constraint.

## Appendices

### Finding-ID namespace ruling

The audited phase declares its prefix at `.kilo/commands/audit/phases/01-audit-process-architecture.md:134`
(`Finding-ID prefix: TOPO-`). **That namespace was already occupied when this report was written**, and the
collision is real, not inherited:

- `docs/SPEC.md:216` records the closed prior phase-01 findings `TOPO-001 … TOPO-008` with their subjects.
- Live in-source references to the historical block: `docs/03-processing/task-queue.md:40`,
  `docs/06-backend/architecture.md:545`, `docs/11-guides/task-queue-migration.md:49`,
  `.ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md:462`,
  `.ai/tasks/B3-txn-003-durable-processing-transitions.yaml:618,711`,
  `.ai/tasks/B9-txn-010-migration-lock.yaml:663`,
  `.ai/plans/_code-context/00-owner-rulings-2026-10-03.md:141`.
- `TOPO-101 … TOPO-114` exist only in `.ai/audit/01-process-architecture/findings.md` and this report. No shipped
  source, configuration, test or document outside the audit tree carries a `1xx` identifier.

**Ruling.** The split namespace is the correct outcome. Minting `TOPO-101`+ and disclosing the collision, as the
input report did, is the behaviour the phase contract asks for ("report the collision rather than creating a
second namespace" — satisfied by disclosure, though a second range does now exist). The historical block is
load-bearing provenance: `.ai/tasks/B3-txn-003` treats a regression against `TOPO-001`/`TOPO-005` as a HIGH
regression gate, so those identifiers must not be renumbered. Recommendation to the coordinator: keep both ranges
disjoint and require tooling to resolve identifiers against an explicit range, since a bare lookup for `TOPO-004`
and a bare lookup for `TOPO-104` must never be treated as the same namespace.

### Duplicate adjudication

- **TOPO-106 vs. the historical TOPO-007.** Declared `duplicate-of` and self-flagged. Confirmed as a duplicate,
  and **further than the input report states**: `docs/SPEC.md:216` shows TOPO-007 was *closed by a deliberate
  decision* excluding `alembic/` on byte-identity grounds, and the same row already records the residual. Re-typed
  (see the finding) rather than merged, because the observation is still true — but it must not be counted as a new
  regression, exactly as the input report says.
- **Cross-phase.** Compared against `.ai/audit/02-configuration-secrets/findings.md` (CFG-101 … CFG-114, the only
  sibling present). No contested claim, no ownership overlap, and no two phases reaching opposite conclusions about
  the same subject. CFG-101 (production SPA throws on `VITE_API_URL`) and TOPO-105 both concern the production
  bundle, but they are disjoint mechanisms — CFG-101 is a build-time throw inside the bundle, TOPO-105 is the
  server's catch-all mount. Cross-reference only.
- **Seam check.** Every finding falls inside the input's own declared scope (component inventory and per-tier
  topology, entry surfaces, startup window, termination, periodic loop and submission, schema bootstrap gate,
  shared state, entry-layer discipline, route surface). No seam violation.

### Recommendations that are substantiated but unusable

Recorded as such, distinct from rejection: **TOPO-103's** primary branch depends on
`processing_logs.metadata`, which does not exist — it needs either a distinct status or a new persisted key with a
migration. **TOPO-106's** remedy contradicts a standing ruling and needs the ruling reopened first.

### Coverage ledger

| Block | Item count reached | Notes |
|---|---|---|
| 1 — Component inventory / tier topology | 3 findings re-derived (101, 112, 113) + 4 live containers | compose healthcheck anchors re-enumerated from all three files |
| 2 — Entry surfaces and gate coverage | 4 findings re-derived (102, 106, 107, 114) | `setup_logging` census, gate census, manifest census, reproduction ×2 |
| 3 — Startup window | 0 findings | not re-audited; no finding depends on it |
| 4 — Termination / drain | 0 findings | not re-audited; no finding depends on it |
| 5 — Periodic loop and submission | 1 finding re-derived (103) | sweep predicate re-read; no queue handle in the signature |
| 6 — Schema bootstrap gate and guards | 1 finding re-derived (108) | `assert_safe_test_database_name` and `acquire_test_database_recreate_lock` call-site census |
| 7 — Shared state / per-process surface | 1 finding re-derived (111) | caller census across `src/` and `tests/` |
| 8 — Entry-layer discipline | 2 findings re-derived (109, 110) | back-import search; anchors |
| 9 — Route surface and reachability | 2 findings re-derived (104, 105) | live route-table enumeration; `TestClient` reproduction |
| Namespace integrity | 2 ranges | ruling above |
| Duplicate / cross-phase | 1 sibling report compared | no contested claim |
| Template compliance | 14 findings inspected | see below |

**Template compliance of the input report.** All fourteen blocks carry severity, areas, kind, evidence and a
recommendation. **None carries the template's `Zone` field**, which the template mandates as "the audit block
title this finding came from, quoted verbatim"; the input substitutes a free-text `areas` list mixing block numbers
with parentheticals, so no zone can be quoted verbatim from it. The `duplicate-of` field appears on TOPO-106 and
is not in the template's six per-finding fields. The input's front matter is absent entirely — the report opens at
`# Findings: Phase 01 — Process Architecture` with a bold-field metadata block, so `phase:`, `executed:`,
`executor:`, `problems-only:` and `by-severity:` are all missing. Recorded, not repaired.

**Claims left unsettled, with reasons.** None. Every finding was either reproduced, statically proven, or refuted
from the working tree. Two verifications were re-anchored rather than left open: the nginx reproduction ran
against the local `nginx:1.27-alpine` tag rather than the digest-pinned base (`docker/Dockerfile:207`), whose own
digest resolves to the identical `nginx@sha256:65645c7bb6a0…`, and `/etc/nginx/nginx.conf` was confirmed a
regular file in that tag — the read-only behaviour is a property of the container runtime flag, not of the layer
identity. Host-side `uv run python -c "import mkobi.app"` fails on `libmagic` (a documented host limitation), so
the TOPO-107 reproduction was run inside `mkobi-app-1` instead.

**Environment note.** No file under `src/`, `frontend/src/`, `tests/`, `alembic/`, `docker/` or any
production/config file was modified. The only file written by this run is this report. One scratch bundle stub was
created under `C:\Users\Om\AppData\Local\Temp\kilo\` for the TOPO-105 reproduction and has been deleted.
`\.\Makefile.ps1 test` and `\.\Makefile.ps1 check` were not run; they neither add nor remove evidence for any
finding adjudicated here.