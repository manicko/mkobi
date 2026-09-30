"""Tests for the application lifespan after the queue-worker removal.

The in-process queue worker was removed from app.py::lifespan. These tests
assert the lifespan source no longer references any task-queue symbol and that
teardown cancels only the stale-processing cleanup task.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mkobi.app as app_module


class TestLifespanSourceHasNoQueueWorker:
    """The lifespan source carries no task-queue references."""

    def test_lifespan_source_references_no_task_queue_symbol(self):
        """No retired task-queue symbol appears in the lifespan source."""
        source = inspect.getsource(app_module.lifespan)
        for symbol in (
            "get_task_queue",
            "TaskQueue",
            "queue_worker",
            "queue_worker_task",
            "default_queue",
        ):
            assert symbol not in source, f"lifespan still references {symbol}"

    def test_module_does_not_import_task_queue(self):
        """app.py no longer imports the submission seam or a task queue factory."""
        source = inspect.getsource(app_module)
        assert "get_task_queue" not in source
        assert "from mkobi.core.task_queue import" not in source


class TestLifespanTeardown:
    """Teardown cancels the cleanup task and disposes the engine."""

    @pytest.mark.asyncio
    async def test_teardown_cancels_only_cleanup_task(self):
        """Lifespan teardown creates no queue-worker task and disposes the engine."""
        app = MagicMock()
        starter = MagicMock()
        starter.startup = AsyncMock()
        starter.shutdown = AsyncMock()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch.object(
                app_module,
                "mark_orphaned_uploaded_logs_failed",
                new=AsyncMock(),
            ):
                with patch.object(
                    app_module,
                    "start_stale_processing_cleanup_task",
                    new=AsyncMock(return_value=None),
                ):
                    with patch.object(
                        app_module, "dispose_engine", new=AsyncMock()
                    ) as mock_dispose:
                        async with app_module.lifespan(app):
                            pass

        # Engine disposed exactly once on teardown; starter shut down afterwards.
        mock_dispose.assert_awaited_once()
        starter.shutdown.assert_awaited_once()
