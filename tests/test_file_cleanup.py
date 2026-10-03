"""Tests for file cleanup utilities."""
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

from mkobi.services.file_cleanup import cleanup_stale_temp_files


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

        deleted_count = cleanup_stale_temp_files()

        assert deleted_count == 1
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
        deleted_count = cleanup_stale_temp_files(max_age_hours=2)
        assert deleted_count == 1

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
        deleted_count = cleanup_stale_temp_files(max_age_hours=5)
        assert deleted_count == 0
        assert file_path.exists()

    def test_cleanup_stale_temp_files_nonexistent_directory(self, monkeypatch):
        """Test cleanup when upload directory doesn't exist."""
        monkeypatch.setattr(
            "mkobi.services.file_cleanup.get_config",
            lambda: MagicMock(upload_temp_dir="/nonexistent/path", stale_file_threshold_hours=24)
        )

        deleted_count = cleanup_stale_temp_files()
        assert deleted_count == 0

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

        deleted_count = cleanup_stale_temp_files(max_age_hours=0)
        assert deleted_count == 2  # All files should be deleted

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

        deleted_count = cleanup_stale_temp_files(max_age_hours=-1)
        assert deleted_count == 0  # Negative threshold is invalid, no files deleted
        assert file1.exists()  # File should still exist

        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)




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
    """A failed commit of the main transaction must not leak the temp file.

    The success path unlinks the temp file *inside* the transaction body, so a
    commit failure rolls the status back but the file is already gone and the
    compensation's ``if file_path.exists()`` guard makes its own unlink a no-op.
    Moving the unlink after the commit would leak the file here.
    """

    @staticmethod
    def _session_with_failing_commit(observed: dict[str, Any], task_file: Path) -> MagicMock:
        """A mock session whose ``begin()`` block raises when it commits.

        Records whether the temp file still exists at the moment the commit
        fails (``__aexit__``, after the block body ran) - that is the instant
        that distinguishes an unlink kept inside the transaction body (already
        gone) from one moved after the commit (still present, and leaked on any
        path that does not reach it).
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
        from mkobi.models.enums import ProcessingStatus
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

        # The unlink ran inside the transaction body: the file was already gone
        # when the main transaction failed to commit, and the compensation's own
        # unlink was therefore a no-op. Moving the unlink after the commit would
        # leave the file present at this instant.
        assert observed.get("file_exists_at_commit") is False
        assert list(tmp_path.glob("*.csv*")) == []
