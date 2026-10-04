"""Security module for password hashing and JWT token handling."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import redis
import redis.asyncio as aioredis
from fastapi import Response
from jose import JWTError, jwt

from mkobi.config import get_config
from uuid import UUID

logger = logging.getLogger(__name__)


def _get_config() -> Any:
    """Get config with validation that JWT secret is configured.

    Returns the cached config singleton. Does not mutate the config.

    Raises:
        ValueError: If JWT__SECRET_KEY is not configured (production always has it set).
    """
    config = get_config()
    if config.jwt.secret_key is None:
        raise ValueError(
            "JWT__SECRET_KEY must be configured. "
            "Set JWT__SECRET_KEY environment variable."
        )
    return config


# Constants
SALT_ROUNDS: int = 12
MAX_PASSWORD_LENGTH: int = 72
BLACKLIST_PREFIX: str = "token_blacklist:"
REFRESH_TOKEN_BLACKLIST_PREFIX: str = "refresh_token_blacklist:"

# Cookie security defaults
COOKIE_HTTPONLY: bool = True
COOKIE_SAMESITE: str = "strict"
COOKIE_NAME: str = "mkobi_refresh_token"


class RevocationStoreUnavailableError(Exception):
    """Raised when the token revocation store cannot be read.

    This is a store fault, not a credential verdict: it says nothing about
    whether the token is valid or revoked, only that the store could not answer.
    Callers must map it to a dependency-outage response rather than to an
    authentication failure, so a degraded Redis does not become a mass logout.
    """

    pass


def _generate_jti() -> str:
    """Generate a unique JWT ID for token identification.

    Returns:
        str: Unique identifier string for JWT.
    """
    import secrets
    return secrets.token_urlsafe(32)


class RateLimiter:
    def __init__(self, redis_client: redis.Redis, fail_closed: bool = True) -> None:
        self._redis = redis_client
        self._fail_closed = fail_closed

    def check_rate_limit(
        self, key: str, max_attempts: int, ttl: int
    ) -> tuple[bool, int | None]:
        """Check if request is allowed under rate limit.

        Args:
            key: Unique identifier for rate limiting scope (e.g., user ID or IP).
            max_attempts: Maximum allowed attempts within the TTL window.
            ttl: Time-to-live in seconds for the rate limit key.

        Returns:
            Tuple of (allowed, retry_after_seconds). If rate limit exceeded,
            retry_after_seconds contains the remaining TTL for Retry-After header.
        """
        try:
            attempts = self._redis.get(key)
            if attempts is not None and int(str(attempts)) >= max_attempts:
                ttl_remaining = self._redis.ttl(key)
                logger.warning("Rate limit exceeded for key: %s", key)
                return False, ttl_remaining if ttl_remaining > 0 else ttl

            pipeline = self._redis.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, ttl)
            pipeline.execute()
            return True, None
        except Exception as e:
            logger.error("Rate limiter Redis error for key %s: %s", key, e)
            if self._fail_closed:
                logger.critical(
                    "Rate limiter FAIL-CLOSED: rejecting request for key %s "
                    "(Redis unavailable)",
                    key,
                )
                return False, ttl
            logger.warning(
                "Rate limiter fail-open: allowing request for key %s "
                "(Redis unavailable)",
                key,
            )
            return True, None


class AsyncRateLimiter:
    def __init__(self, redis_client: aioredis.Redis, fail_closed: bool = True) -> None:
        self._redis = redis_client
        self._fail_closed = fail_closed

    async def check_rate_limit(
        self, key: str, max_attempts: int, ttl: int
    ) -> tuple[bool, int | None]:
        """Check if request is allowed under rate limit.

        Args:
            key: Unique identifier for rate limiting scope (e.g., user ID or IP).
            max_attempts: Maximum allowed attempts within the TTL window.
            ttl: Time-to-live in seconds for the rate limit key.

        Returns:
            Tuple of (allowed, retry_after_seconds). If rate limit exceeded,
            retry_after_seconds contains the remaining TTL for Retry-After header.
        """
        try:
            attempts = await self._redis.get(key)
            if attempts is not None and int(str(attempts)) >= max_attempts:
                ttl_remaining = await self._redis.ttl(key)
                logger.warning("Rate limit exceeded for key: %s", key)
                return False, ttl_remaining if ttl_remaining > 0 else ttl

            async with self._redis.pipeline() as pipeline:
                await pipeline.incr(key)
                await pipeline.expire(key, ttl)
                await pipeline.execute()
            return True, None
        except Exception as e:
            logger.error("Rate limiter Redis error for key %s: %s", key, e)
            if self._fail_closed:
                logger.critical(
                    "Rate limiter FAIL-CLOSED: rejecting request for key %s "
                    "(Redis unavailable)",
                    key,
                )
                return False, ttl
            logger.warning(
                "Rate limiter fail-open: allowing request for key %s "
                "(Redis unavailable)",
                key,
            )
            return True, None


def _truncate_password(password: str) -> str:
    """Truncate password to 72 bytes (bcrypt limit) at character boundary.

    Bcrypt has a limitation on password length - 72 bytes.
    Truncation happens at character boundary to avoid splitting multi-byte UTF-8 characters.

    Args:
        password: Original password string.

    Returns:
        str: Password truncated to 72 bytes or less, preserving valid UTF-8.
    """
    encoded = password.encode("utf-8")
    if len(encoded) <= MAX_PASSWORD_LENGTH:
        return password

    # Truncate at character boundary to prevent invalid UTF-8 sequences
    truncated_chars = []
    current_byte_len = 0
    for char in password:
        char_byte_len = len(char.encode("utf-8"))
        if current_byte_len + char_byte_len > MAX_PASSWORD_LENGTH:
            break
        truncated_chars.append(char)
        current_byte_len += char_byte_len

    truncated = "".join(truncated_chars)
    truncated_byte_len = len(truncated.encode("utf-8"))
    logger.warning(
        "Password truncated from %d bytes to %d bytes (character boundary preservation)",
        len(encoded),
        truncated_byte_len,
    )
    return truncated


def hash_password(password: str) -> str:
    """Hash password using bcrypt.

    Uses bcrypt algorithm with specified number of salt rounds (SALT_ROUNDS=12).
    Password is truncated to 72 bytes before hashing, as bcrypt has
    a limitation on maximum password length.

    Args:
        password: Password as a regular string.

    Returns:
        str: Password hash in bcrypt format.

    Example:
        >>> hash = hash_password("my_secure_password")
        >>> isinstance(hash, str)
        True
    """
    truncated_password = _truncate_password(password)
    password_bytes = truncated_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=SALT_ROUNDS)
    password_hash = bcrypt.hashpw(password_bytes, salt)
    logger.debug("Password hashed successfully")
    return password_hash.decode("latin-1")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password against hash.

    Compares provided password with stored bcrypt hash.
    Password is truncated to 72 bytes before verification.

    Args:
        password: Password as a regular string to verify.
        hashed_password: Password hash stored in database.

    Returns:
        bool: True if password matches hash, False otherwise.

    Example:
        >>> hash = hash_password("my_password")
        >>> verify_password("my_password", hash)
        True
        >>> verify_password("wrong_password", hash)
        False
    """
    truncated_password = _truncate_password(password)
    password_bytes = truncated_password.encode("utf-8")
    hash_bytes = hashed_password.encode("latin-1")
    try:
        result = bcrypt.checkpw(password_bytes, hash_bytes)
        if result:
            logger.debug("Password verified successfully")
        else:
            logger.warning("Password verification failed")
        return result
    except (ValueError, TypeError) as e:
        logger.error("Error verifying password: %s", e)
        return False


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """Create JWT access token with specified data.

    Token contains provided data, expiration time (exp), issued-at time (iat)
    in epoch milliseconds, and a jti (JWT ID) for token revocation support. The
    iat claim lets the user-level revocation marker decide whether a token
    predates a revocation.
    If expires_delta is not specified, uses value from config
    (default 30 minutes).

    Args:
        data: Data to include in the token (e.g., user_id, email).
        expires_delta: Additional token lifetime.
            If None, uses value from config.

    Returns:
        str: Encoded JWT token.

    Example:
        >>> token = create_access_token({"user_id": 1, "email": "user@example.com"})
        >>> isinstance(token, str)
        True
    """
    config = _get_config()
    to_encode = data.copy()
    # Convert UUID objects to strings for JWT serialization
    for key, value in to_encode.items():
        if isinstance(value, UUID):
            to_encode[key] = str(value)

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=config.jwt.access_token_expire_minutes
        )
    to_encode.update(
        {
            "exp": expire,
            "iat": int(datetime.now(UTC).timestamp() * 1000),
            "jti": _generate_jti(),
        }
    )
    secret_key = config.jwt.secret_key
    if secret_key is None:
        raise ValueError("JWT_SECRET_KEY must be configured")
    encoded_jwt: str = jwt.encode(
        to_encode,
        secret_key,
        algorithm=config.jwt.algorithm,
    )
    logger.info("JWT token created successfully")
    return encoded_jwt


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create JWT refresh token with extended expiration.

    Token contains provided data, expiration time (exp), issued-at time (iat)
    in epoch milliseconds, and a jti (JWT ID) for token revocation support. The
    iat claim lets the user-level revocation marker decide whether a token
    predates a revocation.
    Uses refresh_token_expire_minutes from config (default 7 days = 10080 minutes).

    Args:
        data: Data to include in the token (e.g., user_id, email).

    Returns:
        str: Encoded JWT refresh token.

    Example:
        >>> token = create_refresh_token({"user_id": 1, "email": "user@example.com"})
        >>> isinstance(token, str)
        True
    """
    config = _get_config()
    to_encode = data.copy()
    # Convert UUID objects to strings for JWT serialization
    for key, value in to_encode.items():
        if isinstance(value, UUID):
            to_encode[key] = str(value)

    expire = datetime.now(UTC) + timedelta(
        minutes=config.jwt.refresh_token_expire_minutes
    )
    to_encode.update(
        {
            "exp": expire,
            "iat": int(datetime.now(UTC).timestamp() * 1000),
            "jti": _generate_jti(),
        }
    )
    secret_key = config.jwt.secret_key
    if secret_key is None:
        raise ValueError("JWT_SECRET_KEY must be configured")
    encoded_jwt: str = jwt.encode(
        to_encode,
        secret_key,
        algorithm=config.jwt.algorithm,
    )
    logger.info("JWT refresh token created successfully")
    return encoded_jwt


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and validate JWT token.

    Verifies token signature and expiration time (exp).
    Returns None on decode or validation error.

    Args:
        token: JWT token to decode.

    Returns:
        dict[str, Any] | None: Decoded token data or None,
            if token is invalid.

    Example:
        >>> token = create_access_token({"user_id": 1})
        >>> data = decode_token(token)
        >>> data["user_id"]
        1
        >>> decode_token("invalid.token.here") is None
        True
    """
    config = _get_config()
    secret_key = config.jwt.secret_key
    if secret_key is None:
        raise ValueError("JWT_SECRET_KEY must be configured")
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            secret_key,
            algorithms=[config.jwt.algorithm],
        )
        logger.debug("JWT token decoded successfully")
        return payload
    except JWTError as e:
        logger.error("JWT token decode error: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected error decoding token: %s", e)
        return None


