"""Tests for the shared accessible-dashboard filter on collection endpoints.

Three surfaces are covered:

* ``api/deps.py::get_accessible_dashboard_ids`` — the single implementation of
  the set-shaped rule, including the admin bypass.
* ``GET /graphs/`` — the graphs collection now routed through that filter.
* ``GET /layouts`` — the layouts collection now routed through that filter.

Isolation follows the harness contract: rows are created with ``flush()`` only,
so the SAVEPOINT that ``async_db_session`` opens is rolled back at teardown and
nothing leaks into later tests. ``async_client`` overrides ``get_db_dependency``
with that same session, so flushed rows are visible to the request. Callers are
authenticated with a token rather than a login round-trip.

The admin tests assert a **superset** (``>=``), because the admin branch reads
the whole table, including rows other tests committed. The non-admin tests
assert **exact** sets, because the caller's grant set is exactly the one
dashboard each test grants.
"""

from typing import Any
from uuid import UUID, uuid4

from fastapi import status
from httpx import AsyncClient

from mkobi.api.deps import get_accessible_dashboard_ids
from mkobi.core.security import create_access_token
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.db.repositories.layout_repo import LayoutRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.dashboard import DashboardSummary
from mkobi.models.enums import DashboardPermission, GraphType, UserRole
from mkobi.models.user import UserRead
from datetime import UTC


def _authenticate(client: AsyncClient, user: UserRead) -> None:
    """Attach a bearer token for ``user`` to the client headers."""
    token = create_access_token({"user_id": str(user.id), "email": user.email})
    client.headers.update({"Authorization": f"Bearer {token}"})


def _user_read(user_id: UUID, role: UserRole) -> UserRead:
    """Build a ``UserRead`` from the fields the dependency reads."""
    from datetime import datetime

    now = datetime.now(UTC)
    return UserRead(
        id=user_id,
        email=f"{user_id.hex[:8]}@example.com",
        role=role,
        is_active=True,
        created_at=now,
    )


class _StubDashboardService:
    """Minimal stand-in whose ``get_user_dashboards`` is observable."""

    def __init__(self, dashboards: list[DashboardSummary]) -> None:
        self._dashboards = dashboards
        self.call_count = 0
        self.last_user_role: Any = None

    async def get_user_dashboards(
        self, user_id: UUID, user_role: Any, db: Any
    ) -> list[DashboardSummary]:
        self.call_count += 1
        self.last_user_role = user_role
        return self._dashboards


class _ExplodingDashboardService:
    """A service that fails if the dependency reaches it at all."""

    async def get_user_dashboards(
        self, user_id: UUID, user_role: Any, db: Any
    ) -> list[DashboardSummary]:
        raise AssertionError("admin bypass must not query the dashboard service")


class TestAccessibleDashboardIdsDependency:
    """Unit tests for the shared set-shaped dependency."""

    async def test_admin_role_caller_yields_no_dashboard_filter(self) -> None:
        """An admin short-circuits to ``None`` before any query runs."""
        admin = _user_read(uuid4(), UserRole.ADMIN)

        result = await get_accessible_dashboard_ids(
            user=admin,
            db=None,  # type: ignore[arg-type]
            dashboard_service=_ExplodingDashboardService(),
        )

        assert result is None

    async def test_non_admin_caller_yields_the_dashboards_the_service_reports(
        self,
    ) -> None:
        """A non-admin caller receives exactly the ids the service reports."""
        from datetime import datetime

        now = datetime.now(UTC)
        first_id = uuid4()
        second_id = uuid4()
        dashboards = [
            DashboardSummary(
                id=first_id,
                name="first",
                description=None,
                permission=DashboardPermission.VIEW,
                created_at=now,
            ),
            DashboardSummary(
                id=second_id,
                name="second",
                description=None,
                permission=DashboardPermission.VIEW,
                created_at=now,
            ),
        ]
        service = _StubDashboardService(dashboards)
        editor = _user_read(uuid4(), UserRole.EDITOR)

        result = await get_accessible_dashboard_ids(
            user=editor,
            db=None,  # type: ignore[arg-type]
            dashboard_service=service,
        )

        assert result == [first_id, second_id]
        assert service.call_count == 1
        assert service.last_user_role == UserRole.EDITOR


