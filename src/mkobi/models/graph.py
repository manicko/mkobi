from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator
from uuid import UUID

from mkobi.models.enums import GraphType
from mkobi.models.types import GraphConfigDict


# The keys ``GraphConfigDict`` declares. Computed once from the TypedDict's own
# annotations so the refusal set cannot drift from the declared vocabulary.
_DECLARED_GRAPH_CONFIG_KEYS: frozenset[str] = frozenset(GraphConfigDict.__annotations__)


def _reject_unknown_config_keys(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Refuse an undeclared key inside a graph ``config`` mapping.

    Pydantic's model-level ``extra="forbid"`` reaches a nested ``TypedDict`` in
    the pinned Pydantic version, but this validator states the rule explicitly
    at the model boundary and names the offending key, so the refusal is a
    deliberate contract rather than a library-version accident. The client
    genuinely sends ``metrics``, ``orientation``, ``barmode`` and ``showlegend``;
    those are now declared, so only a genuinely unknown key is refused.

    Args:
        config: The incoming ``config`` mapping, or None when omitted.

    Returns:
        The mapping unchanged when every key is declared.

    Raises:
        ValueError: When ``config`` carries a key outside the declared set; the
            message names the key.
    """
    if config is None:
        return config
    unknown = set(config) - _DECLARED_GRAPH_CONFIG_KEYS
    if unknown:
        named = ", ".join(sorted(unknown))
        raise ValueError(f"unknown graph config key(s): {named}")
    return config


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

    @field_validator("config", mode="before")
    @classmethod
    def reject_unknown_config_keys(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Refuse a key inside ``config`` that ``GraphConfigDict`` does not declare."""
        return _reject_unknown_config_keys(value)


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

    @field_validator("config", mode="before")
    @classmethod
    def reject_unknown_config_keys(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Refuse a key inside ``config`` that ``GraphConfigDict`` does not declare."""
        return _reject_unknown_config_keys(value)


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
