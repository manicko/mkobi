"""Revocation-store failure direction.

A fault reading the revocation store must surface as a dependency outage
(``503 SERVICE_UNAVAILABLE``) rather than as a credential verdict (``401``).
A Redis degradation must not look like a mass sign-out, and "cannot answer"
must never be blurred into "the answer is no".

Tests cover:
- A protected request answers 503 SERVICE_UNAVAILABLE while the store faults
- ``POST /auth/refresh`` answers 503 SERVICE_UNAVAILABLE while the store faults
- A genuine revocation over a healthy store still answers 401 TOKEN_REVOKED
- An absent marker over a healthy store lets the request proceed
"""

from fastapi import status
from httpx import AsyncClient

from mkobi.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    revoke_all_user_tokens,
)
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import UserRole


def _fault_store(app, operation: str, prefix: str) -> None:
    """Make one revocation read on the app's own Redis instance raise.

    Only reads whose key starts with ``prefix`` fail, so the fault isolates the
    revocation reader from other users of the same operation (the rate limiter
    also calls ``get``). The app's instance is the one the dependency override
    returns (``app.state.mock_redis``), so the fault must be injected into that
    very object -- a fault placed on the ``strict_redis`` fixture instance
    would exercise nothing.
    """
    mock_redis = app.state.mock_redis
    original = getattr(mock_redis, operation)

    async def failing(key, *args, **kwargs):
        if isinstance(key, str) and key.startswith(prefix):
            raise ConnectionError("Redis connection failed")
        return await original(key, *args, **kwargs)

    setattr(mock_redis, operation, failing)


async def _create_user(async_db_session, email: str):
    user_repo = UserRepository()
    user = await user_repo.create(
        db=async_db_session,
        email=email,
        password_hash=hash_password("TestPass123!"),
        role=UserRole.VIEWER,
    )
    await async_db_session.commit()
    return user


class TestRevocationStoreOutage:
    """A store fault is reported as unavailable, not as a credential verdict."""

    async def test_protected_path_reports_dependency_outage(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        user = await _create_user(async_db_session, "outage_protected@example.com")
        token = create_access_token({"user_id": str(user.id), "email": user.email})

        _fault_store(
            async_client._transport.app,  # type: ignore[attr-defined]
            "exists",
            "token_blacklist:",
        )

        response = await async_client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        body = response.json()
        assert body["code"] == "SERVICE_UNAVAILABLE"
        assert body["code"] != "TOKEN_REVOKED"

    async def test_refresh_reports_dependency_outage(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        user = await _create_user(async_db_session, "outage_refresh@example.com")
        refresh_token = create_refresh_token(
            {"sub": str(user.id), "email": user.email, "role": user.role}
        )

        # ``exists`` succeeds (no refresh jti revoked); ``get`` faults only on
        # the user-level marker read, not on the rate limiter's reads.
        _fault_store(
            async_client._transport.app,  # type: ignore[attr-defined]
            "get",
            "user_tokens_revoked:",
        )

        response = await async_client.post(
            "/auth/refresh", cookies={"mkobi_refresh_token": refresh_token}
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        body = response.json()
        assert body["code"] == "SERVICE_UNAVAILABLE"
        assert body["code"] != "TOKEN_REVOKED"
        assert body["code"] != "AUTHENTICATION_FAILED"


class TestHealthyStoreUnaffected:
    """The distinction must not blur "cannot answer" into "the answer is no"."""

    async def test_genuine_revocation_still_401(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        user = await _create_user(async_db_session, "genuine_revocation@example.com")
        # The credential must predate the marker: mint it first, then revoke.
        token = create_access_token({"user_id": str(user.id), "email": user.email})
        app = async_client._transport.app  # type: ignore[attr-defined]
        await revoke_all_user_tokens(
            app.state.mock_redis,
            user.id,
            access_ttl=900,
            refresh_ttl=604800,
        )

        response = await async_client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["code"] == "TOKEN_REVOKED"

    async def test_marker_absent_still_allows(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        user = await _create_user(async_db_session, "marker_absent@example.com")
        token = create_access_token({"user_id": str(user.id), "email": user.email})

        response = await async_client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == status.HTTP_200_OK
