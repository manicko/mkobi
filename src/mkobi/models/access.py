from uuid import UUID

from pydantic import BaseModel, ConfigDict

from mkobi.models.enums import DashboardPermission


class AccessCheck(BaseModel):
    """Model for checking dashboard access."""

    user_id: UUID
    dashboard_id: UUID
    required_permission: DashboardPermission = DashboardPermission.VIEW

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440001",
                "required_permission": "view",
            }
        },
    )


class AccessGrant(BaseModel):
    """Model for granting dashboard access."""

    user_id: UUID
    dashboard_id: UUID
    permission: DashboardPermission = DashboardPermission.VIEW

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440001",
                "permission": "edit",
            }
        },
    )