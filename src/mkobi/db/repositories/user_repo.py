"""Repository for user operations.

Provides CRUD methods for User model.
All methods use contextual session management and handle errors.
"""

import logging
from uuid import UUID
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models import user as user_model
from mkobi.interfaces.repository_interfaces import IUserRepository
from mkobi.models.user import UserRead

logger = logging.getLogger(__name__)


class UserRepository(IUserRepository):
    """Repository for user operations.

    Provides methods for creating, reading, updating and deleting
    users in the database. All operations are performed within a
    separate database session with automatic transaction management.
    Implements IUserRepository interface.
    """
    async def get(self, id: UUID, db: AsyncSession) -> UserRead | None:
        """Get user by ID.

        Args:
            id: User identifier (UUID).
            db: Async database session.

        Returns:
            UserRead model or None if not found.
        """
        try:
            result = await db.execute(
                select(user_model.User).where(user_model.User.id == id)
            )
            user = result.scalar_one_or_none()
            if user:
                logger.info("User retrieved: id=%s", id)
                return cast(UserRead, UserRead.model_validate(user))
            logger.warning("User not found: id=%s", id)
            return None
        except SQLAlchemyError as e:
            logger.error("Error getting user id=%s: %s", id, e)
            raise
    async def get_by_email(self, email: str, db: AsyncSession) -> UserRead | None:
        """Get user by email.

        Args:
            email: User email.
            db: Async database session.

        Returns:
            UserRead model or None if not found.
        """
        try:
            result = await db.execute(
                select(user_model.User).where(user_model.User.email == email)
            )
            user = result.scalar_one_or_none()
            if user:
                logger.info("User retrieved by email: %s", email)
                return cast(UserRead, UserRead.model_validate(user))
            logger.warning("User not found by email: %s", email)
            return None
        except SQLAlchemyError as e:
            logger.error("Error getting user email=%s: %s", email, e)
            raise
    async def get_by_email_with_hash(self, email: str, db: AsyncSession) -> user_model.User | None:
        """Get user by email with password hash for authentication.

        Args:
            email: User email.
            db: Async database session.

        Returns:
            User DB model with password_hash or None if not found.
        """
        try:
            result = await db.execute(
                select(user_model.User).where(user_model.User.email == email)
            )
            user: user_model.User | None = cast(user_model.User | None, result.scalar_one_or_none())
            if user:
                logger.info("User retrieved by email (with hash): %s", email)
                return user
            logger.warning("User not found by email: %s", email)
            return None
        except SQLAlchemyError as e:
            logger.error("Error getting user email=%s: %s", email, e)
            raise

    async def get_with_hash(self, id: UUID, db: AsyncSession) -> user_model.User | None:
        """Get user by ID with password hash for password change.

        Args:
            id: User identifier (UUID).
            db: Async database session.

        Returns:
            User DB model with password_hash or None if not found.
        """
        try:
            result = await db.execute(
                select(user_model.User).where(user_model.User.id == id)
            )
            user: user_model.User | None = cast(user_model.User | None, result.scalar_one_or_none())
            if user:
                logger.info("User retrieved by id (with hash): %s", id)
                return user
            logger.warning("User not found by id: %s", id)
            return None
        except SQLAlchemyError as e:
            logger.error("Error getting user id=%s: %s", id, e)
            raise

    async def get_all(
        self, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[UserRead]:
        """Get users, optionally bounded.

        Args:
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of UserRead models.
        """
        try:
            query = select(user_model.User)
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            users = list(result.scalars().all())
            logger.info("Users list retrieved, count: %s", len(users))
            return [UserRead.model_validate(u) for u in users]
        except SQLAlchemyError as e:
            logger.error("Error getting users list: %s", e)
            raise
    async def create(
        self, db: AsyncSession, **kwargs: Any
    ) -> UserRead | None:
        """Create new user.

        Args:
            db: Async database session.
            **kwargs: User parameters (email, password_hash, role).

        Returns:
            Created UserRead model with ID or None on error.
        """
        try:
            user_obj = user_model.User(**kwargs)
            db.add(user_obj)
            await db.flush()
            await db.refresh(user_obj)
            logger.info("User created: id=%s, email=%s", user_obj.id, user_obj.email)
            return cast(UserRead, UserRead.model_validate(user_obj))
        except SQLAlchemyError as e:
            logger.error("Error creating user: %s", e)
            raise
    async def update(
        self, id: UUID, db: AsyncSession, **kwargs: Any
    ) -> UserRead | None:
        """Update user data.

        Args:
            id: User identifier (UUID).
            db: Async database session.
            **kwargs: Fields to update.

        Returns:
            Updated UserRead model or None if not found.
        """
        try:
            result = await db.execute(
                select(user_model.User).where(user_model.User.id == id)
            )
            user_obj = result.scalar_one_or_none()
            if not user_obj:
                logger.warning("User not found for update: id=%s", id)
                return None
            for key, value in kwargs.items():
                if hasattr(user_obj, key):
                    setattr(user_obj, key, value)
            await db.flush()
            await db.refresh(user_obj)
            logger.info("User updated: id=%s", id)
            return cast(UserRead, UserRead.model_validate(user_obj))
        except SQLAlchemyError as e:
            logger.error("Error updating user id=%s: %s", id, e)
            raise
    async def delete(self, id: UUID, db: AsyncSession) -> bool:
        """Delete user.

        Args:
            id: User identifier (UUID).
            db: Async database session.

        Returns:
            True if deletion successful, False if user not found.
        """
        try:
            result = await db.execute(
                select(user_model.User).where(user_model.User.id == id)
            )
            user_obj = result.scalar_one_or_none()
            if not user_obj:
                logger.warning("User not found for deletion: id=%s", id)
                return False
            await db.delete(user_obj)
            await db.flush()
            logger.info("User deleted: id=%s", id)
            return True
        except SQLAlchemyError as e:
            logger.error("Error deleting user id=%s: %s", id, e)
            raise
