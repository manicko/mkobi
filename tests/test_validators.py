"""Tests for validator utility functions.

Tests:
- Email validation
- Password validation
- Role validation
- UUID validation
- String validation
- raise_if_invalid function
"""

import pytest

from mkobi.models.enums import UserRole
from mkobi.utils.validators import (
    raise_if_invalid,
    validate_email,
    validate_password,
    validate_password_or_raise,
    validate_role,
    validate_string,
    validate_uuid,
)
from mkobi.core.security import MAX_PASSWORD_LENGTH


class TestValidateEmail:
    """Tests for validate_email function."""

    def test_validate_valid_email(self):
        """Test valid email returns True."""
        assert validate_email("user@example.com") is True

    def test_validate_valid_email_with_subdomain(self):
        """Test valid email with subdomain returns True."""
        assert validate_email("user@mail.example.com") is True

    def test_validate_valid_email_with_plus(self):
        """Test valid email with plus sign returns True."""
        assert validate_email("user+tag@example.com") is True

    def test_validate_valid_email_with_dots(self):
        """Test valid email with dots in local part returns True."""
        assert validate_email("first.last@example.com") is True

    def test_validate_invalid_email_no_at_sign(self):
        """Test email without @ returns False."""
        assert validate_email("userexample.com") is False

    def test_validate_invalid_email_no_domain(self):
        """Test email without domain returns False."""
        assert validate_email("user@") is False

    def test_validate_invalid_email_no_tld(self):
        """Test email without TLD returns False."""
        assert validate_email("user@example") is False

    def test_validate_invalid_email_empty(self):
        """Test empty email returns False."""
        assert validate_email("") is False

    def test_validate_invalid_email_none(self):
        """Test None email returns False."""
        assert validate_email(None) is False

    def test_validate_invalid_email_not_string(self):
        """Test non-string email returns False."""
        assert validate_email(123) is False

    def test_validate_invalid_email_multiple_at_signs(self):
        """Test email with multiple @ signs returns False."""
        assert validate_email("user@@example.com") is False


class TestValidatePassword:
    """Tests for validate_password function."""

    def test_validate_valid_password(self):
        """Test valid password returns True."""
        assert validate_password("SecurePass123") is True

    def test_validate_valid_password_min_length(self):
        """Test password with minimum length returns True."""
        assert validate_password("Abcdefg1") is True

    def test_validate_password_too_short(self):
        """Test password shorter than minimum returns False."""
        assert validate_password("Abc1") is False

    def test_validate_password_no_digit(self):
        """Test password without digit returns False."""
        assert validate_password("NoDigitsHere") is False

    def test_validate_password_no_letter(self):
        """Test password without letter returns False."""
        assert validate_password("12345678") is False

    def test_validate_password_empty(self):
        """Test empty password returns False."""
        assert validate_password("") is False

    def test_validate_password_none(self):
        """Test None password returns False."""
        assert validate_password(None) is False

    def test_validate_password_custom_min_length(self):
        """Test password with custom min length validation."""
        assert validate_password("Short1", min_length=6) is True
        assert validate_password("Short1", min_length=8) is False




class TestValidateRole:
    """Tests for validate_role function."""

    def test_validate_admin_role(self):
        """Test admin role returns True."""
        assert validate_role("admin") is True

    def test_validate_editor_role(self):
        """Test editor role returns True."""
        assert validate_role("editor") is True

    def test_validate_viewer_role(self):
        """Test viewer role returns True."""
        assert validate_role("viewer") is True

    def test_validate_role_with_enum(self):
        """Test UserRole enum returns True."""
        assert validate_role(UserRole.ADMIN) is True
        assert validate_role(UserRole.EDITOR) is True
        assert validate_role(UserRole.VIEWER) is True

    def test_validate_invalid_role(self):
        """Test invalid role returns False."""
        assert validate_role("superadmin") is False

    def test_validate_invalid_role_empty(self):
        """Test empty role returns False."""
        assert validate_role("") is False


class TestValidateUuid:
    """Tests for validate_uuid function."""

    def test_validate_valid_uuid(self):
        """Test valid UUID returns True."""
        assert validate_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_validate_valid_uuid_generated(self):
        """Test generated UUID returns True."""
        from uuid import uuid4
        test_uuid = str(uuid4())
        assert validate_uuid(test_uuid) is True

    def test_validate_invalid_uuid(self):
        """Test invalid UUID returns False."""
        assert validate_uuid("not-a-uuid") is False

    def test_validate_invalid_uuid_partial(self):
        """Test partial UUID returns False."""
        assert validate_uuid("550e8400-e29b-41d4") is False

    def test_validate_invalid_uuid_empty(self):
        """Test empty string returns False."""
        assert validate_uuid("") is False


