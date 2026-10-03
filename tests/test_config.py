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
        distribution's metadata independently, so it fails if the default
        reverts to a hard-written string that no longer matches the package.
        """
        from mkobi.config import distribution_version

        resolved = Settings(_env_file=None).app.version
        assert resolved == distribution_version()

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

