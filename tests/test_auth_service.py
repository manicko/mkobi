"""Unit tests for AuthService business logic."""
import re
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.core.security import hash_password
from mkobi.models.enums import RegistrationStatus, UserRole
from mkobi.models.user import UserRead
from mkobi.services.auth_service import AuthService


@pytest.mark.asyncio
class TestAuthService:
    """Unit tests for AuthService business logic."""

    @pytest.fixture
    def mock_user_repo(self):
        """Create a mock user repository."""
        mock = AsyncMock()
        mock.get_by_email.return_value = None
        mock.get_by_email_with_hash.return_value = None
        mock.get.return_value = None
        mock.get_all.return_value = []
        return mock

    @pytest.fixture
    def mock_reg_request_repo(self):
        """Create a mock registration request repository."""
        return AsyncMock()

    @pytest.fixture
    def auth_service(self, mock_user_repo, mock_reg_request_repo):
        """Create AuthService with mocked repositories."""
        return AuthService(mock_user_repo, mock_reg_request_repo)

    # --- register_user tests ---

    async def test_register_user_success(self, auth_service, mock_user_repo, mock_db):
        """Test successful user registration."""
        mock_user_repo.get_by_email.return_value = None
        mock_user_repo.create.return_value = MagicMock(
            id=uuid4(),
            email="test@example.com",
            role="viewer",
            is_active=True,
            password_hash=hash_password("TestPass123!"),
        )

        result = await auth_service.register_user(
                email="test@example.com",
                password="TestPass123!",
                db=mock_db,
                role="viewer",
            )

        assert isinstance(result, UserRead)
        assert result.email == "test@example.com"
        mock_user_repo.create.assert_called_once()

    async def test_register_user_admin_role(self, auth_service, mock_user_repo, mock_db):
        """Test registration with admin role."""
        mock_user_repo.create.return_value = MagicMock(
            id=uuid4(),
            email="admin@example.com",
            role="admin",
            is_active=True,
            password_hash=hash_password("AdminPass123!"),
        )

        result = await auth_service.register_user(
            email="admin@example.com",
            password="AdminPass123!",
            db=mock_db,
            role="admin",
        )

        assert result.role == UserRole.ADMIN

    async def test_register_user_invalid_email(self, auth_service, mock_db):
        """Test registration rejects invalid email format."""
        with pytest.raises(ValueError, match="Invalid email format"):
            await auth_service.register_user(
                email="invalid-email",
                password="TestPass123!",
                db=mock_db,
                role="viewer",
            )

    async def test_register_user_invalid_role(self, auth_service, mock_db):
        """Test registration rejects invalid role."""
        with pytest.raises(ValueError, match="Invalid role"):
            await auth_service.register_user(
                email="test@example.com",
                password="TestPass123!",
                db=mock_db,
                role="invalid_role",
            )

    async def test_register_user_duplicate_email(self, auth_service, mock_user_repo, mock_db):
        """Test registration fails when email already exists."""
        mock_user_repo.get_by_email.return_value = MagicMock(
            id=uuid4(), email="existing@example.com"
        )

        with pytest.raises(ValueError, match="already exists"):
            await auth_service.register_user(
                email="existing@example.com",
                password="TestPass123!",
                db=mock_db,
                role="viewer",
            )

    async def test_register_user_empty_password(self, auth_service, mock_user_repo, mock_db):
        """Test registration rejects empty password.

        Password validation requires non-empty passwords with digits and letters.
        """
        empty_password = ""
        with pytest.raises(ValueError, match="Password is required"):
            await auth_service.register_user(
                email="empty@example.com",
                password=empty_password,
                db=mock_db,
                role="viewer",
            )

    # --- login_user tests ---

    async def test_login_user_success(self, auth_service, mock_user_repo, mock_db):
        """Test successful login."""
        from datetime import datetime

        test_password = "TestPass123!"
        mock_user = MagicMock()
        mock_user.password_hash = hash_password(test_password)
        mock_user.id = uuid4()
        mock_user.email = "test@example.com"
        mock_user.role = UserRole.ADMIN
        mock_user.is_active = True
        mock_user.created_at = datetime.now()
        mock_user_repo.get_by_email_with_hash.return_value = mock_user

        result = await auth_service.login_user("test@example.com", test_password, mock_db)

        assert result is not None
        assert "access_token" in result
        assert result["token_type"] == "bearer"
        assert "user" in result
        assert result["user"].email == "test@example.com"
        assert hasattr(result["user"], "display_name")
        assert result["user"].display_name == "test"

    async def test_login_user_wrong_password(self, auth_service, mock_user_repo, mock_db):
        """Test login with wrong password returns None."""
        mock_user = MagicMock()
        mock_user.password_hash = hash_password("CorrectPassword")
        mock_user_repo.get_by_email_with_hash.return_value = mock_user

        result = await auth_service.login_user("test@example.com", "WrongPassword", db=mock_db)

        assert result is None

    async def test_login_user_not_found(self, auth_service, mock_user_repo, mock_db):
        """Test login with non-existent email returns None."""
        mock_user_repo.get_by_email_with_hash.return_value = None

        result = await auth_service.login_user("nonexistent@example.com", "AnyPassword", db=mock_db)

        assert result is None

    async def test_login_user_empty_password(self, auth_service, mock_user_repo, mock_db):
        """Test login with empty password."""
        mock_user = MagicMock()
        mock_user.password_hash = hash_password("ActualPassword")
        mock_user_repo.get_by_email_with_hash.return_value = mock_user

        result = await auth_service.login_user("test@example.com", "", db=mock_db)

        assert result is None

    # --- authenticate_user tests ---

    async def test_authenticate_user_success(self, auth_service, mock_user_repo, mock_db):
        """Test successful authentication returns user data."""
        test_password = "TestPass123!"
        mock_user = MagicMock()
        mock_user.password_hash = hash_password(test_password)
        mock_user.id = uuid4()
        mock_user.email = "auth@example.com"
        mock_user.role = UserRole.EDITOR
        mock_user.is_active = True
        mock_user_repo.get_by_email_with_hash.return_value = mock_user
        mock_user_repo.get_by_email.return_value = mock_user

        result = await auth_service.authenticate_user("auth@example.com", test_password, db=mock_db)

        assert result is not None
        assert isinstance(result, UserRead)
        assert result.email == "auth@example.com"

    async def test_authenticate_user_wrong_password(self, auth_service, mock_user_repo, mock_db):
        """Test authentication with wrong password returns None."""
        mock_user = MagicMock()
        mock_user.password_hash = hash_password("CorrectPassword")
        mock_user_repo.get_by_email_with_hash.return_value = mock_user

        result = await auth_service.authenticate_user("test@example.com", "WrongPassword", db=mock_db)

        assert result is None

    async def test_authenticate_user_not_found(self, auth_service, mock_user_repo, mock_db):
        """Test authentication with non-existent user returns None."""
        mock_user_repo.get_by_email_with_hash.return_value = None

        result = await auth_service.authenticate_user("nobody@example.com", "AnyPassword", db=mock_db)

        assert result is None

    # --- create_access_token tests ---

    async def test_create_access_token(self, auth_service):
        """Test access token creation."""
        user_id = uuid4()
        role = UserRole.ADMIN

        token = auth_service.create_access_token(user_id, role)

        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT format

    async def test_create_access_token_different_users(self, auth_service):
        """Test different users get different tokens."""
        token1 = auth_service.create_access_token(uuid4(), UserRole.ADMIN)
        token2 = auth_service.create_access_token(uuid4(), UserRole.VIEWER)

        assert token1 != token2

    # --- verify_token tests ---

    async def test_verify_token_valid(self, auth_service):
        """Test verifying a valid token."""
        user_id = uuid4()
        token = auth_service.create_access_token(user_id, UserRole.ADMIN)

        result = auth_service.verify_token(token)

        assert result is not None
        assert result["user_id"] == str(user_id)

    async def test_verify_token_invalid(self, auth_service):
        """Test verifying an invalid token returns None."""
        result = auth_service.verify_token("invalid.token.here")

        assert result is None

    async def test_verify_token_empty(self, auth_service):
        """Test verifying an empty token returns None."""
        result = auth_service.verify_token("")

        assert result is None

    async def test_verify_token_expired(self, auth_service):
        """Test that expired tokens are rejected and return None.

        Creates a token with negative expires_delta to simulate an already-expired token.
        The JWT library rejects expired tokens during decoding.
        """
        from datetime import timedelta

        from mkobi.core.security import create_access_token

        user_id = uuid4()
        # Create token that expired 1 hour ago
        expired_token = create_access_token(
            {"user_id": str(user_id), "email": "expired@example.com", "role": UserRole.VIEWER},
            expires_delta=timedelta(hours=-1),
        )

        result = auth_service.verify_token(expired_token)

        assert result is None

    # --- refresh_token tests ---

    async def test_refresh_token_success(self, auth_service):
        """Test successful token refresh."""
        user_id = uuid4()
        original_token = auth_service.create_access_token(user_id, UserRole.ADMIN)
        payload = auth_service.verify_token(original_token)

        result = await auth_service.refresh_token(
            user_id=payload["user_id"],
            email="test@example.com",
            role=UserRole.ADMIN,
        )

        assert "access_token" in result
        assert result["token_type"] == "bearer"

    async def test_refresh_token_new_token_different(self, auth_service):
        """Test refreshed token is different from original."""
        user_id = uuid4()
        original_token = auth_service.create_access_token(user_id, UserRole.ADMIN)
        payload = auth_service.verify_token(original_token)

        result = await auth_service.refresh_token(
            user_id=payload["user_id"],
            email="test@example.com",
            role=UserRole.ADMIN,
        )

        assert result["access_token"] != original_token

    # --- get_user_by_id tests ---

    async def test_get_user_by_id_found(self, auth_service, mock_user_repo, mock_db):
        """Test getting user by ID when user exists."""
        expected_user = MagicMock()
        expected_user.id = uuid4()
        expected_user.email = "found@example.com"
        expected_user.role = UserRole.ADMIN
        expected_user.password_hash = hash_password("password")
        expected_user.is_active = True
        mock_user_repo.get.return_value = expected_user

        result = await auth_service.get_user_by_id(expected_user.id, db=mock_db)

        assert result is not None
        assert isinstance(result, UserRead)
        assert result.id == expected_user.id

    async def test_get_user_by_id_not_found(self, auth_service, mock_user_repo, mock_db):
        """Test getting user by ID when user doesn't exist."""
        mock_user_repo.get.return_value = None

        result = await auth_service.get_user_by_id(uuid4(), db=mock_db)

        assert result is None

    # --- get_user_by_email tests ---

    async def test_get_user_by_email_found(self, auth_service, mock_user_repo, mock_db):
        """Test getting user by email when user exists."""
        expected_user = MagicMock()
        expected_user.id = uuid4()
        expected_user.email = "found@example.com"
        expected_user.role = UserRole.VIEWER
        expected_user.password_hash = hash_password("password")
        expected_user.is_active = True
        mock_user_repo.get_by_email.return_value = expected_user

        result = await auth_service.get_user_by_email("found@example.com", db=mock_db)

        assert result is not None
        assert isinstance(result, UserRead)
        assert result.email == "found@example.com"

    async def test_get_user_by_email_not_found(self, auth_service, mock_user_repo, mock_db):
        """Test getting user by email when user doesn't exist."""
        mock_user_repo.get_by_email.return_value = None

        result = await auth_service.get_user_by_email("nobody@example.com", db=mock_db)

        assert result is None

    # --- create_user tests ---

    async def test_create_user_success(self, auth_service, mock_user_repo, mock_db):
        """Test admin creates user successfully."""
        mock_user_repo.create.return_value = MagicMock(
            id=uuid4(), email="new@example.com", role=UserRole.VIEWER,
            is_active=True,
            password_hash=hash_password("ValidPass123"),
        )

        result = await auth_service.create_user(
            email="new@example.com",
            password="ValidPass123",
            role=UserRole.VIEWER,
            db=mock_db,
        )

        assert isinstance(result, UserRead)
        assert result.email == "new@example.com"

    # --- register_request tests ---

    async def test_register_request_success(self, auth_service, mock_reg_request_repo, mock_db):
        """Test successful registration request."""
        mock_reg_request_repo.get_by_email.return_value = None
        mock_reg_request_repo.create.return_value = MagicMock(
            id=uuid4(), email="request@example.com", status=MagicMock(value="pending")
        )

        result = await auth_service.register_request("request@example.com", db=mock_db, ip="127.0.0.1")

        assert "id" in result
        assert result["email"] == "request@example.com"

    async def test_register_request_invalid_email(self, auth_service, mock_db):
        """Test registration request rejects invalid email."""
        with pytest.raises(ValueError, match="Invalid email format"):
            await auth_service.register_request("invalid-email", db=mock_db, ip="127.0.0.1")

    async def test_register_request_duplicate(self, auth_service, mock_reg_request_repo, mock_db):
        """Test registration request fails for duplicate email (PENDING status)."""
        mock_request = MagicMock()
        mock_request.status = RegistrationStatus.PENDING
        mock_reg_request_repo.get_by_email.return_value = mock_request

        with pytest.raises(ValueError, match="Unable to process registration request"):
            await auth_service.register_request("duplicate@example.com", db=mock_db, ip="127.0.0.1")

    async def test_register_request_duplicate_rejected(self, auth_service, mock_reg_request_repo, mock_db):
        """Test registration request fails with rejected status message."""
        mock_request = MagicMock()
        mock_request.status = RegistrationStatus.REJECTED
        mock_reg_request_repo.get_by_email.return_value = mock_request

        with pytest.raises(ValueError, match="Unable to process registration request"):
            await auth_service.register_request("rejected@example.com", db=mock_db, ip="127.0.0.1")

    async def test_register_request_duplicate_approved(self, auth_service, mock_reg_request_repo, mock_db):
        """Test registration request fails with approved status message."""
        mock_request = MagicMock()
        mock_request.status = RegistrationStatus.APPROVED
        mock_reg_request_repo.get_by_email.return_value = mock_request

        with pytest.raises(ValueError, match="Unable to process registration request"):
            await auth_service.register_request("approved@example.com", db=mock_db, ip="127.0.0.1")

    async def test_register_request_blocked_domain(
        self, auth_service, mock_reg_request_repo, mock_db
    ):
        """Test registration request rejects blocked email domains."""
        mock_reg_request_repo.get_by_email.return_value = None

        with pytest.raises(
            ValueError, match="Unable to process registration request"
        ):
            await auth_service.register_request("user@tempmail.com", db=mock_db, ip="127.0.0.1")

    # --- reset_password_admin tests ---

    async def test_reset_password_admin_success(self, auth_service, mock_user_repo, mock_db):
        """Test successful admin password reset."""
        target_user_id = uuid4()
        admin_user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = target_user_id
        mock_user_repo.get_with_hash = AsyncMock(return_value=mock_user)
        mock_user_repo.update = AsyncMock()

        result = await auth_service.reset_password_admin(
            user_id=target_user_id,
            admin_user_id=admin_user_id,
            db=mock_db,
        )

        assert result is not None
        assert "retrieval_token" in result
        assert "user_id" in result
        assert result["user_id"] == str(target_user_id)
        assert "message" in result

        # Verify user_repo.update was called with correct parameters
        mock_user_repo.update.assert_called_once()
        call_args = mock_user_repo.update.call_args
        # First positional arg is user_id
        assert call_args[0][0] == target_user_id
        # Verify password_hash is in kwargs
        assert "password_hash" in call_args.kwargs
        # Verify force_password_change is True
        assert call_args.kwargs["force_password_change"] is True

        mock_db.commit.assert_called_once()

    async def test_reset_password_admin_db_commit_called(self, auth_service, mock_user_repo, mock_db):
        """Test db.commit() is called during reset."""
        target_user_id = uuid4()
        admin_user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = target_user_id
        mock_user_repo.get_with_hash = AsyncMock(return_value=mock_user)
        mock_user_repo.update = AsyncMock()

        await auth_service.reset_password_admin(
            user_id=target_user_id,
            admin_user_id=admin_user_id,
            db=mock_db,
        )

        mock_db.commit.assert_called_once()

    async def test_reset_password_admin_update_params(self, auth_service, mock_user_repo, mock_db):
        """Test user_repo.update called with correct parameters."""
        target_user_id = uuid4()
        admin_user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = target_user_id
        mock_user_repo.get_with_hash = AsyncMock(return_value=mock_user)
        mock_user_repo.update = AsyncMock()

        result = await auth_service.reset_password_admin(
            user_id=target_user_id,
            admin_user_id=admin_user_id,
            db=mock_db,
        )

        # Verify update was called with password_hash and force_password_change=True
        mock_user_repo.update.assert_called_once()
        call_args = mock_user_repo.update.call_args
        assert "password_hash" in call_args.kwargs
        assert call_args.kwargs["force_password_change"] is True
        # Verify retrieval_token is returned (UUID string)
        assert "retrieval_token" in result

    async def test_reset_password_admin_with_temp_password_store(
        self, mock_user_repo, mock_reg_request_repo, mock_db
    ):
        """Test that temp_password_store.store is called when provided."""
        from mkobi.core.temp_password_store import TempPasswordStore

        mock_temp_password_store = AsyncMock(spec=TempPasswordStore)
        auth_service = AuthService(
            mock_user_repo, mock_reg_request_repo, temp_password_store=mock_temp_password_store
        )

        target_user_id = uuid4()
        admin_user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = target_user_id
        mock_user_repo.get_with_hash = AsyncMock(return_value=mock_user)
        mock_user_repo.update = AsyncMock()

        result = await auth_service.reset_password_admin(
            user_id=target_user_id,
            admin_user_id=admin_user_id,
            db=mock_db,
        )

        assert result is not None
        assert "retrieval_token" in result
        # Verify store was called with the retrieval token
        mock_temp_password_store.store.assert_called_once()
        call_args = mock_temp_password_store.store.call_args
        assert call_args[0][0] == result["retrieval_token"]  # token passed as first arg

    async def test_reset_password_admin_self_guard(self, auth_service, mock_user_repo, mock_db):
        """Test self-reset guard raises ValueError."""
        same_id = uuid4()

        with pytest.raises(ValueError, match="Admin cannot reset own password"):
            await auth_service.reset_password_admin(
                user_id=same_id,
                admin_user_id=same_id,
                db=mock_db,
            )

    async def test_reset_password_admin_user_not_found(self, auth_service, mock_user_repo, mock_db):
        """Test returns None for non-existent user."""
        mock_user_repo.get_with_hash = AsyncMock(return_value=None)

        result = await auth_service.reset_password_admin(
            user_id=uuid4(),
            admin_user_id=uuid4(),
            db=mock_db,
        )

        assert result is None
        mock_user_repo.update.assert_not_called()
        mock_db.commit.assert_not_called()

    # --- _generate_temp_password tests ---

    async def test_generate_temp_password_length(self, auth_service):
        """Test generated password is exactly 16 characters for security."""
        password = auth_service._generate_temp_password()

        assert len(password) == 16

    async def test_generate_temp_password_has_letter_and_digit(self, auth_service):
        """Test generated password contains at least one letter and one digit."""
        password = auth_service._generate_temp_password()

        assert re.search(r"[a-zA-Z]", password) is not None
        assert re.search(r"\d", password) is not None

    async def test_generate_temp_password_alphanumeric_only(self, auth_service):
        """Test password only contains characters from a-zA-Z0-9."""
        password = auth_service._generate_temp_password()

        assert re.fullmatch(r"[a-zA-Z0-9]+", password) is not None

    async def test_generate_temp_password_different_each_time(self, auth_service):
        """Test multiple invocations produce different passwords."""
        passwords = [
            auth_service._generate_temp_password()
            for _ in range(100)
        ]

        # With 62 possible chars and 16 positions, we expect all to be unique
        unique_passwords = set(passwords)
        assert len(unique_passwords) > 90  # Allow some collision tolerance

    # --- approve_registration_request tests ---

    def _make_pending_request(self, email: str = "approve@example.com"):
        """Build a pending registration request double."""
        req = MagicMock()
        req.status = RegistrationStatus.PENDING
        req.email = email
        return req

    async def test_approve_registration_request_commit_precedes_store(
        self, mock_user_repo, mock_reg_request_repo
    ):
        """The commit must happen before the temporary password reaches the store.

        This is an ordering assertion about two collaborators: the session that
        records the commit and the store that records its write must be invoked
        in that order. It pins TOPO-006's fix.
        """
        order: list[str] = []

        mock_reg_request_repo.get_by_id = AsyncMock(return_value=self._make_pending_request())
        mock_reg_request_repo.update_status = AsyncMock()

        created = MagicMock(
            id=uuid4(),
            email="approve@example.com",
            role=UserRole.VIEWER,
            is_active=True,
            password_hash=hash_password("TempPass123!"),
        )
        mock_user_repo.get_by_email = AsyncMock(return_value=None)
        mock_user_repo.create = AsyncMock(return_value=created)
        mock_user_repo.update = AsyncMock()

        db = AsyncMock(spec=AsyncSession)

        async def _commit() -> None:
            order.append("commit")

        db.commit = AsyncMock(side_effect=_commit)

        store = AsyncMock()
        store.store = AsyncMock(side_effect=lambda *a, **k: order.append("store"))

        auth_service = AuthService(
            mock_user_repo, mock_reg_request_repo, temp_password_store=store
        )

        result = await auth_service.approve_registration_request(
            request_id=uuid4(), admin_user_id=uuid4(), db=db
        )

        assert result is not None
        # The credential must never be stored before a commit has made the user durable.
        assert order.index("store") > order.index("commit")
        assert order[-1] == "store"

    async def test_approve_registration_request_failed_commit_leaves_no_credential(
        self, mock_user_repo, mock_reg_request_repo
    ):
        """A failed commit must not leave a retrievable credential behind.

        The store is a durable, non-transactional write; if the commit that
        makes the user real fails, the store must never be called.
        """
        mock_reg_request_repo.get_by_id = AsyncMock(return_value=self._make_pending_request())
        mock_reg_request_repo.update_status = AsyncMock()

        mock_user_repo.get_by_email = AsyncMock(return_value=None)
        mock_user_repo.create = AsyncMock(
            return_value=MagicMock(
                id=uuid4(),
                email="approve@example.com",
                role=UserRole.VIEWER,
                is_active=True,
                password_hash=hash_password("TempPass123!"),
            )
        )
        mock_user_repo.update = AsyncMock()

        db = AsyncMock(spec=AsyncSession)
        # register_user commits the created user; the final commit (status +
        # flag) is the one whose failure must prevent the credential write.
        call_state = {"n": 0}

        async def _commit() -> None:
            call_state["n"] += 1
            if call_state["n"] >= 2:
                raise RuntimeError("commit failed")

        db.commit = AsyncMock(side_effect=_commit)

        store = AsyncMock()
        auth_service = AuthService(
            mock_user_repo, mock_reg_request_repo, temp_password_store=store
        )

        with pytest.raises(RuntimeError, match="commit failed"):
            await auth_service.approve_registration_request(
                request_id=uuid4(), admin_user_id=uuid4(), db=db
            )

        store.store.assert_not_called()

    async def test_approve_registration_request_store_failure_after_commit_keeps_user(
        self, mock_user_repo, mock_reg_request_repo
    ):
        """A store failure after a successful commit must not roll back the user.

        The store fails open by design, so the service must not treat its
        success as guaranteed, nor let its failure undo the committed user.
        """
        mock_reg_request_repo.get_by_id = AsyncMock(return_value=self._make_pending_request())
        mock_reg_request_repo.update_status = AsyncMock()

        mock_user_repo.get_by_email = AsyncMock(return_value=None)
        mock_user_repo.create = AsyncMock(
            return_value=MagicMock(
                id=uuid4(),
                email="approve@example.com",
                role=UserRole.VIEWER,
                is_active=True,
                password_hash=hash_password("TempPass123!"),
            )
        )
        mock_user_repo.update = AsyncMock()

        db = AsyncMock(spec=AsyncSession)
        db.commit = AsyncMock()

        # Mirrors TempPasswordStore.store's fail-open contract: log and return.
        store = AsyncMock()
        store.store = AsyncMock(return_value=None)

        auth_service = AuthService(
            mock_user_repo, mock_reg_request_repo, temp_password_store=store
        )

        result = await auth_service.approve_registration_request(
            request_id=uuid4(), admin_user_id=uuid4(), db=db
        )

        assert result is not None
        assert "user_id" in result
        assert "retrieval_token" in result
        mock_user_repo.create.assert_called_once()
        db.commit.assert_called()
        store.store.assert_called_once()

    async def test_approve_registration_request_nonexistent_returns_none(
        self, mock_user_repo, mock_reg_request_repo
    ):
        """A missing request returns None and performs no writes."""
        mock_reg_request_repo.get_by_id = AsyncMock(return_value=None)
        db = AsyncMock(spec=AsyncSession)
        store = AsyncMock()
        auth_service = AuthService(
            mock_user_repo, mock_reg_request_repo, temp_password_store=store
        )

        result = await auth_service.approve_registration_request(
            request_id=uuid4(), admin_user_id=uuid4(), db=db
        )

        assert result is None
        mock_user_repo.create.assert_not_called()
        db.commit.assert_not_called()
        store.store.assert_not_called()

    # --- interface conformance ---

    async def test_auth_service_implements_iauth_service(
        self, auth_service
    ):
        """AuthService must be a complete IAuthService implementation.

        A method added to the ABC but missed on the class is caught here.
        """
        from mkobi.interfaces.service_interfaces import IAuthService

        assert isinstance(auth_service, IAuthService)
        assert not getattr(auth_service, "__abstractmethods__", frozenset())

    # --- reset_password_admin ordering ---

    async def test_reset_password_admin_commit_precedes_store(
        self, mock_user_repo, mock_reg_request_repo
    ):
        """reset_password_admin must order commit before the Redis write too."""
        order: list[str] = []

        target_user_id = uuid4()
        mock_user = MagicMock()
        mock_user.id = target_user_id
        mock_user_repo.get_with_hash = AsyncMock(return_value=mock_user)

        async def _update(*_a, **_k):
            order.append("update")

        mock_user_repo.update = AsyncMock(side_effect=_update)

        db = AsyncMock(spec=AsyncSession)

        async def _commit() -> None:
            order.append("commit")

        db.commit = AsyncMock(side_effect=_commit)

        store = AsyncMock()
        store.store = AsyncMock(side_effect=lambda *a, **k: order.append("store"))

        auth_service = AuthService(
            mock_user_repo, mock_reg_request_repo, temp_password_store=store
        )

        result = await auth_service.reset_password_admin(
            user_id=target_user_id,
            admin_user_id=uuid4(),
            db=db,
        )

        assert result is not None
        assert order == ["update", "commit", "store"]


