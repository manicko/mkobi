from datetime import datetime
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from mkobi.models.enums import GraphType
from mkobi.models.types import GraphConfigDict


class GraphBase(BaseModel):
    """Base model for charts."""

    name: str
    type: GraphType
    dashboard_id: UUID
    config: GraphConfigDict
    dimensions: list[str]
    metrics: list[str]

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Sales by Category",
                "type": "bar",
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
                "config": {"xaxis": {"title": "Category"}, "yaxis": {"title": "Sales"}},
                "dimensions": ["category", "year"],
                "metrics": ["sales", "revenue"],
            }
        },
    )


class GraphCreate(GraphBase):
    """Model for creating chart."""

    # ``extra="forbid"`` is declared here, not on ``GraphBase``. Pydantic
    # inherits ``model_config`` into every subclass, and ``GraphBase`` is also
    # the parent of ``GraphRead`` -- a response model. Forbidding on the base
    # would therefore reach ``GraphRead`` and, because the policy propagates
    # into the nested ``GraphConfigDict`` (a ``TypedDict``), reject any stored
    # ``config`` carrying a key outside that dict's declared set. The dev
    # seeder writes ``config={"x": ..., "color": ..., "metrics": [...]}``, and
    # ``metrics`` is not a ``GraphConfigDict`` key, so a base-level forbid would
    # break the graph read path for seeded data. ``GraphCreate`` is the
    # route-facing request model, so the policy belongs exactly here. The base
    # config is composed in so the request schema keeps its published example.
    model_config = ConfigDict(**GraphBase.model_config, extra="forbid")


class GraphUpdate(BaseModel):
    """Model for updating chart."""

    name: str | None = None
    type: GraphType | None = None
    config: GraphConfigDict | None = None
    dimensions: list[str] | None = None
    metrics: list[str] | None = None

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Updated Sales by Category",
                "type": "line",
                "config": {"xaxis": {"title": "Category"}, "yaxis": {"title": "Revenue"}},
                "dimensions": ["category"],
                "metrics": ["revenue"],
            }
        },
    )


class GraphRead(GraphBase):
    """Model for reading chart data."""

    id: UUID
    created_at: datetime | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Sales by Category",
                "type": "bar",
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
                "config": {"xaxis": {"title": "Category"}, "yaxis": {"title": "Sales"}},
                "dimensions": ["category", "year"],
                "metrics": ["sales", "revenue"],
                "created_at": "2026-04-24T16:02:46+03:00",
            }
        },
    )
