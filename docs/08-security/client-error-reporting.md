---
id: client-error-reporting
domain: security
tags:
  - error-reporting
  - client-side
  - logging
  - monitoring
  - react-error-boundary
related:
  - security-overview
  - frontend-security
  - admin-api
---

# Client Error Reporting API

## Overview

The client error reporting API provides a single public endpoint for the React frontend to report runtime errors (e.g., uncaught exceptions, React Error Boundary catches) to the backend for server-side logging. This enables monitoring of frontend issues without requiring a separate logging infrastructure.

**Base path:** `/api/v1/client-errors`

**Auth level:** Public (no authentication required — errors are reported from the user's browser session, which may not have a valid token).

> **Security:** This endpoint intentionally does not require authentication because errors may occur before or independently of the authentication flow. The endpoint accepts error details and logs them server-side — it does not write to the database or return sensitive information.

---

## Endpoints

### 1. Report Client-Side Error

Accepts error details from the frontend for server-side logging.

| Attribute      | Value                                      |
| -------------- | ------------------------------------------ |
| **Method**     | `POST`                                     |
| **Path**       | `/api/v1/client-errors`                    |
| **Auth level** | Public                                     |
| **Rate limit** | 100 requests / 3600 s per `client-errors:{client_ip}` key (reflects the client address, not the caller identity; see phase 04 `AB-6`) |

**Request body:**

```json
{
  "error": {
    "name": "TypeError",
    "message": "Cannot read properties of null (reading 'map')",
    "stack": "TypeError: Cannot read properties of null (reading 'map')\n    at DashboardView (DashboardView.tsx:42:11)"
  },
  "componentStack": "in DashboardView\n  in App\n  in Router",
  "url": "/dashboard/550e8400-e29b-41d4-a716-446655440000",
  "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
  "timestamp": "2026-05-29T15:30:00.000Z"
}
```

**Request fields:**

| Field            | Type                  | Required | Bound (truncated, not rejected) | Description                                      |
| ---------------- | --------------------- | -------- | ------------------------------- | ------------------------------------------------ |
| `error`          | `object`              | Yes      | values capped at 32768 chars     | Error object with `name`, `message` and `stack` fields (the three the caller sends) |
| `componentStack` | `string \| null`      | No       | 32768 chars                      | React component stack trace (from Error Boundary) |
| `url`            | `string`              | Yes      | 32768 chars                      | Page URL where the error occurred                 |
| `userAgent`      | `string`              | Yes      | 32768 chars                      | Browser user agent string                         |
| `timestamp`      | `string` (ISO 8601)   | Yes      | 32768 chars                      | Client-side timestamp of the error                |

The whole body is also bounded: a request that **declares** a `Content-Length`
above 262 144 bytes is refused with **`413 CONTENT_TOO_LARGE`** before its
values are parsed (Product Owner ruling `DP-11`, option (c), 2026-10-03). A
chunked request declares no length and is instead held by the per-value caps
above, which truncate rather than reject so the single first-party caller keeps
reporting.

**Response** (`204 No Content`)

The endpoint returns an empty response with HTTP 204. No data is persisted to the database.

**Side effects:**
- The error is logged server-side via `logger.error()`. Each accepted string value is truncated to at most 32768 characters before the log call, and the untruncated length of every capped value is recorded in the same record (`truncated=<field>:<length>`), so a truncation is distinguishable from a genuinely short error. No accepted body can produce a log record beyond these caps.
- No database write occurs — the error exists only in server logs

---

## Frontend Integration

Of the three integrations this section names, **one is wired**: the **React Error
Boundary** (`frontend/src/shared/components/ErrorBoundary.tsx::reportError`). The
other two — **global `window.onerror`** and **unhandled promise rejections**
(`window.onunhandledrejection`) — are **not** wired in this repository.

The Error Boundary guards the reporter with `if (import.meta.env.DEV)`:
`import.meta.env.DEV` is **true in development builds**, so the boundary logs to
the console there and calls `reportError` only in the **`else` branch — i.e. in
production builds**. The reporter therefore fires in production builds, not in
development.

This provides visibility into production frontend issues that would otherwise go
unnoticed by backend monitoring.

---

## Cross-References

- [Security Overview](security-overview.md) — Security constraints and measures
- [Frontend Security](../07-frontend/frontend-security.md) — JWT handling, CORS, upload security
- [Admin API](../04-admin/admin-api.md) — Admin monitoring endpoints (server-side logs)
