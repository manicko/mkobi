"""Tests for health check endpoints.

Tests for /health and /health/detailed endpoints.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from mkobi.app import create_app


class TestHealthEndpoint:
    """Tests for basic health check endpoint."""

    @pytest.fixture
    async def health_client(self) -> AsyncClient:
        """Create HTTP client for health endpoint testing without database dependency.

        Health endpoints operate independently of database setup in tests,
        we create a fresh app instance and client without DB setup.
        """
        import os

        os.environ.setdefault("ENV", "test")
        os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")
        os.environ.setdefault("DATABASE__HOST", "localhost")
        os.environ.setdefault("DATABASE__PORT", "5434")
        os.environ.setdefault("DATABASE__DBNAME", "bidb_test")
        os.environ.setdefault("DATABASE__USER", "mkobi_app")
        os.environ.setdefault("DATABASE__PASSWORD", "StrongDbP@ss123!")
        os.environ.setdefault("DATABASE__ADMIN_USER", "postgres")
        os.environ.setdefault("DATABASE__ADMIN_PASSWORD", "StrongT3stP@ss!")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

    async def test_health_endpoint_returns_200(self, health_client: AsyncClient) -> None:
        """GET /health returns 200 status code."""
        response = await health_client.get("/health")
        assert response.status_code == 200

    async def test_health_endpoint_returns_healthy_status(
        self, health_client: AsyncClient
    ) -> None:
        """GET /health returns status 'healthy' when database is connected."""
        response = await health_client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"

    async def test_health_endpoint_returns_database_connected(
        self, health_client: AsyncClient
    ) -> None:
        """GET /health returns database 'connected' status."""
        response = await health_client.get("/health")
        data = response.json()
        assert data["database"] == "connected"


class TestHealthDetailedEndpoint:
    """Tests for detailed health check endpoint."""

    @pytest.fixture
    async def detailed_health_client(self) -> AsyncClient:
        """Create HTTP client for detailed health endpoint testing.

        Detailed health endpoint operates independently of database setup.
        """
        import os

        os.environ.setdefault("ENV", "test")
        os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")
        os.environ.setdefault("DATABASE__HOST", "localhost")
        os.environ.setdefault("DATABASE__PORT", "5434")
        os.environ.setdefault("DATABASE__DBNAME", "bidb_test")
        os.environ.setdefault("DATABASE__USER", "mkobi_app")
        os.environ.setdefault("DATABASE__PASSWORD", "StrongDbP@ss123!")
        os.environ.setdefault("DATABASE__ADMIN_USER", "postgres")
        os.environ.setdefault("DATABASE__ADMIN_PASSWORD", "StrongT3stP@ss!")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

    async def test_health_detailed_endpoint_returns_200(
        self, detailed_health_client: AsyncClient
    ) -> None:
        """GET /health/detailed returns 200 status code."""
        response = await detailed_health_client.get("/health/detailed")
        assert response.status_code == 200

    async def test_health_detailed_endpoint_returns_healthy_status(
        self, detailed_health_client: AsyncClient
    ) -> None:
        """GET /health/detailed returns status 'healthy' when all components are healthy."""
        response = await detailed_health_client.get("/health/detailed")
        data = response.json()
        assert data["status"] == "healthy"

    async def test_health_detailed_endpoint_returns_components(
        self, detailed_health_client: AsyncClient
    ) -> None:
        """GET /health/detailed returns component statuses."""
        response = await detailed_health_client.get("/health/detailed")
        data = response.json()

        assert "components" in data
        components = data["components"]

        assert "database" in components
        assert components["database"]["status"] == "connected"
        assert components["database"]["type"] == "postgresql"

        assert "static_files" in components
        assert "status" in components["static_files"]
        assert "path" in components["static_files"]


class TestDetailedHealthReconcilerComponent:
    """The /health/detailed endpoint reports the reconciler component."""

    @pytest.fixture
    async def detailed_client(self) -> AsyncClient:
        """Create a client for the detailed health endpoint with shared app state."""
        import os

        os.environ.setdefault("ENV", "test")
        os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")
        os.environ.setdefault("DATABASE__HOST", "localhost")
        os.environ.setdefault("DATABASE__PORT", "5434")
        os.environ.setdefault("DATABASE__DBNAME", "bidb_test")
        os.environ.setdefault("DATABASE__USER", "mkobi_app")
        os.environ.setdefault("DATABASE__PASSWORD", "StrongDbP@ss123!")
        os.environ.setdefault("DATABASE__ADMIN_USER", "postgres")
        os.environ.setdefault("DATABASE__ADMIN_PASSWORD", "StrongT3stP@ss!")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client, app

    async def test_status_unknown_without_started_reconciler(self, detailed_client) -> None:
        """Before lifespan runs the component reports not_started, never a wrong state."""
        client, _app = detailed_client
        response = await client.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        component = data["components"]["stale_processing_reconciler"]
        assert component["status"] == "not_started"
        assert component["lease_state"] == "unknown"
        assert component["last_success_at"] is None

    async def test_component_reflects_shared_state(self, detailed_client) -> None:
        """The component reflects the ReconcilerStatus published on app.state."""
        from datetime import UTC, datetime

        from mkobi.core.reconciler_lease import ReconcilerStatus
        from mkobi.models.enums import ReconcilerLeaseState

        client, app = detailed_client
        status = ReconcilerStatus()
        status.lease_state = ReconcilerLeaseState.UNPROTECTED
        status.last_success_at = datetime.now(UTC)
        status.record_success(0)
        app.state.reconciler_status = status

        response = await client.get("/health/detailed")
        assert response.status_code == 200
        component = response.json()["components"]["stale_processing_reconciler"]
        assert component["status"] == "ok"
        assert component["lease_state"] == "unprotected"
        assert component["last_success_at"] is not None
        assert component["last_swept_count"] == 0
        assert component["sweep_count"] >= 1


class TestHealthWithRedisDown:
    """A Redis outage must not drag down /health or the overall detailed status."""

    @pytest.fixture
    async def client(self) -> AsyncClient:
        import os

        os.environ.setdefault("ENV", "test")
        os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")
        os.environ.setdefault("DATABASE__HOST", "localhost")
        os.environ.setdefault("DATABASE__PORT", "5434")
        os.environ.setdefault("DATABASE__DBNAME", "bidb_test")
        os.environ.setdefault("DATABASE__USER", "mkobi_app")
        os.environ.setdefault("DATABASE__PASSWORD", "StrongDbP@ss123!")
        os.environ.setdefault("DATABASE__ADMIN_USER", "postgres")
        os.environ.setdefault("DATABASE__ADMIN_PASSWORD", "StrongT3stP@ss!")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
            yield http_client

    async def test_health_still_healthy_when_redis_down(self, client, monkeypatch) -> None:
        """/health stays 200 with database connected even if Redis cannot be reached."""
        import mkobi.core.redis_client as redis_client_module
        import mkobi.app as app_module

        # Force every Redis access to fail, as an outage would.
        async def unreachable_client():
            raise OSError("redis unavailable")

        monkeypatch.setattr(
            app_module, "get_async_redis_client", lambda: _UnreachableRedis()
        )
        monkeypatch.setattr(redis_client_module, "get_async_redis_client", lambda: _UnreachableRedis())

        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "database": "connected"}

        detailed = await client.get("/health/detailed")
        assert detailed.status_code == 200
        assert detailed.json()["status"] == "healthy"
        assert detailed.json()["components"]["database"]["status"] == "connected"


class _UnreachableRedis:
    """Async Redis double whose every command raises, modelling an outage."""

    async def set(self, *args, **kwargs):
        raise OSError("redis unavailable")

    async def eval(self, *args, **kwargs):
        raise OSError("redis unavailable")

    async def aclose(self) -> None:
        pass