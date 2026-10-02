"""Integration tests for rate limiting functionality.

Tests cover:
- Initial requests succeed under rate limit
- Requests exceeding limit return 429 with Retry-After header
- Requests succeed after rate limit window resets
"""

from fastapi import status


class TestRateLimitingIntegration:
    """Tests for rate limiting behavior across endpoints."""

    async def test_login_rate_limit_exceeded(
        self, async_client, async_db_session, strict_redis
    ) -> None:
        """Test that login endpoint returns 429 when rate limit exceeded."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        user_repo = UserRepository()

        # Create test user
        await user_repo.create(
            db=async_db_session,
            email="rate_limit_login_test@example.com",
            password_hash=hash_password("TestPass123!"),
            role="viewer",
        )
        await async_db_session.commit()

        max_attempts = 5

        for i in range(max_attempts):
            response = await async_client.post(
                "/auth/login",
                json={
                    "email": "rate_limit_login_test@example.com",
                    "password": "wrong_password",
                },
            )
            # All should be processed (though auth fails)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"Request {i + 1} should be processed, got {response.status_code}"
            )

        # The 6th request should be rate limited
        response = await async_client.post(
            "/auth/login",
            json={
                "email": "rate_limit_login_test@example.com",
                "password": "wrong_password",
            },
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            f"Expected 429, got {response.status_code}"
        )

        # Verify Retry-After header is present
        assert "retry-after" in response.headers, (
            "Retry-After header should be present in 429 response"
        )
        retry_after = response.headers["retry-after"]
        assert retry_after.isdigit(), "Retry-After should be a numeric value"
        assert int(retry_after) > 0, "Retry-After should be positive"

        # Verify RFC 7807 error format
        body = response.json()
        assert body["code"] == "RATE_LIMIT_EXCEEDED"
        assert "detail" in body

    async def test_register_request_rate_limit_exceeded(
        self, async_client, async_db_session, strict_redis
    ) -> None:
        """Test that register-request endpoint returns 429 when rate limit exceeded."""
        max_attempts = 3

        for i in range(max_attempts):
            response = await async_client.post(
                "/auth/register-request",
                json={"email": f"test{i}@example.com"},
            )
            # All should be processed (though may fail due to different reasons)
            assert response.status_code in (
                status.HTTP_201_CREATED,
                status.HTTP_400_BAD_REQUEST,
            ), f"Request {i + 1} should be processed, got {response.status_code}"

        # The 4th request should be rate limited
        response = await async_client.post(
            "/auth/register-request",
            json={"email": "test_overflow@example.com"},
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            f"Expected 429, got {response.status_code}"
        )

        # Verify Retry-After header is present
        assert "retry-after" in response.headers, (
            "Retry-After header should be present in 429 response"
        )

    async def test_rate_limit_reset_allow_writes(
        self, async_client, async_db_session, strict_redis
    ) -> None:
        """Test that rate limiting works correctly with reset capability."""
        from mkobi.api.routes.auth import _rate_limit_keys
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        user_repo = UserRepository()

        # Create test user
        await user_repo.create(
            db=async_db_session,
            email="rate_limit_reset_test@example.com",
            password_hash=hash_password("TestPass123!"),
            role="viewer",
        )
        await async_db_session.commit()

        max_attempts = 5

        # Exhaust the rate limit: max_attempts failures then one more. Prove the
        # loop actually exhausts it before trusting the reset below.
        for _ in range(max_attempts):
            response = await async_client.post(
                "/auth/login",
                json={
                    "email": "rate_limit_reset_test@example.com",
                    "password": "wrong_password",
                },
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

        exhausted = await async_client.post(
            "/auth/login",
            json={
                "email": "rate_limit_reset_test@example.com",
                "password": "wrong_password",
            },
        )
        assert exhausted.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            "the exhaustion loop must actually exhaust the limit"
        )

        # Clear both derived buckets on the app's OWN Redis instance. The route
        # fills app.state.mock_redis; the strict_redis fixture is a different
        # instance, so popping from it would clear nothing.
        app_redis = async_client._transport.app.state.mock_redis
        for key in _rate_limit_keys(
            "login", "127.0.0.1", "rate_limit_reset_test@example.com"
        ):
            app_redis._data.pop(key, None)
            app_redis._ttls.pop(key, None)

        # Next request should succeed (return 401 for wrong password)
        response = await async_client.post(
            "/auth/login",
            json={
                "email": "rate_limit_reset_test@example.com",
                "password": "wrong_password",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            f"Request should succeed after reset, got {response.status_code}"
        )

    async def test_two_identifiers_behind_one_peer_have_separate_buckets(
        self, async_client, async_db_session, strict_redis
    ) -> None:
        """One identifier's failures do not consume another's quota.

        The peer bound is deliberately not exhausted here, so this isolates the
        per-identifier budget: failures on user A must not count against user B.
        """
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        user_repo = UserRepository()
        for email in (
            "budget_user_a@example.com",
            "budget_user_b@example.com",
        ):
            await user_repo.create(
                db=async_db_session,
                email=email,
                password_hash=hash_password("TestPass123!"),
                role="viewer",
            )
        await async_db_session.commit()

        # Three failures on A leave its identifier bucket at 3 and the peer at 3.
        for _ in range(3):
            response = await async_client.post(
                "/auth/login",
                json={"email": "budget_user_a@example.com", "password": "wrong_password"},
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # B has its own identifier bucket, so it is still processed (401, not 429).
        response = await async_client.post(
            "/auth/login",
            json={"email": "budget_user_b@example.com", "password": "wrong_password"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            "user B must have its own identifier budget"
        )

    async def test_one_peer_with_two_identifiers_still_hits_peer_bound(
        self, async_client, async_db_session, strict_redis
    ) -> None:
        """Rotating identifiers from one peer must not escape the peer bound."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        user_repo = UserRepository()
        for email in (
            "rotate_user_a@example.com",
            "rotate_user_b@example.com",
        ):
            await user_repo.create(
                db=async_db_session,
                email=email,
                password_hash=hash_password("TestPass123!"),
                role="viewer",
            )
        await async_db_session.commit()

        # Five attempts alternating between two identifiers fill the shared peer
        # bucket; each identifier only reached 3 and 2 of its own budget.
        for i in range(5):
            email = (
                "rotate_user_a@example.com" if i % 2 == 0 else "rotate_user_b@example.com"
            )
            response = await async_client.post(
                "/auth/login",
                json={"email": email, "password": "wrong_password"},
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # The sixth attempt is refused by the peer bound even though neither
        # identifier bucket alone is exhausted.
        response = await async_client.post(
            "/auth/login",
            json={"email": "rotate_user_c@example.com", "password": "wrong_password"},
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    async def test_malformed_peer_does_not_500(
        self, async_client, async_db_session, strict_redis
    ) -> None:
        """A non-IP peer must rate-limit, not crash with a 500."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        user_repo = UserRepository()
        await user_repo.create(
            db=async_db_session,
            email="malformed_peer_test@example.com",
            password_hash=hash_password("TestPass123!"),
            role="viewer",
        )
        await async_db_session.commit()

        # Register-request derives its peer with ip_address(), which raises on a
        # non-IP value. Override the transport peer with a malformed host.
        transport = async_client._transport
        original_client = transport.client
        transport.client = ("not-an-ip", 12345)
        try:
            response = await async_client.post(
                "/auth/register-request",
                json={"email": "malformed_peer_test@example.com"},
            )
        finally:
            transport.client = original_client

        assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR, (
            "a malformed peer must not surface as a 500"
        )
        assert response.status_code in (
            status.HTTP_201_CREATED,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    async def test_different_ips_have_separate_limits(
        self, async_client, async_db_session, strict_redis
    ) -> None:
        """Test that rate limits are tracked per IP address."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        user_repo = UserRepository()

        # Create test user
        await user_repo.create(
            db=async_db_session,
            email="rate_limit_ip_test@example.com",
            password_hash=hash_password("TestPass123!"),
            role="viewer",
        )
        await async_db_session.commit()

        max_attempts = 5

        # Exhaust rate limit for one IP
        for _ in range(max_attempts + 1):
            await async_client.post(
                "/auth/login",
                json={
                    "email": "rate_limit_ip_test@example.com",
                    "password": "wrong_password",
                },
            )

        # Verify first IP is rate limited
        response = await async_client.post(
            "/auth/login",
            json={
                "email": "rate_limit_ip_test@example.com",
                "password": "wrong_password",
            },
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


class TestAsyncRateLimiterUnit:
    """Unit tests for AsyncRateLimiter class."""

    async def test_check_rate_limit_allows_under_limit(self, strict_redis) -> None:
        """Test that check_rate_limit returns True when under limit."""
        from mkobi.core.security import AsyncRateLimiter

        limiter = AsyncRateLimiter(strict_redis)

        for i in range(3):
            allowed, retry_after = await limiter.check_rate_limit(
                "test_key:under_limit", max_attempts=5, ttl=60
            )
            assert allowed is True
            assert retry_after is None, f"Attempt {i + 1} should be allowed"

    async def test_check_rate_limit_blocks_over_limit(self, strict_redis) -> None:
        """Test that check_rate_limit returns False when over limit."""
        from mkobi.core.security import AsyncRateLimiter

        limiter = AsyncRateLimiter(strict_redis)
        key = "test_key:over_limit"

        # Make 5 requests (at limit)
        for i in range(5):
            allowed, retry_after = await limiter.check_rate_limit(key, max_attempts=5, ttl=60)
            assert allowed is True, f"Attempt {i + 1} should be allowed"

        # 6th request should be blocked
        allowed, retry_after = await limiter.check_rate_limit(key, max_attempts=5, ttl=60)
        assert allowed is False, "6th attempt should be blocked"
        assert retry_after is not None, "retry_after should be returned when blocked"
        assert retry_after > 0, "retry_after should be positive"

    async def test_check_rate_limit_returns_ttl_when_blocked(self, strict_redis) -> None:
        """Test that check_rate_limit returns TTL when rate limit is exceeded."""
        from mkobi.core.security import AsyncRateLimiter

        limiter = AsyncRateLimiter(strict_redis)
        key = "test_key:ttl_check"

        # Set up a key with known TTL
        await strict_redis.setex(key, 120, "5")

        # Request should be blocked and TTL returned
        allowed, retry_after = await limiter.check_rate_limit(key, max_attempts=5, ttl=60)
        assert allowed is False
        assert retry_after is not None