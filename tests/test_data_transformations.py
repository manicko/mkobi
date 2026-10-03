"""Unit tests for data transformations.

Tests:
- apply_transformations
- calculate_aggregations
- _calculate_yoy (year-over-year)
- _calculate_share
- _parse_formula (formula parser)
- _validate_formula_tokens
- _parse_polars_dt_expr (safe Polars expression parser)
"""

import uuid

import polars as pl
import pytest

from mkobi.data.processing.transformations import (
    _add_computed_fields,
    _apply_dtypes,
    _apply_filters,
    _calculate_share,
    _calculate_yoy,
    _is_numeric_literal,
    _parse_formula,
    _parse_polars_dt_expr,
    _validate_formula_tokens,
    aggregate_data,
    apply_transformations,
    calculate_aggregations,
)


class TestIsNumericLiteral:
    """Tests for _is_numeric_literal helper function."""

    def test_integer_literal(self):
        """Test integer is recognized as numeric literal."""
        assert _is_numeric_literal("123") is True

    def test_float_literal(self):
        """Test float is recognized as numeric literal."""
        assert _is_numeric_literal("123.45") is True

    def test_negative_integer_literal(self):
        """Test negative integer is recognized as numeric literal."""
        assert _is_numeric_literal("-123") is True

    def test_negative_float_literal(self):
        """Test negative float is recognized as numeric literal."""
        assert _is_numeric_literal("-123.45") is True

    def test_column_name_not_numeric(self):
        """Test column name is not recognized as numeric literal."""
        assert _is_numeric_literal("revenue") is False

    def test_invalid_string_not_numeric(self):
        """Test invalid string is not recognized as numeric literal."""
        assert _is_numeric_literal("abc") is False

    def test_scientific_notation(self):
        """Test scientific notation is recognized as numeric literal."""
        assert _is_numeric_literal("1e5") is True


class TestValidateFormulaTokens:
    """Tests for _validate_formula_tokens function."""

    def test_single_operand_valid(self):
        """Test single operand (column name) is valid."""
        # Single operand: no operators, should pass
        _validate_formula_tokens(["revenue"])  # Should not raise

    def test_binary_op_valid(self):
        """Test valid binary operation tokens."""
        _validate_formula_tokens(["revenue", "+", "cost"])  # Should not raise

    def test_chained_ops_valid(self):
        """Test valid chained operations."""
        _validate_formula_tokens(["a", "+", "b", "-", "c"])  # Should not raise

    def test_invalid_operand(self):
        """Test invalid operand raises error."""
        with pytest.raises(ValueError, match="Invalid operand"):
            _validate_formula_tokens(["revenue", "+", "invalid-column!"])

    def test_invalid_operator(self):
        """Test invalid operator raises error."""
        with pytest.raises(ValueError, match="Expected operator"):
            _validate_formula_tokens(["revenue", "&", "cost"])

    def test_formula_ends_with_operator(self):
        """Test formula ending with operator raises error."""
        with pytest.raises(ValueError, match="must end with an operand"):
            _validate_formula_tokens(["a", "+", "b", "-"])


class TestParseFormula:
    """Tests for _parse_formula function."""

    def test_single_column(self):
        """Test parsing single column name."""
        expr = _parse_formula("revenue")
        # Result should be a Polars expression for column access
        assert "revenue" in str(expr)

    def test_single_literal(self):
        """Test parsing single numeric literal."""
        expr = _parse_formula("100")
        assert "100" in str(expr)

    def test_addition(self):
        """Test parsing addition formula."""
        expr = _parse_formula("revenue + cost")
        result = pl.DataFrame({"revenue": [10], "cost": [5]})
        computed = result.select(expr.alias("total"))
        assert computed["total"][0] == 15

    def test_subtraction(self):
        """Test parsing subtraction formula."""
        expr = _parse_formula("revenue - cost")
        result = pl.DataFrame({"revenue": [10], "cost": [5]})
        computed = result.select(expr.alias("diff"))
        assert computed["diff"][0] == 5

    def test_multiplication(self):
        """Test parsing multiplication formula."""
        expr = _parse_formula("price * quantity")
        result = pl.DataFrame({"price": [10], "quantity": [3]})
        computed = result.select(expr.alias("total"))
        assert computed["total"][0] == 30

    def test_division(self):
        """Test parsing division formula."""
        expr = _parse_formula("revenue / 100")
        result = pl.DataFrame({"revenue": [150]})
        computed = result.select(expr.alias("percent"))
        assert computed["percent"][0] == 1.5

    def test_negative_literal_in_formula(self):
        """Test negative numeric literal in formula."""
        expr = _parse_formula("value + -50")
        result = pl.DataFrame({"value": [100]})
        computed = result.select(expr.alias("total"))
        assert computed["total"][0] == 50

    def test_chained_operations(self):
        """Test parsing chained operations (left-to-right evaluation)."""
        expr = _parse_formula("a + b - c")
        result = pl.DataFrame({"a": [10], "b": [5], "c": [3]})
        computed = result.select(expr.alias("result"))
        # Left-to-right: (10 + 5) - 3 = 12
        assert computed["result"][0] == 12

    def test_column_and_literal(self):
        """Test formula with column and numeric literal."""
        expr = _parse_formula("revenue * 100")
        result = pl.DataFrame({"revenue": [2.5]})
        computed = result.select(expr.alias("percent"))
        assert computed["percent"][0] == 250.0

    def test_empty_formula_raises(self):
        """Test empty formula raises error."""
        with pytest.raises(ValueError, match="empty"):
            _parse_formula("")

    def test_whitespace_formula_raises(self):
        """Test whitespace-only formula raises error."""
        with pytest.raises(ValueError, match="empty"):
            _parse_formula("   ")

    def test_unsupported_operator_raises(self):
        """Test unsupported operator raises error."""
        with pytest.raises(ValueError, match="Invalid operand"):
            _parse_formula("a & b")


