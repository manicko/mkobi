"""Tests for database starter module.

Tests ensure_admin_user placeholder password rejection.
"""

import inspect
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
    assert_safe_test_database_name,
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


class _FakeResult:
    """Minimal statement result carrying a rowcount and optional row."""

    def __init__(self, rowcount: int = 0, row=None) -> None:
        self.rowcount = rowcount
        self._row = row

    def fetchone(self):
        return self._row


class _FakeBegin:
    """Async context manager standing in for ``db.begin()``."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeAdminSession:
    """Fake session for ensure_admin_user.

    ``insert_rowcount`` and ``occupant`` drive the branch under test. The
    INSERT returns ``insert_rowcount``; when the insert did not create a row,
    the SELECT returns ``occupant`` as an ``(id, role)`` tuple.
    """

    def __init__(self, insert_rowcount: int, occupant=None) -> None:
        self._insert_rowcount = insert_rowcount
        self._occupant = occupant

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    def begin(self) -> _FakeBegin:
        return _FakeBegin()

    async def execute(self, statement, params=None):
        rendered = str(statement)
        if "INSERT INTO users" in rendered:
            return _FakeResult(rowcount=self._insert_rowcount)
        if "SELECT id, role FROM users" in rendered:
            return _FakeResult(rowcount=0, row=self._occupant)
        return _FakeResult(rowcount=0)


def _pin_admin_session(monkeypatch, session: _FakeAdminSession) -> None:
    """Pin the session factory to a sentinel returning ``session``."""

    async def _sessionlocal():
        return lambda: session

    monkeypatch.setattr(
        "mkobi.db.session.get_async_sessionlocal", _sessionlocal
    )


def _capture_starter_logs():
    """Attach a collector handler to the starter logger.

    The application's logging setup runs with disable_existing_loggers=True and
    propagate=False, so caplog is not reliable here. Returns the collector list
    and a restore callable.
    """
    import logging

    starter_logger = logging.getLogger("mkobi.db.starter")
    captured: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    collector = _Collector(level=logging.DEBUG)
    original_level = starter_logger.level
    was_disabled = starter_logger.disabled
    starter_logger.addHandler(collector)
    starter_logger.setLevel(logging.DEBUG)
    starter_logger.disabled = False

    def restore() -> None:
        starter_logger.removeHandler(collector)
        starter_logger.setLevel(original_level)
        starter_logger.disabled = was_disabled

    return captured, restore


class TestEnsureAdminUserConflictOutcome:
    """Tests for the D-04-L ensure_admin_user conflict outcomes."""

    def test_created_row_logs_created_message(self, monkeypatch):
        """A fresh address takes the created branch and logs creation."""
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongT3stP@ss!")
        monkeypatch.setenv("ADMIN_USERNAME", "fresh_admin@example.com")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        _pin_admin_session(monkeypatch, _FakeAdminSession(insert_rowcount=1))
        captured, restore = _capture_starter_logs()

        starter = DatabaseStarter(
            DatabaseStarterConfig(env=EnvironmentEnum.DEVELOPMENT)
        )

        import asyncio

        try:
            asyncio.run(starter.ensure_admin_user())
        finally:
            restore()

        messages = [r.getMessage() for r in captured]
        assert any(
            m == "Admin user created: fresh_admin@example.com" for m in messages
        ), messages
        # The already-exists message must not be emitted on the created path.
        assert not any(
            "already existed" in m for m in messages
        ), messages

    def test_existing_admin_row_is_reported_not_raised(self, monkeypatch):
        """An existing admin row is reported by id and role and not raised."""
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongT3stP@ss!")
        monkeypatch.setenv("ADMIN_USERNAME", "existing_admin@example.com")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        occupant = ("00000000-0000-0000-0000-0000000000aa", "admin")
        _pin_admin_session(
            monkeypatch,
            _FakeAdminSession(insert_rowcount=0, occupant=occupant),
        )
        captured, restore = _capture_starter_logs()

        # Even at the production tier an existing admin row is not refused.
        starter = DatabaseStarter(
            DatabaseStarterConfig(env=EnvironmentEnum.PRODUCTION)
        )

        import asyncio

        try:
            asyncio.run(starter.ensure_admin_user())
        finally:
            restore()

        messages = [r.getMessage() for r in captured]
        already = [m for m in messages if "already existed" in m]
        assert already, messages
        assert occupant[0] in already[0], already[0]
        assert occupant[1] in already[0], already[0]
        assert not any("created:" in m for m in messages), messages

    def test_existing_non_admin_warns_and_proceeds_in_development(
        self, monkeypatch
    ):
        """A non-admin occupant warns, names its id and role, and proceeds."""
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongT3stP@ss!")
        monkeypatch.setenv("ADMIN_USERNAME", "occupied_admin@example.com")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        occupant = ("00000000-0000-0000-0000-0000000000bb", "viewer")
        _pin_admin_session(
            monkeypatch,
            _FakeAdminSession(insert_rowcount=0, occupant=occupant),
        )
        captured, restore = _capture_starter_logs()

        starter = DatabaseStarter(
            DatabaseStarterConfig(env=EnvironmentEnum.DEVELOPMENT)
        )

        import asyncio

        try:
            # Development only warns; no exception is raised.
            asyncio.run(starter.ensure_admin_user())
        finally:
            restore()

        warnings = [
            r.getMessage() for r in captured if r.levelno >= 30
        ]
        occupied = [m for m in warnings if "non-admin user" in m]
        assert occupied, warnings
        assert occupant[0] in occupied[0], occupied[0]
        assert occupant[1] in occupied[0], occupied[0]

    def test_existing_non_admin_raises_in_production(self, monkeypatch):
        """A non-admin occupant raises ValueError in production, naming role."""
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongT3stP@ss!")
        monkeypatch.setenv("ADMIN_USERNAME", "occupied_prod@example.com")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        occupant = ("00000000-0000-0000-0000-0000000000cc", "viewer")
        _pin_admin_session(
            monkeypatch,
            _FakeAdminSession(insert_rowcount=0, occupant=occupant),
        )

        starter = DatabaseStarter(
            DatabaseStarterConfig(env=EnvironmentEnum.PRODUCTION)
        )

        import asyncio

        with pytest.raises(ValueError, match="non-admin user") as exc_info:
            asyncio.run(starter.ensure_admin_user())

        assert occupant[1] in str(exc_info.value)
        assert occupant[0] in str(exc_info.value)


class _RecordingTransaction:
    """Fake transaction context manager recording begin()/commit-ish entry.

    Boundaries are appended to the shared statement log with a marker prefix so
    their position relative to statements is preserved; they are also collected
    separately for a cheap count assertion.
    """

    _BEGIN_MARKER = "\x00BEGIN"
    _END_MARKER = "\x00END"

    def __init__(
        self,
        recorder: list[str],
        boundaries: list[tuple[str, str]],
    ) -> None:
        self._recorder = recorder
        self._boundaries = boundaries

    async def __aenter__(self) -> "_RecordingTransaction":
        self._recorder.append(self._BEGIN_MARKER)
        self._boundaries.append(("begin", ""))
        return self

    async def __aexit__(self, *exc_info) -> bool:
        self._recorder.append(self._END_MARKER)
        self._boundaries.append(("end", ""))
        return False


class _RecordingConnection:
    """Fake connection that records the statements issued against it.

    It also records explicit ``begin()`` transaction boundaries, so a test can
    distinguish grants issued inside one transaction from grants issued on an
    autocommit connection.
    """

    def __init__(self, recorder: list[str], boundaries: list[tuple[str, str]]) -> None:
        self._recorder = recorder
        self._boundaries = boundaries
        from sqlalchemy.dialects import postgresql

        self.dialect = postgresql.dialect()

    def begin(self) -> _RecordingTransaction:
        return _RecordingTransaction(self._recorder, self._boundaries)

    async def execute(self, statement, params=None):
        try:
            rendered = str(statement.compile(dialect=self.dialect))
        except Exception:
            rendered = repr(statement)
        self._recorder.append(rendered)
        return None


class _RecordingConnectContext:
    """Async context manager yielding a recording connection."""

    def __init__(
        self,
        recorder: list[str],
        boundaries: list[tuple[str, str]],
    ) -> None:
        self._recorder = recorder
        self._boundaries = boundaries

    async def __aenter__(self) -> _RecordingConnection:
        return _RecordingConnection(self._recorder, self._boundaries)

    async def __aexit__(self, *exc_info) -> bool:
        return False


class _RecordingEngine:
    """Fake async engine whose connections record every statement."""

    def __init__(
        self,
        recorder: list[str],
        boundaries: list[tuple[str, str]],
    ) -> None:
        self._recorder = recorder
        self._boundaries = boundaries

    def connect(self) -> _RecordingConnectContext:
        return _RecordingConnectContext(self._recorder, self._boundaries)

    async def dispose(self) -> None:
        return None


class _RecordingEngineFactory:
    """Callable standing in for create_async_engine, recording every call."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.statements: list[str] = []
        # Explicit transaction boundaries opened on any recording connection,
        # in order, as (event, "") pairs where event is "begin" or "end".
        self.boundaries: list[tuple[str, str]] = []
        self.engine_kwargs: list[dict] = []

    def __call__(self, url, **kwargs) -> _RecordingEngine:
        self.calls.append(str(url))
        self.engine_kwargs.append(dict(kwargs))
        return _RecordingEngine(self.statements, self.boundaries)


