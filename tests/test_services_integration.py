"""Integration tests for all 8 service classes with real database session.

Tests use the async_db_session fixture from conftest.py and real repositories
without mocking. Every service method call explicitly passes db=async_db_session.
"""

import pytest
from uuid import uuid4

from mkobi.core.security import hash_password
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.db.repositories.filter_repo import FilterRepository
from mkobi.db.repositories.layout_repo import LayoutRepository
from mkobi.db.repositories.processing_config_repo import ProcessingConfigRepository
from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository
from mkobi.db.repositories.aggregated_data_repo import AggregatedDataRepository
from mkobi.services.auth_service import AuthService
from mkobi.services.dashboard_service import DashboardService
from mkobi.services.graph_service import GraphService
from mkobi.services.filter_service import FilterService
from mkobi.services.layout_service import LayoutService
from mkobi.services.processing_config_service import ProcessingConfigService
from mkobi.services.processing_log_service import ProcessingLogService
from mkobi.models.graph import GraphCreate
from mkobi.models.enums import UserRole, GraphType
from mkobi.models.layout import LayoutUpdate
from mkobi.models.filters import FilterUpdate


# ========== AuthService Integration Tests ==========

@pytest.mark.asyncio
class TestAuthServiceIntegration:
    """Integration tests for AuthService with real database."""

    @pytest.fixture
    def auth_service(self):
        """Create AuthService with real repositories."""
        from mkobi.db.repositories.registration_request_repo import RegistrationRequestRepository
        user_repo = UserRepository()
        reg_request_repo = RegistrationRequestRepository()
        return AuthService(user_repo, reg_request_repo)

    async def test_register_user_with_db(self, auth_service, async_db_session):
        """Test user registration with real database."""
        unique_email = f"new_user_{uuid4().hex[:8]}@example.com"
        result = await auth_service.register_user(
            email=unique_email,
            password="TestPass123!",
            role="viewer",
            db=async_db_session,
        )
        assert result is not None
        assert result.email == unique_email
        assert result.role == UserRole.VIEWER

    async def test_register_user_invalid_email_raises(self, auth_service, async_db_session):
        """Test registration with invalid email raises ValueError."""
        with pytest.raises(ValueError, match="Invalid email format"):
            await auth_service.register_user(
                email="invalid-email",
                password="TestPass123!",
                role="viewer",
                db=async_db_session,
            )

    async def test_register_user_duplicate_email_raises(self, auth_service, async_db_session):
        """Test registration with duplicate email raises ValueError."""
        unique_email = f"dup_user_{uuid4().hex[:8]}@example.com"
        # First registration
        await auth_service.register_user(
            email=unique_email,
            password="TestPass123!",
            role="viewer",
            db=async_db_session,
        )
        # Duplicate should raise
        with pytest.raises(ValueError, match="already exists"):
            await auth_service.register_user(
                email=unique_email,
                password="TestPass456!",
                role="admin",
                db=async_db_session,
            )

    async def test_login_user_with_db(self, auth_service, async_db_session):
        """Test login with real database."""
        unique_email = f"login_user_{uuid4().hex[:8]}@example.com"
        password = "TestPass123!"
        # Register user first
        await auth_service.register_user(
            email=unique_email,
            password=password,
            role="viewer",
            db=async_db_session,
        )
        # Login
        result = await auth_service.login_user(
            email=unique_email,
            password=password,
            db=async_db_session,
        )
        assert result is not None
        assert "access_token" in result
        assert result["token_type"] == "bearer"

    async def test_login_user_wrong_password(self, auth_service, async_db_session):
        """Test login with wrong password returns None."""
        unique_email = f"wrong_pass_{uuid4().hex[:8]}@example.com"
        await auth_service.register_user(
            email=unique_email,
            password="CorrectPass123",
            role="viewer",
            db=async_db_session,
        )
        result = await auth_service.login_user(
            email=unique_email,
            password="WrongPass456",
            db=async_db_session,
        )
        assert result is None

    async def test_get_user_by_id_with_db(self, auth_service, async_db_session):
        """Test getting user by ID."""
        unique_email = f"get_by_id_{uuid4().hex[:8]}@example.com"
        user = await auth_service.register_user(
            email=unique_email,
            password="TestPass123!",
            role="viewer",
            db=async_db_session,
        )
        result = await auth_service.get_user_by_id(user.id, db=async_db_session)
        assert result is not None
        assert result.id == user.id
        assert result.email == unique_email

    async def test_get_user_by_email_with_db(self, auth_service, async_db_session):
        """Test getting user by email."""
        unique_email = f"get_by_email_{uuid4().hex[:8]}@example.com"
        await auth_service.register_user(
            email=unique_email,
            password="TestPass123!",
            role="viewer",
            db=async_db_session,
        )
        result = await auth_service.get_user_by_email(unique_email, db=async_db_session)
        assert result is not None
        assert result.email == unique_email


