# Phase 07 — External Boundary Audit Findings

**Phase:** 07-audit-external-boundary
**Problems only:** true (no praise, no "what works" summary — negative results live in *Not filed* below)
**Auditor:** fresh-context architecture auditor
**Date:** 2026-10-05
**Base commit / compose resolution:** working tree at 2026-10-05; production topology resolved with `docker compose --env-file <scratch> -f docker/docker-compose.yml --profile production config --format json`

---

## Multipart-spooling escalation — verdict

**CONFIRMED.** The phase-06 validator's inference was correct in substance and wrong in two details. Both are corrected below.

| Assertion | Verdict |
|---|---|
| Starlette spools the multipart body to `tempfile.gettempdir()` above 1 MiB | **CONFIRMED** — `SpooledTemporaryFile(max_size=spool_max_size)` with `spool_max_size = 1024 * 1024` (`starlette/formparsers.py:52`), rollover on `file.tell() > max_size` (`starlette/formparsers.py:135-142`) |
| `app` is `read_only: true` with no `/tmp` tmpfs | **CONFIRMED** — `docker/docker-compose.yml:193`, tmpfs absent from the service block; `rq-worker` has one at `:303-305`; resolved production `config` shows `app ro=True tmpfs=[(none)]` |
| Upload parse fails above 1 MiB in production | **CONFIRMED by execution** — differential below |
| Failure status is **500** | **REFUTED** — the observable status is **400** |
| Failure threshold is **≥ 1 MiB** | **REFUTED** — the boundary is **strictly above 1 048 576 bytes**; a body of exactly 1 MiB still succeeds |

### Differential evidence (executed, single variable: `read_only`)

Same image `mkobi/app:local`, same env, same network `mkobi_default`, current worktree `src` bind-mounted read-only. Only `--read-only` differs between the two containers. Request: `POST /api/v1/upload/<uuid>` with `-F "file=@<N KiB random body>"`, no credentials.

```
read_only=true    64 KiB -> HTTP 401     (body parsed; auth then refused)
read_only=true  1024 KiB -> HTTP 401     (body parsed; exactly 1 MiB, still memory-resident)
read_only=true  1025 KiB -> HTTP 400     "There was an error parsing the body"
read_only=true  2048 KiB -> HTTP 400
read_only=false   64 KiB -> HTTP 401
read_only=false 1024 KiB -> HTTP 401
read_only=false 1025 KiB -> HTTP 401     (control: parsed, auth refused)
read_only=false 2048 KiB -> HTTP 401
```

Root cause, read out of the same image under `--read-only`:

```
$ docker run --rm --read-only -v mkobi_app_data:/app/data -w /app mkobi/app:local python -c "import tempfile; print(tempfile.gettempdir())"
FileNotFoundError: [Errno 2] No usable temporary directory found in ['/tmp', '/var/tmp', '/usr/tmp', '/app']

$ docker run --rm --read-only ... python -c "import tempfile; f=tempfile.SpooledTemporaryFile(max_size=1024*1024); f.write(b'x'*(2*1024*1024))"
spool RAISED FileNotFoundError : [Errno 2] No usable temporary directory found in ['/tmp', '/var/tmp', '/usr/tmp', '/app']

$ docker run --rm -v mkobi_app_data:/app/data -w /app mkobi/app:local python -c "import tempfile; print(tempfile.gettempdir())"
WRITABLE gettempdir -> /tmp
```

Third control, which isolates the cause to the temp directory rather than to `read_only` in general: a **read-only** container with `TMPDIR=/app/data/tmp_uploads` (the already-mounted writable volume) parses the same bodies fine — `1025 KiB -> HTTP 401`, `2048 KiB -> HTTP 401`.

### Why 400 and not 500, and why the operator sees nothing useful

`fastapi/routing.py:406` runs `body = await request.form()` **before** `solve_dependencies` at `:457`, so the parse failure precedes authentication — which is exactly why the differential is observable without credentials. `fastapi/routing.py:445-449` wraps any parse exception in `HTTPException(400, "There was an error parsing the body")`; `src/mkobi/utils/exceptions.py:313` catches `StarletteHTTPException` and renders it as RFC 7807. The underlying `FileNotFoundError` is swallowed by that wrapper. The only operator-visible log line is:

```
"message": "Request body parse failed: There was an error parsing the body",
"logger": "mkobi.api.deps", "level": "WARNING"
```

— no traceback, no mention of a temp directory. Filed as **EXT-101**.

This is the same read-only-posture defect class as the already-validated `TOPO-101` (nginx entrypoint cannot write under `read_only: true`, which I also re-confirmed by execution), but in a different service with a different write, so it is filed separately as instructed.

---

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 2 |
| MEDIUM | 4 |
| LOW | 3 |
| **Total** | **9** |

Severity bands used: HIGH = a correctness or security defect that breaks a declared contract on a normal path, with a concrete impact (not "in the worst case if triggered"); MEDIUM = a real gap that leaves a declared protection or bound unserved but requires a specific condition; LOW = hardening, drift or declared-but-unimplemented.

---

## HIGH

### EXT-101 — `[SPEC-DEVIATION]` Production `app` rejects every multipart upload above 1 MiB: the read-only root filesystem has no writable temp directory

**Zone:** "Which inbound boundaries validate, which defer validation past acceptance, and which documented exceptions are load-bearing"
**Severity:** HIGH — a size-dependent total failure of the declared upload contract on the production tier. Not conditional: every CSV larger than 1 MiB fails, and 1 MiB is smaller than the project's own smallest realistic dashboard export. No credential is needed to reach the failure; the caller's only visible symptom is a body-parse error indistinguishable from a malformed request.

**Code — the missing tmpfs (`docker/docker-compose.yml:189-193`):**

