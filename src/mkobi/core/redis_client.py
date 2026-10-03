import logging

import redis
import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from mkobi.config import get_config

logger = logging.getLogger(__name__)

# A code invariant, not a setting: the transport never retries a failed
# attempt. retries=0 means exactly one try (retries counts retries *after* the
# first attempt, so retries=0 is not "no attempts"), NoBackoff adds no delay,
# and a value below zero would retry forever. One pinned policy governs the
# connect, the handshake, the health ping and every command round-trip. It is
# deep-copied per client, so a single module-level instance is safe to share.
_NO_RETRY = Retry(NoBackoff(), 0)


def get_redis_client() -> redis.Redis:
    """Return synchronous Redis client based on application settings.

    Returns:
        redis.Redis: Synchronous Redis client instance.
    """
    config = get_config()
    logger.debug(
        "Initializing synchronous Redis client: host=%s, port=%s, db=%s",
        config.redis.host,
        config.redis.port,
        config.redis.db,
    )
    return redis.Redis(
        host=config.redis.host,
        port=config.redis.port,
        db=config.redis.db,
        password=config.redis.password,
        decode_responses=True,
        socket_timeout=config.redis.socket_timeout_seconds,
        socket_connect_timeout=config.redis.socket_connect_timeout_seconds,
        retry=_NO_RETRY,
    )


def get_async_redis_client() -> aioredis.Redis:
    """Return asynchronous Redis client based on application settings.

    Returns:
        redis.asyncio.Redis: Asynchronous Redis client instance.
    """
    config = get_config()
    logger.debug(
        "Initializing asynchronous Redis client: host=%s, port=%s, db=%s",
        config.redis.host,
        config.redis.port,
        config.redis.db,
    )
    return aioredis.Redis(
        host=config.redis.host,
        port=config.redis.port,
        db=config.redis.db,
        password=config.redis.password,
        decode_responses=True,
        socket_timeout=config.redis.socket_timeout_seconds,
        socket_connect_timeout=config.redis.socket_connect_timeout_seconds,
        retry=_NO_RETRY,
    )
