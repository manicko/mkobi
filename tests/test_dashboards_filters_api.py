"""Route-level audience and error tests for the dashboard filter bind/unbind surface.

AZ-4: both handlers previously carried no dashboard gate at all -- only
``CurrentUser`` -- so any authenticated user could bind or unbind a filter on a
dashboard they could not administer, and the docstring's "Requires admin role"
claim was false. The bind and unbind routes now carry
``require_dashboard_admin_access``, the same grant gate the access routes use.
The missing-dashboard and missing-filter 404 branches are pinned here as well,
because the handlers previously funnelled them through a bare ``except
Exception``.

Every audience case impersonates an explicit caller: ``conftest.py::test_user``
is ``role="admin"``, so the admin bypass short-circuits before any grant is read
and would mask a wrong gate.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from mkobi.core.security import create_access_token
from mkobi.db.models import Dashboard, DashboardAccess, Filter, User
from mkobi.db.models.filters import dashboard_filters
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.filter_repo import FilterRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import DashboardPermission, FilterType, UserRole


async def _impersonate(async_client: AsyncClient, user: User) -> None:
    """Point the client at one explicit caller, replacing any inherited header."""
    token = create_access_token({"user_id": str(user.id), "email": user.email})
    async_client.headers.update({"Authorization": f"Bearer {token}"})


async def _binding_exists(async_session_maker, dashboard_id, filter_id) -> bool:
    """Read the binding through an independent session."""
    verify = async_session_maker()
    try:
        result = await verify.execute(
            select(dashboard_filters).where(
                dashboard_filters.c.dashboard_id == dashboard_id,
                dashboard_filters.c.filter_id == filter_id,
            )
        )
        return result.first() is not None
    finally:
        await verify.close()


async def _cleanup(
    session,
    *,
    dashboard_id=None,
    filter_id=None,
    user_ids=(),
) -> None:
    """Delete rows the endpoint committed. A production commit is durable here."""
    if dashboard_id is not None:
        await session.execute(
            delete(dashboard_filters).where(
                dashboard_filters.c.dashboard_id == dashboard_id
            )
        )
        await session.execute(
            delete(DashboardAccess).where(
                DashboardAccess.dashboard_id == dashboard_id
            )
        )
        await session.execute(delete(Dashboard).where(Dashboard.id == dashboard_id))
    if filter_id is not None:
        await session.execute(
            delete(dashboard_filters).where(
                dashboard_filters.c.filter_id == filter_id
            )
        )
        await session.execute(delete(Filter).where(Filter.id == filter_id))
    for user_id in user_ids:
        await session.execute(delete(User).where(User.id == user_id))
    await session.commit()


async def _seed_dashboard_and_filter(
    async_db_session, owner_id
):
    """Create one dashboard and one filter, flushed but not committed."""
    dashboard_repo = DashboardRepository()
    filter_repo = FilterRepository()
    dashboard = await dashboard_repo.create(
        db=async_db_session,
        name=f"filters-aud-{uuid4().hex[:8]}",
        created_by=owner_id,
    )
    filter_obj = await filter_repo.create(
        db=async_db_session,
        name=f"filter-{uuid4().hex[:8]}",
        type=FilterType.SELECT,
        config={},
    )
    assert dashboard is not None and filter_obj is not None
    await async_db_session.flush()
    return dashboard, filter_obj


class TestBindFilterAudience:
    """POST /dashboards/{id}/filters enforces the dashboard admin audience."""

    @pytest.mark.asyncio
    async def test_editor_with_no_grant_is_refused_and_writes_no_binding(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """A ``test_user``-role editor with no grant gets 403 on bind."""
        user_repo = UserRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"bind_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"bind_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        assert owner is not None and caller is not None
        dashboard, filter_obj = await _seed_dashboard_and_filter(
            async_db_session, owner.id
        )

        await _impersonate(async_client, caller)

        try:
            response = await async_client.post(
                f"/dashboards/{dashboard.id}/filters",
                params={"filter_id": str(filter_obj.id)},
            )
            assert response.status_code == 403
            assert response.json()["code"] == "PERMISSION_DENIED"
            assert not await _binding_exists(
                async_session_maker, dashboard.id, filter_obj.id
            )
        finally:
            await _cleanup(
                async_db_session,
                dashboard_id=dashboard.id,
                filter_id=filter_obj.id,
                user_ids=(owner.id, caller.id),
            )

    @pytest.mark.asyncio
    async def test_granted_administrator_succeeds(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """A non-admin caller holding an ``admin`` grant on the dashboard succeeds."""
        user_repo = UserRepository()
        access_repo = AccessRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"bind_gowner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"bind_gcaller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        assert owner is not None and caller is not None
        dashboard, filter_obj = await _seed_dashboard_and_filter(
            async_db_session, owner.id
        )
        await access_repo.grant_access(
            db=async_db_session,
            user_id=caller.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.ADMIN,
        )
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        try:
            response = await async_client.post(
                f"/dashboards/{dashboard.id}/filters",
                params={"filter_id": str(filter_obj.id)},
            )
            assert response.status_code == 200
            assert response.json()["bound"] is True
            assert await _binding_exists(
                async_session_maker, dashboard.id, filter_obj.id
            )
        finally:
            await _cleanup(
                async_db_session,
                dashboard_id=dashboard.id,
                filter_id=filter_obj.id,
                user_ids=(owner.id, caller.id),
            )

    @pytest.mark.asyncio
    async def test_missing_dashboard_returns_404_for_an_administrator(
        self, authenticated_client: AsyncClient, async_db_session, async_session_maker,
        test_user: dict,
    ) -> None:
        """An administrator binding on a non-existent dashboard gets 404, not a 500."""
        filter_repo = FilterRepository()
        filter_obj = await filter_repo.create(
            db=async_db_session,
            name=f"bind_missing_{uuid4().hex[:8]}",
            type=FilterType.SELECT,
            config={},
        )
        assert filter_obj is not None
        await async_db_session.flush()

        unknown_dashboard_id = uuid4()
        try:
            response = await authenticated_client.post(
                f"/dashboards/{unknown_dashboard_id}/filters",
                params={"filter_id": str(filter_obj.id)},
            )
            assert response.status_code == 404
            assert response.json()["code"] == "DASHBOARD_NOT_FOUND"
        finally:
            await _cleanup(async_db_session, filter_id=filter_obj.id)

    @pytest.mark.asyncio
    async def test_missing_filter_returns_404(
        self, authenticated_client: AsyncClient, async_db_session, async_session_maker,
        test_user: dict,
    ) -> None:
        """An administrator binding a non-existent filter gets 404 FILTER_NOT_FOUND."""
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"bind_nofilter_{uuid4().hex[:8]}",
            created_by=test_user["id"],
        )
        assert dashboard is not None
        await async_db_session.flush()

        try:
            response = await authenticated_client.post(
                f"/dashboards/{dashboard.id}/filters",
                params={"filter_id": str(uuid4())},
            )
            assert response.status_code == 404
            assert response.json()["code"] == "FILTER_NOT_FOUND"
        finally:
            await _cleanup(async_db_session, dashboard_id=dashboard.id)


class TestUnbindFilterAudience:
    """DELETE /dashboards/{id}/filters/{filter_id} enforces the same audience."""

    @pytest.mark.asyncio
    async def test_editor_with_no_grant_is_refused_and_binding_survives(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """A ``test_user``-role editor with no grant gets 403 on unbind."""
        user_repo = UserRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"unbind_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"unbind_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        assert owner is not None and caller is not None
        dashboard, filter_obj = await _seed_dashboard_and_filter(
            async_db_session, owner.id
        )
        await async_db_session.execute(
            dashboard_filters.insert().values(
                dashboard_id=dashboard.id, filter_id=filter_obj.id
            )
        )
        # Commit so the pre-existing binding is visible to the independent session.
        await async_db_session.commit()
        assert await _binding_exists(async_session_maker, dashboard.id, filter_obj.id)

        await _impersonate(async_client, caller)

        try:
            response = await async_client.delete(
                f"/dashboards/{dashboard.id}/filters/{filter_obj.id}"
            )
            assert response.status_code == 403
            assert response.json()["code"] == "PERMISSION_DENIED"
            assert await _binding_exists(
                async_session_maker, dashboard.id, filter_obj.id
            )
        finally:
            await _cleanup(
                async_db_session,
                dashboard_id=dashboard.id,
                filter_id=filter_obj.id,
                user_ids=(owner.id, caller.id),
            )

    @pytest.mark.asyncio
    async def test_granted_administrator_succeeds(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """A caller holding an ``admin`` grant on the dashboard may unbind."""
        user_repo = UserRepository()
        access_repo = AccessRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"unbind_gowner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"unbind_gcaller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        assert owner is not None and caller is not None
        dashboard, filter_obj = await _seed_dashboard_and_filter(
            async_db_session, owner.id
        )
        await access_repo.grant_access(
            db=async_db_session,
            user_id=caller.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.ADMIN,
        )
        await async_db_session.execute(
            dashboard_filters.insert().values(
                dashboard_id=dashboard.id, filter_id=filter_obj.id
            )
        )
        await async_db_session.commit()
        assert await _binding_exists(async_session_maker, dashboard.id, filter_obj.id)

        await _impersonate(async_client, caller)

        try:
            response = await async_client.delete(
                f"/dashboards/{dashboard.id}/filters/{filter_obj.id}"
            )
            assert response.status_code == 200
            assert not await _binding_exists(
                async_session_maker, dashboard.id, filter_obj.id
            )
        finally:
            await _cleanup(
                async_db_session,
                dashboard_id=dashboard.id,
                filter_id=filter_obj.id,
                user_ids=(owner.id, caller.id),
            )

    @pytest.mark.asyncio
    async def test_missing_dashboard_returns_404_for_an_administrator(
        self, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """An administrator unbinding on a non-existent dashboard gets 404."""
        response = await authenticated_client.delete(
            f"/dashboards/{uuid4()}/filters/{uuid4()}",
        )
        assert response.status_code == 404
        assert response.json()["code"] == "DASHBOARD_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_missing_filter_returns_404(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """An administrator unbinding a filter not bound to the dashboard gets 404."""
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"unbind_nofilter_{uuid4().hex[:8]}",
            created_by=test_user["id"],
        )
        assert dashboard is not None
        await async_db_session.flush()

        try:
            response = await authenticated_client.delete(
                f"/dashboards/{dashboard.id}/filters/{uuid4()}",
            )
            assert response.status_code == 404
            assert response.json()["code"] == "FILTER_NOT_FOUND"
        finally:
            await _cleanup(async_db_session, dashboard_id=dashboard.id)
