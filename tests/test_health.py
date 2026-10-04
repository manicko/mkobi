"""Tests for health check endpoints.

Tests for /health and /health/detailed endpoints.

``SECB-4`` gates ``/health/detailed`` behind the admin dependency and reduces its
body: the absolute bundle path and both raw driver exception texts are gone. These
tests use the conftest ``async_client`` (which installs the database and Redis
dependency overrides) and reach the root-mounted health paths with absolute URLs,
because that client's base path is ``/api/v1``.
"""

from httpx import AsyncClient

from mkobi.core.security import create_access_token, hash_password
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import UserRole

# The root-mounted health paths live outside the conftest client's /api/v1 base
# path, so they are requested as absolute URLs on the same test transport.
_HEALTH_URL = "http://testserver/health"
_DETAILED_HEALTH_URL = "http://testserver/health/detailed"


class TestHealthEndpoint:
    """Tests for basic health check endpoint."""

    async def test_health_endpoint_returns_200(self, async_client: AsyncClient) -> None:
        """GET /health returns 200 status code."""
        response = await async_client.get(_HEALTH_URL)
        assert response.status_code == 200

    async def test_health_endpoint_returns_healthy_status(
        self, async_client: AsyncClient
    ) -> None:
        """GET /health returns status 'healthy' when database is connected."""
        response = await async_client.get(_HEALTH_URL)
        data = response.json()
        assert data["status"] == "healthy"

    async def test_health_endpoint_returns_database_connected(
        self, async_client: AsyncClient
    ) -> None:
        """GET /health returns database 'connected' status."""
        response = await async_client.get(_HEALTH_URL)
        data = response.json()
        assert data["database"] == "connected"

    async def test_health_stays_exactly_two_keys(
        self, async_client: AsyncClient
    ) -> None:
        """/health keeps its exact two-key body; SECB-4 does not touch it."""
        response = await async_client.get(_HEALTH_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "database": "connected"}