def validate_refresh_token(token: str) -> dict[str, Any] | None:
    """Validate a refresh token and return payload if valid.

    Verifies token signature and expiration time.
    Returns None for expired or invalid tokens.
    Used by the cookie-based refresh endpoint to extract user data.

    Args:
        token: JWT refresh token to validate.

    Returns:
        dict[str, Any] | None: Decoded token payload containing user_id,
            email, and role if valid; None if token is invalid or expired.
    """
    config = _get_config()
    secret_key = config.jwt.secret_key
    if secret_key is None:
        logger.warning("JWT_SECRET_KEY not configured for refresh token validation")
        return None
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            secret_key,
            algorithms=[config.jwt.algorithm],
        )
        logger.debug("Refresh token validated successfully")
        return payload
    except JWTError as exc:
        logger.warning("Invalid refresh token: %s", exc)
        return None
    except Exception as exc:
        logger.error("Unexpected error validating refresh token: %s", exc)
        return None


def set_secure_cookie(
    response: Response,
    key: str,
    value: str,
    max_age: int | None = None,
) -> None:
    """Set a secure cookie on the response.

    Uses security constants for httponly, secure, and samesite attributes.
    The secure attribute is configurable via environment variable.

    Args:
        response: FastAPI Response object to set cookie on.
        key: Cookie name.
        value: Cookie value.
        max_age: Cookie max age in seconds. If None, cookie becomes a session cookie.
    """
    config = get_config()
    response.set_cookie(
        key=key,
        value=value,
        httponly=COOKIE_HTTPONLY,
        secure=config.app.cookie_secure,
        samesite=COOKIE_SAMESITE,
        max_age=max_age,
    )


