---
id: configuration-secrets-remediation-execution
domain: plans
tags:
  - configuration
  - secrets
  - security
  - deployment
  - docker
  - remediation
related:
  - configuration
  - deployment
  - security-checklist
  - docker-guide
  - security-overview
---

# Configuration & Secrets — Remediation Execution Plan

## Purpose

Turn the validated findings of audit phase **02-configuration-secrets** into an executable,
dependency-safe programme. This document is the Planner deliverable: it fixes the block
boundaries, names the semantic code units each Implementor touches, supplies the verification
commands, and hands over one ready-to-use task per block.

| Item                     | Value                                                            |
| ------------------------ | ---------------------------------------------------------------- |
| **Phase**                | 02-configuration-secrets (remediation execution)                  |
| **Date**                 | 2026-09-30                                                        |
| **Source plan**          | `.ai/audit/99-validation/02-configuration-secrets-validated-findings.md` |
| **Underlying audit**     | `.ai/audit/02-configuration-secrets/findings.md` (untracked; carries the step-by-step remediation text the validation cites) |
| **Code context**          | Auditor `{code_context}`, tool output `tool_0f1f12809001yt8w483JvLndFW` |
| **Sibling plan**         | `.ai/plans/00-mkobi-docker-taskrunner-remediation-execution.md`    |
| **Task template**        | `.ai/tasks/templates/task_template.yaml`                          |
| **Owner**                | Tech Lead (rulings R1–R12) + Planner (this document)              |
| **Status**               | Ready to execute, one Implementor at a time, strictly sequential  |

> **Anchor authority.** The Auditor's re-derived anchors in `{code_context}` §B supersede the
> source plan's anchors wherever the two disagree. In this document every instruction is
> expressed as a **symbol**, never as a line number; the Auditor's line numbers are locality
> hints only and are quoted here solely to help an Implementor find a symbol quickly.

---

## Scope rulings (R1–R12)

These rulings are decided by the Tech Lead and are **not** re-litigated by any Implementor.

| ID    | Ruling |
| ----- | ------ |
| **R1** | **Block boundaries are fixed.** Execute B1 → B2 → B3 → B4 → B5, sequentially, one Implementor at a time. Do not merge or split them. B1 is self-contained and de-risks the rest; B3, B4 and B5 all edit `src/mkobi/config.py`, so they are strictly ordered; B4 and B5 both edit `src/mkobi/app.py`, so B5 follows B4. |
| **R2** | **Credential predicate scope.** Ship `startswith("change_me")` (case-insensitive) **plus** emptiness and whitespace clauses. **Do NOT ship substring matching** against `WEAK_PASSWORDS` / `WEAK_SECRETS` — the Auditor measured that it rejects the repository's own dev/test credentials and breaks shipped tests. Keep the existing exact-set membership as a backstop. |
| **R3** | **Tier gating.** New placeholder/emptiness clauses go **inside the existing production-gated predicates only**. `JWTSettings.validate_secret_key` is unconditional — do **not** add a placeholder clause there; the dev template and the weak-secret tests would break. |
| **R4** | **Emptiness minimums.** `admin_password`: non-empty after `strip()`, and a minimum length aligned to the existing `DatabaseSettings.validate_admin_password_strength` floor (**8**). `admin_username`: non-empty after `strip()` only — no length rule for a username. |
| **R5** | **No secret value in exception text.** De-interpolate **both** the admin-username message and the `DATABASE__PASSWORD` placeholder message in `Settings.DATABASE_URL`. Do not fix only the username. |
| **R6** | **In scope: VAL-002 and VAL-003.** Both are real MEDIUM system defects sequenced by the plan's own Roadmap before the cleanup step. VAL-003 → **B3**; VAL-002 → **B5**. |
| **R7** | **Out of implementation scope: VAL-001, VAL-004, VAL-005, VAL-006, VAL-007, VAL-008, VAL-009.** All seven are defects in the *audit artefact*, not in the mkobi system. Recorded below as "Deferred — audit-artefact hygiene". The *surviving* content of VAL-005/006/007/008 is carried into the blocks as corrections to the Implementor's instructions so a wrong anchor or wrong premise is not reproduced in a change. |
| **R8** | **CFG-007 rows must each be decided, not deferred.** Where intent cannot be established from the working tree, the ruling is: **delete the field and its `app.yaml` key** — unread configuration *is* the defect CFG-007 reports. All six rows plus the Auditor's seventh candidate (`app.yaml` top-level `env:`) are decided in B5. |
| **R9** | **Documentation is deferred to the dedicated Documentation phase.** B1..B5 may touch comments inside files they already edit, and `docker/.env.production`. **No `docs/**/*.md` file is edited by an Implementor.** The required documentation edits are collected in the consolidated list below. |
| **R10** | **Commit discipline (hard rule).** The working tree already carries unstaged deletions of tracked `.ai/**` files and untracked audit directories. Every commit must use **explicit `git add <specific paths>`** — never `git add -A`, `git add .`, `git add src`, or any pattern that could sweep them in. **One commit per block**, message form `"{type}({scope}): {description}"`, matching the repo's existing style. *(Planner measurement: 19 unstaged deletions and 4 untracked entries — the three audit directories plus this plan file. The count is 19, not 20; the rule applies to all of them regardless.)* |
| **R11** | **Test gates.** Per-block gates: `.\Makefile.ps1 test-select tests/test_config.py -q` (baseline **88 passed**), plus `.\Makefile.ps1 test-select tests/test_starter.py -q` where B3 touches it, plus `uv run ruff check <paths>` and `uv run mypy <paths>`. The **full suite is red at baseline: 23 failed / 963 passed**. The rule is *do not regress*, not *make it green*. The **11 `tests/test_starter.py::TestEnsureAdminUserPlaceholderCheck` failures are in scope** — B3 must leave that class green and meaningful. |
| **R12** | **Hard exclusions.** No frontend changes. No Alembic migration (confirmed unnecessary). No new runtime dependency. No `print()`. English only in comments/logs/docstrings. `StrEnum` for any new constant. Do **not** "fix" the fact that `src/mkobi/config.py` validators raise `ValueError` inside Pydantic — that is the correct mechanism there and never reaches the HTTP/RFC-7807 layer. |

---

## Programme overview

The validated findings describe one coherent problem: **the configuration surface the
repository presents as authoritative is not the configuration surface the system reads.**
Ten product findings (CFG-001..CFG-010) and two in-scope validation findings (VAL-002,
VAL-003) are discharged by five blocks.

| Block | Findings discharged          | Theme                                                | Files |
| ----- | --------------------------- | ---------------------------------------------------- | ----- |
| **B1** | CFG-005                     | Build context must not carry credential material     | `.dockerignore` |
| **B2** | CFG-001, CFG-006, CFG-004   | Deployment posture of the production compose file    | `docker/docker-compose.yml`, `docker/.env.production` |
| **B3** | CFG-002, CFG-003, VAL-003   | Credential predicates: one guard, no secret in errors | `src/mkobi/config.py`, `src/mkobi/db/starter.py`, `tests/test_config.py`, `tests/test_starter.py` |
| **B4** | CFG-008, CFG-009            | Configuration source scope                          | `src/mkobi/config.py`, `src/mkobi/app.py`, `tests/test_config.py` |
| **B5** | CFG-007, VAL-002            | Unread and relative configuration                    | `src/mkobi/config.py`, `src/mkobi/settings/app.yaml`, `.env.example`, `src/mkobi/app.py`, `tests/test_config.py` |

**Blast radius (total):** two Python production modules, one FastAPI factory module, one YAML
settings template, one dotenv template, one Docker-ignore file, two Docker Compose artefacts
(`docker/docker-compose.yml`, `docker/.env.production`), and two test modules. No schema, no
API surface, no frontend.

**What is explicitly NOT being done:**

- **R7** — the seven audit-artefact defects (VAL-001, VAL-004..VAL-009) are not fixed. They are
  defects in the audit documents, not in the mkobi system, and the audit files are protected by
  the user's instruction. They are listed with rationale below.
- **R9** — no `docs/**/*.md` file is edited by an Implementor. All documentation edits are
  handed to the Doc-specialist as a consolidated list.
- **R12** — no frontend change, no Alembic migration, no new dependency, no `print()`, no
  `StrEnum` invention beyond what a block actually needs, and no change to the
  `ValueError`-inside-Pydantic validation mechanism.

**Programme exit condition (all must hold):**

1. B1..B5 committed, one commit each, explicit `git add` paths only (R10).
2. `.\Makefile.ps1 test-select tests/test_config.py -q` is at or above the 88-passed baseline and
   `.\Makefile.ps1 test-select tests/test_starter.py -q` is fully green.
3. `.\Makefile.ps1 lint` and `.\Makefile.ps1 typecheck` are clean for every touched path.
4. The full-suite failure count has **not increased** from the 23-failure baseline, and the
   12 out-of-scope pre-existing failures are listed by name in the final validation report.
5. `git status` shows no swept-in `.ai/**` deletion and no new untracked file other than the
   audit directories that were already untracked at baseline.

---

## Cross-cutting rules

### Test gates (R11)

```powershell
# Per block, always
.\Makefile.ps1 test-select tests/test_config.py -q      # baseline 88 passed
uv run ruff check <paths touched by the block>
uv run mypy <paths touched by the block>

# B3 additionally
.\Makefile.ps1 test-select tests/test_starter.py -q      # baseline 11 failed -> target 11 passed
```

`tests/conftest.py` sets `ENV=test` before importing the application, so most configuration
tests construct `Settings` in the `test` tier. Any new test that needs another tier must set
`ENV` explicitly through `monkeypatch` and restore it — the `TestSettingsBase.clean_env` fixture
already backs up and restores `ENV`.

**Baseline recorded numbers (Auditor-measured, not re-measured by the Planner):**
`tests/test_config.py` → 88 passed. `tests/test_starter.py` → 11 failed, 0 passed (the whole file
is one parametrized class). Full suite → 23 failed / 963 passed, of which 11 are the
`test_starter.py` class (in scope) and 12 are pre-existing and out of scope.

### Commit discipline (R10)

One commit per block, explicit paths only. The pre-existing unstaged deletions of tracked
`.ai/**` files and the untracked audit directories must remain unstaged and unstompped in every
block. Verify with `git status --porcelain` before and after each `git add`.

### Agent requirement matrix

| Block | Auditor | Researcher | Planner | Validator |
| ----- | :-----: | :---------: | :-----: | :--------: |
| **B1** | not required | not required | not required | not required |
| **B2** | not required | not required | not required | **required** |
| **B3** | not required | **required** | not required | **required** |
| **B4** | not required | **required** | not required | **required** |
| **B5** | not required | **required** | not required | **required** |

Rationale per block is given in each block's *Agent requirement* subsection. Auditor is never
required: every file, class, function and test symbol named in this plan was re-verified
against the working tree by the Planner, so no Implementor should need to re-derive locality.

### Environment constants

| Service | Value |
| ------- | ----- |
| Dev Compose project | `mkobi` (`.\Makefile.ps1 <target>`) |
| Test Compose project | `mkobi-test` (PostgreSQL on host port `5434`) |
| Production base file | `docker/docker-compose.yml` (declares `name: mkobi`) |
| Working production invocation | `docker compose --env-file docker/.env.production -f docker/docker-compose.yml up -d` (run from the repo root) |
| Repository root `.env` | present and untracked; contains dev credentials such as `ADMIN_PASSWORD=test_password`, `DATABASE__PASSWORD=test_app_password`, `JWT__SECRET_KEY=dev_secret_key_change_in_production_use_openssl_rand_hex_32` |

---

## B1 — Build context (CFG-005)

### Goal

Make the Docker build context incapable of carrying credential material. Today the
".dockerignore already excludes env files" defence is four root-anchored patterns
(`.env`, `.env.example`, `.env.local`, `.env.*.local`) that match **no file anywhere in the
repository**, while the files that genuinely hold credentials — the untracked root `.env` and
`.env.docker`, the three tracked templates under `docker/`, the `.env` inside
`.kilo/worktrees/lowly-principal/`, the credential file `.ai/mcp/.env`, database dumps and the
`backups/` directory — all enter the build context. This block replaces the four patterns with
a set that cannot be bypassed by moving a file one directory deeper, and adds the dump and
audit-artefact exclusions. It touches exactly one file and is self-contained: it de-risks B2
before B2 changes the production deployment posture.

### Findings discharged

- **CFG-005** (HIGH) — credential material in the Docker build context.

### Findings partially discharged

None.

### Files and semantic code units to touch

| File | Unit |
| ---- | ---- |
| `.dockerignore` | the comment block headed `# Environment and secrets - NEVER include in Docker images` |

No other file is modified by this block. In particular, **no Dockerfile is modified** — the
change must be a pure exclusion expansion, not a build-script change.

### Implementation sequence

1. In `.dockerignore`, edit the **"Environment and secrets"** block in place. Do **not** move the
   block: Docker applies the **last** matching pattern as the decision, and the later
   `docs/` / `*.md` section must keep precedence over the earlier `*.md` and `!README.md`
   lines. Editing in place preserves the existing ordering semantics.
2. Replace the four root-anchored patterns (`.env`, `.env.example`, `.env.local`,
   `.env.*.local`) with a root-anchored pattern plus a recursive one, so a `.env` at any depth is
   excluded. Keep both forms: the bare form is root-anchored in Docker's ignore matching, the
   `**/` form covers every directory level.
3. Add a pattern excluding a path with the `*.dump` suffix (matches `postgres.dump` at the
   repository root).
4. Add a pattern excluding the `backups/` directory, and a pattern excluding the `.ai/` directory.
5. **Do not re-add `.kilo/` or `.idea/`.** They are already present earlier in the file under the
   IDE section. The source plan's remediation list proposes them as additions; the Planner has
   checked the file and they are not additions. Adding them would be duplication.
6. Update the block's leading comment so it states what the block is for. **Do not put a count of
   credential names, files, or bytes into the comment.** See *Corrections carried from R7* below.

### Corrections carried from R7

- **VAL-006 (surviving content).** The audit's name count for `.ai/mcp/.env` is **32**, not 33.
  The Planner did not re-enumerate it. The instruction is negative: the Implementor must not
  write a number into `.dockerignore`. The file is excluded by pattern; its contents are not
  documented anywhere.
- **VAL-005 (surviving content).** `docker/docker-compose.test.yml` does interpolate, but only
  for the three host-port variables. It has **no** credential interpolation. Consequence for this
  block: none — nothing in the test compose is at risk from a pattern change, because the test
  compose reads its env file from the host, not from the build context. Do not reference the test
  compose in `.dockerignore` comments.

### Architectural constraints

- R12: no `print()`, English-only comments, no new dependency, no Alembic, no frontend.
- **No image-content change.** The exclusion set must not shrink what any `COPY` instruction can
  read. Every `COPY` in the tree is selective; the Planner verified them all:
  `docker/Dockerfile` copies `frontend/package*.json`, `frontend/`, `pyproject.toml`, `uv.lock`,
  `README.md`, `src/`, `alembic/`, `alembic.ini`, `tests/`, and one `--from=` stage copy;
  `docker/Dockerfile.frontend.dev` copies `frontend/package*.json` and `frontend/`. None names
  an env file, `backups/`, `.ai/`, or a `*.dump` path. The Implementor must re-verify this rather
  than trust the Planner.
