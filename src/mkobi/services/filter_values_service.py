"""Filter values service.

Provides business logic for retrieving dashboard filter values.
All operations are performed through injected repository.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.interfaces.repository_interfaces import IDashboardFilterValuesRepository

logger = logging.getLogger(__name__)


class FilterValuesService:
    """Service for filter values operations.

    Implements business logic for retrieving filter values from dashboards.
    Uses injected IDashboardFilterValuesRepository for data access.
    """

    def __init__(self, repo: IDashboardFilterValuesRepository) -> None:
        """Initialize service with injected repository.

        Args:
            repo: Dashboard filter values repository implementation.
        """
        self._repo = repo

    async def get_filter_values(
        self,
        dashboard_id: UUID,
        filter_name: str,
        db: AsyncSession,
        limit: int | None = None,
        skip: int = 0,
    ) -> tuple[list[str], int]:
        """Return distinct filter values for a dashboard filter plus the total.

        Args:
            dashboard_id: Dashboard identifier.
            filter_name: Name of the filter to get values for.
            db: Async database session.
            limit: Optional maximum number of values; ``None`` returns all.
            skip: Number of values to skip (offset).

        Returns:
            tuple[list[str], int]: The (possibly bounded) values and the true,
            untruncated distinct-value count.
        """
        logger.info(
            "Getting filter values: dashboard_id=%s, filter_name=%s",
            dashboard_id,
            filter_name,
        )
        values = await self._repo.get_filter_values(
            dashboard_id, filter_name, db, limit=limit, skip=skip
        )
        total = await self._repo.count_filter_values(dashboard_id, filter_name, db)
        return values, total