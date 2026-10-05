"""Bounded, per-name exclusion for destructive test-database recreation.

Two concurrent pytest runs can each pass both recreation guards (the environment
tier gate and the test-name gate) and then both reach ``DROP DATABASE``. The
guards prove only that the *target name* is safe; they do not prove that another
process is not recreating the same name at the same moment. This module adds the
missing mutual exclusion.

The lock is **keyed by the database name**. Two runs recreating *different* test
databases are independent and must run in parallel, so they take different keys
and never wait on each other; only two runs that recreate the *same* name
serialise. That is exactly the collision this guards against, and it is the
collision the per-run name in ``tests/conftest.py`` is designed to avoid - see
the ``MKOBI_TEST_RUN_ID`` note there, which is the one way two runs can be forced
onto one name.

The wait is bounded and non-leaking, the same shape as
``db/advisory_lock.py``. The acquisition is a **single statement** against the
caller's autocommit admin connection (``DROP DATABASE`` cannot run inside a
transaction block, so that connection is AUTOCOMMIT):

.. code-block:: sql

    SELECT pg_advisory_lock(:key)
      FROM (SELECT set_config('lock_timeout', :value, true)) AS _bound

The ``FROM`` subquery is materialised before the target list is evaluated, so
``set_config`` runs first and the ``pg_advisory_lock`` wait is bounded by the
``lock_timeout`` it installs. ``set_config(..., true)`` is transaction-scoped,
so the bound resets at the end of that statement's implicit transaction and a
bare ``SET`` cannot outlive this acquisition on a pooled connection; ``SET LOCAL``
cannot take a bind parameter, which is the only reason ``set_config`` is used.
The lock is ``pg_advisory_lock`` (session-scoped), so it survives the implicit
transaction and is held until the explicit ``pg_advisory_unlock`` below, or, as a
backstop, until the connection closes.

``pg_advisory_xact_lock`` was rejected: a transaction-scoped lock would be
released before the destructive DROP/CREATE it is meant to exclude.
``pg_try_advisory_lock`` was rejected for the same reason as in
``db/advisory_lock.py``: it turns ordinary queueing into a hard failure when the
correct behaviour is for the second run to wait, boundedly.

The key lives in its **own key space**, prefixed into the hashed payload, so it
cannot collide with ``MIGRATION_ADVISORY_LOCK_KEY`` (42) or with the
dashboard-rebuild namespace.
"""

import hashlib
import logging

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from mkobi.config import get_config

logger = logging.getLogger(__name__)

# Namespace prefixed into every hashed payload. A separate key space from the
# Alembic migration lock (a fixed key) and from the rebuild namespace.
TEST_DB_RECREATE_LOCK_NAMESPACE = "mkobi:test-database-recreate"

# PostgreSQL's ``lock_not_available`` SQLSTATE, raised when a ``lock_timeout``
# elapses while waiting for a lock. Same value the rebuild module classifies on.
LOCK_TIMEOUT_SQLSTATE = "55P03"


def test_db_recreate_lock_key(db_name: str) -> int:
    """Derive the advisory-lock key for a test database's recreation.

    The key must be identical in every process that recreates the same name, so
    it is a stable digest and not ``hash()``, whose per-process salt would make
    each process take a different lock and remove the exclusion.

    Args:
        db_name: The already-parsed test database name.

    Returns:
        int: A signed int64-range advisory-lock key for this database name.

    Note:
        ``signed=True`` is load-bearing: asyncpg raises a hard ``DataError`` on an
        unsigned value above 2**63 - 1, it does not truncate.
    """
    payload = f"{TEST_DB_RECREATE_LOCK_NAMESPACE}:{db_name}".encode()
    return int.from_bytes(
        hashlib.blake2b(payload, digest_size=8).digest(),
        byteorder="big",
        signed=True,
    )


async def acquire_test_database_recreate_lock(
    connection: AsyncConnection,
    db_name: str,
    *,
    timeout_ms: int | None = None,
) -> None:
    """Take the per-name recreation exclusion, with a bounded wait.

    Issues exactly one statement against the caller's connection: a
    transaction-scoped ``lock_timeout`` (``set_config(..., true)``) feeding a
    session-scoped ``pg_advisory_lock`` in the same implicit transaction. It
    never opens, commits or rolls back a transaction of its own.

    Args:
        connection: The caller's connection. This is the autocommit admin
            connection, because the DROP/CREATE that follows needs AUTOCOMMIT.
        db_name: The database name whose recreation is to be excluded.
        timeout_ms: Wait bound in milliseconds. Defaults to
            ``get_config().database.lock_timeout_ms``.

    Raises:
        DBAPIError: If the bound elapses (SQLSTATE ``55P03``) or any other
            database error occurs while acquiring the lock.
    """
    bound_ms = timeout_ms if timeout_ms is not None else get_config().database.lock_timeout_ms
    lock_key = test_db_recreate_lock_key(db_name)

    logger.info(
        "Acquiring test-database recreation lock: db_name=%s, lock_key=%s, bound_ms=%s",
        db_name,
        lock_key,
        bound_ms,
    )

    try:
        await connection.execute(
            text(
                "SELECT pg_advisory_lock(:lock_key) "
                "FROM (SELECT set_config('lock_timeout', :value, true)) AS _bound"
            ),
            {"lock_key": lock_key, "value": f"{bound_ms}ms"},
        )
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == LOCK_TIMEOUT_SQLSTATE:
            logger.warning(
                "Timed out waiting for test-database recreation lock after %sms: "
                "db_name=%s, lock_key=%s",
                bound_ms,
                db_name,
                lock_key,
            )
        raise


async def release_test_database_recreate_lock(
    connection: AsyncConnection,
    db_name: str,
) -> None:
    """Release the per-name recreation exclusion taken by the acquire call.

    Best-effort: its own failure is logged, not raised. The lock is
    session-scoped, so the connection closing releases it anyway, and an
    exception here would replace the destructive path's own (more informative)
    exception.

    Args:
        connection: The same connection the lock was acquired on.
        db_name: The database name the lock was acquired for.
    """
    lock_key = test_db_recreate_lock_key(db_name)
    try:
        await connection.execute(
            text("SELECT pg_advisory_unlock(:lock_key)"),
            {"lock_key": lock_key},
        )
    except Exception as exc:
        logger.warning(
            "Failed to release test-database recreation lock %s for %s: %s; the "
            "connection closing releases session-scoped locks with it",
            lock_key,
            db_name,
            exc,
        )
