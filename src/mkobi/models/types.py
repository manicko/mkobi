"""Concrete types to replace Any.

Contains TypedDict and Pydantic models for typing structures
that previously used dict[str, Any] or Any.
"""

from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field

from mkobi.models.enums import AggregationFunctionEnum, BarmodeEnum, OrientationEnum, YoyModeEnum
from mkobi.models.transformation_configs import (
    AggregationConfig as TransformationAggregationConfig,
)
from mkobi.models.transformation_configs import (
    CustomMetricConfig,
    FilterConfig,
    ShareConfig,
    YoyConfig,
)


# ==================== Aggregated Data Types ====================


class DimensionData(TypedDict, total=False):
    """Dimension data for aggregated records."""

    year: int
    month: int
    category: str
    brand: str
    region: str
    # Additional fields may be present
    # depending on dashboard configuration


class MetricData(TypedDict, total=False):
    """Metric data for aggregated records."""

    value: float
    sum: float
    avg: float
    count: int
    min: float
    max: float
    # Additional metrics


class AggregatedRecordModel(BaseModel):
    """Pydantic model for aggregated data record."""

    dims: dict[str, int | float | str] = Field(default_factory=dict)
    metrics: dict[str, int | float | str] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


# ==================== Filter Types ====================


class FilterCondition(TypedDict):
    """Data filter condition."""

    field: str
    operator: str  # ">=", "<=", "==", "!=", ">", "<"
    value: int | str | float


class ChartFilterConfig(TypedDict):
    """Filter configuration for chart."""

    year: int | None
    category: str | None
    brand: str | None
    region: str | None
    filters: dict[str, list[str | int]]  # Additional filters


# ==================== Transformation Types ====================


class TransformationConfig(TypedDict):
    """Data transformation configuration."""

    type: str  # "filter", "map", "derive", etc.
    condition: dict[str, dict[str, int | float | str]]  # Example: {"year": {"$gte": 2020}}


class AggregationConfig(TypedDict):
    """Aggregation configuration."""

    type: str  # "sum", "avg", "count", "min", "max"
    field: str


class ProcessingConfigData(TypedDict):
    """Data processing configuration."""

    transformations: list[TransformationConfig] | None
    aggregations: list[AggregationConfig] | None
    groupby: list[str] | None
    filters: list[FilterCondition] | None
    metrics: list[dict[str, str]] | None  # {"name": "...", "type": "...", "field": "..."}


# ==================== Graph Config Types ====================


class AxisConfig(TypedDict, total=False):
    """Chart axis configuration."""

    title: str
    label: str
    range: list[float] | None
    type: str | None  # "linear", "log", "date", etc.


class ChartLayoutConfig(TypedDict, total=False):
    """Chart layout configuration."""

    title: str
    xaxis: AxisConfig | None
    yaxis: AxisConfig | None
    showlegend: bool
    height: int
    width: int
    template: str | None


class YoYConfig(TypedDict, total=False):
    """Year-over-year comparison settings."""

    enabled: bool
    metric: str
    mode: YoyModeEnum  # YoyModeEnum.PERCENT or YoyModeEnum.ABSOLUTE
    year_field: str


class SortConfig(TypedDict, total=False):
    """Sorting configuration for chart axes."""

    by: str  # Dimension or metric column to sort by
    direction: str  # "asc" or "desc"


class GraphConfigDict(TypedDict, total=False):
    """Declared vocabulary of a graph's ``config`` field.

    This ``TypedDict`` is the write-boundary contract for ``config``: it is the
    set ``_DECLARED_GRAPH_CONFIG_KEYS`` refuses against, and it governs both
    ``GraphCreate`` and ``GraphUpdate``. The two readers of these keys today are
    ``services/aggregation_service.py`` (``x``, ``color``) and the client's
    ``ChartRenderer.tsx`` (``x``, ``color``, ``metrics``, ``orientation``,
    ``barmode``).

    The contract keys are ``x, y, color, metrics, orientation, barmode, title,
    showlegend``. ``x``, ``color``, ``metrics``, ``orientation`` and ``barmode``
    are read by ``ChartRenderer`` as named above. ``y`` names the metric column
    the renderer's ``config.metrics?.[0] ?? 'y'`` fallback falls back to.
    ``title`` and ``showlegend`` are the config-level twins of
    ``ChartLayoutConfig.title`` / ``ChartLayoutConfig.showlegend``, which the
    renderer reads off the response's ``layout`` field; populating that field is
    residual block ``R2``.

    RESERVED (adjudication ``D-16-1``): ``yoy``, ``secondary_y``, ``xaxis``,
    ``yaxis``, ``layout``, ``sort_x``, ``sort_color``. These keys are declared,
    validated at the request boundary, stored and returned on read, but read by
    nothing in ``src/`` or ``frontend/src/`` today. By that ruling they are
    deliberately neither deleted nor silently ignored. ``xaxis`` and ``layout``
    are owned by residual block ``R2``; the rest have no consumer yet.

    ``GraphConfigModel`` (below) mirrors this vocabulary; when one gains a key
    the other must too.
    """

    x: str | None
    y: str | None
    color: str | None
    # Metric column names for the client's trace builder; the dev seeder also
    # stores this key, so it must be declared for the read path to round-trip.
    metrics: list[str] | None
    # Bar trace orientation ("v"/"h") and bar grouping mode.
    orientation: OrientationEnum | None
    barmode: BarmodeEnum | None
    # Legend visibility at the config level (the layout twin lives on
    # ``ChartLayoutConfig.showlegend``).
    showlegend: bool | None
    xaxis: AxisConfig | None  # RESERVED: owned by R2
    yaxis: AxisConfig | None  # RESERVED: no consumer yet
    title: str | None
    layout: ChartLayoutConfig | None  # RESERVED: owned by R2
    yoy: YoYConfig | None  # RESERVED: no consumer yet
    secondary_y: list[str] | None  # RESERVED: no consumer yet
    # Sorting configuration
    sort_x: SortConfig | None  # RESERVED: no consumer yet. Sorts x-axis values.
    sort_color: SortConfig | None  # RESERVED: no consumer yet. Sorts color values.


