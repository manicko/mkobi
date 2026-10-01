---
id: error-handling-guide
domain: reference
tags:
  - error-handling
  - api
  - frontend
  - exceptions
  - troubleshooting
related:
  - error-format
  - security-overview
  - frontend-security
  - backend-architecture
---

# Error Handling Guide

## Purpose

This guide provides practical examples for implementing error handling in both backend (FastAPI) and frontend (React) code. All API errors follow RFC 7807 Problem Details format with ErrorCode extensions.

## Main Concepts

- All API errors use `AppException` with `ErrorCode` enum values
- Backend exceptions are handled by `add_exception_handlers(app)` in `src/mkobi/utils/exceptions.py`
- Frontend errors are extracted via `extractApiError()` in `frontend/src/shared/api/errorHandler.ts`
- Error messages are localized via `getErrorMessage()` in `frontend/src/shared/api/errorMessages.ts`

## Backend: Raising Errors

### Quick Reference

Import required classes:

```python
from mkobi.models.enums import ErrorCode
from mkobi.utils.exceptions import AppException, NotFoundException, PermissionDeniedException, ValidationException, FileUploadException, AuthenticationException, ConflictException
```

### Common Patterns

#### Resource Not Found

```python
# Using specialized NotFoundException (defaults to NOT_FOUND)
raise NotFoundException("Dashboard not found")

# Using AppException with specific code and details
raise AppException(
    code=ErrorCode.DASHBOARD_NOT_FOUND,
    detail="Dashboard not found",
    details={"dashboard_id": str(dashboard_id)},
)
```

#### Permission Denied

```python
# Using specialized exception
raise PermissionDeniedException("You don't have access to this dashboard")

# Or with ACCESS_DENIED
raise AppException(
    code=ErrorCode.ACCESS_DENIED,
    detail="Access denied",
)
```

#### Validation Errors

```python
raise ValidationException("Invalid dashboard configuration")

# With field-level details
raise AppException(
    code=ErrorCode.VALIDATION_ERROR,
    detail="Validation failed",
    details={"field": "name", "error": "Must be at least 3 characters"},
)
```

#### File Upload Errors

```python
raise FileUploadException("Failed to save uploaded file")

raise AppException(
    code=ErrorCode.FILE_TOO_LARGE,
    detail="File exceeds maximum size of 100MB",
    details={"max_size_mb": 100, "file_size_mb": 150},
)

raise AppException(
    code=ErrorCode.INVALID_FILE_TYPE,
    detail="Invalid MIME type for file upload",
    details={"allowed_types": ["text/csv", "application/gzip"]},
)
```

#### Authentication Errors

```python
raise AuthenticationException("Invalid credentials")

raise AppException(
    code=ErrorCode.TOKEN_EXPIRED,
    detail="Access token has expired",
)
```

#### Conflict Errors

```python
raise ConflictException("Email already registered")

raise AppException(
    code=ErrorCode.EMAIL_ALREADY_EXISTS,
    detail="User with this email already exists",
    details={"email": user_email},
)
```

### Complete Example

```python
from mkobi.models.enums import ErrorCode
from mkobi.utils.exceptions import AppException, NotFoundException

async def get_dashboard(dashboard_id: UUID, db: AsyncSession, user: User) -> Dashboard:
    dashboard = await dashboard_repository.get(dashboard_id, db)
    if dashboard is None:
        raise AppException(
            code=ErrorCode.DASHBOARD_NOT_FOUND,
            detail="Dashboard not found",
            details={"dashboard_id": str(dashboard_id)},
        )

    # Check resource-level access
    if not has_permission(user, dashboard, DashboardPermission.VIEW):
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="You don't have permission to view this dashboard",
        )

    return dashboard
```

## Frontend: Handling Errors

### Quick Reference

```typescript
import { extractApiError, getErrorMessage } from '@/shared/api/errorHandler'
import { ErrorCode } from '@/shared/types/enums'
```

### Common Patterns

#### Using extractApiError

```typescript
import { extractApiError } from '@/shared/api/errorHandler'

// In try/catch block
try {
    await api.uploadFile(file)
} catch (error) {
    const extracted = extractApiError(error)
    console.error('Error code:', extracted.code)
    console.error('Error message:', extracted.message)
    console.error('Error details:', extracted.details)
}
```

#### Using getErrorMessage for Localization

```typescript
import { getErrorMessage, sharedErrorMessages } from '@/shared/api/errorMessages'
import { ErrorCode } from '@/shared/types/enums'

// Get user-friendly Russian message
const userMessage = getErrorMessage(ErrorCode.DASHBOARD_NOT_FOUND)
// Returns: "Дашборд не найден"
```

