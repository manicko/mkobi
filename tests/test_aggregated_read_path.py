"""PRF-3: the aggregate read must not materialise what the response discards.

The defect: ``AggregatedData.dashboard`` and ``AggregatedData.graph`` are
``lazy="selectin"``, so reading a dashboard's aggregates cascades into
``Dashboard``'s nine ``selectin`` relationships, and the repository returns ORM
entities whose relationships are eagerly loaded even though the response
serialises only ``graph_id``, ``type``, ``name``, ``config`` and the JSONB
payload. The read path issued 17 SQL statements at 12,500 and 50,000 rows --
structural, not per-row -- and 14 of those 17 came from the ``Dashboard``
cascade.

The fix de-emphasises those relationships **scoped to the aggregate read query**
(SQLAlchemy loader options), leaving the model-level ``lazy`` defaults untouched
for the config/admin read paths, and stops the service building the discarded
per-row intermediate. The endpoint's JSON output is unchanged.

Statement count
---------------
``TestAggregateReadStatementCount`` pins an engine-level tripwire. The ceiling
is the statement count measured **after** the fix, not a vague "fewer than
before". Before the fix the read issued 17 statements; after the fix it issues
the ceiling named in that test's docstring.
"""

from uuid import UUID, uuid4

from fastapi import status
from httpx import AsyncClient

from mkobi.data.storage.manager import StorageManager
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.models.enums import DashboardPermission
from mkobi.services.dashboard_service import DashboardService
from mkobi.services.graph_service import GraphService
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.models.graph import GraphCreate


async def _setup_dashboard_with_aggregates(
    async_db_session,
    owner_id: UUID,
    *,
    rows: int,
    metric_keys: tuple[str, ...] = ("revenue",),
) -> tuple[UUID, UUID]:
    """Create a dashboard, one graph and ``rows`` aggregated records.

    Returns the dashboard id and graph id. Enough relationships exist on the
    dashboard (layout, accesses, processing config, logs, filter values, ...)
    that the nine ``selectin`` queries are all exercised by a read.

    ``metric_keys`` names the metric keys stored on every row and declared on
    the graph. The default reproduces the previous single-metric output exactly.
    """
    ds = DashboardService(DashboardRepository(), AccessRepository())
    dashboard = await ds.create_dashboard(
        name=f"agg-read-path-{uuid4().hex[:8]}",
        config={"graph_types": ["bar"]},
        owner_id=owner_id,
        db=async_db_session,
    )

    graph = await GraphService(GraphRepository()).create(
        GraphCreate(
            name="Aggregate Read Graph",
            type="bar",
            dashboard_id=dashboard.id,
            config={"title": "Revenue"},
            dimensions=["category"],
            metrics=list(metric_keys),
        ),
        db=async_db_session,
    )

    await AccessRepository().grant_access(
        db=async_db_session,
        user_id=owner_id,
        dashboard_id=dashboard.id,
        permission=DashboardPermission.VIEW,
    )
    await async_db_session.commit()

    storage = StorageManager(db=async_db_session)
    aggregates = [
        {
            "graph_id": graph.id,
            "dims": {"category": f"cat-{i}"},
            "metrics": {key: 100 + i for key in metric_keys},
        }
        for i in range(rows)
    ]
    await storage.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=aggregates,
        clear_old=True,
    )
    await async_db_session.commit()

    return dashboard.id, graph.id


