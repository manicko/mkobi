"""Tests for core/permissions.py module.

Tests for access control functions.
"""

from uuid import uuid4

import pytest

from mkobi.core.permissions import (
    AuthenticationError,
    check_dashboard_access,
    check_role,
    get_current_user,
)
from mkobi.db.session import get_db
from mkobi.models.enums import UserRole


class TestCheckRole:
    """Tests for check_role function with role hierarchy."""

    def test_admin_above_editor(self):
        """Admin has higher role than editor."""
        assert check_role(UserRole.ADMIN, UserRole.EDITOR) is True

    def test_editor_below_admin(self):
        """Editor does not have higher role than admin."""
        assert check_role(UserRole.EDITOR, UserRole.ADMIN) is False

    def test_same_role(self):
        """Same role comparison returns True."""
        assert check_role(UserRole.VIEWER, UserRole.VIEWER) is True
        assert check_role(UserRole.EDITOR, UserRole.EDITOR) is True
        assert check_role(UserRole.ADMIN, UserRole.ADMIN) is True

    def test_admin_above_viewer(self):
        """Admin has higher role than viewer."""
        assert check_role(UserRole.ADMIN, UserRole.VIEWER) is True

    def test_viewer_below_editor(self):
        """Viewer does not have higher role than editor."""
        assert check_role(UserRole.VIEWER, UserRole.EDITOR) is False

    def test_editor_above_viewer(self):
        """Editor has higher role than viewer."""
        assert check_role(UserRole.EDITOR, UserRole.VIEWER) is True

    def test_viewer_below_admin(self):
        """Viewer does not have higher role than admin."""
        assert check_role(UserRole.VIEWER, UserRole.ADMIN) is False


