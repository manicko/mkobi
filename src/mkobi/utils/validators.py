"""Utilities for data validation.

Provides functions for checking email, roles, UUIDs and strings.
Used for centralized validation throughout the application.
"""

import logging
import re
from uuid import UUID

from mkobi.models.enums import UserRole

logger = logging.getLogger(__name__)

# Regular expression for email validation
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_email(email: str) -> bool:
    """Check email address validity.

    Args:
        email: Email address to validate.

    Returns:
        True if email is valid, False otherwise.

    Example:
        >>> validate_email("user@example.com")
        True
        >>> validate_email("invalid-email")
        False
    """
    if not email or not isinstance(email, str):
        logger.warning("Email is empty or not a string")
        return False

    if not EMAIL_REGEX.match(email):
        logger.warning("Invalid email format: %s", email)
        return False

    return True


def validate_role(role: str | UserRole) -> bool:
    """Check if role is valid.

    Args:
        role: Role to validate (string or UserRole).

    Returns:
        True if role is valid, False otherwise.

    Example:
        >>> validate_role("admin")
        True
        >>> validate_role("invalid_role")
        False
    """
    try:
        if isinstance(role, UserRole):
            return True
        UserRole(role)
        return True
    except (ValueError, TypeError):
        logger.warning("Invalid role: %s", role)
        return False


def validate_uuid(uuid_str: str) -> bool:
    """Check if string is a valid UUID.

    Args:
        uuid_str: String to validate.

    Returns:
        True if string is a valid UUID, False otherwise.

    Example:
        >>> validate_uuid("550e8400-e29b-41d4-a716-446655440000")
        True
        >>> validate_uuid("not-a-uuid")
        False
    """
    try:
        UUID(uuid_str)
        return True
    except (ValueError, AttributeError):
        logger.warning("Invalid UUID: %s", uuid_str)
        return False


def validate_string(
    value: str,
    min_length: int = 0,
    max_length: int | None = None,
    required: bool = True,
) -> bool:
    """Check string against criteria.

    Args:
        value: String to validate.
        min_length: Minimum string length.
        max_length: Maximum string length (None - no limit).
        required: Whether field is required.

    Returns:
        True if string is valid, False otherwise.

    Example:
        >>> validate_string("hello", min_length=1, max_length=10)
        True
        >>> validate_string("", required=True)
        False
    """
    if value is None:
        if required:
            logger.warning("String is required but None was received")
            return False
        return True

    if not isinstance(value, str):
        logger.warning("Value is not a string: %s", type(value))
        return False

    if required and len(value) == 0:
        logger.warning("String cannot be empty")
        return False

    if len(value) < min_length:
        logger.warning(
            "String too short: %s < %s", len(value), min_length
        )
        return False

    if max_length is not None and len(value) > max_length:
        logger.warning(
            "String too long: %s > %s", len(value), max_length
        )
        return False

    return True


def validate_password(password: str, min_length: int = 8) -> bool:
    """Check password strength.

    Args:
        password: Password to validate.
        min_length: Minimum password length.

    Returns:
        True if password meets requirements, False otherwise.

    Example:
        >>> validate_password("SecurePass123")
        True
        >>> validate_password("short")
        False
    """
    if not password or not isinstance(password, str):
        logger.warning("Password is empty or not a string")
        return False

    if len(password) < min_length:
        logger.warning(
            "Password too short: %s < %s", len(password), min_length
        )
        return False

    # Check for at least one digit and one letter
    if not re.search(r"\d", password):
        logger.warning("Password must contain at least one digit")
        return False

    if not re.search(r"[a-zA-Z]", password):
        logger.warning("Password must contain at least one letter")
        return False

    return True


def validate_password_or_raise(password: str, min_length: int = 8) -> None:
    """Validate password and raise ValueError if invalid.

    Enforces the bcrypt byte budget in addition to the strength rules, because
    the hasher cannot represent more than ``MAX_PASSWORD_LENGTH`` bytes: a value
    beyond it would be silently truncated at mint time, letting a later submitter
    who supplies only the truncated prefix authenticate. The check is bytes, not
    characters, so a multibyte password under the character limit but over the
    byte budget is refused.

    The byte constant is read from its owning module (``mkobi.core.security``) at
    call time rather than imported at module load: ``mkobi.config`` imports
    ``mkobi.models`` during its own import, and this module is reached from
    ``mkobi.models.auth``, so a top-level import of ``mkobi.core.security`` (which
    imports ``mkobi.config``) would close a circular import.

    Args:
        password: Password to validate.
        min_length: Minimum password length.

    Raises:
        ValueError: If password does not meet strength requirements or exceeds
            the bcrypt byte budget.
    """
    from mkobi.core.security import MAX_PASSWORD_LENGTH

    if not password or not isinstance(password, str):
        raise ValueError("Password is required")

    if len(password) < min_length:
        raise ValueError(f"Password must be at least {min_length} characters long")

    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")

    if not re.search(r"[a-zA-Z]", password):
        raise ValueError("Password must contain at least one letter")

    if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"Password is too long: at most {MAX_PASSWORD_LENGTH} bytes are allowed"
        )

    return None

def raise_if_invalid(condition: bool, message: str, exception_type: type = ValueError) -> None:
    """Raise exception if condition is false.

    Args:
        condition: Condition to check.
        message: Error message.
        exception_type: Exception type.

    Raises:
        exception_type: If condition is False.
    """
    if not condition:
        logger.error("Validation error: %s", message)
        raise exception_type(message)
