"""Integration tests for admin user management endpoints.

Tests cover:
- List users (admin only)
- Create user (admin only)
- Update user role (admin only)
- Deactivate/Reactivate user (admin only)
- Reset user password (admin only)
- Authorization: non-admin cannot access admin endpoints
"""

import uuid

from fastapi import status
from httpx import AsyncClient
from sqlalchemy import delete, select

from mkobi.core.security import create_access_token, hash_password
from mkobi.db.models import user as user_model
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import UserRole
from tests.conftest import MockRedis


async def _read_is_active_in_new_session(
    async_session_maker, user_id: uuid.UUID
) -> bool | None:
    """Re-read is_active through a second session, independent of the request's.

    The request session is the test session (conftest overrides the dependency),
    so a re-read through it proves nothing. A second session sees only committed
    rows, which is what distinguishes a durable write from a flushed one.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(user_model.User.is_active).where(user_model.User.id == user_id)
        )
        return result.scalar_one_or_none()


async def _read_role_in_new_session(
    async_session_maker, user_id: uuid.UUID
) -> UserRole | None:
    """Re-read role through a second session, independent of the request's."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(user_model.User.role).where(user_model.User.id == user_id)
        )
        return result.scalar_one_or_none()


async def _read_email_in_new_session(
    async_session_maker, email: str
) -> uuid.UUID | None:
    """Return a committed row's id for an email, or None, from a second session."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(user_model.User.id).where(user_model.User.email == email)
        )
        return result.scalar_one_or_none()


async def _delete_committed_email(async_session_maker, email: str) -> None:
    """Delete a row committed by a test in this suite.

    A production commit in this harness is durable and the fixture's teardown
    rollback cannot undo it, so any test that commits must clean up after itself.
    """
    async with async_session_maker() as session:
        await session.execute(
            delete(user_model.User).where(user_model.User.email == email)
        )
        await session.commit()


class TestListUsers:
    """Tests for GET /admin/users endpoint."""

    async def test_list_users_admin(
        self, async_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Test admin can list all users."""
        user_repo = UserRepository()
        # Create additional user for testing
        await user_repo.create(
            db=async_db_session,
            email="list_test_user@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # test_user is admin, use its token
        response = await async_client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # At least test_user + list_test_user

    async def test_list_users_non_admin_forbidden(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test non-admin cannot list users."""
        user_repo = UserRepository()
        # Create a viewer user
        viewer = await user_repo.create(
            db=async_db_session,
            email="viewer_list@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        viewer_token = create_access_token({
            "user_id": str(viewer.id),
            "email": viewer.email,
        })

        response = await async_client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestCreateUser:
    """Tests for POST /users endpoint (admin only)."""

    async def test_create_user_admin(
        self, async_client: AsyncClient, async_session_maker, test_user: dict
    ) -> None:
        """Test admin can create a new user."""
        email = f"created_{uuid.uuid4().hex[:8]}@example.com"
        try:
            response = await async_client.post(
                "/users/",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "email": email,
                    "password": "NewUserPass123!",
                    "role": UserRole.VIEWER,
                },
            )
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["email"] == email
            assert data["role"] == UserRole.VIEWER
        finally:
            await _delete_committed_email(async_session_maker, email)

    async def test_create_user_editor_role(
        self, async_client: AsyncClient, async_session_maker, test_user: dict
    ) -> None:
        """Test admin can create editor user."""
        email = f"editor_{uuid.uuid4().hex[:8]}@example.com"
        try:
            response = await async_client.post(
                "/users/",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "email": email,
                    "password": "EditorPass123!",
                    "role": UserRole.EDITOR,
                },
            )
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["role"] == UserRole.EDITOR
        finally:
            await _delete_committed_email(async_session_maker, email)

    async def test_create_user_duplicate_email(
        self,
        async_client: AsyncClient,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """Test creating user with existing email returns validation error."""
        email = f"duplicate_{uuid.uuid4().hex[:8]}@example.com"
        try:
            # First create a user. Its response was previously discarded; assert it
            # actually committed, or the second create could pass having created
            # nothing.
            first = await async_client.post(
                "/users/",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "email": email,
                    "password": "Pass123!",
                    "role": UserRole.VIEWER,
                },
            )
            assert first.status_code == status.HTTP_201_CREATED

            committed_id = await _read_email_in_new_session(async_session_maker, email)
            assert committed_id is not None, "first create did not commit"

            # Try to create another with same email - returns 422 because ValueError
            # is raised (duplicate email is reported as a validation error (422)).
            response = await async_client.post(
                "/users/",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "email": email,
                    "password": "AnotherPass123!",
                    "role": UserRole.VIEWER,
                },
            )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        finally:
            await _delete_committed_email(async_session_maker, email)

    async def test_create_user_duplicate_email_race_returns_422(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """An IntegrityError from the unique index surfaces as 422, not 500.

        The repository double returns None from the *first* get_by_email call only,
        defeating the application-level pre-check so the real flush hits the unique
        index. Every other call delegates to the real repository.
        """
        from mkobi.api.deps import get_user_service
        from mkobi.main import app
        from mkobi.services.user_service import UserService

        email = f"race_{uuid.uuid4().hex[:8]}@example.com"
        repo = UserRepository()

        # Seed the winning row so the insert loses the race.
        await repo.create(
            db=async_db_session,
            email=email,
            password_hash=hash_password("WinnerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        state = {"pre_checks": 0}
        real_get_by_email = repo.get_by_email

        async def _defeat_precheck_once(target_email: str, db):
            if target_email == email:
                state["pre_checks"] += 1
                if state["pre_checks"] == 1:
                    return None
            return await real_get_by_email(target_email, db)

        repo.get_by_email = _defeat_precheck_once  # type: ignore[method-assign]
        service = UserService(repo)
        app.dependency_overrides[get_user_service] = lambda: service

        try:
            response = await async_client.post(
                "/users/",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "email": email,
                    "password": "LoserPass123!",
                    "role": UserRole.VIEWER,
                },
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
            assert response.json()["code"] == "VALIDATION_ERROR"

            # Exactly one row exists: the rollback discarded the failed insert.
            async with async_session_maker() as session:
                rows = await session.execute(
                    select(user_model.User.id).where(user_model.User.email == email)
                )
                assert len(list(rows.scalars().all())) == 1

            # The session must remain usable: the classifier's rollback is what
            # prevents PendingRollbackError poisoning every later test.
            probe = await async_db_session.execute(select(user_model.User.id))
            _ = probe.scalars().all()
        finally:
            app.dependency_overrides.pop(get_user_service, None)
            await _delete_committed_email(async_session_maker, email)

    async def test_create_user_non_duplicate_integrity_error_returns_500(
        self,
        async_client: AsyncClient,
        async_db_session,
        test_user: dict,
    ) -> None:
        """An IntegrityError that is not the duplicate-email race still returns 500.

        Same double, but the re-read also returns None, so the classifier re-raises
        the driver error unchanged.
        """
        from sqlalchemy.exc import IntegrityError

        from mkobi.api.deps import get_user_service
        from mkobi.main import app
        from mkobi.services.user_service import UserService

        email = f"nondz_{uuid.uuid4().hex[:8]}@example.com"
        repo = UserRepository()

        async def _always_none(target_email: str, db):
            if target_email == email:
                return None
            return await real_get_by_email(target_email, db)

        async def _raise_integrity_error(**kwargs):
            raise IntegrityError("stmt", {}, Exception("not a unique conflict"))

        real_get_by_email = repo.get_by_email
        repo.get_by_email = _always_none  # type: ignore[method-assign]
        repo.create = _raise_integrity_error  # type: ignore[method-assign]
        service = UserService(repo)
        app.dependency_overrides[get_user_service] = lambda: service

        try:
            response = await async_client.post(
                "/users/",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={
                    "email": email,
                    "password": "Pass123!",
                    "role": UserRole.VIEWER,
                },
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert response.json()["code"] == "INTERNAL_ERROR"
        finally:
            app.dependency_overrides.pop(get_user_service, None)

    async def test_create_user_non_admin_forbidden(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test non-admin cannot create users."""
        user_repo = UserRepository()
        # Create a viewer user
        viewer = await user_repo.create(
            db=async_db_session,
            email="viewer_create2@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        viewer_token = create_access_token({
            "user_id": str(viewer.id),
            "email": viewer.email,
        })

        response = await async_client.post(
            "/users/",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={
                "email": "should_fail2@example.com",
                "password": "Pass123!",
                "role": UserRole.VIEWER,
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestUpdateUserRole:
    """Tests for PATCH /admin/users/{user_id}/role endpoint."""

    async def test_update_user_role_admin(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """Test admin can update user role."""
        user_repo = UserRepository()
        # Create a viewer user
        target_email = f"role_target_{uuid.uuid4().hex[:8]}@example.com"
        target_user = await user_repo.create(
            db=async_db_session,
            email=target_email,
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        try:
            response = await async_client.patch(
                f"/admin/users/{target_user.id}/role",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={"role": UserRole.EDITOR},
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["role"] == UserRole.EDITOR

            # Committed, not merely flushed: a second session must see the new role.
            committed_role = await _read_role_in_new_session(
                async_session_maker, target_user.id
            )
            assert committed_role == UserRole.EDITOR
        finally:
            await _delete_committed_email(async_session_maker, target_email)

    async def test_update_user_role_to_admin(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """Test admin can promote user to admin role."""
        user_repo = UserRepository()
        # Create a viewer user
        target_email = f"promote_{uuid.uuid4().hex[:8]}@example.com"
        target_user = await user_repo.create(
            db=async_db_session,
            email=target_email,
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        try:
            response = await async_client.patch(
                f"/admin/users/{target_user.id}/role",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={"role": UserRole.ADMIN},
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["role"] == UserRole.ADMIN

            committed_role = await _read_role_in_new_session(
                async_session_maker, target_user.id
            )
            assert committed_role == UserRole.ADMIN
        finally:
            await _delete_committed_email(async_session_maker, target_email)

    async def test_update_user_role_nonexistent_user(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test updating role of non-existent user returns error."""
        # The endpoint returns 404 as USER_NOT_FOUND when user doesn't exist
        response = await async_client.patch(
            f"/admin/users/{uuid.uuid4()}/role",
            headers={"Authorization": f"Bearer {test_user['token']}"},
            json={"role": UserRole.EDITOR},
        )
        # Error code should be USER_NOT_FOUND or NOT_FOUND
        assert response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_500_INTERNAL_SERVER_ERROR)

    async def test_update_user_role_non_admin_forbidden(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test non-admin cannot update user role."""
        user_repo = UserRepository()

        # Create a viewer who will try to update roles
        viewer = await user_repo.create(
            db=async_db_session,
            email="viewer_role_update2@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        # Create another user to target
        target = await user_repo.create(
            db=async_db_session,
            email="role_update_target3@example.com",
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        viewer_token = create_access_token({
            "user_id": str(viewer.id),
            "email": viewer.email,
        })

        response = await async_client.patch(
            f"/admin/users/{target.id}/role",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"role": UserRole.EDITOR},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestDeactivateUser:
    """Tests for PATCH /admin/users/{user_id}/active endpoint."""

    async def test_deactivate_user_admin(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """Test admin can deactivate user."""
        user_repo = UserRepository()
        # Create a viewer user
        target_email = f"deactivate_{uuid.uuid4().hex[:8]}@example.com"
        target_user = await user_repo.create(
            db=async_db_session,
            email=target_email,
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        try:
            response = await async_client.patch(
                f"/admin/users/{target_user.id}/active",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={"is_active": False},
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_active"] is False

            # The deactivation must be durable, not merely flushed.
            committed_active = await _read_is_active_in_new_session(
                async_session_maker, target_user.id
            )
            assert committed_active is False
        finally:
            await _delete_committed_email(async_session_maker, target_email)

    async def test_reactivate_user_admin(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """Test admin can reactivate user."""
        user_repo = UserRepository()
        # Create a deactivated user
        target_email = f"reactivate_{uuid.uuid4().hex[:8]}@example.com"
        target_user = await user_repo.create(
            db=async_db_session,
            email=target_email,
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await user_repo.update(target_user.id, async_db_session, is_active=False)
        await async_db_session.commit()

        try:
            response = await async_client.patch(
                f"/admin/users/{target_user.id}/active",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={"is_active": True},
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["is_active"] is True

            committed_active = await _read_is_active_in_new_session(
                async_session_maker, target_user.id
            )
            assert committed_active is True
        finally:
            await _delete_committed_email(async_session_maker, target_email)

    async def test_deactivate_nonexistent_user(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test deactivating non-existent user returns error."""
        response = await async_client.patch(
            f"/admin/users/{uuid.uuid4()}/active",
            headers={"Authorization": f"Bearer {test_user['token']}"},
            json={"is_active": False},
        )
        # Should be USER_NOT_FOUND
        assert response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_500_INTERNAL_SERVER_ERROR)

    async def test_deactivate_user_non_admin_forbidden(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test non-admin cannot deactivate users."""
        user_repo = UserRepository()

        # Create a viewer who will try to deactivate
        viewer = await user_repo.create(
            db=async_db_session,
            email="viewer_deactivate2@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        # Create another user to target
        target = await user_repo.create(
            db=async_db_session,
            email="deactivate_target3@example.com",
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        viewer_token = create_access_token({
            "user_id": str(viewer.id),
            "email": viewer.email,
        })

        response = await async_client.patch(
            f"/admin/users/{target.id}/active",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"is_active": False},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_deactivation_reports_revocation_failure(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """The deactivation guard stays pinned against regression.

        Same commit-then-revoke ordering as the reset path: a Redis fault at the
        revocation step must be reported as a committed deactivation with a
        failed revocation, naming the partial success. The identical guard on
        the reset path mirrors this one, so this test protects the precedent.
        """
        from mkobi.api.deps import get_redis_client_dependency
        from mkobi.main import app

        target_email = f"deactivate_revoke_fault_{uuid.uuid4().hex[:8]}@example.com"
        user_repo = UserRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=target_email,
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        app.dependency_overrides[get_redis_client_dependency] = (
            lambda: _FaultingRevocationRedis()
        )
        try:
            response = await async_client.patch(
                f"/admin/users/{target_user.id}/active",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={"is_active": False},
            )

            # The deactivation itself committed despite the revocation fault.
            committed_active = await _read_is_active_in_new_session(
                async_session_maker, target_user.id
            )
        finally:
            app.dependency_overrides.pop(get_redis_client_dependency, None)
            await _delete_committed_email(async_session_maker, target_email)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        payload = response.json()
        assert payload["code"] == "INTERNAL_ERROR"
        detail = payload["detail"].lower()
        assert "deactivated successfully" in detail
        assert "revoking the user's tokens failed" in detail
        assert committed_active is False


class _FaultingRevocationRedis(MockRedis):
    """Redis double that faults only on the revocation write.

    The reset/deactivation endpoints call ``revoke_all_user_tokens`` after the
    service has already committed, and that call writes the user-level marker
    with ``setex``. The admin gate for the same request also reads revocation
    state, so a double that faults on *every* operation would break the caller's
    own authentication first and answer 503 before the endpoint runs. Inheriting
    the healthy in-memory reads and faulting only ``setex`` isolates the
    post-commit revocation step, which is the step under test.
    """

    async def setex(self, key: str, ttl: int, value: object) -> None:
        raise RuntimeError("Redis revocation store unreachable")


class TestResetUserPassword:
    """Tests for POST /admin/users/{user_id}/reset-password endpoint."""

    async def test_reset_user_password_admin(
        self, async_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Test admin can reset another user's password."""
        user_repo = UserRepository()
        # Create a target user
        target_user = await user_repo.create(
            db=async_db_session,
            email="password_reset_target2@example.com",
            password_hash=hash_password("OriginalPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        response = await async_client.post(
            f"/admin/users/{target_user.id}/reset-password",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "retrieval_token" in data
        assert "user_id" in data
        assert data["user_id"] == str(target_user.id)

    async def test_admin_reset_password_revokes_target_tokens(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """A successful admin reset withdraws the TARGET user's sessions.

        Behavioural: the target's pre-existing token is refused afterwards. The
        admin's own token is asserted still working, so the test cannot pass by
        revoking the wrong (calling) user. Cleanup removes the committed row.
        """
        target_email = f"reset_revoke_{uuid.uuid4().hex[:8]}@example.com"
        user_repo = UserRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=target_email,
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        try:
            # Target logs in, obtaining a token from before the reset.
            target_login = await async_client.post(
                "/auth/login",
                json={"email": target_email, "password": "TargetPass123!"},
            )
            assert target_login.status_code == status.HTTP_200_OK
            target_token = target_login.json()["access_token"]
            target_headers = {"Authorization": f"Bearer {target_token}"}

            assert (
                await async_client.get("/auth/me", headers=target_headers)
            ).status_code == status.HTTP_200_OK

            # Admin resets the target's password.
            response = await async_client.post(
                f"/admin/users/{target_user.id}/reset-password",
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )
            assert response.status_code == status.HTTP_200_OK

            # The target's pre-existing token is now refused with a revocation error.
            target_me = await async_client.get("/auth/me", headers=target_headers)
            assert target_me.status_code == status.HTTP_401_UNAUTHORIZED
            body = target_me.json()
            error_msg = body.get("error", "") or body.get("detail", "")
            assert "revoked" in error_msg.lower()

            # The administrator was not the one revoked.
            admin_me = await async_client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )
            assert admin_me.status_code == status.HTTP_200_OK
        finally:
            await _delete_committed_email(async_session_maker, target_email)

    async def test_reset_user_password_retrieve_temporary(
        self, async_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Test admin can retrieve temporary password via retrieval token."""
        user_repo = UserRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email="password_retrieve_target2@example.com",
            password_hash=hash_password("OriginalPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Request password reset
        reset_response = await async_client.post(
            f"/admin/users/{target_user.id}/reset-password",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        retrieval_token = reset_response.json()["retrieval_token"]

        # Retrieve the temporary password
        retrieve_response = await async_client.get(
            f"/admin/temp-passwords/{retrieval_token}",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert retrieve_response.status_code == status.HTTP_200_OK
        data = retrieve_response.json()
        assert "temp_password" in data
        assert len(data["temp_password"]) >= 16

    async def test_reset_user_password_nonexistent_user(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test resetting password for non-existent user returns error."""
        response = await async_client.post(
            f"/admin/users/{uuid.uuid4()}/reset-password",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_500_INTERNAL_SERVER_ERROR)

    async def test_reset_user_password_non_admin_forbidden(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test non-admin cannot reset user passwords."""
        user_repo = UserRepository()

        # Create a viewer who will try to reset passwords
        viewer = await user_repo.create(
            db=async_db_session,
            email="viewer_reset_pass2@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        # Create another user to target
        target = await user_repo.create(
            db=async_db_session,
            email="reset_pass_target2@example.com",
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        viewer_token = create_access_token({
            "user_id": str(viewer.id),
            "email": viewer.email,
        })

        response = await async_client.post(
            f"/admin/users/{target.id}/reset-password",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_reset_user_password_cannot_reset_own(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test admin cannot reset their own password via admin endpoint."""
        user_repo = UserRepository()
        # Create an admin user
        admin = await user_repo.create(
            db=async_db_session,
            email="admin_own_reset2@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin.id),
            "email": admin.email,
        })

        response = await async_client.post(
            f"/admin/users/{admin.id}/reset-password",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "own password" in response.json()["detail"].lower()

    async def test_reset_password_reports_revocation_failure(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """A commit-then-revoke fault is reported as a partial success, not a total failure.

        The password reset commits before the endpoint revokes. If revocation
        then faults, the response must tell the operator that the password *was*
        reset and a second reset is required. A blanket handler would return a
        generic "Error resetting user password", which misreports the committed
        reset and hides that a temporary credential is now stranded in Redis; the
        assertion on the detail's meaning is what distinguishes the two.
        """
        from mkobi.api.deps import get_redis_client_dependency
        from mkobi.main import app

        target_email = f"reset_revoke_fault_{uuid.uuid4().hex[:8]}@example.com"
        user_repo = UserRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email=target_email,
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        app.dependency_overrides[get_redis_client_dependency] = (
            lambda: _FaultingRevocationRedis()
        )
        try:
            response = await async_client.post(
                f"/admin/users/{target_user.id}/reset-password",
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )
        finally:
            app.dependency_overrides.pop(get_redis_client_dependency, None)
            await _delete_committed_email(async_session_maker, target_email)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        payload = response.json()
        assert payload["code"] == "INTERNAL_ERROR"
        detail = payload["detail"].lower()
        # The operator is told the reset landed and must be repeated.
        assert "reset successfully" in detail
        assert "second reset" in detail
        # It must not read as if nothing happened.
        assert detail != "error resetting user password"