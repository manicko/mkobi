"""Tests for StorageManager."""

from __future__ import annotations

import warnings

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from mkobi.db.models.aggregated_data import AggregatedData
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.models.enums import GraphType

from mkobi.data.storage.manager import StorageManager


@pytest.fixture
def manager(async_db_session: AsyncSession) -> StorageManager:
    """Create StorageManager instance."""
    return StorageManager(db=async_db_session)


@pytest.mark.asyncio
async def test_clear_graph_data(manager: StorageManager):
    """Test clear_graph_data method."""
    graph_id = uuid4()

    # Test deleting from empty table
    deleted = await manager.clear_graph_data(graph_id=graph_id)
    assert deleted == 0


@pytest.mark.asyncio
async def test_clear_graph_data_with_data(
    manager: StorageManager, async_db_session: AsyncSession
):
    """Test clear_graph_data method when actual data exists."""
    # Create a dashboard and graph to own the aggregated data
    dashboard_repo = DashboardRepository()
    dashboard = await dashboard_repo.create(
        db=async_db_session,
        name="test_dashboard",
        description="Test dashboard",
    )
    await async_db_session.commit()

    graph_repo = GraphRepository()
    graph = await graph_repo.create(
        db=async_db_session,
        dashboard_id=dashboard.id,
        name="test_graph",
        type=GraphType.TABLE,
        config={},
        dimensions=[],
        metrics=[],
    )
    await async_db_session.commit()

    # Insert aggregated data for the graph
    test_data = AggregatedData(
        dashboard_id=dashboard.id,
        graph_id=graph.id,
        dims={"category": "A"},
        metrics={"sales": 100},
    )
    async_db_session.add(test_data)
    await async_db_session.commit()

    # Verify data exists before deletion
    result = await async_db_session.execute(
        select(AggregatedData).where(
            AggregatedData.graph_id == graph.id
        )
    )
    assert len(result.scalars().all()) == 1

    # Clear graph data
    deleted = await manager.clear_graph_data(graph_id=graph.id)
    assert deleted == 1

    # Verify data is cleared
    result = await async_db_session.execute(
        select(AggregatedData).where(
            AggregatedData.graph_id == graph.id
        )
    )
    assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_clear_dashboard_data(manager: StorageManager):
    """Test clear_dashboard_data method."""
    dashboard_id = uuid4()

    # Test deleting from empty table
    deleted = await manager.clear_dashboard_data(dashboard_id=dashboard_id)
    assert deleted == 0


