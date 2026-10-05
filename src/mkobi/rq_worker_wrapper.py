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
from urllib.parse import quote

import redis
import rq
from rq.defaults import DEFAULT_WORKER_TTL
from rq.worker_registration import REDIS_WORKER_KEYS

from mkobi.config import get_config
from mkobi.core.task_queue import DEFAULT_QUEUE_NAME
from mkobi.startup import WORKER_REQUIRED_MODULES, check_dependencies

logger = logging.getLogger(__name__)

# Maximum number of retry attempts for Redis connection
MAX_RETRIES = 3

# Base delay in seconds for exponential backoff
BASE_DELAY_SECONDS = 2

# A registered worker is considered dead once its last heartbeat is older than
# the worker hash's own TTL. RQ's ``Worker.heartbeat`` performs
# ``expire(self.key, worker_ttl + 60)`` (``timeout = timeout or
# self.worker_ttl + 60``), so a live hash can never carry a heartbeat older than
# ``worker_ttl + 60``: past that age the hash has already expired and no live
# worker can produce it. Judging the heartbeat against ``worker_ttl + 60`` rather
# than the bare ``worker_ttl`` also closes a false-negative margin - an idle
# worker's heartbeat is refreshed only once per dequeue iteration, whose timeout
# is ``worker_ttl - 15``, so a legitimately idle worker can present a heartbeat
# nearly ``worker_ttl`` seconds old.
WORKER_LIVENESS_TTL_SECONDS = DEFAULT_WORKER_TTL + 60


def _build_redis_url() -> str:
    """Build the Redis URL from configuration.

    Carries the password from the same ``RedisSettings`` the producer
    (``core.task_queue.get_rq_queue``) authenticates with, so the producer and
    the consumer cannot derive different credentials for the same store. A
    password is percent-encoded because URL-reserved characters would otherwise
    corrupt the userinfo section and make the derived URL unparseable.

    Returns:
        str: A ``redis://[:<password>@]<host>:<port>/<db>`` URL built from
        RedisSettings host/port/db and the optional password.
    """
    config = get_config()
    password = config.redis.password
    credentials = f":{quote(password, safe='')}@" if password else ""
    return (
        f"redis://{credentials}"
        f"{config.redis.host}:{config.redis.port}/{config.redis.db}"
    )


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
    timestamp no older than the hash's own TTL (``worker_ttl + 60``).

    The hash can legitimately contain ``last_heartbeat`` and nothing else. RQ's
    ``Worker.heartbeat`` is a bare single-field ``hset(self.key,
    'last_heartbeat', ...)`` which recreates the key when it has expired, and the
    idle path (``dequeue_job_and_maintain_ttl`` -> ``heartbeat``) has no recovery
    step that rewrites ``state`` or ``queues`` - only ``register_birth`` and
    ``maintain_heartbeats`` ever write those. So an expired-then-revived live
    worker has exactly a bare ``{last_heartbeat}`` hash and ``state`` / ``queues``
    must not be required.

    The heartbeat age is judged against ``worker_ttl + 60``: that is the TTL
    ``heartbeat`` itself sets on the key, so a heartbeat older than it proves the
    hash has already expired and no live worker can produce it.

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

    Exits 0 when a live RQ worker is registered with a fresh heartbeat, 1
    otherwise, so the container healthcheck observes the worker rather than the
    broker. The registry check does not verify which queue the worker consumes;
    that agreement is pinned by the shared queue-name constant.
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

    check_dependencies(WORKER_REQUIRED_MODULES)

    try:
        # Run async connection check with retry
        asyncio.run(check_redis_connection(redis_url))
    except ConnectionError as e:
        logger.error("Unable to start RQ worker: %s", e)
        sys.exit(1)

    # Import data worker module (ensures task registration)
    import mkobi.workers.data_worker  # noqa: F401

    # Consume the exact queue the producer enqueues into. Both sides read the
    # one shared constant, so a queue-name divergence cannot go undetected now
    # that the healthcheck no longer inspects the worker's ``queues`` field.
    queue = rq.Queue(DEFAULT_QUEUE_NAME, connection=redis.Redis.from_url(redis_url))
    worker = rq.Worker([queue])
    worker.work()


if __name__ == "__main__":
    start_rq_worker()
