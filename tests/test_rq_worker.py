"""Tests for RQ worker startup retry wrapper."""

import inspect
from unittest.mock import MagicMock

import pytest

from mkobi.rq_worker_wrapper import (
    check_redis_connection,
    check_worker_registered,
    MAX_RETRIES,
    BASE_DELAY_SECONDS,
    start_rq_worker,
)


@pytest.mark.asyncio
class TestRQWorkerRetry:
    """Tests for RQ worker connection retry logic."""

    async def test_check_redis_connection_succeeds_first_attempt(self, mocker):
        """Test that connection succeeds on first attempt without retry."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.close.return_value = None

        mocker.patch(
            "mkobi.rq_worker_wrapper.redis.Redis.from_url",
            return_value=mock_client,
        )

        result = await check_redis_connection("redis://localhost:6379/0")

        assert result is True
        mock_client.ping.assert_called_once()
        mock_client.close.assert_called_once()

    async def test_check_redis_connection_retries_on_failure(self, mocker):
        """Test that connection retries on failure with exponential backoff."""
        sleep_calls = []
        mocker.patch(
            "mkobi.rq_worker_wrapper.asyncio.sleep",
            side_effect=lambda d: sleep_calls.append(d),
        )

        # Make it fail 2 times, succeed on 3rd (MAX_RETRIES = 3)
        call_index = [0]

        def create_mock_client(url):
            client = MagicMock()
            if call_index[0] < MAX_RETRIES - 1:
                client.ping.side_effect = ConnectionError("Connection refused")
            else:
                client.ping.return_value = True
            client.close.return_value = None
            call_index[0] += 1
            return client

        mocker.patch(
            "mkobi.rq_worker_wrapper.redis.Redis.from_url",
            side_effect=create_mock_client,
        )

        result = await check_redis_connection("redis://localhost:6379/0")

        assert result is True
        # Should have slept for 2^0, 2^1 seconds (not after final attempt)
        assert len(sleep_calls) == MAX_RETRIES - 1
        assert sleep_calls[0] == 2 ** 0  # 1 second
        assert sleep_calls[1] == 2 ** 1  # 2 seconds

    async def test_check_redis_connection_stops_after_max_retries(self, mocker):
        """Test that retry stops after MAX_RETRIES failures without sleeping after final attempt."""
        sleep_calls = []

        mocker.patch(
            "mkobi.rq_worker_wrapper.asyncio.sleep",
            side_effect=lambda d: sleep_calls.append(d),
        )

        # Always fail
        mocker.patch(
            "mkobi.rq_worker_wrapper.redis.Redis.from_url",
            return_value=MagicMock(
                ping=MagicMock(side_effect=ConnectionError("Connection refused")),
                close=MagicMock(),
            ),
        )

        with pytest.raises(ConnectionError) as exc_info:
            await check_redis_connection("redis://localhost:6379/0")

        assert "Failed to connect to Redis after 3 attempts" in str(exc_info.value)
        # Should have slept for attempts 0 and 1 only (not after attempt 2, the final)
        assert len(sleep_calls) == MAX_RETRIES - 1
        assert sleep_calls == [1, 2]  # 2^0, 2^1

    async def test_check_redis_connection_exponential_backoff(self, mocker):
        """Test exponential backoff timing: delay = 2^attempt seconds."""
        sleep_calls = []

        mocker.patch(
            "mkobi.rq_worker_wrapper.asyncio.sleep",
            side_effect=lambda d: sleep_calls.append(d),
        )

        # Make it fail 2 times, succeed on 3rd
        call_index = [0]

        def create_mock_client(url):
            client = MagicMock()
            if call_index[0] < MAX_RETRIES - 1:
                client.ping.side_effect = ConnectionError("Connection refused")
            else:
                client.ping.return_value = True
            client.close.return_value = None
            call_index[0] += 1
            return client

        mocker.patch(
            "mkobi.rq_worker_wrapper.redis.Redis.from_url",
            side_effect=create_mock_client,
        )

        result = await check_redis_connection("redis://localhost:6379/0")

        assert result is True
        # Verify exponential backoff: 2^0, 2^1
        expected_delays = [BASE_DELAY_SECONDS ** i for i in range(MAX_RETRIES - 1)]
        assert sleep_calls == expected_delays


class TestStartRQWorker:
    """Tests for start_rq_worker function."""

    def test_start_rq_worker_exits_on_connection_failure(self, mocker):
        """Test that worker exits with code 1 when Redis connection fails."""
        mocker.patch(
            "mkobi.rq_worker_wrapper.check_redis_connection",
            side_effect=ConnectionError("Redis unavailable"),
        )
        mocker.patch("mkobi.rq_worker_wrapper.rq.Queue")
        mocker.patch("mkobi.rq_worker_wrapper.rq.Worker")
        mock_exit = mocker.patch("sys.exit")

        start_rq_worker("redis://localhost:6379/0")

        mock_exit.assert_called_once_with(1)

    def test_start_rq_worker_uses_config_url_when_none(self, mocker, monkeypatch):
        """Test that worker uses Redis URL from config when None is passed."""
        monkeypatch.setenv("REDIS__HOST", "confighost")
        monkeypatch.setenv("REDIS__PORT", "6380")
        monkeypatch.setenv("REDIS__DB", "1")
        monkeypatch.setenv("ENV", "test")
        monkeypatch.setenv("DATABASE__HOST", "localhost")
        monkeypatch.setenv("DATABASE__PORT", "5432")
        monkeypatch.setenv("DATABASE__DBNAME", "bidb_test")
        monkeypatch.setenv("DATABASE__USER", "mkobi_app")
        monkeypatch.setenv("DATABASE__PASSWORD", "test")
        monkeypatch.setenv("JWT__SECRET_KEY", "test_secret_key_for_testing_32_chars")
        monkeypatch.setenv("DATABASE__TEST_DBNAME", "bidb_test")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        mock_check = mocker.patch(
            "mkobi.rq_worker_wrapper.check_redis_connection",
            return_value=True,
        )
        mocker.patch("mkobi.rq_worker_wrapper.rq.Queue")
        mocker.patch("mkobi.rq_worker_wrapper.rq.Worker")

        start_rq_worker()

        # Verify the URL was constructed from config
        expected_url = "redis://confighost:6380/1"
        mock_check.assert_called_once_with(expected_url)


class TestRegisteredJobCallable:
    """The submission seam must point at the sync RQ callable, not the async one."""

    def test_enqueue_processing_job_submits_sync_callable(self):
        """The callable submitted is process_csv_background_sync, not the async one.

        A worker can only execute a sync callable; submitting the async
        ``process_csv_background`` would fail at execution time in the worker.
        """
        import mkobi.services.file_processing as fp

        source = inspect.getsource(fp.enqueue_processing_job)
        assert "process_csv_background_sync" in source
        assert "process_csv_background(" not in source

    def test_enqueue_job_kwargs_match_sync_callable_parameters(self):
        """The kwargs submitted are exactly the sync callable's parameters.

        A rename of a parameter would otherwise only surface as a
        NoSuchFunctionError/signature error inside a worker log at 03:00.
        """
        from mkobi.workers.data_worker import process_csv_background_sync

        expected = set(
            inspect.signature(process_csv_background_sync).parameters.keys()
        )
        assert expected == {
            "file_path_str",
            "task_id",
            "dashboard_id_str",
            "processing_config_dict",
            "mode",
        }

        import mkobi.services.file_processing as fp

        source = inspect.getsource(fp.enqueue_processing_job)
        for name in expected:
            assert f"{name}=" in source


class TestCheckWorkerRegistered:
    """Unit tests for the worker-registry healthcheck."""

    def _patch_connection(self, mocker, workers: dict[str, dict[str, str]]):
        """Patch redis.Redis.from_url to serve a fixed registry.

        Args:
            mocker: pytest-mock fixture.
            workers: Mapping of worker key to its redis hash (string values).
        """
        mock_connection = MagicMock()
        mock_connection.smembers.return_value = {
            key.encode() for key in workers
        }

        def hgetall(key):
            raw = workers.get(key, {})
            return {k.encode(): v.encode() for k, v in raw.items()}

        mock_connection.hgetall.side_effect = hgetall
        mocker.patch(
            "mkobi.rq_worker_wrapper.redis.Redis.from_url",
            return_value=mock_connection,
        )
        return mock_connection

    def test_empty_worker_set_is_not_healthy(self, mocker):
        """An empty registry fails the check."""
        self._patch_connection(mocker, {})

        assert check_worker_registered("default") is False

    def test_worker_on_expected_queue_is_healthy(self, mocker):
        """A live worker subscribed to the expected queue passes."""
        self._patch_connection(
            mocker,
            {"rq:worker:abc": {"state": "idle", "queues": "default"}},
        )

        assert check_worker_registered("default") is True

    def test_worker_on_different_queue_is_not_healthy(self, mocker):
        """A live worker on another queue fails the check."""
        self._patch_connection(
            mocker,
            {"rq:worker:abc": {"state": "idle", "queues": "other"}},
        )

        assert check_worker_registered("default") is False

    def test_dead_worker_state_is_not_healthy(self, mocker):
        """A worker hash whose state is not live fails the check."""
        self._patch_connection(
            mocker,
            {"rq:worker:abc": {"state": "starting", "queues": "default"}},
        )

        assert check_worker_registered("default") is False