class TestParsePolarsDtExpr:
    """Tests for _parse_polars_dt_expr function (safe Polars expression parser)."""

    def test_year_extraction(self):
        """Test pl.col('date').dt.year() parsing."""
        df = pl.DataFrame({
            "date": ["2023-06-15", "2024-01-20"],
        }).with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
        expr = _parse_polars_dt_expr("pl.col('date').dt.year()")
        result = df.select(expr.alias("year"))
        assert result["year"][0] == 2023
        assert result["year"][1] == 2024

    def test_month_extraction(self):
        """Test pl.col('date').dt.month() parsing."""
        df = pl.DataFrame({
            "date": ["2023-06-15", "2024-01-20"],
        }).with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
        expr = _parse_polars_dt_expr("pl.col('date').dt.month()")
        result = df.select(expr.alias("month"))
        assert result["month"][0] == 6
        assert result["month"][1] == 1

    def test_strftime_extraction(self):
        """Test pl.col('date').dt.strftime() parsing."""
        df = pl.DataFrame({
            "date": ["2023-06-15", "2024-01-20"],
        }).with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
        expr = _parse_polars_dt_expr("pl.col('date').dt.strftime('%b %Y')")
        result = df.select(expr.alias("label"))
        assert "Jun 2023" in str(result["label"][0]) or "Jun" in str(result["label"][0])

    def test_day_extraction(self):
        """Test pl.col('date').dt.day() parsing."""
        df = pl.DataFrame({
            "date": ["2023-06-15"],
        }).with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
        expr = _parse_polars_dt_expr("pl.col('date').dt.day()")
        result = df.select(expr.alias("day"))
        assert result["day"][0] == 15

    def test_disallowed_method_raises(self):
        """Test disallowed method raises error."""
        with pytest.raises(ValueError, match="Disallowed datetime method"):
            _parse_polars_dt_expr("pl.col('date').dt.map_elements()")

    def test_invalid_syntax_raises(self):
        """Test invalid syntax raises error."""
        with pytest.raises(ValueError, match="Invalid Polars expression"):
            _parse_polars_dt_expr("pl.filter()")

    def test_strftime_missing_arg_raises(self):
        """Test strftime without argument raises error."""
        with pytest.raises(ValueError, match="strftime requires"):
            _parse_polars_dt_expr("pl.col('date').dt.strftime()")

    def test_double_quote_syntax(self):
        """Test double quote syntax works for column names."""
        df = pl.DataFrame({
            "date": ["2023-06-15"],
        }).with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
        expr = _parse_polars_dt_expr('pl.col("date").dt.year()')
        result = df.select(expr.alias("year"))
        assert result["year"][0] == 2023

    def test_add_computed_dt_fields(self):
        """Test _add_computed_fields with datetime expressions."""
        df = pl.DataFrame({
            "date": ["2023-06-15", "2024-01-20"],
            "value": [100, 200],
        }).with_columns(pl.col("date").str.to_date("%Y-%m-%d"))

        result = _add_computed_fields(df, [
            {"name": "year", "expr": "pl.col('date').dt.year()"},
            {"name": "month", "expr": "pl.col('date').dt.month()"},
        ])

        assert "year" in result.columns
        assert "month" in result.columns
        assert result["year"][0] == 2023
        assert result["month"][0] == 6


class TestApplyFilters:
    """Tests for _apply_filters function."""

    def test_filter_eq(self):
        """Test filter with equals operator."""
        df = pl.DataFrame({"category": ["A", "B", "C"], "value": [10, 20, 30]})
        result = _apply_filters(df, [{"column": "category", "operator": "==", "value": "A"}])
        assert result.shape[0] == 1
        assert result["category"][0] == "A"

    def test_filter_ne(self):
        """Test filter with not-equals operator."""
        df = pl.DataFrame({"category": ["A", "B", "C"], "value": [10, 20, 30]})
        result = _apply_filters(df, [{"column": "category", "operator": "!=", "value": "A"}])
        assert result.shape[0] == 2

    def test_filter_gt(self):
        """Test filter with greater-than operator."""
        df = pl.DataFrame({"value": [10, 20, 30]})
        result = _apply_filters(df, [{"column": "value", "operator": ">", "value": 15}])
        assert result.shape[0] == 2  # 20 and 30

    def test_filter_lt(self):
        """Test filter with less-than operator."""
        df = pl.DataFrame({"value": [10, 20, 30]})
        result = _apply_filters(df, [{"column": "value", "operator": "<", "value": 25}])
        assert result.shape[0] == 2  # 10 and 20

    def test_filter_gte(self):
        """Test filter with greater-or-equal operator."""
        df = pl.DataFrame({"value": [10, 20, 30]})
        result = _apply_filters(df, [{"column": "value", "operator": ">=", "value": 20}])
        assert result.shape[0] == 2  # 20 and 30

    def test_filter_lte(self):
        """Test filter with less-or-equal operator."""
        df = pl.DataFrame({"value": [10, 20, 30]})
        result = _apply_filters(df, [{"column": "value", "operator": "<=", "value": 20}])
        assert result.shape[0] == 2  # 10 and 20

    def test_filter_in(self):
        """Test filter with 'in' operator."""
        df = pl.DataFrame({"category": ["A", "B", "C", "D"]})
        result = _apply_filters(df, [{"column": "category", "operator": "in", "value": ["A", "C"]}])
        assert result.shape[0] == 2

    def test_filter_multiple(self):
        """Test multiple filters applied sequentially."""
        df = pl.DataFrame({
            "category": ["A", "A", "B", "B"],
            "value": [10, 30, 20, 40],
        })
        result = _apply_filters(df, [
            {"column": "category", "operator": "==", "value": "A"},
            {"column": "value", "operator": ">", "value": 15},
        ])
        assert result.shape[0] == 1  # Only A with value > 15

    def test_filter_missing_column_skipped(self):
        """Test filter with missing column is skipped."""
        df = pl.DataFrame({"value": [10, 20, 30]})
        result = _apply_filters(df, [{"column": "missing", "operator": "==", "value": "A"}])
        assert result.shape[0] == 3  # No filtering


class TestAddComputedFields:
    """Tests for _add_computed_fields function."""

    def test_add_single_field(self):
        """Test adding a single computed field."""
        df = pl.DataFrame({"price": [10], "quantity": [5]})
        result = _add_computed_fields(df, [{"name": "total", "expr": "price * quantity"}])

        assert "total" in result.columns
        assert result["total"][0] == 50

    def test_add_multiple_fields(self):
        """Test adding multiple computed fields."""
        df = pl.DataFrame({"a": [10], "b": [5]})
        result = _add_computed_fields(df, [
            {"name": "sum", "expr": "a + b"},
            {"name": "diff", "expr": "a - b"},
        ])

        assert "sum" in result.columns
        assert "diff" in result.columns

    def test_add_field_missing_name(self):
        """Test field without name is skipped."""
        df = pl.DataFrame({"value": [10]})
        result = _add_computed_fields(df, [{"expr": "value * 2"}])

        assert "value" in result.columns

    def test_add_field_missing_expr(self):
        """Test field without expr is skipped."""
        df = pl.DataFrame({"value": [10]})
        result = _add_computed_fields(df, [{"name": "new_field"}])

        assert "new_field" not in result.columns


