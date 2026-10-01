---
phase: 02-configuration-secrets
executed: 2026-09-30
executor: validator
problems-only: true
findings: 10
by-severity:
  CRITICAL: 1
  HIGH: 3
  MEDIUM: 3
  LOW: 3
---

# Phase 02 — Validated Findings

## Summary

Every one of the ten findings in `.ai/audit/02-configuration-secrets/findings.md` was re-derived from the
executing path, not from its quoted evidence, and all ten are substantiated. The report's two load-bearing
runtime artefacts reproduce exactly: `docker compose -f docker/docker-compose.yml --env-file .env config`
resolves the production file to `ENV: development` across `migrate`, `app` and `rq-worker`, and without
`--env-file` the same command aborts on exactly the 15 named interpolation errors. A `Settings()`
construction under `ENV=production` carrying only the repository's own shipped `CHANGE_ME_*` placeholders
constructs and yields
`postgresql+asyncpg://postgres:CHANGE_ME_GENERATE_STRONG_SECRET@localhost:5432/bidb`, and `ADMIN_PASSWORD`
of `''` and `' '` are both accepted while `JWT__SECRET_KEY=''` is refused. The `.dockerignore` gap is
reproduced byte-for-byte by a fresh probe build, and the running dev stack still shows the superuser
credential in `mkobi-app-1` and the `Failed to read secret file .` warning. All ten bands survive
re-grading against the audited phase's own rubric; no band was raised or lowered, and the two
near-boundary calls are recorded in place. Nine defects in the audit itself were found, four of them
MEDIUM: a front-matter severity tally that contradicts the report's own findings, two true defects the
report's own declared blocks name as evidence and never file, and one block that produced no line of
evidence at all.

Each finding below carries the six fields the shared template mandates, plus one the template does not
mandate and the validation output contract requires: **Verdict**. The template enumerates no disposition
field, which is recorded as VAL-009.

## Findings

### CFG-001 — The production compose file resolves `ENV=development` when given the repository's own `.env`, disabling every production guard

**Severity** — CRITICAL

**Verdict** — confirmed; band upheld at CRITICAL

**Zone** — "1. Settings source precedence, and the variant each running process resolves"

**Observation** — Re-derived from the executing path. `docker/docker-compose.yml:62` (`migrate`), `:95`
(`app`) and `:181` (`rq-worker`) each carry `ENV: ${ENV:-production}`. No `env_file:` key exists anywhere
under `docker/` in any of the three compose files, so the tier is whatever `--env-file` supplies. The
repository-root `.env` — which `.env.example:2` instructs the operator to create, and which
`Makefile.ps1:33-35` passes to every dev command — declares `ENV=development` at `.env:7`, matching
`.env.example:10`. Every guard the finding lists is gated on `EnvironmentEnum.PRODUCTION` and therefore
inert at the resolved tier: `config.py:396`, `:429`, `:450`, `:470`, `:635`, `:641`;
`app.py:78`, `:201`, `:205`, `:220-221`. The asserted cause survives. The report's second claim, that the
invocation documented at `docker/docker-compose.yml:5` cannot start the stack, also survives.

**Evidence** — Reproduced in this environment, exit 0:

```
ENV: development          (x3 — migrate, app, rq-worker)
CORS_ORIGINS: '["http://localhost:3000", "http://localhost:5173"]'
```

Both origins are members of `Settings.CORS_ORIGINS_PLACEHOLDERS` (`config.py:434-440`). The same command
without `--env-file` aborts with exactly 15 `required variable … is missing a value` errors naming
`ADMIN_PASSWORD`, `ADMIN_USERNAME`, `DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD` and `JWT__SECRET_KEY`
across `db`, `migrate`, `app` and `rq-worker` — the count and the set the claim states. Compose's implicit
`.env` lookup resolves against the compose file's own directory (`docker/`), which contains
`.env.development`, `.env.example` and `.env.production` but no `.env`.

**Consequence** — Unchanged and confirmed: the production file, with `read_only: true`, `cap_drop: ALL`
and `no-new-privileges`, starts with the development posture. The five `${VAR:?}` presence checks still
fire, so the downgrade is the failure mode an operator cannot see. One correction to the report's
framing: the claim that `_log_initialization` "states nothing about which guard set that implies" is
accurate, but the tier *is* logged (`config.py:576` logs `env=`), so the information exists and only the
interpretation does not. That weakens the diagnostic, not the finding.