def delete_secure_cookie(response: Response, key: str) -> None:
    """Delete a cookie from the response.

    Uses security constants for httponly, secure, and samesite attributes.
    The secure attribute is configurable via environment variable.

    Args:
        response: FastAPI Response object to delete cookie from.
        key: Cookie name to delete.
    """
    config = get_config()
    response.delete_cookie(
        key=key,
        httponly=COOKIE_HTTPONLY,
        secure=config.app.cookie_secure,
        samesite=COOKIE_SAMESITE,
    )


# --- Token Revocation Functions ---


async def revoke_token(redis_client: aioredis.Redis, jti: str, expires_in_seconds: int) -> None:
    """Revoke a token by adding its jti to the Redis blacklist.

    Args:
        redis_client: Async Redis client.
        jti: JWT ID to revoke.
        expires_in_seconds: TTL for the blacklist entry in seconds.
    """
    key = f"{BLACKLIST_PREFIX}{jti}"
    await redis_client.setex(key, expires_in_seconds, "revoked")
    logger.info("Token revoked in blacklist: jti=%s", jti)


async def revoke_refresh_token(redis_client: aioredis.Redis, jti: str, expires_in_seconds: int) -> None:
    """Revoke a refresh token by adding its jti to the Redis blacklist.

    Args:
        redis_client: Async Redis client.
        jti: JWT ID to revoke.
        expires_in_seconds: TTL for the blacklist entry in seconds.
    """
    key = f"{REFRESH_TOKEN_BLACKLIST_PREFIX}{jti}"
    await redis_client.setex(key, expires_in_seconds, "revoked")
    logger.info("Refresh token revoked in blacklist: jti=%s", jti)