# ========== DashboardService Integration Tests ==========

@pytest.mark.asyncio
class TestDashboardServiceIntegration:
    """Integration tests for DashboardService with real database."""

    @pytest.fixture
    def dashboard_service(self):
        """Create DashboardService with real repositories."""
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        return DashboardService(dashboard_repo, access_repo)

    @pytest.fixture
    async def owner_id(self, async_db_session):
        """Create and return a valid owner user ID."""
        from mkobi.core.security import hash_password
        unique_email = f"owner_{uuid4().hex[:8]}@example.com"
        user = await UserRepository().create(
            db=async_db_session,
            email=unique_email,
            password_hash=hash_password("TestPass123!"),
            role="admin",
        )
        await async_db_session.commit()
        return user.id

    @pytest.fixture
    async def dashboard(self, dashboard_service, async_db_session, owner_id):
        """Create and return a dashboard for testing."""
        unique_name = f"Test Dashboard {uuid4().hex[:8]}"
        result = await dashboard_service.create_dashboard(
            name=unique_name,
            config={"graph_types": ["bar", "line"]},
            owner_id=owner_id,
            db=async_db_session,
        )
        return result

    async def test_create_dashboard_with_db(self, dashboard_service, async_db_session, owner_id):
        """Test dashboard creation with real database."""
        result = await dashboard_service.create_dashboard(
            name="New Dashboard",
            config={"graph_types": ["bar"]},
            owner_id=owner_id,
            description="Test description",
            db=async_db_session,
        )
        assert result is not None
        assert result.name == "New Dashboard"
        assert result.description == "Test description"

    async def test_get_dashboard_with_db(self, dashboard_service, async_db_session, dashboard, owner_id):
        """Test getting dashboard by ID."""
        result = await dashboard_service.get_dashboard(
            dashboard_id=dashboard.id,
            user_id=owner_id,
            user_role=UserRole.ADMIN,
            db=async_db_session,
        )
        assert result is not None
        assert result.id == dashboard.id
        # dashboard name now uses unique suffix
        assert result.name.startswith("Test Dashboard")

    async def test_list_dashboards_with_db(self, dashboard_service, async_db_session, owner_id):
        """Test listing dashboards."""
        # Create multiple dashboards
        await dashboard_service.create_dashboard(
            name="Dashboard 1",
            config={"graph_types": ["bar"]},
            owner_id=owner_id,
            db=async_db_session,
        )
        await dashboard_service.create_dashboard(
            name="Dashboard 2",
            config={"graph_types": ["line"]},
            owner_id=owner_id,
            db=async_db_session,
        )
        results = await dashboard_service.get_user_dashboards(
            user_id=owner_id,
            user_role=UserRole.ADMIN,
            db=async_db_session,
        )
        assert len(results) >= 2

    async def test_update_dashboard_with_db(self, dashboard_service, async_db_session, dashboard):
        """Test updating dashboard."""
        unique_name = f"Updated Dashboard {uuid4().hex[:8]}"
        result = await dashboard_service.update_dashboard(
            dashboard_id=dashboard.id,
            update_data={"name": unique_name},
            db=async_db_session,
        )
        assert result is not None
        assert result.name == unique_name

    async def test_delete_dashboard_with_db(self, dashboard_service, async_db_session, owner_id):
        """Test deleting dashboard."""
        dashboard = await dashboard_service.create_dashboard(
            name="To Delete",
            config={"graph_types": ["bar"]},
            owner_id=owner_id,
            db=async_db_session,
        )
        result = await dashboard_service.delete_dashboard(
            dashboard_id=dashboard.id,
            db=async_db_session,
        )
        assert result is True
        # Verify it's gone
        fetched = await dashboard_service.get_dashboard(
            dashboard_id=dashboard.id,
            user_id=owner_id,
            user_role=UserRole.ADMIN,
            db=async_db_session,
        )
        assert fetched is None


