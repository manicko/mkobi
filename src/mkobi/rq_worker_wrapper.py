"""RQ worker startup wrapper with Redis connection retry logic.

Provides a connection wrapper that retries Redis connection on startup failures
with exponential backoff, allowing the RQ worker to gracefully handle temporary
Redis unavailability during container startup.
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
import rq
from rq.defaults import DEFAULT_WORKER_TTL
from rq.worker_registration import REDIS_WORKER_KEYS

from mkobi.config import get_config

logger = logging.getLogger(__name__)

# Maximum number of retry attempts for Redis connection
MAX_RETRIES = 3

# Base delay in seconds for exponential backoff
BASE_DELAY_SECONDS = 2

# A registered worker is considered dead once its last heartbeat is older than
# RQ's own worker TTL. RQ gives every worker hash a TTL of ``worker_ttl + 60``
# (default ``DEFAULT_WORKER_TTL + 60``) and refreshes it on each heartbeat, so a
# heartbeat older than the TTL means the hash itself has already expired: no
# live worker can produce it. This reuses RQ's own constant rather than an
# arbitrary timeout.
WORKER_LIVENESS_TTL_SECONDS = DEFAULT_WORKER_TTL


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


def check_worker_registered() -> bool:
    """Check that a live RQ worker is registered in the worker registry.

    Reads the RQ worker registry (the ``rq:workers`` set) rather than pinging
    Redis. A ping measures the broker from inside the worker container and is
    green even when the worker is dead, wedged, or sitting in a startup retry.

    A registered worker is considered alive when its id is a member of the
    ``rq:workers`` set and the worker hash still carries a ``last_heartbeat``
    timestamp no older than RQ's worker TTL. RQ's registry and heartbeat are the
    only fields ``heartbeat()`` / ``register()`` are guaranteed to keep: an
    expired-then-revived worker hash can legitimately contain ``last_heartbeat``
    and nothing else (see ``Worker.maintain_heartbeats``), so ``state`` and
    ``queues`` must not be required. The heartbeat age is judged against RQ's
    own TTL because the hash cannot outlive its TTL and every live worker
    refreshes it on a heartbeat.

    Returns:
        bool: True when at least one registered worker has a recent heartbeat.
    """
    connection = redis.Redis.from_url(_build_redis_url())
    try:
        worker_keys = connection.smembers(REDIS_WORKER_KEYS)
        if not worker_keys:
            logger.error("No RQ workers registered")
            return False

        now = datetime.now(UTC)
        max_age = timedelta(seconds=WORKER_LIVENESS_TTL_SECONDS)
        for worker_key in worker_keys:
            key = worker_key.decode() if isinstance(worker_key, bytes) else str(worker_key)
            raw_heartbeat = connection.hget(key, "last_heartbeat")
            heartbeat = _parse_heartbeat(raw_heartbeat)
            if heartbeat is None:
                logger.warning("Worker %r has no parsable last_heartbeat", key)
                continue
            if now - heartbeat <= max_age:
                return True
            logger.warning(
                "Worker %r heartbeat is stale by %ds", key, (now - heartbeat).total_seconds()
            )

        logger.error("No live RQ worker registered")
        return False
    finally:
        connection.close()


def _parse_heartbeat(value: Any) -> datetime | None:
    """Parse an RQ ``last_heartbeat`` Redis value into an aware UTC datetime.

    RQ stores the heartbeat as an ISO-8601 string with a ``Z`` suffix
    (``utcformat``). Returns None when the value is missing or malformed.
    """
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode()
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


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
