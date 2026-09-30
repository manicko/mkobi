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