"""Custom exceptions for the application.

Provides base application exception and specialized subclasses, plus FastAPI exception handlers.
All error responses follow RFC 7807 Problem Details format with extensions.
"""

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.status import HTTP_400_BAD_REQUEST
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.status import HTTP_403_FORBIDDEN
from starlette.status import HTTP_404_NOT_FOUND
from starlette.status import HTTP_409_CONFLICT
from starlette.status import HTTP_413_CONTENT_TOO_LARGE
from starlette.status import HTTP_415_UNSUPPORTED_MEDIA_TYPE
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR
from starlette.status import HTTP_503_SERVICE_UNAVAILABLE
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mkobi.core.logging_config import get_logger
from mkobi.models.enums import ErrorCode
from mkobi.models.error_response import ErrorResponse

logger = get_logger(__name__)


# Status code mapping from ErrorCode to HTTP status codes
_ERROR_CODE_STATUS_MAP: dict[ErrorCode, int] = {
    # General errors
    ErrorCode.INTERNAL_ERROR: HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.SERVICE_UNAVAILABLE: HTTP_503_SERVICE_UNAVAILABLE,
    ErrorCode.RATE_LIMIT_EXCEEDED: HTTP_429_TOO_MANY_REQUESTS,
    # Authentication errors
    ErrorCode.AUTHENTICATION_FAILED: HTTP_401_UNAUTHORIZED,
    ErrorCode.TOKEN_EXPIRED: HTTP_401_UNAUTHORIZED,
    ErrorCode.TOKEN_REVOKED: HTTP_401_UNAUTHORIZED,
    ErrorCode.INVALID_TOKEN: HTTP_401_UNAUTHORIZED,
    # Authorization errors
    ErrorCode.PERMISSION_DENIED: HTTP_403_FORBIDDEN,
    ErrorCode.INSUFFICIENT_PERMISSIONS: HTTP_403_FORBIDDEN,
    ErrorCode.ACCESS_DENIED: HTTP_403_FORBIDDEN,
    # Resource errors
    ErrorCode.NOT_FOUND: HTTP_404_NOT_FOUND,
    ErrorCode.DASHBOARD_NOT_FOUND: HTTP_404_NOT_FOUND,
    ErrorCode.USER_NOT_FOUND: HTTP_404_NOT_FOUND,
    ErrorCode.GRAPH_NOT_FOUND: HTTP_404_NOT_FOUND,
    ErrorCode.FILTER_NOT_FOUND: HTTP_404_NOT_FOUND,
    ErrorCode.LAYOUT_NOT_FOUND: HTTP_404_NOT_FOUND,
    ErrorCode.PROCESSING_CONFIG_NOT_FOUND: HTTP_404_NOT_FOUND,
    # Validation errors
    ErrorCode.VALIDATION_ERROR: HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.INVALID_EMAIL: HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.INVALID_PASSWORD: HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.MISSING_REQUIRED_FIELD: HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.INVALID_FIELD_VALUE: HTTP_422_UNPROCESSABLE_CONTENT,
    # File errors
    ErrorCode.FILE_UPLOAD_ERROR: HTTP_400_BAD_REQUEST,
    ErrorCode.FILE_TOO_LARGE: HTTP_413_CONTENT_TOO_LARGE,
    ErrorCode.INVALID_FILE_TYPE: HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    ErrorCode.FILE_PROCESSING_ERROR: HTTP_500_INTERNAL_SERVER_ERROR,
    # Conflict errors
    ErrorCode.EMAIL_ALREADY_EXISTS: HTTP_409_CONFLICT,
    ErrorCode.FILTER_ALREADY_BOUND: HTTP_409_CONFLICT,
    ErrorCode.DUPLICATE_RESOURCE: HTTP_409_CONFLICT,
    # Processing errors
    ErrorCode.PROCESSING_FAILED: HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.PROCESSING_IN_PROGRESS: HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.INVALID_TRANSITION: HTTP_400_BAD_REQUEST,
}


