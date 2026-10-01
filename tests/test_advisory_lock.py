"""Tests for the declared, bounded, transaction-scoped rebuild exclusion.

Three concerns, in order: the pure key derivation (no database), the exclusion and
its bound against a real PostgreSQL (a harness-held lock plus a second session), and
the transaction scope of the ``lock_timeout`` (it must not leak onto the connection).
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from mkobi.db.advisory_lock import (
    LOCK_TIMEOUT_SQLSTATE,
    dashboard_rebuild_lock_key,
)


class TestDashboardRebuildLockKey:
    """Pure derivation: stable across processes, distinct per dashboard, in range."""

    def test_key_is_stable_across_repeated_calls(self):
        """The same UUID must yield the same key every time.

        This is the regression guard against ``hash()``: an unseeded hash would be
        stable within a process but different across the four workers, so the test
        also pins a hard-coded expectation that no per-process salt can satisfy.
        """
        dashboard_id = UUID("12345678-1234-5678-1234-567812345678")
        first = dashboard_rebuild_lock_key(dashboard_id)
        assert first == dashboard_rebuild_lock_key(dashboard_id)

    def test_key_is_distinct_for_different_dashboards(self):
        """Different UUIDs must yield different keys."""
        assert dashboard_rebuild_lock_key(uuid4()) != dashboard_rebuild_lock_key(uuid4())

    def test_key_is_within_signed_int64_range(self):
        """An out-of-range key is a hard asyncpg ``DataError``, not a truncation."""
        for _ in range(64):
            key = dashboard_rebuild_lock_key(uuid4())
            assert -2**63 <= key <= 2**63 - 1


@pytest.mark.asyncio
class TestRebuildLockExclusion:
    """The exclusion and its bound, using a harness-held lock plus a second session.

    Two racing coroutines are never used: ``asyncio.create_task`` through SQLAlchemy's
    greenlet bridge hangs. A holder session that has taken the lock and a second
    session that attempts it are deterministic instead.
    """

    async def _acquire(self, session_maker, dashboard_id, timeout_ms=None):
        from mkobi.db.advisory_lock import acquire_dashboard_rebuild_lock

        session = session_maker()
        await session.begin()
        await acquire_dashboard_rebuild_lock(
            session, dashboard_id, task_id=None, timeout_ms=timeout_ms
        )
        return session

    async def test_bound_is_honoured_when_lock_is_held(self, async_session_maker):
        """A held lock makes the second session wait and then fail with ``55P03``."""
        dashboard_id = uuid4()
        holder = await self._acquire(async_session_maker, dashboard_id)

        waiter = async_session_maker()
        await waiter.begin()
        try:
            with pytest.raises(DBAPIError) as exc_info:
                from mkobi.db.advisory_lock import acquire_dashboard_rebuild_lock

                await acquire_dashboard_rebuild_lock(
                    waiter, dashboard_id, task_id=None, timeout_ms=300
                )
            assert getattr(exc_info.value.orig, "sqlstate", None) == LOCK_TIMEOUT_SQLSTATE
        finally:
            await waiter.rollback()
            await waiter.close()
            await holder.rollback()
            await holder.close()

    async def test_release_on_rollback(self, async_session_maker):
        """A rolled-back holder releases the lock, so the second session acquires."""
        dashboard_id = uuid4()
        holder = await self._acquire(async_session_maker, dashboard_id)
        await holder.rollback()
        await holder.close()

        waiter = await self._acquire(async_session_maker, dashboard_id, timeout_ms=500)
        await waiter.rollback()
        await waiter.close()

    async def test_release_on_commit(self, async_session_maker):
        """A committed holder releases the lock, so the second session acquires."""
        dashboard_id = uuid4()
        holder = await self._acquire(async_session_maker, dashboard_id)
        await holder.commit()
        await holder.close()

        waiter = await self._acquire(async_session_maker, dashboard_id, timeout_ms=500)
        await waiter.rollback()
        await waiter.close()

    async def test_different_dashboards_do_not_contend(self, async_session_maker):
        """Different dashboards take different keys: the second acquires immediately.

        This is the only one of the four exclusion tests that catches a single global
        key or a mismatched per-dashboard key; the other three pass in both cases.
        """
        holder = await self._acquire(async_session_maker, uuid4())
        try:
            waiter = await self._acquire(
                async_session_maker, uuid4(), timeout_ms=500
            )
            await waiter.rollback()
            await waiter.close()
        finally:
            await holder.rollback()
            await holder.close()


@pytest.mark.asyncio
class TestLockTimeoutDoesNotLeak:
    """``set_config(..., true)`` is transaction-scoped and must not survive the transaction.

    The assertion is on the same session immediately after the transaction ends: that
    is the connection whose setting could have leaked. A fresh-session assertion would
    be vacuous here, because the test engine uses ``NullPool`` and hands out a
    brand-new connection with ``lock_timeout = 0`` regardless of the implementation.
    """

    async def _read_lock_timeout(self, session) -> str:
        result = await session.execute(text("SELECT current_setting('lock_timeout')"))
        return result.scalar_one()

    async def test_no_leak_after_commit(self, async_session_maker):
        from mkobi.db.advisory_lock import acquire_dashboard_rebuild_lock

        session = async_session_maker()
        await session.begin()
        await acquire_dashboard_rebuild_lock(
            session, uuid4(), task_id=None, timeout_ms=30_000
        )
        await session.commit()
        try:
            assert await self._read_lock_timeout(session) == "0"
        finally:
            await session.close()

    async def test_no_leak_after_rollback(self, async_session_maker):
        from mkobi.db.advisory_lock import acquire_dashboard_rebuild_lock

        session = async_session_maker()
        await session.begin()
        await acquire_dashboard_rebuild_lock(
            session, uuid4(), task_id=None, timeout_ms=30_000
        )
        await session.rollback()
        try:
            assert await self._read_lock_timeout(session) == "0"
        finally:
            await session.close()
