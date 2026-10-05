"""Route-level contract tests for POST /dashboards/{dashboard_id}/access.

The endpoint had no route-level coverage before this module. Its job is to pin the
chosen contract: a duplicate grant is a 200 idempotent no-op with the same body,
never a 409 and never a 500. The path/body mismatch branch still renders 422, and
the missing-dashboard branch renders 404 (AZ-5 moved it off the old 422).

The audience tests below exist because the admin gate is structurally invisible to
every test that calls through ``authenticated_client``: ``conftest.py::test_user``
is ``role="admin"``, so the bypass in
``core/permissions.py::_check_access_with_session`` short-circuits before any grant
is read. All four pre-existing tests in this module stay green under any audience,
including a wrong one. The audience tests impersonate an explicit caller per test,
so ``require_dashboard_admin_access`` is genuinely exercised end to end.
"""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

from mkobi.core.security import create_access_token
from mkobi.db.models import Dashboard, DashboardAccess, User
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import DashboardPermission, UserRole


async def _impersonate(
    async_client: AsyncClient, user: User
) -> None:
    """Point the client at one explicit caller, replacing any inherited header."""
    token = create_access_token({"user_id": str(user.id), "email": user.email})
    async_client.headers.update({"Authorization": f"Bearer {token}"})


async def _dashboard_access_row_exists(
    async_session_maker, user_id, dashboard_id
) -> bool:
    """Read the grant through an independent session.

    ``expire_on_commit=False`` makes a read-back on the test's own session cached,
    so only a second session can distinguish "the handler never wrote" from "it
    wrote and the session already knows".
    """
    verify = async_session_maker()
    try:
        result = await verify.execute(
            select(DashboardAccess).where(
                DashboardAccess.user_id == user_id,
                DashboardAccess.dashboard_id == dashboard_id,
            )
        )
        return result.scalars().first() is not None
    finally:
        await verify.close()


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
    async def test_unknown_dashboard_returns_404_not_422(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """An admitted caller granting against a non-existent dashboard gets 404.

        AZ-5: the missing-dashboard case used to surface as ``422`` because the
        service raised a bare ``ValueError`` the route mapped to
        ``INSUFFICIENT_PERMISSIONS``. A missing resource is a ``404``; the
        administrator path reaches it because the bypass grants before existence
        is consulted. ``422`` would tell the caller nothing about the actual
        problem.
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
            assert response.status_code == 404
            assert response.status_code != 422
            assert response.json()["code"] == "DASHBOARD_NOT_FOUND"
        finally:
            await _cleanup(async_db_session, unknown_dashboard_id, target_user.id)


class TestGrantAccessAudience:
    """POST /dashboards/{id}/access enforces the ruled owner-or-administrator audience."""

    @pytest.mark.asyncio
    async def test_administrator_who_is_neither_owner_nor_grantee_is_admitted(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """An administrator with no grant row manages access via the admin-role bypass.

        This is the block's only real proof of the bypass: remove
        ``core/permissions.py::_check_access_with_session``'s admin short-circuit and
        this returns 403. Nothing else in the suite catches that.
        """
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"aud_admin_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"aud_admin_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.ADMIN,
        )
        target = await user_repo.create(
            db=async_db_session,
            email=f"aud_admin_target_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert owner is not None and caller is not None and target is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"aud-admin-dashboard-{uuid4().hex[:8]}",
            created_by=owner.id,
        )
        assert dashboard is not None
        await async_db_session.flush()

        await _impersonate(async_client, caller)
        assert not await _dashboard_access_row_exists(async_session_maker, caller.id, dashboard.id)

        body = {
            "user_id": str(target.id),
            "dashboard_id": str(dashboard.id),
            "permission": DashboardPermission.VIEW.value,
        }

        try:
            response = await async_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            assert response.status_code == 200
            assert await _dashboard_access_row_exists(async_session_maker, target.id, dashboard.id)
        finally:
            await _cleanup(async_db_session, dashboard.id, owner.id)
            await _cleanup(async_db_session, uuid4(), caller.id)
            await _cleanup(async_db_session, uuid4(), target.id)

    @pytest.mark.asyncio
    async def test_owner_with_admin_grant_is_admitted(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """A non-admin caller holding an admin grant is admitted.

        The only case that proves the gate reads ``dashboard_access`` at all:
        every other admitted path short-circuits on the bypass.
        """
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        other = await user_repo.create(
            db=async_db_session,
            email=f"aud_owner_other_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"aud_owner_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        target = await user_repo.create(
            db=async_db_session,
            email=f"aud_owner_target_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert other is not None and caller is not None and target is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"aud-owner-dashboard-{uuid4().hex[:8]}",
            created_by=other.id,
        )
        assert dashboard is not None
        await access_repo.grant_access(
            db=async_db_session,
            user_id=caller.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.ADMIN,
        )
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        body = {
            "user_id": str(target.id),
            "dashboard_id": str(dashboard.id),
            "permission": DashboardPermission.VIEW.value,
        }

        try:
            response = await async_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            assert response.status_code == 200
            assert await _dashboard_access_row_exists(async_session_maker, target.id, dashboard.id)
        finally:
            await _cleanup(async_db_session, dashboard.id, other.id)
            await _cleanup(async_db_session, uuid4(), caller.id)
            await _cleanup(async_db_session, uuid4(), target.id)

    @pytest.mark.asyncio
    async def test_grantee_with_view_only_grant_is_refused_and_writes_no_row(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """A caller who holds a row is refused because ``view`` is below ``admin``.

        Proves ``required_permission="admin"`` is enforced, not merely
        "has a row -> admit".
        """
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"aud_view_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"aud_view_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        target = await user_repo.create(
            db=async_db_session,
            email=f"aud_view_target_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert owner is not None and caller is not None and target is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"aud-view-dashboard-{uuid4().hex[:8]}",
            created_by=owner.id,
        )
        assert dashboard is not None
        await access_repo.grant_access(
            db=async_db_session,
            user_id=caller.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.VIEW,
        )
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        body = {
            "user_id": str(target.id),
            "dashboard_id": str(dashboard.id),
            "permission": DashboardPermission.VIEW.value,
        }

        try:
            response = await async_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            assert response.status_code == 403
            assert response.json()["code"] == "PERMISSION_DENIED"
            assert not await _dashboard_access_row_exists(
                async_session_maker, target.id, dashboard.id
            )
        finally:
            await _cleanup(async_db_session, dashboard.id, owner.id)
            await _cleanup(async_db_session, uuid4(), caller.id)
            await _cleanup(async_db_session, uuid4(), target.id)

    @pytest.mark.asyncio
    async def test_user_with_no_grant_is_refused_and_writes_no_row(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """The acceptance criterion: a non-admin with no grant gets 403 and writes nothing."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"aud_none_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"aud_none_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        target = await user_repo.create(
            db=async_db_session,
            email=f"aud_none_target_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert owner is not None and caller is not None and target is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"aud-none-dashboard-{uuid4().hex[:8]}",
            created_by=owner.id,
        )
        assert dashboard is not None
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        body = {
            "user_id": str(target.id),
            "dashboard_id": str(dashboard.id),
            "permission": DashboardPermission.VIEW.value,
        }

        try:
            response = await async_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            assert response.status_code == 403
            assert response.json()["code"] == "PERMISSION_DENIED"
            assert not await _dashboard_access_row_exists(
                async_session_maker, target.id, dashboard.id
            )
        finally:
            await _cleanup(async_db_session, dashboard.id, owner.id)
            await _cleanup(async_db_session, uuid4(), caller.id)
            await _cleanup(async_db_session, uuid4(), target.id)


