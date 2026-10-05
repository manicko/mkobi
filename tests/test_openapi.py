"""OpenAPI schema verification tests.

Verifies that error response schemas are properly documented in the OpenAPI spec.
"""

from typing import Any

from mkobi.models.error_response import ErrorResponse


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


class TestOpenAPIErrorSchemas:
    """Verify OpenAPI schema contains proper error response documentation."""

    def test_error_response_model_exists(self) -> None:
        """ErrorResponse model should be properly defined."""
        assert ErrorResponse is not None

        # Verify required fields per RFC 7807
        fields = ErrorResponse.model_fields
        required_fields = ["type", "title", "status", "detail", "code"]
        for field in required_fields:
            assert field in fields, f"ErrorResponse should have '{field}' field"

    def test_error_response_optional_details(self) -> None:
        """ErrorResponse should have optional details field for additional context."""
        fields = ErrorResponse.model_fields
        assert "details" in fields, "ErrorResponse should have 'details' field"
        assert not fields["details"].is_required(), "'details' should be optional"

    def test_error_response_model_schema_generation(self) -> None:
        """ErrorResponse model should generate valid OpenAPI schema."""
        schema = ErrorResponse.model_json_schema()

        # Verify schema has all required properties
        properties = schema.get("properties", {})
        required_fields = ["type", "title", "status", "detail", "code"]
        for field in required_fields:
            assert field in properties, f"ErrorResponse schema should have '{field}' property"


class TestProcessingSettingsBoundaryOpenAPI:
    """The settings boundary is visible in the generated OpenAPI document.

    DP-014: ``ProcessingConfigUpdate.settings`` is ``ProcessingSettingsModel``
    with ``extra="forbid"``. Only a ``BaseModel`` emits
    ``additionalProperties: false``; the retired ``TypedDict`` emitted none, so
    this tripwire is satisfiable only after the boundary type change.
    """

    def test_put_request_body_forbids_unknown_settings_keys(self) -> None:
        """The PUT settings object forbids extra keys over the twenty-two declared."""
        from mkobi.main import app

        from tests.test_processing_config_boundary import DECLARED_SETTINGS_KEYS

        schema = app.openapi()
        put_path = next(
            path
            for path in schema["paths"]
            if path.endswith("/processing-configs/{dashboard_id}")
        )
        put = schema["paths"][put_path]["put"]
        request_schema = put["requestBody"]["content"]["application/json"]["schema"]
        resolved = _resolve_ref(schema, request_schema)
        settings_schema = _resolve_ref(schema, resolved["properties"]["settings"])

        assert settings_schema.get("additionalProperties") is False
        assert set(settings_schema["properties"]) == DECLARED_SETTINGS_KEYS


class TestProcessingStatusResponseWireShape:
    """``ProcessingStatusResponse.filename`` stays wire-compatible.

    FAB-3 / ART-002 removed the false claim that the record names an artefact,
    but it must not change the published shape. The field's **name and type are
    unchanged**: it is still a required JSON ``string``. This asserts that
    against the generated OpenAPI document rather than assuming it, because a
    rename, a type change, or an emitted ``null`` would be a breaking change for
    the frontend that consumes the payload.
    """

    def test_filename_is_a_required_string_in_the_published_schema(self) -> None:
        """The field is still named ``filename`` and still requires a ``str``."""
        from mkobi.main import app
        from mkobi.models.data import ProcessingStatusResponse

        # Model-level contract: required, and typed `str` (not `str | None`).
        field = ProcessingStatusResponse.model_fields["filename"]
        assert field.is_required(), "filename must stay a required field"
        assert field.annotation is str, (
            f"filename annotation changed from str to {field.annotation!r}"
        )

        # Document-level contract: the schema property is a plain string.
        schema = app.openapi()
        component = schema["components"]["schemas"]["ProcessingStatusResponse"]
        filename_schema = component["properties"]["filename"]
        assert filename_schema.get("type") == "string"
        assert "filename" in component["required"]


