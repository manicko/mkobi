"""Common fixtures for tests."""
import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Set required environment variables before ANY mkobi module imports
# This must be at the very top of this file before other imports
# Use setdefault to allow Docker Compose env vars to take precedence in containers
os.environ.setdefault("ENV", "test")
os.environ.setdefault("DATABASE__HOST", "localhost")
os.environ.setdefault("DATABASE__PORT", "5434")
os.environ.setdefault("DATABASE__DBNAME", "bidb_test")
os.environ.setdefault("DATABASE__USER", "mkobi_app")
os.environ.setdefault("DATABASE__PASSWORD", "test_app_password")
os.environ.setdefault("DATABASE__ADMIN_USER", "postgres")
os.environ.setdefault("DATABASE__ADMIN_PASSWORD", "test_password")
os.environ.setdefault("ADMIN_USERNAME", "test_admin")
os.environ.setdefault("ADMIN_PASSWORD", "test-password-for-integration-tests")
os.environ.setdefault("DATABASE__TEST_DBNAME", "bidb_test")
os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")
os.environ.setdefault("REDIS__HOST", "localhost")
os.environ.setdefault("REDIS__PORT", "6379")
os.environ.setdefault("RECREATE_TEST_DB", "true")


def pytest_load_initial_conftests(early_config, parser, args):
    """Pytest hook that runs before conftest.py is fully loaded.
    
    This ensures environment variables are set before ANY test modules
    are imported during collection.
    """
    # Use setdefault to allow Docker Compose env vars to take precedence in containers
    os.environ.setdefault("ENV", "test")
    os.environ.setdefault("DATABASE__HOST", "localhost")
    os.environ.setdefault("DATABASE__PORT", "5434")
    os.environ.setdefault("DATABASE__DBNAME", "bidb_test")
    os.environ.setdefault("DATABASE__USER", "mkobi_app")
    os.environ.setdefault("DATABASE__ADMIN_USER", "postgres")
    os.environ.setdefault("DATABASE__PASSWORD", "test_app_password")
    os.environ.setdefault("DATABASE__ADMIN_PASSWORD", "test_password")
    os.environ.setdefault("ADMIN_USERNAME", "test_admin")
    os.environ.setdefault("ADMIN_PASSWORD", "test-password-for-integration-tests")
    os.environ.setdefault("DATABASE__TEST_DBNAME", "bidb_test")
    os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")
    os.environ.setdefault("REDIS__HOST", "localhost")
    os.environ.setdefault("REDIS__PORT", "6379")
    os.environ.setdefault("RECREATE_TEST_DB", "true")

# Import config module - this will create the singleton with test env vars
from mkobi.config import clear_config_cache, get_config, Settings  # noqa: E402, F401

# Clear any cached config from previous imports and initialize with test env vars
clear_config_cache()
_config = get_config()

# Validate that JWT secret key is set before proceeding
if _config.jwt.secret_key is None:
    raise RuntimeError(
        "JWT__SECRET_KEY must be set in environment before tests run. "
        f"Current value: {repr(_config.jwt.secret_key)}"
    )


def pytest_sessionstart(session):
    """Ensure config is properly initialized at session start.
    
    This hook runs after conftest.py is loaded but before any tests run,
    ensuring all imports have access to the correct test configuration.
    """
    from mkobi.config import clear_config_cache, get_config
    
    # Re-clear and reinitialize to ensure clean state after any early imports
    clear_config_cache()
    config = get_config()
    
    if config.jwt.secret_key is None:
        raise RuntimeError(
            "JWT__SECRET_KEY must be set in environment before tests run. "
            f"Current value: {repr(config.jwt.secret_key)}"
        )


def pytest_sessionfinish(session, exitstatus):
    """Clean up temporary files after all tests complete.

    This hook ensures that temp files created during tests are cleaned up
    even if tests fail or are interrupted. Deletes all CSV files from the
    upload temp directory.
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        from mkobi.services.file_cleanup import cleanup_stale_temp_files

        # max_age_hours=0 means delete all files immediately regardless of age.
        # The result is a CleanupResult; read its ``deleted`` count. No ceiling is
        # enforced here (the sweep applies none), so this session cleanup cannot
        # inherit an inherited byte/count limit.
        result = cleanup_stale_temp_files(max_age_hours=0)

        if result.deleted > 0:
            logger.info("Cleaned up %d temp files after test session", result.deleted)
    except Exception as e:
        # Log cleanup failures but don't fail the test session
        logger.warning("Failed to clean up temp files after test session: %s", e)


def pytest_configure(config):
    """Ensure config is properly initialized before tests run."""
    # Config should already be initialized above, this is just a sanity check
    _ = _config  # noqa: F841


# Import models for metadata registration (after config is initialized)
from mkobi.db.models import (  # noqa: E402, F401
    AggregatedData,
    Dashboard,
    DashboardAccess,
    Filter,
    Graph,
    Layout,
    ProcessingConfig,
    ProcessingLog,
    RegistrationRequest,
    User,
)

# Import security functions (after config is initialized)
from mkobi.core.security import (  # noqa: E402, F401
    AsyncRateLimiter,
    create_access_token,
    hash_password,
)
from mkobi.db.repositories.user_repo import UserRepository  # noqa: E402, F401


def _get_worker_db_suffix() -> str:
    """Get database suffix for xdist worker isolation.

    When running with pytest-xdist, each worker gets a unique id like 'gw0', 'gw1'.
    We use this to create separate databases per worker for complete isolation.
    """
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")
    if worker_id:
        return f"_{worker_id}"
    return ""


def _build_worker_isolated_test_db_url() -> str:
    """Build test database URL with worker isolation suffix for xdist."""
    from urllib.parse import urlparse, urlunparse

    base_url = str(_config.TEST_DATABASE_URL)
    if not base_url:
        raise RuntimeError("TEST_DATABASE_URL not configured")

    # Add worker suffix for xdist parallel execution isolation
    worker_suffix = _get_worker_db_suffix()
    parsed = urlparse(base_url)
    path = parsed.path
    if path.startswith("/") and worker_suffix:
        path = f"/{path[1:]}{worker_suffix}"
    return urlunparse(parsed._replace(path=path))


# Use worker-isolated URL for parallel xdist execution
TEST_ASYNC_DB_URL = _build_worker_isolated_test_db_url()


class MockRedis:
    """Mock Redis client for testing rate limiter without real Redis."""

    def __init__(self):
        self._data = {}
        self._ttls = {}

    async def get(self, key):
        return self._data.get(key)

    async def set(self, key, value, ex=None):
        """Set a key with optional TTL (TTL not enforced in mock)."""
        self._data[key] = value

    async def exists(self, key):
        """Check if key exists in mock Redis."""
        return 1 if key in self._data else 0

    async def setex(self, key, ttl, value):
        """Set key with TTL in mock Redis."""
        self._data[key] = value
        self._ttls[key] = ttl

    def pipeline(self, transaction=True):
        return MockPipeline(self)

    async def incr(self, key):
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = str(val)
        return val

    async def expire(self, key, ttl):
        self._ttls[key] = ttl

    async def ttl(self, key):
        """Return TTL for key."""
        return self._ttls.get(key, 300)

    async def execute(self):
        pass

    async def close(self):
        pass

    def clear(self):
        """Clear all stored data for test isolation."""
        self._data = {}
        self._ttls = {}


class MockPipeline:
    """Mock pipeline that supports async with."""

    def __init__(self, redis_client):
        self._redis = redis_client
        self._commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def incr(self, key):
        return await self._redis.incr(key)

    async def expire(self, key, ttl):
        return await self._redis.expire(key, ttl)

    def get(self, key):
        """Queue GET command for later execution.

        Note: Redis-py pipeline commands are synchronous (just queue),
        only execute() is async.
        """
        self._commands.append(("get", key))

    def delete(self, key):
        """Queue DELETE command for later execution.

        Note: Redis-py pipeline commands are synchronous (just queue),
        only execute() is async.
        """
        self._commands.append(("delete", key))

    async def execute(self):
        """Execute all queued commands and return results.

        Returns list of results matching the order of queued commands.
        For GET commands, returns the value; for DELETE, returns the count.
        """
        results = []
        for cmd_type, key in self._commands:
            if cmd_type == "get":
                results.append(self._redis._data.get(key))
            elif cmd_type == "delete":
                if key in self._redis._data:
                    del self._redis._data[key]
                    results.append(1)
                else:
                    results.append(0)
        self._commands.clear()
        return results


# Store original AuthService.__init__ before any patches are applied
# This will be used by strict_redis to restore real rate limiting behavior
_original_auth_init = None


def _get_original_auth_init():
    """Get the original AuthService.__init__ method."""
    global _original_auth_init
    if _original_auth_init is None:
        import mkobi.services.auth_service as auth_service_module
        _original_auth_init = auth_service_module.AuthService.__init__
    return _original_auth_init


@pytest.fixture(autouse=True)
def _reset_config_cache():
    """Reset the settings singleton around every test.

    ``mkobi.config`` memoises Settings in a module-level ``_settings`` and
    exposes ``clear_config_cache()`` as the only reset. A test that mutates
    ``os.environ`` and clears the cache mid-test leaves the singleton built from
    its throwaway values; ``monkeypatch`` restores the environment, but nothing
    restored the cache. Every later test then read the previous test's
    configuration, including a foreign ``JWT__SECRET_KEY``.

    Setup discards any cache inherited from a previous test, so the suite's
    canonical configuration - the environment captured at import by the
    ``setdefault`` block above - is what this test sees regardless of ordering.
    Teardown restores the environment snapshot taken at setup and rebuilds the
    singleton from it, so the cache cannot survive a test and the next test
    starts from the baseline rather than from ``None`` reconstructed out of a
    mutated environment. Restoring the environment first is required: a test
    may write to ``os.environ`` directly, bypassing ``monkeypatch``, and that
    write is still present when this teardown runs, so rebuilding without the
    snapshot would read the mutated values and raise.

    The manual ``clear_config_cache()`` calls inside tests remain load-bearing:
    a test that mutates the environment and reads config mid-test needs the
    cache cleared before that read, which teardown cannot provide.
    """
    env_snapshot = dict(os.environ)
    clear_config_cache()
    get_config()
    yield
    os.environ.clear()
    os.environ.update(env_snapshot)
    clear_config_cache()
    get_config()


@pytest.fixture(autouse=True)
def _auto_mock_redis(monkeypatch):
    """Auto-mock Redis client for all tests to avoid requiring a real Redis server.

    This fixture is always active and patches get_async_redis_client and
    get_redis_client to use an in-memory MockRedis instance. It also
    patches AuthService to bypass rate limiting by default, so existing
    tests don't break. Tests that need real rate limiting behavior should
    use the strict_redis fixture.
    """
    # Ensure we capture the original __init__ before patching
    _ = _get_original_auth_init()

    mock_redis_client = MockRedis()

    import mkobi.core.redis_client as redis_client_module

    def mock_get_async_redis_client():
        return mock_redis_client

    def mock_get_redis_client():
        return mock_redis_client

    monkeypatch.setattr(redis_client_module, "get_async_redis_client", mock_get_async_redis_client)
    monkeypatch.setattr(redis_client_module, "get_redis_client", mock_get_redis_client)

    # Patch auth service rate limiter to always allow (backward compatibility)
    import mkobi.services.auth_service as auth_service_module

    original_init = _get_original_auth_init()

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # Make check_rate_limit always return True (allow all)
        async def always_true(*a, **kw):
            return (True, None)

        self._rate_limiter.check_rate_limit = always_true

    monkeypatch.setattr(auth_service_module.AuthService, "__init__", patched_init)


@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis client for tests that need to bypass rate limiting.

    Opt-in fixture - only use when rate limiting should be explicitly
    bypassed. Applies a patched AuthService that always allows login attempts.
    """
    mock_redis_client = MockRedis()

    # Patch get_async_redis_client to return mock
    import mkobi.core.redis_client as redis_client_module

    def mock_get_async_redis_client():
        return mock_redis_client

    monkeypatch.setattr(redis_client_module, "get_async_redis_client", mock_get_async_redis_client)

    # Patch auth service rate limiter to always allow
    import mkobi.services.auth_service as auth_service_module

    original_init = auth_service_module.AuthService.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # Make check_rate_limit always return True (allow all)
        async def always_true(*a, **kw):
            return (True, None)

        self._rate_limiter.check_rate_limit = always_true

    monkeypatch.setattr(auth_service_module.AuthService, "__init__", patched_init)


