"""Tests for the declared, bounded, transaction-scoped rebuild exclusion.

Three concerns, in order: the pure key derivation (no database), the exclusion and
its bound against a real PostgreSQL (a harness-held lock plus a second session), and
the transaction scope of the ``lock_timeout`` (it must not survive the transaction
that set it).
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool

from mkobi.db.advisory_lock import (
    LOCK_TIMEOUT_SQLSTATE,
    acquire_dashboard_rebuild_lock,
    dashboard_rebuild_lock_key,
)


class TestDashboardRebuildLockKey:
    """Pure derivation: stable across processes, distinct per dashboard, in range."""

    def test_key_is_stable_across_repeated_calls(self):
        """The same UUID must yield the same key every time.

        The regression guard against ``hash()``: an unseeded hash is stable within a
        process but differs across the four ``uvicorn --workers 4`` replicas, so a
        derivation that is only stable in-process would also pass a naive equality
        assertion. Determinism across processes is exercised by the signed-range and
        distinctness checks below; this test pins within-process stability only.
        """
        dashboard_id = UUID("12345678-1234-5678-1234-567812345678")
        first = dashboard_rebuild_lock_key(dashboard_id)
        assert first == dashboard_rebuild_lock_key(dashboard_id)
        assert first == dashboard_rebuild_lock_key(UUID(str(dashboard_id)))

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
        session = session_maker()
        await session.begin()
        await acquire_dashboard_rebuild_lock(
            session, dashboard_id, task_id=None, timeout_ms=timeout_ms
        )
        return session

    async def _holder_still_locks(self, session_maker, dashboard_id) -> bool:
        """True while ``dashboard_id``'s advisory lock is still held by someone.

        A fresh session that tries the non-blocking form reports whether anyone holds
        the key, without waiting.
        """
        probe = session_maker()
        try:
            result = await probe.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": dashboard_rebuild_lock_key(dashboard_id)},
            )
            return not result.scalar_one()
        finally:
            await probe.rollback()
            await probe.close()

    async def test_bound_is_honoured_when_lock_is_held(self, async_session_maker):
        """A held lock makes the second session wait and then fail with ``55P03``."""
        dashboard_id = uuid4()
        holder = await self._acquire(async_session_maker, dashboard_id)

        waiter = async_session_maker()
        await waiter.begin()
        try:
            with pytest.raises(DBAPIError) as exc_info:
                await acquire_dashboard_rebuild_lock(
                    waiter, dashboard_id, task_id=None, timeout_ms=300
                )
            assert getattr(exc_info.value.orig, "sqlstate", None) == LOCK_TIMEOUT_SQLSTATE
            # The failed waiter must not have disturbed the holder.
            assert await self._holder_still_locks(async_session_maker, dashboard_id)
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
    """The ``lock_timeout`` bound must not survive the transaction that set it.

    The property is observable only when the **same backend** survives the end of the
    transaction. The conftest engine uses ``NullPool``, which closes the DBAPI
    connection as soon as the session returns it, so a post-transaction
    ``current_setting`` read on that session is served by a brand-new backend and
    reports ``0`` no matter what the implementation did - the same reason a
    fresh-session assertion would be vacuous. These tests therefore build a dedicated
    ``AsyncAdaptedQueuePool(pool_size=1, max_overflow=0)`` engine, end or abort the
    transaction, and read the setting on the session while its single pooled backend
    is still checked out. A bare ``SET lock_timeout`` leaks there and is caught; the
    transaction-scoped ``set_config(..., true)`` is not.
    """

    @pytest.fixture
    async def pooled_session_maker(self, setup_test_database):
        """A factory of one-connection pools so a backend survives the transaction end.

        Each call builds a new ``AsyncAdaptedQueuePool(pool_size=1, max_overflow=0)``
        engine over the test database and returns a session maker bound to it. A
        single-connection pool is deliberate: it guarantees the session's backend is the
        one that stays checked out, so a post-transaction ``current_setting`` read is
        served by the *same* backend that executed the transaction. Separate engines are
        used for the holder and the waiter of a contended test, because a pool of one
        connection cannot hand a second session a connection while the first holds it.
        """
        from tests.conftest import TEST_ASYNC_DB_URL

        engines = []
        makers = []

        def make() -> async_sessionmaker:
            engine = create_async_engine(
                TEST_ASYNC_DB_URL,
                echo=False,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=1,
                max_overflow=0,
            )
            engines.append(engine)
            maker = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            makers.append(maker)
            return maker

        try:
            yield make
        finally:
            for engine in engines:
                await engine.dispose()

    async def _read_lock_timeout(self, session: AsyncSession) -> str:
        """Read the bound as the backend sees it, not a fresh connection's default."""
        result = await session.execute(text("SELECT current_setting('lock_timeout')"))
        return result.scalar_one()

    async def test_no_leak_after_commit(self, pooled_session_maker):
        """After COMMIT the same backend must be back to ``lock_timeout = 0``."""
        session = pooled_session_maker()()
        await session.begin()
        await acquire_dashboard_rebuild_lock(
            session, uuid4(), task_id=None, timeout_ms=30_000
        )
        await session.commit()
        try:
            assert await self._read_lock_timeout(session) == "0"
        finally:
            await session.close()

    async def test_no_leak_after_aborted_lock_wait(self, pooled_session_maker):
        """The error path: a ``55P03``-aborted transaction must not leave the bound set.

        This is the case that distinguishes the two implementations. The transaction
        is aborted by a lock-timeout, so the failure is not merely a clean commit; a
        session-level ``SET`` that survived COMMIT would leave this backend bounded for
        every unrelated lock wait in the process.
        """
        dashboard_id = uuid4()
        holder = pooled_session_maker()()
        await holder.begin()
        await acquire_dashboard_rebuild_lock(
            holder, dashboard_id, task_id=None, timeout_ms=30_000
        )

        waiter = pooled_session_maker()()
        await waiter.begin()
        try:
            with pytest.raises(DBAPIError) as exc_info:
                await acquire_dashboard_rebuild_lock(
                    waiter, dashboard_id, task_id=None, timeout_ms=300
                )
            assert getattr(exc_info.value.orig, "sqlstate", None) == LOCK_TIMEOUT_SQLSTATE
        finally:
            await waiter.rollback()
            await holder.rollback()
            await holder.close()

        try:
            assert await self._read_lock_timeout(waiter) == "0"
        finally:
            await waiter.close()

