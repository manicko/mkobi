---
phase: 02-configuration-secrets
executed: 2026-10-05
executor: validator
problems-only: true
findings: 14
by-severity:
  CRITICAL: 1
  HIGH: 1
  MEDIUM: 7
  LOW: 5
---

# Phase 02 — Validated Findings (Configuration & Secrets)

> **Path note, recorded so a later run does not correct it.** This phase's file stem is
> `{NN}-{phase-name}-validated-findings.md` while its output directory is `99-validation/`. The divergence is
> deliberate and declared by `.kilo/commands/audit/phases/99-audit-validate.md` (Report Output, first bullet).

## Summary

Every one of the fourteen findings was re-derived against the working tree as it stands, not against the
report's quotes. All fourteen survive; none is rejected. The single most consequential claim, CFG-101, was
re-verified from scratch because the frontend was refactored by concurrent work mid-audit — the refactor gave
`VITE_API_URL` a real reader but left the fatal guard and its module-scope call intact, so the finding is
**confirmed, not remediated**, and independently reproduced end to end (a fresh production build emits
`tt()` unconditionally before `createRoot`; the control build with the variable set emits no throw).
Two bands move: CFG-102 HIGH → MEDIUM (the discarded-constructor path has no caller in `src/` or `tests/`
today, so no control is disabled) and CFG-105 MEDIUM → LOW (the length guard still refuses every weak
secret, so there is no exposure — only a declaration that overstates its own reach). CFG-107 and CFG-113 are
confirmed in substance but their inventories and citations are wrong in ways a reader must repair: four of
CFG-107's seven "dead properties" do not exist on `Settings`, and CFG-113 cites a module that is not in the
tree and a `config.py` line inside `is_weak_credential`. Separately, seven defects **in the report itself**
are recorded in their own `VAL-` section, the largest being a systematic line-number drift across the compose
files that leaves every load-bearing claim intact but every citation misplaced.

**Verdict vocabulary.** The instruction for this pass requires `CONFIRMED / CORRECTED / REJECTED`; the
99-validation phase fixes the vocabulary at `confirmed / re-graded / merged / not substantiated / unsettled`.
The mapping used per finding is: **CONFIRMED** = confirmed · **CORRECTED** = confirmed with the evidence or
the band re-derived (re-graded where the band moved) · **REJECTED** = not substantiated. No finding is
re-typed, merged or unsettled.

---

## Findings

Findings appear in descending final severity. Each carries the verdict, the zone quoted verbatim from
`.kilo/commands/audit/phases/02-audit-configuration-secrets.md`, and the location inside the observation.

### CFG-101 — The production SPA throws on first byte: `validateEnv()` runs at module scope and the image's build stage never supplies `VITE_API_URL`

