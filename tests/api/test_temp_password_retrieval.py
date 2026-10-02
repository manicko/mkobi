"""Tests for GET /admin/temp-passwords/{retrieval_token} endpoint."""

from fastapi import status
from httpx import AsyncClient

from mkobi.main import app


class _FaultingPipeline:
    """Pipeline whose execute() always raises, simulating an unreachable Redis."""

    def __init__(self, transaction: bool = True) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, key):
        return self

    def delete(self, key):
        return self

    async def execute(self):
        raise RuntimeError("Redis pipeline failed")


class _FaultingRedis:
    """Redis double whose only real operation, pipeline(), faults on execute."""

    def pipeline(self, transaction: bool = True):
        return _FaultingPipeline()


def _make_faulting_store():
    """Build a real TempPasswordStore over a faulting Redis client."""
    from mkobi.core.temp_password_store import TempPasswordStore

    return TempPasswordStore(_FaultingRedis())


class TestTempPasswordRetrievalEndpoint:
    """Tests for one-time temporary password retrieval endpoint."""

    async def test_retrieve_temp_password_success(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test admin can retrieve a temporary password with valid token."""
        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()

        # Create admin user
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_retrieval_test@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        # Store temp password in Redis directly
        temp_password = "TempPass123!@#ABC"
        retrieval_token = "test_retrieval_token_xyz789"

        # Get the mock Redis from app state and store password
        mock_redis = app.state.mock_redis
        await mock_redis.set(f"temp_pwd:{retrieval_token}", temp_password, ex=3600)

        # Admin retrieves the temp password
        response = await async_client.get(
            f"/admin/temp-passwords/{retrieval_token}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["temp_password"] == temp_password

    async def test_retrieve_temp_password_nonexistent_token(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test retrieving with nonexistent token returns 404."""
        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()

        # Create admin user
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_nonexistent_retrieval@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        # Try to retrieve nonexistent temp password
        response = await async_client.get(
            "/admin/temp-passwords/nonexistent_token_12345",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        body = response.json()
        # RFC 7807 format: check detail field, not error
        assert "detail" in body
        assert "not found" in body["detail"].lower()

    async def test_retrieve_temp_password_single_use(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test that temp password can only be retrieved once."""
        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()

        # Create admin user
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_single_use_retrieval@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        # Store temp password in Redis directly
        temp_password = "OneTimeOnlyPass!"
        retrieval_token = "single_use_token_abc456"

        # Get the mock Redis from app state and store password
        mock_redis = app.state.mock_redis
        await mock_redis.set(f"temp_pwd:{retrieval_token}", temp_password, ex=3600)

        # First retrieval - should succeed
        response1 = await async_client.get(
            f"/admin/temp-passwords/{retrieval_token}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response1.status_code == status.HTTP_200_OK
        assert response1.json()["temp_password"] == temp_password

        # Second retrieval - should return 404 (password deleted after first retrieve)
        response2 = await async_client.get(
            f"/admin/temp-passwords/{retrieval_token}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response2.status_code == status.HTTP_404_NOT_FOUND
        body = response2.json()
        assert "detail" in body
        assert "not found" in body["detail"].lower()

    async def test_retrieve_temp_password_non_admin_forbidden(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test non-admin user cannot access temp password retrieval endpoint."""
        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()

        # Create viewer user (non-admin)
        viewer_user = await user_repo.create(
            db=async_db_session,
            email="viewer_retrieval_forbidden@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        viewer_token = create_access_token({
            "user_id": str(viewer_user.id),
            "email": viewer_user.email,
        })

        # Viewer tries to access admin endpoint - should be forbidden
        response = await async_client.get(
            "/admin/temp-passwords/some_token",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_retrieve_temp_password_expired_token(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test retrieving an expired token returns 404.

        Simulates expired token by not storing anything in Redis.
        In production, Redis TTL handles automatic expiration.
        """
        from uuid import uuid4

        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()

        # Create admin user
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_expired_test@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        # Use a random UUID token that was never stored (simulates expired/deleted)
        expired_token = str(uuid4())

        # Try to retrieve expired temp password
        response = await async_client.get(
            f"/admin/temp-passwords/{expired_token}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        body = response.json()
        assert "detail" in body
        assert "not found" in body["detail"].lower()

    async def test_retrieve_temp_password_store_fault_returns_503(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """A store fault must answer 503, never 404.

        An unreachable store and a spent handle are different states; collapsing
        them would let a retry loop against a 404 be mistaken for an outage.
        """
        from mkobi.api.deps import get_temp_password_store
        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import UserRole

        user_repo = UserRepository()
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_store_fault@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        app.dependency_overrides[get_temp_password_store] = _make_faulting_store
        try:
            response = await async_client.get(
                "/admin/temp-passwords/some_token",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        finally:
            app.dependency_overrides.pop(get_temp_password_store, None)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        body = response.json()
        assert body["code"] == "SERVICE_UNAVAILABLE"
        assert body["title"] == "Service unavailable"
        assert response.status_code != status.HTTP_404_NOT_FOUND