# ========== GraphService Integration Tests ==========

@pytest.mark.asyncio
class TestGraphServiceIntegration:
    """Integration tests for GraphService with real database."""

    @pytest.fixture
    def graph_service(self):
        """Create GraphService with real repository."""
        return GraphService(GraphRepository())

    @pytest.fixture
    def dashboard_service(self):
        """Create DashboardService with real repositories."""
        return DashboardService(DashboardRepository(), AccessRepository())

    @pytest.fixture
    async def dashboard_id(self, async_db_session):
        """Create and return a valid dashboard ID."""
        from mkobi.core.security import hash_password
        user_repo = UserRepository()
        unique_email = f"owner_{uuid4().hex[:8]}@example.com"
        user = await user_repo.create(
            db=async_db_session,
            email=unique_email,
            password_hash=hash_password("TestPass123!"),
            role="admin",
        )
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        dashboard_service = DashboardService(dashboard_repo, access_repo)
        dashboard = await dashboard_service.create_dashboard(
            name=f"Test Dashboard {uuid4().hex[:8]}",
            config={"graph_types": ["bar"]},
            owner_id=user.id,
            db=async_db_session,
        )
        await async_db_session.commit()
        return dashboard.id

    @pytest.fixture
    async def graph(self, graph_service, async_db_session, dashboard_id):
        """Create and return a graph for testing."""
        data = GraphCreate(
            name="Test Graph",
            type="bar",
            dashboard_id=dashboard_id,
            config={},
            dimensions=["dim1"],
            metrics=["metric1"],
        )
        return await graph_service.create(data, db=async_db_session)

    async def test_create_graph_with_db(self, graph_service, async_db_session, dashboard_id):
        """Test graph creation with real database."""
        data = GraphCreate(
            name="New Graph",
            type="bar",
            dashboard_id=dashboard_id,
            config={"title": "test config"},
            dimensions=["dim1", "dim2"],
            metrics=["metric1"],
        )
        result = await graph_service.create(data, db=async_db_session)
        assert result is not None
        assert result.name == "New Graph"
        assert result.type == GraphType.BAR

    async def test_get_graph_with_db(self, graph_service, async_db_session, graph):
        """Test getting graph by ID."""
        result = await graph_service.get(graph.id, db=async_db_session)
        assert result is not None
        assert result.id == graph.id
        assert result.name == "Test Graph"

    async def test_update_graph_with_db(self, graph_service, async_db_session, graph):
        """Test updating graph."""
        from mkobi.models.graph import GraphUpdate
        result = await graph_service.update(
            graph.id,
            GraphUpdate(name="Updated Graph", type=None, config=None, dimensions=None, metrics=None),
            db=async_db_session,
        )
        assert result is not None
        assert result.name == "Updated Graph"

    async def test_delete_graph_with_db(self, graph_service, async_db_session, dashboard_id):
        """Test deleting graph."""
        data = GraphCreate(
            name="To Delete Graph",
            type="bar",
            dashboard_id=dashboard_id,
            config={},
            dimensions=["dim1"],
            metrics=["metric1"],
        )
        graph = await graph_service.create(data, db=async_db_session)
        result = await graph_service.delete(graph.id, db=async_db_session)
        assert result is True

    async def test_list_by_dashboard_with_db(self, graph_service, async_db_session, dashboard_id):
        """Test listing graphs by dashboard."""
        # Create multiple graphs
        await graph_service.create(
            GraphCreate(
                name="Graph 1",
                type="bar",
                dashboard_id=dashboard_id,
                config={},
                dimensions=[],
                metrics=[],
            ),
            db=async_db_session,
        )
        await graph_service.create(
            GraphCreate(
                name="Graph 2",
                type="line",
                dashboard_id=dashboard_id,
                config={},
                dimensions=[],
                metrics=[],
            ),
            db=async_db_session,
        )
        results = await graph_service.list_by_dashboard(dashboard_id, db=async_db_session)
        assert len(results) == 2


