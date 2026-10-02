"""Tests for TempPasswordStore class."""

import pytest

from mkobi.core.temp_password_store import TempPasswordStore


class MockPipeline:
    """Mock Redis pipeline that executes commands immediately."""

    def __init__(self, redis_client: "MockRedis"):
        self._redis = redis_client
        self._cmds: list[tuple[str, str]] = []  # List of (cmd, key) tuples

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, key: str):
        """Queue GET command."""
        self._cmds.append(("get", key))
        return self

    def delete(self, key: str):
        """Queue DELETE command."""
        self._cmds.append(("delete", key))
        return self

    async def execute(self) -> list[str | None | int]:
        """Execute all queued commands and return results.

        Returns results where results[0] is GET result.
        """
        results: list[str | None | int] = []
        for cmd, key in self._cmds:
            if cmd == "get":
                results.append(self._redis._data.get(key))
            elif cmd == "delete":
                if key in self._redis._data:
                    del self._redis._data[key]
                results.append(1)
        return results


class MockRedis:
    """Mock Redis client for testing without real Redis."""

    def __init__(self):
        self._data: dict[str, str | None] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        """Set a key with optional TTL (TTL not enforced in mock)."""
        self._data[key] = value

    async def get(self, key: str) -> str | None:
        """Get a key value."""
        return self._data.get(key)

    async def delete(self, key: str) -> int:
        """Delete a key and return count of deleted keys."""
        if key in self._data:
            del self._data[key]
            return 1
        return 0

    def pipeline(self, transaction: bool = True):
        """Return a mock pipeline context manager."""
        return MockPipeline(self)


class FailingPipeline:
    """Mock pipeline that raises errors on execute."""

    def __init__(self, transaction: bool = True):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, key):
        return self

    def delete(self, key):
        return self

    async def execute(self):
        raise RuntimeError("Redis pipeline failed")


class FailingRedis:
    """Mock Redis that always fails."""

    def pipeline(self, transaction: bool = True):
        return FailingPipeline()


class TestTempPasswordStore:
    """Tests for TempPasswordStore class."""

    def test_init_with_defaults(self) -> None:
        """TempPasswordStore should initialize with default TTL of 86400 seconds."""
        mock_redis = MockRedis()
        store = TempPasswordStore(mock_redis)
        assert store._ttl == 86400

    def test_init_with_custom_ttl(self) -> None:
        """TempPasswordStore should accept custom TTL."""
        mock_redis = MockRedis()
        store = TempPasswordStore(mock_redis, ttl_seconds=3600)
        assert store._ttl == 3600

    @pytest.mark.asyncio
    async def test_store_and_retrieve_password(self) -> None:
        """Password should be stored and retrieved correctly via pipeline."""
        mock_redis = MockRedis()
        store = TempPasswordStore(mock_redis, ttl_seconds=3600)

        token = "test_token_abc123"
        password = "TempPass123!"

        await store.store(token, password)
        result = await store.retrieve(token)

        assert result == password

    @pytest.mark.asyncio
    async def test_retrieve_deletes_password(self) -> None:
        """Retrieve should delete the password, making it unavailable on second call."""
        mock_redis = MockRedis()
        store = TempPasswordStore(mock_redis)

        token = "single_use_token"
        password = "OneTimePass"

        await store.store(token, password)
        result1 = await store.retrieve(token)

        # Password should be deleted after retrieve
        assert result1 == password

        # Verify password is deleted from Redis
        result2 = await mock_redis.get(f"temp_pwd:{token}")
        assert result2 is None

        # Second retrieve should return None
        result3 = await store.retrieve(token)
        assert result3 is None

    @pytest.mark.asyncio
    async def test_retrieve_nonexistent_returns_none(self) -> None:
        """Retrieve for nonexistent token should return None."""
        mock_redis = MockRedis()
        store = TempPasswordStore(mock_redis)

        result = await store.retrieve("nonexistent_token")
        assert result is None

    @pytest.mark.asyncio
    async def test_store_fail_open_on_error(self) -> None:
        """Store should log error but not raise on Redis failure."""
        from unittest.mock import patch

        class FailingSetRedis(MockRedis):
            async def set(self, key, value, ex=None):
                raise RuntimeError("Redis connection failed")

        store = TempPasswordStore(FailingSetRedis())

        # Capture log output via mock
        with patch("mkobi.core.temp_password_store.logger") as mock_logger:
            # Should not raise - graceful degradation
            result = await store.store("token", "password")

            # The failure is reported to the caller, not merely swallowed.
            assert result is False

            # Verify error was logged
            mock_logger.error.assert_called_once()
            assert "Failed to store temp password in Redis" in mock_logger.error.call_args[0][0]

    @pytest.mark.asyncio
    async def test_retrieve_fail_graceful_on_error(self) -> None:
        """Retrieve should return None gracefully on Redis failure."""
        store = TempPasswordStore(FailingRedis())

        # Should not raise, returns None
        result = await store.retrieve("token")
        assert result is None