- **Do not drop `!README.md`.** It is the negation that keeps `README.md` in the context for the
  three `COPY pyproject.toml uv.lock README.md ./` layers. It lives in the earlier `*.md` block
  and is unaffected by this change, but it must still be present afterwards.
- No `.env*` file exists under `frontend/`, so the recursive pattern cannot change what
  `COPY frontend/ ./` delivers. The Implementor must confirm this before the probe build.

### Verification

1. **Static precondition.** Enumerate every `COPY`/`ADD` in `docker/Dockerfile` and
   `docker/Dockerfile.frontend.dev` and confirm none names a path matched by the new patterns.
2. **Build-context probe.** Do **not** build the real image and do **not** read a real secret
   into the context. Instead build a throwaway probe stage whose only instruction is `COPY . /ctx`
   and whose `RUN` reports whether each sensitive path is present in the context. Write the probe
   Dockerfile **outside the repository** (e.g. under `$env:TEMP`) and pass it with `--file`, so
   no new file appears in the repository:

   ```powershell
   $probe = Join-Path $env:TEMP "mkobi-dockerignore-probe.Dockerfile"
   @"
   FROM redis:7.4-alpine
   COPY . /ctx
   RUN for p in .env .env.docker .env.example docker/.env.production docker/.env.development docker/.env.example .ai/mcp/.env .kilo backups; do \
         if [ -e "/ctx/$p" ]; then echo "IN_CONTEXT: $p"; else echo "EXCLUDED:  $p"; fi; done
   "@ | Set-Content -LiteralPath $probe
   docker build --file $probe --output=type=cacheonly --no-cache --progress=plain .
   Remove-Item -LiteralPath $probe
   ```

   Every path listed must print `EXCLUDED:`. `docker build` exits non-zero only on a real build
   failure, so the assertion is on the `RUN` output, not the exit code.
3. **Regression gate (R11).** `.\Makefile.ps1 test-select tests/test_config.py -q` → 88 passed or
   better. `uv run ruff check` / `uv run mypy` are **not applicable** to this block (no Python
   file is touched) — record them as N/A rather than skipping silently.
4. **Post-build image smoke (optional, if the dev stack is already up).** `.\Makefile.ps1 restart`
   followed by `.\Makefile.ps1 logs app` must show a normal boot. Note that the probe build above
   uses `--no-cache` and does not touch the dev images.

### Risks and rollback

| Risk | Mitigation |
| ---- | ---------- |
| A new pattern silently removes a path a `COPY` depends on → image build breaks at B2/B3 time, far from B1. | Verification steps 1 and 2 are mandatory; the `COPY` enumeration is the gate. |
| Build cache invalidation: changing `.dockerignore` invalidates every layer of the dev images, so the next `.\Makefile.ps1 up` is a full rebuild. | Expected and harmless. Time-box it; do not "fix" it by narrowing the patterns. |
| Docker's last-match-wins ordering is disturbed if the block is moved. | Edit in place; do not reorder. |
| The `**/` pattern is interpreted differently by an older BuildKit. | The probe build runs the *same* builder that the project uses, so a mismatch fails loudly in step 2. |

**Rollback:** the entire block is one file. `git restore .dockerignore` restores the previous
behaviour with no other dependency, and no other block's change depends on the new patterns.

### Out of scope for this block

- Any Dockerfile change.
- Any change to what the containers *receive* at runtime (that is B2 and B4).
- Enumerating or documenting the contents of `.ai/mcp/.env` (R7 / VAL-006).
- Deciding the fate of any `*.md` documentation of the build context.

### Agent requirement

- **Auditor — not required.** Single file, no derived locality, every predicate already verified.
- **Researcher — not required.** The correct pattern set is determined by the repository's own
  file layout; no external fact is needed.
- **Planner — not required.** The block is fully specified below.
- **Validator — not required.** Deterministic, read-only verification with a fixed probe output
  and a fixed test baseline; a Validator would re-read one file and re-run one command.

### Ready-to-use Implementor task

```yaml
id: TSK_01_dockerignore_build_context
title: Extend .dockerignore so no credential env file, dump or audit artefact enters the build context
status: pending
priority: high
depends_on: []
source_reference: .ai/audit/99-validation/02-configuration-secrets-validated-findings.md
source_section: "CFG-005"
description: >
  Replace the four root-anchored env-file patterns in .dockerignore (which match no file
  anywhere in this repository) with a root-anchored plus recursive .env pattern, and add
  exclusions for a *.dump suffix, the backups/ directory and the .ai/ directory. Edit the
  existing "Environment and secrets" block in place; do not move it, because Docker applies the
  last matching pattern and the later *.md / !README.md section must keep precedence.
goals:
  - "No .env / .env.* file at any depth of the repository is present in the Docker build context."
  - "Database dumps, the backups/ directory and the .ai/ directory are excluded."
  - "No image content changes: every COPY instruction still receives what it needs."
  - "No Dockerfile is modified and no new file is added to the repository."
extra_context: |
  RULINGS IN FORCE
  - R7: do not fix audit-artefact defects here. VAL-006's name count for .ai/mcp/.env is 32, not
    33, and was not re-enumerated - therefore write NO number into the comment. Exclude the file
    by pattern; do not describe its contents.
  - R7 / VAL-005: docker-compose.test.yml interpolates only the three host-port variables and no
    credentials. Do not mention the test compose in this file.
  - R10: one commit, explicit `git add .dockerignore` only. Never `git add -A` or `git add .` -
    the working tree carries pre-existing unstaged deletions of tracked .ai/** files.
  - R12: English-only comments, no print(), no new dependency, no Alembic, no frontend.
  - R11: gate is `.\Makefile.ps1 test-select tests/test_config.py -q` (baseline 88 passed).
    ruff and mypy are N/A - no Python file is touched. Record them as N/A.
  Do NOT re-add `.kilo/` or `.idea/` - both are already present earlier in the file under the
  IDE section. Adding them is duplication, not a fix.
files:
  - path: .dockerignore
    targets:
      - type: comment_block
        name: "Environment and secrets - NEVER include in Docker images"
    changes:
      - action: modify
        description: >
          Replace the four root-anchored patterns (.env, .env.example, .env.local, .env.*.local)
          with a root-anchored .env* pattern plus a recursive **/.env* pattern.
      - action: add
        description: >
          Add a *.dump suffix pattern, a backups/ directory pattern and a .ai/ directory
          pattern to the same block.
      - action: modify
        description: >
          Update the block's leading comment to state its purpose. The comment must not contain
          any count of files, names or bytes.
acceptance_criteria:
  - "Every .env-style file in the tree is excluded, including root .env, .env.docker, docker/.env.production, docker/.env.development, docker/.env.example, and any .env under .kilo/ or a nested directory."
  - "backups/ and .ai/ and any *.dump file are excluded from the build context."
  - "Every COPY/ADD instruction in docker/Dockerfile and docker/Dockerfile.frontend.dev still names a path that remains included; the enumeration is recorded in the commit body."
  - "No Dockerfile is modified; no new file is added to the repository (the probe Dockerfile is written outside the repository and deleted)."
  - "The probe build output prints EXCLUDED: for every sensitive path listed in the task."
  - "!README.md is still present, so the three `COPY pyproject.toml uv.lock README.md ./` layers still resolve."
  - ".\\Makefile.ps1 test-select tests/test_config.py -q reports 88 passed or better."
  - "git status --porcelain shows no newly staged .ai/** deletion and no newly added file."
```

---

## B2 — Deployment posture (CFG-001, CFG-006, CFG-004)

### Goal

The base compose file is the production deployment definition, and today it can silently deploy
as something other than production. `ENV` is interpolated with a `production` default, so a
stale `ENV=` line, a wrong `--env-file`, or an unset variable silently selects the tier — and
every production-only control in the application (admin credential rules, JWT rules, CORS
rules, the database-URL password requirement, `debug=true` refusal) is gated on that value. This
block pins the tier, wires the three settings the base compose declares but never supplies
(so the shipped production defaults are true rather than accidental), and stops shipping the
PostgreSQL superuser password to the two services that never use it. It also makes
`docker/.env.production` honest about which of its names are actually read.

### Findings discharged

- **CFG-001** (CRITICAL) — `ENV: ${ENV:-production}` lets the production stack boot as a
  non-production tier.
- **CFG-006** (MEDIUM) — the base compose declares `RATE_LIMITER_FAIL_CLOSED`, `CORS_ORIGINS`,
  `LOGGING__LEVEL`, `UPLOAD__MAX_FILE_SIZE_MB` and `LOGGING__JSON_LOGGING` in
  `docker/.env.production`, but never supplies the last three to any service; the
  documentation's verification command is also structurally incapable of confirming a
  `RATE_LIMITER_FAIL_CLOSED=true` deployment.
- **CFG-004** (MEDIUM) — `DATABASE__ADMIN_USER` and `DATABASE__ADMIN_PASSWORD` (the PostgreSQL
  superuser credential) are shipped to the `app` and `rq-worker` services, which never use them.

### Findings partially discharged

None. CFG-002's documentation half (`docker-compose.yml`'s own comment, and
`docs/11-guides/docker.md`) is routed to the Documentation phase per R9 and does not narrow the
code change.

### Files and semantic code units to touch

| File | Unit |
| ---- | ---- |
| `docker/docker-compose.yml` | the `Usage:` comment block in the file header; the `migrate`, `app` and `rq-worker` service `environment:` mappings; the comment on the `db` service's `POSTGRES_PASSWORD`/`MKOBI_APP_PASSWORD` pair |
| `docker/.env.production` | the `Usage:` comment line; the `ENV` line; the shadowed database/JWT/upload names; the comment that introduces the required-secret block |

`docker/docker-compose.override.yml` is read but **not** modified. `docker/docker-compose.test.yml`
is read but **not** modified. Neither appears in the file list of the source plan.

### Implementation sequence

1. **Pin the tier.** In `docker/docker-compose.yml`, replace the interpolated `ENV` mapping with
   the literal string `production` in the `migrate`, `app` and `rq-worker` services — the three
   services that carry it. Remove the interpolation, not just its default.
2. **Correct the header comment** in the same file so the documented production invocation is
   the one that works from the repository root:
   `docker compose --env-file docker/.env.production -f docker/docker-compose.yml up -d`.
   Leave the development and test invocation lines alone — both compose files declare their own
   project `name`, so those lines are already correct.
3. **Wire the three unsupplied settings.** Add to the `environment:` mapping of **both** `app`
   and `rq-worker`, with these exact defaults so the shipped production posture matches what
   `docker/.env.production` claims:
   - `RATE_LIMITER_FAIL_CLOSED: ${RATE_LIMITER_FAIL_CLOSED:-true}`
   - `UPLOAD__MAX_FILE_SIZE_MB: ${UPLOAD__MAX_FILE_SIZE_MB:-100}`
   - `LOGGING__JSON_LOGGING: ${LOGGING__JSON_LOGGING:-true}`

   Do **not** wire them on `migrate` or `db`. `migrate` runs Alembic only and holds neither
   setting today; adding them there would be a change with no consumer.
4. **Remove the superuser credential from the runtime services.** Delete the
   `DATABASE__ADMIN_USER` and `DATABASE__ADMIN_PASSWORD` entries from the `environment:` mapping
   of `app` and `rq-worker`.
5. **Keep them where they belong.** `DATABASE__ADMIN_*` stays on the `db` and `migrate` services
   untouched. `migrate` genuinely needs `DATABASE__ADMIN_USER`/`DATABASE__ADMIN_PASSWORD` to
   build a `TEST_ADMIN_DATABASE_URL` for the test-database creation path, and `db` needs the
   superuser password to initialise its data directory. Do not touch either service.
6. **`docker/.env.production`.** Four edits, all comment-level or deletion-level:
   - Replace the `Usage:` comment with the repository-root-relative production invocation, the
     same string used in step 2.
   - Convert the `ENV` line into a comment stating that the compose file pins the tier and this
     name is no longer read.
   - Convert each name the compose file hard-codes into a comment saying the compose value wins.
     That set is exactly: `DATABASE__HOST`, `DATABASE__PORT`, `DATABASE__DBNAME`,
     `JWT__ALGORITHM`, `UPLOAD__TEMP_DIR` (all set literally for every service that has them),
     and `UPLOAD__ALLOWED_EXTENSIONS`, `UPLOAD__ALLOWED_MIME_TYPES` (never supplied to any
     container at all — the application defaults and `app.yaml` apply).
   - Leave `CORS_ORIGINS`, `LOGGING__LEVEL`, `UPLOAD__MAX_FILE_SIZE_MB`,
     `LOGGING__JSON_LOGGING` and `RATE_LIMITER_FAIL_CLOSED` as live values. After step 3 these
     five are all genuinely interpolated.
   - Add no new secret. The template must continue to carry no real credential value.

### Corrections carried from R7

