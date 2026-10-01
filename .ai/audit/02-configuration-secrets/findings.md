---
phase: 02-configuration-secrets
executed: 2026-09-30
executor: auditor
problems-only: true
findings: 10
by-severity:
  CRITICAL: 1
  HIGH: 2
  MEDIUM: 4
  LOW: 3
---

# Phase 02 — Configuration & Secret Material

## Summary

The configuration surface was examined end to end: `src/mkobi/config.py` (the only `BaseSettings`
class), `src/mkobi/settings/app.yaml`, the four name universes (code, `.env.example`,
`docker/.env.{example,development,production}`, the three compose definitions and `Makefile.ps1`),
and every consumer of the resolved object. Runtime evidence was gathered by starting the documented
dev stack (`.\Makefile.ps1 up`), reading each running container's environment and resolved
`Settings` object, resolving the production compose file through `docker compose config`, probing
`Settings` construction under `ENV=production` with present/empty/placeholder values, and building a
throwaway probe image to enumerate what actually reaches the Docker build context.

The most consequential finding is that **the production tier label is not bound to the production
compose file**. `docker/docker-compose.yml` interpolates `ENV` from whatever file the operator
passes to `--env-file`, so the production stack demonstrably resolves `ENV=development` — which
inverts every production guard in `config.py` and `app.py` simultaneously and silently. Underneath
that, the weak-credential guards are exact set membership tests, so every placeholder token the
repository itself ships passes them, and `ADMIN_PASSWORD`/`ADMIN_USERNAME` accept empty and
whitespace values without any predicate at all.

The phase also produced 4 MEDIUM (a superuser credential crossing into least-privilege processes,
build-context material outside `.dockerignore`, documented production controls no deployment
supplies, and seven unread configuration names) and 3 LOW.

## Findings

### CFG-001 — The production compose file resolves `ENV=development` when given the repository's own `.env`, disabling every production guard

**Severity** — CRITICAL

**Zone** — "1. Settings source precedence, and the variant each running process resolves"

**Observation** — `docker/docker-compose.yml` selects the tier by interpolation, not by identity:
line 95 (`app`) and line 181 (`rq-worker`) both carry `ENV: ${ENV:-production}`. There is no
service-level `env_file:` anywhere in the three compose files, so the process's tier is whatever
`--env-file` supplies. The repository-root `.env` — the file `.env.example:2` instructs the operator
to create — declares `ENV=development` (`.env.example:10`), and `Makefile.ps1:33` passes exactly that
file to every dev command. Resolving the production compose file against it yields a process in
which every one of these is inert:

- `Settings.validate_admin_credentials` (`config.py:396-420`) — no admin-credential rejection
- `Settings.validate_debug_mode` (`config.py:422-431`)
- `Settings.validate_cors_origins_not_placeholder` (`config.py:442-460`)
- `Settings.validate_production_credentials` (`config.py:462-489`)
- `Settings.DATABASE_URL`'s production branches (`config.py:634-646`)
- `create_app`'s CORS checks (`app.py:200-213`) and its `/docs` + `/redoc` suppression (`app.py:220-221`)
- `SecurityHeadersMiddleware`'s HSTS and CSP headers (`app.py:78-80`)

Compounding this, the invocation the compose file documents for itself —
`docker/docker-compose.yml:5`, `Production: docker compose -f docker/docker-compose.yml up -d` —
cannot start the stack at all, because Compose's implicit `.env` lookup resolves against the
compose file's own directory (`docker/`), where no `.env` exists. The only working production
invocation is the one in `docker/.env.production:4`, which supplies `--env-file docker/.env.production`;
nothing prevents substituting any other file.

**Evidence** — Resolved output of `docker compose -p mkobi-probe -f docker/docker-compose.yml --env-file .env config`
(exit 0):

```
ENV: development
CORS_ORIGINS: '["http://localhost:3000", "http://localhost:5173"]'
```

Both resolved origins are members of `Settings.CORS_ORIGINS_PLACEHOLDERS` (`config.py:434-440`), which
the production-tier guard rejects and the development tier accepts. Without `--env-file`, the same
command fails with 15 `required variable ... is missing a value` interpolation errors naming
`ADMIN_PASSWORD`, `ADMIN_USERNAME`, `DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD` and
`JWT__SECRET_KEY` across `db`, `migrate`, `app` and `rq-worker`.

**Consequence** — The production compose file, with its `read_only: true`, `cap_drop: ALL`,
`no-new-privileges` and least-privilege `mkobi_app` role, starts and serves traffic with the
development posture: no `Strict-Transport-Security` and no `Content-Security-Policy` response
headers, `/docs` and `/redoc` published, admin/database/JWT weak-credential rejection switched off,
and CORS served for two localhost origins. Nothing in the startup log says the tier was downgraded —
`_log_initialization` (`config.py:573-582`) logs the resolved environment but states nothing about
which guard set that implies. The five `${VAR:?}` presence checks still fire, so a downgrade is the
only failure mode an operator would see, and it is the silent one.

**Recommendation** — Bind the tier to the file, not to the environment: set `ENV: production`
literally in `docker/docker-compose.yml` and delete the `${ENV:-production}` interpolation from all
three services, so the production file cannot resolve to any other tier. Leave the dev override's
`ENV: development` (line 19) as the single place the development tier is declared. Separately,
correct `docker/docker-compose.yml:5` to the invocation that actually works
(`docker compose --env-file docker/.env.production -f docker/docker-compose.yml up -d`), matching
`docker/.env.production:4`. `[SPEC-DEVIATION]` — `docker/.env.production:7` currently carries
`ENV=production` as a file value; after this change that line becomes redundant and should be
replaced by a comment saying the tier is fixed by the compose file.

