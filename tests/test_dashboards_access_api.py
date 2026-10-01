"""Route-level contract tests for POST /dashboards/{dashboard_id}/access.

The endpoint had no route-level coverage before this module. Its job is to pin the
chosen contract: a duplicate grant is a 200 idempotent no-op with the same body,
never a 409 and never a 500. The pre-existing 422 renderings are pinned so the
untouched branches are proven untouched.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from mkobi.db.models import Dashboard, DashboardAccess, User
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import DashboardPermission, UserRole


async def _cleanup(
    session, dashboard_id, user_id
) -> None:
    """Delete the rows the endpoint committed. A production commit is durable here."""
    await session.execute(
        delete(DashboardAccess).where(DashboardAccess.dashboard_id == dashboard_id)
    )
    await session.execute(delete(Dashboard).where(Dashboard.id == dashboard_id))
    await session.execute(delete(User).where(User.id == user_id))
    await session.commit()


class TestGrantDashboardAccessEndpoint:
    """The endpoint's contract: a duplicate grant is 200 with the same body."""

    @pytest.mark.asyncio
    async def test_grant_twice_returns_200_and_the_same_body(
        self, authenticated_client: AsyncClient, async_db_session, async_session_maker,
        test_user: dict,
    ) -> None:
        """The identical request twice returns 200 and the first body, one row."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=f"api_grant_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert target_user is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"api-grant-dashboard-{uuid4().hex[:8]}",
            created_by=test_user["id"],
        )
        assert dashboard is not None
        await async_db_session.flush()

        body = {
            "user_id": str(target_user.id),
            "dashboard_id": str(dashboard.id),
            "permission": DashboardPermission.VIEW.value,
        }

        try:
            first = await authenticated_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            second = await authenticated_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )

            assert first.status_code == 200
            assert second.status_code == 200
            assert second.json() == first.json()
            assert first.json()["message"] == "Access granted"
            payload = second.json()
            assert payload["dashboard_id"] == str(dashboard.id)
            assert payload["user_id"] == str(target_user.id)
            assert payload["permission"] == DashboardPermission.VIEW.value

            verify = async_session_maker()
            try:
                result = await verify.execute(
                    select(DashboardAccess).where(
                        DashboardAccess.user_id == target_user.id,
                        DashboardAccess.dashboard_id == dashboard.id,
                    )
                )
                rows = result.scalars().all()
                assert len(rows) == 1
                assert rows[0].permission == DashboardPermission.VIEW
            finally:
                await verify.close()
        finally:
            await _cleanup(async_db_session, dashboard.id, target_user.id)

    @pytest.mark.asyncio
    async def test_grant_twice_is_neither_500_nor_409(
        self, authenticated_client: AsyncClient, async_db_session, async_session_maker,
        test_user: dict,
    ) -> None:
        """Stated negatively on purpose: pins the idempotent-200 contract."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=f"api_grant_status_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert target_user is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"api-grant-status-dashboard-{uuid4().hex[:8]}",
            created_by=test_user["id"],
        )
        assert dashboard is not None
        await async_db_session.flush()

        body = {
            "user_id": str(target_user.id),
            "dashboard_id": str(dashboard.id),
            "permission": DashboardPermission.VIEW.value,
        }

        try:
            await authenticated_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            second = await authenticated_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            assert second.status_code != 500
            assert second.status_code != 409
            assert second.status_code == 200
        finally:
            await _cleanup(async_db_session, dashboard.id, target_user.id)

    @pytest.mark.asyncio
    async def test_path_body_mismatch_still_returns_422(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The documented mismatch branch still renders 422."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=f"api_grant_mismatch_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert target_user is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"api-grant-mismatch-dashboard-{uuid4().hex[:8]}",
            created_by=test_user["id"],
        )
        assert dashboard is not None
        await async_db_session.flush()

        body = {
            "user_id": str(target_user.id),
            "dashboard_id": str(uuid4()),
            "permission": DashboardPermission.VIEW.value,
        }

        try:
            response = await authenticated_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            assert response.status_code == 422
        finally:
            await _cleanup(async_db_session, dashboard.id, target_user.id)

    @pytest.mark.asyncio
    async def test_unknown_dashboard_still_returns_422(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The missing-dashboard case still renders the pre-existing 422.

        Semantically it belongs to phase 12's authorization work; this block does
        not change it, and the test records that it did not move.
        """
        user_repo = UserRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=f"api_grant_unknown_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert target_user is not None
        await async_db_session.flush()

        unknown_dashboard_id = uuid4()
        body = {
            "user_id": str(target_user.id),
            "dashboard_id": str(unknown_dashboard_id),
            "permission": DashboardPermission.VIEW.value,
        }

        try:
            response = await authenticated_client.post(
                f"/dashboards/{unknown_dashboard_id}/access", json=body
            )
            assert response.status_code == 422
        finally:
            await _cleanup(async_db_session, unknown_dashboard_id, target_user.id)
