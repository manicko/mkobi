import functools
import importlib.metadata
import logging
import os
from pathlib import Path
from collections.abc import Collection, Hashable
from typing import Any, ClassVar, Final, cast
from urllib.parse import urlparse

from pydantic import BaseModel, Field, PostgresDsn, ValidationInfo, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, YamlConfigSettingsSource
from pydantic_settings.sources import PydanticBaseSettingsSource
from platformdirs import user_data_dir

from mkobi.models.enums import EnvironmentEnum, FileExtensionEnum

# Installed distribution whose metadata declares the advertised application
# version. Named once so the resolver and its error message cannot disagree.
DISTRIBUTION_NAME: Final[str] = "mkobi"


@functools.cache
def distribution_version() -> str:
    """Return the version declared by the installed distribution.

    The advertised application version has exactly one source: the installed
    distribution's metadata, so the published schema document's ``info.version``
    tracks the package rather than a hand-written literal. It is resolved from
    the installed distribution named by ``DISTRIBUTION_NAME`` and memoised, so
    repeated settings construction performs one lookup.

    Returns:
        str: The distribution's declared version.

    Raises:
        RuntimeError: If the distribution is not installed, so no metadata
            exists. Raising is deliberate: a fallback literal would re-create
            the hand-written value this function exists to remove.
    """
    try:
        return importlib.metadata.version(DISTRIBUTION_NAME)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"Distribution {DISTRIBUTION_NAME!r} is not installed, so its version "
            "cannot be resolved. Install the project (for example 'uv sync') so "
            "the advertised version has exactly one source."
        ) from exc

logger = logging.getLogger(__name__)

WEAK_USERNAMES = {"admin", "administrator", "root", "test", "user", "admin@example.com"}
WEAK_PASSWORDS = {
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
}

# Minimum admin password length, shared by DatabaseSettings.validate_admin_password_strength
# and Settings.validate_admin_credentials so the two guards cannot drift apart.
ADMIN_PASSWORD_MIN_LENGTH = 8

# Case-insensitive prefix that marks a shipped placeholder credential.
PLACEHOLDER_CREDENTIAL_PREFIX = "change_me"


def is_weak_credential(value: str | None, weak_values: Collection[str]) -> bool:
    """Return True when a credential is a known weak or placeholder value.

    A missing value (None) is not weak; callers guard optional fields with a
    truthiness check. Comparison is case-insensitive and exact, never substring
    based, so a legitimate value that merely contains a weak word is accepted.

    Args:
        value: The credential value to inspect, possibly None.
        weak_values: The set of known weak values to compare against.

    Returns:
        bool: True if the value is an exact, case-insensitive member of
            weak_values; False otherwise.
    """
    if value is None:
        return False
    return value.lower() in {weak.lower() for weak in weak_values}


def is_placeholder_credential(value: str | None) -> bool:
    """Return True when a credential carries the shipped placeholder prefix.

    A missing value (None) is not a placeholder. Matching is case-insensitive
    and prefix based, which is the rule that catches the CHANGE_ME_ family the
    shipped templates use but which is only an exact member for some values.

    Args:
        value: The credential value to inspect, possibly None.

    Returns:
        bool: True if the value starts with the placeholder prefix, ignoring
            case; False otherwise.
    """
    if value is None:
        return False
    return value.lower().startswith(PLACEHOLDER_CREDENTIAL_PREFIX)


def is_weak_admin_password(value: str | None) -> bool:
    """Return True when an admin password is unusable for production.

    Composite of the four production clauses: exact known-weak member,
    shipped placeholder prefix, empty or whitespace-only, and below the
    minimum length. Defined once here so the configuration validator and the
    startup-time guard in DatabaseStarter cannot drift apart. A missing value
    (None) is treated as weak, matching an empty credential.

    Args:
        value: The admin password to inspect, possibly None.

    Returns:
        bool: True if the password must be refused in production.
    """
    if value is None:
        return True
    return (
        is_weak_credential(value, WEAK_PASSWORDS)
        or is_placeholder_credential(value)
        or not value.strip()
        or len(value) < ADMIN_PASSWORD_MIN_LENGTH
    )


def is_weak_admin_username(value: str | None) -> bool:
    """Return True when an admin username is unusable for production.

    Composite of the two production clauses: exact known-weak member and
    shipped placeholder prefix or empty/whitespace. Defined once here so the
    configuration validator and the startup-time guard in DatabaseStarter
    cannot drift apart. A missing value (None) is treated as weak.

    Args:
        value: The admin username to inspect, possibly None.

    Returns:
        bool: True if the username must be refused in production.
    """
    if value is None:
        return True
    return (
        is_weak_credential(value, WEAK_USERNAMES)
        or is_placeholder_credential(value)
        or not value.strip()
    )


def _set_nested_value(data: dict[str, Any], key: str, value: Any) -> None:
    """Set a nested value in a dict using __ as separator.

    Example: _set_nested_value({}, "DATABASE__PASSWORD", "secret")
             -> {"database": {"password": "secret"}}
    """
    parts = key.lower().split("__")
    current = data
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


