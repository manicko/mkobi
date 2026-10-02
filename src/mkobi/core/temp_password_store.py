"""Redis-backed one-time temporary password storage."""

import logging
from typing import Final

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_KEY_PREFIX: Final[str] = "temp_pwd:"


# --- Exceptions ---


class TempPasswordStoreUnavailableError(Exception):
    """Raised when the temporary-password store cannot be reached.

    A plain ``core``-level type: the store never imports the API or the error
    enum layer, matching the co-located exceptions in ``core/permissions.py``.
    """

    pass


class TempPasswordStore:
    """Redis-backed one-time temporary password storage.

    Passwords are stored with a TTL and deleted immediately upon retrieval.
    Uses Redis pipeline for atomic GET+DELETE to prevent TOCTOU races.

    The two write/read contracts deliberately differ. ``store`` fails open
    because by the time it runs the caller has already committed the credential
    and raising would destroy a real account; ``retrieve`` fails loud because a
    fault there costs nothing to surface and reporting "not found" is a lie the
    caller cannot detect. A caller that wants the fail-open behaviour must ask
    for it by handling the exception; the store never chooses it for them.
    """

    def __init__(self, redis_client: aioredis.Redis, ttl_seconds: int = 86400) -> None:
        """Initialize the temporary password store.

        Args:
            redis_client: Async Redis client instance.
            ttl_seconds: Time-to-live for stored passwords in seconds (default: 24 hours).
        """
        self._redis = redis_client
        self._ttl = ttl_seconds

    async def store(self, token: str, password: str) -> bool:
        """Store a temporary password under the given token with TTL.

        Fails open on Redis errors - logs the error but does not raise, and
        returns False so the caller can report the fault. ``True`` means no
        client-visible Redis error occurred; it is not proof that the value is
        durable and readable.

        Args:
            token: Unique token identifier for the password.
            password: The password to store temporarily.

        Returns:
            bool: True if the SET completed without raising, False if a Redis
                fault was caught and swallowed. Never raises.
        """
        key = f"{_KEY_PREFIX}{token}"
        try:
            await self._redis.set(key, password, ex=self._ttl)
            logger.info(
                "Temp password stored for token %s... (TTL=%ds)",
                token[:8],
                self._ttl,
            )
            return True
        except Exception as exc:
            logger.error("Failed to store temp password in Redis: %s", exc)
            return False

    async def retrieve(self, token: str) -> str | None:
        """Retrieve and delete a temporary password.

        Uses Redis pipeline for atomic GET+DELETE to prevent TOCTOU race conditions.

        Args:
            token: Unique token identifier to retrieve the password for.

        Returns:
            The stored password string, or None if the key is absent, already
            spent or expired.

        Raises:
            TempPasswordStoreUnavailableError: If the Redis pipeline faults. The
                store fails loud on a read so a caller can never mistake an
                outage for a missing or spent token.
        """
        key = f"{_KEY_PREFIX}{token}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.get(key)
                pipe.delete(key)
                results = await pipe.execute()
            password: str | None = results[0]
            if password is not None:
                logger.info("Temp password retrieved for token %s...", token[:8])
            else:
                logger.warning("Temp password not found for token %s...", token[:8])
            return password
        except Exception as exc:
            logger.error("Failed to retrieve temp password from Redis: %s", exc)
            raise TempPasswordStoreUnavailableError(
                "Temporary password store is temporarily unavailable"
            ) from exc