"""PERF-001: the aggregate read is bounded and truncation is visible.

An uncapped read allocates roughly 3,402 B/row and crosses the application's
1 GiB cgroup limit between 250k and 300k rows. These tests pin the two caps
(``max_rows_per_graph`` and ``max_rows_total``), the visible-truncation
contract (``DP-11-B``), and the ``ORDER BY id`` determinism a capped read must
keep.
"""

from uuid import UUID, uuid4

from fastapi import status
from httpx import AsyncClient

from mkobi.data.storage.manager import StorageManager
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.models.enums import DashboardPermission
from mkobi.models.graph import GraphCreate
from mkobi.services.dashboard_service import DashboardService
from mkobi.services.graph_service import GraphService


async def _setup_dashboard_with_aggregates(
    async_db_session, owner_id: UUID, *, rows_per_graph: dict[str, int]
) -> tuple[UUID, dict[str, UUID]]:
    """Create a dashboard with named graphs and a set row count each.

    ``rows_per_graph`` maps a graph name to its row count; returns the dashboard
    id and a name -> graph id mapping.
    """
    ds = DashboardService(DashboardRepository(), AccessRepository())
    dashboard = await ds.create_dashboard(
        name=f"agg-caps-{uuid4().hex[:8]}",
        config={"graph_types": ["bar"]},
        owner_id=owner_id,
        db=async_db_session,
    )

    graph_service = GraphService(GraphRepository())
    graph_ids: dict[str, UUID] = {}
    for name in rows_per_graph:
        graph = await graph_service.create(
            GraphCreate(
                name=name,
                type="bar",
                dashboard_id=dashboard.id,
                config={"title": name},
                dimensions=["category"],
                metrics=["revenue"],
            ),
            db=async_db_session,
        )
        graph_ids[name] = graph.id

    await AccessRepository().grant_access(
        db=async_db_session,
        user_id=owner_id,
        dashboard_id=dashboard.id,
        permission=DashboardPermission.VIEW,
    )
    await async_db_session.commit()

    # One call with ``clear_old=True``: the flag clears the *whole dashboard*,
    # so per-graph calls would wipe each other's rows.
    storage = StorageManager(db=async_db_session)
    aggregates: list[dict[str, object]] = []
    for name, count in rows_per_graph.items():
        aggregates.extend(
            {
                "graph_id": graph_ids[name],
                "dims": {"category": f"{name}-cat-{i}"},
                "metrics": {"revenue": 100 + i},
            }
            for i in range(count)
        )
    await storage.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=aggregates,
        clear_old=True,
    )
    await async_db_session.commit()

    return dashboard.id, graph_ids


class TestAggregateRowCaps:
    """The read is bounded and the bound is visible, never silent."""

    async def test_no_silent_truncation(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Over the cap: total exceeds returned rows and ``truncated`` is true."""
        from mkobi.config import get_config

        caps = get_config().data
        dashboard_id, graph_ids = await _setup_dashboard_with_aggregates(
            async_db_session,
            test_user["id"],
            rows_per_graph={"Big": caps.max_rows_per_graph + 50},
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_ids["Big"])},
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()

        assert body["total_rows"] == caps.max_rows_per_graph + 50
        assert body["truncated"] is True
        graph = body["graphs"][0]
        assert graph["total_rows"] == caps.max_rows_per_graph + 50
        assert graph["rows_truncated"] is True
        assert len(graph["data"]) == caps.max_rows_per_graph

    async def test_bound_respected_per_graph_and_total(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Above both caps: at most the per-graph and the total bound come back."""
        from mkobi.config import get_config

        caps = get_config().data
        per_graph = caps.max_rows_per_graph
        graph_count = 4
        dashboard_id, _ = await _setup_dashboard_with_aggregates(
            async_db_session,
            test_user["id"],
            rows_per_graph={
                f"G{i}": per_graph + 10 for i in range(graph_count)
            },
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()

        returned_per_graph = [len(g["data"]) for g in body["graphs"]]
        assert all(n <= per_graph for n in returned_per_graph)
        total_returned = sum(returned_per_graph)
        assert total_returned <= caps.max_rows_total
        assert body["truncated"] is True
        # The grand total still reports every stored row.
        assert body["total_rows"] == graph_count * (per_graph + 10)

    async def test_under_the_cap_is_unchanged(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Below both caps: every row comes back and ``truncated`` is false."""
        dashboard_id, graph_ids = await _setup_dashboard_with_aggregates(
            async_db_session,
            test_user["id"],
            rows_per_graph={"Small": 5},
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id), "graph_id": str(graph_ids["Small"])},
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()

        assert body["truncated"] is False
        assert body["total_rows"] == 5
        graph = body["graphs"][0]
        assert graph["rows_truncated"] is False
        assert graph["total_rows"] == 5
        assert len(graph["data"]) == 5

    async def test_determinism(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Two identical requests over the same data return the same slice."""
        from mkobi.config import get_config

        caps = get_config().data
        dashboard_id, graph_ids = await _setup_dashboard_with_aggregates(
            async_db_session,
            test_user["id"],
            rows_per_graph={"Big": caps.max_rows_per_graph + 25},
        )
        params = {
            "dashboard_id": str(dashboard_id),
            "graph_id": str(graph_ids["Big"]),
        }

        first = await authenticated_client.get("/data/aggregated", params=params)
        second = await authenticated_client.get("/data/aggregated", params=params)

        assert first.status_code == status.HTTP_200_OK
        assert first.json()["graphs"][0]["data"] == second.json()["graphs"][0]["data"]

    async def test_counts_are_true(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The reported totals equal the real seeded row counts."""
        from mkobi.config import get_config

        caps = get_config().data
        seeded = {"A": caps.max_rows_per_graph + 7, "B": 3}
        dashboard_id, _ = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows_per_graph=seeded
        )

        response = await authenticated_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard_id)},
        )
        assert response.status_code == status.HTTP_200_OK
        body = response.json()

        assert body["total_rows"] == sum(seeded.values())
        by_name = {g["name"]: g for g in body["graphs"]}
        for name, count in seeded.items():
            assert by_name[name]["total_rows"] == count
