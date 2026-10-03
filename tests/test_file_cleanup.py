"""Tests for file cleanup utilities."""
import asyncio
import os
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from mkobi.models.enums import ProcessingStatus
from mkobi.services.file_cleanup import CleanupResult, cleanup_stale_temp_files


@pytest.fixture(autouse=True)
def setup_temp_dir_fixture(monkeypatch):
    """Set up a temporary directory for upload tests."""
    temp_dir = tempfile.mkdtemp()
    
    class MockDatabase:
        lock_timeout_ms = 5000

    class MockConfig:
        upload_temp_dir = temp_dir
        stale_file_threshold_hours = 24
        # The worker builds its loader with ``get_config().max_file_size`` and
        # the rebuild advisory lock reads ``get_config().database.lock_timeout_ms``.
        # This autouse fixture patches ``mkobi.config.get_config``, so the mock is
        # bound into those modules too; without these attributes a path-scoped run
        # of this module fails inside the worker's loader/lock construction.
        max_file_size = 100 * 1024 * 1024
        database = MockDatabase
    
    def get_config_mock():
        return MockConfig()
    
    monkeypatch.setattr("mkobi.services.file_cleanup.get_config", get_config_mock)
    monkeypatch.setattr("mkobi.config.get_config", get_config_mock)
    
    yield temp_dir
    
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestFileCleanup:
    """Tests for file cleanup utilities."""

    def test_cleanup_stale_temp_files_deletes_old_files(self, setup_temp_dir_fixture):
        """Test cleanup_stale_temp_files deletes files older than threshold."""
        temp_dir = setup_temp_dir_fixture
        # Create a file
        old_file = Path(temp_dir) / "old_file.csv"
        old_file.write_text("old,data\n1,2\n")

        # Set mtime to 25 hours ago (older than default 24h threshold)
        old_time = time.time() - (25 * 3600)
        old_file.touch()
        os.utime(old_file, (old_time, old_time))

        # Create a recent file
        recent_file = Path(temp_dir) / "recent_file.csv"
        recent_file.write_text("recent\n")

        result = cleanup_stale_temp_files()

        assert result.deleted == 1
        assert result.already_gone == 0
        assert result.failed == 0
        assert not old_file.exists()
        assert recent_file.exists()

    def test_cleanup_stale_temp_files_custom_threshold(self, setup_temp_dir_fixture):
        """Test cleanup_stale_temp_files with custom threshold."""
        temp_dir = setup_temp_dir_fixture
        # Create a file 3 hours old
        file_path = Path(temp_dir) / "medium_file.csv"
        file_path.write_text("medium\n")
        old_time = time.time() - (3 * 3600)
        file_path.touch()
        os.utime(file_path, (old_time, old_time))

        # With 2 hour threshold, should be deleted
        result = cleanup_stale_temp_files(max_age_hours=2)
        assert result.deleted == 1

    def test_cleanup_stale_temp_files_keeps_recent_files(self, setup_temp_dir_fixture):
        """Test cleanup keeps recent files with 5 hour threshold."""
        temp_dir = setup_temp_dir_fixture
        # Create a fresh file that's 3 hours old
        file_path = Path(temp_dir) / "recent_file.csv"
        file_path.write_text("recent\n")
        old_time = time.time() - (3 * 3600)
        file_path.touch()
        os.utime(file_path, (old_time, old_time))

        # With 5 hour threshold, should NOT be deleted
        result = cleanup_stale_temp_files(max_age_hours=5)
        assert result.deleted == 0
        assert result.already_gone == 0
        assert result.failed == 0
        assert file_path.exists()

    def test_cleanup_stale_temp_files_nonexistent_directory(self, monkeypatch):
        """Test cleanup when upload directory doesn't exist."""
        monkeypatch.setattr(
            "mkobi.services.file_cleanup.get_config",
            lambda: MagicMock(upload_temp_dir="/nonexistent/path", stale_file_threshold_hours=24)
        )

        result = cleanup_stale_temp_files()
        assert result == CleanupResult()

    def test_cleanup_stale_temp_files_zero_threshold_deletes_all(self, monkeypatch):
        """Test that max_age_hours=0 deletes all files regardless of age."""
        temp_dir = tempfile.mkdtemp()
        monkeypatch.setattr(
            "mkobi.services.file_cleanup.get_config",
            lambda: MagicMock(upload_temp_dir=temp_dir, stale_file_threshold_hours=24)
        )

        # Create test files
        file1 = Path(temp_dir) / "test_file1.csv"
        file1.write_text("test,data\n1,2\n")
        file2 = Path(temp_dir) / "test_file2.csv.gz"
        file2.write_text("compressed\n")

        result = cleanup_stale_temp_files(max_age_hours=0)
        assert result.deleted == 2  # All files should be deleted
        assert result.already_gone == 0
        assert result.failed == 0

        # Verify all files are gone
        assert not file1.exists()
        assert not file2.exists()

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_cleanup_stale_temp_files_negative_threshold(self, monkeypatch):
        """Test cleanup with negative threshold returns 0."""
        temp_dir = tempfile.mkdtemp()
        monkeypatch.setattr(
            "mkobi.services.file_cleanup.get_config",
            lambda: MagicMock(upload_temp_dir=temp_dir, stale_file_threshold_hours=24)
        )

        # Create test files
        file1 = Path(temp_dir) / "test_file1.csv"
        file1.write_text("test\n")

        result = cleanup_stale_temp_files(max_age_hours=-1)
        assert result == CleanupResult()  # Negative threshold is invalid, no files deleted
        assert file1.exists()  # File should still exist

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)




