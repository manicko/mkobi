"""Tests for the request-boundary ``extra="forbid"`` policy (EB-5, EXT-007).

Four route-facing request models must reject undeclared fields at the request
boundary with a ``422`` in the project's RFC 7807 envelope, instead of letting
Pydantic's default ``ignore`` silently drop them:

* ``models/graph.py::GraphCreate``   (``POST /graphs/``)
* ``models/graph.py::GraphUpdate``   (``PUT /graphs/{graph_id}``)
* ``models/dashboard.py::DashboardUpdate``  (``PUT /dashboards/{dashboard_id}``)
* ``models/processing_configs.py::ProcessingConfigUpdate``
  (``PUT /processing-configs/{dashboard_id}``)

The five ``extra="allow"`` models in ``models/types.py`` are deliberately out of
scope (DP-6 is write-bodies-only): they are not request-shaped, and forbidding
them would silently drop keys rather than 422.

``GraphCreate`` is a subclass of ``GraphBase``, and Pydantic inherits
``model_config`` across subclassing, so declaring ``extra="forbid"`` on the base
would also reach ``GraphRead(GraphBase)`` -- a **response** model with
``from_attributes=True``. Two effects make that unsafe:

* ``from_attributes`` validation of an ORM object carrying an undeclared
  attribute still succeeds (``from_attributes`` reads only the model's declared
  fields off the source), and
* the ``extra`` policy **propagates into nested ``TypedDict`` fields**, so
  ``GraphRead.config`` (a ``GraphConfigDict``) would reject the ``metrics`` key
  the dev seeder stores. ``metrics`` is now declared (SECB-5 widened the
  vocabulary), so the seeder's key is carried rather than dropped; the guard is
  kept so a later shrink of the vocabulary cannot silently break the read path.

The policy is therefore declared on ``GraphCreate`` directly, and the regression
guards at the bottom pin that ``GraphRead`` still validates the seeder's stored
config. The T-numbers label the block's required tests.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from mkobi.models.dashboard import DashboardUpdate
from mkobi.models.graph import GraphCreate, GraphRead, GraphUpdate
from mkobi.models.processing_configs import ProcessingConfigUpdate
from mkobi.utils.exceptions import ErrorCode

# The declared field set of each route-facing request model. Listed explicitly
# so the positive guards fail loudly if a model gains or loses a field.
DECLARED_GRAPH_CREATE_KEYS: frozenset[str] = frozenset(
    {"name", "type", "dashboard_id", "config", "dimensions", "metrics"}
)
DECLARED_GRAPH_UPDATE_KEYS: frozenset[str] = frozenset(
    {"name", "type", "config", "dimensions", "metrics"}
)
DECLARED_DASHBOARD_UPDATE_KEYS: frozenset[str] = frozenset(
    {"name", "description", "config", "layout_id"}
)
DECLARED_PROCESSING_CONFIG_UPDATE_KEYS: frozenset[str] = frozenset(
    {"settings", "metric_agg"}
)

# Minimal valid bodies for the four routes, one key short of a fully-populated
# payload so a single illegal key can be added without a schema error masking
# the extra-key rejection.
VALID_GRAPH_CREATE: dict[str, Any] = {
    "name": "Boundary Graph",
    "type": "bar",
    "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
    "config": {},
    "dimensions": ["category"],
    "metrics": ["revenue"],
}

# The routes that consume each model, used by the OpenAPI tripwire.
_ROUTE_BODY_PATHS: dict[str, tuple[str, str]] = {
    # selector -> (path suffix, method)
    "GraphCreate (POST /graphs/)": ("/graphs/", "post"),
    "GraphUpdate (PUT /graphs/{graph_id})": ("/graphs/{graph_id}", "put"),
    "DashboardUpdate (PUT /dashboards/{dashboard_id})": (
        "/dashboards/{dashboard_id}",
        "put",
    ),
    "ProcessingConfigUpdate (PUT /processing-configs/{dashboard_id})": (
        "/processing-configs/{dashboard_id}",
        "put",
    ),
}


def _resolve_ref(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Resolve a ``$ref`` node, unwrapping an ``anyOf`` null-union."""
    if "anyOf" in node:
        for branch in node["anyOf"]:
            if branch.get("type") != "null":
                return _resolve_ref(schema, branch)
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return schema["components"]["schemas"][name]
    return node


# ==================== T1-T4: undeclared key is a 422 ====================


