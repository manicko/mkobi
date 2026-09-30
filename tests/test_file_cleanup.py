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
from datetime import datetime, UTC, timedelta

from mkobi.services.file_cleanup import cleanup_stale_temp_files, cleanup_task_files, cleanup_old_processing_logs


@pytest.fixture(autouse=True)
def setup_temp_dir_fixture(monkeypatch):
    """Set up a temporary directory for upload tests."""
    temp_dir = tempfile.mkdtemp()
    
    class MockConfig:
        upload_temp_dir = temp_dir
        stale_file_threshold_hours = 24
    
    def get_config_mock():
        return MockConfig()
    
    monkeypatch.setattr("mkobi.services.file_cleanup.get_config", get_config_mock)
    monkeypatch.setattr("mkobi.config.get_config", get_config_mock)
    
    yield temp_dir
    
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestFileCleanup:
    """Tests for file cleanup utilities."""

    def test_cleanup_task_files_deletes_matching_files(self, setup_temp_dir_fixture):
        """Test cleanup_task_files deletes files matching task ID."""
        temp_dir = setup_temp_dir_fixture
        task_id = uuid4()
        # Create test files
        for suffix in ["", ".gz"]:
            file_path = Path(temp_dir) / f"test_{task_id}{suffix}.csv"
            file_path.write_text("test,data\n1,2\n")

        # Create a file that should NOT be deleted
        other_id = uuid4()
        other_file = Path(temp_dir) / f"other_{other_id}.csv"
        other_file.write_text("other\n")

        cleanup_task_files(task_id)

        # Files with task_id should be deleted
        remaining_files = list(Path(temp_dir).glob(f"*{task_id}*.csv*"))
        assert len(remaining_files) == 0
        # Other files should remain
        assert other_file.exists()

    def test_cleanup_task_files_no_matching_files(self, setup_temp_dir_fixture):
        """Test cleanup_task_files with no matching files."""
        temp_dir = setup_temp_dir_fixture
        task_id = uuid4()
        # Create a file that doesn't match
        other_file = Path(temp_dir) / "other_file.csv"
        other_file.write_text("other\n")

        cleanup_task_files(task_id)

        # No crash, other file should still exist
        assert other_file.exists()

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


class TestCleanupOldProcessingLogs:
    """Tests for cleanup_old_processing_logs functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_old_processing_logs_deletes_terminal_states(self, async_db_session):
        """Test that cleanup_old_processing_logs deletes COMPLETED and FAILED logs older than cutoff."""
        from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository

        repo = ProcessingLogRepository()

        # Create old COMPLETED log (35 days ago)
        old_completed_time = datetime.now(UTC) - timedelta(days=35)
        from sqlalchemy import update as sa_update
        from mkobi.db.models.processing_logs import ProcessingLog

        old_completed = await repo.create_log(
            dashboard_id=None,
            status="completed",
            message="Old completed log",
            db=async_db_session,
        )
        # Manually set finished_at to simulate old entry
        stmt = sa_update(ProcessingLog).where(ProcessingLog.id == old_completed.id).values({
            "finished_at": old_completed_time,
            "started_at": old_completed_time,
        })
        await async_db_session.execute(stmt)
        await async_db_session.commit()

        # Create old FAILED log (40 days ago)
        old_failed_time = datetime.now(UTC) - timedelta(days=40)
        old_failed = await repo.create_log(
            dashboard_id=None,
            status="failed",
            message="Old failed log",
            db=async_db_session,
        )
        stmt = sa_update(ProcessingLog).where(ProcessingLog.id == old_failed.id).values({
            "finished_at": old_failed_time,
            "started_at": old_failed_time,
        })
        await async_db_session.execute(stmt)
        await async_db_session.commit()

        # Create a RECENT COMPLETED log (5 days ago) - should NOT be deleted
        recent_completed_time = datetime.now(UTC) - timedelta(days=5)
        recent_completed = await repo.create_log(
            dashboard_id=None,
            status="completed",
            message="Recent completed log",
            db=async_db_session,
        )
        stmt = sa_update(ProcessingLog).where(ProcessingLog.id == recent_completed.id).values({
            "finished_at": recent_completed_time,
            "started_at": recent_completed_time,
        })
        await async_db_session.execute(stmt)
        await async_db_session.commit()

        # Create a STARTED log - should NOT be deleted (non-terminal state)
        started_log = await repo.create_log(
            dashboard_id=None,
            status="started",
            message="Started log",
            db=async_db_session,
        )

        # Run cleanup with injected session for test isolation
        deleted_count = await cleanup_old_processing_logs(retention_days=30, session=async_db_session)

        # Commit to make changes visible within the test session
        await async_db_session.commit()

        assert deleted_count == 2, "Should have deleted 2 old logs (COMPLETED and FAILED)"

        # Verify old logs are deleted
        deleted_completed = await repo.get_by_id(old_completed.id, db=async_db_session)
        assert deleted_completed is None

        deleted_failed = await repo.get_by_id(old_failed.id, db=async_db_session)
        assert deleted_failed is None

        # Verify recent COMPLETED log still exists
        existing_completed = await repo.get_by_id(recent_completed.id, db=async_db_session)
        assert existing_completed is not None
        assert existing_completed.status == "completed"

        # Verify STARTED log still exists (non-terminal state never deleted)
        existing_started = await repo.get_by_id(started_log.id, db=async_db_session)
        assert existing_started is not None
        assert existing_started.status == "started"

    @pytest.mark.asyncio
    async def test_cleanup_old_processing_logs_respects_non_terminal_states(
        self, async_db_session
    ):
        """Test that non-terminal states (STARTED, UPLOADED, PROCESSING) are never deleted."""
        from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository

        repo = ProcessingLogRepository()

        # Create old logs in non-terminal states
        old_time = datetime.now(UTC) - timedelta(days=40)
        from sqlalchemy import update as sa_update
        from mkobi.db.models.processing_logs import ProcessingLog

        created_log_ids = []
        for status in ["started", "uploaded", "processing"]:
            log = await repo.create_log(
                dashboard_id=None,
                status=status,
                message=f"Old {status} log",
                db=async_db_session,
            )
            created_log_ids.append(log.id)
            # Manually set started_at to simulate old entry
            stmt = sa_update(ProcessingLog).where(ProcessingLog.id == log.id).values({
                "started_at": old_time,
            })
            await async_db_session.execute(stmt)
            await async_db_session.commit()

        # Run cleanup with injected session for test isolation
        deleted_count = await cleanup_old_processing_logs(retention_days=30, session=async_db_session)

        # Commit to make changes visible within the test session
        await async_db_session.commit()

        assert deleted_count == 0, "Non-terminal states should never be deleted"

        # Verify all created logs still exist
        for log_id in created_log_ids:
            log = await repo.get_by_id(log_id, db=async_db_session)
            assert log is not None, f"Log {log_id} should still exist"


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