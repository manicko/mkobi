"""Repository for graph operations.

Provides CRUD methods for Graph model.
All methods use contextual session management and handle errors.
"""

import logging
from uuid import UUID
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models import graphs as graph_model
from mkobi.interfaces.repository_interfaces import IGraphRepository

logger = logging.getLogger(__name__)


class GraphRepository(IGraphRepository):
    """Repository for graph operations.

    Provides methods for creating, reading, updating and deleting
    graphs in the database. All operations are performed within a
    separate database session with automatic transaction management.
    Implements IGraphRepository interface.
    """

    async def get(self, id: UUID, db: AsyncSession) -> graph_model.Graph | None:
        """Get graph by ID.

        Args:
            id: Graph identifier (UUID).
            db: Async database session.

        Returns:
            Graph model or None if not found.
        """
        try:
            result = await db.execute(
                select(graph_model.Graph).where(graph_model.Graph.id == id)
            )
            graph = result.scalar_one_or_none()
            if graph:
                logger.info("Graph retrieved: id=%s", id)
            else:
                logger.warning("Graph not found: id=%s", id)
            return cast(graph_model.Graph | None, graph)
        except SQLAlchemyError as e:
            logger.error("Error getting graph id=%s: %s", id, e)
            raise

    async def get_by_dashboard_id(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> list[graph_model.Graph]:
        """Get all graphs for dashboard.

        Args:
            dashboard_id: Dashboard identifier (UUID).
            db: Async database session.

        Returns:
            List of dashboard graphs.
        """
        try:
            result = await db.execute(
                select(graph_model.Graph).where(
                    graph_model.Graph.dashboard_id == dashboard_id
                )
            )
            graphs = list(result.scalars().all())
            logger.info(
                "Graphs retrieved for dashboard_id=%s, count: %s",
                dashboard_id,
                len(graphs),
            )
            return graphs
        except SQLAlchemyError as e:
            logger.error("Error getting graphs dashboard_id=%s: %s", dashboard_id, e)
            raise

    async def get_by_dashboard_ids(
        self, dashboard_ids: list[UUID], db: AsyncSession
    ) -> list[graph_model.Graph]:
        """Get all graphs for multiple dashboards.

        Args:
            dashboard_ids: List of dashboard identifiers (UUID).
            db: Async database session.

        Returns:
            List of graphs from the specified dashboards.
            Empty list if dashboard_ids is empty.
        """
        if not dashboard_ids:
            return []
        try:
            result = await db.execute(
                select(graph_model.Graph).where(
                    graph_model.Graph.dashboard_id.in_(dashboard_ids)
                )
            )
            graphs = list(result.scalars().all())
            logger.info(
                "Graphs retrieved for %d dashboard_ids, count: %s",
                len(dashboard_ids),
                len(graphs),
            )
            return graphs
        except SQLAlchemyError as e:
            logger.error("Error getting graphs by dashboard ids: %s", e)
            raise

    async def create(self, db: AsyncSession, **kwargs: Any) -> graph_model.Graph | None:
        """Create new graph.

        Args:
            db: Async database session.
            **kwargs: Graph parameters (name, type, config, etc.).

        Returns:
            Created graph model with ID or None on error.
        """
        try:
            graph_obj = graph_model.Graph(**kwargs)
            db.add(graph_obj)
            await db.flush()
            await db.refresh(graph_obj)
            logger.info("Graph created: id=%s, name=%s", graph_obj.id, graph_obj.name)
            return cast(graph_model.Graph | None, graph_obj)
        except SQLAlchemyError as e:
            logger.error("Error creating graph: %s", e, exc_info=True)
            raise

    async def update(
        self, id: UUID, db: AsyncSession, **kwargs: Any
    ) -> graph_model.Graph | None:
        """Update graph data.

        Args:
            id: Graph identifier (UUID).
            db: Async database session.
            **kwargs: Fields to update.

        Returns:
            Updated graph model or None if not found.
        """
        try:
            result = await db.execute(
                select(graph_model.Graph).where(graph_model.Graph.id == id)
            )
            graph_obj = result.scalar_one_or_none()
            if not graph_obj:
                logger.warning("Graph not found for update: id=%s", id)
                return None
            for key, value in kwargs.items():
                if hasattr(graph_obj, key):
                    setattr(graph_obj, key, value)
            await db.flush()
            await db.refresh(graph_obj)
            logger.info("Graph updated: id=%s", id)
            return cast(graph_model.Graph | None, graph_obj)
        except SQLAlchemyError as e:
            logger.error("Error updating graph id=%s: %s", id, e)
            raise

    async def delete(self, id: UUID, db: AsyncSession) -> bool:
        """Delete graph.

        Args:
            id: Graph identifier (UUID).
            db: Async database session.

        Returns:
            True if deletion successful, False if graph not found.
        """
        try:
            result = await db.execute(
                select(graph_model.Graph).where(graph_model.Graph.id == id)
            )
            graph_obj = result.scalar_one_or_none()
            if not graph_obj:
                logger.warning("Graph not found for deletion: id=%s", id)
                return False
            await db.delete(graph_obj)
            await db.flush()
            logger.info("Graph deleted: id=%s", id)
            return True
        except SQLAlchemyError as e:
            logger.error("Error deleting graph id=%s: %s", id, e)
            raise

    async def get_all(self, db: AsyncSession) -> list[graph_model.Graph]:
        """Get all graphs.

        Args:
            db: Async database session.

        Returns:
            List of all graphs.
        """
        try:
            result = await db.execute(select(graph_model.Graph))
            graphs = list(result.scalars().all())
            logger.info("Graphs list retrieved, count: %s", len(graphs))
            return graphs
        except SQLAlchemyError as e:
            logger.error("Error getting graphs list: %s", e)
            raise

    async def get_by_name_and_dashboard(
        self, name: str, dashboard_id: UUID, db: AsyncSession
    ) -> graph_model.Graph | None:
        """Get graph by name and dashboard ID.

        Args:
            name: Graph name.
            dashboard_id: Dashboard identifier.
            db: Async database session.

        Returns:
            Graph model or None if not found.
        """
        try:
            result = await db.execute(
                select(graph_model.Graph).where(
                    graph_model.Graph.name == name,
                    graph_model.Graph.dashboard_id == dashboard_id,
                )
            )
            graph = result.scalar_one_or_none()
            if graph:
                logger.info(
                    "Graph found by name and dashboard: name=%s, dashboard_id=%s",
                    name,
                    dashboard_id,
                )
            else:
                logger.warning(
                    "Graph not found by name and dashboard: name=%s, dashboard_id=%s",
                    name,
                    dashboard_id,
                )
            return cast(graph_model.Graph | None, graph)
        except SQLAlchemyError as e:
            logger.error(
                "Error getting graph by name and dashboard: %s", e
            )
            raise