class TestAccessGrantPermissionIsAnEnumReference:
    """``AccessGrant.permission`` publishes the native enum in the OpenAPI document.

    Before this block the field was a bare ``str`` and the published schema was
    ``{"default": "view", "title": "Permission", "type": "string"}``. Now it is a
    ``$ref`` to the ``DashboardPermission`` component, whose ``enum`` lists the
    three admissible values, so a generated client sees the vocabulary.
    """

    def test_permission_property_is_a_reference_to_dashboard_permission(self) -> None:
        """The field resolves to the ``DashboardPermission`` enum schema."""
        from mkobi.main import app

        schema = app.openapi()
        component = schema["components"]["schemas"]["AccessGrant"]
        permission_schema = component["properties"]["permission"]

        assert (
            permission_schema.get("$ref")
            == "#/components/schemas/DashboardPermission"
        )

        resolved = _resolve_ref(schema, permission_schema)
        assert resolved.get("enum") == ["view", "edit", "admin"]


class TestAggregatedDataResponseCarriesTruncationContract:
    """The bounded aggregate response publishes its count/truncation contract.

    ``DP-11-B`` makes the count field **mandatory**: a bounded response that
    does not report the true totals is a silent truncation, which is rejected.
    This pins the contract in the generated OpenAPI document, so removing or
    renaming ``GraphDataResponse.total_rows``, or dropping the response's
    ``total_rows``/``truncated`` declaration, fails here rather than only at a
    client that no longer sees the counts. It asserts the published shape, not
    an implementation detail.
    """

    def test_graph_response_requires_a_true_row_count(self) -> None:
        """``GraphDataResponse.total_rows`` is a required integer property."""
        from mkobi.main import app
        from mkobi.models.data import GraphDataResponse

        field = GraphDataResponse.model_fields["total_rows"]
        assert field.is_required(), "total_rows must stay a required field"
        assert field.annotation is int, (
            f"total_rows annotation changed from int to {field.annotation!r}"
        )

        schema = app.openapi()
        component = schema["components"]["schemas"]["GraphDataResponse"]
        total_rows_schema = component["properties"]["total_rows"]
        assert total_rows_schema.get("type") == "integer"
        assert "total_rows" in component["required"]
        assert "rows_truncated" in component["properties"]

    def test_graph_response_declares_a_server_supplied_returned_count(self) -> None:
        """``GraphDataResponse.returned_rows`` is a required integer property.

        ``DP-13-C``: the displayed lower bound of "Showing N of M" must come
        from the server, not from a client-side count of ``data``. This pins
        the field in the published schema so the server signal cannot be
        removed without failing here.
        """
        from mkobi.main import app
        from mkobi.models.data import GraphDataResponse

        field = GraphDataResponse.model_fields["returned_rows"]
        assert field.is_required(), "returned_rows must stay a required field"
        assert field.annotation is int, (
            f"returned_rows annotation changed from int to {field.annotation!r}"
        )

        schema = app.openapi()
        component = schema["components"]["schemas"]["GraphDataResponse"]
        returned_schema = component["properties"]["returned_rows"]
        assert returned_schema.get("type") == "integer"
        assert "returned_rows" in component["required"]

    def test_aggregated_response_declares_a_total_and_truncation_flag(self) -> None:
        """``AggregatedDataResponse`` declares ``total_rows`` and ``truncated``."""
        from mkobi.main import app
        from mkobi.models.data import AggregatedDataResponse

        total_field = AggregatedDataResponse.model_fields["total_rows"]
        assert total_field.is_required(), "total_rows must stay a required field"
        assert total_field.annotation is int
        assert "truncated" in AggregatedDataResponse.model_fields

        schema = app.openapi()
        component = schema["components"]["schemas"]["AggregatedDataResponse"]
        assert component["properties"]["total_rows"].get("type") == "integer"
        assert "total_rows" in component["required"]
        assert component["properties"]["truncated"].get("type") == "boolean"