# ========== FilterService Integration Tests ==========

@pytest.mark.asyncio
class TestFilterServiceIntegration:
    """Integration tests for FilterService with real database."""

    @pytest.fixture
    def filter_service(self):
        """Create FilterService with real repository."""
        return FilterService(FilterRepository())

    @pytest.fixture
    async def test_filter(self, filter_service, async_db_session):
        """Create and return a filter for testing."""
        return await filter_service.create_filter(
            name="Test Filter",
            type_="select",
            config={"field": "category"},
            db=async_db_session,
        )

    async def test_create_filter_with_db(self, filter_service, async_db_session):
        """Test filter creation."""
        result = await filter_service.create_filter(
            name="New Filter",
            type_="select",
            config={"field": "status"},
            db=async_db_session,
        )
        assert result is not None
        assert result.name == "New Filter"

    async def test_create_filter_invalid_type(self, filter_service, async_db_session):
        """Test filter creation with invalid type raises."""
        with pytest.raises(ValueError, match="Invalid filter type"):
            await filter_service.create_filter(
                name="Bad Filter",
                type_="invalid_type",
                config={"field": "status"},
                db=async_db_session,
            )

    async def test_get_filter_with_db(self, filter_service, async_db_session, test_filter):
        """Test getting filter by ID."""
        result = await filter_service.get_filter_by_id(test_filter.id, db=async_db_session)
        assert result is not None
        assert result.id == test_filter.id

    async def test_update_filter_with_db(self, filter_service, async_db_session, test_filter):
        """Test updating filter."""
        unique_name = f"Updated Filter {uuid4().hex[:8]}"
        result = await filter_service.update_filter(
            test_filter.id,
            FilterUpdate(name=unique_name),
            db=async_db_session,
        )
        assert result is not None
        assert result.name.startswith("Updated Filter")

    async def test_delete_filter_with_db(self, filter_service, async_db_session):
        """Test deleting filter."""
        new_filter = await filter_service.create_filter(
            name="To Delete Filter",
            type_="select",
            config={"field": "test"},
            db=async_db_session,
        )
        result = await filter_service.delete_filter(new_filter.id, db=async_db_session)
        assert result is True


# ========== LayoutService Integration Tests ==========

@pytest.mark.asyncio
class TestLayoutServiceIntegration:
    """Integration tests for LayoutService with real database."""

    @pytest.fixture
    def layout_service(self):
        """Create LayoutService with real repository."""
        return LayoutService(LayoutRepository())

    @pytest.fixture
    async def layout(self, layout_service, async_db_session):
        """Create and return a layout for testing."""
        return await layout_service.create_layout(
            name=f"Test Layout {uuid4().hex[:8]}",
            definition={"test": "definition"},
            db=async_db_session,
        )

    async def test_create_layout_with_db(self, layout_service, async_db_session):
        """Test layout creation."""
        result = await layout_service.create_layout(
            name=f"New Layout {uuid4().hex[:8]}",
            definition={"grid": [[1, 2], [3, 4]]},
            db=async_db_session,
        )
        assert result is not None
        assert result.name.startswith("New Layout")

    async def test_create_layout_duplicate_name(self, layout_service, async_db_session):
        """Test layout creation with duplicate name raises."""
        unique_name = f"Duplicate Layout {uuid4().hex[:8]}"
        await layout_service.create_layout(
            name=unique_name,
            definition={"test": "def"},
            db=async_db_session,
        )
        with pytest.raises(ValueError, match="already exists"):
            await layout_service.create_layout(
                name=unique_name,
                definition={"test": "def2"},
                db=async_db_session,
            )

    async def test_get_layout_with_db(self, layout_service, async_db_session, layout):
        """Test getting layout by ID."""
        result = await layout_service.get_layout(layout.id, db=async_db_session)
        assert result is not None
        assert result.id == layout.id

    async def test_update_layout_with_db(self, layout_service, async_db_session, layout):
        """Test updating layout."""
        result = await layout_service.update_layout(
            layout.id,
            LayoutUpdate(name=f"Updated Layout {uuid4().hex[:8]}"),
            db=async_db_session,
        )
        assert result is not None
        assert result.name.startswith("Updated Layout")

    async def test_delete_layout_with_db(self, layout_service, async_db_session):
        """Test deleting layout."""
        new_layout = await layout_service.create_layout(
            name=f"To Delete Layout {uuid4().hex[:8]}",
            definition={"test": "def"},
            db=async_db_session,
        )
        result = await layout_service.delete_layout(new_layout.id, db=async_db_session)
        assert result is True