**Severity** — CRITICAL (re-derivation of the audited band's, sustained)

**Zone** — Name universes: what code reads, what the shipped examples declare, and what the deployment supplies

**Observation** — CONFIRMED. The claim still does what it says, at the location it says, after the concurrent
refactor. `frontend/src/main.tsx:7` calls `validateEnv()` at module top level, outside React and outside any
error boundary; `frontend/src/shared/config/env.ts:38-46` makes that call fatal whenever
`import.meta.env.DEV` is false and `VITE_API_URL` is absent (throw at `:43-45`); and no build surface in the
repository supplies the variable. The refactor changed `env.ts` and did not fix this: it added the missing
consumer (`getApiBaseUrl()` at `:20-28`, which is what the phase-13 note recorded as absent) and left the
guard and the call exactly where they were. This is the check this pass was told to make independently, and
the answer is that the defect survived it.

**Evidence** — Re-derived from the current files, not from the report's quotes:
- `frontend/src/main.tsx:4,6,7` — import, comment, unguarded call, all present verbatim.
- `frontend/src/shared/config/env.ts:10` (`DEFAULT_API_BASE_URL = '/api/v1'`), `:13`, `:20-28`, `:38-46` —
  the refactored single-accessor shape; `getApiBaseUrl()` reads the variable, `validateEnv()` throws.
- `docker/Dockerfile:16` pins the `frontend-builder` stage, `:28` runs `npm run build`, and the stage
  declares **no** `ARG` or `ENV` for the variable (the file's only build args are `DEBIAN_MIRROR` at `:48,97`
  and `UV_VERSION`/`UV_INSTALLER_SHA256` at `:74-75,118-119`).
- No supply route exists: every `args:` block in `docker/docker-compose.yml:73,128,245`,
  `docker-compose.override.yml:28,71,124,209` passes only `UV_VERSION`; no `.env*` file in the tree carries
  `VITE_API_URL`; no `frontend/.env*` file exists; `.dockerignore:72-73` (`.env*`, `**/.env*`) closes the
  file-based route.
- **Independent reproduction** (`npx vite build --outDir <temp>`, no `VITE_API_URL` set — the exact condition of
  `Dockerfile:28`): produces `assets/index-DIIOmI8l.js`, containing
  `var Qe='/api/v1',$e='VITE_API_URL';function et(){return Qe}function tt(){throw Error(\`Missing required
  environment variable: ${$e}\`)}` and the bundle tail `...}}),!1]})}tt(),he.createRoot(document.getElementById('root'))...`
  — the definition at offset 11486, the call at offset 17819, unguarded and immediately before `createRoot`.
  This reproduces the report's claimed bundle hash exactly, on a build this pass performed itself.
- **Control run** (identical build, `VITE_API_URL=https://dash.example.com` set): emits
  `index-FZWpJIu8.js` with **no** `Missing required environment variable` string and no `tt()` call site. The
  build-time substitution is the only thing that decides it.
- `docker/Dockerfile:212-214` copies the bundle into the edge image and guards only that `index.html` exists —
  which it does — and `:229` copies the same output into the app image. The Dockerfile's only bundle check
  therefore passes on a bundle that throws.
- `docker/nginx/nginx.conf.template:57-59` proxies `/api` to `app:8000` from the same origin, so the
  same-origin default at `env.ts:10` is exactly the value both proxies serve.

**Consequence** — The SPA served by the `prod` stage (`docker/Dockerfile:4` names `prod` as the default
target) throws during module evaluation, before `createRoot`, so `index.html`'s `<div id="root">` is never
populated and the API is unreachable from the browser. The blast radius is the whole deployment, not a
screen: every page is blank. Because the failure is a module-evaluation throw it lands only in the browser
console, so `docker compose logs app` and the nginx access log both show a healthy 200 for `/`. The dev server
is unaffected (`import.meta.env.DEV` is true), so every developer path stays green.

**Recommendation** — Executable as written; the target exists, is stable, and is load-bearing. Dropping the
throw and letting `getApiBaseUrl()`'s same-origin default stand is sufficient and is the smallest change,
because `nginx.conf.template:57-59` already serves that default. The report's two guards are both correct and
should be kept: do not hard-code `/api/v1` into the Dockerfile (it re-creates CFG-113's cross-language
duplication), and if an explicit value is wanted, make it a required build argument checked in the Dockerfile
so a missing value fails the build rather than the browser. One remediation blocker to name: `frontend/src/
shared/config/env.test.ts:25-29` asserts that a production build **throws** without the variable. That test
encodes the defect and must change with it. One false supporting citation in the input report is recorded as
VAL-02-006: `docs/06-backend/configuration.md:348-355` does not record a `VITE_API_URL` gate — it records
that `allowed_mime_types` was removed and `MimeTypeEnum` is the single declaration.
---

### CFG-103 — The production image ships the superuser as the last-resort default for the application role's connection

**Severity** — HIGH (re-derivation of the audited band's, sustained)

**Zone** — Tier divergence: which differences are deliberate, and which are unintended

**Observation** — CONFIRMED, with one omission in the input report that widens it. The code declares the
least-privilege default at `src/mkobi/config.py:260` (`user: str = "mkobi_app"`), and
`src/mkobi/settings/app.yaml:31` overrides it with `user: postgres` on a source that outranks the code default.
Every shipped compose tier then re-supplies the role as a literal, so no shipped stack escalates — that part
of the input report is correct. The defect is the shape, and this pass adds a second instance of it: the
operator-facing root template `.env.example:15` ships `DATABASE__USER=postgres`, naming the **superuser** as
the application role, and no compose file interpolates the name, so that line never takes effect while still
telling the operator the superuser is correct.

**Evidence** —
- `src/mkobi/config.py:260` and `src/mkobi/settings/app.yaml:27-33` verified verbatim; the trailing comment at
  `app.yaml:32-33` is the `_FILE` note the report refers to.
- **Independent reproduction** (`_env_file=None`, `DATABASE__PASSWORD` set, `DATABASE__USER` deliberately
  absent): `resolved database.user = postgres`, `DATABASE_URL =
  postgresql+asyncpg://postgres:S3cretAppPass@localhost:5432/bidb`. The escalation is real and needs no
  unusual configuration.
- Role supply, all literals and none interpolated: `docker-compose.yml:148` and `:259` (`mkobi_app`, the
  `app` and `rq-worker` blocks) and `:82` (`postgres`, the `migrate` block); `docker-compose.override.yml:147,221`;
  `docker-compose.test.yml:147`.
- `DATABASE__USER` is absent from `.env`, `docker/.env.example`, `docker/.env.development` and
  `docker/.env.production`; present only at `.env.example:15` — and inert, since no compose file interpolates
  `${DATABASE__USER}`.
- `docs/06-backend/configuration.md:85` documents the default as `mkobi_app`, and `:176-181` names the exact
  hazard ("the field would have fallen through to the next source down, which is `app.yaml`'s `postgres` —
  the **superuser** role"). So `app.yaml:31` contradicts the project's own documented default, which is a
  stronger statement than the input report makes.
- Superuser co-residence in the same process corroborated statically: `docker-compose.override.yml:149-150` and
  `:223-224` supply `DATABASE__ADMIN_USER: postgres` and a mandatory `DATABASE__ADMIN_PASSWORD`, and `.env:11`
  sets that password to `postgres`.

**Consequence** — `app.yaml` ships inside every image and is the last-resort source when a deployment omits a
name, and it resolves the application's database role to the superuser rather than the role the code declares
200 lines away. A deployment that supplies `DATABASE__PASSWORD` and omits `DATABASE__USER` connects as
`postgres` with no warning and no check that the role is unprivileged; a deployment that copies
`.env.example` believes the superuser is the correct application role. The `_FILE` route is warned about
(`configuration.md:176-181`); the plain environment-variable route is not. No shipped compose tier is affected
today, so the blast radius today is "an operator who omits or trusts one name".

**Recommendation** — Executable; the code is the better of the two choices. Remove `user: postgres` from
`app.yaml` so the code default applies when nothing supplies one, update the comment at `app.yaml:32-33` to
say so, and correct `.env.example:15` to `mkobi_app` (or remove it, since no compose file reads it — see
VAL-02-008). `docs/06-backend/configuration.md:85` then matches the code and needs no change. The report's
optional addition — a startup log line naming the *resolved* role, never the password — is a sound
visibility measure and `_log_initialization` (`config.py:1009-1018`) has the slot.

---

### CFG-102 — `init_settings` is the lowest-priority source, so every constructor kwarg is silently discarded

**Severity** — MEDIUM (re-graded **down** from the audited HIGH)

**Zone** — Settings source precedence, and the variant each running process resolves

**Observation** — CORRECTED. The mechanism is real and reproduces exactly; the band does not survive this
phase's own rubric. `init_settings` is the last element of the returned source tuple
(`src/mkobi/config.py:994-1000`), so pydantic-settings consults constructor `**data` last and any value the
YAML source supplies overrides it. What changes is the impact: **nothing in the repository exercises the
discarded path today**, so no production control is disabled and no test is currently asserting nothing.

**Evidence** —
- **Independent reproduction**, exactly the reported one:
  `Settings(environment='production', cors_origins=['https://forced.example'], data__max_rows_total=1)` returns
  `tier= development`, `cors= ['http://localhost:3000', 'http://localhost:5173']`, `max_rows_total= 20000`. All
  three requested overrides are dropped. The `cors_origins` come from `src/mkobi/settings/app.yaml:88-90`.
- The load-bearing line is `config.py:999` (`init_settings,`). The method definition is at `:967-975`, **not**
  at the `:989` the input report cites, and the report's quoted signature is a reflow that drops two declared
  parameters (`init_settings`, `file_secret_settings`) — recorded as VAL-02-002.
- **Corrected impact.** `src/` contains exactly one `Settings` construction that passes arguments:
  `get_config()` → `Settings()` at `config.py:1206`, with no kwargs. `tests/` uses
  `Settings(_env_file=None)`, which pydantic-settings consumes itself and which is therefore not evidence of
  the broken path. The input report's two consequences are both conditional — "any runtime override path
  built on the constructor" and "any *new* test". No such path exists.
- `config.py:590-594` (`UploadSettings.__init__`) does assume constructor `data` is authoritative, but
  `UploadSettings` is a plain `BaseModel`, not a settings source, so the inconsistency is latent, not live.
- `docs/06-backend/configuration.md:40-48` lists the same five source priorities as the code's own docstring at
  `config.py:978-983`, with "5 (lowest) Code defaults". Neither document mentions constructor kwargs — the
  report's DOC-UPDATE framing is right.

**Consequence** — `Settings(**data)` is a public constructor that accepts field arguments and ignores every one
of them for any field another source supplies. A future override written that way is a silent no-op, and a
test built on it passes while asserting nothing. The present-state effect is zero; the cost is a trap in the
single configuration object every component consumes.

**Recommendation** — Executable, and the smallest change is documentation: state in both
`config.py:976-986` and `docs/06-backend/configuration.md:40-48` that constructor kwargs are the
lowest-priority source. The code order itself is conventional and the report is right to leave it. If an
override path is ever genuinely needed, restore `init_settings` to first position rather than working around
it — but note that doing so would make the `_log_initialization` / `_log_security_warnings` side effects in
`Settings.__init__` (`config.py:1002-1007`) fire per construction, so it is not a free change.

---

### CFG-104 — Nine names in `.env.example` reach no container and are read by no process

**Severity** — MEDIUM (audited band, sustained; the inventory is understated)

**Zone** — Name universes: what code reads, what the shipped examples declare, and what the deployment supplies

**Observation** — CONFIRMED, and the list is one name short. All nine claimed names are interpolated by no
compose file and no Dockerfile, so setting them in `.env` changes nothing. A tenth name with the same root
cause was missed: `.env.example:15` (`DATABASE__USER=postgres`), which is inert for the same reason and
additionally names the superuser (CFG-103).

**Evidence** — Each name tested mechanically against every `${...}` interpolation in the three compose files
and the Dockerfile:

| Name | Result | Why inert |
|---|---|---|
| `DEBUG` | not interpolated | no service declares it; the field admits only the `DEBUG` env var |
| `RECREATE_TEST_DB` | not interpolated | supplied only by `docker-compose.test.yml` |
| `AUTO_MIGRATE` | not interpolated | removed from `docker-compose.yml:188`; hard-coded `"false"` at `docker-compose.override.yml:165` |
| `MIGRATION_SCRIPT_PATH` | not interpolated | and read by nothing (CFG-110) |
| `ALEMBIC_INI_PATH` | not interpolated | reaches the process only via the field default at `config.py:956` |
| `JWT__ACCESS_TOKEN_EXPIRE_MINUTES` | not interpolated | field default 15 applies |
| `UPLOAD__ALLOWED_EXTENSIONS` | not interpolated | `app.yaml:44-46` supplies the list |
| `TEST_DB_HOST_PORT` | not interpolated | interpolated only at `docker-compose.test.yml:47` |
| `TEST_REDIS_HOST_PORT` | not interpolated | interpolated only at `docker-compose.test.yml:73` |
| `TEST_APP_HOST_PORT` | not interpolated | interpolated only at `docker-compose.test.yml:185` |
| **`DATABASE__USER`** (missed by the input) | not interpolated | no compose file reads it; `app.yaml:31` wins |

- The three host ports are the sharpest case and the mechanism is confirmed: `$TestCompose` at
  `Makefile.ps1:36` is `@('-p', $TestProject, '-f', 'docker/docker-compose.test.yml')` — **no `--env-file`** —
  while the host-port documentation tells operators to set them in a file.

**Consequence** — An operator who follows `.env.example` to shorten the access-token TTL, change the upload
extension list, or run parallel checkouts on different ports edits a value that is discarded with no message.
There is no runtime failure and no security exposure; the cost is a template that makes promises the stack
cannot keep, and `.env.example` is the file an operator copies to `.env` and then trusts.

**Recommendation** — Executable; delete the eight unread names, move the three host ports into a comment block
naming `docker/docker-compose.test.yml` as their only consumer and stating that the test stack is invoked
without `--env-file` (so they must be exported in the shell), and set `.env.example:15` to `mkobi_app` or
remove it with the rest. Check `docs/11-guides/docker.md` and `docs/10-deployment/deployment.md` in the same
pass: they document the host ports as file-configurable, so deleting the template line without correcting the
docs leaves the same defect in a second place.

---

### CFG-106 — Production accepts `DATABASE__ADMIN_PASSWORD=postgres`: the superuser field gets only a prefix/emptiness check

**Severity** — MEDIUM (audited band, sustained)

**Zone** — Guarded preconditions: presence, strength, and whether the refusal is actionable and secret-free

**Observation** — CONFIRMED, with a corrected title. `Settings.validate_production_credentials` checks the
superuser password for exactly two clauses — the `change_me` prefix and emptiness — while the three sibling
credential fields each also get an exact-weak-membership test and (for the admin password) a length floor.
`postgres` is a member of `WEAK_PASSWORDS`, satisfies neither check, and is accepted at the production tier.
The input report's title attributes this to "the production admin bootstrap" having a different predicate; that
is backwards — `DatabaseStarter.ensure_admin_user()` calls the *same*, stricter `is_weak_admin_password` and is
the safer of the two copies. The divergence is on a field neither copy examines. Recorded as VAL-02-004.

**Evidence** —
- `src/mkobi/config.py:886-897` verified verbatim: `is_placeholder_credential(db_admin_password)` at `:888`,
  `not db_admin_password.strip()` at `:893`, nothing else. `WEAK_PASSWORDS` contains `"postgres"` at
  `config.py:64`. `DatabaseSettings.validate_admin_password_strength` (`config.py:338-358`) supplies only the
  8-character floor from `ADMIN_PASSWORD_MIN_LENGTH` (`:69`) — no membership test anywhere.
- **Independent reproduction**, production tier with a strong admin password, a 34-character JWT secret, a
  non-placeholder CORS list and a strong `DATABASE__PASSWORD`: `ACCEPTED -> admin_password = 'postgres'`,
  `TEST_ADMIN_DATABASE_URL = postgresql+asyncpg://postgres:postgres@localhost:5432/postgres`. The accepted value
  flows straight into a live superuser URL.
- Contrast on the same field set: `DATABASE__PASSWORD` **is** refused for an exact weak member
  (`config.py:871-876`), and `ADMIN_PASSWORD` is refused for weak / placeholder / empty / short
  (`config.py:786-803`). The superuser field is the only one of the four with no membership test.
- The report's own reachability caveat is correct and was verified: the `app` block
  (`docker-compose.yml:141-188`) carries no `DATABASE__ADMIN_*` key at all, so the shipped production stack
  never sets this field. `migrate` does receive `DATABASE__PASSWORD` as the superuser password (`:82`).
- `docs/06-backend/configuration.md:220-225` and `:231-233` are quoted accurately by the input report, and the
  asymmetry it describes — the settings guard narrower than the starter outside production — is real.
  `db/starter.py:492` resolves and does call `is_weak_admin_password`, though the report's quoted snippet is a
  reflow (VAL-02-002).

**Consequence** — The superuser credential is the one whose compromise matters most: it can `CREATE DATABASE`,
and `DatabaseStarter.recreate_test_database` (`db/starter.py:331-336`) uses exactly this URL for
`DROP`/`CREATE DATABASE` against a name matched by `TEST_DATABASE_NAME_PATTERN`. A production deployment can
therefore carry a superuser password the project has already declared weak, and nothing objects. No shipped
deployment is affected today; the exposure begins the moment an operator adds the field, which the name's own
documentation at `configuration.md:272-276` invites.

**Recommendation** — Executable, and the code is what should change — the documented intent is a shared
predicate. In `validate_production_credentials` (`config.py:886-897`) add the two clauses the other three
fields already carry: `is_weak_credential(db_admin_password, WEAK_PASSWORDS)` and a floor against
`ADMIN_PASSWORD_MIN_LENGTH`. Then correct `docs/06-backend/configuration.md:220-233`, whose table describes the
username asymmetry accurately but implies the password rows are symmetric. Rollout note: this is the only
guard in the file that can refuse a configuration a running deployment currently accepts, so the change must
land with a note in the deployment docs, and any environment currently running the superuser password through
this field will start refusing at boot.

---

### CFG-107 — `Settings` exposes five compatibility properties that nothing reads

**Severity** — MEDIUM (audited band, sustained on the corrected inventory)

**Zone** — Assigned, derived and branched configuration that nothing reads

**Observation** — CORRECTED. The mechanism survives; the inventory does not. `Settings` exposes 16 properties,
of which exactly **five** have no reader anywhere in `src/`: `jwt_secret_key`, `jwt_algorithm`,
`frontend_dist_dir`, `admin_user`, `admin_pass`. The input report claims seven and names four symbols that do
not exist on `Settings` at all. Its cited definition lines resolve to properties that *are* read, so a
reviewer trusting the table would invert the finding. Recorded as VAL-02-005.

**Evidence** —
- Enumerated by introspection rather than by reading: `Settings.__dict__` yields 16 `property` objects.
- Reader counts taken with a `config.` / `settings.` / `cfg.` / `_config.` prefix over `src/` only:
  `jwt_secret_key` 0, `jwt_algorithm` 0, `frontend_dist_dir` 0, `admin_user` 0, `admin_pass` 0. Live readers do
  exist for the rest — `upload_temp_dir` 2 (`services/file_cleanup.py:73`, `services/file_processing.py:199`),
  `max_file_size` 6, `TEST_DATABASE_URL` 4, `DATABASE_URL` 5, `allowed_file_types` 1, `lazy_threshold_mb` 1,
  `log_level` 1 (`app.py:45`), `log_file` 1 (`app.py:46`), `test_database_url` 2, `test_admin_database_url` 2.
- **Four claimed entries do not exist.** `Settings.redis_host`, `redis_port`, `redis_db` and
  `access_token_expire_minutes` are absent. The report's cited lines resolve elsewhere: `:1155-1157` and
  `:1159` → `frontend_dist_dir` (`config.py:1156-1159`); `:1163-1165` → `max_file_size` (`:1161-1164`);
  `:1140-1142` → `upload_temp_dir` (`:1141-1144`). A fifth claimed row, `max_rows_per_graph` /
  `max_rows_total`, are not `Settings` properties at all — they are `DataSettings` fields (`config.py:615,617`),
  which is exactly why the report's own note that `api/routes/data.py` reads `config.data` and uses
  `caps.max_rows_*` is the correct reading.
- The consumer claims that *are* correct: `core/redis_client.py:38-46` reads `config.redis.host/port/db`
  (the nested model, not an alias); `app.py:520`-region code reads `frontend.dist_dir`.
- The central hazard is confirmed: `docs/06-backend/configuration.md:342` lists `jwt_secret_key` in the
  `Key Properties` table, described as "map to nested config values", and it has zero readers. (The input
  report's list of that table omits `log_level`, which is present at `:346`.)
- `rg`-equivalent check across the whole repository finds no non-`src/` caller of any of the five, so the
  report's "no external consumer" question is answered: none is visible in tracked content.

**Consequence** — No runtime effect: an unread property is inert. The real cost is that `Settings` presents two
spellings for the same value with no way to tell which is canonical, and one of the duplicates —
`jwt_secret_key` — is presented by the documentation as a supported entry point. A maintainer following the
`Key Properties` table would reasonably reach for it and reasonably assume the rest of the table is equally
load-bearing. The drift the property table appears to exist to prevent is present in the table itself.

**Recommendation** — Executable but gated on the dead-code policy's investigate-first rule, and the
investigation is now complete for tracked content: nothing reads these five. Delete the five, keep the eleven
with live readers, and update the `Key Properties` table at `docs/06-backend/configuration.md:336-346` to match
exactly what survives. Note that `jwt_secret_key`'s removal is the one user-visible change in the docs, and it
should be called out in the commit rather than folded in silently. If an external consumer outside the
repository reads any of them, that cannot be settled here and should be confirmed by the coordinator first.

---

### CFG-108 — `_log_security_warnings` duplicates the weak-credential predicate inline and omits the `change_me` prefix clause

**Severity** — MEDIUM (audited band, sustained)

**Zone** — Guarded preconditions: presence, strength, and whether the refusal is actionable and secret-free

**Observation** — CONFIRMED, with three line citations corrected. `_log_security_warnings` is a third,
hand-rolled implementation of the weak-credential test, and it tests only the exact-membership half while its
message claims "weak/placeholder". The `change_me` prefix half — the clause the whole
`is_placeholder_credential` mechanism exists for, and the one that catches every shipped `CHANGE_ME_*` template
value — is not applied. The development tier's only credential signal is therefore silent on precisely the
values the shipped templates contain.

**Evidence** —
- `src/mkobi/config.py:1025-1053` verified verbatim: the three inline membership tests are at `:1036`
  (`database.password`), `:1043` (`admin_username`) and `:1049` (`admin_password`), each rebuilding a
  lowercased set, none calling `is_weak_credential` or `is_placeholder_credential`. The JWT branch at
  `:1057` has the same shape. The production guard's prefix clause is at `config.py:906-910`.
- `WEAK_PASSWORDS` (`config.py:53-65`) contains three `change_me`-family spellings, but none of them is the
  shape the templates actually use.
- **Independent reproduction**: a `development` tier with
  `ADMIN_PASSWORD=CHANGE_ME_GENERATE_STRONG_PASSWORD` and `ADMIN_USERNAME=CHANGE_ME_ADMIN_USERNAME` emits
  **zero** `Weak …` warnings. The narrow clause does work: an earlier run of this pass with exact weak
  members produced all three expected lines ("Weak database password detected", "Weak admin username detected",
  "Weak admin password detected"). Both halves of the claim reproduce.
- **Corrected citations**: the shipped value is at `docker/.env.development:19`, not `:15`;
  `docker/.env.example:19`, not `:14`; `.env:18`, not `.env:29` (`.env:18` is
  `ADMIN_PASSWORD=admin@example.com`; `.env:17` is the matching username).

**Consequence** — Nothing is being let through that the production guards would stop: this is a logging
defect, not a refusal defect. The cost is that an operator who brings up `docker/.env.development` unchanged
sees no warning about any credential in the file, while the log line's own wording claims it is reporting a
"placeholder value". The development tier cannot surface the mistake the production tier would later refuse,
and the message actively misdescribes what was tested.

**Recommendation** — Executable and the smallest correct change: replace the three inline membership tests with
`is_weak_credential(...)` and add the `is_placeholder_credential(...)` clause for `database.password` and
`admin_password`, so the message becomes true and the tier's warning surface matches the shipped templates.
No shipped test asserts the current absence of a warning, so no test change is required — but
`tests/test_config.py` should be extended to pin the new warning, or the fix is unprotected.

---

### CFG-109 — With `CORS_ORIGINS` unset, production fails on a placeholder rather than on a missing value, and the error names origins the operator never set

**Severity** — MEDIUM (audited band, sustained)

**Zone** — Tier divergence: which differences are deliberate, and which are unintended

**Observation** — CONFIRMED, and independently hit by accident twice while reproducing other findings. The
gate itself is correct and fails closed. The defect is diagnostic: the refusal names origins that came from
`app.yaml`, not from the operator's environment, so a production operator who has set nothing reads an error
that implies they supplied a bad value.

**Evidence** —
- `docker/docker-compose.yml:169-172` verified verbatim: the Compose default
  `CORS_ORIGINS: ${CORS_ORIGINS:-["http://localhost:5173"]}` and the comment stating the intent — a missing
  value fails closed at startup.
- `src/mkobi/config.py:839-857` refuses any placeholder origin at the production tier;
  `CORS_ORIGINS_PLACEHOLDERS` at `:832-837` contains `http://localhost:5173`.
- **Independent reproduction**: `ENV=production` with `CORS_ORIGINS` unset produces
  `Value error, Placeholder CORS origins not allowed in production: ['http://localhost:3000',
  'http://localhost:5173'].` — two of the three named origins come from `app.yaml:88-90`, and the operator
  supplied none of them. The message lists them in list order, so the operator-configured-looking
  `http://localhost:3000` appears first and the Compose-supplied one second.
- The report's layering observation is correct: because `:172` substitutes before the container starts,
  `CORS_ORIGINS` is never unset inside the process, so "missing value fails closed" and "Compose's placeholder
  fails closed" are the same outcome reached by different means and the application cannot distinguish them.
- **Corrected citation**: the development override's CORS default is at
  `docker-compose.override.yml:166`, not `:163` (which is `LOGGING__LEVEL: DEBUG`).

**Consequence** — The failure is safe and the tier refuses to start, which is the right outcome. What the
operator gets is an error naming two localhost origins they never configured, in a multi-origin deployment
where one real domain and one placeholder are present the message names only the placeholder and the operator
must work out that the others came from a file they did not write.

**Recommendation** — Executable; the guard is right and the message and layering need work. The practical fix
is to make the Compose default the only placeholder that can arrive: drop `app.yaml:88-90` so the YAML layer
contributes no CORS origins at all, since the development override already supplies
`["http://localhost:3000"]` explicitly at `docker-compose.override.yml:166`. Rollout note: removing the YAML
list changes what a non-Compose, non-env-file run resolves, so it belongs with the documentation correction in
`docs/10-deployment/security-checklist.md`, not alone.

---

### CFG-113 — The frontend and backend have no shared configuration contract, and `/api/v1` is duplicated across two languages

**Severity** — MEDIUM (audited band, sustained)

**Zone** — Name universes: what code reads, what the shipped examples declare, and what the deployment supplies

**Observation** — CONFIRMED, with two false citations and one correction that makes the drift risk **larger**
than reported. The two configuration systems are indeed independent — no shared declaration, no shared name
registry, no generated type, no cross-check. But the backend's prefix is not a single declared constant in
`config.py` as the report states; it is **eleven independent string literals** in `src/mkobi/app.py:361-371`.
So `/api/v1` appears in at least thirteen places across two languages, not two, and the report's recommended fix
("derive the SPA's default from the backend's declared prefix") has no single backend constant to derive from
until one is introduced first. Recorded as VAL-02-006.

**Evidence** —
- `frontend/src/shared/config/env.ts:10` hard-codes `DEFAULT_API_BASE_URL = '/api/v1'` ✓;
  `frontend/vite.config.ts:9-14` proxies `/api` to `http://app:8000` under `server` (dev only) ✓.
- `frontend/src/shared/config/env.test.ts:14-17` asserts `getApiBaseUrl()` equals the literal `/api/v1`. There
  is no test anywhere that compares it to the backend's mounted prefix ✓.
- `docker/nginx/nginx.conf.template:57-59` proxies `location /api` to `app:8000` ✓ — and its own comment at
  `:55` says the prefix "matches FastAPI router prefix `/api/v1/*`", i.e. a third copy, in a comment.
- **False citation 1**: `src/mkobi/config.py:96` does not declare a prefix. Line 96 is
  `return value.lower() in {weak.lower() for weak in weak_values}`, inside `is_weak_credential`. No API prefix
  is declared anywhere in `config.py`.
- **False citation 2**: `src/mkobi/api/router.py` does not exist. The prefix is mounted literally at
  `app.py:361-371` (`application.include_router(..., prefix="/api/v1")`, eleven times).
- No `src/` file derives the SPA's default from the backend, and no build step compares them.

**Consequence** — Changing the API prefix requires finding string literals by search, across eleven backend
`include_router` calls and one TypeScript constant, with no test that fails when one is missed. The failure
surfaces as a runtime 404 from the SPA after deployment, not as a build or test failure. `docs/06-backend/
configuration.md` is 363 lines documenting the backend contract; there is no corresponding document for the
frontend's, and the frontend's one required variable is not mentioned in `docs/07-frontend/` at all.

**Recommendation** — Executable but its stated first step cannot be taken literally as written. The backend
must first declare the prefix **once** (a constant or a settings field that all eleven `include_router` calls
read); only then can the SPA's default be derived from it, which is also the durable fix for CFG-101 because
it removes the need for `VITE_API_URL` to be supplied at all. The report's remaining steps stand and are
correctly ordered after that: (1) a frontend test asserting the SPA default equals the backend's mounted
prefix; (2) documenting the frontend configuration surface in `docs/07-frontend/`. The eleven-call migration
has a wide blast radius — it touches every route registration — so it should land as its own change with the
full suite green before the frontend derives from it.

---

### CFG-105 — `JWTSettings.WEAK_SECRETS` holds seven entries the validator can never match

**Severity** — LOW (re-graded **down** from the audited MEDIUM)

**Zone** — A guard that runs, reports clean, and examines nothing

**Observation** — CORRECTED. The claim is true and measured: seven of nine entries are unreachable at this call
site. The band does not survive the rubric's instruction to rate what is true now. There is no exposure — the
unconditional 32-character guard refuses every one of those seven values first — so the defect is a
declaration that overstates its own reach, not a guard that fails open.

**Evidence** —
- `src/mkobi/config.py:396` declares the nine entries; `:408-415` declares the validator, with the
  unconditional length guard at `:408-411` **before** the membership test at `:412-415`. Both verified verbatim.
- **Independently measured**, by importing the class rather than by reading the set:
  `admin` 5 unreachable · `123456` 6 unreachable · `secret` 6 unreachable · `default` 7 unreachable ·
  `password` 8 unreachable · `change_me` 9 unreachable · `change_me_in_production` 23 unreachable ·
  `change_me_use_openssl_rand_hex_32` 33 reachable · `dev-secret-key-for-local-development` 36 reachable.
  Seven of nine unreachable — the report's table is exact.
- The safety net is intact and this is the load-bearing fact for the band: `JWT__SECRET_KEY` values shorter
  than 32 characters are refused by the length guard regardless of membership, so
  `JWT__SECRET_KEY=password` cannot get through.
- `docs/06-backend/configuration.md:257-259` describes the two checks accurately but attributes the weak-value
  refusal to the full list, which is true of two of nine.

**Consequence** — No security exposure today: a weak short secret is still refused, by the length guard. The
cost is that the list advertises a coverage it does not have, and that the two entries it does protect are
indistinguishable from the seven it does not. The stated hazard is contingent on a future change — a maintainer
reasoning from the list might relax the 32-character rule, at which point seven entries become live with no
signal that they had been dormant. `dev-secret-key-for-local-development` appears in this set only, so the
intent to refuse a recognisable local-development key rests entirely on the two long entries.

**Recommendation** — Executable; the prohibition list is the right shape, the entries are the problem. Prefer
dropping the seven unreachable entries and letting the length guard own short values, with one line documenting
that division of labour. Padding them into 32+ character forms is the worse of the two options. Note that
`change_me`-prefixed values are already caught in production by `is_placeholder_credential` (`config.py:906`),
which is prefix-based and therefore not length-bound — so nothing is lost by dropping them. Per the project's
dead-code policy this is investigate-then-decide: the list may predate the 32-character rule, in which case the
entries are residue rather than intent.

---

### CFG-110 — `migration_script_path` is declared, shipped, documented, plumbed through two layers, and read by nothing

**Severity** — LOW (audited band, sustained)

**Zone** — Assigned, derived and branched configuration that nothing reads

**Observation** — CONFIRMED. The setting is assigned in four places and threaded into
`DatabaseStarterConfig`, and nothing ever reads it. The Alembic path in force comes from `alembic.ini`'s own
`script_location`, resolved relative to the ini file.

**Evidence** — Every occurrence in `src/` and `tests/`, enumerated:
`src/mkobi/config.py:955` (field default `"alembic"`), `src/mkobi/settings/app.yaml:20`,
`src/mkobi/app.py:141` (passed into `DatabaseStarterConfig`), `src/mkobi/db/starter.py:141` (constructor
parameter) and `:151` (`self.migration_script_path = migration_script_path`). **Zero reads.** The input report
says the grep returns "exactly the five lines above plus the two in `db/starter.py`", which double-counts; the
true total is four Python sites plus the YAML line, and the substantive claim — no consumer — is confirmed.
`alembic.ini:8` (`script_location = %(here)s/alembic`, report cites `:5`) supplies the path actually in force,
and `db/starter.py:451,454` show the plumbing stopping one line short: `alembic_ini_path` is read and used,
`migration_script_path` is assigned and never touched. `.env.example:69` also declares it.

**Consequence** — No runtime failure. A configuration name appears in three operator-facing files, is threaded
through the application to a `DatabaseStarterConfig` field, and has no effect. Setting
`MIGRATION_SCRIPT_PATH` to anything but `alembic` changes nothing, because `alembic.ini`'s `%(here)s` anchor
wins. An operator who needs a relocated migration tree reaches for this setting, sees no effect, and gets no
signal about why — resolvable only by reading the ini.

**Recommendation** — Executable, gated on the dead-code policy's investigate-first rule, and the
investigation is complete: no consumer exists in tracked content. If this is a deliberate placeholder for a
planned relocation feature the fix is a comment saying so; otherwise remove the field from `Settings`, from
`DatabaseStarterConfig`, from `app.yaml:20` and from `.env.example:69`, and add one line to
`docs/06-backend/configuration.md` recording that the migration tree location is governed by `script_location`
in `alembic.ini` via `%(here)s`, so the next reader does not re-derive it.

---

### CFG-111 — `.env.docker` is an unread credential file in the working tree with no owner and no consumer

**Severity** — LOW (audited band, sustained)

**Zone** — Secret provenance, and every surface the material can reach

**Observation** — CORRECTED. The core assessment holds and is important: this is **not** a credential exposure,
and the report is right to say so. But the inventory is wrong in three places, and the recommendation is built
on a false premise about who reads `docker/.env.production`.

**Evidence** —
- The file exists at the repository root and is untracked: `git ls-files --error-unmatch .env.docker` fails.
- Ignored correctly on both axes: `git check-ignore -v .env.docker` →
  `.gitignore:158:/.env.*  .env.docker`, and `.dockerignore:72-73` (`.env*`, `**/.env*`) excludes it from every
  build context at every depth. No compose file uses an `env_file:` directive at all (0 occurrences), so the
  file cannot be picked up implicitly.
- **Corrected inventory**: the file holds **six** assignments, not eight —
  `DATABASE__PASSWORD=postgres`, `MKOBI_APP_PASSWORD=mkobi_app`, `JWT__SECRET_KEY=test_secret`,
  `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=admin`, `CORS_ORIGINS=http://localhost:3000`. The input report's
  table carries a row for `ENV` = `development`; **there is no `ENV` line in the file.** That row is fabricated.
- `JWT__SECRET_KEY=test_secret` is 11 characters and would be refused by `JWTSettings.validate_secret_key`
  (`config.py:408`); `CORS_ORIGINS=http://localhost:3000` is not a JSON array for `list[str]`. Both of the
  report's classifications are correct.
- **False premise, recorded as VAL-02-003**: the report states "`Makefile.ps1` names exactly two env files:
  `.env` (`:33`) and `docker/.env.production` (`:34`)". `Makefile.ps1` names **one**: `$DevCompose` at `:33-35`.
  There is no production compose variable anywhere in the file and no reference to
  `docker/.env.production` — verified by search. The file's owner is the operator, documented at
  `.ai/context/commands.md:25` and `.env.example:6-7` ("Run: `docker compose --env-file docker/.env.production
  -f docker/docker-compose.yml up -d`").
- Also corrected: the single tracked mention of `.env.docker` is at
  `.kilo/researches/phase-set-conventions-analysis.md:13`, under `.kilo/`, not under `.ai/` as reported.

**Consequence** — No exposure and no runtime effect: the material is real (it matches the running dev stack's
credentials) but untracked, unbuilt and unreachable. The risk is operational — a file named `.env.docker` next
to `.env` reads as the Docker-oriented variant of the root env file, so an operator debugging a container can
edit the file that does not configure it and see no effect. It is also a credential-shaped file with no owner
and no documentation; `docs/11-guides/docker.md` lists three env files without mentioning it.

**Recommendation** — Executable in direction, **but the stated rationale must be corrected before it is
acted on**: the replacement is not "what `Makefile.ps1:34` actually passes" — nothing passes it. It is the file
the operator invokes directly, per `.ai/context/commands.md:25`. On that corrected basis, delete
`.env.docker`: the credentials it holds are already in `.env` under the same ignore coverage, and
`docker/.env.production` is the tracked production template. Per the dead-code policy, confirm no out-of-band
runbook reads it first — the repository search is exhaustive for tracked content, but an external script would
not appear in it.

---

### CFG-112 — `staging` is a declared environment tier that no deployment pins and no guard covers

**Severity** — LOW (audited band, sustained)

**Zone** — Tier divergence: which differences are deliberate, and which are unintended

**Observation** — CONFIRMED. `staging` is a declared, documented, reachable tier that inherits the fully
permissive branch of every production gate, and no deployment selects it.

**Evidence** —
- `src/mkobi/models/enums.py:115-118` declares `PRODUCTION`, `STAGING`, `DEVELOPMENT`, `TEST` (class at `:111`).
- Every credential and posture guard is gated on `environment == EnvironmentEnum.PRODUCTION` and nothing else:
  `config.py:770` (admin credentials), `:827` (debug mode), `:847` (placeholder CORS origins), `:867`
  (production credentials), `:1071,1077` (`DATABASE_URL`).
- **Independent reproduction**: `ENV=staging` with `DEBUG=true`, `CORS_ORIGINS=["*"]`,
  `ADMIN_USERNAME=admin`, `ADMIN_PASSWORD=admin`, `DATABASE__PASSWORD=postgres` and
  `DATABASE__ADMIN_PASSWORD=postgres` → **accepted**, yielding `debug= True`, `cors= []` and
  `db_admin_pw= 'postgres'`. `validate_debug_mode` (`:827-828`) refuses the same value at the production tier;
  the wildcard is dropped rather than refused, leaving an empty allow-list.
- **Corrected citations**: the wildcard refusal is at `config.py:935-940` and the wildcard-dropping fall-through
  at `:941-951` — not `:920-924` / `:925-929`. The test-tier pin is at
  `docker-compose.test.yml:97,142`, not `:138`.
- Reachability confirmed by search: `staging` has zero references in `docker/` and `Makefile.ps1` (the one
  `git grep` hit is an unrelated "staging the snapshot" progress message). Production is pinned at
  `docker-compose.yml:79,144,256` and development at `docker-compose.override.yml:36,75,136,218` — the input
  report's pin line numbers (`:139,273` / `:85,162,242`) have drifted.

**Consequence** — A tier that is declared, documented as first-class in the enums reference and reachable, but
which no deployment uses and no guard covers, is a trap for the first person who selects it: they get a
deployment that looks production-shaped and is not, with `DEBUG=true` serving tracebacks, no credential floor,
and an empty CORS allow-list. The blast radius is bounded because it requires deliberately choosing `staging`,
and `docs/11-guides/docker.md:538` correctly notes that an env file cannot downgrade the Compose-pinned
production tier.

**Recommendation** — Executable; the absence of a pinned `staging` deployment is deliberate and correct, and the
report is right not to file it as drift. The finding is the unguarded tier. The better of the two fixes is to
give `staging` the same guard set as `production` by introducing one shared predicate
(`environment in (PRODUCTION, STAGING)`) at the five gate sites, which also removes the five-way duplication the
report correctly identifies as fragile; the alternative — removing `STAGING` from `EnvironmentEnum` and its two
documentation rows — is better if a staging deployment is not wanted. Rollout note: changing the gate set is a
small edit with a wide blast radius, because today the five sites are independent and a partial application of
the change would leave them disagreeing.

---

### CFG-114 — `CORS_ORIGINS_PLACEHOLDERS` is a bare `set[str]` where the project's convention is a `StrEnum`

**Severity** — LOW (audited band, sustained)

**Zone** — Guarded preconditions: presence, strength, and whether the refusal is actionable and secret-free

**Observation** — CONFIRMED, with one wrong citation. The refusal set is a bare set literal, and the project's
own rule requires fixed vocabularies to be declared as enums kept in `models/enums.py`.

**Evidence** —
- `src/mkobi/config.py:831-837` verified verbatim: `CORS_ORIGINS_PLACEHOLDERS: ClassVar[set[str]]` with exactly
  four entries. Used correctly at `:850`; the guard works.
- **Corrected citation**: the rule is at **`.kilo/rules/project.md:29-30`**, not `:10` — the input report
  confused the rule's item number ("10. **StrEnum for All Constants**") with a line number. The quoted text is
  otherwise exact.
- The precedent the report invokes is real: `MimeTypeEnum` (`src/mkobi/models/enums.py`) is the existing shape
  for a fixed vocabulary configuration cannot widen, and `docs/06-backend/configuration.md:348-355` records
  that the admitted MIME set is now declared in exactly one place.
- `https://your-domain.com` (`config.py:836`) has no counterpart anywhere in the repository — confirmed.

**Consequence** — No runtime failure. The cost is that a fifth placeholder origin — and there will be more,
since every `docker/.env.*` template adds one — must be remembered in a second location, and no test asserts
that the set covers the placeholders the shipped templates actually contain. That missing test is how CFG-109's
error message came to name origins the operator never wrote.

**Recommendation** — Executable; the `MimeTypeEnum` precedent is the better choice, so the code is what should
change. Move the vocabulary to `src/mkobi/models/enums.py` — a `frozenset`-valued `StrEnum`, or a
`Final[frozenset[str]]` beside it if an enum of URL strings reads poorly — and import it at `config.py:831-837`.
Pair it with the test this finding's absence makes necessary: assert that every placeholder origin appearing in
`docker/.env.*` and `.env.example` is a member of the set, so a new template origin cannot be added without the
guard knowing about it.

---

## Distribution

Twelve of the fourteen findings land on the **configuration object's own boundary** — the declaration in
`config.py`, the file `app.yaml`, the templates under `.env*`, and the guards that read them. One (CFG-101) and
its contract-level twin (CFG-113) land on the **frontend build surface**, and one (CFG-111) on an **unowned file
in the working tree**. The single component carrying the most is `src/mkobi/config.py`, which is cited by nine
findings and holds the mechanism behind five of them.

- `src/mkobi/config.py` — CFG-102, 103, 105, 106, 107, 109, 110, 112 (8 findings)
- `src/mkobi/settings/app.yaml` — CFG-102, 103, 104, 109, 110 (5)
- `.env.example` / `docker/.env.*` — CFG-103, 104, 106, 111, 114 (5)
- `docker/docker-compose*.yml` + `Makefile.ps1` — CFG-101, 103, 104, 108, 112, 113 (6)
- `frontend/src/` + `docker/Dockerfile` — CFG-101, 113 (2)
- `src/mkobi/db/starter.py` — CFG-106, 110 (2)

By tier, the **production tier** carries the most: CFG-101 (its bundle cannot boot), CFG-103 and CFG-106 (its
credential guards have holes), CFG-109 (its refusal is misdiagnosed), CFG-112 (the tier one step below it has
no guards at all). The development tier carries the remainder and mostly in the *diagnostic* rather than the
refusal direction (CFG-108, CFG-109).

## Cross-Finding Analysis

Four causes are shared, and two of them bind the roadmap together:

- **One declaration, several readers, no single owner.** CFG-101, CFG-113 and — via its frontend half — CFG-109
  all reduce to a value the code requires but no surface supplies, and the reason no surface supplies it is
  that the required value was never declared anywhere as a constant. `/api/v1` exists as eleven literals in
  `app.py:361-371` plus `env.ts:10` plus an nginx comment, which is why there is nothing for the Dockerfile to
  pass.
- **The last-resort source is the weakest source.** CFG-103 (`app.yaml:31` → superuser), CFG-110
  (`app.yaml:20` → read by nothing) and, on the guard side, CFG-106 (`config.py:886-897` → superuser field with
  two clauses where its siblings have four) are all the same shape: the value a deployment gets when it forgets
  something is the one nobody reviews.
- **A security predicate re-implemented instead of called.** CFG-105 (a prohibition list the length guard makes
  partly unreachable), CFG-106 (a fourth credential field missing the membership test) and CFG-108 (a third
  inline copy of the membership test) are one mechanism — `is_weak_credential` and `is_placeholder_credential`
  exist and are correct, and each of these is a site that does not call them.
- **Template promises the stack cannot keep.** CFG-104 (nine-plus-one names read by nothing), CFG-111 (an
  unowned env file) and CFG-112 (a tier documented as first-class that nothing pins) are all operator-facing
  surfaces describing configuration the system does not honour.

CFG-102, CFG-107 and CFG-114 are independent of these and of each other.

## Roadmap

Ordered by cause, not by severity, because two of the groups must not be separated.

1. **Un-break the production bundle first** (CFG-101). Nothing else about the production tier can be verified
   from a browser while the SPA throws on the first byte. Must be true before step 2: a green frontend build and
   a reachable `/api/v1` from the served page.
2. **Declare the API prefix once, then derive** (CFG-113, and the durable half of CFG-101). Introduce a single
   constant or settings field that all eleven `app.py:361-371` `include_router` calls read; then make
   `env.ts:10`'s default derive from it rather than restate it. Must be true before step 3: one declared prefix,
   eleven call sites migrated, full suite green. This step is what makes CFG-101's fix correct-by-construction
   rather than a hard-coded third copy.
3. **Close the last-resort-source inversions** (CFG-103, CFG-110). Remove `app.yaml:31`'s superuser default and
   correct `.env.example:15`; resolve `migration_script_path`. Independent of each other; both must land before
   step 5, which rewrites the operator-facing templates.
4. **Make the credential predicates single-sourced** (CFG-106, CFG-108, CFG-105). Add the two missing clauses to
   `validate_production_credentials`, replace `_log_security_warnings`' inline tests with the shared helpers, and
   drop or pad the seven unreachable `WEAK_SECRETS` entries. These are three call sites of one mechanism and
   should be one change; order within the group is free.
5. **Make every operator-facing template honest** (CFG-104, CFG-111, CFG-114, CFG-109's message). Delete the
   unread names, correct the host-port documentation alongside them, delete `.env.docker` on the corrected
   rationale, move the placeholder set into `enums.py` with the coverage test, and drop `app.yaml:88-90` so the
   CORS error can stop naming origins the operator never wrote. Depends on steps 3 and 4 so the templates are
   rewritten once, not twice.
6. **Close the tier and the property gaps** (CFG-112, CFG-107). Unify the five production gates behind one
   predicate and extend it to `staging`; delete the five unread properties and correct the `Key Properties`
   table. Independent of everything above; last because both are documentation-and-shape changes that are easier
   to review once the configuration surface has stopped moving.

## Rollout Safety

Step 1 changes observable behaviour at the browser and touches one shipped test: `frontend/src/shared/config/
env.test.ts:25-29` currently asserts that a production build **throws** without `VITE_API_URL`, so it encodes
the defect and must change in the same commit. Any operator who has been working around the blank page by
setting `VITE_API_URL` at build time will, after the fix, have their value ignored in favour of the same-origin
default — harmless in the shipped nginx topology, worth a release note for anyone running a cross-origin
deployment.

Step 3 changes what a deployment resolves when it omits a name, which is precisely the case nobody tests:
`app.yaml:31` is the current fallback for `database.user`, so any environment relying on that fallback will
start connecting as `mkobi_app` after the change and will fail with an authentication error rather than
silently escalating. That is the correct direction, but it must be a deliberate break with the affected
deployments identified in advance, not a quiet patch.

Step 4 contains the only change in this roadmap that can make a currently-accepted configuration stop being
accepted: adding `is_weak_credential` and a length floor to `DATABASE__ADMIN_PASSWORD` means a production
deployment currently running that field with a weak superuser password will refuse at boot after the upgrade.
This is the intended outcome and it should ship with a note in the deployment documentation. Nothing in the
shipped production compose is affected — the `app` block (`docker-compose.yml:141-188`) does not set the field at
all.

Step 5 changes documentation that operators copy from, so the doc corrections must land with the template
corrections in the same pass; correcting one without the other leaves the same defect in a second place. No
runtime behaviour changes. Step 6's gate unification changes which tier a refusal applies to, and because the
five sites are independent today, a partial application would leave them disagreeing — the predicate must be
introduced and adopted in one change, not incrementally.

Nothing in this roadmap touches a schema, so no Alembic migration and no database rollback is involved.
Reverting any step is a source revert; the one exception worth naming is step 4, where a revert is safe because
no deployment can have come to depend on the *absence* of the guard.

---

## Validation-Level Findings (`VAL-`)

These are defects **in the audited report**, graded on this phase's scale by effect and blast radius. They are
kept out of the findings table above because that table's `Severity` column carries the audited phase's bands,
and mixing two scales in one column would be unreadable.

### VAL-02-001 — Systematic line-number drift across the compose files and two Python modules

**Severity** — MEDIUM · **Zone** — the report as a controlled artefact

Roughly fourteen citations resolve to different content than the report claims. Every load-bearing claim in
the report survived re-derivation, so this is repairable rather than a wrong approval — but a reader who opens
the cited lines lands on the wrong code. Examples: `docker-compose.yml:139` for `DATABASE__USER: mkobi_app`
(actually `:148`); `:273` for the third `ENV: production` pin (`:256`); `override.yml:85,162,242` for the
`ENV: development` pins (`:36,75,136,218`); `test.yml:138` for the test-tier pin (`:97,142`);
`config.py:989-1000` for the source tuple (`:994-1000`, method at `:967-975`); `config.py:920-924` for the
wildcard refusal (`:935-940`); `.kilo/rules/project.md:10` for the StrEnum rule (`:29-30`);
`alembic.ini:5` for `script_location` (`:8`). The pattern is consistent with the compose files and the two
Python modules having moved under the auditor, and the base context explicitly warns that this repository is
under concurrent modification.

### VAL-02-002 — Two evidence blocks are reflowed paraphrases presented as source

**Severity** — MEDIUM · **Zone** — evidence quality

The phase contract requires each finding to cite "the offending code". Two blocks do not reproduce what is in
the file. `config.py:989-1000` (CFG-102) shows a three-parameter signature; the real one has six and declares
`init_settings` and `file_secret_settings`. `db/starter.py:492-497` (CFG-106) shows a single inline
`if is_weak_admin_password(...)` with one `msg`; the real code assigns a local `is_weak_password` first, then
raises at `:493-497` and warns separately at `:498-499` with a different message. A reflow is not cosmetic here:
it hides that the second call site is a two-branch structure rather than one condition.

### VAL-02-003 — CFG-111's remediation rests on a false premise

**Severity** — MEDIUM · **Zone** — whether the recommendation can be carried out

The recommendation directs the reader to `docker/.env.production` because it is "what `Makefile.ps1:34` actually
passes". `Makefile.ps1` has no such reference and defines no production compose variable; the file is passed by
the operator directly, per `.ai/context/commands.md:25` and `.env.example:6-7`. The finding's own evidence
section contains the same false statement. A recommendation whose rationale is wrong cannot be carried out as
written, even though its conclusion happens to be right.

### VAL-02-004 — CFG-106's title misdirects the reader

**Severity** — MEDIUM · **Zone** — report repair before acting

The title attributes the defect to "the production admin bootstrap" having a divergent predicate. The bootstrap
calls the *same* predicate and is the stricter of the two copies; the divergence is on the superuser field,
which the title never mentions. A reader who trusts the title inspects `DatabaseStarter.ensure_admin_user()`,
finds the shared predicate as documented, and concludes there is nothing to fix.

### VAL-02-005 — CFG-107 counts four symbols that do not exist

**Severity** — MEDIUM · **Zone** — report repair before acting

`Settings.redis_host`, `redis_port`, `redis_db` and `access_token_expire_minutes` are not on `Settings`, and a
fifth claimed row (`max_rows_per_graph` / `max_rows_total`) lists `DataSettings` fields as though they were
`Settings` properties. The report's cited definition lines for the phantom entries resolve to properties that
**are** read (`frontend_dist_dir`, `max_file_size`, `upload_temp_dir`), so a reviewer who trusts the table would
reach the opposite conclusion about those lines. The true count of unread properties is five, not seven.

### VAL-02-006 — CFG-113 and CFG-101 cite a nonexistent module and an unrelated line

**Severity** — MEDIUM · **Zone** — report repair before acting

`src/mkobi/api/router.py` does not exist, and `src/mkobi/config.py:96` is
`return value.lower() in {weak.lower() for weak in weak_values}` inside `is_weak_credential`, not an API
prefix declaration. Both claims are load-bearing for CFG-113's "derive from the backend's declared prefix"
recommendation, which cannot be executed until the backend declares the prefix once. Separately, CFG-101's
closing paragraph cites `docs/06-backend/configuration.md:348-355` as recording a `VITE_API_URL` gate; that
range records the **removal** of `allowed_mime_types`. CFG-101 does not depend on it.

### VAL-02-007 — One of the seven claimed direct runtime reproductions is static

**Severity** — LOW · **Zone** — evidence quality

The report claims "direct runtime reproductions: 7 of 14" and lists CFG-113 among them. CFG-113's reproduction
block is a description of two string literals and the nginx configuration — nothing was executed. The other six
were reproduced by this pass independently. A reproduction count that overstates by one is drift with no
remediation consequence, but it is the sort of number a reader uses to judge the report's rigour.

### VAL-02-008 — The report carries no front matter and no template-mandated per-finding fields

**Severity** — MEDIUM · **Zone** — the shared findings template as a controlled artefact

`.ai/audit/templates/audit-findings.md` mandates six front-matter fields (`phase`, `executed`, `executor`,
`problems-only`, `findings`, `by-severity`) and five per-finding fields, with `Zone` to be the block title
quoted verbatim. The audited report has **no** front matter at all — it opens with an H1 and a bold
`**Phase:**` line — and its per-finding fields are `severity` / `areas` / `kind` / `phase-task step` /
`duplicate-of`. The mandated `Zone` field is absent and the replacement `areas:` field is a paraphrase: CFG-101's
reads "Block 2 (name universes: a name read and never supplied)" where Block 2's actual title is "Name
universes: what code reads, what the shipped examples declare, and what the deployment supplies". This is
recorded, not repaired — the template is not this run's to fix.

---

## Adjudication Summary

Every finding carries a verdict, its own identifier (never renumbered), and the re-derivation behind it. The
audited namespace (`CFG-`) and the validation namespace (`VAL-`) are never mixed in one table.

| ID | Verdict | Audited band | Final band | Band moved | Basis for the verdict |
|---|---|---|---|---|---|
| CFG-101 | **CONFIRMED** | CRITICAL | CRITICAL | — | Fresh production build reproduces an unconditional module-scope throw before `createRoot`; control build with the variable set emits no throw; zero build surfaces supply it. The concurrent refactor added the missing *reader* and left the fatal *guard* intact. |
| CFG-103 | **CONFIRMED** | HIGH | HIGH | — | `app.yaml:31` overrides `config.py:260`; reproduced `database.user = postgres` with `DATABASE__USER` omitted. Widened: `.env.example:15` also names the superuser, and `configuration.md:85` documents `mkobi_app` — so app.yaml contradicts the project's own documented default. |
| CFG-102 | **CORRECTED** | HIGH | MEDIUM | ▼ | Mechanism reproduced exactly, but nothing exercises the discarded-kwargs path: `src/` has one `Settings()` call with no kwargs, tests use `_env_file` only. Rubric HIGH ("a production control silently disabled") is not satisfied. |
| CFG-104 | **CONFIRMED** | MEDIUM | MEDIUM | — | All nine names interpolated by nothing; the three host ports are interpolated only by a compose file invoked without `--env-file` (`Makefile.ps1:36`). Inventory understated: `.env.example:15` is a tenth. |
| CFG-106 | **CONFIRMED** | MEDIUM | MEDIUM | — | Production tier accepted `DATABASE__ADMIN_PASSWORD=postgres` and built `TEST_ADMIN_DATABASE_URL = …postgres:postgres@…/postgres`. Title corrected: the bootstrap shares the predicate; the divergence is on the superuser field. |
| CFG-107 | **CORRECTED** | MEDIUM | MEDIUM | — | Hazard real (`jwt_secret_key` documented at `configuration.md:342`, zero readers) but the inventory is wrong: five unread properties, not seven; four claimed entries do not exist. |
| CFG-108 | **CONFIRMED** | MEDIUM | MEDIUM | — | Development tier with the shipped `CHANGE_ME_*` credentials emits zero warnings; the exact-membership half fires. Three line citations corrected. |
| CFG-109 | **CONFIRMED** | MEDIUM | MEDIUM | — | Reproduced incidentally twice: the refusal names `http://localhost:3000` and `http://localhost:5173`, both from `app.yaml:88-90`, with the operator having set nothing. |
| CFG-113 | **CORRECTED** | MEDIUM | MEDIUM | — | No shared contract confirmed, but the backend prefix is eleven literals at `app.py:361-371`, not a constant in `config.py:96`; `api/router.py` does not exist. Drift risk is larger than reported. |
| CFG-105 | **CORRECTED** | MEDIUM | LOW | ▼ | Seven of nine entries unreachable — measured. But the unconditional 32-character guard refuses every one of them first, so there is no exposure; only a declaration that overstates its reach. |
| CFG-110 | **CONFIRMED** | LOW | LOW | — | Four declaration/assignment sites, zero reads; `alembic.ini:8` supplies the path in force. |
| CFG-111 | **CORRECTED** | LOW | LOW | — | Exposure assessment holds (untracked, ignored on both axes, no consumer). Inventory wrong: six assignments not eight, and the table's `ENV` row is fabricated. Recommendation's premise is false (VAL-02-003). |
| CFG-112 | **CONFIRMED** | LOW | LOW | — | `staging` accepted `DEBUG=true`, dropped `*` to an empty allow-list and a weak superuser password; zero references in `docker/` or `Makefile.ps1`. Three line ranges corrected. |
| CFG-114 | **CONFIRMED** | LOW | LOW | — | `config.py:831-837` verbatim; the StrEnum rule is at `.kilo/rules/project.md:29-30`, not `:10`. |

**Disposition tally — agrees with the fourteen verdicts above:**

| Verdict | Count | IDs |
|---|---|---|
| CONFIRMED | 9 | CFG-101, CFG-103, CFG-104, CFG-106, CFG-108, CFG-109, CFG-110, CFG-112, CFG-114 |
| CORRECTED | 5 | CFG-102, CFG-105, CFG-107, CFG-111, CFG-113 |
| REJECTED | 0 | — |
| Merged / re-typed / unsettled | 0 | — |

**Final severity counts for this phase** (audited namespace `CFG-`, after re-grading):

| Band | Audited | Final | Δ |
|---|---|---|---|
| CRITICAL | 1 | 1 | — |
| HIGH | 2 | 1 | −1 (CFG-102 → MEDIUM) |
| MEDIUM | 7 | 7 | — (CFG-105 → LOW offset by CFG-102 → MEDIUM) |
| LOW | 4 | 5 | +1 (CFG-105) |
| **Total** | **14** | **14** | — |

**Validation-level tally (`VAL-`, separate scale):** MEDIUM 7 · LOW 1 · total 8.

## Finding-ID Namespace Ruling

`CFG-` is **occupied** and phase 02 minted a second, non-colliding range rather than reusing it. Re-derived
from the working tree, not inherited: enumerating `git grep -o -E "CFG-[0-9]{3}"` across every commit reachable
from `--all` yields exactly `CFG-001 … CFG-010` and nothing beyond, and seven live reference sites survive in
`.ai/plans/_code-context/` (`09-test-coverage:375` CFG-006 · `10-production-ops:203` CFG-004 · `:329` CFG-006 ·
`:337` CFG-001 · `15-security-baseline:326` CFG-008/009 · `:327` CFG-006/007 · `:415` CFG-006), plus commit
`5b23240`. Minting from `CFG-101` upward is therefore correct and no second namespace was created.

**CFG-103 is a remainder, not a duplicate.** The live reference for the old `CFG-004`
(`10-production-ops-code-context.md:203`) concerns the *injected* superuser password reaching `app` and
`rq-worker`; the compose files no longer do that (`docker-compose.yml:148,259` supply `mkobi_app`).
`app.yaml:31` is a separate last-resort-source residue with a separate owner and a separate fix. Recording
rather than merging.

**Validation namespace.** `VAL-` is used for the eight defects in the report itself, in their own section, per
the 99-validation report contract. No `VAL-` identifier is minted inside the `CFG-` findings table.

---

## Appendices

### A. Verification method

Every citation was resolved mechanically against the working tree as it stands (`2026-10-05`, ~10:30–11:00
local). Static claims were re-derived by reading the cited files, not by trusting the report's quotes; behaviour
claims were reproduced by execution wherever execution was cheap. Where a citation did not resolve, `git log`
and `git status` were consulted; the drift is broad and consistent (VAL-02-001), not a stale single file.

**Reproductions this pass performed itself (7 findings, all from current source):**

| Finding | Method | Result |
|---|---|---|
| CFG-101 | `npx vite build --outDir <temp>`, no `VITE_API_URL` | `index-DIIOmI8l.js`; `tt()` invoked unconditionally before `createRoot`; throw string present |
| CFG-101 (control) | identical build, `VITE_API_URL` set | `index-FZWpJIu8.js`; no throw string, no call site |
| CFG-102 | `Settings(environment='production', cors_origins=[...], data__max_rows_total=1)` | `development` / `['http://localhost:3000','http://localhost:5173']` / `20000` |
| CFG-103 | `DATABASE__PASSWORD` set, `DATABASE__USER` omitted | `database.user = postgres`; `DATABASE_URL = …postgres:…@localhost:5432/bidb` |
| CFG-105 | imported `JWTSettings.WEAK_SECRETS`, measured reachability | 7 of 9 unreachable; lengths 5–23 |
| CFG-106 | `ENV=production`, `DATABASE__ADMIN_PASSWORD=postgres` | accepted; `TEST_ADMIN_DATABASE_URL = …postgres:postgres@…/postgres` |
| CFG-108 | `ENV=development`, `ADMIN_PASSWORD=CHANGE_ME_GENERATE_STRONG_PASSWORD` | zero `Weak …` warnings |
| CFG-109 | `ENV=production`, `CORS_ORIGINS` unset | refusal names `['http://localhost:3000','http://localhost:5173']` |
| CFG-112 | `ENV=staging`, `DEBUG=true`, `CORS_ORIGINS=["*"]`, weak credentials | accepted: `debug=True`, `cors=[]`, `db_admin_pw='postgres'` |
| CFG-107 | `Settings.__dict__` introspection + prefixed-reference counts over `src/` | 16 properties; exactly 5 with zero readers |

Both frontend builds were written to `C:\Users\Om\AppData\Local\Temp\kilo\fe-val-build-{1,2}`, outside the
repository. `frontend/dist` was read but never written. No file under `src/`, `frontend/src/`, `tests/`,
`alembic/`, `docker/` or any production/config file was modified, created or deleted by this pass.

### B. Coverage ledger (residual footer)

| Scope | Blocks / areas reached | Items examined | Settled | Left unsettled |
|---|---|---|---|---|
| CFG-101 | frontend build surface | 4 files + 3 build args blocks + 5 env files + `.dockerignore` | all | none |
| CFG-102–CFG-114 | backend config | `config.py` (1217 lines, read in full across 5 windows) | 13 of 13 | none |
| Doc citations | `configuration.md`, `project.md`, `alembic.ini`, `docker.md` | 12 cited ranges | 12 | none |
| Compose surfaces | 3 compose files, `Makefile.ps1`, `Dockerfile` | all `args:`, `ENV:` and `DATABASE__*` keys | all | none |
| Namespace | `CFG-` and `VAL-` | all commits reachable from `--all` + 7 live sites | all | none |
| Enumerations | `Settings` properties, `WEAK_SECRETS`, `.env.example` names, `.env.docker` keys | 16 / 9 / 32 / 6 | all | none |

**Claims that could not be settled in this environment, and why:**

1. **CFG-103's `docker exec mkobi-app-1` reproduction was not re-run.** The dev stack was not assumed to be up,
   and starting it would have required mutating runtime state. Not load-bearing: the same resolution was
   reproduced locally without Compose, which is the half the finding rests on. The superuser co-residence claim
   was instead confirmed statically (`docker-compose.override.yml:149-150,223-224` with `.env:11`).
2. **CFG-107's "no external consumer" question is settled for tracked content only.** A consumer in an
   untracked script or an out-of-band runbook cannot be observed from the repository. Recorded as an
   investigate-first precondition on the recommendation rather than as a finding.
3. **The live `.ai/audit/02-configuration-secrets/findings.md` was read once, at the start of this pass.** If
   concurrent work amended it after that read, any change made after it is outside this adjudication; the
   verdicts here are anchored to the revision present at read time. `git status` showed the directory as
   untracked (`?? .ai/audit/02-configuration-secrets/`), so no commit hash pins that revision — this is the one
   real limit on the pass.
4. **Nothing was unsettled about CFG-101.** It was the pass's priority check and it was settled three ways:
   current source, an independent build, and a control build.
5. **The working tree moved again during this pass, after the snapshot.** `git status` at the
   start of the pass showed four modified tracked files; at the end it showed ten — the additional
   six (`ChartRenderer.tsx`, `ChartRenderer.test.tsx`, `chartConversion.ts`, `api.types.ts`,
   `api/routes/data.py`, `models/data.py`, `models/types.py`, `test_aggregated_read_path.py`,
   `test_graphs.py`) are concurrent peer work, not this pass's. **No file cited by any of the
   fourteen findings is among them**, so no verdict in this report depends on the movement; every
   anchor above was resolved against the revision current at the time of reading. This is the second
   independent confirmation of the base context's warning, and it is why each finding here carries its
   own resolved line rather than a reference to the input report's.
