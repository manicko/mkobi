from typing import Annotated, Any
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator
import json
from datetime import datetime
from uuid import UUID

from mkobi.models.enums import ErrorCode, FileExtensionEnum, GraphType, BarmodeEnum, OrientationEnum, ProcessingStatus
from mkobi.models.transformation_configs import (
    AggregationConfig,
    CustomMetricConfig,
    FilterConfig,
    ShareConfig,
    YoyConfig,
)
from mkobi.models.types import (
    AggregatedRecordModel,
    ChartMetadata,
    ChartLayoutConfig,
    ProcessingResultData,
)

__all__ = [
    "DataUpload",
    "UploadResponse",
    "ProcessingStatusResponse",
    "ProcessingConfig",
    "ProcessingResult",
    "AggregatedData",
    "DataFilter",
    "ChartDataRequest",
    "LoaderConfig",
    "ValidationResult",
    "ChartData",
    "ChartConfig",
    "FilterState",
    "ProcessingResultData",
    "AggregatedFiltersRequest",
    "MAX_FILTER_KEYS",
    "MAX_FILTER_KEY_LENGTH",
    "MAX_FILTER_VALUE_LENGTH",
    "MAX_FILTER_PAYLOAD_BYTES",
    "GraphDataResponse",
    "AggregatedDataResponse",
    "FilterValuesResponse",
    "ClientErrorPayload",
    "MAX_CLIENT_ERROR_FIELD_LENGTH",
    "MAX_CLIENT_ERROR_BODY_BYTES",
    "CLIENT_ERROR_STACKED_FIELD_NAMES",
]

# Bound for every string value accepted by ClientErrorPayload, including the
# values nested in its ``error`` object. Anonymous callers reach this endpoint,
# and every accepted value is written to a log line, so the model declares a
# ceiling here while the route truncates the parsed values before logging.
MAX_CLIENT_ERROR_FIELD_LENGTH = 32768

# Declared-length ceiling for the whole inbound body (DP-11, option (c)): a
# body that announces a Content-Length above this is refused before parsing.
# A chunked request declares no length and is instead held by the parsed-value
# bounds above.
MAX_CLIENT_ERROR_BODY_BYTES = 262144

# The three fields the one first-party caller (``ErrorBoundary.tsx``) actually
# sends inside ``error``. ``stack`` is the largest unbounded string in a React
# error report; the route truncates all three on the parsed value.
CLIENT_ERROR_STACKED_FIELD_NAMES = ("name", "message", "stack")


def _truncate_client_error_value(value: Any) -> Any:
    """Truncate an over-long client error string to the declared ceiling.

    Applied as a ``BeforeValidator`` so the ceiling is enforced by truncation
    rather than rejection: ``max_length`` alone would answer ``422`` for an
    over-long value, and the sole caller swallows that failure silently.
    """
    if isinstance(value, str) and len(value) > MAX_CLIENT_ERROR_FIELD_LENGTH:
        return value[:MAX_CLIENT_ERROR_FIELD_LENGTH]
    return value


# A bounded client-error string: truncate on the parsed value, then assert the
# declared ``max_length`` (which the truncation has already satisfied).
BoundedClientErrorStr = Annotated[
    str,
    BeforeValidator(_truncate_client_error_value),
    Field(max_length=MAX_CLIENT_ERROR_FIELD_LENGTH),
]


class DataUpload(BaseModel):
    """Model for data upload."""

    file: bytes
    filename: str
    dashboard_id: UUID

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "filename": "data.csv.gz",
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        },
    )


class UploadResponse(BaseModel):
    """Model for upload response."""

    task_id: UUID
    filename: str
    dashboard_id: UUID
    status: ProcessingStatus
    message: str
    uploaded_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "data.csv.gz",
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "uploaded",
                "message": "File uploaded successfully",
                "uploaded_at": "2026-04-24T16:02:46+03:00",
            }
        },
    )


class ProcessingStatusResponse(BaseModel):
    """Model for processing status.

    ``filename`` carries a deliberate, narrow contract. Under ruling
    **D-06-A = (b)** an accepted upload's artefact is *scratch space*: the
    worker removes it on every terminal state (COMPLETED/FAILED), so no durable
    filename or path exists anywhere and ``ProcessingLog`` stores none. This
    field is therefore **display-only** best-effort text derived from the
    processing log's ``message`` column (see ``DataService.get_processing_status``
    and ``DataService.get_processing_result``); it names no artefact on disk and
    **no code may use it to open or locate a file**. It is kept, with its name
    and ``str`` type unchanged, purely for wire compatibility with existing
    clients, which have always received a string here.
    """

    task_id: UUID
    filename: str
    dashboard_id: UUID
    status: ProcessingStatus
    progress: int = Field(0, ge=0, le=100)
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # Error code for RFC 7807 compliant error reporting when processing fails
    error_code: ErrorCode | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "data.csv.gz",
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "processing",
                "progress": 50,
                "message": "Processing data...",
                "started_at": "2026-04-24T16:02:46+03:00",
                "finished_at": None,
            }
        },
    )


