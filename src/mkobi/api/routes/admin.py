"""Admin routes for user management and registration requests."""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    AdminUser,
    get_auth_service,
    get_db_dependency,
    get_registration_request_repository,
    get_user_service,
    get_redis_client_dependency,
    get_temp_password_store,
)
from mkobi.api.schemas.responses import admin_responses
from mkobi.interfaces import IUserService
from mkobi.models.enums import ErrorCode, RegistrationStatus
from mkobi.utils.exceptions import AppException
from mkobi.models.user import UserRead, UserUpdateRequest, UserUpdateActiveRequest
from mkobi.models.auth import RegistrationRequestItem, SuccessResponse
from mkobi.services.auth_service import AuthService
from mkobi.core.security import revoke_all_user_tokens
from mkobi.core.temp_password_store import TempPasswordStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"], redirect_slashes=False)


# --- User Management ---


@router.get(
    "/users",
    response_model=list[UserRead],
    status_code=status.HTTP_200_OK,
    summary="List all users (admin)",
    description="Returns list of all users. Admin only.",
    responses=admin_responses,
)
async def get_users_admin_endpoint(
    admin_user: AdminUser,
    user_service: IUserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> list[UserRead]:
    """Get all users (admin endpoint)."""
    logger.info("Admin: getting all users")
    try:
        return await user_service.get_all_users(db=db)
    except Exception as e:
        logger.error("Error getting users: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting users",
        ) from e


@router.patch(
    "/users/{user_id}/role",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update user role (admin)",
    description="Updates user role. Admin only.",
    responses=admin_responses,
)
async def update_user_role_admin_endpoint(
    user_id: UUID,
    user_data: UserUpdateRequest,
    admin_user: AdminUser,
    user_service: IUserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> UserRead:
    """Update user role (admin endpoint)."""
    logger.info("Admin: updating user role: id=%s, new_role=%s", user_id, user_data.role)
    try:
        updated = await user_service.update_user_role(user_id=user_id, role=user_data.role, db=db)
        if updated is None:
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                details={"user_id": str(user_id)},
            )
        return updated
    except ValueError as e:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error("Error updating user role: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error updating user role",
        ) from e


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user (admin)",
    description="Deletes a user. Admin only.",
    responses=admin_responses,
)
async def delete_user_admin_endpoint(
    user_id: UUID,
    admin_user: AdminUser,
    user_service: Any = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> None:
    """Delete user (admin endpoint)."""
    logger.info("Admin: deleting user: id=%s", user_id)
    try:
        result = await user_service.delete_user(user_id=user_id, db=db)
        if not result:
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                details={"user_id": str(user_id)},
            )
    except ValueError as e:
        raise AppException(
            code=ErrorCode.ACCESS_DENIED,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error("Error deleting user: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error deleting user",
        ) from e


@router.patch(
    "/users/{user_id}/active",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update user active status (admin)",
    description="Deactivates or reactivates a user. Revokes all tokens on deactivation. Admin only.",
    responses=admin_responses,
)
async def update_user_active_admin_endpoint(
    user_id: UUID,
    user_data: UserUpdateActiveRequest,
    admin_user: AdminUser,
    user_service: IUserService = Depends(get_user_service),
    db: AsyncSession = Depends(get_db_dependency),
    redis_client: Any = Depends(get_redis_client_dependency),
) -> UserRead:
    """Update user active status (admin endpoint).

    Two effects are paired on deactivation: the ``is_active`` write and the
    Redis user-level revocation marker. They cannot be made transactional
    together, so the ordering is deliberate. ``update_user_active_status``
    commits before this endpoint revokes, and ``is_active`` is the authority
    for protected access — ``api/deps.py::get_current_user_dependency`` rejects a
    deactivated user independently of Redis. The Redis user-level marker is the
    authority for ``POST /auth/refresh`` and login, which do not re-read the row.
    A Redis fault therefore leaves a committed deactivation with a failed
    revocation: that is reported as 500 and the endpoint is idempotent, so a
    retry completes the revocation.
    """
    from mkobi.config import get_config

    logger.info(
        "Admin: updating user active status: id=%s, is_active=%s",
        user_id,
        user_data.is_active,
    )
    try:
        # First update the user status in database. The service commits on success,
        # so once this returns the new is_active is durable.
        updated = await user_service.update_user_active_status(
            user_id=user_id, is_active=user_data.is_active, db=db
        )
        if updated is None:
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                details={"user_id": str(user_id)},
            )

        # On deactivation, revoke all user tokens via Redis. Guarded separately:
        # a Redis fault must be reported as a committed deactivation with a failed
        # revocation, not conflated with a database error.
        if not user_data.is_active:
            settings = get_config()
            try:
                await revoke_all_user_tokens(
                    redis_client=redis_client,
                    user_id=user_id,
                    access_ttl=settings.jwt.access_token_expire_minutes * 60,
                    refresh_ttl=settings.jwt.refresh_token_expire_minutes * 60,
                )
            except Exception as revoke_error:
                logger.error(
                    "Deactivation committed but token revocation failed: id=%s: %s",
                    user_id,
                    revoke_error,
                )
                raise AppException(
                    code=ErrorCode.INTERNAL_ERROR,
                    detail=(
                        "User was deactivated successfully, but revoking the "
                        "user's tokens failed"
                    ),
                ) from revoke_error
            logger.info("All tokens revoked for deactivated user: id=%s", user_id)

        return updated
    except AppException:
        raise
    except Exception as e:
        # This rollback can only undo work done before the service's commit. Once
        # update_user_active_status has committed, the deactivation stands and this
        # rollback cannot take it back; it is still correct for a failure inside the
        # service before that commit, where the session may need one.
        await db.rollback()
        logger.error("Error updating user active status: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error updating user active status",
        ) from e


