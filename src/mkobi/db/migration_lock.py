"""Bounded, logged, session-scoped exclusion for the Alembic migration run.

Two ``alembic upgrade head`` runs must not interleave on one schema: they would
execute DDL concurrently and race the single-row ``alembic_version`` upsert. The
run is therefore guarded by ``pg_try_advisory_lock``, a **session-scoped** lock
released when the connection closes or the backend exits. A blocked contender
retries a **bounded** number of times - 30 attempts at a fixed 10.0 s interval,
with no backoff - and every refusal is logged. A lock that cannot be acquired in
that window is a **refusal to migrate**, not a warning: the process exits non-zero
and the deployment stops.

Rejected alternatives, one clause each:

- ``pg_advisory_lock`` - the form this replaces: an unbounded, unlogged wait that
  offers no way to see, or bound, a contender queued behind a slow holder.
- ``lock_timeout`` - bounds every lock wait in the session, not only this one, and
  a migration legitimately exceeds a rebuild's bound.
- exponential backoff - one holder and no herd, so a wider window and two more
  constants would serve a case that does not exist here.
- warn-and-proceed - leaves the system with no exclusion at all in the only
  topology where the lock has any practical effect.
- ``pg_advisory_xact_lock`` - transaction-scoped; Alembic's own per-migration
  transactions would release it between revisions, so it would not exclude the run.

``db/advisory_lock.py`` owns the rebuild exclusion and derives its own key inside a
namespace, keeping that key space apart from the fixed key below; the two modules
deliberately do not share constants.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# Shared, deliberately-fixed advisory-lock key for the migration run. The value is
# unchanged from the historical definition and lives here so it is defined once.
MIGRATION_ADVISORY_LOCK_KEY = 42

# Bounded retry policy: 30 attempts at a fixed 10.0 s interval, no backoff, giving a
# total window of (30 - 1) x 10 s = 290 s (~4 m 50 s). ``DATABASE__LOCK_TIMEOUT_MS``
# is deliberately not reused: that value bounds one rebuild transaction, and one
# number with two meanings is worse than a second constant.
MIGRATION_LOCK_MAX_ATTEMPTS = 30
MIGRATION_LOCK_RETRY_INTERVAL_SECONDS = 10.0


async def retry_migration_lock_acquisition(
    try_acquire: Callable[[], Awaitable[bool]],
    *,
    max_attempts: int = MIGRATION_LOCK_MAX_ATTEMPTS,
    interval_seconds: float = MIGRATION_LOCK_RETRY_INTERVAL_SECONDS,
) -> bool:
    """Attempt to acquire the migration lock, retrying a bounded number of times.

    Each ``try_acquire`` call performs one non-blocking attempt and returns whether
    it got the lock. A refusal that will be retried is logged immediately, then the
    coroutine sleeps for the configured interval - fixed, with no backoff.

    Args:
        try_acquire: A coroutine performing one non-blocking acquisition attempt.
        max_attempts: Total attempts before giving up. The first refusal is logged at
            once; there is no sleep after the final attempt.
        interval_seconds: Fixed delay between attempts. Tests pass a short value.

    Returns:
        bool: ``True`` when the lock was acquired, ``False`` when every attempt was
            refused. It never raises for a refusal; the caller decides what a refusal
            means. Exceptions raised by ``try_acquire`` itself propagate - a broken
            connection is a real failure, not a held lock.

    Note:
        Only ``warning`` lines are emitted, because the root logger configuration in
        ``alembic.ini`` is ``WARNING`` and an ``info`` from this module would be
        silently dropped in a real migration run.
    """
    total_wait_seconds = interval_seconds * (max_attempts - 1)
    for attempt in range(1, max_attempts + 1):
        if await try_acquire():
            return True
        if attempt < max_attempts:
            logger.warning(
                "Migration advisory lock %s refused on attempt %s/%s; retrying in %ss",
                MIGRATION_ADVISORY_LOCK_KEY,
                attempt,
                max_attempts,
                interval_seconds,
            )
            await asyncio.sleep(interval_seconds)
    logger.warning(
        "Migration advisory lock %s refused after %s attempts (%ss waited). "
        "Not migrating: wait for the other migration to finish and re-run, "
        "or stop it if it is stuck.",
        MIGRATION_ADVISORY_LOCK_KEY,
        max_attempts,
        total_wait_seconds,
    )
    return False
