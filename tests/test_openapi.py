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