async def _noop_apply_migrations(self, db_url: str) -> None:
    """Stand-in for migration application so no Alembic run is required."""
    return None


# Credentials and host here are inert. Every destructive test in this module
# replaces the starter module's `create_async_engine` with a recording fake
# (`_RecordingEngineFactory`), so no connection is ever opened and these values
# are never used for anything: the config object simply requires a value. The
# password `pw` in particular is a placeholder and is never authenticated
# against, so it must not be read as a statement about the real test credentials.
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


class TestSafeTestDatabaseNamePredicate:
    """Direct tests for the pure name predicate, with no URL or engine.

    ``assert_safe_test_database_name`` is a plain function over a ``str``, so
    the naming rules can be pinned without constructing a URL, an engine or an
    event loop. The end-to-end parametrized test in
    ``TestRecreateTestDatabaseGuards`` still proves the guards are not
    over-tight (the positive path); these tests pin the rejection rules.
    """

    @pytest.mark.parametrize(
        "db_name",
        [
            "bidb_test",
            # The per-run shape tests/conftest.py actually generates:
            # 'bidb_test_' + an 8-hex-char run token.
            "bidb_test_a1b2c3d4",
            # An xdist worker token folded into the same single segment.
            "bidb_test_a1b2c3d4gw0",
        ],
    )
    def test_accepts_convention_names(self, db_name):
        """Convention names return normally."""
        assert_safe_test_database_name(db_name)

    @pytest.mark.parametrize(
        "db_name",
        [
            # The real production database name.
            "bidb",
            # A trailing newline: '$' would accept this, '\Z' must not.
            "bidb_test\n",
            # Two suffix segments are refused (the guard allows at most one).
            "bidb_test_a_b",
            # An empty suffix is refused.
            "bidb_test_",
            # Base name is case-sensitive.
            "BIDB_TEST",
            "Bidb_Test",
            # Substring non-matches must not be treated as the base name.
            "bidb_testing",
            "bidb_testbackup",
            # SQL-injection-shaped strings must be refused.
            "bidb_test; DROP DATABASE bidb",
            "bidb_test--",
            # Absent name.
            None,
            "",
        ],
    )
    def test_rejects_non_convention_names(self, db_name):
        """Non-convention names raise the refusal error."""
        with pytest.raises(UnsafeTestDatabaseRecreationError, match="does not match"):
            assert_safe_test_database_name(db_name)

    def test_suffix_case_is_currently_accepted(self):
        """Suffix case is accepted: pinned as the observed behaviour.

        PostgreSQL folds unquoted identifiers to lowercase, and the suite only
        ever generates a lowercase token, so an uppercase suffix reaches a
        lowercase database and is harmless here. This pins the current
        behaviour; see the report for whether it should instead be refused.
        """
        assert_safe_test_database_name("bidb_test_GW0")

    def test_secondary_guard_is_a_superset_of_the_primary(self):
        """Every name the primary accepts also satisfies the secondary guard.

        The secondary injection guard ``^[a-zA-Z0-9_]+\\Z`` is unreachable
        today because the primary guard's language is a strict subset of it.
        It is deliberately kept as defense in depth, so this test pins that
        property: an exhaustive enumeration over a fixed alphabet that includes
        every character the primary admits, plus a few it rejects, must never
        produce a string the primary accepts and the secondary rejects. A future
        change that makes the secondary guard live (for example, letting the
        primary admit a hyphen) fails here loudly.
        """
        import itertools
        import re

        primary = starter_module.TEST_DATABASE_NAME_PATTERN
        secondary = re.compile(r"^[a-zA-Z0-9_]+\Z")

        # The alphabet spans the accepted set plus characters designed to be
        # refused; an accepted-and-refused-by-secondary pair can only arise from
        # a character the secondary rejects.
        alphabet = "abcZ09_.-\n ;"
        counterexamples = []
        for length in range(1, 5):
            for chars in itertools.product(alphabet, repeat=length):
                candidate = "bidb_test" + "".join(chars)
                if primary.match(candidate) and not secondary.match(candidate):
                    counterexamples.append(candidate)
        assert counterexamples == [], counterexamples


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

    def test_grants_are_issued_inside_one_transaction(self, monkeypatch):
        """The five grants are wrapped in one explicit transaction.

        The connection stays AUTOCOMMIT (the DROP/CREATE before it cannot run
        inside a transaction), so the only BEGIN/COMMIT around the grants is
        the explicit ``conn.begin()`` block. Asserting both the boundary and
        the grants' positions inside it distinguishes this from a regression
        that issues the grants on the autocommit connection.
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

        # The grant engine is the second engine created, and it is the
        # AUTOCOMMIT engine the grants run on.
        assert len(factory.engine_kwargs) >= 2
        assert factory.engine_kwargs[-1].get("isolation_level") == "AUTOCOMMIT"

        # Exactly one explicit transaction is opened, and the five grants are
        # all issued between its begin and end.
        assert factory.boundaries == [("begin", ""), ("end", "")], factory.boundaries

        begin_idx = factory.statements.index(_RecordingTransaction._BEGIN_MARKER)
        end_idx = factory.statements.index(_RecordingTransaction._END_MARKER)
        assert begin_idx < end_idx

        # The five privilege statements this path owns are exactly the ones
        # issued inside the transaction. GRANT CONNECT ON DATABASE is issued
        # earlier on the autocommit admin engine and is deliberately outside
        # this boundary, so it must not be counted here.
        grants_inside = [
            s
            for s in factory.statements[begin_idx + 1 : end_idx]
            if "TO mkobi_app" in s
        ]
        assert len(grants_inside) == 5, grants_inside

        # No mkobi_app grant on the schema engine sits outside the boundary.
        outside = [
            s
            for s in factory.statements[:begin_idx] + factory.statements[end_idx + 1 :]
            if "SCHEMA public" in s and "TO mkobi_app" in s
        ]
        assert outside == [], outside

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

    @pytest.mark.parametrize("db_name", ["bidb_test", "bidb_test_gw0", "bidb_test_w1", "bidb_test_a1b2c3d4"])
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


class TestStarterDoesNotSweepTempFilesAtBoot:
    """FAB-4 / D-06-C(a): the temp-file sweep left the boot path.

    The sweep now rides the lease-guarded periodic loop
    (``start_stale_processing_cleanup_task``), so ``DatabaseStarter.startup``
    must no longer call it. Pinning the *source* is deliberately chosen over a
    behavioural call assertion: ``startup`` needs a live database to reach the
    old call site, whereas "the symbol is absent" is exactly the placement
    property under test and holds regardless of environment.
    """

    def test_startup_source_does_not_reference_the_temp_file_sweep(self):
        """The sweep symbol is gone from the starter module entirely."""
        source = inspect.getsource(starter_module)
        assert "cleanup_stale_temp_files" not in source

    def test_startup_does_not_import_the_temp_file_sweep(self):
        """No import of the swept function remains in the starter's imports."""
        assert not hasattr(starter_module, "cleanup_stale_temp_files")