async def _setup_dashboard_with_two_layout_graphs(
    async_db_session, owner_id: UUID
) -> tuple[UUID, UUID, UUID]:
    """Create a dashboard with two bar graphs and rows for each.

    Graph A stores a full layout under ``config["layout"]``; graph B stores
    config-level ``xaxis`` / ``yaxis`` and **no** ``layout`` key. The pair pins
    the served layout against the stored column and pins that config-level axis
    keys are not lifted into it.

    Returns ``(dashboard_id, graph_a_id, graph_b_id)``.
    """
    ds = DashboardService(DashboardRepository(), AccessRepository())
    dashboard = await ds.create_dashboard(
        name=f"served-layout-{uuid4().hex[:8]}",
        config={"graph_types": ["bar"]},
        owner_id=owner_id,
        db=async_db_session,
    )

    graph_service = GraphService(GraphRepository())
    graph_a = await graph_service.create(
        GraphCreate(
            name="Layout Graph A",
            type="bar",
            dashboard_id=dashboard.id,
            config={
                "layout": {
                    "title": "Stored Layout",
                    "xaxis": {
                        "title": "Category",
                        "type": "category",
                        "range": [0, 10],
                    },
                    "yaxis": {"title": "Revenue", "type": "linear"},
                    "showlegend": True,
                    "height": 480,
                    "width": 640,
                    "template": "plotly_white",
                },
            },
            dimensions=["category"],
            metrics=["revenue"],
        ),
        db=async_db_session,
    )
    graph_b = await graph_service.create(
        GraphCreate(
            name="Config Axis Graph B",
            type="bar",
            dashboard_id=dashboard.id,
            config={
                "xaxis": {"title": "Config X", "type": "category"},
                "yaxis": {"title": "Config Y", "type": "linear"},
            },
            dimensions=["category"],
            metrics=["revenue"],
        ),
        db=async_db_session,
    )

    await AccessRepository().grant_access(
        db=async_db_session,
        user_id=owner_id,
        dashboard_id=dashboard.id,
        permission=DashboardPermission.VIEW,
    )
    await async_db_session.commit()

    storage = StorageManager(db=async_db_session)
    aggregates = [
        {
            "graph_id": graph.id,
            "dims": {"category": f"cat-{i}"},
            "metrics": {"revenue": 100 + i},
        }
        for graph in (graph_a, graph_b)
        for i in range(2)
    ]
    await storage.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=aggregates,
        clear_old=True,
    )
    await async_db_session.commit()

    return dashboard.id, graph_a.id, graph_b.id


# Graph A's stored layout, written out by hand rather than derived from
# ``ChartLayoutConfig.__annotations__`` or a source constant. The literal is the
# pin: a derivation would drift silently with the source it guards.
SERVED_LAYOUT_A: dict[str, object] = {
    "title": "Stored Layout",
    "xaxis": {"title": "Category", "type": "category", "range": [0, 10]},
    "yaxis": {"title": "Revenue", "type": "linear"},
    "showlegend": True,
    "height": 480,
    "width": 640,
    "template": "plotly_white",
}