@pytest.fixture
def strict_redis(monkeypatch):
    """Provide real rate limiting behavior for tests.

    Uses an in-memory MockRedis client that tracks state, allowing rate
    limiting logic to be properly tested without a real Redis server.
    Unlike the default autouse mock, this does NOT patch check_rate_limit
    — the AsyncRateLimiter will actually count attempts and block excess
    requests.
    """
    mock_redis_client = MockRedis()

    # Patch get_async_redis_client to return mock
    import mkobi.core.redis_client as redis_client_module

    def mock_get_async_redis_client():
        return mock_redis_client

    monkeypatch.setattr(redis_client_module, "get_async_redis_client", mock_get_async_redis_client)

    # Restore real rate limiting behavior by patching AuthService.__init__
    # to use the original implementation (not the always-True patched version)
    import mkobi.services.auth_service as auth_service_module

    original_init = _get_original_auth_init()
    monkeypatch.setattr(auth_service_module.AuthService, "__init__", original_init)

    yield mock_redis_client


@pytest.fixture(scope="session")
async def setup_test_database():
    """Fixture to set up test database before tests run.
    
    Uses pytest-asyncio event loop to avoid loop conflicts.
    Recreates the test database and applies migrations.
    This fixture has session scope to run once before all tests.
    When running with xdist, each worker gets its own isolated database.
    """
    from mkobi.db.starter import DatabaseStarter, DatabaseStarterConfig
    from mkobi.config import get_config, clear_config_cache
    from urllib.parse import urlparse, urlunparse

    clear_config_cache()
    config = get_config()

    # Build worker-isolated database URL
    worker_suffix = _get_worker_db_suffix()
    test_db_name = f"bidb_test{worker_suffix}" if worker_suffix else config.database.test_dbname

    # Build isolated database URLs for xdist workers
    parsed_main = urlparse(str(config.DATABASE_URL))
    isolated_test_url = urlunparse(parsed_main._replace(path=f"/{test_db_name}"))

    parsed_admin = urlparse(str(config.test_admin_database_url))
    isolated_admin_url = urlunparse(parsed_admin._replace(path=f"/{test_db_name}"))

    starter_config = DatabaseStarterConfig(
        main_database_url=config.DATABASE_URL,
        test_database_url=isolated_test_url,
        test_admin_database_url=isolated_admin_url,
        recreate_test_db=True,
    )
    await DatabaseStarter(starter_config).recreate_test_database()
    yield
    # Optional: cleanup after all tests
    # Could drop the test database here if needed


