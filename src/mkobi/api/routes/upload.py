"""Upload and processing routes.

This module provides endpoints for:
- Uploading CSV files
- Checking processing status

All operations require authentication and appropriate permissions.
"""

from pathlib import Path
from typing import NoReturn
from uuid import UUID, uuid4

import aiofiles
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    EditorUser,
    get_db_dependency,
    get_data_service,
)
from mkobi.api.schemas.responses import (
    auth_protected_responses,
    error_400,
    error_401,
    error_403,
    error_413,
    error_415,
    error_422,
    error_429,
    error_500,
)
from mkobi.config import get_config
from mkobi.core.logging_config import get_logger
from mkobi.core import redis_client
from mkobi.core.permissions import DashboardPermissionError
from mkobi.core.security import AsyncRateLimiter
from mkobi.models.data import (
    ProcessingResult,
    ProcessingStatusResponse,
    UploadResponse,
)
from mkobi.models.enums import ErrorCode, UploadMode
from mkobi.services.data_service import DataService
from mkobi.utils.exceptions import AppException, get_error_title

router = APIRouter(prefix="/upload", tags=["upload"])

logger = get_logger(__name__)

# Chunk size for streaming file uploads (8KB)
CHUNK_SIZE = 8192


def _handle_value_error(error: Exception) -> NoReturn:
    """Raise a classified ``AppException`` for an upload admission failure.

    Classifies by the exception's own code where one is available: an
    ``AppException`` (or any exception exposing a ``code`` that is a member of
    the project's :class:`ErrorCode`) is raised as that code. Exceptions with no
    usable code fall through to a substring table that exists **only as a
    fallback** for code-less driver and library exceptions, then to the
    ``VALIDATION_ERROR`` default.

    Args:
        error: The exception raised during upload admission.

    Raises:
        AppException: Always, carrying the classified error code.
    """
    logger.warning("Validation error during upload", exc_info=True)

    # Code-first: an exception carrying a usable ErrorCode is classified by it.
    # The caller gets the code's fixed title, never the exception's text, which
    # can carry a path or other internal state. The text is already in the log
    # line above via exc_info.
    code = getattr(error, "code", None)
    if isinstance(code, ErrorCode):
        raise AppException(code=code, detail=get_error_title(code)) from error
    if isinstance(code, str):
        try:
            resolved = ErrorCode(code)
        except ValueError:
            pass
        else:
            raise AppException(code=resolved, detail=get_error_title(resolved)) from error

    # --- Substring fallback for code-less driver and library exceptions ---
    # Not the primary classifier: this table exists only for exceptions that
    # carry no ErrorCode.
    error_msg = str(error).lower()
    if "mime" in error_msg or "invalid mime" in error_msg:
        raise AppException(
            code=ErrorCode.INVALID_FILE_TYPE,
            detail="Invalid file type",
        ) from error
    elif (
        "format" in error_msg
        or "invalid format" in error_msg
        or "extension" in error_msg
    ):
        raise AppException(
            code=ErrorCode.INVALID_FILE_TYPE,
            detail="Invalid file format",
        ) from error
    elif "size" in error_msg or "exceeds" in error_msg or "max" in error_msg:
        raise AppException(
            code=ErrorCode.FILE_TOO_LARGE,
            detail="File size exceeds limit",
        ) from error
    elif "limit" in error_msg or "rate limit" in error_msg:
        raise AppException(
            code=ErrorCode.RATE_LIMIT_EXCEEDED,
            detail="Rate limit exceeded",
        ) from error
    else:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail="Validation error",
        ) from error


