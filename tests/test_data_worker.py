"""Tests for data worker background functions."""
import asyncio
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import polars as pl

from mkobi.models.enums import (
    AggregationFunctionEnum,
    LeaseAcquisitionResult,
    ProcessingStatus,
    ReconcilerLeaseState,
    FilterType,
)
from mkobi.models.data import ProcessingConfig
from mkobi.core.reconciler_lease import (
    LEASE_KEY,
    ReconcilerLease,
    ReconcilerStatus,
)
from mkobi.db.advisory_lock import LOCK_TIMEOUT_SQLSTATE
from mkobi.utils.exceptions import AppException, ErrorCode
from mkobi.workers.data_worker import (
    DEFAULT_STALE_PROCESSING_TIMEOUT_MINUTES,
    _map_processing_error_to_code,
    _update_processing_log_status,
    cleanup_stale_processing_logs,
    mark_orphaned_uploaded_logs_failed,
    start_stale_processing_cleanup_task,
    _store_aggregates,
    _validate_processing_config,
)
from sqlalchemy.exc import DBAPIError


class FakeAsyncRedis:
    """Minimal in-memory async Redis double for lease tests.

    Implements only the commands the lease uses (``set`` with ``nx``/``ex`` and
    server-side ``eval``) plus a ``ttls`` map so ownership and TTL behaviour can
    be asserted directly. Setting ``fail_mode`` makes every command raise, which
    models an unreachable Redis.
    """

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._ttls: dict[str, int] = {}
        self.fail_mode = False
        self.closed = False

    def _check(self) -> None:
        if self.fail_mode:
            raise OSError("redis unavailable")

    async def set(self, key, value, nx=False, ex=None):
        self._check()
        if nx and key in self._data:
            return None
        self._data[key] = value
        if ex is not None:
            self._ttls[key] = ex
        return True

    async def get(self, key):
        self._check()
        return self._data.get(key)

    async def eval(self, script, numkeys, *args):
        self._check()
        key, token = args[0], args[1]
        current = self._data.get(key)
        if current != token:
            return 0
        if "DEL" in script:
            del self._data[key]
            self._ttls.pop(key, None)
            return 1
        ttl = int(args[2])
        self._ttls[key] = ttl
        return 1

    async def aclose(self) -> None:
        self.closed = True

    def expire_ttl(self, key=LEASE_KEY) -> None:
        """Simulate the key's TTL lapsing."""
        self._data.pop(key, None)
        self._ttls.pop(key, None)


