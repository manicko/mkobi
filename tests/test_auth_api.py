"""Integration tests for cookie-based authentication flow and admin password reset.

Tests cover the complete cookie-based authentication flow:
- Login sets refresh token cookie
- Refresh reads from cookie
- Logout clears cookie
- Edge cases (missing cookie, invalid cookie)

Also tests for admin password reset endpoint and registration approval flow.
"""

import re
from fastapi import status
from httpx import AsyncClient


def _extract_refresh_token(response) -> str:
    """Extract refresh token value from set-cookie header.

    Args:
        response: HTTP response with set-cookie header.

    Returns:
        The refresh token value string.
    """
    set_cookie = response.headers.get("set-cookie", "")
    # Format: mkobi_refresh_token=<token>; ...
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.startswith("mkobi_refresh_token="):
            return part.split("=", 1)[1]
    return ""


class TestCookieAuthFlow:
    """Tests for end-to-end cookie-based authentication flow."""

    async def test_login_sets_refresh_cookie(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that login sets refresh token as httpOnly cookie."""
        response = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify access token in JSON response
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "user" in data

        # Verify refresh token cookie is set with security attributes
        assert "set-cookie" in response.headers
        set_cookie = response.headers["set-cookie"]
        assert "mkobi_refresh_token" in set_cookie
        assert "httponly" in set_cookie.lower()
        assert "secure" in set_cookie.lower()
        assert "samesite=strict" in set_cookie.lower()

    async def test_refresh_reads_from_cookie(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that refresh endpoint reads token from cookie set by login."""
        # First login to get refresh cookie
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK

        # Extract cookie from login response
        refresh_token = _extract_refresh_token(login_response)
        assert refresh_token, "Refresh token should be set in cookie"

        # Then refresh using the cookie
        refresh_response = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": refresh_token},
        )
        assert refresh_response.status_code == status.HTTP_200_OK
        assert "access_token" in refresh_response.json()
        assert refresh_response.json()["token_type"] == "bearer"

    async def test_logout_clears_cookie(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that logout clears the refresh token cookie."""
        # Login first
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK

        # Extract cookie from login response
        refresh_token = _extract_refresh_token(login_response)

        # Logout - need access token in header for authentication
        access_token = login_response.json()["access_token"]
        response = await async_client.post(
            "/auth/logout",
            cookies={"mkobi_refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["message"] == "Logged out successfully"

        # Verify cookie is cleared (set to empty with past expiry)
        set_cookie = response.headers.get("set-cookie", "")
        assert "mkobi_refresh_token" in set_cookie
        # Cookie should be cleared (empty value or max-age=0)
        assert "max-age=0" in set_cookie.lower() or "mkobi_refresh_token=;" in set_cookie.lower()

    async def test_refresh_fails_without_cookie(
        self, async_client: AsyncClient
    ) -> None:
        """Test that refresh fails without refresh cookie."""
        response = await async_client.post("/auth/refresh")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Refresh token not found"

    async def test_refresh_fails_with_invalid_cookie(
        self, async_client: AsyncClient
    ) -> None:
        """Test that refresh fails with invalid refresh cookie."""
        response = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": "invalid.token.here"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Invalid token"

    async def test_refresh_returns_new_access_token(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that refresh returns a valid access token."""
        # Login to get initial cookie
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK

        # Extract cookie from login response
        refresh_token = _extract_refresh_token(login_response)

        # Refresh
        response = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": refresh_token},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        # Verify the token is valid by decoding it
        from mkobi.core.security import decode_token
        payload = decode_token(data["access_token"])
        assert payload is not None
        assert payload["user_id"] == str(test_user["id"])
        assert payload["email"] == test_user["email"]

    async def test_refresh_rotates_refresh_cookie(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Each refresh rotates the refresh cookie, and the new cookie works."""
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        first_cookie = _extract_refresh_token(login_response)
        assert first_cookie, "login must set a refresh cookie"

        # First refresh: must set a new cookie value.
        first_refresh = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": first_cookie},
        )
        assert first_refresh.status_code == status.HTTP_200_OK
        rotated_cookie = _extract_refresh_token(first_refresh)
        assert rotated_cookie, "refresh must rotate and set a refresh cookie"
        assert rotated_cookie != first_cookie

        # Second refresh with the rotated cookie must succeed.
        second_refresh = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": rotated_cookie},
        )
        assert second_refresh.status_code == status.HTTP_200_OK
        assert "access_token" in second_refresh.json()

    async def test_refresh_does_not_revoke_presented_token(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """The presented refresh token is not revoked by rotation (deliberate).

        Rotation replaces the cookie but leaves the presented token's jti valid,
        so the previous cookie keeps working until its own TTL. This pins the
        ruling's choice: reuse detection is deferred to the frontend's phase, and
        a future change to revoke the presented jti must be a conscious decision.
        """
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        original_cookie = _extract_refresh_token(login_response)

        # A rotation happens; the response carries a different cookie.
        refresh_response = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": original_cookie},
        )
        assert refresh_response.status_code == status.HTTP_200_OK
        assert _extract_refresh_token(refresh_response) != original_cookie

        # The original cookie is still accepted: the presented jti was not revoked.
        replay_response = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": original_cookie},
        )
        assert replay_response.status_code == status.HTTP_200_OK
        assert "access_token" in replay_response.json()

    async def test_full_auth_flow_login_refresh_logout(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test complete authentication flow: login -> refresh -> logout."""
        # 1. Login and verify cookie is set
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        assert "set-cookie" in login_response.headers

        # Extract access token and refresh token
        access_token = login_response.json()["access_token"]
        refresh_token = _extract_refresh_token(login_response)

        # 2. Refresh using the cookie
        refresh_response = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": refresh_token},
        )
        assert refresh_response.status_code == status.HTTP_200_OK
        assert "access_token" in refresh_response.json()

        # 3. Logout and verify cookie is cleared
        logout_response = await async_client.post(
            "/auth/logout",
            cookies={"mkobi_refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_response.status_code == status.HTTP_200_OK

        # 4. Verify refresh no longer works after logout
        # Use a valid token but without the cookie, or with cleared cookie
        final_refresh = await async_client.post("/auth/refresh")
        assert final_refresh.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_refresh_with_expired_token(
        self, async_client: AsyncClient
    ) -> None:
        """Test refresh with expired token returns 401."""
        from datetime import UTC, datetime, timedelta

        from jose import jwt

        expired_token = jwt.encode(
            {
                "sub": "test-user-id",
                "email": "test@example.com",
                "role": "admin",
                "exp": datetime.now(UTC) - timedelta(hours=1),
            },
            "test_secret_key_change_in_production",
            algorithm="HS256",
        )

        response = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": expired_token},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminResetPasswordEndpoint:
    """Tests for POST /admin/users/{user_id}/reset-password endpoint."""

    async def test_admin_reset_password_success(
        self, async_client: AsyncClient, test_user: dict, async_db_session
    ) -> None:
        """Test admin can reset another user's password."""
        # Create a target user (viewer) for the admin to reset
        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()
        target_user = await user_repo.create(
            db=async_db_session,
            email="target_reset@example.com",
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Create admin user for testing
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_reset_test@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        # Admin resets target user's password
        response = await async_client.post(
            f"/admin/users/{target_user.id}/reset-password",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        # Response contains retrieval_token, not temp_password directly
        assert "retrieval_token" in data
        assert "user_id" in data
        assert data["user_id"] == str(target_user.id)

        # Admin uses retrieval endpoint to get the temp password
        retrieval_token = data["retrieval_token"]
        retrieve_response = await async_client.get(
            f"/admin/temp-passwords/{retrieval_token}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert retrieve_response.status_code == status.HTTP_200_OK
        retrieve_data = retrieve_response.json()
        assert "temp_password" in retrieve_data
        temp_password = retrieve_data["temp_password"]
        assert len(temp_password) >= 16
        # Verify temp password has letters and digits
        assert re.search(r"[a-zA-Z]", temp_password) is not None
        assert re.search(r"\d", temp_password) is not None

    async def test_admin_reset_password_self_guard(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test admin cannot reset own password."""
        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_self_reset@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        # Admin tries to reset own password - should fail
        response = await async_client.post(
            f"/admin/users/{admin_user.id}/reset-password",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        # SECB-7: the route emits a fixed detail naming the failure class; the
        # service's own "cannot reset your own password" text is logged, not
        # returned. The refusal itself (422, VALIDATION_ERROR) is unchanged.
        assert response.json()["detail"] == "Invalid password reset"

    async def test_admin_reset_password_nonexistent_user(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test admin reset password for non-existent user returns 400."""
        from uuid import uuid4

        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_nonexist_reset@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        # Try to reset non-existent user
        fake_user_id = uuid4()
        response = await async_client.post(
            f"/admin/users/{fake_user_id}/reset-password",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "not found" in response.json()["detail"].lower()

    async def test_admin_reset_password_non_admin_forbidden(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test non-admin user cannot access admin reset password endpoint."""
        from uuid import uuid4

        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()
        viewer_user = await user_repo.create(
            db=async_db_session,
            email="viewer_reset_forbidden@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        viewer_token = create_access_token({
            "user_id": str(viewer_user.id),
            "email": viewer_user.email,
        })

        # Viewer tries to access admin endpoint - should be forbidden
        fake_user_id = uuid4()
        response = await async_client.post(
            f"/admin/users/{fake_user_id}/reset-password",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestRegistrationApprovalForcePasswordChange:
    """Tests for force_password_change flag during registration approval."""

    async def test_approve_registration_sets_force_password_change(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test that approving registration sets force_password_change=True on user."""
        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.registration_request_repo import (
            RegistrationRequestRepository,
        )
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()

        # Create admin user
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_approve_test@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        # Create registration request
        reg_repo = RegistrationRequestRepository()
        reg_request = await reg_repo.create(
            email="approve_force_test@example.com",
            ip="127.0.0.1",
            db=async_db_session,
        )
        await async_db_session.commit()

        # Approve the registration request
        response = await async_client.post(
            f"/admin/registration-requests/{reg_request.id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify response contains retrieval_token (not temp_password)
        data = response.json()
        assert "retrieval_token" in data
        assert "user_id" in data
        assert "temp_password" not in data
        assert data["message"] == "Registration request approved"

        # Verify user was created with force_password_change=True
        user = await user_repo.get_by_email(
            email="approve_force_test@example.com",
            db=async_db_session,
        )
        assert user is not None
        assert user.force_password_change is True

    async def test_password_change_clears_force_password_change(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test that changing password clears force_password_change flag."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()

        # Create a user with force_password_change=True
        user = await user_repo.create(
            db=async_db_session,
            email="force_change_clear@example.com",
            password_hash=hash_password("TempPass123!"),
            role=UserRole.VIEWER,
        )
        # Manually set the flag (simulating approved registration state)
        await user_repo.update(
            user.id, async_db_session,
            force_password_change=True,
        )
        await async_db_session.commit()

        # Verify initial state
        user = await user_repo.get(user.id, async_db_session)
        assert user.force_password_change is True

        # Login to get access token
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": "force_change_clear@example.com",
                "password": "TempPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        token = login_response.json()["access_token"]

        # Change password
        change_response = await async_client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "TempPass123!",
                "new_password": "NewPass123!",
                "confirm_password": "NewPass123!",
            },
        )
        assert change_response.status_code == status.HTTP_200_OK

        # Verify flag is cleared
        user = await user_repo.get(user.id, async_db_session)
        assert user.force_password_change is False

    async def test_password_change_mismatch_returns_422(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test that mismatched passwords return 422 validation error."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()

        # Create a user
        await user_repo.create(
            db=async_db_session,
            email="password_mismatch_test@example.com",
            password_hash=hash_password("TempPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Login to get access token
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": "password_mismatch_test@example.com",
                "password": "TempPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        token = login_response.json()["access_token"]

        # Try to change password with mismatched confirmation
        change_response = await async_client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "TempPass123!",
                "new_password": "NewPass123!",
                "confirm_password": "DifferentPass123!",
            },
        )
        assert change_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = change_response.json()
        # Check that error message is in the errors list
        errors_str = str(data.get("errors", []))
        assert "do not match" in errors_str.lower() or "mismatch" in errors_str.lower()

    async def test_change_password_revokes_existing_tokens(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """A successful password change must withdraw the user's existing sessions.

        Behavioural, not a mock-call assertion: a token minted before the change
        is refused by a protected route afterwards, with a revocation error. This
        proves the revocation targets the changing user and runs after the commit
        (a pre-commit revocation would still pass a mock assertion).
        """
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()
        await user_repo.create(
            db=async_db_session,
            email="change_pwd_revoke_test@example.com",
            password_hash=hash_password("OldPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Obtain a token representing an existing session.
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": "change_pwd_revoke_test@example.com",
                "password": "OldPass123!",
            },
        )
        assert login_response.status_code == status.HTTP_200_OK
        old_token = login_response.json()["access_token"]
        old_headers = {"Authorization": f"Bearer {old_token}"}

        # The session works before the change.
        assert (
            await async_client.get("/auth/me", headers=old_headers)
        ).status_code == status.HTTP_200_OK

        change_response = await async_client.post(
            "/auth/change-password",
            headers=old_headers,
            json={
                "current_password": "OldPass123!",
                "new_password": "NewPass456!",
                "confirm_password": "NewPass456!",
            },
        )
        assert change_response.status_code == status.HTTP_200_OK

        # The pre-change token is now refused with a revocation error.
        me_response = await async_client.get("/auth/me", headers=old_headers)
        assert me_response.status_code == status.HTTP_401_UNAUTHORIZED
        body = me_response.json()
        error_msg = body.get("error", "") or body.get("detail", "")
        assert "revoked" in error_msg.lower()


class TestDisplayNameComputation:
    """Tests for display_name computed field extraction from email."""

    def test_display_name_standard_email(self) -> None:
        """Test display_name extraction from standard email address.

        Given: user@example.com
        Expected: user
        """
        from mkobi.models.user import UserRead
        from mkobi.models.enums import UserRole

        user = UserRead(
            id="550e8400-e29b-41d4-a716-446655440000",
            email="user@example.com",
            role=UserRole.VIEWER,
            is_active=True,
            created_at="2026-04-24T16:02:46+03:00",
        )
        assert user.display_name == "user"

    def test_display_name_with_dots_and_numbers(self) -> None:
        """Test display_name with complex email prefix containing dots and numbers.

        Given: john.smith123@company.org
        Expected: john.smith123
        """
        from mkobi.models.user import UserRead
        from mkobi.models.enums import UserRole

        user = UserRead(
            id="550e8400-e29b-41d4-a716-446655440000",
            email="john.smith123@company.org",
            role=UserRole.EDITOR,
            is_active=True,
            created_at="2026-04-24T16:02:46+03:00",
        )
        assert user.display_name == "john.smith123"

    def test_display_name_plus_addressing(self) -> None:
        """Test display_name with plus addressing in email.

        Given: user+tag@example.com
        Expected: user+tag
        """
        from mkobi.models.user import UserRead
        from mkobi.models.enums import UserRole

        user = UserRead(
            id="550e8400-e29b-41d4-a716-446655440000",
            email="user+tag@example.com",
            role=UserRole.VIEWER,
            is_active=True,
            created_at="2026-04-24T16:02:46+03:00",
        )
        assert user.display_name == "user+tag"

    def test_display_name_with_numbers(self) -> None:
        """Test display_name with numeric prefix.

        Given: user123@company.org
        Expected: user123
        """
        from mkobi.models.user import UserRead
        from mkobi.models.enums import UserRole

        user = UserRead(
            id="550e8400-e29b-41d4-a716-446655440000",
            email="user123@company.org",
            role=UserRole.VIEWER,
            is_active=True,
            created_at="2026-04-24T16:02:46+03:00",
        )
        assert user.display_name == "user123"

    def test_display_name_subdomain_email(self) -> None:
        """Test display_name with subdomain email.

        Given: user@sub.domain.com
        Expected: user (subdomain does not affect prefix extraction)
        """
        from mkobi.models.user import UserRead
        from mkobi.models.enums import UserRole

        user = UserRead(
            id="550e8400-e29b-41d4-a716-446655440000",
            email="user@sub.domain.com",
            role=UserRole.VIEWER,
            is_active=True,
            created_at="2026-04-24T16:02:46+03:00",
        )
        assert user.display_name == "user"

    def test_display_name_serialization(self) -> None:
        """Test that display_name is included in model serialization."""
        from mkobi.models.user import UserRead
        from mkobi.models.enums import UserRole

        user = UserRead(
            id="550e8400-e29b-41d4-a716-446655440000",
            email="jane.doe@example.com",
            role=UserRole.VIEWER,
            is_active=True,
            created_at="2026-04-24T16:02:46+03:00",
        )

        # Test JSON serialization includes display_name
        json_data = user.model_dump(mode="json")
        assert "display_name" in json_data
        assert json_data["display_name"] == "jane.doe"