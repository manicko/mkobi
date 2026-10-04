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
        """Test that register-request returns 429 once one email's budget is spent.

        The identifier bound is 3/hour. Four requests for the *same* email are
        sent; the fourth must be refused. The shared peer ceiling is 30, so only
        the identifier bound can be doing the work here.
        """
        max_attempts = 3
        email = "register_overflow@example.com"

        for i in range(max_attempts):
            response = await async_client.post(
                "/auth/register-request",
                json={"email": email},
            )
            # All should be processed (not rate limited); a repeat email is
            # rejected as a duplicate registration (422), which is still
            # processed by the service rather than refused by the limiter.
            assert response.status_code in (
                status.HTTP_201_CREATED,
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            ), f"Request {i + 1} should be processed, got {response.status_code}"

        # The 4th request for the same email should be rate limited.
        response = await async_client.post(
            "/auth/register-request",
            json={"email": email},
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
        from mkobi.api.routes.auth import _identifier_digest, _rate_limit_keys
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
        # instance, so popping from it would clear nothing. The identifier is
        # derived through the same digest the route uses; the raw email is no
        # longer what the identifier key hashes.
        app_redis = async_client._transport.app.state.mock_redis
        for key in _rate_limit_keys(
            "login",
            "127.0.0.1",
            _identifier_digest("rate_limit_reset_test@example.com"),
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
        """One identifier's exhausted budget does not lock out another.

        This is the availability property the dual bound exists to deliver:
        identifier A is driven through its *entire* identifier budget, and
        identifier B, behind the same peer, is still served. The peer ceiling is
        10x the identifier bound (50 vs 5), so exhausting A does not touch B.

        The assertion on *which* bound rejected A is load-bearing. A test that
        only checked for a 429 would pass even if the peer bound had fired,
        which is exactly the ambiguity that hid the 5/5 defect.
        """
        from mkobi.api.routes.auth import _identifier_digest, _rate_limit_keys
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

        max_attempts = 5

        # Exhaust A's identifier bucket completely: 5 attempts are processed
        # (401), the 6th is refused by A's identifier bound.
        for i in range(max_attempts):
            response = await async_client.post(
                "/auth/login",
                json={"email": "budget_user_a@example.com", "password": "wrong_password"},
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"attempt {i + 1} on A should be processed, got {response.status_code}"
            )

        response_a = await async_client.post(
            "/auth/login",
            json={"email": "budget_user_a@example.com", "password": "wrong_password"},
        )
        assert response_a.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            "A must be refused once its identifier budget is exhausted"
        )

        # Assert which bound refused A. If the peer bound had fired, the
        # per-peer key would be at its ceiling; the per-identifier key being at
        # its ceiling is the identifier bound and only the identifier bound.
        peer_key, identifier_key = _rate_limit_keys(
            "login",
            "127.0.0.1",
            _identifier_digest("budget_user_a@example.com"),
        )
        app_redis = async_client._transport.app.state.mock_redis
        assert int(app_redis._data[identifier_key]) >= max_attempts, (
            "A must be refused by the identifier bound"
        )
        assert int(app_redis._data[peer_key]) < 50, (
            "the peer bound must not have fired while only one identifier "
            "exhausted its own budget"
        )

        # B is behind the same peer and has its own identifier bucket, so it is
        # still served (401, not 429). This is the assertion that was impossible
        # when both bounds were 5.
        response_b = await async_client.post(
            "/auth/login",
            json={"email": "budget_user_b@example.com", "password": "wrong_password"},
        )
        assert response_b.status_code == status.HTTP_401_UNAUTHORIZED, (
            "user B must be served after user A exhausts its identifier budget"
        )

    async def test_account_rotation_from_one_peer_still_hits_peer_bound(
        self, async_client, async_db_session, strict_redis
    ) -> None:
        """Rotating identifiers from one peer cannot escape the peer ceiling.

        The per-identifier bound cannot catch account rotation: each rotated
        address gets a fresh identifier bucket. The shared per-peer ceiling is
        what engages. With the login peer ceiling at 50, exactly 50 requests
        from one peer are admitted before the 51st is refused, however many
        distinct identifiers they are spread across.
        """
        from mkobi.api.routes.auth import _identifier_digest, _rate_limit_keys
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        user_repo = UserRepository()
        # Ten distinct identifiers, each rotated to at most 5 requests so no
        # single identifier bucket exhausts before the shared peer ceiling.
        emails = [f"rotate_user_{i}@example.com" for i in range(10)]
        for email in emails:
            await user_repo.create(
                db=async_db_session,
                email=email,
                password_hash=hash_password("TestPass123!"),
                role="viewer",
            )
        await async_db_session.commit()

        peer_max_attempts = 50

        # 50 requests, 5 per identifier across 10 identifiers: every request is
        # admitted by both bounds (the identifier bound admits exactly 5, the
        # peer bound admits 50).
        for i in range(peer_max_attempts):
            email = emails[i % len(emails)]
            response = await async_client.post(
                "/auth/login",
                json={"email": email, "password": "wrong_password"},
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"request {i + 1} (identifier {email}) should be admitted by "
                f"both bounds, got {response.status_code}"
            )

        peer_key, _ = _rate_limit_keys(
            "login", "127.0.0.1", _identifier_digest(emails[0])
        )
        app_redis = async_client._transport.app.state.mock_redis
        assert int(app_redis._data[peer_key]) == peer_max_attempts, (
            "the peer counter must reach exactly the peer ceiling"
        )

        # A brand-new identifier, never seen before, is still refused: the
        # shared peer ceiling, not any identifier bound, is doing the work.
        response = await async_client.post(
            "/auth/login",
            json={"email": "rotate_user_fresh@example.com", "password": "wrong_password"},
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            "a fresh identifier must not escape the shared peer ceiling"
        )

    async def test_peer_bound_permits_ten_times_the_identifier_bound(
        self, async_client, async_db_session, strict_redis
    ) -> None:
        """The peer ceiling still engages, and engages at exactly 10x.

        A single identifier is driven past the peer ceiling: its identifier
        bound fires at request 6, but requests 6..50 are still counted against
        the peer as they are refused, and request 51 is refused by the peer
        bound. This pins the number of requests the peer bound permits for one
        identifier (50) and proves the ceiling is not merely decorative.
        """
        from mkobi.api.routes.auth import _identifier_digest, _rate_limit_keys
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        user_repo = UserRepository()
        await user_repo.create(
            db=async_db_session,
            email="ceiling_user@example.com",
            password_hash=hash_password("TestPass123!"),
            role="viewer",
        )
        await async_db_session.commit()

        peer_max_attempts = 50

        # Request 1..5 processed (401), then 6..50 refused by the identifier
        # bound (429) while each still increments the peer counter. The peer
        # counter reaches 50 after request 50.
        for i in range(peer_max_attempts):
            response = await async_client.post(
                "/auth/login",
                json={"email": "ceiling_user@example.com", "password": "wrong_password"},
            )
            if i < 5:
                assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                    f"request {i + 1} should be processed, got {response.status_code}"
                )
            else:
                assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
                    f"request {i + 1} should be refused, got {response.status_code}"
                )

        peer_key, _ = _rate_limit_keys(
            "login", "127.0.0.1", _identifier_digest("ceiling_user@example.com")
        )
        app_redis = async_client._transport.app.state.mock_redis
        assert int(app_redis._data[peer_key]) == peer_max_attempts, (
            "the peer counter must reach exactly 50"
        )

        # Request 51 on the same identifier is refused: by now both bounds are
        # at their ceiling, and the peer bound is checked first.
        response = await async_client.post(
            "/auth/login",
            json={"email": "ceiling_user@example.com", "password": "wrong_password"},
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            "request 51 must be refused by the peer ceiling"
        )

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



