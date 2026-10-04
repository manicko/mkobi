"""Tests for security module (security.py)."""

from datetime import timedelta
from unittest.mock import patch
from jose import jwt

from mkobi.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_refresh_token,
    _truncate_password,
)
from mkobi.config import get_config
from mkobi.core.security import MAX_PASSWORD_LENGTH



class TestTruncatePassword:
    """Tests for _truncate_password function."""

    def test_long_password_truncated(self):
        """Password longer than 72 bytes should be truncated."""
        password = "a" * 100
        result = _truncate_password(password)
        assert len(result.encode("utf-8")) <= 72
        assert result == "a" * 72

    def test_unicode_password_truncated(self):
        """Unicode password should be correctly truncated."""
        password = "α" * 50  # Each character is 2 bytes in UTF-8
        result = _truncate_password(password)
        assert len(result.encode("utf-8")) <= 72


class TestHashPassword:
    """Tests for hash_password function."""

    def test_hash_returns_string(self):
        """Hash should be a string."""
        result = hash_password("test_password")
        assert isinstance(result, str)

    def test_hash_starts_with_bcrypt_prefix(self):
        """Bcrypt hash should start with $2b$."""
        result = hash_password("test_password")
        assert result.startswith("$2b$")

    def test_different_passwords_different_hashes(self):
        """Different passwords should produce different hashes."""
        hash1 = hash_password("password1")
        hash2 = hash_password("password2")
        assert hash1 != hash2

    def test_same_password_same_hash(self):
        """Same passwords should produce different hashes (due to salt)."""
        # Due to random salt, hashes will be different, but verification should work
        hash1 = hash_password("same_password")
        hash2 = hash_password("same_password")
        assert hash1 != hash2  # Salts are different, so hashes are different
        assert verify_password("same_password", hash1)
        assert verify_password("same_password", hash2)

    def test_hash_long_password(self):
        """Hash long password (more than 72 bytes)."""
        long_password = "a" * 100
        result = hash_password(long_password)
        assert isinstance(result, str)
        assert result.startswith("$2b$")

    def test_hash_empty_password(self):
        """Hash empty password."""
        result = hash_password("")
        assert isinstance(result, str)
        assert result.startswith("$2b$")

    def test_hash_special_characters(self):
        """Hash password with special characters."""
        special_password = "p@ssw0rd!#$%^&*()"
        result = hash_password(special_password)
        assert isinstance(result, str)
        assert verify_password(special_password, result)


class TestVerifyPassword:
    """Tests for verify_password function."""

    def test_correct_password(self):
        """Correct password should pass verification."""
        password = "correct_password"
        hash_value = hash_password(password)
        assert verify_password(password, hash_value) is True

    def test_incorrect_password(self):
        """Incorrect password should not pass verification."""
        password = "correct_password"
        wrong_password = "wrong_password"
        hash_value = hash_password(password)
        assert verify_password(wrong_password, hash_value) is False

    def test_empty_password(self):
        """Test empty password verification."""
        hash_value = hash_password("")
        assert verify_password("", hash_value) is True
        assert verify_password("not_empty", hash_value) is False

    def test_long_password_verification(self):
        """Test long password verification."""
        long_password = "a" * 100
        hash_value = hash_password(long_password)
        assert verify_password(long_password, hash_value) is True

    def test_invalid_hash_format(self):
        """Invalid hash format should return False."""
        assert verify_password("password", "invalid_hash") is False

    def test_empty_hash(self):
        """Empty hash should return False."""
        assert verify_password("password", "") is False

    def test_unicode_password_verification(self):
        """Test Unicode password verification."""
        unicode_password = "password123αβγ"
        hash_value = hash_password(unicode_password)
        assert verify_password(unicode_password, hash_value) is True


