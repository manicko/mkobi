"""Tests for StorageManager."""

from __future__ import annotations

import datetime as dt
import inspect
import warnings
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from mkobi.db.models.aggregated_data import AggregatedData
from mkobi.db.repositories.aggregated_data_repo import AggregatedDataRepository
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


def _scalar_repr_type(value: object) -> str:
    """Name the Python type of a stored JSON scalar for the round-trip matrix.

    Read back through ``jsonb_typeof`` a JSON string is ``"string"``. Native
    numbers and booleans are not strings, and that difference is exactly what
    the canonicalisation removes.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


class TestDimsCanonicalisation:
    """DP-003: one category is one row -- the ``dims`` identity canonicalisation.

    Row identity is the unique index ``uq_aggregated_data_dashboard_graph_dims``
    on ``(dashboard_id, graph_id, dims::text)``; every write surface names the
    conflict target ``text("((dims)::text)")``. ``_normalize_json_keys`` sorted
    only the *keys*, leaving the *values* native, so the same five values
    serialised as ``{"region": "1"}`` when the column inferred ``Utf8`` and
    ``{"region": 1}`` when it inferred ``Int64``. Different text, no conflict
    match, a second row for one category, every chart total doubled.

    The rule (ruling ``D-05-E``): every scalar dimension value is stored as its
    ``str()``. It is applied at the storage layer -- ``_canonicalize_dims`` --
    because the conflict target is evaluated by PostgreSQL on the bytes about to
    be inserted, so that is the only placement where the index key and the
    stored value are provably identical for all three write surfaces.

    ``metrics`` are deliberately NOT canonicalised: numbers there are the data.
    """

    @staticmethod
    async def _make_graph(
        async_db_session: AsyncSession, name: str
    ) -> tuple[object, object]:
        """Create a dashboard + graph pair; the graph is required by the FK."""
        dashboard = await DashboardRepository().create(
            db=async_db_session,
            name=name,
            description="dims canonicalisation",
        )
        graph = await GraphRepository().create(
            db=async_db_session,
            dashboard_id=dashboard.id,
            name=f"{name}_graph",
            type=GraphType.TABLE,
            config={},
            dimensions=["region"],
            metrics=["revenue"],
        )
        await async_db_session.commit()
        return dashboard, graph

    @staticmethod
    def _agg(graph_id: object, dims: dict, metrics: dict | None = None) -> dict:
        """Build a hand-built aggregate dict, bypassing the service."""
        return {
            "graph_id": graph_id,
            "dims": dims,
            "metrics": metrics or {"revenue_sum": 1},
        }

    async def _stored_dims(
        self, async_db_session: AsyncSession, dashboard_id: object
    ) -> list[dict]:
        """Return ``dims`` for a dashboard in stored id order."""
        result = await async_db_session.execute(
            select(AggregatedData.dims)
            .where(AggregatedData.dashboard_id == dashboard_id)
            .order_by(AggregatedData.id)
        )
        return list(result.scalars().all())

    # --- 1. The reproduction -------------------------------------------------

    async def test_append_same_values_twice_is_one_row(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """Reproduction (DP-003): APPEND the same five values twice, one row.

        Once ``Utf8`` (``"1"``) and once ``Int64`` (``1``). Before the fix these
        serialise differently and the second append inserts a duplicate instead
        of colliding. After the fix the second append merges the first row.
        """
        dashboard, graph = await self._make_graph(
            async_db_session, "dims_reproduction"
        )

        for value in ("1", 1):
            await manager.save_aggregates(
                dashboard_id=dashboard.id,
                aggregates=[self._agg(graph.id, {"region": value})],
                clear_old=False,
            )

        stored = await self._stored_dims(async_db_session, dashboard.id)
        assert len(stored) == 1
        assert stored[0] == {"region": "1"}

    # --- 2. Both write paths and the mode switch -----------------------------

    async def test_overwrite_then_append_is_one_row(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """The mode-switch case a ``_bulk_upsert``-only fix misses.

        Write native-shaped input in OVERWRITE (``_bulk_insert``), then re-write
        the same logical value in APPEND (``_bulk_upsert``). If only the upsert
        path canonicalised, the overwrite would store ``1`` and the append
        ``"1"`` (or vice versa) and produce two rows.
        """
        dashboard, graph = await self._make_graph(async_db_session, "dims_mode_switch")

        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"region": 1})],
            clear_old=True,
        )
        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"region": "1"})],
            clear_old=False,
        )

        stored = await self._stored_dims(async_db_session, dashboard.id)
        assert len(stored) == 1
        assert stored[0] == {"region": "1"}

    # --- 3. Read path unaffected (the frontend range-slider) -----------------

    async def test_int_filter_value_reads_the_stored_row(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """A stored row is readable by ``get_by_graph_id`` with an int filter.

        The read path compares ``dims[key].astext == str(value)``; storing the
        string keeps that comparison true for a native int filter, which is the
        frontend range-slider case.
        """
        dashboard, graph = await self._make_graph(async_db_session, "dims_int_filter")

        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"region": 5})],
            clear_old=True,
        )

        rows = await AggregatedDataRepository().get_by_graph_id(
            graph_id=graph.id,
            db=async_db_session,
            dashboard_id=dashboard.id,
            filters={"region": 5},
        )
        assert len(rows) == 1
        assert rows[0].dims["region"] == "5"

    # --- 4. Boolean, three assertions with different answers -----------------

    async def test_boolean_readable_does_not_collide_with_one_and_merges_with_text(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """Three different answers on the same axis -- the difference is the point.

        (a) A boolean dim written after the change IS readable via
            ``get_by_graph_id`` (it is not today: jsonb ``true`` renders
            ``true``, not ``str(True)=="True"``).
        (b) A boolean dim does NOT collide with a ``0``/``1`` dim:
            ``"True"`` != ``"1"``, so two rows survive.
        (c) A boolean dim and a text dim whose literal is ``"True"`` now merge
            into one row -- recorded, not rediscovered later as a bug.
        """
        dashboard, graph = await self._make_graph(async_db_session, "dims_boolean")
        repo = AggregatedDataRepository()

        # (c) boolean True and the text "True" are one logical value.
        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"region": True})],
            clear_old=True,
        )
        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"region": "True"})],
            clear_old=False,
        )
        stored = await self._stored_dims(async_db_session, dashboard.id)
        assert len(stored) == 1
        assert stored[0] == {"region": "True"}

        # (a) the boolean row is readable by a boolean filter.
        rows = await repo.get_by_graph_id(
            graph_id=graph.id,
            db=async_db_session,
            dashboard_id=dashboard.id,
            filters={"region": True},
        )
        assert len(rows) == 1
        assert rows[0].dims["region"] == "True"

        # (b) a 1 (int) is a different value and survives as its own row.
        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"region": 1})],
            clear_old=False,
        )
        stored = await self._stored_dims(async_db_session, dashboard.id)
        assert len(stored) == 2
        assert {tuple(sorted(d.items())) for d in stored} == {
            (("region", "1"),),
            (("region", "True"),),
        }

    # --- 5. Float round-trip -------------------------------------------------

    async def test_float_values_are_readable(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """``1e-07`` and ``1e+22`` written after the change ARE readable.

        Both fail today: a ``Float64`` dim holding ``1e-07`` renders through
        ``numeric`` as ``0.0000001``, which is not ``str(1e-07) == '1e-07'``.
        Storing the value as a JSON string fixes it because ``->>`` on a JSON
        string returns the string unchanged.
        """
        dashboard, graph = await self._make_graph(async_db_session, "dims_float")
        repo = AggregatedDataRepository()

        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[
                self._agg(graph.id, {"region": 1e-07}),
                self._agg(graph.id, {"region": 1e22}),
            ],
            clear_old=True,
        )

        for value in (1e-07, 1e22):
            rows = await repo.get_by_graph_id(
                graph_id=graph.id,
                db=async_db_session,
                dashboard_id=dashboard.id,
                filters={"region": value},
            )
            assert len(rows) == 1
            assert rows[0].dims["region"] == str(value)

    # --- 6. Key-order independence (regression guard) ------------------------

    async def test_key_order_independence_is_one_row(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """The same logical dims with reordered keys collapse onto one row.

        Honest framing: this passes BEFORE and AFTER the change, because jsonb
        canonicalises key order itself. It is a regression guard on
        ``_normalize_json_keys``, not a demonstration that the sort provides
        index stability.
        """
        dashboard, graph = await self._make_graph(async_db_session, "dims_key_order")

        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"aa": 2, "b": 1})],
            clear_old=True,
        )
        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"b": 1, "aa": 2})],
            clear_old=False,
        )

        stored = await self._stored_dims(async_db_session, dashboard.id)
        assert len(stored) == 1
        assert stored[0] == {"aa": "2", "b": "1"}

    # --- 7. datetime keeps its isoformat separator ---------------------------

    async def test_datetime_dim_keeps_t_separator(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """A datetime dim's stored value keeps the ``T`` separator.

        Guards the ``str()``-instead-of-``isoformat()`` mistake: ``str()`` on a
        datetime gives ``'2024-01-01 00:00:00'`` and would silently re-space
        every stored datetime dimension.
        """
        dashboard, graph = await self._make_graph(async_db_session, "dims_datetime")
        moment = dt.datetime(2024, 1, 1, 12, 30, 0)

        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"region": moment})],
            clear_old=True,
        )

        stored = await self._stored_dims(async_db_session, dashboard.id)
        assert stored[0]["region"] == "2024-01-01T12:30:00"
        assert "T" in stored[0]["region"]

    # --- Round-trip invariant over the full scalar matrix --------------------

    async def test_full_matrix_round_trip_stored_value_and_read_back(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """Every scalar type stores ``str(filter_value)`` and reads back as str.

        The first half catches a rule that changed; the second catches a
        regression to native types. ``None`` canonicalises to ``""`` (not
        ``str(None) == "None"``), matching the pre-existing ``_coerce_dim_value``
        behaviour the read path already assumes -- so it is stored as the empty
        string but the read path's ``str(None) == "None"`` comparison does not
        select it. The read-back half therefore covers the scalars whose
        canonical form equals ``str(value)`` (numbers, booleans, strings); a
        date/datetime canonicalises through ``isoformat()`` and its own
        ``T``-separator test covers it.
        """
        dashboard, graph = await self._make_graph(async_db_session, "dims_matrix")
        repo = AggregatedDataRepository()
        matrix: list[tuple[str, object]] = [
            ("utf8", "5"),
            ("int64", 5),
            ("float64", 2.5),
            ("boolean", True),
            ("none", None),
            ("date", dt.date(2024, 1, 1)),
            ("datetime", dt.datetime(2024, 1, 1, 12, 30, 0)),
        ]

        for key, value in matrix:
            if value is None:
                expected = ""
            elif isinstance(value, (int, float, bool)):
                expected = str(value)
            elif hasattr(value, "isoformat"):
                # date/datetime canonicalise through isoformat(), keeping the T.
                expected = str(value.isoformat())
            else:
                expected = str(value)

            await manager.save_aggregates(
                dashboard_id=dashboard.id,
                aggregates=[self._agg(graph.id, {key: value})],
                clear_old=True,
            )
            stored = await self._stored_dims(async_db_session, dashboard.id)
            assert stored[0][key] == expected

            if value is None:
                continue

            # For every scalar except date/datetime the read path's
            # ``astext == str(value)`` comparison selects the stored string.
            if isinstance(value, (dt.date, dt.datetime)):
                continue

            rows = await repo.get_by_graph_id(
                graph_id=graph.id,
                db=async_db_session,
                dashboard_id=dashboard.id,
                filters={key: value},
            )
            assert len(rows) == 1
            assert isinstance(rows[0].dims[key], str)

    # --- The tripwire --------------------------------------------------------

    async def test_hand_built_aggregates_are_one_row_on_all_three_sites(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """Behavioural tripwire across all three write surfaces at once.

        Hand-built aggregate dicts bypass ``aggregate_for_dashboard`` entirely
        and pass through ``save_aggregates(clear_old=True)`` (``_bulk_insert``),
        ``save_aggregates(clear_old=False)`` (``_bulk_upsert``) and
        ``upsert_aggregate``. If someone canonicalises one call site and not the
        others, this test fails because the differing representations no longer
        collapse onto one row.
        """
        dashboard, graph = await self._make_graph(async_db_session, "dims_tripwire")

        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"region": 1})],
            clear_old=True,
        )
        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[self._agg(graph.id, {"region": "1"})],
            clear_old=False,
        )
        await manager.upsert_aggregate(
            dashboard_id=dashboard.id,
            graph_id=graph.id,
            dims={"region": 1},
            metrics={"revenue_sum": 1},
        )

        stored = await self._stored_dims(async_db_session, dashboard.id)
        assert len(stored) == 1
        assert stored[0] == {"region": "1"}

    def test_conflict_target_is_identical_on_every_site(self) -> None:
        """Source-level guard: every conflict target names ``((dims)::text)``.

        Precedent: ``tests/test_rq_worker.py::TestRegisteredJobCallable`` and
        ``tests/test_app_lifespan.py`` both use ``inspect.getsource``. Every
        ``on_conflict_do_update`` in ``data/storage/manager.py`` must be preceded
        by the same ``index_elements`` list containing ``text("((dims)::text)")``,
        so a hand-edited call site cannot silently diverge from the index.
        """
        # Read the whole file rather than inspect.getsource(StorageManager) so
        # the assertion is not exposed to linecache staleness for a class whose
        # source spans the snippet boundary.
        source_path = Path(inspect.getfile(StorageManager))
        source = source_path.read_text(encoding="utf-8")
        marker = "on_conflict_do_update"
        # Exactly two live conflict surfaces carry the clause: ``_bulk_upsert``
        # and ``upsert_aggregate``. ``_bulk_insert`` has no ON CONFLICT by
        # design (it is the OVERWRITE path); its canonicalisation is what makes
        # a later APPEND collide. Guard both, not three.
        assert source.count(marker) == 2

        for block in source.split(marker)[1:]:
            window = block.split("set_=", 1)[0]
            assert "index_elements" in window
            assert 'text("((dims)::text)")' in window

    # --- Stored representation is a JSON string ------------------------------

    async def test_stored_scalars_are_json_strings(
        self, manager: StorageManager, async_db_session: AsyncSession
    ) -> None:
        """The stored representation of every scalar dim is a JSON string.

        Read through ``jsonb_typeof``: native numbers and booleans are not
        strings, which is the second half of the round-trip invariant and the
        regression guard against native types returning.
        """
        dashboard, graph = await self._make_graph(async_db_session, "dims_json_type")

        await manager.save_aggregates(
            dashboard_id=dashboard.id,
            aggregates=[
                self._agg(
                    graph.id,
                    {"i": 1, "f": 2.5, "b": True, "n": None, "s": "x", "d": 1e-07},
                )
            ],
            clear_old=True,
        )

        result = await async_db_session.execute(
            text(
                "SELECT jsonb_typeof(dims -> 'i'), jsonb_typeof(dims -> 'f'), "
                "jsonb_typeof(dims -> 'b'), jsonb_typeof(dims -> 'n'), "
                "jsonb_typeof(dims -> 's'), jsonb_typeof(dims -> 'd') "
                "FROM aggregated_data WHERE dashboard_id = :dashboard_id"
            ),
            {"dashboard_id": dashboard.id},
        )
        row = result.one()
        assert list(row) == ["string"] * 6
        assert _scalar_repr_type(2.5) == "number"