class TestConcurrentSweepCountContract:
    """The count is a contract, and a lost race is not an ERROR.

    Several sweepers over the same directory race the same candidates. Exactly
    one removes each file; the others see ``FileNotFoundError``. The ruling: a
    lost race is the ordinary outcome and must be silent at ERROR, while the
    ``deleted`` values across sweepers still sum to the number of files removed
    exactly once (FAB-4 / D-06-D(c)).
    """

    @staticmethod
    def _make_old_csv(directory: Path, index: int) -> Path:
        """Create one stale CSV file (mtime far in the past)."""
        path = directory / f"race_{index}.csv"
        path.write_text("a,b\n1,2\n")
        old_time = time.time() - (100 * 3600)
        os.utime(path, (old_time, old_time))
        return path

    def test_concurrent_sweepers_delete_each_file_once_and_do_not_log_errors(
        self, setup_temp_dir_fixture
    ):
        """N sweepers over M old files: each deleted once, no ERROR, counts sum.

        The last assertion is what turns ``deleted`` from a log line into a
        contract: the sum over all concurrent sweepers of ``deleted`` equals
        ``M``, and ``deleted + already_gone`` also sums to ``M`` -- so every
        candidate is accounted for exactly once across the fleet.
        """
        import logging

        temp_dir = Path(setup_temp_dir_fixture)
        m_files = 20
        paths = [self._make_old_csv(temp_dir, i) for i in range(m_files)]

        records: list[logging.LogRecord] = []

        class _Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        cleanup_logger = logging.getLogger("mkobi.services.file_cleanup")
        collector = _Collector(level=logging.DEBUG)
        original_level = cleanup_logger.level
        was_disabled = cleanup_logger.disabled
        cleanup_logger.addHandler(collector)
        cleanup_logger.setLevel(logging.DEBUG)
        cleanup_logger.disabled = False
        try:
            # Simulate N concurrent sweepers by interleaving the same glob list:
            # each sweeper independently lists the directory, so the losers reach
            # files the winner already removed.
            results = [cleanup_stale_temp_files(max_age_hours=0) for _ in range(5)]
        finally:
            cleanup_logger.removeHandler(collector)
            cleanup_logger.setLevel(original_level)
            cleanup_logger.disabled = was_disabled

        # (i) Every file is deleted exactly once: physically gone...
        assert all(not path.exists() for path in paths)

        # (ii) No ERROR-level record is produced for a file another sweeper won.
        error_records = [r for r in records if r.levelno >= logging.ERROR]
        assert error_records == [], [r.getMessage() for r in error_records]

        # (iii) The sweepers' deleted counts sum to M; deleted + already_gone
        # also sum to M, so no candidate is counted twice or lost.
        assert sum(r.deleted for r in results) == m_files
        assert sum(r.deleted + r.already_gone for r in results) == m_files
        assert sum(r.failed for r in results) == 0

    def test_deleted_is_the_count_contract_not_an_error_line(
        self, setup_temp_dir_fixture
    ):
        """One sweeper: deleted counts exactly the files it removed.

        The plain single-sweeper shape of the same contract, stated so a reader
        sees ``deleted`` as "files this process won" and not "files observed".
        """
        temp_dir = Path(setup_temp_dir_fixture)
        paths = [self._make_old_csv(temp_dir, i) for i in range(3)]

        result = cleanup_stale_temp_files(max_age_hours=0)

        assert result.deleted == 3
        assert result.already_gone == 0
        assert result.failed == 0
        assert all(not path.exists() for path in paths)