class SecretsFileSource(PydanticBaseSettingsSource):
    """Custom settings source for reading Docker secrets from files.

    Supports environment variables like DATABASE__PASSWORD_FILE that point to
    files containing the actual secret values (Docker secrets pattern).
    """

    def get_field_value(self, field_info: FieldInfo, field_name: str) -> Any:
        """Read secret from file for a specific field."""
        return None  # Not used - we override __call__ instead

    def __call__(self) -> dict[str, Any]:
        """Read secrets from file-based environment variables.

        Only variables whose base name is a secret-bearing field are honoured.
        A *_FILE name that resolves to an ordinary settings field is skipped
        with a warning naming the variable and the field (never the value),
        because silently ignoring it would let the field fall back to another
        source. A *_FILE name that resolves to no field at all is skipped at
        debug level.
        """
        result: dict[str, Any] = {}
        allowed_names = _secret_field_env_names(self.settings_cls)
        known_names = _all_field_env_names(self.settings_cls)

        # Look for environment variables ending with _FILE
        for env_var_name in list(os.environ.keys()):
            if not env_var_name.endswith("_FILE"):
                continue
            # Get the base env var name (without _FILE suffix)
            base_env_var = env_var_name[:-5]  # Remove "_FILE"
            if base_env_var.lower() not in allowed_names:
                if base_env_var.lower() in known_names:
                    # A real, addressable field that simply is not secret-bearing.
                    # Ignoring it silently would let a mis-set *_FILE fall back to
                    # another source's value, so surface the mistake by name.
                    logger.warning(
                        "Ignoring *_FILE variable %s: %s is not a secret-bearing field",
                        env_var_name,
                        base_env_var,
                    )
                else:
                    # Names nothing on Settings (for example LOGGING__LOG_FILE,
                    # which strips to logging__log: only the "_FILE" suffix is
                    # removed, so the "__" nesting separator survives and the
                    # base is not a field path). Silent at debug level.
                    logger.debug(
                        "Skipping *_FILE variable that names no settings field: %s",
                        env_var_name,
                    )
                continue

            file_path_str = os.environ[env_var_name]
            file_path = Path(file_path_str)

            if file_path.exists():
                try:
                    secret_value = file_path.read_text().strip()
                    # Convert DATABASE__PASSWORD to nested dict structure
                    _set_nested_value(result, base_env_var, secret_value)
                    logger.debug(
                        f"Loaded secret for {base_env_var} from {file_path}"
                    )
                except OSError as e:
                    logger.warning(f"Failed to read secret file {file_path}: {e}")

        return result

    def __repr__(self) -> str:
        return "SecretsFileSource()"