class TestUndeclaredKeyIs422:
    """Each route rejects an undeclared key with the standard error envelope."""

    async def test_t1_create_graph_rejects_undeclared_key(
        self, authenticated_client: AsyncClient
    ) -> None:
        """T1: ``POST /graphs/`` rejects an undeclared key with 422."""
        body = {**VALID_GRAPH_CREATE, "bogus_key": 1}
        response = await authenticated_client.post("/graphs/", json=body)
        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.VALIDATION_ERROR.value

    async def test_t2_update_graph_rejects_undeclared_key(
        self, authenticated_client: AsyncClient
    ) -> None:
        """T2: ``PUT /graphs/{graph_id}`` rejects an undeclared key with 422."""
        response = await authenticated_client.put(
            f"/graphs/{uuid4()}",
            json={"name": "Updated", "bogus_key": 1},
        )
        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.VALIDATION_ERROR.value

    async def test_t3_update_dashboard_rejects_undeclared_key(
        self, authenticated_client: AsyncClient
    ) -> None:
        """T3: ``PUT /dashboards/{dashboard_id}`` rejects an undeclared key with 422."""
        response = await authenticated_client.put(
            f"/dashboards/{uuid4()}",
            json={"name": "Updated", "bogus_key": 1},
        )
        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.VALIDATION_ERROR.value

    async def test_t4_update_processing_config_rejects_undeclared_key(
        self, authenticated_client: AsyncClient
    ) -> None:
        """T4: ``PUT /processing-configs/{dashboard_id}`` rejects an undeclared key.

        ``settings`` itself is already strict (DP-014); this pins the *top-level*
        request body, which previously ignored unknown keys.
        """
        response = await authenticated_client.put(
            f"/processing-configs/{uuid4()}",
            json={"metric_agg": "sum", "bogus_key": 1},
        )
        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.VALIDATION_ERROR.value


# ==================== T5-T8: declared keys are still accepted ====================


class TestDeclaredKeysStillAccepted:
    """A positive guard per model: forbidding dropped nothing legitimate.

    Without these, a ``forbid`` that silently broke a real write would pass
    every negative test above. Validated at the model boundary -- deterministic
    and independent of route access control -- which is exactly the surface the
    policy changed.
    """

    def test_t5_graph_create_accepts_declared_keys(self) -> None:
        """T5: every declared ``GraphCreate`` key still validates."""
        model = GraphCreate.model_validate(VALID_GRAPH_CREATE)
        assert set(type(model).model_fields) == DECLARED_GRAPH_CREATE_KEYS

    def test_t6_graph_update_accepts_declared_keys(self) -> None:
        """T6: every declared ``GraphUpdate`` key still validates."""
        model = GraphUpdate.model_validate(
            {
                "name": "Updated",
                "type": "line",
                "config": {},
                "dimensions": ["category"],
                "metrics": ["revenue"],
            }
        )
        assert set(type(model).model_fields) == DECLARED_GRAPH_UPDATE_KEYS

    def test_t7_dashboard_update_accepts_declared_keys(self) -> None:
        """T7: every declared ``DashboardUpdate`` key still validates."""
        model = DashboardUpdate.model_validate(
            {
                "name": "Updated",
                "description": "Updated description",
                "config": {"graph_types": ["bar"]},
                "layout_id": "550e8400-e29b-41d4-a716-446655440001",
            }
        )
        assert set(type(model).model_fields) == DECLARED_DASHBOARD_UPDATE_KEYS

    def test_t8_processing_config_update_accepts_declared_keys(self) -> None:
        """T8: every declared ``ProcessingConfigUpdate`` key still validates."""
        model = ProcessingConfigUpdate.model_validate(
            {"settings": {"loader": "L"}, "metric_agg": "sum"}
        )
        assert set(type(model).model_fields) == DECLARED_PROCESSING_CONFIG_UPDATE_KEYS


# ==================== T9: OpenAPI tripwire ====================


class TestRequestBoundaryOpenAPISchema:
    """The forbid policy is visible as ``additionalProperties: false``."""

    def test_t9_all_four_request_bodies_forbid_undeclared_keys(self) -> None:
        """T9: each published request body schema sets ``additionalProperties: false``.

        Follows ``TestSettingsOpenAPISchema::t4_openapi_settings_schema_has_no_additional_properties``.
        """
        from mkobi.main import app

        schema = app.openapi()
        for selector, (suffix, method) in _ROUTE_BODY_PATHS.items():
            path = next(
                path
                for path in schema["paths"]
                if path.endswith(suffix) and method in schema["paths"][path]
            )
            body_schema = schema["paths"][path][method]["requestBody"]["content"][
                "application/json"
            ]["schema"]
            resolved = _resolve_ref(schema, body_schema)
            assert resolved.get("additionalProperties") is False, (
                f"{selector} must publish additionalProperties: false"
            )


# ==================== T10: GraphRead response regression guard ====================