**Recommendation** — Executable as written. The target (`docker-compose.yml:62,95,181`) exists and is
stable; removing the interpolation is a three-line change and every listed guard becomes tier-bound
again. One statement in the recommendation is false and must be corrected before it is applied: it says
to leave "the dev override's `ENV: development` (line 19) as the single place the development tier is
declared". The dev override declares it in **three** places — `docker-compose.override.yml:19`
(`migrate`), `:65` (`app`), `:130` (`rq-worker`). Compose merges `environment:` maps across files rather
than replacing them, so the fix still works for all three dev services; the stated invariant ("a single
place") is wrong and would mislead a reviewer into deleting two of the three. `docker/.env.production:7`
should indeed be replaced by a comment, and the documented invocation at `docker/.env.production:4` is
`docker compose --env-file .env.production -f docker-compose.yml up -d` — correct only from inside
`docker/`, which the recommendation's own rewrite correctly resolves by making both paths repo-relative.

### CFG-002 — Every placeholder token the shipped example env files use passes the production weak-credential guards

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH; one clause of the asserted cause refuted

**Zone** — "9. A guard that runs, reports clean, and examines nothing"

**Observation** — Re-derived. The three prohibited-value tests are exact set membership:
`config.py:402` (`self.admin_password.lower() in WEAK_PASSWORDS`), `config.py:473`
(`db_password.lower() in {p.lower() for p in WEAK_PASSWORDS}`) and `config.py:482`
(`jwt_secret.lower() in {s.lower() for s in JWTSettings.WEAK_SECRETS}`). `WEAK_PASSWORDS`
(`config.py:19-31`) contains `change_me` and `change_me_admin_password` and no entry matching a suffixed
`CHANGE_ME_*` token. The four shipped forms appear verbatim at `.env.example:17,27,66,67,70`,
`docker/.env.development:10,11,15,18,19,22` and `docker/.env.example:10,15,18,19`. The finding survives on
the predicate form.

**Evidence** — Reproduced exactly. Under `ENV=production` with `DATABASE__PASSWORD`,
`ADMIN_USERNAME`, `ADMIN_PASSWORD`, `JWT__SECRET_KEY` and `DATABASE__ADMIN_PASSWORD` all set to the
shipped `CHANGE_ME_*` values and `CORS_ORIGINS` to a non-placeholder origin:

```
ACCEPTED environment=<EnvironmentEnum.PRODUCTION: 'production'>
  DATABASE_URL: postgresql+asyncpg://postgres:CHANGE_ME_GENERATE_STRONG_SECRET@localhost:5432/bidb
```

Membership measured against the two constants: `CHANGE_ME_GENERATE_STRONG_SECRET`,
`CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32`, `CHANGE_ME_GENERATE_STRONG_PASSWORD` and
`CHANGE_ME_ADMIN_USERNAME` all return `False` for both sets; `CHANGE_ME_ADMIN_PASSWORD` returns `True`
for `WEAK_PASSWORDS` and `False` for `WEAK_SECRETS`. The report's table is correct in every cell.

**Consequence** — The finding's second sentence, that "`MKOBI_APP_PASSWORD` … is never subject to any
strength check by construction", is **refuted**. `MKOBI_APP_PASSWORD` is mapped onto `DATABASE__PASSWORD`
for `app` and `rq-worker` at `docker-compose.yml:100,185`, and that field *is* checked — twice, at
`config.py:473` and `config.py:642`. The name is unmodelled; the value is not unguarded, it is guarded by
a predicate that misses. The report's own recommendation concedes this ("needs no new field — once it is
mapped onto `DATABASE__PASSWORD` it is covered"), so the observation and the consequence contradict each
other, and the consequence is the false half. Grading the finding, not the mechanism: the defect survives
intact — a production tier that accepts four attacker-guessable shipped placeholders, silently, because
three guards cannot match the form their own inputs take. HIGH is the right band, on the rubric's own
words ("a validation gate whose body cannot fail").

**Recommendation** — Executable, and no shipped test blocks it. `tests/test_config.py:324-344` pins the
*rejection* of `["admin", "administrator", "root", "test", "user", "admin@example.com"]` and
`["password", "123456", "admin", "secret", "test", "admin@example.com", "CHANGE_ME_ADMIN_PASSWORD"]`;
every one of those still fails under a `startswith("change_me")` predicate, so both tests keep passing.
One ordering hazard the recommendation does not name: the suggested "substring-match against
`WEAK_PASSWORDS`/`WEAK_SECRETS`" widens the predicate well beyond the placeholder problem — it would
newly reject any legitimate credential containing `admin`, `test`, `secret` or `password`, which is a
behaviour change to two credential fields on a live tier. The `startswith`/`empty`/whitespace clauses are
uncontroversial; the substring clause needs its own blast-radius check before it ships. Both `[DOC-UPDATE]`
targets exist and are quoted correctly.

### CFG-003 — `ADMIN_PASSWORD` and `ADMIN_USERNAME` accept empty and whitespace values; there is no emptiness or length predicate on either field

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH (near-boundary recorded, not re-graded)

**Zone** — "3. Guarded preconditions: presence, strength, and whether the refusal is actionable and secret-free"

**Observation** — Re-derived. `Settings.admin_username` and `Settings.admin_password` (`config.py:356-357`)
carry no field validator. Their only production-time test is the membership check at `config.py:397,402`,
which an empty string and a single space both miss. The neighbouring fields do have the predicate the
report names: `JWTSettings.validate_secret_key` (`config.py:201-203`) refuses under 32 characters and
`DatabaseSettings.validate_admin_password_strength` (`config.py:173-176`) refuses under 8. The second
copy of the guard, `DatabaseStarter.ensure_admin_user` (`starter.py:336-341`), re-runs the identical
membership test and therefore also raises nothing on `''` or `' '`. The report's parenthetical
"mirroring `validate_temp_password_ttl` (`config.py:371-387`) in style and placement" resolves correctly.

**Evidence** — Every row of the report's probe table reproduced, in an isolated process per case with the
CWD moved off the repository root so the `.env` dotenv source cannot contribute:

```
ADMIN_PASSWORD absent (code default)         REFUSED   Value error, Admin password is too common.
ADMIN_PASSWORD='' (present, empty)           ACCEPTED  admin_password=''
ADMIN_USERNAME='' (present, empty)           ACCEPTED  admin_username=''
ADMIN_PASSWORD=' ' (whitespace)              ACCEPTED  admin_password=' '
JWT__SECRET_KEY='' (present, empty)          REFUSED   Value error, JWT secret key must be at least 32 characters
DATABASE__PASSWORD='' (present, empty)       ACCEPTED
```

The absence case must be run in a clean process — a probe that reuses one `os.environ` across cases will
report it as accepted, because the previous case's value survives. The report's own table is correct on
all six rows. The disclosure claim is confirmed with the value visible: a `Settings()` built with
`ADMIN_USERNAME=admin@example.com` raises
`Admin username 'admin@example.com' is too common. Please choose a more secure username.`
(`config.py:399`) — a real username interpolated into the startup error text and the container log.

**Consequence** — Confirmed. `starter.py:336` computes `is_weak(" ") == False`, so nothing raises, and
`starter.py:358-366` inserts the bootstrap administrator with `hash_password(" ")`. Compose's
`${ADMIN_PASSWORD:?}` at `docker-compose.yml:110` refuses an empty value, so the reachable mis-set is the
whitespace one. The report's statement that the *identical* mistake on `JWT__SECRET_KEY` or
`DATABASE__ADMIN_PASSWORD` is refused is confirmed by the probe.

**Band call, recorded rather than applied.** The rubric's HIGH band reads "a production control silently
disabled or bypassable, including a validation gate whose body cannot fail", which is exactly this.
The CRITICAL band reads "a signing or credential value that is empty, malformed, or shared with another
variant or process", which the *field* arguably meets — the field accepts an empty value. The CRITICAL
clause is not reached, because the value the system itself supplies is never empty (`config.py:357`),
no shipped artefact supplies an empty one, and the composed deployment's `${ADMIN_PASSWORD:?}` refuses it
outright. HIGH is correct, and it is independently supported by the second half of the same finding:
a real username reaching the error text is "secret values reaching … error paths", which is the rubric's
second HIGH clause. The finding is near the CRITICAL line and a later reader may legitimately re-open it;
nothing in the evidence justifies raising it now.

**Recommendation** — Executable, trivial, and unblocked. A search of `tests/` finds no case that sets
`ADMIN_PASSWORD` or `ADMIN_USERNAME` to an empty or whitespace value, so no shipped test asserts the
current behaviour and no test change is required. Note that the report's own `tests/test_config.py:466-479`
does pin `DATABASE__PASSWORD=""` being accepted at `Settings()` and refused at `DATABASE_URL` — that is
the intended shape and is not affected. Both halves of the recommendation (the emptiness validator and
the de-interpolation of the username) are named with stable targets.

### CFG-004 — The Postgres superuser password is injected into `app` and `rq-worker`, which run as the least-privilege `mkobi_app` role

**Severity** — MEDIUM

**Verdict** — confirmed; band upheld at MEDIUM

**Zone** — "5. Tier divergence: which differences are deliberate, and which are unintended"

**Observation** — Re-derived. `docker-compose.yml:99` and `:184` set `DATABASE__USER: mkobi_app` for `app`
and `rq-worker`; `:102` and `:187` give both the same `DATABASE__ADMIN_PASSWORD: ${DATABASE__PASSWORD:?…}`
that `db` (`:25`) and `migrate` (`:68`) receive. `DatabaseSettings.admin_password` has exactly one
consumer path, `DatabaseStarter.recreate_test_database()` (`starter.py:189-292`), reached only from
`starter.py:184` — `if self._config.env == EnvironmentEnum.TEST or self._config.recreate_test_db`. In
production `env` is `production` and `recreate_test_db` is not set by any compose file, so it resolves
from `app.yaml:16` to `false`. The report's claim about lines `:52-54` documenting the `migrate` need, and
about `starter.py:312` using `render_as_string(hide_password=True)`, both resolve correctly.

**Evidence** — Reproduced against the running dev stack, not asserted:

```
docker exec mkobi-app-1 env  ->  DATABASE__USER=mkobi_app
                                DATABASE__ADMIN_USER=postgres
                                DATABASE__ADMIN_PASSWORD=postgres
docker exec mkobi-rq-worker-1 … get_config()  ->  db.user=mkobi_app  admin_user=postgres
                                admin_pw_set=True  recreate_test_db=False
```

**Consequence** — Confirmed and correctly bounded by the report: a live superuser credential in the
environment of the process that parses untrusted uploaded CSV, unused in production. MEDIUM is right —
the rubric's "material or policy crossing a variant or process boundary" is the exact clause, and the
report's own reasoning for declining CRITICAL (a within-tier boundary crossing, not a value shared across
environments) is sound.

**Recommendation** — Executable, but its safety argument cites the wrong file and must be corrected
before the step is applied. The recommendation offers to leave the test path covered with
"(`docker-compose.test.yml:137-139`, `docker-compose.override.yml:71-72`)". `docker-compose.test.yml:138-139`
is indeed the test path, and it is correct. `docker-compose.override.yml:71-72` is **not** the test path —
it is the *dev* path, and it re-supplies `DATABASE__ADMIN_USER: postgres` and
`DATABASE__ADMIN_PASSWORD: ${DATABASE__ADMIN_PASSWORD:?…}` for `app`, with the same at `:135-136` for
`rq-worker`. After the recommended base-file change the dev stack therefore still receives the superuser
credential, which is exactly what the report's own Appendix B records as present in the running dev
containers today. The production outcome the recommendation targets is unaffected; the exit condition
must name the dev path as the thing that is expected to keep it, or the reader will verify the wrong
stack. See VAL-008.

### CFG-005 — `.dockerignore` does not cover the build context: a database dump and a credential env file ship into every build

**Severity** — HIGH

**Verdict** — confirmed; band upheld at HIGH

**Zone** — "4. Secret provenance, and every surface the material can reach"

**Observation** — Re-derived. All three build services declare `context: ..` (`docker-compose.yml:57,84,172`),
so the context is the whole working tree. `.dockerignore:70-74` lists exactly four environment patterns
(`.env`, `.env.example`, `.env.local`, `.env.*.local`); because a `.dockerignore` pattern without a slash
is anchored at the context root, none of them matches `docker/.env.production`, `docker/.env.development`,
`docker/.env.example` or `.env.docker`. No pattern covers `backups/` or `.ai/`. The version-control side is
covered — `.gitignore:157` (`/.env.*`), `:163` (`.ai/mcp/.env`), `:254` (`backups/`) — and `.gitignore:160-161`
deliberately un-ignores the three `docker/.env.*` files, which is why they are tracked and unexcluded
simultaneously. The report's claim that no image layer receives the material is correct: every `COPY` in
`docker/Dockerfile` (`:15`, `:21`, `:105-106`, `:113-114`, `:134-141`, `:158-159`, `:166`, `:169-170`) is
selective.