class DatabaseSettings(BaseModel):
    """Database connection settings."""

    host: str = "localhost"
    port: int = 5432
    dbname: str = "bidb"
    user: str = "mkobi_app"
    password: str | None = None
    test_dbname: str = "bidb_test"
    # Admin credentials for database administration operations (test DB creation)
    admin_user: str = "postgres"
    admin_password: str | None = None
    # Transaction-scoped bound on the aggregate-rebuild advisory-lock wait
    # (DATABASE__LOCK_TIMEOUT_MS). 180 000 ms is comfortably above a 100 MB upload
    # plus aggregation, and - the binding reason - below the 30-minute
    # stale_processing_timeout_minutes backstop: a lock wait that outlives the
    # mechanism meant to clean up after it is not a bound at all.
    lock_timeout_ms: int = 180_000

    # Application connection-pool settings. Field names are the unprefixed
    # SQLAlchemy keywords so the settings-to-engine mapping is 1:1 and greppable
    # in both directions. Defaults are the values that were previously hard-coded
    # in db/session.py, so rollout changes nothing.
    #
    # 0 is SQLAlchemy's unbounded sentinel: it disables the pool-size cap *and
    # silently discards max_overflow*, so an operator writing 0 meaning "no
    # pooling" gets the opposite. The validator below refuses it and points at
    # NullPool, which is the supported way to express "no pooling".
    pool_size: int = Field(default=10, le=500)  # DATABASE__POOL_SIZE
    # max_overflow=0 is legitimate - a strict cap that permits no overflow - so
    # unlike pool_size it is not refused. That asymmetry is why the two fields
    # carry different validation shapes.
    max_overflow: int = Field(default=20, ge=0, le=500)  # DATABASE__MAX_OVERFLOW
    # ge=1 is not arbitrary: the async pool's get() is asyncio.wait_for(q.get(),
    # timeout), and wait_for(coro, 0) on an unready future raises in ~0.2 ms. So
    # pool_timeout=0 means "fail immediately, never queue" - every burst becomes
    # an instant 500 - and not the intuitive "wait forever".
    pool_timeout: int = Field(default=30, ge=1, le=300)  # DATABASE__POOL_TIMEOUT
    # -1 is SQLAlchemy's own sentinel and the value effective today (the setting
    # was absent, so no recycled connection ever expired). Allowing -1 keeps
    # rollout a no-op; the recommended production value (300 s) is documentation
    # only. le=86_400 is a managed-proxy 24-hour hard cap on client connection
    # lifetime, not an invented bound.
    pool_recycle: int = Field(default=-1, ge=-1, le=86_400)  # DATABASE__POOL_RECYCLE
    # Pure observability label attached to every backend as the PostgreSQL
    # application_name. It was unset project-wide, so the standard per-application
    # breakdown query collapsed every connection into one (blank) row.
    application_name: str = "mkobi-app"  # DATABASE__APPLICATION_NAME

    model_config = {"extra": "ignore"}

    @property
    def database_url(self) -> PostgresDsn:
        """Build PostgreSQL connection URL using asyncpg."""
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            path=self.dbname,
        )

    @field_validator("password")
    @classmethod
    def validate_password_not_placeholder(cls, v: str | None) -> str | None:
        """Reject placeholder passwords in production environments.

        In development, allows placeholder passwords for convenience.
        The environment check happens at Settings level (__init__ reads from env).

        Args:
            v: The password value to validate.

        Returns:
            str | None: The validated password value.

        Raises:
            ValueError: If password is a known placeholder value in production.
        """
        # Note: This validator runs before we know the environment.
        # Placeholder rejection for production is handled in Settings.DATABASE_URL property.
        return v

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password_strength(cls, v: str | None) -> str | None:
        """Validate admin password is not weak in production.

        Ensures admin password is at least 8 characters for security.

        Args:
            v: The admin password value to validate.

        Returns:
            str | None: The validated admin password value.

        Raises:
            ValueError: If admin password is less than 8 characters.
        """
        if v is not None and len(v) < ADMIN_PASSWORD_MIN_LENGTH:
            raise ValueError(
                "Admin password must be at least 8 characters for security"
            )
        return v

    @field_validator("pool_size")
    @classmethod
    def validate_pool_size_not_unbounded(cls, value: int) -> int:
        """Refuse pool_size=0, which is SQLAlchemy's unbounded sentinel.

        A pool_size of 0 does not mean "no pooling": it removes the cap and
        silently discards the configured max_overflow, so an operator writing 0
        for "no pooling" gets the opposite of what they intend. Use NullPool to
        express "no pooling".

        Args:
            value: The configured pool size.

        Returns:
            int: The validated pool size.

        Raises:
            ValueError: If pool size is the unbounded sentinel 0.
        """
        if value == 0:
            raise ValueError(
                "pool_size=0 is SQLAlchemy's unbounded sentinel, which also "
                "discards max_overflow. Use NullPool for no pooling."
            )
        return value


class JWTSettings(BaseModel):
    """JWT authentication settings."""

    secret_key: str | None = None
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_minutes: int = 10080

    # Weak secrets that should be rejected
    WEAK_SECRETS: ClassVar[set[str]] = {"password", "secret", "admin", "123456", "change_me", "default", "dev-secret-key-for-local-development", "change_me_in_production", "change_me_use_openssl_rand_hex_32"}

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str | None) -> str | None:
        """Validate JWT secret key strength.

        In production, ensures the secret is at least 32 characters
        and not a common weak value.
        """
        if v is None:
            return v
        if len(v) < 32:
            raise ValueError(
                "JWT secret key must be at least 32 characters for security"
            )
        if v.lower() in cls.WEAK_SECRETS:
            raise ValueError(
                "JWT secret key is too common. Please generate a strong secret."
            )
        return v