class _FakeGraphRow:
    """An ORM-like row carrying an attribute ``GraphRead`` does not declare.

    The real ``db.models.graphs.Graph`` supplies ``updated_at``; ``GraphRead``
    declares ``id`` and ``created_at`` but not ``updated_at``.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        from datetime import datetime

        self.id = uuid4()
        self.name = "Response Graph"
        self.type = "bar"
        self.dashboard_id = uuid4()
        self.config: dict[str, Any] = config if config is not None else {}
        self.dimensions = ["category"]
        self.metrics = ["revenue"]
        self.created_at = datetime.now()
        # Undeclared extra attribute, present on the real ORM row.
        self.updated_at = datetime.now()


class TestGraphReadResponseUnaffected:
    """``extra="forbid"`` is NOT on ``GraphRead``; the read path is unchanged.

    Declaring the policy on ``GraphBase`` would inherit it into ``GraphRead``,
    and Pydantic propagates a parent's ``extra`` policy into nested
    ``TypedDict`` fields. ``GraphRead.config`` is a ``GraphConfigDict``. SECB-5
    widened that dict to declare ``metrics`` (the dev seeder stores
    ``config={"x": ..., "color": ..., "metrics": [...]}``), so the read path
    carries the key instead of dropping it. A base-level forbid would still
    reject any *genuinely* unknown stored key, which is why the policy lives on
    ``GraphCreate``.
    """

    def test_t10_graph_read_accepts_stored_config_with_undeclared_key(
        self,
    ) -> None:
        """T10: ``GraphRead`` validates the seeder's stored ``config.metrics``.

        The real ``db.seeders.test_media_dash`` writes a ``metrics`` key inside
        the graph config. Since SECB-5 declared it, the read carries it; because
        ``GraphRead`` carries no forbid, any other undeclared key is ignored
        rather than rejected. A base-level forbid would have raised on such a
        key and broken the read path for seeded graphs, which is why the policy
        lives on ``GraphCreate``.
        """
        seeded_config = {"x": "month_label", "color": "brand", "metrics": ["tvr_sum"]}
        read = GraphRead.model_validate(_FakeGraphRow(config=seeded_config))
        # Validation did not raise. The declared keys are carried.
        assert read.config["x"] == "month_label"
        assert read.config["color"] == "brand"
        assert read.config["metrics"] == ["tvr_sum"]

    def test_t11_graph_read_does_not_declare_forbid(self) -> None:
        """T11: ``GraphRead`` carries no ``extra="forbid"`` policy."""
        assert GraphRead.model_config.get("extra") != "forbid"
        # The inherited forbid is absent, so the nested TypedDict keeps its own
        # permissive policy and the undeclared source attribute is ignored.
        read = GraphRead.model_validate(_FakeGraphRow())
        assert "updated_at" not in read.model_dump()


# ==================== SECB-5: nested config vocabulary ====================


class TestGraphConfigNestedVocabulary:
    """SECB-5: the declared ``config`` vocabulary matches the client, and a
    genuinely unknown key inside ``config`` is refused at create and update.

    The client (``ChartRenderer.tsx``) reads ``x``, ``color``, ``metrics``,
    ``orientation`` and ``barmode`` from ``graph.config``; ``showlegend`` lives
    on ``config.layout``. Before this block the ``GraphConfigDict`` declared
    neither ``metrics`` nor ``orientation`` nor ``barmode``, so a request
    carrying them was refused by the nested forbid.
    """

    def test_declared_config_keys_are_accepted_at_create(self) -> None:
        """Every client-read ``config`` key validates on ``GraphCreate``."""
        model = GraphCreate.model_validate(
            {
                **VALID_GRAPH_CREATE,
                "config": {
                    "x": "month",
                    "color": "brand",
                    "metrics": ["sales"],
                    "orientation": "h",
                    "barmode": "stack",
                    "showlegend": True,
                },
            }
        )
        assert model.config["metrics"] == ["sales"]
        assert model.config["orientation"] == "h"
        assert model.config["barmode"] == "stack"

    def test_declared_config_keys_are_accepted_at_update(self) -> None:
        """Every client-read ``config`` key validates on ``GraphUpdate``."""
        model = GraphUpdate.model_validate(
            {"config": {"x": "month", "metrics": ["sales"], "barmode": "group"}}
        )
        assert model.config is not None
        assert model.config["barmode"] == "group"

    def test_undeclared_config_key_is_refused_at_create(self) -> None:
        """A key inside ``config`` that is not declared fails on create."""
        with pytest.raises(ValidationError) as exc_info:
            GraphCreate.model_validate(
                {**VALID_GRAPH_CREATE, "config": {"x": "month", "bogus": 1}}
            )
        assert "bogus" in str(exc_info.value)

    def test_undeclared_config_key_is_refused_at_update(self) -> None:
        """A key inside ``config`` that is not declared fails on update."""
        with pytest.raises(ValidationError) as exc_info:
            GraphUpdate.model_validate({"config": {"bogus": 1}})
        assert "bogus" in str(exc_info.value)

    def test_top_level_undeclared_key_is_still_refused(self) -> None:
        """The model-level forbid still governs the top level of the body."""
        with pytest.raises(ValidationError) as exc_info:
            GraphCreate.model_validate({**VALID_GRAPH_CREATE, "bogus_top": 1})
        assert "bogus_top" in str(exc_info.value)

    async def test_unknown_nested_key_is_refused_through_the_route(
        self, authenticated_client: AsyncClient
    ) -> None:
        """The nested refusal reaches the HTTP boundary as a 422."""
        response = await authenticated_client.post(
            "/graphs/",
            json={**VALID_GRAPH_CREATE, "config": {"bogus": 1}},
        )
        assert response.status_code == 422
        assert response.json()["code"] == ErrorCode.VALIDATION_ERROR.value