@pytest.fixture(scope="session")
async def async_test_engine(setup_test_database):
    """Fixture for creating async test DB engine.
    
    Uses NullPool to prevent connection pooling issues in tests:
    - Avoids zombie connections
    - Prevents "database is being accessed by other users" errors
    - Eliminates asyncpg stale connection issues
    - Reduces intermittent CI failures
    """
    engine = create_async_engine(
        TEST_ASYNC_DB_URL,
        echo=False,
        pool_pre_ping=True,
        poolclass=NullPool,
    )
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def async_session_maker(async_test_engine):
    """Fixture for creating async session factory."""
    async_session = async_sessionmaker(
        async_test_engine, class_=AsyncSession, expire_on_commit=False
    )
    return async_session


@pytest.fixture(scope="function")
async def async_db_session(async_session_maker):
    """Fixture for creating async DB session for tests.

    Opens a nested transaction (SAVEPOINT) and rolls it back when the test
    ends. This isolates only work that stays inside that SAVEPOINT.

    It does not give full per-test isolation. ``Session.commit()`` inside a
    test commits the session's root transaction, and the fixture's rollback of
    the SAVEPOINT does not undo it: committed rows persist in the test database
    and are visible to later tests. Cross-test cleanup is therefore the test's
    responsibility. The ``delete(...)`` blocks shipped in tests that create
    such rows are load-bearing, not redundant, and must not be removed.
    """
    from sqlalchemy import event

    async with async_session_maker() as session:
        # Register a listener to start a new SAVEPOINT after each commit/rollback
        # This allows tests to use commit() while maintaining isolation
        # Note: Must listen on sync_session for AsyncSession
        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(sess, trans):
            if trans.nested and not trans._parent.nested:
                # End the current nested transaction
                sess.begin_nested()

        # Start the initial SAVEPOINT
        await session.begin_nested()
        try:
            yield session
        finally:
            # Rollback to SAVEPOINT
            await session.rollback()
            await session.close()


