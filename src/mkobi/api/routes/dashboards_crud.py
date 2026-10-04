"""Dashboard CRUD routes.

This module provides endpoints for create, read, update, delete operations on dashboards.
Access to most operations is restricted and requires authentication.
Create, update and delete operations are available only to owners.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    AdminUser,
    CurrentUser,
    get_db_dependency,
    get_dashboard_service,
    check_dashboard_access,
)
from mkobi.api.schemas.responses import (
    admin_responses,
    auth_protected_responses,
    error_401,
    error_403,
    error_404,
    error_422,
    error_429,
    error_500,
)
from mkobi.models.dashboard import (
    DashboardAdmin,
    DashboardRead,
    DashboardCreate,
    DashboardUpdate,
    DashboardSummary,
)
from mkobi.models.enums import ErrorCode, UserRole, DashboardPermission
from mkobi.services.dashboard_service import DashboardService
from mkobi.utils.exceptions import AppException, PermissionDeniedException

logger = logging.getLogger(__name__)

# No prefix - this router is mounted under /dashboards
router = APIRouter(tags=["dashboards"])


@router.get(
    "/",
    response_model=list[DashboardAdmin],
    status_code=status.HTTP_200_OK,
    summary="List all dashboards (admin)",
    description="Returns list of all dashboards. Available only to admins.",
    responses=admin_responses,
)
async def get_dashboards_admin_endpoint(
    admin_user: AdminUser,
    db: AsyncSession = Depends(get_db_dependency),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of records (max. 1000)",
    ),
) -> list[DashboardAdmin]:
    """Get all dashboards for admin panel.

    Args:
        admin_user: Authenticated admin user.
        db: Database session.
        dashboard_service: Injected dashboard service.
        skip: Number of records to skip (offset).
        limit: Maximum number of records.

    Returns:
        list[DashboardAdmin]: List of dashboards without full config.
    """
    logger.info("Admin: getting all dashboards")
    try:
        dashboards = await dashboard_service.get_all_dashboards(
            db=db, limit=limit, skip=skip
        )
        return [
            DashboardAdmin(
                id=d.id,
                name=d.name,
                description=d.description,
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
            for d in dashboards
        ]
    except Exception as e:
        logger.error("Error getting all dashboards: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting dashboards",
        ) from e


@router.post(
    "/",
    response_model=DashboardRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create dashboard",
    description="Creates new dashboard. Available only to admins.",
    responses=admin_responses,
)
async def create_dashboard_endpoint(
    dashboard_data: DashboardCreate,
    admin_user: AdminUser,
    db: AsyncSession = Depends(get_db_dependency),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> DashboardRead:
    """Create new dashboard.

    Current authenticated user automatically becomes
    the owner (admin) of the created dashboard.

    Args:
        dashboard: Dashboard creation data model.
        admin_user: Current authenticated admin user.
        db: Database session.
        dashboard_service: Injected dashboard service.

    Returns:
        DashboardRead: Model of the created dashboard.

    Raises:
        AppException 422: If data validation failed.
        AppException 500: On database error.
    """
    logger.info(
        "Creating dashboard: name=%s, owner_id=%s",
        dashboard_data.name,
        admin_user.id,
    )

    try:
        result = await dashboard_service.create_dashboard(
            name=dashboard_data.name,
            config=dashboard_data.config.model_dump(),
            owner_id=admin_user.id,
            description=dashboard_data.description,
            layout_id=dashboard_data.layout_id,
            db=db,
        )
        await db.commit()

        logger.info(
            "Dashboard created successfully: id=%s, name=%s",
            result.id,
            result.name,
        )
        return result
    except ValueError as e:
        logger.warning("Validation error creating dashboard: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "Error creating dashboard name=%s",
            dashboard_data.name,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error creating dashboard",
        ) from e


@router.get(
    "/my",
    response_model=list[DashboardSummary],
    status_code=status.HTTP_200_OK,
    summary="Get user dashboards",
    description="Returns list of dashboards available to current user.",
    responses=auth_protected_responses,
)
async def get_my_dashboards_endpoint(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of records (max. 1000)",
    ),
) -> list[DashboardSummary]:
    """Get user dashboards.

    Args:
        current_user: Current authenticated user.
        db: Database session.
        dashboard_service: Injected dashboard service.
        skip: Number of records to skip (offset).
        limit: Maximum number of records.

    Returns:
        list[DashboardSummary]: List of dashboards available to user with permission.

    Raises:
        AppException 500: On database error.
    """
    logger.info("Getting user dashboards: user_id=%s", current_user.id)

    try:
        dashboards = await dashboard_service.get_user_dashboards(
            user_id=current_user.id, user_role=current_user.role, db=db,
            limit=limit, skip=skip,
        )
        logger.info(
            "Retrieved dashboards for user: user_id=%s, count=%s",
            current_user.id,
            len(dashboards),
        )
        return dashboards
    except Exception as e:
        logger.error(
            "Error getting user dashboards user_id=%s",
            current_user.id,
            exc_info=True,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting user dashboards",
        ) from e


@router.get(
    "/{dashboard_id}",
    response_model=DashboardRead,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard by ID",
    description="Returns dashboard data by its ID with access check.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def get_dashboard_endpoint(
    dashboard_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> DashboardRead:
    """Get dashboard by ID with access check.

    Args:
        dashboard_id: Dashboard ID.
        current_user: Current authenticated user.
        db: Database session.
        dashboard_service: Injected dashboard service.

    Returns:
        DashboardRead: Dashboard model.

    Raises:
        AppException 403: If user has no access.
        AppException 404: If dashboard not found.
        AppException 500: On database error.
    """
    logger.info(
        "Dashboard request: dashboard_id=%s, user_id=%s",
        dashboard_id,
        current_user.id,
    )

    try:
        dashboard = await dashboard_service.get_dashboard(
            dashboard_id, user_id=current_user.id, user_role=current_user.role, db=db
        )
        if dashboard is None:
            logger.warning(
                "Dashboard not found: dashboard_id=%s",
                dashboard_id,
            )
            raise AppException(
                code=ErrorCode.DASHBOARD_NOT_FOUND,
                detail="Dashboard not found",
                details={"dashboard_id": str(dashboard_id)},
            )

        logger.info(
            "Dashboard retrieved: id=%s, name=%s",
            dashboard.id,
            dashboard.name,
        )
        return dashboard
    except PermissionDeniedException:
        raise AppException(
            code=ErrorCode.ACCESS_DENIED,
            detail="Access denied",
        ) from None
    except AppException:
        raise
    except Exception as e:
        logger.error(
            "Error getting dashboard dashboard_id=%s: %s",
            dashboard_id,
            e,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting dashboard",
        ) from e


@router.put(
    "/{dashboard_id}",
    response_model=DashboardRead,
    status_code=status.HTTP_200_OK,
    summary="Update dashboard",
    description="Updates dashboard configuration. Available to admins or editors with edit access.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def update_dashboard_endpoint(
    dashboard_id: UUID,
    dashboard_update: DashboardUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> DashboardRead:
    """Update dashboard.

    Available to dashboard owners (users with admin/edit permission) or system admins.

    Args:
        dashboard_id: Dashboard ID to update.
        dashboard_update: Model with new data.
        current_user: Current authenticated user.
        db: Database session.
        dashboard_service: Injected dashboard service.

    Returns:
        DashboardRead: Updated dashboard model.

    Raises:
        AppException 403: If user has no update rights.
        AppException 404: If dashboard not found.
        AppException 422: If data validation failed.
        AppException 500: On database error.
    """
    logger.info(
        "Updating dashboard: dashboard_id=%s, user_id=%s",
        dashboard_id,
        current_user.id,
    )

    # Check resource-level access: admin role or edit permission on dashboard
    # Admin users bypass resource-level checks
    has_edit_access = False
    if current_user.role != UserRole.ADMIN:
        has_edit_access = await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=dashboard_id,
            db=db,
            required_permission=DashboardPermission.EDIT,
        )
        if not has_edit_access:
            logger.warning(
                "Access denied for update: user_id=%s, dashboard_id=%s",
                current_user.id,
                dashboard_id,
            )
            raise AppException(
                code=ErrorCode.PERMISSION_DENIED,
                detail="You don't have access to this dashboard",
            )

    try:
        # Determine user's permission for response
        user_permission = DashboardPermission.EDIT if current_user.role == UserRole.ADMIN or has_edit_access else DashboardPermission.VIEW

        updated = await dashboard_service.update_dashboard(
            dashboard_id=dashboard_id,
            update_data=dashboard_update.model_dump(exclude_unset=True),
            db=db,
            permission=user_permission,
        )
        if updated is None:
            logger.warning("Dashboard not found for update: id=%s", dashboard_id)
            raise AppException(
                code=ErrorCode.DASHBOARD_NOT_FOUND,
                detail="Dashboard not found",
                details={"dashboard_id": str(dashboard_id)},
            )
        return updated
    except ValueError as e:
        logger.warning("Validation error updating dashboard: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except AppException:
        raise
    except Exception as e:
        logger.error("Error updating dashboard id=%s: %s", dashboard_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Dashboard update error",
        ) from e


@router.delete(
    "/{dashboard_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete dashboard",
    description="Deletes dashboard. Available to admins or users with admin access to the dashboard.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def delete_dashboard_endpoint(
    dashboard_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_dependency),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> None:
    """Delete dashboard.

    Available to dashboard admins (users with admin permission on dashboard) or system admins.

    Args:
        dashboard_id: Dashboard ID to delete.
        current_user: Current authenticated user.
        db: Database session.
        dashboard_service: Injected dashboard service.

    Raises:
        AppException 403: If user has no deletion rights.
        AppException 404: If dashboard not found.
        AppException 500: On database error.
    """
    logger.info(
        "Deleting dashboard: dashboard_id=%s, user_id=%s",
        dashboard_id,
        current_user.id,
    )

    # Check resource-level access: system admin role or admin permission on dashboard
    # System admins bypass resource-level checks
    if current_user.role != UserRole.ADMIN:
        has_admin_access = await check_dashboard_access(
            user_id=current_user.id,
            dashboard_id=dashboard_id,
            db=db,
            required_permission=DashboardPermission.ADMIN,
        )
        if not has_admin_access:
            logger.warning(
                "Access denied for delete: user_id=%s, dashboard_id=%s",
                current_user.id,
                dashboard_id,
            )
            raise AppException(
                code=ErrorCode.ACCESS_DENIED,
                detail="Access denied",
            )

    try:
        result = await dashboard_service.delete_dashboard(
            dashboard_id=dashboard_id, db=db
        )
        if not result:
            logger.warning("Dashboard not found for deletion: id=%s", dashboard_id)
            raise AppException(
                code=ErrorCode.DASHBOARD_NOT_FOUND,
                detail="Dashboard not found",
                details={"dashboard_id": str(dashboard_id)},
            )
    except AppException:
        raise
    except Exception as e:
        logger.error("Error deleting dashboard id=%s: %s", dashboard_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Dashboard deletion error",
        ) from e