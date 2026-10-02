"""Code-first classification of upload failures by the route's error mapper.

The upload route maps a ``ValueError`` raised during admission to an
``AppException`` carrying an ``ErrorCode``. The mapper is code-first: an
exception carrying a usable ``ErrorCode`` is classified by that code, and only
exceptions with no usable code fall through to the documented substring table.
"""
import pytest

from mkobi.api.routes.upload import _handle_value_error
from mkobi.models.enums import ErrorCode
from mkobi.utils.exceptions import AppException


class TestUploadValueErrorClassification:
    """Classification of upload admission failures by ``_handle_value_error``."""

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            # Code-first: an AppException carrying a code is classified by it,
            # even when its message text matches a different substring branch.
            # "rate limit" in the detail would send the old table to
            # RATE_LIMIT_EXCEEDED; the code must win.
            pytest.param(
                AppException(code=ErrorCode.VALIDATION_ERROR, detail="rate limit details absent"),
                ErrorCode.VALIDATION_ERROR,
                id="app_exception_validation_error_misleading_text",
            ),
            # "exceeds" in the detail would send the substring table to
            # FILE_TOO_LARGE; the carried code must win.
            pytest.param(
                AppException(code=ErrorCode.INVALID_FILE_TYPE, detail="exceeds nothing"),
                ErrorCode.INVALID_FILE_TYPE,
                id="app_exception_invalid_file_type_misleading_text",
            ),
            # Code-less: the substring fallback still classifies it.
            pytest.param(
                ValueError("Invalid MIME type"),
                ErrorCode.INVALID_FILE_TYPE,
                id="value_error_mime_fallback",
            ),
            pytest.param(
                ValueError("Unsupported extension"),
                ErrorCode.INVALID_FILE_TYPE,
                id="value_error_extension_fallback",
            ),
            pytest.param(
                ValueError("File size exceeds the max allowed"),
                ErrorCode.FILE_TOO_LARGE,
                id="value_error_size_fallback",
            ),
            pytest.param(
                ValueError("rate limit reached"),
                ErrorCode.RATE_LIMIT_EXCEEDED,
                id="value_error_rate_limit_fallback",
            ),
            pytest.param(
                ValueError("unidentified problem"),
                ErrorCode.VALIDATION_ERROR,
                id="value_error_default",
            ),
        ],
    )
    def test_maps_by_code_first_then_fallback(self, error, expected):
        """Every row of the (exception, code) table classifies as expected."""
        with pytest.raises(AppException) as exc_info:
            _handle_value_error(error)
        assert exc_info.value.code == expected

    def test_every_emitted_code_is_a_mapped_error_code_member(self):
        """Classifier output can never drift from the ErrorCode enum."""
        emitted: list[ErrorCode] = []
        for error in [
            ValueError("Invalid MIME type"),
            ValueError("Unsupported extension"),
            ValueError("File size exceeds the max"),
            ValueError("rate limit reached"),
            ValueError("unidentified problem"),
        ]:
            with pytest.raises(AppException) as exc_info:
                _handle_value_error(error)
            emitted.append(exc_info.value.code)
        valid = {code.value for code in ErrorCode}
        assert {code.value for code in emitted} <= valid
