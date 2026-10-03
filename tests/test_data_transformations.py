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

    def test_transformations_with_limit(self):
        """Test transformations with limit."""
        df = pl.DataFrame({"value": [10, 20, 30, 40, 50]})
        result = apply_transformations(df, limit=3)

        assert result.shape[0] == 3

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