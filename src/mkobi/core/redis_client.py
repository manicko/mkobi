import functools
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


@functools.cache
def get_redis_client() -> redis.Redis:
    """Return the process-wide synchronous Redis client.

    The client is built once per process and reused, so a request does not
    construct a new connection pool on every call. The connection pool is what
    is shared, not merely the pool object: redis-py multiplexes commands over
    the same socket until a blocking command forces a second connection. The
    cache is discarded by ``close_redis_client`` so a re-open is possible.

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


@functools.cache
def get_async_redis_client() -> aioredis.Redis:
    """Return the process-wide asynchronous Redis client.

    The client is built once per process and reused, so a request does not
    construct a new connection pool on every call. The connection pool is what
    is shared, not merely the pool object: redis-py multiplexes commands over
    the same socket, and an explicit pipeline crosses the wire in one round
    trip. The cache is discarded by ``close_async_redis_client`` so a re-open
    is possible after shutdown.

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


def close_redis_client() -> None:
    """Close and discard the cached synchronous Redis client.

    Closing releases the connection pool, and ``cache_clear`` drops the cached
    object so the next ``get_redis_client`` call builds a fresh one. Calling
    this when no client was ever created is a no-op.
    """
    if get_redis_client.cache_info().currsize:
        client = get_redis_client()
        client.close()
    get_redis_client.cache_clear()


async def close_async_redis_client() -> None:
    """Close and discard the cached asynchronous Redis client.

    Closing releases the connection pool, and ``cache_clear`` drops the cached
    object so the next ``get_async_redis_client`` call builds a fresh one.
    Calling this when no client was ever created is a no-op.
    """
    if get_async_redis_client.cache_info().currsize:
        client = get_async_redis_client()
        await client.aclose()
    get_async_redis_client.cache_clear()
