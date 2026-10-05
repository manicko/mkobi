# Findings: Phase 01 — Process Architecture

**Phase:** `01-audit-process-architecture`
**Date:** 2026-10-05
**Auditor:** architecture-auditor
**Mode:** problems_only (no overview, no praise, no "what works" summary)

---

## Summary

- **Total findings:** 14
- **by severity:** CRITICAL 0 · HIGH 2 · MEDIUM 6 · LOW 6
- **by kind:** defect 9 · gap 3 · risk 2
  (`risk` covers the two dead-code entries, TOPO-104 and TOPO-111. Per the project's dead-code policy their recommendations are *investigate the purpose, not delete*; that instruction is carried in each finding's recommendation text.)
- **by area** (first-listed area; secondary areas noted in each entry): Block 1 (component inventory / ordering / liveness) 4 · Block 2 (entry surfaces + gate coverage) 3 · Block 3 (preconditions / startup window) 0 · Block 4 (termination / drain / cancellation) 0 · Block 5 (periodic loop + work submission) 1 · Block 6 (schema / reference bootstrap gate) 1 · Block 7 (shared state, per-process surface) 1 · Block 8 (entry-layer discipline / cycles / duplication) 2 · Block 9 (route surface / reachability) 2
- **duplicates:** 0 (`TOPO-106` re-confirms, and is flagged as a duplicate of, the already-recorded prior finding `TOPO-007`; see that entry's `duplicate-of` field)
- **not runnable:** 0
- **direct runtime reproductions:** 4 of the 14 findings (TOPO-101, TOPO-102, TOPO-105, TOPO-106)

### Finding-ID namespace collision (required disclosure)

**The `TOPO-` prefix is already in use.** `docs/SPEC.md:216` (change log 3.13) records *"audit findings TOPO-001 … TOPO-008"* from the previous phase-01 pass, and the same identifiers are referenced from `docs/03-processing/task-queue.md:40`, `docs/06-backend/architecture.md:545`, `docs/11-guides/task-queue-migration.md:49`, `.ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md:462` and eleven `.ai/plans/_code-context/*.md` notes.

Per the phase rule ("check for a collision before minting an identifier; report the collision rather than creating a second namespace"), this report **does not reuse the `TOPO-001 … TOPO-008` block**. Identifiers here are minted from **`TOPO-101`** upward, leaving the historical namespace intact and preventing any cross-reference from silently changing meaning. A second namespace now exists for this phase and the coordinator must decide whether to renumber this report into the historical block or keep the offset.

---

## Findings

### TOPO-101 — The production edge container cannot start: its entry point writes into a root filesystem the service declares read-only

- **severity:** HIGH
- **areas:** Block 1 (component inventory / ordering edges), Block 2 (entry surfaces and load-time resources)
- **kind:** defect
- **phase-task step:** "derive the per-tier component inventory from the topology files; establish which edges are ordering (one-shot completion) and which are readiness (health)"

**Evidence**

`docker/docker-compose.yml:375` wires the edge's entry point:

```yaml
375:    entrypoint: ["/etc/nginx/entrypoint-render.sh"]
```

`docker/nginx/entrypoint-render.sh:11-14` renders the mounted template into the stock image's own config path:

```sh
11: TEMPLATE=/etc/nginx/nginx.conf.template
12: RENDERED=/etc/nginx/nginx.conf
14: envsubst '${NGINX_CLIENT_MAX_BODY_SIZE}' < "$TEMPLATE" > "$RENDERED"
```

`docker/docker-compose.yml:381-389` declares the posture of that same service:

```yaml
385:    read_only: true
386:    tmpfs:
387:      - /tmp
388:      - /var/cache/nginx
389:      - /var/run
```

`/etc/nginx/nginx.conf` is a regular file in the `nginx:1.27-alpine` image layer and is **not** covered by any of the three tmpfs mounts, so the redirection at line 14 targets a read-only path. `set -eu` (line 9) turns the failure into a non-zero exit.

**Direct reproduction** — the service's exact posture, on the base image it declares:

```
docker run --rm --read-only --tmpfs /tmp --tmpfs /var/cache/nginx --tmpfs /var/run \
  -e NGINX_CLIENT_MAX_BODY_SIZE=512m --entrypoint /etc/nginx/entrypoint-render.sh \
  -v docker/nginx/nginx.conf.template:/etc/nginx/nginx.conf.template:ro \
  -v docker/nginx/entrypoint-render.sh:/etc/nginx/entrypoint-render.sh:ro \
  nginx:1.27-alpine nginx -g "daemon off;"

/etc/nginx/entrypoint-render.sh: line 14: can't create /etc/nginx/nginx.conf: Read-only file system
EXIT=1
```

Control run with the identical mounts and env but **without** `--read-only` reaches the stock entry point and renders successfully (it then fails only on `nginx -t`, because the hostname `app` does not resolve in a throwaway container) — so the read-only root filesystem is the sole cause, not the script.

**Invariant broken**

A container entry that cannot complete its load cannot reach a serving state. The edge is a declared component of the production tier (`docker/docker-compose.yml:360-371`, profile `production`, `ports: "80:80"`, `depends_on: app: condition: service_healthy`), and every request the edge is the only path to (`location /api` at `docker/nginx/nginx.conf.template:57`, `location /` at `:73`) is therefore unreachable in that tier.

**Consequence**

`docker compose --profile production up -d` — the invocation documented at `docker/docker-compose.yml:5-7` and `docs/10-deployment/deployment.md:230` — leaves `nginx` in a restart loop under `restart: unless-stopped` (`:379`). An outside observer sees a crash-looping container whose only output is one shell line per attempt, and no process is bound to port 80. The application tier behind it stays healthy, so `/health` probes that bypass the edge keep passing while the documented production entry point is down.

**Recommendation** (advisory) — either add `/etc/nginx` to the `tmpfs:` list (the deeper bind mount at `/etc/nginx/nginx.conf.template` is applied after the tmpfs by Compose's path-depth ordering, so the template mount survives), or render to a writable path (`/tmp/nginx.conf`) and start nginx with `-c /tmp/nginx.conf`. The first option is the smaller diff.

**effort:** trivial · **priority:** recommended

**Rollout safety** — changes the edge's writable path only; no API, schema or client-visible contract moves. Add a one-shot container check that the rendered file exists before `exec`.

---

### TOPO-102 — The background worker installs no log handler: every application record from the component that performs all data processing is discarded

- **severity:** HIGH
- **areas:** Block 1 (liveness / observability of a component), Block 5 (the work-submission executor), Block 7 (per-process surface)
- **kind:** defect
- **phase-task step:** "record what each component states it requires before it can work, and what the tier actually guarantees"

**Evidence**

`setup_logging()` has exactly one call site in the entire repository — `src/mkobi/app.py:44`:

```python
43: config = get_config()
44: setup_logging(
45:     log_level=config.LOGGING.level,
46:     log_file=config.LOGGING.log_file,
47:     json_logging=config.LOGGING.json_logging,
48: )
```

The worker entry point never calls it. `src/mkobi/rq_worker_wrapper.py:19-24` creates a module logger, and `start_rq_worker()` (`:213-238`) proceeds straight to the worker:

```python
221:     check_dependencies(REQUIRED_MODULES)
225:     asyncio.run(check_redis_connection(redis_url, stop_event))
231:         from mkobi.workers.data_worker import cleanup_stale_temp_files  # noqa: F401
236:     queue = rq.Queue(DEFAULT_QUEUE_NAME, connection=redis.Redis.from_url(redis_url))
237:     worker = rq.Worker([queue])
238:     worker.work(with_scheduler=True)
```

There is no `basicConfig`, no `dictConfig` and no handler installation anywhere on that path. The `LOGGING__*` settings declared for the service are therefore inert:

- `docker/docker-compose.yml:275` — `LOGGING__LEVEL: ${LOGGING__LEVEL:-INFO}`
- `docker/docker-compose.yml:288` — `LOGGING__JSON_LOGGING: "true"`
- `docker/docker-compose.override.yml:244` — `LOGGING__LEVEL: DEBUG`

**Direct reproduction**, inside the running `mkobi-rq-worker-1` container, reproducing exactly what `start_rq_worker()` does (import the job module, construct the queue and worker, call RQ's own `bootstrap()`):

```
root handlers after rq bootstrap: []      root level: 30
rq logger handlers: []
mkobi.workers.data_worker effective level: 30   isEnabledFor(INFO): False
mkobi.workers logger effective level: 30
--- now emit INFO + WARNING from the worker module's own logger ---
THIS-IS-A-WARNING-RECORD-FROM-THE-JOB-ENTRYPOINT
```

The INFO record is not emitted at all. The WARNING record reaches stderr only through `logging.lastResort` — bare text, no timestamp, no level, no `service`/`module` fields — so it does not satisfy `docs/06-backend/logging.md:159` ("Logs are written to **stdout** by default") either.

Observed in the running tier:

```
docker logs mkobi-rq-worker-1 --tail 5
17:47:48 Worker 87ea90a14ac2409f86b84a5329505e76: cleaning registries for queue: default
(repeated every ~13.5 min; every line is RQ's own logger)
```

versus `docker logs mkobi-app-1 --tail 5`, which shows the project's JSON records — including DEBUG records from `mkobi.workers.data_worker` (`data_worker.py:531` etc.) running on the *app* side of the same module.

**Invariant broken**

`docs/06-backend/logging.md:143-155` lists "Processing start", "Processing result" and "Processing failure" as INFO/ERROR events that are logged. On the only component that performs them, none of those records exist in the log stream. `docs/06-backend/logging.md:166-173` reasons about which processes open a `RotatingFileHandler` and counts `app` and `rq-worker` among them — the `rq-worker` never opens one because it never installs any handler.

**Consequence**

`docker compose logs rq-worker` cannot show that a job started, what it parsed, how many rows it produced, or why it failed. With one worker replica (`docker/docker-compose.yml:246-247` declares no `replicas` and no scale target), a wedged or crashing job is indistinguishable from an idle queue. The only surviving trace of a failure is the `processing_logs` row, and per TOPO-103 that row can itself be written to a false value. Every operational question that requires the worker log is unanswerable from the deployed system.

**Recommendation** (advisory) — call `setup_logging(log_level=..., log_file=..., json_logging=...)` from `start_rq_worker()` before `worker.work()`, reading the same `LoggingSettings` the app reads, so both tiers share one logging contract. One call in one function removes the tier asymmetry entirely; no new configuration surface is needed.

**effort:** trivial · **priority:** recommended

**Rollout safety** — adds a stdout stream to a component that currently produces none. Harmless to existing log pipelines, and it makes the currently-declared `LOGGING__JSON_LOGGING`/`LOGGING__LEVEL` variables start working, which is a behaviour change an operator may want to stage.

---

### TOPO-103 — The periodic reconciler reports an accepted, still-queued upload as FAILED

- **severity:** MEDIUM
- **areas:** Block 5 (state a restart finds for accepted work)
- **kind:** defect
- **phase-task step:** "for each, establish what state a repeat run or a restart finds: whether status and outcome live in the process, whether a repeat is safe, and what a restart does to work already accepted"

**Evidence**

Upload admission commits the work record before the job is submitted — `src/mkobi/services/file_processing.py:236-269`:

```python
236:        await db.commit()
...
263:    queue_job_id = await enqueue_processing_job(
264:        log_id=str(log.id),
265:        dashboard_id=str(dashboard_id),
266:        file_path=str(final_path),
267:        filename=filename,
268:        user_mode=mode,
269:    )
```

So a `processing_logs` row sits in `UPLOADED` from the moment the client receives `201` until a worker picks the job up. `started_at` is set at creation (`src/mkobi/db/repositories/processing_log_repo.py:56`), so the row is immediately eligible for the reconciler's orphan sweep.

The sweep filters on age only — `src/mkobi/workers/data_worker.py:530-607`:

```python
568:    cutoff = now - timedelta(minutes=timeout_minutes)
569:
570:    query = (
571:        select(processing_log_model.ProcessingLog)
572:        .where(
573:            processing_log_model.ProcessingLog.status
574:            == ProcessingStatus.UPLOADED
575:        )
576:        .where(
577:            processing_log_model.ProcessingLog.started_at
578:            < cutoff
579:        )
...
583:            "Worker restart: orphaned UPLOADED entry detected "
584:            "(the queue or the consumer is gone)"
```

and writes `FAILED` with that message (`:590-596`). The statement contains **no reference to the queue** — no check that the job is still enqueued, no check that any consumer is alive.

The horizon is 30 minutes (`src/mkobi/config.py:736`, `stale_processing_timeout_minutes: int = Field(default=30, ...)`), passed through at `src/mkobi/app.py:203-204` and applied by the sweep every `stale_processing_cleanup_interval_seconds` (300 s default, `src/mkobi/config.py:741`). No compose service overrides it.

The sweep's own docstring asserts the opposite behaviour — `src/mkobi/workers/data_worker.py:1547-1550`:

```
1547:    - Second: a row a consumer is still about to pick up stays ``UPLOADED``,
1548:      while a genuinely stuck consumer's row is now failed on a clock, which
1549:      the system never did for this class before. ... the two markers share
1550:      the same horizon, so a queue that drains normally never trips them.
```

A row stays `UPLOADED` only while it is *younger* than the horizon. Sharing the horizon narrows the exposure; it does not remove it.

**Invariant broken**

A work record must not report a terminal outcome while the unit of work it names is still awaiting execution. Status is the answer `GET /api/v1/upload/status/{task_id}` (`src/mkobi/api/routes/upload.py:294-321`) returns to the client, and the client polls it.

**Consequence**

Whenever the queue holds a job for longer than `stale_processing_timeout_minutes`, `docker compose logs app` reports the row `FAILED` with *"Worker restart: orphaned UPLOADED entry detected"* — a message that is factually wrong, since nothing restarted — while the job sits in Redis. The client is told its upload failed and may re-submit. If the worker later drains the queue, `_process_csv_file_async` writes `PROCESSING` and then `COMPLETED` over the same row and replaces the dashboard's `aggregated_data` from the older file. A single worker replica (`docker/docker-compose.yml:246-247`) that is stopped, crash-looping or backed up by more than 30 minutes of large-CSV work makes every queued upload report `FAILED` before it has run.

**Recommendation** (advisory) — the sweep's premise is that `UPLOADED` means "no consumer will ever take this". Replace the age test with an existence test against the queue before failing the row (the RQ job registry already records the queue job id in `processing_logs.metadata`, so the decision can be made from a key that actually exists), or carry a distinct `QUEUED` status that the age sweep excludes and that `get_processing_status` maps to "awaiting processing". Whichever is chosen, the docstring at `:1547-1550` has to be corrected in the same change — it is the sentence that made the gap look closed.

**effort:** medium · **priority:** recommended

**Rollout safety** — changes status semantics. Existing rows in `UPLOADED` older than the horizon would survive the rollout and fail on the next sweep; drain or reconcile them before deploying. The client-visible string changes, so the frontend's status mapping needs checking.

---

### TOPO-104 — Entry-layer dependency providers that no route reaches

- **severity:** MEDIUM
- **areas:** Block 9 (route surface and reachability)
- **kind:** risk
- **phase-task step:** "any registered entry no inbound trigger reaches is a finding; so is an alias retained without a caller"

**Evidence**

`src/mkobi/api/deps.py` declares four authorization providers and re-exports all four in `__all__`, but no module binds any of them to a route:

| Symbol | Declared | Re-exported | Callers |
|---|---|---|---|
| `get_dashboard_permissions` | `deps.py:982-1027` | `deps.py:87` | none |
| `require_role_dependency` | `deps.py:751-791` | `deps.py:78` | none (only its own docstring example at `:770`) |
| `require_viewer_role` | `deps.py:733-748` | `deps.py:77` | only `ViewerUser` |
| `ViewerUser` | `deps.py:979` | `deps.py:86` | none |

`get_dashboard_permissions` is a full permission resolver — three `check_dashboard_access` calls returning `can_read` / `can_write` / `can_admin` (`deps.py:1009-1027`):

```python
 982: async def get_dashboard_permissions(
...
1009:         "can_read": await check_dashboard_access(
1010:             user_id=current_user.id, dashboard_id=dashboard_id, required_permission=DashboardPermission.READ
1012:         ),
```

A repository-wide search of `src/` and `tests/` finds these four names only inside `deps.py`. `docs/` contains no reference to any of them.

For contrast, the three aliases that *are* used — `AdminUser`, `EditorUser`, `CurrentUser` — are bound at 24 route signatures across `admin.py`, `users.py`, `dashboards_crud.py`, `upload.py`, `graphs.py`, `layouts.py`, `data.py` and `processing_configs.py`.

**Invariant broken**

An alias retained without a caller is a second, unverified copy of a contract. `get_dashboard_permissions` in particular encodes the read/write/admin permission triple in one place and nothing executes it, so it can drift from `check_dashboard_access` usage in `data.py:107`, `graphs.py:98,270,358,468` and `dashboards_crud.py:371,466` without any signal.

**Consequence**

No runtime failure today. The maintenance cost is real: a reviewer cannot tell whether this is the live permission path, a retired one, or an in-progress migration, and the documented layering contract (`AGENTS.md`: access control checked on every dashboard request) has an entry-layer branch that looks authoritative and is never executed.

**Recommendation** (advisory) — before removing anything, establish intent for each: `get_dashboard_permissions` is either the intended shape for a future permission endpoint or residue from one that was never built, and the answer is not derivable from the tree. If it is residue, delete it together with the three aliases; if it is intended, wire it and delete the per-route `check_dashboard_access` calls it duplicates.

**effort:** small · **priority:** recommended

---

### TOPO-105 — The catch-all mount answers every undeclared path with 200 and the SPA index

- **severity:** MEDIUM
- **areas:** Block 9 (route surface assembly)
- **kind:** defect
- **phase-task step:** "identify any mount that intercepts a path nothing else resolves ... the fallback answering a path no route declares is a finding"

**Evidence**

`src/mkobi/app.py:543-590` mounts a `StaticFiles` at the root path, registered **after** every router and after `/docs`, `/redoc`, `/openapi.json` (`app.py:448-451`), so it is the last matcher:

```python
548:     API_PREFIXES = frozenset({"api/"})
...
586:     application.mount(
587:         "/",
588:         SPAStaticFiles(directory=str(static_dir), html=True),
589:         name="static",
590:     )
```

The SPA fallback guard is a literal prefix test (`app.py:570-584`):

```python
570:         for prefix in API_PREFIXES:
571:             if not path.startswith(prefix):
572:                 continue
573:             try:
574:                 return await super().get_response(path, scope)
575:             except HTTPException:
576:                 raise HTTPException(status_code=404, detail="Not found") from None
```

`super()` is the bare static handler, so `html=True` serves `index.html` for anything that is not a file — i.e. the fallback answers whatever no route declared.

The assembled route table was enumerated in the running container: 68 routes, all under `/api/v1`, plus `/health`, `/health/detailed`, `/docs`, `/redoc`, `/openapi.json`. No route claims `/` or any non-`api/` path. In the production image the bundle is present (`docker/Dockerfile:229` copies `frontend/dist`), so the mount is registered.

**Direct reproduction**, with `FRONTEND__DIST_DIR` pointed at a directory holding an `index.html` (exactly the condition `resolve_frontend_bundle()` tests at `app.py:585`), lifespan not started:

```
MOUNTS: [('', 'Mount')]
REQ /                          -> 200 text/html; charset=utf-8 :: 'SPA-INDEX\n'
REQ /nonexistent-route-zzz     -> 200 text/html; charset=utf-8 :: 'SPA-INDEX\n'
REQ /apifoo                    -> 200 text/html; charset=utf-8 :: 'SPA-INDEX\n'
REQ /api/v1/nope               -> 404 application/json  :: {"type":".../not_found",...}
REQ /api/v2/nope               -> 404 application/json  :: {"type":".../not_found",...}
```

**Invariant broken**

An undeclared path is an observable protocol statement. Returning `200` for it means the response cannot distinguish "the SPA exists" from "this endpoint exists". The `api/` prefix guard is a literal string test, so it also misses a near-miss such as `/apifoo`, which the fallback answers with `200 text/html` instead of the `404` a caller would get from the neighbouring path.

**Consequence**

In the production tier an operator probing the internal app port sees `200` for a misspelled route, a stale path, or a probe pointed at a route that was removed — the exact condition the phase treats as a finding. Client-side mistakes degrade silently instead of surfacing as `404`, and any external monitoring that infers endpoint existence from the status code reports the service as fully available. The edge normally hides this (`docker/nginx/nginx.conf.template:73-77` serves the SPA for `/` itself), but the app's own port is reachable from the compose network and from the host port mapping, so the behaviour is observable.

**Recommendation** (advisory) — resolve the fallback only for paths the SPA actually owns (an allow-list of top-level route prefixes read from the frontend router, or an explicit `Accept: text/html` requirement), and let everything else fall through to Starlette's `404`. Tightening `API_PREFIXES` from the literal `"api/"` to a segment-aware check closes the `/apifoo` half on its own.

**effort:** small · **priority:** recommended

**Rollout safety** — changes observable responses. Any client, test or external probe currently relying on `200` from a mistyped path will start receiving `404`.

---

### TOPO-106 — The declared lint and typecheck gates do not cover the migration scripts, which carry lint errors today

- **severity:** MEDIUM
- **areas:** Block 2 (gate coverage of the entry surface), Block 6 (schema-mutating path)
- **kind:** gap
- **phase-task step:** "establish what the automated lint and static-typing gates actually include: an entry surface they never analyse is invisible risk, and an aggregate gate that omits part of the surface is a finding in its own right"
- **duplicate-of:** prior phase-01 finding `TOPO-007` (recorded in `docs/SPEC.md:216` and re-verified in `.ai/plans/_code-context/14-schema-migrations-code-context.md:318`). **This entry is a re-confirmation, not a new defect** — the condition was still present when re-measured on 2026-10-05. It is filed so the standing gap has a current citation; it must not be counted as an independent regression.

**Evidence**

The two quality gates name three paths, and neither names the migration directory — `Makefile.ps1:262,266,270`:

```powershell
262:    Invoke-InContainer tools "ruff check src/ tests/ alembic/env.py"
266:    Invoke-InContainer tools "mypy src/ alembic/env.py"
270:    Invoke-InContainer tools "mypy --strict src/mkobi/interfaces/ services/ db/repositories/ models/"
```

`alembic/versions/` — 10 migration scripts — is named by none of them, and `pyproject.toml:169` additionally excludes it from mypy by directory pattern:

```toml
169: exclude = ["alembic/"]
```

(Explicitly-named files are not subject to `exclude`, which is why `alembic/env.py` is still analysed — verified: `mypy alembic/env.py` returns `Success: no issues found in 1 source file`.)

The declared gate passes while the omitted directory does not — both measured through the project's own `tools` service:

```
# the declared gate
$ ruff check src/ tests/ alembic/env.py
All checks passed!

# the directory the gate does not name
$ ruff check alembic/ --output-format concise
alembic/versions/82739c97fde1_add_error_code_column_to_processing_.py:8:1:  UP035  Import from `collections.abc` instead: `Sequence`
alembic/versions/82739c97fde1_add_error_code_column_to_processing_.py:16:16: UP007  Use `X | Y` for type annotations
alembic/versions/82739c97fde1_add_error_code_column_to_processing_.py:17:16: UP007  Use `X | Y` for type annotations
alembic/versions/82739c97fde1_add_error_code_column_to_processing_.py:18:13: UP007  Use `X | Y` for type annotations
Found 4 errors.
```

**Invariant broken**

`AGENTS.md` requires that `ruff` and `mypy` pass clean, and the migration scripts are code that executes DDL against the production schema on every deploy (`docker/docker-compose.yml:150-183`, `command: ["alembic", "upgrade", "head"]`). A path that can mutate the schema is not outside the quality contract.

**Consequence**

Four lint errors in `alembic/versions/82739c97fde1_add_error_code_column_to_processing_.py` are invisible to `.\Makefile.ps1 lint`, `typecheck` and `check`. The practical exposure is not the four errors themselves but the absence of any signal for the whole directory: a migration is the one file class whose defects surface at deploy time against live data, and it is the one file class no gate reads.

**Recommendation** (advisory) — extend both gates to `alembic/` (`ruff check src/ tests/ alembic/` and `mypy src/ alembic/env.py alembic/versions/`), and drop or narrow `exclude = ["alembic/"]` so mypy's directory discovery agrees with the explicit list instead of depending on it. Four `--fix`-able errors are the whole migration of effort; the durable value is that the directory stops being invisible.

**effort:** trivial · **priority:** recommended

---

### TOPO-107 — The declared console-script entry point names an attribute that does not exist

- **severity:** MEDIUM
- **areas:** Block 2 (entry-surface inventory)
- **kind:** defect
- **phase-task step:** "enumerate every surface the system can be started or entered through — every process entry, every declared container entry ... derive that population rather than accepting the declared entry points as complete"

**Evidence**

`pyproject.toml:54-55` declares an installed entry point:

```toml
54: [project.scripts]
55: mko-get-mediascope = "mkobi.app:app"
```

`src/mkobi/app.py` exposes no module-level `app`. The application factory is `create_app()`; the ASGI instance is built in a different module, `src/mkobi/main.py:29` (`app = create_app()`), and `main.py` is not referenced by the entry point either.

**Direct reproduction**, inside the running application container:

```
$ python -c "import importlib; m=importlib.import_module('mkobi.app'); print('has app attr:', hasattr(m,'app'))"
has app attr: False

$ python -c "from mkobi.app import app"
ImportError: cannot import name 'app' from 'mkobi.app' (/app/src/mkobi/app.py)
```

The `Dockerfile:207` install (`uv sync --no-dev --frozen`) writes the console script into `/app/.venv/bin/`, so the broken shim is present in every shipped image even though nothing in the compose files or the Makefile invokes it. `docs/SPEC.md:214` attributes the previous task runner to "a task-runner copied from an unrelated Django project"; the entry point carries that same provenance (`mko-get-mediascope` matches no module in this repository).

**Invariant broken**

A declared entry surface that cannot resolve is worse than an absent one: it is discoverable, it appears in the installed image, and it fails only at invocation.

**Consequence**

No current failure — no compose service, Makefile target or Dockerfile `CMD` calls `mko-get-mediascope`. The cost is a permanently broken shim in every image plus a manifest entry that sends a reader looking for a `mkobi.app:app` object that does not exist. `src/mkobi/main.py:29-36` also shows that the module-level `app` there is built as a side effect of import, which is precisely the pattern that makes a `module:app` entry point look plausible enough to survive review.

**Recommendation** (advisory) — delete `[project.scripts]` from `pyproject.toml`. There is no supported invocation for it, and no other declared entry point covers this need. If a console entry is wanted later, point it at `mkobi.main:app` and give it a name that matches this repository.

**effort:** trivial · **priority:** recommended

---

### TOPO-108 — The test harness's session-end `DROP DATABASE` path carries no store-level guard and duplicates the guarded one

- **severity:** MEDIUM
- **areas:** Block 6 (schema-mutating paths and their guards)
- **kind:** gap
- **phase-task step:** "enumerate every path that can mutate the schema ... and the test harness — and derive that population rather than accepting the declared set. For each, record which guard it takes and whether it takes one at all"

**Evidence**

Two paths in the test tier drop a database, and they are guarded differently.

**Creation** goes through the guarded implementation — `tests/conftest.py:626-634`:

```python
626:    starter_config = DatabaseStarterConfig(
...
630:        recreate_test_db=True,
631:    )
632:    await DatabaseStarter(starter_config).recreate_test_database()
633:    _test_db_created = True
```

which takes, in `src/mkobi/db/starter.py:397-620`, three layers: the environment tier gate (`:401-409`), the database-name gate `assert_safe_test_database_name` (`:411-430`, enforced at `:500`, `:556`, `:597`, `:613`), and a bounded `pg_advisory_lock` keyed by database name (`:559-580`, via `src/mkobi/db/test_database_lock.py:93-144`).

**Teardown** does not. `tests/conftest.py:169-230` re-implements the drop:

```python
182:    if not _test_db_created:
183:        return
...
203:                        "SELECT pg_terminate_backend(pid) "
204:                        "FROM pg_stat_activity "
205:                        "WHERE datname = :name AND pid <> pg_backend_pid()"
...
216:                await conn.execute(
217:                    DDL(
218:                        "DROP DATABASE IF EXISTS %(name)s",
219:                        context={"name": quoted_db_name},
220:                    )
221:                )
```

The only exclusion is the module-level flag `_test_db_created` (`:93`), which is per-process by construction. There is no `assert_safe_test_database_name`, no tier gate, and no advisory lock on this statement — `acquire_test_database_recreate_lock` is not called anywhere in `tests/`.

**Invariant broken**

The declared guard set for a destructive schema path is environment tier + name pattern + bounded advisory lock. This path takes none of them, and it is a second copy of the same statement, so it will drift from the guarded one.

**Consequence**

The blast radius today is bounded by the per-run database name — `bidb_test_<token><worker>` at `tests/conftest.py:49-51` — so an ordinary run cannot reach another run's data. The exposure is the forced-collision path the code itself documents at `tests/conftest.py:43-47`: *"Two concurrent runs sharing one value are mutually destructive: the first to finish drops the database the second is still using, because the teardown guard proves only that this process created the database, not that it is the sole user."* With `MKOBI_TEST_RUN_ID` set (documented at `.kilo/rules/commands.md` under `test-select` / `MKOBI_TEST_RUN_ID`), `pg_terminate_backend` kills the other run's sessions and the `DROP` removes its database mid-run, with a `logger.warning` as the only trace (`:230`).

**Recommendation** (advisory) — reduce this to one implementation: have `_drop_test_database_if_owned()` call the same guarded path in `src/mkobi/db/starter.py`, with the ownership check expressed as the flag plus the per-name advisory lock, instead of repeating `pg_terminate_backend` + `DROP`. One drop statement, one guard set, no second copy to keep in step.

**effort:** small · **priority:** recommended

---

### TOPO-109 — Import cycle: the error layer imports back into the entry module that imports it

- **severity:** LOW
- **areas:** Block 8 (imports that point back from a lower layer into the entry layer, and cycles)
- **kind:** defect
- **phase-task step:** "every import that points back from a lower layer into the entry layer, and every cycle in the graph"

**Evidence**

The entry module reaches into the error layer — `src/mkobi/app.py:492-493`:

```python
492:     # Register RFC 7807 exception handlers
493:     add_exception_handlers(application)
```

The error layer reaches back into the entry module — `src/mkobi/utils/exceptions.py:357-362`, inside the global handler:

```python
357:         # This handler builds its own JSONResponse and therefore never traverses
358:         # SecurityHeadersMiddleware (which is registered innermost). Stamp the
359:         # same baseline headers here so an unhandled 500 is not served without
360:         # them. The single definition lives in mkobi.app (SECB-3); the import is
361:         # local because mkobi.app imports this module.
362:         from mkobi.app import build_security_headers
```

A repository-wide search for `from mkobi.api` / `import mkobi.api` outside `api/` returns **no** matches, so this is the only back-import into the entry layer in the tree. The only other references to `mkobi.app` are the forward import at `main.py:14` and this one.

**Invariant broken**

`AGENTS.md` declares strict layering. `utils/` is the lowest layer; a cycle between it and the entry module means neither can be imported in isolation, and the dependency direction is inverted exactly where the shared contract lives — `build_security_headers` is a transport concern that both `SecurityHeadersMiddleware` (`app.py:96-101`) and the error handler need.

**Consequence**

No runtime failure — the deferred import is correct for a cycle, and the comment at `:360-361` documents why. The cost is that the security-header policy has a single definition in the highest layer with no lower-layer owner, so any lower-layer component that needs it must either repeat the header set or grow the same back-import. A second copy of `build_security_headers` is the failure mode this shape invites.

**Recommendation** (advisory) — move `build_security_headers` (and the `SecurityHeadersMiddleware` that uses it) down into a lower layer. `core/` already owns security concerns and `utils/exceptions.py` does not import from `core/` today, so the cycle closes without a new one. The comment at `:357-361` should be replaced with a pointer to the new home.

**effort:** small · **priority:** recommended

---

### TOPO-110 — The entry layer performs a repository query directly, bypassing the service layer

- **severity:** LOW
- **areas:** Block 8 (entry-layer discipline)
- **kind:** defect
- **phase-task step:** "establish whether the entry layer parses, delegates and responds and nothing more ... persistence operations found inside an entry module are a finding"

**Evidence**

`src/mkobi/api/deps.py:602-603`, inside the current-user dependency:

```python
602:    repo = UserRepository()
603:    user = await repo.get(str(current_user.id), db)
```

The dependency constructs a repository and issues a query directly, without going through a service. The declared contract is `api/ -> services/ -> db/` (`AGENTS.md`, `docs/06-backend/architecture.md`), and every other route in `api/routes/` resolves its repository through a service.

The same module holds three further direct repository calls in the access path — `deps.py:823,867,911` (`check_dashboard_access`, from `mkobi.core.permissions`) — but those reach `core/`, which is a declared layer, and the routes call the same function directly (`api/routes/data.py:107`, `api/routes/graphs.py:98`, and five more). The `UserRepository()` instantiation at `:602` is the one that constructs a persistence object inside the transport layer.

**Invariant broken**

The entry layer parses, delegates and responds. Here it opens a database session and performs a lookup, so the query lives in a module whose other contents are parameter extraction and dependency wiring.

**Consequence**

The user lookup has no service to own it, so it has no place to be tested as business behaviour and no place for a caching or normalisation rule to land without moving it. It is a single query today; the pattern is what generalises badly, because a dependency that owns a query is a dependency nobody looks in when the user table's identity rules change.

**Recommendation** (advisory) — move the fetch behind an existing service (`AuthService` already owns user lookup for `get_current_user` at `deps.py:539-546`) so the dependency asks for a user rather than constructing a repository. If the current-user path is intentionally dependency-local, say so in a comment that names why, so the next reader does not copy it into a second route.

**effort:** small · **priority:** recommended

---

### TOPO-111 — Unused shared-surface helpers left behind by the queue removal: the per-user upload tree and the synchronous Redis client

- **severity:** LOW
- **areas:** Block 7 (shared state, per-process surface), Block 2 (entry-surface inventory)
- **kind:** risk
- **phase-task step:** "trace each one back to something that writes it"

**Evidence**

`src/mkobi/utils/file_utils.py:18-45` implements the per-user upload tree that the declared contract names, and it has no caller:

```python
18: def get_user_temp_dir(user_id: UUID | str) -> Path:
...
27:     cache_dir = Path(platformdirs.user_cache_dir("mkobi", appauthor=False))
28:     temp_dir = cache_dir / "uploads" / str(user_id)
29:     temp_dir.mkdir(parents=True, exist_ok=True)
...
34: def cleanup_temp_dir(temp_dir: Path) -> None:
```

Both are re-exported (`src/mkobi/utils/__init__.py:9,13,14`) and neither is referenced anywhere: the only `user_cache_dir` call in `src/` is the one inside `get_user_temp_dir` itself, and upload admission uses `get_config().upload_temp_dir` instead (`src/mkobi/api/routes/upload.py:203`, `src/mkobi/services/file_processing.py:199`).

The declared contract in `AGENTS.md` §5 names both locations explicitly:

> Сохранение в staging-папку через `platformdirs`: `UploadSettings.temp_dir` — `user_data_dir("mkobi", "ZOO") / "tmp_uploads"`, а per-user дерево загрузок — `user_cache_dir("mkobi", appauthor=False) / "uploads" / <user_id>`

The second of those two locations is never created. The consequence for the sweep is concrete: `cleanup_stale_temp_files` globs exactly one directory (`src/mkobi/services/file_cleanup.py:73-77`):

```python
73:     upload_dir = Path(config.upload_temp_dir)
74:     pattern = "*.csv*"
```

so a tree under `user_cache_dir` would fall outside every sweep — the helper is currently unreachable, but re-enabling it without moving the sweep would reintroduce an un-swept temp area.

The same shape appears in `src/mkobi/core/redis_client.py`: `get_redis_client()` (`:23`) and `close_redis_client()` (`:87`) have no caller in `src/` — the live code paths use the async pair `get_async_redis_client()` / `close_async_redis_client()`.

Both remainders date from the removal of the in-process queue recorded at `docs/SPEC.md:216` (TOPO-002/003) and from the upload-path consolidation; `.ai/plans/_code-context/10-production-ops-code-context.md:654` already notes "symbols the report names that do not exist today" for the same removal.

**Invariant broken**

A helper that nothing calls is a second, unwritten contract. Here it is a contract the project's own `AGENTS.md` still declares, so a reader following the documented upload path would look for a per-user tree that does not exist.

**Consequence**

No runtime failure. The maintenance cost is that `AGENTS.md` §5, `src/mkobi/utils/__init__.py`'s public surface and `core/redis_client.py`'s public surface all describe a topology that is not the one running.

**Recommendation** (advisory) — establish intent before removing anything, per the project's own dead-code policy. Two coherent outcomes: (a) the per-user tree is intended, in which case upload admission and `cleanup_stale_temp_files` should be moved onto `get_user_temp_dir` and the sweep widened to match; (b) it is residue, in which case delete `get_user_temp_dir` / `cleanup_temp_dir` and correct `AGENTS.md` §5 so the documented upload path matches the running one. The same question applies to `get_redis_client` / `close_redis_client`.

**effort:** small · **priority:** recommended

---

### TOPO-112 — `SPEC.md` describes a worker command line and a configuration coupling that no longer exist

- **severity:** LOW
- **areas:** Block 1 (component contract), Block 5 (the executor)
- **kind:** defect
- **phase-task step:** "report it only where the code's own documentation or comments misstate it"

**Evidence**

`docs/SPEC.md:185` states:

> The `rq-worker` service does not need these variables — it receives its target from the explicit `--url redis://redis:6379/0` command line, and its worker code reads no Redis configuration.

Both halves are false against the shipped configuration.

**The command line carries no `--url`** — `docker/docker-compose.yml:250`:

```yaml
250:    command: ["/app/.venv/bin/python", "-m", "mkobi.rq_worker_wrapper"]
```

Confirmed on the running container: `docker inspect mkobi-rq-worker-1 --format '{{.Config.Cmd}}'` → `[/app/.venv/bin/python, -m, mkobi.rq_worker_wrapper]`.

**The worker does read Redis configuration** — `src/mkobi/rq_worker_wrapper.py:226-228` calls `_build_redis_url()`, which resolves `RedisSettings` (`src/mkobi/config.py:639-650`):

```python
226:     redis_url = _build_redis_url()
227:     if redis_url is None:
228:         raise RuntimeError("REDIS__HOST / REDIS__PORT / REDIS__DB / REDIS__PASSWORD must be set")
```

So the `REDIS__HOST` / `REDIS__PORT` / `REDIS__PASSWORD` variables are load-bearing for `rq-worker` in the same way they are for `app`, and the base compose supplies them (`docker/docker-compose.yml:277-280`).

**Invariant broken**

A component's documented configuration coupling is part of its contract. The sentence tells an operator that the worker tolerates a wrong or absent Redis host — the exact failure the same sentence warns about for `app`, where `rate_limiter_fail_closed` defaults to true. A worker pointed at the wrong Redis simply never picks jobs up, silently, while its process and its healthcheck stay green.

**Consequence**

An operator reading `SPEC.md` to decide whether the worker needs `REDIS__HOST` gets the wrong answer, in a paragraph that is otherwise correct and easy to trust. `.ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md:462` already flags this sentence (`PRF-7` "must not assert the worker receives…"), so the correction is known and unmade.

**Recommendation** (advisory) — rewrite the last sentence of `SPEC.md:185` to say the worker derives its URL from the same `RedisSettings` as `app` via `_build_redis_url()`, and that a wrong host there leaves the worker silent with a healthy process rather than failing loudly. That last part is the operationally useful half and belongs in the sentence.

**effort:** trivial · **priority:** recommended

---

### TOPO-113 — The development tier's aggregate readiness gate cannot observe the frontend component

- **severity:** LOW
- **areas:** Block 1 (readiness edges, per-tier)
- **kind:** gap
- **phase-task step:** "record what each component states it requires before it can work, and what the tier actually guarantees"

**Evidence**

`.\Makefile.ps1` declares `up` as a readiness gate — help text at `Makefile.ps1:71`:

```
71: up          Start dev stack and block until healthy
```

The implementation at `Makefile.ps1:397-400` delegates to Compose:

```powershell
397: function Invoke-Up {
398:     Invoke-DownMigrate
399:     Invoke-InHost "docker compose -p $DevProject ... up -d --wait"
400: }
```

`--wait` only waits on services that declare a `healthcheck`. Every long-lived dev component declares one except `frontend`:

| service | healthcheck | source |
|---|---|---|
| `db` | `pg_isready` | `docker-compose.yml:106-110` |
| `redis` | `redis-cli ping` | `docker-compose.yml:171-176` |
| `app` | `curl /health` | `docker-compose.yml:189-195`, re-enabled by `docker-compose.override.yml:78-79` |
| `rq-worker` | registry probe | `docker-compose.yml:268-273` |
| `frontend` | **none** | `docker-compose.override.yml:93-113` |

Observed in the running tier — every component carries a status except `frontend`:

```
$ docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml ps
mkobi-app-1        Up 32 hours (healthy)
mkobi-db-1         Up 3 days (healthy)
mkobi-frontend-1   Up 32 hours
mkobi-redis-1      Up 3 days (healthy)
mkobi-rq-worker-1  Up 32 hours (healthy)
```

`docker-compose.override.yml:100-101` exposes `5173`, and `docker/Dockerfile.frontend.dev:15` runs `npm ci` before `CMD ["npm","run","dev",...]` (`:28`), so the component has a real, non-trivial start-up window (install on first run, Vite's dependency scan afterwards) inside which port 5173 is not served.

**Invariant broken**

A readiness gate that returns before one component can work reports success for a stack that is not usable. `docker-compose.override.yml:81-83` states the intent for `app` ("`up --wait` then waits for the app's boot instead of returning on start"); the same guarantee is simply absent for `frontend`.

**Consequence**

`.\Makefile.ps1 up` returns, the developer opens `http://localhost:5173`, and Vite may still be scanning dependencies — a connection refused that reads as a broken setup and is not. Dev-only, so no production impact; the cost is a recurring false alarm on the project's most-used command.

**Recommendation** (advisory) — add a `healthcheck` to the `frontend` service in `docker-compose.override.yml` that probes 5173 (`wget -qO- http://localhost:5173/ >/dev/null 2>&1 || exit 1`, or a TCP probe via `nc -z`), sized to cover the install/startup window on first run. That makes the `up --wait` claim in the help text true for every component in the tier.

**effort:** small · **priority:** recommended

---

### TOPO-114 — The declared dev toolchain includes stubs for a dependency the project forbids

- **severity:** LOW
- **areas:** Block 2 (declared entry/toolchain surface)
- **kind:** defect
- **phase-task step:** "establish what the automated lint and static-typing gates actually include"

**Evidence**

`pyproject.toml:210-231` declares the dev group. Line 219:

```toml
219:    "pandas-stubs==3.0.0.260204",
```

`AGENTS.md` §3 lists pandas under **Запрещено** (forbidden) and names Polars as the only dataframe library; the same section mandates the toolchain as "**Инструменты**: uv, ruff, mypy". There is no pandas import anywhere in `src/` (repository-wide search for `import pandas` / `from pandas` returns no matches).

The same group also carries `black`, `isort`, `flake8`, `autopep8`, `twine` and `libcst` (`pyproject.toml:212-213,222,224,226,228`), none of which any `Makefile.ps1` target invokes — the only quality targets are `lint`, `format` and `typecheck`, all `ruff`/`mypy` (`Makefile.ps1:262-270`).

`pandas-stubs` in particular is not merely unused: it is the type-stub package for a library the project prohibits, present in every image built from `docker/Dockerfile:197` (`uv sync --dev`).

**Invariant broken**

The declared stack is the contract this audit and the agents' own instructions check against. A declared dev dependency for a forbidden library makes `AGENTS.md` §3 and `pyproject.toml` disagree about the stack, and nothing reports the disagreement.

**Consequence**

No runtime effect. The cost is contract ambiguity plus install weight: `pandas-stubs` pulls the full pandas stub set into the dev image for a library nothing imports, and a reader checking whether pandas is really banned here gets two answers.

**Recommendation** (advisory) — remove `pandas-stubs` from the dev group. It exists only to type-check pandas usage, and any pandas usage is itself the violation `AGENTS.md` prohibits. The unused linters/formatters can be removed in the same change, or kept deliberately — but if they are kept, the toolchain line in `AGENTS.md` §3 should say so, otherwise the manifest and the documented toolchain will keep disagreeing.

**effort:** trivial · **priority:** recommended

---

## Areas checked with no findings

Recorded explicitly so the coverage is legible. Each area was inspected against the named contract; no entry is recorded as clean because it was not read.

- **Block 1 — component inventory per tier.** Every service in `docker/docker-compose.yml`, `docker-compose.override.yml` and `docker-compose.test.yml` was inventoried and its compose dependency edges classified as ordering (`migrate: service_completed_successfully` at `:157`, `:169`) or readiness (health checks at `:106-110`, `:171-176`, `:189-195`, `:268-273`). Apart from TOPO-113 (the one component with no readiness edge) and TOPO-101 (one component that cannot reach its serving state), every component is either reached by a request or by submitted work: `migrate` by `app`/`rq-worker` completion, `db` and `redis` by the two Python services, `app` by the edge and the dev browser, `rq-worker` by the `default` queue, `frontend` by the dev browser, `test-app`/`tools`/`test-migrate` by the explicit `docker compose run` invocations documented at `Makefile.ps1:412-424`.

- **Block 2 — load-time work of each entry surface.** Read in full: `src/mkobi/main.py`, `src/mkobi/app.py`, `src/mkobi/rq_worker_wrapper.py`, `alembic/env.py`, `docker/Dockerfile` (all stages), `docker/Dockerfile.frontend.dev`, `docker/nginx/entrypoint-render.sh`. Apart from TOPO-101, TOPO-107 and TOPO-114, no entry surface reaches the network or the database during load: `check_dependencies` (`main.py:29-52`) is an in-memory import check; `alembic/env.py:28-72` defers `config.attributes["connection"]` resolution to `run_async_migrations`; the filesystem reach in `Settings.__init__` (`config.py:1021-1029`, creating the upload temp dir) is idempotent and performed by the process that needs it. Findings for this area are confined to gate coverage (TOPO-106) and the manifest (TOPO-107, TOPO-114).

- **Block 3 — preconditions and the startup window.** `lifespan` (`src/mkobi/app.py:120-221`) awaits `starter.startup()` before `yield`, and uvicorn runs `lifespan.startup()` before binding and listening, so no request is accepted before `DatabaseStarter.startup()` completes: `check_database_exists`, the Alembic revision check (`starter.py:268-297`), `ensure_admin_user` (`:300-353`, atomic `ON CONFLICT (username) DO UPDATE`), `run_dev_seeders` (`:509-517`, development only) and `cleanup_old_logs` (`:433-455`). `main.py:29-36` re-checks dependencies after import, and `app.py:573-591` fails creation outright on a missing bundle or an unusable JWT secret, so there is no post-binding fallback. `start_stale_processing_cleanup_task` (`app.py:195-206`) is awaited before `yield` and publishes its state at `:207`, so `/health/detailed` never reads a missing attribute. **No startup-window finding.**

- **Block 4 — termination, drain and cancellation for the periodic loop.** `app.py:208-219` cancels the cleanup task, awaits it so the `CancelledError` handler at `data_worker.py:1588-1594` runs, releases the reconciler lease with an owner-checked Lua script, disposes the engine, closes the async Redis client and runs the starter's own shutdown, all inside a `fail-isolated` wrapper; `startup_failed` drives `os._exit(1)` only after that teardown has run. Nothing in the tree spawns a thread, a process or a `BackgroundTask` that the process does not own (a repository-wide search for `create_task`, `Thread`, `Executor`, `multiprocessing` and `BackgroundTasks` returns only the one reconciler `create_task` in the lifespan and RQ's own scheduler internals). **No termination finding for the periodic loop.** Reconciliation of work the *RQ worker* abandons at termination is TOPO-103's subject.

- **Block 5 — periodic loop convergence.** `start_stale_processing_cleanup_task` (`data_worker.py:1509-1585`) sleeps in 30 s slices, renews the lease on the tick and re-acquires it when a non-holder becomes the holder, `break`s only on shutdown, and re-acquires after every `RedisError` because the lease fails open — so a Redis outage lengthens the sleep and shortens no sweep. Its liveness is observable from outside the process: `ReconcilerStatus` (`app.py:207`, `data_worker.py:1502-1507`) is published on `/health/detailed` as `active`, `lease_holder`, `last_success_at` and `sweep_count`, and the live instance confirms the sweep is running on the declared 300 s cadence. **No convergence finding.** Submission-mechanism inventory: exactly one (`core/task_queue.py:52` `enqueue_job`), reached from `services/file_processing.py:344`; no mechanism exists that is started and never receives anything.

- **Block 6 — schema bootstrap gate and advisory-lock semantics.** Every path that can mutate the schema was enumerated: the `migrate` one-shot (`docker-compose.yml:150-183`), the in-process `_apply_migrations` behind `auto_migrate` (`starter.py:186-205`), the ad-hoc CLI `main()` (`starter.py:623-633`), the test-harness create (`tests/conftest.py:632`), the test-harness drop (`tests/conftest.py:169-230`), plus `docker/init-scripts/01-create-app-role.sh` and `ensure_admin_user` for reference data. Acquisition semantics were verified for each: the migration guard is `pg_try_advisory_lock` with 30 bounded attempts at 10 s and a **non-zero exit on refusal** (`db/migration_lock.py:78-98`), the holder is the process that executes the migrations (`alembic/env.py:113-128`), and the test-database guard is a single-statement `pg_advisory_lock` bounded by a transaction-scoped `lock_timeout` with `signed=True` key derivation (`db/test_database_lock.py:93-144`), the holder again being the process that runs the `DROP`. The only gap found is the unguarded second drop implementation — TOPO-108.

- **Block 7 — shared state, per component.** Four stores: PostgreSQL `bidb` (app, rq-worker, migrate), the `redis_data` volume (reconciler lease, rate-limit counters, token revocation, temp passwords, the RQ queue and worker registry), the `app_data` volume at `/app/data` (`app` writes `tmp_uploads`; `rq-worker` reads and deletes the artefact — `docs/06-backend/architecture.md:452` records that the reconciler does **not** run in `rq-worker`), and two in-process surfaces — the `app.state.reconciler_status` snapshot and the `functools.cache`d Redis clients in `core/redis_client.py`. Each was traced back to its writer: the one-shot temp credentials in `core/temp_password_store.py` are Redis-backed with a TTL rather than an in-memory marker, so a restart cannot lose them; `reconciler_status` is rebuilt at boot and its loss carries no work. **No shared-state finding**; the dead helpers whose contracts are never exercised are TOPO-111.

- **Block 8 — entry-layer back-imports and cycles.** A repository-wide search for `from mkobi.api` / `import mkobi.api` from outside `api/` returns no matches, so no lower layer reaches the router package. The two references to `mkobi.app` are the forward import at `main.py:14` and the cycle at `utils/exceptions.py:362` (TOPO-109). One duplicated contract was found in the entry layer — TOPO-110; the other duplication in scope (the drop statement) is TOPO-108.

- **Block 9 — route surface assembly and reachability.** The assembled table was enumerated from the live container rather than from the source: 68 routes, all under `/api/v1`, plus `/health`, `/health/detailed`, `/docs`, `/redoc` and `/openapi.json`. Every router in `src/mkobi/api/routes/__init__.py:33-44` is included through a parent router (`filter_values` through `dashboards.py:65`, `layouts` through `dashboards.py:81`), so none is orphaned. Every dashboard-scoped route resolves access through `require_dashboard_read_access` / `require_dashboard_write_access` / `require_dashboard_admin_access` (`deps.py:806-921`), or through `get_accessible_dashboard_ids` (`deps.py:929-971`), or through `check_dashboard_access` directly — satisfying `AGENTS.md`'s per-request access-control rule. Findings are TOPO-104 (no caller) and TOPO-105 (the fallback mount).

---

## Cross-finding analysis

**One shared cause behind TOPO-106, TOPO-107 and TOPO-114.** All three are the *declared* surface — the gate path list in `Makefile.ps1`, the `[project.scripts]` table and the dev dependency group in `pyproject.toml` — drifting from the real surface, with no gate asserting either direction of that agreement. The durable fix is one check that enumerates the declared entry points, confirms each resolves, and confirms each declared path is analysed by the gates; the three individual edits are the immediate work.

**One shared cause behind TOPO-111 and TOPO-112.** Both are residue of the in-process queue removal recorded at `docs/SPEC.md:216` (TOPO-002/003): the helpers that removal orphaned (`get_redis_client`, `get_user_temp_dir`) and the sentence that removal falsified (`SPEC.md:185`) were both left behind. `.ai/plans/_code-context/10-production-ops-code-context.md:654` and `.ai/decisions/ADJUDICATED-2026-10-03-product-owner-rulings.md:462` both record the intent to deal with them later; the later has not arrived. A single pass over that removal's blast radius closes both.

**The observability surface has one hole, and it is the component that mutates data.** TOPO-102 (no log handler on the worker) and TOPO-103 (a status answer the reconciler writes without consulting the queue) are independent defects, but they compound: today the only way to learn why a job failed is the `processing_logs` row, and TOPO-103 shows that row can hold a value the reconciler invented rather than observed. An operator diagnosing TOPO-103 on the deployed system has no second evidence source. Sequence TOPO-102 first — it is a one-call fix and it is what makes TOPO-103 diagnosable.

**Two findings are blockers for tiers nobody is currently running.** TOPO-101 means the production edge cannot start under the posture the compose file declares; TOPO-113 means `.\Makefile.ps1 up` returns before the dev frontend serves. Neither is visible from the currently-running dev tier, which is why neither shows up in `docker compose ps`. Treat the absence of evidence in the running tier as absence of coverage, not absence of defect — and note that TOPO-101 was found by reproducing the service's declared posture outside the running stack, which is the only way to reach it while the production profile is unused.

**The `TOPO-` namespace is now split.** Fourteen identifiers in `TOPO-101 … TOPO-114` coexist with the historical `TOPO-001 … TOPO-008` block documented at `docs/SPEC.md:216`. Any tooling that resolves findings by identifier must treat them as two disjoint ranges until the coordinator decides otherwise; a lookup for `TOPO-004` today means the historical migration-scaling finding, and after any renumbering it would silently mean something else.

---

## Appendix: component inventory and verdict per tier

Derived from the topology files and confirmed against the running dev stack. "Reached" means the component is the destination of a request, a submitted job, or an explicit `docker compose run`.

### Development tier (`docker-compose.yml` + `docker-compose.override.yml`, project `mkobi`)

| Component | Image / target | Command | Depends on | Readiness edge | Reached by | Verdict |
|---|---|---|---|---|---|---|
| `db` | `postgres:18-bookworm` | `postgres` | — | `pg_isready`, `:106-110` | `migrate`, `app`, `tests` | OK |
| `migrate` | `Dockerfile:dev` | `alembic upgrade head` | `db` healthy | `service_completed_successfully`, `:157` | `app`, `rq-worker` | OK |
| `app` | `Dockerfile:dev` | `uvicorn --reload` | `db` healthy, `redis` healthy, `migrate` completed | `curl /health`, `:189-195` | Vite proxy / browser | OK |
| `redis` | `redis:7.4-alpine` | — | — | `redis-cli ping`, `:171-176` | app, rq-worker | OK |
| `rq-worker` | `Dockerfile:prod` (the override hard-codes `prod`) | `python -m mkobi.rq_worker_wrapper` | `redis` healthy, `migrate` completed | registry probe, `:268-273` | RQ `default` queue | Findings TOPO-102, TOPO-112 |
| `frontend` | `Dockerfile.frontend.dev` | `npm run dev -- --host 0.0.0.0` | `app: service_started` | **none** | dev browser | Finding TOPO-113 |
| `tools` | `Dockerfile:tools` | per-command | — | n/a (run-only) | `lint` / `format` / `typecheck` / `psql` | Finding TOPO-106 |

Observed: `docker compose ps` → `app` healthy, `db` healthy, `redis` healthy, `rq-worker` healthy, `frontend` with no status. Matches the table.

### Production tier (`docker-compose.yml`, profile `production`, project `mkobi`)

| Component | Command | Readiness edge | Reached by | Verdict |
|---|---|---|---|---|
| `db` | `postgres` | `pg_isready`, `:106-110` | `migrate`, `app` | OK |
| `migrate` | `alembic upgrade head` | `service_completed_successfully`, `:157` | `app` | OK |
| `app` | `uvicorn src.mkobi.main:app --workers 4` (`Dockerfile:229`) | `curl /health`, `:189-195` | `nginx` | Finding TOPO-105 |
| `redis` | `redis-server` | `redis-cli ping`, `:171-176` | app, rq-worker | OK |
| `rq-worker` | `python -m mkobi.rq_worker_wrapper` | registry probe, `:268-273` | RQ `default` queue | Findings TOPO-102, TOPO-103, TOPO-112 |
| `nginx` | `entrypoint-render.sh` → stock entrypoint | `curl http://localhost/health`, `:391-394` | external clients | **Finding TOPO-101 — cannot reach a serving state** |

Note on `app` under `--workers 4`: four lifespans run concurrently, each running `DatabaseStarter.startup()`. The reconciler is correctly elected to one replica by `core/reconciler_lease.py` (verified live: `mkobi:reconciler:stale_processing:lease` is present in the running dev Redis). `ensure_admin_user` is a no-op after the first run (`starter.py:317-341`), so the shared startup preconditions need no election. No finding.

### Test tier (`docker/docker-compose.test.yml`, project `mkobi-test`)

| Component | Command | Readiness edge | Reached by | Verdict |
|---|---|---|---|---|
| `test-db` | `postgres:18-bookworm` | `pg_isready`, `:38-43` | `test-migrate`, `test-app` | OK |
| `test-redis` | `redis:7.4-alpine` | `redis-cli ping`, `:60-65` | `test-app` | OK |
| `test-migrate` | `alembic upgrade head` | `service_completed_successfully`, `:79-82` | `test-app` | OK |
| `test-app` | `tail -f /dev/null` (`:115`) | none (`healthcheck.disabled: true`, `:116-118`) | `docker compose run --rm --no-deps test-app pytest` | Finding TOPO-108 (the teardown it runs) |
| `tools` | `Dockerfile:tools` | n/a (run-only) | `backup` / `restore` / `test-fresh` | — |

`test-app` is deliberately an idle container (`Makefile.ps1:412-424`, `docker-compose.test.yml:3-11`); it is not a finding, because no health edge is declared for it and no invocation expects it to serve.

### Entry-surface inventory

| Surface | Kind | Load-time reach | Verdict |
|---|---|---|---|
| `src/mkobi/main.py` | process entry (dev and prod `uvicorn` target) | import-time dependency check; `create_app()` at import (`:29`) | OK |
| `src/mkobi/app.py` | application factory | `get_config()` + `setup_logging` at import (`:43-48`); filesystem probe for the bundle (`:573-591`) | OK |
| `src/mkobi/rq_worker_wrapper.py` | process entry (`rq-worker`) | dependency check + Redis ping before `worker.work()` | Findings TOPO-102, TOPO-112 |
| `alembic/env.py` | one-shot entry (`migrate`) | config resolution only; the connection is deferred to `run_async_migrations` | OK (guard semantics verified — TOPO-108 covers the harness, not this) |
| `src/mkobi/db/starter.py::main()` | ad-hoc CLI (`python -m mkobi.db.starter --recreate-test-db`) | none; guarded by tier, name and advisory lock | OK |
| `docker/nginx/entrypoint-render.sh` | container entry (`nginx`) | writes a file into the container filesystem | **Finding TOPO-101** |
| `docker/Dockerfile.frontend.dev` | container entry (`frontend`) | `npm ci` at build; `npm run dev` at start | OK (readiness gap: TOPO-113) |
| `mkobi.app:app` (`[project.scripts]`) | declared console entry | cannot resolve | **Finding TOPO-107** |

---

## Appendix: areas deliberately not reported

Phase 01 owns process and architecture boundaries. The following were examined and are recorded here as out-of-scope rather than as findings, so a later phase does not have to re-derive them:

- **Redis durability** (`appendonly` not set on `redis`, `docker-compose.yml:168-176`) — a store reachable by two components. Phase 10 owns "the deployed container posture, artifact provenance and backup contract".
- **What the submitted work does once accepted** — the parse/transform/aggregate pipeline, the `dims`/`metrics` contract and the per-dashboard rebuild exclusion (`db/advisory_lock.py:90`). Phase 05 owns "what the submitted work does once accepted, and the pipeline it enters". TOPO-103 is reported only because it is a restart-semantics defect about the *accepted unit of work*, not a defect in the pipeline.
- **The `/health` and `/health/detailed` probe contract**, including the admin-only gate on the latter. Phase 10 owns "the health and readiness surfaces and what a probe is contractually promised". TOPO-105 is reported as a route-surface defect, not as a probe-contract defect.
- **RFC 7807 conformance and the `ErrorCode` mapping**, and the frontend `errorHandler.ts` extraction chain. Phase 11 owns transport correctness; `src/mkobi/utils/exceptions.py` was read only far enough to establish the import cycle (TOPO-109).
- **Startup-window ordering for the worker**, i.e. whether the reconciler loop on `app` could race the first RQ job. Block 5's convergence analysis found no defect; the RQ-versus-delete question is recorded as settled at `docs/SPEC.md:216` and is not re-opened.

---

## Verification performed

Everything below was run against the repository or the running dev stack on 2026-10-05. No file under `src/`, `frontend/src/`, `tests/`, `alembic/`, `docker/` or any production/config file was modified; this report is the only file written.

**Static inspection** — read in full: `Makefile.ps1`, `pyproject.toml`, `alembic.ini`, `docker/docker-compose.yml`, `docker/docker-compose.override.yml`, `docker/docker-compose.test.yml`, `docker/Dockerfile`, `docker/Dockerfile.frontend.dev`, `docker/nginx/entrypoint-render.sh`, `docker/nginx/nginx.conf.template`, `src/mkobi/main.py`, `src/mkobi/app.py`, `src/mkobi/rq_worker_wrapper.py`, `src/mkobi/startup.py`, `src/mkobi/config.py`, `src/mkobi/db/starter.py`, `src/mkobi/db/session.py`, `src/mkobi/db/migration_lock.py`, `src/mkobi/db/test_database_lock.py`, `src/mkobi/core/task_queue.py`, `src/mkobi/core/redis_client.py`, `src/mkobi/core/reconciler_lease.py`, `src/mkobi/core/temp_password_store.py`, `src/mkobi/core/logging_config.py`, `src/mkobi/core/permissions.py`, `src/mkobi/api/routes/__init__.py`, `src/mkobi/api/deps.py`, `src/mkobi/api/routes/dashboards.py`, `src/mkobi/api/routes/upload.py`, `src/mkobi/services/file_processing.py`, `src/mkobi/services/file_cleanup.py`, `src/mkobi/utils/exceptions.py`, `src/mkobi/utils/file_utils.py`, `alembic/env.py`, the load-bearing regions of `tests/conftest.py`, and the cited regions of `src/mkobi/workers/data_worker.py`, `src/mkobi/db/repositories/processing_log_repo.py` and `src/mkobi/db/models/processing_logs.py`.

**Repository-wide searches** — for `from mkobi.api` / `import mkobi.api` outside `api/`; for `setup_logging(`, `get_user_temp_dir(`, `cleanup_temp_dir(`, `close_redis_client(`, `get_redis_client(`; for `enqueue_job`, `enqueue_processing_job`, `acquire_dashboard_rebuild_lock`, `import rq`; for `create_task`, `BackgroundTasks`, `threading.Thread`, `ThreadPoolExecutor`, `ProcessPoolExecutor`, `multiprocessing`; for `import pandas` / `from pandas`; for `user_cache_dir` / `upload_temp_dir` / `temp_dir`; for `get_dashboard_permissions`, `require_role_dependency`, `require_viewer_role`, `ViewerUser`, `AdminUser`, `EditorUser`, `CurrentUser` across `src/` **and** `tests/`; and for `TOPO-0` across all markdown.

**Runtime verification against the running dev stack** (`mkobi` project: `app` healthy, `db` healthy, `redis` healthy, `rq-worker` healthy, `frontend` with no status):

1. `docker inspect mkobi-app-1 --format '{{.Config.Cmd}}'` → the reload command; the same for `rq-worker` (no `--url`) and `migrate` (`alembic upgrade head`) — evidence for TOPO-112.
2. `docker logs mkobi-app-1 --tail 120` → structured JSON records including DEBUG lines from `mkobi.workers.data_worker`; `docker logs mkobi-rq-worker-1 --tail 60` → only RQ's own lines — half the evidence for TOPO-102.
3. `docker exec mkobi-rq-worker-1 python -c ...`, replicating `start_rq_worker()` and calling RQ's `bootstrap()`: root handlers `[]`, effective level `30`, `isEnabledFor(INFO) == False`, an INFO record emitted nowhere and a WARNING record emitted bare — the decisive half of TOPO-102.
4. `docker exec mkobi-rq-worker-1 python -c "from mkobi.app import app"` → `ImportError` — evidence for TOPO-107.
5. Route-table enumeration inside `mkobi-app-1` → 68 routes plus the five document/health endpoints and no `/` mount (the dev image ships no bundle, so `app.py:579` logs the warning instead of registering the mount).
6. SPA-fallback probe: `docker run --rm -i mkobi/app:local` with `FRONTEND__DIST_DIR` pointed at a bundle stub and `TestClient` used without lifespan → `200 text/html` for `/`, `/nonexistent-route-zzz` and `/apifoo`; `404 application/json` for `/api/v1/nope` and `/api/v2/nope` — evidence for TOPO-105.
7. nginx entrypoint probe with the service's declared posture → `line 14: can't create /etc/nginx/nginx.conf: Read-only file system`, `EXIT=1`; a control run without `--read-only` renders successfully — evidence for TOPO-101.
8. `docker exec mkobi-redis-1 redis-cli KEYS '*'` → `mkobi:reconciler:stale_processing:lease` present, confirming the live lease election under Block 5.
9. `docker compose … ps` → the per-component health status table used in TOPO-113 and in the inventory above.

**Gate measurement through the project's own `tools` service** (`docker compose -p mkobi … run --rm --no-deps tools`, run-only; no service was started or stopped):

- `ruff check src/ tests/ alembic/env.py` → `All checks passed!`
- `ruff check alembic/ --output-format concise` → `Found 4 errors.` (`UP035` plus 3× `UP007`, all in `alembic/versions/82739c97fde1_add_error_code_column_to_processing_.py`)
- `mypy alembic/env.py --no-incremental` → `Success: no issues found in 1 source file`, confirming that `exclude = ["alembic/"]` applies to directory discovery and not to explicitly named files

**Not executed:** `.\Makefile.ps1 test` and `.\Makefile.ps1 check` were not run. The phase does not require them, they neither add nor remove evidence for any finding above, and the full suite would have required starting the test tier.
