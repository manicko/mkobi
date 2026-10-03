"""Aggregation transformations for data processing.

This module provides functions for calculating aggregations, YoY growth, and share calculations.
"""

import logging
from typing import Any

import polars as pl

from mkobi.models.enums import AggregationFunctionEnum

logger = logging.getLogger(__name__)

# Mapping aggregation functions to Polars expressions
AGG_FUNC_MAP: dict[AggregationFunctionEnum, Any] = {
    AggregationFunctionEnum.SUM: lambda col: pl.col(col).sum(),
    AggregationFunctionEnum.MEAN: lambda col: pl.col(col).mean(),
    AggregationFunctionEnum.COUNT: lambda col: pl.col(col).count(),
    AggregationFunctionEnum.MIN: lambda col: pl.col(col).min(),
    AggregationFunctionEnum.MAX: lambda col: pl.col(col).max(),
    AggregationFunctionEnum.MEDIAN: lambda col: pl.col(col).median(),
    AggregationFunctionEnum.STD: lambda col: pl.col(col).std(),
    AggregationFunctionEnum.VAR: lambda col: pl.col(col).var(),
    AggregationFunctionEnum.FIRST: lambda col: pl.col(col).first(),
    AggregationFunctionEnum.LAST: lambda col: pl.col(col).last(),
}


def calculate_aggregations(
    df: pl.DataFrame,
    groupby: list[str] | None = None,
    aggregations: list[Any] | None = None,
    yoy_config: dict[str, Any] | None = None,
    share_config: dict[str, Any] | None = None,
    custom_metrics: list[Any] | None = None,
) -> pl.DataFrame:
    """Calculate data aggregations with YoY and share support.

    Args:
        df: Source DataFrame.
        groupby: List of columns to group by.
        aggregations: List of aggregation configs (AggregationConfig objects).
        yoy_config: Configuration for YoY calculation.
        share_config: Configuration for share calculation.
        custom_metrics: List of custom metrics.

    Returns:
        pl.DataFrame: Aggregated DataFrame.
    """
    logger.info("Starting aggregation calculation")
    result = df

    # Grouping and base aggregations
    if groupby and aggregations:
        logger.debug("Grouping by: %s", groupby)
        result = _apply_groupby_aggregations(result, groupby, aggregations)

    # YoY calculation
    if yoy_config:
        logger.debug("YoY calculation: %s", yoy_config)
        result = _calculate_yoy(result, **yoy_config)

    # Share calculation
    if share_config:
        logger.debug("Share calculation: %s", share_config)
        result = _calculate_share(result, **share_config)

    # Custom metrics
    if custom_metrics:
        logger.debug("Custom metrics: %s", custom_metrics)
        # Import here to avoid circular import
        from mkobi.data.processing.filter_transforms import _add_computed_fields
        result = _add_computed_fields(result, custom_metrics)

    logger.info("Aggregations calculated: %d rows", result.shape[0])
    return result


