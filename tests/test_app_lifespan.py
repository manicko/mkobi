"""Tests for the application lifespan after the queue-worker removal.

The in-process queue worker was removed from app.py::lifespan. These tests
assert the lifespan source no longer references any task-queue symbol, that
teardown cancels only the stale-processing cleanup task, and that the orphan
reclamation is NOT run at boot - it rides the lease-guarded periodic loop
started here, so a stranded ``uploaded`` row recovers on a tick, not only on a
restart.
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

    def test_lifespan_does_not_run_the_orphan_sweep_at_boot(self):
        """The boot path no longer runs the orphan reclamation.

        The sweep moved onto the lease-guarded periodic loop, so it must not
        appear in the lifespan body at all. This is the pin that replaced the
        former boot-only call.
        """
        source = inspect.getsource(app_module.lifespan)
        assert "mark_orphaned_uploaded_logs_failed" not in source
        assert "orphan" not in source.lower().replace("orphan reclamation", "")


class TestLifespanTeardown:
    """Teardown cancels the cleanup task and disposes the engine."""

    @pytest.mark.asyncio
    async def test_teardown_cancels_only_cleanup_task(self):
        """Lifespan teardown creates no queue-worker task and disposes the engine."""
        app = MagicMock()
        starter = MagicMock()
        starter.startup = AsyncMock()
        starter.shutdown = AsyncMock()

        # Patch site 1 of 5: the whole file pins the boot path to NOT sweep
        # orphans. It rides the periodic loop instead, so every lifespan test
        # that used to patch-and-permit the boot call now patches-and-forbids it.
        orphan_repair = AsyncMock()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch("mkobi.workers.data_worker.mark_orphaned_uploaded_logs_failed", new=orphan_repair):
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
        # The boot path must not reclaim orphans any more.
        orphan_repair.assert_not_awaited()


class TestLifespanLeaseGuard:
    """The lease is elected at boot; the orphan sweep rides the periodic loop."""

    @pytest.mark.asyncio
    async def test_boot_acquires_lease_but_does_not_sweep_orphans(self):
        """A boot that wins the lease elects itself but runs no orphan sweep.

        The sweep now runs on the periodic loop; running it here as well would
        make it boot-only again for the lease-acquired path.
        """
        app = MagicMock()
        starter = MagicMock()
        starter.startup = AsyncMock()
        starter.shutdown = AsyncMock()

        # Patch site 2 of 5.
        orphan_repair = AsyncMock()
        periodic_started = AsyncMock(return_value=None)
        dispose = AsyncMock()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch.object(
                app_module, "get_async_redis_client", return_value=_FreeRedis()
            ):
                with patch("mkobi.workers.data_worker.mark_orphaned_uploaded_logs_failed", new=orphan_repair):
                    with patch.object(app_module, "dispose_engine", new=dispose):
                        with patch.object(
                            app_module,
                            "start_stale_processing_cleanup_task",
                            new=periodic_started,
                        ):
                            async with app_module.lifespan(app):
                                pass

        # Boot elected the lease and started the periodic loop, but did not sweep.
        assert app.state.reconciler_status.lease_state.value == "holder"
        periodic_started.assert_called_once()
        orphan_repair.assert_not_awaited()
        dispose.assert_awaited_once()
        starter.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_boot_completes_with_redis_down(self):
        """Redis down at boot: lifespan still starts, elects nobody, starts the loop."""
        app = MagicMock()
        starter = MagicMock()
        starter.startup = AsyncMock()
        starter.shutdown = AsyncMock()

        # Patch site 3 of 5.
        orphan_repair = AsyncMock()
        periodic_started = AsyncMock(return_value=None)
        dispose = AsyncMock()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch.object(
                app_module, "get_async_redis_client", return_value=_UnreachableRedis()
            ):
                with patch("mkobi.workers.data_worker.mark_orphaned_uploaded_logs_failed", new=orphan_repair):
                    with patch.object(app_module, "dispose_engine", new=dispose):
                        with patch.object(
                            app_module,
                            "start_stale_processing_cleanup_task",
                            new=periodic_started,
                        ):
                            async with app_module.lifespan(app):
                                pass

        # Boot completed despite the unreachable lease (fail open) and still
        # started the periodic loop; teardown reached dispose_engine.
        assert app.state.reconciler_status.lease_state.value == "unprotected"
        periodic_started.assert_called_once()
        orphan_repair.assert_not_awaited()
        dispose.assert_awaited_once()
        starter.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_boot_not_holder_still_starts_the_periodic_loop(self):
        """Reachable Redis held by another replica: this replica starts the loop.

        The loop is what re-elects later, so it must start even when this boot
        is not the holder. The skip case itself is covered at loop level in
        tests/test_data_worker.py::TestReconcilerLoop, which asserts a
        non-holder performs no sweep.
        """
        app = MagicMock()
        starter = MagicMock()
        starter.startup = AsyncMock()
        starter.shutdown = AsyncMock()

        # Patch site 4 of 5.
        orphan_repair = AsyncMock()
        periodic_started = AsyncMock(return_value=None)
        dispose = AsyncMock()

        holder_client = _HeldRedis()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch.object(
                app_module, "get_async_redis_client", return_value=holder_client
            ):
                with patch("mkobi.workers.data_worker.mark_orphaned_uploaded_logs_failed", new=orphan_repair):
                    with patch.object(app_module, "dispose_engine", new=dispose):
                        with patch.object(
                            app_module,
                            "start_stale_processing_cleanup_task",
                            new=periodic_started,
                        ):
                            async with app_module.lifespan(app):
                                pass

        # The key is held by a foreign replica, so this boot is not the holder.
        assert app.state.reconciler_status.lease_state.value == "not_holder"
        periodic_started.assert_called_once()
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
        # Patch site 5 of 5.
        orphan_repair = AsyncMock()

        with patch.object(app_module, "DatabaseStarter", return_value=starter):
            with patch.object(
                app_module, "get_async_redis_client", return_value=_UnreachableRedis()
            ):
                with patch.object(
                    app_module.ReconcilerLease,
                    "release",
                    new=AsyncMock(side_effect=RuntimeError("release blew up")),
                ):
                    with patch("mkobi.workers.data_worker.mark_orphaned_uploaded_logs_failed", new=orphan_repair):
                        with patch.object(app_module, "dispose_engine", new=dispose):
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
        orphan_repair.assert_not_awaited()

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


class _FreeRedis:
    """Async Redis double whose key is free, so the first NX wins."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self._data:
            return None
        self._data[key] = value
        return True

    async def eval(self, *args, **kwargs):
        return 1

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


