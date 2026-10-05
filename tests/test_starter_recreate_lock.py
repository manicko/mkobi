"""Tests for the per-name exclusion in ``recreate_test_database`` (MIGB-9).

These tests live in their own module so ``tests/test_starter.py`` stays
unmodified while the new behaviour is pinned. They reuse the recording-engine
shape of that module's fakes, kept local so this file has no import dependency
on a non-package test module.

The defect: two concurrent runs can both pass the guards and then both
``DROP DATABASE``. The fix is one bounded advisory acquisition placed *after*
both guards and *before* ``pg_terminate_backend``. The ordering is the fix, so
these tests assert placement, not merely that a lock is taken.
"""

import asyncio
import os

import pytest

# Set required env vars before importing app modules (mirrors test_starter.py).
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
)
from mkobi.db.test_database_lock import (  # noqa: E402
    TEST_DB_RECREATE_LOCK_NAMESPACE,
    test_db_recreate_lock_key as derive_lock_key,
)
from mkobi.models.enums import EnvironmentEnum  # noqa: E402

_TEST_DB_URL = "postgresql+asyncpg://mkobi_app:pw@localhost:5434/bidb_test"
_TEST_ADMIN_URL = "postgresql+asyncpg://postgres:pw@localhost:5434/postgres"

_LOCK_MARKER = "pg_advisory_lock"
_UNLOCK_MARKER = "pg_advisory_unlock"
_TERMINATE_MARKER = "pg_terminate_backend"


async def _noop_apply_migrations(self, db_url: str) -> None:
    """Stand-in so no Alembic run is required."""
    return None


class _ConfiguredEnvironment:
    """Minimal stand-in exposing only the configured application environment."""

    def __init__(self, environment: EnvironmentEnum) -> None:
        self.environment = environment


class _RecordingTransaction:
    _BEGIN_MARKER = "\x00BEGIN"
    _END_MARKER = "\x00END"

    def __init__(
        self,
        recorder: list[str],
        params: list[dict],
        boundaries: list[tuple[str, str]],
    ) -> None:
        self._recorder = recorder
        self._params = params
        self._boundaries = boundaries

    async def __aenter__(self) -> "_RecordingTransaction":
        self._recorder.append(self._BEGIN_MARKER)
        self._params.append({})
        self._boundaries.append(("begin", ""))
        return self

    async def __aexit__(self, *exc_info) -> bool:
        self._recorder.append(self._END_MARKER)
        self._params.append({})
        self._boundaries.append(("end", ""))
        return False


class _RecordingConnection:
    """Fake connection recording statements and their bind parameters."""

    def __init__(
        self,
        recorder: list[str],
        params: list[dict],
        boundaries: list[tuple[str, str]],
    ) -> None:
        self._recorder = recorder
        self._params = params
        self._boundaries = boundaries
        from sqlalchemy.dialects import postgresql

        self.dialect = postgresql.dialect()

    def begin(self) -> _RecordingTransaction:
        return _RecordingTransaction(self._recorder, self._params, self._boundaries)

    async def execute(self, statement, parameters=None):
        try:
            rendered = str(statement.compile(dialect=self.dialect))
        except Exception:
            rendered = repr(statement)
        self._recorder.append(rendered)
        self._params.append(dict(parameters) if parameters else {})
        return None


class _RecordingConnectContext:
    def __init__(
        self,
        recorder: list[str],
        params: list[dict],
        boundaries: list[tuple[str, str]],
    ) -> None:
        self._recorder = recorder
        self._params = params
        self._boundaries = boundaries

    async def __aenter__(self) -> _RecordingConnection:
        return _RecordingConnection(self._recorder, self._params, self._boundaries)

    async def __aexit__(self, *exc_info) -> bool:
        return False


class _RecordingEngine:
    def __init__(
        self,
        recorder: list[str],
        params: list[dict],
        boundaries: list[tuple[str, str]],
    ) -> None:
        self._recorder = recorder
        self._params = params
        self._boundaries = boundaries

    def connect(self) -> _RecordingConnectContext:
        return _RecordingConnectContext(self._recorder, self._params, self._boundaries)

    async def dispose(self) -> None:
        return None


class _RecordingEngineFactory:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.statements: list[str] = []
        self.parameters: list[dict] = []
        self.boundaries: list[tuple[str, str]] = []
        self.engine_kwargs: list[dict] = []

    def __call__(self, url, **kwargs) -> _RecordingEngine:
        self.calls.append(str(url))
        self.engine_kwargs.append(dict(kwargs))
        return _RecordingEngine(self.statements, self.parameters, self.boundaries)


def _pin_configured_env(monkeypatch, environment: EnvironmentEnum) -> None:
    monkeypatch.setattr(
        starter_module, "get_config", lambda: _ConfiguredEnvironment(environment)
    )


def _run(starter: DatabaseStarter) -> None:
    asyncio.run(starter.recreate_test_database())


def _lock_parameters(factory: _RecordingEngineFactory) -> list[dict]:
    """Bind parameters of every recorded ``pg_advisory_lock`` statement."""
    found: list[dict] = []
    for statement, params in zip(factory.statements, factory.parameters, strict=True):
        if _LOCK_MARKER in statement and _UNLOCK_MARKER not in statement:
            found.append(params)
    return found


class TestRecreationLockPlacement:
    """The acquisition sits after both guards and before the destructive drop."""

    def test_lock_acquired_after_guards_and_before_terminate(self, monkeypatch):
        """On the positive path the lock precedes pg_terminate_backend.

        The guards are not statements, so "after both guards" is proven by the
        refusal tests below recording no lock at all; here the ordering against
        the destructive statement is the placement the fix depends on.
        """
        factory = _RecordingEngineFactory()
        monkeypatch.setattr(starter_module, "create_async_engine", factory)
        monkeypatch.setattr(DatabaseStarter, "_apply_migrations", _noop_apply_migrations)
        _pin_configured_env(monkeypatch, EnvironmentEnum.TEST)

        starter = DatabaseStarter(
            DatabaseStarterConfig(
                test_database_url=_TEST_DB_URL,
                test_admin_database_url=_TEST_ADMIN_URL,
                recreate_test_db=True,
            )
        )
        _run(starter)

        lock_idx = next(
            i for i, s in enumerate(factory.statements) if _LOCK_MARKER in s
        )
        terminate_idx = next(
            i for i, s in enumerate(factory.statements) if _TERMINATE_MARKER in s
        )
        drop_idx = next(
            i for i, s in enumerate(factory.statements) if "DROP DATABASE" in s
        )

        assert lock_idx < terminate_idx < drop_idx, factory.statements

    def test_lock_released_after_the_destructive_work(self, monkeypatch):
        """The session lock is released in the same path that took it."""
        factory = _RecordingEngineFactory()
        monkeypatch.setattr(starter_module, "create_async_engine", factory)
        monkeypatch.setattr(DatabaseStarter, "_apply_migrations", _noop_apply_migrations)
        _pin_configured_env(monkeypatch, EnvironmentEnum.TEST)

        starter = DatabaseStarter(
            DatabaseStarterConfig(
                test_database_url=_TEST_DB_URL,
                test_admin_database_url=_TEST_ADMIN_URL,
                recreate_test_db=True,
            )
        )
        _run(starter)

        lock_idx = next(
            i for i, s in enumerate(factory.statements) if _LOCK_MARKER in s
        )
        unlock_idx = next(
            i for i, s in enumerate(factory.statements) if _UNLOCK_MARKER in s
        )
        drop_idx = next(
            i for i, s in enumerate(factory.statements) if "DROP DATABASE" in s
        )

        assert lock_idx < drop_idx < unlock_idx, factory.statements

    def test_environment_guard_refuses_before_any_lock(self, monkeypatch):
        """A production tier refuses with no engine, hence no lock."""
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

        with pytest.raises(UnsafeTestDatabaseRecreationError, match="not 'test'"):
            _run(starter)

        assert factory.calls == []
        assert factory.statements == []

    def test_name_guard_refuses_before_any_lock(self, monkeypatch):
        """A test tier pointed at a non-test name refuses before any statement."""
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

        with pytest.raises(UnsafeTestDatabaseRecreationError, match="does not match"):
            _run(starter)

        assert factory.calls == []
        assert factory.statements == []


class TestRecreationLockKeyIsPerName:
    """Differently named test databases are independent and must not serialise."""

    def test_different_names_take_different_keys(self):
        """The two xdist-style names take distinct keys, so they run in parallel."""
        assert derive_lock_key("bidb_test_gw0") != derive_lock_key(
            "bidb_test_gw1"
        )

    def test_same_name_takes_the_same_key(self):
        """The key is a stable digest, identical in every process."""
        assert derive_lock_key("bidb_test") == derive_lock_key(
            "bidb_test"
        )

    def test_key_is_in_its_own_namespace(self):
        """The key is prefixed with this module's namespace, not a shared one."""
        assert TEST_DB_RECREATE_LOCK_NAMESPACE == "mkobi:test-database-recreate"

    @pytest.mark.parametrize("db_name", ["bidb_test_gw0", "bidb_test_gw1"])
    def test_each_run_acquires_the_key_for_its_own_name(self, monkeypatch, db_name):
        """A run records exactly one lock, bound to its own database's key."""
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
        _run(starter)

        locks = _lock_parameters(factory)
        assert len(locks) == 1, factory.statements
        assert locks[0]["lock_key"] == derive_lock_key(db_name)