@pytest.mark.asyncio
class TestReconcilerLoop:
    """Lease-guarded behaviour of the stale-processing reconciler loop."""

    @pytest.fixture
    def status(self):
        return ReconcilerStatus()

    @pytest.fixture
    def sweep_recorder(self):
        """Sweep double plus its call recorder.

        Patches the module-level ``cleanup_stale_processing_logs`` for the whole
        fixture lifetime, so the loop never opens a real database session and the
        tick behaviour is deterministic. The loop is driven with
        ``interval_seconds=0`` (a real, yielding ``asyncio.sleep(0)``) rather than
        by patching ``asyncio.sleep`` - patching that attribute is global to the
        ``asyncio`` module and would also neutralise the test's own yields.
        """
        calls: list[int] = []

        async def sweep(timeout_minutes=5, session=None):
            calls.append(len(calls))
            return 0

        with patch(
            "mkobi.workers.data_worker.cleanup_stale_processing_logs", new=sweep
        ):
            yield calls

    async def _run_for(self, ticks: int) -> None:
        """Drive the zero-interval loop forward by yielding the event loop.

        A real (tiny) timer rather than a bare ``sleep(0)``: the loop's own
        ``await`` competes with the test's, so a fixed number of zero-delay
        yields is not enough to guarantee a tick per yield.
        """
        for _ in range(ticks):
            await asyncio.sleep(0.005)

    async def _run_until(self, predicate, ticks: int = 200) -> bool:
        """Yield until ``predicate`` is true or the tick budget runs out."""
        for _ in range(ticks):
            if predicate():
                return True
            await asyncio.sleep(0.005)
        return predicate()

    async def _stop(self, task) -> None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_two_contenders_exactly_one_sweeps(
        self, status, sweep_recorder
    ):
        """Two independent contenders: exactly one wins and only it sweeps."""
        client = FakeAsyncRedis()
        winner_lease = ReconcilerLease(client)
        loser_lease = ReconcilerLease(client)

        contender_results: list[LeaseAcquisitionResult] = [
            await winner_lease.acquire(),
            await loser_lease.acquire(),
        ]
        assert contender_results.count(LeaseAcquisitionResult.ACQUIRED) == 1
        assert winner_lease.is_holder
        assert not loser_lease.is_holder

        # The winner's loop sweeps.
        winner_task = asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=0, lease=winner_lease, status=status
            )
        )
        try:
            assert await self._run_until(lambda: bool(sweep_recorder))
            assert status.lease_state == ReconcilerLeaseState.HOLDER
        finally:
            await self._stop(winner_task)

        # Start the loser against the still-held key with a clean recorder. It
        # reaches Redis but never owns the lease, so it must not sweep at all.
        sweep_recorder.clear()
        loser_task = asyncio.create_task(
            start_stale_processing_cleanup_task(interval_seconds=0, lease=loser_lease)
        )
        try:
            await self._run_for(60)
            assert sweep_recorder == [], "NOT_ACQUIRED must not sweep"
        finally:
            await self._stop(loser_task)

    async def test_recovery_after_holder_loss(self, status, sweep_recorder):
        """After the holder's lease lapses, another contender acquires - the loop is not wedged."""
        client = FakeAsyncRedis()
        first_lease = ReconcilerLease(client)
        second_lease = ReconcilerLease(client)

        assert await first_lease.acquire() == LeaseAcquisitionResult.ACQUIRED
        assert await second_lease.acquire() == LeaseAcquisitionResult.NOT_ACQUIRED

        # Holder stops renewing; after the TTL the key is gone and the second
        # contender wins on its next attempt.
        client.expire_ttl()
        assert await second_lease.acquire() == LeaseAcquisitionResult.ACQUIRED

        task = asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=0, lease=second_lease, status=status
            )
        )
        try:
            assert await self._run_until(lambda: bool(sweep_recorder))
            assert sweep_recorder, "recovered holder must sweep"
        finally:
            await self._stop(task)

    async def test_not_acquired_skips_but_unreachable_sweeps(
        self, status, sweep_recorder
    ):
        """The ruling: NOT_ACQUIRED skips the sweep, UNREACHABLE sweeps - as a pair."""
        # They are distinct values; the forbidden collapse cannot happen.
        assert LeaseAcquisitionResult.NOT_ACQUIRED != LeaseAcquisitionResult.UNREACHABLE

        holder_client = FakeAsyncRedis()
        assert await ReconcilerLease(holder_client).acquire() == LeaseAcquisitionResult.ACQUIRED

        # Share the held key with a contender that will reach Redis and lose.
        contender_lease = ReconcilerLease(holder_client)
        task = asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=0, lease=contender_lease, status=status
            )
        )
        try:
            await self._run_for(60)
            assert sweep_recorder == [], "NOT_ACQUIRED must not sweep"
            assert status.lease_state == ReconcilerLeaseState.NOT_HOLDER
        finally:
            await self._stop(task)

        # Now make Redis unreachable: the loop must fail open and sweep.
        unreachable_client = FakeAsyncRedis()
        unreachable_client.fail_mode = True
        unprotected_status = ReconcilerStatus()

        task = asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=0,
                lease=ReconcilerLease(unreachable_client),
                status=unprotected_status,
            )
        )
        try:
            assert await self._run_until(lambda: bool(sweep_recorder))
            assert sweep_recorder, "UNREACHABLE must fail open and sweep"
            assert unprotected_status.lease_state == ReconcilerLeaseState.UNPROTECTED
        finally:
            await self._stop(task)

    async def test_renewal_failure_does_not_kill_loop(
        self, status, sweep_recorder
    ):
        """Consecutive renewal failures: the sweep count still increments and the task lives."""
        lease = ReconcilerLease(FakeAsyncRedis())

        with patch.object(lease, "renew", new=AsyncMock(return_value=False)):
            task = asyncio.create_task(
                start_stale_processing_cleanup_task(
                    interval_seconds=0, lease=lease, status=status
                )
            )
            try:
                assert await self._run_until(lambda: len(sweep_recorder) >= 3)
                assert len(sweep_recorder) >= 3, "sweep must keep running after renewal failure"
                assert not task.done(), "renewal failure must not kill the loop"
                assert status.lease_state == ReconcilerLeaseState.UNPROTECTED
            finally:
                await self._stop(task)

    async def test_lost_lease_returns_to_election_and_stops_sweeping(
        self, status, sweep_recorder
    ):
        """After the lease is taken by another replica, the loop re-elects and stops.

        Regression guard for the never-re-entering latch. The lease is held, then
        a foreign replica replaces the key and this replica's renewal fails
        (``renew`` -> False). The loop must resolve whether it still owns the
        lease: since it does not, it must stop sweeping and report ``NOT_HOLDER``
        instead of sweeping unprotected forever while believing it is the holder.
        """
        client = FakeAsyncRedis()
        lease = ReconcilerLease(client)
        assert await lease.acquire() == LeaseAcquisitionResult.ACQUIRED

        task = asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=0, lease=lease, status=status
            )
        )
        try:
            # Let it take at least one real tick as the holder.
            assert await self._run_until(lambda: bool(sweep_recorder))

            # Another replica now owns the key, and this replica's renew fails.
            client._data[LEASE_KEY] = "foreign-token"
            with patch.object(lease, "renew", new=AsyncMock(return_value=False)):
                assert await self._run_until(
                    lambda: status.lease_state == ReconcilerLeaseState.NOT_HOLDER
                ), "the loop must detect that it lost the lease"
                assert status.lease_state == ReconcilerLeaseState.NOT_HOLDER
                assert not lease.is_holder
                # From the moment it detected the loss it must stop sweeping.
                settled_sweeps = len(sweep_recorder)
                await self._run_for(40)
                assert len(sweep_recorder) == settled_sweeps, (
                    "a replica that lost the lease must stop sweeping"
                )
                assert not task.done()
        finally:
            await self._stop(task)

    async def test_zero_row_tick_still_updates_last_success(
        self, status, sweep_recorder
    ):
        """A tick that marked 0 rows still advances last_success_at."""
        assert status.last_success_at is None
        lease = ReconcilerLease(FakeAsyncRedis())

        task = asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=0, lease=lease, status=status
            )
        )
        try:
            assert await self._run_until(lambda: status.last_success_at is not None)
            assert status.last_success_at is not None
            assert status.last_swept_count == 0
            assert status.sweep_count >= 1
        finally:
            await self._stop(task)


@pytest.mark.asyncio
class TestReconcilerLeaseOwnership:
    """Owner-checked renewal and release of the Redis lease."""

    async def test_renew_extends_owned_lease_and_is_owner_checked(self):
        client = FakeAsyncRedis()
        lease = ReconcilerLease(client, ttl_seconds=90)
        assert await lease.acquire() == LeaseAcquisitionResult.ACQUIRED
        assert client._ttls[LEASE_KEY] == 90

        # Foreign token in the key: renew must leave both key and TTL intact.
        client._data[LEASE_KEY] = "foreign-token"
        client._ttls[LEASE_KEY] = 11
        assert await lease.renew() is False
        assert client._data[LEASE_KEY] == "foreign-token"
        assert client._ttls[LEASE_KEY] == 11

    async def test_renew_with_correct_token_extends_ttl(self):
        client = FakeAsyncRedis()
        lease = ReconcilerLease(client, ttl_seconds=90)
        assert await lease.acquire() == LeaseAcquisitionResult.ACQUIRED
        client._ttls[LEASE_KEY] = 5  # model a partially elapsed TTL
        assert await lease.renew() is True
        assert client._ttls[LEASE_KEY] == 90

    async def test_release_is_owner_checked(self):
        client = FakeAsyncRedis()
        lease = ReconcilerLease(client)
        assert await lease.acquire() == LeaseAcquisitionResult.ACQUIRED

        # A foreign replica now owns the key.
        client._data[LEASE_KEY] = "foreign-token"
        assert await lease.release() is False
        assert client._data[LEASE_KEY] == "foreign-token"

    async def test_release_deletes_owned_key_immediately(self):
        client = FakeAsyncRedis()
        lease = ReconcilerLease(client)
        assert await lease.acquire() == LeaseAcquisitionResult.ACQUIRED
        assert await lease.release() is True
        assert LEASE_KEY not in client._data

    async def test_release_never_raises_on_redis_error(self):
        client = FakeAsyncRedis()
        lease = ReconcilerLease(client)
        assert await lease.acquire() == LeaseAcquisitionResult.ACQUIRED
        client.fail_mode = True
        assert await lease.release() is False


@pytest.mark.asyncio
class TestReconcilerLoopTask:
    """Tests for the worker module-level reconciler entry point."""


