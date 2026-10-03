"""Data transformations and aggregations for processing pipeline.

This module provides functions to apply various
data transformations including filtering, grouping,
sorting, YoY calculation and share calculation.

For backward compatibility, this module re-exports all public functions
from the split modules.
"""

import logging
from typing import Any, cast

import polars as pl

from mkobi.data.processing.aggregate_transforms import (
    _calculate_share,
    _calculate_yoy,
    aggregate_data,
    calculate_aggregations,
)
from mkobi.data.processing.filter_transforms import (
    _add_computed_fields,
    _apply_dtypes,
    _apply_filters,
)
from mkobi.data.processing.formula_parser import (
    _is_numeric_literal,
    _parse_formula,
    _parse_polars_dt_expr,
    _validate_formula_tokens,
)

logger = logging.getLogger(__name__)

# Re-export for external access
__all__ = [
    "apply_transformations",
    "calculate_aggregations",
    "aggregate_data",
    "_apply_filters",
    "_add_computed_fields",
    "_apply_dtypes",
    "_calculate_yoy",
    "_calculate_share",
    "_is_numeric_literal",
    "_parse_formula",
    "_parse_polars_dt_expr",
    "_validate_formula_tokens",
]


def apply_transformations(
    df: pl.DataFrame,
    config: dict[str, Any] | None = None,
    filters: list[Any] | None = None,
    groupby: list[str] | None = None,
    sort_by: list[str] | None = None,
    descending: bool = False,
) -> pl.DataFrame:
    """Apply transformations to DataFrame per config.

    Executes filtering, grouping, sorting,
    computed field addition, column renaming
    and type casting.

    The configured ``limit`` is deliberately **not** applied here (DP-008). A
    limit truncates the number of stored groups, so it must be applied to the
    frame the number is computed in -- the aggregated frame produced by
    ``calculate_aggregations`` -- not to this frame. The worker
    (``workers/data_worker.py::_run_with_transaction``) applies the limit after
    aggregation; see :func:`_apply_post_aggregation_limit`. Applying it here
    truncated the raw rows before any ``sum``/``mean`` was computed, so the
    stored aggregate was a function of the input row order.

    When ``groupby`` is supplied without ``aggregations`` each group is
    collapsed to one representative row (deterministic de-duplication): the
    frame is first sorted deterministically by every remaining column in the
    frame's own column order with ``nulls_last=True``, then the first row of
    each group is taken. The representative row is therefore the lexicographic
    minimum across the non-group columns -- a deliberate, reproducible rule, not
    an arbitrary pick -- and a null-bearing row is never chosen by accident.

    Args:
        df: Source DataFrame.
        config: Configuration dict (filters, computed_fields, rename, dtype).
        filters: List of filter conditions.
        groupby: List of columns for base grouping (no aggregations).
        sort_by: Column name to sort by.
        descending: Sort in descending order.

    Returns:
        pl.DataFrame: Transformed DataFrame.
    """
    # Lazy import to avoid circular dependency
    from pydantic import ValidationError

    from mkobi.models.transformation_configs import TransformationConfig

    config = config or {}
    # Validate config structure
    try:
        TransformationConfig(**config)
    except ValidationError as e:
        logger.error("Invalid transformation config: %s", e)
        raise ValueError(f"Invalid transformation config: {e}") from None
    result = df

    # 1. Row filtering (where conditions)
    filter_list: list[Any] | None = filters if filters is not None else config.get("filters") if config else None
    if filter_list:
        logger.debug("Applying filters: %s", filter_list)
        result = _apply_filters(result, filter_list)

    # 2. Base grouping (no aggregations)
    #
    # De-duplication rule (DP-007). A groupby supplied without aggregations
    # collapses each group to one representative row, but which row that is must
    # not depend on input row order. The frame is therefore first sorted
    # deterministically by every remaining (non-group) column in the frame's own
    # column order, and the first row of each group is then taken. The
    # representative row is the lexicographic minimum across the non-group
    # columns, which is independent of input order and fully reproducible.
    # Sorting by the group columns alone would leave the within-group order
    # undefined; every remaining column is included. nulls_last=True so a null
    # in a non-group column never becomes the representative row by accident.
    # pl.all().first() is kept as the per-group reducer: the input is ordered
    # first, so "first" is well defined.
    if groupby:
        logger.debug("Grouping by: %s (deterministic de-duplication)", groupby)
        sort_columns = [column for column in result.columns if column not in groupby]
        if sort_columns:
            result = result.sort(sort_columns, nulls_last=True)
        result = result.group_by(groupby).agg(pl.all().first())

    # 3. Sorting
    if sort_by:
        logger.debug("Sorting by: %s (desc=%s)", sort_by, descending)
        result = result.sort(sort_by, descending=descending)

    # 4. Computed fields
    computed_fields = config.get("computed_fields") if config else None
    if computed_fields:
        logger.debug("Adding computed fields: %s", computed_fields)
        result = _add_computed_fields(result, cast(list[dict[str, Any]], computed_fields))

    # 5. Column renaming
    rename_map = config.get("rename")
    if rename_map:
        logger.debug("Renaming columns: %s", rename_map)
        result = result.rename(rename_map)

    # 6. Column type casting
    dtype_map = config.get("dtype") if config else None
    if dtype_map:
        logger.debug("Casting column types: %s", dtype_map)
        result = _apply_dtypes(result, cast(dict[str, str], dtype_map))

    logger.info("Transformations applied: %d rows", result.shape[0])
    return result