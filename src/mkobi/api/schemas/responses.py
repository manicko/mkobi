"""Shared OpenAPI response schemas for error documentation.

Provides reusable response dictionaries for documenting common error responses
in FastAPI route decorators following RFC 7807 Problem Details format.
"""

from mkobi.models.error_response import ErrorResponse

# Reusable error response schema for OpenAPI documentation
error_400 = {
    "description": "Bad Request - Invalid input data",
    "model": ErrorResponse,
}

error_401 = {
    "description": "Unauthorized - Authentication required or invalid credentials",
    "model": ErrorResponse,
}

error_403 = {
    "description": "Forbidden - Insufficient permissions",
    "model": ErrorResponse,
}

error_404 = {
    "description": "Not Found - Resource does not exist",
    "model": ErrorResponse,
}

error_409 = {
    "description": "Conflict - Resource state conflict (e.g., duplicate)",
    "model": ErrorResponse,
}

error_422 = {
    "description": "Unprocessable Content - Validation error",
    "model": ErrorResponse,
}

error_429 = {
    "description": "Too Many Requests - Rate limit exceeded",
    "model": ErrorResponse,
}

error_500 = {
    "description": "Internal Server Error",
    "model": ErrorResponse,
}

error_503 = {
    "description": "Service Unavailable - Upstream dependency unreachable",
    "model": ErrorResponse,
}

error_413 = {
    "description": "Payload Too Large - File size exceeds limit",
    "model": ErrorResponse,
}

error_415 = {
    "description": "Unsupported Media Type - Invalid file type",
    "model": ErrorResponse,
}

# Auth endpoints - public endpoints (no auth required for some, but can return 401/422).
# Only ``POST /auth/refresh`` can answer 503 when the revocation store is
# unreachable, so that route unpacks 503 in its own decorator rather than this
# shared dict. The other public routes fail closed on a Redis fault and answer
# 429, so declaring 503 here would misdocument their OpenAPI surface.
auth_public_responses = {
    401: error_401,
    422: error_422,
    429: error_429,
    500: error_500,
}

# Auth endpoints - protected endpoints (require authentication). Every route
# behind ``get_current_user_dependency`` can now answer 503 when the revocation
# store is unreachable, so 503 is declared here too.
auth_protected_responses = {
    401: error_401,
    403: error_403,
    404: error_404,
    422: error_422,
    429: error_429,
    500: error_500,
    503: error_503,
}

# Admin endpoints
admin_responses = {
    401: error_401,
    403: error_403,
    404: error_404,
    422: error_422,
    429: error_429,
    500: error_500,
}

# Resource endpoints (CRUD with specific resources)
resource_responses = {
    400: error_400,
    401: error_401,
    403: error_403,
    404: error_404,
    409: error_409,
    422: error_422,
    429: error_429,
    500: error_500,
}

__all__ = [
    "error_400",
    "error_401",
    "error_403",
    "error_404",
    "error_409",
    "error_413",
    "error_415",
    "error_422",
    "error_429",
    "error_500",
    "error_503",
    "auth_public_responses",
    "auth_protected_responses",
    "admin_responses",
    "resource_responses",
]