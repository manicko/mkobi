---
id: mkobi-docker-taskrunner-remediation-execution
domain: plans
tags:
  - docker
  - compose
  - tooling
  - task-runner
  - git
  - documentation
related:
  - mkobi-docker-taskrunner-remediation
  - docker-guide
  - deployment
  - run-guide
---

# Execution plan — mkobi Docker + Task-Runner Remediation

## Purpose

Turn the remediation plan `.ai/plans/mkobi-docker-taskrunner-remediation.md` into a
dependency-safe sequence of small, independently committable execution blocks. The plan's
code is already written and statically verified; this document governs the work that
genuinely remains — **one unimplemented requirement, two verification gates, eleven commits,
and three unresolved decisions.**

---

## 1. Situation summary (from `{code_context}`)

The step-1 Auditor established that the source plan is **~96 % implemented**.

| Finding | State |
|---|---|
| Plan Tasks 1–8 (Parts A/B/C) | Landed and verified in the working tree |
| Plan §7.6.1 / §7.6.2 / §7.6.3 | Landed and verified |
| §8 Definition of Done | 25 of 26 boxes satisfied by code; **all 26 still unticked** |
| §8 "End-to-end" block (5 items) | **Never executed** — no `mkobi` / `mkobi-test` containers exist |
| Git | **Nothing committed.** `HEAD` = `2019ddf` (2026-06-18, branch `feat/react`); `Makefile.ps1` is untracked |

Re-verified independently during planning:

- Only two Compose volumes exist: `mkobi-test_test_postgres_data`, `mkobi-test_test_redis_data`.
  No `mkobi_*` dev volume, no `docker_*` legacy volume, no `mkobi` container.
- `mko-bazuna-*` containers are **live** (`mko-bazuna-dev-web-1` holds host `8000`,
  `mko-bazuna-test-db-1` holds `5433`) and are out of scope.
- `Invoke-Up` (`Makefile.ps1`) is `rm -sf migrate` + `up -d --wait --wait-timeout $UpTimeout`
  with **no failure message** — the single unimplemented §8 requirement (D7).
- `Invoke-TestSelect` runs `run --rm --no-deps test-app pytest @Rest` with **no `up -d --wait`**
  prerequisite, unlike `Invoke-Test` / `Invoke-TestAll` (D11).
- All 23 diff hunks across the three Compose files, both `tests/conftest.py` hunks, and the
  single `.env.example` hunk are **plan-caused** — no unrelated edits are mixed in.
- `.gitignore` has exactly one hunk (the `$null` / `backups/` block). Nothing else.
- `.ai/context/commands.md` has **exactly two hunks, both plan-caused** (`5433` → `5434`).
  The Auditor classified it as pre-existing/unrelated; **that classification is wrong** and
  the file belongs in the plan's commit set.
- `.ai/tasks/templates/task_template.yaml` **exists on disk and is tracked and clean.**
  The workflow brief stated it was deleted; it was not. See §6, Open Decision O6.

**The single most important structural fact:** the plan's own risk register (§7.1) says the
`up --wait` risk must be *"resolved empirically before committing the script"*. Committing
`Makefile.ps1` before proving `--wait` works would invert the plan's stated mitigation.
Execution Block 2 exists specifically to satisfy that ordering constraint.

---

## 2. Scope boundaries

### 2.1 In scope

- Committing the already-landed Part A / Part B / Part C work as discrete, path-explicit commits.
- Implementing the one missing §8 requirement (D7 — `up` hard-fail message).
- Running the two deferred end-to-end verification gates (D2), in the plan's own order.
- Correcting `docs/11-guides/docker.md` profile / service-set drift (D4), queued by plan §7.4.
- Resolving the `docs/SPEC.md` append-only integrity conflict (D5) — as a **decision**, not a
  unilateral edit.
- Committing the plan of record and this execution plan.

### 2.2 Out of scope — explicitly NOT to be implemented

Everything in plan §7.4 "Deferred — explicitly out of scope" stays deferred:

README translation to English · `pyproject.toml` cleanup (broken `mko-get-mediascope` console
script, unused `testcontainers`, unused `slow`/`fast` markers, inert `--cov-fail-under`) ·
`.dockerignore` secret exclusion · nginx `/tmp` tmpfs · dedicated migration role · Vite proxy
target switch · deleting the redundant `test-migrate` service · reaping `mko-bazuna-*` ·
`docker/.env.production` · nginx `frontend/dist` design change.

**Cross-check:** no block in this plan changes `pyproject.toml`, `alembic/`,
`docker/docker-compose.test.yml`'s `test-migrate` service, `frontend/vite.config.ts`, or
`.dockerignore`. None of the deferred items is broken by any block here.

### 2.3 Hard prohibitions for every block

1. **Never `git add -A`, never `git add .`, never `git add -u`.** Stage by explicit path only.
   The working tree carries ~19 unrelated `.ai/` deletions, ~20 modified and ~35 untracked
   `.kilo/` files. All must remain unstaged and unreverted.
2. **Never touch the `mko-bazuna-*` stack.** No `down`, no `down -v`, no `system prune`,
   no `docker system prune --volumes`. Host ports `8000` and `5433` are held by it.
3. **Never re-run plan §3.3** (the one-time volume deletion). It is complete and must not repeat.
4. **Never run `nuke` or `fullclean`** as part of verification.
5. **Do not modify the source plan file** in any block except Block 11, and only with the
   explicit authorization named in Open Decision O1.
6. Comments, commit messages, and documentation are **English only**.

---

## 3. Execution blocks

### Block 1 — Commit repository hygiene (Task 8)

**Goal.** Commit the `.gitignore` additions and the two already-staged root-artifact deletions
as a standalone, zero-risk commit, establishing a clean tree baseline for every later block.

**Files / semantic units touched**

- `.gitignore` — trailing block `# PowerShell mis-quoted redirection artifacts and scratch files`
- Root artifacts `$null` and `test_write_permission.md` — already removed from disk and already
  staged as deletions (`D ` in `git status --porcelain`); nothing to do but commit them.

**Dependencies.** None. This is the first block.

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | None | Content already exists and is verified; no new code |
| Rollout | None | No runtime effect |
| Regression | None | `.gitignore` adds two ignore rules; the deletions remove two stray files never referenced by code |
| Compatibility | None | The `$null` file is a captured Docker CLI stderr artifact, not a source file |

**Required agents.** None. Pure `git add` + `git commit` against a pre-verified working tree.

**Acceptance criteria**

1. `git status --porcelain` shows `D  $null` and `D  test_write_permission.md` (staged, capital `D`
   in the first column) immediately before committing.
2. `Test-Path '$null'` and `Test-Path 'test_write_permission.md'` both return `False`.
3. `git check-ignore -v '$null' backups` resolves both patterns to rules in `.gitignore`.
4. After the commit, `git status --porcelain` shows **no** new deletions under `.ai/` or `.kilo/`
   beyond the pre-existing ones.

**Commit plan**

```powershell
git add -- .gitignore
git status --porcelain          # MANDATORY preview: confirm only the two staged deletions
                                # and .gitignore are in the index
git commit -m "chore(repo): ignore PowerShell redirection artifacts and the backups directory"
```

Explicitly **not** staged: any path under `.ai/` or `.kilo/` other than the one named in Block 6.

**Stop conditions / rollback.** Stop if the pre-commit `git status` preview shows any `.ai/`
or `.kilo/` path in the index. Rollback: `git reset --soft HEAD~1` (nothing was deleted from
disk; the files are gone from disk but recoverable from the index or the previous commit).

---

### Block 2 — E2E gate A: dev stack start and `--wait` proof

**Goal.** Empirically prove that `.\Makefile.ps1 up` reaches a healthy dev stack and that
`docker compose up -d --wait` treats the exited-0 `migrate` one-shot as satisfied — closing
plan §7.1's highest-likelihood open risk **before** the runner and Compose files are committed.
No commit is produced by this block.

