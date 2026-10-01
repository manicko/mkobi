---
id: error-format
domain: security
tags:
  - error-handling
  - rfc-7807
  - api-errors
  - exception-handling
related:
  - security-overview
  - access-control
  - auth-api
  - frontend-security
  - error-handling-guide
---

# Error Format

## Overview

All API error responses follow the RFC 7807 Problem Details format with extensions. This provides a consistent, machine-readable structure that enables programmatic error handling on the frontend while delivering human-readable messages for debugging.

## RFC 7807 Compliance

The system implements [RFC 7807 Problem Details for HTTP APIs](https://datatracker.ietf.org/doc/html/rfc7807) with the following standard fields plus extensions:

### Standard Fields

| Field | Type | Description |
| --- | --- | --- |
| `type` | string | URI-style error type for documentation reference |
| `title` | string | Short human-readable summary |
| `status` | integer | HTTP status code |
| `detail` | string | Developer-facing message (English) |

### Extended Fields

| Field | Type | Description |
| --- | --- | --- |
| `code` | ErrorCode | Machine-readable error code enum value |
| `details` | object | Optional structured context (field names, column names, etc.) |
| `errors` | array | Field-level validation errors (validation responses only) |

## Error Response Examples

### 401 Unauthorized (Authentication Failed)

```json
{
  "type": "https://api.mkobi.com/errors/authentication_failed",
  "title": "Authentication failed",
  "status": 401,
  "detail": "Token has expired",
  "code": "TOKEN_EXPIRED"
}
```

### 403 Forbidden (Permission Denied)

```json
{
  "type": "https://api.mkobi.com/errors/permission_denied",
  "title": "Permission denied",
  "status": 403,
  "detail": "Access denied to dashboard",
  "code": "ACCESS_DENIED"
}
```

### 404 Not Found (Dashboard Not Found)

```json
{
  "type": "https://api.mkobi.com/errors/dashboard_not_found",
  "title": "Dashboard not found",
  "status": 404,
  "detail": "Dashboard with ID '123e4567-e89b-12d3-a456-426614174000' not found",
  "code": "DASHBOARD_NOT_FOUND"
}
```

### 422 Unprocessable Entity (Validation Error)

```json
{
  "type": "https://api.mkobi.com/errors/validation_error",
  "title": "Validation error",
  "status": 422,
  "detail": "Request validation failed",
  "code": "VALIDATION_ERROR",
  "errors": [
    { "loc": ["body", "email"], "msg": "Invalid email format", "type": "value_error" },
    { "loc": ["body", "password"], "msg": "Password must be at least 8 characters", "type": "value_error" }
  ]
}
```

### 500 Internal Server Error

```json
{
  "type": "https://api.mkobi.com/errors/internal_error",
  "title": "Internal server error",
  "status": 500,
  "detail": "An unexpected error occurred",
  "code": "INTERNAL_ERROR"
}
```

## ErrorCode Reference Table

| ErrorCode | HTTP Status | Description | Category |
| --- | --- | --- | --- |
| `INTERNAL_ERROR` | 500 | Internal server error | General |
| `SERVICE_UNAVAILABLE` | 503 | Service unavailable | General |
| `RATE_LIMIT_EXCEEDED` | 429 | Rate limit exceeded | General |
| `AUTHENTICATION_FAILED` | 401 | Authentication failed | Authentication |
| `TOKEN_EXPIRED` | 401 | Token expired | Authentication |
| `TOKEN_REVOKED` | 401 | Token revoked | Authentication |
| `INVALID_TOKEN` | 401 | Invalid token | Authentication |
| `PERMISSION_DENIED` | 403 | Permission denied | Authorization |
| `INSUFFICIENT_PERMISSIONS` | 403 | Insufficient permissions | Authorization |
| `ACCESS_DENIED` | 403 | Access denied | Authorization |
| `NOT_FOUND` | 404 | Resource not found | Resource |
| `DASHBOARD_NOT_FOUND` | 404 | Dashboard not found | Resource |
| `USER_NOT_FOUND` | 404 | User not found | Resource |
| `GRAPH_NOT_FOUND` | 404 | Graph not found | Resource |
| `FILTER_NOT_FOUND` | 404 | Filter not found | Resource |
| `LAYOUT_NOT_FOUND` | 404 | Layout not found | Resource |
| `PROCESSING_CONFIG_NOT_FOUND` | 404 | Processing config not found | Resource |
| `VALIDATION_ERROR` | 422 | Validation error | Validation |
| `INVALID_EMAIL` | 422 | Invalid email | Validation |
| `INVALID_PASSWORD` | 422 | Invalid password | Validation |
| `MISSING_REQUIRED_FIELD` | 422 | Missing required field | Validation |
| `INVALID_FIELD_VALUE` | 422 | Invalid field value | Validation |
| `FILE_UPLOAD_ERROR` | 400 | File upload failed | File |
| `FILE_TOO_LARGE` | 413 | File too large | File |
| `INVALID_FILE_TYPE` | 415 | Invalid file type | File |
| `FILE_PROCESSING_ERROR` | 500 | File processing error | File |
| `EMAIL_ALREADY_EXISTS` | 409 | Email already exists | Conflict |
| `FILTER_ALREADY_BOUND` | 409 | Filter already bound | Conflict |
| `DUPLICATE_RESOURCE` | 409 | Duplicate resource | Conflict |
| `PROCESSING_FAILED` | 500 | Processing failed | Processing |
| `PROCESSING_IN_PROGRESS` | 500 | Processing in progress | Processing |

## Security Considerations

### No Sensitive Data Leakage

Error responses are carefully constructed to avoid exposing sensitive information:

- **No passwords or tokens** in error messages
- **No internal paths or stack traces** in production
- **No database details** (table names, column names beyond validation context)
- **No user enumeration** through error timing or messages

### Detail Field for Development Only

The `detail` field contains English developer-facing messages. In production:

- Messages are generic for user-facing scenarios
- Full details are logged server-side but returned minimally
- Error codes enable programmatic handling without exposing internals

### Error Codes for Programmatic Handling

The `code` field enables frontend applications to respond appropriately:

- Display specific UI elements based on error type
- Route errors to appropriate handlers
- Support localization by mapping codes to translated messages

### Global Handler Coverage

All error paths converge through registered exception handlers in `src/mkobi/utils/exceptions.py`:

1. **AppException handler**: Primary path for application errors
2. **RequestValidationError handler**: FastAPI validation errors with field-level details
3. **StarletteHTTPException handler**: Catches standard HTTP exceptions
4. **Global exception handler**: Catch-all for unexpected errors (returns 500)

This ensures consistent formatting even for unanticipated error conditions.

## Implementation Reference

### Backend Components

| Component | Location | Purpose |
| --- | --- | --- |
| `ErrorCode` enum | `src/mkobi/models/enums.py` | Central error code definitions |
| `AppException` | `src/mkobi/utils/exceptions.py` | Base exception class |
| `ErrorResponse` | `src/mkobi/utils/exceptions.py` | Pydantic response model |
| `add_exception_handlers` | `src/mkobi/utils/exceptions.py` | FastAPI handler registration |

### Frontend Components

| Component | Location | Purpose |
| --- | --- | --- |
| `ErrorCode` type | `frontend/src/shared/types/enums.ts` | TypeScript error code constants |
| `extractApiError` | `frontend/src/shared/api/errorHandler.ts` | Error extraction and parsing |

### Migration Notes

All API routes should use `AppException` for error raising:

```python
# Correct approach
raise PermissionDeniedException("Access denied to dashboard")

# Incorrect — never raise HTTPException directly
raise HTTPException(status_code=403, detail="Access denied")
```

The `AppException` class automatically maps `ErrorCode` values to HTTP status codes via `_ERROR_CODE_STATUS_MAP`.

### Refactoring Without Changing the Error Surface

Moving logic out of a route and into a service is not automatically
API-compatible. Two recent refactors are worth recording because both *were*
checked, and the difference matters when reviewing the next one:

- **Admin approval transaction moved into `AuthService` (2026-09-30).** The
  admin approval route stopped owning its transaction and delegated to
  `AuthService.approve_registration_request`. The endpoint still raises
  `NOT_FOUND`, `DUPLICATE_RESOURCE` and `INTERNAL_ERROR` through `AppException`,
  with the same statuses and response keys, so the table above is unchanged. The
  refactor was about the *order* of a commit and a non-transactional Redis write,
  not about the error contract — see
  [Admin API](../04-admin/admin-api.md#approval-sequence-and-transaction-ownership).
- **Destructive test-database recreation guarded (2026-09-30).** The refusal in
  `DatabaseStarter.recreate_test_database` raises
  `UnsafeTestDatabaseRecreationError`, a plain startup exception. It never
  reaches an HTTP response, so no `ErrorCode` was added for it.

The general rule these two establish: a change that moves *where* an error is
raised must still raise it through `AppException` with the same `ErrorCode`, or
it is an API change and needs its own entry in the table above.

## Frontend Integration

### Error Extraction Chain

The frontend error handler processes errors in this order:

1. **Legacy FastAPI validation format**: 422 status with `errors` array but no `code` field → mapped to `VALIDATION_ERROR`
2. **RFC 7807 format**: Response contains `code` field → used directly
3. **Field-level extraction**: For `VALIDATION_ERROR`, extracts field names and messages from `errors` array
4. **AxiosError fallback**: Uses `error.message` for Axios errors without structured response
5. **Generic fallback**: Returns `INTERNAL_ERROR` with generic message

### TypeScript Error Handling

```typescript
import { ErrorCode } from '../types/enums'
import { extractApiError } from './errorHandler'

try {
  await apiCall()
} catch (error) {
  const { code, message } = extractApiError(error)
  
  if (code === ErrorCode.VALIDATION_ERROR) {
    // Handle validation errors with field highlighting
  } else if (code === ErrorCode.TOKEN_EXPIRED) {
    // Trigger token refresh flow
  } else if (code === ErrorCode.PERMISSION_DENIED) {
    // Redirect to access request page
  }
}
```

## Cross-References

- [Security Overview](security-overview.md) — Rate limiting, CORS, credential enforcement
- [Access Control](access-control.md) — Dashboard-level permission enforcement model
- [Authentication API](../01-auth/auth-api.md) — Auth endpoint error handling
- [Frontend Security](../07-frontend/frontend-security.md) — JWT handling, CORS security