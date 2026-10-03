import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from uuid import UUID

from mkobi.models.enums import DashboardPermission, GraphType
from mkobi.models.layout import LayoutRead


class DashboardConfig(BaseModel):
    """Dashboard configuration model."""

    graph_types: list[GraphType]
    filters: list[dict[str, Any]] | None = None
    aggregations: list[dict[str, Any]] | None = None
    charts: list[dict[str, Any]] | None = None
    title: str | None = None
    description: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "graph_types": ["bar", "line"],
                "filters": [
                    {"field": "year", "type": "select"},
                    {"field": "category", "type": "multi_select"},
                ],
                "aggregations": [
                    {"type": "sum", "field": "revenue"},
                    {"type": "avg", "field": "sales"},
                ],
                "charts": [
                    {
                        "type": "bar",
                        "x": "category",
                        "y": "revenue",
                        "title": "Revenue by Category",
                    }
                ],
                "title": "Sales Dashboard",
                "description": "Overview of sales performance",
            }
        },
    )


class DashboardCreate(BaseModel):
    """Model for creating new dashboard."""

    name: str
    description: str | None = Field(None, max_length=200)
    config: DashboardConfig = DashboardConfig(graph_types=[GraphType.BAR])
    layout_id: UUID | None = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError('Name must be at least 3 characters')
        if len(v) > 100:
            raise ValueError('Name must be at most 100 characters')
        if not re.match(r'^[a-zA-Z0-9\s-]+$', v):
            raise ValueError('Name can only contain letters, numbers, spaces, and hyphens')
        return v

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Sales Dashboard",
                "description": "Overview of sales performance",
                "config": {
                    "graph_types": ["bar", "line"],
                    "filters": [{"field": "year", "type": "select"}],
                    "charts": [
                        {
                            "type": "bar",
                            "x": "category",
                            "y": "revenue",
                        }
                    ],
                },
                "layout_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        },
    )


class DashboardRead(BaseModel):
    """Model for reading dashboard data.

    Note: The `permission` field is NOT a database column. It is injected at runtime
    by the service layer based on the requesting user's access level. When constructing
    DashboardRead from ORM, the permission must be provided explicitly via the
    `_dashboard_to_read` method or by passing permission to the constructor.
    """

    id: UUID
    name: str
    description: str | None
    config: DashboardConfig
    permission: DashboardPermission
    layout_id: UUID | None = None
    layout: LayoutRead | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Sales Dashboard",
                "description": "Overview of sales performance",
                "config": {
                    "graph_types": ["bar", "line"],
                    "filters": [{"field": "year", "type": "select"}],
                },
                "layout_id": "550e8400-e29b-41d4-a716-446655440001",
                "layout": {
                    "id": "550e8400-e29b-41d4-a716-446655440001",
                    "name": "sales_layout",
                    "definition": {"grid": []},
                    "created_at": "2026-05-04T18:00:00+03:00",
                },
                "created_at": "2026-04-24T16:02:46+03:00",
                "updated_at": "2026-04-24T16:02:46+03:00",
            }
        },
    )


class DashboardUpdate(BaseModel):
    """Model for updating dashboard."""

    name: str | None = None
    description: str | None = Field(None, max_length=200)
    config: DashboardConfig | None = None
    layout_id: UUID | None = None

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Updated Sales Dashboard",
                "description": "Updated description",
                "config": {
                    "graph_types": ["bar", "line", "pie"],
                    "filters": [{"field": "year", "type": "select"}],
                },
                "layout_id": "550e8400-e29b-41d4-a716-446655440001",
            }
        },
    )


class DashboardSummary(BaseModel):
    """Model for dashboard list view with user's access permission."""

    id: UUID
    name: str
    description: str | None
    permission: DashboardPermission
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class DashboardAdmin(BaseModel):
    """Model for admin dashboard list without full config."""

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )
