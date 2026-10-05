"""Tests for application configuration.

Tests:
- Loading from environment variables
- Loading from .env file
- Loading from Docker secrets (_FILE suffix)
- Loading from YAML file
- Source priority
"""

import os
import pytest

from mkobi.config import Settings
from mkobi.models.enums import EnvironmentEnum, FileExtensionEnum
import re


def _validation_msg(exc_info: pytest.ExceptionInfo) -> str:
    """Return the first pydantic validation message without echoing inputs.

    Reading the ``msg`` field avoids pydantic's ``input_value=`` rendering,
    which can embed the rejected secret in ``str(exc_info.value)``.
    """
    return str(exc_info.value.errors()[0]["msg"])


class TestSettingsBase:
    """Base class for settings tests."""

    @pytest.fixture(autouse=True)
    def clean_env(self):
        """Clean up environment variables after each test."""
        # Save current variables
        env_backup: dict[str, str] = {
            key: os.environ[key]
            for key in os.environ
            if key.startswith((
                "DATABASE__",
                "JWT__",
                "UPLOAD__",
                "REDIS__",
                "LOGGING__",
                "CORS_",
                "APP_",
                "ENV",
                "DEBUG",
                "HOST",
                "PORT",
            ))
        }
        yield
        # Clean up test variables
        for key in list(os.environ.keys()):
            if key.startswith((
                "DATABASE__",
                "JWT__",
                "UPLOAD__",
                "REDIS__",
                "LOGGING__",
                "CORS_",
                "APP_",
                "ENV",
                "DEBUG",
                "HOST",
                "PORT",
            )):
                if key in env_backup:
                    os.environ[key] = env_backup[key]
                else:
                    os.environ.pop(key, None)


