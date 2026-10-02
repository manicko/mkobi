"""Tests for users API endpoints."""

import uuid
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import delete, select

from mkobi.core.security import hash_password
from mkobi.db.models import user as user_model
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import UserRole


async def _read_role_in_new_session(async_session_maker, user_id: uuid.UUID) -> UserRole | None:
    """Re-read a user's role through a second session, independent of the request's."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(user_model.User.role).where(user_model.User.id == user_id)
        )
        return result.scalar_one_or_none()


async def _delete_committed_email(async_session_maker, email: str) -> None:
    """Delete a row committed by this test; a production commit is durable here."""
    async with async_session_maker() as session:
        await session.execute(
            delete(user_model.User).where(user_model.User.email == email)
        )
        await session.commit()


class TestGetProfile:
    """Tests for get profile endpoint."""

    async def test_get_own_profile(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test getting own profile via /auth/me."""
        login_resp = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        token = login_resp.json()["access_token"]

        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == test_user["email"]
        assert data["role"] == test_user["role"]

    async def test_get_profile_unauthorized(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting profile without token."""
        response = await async_client.get("/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUpdateUserRoleDeprecatedPut:
    """Tests for the deprecated PUT /users/{user_id} surface.

    This endpoint reaches UserService.update_user_role and had no test caller at
    all; it is one of the four endpoints whose write was not committed.
    """

    async def test_deprecated_put_updates_role_durably(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """PUT /users/{user_id} returns the updated role and commits it."""
        repo = UserRepository()
        target_email = f"deprecated_put_{uuid.uuid4().hex[:8]}@example.com"
        target = await repo.create(
            db=async_db_session,
            email=target_email,
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        try:
            response = await async_client.put(
                f"/users/{target.id}",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={"role": UserRole.EDITOR},
            )
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["role"] == UserRole.EDITOR

            # Committed, not merely flushed.
            committed_role = await _read_role_in_new_session(
                async_session_maker, target.id
            )
            assert committed_role == UserRole.EDITOR
        finally:
            # The request shares this session. A failed durability assertion
            # leaves the uncommitted UPDATE holding a row lock, so release it
            # before the cleanup DELETE or a regression would hang here
            # instead of reporting red.
            await async_db_session.rollback()
            await _delete_committed_email(async_session_maker, target_email)


class TestDeleteAccount:
    """Tests for self-deletion endpoint."""

    async def test_delete_own_account(
        self, async_client: AsyncClient, test_user: dict, async_db_session
    ) -> None:
        """Test deleting own account via /users/me."""
        login_resp = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        token = login_resp.json()["access_token"]

        response = await async_client.delete(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

        login_resp = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        assert login_resp.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_delete_account_unauthorized(
        self, async_client: AsyncClient
    ) -> None:
        """Test deleting account without token."""
        response = await async_client.delete("/users/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_admin_cannot_delete_self(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test that admin cannot delete their own account when they are the only admin.

        The _check_admin_deletion_allowed function blocks deletion when:
        - total users > 1 (other users exist)
        - admin count <= 1 (this admin is the sole admin)
        """
        repo = UserRepository()

        # Clean the slate: delete all existing users
        all_users = await repo.get_all(async_db_session)
        for user in all_users:
            await repo.delete(user.id, async_db_session)
        await async_db_session.commit()

        # Verify cleanup
        remaining = await repo.get_all(async_db_session)
        assert len(remaining) == 0, "Database cleanup failed"

        # Create a sole admin user
        admin_user = await repo.create(
            db=async_db_session,
            email=f"sole_admin_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        # Create a non-admin user
        await repo.create(
            db=async_db_session,
            email=f"viewer_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Verify state: 2 users, 1 admin
        all_after = await repo.get_all(async_db_session)
        admins = [u for u in all_after if u.role == UserRole.ADMIN]
        assert len(all_after) == 2, f"Expected 2 users, got {len(all_after)}"
        assert len(admins) == 1, f"Expected 1 admin, got {len(admins)}"

        # Login as the admin
        login_resp = await async_client.post(
            "/auth/login",
            json={
                "email": admin_user.email,
                "password": "AdminPass123!",
            },
        )
        assert login_resp.status_code == status.HTTP_200_OK
        token = login_resp.json()["access_token"]

        # Attempt to delete own admin account
        response = await async_client.delete(
            f"/users/{admin_user.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Should be forbidden: sole admin cannot be deleted while users exist
        assert response.status_code == status.HTTP_403_FORBIDDEN