class TestGrantPermissionVocabularyAtTheBoundary:
    """Out-of-vocabulary ``permission`` values are rejected by Pydantic, not the service.

    Before this block ``AccessGrant.permission`` was a bare ``str`` and the
    service accepted the ``read``/``write`` aliases. Now the model binds the
    native ``DashboardPermission``, so an alias is a 422 and writes no row on
    both the new-row and the existing-row path. The owner-grant on the create
    path is the positive control: a valid grant still writes.
    """

    @pytest.mark.asyncio
    async def test_read_alias_is_rejected_and_writes_no_row(
        self, authenticated_client: AsyncClient, async_db_session, async_session_maker,
        test_user: dict,
    ) -> None:
        """``read`` is not a ``DashboardPermission`` value: 422 with no row written."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=f"vocab_read_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert target_user is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"vocab-read-dashboard-{uuid4().hex[:8]}",
            created_by=test_user["id"],
        )
        assert dashboard is not None
        await async_db_session.flush()

        body = {
            "user_id": str(target_user.id),
            "dashboard_id": str(dashboard.id),
            "permission": "read",
        }

        try:
            response = await authenticated_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            assert response.status_code == 422
            assert not await _dashboard_access_row_exists(
                async_session_maker, target_user.id, dashboard.id
            )
        finally:
            await _cleanup(async_db_session, dashboard.id, target_user.id)

    @pytest.mark.asyncio
    async def test_write_alias_is_rejected_and_writes_no_row(
        self, authenticated_client: AsyncClient, async_db_session, async_session_maker,
        test_user: dict,
    ) -> None:
        """``write`` is not a ``DashboardPermission`` value: 422 with no row written."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=f"vocab_write_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert target_user is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"vocab-write-dashboard-{uuid4().hex[:8]}",
            created_by=test_user["id"],
        )
        assert dashboard is not None
        await async_db_session.flush()

        body = {
            "user_id": str(target_user.id),
            "dashboard_id": str(dashboard.id),
            "permission": "write",
        }

        try:
            response = await authenticated_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            assert response.status_code == 422
            assert not await _dashboard_access_row_exists(
                async_session_maker, target_user.id, dashboard.id
            )
        finally:
            await _cleanup(async_db_session, dashboard.id, target_user.id)

    @pytest.mark.asyncio
    async def test_alias_is_rejected_on_the_existing_row_path(
        self, authenticated_client: AsyncClient, async_db_session, async_session_maker,
        test_user: dict,
    ) -> None:
        """On an existing row the alias is still 422 and the stored row is untouched."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=f"vocab_existing_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert target_user is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"vocab-existing-dashboard-{uuid4().hex[:8]}",
            created_by=test_user["id"],
        )
        assert dashboard is not None
        await access_repo.grant_access(
            db=async_db_session,
            user_id=target_user.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.VIEW,
        )
        await async_db_session.commit()

        body = {
            "user_id": str(target_user.id),
            "dashboard_id": str(dashboard.id),
            "permission": "write",
        }

        try:
            response = await authenticated_client.post(
                f"/dashboards/{dashboard.id}/access", json=body
            )
            assert response.status_code == 422

            verify = async_session_maker()
            try:
                result = await verify.execute(
                    select(DashboardAccess).where(
                        DashboardAccess.user_id == target_user.id,
                        DashboardAccess.dashboard_id == dashboard.id,
                    )
                )
                stored = result.scalar_one()
                assert stored.permission == DashboardPermission.VIEW
            finally:
                await verify.close()
        finally:
            await _cleanup(async_db_session, dashboard.id, target_user.id)

    @pytest.mark.asyncio
    async def test_create_path_still_writes_the_owner_grant(
        self, authenticated_client: AsyncClient, async_db_session, async_session_maker,
        test_user: dict,
    ) -> None:
        """The create path's owner-grant is a valid write and still lands."""
        body = {
            "name": f"vocab-owner-grant-{uuid4().hex[:8]}",
            "config": {"graph_types": ["bar"]},
        }

        response = await authenticated_client.post("/dashboards/", json=body)
        assert response.status_code == 201
        dashboard_id = response.json()["id"]

        try:
            assert await _dashboard_access_row_exists(
                async_session_maker, test_user["id"], UUID(dashboard_id)
            )
        finally:
            await _cleanup(async_db_session, UUID(dashboard_id), test_user["id"])


