"""Tests for RQ worker startup retry wrapper."""

import inspect
from unittest.mock import MagicMock

import pytest
import redis

from mkobi.rq_worker_wrapper import (
    _build_redis_url,
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


class TestBuildRedisUrlCredentialParity:
    """B11: the consumer's derived URL carries the producer's credential.

    The producer authenticates via ``redis.Redis(host=..., password=...)`` in
    ``core.task_queue.get_rq_queue``; the consumer derives a URL. A password
    configured for the store must reach the consumer's derivation, and a
    password with URL-reserved characters must survive percent-encoding.
    """

    def _derive_with_config(self, monkeypatch, password: str | None) -> str:
        from mkobi.config import clear_config_cache

        monkeypatch.setenv("REDIS__HOST", "redishost")
        monkeypatch.setenv("REDIS__PORT", "6380")
        monkeypatch.setenv("REDIS__DB", "2")
        if password is None:
            monkeypatch.delenv("REDIS__PASSWORD", raising=False)
        else:
            monkeypatch.setenv("REDIS__PASSWORD", password)
        clear_config_cache()
        try:
            return _build_redis_url()
        finally:
            clear_config_cache()

    def test_url_carries_password_when_configured(self, monkeypatch):
        """A configured password appears in the derived URL's userinfo."""
        url = self._derive_with_config(monkeypatch, "s3cret")

        assert url == "redis://:s3cret@redishost:6380/2"
        # The producer reads the same setting through RedisSettings.
        assert redis.Redis.from_url(url).connection_pool.connection_kwargs["password"] == "s3cret"

    def test_url_has_no_userinfo_when_password_absent(self, monkeypatch):
        """With no password the URL has no userinfo section."""
        url = self._derive_with_config(monkeypatch, None)

        assert url == "redis://redishost:6380/2"
        assert "@" not in url

    def test_password_with_reserved_characters_round_trips(self, monkeypatch):
        """A password containing URL-reserved characters survives round-tripping.

        ``from_url`` must recover the exact original password, which only holds
        when the reserved characters were percent-encoded on the way in.
        """
        password = "p@ss:w/rd?#{}[]"
        url = self._derive_with_config(monkeypatch, password)

        # The raw password must not appear unescaped in the URL.
        assert password not in url
        assert redis.Redis.from_url(url).connection_pool.connection_kwargs["password"] == password

    def test_worker_queue_connection_uses_the_derived_url(self, mocker, monkeypatch):
        """start_rq_worker builds its queue connection from the derived URL.

        Patches ``from_url`` and asserts the password reaches it, so a future
        divergence between the producer's credential and the consumer's cannot
        pass unnoticed.
        """
        monkeypatch.setenv("REDIS__HOST", "redishost")
        monkeypatch.setenv("REDIS__PORT", "6380")
        monkeypatch.setenv("REDIS__DB", "2")
        monkeypatch.setenv("REDIS__PASSWORD", "queuesecret")
        monkeypatch.setenv("ENV", "test")
        monkeypatch.setenv("DATABASE__HOST", "localhost")
        monkeypatch.setenv("DATABASE__PORT", "5432")
        monkeypatch.setenv("DATABASE__DBNAME", "bidb_test")
        monkeypatch.setenv("DATABASE__USER", "mkobi_app")
        monkeypatch.setenv("DATABASE__PASSWORD", "test")
        monkeypatch.setenv("DATABASE__TEST_DBNAME", "bidb_test")
        monkeypatch.setenv("JWT__SECRET_KEY", "test_secret_key_for_testing_32_chars")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        mocker.patch("mkobi.rq_worker_wrapper.check_redis_connection", return_value=True)
        mock_from_url = mocker.patch(
            "mkobi.rq_worker_wrapper.redis.Redis.from_url",
            return_value=MagicMock(),
        )
        mocker.patch("mkobi.rq_worker_wrapper.rq.Queue")
        mocker.patch("mkobi.rq_worker_wrapper.rq.Worker")

        start_rq_worker()

        assert mock_from_url.call_args.args[0] == "redis://:queuesecret@redishost:6380/2"


class TestQueueNameAgreement:
    """The producer and the worker must agree on a single queue name."""

    def test_producer_and_worker_share_one_queue_constant(self):
        """Both sides read the same constant rather than two literals.

        If the producer enqueued to one queue and the worker consumed another,
        every submission would sit unconsumed and - now that the healthcheck no
        longer inspects the worker's ``queues`` field - nothing would detect it.
        """
        from mkobi.core.task_queue import DEFAULT_QUEUE_NAME
        import mkobi.rq_worker_wrapper as wrapper

        assert wrapper.DEFAULT_QUEUE_NAME is DEFAULT_QUEUE_NAME

    def test_worker_subscribes_to_the_shared_queue_name(self, mocker, monkeypatch):
        """start_rq_worker builds its queue with the shared constant."""
        from mkobi.core.task_queue import DEFAULT_QUEUE_NAME

        monkeypatch.setenv("REDIS__HOST", "confighost")
        monkeypatch.setenv("REDIS__PORT", "6380")
        monkeypatch.setenv("REDIS__DB", "1")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        mocker.patch(
            "mkobi.rq_worker_wrapper.check_redis_connection", return_value=True
        )
        mock_queue = mocker.patch("mkobi.rq_worker_wrapper.rq.Queue")
        mock_worker = mocker.patch("mkobi.rq_worker_wrapper.rq.Worker")

        start_rq_worker("redis://localhost:6379/0")

        assert mock_queue.call_args.args[0] == DEFAULT_QUEUE_NAME
        assert mock_worker.call_args.args[0][0] is mock_queue.return_value


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

        def hget(key, field):
            raw = workers.get(key, {})
            value = raw.get(field)
            return value.encode() if value is not None else None

        mock_connection.hget.side_effect = hget
        mocker.patch(
            "mkobi.rq_worker_wrapper.redis.Redis.from_url",
            return_value=mock_connection,
        )
        return mock_connection

    @staticmethod
    def _heartbeat(age_seconds: int = 0) -> str:
        """Format a ``last_heartbeat`` value ``age_seconds`` in the past.

        RQ writes the heartbeat with ``utcformat`` (ISO-8601, ``Z`` suffix).
        """
        from datetime import UTC, datetime, timedelta

        return (
            datetime.now(UTC) - timedelta(seconds=age_seconds)
        ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def test_empty_worker_set_is_not_healthy(self, mocker):
        """An empty registry fails the check."""
        self._patch_connection(mocker, {})

        assert check_worker_registered() is False

    def test_registry_member_with_fresh_heartbeat_is_healthy(self, mocker):
        """Regression: the real observed hash shape must pass the check.

        RQ's ``Worker.maintain_heartbeats`` resurrects an expired worker hash as
        a bare ``{last_heartbeat}`` hash and its recovery write is lost on the
        released pipeline, so a demonstrably live worker has exactly this hash.
        Before the fix the check required ``state``/``queues`` and reported
        ``unhealthy`` for this live worker.
        """
        self._patch_connection(
            mocker,
            {"rq:worker:abc": {"last_heartbeat": self._heartbeat(age_seconds=0)}},
        )

        assert check_worker_registered() is True

    def test_heartbeat_within_worker_ttl_plus_60_is_healthy(self, mocker):
        """A heartbeat past the bare worker TTL but inside worker_ttl + 60 is alive.

        RQ's ``heartbeat`` sets the hash TTL to ``worker_ttl + 60``, and an idle
        worker refreshes ``last_heartbeat`` only once per dequeue iteration whose
        timeout is ``worker_ttl - 15``. A heartbeat this old is therefore
        legitimate for a live idle worker and must not be reported unhealthy.
        """
        self._patch_connection(
            mocker,
            {"rq:worker:abc": {"last_heartbeat": self._heartbeat(age_seconds=450)}},
        )

        assert check_worker_registered() is True

    def test_stale_heartbeat_is_not_healthy(self, mocker):
        """A heartbeat older than the hash TTL fails the check."""
        self._patch_connection(
            mocker,
            {"rq:worker:abc": {"last_heartbeat": self._heartbeat(age_seconds=600)}},
        )

        assert check_worker_registered() is False

    def test_missing_heartbeat_is_not_healthy(self, mocker):
        """A registered key without a heartbeat field fails the check."""
        self._patch_connection(mocker, {"rq:worker:abc": {}})

        assert check_worker_registered() is False

    def test_malformed_heartbeat_is_not_healthy(self, mocker):
        """A non-ISO heartbeat value fails the check instead of crashing."""
        self._patch_connection(
            mocker,
            {"rq:worker:abc": {"last_heartbeat": "not-a-timestamp"}},
        )

        assert check_worker_registered() is False
