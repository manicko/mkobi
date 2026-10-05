"""Storage manager for aggregated data.

Implements operations for saving, updating, deleting and retrieving
aggregated data for dashboards in PostgreSQL.

Features:
- Uses PostgreSQL UPSERT (ON CONFLICT DO UPDATE)
- Supports batch insert/upsert
- Does not manage transactions (commit/rollback is external)
- Uses SQLAlchemy Core
- No race condition

Dimension identity
------------------
``_canonicalize_dims`` is applied at every write surface (``_bulk_insert``,
``_bulk_upsert`` and ``upsert_aggregate``) so a dimension value is stored as
its canonical string and the conflict target ``((dims)::text)`` matches. See
:func:`_canonicalize_dim_scalar` for the rule.
"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import and_, bindparam, delete, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert

from mkobi.db.models.aggregated_data import AggregatedData
from mkobi.models.enums import UploadMode

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _normalize_json_keys(data: Any) -> Any:
    """Recursively sort dictionary keys for deterministic JSON serialization.

    Ensures that semantically identical JSON objects produce the same text
    representation regardless of original key ordering. Two tests assert this
    key-sort contract. Note that jsonb canonicalises key order itself, so this
    sort is cosmetic for index identity -- it is not what makes the conflict
    target stable.

    Args:
        data: Any JSON-serializable data structure.

    Returns:
        The same data with all dict keys sorted recursively.
    """
    if isinstance(data, dict):
        return {k: _normalize_json_keys(v) for k, v in sorted(data.items())}
    if isinstance(data, list):
        return [_normalize_json_keys(item) for item in data]
    return data


def _canonicalize_dim_scalar(value: Any) -> str:
    """Canonicalise a single dimension value to its stored string form.

    Row identity on ``aggregated_data`` is the unique index
    ``uq_aggregated_data_dashboard_graph_dims`` on
    ``(dashboard_id, graph_id, dims::text)``, and every write surface names the
    conflict target ``text("((dims)::text)")``. The same logical value renders
    differently with its native type -- ``{"region": "1"}`` under a ``Utf8``
    column and ``{"region": 1}`` under an ``Int64`` column -- so no conflict
    match occurs and one category becomes two rows, doubling every chart total.

    The rule (ruling ``D-05-E``):

    - ``None`` -> ``""`` (unchanged).
    - A value with ``isoformat`` (``date``, ``datetime``) -> its ISO string,
      keeping the ``T`` separator. A blanket ``str()`` would give
      ``'2024-01-01 00:00:00'`` and silently re-space every stored datetime.
    - ``int``, ``float``, ``bool`` -> ``str(value)``. ``str(True) == "True"`` is
      distinct from ``str(1) == "1"``, so a boolean dimension does not collide
      with a 0/1 dimension. A ``Float64`` value holding ``1e-07`` becomes the
      string ``'1e-07'``, which ``->>`` returns unchanged -- native storage
      would render it through ``numeric`` as ``0.0000001`` and make it
      unreadable by the read path's ``astext == str(value)`` comparison.
    - Anything else -> ``str(value)``.

    ``metrics`` are deliberately NOT canonicalised -- numbers there are the data.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _canonicalize_dims(data: Any) -> dict[str, Any]:
    """Canonicalise a ``dims`` mapping so one logical category is one row.

    Delegates the key-sort contract to :func:`_normalize_json_keys` and maps
    every scalar value through :func:`_canonicalize_dim_scalar`, so the value
    PostgreSQL serialises into the index key is the exact same bytes for every
    write surface. Nested dicts and lists are canonicalised recursively so the
    key-sort contract is preserved at every level. This lives in the storage
    layer -- not in ``AggregationService._coerce_dim_value`` -- because the
    conflict target ``((dims)::text)`` is evaluated by PostgreSQL on the value
    about to be inserted, so this is the only placement where the index key and
    the stored value are provably identical, and the only one that covers all
    three write surfaces including a hand-built ``save_aggregates`` call that
    bypasses the service.

    Args:
        data: A ``dims`` mapping (already validated as a dict).

    Returns:
        The same structure with keys sorted and scalar values canonicalised.
    """
    return {
        key: _canonicalize_dims_value(nested)
        for key, nested in _normalize_json_keys(data).items()
    }


