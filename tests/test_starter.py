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


class TestEnsureAdminUserPlaceholderCheck:
    """Tests for placeholder password rejection in ensure_admin_user()."""

    @pytest.mark.parametrize("weak_password", [
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
    ])
    def test_ensure_admin_user_rejects_placeholder_password(
        self, monkeypatch, weak_password
    ):
        """Verify ensure_admin_user raises ValueError for known placeholder passwords."""
        monkeypatch.setenv("ADMIN_PASSWORD", weak_password)
        monkeypatch.setenv("ADMIN_USERNAME", "test_admin")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        # Need to re-import to get fresh config with the new password
        # The check happens inside ensure_admin_user, not at Settings init
        from mkobi.db.starter import DatabaseStarter

        starter = DatabaseStarter()

        # This should raise ValueError when called
        with pytest.raises(ValueError, match="known placeholder value"):
            import asyncio
            asyncio.run(starter.ensure_admin_user())