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
    async_db_session, owner_id: UUID, *, rows: int
) -> tuple[UUID, UUID]:
    """Create a dashboard, one graph and ``rows`` aggregated records.

    Returns the dashboard id and graph id. Enough relationships exist on the
    dashboard (layout, accesses, processing config, logs, filter values, ...)
    that the nine ``selectin`` queries are all exercised by a read.
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
        for i in range(rows)
    ]
    await storage.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=aggregates,
        clear_old=True,
    )
    await async_db_session.commit()

    return dashboard.id, graph.id


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
        ordering snapshot. ``layout`` stays ``None``: the audit found
        ``GraphDataResponse.layout`` is never populated, and this phase does not
        start populating it.
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
            "graph_id", "type", "name", "data",
            "returned_rows", "total_rows", "rows_truncated", "layout", "config",
        }
        assert graph["graph_id"] == str(graph_id)
        assert graph["type"] == "bar"
        assert graph["name"] == "Aggregate Read Graph"
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