class TestHealthDetailedAuthorisation:
    """SECB-4: /health/detailed requires an administrator."""

    async def test_anonymous_caller_gets_401(
        self, async_client: AsyncClient
    ) -> None:
        """An unauthenticated caller receives 401 via the RFC 7807 path."""
        response = await async_client.get(_DETAILED_HEALTH_URL)
        assert response.status_code == 401
        assert response.json()["code"] == "AUTHENTICATION_FAILED"

    async def test_authenticated_non_admin_gets_403(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """An authenticated viewer receives 403 via the RFC 7807 path."""
        repo = UserRepository()
        viewer = await repo.create(
            db=async_db_session,
            email=f"health_viewer_{__import__('uuid').uuid4().hex[:8]}@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()
        token = create_access_token(
            {"user_id": str(viewer.id), "email": viewer.email}
        )

        response = await async_client.get(
            _DETAILED_HEALTH_URL,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        assert response.json()["code"] == "INSUFFICIENT_PERMISSIONS"


class TestHealthDetailedEndpoint:
    """Tests for detailed health check endpoint (administrator)."""

    async def test_health_detailed_endpoint_returns_200(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """GET /health/detailed returns 200 for an administrator."""
        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert response.status_code == 200

    async def test_health_detailed_endpoint_returns_healthy_status(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """GET /health/detailed returns status 'healthy' when components are healthy."""
        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        data = response.json()
        assert data["status"] == "healthy"

    async def test_health_detailed_endpoint_returns_components(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """GET /health/detailed returns component statuses without the bundle path."""
        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        data = response.json()

        assert "components" in data
        components = data["components"]

        assert "database" in components
        assert components["database"]["status"] == "connected"
        assert components["database"]["type"] == "postgresql"

        assert "static_files" in components
        assert components["static_files"]["status"] in {"available", "unavailable"}
        # The absolute filesystem path is no longer disclosed (SECB-4).
        assert "path" not in components["static_files"]

    async def test_admin_response_still_reports_all_components(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """The reduced body still earns the endpoint's name: every component is present."""
        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert response.status_code == 200
        components = response.json()["components"]
        assert set(components) == {
            "database",
            "static_files",
            "redis",
            "stale_processing_reconciler",
        }


class TestDetailedHealthReconcilerComponent:
    """The /health/detailed endpoint reports the reconciler component."""

    async def test_status_unknown_without_started_reconciler(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Before lifespan runs the component reports not_started, never a wrong state."""
        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        component = data["components"]["stale_processing_reconciler"]
        assert component["status"] == "not_started"
        assert component["lease_state"] == "unknown"
        assert component["last_success_at"] is None

    async def test_component_reflects_shared_state(
        self, async_client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """The component reflects the ReconcilerStatus published on app.state."""
        from datetime import UTC, datetime

        from mkobi.core.reconciler_lease import ReconcilerStatus
        from mkobi.main import app
        from mkobi.models.enums import ReconcilerLeaseState

        status = ReconcilerStatus()
        status.lease_state = ReconcilerLeaseState.UNPROTECTED
        status.last_success_at = datetime.now(UTC)
        status.record_success(0)
        app.state.reconciler_status = status

        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert response.status_code == 200
        component = response.json()["components"]["stale_processing_reconciler"]
        assert component["status"] == "ok"
        assert component["lease_state"] == "unprotected"
        assert component["last_success_at"] is not None
        assert component["last_swept_count"] == 0
        assert component["sweep_count"] >= 1


class TestDetailedHealthRedisComponent:
    """The redis component reports a degraded Redis without moving liveness."""

    async def test_redis_down_reported_and_liveness_unchanged(
        self, async_client: AsyncClient, auth_headers: dict[str, str], monkeypatch
    ) -> None:
        """A Redis outage is reported on /health/detailed without moving liveness (DP-1)."""
        import mkobi.app as app_module

        # app.py imports the factory into its own namespace; patch it there so
        # the autouse conftest fixture (which targets the redis_client module)
        # does not reach the handler.
        monkeypatch.setattr(
            app_module, "get_async_redis_client", lambda: _UnreachableRedis()
        )

        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        redis_component = data["components"]["redis"]
        assert redis_component["status"] == "disconnected"
        assert redis_component["type"] == "redis"
        # The raw driver exception text is no longer disclosed (SECB-4).
        assert "error" not in redis_component

    async def test_redis_healthy_reported(
        self, async_client: AsyncClient, auth_headers: dict[str, str], monkeypatch
    ) -> None:
        """A reachable Redis is reported connected, so the degraded test cannot pass by accident."""
        import mkobi.app as app_module

        monkeypatch.setattr(
            app_module, "get_async_redis_client", lambda: _ReachableRedis()
        )

        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert response.status_code == 200
        redis_component = response.json()["components"]["redis"]
        assert redis_component["status"] == "connected"
        assert redis_component["type"] == "redis"

    async def test_health_stays_two_key_shape_when_redis_down(
        self, async_client: AsyncClient, monkeypatch
    ) -> None:
        """/health keeps its exact two-key shape while Redis is unreachable."""
        import mkobi.app as app_module

        monkeypatch.setattr(
            app_module, "get_async_redis_client", lambda: _UnreachableRedis()
        )

        response = await async_client.get(_HEALTH_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "database": "connected"}

    async def test_database_failure_hides_driver_error(
        self, async_client: AsyncClient, auth_headers: dict[str, str], monkeypatch
    ) -> None:
        """A database failure reports the component without the raw driver text."""
        import mkobi.app as app_module

        class _FailingSession:
            async def execute(self, *args, **kwargs):
                raise RuntimeError("SENTINEL-DRIVER-ENDPOINT-MUST-NOT-LEAK")

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        def failing_get_session():
            return _FailingSession()

        monkeypatch.setattr(app_module, "get_session", failing_get_session)

        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        database_component = data["components"]["database"]
        assert database_component["status"] == "disconnected"
        assert "error" not in database_component
        assert "SENTINEL-DRIVER-ENDPOINT-MUST-NOT-LEAK" not in response.text

    async def test_existing_components_survive_alongside_redis(
        self, async_client: AsyncClient, auth_headers: dict[str, str], monkeypatch
    ) -> None:
        """The database, static_files and reconciler components still compose with redis."""
        import mkobi.app as app_module

        monkeypatch.setattr(
            app_module, "get_async_redis_client", lambda: _ReachableRedis()
        )

        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert response.status_code == 200
        components = response.json()["components"]
        assert components["database"]["status"] == "connected"
        assert components["database"]["type"] == "postgresql"
        assert components["static_files"]["status"] in {"available", "unavailable"}
        assert "path" not in components["static_files"]
        assert "stale_processing_reconciler" in components
        assert components["redis"]["status"] == "connected"

    async def test_health_poll_uses_shared_client_without_closing_it(
        self, async_client: AsyncClient, auth_headers: dict[str, str], monkeypatch
    ) -> None:
        """A health poll pings the process-wide client and does not close it.

        The client is shared across requests and closed once at lifespan
        teardown, so a poll must not release the pooled connections every later
        request depends on. This replaces the former per-poll close contract:
        pinging proves the poll observed the shared client, and an empty close
        list proves it left it open.
        """
        import mkobi.app as app_module

        closed: list[bool] = []
        probe = _ReachableRedis()
        probe.close_calls = closed

        monkeypatch.setattr(
            app_module, "get_async_redis_client", lambda: probe
        )

        response = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["components"]["redis"]["status"] == "connected"
        assert closed == [], "a health poll must not close the shared client"


class TestHealthWithRedisDown:
    """A Redis outage must not drag down /health or the overall detailed status."""

    async def test_health_still_healthy_when_redis_down(
        self, async_client: AsyncClient, auth_headers: dict[str, str], monkeypatch
    ) -> None:
        """/health stays 200 with database connected even if Redis cannot be reached."""
        import mkobi.core.redis_client as redis_client_module
        import mkobi.app as app_module

        monkeypatch.setattr(
            app_module, "get_async_redis_client", lambda: _UnreachableRedis()
        )
        monkeypatch.setattr(redis_client_module, "get_async_redis_client", lambda: _UnreachableRedis())

        response = await async_client.get(_HEALTH_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "database": "connected"}

        detailed = await async_client.get(
            _DETAILED_HEALTH_URL, headers=auth_headers
        )
        assert detailed.status_code == 200
        assert detailed.json()["status"] == "healthy"
        assert detailed.json()["components"]["database"]["status"] == "connected"


class _UnreachableRedis:
    """Async Redis double whose every command raises, modelling an outage."""

    async def set(self, *args, **kwargs):
        raise OSError("redis unavailable")

    async def eval(self, *args, **kwargs):
        raise OSError("redis unavailable")

    async def ping(self, *args, **kwargs):
        raise OSError("redis unavailable")

    async def aclose(self) -> None:
        pass


class _ReachableRedis:
    """Async Redis double that answers ping, modelling a reachable Redis.

    ``close_calls`` can be pointed at a list by the caller so a test can observe
    that the handler closed the client it built.
    """

    def __init__(self, close_calls: list[bool] | None = None) -> None:
        self.close_calls = close_calls

    async def ping(self, *args, **kwargs) -> bool:
        return True

    async def aclose(self) -> None:
        if self.close_calls is not None:
            self.close_calls.append(True)