**Files / semantic units touched**

- `Makefile.ps1` — executed only (`Invoke-Up`, `Invoke-Ps`, `Invoke-Logs`, `Invoke-Down`)
- `src/mkobi/**` — read only; **no file is modified**
- Docker host state: creates `mkobi_postgres_data`, `mkobi_redis_data`,
  `mkobi_frontend_vite_cache`; creates the `mkobi` network and its containers

**Dependencies.** Block 1 (clean tree baseline).

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | Medium | First ever start of the `mkobi` dev stack; the `--wait` behaviour is rated **Medium** likelihood in plan §7.1 |
| Rollout | High | Mutates the Docker host: builds the `dev` image (slow on first run), publishes host `8010`, `5432`, `5173` |
| Regression | Low | No running `mkobi` stack to regress. Host ports `8000`/`5433` are untouched, so `mko-bazuna-*` is unaffected |
| Compatibility | Low | First start of a dev DB that does not yet exist |

**Data impact.** **None destroyed.** No `mkobi_postgres_data` volume exists at execution time,
so the dev database `bidb` starts empty. This is confirmed at execution time by
`docker volume ls --filter label=com.docker.compose.project=mkobi` returning nothing.
If that filter *does* return a volume, **STOP** — a populated dev database exists and the
operator must decide before continuing.

**Required agents**

- **Planner — light.** Pre-write the exact step sequence, the per-step expected output, and the
  stop conditions below into the task description so the Implementor does not improvise.
- **Validator — required.** This gate unblocks three commits (Blocks 3, 4, 5). The Validator
  confirms `--wait` genuinely returned 0 and that `migrate` exited 0, rather than the stack
  merely appearing to be up.

No Auditor (nothing to investigate — behaviour is already specified). No Researcher (the
fallback for a failure is already documented in plan §6 Phase 3 and is a user decision, not a
research question).

**Acceptance criteria**

1. `docker volume ls --filter label=com.docker.compose.project=mkobi` is empty **before** starting.
2. `.\Makefile.ps1 up` exits with code `0`.
3. `.\Makefile.ps1 ps` shows `db`, `redis`, `app`, `rq-worker`, `frontend` running and `migrate`
   exited with code `0`. **`nginx` must be absent.**
4. `Invoke-WebRequest -UseBasicParsing http://localhost:8010/health` returns `200`.
5. `.\Makefile.ps1 logs app` shows a successful application startup and **no** CORS `ValueError`.
6. `mko-bazuna-*` containers are still running and unchanged (`docker ps` comparison).
7. `.\Makefile.ps1 down` exits 0 and leaves no `mkobi` containers or networks behind.

**Commit plan.** None — this block produces no commit. Any file it accidentally modifies
(notably under `src/`) must be reverted before Block 3.

**Stop conditions**

- **STOP-1** — `up` reports `container ... unhealthy`, `dependency failed to start`, or a
  `--wait` timeout. Then run `.\Makefile.ps1 ps` and `.\Makefile.ps1 logs db` to capture
  diagnostics, run `.\Makefile.ps1 down`, and escalate. **Do not** apply the plan §6 Phase 3
  fallback silently — see Open Decision O2.
- **STOP-2** — the failure names `migrate`. This is the specific unresolved case in plan §7.1.
  Escalate to Open Decision O2; do not hand-roll a polling loop.
- **STOP-3** — any `mkobi_postgres_data` volume already exists at step 1. Escalate.
- **STOP-4** — any host port bind fails. Check whether `mko-bazuna-*` has changed; do not stop
  that stack.
- **STOP-5** — any file under `src/` or `docker/` shows as modified after the run beyond what
  Block 1 already committed. Investigate before proceeding.

**Rollback.** `.\Makefile.ps1 down` (non-destructive; keeps volumes). If a later block needs a
truly clean dev stack, `.\Makefile.ps1 clean` removes both projects' containers and networks and
**keeps volumes**. Do **not** use `fullclean` or `nuke`.

---

### Block 3 — Commit Part A: Compose topology, hermeticity, hot reload

**Goal.** Commit the three Compose files as landed — project-name isolation, un-gated
`rq-worker`, safe `CORS_ORIGINS` default, hermetic test credentials, `WATCHFILES_*` polling,
production `REDIS__HOST`, and env-overridable host ports — as one coherent commit.

**Files / semantic units touched**

- `docker/docker-compose.yml` — top-level `name: mkobi`; `services.app.environment.CORS_ORIGINS`
  uses `${CORS_ORIGINS:-[...]}` with an explanatory comment; `services.app.environment` gains
  `REDIS__HOST: redis` and `REDIS__PORT: "6379"`; the `profiles: [production]` block under
  `services.rq-worker` is deleted; `services.nginx.profiles` is **retained**
- `docker/docker-compose.override.yml` — `services.app.environment` gains
  `WATCHFILES_FORCE_POLLING` and `WATCHFILES_POLL_DELAY_MS`; `services.app.ports` becomes
  `${APP_HOST_PORT:-8010}:8000`; the `profiles: []` line under `services.rq-worker` is deleted;
  `services.frontend` **retains** `CHOKIDAR_USEPOLLING` / `WATCHPACK_POLLING`; the file
  deliberately declares **no** top-level `name:`
- `docker/docker-compose.test.yml` — top-level `name: mkobi-test`; all four `container_name:`
  keys deleted; all twelve credential values replaced by hard-coded literals; the only remaining
  interpolations are the three host-port expressions `TEST_DB_HOST_PORT`, `TEST_REDIS_HOST_PORT`,
  `TEST_APP_HOST_PORT`

**Dependencies.** Block 2 (must have passed — proves this exact Compose content starts a healthy
stack). Block 1.

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | None | Already written; all 23 hunks verified plan-caused during planning |
| Rollout | High (historical) | The `name:` change orphans the six `docker_*` volumes — **already done and approved** per plan §3.3 / §7.6.3. Committing makes it permanent in history |
| Regression | Low | All six services verified healthy by Block 2. `mko-bazuna-*` volumes are labelled under a different project and are unreachable by these files |
| Compatibility | Medium | Container names change from `docker-*` to `mkobi-*` / `mkobi-test-*`; any external muscle memory, bookmark, or CI reference to the old names breaks. No such reference exists in the repo (verified) |

**Required agents**

- **Validator — required.** This is the foundational commit: Blocks 4–11 all assume it. The
  Validator independently re-runs the plan §6 Phase 1 static checks (V1–V5) against the
  **committed** tree and confirms the credential-leak regression still returns zero matches.
- **Auditor — light (single hunk-attribution pass only).** Re-confirm with
  `git diff --cached --stat` that the index contains only the three Compose files and that the
  hunk count is 23. This was pre-verified during planning; the Implementor repeats it as a
  cheap guard against a concurrent edit.

No Researcher (no viable-alternatives question — the alternatives were already rejected and
recorded in plan §7.3). No Planner (no design work remains).

**Acceptance criteria**

1. `git diff --cached --name-only` lists exactly the three Compose files and nothing else.
2. `docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config | Select-String '^name:'` prints `name: mkobi`.
3. The same dev pair's `config --services` returns `db`, `migrate`, `app`, `redis`, `rq-worker`,
   `frontend`, and **no** `nginx`.
4. `docker compose -f docker/docker-compose.yml config --services` returns the five base services
   with **no** `nginx`; adding `--profile production` adds **exactly** `nginx`.
5. `Select-String 'container_name' docker/docker-compose.test.yml` returns nothing.
6. Credential-leak regression: with `DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD` and
   `JWT__SECRET_KEY` exported as `LEAKED_SHOULD_NOT_APPEAR`, the resolved test config contains
   **zero** matches; `POSTGRES_PASSWORD: test_password` and `MKOBI_APP_PASSWORD: test_app_password`
   remain literals. Unset the variables afterwards.
