"""Unit tests for UserService business logic.

These tests pin the transaction-ownership contract declared on ``IUserService``:
a write method commits exactly once on success and commits nothing when the
entity does not exist. A second commit is the regression this contract exists to
prevent, so the assertions check the exact count rather than "at least once".
No database is required — the session and repository are doubles.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from mkobi.core.security import hash_password
from mkobi.models.enums import UserRole
from mkobi.services.user_service import UserService


def _make_user(**overrides) -> MagicMock:
    """Build a repository/user double accepted by UserRead.model_validate."""
    user = MagicMock()
    user.id = overrides.get("id", uuid4())
    user.email = overrides.get("email", "user@example.com")
    user.role = overrides.get("role", UserRole.VIEWER)
    user.is_active = overrides.get("is_active", True)
    user.password_hash = overrides.get("password_hash", hash_password("TestPass123!"))
    return user


@pytest.mark.asyncio
class TestUserServiceCommitOwnership:
    """Commit-count contract for every UserService write method."""

    @pytest.fixture
    def mock_user_repo(self) -> AsyncMock:
        """Repository double with a permissive default surface."""
        repo = AsyncMock()
        repo.get_by_email.return_value = None
        repo.get.return_value = None
        repo.get_all.return_value = []
        return repo

    @pytest.fixture
    def user_service(self, mock_user_repo: AsyncMock) -> UserService:
        """UserService with an injected repository double."""
        return UserService(mock_user_repo)

    async def test_create_user_commits_exactly_once(
        self, user_service: UserService, mock_user_repo: AsyncMock, mock_db
    ) -> None:
        """create_user commits exactly once on the success path."""
        mock_user_repo.create.return_value = _make_user(email="new@example.com")

        result = await user_service.create_user(
            email="new@example.com",
            password="TestPass123!",
            role=UserRole.VIEWER,
            db=mock_db,
        )

        assert result.email == "new@example.com"
        assert mock_db.commit.await_count == 1

    async def test_update_user_role_commits_exactly_once(
        self, user_service: UserService, mock_user_repo: AsyncMock, mock_db
    ) -> None:
        """update_user_role commits exactly once when the user exists."""
        existing = _make_user(role=UserRole.VIEWER)
        mock_user_repo.get.return_value = existing
        mock_user_repo.update.return_value = _make_user(role=UserRole.EDITOR)

        result = await user_service.update_user_role(
            user_id=existing.id, role=UserRole.EDITOR, db=mock_db
        )

        assert result is not None
        assert result.role == UserRole.EDITOR
        assert mock_db.commit.await_count == 1

    async def test_update_user_role_not_found_does_not_commit(
        self, user_service: UserService, mock_user_repo: AsyncMock, mock_db
    ) -> None:
        """The user-not-found path returns None and commits nothing."""
        mock_user_repo.get.return_value = None

        result = await user_service.update_user_role(
            user_id=uuid4(), role=UserRole.EDITOR, db=mock_db
        )

        assert result is None
        assert mock_db.commit.not_awaited
        mock_user_repo.update.assert_not_awaited()

    async def test_update_user_active_status_commits_exactly_once(
        self, user_service: UserService, mock_user_repo: AsyncMock, mock_db
    ) -> None:
        """update_user_active_status commits exactly once when the user exists."""
        existing = _make_user(is_active=True)
        mock_user_repo.get.return_value = existing
        mock_user_repo.update.return_value = _make_user(is_active=False)

        result = await user_service.update_user_active_status(
            user_id=existing.id, is_active=False, db=mock_db
        )

        assert result is not None
        assert result.is_active is False
        assert mock_db.commit.await_count == 1

    async def test_update_user_active_status_not_found_does_not_commit(
        self, user_service: UserService, mock_user_repo: AsyncMock, mock_db
    ) -> None:
        """The user-not-found path returns None and commits nothing."""
        mock_user_repo.get.return_value = None

        result = await user_service.update_user_active_status(
            user_id=uuid4(), is_active=False, db=mock_db
        )

        assert result is None
        assert mock_db.commit.not_awaited
        mock_user_repo.update.assert_not_awaited()

    async def test_delete_user_commits_exactly_once(
        self, user_service: UserService, mock_user_repo: AsyncMock, mock_db
    ) -> None:
        """delete_user still commits exactly once — it must not gain a second one."""
        mock_user_repo.get.return_value = _make_user(role=UserRole.VIEWER)
        mock_user_repo.delete.return_value = True

        result = await user_service.delete_user(user_id=uuid4(), db=mock_db)

        assert result is True
        assert mock_db.commit.await_count == 1

    async def test_delete_user_not_found_does_not_commit(
        self, user_service: UserService, mock_user_repo: AsyncMock, mock_db
    ) -> None:
        """delete_user's not-found path returns False and commits nothing."""
        mock_user_repo.get.return_value = None

        result = await user_service.delete_user(user_id=uuid4(), db=mock_db)

        assert result is False
        assert mock_db.commit.not_awaited
