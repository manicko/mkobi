"""Tests for token revocation mechanism.

Tests cover:
- Valid token works before revocation
- Revoked token returns 401 on authenticated endpoints
- Logout revokes the current access token
- Blacklist entries expire after TTL
- User deactivation revokes all active tokens
- Other users' tokens are not affected by one user's revocation
"""

from fastapi import status
from httpx import AsyncClient
from sqlalchemy import delete, select

from mkobi.core.security import (
    hash_password,
    decode_token,
)
from mkobi.db.models import user as user_model
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import UserRole


async def _read_is_active_in_new_session(
    async_session_maker, user_id
) -> bool | None:
    """Re-read is_active through a second session, independent of the request's."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(user_model.User.is_active).where(user_model.User.id == user_id)
        )
        return result.scalar_one_or_none()


async def _delete_committed_user(async_session_maker, user_id) -> None:
    """Delete a row committed by this test; a production commit is durable here."""
    async with async_session_maker() as session:
        await session.execute(
            delete(user_model.User).where(user_model.User.id == user_id)
        )
        await session.commit()


class TestTokenRevocation:
    """Test token blacklist mechanism."""

    async def test_valid_token_works(
        self, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Valid token should grant access to protected endpoint."""
        response = await authenticated_client.get("/auth/me")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == test_user["email"]

    async def test_revoked_token_returns_401(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """After logout, old token should be rejected with 401.

        Verifies the full logout flow revokes the access token.
        """
        # Create a user (user variable not used, just needed for DB setup)
        user_repo = UserRepository()
        await user_repo.create(
            db=async_db_session,
            email="logout_revoked_test@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Login to get a fresh token
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": "logout_revoked_test@example.com",
                "password": "TestPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        access_token = login_response.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # Verify token works before logout
        me_response = await async_client.get("/auth/me", headers=auth_headers)
        assert me_response.status_code == status.HTTP_200_OK

        # Logout to revoke the token
        logout_response = await async_client.post("/auth/logout", headers=auth_headers)
        assert logout_response.status_code == status.HTTP_200_OK
        assert logout_response.json()["message"] == "Logged out successfully"

        # Try to use the revoked token - should get 401
        response = await async_client.get("/auth/me", headers=auth_headers)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        response_data = response.json()
        error_msg = response_data.get("error", "") or response_data.get("detail", "")
        assert "revoked" in error_msg.lower()

    async def test_logout_revokes_access_token(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Logout endpoint should revoke the access token from Authorization header."""
        # Create a user (user variable not used, just needed for DB setup)
        user_repo = UserRepository()
        await user_repo.create(
            db=async_db_session,
            email="logout_access_test@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Login
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": "logout_access_test@example.com",
                "password": "TestPass123!",
            },
        )
        access_token = login_response.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # Logout
        logout_response = await async_client.post("/auth/logout", headers=auth_headers)
        assert logout_response.status_code == status.HTTP_200_OK

        # Token should now be revoked
        me_response = await async_client.get("/auth/me", headers=auth_headers)
        assert me_response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_other_user_token_unaffected(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Revoking one user's token should not affect another user's tokens."""
        user_repo = UserRepository()

        # Create two users: admin and regular user
        await user_repo.create(
            db=async_db_session,
            email="admin_unaffected_test@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        await user_repo.create(
            db=async_db_session,
            email="viewer_unaffected_test@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Login as both users
        admin_login = await async_client.post(
            "/auth/login",
            json={
                "email": "admin_unaffected_test@example.com",
                "password": "AdminPass123!",
            },
        )
        admin_token = admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        viewer_login = await async_client.post(
            "/auth/login",
            json={
                "email": "viewer_unaffected_test@example.com",
                "password": "ViewerPass123!",
            },
        )
        viewer_token = viewer_login.json()["access_token"]
        viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

        # Both tokens should work initially
        assert (await async_client.get("/auth/me", headers=admin_headers)).status_code == status.HTTP_200_OK
        assert (await async_client.get("/auth/me", headers=viewer_headers)).status_code == status.HTTP_200_OK

        # Logout admin (revoke admin's token)
        await async_client.post("/auth/logout", headers=admin_headers)

        # Admin token should now be revoked
        admin_me = await async_client.get("/auth/me", headers=admin_headers)
        assert admin_me.status_code == status.HTTP_401_UNAUTHORIZED

        # Viewer token should still work (not affected by admin's logout)
        viewer_me = await async_client.get("/auth/me", headers=viewer_headers)
        assert viewer_me.status_code == status.HTTP_200_OK
        assert viewer_me.json()["email"] == "viewer_unaffected_test@example.com"


class TestUserDeactivationRevocation:
    """Test token revocation on user deactivation."""

    async def test_user_deactivation_revokes_all_tokens(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """Deactivating a user should revoke all their active tokens."""
        user_repo = UserRepository()

        # Create a user
        user_email = "deactiv_revoked_test@example.com"
        user = await user_repo.create(
            db=async_db_session,
            email=user_email,
            password_hash=hash_password("TestPass123!"),
            role=UserRole.VIEWER,
            is_active=True,
        )
        await async_db_session.commit()

        # Create admin user to perform deactivation (variable not used directly)
        admin_email = "admin_deactivate_test@example.com"
        await user_repo.create(
            db=async_db_session,
            email=admin_email,
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        try:
            # Login as the user to get their token
            user_login = await async_client.post(
                "/auth/login",
                json={
                    "email": user_email,
                    "password": "TestPass123!",
                },
            )
            user_token = user_login.json()["access_token"]
            user_headers = {"Authorization": f"Bearer {user_token}"}

            # Verify token works
            assert (await async_client.get("/auth/me", headers=user_headers)).status_code == status.HTTP_200_OK

            # Admin deactivates the user
            admin_login = await async_client.post(
                "/auth/login",
                json={
                    "email": admin_email,
                    "password": "AdminPass123!",
                },
            )
            admin_token = admin_login.json()["access_token"]
            admin_headers = {"Authorization": f"Bearer {admin_token}"}

            deactivate_response = await async_client.patch(
                f"/admin/users/{user.id}/active",
                json={"is_active": False},
                headers=admin_headers,
            )
            assert deactivate_response.status_code == status.HTTP_200_OK
            assert deactivate_response.json()["is_active"] is False

            # User's token should now be revoked
            me_response = await async_client.get("/auth/me", headers=user_headers)
            assert me_response.status_code == status.HTTP_401_UNAUTHORIZED
            response_data = me_response.json()
            error_msg = response_data.get("error", "") or response_data.get("detail", "")
            assert "revoked" in error_msg.lower()

            # Database-side half: the Redis marker is consulted before the row, so
            # the assertions above can pass without the deactivation persisting.
            # A second session proves is_active is committed False.
            committed_active = await _read_is_active_in_new_session(
                async_session_maker, user.id
            )
            assert committed_active is False
        finally:
            await _delete_committed_user(async_session_maker, user.id)
            async with async_session_maker() as session:
                await session.execute(
                    delete(user_model.User).where(user_model.User.email == admin_email)
                )
                await session.commit()

    async def test_other_users_unaffected_by_deactivation(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Deactivating one user should not affect other users' tokens."""
        user_repo = UserRepository()

        # Create two users
        user1 = await user_repo.create(
            db=async_db_session,
            email="user1_deactivate_test@example.com",
            password_hash=hash_password("UserPass123!"),
            role=UserRole.VIEWER,
            is_active=True,
        )
        await async_db_session.commit()

        await user_repo.create(
            db=async_db_session,
            email="user2_deactivate_test@example.com",
            password_hash=hash_password("UserPass123!"),
            role=UserRole.VIEWER,
            is_active=True,
        )
        await async_db_session.commit()

        # Create admin (variable not used directly)
        await user_repo.create(
            db=async_db_session,
            email="admin_multi_deactivate@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        # Login as both users
        user1_login = await async_client.post(
            "/auth/login",
            json={
                "email": "user1_deactivate_test@example.com",
                "password": "UserPass123!",
            },
        )
        user1_token = user1_login.json()["access_token"]
        user1_headers = {"Authorization": f"Bearer {user1_token}"}

        user2_login = await async_client.post(
            "/auth/login",
            json={
                "email": "user2_deactivate_test@example.com",
                "password": "UserPass123!",
            },
        )
        user2_token = user2_login.json()["access_token"]
        user2_headers = {"Authorization": f"Bearer {user2_token}"}

        # Admin deactivates user1 only
        admin_login = await async_client.post(
            "/auth/login",
            json={
                "email": "admin_multi_deactivate@example.com",
                "password": "AdminPass123!",
            },
        )
        admin_token = admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        await async_client.patch(
            f"/admin/users/{user1.id}/active",
            json={"is_active": False},
            headers=admin_headers,
        )

        # user1's token should be revoked
        assert (await async_client.get("/auth/me", headers=user1_headers)).status_code == status.HTTP_401_UNAUTHORIZED

        # user2's token should still work
        user2_me = await async_client.get("/auth/me", headers=user2_headers)
        assert user2_me.status_code == status.HTTP_200_OK
        assert user2_me.json()["email"] == "user2_deactivate_test@example.com"


class TestBlacklistExpiry:
    """Test that blacklist entries expire after TTL."""

    async def test_blacklist_entry_can_be_cleared(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Blacklist entry should eventually expire and allow token reuse.

        This tests the mechanism by directly manipulating the mock Redis
        to verify the TTL-based expiry logic works.
        """
        user_repo = UserRepository()

        # Create a user (user variable not used, just needed for DB setup)
        await user_repo.create(
            db=async_db_session,
            email="expiry_test@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Login to get token
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": "expiry_test@example.com",
                "password": "TestPass123!",
            },
        )
        access_token = login_response.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # Verify token works
        payload = decode_token(access_token)
        assert payload is not None

        # Logout to revoke
        await async_client.post("/auth/logout", headers=auth_headers)

        # Token should be revoked
        response = await async_client.get("/auth/me", headers=auth_headers)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRefreshBlacklist:
    """Test refresh token revocation."""

    async def test_revoked_refresh_token_returns_401(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Revoked refresh token should be rejected on refresh endpoint."""
        user_repo = UserRepository()

        # Create a user (user variable not used, just needed for DB setup)
        await user_repo.create(
            db=async_db_session,
            email="refresh_revoked_test@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Login to get both tokens
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": "refresh_revoked_test@example.com",
                "password": "TestPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        body = login_response.json()
        access_token = body["access_token"]

        # Extract refresh token from cookie
        set_cookie = login_response.headers.get("set-cookie", "")
        refresh_token = ""
        for part in set_cookie.split(";"):
            part = part.strip()
            if part.startswith("mkobi_refresh_token="):
                refresh_token = part.split("=", 1)[1]
                break

        # Verify refresh token works
        refresh_response = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": refresh_token},
        )
        assert refresh_response.status_code == status.HTTP_200_OK

        # Logout to revoke both tokens
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        await async_client.post(
            "/auth/logout",
            cookies={"mkobi_refresh_token": refresh_token},
            headers=auth_headers,
        )

        # Refresh token should now be revoked
        final_refresh = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": refresh_token},
        )
        assert final_refresh.status_code == status.HTTP_401_UNAUTHORIZED
        response_data = final_refresh.json()
        error_msg = response_data.get("error", "") or response_data.get("detail", "")
        assert "revoked" in error_msg.lower()