# ========== ProcessingConfigService Integration Tests ==========

@pytest.mark.asyncio
class TestProcessingConfigServiceIntegration:
    """Integration tests for ProcessingConfigService with real database."""

    @pytest.fixture
    def config_service(self):
        """Create ProcessingConfigService with real repository."""
        return ProcessingConfigService(ProcessingConfigRepository())

    @pytest.fixture
    def dashboard_service(self):
        """Create DashboardService with real repositories."""
        return DashboardService(DashboardRepository(), AccessRepository())

    @pytest.fixture
    async def dashboard_id(self, async_db_session):
        """Create and return a valid dashboard ID."""
        from mkobi.core.security import hash_password
        user_repo = UserRepository()
        unique_email = f"owner_{uuid4().hex[:8]}@example.com"
        user = await user_repo.create(
            db=async_db_session,
            email=unique_email,
            password_hash=hash_password("TestPass123!"),
            role="admin",
        )
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        dashboard_service = DashboardService(dashboard_repo, access_repo)
        dashboard = await dashboard_service.create_dashboard(
            name=f"Config Test Dashboard {uuid4().hex[:8]}",
            config={"graph_types": ["bar"]},
            owner_id=user.id,
            db=async_db_session,
        )
        await async_db_session.commit()
        return dashboard.id

    @pytest.fixture
    def valid_settings(self):
        """Return valid processing settings as the strict boundary model."""
        from mkobi.models.types import ProcessingSettingsModel

        return ProcessingSettingsModel(separator=",", encoding="UTF-8")

    async def test_create_config_with_db(self, config_service, async_db_session, dashboard_id, valid_settings):
        """Test processing config creation."""
        result = await config_service.create_processing_config(
            dashboard_id=dashboard_id,
            settings=valid_settings,
            db=async_db_session,
        )
        assert result is not None
        assert result.dashboard_id == dashboard_id

    async def test_create_config_invalid_settings(self, config_service, async_db_session, dashboard_id):
        """Test config creation with empty settings raises."""
        from mkobi.models.types import ProcessingSettingsModel

        # An empty model should raise ValueError at the service boundary.
        with pytest.raises(ValueError, match="Settings cannot be empty"):
            await config_service.create_processing_config(
                dashboard_id=dashboard_id,
                settings=ProcessingSettingsModel(),
                db=async_db_session,
            )

    async def test_create_config_non_model_settings(self, config_service, async_db_session, dashboard_id):
        """Test config creation with a non-model settings value raises."""
        with pytest.raises(ValueError, match="Settings must be a ProcessingSettingsModel"):
            await config_service.create_processing_config(
                dashboard_id=dashboard_id,
                settings="not a model",  # type: ignore[arg-type]
                db=async_db_session,
            )

    async def test_create_config_invalid_separator_type(self, async_db_session, dashboard_id):
        """A non-string separator is rejected by the boundary model."""
        from mkobi.models.types import ProcessingSettingsModel
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProcessingSettingsModel.model_validate({"separator": 123})

    async def test_create_config_invalid_decimal_separator_type(self, async_db_session, dashboard_id):
        """A non-string decimal_separator is rejected by the boundary model."""
        from mkobi.models.types import ProcessingSettingsModel
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProcessingSettingsModel.model_validate({"decimal_separator": ["comma"]})

    async def test_create_config_invalid_column_types_type(self, async_db_session, dashboard_id):
        """A non-dict column_types is rejected by the boundary model."""
        from mkobi.models.types import ProcessingSettingsModel
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProcessingSettingsModel.model_validate({"column_types": "not_a_dict"})

    async def test_create_config_invalid_date_format_type(self, async_db_session, dashboard_id):
        """A non-string date_format is rejected by the boundary model."""
        from mkobi.models.types import ProcessingSettingsModel
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ProcessingSettingsModel.model_validate({"date_format": 2024})

    async def test_create_config_valid_type_settings(self, config_service, async_db_session, dashboard_id):
        """Test config creation with valid typed settings passes validation."""
        from mkobi.models.types import ProcessingSettingsModel

        valid_settings = ProcessingSettingsModel(
            separator=",",
            decimal_separator=".",
            column_types={"col1": "str", "col2": "int"},
            date_format="%Y-%m-%d",
        )
        result = await config_service.create_processing_config(
            dashboard_id=dashboard_id,
            settings=valid_settings,
            db=async_db_session,
        )
        assert result is not None
        assert result.dashboard_id == dashboard_id

    async def test_create_config_missing_fields_no_type_validation(self, config_service, async_db_session, dashboard_id):
        """Test that missing optional fields are not type-validated (pass validation)."""
        from mkobi.models.types import ProcessingSettingsModel

        result = await config_service.create_processing_config(
            dashboard_id=dashboard_id,
            settings=ProcessingSettingsModel(encoding="UTF-8"),
            db=async_db_session,
        )
        assert result is not None

    async def test_get_config_with_db(self, config_service, async_db_session, dashboard_id, valid_settings):
        """Test getting config by dashboard ID."""
        await config_service.create_processing_config(
            dashboard_id=dashboard_id,
            settings=valid_settings,
            db=async_db_session,
        )
        result = await config_service.get_processing_config_by_dashboard(
            dashboard_id, db=async_db_session
        )
        assert result is not None
        assert result.dashboard_id == dashboard_id

    async def test_update_config_with_db(self, config_service, async_db_session, dashboard_id, valid_settings):
        """Test updating processing config."""
        from mkobi.models.types import ProcessingSettingsModel

        await config_service.create_processing_config(
            dashboard_id=dashboard_id,
            settings=valid_settings,
            db=async_db_session,
        )
        updated_settings = ProcessingSettingsModel(separator=";", encoding="UTF-8")
        result = await config_service.update_processing_config(
            dashboard_id=dashboard_id,
            settings=updated_settings,
            db=async_db_session,
        )
        assert result is not None

    async def test_delete_config_with_db(self, config_service, async_db_session, dashboard_id, valid_settings):
        """Test deleting processing config."""
        await config_service.create_processing_config(
            dashboard_id=dashboard_id,
            settings=valid_settings,
            db=async_db_session,
        )
        result = await config_service.delete_processing_config(
            dashboard_id, db=async_db_session
        )
        assert result is True


