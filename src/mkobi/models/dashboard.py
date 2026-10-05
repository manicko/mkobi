import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from uuid import UUID

from mkobi.models.enums import DashboardPermission, GraphType
from mkobi.models.layout import LayoutRead


class EvaluableFilterType(StrEnum):
    """The closed vocabulary of filter controls the aggregate read can evaluate.

    This is deliberately **not** ``mkobi.models.enums.FilterType``. That enum is
    the *storage* vocabulary (a live PostgreSQL enum whose labels are inert and
    whose retirement is ``C14-17``); this one is the set of declared types a
    submitted filter value can actually be evaluated against. Aliasing the two
    would make the storage enum authoritative over evaluability and recreate the
    defect this boundary closes.

    ``range`` is absent on purpose: ``D-16-2`` removed it until a range
    definition exists, and this model is where a stored ``range`` is refused
    **by name** -- on a dashboard save, naming one field, which cannot blank an
    already-rendered dashboard.
    """

    SELECT = "select"
    MULTISELECT = "multiselect"
    DATE = "date"


class DashboardFilterConfig(BaseModel):
    """One declared dashboard filter, as submitted to a write boundary.

    This element validates a **submission**; it does not own the stored shape.
    ``DashboardConfig.filters`` stays ``list[dict[str, Any]] | None`` so the
    read path (``DashboardRead.config``) keeps passing every already-stored
    element through byte-for-byte. ``extra="allow"`` preserves and passes
    through any additional keys an operator stored (``options``, ``default``,
    ``min``, ``max`` ...) instead of silently deleting them on a save round
    trip. ``type`` is the closed ``EvaluableFilterType`` vocabulary, so a
    declared ``range`` is refused with a named field.
    """

    model_config = ConfigDict(extra="allow")

    field: str
    type: EvaluableFilterType
    source: str | None = None
    multi: bool | None = None


class _DashboardConfigBase[T](BaseModel):
    """Shared shape of the dashboard config, parameterised by its filter element.

    ``T`` is the element type of ``filters``: ``dict[str, Any]`` for the
    storage/read shape (``DashboardConfig``) and ``DashboardFilterConfig`` for
    the write-boundary shape (``DashboardWriteConfig``). Parameterising the
    shared shape -- rather than narrowing a mutable field in a subclass -- keeps
    both concrete models independently typed without a subclass override mypy
    would reject.
    """

    graph_types: list[GraphType]
    filters: list[T] | None = None
    aggregations: list[dict[str, Any]] | None = None
    charts: list[dict[str, Any]] | None = None
    title: str | None = None
    description: str | None = None


class DashboardConfig(_DashboardConfigBase[dict[str, Any]]):
    """Dashboard configuration model -- the storage and read shape.

    ``filters`` is the tolerant ``list[dict[str, Any]] | None``: this is
    simultaneously what ``DashboardService`` stores (``model_dump``) and what
    ``DashboardRead.config`` serves, so it must keep today's passthrough
    behaviour byte-for-byte. A stored ``range`` element reads back unchanged.
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "graph_types": ["bar", "line"],
                "filters": [
                    {"field": "year", "type": "select"},
                    {"field": "category", "type": "multiselect"},
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


class DashboardWriteConfig(_DashboardConfigBase[DashboardFilterConfig]):
    """The write-boundary shape of the dashboard config.

    Identical to ``DashboardConfig`` except that each ``filters`` element is a
    validated ``DashboardFilterConfig``. Used by ``DashboardCreate`` and
    ``DashboardUpdate`` only; ``DashboardRead.config`` keeps the tolerant
    ``DashboardConfig``, so this typing is **write-only** and never makes a read
    refuse an already-stored value.
    """

    model_config = ConfigDict(from_attributes=True)


class DashboardCreate(BaseModel):
    """Model for creating new dashboard."""

    name: str
    description: str | None = Field(None, max_length=200)
    config: DashboardWriteConfig = DashboardWriteConfig(graph_types=[GraphType.BAR])
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
    config: DashboardWriteConfig | None = None
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