class _StatementCounter:
    """Engine-level ``before_cursor_execute`` listener counting statements."""

    def __init__(self, sync_engine) -> None:
        self._engine = sync_engine
        self.statements: list[str] = []

    def __enter__(self):
        from sqlalchemy import event

        @event.listens_for(self._engine, "before_cursor_execute")
        def _record(conn, cursor, statement, parameters, context, executemany):
            self.statements.append(statement)

        self._remove = lambda: event.remove(
            self._engine, "before_cursor_execute", _record
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        self._remove()
        return False

    def count_matching(self, needle: str) -> int:
        """Statements whose text contains ``needle`` (case-insensitive)."""
        lowered = needle.lower()
        return sum(1 for s in self.statements if lowered in s.lower())


class TestAggregateReadStatementCount:
    """The read path must not fire the dashboard's nine selectin queries.

    The count is taken around the service read directly, not the whole HTTP
    request: the endpoint's dashboard access-control check queries
    ``dashboard_access`` on its own, and counting that would conflate the
    permission path with the ORM cascade this phase removes.
    """

    async def test_read_does_not_cascade_into_dashboard_relationships(
        self, async_db_session, test_user: dict
    ) -> None:
        """The service aggregate read issues no more than the pinned ceiling.

        Measured after the fix: the single-graph aggregate read issues **1**
        statement -- one ``aggregated_data`` select projecting only the five
        columns the response consumes, with ``ORDER BY aggregated_data.id``
        preserved. Before the fix the same read issued **12** statements, 10 of
        them from the ``Dashboard`` and ``Graph`` ``selectin`` cascades. The
        ceiling below is the measured post-fix number; the assertion is a
        ceiling, so a future regression that re-introduces any eager
        relationship fails it.
        """
        from mkobi.db.repositories.aggregated_data_repo import (
            AggregatedDataRepository,
        )
        from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository
        from mkobi.services.data_service import DataService

        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=5
        )

        service = DataService(
            agg_repo=AggregatedDataRepository(),
            log_repo=ProcessingLogRepository(),
            graph_repo=GraphRepository(),
        )

        sync_engine = async_db_session.bind.sync_engine
        with _StatementCounter(sync_engine) as counter:
            result = await service.get_aggregated_data(
                dashboard_id=dashboard_id, graph_id=graph_id, db=async_db_session
            )

        assert len(result) == 5

        # The nine dashboard relationships (accesses, users, layout, graphs,
        # aggregated_data, filters, processing_config, processing_logs,
        # filter_values) are each a selectin query against their own table. A
        # fixed relationship whose table select disappears proves the cascade is
        # gone.
        for table in (
            "dashboard_access",
            "dashboard_filters",
            "processing_config",
            "processing_logs",
            "dashboard_filter_values",
            "dashboards",
        ):
            assert counter.count_matching(f"FROM {table}") == 0, (
                f"aggregate read still selects {table} via a Dashboard selectin"
            )

        # Pinned ceiling: the post-fix statement count, fixed as a number. The
        # prior count was 12; a ceiling of 1 admits exactly the single
        # aggregated-data select and nothing else.
        assert len(counter.statements) <= 1, (
            f"aggregate read issued {len(counter.statements)} statements, "
            f"ceiling is 1"
        )

    async def test_read_all_graphs_does_not_cascade(
        self, async_db_session, test_user: dict
    ) -> None:
        """The all-graphs read path (per graph) also avoids the cascade."""
        from mkobi.db.repositories.aggregated_data_repo import (
            AggregatedDataRepository,
        )
        from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository
        from mkobi.services.data_service import DataService

        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=3
        )

        service = DataService(
            agg_repo=AggregatedDataRepository(),
            log_repo=ProcessingLogRepository(),
            graph_repo=GraphRepository(),
        )

        sync_engine = async_db_session.bind.sync_engine
        with _StatementCounter(sync_engine) as counter:
            result = await service.get_aggregated_data(
                dashboard_id=dashboard_id, graph_id=graph_id, db=async_db_session
            )

        assert len(result) == 3
        for table in (
            "dashboard_access",
            "dashboard_filters",
            "processing_config",
            "processing_logs",
            "dashboard_filter_values",
            "dashboards",
        ):
            assert counter.count_matching(f"FROM {table}") == 0