@pytest.mark.asyncio
class TestDataWorker:
    """Tests for data worker background functions."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock AsyncSession."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    # --- _update_processing_log_status tests ---

    async def test_update_processing_log_status_started(
        self, mock_session
    ):
        """Test updating status to PROCESSING adds started_at."""
        task_id = str(uuid4())
        mock_result = MagicMock()
        mock_result.rowcount = None
        mock_session.execute.return_value = mock_result

        test_started_at = datetime(2024, 1, 1, 12, 0, 0)
        await _update_processing_log_status(
            task_id=task_id,
            status=ProcessingStatus.PROCESSING,
            message="Processing started",
            started_at=test_started_at,
            session=mock_session,
        )

        # Verify execute was called once
        mock_session.execute.assert_called_once()

        # Verify the SQL statement contains correct values
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]

        # Check it's an UPDATE statement on ProcessingLog table
        assert stmt.is_update is True
        assert str(stmt.table.name) == "processing_logs"

        # Verify the values being set in the UPDATE statement
        stmt_values = dict(stmt._values)
        # Extract column name and value from BindParameter objects
        values_dict = {k.key: v.value for k, v in stmt_values.items()}
        assert values_dict["status"] == ProcessingStatus.PROCESSING
        assert values_dict["message"] == "Processing started"
        assert values_dict["started_at"] == test_started_at

        # Verify no commit in test mode (caller manages transaction)
        mock_session.commit.assert_not_called()

    async def test_update_processing_log_status_completed(
        self, mock_session
    ):
        """Test updating status to COMPLETED sets finished_at.

        In test mode (session provided), no commit happens - caller manages transaction.
        """
        task_id = str(uuid4())
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await _update_processing_log_status(
            task_id=task_id,
            status=ProcessingStatus.COMPLETED,
            message="Processing completed",
            session=mock_session,
        )

        # Verify execute was called once
        mock_session.execute.assert_called_once()

        # Verify the SQL statement contains correct values
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]

        # Check it's an UPDATE statement on ProcessingLog table
        assert stmt.is_update is True
        assert str(stmt.table.name) == "processing_logs"

        # Verify the values being set in the UPDATE statement
        stmt_values = dict(stmt._values)
        values_dict = {k.key: v.value for k, v in stmt_values.items()}
        assert values_dict["status"] == ProcessingStatus.COMPLETED
        assert values_dict["message"] == "Processing completed"
        # finished_at should be set (auto-generated by function)
        assert "finished_at" in values_dict
        assert values_dict["finished_at"] is not None

        # No commit in test mode - caller (SAVEPOINT) manages transaction
        mock_session.commit.assert_not_called()

    async def test_update_processing_log_status_failed(
        self, mock_session
    ):
        """Test updating status to FAILED sets finished_at.

        In test mode (session provided), no commit happens - caller manages transaction.
        """
        task_id = str(uuid4())
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        await _update_processing_log_status(
            task_id=task_id,
            status=ProcessingStatus.FAILED,
            message="Processing failed",
            session=mock_session,
        )

        mock_session.execute.assert_called_once()
        # No commit in test mode - caller (SAVEPOINT) manages transaction
        mock_session.commit.assert_not_called()

    async def test_update_processing_log_status_with_provided_finished_at(
        self, mock_session
    ):
        """Test finished_at can be explicitly provided."""
        task_id = str(uuid4())
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute.return_value = mock_result

        explicit_time = datetime(2024, 1, 1, 12, 0, 0)
        await _update_processing_log_status(
            task_id=task_id,
            status=ProcessingStatus.COMPLETED,
            message="Done",
            finished_at=explicit_time,
            session=mock_session,
        )

        mock_session.execute.assert_called_once()

    # --- cleanup_stale_processing_logs tests ---

    async def test_cleanup_stale_processing_logs_finds_stale_entries(
        self, mock_session
    ):
        """Test cleanup finds and marks stale PROCESSING entries."""
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result

        count = await cleanup_stale_processing_logs(
            timeout_minutes=30,
            session=mock_session,
        )

        assert count == 3
        mock_session.execute.assert_called_once()

    async def test_cleanup_stale_processing_logs_no_entries(
        self, mock_session
    ):
        """Test cleanup returns 0 when no stale entries found."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await cleanup_stale_processing_logs(session=mock_session)

        assert count == 0

    async def test_cleanup_stale_processing_logs_custom_timeout(
        self, mock_session
    ):
        """Test cleanup with custom timeout value."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        count = await cleanup_stale_processing_logs(
            timeout_minutes=60,
            session=mock_session,
        )

        assert count == 5

    # --- mark_orphaned_uploaded_logs_failed tests ---

    async def test_mark_orphaned_uploaded_logs_failed_finds_orphaned(
        self, mock_session
    ):
        """Test marking orphaned UPLOADED entries as FAILED."""
        mock_result = MagicMock()
        mock_result.rowcount = 2
        mock_session.execute.return_value = mock_result

        count = await mark_orphaned_uploaded_logs_failed(session=mock_session)

        assert count == 2
        mock_session.execute.assert_called_once()

    async def test_mark_orphaned_uploaded_logs_failed_no_entries(
        self, mock_session
    ):
        """Test marking returns 0 when no orphaned entries found."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        count = await mark_orphaned_uploaded_logs_failed(session=mock_session)

        assert count == 0

    # --- mark_orphaned_uploaded_logs_failed horizon tests ---

    @staticmethod
    def _cutoff_from_compiled_values(stmt) -> datetime:
        """Extract the bound ``started_at < cutoff`` value from the marker's UPDATE.

        ``cutoff`` is the right-hand operand of the WHERE comparison, not a
        column being set, so it is read from the clause comparing ``started_at``.
        """
        clauses = list(getattr(stmt.whereclause, "clauses", [stmt.whereclause]))
        for clause in clauses:
            left = getattr(clause, "left", None)
            if getattr(left, "key", None) == "started_at":
                return clause.right.value
        raise AssertionError("no started_at comparison found in the marker WHERE clause")

    async def test_mark_orphaned_uploaded_logs_failed_uses_the_configured_stale_processing_horizon(
        self, mock_session
    ):
        """No-argument call resolves its cutoff from the configured horizon.

        The cutoff must be ``Settings.stale_processing_timeout_minutes``, not the
        sweep's own ``DEFAULT_STALE_PROCESSING_TIMEOUT_MINUTES`` nor the retired
        one-minute literal. Those candidates are checked only when they actually
        differ from the configured value, so a developer environment that sets
        the horizon to 1 or 5 does not make this test fail.
        """
        from mkobi.config import get_config

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        configured = get_config().stale_processing_timeout_minutes
        # Candidates the cutoff must NOT be, minus any that coincide with the
        # configured value (the configured value is the only correct answer).
        stale_candidates = {
            candidate
            for candidate in (1, DEFAULT_STALE_PROCESSING_TIMEOUT_MINUTES, configured + 1)
            if candidate != configured
        }

        before = datetime.now(UTC)
        await mark_orphaned_uploaded_logs_failed(session=mock_session)
        after = datetime.now(UTC)

        stmt = mock_session.execute.call_args[0][0]
        cutoff = self._cutoff_from_compiled_values(stmt)

        assert before - timedelta(minutes=configured) <= cutoff <= after - timedelta(
            minutes=configured
        )
        for candidate in stale_candidates:
            assert not (
                before - timedelta(minutes=candidate)
                <= cutoff
                <= after - timedelta(minutes=candidate)
            ), f"cutoff matched stale candidate {candidate}, not the configured horizon"

    async def test_mark_orphaned_uploaded_logs_failed_explicit_override_wins(
        self, mock_session
    ):
        """An explicit ``timeout_minutes`` overrides the configured horizon."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        before = datetime.now(UTC)
        await mark_orphaned_uploaded_logs_failed(
            timeout_minutes=7, session=mock_session
        )
        after = datetime.now(UTC)

        stmt = mock_session.execute.call_args[0][0]
        cutoff = self._cutoff_from_compiled_values(stmt)

        assert before - timedelta(minutes=7) <= cutoff <= after - timedelta(minutes=7)


# --- _map_processing_error_to_code tests ---


class TestProcessingErrorClassification:
    """Classification of processing failures by the worker's error mapper.

    The mapper is code-first: an exception carrying a usable ``ErrorCode`` is
    classified by that code. Only exceptions with no usable code (a driver's
    ``SQLAlchemyError``, a Polars exception, a bare ``ValueError``) fall through
    to the documented substring table and then to the default.
    """

    @staticmethod
    def _dbapi_error(sqlstate: str) -> DBAPIError:
        """Build a DBAPIError whose driver error carries ``sqlstate``."""
        orig = MagicMock()
        orig.sqlstate = sqlstate
        return DBAPIError("stmt", {}, orig, connection_invalidated=False)

    def test_lock_timeout_maps_to_processing_in_progress(self):
        """A contended rebuild (55P03) is reported as in-progress, not failed."""
        error = self._dbapi_error(LOCK_TIMEOUT_SQLSTATE)
        assert _map_processing_error_to_code(error) == ErrorCode.PROCESSING_IN_PROGRESS.value

    def test_other_dbapi_error_still_maps_to_processing_failed(self):
        """Another sqlstate is untouched: the new branch is narrow."""
        error = self._dbapi_error("23505")
        assert _map_processing_error_to_code(error) == ErrorCode.PROCESSING_FAILED.value

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            # The finding: _validate_processing_config raises this AppException,
            # and the subclass's default detail ("Validation error") carries no
            # substring the old table matched, so it was overwritten with
            # PROCESSING_FAILED. Code-first must report the code it carries.
            pytest.param(
                AppException(code=ErrorCode.VALIDATION_ERROR, detail="Processing config has empty groupby column name"),
                ErrorCode.VALIDATION_ERROR,
                id="app_exception_validation_error",
            ),
            # A missing file is raised before CSVLoader.load_csv's blanket try:
            # block, so it reaches the mapper unwrapped as FileNotFoundError and
            # maps to FILE_UPLOAD_ERROR -- not "encoding" as the audit states.
            pytest.param(
                FileNotFoundError("File not found: /tmp/x.csv"),
                ErrorCode.FILE_UPLOAD_ERROR,
                id="file_not_found_error",
            ),
            # Code-less exception: the substring fallback still classifies it.
            pytest.param(
                ValueError("File too large: 200MB exceeds limit"),
                ErrorCode.FILE_TOO_LARGE,
                id="value_error_too_large_fallback",
            ),
            # An AppException carrying FILE_TOO_LARGE is classified by its code,
            # independent of message text.
            pytest.param(
                AppException(code=ErrorCode.FILE_TOO_LARGE, detail="nope"),
                ErrorCode.FILE_TOO_LARGE,
                id="app_exception_file_too_large",
            ),
            # Nothing to go on: default.
            pytest.param(
                RuntimeError("something went sideways"),
                ErrorCode.PROCESSING_FAILED,
                id="unclassifiable_default",
            ),
        ],
    )
    def test_map_processing_error_is_code_first_then_fallback(self, error, expected):
        """Every row of the (exception, code) table classifies as expected."""
        assert _map_processing_error_to_code(error) == expected.value

    def test_map_processing_error_emitted_codes_are_error_code_members(self):
        """Classifier output can never drift from the ErrorCode enum.

        Every code the mapper can emit is enumerated here explicitly; the test
        fails if the classifier grows a branch that returns a string which is
        not a member of ErrorCode.
        """
        emitted = [
            _map_processing_error_to_code(self._dbapi_error(LOCK_TIMEOUT_SQLSTATE)),
            _map_processing_error_to_code(AppException(code=ErrorCode.VALIDATION_ERROR, detail="x")),
            _map_processing_error_to_code(FileNotFoundError("x")),
            _map_processing_error_to_code(ValueError("File too large: x")),
            _map_processing_error_to_code(ValueError("encoding problem")),
            _map_processing_error_to_code(ValueError("failed to read csv parse")),
            _map_processing_error_to_code(ValueError("missing required columns")),
            _map_processing_error_to_code(ValueError("validation failed")),
            _map_processing_error_to_code(RuntimeError("unknown")),
        ]
        valid = {code.value for code in ErrorCode}
        assert set(emitted) <= valid, f"Unmapped codes emitted: {set(emitted) - valid}"


# --- _validate_processing_config tests ---


class TestValidateProcessingConfig:
    """Tests for _validate_processing_config function.

    Note: Pydantic models already validate required fields. These tests focus on
    custom validation for empty string values that pass Pydantic but are invalid
    for processing logic.
    """

    def test_valid_config_no_fields(self):
        """Test that config with no optional fields passes validation."""
        config = ProcessingConfig()
        _validate_processing_config(config)  # Should not raise

    def test_valid_config_with_valid_fields(self):
        """Test that config with valid fields passes validation."""
        config = ProcessingConfig(
            groupby=["category", "region"],
            sort_by=["year"],
            aggregations=[
                {"column": "revenue", "function": AggregationFunctionEnum.SUM},
            ],
            yoy_config={"year_column": "year", "value_column": "revenue_sum"},
            share_config={"value_column": "revenue_sum"},
            custom_metrics=[{"name": "profit", "expr": "revenue - cost"}],
        )
        _validate_processing_config(config)  # Should not raise

    def test_valid_config_with_dict_aggregations(self):
        """Test that config with dict-style aggregations passes validation."""
        config = ProcessingConfig(
            aggregations=[
                {"column": "revenue", "function": AggregationFunctionEnum.SUM},
            ],
        )
        _validate_processing_config(config)  # Should not raise

    def test_invalid_groupby_empty_string(self):
        """Test that groupby with empty string raises error."""
        config = ProcessingConfig(
            groupby=["category", ""],
        )
        with pytest.raises(AppException) as exc_info:
            _validate_processing_config(config)
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert "groupby" in exc_info.value.detail.lower()

    def test_invalid_sort_by_empty_string(self):
        """Test that sort_by with empty string raises error."""
        config = ProcessingConfig(
            sort_by=["year", ""],
        )
        with pytest.raises(AppException) as exc_info:
            _validate_processing_config(config)
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert "sort_by" in exc_info.value.detail.lower()

    def test_valid_metrics(self):
        """Test that metrics with valid entries passes validation."""
        config = ProcessingConfig(
            metrics=[{"name": "revenue", "type": "sum"}],
        )
        _validate_processing_config(config)  # Should not raise

    def test_invalid_metrics_empty_value(self):
        """Test that metrics with empty values raises error."""
        config = ProcessingConfig(
            metrics=[{"name": "", "type": "sum"}],
        )
        with pytest.raises(AppException) as exc_info:
            _validate_processing_config(config)
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR


# --- _store_aggregates tests ---


@pytest.mark.asyncio
class TestStoreAggregates:
    """Tests for _store_aggregates function."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock AsyncSession."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    async def test_store_aggregates_no_graphs(
        self, mock_session
    ):
        """Test _store_aggregates returns early when no graphs found."""
        df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        dashboard_id = uuid4()
        task_id = str(uuid4())

        # Mock result with no graphs
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await _store_aggregates(
            df=df,
            dashboard_id=dashboard_id,
            task_id=task_id,
            mode="overwrite",
            db_session=mock_session,
        )

        mock_session.execute.assert_called()

    async def test_store_aggregates_with_graphs(
        self, mock_session
    ):
        """Test _store_aggregates processes data when graphs exist."""
        from mkobi.models.enums import GraphType

        df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        dashboard_id = uuid4()
        task_id = str(uuid4())

        # Create mock Graph with valid type
        mock_graph = MagicMock()
        mock_graph.id = uuid4()
        mock_graph.name = "Test Graph"
        mock_graph.type = GraphType.BAR
        mock_graph.dashboard_id = dashboard_id
        mock_graph.config = {}
        mock_graph.dimensions = []
        mock_graph.metrics = []

        # Create mock Filter with valid type
        mock_filter = MagicMock()
        mock_filter.id = uuid4()
        mock_filter.name = "Test Filter"
        mock_filter.type = FilterType.SELECT
        mock_filter.config = {}
        mock_filter.created_at = datetime.now(UTC)

        # Create mock results for the execute calls (graph query, filter query)
        mock_graph_result = MagicMock()
        mock_graph_result.scalars.return_value.all.return_value = [mock_graph]

        mock_filter_result = MagicMock()
        mock_filter_result.scalars.return_value.all.return_value = [mock_filter]

        # For OVERWRITE mode, no get_aggregates call is needed
        mock_session.execute.side_effect = [mock_graph_result, mock_filter_result]

        # Patch the classes that are imported inside the function
        with patch(
            "mkobi.services.aggregation_service.AggregationService"
        ) as mock_agg_service, patch(
            "mkobi.data.storage.manager.StorageManager"
        ) as mock_storage, patch(
            "mkobi.db.repositories.dashboard_filter_values_repo.DashboardFilterValuesRepository"
        ) as mock_repo:
            mock_service_instance = AsyncMock()
            mock_service_instance.aggregate_for_dashboard = AsyncMock(
                return_value=[{"graph_id": mock_graph.id, "dims": {}, "metrics": {}}]
            )
            mock_service_instance.extract_filter_values = AsyncMock(return_value={})
            mock_agg_service.return_value = mock_service_instance

            mock_manager_instance = AsyncMock()
            mock_manager_instance.save_aggregates = AsyncMock(return_value=5)
            mock_storage.return_value = mock_manager_instance

            mock_repo_instance = AsyncMock()
            mock_repo_instance.save_filter_values = AsyncMock()
            mock_repo_instance.clear_dashboard_values = AsyncMock()
            mock_repo.return_value = mock_repo_instance

            await _store_aggregates(
                df=df,
                dashboard_id=dashboard_id,
                task_id=task_id,
                mode="overwrite",
                db_session=mock_session,
            )

            # Verify aggregate_for_dashboard called with correct arguments
            agg_call = mock_service_instance.aggregate_for_dashboard.call_args
            assert agg_call is not None, "aggregate_for_dashboard should have been called"
            assert agg_call[0][0] is df, "aggregate_for_dashboard should receive the DataFrame"
            assert agg_call[1]["metric_agg"] == "sum", "aggregate_for_dashboard should use default metric_agg='sum'"

            # Verify save_aggregates called with correct arguments
            save_call = mock_manager_instance.save_aggregates.call_args
            assert save_call is not None, "save_aggregates should have been called"
            assert save_call[1]["dashboard_id"] == dashboard_id, "save_aggregates should receive dashboard_id"
            assert save_call[1]["clear_old"] is True, "OVERWRITE mode should set clear_old=True"
            assert "aggregates" in save_call[1], "save_aggregates should receive aggregates list"
            aggregates_arg = save_call[1]["aggregates"]
            assert len(aggregates_arg) == 1, "aggregates should contain one record"

    async def test_store_aggregates_append_mode(
        self, mock_session
    ):
        """Test _store_aggregates uses append mode correctly (clear_old=False).

        Per SPEC.md, filter values are rebuilt on each upload (idempotent overwrite),
        so clear_dashboard_values must be called regardless of mode.
        """
        from mkobi.models.enums import GraphType

        df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        dashboard_id = uuid4()
        task_id = str(uuid4())

        mock_graph = MagicMock()
        mock_graph.id = uuid4()
        mock_graph.name = "Test Graph"
        mock_graph.type = GraphType.BAR
        mock_graph.dashboard_id = dashboard_id
        mock_graph.config = {}
        mock_graph.dimensions = []
        mock_graph.metrics = []

        mock_filter = MagicMock()
        mock_filter.id = uuid4()
        mock_filter.name = "Test Filter"
        mock_filter.type = FilterType.SELECT
        mock_filter.config = {}
        mock_filter.created_at = datetime.now(UTC)

        mock_graph_result = MagicMock()
        mock_graph_result.scalars.return_value.all.return_value = [mock_graph]

        mock_filter_result = MagicMock()
        mock_filter_result.scalars.return_value.all.return_value = [mock_filter]

        mock_session.execute.side_effect = [mock_graph_result, mock_filter_result] * 3

        with patch(
            "mkobi.services.aggregation_service.AggregationService"
        ) as mock_agg_service, patch(
            "mkobi.data.storage.manager.StorageManager"
        ) as mock_storage, patch(
            "mkobi.db.repositories.dashboard_filter_values_repo.DashboardFilterValuesRepository"
        ) as mock_repo:
            mock_service_instance = AsyncMock()
            mock_service_instance.aggregate_for_dashboard = AsyncMock(
                return_value=[{"graph_id": mock_graph.id, "dims": {}, "metrics": {}}]
            )
            mock_service_instance.extract_filter_values = AsyncMock(return_value={})
            mock_agg_service.return_value = mock_service_instance

            mock_manager_instance = AsyncMock()
            mock_manager_instance.save_aggregates = AsyncMock(return_value=3)
            mock_storage.return_value = mock_manager_instance

            mock_repo_instance = AsyncMock()
            mock_repo_instance.save_filter_values = AsyncMock()
            mock_repo_instance.clear_dashboard_values = AsyncMock()
            mock_repo.return_value = mock_repo_instance

            await _store_aggregates(
                df=df,
                dashboard_id=dashboard_id,
                task_id=task_id,
                mode="append",
                db_session=mock_session,
            )

            # Check that clear_old was False (append mode)
            call_kwargs = mock_manager_instance.save_aggregates.call_args
            assert call_kwargs[1]["clear_old"] is False

            # Verify filter values are cleared in append mode (idempotent rebuild per SPEC.md)
            mock_repo_instance.clear_dashboard_values.assert_called_once()

    async def test_store_aggregates_reads_metric_agg_from_producer_shape(
        self, mock_session
    ):
        """DP-002: the worker reads ``metric_agg`` from the shape the producer writes.

        ``DataService._execute_upload`` builds ``dict(config_response.settings)``,
        so ``metric_agg`` sits at the **top level** of the dict handed to the
        worker. Before the fix the worker read ``["settings"]["metric_agg"]``,
        which never exists, so ``_agg_fn_map`` always received ``"sum"`` and a
        dashboard configured for ``mean`` stored a sum under ``revenue_mean``.
        This asserts both the key and the value.
        """
        from mkobi.models.enums import GraphType

        df = pl.DataFrame({"category": ["A", "A", "B"], "sales": [100, 200, 400]})
        dashboard_id = uuid4()
        task_id = str(uuid4())

        mock_graph = MagicMock()
        mock_graph.id = uuid4()
        mock_graph.name = "Test Graph"
        mock_graph.type = GraphType.BAR
        mock_graph.dashboard_id = dashboard_id
        mock_graph.config = {}
        mock_graph.dimensions = []
        mock_graph.metrics = []

        mock_filter = MagicMock()
        mock_filter.id = uuid4()
        mock_filter.name = "Test Filter"
        mock_filter.type = FilterType.SELECT
        mock_filter.config = {}
        mock_filter.created_at = datetime.now(UTC)

        mock_graph_result = MagicMock()
        mock_graph_result.scalars.return_value.all.return_value = [mock_graph]

        mock_filter_result = MagicMock()
        mock_filter_result.scalars.return_value.all.return_value = [mock_filter]

        mock_session.execute.side_effect = [mock_graph_result, mock_filter_result] * 3

        with patch(
            "mkobi.services.aggregation_service.AggregationService"
        ) as mock_agg_service, patch(
            "mkobi.data.storage.manager.StorageManager"
        ) as mock_storage, patch(
            "mkobi.db.repositories.dashboard_filter_values_repo.DashboardFilterValuesRepository"
        ) as mock_repo:
            mock_service_instance = AsyncMock()
            mock_service_instance.aggregate_for_dashboard = AsyncMock(
                return_value=[{"graph_id": mock_graph.id, "dims": {}, "metrics": {}}]
            )
            mock_service_instance.extract_filter_values = AsyncMock(return_value={})
            mock_agg_service.return_value = mock_service_instance

            mock_manager_instance = AsyncMock()
            mock_manager_instance.save_aggregates = AsyncMock(return_value=1)
            mock_storage.return_value = mock_manager_instance

            mock_repo_instance = AsyncMock()
            mock_repo_instance.save_filter_values = AsyncMock()
            mock_repo_instance.clear_dashboard_values = AsyncMock()
            mock_repo.return_value = mock_repo_instance

            # The producer's shape: settings at the top level, metric_agg a key
            # of that same dict -- exactly what DataService._execute_upload passes.
            await _store_aggregates(
                df=df,
                dashboard_id=dashboard_id,
                task_id=task_id,
                mode="overwrite",
                db_session=mock_session,
                processing_config_dict={"metric_agg": "mean"},
            )

            agg_call = mock_service_instance.aggregate_for_dashboard.call_args
            assert agg_call is not None, "aggregate_for_dashboard should have been called"
            assert agg_call[1]["metric_agg"] == "mean", (
                "metric_agg must be read from the top-level producer shape, not ['settings']"
            )

    async def test_store_aggregates_logs_processed_count(
        self, mock_session
    ):
        """Test _store_aggregates saves filter values when present."""
        from mkobi.models.enums import GraphType

        df = pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        dashboard_id = uuid4()
        task_id = str(uuid4())

        mock_graph = MagicMock()
        mock_graph.id = uuid4()
        mock_graph.name = "Test Graph"
        mock_graph.type = GraphType.BAR
        mock_graph.dashboard_id = dashboard_id
        mock_graph.config = {}
        mock_graph.dimensions = []
        mock_graph.metrics = []

        mock_filter = MagicMock()
        mock_filter.id = uuid4()
        mock_filter.name = "Test Filter"
        mock_filter.type = FilterType.SELECT
        mock_filter.config = {}
        mock_filter.created_at = datetime.now(UTC)

        mock_graph_result = MagicMock()
        mock_graph_result.scalars.return_value.all.return_value = [mock_graph]

        mock_filter_result = MagicMock()
        mock_filter_result.scalars.return_value.all.return_value = [mock_filter]

        mock_session.execute.side_effect = [mock_graph_result, mock_filter_result] * 3

        with patch(
            "mkobi.services.aggregation_service.AggregationService"
        ) as mock_agg_service, patch(
            "mkobi.data.storage.manager.StorageManager"
        ) as mock_storage, patch(
            "mkobi.db.repositories.dashboard_filter_values_repo.DashboardFilterValuesRepository"
        ) as mock_repo:
            mock_service_instance = AsyncMock()
            mock_service_instance.aggregate_for_dashboard = AsyncMock(
                return_value=[{"graph_id": mock_graph.id, "dims": {"a": [1]}, "metrics": {"b": 1}}]
            )
            mock_service_instance.extract_filter_values = AsyncMock(
                return_value={"b": ["x", "y"]}
            )
            mock_agg_service.return_value = mock_service_instance

            mock_manager_instance = AsyncMock()
            mock_manager_instance.save_aggregates = AsyncMock(return_value=3)
            mock_storage.return_value = mock_manager_instance

            mock_repo_instance = AsyncMock()
            mock_repo_instance.save_filter_values = AsyncMock()
            mock_repo_instance.clear_dashboard_values = AsyncMock()
            mock_repo.return_value = mock_repo_instance

            await _store_aggregates(
                df=df,
                dashboard_id=dashboard_id,
                task_id=task_id,
                mode="overwrite",
                db_session=mock_session,
            )

            mock_repo_instance.save_filter_values.assert_called_once()


