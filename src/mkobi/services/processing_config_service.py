"""Processing configuration service.

Provides business logic for operations with processing settings.

All operations are performed asynchronously through IProcessingConfigRepository.
"""

import logging
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.interfaces.repository_interfaces import IProcessingConfigRepository
from mkobi.interfaces.service_interfaces import IProcessingConfigService
from mkobi.models.processing_configs import ProcessingConfigRead
from mkobi.models.types import ProcessingSettingsModel

logger = logging.getLogger(__name__)


class ProcessingConfigService(IProcessingConfigService):
    """Processing configuration management service."""

    def __init__(self, config_repo: IProcessingConfigRepository) -> None:
        """Initialize service with injected repository.

        Args:
            config_repo: Processing config repository instance.
        """
        self.config_repo = config_repo
        logger.info("ProcessingConfigService initialized with injected repository")

    def _merge_metric_agg_into_settings(
        self,
        settings: ProcessingSettingsModel | None,
        metric_agg: str | None,
    ) -> ProcessingSettingsModel | None:
        """Merge metric_agg into the settings model.

        A raw ``{**settings, "metric_agg": ...}`` spread does not work on a
        ``BaseModel``, so the merge is ``model_dump``-based: the stored settings
        are dumped to a dict, the metric_agg is placed, and the result is
        re-validated. Re-validation is the point -- the merged dict is the same
        strict boundary as the request body.

        Args:
            settings: Processing settings model.
            metric_agg: Optional metric aggregation function.

        Returns:
            Settings model with metric_agg merged in, or None.
        """
        if settings is None:
            return None
        if metric_agg is not None:
            merged = settings.model_dump()
            merged["metric_agg"] = metric_agg
            return cast(ProcessingSettingsModel, ProcessingSettingsModel.model_validate(merged))
        return settings

    def _extract_metric_agg_from_settings(
        self,
        settings: ProcessingSettingsModel,
    ) -> str | None:
        """Extract metric_agg from the settings model.

        Args:
            settings: Processing settings model.

        Returns:
            metric_agg value or None.
        """
        metric_agg = settings.metric_agg
        if metric_agg is None:
            return None
        return str(metric_agg)

    async def _validate_settings(self, settings: ProcessingSettingsModel) -> None:
        """Validate processing settings structure.

        The type authority for every settings key is now
        :class:`ProcessingSettingsModel`, which the request boundary enforces
        with ``extra="forbid"``. Only the two structural checks remain here; the
        per-key type loop was provably redundant once the boundary type became a
        model, and extending it to all nineteen keys would create a second
        source of truth.

        Args:
            settings: Processing settings model.

        Raises:
            ValueError: If the settings structure is incorrect.
        """
        if not isinstance(settings, ProcessingSettingsModel):
            raise ValueError("Settings must be a ProcessingSettingsModel")

        if not settings.model_dump(exclude_none=True):
            raise ValueError("Settings cannot be empty")

    async def get_by_dashboard_id(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> ProcessingConfigRead | None:
        """Get processing config by dashboard ID.

        Args:
            dashboard_id: Dashboard identifier.
            db: Async database session.

        Returns:
            ProcessingConfigRead or None if not found.
        """
        logger.info("Getting config: dashboard_id=%s", dashboard_id)

        config_obj = await self.config_repo.get(dashboard_id, db)
        if config_obj is None:
            logger.warning("Config not found: dashboard_id=%s", dashboard_id)
            return None

        logger.info("Config retrieved: dashboard_id=%s", dashboard_id)
        # Extract metric_agg from settings for the response. The stored JSONB is
        # re-validated against the strict model before it is used, so a stored
        # payload cannot carry a key the boundary would reject.
        stored_settings = ProcessingSettingsModel.model_validate(config_obj.settings)
        metric_agg = self._extract_metric_agg_from_settings(stored_settings)
        return cast(
            ProcessingConfigRead,
            ProcessingConfigRead.model_validate(
                {
                    "dashboard_id": config_obj.dashboard_id,
                    "settings": stored_settings,
                    "updated_at": config_obj.updated_at,
                    "metric_agg": metric_agg,
                }
            ),
        )

    async def upsert(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
        settings: ProcessingSettingsModel | None = None,
        metric_agg: str | None = None,
    ) -> ProcessingConfigRead:
        """Create or update processing config.

        Args:
            dashboard_id: Dashboard identifier.
            db: Async database session.
            settings: Processing settings model.
            metric_agg: Optional metric aggregation function to merge into settings.

        Returns:
            ProcessingConfigRead: Config model.

        Raises:
            ValueError: If settings structure is incorrect.
        """
        logger.info("Upsert config: dashboard_id=%s", dashboard_id)

        # Merge metric_agg into settings
        settings = self._merge_metric_agg_into_settings(settings, metric_agg)

        if settings is not None:
            await self._validate_settings(settings)

        # JSONB stores a plain dict; the model is the boundary, not the column.
        stored: dict[str, Any] | None = (
            settings.model_dump(exclude_none=True) if settings is not None else None
        )

        existing = await self.config_repo.get(dashboard_id, db)
        if existing:
            updated = await self.config_repo.update(
                dashboard_id, db, settings=stored
            )
            if updated is None:
                raise ValueError(
                    f"Failed to update config for dashboard {dashboard_id}"
                )
            logger.info("Config updated: dashboard_id=%s", dashboard_id)
            updated_settings = ProcessingSettingsModel.model_validate(updated.settings)
            return cast(
                ProcessingConfigRead,
                ProcessingConfigRead.model_validate(
                    {
                        "dashboard_id": updated.dashboard_id,
                        "settings": updated_settings,
                        "updated_at": updated.updated_at,
                        "metric_agg": self._extract_metric_agg_from_settings(updated_settings),
                    }
                ),
            )
        else:
            created = await self.config_repo.create(
                db=db,
                dashboard_id=dashboard_id,
                settings=stored,
            )
            if created is None:
                raise ValueError(
                    f"Failed to create config for dashboard {dashboard_id}"
                )
            logger.info("Config created: dashboard_id=%s", dashboard_id)
            created_settings = ProcessingSettingsModel.model_validate(created.settings)
            return cast(
                ProcessingConfigRead,
                ProcessingConfigRead.model_validate(
                    {
                        "dashboard_id": created.dashboard_id,
                        "settings": created_settings,
                        "updated_at": created.updated_at,
                        "metric_agg": self._extract_metric_agg_from_settings(created_settings),
                    }
                ),
            )

    async def delete(self, dashboard_id: UUID, db: AsyncSession) -> bool:
        """Delete processing config.

        Args:
            dashboard_id: Dashboard identifier.
            db: Async database session.

        Returns:
            True if deletion successful.
        """
        logger.info("Deleting config: dashboard_id=%s", dashboard_id)

        result: bool = await self.config_repo.delete(dashboard_id, db)
        if result:
            logger.info("Config deleted: dashboard_id=%s", dashboard_id)
        else:
            logger.warning(
                "Config not found for deletion: dashboard_id=%s", dashboard_id
            )
        return result

    # ========= IProcessingConfigService interface methods =========

    async def create_processing_config(
        self,
        dashboard_id: UUID,
        settings: ProcessingSettingsModel,
        db: AsyncSession,
        metric_agg: str | None = None,
    ) -> ProcessingConfigRead:
        """Create processing config for dashboard."""
        return await self.upsert(dashboard_id, db, settings=settings, metric_agg=metric_agg)

    async def get_processing_config_by_dashboard(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> ProcessingConfigRead | None:
        """Get processing config by dashboard ID."""
        return await self.get_by_dashboard_id(dashboard_id, db)

    async def update_processing_config(
        self,
        dashboard_id: UUID,
        settings: ProcessingSettingsModel,
        db: AsyncSession,
        metric_agg: str | None = None,
    ) -> ProcessingConfigRead | None:
        """Update processing config."""
        return await self.upsert(dashboard_id, db, settings=settings, metric_agg=metric_agg)

    async def delete_processing_config(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> bool:
        """Delete processing config."""
        return await self.delete(dashboard_id, db)