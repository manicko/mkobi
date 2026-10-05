"""AZ-11: one refusal code for one class of refusal.

Same-class 403s are normalised to ``PERMISSION_DENIED``. The sites that already
used it (``layouts.py``, ``api/deps.py``, ``graphs.py``, ``processing_configs.py``,
``processing_logs.py``, ``upload.py``) are left untouched. The mixed sites this
suite pins are:

- ``dashboards_crud.py``: the get and delete handlers used ``ACCESS_DENIED``.
- ``users.py``: the self-delete and admin-delete handlers used ``ACCESS_DENIED``.
- ``data.py``: the aggregate handler used ``ACCESS_DENIED``.

``dashboards_access.py``'s revoke-miss keeps ``NOT_FOUND``: a revoke of a grant
that does not exist is a not-found on a sub-resource, not a permission refusal,
and only same-class 403s are normalised. That classification is pinned here too,
so it is not left silently unclassified.

The client owns the error-code vocabulary; this change files the rename and does
not edit any frontend message map. Every test impersonates an explicit caller
because ``conftest.py::test_user`` is ``role="admin"`` and would bypass the gate.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete

from mkobi.core.security import create_access_token
from mkobi.db.models import Dashboard, DashboardAccess, User
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import UserRole


async def _impersonate(async_client: AsyncClient, user: User) -> None:
    """Point the client at one explicit caller, replacing any inherited header."""
    token = create_access_token({"user_id": str(user.id), "email": user.email})
    async_client.headers.update({"Authorization": f"Bearer {token}"})


async def _cleanup(session, *, dashboard_id=None, user_ids=()) -> None:
    """Delete rows a test committed. A production commit is durable here."""
    if dashboard_id is not None:
        await session.execute(
            delete(DashboardAccess).where(
                DashboardAccess.dashboard_id == dashboard_id
            )
        )
        await session.execute(delete(Dashboard).where(Dashboard.id == dashboard_id))
    for user_id in user_ids:
        await session.execute(delete(User).where(User.id == user_id))
    await session.commit()


class TestDashboardsCrudRefusalCode:
    """The dashboards_crud refusals render PERMISSION_DENIED, never ACCESS_DENIED."""

    @pytest.mark.asyncio
    async def test_get_dashboard_without_access_is_permission_denied(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """A non-admin with no grant on the dashboard is refused with PERMISSION_DENIED."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"norm_get_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"norm_get_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        assert owner is not None and caller is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"norm-get-{uuid4().hex[:8]}",
            created_by=owner.id,
            config={"graph_types": ["bar"]},
        )
        assert dashboard is not None
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        try:
            response = await async_client.get(f"/dashboards/{dashboard.id}")
            assert response.status_code == 403
            assert response.json()["code"] == "PERMISSION_DENIED"
        finally:
            await _cleanup(
                async_db_session, dashboard_id=dashboard.id, user_ids=(owner.id, caller.id)
            )

    @pytest.mark.asyncio
    async def test_delete_dashboard_without_admin_grant_is_permission_denied(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """A non-admin without an admin grant on the dashboard is refused with PERMISSION_DENIED."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"norm_del_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"norm_del_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        assert owner is not None and caller is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"norm-del-{uuid4().hex[:8]}",
            created_by=owner.id,
            config={"graph_types": ["bar"]},
        )
        assert dashboard is not None
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        try:
            response = await async_client.delete(f"/dashboards/{dashboard.id}")
            assert response.status_code == 403
            assert response.json()["code"] == "PERMISSION_DENIED"
        finally:
            await _cleanup(
                async_db_session, dashboard_id=dashboard.id, user_ids=(owner.id, caller.id)
            )


class TestDataRefusalCode:
    """The aggregate read renders PERMISSION_DENIED for a caller with no grant."""

    @pytest.mark.asyncio
    async def test_aggregate_without_dashboard_access_is_permission_denied(
        self, async_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A non-admin with no grant on the dashboard gets 403 PERMISSION_DENIED."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"norm_data_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"norm_data_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        assert owner is not None and caller is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"norm-data-{uuid4().hex[:8]}",
            created_by=owner.id,
            config={"graph_types": ["bar"]},
        )
        assert dashboard is not None
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        try:
            response = await async_client.get(
                "/data/aggregated",
                params={"dashboard_id": str(dashboard.id)},
            )
            assert response.status_code == 403
            assert response.json()["code"] == "PERMISSION_DENIED"
        finally:
            await _cleanup(
                async_db_session, dashboard_id=dashboard.id, user_ids=(owner.id, caller.id)
            )


class TestRevokeMissClassification:
    """A revoke of an absent grant stays a 404 NOT_FOUND, deliberately not a 403.

    AZ-11 normalises only same-class 403s. A revoke-miss is a not-found on a
    sub-resource and a different class, so it keeps ``NOT_FOUND``. This test
    pins that decision rather than leaving it unclassified.
    """

    @pytest.mark.asyncio
    async def test_revoke_of_absent_grant_is_404_not_permission_denied(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """An administrator revoking a grant that does not exist gets 404 NOT_FOUND."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"norm_rev_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        target = await user_repo.create(
            db=async_db_session,
            email=f"norm_rev_target_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert owner is not None and target is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"norm-rev-{uuid4().hex[:8]}",
            created_by=owner.id,
            config={"graph_types": ["bar"]},
        )
        assert dashboard is not None
        await async_db_session.flush()
        # target has no grant on the dashboard, so the revoke finds nothing.

        try:
            response = await authenticated_client.delete(
                f"/dashboards/{dashboard.id}/access/{target.id}"
            )
            assert response.status_code == 404
            assert response.json()["code"] == "NOT_FOUND"
            assert response.json()["code"] != "PERMISSION_DENIED"
        finally:
            await _cleanup(
                async_db_session,
                dashboard_id=dashboard.id,
                user_ids=(owner.id, target.id),
            )