```yaml
    volumes:
      - app_data:/app/data
    restart: unless-stopped
    # Security: read-only root filesystem with explicit writable paths via app_data volume
    read_only: true
```

The service block has no `tmpfs:` key. The sibling service that runs the same image has one — `docker/docker-compose.yml:303-305`:

```yaml
    read_only: true
    tmpfs:
      - /tmp:rw,size=128m
```

**Code — the boundary that fails (`src/mkobi/api/routes/upload.py:141-148`):**

```python
async def upload_file(
    dashboard_id: UUID,
    request: Request,
    file: UploadFile = File(...),
```

**Code — the limit that is actually in force (`starlette/formparsers.py:52` and `:135-142`):**

```python
    spool_max_size = 1024 * 1024
```

```python
    def _check(self, file):
        if self._rolled:
            return
        max_size = self._max_size
        if max_size and file.tell() > max_size:
            self.rollover()
```

**Code — the application ceiling that never runs (`docker/docker-compose.yml:186`):**

```yaml
      UPLOAD__MAX_FILE_SIZE_MB: ${UPLOAD__MAX_FILE_SIZE_MB:-100}
```

**Why this violates the declared contract:**

1. `AGENTS.md` §4 declares the upload boundary as "rate limiting + MIME-type + size limit on upload", and `docker/.env.production:42` sets `UPLOAD__MAX_FILE_SIZE_MB=100`. The declared ceiling is 100 MB.
2. `upload.py:215-229` enforces that ceiling while streaming. It is never reached, because Starlette rolls the same bytes onto disk at 1 MiB and the disk does not exist.
3. `docker/nginx/nginx.conf.template:32-40` states the design intent explicitly: "*a body the edge rejects first never reaches the application at all*" and "*the application decides whether an upload is accepted*". The intent is that the edge is the only outer ceiling and the application is authoritative. Here a third, undocumented ceiling — a Starlette library default — sits between the two and is the one that fires.
4. The project's own test suite already states the rule this service violates, in `tests/test_config.py:1816-1817`:

```python
        /tmp is required under read_only because Python's tempfile.gettempdir()
        finds no usable directory in a read-only rootfs. The app_data volume
```

but applies it only to the worker (`tests/test_config.py:1823-1826`):

```python
            block = self._service_block(text, "rq-worker")
            assert self._top_level_key(block, "read_only") == "true", name
            assert "tmpfs:" in block, name
            assert "/tmp:rw,size=128m" in block, name
```

`test_app_boundary_is_unchanged` (`tests/test_config.py:1804-1811`) asserts `read_only == "true"` for `app` and never asks for a tmpfs. No test in the repository posts a multipart body above 1 MiB, so the suite passes.

**Concrete impact.** In production, any upload whose file part exceeds 1 048 576 bytes returns `400 {"code":"VALIDATION_ERROR","detail":"There was an error parsing the body"}`. The user is told their file is invalid. Retrying, re-choosing the file, and re-uploading all fail identically; the only symptom in the logs is a WARNING naming a parse failure with no cause. Because `UPLOAD__MAX_FILE_SIZE_MB=100` is advertised, this presents as "large files are rejected by the app" rather than as "the container has no scratch space".

**Remediation.** One line on the `app` service:

```yaml
    tmpfs:
      - /tmp:rw,size=128m
```

mirroring `rq-worker`. Because the `app_data` volume already covers `/app/data`, this must not be placed over `tmp_uploads` — a tmpfs there would mask the volume (the same hazard `tests/test_config.py:1817-1819` calls out for the worker). Extending `test_rq_worker_is_read_only_with_tmpfs_in_both_tiers` to `app` would make the rule non-regressable.

---

### EXT-102 — `[SPEC-DEVIATION]` The shipped production edge publishes HTTP only, while the session credential is a `Secure`-only cookie

**Zone:** "The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them"
**Severity:** HIGH — the deployed topology cannot hold a session across a page reload, and every credential crosses the network in cleartext. This is the default production configuration produced by the command the deployment documentation gives.

**Code — the only published port (`docker/docker-compose.yml:365-366`):**

```yaml
    ports:
      - "80:80"
```

**Code — the only TLS in the tree (`docker/nginx/nginx.conf.template:80-86`, inside a fully commented block):**

```nginx
    # ----------------------------------------------------------------------
    # HTTPS server block (production)
    # ----------------------------------------------------------------------
    # Uncomment and configure with certificates for production HTTPS:
    #     listen 443 ssl;
```

A repository-wide search for `ssl_certificate`, `443`, `letsencrypt` and `certbot` across `docker/` returns only those three commented lines. There is no certificate, no 443 publish and no certificate provisioning anywhere.

**Code — the cookie flag (`src/mkobi/config.py:571-574`):**

```python
    cookie_secure: bool = Field(
        True,
        description="Secure flag for cookies. Set APP__COOKIE_SECURE=false for development.",
    )
```

**Code — the cookie it governs (`src/mkobi/core/security.py:463-471`):**

```python
    config = get_config()
    response.set_cookie(
        key=key,
        value=value,
        httponly=COOKIE_HTTPONLY,
        secure=config.app.cookie_secure,
        samesite=COOKIE_SAMESITE,
        max_age=max_age,
    )
```

**Code — the declared contract (`docs/10-deployment/deployment.md:144` and `:147`):**

```
Nginx proxies API requests to FastAPI and serves the React SPA static files. This adds a layer of control (SSL termination, caching, load balancing) at the cost of additional complexity.
```

```
Client → Nginx (port 80/443)
```

`docs/10-deployment/deployment.md:173` gives the deployment command; it starts the `production` profile and nothing else.

**Why this violates the declared contract.** The documentation promises an 80/443 edge with SSL termination; the compose file and the template ship 80 only. Two consequences follow from the mismatch, and they are independent of each other:

1. **Functional.** MDN is explicit: "*Insecure sites (`http:`) cannot set cookies with the `Secure` attribute (since Chrome 52 and Firefox 52)*", with the sole exception being `localhost` ("*The https: requirements are ignored when the Secure attribute is set by localhost*"). A deployment on any real hostname, started with the documented command, receives `Set-Cookie: …; Secure; HttpOnly; SameSite=strict` over `http://` and the browser discards it. The SPA holds the access token in a module-level variable only in production builds (`frontend/src/shared/auth/tokenStore.ts:74`, `:142-154`), so the refresh cookie is the *only* durable credential. Every full page reload ends the session.
2. **Security.** On the same port, passwords, bearer tokens and the refresh cookie traverse the network unencrypted. `app.py:101-102` compounds this by advertising a transport the deployment does not have:

```python
        if config.environment == EnvironmentEnum.PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
```

Browsers ignore HSTS received over HTTP, so the header is inert here; the template's own comment at `docker/nginx/nginx.conf.template:47` already says "*HSTS header should only be set on HTTPS connections*". The application contradicts the edge's own note.

**Concrete impact.** A production deployment that follows the documented command either cannot keep a user logged in across a reload, or is silently downgraded to plain HTTP with the credential-bearing cookie on the wire. There is nothing in the compose file, the env template or the documentation that states "you must terminate TLS in front of this" — `docker/.env.production` never mentions it either.

**Remediation.** Either declare the requirement and make it fail loudly (add `APP__COOKIE_SECURE` and a TLS-terminating service to the production profile, or a startup guard that refuses `cookie_secure=True` when no TLS listener exists), or implement the commented HTTPS block and publish 443. What must not remain is the current state, where the documentation, the code and the compose file disagree about which of the two the project intends.

---

## MEDIUM

### EXT-103 — `[BEST-PRACTICE]` The edge buffers anonymous bodies up to 512 MB into a RAM-backed tmpfs inside a 128 MiB-capped container

**Zone:** "The aggregate ingress budget: what bounds arrival, how its scope is shared, and whether one caller is recognised the same way on every surface"
**Severity:** MEDIUM — the bound exists but is implemented in a way that converts an arrival bound into a memory bound, one unauthenticated request from a full outage of the only edge container. Graded MEDIUM rather than HIGH because it is currently **unreachable**: the production edge cannot start at all under `read_only: true` (`TOPO-101`, which I re-confirmed by execution — see the escalation section). **This becomes HIGH the moment `TOPO-101` is fixed**, because it needs no credential and a single request suffices. It should be fixed in the same change that unblocks the edge.

**Code — the arrival bound (`docker/nginx/nginx.conf.template:41`):**

```nginx
        client_max_body_size ${NGINX_CLIENT_MAX_BODY_SIZE};
```

**Code — where the memory limit comes from (`docker/docker-compose.yml:397-400`):**

```yaml
    deploy:
      resources:
        limits:
          memory: 128M
```

**Code — the tmpfs that receives the body (`docker/docker-compose.yml:386-389`):**

```yaml
    tmpfs:
      - /tmp
      - /var/cache/nginx
      - /var/run
```

**Code — the proxied location, which sets no buffering or timeout of its own (`docker/nginx/nginx.conf.template:57-63`):**

```nginx
        location /api {
            proxy_pass http://app:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
```

**Chain of evidence.**

- `deploy.resources.limits.memory` is applied by Compose v2 in this repository, verified on two running containers of this project: `docker inspect mkobi-app-1 --format '{{.HostConfig.Memory}}'` → `1073741824`, matching the `1G` declared for `app`. So `nginx` really is capped at 134 217 728 bytes.
- The nginx image is `nginx:1.27-alpine`, whose compiled defaults include `--http-client-body-temp-path=/var/cache/nginx/client_temp` (read from `nginx -V` inside the image). That path is inside the tmpfs declared at `:388`.
- `proxy_request_buffering` is not set anywhere in the template, so it keeps its nginx default of `on`. nginx therefore reads the **entire** request body from the client into `client_body_temp_path` before it forwards a single byte upstream. No credential is involved: the buffering precedes the proxied request entirely.
- The tmpfs entries carry no `size=` option, so nothing bounds them relative to the container's memory limit.
- Nothing bounds the request at any lower rate either: the location sets no `client_body_timeout`, no `proxy_read_timeout` and no `proxy_send_timeout`, so the nginx defaults (60 s each) apply.

