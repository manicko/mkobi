"""Tests for the RQ submission boundary in mkobi.core.task_queue.

Covers three properties:
- the queue receives the job with the expected arguments against the test Redis;
- the module no longer exposes the retired in-memory TaskQueue symbols;
- no service module imports rq directly (asserted with ast, not observed).
"""

import ast
import os
from pathlib import Path

import pytest
import redis
import rq

import mkobi.core.task_queue as task_queue


def _test_redis_connection() -> redis.Redis:
    """Build a Redis connection from the test environment."""
    return redis.Redis(
        host=os.environ.get("REDIS__HOST", "localhost"),
        port=int(os.environ.get("REDIS__PORT", "6379")),
        db=int(os.environ.get("REDIS__DB", "0")),
    )


@pytest.fixture
def coherent_config(monkeypatch):
    """Pin the Redis config to the test broker and reset both caches.

    Other test modules mutate REDIS__* and clear the settings cache without
    restoring it, so this test must establish its own coherent config before
    building the queue.
    """
    from mkobi.config import clear_config_cache

    monkeypatch.setenv("REDIS__HOST", os.environ.get("REDIS__HOST", "localhost"))
    monkeypatch.setenv("REDIS__PORT", os.environ.get("REDIS__PORT", "6379"))
    monkeypatch.setenv("REDIS__DB", os.environ.get("REDIS__DB", "0"))
    clear_config_cache()
    task_queue.get_rq_queue.cache_clear()
    yield
    clear_config_cache()
    task_queue.get_rq_queue.cache_clear()


@pytest.mark.asyncio
class TestQueueReceivesJob:
    """The queue receives the submitted job with the expected arguments."""

    async def test_enqueue_job_delivers_to_queue(self, coherent_config):
        """enqueue_job places a job on the RQ queue with the expected args/kwargs."""
        connection = _test_redis_connection()
        queue = rq.Queue(task_queue.DEFAULT_QUEUE_NAME, connection=connection)
        original_len = connection.llen(queue.key)
        job_id: str | None = None

        def dummy_job(width: int, label: str) -> int:
            """Trivial job callable for the enqueue round-trip."""
            return width

        try:
            job_id = await task_queue.enqueue_job(dummy_job, width=7, label="hello")

            assert job_id
            assert connection.llen(queue.key) == original_len + 1

            job = rq.job.Job.fetch(job_id, connection=connection)
            assert job.kwargs == {"width": 7, "label": "hello"}
        finally:
            # Drain what this test enqueued so the assertion is isolated.
            while connection.llen(queue.key) > original_len:
                connection.rpop(queue.key)
            if job_id is not None:
                connection.delete(f"rq:job:{job_id}")
            connection.close()


class TestRetiredSymbolsRemoved:
    """The in-memory TaskQueue surface is gone."""

    @pytest.mark.parametrize(
        "symbol", ["TaskQueue", "default_queue", "get_task_queue"]
    )
    def test_module_does_not_expose_symbol(self, symbol):
        """The module exposes none of the retired in-memory queue symbols."""
        assert not hasattr(task_queue, symbol)


class TestServicesDoNotImportRq:
    """No module under src/mkobi/services/ imports rq; the seam owns that."""

    def test_no_service_module_imports_rq(self):
        """Assert the layering rule: services never import rq directly."""
        services_dir = Path(task_queue.__file__).resolve().parents[1] / "services"
        offenders: list[str] = []

        for path in services_dir.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "rq" or alias.name.startswith("rq."):
                            offenders.append(f"{path}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "rq" or module.startswith("rq."):
                        offenders.append(f"{path}: from {module} import ...")

        assert offenders == [], (
            "Service modules must not import rq; the submission seam is "
            f"mkobi.core.task_queue. Offenders: {offenders}"
        )