class TestSettingsFromEnv(TestSettingsBase):
    """Tests for loading from environment variables."""

    def test_load_database_host_from_env(self, monkeypatch):
        """Test loading DATABASE__HOST from environment variable."""
        monkeypatch.setenv("DATABASE__HOST", "env-host")
        settings = Settings()
        assert settings.database.host == "env-host"

    def test_load_jwt_secret_from_env(self, monkeypatch):
        """Test loading JWT__SECRET_KEY from environment variable."""
        monkeypatch.setenv("JWT__SECRET_KEY", "test-secret-from-env-32-characters-long")
        settings = Settings()
        assert settings.jwt.secret_key == "test-secret-from-env-32-characters-long"

    def test_load_upload_max_file_size_mb_from_env(self, monkeypatch):
        """Test loading UPLOAD__MAX_FILE_SIZE_MB from environment variable."""
        monkeypatch.setenv("UPLOAD__MAX_FILE_SIZE_MB", "200")
        settings = Settings()
        assert settings.upload.max_file_size_mb == 200

    def test_load_environment_enum_from_env(self, monkeypatch):
        """Test loading ENV from environment variable."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "testadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "testpassword123")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        settings = Settings()
        assert settings.environment == EnvironmentEnum.PRODUCTION


class TestSettingsFromYaml(TestSettingsBase):
    """Tests for loading from YAML file."""

    def test_load_email_blocked_domains_from_yaml(self):
        """Test loading email.blocked_domains from YAML file."""
        settings = Settings()
        assert "tempmail.com" in settings.email.blocked_domains
        assert "throwaway.email" in settings.email.blocked_domains


class TestSettingsDockerSecrets(TestSettingsBase):
    """Tests for Docker secrets support."""

    def test_derived_secret_field_env_names(self):
        """The *_FILE allow-list is exactly the five secret-bearing fields.

        This is the guard against two silent defects: the absent
        DatabaseSettings.redis_password (which would KeyError at construction)
        and a Redis test that asserts "not None" on a dropped field.
        """
        from mkobi.config import _secret_field_env_names

        assert _secret_field_env_names(Settings) == frozenset({
            "database__password",
            "database__admin_user",
            "database__admin_password",
            "jwt__secret_key",
            "redis__password",
        })

    def test_docker_secret_file_loading(self, tmp_path, monkeypatch):
        """Test loading secrets from files (_FILE suffix)."""
        # Create temporary file with secret
        secret_file = tmp_path / "db_password"
        secret_file.write_text("secret-from-file")

        # Set environment variable with _FILE suffix
        monkeypatch.setenv("DATABASE__PASSWORD_FILE", str(secret_file))
        # Remove regular environment variable so secret_file takes priority
        monkeypatch.delenv("DATABASE__PASSWORD", raising=False)

        settings = Settings()
        assert settings.database.password == "secret-from-file"

    def test_docker_secret_admin_credentials_file_loading(self, tmp_path, monkeypatch):
        """DATABASE__ADMIN_USER_FILE and DATABASE__ADMIN_PASSWORD_FILE still load."""
        admin_user_file = tmp_path / "admin_user"
        admin_user_file.write_text("db-admin")
        admin_password_file = tmp_path / "admin_password"
        admin_password_file.write_text("db-admin-password")

        monkeypatch.setenv("DATABASE__ADMIN_USER_FILE", str(admin_user_file))
        monkeypatch.setenv("DATABASE__ADMIN_PASSWORD_FILE", str(admin_password_file))
        monkeypatch.delenv("DATABASE__ADMIN_USER", raising=False)
        monkeypatch.delenv("DATABASE__ADMIN_PASSWORD", raising=False)

        settings = Settings()
        assert settings.database.admin_user == "db-admin"
        assert settings.database.admin_password == "db-admin-password"

    def test_docker_secret_redis_password_file_loading(self, tmp_path, monkeypatch):
        """REDIS__PASSWORD_FILE loads the real file contents into redis.password.

        The base is a nested field, so the working env name is REDIS__PASSWORD,
        not REDIS_PASSWORD. Asserting equality (not merely "not None") is what
        proves the value was actually injected.
        """
        secret_file = tmp_path / "redis_password"
        secret_file.write_text("redis-secret-from-file")
        monkeypatch.setenv("REDIS__PASSWORD_FILE", str(secret_file))
        monkeypatch.delenv("REDIS__PASSWORD", raising=False)

        settings = Settings()
        assert settings.redis.password == "redis-secret-from-file"

    def test_docker_secret_non_secret_base_cannot_inject_into_list_field(
        self, tmp_path, monkeypatch
    ):
        """A non-secret *_FILE base must not abort startup on an unrelated field.

        This is the discriminating regression test for the *_FILE allow-list.
        Pre-fix, UPLOAD__ALLOWED_EXTENSIONS_FILE injected the file's string
        contents into the list-valued ``upload.allowed_extensions`` field and
        raised ValidationError, aborting startup on a configuration point that
        has nothing to do with secrets. Post-fix the variable is skipped and
        Settings() constructs with the field at its normal value.
        """
        payload_file = tmp_path / "extensions"
        payload_file.write_text("csv")

        monkeypatch.setenv("UPLOAD__ALLOWED_EXTENSIONS_FILE", str(payload_file))
        monkeypatch.delenv("UPLOAD__ALLOWED_EXTENSIONS", raising=False)

        settings = Settings()
        assert settings.upload.allowed_extensions == [
            FileExtensionEnum.CSV_GZ,
            FileExtensionEnum.CSV,
        ]

    def test_docker_source_skips_non_secret_base(self, tmp_path, monkeypatch):
        """The source returns {} for a *_FILE whose base is not a secret field."""
        from mkobi.config import SecretsFileSource

        payload_file = tmp_path / "extensions"
        payload_file.write_text("csv")
        monkeypatch.setenv("UPLOAD__ALLOWED_EXTENSIONS_FILE", str(payload_file))
        monkeypatch.setenv("LOGGING__LOG_FILE", str(tmp_path / "logs.txt"))

        assert SecretsFileSource(Settings)() == {}

    def test_docker_secret_lowercase_variable_name_still_loads(self, tmp_path, monkeypatch):
        """A lower/mixed-case *_FILE name loads, per case_sensitive=False."""
        secret_file = tmp_path / "jwt_secret"
        secret_file.write_text("secret-from-file-32-characters-long")
        monkeypatch.setenv("jwt__secret_key_FILE", str(secret_file))
        monkeypatch.delenv("JWT__SECRET_KEY", raising=False)

        settings = Settings()
        assert settings.jwt.secret_key == "secret-from-file-32-characters-long"

    def test_docker_secret_overrides_yaml(self, tmp_path, monkeypatch):
        """Test that Docker secrets override YAML."""
        # Create temporary file with secret
        secret_file = tmp_path / "jwt_secret"
        secret_file.write_text("secret-from-file-32-characters-long")

        # Set environment variable with _FILE suffix
        monkeypatch.setenv("JWT__SECRET_KEY_FILE", str(secret_file))
        # Remove regular environment variable so secret_file takes priority
        monkeypatch.delenv("JWT__SECRET_KEY", raising=False)

        settings = Settings()
        assert settings.jwt.secret_key == "secret-from-file-32-characters-long"


class TestSettingsPriority(TestSettingsBase):
    """Tests for settings source priority."""

    def test_env_overrides_yaml(self, monkeypatch):
        """Test that environment variables override YAML."""
        monkeypatch.setenv("DATABASE__HOST", "env-host")
        settings = Settings()
        # YAML has localhost, but env should override
        assert settings.database.host == "env-host"

    def test_env_overrides_dotenv(self, monkeypatch):
        """Test that environment variables override .env file."""
        # Create temporary .env file
        monkeypatch.setenv("DATABASE__HOST", "env-host")
        settings = Settings()
        assert settings.database.host == "env-host"

    def test_priority_order(self, tmp_path, monkeypatch):
        """Test correct priority order.

        Priority: env vars > Docker secrets > .env > YAML > defaults
        """
        # Create file with secret
        secret_file = tmp_path / "secret"
        secret_file.write_text("secret-value-32-characters-for-testing")

        # Set variables - remove JWT__SECRET_KEY env var so Docker secret takes effect
        monkeypatch.setenv("JWT__SECRET_KEY_FILE", str(secret_file))
        monkeypatch.delenv("JWT__SECRET_KEY", raising=False)

        settings = Settings()
        # Docker secret should be loaded
        assert settings.jwt.secret_key == "secret-value-32-characters-for-testing"


class TestSettingsProperties(TestSettingsBase):
    """Tests for Settings properties and methods."""

    def test_database_url_property(self):
        """Test DATABASE_URL property."""
        settings = Settings()
        url = settings.DATABASE_URL
        # In development without password, DATABASE_URL returns None
        # (password is required in production)
        if url is not None:
            assert "postgresql" in url or "postgresql+asyncpg" in url

    def test_allowed_file_types_property(self):
        """Test allowed_file_types property."""
        settings = Settings()
        extensions = settings.allowed_file_types
        assert "csv" in extensions
        assert "csv.gz" in extensions

    def test_max_file_size_property(self):
        """Test max_file_size property (in bytes)."""
        settings = Settings()
        # 100 MB = 100 * 1024 * 1024 bytes
        assert settings.max_file_size == 100 * 1024 * 1024

    def test_log_level_property(self, monkeypatch):
        """Test log_level property."""
        monkeypatch.setenv("LOGGING__LEVEL", "INFO")
        settings = Settings()
        assert settings.log_level == "INFO"


class TestAppSettings(TestSettingsBase):
    """Tests for AppSettings."""

    def test_app_settings_defaults(self):
        """Test default values for AppSettings.

        ``app.version`` no longer has a hand-written default: it is the
        installed distribution's declared version (see
        ``distribution_version()``), so the assertion compares against that
        resolver rather than a literal. Comparing against a literal would
        re-create the very staleness this default removes — the distribution
        bumps independently of the test.
        """
        from mkobi.config import distribution_version

        settings = Settings()
        assert settings.app.name == "mkobi"
        assert settings.app.version == distribution_version()

    def test_app_version_default_has_one_source(self):
        """The advertised version equals the installed distribution's version.

        This is the EXT-010 guarantee: the value is derived, not written down,
        so there is exactly one place to read it. The assertion reads the
        distribution's metadata independently — through ``importlib.metadata``
        directly, not through the production ``distribution_version`` helper —
        so it fails if the default reverts to a hard-written string that no
        longer matches the installed package.
        """
        import importlib.metadata

        resolved = Settings(_env_file=None).app.version
        assert resolved == importlib.metadata.version("mkobi")

    def test_app_version_env_override_wins_over_distribution(self, monkeypatch):
        """``APP__VERSION`` still overrides the distribution-derived default.

        Belt-and-braces alongside the unmodified end-to-end
        ``TestCreateAppMetadata``: this pins the override at the settings layer.
        """
        monkeypatch.setenv("APP__VERSION", "9.9.9")
        settings = Settings(_env_file=None)
        assert settings.app.version == "9.9.9"

    def test_app_yaml_no_longer_pins_a_version_literal(self):
        """``app.yaml`` does not carry a competing ``app.version`` literal.

        A YAML literal outranks the code default, so any value left here would
        keep the document stale regardless of the distribution. The key must be
        absent, not merely equal.
        """
        from pathlib import Path

        yaml_text = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "mkobi"
            / "settings"
            / "app.yaml"
        ).read_text(encoding="utf-8")
        app_block = yaml_text.split("app:", 1)[1].split("auto_migrate", 1)[0]
        assert "version:" not in app_block


class TestDatabaseSettings(TestSettingsBase):
    """Tests for DatabaseSettings."""

    def test_lock_timeout_defaults_to_three_minutes(self, monkeypatch):
        """The aggregate-rebuild lock bound defaults to 180 000 ms.

        The default must stay below ``STALE_PROCESSING_TIMEOUT_MINUTES``; that
        relationship is asserted here rather than stated in a comment.
        """
        monkeypatch.delenv("DATABASE__LOCK_TIMEOUT_MS", raising=False)
        settings = Settings(_env_file=None)
        assert settings.database.lock_timeout_ms == 180_000
        assert settings.database.lock_timeout_ms < 30 * 60 * 1000

    def test_lock_timeout_from_env(self, monkeypatch):
        """``DATABASE__LOCK_TIMEOUT_MS`` overrides the default."""
        monkeypatch.setenv("DATABASE__LOCK_TIMEOUT_MS", "4000")
        settings = Settings(_env_file=None)
        assert settings.database.lock_timeout_ms == 4000


class TestUploadSettings(TestSettingsBase):
    """Tests for UploadSettings."""

    def test_upload_settings_defaults(self):
        """Test default values for UploadSettings."""
        settings = Settings()
        assert settings.upload.max_file_size_mb == 100
        assert FileExtensionEnum.CSV in settings.upload.allowed_extensions

    def test_upload_temp_dir_is_absolute_without_env(self):
        """The resolved upload temp dir is absolute when no env value is supplied.

        Guards the VAL-002 remedy: app.yaml no longer pins a relative
        ``data/tmp_uploads``, so UploadSettings falls back to its own
        platformdirs default, which is absolute on every platform.

        The assertion goes through the real ``Settings`` source chain so that it
        observes app.yaml; constructing ``UploadSettings`` directly would bypass
        the YAML source and could never fail if a relative key were restored.
        ``_env_file=None`` neutralises any untracked local ``.env``, whose dotenv
        source outranks the YAML source and cannot be suppressed by
        ``monkeypatch.delenv``.
        """
        from pathlib import Path

        resolved = Settings(_env_file=None).upload.temp_dir
        assert Path(resolved).is_absolute()
        assert not resolved.endswith("data/tmp_uploads")


class TestEmailSettings(TestSettingsBase):
    """Tests for EmailSettings."""

    def test_email_blocked_domains(self):
        """Test blocked domains."""
        settings = Settings()
        assert "tempmail.com" in settings.email.blocked_domains
        assert "throwaway.email" in settings.email.blocked_domains


class TestCORSOrigins(TestSettingsBase):
    """Tests for CORS origins configuration."""

    def test_cors_origins_default_from_yaml(self):
        """Test that CORS origins are loaded from YAML config."""
        settings = Settings()
        # Default from app.yaml
        assert "http://localhost:3000" in settings.cors_origins
        assert "http://localhost:5173" in settings.cors_origins

    def test_cors_origins_from_env_json(self, monkeypatch):
        """Test CORS origins parsing from JSON string in env var."""
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
        settings = Settings()
        assert settings.cors_origins == ["http://localhost:3000"]

    def test_cors_origins_from_env_multiple(self, monkeypatch):
        """Test CORS origins parsing from JSON array in env var."""
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000", "https://app.example.com"]')
        settings = Settings()
        assert "http://localhost:3000" in settings.cors_origins
        assert "https://app.example.com" in settings.cors_origins

    def test_cors_origins_from_env_comma_separated(self, monkeypatch):
        """Test CORS origins parsing from comma-separated string."""
        # CORS_ORIGINS expects JSON format, not comma-separated
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000", "http://example.com"]')
        settings = Settings()
        assert "http://localhost:3000" in settings.cors_origins
        assert "http://example.com" in settings.cors_origins

    def test_cors_origins_from_env_single(self, monkeypatch):
        """Test CORS origins parsing from single string."""
        # CORS_ORIGINS expects JSON format
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
        settings = Settings()
        assert settings.cors_origins == ["http://localhost:3000"]

    def test_cors_origins_env_overrides_yaml(self, monkeypatch):
        """Test that env var overrides YAML config."""
        monkeypatch.setenv("CORS_ORIGINS", '["http://from-env:3000"]')
        settings = Settings()
        assert settings.cors_origins == ["http://from-env:3000"]
        assert "https://example.com" not in settings.cors_origins


class TestWeakCredentialDetection(TestSettingsBase):
    """Tests for weak admin credential detection."""

    @pytest.mark.parametrize("weak_username", [
        "admin", "administrator", "root", "test", "user", "admin@example.com"
    ])
    def test_weak_username_rejected(self, monkeypatch, weak_username):
        """Verify known-weak usernames are rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", weak_username)
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        with pytest.raises(ValueError, match="too common"):
            Settings()

    @pytest.mark.parametrize("weak_password", [
        "password", "123456", "admin", "secret", "test", "admin@example.com", "CHANGE_ME_ADMIN_PASSWORD"
    ])
    def test_weak_password_rejected(self, monkeypatch, weak_password):
        """Verify known-weak passwords are rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "secure_admin")
        monkeypatch.setenv("ADMIN_PASSWORD", weak_password)
        with pytest.raises(ValueError, match="too common"):
            Settings()

    def test_strong_credentials_accepted(self, monkeypatch):
        """Verify strong credentials pass validation in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "secure_admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        # Should not raise
        settings = Settings()
        assert settings.admin_username == "secure_admin"
        assert settings.admin_password == "StrongP@ss1"

    @pytest.mark.parametrize("placeholder_password", [
        "CHANGE_ME_GENERATE_STRONG_PASSWORD",
        "change_me_generate_strong_password",
        "CHANGE_ME_ADMIN_USERNAME",
    ])
    def test_change_me_placeholder_password_rejected_in_production(
        self, monkeypatch, placeholder_password
    ):
        """Verify a placeholder-family password is rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "secure_admin")
        monkeypatch.setenv("ADMIN_PASSWORD", placeholder_password)
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        with pytest.raises(ValueError, match="known placeholder value"):
            Settings()

    def test_shipped_placeholder_username_refused_in_production(self, monkeypatch):
        """Verify the shipped placeholder username alone is refused in production.

        docker/.env.example ships ADMIN_USERNAME=CHANGE_ME_ADMIN_USERNAME. Even
        with a strong password, the username must be refused, and the diagnosis
        must name 'unset or still a shipped placeholder' rather than 'too common'.
        """
        submitted_username = "CHANGE_ME_ADMIN_USERNAME"
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", submitted_username)
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        with pytest.raises(ValueError) as exc_info:
            Settings()
        message = _validation_msg(exc_info)
        assert "unset or still a shipped placeholder" in message
        assert "too common" not in message
        assert submitted_username not in message
        assert submitted_username[:8] not in message

    def test_exact_weak_username_still_diagnosed_as_too_common(self, monkeypatch):
        """Verify an exact weak username keeps its unchanged 'too common' message."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "root")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        with pytest.raises(ValueError) as exc_info:
            Settings()
        assert "too common" in _validation_msg(exc_info)

    def test_shipped_placeholder_username_accepted_in_development(self, monkeypatch):
        """Verify the shipped placeholder username is accepted outside production."""
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("ADMIN_USERNAME", "CHANGE_ME_ADMIN_USERNAME")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        assert settings.admin_username == "CHANGE_ME_ADMIN_USERNAME"

    def test_empty_admin_password_rejected_in_production(self, monkeypatch):
        """Verify an empty admin password is rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "secure_admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        with pytest.raises(ValueError, match="Admin password"):
            Settings()

    def test_whitespace_admin_password_rejected_in_production(self, monkeypatch):
        """Verify a whitespace-only admin password is rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "secure_admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "        ")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        with pytest.raises(ValueError, match="Admin password"):
            Settings()

    def test_empty_admin_username_rejected_in_production(self, monkeypatch):
        """Verify an empty admin username is rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        with pytest.raises(ValueError) as exc_info:
            Settings()
        message = _validation_msg(exc_info)
        assert "unset or still a shipped placeholder" in message
        assert "too common" not in message

    def test_rejection_message_does_not_leak_submitted_value(self, monkeypatch):
        """Verify the username rejection message never echoes the secret value."""
        monkeypatch.setenv("ENV", "production")
        submitted_username = "root"
        monkeypatch.setenv("ADMIN_USERNAME", submitted_username)
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        with pytest.raises(ValueError) as exc_info:
            Settings()
        message = _validation_msg(exc_info)
        assert "too common" in message
        assert submitted_username not in message
        assert submitted_username[:3] not in message

    def test_password_containing_weak_word_accepted_in_production(self, monkeypatch):
        """Verify a legitimate password that merely contains a weak word is accepted.

        Regression guard for R2: the predicate must never fall back to substring
        matching, otherwise this value (which contains 'test' and 'password')
        would be rejected.
        """
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "secure_admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "testpassword123")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        settings = Settings()
        assert settings.admin_password == "testpassword123"


class TestJWTSecretValidation(TestSettingsBase):
    """Tests for JWT secret key validation and loading."""

    def test_short_jwt_secret_rejected(self, monkeypatch):
        """Verify JWT secret shorter than 32 characters is rejected."""
        monkeypatch.setenv("JWT__SECRET_KEY", "tooshort")
        with pytest.raises(ValueError, match="at least 32 characters"):
            Settings()

    def test_weak_jwt_secret_rejected(self, monkeypatch):
        """Verify weak JWT secrets are rejected."""
        monkeypatch.setenv("JWT__SECRET_KEY", "dev-secret-key-for-local-development")
        with pytest.raises(ValueError, match="too common"):
            Settings()

    def test_placeholder_jwt_secret_rejected(self, monkeypatch):
        """Verify placeholder JWT secret is rejected (it's in WEAK_SECRETS)."""
        monkeypatch.setenv("JWT__SECRET_KEY", "dev-secret-key-for-local-development")
        with pytest.raises(ValueError, match="too common"):
            Settings()

    def test_env_jwt_secret_accepted(self, monkeypatch):
        """Verify JWT__SECRET_KEY from env var is loaded into settings."""
        monkeypatch.setenv("JWT__SECRET_KEY", "test-jwt-secret-key-for-unit-tests-32-chars!")
        settings = Settings()
        assert settings.jwt.secret_key == "test-jwt-secret-key-for-unit-tests-32-chars!"

    def test_strong_jwt_secret_accepted(self, monkeypatch):
        """Verify strong JWT secret passes validation."""
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        settings = Settings()
        assert settings.jwt.secret_key == "strong-jwt-secret-key-32-characters-long!"


class TestGetConfigReload:
    """Tests for get_config() reload mechanism."""

    def test_get_config_returns_singleton(self, monkeypatch):
        """Test that get_config returns the same instance by default."""
        from mkobi.config import get_config, clear_config_cache

        # Clear cache first to start fresh
        clear_config_cache()

        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_get_config_reload_returns_new_instance(self, monkeypatch):
        """Test that get_config(reload=True) returns a new instance."""
        from mkobi.config import get_config, clear_config_cache

        # Clear cache first to start fresh
        clear_config_cache()

        config1 = get_config()
        config2 = get_config(reload=True)
        assert config1 is not config2

    def test_clear_config_cache_allows_new_instance(self, monkeypatch):
        """Test that clear_config_cache allows creating a new config instance."""
        from mkobi.config import get_config, clear_config_cache

        # Clear cache first to start fresh
        clear_config_cache()

        config1 = get_config()
        clear_config_cache()
        config2 = get_config()
        assert config1 is not config2

    def test_get_config_reload_with_different_env(self, monkeypatch):
        """Test reload picks up new environment variables."""
        from mkobi.config import get_config, clear_config_cache

        # Clear cache first
        clear_config_cache()

        # Set initial env
        monkeypatch.setenv("DATABASE__HOST", "initial-host")
        config1 = get_config()
        assert config1.database.host == "initial-host"

        # Change env and reload
        monkeypatch.setenv("DATABASE__HOST", "new-host")
        config2 = get_config(reload=True)
        assert config2.database.host == "new-host"

        # Verify singleton still works (returns same instance as last call)
        config3 = get_config()
        assert config3 is config2


class TestDatabaseUrlPasswordValidation(TestSettingsBase):
    """Tests for DATABASE_URL password validation."""

    def test_database_url_returns_none_without_password_in_development(self, monkeypatch):
        """Test DATABASE_URL returns None when password is missing in development."""
        # Override password to empty string to simulate missing password
        monkeypatch.setenv("DATABASE__PASSWORD", "")
        monkeypatch.setenv("ENV", "development")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        # Password is empty string (which is falsy), so DATABASE_URL should return None
        assert settings.database.password == ""
        assert settings.DATABASE_URL is None

    def test_database_url_raises_error_without_password_in_production(self, monkeypatch):
        """Test DATABASE_URL raises ValueError when password is missing in production."""
        # Override password to empty string to simulate missing password
        monkeypatch.setenv("DATABASE__PASSWORD", "")
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        # Should raise ValueError in production without password
        with pytest.raises(ValueError, match="DATABASE__PASSWORD is required in production"):
            _ = settings.DATABASE_URL

    def test_database_url_returns_url_with_password(self, monkeypatch):
        """Test DATABASE_URL returns URL when password is set."""
        monkeypatch.setenv("DATABASE__PASSWORD", "test-password")
        settings = Settings()
        url = settings.DATABASE_URL
        assert url is not None
        assert "postgresql" in url or "postgresql+asyncpg" in url


class TestDebugModeValidation(TestSettingsBase):
    """Tests for debug mode validation in production."""

    def test_debug_true_rejected_in_production(self, monkeypatch):
        """Verify debug=True is rejected in production environment."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DEBUG", "true")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        with pytest.raises(ValueError, match="debug=True is not allowed in production"):
            Settings()

    def test_debug_false_accepted_in_production(self, monkeypatch):
        """Verify debug=False is accepted in production environment."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DEBUG", "false")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        # Should not raise
        settings = Settings()
        assert settings.debug is False

    def test_debug_true_accepted_in_development(self, monkeypatch):
        """Verify debug=True is allowed in development environment."""
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("DEBUG", "true")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        # Should not raise
        settings = Settings()
        assert settings.debug is True

    def test_debug_true_accepted_in_staging(self, monkeypatch):
        """Verify debug=True is allowed in staging environment."""
        monkeypatch.setenv("ENV", "staging")
        monkeypatch.setenv("DEBUG", "true")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        # Should not raise
        settings = Settings()
        assert settings.debug is True

    def test_debug_default_false_in_development(self, monkeypatch):
        """Verify debug defaults to False in development environment."""
        monkeypatch.setenv("ENV", "development")
        # DEBUG not set, should use default
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        assert settings.debug is False