async def is_token_revoked(redis_client: aioredis.Redis, jti: str) -> bool:
    """Check if a token is revoked.

    Args:
        redis_client: Async Redis client.
        jti: JWT ID to check.

    Returns:
        bool: True if token is revoked, False otherwise.

    Raises:
        RevocationStoreUnavailableError: If the revocation store cannot be read.
    """
    key = f"{BLACKLIST_PREFIX}{jti}"
    try:
        exists = await redis_client.exists(key)
    except Exception as e:
        logger.error("Revocation store unavailable checking token jti=%s: %s", jti, e)
        raise RevocationStoreUnavailableError(
            "Token revocation store is unavailable"
        ) from e
    return bool(exists)


async def is_refresh_token_revoked(redis_client: aioredis.Redis, jti: str) -> bool:
    """Check if a refresh token is revoked.

    Args:
        redis_client: Async Redis client.
        jti: JWT ID to check.

    Returns:
        bool: True if token is revoked, False otherwise.

    Raises:
        RevocationStoreUnavailableError: If the revocation store cannot be read.
    """
    key = f"{REFRESH_TOKEN_BLACKLIST_PREFIX}{jti}"
    try:
        exists = await redis_client.exists(key)
    except Exception as e:
        logger.error(
            "Revocation store unavailable checking refresh token jti=%s: %s", jti, e
        )
        raise RevocationStoreUnavailableError(
            "Refresh token revocation store is unavailable"
        ) from e
    return bool(exists)