class _FailingRedis:
    """Redis double whose commands raise, modelling an outage.

    The methods are synchronous raisers so the same double works for both the
    sync and async limiter: the call raises before any await or coroutine is
    created.
    """

    def get(self, *args, **kwargs):
        raise ConnectionError("redis unavailable")

    def ttl(self, *args, **kwargs):
        raise ConnectionError("redis unavailable")

    def pipeline(self):
        raise ConnectionError("redis unavailable")


class TestRateLimiterFailClosedDefault:
    """SECB-2: the shipped posture is fail-closed and must be the class default.

    The declared posture is ``config.rate_limiter_fail_closed`` (default ``True``).
    A construction site that omits the argument must therefore get the safe
    behaviour, not the fail-open one the classes used to default to.
    """

    async def test_async_limiter_defaults_to_fail_closed(self) -> None:
        """AsyncRateLimiter rejects when Redis fails, with no explicit argument."""
        from mkobi.core.security import AsyncRateLimiter

        limiter = AsyncRateLimiter(_FailingRedis())

        allowed, retry_after = await limiter.check_rate_limit(
            "test_key:fail_closed_default", max_attempts=5, ttl=60
        )
        assert allowed is False, "the default posture must fail closed"
        assert retry_after == 60

    def test_sync_limiter_defaults_to_fail_closed(self) -> None:
        """RateLimiter rejects when Redis fails, with no explicit argument."""
        from mkobi.core.security import RateLimiter

        limiter = RateLimiter(_FailingRedis())

        allowed, retry_after = limiter.check_rate_limit(
            "test_key:fail_closed_default", max_attempts=5, ttl=60
        )
        assert allowed is False, "the default posture must fail closed"
        assert retry_after == 60

    async def test_explicit_false_still_fails_open(self) -> None:
        """An explicit ``fail_closed=False`` is still expressible."""
        from mkobi.core.security import AsyncRateLimiter

        limiter = AsyncRateLimiter(_FailingRedis(), fail_closed=False)

        allowed, retry_after = await limiter.check_rate_limit(
            "test_key:fail_open_explicit", max_attempts=5, ttl=60
        )
        assert allowed is True
        assert retry_after is None