class TestAggregateResponseShape:
    """The endpoint's output shape is unchanged by the read-path fix."""

    async def test_single_graph_response_has_expected_shape(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The single-graph response keeps its structural shape and payload.

        Structural comparison against the expected keys, not an incidental
        ordering snapshot. This fixture's graph stores ``config={"title":
        "Revenue"}`` with no ``layout`` key, so ``layout`` stays ``None`` even
        though the field is now populated from the stored config on every
        response.
        """
        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=2
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()

        assert set(body.keys()) == {"graphs", "total_rows", "truncated"}
        assert len(body["graphs"]) == 1
        graph = body["graphs"][0]
        assert set(graph.keys()) == {
            "graph_id", "type", "name", "data", "metrics", "dimensions",
            "returned_rows", "total_rows", "rows_truncated", "layout", "config",
        }
        assert graph["graph_id"] == str(graph_id)
        assert graph["type"] == "bar"
        assert graph["name"] == "Aggregate Read Graph"
        # The served key lists name the row's own shape: measure and axis.
        assert graph["metrics"] == ["revenue"]
        assert graph["dimensions"] == ["category"]
        assert graph["config"] == {"title": "Revenue"}
        assert graph["layout"] is None
        # Two stored rows: under both caps, so nothing is truncated.
        assert body["truncated"] is False
        assert body["total_rows"] == 2
        # DP-13-C: the server supplies the returned-row count the client
        # renders; it is not the client's `data.length`.
        assert graph["returned_rows"] == 2
        assert graph["total_rows"] == 2
        assert graph["rows_truncated"] is False

        # Two rows were stored; each row is one data point whose dict is the
        # merge of dims and metrics.
        data_points = graph["data"]
        assert len(data_points) == 2
        categories = sorted(point["category"] for point in data_points)
        assert categories == ["cat-0", "cat-1"]
        for point in data_points:
            assert set(point.keys()) == {"category", "revenue"}


class TestServedRowKeys:
    """R3 / ``CHTB-2``: the response names the served measure and dimension keys.

    ``convertToPlotlyData`` guesses the measure column (``config.metrics?.[0]``)
    and the axis column (``config.x``), and when the guess misses every point
    renders as ``0`` under correct category labels. These tests pin the served
    ``metrics`` / ``dimensions`` lists -- read off the stored rows -- as the
    unambiguous description of the row's own shape. The lists are computed in
    ``DataService.get_bounded_aggregated_data`` and passed through at both route
    construction sites; the derivation is never re-run from ``config``.
    """

    async def test_served_measure_name_is_a_key_on_the_served_row(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The served measure name is a key on every served row, not ``revenue_sum``."""
        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=2
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]

        served = set(graph["metrics"])
        assert served, "a graph with rows must name its measure"
        assert graph["data"], "the fixture stored rows"
        # Stronger than intersecting one row: the served measure names are a
        # subset of the keys of *every* served row.
        for row in graph["data"]:
            assert served <= set(row), (
                f"served measure names {served} are not keys on row {row}"
            )
        # The stored row is keyed ``revenue`` (not ``revenue_sum``): re-deriving
        # the ``_{metric_agg}`` name from config would serve a name on no row.
        assert graph["metrics"] == ["revenue"]

    async def test_served_dimension_names_are_keys_on_the_served_row(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The symmetric half: served dimension names are keys on every row."""
        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=2
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]

        assert graph["dimensions"] == ["category"]
        served = set(graph["dimensions"])
        assert served
        for row in graph["data"]:
            assert served <= set(row), (
                f"served dimension names {served} are not keys on row {row}"
            )

    async def test_served_names_are_unaffected_by_the_current_metric_agg(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Flipping ``metric_agg`` after the rows were stored does not rename them.

        Precondition: ``metric_agg`` is mutable without re-aggregation --
        ``ProcessingConfigService.upsert`` writes it and returns, reachable from
        ``PUT /processing-configs/{dashboard_id}``. A derivation that re-applied
        the naming rule would then serve ``revenue_mean``, absent from every
        stored row.
        """
        from mkobi.db.repositories.processing_config_repo import (
            ProcessingConfigRepository,
        )
        from mkobi.models.types import ProcessingSettingsModel
        from mkobi.services.processing_config_service import ProcessingConfigService

        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=2
        )

        await ProcessingConfigService(ProcessingConfigRepository()).upsert(
            dashboard_id=dashboard_id,
            db=async_db_session,
            settings=ProcessingSettingsModel(),
            metric_agg="mean",
        )
        await async_db_session.commit()

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]

        assert graph["metrics"] == ["revenue"]
        assert "revenue_mean" not in graph["metrics"]

    async def test_zero_row_graph_serves_empty_key_lists(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A graph with no stored rows appears with ``[]`` key lists, not absent.

        The endpoint enumerates the ``graphs`` table, so a zero-row graph is
        present with an empty ``data`` list and an honest ``[]`` for both key
        lists -- never ``None`` and never a fabricated name.
        """
        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=0
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()

        graphs = {entry["graph_id"]: entry for entry in body["graphs"]}
        assert str(graph_id) in graphs, "the zero-row graph is present, not absent"
        entry = graphs[str(graph_id)]
        assert entry["data"] == []
        assert entry["returned_rows"] == 0
        assert entry["metrics"] == []
        assert entry["dimensions"] == []

    async def test_both_response_branches_serve_the_same_key_lists(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The all-graphs and single-graph branches serve identical key lists.

        A change applied at only one construction site is invisible without
        this: the all-graphs loop and the single-graph branch must agree.
        """
        dashboard_id, graph_a_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=2
        )
        _, graph_b_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=3
        )
        graph_b = await GraphRepository().get(id=graph_b_id, db=async_db_session)
        assert graph_b is not None
        graph_b.dashboard_id = dashboard_id
        graph_b.name = "Aggregate Read Graph B"
        await async_db_session.commit()

        all_response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id)},
        )
        assert all_response.status_code == status.HTTP_200_OK
        all_entries = {
            entry["graph_id"]: entry for entry in all_response.json()["graphs"]
        }

        single_a = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_a_id)},
        )
        single_b = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_b_id)},
        )
        assert single_a.status_code == status.HTTP_200_OK
        assert single_b.status_code == status.HTTP_200_OK

        for graph_id, single_response in (
            (graph_a_id, single_a),
            (graph_b_id, single_b),
        ):
            single = single_response.json()["graphs"][0]
            all_entry = all_entries[str(graph_id)]
            assert single["metrics"] == all_entry["metrics"]
            assert single["dimensions"] == all_entry["dimensions"]

    async def test_every_metric_key_of_a_multi_metric_graph_is_served(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Both stored metric keys are served, not only the first.

        Guards against an implementation that serves ``metrics[0]`` only -- the
        exact ``[0]`` bug class the renderer has. The expected order is the
        stored row's own key order (``metrics`` are key-sorted on write), which
        the served list must match rather than reorder.
        """
        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session,
            test_user["id"],
            rows=2,
            metric_keys=("revenue", "profit"),
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]

        assert set(graph["metrics"]) == {"revenue", "profit"}
        # The served order is the served row's key order, not a guess.
        assert graph["metrics"] == list(graph["data"][0].keys())[1:]
        for row in graph["data"]:
            assert set(graph["metrics"]) <= set(row)

    async def test_served_keys_ignore_a_config_metric_no_row_carries(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The served list reports the row's real keys, not the config's guess.

        The actual ``CHT-001`` failure mode: ``config["metrics"]`` names a column
        no stored row carries. The served list must equal the row's real keys.

        This does **not** fix the renderer: ``config.metrics[0]`` still points at
        a missing key and ``convertToPlotlyData`` still collapses to ``0``. The
        ``?? 0`` collapse and the nameable-vs-known gap are ``R4``'s and
        ``R6``'s.
        """
        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=2
        )

        # The graph's config names a measure that no stored row carries.
        graph_repo = GraphRepository()
        stored_graph = await graph_repo.get(id=graph_id, db=async_db_session)
        assert stored_graph is not None
        stored_graph.config = {**stored_graph.config, "metrics": ["ghost_metric"]}
        await async_db_session.commit()

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]

        assert graph["metrics"] == ["revenue"]
        assert "ghost_metric" not in graph["metrics"]
        assert "revenue" in graph["data"][0]

    async def test_service_returns_the_served_key_lists(
        self, async_db_session, test_user: dict
    ) -> None:
        """The 4-tuple carries the key unions in the pinned positions.

        A service-level pin by position: a silent reorder or a same-typed swap
        of the third and fourth elements fails here.
        """
        from mkobi.db.repositories.aggregated_data_repo import (
            AggregatedDataRepository,
        )
        from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository
        from mkobi.services.data_service import DataService

        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=3
        )

        service = DataService(
            agg_repo=AggregatedDataRepository(),
            log_repo=ProcessingLogRepository(),
            graph_repo=GraphRepository(),
        )

        records, total_rows, metric_keys, dimension_keys = (
            await service.get_bounded_aggregated_data(
                dashboard_id=dashboard_id,
                graph_id=graph_id,
                db=async_db_session,
                max_rows=10,
            )
        )

        assert total_rows == 3
        assert metric_keys == ["revenue"]
        assert dimension_keys == ["category"]
        # The served keys really are keys on the served records.
        served_rows = [record["preview"][0] for record in records]
        for row in served_rows:
            assert set(metric_keys) <= set(row)
            assert set(dimension_keys) <= set(row)



