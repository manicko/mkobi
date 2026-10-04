"""Tests for layouts API."""

import pytest

from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def test_create_layout_duplicate_name_returns_400(
        self, async_db_session: AsyncSession, authenticated_client: AsyncClient, test_user: dict
    ) -> None:
        """Test that creating layout with duplicate name returns validation error."""
        # Create first layout
        repo = LayoutRepository()
        await repo.create(
            db=async_db_session,
            name="duplicate_test_layout",
            definition={"grid": []},
        )
        await async_db_session.flush()

        # Try to create another layout with same name
        response = await authenticated_client.post(
            "/layouts",
            json={"name": "duplicate_test_layout", "definition": {"grid": []}},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "already exists" in data["detail"].lower()