class ProcessingConfig(BaseModel):
    """Model for processing configuration."""

    filters: list[FilterConfig] | None = None
    groupby: list[str] | None = None
    aggregations: list[AggregationConfig] | None = None
    sort_by: list[str] | None = None
    descending: bool = False
    limit: int | None = None
    yoy_config: YoyConfig | None = None
    share_config: ShareConfig | None = None
    custom_metrics: list[CustomMetricConfig] | None = None
    metrics: list[dict[str, str]] | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "filters": [
                    {"column": "year", "operator": ">=", "value": 2020}
                ],
                "groupby": ["category", "region"],
                "aggregations": [
                    {"column": "revenue", "function": "sum", "alias": "total_revenue"}
                ],
                "sort_by": ["year"],
                "descending": False,
                "yoy_config": {
                    "year_column": "year",
                    "value_column": "revenue_sum",
                },
                "share_config": {
                    "value_column": "revenue_sum",
                },
                "custom_metrics": [
                    {"name": "profit", "formula": "revenue - cost"}
                ],
            }
        },
    )


class ProcessingResult(BaseModel):
    """Model for processing result."""

    success: bool
    task_id: UUID
    dashboard_id: UUID
    rows_processed: int
    message: str
    data: ProcessingResultData | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "success": True,
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
                "rows_processed": 1000,
                "message": "Data processed successfully",
                "data": {"columns": ["category", "revenue"], "rows": 50},
            }
        },
    )


class AggregatedData(BaseModel):
    """Model for aggregated data for dashboard."""

    dashboard_id: UUID
    chart_type: GraphType
    data: list[AggregatedRecordModel]
    metadata: ChartMetadata | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
                "chart_type": "bar",
                "data": [
                    {"dims": {"category": "A"}, "metrics": {"revenue": 1000}},
                    {"dims": {"category": "B"}, "metrics": {"revenue": 2000}},
                ],
                "metadata": {"total": 3000, "count": 2},
            }
        },
    )


class DataFilter(BaseModel):
    """Model for filtering aggregated data.

    Used to filter data by year, category, brand and other parameters.
    """

    dashboard_id: UUID
    filters: dict[str, Any] | None = None
    year: int | None = None
    category: str | None = None
    brand: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
                "year": 2023,
                "category": "Electronics",
                "brand": "Brand A",
                "filters": {
                    "region": "North",
                    "status": "active",
                },
            }
        },
    )


class ChartDataRequest(BaseModel):
    """Model for requesting data for specific charts.

    Used to get data only for specified charts of the dashboard.
    """

    dashboard_id: UUID
    chart_ids: list[UUID] | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "dashboard_id": "550e8400-e29b-41d4-a716-446655440000",
                "chart_ids": [
                    "550e8400-e29b-41d4-a716-446655440001",
                    "550e8400-e29b-41d4-a716-446655440002",
                ],
            }
        },
    )


class LoaderConfig(BaseModel):
    """Configuration for CSV data loader.

    Used to configure data loading and validation parameters.
    """

    required_columns: list[str] = Field(
        default_factory=list,
        description="List of required columns",
    )
    column_types: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping columns to expected data types",
    )
    strict_schema: bool = Field(
        default=False,
        description="Whether to check strict schema compliance",
    )
    max_file_size: int = Field(
        default=100 * 1024 * 1024,
        description="Maximum file size in bytes",
        ge=1,
        le=1024 * 1024 * 1024,  # 1GB max
    )
    allowed_file_types: list[FileExtensionEnum] = Field(
        default_factory=lambda: [FileExtensionEnum.CSV, FileExtensionEnum.CSV_GZ],
        description="Allowed file types",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "required_columns": ["date", "category", "revenue"],
                "column_types": {
                    "date": "date",
                    "revenue": "float",
                    "category": "str",
                },
                "strict_schema": False,
                "max_file_size": 104857600,
                "allowed_file_types": [".csv", ".csv.gz"],
            }
        },
    )


class ValidationResult(BaseModel):
    """Validation result for data.

    Contains information about whether data passed validation,
    as well as list of errors and warnings.
    """

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    column_count: int = Field(ge=0)
    columns: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "is_valid": True,
                "errors": [],
                "warnings": ["Found 5 null values in column 'category'"],
                "row_count": 1000,
                "column_count": 5,
                "columns": ["date", "category", "revenue", "region", "brand"],
            }
        },
    )


