"""Tests for Pydantic models.

Tests the business logic for file upload, processing, and status tracking.
"""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from mkobi.models.user import (
    UserBase,
    UserCreate,
    UserRead,
    UserDB,
    UserUpdate,
)
from mkobi.models.enums import UserRole, DashboardPermission, GraphType, FilterType
from mkobi.models.dashboard import (
    DashboardConfig,
    DashboardCreate,
    DashboardRead,
    DashboardUpdate,
    DashboardSummary,
)
from mkobi.models.data import (
    DataUpload,
    ProcessingConfig,
    ProcessingResult,
    AggregatedData,
)
from mkobi.models.auth import (
    LoginRequest,
    Token,
    TokenData,
    TokenWithUser,
    ChangePasswordRequest,
)
from mkobi.models.access import (
    AccessCheck,
    AccessGrant,
)


class TestUserModels:
    """Tests for Pydantic user models."""

    def test_user_create_valid(self):
        """Test valid user creation."""
        user = UserCreate(
            email="test@example.com",
            password="secure_password123",
            role=UserRole.VIEWER,
        )
        assert user.email == "test@example.com"
        assert user.password == "secure_password123"
        assert user.role == UserRole.VIEWER

    def test_user_create_invalid_email(self):
        """Test validation of invalid email."""
        with pytest.raises(ValidationError):
            UserCreate(
                email="invalid-email",
                password="secure_password123",
                role=UserRole.VIEWER,
            )

    def test_user_create_invalid_role(self):
        """Test validation of invalid role."""
        with pytest.raises(ValidationError):
            UserCreate(
                email="test@example.com",
                password="secure_password123",
                role="invalid_role",
            )

    def test_user_create_missing_password(self):
        """Test password requirement."""
        with pytest.raises(ValidationError):
            UserCreate(
                email="test@example.com",
                role=UserRole.VIEWER,
            )

    def test_user_read_valid(self):
        """Test user read model creation."""
        user = UserRead(
            id="550e8400-e29b-41d4-a716-446655440000",
            email="john@example.com",
            role=UserRole.ADMIN,
            is_active=True,
            created_at="2026-04-24T16:02:46+03:00",
        )
        assert str(user.id) == "550e8400-e29b-41d4-a716-446655440000"
        assert user.email == "john@example.com"
        assert user.role == UserRole.ADMIN
        assert user.display_name == "john"

    def test_user_db_valid(self):
        """Test user DB model creation."""
        user = UserDB(
            id="550e8400-e29b-41d4-a716-446655440000",
            email="test@example.com",
            password_hash="$2b$12$examplehash",
            role=UserRole.EDITOR,
            is_active=True,
            created_at="2026-04-24T16:02:46+03:00",
            updated_at="2026-04-24T16:02:46+03:00",
        )
        assert str(user.id) == "550e8400-e29b-41d4-a716-446655440000"
        assert user.password_hash == "$2b$12$examplehash"
        assert user.role == UserRole.EDITOR

    def test_user_update_partial(self):
        """Test partial user update."""
        user = UserUpdate(email="new@example.com")
        assert user.email == "new@example.com"
        assert user.role is None
        assert user.password is None

    def test_user_update_all_fields(self):
        """Test updating all user fields."""
        user = UserUpdate(
            email="new@example.com",
            role=UserRole.ADMIN,
            password="new_password",
        )
        assert user.email == "new@example.com"
        assert user.role == UserRole.ADMIN
        assert user.password == "new_password"

    def test_user_base_config(self):
        """Test base model configuration."""
        user = UserBase(email="test@example.com", role=UserRole.VIEWER)
        config = user.model_config
        assert config.get("from_attributes") is True

    def test_user_create_from_attributes(self):
        """Test model creation from attributes."""
        data = {
            "email": "test@example.com",
            "password": "pass",
            "role": UserRole.ADMIN,
        }
        user = UserCreate.model_validate(data)
        assert user.email == "test@example.com"
        assert user.role == UserRole.ADMIN


class TestDashboardModels:
    """Tests for Pydantic dashboard models."""

    def test_dashboard_config_valid(self):
        """Test valid dashboard configuration."""
        config = DashboardConfig(
            graph_types=[GraphType.BAR, GraphType.LINE],
            filters=[{"field": "year", "type": FilterType.SELECT}],
            aggregations=[{"type": "sum", "field": "revenue"}],
        )
        assert config.graph_types == [GraphType.BAR, GraphType.LINE]

    def test_dashboard_config_minimal(self):
        """Test minimal dashboard configuration."""
        config = DashboardConfig(graph_types=[GraphType.BAR])
        assert config.graph_types == [GraphType.BAR]

    def test_dashboard_config_invalid_graph_type(self):
        """Test validation of invalid graph type."""
        with pytest.raises(ValidationError):
            DashboardConfig(graph_types=["invalid_type"])

    def test_dashboard_create_valid(self):
        """Test valid dashboard creation."""
        dashboard = DashboardCreate(
            name="Sales Dashboard",
            config=DashboardConfig(
                graph_types=[GraphType.BAR, GraphType.LINE],
                filters=[{"field": "year", "type": FilterType.SELECT}],
            ),
        )
        assert dashboard.name == "Sales Dashboard"
        assert dashboard.config.graph_types == [GraphType.BAR, GraphType.LINE]

    def test_dashboard_read_valid(self):
        """Test dashboard read model creation."""
        dashboard = DashboardRead(
            id="550e8400-e29b-41d4-a716-446655440000",
            name="Sales Dashboard",
            description="Test description",
            config=DashboardConfig(graph_types=[GraphType.BAR]),
            permission=DashboardPermission.VIEW,
            created_at="2026-04-24T16:02:46+03:00",
            updated_at="2026-04-24T16:02:46+03:00",
        )
        assert str(dashboard.id) == "550e8400-e29b-41d4-a716-446655440000"
        assert dashboard.name == "Sales Dashboard"
        assert dashboard.config.graph_types == [GraphType.BAR]

    def test_dashboard_update_partial(self):
        """Test partial dashboard update."""
        update = DashboardUpdate(name="New Name")
        assert update.name == "New Name"
        assert update.config is None

    def test_dashboard_config_with_charts(self):
        """Test configuration with charts."""
        config = DashboardConfig(
            graph_types=[GraphType.BAR, GraphType.LINE, GraphType.PIE],
            charts=[
                {
                    "type": GraphType.BAR,
                    "x": "category",
                    "y": "revenue",
                    "title": "Revenue by Category",
                }
            ],
        )
        assert len(config.charts) == 1
        assert config.charts[0]["type"] == GraphType.BAR

    def test_dashboard_summary_with_permission(self):
        """Test DashboardSummary model includes permission field."""
        from datetime import datetime
        summary = DashboardSummary(
            id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            name="Test Dashboard",
            description="Test description",
            permission=DashboardPermission.VIEW,
            created_at=datetime.now(),
        )
        assert summary.id == uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        assert summary.name == "Test Dashboard"
        assert summary.permission == DashboardPermission.VIEW

    def test_dashboard_summary_permission_serialization(self):
        """Test DashboardSummary permission field serializes correctly."""
        from datetime import datetime
        summary = DashboardSummary(
            id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            name="Test Dashboard",
            description="Test description",
            permission=DashboardPermission.EDIT,
            created_at=datetime.now(),
        )
        # Test model serialization
        data = summary.model_dump()
        assert data["permission"] == "edit"

        # Test JSON serialization
        json_data = summary.model_dump(mode="json")
        assert json_data["permission"] == "edit"


class TestDataModels:
    """Tests for Pydantic data models."""

    def test_data_upload_valid(self):
        """Test valid data upload."""
        upload = DataUpload(
            file=b"test,data\n1,2\n3,4",
            filename="data.csv.gz",
            dashboard_id="550e8400-e29b-41d4-a716-446655440000",
        )
        assert upload.filename == "data.csv.gz"
        assert str(upload.dashboard_id) == "550e8400-e29b-41d4-a716-446655440000"

    def test_processing_config_valid(self):
        """Test valid processing configuration."""
        from mkobi.models.transformation_configs import (
            AggregationConfig,
            FilterConfig,
        )
        from mkobi.models.enums import (
            AggregationFunctionEnum,
            FilterOperatorEnum,
        )
        
        config = ProcessingConfig(
            filters=[FilterConfig(column="year", operator=FilterOperatorEnum.GTE, value=2020)],
            aggregations=[AggregationConfig(column="revenue", function=AggregationFunctionEnum.SUM, alias="total_revenue")],
            groupby=["category", "region"],
        )
        assert len(config.filters) == 1
        assert len(config.aggregations) == 1

    def test_processing_config_minimal(self):
        """Test minimal processing configuration."""
        config = ProcessingConfig()
        assert config.filters is None
        assert config.aggregations is None

    def test_processing_result_valid(self):
        """Test valid processing result."""
        result = ProcessingResult(
            success=True,
            task_id="550e8400-e29b-41d4-a716-446655440000",
            dashboard_id="550e8400-e29b-41d4-a716-446655440000",
            rows_processed=1000,
            message="Data processed successfully",
            data={"columns": ["category", "revenue"], "rows": 50},
        )
        assert result.success is True
        assert str(result.task_id) == "550e8400-e29b-41d4-a716-446655440000"
        assert result.rows_processed == 1000

    def test_processing_result_without_data(self):
        """Test processing result without additional data."""
        result = ProcessingResult(
            success=True,
            task_id="550e8400-e29b-41d4-a716-446655440000",
            dashboard_id="550e8400-e29b-41d4-a716-446655440000",
            rows_processed=0,
            message="No data to process",
        )
        assert result.data is None

    def test_aggregated_data_valid(self):
        """Test valid aggregated data."""
        data = AggregatedData(
            dashboard_id="550e8400-e29b-41d4-a716-446655440000",
            chart_type=GraphType.BAR,
            data=[
                {"dims": {"category": "A"}, "metrics": {"revenue": 1000}},
                {"dims": {"category": "B"}, "metrics": {"revenue": 2000}},
            ],
            metadata={"total": 3000, "count": 2},
        )
        assert data.chart_type == GraphType.BAR
        assert len(data.data) == 2

    def test_aggregated_data_invalid_chart_type(self):
        """Test validation of invalid chart type."""
        with pytest.raises(ValidationError):
            AggregatedData(
                dashboard_id=uuid.uuid4(),
                chart_type="invalid",
                data=[],
            )


