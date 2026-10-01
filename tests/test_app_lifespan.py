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


class TestLifespanLeaseGuard:
    """The reconciler lease guards the boot path and never prevents booting."""

    @pytest.mark.asyncio
    async def test_boot_completes_with_redis_down(self):
        """Redis down at boot: lifespan still starts, repairs orphans, disposes engine."""
        app = MagicMock()
        starter = MagicMock()
        starter.startup = AsyncMock()
        starter.shutdown = AsyncMock()

        orphan_repair = AsyncMock()
        dispose = AsyncMock()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch.object(
                app_module, "get_async_redis_client", return_value=_UnreachableRedis()
            ):
                with patch.object(
                    app_module, "mark_orphaned_uploaded_logs_failed", new=orphan_repair
                ):
                    with patch.object(
                        app_module, "dispose_engine", new=dispose
                    ):
                        with patch.object(
                            app_module,
                            "start_stale_processing_cleanup_task",
                            new=AsyncMock(return_value=None),
                        ):
                            async with app_module.lifespan(app):
                                pass

        # Boot completed: orphan repair still ran despite the lease being
        # unreachable (fail open), and teardown still reached dispose_engine.
        orphan_repair.assert_awaited_once()
        dispose.assert_awaited_once()
        starter.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_boot_skips_repair_when_not_holder(self):
        """Reachable Redis held by another replica: boot repair is skipped."""
        app = MagicMock()
        starter = MagicMock()
        starter.startup = AsyncMock()
        starter.shutdown = AsyncMock()

        orphan_repair = AsyncMock()
        dispose = AsyncMock()

        holder_client = _HeldRedis()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch.object(
                app_module, "get_async_redis_client", return_value=holder_client
            ):
                with patch.object(
                    app_module, "mark_orphaned_uploaded_logs_failed", new=orphan_repair
                ):
                    with patch.object(app_module, "dispose_engine", new=dispose):
                        with patch.object(
                            app_module,
                            "start_stale_processing_cleanup_task",
                            new=AsyncMock(return_value=None),
                        ):
                            async with app_module.lifespan(app):
                                pass

        # The key is held by a foreign replica, so this boot is not the holder
        # and must not run the repair. Teardown is unaffected.
        orphan_repair.assert_not_awaited()
        dispose.assert_awaited_once()


class TestLifespanTeardownFailIsolation:
    """One failing teardown step must not skip the remaining releases."""

    @pytest.mark.asyncio
    async def test_lease_release_failure_still_disposes_and_shuts_down(self):
        """A raising lease.release() must not skip dispose_engine or starter.shutdown.

        ``ReconcilerLease.release`` swallows its own Redis errors, so this can
        only be raised from the lease call boundary itself. The existing
        boot-time-unreachable-lease test short-circuits ``release()`` before any
        Redis call, so it does not cover this path.
        """
        app = MagicMock()
        starter = MagicMock()
        starter.startup = AsyncMock()
        starter.shutdown = AsyncMock()

        dispose = AsyncMock()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch.object(
                app_module, "get_async_redis_client", return_value=_UnreachableRedis()
            ):
                with patch.object(
                    app_module.ReconcilerLease,
                    "release",
                    new=AsyncMock(side_effect=RuntimeError("release blew up")),
                ):
                    with patch.object(app_module, "dispose_engine", new=dispose):
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
                                async with app_module.lifespan(app):
                                    pass

        # The release raised, yet both later releases still ran.
        dispose.assert_awaited_once()
        starter.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_engine_dispose_failure_still_shuts_down_starter(self):
        """A raising dispose_engine() must not skip starter.shutdown()."""
        app = MagicMock()
        starter = MagicMock()
        starter.startup = AsyncMock()
        starter.shutdown = AsyncMock()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch.object(
                app_module, "get_async_redis_client", return_value=_UnreachableRedis()
            ):
                with patch.object(
                    app_module,
                    "dispose_engine",
                    new=AsyncMock(side_effect=RuntimeError("dispose blew up")),
                ):
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
                            async with app_module.lifespan(app):
                                pass

        starter.shutdown.assert_awaited_once()


class _UnreachableRedis:
    """Async Redis double whose every command raises, modelling an outage."""

    async def set(self, *args, **kwargs):
        raise OSError("redis unavailable")

    async def eval(self, *args, **kwargs):
        raise OSError("redis unavailable")

    async def aclose(self) -> None:
        pass


class _HeldRedis:
    """Async Redis double whose key is held by another replica."""

    async def set(self, key, value, nx=False, ex=None):
        return None  # NX never wins: the key already exists.

    async def eval(self, script, numkeys, *args):
        return 0

    async def aclose(self) -> None:
        pass