class TestServedGraphLayout:
    """CHT-006: the served ``layout`` is the graph's stored ``config["layout"]``.

    Both construction sites in ``get_aggregated_data_endpoint`` pass it, so a
    stored layout reaches the client. Decision 1 of residual block ``R2`` serves
    that column **verbatim**: config-level ``xaxis`` / ``yaxis`` / ``title`` /
    ``showlegend`` are not lifted into it, and that non-lifting is pinned here
    so a later block that does lift fails loudly.
    """

    async def test_single_graph_branch_serves_the_stored_layout_verbatim(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The single-graph branch serves graph A's stored layout as stored."""
        dashboard_id, graph_a_id, _graph_b_id = (
            await _setup_dashboard_with_two_layout_graphs(
                async_db_session, test_user["id"]
            )
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_a_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]

        assert graph["layout"] == SERVED_LAYOUT_A
        # Additive change: the stored config is still served untouched.
        assert graph["config"] == {"layout": SERVED_LAYOUT_A}

    async def test_all_graphs_branch_serves_the_stored_layout_verbatim(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The all-graphs branch serves A's layout and B's ``None``."""
        dashboard_id, graph_a_id, graph_b_id = (
            await _setup_dashboard_with_two_layout_graphs(
                async_db_session, test_user["id"]
            )
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        entries = {entry["graph_id"]: entry for entry in response.json()["graphs"]}

        assert entries[str(graph_a_id)]["layout"] == SERVED_LAYOUT_A
        assert entries[str(graph_b_id)]["layout"] is None

    async def test_config_level_axis_keys_are_not_lifted_into_layout(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Graph B's ``config["xaxis"]`` is served in ``config`` but not lifted."""
        dashboard_id, _graph_a_id, graph_b_id = (
            await _setup_dashboard_with_two_layout_graphs(
                async_db_session, test_user["id"]
            )
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_b_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]

        # The fixture really carries the config-level axis ...
        assert graph["config"]["xaxis"] == {
            "title": "Config X",
            "type": "category",
        }
        # ... and Decision 1 means it is deliberately not lifted into layout.
        assert graph["layout"] is None


class TestAggregateGraphScoping:
    """AZ-8: a supplied ``graph_id`` is scoped to the named ``dashboard_id``.

    The defect: the endpoint resolved ``graph_repo.get(id=graph_id)`` with no
    dashboard constraint, so a caller with access to dashboard A could pass
    dashboard B's ``graph_id`` to A's endpoint. The parent-dashboard
    authorization already ran before the lookup, so the fix only adds the
    belonging assertion; it must stay *after* that authorization or the endpoint
    becomes a graph-existence oracle for dashboards the caller cannot read.
    """

    async def test_graph_of_another_dashboard_is_refused(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A and B are readable by the same caller; A's endpoint must refuse B's graph."""
        dashboard_a, _graph_a = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=1
        )
        dashboard_b, graph_b = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=1
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_a), "graph_id": str(graph_b)},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "GRAPH_NOT_FOUND"

    async def test_legitimate_pair_still_returns_its_rows(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The matching pair is unchanged: the same rows as before this fix."""
        dashboard_id, graph_id = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=3
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_id)},
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert len(body["graphs"]) == 1
        assert body["graphs"][0]["graph_id"] == str(graph_id)
        assert len(body["graphs"][0]["data"]) == 3
        assert body["total_rows"] == 3

    async def test_caller_without_access_to_named_dashboard_is_refused_first(
        self, async_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The caller cannot read B; naming B's dashboard is refused before any graph lookup."""
        from mkobi.core.security import create_access_token
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        dashboard_b, graph_b = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows=1
        )

        outsider = await UserRepository().create(
            db=async_db_session,
            email=f"az8_outsider_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        assert outsider is not None
        await async_db_session.flush()
        token = create_access_token(
            {"user_id": str(outsider.id), "email": outsider.email}
        )

        # The outsider has no grant on B and asks for B's graph on B's endpoint.
        # The response must be a refusal, and must not be GRAPH_NOT_FOUND: the
        # graph exists, and the authorization runs first, so the endpoint is not
        # an existence oracle. The refusal code is normalized to PERMISSION_DENIED
        # by the AZ-11 work item; this test pins the status and that the refusal
        # is not the graph-not-found branch.
        response = await async_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_b), "graph_id": str(graph_b)},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["code"] != "GRAPH_NOT_FOUND"
