"""RQ-backed task submission for data processing.

Single submission path for background work: jobs are enqueued onto a Redis-backed
RQ queue that the deployed ``rq-worker`` container consumes. This module is the
only place the RQ enqueue is written, so service modules never import ``rq``.
"""

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any

import redis
import rq

from mkobi.config import get_config
from mkobi.models.enums import ErrorCode
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

# Name of the RQ queue the producer enqueues into and the worker must subscribe
# to. This is the single shared definition: ``rq_worker_wrapper`` imports it so
# the producer and the consumer cannot diverge onto different queues.
DEFAULT_QUEUE_NAME = "default"


@functools.cache
def get_rq_queue() -> rq.Queue:
    """Return the cached RQ queue built from RedisSettings.

    The connection is created once per process so a request does not open a new
    Redis connection on every submission. Host, port, db and password all come
    from ``mkobi.config.RedisSettings`` so the producer and the consumer cannot
    silently diverge onto different Redis databases.

    Returns:
        rq.Queue: The queue the worker consumes from.
    """
    config = get_config()
    redis_settings = config.redis
    connection = redis.Redis(
        host=redis_settings.host,
        port=redis_settings.port,
        db=redis_settings.db,
        password=redis_settings.password,
    )
    return rq.Queue(DEFAULT_QUEUE_NAME, connection=connection)


async def enqueue_job(
    func: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> str:
    """Submit a job to the RQ queue.

    Args:
        func: Function to execute in the worker.
        *args: Positional arguments.
        **kwargs: Keyword arguments.

    Returns:
        str: RQ job ID returned by the queue.

    Raises:
        AppException: If enqueue fails.
    """
    try:
        queue = get_rq_queue()
        job = await asyncio.to_thread(queue.enqueue, func, *args, **kwargs)
        return str(job.id)
    except Exception as e:
        logger.error("Failed to enqueue job: %s", e)
        raise AppException(
            code=ErrorCode.FILE_PROCESSING_ERROR,
            detail=f"Failed to enqueue processing job: {e}",
        ) from e
