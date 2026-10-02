"""Aggregation service for per-chart Polars GROUP BY operations.

Provides data aggregation logic for dashboard graphs using Polars DataFrames.
Performs GROUP BY with graph dimensions and dashboard filter dimensions.
"""

import logging
from typing import Any

import polars as pl

from mkobi.data.processing.aggregate_transforms import AGG_FUNC_MAP
from mkobi.models.enums import AggregationFunctionEnum, ErrorCode
from mkobi.models.graph import GraphRead
from mkobi.models.filters import FilterRead
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)


def _resolve_metric_agg(metric_agg: AggregationFunctionEnum | str) -> AggregationFunctionEnum:
    """Normalise and validate an aggregation function name.

    Accepts either an :class:`AggregationFunctionEnum` member or the stored
    string. The string is normalised (``strip()`` + ``lower()``) and resolved
    against the enum. An unrecognised name **fails loudly** with
    :class:`AppException` and ``VALIDATION_ERROR`` rather than silently falling
    back to ``sum`` under the requested name (DP-018).

    Args:
        metric_agg: Aggregation function as an enum member or a string.

    Returns:
        The matching AggregationFunctionEnum member.

    Raises:
        AppException: If the name is not a member of AggregationFunctionEnum.
    """
    if isinstance(metric_agg, AggregationFunctionEnum):
        return metric_agg
    normalised = str(metric_agg).strip().lower()
    try:
        return AggregationFunctionEnum(normalised)
    except ValueError:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=f"Unsupported aggregation function: '{metric_agg}'",
        ) from None


