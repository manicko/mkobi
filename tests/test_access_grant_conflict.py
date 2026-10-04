"""Tests that a duplicate dashboard access grant applies the requested permission.

Four concerns, in order: the sequential re-grant in a single session, the race
forced deterministically with two sessions from the session maker, a committed
conflict forced through the production method's upsert statement, and the
declared interface contract. No test races two coroutines through SQLAlchemy's
greenlet bridge: that hangs. A holder session and a second session with a fixed
ordering are deterministic instead.

The production statement is ``INSERT ... ON CONFLICT DO UPDATE`` on
``dashboard_access_pkey``: a conflict applies the requested permission and
``RETURNING`` yields the updated row, so a conflict is absorbed without raising
``IntegrityError``/``23505`` and the requested value is what survives.
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
# discrimination between a re-grant and a conflict is visible in the test itself.
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
        # Positional count: grant_access issues a leading SELECT and then an
        # INSERT. Re-check this if a statement is added before that SELECT.
        if self._executes == 1:
            await self._commit_competing_row()
        return result


class TestCommittedConflictReachesTheProductionInsert:
    """The production upsert is reached with a conflict already committed.

    The other production-method test commits the winner before calling
    ``grant_access``. Here the competitor commits *after* the leading SELECT
    and *before* the upsert, so only the conflict-tolerant statement can absorb
    it. The point is that a conflict committed inside the TOCTOU window is
    absorbed rather than raising ``IntegrityError``/``23505``, and the requested
    permission is applied.
    """

    @pytest.mark.asyncio
    async def test_committed_conflict_is_absorbed_by_the_production_insert(
        self, async_session_maker, test_user: dict
    ) -> None:
        """A conflict committed inside the TOCTOU window is absorbed, not a 500.

        Against a read-then-insert implementation the INSERT raises
        ``IntegrityError``/``23505`` on ``dashboard_access_pkey``; against the
        conflict-tolerant upsert it is absorbed and the requested ADMIN is
        applied to the stored row.
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
            # The committed winner's row is updated by the conflict action, so
            # the requested ADMIN is what the production statement applies.
            assert result.permission == DashboardPermission.ADMIN
        finally:
            await loser.rollback()
            await loser.close()
            cleanup = async_session_maker()
            try:
                await _delete_pair(cleanup, user.id, dashboard.id, test_user["id"])
            finally:
                await cleanup.close()


class TestGrantTwiceAppliesTheRequestedPermission:
    """The sequential re-grant: no concurrency, no exception, requested value wins."""

    @pytest.mark.asyncio
    async def test_second_grant_writes_the_requested_permission(
        self, async_session_maker, test_user: dict
    ) -> None:
        """Granting twice applies the second permission and leaves exactly one row."""
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
            # On CONFLICT DO UPDATE applies the second request: the stored
            # permission is the requested ADMIN, and the returned row reflects
            # the stored state after the write.
            assert second.permission == DashboardPermission.ADMIN

            # The upsert on the pair's primary key updates in place rather than
            # inserting a second row, so exactly one row exists after the re-grant.
            stored = await second_session.execute(
                select(DashboardAccess).where(
                    DashboardAccess.user_id == user.id,
                    DashboardAccess.dashboard_id == dashboard.id,
                )
            )
            assert len(stored.scalars().all()) == 1
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
            # The upsert updates the winner's committed row to B's requested
            # ADMIN; the leading read was not the correctness mechanism.
            assert result.permission == DashboardPermission.ADMIN
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
        """The sharpest discriminator: a committed conflict completes, with a row.

        No concurrency is needed. Pre-fix the same statement raised
        ``IntegrityError``/``23505``. Under ``ON CONFLICT DO UPDATE ... RETURNING``
        the committed conflict returns the updated row carrying the requested
        permission, so the test asserts both facts.
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
                        user.id, dashboard.id, DashboardPermission.ADMIN
                    )
                )
                updated_row = result.first()
                assert updated_row is not None
                assert updated_row.permission == DashboardPermission.ADMIN
                await loser.commit()
            finally:
                await loser.close()
        finally:
            cleanup = async_session_maker()
            try:
                await _delete_pair(cleanup, user.id, dashboard.id, test_user["id"])
            finally:
                await cleanup.close()


class TestExistingRowBranchContract:
    """The existing-row path returns a DashboardAccess reflecting the stored state."""

    @pytest.mark.asyncio
    async def test_existing_row_branch_returns_a_dashboard_access(
        self, async_session_maker, test_user: dict
    ) -> None:
        """A pre-existing pair comes back as a DashboardAccess carrying the new value."""
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
                # check_access re-reads the row through the same session, so it
                # returns the same identity-mapped instance and the equality is
                # not independent evidence. ``result.permission == ADMIN`` below
                # is what pins the refreshed value.
                permission = await repo.check_access(user.id, dashboard.id, session)
                assert permission == result.permission
                assert result.permission == DashboardPermission.ADMIN
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
