"""RQ worker startup wrapper with Redis connection retry logic.

Provides a connection wrapper that retries Redis connection on startup failures
with exponential backoff, allowing the RQ worker to gracefully handle temporary
Redis unavailability during container startup.
"""

import asyncio
import logging
import sys
from typing import Any

import redis
import rq
from rq.worker_registration import REDIS_WORKER_KEYS

from mkobi.config import get_config

logger = logging.getLogger(__name__)

# Maximum number of retry attempts for Redis connection
MAX_RETRIES = 3

# Base delay in seconds for exponential backoff
BASE_DELAY_SECONDS = 2

# Worker states that mean the worker is alive and consuming.
LIVE_WORKER_STATES = {"busy", "idle"}


def _build_redis_url() -> str:
    """Build the Redis URL from configuration.

    Returns:
        str: A redis:// URL built from RedisSettings host/port/db.
    """
    config = get_config()
    return f"redis://{config.redis.host}:{config.redis.port}/{config.redis.db}"


async def check_redis_connection(redis_url: str, max_retries: int = MAX_RETRIES) -> bool:
    """Check Redis connectivity with exponential backoff retry.

    Attempts to connect to Redis and pings it. Retries on connection failures
    using exponential backoff (2^attempt seconds).

    Args:
        redis_url: Redis connection URL (e.g., redis://redis:6379/0).
        max_retries: Maximum number of connection attempts.

    Returns:
        bool: True if connection successful, False otherwise.

    Raises:
        ConnectionError: If all retry attempts fail.
    """
    for attempt in range(max_retries):
        try:
            client = redis.Redis.from_url(redis_url)
            client.ping()
            client.close()
            if attempt > 0:
                logger.info(
                    "Redis connection established after %d attempt(s)",
                    attempt + 1,
                )
            return True
        except (ConnectionError, redis.ConnectionError, OSError) as e:
            if attempt < max_retries - 1:
                delay = BASE_DELAY_SECONDS ** attempt
                logger.warning(
                    "Redis connection attempt %d/%d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    max_retries,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Redis connection failed after %d attempts: %s",
                    max_retries,
                    e,
                )
                raise ConnectionError(
                    f"Failed to connect to Redis after {max_retries} attempts: {e}"
                ) from e
    return False


def check_worker_registered(queue_name: str = "default") -> bool:
    """Check that a live RQ worker is registered for the expected queue.

    Reads the RQ worker registry (the ``rq:workers`` set) rather than pinging
    Redis. A ping measures the broker from inside the worker container and is
    green even when the worker is dead, wedged, mis-subscribed, or sitting in a
    startup retry. This check fails when the registry is empty, and, for each
    registered worker hash, accepts only a live state (``busy`` or ``idle``)
    whose subscribed queues include the queue the producer enqueues into. It
    fails when no registered worker names the expected queue, which detects a
    producer/consumer split across different Redis databases or queue names.

    Args:
        queue_name: The queue the producer submits to.

    Returns:
        bool: True when at least one live worker consumes ``queue_name``.
    """
    connection = redis.Redis.from_url(_build_redis_url())
    try:
        worker_keys = connection.smembers(REDIS_WORKER_KEYS)
        if not worker_keys:
            logger.error("No RQ workers registered")
            return False

        for worker_key in worker_keys:
            key = worker_key.decode() if isinstance(worker_key, bytes) else str(worker_key)
            data = {
                _as_text(field): _as_text(value)
                for field, value in connection.hgetall(key).items()
            }
            state = data.get("state")
            queues = data.get("queues") or ""
            subscribed = [name for name in queues.split(",") if name]
            if state in LIVE_WORKER_STATES and queue_name in subscribed:
                return True

        logger.error(
            "No live RQ worker registered for queue %r", queue_name
        )
        return False
    finally:
        connection.close()


def _as_text(value: Any) -> str | None:
    """Decode a Redis value to text, tolerating bytes and None."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def main() -> None:
    """Entry point for the worker container healthcheck.

    Exits 0 when a live worker consumes the expected queue, 1 otherwise, so the
    container healthcheck observes the worker rather than the broker.
    """
    if check_worker_registered():
        sys.exit(0)
    sys.exit(1)


def start_rq_worker(redis_url: str | None = None) -> None:
    """Start RQ worker with Redis connection retry logic.

    Creates an RQ worker that connects to Redis. Retries the connection on startup
    failures with exponential backoff. This allows the worker to handle temporary
    Redis unavailability during container startup.

    Args:
        redis_url: Redis connection URL. If None, uses the URL from config.

    Raises:
        SystemExit: If Redis connection fails after all retries.
    """
    if redis_url is None:
        redis_url = _build_redis_url()

    try:
        # Run async connection check with retry
        asyncio.run(check_redis_connection(redis_url))
    except ConnectionError as e:
        logger.error("Unable to start RQ worker: %s", e)
        sys.exit(1)

    # Import data worker module (ensures task registration)
    import mkobi.workers.data_worker  # noqa: F401

    # RQ Worker uses Redis connection directly via URL
    queue = rq.Queue(connection=redis.Redis.from_url(redis_url))
    worker = rq.Worker([queue])
    worker.work()


if __name__ == "__main__":
    start_rq_worker()
