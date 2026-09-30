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

from mkobi.db.starter import DatabaseStarter, DatabaseStarterConfig  # noqa: E402
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