class TestValidateString:
    """Tests for validate_string function."""

    def test_validate_valid_string(self):
        """Test valid string returns True."""
        assert validate_string("hello") is True

    def test_validate_string_min_length(self):
        """Test string meets min length returns True."""
        assert validate_string("hello", min_length=3) is True

    def test_validate_string_too_short(self):
        """Test string shorter than min length returns False."""
        assert validate_string("hi", min_length=3) is False

    def test_validate_string_max_length(self):
        """Test string within max length returns True."""
        assert validate_string("hello", max_length=10) is True

    def test_validate_string_too_long(self):
        """Test string longer than max length returns False."""
        assert validate_string("hello world", max_length=5) is False

    def test_validate_string_required_empty(self):
        """Test required empty string returns False."""
        assert validate_string("", required=True) is False

    def test_validate_string_optional_empty(self):
        """Test optional empty string returns True."""
        assert validate_string("", required=False) is True

    def test_validate_string_none_required(self):
        """Test None with required=True returns False."""
        assert validate_string(None, required=True) is False

    def test_validate_string_none_optional(self):
        """Test None with required=False returns True."""
        assert validate_string(None, required=False) is True

    def test_validate_string_not_string(self):
        """Test non-string value returns False."""
        assert validate_string(12345) is False


class TestRaiseIfInvalid:
    """Tests for raise_if_invalid function."""

    def test_raise_if_invalid_condition_true(self):
        """Test no exception raised when condition is True."""
        raise_if_invalid(True, "error")  # Should not raise

    def test_raise_if_invalid_condition_false(self):
        """Test exception raised when condition is False."""
        with pytest.raises(ValueError):
            raise_if_invalid(False, "error message")

    def test_raise_if_invalid_custom_exception(self):
        """Test custom exception type can be raised."""
        with pytest.raises(TypeError):
            raise_if_invalid(False, "custom error", exception_type=TypeError)

    def test_raise_if_invalid_message_content(self):
        """Test exception message is correct."""
        with pytest.raises(ValueError) as exc_info:
            raise_if_invalid(False, "test error message")
        assert "test error message" in str(exc_info.value)

class TestValidatePasswordOrRaise:
    """Tests for validate_password_or_raise function."""

    def test_valid_password_no_exception(self):
        """Test valid password does not raise."""
        validate_password_or_raise("SecurePass123")  # Should not raise

    def test_invalid_password_too_short_raises(self):
        """Test short password raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_password_or_raise("short")
        assert "at least" in str(exc_info.value).lower()

    def test_invalid_password_no_digit_raises(self):
        """Test password without digit raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_password_or_raise("NoDigitsHere")
        assert "digit" in str(exc_info.value).lower()

    def test_invalid_password_no_letter_raises(self):
        """Test password without letter raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_password_or_raise("12345678")
        assert "letter" in str(exc_info.value).lower()

    def test_invalid_password_empty_raises(self):
        """Test empty password raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            validate_password_or_raise("")
        assert "required" in str(exc_info.value).lower()


class TestPasswordByteBudget:
    """SECB-10: the mint validator must measure the bcrypt byte budget.

    The bound is bytes, not characters: a 72-character multibyte password is over
    the budget and must be refused, while a 72-byte ASCII password is accepted.
    """

    def test_72_byte_ascii_password_accepted(self):
        """Exactly the byte budget is accepted."""
        password = "a" * (MAX_PASSWORD_LENGTH - 1) + "1"
        assert len(password.encode("utf-8")) == MAX_PASSWORD_LENGTH
        validate_password_or_raise(password)  # Should not raise

    def test_73_byte_ascii_password_refused(self):
        """One byte over the budget is refused."""
        password = "a" * MAX_PASSWORD_LENGTH + "1"
        assert len(password.encode("utf-8")) == MAX_PASSWORD_LENGTH + 1
        with pytest.raises(ValueError) as exc_info:
            validate_password_or_raise(password)
        assert "too long" in str(exc_info.value).lower() or "byte" in str(
            exc_info.value
        ).lower()

    def test_72_character_multibyte_password_refused(self):
        """A 72-character password over 72 bytes is refused.

        Each 'я' is 2 bytes in UTF-8, so 69 Cyrillic characters plus 'ab1'
        is 72 characters and 141 bytes: over the budget even though the
        character count equals the limit and the strength rules are met.
        """
        password = ("я" * 69) + "ab1"
        assert len(password) == 72
        assert len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH
        with pytest.raises(ValueError):
            validate_password_or_raise(password)