class TestListAccessAudience:
    """GET /dashboards/{id}/access enforces the ruled owner-or-administrator audience."""

    @pytest.mark.asyncio
    async def test_administrator_who_is_neither_owner_nor_grantee_may_list(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """The admin-role bypass admits an administrator on the read surface too."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"list_admin_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"list_admin_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.ADMIN,
        )
        assert owner is not None and caller is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"list-admin-dashboard-{uuid4().hex[:8]}",
            created_by=owner.id,
        )
        assert dashboard is not None
        await access_repo.grant_access(
            db=async_db_session,
            user_id=owner.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.ADMIN,
        )
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        try:
            response = await async_client.get(f"/dashboards/{dashboard.id}/access")
            assert response.status_code == 200
            payload = response.json()
            assert isinstance(payload, list)
            assert any(record["user_id"] == str(owner.id) for record in payload)
        finally:
            await _cleanup(async_db_session, dashboard.id, owner.id)
            await _cleanup(async_db_session, uuid4(), caller.id)

    @pytest.mark.asyncio
    async def test_user_with_no_grant_is_refused(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """A caller outside the audience gets 403, not the old ``200 []`` oracle."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"list_none_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"list_none_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        assert owner is not None and caller is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"list-none-dashboard-{uuid4().hex[:8]}",
            created_by=owner.id,
        )
        assert dashboard is not None
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        try:
            response = await async_client.get(f"/dashboards/{dashboard.id}/access")
            assert response.status_code == 403
            assert response.json()["code"] == "PERMISSION_DENIED"
        finally:
            await _cleanup(async_db_session, dashboard.id, owner.id)
            await _cleanup(async_db_session, uuid4(), caller.id)

    @pytest.mark.asyncio
    async def test_empty_list_is_200_not_a_refusal(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """An admitted caller on a rowless dashboard gets 200 [], never 403.

        AZ-5: the ACL read stays 200 with an empty list. The distinction the
        contract now states is that ``200 []`` means "no access rows", while a
        caller outside the audience gets 403 regardless of row count. This pins
        the half that could regress: an empty ACL must not be rendered as a
        refusal.

        The caller is an administrator, whose bypass admits it without any grant
        row of its own, so the dashboard genuinely has zero access rows.
        """
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"empty_list_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"empty_list_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.ADMIN,
        )
        assert owner is not None and caller is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"empty-list-dashboard-{uuid4().hex[:8]}",
            created_by=owner.id,
        )
        assert dashboard is not None
        await async_db_session.flush()

        await _impersonate(async_client, caller)

        try:
            response = await async_client.get(f"/dashboards/{dashboard.id}/access")
            assert response.status_code == 200
            payload = response.json()
            assert payload == []
        finally:
            await _cleanup(async_db_session, dashboard.id, owner.id)
            await _cleanup(async_db_session, uuid4(), caller.id)