class TestCheckDashboardAccess:
    """Tests for check_dashboard_access function with real db session."""

    @pytest.mark.asyncio
    async def test_admin_bypass(self, async_db_session):
        """Admin gets access without explicit access record."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # Create admin user
        user_repo = UserRepository()
        admin_user = await user_repo.create(
            db=async_db_session,
            email="admin_bypass@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        # Create dashboard (no access record)
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Admin Bypass Test Dashboard",
        )
        await async_db_session.commit()

        # Admin should have access without explicit access record
        result = await check_dashboard_access(
            user_id=admin_user.id,
            dashboard_id=dashboard.id,
            required_permission="view",
            db=async_db_session,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_viewer_with_access(self, async_db_session):
        """Viewer with view permission gets access."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # Create viewer user
        user_repo = UserRepository()
        viewer_user = await user_repo.create(
            db=async_db_session,
            email="viewer_with_access@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Create dashboard
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Viewer Access Test Dashboard",
        )
        await async_db_session.commit()

        # Grant view access
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=viewer_user.id,
            dashboard_id=dashboard.id,
            permission="view",
        )
        await async_db_session.commit()

        # Viewer should have access
        result = await check_dashboard_access(
            user_id=viewer_user.id,
            dashboard_id=dashboard.id,
            required_permission="view",
            db=async_db_session,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_viewer_no_access(self, async_db_session):
        """Viewer without access record gets denied."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # Create viewer user
        user_repo = UserRepository()
        viewer_user = await user_repo.create(
            db=async_db_session,
            email="viewer_no_access@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Create dashboard (no access record for this user)
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"No Access Test Dashboard {uuid4().hex[:8]}",
        )
        await async_db_session.commit()

        # Viewer should not have access
        result = await check_dashboard_access(
            user_id=viewer_user.id,
            dashboard_id=dashboard.id,
            required_permission="view",
            db=async_db_session,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_editor_edit_access(self, async_db_session):
        """Editor with edit permission can edit."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # Create editor user
        user_repo = UserRepository()
        editor_user = await user_repo.create(
            db=async_db_session,
            email="editor_edit_access@example.com",
            password_hash=hash_password("EditorPass123!"),
            role=UserRole.EDITOR,
        )
        await async_db_session.commit()

        # Create dashboard
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Editor Edit Test Dashboard",
        )
        await async_db_session.commit()

        # Grant edit access
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=editor_user.id,
            dashboard_id=dashboard.id,
            permission="edit",
        )
        await async_db_session.commit()

        # Editor should have edit access
        result = await check_dashboard_access(
            user_id=editor_user.id,
            dashboard_id=dashboard.id,
            required_permission="edit",
            db=async_db_session,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_viewer_cannot_edit(self, async_db_session):
        """Viewer with view permission cannot edit."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # Create viewer user
        user_repo = UserRepository()
        viewer_user = await user_repo.create(
            db=async_db_session,
            email="viewer_cannot_edit@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Create dashboard
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Viewer Cannot Edit Test Dashboard",
        )
        await async_db_session.commit()

        # Grant view access only
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=viewer_user.id,
            dashboard_id=dashboard.id,
            permission="view",
        )
        await async_db_session.commit()

        # Viewer should not have edit access
        result = await check_dashboard_access(
            user_id=viewer_user.id,
            dashboard_id=dashboard.id,
            required_permission="edit",
            db=async_db_session,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_invalid_permission_raises(self, async_db_session):
        """Invalid permission string raises ValueError."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        # Create a user
        user_repo = UserRepository()
        user = await user_repo.create(
            db=async_db_session,
            email="invalid_perm@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Invalid permission should raise ValueError
        with pytest.raises(ValueError, match="Allowed values"):
            await check_dashboard_access(
                user_id=user.id,
                dashboard_id=user.id,  # Use any UUID
                required_permission="invalid",
                db=async_db_session,
            )


class TestCheckDashboardAccessPermissionVocabulary:
    """The narrowed permission type and the single permission ladder.

    ``check_dashboard_access`` now declares ``DashboardPermission`` and compares
    through ``PERMISSION_LEVELS``. Members are the supported spelling; the
    retired ``read``/``write`` aliases are refused by the vocabulary guard.
    """

    @pytest.mark.asyncio
    async def test_member_permission_grants_sufficient_access(
        self, async_db_session
    ) -> None:
        """An ``admin`` member satisfies a required ``view`` member."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import DashboardPermission

        user_repo = UserRepository()
        viewer = await user_repo.create(
            db=async_db_session,
            email=f"member_perm_{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"Member Perm Dashboard {uuid4().hex[:8]}",
        )
        await async_db_session.commit()

        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=viewer.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.ADMIN,
        )
        await async_db_session.commit()

        assert await check_dashboard_access(
            user_id=viewer.id,
            dashboard_id=dashboard.id,
            required_permission=DashboardPermission.VIEW,
            db=async_db_session,
        )

    @pytest.mark.asyncio
    async def test_ladder_refuses_insufficient_member(
        self, async_db_session
    ) -> None:
        """A ``view`` grant does not satisfy a required ``edit`` member."""
        from mkobi.core.security import hash_password
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.enums import DashboardPermission

        user_repo = UserRepository()
        viewer = await user_repo.create(
            db=async_db_session,
            email=f"ladder_perm_{uuid4().hex[:8]}@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"Ladder Perm Dashboard {uuid4().hex[:8]}",
        )
        await async_db_session.commit()

        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=viewer.id,
            dashboard_id=dashboard.id,
            permission=DashboardPermission.VIEW,
        )
        await async_db_session.commit()

        assert not await check_dashboard_access(
            user_id=viewer.id,
            dashboard_id=dashboard.id,
            required_permission=DashboardPermission.EDIT,
            db=async_db_session,
        )

    @pytest.mark.asyncio
    async def test_retired_alias_is_refused(self, async_db_session) -> None:
        """The ``read`` alias is not in the vocabulary and raises ``ValueError``."""
        with pytest.raises(ValueError, match="Allowed values"):
            await check_dashboard_access(
                user_id=uuid4(),
                dashboard_id=uuid4(),
                required_permission="read",  # type: ignore[arg-type]
                db=async_db_session,
            )


class TestGetCurrentUser:
    """Tests for get_current_user function with real db session."""

    @pytest.mark.asyncio
    async def test_valid_token(self, async_db_session):
        """Valid token returns UserRead."""
        from mkobi.core.security import create_access_token, hash_password
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.models.user import UserRead

        # Create user
        user_repo = UserRepository()
        user = await user_repo.create(
            db=async_db_session,
            email="valid_token@example.com",
            password_hash=hash_password("Pass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Create token
        token = create_access_token({"user_id": str(user.id), "email": user.email})

        # Get current user
        result = await get_current_user(token=token, db=async_db_session)

        assert isinstance(result, UserRead)
        assert result.email == user.email
        assert result.role == UserRole.VIEWER

    @pytest.mark.asyncio
    async def test_invalid_token(self, async_db_session):
        """Invalid token raises AuthenticationError."""
        with pytest.raises(AuthenticationError, match="Invalid token"):
            await get_current_user(token="invalid.token.here", db=async_db_session)

    @pytest.mark.asyncio
    async def test_user_not_found(self, async_db_session):
        """Valid token but deleted user raises AuthenticationError."""
        from uuid import uuid4

        # Create token for non-existent user
        fake_user_id = uuid4()
        from mkobi.core.security import create_access_token

        token = create_access_token({"user_id": str(fake_user_id), "email": "ghost@example.com"})

        # Should raise AuthenticationError
        with pytest.raises(AuthenticationError, match="User not found"):
            await get_current_user(token=token, db=async_db_session)

    @pytest.mark.asyncio
    async def test_empty_token(self, async_db_session):
        """Empty token raises AuthenticationError."""
        with pytest.raises(AuthenticationError, match="Invalid token"):
            await get_current_user(token="", db=async_db_session)


class TestGetDb:
    """Tests for get_db generator function."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """get_db() yields an AsyncSession."""
        from sqlalchemy.ext.asyncio import AsyncSession

        # Get the session from the generator
        gen = get_db()
        session = await gen.__anext__()

        assert isinstance(session, AsyncSession)

        # Close the session after test
        await gen.aclose()

    @pytest.mark.asyncio
    async def test_get_db_closes_session(self):
        """get_db() closes session after generator exits."""
        closed = False

        async def mock_close():
            nonlocal closed
            closed = True

        gen = get_db()
        session = await gen.__anext__()

        # Patch the close method
        session.close = mock_close

        # Exhaust the generator
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

        assert closed is True