# ========== ProcessingLogService Integration Tests ==========

@pytest.mark.asyncio
class TestProcessingLogServiceIntegration:
    """Integration tests for ProcessingLogService with real database."""

    @pytest.fixture
    def log_service(self):
        """Create ProcessingLogService with real repository."""
        return ProcessingLogService(ProcessingLogRepository())

    @pytest.fixture
    def dashboard_service(self):
        """Create DashboardService with real repositories."""
        dashboard_repo = DashboardRepository()
        access_repo = AccessRepository()
        return DashboardService(dashboard_repo, access_repo)

    @pytest.fixture
    async def owner_id(self, async_db_session):
        """Create and return a valid owner user ID."""
        unique_email = f"owner_{uuid4().hex[:8]}@example.com"
        user = await UserRepository().create(
            db=async_db_session,
            email=unique_email,
            password_hash=hash_password("TestPass123!"),
            role="admin",
        )
        await async_db_session.commit()
        return user.id

    @pytest.fixture
    async def dashboard_id(self, dashboard_service, async_db_session, owner_id):
        """Create and return a valid dashboard ID."""
        unique_name = f"Test Dashboard {uuid4().hex[:8]}"
        dashboard = await dashboard_service.create_dashboard(
            name=unique_name,
            config={"graph_types": ["bar"]},
            owner_id=owner_id,
            db=async_db_session,
        )
        return dashboard.id

    async def test_create_log_with_db(self, log_service, async_db_session, dashboard_id):
        """Test processing log creation."""
        result = await log_service.create_processing_log(
            dashboard_id=dashboard_id,
            status="started",
            message="Processing started",
            db=async_db_session,
        )
        assert result is not None
        assert result.status.value == "started"

    async def test_get_log_with_db(self, log_service, async_db_session, dashboard_id):
        """Test getting processing log."""
        await log_service.create_processing_log(
            dashboard_id=dashboard_id,
            status="started",
            message="Test log",
            db=async_db_session,
        )
        result = await log_service.get_processing_logs_by_dashboard(
            dashboard_id, db=async_db_session
        )
        assert len(result) == 1
        assert result[0].dashboard_id == dashboard_id

    async def test_update_log_status_with_db(self, log_service, async_db_session, dashboard_id):
        """Test updating log status."""
        log = await log_service.create_processing_log(
            dashboard_id=dashboard_id,
            status="started",
            message="Starting",
            db=async_db_session,
        )
        # Follow proper state transitions: started -> uploaded -> processing -> completed
        await log_service.update_processing_log(
            log_id=log.id,
            status="uploaded",
            message="File uploaded",
            finished_at=None,
            db=async_db_session,
        )
        await log_service.update_processing_log(
            log_id=log.id,
            status="processing",
            message="Processing",
            finished_at=None,
            db=async_db_session,
        )
        result = await log_service.update_processing_log(
            log_id=log.id,
            status="completed",
            message="Completed",
            finished_at=None,
            db=async_db_session,
        )
        assert result is not None
        assert result.status.value == "completed"