class ChartData(BaseModel):
    """Model for chart data.

    Contains list of dictionaries with data, where each dictionary
    represents one data point with dimensions and metrics.
    """

    data: list[dict[str, int | float | str]]

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "data": [
                    {"category": "A", "revenue": 1000, "year": 2023},
                    {"category": "B", "revenue": 2000, "year": 2023},
                ]
            }
        },
    )


class ChartConfig(BaseModel):
    """Model for chart configuration.

    Defines visualization parameters: axes, colors, display modes
    and additional layout settings.
    """

    x: str
    color: str | None = None
    metrics: list[str]
    orientation: OrientationEnum = OrientationEnum.VERTICAL
    barmode: BarmodeEnum = BarmodeEnum.GROUP
    secondary_y: list[str] = Field(default_factory=list)
    layout: ChartLayoutConfig | None = Field(default=None)
    yoy: YoyConfig | None = Field(
        default=None,
        description="Year-over-year comparison settings",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "x": "category",
                "color": "year",
                "metrics": ["revenue", "sales"],
                "orientation": "v",
                "barmode": "group",
                "secondary_y": ["profit"],
                "layout": {"title": "Sales by Category"},
                "yoy": {
                    "enabled": True,
                    "metric": "revenue",
                    "mode": "percent",
                    "year_field": "year",
                },
            }
        },
    )


class FilterState(BaseModel):
    """Model for dashboard filter state.

    Stores current filter values as a dictionary,
    where key is filter name, value is list of selected values.
    """

    filters: dict[str, list[int | str]] = Field(default_factory=dict)

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "filters": {
                    "year": [2023, 2024],
                    "category": ["Electronics"],
                    "region": ["North", "South"],
                }
            }
        },
    )


# ==================== Filter Payload Bounds (PRF-5) ====================

# The ``filters`` query-string parameter is a JSON-encoded object whose keys
# become one ``->>`` equality each in the aggregate query. Nothing previously
# bounded its width, so any caller could make the planner build an arbitrarily
# large predicate set. Phase-1 measurement (authoritative) found that execution
# time stays in a 16.4--33.1 ms band regardless of key count while *planning*
# time grows from 0.889 ms at K=0 to 37.971 ms at K=1000 (43x). The bound below
# is therefore about the plan, not the scan.
#
# Derivation: the edge applies nginx's default 8 KB request-line limit, and no
# ``large_client_header_buffers`` directive exists repository-wide, so a payload
# that reaches the application is already under roughly 8 KB. 20 keys with
# realistic key/value lengths sit comfortably inside that ceiling while holding
# planning time to roughly 1.6 ms instead of the 38 ms a thousand keys produce.
MAX_FILTER_KEYS = 20
MAX_FILTER_KEY_LENGTH = 64
MAX_FILTER_VALUE_LENGTH = 256
MAX_FILTER_PAYLOAD_BYTES = 4096


class AggregatedFiltersRequest(BaseModel):
    """Validated ``filters`` payload for the aggregated data endpoint.

    Keys are dimension names compared with ``->>`` equality; values are coerced
    to text by the repository. Four bounds apply (``PRF-5``): a maximum key
    count, a maximum key-name length, a maximum value length, and a maximum
    serialised payload size. See ``MAX_FILTER_*`` for the derivation.

    The enforced limits reject with a Pydantic ``ValidationError``, which the
    route maps to the same RFC 7807 ``VALIDATION_ERROR`` as malformed JSON.
    """

    filters: dict[str, str | int | float | bool]

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "filters": {
                    "year": 2023,
                    "category": "Electronics",
                }
            }
        },
    )

    @field_validator("filters")
    @classmethod
    def validate_filter_bounds(
        cls, v: dict[str, str | int | float | bool]
    ) -> dict[str, str | int | float | bool]:
        """Enforce key-count, key-length, value-length and payload-size bounds."""
        if len(v) > MAX_FILTER_KEYS:
            raise ValueError(
                f"filters accepts at most {MAX_FILTER_KEYS} keys, got {len(v)}"
            )
        for key, value in v.items():
            if len(key) > MAX_FILTER_KEY_LENGTH:
                raise ValueError(
                    f"filter key names accept at most {MAX_FILTER_KEY_LENGTH} "
                    f"characters, got {len(key)}"
                )
            if len(str(value)) > MAX_FILTER_VALUE_LENGTH:
                raise ValueError(
                    f"filter values accept at most {MAX_FILTER_VALUE_LENGTH} "
                    f"characters, got {len(str(value))}"
                )
        serialised = json.dumps(v)
        if len(serialised.encode("utf-8")) > MAX_FILTER_PAYLOAD_BYTES:
            raise ValueError(
                f"filters payload accepts at most {MAX_FILTER_PAYLOAD_BYTES} "
                f"bytes, got {len(serialised.encode('utf-8'))}"
            )
        return v

    @property
    def parsed(self) -> dict[str, Any]:
        """Return the filters as a plain mapping for the repository."""
        return dict(self.filters)