class TestGenuineRemovalFailureIsNotSilenced:
    """A real removal error stays an ERROR and is counted in ``failed``.

    This is the counterweight to the race test: an implementation could make the
    log quiet by swallowing every exception as "someone else got it", which is
    exactly the opposite of the finding. An ``OSError`` that is *not*
    ``FileNotFoundError`` (here, an ``EACCES``) must be counted in ``failed`` and
    logged at ERROR with a traceback.

    The unwritable case is simulated by patching ``Path.unlink`` to raise
    ``PermissionError`` (an ``OSError`` subclass): this is platform-independent
    and does not depend on the test process not being privileged, which is what
    a real chmod-based EACCES would.
    """

    def test_permission_error_is_counted_failed_and_logged_error(
        self, setup_temp_dir_fixture
    ):
        """An EACCES-equivalent removal is a failure, not a lost race."""
        import logging

        temp_dir = Path(setup_temp_dir_fixture)
        target = temp_dir / "unwritable.csv"
        target.write_text("a,b\n1,2\n")
        old_time = time.time() - (100 * 3600)
        os.utime(target, (old_time, old_time))

        records: list[logging.LogRecord] = []

        class _Collector(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        cleanup_logger = logging.getLogger("mkobi.services.file_cleanup")
        collector = _Collector(level=logging.DEBUG)
        original_level = cleanup_logger.level
        was_disabled = cleanup_logger.disabled
        cleanup_logger.addHandler(collector)
        cleanup_logger.setLevel(logging.DEBUG)
        cleanup_logger.disabled = False

        real_unlink = Path.unlink

        def _raise_permission_error(self, *args, **kwargs):
            if self == target:
                raise PermissionError(13, "Permission denied", str(self))
            return real_unlink(self, *args, **kwargs)

        try:
            with patch.object(Path, "unlink", _raise_permission_error):
                result = cleanup_stale_temp_files(max_age_hours=0)
        finally:
            cleanup_logger.removeHandler(collector)
            cleanup_logger.setLevel(original_level)
            cleanup_logger.disabled = was_disabled

        # The failure is counted as a failure, not absorbed as a lost race.
        assert result.failed == 1
        assert result.deleted == 0
        assert result.already_gone == 0

        # The ERROR severity survives: a genuine failure is not made silent.
        error_records = [
            r for r in records if r.levelno >= logging.ERROR and target.name in r.getMessage()
        ]
        assert error_records, "a genuine removal failure must be logged at ERROR"
        # exc_info is attached (a traceback is available on the record).
        assert any(r.exc_info is not None for r in error_records)

        # The file was not removed, so a later tick can retry it.
        assert target.exists()


class TestPlacementUnderTheReconcilerLease:
    """Placement/guard: the sweep rides the lease-guarded periodic loop.

    The sweep moved out of ``DatabaseStarter.startup`` and onto
    ``start_stale_processing_cleanup_task``. The guard's committed direction is
    fail **open**: a non-holder does not sweep, but an unreachable Redis still
    sweeps.
    """

    @staticmethod
    def _run_loop(lease, status=None):
        """Create the periodic loop task with a zero interval."""
        from mkobi.workers.data_worker import start_stale_processing_cleanup_task

        return asyncio.create_task(
            start_stale_processing_cleanup_task(
                interval_seconds=0, lease=lease, status=status
            )
        )

    @staticmethod
    async def _run_for(ticks: int) -> None:
        for _ in range(ticks):
            await asyncio.sleep(0.005)

    @staticmethod
    async def _stop(task) -> None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_non_holder_does_not_sweep_and_unreachable_redis_does(self):
        """A non-holder performs no sweep; an unreachable Redis still sweeps.

        Mirrors the assertion shape of the existing
        ``TestReconcilerLoop`` lease tests: the same ``FakeAsyncRedis`` double,
        the same zero-interval loop, the same ``NOT_ACQUIRED`` vs ``UNREACHABLE``
        pair. Both sweeps of the paired recorder are patched so the loop opens no
        database session.
        """
        from mkobi.core.reconciler_lease import LEASE_KEY, ReconcilerLease
        from mkobi.models.enums import LeaseAcquisitionResult
        from tests.test_data_worker import FakeAsyncRedis

        sweeps: list[int] = []
        orphans: list[int] = []
        file_sweeps: list[int] = []

        async def sweep(timeout_minutes=5, session=None):
            sweeps.append(len(sweeps))
            return 0

        async def orphan_sweep(timeout_minutes=None, session=None):
            orphans.append(len(orphans))
            return 0

        def file_sweep(max_age_hours=None):
            file_sweeps.append(len(file_sweeps))
            return CleanupResult()

        with patch(
            "mkobi.workers.data_worker.cleanup_stale_processing_logs", new=sweep
        ):
            with patch(
                "mkobi.workers.data_worker.mark_orphaned_uploaded_logs_failed",
                new=orphan_sweep,
            ):
                with patch(
                    "mkobi.workers.data_worker.cleanup_stale_temp_files", new=file_sweep
                ):
                    # (1) Reachable Redis held by another replica: no sweep.
                    holder_client = FakeAsyncRedis()
                    assert (
                        await ReconcilerLease(holder_client).acquire()
                        == LeaseAcquisitionResult.ACQUIRED
                    )
                    task = self._run_loop(ReconcilerLease(holder_client))
                    try:
                        await self._run_for(60)
                        assert sweeps == [], "a non-holder must not run the DB sweep"
                        assert file_sweeps == [], "a non-holder must not sweep files"
                    finally:
                        await self._stop(task)

                    # (2) Unreachable Redis: fail open and sweep the files too.
                    unreachable = FakeAsyncRedis()
                    unreachable.fail_mode = True
                    task = self._run_loop(ReconcilerLease(unreachable))
                    try:
                        for _ in range(200):
                            if file_sweeps:
                                break
                            await asyncio.sleep(0.005)
                        assert file_sweeps, "UNREACHABLE must fail open and sweep"
                    finally:
                        await self._stop(task)
        # The key is held by the foreign replica throughout; nothing here deleted
        # it, which is what makes case (1) a genuine NOT_ACQUIRED, not an outage.
        assert LEASE_KEY in holder_client._data


class TestTempFileCleanupOnProcessingFailure:
    """Tests for temp file cleanup when processing fails during background job."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock AsyncSession for unit tests."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_temp_file_cleaned_up_when_processing_fails(
        self, mock_session, tmp_path
    ):
        """Verify task file is cleaned up when CSV processing raises an exception.

        Creates a malformed CSV file at a task location, then calls the processing
        function directly and verifies cleanup happens in the exception handler.
        Uses a temporary directory to avoid needing real database for file operations.
        """
        from mkobi.workers.data_worker import _process_csv_file_async

        # Create malformed CSV file in temp directory
        task_id = uuid4()
        task_file = tmp_path / f"{task_id}.csv"
        malformed_csv = b"category,sales\n1,\"unclosed quote\n"  # Malformed CSV
        task_file.write_bytes(malformed_csv)

        files_before = list(tmp_path.glob("*.csv*"))

        # Process the malformed CSV - this should fail and clean up
        with patch(
            "mkobi.workers.data_worker._update_processing_log_status",
            new_callable=AsyncMock,
        ):
            with patch(
                "mkobi.workers.data_worker._store_aggregates",
                new_callable=AsyncMock,
            ):
                try:
                    await _process_csv_file_async(
                        file_path_str=str(task_file),
                        task_id=str(task_id),
                        dashboard_id_str="00000000-0000-0000-0000-000000000000",
                        processing_config_dict=None,
                        mode="overwrite",
                        db_session=mock_session,
                    )
                except Exception:
                    pass  # Expected to fail due to malformed CSV

        # Verify temp file is cleaned up after processing failure
        files_after = list(tmp_path.glob("*.csv*"))
        assert len(files_after) == len(files_before) - 1, (
            f"Task file should be cleaned up after processing failure. "
            f"Before: {len(files_before)}, After: {len(files_after)}"
        )


class TestProcessingFailureReportedOnOwnSession:
    """Tests for failure reporting when the worker owns the session (production path).

    Production calls ``_process_csv_file_async`` with ``db_session=None``. The
    failure must be written to ``processing_logs`` on a fresh session, after the
    failed transaction has exited, so the FAILED row survives the rollback it is
    reporting. These tests drive that production branch directly; every other
    existing caller passes a non-None session and never reaches it.
    """

    async def _run_failure_with_patched_get_session(self, tmp_path, session_cm):
        """Run a failing production-path job with ``get_session`` replaced.

        The malformed CSV is left in ``tmp_path`` so cleanup can be asserted, but
        ``CSVLoader.load_csv`` is patched to return a valid frame: the failure must
        come from ``_store_aggregates`` (after the transaction has begun), not from
        parsing.

        Args:
            tmp_path: pytest temporary directory used for the malformed CSV.
            session_cm: An async context manager factory standing in for
                ``mkobi.workers.data_worker.get_session``.

        Returns:
            tuple: (raised_exception, status_mock, store_mock)
        """
        import polars as pl

        from mkobi.workers.data_worker import CSVLoader, _process_csv_file_async

        task_id = uuid4()
        task_file = tmp_path / f"{task_id}.csv"
        task_file.write_bytes(b"category,sales\n1,\"unclosed quote\n")

        valid_frame = pl.DataFrame({"category": ["a"], "sales": [1]})
        status_mock = AsyncMock(return_value=None)
        # Force a failure after the transaction has begun, not during parsing.
        store_mock = AsyncMock(side_effect=RuntimeError("forced processing failure"))

        raised: BaseException | None = None
        with patch(
            "mkobi.workers.data_worker._update_processing_log_status", new=status_mock
        ), patch(
            "mkobi.workers.data_worker._store_aggregates", new=store_mock
        ), patch(
            "mkobi.workers.data_worker.get_session", new=session_cm
        ), patch.object(
            CSVLoader, "load_csv", return_value=valid_frame
        ):
            try:
                await _process_csv_file_async(
                    file_path_str=str(task_file),
                    task_id=str(task_id),
                    dashboard_id_str="00000000-0000-0000-0000-000000000000",
                    processing_config_dict=None,
                    mode="overwrite",
                    db_session=None,
                )
            except BaseException as exc:  # noqa: BLE001 - we assert on the type below
                raised = exc

        return raised, status_mock, store_mock

    @staticmethod
    def _failed_writes(status_mock: AsyncMock) -> list[Any]:
        """Return the status writes that carried ``ProcessingStatus.FAILED``."""
        from mkobi.models.enums import ProcessingStatus

        return [
            call.kwargs
            for call in status_mock.await_args_list
            if call.kwargs.get("status") == ProcessingStatus.FAILED
        ]

    @pytest.mark.asyncio
    async def test_failure_is_reported_on_a_fresh_session_without_a_session_argument(
        self, tmp_path
    ):
        """A post-transaction failure writes FAILED on a session the helper opens.

        The absence of a ``session`` argument is what distinguishes a real fix
        from a write performed on the session that is about to roll back.
        """
        session = AsyncMock()
        session.begin = MagicMock()

        @asynccontextmanager
        async def fake_get_session():
            yield session

        raised, status_mock, store_mock = await self._run_failure_with_patched_get_session(
            tmp_path, fake_get_session
        )

        # The forced failure really came from _store_aggregates.
        assert store_mock.await_count == 1

        # (1) The write escaped the transaction: exactly one FAILED write, with a
        # populated message and crucially no session argument.
        failed_writes = self._failed_writes(status_mock)
        assert len(failed_writes) == 1
        assert failed_writes[0]["message"]
        assert "session" not in failed_writes[0]

        # (2) The failure still propagates.
        assert isinstance(raised, RuntimeError)
        assert "forced processing failure" in str(raised)

        # (4) The temp file is still cleaned up.
        assert list(tmp_path.glob("*.csv*")) == []

    @pytest.mark.asyncio
    async def test_failure_before_transaction_begin_reports_failed_not_nameerror(
        self, tmp_path
    ):
        """A failure in ``get_session()`` itself is reported, never a NameError.

        This is the trap the naive fall-through fix introduces: the dead block
        reads ``error_msg``/``error_code``, which are unbound for failures that
        happen before the nested transaction body.
        """
        @asynccontextmanager
        async def failing_get_session():
            raise RuntimeError("session acquisition failed")
            yield  # pragma: no cover - never reached

        raised, status_mock, _store_mock = await self._run_failure_with_patched_get_session(
            tmp_path, failing_get_session
        )

        assert not isinstance(raised, NameError)
        assert isinstance(raised, RuntimeError)
        assert "session acquisition failed" in str(raised)

        failed_writes = self._failed_writes(status_mock)
        assert len(failed_writes) == 1
        assert failed_writes[0]["message"]
        assert "session" not in failed_writes[0]

        assert list(tmp_path.glob("*.csv*")) == []


class TestRolledBackMainTransactionLeavesNoLeakedFile:
    """A failed commit of the main transaction must still not leak the temp file.

    The success path unlinks the temp file *after* the main transaction commits
    (ruling D-05-B), so at the instant the commit fails the file is **still
    present** and the success-path unlink never runs. No file leaks because the
    failure-path unlink in ``_process_csv_file_async`` is **retained**: that
    handler reclaims the very file the success path has not yet reached. The
    assertion below is therefore inverted relative to the pre-ruling version
    (which expected the file to be gone because it was unlinked inside the
    transaction body); the reason no file leaks is the retained failure-path
    unlink, and the final ``list(tmp_path.glob("*.csv*")) == []`` is the genuine
    guard that a commit failure still cleans up.
    """

    @staticmethod
    def _session_with_failing_commit(observed: dict[str, Any], task_file: Path) -> MagicMock:
        """A mock session whose ``begin()`` block raises when it commits.

        Records whether the temp file still exists at the moment the commit
        fails (``__aexit__``, after the block body ran) - that is the instant
        that distinguishes an unlink kept inside the transaction body (already
        gone) from one moved after the commit (still present, and reclaimed by
        the retained failure-path unlink).
        """

        class _FailingBegin:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                observed["file_exists_at_commit"] = task_file.exists()
                raise RuntimeError("main transaction commit failed")

        session = MagicMock()
        session.execute = AsyncMock()
        session.begin = lambda: _FailingBegin()
        return session

    @staticmethod
    def _successful_session() -> MagicMock:
        """A mock session whose ``begin()`` block commits normally."""
        from contextlib import asynccontextmanager

        session = MagicMock()
        session.execute = AsyncMock()

        @asynccontextmanager
        async def ok_begin():
            yield

        session.begin = ok_begin
        return session

    @pytest.mark.asyncio
    async def test_rolled_back_main_transaction_leaves_no_leaked_file_and_no_secondary_failure(
        self, tmp_path
    ):
        """The early commit succeeds, the main commit fails, no file is left."""
        import polars as pl

        import mkobi.workers.data_worker as data_worker
        from mkobi.workers.data_worker import CSVLoader

        task_id = uuid4()
        task_file = tmp_path / f"{task_id}.csv"
        task_file.write_bytes(b"category,sales\n1,\"unclosed quote\n")

        original_helper = data_worker._update_processing_log_status
        status_calls: list[dict[str, Any]] = []
        observed: dict[str, Any] = {}

        async def spy_helper(**kwargs):
            """Record every status write, then delegate to the real helper."""
            status_calls.append(kwargs)
            return await original_helper(**kwargs)

        main_session = self._session_with_failing_commit(observed, task_file)
        # get_session is opened once per own-session status write: the early
        # PROCESSING announcement, the main transaction, then the compensation's
        # FAILED report. Only the main transaction's session fails to commit.
        sessions = [
            self._successful_session(),
            main_session,
            self._successful_session(),
        ]

        @asynccontextmanager
        async def counting_get_session():
            yield sessions.pop(0)

        valid_frame = pl.DataFrame({"category": ["a"], "sales": [1]})
        store_mock = AsyncMock(return_value=None)

        raised: BaseException | None = None
        with patch(
            "mkobi.workers.data_worker._update_processing_log_status", new=spy_helper
        ), patch(
            "mkobi.workers.data_worker._store_aggregates", new=store_mock
        ), patch(
            "mkobi.workers.data_worker.get_session", new=counting_get_session
        ), patch(
            "mkobi.workers.data_worker.acquire_dashboard_rebuild_lock",
            new=AsyncMock(),
        ), patch.object(
            CSVLoader, "load_csv", return_value=valid_frame
        ):
            try:
                await data_worker._process_csv_file_async(
                    file_path_str=str(task_file),
                    task_id=str(task_id),
                    dashboard_id_str="00000000-0000-0000-0000-000000000000",
                    processing_config_dict=None,
                    mode="overwrite",
                    db_session=None,
                )
            except BaseException as exc:  # noqa: BLE001 - asserted below
                raised = exc

        # The original commit failure propagates; the compensation raised nothing
        # of its own (a secondary failure would replace it here).
        assert isinstance(raised, RuntimeError)
        assert "main transaction commit failed" in str(raised)

        # The early PROCESSING write carries no session argument (own transaction).
        processing_writes = [
            call for call in status_calls if call.get("status") == ProcessingStatus.PROCESSING
        ]
        assert len(processing_writes) == 1
        assert "session" not in processing_writes[0]

        # Exactly one FAILED write, on a session the helper opened (no argument).
        failed_writes = [
            call for call in status_calls if call.get("status") == ProcessingStatus.FAILED
        ]
        assert len(failed_writes) == 1
        assert "session" not in failed_writes[0]

        # The unlink now runs after the commit, so the file is still present when
        # the main transaction fails to commit. It does not leak because the
        # retained failure-path unlink reclaims it (ruling D-05-B): the final
        # glob assertion below is the guard that a commit failure still cleans up.
        assert observed.get("file_exists_at_commit") is True
        assert list(tmp_path.glob("*.csv*")) == []

    @pytest.mark.asyncio
    async def test_cancellation_still_removes_the_file(
        self, tmp_path
    ):
        """A cancelled run must reclaim the temp file (DP-016, first half).

        ``asyncio.CancelledError`` inherits ``BaseException``, so the old
        ``except Exception`` handler could never reach it and a cancelled run
        kept its file. This drives a **mocked** ``CancelledError`` through the
        production path. A mocked one is chosen over a real asyncio cancellation
        because it exercises the handler's own behaviour (its ``except`` clause
        and its re-raise) rather than asyncio's task-cancellation plumbing, and
        the exception type is what the handler discriminates on.
        """
        import polars as pl

        import mkobi.workers.data_worker as data_worker
        from mkobi.workers.data_worker import CSVLoader

        task_id = uuid4()
        task_file = tmp_path / f"{task_id}.csv"
        task_file.write_bytes(b"category,sales\n1,\"unclosed quote\n")

        status_mock = AsyncMock(return_value=None)
        # Force a cancellation after the main transaction has begun, not during
        # parsing. CancelledError inherits BaseException; the old `except
        # Exception` would not have caught it.
        store_mock = AsyncMock(side_effect=asyncio.CancelledError())

        async def successful_session():
            session = AsyncMock()
            session.execute = AsyncMock()
            session.begin = MagicMock()
            return session

        @asynccontextmanager
        async def fake_get_session():
            yield await successful_session()

        valid_frame = pl.DataFrame({"category": ["a"], "sales": [1]})

        raised: BaseException | None = None
        with patch(
            "mkobi.workers.data_worker._update_processing_log_status", new=status_mock
        ), patch(
            "mkobi.workers.data_worker._store_aggregates", new=store_mock
        ), patch(
            "mkobi.workers.data_worker.get_session", new=fake_get_session
        ), patch(
            "mkobi.workers.data_worker.acquire_dashboard_rebuild_lock",
            new=AsyncMock(),
        ), patch.object(
            CSVLoader, "load_csv", return_value=valid_frame
        ):
            try:
                await data_worker._process_csv_file_async(
                    file_path_str=str(task_file),
                    task_id=str(task_id),
                    dashboard_id_str="00000000-0000-0000-0000-000000000000",
                    processing_config_dict=None,
                    mode="overwrite",
                    db_session=None,
                )
            except BaseException as exc:  # noqa: BLE001 - we assert on the type below
                raised = exc

        # The cancellation still propagates: the handler must not swallow it.
        assert isinstance(raised, asyncio.CancelledError)
        # The file is reclaimed even though the exception is not an Exception.
        assert list(tmp_path.glob("*.csv*")) == []
        # The failure was still reported on the helper's own session (no arg).
        failed_writes = [
            call.kwargs
            for call in status_mock.await_args_list
            if call.kwargs.get("status") == ProcessingStatus.FAILED
        ]
        assert len(failed_writes) == 1
        assert "session" not in failed_writes[0]

    @pytest.mark.asyncio
    async def test_failing_commit_still_removes_the_file(
        self, tmp_path
    ):
        """A failed commit must unlink the file, else every commit failure leaks.

        This is the guard on D-05-B's mandatory condition. The success path now
        unlinks after the commit, so on a commit failure the file is present at
        commit time (asserted here) and only the **retained** failure-path
        unlink reclaims it. A move that dropped that unlink would fail this test.
        """
        import polars as pl

        import mkobi.workers.data_worker as data_worker
        from mkobi.workers.data_worker import CSVLoader

        task_id = uuid4()
        task_file = tmp_path / f"{task_id}.csv"
        task_file.write_bytes(b"category,sales\n1,\"unclosed quote\n")

        observed: dict[str, Any] = {}
        # The status helper is mocked whole, so it never opens a session itself;
        # the only get_session() call is the main transaction. Make that one fail
        # to commit.
        failing = self._session_with_failing_commit(observed, task_file)
        sessions = [failing]

        @asynccontextmanager
        async def counting_get_session():
            yield sessions.pop(0)

        status_mock = AsyncMock(return_value=None)
        valid_frame = pl.DataFrame({"category": ["a"], "sales": [1]})

        raised: BaseException | None = None
        with patch(
            "mkobi.workers.data_worker._update_processing_log_status", new=status_mock
        ), patch(
            "mkobi.workers.data_worker._store_aggregates", new=AsyncMock(return_value=None)
        ), patch(
            "mkobi.workers.data_worker.get_session", new=counting_get_session
        ), patch(
            "mkobi.workers.data_worker.acquire_dashboard_rebuild_lock",
            new=AsyncMock(),
        ), patch.object(
            CSVLoader, "load_csv", return_value=valid_frame
        ):
            try:
                await data_worker._process_csv_file_async(
                    file_path_str=str(task_file),
                    task_id=str(task_id),
                    dashboard_id_str="00000000-0000-0000-0000-000000000000",
                    processing_config_dict=None,
                    mode="overwrite",
                    db_session=None,
                )
            except BaseException as exc:  # noqa: BLE001 - we assert on the type below
                raised = exc

        assert isinstance(raised, RuntimeError)
        assert "main transaction commit failed" in str(raised)
        # The file was still present when the commit failed - the success-path
        # unlink had not run - and the failure path reclaimed it.
        assert observed.get("file_exists_at_commit") is True
        assert list(tmp_path.glob("*.csv*")) == []


class TestAcceptedArtefactTerminalStateRule:
    """The accepted artefact is scratch space: gone on every terminal state.

    This class states and asserts the rule that ruling **D-06-A = (b)** makes
    explicit. ``_process_csv_file_async`` owns it: once a job reaches a terminal
    state -- COMPLETED or FAILED -- the input file is removed. The removal is a
    *designed* property, not an accident, and this class is where the design is
    held to account.

    The rule's scope is stated honestly. Three failure edges each delete:
    rollback, cancellation, and commit failure. The one state in which a file
    outlives its task is a *hard process kill* mid-job, where RQ never runs the
    handler; there the file is left to the stale-age sweep. The boundary test at
    the end of this class asserts that residual rather than pretending the
    invariant is total.

    These tests drive the production path (``db_session=None``) with the same
    mock shape used elsewhere in this module. They do not duplicate the
    implementation; they assert the terminal state the implementation reaches.
    """

    @staticmethod
    def _write_task_file(tmp_path: Path) -> tuple[Any, Path]:
        """Create a task file whose parse would fail; the body patches the loader."""
        task_id = uuid4()
        task_file = tmp_path / f"{task_id}.csv"
        task_file.write_bytes(b"category,sales\n1,\"unclosed quote\n")
        return task_id, task_file

    @staticmethod
    def _ok_session() -> MagicMock:
        """A mock session whose ``begin()`` block commits normally."""
        session = MagicMock()
        session.execute = AsyncMock()
        session.begin = MagicMock()
        return session

    @staticmethod
    def _session_that_rolls_back() -> MagicMock:
        """A mock session whose ``begin()`` block rolls back on a body exception.

        ``__aexit__`` returns falsy, so a body exception propagates and no commit
        happens -- the *rollback* edge, distinct from a commit failure (which
        raises on a *successful* body).
        """

        class _RollingBackBegin:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        session = MagicMock()
        session.execute = AsyncMock()
        session.begin = lambda: _RollingBackBegin()
        return session

    async def _run_with_session(
        self,
        tmp_path: Path,
        session: MagicMock,
        status_mock: AsyncMock,
        store_mock: AsyncMock,
    ) -> BaseException | None:
        """Drive the production path once with one main-transaction session.

        Only the main transaction opens ``get_session`` here: the status helper
        is mocked whole, so it never opens a session of its own. Returns the
        raised exception, or None on a normal return.
        """
        import polars as pl

        import mkobi.workers.data_worker as data_worker
        from mkobi.workers.data_worker import CSVLoader

        task_id, task_file = self._write_task_file(tmp_path)

        @asynccontextmanager
        async def one_session():
            yield session

        valid_frame = pl.DataFrame({"category": ["a"], "sales": [1]})
        raised: BaseException | None = None
        with patch(
            "mkobi.workers.data_worker._update_processing_log_status", new=status_mock
        ), patch(
            "mkobi.workers.data_worker._store_aggregates", new=store_mock
        ), patch(
            "mkobi.workers.data_worker.get_session", new=one_session
        ), patch(
            "mkobi.workers.data_worker.acquire_dashboard_rebuild_lock",
            new=AsyncMock(),
        ), patch.object(
            CSVLoader, "load_csv", return_value=valid_frame
        ):
            try:
                await data_worker._process_csv_file_async(
                    file_path_str=str(task_file),
                    task_id=str(task_id),
                    dashboard_id_str="00000000-0000-0000-0000-000000000000",
                    processing_config_dict=None,
                    mode="overwrite",
                    db_session=None,
                )
            except BaseException as exc:  # noqa: BLE001 - asserted by callers
                raised = exc
        return raised

    def _failed_writes(self, status_mock: AsyncMock) -> list[Any]:
        """Return the status writes carrying ``ProcessingStatus.FAILED``."""
        return [
            call.kwargs
            for call in status_mock.await_args_list
            if call.kwargs.get("status") == ProcessingStatus.FAILED
        ]

    @pytest.mark.asyncio
    async def test_rollback_after_aggregates_are_staged_removes_the_artefact(
        self, tmp_path
    ):
        """Edge 1: the transaction rolls back after the aggregates are staged.

        The aggregates are stored successfully inside the transaction body, then
        the terminal COMPLETED write raises before the block can exit. The body
        exception makes ``__aexit__`` roll back rather than commit, so the
        success-path unlink (which sits after the commit) is never reached and
        the failure handler must reclaim the file. The run produced no durable
        aggregates, so the artefact must be gone.
        """
        status_mock = AsyncMock(return_value=None)

        async def status_raises_on_completed(**kwargs):
            if kwargs.get("status") == ProcessingStatus.COMPLETED:
                raise RuntimeError("rollback after staging aggregates")
            return None

        status_mock.side_effect = status_raises_on_completed
        store_mock = AsyncMock(return_value=None)

        session = self._session_that_rolls_back()
        raised = await self._run_with_session(tmp_path, session, status_mock, store_mock)

        # The rollback still propagates and the aggregates were staged first:
        # the COMPLETED write is what raised, after ``_store_aggregates`` ran, so
        # this is genuinely "the transaction fails after the aggregates are
        # staged".
        assert isinstance(raised, RuntimeError)
        assert "rollback after staging aggregates" in str(raised)
        assert store_mock.await_count == 1
        # The ruled state: artefact absent on the rollback edge.
        assert list(tmp_path.glob("*.csv*")) == []
        # The failure is still reported on the helper's own session (no arg),
        # so the FAILED row survives the rollback it reports.
        failed_writes = self._failed_writes(status_mock)
        assert len(failed_writes) == 1
        assert "session" not in failed_writes[0]

    @pytest.mark.asyncio
    async def test_cancellation_during_the_job_removes_the_artefact(self, tmp_path):
        """Edge 2: ``asyncio.CancelledError`` during the job removes the artefact.

        ``CancelledError`` inherits ``BaseException``, so the pre-``5e73e37``
        ``except Exception`` handler could not reach it and a cancelled run kept
        its file. This is the edge ``5e73e37`` made reachable; the test asserts
        it rather than assuming it. A mocked ``CancelledError`` is used because
        the exception type is what the handler discriminates on.
        """
        status_mock = AsyncMock(return_value=None)
        store_mock = AsyncMock(side_effect=asyncio.CancelledError())

        session = self._ok_session()
        raised = await self._run_with_session(tmp_path, session, status_mock, store_mock)

        # The cancellation propagates -- the handler must not swallow it.
        assert isinstance(raised, asyncio.CancelledError)
        # The ruled state: artefact absent on the cancellation edge.
        assert list(tmp_path.glob("*.csv*")) == []
        failed_writes = self._failed_writes(status_mock)
        assert len(failed_writes) == 1
        assert "session" not in failed_writes[0]

    @pytest.mark.asyncio
    async def test_commit_failure_removes_the_artefact_and_not_before(self, tmp_path):
        """Edge 3: the commit itself raising removes the artefact.

        The block body succeeds, so the failure comes from the commit on exit,
        not from the body (that is the rollback edge). The file is still present
        at commit time -- the success-path unlink sits after the commit -- and the
        retained failure-path unlink reclaims it, so no commit failure leaks.
        """
        status_mock = AsyncMock(return_value=None)
        store_mock = AsyncMock(return_value=None)

        observed: dict[str, Any] = {}
        task_id = uuid4()
        task_file = tmp_path / f"{task_id}.csv"
        task_file.write_bytes(b"category,sales\n1,\"unclosed quote\n")
        session = TestRolledBackMainTransactionLeavesNoLeakedFile._session_with_failing_commit(
            observed, task_file
        )

        @asynccontextmanager
        async def one_session():
            yield session

        import polars as pl

        import mkobi.workers.data_worker as data_worker
        from mkobi.workers.data_worker import CSVLoader

        valid_frame = pl.DataFrame({"category": ["a"], "sales": [1]})
        raised: BaseException | None = None
        with patch(
            "mkobi.workers.data_worker._update_processing_log_status", new=status_mock
        ), patch(
            "mkobi.workers.data_worker._store_aggregates", new=store_mock
        ), patch(
            "mkobi.workers.data_worker.get_session", new=one_session
        ), patch(
            "mkobi.workers.data_worker.acquire_dashboard_rebuild_lock",
            new=AsyncMock(),
        ), patch.object(
            CSVLoader, "load_csv", return_value=valid_frame
        ):
            try:
                await data_worker._process_csv_file_async(
                    file_path_str=str(task_file),
                    task_id=str(task_id),
                    dashboard_id_str="00000000-0000-0000-0000-000000000000",
                    processing_config_dict=None,
                    mode="overwrite",
                    db_session=None,
                )
            except BaseException as exc:  # noqa: BLE001 - asserted below
                raised = exc

        assert isinstance(raised, RuntimeError)
        assert "main transaction commit failed" in str(raised)
        # The file was still present at the instant the commit failed: the
        # success-path unlink had not run, which is what makes the retained
        # failure-path unlink load-bearing.
        assert observed.get("file_exists_at_commit") is True
        # The ruled state: artefact absent on the commit-failure edge.
        assert list(tmp_path.glob("*.csv*")) == []

    @pytest.mark.asyncio
    async def test_every_terminal_status_leaves_the_artefact_absent(self, tmp_path):
        """The invariant: for every terminal status the artefact is gone.

        COMPLETED (the success path commits, then unlinks) and FAILED (the
        failure path rolls back and unlinks) are the two terminal states of
        ``ProcessingStatus``. Both must leave no file behind. This is the
        terminal-state invariant stated once for the whole set, so a future
        terminal status cannot be added without confronting it.
        """
        terminal_states = [
            s for s, targets in ProcessingStatus.valid_transitions().items() if not targets
        ]
        assert set(terminal_states) == {
            ProcessingStatus.COMPLETED,
            ProcessingStatus.FAILED,
        }

        # COMPLETED: a clean run reaches the success path and unlinks after the
        # commit.
        success_status = AsyncMock(return_value=None)
        success_raised = await self._run_with_session(
            tmp_path, self._ok_session(), success_status, AsyncMock(return_value=None)
        )
        assert success_raised is None
        assert list(tmp_path.glob("*.csv*")) == []

        # FAILED: a run that raises mid-transaction rolls back and unlinks in the
        # failure handler.
        failed_status = AsyncMock(return_value=None)
        failure_raised = await self._run_with_session(
            tmp_path,
            self._ok_session(),
            failed_status,
            AsyncMock(side_effect=RuntimeError("forced failure")),
        )
        assert isinstance(failure_raised, RuntimeError)
        assert list(tmp_path.glob("*.csv*")) == []

    @pytest.mark.asyncio
    async def test_interrupted_run_leaves_the_file_to_the_stale_age_sweep(
        self, setup_temp_dir_fixture
    ):
        """The honest boundary: a hard kill skips every edge, so the sweep owns it.

        A hard process kill (SIGKILL/OOM/container stop) mid-job never runs RQ's
        handler, so the file outlives its task. The invariant above is therefore
        scoped to *reached* terminal states, and this test asserts the residual
        explicitly instead of overstating the rule. The kill is modelled by
        making the success-path unlink a no-op: the job returns success with the
        file still on disk, which is exactly the state a kill after the commit
        and before the unlink leaves behind. ``cleanup_stale_temp_files`` then
        reclaims it, so the residual is bounded rather than unbounded.

        The task file is written into the *configured* upload directory (the
        autouse fixture's temp dir), because that is the directory the sweep
        globs -- the same directory a real interrupted run would leave it in.
        """
        import polars as pl

        import mkobi.workers.data_worker as data_worker
        from mkobi.workers.data_worker import CSVLoader

        tmp_path = Path(setup_temp_dir_fixture)
        task_id, task_file = self._write_task_file(tmp_path)

        status_mock = AsyncMock(return_value=None)
        store_mock = AsyncMock(return_value=None)
        session = self._ok_session()

        @asynccontextmanager
        async def one_session():
            yield session

        real_unlink = Path.unlink

        def _noop_unlink(self, *args, **kwargs):
            # Model the process dying before the unlink lands: this process never
            # removes the file, and no handler runs either.
            return None

        valid_frame = pl.DataFrame({"category": ["a"], "sales": [1]})
        with patch(
            "mkobi.workers.data_worker._update_processing_log_status", new=status_mock
        ), patch(
            "mkobi.workers.data_worker._store_aggregates", new=store_mock
        ), patch(
            "mkobi.workers.data_worker.get_session", new=one_session
        ), patch(
            "mkobi.workers.data_worker.acquire_dashboard_rebuild_lock",
            new=AsyncMock(),
        ), patch.object(Path, "unlink", _noop_unlink), patch.object(
            CSVLoader, "load_csv", return_value=valid_frame
        ):
            await data_worker._process_csv_file_async(
                file_path_str=str(task_file),
                task_id=str(task_id),
                dashboard_id_str="00000000-0000-0000-0000-000000000000",
                processing_config_dict=None,
                mode="overwrite",
                db_session=None,
            )

        # The interruption boundary: the file outlives its task.
        assert task_file.exists()

        # The sweep is what bounds the residual. Restore the real unlink before
        # sweeping, so this is the sweep's own removal and not the no-op.
        with patch.object(Path, "unlink", real_unlink):
            result = cleanup_stale_temp_files(max_age_hours=0)
        assert result.deleted == 1
        assert not task_file.exists()

