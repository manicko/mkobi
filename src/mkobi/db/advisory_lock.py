"""Declared, bounded, transaction-scoped advisory exclusion for aggregate rebuilds.

Two concurrent rebuilds of the same dashboard must not interleave: they clear and
rewrite the same ``aggregated_data`` rows, so the second one has to wait for the
first. Historically that exclusion was incidental - the rebuilders serialised on a
row lock that neither side declared - which left the wait unbounded, unlogged and
invisible. This module replaces the accident with an explicit per-dashboard
``pg_advisory_xact_lock`` and a configured bound on the wait.

The lock is transaction-scoped (the ``_xact_`` form), so PostgreSQL releases it at
transaction end on commit, on rollback and at session end on crash. It uses the
single-argument ``bigint`` form; the two-argument ``(int4, int4)`` form would force
an arbitrary 32/32 split of a key space the single-argument form gets for free by
prefixing a namespace into the hashed payload.

Rejected alternatives, one clause each:

- ``hash()`` - unseeded, so each process (four ``uvicorn --workers 4`` replicas plus
  ``rq-worker``) would take a *different* key and the exclusion would not exist.
- SQL-side ``hashtextextended`` - undocumented, collation-sensitive, and it disagrees
  with a Python-side derivation anyway.
- UUID truncation - lossy on the least-uniform bits of a v4 UUID, so distinct
  dashboards collide.
- ``pg_try_advisory_xact_lock`` - converts ordinary queueing into a hard failure,
  when the correct behaviour is for the second rebuilder to wait (boundedly).
- ``statement_timeout`` - not scoped to lock acquisition, so it would also abort a
  long but legitimate aggregation.
"""

import hashlib
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.config import get_config

logger = logging.getLogger(__name__)

# Namespace prefixed into every hashed payload. The Alembic migration lock lives in
# the same 2^64 advisory key space, so an unprefixed derivation could collide with it;
# naming the purpose keeps the two key spaces apart.
REBUILD_LOCK_NAMESPACE = "mkobi:aggregate-rebuild"

# PostgreSQL's ``lock_not_available`` SQLSTATE, raised when a ``lock_timeout`` elapses
# while waiting for a lock. Classification keys on this value rather than on the
# exception type because SQLAlchemy's asyncpg dialect maps only a handful of asyncpg
# exception classes and ``LockNotAvailableError`` is not among them, so
# ``isinstance(exc, OperationalError)`` is False for this error.
LOCK_TIMEOUT_SQLSTATE = "55P03"


def dashboard_rebuild_lock_key(dashboard_id: UUID) -> int:
    """Derive the advisory-lock key for a dashboard's aggregate rebuild.

    The key must be identical in every process (four ``uvicorn --workers 4`` replicas
    plus ``rq-worker``), so it is a stable digest and not ``hash()``, whose per-process
    salt would make each replica take a different lock.

    Args:
        dashboard_id: The dashboard whose rebuild is to be excluded.

    Returns:
        int: A signed int64-range advisory-lock key for this dashboard.

    Note:
        ``signed=True`` is load-bearing: asyncpg raises a hard ``DataError`` on an
        unsigned value above 2**63 - 1, it does not truncate. Big-endian is the
        correct reading of the digest bytes (``uuid.int`` is the big-endian form).
    """
    payload = f"{REBUILD_LOCK_NAMESPACE}:{dashboard_id}".encode()
    return int.from_bytes(
        hashlib.blake2b(payload, digest_size=8).digest(),
        byteorder="big",
        signed=True,
    )


async def acquire_dashboard_rebuild_lock(
    session: AsyncSession,
    dashboard_id: UUID,
    *,
    task_id: str | None = None,
    timeout_ms: int | None = None,
) -> None:
    """Take the transaction-scoped rebuild exclusion for a dashboard, with a bounded wait.

    Issues exactly two statements, in this order, inside the caller's already-open
    transaction: a transaction-scoped ``lock_timeout`` and then the advisory lock
    itself. It never opens, commits or rolls back a transaction and never consumes the
    return value of either statement.

    Args:
        session: The caller's session, already inside ``async with session.begin()``.
        dashboard_id: The dashboard whose rebuild is to be excluded.
        task_id: Optional job id, used only to correlate the wait log lines.
        timeout_ms: Wait bound in milliseconds. Defaults to
            ``get_config().database.lock_timeout_ms``.

    Raises:
        DBAPIError: If the bound elapses (SQLSTATE ``55P03``) or any other database
            error occurs while acquiring the lock.

    Note:
        Both statements must be issued inside the caller's ``async with
        session.begin():`` block. SQLAlchemy autobegins, so a statement issued before
        ``session.begin()`` raises ``InvalidRequestError: A transaction is already
        begun on this Session``. The lock must also not be taken outside that block:
        the worker's failure-compensation handler runs after ``session.begin()`` has
        exited and rolled back, and depends on the lock already being released.
    """
    bound_ms = timeout_ms if timeout_ms is not None else get_config().database.lock_timeout_ms
    lock_key = dashboard_rebuild_lock_key(dashboard_id)

    # ``set_config(..., true)`` is transaction-scoped. A bare ``SET lock_timeout``
    # survives COMMIT on the pooled connection and would then bound every unrelated
    # lock wait in this process; ``SET LOCAL`` cannot take a bind parameter, which is
    # the only reason ``set_config`` is used at all.
    await session.execute(
        text("SELECT set_config('lock_timeout', :value, true)"),
        {"value": f"{bound_ms}ms"},
    )

    logger.info(
        "Acquiring dashboard rebuild lock: dashboard_id=%s, task_id=%s, lock_key=%s, bound_ms=%s",
        dashboard_id,
        task_id,
        lock_key,
        bound_ms,
    )

    try:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )
    except DBAPIError as exc:
        if is_lock_timeout_error(exc):
            logger.warning(
                "Timed out waiting for dashboard rebuild lock after %sms: dashboard_id=%s, task_id=%s, lock_key=%s",
                bound_ms,
                dashboard_id,
                task_id,
                lock_key,
            )
        raise


def is_lock_timeout_error(error: BaseException) -> bool:
    """Return True when an exception is a PostgreSQL lock-timeout failure.

    Args:
        error: The exception to classify.

    Returns:
        bool: True if it is a ``DBAPIError`` whose driver error carries SQLSTATE
            ``55P03``; False otherwise.

    Note:
        The same state is also visible as ``.pgcode`` on the asyncpg error, but keying
        on ``sqlstate`` (read via ``getattr``, since ``orig`` is not guaranteed to
        expose the attribute) is the only portable form.
    """
    return (
        isinstance(error, DBAPIError)
        and getattr(error.orig, "sqlstate", None) == LOCK_TIMEOUT_SQLSTATE
    )