def aggregate_data(
    df: pl.DataFrame,
    graph_configs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate data per graph configurations.

    Args:
        df: Source DataFrame.
        graph_configs: List of graph configuration dicts.

    Returns:
        list[dict]: List of dicts for JSONB storage.
    """
    results = []
    for config in graph_configs:
        groupby = config.get("dimensions", [])
        aggs = config.get("metrics", [])

        if not groupby or not aggs:
            continue

        aggregated = calculate_aggregations(
            df=df,
            groupby=groupby,
            aggregations=aggs,
        )
        results.extend(aggregated.to_dicts())
    return results


def _apply_groupby_aggregations(
    df: pl.DataFrame,
    groupby: list[str],
    aggregations: list[Any],
) -> pl.DataFrame:
    """Apply grouping and aggregations.

    Args:
        df: Source DataFrame.
        groupby: List of columns to group by.
        aggregations: List of aggregation configs (AggregationConfig objects or dicts).

    Returns:
        pl.DataFrame: Aggregated DataFrame.
    """
    agg_exprs = []
    for agg in aggregations:
        # Handle both Pydantic models and dictionaries
        if isinstance(agg, dict):
            column = agg.get("column")
            func_str = agg.get("function")
            alias = agg.get("alias", f"{column}_{func_str}")
        else:
            column = getattr(agg, 'column', None)
            func_str = getattr(agg, 'function', None)
            alias = getattr(agg, 'alias', None) or f"{column}_{func_str}"

        try:
            func_enum = AggregationFunctionEnum(func_str) if isinstance(func_str, str) else func_str
        except ValueError:
            logger.warning("Unknown aggregation function: %s", func_str)
            continue

        if func_enum not in AGG_FUNC_MAP:
            logger.warning("Unsupported aggregation function: %s", func_enum)
            continue

        expr = AGG_FUNC_MAP[func_enum](column).alias(alias)
        agg_exprs.append(expr)

    return df.group_by(groupby).agg(agg_exprs)


def _calculate_yoy(
    df: pl.DataFrame,
    year_column: str,
    value_column: str,
    group_cols: list[str] | None = None,
    month_column: str | None = None,
    alias: str = "yoy",
    percent_alias: str | None = None,
) -> pl.DataFrame:
    """Calculate Year-over-Year growth.

    The growth is always computed against the **same entity's** previous period,
    never the globally preceding row. When ``group_cols`` is supplied the entity
    is the group; when it is absent the entity is whatever identifies a series --
    any column that is neither the year, the value nor the shift key. That
    discovers the entity columns from the frame itself so the per-entity
    arithmetic is correct without a configuration key. ``month_column`` shifts
    within the month and the discovered entity columns.

    Args:
        df: Source DataFrame.
        year_column: Column name containing year.
        value_column: Column name containing value.
        group_cols: List of grouping columns (dimensions).
        month_column: Column name containing month.
        alias: Name of resulting YoY column.
        percent_alias: Reserved; not used by this implementation.

    Returns:
        pl.DataFrame: DataFrame with YoY column.
    """
    sort_cols = [year_column]
    if month_column:
        sort_cols.append(month_column)
    if group_cols:
        sort_cols.extend(group_cols)

    result = df.sort(sort_cols)

    # Columns that are neither the year, the value nor the month are entity
    # identifiers (the group-less case): shift within them so each entity's YoY
    # is taken against its own previous period. With ``group_cols`` supplied they
    # are the shift keys unchanged.
    if group_cols:
        shift_group_cols = list(group_cols)
    else:
        shift_group_cols = [
            column
            for column in df.columns
            if column not in {year_column, value_column, month_column}
        ]

    if month_column:
        shift_group_cols = [month_column, *shift_group_cols]

        result = result.with_columns([
            pl.col(value_column).shift(1).over(shift_group_cols).alias("__prev_value"),
            pl.col(year_column).shift(1).over(shift_group_cols).alias("__prev_year"),
        ])

        year_diff = pl.col(year_column) - pl.col("__prev_year")
        prev_value_expr = pl.when(year_diff == 1).then(pl.col("__prev_value")).otherwise(None)
    else:
        shift_lag = 1
        if shift_group_cols:
            prev_value_expr = pl.col(value_column).shift(shift_lag).over(shift_group_cols)
        else:
            prev_value_expr = pl.col(value_column).shift(shift_lag)

    result = result.with_columns([
        pl.when(prev_value_expr.is_null() | (prev_value_expr == 0))
        .then(None)
        .otherwise((pl.col(value_column) - prev_value_expr) / prev_value_expr * 100)
        .alias(alias)
    ])

    result = result.with_columns([pl.col(alias).fill_nan(None)])
    # Handle infinity values from division by zero edge cases
    result = result.with_columns(
        pl.when(pl.col(alias).is_infinite())
        .then(None)
        .otherwise(pl.col(alias))
        .alias(alias)
    )
    temp_cols = ["__prev_value", "__prev_year"]
    for col in temp_cols:
        if col in result.columns:
            result = result.drop(col)

    return result


def _calculate_share(
    df: pl.DataFrame,
    value_column: str,
    alias: str = "share",
    group_cols: list[str] | None = None,
) -> pl.DataFrame:
    """Calculate share of each value from total sum.

    Args:
        df: Source DataFrame.
        value_column: Column name containing value.
        alias: Name of resulting share column.
        group_cols: List of columns to group by.

    Returns:
        pl.DataFrame: DataFrame with share column.
    """
    if group_cols:
        total_df = df.group_by(group_cols).agg(pl.col(value_column).sum().alias("total"))
        result = df.join(total_df, on=group_cols)
        result = result.with_columns(
            pl.when(pl.col("total") == 0)
            .then(0.0)
            .otherwise(pl.col(value_column) / pl.col("total") * 100)
            .alias(alias)
        )
        result = result.drop("total")
    else:
        total = df[value_column].sum()
        if total == 0:
            result = df.with_columns(pl.lit(0.0).alias(alias))
        else:
            result = df.with_columns((pl.col(value_column) / total * 100).alias(alias))

    return result