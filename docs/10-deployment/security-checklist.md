---
id: security-checklist
domain: deployment
tags:
  - security
  - deployment
  - production
  - checklist
related:
  - deployment
  - security-overview
  - configuration
---

## Purpose

This document provides a production security checklist for deploying the mkobi BI Dashboard system. Use this checklist to verify all security-critical configurations before going to production.

## Main Concepts

- Rate limiting is a critical defense layer that must be configured correctly for production
- Fail-closed mode prevents attackers from exploiting Redis outages to bypass rate limits
- All secrets must be explicitly configured with no defaults in production

## Rate Limiting Security Configuration

### Fail-Closed Rate Limiting

The rate limiter is Redis-based and has configurable fail-open/fail-closed behavior:

| Setting | Development Default | Production Default | Recommendation |
| --- | --- | --- | --- |
| `RATE_LIMITER_FAIL_CLOSED` | `false` (fail-open) | `true` (fail-closed) | Always `true` in production |

#### Behavior

- **Fail-open** (`RATE_LIMITER_FAIL_CLOSED=false`): Requests are allowed through when Redis is unavailable. Use only for development and availability-first deployments.
- **Fail-closed** (`RATE_LIMITER_FAIL_CLOSED=true`): Requests are rejected with HTTP 429 when the rate limiter cannot connect to Redis. This is the secure default for production.

#### Log Messages

When Redis is unavailable:

| Mode | Log Level | Message |
| --- | --- | --- |
| Fail-open | WARNING | "Rate limiter fail-open: allowing request for key X (Redis unavailable)" |
| Fail-closed | CRITICAL | "Rate limiter FAIL-CLOSED: rejecting request for key X (Redis unavailable)" |

## Required Production Variables

### Required by Compose (`${VAR:?}`)

The base compose file uses `${VAR:?}` for the five names below, so Compose aborts
interpolation when any one of them is absent and **the stack does not start**. Read
the whole table before assuming the stack will come up: following a shorter list
means an aborted start. `${VAR:?}` enforces presence only, not strength.

| Variable | Description |
| --- | --- |
| `DATABASE__PASSWORD` | PostgreSQL **superuser** password. On `db` and `migrate` it is used directly; the `mkobi_app` role's password is supplied separately as `MKOBI_APP_PASSWORD` and mapped onto `DATABASE__PASSWORD` for `app` and `rq-worker` |
| `MKOBI_APP_PASSWORD` | Password of the least-privilege application database role (`mkobi_app`) |
| `JWT__SECRET_KEY` | JWT signing secret (256-bit random) |
| `ADMIN_USERNAME` | Initial admin username (must be a valid email) |
| `ADMIN_PASSWORD` | Initial admin password |

The development override adds `DATABASE__ADMIN_PASSWORD` to the same list.

### Required in Practice but Carrying a Default (`${VAR:-}`)

Both names below carry a `:-` default, so Compose never aborts interpolation on
them. A `:-` default keeps the stack *starting* only when the defaulted value is
itself acceptable, and these two differ: one default is safe, the other is refused
at startup.

| Variable | Compose default | Required In Production |
| --- | --- | --- |
| `RATE_LIMITER_FAIL_CLOSED` | `true` | Set to `true` explicitly to pin the choice |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | **Yes — the default is a placeholder and is refused** |

`CORS_ORIGINS` is effectively required. The compose default is one of the four
placeholder origins the production tier refuses, so a production start that relies on
the default aborts while `Settings` is being constructed:

```
Placeholder CORS origins not allowed in production: ['http://localhost:5173']. Please set CORS_ORIGINS to your actual production domains.
```

The refused set is `http://localhost:3000`, `http://localhost:5173`,
`https://example.com` and `https://your-domain.com`; the message lists whichever of
them are actually present. The base compose supplies `CORS_ORIGINS` to all three
Python services — `migrate`, `app` and `rq-worker` — so the refusal surfaces on any
of them, including the two that do not serve HTTP. A CORS-settings error on `migrate`
or `rq-worker` means the *setting* is wrong, not that the service needs origins.

> **`docker/.env.production` ships `CORS_ORIGINS` commented out.** It previously
> shipped `CORS_ORIGINS='["https://your-domain.com"]'`, which was itself a
> placeholder and was refused by the same guard. The template now carries guidance
> and an example instead, so an operator copying it must supply real domains, for
> example `CORS_ORIGINS='["https://app.example.org"]'`.

> **Admin password strength is a boot-time failure, not a warning.** `${ADMIN_PASSWORD:?}`
> checks presence only, so Compose starts and the application then refuses a password
> that is shorter than 8 characters, a known weak value, empty, or a `change_me`
> placeholder. A 6-character admin password that worked before this check existed now
> hard-fails at startup in the production tier. This is fail-closed and intended, but
> it will surprise the first operator who tries one. See
> [Configuration](../06-backend/configuration.md#admin-credentials) for the full
> predicate.

## Optional Security Hardening

| Variable | Default | Production Recommendation |
| --- | --- | --- |
| `LOGGING__LEVEL` | `INFO` | Set to `WARNING` to reduce log verbosity |

`ADMIN_USERNAME` and `ADMIN_PASSWORD` are listed as `${VAR:?}`-required above. Their
production requirement goes beyond presence: the username must be outside the weak
set, carry no `change_me` prefix and not be empty; the password must satisfy the same
rules and be at least 8 characters long.

## Docker Compose Production Check

Run this command to print the resolved `environment:` map of the `app` service:

```bash
docker compose -p mkobi --env-file docker/.env.production \
  -f docker/docker-compose.yml config --format json \
  | jq '.services.app.environment'
```

Verify that `ENV` is the literal `production` and that the rate-limiter, upload-size
and JSON-logging controls are present with their resolved values:

```json
{
  "ENV": "production",
  "RATE_LIMITER_FAIL_CLOSED": "true",
  "UPLOAD__MAX_FILE_SIZE_MB": "100",
  "LOGGING__JSON_LOGGING": "true"
}
```

Do **not** use `docker compose … config --services` for this check: it prints service
names only and cannot show a single environment value.

## Security Verification Steps

1. **Rate Limiter Test**: Verify Redis connectivity is required for requests to succeed when `RATE_LIMITER_FAIL_CLOSED=true`
2. **File Upload Limits**: Confirm `UPLOAD__MAX_FILE_SIZE_MB` is appropriate for your data
3. **CORS Validation**: Ensure `CORS_ORIGINS` contains only your production domain(s)
4. **JWT Secret**: Verify `JWT__SECRET_KEY` is at least 32 bytes of random data
5. **Admin Credentials**: Confirm `ADMIN_USERNAME` and `ADMIN_PASSWORD` are not default values

## Test Port Exposure in CI/CD

The test compose file (`docker/docker-compose.test.yml`) exposes database and application ports to the host for convenient local test execution. In CI/CD environments, avoid exposing these ports for security:

```bash
# Instead of relying on exposed ports, use:
docker compose -f docker/docker-compose.test.yml exec app uv run pytest tests/

# Or run tests inside the container network:
docker compose -f docker/docker-compose.test.yml exec test-app /app/.venv/bin/pytest tests/
```

**Rationale:** While port exposure is acceptable for local development (security risk is LOW — test databases contain no production data), CI/CD environments may have different network security boundaries. Running tests inside the container via `docker compose exec` keeps ports isolated within the Docker network.

## Cross-References

- [Deployment](deployment.md) — Production deployment procedures
- [Security Overview](../08-security/security-overview.md) — Rate limiting implementation details
- [Configuration](../06-backend/configuration.md) — Environment variables reference