def _canonicalize_dims_value(value: Any) -> Any:
    """Recursively canonicalise a dims value: scalars to str, containers kept.

    Args:
        value: A scalar, dict or list from a ``dims`` mapping.

    Returns:
        Scalars mapped through :func:`_canonicalize_dim_scalar`; dicts and lists
        rebuilt recursively with their keys sorted.
    """
    if isinstance(value, dict):
        return {
            key: _canonicalize_dims_value(nested)
            for key, nested in _normalize_json_keys(value).items()
        }
    if isinstance(value, list):
        return [_canonicalize_dims_value(item) for item in value]
    return _canonicalize_dim_scalar(value)


class StorageManager:
    """Storage manager for aggregated data.

    Writes are set-based. The chunk size is derived from the store's
    bind-parameter limit rather than an arbitrary constant, so the statement
    count for a save is ``ceil(N / ROWS_PER_STATEMENT)`` and is bounded by a
    protocol limit, not by a magic number.
    """

    # PostgreSQL's protocol limit on bind parameters in a single statement
    # (``MaxBindParams`` in the backend). It is a property of the store, not a
    # tuning choice.
    MAX_BIND_PARAMS: int = 65535

    # Columns written per row by ``_write_set_based`` for ``aggregated_data``:
    # ``dashboard_id``, ``graph_id``, ``dims``, ``metrics``.
    COLUMNS_PER_ROW: int = 4

    # Largest number of rows a statement may carry before it would exceed the
    # bind-parameter ceiling in the equivalent row-per-parameter form. With the
    # four columns above this is 65535 // 4 = 16383. The ``unnest`` form uses a
    # fixed four array parameters per statement regardless of row count, so
    # this bound is conservative: it keeps any single array from growing
    # without limit while still making the statement count a small fraction of
    # the old per-1000-row chunking.
    ROWS_PER_STATEMENT: int = MAX_BIND_PARAMS // COLUMNS_PER_ROW

    def __init__(self, db: AsyncSession) -> None:
        """Initialize manager.

        Args:
            db: Async SQLAlchemy session.
        """
        self.db = db

    # =========================================================================
    # Public API
    # =========================================================================

    async def save_aggregates(
        self,
        dashboard_id: UUID,
        aggregates: list[dict[str, Any]],
        clear_old: bool = False,
    ) -> int:
        """Save aggregated data.

        When clear_old=True:
        - deletes old dashboard data
        - performs bulk insert

        When clear_old=False:
        - performs bulk upsert

        Args:
            dashboard_id: Dashboard ID.
            aggregates: Aggregated data.
            clear_old: Delete old data.

        Returns:
            Number of processed records.

        Raises:
            ValueError: Validation error.
            SQLAlchemyError: Database error.
        """
        # The empty-list check must not short-circuit a clear_old=True call
        # before its own delete. Returning early here while the caller's
        # separate clear_dashboard_values still ran produced a torn state: the
        # old aggregate rows survived, the filter-value list was wiped, and the
        # run reported success (DP-004). An empty list with clear_old=True
        # therefore still performs the clear -- no rows are inserted and the
        # method returns 0, but the clear is not skipped. Callers that must
        # preserve the previous rows (the worker's empty-selection guard) fail
        # before reaching this method.
        if not aggregates:
            logger.info(
                "Empty aggregates list for dashboard_id=%s",
                dashboard_id,
            )

            if clear_old:
                deleted = await self.delete_by_dashboard(dashboard_id)

                logger.info(
                    "Deleted %d old records for dashboard_id=%s",
                    deleted,
                    dashboard_id,
                )

            return 0

        self._validate_aggregates(aggregates)

        graph_ids = {agg["graph_id"] for agg in aggregates}

        await self._validate_graphs_exist(
            graph_ids=graph_ids,
            dashboard_id=dashboard_id,
        )

        if clear_old:
            deleted = await self.delete_by_dashboard(dashboard_id)

            logger.info(
                "Deleted %d old records for dashboard_id=%s",
                deleted,
                dashboard_id,
            )

            inserted = await self._bulk_insert(
                dashboard_id=dashboard_id,
                aggregates=aggregates,
                table_model=AggregatedData,
            )

            logger.info(
                "Inserted %d aggregates for dashboard_id=%s",
                inserted,
                dashboard_id,
            )

            return inserted

        processed = await self._bulk_upsert(
            dashboard_id=dashboard_id,
            aggregates=aggregates,
            table_model=AggregatedData,
        )

        logger.info(
            "Upserted %d aggregates for dashboard_id=%s",
            processed,
            dashboard_id,
        )

        return processed

    async def upsert_aggregate(
        self,
        dashboard_id: UUID,
        graph_id: UUID,
        dims: dict[str, Any],
        metrics: dict[str, Any],
    ) -> bool:
        """Perform UPSERT for a single aggregate.

        Returns:
            True if a new record was inserted.
            False if an existing record was updated.
        """
        self._validate_single_aggregate(dims, metrics)

        await self._validate_graphs_exist(
            graph_ids={graph_id},
            dashboard_id=dashboard_id,
        )

        normalized_dims = _canonicalize_dims(dims)

        stmt = insert(AggregatedData).values(
            dashboard_id=dashboard_id,
            graph_id=graph_id,
            dims=normalized_dims,
            metrics=metrics,
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=[
                AggregatedData.dashboard_id,
                AggregatedData.graph_id,
                text("((dims)::text)"),
            ],
            set_={
                "metrics": stmt.excluded.metrics,
            },
        ).returning(AggregatedData.id)

        result = await self.db.execute(stmt)

        inserted = result.scalar_one_or_none() is not None

        logger.debug(
            "UPSERT aggregate dashboard_id=%s graph_id=%s",
            dashboard_id,
            graph_id,
        )

        return inserted

    async def get_aggregates(
        self,
        dashboard_id: UUID,
        graph_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve aggregated data."""
        query = select(
            AggregatedData.id,
            AggregatedData.graph_id,
            AggregatedData.dims,
            AggregatedData.metrics,
        ).where(
            AggregatedData.dashboard_id == dashboard_id,
        )

        if graph_id:
            query = query.where(
                AggregatedData.graph_id == graph_id,
            )

        result = await self.db.execute(query)

        return [
            {
                "id": row.id,
                "graph_id": row.graph_id,
                "dims": row.dims,
                "metrics": row.metrics,
            }
            for row in result
        ]

    async def delete_by_graph(
        self,
        graph_id: UUID,
    ) -> int:
        """Delete data for a specific graph."""
        result = await self.db.execute(
            delete(AggregatedData).where(
                AggregatedData.graph_id == graph_id,
            )
        )

        deleted = result.rowcount or 0

        logger.info(
            "Deleted %d records for graph_id=%s",
            deleted,
            graph_id,
        )

        return deleted

    async def delete_by_dashboard(
        self,
        dashboard_id: UUID,
    ) -> int:
        """Delete all data for a dashboard."""
        result = await self.db.execute(
            delete(AggregatedData).where(
                AggregatedData.dashboard_id == dashboard_id,
            )
        )

        deleted = result.rowcount or 0

        logger.info(
            "Deleted %d records for dashboard_id=%s",
            deleted,
            dashboard_id,
        )

        return deleted

    # =========================================================================
    # Internal methods
    # =========================================================================

    async def _bulk_insert(
        self,
        dashboard_id: UUID,
        aggregates: list[dict[str, Any]],
        table_model: Any,
    ) -> int:
        """Perform the OVERWRITE write as one set-based statement per chunk.

        Each statement is ``INSERT ... SELECT ... FROM unnest(...)`` so a chunk
        of N rows costs a fixed four bind parameters regardless of N, not one
        per row. The chunk size is still bounded, by the derived
        :attr:`ROWS_PER_STATEMENT`, so no single statement carries an unbounded
        array. Statement count is ``ceil(N / ROWS_PER_STATEMENT)``.
        """
        return await self._write_set_based(
            dashboard_id=dashboard_id,
            aggregates=aggregates,
            table_model=table_model,
            on_conflict=False,
        )

    async def _bulk_upsert(
        self,
        dashboard_id: UUID,
        aggregates: list[dict[str, Any]],
        table_model: Any,
    ) -> int:
        """Perform the APPEND write as one set-based upsert statement per chunk.

        Same ``unnest`` shape as :meth:`_bulk_insert`, plus the
        ``ON CONFLICT ... DO UPDATE`` clause. The conflict target is the
        expression unique index ``uq_aggregated_data_dashboard_graph_dims`` on
        ``((dims)::text)``, named identically to every other write site.
        """
        return await self._write_set_based(
            dashboard_id=dashboard_id,
            aggregates=aggregates,
            table_model=table_model,
            on_conflict=True,
        )

    async def _write_set_based(
        self,
        dashboard_id: UUID,
        aggregates: list[dict[str, Any]],
        table_model: Any,
        *,
        on_conflict: bool,
    ) -> int:
        """Write rows in set-based chunks, optionally as an UPSERT.

        Canonicalisation is applied here, at the write surface, so the bytes
        PostgreSQL serialises into the ``((dims)::text)`` index key are exactly
        the bytes stored -- the property the conflict target depends on.

        Args:
            dashboard_id: Dashboard owning every row in ``aggregates``.
            aggregates: Validated aggregate dicts (``graph_id``, ``dims``,
                ``metrics``).
            table_model: The ORM model class for the target table.
            on_conflict: When True, append the UPSERT clause; when False, the
                plain insert used by the OVERWRITE path.

        Returns:
            The number of rows written (one per input aggregate).
        """
        total = 0

        for start in range(0, len(aggregates), self.ROWS_PER_STATEMENT):
            chunk = aggregates[start : start + self.ROWS_PER_STATEMENT]

            dashboard_ids = [dashboard_id] * len(chunk)
            graph_ids = [agg["graph_id"] for agg in chunk]
            dims = [_canonicalize_dims(agg["dims"]) for agg in chunk]
            metrics = [agg["metrics"] for agg in chunk]

            dashboard_ids_param = bindparam(
                "dashboard_ids", type_=ARRAY(PG_UUID(as_uuid=True))
            )
            graph_ids_param = bindparam(
                "graph_ids", type_=ARRAY(PG_UUID(as_uuid=True))
            )
            dims_param = bindparam("dims", type_=ARRAY(JSONB))
            metrics_param = bindparam("metrics", type_=ARRAY(JSONB))

            stmt = insert(table_model.__table__).from_select(
                [
                    table_model.dashboard_id,
                    table_model.graph_id,
                    table_model.dims,
                    table_model.metrics,
                ],
                select(
                    func.unnest(dashboard_ids_param).label("dashboard_id"),
                    func.unnest(graph_ids_param).label("graph_id"),
                    func.unnest(dims_param).label("dims"),
                    func.unnest(metrics_param).label("metrics"),
                ),
            )

            if on_conflict:
                stmt = stmt.on_conflict_do_update(
                    index_elements=[
                        table_model.dashboard_id,
                        table_model.graph_id,
                        text("((dims)::text)"),
                    ],
                    set_={
                        "metrics": stmt.excluded.metrics,
                    },
                )

            await self.db.execute(
                stmt,
                {
                    "dashboard_ids": dashboard_ids,
                    "graph_ids": graph_ids,
                    "dims": dims,
                    "metrics": metrics,
                },
            )

            total += len(chunk)

        return total

    async def _validate_graphs_exist(
        self,
        graph_ids: set[UUID],
        dashboard_id: UUID,
    ) -> None:
        """Validate that graphs exist and belong to the dashboard."""
        from mkobi.db.models import graphs as graphs_model

        result = await self.db.execute(
            select(graphs_model.Graph.id).where(
                and_(
                    graphs_model.Graph.id.in_(list(graph_ids)),
                    graphs_model.Graph.dashboard_id == dashboard_id,
                )
            )
        )

        found_ids = set(result.scalars().all())

        missing = graph_ids - found_ids

        if missing:
            raise ValueError(
                f"Graphs not found or do not belong to dashboard: {missing}"
            )

    def _validate_aggregates(
        self,
        aggregates: list[dict[str, Any]],
    ) -> None:
        """Validate list of aggregates."""
        required_fields = {
            "graph_id",
            "dims",
            "metrics",
        }

        for idx, agg in enumerate(aggregates):
            missing = required_fields - set(agg.keys())

            if missing:
                raise ValueError(f"Aggregate {idx} missing fields: {missing}")

            self._validate_single_aggregate(
                dims=agg["dims"],
                metrics=agg["metrics"],
            )

    @staticmethod
    def _validate_single_aggregate(
        dims: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        """Validate a single aggregate."""
        if not isinstance(dims, dict):
            raise ValueError("dims must be a dict")

        if not isinstance(metrics, dict):
            raise ValueError("metrics must be a dict")

    # =========================================================================
    # Compatibility API
    # =========================================================================

    async def clear_graph_data(
        self,
        graph_id: UUID,
    ) -> int:
        """Delete aggregated data for a specific graph.

        Args:
            graph_id: Graph ID.

        Returns:
            Number of deleted records.
        """
        return await self.delete_by_graph(graph_id=graph_id)

    async def clear_dashboard_data(
        self,
        dashboard_id: UUID,
    ) -> int:
        """Delete all aggregated data for a dashboard.

        Args:
            dashboard_id: Dashboard ID.

        Returns:
            Number of deleted records.
        """
        return await self.delete_by_dashboard(dashboard_id=dashboard_id)

    @classmethod
    async def save_aggregated_data(
        cls,
        dashboard_id: UUID,
        graph_id: UUID,
        aggregated_results: list[dict[str, Any]],
        mode: UploadMode,
        db: AsyncSession,
    ) -> None:
        """Compatibility wrapper.

        .. deprecated::
            Use instance method :meth:`save_aggregates` instead.
        """
        warnings.warn(
            "save_aggregated_data classmethod is deprecated. Use instance method "
            "save_aggregates instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        manager = cls(db)

        aggregates = [
            {
                "graph_id": graph_id,
                "dims": item.get("dims", {}),
                "metrics": item.get("metrics", {}),
            }
            for item in aggregated_results
        ]

        await manager.save_aggregates(
            dashboard_id=dashboard_id,
            aggregates=aggregates,
            clear_old=(mode == UploadMode.OVERWRITE),
        )

    @classmethod
    async def clear_graph_data_compat(
        cls,
        graph_id: UUID,
        db: AsyncSession,
    ) -> int:
        """Compatibility method with db parameter.

        .. deprecated::
            Use instance method :meth:`clear_graph_data` instead.

        Args:
            graph_id: Graph ID.
            db: Async SQLAlchemy session.

        Returns:
            Number of deleted records.
        """
        warnings.warn(
            "clear_graph_data_compat classmethod is deprecated. Use instance method "
            "clear_graph_data instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        manager = cls(db)
        return await manager.clear_graph_data(graph_id=graph_id)

    @classmethod
    async def clear_dashboard_data_compat(
        cls,
        dashboard_id: UUID,
        db: AsyncSession,
    ) -> int:
        """Compatibility method with db parameter.

        .. deprecated::
            Use instance method :meth:`clear_dashboard_data` instead.

        Args:
            dashboard_id: Dashboard ID.
            db: Async SQLAlchemy session.

        Returns:
            Number of deleted records.
        """
        warnings.warn(
            "clear_dashboard_data_compat classmethod is deprecated. Use instance "
            "method clear_dashboard_data instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        manager = cls(db)
        return await manager.clear_dashboard_data(dashboard_id=dashboard_id)
