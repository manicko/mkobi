"""Tests pinning that the validation surface never echoes a submitted password.

``SECB-1`` (verified at ``ea4fdf0``): the ``RequestValidationError`` handler in
``mkobi.utils.exceptions`` logged ``exc.errors()`` and appended each error dict
verbatim to the 422 response ``errors`` array. Pydantic's ``errors()`` carries an
``input`` key holding the offending raw value, and every password field in
``mkobi.models.auth`` is a plain ``str``, so a validation failure on a login,
register, change-password or reset-password payload wrote the submitted plaintext
password into both the log record and the HTTP response body.

The fix lives at the single handler seam: each error entry is rebuilt so it can
never carry the offending value (``input`` and ``url`` are dropped), while
``loc``, ``msg``, ``type`` and the existing ``ctx["error"]`` rewrite are kept.

Capture note: the application calls ``setup_logging`` at import time, which
configures every ``mkobi.*`` logger with ``propagate=False`` and its own
handlers, so pytest's ``caplog`` root handler never receives these records. The
project's established pattern for this configuration is a collector handler
attached directly to the emitting logger (see
``tests/test_client_errors.py`` and ``tests/test_processing_config_boundary.py``).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from httpx import AsyncClient

# A value that would be unmistakable if it leaked into a log record or a response
# body. It is deliberately longer than the 8-character minimum so it is a
# well-formed password for validation purposes and can only fail on the field it
# is sent against (here, an invalid email forces the whole payload to fail).
_SENTINEL_PASSWORD = "SENTINEL-PASSWORD-MUST-NOT-LEAK-9c1f4a7e"

# Change-password's own field validator rejects the value below; it carries the
# same sentinel so a leak of the new password is caught even when it is the field
# that fails rather than a sibling.
_SENTINEL_NEW_PASSWORD = "SENTINEL-NEW-PASSWORD-MUST-NOT-LEAK-" + "z" * 60


@contextmanager
def _capture_handler_records() -> Iterator[list[logging.LogRecord]]:
    """Yield the records emitted by the exception-handler module.

    A collector is attached directly to the emitting logger because the
    application configures ``propagate=False`` on the ``mkobi.*`` tree. The
    logger's level and disabled flag are forced open for the duration and
    restored on exit.
    """
    logger = logging.getLogger("mkobi.utils.exceptions")
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


def _error_entries(body: dict) -> list[dict]:
    """Return the field-level error entries from a 422 response body."""
    errors = body.get("errors")
    assert isinstance(errors, list), "the validation response must carry an errors array"
    return errors


class TestValidationPasswordNotEchoed:
    """A failed password-bearing validation must not echo the submitted value."""

    async def test_response_body_does_not_echo_password(
        self, async_client: AsyncClient
    ) -> None:
        """No error entry in the 422 body may contain the submitted password.

        The email is invalid so the request fails validation; the password is
        still carried in the parsed payload and would appear under ``input`` in
        an unfixed handler.
        """
        response = await async_client.post(
            "/auth/login",
            json={
                "email": "not-an-email",
                "password": _SENTINEL_PASSWORD,
            },
        )
        assert response.status_code == 422
        body = response.json()

        assert _SENTINEL_PASSWORD not in response.text

        for entry in _error_entries(body):
            assert "input" not in entry, "the offending raw value must not be echoed"
            assert _SENTINEL_PASSWORD not in str(entry)

    async def test_log_records_do_not_contain_password(
        self, async_client: AsyncClient
    ) -> None:
        """No log record for the request may contain the submitted password."""
        with _capture_handler_records() as records:
            response = await async_client.post(
                "/auth/login",
                json={
                    "email": "not-an-email",
                    "password": _SENTINEL_PASSWORD,
                },
            )

        assert response.status_code == 422
        assert records, "the validation handler must log the failure"

        leaked = [record for record in records if _SENTINEL_PASSWORD in record.getMessage()]
        assert leaked == [], (
            "the validation log record must not carry the submitted password: "
            f"{[record.getMessage() for record in leaked]}"
        )

    async def test_register_password_not_echoed(
        self, authenticated_client: AsyncClient
    ) -> None:
        """A register payload that fails validation must not echo the password.

        ``/auth/register`` is admin-only, so the authenticated (admin) client is
        used; the invalid email still forces a validation failure while the
        sentinel password is carried in the parsed payload.
        """
        with _capture_handler_records() as records:
            response = await authenticated_client.post(
                "/auth/register",
                json={
                    "email": "not-an-email",
                    "password": _SENTINEL_PASSWORD,
                    "role": "viewer",
                },
            )

        assert response.status_code == 422
        assert _SENTINEL_PASSWORD not in response.text
        assert not any(
            _SENTINEL_PASSWORD in record.getMessage() for record in records
        )

    async def test_change_password_payload_not_echoed(
        self, authenticated_client: AsyncClient
    ) -> None:
        """A change-password payload that fails validation must not echo any field.

        The sentinel is placed in ``new_password``, the exact field the defect
        report named; an over-long value fails the strength validator before the
        endpoint body runs, so the sentinel must not survive in the body or the
        logs.
        """
        with _capture_handler_records() as records:
            response = await authenticated_client.post(
                "/auth/change-password",
                json={
                    "current_password": "CurrentPass123!",
                    "new_password": _SENTINEL_NEW_PASSWORD,
                    "confirm_password": _SENTINEL_NEW_PASSWORD,
                },
            )

        assert response.status_code == 422
        assert _SENTINEL_NEW_PASSWORD not in response.text
        assert not any(
            _SENTINEL_NEW_PASSWORD in record.getMessage()
            for record in records
        )

    async def test_error_shape_keeps_loc_msg_type(
        self, async_client: AsyncClient
    ) -> None:
        """The sanitised entries still carry the useful, non-sensitive loc/msg/type."""
        response = await async_client.post(
            "/auth/login",
            json={
                "email": "not-an-email",
                "password": _SENTINEL_PASSWORD,
            },
        )
        assert response.status_code == 422
        entries = _error_entries(response.json())
        assert entries, "the validation failure must report at least one entry"
        for entry in entries:
            assert "loc" in entry
            assert "msg" in entry
            assert "type" in entry