**Evidence** — An independent probe build (`FROM redis:7.4-alpine`, `COPY . /ctx`,
`--output=type=cacheonly --no-cache`, nothing written to the repository) reproduces the report's eight
lines and adds two the report did not test:

```
IN_CONTEXT: .env.docker            IN_CONTEXT: backups          EXCLUDED:  .kilo
IN_CONTEXT: .ai/mcp/.env           IN_CONTEXT: .ai/audit        EXCLUDED:  .env
IN_CONTEXT: docker/.env.production EXCLUDED:  docs              EXCLUDED:  .env.example
IN_CONTEXT: docker/.env.development                        EXCLUDED:  frontend/node_modules
IN_CONTEXT: docker/.env.example
```

The dump's table of contents, read with `pg_restore -l` inside `mkobi-db-1` (the artefact was removed from
the container afterwards), lists 13 `TABLE DATA` entries including `public users`, `public dashboards`,
`public aggregated_data`, `public dashboard_access`, `public dashboard_filter_values`, `public graphs`,
`public processing_configs` and `public registration_requests` — the report's list, reproduced exactly.

**Consequence** — Confirmed, with the present material quantified rather than asserted. The development
database the dumps were taken from holds exactly one account — `admin@example.com`, role `admin`, with a
60-character `$2b$12$` hash — and `.env.docker` carries six names with values `postgres`, `mkobi_app`,
`test_secret`, `admin`, `admin` and a localhost origin. `.ai/mcp/.env` carries 32 credential-shaped names
including `DATABASE__PASSWORD`, `DATABASE__ADMIN_PASSWORD`, `JWT__SECRET_KEY`, `ADMIN_PASSWORD` and
`MKOBI_APP_PASSWORD`. So what transits today is a development-tier credential set plus one real password
hash and one dashboard row, on every `docker compose build`, retained in the builder's context store and
any exported cache. The report's grading rationale — not CRITICAL, because the material is development-tier
and the exposure requires read access to the builder rather than to the image — is correct and is stated
honestly. HIGH is upheld on the rubric's effect-and-blast-radius basis, for a mechanism the rubric does
not enumerate; a mechanism absent from an enumerated band is not thereby a lower band, and the effect is
real material leaving the repository to a component outside it on every build, with a trivial and total fix.

**Recommendation** — Executable, and the exit condition is verifiable by the method the report supplies
itself. Two of the seven patterns it proposes are already present (`.kilo/` at `.dockerignore:23` and
`.idea/` at `:21`), and it omits `docs/`, already present at `:55` — harmless redundancy, not a defect.
The one pattern that changes behaviour beyond the credential files is `**/.env*`, which newly excludes the
three tracked `docker/.env.*` templates; nothing in `docker/Dockerfile` copies them, so the change is
inert to the image, and the report's claim that rebuild hashes are unaffected is right for every target.

### CFG-006 — `RATE_LIMITER_FAIL_CLOSED` and `UPLOAD__MAX_FILE_SIZE_MB` are documented production controls that no deployment supplies

**Severity** — MEDIUM

**Verdict** — confirmed; band upheld at MEDIUM

**Zone** — "2. Name universes: what code reads, what the shipped examples declare, and what the deployment supplies"

**Observation** — Re-derived. Because no compose file declares a service-level `env_file:`, `--env-file`
supplies values for `${…}` interpolation only, and a name reaches a container solely if an `environment:`
block lists it. The `app` block is `docker-compose.yml:94-122` and carries exactly 19 keys; neither
`RATE_LIMITER_FAIL_CLOSED` nor `UPLOAD__MAX_FILE_SIZE_MB` is among them, nor is either in the
`rq-worker` block (`:180-199`) or in `docker-compose.override.yml` or `docker-compose.test.yml`. Both are
declared in `docker/.env.production` — `RATE_LIMITER_FAIL_CLOSED=true` at `:38`, `UPLOAD__MAX_FILE_SIZE_MB=100`
at `:33`. The shadowing list is accurate: `DATABASE__HOST`/`__PORT`/`__DBNAME` (`.env.production:17-19`
against `docker-compose.yml:96-98,103`), `JWT__ALGORITHM` (`:22` against `:107`), `UPLOAD__TEMP_DIR` (`:32`
against `:111`), `UPLOAD__ALLOWED_EXTENSIONS`/`UPLOAD__ALLOWED_MIME_TYPES` (`:34-35`, no entry) and
`LOGGING__JSON_LOGGING` (`:29`, no entry). `CORS_ORIGINS` and `LOGGING__LEVEL`, the only two other
`.env.production` values, *are* wired (`:121`, `:122`) and the report correctly does not list them.

**Evidence** — Reproduced in two independent ways. Statically, the container environment of the running
dev stack contains no `RATE_LIMITER_FAIL_CLOSED` and no `UPLOAD__MAX_FILE_SIZE_MB`. Dynamically, the
resolved object inside `mkobi-rq-worker-1` reports `rate_limiter_fail_closed=True` and
`upload_max_mb=100` — which are the *field defaults* at `config.py:366` and `config.py:239`, not the
values the deployment declared. That is the report's central point, established rather than argued: the
pinning is an accident of the default. The documentation targets all resolve — `security-checklist.md:57`
under the "Docker Compose will fail to start if unset" section opened at `:51`, `:76-81`, `:73`, `:86`;
`docs/11-guides/docker.md:449`. The upload rejection path at `src/mkobi/api/routes/upload.py:129-141` and
`:181-195` quotes `config.upload.max_file_size_mb` in both messages, so the client-facing error is
self-consistent exactly as claimed.

**Consequence** — Confirmed, and the report's split of the two names by direction is accurate and
matters: `RATE_LIMITER_FAIL_CLOSED` fails *safe* (the process keeps `True`) and costs only the assurance
the checklist offers, while `UPLOAD__MAX_FILE_SIZE_MB` fails *silently wrong* — an operator who raises it
in `.env.production` to accept larger files still receives `FILE_TOO_LARGE` at 100 MB with a message
quoting the unchanged 100. MEDIUM is the right band on the rubric's own words, "configuration-name drift".

**Recommendation** — Executable. The `app` block has 19 keys at `:94-122`, so the three additions fit
without disturbing anything; `${UPLOAD__MAX_FILE_SIZE_MB:-100}` and `${LOGGING__JSON_LOGGING:-true}`
preserve the current value when absent, which is what the report's claim that the step is inert by
construction depends on, and which is correct. `security-checklist.md:73`'s prescribed verification command
is genuinely incapable of checking what the section tells the operator to verify — `config --services`
prints service names only — so the correction is necessary and not cosmetic. One check the report should
have made and did not: `LOGGING__JSON_LOGGING` is listed as unwired, but `logging_config.py:85` reads
`config.logging.json_logging` at every `setup_logging` call, so wiring it is a behaviour change on a
field that is currently always `True`; the `${…:-true}` default keeps it so, and the risk is nil. That is
an observation, not a correction.

### CFG-007 — Seven declared configuration names are read by nothing

**Severity** — MEDIUM

**Verdict** — confirmed as a finding; its **recommendation is substantiated but unusable**; band upheld at MEDIUM

**Zone** — "8. Assigned, derived and branched configuration that nothing reads"

**Observation** — Re-derived by sweeping `src/`, `tests/` and `alembic/`. `upload.temp_dir_prefix`
appears only at `config.py:238` and `tests/test_config.py:252`. `dashboard.default_items_per_page` only at
`config.py:268` and `tests/test_config.py:120,272`. `Settings.load_yaml_config()` only at `config.py:750`
and `tests/test_config.py:101,108,227,230`. `Settings.app` appears at no call site in `src/`; `app.py:216`
reads the separate `Settings.app_name` field and `app.py:218` hard-codes `version="1.0.0"`, and
`logging_config.py` has no `format` parameter at all — `setup_logging` takes `log_level`, `log_file` and
`json_logging` only, and the non-JSON format string at `logging_config.py:97` is a literal. `Settings.host`
and `Settings.port` are read by nothing: the bind address is a literal in the container command at
`docker/Dockerfile:127,179` and `docker-compose.override.yml:109`, and `main.py` passes no host or port.
Each row of the table is correct, and the three "actively misleading" claims hold — a controlled probe
confirms the fields *do* resolve from the environment (`host=1.2.3.4`, `port=9999`,
`temp_dir_prefix='prefixXYZ'`, `default_items_per_page=77`, `logging.format='CUSTOM'`,
`app.name='fromenv'`) while `Settings.app_name` stayed `'mkobi'`, so the values are assigned and
discarded rather than ignored.