#### Feature-Specific Error Messages

```typescript
import { getErrorMessage } from '@/shared/api/errorMessages'
import { ErrorCode } from '@/shared/types/enums'

// Feature-specific override
const featureMessages = {
    [ErrorCode.VALIDATION_ERROR]: 'Проверьте правильность заполнения формы',
}

const message = getErrorMessage(
    ErrorCode.VALIDATION_ERROR,
    featureMessages
)
```

### Complete Example with React Hook Form

```typescript
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { extractApiError, getErrorMessage } from '@/shared/api/errorHandler'
import { ErrorCode } from '@/shared/types/enums'

const schema = z.object({
    name: z.string().min(3),
    email: z.string().email(),
})

export function DashboardForm() {
    const { register, handleSubmit, setError, formState: { errors } } = useForm({
        resolver: zodResolver(schema),
    })

    const onSubmit = async (data: FormData) => {
        try {
            await api.createDashboard(data)
        } catch (error) {
            const extracted = extractApiError(error)

            if (extracted.code === ErrorCode.VALIDATION_ERROR && extracted.details?.validation_errors) {
                // Set field-level errors
                const validationErrors = extracted.details.validation_errors as any[]
                validationErrors.forEach((err: any) => {
                    if (err.loc?.[err.loc.length - 1]) {
                        setError(err.loc[err.loc.length - 1] as string, {
                            type: 'manual',
                            message: err.msg,
                        })
                    }
                })
            } else {
                // Show general error
                toast.error(getErrorMessage(extracted.code))
            }
        }
    }
}
```

## ErrorCode Quick Reference

### General Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INTERNAL_ERROR` | 500 | Internal server error |
| `SERVICE_UNAVAILABLE` | 503 | Service unavailable |
| `RATE_LIMIT_EXCEEDED` | 429 | Rate limit exceeded |

### Authentication Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `AUTHENTICATION_FAILED` | 401 | Authentication failed |
| `TOKEN_EXPIRED` | 401 | Token expired |
| `TOKEN_REVOKED` | 401 | Token revoked |
| `INVALID_TOKEN` | 401 | Invalid token |

### Authorization Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `PERMISSION_DENIED` | 403 | Permission denied |
| `INSUFFICIENT_PERMISSIONS` | 403 | Insufficient permissions |
| `ACCESS_DENIED` | 403 | Access denied |

### Resource Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `NOT_FOUND` | 404 | Resource not found |
| `DASHBOARD_NOT_FOUND` | 404 | Dashboard not found |
| `USER_NOT_FOUND` | 404 | User not found |
| `GRAPH_NOT_FOUND` | 404 | Graph not found |
| `FILTER_NOT_FOUND` | 404 | Filter not found |
| `LAYOUT_NOT_FOUND` | 404 | Layout not found |
| `PROCESSING_CONFIG_NOT_FOUND` | 404 | Processing config not found |

### Validation Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 422 | Validation error |
| `INVALID_EMAIL` | 422 | Invalid email |
| `INVALID_PASSWORD` | 422 | Invalid password |
| `MISSING_REQUIRED_FIELD` | 422 | Missing required field |
| `INVALID_FIELD_VALUE` | 422 | Invalid field value |

### File Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `FILE_UPLOAD_ERROR` | 400 | File upload error |
| `FILE_TOO_LARGE` | 413 | File too large |
| `INVALID_FILE_TYPE` | 415 | Invalid file type |
| `FILE_PROCESSING_ERROR` | 500 | File processing error |

### Conflict Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `EMAIL_ALREADY_EXISTS` | 409 | Email already exists |
| `FILTER_ALREADY_BOUND` | 409 | Filter already bound |
| `DUPLICATE_RESOURCE` | 409 | Duplicate resource |

### Processing Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `PROCESSING_FAILED` | 500 | Processing failed |
| `PROCESSING_IN_PROGRESS` | 500 | Processing in progress |

## Migration Guide: HTTPException → AppException

### Before (HTTPException)

```python
from fastapi import HTTPException

# Simple 404
raise HTTPException(status_code=404, detail="Dashboard not found")

# Validation error
raise HTTPException(status_code=422, detail="Invalid email format")

# Conflict
raise HTTPException(status_code=409, detail="Email already exists")
```

**Problems:**
- No machine-readable error code
- Inconsistent error format
- Hard to handle on frontend

### After (AppException)