# --- Concurrent APPEND upload tests (unit tests with mocks) ---

@pytest.mark.asyncio
class TestConcurrentAppendUploads:
    """Tests for concurrent APPEND mode uploads in _store_aggregates.

    Verifies that concurrent uploads to the same dashboard in APPEND mode
    do not cause data corruption or loss. Tests the UPSERT mechanism's
    thread-safety and transaction isolation.
    """

    @pytest.fixture
    def mock_session(self):
        """Create a mock AsyncSession for concurrent upload tests."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    async def test_concurrent_append_uploads_completes_successfully(
        self, mock_session
    ):
        """Verify two concurrent APPEND uploads complete without errors.

        Both uploads use clear_old=False (append mode) and should complete
        successfully without race conditions or deadlocks.
        """
        from mkobi.models.enums import GraphType

        graph_id = uuid4()
        dashboard_id = uuid4()

        df1 = pl.DataFrame({"a": [1], "b": ["x"]})
        df2 = pl.DataFrame({"a": [2], "b": ["y"]})
        task_id1 = str(uuid4())
        task_id2 = str(uuid4())

        mock_graph = MagicMock()
        mock_graph.id = graph_id
        mock_graph.name = "Test Graph"
        mock_graph.type = GraphType.BAR
        mock_graph.dashboard_id = dashboard_id
        mock_graph.config = {}
        mock_graph.dimensions = []
        mock_graph.metrics = []

        mock_filter = MagicMock()
        mock_filter.id = uuid4()
        mock_filter.name = "region"
        mock_filter.type = FilterType.SELECT
        mock_filter.config = {}
        mock_filter.created_at = datetime.now(UTC)

        mock_graph_result = MagicMock()
        mock_graph_result.scalars.return_value.all.return_value = [mock_graph]

        mock_filter_result = MagicMock()
        mock_filter_result.scalars.return_value.all.return_value = [mock_filter]

        mock_session.execute.side_effect = ([mock_graph_result, mock_filter_result] * 3)[:6]

        with patch(
            "mkobi.services.aggregation_service.AggregationService"
        ) as mock_agg_service, patch(
            "mkobi.data.storage.manager.StorageManager"
        ) as mock_storage, patch(
            "mkobi.db.repositories.dashboard_filter_values_repo.DashboardFilterValuesRepository"
        ) as mock_repo:
            mock_service_instance = AsyncMock()
            mock_service_instance.aggregate_for_dashboard = AsyncMock(return_value=[])
            mock_service_instance.extract_filter_values = AsyncMock(return_value={})
            mock_agg_service.return_value = mock_service_instance

            mock_manager_instance = AsyncMock()
            mock_manager_instance.save_aggregates = AsyncMock(return_value=1)
            mock_storage.return_value = mock_manager_instance

            mock_repo_instance = AsyncMock()
            mock_repo_instance.save_filter_values = AsyncMock()
            mock_repo_instance.clear_dashboard_values = AsyncMock()
            mock_repo.return_value = mock_repo_instance

            results = await asyncio.gather(
                _store_aggregates(
                    df=df1,
                    dashboard_id=dashboard_id,
                    task_id=task_id1,
                    mode="append",
                    db_session=mock_session,
                ),
                _store_aggregates(
                    df=df2,
                    dashboard_id=dashboard_id,
                    task_id=task_id2,
                    mode="append",
                    db_session=mock_session,
                ),
                return_exceptions=True,
            )

            assert all(isinstance(r, type(None)) for r in results), \
                f"Both uploads should complete without exceptions, got: {results}"

            assert mock_manager_instance.save_aggregates.call_count == 2
            for call in mock_manager_instance.save_aggregates.call_args_list:
                assert call[1]["clear_old"] is False, "APPEND mode should use clear_old=False"

    async def test_concurrent_append_uploads_data_integrity(
        self, mock_session
    ):
        """Verify data from both concurrent APPEND uploads is preserved.

        Tests that the UPSERT mechanism correctly handles concurrent calls
        and both uploads' data is processed.
        """
        from mkobi.models.enums import GraphType

        graph_id = uuid4()
        dashboard_id = uuid4()

        mock_graph = MagicMock()
        mock_graph.id = graph_id
        mock_graph.name = "Test Graph"
        mock_graph.type = GraphType.BAR
        mock_graph.dashboard_id = dashboard_id
        mock_graph.config = {}
        mock_graph.dimensions = []
        mock_graph.metrics = []

        mock_filter = MagicMock()
        mock_filter.id = uuid4()
        mock_filter.name = "Test Filter"
        mock_filter.type = FilterType.SELECT
        mock_filter.config = {}
        mock_filter.created_at = datetime.now(UTC)

        mock_graph_result = MagicMock()
        mock_graph_result.scalars.return_value.all.return_value = [mock_graph]

        mock_filter_result = MagicMock()
        mock_filter_result.scalars.return_value.all.return_value = [mock_filter]

        mock_session.execute.side_effect = [mock_graph_result, mock_filter_result] * 3

        df1 = pl.DataFrame({"a": [1], "b": ["A"]})
        df2 = pl.DataFrame({"a": [2], "b": ["B"]})
        task_id1 = str(uuid4())
        task_id2 = str(uuid4())

        with patch(
            "mkobi.services.aggregation_service.AggregationService"
        ) as mock_agg_service, patch(
            "mkobi.data.storage.manager.StorageManager"
        ) as mock_storage, patch(
            "mkobi.db.repositories.dashboard_filter_values_repo.DashboardFilterValuesRepository"
        ) as mock_repo:
            mock_service_instance = AsyncMock()
            mock_service_instance.aggregate_for_dashboard = AsyncMock(
                side_effect=[
                    [{"graph_id": graph_id, "dims": {"category": "A"}, "metrics": {"revenue_sum": 100}}],
                    [{"graph_id": graph_id, "dims": {"category": "B"}, "metrics": {"revenue_sum": 200}}],
                ]
            )
            mock_service_instance.extract_filter_values = AsyncMock(return_value={"category": ["A", "B"]})
            mock_agg_service.return_value = mock_service_instance

            processed_counts = []

            async def save_aggregates_side_effect(*args, **kwargs):
                aggregates = kwargs.get("aggregates", [])
                processed_counts.append(len(aggregates))
                return len(aggregates)

            mock_manager_instance = AsyncMock()
            mock_manager_instance.save_aggregates = AsyncMock(side_effect=save_aggregates_side_effect)
            mock_manager_instance.get_aggregates = AsyncMock(return_value=[])
            mock_storage.return_value = mock_manager_instance

            mock_repo_instance = AsyncMock()
            mock_repo_instance.save_filter_values = AsyncMock()
            mock_repo_instance.clear_dashboard_values = AsyncMock()
            mock_repo.return_value = mock_repo_instance

            await asyncio.gather(
                _store_aggregates(
                    df=df1,
                    dashboard_id=dashboard_id,
                    task_id=task_id1,
                    mode="append",
                    db_session=mock_session,
                ),
                _store_aggregates(
                    df=df2,
                    dashboard_id=dashboard_id,
                    task_id=task_id2,
                    mode="append",
                    db_session=mock_session,
                ),
            )

            total_records = sum(processed_counts)
            assert total_records == 2, f"Expected 2 total records, got {total_records}"


# --- Integration tests for concurrent APPEND uploads with real database ---

@pytest.mark.asyncio
class TestConcurrentAppendUploadsIntegration:
    """Integration tests for concurrent APPEND mode uploads with real database.

    Verifies that concurrent uploads to the same dashboard in APPEND mode
    correctly persist both datasets using the UPSERT mechanism without
    data corruption or loss.
    """

    @pytest.fixture
    async def test_dashboard(
        self, async_db_session, test_user: dict
    ):
        """Create a test dashboard for integration tests."""
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository
        from mkobi.models.enums import DashboardPermission

        repo = DashboardRepository()
        dashboard = await repo.create(
            db=async_db_session,
            name=f"integration_test_dashboard_{uuid4().hex[:8]}",
            description="Dashboard for concurrent upload integration tests",
        )

        # Grant edit access to test user
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=test_user["id"],
            dashboard_id=dashboard.id,
            permission=DashboardPermission.EDIT,
        )
        await async_db_session.commit()

        return dashboard

    @pytest.fixture
    async def graph_for_dashboard(
        self, async_db_session, test_dashboard
    ):
        """Create a graph for the dashboard."""
        from mkobi.models.enums import GraphType
        from mkobi.db.repositories.graph_repo import GraphRepository

        graph_repo = GraphRepository()
        graph = await graph_repo.create(
            db=async_db_session,
            dashboard_id=test_dashboard.id,
            name="Test Graph",
            type=GraphType.BAR,
            dimensions=["category"],
            metrics=["sales"],
        )
        await async_db_session.commit()
        return graph

    async def test_concurrent_append_uploads(
        self,
        async_db_session,
        test_dashboard,
        graph_for_dashboard,
    ):
        """Verify concurrent APPEND uploads complete successfully and data is preserved.

        Two sequential uploads in APPEND mode should both complete without errors,
        and the final aggregated data should contain records from both uploads.
        """
        from mkobi.data.storage.manager import StorageManager
        from mkobi.models.graph import GraphRead
        from mkobi.models.filters import FilterRead
        from mkobi.services.aggregation_service import AggregationService
        from mkobi.models.enums import GraphType

        dashboard_id = test_dashboard.id
        graph_id = graph_for_dashboard.id

        # Build graph_reads and filter_reads for aggregation
        graph_reads = [GraphRead(
            id=graph_id,
            name="Test Graph",
            type=GraphType.BAR,
            dashboard_id=dashboard_id,
            config={},
            dimensions=["category"],
            metrics=["sales"],
            created_at=datetime.now(UTC),
        )]
        filter_reads: list[FilterRead] = []  # No filters to avoid duplicate column names in groupby

        # Initialize services with real database session
        agg_service = AggregationService()
        storage_manager = StorageManager(async_db_session)

        # Create test data for two uploads
        df1 = pl.DataFrame({"category": ["A", "B"], "sales": [100, 200]})
        df2 = pl.DataFrame({"category": ["C", "D"], "sales": [300, 400]})

        # First upload in APPEND mode
        records1 = await agg_service.aggregate_for_dashboard(
            df1, graph_reads, filter_reads, metric_agg="sum"
        )
        aggregates1 = [
            {"graph_id": r["graph_id"], "dims": r["dims"], "metrics": r["metrics"]}
            for r in records1
        ]
        await storage_manager.save_aggregates(
            dashboard_id=dashboard_id,
            aggregates=aggregates1,
            clear_old=False,
        )

        # Second upload in APPEND mode
        records2 = await agg_service.aggregate_for_dashboard(
            df2, graph_reads, filter_reads, metric_agg="sum"
        )
        aggregates2 = [
            {"graph_id": r["graph_id"], "dims": r["dims"], "metrics": r["metrics"]}
            for r in records2
        ]
        await storage_manager.save_aggregates(
            dashboard_id=dashboard_id,
            aggregates=aggregates2,
            clear_old=False,
        )

        # Commit to persist data within the SAVEPOINT transaction
        # (async_db_session fixture handles SAVEPOINT, rollback happens after test)

        # Verify both datasets are present in the database
        all_records = await storage_manager.get_aggregates(dashboard_id)

        categories_found = {rec["dims"].get("category") for rec in all_records}
        assert "A" in categories_found, "Data from first upload should be present"
        assert "B" in categories_found, "Data from first upload should be present"
        assert "C" in categories_found, "Data from second upload should be present"
        assert "D" in categories_found, "Data from second upload should be present"

        # Verify no data corruption - all 4 records should exist
        assert len(all_records) == 4, f"Expected 4 records, got {len(all_records)}"