# ==================== Filter Config Types ====================


class FilterConfigDict(TypedDict, total=False):
    """Filter configuration (config field)."""

    field: str  # Field for filtering
    source: str  # "dims", "metrics", "custom"
    multi: bool  # Multiple selection
    type: str | None  # Input type ("select", "multiselect", "range", "date")
    options: list[str | int] | None  # Available options
    default: str | int | list[str | int] | None


# ==================== Processing Settings Types ====================


# ==================== Auth Token Types ====================


class TokenData(TypedDict):
    """JWT token data."""

    user_id: str
    email: str
    role: str
    exp: int | None


class LoginResponse(TypedDict):
    """Response on successful login."""

    access_token: str
    token_type: str
    expires_in: int | None


# ==================== Metadata Types ====================


class ChartMetadata(TypedDict, total=False):
    """Chart metadata."""

    graph_id: str
    graph_name: str
    count: int
    total: float | None


class ProcessingResultData(TypedDict, total=False):
    """Processing result data."""

    columns: list[str]
    rows: int
    dashboard_id: int
    preview: list[dict[str, int | float | str]] | None


# ==================== Pydantic Models for Runtime Validation ====================


class DimensionModel(BaseModel):
    """Pydantic model for dimensions."""

    year: int | None = None
    month: int | None = None
    category: str | None = None
    brand: str | None = None
    region: str | None = None

    model_config = {"extra": "allow"}


class MetricModel(BaseModel):
    """Pydantic model for metrics."""

    value: float | None = None
    sum: float | None = None
    avg: float | None = None
    count: int | None = None
    min: float | None = None
    max: float | None = None

    model_config = {"extra": "allow"}


class GraphConfigModel(BaseModel):
    """Pydantic model for chart configuration.

    Mirrors the declared vocabulary of :class:`GraphConfigDict` **including its
    RESERVED classification**; see that class for the statement. Kept in step
    with it so a runtime consumer of this model sees the same keys the request
    boundary accepts.
    """

    x: str | None = None
    y: str | None = None
    color: str | None = None
    metrics: list[str] | None = None
    orientation: OrientationEnum | None = None
    barmode: BarmodeEnum | None = None
    showlegend: bool | None = None
    xaxis: AxisConfig | None = None
    yaxis: AxisConfig | None = None
    title: str | None = None
    layout: ChartLayoutConfig | None = None
    yoy: YoYConfig | None = None
    secondary_y: list[str] | None = None
    # Sorting configuration
    sort_x: SortConfig | None = None
    sort_color: SortConfig | None = None

    model_config = {"extra": "allow"}


class FilterConfigModel(BaseModel):
    """Pydantic model for filter configuration."""

    field: str | None = None
    source: str | None = None
    multi: bool = False
    type: str | None = None
    options: list[str | int] | None = None
    default: str | int | list[str | int] | None = None

    model_config = {"extra": "allow"}


class ProcessingSettingsModel(BaseModel):
    """Pydantic model for processing settings.

    The single, strict settings boundary. It declares all **nineteen** keys the
    worker reads, so an unknown key is rejected at the request boundary instead
    of being silently dropped.

    Read directly by ``workers/data_worker.py::_run_with_transaction``:
    ``separator``, ``encoding``, ``column_types``, ``required_columns``,
    ``decimal_separator``, ``date_format``, ``renames``, ``computed_fields``,
    ``metric_agg``.

    Reached through ``ProcessingConfig(**processing_config_dict)``:
    ``filters``, ``groupby``, ``aggregations``, ``sort_by``, ``descending``,
    ``limit``, ``yoy_config``, ``share_config``, ``custom_metrics``, ``metrics``.

    ``loader``, ``date_column`` and ``timezone`` are read by nothing in ``src/``;
    they are kept because the dev seeder writes ``date_column`` and stored
    payloads may carry them. No default is given to ``timezone``, ``encoding``
    or ``separator``: a default the stored column never had would make a read
    model assert something the database does not say.
    """

    # CSV parsing (worker read)
    separator: str | None = None
    encoding: str | None = None
    column_types: dict[str, str] | None = None
    required_columns: list[str] | None = None
    decimal_separator: str | None = None
    date_format: str | None = None

    # Frame reshaping (worker read)
    renames: dict[str, str] | None = None
    computed_fields: list[CustomMetricConfig] | None = None

    # Aggregation defaults (worker read)
    metric_agg: AggregationFunctionEnum | None = None

    # Transformations (reached via ProcessingConfig)
    filters: list[FilterConfig] | None = None
    groupby: list[str] | None = None
    aggregations: list[TransformationAggregationConfig] | None = None
    sort_by: list[str] | None = None
    descending: bool | None = None
    limit: int | None = None
    yoy_config: YoyConfig | None = None
    share_config: ShareConfig | None = None
    custom_metrics: list[CustomMetricConfig] | None = None
    metrics: list[dict[str, str]] | None = None

    # Declared but read by nothing in src/ (kept for the seeder's stored shape)
    loader: str | None = None
    date_column: str | None = None
    timezone: str | None = None

    model_config = ConfigDict(extra="forbid")