```python
from mkobi.models.enums import ErrorCode
from mkobi.utils.exceptions import AppException, NotFoundException

# Resource not found
raise NotFoundException("Dashboard not found")

# Or with specific code
raise AppException(
    code=ErrorCode.DASHBOARD_NOT_FOUND,
    detail="Dashboard not found",
    details={"dashboard_id": str(dashboard_id)},
)

# Validation error
raise AppException(
    code=ErrorCode.INVALID_EMAIL,
    detail="Invalid email format",
)

# Conflict
raise AppException(
    code=ErrorCode.EMAIL_ALREADY_EXISTS,
    detail="Email already exists",
    details={"email": user_email},
)
```

### Response Comparison

**Before (HTTPException):**
```json
{
    "detail": "Dashboard not found"
}
```

**After (AppException):**
```json
{
    "type": "https://api.mkobi.com/errors/dashboard_not_found",
    "title": "Dashboard not found",
    "status": 404,
    "detail": "Dashboard not found",
    "code": "DASHBOARD_NOT_FOUND",
    "details": {"dashboard_id": "123e4567-e89b-12d3-a456-426614174000"}
}
```

### Moving a Transaction Into a Service Without Changing Any Code

Moving error-raising logic out of a route and into a service is where error
contracts usually break. Two refactorings in this repository did **not** break
one, and the check is cheap to repeat:

| Change | Error surface |
|---|---|
| Admin approval route delegates to `AuthService.approve_registration_request` (2026-09-30) | Unchanged — still `NOT_FOUND`, `DUPLICATE_RESOURCE`, `INTERNAL_ERROR` via `AppException`, same statuses and response keys |
| `DatabaseStarter.recreate_test_database` gains an environment and name guard (2026-09-30) | `UnsafeTestDatabaseRecreationError` is a startup exception; it never reaches HTTP, so no `ErrorCode` was added |

When you do the same refactor yourself, three things keep the contract intact:

1. Keep raising through `AppException` with the **same `ErrorCode`**. A new code
   is a new row in the tables above and a change for every frontend consumer.
2. Keep the `detail` strings clients may match on. Re-wording a `detail` is a
   behaviour change even though the status code is identical.
3. Do not let the service swallow an exception the route used to map. If the
   service returns `None` to mean "not found", the route must translate that
   back into the same `AppException` it raised before — a sentinel return is not
   a substitute for an error contract.

## Troubleshooting Common Mistakes

### Backend

#### 1. Forgetting to Register Exception Handlers

**Problem:** Errors return as generic HTTPException format.

**Solution:** Ensure `add_exception_handlers(app)` is called in `src/mkobi/app.py`:

```python
from mkobi.utils.exceptions import add_exception_handlers

app = FastAPI()
add_exception_handlers(app)
```

#### 2. Using HTTPException Directly (Forbidden)

**Wrong:**
```python
raise HTTPException(status_code=404, detail="Not found")
```

**Correct:**
```python
raise AppException(code=ErrorCode.NOT_FOUND, detail="Not found")
```

#### 3. Hardcoding Error Code Strings

**Wrong:**
```python
raise AppException(code="NOT_FOUND", detail="Not found")
```

**Correct:**
```python
raise AppException(code=ErrorCode.NOT_FOUND, detail="Not found")
```

#### 4. Missing type hints on AppException

Always ensure type hints are present. The constructor signature is:

```python
def __init__(
    self,
    code: ErrorCode | None = None,
    detail: str = "",
    details: dict[str, Any] | None = None,
    status_code: int | None = None,
    error_code: str | None = None,  # Legacy, prefer code
    headers: dict[str, str] | None = None,
) -> None:
```

### Frontend

#### 1. Not Handling Legacy Validation Format

**Problem:** Validation errors from FastAPI don't show field-level details.

**Solution:** The `extractApiError` function handles both legacy (422 without `code` field) and RFC 7807 formats automatically.

#### 2. Using English Messages Directly

**Problem:** Displaying technical error messages to users.

**Solution:** Always use `getErrorMessage()` for user-facing text:

```typescript
// Wrong
toast.error(extracted.message)

// Correct
toast.error(getErrorMessage(extracted.code, featureMessages))
```

#### 3. Missing ErrorCode Import

**Wrong:**
```typescript
if (extracted.code === 'VALIDATION_ERROR') ...
```

**Correct:**
```typescript
import { ErrorCode } from '@/shared/types/enums'

if (extracted.code === ErrorCode.VALIDATION_ERROR) ...
```

## Related Documentation

- [Error Format Specification](../08-security/error-format.md) — RFC 7807 format details
- [API Routes](../02-dashboards/dashboards-api.md) — Dashboard API endpoints
- [Authentication API](../01-auth/auth-api.md) — Auth error codes
- [Backend Architecture](../06-backend/architecture.md) — Layer separation and error flow
- [AGENTS.md Error Handling Section](../../AGENTS.md#error-handling)