"""Tests for database starter module.

Tests ensure_admin_user placeholder password rejection.
"""

import os

import pytest

# Set required env vars before importing app modules
os.environ.setdefault("DATABASE__HOST", "localhost")
os.environ.setdefault("DATABASE__PORT", "5434")
os.environ.setdefault("DATABASE__DBNAME", "bidb_test")
os.environ.setdefault("DATABASE__USER", "mkobi_app")
os.environ.setdefault("DATABASE__PASSWORD", "StrongDbP@ss123!")
os.environ.setdefault("DATABASE__ADMIN_USER", "postgres")
os.environ.setdefault("DATABASE__ADMIN_PASSWORD", "StrongT3stP@ss!")
os.environ.setdefault("DATABASE__TEST_DBNAME", "bidb_test")
os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")
os.environ.setdefault("ADMIN_USERNAME", "test_admin")
os.environ.setdefault("ADMIN_PASSWORD", "StrongT3stP@ss!")

from mkobi.db import starter as starter_module  # noqa: E402
from mkobi.db.starter import (  # noqa: E402
    DatabaseStarter,
    DatabaseStarterConfig,
    UnsafeTestDatabaseRecreationError,
    main,
)
from mkobi.models.enums import EnvironmentEnum  # noqa: E402


class TestEnsureAdminUserPlaceholderCheck:
    """Tests for placeholder password rejection in ensure_admin_user()."""

    # Every value below is refused by the shared composite. The set spans all
    # four clauses so each branch is driven through the starter path, not just
    # the exact WEAK_PASSWORDS membership test.
    @pytest.mark.parametrize("weak_password", [
        # exact WEAK_PASSWORDS members
        "password",
        "123456",
        "admin",
        "secret",
        "test",
        "admin@example.com",
        "change_me_admin_password",
        "CHANGE_ME",
        "change_me",
        "placeholder",
        "postgres",
        # change_me prefix but not an exact member
        "CHANGE_ME_GENERATE_STRONG_PASSWORD",
        "change_me_generate_strong_secret",
        # empty / whitespace-only
        "",
        "        ",
        # below the minimum length
        "Ab1!",
    ])
    def test_ensure_admin_user_rejects_placeholder_password(
        self, monkeypatch, weak_password
    ):
        """Verify ensure_admin_user raises ValueError for every weak-password clause.

        The failure must happen before any session is acquired, so the test is
        database-free.
        """
        monkeypatch.setenv("ADMIN_PASSWORD", weak_password)
        monkeypatch.setenv("ADMIN_USERNAME", "test_admin")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        # The starter is constructed at the production tier, the tier at which
        # the guard refuses; the shared composite still runs in every tier.
        starter = DatabaseStarter(
            DatabaseStarterConfig(env=EnvironmentEnum.PRODUCTION)
        )

        # This should raise ValueError before any database session is acquired.
        import asyncio

        with pytest.raises(ValueError, match="known placeholder value"):
            asyncio.run(starter.ensure_admin_user())

    def test_ensure_admin_user_warns_and_proceeds_in_development(
        self, monkeypatch
    ):
        """Verify a weak password warns and proceeds in the development tier."""
        monkeypatch.setenv("ADMIN_PASSWORD", "CHANGE_ME_GENERATE_STRONG_PASSWORD")
        monkeypatch.setenv("ADMIN_USERNAME", "test_admin")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        # The development branch deliberately proceeds to the insert; pin the
        # session factory to a sentinel async context manager so no live
        # database connection is required.
        class _FakeSession:
            async def __aenter__(self):
                raise AssertionError(
                    "development branch must proceed to the session factory, "
                    "but the insert must not be exercised by this test"
                )

            async def __aexit__(self, *exc_info):
                return False

        async def _sentinel_sessionlocal():
            return _FakeSession

        monkeypatch.setattr(
            "mkobi.db.session.get_async_sessionlocal", _sentinel_sessionlocal
        )

        starter = DatabaseStarter(
            DatabaseStarterConfig(env=EnvironmentEnum.DEVELOPMENT)
        )

        # Capture the warning through a handler attached directly to the
        # emitting logger. The application's logging setup runs with
        # disable_existing_loggers=True and propagate=False, and an earlier
        # test in a full session can leave mkobi.db.starter unable to reach
        # pytest's caplog root handler, so caplog is not reliable here.
        import asyncio
        import logging

        starter_logger = logging.getLogger("mkobi.db.starter")
        captured: list[logging.LogRecord] = []

        class _Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        collector = _Collector(level=logging.WARNING)
        original_level = starter_logger.level
        starter_logger.addHandler(collector)
        starter_logger.setLevel(logging.WARNING)
        # A disabled logger drops records before any handler runs.
        was_disabled = starter_logger.disabled
        starter_logger.disabled = False
        try:
            # Should not raise - development only warns; the session factory is
            # reached, which proves the guard did not refuse in this tier.
            with pytest.raises(AssertionError, match="session factory"):
                asyncio.run(starter.ensure_admin_user())
        finally:
            starter_logger.removeHandler(collector)
            starter_logger.setLevel(original_level)
            starter_logger.disabled = was_disabled

        # The warning is the other half of 'warns and proceeds' - assert it fired.
        assert any(
            "Admin password is a known placeholder value" in record.getMessage()
            for record in captured
        )


