"""Repository for aggregated data operations.

Provides methods for managing dashboard aggregated data.
All methods use contextual session management and handle errors.

Stored row order
----------------
``AggregationService._apply_chart_sorting`` is the pipeline's ordering decision:
Plotly stacked-bar trace order determines what a chart renders, so the
aggregated frame is sorted (colour total descending, then x ascending) and
``workers/data_worker.py::_store_aggregates`` inserts in that order. That order
is a *presentation contract*, not an incidental side effect.

The three read methods below pin it with ``ORDER BY id``. The ``id`` is an
autoincrement ``BigInteger`` with no ``ordinal`` column, so this is an
**interim** guarantee with a known limitation:

- **Overwrite mode** -- correct. ``save_aggregates(clear_old=True)`` deletes the
  dashboard's rows before re-inserting, so the ``id`` sequence regenerates and
  matches the chart order.
- **Append mode** -- best effort, and wrong at the edges. ``_bulk_upsert``
  updates existing ``(dashboard_id, graph_id, dims)`` rows in place while
  keeping their old ``id``, and new rows take fresh, larger ids. A monotonic
  ``id`` therefore no longer reproduces the freshly computed chart order:
  updated rows keep a stale position and new rows sort after all existing ones.

Closing the append divergence needs a dedicated ``aggregated_data.ordinal``
column populated from the chart order and read back by these methods. That is
**phase-14 DDL** (hand-over ``C05-5``), not a phase-05 change -- this phase
authors no Alembic migration. Until the column lands, the append case is
covered by an explicit test
(``tests/test_repositories.py::TestAggregatedDataReadOrder::test_append_mode_upsert_keeps_stale_id_order``)
that makes the divergence visible, so phase 14 has a test that tells it when
the behaviour changed.
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models import aggregated_data as aggregated_data_model
from mkobi.interfaces.repository_interfaces import IAggregatedDataRepository

logger = logging.getLogger(__name__)


class AggregatedDataRepository(IAggregatedDataRepository):
    """Repository for aggregated data operations.

    Provides methods for saving, reading and deleting
    aggregated data. All operations are performed within a
    separate database session with automatic transaction management.
    Implements IAggregatedDataRepository interface.
    """
    async def bulk_insert(
        self,
        db: AsyncSession,
        dashboard_id: UUID,
        records: list[dict[str, Any]],
        clear_old: bool = True,
    ) -> int:
        """Perform batch insert of aggregated data.

        Operation is performed in transaction:
        1. If clear_old=True, old data is deleted by dashboard_id
        2. Batch insert of new data is performed
        3. Transaction is rolled back on error

        Args:
            db: Async database session.
            dashboard_id: Dashboard identifier.
            records: List of aggregated data for insertion.
                Each item must contain:
                - graph_id: UUID of the graph
                - dims: dict of dimension values (JSON)
                - metrics: dict of metric values (JSON)
            clear_old: Whether to delete old data (default True).

        Returns:
            Number of inserted records.
        """
        try:
            if clear_old:
                await db.execute(
                    delete(aggregated_data_model.AggregatedData).where(
                        aggregated_data_model.AggregatedData.dashboard_id == dashboard_id
                    )
                )

            if not records:
                logger.info("No data to insert: dashboard_id=%s", dashboard_id)
                return 0

            # Prepare data for insertion
            insert_data = []
            for item in records:
                insert_data.append({
                    "dashboard_id": dashboard_id,
                    "graph_id": item["graph_id"],
                    "dims": item["dims"],
                    "metrics": item["metrics"],
                })

            await db.execute(
                insert(aggregated_data_model.AggregatedData),
                insert_data,
            )

            count = len(insert_data)
            logger.info(
                "Data inserted: dashboard_id=%s, count=%s",
                dashboard_id,
                count,
            )
            return count
        except SQLAlchemyError as e:
            logger.error(
                "Error inserting data dashboard_id=%s: %s",
                dashboard_id,
                e,
            )
            raise
    async def get_by_dashboard_id(
        self, dashboard_id: UUID, db: AsyncSession
    ) -> list[aggregated_data_model.AggregatedData]:
        """Get aggregated data for dashboard, in stored chart order.

        Rows are returned by ascending ``id`` -- the interim stored-order
        guarantee described in the module docstring. Under overwrite mode this
        reproduces the chart order; under append mode it diverges (phase-14
        hand-over ``C05-5``).

        Args:
            dashboard_id: Dashboard identifier.
            db: Async database session.

        Returns:
            List of aggregated data for dashboard, ordered by ascending id.
        """
        try:
            result = await db.execute(
                select(aggregated_data_model.AggregatedData)
                .where(aggregated_data_model.AggregatedData.dashboard_id == dashboard_id)
                .order_by(aggregated_data_model.AggregatedData.id)
            )
            data = list(result.scalars().all())
            logger.info(
                "Data retrieved for dashboard_id=%s, count=%s",
                dashboard_id,
                len(data),
            )
            return data
        except SQLAlchemyError as e:
            logger.error(
                "Error getting data dashboard_id=%s: %s",
                dashboard_id,
                e,
            )
            raise
    async def get_by_graph_id(
        self,
        graph_id: UUID,
        db: AsyncSession,
        dashboard_id: UUID | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[aggregated_data_model.AggregatedData]:
        """Get aggregated data for graph, in stored chart order.

        Rows are returned by ascending ``id`` -- the interim stored-order
        guarantee described in the module docstring. Under overwrite mode this
        reproduces the chart order; under append mode it diverges (phase-14
        hand-over ``C05-5``).

        Args:
            graph_id: Graph identifier (UUID).
            db: Async database session.
            dashboard_id: Optional dashboard identifier for additional filtering.
            filters: Optional dictionary of filters for JSONB field dims.

        Returns:
            List of data points for graph, ordered by ascending id.
        """
        try:
            query = select(aggregated_data_model.AggregatedData).where(
                aggregated_data_model.AggregatedData.graph_id == graph_id
            )

            # Apply dashboard_id filter for data isolation
            if dashboard_id is not None:
                query = query.where(
                    aggregated_data_model.AggregatedData.dashboard_id == dashboard_id
                )

            # Apply filters to JSONB field dims
            if filters:
                for key, value in filters.items():
                    query = query.where(
                        aggregated_data_model.AggregatedData.dims[key].astext == str(value)
                    )

            query = query.order_by(aggregated_data_model.AggregatedData.id)

            result = await db.execute(query)
            data = list(result.scalars().all())
            logger.info(
                "Data retrieved for graph_id=%s, count=%s",
                graph_id,
                len(data),
            )
            return data
        except SQLAlchemyError as e:
            logger.error(
                "Error getting data graph_id=%s: %s",
                graph_id,
                e,
            )
            raise
    async def delete_by_graph_id(
        self,
        graph_id: UUID,
        db: AsyncSession,
    ) -> int:
        """Delete aggregated data for graph.

        Args:
            graph_id: Graph identifier.
            db: Async database session.

        Returns:
            Number of deleted records.
        """
        try:
            result = await db.execute(
                delete(aggregated_data_model.AggregatedData)
                .where(aggregated_data_model.AggregatedData.graph_id == graph_id)
            )
            count = result.rowcount if hasattr(result, 'rowcount') else 0
            logger.info(
                "Data deleted: graph_id=%s, count=%s",
                graph_id,
                count,
            )
            return count
        except SQLAlchemyError as e:
            logger.error(
                "Error deleting data graph_id=%s: %s",
                graph_id,
                e,
            )
            raise
    async def delete_by_dashboard_id(
        self,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> int:
        """Delete all aggregated data for dashboard.

        Args:
            dashboard_id: Dashboard identifier.
            db: Async database session.

        Returns:
            Number of deleted records.
        """
        try:
            result = await db.execute(
                delete(aggregated_data_model.AggregatedData)
                .where(aggregated_data_model.AggregatedData.dashboard_id == dashboard_id)
            )
            count = result.rowcount if hasattr(result, 'rowcount') else 0
            logger.info(
                "Data deleted: dashboard_id=%s, count=%s",
                dashboard_id,
                count,
            )
            return count
        except SQLAlchemyError as e:
            logger.error(
                "Error deleting data dashboard_id=%s: %s",
                dashboard_id,
                e,
            )
            raise
    async def get_dims_values(
        self,
        graph_id: UUID,
        dim_name: str,
        db: AsyncSession,
    ) -> list[str]:
        """Get unique dimension values for graph, in stored chart order.

        Used to get filter value lists.
        Extracts unique values from JSONB field dims.

        Values are deduplicated and ordered by the smallest ``id`` of the rows
        carrying them, i.e. the position of each value's first occurrence in the
        stored row order. This keeps the uniqueness the previous ``DISTINCT``
        gave (a graph's rows can share a ``dim_name`` value across different
        composite ``dims``) while making the result deterministic -- the same
        interim guarantee as the other read methods (module docstring): under
        overwrite mode it tracks the chart order, under append mode it diverges
        (phase-14 hand-over ``C05-5``).

        Args:
            graph_id: Graph identifier.
            dim_name: Dimension name (field in JSONB dims).
            db: Async database session.

        Returns:
            List of unique dimension values, in stored row order.
        """
        try:
            # One row per distinct value, carrying the smallest id that holds
            # it; ordering by that id fixes each value's first-seen position.
            value_expr = aggregated_data_model.AggregatedData.dims[dim_name].astext
            first_seen = (
                select(
                    value_expr.label("value_name"),
                    func.min(aggregated_data_model.AggregatedData.id).label("first_id"),
                )
                .where(
                    aggregated_data_model.AggregatedData.graph_id == graph_id
                )
                .group_by(value_expr)
                .subquery()
            )
            result = await db.execute(
                select(first_seen.c.value_name).order_by(first_seen.c.first_id)
            )
            values = [row[0] for row in result if row[0] is not None]
            logger.info(
                "Dimension values retrieved: graph_id=%s, dim_name=%s, count=%s",
                graph_id,
                dim_name,
                len(values),
            )
            return values
        except SQLAlchemyError as e:
            logger.error(
                "Error getting dimension values graph_id=%s: %s",
                graph_id,
                e,
            )
            raise
