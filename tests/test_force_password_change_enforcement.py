"""Server-side enforcement of the ``force_password_change`` flag.

A user whose password must be changed is refused on every protected route except
a small allow-list that keeps the completion path, the silent refresh, logout,
and the flag-carrying ``/auth/me`` reachable. The refusal is ``403`` with
``PERMISSION_DENIED`` — never ``401`` — because the SPA answers any 401 with a
sign-out, which would turn the refusal into a redirect loop.

Tests cover:
- A flagged user is refused off the allow-list with 403 PERMISSION_DENIED
- A flagged user still reaches each allow-listed route
- An unflagged user is unaffected
- The named predicate answers for each allow-listed path and a non-listed one
"""

from fastapi import status
from httpx import AsyncClient

from mkobi.api.deps import is_password_change_completion_path
from mkobi.core.security import create_access_token, hash_password
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import UserRole


async def _create_flagged_user(async_db_session, email: str):
    """Create a user with ``force_password_change=True`` and return it."""
    user_repo = UserRepository()
    user = await user_repo.create(
        db=async_db_session,
        email=email,
        password_hash=hash_password("TempPass123!"),
        role=UserRole.VIEWER,
    )
    await user_repo.update(user.id, async_db_session, force_password_change=True)
    await async_db_session.commit()
    return user


def _token_for(user) -> str:
    return create_access_token({"user_id": str(user.id), "email": user.email})


async def _login_and_get_refresh_cookie(async_client: AsyncClient, email: str) -> str:
    response = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "TempPass123!"},
    )
    assert response.status_code == status.HTTP_200_OK
    set_cookie = response.headers.get("set-cookie", "")
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.startswith("mkobi_refresh_token="):
            return part.split("=", 1)[1]
    return ""


class TestFlaggedUserRefused:
    """A flagged user cannot use protected routes off the allow-list."""

    async def test_flagged_user_is_refused_on_protected_route(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """A flagged user gets 403 PERMISSION_DENIED on a protected route."""
        user = await _create_flagged_user(
            async_db_session, "flagged_refused_test@example.com"
        )
        headers = {"Authorization": f"Bearer {_token_for(user)}"}

        response = await async_client.get(f"/users/{user.id}", headers=headers)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        body = response.json()
        assert body["code"] == "PERMISSION_DENIED"

    async def test_unflagged_user_is_unaffected(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """A normal user is not gated on the same route."""
        user_repo = UserRepository()
        user = await user_repo.create(
            db=async_db_session,
            email="unflagged_control_test@example.com",
            password_hash=hash_password("TestPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        headers = {"Authorization": f"Bearer {_token_for(user)}"}
        response = await async_client.get(f"/users/{user.id}", headers=headers)

        assert response.status_code == status.HTTP_200_OK


class TestFlaggedUserAllowList:
    """A flagged user still reaches the routes needed to complete the change."""

    async def test_flagged_user_reaches_get_me(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        user = await _create_flagged_user(async_db_session, "flagged_me_test@example.com")
        headers = {"Authorization": f"Bearer {_token_for(user)}"}

        response = await async_client.get("/auth/me", headers=headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["force_password_change"] is True

    async def test_flagged_user_reaches_change_password(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        user = await _create_flagged_user(
            async_db_session, "flagged_change_test@example.com"
        )
        headers = {"Authorization": f"Bearer {_token_for(user)}"}

        response = await async_client.post(
            "/auth/change-password",
            headers=headers,
            json={
                "current_password": "TempPass123!",
                "new_password": "NewSecure123!",
                "confirm_password": "NewSecure123!",
            },
        )

        assert response.status_code != status.HTTP_403_FORBIDDEN
        assert response.status_code == status.HTTP_200_OK

    async def test_flagged_user_reaches_logout(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        user = await _create_flagged_user(async_db_session, "flagged_logout_test@example.com")
        headers = {"Authorization": f"Bearer {_token_for(user)}"}

        response = await async_client.post("/auth/logout", headers=headers)

        assert response.status_code == status.HTTP_200_OK

    async def test_flagged_user_reaches_refresh(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        await _create_flagged_user(
            async_db_session, "flagged_refresh_test@example.com"
        )
        refresh_cookie = await _login_and_get_refresh_cookie(
            async_client, "flagged_refresh_test@example.com"
        )

        response = await async_client.post(
            "/auth/refresh",
            cookies={"mkobi_refresh_token": refresh_cookie},
        )

        assert response.status_code != status.HTTP_403_FORBIDDEN
        assert response.status_code == status.HTTP_200_OK


class TestPasswordChangeCompletionPredicate:
    """The allow-list predicate is callable with no request pipeline."""

    def test_completion_path_predicate(self) -> None:
        allow_listed = [
            ("POST", "/api/v1/auth/change-password"),
            ("POST", "/api/v1/auth/refresh"),
            ("POST", "/api/v1/auth/logout"),
            ("GET", "/api/v1/auth/me"),
        ]
        for method, path in allow_listed:
            assert is_password_change_completion_path(method, path) is True, (
                f"{method} {path} should be allow-listed"
            )

        assert (
            is_password_change_completion_path("GET", "/api/v1/users/00000000-0000-0000-0000-000000000000")
            is False
        )
        assert is_password_change_completion_path("GET", "/api/v1/auth/login") is False
        # Method matters: the allow-list is not path-only.
        assert is_password_change_completion_path("DELETE", "/api/v1/auth/logout") is False