**Concrete impact.** One anonymous `POST` to `http://<host>/api/v1/anything` with a body of a few hundred megabytes is fully buffered into RAM inside a 128 MiB-capped container. The cgroup OOM-kills the only process serving every SPA request and every API call. There is no rate limit at the edge (the application's own limiter is reached only after the body has been spooled), no authentication requirement, and no configuration that makes this expensive for the attacker beyond bandwidth.

**Remediation.** Bound the buffering rather than the arrival: either set `proxy_request_buffering off` in `location /api` so the body streams to the application (which enforces its own ceiling while streaming at `src/mkobi/api/routes/upload.py:215`), or cap the tmpfs explicitly with `size=` on the `/var/cache/nginx` entry. Setting `client_max_body_size` close to `UPLOAD__MAX_FILE_SIZE_MB` rather than 512 MB reduces the exposure window without fixing the mechanism.

---

### EXT-104 — `[BEST-PRACTICE]` Edge-generated refusals disclose the nginx version and answer `/api/*` with an HTML page instead of the declared RFC 7807 body

**Zone:** "The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them"
**Severity:** MEDIUM — an unauthenticated caller receives a precise version fingerprint on the paths most likely to be probed, and receives a response body that violates the project's own error contract for API paths.

**Code — the header block, which never sets `server_tokens` (`docker/nginx/nginx.conf.template:28-46`):**

```nginx
    server {
        listen [::]:80;
        server_name localhost;

        # Upload byte ceiling for the edge.
```

`server_tokens` appears nowhere in the template; nginx's default is `on`, which emits the product and version.

**Observed response (executed against `nginx:1.27-alpine`, the image the compose `nginx` service builds from, `POST` of an oversized body):**

```
HTTP/1.1 413 Request Entity Too Large
Server: nginx/1.27.5
Content-Type: text/html
Content-Length: 183

<html>
<head><title>413 Request Entity Too Large</title></head>
<body>
<center><h1>413 Request Entity Too Large</h1></center>
<hr><center>nginx/1.27.5</center>
</body>
</html>
```

The `413` is the response for *any* body over `client_max_body_size`; `502` and `504` — the responses an attacker deliberately induces by making `app` unreachable — are generated by the same code path and carry the same banner.

**Why this violates the declared contract.** `AGENTS.md` §4 states that RFC 7807 is mandatory: "*All API errors return standardized responses with `type`, `title`, `status`, `detail`, `code`, and optional `details` fields*". On `413`, `502` and `504` under `location /api`, the declared body is replaced by an HTML page. The client-side chain degrades rather than breaks — `frontend/src/shared/api/errorHandler.ts:80-86` falls through to `error.message` — so the observable user experience is a toast reading `Internal server error: Request failed with status code 413` for what is a body-too-large refusal. A user who genuinely exceeds the upload ceiling is told the server has an internal error — the pattern this phase's block "A degraded result the consumer cannot tell from a real one" describes.

For the version banner, CIS NGINX Level 1 item 2.5.1 ("Ensure `server_tokens` directive is set to `off`") exists precisely to remove this reconnaissance surface.

**Concrete impact.** Any scanner or manual prober learns the exact edge version from the first oversized request, with no credential. Frontend error classification is wrong for every edge-generated refusal.

**Remediation.** Add `server_tokens off;` in the `http` block. If the RFC 7807 contract is meant to hold on edge refusals too, that is a larger decision and belongs in the error contract, not here — but at minimum the mismatch should be documented rather than left implicit.

---

### EXT-105 — `[BEST-PRACTICE]` The production CSP forbids exactly the cross-origin API surface the production CORS guard obliges the operator to declare

**Zone:** "The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them"
**Severity:** MEDIUM — two declared contracts in the same production deployment are mutually unsatisfiable. This is filed as *additional* to `CFG-101` and does not overlap it: `CFG-101` is that `VITE_API_URL` is supplied by no build surface; this is that once it *is* supplied with a cross-origin value, the edge's own CSP refuses the resulting requests.

**Code — the CSP the edge serves (`docker/nginx/nginx.conf.template:53`):**

```nginx
        add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'" always;
```

`connect-src 'self'` restricts `fetch`/`XHR` destinations to the document's own origin.

**Code — the production build refuses to start without an explicit base URL (`frontend/src/shared/config/env.ts:38-45`):**

```typescript
export function validateEnv(): void {
  if (import.meta.env.DEV) {
    return
  }

  if (!import.meta.env.VITE_API_URL) {
    throw new Error(`Missing required environment variable: ${API_URL_ENV_VAR}`)
  }
}
```

**Code — the value is used verbatim (`frontend/src/shared/config/env.ts:20-28`):**

```typescript
export function getApiBaseUrl(): string {
  // Vite types `import.meta.env` values as `any`; read it as `unknown` first so
  // narrowing happens here rather than leaking an `any` into the return type.
  const configured: unknown = import.meta.env.VITE_API_URL
  if (typeof configured === 'string' && configured.length > 0) {
    return configured
  }
  return DEFAULT_API_BASE_URL
}
```

**Code — and production is obliged to declare a non-localhost origin (`src/mkobi/config.py:832-837` and `:847-857`):**

```python
    CORS_ORIGINS_PLACEHOLDERS: ClassVar[set[str]] = {
        "http://localhost:3000",
        "http://localhost:5173",
        "https://example.com",
        "https://your-domain.com",
    }
```

```python
        if self.environment == EnvironmentEnum.PRODUCTION:
            invalid_origins = [
                origin for origin in self.cors_origins
                if origin in self.CORS_ORIGINS_PLACEHOLDERS
            ]
            if invalid_origins:
                raise ValueError(
                    f"Placeholder CORS origins not allowed in production: {invalid_origins}. "
```

plus `src/mkobi/app.py:306-309`, which refuses to start on an empty list.

**Why this violates the declared contract.** The CORS guard exists to make a production deployment declare real origins, and `app.py:345-346` applies `allow_origins=config.cors_origins` with `allow_credentials=True`. That machinery only has meaning for a cross-origin API. But the CSP the same deployment serves restricts `connect-src` to `'self'`, so a browser running the SPA will refuse every cross-origin API request before CORS is ever consulted. The operator is required to configure something that the edge then forbids.

**Concrete impact.** A deployment that follows both contracts — non-placeholder `CORS_ORIGINS` for a separate API host, `VITE_API_URL` pointing at it — serves a SPA that cannot make a single API call. The failure appears as a CSP violation in the browser console and a generic toast in the UI, not as a configuration error.

**Remediation.** Pick one deployment shape and make the code say so. If the SPA and API are always same-origin behind this edge, then `CORS_ORIGINS` should be documented as forward-proxy configuration rather than as the SPA's own origin list, and `validateEnv` should accept the same-origin value it already defaults to. If split origins are supported, `connect-src` must name them — which means the value has to reach the template, not just the bundle.

---

### EXT-106 — `[BEST-PRACTICE]` The dev and test tiers publish authenticated services on `0.0.0.0` while the same files bind the database to `127.0.0.1`

**Zone:** "The aggregate ingress budget: what bounds arrival, how its scope is shared, and whether one caller is recognised the same way on every surface"
**Severity:** MEDIUM — reachable from the local network with credentials that are weak by construction, and it contradicts a rule the same file states in capital letters for the database one service away.

**Code — the authenticated API, published on every interface (`docker/docker-compose.override.yml:186-191`):**

```yaml
    ports:
      # Host port configurable for parallel checkouts (default 8010; 8000 is
      # commonly taken by other projects). Container-internal port stays 8000,
      # and the Vite dev server reaches the app over the internal network.
      - "${APP_HOST_PORT:-8010}:8000"
```

The port spec carries no host address, so Docker binds `0.0.0.0`. Confirmed at runtime on this host: `docker inspect mkobi-app-1 --format '{{json .HostConfig.PortBindings}}'` → `{"8000/tcp":[{"HostIp":"","HostPort":"8010"}]}` — empty `HostIp` is the wildcard.

**Code — the database, one service away, with the opposite rule (`docker/docker-compose.override.yml:271-275`):**

```yaml
  db:
    ports:
      # Bound to 127.0.0.1 to limit exposure to local machine only.
      # Do not change to 0.0.0.0 — that would expose the database to the network.
      - "127.0.0.1:5432:5432"
```

**Code — and the same for the test tier (`docker/docker-compose.test.yml:44-47` and `:71-73`):**

```yaml
    ports:
      # Host port configurable to allow parallel checkouts on one machine.
      # Default 5434 (5433 is commonly taken by other projects' test databases).
      - "${TEST_DB_HOST_PORT:-5434}:5432"
```

```yaml
    ports:
      # Host port configurable for parallel checkouts (default 6381).
      - "${TEST_REDIS_HOST_PORT:-6381}:6379"
```

`docker/docker-compose.test.yml:15` records the reasoning:

```
#   - Bind address: 0.0.0.0 (Docker default, localhost-only on most systems)
```

That parenthetical is not true of `0.0.0.0`; a wildcard publish is reachable from every interface the host has, on every platform. The consequence is documented one line earlier (`:14`) — "*Uses default passwords: test_password (postgres), test_app_password (mkobi_app)*" — so the two facts combine into a LAN-reachable Postgres and Redis with credentials committed in the file. `docker/docker-compose.test.yml:13` rates this "*LOW severity*" on the grounds that "*Test database contains NO production data*", which does not address the LAN-reachability question it is adjacent to.

**Why this matters at this boundary.** The production tier is clean on this point — see *Not filed*. The exposure is entirely in the two tiers a developer runs on a laptop plugged into a hotel or conference network, and in the tier the documented host-side pytest workflow depends on. The dev override's own comment sets the standard that the same file does not meet for the service that actually speaks HTTP.

**Concrete impact.** Any host on the same network can reach `POST http://<dev-host>:8010/api/v1/auth/login` and the test Postgres/Redis on `5434`/`6381`. The dev stack runs with operator-supplied development credentials (`:278` sources `POSTGRES_PASSWORD` from `.env`), and the running instance on this host uses `postgres`.

**Remediation.** Add explicit `127.0.0.1:` prefixes to the `app` publish and to both test-tier publishes, keeping the configurability. If a LAN-reachable path is genuinely wanted, the documentation should say so instead of asserting that the wildcard bind is "localhost-only on most systems".

---

## LOW

### EXT-107 — `[BEST-PRACTICE]` `NGINX_CLIENT_MAX_BODY_SIZE` is interpolated into the generated main config with no escaping or validation

**Zone:** "The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them"
**Severity:** LOW — the missing validation is real and demonstrable, but the value is operator-controlled, so no privilege boundary is crossed. An operator who can set `NGINX_CLIENT_MAX_BODY_SIZE` in `.env` can already set any other environment variable for the whole deployment. This is hardening, not an exposure.

**Code — the render (`docker/nginx/entrypoint-render.sh:12-16`):**

```bash
TEMPLATE="/etc/nginx/nginx.conf.template"
RENDERED="/etc/nginx/nginx.conf"

if [ ! -f "$TEMPLATE" ]; then
    echo "ERROR: nginx template not found at $TEMPLATE" >&2
    exit 1
fi

envsubst '${NGINX_CLIENT_MAX_BODY_SIZE}' < "$TEMPLATE" > "$RENDERED"
```

**Code — the unvalidated source (`docker/docker-compose.yml:373-374`):**

```yaml
    environment:
      NGINX_CLIENT_MAX_BODY_SIZE: ${NGINX_CLIENT_MAX_BODY_SIZE:-512m}
```

**Observed behaviour (executed).** With `NGINX_CLIENT_MAX_BODY_SIZE='512m; access_log /var/log/nginx/INJECTED.log combined;'`, `envsubst` produces:

```
        client_max_body_size 512m; access_log /var/log/nginx/INJECTED.log combined;;
```

A `;` in the value terminates the `client_max_body_size` directive and injects arbitrary further directives into the **main** configuration context, which includes the `server` block. There is no allow-list, no numeric-format check and no escaping.

**What I checked and did not find.** The template's own claim at `docker/nginx/nginx.conf.template:17-20` — that `envsubst` must not eat nginx's own variables — is **correct**. Verified by execution: with the explicit `SHELL-FORMAT` argument, only `NGINX_CLIENT_MAX_BODY_SIZE` is substituted and `$remote_addr`, `$uri`, `$time_local`, `$status` and the rest reach nginx verbatim. The escaping question is confined to the one interpolated value.

**Concrete impact.** Limited to operator error rather than attacker input. The realistic failure is not injection but a typo producing an nginx that will not start, which is a loud failure and therefore harmless.

**Remediation.** Validate the value in the render script before substitution — `case "$NGINX_CLIENT_MAX_BODY_SIZE" in (*[0-9]*) ;; (*) echo "..." >&2; exit 1;; esac` — or pin it to a constant in the template. Effort is trivial; the benefit is that a mistyped value fails with a clear message instead of a generated config nginx rejects.

---

### EXT-108 — `[BEST-PRACTICE]` The edge listens only on `[::]:80`, which is not reachable through an IPv4 published port on this host

**Zone:** "The inbound surface: which paths answer an anonymous caller, what each discloses, and what the published description promises about them"
**Severity:** LOW — reproduced twice on this host, but the behaviour is host-kernel and Docker-runtime dependent rather than a property of the configuration, and it is currently masked by `TOPO-101` (the edge cannot start at all under `read_only: true`). It is filed because the deployment documentation's own snippet uses `listen 80;` and the shipped template does not, and that divergence is worth resolving deliberately rather than by accident.

**Code (`docker/nginx/nginx.conf.template:28-30`):**

```nginx
    server {
        listen [::]:80;
        server_name localhost;
```

**Code — the documentation's snippet (`docs/10-deployment/deployment.md:154-156`):**

```nginx
server {
    listen 80;
    server_name your-domain.com;
```

**Observed behaviour (executed).** Containers from the same image. The three repo-template rows were run with a **writable** root filesystem, deliberately bypassing `TOPO-101` so that the render could complete and the listener question could be isolated; every other hardening flag of the production `nginx` service (tmpfs set, `NGINX_CLIENT_MAX_BODY_SIZE`, the mounted template and entrypoint, the `command`) was left exactly as declared.

| container | listener | IPv4 publish | result |
|---|---|---|---|
| repo template, rendered by `entrypoint-render.sh` | `[::]:80` only | `-p 18099:80` | `HTTP 000` — TCP accepted, then "Empty reply from server"; no access-log line |
| repo template, published on `[::]` | `[::]:80` only | `-p [::]:18097:80` | `HTTP 000` |
| minimal control config | `listen [::]:80` only | `-p 18095:80` | `HTTP 000` |
| stock `nginx:1.27-alpine` config | `listen 80` (+`[::]:80`) | `-p 18098:80` | `HTTP 200`, access-log line present |
| repo template, same content, same flags, rendered to a tmpfs path | — | probed from a sibling container at the container's own IPv4 | `HTTP 000` |

The container reports `bindv6only = 0` and `netstat -lnt` shows a single `:::80` LISTEN socket, so the wildcard socket is not refusing IPv4 at the kernel level; the reachability loss is in this Docker Desktop / WSL2 port-publishing path.

**What this is not.** It is not a claim that `listen [::]:80` is wrong in general. With `bindv6only = 0` on a plain Linux Docker Engine, an IPv6 wildcard listener accepts IPv4-mapped connections and the published port serves normally. I could not test a Linux-engine host from this environment.

**Remediation.** Add the conventional second directive so the edge listens on both families regardless of host defaults — `listen 80;` alongside `listen [::]:80;` — which also removes the divergence from the documented snippet. Effort is trivial and the change is harmless on a Linux engine.

---

### EXT-109 — `[DOC-UPDATE]` The declared per-user upload tree exists only as an uncalled helper and would fail if it were called

**Zone:** "Whether this boundary exists at all, and every mechanism that would carry one"
**Severity:** LOW — no runtime impact today, because nothing calls it. It is filed because the documented pipeline declares a second upload location that the code does not implement, and that location is uncreatable in the shipped image.

**Code — the helper (`src/mkobi/utils/file_utils.py:27-31`):**

```python
    cache_dir = Path(platformdirs.user_cache_dir("mkobi", appauthor=False))
    temp_dir = cache_dir / "uploads" / str(user_id)
    temp_dir.mkdir(parents=True, exist_ok=True)
    logger.info("User temp directory: user_id=%s, path=%s", user_id, temp_dir)
    return temp_dir
```

`get_user_temp_dir` has no caller anywhere in `src/` outside the re-export in `src/mkobi/utils/__init__.py:9`. The only staging write that actually happens is `src/mkobi/api/routes/upload.py:203-205`:

```python
        upload_dir = Path(get_config().upload_temp_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
```

**The declared contract (`AGENTS.md` §5, step 2)** names both locations: a staging folder at `user_data_dir("mkobi", "ZOO") / "tmp_uploads"` *and* "a per-user upload tree — `user_cache_dir` … `/uploads` / <user_id>".

**Why it matters that the second one cannot work.** Resolved inside the production image:

```
$ docker run --rm mkobi/app:local python -c "import os,platformdirs; print(os.environ.get('HOME'), platformdirs.user_cache_dir('mkobi', appauthor=False))"
/nonexistent /nonexistent/.cache/mkobi
```

The runtime user is created by `docker/Dockerfile:129`:

```dockerfile
RUN addgroup --system app && adduser --system --group app
```

`adduser --system` leaves the home at Debian's `/nonexistent` default and does not create it, so `mkdir(parents=True)` would raise on the first call. The staging path is safe only because the compose file pins `UPLOAD__TEMP_DIR=/app/data/tmp_uploads` onto the `app_data` volume; nothing pins the per-user path, because nothing uses it.

**Concrete impact.** None currently. The risk is drift: a reader of `AGENTS.md` will believe there is a per-user upload tree, and anyone who wires `get_user_temp_dir` into the upload pipeline gets an immediate `OSError` that reproduces only in the production image, not on a developer machine where `$HOME` is writable.

**Remediation.** Per the dead-code policy this is documented, so it is future-proofing rather than dead code and the recommendation is to establish its purpose, not to delete it. Either point the compose file at a writable volume for the per-user tree (mirroring the `UPLOAD__TEMP_DIR` treatment) so the declared contract is implementable, or update `AGENTS.md` §5 to describe the single staging location the code actually uses.

---

## Not filed — areas checked with no findings

Each entry names the check performed and the evidence that closed it, so a later reader can tell a negative result from an unchecked surface.

**Outbound boundary — does not exist.** Established from both ends. A search of `src/mkobi` for `httpx|aiohttp|requests.|urlopen|urllib|socket.|boto3|verify=|aiofiles|subprocess` returns 6 hits, none of them a network call: `urllib.parse` imported in `src/mkobi/config.py:8` and `src/mkobi/db/starter.py:22` (URL *parsing*, no network), the string `"aiofiles"` in the dependency-presence list at `src/mkobi/startup.py:23`, and `import aiofiles` / `aiofiles.open(...)` at `src/mkobi/api/routes/upload.py:14` and `:210` (asynchronous *filesystem* I/O). No HTTP client library is imported anywhere in `src/`. Every network destination in the system is Redis or PostgreSQL, addressed by container service name. Consequently there are no outbound timeouts, retries or TLS-verification settings to audit, and no third-party slow-or-down path to grade.

**SSRF — no surface.** No user-controlled URL is ever fetched. `config.py:943-945` parses `cors_origins` values with `urlparse` and compares the result against literals; it never resolves or requests them.

**Production port exposure.** Resolved with `docker compose --env-file <scratch> -f docker/docker-compose.yml --profile production config --format json`:

```
app        ro=True   tmpfs=[(none)]            ports=[(none)]
db         ro=(unset) tmpfs=[(none)]          ports=[(none)]
migrate    ro=(unset) tmpfs=[(none)]          ports=[(none)]
redis      ro=(unset) tmpfs=[(none)]          ports=[(none)]
rq-worker  ro=True   tmpfs=[/tmp:rw,size=128m] ports=[(none)]
nginx      ro=True   tmpfs=[/tmp, /var/cache/nginx, /var/run] ports=[:80->80]
```

Postgres and Redis publish no host port in the production tier, so they are reachable only from the project bridge. Only `nginx` is externally published, and it is the only service in the `production` profile. The edge depends on `app` being healthy first (`docker/docker-compose.yml:362-364`).

**Cross-tier port leakage.** `docker/docker-compose.test.yml:26` declares `name: mkobi-test`, and `Makefile.ps1:31-36` binds the two stacks to two explicit project names with two disjoint file sets:

```powershell
$DevProject  = 'mkobi'
$TestProject = 'mkobi-test'
$DevCompose  = @('-p', $DevProject,  '--env-file', '.env',
                 '-f', 'docker/docker-compose.yml',
                 '-f', 'docker/docker-compose.override.yml')
$TestCompose = @('-p', $TestProject, '-f', 'docker/docker-compose.test.yml')
```

Every compose invocation in `Makefile.ps1` uses one of those two arrays; none combines the test file with the base compose, and none passes `--profile production` to the test project. No test-tier port is published into the production profile.

**API prefix contract.** The `/api/v1` prefix is consistent end to end, and nothing additional survives once `CFG-101` is fixed. `frontend/src/shared/config/env.ts:10` sets `const DEFAULT_API_BASE_URL = '/api/v1'`; every feature module builds paths relative to it — `frontend/src/features/upload/api/uploadApi.ts:17` is `` `/upload/${dashboardId}` `` — so the composed request is `/api/v1/upload/...`. `frontend/vite.config.ts:10-13` proxies `/api` with `changeOrigin: true` and no `rewrite`, so the path is preserved. `docker/nginx/nginx.conf.template:57` is `location /api` (a prefix match, so `/api/v1/*` matches) with `proxy_pass http://app:8000;` and no trailing URI component, so the path is forwarded unchanged — as its own comment at `:55-56` states. `src/mkobi/app.py:361-371` mounts every router at `prefix="/api/v1"`. No doubled prefix, no dropped segment, no rewrite. Separately checked and cleared: `frontend/src/features/upload/api/uploadApi.ts:21` sets `'Content-Type': 'multipart/form-data'` with no boundary, which would normally break multipart parsing; axios 1.16.0 replaces it with `undefined` for a `FormData` body in a browser environment (`node_modules/axios/dist/esm/axios.js`, `headers.setContentType(undefined); // browser handles it`), so the browser supplies the boundary.

**CORS wildcard with credentials — not reachable in production.** `src/mkobi/app.py:343-348` passes `allow_origins=config.cors_origins` with `allow_credentials=True`. In production a wildcard is refused outright, before the filter that would otherwise drop it: `src/mkobi/config.py:935-940` raises when any entry equals `"*"`, and `src/mkobi/config.py:941-950` then discards entries that do not parse as an `http`/`https` URL — `"*"` does not. So `allow_origins` in production is always an explicit list. In non-production tiers the same filter removes `"*"` before it can reach the middleware. `allow_credentials=True` therefore never coexists with a wildcard origin in any tier.

**Rate-limiter failure direction — a declared value, not a hard-coded branch.** `src/mkobi/config.py:740` declares it as a settings field:

```python
    rate_limiter_fail_closed: bool = Field(default=True, alias="RATE_LIMITER_FAIL_CLOSED")
```

The default is fail-closed, the production tier pins it for both services that enforce a limit (`docker/docker-compose.yml:185` for `app`, `:286` for `rq-worker`), the dev tier pins it for both (`docker/docker-compose.override.yml:157` and `:234`), and the test tier inherits the default — `docker/docker-compose.test.yml:148-159` does not set it. Every call site reads it through the config accessor rather than branching on a constant: `src/mkobi/api/routes/auth.py:203`, `:435`, `:760`, `src/mkobi/api/routes/upload.py:180`, `src/mkobi/api/routes/client_errors.py:105`. Which direction an outage resolves to is therefore configuration, not code. (The ingress *budget* itself — the counter being process-local, `docker/Dockerfile:242` running `--workers 4`, and the trusted-proxy collapse — is already owned by phase 04 and is not re-filed here.)

**Proxy-header trust chain — correctly bounded.** `src/mkobi` sets `PROXY_HEADERS` nowhere, and `docker/Dockerfile:242` passes no `--forwarded-allow-ips`:

```dockerfile
CMD ["uvicorn", "src.mkobi.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

so uvicorn reads the environment: `uvicorn/config.py:343-344` does `os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")` when the CLI argument is absent. The compose file supplies it at `docker/docker-compose.yml:182` as `${FORWARDED_ALLOW_IPS:-172.21.0.0/16}`, scoped to the compose subnet, and the dev override pins it to `127.0.0.1` (confirmed on the running container: `FORWARDED_ALLOW_IPS=127.0.0.1`). The default is already the safe one. The `$remote_user` placeholder in the log format at `docker/nginx/nginx.conf.template:21` renders as `-` and discloses nothing.

**Stack-trace and debug disclosure at the boundary — none found.** No exception handler returns a traceback. The catch-all at `src/mkobi/utils/exceptions.py:344-348` logs the exception server-side with `exc_info=True` and returns a fixed document:

```python
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception,
    ) -> JSONResponse:
        logger.error("Unhandled exception: %s", exc, exc_info=True)
```

The response body is built from constants at `src/mkobi/utils/exceptions.py:349-355` (`detail="Internal server error"`, `details=None`), so no driver text or filesystem path reaches the caller. The validation handler is equally careful about echoing submitted values (`src/mkobi/utils/exceptions.py:272-278` documents dropping `input` so a plaintext password cannot be reflected). `src/mkobi/config.py:827-828` refuses `debug=True` in production, and `src/mkobi/app.py:333` passes it to `FastAPI(debug=...)`. `/health` returns a two-key body (`src/mkobi/app.py:384-386`). The anonymous-refusal surface is limited to what EXT-104 records.

**`envsubst` variable handling — no finding.** Verified by execution against `docker/nginx/nginx.conf.template`: with the explicit `SHELL-FORMAT` argument at `docker/nginx/entrypoint-render.sh:14`, only `NGINX_CLIENT_MAX_BODY_SIZE` is substituted and nginx's own `$remote_addr`, `$uri`, `$time_local`, `$status`, `$body_bytes_sent`, `$http_referer` and `$http_user_agent` reach the runtime verbatim. The template's comment at `:17-20` is accurate. (The escaping gap for the one substituted value is EXT-107.)

**`/health/detailed` gating — the template's comment is accurate.** `docker/nginx/nginx.conf.template:65-66` claims the path is "admin-gated at the application layer (unsatisfied callers get 401/403 through this proxy)". Confirmed: `src/mkobi/app.py:394-398` declares `_admin: Any = Depends(require_admin_role)`, and `src/mkobi/api/deps.py:679-703` raises `AppException` when the role check fails. Verified against a container running current worktree source — an anonymous `GET /health/detailed` returns `401 {"code":"AUTHENTICATION_FAILED"}`.

---

## Appendix — limits on this audit

**The running dev stack was stale, and I did not restart it.** `docker logs mkobi-app-1` shows its last reload at `2026-10-03T23:02`, while `src/mkobi/app.py` was last modified `2026-10-05T06:00`. Its behaviour does not match the worktree — an anonymous `GET /health/detailed` against `localhost:8010` returns `200` and a body containing `"path":"/app/frontend/dist"`, neither of which is possible with the current source (`src/mkobi/app.py:397` gates the endpoint; `:436-439` sets no `path` key). I treated this as an environment fact, not a defect: no finding is filed from the stale container. All runtime evidence in this report comes from throwaway containers I started with the current worktree `src` bind-mounted, or from library-level probes inside the shipped image. I did not restart or otherwise mutate the shared dev stack, since concurrent audit phases depend on it.

**One inference could not be reproduced.** EXT-103 is a static chain: the memory limit, the tmpfs target, nginx's compiled `client_body_temp_path` and the default `proxy_request_buffering on` are each established individually, but I did not observe the OOM-kill itself. Attempting it through the repo's edge configuration is impossible while `TOPO-101` stands; a bypass run against a writable nginx did not reach the buffering path before I stopped the experiment. The finding is graded MEDIUM on that basis, with the re-grade condition stated in the finding.

**The IPv6-only listener result is host-specific.** EXT-108 was reproduced twice on this Docker Desktop / WSL2 host, but I could not test a Linux-engine host, where an IPv6 wildcard listener with `bindv6only = 0` accepts IPv4-mapped connections and the published port would serve normally. The finding is stated as a divergence from the project's own documented snippet, not as a universal failure.

**`VITE_API_URL` remains unsupplied by every build surface.** `CFG-101` is validated and excluded from this report; EXT-105 is filed only for the CSP-vs-CORS contradiction that remains after that is fixed.

**Redis holds unauthenticated credential material — recorded as a hand-over, not filed.** `docker/docker-compose.yml` declares no `requirepass` on the `redis` service and no `REDIS__PASSWORD` on `app` or `rq-worker`, so the store holds token-revocation markers and temporary login passwords without authentication on the project bridge. Per the phase boundary, "*what credential material the store holds*" belongs to phase 15, and `.ai/plans/_code-context/15-security-baseline-code-context.md:125` already records it. Not filed here to avoid a duplicate.

**Out of scope, observed in passing.** The canonical-slash 307 redirect that makes a declared collection path an existence oracle is already validated as `EXT-006` and is not re-filed here; the control it turns on is `src/mkobi/app.py:337`, `redirect_slashes=False`, which this phase did not audit.
