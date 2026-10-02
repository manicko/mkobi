"""Tests that a duplicate dashboard access grant is the repository's own no-op.

Four concerns, in order: the sequential no-op contract in a single session, the
race forced deterministically with two sessions from the session maker, a
committed conflict forced through the production method's INSERT statement, and
the declared interface contract. No test races two coroutines through
SQLAlchemy's greenlet bridge: that hangs. A holder session and a second session
with a fixed ordering are deterministic instead.
"""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models import Dashboard, DashboardAccess, User
from mkobi.db.repositories.access_repo import (
    AccessRepository,
    _conflict_tolerant_access_insert,
)
from mkobi.interfaces.repository_interfaces import IAccessRepository
from mkobi.models.enums import DashboardPermission, UserRole

# The inverse of the grant endpoint's success status, kept explicit here so the
# discrimination between "no-op" and "conflict" is visible in the test itself.
_LOCK_TIMEOUT_SQLSTATE = "55P03"
_UNIQUE_VIOLATION_SQLSTATE = "23505"


async def _make_dashboard_and_user(session, owner_id: UUID) -> tuple[Dashboard, User]:
    """Create a committed dashboard and a second user for the pair to grant."""
    dashboard = Dashboard(
        name=f"grant-conflict-dashboard-{uuid4().hex[:8]}",
        created_by=owner_id,
    )
    user = User(
        email=f"grant_conflict_{uuid4().hex[:8]}@example.com",
        password_hash="hash",
        role=UserRole.VIEWER,
    )
    session.add_all([dashboard, user])
    await session.commit()
    return dashboard, user


async def _delete_pair(session, user_id: UUID, dashboard_id: UUID, owner_id: UUID) -> None:
    """Remove the rows a test committed, then its owner's user row is untouched."""
    await session.execute(
        delete(DashboardAccess).where(
            DashboardAccess.user_id == user_id,
            DashboardAccess.dashboard_id == dashboard_id,
        )
    )
    await session.execute(delete(Dashboard).where(Dashboard.id == dashboard_id))
    await session.execute(delete(User).where(User.id == user_id))
    await session.commit()