---

### CFG-002 — Every placeholder token the shipped example env files use passes the production weak-credential guards, and the application's own database password has no guard at all

**Severity** — HIGH

**Zone** — "9. A guard that runs, reports clean, and examines nothing"

**Observation** — The three weak-value checks in `config.py` are exact set membership tests:
`self.admin_password.lower() in WEAK_PASSWORDS` (line 402), `db_password.lower() in {p.lower() for p in WEAK_PASSWORDS}` (line 473),
and `jwt_secret.lower() in {s.lower() for s in JWTSettings.WEAK_SECRETS}` (line 482). `WEAK_PASSWORDS`
(`config.py:19-31`) contains the bare tokens `change_me` and `change_me_admin_password` but no entry
that matches a `CHANGE_ME_*` token with a suffix. The repository ships four distinct suffixed forms:

| Shipped placeholder | in `WEAK_PASSWORDS` | in `WEAK_SECRETS` |
| --- | --- | --- |
| `CHANGE_ME_GENERATE_STRONG_SECRET` | no | no |
| `CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32` | no | no |
| `CHANGE_ME_GENERATE_STRONG_PASSWORD` | no | no |
| `CHANGE_ME_ADMIN_USERNAME` | no | no |
| `CHANGE_ME_ADMIN_PASSWORD` (the code default) | yes | no |

Those four unshipped-list forms appear verbatim in `.env.example:17,27,66,67`,
`docker/.env.development:10,15,18,19` and `docker/.env.example:10,15,18,19`. Separately,
`MKOBI_APP_PASSWORD` — which becomes `DATABASE__PASSWORD` for `app` and `rq-worker`
(`docker-compose.yml:100,185`) and is therefore the production application's *actual* database
password — has no field, validator or model check anywhere in `config.py`; `Settings` never sees the
name.

Two places assert the opposite. `docker/docker-compose.yml:23-24`: "NOTE: ${VAR:?} enforces presence,
not strength. The application validates credential strength at startup when ENV=production."
`docs/11-guides/docker.md:436-439` repeats it for `DATABASE__PASSWORD`, `MKOBI_APP_PASSWORD` and
`JWT__SECRET_KEY` by name.

**Evidence** — `Settings()` constructed with `ENV=production` and exactly the shipped placeholder
strings constructs successfully and yields a usable DSN:

```
constructed with shipped placeholders, env = production
db password accepted: CHANGE_ME_GENERATE_STRONG_SECRET
DATABASE_URL: postgresql+asyncpg://postgres:CHANGE_ME_GENERATE_STRONG_SECRET@localhost:5432/bidb
```

Weak-set membership measured directly against the two constants: all four shipped forms return
`False` for both `WEAK_PASSWORDS` and `WEAK_SECRETS`.

**Consequence** — A production deployment whose credentials are still the documented
`CHANGE_ME_*` placeholders — the state an operator reaches by following the repo's own example files
and only editing `ENV` — boots, reports itself clean, and runs with four attacker-guessable
credentials, one of which (`MKOBI_APP_PASSWORD`) is never subject to any strength check by
construction. The two comments that promise otherwise are the only signal an operator gets, and
both are false.

**Recommendation** — Replace exact membership with a predicate the value's own producer can satisfy:
reject any credential that `startswith("change_me")` (case-insensitive), is empty after stripping, or
is a substring-match against `WEAK_PASSWORDS`/`WEAK_SECRETS`. Keep the exact entries as a
backstop. `MKOBI_APP_PASSWORD` needs no new field — once it is mapped onto `DATABASE__PASSWORD` it is
covered — so the fix is confined to the predicate plus correcting the two comments. Effort: small.
`[DOC-UPDATE]` — reword `docker/docker-compose.yml:23-24` and `docs/11-guides/docker.md:436-439`
after the fix so they describe what is actually enforced.

---

### CFG-003 — `ADMIN_PASSWORD` and `ADMIN_USERNAME` accept empty and whitespace values; there is no emptiness or length predicate on either field

**Severity** — HIGH

**Zone** — "3. Guarded preconditions: presence, strength, and whether the refusal is actionable and secret-free"

**Observation** — `Settings.admin_password` and `Settings.admin_username` (`config.py:356-357`) carry
no field validator at all. Their only production-time test is the `WEAK_PASSWORDS` /
`WEAK_USERNAMES` membership check inside `validate_admin_credentials`, which an empty string and a
single space both fail to match. Contrast the neighbouring fields: `JWTSettings.validate_secret_key`
(`config.py:201-203`) refuses anything under 32 characters; `DatabaseSettings.validate_admin_password_strength`
(`config.py:173-176`) refuses anything under 8. `Settings.admin_password` — a *different* field, the
bootstrap admin's login password — has neither. The same gap exists in the second copy of the guard,
`DatabaseStarter.ensure_admin_user` (`starter.py:336-341`), which re-runs the identical membership
test and therefore also raises nothing.

**Evidence** — Isolated probe (`ENV=production`, CWD moved off the repo root so the `.env` source
cannot contribute, all four credential fields under explicit control):

```
ADMIN_PASSWORD absent -> code default        REFUSED   Value error, Admin password is too common.
ADMIN_PASSWORD='' (present, empty)           ACCEPTED  admin_user='ops@example.com' admin_pw_len=0
ADMIN_USERNAME='' (present, empty)           ACCEPTED  admin_user=''              admin_pw_len=19
ADMIN_PASSWORD=' ' (whitespace)              ACCEPTED  admin_user='ops@example.com' admin_pw_len=1
JWT__SECRET_KEY='' (present, empty)          REFUSED   Value error, JWT secret key must be at least 32 characters
DATABASE__PASSWORD='' (present, empty)       ACCEPTED  (refused later, by Settings.DATABASE_URL, not by Settings())
```

