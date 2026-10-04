"""User management routes.

This module provides endpoints for CRUD operations with users.
Access to most operations is restricted and requires authentication.
Delete and list all users operations are admin-only.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    AdminUser,
    CurrentUser,
    get_db_dependency,
    get_user_service,
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
from mkobi.models.enums import ErrorCode, UserRole
from mkobi.models.user import UserCreateRequest, UserRead, UserUpdateRequest
from mkobi.services.user_service import UserService
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "/",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
    description="Creates a new user. Admin only.",
    responses=admin_responses,
)
async def create_user_endpoint(
    user_data: UserCreateRequest,
    admin_user: AdminUser,
    user_service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> UserRead:
    """Create a new user in the system.

    Args:
        user_data: User creation data with email, password, and role.
        _: User with admin role (verified via dependency).
        user_service: User service.
        db: Database session.

    Returns:
        UserRead: Model of the created user without password.

    Raises:
        AppException 422: If data validation failed, including a duplicate
            email: the service raises ValueError for both the pre-check and
            the unique-index race, and this route maps ValueError to
            VALIDATION_ERROR. This endpoint returns no 409.
        AppException 500: On database error.
    """
    logger.info("Creating user: email=%s, role=%s", user_data.email, user_data.role)

    try:
        user = await user_service.create_user(
            email=user_data.email, password=user_data.password, role=user_data.role, db=db
        )
        return user
    except ValueError as e:
        logger.warning("Validation error creating user: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error("Error creating user %s: %s", user_data.email, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error creating user",
        ) from e


@router.get(
    "/",
    response_model=list[UserRead],
    status_code=status.HTTP_200_OK,
    summary="List all users",
    description="Returns list of all users. Admin only.",
    responses=admin_responses,
)
async def get_users_endpoint(
    admin_user: AdminUser,
    user_service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> list[UserRead]:
    """Get list of all users in the system.

    Args:
        _: User with admin role (verified via dependency).
        user_service: User service.
        db: Database session.

    Returns:
        list[UserRead]: List of all users.

    Raises:
        AppException 500: On database error.
    """
    logger.info("Getting all users")

    try:
        users_data = await user_service.get_all_users(db=db)
        return users_data  # Already returns list[UserRead]
    except Exception as e:
        logger.error("Error getting user list: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting user list",
        ) from e


@router.get(
    "/{user_id}",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get user by ID",
    description="Returns user data by ID. Users can get their own data, admins can get any.",
    responses={
        401: error_401,
        403: error_403,
        404: error_404,
        422: error_422,
        429: error_429,
        500: error_500,
    },
)
async def get_user_endpoint(
    user_id: UUID,
    current_user: CurrentUser,
    user_service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> UserRead:
    """Get user by ID.

    Users can only get their own data.
    Admins can get any user's data.

    Args:
        user_id: User ID.
        current_user: Current authenticated user.
        user_service: User service.
        db: Database session.

    Returns:
        UserRead: User model.

    Raises:
        AppException 403: If user tries to get another user's data.
        AppException 404: If user not found.
        AppException 500: On database error.
    """
    logger.info("Getting user: id=%s, requester_id=%s", user_id, current_user.id)

    # Check permissions: user can only get their own data, admin can get any
    if current_user.role != UserRole.ADMIN and str(current_user.id) != str(user_id):
        logger.warning(
            "Attempt to get another user's data: requester_id=%s, target_id=%s",
            current_user.id,
            user_id,
        )
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="Insufficient permissions to access this user's data",
        )

    try:
        user_data = await user_service.get_user_by_id(user_id=user_id, db=db)
        if user_data is None:
            logger.warning("User not found: id=%s", user_id)
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                details={"user_id": str(user_id)},
            )
        return user_data  # Already returns UserRead | None
    except AppException:
        raise
    except Exception as e:
        logger.error("Error getting user id=%s: %s", user_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting user",
        ) from e


@router.put(
    "/{user_id}",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update user role",
    description="Updates user role. Admin only.",
    responses=admin_responses,
    deprecated=True,
)
async def update_user_endpoint(
    user_id: UUID,
    user_data: UserUpdateRequest,
    admin_user: AdminUser,
    user_service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> UserRead:
    """Update user role.

    Deprecated: Use PATCH /admin/users/{user_id}/role instead.

    Args:
        user_id: User ID to update.
        user_data: Request body containing the new role.
            Allowed values: 'admin', 'editor', 'viewer'.
        _: User with admin role (verified via dependency).
        user_service: User service.
        db: Database session.

    Returns:
        UserRead: Model of the updated user.

    Raises:
        AppException 404: If user not found.
        AppException 422: If role is invalid.
        AppException 500: On database error.
    """
    logger.info("Updating user: id=%s, new_role=%s", user_id, user_data.role)

    try:
        updated = await user_service.update_user_role(
            user_id=user_id, role=user_data.role, db=db
        )
        if updated is None:
            logger.warning("User not found for update: id=%s", user_id)
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                details={"user_id": str(user_id)},
            )
        return updated
    except ValueError as e:
        logger.warning("Validation error updating user: %s", e)
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except AppException:
        raise
    except Exception as e:
        logger.error("Error updating user id=%s: %s", user_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error updating user",
        ) from e


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete own account",
    description="Deletes the current user's account.",
    responses=auth_protected_responses,
)
async def delete_me_endpoint(
    current_user: CurrentUser,
    user_service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> None:
    """Delete own account.

    Args:
        current_user: Current authenticated user.
        user_service: User service.
        db: Database session.

    Returns:
        None: Returns empty response with 204 code.

    Raises:
        AppException 403: If trying to delete admin account.
        AppException 404: If user not found.
        AppException 500: On database error.
    """
    logger.info("Deleting own account: id=%s", current_user.id)

    try:
        result = await user_service.delete_user(user_id=current_user.id, db=db)
        if not result:
            logger.warning("User not found for deletion: id=%s", current_user.id)
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                details={"user_id": str(current_user.id)},
            )
    except ValueError as e:
        logger.warning("Error deleting account: %s", e)
        raise AppException(
            code=ErrorCode.ACCESS_DENIED,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error("Error deleting account id=%s: %s", current_user.id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error deleting account",
        ) from e


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Deletes a user from the system. Admin only.",
    responses=admin_responses,
)
async def delete_user_endpoint(
    user_id: UUID,
    admin_user: AdminUser,
    user_service: UserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> None:
    """Delete user from the system.

    Args:
        user_id: User ID to delete.
        _: User with admin role (verified via dependency).
        user_service: User service.
        db: Database session.

    Returns:
        None: Returns empty response with 204 code.

    Raises:
        AppException 404: If user not found.
        AppException 403: If trying to delete admin with other users present.
        AppException 500: On database error.
    """
    logger.info("Deleting user: id=%s", user_id)

    try:
        result = await user_service.delete_user(user_id=user_id, db=db)
        if not result:
            logger.warning("User not found for deletion: id=%s", user_id)
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                details={"user_id": str(user_id)},
            )
    except ValueError as e:
        logger.warning("Error deleting user: %s", e)
        raise AppException(
            code=ErrorCode.ACCESS_DENIED,
            detail=str(e),
        ) from e
    except AppException:
        raise
    except Exception as e:
        logger.error("Error deleting user id=%s: %s", user_id, e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error deleting user",
        ) from e