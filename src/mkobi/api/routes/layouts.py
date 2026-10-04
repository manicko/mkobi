"""Routes for managing layouts.

This module provides endpoints for CRUD operations on layouts.
Access is restricted and requires authentication.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    get_db_dependency,
    CurrentUser,
    get_layout_service,
)
from mkobi.api.schemas.responses import (
    auth_protected_responses,
    error_401,
    error_403,
    error_404,
    error_422,
    error_429,
    error_500,
)
from mkobi.core.permissions import check_dashboard_access
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.models.enums import DashboardPermission, ErrorCode, UserRole
from mkobi.models.layout import (
    LayoutRead,
    LayoutUpdate,
    LayoutCreate,
)
from mkobi.services.layout_service import LayoutService
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/layouts", tags=["layouts"], redirect_slashes=False)


@router.post(
    "",
    response_model=LayoutRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create layout",
    description="Creates a new layout. Admin only.",
    responses={
        401: error_401,
        403: error_403,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def create_layout_endpoint(
    layout: LayoutCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    layout_service: LayoutService = Depends(get_layout_service),
) -> LayoutRead:
    """Create a new layout.

    Args:
        layout: Model with layout creation data.
        current_user: Current authenticated user.
        db: Database session.
        layout_service: Injected layout service.

    Returns:
        LayoutRead: Model of the created layout.

    Raises:
        AppException 403: If user is not an admin.
        AppException 422: If data validation failed.
        AppException 500: On database error.
    """
    # Check admin permissions
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Insufficient permissions to create layout: user_id=%s, role=%s",
            current_user.id,
            current_user.role,
        )
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="Only admins can create layouts",
        )

    logger.info(
        "Creating layout: name=%s, user_id=%s",
        layout.name,
        current_user.id,
    )

    try:
        result = await layout_service.create_layout(
            name=layout.name,
            definition=layout.definition,
            db=db,
        )
        return result
    except ValueError as e:
        logger.warning("Validation error creating layout: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "Error creating layout name=%s",
            layout.name,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error creating layout",
        ) from e


@router.get(
    "",
    response_model=list[LayoutRead],
    status_code=status.HTTP_200_OK,
    summary="List layouts",
    description="Returns list of layouts. Non-admin users see layouts from accessible dashboards only.",
    responses=auth_protected_responses,
)
async def get_layouts_endpoint(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    layout_service: LayoutService = Depends(get_layout_service),
) -> list[LayoutRead]:
    """Get list of layouts.

    Non-admin users only see layouts from dashboards they have access to.
    Admins see all layouts.

    Args:
        current_user: Current authenticated user.
        db: Database session.
        layout_service: Injected layout service.

    Returns:
        list[LayoutRead]: List of layout models.

    Raises:
        AppException 500: On database error.
    """
    logger.info("Getting layout list for user_id=%s", current_user.id)

    try:
        if current_user.role == UserRole.ADMIN:
            layouts: list[LayoutRead] = await layout_service.get_all_layouts(db=db)
        else:
            # Non-admin users: get only layouts from accessible dashboards
            access_repo = AccessRepository()
            accessible_dashboards = [
                d.id for d in await access_repo.get_user_dashboards(
                    user_id=current_user.id, db=db
                )
            ]
            layouts = await layout_service.get_layouts_by_dashboard_ids(
                dashboard_ids=accessible_dashboards, db=db
            )
        logger.info("Retrieved layouts: count=%s", len(layouts))
        return layouts
    except Exception as e:
        logger.error("Error getting layout list", exc_info=True)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting layout list",
        ) from e


@router.get(
    "/{layout_id}",
    response_model=LayoutRead,
    status_code=status.HTTP_200_OK,
    summary="Get layout by ID",
    description="Returns layout data by ID. Requires read access to associated dashboard.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def get_layout_endpoint(
    layout_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    layout_service: LayoutService = Depends(get_layout_service),
) -> LayoutRead:
    """Get layout by ID with dashboard access control.

    IDOR protection: verifies user has read access to the dashboard(s)
    associated with the layout. For orphaned layouts (no dashboard association),
    returns 404 to prevent enumeration.

    Args:
        layout_id: Layout ID.
        current_user: Current authenticated user.
        db: Database session.
        layout_service: Injected layout service.

    Returns:
        LayoutRead: Layout model.

    Raises:
        AppException 404: If layout not found or no associated dashboard.
        AppException 403: If user has no read access to the dashboard.
        AppException 500: On database error.
    """
    logger.info("Layout request: layout_id=%s, user_id=%s", layout_id, current_user.id)

    try:
        layout = await layout_service.get_layout(layout_id=layout_id, db=db)
        if layout is None:
            logger.warning("Layout not found: id=%s", layout_id)
            raise AppException(
                code=ErrorCode.LAYOUT_NOT_FOUND,
                detail="Layout not found",
            )

        # Admin bypass: admins can access any layout
        if current_user.role != UserRole.ADMIN:
            # Resolve layout's dashboard association
            dashboard_id = await layout_service.get_dashboard_id_for_layout(layout_id, db)
            if dashboard_id is None:
                # Orphaned layout - return 404 to prevent enumeration
                logger.warning("Orphaned layout (no dashboard) accessed: id=%s", layout_id)
                raise AppException(
                    code=ErrorCode.LAYOUT_NOT_FOUND,
                    detail="Layout not found",
                )

            # IDOR protection: verify user has read access to the dashboard
            has_access = await check_dashboard_access(
                user_id=current_user.id,
                dashboard_id=dashboard_id,
                db=db,
                required_permission=DashboardPermission.VIEW,
            )
            if not has_access:
                logger.warning(
                    "Access denied to layout: user_id=%s, layout_id=%s, dashboard_id=%s",
                    current_user.id,
                    layout_id,
                    dashboard_id,
                )
                raise AppException(
                    code=ErrorCode.PERMISSION_DENIED,
                    detail="You do not have read access to this layout",
                )

        return layout
    except AppException:
        raise
    except Exception as e:
        logger.error("Error getting layout id=%s", layout_id, exc_info=True)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting layout",
        ) from e


@router.put(
    "/{layout_id}",
    response_model=LayoutRead,
    status_code=status.HTTP_200_OK,
    summary="Update layout",
    description="Updates layout data. Admin only.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def update_layout_endpoint(
    layout_id: UUID,
    layout_update: LayoutUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    layout_service: LayoutService = Depends(get_layout_service),
) -> LayoutRead:
    """Update layout.

    Admin-only operation.

    Args:
        layout_id: Layout ID to update.
        layout_update: Model with new data.
        current_user: Current authenticated user.
        db: Database session.
        layout_service: Injected layout service.

    Returns:
        LayoutRead: Model of the updated layout.

    Raises:
        AppException 403: If user is not an admin.
        AppException 404: If layout not found.
        AppException 422: If data validation failed.
        AppException 500: On database error.
    """
    # Check admin permissions
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Insufficient permissions to update layout: user_id=%s, role=%s",
            current_user.id,
            current_user.role,
        )
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="Only admins can update layouts",
        )

    logger.info(
        "Updating layout: layout_id=%s, user_id=%s",
        layout_id,
        current_user.id,
    )

    try:
        updated = await layout_service.update_layout(
            layout_id=layout_id,
            update_data=layout_update,
            db=db,
        )
        if updated is None:
            logger.warning("Layout not found for update: id=%s", layout_id)
            raise AppException(
                code=ErrorCode.LAYOUT_NOT_FOUND,
                detail="Layout not found",
            )
        return updated
    except ValueError as e:
        logger.warning("Validation error updating layout: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except AppException:
        raise
    except Exception as e:
        logger.error("Error updating layout id=%s", layout_id, exc_info=True)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error updating layout",
        ) from e


@router.delete(
    "/{layout_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete layout",
    description="Deletes a layout. Admin only.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def delete_layout_endpoint(
    layout_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    layout_service: LayoutService = Depends(get_layout_service),
) -> None:
    """Delete layout.

    Admin-only operation.

    Args:
        layout_id: Layout ID to delete.
        current_user: Current authenticated user.
        db: Database session.
        layout_service: Injected layout service.

    Raises:
        AppException 403: If user is not an admin.
        AppException 404: If layout not found.
        AppException 500: On database error.
    """
    # Check admin permissions
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Insufficient permissions to delete layout: user_id=%s, role=%s",
            current_user.id,
            current_user.role,
        )
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="Only admins can delete layouts",
        )

    logger.info(
        "Deleting layout: layout_id=%s, user_id=%s",
        layout_id,
        current_user.id,
    )

    try:
        result = await layout_service.delete_layout(layout_id=layout_id, db=db)
        if not result:
            logger.warning("Layout not found for deletion: id=%s", layout_id)
            raise AppException(
                code=ErrorCode.LAYOUT_NOT_FOUND,
                detail="Layout not found",
            )
    except AppException:
        raise
    except Exception as e:
        logger.error("Error deleting layout id=%s", layout_id, exc_info=True)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error deleting layout",
        ) from e