# ========== DataService Integration Tests ==========

@pytest.mark.asyncio
class TestDataServiceIntegration:
    """Integration tests for DataService with real database."""

    @pytest.fixture
    def data_service(self):
        """Create DataService with real repositories."""
        from mkobi.services.data_service import DataService
        return DataService(
            agg_repo=AggregatedDataRepository(),
            log_repo=ProcessingLogRepository(),
            graph_repo=GraphRepository(),
        )

    async def test_get_processing_status_missing_task(self, data_service, async_db_session):
        """Test getting processing status for non-existent task."""
        with pytest.raises(ValueError, match="not found"):
            await data_service.get_processing_status(
                task_id=uuid4(),
                user_id=uuid4(),
                db=async_db_session,
            )

    async def test_get_aggregated_data_empty(self, data_service, async_db_session):
        """Test getting aggregated data for non-existent graph."""
        result = await data_service.get_aggregated_data(
            dashboard_id=uuid4(),
            graph_id=uuid4(),
            db=async_db_session,
        )
        assert result == []

    async def test_get_available_metrics_empty(self, data_service, async_db_session):
        """Test getting available metrics for non-existent dashboard."""
        result = await data_service.get_available_metrics(
            dashboard_id=uuid4(),
            db=async_db_session,
        )
        assert result == []

    async def test_get_available_dimensions_empty(self, data_service, async_db_session):
        """Test getting available dimensions for non-existent dashboard."""
        result = await data_service.get_available_dimensions(
            dashboard_id=uuid4(),
            db=async_db_session,
        )
        assert result == []


# ========== Registration Approval Flow Integration Tests ==========