class TestApproveRegistrationRouteOrdering:
    """Route-level assertions for the corrected approval sequence."""

    @pytest.fixture
    def mock_user_repo(self):
        """Create a mock user repository."""
        mock = AsyncMock()
        mock.get_by_email.return_value = None
        return mock

    @pytest.fixture
    def mock_reg_request_repo(self):
        """Create a mock registration request repository."""
        return AsyncMock()

    async def _seed_request(self, db_session):
        """Persist a pending registration request and return its id."""
        from mkobi.db.repositories.registration_request_repo import (
            RegistrationRequestRepository,
        )

        repo = RegistrationRequestRepository()
        req = await repo.create(
            email=f"route_approve_{uuid4().hex[:8]}@example.com",
            ip="127.0.0.1",
            db=db_session,
        )
        await db_session.commit()
        return req.id

    async def test_failed_commit_returns_rfc7807_and_no_credential(
        self, async_client, async_db_session, test_user, mock_user_repo, mock_reg_request_repo
    ):
        """A commit failure yields the documented error and never stores a credential."""
        from mkobi.api.deps import (
            get_auth_service,
            get_registration_request_repository,
        )
        from mkobi.main import app

        request_id = await self._seed_request(async_db_session)

        mock_reg_request_repo.get_by_id = AsyncMock(
            return_value=MagicMock(
                status=RegistrationStatus.PENDING, email="route_approve@example.com"
            )
        )
        mock_reg_request_repo.update_status = AsyncMock()
        mock_user_repo.get_by_email = AsyncMock(return_value=None)
        mock_user_repo.create = AsyncMock(
            return_value=MagicMock(
                id=uuid4(),
                email="route_approve@example.com",
                role=UserRole.VIEWER,
                is_active=True,
                password_hash=hash_password("TempPass123!"),
            )
        )
        mock_user_repo.update = AsyncMock()

        store = AsyncMock()
        failing_service = AuthService(
            mock_user_repo, mock_reg_request_repo, temp_password_store=store
        )
        # register_user performs the first commit; the final commit (flag +
        # status) is the one forced to fail here.
        original_commit = async_db_session.commit
        commit_state = {"n": 0}

        async def _commit() -> None:
            commit_state["n"] += 1
            if commit_state["n"] >= 2:
                raise RuntimeError("commit failed")
            await original_commit()

        async_db_session.commit = _commit

        app.dependency_overrides[get_registration_request_repository] = (
            lambda: mock_reg_request_repo
        )
        app.dependency_overrides[get_auth_service] = lambda: failing_service

        try:
            response = await async_client.post(
                f"/admin/registration-requests/{request_id}/approve",
                headers={"Authorization": f"Bearer {test_user['token']}"},
            )
        finally:
            async_db_session.commit = original_commit

        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"
        store.store.assert_not_called()

    async def test_store_failure_after_commit_returns_success(
        self, async_client, async_db_session, test_user, mock_user_repo, mock_reg_request_repo
    ):
        """A fail-open store after a successful commit must not turn the endpoint into a 500."""
        from mkobi.api.deps import (
            get_auth_service,
            get_registration_request_repository,
        )
        from mkobi.main import app

        request_id = await self._seed_request(async_db_session)

        mock_reg_request_repo.get_by_id = AsyncMock(
            return_value=MagicMock(
                status=RegistrationStatus.PENDING, email="route_approve@example.com"
            )
        )
        mock_reg_request_repo.update_status = AsyncMock()
        mock_user_repo.get_by_email = AsyncMock(return_value=None)
        mock_user_repo.create = AsyncMock(
            return_value=MagicMock(
                id=uuid4(),
                email="route_approve@example.com",
                role=UserRole.VIEWER,
                is_active=True,
                password_hash=hash_password("TempPass123!"),
            )
        )
        mock_user_repo.update = AsyncMock()

        # Mirrors TempPasswordStore.store's fail-open contract.
        store = AsyncMock()
        store.store = AsyncMock(return_value=None)

        service = AuthService(
            mock_user_repo, mock_reg_request_repo, temp_password_store=store
        )

        app.dependency_overrides[get_registration_request_repository] = (
            lambda: mock_reg_request_repo
        )
        app.dependency_overrides[get_auth_service] = lambda: service

        response = await async_client.post(
            f"/admin/registration-requests/{request_id}/approve",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "Registration request approved"
        assert "user_id" in body
        assert "retrieval_token" in body
        store.store.assert_called_once()