@router.post(
    "/users/{user_id}/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset user password (admin)",
    description="Generates a temporary password, sets force_password_change flag.",
    responses=admin_responses,
)
async def reset_user_password_admin_endpoint(
    user_id: UUID,
    admin_user: AdminUser,
    db: AsyncSession = Depends(get_db_dependency),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    """Reset user password and return temporary password."""
    logger.info(
        "Admin: resetting password for user: id=%s, admin=%s",
        user_id, admin_user.email,
    )
    try:
        result = await auth_service.reset_password_admin(
            user_id=user_id,
            admin_user_id=admin_user.id,
            db=db,
        )
        if result is None:
            raise AppException(
                code=ErrorCode.USER_NOT_FOUND,
                detail="User not found",
                details={"user_id": str(user_id)},
            )
        return result
    except ValueError as exc:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(exc),
        ) from exc
    except AppException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Error resetting user password: %s", exc)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error resetting user password",
        ) from exc


# --- Registration Requests ---


@router.get(
    "/registration-requests",
    response_model=list[RegistrationRequestItem],
    status_code=status.HTTP_200_OK,
    summary="List registration requests (admin)",
    description="Returns list of all registration requests. Admin only.",
    responses=admin_responses,
)
async def get_registration_requests_admin_endpoint(
    admin_user: AdminUser,
    db: AsyncSession = Depends(get_db_dependency),
    repo: Any = Depends(get_registration_request_repository),
) -> list[RegistrationRequestItem]:
    """Get all registration requests (admin endpoint)."""
    logger.info("Admin: getting registration requests")
    try:
        requests = await repo.get_all(db)
        return [RegistrationRequestItem.model_validate(req) for req in requests]
    except Exception as e:
        logger.error("Error getting registration requests: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting registration requests",
        ) from e


@router.post(
    "/registration-requests/{request_id}/approve",
    status_code=status.HTTP_200_OK,
    summary="Approve registration request (admin)",
    description="Approves a registration request and creates user. Admin only.",
    responses=admin_responses,
)
async def approve_registration_request_admin_endpoint(
    request_id: UUID,
    admin_user: AdminUser,
    db: AsyncSession = Depends(get_db_dependency),
    auth_service: AuthService = Depends(get_auth_service),
    repo: Any = Depends(get_registration_request_repository),
) -> dict[str, Any]:
    """Approve registration request (admin endpoint)."""
    logger.info("Admin: approving registration request: id=%s", request_id)
    try:
        # Existence check distinguishes a missing request from a non-pending one,
        # preserving the endpoint's NOT_FOUND vs DUPLICATE_RESOURCE mapping.
        req = await repo.get_by_id(request_id, db)
        if not req:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                detail="Registration request not found",
                details={"request_id": str(request_id)},
            )

        if req.status != RegistrationStatus.PENDING:
            raise AppException(
                code=ErrorCode.DUPLICATE_RESOURCE,
                detail=f"Request already {req.status}",
            )

        # The service owns the create -> flag -> status -> commit -> Redis write sequence.
        result = await auth_service.approve_registration_request(
            request_id=request_id,
            admin_user_id=admin_user.id,
            db=db,
        )
        if result is None:
            raise AppException(
                code=ErrorCode.DUPLICATE_RESOURCE,
                detail=f"Request already {req.status}",
            )

        return result
    except AppException:
        raise
    except Exception as e:
        logger.error("Error approving registration request: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error approving registration request",
        ) from e


@router.post(
    "/registration-requests/{request_id}/reject",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject registration request (admin)",
    description="Rejects a registration request. Admin only.",
    responses=admin_responses,
)
async def reject_registration_request_admin_endpoint(
    request_id: UUID,
    admin_user: AdminUser,
    db: AsyncSession = Depends(get_db_dependency),
    repo: Any = Depends(get_registration_request_repository),
) -> SuccessResponse:
    """Reject registration request (admin endpoint)."""
    logger.info("Admin: rejecting registration request: id=%s", request_id)
    try:
        req = await repo.get_by_id(request_id, db)
        if not req:
            raise AppException(
                code=ErrorCode.NOT_FOUND,
                detail="Registration request not found",
                details={"request_id": str(request_id)},
            )

        if req.status != RegistrationStatus.PENDING:
            raise AppException(
                code=ErrorCode.DUPLICATE_RESOURCE,
                detail=f"Request already {req.status}",
            )

        # Update request status
        await repo.update_status(
            request_id=request_id,
            status=RegistrationStatus.REJECTED,
            db=db,
            reviewed_by=admin_user.id,
        )
        await db.commit()

        return SuccessResponse(message="Registration request rejected")
    except AppException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Error rejecting registration request: %s", e)
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error rejecting registration request",
        ) from e


# --- Temp Password Retrieval ---


@router.get(
    "/temp-passwords/{retrieval_token}",
    status_code=status.HTTP_200_OK,
    summary="Retrieve temporary password (admin)",
    description="Returns a one-time temporary password. Admin only. Password is deleted after retrieval.",
    responses=admin_responses,
)
async def retrieve_temp_password_admin_endpoint(
    retrieval_token: str,
    admin_user: AdminUser,
    temp_password_store: TempPasswordStore = Depends(get_temp_password_store),
) -> dict[str, str]:
    """Retrieve a temporary password by its retrieval token (one-time, admin only)."""
    logger.info("Admin: retrieving temp password: token=%s...", retrieval_token[:8])
    password = await temp_password_store.retrieve(retrieval_token)
    if password is None:
        raise AppException(
            code=ErrorCode.NOT_FOUND,
            detail="Temporary password not found or already retrieved",
        )
    return {"temp_password": password}
