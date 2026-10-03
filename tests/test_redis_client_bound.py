"""Evidence for the declared Redis transport bound.

The whole suite mocks Redis: ``tests/conftest.py::_auto_mock_redis`` is
``autouse=True`` and replaces both factories for every test. No shipped test
inspects a real client's transport configuration, so nothing would catch a
missing timeout or a missing retry pin. These tests therefore capture the real
factories at module import time -- collection happens before any fixture runs --
and read ``connection_pool.connection_kwargs`` from a client they construct
themselves. They close every client they build.
"""

import time

import pytest

# Captured at import time, before the autouse fixture can patch the module.
# A monkeypatch.undo() or importlib.reload would leave the module object
# inconsistent for later tests in the session, so neither is used.
from mkobi.core.redis_client import get_async_redis_client as _real_async_factory
from mkobi.core.redis_client import get_redis_client as _real_sync_factory

import redis.exceptions

from mkobi.config import Settings, clear_config_cache


def _kwargs(client) -> dict:
    """Return the effective transport kwargs of a constructed client."""
    return client.connection_pool.connection_kwargs


class TestAsyncClientBound:
    """The async factory carries the ruled transport bound."""

    @pytest.mark.asyncio
    async def test_async_client_carries_declared_bound(self):
        """A constructed client carries both timeouts and the pinned retry.

        This is the primary evidence. It reads the client's own effective
        connection kwargs rather than the values the factory was handed, so a
        value the library silently overrides would be caught.
        """
        clear_config_cache()
        try:
            client = _real_async_factory()
            try:
                kwargs = _kwargs(client)
                settings = Settings()
                assert kwargs["socket_timeout"] == settings.redis.socket_timeout_seconds
                assert (
                    kwargs["socket_connect_timeout"]
                    == settings.redis.socket_connect_timeout_seconds
                )
                assert kwargs["retry"].get_retries() == 0
            finally:
                await client.aclose()
        finally:
            clear_config_cache()

    @pytest.mark.asyncio
    async def test_connect_and_read_bounds_are_independent(self, monkeypatch):
        """The two bounds are set explicitly and are not one shared number.

        Guards the ``socket_connect_timeout=None`` inheritance trap: if the
        connect bound were left unset it would silently inherit
        ``socket_timeout``, so an operator could not bound the connect
        separately from the read.
        """
        monkeypatch.setenv("REDIS__SOCKET_TIMEOUT_SECONDS", "3")
        monkeypatch.setenv("REDIS__SOCKET_CONNECT_TIMEOUT_SECONDS", "7")
        clear_config_cache()
        try:
            client = _real_async_factory()
            try:
                kwargs = _kwargs(client)
                assert kwargs["socket_timeout"] == 3.0
                assert kwargs["socket_connect_timeout"] == 7.0
            finally:
                await client.aclose()
        finally:
            clear_config_cache()


class TestSyncClientBound:
    """The sync factory carries the same bound, despite having no callers."""

    def test_sync_client_carries_declared_bound(self):
        """A constructed sync client carries both timeouts and the retry pin."""
        clear_config_cache()
        try:
            client = _real_sync_factory()
            try:
                kwargs = _kwargs(client)
                settings = Settings()
                assert kwargs["socket_timeout"] == settings.redis.socket_timeout_seconds
                assert (
                    kwargs["socket_connect_timeout"]
                    == settings.redis.socket_connect_timeout_seconds
                )
                assert kwargs["retry"].get_retries() == 0
            finally:
                client.close()
        finally:
            clear_config_cache()


class TestRedisSettingsBoundResolution:
    """RedisSettings resolves the new keys from the environment."""

    def test_defaults_apply_when_unset(self):
        """The code default is 1.0 s for both fields when the env is unset."""
        settings = Settings()
        assert settings.redis.socket_timeout_seconds == 1.0
        assert settings.redis.socket_connect_timeout_seconds == 1.0

    def test_env_resolves_both_keys_via_nested_alias(self, monkeypatch):
        """REDIS__SOCKET_*_SECONDS address their nested fields."""
        monkeypatch.setenv("REDIS__SOCKET_TIMEOUT_SECONDS", "2.5")
        monkeypatch.setenv("REDIS__SOCKET_CONNECT_TIMEOUT_SECONDS", "4.5")
        settings = Settings()
        assert settings.redis.socket_timeout_seconds == 2.5
        assert settings.redis.socket_connect_timeout_seconds == 4.5


class TestTimeoutIsBounded:
    """A Redis timeout surfaces as a bounded failure rather than a hang."""

    @pytest.mark.asyncio
    async def test_unreachable_host_fails_within_bound(self):
        """A blackholed address fails in about the connect bound, not ~59 s.

        The address is a non-routable sink, so the connect attempt can only end
        by timing out rather than being refused. The wall-clock ceiling is
        generous relative to the 0.5 s bound, but it is roughly two orders of
        magnitude below the undeclared eleven-attempt default this block
        removes, so it separates "bounded" from "hang".
        """
        from redis.asyncio.retry import Retry
        from redis.backoff import NoBackoff
        import redis.asyncio as aioredis

        client = aioredis.Redis(
            host="10.255.255.1",
            port=6379,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
            retry=Retry(NoBackoff(), 0),
        )
        started = time.monotonic()
        try:
            with pytest.raises(redis.exceptions.TimeoutError):
                await client.ping()
        finally:
            await client.aclose()
        assert time.monotonic() - started < 5.0