`hash_password(" ")` returns a valid `$2b$12$…` hash and `verify_password(" ", hash)` returns `True`;
`is_weak(" ")` is `False`, so `starter.py:337` does not raise. Compose's `${ADMIN_PASSWORD:?}`
(`docker-compose.yml:110`) rejects the empty string but accepts a single space.

**Consequence** — Absent, empty and malformed are three distinct states and only two of them are
controlled. Today an operator who sets `ADMIN_PASSWORD=" "` — a plausible artefact of trimming a
heredoc — gets a production stack that starts, logs nothing, and seeds the bootstrap administrator
(`starter.py:358-370`) with a one-character password, while the identical mistake on
`JWT__SECRET_KEY` or `DATABASE__ADMIN_PASSWORD` is refused. The refusal that does exist for
`ADMIN_PASSWORD` is also *leaky in the other direction*: `config.py:399` interpolates
`f"Admin username '{self.admin_username}' is too common"` into the exception, so a real username is
echoed into the startup error text and the container log.

**Recommendation** — Add one `field_validator` on `Settings.admin_username`/`admin_password`
rejecting empty and whitespace-only values, mirroring `validate_temp_password_ttl`
(`config.py:371-387`) in style and placement. Replace the username interpolation in
`validate_admin_credentials`' message with a non-revealing one. Effort: trivial.

---

### CFG-004 — The Postgres superuser password is injected into `app` and `rq-worker`, which run as the least-privilege `mkobi_app` role

**Severity** — MEDIUM

**Zone** — "5. Tier divergence: which differences are deliberate, and which are unintended"

**Observation** — `docker/docker-compose.yml:99` sets `DATABASE__USER: mkobi_app` for the `app`
service, and line 184 does the same for `rq-worker`. Both services are then also given the
superuser credential: line 102 and line 187 carry `DATABASE__ADMIN_PASSWORD: ${DATABASE__PASSWORD:?DATABASE__PASSWORD is required}`,
the same value the `db` service (line 25) and the `migrate` service (line 68) receive. That value is
a `CREATEDB`-capable Postgres superuser password, distinct from `MKOBI_APP_PASSWORD`, which is what
the application role actually uses. The only consumer of `database.admin_password` is
`DatabaseStarter.recreate_test_database()` (`starter.py:189-292`), reached solely from
`starter.py:184`, `if self._config.env == EnvironmentEnum.TEST or self._config.recreate_test_db`.
In production `environment` is `production` and `recreate_test_db` is not supplied by any compose
file, so it resolves to `false` from `app.yaml:16`. The credential is present and never used.

**Evidence** — `docker exec mkobi-app-1 env` names include `DATABASE__ADMIN_PASSWORD`,
`DATABASE__ADMIN_USER` and `DATABASE__USER`; the resolved object read from inside the running
container is `db.user=mkobi_app, admin_user=postgres`. `docker exec mkobi-rq-worker-1 ... get_config()`
returns the same pair. The `migrate` service (`docker-compose.yml:65`) legitimately needs it, and
lines 52-54 document that choice.

**Consequence** — The internet-facing process — which also parses untrusted operator-uploaded CSV
through Polars, the largest untrusted-input surface in the application — holds a Postgres superuser
credential it never uses, alongside a `read_only` filesystem and `cap_drop: ALL`. The hardening at
`docker-compose.yml:127-134` bounds what a compromise of that process can reach in the filesystem;
it does not bound what a live superuser credential in that process's environment can reach in the
database. Graded MEDIUM rather than CRITICAL because the credential is single-tier and the
processes that need it are the same tier, so this is a privilege boundary crossing within a tier
rather than a value shared across environments.

**Recommendation** — Drop `DATABASE__ADMIN_USER`/`DATABASE__ADMIN_PASSWORD` from the `app` and
`rq-worker` environment blocks (`docker-compose.yml:101-102`, `:186-187`). The production path never
consumes them; the test path supplies its own
(`docker-compose.test.yml:137-139`, `docker-compose.override.yml:71-72`). If a future production
need for `recreate_test_db` appears, reintroduce them through a Docker secret on that one service
rather than the compose environment. Effort: trivial; verify by booting production compose and
confirming `create_app` and the health endpoint come up unchanged.

---

### CFG-005 — `.dockerignore` does not cover the build context: a database dump and a credential env file ship into every build

**Severity** — HIGH

**Zone** — "4. Secret provenance, and every surface the material can reach"

**Observation** — All three compose services declare `build.context: ..` (the repository root), so the
context is the whole working tree. `.dockerignore:70-74` lists exactly four env patterns — `.env`,
`.env.example`, `.env.local`, `.env.*.local` — and nothing else. Three credential-bearing
directories and files that `.gitignore` already excludes from version control match none of them:
`.gitignore:254` (`backups/`), `.gitignore:163` (`.ai/mcp/.env`), and the `/.env.*` rule at
`.gitignore:157` (`.env.docker`). `docker/.env.production`, `docker/.env.development` and
`docker/.env.example` are intentionally tracked and also unexcluded.

**Evidence** — Probe build from the repository root with `COPY . /ctx` and an existence test per path
(`--output=type=cacheonly`, nothing written to the repository):

