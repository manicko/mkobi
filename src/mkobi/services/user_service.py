"""User management service.

Provides business logic for CRUD operations with users.

All operations are performed through injected UserRepository with validation,
permission checking, and logging.

Implements IUserService interface for dependency injection.
"""

import logging
from uuid import UUID
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.core.security import hash_password
from mkobi.db.models import user as user_model
from mkobi.interfaces import IUserService
from mkobi.interfaces.repository_interfaces import IUserRepository
from mkobi.models.enums import UserRole
from mkobi.models.user import UserRead

logger = logging.getLogger(__name__)


# Allowed roles in the system (defined in UserRole)
def _validate_role(role: UserRole) -> None:
    """Validate that role is allowed.

    Args:
        role: User role to check.

    Raises:
        ValueError: If role is not in the allowed list.
    """
    try:
        # role is already UserRole, so no need to validate, but keep for safety
        UserRole(role)
    except ValueError as err:
        logger.error(
            "Invalid role: '%s'. Allowed roles: %s",
            role,
            sorted([e.value for e in UserRole]),
        )
        raise ValueError(
            f"Invalid role: '{role}'. "
            f"Allowed values: {', '.join(sorted([e.value for e in UserRole]))}"
        ) from err


async def _validate_user_exists(
    user_id: UUID, db: AsyncSession, user_repo: IUserRepository
) -> "user_model.User | None":
    """Check user existence and return its model.

    Args:
        user_id: User identifier.
        db: Async database session.
        user_repo: Injected user repository.

    Returns:
        User model or None if not found.
    """
    user_obj = await user_repo.get(user_id, db)
    if user_obj is None:
        logger.warning("User not found: id=%s", user_id)
    return user_obj


async def _check_admin_deletion_allowed(
    db: AsyncSession, user_repo: IUserRepository
) -> None:
    """Check if admin deletion is allowed.

    Prohibits deleting admins if there are other users in the system.
    This protects against a situation where all admins are deleted and access
    to user management is lost.

    Args:
        db: Async database session.
        user_repo: Injected user repository.

    Raises:
        ValueError: If there are other users besides the deleted one.
    """
    all_users = await user_repo.get_all(db)
    admin_users = [u for u in all_users if u.role == UserRole.ADMIN]
    if len(all_users) > 1 and len(admin_users) <= 1:
        logger.error(
            "Deletion of last admin is prohibited. Total users: %s, admins: %s",
            len(all_users),
            len(admin_users),
        )
        raise ValueError(
            "Cannot delete admin if there are other users in the system. "
            "Assign another admin first."
        )