class _RecordingConnection:
    """Fake connection that records the statements issued against it."""

    def __init__(self, recorder: list[str]) -> None:
        self._recorder = recorder
        from sqlalchemy.dialects import postgresql

        self.dialect = postgresql.dialect()

    async def execute(self, statement, params=None):
        try:
            rendered = str(statement.compile(dialect=self.dialect))
        except Exception:
            rendered = repr(statement)
        self._recorder.append(rendered)
        return None


class _RecordingConnectContext:
    """Async context manager yielding a recording connection."""

    def __init__(self, recorder: list[str]) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> _RecordingConnection:
        return _RecordingConnection(self._recorder)

    async def __aexit__(self, *exc_info) -> bool:
        return False


class _RecordingEngine:
    """Fake async engine whose connections record every statement."""

    def __init__(self, recorder: list[str]) -> None:
        self._recorder = recorder

    def connect(self) -> _RecordingConnectContext:
        return _RecordingConnectContext(self._recorder)

    async def dispose(self) -> None:
        return None


class _RecordingEngineFactory:
    """Callable standing in for create_async_engine, recording every call."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.statements: list[str] = []

    def __call__(self, url, **kwargs) -> _RecordingEngine:
        self.calls.append(str(url))
        return _RecordingEngine(self.statements)


async def _noop_apply_migrations(self, db_url: str) -> None:
    """Stand-in for migration application so no Alembic run is required."""
    return None


_TEST_DB_URL = "postgresql+asyncpg://mkobi_app:pw@localhost:5434/bidb_test"
_TEST_ADMIN_URL = "postgresql+asyncpg://postgres:pw@localhost:5434/postgres"


class _ConfiguredEnvironment:
    """Minimal stand-in exposing only the configured application environment."""

    def __init__(self, environment: EnvironmentEnum) -> None:
        self.environment = environment


def _pin_configured_env(monkeypatch, environment: EnvironmentEnum) -> None:
    """Pin the configured application environment seen by the starter module."""
    monkeypatch.setattr(
        starter_module, "get_config", lambda: _ConfiguredEnvironment(environment)
    )


class TestRecreateTestDatabaseGuards:
    """Tests for the destructive-recreation guards in recreate_test_database()."""

    def test_recreates_guarded_test_database(self, monkeypatch):
        """A test-tier, test-named database is recreated successfully.

        This is the positive path: it fails if either guard is over-tight. It
        relies on the configured environment being the test tier, which is how
        the session-scoped setup_test_database fixture (tests/conftest.py)
        calls this function.
        """
        factory = _RecordingEngineFactory()
        monkeypatch.setattr(starter_module, "create_async_engine", factory)
        monkeypatch.setattr(DatabaseStarter, "_apply_migrations", _noop_apply_migrations)

        starter = DatabaseStarter(
            DatabaseStarterConfig(
                test_database_url=_TEST_DB_URL,
                test_admin_database_url=_TEST_ADMIN_URL,
                recreate_test_db=True,
            )
        )

        import asyncio

        asyncio.run(starter.recreate_test_database())

        # The destructive path ran: the admin engine was created and the
        # terminate/drop/create statements were issued.
        assert factory.calls, "recreation must create an admin engine"
        assert any(
            "pg_terminate_backend" in statement for statement in factory.statements
        )
        assert any(
            "DROP DATABASE" in statement or "CREATE DATABASE" in statement
            for statement in factory.statements
        )

    def test_refuses_production_tier(self, monkeypatch):
        """A production tier refuses before any statement is issued."""
        factory = _RecordingEngineFactory()
        monkeypatch.setattr(starter_module, "create_async_engine", factory)
        _pin_configured_env(monkeypatch, EnvironmentEnum.PRODUCTION)

        starter = DatabaseStarter(
            DatabaseStarterConfig(
                test_database_url=_TEST_DB_URL,
                test_admin_database_url=_TEST_ADMIN_URL,
                recreate_test_db=True,
            )
        )

        import asyncio

        with pytest.raises(UnsafeTestDatabaseRecreationError, match="not 'test'"):
            asyncio.run(starter.recreate_test_database())

        # The refusal happened BEFORE any target-database statement: no engine
        # was created and nothing was issued. Asserting only the exception would
        # also pass if the drop ran and the guard fired afterwards.
        assert factory.calls == []
        assert factory.statements == []

    def test_refuses_non_test_database_name(self, monkeypatch):
        """A test tier pointed at a non-test name still refuses.

        This is the misconfigured-name check that would have prevented the
        finding.
        """
        factory = _RecordingEngineFactory()
        monkeypatch.setattr(starter_module, "create_async_engine", factory)
        _pin_configured_env(monkeypatch, EnvironmentEnum.TEST)

        starter = DatabaseStarter(
            DatabaseStarterConfig(
                test_database_url="postgresql+asyncpg://mkobi_app:pw@localhost:5434/bidb",
                test_admin_database_url=_TEST_ADMIN_URL,
                recreate_test_db=True,
            )
        )

        import asyncio

        with pytest.raises(UnsafeTestDatabaseRecreationError, match="does not match"):
            asyncio.run(starter.recreate_test_database())

        assert factory.calls == []
        assert factory.statements == []

    @pytest.mark.parametrize("db_name", ["bidb_test", "bidb_test_gw0", "bidb_test_w1"])
    def test_accepts_convention_names(self, monkeypatch, db_name):
        """Worker-isolated names from conftest's convention are accepted."""
        factory = _RecordingEngineFactory()
        monkeypatch.setattr(starter_module, "create_async_engine", factory)
        monkeypatch.setattr(DatabaseStarter, "_apply_migrations", _noop_apply_migrations)
        _pin_configured_env(monkeypatch, EnvironmentEnum.TEST)

        starter = DatabaseStarter(
            DatabaseStarterConfig(
                test_database_url=f"postgresql+asyncpg://mkobi_app:pw@localhost:5434/{db_name}",
                test_admin_database_url=_TEST_ADMIN_URL,
                recreate_test_db=True,
            )
        )

        import asyncio

        asyncio.run(starter.recreate_test_database())

        assert factory.calls, "a convention-matching name must not be refused"


class TestRecreateTestDatabaseCliGuard:
    """Tests that the --recreate-test-db CLI path is guarded too."""

    def test_cli_refuses_production_tier(self, monkeypatch):
        """main() refuses on a production tier instead of dropping a database."""
        factory = _RecordingEngineFactory()
        monkeypatch.setattr(starter_module, "create_async_engine", factory)
        # The CLI reads the configured tier through get_config(); pin it to a
        # production stub so no real production settings are required.
        _pin_configured_env(monkeypatch, EnvironmentEnum.PRODUCTION)
        monkeypatch.setattr(
            "sys.argv", ["mkobi.db.starter", "--recreate-test-db"]
        )

        with pytest.raises(UnsafeTestDatabaseRecreationError, match="not 'test'"):
            main()

        # The CLI path must refuse before reaching any destructive call.
        assert factory.calls == []
        assert factory.statements == []
