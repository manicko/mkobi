"""Tests for graphs API."""

import uuid
from typing import Any

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.core.security import create_access_token, hash_password
from mkobi.db.models import dashboard as dashboard_model
from mkobi.db.models import graphs as graph_model
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.models.enums import (
    BarmodeEnum,
    DashboardPermission,
    ErrorCode,
    GraphType,
    OrientationEnum,
    UserRole,
    YoyModeEnum,
)
from mkobi.models.types import GraphConfigDict, GraphConfigModel


async def _delete_committed_graph(
    async_session_maker, dashboard_id: uuid.UUID, name: str
) -> None:
    """Delete rows a create request in this suite committed.

    A production commit in this harness is durable and the fixture's teardown
    rollback cannot undo it, so any test that creates a graph must delete it
    afterwards. Graphs are deleted before their dashboard to respect the
    foreign key.
    """
    async with async_session_maker() as session:
        await session.execute(
            delete(graph_model.Graph).where(
                graph_model.Graph.dashboard_id == dashboard_id,
                graph_model.Graph.name == name,
            )
        )
        await session.execute(
            delete(dashboard_model.Dashboard).where(
                dashboard_model.Dashboard.id == dashboard_id
            )
        )
        await session.commit()


async def _count_committed_graphs(
    async_session_maker, dashboard_id: uuid.UUID, name: str
) -> int:
    """Count graph rows for a pair through a session independent of the request's."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count())
            .select_from(graph_model.Graph)
            .where(
                graph_model.Graph.dashboard_id == dashboard_id,
                graph_model.Graph.name == name,
            )
        )
        return result.scalar_one()


# The declared vocabulary of a graph ``config``, written out by hand rather than
# derived from ``GraphConfigDict.__annotations__``. The literal is the pin: a
# round-trip test checked against the live annotations would shrink silently with
# a future narrowing of the vocabulary (the regression f500d1f introduced), so
# the expected set must not be able to drift with the source it guards.
EXPECTED_GRAPH_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "x",
        "y",
        "color",
        "metrics",
        "orientation",
        "barmode",
        "showlegend",
        "xaxis",
        "yaxis",
        "title",
        "layout",
        "yoy",
        "secondary_y",
        "sort_x",
        "sort_color",
    }
)

# The six keys that are declared, validated at the request boundary, stored and
# returned on read, but read by nothing in ``src/`` or ``frontend/src/`` today.
# They are RESERVED by adjudication D-16-1: deliberately not deleted and
# deliberately not silently ignored. Stating the split as a literal makes the
# classification a testable fact rather than a comment.
#
# ``layout`` left this set in residual block ``R2``: it is now read by
# ``api/routes/data.py::get_aggregated_data_endpoint`` into
# ``GraphDataResponse.layout``. ``xaxis`` / ``yaxis`` stay reserved, deliberately
# unwired, because the renderer reads the response's ``layout`` field only.
RESERVED_GRAPH_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "yoy",
        "secondary_y",
        "xaxis",
        "yaxis",
        "sort_x",
        "sort_color",
    }
)

# A config carrying all fifteen declared keys, each with a non-default value that
# is distinguishable from every other key's value, so a dropped or overwritten
# key changes the deep-equality comparison at every leg of the round trip.
FULL_GRAPH_CONFIG: dict[str, Any] = {
    "x": "category",
    "y": "sales",
    "color": "region",
    "metrics": ["profit"],
    "orientation": OrientationEnum.HORIZONTAL,
    "barmode": BarmodeEnum.STACK,
    "showlegend": False,
    "xaxis": {"title": "Category axis", "type": "linear"},
    "yaxis": {"title": "Sales axis", "type": "log"},
    "title": "Sales by category",
    "layout": {"title": "Layout title", "showlegend": True, "height": 480},
    "yoy": {"enabled": True, "metric": "revenue", "mode": YoyModeEnum.PERCENT},
    "secondary_y": ["margin"],
    "sort_x": {"by": "sales", "direction": "desc"},
    "sort_color": {"by": "profit", "direction": "asc"},
}


class TestGraphsAPI:
    """Test cases for graphs API endpoints."""

    async def _create_editor_user(self, async_db_session: AsyncSession, suffix: str = ""):
        """Helper to create and commit an editor user."""
        user_repo = UserRepository()
        email = f"editor_{suffix}{uuid.uuid4().hex[:8]}@example.com"
        editor = await user_repo.create(
            db=async_db_session,
            email=email,
            password_hash=hash_password("TestPass123!"),
            role="editor",
        )
        await async_db_session.commit()
        return editor

    async def _create_admin_user(self, async_db_session: AsyncSession, suffix: str = ""):
        """Helper to create and commit an admin user."""
        user_repo = UserRepository()
        email = f"admin_{suffix}{uuid.uuid4().hex[:8]}@example.com"
        admin = await user_repo.create(
            db=async_db_session,
            email=email,
            password_hash=hash_password("AdminPass123!"),
            role="admin",
        )
        await async_db_session.commit()
        return admin

    async def _create_viewer_user(self, async_db_session: AsyncSession, suffix: str = ""):
        """Helper to create and commit a viewer user."""
        user_repo = UserRepository()
        email = f"viewer_{suffix}{uuid.uuid4().hex[:8]}@example.com"
        viewer = await user_repo.create(
            db=async_db_session,
            email=email,
            password_hash=hash_password("TestPass123!"),
            role="viewer",
        )
        await async_db_session.commit()
        return viewer

    async def test_create_graph_admin_required(
        self, async_db_session: AsyncSession, async_client: AsyncClient
    ) -> None:
        """Test that creating graph requires admin role."""
        # Create a viewer user (not admin)
        viewer = await self._create_viewer_user(async_db_session, suffix="graph_test_")

        # Create an admin user to own the dashboard
        admin = await self._create_admin_user(async_db_session, suffix="graph_test_")

        # Login as admin and create dashboard via API
        admin_login = await async_client.post(
            "/auth/login",
            json={"email": admin.email, "password": "AdminPass123!"},
        )
        assert admin_login.status_code == status.HTTP_200_OK
        admin_token = admin_login.json()["access_token"]

        dashboard_response = await async_client.post(
            "/dashboards/",
            json={
                "name": f"test-dashboard-{uuid.uuid4().hex[:8]}",
                "description": "Test",
                "config": {"graph_types": ["bar"]},
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert dashboard_response.status_code == status.HTTP_201_CREATED
        dashboard_id = dashboard_response.json()["id"]

        # Login as viewer and attempt to create a graph
        viewer_login = await async_client.post(
            "/auth/login",
            json={"email": viewer.email, "password": "TestPass123!"},
        )
        assert viewer_login.status_code == status.HTTP_200_OK
        viewer_token = viewer_login.json()["access_token"]

        response = await async_client.post(
            f"/dashboards/{dashboard_id}/graphs",
            json={
                "dashboard_id": str(dashboard_id),
                "name": "test-graph",
                "type": "bar",
                "config": {"xaxis": {"title": "X"}},
                "dimensions": ["category"],
                "metrics": ["sales"],
            },
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_graphs_for_dashboard(
        self, async_db_session: AsyncSession, async_client: AsyncClient
    ) -> None:
        """Test getting graphs for a dashboard."""
        # Create admin user
        admin = await self._create_admin_user(async_db_session, suffix="graph_test2_")

        # Login as admin
        login_response = await async_client.post(
            "/auth/login",
            json={"email": admin.email, "password": "AdminPass123!"},
        )
        assert login_response.status_code == status.HTTP_200_OK
        admin_token = login_response.json()["access_token"]

        # Create dashboard via API
        dashboard_response = await async_client.post(
            "/dashboards/",
            json={
                "name": f"test-dashboard-{uuid.uuid4().hex[:8]}",
                "description": "Test",
                "config": {"graph_types": ["bar", "line"]},
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert dashboard_response.status_code == status.HTTP_201_CREATED
        dashboard_id = dashboard_response.json()["id"]

        # Create graphs via API
        graph1_response = await async_client.post(
            f"/dashboards/{dashboard_id}/graphs",
            json={
                "dashboard_id": str(dashboard_id),
                "name": "Graph 1",
                "type": "bar",
                "config": {"xaxis": {"title": "Category"}, "yaxis": {"title": "Sales"}},
                "dimensions": ["category", "region"],
                "metrics": ["sales", "profit", "qty"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert graph1_response.status_code == status.HTTP_201_CREATED

        graph2_response = await async_client.post(
            f"/dashboards/{dashboard_id}/graphs",
            json={
                "dashboard_id": str(dashboard_id),
                "name": "Graph 2",
                "type": "line",
                "config": {"xaxis": {"title": "Date"}, "yaxis": {"title": "Revenue"}},
                "dimensions": ["region", "product"],
                "metrics": ["sales", "profit"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert graph2_response.status_code == status.HTTP_201_CREATED

        # Get graphs for dashboard via API
        graphs_response = await async_client.get(
            f"/dashboards/{dashboard_id}/graphs",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert graphs_response.status_code == status.HTTP_200_OK
        data = graphs_response.json()
        assert len(data) >= 2

    async def test_create_graph_admin_success(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test creating graph as admin (success)."""
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # Create a dashboard for the graph to belong to
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="test-dashboard-for-graph",
            config={"graph_types": ["bar"]},
        )
        await async_db_session.flush()

        response = await authenticated_client.post(
            "/graphs/",
            json={
                "dashboard_id": str(dashboard.id),
                "name": "admin_graph",
                "type": "bar",
                "config": {"xaxis": {"title": "X"}, "yaxis": {"title": "Y"}},
                "dimensions": ["category"],
                "metrics": ["sales"],
            },
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "admin_graph"
        assert data["type"] == GraphType.BAR

    async def test_create_graph_editor_forbidden(
        self, async_db_session: AsyncSession, async_client: AsyncClient
    ) -> None:
        """Test that creating graph requires admin role (editor forbidden)."""
        # Create editor user
        editor = await self._create_editor_user(async_db_session, suffix="graph_test_")

        # Create admin to own dashboard
        admin = await self._create_admin_user(async_db_session, suffix="graph_test_")

        # Login as admin and create dashboard via API
        admin_login = await async_client.post(
            "/auth/login",
            json={"email": admin.email, "password": "AdminPass123!"},
        )
        assert admin_login.status_code == status.HTTP_200_OK
        admin_token = admin_login.json()["access_token"]

        dashboard_response = await async_client.post(
            "/dashboards/",
            json={
                "name": f"test-dashboard-{uuid.uuid4().hex[:8]}",
                "description": "Test",
                "config": {"graph_types": ["bar"]},
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert dashboard_response.status_code == status.HTTP_201_CREATED
        dashboard_id = dashboard_response.json()["id"]

        # Login as editor and attempt to create a graph
        editor_login = await async_client.post(
            "/auth/login",
            json={"email": editor.email, "password": "TestPass123!"},
        )
        assert editor_login.status_code == status.HTTP_200_OK
        editor_token = editor_login.json()["access_token"]

        response = await async_client.post(
            f"/dashboards/{dashboard_id}/graphs",
            json={
                "dashboard_id": str(dashboard_id),
                "name": "editor-graph",
                "type": "line",
                "config": {"xaxis": {"title": "X"}},
                "dimensions": ["category"],
                "metrics": ["sales"],
            },
            headers={"Authorization": f"Bearer {editor_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_get_graph_by_id(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test getting graph by ID."""
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # Create a dashboard for the graph to belong to
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="test-dashboard-for-read",
            config={"graph_types": ["line"]},
        )
        await async_db_session.flush()

        repo = GraphRepository()
        graph = await repo.create(
            db=async_db_session,
            name="detail_test_graph",
            type=GraphType.LINE,
            dashboard_id=dashboard.id,
            config={"xaxis": {"title": "Category"}},
            dimensions=["category"],
            metrics=["sales"],
        )
        await async_db_session.flush()

        response = await authenticated_client.get(f"/graphs/{graph.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(graph.id)
        assert data["name"] == "detail_test_graph"
        assert data["type"] == GraphType.LINE

    async def test_get_graph_cross_dashboard_forbidden(
        self, async_client: AsyncClient, async_db_session: AsyncSession
    ) -> None:
        """Graph on dashboard A should not be accessible from user with access only to dashboard B."""
        from mkobi.db.repositories.dashboard_repo import DashboardRepository
        from mkobi.db.repositories.access_repo import AccessRepository

        # Create two dashboards
        dashboard_repo = DashboardRepository()
        dashboard_a = await dashboard_repo.create(
            db=async_db_session,
            name="dashboard-a-for-cross-access-test",
            config={"graph_types": ["bar"]},
        )
        dashboard_b = await dashboard_repo.create(
            db=async_db_session,
            name="dashboard-b-for-cross-access-test",
            config={"graph_types": ["line"]},
        )
        await async_db_session.flush()

        # Create two viewer users with separate access
        user_repo = UserRepository()
        user_a = await user_repo.create(
            db=async_db_session,
            email=f"viewer_a_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.VIEWER,
        )
        user_b = await user_repo.create(
            db=async_db_session,
            email=f"viewer_b_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.flush()

        # Grant access: user_a to dashboard_a, user_b to dashboard_b
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=user_a.id,
            dashboard_id=dashboard_a.id,
            permission=DashboardPermission.VIEW,
        )
        await access_repo.grant_access(
            db=async_db_session,
            user_id=user_b.id,
            dashboard_id=dashboard_b.id,
            permission=DashboardPermission.VIEW,
        )
        await async_db_session.flush()

        # Create graph on dashboard_a
        repo = GraphRepository()
        graph = await repo.create(
            db=async_db_session,
            name="cross-access-test-graph",
            type=GraphType.BAR,
            dashboard_id=dashboard_a.id,
            config={"xaxis": {"title": "Category"}},
            dimensions=["category"],
            metrics=["sales"],
        )
        await async_db_session.flush()

        # Login as user B (has access only to dashboard B)
        token_b = create_access_token({"user_id": str(user_b.id), "email": user_b.email})
        async_client.headers = {"Authorization": f"Bearer {token_b}"}

        # User B tries to access graph from dashboard A -> should get 403
        response = await async_client.get(f"/graphs/{graph.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # Login as user A (has access to dashboard A) -> should get 200
        token_a = create_access_token({"user_id": str(user_a.id), "email": user_a.email})
        async_client.headers = {"Authorization": f"Bearer {token_a}"}

        response = await async_client.get(f"/graphs/{graph.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(graph.id)
        assert data["name"] == "cross-access-test-graph"

    async def test_get_graph_not_found(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient
    ) -> None:
        """Test getting non-existent graph returns 404."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(f"/graphs/{fake_id}")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_update_graph_admin_required(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient
    ) -> None:
        """Test that updating graph requires admin role."""
        # Create viewer user and dashboard
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        user_repo = UserRepository()
        viewer = await user_repo.create(
            db=async_db_session,
            email=f"viewer_update_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("TestPass123!"),
            role="viewer",
        )
        await async_db_session.flush()

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="test-dashboard-for-update",
            config={"graph_types": ["bar"]},
        )
        await async_db_session.flush()

        repo = GraphRepository()
        graph = await repo.create(
            db=async_db_session,
            name="update_test_graph",
            type=GraphType.BAR,
            dashboard_id=dashboard.id,
            config={"xaxis": {"title": "X"}},
            dimensions=["category"],
            metrics=["sales"],
        )
        await async_db_session.flush()

        # Login as viewer
        token = create_access_token({"user_id": str(viewer.id), "email": viewer.email})
        viewer_client = authenticated_client
        viewer_client.headers["Authorization"] = f"Bearer {token}"

        response = await viewer_client.put(
            f"/graphs/{graph.id}",
            json={"name": "hacked_graph"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_update_graph_admin_success(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test updating graph as admin (success)."""
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="test-dashboard-for-update-success",
            config={"graph_types": ["bar"]},
        )
        await async_db_session.flush()

        repo = GraphRepository()
        graph = await repo.create(
            db=async_db_session,
            name="update_success_graph",
            type=GraphType.BAR,
            dashboard_id=dashboard.id,
            config={"xaxis": {"title": "X"}},
            dimensions=["category"],
            metrics=["sales"],
        )
        await async_db_session.flush()

        response = await authenticated_client.put(
            f"/graphs/{graph.id}",
            json={"name": "updated_graph_name", "type": "line"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "updated_graph_name"
        assert data["type"] == GraphType.LINE

    async def test_delete_graph_admin_required(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient
    ) -> None:
        """Test that deleting graph requires admin role."""
        # Create viewer user and dashboard
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        user_repo = UserRepository()
        viewer = await user_repo.create(
            db=async_db_session,
            email=f"viewer_delete_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("TestPass123!"),
            role="viewer",
        )
        await async_db_session.flush()

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="test-dashboard-for-delete",
            config={"graph_types": ["bar"]},
        )
        await async_db_session.flush()

        repo = GraphRepository()
        graph = await repo.create(
            db=async_db_session,
            name="delete_test_graph",
            type=GraphType.BAR,
            dashboard_id=dashboard.id,
            config={"xaxis": {"title": "X"}},
            dimensions=["category"],
            metrics=["sales"],
        )
        await async_db_session.flush()

        # Login as viewer
        token = create_access_token({"user_id": str(viewer.id), "email": viewer.email})
        viewer_client = authenticated_client
        viewer_client.headers["Authorization"] = f"Bearer {token}"

        response = await viewer_client.delete(f"/graphs/{graph.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_delete_graph_admin_success(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test deleting graph as admin (success)."""
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="test-dashboard-for-delete-success",
            config={"graph_types": ["bar"]},
        )
        await async_db_session.flush()

        repo = GraphRepository()
        graph = await repo.create(
            db=async_db_session,
            name="delete_success_graph",
            type=GraphType.BAR,
            dashboard_id=dashboard.id,
            config={"xaxis": {"title": "X"}},
            dimensions=["category"],
            metrics=["sales"],
        )
        await async_db_session.flush()

        response = await authenticated_client.delete(f"/graphs/{graph.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    async def test_create_graph_duplicate_name_returns_409(
        self,
        async_db_session: AsyncSession,
        async_session_maker,
        authenticated_client: AsyncClient,
    ) -> None:
        """A duplicate name on the global create route answers 409, not 500 or 422."""
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"dup-graph-dashboard-{uuid.uuid4().hex[:8]}",
            config={"graph_types": ["bar"]},
        )
        await async_db_session.flush()
        # Capture the id now: the request commits, which expires the ORM
        # instance, and reading it afterwards would trigger a lazy load.
        dashboard_id = dashboard.id
        name = f"dup-graph-{uuid.uuid4().hex[:8]}"
        body = {
            "dashboard_id": str(dashboard_id),
            "name": name,
            "type": "bar",
            "config": {"xaxis": {"title": "X"}},
            "dimensions": ["category"],
            "metrics": ["sales"],
        }

        try:
            first = await authenticated_client.post("/graphs/", json=body)
            assert first.status_code == status.HTTP_201_CREATED
            first_body = first.json()
            assert first_body["name"] == name
            assert first_body["type"] == GraphType.BAR
            assert first_body["dashboard_id"] == str(dashboard_id)
            assert first_body["id"]

            second = await authenticated_client.post("/graphs/", json=body)
            assert second.status_code == status.HTTP_409_CONFLICT
            assert second.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR
            assert second.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT
            conflict = second.json()
            assert conflict["code"] == ErrorCode.DUPLICATE_RESOURCE.value
            assert conflict["detail"] == "Conflict: graph creation failed"

            count = await _count_committed_graphs(
                async_session_maker, dashboard_id, name
            )
            assert count == 1
        finally:
            await _delete_committed_graph(async_session_maker, dashboard_id, name)

    async def test_create_dashboard_graph_duplicate_name_returns_409(
        self,
        async_db_session: AsyncSession,
        async_session_maker,
        authenticated_client: AsyncClient,
    ) -> None:
        """The dashboard-scoped route answers a duplicate name with the same 409.

        This is an anti-drift pin: it asserts the surviving sibling route's
        contract matches the global route's status, code and detail, so the two
        surfaces cannot diverge again silently. It does not discriminate the fix
        -- it passes before and after the change by design.
        """
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"dup-scoped-dashboard-{uuid.uuid4().hex[:8]}",
            config={"graph_types": ["bar"]},
        )
        await async_db_session.flush()
        dashboard_id = dashboard.id
        name = f"dup-scoped-graph-{uuid.uuid4().hex[:8]}"
        body = {
            "dashboard_id": str(dashboard_id),
            "name": name,
            "type": "bar",
            "config": {"xaxis": {"title": "X"}},
            "dimensions": ["category"],
            "metrics": ["sales"],
        }
        path = f"/dashboards/{dashboard_id}/graphs"

        try:
            first = await authenticated_client.post(path, json=body)
            assert first.status_code == status.HTTP_201_CREATED

            second = await authenticated_client.post(path, json=body)
            assert second.status_code == status.HTTP_409_CONFLICT
            assert second.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR
            assert second.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT
            conflict = second.json()
            assert conflict["code"] == ErrorCode.DUPLICATE_RESOURCE.value
            assert conflict["detail"] == "Conflict: graph creation failed"

            count = await _count_committed_graphs(
                async_session_maker, dashboard_id, name
            )
            assert count == 1
        finally:
            await _delete_committed_graph(async_session_maker, dashboard_id, name)

    @pytest.mark.parametrize(
        "path_template",
        ["/graphs/", "/dashboards/{dashboard_id}/graphs"],
    )
    async def test_graph_name_conflict_is_not_500_on_any_create_route(
        self,
        async_db_session: AsyncSession,
        async_session_maker,
        authenticated_client: AsyncClient,
        path_template: str,
    ) -> None:
        """A name conflict never surfaces as 500 on either create route."""
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # The unique index is per (dashboard_id, name), so each parametrised
        # case needs its own dashboard.
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"conflict-dashboard-{uuid.uuid4().hex[:8]}",
            config={"graph_types": ["bar"]},
        )
        await async_db_session.flush()
        dashboard_id = dashboard.id
        name = f"conflict-graph-{uuid.uuid4().hex[:8]}"
        body = {
            "dashboard_id": str(dashboard_id),
            "name": name,
            "type": "bar",
            "config": {"xaxis": {"title": "X"}},
            "dimensions": ["category"],
            "metrics": ["sales"],
        }
        path = path_template.format(dashboard_id=dashboard_id)

        try:
            first = await authenticated_client.post(path, json=body)
            assert first.status_code == status.HTTP_201_CREATED

            second = await authenticated_client.post(path, json=body)
            assert second.status_code == status.HTTP_409_CONFLICT
            assert second.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR
            assert second.json()["code"] == ErrorCode.DUPLICATE_RESOURCE.value
        finally:
            await _delete_committed_graph(async_session_maker, dashboard_id, name)



class TestGraphConfigRoundTrip:
    """A declared graph ``config`` survives create -- read -- update -- read over HTTP.

    The round trip is a persistence and serialization property, not a
    request-boundary refusal, so it does not belong beside the ``extra="forbid"``
    suite in ``tests/test_request_boundary_extra_forbid.py``. It lives here
    because ``POST /graphs/`` commits: the committed row survives the DB
    fixture's teardown rollback, and the cleanup helpers that undo it live only
    in this module.

    The vocabulary test below pins the declared set to a hand-written literal.
    Without it the round-trip test would be vacuous against the regression this
    phase already hit once (``f500d1f`` narrowed a boundary vocabulary rather
    than widening it): a round trip checked against the live annotations would
    shrink with the source it guards and still pass.
    """

    async def test_declared_config_survives_create_read_update_read(
        self,
        async_db_session: AsyncSession,
        async_session_maker,
        authenticated_client: AsyncClient,
    ) -> None:
        """A full fifteen-key config round-trips byte-identically through the routes.

        The update leg sends the exact config the read leg returned, so the
        assertion is about the read-modify-write shape the client performs, not
        about a re-typed literal. Every leg asserts deep equality against
        ``FULL_GRAPH_CONFIG`` because a silent drop earlier in the cycle would be
        invisible to a check made only at the end.
        """
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"roundtrip-dashboard-{uuid.uuid4().hex[:8]}",
            config={"graph_types": ["bar"]},
        )
        await async_db_session.flush()
        # Capture the id now: the create request commits, which expires the ORM
        # instance, and reading it afterwards would trigger a lazy load.
        dashboard_id = dashboard.id
        name = f"roundtrip-graph-{uuid.uuid4().hex[:8]}"

        try:
            created = await authenticated_client.post(
                "/graphs/",
                json={
                    "dashboard_id": str(dashboard_id),
                    "name": name,
                    "type": "bar",
                    "config": FULL_GRAPH_CONFIG,
                    "dimensions": ["category"],
                    "metrics": ["sales"],
                },
            )
            assert created.status_code == status.HTTP_201_CREATED
            graph_id = created.json()["id"]

            first_read = await authenticated_client.get(f"/graphs/{graph_id}")
            assert first_read.status_code == status.HTTP_200_OK
            first_config = first_read.json()["config"]
            assert first_config == FULL_GRAPH_CONFIG
            assert set(first_config) == EXPECTED_GRAPH_CONFIG_KEYS

            # The only update key is ``config``, and its value is the config the
            # read leg returned -- the read-modify-write shape the hazard names.
            # A future asymmetry between the create-side and update-side declared
            # sets answers 422 here rather than passing as "nothing changed".
            updated = await authenticated_client.put(
                f"/graphs/{graph_id}",
                json={"config": first_config},
            )
            assert updated.status_code == status.HTTP_200_OK
            assert updated.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT

            second_read = await authenticated_client.get(f"/graphs/{graph_id}")
            assert second_read.status_code == status.HTTP_200_OK
            second_config = second_read.json()["config"]
            assert set(second_config) == EXPECTED_GRAPH_CONFIG_KEYS
            assert second_config == FULL_GRAPH_CONFIG
        finally:
            await _delete_committed_graph(async_session_maker, dashboard_id, name)

    async def test_declared_vocabulary_is_the_published_graph_config_contract(
        self,
    ) -> None:
        """The declared config vocabulary is the literal contract, reserved split included.

        No database and no HTTP: this pins the source vocabulary to a literal so
        removing or moving a key fails loudly instead of shrinking the round-trip
        test with it, mirroring ``DECLARED_GRAPH_CREATE_KEYS`` in the boundary
        suite. It also pins the reserved split as a stated classification.
        """
        assert frozenset(GraphConfigDict.__annotations__) == EXPECTED_GRAPH_CONFIG_KEYS
        assert frozenset(GraphConfigModel.model_fields) == EXPECTED_GRAPH_CONFIG_KEYS
        assert EXPECTED_GRAPH_CONFIG_KEYS - RESERVED_GRAPH_CONFIG_KEYS == frozenset(
            {
                "x",
                "y",
                "color",
                "metrics",
                "orientation",
                "barmode",
                "title",
                "showlegend",
                "layout",
            }
        )
        assert frozenset(GraphConfigModel.model_fields) == frozenset(
            GraphConfigDict.__annotations__
        )


class TestDashboardGraphCreateAudience:
    """POST /dashboards/{id}/graphs enforces the per-dashboard grant, not the global role.

    AZ-6: the create path carried a global ``require_admin_role`` dependency. That
    is a wrong *kind* of gate, not a missing gate: it admits any administrator and
    refuses any non-administrator, regardless of which dashboards they administer.
    The route now carries ``require_dashboard_admin_access``, the same per-dashboard
    grant gate the access routes use, so an editor granted admin on dashboard A can
    create a graph there and a caller with no grant on dashboard B is refused there.
    The admin-role bypass must survive, and is covered by the administrator case.
    """

    @pytest.mark.asyncio
    async def test_granted_editor_can_create_on_their_dashboard(
        self, async_client: AsyncClient, async_db_session: AsyncSession,
        async_session_maker,
    ) -> None:
        """A non-admin editor holding an ``admin`` grant on the dashboard succeeds."""
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"graph_az6_owner_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.EDITOR,
        )
        editor = await user_repo.create(
            db=async_db_session,
            email=f"graph_az6_editor_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.EDITOR,
        )
        assert owner is not None and editor is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"az6-granted-dashboard-{uuid.uuid4().hex[:8]}",
            created_by=owner.id,
            config={"graph_types": ["bar"]},
        )
        assert dashboard is not None
        await access_repo.grant_access(
            db=async_db_session,
            user_id=editor.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.ADMIN,
        )
        await async_db_session.flush()
        dashboard_id = dashboard.id
        name = f"az6-granted-graph-{uuid.uuid4().hex[:8]}"

        token = create_access_token({"user_id": str(editor.id), "email": editor.email})
        try:
            response = await async_client.post(
                f"/dashboards/{dashboard_id}/graphs",
                json={
                    "dashboard_id": str(dashboard_id),
                    "name": name,
                    "type": "bar",
                    "config": {"xaxis": {"title": "X"}},
                    "dimensions": ["category"],
                    "metrics": ["sales"],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == status.HTTP_201_CREATED
            assert await _count_committed_graphs(
                async_session_maker, dashboard_id, name
            ) == 1
        finally:
            await _delete_committed_graph(async_session_maker, dashboard_id, name)

    @pytest.mark.asyncio
    async def test_no_grant_on_dashboard_is_refused(
        self, async_client: AsyncClient, async_db_session: AsyncSession,
        async_session_maker,
    ) -> None:
        """A caller with an admin grant on A is still refused on B with no grant."""
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"graph_az6b_owner_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"graph_az6b_caller_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.EDITOR,
        )
        assert owner is not None and caller is not None
        dashboard_a = await dashboard_repo.create(
            db=async_db_session,
            name=f"az6b-a-{uuid.uuid4().hex[:8]}",
            created_by=owner.id,
            config={"graph_types": ["bar"]},
        )
        dashboard_b = await dashboard_repo.create(
            db=async_db_session,
            name=f"az6b-b-{uuid.uuid4().hex[:8]}",
            created_by=owner.id,
            config={"graph_types": ["bar"]},
        )
        assert dashboard_a is not None and dashboard_b is not None
        # Caller administers A only.
        await access_repo.grant_access(
            db=async_db_session,
            user_id=caller.id,
            dashboard_id=dashboard_a.id,
            permission=DashboardPermission.ADMIN,
        )
        await async_db_session.flush()
        dashboard_b_id = dashboard_b.id
        name = f"az6b-graph-{uuid.uuid4().hex[:8]}"

        token = create_access_token({"user_id": str(caller.id), "email": caller.email})
        try:
            response = await async_client.post(
                f"/dashboards/{dashboard_b_id}/graphs",
                json={
                    "dashboard_id": str(dashboard_b_id),
                    "name": name,
                    "type": "bar",
                    "config": {"xaxis": {"title": "X"}},
                    "dimensions": ["category"],
                    "metrics": ["sales"],
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert response.json()["code"] == ErrorCode.PERMISSION_DENIED.value
            assert await _count_committed_graphs(
                async_session_maker, dashboard_b_id, name
            ) == 0
        finally:
            await _delete_committed_graph(async_session_maker, dashboard_b_id, name)
            await _delete_committed_graph(
                async_session_maker, dashboard_a.id, "az6b-no-such-graph"
            )

    @pytest.mark.asyncio
    async def test_administrator_bypass_survives(
        self, authenticated_client: AsyncClient, async_db_session: AsyncSession,
        async_session_maker, test_user: dict,
    ) -> None:
        """An administrator with no grant row still creates (the bypass must survive)."""
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"az6-admin-dashboard-{uuid.uuid4().hex[:8]}",
            created_by=test_user["id"],
            config={"graph_types": ["bar"]},
        )
        assert dashboard is not None
        await async_db_session.flush()
        dashboard_id = dashboard.id
        name = f"az6-admin-graph-{uuid.uuid4().hex[:8]}"

        try:
            response = await authenticated_client.post(
                f"/dashboards/{dashboard_id}/graphs",
                json={
                    "dashboard_id": str(dashboard_id),
                    "name": name,
                    "type": "bar",
                    "config": {"xaxis": {"title": "X"}},
                    "dimensions": ["category"],
                    "metrics": ["sales"],
                },
            )
            assert response.status_code == status.HTTP_201_CREATED
            assert await _count_committed_graphs(
                async_session_maker, dashboard_id, name
            ) == 1
        finally:
            await _delete_committed_graph(async_session_maker, dashboard_id, name)
