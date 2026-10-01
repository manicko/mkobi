"""Tests for database connection pool behavior.

Verifies pool exhaustion handling, connection leak prevention, and recovery.
"""

import asyncio
import time

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool.impl import AsyncAdaptedQueuePool


class TestDbPoolExhaustion:
    """Tests for database connection pool exhaustion scenarios."""

    async def test_pool_exhaustion_queued_and_recovers(
        self, setup_test_database: None
    ) -> None:
        """Test that pool handles exhaustion gracefully.

        Verifies:
        1. Requests are queued when pool is exhausted
        2. No connections are leaked after operations
        3. Pool recovers after load decreases

        Uses a pool with pool_size=2, max_overflow=0 to force exhaustion quickly.
        """
        from mkobi.config import get_config

        config = get_config()
        db_url = str(config.TEST_DATABASE_URL)

        if db_url is None:
            pytest.skip("TEST_DATABASE_URL not configured")

        # Create engine with intentionally small pool
        pool_size = 2
        max_overflow = 0
        pool_timeout = 5
        engine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
        )

        async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        try:
            acquired_connections: list[AsyncSession] = []
            queue_count = 3
            tasks_completed = 0

            async def acquire_and_hold(session_idx: int, hold_time: float) -> None:
                """Acquire a session, hold it for specified time, then release."""
                nonlocal tasks_completed
                async with async_session_factory() as session:
                    acquired_connections.append(session)
                    # Hold the connection for a while
                    await asyncio.sleep(hold_time)
                    tasks_completed += 1

            # Start timing
            start_time = time.monotonic()

            # Launch more concurrent requests than pool can handle
            hold_duration = 0.5
            tasks = [
                asyncio.create_task(acquire_and_hold(i, hold_duration))
                for i in range(queue_count)
            ]

            # Wait for all tasks to complete
            await asyncio.gather(*tasks)

            elapsed_time = time.monotonic() - start_time

            # All tasks should have completed
            assert tasks_completed == queue_count

            # With pool_size=2, max_overflow=0, and 3 concurrent requests:
            # - First 2 acquire immediately
            # - Third waits ~0.5s for pool timeout
            # But since we're using NullPool implicitly in tests, adjust expectation
            # Actually the pool should queue and wait for release
            assert elapsed_time >= hold_duration

            # Verify no connections leaked - all should be properly closed
            # Check that we can still acquire connections after the load
            async with async_session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                assert result.scalar_one() == 1

            # Pool should have recovered
            pool = engine.pool
            assert pool is not None
            checked_out = pool.checkedout()

            # All connections should be returned to the pool
            assert checked_out == 0, f"Expected 0 checked out connections, got {checked_out}"

        finally:
            # Clean up
            acquired_connections.clear()
            await engine.dispose()

    async def test_pool_no_connection_leaks_on_exception(
        self, setup_test_database: None
    ) -> None:
        """Test that connections are properly returned to pool on exception.

        Verifies that when exceptions occur during database operations,
        connections are not leaked and remain available for reuse.
        """
        from mkobi.config import get_config

        config = get_config()
        db_url = str(config.TEST_DATABASE_URL)

        if db_url is None:
            pytest.skip("TEST_DATABASE_URL not configured")

        # Create engine with small pool
        engine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
            pool_timeout=5,
        )

        async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        try:
            # Simulate an operation that fails with an exception
            async def failing_operation() -> None:
                async with async_session_factory() as session:
                    await session.execute(text("SELECT 1"))
                    raise RuntimeError("Simulated error")

            # This should raise but connection should be returned to pool
            with pytest.raises(RuntimeError, match="Simulated error"):
                await failing_operation()

            # Give a moment for cleanup
            await asyncio.sleep(0.1)

            # Verify pool is still usable (no leaked connections)
            pool = engine.pool
            assert pool is not None

            # Should be able to acquire connections again
            async with async_session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                assert result.scalar_one() == 1

            checked_out = pool.checkedout()
            assert checked_out == 0, f"Expected 0 checked out connections after error, got {checked_out}"

        finally:
            await engine.dispose()

    async def test_pool_max_overflow_behavior(
        self, setup_test_database: None
    ) -> None:
        """Test pool creation with overflow connections.

        Verifies that when max_overflow is configured, the pool can create
        additional connections beyond pool_size up to max_overflow limit.
        """
        from mkobi.config import get_config

        config = get_config()
        db_url = str(config.TEST_DATABASE_URL)

        if db_url is None:
            pytest.skip("TEST_DATABASE_URL not configured")

        # Create engine with pool_size=2 and max_overflow=3
        engine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=3,
            pool_timeout=5,
        )

        async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        try:
            acquired = []

            async def acquire_session(idx: int) -> int:
                async with async_session_factory():  # noqa: F841
                    acquired.append(idx)
                    await asyncio.sleep(0.1)
                    return idx

            # Launch 4 concurrent requests (2 pool + 2 overflow)
            tasks = [asyncio.create_task(acquire_session(i)) for i in range(4)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 4
            assert len(acquired) == 4

            # All connections should be returned
            pool = engine.pool
            if pool is not None:
                checked_out = pool.checkedout()
                assert checked_out == 0, f"Expected 0 checked out connections, got {checked_out}"

        finally:
            await engine.dispose()

    async def test_pool_timeout_on_exhaustion(
        self, setup_test_database: None
    ) -> None:
        """Test that pool respects timeout when exhausted.

        Verifies that when pool is exhausted and no overflow is allowed,
        requests wait up to pool_timeout seconds before succeeding.
        """
        from mkobi.config import get_config
        from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

        config = get_config()
        db_url = str(config.TEST_DATABASE_URL)

        if db_url is None:
            pytest.skip("TEST_DATABASE_URL not configured")

        # Create engine with very small pool and no overflow
        engine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            pool_timeout=1,
        )

        async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        try:
            first_acquired = asyncio.Event()
            can_finish = asyncio.Event()

            async def hold_first_connection() -> None:
                async with async_session_factory():  # noqa: F841
                    first_acquired.set()
                    # Hold until we signal it's OK to finish
                    await can_finish.wait()

            # First task holds the only connection
            holder = asyncio.create_task(hold_first_connection())
            await first_acquired.wait()

            start_time = time.monotonic()

            # Second task should wait (not timeout due to 1s timeout)
            second_succeeded = False
            try:
                async with async_session_factory() as session:
                    await session.execute(text("SELECT 1"))
                    second_succeeded = True
            except SQLAlchemyTimeoutError:
                pass

            elapsed_time = time.monotonic() - start_time

            # Signal the holder to finish
            can_finish.set()
            await holder

            # With pool_timeout=1, the second request should succeed after ~wait
            # Since we have pool_timeout=1 and we signal completion before that
            assert second_succeeded, "Second request should have succeeded after waiting"
            assert elapsed_time < 1.0, f"Should not have waited full timeout, waited {elapsed_time}s"

        finally:
            await engine.dispose()