class TestRevokeAccessAudience:
    """DELETE /dashboards/{id}/access/{user_id} enforces the ruled audience."""

    @pytest.mark.asyncio
    async def test_administrator_who_is_neither_owner_nor_grantee_may_revoke(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """An administrator may revoke; the target row is gone when read independently."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"rev_admin_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"rev_admin_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.ADMIN,
        )
        target = await user_repo.create(
            db=async_db_session,
            email=f"rev_admin_target_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert owner is not None and caller is not None and target is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"rev-admin-dashboard-{uuid4().hex[:8]}",
            created_by=owner.id,
        )
        assert dashboard is not None
        await access_repo.grant_access(
            db=async_db_session,
            user_id=target.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.VIEW,
        )
        # Commit so the pre-existing grant row is durable and visible to the
        # independent session below; the survival check needs a real stored row.
        await async_db_session.commit()
        assert await _dashboard_access_row_exists(async_session_maker, target.id, dashboard.id)

        await _impersonate(async_client, caller)

        try:
            response = await async_client.delete(
                f"/dashboards/{dashboard.id}/access/{target.id}"
            )
            assert response.status_code == 200
            assert not await _dashboard_access_row_exists(
                async_session_maker, target.id, dashboard.id
            )
        finally:
            await _cleanup(async_db_session, dashboard.id, owner.id)
            await _cleanup(async_db_session, uuid4(), caller.id)
            await _cleanup(async_db_session, uuid4(), target.id)

    @pytest.mark.asyncio
    async def test_user_with_no_grant_is_refused_and_the_row_survives(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """403, and the pre-existing grant row survives, proving the body never ran."""
        user_repo = UserRepository()
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        owner = await user_repo.create(
            db=async_db_session,
            email=f"rev_none_owner_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        caller = await user_repo.create(
            db=async_db_session,
            email=f"rev_none_caller_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.EDITOR,
        )
        target = await user_repo.create(
            db=async_db_session,
            email=f"rev_none_target_{uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        assert owner is not None and caller is not None and target is not None
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"rev-none-dashboard-{uuid4().hex[:8]}",
            created_by=owner.id,
        )
        assert dashboard is not None
        await access_repo.grant_access(
            db=async_db_session,
            user_id=target.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.VIEW,
        )
        # Commit so the pre-existing grant row is durable and visible to the
        # independent session below; the survival check needs a real stored row.
        await async_db_session.commit()
        assert await _dashboard_access_row_exists(async_session_maker, target.id, dashboard.id)

        await _impersonate(async_client, caller)

        try:
            response = await async_client.delete(
                f"/dashboards/{dashboard.id}/access/{target.id}"
            )
            assert response.status_code == 403
            assert response.json()["code"] == "PERMISSION_DENIED"
            assert await _dashboard_access_row_exists(
                async_session_maker, target.id, dashboard.id
            )
        finally:
            await _cleanup(async_db_session, dashboard.id, owner.id)
            await _cleanup(async_db_session, uuid4(), caller.id)
            await _cleanup(async_db_session, uuid4(), target.id)