# ==================== Aggregated Data Response Types ====================

class GraphDataResponse(BaseModel):
    """Model for individual graph data response.

    Contains the graph metadata (id, type, name) and Plotly.js data.

    ``total_rows`` is the graph's **true, untruncated** row count, reported
    from a ``COUNT(*)`` query rather than the length of the (possibly bounded)
    ``data`` list. ``DP-11-B`` makes it mandatory: without it, a bounded
    response would silently drop rows.

    ``returned_rows`` is the server-supplied count of rows actually placed in
    ``data``. ``DP-13-C`` requires the displayed lower bound to come from the
    server, never from a client-side count of the array: a client that filters,
    slices or otherwise transforms ``data`` before rendering would otherwise
    show a number that silently stops describing what the server sent.

    ``rows_truncated`` is true exactly when ``data`` is shorter than
    ``total_rows``.
    """

    graph_id: str
    type: GraphType
    name: str
    data: list[dict[str, int | float | str]]
    returned_rows: int
    total_rows: int
    rows_truncated: bool = False
    layout: ChartLayoutConfig | None = None
    config: dict[str, Any] | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "graph_id": "550e8400-e29b-41d4-a716-446655440000",
                "type": "bar",
                "name": "Sales by Category",
                "data": [
                    {"category": "A", "revenue": 1000},
                    {"category": "B", "revenue": 2000},
                ],
                "returned_rows": 2,
                "total_rows": 2000,
                "rows_truncated": True,
                "layout": {"title": "Sales Chart"},
            }
        },
    )


class AggregatedDataResponse(BaseModel):
    """Model for aggregated data response.

    Wrapper for graph data with configuration.

    ``total_rows`` is the dashboard-wide **true, untruncated** row count, on
    both the dashboard response and the single-graph response; the per-graph
    count is carried separately on each ``GraphDataResponse.total_rows``. The
    response is marked ``truncated`` when any graph was bounded by the
    per-graph cap or the rows collectively exhausted the dashboard-wide budget;
    a graph whose rows were not returned at all still appears, carrying its
    counts and an empty ``data`` list.
    """

    graphs: list[GraphDataResponse]
    total_rows: int
    truncated: bool = False

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "graphs": [
                    {
                        "graph_id": "550e8400-e29b-41d4-a716-446655440000",
                        "type": "bar",
                        "name": "Sales by Category",
                        "data": [
                            {"category": "A", "revenue": 1000},
                            {"category": "B", "revenue": 2000},
                        ],
                        "returned_rows": 2,
                        "total_rows": 2000,
                        "rows_truncated": True,
                    }
                ],
                "total_rows": 2000,
                "truncated": True,
            }
        },
    )


class FilterValuesResponse(BaseModel):
    """Model for filter values response.

    Returned by the filter-values endpoint with distinct values
    for a specified dashboard filter.

    ``total_values`` is the **true, untruncated** distinct-value count, reported
    from a ``COUNT(*)`` query rather than the length of the (possibly bounded)
    ``values`` list, so a bounded response can report its truncation honestly
    (the same contract as the aggregate response's ``total_rows``).
    """

    filter_name: str
    values: list[str]
    total_values: int

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "filter_name": "category",
                "values": ["Electronics", "Clothing", "Food"],
                "total_values": 3,
            }
        },
    )


class ClientErrorPayload(BaseModel):
    """Payload model for client-side error reports.

    Used by the /client-errors endpoint to receive error details
    from the frontend for monitoring purposes.

    This model is submitted by an anonymous caller and every value it carries is
    written to a log line, so each declared string is bounded here. The bounds
    are truncation ceilings, not rejection rules: the sole first-party caller
    (``ErrorBoundary.tsx``) must keep reporting, and a rejection would be
    swallowed by its ``.catch(() => {})``. ``error`` is a free-form
    ``dict[str, Any]`` — a ``max_length`` here would bound the *key count* and
    not the values, so the values inside it (``name``, ``message``,
    ``stack``) are bounded where they are read and truncated by the route.
    """

    error: dict[str, Any]
    componentStack: BoundedClientErrorStr | None = None
    url: BoundedClientErrorStr
    userAgent: BoundedClientErrorStr
    timestamp: BoundedClientErrorStr

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "error": {"message": "Cannot read property 'x' of undefined", "name": "TypeError"},
                "componentStack": "in ChartRenderer (ChartRenderer.tsx:45)",
                "url": "https://app.example.com/dashboard/123",
                "userAgent": "Mozilla/5.0...",
                "timestamp": "2026-06-08T12:34:56.789Z",
            }
        },
    )