async def revoke_all_user_tokens(
    redis_client: aioredis.Redis, user_id: UUID, access_ttl: int, refresh_ttl: int
) -> None:
    """Revoke all tokens for a user by storing a timestamped revocation marker.

    The marker's value is the epoch **millisecond** at which the revocation
    happened. ``is_user_tokens_revoked`` compares a token's ``iat`` (also in
    epoch milliseconds) against it, so credentials issued before the marker are
    rejected while credentials issued afterwards (for example, after re-login)
    are accepted. Millisecond precision matters: at one-second granularity a
    re-login in the same second as the change would share the marker's instant
    and be rejected by the fail-closed comparison, so the two clocks must agree
    at a finer resolution than the requests they span.

    This is what distinguishes credential rotation from deactivation, where
    every future token is blocked by the ``is_active`` checks instead.

    Args:
        redis_client: Async Redis client.
        user_id: User ID whose tokens should be revoked.
        access_ttl: TTL for access token blacklist entries.
        refresh_ttl: TTL for refresh token blacklist entries.
    """
    key = f"user_tokens_revoked:{user_id}"
    # The marker only has to outlive the oldest still-presentable token, so the
    # longer TTL is sufficient; nothing issued after it is affected.
    ttl = max(access_ttl, refresh_ttl)
    revoked_at = int(datetime.now(UTC).timestamp() * 1000)
    await redis_client.setex(key, ttl, revoked_at)
    logger.info("All tokens revoked for user: id=%s", user_id)


async def is_user_tokens_revoked(
    redis_client: aioredis.Redis,
    user_id: UUID,
    issued_at: int | None = None,
) -> bool:
    """Check whether a credential predates the user's revocation marker.

    The marker stores the epoch millisecond of the revocation. A token is
    revoked only when its ``iat`` is at or before that instant; tokens issued
    later are already newer than the withdrawal and are allowed.

    Args:
        redis_client: Async Redis client.
        user_id: User ID to check.
        issued_at: The token's ``iat`` claim in epoch milliseconds, if available.

    Returns:
        bool: True if the credential must be rejected, False otherwise.

    Raises:
        RevocationStoreUnavailableError: If the revocation store cannot be read.
    """
    key = f"user_tokens_revoked:{user_id}"
    try:
        value = await redis_client.get(key)
    except Exception as e:
        logger.error(
            "Revocation store unavailable checking user marker user_id=%s: %s",
            user_id,
            e,
        )
        raise RevocationStoreUnavailableError(
            "User token revocation store is unavailable"
        ) from e
    if value is None:
        return False
    try:
        revoked_at = int(value)
    except (TypeError, ValueError):
        # Unknown value (for example a legacy "revoked" literal written by a
        # deployment that has not restarted). Fail closed so a rolling deploy
        # never re-admits sessions that were already withdrawn.
        logger.warning(
            "Unparseable user revocation marker; failing closed: user_id=%s",
            user_id,
        )
        return True
    if issued_at is None:
        # A credential that cannot be dated cannot be proven newer than the
        # revocation. Fail closed.
        return True
    return issued_at <= revoked_at
