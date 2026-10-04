"""Tests for security headers on the unhandled-500 response (SECB-3).

``SecurityHeadersMiddleware`` stamps three baseline headers on every response it
passes through, but it is registered innermost and the ``global_exception_handler``
in ``mkobi.utils.exceptions`` builds its own ``JSONResponse`` directly. A request
that raises an unhandled exception never traverses the middleware's response
path, so without this fix the 500 response carried none of the three headers.

The three headers are defined once, in ``mkobi.app.build_security_headers``, and
both the middleware and the handler read them from there; this test pins the
values rather than the helper so a drift in either call site fails here.
"""

from httpx import ASGITransport, AsyncClient

# The three baseline headers the middleware and the 500 handler must agree on.
# ``Strict-Transport-Security`` and ``Content-Security-Policy`` are production
# only and deliberately absent in the test environment.
_EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-xss-protection": "1; mode=block",
    "referrer-policy": "strict-origin-when-cross-origin",
}


class TestUnhandled500SecurityHeaders:
    """An unhandled exception still answers with the three security headers."""

    async def _client_with_raising_route(self) -> AsyncClient:
        """Build an app with a test-only route that raises an unhandled error.

        The route is added after ``create_app`` so the exception handlers and the
        security-headers middleware are already registered; the raise then
        travels the real ``global_exception_handler`` path.
        """
        import os

        os.environ.setdefault("ENV", "test")
        os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")

        from mkobi.config import clear_config_cache

        clear_config_cache()

        from mkobi.app import create_app

        app = create_app()

        @app.get("/__test__/unhandled")
        async def _raise_unhandled() -> None:  # pragma: no cover - test-only route
            raise RuntimeError("test-only unhandled failure")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        return AsyncClient(transport=transport, base_url="http://testserver")

    async def test_500_response_carries_the_three_security_headers(self) -> None:
        """The 500 body is the RFC 7807 shape and carries all three headers."""
        async with await self._client_with_raising_route() as client:
            response = await client.get("/__test__/unhandled")

        assert response.status_code == 500
        for name, value in _EXPECTED_HEADERS.items():
            assert response.headers.get(name) == value, name
        assert response.json()["code"] == "INTERNAL_ERROR"

    def test_helper_is_the_single_definition(self) -> None:
        """The helper returns exactly the three non-production headers.

        This pins the agreement the middleware and handler share: a fourth
        header added here without a matching expectation above (or vice versa)
        fails loudly.
        """
        from mkobi.app import build_security_headers

        actual = {name.lower(): value for name, value in build_security_headers().items()}
        assert actual == _EXPECTED_HEADERS