7. The dev `app` config shows `WATCHFILES_FORCE_POLLING: "true"`, `WATCHFILES_POLL_DELAY_MS: "400"`,
   and a command containing `--reload` and `--reload-exclude /app/tests/`.
8. `docker/docker-compose.override.yml` contains no top-level `name:` key.
9. After committing, `git status --porcelain -- docker/` is empty.

**Commit plan**

```powershell
git add -- docker/docker-compose.yml docker/docker-compose.override.yml docker/docker-compose.test.yml
git commit -m "fix(docker): isolate compose projects, un-gate rq-worker, hermeticise the test stack"
```

**Stop conditions / rollback.** Stop if the `git diff --cached --name-only` preview shows any
path outside `docker/`. Rollback: `git revert --no-edit HEAD` (preferred — history stays honest)
or `git reset --hard HEAD~1` only if nothing downstream depends on it (Blocks 4–11 do).

---

### Block 4 — Commit the test-harness port alignment

**Goal.** Commit the native-pytest side of the host-port change so `tests/conftest.py` and
`.env.example` match the test Compose file committed in Block 3.

**Files / semantic units touched**

- `tests/conftest.py` — the two `os.environ.setdefault("DATABASE__PORT", "5433")` defaults
  (one at module import, one inside `pytest_load_initial_conftests`) become `5434`
- `.env.example` — new commented block declaring `APP_HOST_PORT`, `TEST_DB_HOST_PORT`,
  `TEST_REDIS_HOST_PORT`, `TEST_APP_HOST_PORT` with their defaults

**Dependencies.** Block 3 (must land first so the two sides of the port contract are atomic).

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | None | Two one-line default changes plus a documentation block |
| Rollout | None | `setdefault` means an explicit env var still wins; inside Docker the Compose value (`5432`) still takes precedence |
| Regression | Medium | A wrong default here breaks **native** (host-side) pytest, which the Docker path would mask. Block 6 Gate B is the real check |
| Compatibility | Low | Only affects developers who run pytest on the host without an explicit `DATABASE__PORT` |

**Required agents.** None. The change is two literals and a comment block; the audit already
verified both hunks verbatim.

**Acceptance criteria**

1. `git diff --cached --name-only` lists exactly `tests/conftest.py` and `.env.example`.
2. `tests/conftest.py` contains no remaining `5433`; `.env.example` declares all four port
   variables with the values `8010`, `5434`, `6381`, `8001`.
3. `uv run ruff check tests/conftest.py` passes.
4. No other file is staged.

**Commit plan**

```powershell
git add -- tests/conftest.py .env.example
git commit -m "test: align native pytest defaults with the configurable test host ports"
```

**Stop conditions / rollback.** Stop if `ruff` reports an error, or if the index preview shows
extra paths. Rollback: `git revert --no-edit HEAD`.

---

### Block 5 — Commit the task runner as landed

**Goal.** Commit `Makefile.ps1` in its current, statically verified state — establishing the
canonical developer entry point in version control.

**Files / semantic units touched**

- `Makefile.ps1` (new file, 428 lines) — `Show-Help`; the `$DevCompose` / `$TestCompose` splat
  arrays; and 43 `Invoke-*` functions plus the `default` fallback in the dispatch table.
  Notable semantic units: `Invoke-Up` (`rm -sf migrate` then `up -d --wait --wait-timeout
  $UpTimeout`), `Invoke-Test` / `Invoke-TestAll` / `Invoke-TestFresh` / `Invoke-TestSelect`
  / `Invoke-TestShell`, `Invoke-Backup` / `Invoke-Restore` (both `docker compose cp`-based),
  `Invoke-FullClean` / `Invoke-Nuke` (both prompt-gated, neither using
  `docker system prune --volumes`).

