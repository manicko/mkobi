"""Tests for the public client-error reporting endpoint.

The endpoint accepts an anonymous caller's body and writes its values to a log
line. These tests prove the DP-11 (option (c), 2026-10-03) bound: an oversized
*declared* body is refused with 413, and an oversized *parsed* value is accepted
with the value truncated. They also pin the properties the defect report
established by measurement: the emitted record stays within the cap, the
untruncated length is logged beside a capped value, the record remains one
physical line (log-injection property), and the per-IP rate limit is unchanged.

Capture note: the application calls ``setup_logging`` at import time, which
configures every ``mkobi.*`` logger with ``propagate=False`` and its own
handlers. pytest's ``caplog`` attaches its handler to the *root* logger, so a
record emitted by ``mkobi.api.routes.client_errors`` is stopped at the
``mkobi.api`` logger and ``caplog`` never sees it. ``caplog`` therefore captures
nothing (in isolation or in a full-suite run). The project's established
pattern for this configuration is a collector handler attached directly to the
emitting logger; see ``tests/test_processing_config_boundary.py``'s
``_capture_logs`` and ``tests/test_starter.py``. The captured record is still
formatted with the production ``JSONFormatter``, so the log-injection property
is proven through the JSON formatter exactly as before.
"""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import status
from httpx import AsyncClient

from mkobi.core.logging_config import JSONFormatter
from mkobi.models.data import (
    MAX_CLIENT_ERROR_BODY_BYTES,
    MAX_CLIENT_ERROR_FIELD_LENGTH,
)


# The exact payload shape sent by
# ``frontend/src/shared/components/ErrorBoundary.tsx::reportError``:
# three fields inside ``error`` (name, message, stack), plus componentStack,
# url, userAgent and timestamp. It is copied from the file rather than invented,
# because a bound that rejected ``stack`` would make the only first-party caller
# silently stop reporting (its promise chain ends in ``.catch(() => {})``).
def _caller_shaped_payload() -> dict[str, Any]:
    """Return ErrorBoundary.tsx's exact payload shape."""
    return {
        "error": {
            "name": "TypeError",
            "message": "Cannot read properties of null (reading 'map')",
            "stack": (
                "TypeError: Cannot read properties of null (reading 'map')\n"
                "    at DashboardView (DashboardView.tsx:42:11)\n"
                "    at renderWithHooks (react-dom.development.js:15486:18)"
            ),
        },
        "componentStack": "\n    in DashboardView\n    in App\n    in Router",
        "url": "https://app.example.com/dashboard/550e8400-e29b-41d4-a716-446655440000",
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "timestamp": "2026-10-03T12:34:56.789Z",
    }


def _endpoint_logger() -> logging.Logger:
    """Return the logger the report path emits through."""
    return logging.getLogger("mkobi.api.routes.client_errors")


@contextmanager
def _capture_endpoint_records() -> Iterator[list[logging.LogRecord]]:
    """Yield the records emitted by the client-errors route.

    A collector is attached directly to the emitting logger because the
    application configures ``propagate=False`` on the ``mkobi.*`` tree, so the
    root handler pytest's ``caplog`` installs would never receive these records.
    The logger's level and disabled flag are forced open for the duration (the
    test image sets ``LOGGING__LEVEL=WARNING``, which is below ERROR, but the
    forced level keeps the capture independent of that setting) and restored on
    exit.
    """
    logger = _endpoint_logger()
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    collector = _Collector()
    original_level = logger.level
    was_disabled = logger.disabled
    logger.addHandler(collector)
    logger.setLevel(logging.DEBUG)
    logger.disabled = False
    try:
        yield records
    finally:
        logger.removeHandler(collector)
        logger.setLevel(original_level)
        logger.disabled = was_disabled


def _single_endpoint_record(records: list[logging.LogRecord]) -> logging.LogRecord:
    """Return the single endpoint record the report path emitted."""
    assert len(records) == 1, f"expected one endpoint record, got {len(records)}"
    return records[0]


