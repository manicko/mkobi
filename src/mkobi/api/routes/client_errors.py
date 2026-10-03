"""Routes for client-side error reporting.

This module provides an endpoint for frontend error logging.
No database persistence - errors are logged for monitoring.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, status

from mkobi.api.schemas.responses import auth_public_responses
from mkobi.config import get_config
from mkobi.core import redis_client
from mkobi.core.security import AsyncRateLimiter
from mkobi.models.data import (
    CLIENT_ERROR_STACKED_FIELD_NAMES,
    MAX_CLIENT_ERROR_BODY_BYTES,
    MAX_CLIENT_ERROR_FIELD_LENGTH,
    ClientErrorPayload,
)
from mkobi.models.enums import ErrorCode
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client-errors", tags=["client-errors"], redirect_slashes=False)


async def enforce_declared_content_length(request: Request) -> None:
    """Reject a body that *declares* a Content-Length above the ceiling.

    DP-11, option (c), first half. This runs as a dependency, ahead of the
    model validation that would otherwise reject an over-long value with 422,
    so a request that merely announces an oversized body is refused with 413.
    A chunked request declares no length and passes here; the parsed-value bound
    in ``report_client_error`` is what holds it.
    """
    declared_length = request.headers.get("content-length")
    if declared_length is None:
        return
    try:
        declared_bytes = int(declared_length)
    except ValueError:
        return
    if declared_bytes > MAX_CLIENT_ERROR_BODY_BYTES:
        raise AppException(
            code=ErrorCode.FILE_TOO_LARGE,
            detail="Client error report exceeds the maximum allowed size",
        )


def _bounded(value: str, *, name: str, truncated: dict[str, int]) -> str:
    """Truncate a single logged value to the field ceiling.

    When the value is capped, its untruncated length is recorded in
    ``truncated`` so it can be logged beside the capped value: an investigator
    can then tell a truncation from a genuinely short error.
    """
    if len(value) > MAX_CLIENT_ERROR_FIELD_LENGTH:
        truncated[name] = len(value)
        return value[:MAX_CLIENT_ERROR_FIELD_LENGTH]
    return value


def _bounded_error(error: dict[str, Any], *, truncated: dict[str, int]) -> dict[str, str]:
    """Render ``error`` as the three fields the caller sends, each bounded.

    ``error`` is ``dict[str, Any]``, so a Pydantic ``max_length`` on the field
    would bound the key count rather than the values; the values are bounded
    here, on the parsed value, and never rejected. Non-string values are
    omitted rather than coerced, so no unbounded value can reach the log.
    """
    return {
        name: _bounded(str(error[name]), name=name, truncated=truncated)
        for name in CLIENT_ERROR_STACKED_FIELD_NAMES
        if isinstance(error.get(name), str)
    }


@router.post(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Report client-side error",
    description="Accepts client error details for logging. No authentication required.",
    responses=auth_public_responses,
    dependencies=[Depends(enforce_declared_content_length)],
)
async def report_client_error(payload: ClientErrorPayload, request: Request) -> None:
    """Report client-side error.

    Logs error details from frontend without persisting to database.
    Rate limiting is applied per IP address to prevent DoS flooding attacks.

    Args:
        payload: Client error information including error, url, and context.
        request: FastAPI request object for extracting client IP.
    """
    config = get_config()
    client_ip = request.client.host if request.client else "unknown"

    # Rate limiting check
    rate_limiter = AsyncRateLimiter(
        redis_client.get_async_redis_client(),
        fail_closed=config.rate_limiter_fail_closed,
    )
    rate_limit_key = f"client-errors:{client_ip}"
    allowed, retry_after = await rate_limiter.check_rate_limit(rate_limit_key, max_attempts=100, ttl=3600)
    if not allowed:
        logger.warning(
            "Rate limit exceeded for client-errors endpoint",
            extra={"ip": client_ip},
        )
        raise AppException(
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            detail="Rate limit exceeded for client error reports",
            headers={"Retry-After": str(retry_after)} if retry_after else None,
        )

    # DP-11, option (c), second half: truncate on the parsed field values.
    # Every logged value is bounded before the log call, so no accepted body
    # can produce a record beyond the ceiling.
    truncated: dict[str, int] = {}
    error_fields = _bounded_error(payload.error, truncated=truncated)
    bounded_url = _bounded(payload.url, name="url", truncated=truncated)
    bounded_user_agent = _bounded(payload.userAgent, name="userAgent", truncated=truncated)
    bounded_component_stack = (
        _bounded(payload.componentStack, name="componentStack", truncated=truncated)
        if payload.componentStack is not None
        else None
    )

    # The untruncated length of every capped value is logged beside it, in the
    # same ERROR record, so the cap is auditable rather than silent.
    truncation_note = (
        " | truncated=" + ",".join(f"{name}:{length}" for name, length in truncated.items())
        if truncated
        else ""
    )
    logger.error(
        "Client error: error=%s | url=%s | userAgent=%s | componentStack=%s%s",
        error_fields,
        bounded_url,
        bounded_user_agent,
        bounded_component_stack,
        truncation_note,
    )