- **VAL-008 (surviving content — this changes the block's exit condition).** The remediation is
  correct to leave the dev stack supplying both keys, but "removed from the runtime services" is
  **not** observable in the dev stack, because `docker/docker-compose.override.yml` re-declares
  `DATABASE__ADMIN_USER` and `DATABASE__ADMIN_PASSWORD` for **both** `app` and `rq-worker`. The
  exit condition is therefore stated against the **base file's resolved configuration**, not
  against the running dev containers. The Implementor must not delete the two lines from the
  override file, and must not "verify" the removal by inspecting a dev container — it will still
  show `postgres`.
- **VAL-005 (surviving content).** `docker/docker-compose.test.yml` supplies its own
  `POSTGRES_PASSWORD` and `MKOBI_APP_PASSWORD` and does not rely on the base file's
  interpolation for them. This block does not touch the test compose, and no conclusion in this
  plan may rest on the test compose honouring the base file's `MKOBI_APP_PASSWORD` mapping.
- The dev override declares the development tier in **three** places (`migrate`, `app`,
  `rq-worker`) plus one shared `migrate` block. Do not describe it as declared in a single
  place, and do not consolidate it.

### Architectural constraints

- R12: no `print()`, English-only comments, no new dependency, no Alembic, no frontend.
- **Fail-closed direction (an accepted regression).** After step 1, an operator who intended a
  staging deployment gets a production boot instead. This is the intent of CFG-001 and matches
  the documented production-only staging gate. The Planner swept the tree for a `staging`
  deployment path: the only occurrences are a docstring in `src/mkobi/models/enums.py`, a
  comment in `src/mkobi/config.py`, and a passing test in `tests/test_config.py` that
  constructs `Settings` in-process. No deployment path sets `ENV=staging`.
- **`ENV` is still honoured in the dev stack.** Step 1 only pins the base file. The dev
  override's `ENV: development` is unaffected and the merged result must still be
  `development`.
- **Cross-block ordering.** B2 pins the tier; **B3** then makes the production-gated credential
  predicates real for anyone who deploys this compose file. B2 must not itself tighten a
  credential rule. If B3 is rolled back, the deployment is still pinned and still sound.
- Do not add `DATABASE__ADMIN_*` back to a runtime service "for symmetry" with `db`/`migrate`.
  `db` is a different service with a different credential model.

### Verification

1. **Production tier is pinned, base file alone:**

   ```powershell
   docker compose -f docker/docker-compose.yml --env-file .env config | Select-String -Pattern 'ENV:'
   ```

   Must show `ENV: production` for `migrate`, `app` and `rq-worker` — three occurrences, no
   `${ENV` interpolation. A value of `development` in the root `.env` must be ignored by this
   file.

2. **Dev tier is unaffected (map-merge proof):**

   ```powershell
   .\Makefile.ps1 config | Select-String -Pattern 'ENV:'
   ```

   Must show `ENV: development`. This is the check that the base-file change did not leak through
   the override.

3. **Presence enforcement is unchanged.** Running step 1's command with the root `.env` removed
   from the environment must still fail with exactly the fifteen missing-variable errors the
   Auditor measured, listing `ADMIN_PASSWORD`, `ADMIN_USERNAME`, `DATABASE__PASSWORD`,
   `JWT__SECRET_KEY` and `MKOBI_APP_PASSWORD` among them. The count must not drop.

4. **CFG-004 observable, against the base file's resolved config:**

   ```powershell
   $c = docker compose -f docker/docker-compose.yml --env-file .env config
   # DATABASE__ADMIN_PASSWORD must NOT appear under the app: or rq-worker: sections
   # and MUST still appear under the db: and migrate: sections
   ```

   Assert per service block, not on the whole document. The dev-stack container read is *not*
   a valid check (see VAL-008 above).

5. **The three newly wired names are now interpolated.** In the same resolved config, the `app`
   service's `environment:` block must contain `RATE_LIMITER_FAIL_CLOSED`, `UPLOAD__MAX_FILE_SIZE_MB`
   and `LOGGING__JSON_LOGGING`.

6. **Regression gate (R11).** `.\Makefile.ps1 test-select tests/test_config.py -q` → 88 passed or
   better. `uv run ruff check` / `uv run mypy` are N/A (no Python file touched) — record as N/A.

7. **Optional dev-stack smoke.** If the dev stack is already up: `.\Makefile.ps1 restart` then
   `.\Makefile.ps1 logs app` must show a normal boot. A restart is required because the tier and
   the environment map are read at container start.

### Risks and rollback

| Risk | Mitigation |
| ---- | ---------- |
| A deployment that relied on `ENV=staging` in its env file now boots as production and refuses credentials. | Accepted and intended (CFG-001). The refusal is B3's, not B2's, so B2 alone is reversible. |
| Removing the superuser credential breaks a code path that quietly depended on it. | The Planner verified that `DatabaseSettings.admin_user` / `admin_password` are consumed only by `admin_database_url` and `test_admin_database_url`, and that `DatabaseStarter.recreate_test_database` is gated on the `test` tier or an explicit `recreate_test_db`, which is `false` in the base compose. The base compose's `db` and `migrate` retain the credential. |
| The `migrate` service is left needing a credential that the dev override also supplies, so the two compose files can drift. | Out of scope for this block; recorded in *Known unsettled / unverified*. |
| `docker compose ... config` prints resolved secrets. | Never paste the output into a shared channel or a commit message. Verification step 4 must be run locally and only the presence/absence verdict reported. |
| The `Usage:` comment becomes stale again. | It is listed once in the consolidated documentation list as well, but the source of truth is the compose header, corrected here. |

**Rollback:** every change is inside two tracked files with no cross-file coupling. `git restore
docker/docker-compose.yml docker/.env.production` fully reverts. B3 depends on B2 only in
ordering, not in content, so B3 can proceed after a B2 rollback.

### Out of scope for this block

- Any change to `docker/docker-compose.override.yml` or `docker/docker-compose.test.yml`.
- Any change to the database initialisation scripts under `docker/init-scripts/`.
- Any credential predicate change — that is B3.
- The `docker/.env.development` and `docker/.env.example` templates under `docker/`.
- Rewriting `docs/10-deployment/security-checklist.md` or `docs/11-guides/docker.md` (R9).

### Agent requirement

- **Auditor — not required.** Every service, environment key and template name named here was
  read in full from the two files.
- **Researcher — not required.** The four CFG findings are settled; the remaining work is
  mechanical and the two open choices (pin versus gate; comment-out versus delete the shadowed
  names) were both decided by the Planner on evidence and recorded above.
- **Planner — not required.** Fully specified.
- **Validator — required.** This block changes the definition of the production deployment and
  its verification depends on reading resolved Compose output, which is easy to misread
  (`ENV` appears four times, `DATABASE__ADMIN_PASSWORD` legitimately still appears twice). A
  Validator must independently confirm steps 1, 4 and 5 and state the fail-closed consequence
  in the report.

### Ready-to-use Implementor task

```yaml
id: TSK_02_compose_deployment_posture
title: Pin the production tier, wire the three unsupplied settings, and stop shipping the superuser credential to runtime services
status: pending
priority: high
depends_on:
  - TSK_01_dockerignore_build_context
source_reference: .ai/audit/99-validation/02-configuration-secrets-validated-findings.md
source_section: "CFG-001, CFG-006, CFG-004"
description: >
  In docker/docker-compose.yml, replace the interpolated ENV mapping with the literal
  `production` in the migrate, app and rq-worker services; supply RATE_LIMITER_FAIL_CLOSED
  (default true), UPLOAD__MAX_FILE_SIZE_MB (default 100) and LOGGING__JSON_LOGGING
  (default true) to the app and rq-worker environment mappings; and delete
  DATABASE__ADMIN_USER and DATABASE__ADMIN_PASSWORD from the app and rq-worker environment
  mappings. Correct the file header's production invocation. In docker/.env.production, correct
  the usage comment, comment out the ENV line and the seven names the compose file hard-codes or
  never supplies, and leave the five now-interpolated names as live values.
goals:
  - "The base compose file cannot deploy the stack as a non-production tier."
  - "The three settings docker/.env.production declares are genuinely delivered to the app and rq-worker services."
  - "The PostgreSQL superuser credential is no longer present in the app or rq-worker container environment."
  - "docker/.env.production no longer advertises a name the deployment ignores as a live value."
extra_context: |
  RULINGS IN FORCE
  - R7 / VAL-008 CORRECTION: the dev stack still shows the superuser credential, because
    docker-compose.override.yml re-declares DATABASE__ADMIN_USER and DATABASE__ADMIN_PASSWORD for
    app and rq-worker. Assert the removal against the BASE FILE's resolved config, never against a
    running dev container. Do NOT delete the two lines from the override file.
  - R7 / VAL-005 CORRECTION: docker-compose.test.yml supplies its own POSTGRES_PASSWORD and
    MKOBI_APP_PASSWORD; do not rely on the base file's MKOBI_APP_PASSWORD mapping when reasoning
    about the test stack, and do not modify the test compose.
  - R7: the dev override declares ENV: development in THREE places (migrate, app, rq-worker).
    Do not consolidate it and do not describe it as a single declaration.
  - R10: one commit, explicit `git add docker/docker-compose.yml docker/.env.production` only.
  - R12: English-only comments, no new dependency, no Alembic, no frontend, no change to
    docker-compose.override.yml or docker-compose.test.yml.
  - R11 gate: `.\Makefile.ps1 test-select tests/test_config.py -q` (baseline 88 passed).
    ruff and mypy are N/A - no Python file is touched. Record them as N/A.
  DECIDED, DO NOT RE-OPEN: pin the tier with a literal rather than gating on DEV_STAGING; and
  comment out the shadowed names in docker/.env.production rather than deleting them, so the
  template keeps the operator's information while making the shadowing visible.
  SECURITY NOTE: `docker compose ... config` prints resolved secrets. Never paste its output into
  a commit message, a task file, or a shared channel.
files:
  - path: docker/docker-compose.yml
    targets:
      - type: comment_block
        name: "Usage header"
      - type: service
        name: migrate
      - type: service
        name: app
      - type: service
        name: rq-worker
    changes:
      - action: modify
        description: "Replace `ENV: ${ENV:-production}` with the literal `ENV: production` in migrate, app and rq-worker."
      - action: add
        description: "Add RATE_LIMITER_FAIL_CLOSED (default true), UPLOAD__MAX_FILE_SIZE_MB (default 100) and LOGGING__JSON_LOGGING (default true) to the app and rq-worker environment mappings. Do not add them to migrate or db."
      - action: delete
        description: "Delete DATABASE__ADMIN_USER and DATABASE__ADMIN_PASSWORD from the app and rq-worker environment mappings. Leave the db and migrate services untouched."
      - action: modify
        description: "Correct the header's production invocation to `docker compose --env-file docker/.env.production -f docker/docker-compose.yml up -d`. Leave the development and test invocation lines unchanged."
  - path: docker/.env.production
    targets:
      - type: comment_block
        name: "Usage header"
    changes:
      - action: modify
        description: "Replace the Usage comment with the repository-root-relative production invocation."
      - action: modify
        description: "Convert the ENV line into a comment stating that the compose file pins the tier and this name is not read."
      - action: modify
        description: "Convert DATABASE__HOST, DATABASE__PORT, DATABASE__DBNAME, JWT__ALGORITHM and UPLOAD__TEMP_DIR into comments saying the compose file hard-codes them."
      - action: modify
        description: "Convert UPLOAD__ALLOWED_EXTENSIONS and UPLOAD__ALLOWED_MIME_TYPES into comments stating that no compose service supplies them, so the application defaults and app.yaml apply."
acceptance_criteria:
  - "`docker compose -f docker/docker-compose.yml --env-file .env config` shows ENV: production three times (migrate, app, rq-worker) and no `${ENV` interpolation."
  - "`.\\Makefile.ps1 config` still shows ENV: development - the base-file change does not leak through the override."
  - "With the root .env removed from the environment, the same config command still fails with the fifteen missing-variable errors, including ADMIN_PASSWORD, ADMIN_USERNAME, DATABASE__PASSWORD, JWT__SECRET_KEY and MKOBI_APP_PASSWORD."
  - "The base file's resolved config contains no DATABASE__ADMIN_USER or DATABASE__ADMIN_PASSWORD under the app: or rq-worker: sections, and still contains both under the db: and migrate: sections."
  - "The base file's resolved config for app contains RATE_LIMITER_FAIL_CLOSED, UPLOAD__MAX_FILE_SIZE_MB and LOGGING__JSON_LOGGING."
  - "docker/.env.production still contains no real credential value, and the five interpolated names remain live values."
  - "docker-compose.override.yml and docker-compose.test.yml are unmodified."
  - ".\\Makefile.ps1 test-select tests/test_config.py -q reports 88 passed or better."
  - "git status --porcelain shows no newly staged .ai/** deletion and no newly added file."
```

---

## B3 — Credential predicates (CFG-002, CFG-003, VAL-003)

### Goal

Three defects share one subject: the credential guards. The repository's own
`docker/.env.example` ships `CHANGE_ME_GENERATE_STRONG_PASSWORD` as the admin password, but
that value is not in `WEAK_PASSWORDS` and does not match the exact membership test — so a
production deployment created by copying the shipped template is accepted. The same gap exists
for the database password and the JWT secret. Separately, an empty or whitespace-only value
(`" "` becomes the empty string after the username is split and stripped) is a non-member of
every weak set, so it passes all guards and yields a stack with a one-character admin password.
And the guard that would catch the placeholder at the point of use exists twice, with three
irreducible divergences, so a fix applied to one copy is silently not applied to the other. This
block closes the placeholder and emptiness gaps inside the existing production-gated predicates,
removes the secret value from the two exception messages that currently interpolate it, and
reduces the two guard copies to one.

### Findings discharged

- **CFG-002** (HIGH) — the documented, shipped placeholder family is not rejected in
  production.
- **CFG-003** (HIGH) — empty and whitespace-only admin credentials are accepted in production.
- **VAL-003** (MEDIUM, in scope per R6) — two divergent copies of one credential guard, in
  `src/mkobi/config.py` and `src/mkobi/db/starter.py`, disagreeing on the rejection condition,
  on the username predicate, and on where the credential is read from.

### Findings partially discharged

None. CFG-002's documentation half is routed to the Documentation phase per R9.

### Files and semantic code units to touch

| File | Unit |
| ---- | ---- |
| `src/mkobi/config.py` | module-level constants `WEAK_USERNAMES`, `WEAK_PASSWORDS`, `WEAK_SECRETS`; the shared predicate introduced by the Researcher's decision (D-B3-1); `Settings.validate_admin_credentials`; `Settings.validate_production_credentials`; the `Settings.DATABASE_URL` property |
| `src/mkobi/db/starter.py` | the module-level import of `WEAK_PASSWORDS` and `get_config` from `mkobi.config`; `DatabaseStarter.ensure_admin_user` |
| `tests/test_config.py` | class `TestWeakCredentialDetection`; class `TestProductionCredentialValidation` |
| `tests/test_starter.py` | class `TestEnsureAdminUserPlaceholderCheck` and its single parametrized test method |

Not touched: `DatabaseSettings.validate_admin_password_strength` (its floor is read, not
changed); `JWTSettings.validate_secret_key` (R3 forbids adding a clause there);
`Settings.validate_debug_mode`; `Settings.validate_cors_origins_not_placeholder`;
`Settings._log_security_warnings`; every API route and service.

### REQUIRES Researcher — D-B3-1

**This block cannot start until the Researcher answers D-B3-1.** It is isolated: the answer
determines only *where the shared predicate lives, what its signature is, and whether the
predicate or the caller produces the message text*. No step after step 1 depends on which
option is chosen, and both options produce the same behaviour.

> **Question.** How do `Settings.validate_admin_credentials` and
> `DatabaseStarter.ensure_admin_user` share one guard implementation without creating an
> import cycle, and without duplicating the `WEAK_*` constants?
>
> Facts already established by the Planner, which bound the answer:
> - `src/mkobi/db/starter.py` already imports from `mkobi.config` at module level
>   (`WEAK_PASSWORDS`, `get_config`). That dependency is one-way and load-bearing.
> - `src/mkobi/config.py` does **not** import `starter.py`. A cycle appears only if the shared
>   predicate is placed in `starter.py` and imported into `config.py`.
> - `WEAK_USERNAMES` and `WEAK_PASSWORDS` are each used in six places inside `config.py` and
>   in one place in `starter.py`.
>
> Options to evaluate and pick between:
> - **(a)** A module-level function in `config.py`, imported by `starter.py`. Zero new files,
>   zero new module edges; the sibling predicates already live in that file.
> - **(b)** A new leaf module (for example `src/mkobi/core/credentials.py`) owning the constants
>   and the predicate, with `config.py` re-exporting `WEAK_USERNAMES` / `WEAK_PASSWORDS` for the
>   existing importers. Cleaner per the repository's "small modules" rule; costs one new file
>   and a re-export surface.
> - **(c)** Keep two copies. **Rejected by R6** — two copies *is* VAL-003.
>
> The Researcher must also state the predicate's **return contract**: boolean, or a reason the
> caller turns into a message. That choice determines whether the two call sites can keep their
> distinct, test-asserted message strings (see step 6).

Two sub-questions the Planner has already decided, so the Researcher need not revisit them:

- **Source of truth for the tier inside `ensure_admin_user`:** the injected
  `DatabaseStarterConfig.env`. `src/mkobi/app.py`'s `lifespan` populates it from
  `config.environment`, so in the shipped path the two cannot diverge, and it is the only form
  that makes the class testable. The divergence VAL-003 reports is that *one guard* mixed
  `get_config()` for the credential with the injected value for the tier — the fix is for the
  guard to state its two sources explicitly, not to collapse them.
- **Severity on a weak username at the point of use:** warn, not raise. `Settings` already
  refuses a weak username in production, so raising again at startup is redundant; what matters
  is that the *predicate* and the *condition* agree between the two copies.

### Implementation sequence

1. **Consume the Researcher's answer to D-B3-1.** Introduce the shared predicate exactly as
   described. Do not proceed to step 2 without it.
2. **`Settings.validate_admin_credentials`, production branch.** Inside the existing
   production-gated block, add the new clauses for `admin_password` **in this order**, so the
   existing message text keeps matching its shipped tests:
   - keep the existing exact-set membership test against `WEAK_PASSWORDS`, with its existing
     message, **first**;
   - then a case-insensitive `startswith("change_me")` test;
   - then a `not value.strip()` test (one clause covers both empty and whitespace-only);
   - then a minimum-length test whose floor is **8**, taken from the existing
     `DatabaseSettings.validate_admin_password_strength` floor so the two cannot drift.
   For `admin_username`, add only a `not value.strip()` test. **No length rule** (R4).
3. **`Settings.validate_admin_credentials` message.** De-interpolate the username from the
   rejection message (R5). The message must still contain the substring **`too common`** — two
   shipped tests match on exactly that. Do not change the password branch's wording.
4. **`Settings.validate_production_credentials`, production branch.** For the database password
   and for the JWT secret, add a case-insensitive `startswith("change_me")` test alongside the
   existing exact-set test. **Order matters:** keep the exact-set test first and unchanged, so
   the shipped test whose parameter is `CHANGE_ME` — an exact member of `WEAK_PASSWORDS` — still
   matches its expected message. The new branch gets its own message.
5. **`Settings.DATABASE_URL`.** De-interpolate the password from the message (R5). The Planner
   verified that no shipped test matches this string, so the wording is free. Do **not** change
   the `no_password_prefix` logic, the `WEAK_PASSWORDS` membership test, or the
   `PASSWORD_TOO_LONG` branch.
6. **`DatabaseStarter.ensure_admin_user`.** Route the placeholder and emptiness decisions through
   the shared predicate from step 1. Align the rejection condition on
   `environment == PRODUCTION` — the condition every other guard in `config.py` uses. Align the
   username check on the shared `WEAK_USERNAMES` predicate instead of the local `== "admin"`
   comparison. Keep the message containing the substring **`known placeholder value`**, which the
   shipped test matches. Keep the development warning branch and its message.
7. **`PRODUCTION`, not `!= DEVELOPMENT` (decided — do not re-open).** The source plan's
   remediation text proposes `!= DEVELOPMENT` in the starter copy. That is wrong for this
   repository and would break shipped tests: `Settings.validate_admin_credentials` gates on
   `PRODUCTION` today, and
   `tests/test_config.py::TestProductionCredentialValidation::test_weak_db_password_accepted_in_staging`
   constructs `Settings` with `ENV=staging` and the default admin credentials. Widening the
   config-side gate to `!= DEVELOPMENT` makes that test fail. Both copies therefore gate on
   `PRODUCTION`.
8. **Do not touch `JWTSettings.validate_secret_key`** (R3). It stays unconditional, with only
   the 32-character length floor and the exact `WEAK_SECRETS` membership test. A placeholder
   clause there would reject `CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32` — the value
   `.env.example` and the dev template ship — and would break the two JWT tests that assert
   long test secrets are accepted in the default tier.
9. **Do not ship substring matching** (R2). The Planner found a fifth shipped test beyond the
   four the Auditor listed: `tests/test_config.py::TestSettingsFromEnv::test_load_environment_enum_from_env`
   sets `ADMIN_PASSWORD=testpassword123` with `ENV=production` and asserts that `Settings()`
   constructs. A substring clause against `WEAK_PASSWORDS` rejects it, because the value contains
   both `test` and `password`. The same clause would reject the repository's own root `.env`
   values `test_app_password` and `test_password`.
10. **Tests — `tests/test_starter.py`.** The class is red at baseline: 11 failures, all from one
    parametrized test that constructs `DatabaseStarter()` with the default
    `DatabaseStarterConfig()`, whose `env` is `DEVELOPMENT`, and then expects a refusal the code
    deliberately does not issue in that tier. Fix the **test**, not the production code:
    construct the starter with a `DatabaseStarterConfig` whose `env` is
    `EnvironmentEnum.PRODUCTION`, so the class tests the tier at which the guard refuses. Keep
    all eleven parameters — they then exercise three distinct branches (exact-set members,
    `change_me` prefixes, ordinary weak values) and the class becomes meaningful instead of
    vacuously red. Add a development-tier case asserting that the same weak value **warns and
    proceeds** rather than raising, so the tier gating is pinned rather than assumed.
11. **Tests — `tests/test_config.py`.** In `TestWeakCredentialDetection` add: a production case
    rejecting the shipped `CHANGE_ME_GENERATE_STRONG_PASSWORD` family; production cases
    rejecting an empty and a whitespace-only `ADMIN_PASSWORD` and an empty `ADMIN_USERNAME`; and
    a case asserting the rejection message contains neither the submitted value nor a substring
    of it. In `TestProductionCredentialValidation` add: a production case rejecting a
    `CHANGE_ME_`-prefixed `DATABASE__PASSWORD` that is not an exact weak member, and a
    development-tier case pinning that `CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32` is still
    accepted as a JWT secret (the R3 decision made executable). Add one explicit regression case
    asserting a legitimate credential that merely *contains* a weak word is still accepted in
    production — the R2 decision made executable, and the test that fails if a later change
    re-introduces substring matching.

### Architectural constraints

- R12: no `print()`, English-only comments and docstrings, no new dependency, no Alembic, no
  frontend, no `StrEnum` unless the Researcher's answer introduces a new constant.
- **No import cycle.** `starter.py` may import from `config.py`; `config.py` must not import
  from `starter.py`. Any answer to D-B3-1 that reverses that direction is wrong.
- **Do not move validation out of Pydantic.** Raising `ValueError` inside a Pydantic validator
  is the correct mechanism for this module and never reaches the HTTP/RFC-7807 layer. Do not
  convert these to `AppException` and do not move them to a route.
- **No secret value in any message produced by this block** — that covers both
  de-interpolations required by R5 and every new branch added here.
- **Message text is a test contract.** Five shipped `pytest.raises(match=...)` patterns constrain
  the wording: `too common`; `DATABASE__PASSWORD is a known weak/placeholder value`;
  `JWT secret key (must be at least 32 characters|is too common)`; and
  `known placeholder value`. Changing any of them requires changing the matching test, and the
  Implementor must justify that in the commit body.
- **The tier is now real.** B2 pinned the production compose file to the `production` tier, so
  after B3 the new clauses affect anyone who deploys that file. B2 must not be rolled back after
  B3 lands without also rolling back B3.

### Verification

```powershell
# Per-block gates (R11)
.\Makefile.ps1 test-select tests/test_config.py -q        # baseline 88 passed; target >= 88 plus the new cases
.\Makefile.ps1 test-select tests/test_starter.py -q       # baseline 11 failed; target 11 passed, 0 failed
uv run ruff check src/mkobi/config.py src/mkobi/db/starter.py tests/test_config.py tests/test_starter.py
uv run mypy src/mkobi/config.py src/mkobi/db/starter.py
```

Block-specific observable checks:

1. **Placeholder refused in production.** Construct `Settings` in a throwaway process with
   `ENV=production` and `ADMIN_PASSWORD=CHANGE_ME_GENERATE_STRONG_PASSWORD` — the value
   `.env.example` ships — alongside otherwise-valid production credentials. It must raise.
2. **Placeholder still accepted in development.** The same value with `ENV=development` must
   construct. The real check is the dev stack: `.\Makefile.ps1 restart` then `.\Makefile.ps1 logs app`
   must show a normal boot, with the dev container's `ADMIN_PASSWORD` still holding a
   `test`-family value.
3. **Emptiness refused in production.** A single-space `ADMIN_PASSWORD` must raise under
   `ENV=production`; the same value must not raise under `ENV=development`, because that tier
   legitimately permits weak values and the starter's development branch warns.
4. **No secret in any message.** Assert that the exception text for a rejected username and for
   a rejected `DATABASE__PASSWORD` placeholder contains neither the submitted value nor any
   substring of it. This is a shipped test, not a manual inspection.
5. **The two guards agree.** The shared predicate is exercised from both call sites: the starter
   test proves the startup-side refusal, the config tests prove the construction-side refusal,
   and both must call the same predicate symbol.

### Risks and rollback

| Risk | Mitigation |
| ---- | ---------- |
| A message rewording breaks one of the five shipped `match=` patterns. | Steps 3, 4 and 6 state the required substrings explicitly; the per-block test gate catches it immediately. |
| Scope creep into substring matching (R2). | Step 9 names the fifth broken test; step 11 makes the rejection executable as a shipped test. |
| `JWTSettings.validate_secret_key` gains a clause and the dev stack refuses to boot (R3). | Step 8 forbids it; the `CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32` acceptance test in step 11 fails immediately if it happens. |
| The Researcher's chosen shape creates a cycle or a second copy of the constants. | D-B3-1 states the cycle direction and the constants constraint before the answer is accepted. |
| The 11 red starter tests are "fixed" by weakening production code. | Forbidden by project rule 2 and by step 10. The fix is to construct the starter at the tier under test. |
| A deployment that today boots with `CHANGE_ME_*` credentials stops booting. | Intended (CFG-002 / CFG-003). It is confined to the production tier, and B3 is independently revertible. |

**Rollback:** the block is revertible as one commit. Reverting restores the previous acceptance
behaviour; B2's tier pinning remains valid on its own.

### Out of scope for this block

- `JWTSettings` beyond leaving it untouched.
- `Settings.validate_debug_mode`, `Settings.validate_cors_origins_not_placeholder`,
  `Settings._log_security_warnings`, `Settings.validate_temp_password_ttl`.
- `DatabaseSettings` and its `admin_database_url` / `test_admin_database_url` properties.
- Any change to the upload, Redis, logging or charts settings.
- Any documentation file (R9). The `docker/docker-compose.yml` comment about credential
  validation is routed to the Documentation list; the source of truth is the `config.py` change
  made here.

### Agent requirement

- **Auditor — not required.** Every symbol, message string and test class named here was read
  from the working tree by the Planner.
- **Researcher — required.** D-B3-1 is a genuine open choice: two defensible module shapes
  exist and the choice is load-bearing for the file layout and for the shared message contract.
  The Planner will not pick for the Implementor.
- **Planner — not required.** The rest of the block is fully specified.
- **Validator — required.** The block rewrites security predicates whose failure mode is silent
  under-acceptance, and it must simultaneously keep five `match=` patterns and the development
  tier intact. A Validator must confirm R2, R3, R4 and R5 were honoured literally, and must
  confirm the full-suite failure count did not increase from 23.

### Ready-to-use Implementor task

```yaml
id: TSK_03_credential_predicates
title: Close the placeholder and emptiness gaps in the credential guards and collapse the duplicated admin guard
status: blocked
priority: high
blocked_by:
  - TSK_03_research_admin_guard_unification
depends_on:
  - TSK_02_compose_deployment_posture
source_reference: .ai/audit/99-validation/02-configuration-secrets-validated-findings.md
source_section: "CFG-002, CFG-003, VAL-003"
description: >
  Inside the existing production-gated predicates, reject the CHANGE_ME_ placeholder family and
  empty or whitespace credentials; de-interpolate the secret value from the admin-username
  message and from the DATABASE__PASSWORD placeholder message in Settings.DATABASE_URL; and
  reduce the two divergent copies of the admin guard - Settings.validate_admin_credentials and
  DatabaseStarter.ensure_admin_user - to one shared predicate. Fix the eleven red
  TestEnsureAdminUserPlaceholderCheck cases by correcting the test's construction, not the
  production code.
goals:
  - "A production deployment created from the shipped docker/.env.example template is refused."
  - "Empty and whitespace-only admin credentials are refused in production."
  - "No exception message produced by this block contains the rejected secret value."
  - "One guard implementation serves both the configuration authority and the startup consumer, with no import cycle."
  - "tests/test_starter.py::TestEnsureAdminUserPlaceholderCheck is green and meaningful."
extra_context: |
  R2: ship startswith("change_me") case-insensitive plus emptiness and whitespace clauses. DO NOT
  ship substring matching against WEAK_PASSWORDS / WEAK_SECRETS; keep the exact-set membership as
  a backstop. A substring clause breaks a fifth shipped test the audit did not list -
  TestSettingsFromEnv::test_load_environment_enum_from_env sets ADMIN_PASSWORD=testpassword123 with
  ENV=production and asserts Settings() constructs - and would reject the repository's own root
  .env values test_app_password and test_password.
  R3: new clauses go INSIDE the existing production-gated predicates only. Do NOT add a clause to
  JWTSettings::validate_secret_key - it is unconditional, and a placeholder clause there rejects
  CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32 (the shipped dev template value) and breaks the two
  JWT tests that assert long test secrets are accepted in the default tier.
  R4: admin_password = non-empty after strip() plus a minimum length of 8, the existing
  DatabaseSettings::validate_admin_password_strength floor. admin_username = non-empty after
  strip() only; no length rule.
  R5: de-interpolate BOTH the admin-username message in validate_admin_credentials AND the
  DATABASE__PASSWORD placeholder message in the DATABASE_URL property.
  DECIDED, DO NOT RE-OPEN: both guards gate on `environment == PRODUCTION`, not on
  `!= DEVELOPMENT`. The wider gate makes
  TestProductionCredentialValidation::test_weak_db_password_accepted_in_staging fail.
  MESSAGE-TEXT CONTRACTS - five shipped pytest.raises match= patterns depend on them: "too
  common"; "DATABASE__PASSWORD is a known weak/placeholder value"; "JWT secret key (must be at
  least 32 characters|is too common)"; "known placeholder value" in the starter. Keep the
  exact-set check FIRST in every predicate, so a value that is an exact weak member still
  reaches the unchanged message.
  R6 / D-B3-1: the Researcher answer is the FIRST step; do not proceed past step 1 without it.
  Cycle direction: starter.py may import from config.py, never the reverse.
  R12: no print(), English-only comments, no new dependency, no Alembic, no frontend. Do NOT
  convert the ValueError-in-Pydantic mechanism; it is correct and never reaches the HTTP layer.
  R10: one commit, explicit git add of the four paths only.
  R11 gates:
    .\Makefile.ps1 test-select tests/test_config.py -q     baseline 88 passed
    .\Makefile.ps1 test-select tests/test_starter.py -q    baseline 11 failed -> target 11 passed
    uv run ruff check src/mkobi/config.py src/mkobi/db/starter.py tests/test_config.py tests/test_starter.py
    uv run mypy src/mkobi/config.py src/mkobi/db/starter.py
files:
  - path: src/mkobi/config.py
    targets:
      - type: class
        name: Settings
      - type: method
        name: Settings.validate_admin_credentials
      - type: method
        name: Settings.validate_production_credentials
      - type: property
        name: Settings.DATABASE_URL
    changes:
      - action: add
        description: "Introduce the shared credential predicate in the shape the Researcher selects (D-B3-1)."
      - action: modify
        description: "Settings.validate_admin_credentials: keep the exact-set check first, then add a case-insensitive change_me prefix test, a not-stripped() test, and a minimum length of 8 for admin_password. For admin_username add only a not-stripped() test."
      - action: modify
        description: "Settings.validate_admin_credentials: remove the username from the rejection message while keeping the substring 'too common'."
      - action: modify
        description: "Settings.validate_production_credentials: add a case-insensitive change_me prefix test for database.password and jwt.secret_key alongside the unchanged exact-set test, which must stay first."
      - action: modify
        description: "Settings.DATABASE_URL: remove the password from the placeholder message. Leave the no_password_prefix logic, the WEAK_PASSWORDS membership test and the PASSWORD_TOO_LONG branch untouched."
  - path: src/mkobi/db/starter.py
    targets:
      - type: method
        name: DatabaseStarter.ensure_admin_user
    changes:
      - action: modify
        description: "Route the placeholder and emptiness decisions through the shared predicate; gate the refusal on environment == PRODUCTION; replace the local admin_email == 'admin' username check with the shared WEAK_USERNAMES predicate (warn, not raise); update the module-level import of WEAK_PASSWORDS / get_config to match the Researcher's chosen shape. Keep the substring 'known placeholder value' and the development warning branch."
  - path: tests/test_starter.py
    targets:
      - type: class
        name: TestEnsureAdminUserPlaceholderCheck
    changes:
      - action: modify
        description: "Construct the starter with DatabaseStarterConfig(env=EnvironmentEnum.PRODUCTION) instead of the default DEVELOPMENT config, so the eleven parameters exercise the tier at which the guard refuses. Keep all eleven parameters, and add a development-tier case asserting the same weak value warns and proceeds rather than raising."
  - path: tests/test_config.py
    targets:
      - type: class
        name: TestWeakCredentialDetection
      - type: class
        name: TestProductionCredentialValidation
    changes:
      - action: add
        description: "TestWeakCredentialDetection: production rejection of the shipped CHANGE_ME_GENERATE_STRONG_PASSWORD family; production rejection of empty and whitespace-only ADMIN_PASSWORD and of empty ADMIN_USERNAME; a case asserting the rejection message contains neither the submitted value nor a substring of it."
      - action: add
        description: "TestProductionCredentialValidation: production rejection of a CHANGE_ME_-prefixed DATABASE__PASSWORD that is not an exact weak member; a development-tier case pinning that CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32 is still accepted as a JWT secret."
      - action: add
        description: "Add one explicit regression case asserting that a legitimate production credential that merely contains a weak word (testpassword123) is still accepted - the R2 decision made executable."
acceptance_criteria:
  - "Settings under ENV=production refuses ADMIN_PASSWORD=CHANGE_ME_GENERATE_STRONG_PASSWORD and any CHANGE_ME_-prefixed DATABASE__PASSWORD or JWT__SECRET_KEY."
  - "Settings under ENV=development and ENV=staging still accept a CHANGE_ME_ placeholder."
  - "Settings under ENV=production refuses an empty and a whitespace-only ADMIN_PASSWORD and an empty ADMIN_USERNAME; the same values are not refused in development."
  - "No exception message from this block contains the rejected secret value; a shipped test asserts it."
  - "All shipped match= substrings still match: 'too common', 'DATABASE__PASSWORD is a known weak/placeholder value', 'JWT secret key (must be at least 32 characters|is too common)', 'known placeholder value'."
  - "JWTSettings.validate_secret_key is unchanged, and CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32 is still accepted as a JWT secret in the development tier."
  - "There is exactly one guard implementation; starter.py imports it and config.py does not import from starter.py."
  - "DatabaseStarter.ensure_admin_user gates the refusal on environment == PRODUCTION and warns in the other tiers."
  - ".\\Makefile.ps1 test-select tests/test_config.py -q reports at least 88 passed with the new cases; .\\Makefile.ps1 test-select tests/test_starter.py -q reports 0 failed."
  - "uv run ruff check and uv run mypy are clean for the four touched files."
  - "git status --porcelain shows no newly staged .ai/** deletion and no newly added file."
```

---

## B4 — Configuration source scope (CFG-008, CFG-009)

### Goal

The Docker-secrets mechanism is unconditionally broad. `SecretsFileSource.__call__` claims every
environment variable ending in `_FILE` and injects the file's contents under the base name. The
running dev stack already proves the cost: `LOGGING__LOG_FILE` is a path-valued field, so the
custom source resolves an empty path to `.` and tries to read a directory, emitting
`Failed to read secret file` on every dev boot. Worse, a hypothetical
`CORS_ORIGINS_FILE` or `UPLOAD__ALLOWED_EXTENSIONS_FILE` would inject a *string* into a field
pydantic expects to be a list, and the application would abort startup on a configuration point
that has nothing to do with secrets. This block narrows the mechanism to the fields that actually
are secrets, and makes the CORS wildcard refusal reachable — today it exists in two places and
neither of them can fire on a real deployment.

### Findings discharged

- **CFG-008** (MEDIUM) — the `*_FILE` Docker-secrets source captures non-secret fields, is not
  restricted to secret-bearing fields, and cannot be configured.
- **CFG-009** (LOW) — the CORS wildcard refusal is dead code in both of its locations: the
  `create_app` check runs after the settings validator has already dropped every wildcard, and
  the `"*"` entry in the placeholder set can never survive the same filter.

### Findings partially discharged

None. CFG-008's documentation half is routed to the Documentation phase per R9 with a corrected
premise (see below).

### Files and semantic code units to touch

| File | Unit |
| ---- | ---- |
| `src/mkobi/config.py` | class `SecretsFileSource` and its `__call__`; the allow-list the Researcher's answer introduces; `Settings.validate_cors_origins`; the class variable `Settings.CORS_ORIGINS_PLACEHOLDERS` |
| `src/mkobi/app.py` | the wildcard branch inside `create_app` |
| `tests/test_config.py` | class `TestSettingsDockerSecrets`; class `TestCORsOriginUrlValidation`; class `TestCORsOriginsPlaceholderValidation` |

Not touched: `Settings.settings_customise_sources` (its ordering is correct and documented; the
allow-list plugs in behind it); `Settings._log_initialization`; `LoggingSettings`; the upload
settings (that is B5's VAL-002).

### REQUIRES Researcher — D-B4-1

**This block cannot start until the Researcher answers D-B4-1.** The behaviour is settled; only
the *derivation* of the allow-list is open, and the derivation is load-bearing because the
requirement is "not a second hard-coded copy of the field list" — a literal list inside
`SecretsFileSource` would simply relocate the drift.

> **Question.** How should `SecretsFileSource` decide that an `X_FILE` variable names a
> secret-bearing field, in a way derived from the models rather than from a second literal list
> of field names?
>
> Facts already established by the Planner, which bound the answer:
> - The secret-bearing fields are exactly those modelled by `DatabaseSettings`
>   (`password`, `admin_user`, `admin_password`, `redis_password`), `JWTSettings`
>   (`secret_key`) and `RedisSettings` (`password`). The first three model classes are nested
>   under the `database` and `jwt` fields; the fourth is a top-level `Settings` field, so its
>   real environment name is `REDIS_PASSWORD`, **not** `REDIS__PASSWORD`.
> - `DatabaseSettings`, `JWTSettings` and `RedisSettings` all derive from `ConfigModel` and all
>   expose their fields through pydantic's `model_fields`, so the set is derivable by
>   introspection at import time and cannot drift from the models.
> - Whether `Settings` itself should be consulted — which would admit names such as
>   `ADMIN_PASSWORD_FILE` — is **not** settled and is part of the question. Admitting it widens
>   the secret surface to fields that are not modelled as secrets.
>
> Options to evaluate and pick between:
> - **(a)** Derive from `model_fields` of the three secret models, computed once at module import
>   into a `frozenset` of environment names. Zero drift, no new file, no re-export surface.
> - **(b)** Derive at call time from a declarative registry of secret-bearing models, so adding a
>   model is a one-line change. Slightly slower per call, and introduces a registry that could
>   itself drift.
> - **(c)** A literal `frozenset` of the currently valid names. **Rejected by the Planner:** it
>   is exactly the second copy of the field list the requirement forbids.
>
> The Researcher must state the chosen derivation, the exact environment names it produces, and
> whether `Settings`-level names are included.

### Implementation sequence

1. **Consume the Researcher's answer to D-B4-1.** Introduce the allow-list exactly as described.
2. **`SecretsFileSource.__call__`.** Before reading a file, compute the base name of the `_FILE`
   variable and check it against the allow-list. If the base name is not allowed, skip the
   variable entirely and read nothing. Retain the `env_prefix` and `env_nested_delimiter` logic
   and the split-on-`__` normalisation exactly as they are, including the `if not parts[-1]`
   guard.
3. **Log a skip.** When a `*_FILE` name is skipped because its base is not a secret field, log
   the **variable name** at `debug` level, with no value interpolated. That is what turns a
   silent no-op into a diagnosable one. Do not log at warning level: the running dev stack
   already sets `LOGGING__LOG_FILE=""`, and a warning per boot is noise, not signal.
4. **`Settings.validate_cors_origins`.** Make the wildcard refusal reachable. Add a
   `ValidationInfo` parameter to the existing field validator and, **before** filtering, scan
   the input list for a `"*"` entry; when one is present and the already-validated `environment`
   field is `PRODUCTION`, raise a message that names the wildcard explicitly and says how to
   remove it. Keep the existing filter that drops wildcard and non-`http`/`https` entries in
   every other tier, unchanged, so the shipped tests that pass a wildcard in the `test` tier
   still see a clean list.
5. **Remove the two dead copies the now-live check supersedes.** Delete the `"*"` entry from
   `Settings.CORS_ORIGINS_PLACEHOLDERS`, and delete the wildcard branch inside `create_app` in
   `src/mkobi/app.py`. Leaving them is the defect CFG-009 reports: two unreachable controls that
   read as the enforcement point. Keep `create_app`'s other production CORS checks — the
   empty-list refusal, and the `debug` / docs-URL logic — untouched.
6. **Tests — `tests/test_config.py`.** In `TestSettingsDockerSecrets`, add a case in which a
   `_FILE` variable for a non-secret field points at a real file, asserting that the resolved
   field still holds its normal value and that nothing is raised. In `TestCORsOriginUrlValidation`,
   add the production wildcard case (a list containing `"*"` under `ENV=production` raises with a
   message naming the wildcard) and keep the existing non-production wildcard case as is, since
   the filter must survive there. In `TestCORsOriginsPlaceholderValidation`, no change is
   required — it parametrizes only non-wildcard placeholders and must continue to pass.

### Corrections carried from R7

- **VAL-007 (surviving content — the plan's premise was wrong).** The source plan's
  `[DOC-UPDATE]` for this finding points at `docs/06-backend/configuration.md` and describes the
  documented behaviour as misleading. The Planner read that file: the sentence "The custom
  `SecretsFileSource` class scans all environment variables ending with `_FILE`" is an
  **accurate description of the current code**, not an error. So:
  - **Do not** "correct" that sentence to pretend the mechanism is already narrow — it is not,
    until this block lands.
  - The sentence becomes false *after* this block. Rewriting it is a Documentation-phase edit and
    is listed in the consolidated list below.
  - No Implementor edits that file (R9).
- **VAL-006 (surviving content).** The audit report's anchor `logging_config.py:115` for the
  non-JSON format string is **wrong**. The Planner verified that
  `src/mkobi/core/logging_config.py::setup_logging` has no `format` parameter and hard-codes the
  standard formatter string inside its own body. Consequence for this block: **do not open
  `logging_config.py` and do not edit it.** The anchor correction also belongs to B5, where the
  `logging.format` row is decided; it is recorded there too.

### Architectural constraints

- R12: no `print()`, English-only comments and docstrings, no new dependency, no Alembic, no
  frontend.
- **Do not reorder the sources.** `Settings.settings_customise_sources` returns
  `[InitSettingsSource, EnvSettingsSource, SecretsFileSource, DotEnvSettingsSource,
  YamlConfigSettingsSource]`; that is correct and documented. The allow-list is a filter inside
  `SecretsFileSource`, not a new source.
- **Backward compatibility.** `DATABASE__PASSWORD_FILE`, `DATABASE__ADMIN_USER_FILE`,
  `DATABASE__ADMIN_PASSWORD_FILE`, `JWT__SECRET_KEY_FILE` and `REDIS_PASSWORD_FILE` must keep
  working, and `DATABASE__PASSWORD_FILE` must keep outranking `DATABASE__PASSWORD` — that
  precedence is asserted by a shipped test. If the Researcher's derived set does not include
  `REDIS_PASSWORD`, the Researcher must say so explicitly rather than let the Implementor guess.
- **The allow-list must not be a second copy of the field list.** See D-B4-1; option (c) is
  rejected.
- **Do not change `Settings._log_initialization`.** The dev-stack warning disappears as a
  *consequence* of the allow-list, not because the log call was removed.
- **`create_app` keeps its other production CORS checks.** Only the wildcard branch is removed.

### Verification

```powershell
# Per-block gates (R11)
.\Makefile.ps1 test-select tests/test_config.py -q
uv run ruff check src/mkobi/config.py src/mkobi/app.py tests/test_config.py
uv run mypy src/mkobi/config.py src/mkobi/app.py
```

Block-specific observable checks:

1. **The dev-stack warning is gone** — this is the finding's original reproduction. With the dev
   stack up, after a restart the `app` container log must not contain `Failed to read secret file`:

   ```powershell
   .\Makefile.ps1 restart
   docker logs mkobi-app-1 2>&1 | Select-String -Pattern 'Failed to read secret file'
   ```

   No output is the pass condition. Resolve the container name with `.\Makefile.ps1 ps` rather
   than assuming it. A cheaper read-only equivalent, if a restart is not wanted:

   ```powershell
   docker exec mkobi-app-1 python -c "from mkobi.config import SecretsFileSource, Settings; print(sorted(SecretsFileSource(Settings)()))"
   ```

   The printed key list must not contain `logging`.

2. **A non-secret `*_FILE` cannot abort startup.** Point a `_FILE` variable for a list-valued or
   path-valued field at a real file and assert `Settings()` still constructs. Covered by the new
   shipped test in step 6.

3. **The wildcard refusal is reachable.** Under `ENV=production` with otherwise-valid production
   credentials, `CORS_ORIGINS='["*"]'` must raise a message naming the wildcard. Under the
   default `test` tier, the same input must still construct with the wildcard filtered out. Both
   are shipped tests.

4. **Dead code is gone.** `grep` for `"*"` in `Settings.CORS_ORIGINS_PLACEHOLDERS` and for the
   wildcard branch in `create_app` returns nothing.

### Risks and rollback

| Risk | Mitigation |
| ---- | ---------- |
| The derived allow-list omits a real secret name, silently breaking Docker-secrets deployments. | D-B4-1 requires the Researcher to state the exact names produced, and the Implementor must enumerate the derived set into the commit body so a reviewer can compare it against the models by eye. |
| The derived allow-list is too broad, so nothing is actually fixed. | The new shipped test in step 6 fails if a non-secret base is still captured. |
| Reading `environment` inside the CORS field validator does not work — for example if pydantic's `ValidationInfo.data` does not carry it. | The value is shipped through the composed settings model and is provably populated for a sibling field of the same class. If the Implementor finds the data unavailable, they must use a separate `mode="before"` field validator on the same field and state the reason in the commit body; the behaviour and the tests are identical either way. |
| Removing the `create_app` wildcard branch is read as a security regression. | The commit body must state that the refusal moved **into** `Settings.validate_cors_origins`, where it is reachable, and that the removed branch could not fire. |
| The `*_FILE` skip log becomes noisy. | `debug` level only, variable name only, no value. |

**Rollback:** one commit; `git restore` of the three files reverts cleanly. No other block
depends on this change.

### Out of scope for this block

- `Settings._log_initialization` (its message disappears as a consequence, not by deletion).
- `src/mkobi/core/logging_config.py` — do not open it (see the VAL-006 correction).
- `UploadSettings` and `LoggingSettings` field removal — that is B5.
- `docs/06-backend/configuration.md` and every other documentation file (R9).
- Any change to the CORS behaviour in the non-production tiers, which stays as it is today.

### Agent requirement

- **Auditor — not required.** Every symbol, constant and test class named here was read from the
  working tree by the Planner, including the exact field names of the secret models.
- **Researcher — required.** D-B4-1 is a genuine open choice about how the allow-list is
  derived. A hard-coded list would violate the finding's own requirement, and the two derivation
  strategies differ in failure mode as well as in shape.
- **Planner — not required.** The rest of the block is fully specified.
- **Validator — required.** The block removes a security check from one location and installs it
  in another; a Validator must confirm the refusal is genuinely reachable in production and that
  no path exists by which a wildcard reaches a running application.

### Ready-to-use Implementor task

```yaml
id: TSK_04_config_source_scope
title: Restrict the _FILE secrets source to secret-bearing fields and make the CORS wildcard refusal reachable
status: blocked
priority: medium
blocked_by:
  - TSK_04_research_file_source_allowlist
depends_on:
  - TSK_03_credential_predicates
source_reference: .ai/audit/99-validation/02-configuration-secrets-validated-findings.md
source_section: "CFG-008, CFG-009"
description: >
  Restrict SecretsFileSource so a *_FILE variable is honoured only when its base name is a
  secret-bearing field, derived from the models rather than hard-coded, and log each skipped name
  at debug level. Then make the CORS wildcard refusal reachable by raising inside
  Settings.validate_cors_origins when the production tier sees a wildcard, and remove the two
  dead copies the live check supersedes: the '*' entry in
  Settings.CORS_ORIGINS_PLACEHOLDERS and the wildcard branch in create_app.
goals:
  - "A path-valued or list-valued field can no longer be overwritten by a *_FILE variable, so the dev stack stops logging 'Failed to read secret file'."
  - "The Docker-secrets mechanism keeps working for every valid secret name, including DATABASE__PASSWORD_FILE outranking DATABASE__PASSWORD."
  - "A CORS wildcard is refused in production by a check that can actually run."
  - "There is exactly one enforcement point for the wildcard refusal."
extra_context: |
  R7 / VAL-007 CORRECTION - THE PLAN'S PREMISE WAS WRONG. The sentence in
  docs/06-backend/configuration.md ("scans all environment variables ending with _FILE") is an
  accurate description of the CURRENT code, not a documentation error. Do NOT "correct" it to
  claim the mechanism is already narrow. It becomes false only after this block, and the rewrite
  is a Documentation-phase edit. No documentation file is edited here (R9).
  R7 / VAL-006 CORRECTION: the audit anchor logging_config.py:115 is WRONG. setup_logging has no
  `format` parameter and hard-codes the standard formatter string in its own body. Do NOT open or
  edit src/mkobi/core/logging_config.py in this block.
  R12: no print(), English-only comments, no new dependency, no Alembic, no frontend. Do NOT
  touch Settings._log_initialization or Settings.settings_customise_sources.
  DO NOT HARD-CODE A SECOND COPY OF THE FIELD LIST - that is part of what CFG-008 asks for.
  REAL SPELLING WARNING: the Redis password field is currently REDIS_PASSWORD, not
  REDIS__PASSWORD, because RedisSettings is a top-level Settings field rather than a nested
  DatabaseSettings child. If the derived set does not include it, say so explicitly - do not
  guess.
  KEEP create_app's other two production CORS checks (the empty-list refusal, and the
  debug/docs-URL logic) untouched. Remove ONLY the wildcard branch.
  R10: one commit, explicit git add of the three paths only.
  R11 gates:
    .\Makefile.ps1 test-select tests/test_config.py -q     baseline 88 passed
    uv run ruff check src/mkobi/config.py src/mkobi/app.py tests/test_config.py
    uv run mypy src/mkobi/config.py src/mkobi/app.py
files:
  - path: src/mkobi/config.py
    targets:
      - type: class
        name: SecretsFileSource
      - type: method
        name: SecretsFileSource.__call__
      - type: class
        name: Settings
      - type: method
        name: Settings.validate_cors_origins
    changes:
      - action: add
        description: "Introduce the secret-field allow-list in the derivation the Researcher selects (D-B4-1), computed from the models rather than hard-coded. Enumerate the derived set into the commit body."
      - action: modify
        description: "SecretsFileSource.__call__: before reading a file, compute the base name of the *_FILE variable and skip the variable when the base is not in the allow-list. Retain the env_prefix, env_nested_delimiter, split-on-__ and parts[-1] logic unchanged."
      - action: add
        description: "Log each skipped *_FILE variable name at debug level with no value interpolated."
      - action: modify
        description: "Settings.validate_cors_origins: add a ValidationInfo parameter; before the existing filter, scan the input list for a '*' entry and raise a message naming the wildcard when environment is PRODUCTION. Keep the existing wildcard and scheme filter unchanged for every other tier."
      - action: modify
        description: "Delete the '*' entry from Settings.CORS_ORIGINS_PLACEHOLDERS."
  - path: src/mkobi/app.py
    targets:
      - type: function
        name: create_app
    changes:
      - action: delete
        description: "Delete the wildcard branch ('*' in config.cors_origins) from the production CORS block. It can no longer fire, because the settings validator drops every wildcard first, and the live refusal now lives in Settings.validate_cors_origins. Leave the empty-list refusal and the debug/docs-URL logic unchanged."
  - path: tests/test_config.py
    targets:
      - type: class
        name: TestSettingsDockerSecrets
      - type: class
        name: TestCORsOriginUrlValidation
    changes:
      - action: add
        description: "TestSettingsDockerSecrets: a *_FILE variable whose base name is not a secret-bearing field is ignored - the resolved field keeps its normal value and no error is raised."
      - action: add
        description: "TestCORsOriginUrlValidation: under ENV=production a list containing '*' raises with a message naming the wildcard; in the default tier the same input still constructs with the wildcard filtered out. The existing non-production wildcard case stays as is."
acceptance_criteria:
  - "A *_FILE variable for a non-secret field is ignored: no file is read, no exception is raised, and the field keeps its normal value."
  - "DATABASE__PASSWORD_FILE, DATABASE__ADMIN_USER_FILE, DATABASE__ADMIN_PASSWORD_FILE and JWT__SECRET_KEY_FILE keep working, and DATABASE__PASSWORD_FILE still outranks DATABASE__PASSWORD."
  - "The derived allow-list is enumerated in the commit body, and no literal field list exists inside SecretsFileSource."
  - "Each skipped *_FILE name is logged at debug level, with no value interpolated."
  - "The dev stack logs no 'Failed to read secret file' after a restart; the SecretsFileSource key list contains no logging key."
  - "Under ENV=production, CORS_ORIGINS containing '*' raises with a message naming the wildcard; in the test tier the same input constructs with '*' filtered out."
  - "Settings.CORS_ORIGINS_PLACEHOLDERS no longer contains '*', and create_app no longer contains a wildcard branch."
  - "create_app's empty-list CORS refusal and its debug/docs-URL logic are unchanged."
  - "src/mkobi/core/logging_config.py is unmodified; no docs/**/*.md file is modified."
  - ".\\Makefile.ps1 test-select tests/test_config.py -q reports at least 88 passed with the new cases; uv run ruff check and uv run mypy are clean for the three touched files."
  - "git status --porcelain shows no newly staged .ai/** deletion and no newly added file."
```

---

## B5 — Unread and relative configuration (CFG-007, VAL-002)

### Goal

Two related defects. First, seven configuration fields are advertised through `.env.example`,
`app.yaml` and the documentation but read by nothing: a field nobody reads is not configuration,
it is a trap, because an operator who tunes it observes no effect. Second, `app.yaml` pins
`upload.temp_dir` to the relative path `data/tmp_uploads`, so a host-run process resolves it
against whatever the current working directory happens to be and creates it there — while every
container deployment supplies an absolute path, and the field's own constructor already contains
an absolute, platform-specific default that the YAML key silently pre-empts. This block decides
every CFG-007 row (R8), removes the unread ones, and closes the relative-path gap in the way
the code already intends.

### Findings discharged

- **CFG-007** (MEDIUM) — seven configuration fields have no reader: `Settings.host`,
  `Settings.port`, `Settings.load_yaml_config()`, `AppSettings.name`, `AppSettings.version`
  alongside `Settings.app_name`, `LoggingSettings.format`, `upload.temp_dir_prefix`,
  `dashboard.default_items_per_page`, and `app.yaml`'s top-level `env:` key.
- **VAL-002** (MEDIUM, in scope per R6) — a relative `upload.temp_dir` resolves against the
  current working directory, so the directory the application creates is not the directory any
  deployment configured.

### Findings partially discharged

None.

### The CFG-007 decisions (R8 — every row decided)

| Row | Decision | Basis |
| --- | -------- | ----- |
| `Settings.host`, `Settings.port` | **Delete both fields**; delete `HOST` and `PORT` from `.env.example` | Zero readers anywhere. The bind address is a literal in `docker/Dockerfile` and in `docker-compose.override.yml`, and `src/mkobi/main.py` constructs the app without passing one. Intent is not establishable, so R8's default applies. |
| `Settings.load_yaml_config()` | **Delete the method** and the three tests that are its only callers | Its sole purpose is to re-read `app.yaml` for tests that assert the file's contents rather than the application's configuration. It is a test-only API on a production settings class. |
| `AppSettings.name` / `AppSettings.version` vs `Settings.app_name` | **Make `AppSettings` the single owner.** Point `create_app` at `config.app.name` for the FastAPI title and at `config.app.version` for the version; delete `Settings.app_name`; delete `APP_NAME` from `.env.example` | The nested model already exists, already has `app.yaml` keys, and is asserted by a passing test. `Settings.app_name` is a top-level duplicate reachable only by field-name matching against the `APP_NAME` env var. This **removes a name** rather than adding a consumer, and it removes the hard-coded `version="1.0.0"` that no `app.yaml` edit could ever change. |
| `LoggingSettings.format` | **Delete the field and its `app.yaml` key** | `setup_logging` has no `format` parameter. Threading one in would add API surface with zero callers, which the repository's "avoid overengineering" rule forbids. |
| `upload.temp_dir_prefix` | **Delete the field and its `app.yaml` key**; update `test_upload_settings_defaults` | Zero readers in `src/`, `tests/`, `frontend/`, `docker/` and `docs/`. Intent is not establishable — the name suggests per-upload keying that no code implements — so R8's default applies. |
| `dashboard.default_items_per_page` | **REQUIRES Researcher (D-B5-1)**, defaulting to **delete the field and the whole `dashboard:` block** | See D-B5-1. |
| `app.yaml` top-level `env: development` | **Delete the key**; replace its comment with a standalone note that the tier is selected by the `ENV` environment variable | `Settings.environment` declares `alias="ENV"` with no `validation_alias`, so the YAML key resolves to nothing. This is the Auditor's seventh candidate row. The file currently has **no** effective way to set the tier, which is worth stating in the replacement comment. |

### REQUIRES Researcher — D-B5-1

> **Question.** Does `dashboard.default_items_per_page` have a real consumer outside the
> `src/` / `tests/` / `alembic/` sweep the audit performed — in particular a page-size contract
> between the API and `frontend/`?
>
> The Planner already swept the tree: the identifier appears in exactly three places —
> `src/mkobi/config.py` (the field), `src/mkobi/settings/app.yaml` (the key), and two assertions
> in `tests/test_config.py`. A second sweep of `frontend/src` for `page_size`, `pageSize`,
> `per_page`, `perPage`, `items_per_page` and `itemsPerPage` found only hard-coded client-side
> literals in the MUI data grids (`pageSizeOptions={[10, 25, 50]}` with a default of `10` or
> `25`), none of which reads a server-provided default.
>
> **Default if the Researcher finds no consumer:** delete the `DashboardSettings` field and the
> `dashboard:` block from `app.yaml`, and update the two tests in `tests/test_config.py` — the
> YAML-loading case in `TestSettingsFromYaml` and `TestDashboardSettings.test_dashboard_default_items`.
> If a consumer *is* found, the field stays and the block's remaining work is unaffected.

The gate is narrow on purpose: it covers one row. The other six rows and VAL-002 are decided and
are not gated.

### Implementation sequence

1. **Consume the Researcher's answer to D-B5-1** before touching the `dashboard` row. Every other
   step in this block is independent of it.
2. **`Settings.host` / `Settings.port`.** Delete both fields. Delete the `HOST` and `PORT` lines
   from `.env.example`. Leave the `TestSettingsBase.clean_env` prefix tuples alone: the
   `HOST` / `PORT` strings they contain become harmless no-ops, and editing them is churn the
   finding does not require.
3. **`Settings.load_yaml_config()`.** Delete the method. Delete its three test-only callers:
   `TestSettingsFromYaml.test_load_app_name_from_yaml`,
   `TestSettingsFromYaml.test_load_app_version_from_yaml` and
   `TestSettingsProperties.test_load_yaml_config_method`. Remove the now-unused `import yaml`
   at the top of `src/mkobi/config.py` — the Planner verified that `yaml.safe_load` is used
   nowhere else in the file. **Keep `from pathlib import Path`**: it is still used to locate
   `app.yaml` inside `Settings.settings_customise_sources`.
4. **`AppSettings` becomes the single owner of the application name and version.** In
   `src/mkobi/app.py`'s `create_app`, replace the `title` argument with `config.app.name` and the
   hard-coded `version="1.0.0"` with `config.app.version`. Delete the `Settings.app_name` field
   from `src/mkobi/config.py` and delete the `APP_NAME` line from `.env.example`. Keep
   `TestAppSettings.test_app_settings_defaults` as it is — it still passes and becomes a real
   test of the field that now drives the application metadata.
5. **`LoggingSettings.format`.** Delete the field and the `logging.format` key from `app.yaml`.
   Do not touch `src/mkobi/core/logging_config.py` — see the VAL-006 correction below.
6. **`upload.temp_dir_prefix`.** Delete the field and the `app.yaml` key. Remove the
   `temp_dir_prefix` assertion from `TestUploadSettings.test_upload_settings_defaults`.
7. **`app.yaml` top-level `env:` key.** Delete the key. Replace its comment with a standalone
   note stating that the tier is selected by the `ENV` environment variable.
8. **`dashboard.default_items_per_page`.** Per D-B5-1's answer: delete the `DashboardSettings`
   field and the `dashboard:` block from `app.yaml`, and update the two tests named in D-B5-1 —
   **or**, if a consumer is found, change nothing here.
9. **VAL-002 — the relative upload temp directory.** Delete the `upload.temp_dir` key from
   `app.yaml` and delete the `UPLOAD__TEMP_DIR` line from `.env.example`, so the absolute,
   platform-specific default already implemented in `UploadSettings.__init__` becomes the
   resolved value instead of being silently pre-empted. Do **not** edit `UploadSettings.__init__`
   and do **not** add a new guard to `Settings._ensure_upload_dir`; see the constraints below.
10. **Tests — `tests/test_config.py`.** The deletions in steps 2, 3, 6 and 8 remove shipped test
    cases. That reduces the raw test count, which is expected: those cases asserted the existence
    of a field, not the behaviour of the application. Add one replacement case in
    `TestUploadSettings` asserting that the resolved `upload.temp_dir` is an **absolute** path
    when no environment value is supplied — this is the VAL-002 fix made executable, and it fails
    if anyone re-adds a relative `app.yaml` key.

### Corrections carried from R7

- **VAL-006 (surviving content).** The audit report anchors the hard-coded non-JSON formatter
  string at `logging_config.py:115`. That anchor is **wrong**: the string is hard-coded inside
  `setup_logging`'s own body, and `setup_logging` takes no `format` parameter. Step 5 therefore
  deletes the *field*, and no edit to `logging_config.py` is intended or needed. Do not go
  looking for line 115.
- **VAL-008 / VAL-005.** No surviving content reaches this block; they are B2's, and B2's task
  already carries both corrections.
- **VAL-007.** No surviving content reaches this block; the surviving premise correction is
  B4's and the doc item is in the consolidated list.

### Architectural constraints

- R12: no `print()`, English-only comments and docstrings, no new dependency, no Alembic, **no
  frontend change** — note that the `dashboard` row deletes a *server* field and must not trigger
  a matching frontend edit even if the Researcher finds a client-side literal.
- **One coherent naming story after step 4.** `app.name` and `app.version` in `app.yaml` become
  the only source of the application's displayed name and version. The Doc-specialist needs the
  table above to record the change; no Implementor touches the docs.
- **VAL-002 remedy is deletion, not a new guard.** Threading a relative path to an absolute one
  inside `Settings._ensure_upload_dir` would be a third code path for a value that should be
  absolute by construction. After step 9, no shipped source produces a relative
  `upload.temp_dir`; the residual is recorded under *Known unsettled / unverified*.
- **Behaviour change that must be stated in the commit body.** A host-run process that previously
  wrote uploads to `<cwd>/data/tmp_uploads` will now write them under the platform user-data
  directory. That is the field's own documented default, and `docs/11-guides/docker.md` and
  `docs/03-processing/processing-api.md` already describe it as a platformdirs path — so this
  makes the code match the documentation rather than the reverse.
- **Do not remove the `import yaml` line unless the method is actually deleted.** The two are
  one change; splitting them leaves a lint failure.
- **Do not touch `Settings._ensure_upload_dir`.** Its warning path is correct; after step 9 it
  simply stops firing for the shipped configuration.

### Verification

```powershell
# Per-block gates (R11)
.\Makefile.ps1 test-select tests/test_config.py -q
uv run ruff check src/mkobi/config.py src/mkobi/app.py tests/test_config.py
uv run mypy src/mkobi/config.py src/mkobi/app.py
```

Note: the test count will **drop** by the number of deleted cases. The gate is *no failures and
no unintended loss* — the Implementor must enumerate the deleted test method names in the commit
body so the drop is auditable.

Block-specific observable checks:

1. **VAL-002 — the resolved temp dir is absolute.** Construct `Settings` with `UPLOAD__TEMP_DIR`
   unset and confirm the resolved `upload.temp_dir` is absolute and no longer ends in
   `data/tmp_uploads`. Asserted by the new shipped test in step 10 and re-checkable in a
   throwaway process with the working directory moved elsewhere.
2. **No unread field survives.** `grep` `src/mkobi/config.py` and `src/mkobi/app.py` for
   `app_name`, `load_yaml_config`, `temp_dir_prefix`, `default_items_per_page` and `host` /
   `port` field declarations — each must return nothing outside a docstring or a comment. For
   `host` / `port` be careful: the strings appear in `create_app`? No — they do not; verify
   rather than assume, because `main.py` also contains none.
3. **`app.yaml` has no key that resolves to nothing.** For every remaining key in
   `src/mkobi/settings/app.yaml`, confirm the corresponding field exists. The Planner verified
   the removal set: the only non-resolving key today is the top-level `env:`.
4. **The application metadata follows `app.yaml`.** Change nothing, but confirm that
   `create_app` now reads `config.app.name` and `config.app.version`, so a future edit of
   `app.yaml`'s `app:` block changes `/openapi.json`.
5. **Regression gate on the compose path.** `.\Makefile.ps1 test-select tests/test_config.py -q`
   with zero failures, and `uv run ruff check` / `uv run mypy` clean. A dev-stack restart is not
   required by this block, because every compose file supplies `UPLOAD__TEMP_DIR` explicitly.

### Risks and rollback

| Risk | Mitigation |
| ---- | ---------- |
| Deleting `Settings.app_name` breaks an unknown reader. | The Planner swept the whole tree: the only reader is `create_app`'s `title=` argument, and `APP_NAME` appears in no other file. The Implementor must re-run the sweep before deleting. |
| Deleting shipped tests is mistaken for weakening coverage. | Step 10 replaces the coverage: the deleted cases asserted that a field exists, and the new case asserts the behaviour that actually matters (an absolute temp dir). Every deleted test name is listed in the commit body. |
| The host upload temp directory moves and an operator's local run appears to "lose" uploads. | Stated in the commit body as an intended behaviour change that makes the code match the existing documentation. The directory is created on demand, so nothing fails; only the location changes. |
| Deleting `import yaml` while some other path still needs it. | The Planner verified `yaml.safe_load` is used only inside the deleted method. `ruff` catches the inverse error immediately. |
| A `StrEnum` or constant is invented for the deleted rows. | R12: none is needed. The block is pure deletion plus one ownership transfer. |
| The Researcher finds a frontend consumer for `default_items_per_page`, and the Implementor edits the frontend anyway. | R12 forbids frontend changes. The finding stays open for that row and is reported; it is not resolved by editing `frontend/`. |

**Rollback:** one commit, five files. `git restore` reverts cleanly. No other block depends on
this change, and the dev/test stacks are unaffected because every compose file pins
`UPLOAD__TEMP_DIR` explicitly.

### Out of scope for this block

- `src/mkobi/core/logging_config.py` — do not open it (VAL-006 correction).
- `UploadSettings.__init__` and `Settings._ensure_upload_dir` — read, not edited.
- `src/mkobi/settings/app.yaml`'s remaining keys — none is removed.
- `frontend/**` — untouched under R12, even if a client-side literal looks related.
- `docs/06-backend/configuration.md`, `docs/99-reference/run-guide.md` and every other
  documentation file (R9) — the affected statements are listed in the consolidated list below.

### Agent requirement

- **Auditor — not required.** Every field, method, test class, YAML key and dotenv line named
  here was read from the working tree by the Planner, including the two frontend sweeps.
- **Researcher — required.** D-B5-1 is the one row where the Planner cannot decide from the
  tree with certainty: whether a page-size contract exists that the audit's sweep could not see.
  The gate is deliberately narrow so it does not hold up the other six rows.
- **Planner — not required.** Six of the seven CFG-007 rows and the VAL-002 remedy are decided
  and justified above.
- **Validator — required.** The block deletes seven fields and several shipped tests; only an
  independent check can confirm that every deletion was genuinely unread and that no coverage was
  lost silently. The Validator must also confirm the test-count drop matches the enumerated
  deletions.

### Ready-to-use Implementor task

```yaml
id: TSK_05_unread_relative_config
title: Decide every CFG-007 row, delete the unread fields, and make the upload temp dir absolute
status: blocked
priority: medium
blocked_by:
  - TSK_05_research_unread_config_intent
depends_on:
  - TSK_04_config_source_scope
source_reference: .ai/audit/99-validation/02-configuration-secrets-validated-findings.md
source_section: "CFG-007, VAL-002"
description: >
  Delete the six configuration fields that nothing reads (Settings.host, Settings.port,
  Settings.load_yaml_config, LoggingSettings.format, upload.temp_dir_prefix, and the
  app.yaml top-level env: key), transfer ownership of the application name and version from
  Settings.app_name to AppSettings, and resolve the dashboard.default_items_per_page row per the
  Researcher's answer. Then delete the upload.temp_dir key from app.yaml and the
  UPLOAD__TEMP_DIR line from .env.example so the absolute platformdirs default implemented in
  UploadSettings.__init__ is the resolved value, closing VAL-002.
goals:
  - "Every remaining key in app.yaml and .env.example maps to a field that is actually read."
  - "The application name and version have a single owner, and both reach the FastAPI application."
  - "A host-run process resolves upload.temp_dir to an absolute path, not a path relative to the current working directory."
  - "The seven deleted test cases are enumerated so the reduction in test count is auditable."
extra_context: |
  R7 / VAL-006 CORRECTION: the audit anchor logging_config.py:115 is WRONG. setup_logging has no
  `format` parameter and hard-codes the standard formatter string in its own body. Delete the
  LoggingSettings.format FIELD; do not open or edit src/mkobi/core/logging_config.py.
  R8: every CFG-007 row is decided. Rows deleted: Settings.host, Settings.port,
  Settings.load_yaml_config, LoggingSettings.format, upload.temp_dir_prefix, the app.yaml top-level
  `env:` key, and - subject to D-B5-1 - dashboard.default_items_per_page. The app.name /
  app.version / Settings.app_name row is a transfer of ownership, not a deletion of both.
  R6: VAL-002 is IN SCOPE. Remedy = delete the app.yaml `upload.temp_dir` key and the
  `UPLOAD__TEMP_DIR` line from .env.example so UploadSettings.__init__'s platformdirs default
  applies. Do NOT add a guard to Settings._ensure_upload_dir and do NOT edit UploadSettings.
  R7 / VAL-008 and VAL-005 have no surviving content here; their corrections are in TSK_02.
  R12: NO frontend change - not even if the Researcher reports a client-side page-size literal.
  No print(), no new dependency, no Alembic, no invented StrEnum. Keep
  `from pathlib import Path` in config.py (still used to locate app.yaml); remove `import yaml`
  only together with the method that uses it.
  Leave the TestSettingsBase.clean_env prefix tuples alone even though HOST and PORT become
  no-ops - editing them is churn the finding does not require.
  The block's gate is NO FAILURES plus an enumerated list of the deleted test methods; the raw
  test count is expected to DROP and that is correct.
  R10: one commit, explicit git add of the five paths only.
  R11 gates:
    .\Makefile.ps1 test-select tests/test_config.py -q     baseline 88 passed, zero failures after
    uv run ruff check src/mkobi/config.py src/mkobi/app.py tests/test_config.py
    uv run mypy src/mkobi/config.py src/mkobi/app.py
files:
  - path: src/mkobi/config.py
    targets:
      - type: class
        name: Settings
      - type: class
        name: AppSettings
      - type: class
        name: LoggingSettings
      - type: class
        name: DashboardSettings
      - type: class
        name: UploadSettings
      - type: method
        name: Settings.load_yaml_config
    changes:
      - action: delete
        description: "Delete the host and port fields and the load_yaml_config method. Remove the now-unused `import yaml` in the same change; keep `from pathlib import Path`."
      - action: delete
        description: "Delete the app_name field. AppSettings.name and AppSettings.version become the single owner of the application name and version."
      - action: delete
        description: "Delete the LoggingSettings.format field and the UploadSettings.temp_dir_prefix field."
      - action: delete
        description: "Delete the DashboardSettings.default_items_per_page field, per D-B5-1. If the Researcher finds a real consumer, skip this deletion and say so in the commit body."
  - path: src/mkobi/app.py
    targets:
      - type: function
        name: create_app
    changes:
      - action: modify
        description: "Pass config.app.name as the FastAPI title and config.app.version as the version, replacing the hard-coded '1.0.0'."
  - path: src/mkobi/settings/app.yaml
    targets:
      - type: key
        name: "env (top level)"
      - type: key
        name: "logging.format"
      - type: key
        name: "upload.temp_dir"
      - type: key
        name: "upload.temp_dir_prefix"
      - type: key
        name: "dashboard (whole block)"
    changes:
      - action: delete
        description: "Delete the top-level `env: development` key - it resolves to nothing because Settings.environment's alias is ENV - and replace its comment with a standalone note that the tier is selected by the ENV environment variable."
      - action: delete
        description: "Delete the logging.format key and the upload.temp_dir_prefix key."
      - action: delete
        description: "Delete the upload.temp_dir key so the absolute platformdirs default in UploadSettings.__init__ is no longer pre-empted by a relative value."
      - action: delete
        description: "Delete the whole dashboard block, per D-B5-1."
  - path: .env.example
    targets:
      - type: key
        name: "HOST"
      - type: key
        name: "PORT"
      - type: key
        name: "APP_NAME"
      - type: key
        name: "UPLOAD__TEMP_DIR"
    changes:
      - action: delete
        description: "Delete the HOST, PORT, APP_NAME and UPLOAD__TEMP_DIR lines."
  - path: tests/test_config.py
    targets:
      - type: class
        name: TestSettingsFromYaml
      - type: class
        name: TestSettingsProperties
      - type: class
        name: TestUploadSettings
      - type: class
        name: TestDashboardSettings
    changes:
      - action: delete
        description: "Delete test_load_app_name_from_yaml, test_load_app_version_from_yaml (the only two that read app.yaml through load_yaml_config, alongside test_load_yaml_config_method) and test_load_yaml_config_method. Keep test_load_email_blocked_domains_from_yaml, which reads settings.email, not the raw YAML."
      - action: modify
        description: "Remove the temp_dir_prefix assertion from test_upload_settings_defaults. Keep the rest of that test."
      - action: delete
        description: "Per D-B5-1, update test_load_dashboard_default_items_from_yaml and TestDashboardSettings.test_dashboard_default_items to match the dashboard decision."
      - action: add
        description: "TestUploadSettings: assert that the resolved upload.temp_dir is an ABSOLUTE path when UPLOAD__TEMP_DIR is unset - the VAL-002 fix made executable."
acceptance_criteria:
  - "grep finds no field named host or port, no load_yaml_config, no app_name, no temp_dir_prefix, and - per D-B5-1 - no default_items_per_page in src/mkobi/config.py or src/mkobi/app.py."
  - "create_app passes config.app.name and config.app.version to FastAPI; the hard-coded version string is gone."
  - "Every remaining key in src/mkobi/settings/app.yaml maps to an existing field; the top-level `env:` key is gone and is replaced by a comment naming the ENV environment variable."
  - "With UPLOAD__TEMP_DIR unset, the resolved upload.temp_dir is absolute and does not end in data/tmp_uploads; a shipped test asserts it."
  - "Every compose file still supplies UPLOAD__TEMP_DIR explicitly, so no container deployment changes."
  - "src/mkobi/core/logging_config.py is unmodified; no frontend file and no docs/**/*.md file is modified."
  - "The deleted test method names are listed in the commit body and account exactly for the drop in test count."
  - ".\\Makefile.ps1 test-select tests/test_config.py -q reports zero failures; uv run ruff check and uv run mypy are clean for the touched Python files."
  - "git status --porcelain shows no newly staged .ai/** deletion and no newly added file."
```

---

## Consolidated documentation edits (R9)

No Implementor edits any file in this list (R9). They are handed to the Doc-specialist as a
de-duplicated set. Each item names the file, the heading or table the edit targets, and the
**corrected premise** where the source plan's original was wrong.

| # | File | Target | Edit | Corrected premise |
| --- | ---- | ------ | ---- | ----------------- |
| D1 | `docs/06-backend/configuration.md` | `## Environment Variables`, the `ADMIN_PASSWORD` row | Default cell `admin` → `CHANGE_ME_ADMIN_PASSWORD` | None. This is CFG-010 cell 1. The `ADMIN_USERNAME` row's `admin` default is **correct** and must stay. |
| D2 | `docs/06-backend/configuration.md` | `## Environment Variables`, the `CORS_ORIGINS` row | Default cell `[]` → the two origins contributed by `app.yaml`'s `cors_origins` block | None. This is CFG-010 cell 2. |
| D3 | `docs/10-deployment/security-checklist.md` | `## Optional Security Hardening`, the `ADMIN_PASSWORD` row | Default cell `admin` → `CHANGE_ME_ADMIN_PASSWORD` | Same defect as D1, different file. Edit once, in this file, and keep the two consistent. |
| D4 | `docs/06-backend/configuration.md` | `## Production Credential Enforcement` → `### Admin Credentials` | Replace the code snippet, which shows `admin_username == "admin"`, with the real enforcement: membership in `WEAK_USERNAMES` / `WEAK_PASSWORDS` plus, after B3, the `change_me` prefix, emptiness and the length-8 floor on the password. Delete the quoted message `"Default admin credentials are not allowed in production."` — no such message exists in the code. | This is CFG-010 cell 4. The snippet is illustrative, so replace it rather than "fix" it. |
| D5 | `docs/06-backend/configuration.md` | `## Config Source Priority`, row 4 (`app.yaml`) | Name the values `app.yaml` actually contributes that differ from the field defaults. **After B5 that set changes**: `upload.temp_dir` is no longer contributed (the key is deleted), and `app.name` / `app.version` become the single owner of the application metadata. | This is CFG-010's second half, **re-scoped**. State `cors_origins` and `app.name`/`app.version`; do not keep claiming `upload.temp_dir`. Also record that `app.yaml` has no effective way to set the tier — the top-level `env:` key is being deleted because it resolves to nothing. |
| D6 | `docs/06-backend/configuration.md` | `## Secrets Management` → `### Docker Secrets Support`, the paragraph describing `SecretsFileSource` | Rewrite to state the post-B4 behaviour: only `*_FILE` variables whose base name is a secret-bearing field are honoured, and a path- or list-valued field such as `LOGGING__LOG_FILE` is ignored. | **Premise corrected (VAL-007).** The current sentence — "scans all environment variables ending with `_FILE`" — is an *accurate description of the pre-B4 code*, not an error. It becomes false only because of B4. Do not "correct" it as a pre-existing inaccuracy. |
| D7 | `docs/06-backend/configuration.md` | `## Production Credential Enforcement` → `### JWT Secret Key` and `### Database Password` | Reconcile the prose with the post-B3 predicate set (placeholder prefix, emptiness, length floor) alongside the existing production-gated weak-set checks, and with the post-B2 statement that the compose file now pins the tier to `production`. | None. |
| D8 | `docs/10-deployment/security-checklist.md` | `## Docker Compose Production Check` | Replace `docker compose -f docker/docker-compose.yml config --services` with a command that prints the resolved `environment:` map for the `app` service, so the check can actually confirm what the section claims. | None. This is CFG-006's verification-command defect: `--services` prints service names and cannot inspect the environment. |
| D9 | `docs/10-deployment/security-checklist.md` | `## Required Production Variables` | Reword the sentence "Docker Compose will fail to start if unset". After B2 the three newly wired names carry `:-` defaults, so the stack does **not** fail to start when they are absent. | None. |
| D10 | `docs/10-deployment/security-checklist.md` | `## Required Production Variables`, the `DATABASE__PASSWORD` row | Description says "Database password for `mkobi_app` role". In the base compose that name carries the **PostgreSQL superuser** password; the application role's password arrives as `MKOBI_APP_PASSWORD` and is mapped onto `DATABASE__PASSWORD` for `app` and `rq-worker`. | **This row inverts the two roles.** The audit did not report it; the Planner found it while verifying B2. This is the observation the source plan's CFG-006 section missed. |
| D11 | `docs/11-guides/docker.md` | `## Environment Configuration` → `### Required Variables`, the `Security Note` blockquote | Reword: presence is enforced by `${VAR:?}`; strength is enforced by the production-gated predicates; and the compose file now pins `ENV` to `production`, so putting `ENV=staging` in the env file no longer downgrades anything. | None. This is CFG-002's documentation target. |
| D12 | `docs/11-guides/docker.md` | `## Environment Configuration` → `### Which .env File to Use`, the `Note on Development Credentials` blockquote | Fix the internal inconsistency: the blockquote says the resulting `.env` uses `admin@example.com` for both admin variables, but the file it tells the reader to copy (`docker/.env.development`) carries `CHANGE_ME_*` values. | **Re-scoped (VAL-007-style correction).** The source plan blamed `.env.example` for a default that `.env.example` does **not** have. `.env.example` is correct and must not be edited. The defect is entirely inside this one file, in one blockquote. |
| D13 | `docs/11-guides/docker.md` | `### Key Variables` table, the `ENV` row | After B2, `ENV` is a fixed literal in the base compose and is set only by the development override. It is no longer a key variable of the production file. | None. This is the second observation the source plan's CFG-006 section missed. |
| D14 | `docker/docker-compose.yml` (comment, not a `docs/` file) | the `db` service's comment on `POSTGRES_PASSWORD` / `MKOBI_APP_PASSWORD` | Reword so the comment states that `${VAR:?}` enforces presence only, and that credential **strength** is checked by the application at startup when the tier is `production` — which B2 has now made a fact rather than a promise. | None. Execute in **one** place only: either as a comment edit inside B2's Implementor task (R9 permits comments in files a block already edits) **or** by the Doc-specialist. Not both. |
| D15 | `docs/99-reference/run-guide.md` | the `upload.temp_dir` example under the settings block | Remove or re-point the example that shows `temp_dir: "data/tmp_uploads"`. After B5 the key no longer exists in `app.yaml` and the resolved value is an absolute platformdirs path. | None. Not listed in the source plan; found by the Planner while grounding B5. |

**Advisory, not required by R9** — the Doc-specialist decides whether to act:

- `docs/11-guides/docker.md`'s `Key Variables` table lists `RECREATE_TEST_DB`, which
  `docker/.env.example` also declares, but no compose `environment:` block supplies it. Wiring it
  is **not** a CFG finding and is out of this programme's scope; the table entry or the
  `.env.example` entry is the inaccurate one.
- `docs/SPEC.md`'s `Key Design Decisions` section records a Redis/rq-worker decision. B2 changes
  the base compose's `app` / `rq-worker` credential shape. Whether that warrants a
  version-history entry is the Doc-specialist's call.

---

## Deferred — audit-artefact hygiene, not product scope (R7)

None of the following is a defect in the mkobi system. All seven are defects in the audit
artefacts themselves. `C:\py_dev\mkobi\.ai\audit\02-configuration-secrets\findings.md` is
untracked and superseded by the validation file; `.ai/audit/templates/audit-findings.md` is an
audit-phase template explicitly protected by the user's instruction. **Do not fix any of these.**

| ID | One-line rationale |
| -- | ------------------ |
| **VAL-001** | The validation file was written to an untracked path, so the `findings.md` → validation link chain is broken for any reader arriving from a fresh clone. Artefact-hygiene fix, no product consequence. |
| **VAL-004** | The source plan's remediation numbered all ten CFG findings "CRITICAL", contradicting its own impact column, which rates nine of them MEDIUM and CFG-009 LOW. The per-finding entries are still correct; only the summary preamble is wrong. |
| **VAL-005** | The source plan asserts the test compose contains no `${…}` interpolation, contradicting `docker-compose.test.yml`, which interpolates three host-port variables (no credentials). Carried into B2 and B1 as corrections so no conclusion is drawn from the wrong premise. |
| **VAL-006** | The source plan's `logging_config.py:115` anchor does not point at the hard-coded non-JSON formatter string, and its `.ai/mcp/.env` name count is 32, not 33. Carried into B5 and B1 as corrections; the Planner verified both independently. |
| **VAL-007** | The source plan's CFG-008 `[DOC-UPDATE]` calls an accurate description of the current code misleading. Carried into B4 as a correction and into D6/D12 as a re-scoped documentation item. |
| **VAL-008** | The source plan's CFG-004 remediation names `app` and `rq-worker`, but the dev override re-declares both keys, so the removal is only observable against the base file. Carried into B2 and restated as the block's exit condition. |
| **VAL-009** | The source plan's CFG-007 remediation offers an A-or-B choice for `app.name`/`app.version` and for `logging.format` instead of choosing, which is exactly what R8 forbids. Resolved by the Planner's table in B5; nothing remains for the audit artefact. |

---

## Known unsettled / unverified

Carried forward honestly. None of these blocks execution; each is a statement of what is **not**
known.

1. **No production deployment exists to inspect.** The highest-severity items (CFG-001, CFG-002,
   CFG-003, CFG-004, CFG-006) were established against a repository and a running *development*
   stack. B2 and B3 will therefore be verified by reading resolved Compose output and by
   construction, not by observing a production boot refuse to start. The first real production
   deploy after B3 is an unverified event.
2. **The full suite is red at baseline — 23 failed / 963 passed.** Twelve of those failures are
   pre-existing and out of scope: the rate-limiting API-shape drift,
   `tests/test_layouts.py`, `tests/test_pydantic_models.py::test_user_db_valid`, and
   `tests/test_users_api.py`. The Planner did not re-run the suite; the number is
   Auditor-measured. The rule is *do not regress*, and the final validation must list the 12 by
   name so a reader can tell pre-existing failures from new ones.
3. **`.ai/mcp/.env` name count was not re-enumerated.** The Planner carries the corrected count
   of 32 from VAL-006 and instructs B1 not to write a number into `.dockerignore` at all, so
   the count does not affect the change. It remains unverified.
4. **CFG-005's runtime context enumeration was not re-probed.** The Planner substituted a static
   proof: every `COPY`/`ADD` in `docker/Dockerfile` and `docker/Dockerfile.frontend.dev` was read
   and shown to be selective, and no `.env*` file exists under `frontend/`. The B1 Implementor
   still runs the probe build, because a static argument about `COPY` cannot cover a `RUN` step
   or a future build-file change.
5. **The `migrate` service's credential drift is unresolved by design.** `migrate` retains
   `DATABASE__ADMIN_USER` and `DATABASE__ADMIN_PASSWORD` in the base file, and the development
   override supplies a *differently named* `DATABASE__ADMIN_PASSWORD` for the same service. After
   B2 the production stack has no drift; the development stack still does. This is a
   deployment-topology question, not a configuration-surface defect, and no CFG finding covers
   it.
6. **VAL-002's residual is unclosed by design.** After B5 no *shipped* source produces a relative
   `upload.temp_dir`, but an operator who explicitly sets a relative `UPLOAD__TEMP_DIR` still
   gets a working-directory-relative directory, because the block deliberately adds no new guard
   to `Settings._ensure_upload_dir`. The requirement that the value be absolute is recorded in
   D15's neighbourhood instead.
7. **`dashboard.default_items_per_page` remains open until D-B5-1 is answered.** If the
   Researcher finds a real consumer, that single row is not discharged by this programme, because
   resolving it would require a frontend change that R12 forbids.
8. **The dev stack's live credential values were read, not classified.** The root `.env` holds
   `test`-family values today, which is why R2's substring clause is refused; if an operator
   replaces them with a value that a *correctly scoped* placeholder or emptiness clause would
   reject, the development stack stops booting. That is the intended fail-closed direction, but it
   will surprise whoever does it.
9. **The pre-existing unstaged-deletion count is 19, not the 20 stated in R10.** The Planner
   measured `git status --porcelain` directly: 19 entries of the form ` D .ai/...` and 4
   untracked entries (the three audit directories plus this plan file). The rule is unchanged —
   every one of them must stay unstaged — but an Implementor who expects 20 and counts 19 should
   not go looking for the missing one.

---

## Definition of done

- [ ] B1, B2, B3, B4 and B5 each committed exactly once, with explicit `git add` paths, in that
      order, with `"{type}({scope}): {description}"` messages.
- [ ] Three Researcher answers recorded: D-B3-1, D-B4-1, D-B5-1.
- [ ] `.\Makefile.ps1 test-select tests/test_config.py -q` at or above the 88-passed baseline with
      zero failures; `.\Makefile.ps1 test-select tests/test_starter.py -q` at zero failures.
- [ ] `uv run ruff check` and `uv run mypy` clean for every touched path; `.\Makefile.ps1 lint`
      and `.\Makefile.ps1 typecheck` clean overall.
- [ ] Full-suite failure count not greater than the 23-failure baseline, with the 12
      out-of-scope failures named in the final report.
- [ ] `git status --porcelain` shows the pre-existing `.ai/**` deletions still unstaged, the three
      untracked audit directories still untracked, and no new untracked file.
- [ ] Every item in the consolidated documentation list is either applied by the Doc-specialist or
      explicitly waived with a reason.
- [ ] The seven deferred items remain untouched.