class TestCreateAccessToken:
    """Tests for create_access_token function."""

    def test_token_is_string(self):
        """Token should be a string."""
        token = create_access_token({"user_id": "1"})
        assert isinstance(token, str)

    def test_token_contains_dot(self):
        """JWT token should contain dots (format header.payload.signature)."""
        token = create_access_token({"user_id": "1"})
        parts = token.split(".")
        assert len(parts) == 3

    def test_token_with_user_data(self):
        """Token should contain the provided data."""
        data = {"user_id": "123", "email": "test@example.com"}
        token = create_access_token(data)
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded["user_id"] == "123"
        assert decoded["email"] == "test@example.com"

    def test_token_with_custom_expiry(self):
        """Token with custom expiry time."""
        data = {"user_id": "1"}
        expires_delta = timedelta(minutes=60)
        token = create_access_token(data, expires_delta=expires_delta)
        decoded = decode_token(token)
        assert decoded is not None
        assert "exp" in decoded

    def test_token_has_exp_claim(self):
        """Token should contain expiration time (exp)."""
        token = create_access_token({"user_id": "1"})
        decoded = decode_token(token)
        assert decoded is not None
        assert "exp" in decoded

    def test_different_tokens_for_different_data(self):
        """Different data should produce different tokens."""
        token1 = create_access_token({"user_id": "1"})
        token2 = create_access_token({"user_id": "2"})
        assert token1 != token2

    def test_empty_data_token(self):
        """Token with empty data."""
        token = create_access_token({})
        decoded = decode_token(token)
        assert decoded is not None
        assert "exp" in decoded


class TestDecodeToken:
    """Tests for decode_token function."""

    def test_valid_token_decoding(self):
        """Decode valid token."""
        token = create_access_token({"user_id": "1", "email": "test@example.com"})
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded["user_id"] == "1"
        assert decoded["email"] == "test@example.com"

    def test_invalid_token_returns_none(self):
        """Invalid token should return None."""
        result = decode_token("invalid.token.here")
        assert result is None

    def test_empty_token_returns_none(self):
        """Empty token should return None."""
        result = decode_token("")
        assert result is None

    def test_malformed_token_returns_none(self):
        """Malformed token should return None."""
        result = decode_token("not.a.token")
        assert result is None

    def test_token_with_wrong_signature(self):
        """Token with wrong signature should return None."""
        # Create token with correct key
        token = create_access_token({"user_id": "1"})
        # Try to decode with different key (simulating an error)
        with patch("mkobi.core.security.get_config") as mock_get_config:
            mock_config = mock_get_config.return_value
            mock_config.jwt.secret_key = "wrong_secret"
            mock_config.jwt.algorithm = "HS256"
            result = decode_token(token)
            assert result is None

    def test_expired_token_returns_none(self):
        """Expired token should return None."""
        # Create token with negative expiry time (already expired)
        expired_delta = timedelta(seconds=-1)
        token = create_access_token({"user_id": "1"}, expires_delta=expired_delta)
        result = decode_token(token)
        assert result is None

    def test_token_without_exp_claim(self):
        """Token without exp claim (if created manually) should be decoded."""
        # Create token manually without exp
        payload = {"user_id": "1"}
        token = jwt.encode(
            payload,
            get_config().jwt.secret_key,
            algorithm=get_config().jwt.algorithm,
        )
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded["user_id"] == "1"
        assert "exp" not in decoded

    def test_token_with_additional_claims(self):
        """Token with additional fields."""
        data = {
            "user_id": "1",
            "email": "test@example.com",
            "role": "admin",
            "permissions": ["view", "edit"],
        }
        token = create_access_token(data)
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded["user_id"] == "1"
        assert decoded["email"] == "test@example.com"
        assert decoded["role"] == "admin"
        assert decoded["permissions"] == ["view", "edit"]


class TestValidateRefreshToken:
    """Tests for validate_refresh_token function."""

    def test_valid_refresh_token(self):
        """Valid refresh token should return payload."""
        data = {"user_id": "123", "email": "test@example.com", "role": "user"}
        token = create_refresh_token(data)
        payload = validate_refresh_token(token)
        assert payload is not None
        assert payload["user_id"] == "123"
        assert payload["email"] == "test@example.com"
        assert payload["role"] == "user"

    def test_invalid_refresh_token_returns_none(self):
        """Invalid refresh token should return None."""
        result = validate_refresh_token("invalid.token.here")
        assert result is None

    def test_empty_refresh_token_returns_none(self):
        """Empty refresh token should return None."""
        result = validate_refresh_token("")
        assert result is None

    def test_malformed_refresh_token_returns_none(self):
        """Malformed refresh token should return None."""
        result = validate_refresh_token("not.a.token")
        assert result is None

    def test_expired_refresh_token_returns_none(self):
        """Expired refresh token should return None."""
        # Create expired token manually
        from datetime import datetime, UTC
        expired_payload = {
            "user_id": "1",
            "exp": datetime.now(UTC) - timedelta(seconds=1),  # Already expired
        }
        expired_token = jwt.encode(
            expired_payload,
            get_config().jwt.secret_key,
            algorithm=get_config().jwt.algorithm,
        )
        result = validate_refresh_token(expired_token)
        assert result is None

    def test_refresh_token_with_wrong_signature_returns_none(self):
        """Refresh token with wrong signature should return None."""
        token = create_refresh_token({"user_id": "1"})
        with patch("mkobi.core.security.get_config") as mock_get_config:
            mock_config = mock_get_config.return_value
            mock_config.jwt.secret_key = "wrong_secret"
            mock_config.jwt.algorithm = "HS256"
            result = validate_refresh_token(token)
            assert result is None


class TestIntegration:
    """Integration tests."""

    def test_full_password_hash_and_verify_cycle(self):
        """Full cycle: hash and verify password."""
        original_password = "My$ecureP@ssw0rd!"
        hash_value = hash_password(original_password)
        assert verify_password(original_password, hash_value) is True
        assert verify_password("WrongPassword", hash_value) is False

    def test_full_token_create_and_decode_cycle(self):
        """Full cycle: create and decode token."""
        user_data = {"user_id": "42", "email": "user42@example.com"}
        token = create_access_token(user_data)
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded["user_id"] == "42"
        assert decoded["email"] == "user42@example.com"

    def test_token_expiration_from_config(self):
        """Verify that token expiration is taken from configuration."""
        token = create_access_token({"user_id": "1"})
        decoded = decode_token(token)
        assert decoded is not None
        assert "exp" in decoded
        # exp should be in the future
        import time

        assert decoded["exp"] > time.time()

    def test_multiple_users_different_tokens(self):
        """Different users should have different tokens."""
        token1 = create_access_token({"user_id": "1"})
        token2 = create_access_token({"user_id": "2"})
        token3 = create_access_token({"user_id": "3"})
        assert token1 != token2 != token3
        assert decode_token(token1)["user_id"] == "1"
        assert decode_token(token2)["user_id"] == "2"
        assert decode_token(token3)["user_id"] == "3"

    def test_password_hash_uniqueness(self):
        """Hashes of the same password should be different (due to salt)."""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)

    def test_token_with_user_id_only(self):
        """Token with only user_id."""
        token = create_access_token({"user_id": "999"})
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded["user_id"] == "999"



class TestVerifyTruncationUnchanged:
    """SECB-10: verification still truncates a legacy over-length credential.

    The mint path refuses a password the hasher cannot represent; the verify path
    must stay byte-symmetric with hashing so a user who already holds a stored
    hash of a >72-byte password can still authenticate with the same value.
    """

    def test_legacy_over_length_password_still_verifies(self):
        """A >72-byte password hashed before the mint bound still verifies."""
        legacy_password = "z" * (MAX_PASSWORD_LENGTH + 28)
        assert len(legacy_password.encode("utf-8")) > MAX_PASSWORD_LENGTH
        stored_hash = hash_password(legacy_password)

        assert verify_password(legacy_password, stored_hash) is True

    def test_legacy_password_matches_its_truncated_prefix(self):
        """The stored hash is over the first 72 bytes, as it always was."""
        legacy_password = "z" * (MAX_PASSWORD_LENGTH + 28)
        stored_hash = hash_password(legacy_password)

        prefix = "z" * MAX_PASSWORD_LENGTH
        assert verify_password(prefix, stored_hash) is True
