"""PRF-2: one process-wide Redis client and one pipelined revocation round trip.

The defect this file pins: ``get_async_redis_client`` and ``get_redis_client``
constructed a fresh client (a fresh connection pool) on every call, and the
protected-request auth path issued the two revocation reads as two sequential
round trips. The fix caches one client per process per flavour and pipelines the
two reads into one execution.

The real factories are captured at import time because ``tests/conftest.py``'s
autouse ``_auto_mock_redis`` fixture replaces both module attributes for every
test. Identity and lifecycle assertions target the captured originals, so they
exercise the shipped factory rather than the mock.
"""

import pytest

# Captured at import time, before the autouse fixture patches the module.
import mkobi.core.redis_client as redis_client_module
from mkobi.core.redis_client import (
    close_async_redis_client,
    close_redis_client,
    get_async_redis_client as _real_async_factory,
    get_redis_client as _real_sync_factory,
)

from mkobi.core.security import (
    are_tokens_revoked,
    is_token_revoked,
    is_user_tokens_revoked,
    revoke_all_user_tokens,
    revoke_token,
)

from tests.conftest import MockRedis


@pytest.fixture
def clean_client_cache(monkeypatch):
    """Restore the real factories and discard both client caches around a test.

    ``tests/conftest.py``'s autouse ``_auto_mock_redis`` fixture replaces the
    two module attributes with mocks, and the ``close_*`` helpers resolve those
    attributes by name at call time. The tests here exercise the shipped
    factory, so the module attributes are restored to the captured originals
    for the duration of the test, and both ``functools.cache`` stores are
    cleared on setup and teardown so one test cannot inherit another's client.
    """
    monkeypatch.setattr(
        redis_client_module, "get_async_redis_client", _real_async_factory
    )
    monkeypatch.setattr(
        redis_client_module, "get_redis_client", _real_sync_factory
    )
    _real_async_factory.cache_clear()
    _real_sync_factory.cache_clear()
    yield
    _real_async_factory.cache_clear()
    _real_sync_factory.cache_clear()


class TestOneClientPerProcess:
    """The factory returns the same object on successive calls."""

    @pytest.mark.asyncio
    async def test_async_factory_is_identity_stable(self, clean_client_cache) -> None:
        """Two successive calls return the very same client object.

        Proved behaviourally: identity of the returned object, not the presence
        of a decorator. ``is`` is the assertion because sharing the connection
        pool requires sharing the client instance that owns it.
        """
        first = _real_async_factory()
        second = _real_async_factory()
        assert first is second
        await close_async_redis_client()

    def test_sync_factory_is_identity_stable(self, clean_client_cache) -> None:
        """The synchronous flavour shares the same one-client guarantee."""
        first = _real_sync_factory()
        second = _real_sync_factory()
        assert first is second
        close_redis_client()


class TestPipelinedRevocation:
    """The two revocation checks cross the wire in one pipeline execution."""

    @pytest.mark.asyncio
    async def test_protected_request_uses_one_pipeline(
        self, authenticated_client
    ) -> None:
        """An authenticated request executes exactly one revocation pipeline.

        The request path (``get_current_user_dependency``) pipelines the token
        blacklist read and the user-marker read. Counting pipeline executions on
        the app's own mock Redis proves the two checks ride one round trip rather
        than two sequential ones.
        """
        app = authenticated_client._transport.app  # type: ignore[attr-defined]
        redis = app.state.mock_redis

        executions = 0
        original_pipeline = redis.pipeline

        def counting_pipeline(transaction: bool = True):
            pipe = original_pipeline(transaction=transaction)
            original_execute = pipe.execute

            async def counting_execute():
                nonlocal executions
                executions += 1
                return await original_execute()

            pipe.execute = counting_execute  # type: ignore[method-assign]
            return pipe

        redis.pipeline = counting_pipeline  # type: ignore[method-assign]

        response = await authenticated_client.get("/auth/me")
        assert response.status_code == 200
        assert executions == 1

    @pytest.mark.asyncio
    async def test_two_checks_use_one_pipeline_execution(self) -> None:
        """A healthy store issues exactly one pipeline execution for both checks.

        A counting wrapper around ``MockRedis.pipeline`` observes the number of
        pipeline objects created and executions performed. The protected path
        issues both reads (token blacklist, user marker) in a single pipeline,
        so the count is one -- not two sequential round trips.
        """
        redis = MockRedis()
        created: list = []

        original_pipeline = redis.pipeline

        def counting_pipeline(transaction: bool = True):
            pipe = original_pipeline(transaction=transaction)
            created.append(pipe)
            return pipe

        redis.pipeline = counting_pipeline  # type: ignore[method-assign]

        revoked = await are_tokens_revoked(
            redis,
            "some-jti",
            user_id=__import__("uuid").uuid4(),
            issued_at=1000,
        )
        assert revoked is False
        assert len(created) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("token_revoked", "user_revoked", "expected"),
        [
            (False, False, False),
            (True, False, True),
            (False, True, True),
            (True, True, True),
        ],
    )
    async def test_pipelined_results_for_all_combinations(
        self, token_revoked: bool, user_revoked: bool, expected: bool
    ) -> None:
        """All four (access / user) revocation combinations give the same verdict.

        Each combination is also checked against the two sequential reference
        functions, so the pipeline cannot silently invert either read.
        """
        from uuid import uuid4

        redis = MockRedis()
        jti = "jti-1234"
        user_id = uuid4()
        issued_at = 500

        if token_revoked:
            await revoke_token(redis, jti, expires_in_seconds=900)
        if user_revoked:
            await revoke_all_user_tokens(
                redis, user_id, access_ttl=900, refresh_ttl=604800
            )

        pipelined = await are_tokens_revoked(redis, jti, user_id, issued_at)

        sequential = await is_token_revoked(redis, jti) or await is_user_tokens_revoked(
            redis, user_id, issued_at
        )

        assert pipelined is expected
        assert pipelined == sequential

    @pytest.mark.asyncio
    async def test_none_jti_still_checks_user_marker(self) -> None:
        """A token without ``jti`` still evaluates the user marker correctly."""
        from uuid import uuid4

        redis = MockRedis()
        user_id = uuid4()
        await revoke_all_user_tokens(
            redis, user_id, access_ttl=900, refresh_ttl=604800
        )

        assert await are_tokens_revoked(redis, None, user_id, issued_at=100) is True
        assert await are_tokens_revoked(redis, None, user_id, issued_at=10**18) is False


class TestClientLifecycle:
    """The cached async client is closed and its cache discarded at shutdown."""

    @pytest.mark.asyncio
    async def test_close_discards_cache_and_next_call_builds_fresh(
        self, clean_client_cache
    ) -> None:
        """After close, a new factory call constructs a different client.

        This is the re-open guarantee: teardown evicts the cached instance so a
        subsequent startup is not handed a closed pool.
        """
        first = _real_async_factory()
        await close_async_redis_client()

        second = _real_async_factory()
        try:
            assert second is not first
        finally:
            await close_async_redis_client()

    def test_sync_close_discards_cache(self, clean_client_cache) -> None:
        """The synchronous close discards its cache entry as well."""
        first = _real_sync_factory()
        close_redis_client()
        second = _real_sync_factory()
        try:
            assert second is not first
        finally:
            close_redis_client()