class _CommitConflictingRowAfterFirstExecute:
    """Session proxy that commits a competing row between two statements.

    The production ``grant_access`` issues a leading SELECT and then an INSERT,
    separated by an await point. A concurrent winner can commit inside that
    window; the leading SELECT cannot see an uncommitted row, so the method's
    INSERT is reached with the conflict already committed. This proxy forces
    that exact ordering on a single coroutine -- two coroutines are never raced
    through SQLAlchemy's greenlet bridge, which hangs -- while leaving the
    production class unmodified: it controls only *when* the competing commit
    happens, never the method's own statements. The SELECT still runs against
    the real session and returns nothing; the competing commit lands before the
    INSERT is issued.
    """

    def __init__(
        self,
        inner: AsyncSession,
        commit_competing_row: Callable[[], Awaitable[None]],
    ) -> None:
        self._inner = inner
        self._commit_competing_row = commit_competing_row
        self._executes = 0

    def __getattr__(self, name: str) -> Any:
        """Delegate every other attribute to the wrapped session unchanged."""
        return getattr(self._inner, name)

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Run the wrapped statement, then commit the competitor once."""
        result = await self._inner.execute(*args, **kwargs)
        self._executes += 1
        if self._executes == 1:
            await self._commit_competing_row()
        return result


class TestCommittedConflictReachesTheProductionInsert:
    """The production INSERT is reached with a conflict already committed.

    The other production-method test commits the winner before calling
    ``grant_access``, so the leading SELECT sees it and returns through the fast
    path -- it never reaches the INSERT and cannot detect a broken INSERT.
    Here the competitor commits *after* the leading SELECT and *before* the
    INSERT, so only the conflict-tolerant INSERT can absorb it.
    """

    @pytest.mark.asyncio
    async def test_committed_conflict_is_absorbed_by_the_production_insert(
        self, async_session_maker, test_user: dict
    ) -> None:
        """A conflict committed inside the TOCTOU window is a no-op, not a 500.

        Against a read-then-insert implementation the INSERT raises
        ``IntegrityError``/``23505`` on ``dashboard_access_pkey``; against the
        conflict-tolerant INSERT it is absorbed and the stored row is returned.
        """
        repo = AccessRepository()
        setup = async_session_maker()
        dashboard, user = await _make_dashboard_and_user(setup, test_user["id"])
        await setup.close()

        loser = async_session_maker()
        try:

            async def commit_competing_row() -> None:
                winner = async_session_maker()
                try:
                    await winner.execute(
                        _conflict_tolerant_access_insert(
                            user.id, dashboard.id, DashboardPermission.VIEW
                        )
                    )
                    await winner.commit()
                finally:
                    await winner.close()

            proxy = _CommitConflictingRowAfterFirstExecute(loser, commit_competing_row)
            result = await repo.grant_access(
                db=proxy,
                user_id=user.id,
                dashboard_id=dashboard.id,
                permission=DashboardPermission.ADMIN,
            )
            await loser.commit()

            assert isinstance(result, DashboardAccess)
            assert result.user_id == user.id
            assert result.dashboard_id == dashboard.id
            # The committed winner's permission survives; the requested ADMIN
            # never overwrites it.
            assert result.permission == DashboardPermission.VIEW
        finally:
            await loser.rollback()
            await loser.close()
            cleanup = async_session_maker()
            try:
                await _delete_pair(cleanup, user.id, dashboard.id, test_user["id"])
            finally:
                await cleanup.close()


class TestGrantTwiceIsANoOp:
    """The sequential duplicate: no concurrency, no exception, stored value wins."""

    @pytest.mark.asyncio
    async def test_second_grant_returns_the_stored_row_unchanged(
        self, async_session_maker, test_user: dict
    ) -> None:
        """Granting twice keeps the first permission and leaves exactly one row."""
        repo = AccessRepository()
        setup = async_session_maker()
        dashboard, user = await _make_dashboard_and_user(setup, test_user["id"])
        await setup.close()

        try:
            first_session = async_session_maker()
            try:
                first = await repo.grant_access(
                    db=first_session,
                    user_id=user.id,
                    dashboard_id=dashboard.id,
                    permission=DashboardPermission.VIEW,
                )
                await first_session.commit()
            finally:
                await first_session.close()

            second_session = async_session_maker()
            try:
                second = await repo.grant_access(
                    db=second_session,
                    user_id=user.id,
                    dashboard_id=dashboard.id,
                    permission=DashboardPermission.ADMIN,
                )
                await second_session.commit()
            finally:
                await second_session.close()

            assert isinstance(first, DashboardAccess)
            assert isinstance(second, DashboardAccess)
            assert second.user_id == user.id
            assert second.dashboard_id == dashboard.id
            # The no-op contract: the stored permission is the first request's,
            # never the requested downgrade/upgrade. On CONFLICT DO UPDATE would
            # flip this to ADMIN.
            assert second.permission == DashboardPermission.VIEW
        finally:
            cleanup = async_session_maker()
            try:
                await _delete_pair(cleanup, user.id, dashboard.id, test_user["id"])
            finally:
                await cleanup.close()

        verify = async_session_maker()
        try:
            result = await verify.execute(
                select(DashboardAccess).where(
                    DashboardAccess.user_id == user.id,
                    DashboardAccess.dashboard_id == dashboard.id,
                )
            )
            rows = result.scalars().all()
            assert rows == []
        finally:
            await verify.close()


class TestGrantAcrossTwoSessions:
    """The race, forced deterministically through the production statement.

    ``async_test_engine`` uses ``NullPool``, so the second session is a genuinely
    separate connection. Two coroutines are never raced through the greenlet bridge;
    the ordering is fixed by the test.
    """

    @pytest.mark.asyncio
    async def test_winning_insert_is_absorbed_by_the_loser(
        self, async_session_maker, test_user: dict
    ) -> None:
        """An uncommitted winner makes the loser wait, not fail, then re-read.

        Pre-fix, against ``db.add`` + the ORM insert, this same second statement
        is an ``IntegrityError``/``23505`` after the same wait: that is the defect.
        """
        setup = async_session_maker()
        dashboard, user = await _make_dashboard_and_user(setup, test_user["id"])
        await setup.close()

        winner = async_session_maker()
        loser = async_session_maker()
        try:
            await winner.begin()
            await winner.execute(
                _conflict_tolerant_access_insert(
                    user.id, dashboard.id, DashboardPermission.VIEW
                )
            )

            await loser.begin()
            # Bound the wait transaction-scoped, never with a bare SET (which
            # survives COMMIT on the pooled connection). The assertion runs on
            # the session that could have leaked.
            await loser.execute(
                text("SELECT set_config('lock_timeout', :value, true)"),
                {"value": "2000ms"},
            )
            with pytest.raises(DBAPIError) as exc_info:
                await loser.execute(
                    _conflict_tolerant_access_insert(
                        user.id, dashboard.id, DashboardPermission.VIEW
                    )
                )
            assert getattr(exc_info.value.orig, "sqlstate", None) == _LOCK_TIMEOUT_SQLSTATE
            assert not isinstance(exc_info.value, IntegrityError)
            assert _UNIQUE_VIOLATION_SQLSTATE not in str(exc_info.value)
            await loser.rollback()

            await winner.commit()

            rechecked = async_session_maker()
            try:
                result = await rechecked.execute(
                    select(DashboardAccess).where(
                        DashboardAccess.user_id == user.id,
                        DashboardAccess.dashboard_id == dashboard.id,
                    )
                )
                row = result.scalar_one_or_none()
                assert row is not None
                assert row.permission == DashboardPermission.VIEW
            finally:
                await rechecked.close()
        finally:
            await winner.rollback()
            await winner.close()
            await loser.close()
            cleanup = async_session_maker()
            try:
                await _delete_pair(cleanup, user.id, dashboard.id, test_user["id"])
            finally:
                await cleanup.close()

    @pytest.mark.asyncio
    async def test_loser_returns_the_winners_row_through_the_production_method(
        self, async_session_maker, test_user: dict
    ) -> None:
        """The TOCTOU window is forced, then the production method is called."""
        repo = AccessRepository()
        setup = async_session_maker()
        dashboard, user = await _make_dashboard_and_user(setup, test_user["id"])
        await setup.close()

        winner = async_session_maker()
        loser = async_session_maker()
        try:
            await winner.begin()
            await winner.execute(
                _conflict_tolerant_access_insert(
                    user.id, dashboard.id, DashboardPermission.EDIT
                )
            )

            # The forced TOCTOU window: the loser's SELECT cannot see the
            # winner's uncommitted row. This is why correctness cannot depend on
            # the leading read.
            await loser.begin()
            visible = await loser.execute(
                select(DashboardAccess).where(
                    DashboardAccess.user_id == user.id,
                    DashboardAccess.dashboard_id == dashboard.id,
                )
            )
            assert visible.scalar_one_or_none() is None
            await loser.commit()

            await winner.commit()

            result = await repo.grant_access(
                db=loser,
                user_id=user.id,
                dashboard_id=dashboard.id,
                permission=DashboardPermission.ADMIN,
            )
            await loser.commit()

            assert isinstance(result, DashboardAccess)
            # A's permission wins, not B's requested ADMIN.
            assert result.permission == DashboardPermission.EDIT
        finally:
            await winner.rollback()
            await winner.close()
            await loser.rollback()
            await loser.close()
            cleanup = async_session_maker()
            try:
                await _delete_pair(cleanup, user.id, dashboard.id, test_user["id"])
            finally:
                await cleanup.close()

    @pytest.mark.asyncio
    async def test_committed_conflict_is_absorbed_without_an_exception(
        self, async_session_maker, test_user: dict
    ) -> None:
        """The sharpest discriminator: a committed conflict returns no row, no error.

        No concurrency is needed. Pre-fix the same statement raises
        ``IntegrityError``/``23505``.
        """
        setup = async_session_maker()
        dashboard, user = await _make_dashboard_and_user(setup, test_user["id"])
        await setup.close()

        try:
            winner = async_session_maker()
            try:
                await winner.execute(
                    _conflict_tolerant_access_insert(
                        user.id, dashboard.id, DashboardPermission.VIEW
                    )
                )
                await winner.commit()
            finally:
                await winner.close()

            loser = async_session_maker()
            try:
                result = await loser.execute(
                    _conflict_tolerant_access_insert(
                        user.id, dashboard.id, DashboardPermission.VIEW
                    )
                )
                assert result.first() is None
                await loser.commit()
            finally:
                await loser.close()
        finally:
            cleanup = async_session_maker()
            try:
                await _delete_pair(cleanup, user.id, dashboard.id, test_user["id"])
            finally:
                await cleanup.close()


class TestNoOpBranchContract:
    """The defined no-op branch still exists and returns what the interface declares."""

    @pytest.mark.asyncio
    async def test_existing_row_branch_returns_a_dashboard_access(
        self, async_session_maker, test_user: dict
    ) -> None:
        """A pre-existing pair comes back as a DashboardAccess, unchanged."""
        repo = AccessRepository()
        setup = async_session_maker()
        dashboard, user = await _make_dashboard_and_user(setup, test_user["id"])
        await setup.close()

        first_session = async_session_maker()
        try:
            await repo.grant_access(
                db=first_session,
                user_id=user.id,
                dashboard_id=dashboard.id,
                permission=DashboardPermission.VIEW,
            )
            await first_session.commit()
        finally:
            await first_session.close()

        try:
            session = async_session_maker()
            try:
                result = await repo.grant_access(
                    db=session,
                    user_id=user.id,
                    dashboard_id=dashboard.id,
                    permission=DashboardPermission.ADMIN,
                )
                assert isinstance(result, DashboardAccess)
                permission = await repo.check_access(user.id, dashboard.id, session)
                assert permission == result.permission
                assert result.permission == DashboardPermission.VIEW
            finally:
                await session.close()
        finally:
            cleanup = async_session_maker()
            try:
                await _delete_pair(cleanup, user.id, dashboard.id, test_user["id"])
            finally:
                await cleanup.close()

    def test_declared_contract_matches_the_implementation(self) -> None:
        """The concrete method still overrides the interface and admits its return.

        The interface module is under ``ignore_errors = true`` in ``pyproject.toml``,
        so the type checker does not gate this; this comparison via ``inspect`` is
        the substitute evidence that the signature was not changed.
        """
        implementation = inspect.signature(AccessRepository.grant_access)
        declared = inspect.signature(IAccessRepository.grant_access)
        assert list(implementation.parameters) == list(declared.parameters)
        assert implementation.return_annotation is not inspect.Signature.empty