def _coerce_dim_value(value: Any) -> str | int | float | bool:
    """Convert a Polars value to a JSON-safe native Python type.

    Preserves int, float, and bool as-is for correct sorting in the frontend.
    Converts date/datetime types to ISO format strings.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


class AggregationService:
    """Service for aggregating data for dashboard graphs.

    Performs per-chart GROUP BY aggregation using Polars.
    Each unique combination of dimensions becomes one row with aggregated metrics.
    """

    def __init__(self) -> None:
        """Initialize aggregation service."""
        logger.info("AggregationService initialized")

    async def aggregate_for_dashboard(
        self,
        df: pl.DataFrame,
        graphs: list[GraphRead],
        dashboard_filters: list[FilterRead],
        metric_agg: AggregationFunctionEnum | str = "sum",
    ) -> list[dict[str, Any]]:
        """Aggregate data for each graph in dashboard.

        Args:
            df: Polars DataFrame with source data.
            graphs: List of GraphRead models for the dashboard.
            dashboard_filters: List of FilterRead models for the dashboard.
            metric_agg: Aggregation function as an AggregationFunctionEnum
                member or its string value (default: "sum").

        Returns:
            List of dicts with {dashboard_id, graph_id, dims: {native types}, metrics: {}}.

        Raises:
            AppException: If ``metric_agg`` is not a recognised function.
        """
        agg_enum = _resolve_metric_agg(metric_agg)
        agg_name = agg_enum.value
        dashboard_filter_dim_names = [f.name for f in dashboard_filters]
        results: list[dict[str, Any]] = []

        for graph in graphs:
            # Collect columns for GROUP BY from graph dimensions and dashboard
            # filters. De-duplicate in first-seen order so a filter named like a
            # graph dimension does not repeat the key (Polars DuplicateError);
            # graph dimensions stay ahead of filter-only names.
            groupby_cols = list(
                dict.fromkeys(
                    d
                    for d in (graph.dimensions + dashboard_filter_dim_names)
                    if d in df.columns
                )
            )

            # Collect metric columns that exist in DataFrame
            metric_cols = [m for m in graph.metrics if m in df.columns]

            # Skip graph if no valid columns
            if not groupby_cols or not metric_cols:
                logger.warning(
                    "Skipping graph %s - no valid groupby or metric columns", graph.id
                )
                continue

            # Build aggregation expressions for metrics. The function map is
            # consumed from data/processing/aggregate_transforms.py::AGG_FUNC_MAP,
            # which already implements all ten AggregationFunctionEnum members.
            # The value is keyed by the enum and called with a column name.
            agg_exprs = [
                AGG_FUNC_MAP[agg_enum](m).alias(f"{m}_{agg_name}") for m in metric_cols
            ]

            # Perform GROUP BY aggregation
            result = df.group_by(groupby_cols).agg(agg_exprs)

            # Apply sorting based on graph configuration
            result = self._apply_chart_sorting(
                result,
                x_col=graph.config.get("x") if graph.config else None,
                color_col=graph.config.get("color") if graph.config else None,
                metric_cols=metric_cols,
                metric_agg=agg_name,
            )

            # Convert each row to record dict with coerced dimensions
            for row in result.to_dicts():
                dims = {col: _coerce_dim_value(row[col]) for col in groupby_cols}
                # Exclude helper columns (like _color_total) from metrics output
                metrics = {
                    k: v for k, v in row.items()
                    if k not in groupby_cols and not k.startswith("_")
                }
                record = {
                    "dashboard_id": graph.dashboard_id,
                    "graph_id": graph.id,
                    "dims": dims,
                    "metrics": metrics,
                }
                results.append(record)

        return results

    async def extract_filter_values(
        self,
        aggregated_records: list[dict[str, Any]],
        dashboard_filter_names: list[str],
    ) -> dict[str, list[str | int | float | bool]]:
        """Extract distinct values for each filter dimension from aggregated records.

        Args:
            aggregated_records: List of aggregated data records.
            dashboard_filter_names: List of filter dimension names.

        Returns:
            Dict with {filter_name: [sorted unique values preserving native types]}.
        """
        # Initialize sets for each filter name
        value_sets: dict[str, set[Any]] = {
            name: set() for name in dashboard_filter_names
        }

        # Collect values from each record's dims
        for record in aggregated_records:
            dims = record.get("dims", {})
            for filter_name in dashboard_filter_names:
                if filter_name in dims:
                    value_sets[filter_name].add(dims[filter_name])

        # Return sorted lists with native types preserved
        # Empty string ("") needs special handling for sorting
        return {
            name: sorted(list(values), key=lambda v: (isinstance(v, str), v))
            for name, values in value_sets.items()
        }

    def _apply_chart_sorting(
        self,
        df: pl.DataFrame,
        x_col: str | None,
        color_col: str | None,
        metric_cols: list[str],
        metric_agg: str,
    ) -> pl.DataFrame:
        """Apply chart-specific sorting to aggregated DataFrame.

        Sorts data for proper visualization in stacked bar charts:
        - X-axis (e.g., month_label) sorted chronologically using year/month columns
        - Color dimension (e.g., brand) sorted by total metric volume (descending)

        For stacked bar charts in Plotly, the trace order determines stacking.
        The first trace appears at the bottom. We sort by color_total descending
        first, then by x-axis ascending, so larger values appear first (bottom of stack).

        Args:
            df: Aggregated DataFrame.
            x_col: X-axis column name.
            color_col: Color dimension column name.
            metric_cols: List of metric column names.
            metric_agg: Aggregation function used.

        Returns:
            Sorted DataFrame.
        """
        if x_col is None:
            return df

        # For color dimension sorting by metric total
        # Calculate and add _color_total column for sorting
        if color_col and color_col in df.columns and metric_cols:
            primary_metric = f"{metric_cols[0]}_{metric_agg}"
            if primary_metric in df.columns:
                # Calculate total metric per color value
                color_totals = df.group_by(color_col).agg(
                    pl.col(primary_metric).sum().alias("_color_total")
                )
                # Join totals back to main dataframe
                df = df.join(color_totals, on=color_col, how="left")
                logger.debug(
                    "Applied color total calculation for sorting: %s",
                    color_col,
                )

        # Build sort columns: sort by color_total desc, then x-axis asc
        # This ensures: larger values at bottom, chronological x order within each color
        sort_columns: list[str] = []
        descending_flags: list[bool] = []

        # X-axis ascending (chronological) - year/month columns
        x_sort_cols: list[str] = []
        x_sort_desc: list[bool] = []
        if "year" in df.columns and "month" in df.columns:
            x_sort_cols.extend(["year", "month"])
            x_sort_desc.extend([False, False])
        elif x_col in df.columns:
            x_sort_cols.append(x_col)
            x_sort_desc.append(False)

        # Build final sort: color_total first (if present), then x-axis
        if "_color_total" in df.columns:
            sort_columns.append("_color_total")
            descending_flags.append(True)  # Descending for larger at bottom
            sort_columns.extend(x_sort_cols)
            descending_flags.extend(x_sort_desc)
            logger.debug(
                "Applying sort: _color_total(desc), then x-axis(asc) for color sort"
            )
        elif x_sort_cols:
            sort_columns.extend(x_sort_cols)
            descending_flags.extend(x_sort_desc)
            logger.debug("Applying x-axis sort only: %s(asc)", x_sort_cols)

        if sort_columns:
            df = df.sort(sort_columns, descending=descending_flags)

        return df
