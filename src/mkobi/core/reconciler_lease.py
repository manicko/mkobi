"""Redis-backed lease for the stale-processing reconciler.

Production runs the application with several uvicorn workers, so every worker
executes ``lifespan`` and would otherwise start its own copy of the periodic
reconciler and its own boot-time orphan repair. This lease elects a single
holder so exactly one replica sweeps.

The lease is a load-and-observability optimisation, never a correctness gate.
It fails **open**: a worker that cannot reach Redis still sweeps, because
``cleanup_stale_processing_logs`` is a monotone, idempotent ``UPDATE`` and
skipping it during a Redis outage would silently disable the only sweeper of
``PROCESSING`` rows. The distinction that matters is "cannot reach Redis"
(``UNREACHABLE``) versus "reached Redis and it is not mine" (``NOT_ACQUIRED``);
those two must never share a branch.
"""

import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from mkobi.models.enums import LeaseAcquisitionResult, ReconcilerLeaseState

logger = logging.getLogger(__name__)

# Key every replica contends for. A single well-known name is enough - there is
# only one reconciler in the application.
LEASE_KEY = "mkobi:reconciler:stale_processing:lease"

# Default lease lifetime. Kept comfortably below the reconciler interval so a
# crashed holder is replaced within one tick and a stale holder whose lease has
# lapsed never blocks a live one for long.
DEFAULT_LEASE_TTL_SECONDS = 90

# Explicit short budget for every Redis round-trip. redis-py's default retry
# backoff can push a single unguarded call past 50s; an unguarded SET NX in the
# event loop would stall startup and every request for that whole time. Budgets
# are therefore bounded well under the sweep interval.
ACQUIRE_TIMEOUT_SECONDS = 2.0
RENEW_TIMEOUT_SECONDS = 2.0
RELEASE_TIMEOUT_SECONDS = 2.0

# Compare-and-renew and compare-and-delete run as one server-side script so no
# other command can interleave between the token read and the write. A holder
# whose lease lapsed and was re-acquired by another replica must not renew or
# delete that replica's lease.
_LEASE_SCRIPTS: dict[str, str] = {
    "renew": (
        "if redis.call('GET', KEYS[1]) == ARGV[1] then "
        "return redis.call('EXPIRE', KEYS[1], ARGV[2]) "
        "else return 0 end"
    ),
    "release": (
        "if redis.call('GET', KEYS[1]) == ARGV[1] then "
        "return redis.call('DEL', KEYS[1]) "
        "else return 0 end"
    ),
}


@dataclass
class ReconcilerStatus:
    """Mutable snapshot of the reconciler's observable state.

    ``lifespan`` creates one instance per process, hands it to the loop, and
    reads it from the health endpoint. ``last_success_at`` advances whenever a
    sweep completes - including a tick that marked zero rows - so a dead loop is
    distinguishable from an idle one.
    """

    lease_state: ReconcilerLeaseState = ReconcilerLeaseState.UNKNOWN
    last_success_at: datetime | None = None
    last_swept_count: int = 0
    sweep_count: int = 0
    unprotected_ticks: int = 0
    _last_warning_at: datetime | None = field(default=None, repr=False)

    def record_success(self, marked_count: int) -> None:
        """Record a completed sweep tick.

        Args:
            marked_count: Rows the sweep moved to a terminal state, possibly 0.
        """
        self.last_success_at = datetime.now(UTC)
        self.last_swept_count = marked_count
        self.sweep_count += 1
        if self.lease_state == ReconcilerLeaseState.UNPROTECTED:
            self.unprotected_ticks += 1


class ReconcilerLease:
    """Exclusive, TTL-bounded lease guarding a single reconciler replica.

    The instance owns one long-lived async Redis client, mirroring the
    ``functools.cache``d ``get_rq_queue`` precedent for holding a single
    Redis-backed resource per process. The client is created via
    ``get_async_redis_client`` (which is not itself cached) and must be
    ``aclose()``d by the caller.
    """

    def __init__(
        self,
        client: aioredis.Redis,
        ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    ) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds
        self._token: str | None = None

    async def acquire(self) -> LeaseAcquisitionResult:
        """Try to take the lease for this replica.

        Returns:
            LeaseAcquisitionResult: ``ACQUIRED`` when the ``SET NX`` won,
                ``NOT_ACQUIRED`` when Redis was reached but the key is held by
                another replica, ``UNREACHABLE`` when Redis could not be
                contacted. The last two are deliberately distinct.
        """
        token = secrets.token_urlsafe(32)
        try:
            acquired = await asyncio.wait_for(
                self._client.set(
                    LEASE_KEY, token, nx=True, ex=self._ttl_seconds
                ),
                timeout=ACQUIRE_TIMEOUT_SECONDS,
            )
        except (RedisError, OSError, TimeoutError):
            self._token = None
            return LeaseAcquisitionResult.UNREACHABLE
        if acquired:
            self._token = token
            return LeaseAcquisitionResult.ACQUIRED
        self._token = None
        return LeaseAcquisitionResult.NOT_ACQUIRED

    async def renew(self) -> bool:
        """Extend this replica's lease if (and only if) it still holds it.

        Best-effort: any failure leaves the caller free to keep sweeping. A lost
        ownership (token mismatch) or an unreachable Redis both return ``False``
        and neither raises.

        Returns:
            bool: True when this replica's lease was extended.
        """
        if self._token is None:
            return False
        try:
            result = await asyncio.wait_for(
                self._client.eval(
                    _LEASE_SCRIPTS["renew"],
                    1,
                    LEASE_KEY,
                    self._token,
                    str(self._ttl_seconds),
                ),
                timeout=RENEW_TIMEOUT_SECONDS,
            )
        except (RedisError, OSError, TimeoutError):
            return False
        return int(result) == 1

    async def release(self) -> bool:
        """Best-effort, owner-checked release of this replica's lease.

        The compare-and-delete runs server-side, so a lease this replica lost and
        another replica re-acquired is left untouched. Never raises: a Redis error
        here must not break the caller's ``finally`` chain.

        Returns:
            bool: True when the owned key was deleted.
        """
        if self._token is None:
            return False
        token = self._token
        self._token = None
        try:
            result = await asyncio.wait_for(
                self._client.eval(
                    _LEASE_SCRIPTS["release"], 1, LEASE_KEY, token
                ),
                timeout=RELEASE_TIMEOUT_SECONDS,
            )
        except (RedisError, OSError, TimeoutError):
            return False
        return int(result) == 1

    async def aclose(self) -> None:
        """Close the underlying Redis client without raising."""
        try:
            await self._client.aclose()
        except (RedisError, OSError, TimeoutError):
            logger.debug("Failed to close reconciler lease Redis client", exc_info=True)

    @property
    def is_holder(self) -> bool:
        """Whether this replica currently holds the lease token."""
        return self._token is not None

    @property
    def ttl_seconds(self) -> int:
        """Lease lifetime granted on acquire and renewal, in seconds."""
        return self._ttl_seconds