@router.post(
    "/{dashboard_id}",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload file",
    description="Uploads a CSV file for processing. Available to editors and admins only.",
    responses={
        400: error_400,
        401: error_401,
        403: error_403,
        413: error_413,
        415: error_415,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def upload_file_endpoint(
    dashboard_id: UUID,
    current_user: EditorUser,
    file: UploadFile = File(...),
    mode: UploadMode = UploadMode.OVERWRITE,
    db: AsyncSession = Depends(get_db_dependency),
    data_service: DataService = Depends(get_data_service),
) -> UploadResponse:
    """Upload file for dashboard."""
    logger.info(
        "File upload started",
        extra={
            "file_name": file.filename,
            "dashboard_id": str(dashboard_id),
            "user_id": str(current_user.id),
        },
    )

    try:
        config = get_config()

        # Enforce file size limit before reading into memory
        if file.size is not None and file.size > config.max_file_size:
            logger.warning(
                "File size exceeds limit",
                extra={
                    "file_name": file.filename,
                    "size_bytes": file.size,
                    "max_bytes": config.max_file_size,
                },
            )
            raise AppException(
                code=ErrorCode.FILE_TOO_LARGE,
                detail=f"File size exceeds maximum limit of {config.upload.max_file_size_mb}MB",
            )

        # Apply rate limiting for upload endpoint
        rate_limiter = AsyncRateLimiter(
            redis_client.get_async_redis_client(),
            fail_closed=config.rate_limiter_fail_closed,
        )
        allowed, retry_after = await rate_limiter.check_rate_limit(
            f"upload:{current_user.id}",
            max_attempts=100,
            ttl=3600,
        )
        if not allowed:
            logger.warning(
                "Upload rate limit exceeded",
                extra={"user_id": str(current_user.id)},
            )
            raise AppException(
                code=ErrorCode.RATE_LIMIT_EXCEEDED,
                detail="Rate limit exceeded for uploads",
                headers={"Retry-After": str(retry_after)} if retry_after else None,
            )

        # Read and stream file content to temporary location
        filename = file.filename or "unknown"
        sanitized_filename = Path(filename).name

        # Create temporary file path with unique name
        upload_dir = Path(get_config().upload_temp_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        temp_file_path = upload_dir / f"upload_{uuid4()}_{sanitized_filename}"

        try:
            # Stream file in chunks to reduce memory pressure
            total_bytes = 0
            async with aiofiles.open(temp_file_path, "wb") as f:
                while chunk := await file.read(CHUNK_SIZE):
                    total_bytes += len(chunk)
                    # Enforce size limit during streaming even when file.size is None
                    # This prevents disk exhaustion attacks when Content-Length is missing
                    if total_bytes > config.max_file_size:
                        await file.close()
                        temp_file_path.unlink(missing_ok=True)
                        logger.warning(
                            "Upload rejected: cumulative size exceeds limit",
                            extra={
                                "file_name": sanitized_filename,
                                "size_bytes": total_bytes,
                                "max_bytes": config.max_file_size,
                            },
                        )
                        raise AppException(
                            code=ErrorCode.FILE_TOO_LARGE,
                            detail=f"File size exceeds maximum limit of {config.upload.max_file_size_mb}MB",
                        )
                    await f.write(chunk)

            await file.close()

            logger.info(
                "File streamed to disk",
                extra={"file_name": sanitized_filename, "size_bytes": total_bytes},
            )

            # Call service (validation is in service layer)
            result = await data_service.process_upload(
                file_path=str(temp_file_path),
                dashboard_id=dashboard_id,
                user_id=current_user.id,
                filename=filename,
                content_type=file.content_type,
                mode=mode,
                db=db,
            )

            logger.info(
                "File uploaded successfully",
                extra={
                    "task_id": str(result.task_id),
                    "file_name": file.filename,
                    "mode": mode,
                },
            )

            return result
        finally:
            # Clean up temp file if processing failed (file was not moved to final location)
            # temp_file_path no longer exists if process_upload succeeded (file was moved)
            if temp_file_path.exists():
                logger.info("Cleaning up temp file after failed upload", extra={"path": str(temp_file_path)})
                temp_file_path.unlink(missing_ok=True)

    except AppException as e:
        # Re-raise AppException to let global handler format it with error_code
        raise e
    except ValueError as e:
        _handle_value_error(e)
    except DashboardPermissionError as e:
        logger.warning("Permission denied for upload: %s", e)
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="Permission denied",
        ) from e
    except Exception as e:
        logger.error("Error during file upload", exc_info=True)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error during file upload",
        ) from e


@router.get(
    "/status/{task_id}",
    response_model=ProcessingStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get processing status",
    description="Returns current processing status of file.",
    responses=auth_protected_responses,
)
async def get_status_endpoint(
    task_id: UUID,
    current_user: EditorUser,
    db: AsyncSession = Depends(get_db_dependency),
    data_service: DataService = Depends(get_data_service),
) -> ProcessingStatusResponse:
    """Get current processing status of file."""
    logger.info(
        "Status check requested",
        extra={
            "task_id": str(task_id),
            "user_id": str(current_user.id),
        },
    )

    try:
        result = await data_service.get_processing_status(
            task_id=task_id,
            user_id=current_user.id,
            db=db,
        )

        logger.info(
            "Status retrieved",
            extra={"task_id": str(task_id), "status": result.status},
        )

        return result

    except ValueError as e:
        logger.warning("Task not found", exc_info=True)
        raise AppException(
            code=ErrorCode.NOT_FOUND,
            detail="Task not found",
        ) from e
    except DashboardPermissionError as e:
        logger.warning("Permission denied for status check", exc_info=True)
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="Access denied",
        ) from e
    except Exception as e:
        logger.error("Error getting status", exc_info=True)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting status",
        ) from e


@router.get(
    "/result/{task_id}",
    response_model=ProcessingResult,
    status_code=status.HTTP_200_OK,
    summary="Get processing result",
    description="Returns processing result of file.",
    responses=auth_protected_responses,
)
async def get_result_endpoint(
    task_id: UUID,
    current_user: EditorUser,
    db: AsyncSession = Depends(get_db_dependency),
    data_service: DataService = Depends(get_data_service),
) -> ProcessingResult:
    """Get processing result of file."""
    logger.info(
        "Result requested",
        extra={
            "task_id": str(task_id),
            "user_id": str(current_user.id),
        },
    )

    try:
        result = await data_service.get_processing_result(
            task_id=task_id,
            user_id=current_user.id,
            db=db,
        )

        logger.info(
            "Result retrieved",
            extra={"task_id": str(task_id), "rows_processed": result.rows_processed},
        )

        return result

    except ValueError as e:
        logger.warning("Error getting result", exc_info=True)
        raise AppException(
            code=ErrorCode.NOT_FOUND,
            detail="Result not found",
        ) from e
    except DashboardPermissionError as e:
        logger.warning("Permission denied for result", exc_info=True)
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="Access denied",
        ) from e
    except Exception as e:
        logger.error("Error getting result", exc_info=True)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting result",
        ) from e