class TestClientErrorAcceptance:
    """Ordinary and caller-shaped reports are accepted with 204."""

    async def test_caller_shaped_payload_returns_204(self, async_client: AsyncClient) -> None:
        """The exact ErrorBoundary.tsx payload must be accepted.

        This is the detector for the silent-swallow failure mode: the caller's
        ``.catch(() => {})`` would hide a 422, and no other test would fail.
        """
        response = await async_client.post(
            "/client-errors", json=_caller_shaped_payload()
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"caller-shaped payload must be accepted, got {response.status_code}: "
            f"{response.text}"
        )

    async def test_ordinary_size_body_returns_204(self, async_client: AsyncClient) -> None:
        """A plainly-sized body is accepted."""
        response = await async_client.post(
            "/client-errors",
            json={
                "error": {"name": "Error", "message": "boom", "stack": "at f (a.js:1:1)"},
                "componentStack": "in App",
                "url": "/dashboard/1",
                "userAgent": "pytest/1.0",
                "timestamp": "2026-10-03T00:00:00.000Z",
            },
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT


class TestDeclaredLengthRejection:
    """DP-11, option (c), first half: a declared-length body is rejected."""

    async def test_declared_oversized_content_length_returns_413(
        self, async_client: AsyncClient
    ) -> None:
        """A request that *declares* a body above the ceiling is refused.

        The body is valid JSON so it survives parsing and reaches the
        declared-length guard (which runs before model validation); the point
        is that the *declared* size alone refuses it, without inspecting the
        values. A header check that only ran after model validation would
        answer 422 here instead.
        """
        filler = "x" * (MAX_CLIENT_ERROR_BODY_BYTES + 1)
        body = json.dumps(
            {
                "error": {"name": "Error", "message": "boom", "stack": "at f"},
                "componentStack": "in App",
                "url": "/dashboard/1",
                "userAgent": "pytest/1.0",
                "timestamp": "2026-10-03T00:00:00.000Z",
                "filler": filler,
            }
        ).encode("utf-8")
        assert len(body) > MAX_CLIENT_ERROR_BODY_BYTES
        response = await async_client.post(
            "/client-errors",
            content=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE, (
            f"declared oversized body must be refused, got {response.status_code}: "
            f"{response.text}"
        )
        # RFC 7807 body with the reused error code (no new enum member added).
        body_json = response.json()
        assert body_json["code"] == "FILE_TOO_LARGE"
        assert body_json["status"] == status.HTTP_413_CONTENT_TOO_LARGE


class TestParsedValueTruncation:
    """DP-11, option (c), second half: parsed values are truncated."""

    async def test_chunked_oversized_stack_truncated_not_rejected(
        self, async_client: AsyncClient
    ) -> None:
        """No declared length: oversized ``stack`` is accepted, then truncated.

        A header-only implementation passes the 413 case above and fails this
        one, which is exactly why both halves are asserted separately. The body
        is streamed as a generator so no Content-Length is declared.
        """
        payload = _caller_shaped_payload()
        payload["error"]["stack"] = "s" * (MAX_CLIENT_ERROR_FIELD_LENGTH + 5000)
        body = json.dumps(payload).encode("utf-8")

        async def _chunks():
            yield body

        response = await async_client.post(
            "/client-errors",
            content=_chunks(),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"a chunked oversized parsed value must be accepted (truncated), "
            f"got {response.status_code}: {response.text}"
        )

    async def test_oversized_top_level_fields_bounded_without_declared_length(
        self,
        async_client: AsyncClient,
    ) -> None:
        """``url``, ``userAgent`` and ``componentStack`` are bounded, not rejected.

        Every oversized value is sent chunked (no declared length), so only the
        parsed-value bound can hold it. ``max_length`` alone would answer 422;
        the model's truncating ``BeforeValidator`` is what keeps the caller
        reporting.
        """
        oversized = "z" * (MAX_CLIENT_ERROR_FIELD_LENGTH + 4096)
        payload = _caller_shaped_payload()
        payload["url"] = oversized
        payload["userAgent"] = oversized
        payload["componentStack"] = oversized
        body = json.dumps(payload).encode("utf-8")

        async def _chunks():
            yield body

        with _capture_endpoint_records() as records:
            response = await async_client.post(
                "/client-errors",
                content=_chunks(),
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"oversized top-level fields must be accepted (truncated), "
            f"got {response.status_code}: {response.text}"
        )

        record = _single_endpoint_record(records)
        rendered = JSONFormatter().format(record)
        assert len(rendered) <= 4 * MAX_CLIENT_ERROR_FIELD_LENGTH + 1024, (
            f"record length {len(rendered)} exceeds the expected bound"
        )
        assert oversized not in rendered, "the oversized value must be truncated"

    async def test_oversized_error_message_truncated_and_length_logged(
        self,
        async_client: AsyncClient,
    ) -> None:
        """An oversized ``error.message`` is truncated and its real length logged."""
        oversized = "m" * (MAX_CLIENT_ERROR_FIELD_LENGTH + 2048)
        payload = _caller_shaped_payload()
        payload["error"]["message"] = oversized

        with _capture_endpoint_records() as records:
            response = await async_client.post("/client-errors", json=payload)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        record = _single_endpoint_record(records)
        rendered = JSONFormatter().format(record)
        assert oversized not in rendered, "the oversized value must be truncated"
        assert f"truncated=message:{len(oversized)}" in rendered, (
            "the untruncated length must be logged beside the capped value"
        )


class TestLogRecordProperties:
    """The emitted record's shape is pinned by test, not assumed."""

    async def test_multi_line_values_stay_one_physical_record_line(
        self, async_client: AsyncClient
    ) -> None:
        """A body containing newlines cannot forge a record boundary.

        The record is emitted through the JSON formatter, which escapes
        newlines; this must still hold after the bound is added. The assertion
        formats the captured record with the production ``JSONFormatter``, which
        is the same formatter the application's handler runs at emit time; a
        plain-text formatter would not escape.
        """
        payload = _caller_shaped_payload()
        payload["error"]["message"] = "line one\nline two\nERROR forged record"
        payload["error"]["stack"] = "at a\nat b\nat c"
        payload["componentStack"] = "\n    in A\n    in B"

        with _capture_endpoint_records() as records:
            response = await async_client.post("/client-errors", json=payload)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        record = _single_endpoint_record(records)
        rendered = JSONFormatter().format(record)
        assert "\n" not in rendered, "the emitted record must be one physical line"
        # json.loads round-trips, so the record is one JSON object, not several.
        parsed = json.loads(rendered)
        assert "forged record" in parsed["message"]

    async def test_truncated_log_record_within_cap_and_length_logged(
        self, async_client: AsyncClient
    ) -> None:
        """The emitted record stays within the cap and reports the real length."""
        payload = _caller_shaped_payload()
        original = "q" * (MAX_CLIENT_ERROR_FIELD_LENGTH + 1000)
        payload["error"]["stack"] = original

        with _capture_endpoint_records() as records:
            response = await async_client.post("/client-errors", json=payload)
        assert response.status_code == status.HTTP_204_NO_CONTENT

        record = _single_endpoint_record(records)
        rendered = JSONFormatter().format(record)
        assert len(rendered) <= MAX_CLIENT_ERROR_FIELD_LENGTH + 2048, (
            f"record length {len(rendered)} exceeds the cap"
        )
        assert original not in rendered, "the oversized value must be truncated"
        # The untruncated length is present beside the capped value.
        assert f"truncated=stack:{len(original)}" in rendered


class TestRateLimitUnchanged:
    """The endpoint's own per-IP bound still applies."""

    async def test_rate_limit_rejects_with_rate_limit_exceeded(
        self, async_client: AsyncClient, strict_redis
    ) -> None:
        """The 101st request from one IP is refused with RATE_LIMIT_EXCEEDED.

        The bound (100/3600s) and the key identity are unchanged; the
        key-identity question belongs to phase 04's AB-6.
        """
        payload = _caller_shaped_payload()

        for i in range(100):
            response = await async_client.post("/client-errors", json=payload)
            assert response.status_code == status.HTTP_204_NO_CONTENT, (
                f"request {i + 1} should be admitted under the bound, "
                f"got {response.status_code}"
            )

        refused = await async_client.post("/client-errors", json=payload)
        assert refused.status_code == status.HTTP_429_TOO_MANY_REQUESTS, (
            f"the 101st request must be refused, got {refused.status_code}"
        )
        assert refused.json()["code"] == "RATE_LIMIT_EXCEEDED"