**Evidence** — The grep sweeps above. The report's "Zero occurrences outside `config.py`" claim is
accurate for all five production names. The test references it cites are correct: `test_config.py:98-109`
(`test_load_app_name_from_yaml`, `test_load_app_version_from_yaml`), `:117-120` and its duplicate at
`:269-272`, `:238-242`, `:248-252`. One line anchor in the report is wrong: it places the hard-coded
non-JSON format string at `logging_config.py:115`, which is
`"class": "logging.handlers.RotatingFileHandler"`. The string is at `:97`. See VAL-006.

**Consequence** — Confirmed. The three-name split around the application title and version means neither
`app.name`/`app.version` in `app.yaml` nor `APP_NAME` in `.env.example:43` can change the version reported
in `/openapi.json`; only `Settings.app_name` reaches `app.py:216`. MEDIUM is the rubric's "unread
configuration" verbatim.

**Recommendation** — **Substantiated but unusable**, recorded as such rather than passed over. Every target
it names exists and is stable, and deleting `host`, `port` and `load_yaml_config` is directly actionable.
But for three of its five rows it offers alternatives without choosing — "either point `create_app` at
`config.app.name`/`config.app.version` and drop `Settings.app_name`, or delete the `AppSettings` fields
and keep `APP_NAME`", and "either thread it into `setup_logging` or drop it from `LoggingSettings`" — and
for the remaining two it defers the decision entirely ("need a consumer or removal — investigate intent
before deleting"). Two of those five rows do need intent investigated, which the report is right to say,
but the other three are stated as a choice the reader must make. A recommendation that names no
implementation approach is a distinct outcome from rejection, and it is the outcome here. The report's own
Rollout Safety section correctly identifies the four shipped tests that encode the defect
(`test_config.py:98-109`, `:117-120`/`:269-272`, `:238-242`, `:248-252`) and names `test_priority_order`
(`:172-187`) as vacuous — that claim is confirmed: it sets `JWT__SECRET_KEY_FILE` and asserts the secret
loads, and never creates a `.env`, so it cannot detect a precedence change. Those tests are remediation
blockers for the rows that delete a field, and the report is right to label them blockers rather than
gates.

---

### CFG-008 — `SecretsFileSource` treats `LOGGING__LOG_FILE` as a secret pointer and reads the path it names

**Severity** — LOW

**Verdict** — confirmed; band upheld at LOW; one `[DOC-UPDATE]` premise refuted

**Zone** — "4. Secret provenance, and every surface the material can reach"

**Observation** — Re-derived. `SecretsFileSource.__call__` (`config.py:60-83`) iterates `os.environ` and
acts on **every** name ending in `_FILE`, with no allow-list and no check that the stripped base is a
declared field. `_set_nested_value` (`config.py:34-46`) splits on `__` and lower-cases, so
`LOGGING__LOG_FILE` yields the base `LOGGING__LOG` and is injected as `{"logging": {"log": <contents>}}`.
`LoggingSettings` has no `log` field and the model config carries `extra: "ignore"` (`config.py:527`), so
the value is discarded downstream — but the read has already happened. Both compose files set the variable:
`docker-compose.yml:112,197` to `/app/data/logs/app.log` and `docker-compose.override.yml:82` to `""`.

**Evidence** — Direct invocation of the source, reproduced with the log content as the target file:

```
{'jwt': {'secret_key': 'SENSITIVE LOG LINE …'},
 'logging': {'log': 'SENSITIVE LOG LINE …'},
 'some_unrelated': 'SENSITIVE LOG LINE …'}
```

The `Path("")` case is confirmed against the running stack rather than reasoned: `docker logs mkobi-app-1`
carries `Failed to read secret file .: [Errno 21] Is a directory: '.'` on every start, and
`docker exec mkobi-app-1 printenv LOGGING__LOG_FILE` returns the empty string, so `Path("")` resolves to the
container's working directory. Both of the report's concrete effects are real.

**Consequence** — Confirmed and correctly bounded: a spurious WARNING on every development boot whose
text points an operator at a nonexistent secret file, and an unconditional read of the entire active log
file into memory on every production boot of `app`, `rq-worker` and `migrate`. No secret crosses a
boundary — the value is discarded by `extra: ignore`, which the direct invocation demonstrates. LOW is the
rubric's "undocumented switches" and "explanatory comments that no longer match", and it is right.

**Recommendation** — Executable, and the claim that the `_FILE` tests keep passing is confirmed:
`tests/test_config.py:126-138` uses `DATABASE__PASSWORD_FILE` and `:140-152` uses `JWT__SECRET_KEY_FILE`,
both declared secret fields, so an allow-list keyed on declared secret fields preserves them unchanged.
The `[DOC-UPDATE]` sub-recommendation is **not substantiated as stated**: the report says
`docs/06-backend/configuration.md:83` "describes the scan as a secrets mechanism, with no note that ordinary
`*_FILE` names are captured", but line 83 reads "The custom `SecretsFileSource` class scans **all**
environment variables ending with `_FILE`" — the document states the behaviour exactly and precisely. The
narrower point survives (it does not warn that a path-valued setting such as `LOGGING__LOG_FILE` will be
read), and the sub-recommendation should be re-worded to that. See VAL-007.

### CFG-009 — The CORS wildcard refusal is unreachable: the field validator removes `"*"` before either copy of the guard can see it

**Severity** — LOW

**Verdict** — confirmed; band upheld at LOW

**Zone** — "9. A guard that runs, reports clean, and examines nothing"

**Observation** — Re-derived. `Settings.validate_cors_origins` is a `field_validator` (`config.py:491-515`),
and pydantic runs field validators before every model validator, so it executes ahead of
`validate_cors_origins_not_placeholder` (`config.py:442-460`) and of `create_app`'s checks
(`app.py:201-213`). It admits an origin only when `urlparse(origin).scheme` is `http`/`https` and
`parsed.netloc` is non-empty; `"*"` satisfies neither, so it is dropped with a warning. Two controls
therefore test for a value that can no longer exist: the `"*"` entry in `Settings.CORS_ORIGINS_PLACEHOLDERS`
(`config.py:435`) and the `"*" in config.cors_origins` refusal at `app.py:205-213`. The report is also
right that the model validator is **not** vacuous in general — the other four placeholder entries survive
the field validator, and I confirmed `CORS_ORIGINS='["https://app.example.org"]'` constructs cleanly under
`ENV=production`.

**Evidence** — Reproduced under `ENV=production` with `CORS_ORIGINS='["*"]'`:

```
Invalid CORS origin rejected: '*' (must be http:// or https:// URL)
cors_origins after field validator: []
'*' in cors_origins -> False
Settings() then constructs with environment=production
```

The refusal that actually fires is `app.py:202-204` ("CORS origins must be configured for production"),
which reports a missing value rather than the wildcard the operator configured. The report's reading of
`app.py:202-204` versus `:205-213` is exact.

**Consequence** — Confirmed. Fails closed, so nothing is served with a wildcard policy; what remains is
two dead controls and a misleading diagnostic. The report's statement that
`docs/06-backend/configuration.md:126-129` matches the behaviour that actually fires, so no document is
wrong here, is correct and is the kind of negative finding that should be stated.

**Recommendation** — Executable, trivial, and it names both directions with a preference ("the direction
that preserves operator-facing clarity is the second"). Both targets exist and are stable; moving the
wildcard check ahead of the field validator is a one-block move inside the same file, and deleting the
`"*"` entry is a one-line change. No shipped test pins the wildcard branch — the closest is
`tests/test_config.py`'s CORS class, which asserts origins load from YAML rather than the refusal — so
neither direction is blocked.

### CFG-010 — Four documentation defaults no longer match the code

**Severity** — LOW

**Verdict** — confirmed (three of four rows); one row **not substantiated as stated**; band upheld at LOW

**Zone** — "10. Defaults that are wrong for the environment the process is deployed into"

**Observation** — Three of the four rows verified exactly. `docs/06-backend/configuration.md:61` asserts
`ADMIN_PASSWORD` defaults to `admin`; `config.py:357` sets `CHANGE_ME_ADMIN_PASSWORD`.
`docs/06-backend/configuration.md:66` asserts `CORS_ORIGINS` defaults to `[]`; `app.yaml:86-88` supplies
`http://localhost:3000` and `http://localhost:5173` at a priority above the field default
`config.py:353`. `docs/06-backend/configuration.md:103-108` shows
`if environment == "production" and (admin_username == "admin" or admin_password == "admin")`; the code at
`config.py:397,402` is a membership test against `WEAK_USERNAMES` / `WEAK_PASSWORDS`, and the probe
confirms the only message the shipped `admin@example.com` can produce is the `WEAK_USERNAMES` branch,
which the documented `==` snippet cannot generate.

**Evidence** — Row 3 is **not substantiated as stated**. The claim is that
`docs/11-guides/docker.md:416-419` ("the default `.env` uses `admin@example.com` for both") is contradicted
by `.env.example:66-67`, which uses `CHANGE_ME_ADMIN_USERNAME` / `CHANGE_ME_GENERATE_STRONG_PASSWORD`. The
document does not name `.env.example`; it names `.env`. The repository-root `.env` — untracked, created
locally — does carry `ADMIN_USERNAME=admin@example.com` and `ADMIN_PASSWORD=admin@example.com` at `:17-18`,
so the sentence is accurate about the file it names. What it is inaccurate about is the flow the same
document prescribes twelve lines earlier at `docker.md:406` (`cp docker/.env.development docker/.env`),
which produces a `.env` carrying `CHANGE_ME_*` values (`docker/.env.development:18-19`). The row is
therefore arguably right for the wrong reason: the defect is an internal inconsistency in `docker.md`
between its own prescribed creation step and its description of the result, not a mismatch against
`.env.example`. It must be re-worded before it is actioned, because a reader who takes the finding at
face value will edit a line that is correct as written.

**Consequence** — Confirmed for the three verified rows, and the report is right about why they matter:
both misstatements are the kind an operator uses to decide whether a guard has already fired, which is
precisely the question CFG-002 and CFG-003 turn on. LOW is the rubric's "explanatory comments that no
longer match the value they describe", verbatim.

**Recommendation** — Executable and trivial for the three verified cells, all four of which resolve at
the cited lines. The second half — adding a row to `docs/06-backend/configuration.md:37`'s priority table
naming the two values `app.yaml` contributes that differ from the field defaults (`cors_origins`,
`upload.temp_dir`) — is confirmed against `app.yaml:34` and `:86-88`, and both are the source of two of
the three verified drifts, so it closes the loop the report intends. The row-3 cell must be re-scoped to
the `docker.md:406` / `:416-419` inconsistency before it is edited.

---

## Validation-Level Findings
Nine defects in the audit, graded on the validation taxonomy — a different scale from the findings above,
and never mixed with it. These are not defects in the mkobi system.

### VAL-001 — The front-matter severity tally contradicts the report's own per-finding bands, and the Summary repeats the stale classification

**Severity** — MEDIUM

**Zone** — "8. The Shared Findings Template as a Controlled Artefact"

**Observation** — The front matter declares `by-severity: CRITICAL: 1, HIGH: 2, MEDIUM: 4, LOW: 3`, summing
to 10. The per-finding `**Severity**` lines carry CFG-001 CRITICAL; CFG-002, CFG-003 and CFG-005 HIGH;
CFG-004, CFG-006 and CFG-007 MEDIUM; CFG-008, CFG-009 and CFG-010 LOW. The true tally is
**1 / 3 / 3 / 3**. The Summary compounds it: "The phase also produced 4 MEDIUM (a superuser credential
crossing into least-privilege processes, build-context material outside `.dockerignore`, documented
production controls no deployment supplies, and seven unread configuration names)" — of those four listed
items, build-context material is CFG-005, which the body grades HIGH. The pattern is coherent and
identifiable: the tally and the Summary were written when CFG-005 was MEDIUM, and the finding was later
re-graded to HIGH in its own body without the two aggregates being brought back into agreement.

**Evidence** — Line-by-line comparison of `.ai/audit/02-configuration-secrets/findings.md:7-11` against
the ten `**Severity**` lines at `:43`, `:107`, `:168`, `:218`, `:258`, `:313`, `:364`, `:410`, `:456`,
`:503`, plus the Summary sentence at `:35-37`. The auditor's own board post to the coordinator carried the
same stale "CRITICAL + 2 HIGH".

**Consequence** — A reader triaging by the front-matter table sends CFG-005 to the MEDIUM queue. It is a
HIGH, and under this validation's HIGH band — "a true finding … graded below what its own rubric implies, so
work that must be done never reaches the roadmap" — the miscount is the mechanism by which a build-context
defect carrying a database dump and two live credential files is deprioritised.

**Recommendation** — Correct `by-severity` to `CRITICAL: 1, HIGH: 3, MEDIUM: 3, LOW: 3` and re-word the
Summary sentence to exclude CFG-005 from the MEDIUM list. One line each; the finding bodies need no change.

### VAL-002 — A MEDIUM defect the phase's own block 8 names as evidence was identified in passing and never filed

**Severity** — MEDIUM

**Zone** — "6. Cross-Phase Conflict, Ownership and Merge" (recorded as a coverage gap; owned by the audited phase)

**Observation** — Phase 02's block 8 requires evidence of "a path that resolves relative to the process
working directory while every deployment supplies an absolute one", and its own severity rubric lists the
same mechanism in the MEDIUM band verbatim: "a value resolving against a different root than every
deployment supplies". The defect is present and the report saw it: CFG-010's recommendation asks to add an
`app.yaml` row to `docs/06-backend/configuration.md:37` naming the two values `app.yaml` contributes that
differ from the field defaults, one of which is `upload.temp_dir`. That value is `app.yaml:34`,
`temp_dir: "data/tmp_uploads"` — relative — and every container deployment supplies an absolute path
(`docker-compose.yml:111,196`; the dev override inherits `:111` for `app` through Compose's map merge).
`Settings.__init__` calls `_ensure_upload_dir` (`config.py:570`, `:584-587`), which
`Path(self.upload.temp_dir).mkdir(parents=True, exist_ok=True)` — so the relative root is not merely
resolved differently, it is **created**, at whatever directory the process happens to start in. It was
mentioned as a documentation nicety and not filed as a defect.

**Evidence** — Reproduced in an isolated process with `UPLOAD__TEMP_DIR` unset and the CWD moved off the
repository root:

```
upload.temp_dir = 'data/tmp_uploads'  | absolute? False
resolved against CWD C:\…\val_cfg_z137ldiw -> C:\…\val_cfg_z137ldiw\data\tmp_uploads
created by _ensure_upload_dir -> True
```

**Consequence** — A MEDIUM defect the rubric names in its own words never reaches the roadmap, so the
reader is left believing the configuration surface is fully swept. The exposure is a host-run application
using a different data root from the same checkout depending on the working directory, and a directory
tree created outside the repository in whatever CWD a supervisor chose. `Makefile.ps1` runs
`docker compose exec` rather than a host uvicorn, so no shipped path exercises it today; the blast radius
is bounded accordingly, which is why MEDIUM and not HIGH.

**Recommendation** — File this as a phase-02 block-8 finding and add it to the roadmap. It is not this
validation's to file, and this validation does not modify the audited report.

### VAL-003 — Two copies of the bootstrap-admin guard disagree on the condition and on the username predicate, and the divergence is not recorded

**Severity** — MEDIUM

**Zone** — "6. Cross-Phase Conflict, Ownership and Merge" (recorded as a coverage gap; owned by the audited phase)

**Observation** — Phase 02's block 3 states: "where one boot precondition is enforced in several places,
establish whether the copies agree on the condition, the skip rules and the source they expect to read —
**divergent copies of one guard are a finding**", and its evidence item is "one duplicated guard whose
copies disagree". The two copies are `Settings.validate_admin_credentials` (`config.py:389-420`) and
`DatabaseStarter.ensure_admin_user` (`starter.py:317-352`). They disagree twice. On the **condition**:
`config.py:396` gates on `self.environment == EnvironmentEnum.PRODUCTION` and warns otherwise, while
`starter.py:337` gates on `self._config.env != EnvironmentEnum.DEVELOPMENT` and raises. On the **username
predicate**: `config.py:397` tests membership in `WEAK_USERNAMES` in production, while `starter.py:349`
tests `admin_email == "admin"` and only warns. The report discusses both copies under CFG-003, but only for
the emptiness gap, and records neither divergence.

**Evidence** — Static, from the two executing paths as they stand:

| `env` | `config.py:396-405` | `starter.py:337-341` |
| --- | --- | --- |
| `production` | raises | raises |
| `staging` | warns | **raises** |
| `test` | warns | **raises** |
| `development` | warns | warns |

`EnvironmentEnum.STAGING` exists at `models/enums.py:87` and `app.yaml:1` lists `staging` as a supported
value, so `staging` is a tier a configuration can select.

**Consequence** — A true finding the phase's own block declares to be a finding in its own right never
reaches the roadmap. The present effect is bounded — no shipped artefact selects `staging`, and the test
tier's placeholder admin password is not in `WEAK_PASSWORDS` — but the divergence means the settings object
and the component that consumes the value can disagree about whether a credential is acceptable, which is
the precondition the report's CFG-002 and CFG-003 both turn on. A future operator who selects `staging`
gets a stricter boot from `starter.py` than from `Settings`, and the diagnostic comes from a different file
with a different message.

**Recommendation** — File as a phase-02 block-3 finding: state the two divergences as separate rows and
name the two files that must agree. This validation does not modify the audited report.

### VAL-004 — Phase-02 block 7 produced no finding, no appendix and no line of evidence, and block 1's third evidence item is undischarged

**Severity** — MEDIUM

**Zone** — "2. The Vacuous-Control Angle, and Its Bindings: Does It Exist, What Scope Does It Declare, What Did It Examine"

**Observation** — Of the ten declared blocks, block 7 ("Posture switches that can change a running
process") is cited by no finding's Zone and addressed by no appendix. Its evidence items — "per setting,
whether the substitution is constrained and when it is re-pinned", "one switch whose effect reaches only
components built after it is read", "one hardened variant where the switch was never re-pinned" — appear
nowhere. Block 1's third evidence item, "one setting whose re-resolution differs between its load-time
path and its per-use path", is likewise undischarged; Appendix A records the precedence order and the
`init_settings` inversion, and Appendix D records construction side effects, but neither addresses
re-resolution. The report does not state that block 7 was executed and found clean, and does not state
that it was skipped. A reader cannot distinguish the two, which is the condition this validation phase
exists to surface: a control that is absent and a control that ran and decided nothing are different
defects with different owners of the fix.

**Evidence** — Re-derived here, and the block is **satisfiable as clean**:
`rate_limiter_fail_closed` is read at eight call sites — `api/routes/auth.py:86,312,564`,
`api/routes/client_errors.py:47`, `api/routes/upload.py:146`, `services/auth_service.py:68` — so it is
honoured at every use; `app.cookie_secure` is read at two (`core/security.py:438,458`); `debug` is read
only at construction (`app.py:219`) and at construction-time logging (`config.py:429,581`); and
`get_config(reload=True)` has **no caller anywhere in `src/`**, so no re-resolution path exists against
which a construction-time-only consumer could diverge. The posture switch that *is* mis-pinned is `ENV`
itself, and it is CFG-001.

**Consequence** — The block's answer is benign, but the report's silence is not: an unexecuted block and
an executed-clean block are indistinguishable in the artefact, and block 7 is precisely the block that would
have surfaced the re-pin question CFG-001 turns on. For a reader deciding whether the configuration surface
was fully swept, one of ten declared blocks is simply absent.

**Recommendation** — Either execute block 7 and record its answer — the answer is available above and is
"clean, with `ENV` as the single mis-pinned switch, filed as CFG-001" — or record it in the appendices as
executed-and-clean. The second is the smaller change and is what the report's Appendix C already does for
block 6, which is the precedent to copy.

### VAL-005 — Appendix C asserts that the test compose file declares no `${…}` interpolation at all; it declares three

**Severity** — LOW

**Zone** — "8. The Shared Findings Template as a Controlled Artefact"

**Observation** — Appendix C states that `docker-compose.test.yml` "supplies hard-coded literals … and
declares no `${...}` interpolation at all, so it is hermetic by construction". The file declares three:
`docker-compose.test.yml:45` (`"${TEST_DB_HOST_PORT:-5434}:5432"`), `:69` (`"${TEST_REDIS_HOST_PORT:-6381}:6379"`)
and `:150` (`"${TEST_APP_HOST_PORT:-8001}:8000"`). All three are host port mappings with defaults, so the
conclusion — that no credential reaches the test tier through interpolation — survives. The stated reason
does not.

**Evidence** — A pattern search over the file returns exactly those three lines and no others.

**Consequence** — Block 6's own text turns on this distinction: "an environment whose values are hard-coded
literals exercises the interpolation guards only when it in fact interpolates anything." The report asserts
the test environment interpolates nothing, which is false, and a reader auditing that tier against the
assertion would not look for the host-port path. Drift with no remediation consequence today, because all
three defaults are safe and none of them reaches `Settings`.

**Recommendation** — Re-word to "declares `${…}` interpolation for host port mappings only (`:45`, `:69`,
`:150`), each with a default, and none for a value `Settings` reads."

### VAL-006 — Two citation errors in the report: a line anchor that points at a different statement, and a name count that is off by one

**Severity** — LOW

**Zone** — "8. The Shared Findings Template as a Controlled Artefact"

**Observation** — Two verifiable inaccuracies, both cosmetic to the argument. CFG-007 states that
"`logging_config.py:115` hard-codes the non-JSON format string rather than reading `LoggingSettings.format`".
`logging_config.py:115` is `"class": "logging.handlers.RotatingFileHandler"`; the hard-coded format string
is the literal at `logging_config.py:97`. The claim itself is correct and stronger than stated —
`setup_logging` has no `format` parameter at all, so there is no path by which the field could be read.
Separately, CFG-005 states that `.ai/mcp/.env` "carries 33 credential-shaped names". It carries **32**
non-comment assignments, and the named subset it cites is all present.

**Evidence** — Line 97 and line 115 of `logging_config.py` read directly; the `.ai/mcp/.env` name list was
enumerated and counted.

**Consequence** — A wrong approval is the only band this could reach and it does not: both underlying
claims re-derive as true, so no reader is misled about the system. Recorded because the anchor is the kind
of error that propagates into a remediation ticket, where "line 115" is what an engineer opens.

**Recommendation** — Correct the anchor to `logging_config.py:97` and the count to 32.

### VAL-007 — CFG-008's `[DOC-UPDATE]` premise is contradicted by the document it names

**Severity** — LOW

**Zone** — "4. Which Side Moves: Code or Documentation"

**Observation** — CFG-008 states that "`docs/06-backend/configuration.md:83` describes the scan as a
secrets mechanism, with no note that ordinary `*_FILE` names are captured", and attaches a `[DOC-UPDATE]`
to it. Line 83 reads: "The custom `SecretsFileSource` class scans **all** environment variables ending with
`_FILE`, reads the referenced file, and injects the value under the base variable name". The document
states the behaviour precisely, including the word *all*, which is the very fact the finding rests on.

**Evidence** — `docs/06-backend/configuration.md:83` read directly; the behaviour re-derived by direct
invocation, which returned `{'logging': {'log': 'SENSITIVE LOG LINE …'}}` exactly as the report's own
evidence block shows.

**Consequence** — The narrower point survives: the document does not warn an operator that a path-valued
setting such as `LOGGING__LOG_FILE` will be read, and that is worth saying. The finding as written would
send an editor to correct a sentence that is already correct, and the correction they make would likely
make it less accurate.

**Recommendation** — Re-scope the sub-recommendation to the surviving point: warn that the scan captures
any `*_FILE` name, including a path-valued setting, and that the mechanism covers scalar secret fields only.
Drop the claim that the current description is a secrets-only account.

### VAL-008 — CFG-004's recommendation offers to leave "the test path" covered by citing the dev override, so the dev stack keeps the superuser credential after the fix

**Severity** — LOW

**Zone** — "5. Whether the Recommendation Can Be Carried Out"

**Observation** — CFG-004's recommendation says the base-file change is safe because "the test path supplies
its own (`docker-compose.test.yml:137-139`, `docker-compose.override.yml:71-72`)". The first is the test
path. The second is the **dev** path, and it re-supplies `DATABASE__ADMIN_USER: postgres` and
`DATABASE__ADMIN_PASSWORD: ${DATABASE__ADMIN_PASSWORD:?…}` for `app` at `:71-72` and for `rq-worker` at
`:135-136`. Because Compose merges `environment:` maps across files, removing the keys from the base file
leaves the dev stack receiving the superuser credential exactly as it does today — which the report's own
Appendix B records as `database.admin_user=postgres` for both `app` and `rq-worker` in the running dev
containers, and which this validation reproduced in `mkobi-app-1` and `mkobi-rq-worker-1`.

**Evidence** — `docker-compose.override.yml:71-72` and `:135-136` read directly;
`docker exec mkobi-app-1 env` shows `DATABASE__ADMIN_USER=postgres` and `DATABASE__ADMIN_PASSWORD=postgres`
alongside `DATABASE__USER=mkobi_app`.

**Consequence** — The recommendation's action is correct and its production outcome is unaffected. What is
wrong is the exit condition: as written, a reader applying step 4 will verify the production boot and
conclude the superuser credential is gone from the application's processes, while the dev stack — the one
that is actually running — still holds it. The report half-anticipates this in Rollout Safety ("the
override absence is still the reason CFG-004's superuser removal needs care on `rq-worker`"), so the gap is
one sentence of alignment between the recommendation and the safety section.

**Recommendation** — Re-word to "the test path supplies its own (`docker-compose.test.yml:138-139`); the
dev override re-supplies both keys (`docker-compose.override.yml:71-72`, `:135-136`), so the dev stack
keeps the superuser credential after this change and the exit condition should say so."

### VAL-009 — The shared findings template mandates no disposition field, while this validation's output contract requires one on every finding

**Severity** — LOW

**Zone** — "8. The Shared Findings Template as a Controlled Artefact"

**Observation** — `.ai/audit/templates/audit-findings.md:24` requires "One block per finding, in descending
severity. No finding without all five fields", and then enumerates six — `Severity`, `Zone`, `Observation`,
`Evidence`, `Consequence`, `Recommendation` (and the front matter adds a seventh, `findings`). None of them
carries a disposition, a verdict or a re-grade field. The validation output contract requires that "Every
finding in scope carries a verdict, its own identifier, and the re-derivation behind it", and fixes a
disposition vocabulary of six terms. A report written under the template therefore cannot satisfy both
contracts, and this validation resolves it by adding exactly one field — `Verdict` — which the template
does not authorise and which no report written under it carries.

**Evidence** — The template's per-finding field list at `:26-45` against the disposition vocabulary in
`.kilo/commands/audit/phases/99-audit-validate.md:47-48` and the per-finding requirement at `:150`.

**Consequence** — Drift with no remediation consequence today: the added field is additive, named
consistently across all ten findings, and unambiguous. Recorded because the template is a controlled
artefact and the omission will recur on every validation pass until the template gains the field. This
validation does not repair the template from inside a per-phase run.

**Recommendation** — Add `**Verdict** — confirmed | re-typed | re-graded | merged | not substantiated | unsettled`
to the template's per-finding field list, next to `Severity`, so the field is authored once rather than
inferred per run.

## Distribution

Ten findings across the configuration-and-deployment boundary, and the same distribution the input reports —
the heaviest carrier is `src/mkobi/config.py` (five: CFG-002, CFG-003, CFG-007, CFG-008, CFG-009), then
`docker/docker-compose.yml` (three: CFG-001, CFG-004, CFG-006), then `.dockerignore` (CFG-005) and the
documentation set (CFG-010). Per tier, five concern the production tier, two the build context, two the
name universe and one documentation only. Re-derived band distribution is 1 CRITICAL / 3 HIGH / 3 MEDIUM /
3 LOW, against the 1 / 2 / 4 / 3 the front matter declares (VAL-001).

- `src/mkobi/config.py` — credential predicates, unguarded admin fields, the `_FILE` scan, the unreachable
  wildcard, five unread names (5)
- `docker/docker-compose.yml` — tier selection, superuser injection, unwired controls (3)
- `.dockerignore` and the build context (1)
- `docs/` — default drift (1)
- Automation surface (`Makefile.ps1`) — a contributing cause of CFG-001, not an independent defect

The nine validation-level findings fall in a different place: four of them are in the report's aggregates
and its coverage rather than in the system, three are citation-level, one is a recommendation's safety
argument, and one is the shared template's contract. The MEDIUM cluster — the stale tally, the two
unfiled in-scope defects, the silent block — is entirely a property of the report as an artefact.

## Cross-Finding Analysis

The input's two shared causes both re-derive and both survive.

**CFG-002 and CFG-003 share one cause**, and the report's reading of it is exactly right: the
prohibited-value test is exact set membership against a closed list, and on four of the five guarded
credential fields it is the *only* predicate. That form can express neither "differs from the shipped
placeholder" nor "is non-empty and non-whitespace", and `JWTSettings` and `DatabaseSettings` already have
the shape the other two need. Confirmed by direct measurement of both constants against all five shipped
tokens. The report's Cross-Finding Analysis is a genuine cause statement, not a pattern manufactured to
have one.

**CFG-001, CFG-006 and CFG-010 share a second cause** — the deployment definition is not the single
source of truth for the tier label or for the variable set — and the claim re-derives: `ENV` is
interpolated rather than fixed, two documented controls are declared in `docker/.env.production` but
listed in no `environment:` block, and the documentation describing both has drifted with nothing
checking it. All three were reproduced.

One thing the report's Cross-Finding Analysis does not add, and should have: CFG-008 is presented as
independent of the two causes, but it is the same failure in a third form. The `_FILE` source applies to
**every** environment variable whose name ends in `_FILE`, with no check that the name is a declared secret
field — the identical "declare without binding, then read anyway" shape as CFG-006, one layer down in the
source-precedence chain rather than in the compose file. The roadmap already unifies the fix for the
compose-file instance; the `_FILE` instance is scheduled separately at step 6 and never connected to it.

## Roadmap

This phase records whether the input's recommendations can be carried out and in what order. It does not
redesign them.

**Executable as written, target resolved:** CFG-005 (`.dockerignore`; no image-content effect, verification
method supplied and reproduced), CFG-006 (three `environment:` additions fit the 19-key block at
`docker-compose.yml:94-122`; the correction to `security-checklist.md:73` is necessary), CFG-008
(`config.py:60-83`; the `_FILE` tests at `tests/test_config.py:126-152` keep passing, confirmed), CFG-009
(`config.py:434-440` and `app.py:205-213`; no shipped test pins the wildcard branch), CFG-002 and CFG-003
(`config.py:402,473,482` and `:356-357`; the rejection tests at `tests/test_config.py:324-344` keep passing,
confirmed, and no test asserts an empty or whitespace admin credential).

**Executable, one statement to correct first:** CFG-001 (the "single place" claim is false — the dev
override declares `ENV: development` in three places; the outcome is unchanged because Compose merges
`environment:` maps). CFG-004 (the "test path" citation is the dev path; the exit condition must say the
dev stack keeps the credential). CFG-010 (three of four cells are correct; the fourth must be re-scoped
from `.env.example` to the `docker.md:406` / `:416-419` internal inconsistency).

**Substantiated but unusable:** CFG-007. Every target exists, but three of five rows offer alternatives
without choosing and two defer the decision to intent investigation. It names no implementation approach,
which is a distinct outcome from rejection and is recorded as such. The four shipped tests the report
correctly names as encoding the defect (`tests/test_config.py:98-109`, `:117-120`/`:269-272`, `:238-242`,
`:248-252`) are remediation blockers for whichever rows delete a field, and `test_priority_order` (`:172-187`)
is vacuous in the report's own account and adds no gate.

**Ordering.** The input's order — 1 tier binding, 2 credential predicates, 3 deployment variable set, 4
credential bounding, 5 build context, 6 cleanups — is sound, and the two parallelisation claims hold: step 5
changes no image content, and step 4 is independent of steps 1-3. One ordering constraint the input states
correctly and this validation confirms: step 4 should follow step 1 so the boot is exercised at the real
tier, which after step 1 it is.

**The validation-level items precede the roadmap they touch.** VAL-001 must be corrected before the
roadmap is read, or CFG-005 is triaged at the wrong band. VAL-002 and VAL-003 must be filed by the owning
phase before the configuration surface can be called swept, and both belong before step 6, whose exit
condition is "the unread names and the unreachable wildcard are decided" — a statement that cannot be made
while a known MEDIUM from block 8 is unfiled. VAL-004 must be recorded before the report is closed, since
it is the difference between a swept surface and a nine-block surface.

## Rollout Safety

The input's Rollout Safety analysis is sound and every claim in it re-derives. Step 1 is correctly
identified as the only step that changes the behaviour of a currently-working deployment, and its
fail-closed direction is confirmed: after the interpolation is removed, a deployment whose `--env-file`
sets `ENV=staging` will start refusing to boot, and `EnvironmentEnum.STAGING` does exist at
`models/enums.py:87` even though no compose file selects it. The rollback — revert one interpolation line
per service — remains a no-op for everything else, because the dev override supplies `ENV: development`
for all three services independently of the base file. Step 2's observation that
`DatabaseStarter.ensure_admin_user` re-runs the weak-password test and will therefore fail a currently
running deployment at startup rather than silently continue is confirmed at `starter.py:336-341`; that is
the intent, and the refusals need to be observed on a non-live tier first. Step 3 is inert by construction
— the `${…:-default}` forms preserve every current value when the env file supplies nothing — confirmed
against `docker-compose.yml:121-122` and the proposed additions. Step 5's only cost is a build-cache
invalidation, and its proposed patterns change no image content, which this validation verified against
every `COPY` in `docker/Dockerfile`.

Two corrections a reader must carry into the remediation. First, the "shipped test asserts the current
behaviour" list in step 6 is correct as far as it goes and is not exhaustive of what will resist: the
report names six tests, and the two rejection tests at `tests/test_config.py:324-344` are the ones that
*guard* step 2's fix rather than block it — they should be identified as such so nobody "fixes" them.
Second, step 3's correction of `security-checklist.md:73` and step 4's exit condition both need the
dev/test path distinction VAL-008 records, or the verification will be run against a stack that was never
in scope.

What could not be settled: no production deployment exists to inspect, so CFG-001's and CFG-006's
*consequences in a live production tier* rest on the shipped compose definition and its deterministic
resolution, not on an observed production boot. The mechanism is settled; the live blast radius is not.
The `migrate` service is a `restart: "no"` one-shot and its resolved configuration could not be read from
a running container; its values were derived from `docker-compose.yml:61-75`, as the input also records.
The test suite was not executed in this validation either, so every "shipped test asserts X" claim here is
read from test source, not from an observed green run.

## Appendices

**A. Namespace ruling.** The audited phase declares `Finding-ID prefix: CFG-` at
`.kilo/commands/audit/phases/02-audit-configuration-secrets.md:138`, and the input's front matter states
`phase: 02-configuration-secrets`, so the compound form `02-configuration-secrets` + `CFG-` resolves
without ambiguity. Identifiers minted past the run: `CFG-001` through `CFG-010`, contiguous, no gap, no
duplicate. In-source markers: **none** — a pattern search for `CFG-nnn` across the tracked working tree
returns nothing, and both audit report directories are untracked, so the identifiers exist only inside the
audit artefacts and there is no provenance to migrate and no drift to retire. Reuse across phases: phase 01
declares and mints `TOPO-`; the two namespaces are disjoint. **Ruling: the next run reuses `CFG-`.** No
second namespace is created and no collision is reported.

**B. Template conformance, element by element.** Front matter: `phase` present and honest;
`executed` present; `executor: auditor` correct for the authoring run; `problems-only: true` honoured — no
passing check appears in the findings body; `findings: 10` agrees with the ten blocks. `by-severity` is
the one failed element (VAL-001). Per-finding fields: all six present in all ten, none omitted, none
renamed. Zone rule: all ten zones are the block titles of the phase file quoted verbatim, including the
numeric prefix as that file renders it — no paraphrase, no absence. Reserved empty-state string:
correctly absent, because the report has findings and does not pad a summary in its place. Sections: all
seven template sections present. One element the template does not carry at all and this report therefore
adds — the disposition field (VAL-009).

**C. The vacuous-control angle, applied to the findings' own support and then to the report's.** For each
control the findings lean on: the production guard set (CFG-001) — exists, declares the production scope,
and examines nothing at the resolved tier, which is the finding; the weak-credential predicates (CFG-002) —
exist, and their predicate cannot match the form their own inputs take, which is the finding; the CORS
wildcard refusal (CFG-009) — exists, and examines a value the field validator has already removed, which
is the finding. So the angle was applied, not invoked: in each case a control that is present and
configured was reported as deciding nothing, rather than counted as a pass. The report then applies the
same angle to a shipped test — `test_priority_order` — and correctly reports it as unable to fail. Applied
to the report's own controls, the angle is satisfied rather than violated: Appendix E discloses that no
production deployment was inspected, that the `migrate` container's resolved values could not be read, and
that the test suite was not executed — so the report claims no green run it did not observe. One block-9
evidence item is not discharged: "Record separately where each gate is invoked from". The report establishes
the invocation order (field validators before model validators, via CFG-009) but never states the invocation
*path* per gate, so a gate that examines nothing and a gate never invoked remain hard to separate for the
`starter.py` copy.

**D. Cross-phase comparison and the seam check.** Sibling reports compared:
`.ai/audit/01-process-architecture/findings.md` — **raw, not yet validated** (its validation pass is
running concurrently). Contested claims: none found. Phase 01's TOPO-005 and phase 02's CFG-007 both
anchor on `docker/Dockerfile:179` but on different statements in the same `CMD` — adjacent, not contested.
Phase 01's TOPO-002 (`rq-worker` has never received work) and phase 02's Appendix B (`rq-worker` reads no
Redis configuration) are adjacent observations about the same service from different angles, not competing
claims. Phase 01's TOPO-007 (`alembic/env.py` outside both gates) and phase 02's Appendix E
(`alembic/env.py:42` reads an unvalidated `DATABASE_URL`) touch the same file; phase 02 considered it,
decided not to file it, and recorded the reason — the operator-only surface with no deployment supplying
it is correctly a residual rather than a finding, and the decision is recorded rather than silent. Phase 02
owns CFG-004: its block 5 covers "what must not cross between variants and between co-resident processes",
and phase 01 claims no competing concern. Phase 02 owns CFG-005: its block 4 requires confirming that
"the ignore rules cover the build context and not only version control", and phase 10's scope
("the container posture … that consume these values") does not reach the build context. **Seam check:
all ten zones fall inside the phase's declared scope; no finding is filed outside it.**

**E. Shared angles.** Two angles are held as definitions by this validation phase. The **vacuous-control
angle** is bound by phase 02 in its own words at block 9 ("The vacuous-control angle is 99's; what a
configuration gate examines is this block's") and the binding still asks the three questions — what values
it reads, what predicate it applies, and whether that predicate can match the form the value takes — plus
the invocation path, and it adds the enablement question that block 3 already carries. One phase binds it,
the wording has not drifted, and the binding is discharged in practice (Appendix C). The
**cross-resource side-effect angle** is bound by no executed phase in this set; the live instance belongs to
phase 01, which filed it as TOPO-006 (four cross-store effects including a non-transactional Redis write
ahead of `db.commit()`). No phase cites the angle without a definition, and no binding asks a different
question, so there is no drift to record — only the fact that one angle is currently bound once and one
not at all.

**F. Coverage ledger — blocks examined, the item count each reached, and every claim left unsettled.**
Blocks 1-10 of the audited phase, as this validation reached them.

| Block | Reached | How | Item count reached |
| --- | --- | --- | --- |
| 1. Source precedence, variant per process | yes | `config.py:531-564` re-read; `docker compose config` ×2 | 3 of 3 evidence items; the third (re-resolution) is **unsettled here** and undischarged in the input |
| 2. Name universes | yes | compose `environment:` blocks counted; container env dumped; docs read | 3 of 4; the "actionable drift signal" verdict is carried by CFG-006 rather than stated |
| 3. Guarded preconditions | yes | both admin copies, JWT, database, CORS re-derived; 6-case probe | 4 of 5; the "duplicated guard whose copies disagree" item is **unsettled here** and filed as VAL-003 |
| 4. Secret provenance | yes | `.dockerignore` probe build; `pg_restore -l`; `.gitignore`; direct source invocation | 3 of 3; all three effects observed |
| 5. Tier divergence | yes | running dev stack env ×2; resolved objects from `app` and `rq-worker` | 3 of 4; the per-variant accepted-origins and cookie-attribute diff is carried in Appendix B of the input, not re-derived per variant |
| 6. Automated environments | yes | test compose read in full; `conftest.py:18-31`; `test_config.py` | 2 of 3; the "can it stand in for a deployment" verdict is reached (VAL-005 corrects its stated reason) |
| 7. Posture switches | yes | eight read sites for `rate_limiter_fail_closed`, two for `cookie_secure`, `get_config(reload=)` callers | 3 of 3, all three enumerated; block is clean — **unsettled in the input**, filed as VAL-004 |
| 8. Unread / branched configuration | yes | name sweeps over `src/`, `tests/`, `alembic/`; controlled env-override probe | 2 of 3; the relative-root item is **unsettled here** and filed as VAL-002 |
| 9. Vacuous gate | yes | both constants measured against five tokens; field-vs-model validator order | 2 of 3; the "invocation path per gate" item is **unsettled** (Appendix C) |
| 10. Defaults wrong for the environment | yes | four doc cells read; production `Settings` resolved; guard message reproduced | 3 of 3; one of four cells is not substantiated as stated |

Findings table: 10 — confirmed 10, re-typed 0, re-graded 0, merged 0, not substantiated 0, unsettled 0.
One of the ten confirmed findings carries a sub-element recorded as **not substantiated as stated** —
the third of CFG-010's four documentation cells, which is a statement about a claim inside a confirmed
finding rather than a disposition on the finding, so it is stated inside CFG-010 and does not move the
tally. Bands upheld 10, bands changed 0. Validation-level findings: 9 in their own section on the
validation scale — MEDIUM 4, LOW 5. Disposition tally agrees with the per-finding verdicts in both
tables.

Claims left unsettled, with the reason in each case: (1) CFG-001's and CFG-006's consequences in a live
production tier — no production deployment exists to inspect, so the mechanism is settled from the shipped
compose definition and its deterministic resolution while the live blast radius is not; (2) the `migrate`
service's resolved configuration — it is a `restart: "no"` one-shot container, so its values were derived
from `docker-compose.yml:61-75` rather than read; (3) every "shipped test asserts X" claim, in the input
and here alike — the suite was not executed in either run, so all of them are read from test source; (4)
whether any real deployment reached the `CHANGE_ME_*` state CFG-002 describes — the construction is
reproduced, the deployment history is not observable; (5) block 1's re-resolution item and block 9's
invocation-path item — no deployment or test path in the repository re-resolves `Settings` after
`create_app`, and no per-gate invocation table exists to read.