@pytest.mark.asyncio
class TestRegistrationApprovalFlow:
    """Integration tests for registration approval flow via admin API."""

    @pytest.fixture
    async def registration_request_repo(self):
        """Create registration request repository."""
        from mkobi.db.repositories.registration_request_repo import RegistrationRequestRepository
        return RegistrationRequestRepository()

    async def test_approve_registration_creates_user_with_temp_password(
        self,
        async_client,
        auth_headers,
        async_db_session,
        registration_request_repo,
    ):
        """Verify approving registration creates user with temp password."""
        unique_email = f"approve_{uuid4().hex[:8]}@example.com"

        # Create registration request via public endpoint
        create_response = await async_client.post(
            "/auth/register-request",
            json={"email": unique_email},
        )
        assert create_response.status_code == 201

        # Get the request from DB to get its ID
        requests = await registration_request_repo.get_all(async_db_session)
        req = next((r for r in requests if r.email == unique_email), None)
        assert req is not None, "Registration request should be created"

        # Approve via admin endpoint
        approve_response = await async_client.post(
            f"/admin/registration-requests/{req.id}/approve",
            headers=auth_headers,
        )
        assert approve_response.status_code == 200

        # Verify response contains retrieval_token (not temp_password)
        data = approve_response.json()
        assert "retrieval_token" in data
        assert "user_id" in data
        assert "temp_password" not in data
        assert data["message"] == "Registration request approved"

        # Verify user exists in DB
        user = await UserRepository().get_by_email(unique_email, db=async_db_session)
        assert user is not None, "User should be created after approval"

        # Verify user has viewer role (default for approved registrations)
        assert user.role == UserRole.VIEWER

    async def test_reject_registration_does_not_create_user(
        self,
        async_client,
        auth_headers,
        async_db_session,
        registration_request_repo,
    ):
        """Verify rejecting registration does not create a user."""
        unique_email = f"reject_{uuid4().hex[:8]}@example.com"

        # Create registration request via public endpoint
        create_response = await async_client.post(
            "/auth/register-request",
            json={"email": unique_email},
        )
        assert create_response.status_code == 201

        # Get the request from DB to get its ID
        requests = await registration_request_repo.get_all(async_db_session)
        req = next((r for r in requests if r.email == unique_email), None)
        assert req is not None, "Registration request should be created"

        # Reject via admin endpoint
        reject_response = await async_client.post(
            f"/admin/registration-requests/{req.id}/reject",
            headers=auth_headers,
        )
        assert reject_response.status_code == 200

        # Verify response
        data = reject_response.json()
        assert data["message"] == "Registration request rejected"

        # Verify user does NOT exist in DB
        user = await UserRepository().get_by_email(unique_email, db=async_db_session)
        assert user is None, "User should NOT be created after rejection"

    async def test_approved_user_can_login_with_temp_password(
        self,
        async_client,
        auth_headers,
        async_db_session,
        registration_request_repo,
    ):
        """Verify user can login with temp password after approval."""
        from mkobi.core.temp_password_store import TempPasswordStore
        from mkobi.main import app

        unique_email = f"logintemp_{uuid4().hex[:8]}@example.com"

        # Create registration request via public endpoint
        create_response = await async_client.post(
            "/auth/register-request",
            json={"email": unique_email},
        )
        assert create_response.status_code == 201

        # Get the request from DB to get its ID
        requests = await registration_request_repo.get_all(async_db_session)
        req = next((r for r in requests if r.email == unique_email), None)
        assert req is not None, "Registration request should be created"

        # Approve via admin endpoint - get retrieval_token
        approve_response = await async_client.post(
            f"/admin/registration-requests/{req.id}/approve",
            headers=auth_headers,
        )
        assert approve_response.status_code == 200

        retrieval_token = approve_response.json()["retrieval_token"]

        # Retrieve temp password from Redis using the same mock client
        # that the endpoint used (stored in app.state.mock_redis)
        mock_redis = app.state.mock_redis
        temp_password = await TempPasswordStore(mock_redis).retrieve(retrieval_token)
        assert temp_password is not None, "Temp password should be retrievable from Redis"

        # Login with the temp password
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": unique_email,
                "password": temp_password,
            },
        )
        assert login_response.status_code == 200

        # Verify successful login returns tokens
        login_data = login_response.json()
        assert "access_token" in login_data
        assert login_data["token_type"] == "bearer"
        assert "user" in login_data
        assert login_data["user"]["email"] == unique_email