"""Tests for api/deps.py FastAPI dependencies.

Tests for authentication, authorization, and dependency injection functions.
"""

import pytest
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    get_auth_service,
    get_dashboard_service,
    get_data_service,
    get_filter_service,
    get_graph_service,
    get_layout_service,
)
from mkobi.core.security import create_access_token, hash_password
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.dashboard_filter_repo import DashboardFilterRepository
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.db.repositories.registration_request_repo import RegistrationRequestRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import UserRole


class TestGetDbDependency:
    """Tests for get_db_dependency session lifecycle."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self, async_db_session) -> None:
        """Test that get_db_dependency yields an AsyncSession."""
        from mkobi.api.deps import get_db_dependency

        # Use the dependency directly
        gen = get_db_dependency()
        session = await gen.__anext__()

        assert isinstance(session, AsyncSession)

        # Close the generator properly
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

    @pytest.mark.asyncio
    async def test_get_db_session_usable(self, async_client, test_user) -> None:
        """Test that yielded session can execute queries."""
        # Hit an authenticated endpoint to verify session works
        response = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {test_user['token']}"})
        assert response.status_code == status.HTTP_200_OK


class TestGetCurrentUserDependency:
    """Tests for get_current_user_dependency with token authentication."""

    async def test_valid_token_returns_user(self, async_client, test_user: dict) -> None:
        """Test that valid token returns correct user data."""
        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == test_user["email"]
        assert data["role"] == test_user["role"]

    async def test_invalid_token_returns_401(self, async_client) -> None:
        """Test that invalid token returns 401."""
        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_missing_token_returns_401(self, async_client) -> None:
        """Test that missing token returns 401."""
        response = await async_client.get("/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_wrong_auth_scheme_returns_401(self, async_client) -> None:
        """Test that non-Bearer auth scheme returns 401."""
        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": "Basic dGVzdDp0ZXN0"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRoleRequirements:
    """Tests for role requirement dependencies."""

    async def test_viewer_can_access_viewer_endpoint(self, async_client, async_db_session) -> None:
        """Test that viewer role can access viewer-level endpoints."""
        # Create a viewer user
        repo = UserRepository()
        viewer_user = await repo.create(
            db=async_db_session,
            email="viewer_role_test@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()
        token = create_access_token({"user_id": str(viewer_user.id), "email": viewer_user.email})

        # Access /auth/me which requires viewer role
        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_editor_can_access_viewer_endpoint(self, async_client, async_db_session) -> None:
        """Test that editor role can access viewer-level endpoints."""
        repo = UserRepository()
        editor_user = await repo.create(
            db=async_db_session,
            email="editor_role_test@example.com",
            password_hash=hash_password("EditorPass123!"),
            role=UserRole.EDITOR,
        )
        await async_db_session.commit()
        token = create_access_token({"user_id": str(editor_user.id), "email": editor_user.email})

        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_admin_can_access_viewer_endpoint(self, async_client, test_user) -> None:
        """Test that admin role can access viewer-level endpoints."""
        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_viewer_cannot_access_admin_endpoint(
        self, async_client, async_db_session
    ) -> None:
        """Test that viewer role cannot access admin endpoints."""
        # Create a viewer user
        repo = UserRepository()
        viewer_user = await repo.create(
            db=async_db_session,
            email="viewer_admin_blocked_test@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()
        token = create_access_token({"user_id": str(viewer_user.id), "email": viewer_user.email})

        # Viewer should get 403 when accessing admin-only endpoint
        response = await async_client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestDashboardAccessDependencies:
    """Tests for dashboard access dependencies."""

    async def test_read_access_with_permission(
        self, async_client, async_db_session, test_user
    ) -> None:
        """Test that user with view permission can read dashboard."""
        # Create a dashboard
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Read Access Test Dashboard",
        )
        await async_db_session.commit()

        # Create viewer user with access
        user_repo = UserRepository()
        viewer_user = await user_repo.create(
            db=async_db_session,
            email="viewer_read_test@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
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
        token = create_access_token({"user_id": str(viewer_user.id), "email": viewer_user.email})

        # Access dashboard
        response = await async_client.get(
            f"/dashboards/{dashboard.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_read_access_without_permission(
        self, async_client, async_db_session, test_user
    ) -> None:
        """Test that user without access gets 403."""
        # Create a dashboard
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="No Access Test Dashboard",
        )
        await async_db_session.commit()

        # Create viewer user without access
        user_repo = UserRepository()
        viewer_user = await user_repo.create(
            db=async_db_session,
            email="viewer_no_access_test@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()
        token = create_access_token({"user_id": str(viewer_user.id), "email": viewer_user.email})

        # Try to access dashboard
        response = await async_client.get(
            f"/dashboards/{dashboard.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_write_access_denied_for_editor_with_edit_permission(
        self, async_client, async_db_session, test_user
    ) -> None:
        """Test that editor with edit permission can update dashboard.

        Editor with edit permission now CAN update the dashboard after
        resource-level access control was implemented (TASK_012).
        """
        # Create dashboard
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Write Access Test Dashboard",
        )
        await async_db_session.commit()

        # Create editor user with edit access
        user_repo = UserRepository()
        editor_user = await user_repo.create(
            db=async_db_session,
            email="editor_write_test@example.com",
            password_hash=hash_password("EditorPass123!"),
            role=UserRole.EDITOR,
        )
        await async_db_session.commit()

        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=editor_user.id,
            dashboard_id=dashboard.id,
            permission="edit",
        )
        await async_db_session.commit()
        token = create_access_token({"user_id": str(editor_user.id), "email": editor_user.email})

        # Editor with edit permission can now update the dashboard
        response = await async_client.put(
            f"/dashboards/{dashboard.id}",
            json={"description": "Updated description"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_write_access_with_view_only(
        self, async_client, async_db_session, test_user
    ) -> None:
        """Test that user with view permission gets 403 for write."""
        # Create dashboard
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="View Only Write Test Dashboard",
        )
        await async_db_session.commit()

        # Create viewer user with view-only access
        user_repo = UserRepository()
        viewer_user = await user_repo.create(
            db=async_db_session,
            email="viewer_view_only_test@example.com",
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=viewer_user.id,
            dashboard_id=dashboard.id,
            permission="view",
        )
        await async_db_session.commit()
        token = create_access_token({"user_id": str(viewer_user.id), "email": viewer_user.email})

        # Try to update dashboard (PUT endpoint requires admin role)
        response = await async_client.put(
            f"/dashboards/{dashboard.id}",
            json={"description": "Should fail"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_admin_access_with_admin_permission(
        self, async_client, async_db_session, test_user
    ) -> None:
        """Test that editor with admin dashboard permission can delete.

        After resource-level access control (TASK_012), editors with admin
        permission on a dashboard can delete it (no global ADMIN role required).
        """
        # Create dashboard
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Admin Access Test Dashboard",
        )
        await async_db_session.commit()

        # Create editor user with admin access (but not global admin role)
        user_repo = UserRepository()
        editor_user = await user_repo.create(
            db=async_db_session,
            email="editor_admin_test@example.com",
            password_hash=hash_password("EditorPass123!"),
            role=UserRole.EDITOR,
        )
        await async_db_session.commit()

        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=editor_user.id,
            dashboard_id=dashboard.id,
            permission="admin",
        )
        await async_db_session.commit()
        token = create_access_token({"user_id": str(editor_user.id), "email": editor_user.email})

        # Delete endpoint now checks dashboard admin permission
        response = await async_client.delete(
            f"/dashboards/{dashboard.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Editor with admin permission on dashboard should succeed
        assert response.status_code == status.HTTP_204_NO_CONTENT

    async def test_admin_access_with_admin_role(
        self, async_client, async_db_session, test_user
    ) -> None:
        """Test that user with ADMIN role can delete any dashboard."""
        # Create dashboard (created_by is the owner)
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Admin Role Delete Test Dashboard",
            created_by=test_user["id"],
        )
        await async_db_session.commit()

        # test_user has ADMIN role, so delete should succeed
        response = await async_client.delete(
            f"/dashboards/{dashboard.id}",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    async def test_admin_access_with_edit_permission(
        self, async_client, async_db_session, test_user
    ) -> None:
        """Test that user with edit permission gets 403 for admin actions."""
        # Create dashboard
        dashboard_repo = DashboardRepository()
        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name="Edit Only Admin Test Dashboard",
        )
        await async_db_session.commit()

        # Create editor user with edit-only access
        user_repo = UserRepository()
        editor_user = await user_repo.create(
            db=async_db_session,
            email="editor_edit_only_test@example.com",
            password_hash=hash_password("EditorPass123!"),
            role=UserRole.EDITOR,
        )
        await async_db_session.commit()

        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=editor_user.id,
            dashboard_id=dashboard.id,
            permission="edit",
        )
        await async_db_session.commit()
        token = create_access_token({"user_id": str(editor_user.id), "email": editor_user.email})

        # Try to delete dashboard (admin-only)
        response = await async_client.delete(
            f"/dashboards/{dashboard.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestDIFactories:
    """Tests for dependency injection factory functions."""

    def test_get_auth_service_returns_auth_service(self) -> None:
        """Test that get_auth_service returns AuthService instance."""
        from mkobi.services.auth_service import AuthService

        service = get_auth_service()
        assert isinstance(service, AuthService)

    def test_get_dashboard_service_returns_dashboard_service(self) -> None:
        """Test that get_dashboard_service returns DashboardService instance."""
        from mkobi.services.dashboard_service import DashboardService

        service = get_dashboard_service()
        assert isinstance(service, DashboardService)

    def test_get_graph_service_returns_graph_service(self) -> None:
        """Test that get_graph_service returns GraphService instance."""
        from mkobi.services.graph_service import GraphService

        service = get_graph_service()
        assert isinstance(service, GraphService)

    def test_get_data_service_returns_data_service(self) -> None:
        """Test that get_data_service returns DataService instance."""
        from mkobi.services.data_service import DataService

        service = get_data_service()
        assert isinstance(service, DataService)

    def test_get_filter_service_returns_filter_service(self) -> None:
        """Test that get_filter_service returns FilterService instance."""
        from mkobi.services.filter_service import FilterService

        service = get_filter_service()
        assert isinstance(service, FilterService)

    def test_get_layout_service_returns_layout_service(self) -> None:
        """Test that get_layout_service returns LayoutService instance."""
        from mkobi.services.layout_service import LayoutService

        service = get_layout_service()
        assert isinstance(service, LayoutService)


class TestRepositoryProviderAnnotations:
    """Runtime resolution of the narrowed repository provider annotations.

    ``mypy`` never evaluates a runtime annotation, but FastAPI resolves every
    ``Depends`` parameter annotation at import time. The four route modules
    carry no ``from __future__ import annotations``, so a ``TYPE_CHECKING``-only
    import there is a startup ``NameError`` that no static gate reports. This
    test performs the exact resolution FastAPI performs and builds the app.
    """

    def test_narrowed_dependency_annotations_resolve_at_runtime(self) -> None:
        """Import the changed route modules, resolve their annotations, build the app."""
        import importlib
        import typing

        from mkobi.app import create_app

        # 1. Importing each changed module must succeed. A TYPE_CHECKING-only
        #    import in a module without the future import would raise NameError here.
        admin = importlib.import_module("mkobi.api.routes.admin")
        dashboards_filters = importlib.import_module(
            "mkobi.api.routes.dashboards_filters"
        )
        dashboards_graphs = importlib.import_module(
            "mkobi.api.routes.dashboards_graphs"
        )
        data = importlib.import_module("mkobi.api.routes.data")

        # 2. Resolve one narrowed repository parameter per module, exactly as
        #    FastAPI does while building the dependency graph.
        expected = {
            admin.get_registration_requests_admin_endpoint: (
                "repo",
                RegistrationRequestRepository,
            ),
            dashboards_filters.get_dashboard_filters_endpoint: (
                "dashboard_filter_repo",
                DashboardFilterRepository,
            ),
            dashboards_graphs.get_dashboard_graphs_endpoint: (
                "graph_repo",
                GraphRepository,
            ),
            data.get_aggregated_data_endpoint: ("graph_repo", GraphRepository),
        }
        for handler, (param, concrete) in expected.items():
            hints = typing.get_type_hints(handler)
            assert hints[param] is concrete

        # 3. Build the application so the full dependency graph is constructed;
        #    an unresolvable forward reference raises at startup here.
        create_app()


class TestRepositoryFactories:
    """Tests for repository DI factory functions."""

    def test_get_user_repository_returns_user_repository(self) -> None:
        """Test that get_user_repository returns UserRepository instance."""
        from mkobi.api.deps import get_user_repository
        from mkobi.db.repositories.user_repo import UserRepository

        repo = get_user_repository()
        assert isinstance(repo, UserRepository)

    def test_get_dashboard_repository_returns_dashboard_repository(self) -> None:
        """Test that get_dashboard_repository returns DashboardRepository instance."""
        from mkobi.api.deps import get_dashboard_repository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        repo = get_dashboard_repository()
        assert isinstance(repo, DashboardRepository)

    def test_get_access_repository_returns_access_repository(self) -> None:
        """Test that get_access_repository returns AccessRepository instance."""
        from mkobi.api.deps import get_access_repository
        from mkobi.db.repositories.access_repo import AccessRepository

        repo = get_access_repository()
        assert isinstance(repo, AccessRepository)


class TestExportSurface:
    """Contract for the public export surface of ``api/deps.py``.

    ``__all__`` is the module's public API contract. Unlike a type annotation,
    it is runtime-observable: a symbol added to the module and left out of
    ``__all__`` silently disappears from the export surface, and no lint, mypy
    or import gate reports the omission. This test derives the module's public
    names by inspection so it fails the moment a public symbol is defined
    without being exported -- the one defect in this module that no gate catches.
    """

    def test_all_matches_public_module_surface(self) -> None:
        """Every public defined symbol is exported; ``__all__`` has no duplicates."""
        import inspect
        import types

        import mkobi.api.deps as deps

        exported = list(deps.__all__)

        # 1. ``__all__`` must be duplicate-free -- the export contract is a set.
        duplicates = sorted({name for name in exported if exported.count(name) > 1})
        assert duplicates == [], f"duplicate entries in __all__: {duplicates}"

        # 2. Alphabetised-within-groups is a convention, not the contract, so we
        #    only require that every name in ``__all__`` is actually defined.
        undefined = sorted(name for name in exported if not hasattr(deps, name))
        assert undefined == [], f"__all__ references undefined names: {undefined}"

        # 3. Derive the public callables the module defines itself. Imported
        #    names (``Any``, ``Depends``, ``AsyncSession``, ...) live in other
        #    modules and are excluded by the ``__module__`` check. Symbols with
        #    a leading underscore are explicitly private.
        public_defined: set[str] = set()
        for name, obj in vars(deps).items():
            if name.startswith("_"):
                continue
            if getattr(obj, "__module__", None) != deps.__name__:
                continue
            if inspect.isfunction(obj) or inspect.iscoroutinefunction(obj):
                public_defined.add(name)
            elif isinstance(obj, types.GeneratorType):
                public_defined.add(name)

        # The four ``Annotated`` convenience aliases are public values, not
        # functions, and are defined in this module by assignment.
        for name in ("CurrentUser", "AdminUser", "EditorUser", "ViewerUser"):
            assert name in vars(deps), f"expected alias {name!r} to be defined"
            public_defined.add(name)

        # ``security = HTTPBearer()`` is a module-internal singleton, not a
        # FastAPI dependency or an exported callable.
        known_internal = {"security"}

        unexported = sorted(public_defined - set(exported) - known_internal)
        assert unexported == [], (
            "public symbols defined in deps.py are missing from __all__: "
            f"{unexported}"
        )