@pytest.mark.asyncio
async def test_clear_dashboard_data_with_data(
    manager: StorageManager, async_db_session: AsyncSession
):
    """Test clear_dashboard_data method when actual data exists."""
    # Create a dashboard and graph to own the aggregated data
    dashboard_repo = DashboardRepository()
    dashboard = await dashboard_repo.create(
        db=async_db_session,
        name="test_dashboard_clear",
        description="Test dashboard for clear",
    )
    await async_db_session.commit()

    graph_repo = GraphRepository()
    graph = await graph_repo.create(
        db=async_db_session,
        dashboard_id=dashboard.id,
        name="test_graph_clear",
        type=GraphType.TABLE,
        config={},
        dimensions=[],
        metrics=[],
    )
    await async_db_session.commit()

    # Insert aggregated data for the dashboard
    test_data = AggregatedData(
        dashboard_id=dashboard.id,
        graph_id=graph.id,
        dims={"category": "B"},
        metrics={"revenue": 200},
    )
    async_db_session.add(test_data)
    await async_db_session.commit()

    # Verify data exists before deletion
    result = await async_db_session.execute(
        select(AggregatedData).where(
            AggregatedData.dashboard_id == dashboard.id
        )
    )
    assert len(result.scalars().all()) == 1

    # Clear dashboard data
    deleted = await manager.clear_dashboard_data(dashboard_id=dashboard.id)
    assert deleted == 1

    # Verify data is cleared
    result = await async_db_session.execute(
        select(AggregatedData).where(
            AggregatedData.dashboard_id == dashboard.id
        )
    )
    assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_save_aggregates_empty_with_clear_old_still_clears(
    manager: StorageManager, async_db_session: AsyncSession
):
    """An empty list under clear_old=True must not return before the clear.

    DP-004: StorageManager.save_aggregates returned 0 at its ``if not
    aggregates:`` branch before its own ``clear_old: delete_by_dashboard``, so a
    caller that relied on the clear (and separately cleared filter values) was
    left with the previous aggregate rows still present. The clear now runs even
    for an empty list, so the method no longer silently skips it.
    """
    dashboard_repo = DashboardRepository()
    dashboard = await dashboard_repo.create(
        db=async_db_session,
        name="test_dashboard_empty_clear",
        description="Dashboard for empty clear_old test",
    )
    await async_db_session.commit()

    graph_repo = GraphRepository()
    graph = await graph_repo.create(
        db=async_db_session,
        dashboard_id=dashboard.id,
        name="test_graph_empty_clear",
        type=GraphType.TABLE,
        config={},
        dimensions=[],
        metrics=[],
    )
    await async_db_session.commit()

    async_db_session.add(
        AggregatedData(
            dashboard_id=dashboard.id,
            graph_id=graph.id,
            dims={"category": "A"},
            metrics={"sales": 100},
        )
    )
    await async_db_session.commit()

    # Sanity: the previous row exists before the empty overwrite.
    result = await async_db_session.execute(
        select(AggregatedData).where(AggregatedData.dashboard_id == dashboard.id)
    )
    assert len(result.scalars().all()) == 1

    saved = await manager.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=[],
        clear_old=True,
    )

    assert saved == 0

    # The clear ran: no previous rows survive an empty overwrite call.
    result = await async_db_session.execute(
        select(AggregatedData).where(AggregatedData.dashboard_id == dashboard.id)
    )
    assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_save_aggregates_empty_without_clear_old_keeps_rows(
    manager: StorageManager, async_db_session: AsyncSession
):
    """An empty list under clear_old=False keeps the previous rows."""
    dashboard_repo = DashboardRepository()
    dashboard = await dashboard_repo.create(
        db=async_db_session,
        name="test_dashboard_empty_append",
        description="Dashboard for empty append test",
    )
    await async_db_session.commit()

    graph_repo = GraphRepository()
    graph = await graph_repo.create(
        db=async_db_session,
        dashboard_id=dashboard.id,
        name="test_graph_empty_append",
        type=GraphType.TABLE,
        config={},
        dimensions=[],
        metrics=[],
    )
    await async_db_session.commit()

    async_db_session.add(
        AggregatedData(
            dashboard_id=dashboard.id,
            graph_id=graph.id,
            dims={"category": "A"},
            metrics={"sales": 100},
        )
    )
    await async_db_session.commit()

    saved = await manager.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=[],
        clear_old=False,
    )

    assert saved == 0

    result = await async_db_session.execute(
        select(AggregatedData).where(AggregatedData.dashboard_id == dashboard.id)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_clear_graph_data_compat_deprecated(async_db_session: AsyncSession):
    """Test clear_graph_data_compat emits deprecation warning."""
    graph_id = uuid4()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        deleted = await StorageManager.clear_graph_data_compat(
            graph_id=graph_id,
            db=async_db_session,
        )

    assert deleted == 0
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "clear_graph_data_compat" in str(w[0].message)


@pytest.mark.asyncio
async def test_clear_dashboard_data_compat_deprecated(async_db_session: AsyncSession):
    """Test clear_dashboard_data_compat emits deprecation warning."""
    dashboard_id = uuid4()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        deleted = await StorageManager.clear_dashboard_data_compat(
            dashboard_id=dashboard_id,
            db=async_db_session,
        )

    assert deleted == 0
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "clear_dashboard_data_compat" in str(w[0].message)


@pytest.mark.asyncio
async def test_save_aggregated_data_deprecated(async_db_session: AsyncSession):
    """Test save_aggregated_data emits deprecation warning."""
    from mkobi.models.enums import UploadMode

    dashboard_id = uuid4()
    graph_id = uuid4()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        await StorageManager.save_aggregated_data(
            dashboard_id=dashboard_id,
            graph_id=graph_id,
            aggregated_results=[],
            mode=UploadMode.OVERWRITE,
            db=async_db_session,
        )

    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "save_aggregated_data" in str(w[0].message)
