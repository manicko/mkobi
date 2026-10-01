---
phase: 10-production-ops
executed: 2026-09-30
executor: validator
problems-only: true
baseline: c55550be2317951912a3682ba57d04ebf8bf1b54
baseline-dirty: >-
  clean of tracked modifications; 19 .ai/ files still deleted
  (.ai/structure, .ai/builders, .ai/models, .ai/templates, .ai/plans,
  .ai/audit/templates/audit-final-report.md); .ai/audit/{01..11,99-validation} untracked.
baseline-note: >-
  The input filed against b23a9cb and closed at eeb9a5e. HEAD moved once under this validation,
  eeb9a5e -> c55550b, landing three commits (14be95c, 183056d, c55550b), all of them phase-02
  remediation tail work (settings/app.yaml + tests/test_config.py, then the configuration
  reference, then the deployment, docker and run guides). One of them edits a document this
  report cites, so every anchor below was re-resolved at c55550b: docs/11-guides/docker.md:361-363
  (the RQ worker note OPS-002 rests on) and :367-369 (the "only service gated by the production
  profile" statement OPS-015 rests on) are unchanged, and docs/10-deployment/deployment.md is
  untouched, so no verdict changes. The one consequence is recorded in VAL-10-005. The two
  working-tree modifications present at eeb9a5e (src/mkobi/settings/app.yaml,
  tests/test_config.py) were committed as 14be95c; no code file is dirty.
findings: 16
by-severity:
  CRITICAL: 0
  HIGH: 5
  MEDIUM: 11
  LOW: 0
validation-findings: 6
by-validation-severity:
  CRITICAL: 0
  HIGH: 0
  MEDIUM: 5
  LOW: 1
---

# Phase 10 — Validated Findings (Production Operations)

## Summary

All sixteen `OPS-` findings were re-derived from the executing path, every location reference
resolved mechanically first, and Appendix A's four phase-02 closure claims re-derived independently
rather than accepted: **fourteen confirmed, two merged**. HEAD moved from the input's closing
`eeb9a5e` to `c55550b` during this validation; every anchor this report rests on was re-resolved at
the new head and none of them moved (Appendix B), so no verdict changed — but one of the three new
commits rewrote the very verification command CFG-006's closure rests on, into a form that cannot
execute, which is the sharpest form of the residual below. The merges are
the material result. **OPS-002 is a duplicate of phase 01's TOPO-002** — same root cause, same
anchors (`task_queue.py:159-192`, `app.py:129-143`), same evidence (no `rq:queue:default` key has
ever existed), same recommendation ("route `enqueue_job` through RQ or delete the service") — and
the input filed it with no merge ruling while ruling on nothing at all; the distinction the input
did draw (against TOPO-005, the duplicate cleanup loops) is real but points at the wrong rival.
**OPS-004 restates EXT-001**: the same two handlers, the same missing Redis component, the same
document line, the same single edit, cited with phase 07's own measurement.

The phase-02 verification itself holds on all four claims, and the mechanism CFG-001 relies on is
true — an `environment:` map literal provably beats an `--env-file` value: with
`--env-file docker/.env.production --env-file <file declaring ENV=development>`, all three services
still resolve `ENV=production` while an interpolated neighbour (`LOGGING__JSON_LOGGING`) in the same
map *does* flip to `false`. Two defects surround that correct answer: the input's stated method
cannot have produced its stated output (the shipped `docker/.env.production` has every secret
commented out, so the command it names exits 1 before resolving anything), and its CFG-006 row
closes the claim by citing `deployment.md:167` as a working invocation when that invocation cannot
start the stack.

Two findings survive with a corrected mechanism rather than a corrected verdict. OPS-008's
multiplier is **four** writers, not five: `Multiprocess.run()` in uvicorn 0.49.0 logs the parent,
calls `init_processes()` and never calls `config.load()`, so the parent never imports
`mkobi.main` and never runs `setup_logging()` — the input's "×3 (parent + 2 workers)" at
`--workers 2` is not reproducible from the shipped source. OPS-003's directory is **git-ignored**,
not unignored: `git check-ignore -v` returns `frontend/.gitignore:11` and root `.gitignore:13`, and
the root `dist/` rule matches at any depth. Both sharpen the finding rather than weaken it.

The input's two refuted-by-measurement candidates were re-tested and both refutations stand, with
one correction: `setup_logging()` does run once per worker child, and `deploy.resources.limits` is
applied by this engine (`Memory=1073741824` on `app`, `536870912` on `rq-worker`) — the latter
independently corroborated by phase 11's PERF-001, whose 101.2 % peak was measured against a limit
that was genuinely in force.

## Findings

Identifiers are preserved; none was renumbered. Disposition is carried inside the Observation
field, because the shared template mandates no disposition field.

**Disposition tally** — confirmed **14** (OPS-001, OPS-003, OPS-005, OPS-006, OPS-007, OPS-008,
OPS-009, OPS-010, OPS-011, OPS-012, OPS-013, OPS-014, OPS-015, OPS-016); merged **2** (OPS-002 →
TOPO-002, OPS-004 → EXT-001); re-typed **0**; re-graded **0**; not substantiated **0**; unsettled **0**.
Two of the fourteen confirmed carry a corrected mechanism rather than a corrected verdict (OPS-003,
OPS-008). Bands: five HIGH and eleven MEDIUM as filed, none re-graded; the two merged findings lose
their HIGH bands to the findings that already hold those elements (TOPO-001 at HIGH, TOPO-003 and
TOPO-002 at MEDIUM).

### OPS-001 — The only record that a token was revoked or a user deactivated lives in an unbacked volume that no export path covers

**Severity** — HIGH

**Zone** — The shared transient store: every key it holds, every marker's lifetime, and what its loss stops

**Observation** — Disposition: **confirmed**; band upheld at HIGH, which the rubric's HIGH clause
"a store whose loss silently stops decisions the system believes it is making" states almost
verbatim. Re-derived independently. `redis_data` is declared at `docker-compose.yml:164` and `:278`
and named nowhere else in any compose file, `Makefile.ps1` or `docker/scripts/`: a repository-wide
search for `redis_data|BGSAVE|--rdb|dump\.rdb` returns the two declarations, the two test-stack
volume names, four documentation tables and this audit set — no persistence command, no copy-out, no
scheduler. `Invoke-Backup` (`Makefile.ps1:279-290`) touches `postgres_data` only. The amplifier the
input cites is accurate and is **already filed elsewhere**: `user_repo.update` issues
`await db.flush()` and no commit (`db/repositories/user_repo.py:187`), the service layer adds none
(`services/user_service.py:272-274`), and `get_db_dependency` yields a session from `get_session()`
and never commits on exit (`api/deps.py:101-116`), so the `is_active=false` write never reaches disk
while `admin.py:174-182` writes the Redis marker afterwards. That write defect is **phase 03's
TXN-001** ("Four endpoints return success for a write that is never committed, and one of them is
account deactivation"), whose recommendation already names `update_user_active_status`; the input
cites it without a cross-reference. Anchor correction: the input cites `admin.py:176`; the unguarded
revocation call occupies `:176-181`.

**Evidence** — Static: a search for `redis_data|BGSAVE|--rdb|dump\.rdb` over `Makefile.ps1`,
`docker/**` and `docs/**` returns no persistence command (the two `docs/` hits are volume tables at
`docker.md:117` and `deployment.md:271`). Live: `redis-cli dbsize` → `3`; `keys 'rq:*'` →
`rq:workers`, `rq:workers:default`, `rq:worker:6cbca147…` — after a fresh container start at
17:29:21 UTC the store still holds no revocation, rate-limit or temp-password key, confirming the
input's observation that no negative authorisation has ever been written in this environment. The
commit path was re-read line by line: `user_repo.py:184-190` is `setattr` → `flush` → `refresh` with
no `commit()` between `user_repo.py:163` and the next method, and `deps.py:115-116` is the entire
dependency body.

**Consequence** — Unchanged. Losing the volume re-admits every revoked token and every deactivated
account with no error, because `is_token_revoked` / `is_user_tokens_revoked` answer `False` for keys
that do not exist. One addition the input does not make and this validation does: with CFG-004
remediated, the marker is now *also* the only surviving record of a revocation once the `postgres`
superuser credential has left the runtime services — the two fixes are complementary, not
overlapping.

**Recommendation** — Executable as written and correctly scoped. Two refinements. `redis-cli --rdb`
is a point-in-time copy taken over the wire and needs no write-side `BGSAVE`; `BGSAVE` plus a
`docker compose cp` of `/data/dump.rdb` matches the pattern `Invoke-Backup` already uses for
PostgreSQL and reuses the same stamped directory — but `Invoke-PruneBackups` (`:313-320`) filters
`*.dump` only, so an `.rdb` artifact needs that filter widened, a dependency the recommendation
does not state. Restore order matters: the Redis artifact must load **before** `pg_restore` runs, or a
restored cluster re-admits tokens issued against a pre-restart database.

### OPS-002 — The RQ worker runs, registers and is health-checked, and has never received a job; production processing runs on four per-worker in-memory queues

**Severity** — HIGH

**Zone** — Service coverage and provenance: what the deployment defines, starts, and actually runs

**Observation** — Disposition: **merged** into phase 01's **TOPO-002** (MEDIUM, raw and validated).
The mechanism is real and was reproduced, but it is one finding filed twice. TOPO-002 is titled
"The deployed RQ worker has never received work; every submission goes to the serving process's
memory" and rests on the same anchors this finding cites — the module-global `default_queue`
(`core/task_queue.py:159`), the in-process drain loop (`app.py:129-143`), the single product call
site (`services/file_processing.py:366`) and the `rq-worker` service with a healthcheck and no writer
(`docker-compose.yml:180-237`). Both evidence blocks are the same observation (Redis holds no
`rq:queue:*` key) and both recommendations are the same choice between routing `enqueue_job` through
RQ and deleting the service. Re-derived here: `enqueue_with_worker` (`task_queue.py:55-76`) still has
**no caller** anywhere in `src/`; `rq` is imported by exactly one module, `rq_worker_wrapper.py:12-13`,
which no compose service invokes (both files run the bare `/app/.venv/bin/rqworker` CLI —
`docker-compose.yml:185`, `docker-compose.override.yml:127`). The input's band does not survive the
merge: the queue-loss element it grades HIGH is already held at HIGH by phase 01's **TOPO-001** (a
failed job's `processing_logs` row stays at `UPLOADED` until the next process start) and at MEDIUM by
**TOPO-003** (accepted work and its outcome held only in the serving process, with
`TaskQueue.shutdown()` never called). What remains after those are removed is MEDIUM by this rubric:
a container, a healthcheck and a documented production queue that nothing writes to, plus a
documentation claim contradicted by the deployed arrangement — "a documented procedure or claim that
is inaccurate, but whose consequence an operator can work around". The input's distinction against
TOPO-005 is real (TOPO-005 owns the duplicated cleanup loops, this owns queue loss) but it is the
wrong rival; the duplicate is TOPO-002.

**Evidence** — Independent reproduction after the worker's own restart at 17:29:21 UTC:
`docker logs mkobi-rq-worker-1` shows `started with PID 1, version 2.9.1` → `*** Listening on
default...` → only `cleaning registries for queue: default` at 17:42:51, and a count of every job
line (`rq: worker|Job OK|Result`) over the container's entire log returns **0**. `keys 'rq:*'` →
three keys, none a queue list; `rq:queue:default` does not exist. The asserted cause was tested
separately and holds: `Multiprocess.run()` in uvicorn 0.49.0's
`uvicorn/supervisors/multiprocess.py` logs the parent pid, calls `init_processes()` and then loops on
`handle_signals()` / `keep_subprocess_alive()` — it never calls `self.config.load()`, so the parent
does not import `mkobi.main`; each of the four workers constructs its own `default_queue`, exactly as
filed.

**Consequence** — Unchanged in substance. The input's framing of four per-worker in-memory queues is
the accurate half; the consequence that distinguishes this from TOPO-005 is real, but it is TOPO-003's
consequence and is already filed.

**Recommendation** — Do not schedule separately; merge into TOPO-002, whose recommendation already
prefers routing through RQ and whose roadmap step 2 already sequences it. One correction to carry
into the merged item: the input's proposal — dispatch through `rq.Queue` when `rq` is reachable and
fall back to the in-memory queue otherwise — reintroduces exactly the silent-fallback shape
`docker.md:361-363` already misdescribes, and phase 01's VAL-005 already flagged this recommendation
for offering both options without choosing. Choose one: `rq.Queue` with the fallback removed, or
delete the service.

### OPS-003 — The production SPA is served from an unversioned host directory, so the documented image rollback cannot restore the client bundle

**Severity** — HIGH

**Zone** — Service coverage and provenance: what the deployment defines, starts, and actually runs

**Observation** — Disposition: **confirmed**; band upheld at HIGH, the rubric's HIGH clause "a
recovery path that does not restore a whole-stack known-good state". The asserted mechanism is half
false and is corrected (VAL-10-006): the input states the host directory "is neither tracked in git
nor ignored" and that the root `dist/` rule "is rooted, so it does not match `frontend/dist/`". It is
ignored — twice. Everything load-bearing survives. The bind mount is
`../frontend/dist:/usr/share/nginx/html:ro` (`docker-compose.yml:251`), `nginx.conf:49-53` serves
`/usr/share/nginx/html`, and the `prod` stage separately bakes
`--from=frontend-builder /app/frontend/dist` into the app image (`Dockerfile:166`), so two artefacts
carry one output and the served one is the host copy. No compose service declares `image:`, so the
only artefact coordinate is the local `mkobi-app:latest`, overwritten in place.

**Evidence** — `git ls-files frontend/dist | Measure-Object -Line` → **0**;
`git check-ignore -v frontend/dist frontend/dist/index.html` → `frontend/.gitignore:11:dist` for
both (the root `.gitignore:13` `dist/` would also match at any depth; the input's `.gitignore:15`
anchor is off by two). `Makefile.ps1`'s help block (`:74-81`, `:96-98`) lists no `fe-build`, and a
search of every `.ps1` for `npm run build|vite build|fe-build` returns nothing;
`docker-compose.yml:239-241` states the prerequisite in a comment and nothing performs it.
`docker images mkobi*` shows five `:latest` and no versioned tag. The host directory currently holds
a bundle, so the gap is live rather than hypothetical.

**Consequence** — Unchanged, and sharper than filed: because the directory is *ignored* rather than
merely untracked, both recovery moves an operator reaches for fail — `git clean -xfd` removes the
served bundle, and a fresh clone or a second checkout has none, so
`docker compose --profile production up` creates an empty host directory and nginx answers 404 for
`/`. The bundle is reproducible only by running `npm run build` by hand.

**Recommendation** — Executable as written; take the first alternative (an nginx stage in the
Dockerfile copying `--from=frontend-builder /app/frontend/dist`), because it is the only option under
which the rollback this finding is about becomes possible. Do not ship both, as the input says. If the
bind mount is retained, add the `fe-build` target **and** note that `.gitignore` will otherwise hide
the bundle from `git status` at exactly the moment an operator needs to know it is stale.

### OPS-004 — The health contract an observer acts on cannot see the dependency that decides every authenticated request

**Severity** — HIGH

**Zone** — The health contract an observer can act on

**Observation** — Disposition: **merged** into phase 07's **EXT-001** (HIGH, raw and validated). The
co-ownership the phase-07 validator assigned was honoured in the note but not in the filing: what
OPS-004 states is EXT-001's mechanism restated — the same two handlers, the same two probed
components, the same absent Redis check, the same one-line fix. Re-derived independently and
unchanged: `app.py:248-267` (`/health`) executes exactly `SELECT 1` against PostgreSQL and returns
`{"status": "healthy", "database": "connected"}`; `app.py:269-307` (`/health/detailed`) builds
`components` from exactly two assignments — `database` at `:287` and `:294`, `static_files` at
`:301-304` — and a search for `redis` over `src/mkobi/app.py` returns no match, so the dependency
every protected request reads is examined by neither endpoint. Phase 10's distinct contribution is
narrower than the input makes it and is retained as the phase-10 half: the *consumers* of the contract
in the deployed composition (`Dockerfile:176-177` and `docker-compose.yml:146-151`, both
`curl -f /health`; `nginx`'s `depends_on: app: condition: service_started`), and the fact that the dev
overlay disables the container healthcheck outright (`docker-compose.override.yml:115-116`), which
makes the `/health` 200 a tier-independent property and the Docker consequence a production-tier one.

**Evidence** — Static, all anchors resolving at `eeb9a5e`: `app.py:249,258,270,281,287,301,306`;
`Dockerfile:176-177`; `docker-compose.yml:146-151`; `docker-compose.override.yml:115-116`. Phase 07's
outage measurement is cited and not re-measured, exactly as the input states — this validation did not
pause a shared Redis either. The documentation claim was re-checked and is accurate:
`docs/05-health/health-api.md:118` enumerates the components checked and `:182` tells operators to use
`/health/detailed` "for a component-level status overview"; Redis is in neither.

**Consequence** — Unchanged. One correction of scope: because
`docker-compose.override.yml:115-116` disables the dev healthcheck, the "the container stays healthy
during an outage" half of the input's consequence is a production-tier property and does not follow
from the dev stack. The operator-facing half — the liveness/readiness and uptime rules at
`health-api.md:177-184` — is tier-independent and carries the finding.

**Recommendation** — Schedule once, under EXT-001, which already carries an executable version with
its shipped-test check recorded (`tests/test_health.py:110-125` asserts component presence, not an
exact set, so adding `redis` does not break it). Phase 10's retained half adds one requirement to that
single change: the 503 policy must be decided against `RATE_LIMITER_FAIL_CLOSED`, which CFG-006 has now
wired to `true` on `app` and `rq-worker`, so the two tiers agree on what `unhealthy` means. The
input's `socket_connect_timeout` advice is correct and should be kept.

### OPS-005 — `backup` reports success unconditionally after the dump step, `restore` never examines what it restored, and there is no rehearsal path

**Severity** — HIGH

**Zone** — Evidence that a restore works

**Observation** — Disposition: **confirmed**; band upheld at HIGH. Re-read line by line at `eeb9a5e`
and every element holds. `Invoke-Backup` (`:279-290`) checks `$LASTEXITCODE` after `pg_dump` at `:286`,
then runs `docker compose … cp db:/tmp/mkobi.dump $dest` at `:287` with no exit-code check, no
`Test-Path` and no length assertion, then `rm -f` at `:288`, then prints
`Write-Host "Backup created: $dest" -ForegroundColor Green` at `:289` unconditionally.
`Invoke-Restore` (`:292-306`) checks the inbound `cp` at `:303`, runs
`pg_restore -U postgres -d bidb --clean --if-exists` at `:304` with its result never read, and ends at
`:305` with `rm -f`. The script's last statement is `exit $LASTEXITCODE` (`:441`), which by then holds
the status of that trailing `rm` — zero. Both targets report success on failure. There is no
`rehearse-restore` target, no restore of an artefact taken at a different time than the database it
restores into, and no `RPO`/`RTO` stated in any document outside the vendored `docs/STRUCT.md`.

**Evidence** — Static read of `:279-290`, `:292-306` and `:441`, and of `Show-Help` (`:90-93`),
which documents `backup`, `restore <file>` and `prune-backups` and nothing else. The exit-status chain
was traced: `Write-Host` does not reset `$LASTEXITCODE`, so a failed `cp` at `:287` is followed by a
successful `rm` at `:288` and the script exits 0. The failure premise was not re-induced here — it
would write into the shared `backups/` directory and the `bidb` database that peers own — and the
script logic is dispositive without it, so the input's live `docker compose cp` measurement is
accepted on that basis.

**Consequence** — Unchanged, and stronger than filed in one respect: `restore` returning 0 means an
automated caller of the documented entry point cannot detect the failure either, so the missing
exit-code check is invisible not only at the terminal but to every scheduled caller that will
eventually wrap this target.

**Recommendation** — Executable as written. Two corrections of emphasis. `pg_restore` returns 1 on a
recoverable error **without** `--exit-on-error` — it continues past errors and exits non-zero at the
end — so the option changes where it stops, not whether it reports; the missing `$LASTEXITCODE` check
is the whole defect, and a reader must not read the option as the fix. `pg_restore --list` verifies
the copied file's catalogue, not its integrity, so the rehearsal target is the only step that closes
the loop; the input's Rollout Safety ordering (assertions first, against a scratch database) is
correct and should be kept.

### OPS-006 — `nginx`'s access and error streams are written to a tmpfs on a read-only root: absent from `docker logs`, absent from the filesystem, gone on every recreation

**Severity** — MEDIUM

**Zone** — Signals produced, signals consumed, and the log paths that bypass the structured output

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM ("degraded operability with a
workaround"). Re-derived at `eeb9a5e`. `docker/nginx/nginx.conf:10-11` sets
`access_log /var/log/nginx/access.log` and `error_log /var/log/nginx/error.log` — file paths, not
`stdout`/`stderr` — and no `/dev/stdout` or `/dev/stderr` target appears anywhere in the file.
`docker-compose.yml:255-260` sets `read_only: true` on `nginx` and mounts `/var/log/nginx` as a
`tmpfs` alongside `/tmp`, `/var/cache/nginx` and `/var/run`; no `logging:` driver block exists in any
compose file and no volume maps `/var/log/nginx` out. The application's own stream is unaffected:
`core/logging_config.py:102-109` installs a `StreamHandler` on `ext://sys.stdout`, so every
application and `uvicorn.access` record reaches `docker logs`.

**Evidence** — Static: `nginx.conf:10-11` and `:49-53`; `docker-compose.yml:243-267` (the whole
service block, no `logging:` key, no `/dev/stdout`, four tmpfs mounts, `profiles: [production]` at
`:266-267`). `nginx` is profile-gated and absent from the running dev stack, so nothing was started
to observe the streams — the input states this limit and it holds; the configuration is dispositive.

**Consequence** — Unchanged: the fronting tier's request and error streams reach no collector and no
host path, and are destroyed whenever the container is recreated, which `docker compose up -d` does on
every configuration change, image rebuild and host reboot under `restart: unless-stopped`. A request
that fails at the edge — a 413 from `client_max_body_size`, a 502 while the app restarts — leaves no
trace.

**Recommendation** — Executable as written and correctly minimal: point both directives at
`/dev/stdout` and `/dev/stderr warn;` and drop `/var/log/nginx` from the tmpfs list. One dependency
the input does not state: the nginx image's base `nginx.conf` is replaced by the bind-mounted file
(`docker-compose.yml:250`), so the change is confined to that one file and needs no image rebuild.

### OPS-007 — The system exposes no metrics surface at all, so no alert expression can be evaluated against it

**Severity** — MEDIUM

**Zone** — Signals produced, signals consumed, and the log paths that bypass the structured output

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM. The block this finding comes
from requires the absence to be filed rather than omitted from an inventory, and the requirement is
met. Re-derived: no `/metrics` route exists — the router list at `app.py:236-246` declares the eight
API routers and the two health handlers at `:248` and `:269` are the only non-API paths — and no
exporter, alert rule, dashboard or collector is shipped anywhere in the repository.

**Evidence** — A search for `prometheus|/metrics|opentelemetry|alertmanager` over `src/`, `docs/`,
`docker/` and `Makefile.ps1` returns incidental hits only (vendored/generated text in
`docs/STRUCT.md`, and "metrics" in the chart-measurement sense at
`docs/11-guides/extend-graphs.md:72`). `Get-ChildItem .github` returns nothing, so no alert
definition exists outside a human's notes.

**Consequence** — Unchanged. Recorded as adjacency rather than duplication: the specific conditions
this finding lists as silent are already the subjects of OPS-001 (Redis state), OPS-002 (queue depth)
and OPS-010 (the one-shot step's completion), and its own sentence that an operator's only inputs are
the health verdict and the log stream repeats OPS-004 and OPS-008. What is distinct is the inventory
itself — there is no series for any alert to be written over — and that is what survives the overlap.

**Recommendation** — Executable and correctly bounded: three fields on `/health/detailed` and no new
dependency. One ordering constraint to add, because it collides with a merge decided elsewhere: the
`redis` field and its timeout belong to the single edit already scheduled under EXT-001 (see OPS-004),
so this finding must not schedule a second `app.py` change to the same handlers. The `alembic_version`
field is safe and needs no owner coordination.

### OPS-008 — Under the production `--workers 4`, five independent rotating file handlers write the same file, duplicating every record and rotating it out from under each other

**Severity** — MEDIUM

**Zone** — Signals produced, signals consumed, and the log paths that bypass the structured output

**Observation** — Disposition: **confirmed with a corrected multiplier**; band upheld at MEDIUM. The
defect is real and the input's refutation of its own first hypothesis is correct — `setup_logging()`
does run once per worker. The count is **four, not five**, and the correction is VAL-10-003.
`setup_logging()` is called at module scope (`app.py:39`) and installs a `RotatingFileHandler` at
`LOGGING__LOG_FILE` with `maxBytes=10MB`, `backupCount=5` (`core/logging_config.py:111-122`). Under
`--workers 4` (`Dockerfile:179`) uvicorn 0.49.0 spawns four fresh interpreters that each re-import the
app module, so four handlers hold `app_data:/app/data/logs/app.log` with independent rotation state
and no lock. The parent is **not** a fifth: `Multiprocess.run()` in
`uvicorn/supervisors/multiprocess.py` logs the parent pid, calls `init_processes()` and then loops on
`handle_signals()` / `keep_subprocess_alive()` — it never calls `self.config.load()`, so the parent
never imports `mkobi.main`. The input's evidence line "×3 (parent + 2 workers)" cannot be reproduced
from the shipped source and is not reproduced here.

**Evidence** — `Dockerfile:179` (`--workers 4`); `app.py:21,39`; `logging_config.py:102-122`;
`docker-compose.yml:118` and `:208` (`LOGGING__LOG_FILE` on both `app` and `rq-worker`). Read from the
running image: uvicorn `0.49.0`; `uvicorn/_subprocess.py:18` `spawn = multiprocessing.get_context("spawn")`
(the input's `:19` is off by one); `Multiprocess.run()` / `init_processes()` / `keep_subprocess_alive()`
as quoted above, with no `config.load()` and no application import on the parent path;
`timeout_worker_healthcheck: int = 5` at `uvicorn/config.py`, confirming the OPS-002 and OPS-011 claims
at the same reading.

**Consequence** — Unchanged: every record reaches `app.log` **four** times and each of the four
writers rotates independently, so records are duplicated, interleaved and lost. The volume ceiling is
4 × 6 × 10 MB = ~240 MB of `app.log*`, not the ~300 MB filed, on the same `app_data` volume that holds
`uploads/` and `tmp_uploads/`. At `LOGGING__LEVEL=WARNING` (`docker/.env.production:31`) the
duplicated records are the WARNING/ERROR ones, including every multi-kilobyte `logger.exception`
traceback. OPS-007's Consequence inherits the same correction: the log stream is duplicated **four**
ways, not five.

**Recommendation** — Executable as written, and the direction is right: one writer, not four or five.
The input's proposed gate (`remove the file handler in a uvicorn worker child, or enable it only for
the one-shot `migrate` service`) needs one addition — `migrate` does not set `LOGGING__LOG_FILE`
(`docker-compose.yml:61-81`), so "only where a single process owns it" currently names no service at
all; the effective change is to drop the file handler from the production `app`/`rq-worker`
environment and keep the console stream. The input's closing caution about
`WatchedFileHandler` not being multiprocess-safe is correct and should be kept.

### OPS-009 — Every quality-gate invocation materialises the application's full production credential set into a throwaway container that needs none of it

**Severity** — MEDIUM

**Zone** — What can prevent a change from landing, and what the aggregate entry point omits

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM, and the input's reasoning for
not grading it higher ("the gates that matter are not automatable today, phase 09 owns that verdict")
is the right one. Re-derived at `eeb9a5e`: `Invoke-Lint`, `Invoke-Format`, `Invoke-Typecheck` and
`Invoke-MigrationNew` all run `docker compose @DevCompose run --rm --no-deps app <cmd>`
(`Makefile.ps1:222,226,230,260`), and the `app` service carries `JWT__SECRET_KEY` and
`ADMIN_PASSWORD` through `${VAR:?}` interpolation (`docker-compose.yml:112,116`). `--no-deps` means
`ruff check src/ tests/` needs no database. `Invoke-Check` (`:241-249`) begins with `Invoke-Lint`, so
this precedes every verdict.

**Evidence** — `Makefile.ps1:222,226,230,260`; `docker-compose.yml:96-129` (the `app` environment
block, 19 keys, of which `JWT__SECRET_KEY:112`, `ADMIN_USERNAME:115`, `ADMIN_PASSWORD:116` and
`CORS_ORIGINS:127` are credential-bearing). The resolved production `app` service was inspected for
key *presence* only; no secret value was read or recorded. After CFG-004, `DATABASE__ADMIN_PASSWORD`
is no longer among them, which narrows the set by one without changing the finding.

**Consequence** — Unchanged: the credential set the runtime needs is handed to every static-analysis
process, widening the blast radius of a lint failure, an OOM kill or a crash dump, and making a
rotation strictly broader than it needs to be. The input correctly notes this is a standing
least-privilege break rather than an active incident.

**Recommendation** — Executable, and the `tools` service is the right shape. One dependency to state:
`Invoke-MigrationNew` (`:260`) runs `alembic revision --autogenerate`, which imports the application's
`Settings` and therefore needs `DATABASE__*`, `JWT__SECRET_KEY` and `UPLOAD__TEMP_DIR` — it cannot move
to a credential-free service unchanged. Route `Invoke-Lint`, `Invoke-Format` and `Invoke-Typecheck`
to `tools` and leave the alembic targets on `app`, or the `tools` service will fail at import. The
cache-directory workaround at `docker-compose.override.yml:95-100` is correctly identified as
removable with it.

### OPS-010 — The backup artifact is one database with no roles and no alembic state, and the only script that can restore the roles runs on first volume initialisation

**Severity** — MEDIUM

**Zone** — Backup: consistency, durability, and what each option changes

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM. Re-derived: `Invoke-Backup`
(`Makefile.ps1:285`) runs `pg_dump -U postgres -d bidb -F c -f /tmp/mkobi.dump` with no `--globals`
and no `--roles`, so the cluster's globals — the `postgres` superuser and the `mkobi_app` role with its
`GRANT SELECT, INSERT, UPDATE, DELETE` / `USAGE` grants — are absent from the artefact. The only place
those roles are created is `docker/init-scripts/01-create-app-role.sh`, mounted at
`/docker-entrypoint-initdb.d` (`docker-compose.yml:31-34`), which the official image runs **only when
the data directory is empty**; the script's own header says so at `:4`. `$BackupDir = 'backups'`
(`Makefile.ps1:37`) resolves inside the working tree, `prune-backups` (`:308-320`) is manual with no
scheduler, and `migrate` is `restart: "no"` (`docker-compose.yml:86`), so nothing re-runs on a
restart path.

**Evidence** — `Makefile.ps1:37,285,304,308-320`; `docker-compose.yml:31-34,86`; the init script's
`:4` header and its grant block at `:23-42`. `pg_dump --help` inside `postgres:18-bookworm` lists
`--globals`/`--roles` as separate options the shipped command does not pass.
`git check-ignore -v backups/bidb-20260930_111251.dump` → `.gitignore:254:backups/`, so a repository
loss takes the artefacts with it, as filed.

**Consequence** — Unchanged: restoring into a rebuilt cluster yields a database with no application
role, and the documented way to re-create the role (recreate the volume) destroys the database the
restore was meant to recover. One addition: with CFG-004 remediated, `mkobi_app`'s grants are now the
*only* definition of runtime database access outside the cluster's own init, so the artefact's
completeness gap and the credential split landed in the same commit and are more consequential
together than either is alone.

**Recommendation** — Executable as written; `pg_dumpall --globals-only` as a second stamped artefact,
loaded before the database restore, makes a restore into a rebuilt cluster a complete procedure. Two
orderings the input does not state: `psql -f globals.sql` must run **after** `pg_dump --clean
--if-exists` has finished dropping objects, not before (the roles own the grants the restore
re-issues), and the `alembic_version` print must come from the restored database rather than from the
running one, or it reports the state the operator already had.

### OPS-011 — An app lifespan failure becomes an unbounded worker respawn loop inside a container that never dies and never reaches a terminal state

**Severity** — MEDIUM

**Zone** — Restart and partial restart: ordering, address resolution, and one-shot steps

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM ("degraded operability with a
workaround": `restart: unless-stopped` and an operator reading `docker compose ps` are the workarounds,
and the input says so). Re-derived: the lifespan re-raises every startup failure
(`app.py:147-155` — `DatabaseNotFoundError` at `:149`, `SchemaNotFoundError` at `:152`, catch-all
`Exception` at `:155`), and in production PID 1 is uvicorn's `Multiprocess` supervisor, not a worker
(`Dockerfile:179`, `--workers 4`).

**Evidence** — Read from the running image rather than inferred: `Multiprocess.keep_subprocess_alive()`
iterates the child list, and for each child that fails `process.is_alive(timeout=self.config.timeout_worker_healthcheck)`
calls `process.kill()`, `process.join()`, logs `Child process [...] died` and starts a replacement —
no sleep, no counter, no threshold between the kill and the respawn; `run()` never returns while
`should_exit` is unset, so the container stays `Up`. `timeout_worker_healthcheck: int = 5` confirmed
in `uvicorn/config.py`. `docker-compose.yml:86` gives `migrate` `restart: "no"` and `:95-97` gates
`app` on `service_completed_successfully`, so the one-shot gate stays satisfied while the thing it
gated never becomes ready. The input's 70-second count of `Application startup failed` was **not**
re-measured here — re-inducing it means running a throwaway container against an unreachable database
on a shared daemon — and the static path above is unconditional, so the count is methodology.

**Consequence** — Unchanged: a crash-looping `app` reports itself as a running container whose
`HEALTHCHECK` stays `unhealthy`; `restart: unless-stopped` does not act on `unhealthy`, so nothing
outside the stack notices. `db`, `redis` and `rq-worker` keep running and `migrate` keeps reporting
success.

**Recommendation** — Executable as written. The direction is right and the input's own caveat is the
thing to carry into the roadmap: a terminal exit converts a crash loop into a container exit, and
Docker's backoff then makes a genuinely transient startup failure slower to recover from than the
current cycle. Verify against a slow-but-succeeding `migrate` before relying on it.

### OPS-012 — One Redis outage denies on some paths, admits on others, and the store's jobs have three different unguarded failure modes

**Severity** — MEDIUM

**Zone** — The shared transient store: every key it holds, every marker's lifetime, and what its loss stops

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM. The five-way divergence was
re-derived site by site and every anchor resolves exactly as filed: (i) the rate limiter catches
`Exception` and honours `fail_closed` (`core/security.py:137-151`); (ii) the revocation reads in the
per-request gate are unguarded (`api/deps.py:503-530`, `core/permissions.py:326-334`); (iii) the
revocation writes on logout are unguarded and ordered **before** the cookie clear
(`api/routes/auth.py:448` `revoke_refresh_token`, `:459` `revoke_token`, `:461`
`delete_secure_cookie` — read in this order, confirmed); (iv) `TempPasswordStore.store` catches,
logs and returns (`core/temp_password_store.py:47-48`) while `retrieve` logs and returns `None`
(`:73-75`); (v) `revoke_all_user_tokens` on deactivation is unguarded (`api/routes/admin.py:176-181`)
and runs **after** the database write (`:163-165`), with `except Exception: await db.rollback()` at
`:187-188`.

**Evidence** — Static read of the six cited sites; ordering of `auth.py:441 → 448 → 459 → 461`
re-read in file order. The latency measurement and the `redis-py` retry arithmetic are phase 07's and
are cited, not re-measured; `core/redis_client.py:46-52` passes only host, port, db, password and
`decode_responses`, with no timeout and no retry policy, as filed.

**Consequence** — Unchanged: one outage resolves one user-visible action three ways, and logout is
the worst of them — a 500 after ~59 s that **leaves the session live**, because the cookie is never
cleared and no marker is written, so the user is told their logout failed and has no action that ends
the session.

**Recommendation** — Executable, and the ordering fix is the important half: moving `delete_secure_cookie`
ahead of the revocation writes is a two-line change with no dependency on the timeout work and should
not wait for it. Two cautions the input does not give. Phase 07's VAL-07-004 already merged "catch
`redis.exceptions.RedisError` around the two revocation reads and map to 503" into **AUTH-008** — that
edit belongs to phase 04, so scheduling it twice will produce two teams in `deps.py:503-530`. And
CFG-006 has now wired `RATE_LIMITER_FAIL_CLOSED=true` explicitly, so the fail-closed arm is a declared
production policy in a way it was not before; the recommendation to give each job "one declared failure
mode" is now a change to a declared policy rather than a clarification of a default.

### OPS-013 — `client_max_body_size` and `UPLOAD__MAX_FILE_SIZE_MB` are coupled by nothing but a comment, and the tier that enforces the limit cannot read the setting

**Severity** — MEDIUM

**Zone** — The fronting tier: transport security, certificate lifecycle, and what is exposed

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM. Re-derived: `nginx.conf:18`
hard-codes `client_max_body_size 100m` with the comment at `:17` ("must match backend max_file_size"),
the commented HTTPS block repeats it, and the `nginx` service block (`docker-compose.yml:243-267`) has
no `environment:` key and mounts `nginx.conf` `:ro` at `:250`, so nothing templates the value in.

**Evidence** — `nginx.conf:17-18`; the resolved production `nginx` service carries neither an
`environment` nor a `configs.template` key (confirmed from the resolved JSON; nginx was never started,
which the input states and which does not affect a configuration claim). The application half was
re-derived and is genuinely wired rather than declared: a throwaway container with
`UPLOAD__MAX_FILE_SIZE_MB=7` resolves `config.upload.max_file_size_mb = 7` and
`Settings.max_file_size = 7340032`, so the env source outranks the YAML default of 100 — the coupling
is real in one direction and absent in the other.

**Consequence** — Unchanged: raising `UPLOAD__MAX_FILE_SIZE_MB` above 100 leaves the edge refusing
bodies the application would accept; lowering it lets nginx stream up to 100 MB into the app before
the app rejects it. Neither presents as a configuration error.

**Recommendation** — Executable, and the second option (template through
`/etc/nginx/templates` with `${UPLOAD__MAX_FILE_SIZE_MB}`) is the one to take: it is the only shape in
which the comment at `nginx.conf:17` becomes true rather than aspirational, and the nginx image's
`20-envsubst-on-templates.sh` entrypoint already exists in `nginx:1.27-alpine`, so no image change is
needed — only the file's location and an `environment:` entry on the service. Either way, delete the
"must match" comment, as the input says.

### OPS-014 — The hardened runtime boundary exists on `app` alone, and the dev overlay comments describe a restriction the production file never sets

**Severity** — MEDIUM

**Zone** — Effective runtime posture per service, after every layer is merged

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM. Re-derived from the merged
production definition: `app` alone carries `read_only: true` (`docker-compose.yml:139`),
`security_opt: [no-new-privileges:true]` (`:141-142`) and `cap_drop: [ALL]` (`:144-145`); `nginx`
carries `read_only` plus tmpfs and deliberately no capability drop, for the reason
`docker.md:382-385` gives and which holds; `rq-worker`, `migrate`, `db` and `redis` carry none of the
three. **Anchor correction:** the overlay comment the input places at
`docker-compose.override.yml:149-150` is at **`:153-154`** ("Override production `read_only` for
development (needs write access for processing)" above `read_only: false`), and `:149` is
`LOGGING__LEVEL: DEBUG`.

**Evidence** — `docker-compose.yml:134-145` versus the absence of any `read_only`, `security_opt` or
`cap_drop` key in the `rq-worker` block (`:180-237`) and the `migrate` block (`:55-86`). The input's
refutation of its own "the engine ignores declared limits" hypothesis is **independently confirmed
here**: `docker inspect mkobi-app-1` → `Memory=1073741824 NanoCpus=1000000000 CapDrop=[ALL]
SecurityOpt=[no-new-privileges:true] User=app`, and `mkobi-rq-worker-1` →
`Memory=536870912`. `deploy.resources.limits` is applied by this engine (29.8.0 / Compose v5.5.1) for
every service that declares one, so the asymmetry is in the file, not in the engine. Phase 11's
PERF-001 measured a peak of 1,036.2 MB against the same 1,073,741,824-byte limit, which corroborates
that the limit was genuinely in force.

**Consequence** — Unchanged: the one boundary that would blunt a parser or library escape is drawn
around one of the two services that run the same untrusted-parsing code, and around neither of the two
that hold the broadest credentials. The overlay comment additionally tells a maintainer that
`rq-worker` is read-only in production, and that its `read_only: false` relaxes something — both false.

**Recommendation** — Executable as written. Two ordering constraints. CFG-004 has just removed the
superuser credential from `rq-worker`, so extending `no-new-privileges` there is now a one-line change
with no credential trade-off to weigh. `rq-worker` mounts the shared `app_data` volume
(`docker-compose.yml:216-217`) and writes into it, so `read_only: true` needs the same tmpfs treatment
nginx uses, which the input states. `migrate` needs none of this to be true: it writes no volume at
all, so `no-new-privileges:true` is free.

### OPS-015 — `deployment.md` describes a system that does not exist: a profile-gated worker, a registry rollback, and a migration rollback that cannot execute

**Severity** — MEDIUM

**Zone** — Operational claims as testable artefacts

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM, with the input's own reasoning
that each of the three is workaroundable and the workaround unwritten. All three re-derived at
`eeb9a5e`. (a) `deployment.md:190-193` states that services with `profiles: [production]` include
**rq-worker**; the service at `docker-compose.yml:180-237` declares no `profiles:` key, and
`docker.md:367-369` says the opposite ("the only service gated by the `production` profile") — the
corpus contradicts itself, as filed. (b) `deployment.md:304-320` is the image-rollback procedure and
names `docker images mkobi/app` and `docker pull mkobi/app:<previous-tag>`; no compose service
declares an `image:` key and the resolved `app.image` is the empty string. (c) `deployment.md:235,237,
286,328,331,334,337` tell the operator to run `uv run …` inside `app`.

**Evidence** — `docker compose … config --services` → `db, migrate, redis, rq-worker, app` with no
profile, and `db, app, migrate, nginx, redis, rq-worker` under `--profile production` — `nginx` is the
only profile-gated service, confirmed twice. Resolved `app.image` = `''`; `docker images mkobi*`
returns five `:latest` and nothing versioned. (c) re-measured in the running container:
`docker exec mkobi-app-1 sh -c 'which uv'` returns nothing, `uv --version` returns `sh: 1: uv:
Permission denied`, exit 127. The static cause is identical in both stages and re-read:
`Dockerfile:51-52` and `:85-86` install `uv` into root's home while `:122` and `:172` set `USER app`.

**Consequence** — Unchanged. The combined statement is the one that matters and it is correct: with
OPS-003, **neither half of the deployed system is revertible**, and the promise at `deployment.md:302`
("safely roll back to a previous stable state") is not achievable by the procedure the same document
gives. (a) also has a practical trap the input records: following the doc to add "just the worker"
adds nginx and publishes port 80.

**Recommendation** — Executable as written, and the "correct `deployment.md` to match `docker.md`"
direction is right because `docker.md` is the accurate document. One correction of emphasis: the
image-rollback section should not be replaced with prose about `git checkout` — the honest replacement
is to give the services an `image:` coordinate first (OPS-016's step 1), because until one exists there
is nothing for any rollback paragraph to point at. The `uv run` corrections are straightforward and
`docker compose exec app alembic …` works, since the venv is on `PATH`.

### OPS-016 — Every external input that can change the built artifact without a source change is fetched by tag or by an unverified script, and no updater covers any of them

**Severity** — MEDIUM

**Zone** — What decides the artifact's content, per input class

**Observation** — Disposition: **confirmed**; band upheld at MEDIUM ("a documented procedure or claim
that is inaccurate, but whose consequence an operator can work around" does not fit; the rubric's
MEDIUM is reached through the floating-input class the block names explicitly, and the input's own
bounding — nothing here is a secret or a privileged action, and the lockfiles cover the application's
own dependencies — is the reason it is not higher). Re-derived: five base images are tag-pinned and
none digest-pinned (`node:20-alpine` at `Dockerfile:10`, `python:3.12-slim-bookworm` at `:28` and `:64`,
`postgres:18-bookworm` at `docker-compose.yml:17`, `redis:7.4-alpine` at `:162`, `nginx:1.27-alpine`
at `:244`); `uv` is fetched by `curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh`
(`:51-52`, `:85-86`) with `UV_VERSION` pinned but no checksum and no signature; Debian packages are
resolved unpinned against a configurable `DEBIAN_MIRROR` build arg (`:31-48`, `:66-82`); and the two
lock-pinned inputs (`npm ci` at `:18`, `uv sync --frozen` at `:136`/`:162`) are the only classes with
an integrity guarantee.

**Evidence** — `Dockerfile:10,18,28,31,51-52,64,66,85-86,136,162`;
`docker-compose.yml:17,88-94,162,180-184,244`. The target divergence re-derived and exactly as filed:
`app` builds with `target: ${DOCKER_TARGET:-prod}` and an explicit `UV_VERSION` build arg
(`docker-compose.yml:88-94`) while `migrate` (`:55-59`) and `rq-worker` (`:180-184`) declare
`target: prod` with no build args. `Get-ChildItem .github` returns nothing, so no Dependabot or
Renovate configuration exists; `docker/scripts/scan-images.ps1` is present and, as the input states,
wired into nothing.

**Consequence** — Unchanged: three of the four unpinned classes can change the artefact with no change
to the repository and no record of what changed. The target divergence is a latent defect rather than a
live one — the `ARG` defaults agree today only because no call site overrides `UV_VERSION`.

**Recommendation** — Executable as written, and the priority order is right: digest pinning costs
nothing at runtime and makes the build reproducible; the checksum-verified `uv` install is the only
item that removes a code-execution path; the `UV_VERSION` build arg should go to all three services;
and `scan-images.ps1` should either be wired to a schedule or deleted rather than left as an unwired
scanner. Note that digest pinning interacts with the audit's own convenience: `Makefile.ps1`'s
`rebuild` pulls no base images explicitly, so a digest pin plus a stale local cache turns a build into
a pull, which the input does not mention.

## Validation-Level Findings

Separate section, separate scale, separate namespace. The flat `VAL-` prefix is occupied by the
phase-01 and phase-02 validation reports, and phases 03 through 09 each adopted a phase-qualified
`VAL-NN-` variant; this report follows that established precedent with `VAL-10-`. The deviation from
the flat prefix the output contract specifies is recorded here and in Appendix E.

### VAL-10-001 — OPS-002 duplicates TOPO-002, and the input resolved a duplication it never acknowledged against the wrong finding

**Severity** — MEDIUM

**Zone** — Cross-Phase Conflict, Ownership and Merge

**Observation** — OPS-002 and TOPO-002 are one finding. The root cause is the same (a Redis/RQ queue
is declared, health-checked and never written to, while the product's only submission path targets an
in-process `asyncio.Queue`), the anchors are the same (`task_queue.py:159-192`, `app.py:129-143`,
`services/file_processing.py:366`, `docker-compose.yml:180-237`), the evidence is the same single
observation (no `rq:queue:*` key has ever existed), and the recommendation is the same binary choice.
Phase 01's validator confirmed TOPO-002 at MEDIUM and already flagged its two-option recommendation
(VAL-005). OPS-002 filed **no merge or adjacency ruling of any kind** — not against TOPO-002, not
against TOPO-003, whose "accepted work and its outcome are held only in the serving process" is the
same queue-loss consequence it restates, and not against TOPO-001, which already holds the stuck
`processing_logs` row at HIGH. The input's own Cross-Finding Analysis instead draws its one distinction
against **TOPO-005** — the duplicated periodic cleanup loops — which is a genuine and irrelevant
distinction: TOPO-005 owns four copies of a cleanup loop, not the queue.

**Evidence** — `.ai/audit/01-process-architecture/findings.md:77-124` (TOPO-002) against
`.ai/audit/10-production-ops/findings.md:86-125` (OPS-002); phase 01's validated report `:86-138`
(band upheld MEDIUM) and its VAL-005 at `:709-728`. No paragraph in the OPS-002 block contains a
merge, adjacency or ownership ruling, and neither `Cross-Finding Analysis` nor `Roadmap` mentions a
`TOPO-` identifier anywhere in the phase-10 report. The runtime re-derivation is in OPS-002's own
evidence above.

**Consequence** — Two teams will schedule the same decision, and the second one to land will either
duplicate the first or revert it. The set's owner cannot tell from the phase-10 report that the
defect already has a validated filing, and the phase-10 roadmap's step 3 restates phase 01's roadmap
step 2 as if it were new work. The band divergence compounds it: the same defect appears at HIGH here
and MEDIUM there, so an owner merging by severity alone closes it once and believes it is closed.

**Recommendation** — Record OPS-002 as merged into TOPO-002 in the set's merge register, naming
phase 01 as owner of the decision and phase 03's TOPO-001/TOPO-003 as the holders of the two
consequence elements OPS-002 restates. Do not renumber either phase's identifiers. Fold into the
merged item the two corrections this validation established: the multiplier is four in-memory queues,
and the recommendation must choose between RQ and deletion rather than offering a fallback that
re-creates the arrangement `docker.md:361` already misdescribes.

### VAL-10-002 — OPS-004 is a merge with EXT-001, not a co-owned cross-reference; the co-ownership assignment was met with a restatement

**Severity** — MEDIUM

**Zone** — Cross-Phase Conflict, Ownership and Merge

**Observation** — Phase 07's validator ruled EXT-001/EXT-002 "**not** merged" into phase 10 and named
phase 10 co-owner of the probe-contract half, on the reasoning that 07 files *what the probe measures*
while 10 files *the deployed composition* (Appendix F of that report). OPS-004 does not file the
deployed composition. It files the probe's coverage: the same two handlers, the same two components,
the same absent Redis check, the same cited measurement, the same one-line fix. That is EXT-001's
subject, in EXT-001's zone, with EXT-001's remedy. The phase-10 content that is genuinely distinct —
the `curl -f` healthcheck consumers at `Dockerfile:176-177` and `docker-compose.yml:146-151`, nginx's
`service_started` dependency, and the dev overlay disabling the healthcheck — occupies two sentences
of the Observation and no finding of its own, which is the correct disposition for it and the
incorrect one for everything around it.

**Evidence** — `.ai/audit/99-validation/07-external-boundary-validated-findings.md:1119-1136`
(Appendix F, the ruling and the sibling set compared) against the OPS-004 block at
`.ai/audit/10-production-ops/findings.md:167-208`. Anchors: EXT-001 cites `app.py:257-276` and
`:278-316` (its line numbers, taken at `c3c0a61`); OPS-004 cites `app.py:248-267` and `:269-307` — the
same two functions after the −9 drift the phase-07 validator itself recorded. Both cite
`health-api.md:118-128` and both recommend adding a `redis` component with a bounded timeout.

**Consequence** — Two teams will edit `app.py:248-307` and `health-api.md:118-128`, which are the same
lines in the same two files. The second to land either duplicates the first or silently reverts it.
Worse, the phase-10 roadmap schedules the change inside its own step 4 ("add the `redis` component to
the health surface") with no reference to the phase-07 report that already schedules it, so the set's
owner sees one task in two roadmaps rather than one task with a co-owner.

**Recommendation** — Split the disposition explicitly and schedule once. **Merged:** OPS-004's probe-
coverage mechanism merges into EXT-001, which is already validated, already carries an executable
recommendation and already records that `tests/test_health.py:110-125` does not block it. **Retained
as phase 10's:** the consumer inventory (Docker healthcheck, nginx `service_started`, the four
documented integrations) and the dev-overlay disablement — a cross-reference on EXT-001's change, not a
separate edit. Remediation owner: phase 07 for the code and the document; phase 10 for the
compose/Dockerfile consumers. EXT-002 is not part of this merge: its subject is blast radius and
per-request cost, and its code-change element is already merged into AUTH-008 by phase 07's VAL-07-004.

### VAL-10-003 — OPS-008's writer count is four, not five, and its supporting measurement cannot be reproduced

**Severity** — MEDIUM

**Zone** — The Claim Re-Derived from the Executing Path

**Observation** — OPS-008's Consequence states that "in production every record is written to
`/app/data/logs/app.log` **five** times" and derives a "~300 MB" ceiling from "5 × 6 × 10 MB". The
count is four. uvicorn 0.49.0's `Multiprocess.run()` never calls `self.config.load()`; it logs the
parent pid, calls `init_processes()` and then loops on `handle_signals()` and `keep_subprocess_alive()`.
`config.load()` is the only call that imports `mkobi.main`, and `main.py:55` is where `create_app()`
runs, which is the only place `setup_logging()` is reached. So the parent process installs no
`RotatingFileHandler` and writes no record: with `--workers 4` there are four writers, and with
`--workers 2` there are two. The input's own Evidence — "`Configuring CORS with allowed origins` ×3
(parent + 2 workers)" — cannot arise from the shipped code, because that log line is emitted once per
`create_app()` call (`app.py:217`) and `create_app()` is called exactly once per process
(`main.py:55`). Everything else in the finding is correct and survives: the spawn start method, the
per-process re-import, five-turned-four independent rotation states over one path, the duplicated
WARNING/ERROR records and the multi-kilobyte tracebacks.

**Evidence** — Read from the running image: uvicorn `0.49.0`; the full text of
`uvicorn/supervisors/multiprocess.py` (`Multiprocess.run`, `init_processes`,
`keep_subprocess_alive`) showing no `config.load()` on the parent path;
`uvicorn/server.py`'s `Server.serve`, which does call `config.load()` and runs only in the child;
`src/mkobi/main.py:52-55` (`from mkobi.app import create_app` → `app = create_app()`);
`src/mkobi/app.py:217` (the single "Configuring CORS" call); `app.py:39` (`setup_logging`).
A correction of one line: `uvicorn/_subprocess.py:18` is `spawn = multiprocessing.get_context("spawn")`,
not `:19` as both this input and phase 07's report state.

**Consequence** — The finding survives and is understated rather than overstated: four writers against
one path is the same defect. But a reader who checks the arithmetic finds a mechanism the shipped code
does not produce, and concludes the measurement — and then the finding — was fabricated. That is a
wrong rejection caused by the report, which is worse than no finding, and it is the same failure mode
phase 07 recorded as VAL-07-006 for EXT-002's retry count. The derived ceiling becomes ~240 MB, not
~300 MB; on the same `app_data` volume that also holds `uploads/` and `tmp_uploads/`, so the band does
not move.

**Recommendation** — Replace "five" with "four" in the title, Observation and Consequence, replace the
×3 measurement with the source-level statement (four processes, one call site each), and re-derive the
ceiling as 4 × 6 × 10 MB. If the measurement is retained, state the observation that produced three
matches, because that observation is the only thing in the report that could indicate a second
`create_app()` path this validation did not find. Separately, fix `_subprocess.py:19` to `:18` in both
this report's lineage and phase 07's.

### VAL-10-004 — Appendix A's stated verification method cannot have produced its stated output

**Severity** — MEDIUM

**Zone** — The Claim Re-Derived from the Executing Path (asserted cause)

**Observation** — Appendix A gives its method as "re-derivation of the current state from the resolved
production compose (`docker compose -p auditverify --env-file docker/.env.production -f
docker/docker-compose.yml config --format json`)" and then reports resolved values for `ENV`,
`DATABASE__USER`, a credential boolean and three settings. That command **cannot resolve** at
`eeb9a5e`: the shipped `docker/.env.production` is a template in which every secret is commented out —
lines 10-14 (`DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD`, `JWT__SECRET_KEY`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD`), line 7 (`ENV`) and lines 19-25. Run as written, it exits 1 with
`error while interpolating services.app.environment.ADMIN_PASSWORD: required variable ADMIN_PASSWORD
is missing a value`, and produces no resolved output at all. The four closure verdicts are nonetheless
correct and were reproduced here by supplying non-secret placeholder values for the five required
variables through an additional `--env-file`; every conclusion in Appendix A survives that substitution
unchanged. The defect is in the report's evidence chain, not in its conclusions.

**Evidence** — `docker/.env.production` read in full: 44 lines, of which the only uncommented entries
are `CORS_ORIGINS` (`:28`), `LOGGING__LEVEL` (`:31`), `LOGGING__JSON_LOGGING` (`:32`),
`UPLOAD__MAX_FILE_SIZE_MB` (`:37`) and `RATE_LIMITER_FAIL_CLOSED` (`:44`). Three resolution runs:
`--env-file docker/.env.production` → exit 1, four interpolation errors;
`--env-file docker/.env.production` plus a placeholder file → exit 0 and the reported values;
no `--env-file` at all → exit 1, the same four errors (which is what CFG-001's own Evidence recorded
as "15 `required variable … is missing a value` errors" at its baseline). No secret value was read,
printed or recorded at any point in this validation; placeholder values were used throughout.

**Consequence** — A reader who follows Appendix A's method gets an error instead of the answer, and a
reader who does not try may conclude the production compose file resolves from its own shipped env
file. It does not, and the reader who believes it will believe CFG-001's documented invocation is
viable (VAL-10-005).

**Recommendation** — Record the method actually used: the four required variables must be supplied by
the operator's own secret store, and any resolution performed with placeholder values should say so in
the appendix. If the intent was to verify against the shipped file, the finding is that
`docker/.env.production` cannot start the stack as shipped — which is a real observation worth
carrying, and CFG-001's own second half.

### VAL-10-005 — Appendix A closes CFG-006 by citing a documented invocation that cannot start the stack, leaving CFG-001's second half open

**Severity** — MEDIUM

**Zone** — Cross-Phase Conflict, Ownership and Merge

**Observation** — CFG-006 is genuinely closed, and Appendix A's row for it says so twice: the two
names are supplied as `${VAR:-default}` on `app` and `rq-worker`, they resolve, and they are genuinely
read — this validation confirmed the second point empirically, with `UPLOAD__MAX_FILE_SIZE_MB=7`
resolving `max_file_size` to 7,340,032 bytes through the full `Settings` source chain, so the variable
is wired and not merely declared, and `RATE_LIMITER_FAIL_CLOSED=false` resolving to `False`. The
defect is the last sentence of the row: "Closed even if the env file is not supplied, because the
compose defaults alone are sufficient — the documented production command at `deployment.md:167`
passes no `--env-file` and still resolves both." `deployment.md:167` is
`docker compose -f docker/docker-compose.yml up -d`, and that command cannot start the stack: with no
`--env-file`, five `${VAR:?}` interpolations across `db`, `migrate`, `app` and `rq-worker` fail and
Compose exits 1 without creating anything. CFG-001 filed two claims — the interpolable tier, and that
the documented invocation "cannot start the stack at all" — and only the first is closed. The compose
file's own header (`docker-compose.yml:5`) was corrected by the same commit; the deployment document
was not, and `deployment.md` contains no `--env-file` reference anywhere (its only mention of the file
is `deployment.md:364`, which copies `/secure/backups/.env.production` to `.env` at the repository
root, a path Compose does not read for this invocation).

**Evidence** — Three resolution runs as in VAL-10-004: no `--env-file` → exit 1 with the four
`required variable … is missing a value` errors; with the shipped production file → exit 1, the same
errors; with placeholder values → exit 0 and `RATELIMIT=true MAXSIZE=100` on both `app` and
`rq-worker`. `deployment.md:163-174` (Quick Start) read in full; a search of the whole document for
`--env-file` returns nothing. `docker-compose.yml:5` supplies `--env-file docker/.env.production`,
and `docker/.env.production:4` documents the same form. Settings wiring confirmed by running the
application's own `get_config()` in a throwaway container. **A third instance arrived mid-validation:**
commit `c55550b` corrected `docs/10-deployment/security-checklist.md` — CFG-006's own verification
command — to `docker compose -p mkobi --env-file docker/.env.production -f docker/docker-compose.yml
config --format json`, and that command, run as written against the shipped file, **exits 1** with
`error while interpolating services.app.environment.ADMIN_PASSWORD: required variable ADMIN_PASSWORD
is missing a value`. The check is now correct in form and still cannot run.

**Consequence** — A reader closes both the configuration finding and the operational-claim finding on
the strength of one sentence, and then discovers at deploy time that none of the three documented
production invocations — `deployment.md:167`, `deployment.md:170` and the corrected
`security-checklist.md` check — starts the stack, because none of them is supplied with the five
required values and the only shipped file that claims to hold them is empty of them. The residual is
small in blast radius and large in confusion value: three documents give mutually inconsistent
invocations and the one every operator copies first is the one that fails.

**Recommendation** — Amend Appendix A's CFG-006 row to drop the `deployment.md:167` clause and keep
only the verified claim (both names reach `app` and `rq-worker`, with compose defaults, and both are
read). Record CFG-001 as **half-closed**: the tier is pinned, the documented invocations are still
broken, and closing that half belongs to phase 02's remediation or to the operational-claim owner
(OPS-015's class), not to phase 10. Whichever document is corrected, the corrected form must state
where the five required variables come from, because `docker/.env.production` does not contain them —
and the `security-checklist.md` check needs the same correction, since a verification command that
cannot execute is a control that decides nothing.

### VAL-10-006 — OPS-003's stated mechanism is false: the served bundle directory is git-ignored, not unignored

**Severity** — LOW

**Zone** — The Claim Re-Derived from the Executing Path (asserted cause)

**Observation** — OPS-003 states that the host directory "is neither tracked in git nor ignored",
cites `git ls-files frontend/dist` returning 0 in support, and explains the second half with "the
generic `dist/` rule at `.gitignore:15` is rooted, so it does not match `frontend/dist/`". Both halves
of that mechanism are wrong. The directory **is** ignored — `git check-ignore -v frontend/dist
frontend/dist/index.html` returns exit 0 with `frontend/.gitignore:11:dist` for both paths, and the
root `.gitignore:13`'s `dist/` would match at any depth regardless, because a gitignore pattern's
trailing slash marks a directory and does not anchor the pattern. The root rule is at `:13`, not `:15`.
The finding itself is unaffected and its consequence is stronger: an *ignored* directory is removed by
`git clean -xfd` and absent from any fresh checkout, so the two recovery moves an operator reaches for
both fail.

**Evidence** — `git check-ignore -v frontend/dist frontend/dist/index.html` → exit 0,
`frontend/.gitignore:11:dist` for both; `frontend/.gitignore:11` read; root `.gitignore:13` = `dist/`
within the "Distribution / packaging" block at `:9-15`; `git ls-files frontend/dist` → 0 files.

**Consequence** — No remediation consequence: the reader must delete one clause rather than act on
it. Recorded because a reader who checks it will find the mechanism the report offers to be wrong, and
may discount the finding that is correct — the same shape as VAL-10-003, at lower stakes because the
band and the recommendation both stand without the clause.

**Recommendation** — Delete the "nor ignored" clause and the parenthetical explaining it, and replace
the Evidence line with the `git check-ignore -v` output. Keep the rest of the block, which is correct.

## Distribution

The findings fall on the seam between `docker/docker-compose.yml` and everything it starts, not
inside any component. Of the sixteen, nine name the production compose file as one of their two
subjects and five more name `Makefile.ps1`, `docker/Dockerfile` or `docker/nginx/nginx.conf`; the
heaviest single carrier is `docker/docker-compose.yml`, implicated in OPS-001, OPS-002, OPS-003,
OPS-005 (through the artifact it fails to protect), OPS-009, OPS-011, OPS-013, OPS-014 and OPS-016 —
and the site of all four phase-02 remediations this validation re-derived. The second cluster is the
operational corpus: `deployment.md` is wrong or unusable in three places (OPS-015) and in a fourth,
its production invocation (VAL-10-005); `docker.md` is wrong about the queue (OPS-002) and `health-api.md`
understates the health surface (OPS-004). Two findings are properties of the running system rather
than of any file — the uvicorn respawn loop (OPS-011) and the Redis failure-mode divergence (OPS-012) —
and the two that this validation merged out (OPS-002, OPS-004) both turn out to be properties of
*other* phases' subjects that phase 10 restated rather than new ones.

## Cross-Finding Analysis

Two causes account for eleven of the sixteen, and this validation's two merges remove a third cause
the input believed it owned.

**The deployed artefact has no versioned identity.** No service declares an `image:` coordinate, so
the only artefact is a local `:latest` overwritten in place (OPS-016); the SPA nginx serves lives in a
host directory no build step populates and no image contains (OPS-003); the documented rollback names
a registry that has never been pushed to (OPS-015). The input groups these correctly and no merge is
owed between them — the three remediations are three distinct edits — but the group's consequence is
the one worth stating plainly: **neither half of the deployed system is revertible**, which is what
makes OPS-010 and OPS-005 unrecoverable in practice rather than merely unproven.

**The operational corpus describes the intended system rather than the running one.** The RQ worker is
documented as the production queue and is not (OPS-002, merged into TOPO-002); `deployment.md`
documents a profile-gated worker that is unconditional while `docker.md` says the opposite (OPS-015);
`docker.md` documents one rotating log file where the deployment runs four (OPS-008);
`health-api.md` publishes a two-component health surface for a three-dependency request path (OPS-004,
merged into EXT-001); and the control that decides what may land, `Invoke-Backup`, reports success
without reading what it produced (OPS-005). A reader who follows the docs is wrong about the queue,
the rollback, the logs, the health contract and the invocations.

The remaining five — OPS-006, OPS-007, OPS-010, OPS-011, OPS-012 — share no cause with each other or
with the two clusters. They are, respectively, the lost edge log, the absent metrics surface, the
incomplete artefact, the non-terminal startup state and the divergent store failure modes; the input is
right not to manufacture a pattern for them.

## Roadmap

Ordered by cause, as the input orders them, with two merges folded in. The input's sequencing survives
validation; what changes is that steps 3 and 4 are no longer this phase's alone to schedule.

1. **Give the artefact a revertible identity** (OPS-016, OPS-003, OPS-015). Set an `image:` coordinate
   and tag for every built service; move the SPA into the image so nginx consumes it from a stage, or
   add `fe-build` plus a preflight. *Before step 2:* a rollback needs an artefact to select.
   **Phase 10 owns this step alone.**
2. **Make the controls non-vacuous** (OPS-005, OPS-007, OPS-011, OPS-010). Add the exit-code and
   existence assertions to `backup` and `restore`, add `rehearse-restore`, add the `alembic_version` and
   stuck-processing fields to `/health/detailed`, add the globals artefact, and give the app lifespan a
   terminal exit. *Before step 3:* an operator must be able to tell a successful recovery from a failed
   one. **Two coordination points, not two extra edits: the `redis` health field belongs to EXT-001's
   single change (VAL-10-002), and OPS-001's Redis artefact must load before the database restore.**
3. **Decide the work-submission mechanism once** (OPS-002 → merged into TOPO-002). Route `enqueue_job`
   through RQ or delete `rq-worker`; correct `deployment.md`'s profile section against `docker.md`.
   **Phase 01 owns the decision**; phase 10 contributes only the documentation correction, which is
   already part of OPS-015's step 1.
4. **Close the store's failure domain and protect its contents** (OPS-001, OPS-012, OPS-004 → merged
   into EXT-001). Explicit timeouts, a declared failure mode per job, `delete_secure_cookie` ahead of the
   revocation writes, a Redis artefact in `backup`, and one `app.py:248-307` change adding a bounded
   `redis` component. **Phase 04 owns the revocation-read edit (AUTH-008), phase 07 owns the probe edit
   (EXT-001), phase 10 owns the artefact and the timeout defaults.**
5. **Draw the runtime boundary and shrink the credential set** (OPS-014, OPS-009, OPS-013). Extend
   `no-new-privileges` to `migrate` and `rq-worker`, add a `tools` service for the three static-analysis
   gates (not the alembic ones), and template `client_max_body_size`. Independently cheap.
6. **Restore the edge and worker log streams** (OPS-006, OPS-008). Point nginx at
   `/dev/stdout`/`/dev/stderr`; drop the production `LOGGING__LOG_FILE` so one console writer remains.

## Rollout Safety

The input's rollout analysis survives validation and is complete for its own findings; three
corrections belong with it. Steps 1 and 2 change observable behaviour as the input states — an `image:`
coordinate changes what `docker compose up` creates, and moving the SPA into the image makes host-side
edits to `frontend/dist` silently ignored. Because `frontend/dist` is **git-ignored** (VAL-10-006),
step 1's second option also has to remove the host directory from `.gitignore`'s blind spot before an
operator can see that it is stale; that is a repository change, not only a compose change.

Step 2 remains the only step that can destroy something, and the input's ordering (assertions first,
against a scratch database the target creates and drops) is right. One addition this validation
requires: `psql -f globals.sql` must run **after** `pg_restore --clean --if-exists` has finished, or the
restore's re-issued grants are dropped by the roles load that precedes them. And the Redis artefact must
load before the database restore, not after, or a restored cluster re-admits tokens minted against the
pre-restore data.

Step 3's rollout changes once the merge is applied: switching `enqueue_job` to RQ makes the in-process
loop dead code that must be removed rather than left as a fallback, and the dev overlay's
`rq-worker` (which runs the same `target: prod` image) has to change with it or the dev stack keeps
the arrangement the fix removes. That last point is in neither report.

## Appendices

### Appendix A — Independent re-derivation of the four phase-02 closure claims

Each claim was re-derived from the current tree, not from the input's verdict. Method: read the
committed state of `docker/docker-compose.yml` and `docker/.env.production`, then resolve the
production definition three times with `docker compose -p mkobi-val10 -f docker/docker-compose.yml … config
--format json` and extract only `ENV`, `DATABASE__USER`, a boolean comparing each service's resolved
`DATABASE__PASSWORD` against the superuser value, the presence of `DATABASE__ADMIN_PASSWORD`, and
`RATE_LIMITER_FAIL_CLOSED` / `UPLOAD__MAX_FILE_SIZE_MB` / `LOGGING__JSON_LOGGING` / `UPLOAD__TEMP_DIR`.
**No secret value was read, printed or recorded.** The five required variables were supplied as
non-secret placeholders through an additional `--env-file`, because the shipped production file cannot
resolve them (VAL-10-004).

| Claim | Commit | Verdict as filed | Verdict re-derived |
|---|---|---|---|
| **CFG-001** production tier label | `8505a62` | CLOSED | **CLOSED — mechanism independently proved.** `ENV` is the literal `production` in the `environment:` map of `migrate` (`:64`), `app` (`:103`) and `rq-worker` (`:194`). The decisive test the input asserted but did not run: with `--env-file docker/.env.production --env-file <file declaring `ENV=development`, `LOGGING__JSON_LOGGING=false`>`, all three services still resolve `ENV=production` while `LOGGING__JSON_LOGGING` flips to `false` on both — an `environment:` map literal beats an `--env-file` value, while an interpolated `${VAR:-default}` neighbour in the same map does not. `db` and `redis` carry no `ENV`; the dev overlay still sets `ENV: development` at `override:19,69,134`. |
| **CFG-004** superuser credential in `app` and `rq-worker` | `8505a62` | CLOSED for both | **CLOSED — and no other service holds it.** Resolved: `app DATABASE__USER=mkobi_app`, `rq-worker DATABASE__USER=mkobi_app`, `DATABASE__ADMIN_PASSWORD` **absent** from both, and the boolean "resolved `DATABASE__PASSWORD` equals the superuser value" is **False** for both. `migrate` retains the superuser credential *as its own primary credential* (`DATABASE__USER=postgres`, `DATABASE__PASSWORD` = the superuser value) — it does **not** carry `DATABASE__ADMIN_*` at all, so the
split is narrower than the input's phrasing implies and correctly so. `migrate` genuinely needs a
DDL-capable role: `alembic upgrade head` (`docker-compose.yml:60`) cannot run as `mkobi_app`, whose
grants are `CONNECT`, `USAGE ON SCHEMA`, `SELECT, INSERT, UPDATE, DELETE` and `USAGE ON SEQUENCES`
only (`docker/init-scripts/01-create-app-role.sh:23-42` — role at `:23-24`, grants at `:29-42`). No
residual on the runtime side either: the removed credential's only consumer,
`DatabaseStarter.recreate_test_database()`, is reached only when the tier is `test` or `recreate_test_db`
is set, and no compose file sets either, so nothing on the production path needs it. The residual to
record is in the other direction: `docker-compose.override.yml:75-76,139-140` still gives both `app`
and `rq-worker` `DATABASE__ADMIN_USER`/`DATABASE__ADMIN_PASSWORD` in the **dev** overlay — which is
what CFG-004's own recommendation said to do (the test path supplies its own), and which a
`docker compose -f … -f override` dev command therefore still does. |
| **CFG-005** `.dockerignore` misses the build context | `044e630` | CLOSED | **CLOSED — proved by a build-context probe, no image left behind.** `docker buildx build --no-cache --output=type=cacheonly -f <probe> .` with `COPY . /ctx` and an existence test per path: `EXCLUDED` for `backups`, `.env.docker`, `.ai/mcp/.env`, `.ai/audit`, `.ai`, `docker/.env.production`, `docker/.env.development`, `docker/.env.example`, `.env`, `.env.example`; `IN_CONTEXT` for `README.md`, `src/mkobi`, `alembic`, `frontend/package.json`, `uv.lock`. All four paths CFG-005 named are now excluded and `!README.md` still works. **One correction to the input's evidence wording:** the pre-remediation patterns "matched nothing in this repository" is not quite true — the root `.env` file exists on this host and the old pattern `.env` did match it. The patterns' real failure was the other three plus the depth coverage, which is what the change fixed. `backups/` still holds three `pg_dump -F c` artefacts on this host, so the exposure the finding described is real and is now excluded rather than absent. |
| **CFG-006** unsupplied deployment controls | `8505a62` | CLOSED, twice over | **CLOSED on the claim, overstated in the reasoning.** Resolved on `app` and `rq-worker`: `RATELIMIT=true`, `MAXSIZE=100`, and they resolve identically with **no** `--env-file` at all (only the five required placeholders), which is the stronger form of the input's claim. Both are genuinely read, which the input asserted for the rate limiter only: a throwaway container with `UPLOAD__MAX_FILE_SIZE_MB=7` and `RATE_LIMITER_FAIL_CLOSED=false` resolves `config.upload.max_file_size_mb = 7`, `Settings.max_file_size = 7340032` and `rate_limiter_fail_closed = False` through the full `Settings` source chain, so the env source (`config.py:735-741`, first in the tuple) outranks both the YAML value at `settings/app.yaml` and the field default. `migrate` supplies neither, correctly. **But** the row's closing clause — that the documented command at `deployment.md:167` "still resolves both" — is true of those two variables and false of the command: with no `--env-file` it exits 1 on five `${VAR:?}` interpolations. See VAL-10-005. |

### Appendix B — Drift, and the two candidates the input refuted by measurement

**Drift.** The input filed against `b23a9cb` and closed at `eeb9a5e`. **HEAD moved from `eeb9a5e` to
`c55550b` during this validation**, landing `14be95c`, `183056d` and `c55550b` — all phase-02
remediation tail work (`settings/app.yaml` and `tests/test_config.py`; the configuration reference; the
deployment, docker and run guides). One of them edits a document this report cites, so every anchor was
re-resolved at `c55550b` and re-checked individually: `docker.md:361-363`, the RQ-worker note OPS-002
rests on, is byte-identical; `docker.md:367-369`, the "only service gated by the `production` profile"
statement OPS-015's contradiction rests on, is byte-identical; `deployment.md` is untouched, so
OPS-015(a)-(c) and VAL-10-005 stand unchanged; `docs/05-health/health-api.md` and
`docs/10-deployment/deployment.md:304-320,326-338` are untouched, so OPS-004 and OPS-015(b)-(c) stand.
No verdict in this report changes. The one drift with a consequence is `c55550b`'s rewrite of
`docs/10-deployment/security-checklist.md`, which replaced CFG-006's non-functional
`config --services` check with a `config --format json` check that **cannot execute against the shipped
env file** — recorded in VAL-10-005, and the reason this report's baseline is `c55550b` rather than
`eeb9a5e`. The input's own Appendix B commit table is accurate for its window
(`8747be7` and `eeb9a5e` after the work began, `5f1d9ee` in between), and the two working-tree
modifications it recorded as uncommitted were subsequently committed as `14be95c`.

Three anchors in the input's own text do not resolve, all recorded in place above:
`OPS-003`'s `.gitignore:15` (the rule is at `:13`; `frontend/.gitignore:11` is the one that matches),
`OPS-008`'s `uvicorn/_subprocess.py:19` (the assignment is at `:18`), and `OPS-014`'s
`docker-compose.override.yml:149-150` (the comment is at `:153-154`). **The input did not repeat
phase 01's refuted `start_period` mechanism** anywhere, and that discipline is correct and worth
recording: the phase-01 validator established that `start_period` suppresses failure counting rather
than manufacturing a healthy verdict, and neither this report's subject nor its conclusions rest on it.

**The two refutations.** Both were re-tested.

- `setup_logging()` **does** run once per uvicorn worker child — confirmed, and the parent is *not* one
  of them, so the real count is four rather than the five the input filed. The refutation of the input's
  own first hypothesis stands; the multiplier does not (VAL-10-003).
- `deploy.resources.limits` **is** applied by this engine — confirmed independently of the input:
  `docker inspect mkobi-app-1` → `Memory=1073741824 NanoCpus=1000000000`, `mkobi-rq-worker-1` →
  `Memory=536870912`, on Docker 29.8.0 with Compose v5.5.1. A "declared limit the engine ignores"
  finding would have been false, and correctly was not filed. Phase 11's PERF-001 corroborates it from
  the other side: its 1,036.2 MB peak was measured against a 1,073,741,824-byte limit that was in force,
  which is what makes that finding's 101.2 % figure real rather than an artefact of an unenforced cap.
- `pg_restore` exits 1 with and without `--exit-on-error` — consistent with documented behaviour: the
  tool continues past recoverable errors and returns a non-zero status at the end, while the option stops
  at the first one. The input recorded this as methodology rather than as a finding, which is the right
  call: the defect in `Invoke-Restore` is the absent exit-code check, and the option would change where
  the tool stops, not whether it reports.

### Appendix C — The vacuous-control angle, applied to every control the input leans on

For each control: does it exist, what scope does it declare, what did it actually examine, and by what
path a verdict would have reached a decision.

| Control | Exists | Declared scope | Actually examined | Reaches a decision by |
|---|---|---|---|---|
| `app` healthcheck (`curl -f /health`) | yes, `Dockerfile:176-177`, `compose:146-151`; **disabled in dev** (`override:115-116`) | database reachability | one `SELECT 1`; Redis never | exit code of curl → container health state |
| `rq-worker` healthcheck | yes, `compose:221-230` | "the worker is alive" | `Redis(...).ping()` — **0 jobs in the container's entire log** | exit code → worker health state, while the queue is never written to |
| `nginx` healthcheck | yes, `compose:261-265`; never started here | an HTTP response from `/` | `wget --spider` against `try_files` | exit code → nginx health state |
| `migrate` as a boot gate | yes, `compose:95-97` | migrations completed before `app` | satisfied **once**, permanently; `restart: "no"` (`:86`) | `service_completed_successfully`, never re-evaluated |
| `Invoke-Backup` / `Invoke-Restore` | yes, `Makefile.ps1:279-306` | take a dump / restore it | `pg_dump`'s exit code only; the `cp` and `pg_restore` results are never read | **nothing** — `exit $LASTEXITCODE` carries the trailing `rm`'s zero |
| `Invoke-Check` | yes, `Makefile.ps1:241-249` | the aggregate gate | ruff → mypy → eslint → vitest; **no pytest** | short-circuits on the first non-zero; phase 09 owns this verdict |
| `docker/scripts/scan-images.ps1` | present | image scanning | — | nothing; wired to no schedule |

Every control the input's arguments lean on exists and was examined; the three that decide nothing
(backup/restore, the `rq-worker` probe, `migrate`'s one-shot gate) are already filed inside this report,
and the two the input correctly declined to file (the gate chain, the unwired scanner) are owned by
phases 09 and this report's OPS-016 respectively. No control here is green over an examined item count
of zero **without** a finding behind it, which is the property the angle exists to detect.

### Appendix D — The shared template as a controlled artefact, applied to this input

The template resolves and was not repaired from inside this run. Across the sixteen blocks and the
thirteen declared blocks of the audited phase:

| Mandated element | Verdict |
|---|---|
| Front matter `phase:` / `executed` / `executor` / `problems-only` / `findings` / `by-severity` | all present; `phase: 10-production-ops` is the phase that wrote it; counts verified against the bodies |
| Non-templated extensions (`baseline`, `baseline-dirty`, `baseline-final`) | benign; `baseline-dirty` is honest about the `.ai/` deletions that were present at filing and at validation |
| Per-finding fields | **16 of 16** blocks carry all six (`Severity`, `Zone`, `Observation`, `Evidence`, `Consequence`, `Recommendation`); none omitted, none renamed |
| `Zone` quoted verbatim from a block title | **16 of 16** verbatim against `10-audit-production-ops.md`; no paraphrase and no absent zone |
| Reserved empty-state string | not applicable — the phase produced findings, and the summary is not padded |
| Sections the template treats as required | Summary, Findings, Distribution, Cross-Finding Analysis, Roadmap, Rollout Safety, Appendices all present; Cross-Finding Analysis is substantive rather than the "every finding is independent" one-liner |

The one template-level defect this input carries is not in the template's shape but in its **evidence
chain**: Appendix A names a command that cannot produce its stated output (VAL-10-004). Everything the
template mandates about form is satisfied.

### Appendix E — Finding-ID namespace integrity, and the ruling

Re-derived from the working tree. Phase 10 declares `OPS-` at `10-audit-production-ops.md:190` and
minted `OPS-001` … `OPS-016` with no gap and no collision against any other prefix in the set. No
in-source marker exists: a search of `src/`, `tests/`, `docker/`, `frontend/src/` and `docs/` for
`OPS-0` returns nothing outside this audit set, so there is no in-source provenance to migrate and
nothing to retire. The compound form the template's front matter pairs with the prefix is
`phase: 10-production-ops` + `OPS-`, which the input uses correctly.

**The ruling.** The flat `VAL-` prefix is occupied — phase 01 and phase 02's validation reports carry
flat `VAL-` identifiers — and phases 03 through 09 each adopted a phase-qualified `VAL-NN-` variant.
This report follows that established precedent with `VAL-10-001` … `VAL-10-006`; the deviation from
the flat prefix the output contract specifies is recorded here and in the section preamble. No sibling
file in `.ai/audit/99-validation/` was created, edited, renumbered or deleted by this run.

### Appendix F — Seam check, contested claims, and which phase owns remediation

Sibling reports compared: phases 01, 03, 04, 05, 06, 07, 08, 09 (raw) and the **validated** reports for
01 through 09, plus phase 11's raw `PERF-001`. Nothing written into another phase's directory.

| Contested item | Rival claim | Owner | Disposition |
|---|---|---|---|
| OPS-002 vs TOPO-002 | TOPO-002 (MEDIUM, raw + validated, VAL-005) | phase 01 | **merge** — same root cause, anchors, evidence and remedy; the input filed no ruling, and the only distinction it drew was against TOPO-005, which is not the rival |
| OPS-002's queue-loss consequence vs TOPO-001 / TOPO-003 | TOPO-001 (HIGH), TOPO-003 (MEDIUM) | phase 01 | **merge of those elements** into the merged item; TOPO-001 already holds the stuck row at HIGH |
| OPS-004 vs EXT-001 | EXT-001 (HIGH, raw + validated; phase 07's validator named phase 10 co-owner) | phase 07 for the code, phase 10 for the consumers | **merge** of the probe-coverage mechanism; the consumer inventory is a cross-reference, not a second edit |
| OPS-004 / OPS-007 vs EXT-002 | EXT-002 (HIGH) | phase 07 | **not a merge** — blast radius and per-request cost are a different subject; its code element is already merged into AUTH-008 by VAL-07-004 |
| OPS-004's `app.py` edit vs phase 09's gate verdict | phase 09 owns entry-point remediation | phase 09 | **upheld as the input states it**: 09 owns whether the gates run, 10 owns whether a control exists in the deployed path. Distinct edits. |
| OPS-001's deactivation amplifier vs TXN-001 | TXN-001 (phase 03) | phase 03 | **cross-reference owed, not merged** — the input cited the defect as an amplifier without naming its filing; no remediation collision follows, because the input recommends no `admin.py` edit |
| OPS-012's revocation-read guard vs AUTH-008 | AUTH-008 (phase 04, merged in by VAL-07-004) | phase 04 | **merge upheld**: phase 04 owns that edit; phase 10 owns the `logout` ordering and the timeout defaults |
| OPS-003 vs OPS-015(b) | same report | phase 10 | **adjacency, correctly grouped**: one root cause (no versioned identity), three distinct edits. No merge owed. |
| OPS-007's "no signal" clauses vs OPS-001/002/010 | same report | phase 10 | **adjacency**: the specific silent conditions are those findings' consequences; the absent series is what remains |
| OPS-014 / OPS-011 vs PERF-001 (phase 11) | PERF-001 (CRITICAL, raw) | phase 11 for sizing and read-path cost; phase 01 for the worker model | **adjacency on all three touchpoints**: the 1 GiB limit is applied and PERF-001's peak is measured against it; the OOM restart is a production restart, owned by TOPO-008's class, not by OPS-011's lifespan-respawn loop; `--workers 4` duplication is TOPO-005's, sizing is 11's. Nothing merges. |

**Seam check.** No finding is filed outside the input's own declared scope paragraph, and the two
closest calls were tested rather than assumed. OPS-002 sits in block 5's zone verbatim ("a component
defined and health-checked but never started" — the worker *is* started, which is the finding, not a
seam); OPS-007's inventory of silent conditions touches measured latency only by naming it and defers
to 11 as its contract requires; OPS-014's resource-limit claim was checked against 11's carve-out and
filed as an *asymmetry*, not a sizing verdict, which is exactly the line the contract draws. The two
deferrals the input makes — the uncommitted deactivation write (TXN-001) and the gate-entry-point
verdict (phase 09) — are correct scoping, not seams. The one discipline failure is the missing merge
rulings (VAL-10-001, VAL-10-002), which the contract classifies as a defect in the audit rather than a
seam, and which is recorded as such.

### Appendix G — Coverage ledger and what was not settled

Blocks of the validated phase examined, and the item count each reached:

| Block | Items examined | Outcome |
|---|---|---|
| 1. Effective runtime posture per service | 6 services merged; 3 restriction classes; 1 resource limit class | 1 finding (OPS-014); the "engine ignores declared limits" candidate refuted |
| 2. Artifact content per input class | 4 input classes, 8 unpinned inputs, 1 double-built target | 1 finding (OPS-016) |
| 3. Deployed-surface controls | 7 controls inventoried (Appendix C) | OPS-005, OPS-009, OPS-016; phase 09 owns the gate verdict |
| 4. What can prevent a change from landing | 4 backend gates + 1 aggregate entry point | OPS-009 |
| 5. Service coverage and provenance | 5 base services + 1 profile-gated; 2 artefact sources for 1 SPA | OPS-002 (merged), OPS-003 |
| 6. Restart and one-shot steps | 1 lifespan path, 1 supervisor loop, 1 completion gate | OPS-011 |
| 7. Health contract | 2 endpoints, 4 documented integrations, 3 deployment consumers | OPS-004 (merged) |
| 8. Shared transient store | 5 key classes, 5 failure modes | OPS-001, OPS-012 |
| 9. Fronting tier | 2 cross-tier limits, 1 log-stream pair | OPS-006, OPS-013 |
| 10. Backup consistency and durability | 1 artefact, 3 options, 1 uncovered volume | OPS-001, OPS-010 |
| 11. Evidence a restore works | 1 entry point, 2 unchecked steps, 0 rehearsal paths | OPS-005 |
| 12. Signals produced and consumed | 2 probes, 0 series, 3 log paths | OPS-006, OPS-007, OPS-008 |
| 13. Operational claims as testable artefacts | 3 documented procedures, 8 claim lines | OPS-015 |

Claims left unsettled, with reasons. (1) **The four "Application startup failed" occurrences in a
70-second window** (OPS-011's runtime evidence) was not re-measured: re-inducing it means running a
throwaway container against an unreachable database on a daemon other agents are using. The static path
is unconditional and was re-read from the running image, so the finding does not rest on the count.
(2) **`docker compose cp` failing with exit 1** (OPS-005's failure premise) was not re-induced, for the
same reason plus the `backups/` write; the script logic is dispositive without it. (3) **Phase 07's
Redis-pause measurement** is cited and not re-measured — the outage is phase 07's artefact and this
validation declined to take the shared stack's authenticated path down. (4) **The `prod` image's
behaviour at `--workers 4`** was established on the `dev` image plus source reading; no `prod` build was
run, for the same daemon reason the input cites. (5) **Whether the `nginx` healthcheck would fail against
an absent bundle** (OPS-003's consequence) is stated as a consequence of the configuration, not as an
observation, because `nginx` is profile-gated and starting it would publish port 80 — the input states
this and the statement holds. (6) **The attribution in the input's Appendix D** — that the dev stack was
destroyed mid-audit "by another actor" — cannot be settled from the available record: phase 11's own
report states its run OOM-killed and restarted `mkobi-app-1` at 17:05:31 UTC, which is a different
container from the `mkobi-db-1` disappearance the input describes, and no actor recorded either. Nothing
in this report's findings depends on it. (7) **The 30-second interval versus 10-second timeout on the
`app` healthcheck** was read as configuration and not exercised; the phase-01 validator has already
settled that `start_period` does not manufacture a healthy verdict, and this report does not rely on
either value.