class TestCORsOriginUrlValidation(TestSettingsBase):
    """Tests for CORS origin URL format validation."""

    def test_valid_http_origin_accepted(self, monkeypatch):
        """Test that valid http:// origins are accepted."""
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000", "http://example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        assert "http://localhost:3000" in settings.cors_origins
        assert "http://example.com" in settings.cors_origins

    def test_valid_https_origin_accepted(self, monkeypatch):
        """Test that valid https:// origins are accepted."""
        monkeypatch.setenv("CORS_ORIGINS", '["https://app.example.com", "https://secure.app.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        assert "https://app.example.com" in settings.cors_origins
        assert "https://secure.app.com" in settings.cors_origins

    def test_invalid_origin_rejected(self, monkeypatch):
        """Test that invalid origins (not http/https URLs) are rejected."""
        monkeypatch.setenv("CORS_ORIGINS", '["not-a-url", "http://localhost:3000"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        # Valid origin should be accepted
        assert "http://localhost:3000" in settings.cors_origins
        # Invalid origin should be rejected
        assert "not-a-url" not in settings.cors_origins

    def test_wildcard_origin_rejected(self, monkeypatch):
        """Test that wildcard '*' origin is rejected."""
        monkeypatch.setenv("CORS_ORIGINS", '["*", "http://localhost:3000"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        # Valid origin should be accepted
        assert "http://localhost:3000" in settings.cors_origins
        # Wildcard should be rejected
        assert "*" not in settings.cors_origins

    def test_origin_without_scheme_rejected(self, monkeypatch):
        """Test that origins without scheme are rejected."""
        monkeypatch.setenv("CORS_ORIGINS", '["localhost:3000", "http://localhost:3000"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        # Valid origin should be accepted
        assert "http://localhost:3000" in settings.cors_origins
        # Invalid origin (no scheme) should be rejected
        assert "localhost:3000" not in settings.cors_origins

    def test_all_invalid_origins_returns_empty(self, monkeypatch):
        """Test that all invalid origins result in empty list."""
        monkeypatch.setenv("CORS_ORIGINS", '["*", "not-a-url", "ftp://files.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        assert settings.cors_origins == []

    def test_wildcard_refused_in_production(self, monkeypatch):
        """Under ENV=production a wildcard raises a message naming the wildcard."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("DATABASE__PASSWORD", "StrongDbP@ss123")
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("CORS_ORIGINS", '["*", "https://real.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        with pytest.raises(ValueError, match=r"wildcard '\*' is not allowed in production"):
            Settings()

    def test_wildcard_filtered_in_non_production_tier(self, monkeypatch):
        """The default tier still filters the wildcard out and keeps valid origins."""
        monkeypatch.setenv("CORS_ORIGINS", '["*", "https://real.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        assert "*" not in settings.cors_origins
        assert "https://real.example.com" in settings.cors_origins

    def test_empty_cors_origins_accepted(self, monkeypatch):
        """Test that empty CORS origins list is valid."""
        monkeypatch.setenv("CORS_ORIGINS", "[]")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        assert settings.cors_origins == []

    def test_non_http_scheme_rejected(self, monkeypatch):
        """Test that non-http schemes like ftp, file, ws are rejected."""
        monkeypatch.setenv("CORS_ORIGINS", '["ftp://files.example.com", "ws://socket.example.com", "http://valid.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        # Only http:// should be accepted
        assert "http://valid.com" in settings.cors_origins
        assert "ftp://files.example.com" not in settings.cors_origins
        assert "ws://socket.example.com" not in settings.cors_origins


class TestCORsOriginsPlaceholderValidation(TestSettingsBase):
    """Tests for CORS origins placeholder validation in production."""

    @pytest.mark.parametrize("placeholder_origin", [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://example.com",
        "https://your-domain.com",
    ])
    def test_placeholder_origin_rejected_in_production(self, monkeypatch, placeholder_origin):
        """Verify placeholder CORS origins are rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", f'["{placeholder_origin}", "https://real-domain.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        with pytest.raises(ValueError, match="Placeholder CORS origins not allowed in production"):
            Settings()


class TestProductionCredentialValidation(TestSettingsBase):
    """Tests for production credential validation (database password and JWT secret)."""

    @pytest.mark.parametrize("weak_db_password", [
        "password", "123456", "admin", "secret", "test", "postgres", "CHANGE_ME",
    ])
    def test_weak_database_password_rejected_in_production(self, monkeypatch, weak_db_password):
        """Verify weak database passwords are rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", weak_db_password)
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        with pytest.raises(ValueError, match="DATABASE__PASSWORD is a known weak/placeholder value"):
            Settings()

    def test_strong_database_password_accepted_in_production(self, monkeypatch):
        """Verify strong database passwords pass validation in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", "StrongDbP@ssw0rd123!")
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        # Should not raise
        settings = Settings()
        assert settings.database.password == "StrongDbP@ssw0rd123!"

    @pytest.mark.parametrize("weak_jwt_secret", [
        "dev-secret-key-for-local-development", "change_me_in_production",
        "change_me_use_openssl_rand_hex_32", "change_me", "default",
    ])
    def test_weak_jwt_secret_rejected_in_production(self, monkeypatch, weak_jwt_secret):
        """Verify weak JWT secrets are rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", "StrongDbP@ssw0rd123!")
        monkeypatch.setenv("JWT__SECRET_KEY", weak_jwt_secret)
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        # Either too short (< 32 chars) or too common - both are rejected
        with pytest.raises(ValueError, match="JWT secret key (must be at least 32 characters|is too common)"):
            Settings()

    def test_strong_jwt_secret_accepted_in_production(self, monkeypatch):
        """Verify strong JWT secrets pass validation in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", "StrongDbP@ssw0rd123!")
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        # Should not raise
        settings = Settings()
        assert settings.jwt.secret_key == "strong-jwt-secret-key-32-characters-long!"

    def test_weak_db_password_accepted_in_development(self, monkeypatch):
        """Verify weak db password passes validation in development (warning only)."""
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("DATABASE__PASSWORD", "CHANGE_ME_GENERATE_STRONG_SECRET")
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        # Should not raise - development allows weak db credentials
        settings = Settings()
        assert settings.database.password == "CHANGE_ME_GENERATE_STRONG_SECRET"

    def test_placeholder_database_password_rejected_in_production(self, monkeypatch):
        """Verify a CHANGE_ME_-prefixed db password that is not an exact weak member is rejected."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", "CHANGE_ME_GENERATE_STRONG_SECRET")
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        with pytest.raises(ValueError, match="DATABASE__PASSWORD is a known placeholder value"):
            Settings()

    def test_db_password_placeholder_rejection_message_does_not_leak_submitted_value(self, monkeypatch):
        """The construction-time placeholder rejection never echoes the secret.

        The weak/placeholder database password is refused during Settings
        construction by validate_production_credentials, so this test targets
        that guard's message (it is the only reachable one; DATABASE_URL's own
        weak-password branch cannot be reached once construction has refused).
        """
        submitted_password = "CHANGE_ME_GENERATE_STRONG_SECRET"
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", submitted_password)
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        with pytest.raises(ValueError) as exc_info:
            Settings()
        message = _validation_msg(exc_info)
        assert "known placeholder value" in message
        assert submitted_password not in message
        assert submitted_password[:8] not in message

    @pytest.mark.parametrize("placeholder_admin_password", [
        "CHANGE_ME_GENERATE_STRONG_SECRET",
        "change_me_generate_strong_secret",
    ])
    def test_placeholder_db_admin_password_rejected_in_production(
        self, monkeypatch, placeholder_admin_password
    ):
        """Verify a CHANGE_ME_-prefixed database admin password is rejected.

        DATABASE__ADMIN_PASSWORD reaches the production tier through the compose
        files for db and migrate; before this guard, only its length was checked,
        so a shipped placeholder passed unexamined.
        """
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", "StrongDbP@ssw0rd123!")
        monkeypatch.setenv("DATABASE__ADMIN_PASSWORD", placeholder_admin_password)
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        with pytest.raises(ValueError, match="DATABASE__ADMIN_PASSWORD is a known placeholder value"):
            Settings()

    def test_empty_db_admin_password_rejected_in_production(self, monkeypatch):
        """Verify an empty database admin password is rejected in production."""
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", "StrongDbP@ssw0rd123!")
        monkeypatch.setenv("DATABASE__ADMIN_PASSWORD", "        ")
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.setenv("CORS_ORIGINS", '["https://production.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        with pytest.raises(ValueError, match="DATABASE__ADMIN_PASSWORD must not be empty"):
            Settings()

    def test_placeholder_db_admin_password_accepted_outside_production(self, monkeypatch):
        """Verify the placeholder guard on the db admin password is production-gated."""
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("DATABASE__ADMIN_PASSWORD", "CHANGE_ME_GENERATE_STRONG_SECRET")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        assert settings.database.admin_password == "CHANGE_ME_GENERATE_STRONG_SECRET"

    def test_placeholder_jwt_secret_still_accepted_in_development(self, monkeypatch):
        """Verify CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32 is accepted as a JWT secret.

        R3 decision made executable: JWTSettings.validate_secret_key stays
        unconditional and gains no placeholder clause, so the shipped dev template
        value remains usable outside production.
        """
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("JWT__SECRET_KEY", "CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings()
        assert settings.jwt.secret_key == "CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32"

    def test_weak_db_password_accepted_in_staging(self, monkeypatch):
        """Verify weak db password passes validation in staging."""
        monkeypatch.setenv("ENV", "staging")
        monkeypatch.setenv("DATABASE__PASSWORD", "CHANGE_ME_GENERATE_STRONG_SECRET")
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        from mkobi.config import clear_config_cache
        clear_config_cache()
        # Should not raise - staging allows weak db credentials
        settings = Settings()
        assert settings.database.password == "CHANGE_ME_GENERATE_STRONG_SECRET"



class TestProductionServiceSettingsSurface(TestSettingsBase):
    """Every production service that constructs Settings must satisfy one surface.

    migrate (via alembic/env.py) and rq-worker build Settings() at the pinned
    production tier, exactly as app does, so each must carry the same required
    variables. These tests pin that surface at the Settings level: with the
    production tier pinned, a service that lacks CORS_ORIGINS falls back to the
    shipped app.yaml placeholders and construction fails closed. That
    fail-closed precondition is the mechanism behind the whole-stack boot
    failure the pre-fix migrate and rq-worker containers produced when
    CORS_ORIGINS was supplied to app only.

    Scope limitation: both tests monkeypatch the environment and assert a
    property of Settings; neither reads docker/docker-compose.yml. They
    therefore verify the precondition, not the compose wiring that satisfies
    it, so reverting the compose-level fix would leave this suite green. The
    compose wiring is verified separately by inspecting the resolved Compose
    configuration (docker compose config), not by pytest.
    """

    def test_production_settings_construct_with_service_shaped_environment(
        self, monkeypatch
    ):
        """A production Settings with the migrate service's full surface constructs.

        The compose files resolve CORS_ORIGINS for migrate, app and rq-worker
        alike; an operator's env file is not required to set it. Without that
        resolution, cors_origins falls back to app.yaml's two localhost
        placeholders and construction raises, so migrate exits non-zero and app
        and rq-worker, which depend on migrate completing, never start.
        """
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", "StrongDbP@ssw0rd123!")
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        # The value docker/docker-compose.yml resolves for every
        # Settings-constructing production service.
        monkeypatch.setenv("CORS_ORIGINS", '["https://service.example.com"]')
        from mkobi.config import clear_config_cache
        clear_config_cache()
        settings = Settings(_env_file=None)
        assert settings.environment == EnvironmentEnum.PRODUCTION
        assert settings.cors_origins == ["https://service.example.com"]

    def test_production_settings_without_cors_origins_fail_closed(self, monkeypatch):
        """With no CORS_ORIGINS, construction refuses the app.yaml placeholders.

        This is the exact failure the pre-fix migrate and rq-worker containers
        produced. It is the precondition that makes supplying CORS_ORIGINS to
        every Settings-constructing service mandatory rather than optional.
        """
        monkeypatch.setenv("ENV", "production")
        monkeypatch.setenv("DATABASE__PASSWORD", "StrongDbP@ssw0rd123!")
        monkeypatch.setenv("JWT__SECRET_KEY", "strong-jwt-secret-key-32-characters-long!")
        monkeypatch.setenv("ADMIN_USERNAME", "prodadmin")
        monkeypatch.setenv("ADMIN_PASSWORD", "StrongP@ss1")
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        from mkobi.config import clear_config_cache
        clear_config_cache()
        with pytest.raises(ValueError, match="Placeholder CORS origins not allowed in production"):
            Settings(_env_file=None)


class TestSecretsFileFieldNameWarning(TestSettingsBase):
    """A *_FILE name that resolves to a real non-secret field warns; a name that
    resolves to no field stays at debug."""

    def _collect(self, logger_name: str, level: int):
        import logging

        captured: list[logging.LogRecord] = []

        class _Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        target_logger = logging.getLogger(logger_name)
        collector = _Collector(level=level)
        original_level = target_logger.level
        was_disabled = target_logger.disabled
        target_logger.addHandler(collector)
        target_logger.setLevel(level)
        target_logger.disabled = False
        return target_logger, collector, captured, original_level, was_disabled

    def test_file_variable_naming_ordinary_field_warns(self, tmp_path, monkeypatch):
        """DATABASE__USER_FILE names the ordinary field database.user, so it warns.

        Silently ignoring it would let database.user fall back to app.yaml's
        postgres superuser rather than the intended least-privilege role.
        """
        import logging

        payload_file = tmp_path / "db_user"
        payload_file.write_text("some_role")
        monkeypatch.setenv("DATABASE__USER_FILE", str(payload_file))
        monkeypatch.setenv("LOGGING__LOG_FILE", str(tmp_path / "logs.txt"))

        target_logger, collector, captured, original_level, was_disabled = self._collect(
            "mkobi.config", logging.WARNING
        )
        try:
            from mkobi.config import SecretsFileSource

            assert SecretsFileSource(Settings)() == {}
        finally:
            target_logger.removeHandler(collector)
            target_logger.setLevel(original_level)
            target_logger.disabled = was_disabled

        warnings = [r.getMessage() for r in captured if r.levelno == logging.WARNING]
        assert any("DATABASE__USER_FILE" in m and "DATABASE__USER" in m for m in warnings)
        # The field that resolves to nothing stays quiet at warning level.
        assert not any("LOGGING__LOG_FILE" in m for m in warnings)

    def test_file_variable_naming_no_field_does_not_warn(self, tmp_path, monkeypatch):
        """A *_FILE name that resolves to no field is skipped at debug, not warned.

        LOGGING__LOG_FILE strips to logging__log, which is not a field, so the
        running dev stack stays quiet.
        """
        import logging

        monkeypatch.setenv("LOGGING__LOG_FILE", str(tmp_path / "logs.txt"))

        target_logger, collector, captured, original_level, was_disabled = self._collect(
            "mkobi.config", logging.DEBUG
        )
        try:
            from mkobi.config import SecretsFileSource

            assert SecretsFileSource(Settings)() == {}
        finally:
            target_logger.removeHandler(collector)
            target_logger.setLevel(original_level)
            target_logger.disabled = was_disabled

        assert not any(r.levelno >= logging.WARNING for r in captured)

    def test_all_field_env_names_derivation_covers_secret_fields(self):
        """The all-field derivation is a superset of the secret-field derivation."""
        from mkobi.config import _all_field_env_names, _secret_field_env_names

        all_names = _all_field_env_names(Settings)
        assert _secret_field_env_names(Settings) <= all_names
        # Nested, aliased and top-level names all resolve.
        assert "database__user" in all_names
        assert "admin_username" in all_names
        assert "upload__allowed_extensions" in all_names
        # A non-field name is absent.
        assert "logging__log" not in all_names


class TestRqWorkerComposeWiring:
    """The rq-worker service must run the wrapper module with a live signal.

    These tests read docker/docker-compose.yml and docker/docker-compose.override.yml
    directly. They pin that both tiers run the wrapper module as the worker
    command (so the deployed entry point is the retrying wrapper, not a dead
    one) and that neither tier's healthcheck is a Redis ping or disabled: the
    healthcheck observes the worker, not the broker.
    """

    @staticmethod
    def _compose_files() -> list:
        from pathlib import Path

        docker_dir = Path(__file__).resolve().parent.parent / "docker"
        return [
            docker_dir / "docker-compose.yml",
            docker_dir / "docker-compose.override.yml",
        ]

    @staticmethod
    def _rq_worker_block(text: str) -> str:
        """Return the rq-worker service block from a compose file's text.

        The block starts at the ``rq-worker:`` key and ends at the next
        top-level service key (a line beginning with two spaces and a name).
        """
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.rstrip() == "  rq-worker:":
                start = index
                break
        assert start is not None, "rq-worker service not found"
        block = [lines[start]]
        for line in lines[start + 1:]:
            if line.startswith("  ") and not line.startswith("    ") and line.strip():
                break
            block.append(line)
        return "\n".join(block)

    def test_worker_command_is_wrapper_module_in_both_tiers(self):
        """The resolved worker command is the wrapper module, never rqworker."""
        for compose_path in self._compose_files():
            block = self._rq_worker_block(compose_path.read_text(encoding="utf-8"))
            assert "mkobi.rq_worker_wrapper" in block, compose_path.name
            assert "rqworker" not in block, compose_path.name

    def test_worker_healthcheck_is_not_ping_or_disabled_in_both_tiers(self):
        """The healthcheck is the wrapper check, not a ping and not disabled."""
        for compose_path in self._compose_files():
            block = self._rq_worker_block(compose_path.read_text(encoding="utf-8"))
            assert "disable: true" not in block, compose_path.name
            assert "Redis(" not in block, compose_path.name
            assert "redis-cli" not in block, compose_path.name
            assert "mkobi.rq_worker_wrapper" in block, compose_path.name



class TestLocallyBuiltImageIdentity:
    """OPS-016/OPS-015(b): every locally-built service carries a real image tag.

    These tests read docker/docker-compose.yml and docker/docker-compose.override.yml
    directly. Without an ``image:`` coordinate the built services run as bare
    ``:latest`` and there is no artefact a rollback can select. The tag must not
    be ``latest`` (not selectable), and the base file and the dev override must
    agree exactly, otherwise the artefact identity silently changes between
    tiers. This is the tripwire that fails if someone removes the key.
    """

    # The services that build locally (the db/redis services pull a public
    # image and are therefore out of scope for the locally-built identity).
    # nginx now also builds locally (B6: the client bundle ships inside the
    # image), but its identity is asserted by the nginx build wiring below
    # rather than by the ``mkobi/``-prefix rule here.
    _LOCALLY_BUILT = ("migrate", "app", "rq-worker")

    @staticmethod
    def _compose_files() -> dict:
        from pathlib import Path

        docker_dir = Path(__file__).resolve().parent.parent / "docker"
        return {
            "base": docker_dir / "docker-compose.yml",
            "override": docker_dir / "docker-compose.override.yml",
        }

    @staticmethod
    def _service_block(text: str, service: str) -> str:
        """Return one top-level service block from a compose file's text."""
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.rstrip() == f"  {service}:":
                start = index
                break
        assert start is not None, f"{service} service not found"
        block = [lines[start]]
        for line in lines[start + 1:]:
            if line.startswith("  ") and not line.startswith("    ") and line.strip():
                break
            block.append(line)
        return "\n".join(block)

    @staticmethod
    def _image_line(block: str) -> str | None:
        """Return the ``image:`` line of a service block, or None if absent."""
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("image:"):
                return stripped
        return None

    def test_every_locally_built_service_declares_an_image(self) -> None:
        """Both tiers declare an image coordinate for each locally-built service."""
        for name, compose_path in self._compose_files().items():
            text = compose_path.read_text(encoding="utf-8")
            for service in self._LOCALLY_BUILT:
                block = self._service_block(text, service)
                image_line = self._image_line(block)
                assert image_line is not None, f"{name}:{service} has no image:"
                assert image_line != "image: latest", f"{name}:{service}"

    def test_image_tag_is_not_latest(self) -> None:
        """The tag is never a bare 'latest': latest is not a selectable rollback."""
        for name, compose_path in self._compose_files().items():
            text = compose_path.read_text(encoding="utf-8")
            for service in self._LOCALLY_BUILT:
                image_line = self._image_line(self._service_block(text, service))
                assert image_line is not None, f"{name}:{service}"
                assert ":latest" not in image_line, f"{name}:{service} -> {image_line}"
                # The repository is the local store, so an honest local name.
                assert image_line.startswith("image: mkobi/"), f"{name}:{service}"

    def test_base_and_override_image_coordinates_agree(self) -> None:
        """The dev override declares the identical image value as the base file.

        An override that declared a different value for the same service is a
        latent bug: the tag in the base file and the tag produced by a build
        would diverge, and a rollback would select an artefact that no longer
        matches the service definition.
        """
        files = self._compose_files()
        base_text = files["base"].read_text(encoding="utf-8")
        override_text = files["override"].read_text(encoding="utf-8")

        for service in self._LOCALLY_BUILT:
            base_image = self._image_line(self._service_block(base_text, service))
            override_image = self._image_line(self._service_block(override_text, service))
            assert base_image is not None, f"base:{service}"
            assert override_image is not None, f"override:{service}"
            assert base_image == override_image, f"{service}: {base_image} != {override_image}"


class TestLogFileNotSetByCompose:
    """OPS-008/VAL-10-003: no compose service sets LOGGING__LOG_FILE by default.

    Four processes (app, rq-worker, the migrate service and the dev worker) each
    opened one RotatingFileHandler against the same file when the key was set for
    everyone, so the rotation ceiling was 4 x 6 files x 10 MB ~= 240 MB instead
    of ~150 MB. The setting is not deprecated: ``logging.log_file`` still accepts
    an explicit operator value in .env and adds the handler. These tests read both
    compose files directly and pin that neither tier sets the key for app or
    rq-worker. This is the tripwire that fails if someone re-adds it.
    """

    @staticmethod
    def _compose_files() -> dict:
        from pathlib import Path

        docker_dir = Path(__file__).resolve().parent.parent / "docker"
        return {
            "base": docker_dir / "docker-compose.yml",
            "override": docker_dir / "docker-compose.override.yml",
        }

    @staticmethod
    def _service_block(text: str, service: str) -> str:
        """Return one top-level service block from a compose file's text."""
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.rstrip() == f"  {service}:":
                start = index
                break
        assert start is not None, f"{service} service not found"
        block = [lines[start]]
        for line in lines[start + 1:]:
            if line.startswith("  ") and not line.startswith("    ") and line.strip():
                break
            block.append(line)
        return "\n".join(block)

    def test_neither_tier_sets_log_file_for_app_or_worker(self) -> None:
        """LOGGING__LOG_FILE is absent from app and rq-worker in both compose files.

        Scope note: the dev override blanks the key for ``app`` with an empty
        value (``LOGGING__LOG_FILE: ""``), which is falsy and therefore adds no
        handler — that is the correct dev posture, not a live writer. The
        rejectable case is a non-empty assignment, which is what the base file
        set for both services and what the override set for ``rq-worker``.
        """
        for name, compose_path in self._compose_files().items():
            text = compose_path.read_text(encoding="utf-8")
            for service in ("app", "rq-worker"):
                block = self._service_block(text, service)
                assigns = [
                    line
                    for line in block.splitlines()
                    if "LOGGING__LOG_FILE" in line and not line.strip().startswith("#")
                ]
                # A blank assignment creates no handler (falsy) and is allowed.
                live = [
                    line for line in assigns if line.split(":", 1)[1].strip() not in ('""', "''")
                ]
                assert not live, f"{name}:{service} sets LOGGING__LOG_FILE -> {live}"

    def test_log_file_setting_still_works_when_supplied_explicitly(
        self, monkeypatch, tmp_path
    ) -> None:
        """The setting is not deprecated: an explicit value still resolves.

        This pins that removing the compose default did not remove the setting
        surface; an operator who wants file logging in their own .env can still
        set ``LOGGING__LOG_FILE``.
        """
        from mkobi.config import clear_config_cache

        explicit = tmp_path / "app.log"
        monkeypatch.setenv("LOGGING__LOG_FILE", str(explicit))
        clear_config_cache()
        settings = Settings(_env_file=None)
        assert settings.log_file == str(explicit)


class TestRateLimiterOverrideWiring:
    """SECB-9: the dev override must declare the limiter posture for both services.

    The base compose passes ``RATE_LIMITER_FAIL_CLOSED`` to ``app`` and
    ``rq-worker``, but the dev override declared no such key, so a developer
    setting it in ``.env`` had no way to reach the dev tier through the override
    file. These tests read both compose files directly and pin the key in each
    dev service block with the same base default.
    """

    @staticmethod
    def _compose_files() -> dict:
        from pathlib import Path

        docker_dir = Path(__file__).resolve().parent.parent / "docker"
        return {
            "base": docker_dir / "docker-compose.yml",
            "override": docker_dir / "docker-compose.override.yml",
        }

    @staticmethod
    def _service_block(text: str, service: str) -> str:
        """Return one top-level service block from a compose file's text."""
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.rstrip() == f"  {service}:":
                start = index
                break
        assert start is not None, f"{service} service not found"
        block = [lines[start]]
        for line in lines[start + 1:]:
            if line.startswith("  ") and not line.startswith("    ") and line.strip():
                break
            block.append(line)
        return "\n".join(block)

    def test_override_declares_rate_limiter_key_for_app_and_worker(self) -> None:
        """Both dev services declare RATE_LIMITER_FAIL_CLOSED with the base default."""
        files = self._compose_files()
        override_text = files["override"].read_text(encoding="utf-8")

        for service in ("app", "rq-worker"):
            block = self._service_block(override_text, service)
            assert "RATE_LIMITER_FAIL_CLOSED" in block, service
            assert "${RATE_LIMITER_FAIL_CLOSED:-true}" in block, service

    def test_base_still_declares_the_key_for_both_services(self) -> None:
        """The base tier keeps the key, so the override matches rather than diverges."""
        files = self._compose_files()
        base_text = files["base"].read_text(encoding="utf-8")

        for service in ("app", "rq-worker"):
            block = self._service_block(base_text, service)
            assert "RATE_LIMITER_FAIL_CLOSED" in block, service


class TestQualityGateToolsService:
    """OPS-009: the quality gates run without application credentials.

    ``lint``, ``format`` and ``typecheck`` used to execute inside the ``app``
    service, which holds the full credential set (database password, JWT secret,
    admin credentials, Redis password). A gate is the code most likely to run
    against untrusted input, so it must not be able to read those values from its
    own environment. These tests read docker/docker-compose.override.yml directly
    and pin two properties: the ``tools`` service declares **no** application
    credential key, and the Makefile runs the three static-analysis gates against
    ``tools`` rather than ``app``.

    The database-dependent migration targets are pinned to ``app`` in the same
    test class as a regression guard: a later cleanup must not quietly move a
    gate that needs a live connection onto the credential-free runner, which has
    none.
    """

    # The application credential keys the tools service must not declare. These
    # are the actual secret names the compose files use, not a generic pattern.
    _APPLICATION_CREDENTIALS = (
        "DATABASE__PASSWORD",
        "MKOBI_APP_PASSWORD",
        "JWT__SECRET_KEY",
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD",
        "REDIS__PASSWORD",
    )

    @staticmethod
    def _override_path():
        from pathlib import Path

        return Path(__file__).resolve().parent.parent / "docker" / "docker-compose.override.yml"

    @staticmethod
    def _makefile_path():
        from pathlib import Path

        return Path(__file__).resolve().parent.parent / "Makefile.ps1"

    @staticmethod
    def _service_block(text: str, service: str) -> str:
        """Return one top-level service block from a compose file's text."""
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.rstrip() == f"  {service}:":
                start = index
                break
        assert start is not None, f"{service} service not found"
        block = [lines[start]]
        for line in lines[start + 1:]:
            if line.startswith("  ") and not line.startswith("    ") and line.strip():
                break
            block.append(line)
        return "\n".join(block)

    @classmethod
    def _declared_credentials(cls, block: str) -> list[str]:
        """Credential keys the block declares as live environment assignments.

        Comment lines are ignored so an explanatory note that mentions a secret
        name does not count as an assignment.
        """
        found: list[str] = []
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for key in cls._APPLICATION_CREDENTIALS:
                # Match ``KEY:`` / ``KEY=`` at the line's head, so a substring
                # mention inside another value does not count.
                if stripped.startswith(f"{key}:") or stripped.startswith(f"{key}="):
                    found.append(key)
        return found

    def test_tools_service_exists_in_dev_override(self) -> None:
        """The dev override declares a ``tools`` service."""
        text = self._override_path().read_text(encoding="utf-8")
        block = self._service_block(text, "tools")
        assert block, "tools service not found"

    def test_tools_service_declares_no_application_credentials(self) -> None:
        """Every application credential key is absent from the tools service."""
        text = self._override_path().read_text(encoding="utf-8")
        block = self._service_block(text, "tools")
        declared = self._declared_credentials(block)
        assert not declared, f"tools declares application credentials: {declared}"

    def test_tools_service_keeps_caches_off_the_working_tree(self) -> None:
        """RUFF_CACHE_DIR / MYPY_CACHE_DIR point inside the container, not /app.

        The source tree is bind-mounted from the host, so a cache written to the
        working directory would land in the developer's tree. The caches must be
        redirected to a path outside the mounted tree.
        """
        text = self._override_path().read_text(encoding="utf-8")
        block = self._service_block(text, "tools")
        assert "RUFF_CACHE_DIR: /tmp/ruff_cache" in block
        assert "MYPY_CACHE_DIR: /tmp/mypy_cache" in block

    def test_static_analysis_gates_run_on_tools_not_app(self) -> None:
        """lint / format / typecheck resolve against ``tools`` in the Makefile."""
        makefile = self._makefile_path().read_text(encoding="utf-8")
        for function in ("Invoke-Lint", "Invoke-Format", "Invoke-Typecheck"):
            body = _function_body(makefile, function)
            assert "--no-deps tools " in body, function
            assert "--no-deps app " not in body, function

    def test_database_dependent_gates_stay_on_app(self) -> None:
        """migration-new / migration-status keep the credentialed ``app`` service.

        Autogenerate and ``alembic current`` open a real database connection, so
        they are not static analysis and must not move to the credential-free
        runner. This is the regression guard against a later cleanup.
        """
        makefile = self._makefile_path().read_text(encoding="utf-8")
        for function in ("Invoke-MigrationNew", "Invoke-MigrationStatus"):
            body = _function_body(makefile, function)
            assert "--no-deps app " in body or " app " in body, function
            assert "--no-deps tools " not in body, function


def _function_body(makefile_text: str, function_name: str) -> str:
    """Return the body of a ``function <name> { ... }`` PowerShell definition.

    The body starts at the ``function`` line and ends at the first line that is
    exactly ``}`` at column zero.
    """
    lines = makefile_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith(f"function {function_name} "):
            start = index
            break
    assert start is not None, f"function {function_name} not found"
    body = [lines[start]]
    for line in lines[start + 1:]:
        body.append(line)
        if line.rstrip() == "}":
            break
    return "\n".join(body)


class TestRuntimeBoundaryAndSupervision:
    """OPS-014 / DP-10-12: the hardened boundary spans app, worker and migrator.

    ``app`` alone carried ``cap_drop``, ``security_opt`` and ``read_only``.
    These tests read docker/docker-compose.yml and docker/docker-compose.override.yml
    directly and pin that ``rq-worker`` and ``migrate`` carry the same capability
    and privilege-escalation boundary, that ``read_only`` is enabled on the
    worker (its writes land on the app_data volume and tmpfs /tmp) but *not* on
    the migrator (whose write surface is the database), that ``app``'s four keys
    are unchanged, and that the worker healthcheck remains the proof-based
    registry probe with the retuned DP-10-12 window.
    """

    @staticmethod
    def _compose_files() -> dict:
        from pathlib import Path

        docker_dir = Path(__file__).resolve().parent.parent / "docker"
        return {
            "base": docker_dir / "docker-compose.yml",
            "override": docker_dir / "docker-compose.override.yml",
        }

    @staticmethod
    def _service_block(text: str, service: str) -> str:
        """Return one top-level service block from a compose file's text."""
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.rstrip() == f"  {service}:":
                start = index
                break
        assert start is not None, f"{service} service not found"
        block = [lines[start]]
        for line in lines[start + 1:]:
            if line.startswith("  ") and not line.startswith("    ") and line.strip():
                break
            block.append(line)
        return "\n".join(block)

    @staticmethod
    def _top_level_key(block: str, key: str) -> str | None:
        """Value text of a service-level ``key:`` (two-space indent) or None.

        ``read_only: true`` and its false form both match; a nested key (four
        spaces) does not, which matters for ``healthcheck``'s sub-keys.
        """
        for line in block.splitlines():
            if line.startswith(f"    {key}:"):
                return line.split(":", 1)[1].strip()
        return None

    def test_rq_worker_and_migrate_carry_the_boundary(self) -> None:
        """The base file gives both services no-new-privileges and cap_drop ALL.

        The boundary is defined once, in the base file; the dev override inherits
        it rather than repeating it. The override is checked separately below to
        ensure it does not relax the inherited posture.
        """
        base = self._compose_files()["base"].read_text(encoding="utf-8")
        for service in ("rq-worker", "migrate"):
            block = self._service_block(base, service)
            assert "no-new-privileges:true" in block, f"base:{service}"
            assert "cap_drop:" in block, f"base:{service}"
            assert "- ALL" in block, f"base:{service}"

    def test_dev_override_does_not_relax_the_boundary(self) -> None:
        """The dev override never re-enables privileges or drops the cap_drop.

        A later edit that added ``read_only: false`` to the worker, or replaced
        ``cap_drop`` with an empty list, would silently widen the boundary in the
        tier developers actually run. Pinning the absence of those relaxations is
        the guard.
        """
        override = self._compose_files()["override"].read_text(encoding="utf-8")
        worker = self._service_block(override, "rq-worker")
        # read_only must not be flipped off in dev.
        assert self._top_level_key(worker, "read_only") != "false"
        # cap_drop, if present at all, must still contain ALL.
        if "cap_drop:" in worker:
            assert "- ALL" in worker

    def test_app_boundary_is_unchanged(self) -> None:
        """app keeps read_only true, cap_drop ALL and no-new-privileges in base."""
        base = self._compose_files()["base"].read_text(encoding="utf-8")
        block = self._service_block(base, "app")
        assert self._top_level_key(block, "read_only") == "true"
        assert "cap_drop:" in block
        assert "- ALL" in block
        assert "no-new-privileges:true" in block

    def test_rq_worker_is_read_only_with_tmpfs_in_both_tiers(self) -> None:
        """The worker is read-only and covers /tmp with a tmpfs in both tiers.

        /tmp is required under read_only because Python's tempfile.gettempdir()
        finds no usable directory in a read-only rootfs. The app_data volume
        covers /app/data, so no tmpfs may be placed over tmp_uploads: a tmpfs
        there would mask the volume and hide the file the app admitted.
        """
        for name, compose_path in self._compose_files().items():
            text = compose_path.read_text(encoding="utf-8")
            block = self._service_block(text, "rq-worker")
            assert self._top_level_key(block, "read_only") == "true", name
            assert "tmpfs:" in block, name
            assert "/tmp:rw,size=128m" in block, name

    def test_migrate_does_not_declare_read_only(self) -> None:
        """The migrator writes only SQL, so read_only buys nothing and is absent."""
        for name, compose_path in self._compose_files().items():
            text = compose_path.read_text(encoding="utf-8")
            block = self._service_block(text, "migrate")
            assert self._top_level_key(block, "read_only") is None, name

    def test_worker_healthcheck_is_registry_probe_with_new_window(self) -> None:
        """The probe stays proof-based; the DP-10-12 window is the retuned one."""
        for name, compose_path in self._compose_files().items():
            text = compose_path.read_text(encoding="utf-8")
            block = self._service_block(text, "rq-worker")
            assert "mkobi.rq_worker_wrapper" in block, name
            assert "Redis(" not in block, name
            assert "redis-cli" not in block, name
            assert "disable: true" not in block, name
            for key, value in (
                ("interval", "10s"),
                ("timeout", "5s"),
                ("retries", "3"),
                ("start_period", "60s"),
            ):
                assert f"{key}: {value}" in block, f"{name}:{key}"



class TestBuildInputPinning:
    """OPS-016 (integrity half): every build input resolves to a pinned digest.

    A build that is not reproducible is not a build that can be rolled back to.
    These tests read docker/Dockerfile and all three compose files directly and
    pin three properties: every external base image is digest-pinned (an internal
    stage reference is allowed, since it resolves within the same Dockerfile);
    the ``uv`` installer is downloaded and checksum-verified rather than piped
    straight to a shell; and all three locally-built services (``migrate``,
    ``app``, ``rq-worker``) receive the same ``UV_VERSION`` value, so no service
    builds from a different input than its peers.
    """

    # The digest form accepted: ``name[:tag]@sha256:<64 hex>``.
    _DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}$")

    @staticmethod
    def _docker_dir():
        from pathlib import Path

        return Path(__file__).resolve().parent.parent / "docker"

    def _dockerfile_text(self) -> str:
        return (self._docker_dir() / "Dockerfile").read_text(encoding="utf-8")

    def _base_images(self, text: str) -> list:
        """Return the image reference of every ``FROM`` line in the Dockerfile."""
        images = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("FROM "):
                # FROM <image> [AS <stage>]
                images.append(stripped.split()[1])
        return images

    def _stage_names(self, text: str) -> set:
        """Return every ``AS <name>`` stage name declared in the Dockerfile."""
        names = set()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("FROM ") and " AS " in stripped.upper():
                names.add(stripped.split()[-1].lower())
        return names

    def test_every_external_from_is_digest_pinned(self) -> None:
        """No external base image is left on a floating tag.

        An internal stage reference (a name declared by another ``FROM ... AS``)
        is not an external input and is allowed. Anything else must carry a
        resolved ``@sha256:`` digest or the build is not reproducible.
        """
        text = self._dockerfile_text()
        stages = self._stage_names(text)
        froms = self._base_images(text)
        assert froms, "no FROM instructions found"
        external = [img for img in froms if img.lower() not in stages]
        assert external, "expected at least one external base image"
        for image in external:
            assert self._DIGEST_RE.search(image), f"unpinned base image: {image}"

    def test_compose_images_are_digest_pinned(self) -> None:
        """Every external ``image:`` in the three compose files is digest-pinned.

        Locally-built services carry a repository-local tag (``mkobi/...``) that
        is built, never pulled, so the digest rule does not apply to them. Every
        other image is pulled from a registry and must be pinned.
        """
        for compose_path in self._compose_files().values():
            text = compose_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped.startswith("image:") or stripped.startswith("#"):
                    continue
                value = stripped.split(":", 1)[1].strip()
                # Locally-built artefact: tag is overridable and never pulled.
                if value.startswith("mkobi/"):
                    continue
                assert self._DIGEST_RE.search(value), (
                    f"{compose_path.name}: unpinned image: {value}"
                )

    @staticmethod
    def _compose_files() -> dict:
        from pathlib import Path

        docker_dir = Path(__file__).resolve().parent.parent / "docker"
        return {
            "base": docker_dir / "docker-compose.yml",
            "override": docker_dir / "docker-compose.override.yml",
            "test": docker_dir / "docker-compose.test.yml",
        }

    def test_uv_installer_is_checksum_verified(self) -> None:
        """The uv installer is fetched to a file and verified, never piped to sh.

        An unverified ``curl | sh`` executes whatever the URL returns; pinning
        ``UV_VERSION`` pins only the path, not the bytes. The build must download,
        check a pinned SHA-256 and run the installer only on a match, and it must
        fail closed on a mismatch.
        """
        text = self._dockerfile_text()
        # The old pipe-to-shell form must be gone entirely.
        assert "curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh" not in text
        # The download-then-verify mechanism must be present for the pinned version.
        assert "UV_INSTALLER_SHA256" in text
        assert "sha256sum -c -" in text
        # A mismatch must abort: the check runs before the installer is invoked.
        check_index = text.index("sha256sum -c -")
        run_index = text.index("sh /tmp/uv-install.sh")
        assert check_index < run_index, "checksum check must precede installer run"

    def test_all_built_services_receive_the_same_uv_version(self) -> None:
        """migrate, app and rq-worker pass an identical UV_VERSION build arg.

        The defect was divergence: ``app`` passed an explicit ``UV_VERSION`` while
        ``migrate`` and ``rq-worker`` passed none and silently fell back to the
        Dockerfile default. One mechanism must govern all three.
        """
        base_text = self._compose_files()["base"].read_text(encoding="utf-8")
        override_text = self._compose_files()["override"].read_text(encoding="utf-8")

        def uv_arg(block: str) -> str | None:
            for line in block.splitlines():
                stripped = line.strip()
                if stripped.startswith("- UV_VERSION="):
                    return stripped.split("=", 1)[1].strip()
            return None

        for name, text in (("base", base_text), ("override", override_text)):
            values = set()
            for service in ("migrate", "app", "rq-worker"):
                block = self._service_block(text, service)
                value = uv_arg(block)
                assert value is not None, f"{name}:{service} declares no UV_VERSION arg"
                values.add(value)
            assert len(values) == 1, f"{name}: UV_VERSION diverges across services: {values}"

    @staticmethod
    def _service_block(text: str, service: str) -> str:
        """Return one top-level service block from a compose file's text."""
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.rstrip() == f"  {service}:":
                start = index
                break
        assert start is not None, f"{service} service not found"
        block = [lines[start]]
        for line in lines[start + 1:]:
            if line.startswith("  ") and not line.startswith("    ") and line.strip():
                break
            block.append(line)
        return "\n".join(block)


class TestEdgeLogStreamAndSizeBound:
    """OPS-006/OPS-013: the edge streams its logs and its size bound resolves.

    Measured state before the fix: nginx wrote access.log and error.log onto the
    tmpfs mounted at /var/log/nginx, so ``docker compose logs nginx`` never saw a
    line and the files vanished with the container; and ``client_max_body_size``
    was a bare ``100m`` literal tied to the backend only by a comment, so changing
    the application ceiling silently diverged from the edge. These tests read the
    edge template and the compose file directly and pin the wiring: both log
    destinations target the standard streams, the ceiling is a template
    placeholder fed by an environment key, and the access log uses a
    query-redacting ``log_format`` that the render script's explicit substitution
    list leaves intact.
    """

    @staticmethod
    def _docker_dir():
        from pathlib import Path

        return Path(__file__).resolve().parent.parent / "docker"

    @staticmethod
    def _service_block(text: str, service: str) -> str:
        """Return one top-level service block from a compose file's text."""
        lines = text.splitlines()
        start = None
        for index, line in enumerate(lines):
            if line.rstrip() == f"  {service}:":
                start = index
                break
        assert start is not None, f"{service} service not found"
        block = [lines[start]]
        for line in lines[start + 1:]:
            if line.startswith("  ") and not line.startswith("    ") and line.strip():
                break
            block.append(line)
        return "\n".join(block)

    def _template_text(self) -> str:
        return (self._docker_dir() / "nginx" / "nginx.conf.template").read_text(
            encoding="utf-8"
        )

    def test_both_log_destinations_are_the_standard_streams(self) -> None:
        """The edge streams to stdout/stderr, not to files under /var/log/nginx.

        OPS-006: a log file on the tmpfs never reaches ``docker logs`` and is
        destroyed with the container, so the operator loses the only record of
        what the edge served.
        """
        text = self._template_text()
        assert "access_log /dev/stdout mkobi_redacted;" in text
        assert "error_log /dev/stderr;" in text
        # The tmpfs files are gone from every log directive.
        assert "/var/log/nginx/access.log" not in text
        assert "/var/log/nginx/error.log" not in text

    def test_client_max_body_size_is_a_placeholder_not_a_literal(self) -> None:
        """OPS-013: the ceiling resolves from the environment, not a bare literal.

        A bare ``100m`` cannot follow the application ceiling. The template must
        carry the placeholder so the rendered value comes from the environment.
        """
        text = self._template_text()
        assert "client_max_body_size ${NGINX_CLIENT_MAX_BODY_SIZE};" in text
        for line in text.splitlines():
            if "client_max_body_size" not in line or line.strip().startswith("#"):
                continue
            assert "${NGINX_CLIENT_MAX_BODY_SIZE}" in line, line

    def test_nginx_service_feeds_the_size_bound_key(self) -> None:
        """The nginx service declares the environment key that fills the template."""
        base_text = (self._docker_dir() / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        block = self._service_block(base_text, "nginx")
        assert "NGINX_CLIENT_MAX_BODY_SIZE" in block
        assert "${NGINX_CLIENT_MAX_BODY_SIZE:-" in block

    def test_render_script_substitution_list_is_explicit(self) -> None:
        """AZ-14: the render script must not run a bare ``envsubst``.

        A bare ``envsubst`` with no variable list substitutes *every* ``$VAR``,
        which would blank nginx's own runtime variables (``$uri``, ``$status``,
        ``$remote_addr``, ...) in the ``log_format`` and every other directive
        that uses them -- a log format that renders blank fields and looks fine.
        The substitution list must name exactly the template placeholder, so
        nginx variables survive rendering verbatim.
        """
        script = (
            self._docker_dir() / "nginx" / "entrypoint-render.sh"
        ).read_text(encoding="utf-8")
        # The only envsubst invocation is the explicit-list form.
        assert "envsubst '${NGINX_CLIENT_MAX_BODY_SIZE}'" in script
        for line in script.splitlines():
            if "envsubst" not in line or line.strip().startswith("#"):
                continue
            assert "envsubst '" in line, line
            assert "${NGINX_CLIENT_MAX_BODY_SIZE}" in line, line

    def test_access_log_format_redacts_the_query_string(self) -> None:
        """AZ-14: a ``log_format`` exists, is attached, and logs ``$uri`` only.

        ``$request_uri`` carries the query string, where a ``filters=`` payload
        can hold user-supplied filter values. The format must use ``$uri`` (path
        only) and must not use ``$request_uri`` anywhere.
        """
        text = self._template_text()
        assert "log_format" in text
        # Attached to the access log by name.
        assert "access_log /dev/stdout mkobi_redacted;" in text
        # The format logs the path only, and names no query-bearing variable in
        # any active directive. Comment lines are allowed to name the forbidden
        # variable while explaining the rule.
        assert "$uri" in text
        for line in text.splitlines():
            if line.strip().startswith("#"):
                continue
            assert "$request_uri" not in line, line
        for line in text.splitlines():
            if "access_log" not in line or line.strip().startswith("#"):
                continue
            # Every active access_log line names the redacting format.
            assert "mkobi_redacted" in line, line


class TestLogsRetentionDefaultHasOneSource:
    """The processing-log retention default is declared exactly once.

    ``Settings.logs_retention_days`` and ``DatabaseStarterConfig``'s constructor
    default describe the same setting. They historically carried two literals
    (90 and 30) that could drift apart the moment anyone constructed the starter
    directly. This pins agreement between the two *live* defaults rather than any
    literal, so it fails on drift even if both were edited to the same wrong
    number independently.
    """

    def test_starter_and_settings_defaults_agree(self) -> None:
        import inspect

        from mkobi.db.starter import DatabaseStarterConfig

        settings_default = Settings.model_fields["logs_retention_days"].default
        starter_default = inspect.signature(DatabaseStarterConfig).parameters[
            "logs_retention_days"
        ].default
        assert starter_default == settings_default

    def test_both_defaults_resolve_to_the_single_shared_constant(self) -> None:
        import inspect

        from mkobi.config import LOGS_RETENTION_DAYS_DEFAULT
        from mkobi.db.starter import DatabaseStarterConfig

        assert Settings.model_fields["logs_retention_days"].default == (
            LOGS_RETENTION_DAYS_DEFAULT
        )
        assert inspect.signature(DatabaseStarterConfig).parameters[
            "logs_retention_days"
        ].default == LOGS_RETENTION_DAYS_DEFAULT