class TestGraphDataResponseDeclaresServedRowKeys:
    """R3 / ``CHTB-2``: the served row-key lists are published as optional arrays.

    ``GraphDataResponse.metrics`` / ``.dimensions`` name the measure and
    dimension keys actually present on the served rows. They are additive and
    optional -- a graph with no served rows carries ``[]`` -- so this pins both
    the Python declaration and the published OpenAPI shape, and that the two
    names stay out of the ``required`` list.
    """

    def test_served_row_keys_are_published_as_optional_string_arrays(self) -> None:
        """``metrics`` / ``dimensions`` are optional ``list[str]`` on the wire."""
        from mkobi.main import app
        from mkobi.models.data import GraphDataResponse

        for name in ("metrics", "dimensions"):
            field = GraphDataResponse.model_fields[name]
            assert field.annotation == list[str], (
                f"{name} annotation changed from list[str] to {field.annotation!r}"
            )
            assert not field.is_required(), f"{name} must stay an optional field"

        schema = app.openapi()
        component = schema["components"]["schemas"]["GraphDataResponse"]
        for name in ("metrics", "dimensions"):
            prop = component["properties"][name]
            assert prop["type"] == "array"
            assert prop["items"] == {"type": "string"}
            assert name not in component["required"], (
                f"{name} must not be published as required"
            )


class TestAggregatedFiltersRequestValidatesListValues:
    """The widened ``filters`` payload schema validates a string-array branch.

    The union admits ``list[str]`` so a multiselect value can be evaluated as a
    membership test. This pins the schema as **additive**: the array branch is
    present and every previously-accepted scalar branch survives, so no existing
    client is invalidated.

    ``AggregatedFiltersRequest`` is built at runtime inside the route handler
    (``filters`` is a plain ``str`` query parameter), so it is **not** a
    component of the published OpenAPI document -- this asserts the model's own
    JSON Schema, which is what validates the payload, not a publication.
    """

    def test_filters_payload_schema_validates_a_string_array_branch(self) -> None:
        """``additionalProperties.anyOf`` carries the array and all scalar branches."""
        from mkobi.models.data import AggregatedFiltersRequest

        schema = AggregatedFiltersRequest.model_json_schema()
        any_of = schema["properties"]["filters"]["additionalProperties"]["anyOf"]

        # Order-independent: the scalar branches are compared as a set.
        scalar_types = {
            branch["type"] for branch in any_of if "items" not in branch
        }
        assert {"string", "integer", "number", "boolean"} <= scalar_types

        array_branches = [branch for branch in any_of if branch.get("type") == "array"]
        assert len(array_branches) == 1
        assert array_branches[0]["items"] == {"type": "string"}


class TestDocumentUrlsAreGatedTogether:
    """The three FastAPI document URLs share one production gate.

    ``create_app`` used to set ``docs_url`` and ``redoc_url`` to ``None`` in
    the production tier but left ``openapi_url`` unset, so FastAPI's default
    ``/openapi.json`` was served everywhere. This class asserts all three
    attributes together in both tiers: a test that checked only the two
    human-facing URLs would let the machine-readable one regress silently.

    In the shipped topology this gate has no effect — nginx proxies ``/api``
    and the health paths and serves the SPA for everything else, so the
    application is never asked for these paths (hand-over HO-4). It is defence
    in depth, not the production control.
    """

    def test_production_disables_all_three_document_urls(self, monkeypatch) -> None:
        """Production tier sets docs, redoc and openapi URLs to None.

        The production tier is selected by handing ``create_app`` a config whose
        environment is ``PRODUCTION``, rather than by building a full production
        settings object: the unrelated production credential/CORS guards would
        otherwise dominate this test's failure surface, which is the document
        URLs and nothing else.
        """
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("JWT__SECRET_KEY", "test_secret_key_change_in_production")

        import mkobi.app as app_module

        from mkobi.config import clear_config_cache, get_config
        from mkobi.models.enums import EnvironmentEnum

        clear_config_cache()
        production_config = get_config().model_copy(
            update={"environment": EnvironmentEnum.PRODUCTION}
        )
        monkeypatch.setattr(app_module, "get_config", lambda: production_config)

        application = app_module.create_app()

        assert application.docs_url is None
        assert application.redoc_url is None
        assert application.openapi_url is None

    def test_development_serves_all_three_document_urls(self, monkeypatch) -> None:
        """Development tier keeps the default /docs, /redoc and /openapi.json."""
        monkeypatch.setenv("ENV", "development")
        monkeypatch.setenv("JWT__SECRET_KEY", "test_secret_key_change_in_production")

        from mkobi.app import create_app
        from mkobi.config import clear_config_cache

        clear_config_cache()
        application = create_app()

        assert application.docs_url == "/docs"
        assert application.redoc_url == "/redoc"
        assert application.openapi_url == "/openapi.json"
