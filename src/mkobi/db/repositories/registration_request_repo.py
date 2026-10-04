"""Repository for registration request operations.

Provides methods for creating, reading, updating and deleting
registration requests in the database.
"""

from uuid import UUID
from typing import cast
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.core.logging_config import get_logger
from mkobi.db.models.registration_request import RegistrationRequest
from mkobi.interfaces.repository_interfaces import IRegistrationRequestRepository

logger = get_logger(__name__)


class RegistrationRequestRepository(IRegistrationRequestRepository):
    """Repository for registration request operations.

    Provides methods for creating, reading, updating and deleting
    registration requests in the database.
    """

    async def create(
        self, email: str, ip: str | None, db: AsyncSession
    ) -> RegistrationRequest | None:
        """Create new registration request.

        Args:
            email: Requester email.
            ip: Requester IP address.
            db: Async database session.

        Returns:
            Created registration request model or None on error.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            req = RegistrationRequest(email=email, requested_by_ip=ip)
            db.add(req)
            await db.flush()
            await db.refresh(req)
            logger.info(
                "Registration request created",
                extra={"id": str(req.id), "email": email},
            )
            return req
        except SQLAlchemyError as e:
            logger.error(
                "Error creating registration request",
                extra={"email": email, "error": str(e)},
            )
            raise

    async def get_by_email(
        self, email: str, db: AsyncSession
    ) -> RegistrationRequest | None:
        """Get registration request by email.

        Args:
            email: Email to search.
            db: Async database session.

        Returns:
            Registration request model or None if not found.
        """
        try:
            result = await db.execute(
                select(RegistrationRequest).where(RegistrationRequest.email == email)
            )
            req = result.scalar_one_or_none()
            if req:
                logger.info(
                    "Registration request found",
                    extra={"email": email, "status": req.status},
                )
            else:
                logger.info(
                    "Registration request not found",
                    extra={"email": email},
                )
            return cast(RegistrationRequest | None, req)
        except SQLAlchemyError as e:
            logger.error(
                "Error getting registration request",
                extra={"email": email, "error": str(e)},
            )
            raise

    async def get_by_id(
        self, request_id: UUID, db: AsyncSession
    ) -> RegistrationRequest | None:
        """Get registration request by ID.

        Args:
            request_id: Request identifier (UUID).
            db: Async database session.

        Returns:
            Registration request model or None if not found.
        """
        try:
            result = await db.execute(
                select(RegistrationRequest).where(RegistrationRequest.id == request_id)
            )
            req = result.scalar_one_or_none()
            if req:
                logger.info(
                    "Registration request found",
                    extra={"id": str(request_id), "status": req.status},
                )
            else:
                logger.info(
                    "Registration request not found",
                    extra={"id": str(request_id)},
                )
            return cast(RegistrationRequest | None, req)
        except SQLAlchemyError as e:
            logger.error(
                "Error getting registration request",
                extra={"id": str(request_id), "error": str(e)},
            )
            raise

    async def delete(self, request_id: UUID, db: AsyncSession) -> bool:
        """Delete registration request by ID.

        Args:
            request_id: Request identifier (UUID).
            db: Async database session.

        Returns:
            True if deletion successful, False if request not found.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await db.execute(
                select(RegistrationRequest).where(RegistrationRequest.id == request_id)
            )
            req = result.scalar_one_or_none()
            if not req:
                logger.warning(
                    "Registration request not found for deletion",
                    extra={"id": str(request_id)},
                )
                return False
            await db.delete(req)
            await db.flush()
            logger.info(
                "Registration request deleted",
                extra={"id": str(request_id)},
            )
            return True
        except SQLAlchemyError as e:
            logger.error(
                "Error deleting registration request",
                extra={"id": str(request_id), "error": str(e)},
            )
            raise

    async def get_all(
        self, db: AsyncSession, limit: int | None = None, skip: int = 0
    ) -> list[RegistrationRequest]:
        """Get registration requests, optionally bounded.

        Args:
            db: Async database session.
            limit: Optional maximum number of rows; ``None`` returns all.
            skip: Number of rows to skip (offset).

        Returns:
            List of registration requests.
        """
        try:
            query = select(RegistrationRequest)
            if limit is not None:
                query = query.offset(skip).limit(limit)
            result = await db.execute(query)
            requests = list(result.scalars().all())
            logger.info(
                "Registration requests list retrieved",
                extra={"count": len(requests)},
            )
            return requests
        except SQLAlchemyError as e:
            logger.error(
                "Error getting registration requests list",
                extra={"error": str(e)},
            )
            raise

    async def update_status(
        self,
        request_id: UUID,
        status: str,
        db: AsyncSession,
        reviewed_by: UUID | None = None,
    ) -> RegistrationRequest | None:
        """Update registration request status.

        Args:
            request_id: Request identifier (UUID).
            status: New status.
            db: Async database session.
            reviewed_by: ID of user who reviewed the request.

        Returns:
            Updated registration request model or None if not found.
        """
        try:
            result = await db.execute(
                select(RegistrationRequest).where(RegistrationRequest.id == request_id)
            )
            req = result.scalar_one_or_none()
            if not req:
                logger.warning(
                    "Registration request not found for update",
                    extra={"id": str(request_id)},
                )
                return None
            req.status = status
            if reviewed_by is not None:
                req.reviewed_by = reviewed_by
                req.reviewed_at = datetime.now()
            await db.flush()
            await db.refresh(req)
            logger.info(
                "Registration request status updated",
                extra={"id": str(request_id), "status": status},
            )
            return cast(RegistrationRequest | None, req)
        except SQLAlchemyError as e:
            logger.error(
                "Error updating registration request status",
                extra={"id": str(request_id), "error": str(e)},
            )
            raise