class TestGraphsListAccessScope:
    """Access-scope tests for ``GET /graphs/``."""

    async def test_admin_role_caller_sees_every_graph(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """An admin with no grant rows still sees every graph."""
        user_repo = UserRepository()
        await user_repo.create(
            db=async_db_session,
            email=f"graphs_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        admin = await user_repo.create(
            db=async_db_session,
            email=f"graphs_admin_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.ADMIN,
        )
        await async_db_session.flush()

        dashboard_repo = DashboardRepository()
        graph_repo = GraphRepository()
        dashboard_a = await dashboard_repo.create(
            db=async_db_session, name=f"graphs-admin-a-{uuid4().hex[:8]}"
        )
        dashboard_b = await dashboard_repo.create(
            db=async_db_session, name=f"graphs-admin-b-{uuid4().hex[:8]}"
        )
        await async_db_session.flush()

        graph_a = await graph_repo.create(
            db=async_db_session,
            name=f"graph-a-{uuid4().hex[:8]}",
            type=GraphType.BAR,
            dashboard_id=dashboard_a.id,
        )
        graph_b = await graph_repo.create(
            db=async_db_session,
            name=f"graph-b-{uuid4().hex[:8]}",
            type=GraphType.BAR,
            dashboard_id=dashboard_b.id,
        )
        await async_db_session.flush()
        assert graph_a is not None and graph_b is not None

        _authenticate(async_client, admin)
        response = await async_client.get("/graphs/")

        assert response.status_code == status.HTTP_200_OK
        returned = {item["id"] for item in response.json()}
        assert returned >= {str(graph_a.id), str(graph_b.id)}

    async def test_non_admin_sees_only_graphs_on_granted_dashboards(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """An editor granted VIEW on A sees A's graph and not B's."""
        user_repo = UserRepository()
        editor = await user_repo.create(
            db=async_db_session,
            email=f"graphs_editor_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        await async_db_session.flush()

        dashboard_repo = DashboardRepository()
        graph_repo = GraphRepository()
        dashboard_a = await dashboard_repo.create(
            db=async_db_session, name=f"graphs-granted-a-{uuid4().hex[:8]}"
        )
        dashboard_b = await dashboard_repo.create(
            db=async_db_session, name=f"graphs-granted-b-{uuid4().hex[:8]}"
        )
        await async_db_session.flush()

        graph_a = await graph_repo.create(
            db=async_db_session,
            name=f"graph-granted-a-{uuid4().hex[:8]}",
            type=GraphType.BAR,
            dashboard_id=dashboard_a.id,
        )
        await graph_repo.create(
            db=async_db_session,
            name=f"graph-granted-b-{uuid4().hex[:8]}",
            type=GraphType.BAR,
            dashboard_id=dashboard_b.id,
        )
        await async_db_session.flush()
        assert graph_a is not None

        await AccessRepository().grant_access(
            db=async_db_session,
            user_id=editor.id,
            dashboard_id=dashboard_a.id,
            permission=DashboardPermission.VIEW,
        )
        await async_db_session.flush()

        _authenticate(async_client, editor)
        response = await async_client.get("/graphs/")

        assert response.status_code == status.HTTP_200_OK
        returned = {item["id"] for item in response.json()}
        assert returned == {str(graph_a.id)}

    async def test_non_admin_without_grants_sees_empty_collection(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """An editor with no grants gets 200 and an empty list, not 403 or 500."""
        user_repo = UserRepository()
        editor = await user_repo.create(
            db=async_db_session,
            email=f"graphs_nogrant_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        await async_db_session.flush()

        dashboard_repo = DashboardRepository()
        graph_repo = GraphRepository()
        dashboard_a = await dashboard_repo.create(
            db=async_db_session, name=f"graphs-empty-a-{uuid4().hex[:8]}"
        )
        dashboard_b = await dashboard_repo.create(
            db=async_db_session, name=f"graphs-empty-b-{uuid4().hex[:8]}"
        )
        await async_db_session.flush()

        await graph_repo.create(
            db=async_db_session,
            name=f"graph-empty-a-{uuid4().hex[:8]}",
            type=GraphType.BAR,
            dashboard_id=dashboard_a.id,
        )
        await graph_repo.create(
            db=async_db_session,
            name=f"graph-empty-b-{uuid4().hex[:8]}",
            type=GraphType.BAR,
            dashboard_id=dashboard_b.id,
        )
        await async_db_session.flush()

        _authenticate(async_client, editor)
        response = await async_client.get("/graphs/")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []


class TestLayoutsListAccessScope:
    """Access-scope tests for ``GET /layouts``."""

    async def test_admin_role_caller_sees_every_layout_including_unbound(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """An admin with no grant rows sees an unbound layout and a bound one."""
        user_repo = UserRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"layouts_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        admin = await user_repo.create(
            db=async_db_session,
            email=f"layouts_admin_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.ADMIN,
        )
        await async_db_session.flush()

        layout_repo = LayoutRepository()
        layout_l1 = await layout_repo.create(
            db=async_db_session,
            name=f"layout-unbound-{uuid4().hex[:8]}",
            definition={"grid": []},
        )
        layout_l2 = await layout_repo.create(
            db=async_db_session,
            name=f"layout-bound-{uuid4().hex[:8]}",
            definition={"grid": []},
        )
        await async_db_session.flush()
        assert layout_l1 is not None and layout_l2 is not None

        dashboard_repo = DashboardRepository()
        await dashboard_repo.create(
            db=async_db_session,
            name=f"layouts-admin-dash-{uuid4().hex[:8]}",
            created_by=owner.id,
            layout_id=layout_l2.id,
        )
        await async_db_session.flush()

        _authenticate(async_client, admin)
        response = await async_client.get("/layouts")

        assert response.status_code == status.HTTP_200_OK
        returned = {item["id"] for item in response.json()}
        assert returned >= {str(layout_l1.id), str(layout_l2.id)}

    async def test_non_admin_sees_only_layouts_bound_to_granted_dashboards(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """An editor granted VIEW on A sees exactly A's layout, not B's."""
        user_repo = UserRepository()
        editor = await user_repo.create(
            db=async_db_session,
            email=f"layouts_editor_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        await async_db_session.flush()

        layout_repo = LayoutRepository()
        layout_l1 = await layout_repo.create(
            db=async_db_session,
            name=f"layout-granted-a-{uuid4().hex[:8]}",
            definition={"grid": []},
        )
        layout_l2 = await layout_repo.create(
            db=async_db_session,
            name=f"layout-granted-b-{uuid4().hex[:8]}",
            definition={"grid": []},
        )
        await async_db_session.flush()
        assert layout_l1 is not None and layout_l2 is not None

        dashboard_repo = DashboardRepository()
        dashboard_a = await dashboard_repo.create(
            db=async_db_session,
            name=f"layouts-granted-a-{uuid4().hex[:8]}",
            created_by=editor.id,
            layout_id=layout_l1.id,
        )
        await dashboard_repo.create(
            db=async_db_session,
            name=f"layouts-granted-b-{uuid4().hex[:8]}",
            created_by=editor.id,
            layout_id=layout_l2.id,
        )
        await async_db_session.flush()

        await AccessRepository().grant_access(
            db=async_db_session,
            user_id=editor.id,
            dashboard_id=dashboard_a.id,
            permission=DashboardPermission.VIEW,
        )
        await async_db_session.flush()

        _authenticate(async_client, editor)
        response = await async_client.get("/layouts")

        assert response.status_code == status.HTTP_200_OK
        returned = {item["id"] for item in response.json()}
        assert returned == {str(layout_l1.id)}

    async def test_non_admin_without_grants_sees_empty_collection(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """An editor with no grants gets 200 and an empty list, not 403 or 500."""
        user_repo = UserRepository()
        editor = await user_repo.create(
            db=async_db_session,
            email=f"layouts_nogrant_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        await async_db_session.flush()

        layout_repo = LayoutRepository()
        layout_l1 = await layout_repo.create(
            db=async_db_session,
            name=f"layout-empty-a-{uuid4().hex[:8]}",
            definition={"grid": []},
        )
        layout_l2 = await layout_repo.create(
            db=async_db_session,
            name=f"layout-empty-b-{uuid4().hex[:8]}",
            definition={"grid": []},
        )
        await async_db_session.flush()
        assert layout_l1 is not None and layout_l2 is not None

        dashboard_repo = DashboardRepository()
        await dashboard_repo.create(
            db=async_db_session,
            name=f"layouts-empty-a-{uuid4().hex[:8]}",
            created_by=editor.id,
            layout_id=layout_l1.id,
        )
        await dashboard_repo.create(
            db=async_db_session,
            name=f"layouts-empty-b-{uuid4().hex[:8]}",
            created_by=editor.id,
            layout_id=layout_l2.id,
        )
        await async_db_session.flush()

        _authenticate(async_client, editor)
        response = await async_client.get("/layouts")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []
