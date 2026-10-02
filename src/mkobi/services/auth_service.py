"""User authentication and registration service.

Provides business logic for registration, authentication and authorization
users in the BI Dashboard system. Uses class-based approach.
"""

from __future__ import annotations

import re
import secrets
import string
from typing import TYPE_CHECKING, Any, cast

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.core.logging_config import get_logger
from mkobi.core.redis_client import get_async_redis_client
from mkobi.core.security import (
    AsyncRateLimiter,
    create_access_token,
    decode_token,
    hash_password,
    validate_refresh_token,
    verify_password,
)
from mkobi.interfaces.repository_interfaces import IRegistrationRequestRepository, IUserRepository
from mkobi.interfaces.service_interfaces import IAuthService
from mkobi.utils.validators import validate_password_or_raise
from mkobi.models.enums import RegistrationStatus, UserRole
from mkobi.models.user import UserRead

if TYPE_CHECKING:
    from mkobi.core.temp_password_store import TempPasswordStore

logger = get_logger(__name__)

# Regular expression for email validation
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class AuthService(IAuthService):
    """User authentication and registration service.

    Implements IAuthService interface. Uses class-based approach
    for all authentication and registration operations.
    """

    def __init__(
        self,
        user_repo: IUserRepository,
        reg_request_repo: IRegistrationRequestRepository,
        config: Any | None = None,
        temp_password_store: TempPasswordStore | None = None,
    ) -> None:
        self.user_repo = user_repo
        self.reg_request_repo = reg_request_repo
        self.temp_password_store = temp_password_store
        # Store config and preprocess blocked domains for efficient lookup
        if config is None:
            from mkobi.config import get_config
            config = get_config()
        self.config = config
        self.blocked_domains_set = set(domain.lower() for domain in config.email.blocked_domains)
        self._rate_limiter = AsyncRateLimiter(
            get_async_redis_client(),
            fail_closed=config.rate_limiter_fail_closed,
        )

    def _validate_role(self, role: str) -> None:
        """Validate that role is allowed.

        Args:
            role: User role to validate.

        Raises:
            ValueError: If role is not in allowed list.
        """
        try:
            UserRole(role)
        except ValueError as err:
            logger.error(
                "Invalid role",
                extra={"role": role, "allowed_roles": [e.value for e in UserRole]},
            )
            raise ValueError(
                f"Invalid role: '{role}'. "
                f"Allowed values: {', '.join([e.value for e in UserRole])}"
            ) from err

    def _validate_email_format(self, email: str) -> str:
        """Validate email format using regular expression.

        Args:
            email: Email to validate.

        Returns:
            str: Valid email.

        Raises:
            ValueError: If email has incorrect format.
        """
        if not EMAIL_REGEX.match(email):
            logger.error("Invalid email format", extra={"email": email})
            raise ValueError(f"Invalid email format: '{email}'")
        return email

    async def _check_email_uniqueness(self, email: str, db: AsyncSession) -> None:
        """Check that email is not used by another user.

        Args:
            email: Email to check for uniqueness.
            db: Async database session.

        Raises:
            ValueError: If user with such email already exists.
        """
        existing_user = await self.user_repo.get_by_email(email=email, db=db)
        if existing_user is not None:
            logger.warning(
                "Registration attempt with existing email", extra={"email": email}
            )
            raise ValueError(f"User with email '{email}' already exists")

    async def register_user(
        self,
        email: str,
        password: str,
        db: AsyncSession,
        role: str = "viewer",
    ) -> UserRead:
        """Register new user.

        Args:
            email: User email (will be validated).
            password: User password (will be hashed).
            db: Async database session.
            role: User role (admin, editor, viewer).

        Returns:
            UserRead: Model without password.

        Raises:
            ValueError: If email is invalid, role is invalid,
                password does not meet strength requirements,
                or user already exists.
        """
        self._validate_role(role)
        self._validate_email_format(email)
        validate_password_or_raise(password)
        logger.info("Starting user registration", extra={"email": email, "role": role})

        await self._check_email_uniqueness(email, db)

        try:
            password_hash = hash_password(password)
            logger.info("Password successfully hashed", extra={"email": email})

            user = await self.user_repo.create(
                db=db,
                email=email,
                password_hash=password_hash,
                role=role,
            )
            if user is None:
                raise ValueError("Error creating user")

            await db.commit()

            logger.info(
                "User successfully registered",
                extra={"id": str(user.id), "email": email, "role": role},
            )
            return cast(UserRead, UserRead.model_validate(user))
        except Exception as e:
            logger.error(
                "Error during user registration",
                extra={"email": email, "error": str(e)},
            )
            raise

    async def login_user(
        self,
        email: str,
        password: str,
        db: AsyncSession,
    ) -> dict[str, Any] | None:
        """Authenticate user by email and password.

        Args:
            email: User email.
            password: User password.
            db: Async database session.

        Returns:
            dict: Token data with user data if authentication successful, None otherwise.
        """
        logger.info("Attempting user authentication", extra={"email": email})

        user_obj = await self.user_repo.get_by_email_with_hash(email=email, db=db)
        if user_obj is None:
            # Perform dummy bcrypt call to prevent timing side-channel attack.
            # Without this, an attacker can distinguish "user not found" (fast)
            # from "wrong password" (slow bcrypt verify) by measuring response time.
            verify_password(
                password,
                "$2b$12$dummy.hash.to.prevent.timing.side.channel.attack.dummy.hash",
            )
            return None

        if not verify_password(password, user_obj.password_hash):
            return None

        # is_active is authoritative at login: a deactivated row is refused here
        # exactly as a wrong password is, with the same None contract that
        # api/routes/auth.py::_handle_login turns into AUTHENTICATION_FAILED.
        # Compare the ORM row, not the projected UserRead.
        if not user_obj.is_active:
            logger.info(
                "Login refused for deactivated user", extra={"email": email}
            )
            return None

        logger.info("User successfully authenticated", extra={"email": email})
        user_read = cast(UserRead, UserRead.model_validate(user_obj))
        return {
            "access_token": create_access_token({
                "user_id": str(user_obj.id),
                "email": email,
                "role": user_obj.role,
            }),
            "token_type": "bearer",
            "user": user_read,
        }


    async def authenticate_user(
        self, email: str, password: str, db: AsyncSession
    ) -> UserRead | None:
        """Authenticate user and return user data.

        Args:
            email: User email.
            password: User password.
            db: Optional database session.

        Returns:
            UserRead: User model without password, or None.
        """
        result = await self.login_user(email, password, db)
        if result is None:
            return None
        return cast(UserRead, result["user"])

    def create_access_token(self, user_id: UUID, role: str) -> str:
        """Create access token for user.

        Args:
            user_id: User ID.
            role: User role.

        Returns:
            str: JWT token string.
        """
        return str(create_access_token({"user_id": str(user_id), "email": "", "role": role}))

    async def refresh_token(
        self, user_id: UUID, email: str, role: str
    ) -> dict[str, Any]:
        """Refresh JWT access token for user.

        Args:
            user_id: User ID.
            email: User email.
            role: User role.

        Returns:
            dict: New token data with access_token and token_type.
        """
        logger.info("Refreshing token", extra={"user_id": str(user_id)})

        token = create_access_token({
            "user_id": str(user_id),
            "email": email,
            "role": role,
        })

        logger.info("Token refreshed", extra={"user_id": str(user_id)})
        return {
            "access_token": token,
            "token_type": "bearer",
        }

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify JWT token.

        Args:
            token: JWT token to verify.

        Returns:
            dict: Token payload if valid, None otherwise.
        """
        payload = decode_token(token)
        if payload is None:
            logger.warning("Invalid token during verification")
            return None

        logger.info("Token verified", extra={"user_id": payload.get("user_id")})
        return dict(payload)

    def validate_refresh_token(self, token: str) -> dict[str, Any] | None:
        """Validate a refresh token and return user data.

        Args:
            token: The refresh token string.

        Returns:
            User data dict if valid, None otherwise.
        """
        logger.info("Validating refresh token")
        result = validate_refresh_token(token)
        if result is None:
            logger.warning("Invalid refresh token")
            return None
        # Refresh tokens use "sub" for user ID (JWT standard)
        user_id = result.get("sub")
        logger.info("Refresh token validated", extra={"user_id": user_id})
        return dict(result)

    async def get_user_by_id(
        self, user_id: UUID, db: AsyncSession
    ) -> UserRead | None:
        """Get user by ID.

        Args:
            user_id: User ID.
            db: Async database session.

        Returns:
            UserRead: User model without password, or None.
        """
        logger.info("Getting user by id", extra={"user_id": str(user_id)})

        user_obj = await self.user_repo.get(user_id, db)
        if user_obj is None:
            logger.warning("User not found", extra={"user_id": str(user_id)})
            return None

        return cast(UserRead, UserRead.model_validate(user_obj))

    async def get_user_by_email(
        self, email: str, db: AsyncSession
    ) -> UserRead | None:
        """Get user by email.

        Args:
            email: User email.
            db: Async database session.

        Returns:
            UserRead: User model without password, or None.
        """
        logger.info("Getting user by email", extra={"email": email})

        user_obj = await self.user_repo.get_by_email(email=email, db=db)
        if user_obj is None:
            logger.warning("User not found", extra={"email": email})
            return None

        return cast(UserRead, UserRead.model_validate(user_obj))

    async def create_user(
        self,
        email: str,
        password: str,
        role: UserRole,
        db: AsyncSession,
    ) -> UserRead:
        """Create new user (admin only).

        Args:
            email: User email.
            password: User password.
            role: User role.
            db: Async database session.

        Returns:
            UserRead: Created user model.
        """
        return await self.register_user(email, password, db, role)

    async def register_request(
        self, email: str, ip: str | None, db: AsyncSession
    ) -> dict[str, Any]:
        """Create registration request.

        Args:
            email: User email.
            db: Async database session.
            ip: Client IP address.

        Returns:
            dict: Created request data.

        Raises:
            ValueError: If request with this email already exists.
        """
        logger.info("Creating registration request", extra={"email": email, "ip": ip})

        # Guard against malformed email addresses
        if '@' not in email:
            logger.warning(
                "Registration attempt with invalid email (missing '@')",
                extra={"email": email}
            )
            raise ValueError("Invalid email format")

        # Extract and normalize email domain to lowercase for case-insensitive comparison
        email_domain = email.split('@')[1].lower()

        # Check if request with this email already exists (before domain check)
        existing_request = await self.reg_request_repo.get_by_email(email, db)
        if existing_request is not None:
            if existing_request.status in (
                RegistrationStatus.PENDING,
                RegistrationStatus.APPROVED,
            ):
                logger.warning(
                    "Registration request already exists (active)",
                    extra={"email": email, "status": existing_request.status.value}
                )
                raise ValueError("Unable to process registration request")
            if existing_request.status == RegistrationStatus.REJECTED:
                logger.warning(
                    "Registration request already exists (rejected)",
                    extra={"email": email, "status": existing_request.status.value}
                )
                raise ValueError("Unable to process registration request")

        # Check if email domain is blocked
        if email_domain in self.blocked_domains_set:
            logger.warning(
                "Registration attempt with blocked email domain",
                extra={"email": email, "domain": email_domain}
            )
            raise ValueError("Unable to process registration request")

        # Check if user with this email already exists
        existing_user = await self.user_repo.get_by_email(email=email, db=db)
        if existing_user is not None:
            logger.warning("User already exists", extra={"email": email})
            raise ValueError("Unable to process registration request")

        try:
            req = await self.reg_request_repo.create(email, ip, db)
            if req is None:
                raise ValueError("Error creating registration request")

            await db.commit()  # Commit the transaction

            logger.info(
                "Registration request created",
                extra={"id": str(req.id), "email": email},
            )

            return {
                "id": req.id,
                "email": req.email,
                "status": req.status.value,
            }
        except Exception as e:
            logger.error(
                "Error creating registration request",
                extra={"email": email, "error": str(e)},
            )
            raise

    async def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
        db: AsyncSession,
    ) -> bool:
        """Change user password.

        Args:
            user_id: User ID.
            current_password: Current password for verification.
            new_password: New password to set.
            db: Async database session.

        Returns:
            True if password changed successfully.

        Raises:
            ValueError: If current password is wrong or new password equals current.
        """
        logger.info("Password change attempt", extra={"user_id": str(user_id)})

        # Get user by ID with hash for verification
        user_obj = await self.user_repo.get_with_hash(user_id, db)
        if user_obj is None:
            logger.warning("User not found for password change", extra={"user_id": str(user_id)})
            raise ValueError("User not found")

        if not verify_password(current_password, user_obj.password_hash):
            logger.warning(
                "Incorrect current password during change",
                extra={"user_id": str(user_id)},
            )
            raise ValueError("Current password is incorrect")

        if current_password == new_password:
            logger.warning(
                "New password same as current",
                extra={"user_id": str(user_id)},
            )
            raise ValueError("New password must be different from current password")

        password_hash = hash_password(new_password)
        await self.user_repo.update(
            user_id, db, password_hash=password_hash, force_password_change=False
        )
        await db.commit()

        logger.info("Password changed successfully", extra={"user_id": str(user_id)})
        return True

    def _generate_temp_password(self, length: int = 16) -> str:
        """Generate a cryptographically secure 16-char password with letters + digits.

        Ensures at least one letter and one digit. Up to 3 attempts
        to produce a password passing Pydantic validation.
        """
        alphabet = string.ascii_letters + string.digits
        for _attempt in range(3):
            password = "".join(secrets.choice(alphabet) for _ in range(length))
            if re.search(r"[a-zA-Z]", password) and re.search(r"\d", password):
                return password
        # Fallback (astronomically unlikely to reach)
        password = secrets.choice(string.ascii_letters) + secrets.choice(string.digits)
        password += "".join(secrets.choice(alphabet) for _ in range(length - 2))
        # Shuffle to avoid predictable positions
        password_list = list(password)
        secrets.SystemRandom().shuffle(password_list)
        return "".join(password_list)

    async def reset_password_admin(
        self,
        user_id: UUID,
        admin_user_id: UUID,
        db: AsyncSession,
    ) -> dict[str, Any] | None:
        """Admin-triggered password reset.

        Generates a temp password, hashes it, saves it to the user record, sets
        the force_password_change flag, commits, and only then stores the temp
        password in Redis so the credential is never durable before the commit
        that makes it valid.

        The store fails open by design, so a non-raising call is not proof that
        the credential is retrievable; it is logged by the store only.

        Returns:
            dict with message, user_id, retrieval_token on success.
            None if user not found.

        Raises:
            ValueError: If admin resets own password.
        """
        logger.info(
            "Admin password reset: user_id=%s, admin_id=%s",
            user_id, admin_user_id,
        )

        if user_id == admin_user_id:
            logger.warning(
                "Admin attempted self-password-reset: %s", admin_user_id,
            )
            raise ValueError("Admin cannot reset own password")

        user_obj = await self.user_repo.get_with_hash(user_id, db)
        if user_obj is None:
            logger.warning(
                "User not found for password reset: %s", user_id,
            )
            return None

        temp_password = self._generate_temp_password()
        validate_password_or_raise(temp_password)
        password_hash = hash_password(temp_password)

        await self.user_repo.update(
            user_id, db,
            password_hash=password_hash,
            force_password_change=True,
        )
        await db.commit()

        # Durable side effect placed after the commit on purpose: only now is
        # the credential tied to a committed user record.
        retrieval_token = str(uuid4())
        if self.temp_password_store is not None:
            await self.temp_password_store.store(retrieval_token, temp_password)

        logger.info(
            "Password reset successful: user_id=%s, token=%s...", user_id, retrieval_token[:8],
        )
        return {
            "message": "Password reset successfully",
            "user_id": str(user_id),
            "retrieval_token": retrieval_token,
        }

    async def approve_registration_request(
        self,
        request_id: UUID,
        admin_user_id: UUID,
        db: AsyncSession,
    ) -> dict[str, Any] | None:
        """Approve a pending registration request and provision the user.

        Owns the whole transaction: create the user, set the
        force_password_change flag, mark the request approved, commit, and only
        then hand the temporary password to the store. The store is a
        non-transactional side effect, so it must run after the commit that
        makes the user real; a failure after the commit leaves an existing user
        with a not-yet-retrievable credential (recoverable) instead of a live
        retrieval token pointing at a user who does not exist.

        The store fails open by design, so a non-raising call is not proof that
        the credential is retrievable; it is logged by the store only.

        Returns:
            dict with message, user_id and retrieval_token on success.
            None if the registration request does not exist.
        """
        logger.info(
            "Approving registration request: id=%s, admin_id=%s",
            request_id, admin_user_id,
        )

        req = await self.reg_request_repo.get_by_id(request_id, db=db)
        if req is None:
            logger.warning("Registration request not found: %s", request_id)
            return None

        if req.status != RegistrationStatus.PENDING:
            logger.warning(
                "Registration request already %s: id=%s", req.status, request_id,
            )
            return None

        temp_password = self._generate_temp_password()
        user = await self.create_user(
            email=req.email,
            password=temp_password,
            role=UserRole.VIEWER,
            db=db,
        )

        # User must change the temporary password on first login.
        await self.user_repo.update(user.id, db, force_password_change=True)

        await self.reg_request_repo.update_status(
            request_id=request_id,
            status=RegistrationStatus.APPROVED,
            db=db,
            reviewed_by=admin_user_id,
        )
        await db.commit()

        # Durable side effect placed after the commit on purpose: only now is
        # the credential tied to a user that exists.
        retrieval_token = str(uuid4())
        if self.temp_password_store is not None:
            await self.temp_password_store.store(retrieval_token, temp_password)

        logger.info(
            "Registration request approved: id=%s, user_id=%s",
            request_id, user.id,
        )
        return {
            "message": "Registration request approved",
            "user_id": str(user.id),
            "retrieval_token": retrieval_token,
        }
