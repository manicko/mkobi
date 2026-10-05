"""Routes for managing processing configuration."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    CurrentUser,
    get_db_dependency,
    get_processing_config_service,
)
from mkobi.api.schemas.responses import (
    error_401,
    error_403,
    error_404,
    error_422,
    error_429,
    error_500,
)
from mkobi.models.processing_configs import (
    ProcessingConfigRead,
    ProcessingConfigUpdate,
)
from mkobi.models.enums import DashboardPermission, ErrorCode
from mkobi.utils.exceptions import AppException
from mkobi.core.permissions import check_dashboard_access
from mkobi.services.processing_config_service import ProcessingConfigService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/processing-configs", tags=["processing_configs"])


@router.get(
    "/{dashboard_id}",
    response_model=ProcessingConfigRead,
    status_code=status.HTTP_200_OK,
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def get_config_endpoint(
    dashboard_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    processing_config_service: ProcessingConfigService = Depends(get_processing_config_service),
) -> ProcessingConfigRead:
    """Get processing config by dashboard ID with access control.

    IDOR protection: verifies user has read access to the dashboard.

    Args:
        dashboard_id: Dashboard ID to get config for.
        current_user: Current authenticated user.
        db: Database session.
        processing_config_service: Injected processing config service.

    Returns:
        ProcessingConfigRead: Processing config model.

    Raises:
        AppException 403: If user has no read access to the dashboard.
        AppException 404: If processing config not found.
        AppException 500: On database error.
    """
    logger.info(
        "Requesting processing config: dashboard_id=%s, user_id=%s",
        dashboard_id,
        current_user.id,
    )

    try:
        # IDOR protection: verify user has view access to the dashboard
        if not await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=dashboard_id,
            db=db,
            required_permission=DashboardPermission.VIEW,
        ):
            logger.warning(
                "Access denied to processing config: user_id=%s, dashboard_id=%s",
                current_user.id,
                dashboard_id,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="You do not have read access to this dashboard",
            )

        config = await processing_config_service.get_by_dashboard_id(dashboard_id, db=db)
        if config is None:
            raise AppException(
                code=ErrorCode.PROCESSING_CONFIG_NOT_FOUND,
                detail="Processing config not found",
            )
        return config
    except AppException:
        raise
    except Exception as e:
        logger.error("Error getting processing config: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting processing config",
        ) from e


@router.put(
    "/{dashboard_id}",
    response_model=ProcessingConfigRead,
    status_code=status.HTTP_200_OK,
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def upsert_config_endpoint(
    dashboard_id: UUID,
    config_update: ProcessingConfigUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    processing_config_service: ProcessingConfigService = Depends(get_processing_config_service),
) -> ProcessingConfigRead:
    """Upsert processing config with dashboard access control.

    IDOR protection: verifies user has edit access to the dashboard.

    Args:
        dashboard_id: Dashboard ID to upsert config for.
        config_update: Model with processing config data.
        current_user: Current authenticated user.
        db: Database session.
        processing_config_service: Injected processing config service.

    Returns:
        ProcessingConfigRead: Processing config model.

    Raises:
        AppException 403: If user has no edit access to the dashboard.
        AppException 422: If data validation failed.
        AppException 500: On database error.
    """
    logger.info(
        "Upserting processing config: dashboard_id=%s, user_id=%s",
        dashboard_id,
        current_user.id,
    )

    try:
        # IDOR protection: verify user has edit access to the dashboard
        if not await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=dashboard_id,
            db=db,
            required_permission=DashboardPermission.EDIT,
        ):
            logger.warning(
                "Edit access denied to processing config: user_id=%s, dashboard_id=%s",
                current_user.id,
                dashboard_id,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="You do not have edit access to this dashboard",
            )

        if config_update.settings is None:
            raise AppException(
                code=ErrorCode.MISSING_REQUIRED_FIELD,
                detail="Settings cannot be empty",
            )
        config = await processing_config_service.upsert(
            dashboard_id=dashboard_id,
            db=db,
            settings=config_update.settings,
            metric_agg=config_update.metric_agg,
        )
        return config
    except ValueError as e:
        logger.warning("Invalid processing config update: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail="Invalid processing config",
        ) from e
    except AppException:
        raise
    except Exception as e:
        logger.error("Error updating processing config: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error updating processing config",
        ) from e


@router.delete(
    "/{dashboard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def delete_config_endpoint(
    dashboard_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    processing_config_service: ProcessingConfigService = Depends(get_processing_config_service),
) -> None:
    """Delete processing config with dashboard access control.

    IDOR protection: verifies user has edit access to the dashboard.

    Args:
        dashboard_id: Dashboard ID to delete config for.
        current_user: Current authenticated user.
        db: Database session.
        processing_config_service: Injected processing config service.

    Raises:
        AppException 403: If user has no edit access to the dashboard.
        AppException 404: If processing config not found.
        AppException 500: On database error.
    """
    logger.info(
        "Deleting processing config: dashboard_id=%s, user_id=%s",
        dashboard_id,
        current_user.id,
    )

    try:
        # IDOR protection: verify user has edit access to the dashboard
        if not await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=dashboard_id,
            db=db,
            required_permission=DashboardPermission.EDIT,
        ):
            logger.warning(
                "Edit access denied to delete processing config: user_id=%s, dashboard_id=%s",
                current_user.id,
                dashboard_id,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="You do not have edit access to this dashboard",
            )

        await processing_config_service.delete(dashboard_id, db=db)
    except ValueError as e:
        logger.warning("Processing config not found on delete: %s", e)
        raise AppException(
            code=ErrorCode.PROCESSING_CONFIG_NOT_FOUND,
            detail="Processing config not found",
        ) from e
    except AppException:
        raise
    except Exception as e:
        logger.error("Error deleting processing config: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error deleting processing config",
        ) from e