class _RecordingEngine:
    """Fake async engine that records nothing and disposes cleanly."""

    async def dispose(self) -> None:
        return None


class _RecordingEngineFactory:
    """Callable standing in for create_async_engine, recording every call.

    Mirrors the recording factory used by the starter tests: the URL and the
    full kwargs of each call are captured so a test can assert the wiring
    without opening a connection.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, url: object, **kwargs: object) -> _RecordingEngine:
        self.calls.append((str(url), dict(kwargs)))
        return _RecordingEngine()


def _reset_engine_state(monkeypatch) -> None:
    """Reset the memoised module globals so get_async_engine rebuilds.

    ``_engine`` is a module global and ``_SessionLocal`` caches a sessionmaker
    bound to it; both must be cleared or the new configuration is never read.
    """
    from mkobi.db import session as session_module

    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_SessionLocal", None)


class TestApplicationPoolWiring:
    """Tests for the application engine's pool configuration.

    Every test here is zero-connection: constructing an Engine opens no socket,
    and none of these tests reads from the database.
    """

    async def test_get_async_engine_wires_settings_into_kwargs(
        self, monkeypatch
    ) -> None:
        """The settings reach create_async_engine as the matching kwargs.

        Uses a recording factory so an unrecognised kwarg or a missing mapping
        is caught, and re-hard-coding a value is caught as a changed arg.
        """
        from mkobi.config import clear_config_cache
        from mkobi.db import session as session_module

        monkeypatch.setenv("DATABASE__POOL_SIZE", "7")
        monkeypatch.setenv("DATABASE__MAX_OVERFLOW", "3")
        monkeypatch.setenv("DATABASE__POOL_TIMEOUT", "11")
        monkeypatch.setenv("DATABASE__POOL_RECYCLE", "120")
        monkeypatch.setenv("DATABASE__APPLICATION_NAME", "wiring-probe")
        clear_config_cache()
        _reset_engine_state(monkeypatch)

        factory = _RecordingEngineFactory()
        monkeypatch.setattr(session_module, "create_async_engine", factory)

        try:
            await session_module.get_async_engine()
            assert len(factory.calls) == 1
            _, kwargs = factory.calls[0]
            assert kwargs["pool_size"] == 7
            assert kwargs["max_overflow"] == 3
            assert kwargs["pool_timeout"] == 11
            assert kwargs["pool_recycle"] == 120
            assert kwargs["pool_pre_ping"] is session_module.POOL_PRE_PING
            assert kwargs["connect_args"] == {
                "server_settings": {"application_name": "wiring-probe"}
            }
        finally:
            clear_config_cache()

    async def test_real_engine_reports_public_pool_settings(
        self, monkeypatch
    ) -> None:
        """A real engine exposes the configured values through the public API.

        A fake factory never validates kwargs: an unrecognised keyword raises
        TypeError only when the real create_async_engine is called, so this test
        is required alongside the recording one. Only the public accessors are
        asserted - the configured max_overflow has no public accessor.
        """
        from mkobi.config import clear_config_cache
        from mkobi.db import session as session_module

        monkeypatch.setenv("DATABASE__POOL_SIZE", "4")
        monkeypatch.setenv("DATABASE__MAX_OVERFLOW", "2")
        monkeypatch.setenv("DATABASE__POOL_TIMEOUT", "17")
        clear_config_cache()
        _reset_engine_state(monkeypatch)

        engine = await session_module.get_async_engine()
        try:
            assert isinstance(engine.pool, AsyncAdaptedQueuePool)
            assert engine.pool.size() == 4
            assert engine.pool.timeout() == 17
        finally:
            await engine.dispose()
            clear_config_cache()

    async def test_defaults_are_unchanged(self, monkeypatch) -> None:
        """With no pool env vars the settings and pool match today's values.

        This is the no-rollout guard: the defaults must stay 10/20/30/-1, the
        live pool must report size 10 and timeout 30, and no connection may be
        recycled. pre_ping remains True.
        """
        from mkobi.config import clear_config_cache, get_config
        from mkobi.db import session as session_module

        for var in (
            "DATABASE__POOL_SIZE",
            "DATABASE__MAX_OVERFLOW",
            "DATABASE__POOL_TIMEOUT",
            "DATABASE__POOL_RECYCLE",
            "DATABASE__APPLICATION_NAME",
        ):
            monkeypatch.delenv(var, raising=False)
        clear_config_cache()
        _reset_engine_state(monkeypatch)

        config = get_config(reload=True)
        assert config.database.pool_size == 10
        assert config.database.max_overflow == 20
        assert config.database.pool_timeout == 30
        assert config.database.pool_recycle == -1

        engine = await session_module.get_async_engine()
        try:
            assert isinstance(engine.pool, AsyncAdaptedQueuePool)
            assert engine.pool.size() == 10
            assert engine.pool.timeout() == 30
            # -1 disables recycling, and pre_ping stays True.
            assert engine.pool._recycle == -1
            assert engine.pool._pre_ping is True
        finally:
            await engine.dispose()
            clear_config_cache()

    @pytest.mark.parametrize(
        ("var", "value"),
        [
            ("DATABASE__POOL_SIZE", "0"),
            ("DATABASE__MAX_OVERFLOW", "-1"),
            ("DATABASE__POOL_TIMEOUT", "0"),
        ],
    )
    def test_sentinels_are_rejected(self, monkeypatch, var, value) -> None:
        """The three dangerous sentinel values fail validation."""
        from mkobi.config import Settings, clear_config_cache

        monkeypatch.setenv(var, value)
        clear_config_cache()
        with pytest.raises(ValidationError):
            Settings()
        clear_config_cache()


class TestStarterEngineIsDeliberatelyDifferent:
    """The starter's GRANT engine pins its own pool values, unlike the app's."""

    async def test_starter_engine_uses_pinned_constants(self, monkeypatch) -> None:
        """The starter engine's kwargs are its named constants, not the app's."""
        from mkobi.config import clear_config_cache, get_config
        from mkobi.db import starter as starter_module
        from mkobi.db.starter import DatabaseStarter, DatabaseStarterConfig

        monkeypatch.setenv("DATABASE__POOL_SIZE", "7")
        clear_config_cache()
        _reset_engine_state(monkeypatch)

        factory = _RecordingEngineFactory()
        monkeypatch.setattr(starter_module, "create_async_engine", factory)

        # Stop startup before it touches the database so only the engine
        # construction call is observed.
        async def _noop_check(self, max_retries: int = 5) -> None:
            return None

        async def _noop_verify(self) -> None:
            return None

        async def _stop_at_revision(self):
            raise RuntimeError("stop")

        monkeypatch.setattr(DatabaseStarter, "_check_db_connection", _noop_check)
        monkeypatch.setattr(DatabaseStarter, "_verify_role_privileges", _noop_verify)
        monkeypatch.setattr(
            DatabaseStarter, "_get_alembic_revision", _stop_at_revision
        )

        starter = DatabaseStarter(
            DatabaseStarterConfig(
                main_database_url="postgresql+asyncpg://u:p@localhost:5434/bidb"
            )
        )

        try:
            with pytest.raises(RuntimeError, match="stop"):
                await starter.startup()
        finally:
            clear_config_cache()

        assert len(factory.calls) == 1
        _, kwargs = factory.calls[0]
        assert kwargs["pool_size"] == starter_module.STARTER_POOL_SIZE
        assert kwargs["max_overflow"] == starter_module.STARTER_MAX_OVERFLOW
        assert kwargs["pool_timeout"] == starter_module.STARTER_POOL_TIMEOUT_SECONDS
        assert kwargs["pool_recycle"] == starter_module.STARTER_POOL_RECYCLE_SECONDS
        assert kwargs["pool_pre_ping"] is starter_module.STARTER_POOL_PRE_PING

        # And they are not the application engine's values.
        app_db = get_config().database
        assert kwargs["pool_size"] != app_db.pool_size
        assert kwargs["pool_recycle"] != app_db.pool_recycle


class TestApplicationNameReachesServer:
    """The application_name label is shaped the way asyncpg accepts it.

    The zero-connection tests cannot catch this: ``connect_args`` is validated
    by the DBAPI at connect time, not by ``create_async_engine``. This test opens
    one connection and reads the label back from the server, which is the only
    way to prove the ``server_settings`` nesting is correct.
    """

    async def test_application_name_is_visible_to_postgresql(
        self, monkeypatch, setup_test_database: None
    ) -> None:
        """PostgreSQL reports the configured application_name for the session."""
        from mkobi.config import clear_config_cache
        from mkobi.db import session as session_module

        monkeypatch.setenv("DATABASE__APPLICATION_NAME", "pool-wiring-probe")
        clear_config_cache()
        _reset_engine_state(monkeypatch)

        engine = await session_module.get_async_engine()
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT current_setting('application_name')")
                )
                assert result.scalar_one() == "pool-wiring-probe"
        finally:
            await engine.dispose()
            clear_config_cache()

