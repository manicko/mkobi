"""Tests for layouts API."""

import uuid

import pytest

from fastapi import status
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models import layout as layout_model
from mkobi.db.repositories.layout_repo import LayoutRepository
from mkobi.models.enums import ErrorCode, UserRole


@pytest.mark.asyncio
class TestLayoutsAPI:
    """Test cases for layouts API endpoints."""

    async def test_create_layout_admin_required(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient
    ) -> None:
        """Test that creating layout requires admin role."""
        # Create viewer user
        from mkobi.db.repositories.user_repo import UserRepository
        user_repo = UserRepository()
        user = await user_repo.create(
            db=async_db_session,
            email="viewer_layout@example.com",
            password_hash="hash",
            role="viewer",
        )
        await async_db_session.flush()

        # Login as viewer
        from mkobi.core.security import create_access_token
        token = create_access_token({"user_id": str(user.id), "email": user.email})
        viewer_client = authenticated_client
        viewer_client.headers["Authorization"] = f"Bearer {token}"

        response = await viewer_client.post(
            "/layouts",
            json={"name": "test_layout", "definition": {"grid": []}},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_create_layout_admin_success(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test creating layout as admin (success)."""
        response = await authenticated_client.post(
            "/layouts",
            json={"name": "admin_layout", "definition": {"grid": []}},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "admin_layout"

    async def test_get_layouts_list(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test getting list of layouts."""
        # Create test layout
        repo = LayoutRepository()
        await repo.create(
            db=async_db_session,
            name="list_test_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        response = await authenticated_client.get("/layouts")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_layout_by_id(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test getting layout by ID."""
        repo = LayoutRepository()
        layout = await repo.create(
            db=async_db_session,
            name="detail_test_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        response = await authenticated_client.get(f"/layouts/{layout.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(layout.id)
        assert data["name"] == "detail_test_layout"

    async def test_update_layout_admin_required(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient
    ) -> None:
        """Test that updating layout requires admin role."""
        # Create viewer user and layout
        from mkobi.db.repositories.user_repo import UserRepository
        user_repo = UserRepository()
        user = await user_repo.create(
            db=async_db_session,
            email="viewer_layout2@example.com",
            password_hash="hash",
            role="viewer",
        )
        await async_db_session.flush()

        repo = LayoutRepository()
        layout = await repo.create(
            db=async_db_session,
            name="update_test_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        # Login as viewer
        from mkobi.core.security import create_access_token
        token = create_access_token({"user_id": str(user.id), "email": user.email})
        viewer_client = authenticated_client
        viewer_client.headers["Authorization"] = f"Bearer {token}"

        response = await viewer_client.put(
            f"/layouts/{layout.id}",
            json={"name": "hacked_layout"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_update_layout_admin_success(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test updating layout as admin (success)."""
        repo = LayoutRepository()
        layout = await repo.create(
            db=async_db_session,
            name="update_success_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        response = await authenticated_client.put(
            f"/layouts/{layout.id}",
            json={"name": "updated_layout_name"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "updated_layout_name"

    async def test_delete_layout_admin_required(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient
    ) -> None:
        """Test that deleting layout requires admin role."""
        # Create viewer user and layout
        from mkobi.db.repositories.user_repo import UserRepository
        user_repo = UserRepository()
        user = await user_repo.create(
            db=async_db_session,
            email="viewer_layout3@example.com",
            password_hash="hash",
            role="viewer",
        )
        await async_db_session.flush()

        repo = LayoutRepository()
        layout = await repo.create(
            db=async_db_session,
            name="delete_test_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        # Login as viewer
        from mkobi.core.security import create_access_token
        token = create_access_token({"user_id": str(user.id), "email": user.email})
        viewer_client = authenticated_client
        viewer_client.headers["Authorization"] = f"Bearer {token}"

        response = await viewer_client.delete(f"/layouts/{layout.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_delete_layout_admin_success(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test deleting layout as admin (success)."""
        repo = LayoutRepository()
        layout = await repo.create(
            db=async_db_session,
            name="delete_success_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        response = await authenticated_client.delete(f"/layouts/{layout.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    async def test_get_layout_requires_dashboard_access(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that getting layout by ID requires dashboard access."""
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # Create a viewer user
        user_repo = UserRepository()
        viewer = await user_repo.create(
            db=async_db_session,
            email="layout_viewer@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        await async_db_session.flush()

        # Create a dashboard with a layout
        layout_repo = LayoutRepository()
        layout = await layout_repo.create(
            db=async_db_session,
            name="dashboard_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Protected Dashboard",
        )
        dashboard.layout_id = layout.id  # Associate layout with dashboard
        await async_db_session.flush()

        # Login as viewer (no access granted)
        from mkobi.core.security import create_access_token
        token = create_access_token({"user_id": str(viewer.id), "email": viewer.email})
        viewer_client = authenticated_client
        viewer_client.headers["Authorization"] = f"Bearer {token}"

        # Viewer should not have access to layout tied to a dashboard they don't have access to
        response = await viewer_client.get(f"/layouts/{layout.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        json_response = response.json()
        assert "access" in json_response["detail"].lower()

    async def test_get_layout_orphaned_returns_404(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that orphaned layout (no dashboard) returns 404 for non-admin."""
        from mkobi.db.repositories.user_repo import UserRepository

        # Create a viewer user
        user_repo = UserRepository()
        viewer = await user_repo.create(
            db=async_db_session,
            email="layout_viewer_orphan@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        await async_db_session.flush()

        # Create a layout without associating it to any dashboard
        layout_repo = LayoutRepository()
        layout = await layout_repo.create(
            db=async_db_session,
            name="orphaned_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        # Login as viewer
        from mkobi.core.security import create_access_token
        token = create_access_token({"user_id": str(viewer.id), "email": viewer.email})
        viewer_client = authenticated_client
        viewer_client.headers["Authorization"] = f"Bearer {token}"

        # Viewer should get 404 for orphaned layout (to prevent enumeration)
        response = await viewer_client.get(f"/layouts/{layout.id}")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_layout_with_dashboard_access(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that user with dashboard read access can get the layout."""
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.user_repo import UserRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        # Create a viewer user
        user_repo = UserRepository()
        viewer = await user_repo.create(
            db=async_db_session,
            email="layout_viewer_with_access@example.com",
            password_hash="hash",
            role=UserRole.VIEWER,
        )
        await async_db_session.flush()

        # Create a dashboard with a layout
        layout_repo = LayoutRepository()
        layout = await layout_repo.create(
            db=async_db_session,
            name="accessible_dashboard_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Accessible Dashboard",
        )
        dashboard.layout_id = layout.id
        await async_db_session.flush()

        # Grant view access to the viewer
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=viewer.id,
            dashboard_id=dashboard.id,
            permission="view",
        )
        await async_db_session.flush()

        # Login as viewer
        from mkobi.core.security import create_access_token
        token = create_access_token({"user_id": str(viewer.id), "email": viewer.email})
        viewer_client = authenticated_client
        viewer_client.headers["Authorization"] = f"Bearer {token}"

        # Viewer should have access to layout tied to a dashboard they have access to
        response = await viewer_client.get(f"/layouts/{layout.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(layout.id)

    async def test_get_layout_admin_can_access_any(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that admin can access any layout including orphaned ones."""
        # Create an orphaned layout
        layout_repo = LayoutRepository()
        layout = await layout_repo.create(
            db=async_db_session,
            name="orphaned_for_admin_test",
            definition={"grid": []},
        )
        await async_db_session.flush()

        # Admin should be able to access orphaned layout
        response = await authenticated_client.get(f"/layouts/{layout.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == str(layout.id)

    # --- Validation error tests ---

    async def test_create_layout_missing_name_returns_422(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that creating layout without name returns validation error 422."""
        response = await authenticated_client.post(
            "/layouts",
            json={"definition": {"grid": []}},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        # RFC 7807 Problem Details envelope.
        for member in ("type", "title", "status", "detail", "code"):
            assert member in data
        assert data["code"] == ErrorCode.VALIDATION_ERROR
        assert data["status"] == status.HTTP_422_UNPROCESSABLE_ENTITY
        # Field-level validation errors live in the top-level 'errors' array.
        errors = data["errors"]
        assert isinstance(errors, list)
        # Find the error for the 'name' field
        name_errors = [e for e in errors if "name" in e.get("loc", [])]
        assert len(name_errors) > 0, "Expected validation error for 'name' field"

    async def test_create_layout_missing_definition_returns_422(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that creating layout without definition returns validation error 422."""
        response = await authenticated_client.post(
            "/layouts",
            json={"name": "test_layout_no_def"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        # RFC 7807 Problem Details envelope.
        for member in ("type", "title", "status", "detail", "code"):
            assert member in data
        assert data["code"] == ErrorCode.VALIDATION_ERROR
        assert data["status"] == status.HTTP_422_UNPROCESSABLE_ENTITY
        # Field-level validation errors live in the top-level 'errors' array.
        errors = data["errors"]
        assert isinstance(errors, list)
        # Find the error for the 'definition' field
        definition_errors = [e for e in errors if "definition" in e.get("loc", [])]
        assert len(definition_errors) > 0, "Expected validation error for 'definition' field"

    async def test_create_layout_duplicate_name_returns_409(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """A duplicate layout name answers 409, not 500 or 422.

        The unique index on ``layouts.name`` is the detector: the service no
        longer pre-checks, so the conflict always arrives as a flush-time
        ``IntegrityError`` and the route maps it to ``DUPLICATE_RESOURCE``.
        """
        # Create first layout on the shared session.
        repo = LayoutRepository()
        await repo.create(
            db=async_db_session,
            name="duplicate_test_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        # Try to create another layout with same name.
        response = await authenticated_client.post(
            "/layouts",
            json={"name": "duplicate_test_layout", "definition": {"grid": []}},
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        # RFC 7807 Problem Details envelope.
        for member in ("type", "title", "status", "detail", "code"):
            assert member in data
        assert data["code"] == ErrorCode.DUPLICATE_RESOURCE
        assert data["status"] == status.HTTP_409_CONFLICT
        assert data["details"] == {"name": "duplicate_test_layout"}

    async def test_update_layout_rename_onto_existing_name_returns_409(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Renaming a layout onto an existing name answers 409, not 500 or 422."""
        repo = LayoutRepository()
        await repo.create(
            db=async_db_session,
            name="rename_target_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        layout = await repo.create(
            db=async_db_session,
            name="rename_source_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()
        layout_id = layout.id

        response = await authenticated_client.put(
            f"/layouts/{layout_id}",
            json={"name": "rename_target_layout"},
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        for member in ("type", "title", "status", "detail", "code"):
            assert member in data
        assert data["code"] == ErrorCode.DUPLICATE_RESOURCE
        assert data["status"] == status.HTTP_409_CONFLICT
        assert data["details"] == {"name": "rename_target_layout"}

    async def test_create_layout_duplicate_name_race_returns_409(
        self,
        async_db_session: AsyncSession,
        async_session_maker,
        authenticated_client: AsyncClient,
        test_user: dict,
    ) -> None:
        """The loser of a create race answers 409, never 500.

        Two real sessions exercise the sequential/loser ordering: one session
        commits a layout, then the HTTP request runs in a second session and
        must observe the unique-index conflict as 409 rather than a 500. The
        ordering is fixed by the test -- no coroutine is raced.
        """
        name = f"race_layout_{uuid.uuid4().hex[:8]}"

        repo = LayoutRepository()
        try:
            # Winner: a genuinely separate connection commits the row.
            async with async_session_maker() as winner_session:
                await repo.create(
                    db=winner_session,
                    name=name,
                    definition={"grid": []},
                )
                await winner_session.commit()

            # Loser: the request session now creates the same name.
            response = await authenticated_client.post(
                "/layouts",
                json={"name": name, "definition": {"grid": []}},
            )
            assert response.status_code == status.HTTP_409_CONFLICT
            assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR
            assert response.status_code != status.HTTP_422_UNPROCESSABLE_CONTENT
            assert response.json()["code"] == ErrorCode.DUPLICATE_RESOURCE
        finally:
            # A production commit is durable; the fixture teardown cannot undo
            # it, so the winner's row must be deleted through its own session.
            async with async_session_maker() as cleanup_session:
                await cleanup_session.execute(
                    delete(layout_model.Layout).where(layout_model.Layout.name == name)
                )
                await cleanup_session.commit()