class UserService(IUserService):
    """User management service.

    Implements IUserService interface for working with users.
    """

    def __init__(self, user_repo: IUserRepository) -> None:
        """Initialize service with injected repository.

        Args:
            user_repo: User repository instance implementing IUserRepository.
        """
        self.user_repo = user_repo
        logger.debug("UserService initialized with injected repository")

    async def get_user_by_id(self, user_id: UUID, db: AsyncSession) -> UserRead | None:
        """Get user by ID.

        Args:
            user_id: User identifier.
            db: Async database session.

        Returns:
            UserRead or None if not found.
        """
        user_obj = await self.user_repo.get(user_id, db)
        if user_obj:
            logger.info("User retrieved: id=%s", user_id)
            return cast(UserRead, UserRead.model_validate(user_obj))
        else:
            logger.warning("User not found: id=%s", user_id)
            return None

    async def get_user_by_email(self, email: str, db: AsyncSession) -> UserRead | None:
        """Get user by email.

        Args:
            email: User email to search.
            db: Async database session.

        Returns:
            UserRead or None if not found.
        """
        user_obj = await self.user_repo.get_by_email(email, db)
        if user_obj:
            logger.info("User found by email: %s", email)
            return cast(UserRead, UserRead.model_validate(user_obj))
        else:
            logger.warning("User not found by email: %s", email)
            return None

    async def create_user(
        self, email: str, password: str, role: UserRole, db: AsyncSession
    ) -> UserRead:
        """Create new user.

        Validates email and role, checks email uniqueness,
        hashes password and saves user to database.

        Args:
            email: User email. Must be valid and unique.
            password: User password. Will be hashed before saving.
            role: User role.
            db: Async database session.

        Returns:
            Created user data. The row is committed before this method returns.

        Raises:
            ValueError: If email is incorrect or email is already taken.
            SQLAlchemyError: On database error.
        """
        logger.info("Starting user creation: email=%s, role=%s", email, role)

        # Check email uniqueness
        existing_user = await self.user_repo.get_by_email(email, db)
        if existing_user is not None:
            logger.warning("Attempt to create user with existing email: %s", email)
            raise ValueError(f"User with email '{email}' already exists")

        # Password hashing
        password_hash = hash_password(password)
        logger.info("Password hashed successfully for user: %s", email)

        # Create user through repository
        try:
            user_obj = await self.user_repo.create(
                db=db,
                email=email,
                password_hash=password_hash,
                role=role,
            )
        except IntegrityError:
            # The pre-check above cannot see a concurrent insert. A unique-index
            # conflict on users.email is only raised once the competing
            # transaction has committed, so the winner is visible on the re-read.
            # Roll back first: the aborted transaction must not poison the session.
            await db.rollback()
            winner = await self.user_repo.get_by_email(email, db)
            if winner is not None:
                logger.warning(
                    "Unique-index conflict on users.email: %s", email
                )
                raise ValueError(f"User with email '{email}' already exists") from None
            # Not the duplicate-email race: surface the driver error unchanged.
            raise

        if user_obj is None:
            raise ValueError("Failed to create user")

        await db.commit()

        logger.info(
            "User created successfully: id=%s, email=%s, role=%s",
            user_obj.id,
            email,
            role,
        )

        # Convert to Pydantic model (without password_hash)
        return cast(UserRead, UserRead.model_validate(user_obj))

    async def update_user_role(
        self, user_id: UUID, role: UserRole, db: AsyncSession
    ) -> UserRead | None:
        """Update user role.

        Checks validity of new role and user existence,
        then updates role in database.

        Args:
            user_id: User identifier.
            role: New user role.
            db: Async database session.

        Returns:
            UserRead of updated user or None if user not found. The new role is
            committed before the method returns on the success path.

        Raises:
            ValueError: If role is invalid.
            SQLAlchemyError: On database error.
        """
        logger.info("Updating user role: id=%s, new_role=%s", user_id, role)

        # Check user existence
        user_obj = await _validate_user_exists(user_id, db, self.user_repo)
        if user_obj is None:
            return None

        # Update role through repository
        updated_user = await self.user_repo.update(id=user_id, db=db, role=role)

        if updated_user:
            await db.commit()
            logger.info(
                "User role updated: id=%s, old_role=%s, new_role=%s",
                user_id,
                user_obj.role,
                role,
            )
            return cast(UserRead, UserRead.model_validate(updated_user))
        else:
            logger.warning("Failed to update user role: id=%s", user_id)
            return None

    async def update_user_active_status(
        self, user_id: UUID, is_active: bool, db: AsyncSession
    ) -> UserRead | None:
        """Update user active status (deactivate/reactivate user).

        Args:
            user_id: User identifier.
            is_active: New active status.
            db: Async database session.

        Returns:
            UserRead of updated user or None if user not found. The new active
            status is committed before the method returns on the success path.

        Raises:
            SQLAlchemyError: On database error.
        """
        logger.info("Updating user active status: id=%s, is_active=%s", user_id, is_active)

        # Check user existence
        user_obj = await _validate_user_exists(user_id, db, self.user_repo)
        if user_obj is None:
            return None

        # Update is_active through repository
        updated_user = await self.user_repo.update(
            id=user_id, db=db, is_active=is_active
        )

        if updated_user:
            await db.commit()
            logger.info(
                "User active status updated: id=%s, is_active=%s",
                user_id,
                is_active,
            )
            return cast(UserRead, UserRead.model_validate(updated_user))
        else:
            logger.warning("Failed to update user active status: id=%s", user_id)
            return None

    async def delete_user(self, user_id: UUID, db: AsyncSession) -> bool:
        """Delete user from system.

        Checks user existence and prohibits deleting
        admins if there are other users in the system.
        On deletion, also cleans up all user access rights.

        Args:
            user_id: User identifier to delete.
            db: Async database session.

        Returns:
            True if deletion successful, False if user not found.

        Raises:
            ValueError: If attempting to delete admin when other users exist.
            SQLAlchemyError: On database error.
        """
        logger.info("Deleting user: id=%s", user_id)

        # Check user existence
        user_obj = await _validate_user_exists(user_id, db, self.user_repo)
        if user_obj is None:
            return False

        # Check admin deletion prohibition
        if user_obj.role == UserRole.ADMIN:
            await _check_admin_deletion_allowed(db, self.user_repo)

        # Delete through repository
        result: bool = await self.user_repo.delete(user_id, db)

        if result:
            await db.commit()
            logger.info(
                "User deleted successfully: id=%s, email=%s",
                user_id,
                user_obj.email,
            )
        else:
            logger.warning("Failed to delete user: id=%s", user_id)

        return result

    async def get_all_users(self, db: AsyncSession) -> list[UserRead]:
        """Get list of all users in the system.

        Args:
            db: Async database session.

        Returns:
            List of all users.

        Raises:
            SQLAlchemyError: On database error.
        """
        logger.info("Getting all users")

        users = await self.user_repo.get_all(db)
        logger.info("Retrieved users: %s", len(users))
        return [UserRead.model_validate(user) for user in users]