class TestApplyDtypes:
    """Tests for _apply_dtypes function."""

    def test_apply_single_dtype(self):
        """Test applying single type cast."""
        df = pl.DataFrame({"value": ["1", "2", "3"]})
        result = _apply_dtypes(df, {"value": "Int64"})

        assert result["value"].dtype == pl.Int64

    def test_apply_multiple_dtypes(self):
        """Test applying multiple type casts."""
        df = pl.DataFrame({"a": ["1"], "b": ["2.5"]})
        result = _apply_dtypes(df, {"a": "Int64", "b": "Float64"})

        assert result["a"].dtype == pl.Int64
        assert result["b"].dtype == pl.Float64

    def test_apply_unknown_dtype_skipped(self):
        """Test unknown type is skipped."""
        df = pl.DataFrame({"value": [1, 2, 3]})
        result = _apply_dtypes(df, {"value": "UnknownType"})

        assert result["value"].dtype == pl.Int64  # Unchanged

    def test_apply_missing_column_skipped(self):
        """Test missing column type cast is skipped."""
        df = pl.DataFrame({"a": [1]})
        result = _apply_dtypes(df, {"missing": "Int64"})

        assert "a" in result.columns


class TestApplyTransformations:
    """Tests for apply_transformations function."""

    def test_empty_transformations(self):
        """Test no transformations returns original DataFrame."""
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        result = apply_transformations(df)

        assert result.shape == df.shape

    def test_transformations_with_filters(self):
        """Test transformations with filters."""
        df = pl.DataFrame({"category": ["A", "B", "A"], "value": [10, 20, 30]})
        result = apply_transformations(
            df,
            config={"filters": [{"column": "category", "operator": "==", "value": "A"}]},
        )

        assert result.shape[0] == 2

    def test_transformations_with_groupby(self):
        """Test transformations with grouping.

        The representative row is the deterministic lexicographic minimum of the
        non-group columns (DP-007 de-duplication rule), not whatever row Polars
        happened to present first.
        """
        df = pl.DataFrame({"category": ["A", "A", "B"], "value": [20, 10, 30]})
        result = apply_transformations(
            df,
            groupby=["category"],
        )

        assert result.shape[0] == 2  # Two groups
        assert "category" in result.columns
        assert result.filter(pl.col("category") == "A")["value"].item() == 10

    def test_groupby_without_aggregations_is_input_order_independent(self):
        """Identical four rows in forward and reversed order store the same value.

        DP-007 evidence: with the arbitrary pick, forward order yielded N=1 and
        reversed order yielded N=9 for the same four rows.
        """
        forward = pl.DataFrame({"g": ["A", "A", "A", "A"], "N": [1, 7, 2, 9]})
        reversed_ = pl.DataFrame({"g": ["A", "A", "A", "A"], "N": [9, 2, 7, 1]})

        forward_result = apply_transformations(forward, groupby=["g"])
        reversed_result = apply_transformations(reversed_, groupby=["g"])

        assert forward_result["N"].item() == reversed_result["N"].item() == 1

    def test_groupby_representative_is_lexicographic_minimum(self):
        """The representative row is the lexicographic minimum, not an incidental pick."""
        df = pl.DataFrame(
            {
                "g": ["A", "A", "A", "A"],
                "a": [3, 1, 4, 1],
                "b": [5, 9, 2, 2],
            }
        )

        result = apply_transformations(df, groupby=["g"])

        # Sorted by (a, b): (1,2), (1,9), (3,5), (4,2) -> representative (1, 2).
        assert result["a"].item() == 1
        assert result["b"].item() == 2

    def test_groupby_null_is_not_the_representative_row(self):
        """A null in a non-group column is not chosen as the representative row."""
        df = pl.DataFrame(
            {
                "g": ["A", "A"],
                "value": [None, 5],
            },
            schema={"g": pl.Utf8, "value": pl.Int64},
        )

        result = apply_transformations(df, groupby=["g"])

        assert result["value"].item() == 5

    def test_groupby_with_aggregations_is_unaffected(self):
        """groupby with aggregations leaves apply_transformations step 2 inert.

        The worker passes groupby only when aggregations is falsy
        (``groupby=config.groupby if not config.aggregations else None``). With
        aggregations configured, apply_transformations receives groupby=None, so
        step 2 is skipped and the frame is untouched -- the common path reaches
        calculate_aggregations instead.
        """
        df = pl.DataFrame({"g": ["A", "A", "B"], "N": [1, 7, 2]})

        result = apply_transformations(df, groupby=None)

        assert result.shape == df.shape
        assert result["N"].to_list() == [1, 7, 2]

    def test_transformations_with_sort(self):
        """Test transformations with sorting."""
        df = pl.DataFrame({"value": [30, 10, 20]})
        result = apply_transformations(
            df,
            sort_by=["value"],
            descending=True,
        )

        assert result["value"][0] == 30
        assert result["value"][2] == 10

    def test_limit_with_complete_sort_by_truncates_deterministically(self):
        """A complete ``sort_by`` orders the frame the limit is taken from.

        The ruled semantic is "top N by this metric": order by the metric
        descending, keep the first N. This exercises the ordering half directly;
        the worker applies sort+limit together through
        ``_apply_post_aggregation_limit`` after aggregation. This is the case
        that must not regress under the move.
        """
        df = pl.DataFrame({"category": ["A", "B", "C", "D"], "value": [10, 40, 20, 30]})

        result = apply_transformations(df, sort_by=["value"], descending=True)

        assert result["value"].to_list() == [40, 30, 20, 10]
        assert result["category"].to_list() == ["B", "D", "C", "A"]

    def test_post_aggregation_limit_is_order_then_head(self):
        """``_apply_post_aggregation_limit`` sorts the frame, then truncates it.

        Sorting by an aggregate column (``value_sum``) is only possible here,
        after aggregation, which is why the limit's ordering is a post-aggregation
        concern.
        """
        from mkobi.workers.data_worker import _apply_post_aggregation_limit

        grouped = pl.DataFrame(
            {
                "category": ["C0", "C1", "C2", "C3", "C4"],
                "value_sum": [10, 50, 30, 20, 40],
            }
        )

        result = _apply_post_aggregation_limit(grouped, ["value_sum"], True, 3)

        assert result["value_sum"].to_list() == [50, 40, 30]
        assert result["category"].to_list() == ["C1", "C4", "C2"]

    def test_post_aggregation_limit_without_sort_by_only_truncates(self):
        """A bare ``limit`` truncates without reordering the frame."""
        from mkobi.workers.data_worker import _apply_post_aggregation_limit

        df = pl.DataFrame({"value": [10, 20, 30, 40, 50]})

        result = _apply_post_aggregation_limit(df, None, False, 3)
        unchanged = _apply_post_aggregation_limit(df, None, False, None)

        assert result["value"].to_list() == [10, 20, 30]
        assert unchanged.shape == df.shape
        assert unchanged["value"].to_list() == [10, 20, 30, 40, 50]

    def test_limit_composes_with_groupby_aggregation(self):
        """``groupby`` + ``aggregations`` + ``limit`` compose: aggregate all
        groups, then truncate by the computed metric.

        Ten distinct categories each with one value; the aggregate ranking
        (largest first) differs from the raw row order. Aggregating all ten then
        keeping the top three by the computed metric yields the three LARGEST.
        """
        from mkobi.workers.data_worker import _apply_post_aggregation_limit

        df = pl.DataFrame(
            {
                "category": [f"C{i}" for i in range(10)],
                "value": [10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            }
        )

        grouped = calculate_aggregations(
            df,
            groupby=["category"],
            aggregations=[{"column": "value", "function": "sum"}],
        )
        limited = _apply_post_aggregation_limit(grouped, ["value_sum"], True, 3)

        assert limited["value_sum"].to_list() == [100, 90, 80]
        assert limited["category"].to_list() == ["C9", "C8", "C7"]

    def test_groupby_dedup_and_limit_do_not_disturb_each_other(self):
        """The DP-007 ``groupby`` de-duplication and the post-aggregation limit
        are independent: the groupby reduces to one representative row per group
        first, and the limit then truncates those groups by order.
        """
        from mkobi.workers.data_worker import _apply_post_aggregation_limit

        df = pl.DataFrame({"category": ["A", "A", "B", "C"], "value": [20, 10, 30, 40]})

        deduped = apply_transformations(df, groupby=["category"])
        assert deduped.shape[0] == 3

        limited = _apply_post_aggregation_limit(deduped, ["value"], True, 2)
        assert limited["category"].to_list() == ["C", "B"]
        assert limited["value"].to_list() == [40, 30]

    def test_transformations_reject_a_limit(self):
        """``limit`` is applied after aggregation, not inside apply_transformations.

        DP-008: truncating the raw frame before ``calculate_aggregations`` makes
        ``limit: 3`` aggregate the first three raw rows instead of aggregating
        all rows and keeping three groups. The truncation point therefore moved
        into the worker's post-aggregation stage
        (``data_worker._run_with_transaction`` calling
        ``_apply_post_aggregation_limit``). The parameter was removed, not
        accepted-and-ignored: passing it is a ``TypeError``, so no caller can
        silently retain the old behaviour.
        """
        df = pl.DataFrame({"value": [10, 20, 30, 40, 50]})

        with pytest.raises(TypeError):
            apply_transformations(df, limit=3)  # type: ignore[call-arg]

    def test_transformations_with_computed_fields(self):
        """Test transformations with computed fields."""
        df = pl.DataFrame({"price": [10], "quantity": [5]})
        result = apply_transformations(
            df,
            config={"computed_fields": [{"name": "total", "expr": "price * quantity"}]},
        )

        assert "total" in result.columns
        assert result["total"][0] == 50

    def test_transformations_with_rename(self):
        """Test transformations with column rename."""
        df = pl.DataFrame({"old_name": [1, 2, 3]})
        result = apply_transformations(
            df,
            config={"rename": {"old_name": "new_name"}},
        )

        assert "new_name" in result.columns
        assert "old_name" not in result.columns

    def test_transformations_invalid_config_raises(self):
        """Test invalid config raises error."""
        df = pl.DataFrame({"a": [1]})
        with pytest.raises(ValueError, match="Invalid transformation config"):
            apply_transformations(df, config={"invalid_key": "value"})


class TestCalculateAggregations:
    """Tests for calculate_aggregations function."""

    def test_aggregation_sum(self):
        """Test aggregation with sum function."""
        df = pl.DataFrame({
            "category": ["A", "A", "B"],
            "value": [10, 20, 30],
        })
        result = calculate_aggregations(
            df,
            groupby=["category"],
            aggregations=[{"column": "value", "function": "sum"}],
        )

        assert result.shape[0] == 2

    def test_aggregation_multiple_functions(self):
        """Test aggregation with multiple functions."""
        df = pl.DataFrame({
            "category": ["A", "A", "B"],
            "value": [10, 20, 30],
        })
        result = calculate_aggregations(
            df,
            groupby=["category"],
            aggregations=[
                {"column": "value", "function": "sum"},
                {"column": "value", "function": "mean"},
            ],
        )

        assert result.shape[0] == 2

    def test_aggregation_with_yoy(self):
        """Test aggregation with YoY calculation."""
        df = pl.DataFrame({
            "year": [2022, 2023, 2022, 2023],
            "category": ["A", "A", "B", "B"],
            "value": [100, 150, 200, 250],
        })
        result = calculate_aggregations(
            df,
            groupby=["year", "category"],
            aggregations=[{"column": "value", "function": "sum"}],
            yoy_config={
                "year_column": "year",
                "value_column": "value_sum",
                "group_cols": ["category"],
            },
        )

        assert "yoy" in result.columns

    def test_aggregation_unknown_function_skipped(self):
        """Test aggregation skips unknown function."""
        df = pl.DataFrame({
            "category": ["A", "A"],
            "value": [10, 20],
        })
        result = calculate_aggregations(
            df,
            groupby=["category"],
            aggregations=[{"column": "value", "function": "unknown"}],
        )

        assert result.shape[0] == 1


class TestCalculateYoY:
    """Tests for _calculate_yoy function."""

    def test_yoy_basic(self):
        """Test basic YoY calculation."""
        df = pl.DataFrame({
            "year": [2022, 2023, 2023, 2024],
            "value": [100, 150, 200, 300],
        }).sort("year")

        result = _calculate_yoy(
            df,
            year_column="year",
            value_column="value",
        )

        assert "yoy" in result.columns

    def test_yoy_with_group_cols(self):
        """Test YoY with grouping columns."""
        df = pl.DataFrame({
            "year": [2022, 2022, 2023, 2023],
            "category": ["A", "B", "A", "B"],
            "value": [100, 200, 150, 250],
        }).sort(["year", "category"])

        result = _calculate_yoy(
            df,
            year_column="year",
            value_column="value",
            group_cols=["category"],
        )

        assert "yoy" in result.columns
        assert "__prev_value" not in result.columns
        assert "__prev_year" not in result.columns

    def test_yoy_calculates_percentage(self):
        """Test YoY calculates correct percentage change."""
        df = pl.DataFrame({
            "year": [2022, 2023],
            "value": [100, 150],
        }).sort("year")

        result = _calculate_yoy(
            df,
            year_column="year",
            value_column="value",
        )

        # YoY should be (150-100)/100 * 100 = 50%
        # Note: actual calculation may have null for first year
        non_null_yoy = result.filter(pl.col("yoy").is_not_null())
        if len(non_null_yoy) > 0:
            assert non_null_yoy["yoy"][0] == pytest.approx(50.0, rel=0.01)

    def test_yoy_custom_alias(self):
        """Test YoY with custom alias."""
        df = pl.DataFrame({
            "year": [2022, 2023],
            "value": [100, 150],
        }).sort("year")

        result = _calculate_yoy(
            df,
            year_column="year",
            value_column="value",
            alias="custom_yoy",
        )

        assert "custom_yoy" in result.columns

    def test_yoy_with_month_column(self):
        """Test YoY with month column for 12-month shift."""
        df = pl.DataFrame({
            "year": [2022, 2023, 2023, 2023],
            "month": [12, 12, 1, 1],
            "category": ["A", "A", "A", "A"],
            "value": [100, 150, 200, 250],
        }).sort(["year", "month"])

        result = _calculate_yoy(
            df,
            year_column="year",
            value_column="value",
            month_column="month",
            group_cols=["category"],
        )

        assert "yoy" in result.columns


class TestCalculateShare:
    """Tests for _calculate_share function."""

    def test_share_basic(self):
        """Test basic share calculation."""
        df = pl.DataFrame({
            "value": [100, 200, 300],
        })

        result = _calculate_share(df, value_column="value")

        # Total = 600, shares should be 100/600=16.67%, 200/600=33.33%, 300/600=50%
        assert "share" in result.columns
        assert result["share"][0] == pytest.approx(16.67, rel=0.01)
        assert result["share"][1] == pytest.approx(33.33, rel=0.01)
        assert result["share"][2] == pytest.approx(50.0, rel=0.01)

    def test_share_with_group_cols(self):
        """Test share calculation with grouping columns."""
        df = pl.DataFrame({
            "year": [2023, 2023, 2024, 2024],
            "value": [100, 200, 300, 100],
        })

        result = _calculate_share(
            df,
            value_column="value",
            group_cols=["year"],
        )

        assert "share" in result.columns

    def test_share_custom_alias(self):
        """Test share with custom alias."""
        df = pl.DataFrame({"value": [50, 50]})

        result = _calculate_share(df, value_column="value", alias="percentage")

        assert "percentage" in result.columns

    def test_share_zero_total(self):
        """Test share with zero total returns zero share."""
        df = pl.DataFrame({"value": [0, 0, 0]})

        result = _calculate_share(df, value_column="value")

        assert "share" in result.columns
        assert all(result["share"] == 0.0)

    def test_share_custom_metric(self):
        """Test share calculation with custom metric expression."""
        df = pl.DataFrame({
            "revenue": [100, 200],
            "cost": [50, 50],
        })

        result = _calculate_share(
            df,
            value_column="revenue",  # Share of revenue
        )

        assert "share" in result.columns


class TestYoyUnpackingContract:
    """DP-009: the argument shape ``calculate_aggregations`` is documented to take.

    ``calculate_aggregations`` unpacks ``yoy_config``/``share_config`` with ``**``
    and passes ``custom_metrics`` to ``filter_transforms._add_computed_fields``,
    which reads ``field["name"]``. The worker therefore had to hand it **mappings**
    (and a list of mappings), not the Pydantic models declared on
    ``ProcessingConfig``. These tests pin the receiving contract directly, so the
    worker's dump-shape fix has a stated target.
    """

    def test_yoy_config_mapping_works_and_model_does_not(self):
        """A dict unpacks; the model raises ``TypeError`` at the ``**`` boundary."""
        from mkobi.models.transformation_configs import YoyConfig

        df = pl.DataFrame({"year": [2022, 2023], "value": [100, 150]})
        mapping = {"year_column": "year", "value_column": "value"}

        result = calculate_aggregations(df, yoy_config=mapping)
        assert "yoy" in result.columns

        with pytest.raises(TypeError):
            calculate_aggregations(df, yoy_config=YoyConfig(**mapping))

    def test_share_config_mapping_works_and_model_does_not(self):
        """A dict unpacks; the model raises ``TypeError`` at the ``**`` boundary."""
        from mkobi.models.transformation_configs import ShareConfig

        df = pl.DataFrame({"value": [100, 200]})
        mapping = {"value_column": "value"}

        result = calculate_aggregations(df, share_config=mapping)
        assert "share" in result.columns

        with pytest.raises(TypeError):
            calculate_aggregations(df, share_config=ShareConfig(**mapping))

    def test_custom_metrics_mapping_works_and_model_does_not(self):
        """A list of dicts works; the model raises ``AttributeError`` on ``.get``."""
        from mkobi.models.transformation_configs import CustomMetricConfig

        df = pl.DataFrame({"revenue": [100, 200], "cost": [40, 80]})
        mapping = {"name": "profit", "expr": "revenue - cost"}

        result = calculate_aggregations(df, custom_metrics=[mapping])
        assert "profit" in result.columns
        assert result["profit"].to_list() == [60, 120]

        with pytest.raises(AttributeError):
            calculate_aggregations(
                df, custom_metrics=[CustomMetricConfig(**mapping)]
            )


class TestDumpShapeExcludesNone:
    """DP-009: the dump handed to ``calculate_aggregations`` must not leak ``None``.

    The receiving functions treat their arguments as configuration, so a
    ``"group_cols": None`` entry would be read as if a caller had configured it.
    ``exclude_none=True`` is the chosen shape and is asserted here -- not assumed.
    """

    def test_exclude_none_ooo_config_omits_unset_keys(self):
        from mkobi.models.transformation_configs import YoyConfig

        dumped = YoyConfig(
            year_column="year", value_column="value"
        ).model_dump(exclude_none=True)

        # None-valued fields must not leak into a function that reads the
        # argument as configuration. Non-None defaults (alias, percent_alias)
        # are legitimate settings and are allowed to remain.
        assert dumped["year_column"] == "year"
        assert dumped["value_column"] == "value"
        assert "group_cols" not in dumped
        assert "month_column" not in dumped
        assert all(value is not None for value in dumped.values())

    def test_exclude_none_share_config_omits_unset_keys(self):
        from mkobi.models.transformation_configs import ShareConfig

        dumped = ShareConfig(value_column="value").model_dump(exclude_none=True)

        assert dumped["value_column"] == "value"
        assert "group_cols" not in dumped
        assert all(value is not None for value in dumped.values())

    def test_default_model_dump_does_leak_none(self):
        """The reason ``exclude_none`` is chosen: the default dump leaks ``None``."""
        from mkobi.models.transformation_configs import YoyConfig

        leaked = YoyConfig(year_column="year", value_column="value").model_dump()

        assert leaked["group_cols"] is None
        assert "group_cols" in leaked


class TestGroupLessYoyIsPerEntity:
    """D-05-P(a): the group-less YoY path must be per-entity, not global.

    With no ``group_cols`` the unfixed ``_calculate_yoy`` sorts by the year column
    and applies one ungrouped ``shift(1)``, so an entity's YoY is taken against the
    globally preceding row rather than its own previous year. The entity column is
    available, so the arithmetic is correctable without a configuration key.
    """

    def test_group_less_yoy_is_computed_per_entity(self):
        from mkobi.models.transformation_configs import YoyConfig

        interleaved = pl.DataFrame(
            {
                "year": [2022, 2022, 2023, 2023],
                "entity": ["B", "A", "B", "A"],
                "value": [200, 100, 300, 150],
            }
        )

        result = _calculate_yoy(interleaved, **YoyConfig(
            year_column="year", value_column="value"
        ).model_dump(exclude_none=True))
        by_entity = {row["entity"]: row["yoy"] for row in result.to_dicts()}

        # Each entity's YoY is its own prior year: A: 100 -> 150 = 50%,
        # B: 200 -> 300 = 50%.
        assert by_entity["A"] == pytest.approx(50.0)
        assert by_entity["B"] == pytest.approx(50.0)

    def test_group_less_yoy_uses_a_differing_entity_baseline(self):
        from mkobi.models.transformation_configs import YoyConfig

        interleaved = pl.DataFrame(
            {
                "year": [2022, 2022, 2023, 2023],
                "entity": ["B", "A", "B", "A"],
                "value": [200, 100, 300, 400],
            }
        )

        result = _calculate_yoy(interleaved, **YoyConfig(
            year_column="year", value_column="value"
        ).model_dump(exclude_none=True))
        by_entity = {row["entity"]: row["yoy"] for row in result.to_dicts()}

        # A: (400-100)/100 = 300%, B: (300-200)/200 = 50%. Any global-order
        # shift would compare A 2023 against B 2022 or A 2022.
        assert by_entity["A"] == pytest.approx(300.0)
        assert by_entity["B"] == pytest.approx(50.0)


class TestCalculateAggregationsDictShape:
    """DP-009: the plain-dict contract of ``calculate_aggregations`` is unchanged.

    ``aggregate_data`` calls ``calculate_aggregations`` positionally with dicts.
    The worker's boundary fix must not alter the function's public signature or
    its dict tolerance.
    """

    def test_all_three_dicts_are_accepted_positionally(self):
        df = pl.DataFrame(
            {
                "year": [2022, 2023],
                "region": ["N", "N"],
                "value": [100, 150],
            }
        )

        result = calculate_aggregations(
            df,
            ["year", "region"],
            [{"column": "value", "function": "sum"}],
            {"year_column": "year", "value_column": "value_sum"},
            {"value_column": "value_sum"},
            [{"name": "double", "expr": "value_sum * 2"}],
        )

        assert "yoy" in result.columns
        assert "share" in result.columns
        assert "double" in result.columns

    def test_aggregate_data_positional_call_is_unaffected(self):
        df = pl.DataFrame({"category": ["A", "A", "B"], "value": [10, 20, 30]})
        graph_configs = [
            {
                "dimensions": ["category"],
                "metrics": [{"column": "value", "function": "sum"}],
            }
        ]

        result = aggregate_data(df, graph_configs)

        assert len(result) == 2
        assert all(isinstance(row, dict) for row in result)


class TestWorkerStoresAllThreeFields:
    """DP-009: the three structural fields store and run end to end.

    Drives the real worker (``process_csv_background``) over the real storage path
    (``StorageManager.save_aggregates``) with a config carrying each field, and
    reads the persisted metrics back. Each of the three fails today at the
    ``calculate_aggregations`` call boundary -- ``yoy_config`` and ``share_config``
    with ``TypeError`` from ``**`` on a model, ``custom_metrics`` with
    ``AttributeError`` from ``.get`` on a model. These are the three tripwires the
    finding needs.
    """

    @pytest.fixture
    async def agg_dashboard(self, async_db_session):
        """Dashboard with a year/region graph over the config's output columns.

        The graph names every derived column this class asserts (``yoy``,
        ``share``, ``double``) plus the config's ``revenue_sum``. A metric absent
        from a given run's frame is dropped by ``AggregationService`` rather than
        failing, so one graph serves all three tripwires. Each stored metric is
        named ``<column>_sum``.
        """
        from mkobi.db.repositories.dashboard_repo import DashboardRepository
        from mkobi.db.repositories.graph_repo import GraphRepository
        from mkobi.models.enums import GraphType

        dashboard = await DashboardRepository().create(
            db=async_db_session,
            name=f"tripwire_{uuid.uuid4().hex[:8]}",
            description="DP-009 tripwire",
        )
        graph = await GraphRepository().create(
            db=async_db_session,
            dashboard_id=dashboard.id,
            name=f"tripwire_graph_{uuid.uuid4().hex[:8]}",
            type=GraphType.TABLE,
            dimensions=["year", "region"],
            metrics=["revenue_sum", "yoy", "share", "double"],
            config={},
        )
        await async_db_session.commit()
        return {"dashboard": dashboard, "graph": graph}

    @staticmethod
    def _csv() -> bytes:
        """Two entities interleaved across two years."""
        return (
            b"year,region,revenue\n"
            b"2022,N,100\n"
            b"2022,S,200\n"
            b"2023,N,150\n"
            b"2023,S,300\n"
        )

    async def _run(self, async_db_session, dashboard_id, settings) -> list[dict]:
        import tempfile
        from pathlib import Path

        from mkobi.data.storage.manager import StorageManager
        from mkobi.workers.data_worker import process_csv_background

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write(self._csv())
            csv_path = Path(f.name)

        try:
            await process_csv_background(
                file_path_str=str(csv_path),
                task_id=str(uuid.uuid4()),
                dashboard_id_str=str(dashboard_id),
                processing_config_dict={"settings": settings, **settings},
                mode="overwrite",
                db_session=async_db_session,
            )
            await async_db_session.flush()
            return await StorageManager(async_db_session).get_aggregates(dashboard_id)
        finally:
            csv_path.unlink(missing_ok=True)

    async def test_yoy_config_stores_and_runs(
        self, async_db_session, agg_dashboard
    ) -> None:
        """Red before the fix: ``TypeError: argument after ** must be a mapping``."""
        settings = {
            "groupby": ["year", "region"],
            "aggregations": [{"column": "revenue", "function": "sum"}],
            "yoy_config": {"year_column": "year", "value_column": "revenue_sum"},
        }

        records = await self._run(
            async_db_session, agg_dashboard["dashboard"].id, settings
        )

        by_entity = {
            (record["dims"]["year"], record["dims"]["region"]): record["metrics"]
            for record in records
        }
        # N: 100 -> 150 is +50%; S: 200 -> 300 is +50%. Year dimes are stored as
        # their canonical string form.
        assert by_entity[("2023", "N")]["yoy_sum"] == pytest.approx(50.0)
        assert by_entity[("2023", "S")]["yoy_sum"] == pytest.approx(50.0)

    async def test_share_config_stores_and_runs(
        self, async_db_session, agg_dashboard
    ) -> None:
        """Red before the fix: ``TypeError`` from ``**share_config``."""
        settings = {
            "groupby": ["year", "region"],
            "aggregations": [{"column": "revenue", "function": "sum"}],
            "share_config": {"value_column": "revenue_sum"},
        }

        records = await self._run(
            async_db_session, agg_dashboard["dashboard"].id, settings
        )

        total = sum(record["metrics"]["revenue_sum_sum"] for record in records)
        for record in records:
            expected = record["metrics"]["revenue_sum_sum"] / total * 100
            assert record["metrics"]["share_sum"] == pytest.approx(expected)

    async def test_custom_metrics_stores_and_runs(
        self, async_db_session, agg_dashboard
    ) -> None:
        """Red before the fix: ``AttributeError: 'CustomMetricConfig' has no .get``."""
        settings = {
            "groupby": ["year", "region"],
            "aggregations": [{"column": "revenue", "function": "sum"}],
            "custom_metrics": [{"name": "double", "expr": "revenue_sum * 2"}],
        }

        records = await self._run(
            async_db_session, agg_dashboard["dashboard"].id, settings
        )

        for record in records:
            assert record["metrics"]["double_sum"] == pytest.approx(
                record["metrics"]["revenue_sum_sum"] * 2
            )


class TestAggregateData:
    """Tests for aggregate_data function."""

    def test_aggregate_data_single_graph(self):
        """Test aggregation for single graph config."""
        df = pl.DataFrame({
            "category": ["A", "A", "B"],
            "value": [10, 20, 30],
        })

        graph_configs = [
            {
                "dimensions": ["category"],
                "metrics": [
                    {"column": "value", "function": "sum"},
                ],
            },
        ]

        result = aggregate_data(df, graph_configs)

        assert len(result) == 2
        assert all(isinstance(r, dict) for r in result)

    def test_aggregate_data_multiple_graphs(self):
        """Test aggregation for multiple graph configs."""
        df = pl.DataFrame({
            "category": ["A", "B"],
            "value": [10, 20],
        })

        graph_configs = [
            {
                "dimensions": ["category"],
                "metrics": [{"column": "value", "function": "sum"}],
            },
            {
                "dimensions": [],
                "metrics": [{"column": "value", "function": "mean"}],
            },
        ]

        result = aggregate_data(df, graph_configs)

        # Should have results from both configs
        assert len(result) >= 2

    def test_aggregate_data_empty_config(self):
        """Test aggregation with empty config list."""
        df = pl.DataFrame({"value": [10, 20]})

        result = aggregate_data(df, [])

        assert result == []

    def test_aggregate_data_missing_dimensions(self):
        """Test aggregation skips config with missing dimensions."""
        df = pl.DataFrame({"value": [10, 20]})

        graph_configs = [
            {"dimensions": [], "metrics": [{"column": "value", "function": "sum"}]},
        ]

        result = aggregate_data(df, graph_configs)

        assert result == []

    def test_aggregate_data_to_dicts(self):
        """Test aggregation returns list of dicts."""
        df = pl.DataFrame({
            "category": ["A", "B"],
            "value": [10, 20],
        })

        graph_configs = [
            {
                "dimensions": ["category"],
                "metrics": [{"column": "value", "function": "sum"}],
            },
        ]

        result = aggregate_data(df, graph_configs)

        assert all(isinstance(item, dict) for item in result)


class TestLimitAfterAggregationStoredValue:
    """DP-008: the stored-value detector for the limit's truncation point.

    The truncation point must be asserted on the STORED value, not on a frame
    shape: a test that only counts rows passes against the unfixed code and
    proves nothing. These tests drive the real worker
    (``process_csv_background``) over the real storage path
    (``StorageManager.save_aggregates``) and read the persisted metrics back.

    The fixture is the audit report's DP-008 shape: ten raw rows in two regions
    (``N`` × 1..5, then ``S`` × 10..50), ``groupby=["region"]``,
    ``aggregations=[revenue sum]`` and a bare ``limit=3`` with no ``sort_by``.
    The first three raw rows are all region ``N``, so the unfixed premature
    truncation aggregates three rows and loses region ``S`` entirely
    (``{N: revenue_sum 6}``); the fix aggregates all ten and then truncates the
    two resulting groups (``{N: 15, S: 150}``). The stored value, not the row
    count, is the detector.
    """

    @pytest.fixture
    async def limit_dashboard(self, async_db_session) -> dict:
        """Dashboard with a region graph whose metric is the config's ``revenue_sum``.

        The processing config aggregates ``revenue`` to ``revenue_sum``, so the
        graph's metric must name the post-config column (``revenue_sum``); the
        pipeline's own per-graph aggregation then stores it under
        ``revenue_sum_sum``, which is the asserted stored key.
        """
        from mkobi.db.repositories.dashboard_repo import DashboardRepository
        from mkobi.db.repositories.graph_repo import GraphRepository
        from mkobi.models.enums import GraphType

        dashboard = await DashboardRepository().create(
            db=async_db_session,
            name=f"limit_after_agg_{uuid.uuid4().hex[:8]}",
            description="DP-008 stored-value detector",
        )
        graph = await GraphRepository().create(
            db=async_db_session,
            dashboard_id=dashboard.id,
            name=f"limit_graph_{uuid.uuid4().hex[:8]}",
            type=GraphType.TABLE,
            dimensions=["region"],
            metrics=["revenue_sum"],
            config={},
        )
        await async_db_session.commit()
        return {"dashboard": dashboard, "graph": graph}

    async def _store_with_config(
        self,
        async_db_session,
        dashboard_id,
        csv_content: bytes,
        settings: dict,
    ) -> dict[str, int]:
        """Run the worker synchronously over a temp CSV, return stored metrics.

        Returns a mapping of region -> the STORED metric value, read back from
        the database through StorageManager so the assertion is on persisted
        data, not on an intermediate frame.
        """
        import tempfile
        from pathlib import Path

        from mkobi.data.storage.manager import StorageManager
        from mkobi.workers.data_worker import process_csv_background

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            csv_path = Path(f.name)

        try:
            await process_csv_background(
                file_path_str=str(csv_path),
                task_id=str(uuid.uuid4()),
                dashboard_id_str=str(dashboard_id),
                # The producer (DataService._execute_upload) passes
                # ``dict(config_response.settings)`` -- a FLAT dict, all keys at
                # the top level. The worker reads CSV options from the same dict
                # and builds ``ProcessingConfig(**processing_config_dict)`` from
                # it, so ``groupby``/``limit`` sit at the top level too.
                processing_config_dict=settings,
                mode="overwrite",
                db_session=async_db_session,
            )
            await async_db_session.flush()
            records = await StorageManager(async_db_session).get_aggregates(
                dashboard_id
            )
        finally:
            csv_path.unlink(missing_ok=True)

        return {
            record["dims"]["region"]: record["metrics"]["revenue_sum_sum"]
            for record in records
        }

    @staticmethod
    def _audit_csv() -> bytes:
        """The audit report's ten rows in the exact order it uses.

        Rows: N × 1..5 first, then S × 10..50. A ``head(3)`` before aggregation
        therefore sees only region ``N``.
        """
        rows = [f"N,{n}\n".encode() for n in range(1, 6)]
        rows += [f"S,{s}\n".encode() for s in range(10, 51, 10)]
        return b"region,revenue\n" + b"".join(rows)

    async def test_stored_value_is_the_full_aggregate_not_the_truncation(
        self, async_db_session, limit_dashboard
    ) -> None:
        """The stored sum is over ALL ten rows, not the three the old head kept.

        Red before the fix: the stored set was ``{N: 6}`` -- region ``S`` was
        lost and region ``N`` summed only the first three raw rows. After the
        fix it is ``{N: 15, S: 150}``.
        """
        settings = {
            "groupby": ["region"],
            "aggregations": [{"column": "revenue", "function": "sum"}],
            "limit": 3,
        }

        stored = await self._store_with_config(
            async_db_session,
            limit_dashboard["dashboard"].id,
            self._audit_csv(),
            settings,
        )

        assert stored == {"N": 15, "S": 150}
        # Explicitly pin the unfixed value so a regression to premature
        # truncation is unmistakable.
        assert stored != {"N": 6}

    async def test_reversed_source_order_stores_the_same_value(
        self, async_db_session, limit_dashboard
    ) -> None:
        """Identical rows in reversed order store the same aggregate.

        The audit's second half: with the unfixed code the reversed source
        stored ``{N: 6}`` forward and ``{S: 120}`` reversed -- the same data,
        a different number. Post-fix both orders store ``{N: 15, S: 150}``.
        """
        settings = {
            "groupby": ["region"],
            "aggregations": [{"column": "revenue", "function": "sum"}],
            "limit": 3,
        }
        forward = self._audit_csv()
        reversed_rows = [f"S,{s}\n".encode() for s in range(10, 51, 10)]
        reversed_rows += [f"N,{n}\n".encode() for n in range(1, 6)]
        reversed_csv = b"region,revenue\n" + b"".join(reversed_rows)

        stored_forward = await self._store_with_config(
            async_db_session,
            limit_dashboard["dashboard"].id,
            forward,
            settings,
        )
        stored_reversed = await self._store_with_config(
            async_db_session,
            limit_dashboard["dashboard"].id,
            reversed_csv,
            settings,
        )

        assert stored_forward == stored_reversed == {"N": 15, "S": 150}

    async def test_complete_sort_by_makes_the_truncation_deterministic(
        self, async_db_session, limit_dashboard
    ) -> None:
        """A complete ``sort_by`` + ``limit`` keeps the top N groups by metric.

        With ``sort_by=["revenue_sum"]``, ``descending=True`` and ``limit=1``,
        the aggregated frame is ordered by the computed metric before the limit
        is applied, so the single surviving group is the largest-region total.
        This is the "top N by this metric" semantic and the case that must not
        regress.
        """
        settings = {
            "groupby": ["region"],
            "aggregations": [{"column": "revenue", "function": "sum"}],
            "sort_by": ["revenue_sum"],
            "descending": True,
            "limit": 1,
        }

        stored = await self._store_with_config(
            async_db_session,
            limit_dashboard["dashboard"].id,
            self._audit_csv(),
            settings,
        )

        assert stored == {"S": 150}


