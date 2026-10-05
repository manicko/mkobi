"""PRF-10: the aggregate write is set-based, not chunked on the event loop.

PERF-003 (HIGH): ``StorageManager`` chunked its writes, so an N-row save issued
``ceil(N / CHUNK_SIZE) + 2`` statements -- all on the event loop that also
serves requests. The write is now set-based: each statement carries a chunk of
``StorageManager.ROWS_PER_STATEMENT`` rows, and the statement count for a save is
``ceil(N / ROWS_PER_STATEMENT)``, bounded by the store's bind-parameter limit.

These tests pin the outcome, not the mechanism: the statement bound, the UPSERT
identity, the empty-selection and append/overwrite semantics, the hand-built
aggregate conflict target, and the cross-batch boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from mkobi.data.storage.manager import StorageManager
from mkobi.db.models.aggregated_data import AggregatedData
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.models.enums import GraphType

# The derived per-statement row capacity:
#
#   ROWS_PER_STATEMENT = MAX_BIND_PARAMS // COLUMNS_PER_ROW = 65535 // 4 = 16383
#
# 65535 is PostgreSQL's protocol limit on bind parameters in one statement
# (``MaxBindParams``). ``aggregated_data`` is written through four columns
# (``dashboard_id``, ``graph_id``, ``dims``, ``metrics``), so in the equivalent
# row-per-parameter form one statement carries at most 65535 // 4 = 16383 rows.
# The old assertion scaled with the arbitrary ``CHUNK_SIZE = 1000``; this one
# does not.
_MAX_BIND_PARAMS = 65535
_COLUMNS_PER_ROW = 4
_DERIVED_ROWS_PER_STATEMENT = _MAX_BIND_PARAMS // _COLUMNS_PER_ROW  # 16383


@pytest.fixture
def manager(async_db_session: AsyncSession) -> StorageManager:
    """Create a StorageManager bound to the isolated test session."""
    return StorageManager(db=async_db_session)


@pytest.fixture
async def graph_pair(async_db_session: AsyncSession) -> tuple[object, object]:
    """Create a dashboard plus the graph its aggregates must reference.

    Names are unique per call: committed rows persist in the test database (see
    ``async_db_session``), so a fixed name would collide across tests.
    """
    suffix = uuid4().hex[:12]
    dashboard = await DashboardRepository().create(
        db=async_db_session,
        name=f"set_based_dashboard_{suffix}",
        description="PRF-10 set-based write",
    )
    graph = await GraphRepository().create(
        db=async_db_session,
        dashboard_id=dashboard.id,
        name=f"set_based_graph_{suffix}",
        type=GraphType.TABLE,
        config={},
        dimensions=["region"],
        metrics=["revenue"],
    )
    await async_db_session.commit()
    return dashboard, graph


def _aggregates(graph_id: object, count: int) -> list[dict]:
    """Build ``count`` hand-built aggregates with distinct dims."""
    return [
        {
            "graph_id": graph_id,
            "dims": {"region": str(index)},
            "metrics": {"revenue_sum": index},
        }
        for index in range(count)
    ]


@pytest.fixture
def statement_counter(async_test_engine: AsyncEngine) -> Iterator[list[str]]:
    """Count statements executed through this engine's connections.

    A ``before_cursor_execute`` listener appends each statement to a list; a
    test asserts on the count of statements whose text is an aggregate write.
    """
    statements: list[str] = []

    def _record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(async_test_engine.sync_engine, "before_cursor_execute", _record)
    try:
        yield statements
    finally:
        event.remove(
            async_test_engine.sync_engine, "before_cursor_execute", _record
        )


# --- 1. Statement count ---------------------------------------------------


@pytest.mark.asyncio
async def test_statement_count_is_at_or_below_derived_bound(
    manager: StorageManager,
    graph_pair: tuple[object, object],
    statement_counter: list[str],
) -> None:
    """An N-row save issues at most ``ceil(N / 16383) + 2`` aggregate statements.

    Pinned derived bound: ``ROWS_PER_STATEMENT = 65535 // 4 = 16383``. For the
    N below (20000 rows, one batch boundary) the bound is
    ``ceil(20000 / 16383) = 2`` aggregate statements, plus the two surrounding
    statements a clear-free APPEND issues (the graph-existence SELECT is a
    read, not an aggregate write, and is not counted).
    """
    dashboard, graph = graph_pair
    n = 20000
    old_chunk_count = (n + 999) // 1000  # ceil(N / 1000) under CHUNK_SIZE
    bound = (n + _DERIVED_ROWS_PER_STATEMENT - 1) // _DERIVED_ROWS_PER_STATEMENT

    statement_counter.clear()
    saved = await manager.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=_aggregates(graph.id, n),
        clear_old=False,
    )

    assert saved == n
    assert bound == 2
    aggregate_writes = [
        s for s in statement_counter if "INSERT INTO aggregated_data" in s
    ]
    assert len(aggregate_writes) <= bound
    # The old constant would have produced 20 statements; the new bound is two.
    assert len(aggregate_writes) < old_chunk_count


# --- 2. Upsert still upserts ----------------------------------------------


@pytest.mark.asyncio
async def test_same_dims_written_twice_is_one_row(
    manager: StorageManager,
    graph_pair: tuple[object, object],
    async_db_session: AsyncSession,
) -> None:
    """APPEND the same dims twice: the UPSERT merges onto one row."""
    dashboard, graph = graph_pair

    for _ in range(2):
        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[
                {
                    "graph_id": graph.id,
                    "dims": {"region": "A"},
                    "metrics": {"revenue_sum": 1},
                }
            ],
            clear_old=False,
        )

    rows = (
        await async_db_session.execute(
            select(AggregatedData).where(
                AggregatedData.dashboard_id == dashboard.id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].dims == {"region": "A"}


# --- 3. Empty selection ---------------------------------------------------


@pytest.mark.asyncio
async def test_empty_selection_with_and_without_clear_old(
    manager: StorageManager,
    graph_pair: tuple[object, object],
    async_db_session: AsyncSession,
) -> None:
    """An empty list clears under clear_old=True and preserves rows otherwise."""
    dashboard, graph = graph_pair
    await async_db_session.execute(
        AggregatedData.__table__.insert().values(
            dashboard_id=dashboard.id,
            graph_id=graph.id,
            dims={"region": "A"},
            metrics={"revenue_sum": 1},
        )
    )
    await async_db_session.commit()

    # Without clear_old an empty selection keeps the previous row.
    assert (
        await manager.save_aggregates(
            dashboard_id=dashboard.id, aggregates=[], clear_old=False
        )
        == 0
    )
    remaining = (
        await async_db_session.execute(
            select(AggregatedData).where(
                AggregatedData.dashboard_id == dashboard.id
            )
        )
    ).scalars().all()
    assert len(remaining) == 1

    # With clear_old an empty selection still clears.
    assert (
        await manager.save_aggregates(
            dashboard_id=dashboard.id, aggregates=[], clear_old=True
        )
        == 0
    )
    remaining = (
        await async_db_session.execute(
            select(AggregatedData).where(
                AggregatedData.dashboard_id == dashboard.id
            )
        )
    ).scalars().all()
    assert len(remaining) == 0


# --- 4. Overwrite then append ---------------------------------------------


@pytest.mark.asyncio
async def test_overwrite_then_append_is_one_row(
    manager: StorageManager,
    graph_pair: tuple[object, object],
    async_db_session: AsyncSession,
) -> None:
    """OVERWRITE the same dims, then APPEND it: one row survives."""
    dashboard, graph = graph_pair
    aggregate = [
        {
            "graph_id": graph.id,
            "dims": {"region": "B"},
            "metrics": {"revenue_sum": 1},
        }
    ]

    await manager.save_aggregates(
        dashboard_id=dashboard.id, aggregates=aggregate, clear_old=True
    )
    await manager.save_aggregates(
        dashboard_id=dashboard.id, aggregates=aggregate, clear_old=False
    )

    rows = (
        await async_db_session.execute(
            select(AggregatedData).where(
                AggregatedData.dashboard_id == dashboard.id
            )
        )
    ).scalars().all()
    assert len(rows) == 1


# --- 5. Hand-built aggregate through the same conflict target --------------


@pytest.mark.asyncio
async def test_hand_built_aggregate_lands_and_conflicts(
    manager: StorageManager,
    graph_pair: tuple[object, object],
    async_db_session: AsyncSession,
) -> None:
    """A hand-built aggregate -- bypassing the service -- still upserts.

    The write surface canonicalises ``dims`` itself, so a hand-built dict with a
    native-typed scalar still collides through the ``((dims)::text)`` conflict
    target rather than inserting a duplicate.
    """
    dashboard, graph = graph_pair

    await manager.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=[
            {"graph_id": graph.id, "dims": {"region": 1}, "metrics": {"v": 1}}
        ],
        clear_old=True,
    )
    await manager.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=[
            {"graph_id": graph.id, "dims": {"region": "1"}, "metrics": {"v": 2}}
        ],
        clear_old=False,
    )

    rows = (
        await async_db_session.execute(
            select(AggregatedData).where(
                AggregatedData.dashboard_id == dashboard.id
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].dims == {"region": "1"}


# --- 6. Across a batch boundary -------------------------------------------


@pytest.mark.asyncio
async def test_batch_larger_than_one_statement_capacity(
    manager: StorageManager,
    graph_pair: tuple[object, object],
    async_db_session: AsyncSession,
) -> None:
    """A save spanning several statements completes and upserts across the seam.

    ``ROWS_PER_STATEMENT + 7`` rows forces two statements. Writing the same set
    again must leave the row count unchanged, so the batch seam does not
    duplicate rows.
    """
    dashboard, graph = graph_pair
    n = _DERIVED_ROWS_PER_STATEMENT + 7
    aggregates = _aggregates(graph.id, n)

    saved = await manager.save_aggregates(
        dashboard_id=dashboard.id, aggregates=aggregates, clear_old=False
    )
    assert saved == n

    count = (
        await async_db_session.execute(
            select(func.count())
            .select_from(AggregatedData)
            .where(AggregatedData.dashboard_id == dashboard.id)
        )
    ).scalar_one()
    assert count == n

    # Re-write the same set: every row conflicts and updates, none duplicates.
    await manager.save_aggregates(
        dashboard_id=dashboard.id, aggregates=aggregates, clear_old=False
    )
    count = (
        await async_db_session.execute(
            select(func.count())
            .select_from(AggregatedData)
            .where(AggregatedData.dashboard_id == dashboard.id)
        )
    ).scalar_one()
    assert count == n