@pytest.fixture(scope="session")
async def baseline_data(setup_test_database):
    """Load minimal reference data once per test session.

    This fixture is a placeholder for future reference data loading.
    Currently ensures the test database is properly initialized.
    """
    yield


@pytest.fixture
def mock_db():
    """Mock AsyncSession for unit tests that don't need a real database.

    Service methods now require db as a mandatory parameter.
    This fixture provides a MagicMock that satisfies the type checker
    for unit tests with mocked repositories.
    """
    from unittest.mock import AsyncMock
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
async def async_client(async_db_session):
    """Fixture for creating async HTTP client.

    Overrides the get_db_dependency to use the test's session.
    This ensures the API and test use the same session.
    """
    from mkobi.api.deps import (
        get_db_dependency,
        get_redis_client_dependency,
        get_temp_password_store,
    )
    from mkobi.main import app
    import httpx
    from httpx import ASGITransport
    from mkobi.core.temp_password_store import TempPasswordStore

    # Override the database dependency to use test session
    async def override_get_db() -> AsyncSession:
        yield async_db_session

    app.dependency_overrides[get_db_dependency] = override_get_db

    # Create a mock Redis client for testing
    mock_redis = MockRedis()
    async def override_get_redis():
        return mock_redis
    app.dependency_overrides[get_redis_client_dependency] = override_get_redis

    # Override TempPasswordStore to use the same mock Redis
    def override_get_temp_password():
        return TempPasswordStore(redis_client=mock_redis)
    app.dependency_overrides[get_temp_password_store] = override_get_temp_password

    # Store mock_redis on the app for access by tests
    app.state.mock_redis = mock_redis

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver/api/v1"
    ) as client:
        yield client

    # Clear overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
async def authenticated_client(async_client, auth_headers):
    """Returns HTTP client with authorization headers set."""
    async_client.headers.update(auth_headers)
    yield async_client


@pytest.fixture
async def test_user(async_db_session) -> dict[str, str | object]:
    """Creates test user and returns data with token."""
    unique_id = str(uuid4())[:8]

    # UserRepository doesn't store db - it's passed to each method
    repo = UserRepository()
    user = await repo.create(
        db=async_db_session,
        email=f"test_{unique_id}@example.com",
        password_hash=hash_password("TestPass123!"),
        role="admin",
    )
    # Commit the user so the API can see it
    await async_db_session.commit()

    token = create_access_token({"user_id": str(user.id), "email": user.email})

    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "token": token,
    }


@pytest.fixture
def auth_headers(test_user) -> dict[str, str]:
    """Returns authorization headers with JWT token."""
    return {"Authorization": f"Bearer {test_user['token']}"}


@pytest.fixture
def valid_csv_content() -> bytes:
    """CSV content large enough for libmagic to detect as text/csv."""
    header = "category,region,sales,profit,date,qty\n"
    rows = "\n".join(
        f"{chr(65+i)},Region{i},{100+i*10},{25+i*5},2023-01-{i+1:02d},{10+i}"
        for i in range(10)
    )
    return (header + rows).encode("utf-8")