```
IN_CONTEXT: .env.docker
IN_CONTEXT: .ai/mcp/.env
IN_CONTEXT: docker/.env.production
IN_CONTEXT: docker/.env.development
IN_CONTEXT: docker/.env.example
IN_CONTEXT: backups
IN_CONTEXT: .ai/audit
EXCLUDED:  .env
EXCLUDED:  .env.example
```

`backups/` contains two `pg_dump -F c` dumps written today
(`bidb-20260930_111251.dump`, `bidb-20260930_113752.dump`, ~39 KB each, produced by
`Makefile.ps1:279-290`). `pg_restore -l` on the second lists `TABLE DATA public users`,
`dashboard_access`, `dashboard_filter_values`, `aggregated_data`, `dashboards`, `graphs`,
`processing_configs`, `registration_requests` and more. `.ai/mcp/.env` carries 33 credential-shaped
names including `DATABASE__PASSWORD`, `DATABASE__ADMIN_PASSWORD`, `JWT__SECRET_KEY`,
`ADMIN_PASSWORD` and `MKOBI_APP_PASSWORD`. `.env.docker` carries six.

**Consequence** — Every `docker compose build` transmits a full database dump (including the `users`
table's bcrypt password hashes and all dashboard content) and two live credential files to the
Docker daemon, where they are retained in the builder's context store and in any build cache. No
image layer receives them — the `COPY` instructions in `docker/Dockerfile` are selective
(lines 15, 21, 105-106, 113-114, 134-141, 158-170) — but a remote, rootless or shared builder, or an
exported cache, would. Graded HIGH rather than CRITICAL because the material present in this
repository is development-tier (`postgres`/`mkobi_app`/`admin` in `.env.docker`, dumps of the dev
database) and the exposure requires read access to the builder rather than to the image.

**Recommendation** — Extend the environment block of `.dockerignore` to a pattern set that cannot be
bypassed by a new name: add `**/.env*`, `.env*`, `backups/`, `.ai/`, `.kilo/`, `.idea/` and
`*.dump`. Verify with the same probe build and confirm every path reports `EXCLUDED`. Effort:
trivial; no image content changes, so rebuild hashes are unaffected.

---

### CFG-006 — `RATE_LIMITER_FAIL_CLOSED` and `UPLOAD__MAX_FILE_SIZE_MB` are documented production controls that no deployment supplies

**Severity** — MEDIUM

**Zone** — "2. Name universes: what code reads, what the shipped examples declare, and what the deployment supplies"

**Observation** — Because no compose file declares a service-level `env_file:`, `--env-file`
supplies values for `${...}` interpolation only; a name reaches a container only if the
`environment:` block lists it. Neither name appears in any `environment:` block in
`docker-compose.yml`, `docker-compose.override.yml` or `docker-compose.test.yml`. Both are declared
in `docker/.env.production`: `RATE_LIMITER_FAIL_CLOSED=true` (line 38) and
`UPLOAD__MAX_FILE_SIZE_MB=100` (line 33). Both are documented as live production controls:
`docs/10-deployment/security-checklist.md:57` lists `RATE_LIMITER_FAIL_CLOSED` under "Required
Production Variables" in a section opening at line 51 with "Docker Compose will fail to start if
unset", and lines 76-81 instruct the operator to verify that the `app` service includes
`RATE_LIMITER_FAIL_CLOSED: ${RATE_LIMITER_FAIL_CLOSED:-true}`. Line 86 instructs the operator to
confirm `UPLOAD__MAX_FILE_SIZE_MB` is appropriate. `docs/11-guides/docker.md:449` lists
`RECREATE_TEST_DB` as a key variable of the base compose. In each case the shipped file supplies
neither the variable nor a placeholder for it.

The same shadowing affects six further names in `docker/.env.production` that the compose `environment:`
blocks overwrite with literals: `DATABASE__HOST`/`DATABASE__PORT`/`DATABASE__DBNAME`
(`:17-19` vs `:96-98,103`), `JWT__ALGORITHM` (`:22` vs `:107`), `UPLOAD__TEMP_DIR` (`:32` vs `:111`),
`UPLOAD__ALLOWED_EXTENSIONS`/`UPLOAD__ALLOWED_MIME_TYPES` (`:34-35`, no entry) and
`LOGGING__JSON_LOGGING` (`:29`, no entry).

**Evidence** — The `app` `environment:` block is `docker-compose.yml:94-122`; its 19 keys contain
none of these names. The prescribed verification command at
`docs/10-deployment/security-checklist.md:73` is `docker compose -f docker/docker-compose.yml config --services`,
which prints service names and cannot surface an environment key at all. The upload rejection path
(`src/mkobi/api/routes/upload.py:129-141` and `:181-195`) reports
`config.upload.max_file_size_mb` — which still reads 100 — so the client-facing error is
self-consistent and gives the operator no hint that the setting was ignored.

**Consequence** — `RATE_LIMITER_FAIL_CLOSED` fails in the safe direction: the process keeps the
`True` default (`config.py:366`), and no operator can switch it off. The cost is the assurance the
checklist offers: an operator who works through the list concludes a fail-closed control is pinned,
when the pinning is an accident of the field default rather than of the deployment. The upload limit
fails in the silently-wrong direction: an operator who raises `UPLOAD__MAX_FILE_SIZE_MB` in
`.env.production` to accept larger files continues to receive `FILE_TOO_LARGE` at 100 MB, with an
error message quoting the unchanged 100 MB value.

**Recommendation** — Add `RATE_LIMITER_FAIL_CLOSED: ${RATE_LIMITER_FAIL_CLOSED:-true}`,
`UPLOAD__MAX_FILE_SIZE_MB: ${UPLOAD__MAX_FILE_SIZE_MB:-100}` and
`LOGGING__JSON_LOGGING: ${LOGGING__JSON_LOGGING:-true}` to the `app` and `rq-worker` `environment:`
blocks. Then correct `docs/10-deployment/security-checklist.md:73` to a verification command that
actually inspects the environment (`docker compose --env-file docker/.env.production -f
docker/docker-compose.yml config | grep -A30 'app:'`, or `make config`). Delete the names from
`.env.production` that the compose file hard-codes, or convert them to comments saying so.
`[SPEC-DEVIATION]`. Effort: small.

---

### CFG-007 — Seven declared configuration names are read by nothing

**Severity** — MEDIUM

**Zone** — "8. Assigned, derived and branched configuration that nothing reads"

**Observation** — Per-name liveness, swept across `src/mkobi/`, `tests/`, `alembic/` and the
compose files:

| Name | Declared in | Read by |
| --- | --- | --- |
| `Settings.host`, `Settings.port` | `config.py:328-329`; supplied as `HOST=0.0.0.0` / `PORT=8000` by `.env.example:45-46` | nothing |
| `upload.temp_dir_prefix` | `config.py:238`; `app.yaml:35` | nothing |
| `dashboard.default_items_per_page` | `config.py:268`; `app.yaml:95-96` | nothing |
| `logging.format` | `config.py:274`; `app.yaml:54` | nothing |
| `app.name`, `app.version` | `config.py:224-225`; `app.yaml:5-7` | nothing |
| `Settings.load_yaml_config()` | `config.py:750-761` | tests only |

Three of these are actively misleading. `create_app` sets the FastAPI title from `config.app_name`
(`app.py:216`) while hard-coding `version="1.0.0"` (`app.py:218`), so the `app.version` in
`app.yaml` and the `APP_NAME` in `.env.example:43` describe two different fields from the one that
is used. `logging_config.py:115` hard-codes the non-JSON format string rather than reading
`LoggingSettings.format`, so `json_logging: false` produces the built-in format regardless.
The bind address is hard-coded in `docker/Dockerfile:127,179` and
`docker/docker-compose.override.yml:109`; `HOST`/`PORT` in `.env.example` control nothing.

**Evidence** — Zero occurrences outside `config.py` for each row's right-hand column; the only
consumers are `tests/test_config.py:100-109` (`load_yaml_config`), `:120` and `:272`
(`default_items_per_page`) and `:252` (`temp_dir_prefix`).

**Consequence** — An operator who sets `UPLOAD__TEMP_DIR_PREFIX`, `DASHBOARD__DEFAULT_ITEMS_PER_PAGE`,
`LOGGING__FORMAT`, `HOST` or `PORT` gets a running system that ignores them, with no warning. The
three-name-for-one-concept split around the application title/version means the version reported in
`/openapi.json` and the title in `/docs` cannot be changed by configuration at all, which is the more
likely intent of `app.yaml` existing at all.

**Recommendation** — Delete `host`, `port` and `Settings.load_yaml_config()` (nothing outside tests
uses them) and remove `HOST`/`PORT` from `.env.example`. For `app.name`/`app.version`, pick one
owner: either point `create_app` at `config.app.name`/`config.app.version` and drop `Settings.app_name`,
or delete the `AppSettings` fields and keep `APP_NAME`. For `logging.format`, either thread it into
`setup_logging` or drop it from `LoggingSettings` and `app.yaml`. `dashboard.default_items_per_page`
and `upload.temp_dir_prefix` need a consumer or removal — investigate intent before deleting.
`[DOC-UPDATE]`. Effort: small.

---

### CFG-008 — `SecretsFileSource` treats `LOGGING__LOG_FILE` as a secret pointer and reads the path it names

**Severity** — LOW

**Zone** — "4. Secret provenance, and every surface the material can reach"

**Observation** — `SecretsFileSource.__call__` (`config.py:60-83`) iterates `os.environ` and acts on
**every** variable whose name ends in `_FILE`, with no allow-list and no check that the stripped base
name corresponds to a declared secret field. `LOGGING__LOG_FILE` is an ordinary path setting that
both compose files set: `docker-compose.yml:112,197` to `/app/data/logs/app.log` and
`docker-compose.override.yml:82` to `""`. Stripping `_FILE` from it yields the base name
`LOGGING__LOG`, which `_set_nested_value` (`config.py:34-46`) turns into `{"logging": {"log": <file
contents>}}`. The value is discarded downstream because `LoggingSettings` has no `log` field and the
settings tree runs with `extra: ignore` (`config.py:527`) — but the read happens first.

**Evidence** — Direct invocation of the source in a container-equivalent environment:

```
LOGGING__LOG_FILE=/app/data/logs/app.log
SecretsFileSource returned: {'logging': {'log': 'SENSITIVE LOG LINE THAT SHOULD NEVER BE LOADED AS A SETTING'},
                              'jwt': {'secret_key': 'a-strong-32-plus-character-secret-value-here'},
                              'some_unrelated': 'a-strong-32-plus-character-secret-value-here'}
```

With `LOGGING__LOG_FILE=""` (the dev override's value) `Path("")` resolves to the process working
directory; the running `mkobi-app-1` container emits `WARNING mkobi.config: Failed to read secret
file .: [Errno 21] Is a directory: '.'` at every start. `docs/06-backend/configuration.md:83`
describes the scan as a secrets mechanism, with no note that ordinary `*_FILE` names are captured.

**Consequence** — Two concrete effects today, neither a secret exposure: a spurious WARNING on every
development boot whose message points an operator at a nonexistent secret file, and an unconditional
read of the entire active log file into memory on every production boot of `app`, `rq-worker` and
`migrate`. The underlying hazard is larger than the effect: any `*_FILE` variable the operator sets
for an unrelated reason is read and injected above `.env` and `app.yaml` in the precedence chain, and
the complex-field JSON decoding that `EnvSettingsSource` performs is not applied, so
`CORS_ORIGINS_FILE` or `UPLOAD__ALLOWED_EXTENSIONS_FILE` aborts startup with
`Input should be a valid list` rather than configuring anything.

**Recommendation** — Restrict the source to names that are declared secret fields: skip any
`X_FILE` whose stripped base is not a `Settings` field of a known-secret model, and skip the literal
base `LOGGING__LOG` explicitly if the allow-list approach is deferred. Effort: small; the `_FILE`
tests in `tests/test_config.py:126-152` still pass unchanged. `[DOC-UPDATE]` — note in
`docs/06-backend/configuration.md:73-83` that the mechanism covers scalar secret fields only.

---

### CFG-009 — The CORS wildcard refusal is unreachable: the field validator removes `"*"` before either copy of the guard can see it

**Severity** — LOW

**Zone** — "9. A guard that runs, reports clean, and examines nothing"

**Observation** — `Settings.validate_cors_origins` (`config.py:491-515`) is a field validator and runs
before every model validator. It admits an origin only if `urlparse(origin).scheme` is `http` or
`https` and `parsed.netloc` is non-empty, so `"*"` is dropped with a warning. Two controls therefore
test for a value that can no longer exist: the `"*"` entry in
`Settings.CORS_ORIGINS_PLACEHOLDERS` (`config.py:434-440`), and `create_app`'s
`if "*" in config.cors_origins` refusal (`app.py:205-213`). The remaining entries of the placeholder
set — `http://localhost:5173` and the others — do survive the field validator, so the model validator
is not vacuous in general.

**Evidence** — With `ENV=production` and `CORS_ORIGINS='["*"]'`:

```
Invalid CORS origin rejected: '*' (must be http:// or https:// URL)
cors_origins after field validator: []
'*' in cors_origins -> False
```

`Settings()` then constructs successfully with `environment=production` and an empty origin list;
the refusal comes from the *other* check, `app.py:202-204`, which reports "CORS origins must be set in
production environment" — a message that describes a missing value, not the wildcard the operator
actually configured.

**Consequence** — Fails closed, so nothing is served with a wildcard policy. What remains is two dead
controls and a misleading diagnostic: an operator who pastes `CORS_ORIGINS='["*"]'` into
`.env.production` is told to configure origins, and if they replace it with a single wildcard-looking
entry again nothing in the logs names the wildcard as the cause. The documentation at
`docs/06-backend/configuration.md:126-129` ("raises an error if origins are not set in production
mode") matches the behaviour that actually fires, so no document is wrong here.

**Recommendation** — Delete the `"*"` entry from `CORS_ORIGINS_PLACEHOLDERS` and the
`app.py:205-213` wildcard branch, or move the wildcard check ahead of the field validator. The
direction that preserves operator-facing clarity is the second: check the raw parsed input for `*`
before filtering, so the error names the wildcard. Effort: trivial.

---

### CFG-010 — Four documentation defaults no longer match the code

**Severity** — LOW

**Zone** — "10. Defaults that are wrong for the environment the process is deployed into"

**Observation** — Each of these is a documented default whose asserted value differs from the
resolved one, with no assertion anywhere that keeps it true:

| Location | Asserted | Actual |
| --- | --- | --- |
| `docs/06-backend/configuration.md:61` | `ADMIN_PASSWORD` default `admin` | `CHANGE_ME_ADMIN_PASSWORD` (`config.py:357`) |
| `docs/06-backend/configuration.md:66` | `CORS_ORIGINS` default `[]` | `app.yaml:86-88`'s two localhost origins |
| `docs/11-guides/docker.md:416-419` | "the default `.env` uses `admin@example.com` for both" | `.env.example:66-67` uses `CHANGE_ME_ADMIN_USERNAME` / `CHANGE_ME_GENERATE_STRONG_PASSWORD` |
| `docs/06-backend/configuration.md:103-108` | admin check is `== "admin"` | membership test against `WEAK_USERNAMES` / `WEAK_PASSWORDS` (`config.py:397,402`) |

**Evidence** — Resolved production `Settings` with no `.env` present: `cors_origins` equals
`['http://localhost:3000', 'http://localhost:5173']`, not `[]`. The `admin_username` guard message
produced by the probe run is the `WEAK_USERNAMES` branch ("Admin username 'admin@example.com' is too
common"), which the documented `==` snippet cannot generate.

**Consequence** — A reader checking `configuration.md` before a production deploy concludes that an
unset `CORS_ORIGINS` yields no cross-origin access (true) and that `ADMIN_PASSWORD` defaults to
`admin` (false — the default the guards actually reject is `CHANGE_ME_ADMIN_PASSWORD`). Neither
misstatement causes a fault on its own, but both are the kind an operator uses to decide whether a
guard has already fired, which is exactly the question CFG-002 and CFG-003 turn on.

**Recommendation** — Correct the four cells in the table above against the resolved values, and add
`docs/06-backend/configuration.md:37`'s priority table row for `app.yaml` to name the two values it
contributes that differ from the field defaults (`cors_origins`, `upload.temp_dir`). Effort:
trivial. `[DOC-UPDATE]`.

## Distribution

Ten findings, concentrated on the configuration-and-deployment boundary rather than on any single
process. The heaviest carrier is `docker/docker-compose.yml` (CFG-001, CFG-004, CFG-006) followed by
`src/mkobi/config.py` (CFG-002, CFG-003, CFG-007, CFG-008, CFG-009), then `.dockerignore` (CFG-005)
and the documentation set (CFG-010). Per tier: five findings concern the production tier, two the
build context, two the name universe, one documentation-only.

- `docker/docker-compose.yml` — tier selection, superuser credential injection, unwired controls (3)
- `src/mkobi/config.py` — weak-value predicates, unguarded admin fields, `_FILE` scan, unreachable wildcard, unread names (5)
- `.dockerignore` / build context (1)
- `docs/` — default drift (1)
- Automation surface (`Makefile.ps1`) — a contributing cause of CFG-001, not an independent defect

## Cross-Finding Analysis

Two causes are shared.

**CFG-002 and CFG-003 share one cause:** the prohibited-value test is exact set membership against a
closed list, and it is the *only* predicate on four of the five guarded credential fields. That form
can express neither "differs from the shipped placeholder" (CFG-002 — every `CHANGE_ME_*` variant
misses) nor "is non-empty and non-whitespace" (CFG-003 — `""` and `" "` miss). `JWTSettings` already
has the shape the others need, a length predicate; `DatabaseSettings` has one too. Only
`Settings.admin_username`/`admin_password` lack it. Fixing the predicate form and adding a length/emptiness
check are the same change to the same four lines of `config.py`.

**CFG-001, CFG-006 and CFG-010 share a second cause:** the deployment definition is not the single
source of truth for either the tier label or the variable set. `ENV` is interpolated rather than
fixed (CFG-001); documented controls are declared in `docker/.env.production` but never listed in an
`environment:` block (CFG-006); the documentation that describes both drifted without anything
checking it (CFG-010). The one durable fix is to make `docker/docker-compose.yml` the authority for
the tier and for the variable set, and to let `docker/.env.production` hold only values the compose
file interpolates.

CFG-004, CFG-005, CFG-007, CFG-008 and CFG-009 are independent of each other and of the two causes above.

## Roadmap

Ordered by cause, not by severity. Each step's exit condition is stated because the next step depends on it.

1. **Bind the tier to the compose file (CFG-001).** Replace `ENV: ${ENV:-production}` with
   `ENV: production` in `docker/docker-compose.yml:95,181`; correct the invocation at
   `docker/docker-compose.yml:5`.
   *Exit:* `docker compose --env-file .env -f docker/docker-compose.yml config` no longer resolves
   `ENV=development`, and the corrected documented invocation resolves.
2. **Fix the credential predicates (CFG-002, CFG-003).** In `config.py`, add the
   `startswith("change_me")` / empty / whitespace rejection and a minimum-length validator on
   `admin_username`/`admin_password`; drop the username interpolation from the guard message.
   *Exit:* the CFG-002 probe constructs no longer boot, and the CFG-003 empty/whitespace cases are
   refused. Both are observable with a single `Settings()` construction per case.
3. **Reconcile the deployment variable set and the documentation that describes it (CFG-006, CFG-010).**
   Add the missing `environment:` entries, delete or comment the shadowed names, correct the four
   documented defaults and the prescribed verification command.
   *Exit:* every name in `docker/.env.production` appears in an `environment:` block, and
   `security-checklist.md`'s verification command prints the environment it claims to check.
4. **Bound the credential each process holds (CFG-004).** Remove `DATABASE__ADMIN_USER`/
   `DATABASE__ADMIN_PASSWORD` from `app` and `rq-worker`.
   *Exit:* production compose boots and `/health` and `/health/detailed` respond; the running app
   container's environment no longer contains a superuser password. Independent of steps 1-3; can run
   in parallel with them, but do it after step 1 so the boot is exercised at the real tier.
5. **Close the build-context gap (CFG-005).** Extend `.dockerignore`.
   *Exit:* the probe build reports `EXCLUDED` for `.env.docker`, `.ai/mcp/.env`, `backups/` and
   `docker/.env.*`. Safe to run at any time; it changes no image content.
6. **Decide the fate of the unread names (CFG-007) and the unreachable wildcard (CFG-009), and scope
   the `_FILE` source (CFG-008).** These are independent cleanups; investigate intent before removing
   `upload.temp_dir_prefix` and `dashboard.default_items_per_page`, per the dead-code policy.

## Rollout Safety

Step 1 is the only step that changes behaviour of a deployment that is currently working, and it can
fail closed. A deployment whose `--env-file` deliberately sets `ENV=staging` will start refusing to
boot, because `staging` also bypasses every production guard that step 1 removes the ability to skip
— verify no environment uses `ENV=staging` before applying it (`EnvironmentEnum.STAGING` exists at
`models/enums.py:87` but no compose file selects it). Roll back by reverting the single interpolation
line; nothing else depends on it.

Step 2 will refuse boots that previously succeeded, which is the intent, but the refusals must be
observed before they reach a live tier: `DatabaseStarter.ensure_admin_user` (`starter.py:336-346`)
re-runs the weak-password test, so a deployment currently running with a placeholder admin password
will fail at startup rather than silently continue. Steps 2 and 4 touch `docker-compose.yml` and
`config.py` in different files and do not interact. Step 3 is inert by construction — adding names to
an `environment:` block only takes effect if the corresponding env file supplies them, and
`${UPLOAD__MAX_FILE_SIZE_MB:-100}` preserves the current value when absent.

Step 5 has no runtime effect and no image-content effect; the only cost is a full cache invalidation
on the next build, since the context hash changes.

Steps 6-9 are the ones that need `tests/test_config.py` reconciled. Four shipped tests assert the
current values and will encode the defects if left alone: `test_load_app_name_from_yaml` and
`test_load_app_version_from_yaml` (`:98-109`), `test_load_dashboard_default_items_from_yaml` (`:117-120`,
duplicated at `:269-272`), and `test_app_settings_defaults` (`:238-242`) all read
`load_yaml_config()` and `app.*` rather than the fields the application uses;
`test_upload_settings_defaults` (`:248-252`) asserts `temp_dir_prefix`. `test_priority_order`
(`:172-187`) claims to verify `Docker secret > .env` but never creates a `.env`, so it cannot detect
a precedence change. These are remediation blockers for CFG-007, not gates on it.

## Appendices

**A. Source precedence as resolved.** `Settings.settings_customise_sources` (`config.py:531-564`)
returns `(env_settings, SecretsFileSource, dotenv_settings, YamlConfigSettingsSource, init_settings)`;
pydantic-settings treats the first entry as highest priority. This matches the docstring at
`config.py:542-548` and `docs/06-backend/configuration.md:32-38`. Note that `init_settings` is placed
*lowest*, below `app.yaml`, which inverts pydantic's own convention; nothing constructs `Settings`
with keyword arguments in `src/`, so the inversion is currently unobservable.

**B. Per-process resolved values, captured from the running dev stack** (`.\Makefile.ps1 up`, exit 0,
all six services healthy):

| | `app` | `rq-worker` | `migrate` |
| --- | --- | --- | --- |
| `environment` | `development` | `development` | `development` |
| `redis.host` | `redis` | `localhost` | `localhost` |
| `app.cookie_secure` | `False` (override) | `True` (default) | `True` (default) |
| `cors_origins` | `[localhost:3000, localhost:5173]` | same | same |
| `logging.level` | `DEBUG` (override) | `DEBUG` (override) | default |
| `database.user` | `mkobi_app` | `mkobi_app` | `postgres` |
| `database.admin_user` | `postgres` | `postgres` | `postgres` |

The `redis.host` difference is **not** a finding: `SPEC.md:184` declares it intentional ("The
`rq-worker` service does not need these variables — it receives its target from the explicit
`--url redis://redis:6379/0` command line, and its worker code reads no Redis configuration"), and
the code honours the declaration — `workers/data_worker.py` imports no Redis client and
`src/mkobi/core/redis_client.py` is reached only from `api/deps.py` and `services/auth_service.py`,
neither of which is in the worker path. The override absence is still the reason CFG-004's
superuser removal needs care on `rq-worker`.

**C. Automated environments and the source each exercises.** `docker-compose.test.yml` supplies
hard-coded literals (`:34-35` `test_password`/`test_app_password`, `:106` a 48-character JWT secret,
`:108-109` admin credentials) and declares no `${...}` interpolation at all, so it is hermetic by
construction. It therefore exercises the environment-variable source and `app.yaml` only: no
`_FILE` path, no `.env`, and no compose interpolation. The `_FILE` path and the production-only guard
branches are reachable only through `tests/test_config.py`, which constructs a fresh `Settings()` after
`monkeypatch.setenv("ENV", "production")` (`:87`, `:329`, `:340`, `:466-510`, `:638-708`). One
divergence worth recording: `tests/conftest.py:27` sets `JWT__SECRET_KEY` to
`test_secret_key_change_in_production` while `docker-compose.test.yml:106,142` sets
`test_jwt_secret_key_for_integration_tests_32_chars`; because `conftest` uses `setdefault`, the
compose value wins inside the container and the conftest literal is inert on the canonical path. No
guard in `config.py` was found to be unreachable by every automated environment.

**D. Construction side effects of `Settings()`.** `Settings.__init__` (`config.py:566-571`) calls
`_log_initialization` (logs `env`, `database_host`, `redis_host` only), `_ensure_upload_dir`
(`config.py:584-587`, `Path(upload.temp_dir).mkdir(parents=True, exist_ok=True)`) and
`_log_security_warnings` (non-production only). The directory creation is real and happens in every
process that constructs the object, including the one-shot `migrate` service, and it succeeded under
production's `read_only: true` only because `/app/data` is a mounted volume. `SecretsFileSource`
additionally reads every `*_FILE`-suffixed path (CFG-008). No loaded value was observed in any log
line, exception message or command line during this phase; `_log_initialization` and the
`DATABASE_URL` construction are both clean of credential material, and
`starter.py:312` uses `render_as_string(hide_password=True)`.

**E. What could not be verified here, and why.** No production deployment exists to inspect, so
CFG-001's and CFG-006's consequences are established from the shipped compose definition and its
resolution, not from a running production stack — the blast radius stated is what the shipped
artefact permits, which is the best available basis. The `migrate` service's resolved configuration
could not be read directly because it is a `restart: "no"` one-shot container; its values were
derived from `docker-compose.yml:61-75` and from the fact that `alembic/env.py:44-47` constructs
`Settings()` only when `sqlalchemy.url` and `DATABASE_URL` are both absent (`alembic.ini:90` leaves
the URL unset, so it does construct). Note that `alembic/env.py:42` reads an unvalidated
`DATABASE_URL` environment variable ahead of `get_config()`, bypassing every production guard — this
was not filed as a finding because no compose file sets `DATABASE_URL`, so it is an operator-only
surface; it is recorded here because it is the one path by which a guarded credential reaches
migrations unvalidated. The test suite was not executed in this phase (the `mkobi-test` stack was not
started), so the "shipped test asserts the current behaviour" claims in Rollout Safety are read from
test source, not from an observed green run.