**Dependencies.** Block 2 (proved `--wait` works — the plan's §7.1 mitigation).
Blocks 3 and 4 (the runner's service names and project names come from those files).

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | None | 0 parse errors; `help` and `doctor` exit 0; `ps` and `test-ps` exit 0; satisfies plan constraints 2, 3, 4, 5, 7, 8 |
| Rollout | Low | Adopting the script changes how every developer invokes Docker. Commands are *more* explicit than before (`-p` on every invocation, explicit `-f`), so nothing gets less discoverable |
| Regression | Low | The old file was already non-functional for this repo (wrong service names, `manage.py`, `locust`, `basedpyright`) |
| Compatibility | Low | Container-name change is inherited from Block 3, not introduced here |

**Known defect carried by this commit.** §8 requires that `up` *"hard-fails with a clear message
when `--wait` returns non-zero"*. `Invoke-Up` propagates `$LASTEXITCODE` silently. This commit
is a **faithful snapshot of the landed script**; the missing behaviour is added separately and
reviewably in Block 6. Do not fix it here.

**Required agents**

- **Validator — required.** Largest single artifact in the change set (428 lines, 44 dispatch
  entries) and the file every developer will use. Independent re-check of plan §8 Part B plus
  plan §6 Phase 1 static checks.
- **Auditor — light.** Confirm the file is genuinely untracked and that adding it does not
  collide with a `.gitignore` rule (`$null` and `backups/` must not match it).

No Researcher (the target table and the rejected options are already fixed by plan §5 and §7.3).
No Planner.

**Acceptance criteria**

1. `git diff --cached --name-only` lists exactly `Makefile.ps1`.
2. The script parses with no syntax errors and `.\Makefile.ps1 help` exits 0.
3. `Select-String 'COMPOSE_PROJECT_NAME|--project-directory|manage\.py|locust|basedpyright|mko-bazuna|PYTEST_OPTS|PYTEST_SKIP_MARKERS' Makefile.ps1` returns nothing.
4. Exactly one `exit $LASTEXITCODE` exists and it is the final line.
5. The dispatch table contains all 44 targets from plan §5 and no foreign target.
6. `.\Makefile.ps1 help` output names every target in plan §5 and none that does not exist —
   this closes the fifth §8 End-to-end box at zero cost.
7. No `$env:` assignment and no `--%` token anywhere in the file.

**Commit plan**

```powershell
git add -- Makefile.ps1
git commit -m "build(tooling): add the PowerShell task runner over docker compose"
```

**Stop conditions / rollback.** Stop if `.gitignore` causes the add to be a no-op, or if the
index preview shows extra paths. Rollback: `git revert --no-edit HEAD` followed by
`Remove-Item -LiteralPath Makefile.ps1` if the file must leave the tree too.

---

### Block 6 — E2E gate B, step 1: implement the `up` hard-fail message (D7)

**Goal.** Satisfy the one unimplemented §8 requirement: make `up` emit a clear, actionable
message when `docker compose up --wait` returns non-zero, without violating plan constraint 5
(exactly one `exit $LASTEXITCODE`, on the final line).

**Files / semantic units touched**

- `Makefile.ps1` — body of the function `Invoke-Up`

**Dependencies.** Block 5 (the file must be tracked before it is modified, so the fix is a
reviewable delta rather than an unreviewable blob).

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | Low | One function, three lines, no new dependencies |
| Rollout | Low | Adds output on a path that currently fails silently. The non-zero exit code is unchanged |
| Regression | Medium | **This is the real risk.** A naive fix (`Write-Error` + `exit 1`) would introduce a second `exit`, breaking plan constraint 5 and the §8 "exactly one `exit $LASTEXITCODE`" box. Guard against it explicitly |
| Compatibility | Low | Purely additive output |

**Implementation alternatives — the Implementor must pick one, Validator confirms**

| # | Shape | Trade-off |
|---|---|---|
| A | `Write-Warning`/`Write-Error` after the `up` call when `$LASTEXITCODE -ne 0`, then return; the existing final `exit $LASTEXITCODE` propagates | **Compliant with constraint 5 by construction.** Only downside: `Write-Error` writes to the error stream while the script's own exit is the real signal |
| B | Capture the code into a local, emit a multi-line hint block (which services to inspect, that `--wait-timeout` is `$UpTimeout`, that plan §6 Phase 3 has a fallback requiring approval), then let `$LASTEXITCODE` propagate | Most helpful message; still compliant. More lines, more text to keep current |
| C | A small `Write-UpFailure` helper function called by `Invoke-Up` | Cleaner if other `Invoke-*` functions later need the same treatment. Mild over-engineering for a single call site — plan rule 5 (avoid over-engineering) argues against it unless applied to `Invoke-TestUp` and `Invoke-TestReset` too |

**Recommendation:** shape **B**, restricted to `Invoke-Up`. Shape A is the minimum viable
option if the Implementor wants the smallest possible diff. Do **not** choose C unless the same
helper is applied consistently to the other two `--wait` call sites.

**Required agents**

- **Validator — required.** The single-`exit`-path constraint is a hard §8 acceptance criterion
  and a silent regression here would be easy to miss. The Validator re-runs acceptance
  criterion 3 below after the change.
- **Planner — light.** Choose among shapes A/B/C and write the exact message text (English,
  actionable, naming `$UpTimeout` and the diagnostic targets `\Makefile.ps1 ps` and
  `\Makefile.ps1 logs <service>`).

No Auditor. No Researcher — the options are enumerated above; there is no external
best-practice question to settle.

**Acceptance criteria**

1. `Invoke-Up` emits a clear English message naming the failure (a `--wait` timeout or unhealthy
   dependency) and pointing at `\Makefile.ps1 ps` and `\Makefile.ps1 logs <service>` for diagnosis.
2. `Select-String 'exit ' Makefile.ps1` still matches **exactly one** line, and that line is the
   final line of the file. The script still exits with the same non-zero code as `docker compose`.
3. On success, the extra message is **not** printed.
4. `.\Makefile.ps1 help` still exits 0 and the script still parses with no syntax errors.
5. The message text is not baked from a variable that can be empty (guard `$UpTimeout` usage).

**Commit plan**

```powershell
git add -- Makefile.ps1
git commit -m "fix(tooling): report a clear failure when the dev stack never becomes healthy"
```

**Stop conditions / rollback.** Stop immediately if acceptance criterion 2 fails — a second
`exit` has been introduced. Rollback: `git revert --no-edit HEAD`, which restores the exact
Block-5 state.

---

### Block 7 — E2E gate B, steps 2–5: hot reload, test suite, backup round-trip

**Goal.** Close the four remaining §8 End-to-end boxes that have never been executed
(hot reload, green test suite, backup/restore round-trip, and — already covered by Block 5
criterion 6 — `help` output). No commit is produced unless a defect is found and fixed as a
follow-up.

**Files / semantic units touched**

- `Makefile.ps1` — executed only (`Invoke-DevWatch` / `Invoke-Up` + `Invoke-Logs`,
  `Invoke-TestUp` / `Invoke-Test`, `Invoke-Backup` / `Invoke-Restore`, `Invoke-Lint`,
  `Invoke-Typecheck`)
- `src/mkobi/main.py` — **touched only for the hot-reload probe**, and reverted within the step
- `backups/` — receives one `.dump` (already git-ignored by Block 1)

**Dependencies.** Blocks 2, 3, 4, 5, 6.

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | Low | No code change intended |
| Rollout | High | Builds the `test` image, runs the full pytest suite, and executes `pg_dump` / `pg_restore` |
| Regression | Low | Test database is disposable and recreated by `tests/conftest.py` on every run |
| Compatibility | Low | Dev host port `8010` is free; `5433`/`8000` (held by `mko-bazuna-*`) are untouched |

**Data impact — step by step, explicit**

| Step | Destroys data? | Detail |
|---|---|---|
| Hot-reload probe | **No (revertible)** | Adds a comment to `src/mkobi/main.py`, then reverts it. If the machine is interrupted mid-step, `src/mkobi/main.py` is left dirty — this is the one step that can corrupt the working tree |
| `.\Makefile.ps1 test` | **No** | The test database is recreated and migrated by the session-scoped `setup_test_database` fixture. `mkobi-test_test_postgres_data` is repopulated automatically |
| `.\Makefile.ps1 backup` | **No** | Read-only `pg_dump`, written to `backups/` |
| `.\Makefile.ps1 restore` | **CONDITIONAL — read this** | `Invoke-Restore` runs `pg_restore --clean --if-exists` against the dev database `bidb`. **Safe only if `bidb` is empty**, which is true on a first-ever dev start (Block 2 created a fresh volume). If `mkobi_postgres_data` already holds real dashboards, users, or `aggregated_data`, this step **destroys them** and must be skipped or explicitly approved |

**Required agents**

- **Validator — required.** Four §8 boxes, one conditionally destructive step, and a working-tree
  mutation. Independent sign-off that each step's evidence is real (non-zero dump size, actual
  reload line, actual test counts) rather than inferred.
- **Planner — light.** Write the exact per-step command, the expected evidence, and the stop
  condition for each of the four steps.

No Auditor. No Researcher.

**Acceptance criteria**

1. **Hot reload** — with the dev stack up, a change under `src/mkobi/` produces a `Reloading`
   line in the app log within ~10 seconds. `src/mkobi/main.py` is byte-identical to `HEAD`
   afterwards (`git status --porcelain -- src/` is empty).
2. **Test suite** — `.\Makefile.ps1 test` exits 0. Report the pass/skip counts. The
   `could not create cache path: /.pytest_cache` warning documented in plan §6 Phase 5 is
   expected and is **not** a failure; do not "fix" it with `--no-cacheprovider`.
3. **Quality gates** (reuse the already-built image; cheap and they exercise two unverified
   target shapes) — `.\Makefile.ps1 lint` and `.\Makefile.ps1 typecheck` both exit 0.
4. **Backup** — `.\Makefile.ps1 backup` exits 0 and `Get-ChildItem .\backups` shows a `.dump`
   whose `Get-Item` length is plausible (hundreds of KB to a few MB). A file of a few hundred
   bytes means binary corruption — treat as a failure.
5. **Restore** — `.\Makefile.ps1 restore .\backups\<file>` exits 0 with no `pg_restore` errors,
   **and only if the data-impact condition above is satisfied.**
6. **Teardown** — `.\Makefile.ps1 test-down` and `.\Makefile.ps1 down` both exit 0; no `mkobi`
   or `mkobi-test` containers or networks remain; `mko-bazuna-*` is untouched.
7. `git status --porcelain` shows no new modifications under `src/`.

**Not in scope for this block.** `fe-install`, `fe-lint`, `fe-test`, and `check` require
`npm ci` and are §6 Phase 6 items, not §8 boxes. Skip them unless the operator asks.

**Stop conditions**

- **STOP-1** — `docker volume ls --filter label=com.docker.compose.project=mkobi` shows a
  `postgres_data` volume with real content. **Skip the restore step entirely** and report.
- **STOP-2** — the hot-reload probe does not produce a reload line within ~10 s. Stop, restore
  `src/mkobi/main.py` with `git checkout -- src/mkobi/main.py`, and escalate to Open Decision O3.
- **STOP-3** — the pytest suite fails. Stop and report the failure; do **not** "fix" tests to make
  them pass (project rule 2: production code is king).
- **STOP-4** — the backup file is implausibly small. Stop; the binary-safety fix in plan §2.8 is
  not working. Do not attempt a `restore` from a corrupt dump.
- **STOP-5** — any `mko-bazuna-*` container changes state. Stop and report immediately.

**Rollback.** `.\Makefile.ps1 clean` (containers and networks, **volumes kept**).
`git checkout -- src/mkobi/main.py` to restore the hot-reload probe. `Remove-Item` the
`backups/*.dump` file if it should not persist. Never `fullclean`, never `nuke`.

---

### Block 8 — Commit the agent-facing instruction files (Task 7)

**Goal.** Commit the agent instruction updates so no agent is directed at a foreign Compose
project or a non-existent task-runner target.

**Files / semantic units touched**

- `.kilo/rules/commands.md` — the "Quick start" table, the raw `$dc` alias, and the
  Python/quality-gate sections, all rewritten against `-p mkobi` / `-p mkobi-test` and the 44
  real `Makefile.ps1` targets
- `.ai/context/commands.md` — two lines: the testing-database port `5433` → `5434` in the
  context description and in the test `psql` example

**> Correction to the audit.** The Auditor classified `.ai/context/commands.md` as a pre-existing
unrelated change. **It is not.** Planning verified that the file has exactly two hunks and both
are the plan's `5433` → `5434` port change. It must be committed here, not left dirty.

**Dependencies.** Block 5 (the target names committed there are the names this file documents).

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | None | Already written; 34 target references all verified valid |
| Rollout | Low | Agent instruction files take effect on the next agent session |
| Regression | Low | Removes standing instructions to run `mko-bazuna` commands and `test-recreate`, a target that does not exist |
| Compatibility | Low | Would become a problem if the runner's target set changed later — but Block 5 is now committed and stable |

**Required agents.** None. Content verified: 34 target references, English-only, 150 lines,
all Django/mkozuna references removed.

**Acceptance criteria**

1. `git diff --cached --name-only` lists exactly `.kilo/rules/commands.md` and
   `.ai/context/commands.md`.
2. `Select-String 'mko-bazuna|test-recreate|seed|basedpyright|manage\.py|PYTEST_OPTS' .kilo/rules/commands.md` returns nothing.
3. Every `.\Makefile.ps1 <target>` in the file names a target that exists in the committed
   `Makefile.ps1` dispatch table.
4. `.ai/context/commands.md` contains no `5433` and no `6380`.
5. Both files remain English-only.
6. `git status --porcelain -- .kilo/ .ai/` afterwards shows **no** change to the other ~20
   modified and ~35 untracked `.kilo/` paths.

**Commit plan**

```powershell
git add -- .kilo/rules/commands.md .ai/context/commands.md
git commit -m "docs(agents): point agent instructions at the mkobi compose projects"
```

**Stop conditions / rollback.** Stop if the index preview shows any `.kilo/` path other than
`.kilo/rules/commands.md` — the working tree carries ~20 unrelated modified `.kilo/` files and
one deletion (`.kilo/agents/implementor-orchestrator.md`) that must stay untouched. Rollback:
`git revert --no-edit HEAD`.

---

### Block 9 — Commit the operational and deployment documentation

**Goal.** Commit the port-renumbering updates in the four human-facing documents so they stop
advertising `8000` / `5433` / `6380`.

**Files / semantic units touched**

- `README.md` — the backend run URL and test-port references
- `docs/10-deployment/deployment.md` — published host ports for the deployment topology
- `docs/99-reference/run-guide.md` — the local run instructions
- `docs/99-reference/swagger.md` — the documented local API base URL

**Dependencies.** Block 4 (the ports must be committed before they are documented).
Does **not** depend on Block 7 — these are port renames, not behavioural claims.

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | None | A re-scan for `5433`, `6380` and `localhost:8000` across all four files returns no matches |
| Rollout | None | Documentation only |
| Regression | None | No code reads these files |
| Compatibility | Low | Developers with `localhost:8000` muscle memory are affected — this is the intended, documented consequence of Block 3 |

**Known limitation carried by this commit.** `README.md` is still in Russian and still
documents `mkobi.app:app` instead of `src.mkobi.main:app`. Both are plan §7.4 deferred items and
**must not** be fixed here — noting them so the commit is not mistaken for full README
correction.

**Required agents.** None for the port change itself. **Validator — light** is recommended if
the Implementor is tempted to fold in the deferred README fixes; the Validator's job is to
confirm scope was not widened.

**Acceptance criteria**

1. `git diff --cached --name-only` lists exactly the four documents.
2. `Select-String '5433|6380|localhost:8000'` across all four returns no matches.
3. Each file retains its YAML frontmatter contract (`id`, `domain`, `tags`, `related`) intact.
4. No change was made to `README.md`'s language or to the ASGI app path reference.
5. No doc grew past the repo's soft 800-line / hard 1000-line splitting threshold
   (`docs/00-overview/doc-maintenance-rules.md`).

**Commit plan**

```powershell
git add -- README.md docs/10-deployment/deployment.md docs/99-reference/run-guide.md docs/99-reference/swagger.md
git commit -m "docs: publish the configurable dev and test host ports"
```

**Stop conditions / rollback.** Stop if the index preview shows a fifth path, or if the diff
contains anything other than port numbers. Rollback: `git revert --no-edit HEAD`.

---

### Block 10 — Correct the Docker guide profile and service-set drift (D4)

**Goal.** Bring `docs/11-guides/docker.md` in line with the running configuration. This is the
largest doc-drift item and is explicitly queued by plan §7.4 ("must be written **after**
Tasks 1–5 land" — they have landed). It belongs to the Doc-specialist step.

**Files / semantic units touched** — `docs/11-guides/docker.md` only (currently 633 lines):

| Location / topic | Current state (wrong) | Required correction |
|---|---|---|
| The service table's `redis` row | Describes Redis as "production profile" | `redis` has **no** profile; it is always started |
| The "Profiles" section, and the "Note on Frontend Profile" block | Instructs the reader to start the frontend with `--profile frontend` | **No `frontend` profile exists.** Delete the block |
| The "Production Profile" section | Says `production` adds `rq-worker` and `nginx` | `production` adds **exactly `nginx`** — `rq-worker` is un-gated in the base file |
| The "default service set" statement | Wrong set | The dev pair resolves to `db, migrate, app, redis, rq-worker, frontend`; the base file alone resolves to `db, migrate, app, redis, rq-worker` (`frontend` lives in the override) |
| Commands that omit the override file while referring to `frontend` | Broken as written | Every `frontend` reference must include `-f docker/docker-compose.override.yml` |
| The volume-cleanup example | Names `docker_frontend_node_modules` and bare `frontend_vite_cache` | `docker_frontend_node_modules` was deleted; the current volume is `mkobi_frontend_vite_cache` |
| The frontend build example | `exec app npm run build --prefix frontend` | `npm` is **not** in the backend image; the command cannot work |
| Throughout | No `-p mkobi` / `-p mkobi-test` project names | Add them, and document the new `test*` task-runner targets |
| Throughout | No mention of `Makefile.ps1` | Cross-reference `.\Makefile.ps1 help` rather than duplicating the target list (doc rule: single source of truth) |

**Dependencies.** Block 3 (Compose committed), Block 5 (target table committed), Block 9
(sibling docs committed). Strongly recommended after Block 7 so the service set is
empirically confirmed.

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | Low | Documentation only, but 9 distinct corrections across a 633-line file |
| Rollout | None | No runtime effect |
| Regression | None | No code reads this file |
| Compatibility | Low | The doc currently instructs readers to run a command that cannot succeed; fixing it can only improve correctness |

**Required agents**

- **Planner — required (small).** One genuine ambiguity must be settled *before* the Doc writes:
  the doc must state **two different default service sets** (base file alone vs. base + dev
  override) and readers will confuse them. The Planner decides how to present both without
  creating a new false claim, and whether the file should be split (it is 633 lines; the repo
  soft threshold is 800, so no split is required).
- **Validator — required.** Nine corrections is enough surface for a Doc specialist to
  reintroduce a claim that is wrong in a *new* place. The Validator's job is to confirm the
  corrected file makes **no** claim that `docker compose config --services` contradicts.

No Auditor. No Researcher — plan §7.4 already prescribes the exact fixes (a), (b) and (c); there
is no open best-practice question.

**Acceptance criteria**

1. `Select-String 'profile frontend' docs/11-guides/docker.md` returns nothing.
2. `Select-String 'docker_frontend_node_modules' docs/11-guides/docker.md` returns nothing.
3. `npm run build` no longer appears as a command runnable inside the backend `app` container.
4. Every example that mentions `frontend` passes `-f docker/docker-compose.override.yml`.
5. Both `-p mkobi` and `-p mkobi-test` appear, and every service-list claim matches
   `docker compose ... config --services` output exactly.
6. The `test` target family and `.\Makefile.ps1 help` are cross-referenced, not re-listed in full.
7. Frontmatter contract intact; file still under the 800-line soft threshold; English only.
8. `git diff --cached --name-only` lists exactly `docs/11-guides/docker.md`.

**Commit plan**

```powershell
git add -- docs/11-guides/docker.md
git commit -m "docs(docker): correct the service set and profile documentation"
```

**Stop conditions / rollback.** Stop if the Doc specialist proposes changing Compose to match
the doc — the doc is what is wrong here. Rollback: `git revert --no-edit HEAD`.

---

### Block 11 — Resolve and commit the `docs/SPEC.md` history-integrity conflict (D5)

**Goal.** Settle and then commit the `docs/SPEC.md` change. **This block must not begin until
Open Decision O4 is resolved by the Validator.** No approach is chosen here.

**Files / semantic units touched** — `docs/SPEC.md` only.

**The conflict.** Plan §7.6.1 states: *"`docs/SPEC.md` was deliberately **not** edited — lines
164/180/202 are an append-only record of what was done at a point in time."* That claim is
**false**. The working-tree diff shows:

- **Three new history bullets appended** (compose project-name isolation; configurable host
  ports; hermetic test credentials) and **two new bullets** (`Makefile.ps1` is the canonical
  entry point; production `REDIS__HOST` is mandatory) — all legitimately append-only.
- **Two existing history rows rewritten in place**: the "Standalone test compose" row and the
  "Test port exposure trade-off" row were edited to change `5433, 6380` → `5434, 6381`.
- The version header bumped `3.10` → `3.11` and the date `2026-06-16` → `2026-09-30`.

So the file mixes append-only additions with in-place mutation of a historical record, while
the plan asserts the latter never happened.

**Additional inconsistency.** The version-3.6 history row still says `5433, 6380, 8001`, which
now contradicts the 3.11 row's `5434, 6381, 8001`. Under a strict append-only reading this is
*correct* (3.6 records what was true in 3.6); under an in-place-mutation reading it is a bug.

**Alternatives — the Validator chooses; the Planner does not**

| # | Path | Rationale for | Rationale against |
|---|---|---|---|
| A | **Restore the two rewritten rows** to their original text, keeping only the additive 3.11 row and new bullets; add one line to the 3.11 row noting the port correction | Makes the file genuinely append-only and makes §7.6.1's claim true. The historical record stays accurate | The "what the test compose looks like" bullets then sit in the 3.6 section describing stale ports, with the correction only visible in 3.11 |
| B | **Keep the in-place edits and annotate** them (e.g. a parenthetical "ports since corrected to 5434/6381 in 3.11") | Keeps the document readable and current; the annotation preserves the audit trail | Still mutates history; contradicts §7.6.1 as written; every future correction repeats the problem |
| C | **Leave the file exactly as it is** and treat the in-place edits as acceptable because they are factually more correct | Smallest diff; the document is more accurate now | The §7.6.1 claim remains false; the 3.6-vs-3.11 port inconsistency stays unexplained |

**Dependencies.** Blocks 3, 4, 5, 7 (the technical facts recorded in SPEC.md must be committed
first). **Blocked on Open Decision O4.**

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | Low | One file, small diff |
| Rollout | None | No runtime effect |
| Regression | None | No code reads this file |
| Compatibility | None | Purely a documentation-integrity judgement |

**Required agents**

- **Validator — required and decisive.** This is a doc-integrity call with no objectively correct
  answer, and the plan's own statement is demonstrably false. The Validator picks A, B, or C,
  states why, and confirms the choice is consistent with
  `docs/00-overview/doc-maintenance-rules.md` ("no silent dropping", "single source of truth").
- **Planner — light.** Once A/B/C is chosen, write the exact edit.

No Auditor. No Researcher.

**Acceptance criteria**

1. A Validator decision on A/B/C is recorded in this plan's §6 (Open Decision O4).
2. The resulting `docs/SPEC.md` either is genuinely append-only, or carries an annotation that
   makes the in-place mutations self-evident.
3. The 3.6-vs-3.11 port inconsistency is either resolved or explicitly explained.
4. If path A is chosen, `git diff` shows **no** modification to any pre-existing history row.
5. Frontmatter and file structure unchanged; English only.

**Commit plan** (path chosen by the Validator; message shown for path B)

```powershell
git add -- docs/SPEC.md
git commit -m "docs(spec): record compose project isolation and configurable host ports"
```

**Stop conditions / rollback.** Stop if no Validator decision exists. Rollback:
`git revert --no-edit HEAD`.

---

### Block 12 — Commit the plan of record

**Goal.** Bring the source plan and this execution plan into version control so the next
reader has the authoritative status.

**Files / semantic units touched**

- `.ai/plans/mkobi-docker-taskrunner-remediation.md` (untracked, 1200 lines) — **add only.**
  Do **not** tick the §8 boxes or correct the §2.7 / Task 6 / §7.6.3 factual errors without the
  user authorization named in Open Decision O1
- `.ai/plans/00-mkobi-docker-taskrunner-remediation-execution.md` (this file, new)

**Dependencies.** All prior blocks.

**Risk**

| Dimension | Rating | Note |
|---|---|---|
| Implementation | None | Two `git add` operations |
| Rollout | None | No runtime effect |
| Regression | None | Documentation only |
| Compatibility | None | — |

**Required agents.** None for the add. If the user authorizes Open Decision O1, add a
**Validator** pass to confirm the tick/correction set is accurate and that no factual error was
introduced.

**Acceptance criteria**

1. `git diff --cached --name-only` lists exactly the two plan files.
2. `.ai/plans/audit-fix-plan.md` remains deleted and unrestored (expected per plan Task 8's
   warning — do not "fix" it).
3. No other `.ai/` path is staged.
4. All 26 §8 boxes are still unticked and the three §D8 factual errors are still present —
   unless and until Open Decision O1 is answered.

**Commit plan**

```powershell
git add -- .ai/plans/mkobi-docker-taskrunner-remediation.md .ai/plans/00-mkobi-docker-taskrunner-remediation-execution.md
git commit -m "docs(plans): record the docker and task-runner remediation and its execution plan"
```

**Stop conditions / rollback.** Stop if the index preview shows any path outside `.ai/plans/`.
Rollback: `git revert --no-edit HEAD`.

---

## 4. Block dependency graph and execution order

```
                    ┌─────────────────────────────────────────────┐
                    │  BLOCK 1  Commit repository hygiene          │
                    │  (.gitignore, $null, test_write_permission)  │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  BLOCK 2  E2E gate A: dev stack + --wait      │  ← satisfies plan §7.1
                    │  NO COMMIT · mutates Docker · NO data lost   │     "resolve empirically
                    └──────────────────┬──────────────────────────┘     before committing"
             ┌─────────────────────────┼─────────────────────────┐
             │                         │                         │
  ┌──────────▼─────────┐   ┌───────────▼──────────┐   ┌──────────▼──────────┐
  │ BLOCK 3            │   │ BLOCK 4              │   │ BLOCK 5             │
  │ Commit Part A      │   │ Commit conftest +    │   │ Commit Makefile.ps1 │
  │ (3 compose files)  │   │ .env.example         │   │ as landed           │
  └──────────┬─────────┘   └──────────┬───────────┘   └──────────┬──────────┘
             └─────────────────────────┴─────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  BLOCK 6  Implement `up` hard-fail message    │  ← the only §8 gap
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  BLOCK 7  E2E gate B: hot reload, test,      │  ← CONDITIONALLY
                    │  backup/restore    NO COMMIT                 │     DESTRUCTIVE
                    └──────────────────┬──────────────────────────┘
             ┌─────────────────────────┼─────────────────────────┐
             │                         │                         │
  ┌──────────▼─────────┐   ┌───────────▼──────────┐   ┌──────────▼──────────┐
  │ BLOCK 8            │   │ BLOCK 9              │   │ BLOCK 10            │
  │ Commit agent       │   │ Commit ops/deploy    │   │ D4: fix             │
  │ instructions       │   │ docs (ports)         │   │ docker.md drift     │
  └────────────────────┘   └──────────────────────┘   └─────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  BLOCK 11  D5: SPEC.md integrity             │  ← BLOCKED on O4
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  BLOCK 12  Commit the plan of record         │
                    └─────────────────────────────────────────────┘
```

**Recommended execution order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12**

**Why 2 comes before 3, 4 and 5.** Plan §7.1 rates the "`up --wait` does not treat the exited-0
`migrate` one-shot as satisfied" risk as **Medium** likelihood and prescribes the mitigation
*"resolve empirically before committing the script"*. Committing Compose and the runner first
would commit a configuration whose central claim is untested.

**Why 6 comes after 5 and not before.** Committing the script as-landed creates a clean baseline
against which the D7 fix is a small, independently reviewable delta. If the fix were folded into
the initial commit, the Validator would have to review 428 lines plus a behavioural change at
once, and a single-`exit`-path regression would be much harder to spot.

**Why 7 comes before 8–10.** The doc blocks (8, 9, 10) describe the behaviour that Block 7
verifies. Writing documentation against unverified behaviour is how doc drift is created —
Block 10 exists precisely to fix drift.

**Why 11 is last among docs.** It is blocked on a Validator decision, and it should record only
facts already committed and verified.

**Parallelism.** None. The project rule permits one Implementor at a time, and the blocks share
the single working tree, the single Docker daemon, and — critically — the same staged index.
Serial execution is the only safe choice.

---

## 5. Risk register (consolidated, ranked)

| # | Risk | Blocks | Likelihood | Impact | Mitigation |
|---|---|---|---|---|---|
| R1 | `up --wait` does not accept the exited-0 `migrate` one-shot; the dev stack never starts | 2, 3, 5, 6, 7 | Medium (plan §7.1) | High — blocks 5 downstream commits | Block 2 runs first. On failure, STOP-2 escalates to O2; the plan's documented fallback is **not** applied without approval |
| R2 | A commit sweeps in unrelated `.ai/` / `.kilo/` changes | every committing block | **High** without discipline | High — corrupts the plan of record and destroys the operator's unrelated work | Stage by explicit path only; `git diff --cached --name-only` preview is a **mandatory** gate in every commit block; `git add -A`/`.`/`-u` are prohibited outright |
| R3 | `restore` destroys real dev data in `bidb` | 7 | Low (no dev volume exists today) | **Severe and irreversible** | STOP-1 re-checks for a populated `mkobi_postgres_data` before the step; the step is skipped if one exists |
| R4 | The hot-reload probe leaves `src/mkobi/main.py` dirty, and it gets swept into a later commit | 7 | Medium | Medium | `git status --porcelain -- src/` is acceptance criterion 1 of Block 7; `git checkout -- src/mkobi/main.py` is in the block's rollback |
| R5 | `mko-bazuna-*` is disturbed (it holds host ports `8000` and `5433`) | 2, 7 | Low | High — destroys another project's running stack | Never run `down`/`prune` against it; `nuke`/`fullclean` are excluded from every block; STOP-5 in Block 7 |
| R6 | The D7 fix introduces a second `exit`, breaking plan constraint 5 and an §8 box | 6 | Medium if shape C is chosen | Medium | Shape A/B is compliant by construction; acceptance criterion 2 re-runs the `exit` grep; Validator is required |
| R7 | `docs/SPEC.md` history is mutated while the plan asserts it was not | 11 | **Certain — already happened** | Medium (doc integrity) | Decision is escalated to the Validator (O4); no Implementor picks a path unilaterally |
| R8 | A later agent reads §8 literally and reports 26 false failures | any | **High** | Medium — wasted cycles, false bug reports | This plan is the authoritative status record. O1 requests authorization to tick the boxes and correct the three D8 errors |
| R9 | `docs/11-guides/docker.md` is "fixed" but a new wrong claim is introduced elsewhere in the file | 10 | Medium | Medium | Validator's job is specifically to cross-check every service-set claim against `config --services` output |
| R10 | A Doc specialist widens scope and implements a plan §7.4 deferred item | 9, 10, 11 | Medium | Medium — scope creep into risky areas (`pyproject.toml`, README translation, `test-migrate` removal) | §2.2 lists the excluded items explicitly; acceptance criteria in Block 9 forbid folding in the README fixes |
| R11 | `test-select` on a cold machine fails with a DB connection error | future | Medium | Low — confusing, not incorrect | Left unfixed by design. O5 presents three shapes; the decision belongs to the Validator |
| R12 | The `mkobi` / `mkobi-test` project names become part of history before they are proven to start | 3, 5 | Low (Block 2 gates it) | Medium | Block 2 precedes both |
| R13 | Test suite fails in Block 7 and pressure is applied to "fix the tests" | 7 | Medium | Medium — violates project rule 2 | STOP-3 explicitly forbids it: report the failure, do not distort production code |
| R14 | The first `dev` image build in Block 2 is slow and the block is abandoned mid-run, leaving a partial stack | 2 | Medium | Low | `.\Makefile.ps1 down` is non-destructive and idempotent; safe to re-enter |

---

## 6. Open decisions — deliberately not chosen

| ID | Question | Why not decided here | Decider | Blocks |
|---|---|---|---|---|
| **O1** | May the source plan be edited to tick the 25 satisfied §8 boxes and correct the three D8 factual errors ("9 revisions" → 8; the `README.md:103` claim about `mkobi.app:app`; §7.6.3's "a single `mkobi-test_test_postgres_data` volume" — there are two)? | The workflow brief instructs that the source plan must not be modified. Editing it requires explicit user authorization that this Planner cannot grant | **User**, then **Validator** to verify the tick set | 12 |
| **O2** | If `up --wait` fails naming `migrate`, is the plan §6 Phase 3 fallback approved? The fallback replaces the single `up -d --wait` with `rm -sf migrate` → `run --rm migrate` → `up -d --wait`. The plan states it *"requires approval before use"* and explicitly forbids silently substituting a hand-rolled polling loop | It is an explicit user-approval gate written into the plan. Substituting it automatically would invert the plan's own instruction | **User** (escalated by the Implementor via Block 2 STOP-1/STOP-2) | 2 → 3, 5, 6, 7 |
| **O3** | How is the hot-reload probe triggered? (a) add a comment to `src/mkobi/main.py` and revert it — plan-literal but mutates a production source file; (b) mtime-only touch — content-safe, but may not propagate through gRPC-FUSE; (c) create and delete a throwaway `src/mkobi/_reload_probe.py` — content-safe for real sources, briefly adds a file to the package | (a) follows the plan literally but carries the working-tree-corruption risk in R4; (c) is safer for the tree but deviates from the plan's literal instruction. Both are defensible and the plan does not rank them | **Implementor**, confirmed by the **Validator** | 7 |
| **O4** | `docs/SPEC.md`: restore the two rewritten history rows (A), keep the in-place edits and annotate them (B), or leave as-is (C)? | Explicitly escalated: a documentation-integrity judgement with no objectively correct answer, where the plan's own §7.6.1 claim is demonstrably false | **Validator** (decisive) | 11 |
| **O5** | `test-select` on a cold machine: (a) add the `up -d --wait test-db test-redis` line to `Invoke-TestSelect`, matching `Invoke-Test`/`Invoke-TestAll`; (b) document the `test-up` prerequisite in `.kilo/rules/commands.md` only; (c) add a friendly pre-flight check that reports *"run .\Makefile.ps1 test-up first"* | Three reasonable shapes with different trade-offs (a) changes code, (b) shifts burden to the reader, (c) adds a code path for a case Compose already reports clearly. The plan does not address it at all and D11 is a **deferred/out-of-scope** finding — so fixing it here would be scope creep without a decision | **Validator**, then Implementor **only if authorized** | future — not in this plan |
| **O6** | Should step 3.3 use `.ai/tasks/templates/task_template.yaml`? The workflow brief states this file was deleted in a pre-existing working-tree deletion and instructs this Planner to define the structure inline. **Planning verified the file exists on disk, is tracked by git, and is clean** — the brief's premise is incorrect. This plan therefore defines the structure inline as instructed, **derived from the real template so the two stay compatible** | Resolved procedurally: inline structure is provided below and is template-compatible. No decision needed, but the discrepancy is recorded so the user can correct the brief | **User** (informational) | all |

### 6.1 Inline YAML task-description structure (template substitution)

**Note.** The workflow normally references `.ai/tasks/templates/task_template.yaml` for step 3.3.
Per instruction, that file is **not** restored or referenced; the structure below is defined
inline. Planning found the real template still present, tracked and clean (see O6), so the keys
below deliberately mirror it and can be adopted back into the template verbatim if the user
prefers.

```yaml
id: TSK_<block_id>                     # e.g. TSK_03_compose_commit
title: <block title>
type: implementation | verification | decision   # 'decision' for blocks 2, 7, 11
status: pending | blocked
blocked_by: []                          # TSK ids that must land first
depends_on: []
priority: high | medium | low

source_reference: C:\py_dev\mkobi\.ai\plans\mkobi-docker-taskrunner-remediation.md
source_file: C:\py_dev\mkobi\.ai\plans\00-mkobi-docker-taskrunner-remediation-execution.md
source_section: "BLOCK <n> — <title>"

description: >
  One paragraph. What this block does and why it exists.

goals:
  - <goal 1>
  - <goal 2>

files:
  - path: <repo-relative path>
    targets:                            # SEMANTIC anchors only — never line numbers
      - type: function
        name: Invoke-Up
      - type: yaml_key
        name: services.app.environment.CORS_ORIGINS
      - type: markdown_section
        name: "Profiles"
    semantic_anchors:
      insert_before: { type: return_statement }
      insert_after:  { type: function_call, value: Invoke-Test }

changes:
  - action: commit | add_code | edit_doc | run_only
    description: >
      What changes, in one sentence.
    code_hint: |
      Optional. Exact snippet for add_code blocks only.

risk:
  implementation: low | medium | high
  rollout: low | medium | high
  regression: low | medium | high
  compatibility: low | medium | high
  data_destructive: true | false
  rollback: <exact revert command>

agents:
  auditor:     { required: bool, justification: <one line> }
  researcher:  { required: bool, justification: <one line> }
  planner:     { required: bool, justification: <one line> }
  validator:   { required: bool, justification: <one line> }

acceptance_criteria:
  - <concrete, verifiable criterion>

commit:
  stage:                          # EXPLICIT PATHS ONLY — never -A, never .
    - <path>
  message: "<repo-style conventional commit subject>"
  preview_required: true         # git diff --cached --name-only must be reviewed before commit

stop_conditions:
  - STOP-<n>: <condition and required action>

open_decisions: [O1, O2, ...]     # ids from section 6
```

**Verification-task variant** (used by blocks 2 and 7):

```yaml
id: VERIFY_<block_id>
title: "Verify — <block title>"
type: verification
depends_on: [TSK_...]
verifies: [TSK_...]
verification_steps:
  - build: <command>
  - run: <command>
  - evidence: <the exact artifact that proves success, e.g. exit code, HTTP status, byte size>
pass_criteria: [<criterion 1>, <criterion 2>]
failure_action: return <implementor task> to rework; escalate if a stop condition fired
rollback_task: <id or null>
```

### 6.2 Per-block agent requirement matrix

| Block | Goal (one line) | Auditor | Researcher | Planner | Validator |
|---|---|:---:|:---:|:---:|:---:|
| 1 | Commit `.gitignore` + the two staged root-artifact deletions | – | – | – | – |
| 2 | Prove the dev stack starts and `--wait` accepts the exited-0 `migrate` | – | – | light | **yes** |
| 3 | Commit the three Compose files as landed | light | – | – | **yes** |
| 4 | Commit the `tests/conftest.py` + `.env.example` port alignment | – | – | – | – |
| 5 | Commit `Makefile.ps1` as landed | light | – | – | **yes** |
| 6 | Add the `up` hard-fail message to `Invoke-Up` | – | – | light | **yes** |
| 7 | Close hot-reload / test / backup-restore §8 boxes | – | – | light | **yes** |
| 8 | Commit the agent instruction files | – | – | – | – |
| 9 | Commit the four port-renumbered docs | – | – | – | light |
| 10 | Correct the `docker.md` profile / service-set drift | – | – | **yes** | **yes** |
| 11 | Decide and commit the `docs/SPEC.md` integrity fix | – | – | light | **yes** (decisive) |
| 12 | Commit the source plan + this execution plan | – | – | – | conditional on O1 |

**Blocks 2, 6, 7 and 11 get all-agent treatment for their required subset** — they are the
high-risk blocks: one mutates Docker, one writes new code against a hard constraint, one is
conditionally destructive, one resolves a judgement call.

---

## 7. Definition of Done for this execution

The execution is complete when **all** of the following hold.

**Committed state**

1. `git status --porcelain` shows **no** unstaged modification to any file this plan touched.
2. The working tree still contains the operator's pre-existing unrelated changes: the ~19 `.ai/`
   deletions, the modified `.ai/audit/templates/audit-findings.md`, the modified
   `.ai/context/commands.md` (**now committed** — see Block 8), the deleted
   `.kilo/agents/implementor-orchestrator.md`, the ~20 modified and ~35 untracked `.kilo/` files.
   **None of these are reverted or committed except the one file Block 8 legitimately claims.**
3. `git log` shows exactly 11 new commits, in the order given in §4, with no `git add -A` and no
   empty commits.
4. Every commit's `git diff --cached --name-only` was reviewed before committing.

**Plan requirements**

5. All 26 §8 boxes are satisfied by the committed code — verified by direct inspection of the
   commit, **not** by the unticked boxes themselves (see O1 and R8).
6. The 12 commits collectively cover: 3 Compose files, `tests/conftest.py`, `.env.example`,
   `Makefile.ps1`, `.gitignore`, `README.md`, `docs/10-deployment/deployment.md`,
   `docs/11-guides/docker.md`, `docs/99-reference/run-guide.md`, `docs/99-reference/swagger.md`,
   `docs/SPEC.md`, `.kilo/rules/commands.md`, `.ai/context/commands.md`, and both plan files.
   Plus the two deletions of `$null` and `test_write_permission.md`.

**Verification**

7. `docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config --services` returns the six dev services with no `nginx`.
8. The credential-leak regression returns zero `LEAKED*` matches.
9. `Select-String 'exit ' Makefile.ps1` matches exactly one line, and it is the final line.
10. `Select-String 'mko-bazuna|test-recreate|basedpyright|manage\.py' .kilo/rules/commands.md` returns nothing.
11. Every service-set and profile claim in `docs/11-guides/docker.md` matches `config --services` output.
12. Block 2 and Block 7 evidence exists and was signed off by a Validator.

**Unchanged state**

13. `mko-bazuna-*` containers are still running, untouched.
14. No `docker_*` legacy volume was recreated; the plan §3.3 sequence was not re-run.
15. `nuke`, `fullclean`, and `docker system prune --volumes` were never executed.

**Explicitly not required**

16. The plan §7.4 deferred list is untouched.
17. O1, O2, O3, O4 and O5 are each either resolved or recorded as an accepted open item with a
    named decider.