class RedisSettings(BaseModel):
    """Redis settings."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    # Bounds on a single socket operation. Without these the transport inherits
    # an undeclared library default: socket_timeout=5 with
    # Retry(ExponentialWithJitterBackoff(base=0.01, cap=1), retries=10), so a
    # Redis outage costs eleven 5-second attempts, about 59 s, per request. The
    # bound is declared here so the number is the project's, not the lockfile's.
    #
    # 1.0 s sits strictly below the reconciler lease's existing 2.0 s
    # asyncio.wait_for ceiling, so the inner socket bound is the one that fires
    # and the lease's outer guard can never be the ratchet. It is far above
    # normal in-subnet latency, so ordinary load is not reported as an outage.
    # The two fields are independent and both are set explicitly: a
    # socket_connect_timeout of None silently inherits socket_timeout, which
    # would couple the connect and read bounds into one number.
    socket_timeout_seconds: float = Field(default=1.0, gt=0, le=60)
    socket_connect_timeout_seconds: float = Field(default=1.0, gt=0, le=60)


# Secret-bearing fields, declared as (outer Settings field, model class, inner
# field names). SecretsFileSource derives their environment names from this
# registry so the allow-list cannot become a second, drifting copy of the field
# list. Extend a tuple to admit a field; add a triple to admit a model.
SECRET_FIELD_REGISTRY: Final[tuple[tuple[str, type[BaseModel], tuple[str, ...]], ...]] = (
    ("database", DatabaseSettings, ("password", "admin_user", "admin_password")),
    ("jwt", JWTSettings, ("secret_key",)),
    ("redis", RedisSettings, ("password",)),
)


@functools.cache
def _secret_field_env_names(settings_cls: type[BaseSettings]) -> frozenset[str]:
    """Derive the environment names the *_FILE source is allowed to honour.

    Names are derived from SECRET_FIELD_REGISTRY by reading the nesting rule
    from the settings model config, so the filter and _set_nested_value share
    one definition of the rule. Lazy and memoised because SecretsFileSource is
    declared before the models in this module: evaluating it at import time
    would raise NameError. Results are lower-cased because the settings model
    is case-insensitive (case_sensitive=False).

    Args:
        settings_cls: The settings class whose model config supplies the
            nested delimiter.

    Returns:
        frozenset[str]: Lower-cased environment names of secret-bearing fields.

    Raises:
        TypeError: If a registry entry names an outer Settings field that does
            not exist, or that no longer points at the expected model class, so
            drift is loud.
    """
    delimiter = settings_cls.model_config.get("env_nested_delimiter", "__")
    names: set[str] = set()
    for outer, model, inner_fields in SECRET_FIELD_REGISTRY:
        if outer not in settings_cls.model_fields:
            raise TypeError(
                f"Secret field registry names Settings.{outer}, which does not exist. "
                "Update SECRET_FIELD_REGISTRY."
            )
        outer_annotation = settings_cls.model_fields[outer].annotation
        if outer_annotation is not model:
            raise TypeError(
                f"Secret field registry expects Settings.{outer} to be {model.__name__}, "
                f"but it is {outer_annotation!r}. Update SECRET_FIELD_REGISTRY."
            )
        for inner in inner_fields:
            if inner not in model.model_fields:
                raise TypeError(
                    f"Secret field registry names {model.__name__}.{inner}, which does not exist."
                )
            names.add(f"{outer}{delimiter}{inner}".lower())
    return frozenset(names)


@functools.cache
def _all_field_env_names(settings_cls: type[BaseSettings]) -> frozenset[str]:
    """Derive every addressable environment name on the settings model.

    Symmetric with _secret_field_env_names but not limited to secrets: it walks
    each top-level field, using its alias when it declares one, and recurses
    into nested BaseModel fields. SecretsFileSource consults this set to tell a
    mis-set *_FILE name that resolves to an ordinary field (warning) from one
    that resolves to nothing at all (debug). Derived, never hand-written, so it
    cannot drift from the model. Lazy and memoised because SecretsFileSource is
    declared before the models in this module.

    Args:
        settings_cls: The settings class to walk.

    Returns:
        frozenset[str]: Lower-cased environment names of every addressable
            field path on the model.

    Raises:
        TypeError: If a secret-bearing name derived from SECRET_FIELD_REGISTRY
            is not present in the derived all-field set, so the two derivations
            cannot silently disagree.
    """
    delimiter = settings_cls.model_config.get("env_nested_delimiter", "__")

    def env_name(field_name: str, field_info: FieldInfo) -> str:
        # pydantic-settings resolves a field from its alias when one is set,
        # otherwise from its field name, and matching is case-insensitive here.
        return str(field_info.alias or field_name).lower()

    def walk(model: type[BaseModel], prefix: str) -> None:
        for field_name, field_info in model.model_fields.items():
            path = f"{prefix}{delimiter}{env_name(field_name, field_info)}"
            names.add(path)
            annotation = field_info.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                walk(annotation, path)

    names: set[str] = set()
    for field_name, field_info in settings_cls.model_fields.items():
        top = env_name(field_name, field_info)
        names.add(top)
        annotation = field_info.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            walk(annotation, top)

    # functools.cache keys its memo on Hashable arguments; a class object is
    # hashable at runtime but the cached callable's signature demands Hashable,
    # and this module's settings class resolves to type[Any] under the project's
    # mypy import policy. Cast the argument to the demanded type.
    missing = _secret_field_env_names(cast(Hashable, settings_cls)) - names
    if missing:
        raise TypeError(
            "Secret field registry names settings fields absent from the derived "
            f"all-field set: {sorted(missing)}. Update SECRET_FIELD_REGISTRY."
        )
    return frozenset(names)


class AppSettings(BaseModel):
    """Application settings."""

    name: str = "mkobi"
    # The advertised version has exactly one source: the installed
    # distribution's declared version, resolved through distribution_version().
    # This is a plain field name, not alias=, because AppSettings has no
    # populate_by_name and the environment name would otherwise be unreachable.
    version: str = Field(default_factory=distribution_version)
    # In production, always keep True. In development, set APP__COOKIE_SECURE=false
    # to allow HTTP cookies without TLS.
    cookie_secure: bool = Field(
        True,
        description="Secure flag for cookies. Set APP__COOKIE_SECURE=false for development.",
    )


class UploadSettings(BaseModel):
    """File upload settings."""

    temp_dir: str = Field(default="", alias="temp_dir")
    max_file_size_mb: int = Field(default=100, alias="max_file_size_mb")
    allowed_extensions: list[FileExtensionEnum] = [
        FileExtensionEnum.CSV_GZ,
        FileExtensionEnum.CSV,
    ]
    lazy_threshold_mb: float = 10.0

    model_config = {"populate_by_name": True}

    def __init__(self, **data: Any) -> None:
        """Initialize with platformdirs temp directory if not provided."""
        if "temp_dir" not in data or not data.get("temp_dir"):
            data["temp_dir"] = str(Path(user_data_dir("mkobi", "ZOO")) / "tmp_uploads")
        super().__init__(**data)


class DataSettings(BaseModel):
    """Aggregate-read bounds for the dashboard response.

    The aggregate read previously had no row bound. The read path allocates
    roughly ``3,402 B/row`` (linear; the 1,277 B/row floor after removing the
    eager ORM cascade is the raw JSONB payload), and the linear memory curve
    crosses the application's 1 GiB cgroup limit between 250,000 and 300,000
    rows. An uncapped read is therefore the defect; these two values bound it.

    Derivation of the defaults: ``20,000 rows x 3,402 B/row`` is roughly **68
    MB** for one dashboard response, which leaves comfortable headroom inside
    the 1 GiB application limit while ``--workers 4`` serve concurrently. The
    per-graph cap (``2,000``) keeps any single chart's payload small; the total
    cap (``20,000``) bounds the whole response. Truncation is never silent: the
    true, untruncated counts travel alongside the rows in the response.
    """

    # Maximum rows returned for a single graph in one dashboard response.
    max_rows_per_graph: int = Field(default=2_000, ge=0)
    # Maximum rows returned across the whole dashboard response.
    max_rows_total: int = Field(default=20_000, ge=0)


class FrontendSettings(BaseModel):
    """Frontend build settings.

    The built SPA bundle is served by app.py only when the configured directory
    exists and carries an ``index.html``. The location is configuration rather
    than a literal in two places, so the mount and the /health/detailed
    component can never disagree about which directory is served.
    """

    # Defaults to the CWD-relative value that was hard-coded before, so the
    # container's working directory and the served bundle are unchanged.
    dist_dir: str = Field(default="frontend/dist", alias="dist_dir")

    model_config = {"populate_by_name": True}


class EmailSettings(BaseModel):
    """Email settings."""

    blocked_domains: list[str] = ["tempmail.com", "throwaway.email"]


class LoggingSettings(BaseModel):
    """Logging settings."""

    level: str = "INFO"
    log_file: str | None = None
    json_logging: bool = True


class ChartsSettings(BaseModel):
    """Chart settings."""

    default_colors: list[str] = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
    ]

    class YOYSettings(BaseModel):
        """Year-over-year comparison settings."""

        class CurrentYearStyle(BaseModel):
            line: dict[str, Any] = {"dash": "solid", "width": 3}

        class PreviousYearStyle(BaseModel):
            line: dict[str, Any] = {"dash": "dash", "width": 2}

        current_year_style: CurrentYearStyle = CurrentYearStyle()
        previous_year_style: PreviousYearStyle = PreviousYearStyle()

    yoy: YOYSettings = YOYSettings()

    class LayoutSettings(BaseModel):
        template: str = "plotly_white"
        margin: dict[str, int] = {"l": 50, "r": 50, "t": 50, "b": 50}

    layout: LayoutSettings = LayoutSettings()


class Settings(BaseSettings):
    """Application configuration using pydantic-settings.

    All settings are loaded from environment variables, .env file,
    Docker secrets and YAML file with proper priority.
    """

    # --- App ---
    environment: EnvironmentEnum = Field(
        default=EnvironmentEnum.DEVELOPMENT, alias="ENV"
    )
    debug: bool = False
    app: AppSettings = AppSettings()
    email: EmailSettings = EmailSettings()

    # --- Database ---
    database: DatabaseSettings = DatabaseSettings()

    # --- JWT ---
    jwt: JWTSettings = JWTSettings()

    # --- Upload ---
    upload: UploadSettings = UploadSettings()

    # --- Data ---
    data: DataSettings = DataSettings()

    # --- Frontend ---
    frontend: FrontendSettings = FrontendSettings()

    # --- Redis ---
    redis: RedisSettings = RedisSettings()

    # --- Logging ---
    logging: LoggingSettings = LoggingSettings()

    # --- Charts ---
    charts: ChartsSettings = ChartsSettings()

    # --- CORS ---
    cors_origins: list[str] = []

    # --- Admin ---
    admin_username: str = Field(default="admin", alias="ADMIN_USERNAME")
    admin_password: str = Field(default="CHANGE_ME_ADMIN_PASSWORD", alias="ADMIN_PASSWORD")

    # --- Cleanup Settings ---
    logs_retention_days: int = Field(default=90, alias="LOGS_RETENTION_DAYS")
    stale_file_threshold_hours: int = Field(default=24, alias="STALE_FILE_THRESHOLD_HOURS")
    stale_processing_timeout_minutes: int = Field(default=30, alias="STALE_PROCESSING_TIMEOUT_MINUTES")
    stale_processing_cleanup_interval_seconds: int = Field(default=300, alias="STALE_PROCESSING_CLEANUP_INTERVAL_SECONDS")

# --- Rate Limiter ---
    rate_limiter_fail_closed: bool = Field(default=True, alias="RATE_LIMITER_FAIL_CLOSED")

    # --- Temp Password ---
    temp_password_ttl_seconds: int = Field(default=86400, alias="TEMP_PASSWORD_TTL_SECONDS")

    @field_validator("temp_password_ttl_seconds")
    @classmethod
    def validate_temp_password_ttl(cls, value: int) -> int:
        """Validate temp password TTL is at least 60 seconds.

        Args:
            value: TTL value in seconds.

        Returns:
            int: Validated TTL value.

        Raises:
            ValueError: If TTL is less than 60 seconds.
        """
        if value < 60:
            raise ValueError("TEMP_PASSWORD_TTL_SECONDS must be at least 60 seconds")
        return value

    @model_validator(mode="after")
    def validate_admin_credentials(self) -> "Settings":
        """Validate admin credentials are explicitly set in production.

        In production, default credentials are a security risk.
        This validator ensures they are explicitly set via environment variables.
        """
        if self.environment == EnvironmentEnum.PRODUCTION:
            # Reject an unusable username without echoing the value. The
            # exact-weak-member case keeps its established diagnosis; the
            # unset/placeholder case gets a distinct one that names the real
            # problem instead of calling it 'too common'.
            if is_weak_admin_username(self.admin_username):
                if is_weak_credential(self.admin_username, WEAK_USERNAMES):
                    raise ValueError(
                        "Admin username is too common. "
                        "Please choose a more secure username."
                    )
                raise ValueError(
                    "Admin username is unset or still a shipped placeholder "
                    "value. Set ADMIN_USERNAME to a real, unique username."
                )
            # Ordered most-specific first so an exact weak member keeps its message.
            if is_weak_admin_password(self.admin_password):
                if is_weak_credential(self.admin_password, WEAK_PASSWORDS):
                    raise ValueError(
                        "Admin password is too common. Please choose a more secure password."
                    )
                if is_placeholder_credential(self.admin_password):
                    raise ValueError(
                        "Admin password is a known placeholder value. "
                        "Set ADMIN_PASSWORD to a strong, unique password."
                    )
                if not self.admin_password.strip():
                    raise ValueError(
                        "Admin password must not be empty. "
                        "Set ADMIN_PASSWORD to a strong, unique password."
                    )
                raise ValueError(
                    "Admin password is too short. Please choose a stronger password."
                )
        else:
            # Log warning in development if defaults are used
            if is_weak_credential(self.admin_username, WEAK_USERNAMES):
                logger.warning(
                    "Using default admin username in %s environment - "
                    "set ADMIN_USERNAME for production use",
                    self.environment.value,
                )
            if is_weak_credential(self.admin_password, WEAK_PASSWORDS):
                logger.warning(
                    "Using default admin password in %s environment - "
                    "set ADMIN_PASSWORD for production use",
                    self.environment.value,
                )
        return self

    @model_validator(mode="after")
    def validate_debug_mode(self) -> "Settings":
        """Validate debug mode is disabled in production.

        Debug mode exposes sensitive information and should never be enabled
        in production environments for security reasons.
        """
        if self.debug and self.environment == EnvironmentEnum.PRODUCTION:
            raise ValueError("debug=True is not allowed in production environment")
        return self

    # --- Placeholder CORS origins that should never be used in production ---
    CORS_ORIGINS_PLACEHOLDERS: ClassVar[set[str]] = {
        "http://localhost:3000",
        "http://localhost:5173",
        "https://example.com",
        "https://your-domain.com",
    }

    @model_validator(mode="after")
    def validate_cors_origins_not_placeholder(self) -> "Settings":
        """Validate CORS origins do not contain placeholder values in production.

        In production, known placeholder values like '*' or example URLs would
        lead to misconfigured CORS and should be rejected with an error.
        Development and staging environments allow these for local workflows.
        """
        if self.environment == EnvironmentEnum.PRODUCTION:
            invalid_origins = [
                origin for origin in self.cors_origins
                if origin in self.CORS_ORIGINS_PLACEHOLDERS
            ]
            if invalid_origins:
                raise ValueError(
                    f"Placeholder CORS origins not allowed in production: {invalid_origins}. "
                    "Please set CORS_ORIGINS to your actual production domains."
                )
        return self

    @model_validator(mode="after")
    def validate_production_credentials(self) -> "Settings":
        """Reject known-weak credentials when running in production.

        Extends the existing validate_admin_credentials pattern to cover
        database passwords and JWT secrets. Fails fast on startup rather
        than allowing a production deployment with compromised credentials.
        """
        if self.environment == EnvironmentEnum.PRODUCTION:
            # Check database password against known-weak values.
            # The exact-set membership test stays first so an exact weak member
            # keeps its established message.
            db_password = self.database.password
            if db_password and is_weak_credential(db_password, WEAK_PASSWORDS):
                raise ValueError(
                    "DATABASE__PASSWORD is a known weak/placeholder value. "
                    "Set a strong password for production."
                )
            if db_password and is_placeholder_credential(db_password):
                raise ValueError(
                    "DATABASE__PASSWORD is a known placeholder value. "
                    "Set a strong password for production."
                )
            # Check the database admin password against the same placeholder
            # and emptiness clauses. It has no strength guard of its own beyond
            # the length check, so the shipped CHANGE_ME_* value would otherwise
            # pass production unexamined.
            db_admin_password = self.database.admin_password
            if db_admin_password is not None:
                if is_placeholder_credential(db_admin_password):
                    raise ValueError(
                        "DATABASE__ADMIN_PASSWORD is a known placeholder value. "
                        "Set a strong password for production."
                    )
                if not db_admin_password.strip():
                    raise ValueError(
                        "DATABASE__ADMIN_PASSWORD must not be empty. "
                        "Set a strong password for production."
                    )
            # Check JWT secret against known-weak values. The exact-set test
            # stays first for the same reason.
            jwt_secret = self.jwt.secret_key
            if jwt_secret and is_weak_credential(jwt_secret, JWTSettings.WEAK_SECRETS):
                raise ValueError(
                    "JWT__SECRET_KEY is a known weak/placeholder value. "
                    "Generate a strong secret for production."
                )
            if jwt_secret and is_placeholder_credential(jwt_secret):
                raise ValueError(
                    "JWT__SECRET_KEY is a known placeholder value. "
                    "Generate a strong secret for production."
                )
        return self

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str], info: ValidationInfo) -> list[str]:
        """Validate CORS origins are proper http(s) URLs.

        In production a wildcard is refused outright, naming the wildcard and how
        to remove it. Every other tier drops the wildcard and non-http(s) entries
        with a warning, as before.

        Args:
            value: List of CORS origins (already parsed by pydantic-settings).
            info: Validation context; carries the already-validated environment.

        Returns:
            list[str]: Validated list of CORS origins. Invalid origins are filtered out
                and a warning is logged.

        Raises:
            ValueError: If the production tier configures a wildcard origin.
        """
        if not isinstance(value, list):
            return []
        if info.data.get("environment") == EnvironmentEnum.PRODUCTION:
            if any(str(origin) == "*" for origin in value):
                raise ValueError(
                    "CORS wildcard '*' is not allowed in production. "
                    "Remove '*' from CORS_ORIGINS and list your production domains explicitly."
                )
        validated: list[str] = []
        for origin in value:
            parsed = urlparse(str(origin))
            if parsed.scheme in ("http", "https") and parsed.netloc:
                validated.append(str(origin))
            else:
                logger.warning(
                    "Invalid CORS origin rejected: %r (must be http:// or https:// URL)",
                    origin,
                )
        return validated

    # --- Database Migrations ---
    auto_migrate: bool = False
    migration_script_path: str = "alembic"
    alembic_ini_path: str = "alembic.ini"
    recreate_test_db: bool = False

    model_config = {
        "env_prefix": "",
        "env_nested_delimiter": "__",
        "case_sensitive": False,
        "extra": "ignore",
        "env_file": ".env",
    }

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources with correct priority order.

        Priority (highest to lowest):
        1. Environment variables (DATABASE__PASSWORD, JWT__SECRET_KEY, etc.)
        2. Docker secrets files (DATABASE__PASSWORD_FILE -> /run/secrets/db_password)
        3. .env file (for development convenience)
        4. YAML config file (app.yaml)
        5. Default values from code

        Note: In pydantic-settings 2.x, the FIRST source in tuple has HIGHEST priority.
        """
        yaml_file_path = Path(__file__).parent / "settings" / "app.yaml"
        yaml_source = YamlConfigSettingsSource(
            settings_cls,
            yaml_file=yaml_file_path,
        )
        secrets_source = SecretsFileSource(settings_cls)
        # First source has highest priority
        return (
            env_settings,
            secrets_source,
            dotenv_settings,
            yaml_source,
            init_settings,
        )

    def __init__(self, **data: Any) -> None:
        """Initialize configuration and log settings (without secrets)."""
        super().__init__(**data)
        self._log_initialization()
        self._ensure_upload_dir()
        self._log_security_warnings()

    def _log_initialization(self) -> None:
        """Log configuration initialization without exposing secrets."""
        logger.info(
            "Configuration loaded: env=%s, database_host=%s, redis_host=%s",
            self.environment,
            self.database.host,
            self.redis.host,
        )
        if self.debug:
            logger.debug("Debug mode is enabled")

    def _ensure_upload_dir(self) -> None:
        """Create directory for temporary upload files if it doesn't exist."""
        upload_path = Path(self.upload.temp_dir)
        upload_path.mkdir(parents=True, exist_ok=True)

    def _log_security_warnings(self) -> None:
        """Log security warnings for weak/default credentials in non-production.

        Checks database password, admin credentials, and JWT secret against known
        weak values and logs warnings. Does not block startup - only alerts developers.
        """
        if self.environment == EnvironmentEnum.PRODUCTION:
            return

        # Check database password against known-weak values
        if self.database.password:
            if self.database.password.lower() in {p.lower() for p in WEAK_PASSWORDS}:
                logger.warning(
                    "Weak database password detected: DATABASE__PASSWORD uses a known "
                    "weak/placeholder value. Generate a strong password for production."
                )

        # Check admin credentials against known-weak values
        if self.admin_username.lower() in {u.lower() for u in WEAK_USERNAMES}:
            logger.warning(
                "Weak admin username detected: ADMIN_USERNAME uses a known weak value. "
                "Set a secure username for production use."
            )

        if self.admin_password.lower() in {p.lower() for p in WEAK_PASSWORDS}:
            logger.warning(
                "Weak admin password detected: ADMIN_PASSWORD uses a known "
                "weak/placeholder value. Set a secure password for production use."
            )

        # Check JWT secret against known-weak values
        if self.jwt.secret_key:
            if self.jwt.secret_key.lower() in {s.lower() for s in JWTSettings.WEAK_SECRETS}:
                logger.warning(
                    "Weak JWT secret detected: JWT__SECRET_KEY uses a known "
                    "weak/placeholder value. Generate a strong secret for production."
                )

    @property
    def DATABASE_URL(self) -> str | None:
        """Build PostgreSQL connection URL.

        Returns None in non-production if password is missing.
        Raises ValueError in production if password is missing or is a placeholder.
        """
        if not self.database.password:
            if self.environment == EnvironmentEnum.PRODUCTION:
                raise ValueError(
                    "DATABASE__PASSWORD is required in production. "
                    "Set DATABASE__PASSWORD environment variable."
                )
            return None
        if self.environment == EnvironmentEnum.PRODUCTION:
            if is_weak_credential(self.database.password, WEAK_PASSWORDS):
                raise ValueError(
                    "DATABASE__PASSWORD is a known placeholder value. "
                    "Set a strong password for production."
                )
        return str(self.database.database_url)

    @property
    def TEST_DATABASE_URL(self) -> str | None:
        """Construct test database URL from database settings with test dbname."""
        if not self.database.password:
            return None
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.database.user,
                password=self.database.password,
                host=self.database.host,
                port=self.database.port,
                path=self.database.test_dbname,
            )
        )

    @property
    def TEST_ADMIN_DATABASE_URL(self) -> str | None:
        """Construct admin connection URL for test database (re)creation.

        Uses postgres superuser credentials for CREATE DATABASE operations
        which require CREATEDB privilege that the application user lacks.
        """
        if not self.database.admin_password:
            return None
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.database.admin_user,
                password=self.database.admin_password,
                host=self.database.host,
                port=self.database.port,
                path="postgres",  # Connect to default postgres db for admin ops
            )
        )

    @property
    def test_database_url(self) -> str | None:
        """Alias for TEST_DATABASE_URL."""
        return self.TEST_DATABASE_URL

    @property
    def test_admin_database_url(self) -> str | None:
        """Alias for TEST_ADMIN_DATABASE_URL."""
        return self.TEST_ADMIN_DATABASE_URL

    @property
    def jwt_secret_key(self) -> str | None:
        """Alias for JWT_SECRET_KEY."""
        return self.jwt.secret_key

    @property
    def jwt_algorithm(self) -> str:
        """Alias for JWT_ALGORITHM."""
        return self.jwt.algorithm

    @property
    def upload_temp_dir(self) -> str:
        """Alias for UPLOAD_TEMP_DIR."""
        return self.upload.temp_dir

    @property
    def allowed_file_types(self) -> list[str]:
        """Return list of allowed file extensions."""
        return [ext.value for ext in self.upload.allowed_extensions]

    @property
    def lazy_threshold_mb(self) -> float:
        """Threshold in MB above which the loader builds the frame via scan_csv."""
        return self.upload.lazy_threshold_mb

    @property
    def frontend_dist_dir(self) -> str:
        """Alias for FRONTEND__DIST_DIR; the built SPA bundle location."""
        return self.frontend.dist_dir

    @property
    def max_file_size(self) -> int:
        """Return maximum file size in bytes."""
        return self.upload.max_file_size_mb * 1024 * 1024

    @property
    def log_level(self) -> str:
        """Alias for logging level."""
        return self.logging.level

    @property
    def log_file(self) -> str | None:
        """Alias for logging file."""
        return self.logging.log_file

    @property
    def admin_user(self) -> str:
        """Return admin username."""
        return self.admin_username

    @property
    def admin_pass(self) -> str:
        """Return admin password."""
        return self.admin_password


# Cached configuration instance
_settings: Settings | None = None


def get_config(*, reload: bool = False) -> Settings:
    """Return configuration instance.

    Uses singleton pattern with caching to ensure
    a single configuration source in the application.

    Args:
        reload: If True, force reload of configuration from environment.
            Primarily useful for testing with different configs.

    Returns:
        Settings: Configuration instance.
    """
    global _settings
    if _settings is None or reload:
        _settings = Settings()
    return _settings


def clear_config_cache() -> None:
    """Clear the cached configuration instance.

    Primarily useful for testing scenarios where different
    configuration instances need to be tested.
    """
    global _settings
    _settings = None
