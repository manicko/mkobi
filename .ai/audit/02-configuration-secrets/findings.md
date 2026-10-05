# Findings: Phase 02 — Configuration & Secrets

**Phase:** `02-audit-configuration-secrets`
**Date:** 2026-10-05
**Auditor:** architecture-auditor
**Mode:** problems_only (no overview, no praise, no "what works" summary)

> **Note on the moving target.** `frontend/src/main.tsx`, `frontend/src/shared/config/env.ts` and `frontend/vite.config.ts` were refactored by concurrent work *during* this audit. Every frontend line citation below was re-verified against the current files after that change, and CFG-101's bundle reproduction was re-run end to end on the refactored source (same result, same bundle hash `index-DIIOmI8l.js`). No finding in this report rests on a pre-refactor reading. Backend, compose and documentation files did not move.

---

## Summary

- **Total findings:** 14
- **by severity:** CRITICAL 1 · HIGH 2 · MEDIUM 7 · LOW 4
- **by kind:** defect 6 · dead-code 3 · risk 3 · gap 2
- **by area** (first-listed area only; secondary areas are recorded in each entry's `areas:` field):
  - Block 1 (source precedence, variant selection, load-time vs per-use resolution) — 1 (`CFG-102`)
  - Block 2 (name universes, symmetric difference, inert names) — 4 (`CFG-101`, `CFG-104`, `CFG-111`, `CFG-113`)
  - Block 3 (guarded preconditions, duplicate guards) — 5 (`CFG-105`, `CFG-106`, `CFG-108`, `CFG-109`, `CFG-114`)
  - Block 4 (secret provenance, exposure surfaces) — 0 primary, 3 secondary (`CFG-101`, `CFG-103`, `CFG-111`)
  - Block 5 (tier divergence, material crossing a variant boundary) — 2 (`CFG-103`, `CFG-112`)
  - Block 6 (automated environments, config path) — 0
  - Block 7 (posture switches reachable by a running process) — 0
  - Block 8 (assigned/derived config nothing reads) — 2 (`CFG-107`, `CFG-110`)
  - Block 9 (config gates that examine nothing) — 0 primary, 1 secondary (`CFG-105`)
  - Block 10 (defaults wrong for the deployed environment) — 0 primary, 1 secondary (`CFG-101`)

  **Blocks 6, 7 and 9 are empty as primary areas, and the reason is recorded under "no findings" below rather than left as a silent zero** — this is a genuinely clean result for two of them and a structural observation for the third.
- **duplicates within this report:** 0. One cross-pass re-confirmation: **CFG-103** is the narrow remainder of the prior pass's `CFG-004` (see the namespace disclosure below).
- **not runnable:** 0
- **direct runtime reproductions:** 7 of 14 (CFG-101, CFG-102, CFG-105, CFG-106, CFG-108, CFG-112, CFG-113)

### Finding-ID namespace collision (required disclosure)

**The `CFG-` prefix is already occupied by `CFG-001 … CFG-010`,** minted by the previous phase-02 pass. The identifiers are referenced from seven places outside this report:

| Reference | Identifiers |
| --- | --- |
| `.ai/plans/_code-context/10-production-ops-code-context.md:337` | `CFG-001` (recorded as *half-closed*) |
| `.ai/plans/_code-context/10-production-ops-code-context.md:203` | `CFG-004` |
| `.ai/plans/_code-context/09-test-coverage-code-context.md:375` | `CFG-006` |
| `.ai/plans/_code-context/10-production-ops-code-context.md:329` | `CFG-006` (recorded as *closed*) |
| `.ai/plans/_code-context/15-security-baseline-code-context.md:327` | `CFG-006`, `CFG-007` |
| `.ai/plans/_code-context/15-security-baseline-code-context.md:326` | `CFG-008`, `CFG-009` |
| commit `5b23240` *docs(audit): add validated findings for all 16 audit phases* | `CFG-001 … CFG-010` (the two now-deleted files `.ai/audit/02-configuration-secrets/findings.md` and `…-validated-findings.md`) |

Verified by enumerating `git grep -o -E "CFG-[0-9]{3}"` across every commit reachable from `--all` over `.ai/**` and `docs/**`: the complete occupied set is exactly `CFG-001 … CFG-010`. No live `docs/` file references the prefix; every surviving reference is in `.ai/plans/_code-context/`.

Per the phase rule, this report does not reuse the occupied block. Identifiers are minted from **`CFG-101`** upward — the same offset phase 01 applied when it found `TOPO-001 … TOPO-008` occupied — leaving `CFG-001 … CFG-010` intact so no existing cross-reference silently changes meaning. **`CFG-006` today names a closed env-wiring finding and `CFG-001` a half-closed one; after this report lands, `CFG-106` is an unrelated superuser-credential guard gap and `CFG-101` is an unrelated blank-page defect.** Any tooling that resolves findings by identifier must treat the two ranges as separate until the coordinator decides whether to renumber this report down into `001 … 014` or keep the offset.

**None of this report's findings is a duplicate of `CFG-001 … CFG-010`, and the reason is worth recording.** The prior block was written against a materially different `config.py`, and its subjects have since been remediated rather than re-reported:

| Prior ID | Prior subject | State now |
| --- | --- | --- |
| `CFG-001` | Production compose resolved `ENV=development` from `.env`, disabling every guard | Remediated — `docker-compose.yml:79,139,273` pin `ENV: production` as a literal |
| `CFG-002` | Shipped placeholder tokens passed the weak-credential guards | Remediated — `is_placeholder_credential` (`config.py:100-116`) adds the `change_me` prefix clause |
| `CFG-003` | `ADMIN_PASSWORD`/`ADMIN_USERNAME` accepted empty and whitespace | Remediated — `.strip()` and length checks at `config.py:796-803` |
| `CFG-004` | Superuser password injected into `app`/`rq-worker` | Remediated — least-privilege change; `app.yaml:31` is now the residue, filed as **CFG-103** |
| `CFG-005` | `.dockerignore` did not cover the build context | Remediated — `.dockerignore:72-73` |
| `CFG-006` | `RATE_LIMITER_FAIL_CLOSED` / `UPLOAD__MAX_FILE_SIZE_MB` documented but unsupplied | Remediated — supplied at `docker-compose.yml:185-186` |
| `CFG-007` | Seven declared names read by nothing (`upload.temp_dir_prefix`, `dashboard.default_items_per_page`, `logging.format`, `Settings.host`/`port`, `Settings.load_yaml_config`) | Remediated — every listed field is gone from source (only stale `tests/__pycache__/*.pyc` bytes remain). **CFG-107** in this report is a *different* symbol set: seven `Settings` compatibility *properties*, not seven removed *fields* |
| `CFG-008` | `SecretsFileSource` read `LOGGING__LOG_FILE` as a secret pointer | Remediated — the allow-list (`config.py:447-451`) excludes it |
| `CFG-009` | CORS wildcard refusal unreachable; the field validator stripped `*` first | Remediated — `config.py:920-924` refuses `*` at the production tier |
| `CFG-010` | Four documentation defaults no longer matching the code | Superseded by the documentation corrections this report also requests (**CFG-102**, **CFG-106**) |

The one genuine re-confirmation across the two passes is the `app.yaml` database-role residue: `CFG-004` moved the *injected* superuser password out of `app` and `rq-worker`, and **CFG-103** records that `app.yaml:31` still names the superuser as the last-resort default for a deployment that omits `DATABASE__USER`. That is a narrow, specific remainder of the old finding, not the old finding itself.

### Explicit "no findings" areas

- **Block 6 (automated environments and their configuration path) — no findings.** `docker/docker-compose.test.yml` is hermetic and internally consistent: its application-role password comes from the same `MKOBI_APP_PASSWORD` variable the base stack derives the role from (`docker/init-scripts/01-create-app-role.sh:25`, paired with `docker-compose.test.yml:37`), its role separation mirrors the base file's least-privilege split (`test-app` connects as `mkobi_app` at `docker-compose.test.yml:147`, `test-migrate` as `postgres` at `:102`), and its `ENV=test` pin (`:97`, `:142`) correctly relaxes every production-gated guard without weakening anything a non-test tier relies on. `tests/conftest.py:68-69` sets the same values by `setdefault` into `os.environ` for the host-side path, and the per-run `bidb_test_<token>` database means two concurrent runs cannot collide. The one structural observation — that the tier carries fixed, publicly-known credentials — is deliberate and documented at `docker-compose.test.yml:14` and `docs/06-backend/testing.md`, and Phase 12 owns the container-port exposure question; it is not a configuration defect.
- **Block 7 (a posture switch that changes only part of a running process) — no findings.** Every posture-relevant consumer reads through `get_config()` at its own point of use rather than from a value captured at import: `app.cookie_secure` is read per cookie emission (`core/security.py:468,488`), `rate_limiter_fail_closed` per limit decision (`api/routes/auth.py:203`, `upload.py:180`, `client_errors.py:105`), `cors_origins` once at `create_app` (`app.py:345`, which is correct for middleware), `debug` once at `FastAPI(debug=…)` construction (`app.py:333`, matching the object's lifetime), and `documents_enabled` once from the same pin (`app.py:317`). The `env`→`uvicorn --reload` dev behaviour is documented at `docker-compose.override.yml:79-83`. `setup_logging()` *is* import-time (`app.py:44`), which is a logging-init finding owned by Phase 01 as `TOPO-102`, not a configuration-surface split — and notably it is not a *split*: `LOGGING__LEVEL` is read once by the one function that installs handlers, so there is no divergence to report here.
- **Block 9 (a configuration gate that examines nothing) — no findings.** The two gates closest to this shape both examined something. `validate_password_not_placeholder` (`config.py:317-336`) returns its input unchanged and is therefore dead as a *validator* — but it is explicitly a documented marker, its own comment states that "Placeholder rejection for production is handled in `Settings.DATABASE_URL`", and `DATABASE_URL:1077-1082` does perform that check, so the pair is correct rather than vacuous. The genuine instance of this shape in the subsystem is the unreachable prohibition list, filed as **CFG-105**. `SECONDARY_TEST_DATABASE_NAME_PATTERN` (`db/starter.py:128`) is unreachable by design, and its own comment plus `tests/test_starter.py:600-630` pin the subset property that keeps it harmless — the documented defence-in-depth case the dead-code policy explicitly exempts.
- **Block 10 (default wrong for the environment it is deployed into) — no findings.** The names with a host-shaped default that would normally qualify (`upload.temp_dir` → `user_data_dir(...)`, `frontend.dist_dir` → `frontend/dist`, `alembic_ini_path` → `alembic.ini`, `migration_script_path` → `alembic`) were each traced. The first falls out to an absolute path and every compose service overrides it with an absolute in-container path anyway; the other three are CWD-relative but every compose service sets `working_dir: /app` and the shipped image contains the artefacts at those exact paths. A host-shaped default exists and is harmless here; the real defects in this neighbourhood are the unread fields (**CFG-110**) and the `app.yaml` role residue (**CFG-103**), filed under their own blocks.
- **Secret files under version control — no findings.** `.env` and `.env.docker` are untracked (`git ls-files --error-unmatch` fails for both, `git log --all --oneline --name-only | Select-String '^\.env'` returns only `.env.example`), `.gitignore:158` (`/.env.*`) covers both, and `.dockerignore:72-73` (`.env*`, `**/.env*`) excludes every env file at every depth from every build context. No `SECRET_FIELD_REGISTRY` value and no `*_FILE` path appears in any committed file.
- **Variant selection is not env-file-settable in a deployed stack — no findings.** `docker/docker-compose.yml:79,139,273` pins `ENV: production` as a literal on all three Settings-constructing services and `docker/docker-compose.override.yml:85,162,242` pins `development`; neither is interpolated. An env file cannot downgrade the tier, which is what `docs/11-guides/docker.md:538` claims. The residual — that `staging` is a fully unguarded tier reachable from an env file on a *non*-compose deployment — is filed separately as CFG-113 because it is a different defect (a branch nothing pins), not a failure of the pin.

---

## Findings

### CFG-101 — The production SPA throws on first byte: `validateEnv()` runs at module scope and the image's build stage never supplies `VITE_API_URL`

- **severity:** CRITICAL
- **areas:** Block 2 (name universes: a name read and never supplied), Block 4 (secret/derived material reaching a surface), Block 10 (defaults)
- **kind:** defect
- **phase-task step:** "a name that is read and never supplied, produces a bound that a deployed configuration can never satisfy"
- **duplicate-of:** none

**Evidence**

`frontend/src/main.tsx:6-7` calls the guard at module top level, outside React and outside any error boundary:

```ts
 4: import { validateEnv } from './shared/config/env'
 5:
 6: // Validate environment variables before app initialization
 7: validateEnv()
 8:
 9: ReactDOM.createRoot(document.getElementById('root')!).render(
```

`frontend/src/shared/config/env.ts:38-45` makes that call fatal whenever the build is not a dev build and the variable is absent:

```ts
38: export function validateEnv(): void {
39:   if (import.meta.env.DEV) {
40:     return
41:   }
42:
43:   if (!import.meta.env.VITE_API_URL) {
44:     throw new Error(`Missing required environment variable: ${API_URL_ENV_VAR}`)
45:   }
46: }
```

The variable is supplied by no build surface. `docker/Dockerfile:16-28` is the stage the shipped bundle comes from, and it declares no build arg and no env for it:

```dockerfile
16: FROM node:20-alpine@sha256:fb4… AS frontend-builder
…
23: # Install dependencies (no cache mount …)
28: RUN npm run build
```

`docker/Dockerfile:212-214` then copies that exact output into the edge image, and `:229` copies it into the app image. The two only file-based supply routes are both closed: `.dockerignore:72-73` excludes `.env*` and `**/.env*`, so a `frontend/.env.production` would not reach the build context; and there is no `VITE_*` key in any compose `environment:`, `ARG` or `build.args` block (searched `docker/`, `Makefile.ps1`, and all three compose files — zero hits). `Makefile.ps1` never sets it for a host build either: `Invoke-FeLint`/`Invoke-FeTest`/`Invoke-Check` run `npm run lint`, `npm run test` and nothing that builds (`Makefile.ps1:189-215`).

**Direct runtime reproduction.** `npm run build` from `frontend/` with no `VITE_API_URL` in the environment — the exact condition of `docker/Dockerfile:28` — produces a bundle in which the guard survives minification and is invoked unconditionally at module scope:

```js
var Qe=`/api/v1`,$e=`VITE_API_URL`;function et(){return Qe}
function tt(){throw Error(`Missing required environment variable: ${$e}`)}
…
}),!1]})}tt()
```

The closing `tt()` is the call at `main.tsx:7`; it is not inside a branch. Control run: the same build with `VITE_API_URL=https://dash.example.com` set eliminates the throw entirely (`grep 'Missing required environment variable' dist/assets/index-*.js` → no match), which confirms the build-time substitution is the only thing that decides it. The dev server is unaffected because `import.meta.env.DEV` is true there, so `docker-compose.override.yml`'s Vite service and every developer's `npm run dev` are green — the failure exists only in the two production bundles.

**Impact.** The application served by `docker/Dockerfile` (default `prod` target) throws before `createRoot`, so `index.html`'s `<div id="root">` is never populated. The user sees a blank page and the API is unreachable from the SPA. Because the failure is a module-evaluation throw, the stack trace lands in the browser console, not in any server log — `docker compose logs app` and `nginx`'s access log both show a clean 200 for `/` and nothing about the failure, so the edge looks healthy while serving nothing. `docker/Dockerfile:213-214` verifies only that `index.html` exists, which it does, so the guard the Dockerfile *does* apply passes.

This is the same `VITE_API_URL` gate `docs/06-backend/configuration.md:348-355` records as having been deliberately kept for `allowed_mime_types`' successor; the intent (fail closed rather than silently calling the wrong host) is sound, but the guard is satisfied by no configuration the repository or its build can produce.

**Recommendation.** `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**. Decide the deployment's actual answer and make the guard match it. The edge already terminates TLS and proxies `/api/` to the app from the same origin (`docker/nginx/nginx.conf.template:57-59`), and the same-origin default `getApiBaseUrl()` returns (`frontend/src/shared/config/env.ts:10,20-28`) is exactly what both proxies serve — so the correct production value *is* that default, and the guard is refusing the only value the deployment can legitimately use. The cleanest resolution is therefore to drop the throw and let `getApiBaseUrl()`'s default stand, since the guard's stated purpose ("an explicit value is required so a misconfigured deployment fails loudly", `env.ts:35-36`) is not served by a variable no deployment can supply. If an explicit value is nonetheless wanted, it must become a documented required build argument checked in the Dockerfile, so a missing value fails the *build* rather than the browser. Do not simply point `VITE_API_URL` at a hard-coded `/api/v1` in the Dockerfile: that re-creates the cross-language duplication CFG-113 describes. Note that the failure mode a guard like this prevents — a bundle pointing at a developer's `localhost:8000` — is real, and it is better prevented by a build-time assertion than by a browser-time throw.

---

### CFG-102 — `init_settings` is the lowest-priority source, so every constructor kwarg is silently discarded

- **severity:** HIGH
- **areas:** Block 1 (source precedence), Block 3 (guarded preconditions)
- **kind:** defect
- **phase-task step:** "a load-time path and a per-use path for the same value that can disagree; a value the resolution depends on that the declaration does not admit"
- **duplicate-of:** none

**Evidence**

`src/mkobi/config.py:989-1000` places the init source last in the tuple:

```python
989:    def settings_customise_sources(
990:        cls,
991:        settings_cls: type[BaseSettings],
992:    ) -> tuple[PydanticBaseSettingsSource, ...]:
993:        return (
994:            env_settings,
995:            secrets_source,
996:            dotenv_settings,
997:            yaml_source,
998:            init_settings,
999:        )
```

pydantic-settings applies the tuple in order with the first source winning, so the `**data` a caller passes to `Settings(...)` is consulted *last* and any value the YAML source supplies overrides it. `src/mkobi/settings/app.yaml` supplies `cors_origins` (`:88-90`), `data` is absent but `upload.max_file_size_mb` is present (`:43`), and `debug`, `recreate_test_db`, `auto_migrate` and `migration_script_path` are all present (`:19-25`).

**Direct runtime reproduction.** Constructor kwargs are accepted and then dropped:

```
$ uv run python -c "from mkobi.config import Settings; \
    s = Settings(environment='production', cors_origins=['https://forced.example'], \
                 data__max_rows_total=1); \
    print(s.environment, s.cors_origins, s.data.max_rows_total)"
development ['http://localhost:3000', 'http://localhost:5173'] 20000
```

All three requested overrides are discarded; the values come from `app.yaml` and the field defaults. The requested tier `production` is the sharpest instance: a caller that explicitly asks for the production tier and the production CORS list gets the development tier and the localhost origins, with no error.

**Impact.** Two concrete consequences. (1) `tests/test_config.py` uses `Settings(_env_file=None)` in eight places (`:338, 348, 381, 388, 417, 1172, 1192, 1516`) — that works only because `_env_file` is consumed by pydantic-settings itself rather than becoming a field, so the tests are not exercising the broken path; but any *new* test or future caller that tries to pin a value by constructor will get a passing test that asserts nothing. (2) Any runtime override path built on the constructor would be a no-op, which is the kind of defect that survives review because the call reads as an override. Note this is also inconsistent with the project's own layering intent: `UploadSettings.__init__` (`:590-594`) is written on the assumption that constructor `data` is authoritative — `if "temp_dir" not in data or not data.get("temp_dir")` — and that assumption holds only because `UploadSettings` is not a settings source itself and is always constructed from already-resolved values by the outer model.

**Recommendation.** The code is the better choice here; the docstring is what needs fixing. `[DOC-UPDATE]`, **priority: recommended**, **effort: trivial**. `src/mkobi/config.py:977-986` already documents the correct order — "5. Default values from code" — so the code matches its own documentation and `docs/06-backend/configuration.md:40-48` matches too. The gap is that neither document states that *constructor kwargs* are the lowest-priority source, which is the fact a reader needs. Add one sentence to both. If an override path is ever genuinely needed, restore the conventional order (`init_settings` first) rather than working around it.

---

### CFG-103 — The production image ships the superuser password for the application role's connection, inherited from `app.yaml`

- **severity:** HIGH
- **areas:** Block 5 (tier divergence: material crossing a variant boundary), Block 4 (secret provenance)
- **kind:** defect
- **phase-task step:** "a value that is the declared default in one source and is overridden in every deployment — if the override can be absent, the weaker value is what a deployment gets"
- **duplicate-of:** none

**Evidence**

`src/mkobi/config.py:260` declares the least-privilege default the project's design calls for:

```python
260:    user: str = "mkobi_app"
```

`src/mkobi/settings/app.yaml:31` overrides it with the superuser, on the same source that outranks the code default:

```yaml
27: database:
28:   host: localhost
…
31:   user: postgres
```

`docker/docker-compose.yml:139` (and `:82` for `migrate`) then re-supplies the role per service, so the *deployed* stacks are correct:

```yaml
139:       DATABASE__USER: mkobi_app
```

All three compose tiers do supply it: `docker/docker-compose.yml` declares `DATABASE__USER` three times, `docker/docker-compose.override.yml` twice, `docker/docker-compose.test.yml` twice, and every declaration is a literal — none is interpolated from an env file. No deployment can therefore reach the escalation by accident. The residue is narrower, and it is what `app.yaml` is for: **the name is absent from four of the five shipped env files** (`.env.example` carries it at `:15`; `docker/.env.example`, `docker/.env.development` and `docker/.env.production` do not), so a deployment that supplies `DATABASE__PASSWORD` and omits `DATABASE__USER` resolves `database.user` from `app.yaml:31` and connects as `postgres`.

Confirming what the running process actually resolves, on the dev stack started by the documented command:

```
$ docker exec mkobi-app-1 python -c "from mkobi.config import get_config; c=get_config(); \
    print(c.DATABASE_URL); print(c.TEST_ADMIN_DATABASE_URL)"
postgresql+asyncpg://mkobi_app:postgres@db:5432/bidb
postgresql+asyncpg://postgres:postgres@db:5432/postgres
```

The application's credential is `mkobi_app:postgres`, and the superuser credential `postgres:postgres` is simultaneously present in the same process, in the same `Settings` object, because the dev stack supplies `DATABASE__ADMIN_PASSWORD: ${DATABASE__ADMIN_PASSWORD:?…}` (`docker-compose.override.yml:150` for `app`, `:224` for `rq-worker`) and `.env:11` sets it to `postgres`.

**Impact.** In the dev tier this is acceptable and is the documented convenience (`docs/06-backend/configuration.md:270-271` explicitly permits a weak development database). The defect is the *shape*: `app.yaml` — the file that ships inside every image and is the last-resort source when a deployment forgets a name — resolves `database.user` to the **superuser**, not the least-privilege role the code declares two hundred lines away. Any deployment that sets `DATABASE__PASSWORD` but not `DATABASE__USER` connects as `postgres`. `docs/06-backend/configuration.md:178-181` identifies exactly this hazard and mitigates it only for the `*_FILE` route, where a mis-set `DATABASE__USER_FILE` now warns. The plain environment-variable route has no such protection: `DATABASE__USER=whatever` in a deployment's env file, intended for a least-privilege role, is honoured with no warning and no check that the role exists or is unprivileged. Combined, a deployment that omits the name silently escalates; a deployment that supplies a wrong name silently escalades.

**Recommendation.** The code (`user: str = "mkobi_app"`) is the better of the two choices; `app.yaml` is the deviation. `[BEST-PRACTICE]` + `[DOC-UPDATE]`, **priority: recommended**, **effort: small**. Remove `user: postgres` from `app.yaml` so the code default applies when no environment supplies one, and update the comment at `app.yaml:32-33` to say so. `docs/06-backend/configuration.md:85` already documents the default as `mkobi_app`, so the doc needs no change — the code needs to match it. Separately, consider a startup log line naming the *resolved* role (never the password) so a privilege escalation is visible in `docker compose logs app`; `_log_initialization` (`:1011-1016`) already logs host and tier and has the slot.

---

### CFG-104 — Nine names in `.env.example` reach no container and are read by no process

- **severity:** MEDIUM
- **areas:** Block 2 (name universes, symmetric difference)
- **kind:** gap
- **phase-task step:** "a name that is supplied but never read"
- **duplicate-of:** none

**Evidence**

`.env.example` declares 31 names. Cross-referencing every name against (a) the `${…}` interpolations in `docker/docker-compose.yml` + `docker/docker-compose.override.yml`, (b) every `environment:` key in the resolved dev stack (`docker compose -p mkobi --env-file .env -f docker/docker-compose.yml -f docker/docker-compose.override.yml config`), and (c) the field set pydantic-settings actually admits, nine names reach nothing:

| Name | `.env.example` line | Why it is inert |
|---|---|---|
| `DEBUG` | 41 | Not interpolated by either compose file; no service declares it. The field's only admission is the `DEBUG` env var, and no container receives one. |
| `RECREATE_TEST_DB` | 71 | Not interpolated; supplied only by `docker-compose.test.yml:160`. `docs/11-guides/docker.md:552` says exactly this — so the line in `.env.example` is the defect, not the behaviour. |
| `AUTO_MIGRATE` | 68 | Not interpolated; `docker-compose.yml:188` removed it deliberately ("migrations handled by dedicated migrate service"). The dev override hard-codes `AUTO_MIGRATE: "false"` at `:165` (app) and `:245` (rq-worker). |
| `MIGRATION_SCRIPT_PATH` | 69 | Not interpolated, and read by nothing (see CFG-110). |
| `ALEMBIC_INI_PATH` | 70 | Not interpolated. Reaches the process only via the field default `alembic.ini`, which is correct. |
| `JWT__ACCESS_TOKEN_EXPIRE_MINUTES` | 29 | Not interpolated; the field default 15 applies. |
| `UPLOAD__ALLOWED_EXTENSIONS` | 33 | Not interpolated; `app.yaml:44-46` supplies the list. |
| `TEST_DB_HOST_PORT`, `TEST_REDIS_HOST_PORT`, `TEST_APP_HOST_PORT` | 48-50 | Interpolated, but by `docker/docker-compose.test.yml:47,73,185` only — and the test compose is invoked without `--env-file` (`Makefile.ps1:81-85`, and `.kilo/rules/commands.md:86`: "No `--env-file` is needed: the test compose is hermetic"). Setting them in the root `.env` therefore changes nothing. |

`docker/.env.development` and `docker/.env.production` have zero inert names (checked the same way), so the problem is confined to the root template.

**Impact.** Direct: an operator following `.env.example` to shorten the access-token TTL, switch the upload extension list, or enable the test-DB recreate edits a value that is discarded without any message, and the stack behaves as if the edit never happened. The three host ports are the sharpest case because they are documented in `docs/11-guides/docker.md:557` and `docs/10-deployment/deployment.md:341-345` as the supported way to run parallel checkouts, and the only file that appears to configure them (`.env.example`) is not the file the test stack reads. There is no runtime failure and no security exposure; the cost is a documentation surface that misleads. Severity is MEDIUM rather than LOW because `.env.example` is the file an operator copies to `.env` and then trusts.

**Recommendation.** `[DOC-UPDATE]`, **priority: recommended**, **effort: trivial**. Delete the eight names that nothing reads, and move the three host ports into a comment block that names `docker/docker-compose.test.yml` as their only consumer and states that the test stack is invoked without `--env-file` (so the operator must export them in the shell, not in a file). Keeping a name in a template is a promise that it does something; the template should not make promises the stack cannot keep.

---

### CFG-105 — `JWTSettings.WEAK_SECRETS` holds seven entries the validator can never match, because the length check runs first

- **severity:** MEDIUM
- **areas:** Block 3 (guarded preconditions), Block 9 (a prohibition list holding an entry the form can never produce)
- **kind:** dead-code
- **phase-task step:** "a prohibited-value list holding an entry the form can never produce"
- **duplicate-of:** none

**Evidence**

`src/mkobi/config.py:396` declares the list and `:408-415` declares the validator that consults it:

```python
396:    WEAK_SECRETS: ClassVar[set[str]] = {"password", "secret", "admin", "123456", "change_me", "default", "dev-secret-key-for-local-development", "change_me_in_production", "change_me_use_openssl_rand_hex_32"}
…
408:        if len(v) < 32:
409:            raise ValueError(
410:                "JWT secret key must be at least 32 characters for security"
411:            )
412:        if v.lower() in cls.WEAK_SECRETS:
413:            raise ValueError(
414:                "JWT secret key is too common. Please generate a strong secret."
415:            )
```

The length guard is unconditional and precedes the membership test, so only entries of 32 characters or more are reachable. Measured:

```
   5  'admin'                              reachable=False
   6  'secret'                             reachable=False
   6  '123456'                             reachable=False
   7  'default'                            reachable=False
   8  'password'                           reachable=False
   9  'change_me'                          reachable=False
  23  'change_me_in_production'            reachable=False
  33  'change_me_use_openssl_rand_hex_32'  reachable=True
  36  'dev-secret-key-for-local-development' reachable=True
```

Seven of nine entries are dead at this call site.

**Direct runtime reproduction.** Each dead entry is caught by the *other* guard with a different message, so the behaviour is safe — only the message and the list are wrong:

```
$ JWT__SECRET_KEY=SHORT_CANARY_1 uv run python -c "from mkobi.config import Settings; Settings()"
1 validation error for Settings
jwt.secret_key
  Value error, JWT secret key must be at least 32 characters for security
    [type=value_error, input_value='SHORT_CANARY_1', input_type=str]
```

The "too common" branch at `:413-415` is reachable only for the two long entries, and `docs/06-backend/configuration.md:258-259` describes it as the check that "refuses an exact, case-insensitive member of `JWTSettings.WEAK_SECRETS`" — true, but true of two of nine.

**Impact.** No security exposure: a weak short secret is still refused, by the length guard. The cost is that the list advertises a coverage it does not have, and the two branches it *does* protect are indistinguishable from the seven it does not. A maintainer reasoning about the guard will believe `JWT__SECRET_KEY=password` is caught by the weak-value check and may therefore shorten or relax the 32-character rule — at which point seven entries become live with no signal that they had been dormant. The list is also the only place `dev-secret-key-for-local-development` appears, so the intent to refuse a recognisable local-development key rests entirely on the two long entries.

**Recommendation.** The prohibition list is the right shape; the entries are the problem. `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**. Either drop the seven unreachable entries and let the length guard own short values (documenting that division of labour), or pad them into realistic 32+ character forms. Prefer the first: a shorter list is easier to audit, and `change_me`-prefixed values are already caught in production by `is_placeholder_credential` (`:906`), which is prefix-based and so not length-bound. Per the project's dead-code policy this is an *investigate-then-decide* item, not a delete-now item — the list may predate the 32-character rule, in which case the entries are residue rather than intent.

---

### CFG-106 — The production admin bootstrap has a different weak-credential predicate from the configuration guard that is documented as sharing it

- **severity:** MEDIUM
- **areas:** Block 3 (guarded preconditions: divergent copies of one guard), Block 5 (tier divergence)
- **kind:** defect
- **phase-task step:** "divergent copies of one guard are a finding"
- **duplicate-of:** none

**Evidence**

`docs/06-backend/configuration.md:214-233` states the relationship precisely and in a table:

> "The predicates live in `config.py` as `is_weak_admin_username()` and `is_weak_admin_password()`, and the bootstrap path in `DatabaseStarter.ensure_admin_user()` now calls the same two functions, so the two copies cannot drift apart. **They do not behave identically, by design**… | Weak **username**, production tier | **Raises** `ValueError` | **Warns** and proceeds |"

The username asymmetry is documented and deliberate, and this audit does not contest it. The **password** row above it is what does not hold. The documented table says both raise in production and both warn outside it, differing "only in breadth". In fact the two copies test *different fields*:

`src/mkobi/config.py:786-803` — the configuration guard, on `Settings.admin_password` (from `ADMIN_PASSWORD`):

```python
789:            if is_weak_admin_password(self.admin_password):
…
791:            if is_placeholder_credential(self.admin_password):
…
796:            if not self.admin_password.strip():
…
801:            raise ValueError(
802:                "Admin password is too short. Please choose a stronger password."
803:            )
```

`src/mkobi/db/starter.py:492-497` — the bootstrap guard, on the *same* `ADMIN_PASSWORD` value (`:485-486` reads `get_config().admin_username` / `.admin_password`, not `database.admin_*`):

```python
492:        if is_weak_admin_password(config.admin_password):
493:            msg = ("Admin password is a known weak/placeholder value. "
494:                   "Set ADMIN_PASSWORD to a strong, unique password.")
495:            if self._config.env == EnvironmentEnum.PRODUCTION:
496:                raise ValueError(msg)
497:            logger.warning(msg)
```

Here `is_weak_admin_password` is the *full* composite (`:118-130`: weak member **or** `change_me` prefix **or** empty **or** under 8 chars), so the starter's production refusal is a strict superset of what `validate_admin_credentials` refuses. That direction is safe.

The divergence is the opposite one, and it is in a field the documentation does not mention. `Settings.validate_production_credentials` (`:886-897`) checks `database.admin_password` — the *superuser* password used for test-DB creation, `DATABASE__ADMIN_PASSWORD` — for the placeholder prefix and emptiness only:

```python
886:            db_admin_password = self.database.admin_password
887:            if db_admin_password is not None:
888:                if is_placeholder_credential(db_admin_password):
…
893:                if not db_admin_password.strip():
```

There is no exact-weak-membership test and no length test on this field anywhere. `DatabaseSettings.validate_admin_password_strength` (`:338-358`) supplies only a floor of 8 characters.

**Direct runtime reproduction.** A production-tier `Settings` accepts an exact member of `WEAK_PASSWORDS` on that field:

```
$ ENV=production … DATABASE__ADMIN_PASSWORD=postgres uv run python -c "from mkobi.config import Settings; print(Settings(_env_file=None).database.admin_password)"
PRODUCTION accepted DATABASE__ADMIN_PASSWORD=postgres -> postgres
```

`postgres` is in `WEAK_PASSWORDS` (`config.py:64`). `.env:11` ships it as `DATABASE__ADMIN_PASSWORD`, and `.env.example:23` ships the `CHANGE_ME_GENERATE_STRONG_SECRET` placeholder that the prefix clause at `config.py:888` does catch — so the gap is exactly the exact-weak-member half, not the placeholder half. The same run shows the accepted value flowing into a live superuser URL: `TEST_ADMIN_DATABASE_URL = postgresql+asyncpg://postgres:SUPERSECRET…@db:5432/postgres`.

**Impact.** The superuser credential is the one whose compromise matters most — it can `CREATE DATABASE`, and `DatabaseStarter.recreate_test_database` (`:331-336`) uses exactly this URL for `DROP DATABASE`/`CREATE DATABASE` on a name matched by `TEST_DATABASE_NAME_PATTERN`. A production deployment can therefore run with a superuser password that the project has already declared weak, and no guard objects. This is not reachable on the production compose as shipped — `docs/11-guides/docker.md:560-564` records that `app` and `rq-worker` no longer receive `DATABASE__ADMIN_*` at all, and the base file confirms it (no `DATABASE__ADMIN_` key in the `app` block, `docker-compose.yml:132-188`) — but `migrate` does receive `DATABASE__PASSWORD` as the superuser password, and any operator who adds `DATABASE__ADMIN_PASSWORD` (a natural move, since the name exists and is documented at `configuration.md:272-276`) gets an unexamined superuser secret. Combined with CFG-107, the gap is one of degree, not of presence.

**Recommendation.** The predicate should be shared, which is the documented intent — so the code needs work, not the doc. `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**. In `validate_production_credentials` (`:886-897`), add the two clauses the other three credential fields already have: `is_weak_credential(db_admin_password, WEAK_PASSWORDS)` and a length floor against `ADMIN_PASSWORD_MIN_LENGTH`. Then correct `docs/06-backend/configuration.md:220-233`, whose table describes the username asymmetry accurately but implies the password rows are symmetric when in fact the configuration guard is the narrower of the two on `Settings.admin_password` and the superuser field is narrower still.

---

### CFG-107 — `Settings` exposes seven compatibility properties that nothing reads

- **severity:** MEDIUM
- **areas:** Block 8 (derived configuration that no consumer reads)
- **kind:** dead-code
- **phase-task step:** "a derivation that recomputes what the object already holds, where one copy is authoritative and the other is not"
- **duplicate-of:** none

**Evidence**

`src/mkobi/config.py:1126-1170` defines a block of alias properties. Counting every `config.<name>` / `settings.<name>` reference across `src/` (production code only):

| Property | Definition | `src/` references | Consumer |
|---|---|---|---|
| `Settings.admin_user` | `:1147-1149` | 0 | none — callers use `self.admin_username` |
| `Settings.admin_pass` | `:1151-1153` | 0 | none |
| `Settings.redis_host` | `:1155-1157` | 0 | none — `core/redis_client.py:36-46` reads `config.redis.host` |
| `Settings.redis_port` | `:1159-1161` | 0 | none |
| `Settings.redis_db` | `:1163-1165` | 0 | none |
| `Settings.jwt_secret_key` | `:1132-1134` | 0 | none — `core/security.py` reads `config.jwt.secret_key` |
| `Settings.jwt_algorithm` | `:1136-1138` | 0 | none |
| `Settings.access_token_expire_minutes` | `:1140-1142` | 0 | none |
| `Settings.frontend_dist_dir` | `:1159` (region) | 0 | none — `app.py:520` reads `get_config().frontend.dist_dir` |
| `Settings.max_rows_per_graph` / `max_rows_total` | — | 0 | none — `api/routes/data.py:138` reads `get_config().data` and uses `caps.max_rows_*` |

Six of these are also absent from the `Key Properties` table at `docs/06-backend/configuration.md:338-347`, which lists only `DATABASE_URL`, `TEST_DATABASE_URL`, `jwt_secret_key`, `upload_temp_dir`, `max_file_size` and `allowed_file_types`. `jwt_secret_key` is therefore both unread *and* documented as a supported entry point.

**Impact.** No runtime failure — an unused property is inert. The cost is that `Settings` presents two spellings for the same value, and a reader cannot tell which is canonical. The concrete hazard is `jwt_secret_key`: it is listed in the documentation's "Key Properties" table alongside six properties that genuinely are the used spellings, so a maintainer following the doc would reasonably use it and reasonably assume the rest of that table is equally load-bearing. Six of the seven dead properties duplicate a nested field that *is* read directly, which is exactly the drift the property table was presumably introduced to prevent.

**Recommendation.** `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**. Delete the properties with no consumer, keeping the four that `src/` actually reads (`DATABASE_URL`, `TEST_DATABASE_URL`, `upload_temp_dir`, `max_file_size`, `allowed_file_types`, `log_level`, `log_file` — the ones with live references), and update the `Key Properties` table in `docs/06-backend/configuration.md` to match whatever survives. Per the project's dead-code policy, investigate before deleting: these are plausibly retained for external consumers or for symmetry with the documented table, and the first question is whether anything outside `src/` (a script, a notebook, an operational runbook) reaches for them. `rg` over the repository finds no such caller.

---

### CFG-108 — `_log_security_warnings` duplicates the weak-credential predicate inline instead of calling the shared helper, and its database branch omits the `change_me` prefix clause the production guard uses

- **severity:** MEDIUM
- **areas:** Block 3 (divergent copies of one guard)
- **kind:** defect
- **phase-task step:** "duplicated guards: do the copies agree on the condition, on the skip rules and on the source they expect to read"
- **duplicate-of:** none

**Evidence**

`src/mkobi/config.py:1025-1053` is a third implementation of the weak-credential check, alongside `is_weak_credential` (`:80-97`) and the production guards that call it:

```python
1034:        # Check database password against known-weak values
1035:        if self.database.password:
1036:            if self.database.password.lower() in {p.lower() for p in WEAK_PASSWORDS}:
1037:                logger.warning(
1038:                    "Weak database password detected: DATABASE__PASSWORD uses a known "
1039:                    "weak/placeholder value. Generate a strong password for production."
1040:                )
…
1043:        if self.admin_username.lower() in {u.lower() for u in WEAK_USERNAMES}:
…
1049:        if self.admin_password.lower() in {p.lower() for p in WEAK_PASSWORDS}:
```

Three differences from the shared helper and the production guards:

1. It rebuilds the lowercased set on every call — `{p.lower() for p in WEAK_PASSWORDS}` three times, where `is_weak_credential` (`:97`) does the same but is at least one function. Minor.
2. The message says *"known weak/placeholder value"*, but only the exact-weak-membership half is tested. The `change_me`-prefix half — the clause the whole `is_placeholder_credential` mechanism exists for, and the one that catches every shipped `CHANGE_ME_*` template value — is not applied. `WEAK_PASSWORDS` (`:53-65`) contains only two `change_me` spellings (`change_me`, `CHANGE_ME`) and neither is the actual shape of the shipped templates: `docker/.env.development:15` ships `ADMIN_PASSWORD=CHANGE_ME_GENERATE_STRONG_PASSWORD`, which is not a member of the set.
3. `self.admin_password` is compared without the `.strip()` / emptiness handling the production guard has, and without a length check, so `ADMIN_PASSWORD="    "` is silent here.

**Direct runtime reproduction.** In the live dev container, with `ADMIN_PASSWORD=admin@example.com` (from `.env:29`, an exact weak member), the warning fires — the narrow clause works:

```
$ docker exec mkobi-app-1 python -c "from mkobi.config import get_config; get_config()" 2>&1
Weak database password detected: DATABASE__PASSWORD uses a known weak/placeholder value.
Weak admin username detected: ADMIN_USERNAME uses a known weak value.
Weak admin password detected: ADMIN_PASSWORD uses a known weak/placeholder value.
```

But the message's "placeholder" half is unearned. With a development-tier `ADMIN_PASSWORD=CHANGE_ME_GENERATE_STRONG_PASSWORD` — the value `docker/.env.development:15` and `docker/.env.example:14` actually instruct the operator to keep — nothing is emitted:

```
$ ADMIN_PASSWORD=CHANGE_ME_GENERATE_STRONG_PASSWORD uv run python -c \
    "from mkobi.config import get_config; get_config()" 2>&1 | grep -c "Weak admin password"
0
```

**Impact.** The development tier's only credential signal is silent on precisely the values the shipped templates contain. An operator who brings up `docker/.env.development` unchanged — which `docs/11-guides/docker.md:496-499` explicitly says works — sees no warning about any credential in the file, while the log line's own wording claims it is telling them about a "placeholder value". This is a logging defect, not a refusal defect: nothing is being let through that the production guards would stop. Its cost is that the tier's single warning surface is narrower than its own message and narrower than the templates it ships, so the development tier cannot surface the mistake the production tier would later refuse.

**Recommendation.** The shared helper is the right choice; this third copy is the deviation. `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**. Replace the three inline membership tests with `is_weak_credential(...)` and add the `is_placeholder_credential(...)` clause for `database.password` and `admin_password`, so the message becomes true. The breadth asymmetry with the production guards is then gone, and the two tiers warn about the same values the strong tier refuses.

---

### CFG-109 — With `CORS_ORIGINS` unset, the production stack fails to start on a placeholder rather than on a missing value, and the error names origins the operator never asked for

- **severity:** MEDIUM
- **areas:** Block 3 (guarded preconditions), Block 5 (tier divergence)
- **kind:** risk
- **phase-task step:** "a guard a deployed configuration can switch off; a value that is a secret only in one of the tiers it reaches"
- **duplicate-of:** none

**Evidence**

`docker/docker-compose.yml:169-172` supplies a Compose-level default so the variable is never absent:

```yaml
169:      # Default is a known placeholder origin: src/mkobi/config.py rejects it when
170:      # ENV=production, so a missing value fails closed at app startup instead of
171:      # silently serving a permissive policy.
172:      CORS_ORIGINS: ${CORS_ORIGINS:-["http://localhost:5173"]}
```

`src/mkobi/config.py:839-857` then refuses any placeholder origin at the production tier, and `CORS_ORIGINS_PLACEHOLDERS` (`:832-837`) contains `http://localhost:5173`. The comment describes the intent accurately. What the operator sees is not what the comment implies:

```
$ uv run python -c "from mkobi.config import Settings; Settings()"   # ENV=production, CORS unset
1 validation error for Settings
  Value error, Placeholder CORS origins not allowed in production:
  ['http://localhost:3000', 'http://localhost:5173'].
  Please set CORS_ORIGINS to your actual production domains.
```

Two of the three named origins — `http://localhost:3000` and `http://localhost:5173` — came from `app.yaml:88-90`, not from the operator's environment. Only `http://localhost:5173` is what Compose supplied, and it is listed second. The same run shows the interaction with the Compose default: because `:172` substitutes before the container starts, `CORS_ORIGINS` is *never* unset inside the process, so the intended "missing value fails closed" and the actual "Compose's placeholder fails closed" are the same outcome reached by different means — the application cannot distinguish them.

**Impact.** The failure is safe and the tier refuses to start, which is the correct outcome. The defect is diagnostic: a production operator who has set nothing gets an error naming two localhost origins they never configured, and the documented remedy (`docs/10-deployment/security-checklist.md`, referenced from `docs/11-guides/docker.md:529-531`) reads as though the operator had supplied a bad value. In a multi-origin deployment where one real domain and one placeholder are both present, the message names only the placeholder — correct, but the operator must work out that the *other* origins in the list came from a file they did not write. Severity is MEDIUM rather than higher because the gate itself is correct and `docs/11-guides/docker.md:536-539` does warn that `${VAR:?}` "enforces presence only, not strength", which is the same class of surprise stated for a different variable.

**Recommendation.** The guard is right; the message and the layering are what need work. `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**. Have `validate_cors_origins_not_placeholder` (`:847-856`) name only the origins that came from a source above `app.yaml` — the validator cannot see provenance, so the practical fix is to make the Compose default the *only* placeholder that can arrive: either drop `app.yaml:88-90` so the YAML layer contributes no CORS origins at all (the development override supplies `["http://localhost:3000"]` explicitly, `docker-compose.override.yml:163`), or keep the YAML list and change the Compose default at `:172` to a sentinel the application reports as unset. The first is simpler and removes the ambiguity permanently.

---

### CFG-110 — `migration_script_path` is configured, shipped in `app.yaml`, documented in `.env.example`, plumbed through two layers — and read by nothing

- **severity:** LOW
- **areas:** Block 8 (configuration that no consumer reads)
- **kind:** dead-code
- **phase-task step:** "a value that is assigned but never read"
- **duplicate-of:** none

**Evidence**

Four declarations and one assignment, zero reads:

- `src/mkobi/config.py:955` — `migration_script_path: str = "alembic"`
- `src/mkobi/settings/app.yaml:20` — `migration_script_path: "alembic"`
- `.env.example:69` — `MIGRATION_SCRIPT_PATH=alembic`
- `src/mkobi/app.py:141` — passed into `DatabaseStarterConfig(migration_script_path=config.migration_script_path, …)`
- `src/mkobi/db/starter.py:141` — constructor parameter; `:151` — `self.migration_script_path = migration_script_path`

Every read of the sibling field proves the plumbing stops one line short:

```python
151:        self.migration_script_path = migration_script_path
…
451:            alembic_ini = self._config.alembic_ini_path
452:
453:            # Override the database URL in alembic config
454:            config = Config(alembic_ini)
```

`alembic_ini_path` is read at `:451` and used at `:454`. `migration_script_path` is never read — `grep -rn "migration_script_path" src/ tests/` returns exactly the five lines above plus the two in `db/starter.py`, and no consumer. The path Alembic actually uses comes from `alembic.ini:5` (`script_location = %(here)s/alembic`), resolved relative to the ini file, not from this setting.

**Impact.** No runtime failure. The cost is a configuration name that appears in three operator-facing files, that is threaded through the application to a `DatabaseStarterConfig` field, and that has no effect: setting `MIGRATION_SCRIPT_PATH` to anything other than `alembic` changes nothing, because `alembic.ini`'s own `%(here)s` anchor wins. If a deployment genuinely needs a relocated migration tree, this setting is the obvious lever to reach for and it is inert — an operator would change it, see no effect, and have no signal about why. `alembic.ini:5` makes the actual mechanism (`%(here)s`) discoverable, so the confusion is resolvable, but only by reading the ini.

**Recommendation.** Per the project's dead-code policy, investigate before deleting: this may be a deliberate placeholder for a planned relocation feature, in which case it is future-proofing rather than dead code and the fix is a comment saying so. If not, `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**: remove the field from `Settings`, from `DatabaseStarterConfig`, from `app.yaml:20` and from `.env.example:69`, and add one line to `docs/06-backend/configuration.md` explaining that the migration tree location is governed by `script_location` in `alembic.ini`, resolved via `%(here)s` — so the next reader does not re-derive this.

---

### CFG-111 — `.env.docker` is an unread credential file in the working tree, with no owner, no documentation, and no consumer

- **severity:** LOW
- **areas:** Block 2 (name universes), Block 4 (secret provenance and exposure surfaces)
- **kind:** risk
- **phase-task step:** "classify every credential-shaped literal as real, placeholder or fixture"
- **duplicate-of:** none

**Evidence**

`.env.docker` exists at the repository root with 8 credential-shaped assignments, and nothing reads it. Searching the whole repository for a reference:

- `grep -rn "\.env\.docker"` across `src/`, `tests/`, `docker/`, `frontend/`, `Makefile.ps1`, `docs/`, `alembic/` → **zero hits**. The only mentions anywhere are two research/context notes under `.ai/` (`.ai/researches/phase-set-conventions-analysis.md:13`, which lists it as part of the repo shape, and `.ai/plans/_code-context/`), neither of which is an instruction to use it.
- `Makefile.ps1` names exactly two env files: `.env` (`:33`, the dev stack) and `docker/.env.production` (`:34`, the production stack). `.env.docker` appears in neither.
- No compose file uses `env_file:` at all (the project passes variables through the `${…}` interpolation mechanism plus per-service `environment:` blocks), so a file named `.env.docker` cannot be picked up implicitly.

Its contents, with classification:

| Name | Value | Classification |
|---|---|---|
| `DATABASE__PASSWORD` | `postgres` | **real** — the superuser password in the running dev stack |
| `MKOBI_APP_PASSWORD` | `mkobi_app` | **real** — the application role's password in the running dev stack |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin` | **real** — the dev admin credentials |
| `JWT__SECRET_KEY` | `test_secret` | **placeholder** — and unusable: 11 characters, so `JWTSettings.validate_secret_key` (`config.py:408`) would refuse it |
| `ENV` | `development` | n/a |
| `CORS_ORIGINS` | `http://localhost:3000` | n/a, but malformed for the field (`:913` requires a JSON array) |

So it is a stale, partially-usable copy of the real `.env`, with a JWT secret that would not survive construction and a `CORS_ORIGINS` that is not valid JSON for `list[str]`.

**Exposure assessment — the important half.** The ignore rules cover it correctly on both axes: `.gitignore:158` (`/.env.*`) matches it (`git check-ignore -v .env.docker` → `.gitignore:158:/.env.*  .env.docker`), and `.dockerignore:72-73` (`.env*`, `**/.env*`) excludes it from every build context at every depth. It has never been committed (`git log --all --oneline --name-only | Select-String '^\.env'` yields only `.env.example`). So this is **not** a credential exposure: the material is real but it is untracked, unbuilt and unreachable.

**Impact.** The risk is operational, not informational. A file named `.env.docker` next to `.env` reads as the Docker-oriented variant of the root env file, and its real values match the running dev stack — so an operator debugging a container can easily believe they are editing the file that configures it, change `MKOBI_APP_PASSWORD` there, and see no effect. It is also a credential-shaped file with no owner: nothing references it, nothing documents it, and `docs/11-guides/docker.md:475-477` lists exactly three env files (`.env`, `docker/.env.development`, `docker/.env.production`) without mentioning it. Severity LOW because there is no exposure and no runtime effect.

**Recommendation.** `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**. Delete it. If it was meant to be the production template, it is superseded by `docker/.env.production` (which is tracked, has `${VAR:?}`-compatible names, and is what `Makefile.ps1:34` actually passes), and the credentials it holds are already in `.env` with the same ignore coverage. Per the dead-code policy, first confirm no operator runbook or external script reads it — the repository search is exhaustive for tracked content, but an out-of-band script would not appear in it.

---

### CFG-112 — `staging` is a declared environment tier that no deployment pins and no guard covers

- **severity:** LOW
- **areas:** Block 5 (tier divergence), Block 3 (guarded preconditions)
- **kind:** gap
- **phase-task step:** "a branch nothing pins — confirm the absence is deliberate before recording it as drift"
- **duplicate-of:** none

**Evidence**

`src/mkobi/models/enums.py:111-117` declares four tiers:

```python
111: class EnvironmentEnum(StrEnum):
115:     PRODUCTION = "production"
116:     STAGING = "staging"
117:     DEVELOPMENT = "development"
118:     TEST = "test"
```

Every credential and posture guard is gated on `environment == EnvironmentEnum.PRODUCTION` and nothing else: `validate_admin_credentials` (`:770`), `validate_debug_mode` (`:827`), `validate_cors_origins_not_placeholder` (`:847`), `validate_production_credentials` (`:867`), `DATABASE_URL` (`:1071,1077`). `staging` therefore inherits the fully-permissive branch of every one of them, and additionally the wildcard-dropping branch at `:925-929` rather than the wildcard refusal at `:920-924`.

**Direct runtime reproduction.** A `staging` tier accepts a configuration that `production` refuses outright:

```
$ ENV=staging CORS_ORIGINS='["*"]' ADMIN_USERNAME=admin ADMIN_PASSWORD=admin \
  JWT__SECRET_KEY=<40 chars> DATABASE__PASSWORD=postgres DATABASE__ADMIN_PASSWORD=postgres \
  DEBUG=true uv run python -c "from mkobi.config import Settings; s=Settings(_env_file=None); \
  print('debug=',s.debug,'cors=',s.cors_origins)"
RESULT STAGING accepted: debug= True cors= []
```

`DEBUG=true`, which `validate_debug_mode` (`:827-828`) refuses at the production tier, is accepted. The `*` is dropped rather than refused, leaving an empty allow-list. The same weak credentials the production tier refuses on construction are accepted with only warnings.

No deployment pins this tier. `docker/docker-compose.yml:79,139,273` pin `ENV: production` as literals; `docker/docker-compose.override.yml:85,162,242` pin `development`; `docker/docker-compose.test.yml:138` pins `test`. `staging` appears in no compose file, no env file and no `Makefile.ps1` target. It is reachable only by a deployment that supplies `ENV=staging` directly to a container or process — for example a bare-metal or non-Compose run, or an operator editing the `ENV:` literal in a fork of the compose file.

**Impact.** A tier that is declared, documented (`docs/09-database/enums.md:40,235`) and reachable, but which no deployment uses and no guard covers, is a trap for the first person who selects it: they get a deployment that looks production-shaped and is not, with `DEBUG=true` serving tracebacks and no credential floor. The blast radius is bounded — it requires deliberately choosing `staging` — and `docs/11-guides/docker.md:538` correctly notes that an env file cannot downgrade the Compose-pinned production tier, which is the more likely mistake. The gap is that `staging` is documented as a first-class tier in the enums reference, so it reads as supported, and it behaves as a development tier.

**Recommendation.** The absence of a pinned `staging` deployment is deliberate and correct — no drift there. The finding is the unguarded tier. `[BEST-PRACTICE]`, **priority: recommended**, **effort: small**: either give `staging` the same guard set as `production` minus nothing (treat `environment in (PRODUCTION, STAGING)` as the hardened set, which is a one-line change at each of the five gate sites and would make the tier safe to select), or remove `STAGING` from `EnvironmentEnum` and its two documentation rows so it cannot be selected. The first is better if a staging deployment is ever wanted; the second is better if it is not. Note that changing the gate set is a small edit with a wide blast radius — the five sites are independent today, so they should probably be unified into one predicate as part of the change.

---

### CFG-113 — The frontend and backend have no shared configuration contract, and the one variable the SPA requires cannot be supplied by any deployment surface

- **severity:** MEDIUM
- **areas:** Block 2 (name universes), Block 1 (variant selection and load-time vs per-use resolution)
- **kind:** defect
- **phase-task step:** "a name read in two source files with different values, so the two sources disagree and resolve alike"
- **duplicate-of:** none (shares its root cause with CFG-101; filed separately because the *contract gap* is the systemic defect and the *blank page* is one instance)

**Evidence**

The project has two entirely independent configuration systems with no shared declaration, no shared name registry and no validation that they agree.

Backend: `src/mkobi/config.py` — 70 name paths, pydantic-settings, `**__**` nesting, `ENV` for the tier, five sources, RFC-shaped startup refusal.

Frontend: `frontend/src/shared/config/env.ts` — one name, `import.meta.env.VITE_API_URL`, flat, build-time inlined, `import.meta.env.DEV` for the dev/production switch.

The two never meet. There is no generated type, no shared `.env` schema, no OpenAPI-derived client config, and no check in either build that the two agree about which origin the SPA should call. The only coupling is the reverse proxy (`docker/nginx/nginx.conf.template:57-59` proxies `/api/` to `app:8000`), which is a *deployment* convention that the frontend has no way to verify.

**Direct runtime reproduction.** Two independent naming decisions, both correct in isolation, silently disagreeing:

- Backend: `src/mkobi/config.py:96` declares the prefix, and `api/router.py` / `api/deps.py` build paths like `/api/v1/...` from it. The SPA must call exactly that prefix.
- Frontend: `frontend/src/shared/config/env.ts:10` hard-codes `DEFAULT_API_BASE_URL = '/api/v1'` as its fallback, and `frontend/vite.config.ts:9-14` proxies `/api` to `http://app:8000` in dev only. There is no mechanism by which the backend could change its prefix, or by which a mismatch would be caught.

The result is that CFG-101's missing `VITE_API_URL` has no correct-by-construction resolution: the value the SPA needs is the backend's prefix, the backend's prefix is a code constant, and the SPA's copy of it is a separate code constant in a different language.

**Impact.** The maintenance cost is the real finding. `docs/06-backend/configuration.md` is 363 lines documenting the backend contract in detail; there is no corresponding document for the frontend's, and the frontend's one required variable is not mentioned in `docs/07-frontend/` at all. A change to the API prefix requires finding a string literal in a TypeScript file by search, with no test to fail if it is missed — the failure surfaces as a runtime 404 from the SPA, after deployment. `frontend/src/shared/config/env.test.ts` tests `getApiBaseUrl()` and `validateEnv()` in isolation; it does not assert that the default `/api/v1` matches the backend's.

**Recommendation.** `[BEST-PRACTICE]`, **priority: recommended**, **effort: medium**. The single highest-value step is the CFG-101 fix, which should *not* hard-code `/api/v1` a third time: derive the SPA's default from the backend's declared prefix so the two cannot drift. Beyond that, the durable improvements in order of value/effort: (1) add a test that asserts the SPA's default base URL equals the backend's registered API prefix, so a backend change fails the frontend suite rather than production; (2) document the frontend's configuration surface in `docs/07-frontend/frontend-architecture.md` the way the backend's is documented, so the one required variable is discoverable; (3) if the deployment ever needs a cross-origin API, promote the value to a documented build argument with a build-time check (per CFG-101) rather than leaving it as a browser-time throw.

---

### CFG-114 — `CORS_ORIGINS_PLACEHOLDERS` is a hard-coded set of four origins while the codebase already declares a `StrEnum` for exactly this kind of fixed vocabulary

- **severity:** LOW
- **areas:** Block 3 (guarded preconditions)
- **kind:** risk
- **phase-task step:** "a constant the guard depends on whose value is not a constant the project can name in one place"
- **duplicate-of:** none

**Evidence**

`src/mkobi/config.py:831-837` declares the refusal set as a bare `set[str]` literal:

```python
831:    # --- Placeholder CORS origins that should never be used in production ---
832:    CORS_ORIGINS_PLACEHOLDERS: ClassVar[set[str]] = {
833:        "http://localhost:3000",
834:        "http://localhost:5173",
835:        "https://example.com",
836:        "https://your-domain.com",
837:    }
```

The project's stated rule (`.kilo/rules/project.md:10`) is *"All fixed values and settings must use `Enum` or `StrEnum` instead of dicts and lists. Keep them separately in models."* — and `src/mkobi/models/enums.py` is the designated home, already holding 18 such enums including `EnvironmentEnum` (`:111-117`) and `MimeTypeEnum` (`:120-127`), the latter being the precedent for exactly this shape (a fixed vocabulary the code refuses to let configuration widen — see `docs/06-backend/configuration.md:348-355`).

**Impact.** No runtime failure: the set is used correctly at `:850` and the guard works. The cost is that a fourth placeholder origin — and there are only ever going to be more, since every `docker/.env.*` template adds one — must be remembered in a second location. `https://your-domain.com` (`:836`) has no counterpart anywhere in the repository; it is a guess at a value an operator might type. There is no test that the set covers the placeholders the shipped templates actually contain, which is how CFG-109's message ended up naming origins the operator never wrote. Severity LOW: this is a maintainability observation about one declaration, not a defect, and the project's rule is about the general convention rather than this specific line.

**Recommendation.** The `MimeTypeEnum` precedent is the better choice, so the code is what should change. `[BEST-PRACTICE]`, **priority: recommended**, **effort: trivial**: move the vocabulary to `src/mkobi/models/enums.py` as a `frozenset`-valued `StrEnum` (or a `Final[frozenset[str]]` beside it, if an enum of URL strings reads poorly) and import it into `config.py:831-837`. Add the test this finding's absence of makes necessary: assert that every `CHANGE_ME`/placeholder origin appearing in `docker/.env.*` and `.env.example` is a member of the set, so a new template origin cannot be added without the guard knowing about it.