class AppException(Exception):
    """Base application exception.

    All exceptions in the application should inherit from this class.
    Uses ErrorCode enum for machine-readable error codes.
    """

    def __init__(
        self,
        code: ErrorCode | None = None,
        detail: str = "",
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize AppException.

        New signature accepts code: ErrorCode. For backward compatibility,
        error_code: str can still be used and will be converted to ErrorCode.

        Args:
            code: Machine-readable error code from ErrorCode enum (preferred).
            detail: Human-readable error message. Defaults to empty string.
            details: Optional structured context dictionary.
            status_code: Optional override for HTTP status code. If not provided,
                derived from ErrorCode via _ERROR_CODE_STATUS_MAP.
            error_code: Legacy string error code (for backward compatibility).
            headers: Optional HTTP headers to include in response.
        """
        # Handle backward compatibility: if error_code provided, convert to ErrorCode
        if code is None and error_code is not None:
            try:
                code = ErrorCode(error_code)
            except ValueError:
                code = ErrorCode.INTERNAL_ERROR

        if code is None:
            code = ErrorCode.INTERNAL_ERROR

        self.code = code
        self.detail = detail
        self.details = details
        self.headers = headers
        self.status_code = (
            status_code if status_code is not None
            else _ERROR_CODE_STATUS_MAP.get(code, HTTP_500_INTERNAL_SERVER_ERROR)
        )
        super().__init__(detail)

    @property
    def error_code(self) -> str:
        """Compatibility property for legacy access to error code."""
        return str(self.code.value)


class NotFoundException(AppException):
    """Exception raised when a resource is not found."""

    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(code=ErrorCode.NOT_FOUND, detail=detail)


class PermissionDeniedException(AppException):
    """Exception raised when user lacks permission."""

    def __init__(self, detail: str = "Permission denied") -> None:
        super().__init__(code=ErrorCode.PERMISSION_DENIED, detail=detail)


class ValidationException(AppException):
    """Exception raised for validation errors."""

    def __init__(self, detail: str = "Validation error") -> None:
        super().__init__(code=ErrorCode.VALIDATION_ERROR, detail=detail)


class FileUploadException(AppException):
    """Exception raised for file upload errors."""

    def __init__(self, detail: str = "File upload failed") -> None:
        super().__init__(code=ErrorCode.FILE_UPLOAD_ERROR, detail=detail)


class AuthenticationException(AppException):
    """Exception raised for authentication failures."""

    def __init__(self, detail: str = "Authentication failed") -> None:
        super().__init__(code=ErrorCode.AUTHENTICATION_FAILED, detail=detail)


class ConflictException(AppException):
    """Exception raised for conflict errors (e.g., duplicate email)."""

    def __init__(self, detail: str = "Resource conflict") -> None:
        super().__init__(code=ErrorCode.EMAIL_ALREADY_EXISTS, detail=detail)


def get_error_title(code: ErrorCode) -> str:
    """Get human-readable title for an error code.

    Args:
        code: The error code to get the title for.

    Returns:
        A short, human-readable title string.
    """
    titles: dict[ErrorCode, str] = {
        # General errors
        ErrorCode.INTERNAL_ERROR: "Internal server error",
        ErrorCode.SERVICE_UNAVAILABLE: "Service unavailable",
        ErrorCode.RATE_LIMIT_EXCEEDED: "Rate limit exceeded",
        # Authentication errors
        ErrorCode.AUTHENTICATION_FAILED: "Authentication failed",
        ErrorCode.TOKEN_EXPIRED: "Token expired",
        ErrorCode.TOKEN_REVOKED: "Token revoked",
        ErrorCode.INVALID_TOKEN: "Invalid token",
        # Authorization errors
        ErrorCode.PERMISSION_DENIED: "Permission denied",
        ErrorCode.INSUFFICIENT_PERMISSIONS: "Insufficient permissions",
        ErrorCode.ACCESS_DENIED: "Access denied",
        # Resource errors
        ErrorCode.NOT_FOUND: "Resource not found",
        ErrorCode.DASHBOARD_NOT_FOUND: "Dashboard not found",
        ErrorCode.USER_NOT_FOUND: "User not found",
        ErrorCode.GRAPH_NOT_FOUND: "Graph not found",
        ErrorCode.FILTER_NOT_FOUND: "Filter not found",
        ErrorCode.LAYOUT_NOT_FOUND: "Layout not found",
        ErrorCode.PROCESSING_CONFIG_NOT_FOUND: "Processing config not found",
        # Validation errors
        ErrorCode.VALIDATION_ERROR: "Validation error",
        ErrorCode.INVALID_EMAIL: "Invalid email",
        ErrorCode.INVALID_PASSWORD: "Invalid password",
        ErrorCode.MISSING_REQUIRED_FIELD: "Missing required field",
        ErrorCode.INVALID_FIELD_VALUE: "Invalid field value",
        # File errors
        ErrorCode.FILE_UPLOAD_ERROR: "File upload error",
        ErrorCode.FILE_TOO_LARGE: "File too large",
        ErrorCode.INVALID_FILE_TYPE: "Invalid file type",
        ErrorCode.FILE_PROCESSING_ERROR: "File processing error",
        # Conflict errors
        ErrorCode.EMAIL_ALREADY_EXISTS: "Email already exists",
        ErrorCode.FILTER_ALREADY_BOUND: "Filter already bound",
        ErrorCode.DUPLICATE_RESOURCE: "Duplicate resource",
        # Processing errors
        ErrorCode.PROCESSING_FAILED: "Processing failed",
        ErrorCode.PROCESSING_IN_PROGRESS: "Processing in progress",
        ErrorCode.INVALID_TRANSITION: "Invalid state transition",
    }
    return titles.get(code, "Error")


def add_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for custom exceptions in FastAPI app.

    Handlers produce RFC 7807 JSON responses in order:
    1. AppException handler
    2. StarletteHTTPException handler (for FastAPI default validation errors)
    3. Global exception handler (catches all unexpected errors)
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException,
    ) -> JSONResponse:
        logger.error(
            "AppException raised: code=%s, detail=%s",
            exc.code.value,
            exc.detail,
        )
        response = ErrorResponse(
            type=f"https://api.mkobi.com/errors/{exc.code.value.lower()}",
            title=get_error_title(exc.code),
            status=exc.status_code,
            detail=exc.detail,
            code=exc.code,
            details=exc.details,
        )
        # Filter out None header values
        filtered_headers = {k: v for k, v in (exc.headers or {}).items() if v is not None}
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(),
            headers=filtered_headers if filtered_headers else None,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request, exc: RequestValidationError,
    ) -> JSONResponse:
        """Handler for FastAPI request validation errors.

        Produces RFC 7807 format with additional 'errors' array containing
        field-level validation details.

        Each entry is rebuilt from an allow-list so it can never carry the
        offending raw value: Pydantic's ``errors()`` includes an ``input`` key
        holding the submitted value, and password fields are plain strings, so
        echoing it would leak a submitted plaintext password into both the log
        record and the response body. ``url`` is dropped for the same reason:
        it can echo request context. Only ``loc``, ``msg``, ``type`` and the
        stringified ``ctx["error"]`` are retained.
        """
        safe_errors = [
            {
                "loc": list(err.get("loc", ())),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
                **(
                    {"ctx": {"error": str(err["ctx"]["error"])}}
                    if "ctx" in err and "error" in err["ctx"]
                    else {}
                ),
            }
            for err in exc.errors()
        ]
        logger.error(
            "RequestValidationError raised: %s",
            safe_errors,
        )
        response = ErrorResponse(
            type="https://api.mkobi.com/errors/validation_error",
            title="Validation error",
            status=HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Request validation failed",
            code=ErrorCode.VALIDATION_ERROR,
            details=None,
        )
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                **response.model_dump(),
                "errors": safe_errors,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def starlette_exception_handler(
        request: Request, exc: StarletteHTTPException,
    ) -> JSONResponse:
        logger.error(
            "StarletteHTTPException raised: status_code=%s, detail=%s",
            exc.status_code,
            exc.detail,
        )
        # Map common HTTP status codes to error codes
        status_to_code: dict[int, ErrorCode] = {
            HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
            HTTP_401_UNAUTHORIZED: ErrorCode.AUTHENTICATION_FAILED,
            HTTP_403_FORBIDDEN: ErrorCode.PERMISSION_DENIED,
            HTTP_400_BAD_REQUEST: ErrorCode.VALIDATION_ERROR,
            HTTP_422_UNPROCESSABLE_CONTENT: ErrorCode.VALIDATION_ERROR,
        }
        code = status_to_code.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        response = ErrorResponse(
            type=f"https://api.mkobi.com/errors/{code.value.lower()}",
            title=get_error_title(code),
            status=exc.status_code,
            detail=str(exc.detail) if exc.detail else get_error_title(code),
            code=code,
            details=None,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception,
    ) -> JSONResponse:
        logger.error("Unhandled exception: %s", exc)
        response = ErrorResponse(
            type="https://api.mkobi.com/errors/internal_error",
            title="Internal server error",
            status=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            code=ErrorCode.INTERNAL_ERROR,
            details=None,
        )
        return JSONResponse(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            content=response.model_dump(),
        )