class TestAuthModels:
    """Tests for Pydantic authentication models."""

    def test_login_request_valid(self):
        """Test valid login request."""
        login = LoginRequest(
            email="user@example.com",
            password="secure_password123",
        )
        assert login.email == "user@example.com"

    def test_login_request_invalid_email(self):
        """Test validation of invalid email in login request."""
        with pytest.raises(ValidationError):
            LoginRequest(
                email="not-an-email",
                password="secure_password123",
            )

    def test_token_valid(self):
        """Test valid token creation."""
        token = Token(
            access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            token_type="bearer",
        )
        assert token.token_type == "bearer"

    def test_token_with_user_valid(self):
        """Test valid token with user creation."""
        user = UserRead(
            id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            email="john@example.com",
            role=UserRole.VIEWER,
            is_active=True,
            created_at=datetime.now(),
        )
        token = TokenWithUser(
            access_token="test_token_123",
            token_type="bearer",
            user=user,
        )
        assert token.access_token == "test_token_123"
        assert token.token_type == "bearer"
        assert token.user.email == "john@example.com"
        assert token.user.display_name == "john"

    def test_token_data_valid(self):
        """Test valid token data creation."""
        token_data = TokenData(
            email="user@example.com",
            user_id="550e8400-e29b-41d4-a716-446655440000",
        )
        assert token_data.email == "user@example.com"

    def test_token_data_partial(self):
        """Test token data creation with partial data."""
        token_data = TokenData(email="user@example.com")
        assert token_data.user_id is None

    def test_access_check_valid(self):
        """Test valid access check creation."""
        check = AccessCheck(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            dashboard_id="550e8400-e29b-41d4-a716-446655440001",
            required_permission=DashboardPermission.VIEW,
        )
        assert check.required_permission == DashboardPermission.VIEW

    def test_access_check_default_permission(self):
        """Test default permission value."""
        check = AccessCheck(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            dashboard_id="550e8400-e29b-41d4-a716-446655440001",
        )
        assert check.required_permission == DashboardPermission.VIEW

    def test_access_grant_valid(self):
        """Test valid access grant creation."""
        grant = AccessGrant(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            dashboard_id="550e8400-e29b-41d4-a716-446655440001",
            permission=DashboardPermission.EDIT,
        )
        assert grant.permission == DashboardPermission.EDIT

    def test_access_grant_default_permission(self):
        """Test default access level value."""
        grant = AccessGrant(
            user_id="550e8400-e29b-41d4-a716-446655440000",
            dashboard_id="550e8400-e09b-41d4-a716-446655440001",
        )
        assert grant.permission == DashboardPermission.VIEW

    def test_change_password_request_valid(self):
        """Test valid change password request."""
        req = ChangePasswordRequest(
            current_password="OldPass123!",
            new_password="NewPass456!",
            confirm_password="NewPass456!",
        )
        assert req.current_password == "OldPass123!"
        assert req.new_password == "NewPass456!"

    def test_change_password_request_passwords_match(self):
        """Test valid change password request with matching passwords."""
        req = ChangePasswordRequest(
            current_password="OldPass123!",
            new_password="NewPass456!",
            confirm_password="NewPass456!",
        )
        assert req.new_password == req.confirm_password

    def test_change_password_request_passwords_mismatch(self):
        """Test validation error when passwords do not match."""
        with pytest.raises(ValidationError) as exc_info:
            ChangePasswordRequest(
                current_password="OldPass123!",
                new_password="NewPass456!",
                confirm_password="DifferentPass!",
            )
        errors = exc_info.value.errors()
        assert any("do not match" in str(err.get("msg", "")) for err in errors)

    def test_change_password_request_weak_password(self):
        """Test validation error for weak new password."""
        with pytest.raises(ValidationError):
            ChangePasswordRequest(
                current_password="OldPass123!",
                new_password="weak",
                confirm_password="weak",
            )
