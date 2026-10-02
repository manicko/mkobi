"""Tests for AggregationService business logic."""

from unittest.mock import MagicMock
from uuid import uuid4

import polars as pl
import pytest

from mkobi.models.enums import AggregationFunctionEnum, ErrorCode
from mkobi.models.filters import FilterRead
from mkobi.services.aggregation_service import AggregationService
from mkobi.utils.exceptions import AppException


class TestAggregationService:
    """Unit tests for AggregationService business logic."""

    @pytest.fixture
    def aggregation_service(self):
        """Create AggregationService instance."""
        return AggregationService()

    @pytest.fixture
    def sample_dataframe(self):
        """Create sample DataFrame for testing."""
        return pl.DataFrame({
            "category": ["A", "A", "B", "B", "C", "C"],
            "region": ["North", "South", "North", "South", "North", "South"],
            "sales": [100, 150, 200, 250, 300, 350],
            "profit": [10, 20, 30, 40, 50, 60],
        })

    def _make_graph_read(
        self, graph_id=None, dashboard_id=None, dimensions=None, metrics=None
    ):
        """Create a mock GraphRead-like object for testing."""
        obj = MagicMock()
        obj.id = graph_id or uuid4()
        obj.dashboard_id = dashboard_id or uuid4()
        obj.dimensions = dimensions or ["category"]
        obj.metrics = metrics or ["sales"]
        return obj

    def _make_filter_read(self, name, filter_id=None):
        """Create FilterRead model for testing."""
        return FilterRead(
            id=filter_id or uuid4(),
            name=name,
            type="select",
            config={"field": name},
            created_at=None,
        )

    # --- aggregate_for_dashboard tests ---

    async def test_aggregate_for_dashboard_basic(
        self, aggregation_service, sample_dataframe
    ):
        """Test basic aggregation with one graph."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
        )

        assert len(results) > 0
        assert all("dashboard_id" in r for r in results)
        assert all("graph_id" in r for r in results)
        assert all("dims" in r for r in results)
        assert all("metrics" in r for r in results)

    async def test_aggregate_for_dashboard_multiple_graphs(
        self, aggregation_service, sample_dataframe
    ):
        """Test aggregation with multiple graphs."""
        dashboard_id = uuid4()
        graph1 = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )
        graph2 = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["region"],
            metrics=["profit"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph1, graph2],
            dashboard_filters=[],
        )

        # Should have results from both graphs
        assert len(results) >= 2

    async def test_aggregate_for_dashboard_with_dashboard_filters(
        self, aggregation_service, sample_dataframe
    ):
        """Test aggregation includes dashboard filter dimensions."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )
        dashboard_filter = self._make_filter_read(name="region")

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[dashboard_filter],
        )

        assert len(results) > 0
        # Region should be included in dimensions
        for r in results:
            assert "dims" in r

    async def test_aggregate_for_dashboard_deduplicates_shared_filter_name(
        self, aggregation_service, sample_dataframe
    ):
        """Test a graph dimension and filter sharing a name do not duplicate the key.

        Before the de-duplication fix the group key became ["region", "region"],
        which made Polars raise DuplicateError and every upload fail.
        """
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["region"],
            metrics=["sales"],
        )
        dashboard_filter = self._make_filter_read(name="region")

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[dashboard_filter],
        )

        # Aggregation completes and yields exactly one row per distinct region.
        assert len(results) == 2
        regions = sorted(r["dims"]["region"] for r in results)
        assert regions == ["North", "South"]
        for r in results:
            assert list(r["dims"].keys()) == ["region"]

    async def test_aggregate_for_dashboard_dedup_preserves_first_seen_order(
        self, aggregation_service, sample_dataframe
    ):
        """Test the de-duplicated group key keeps graph dimensions first.

        The group key is de-duplicated in first-seen order, so graph dimensions
        stay ahead of filter-only names. An unordered construct such as set()
        would lose this order; the dims key order exposes it.
        """
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["region", "category"],
            metrics=["sales"],
        )
        dashboard_filter = self._make_filter_read(name="category")

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[dashboard_filter],
        )

        assert len(results) > 0
        # Graph dimension "region" precedes "category"; "category" is not repeated.
        for r in results:
            assert list(r["dims"].keys()) == ["region", "category"]

    async def test_aggregate_for_dashboard_no_overlap_is_unchanged(
        self, aggregation_service, sample_dataframe
    ):
        """Test a dashboard with no overlapping filter keeps dims unchanged."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )
        dashboard_filter = self._make_filter_read(name="region")

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[dashboard_filter],
        )

        # No overlap: both distinct dims are kept in first-seen order, so the
        # de-duplication is a no-op for the common case (3 categories x 2 regions).
        assert len(results) == 6
        for r in results:
            assert list(r["dims"].keys()) == ["category", "region"]

    async def test_aggregate_for_dashboard_skips_missing_columns(
        self, aggregation_service, sample_dataframe
    ):
        """Test graph with columns not in DataFrame is skipped."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["nonexistent_column"],
            metrics=["sales"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
        )

        # Should skip graph with no valid columns
        assert results == []

    async def test_aggregate_for_dashboard_skips_no_metrics(
        self, aggregation_service, sample_dataframe
    ):
        """Test graph with no valid metric columns is skipped."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["nonexistent_metric"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
        )

        assert results == []

    async def test_aggregate_for_dashboard_returns_proper_structure(
        self, aggregation_service, sample_dataframe
    ):
        """Test aggregation returns correct data structure."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
        )

        for r in results:
            assert isinstance(r["dims"], dict)
            assert isinstance(r["metrics"], dict)
            # All dim values should be native types (str, int, float, bool)
            for v in r["dims"].values():
                assert isinstance(v, (str, int, float, bool))

    # --- extract_filter_values tests ---

    async def test_extract_filter_values_basic(self, aggregation_service):
        """Test extracting filter values from aggregated records."""
        records = [
            {"dims": {"region": "North", "status": "active"}},
            {"dims": {"region": "South", "status": "inactive"}},
            {"dims": {"region": "North", "status": "active"}},
        ]

        filter_names = ["region", "status"]
        result = await aggregation_service.extract_filter_values(records, filter_names)

        assert "region" in result
        assert "status" in result
        assert sorted(result["region"]) == ["North", "South"]
        assert sorted(result["status"]) == ["active", "inactive"]

    async def test_extract_filter_values_empty_records(self, aggregation_service):
        """Test extraction with empty records list."""
        result = await aggregation_service.extract_filter_values([], ["region"])
        assert result == {"region": []}

    async def test_extract_filter_values_missing_filter_in_dims(
        self, aggregation_service
    ):
        """Test extraction when some filters not present in records."""
        records = [
            {"dims": {"region": "North"}},
        ]

        filter_names = ["region", "missing_filter"]
        result = await aggregation_service.extract_filter_values(records, filter_names)

        assert sorted(result["region"]) == ["North"]
        assert result["missing_filter"] == []

    async def test_extract_filter_values_no_dims_key(self, aggregation_service):
        """Test extraction handles records without dims key gracefully."""
        records = [
            {"metrics": {"sales": 100}},
            {"dims": {"region": "South"}},
        ]

        filter_names = ["region"]
        result = await aggregation_service.extract_filter_values(records, filter_names)

        assert sorted(result["region"]) == ["South"]

    async def test_extract_filter_values_sorted_result(self, aggregation_service):
        """Test that extracted values are sorted."""
        records = [
            {"dims": {"region": "C"}},
            {"dims": {"region": "A"}},
            {"dims": {"region": "B"}},
        ]

        result = await aggregation_service.extract_filter_values(records, ["region"])

        assert result["region"] == ["A", "B", "C"]

    # --- Integration test ---

    async def test_full_aggregation_flow(self, aggregation_service):
        """Test full aggregation flow from DataFrame to records."""
        df = pl.DataFrame({
            "product": ["A", "A", "B"],
            "sales": [100, 200, 150],
            "quantity": [10, 20, 15],
        })

        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["product"],
            metrics=["sales", "quantity"],
        )

        records = await aggregation_service.aggregate_for_dashboard(
            df=df,
            graphs=[graph],
            dashboard_filters=[],
            metric_agg="sum",
        )

        assert len(records) == 2  # Two products

        # Check aggregation values
        record_a = next(r for r in records if r["dims"]["product"] == "A")
        assert record_a["metrics"]["sales_sum"] == 300
        assert record_a["metrics"]["quantity_sum"] == 30

    async def test_aggregate_for_dashboard_mean_aggregation(
        self, aggregation_service, sample_dataframe
    ):
        """Test mean aggregation type."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
            metric_agg="mean",
        )

        assert len(results) > 0
        for r in results:
            # Check that metric key uses "mean" suffix
            assert any(k.endswith("_mean") for k in r["metrics"].keys())

    async def test_aggregate_for_dashboard_min_aggregation(
        self, aggregation_service, sample_dataframe
    ):
        """Test min aggregation type."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
            metric_agg="min",
        )

        assert len(results) > 0
        for r in results:
            # Check that metric key uses "min" suffix
            assert any(k.endswith("_min") for k in r["metrics"].keys())

    async def test_aggregate_for_dashboard_max_aggregation(
        self, aggregation_service, sample_dataframe
    ):
        """Test max aggregation type."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
            metric_agg="max",
        )

        assert len(results) > 0
        for r in results:
            # Check that metric key uses "max" suffix
            assert any(k.endswith("_max") for k in r["metrics"].keys())

    async def test_aggregate_for_dashboard_count_aggregation(
        self, aggregation_service, sample_dataframe
    ):
        """Test count aggregation type."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
            metric_agg="count",
        )

        assert len(results) > 0
        for r in results:
            # Check that metric key uses "count" suffix and values are counts
            metric_key = next(k for k in r["metrics"].keys() if k.endswith("_count"))
            assert r["metrics"][metric_key] == 2  # Two rows per category in sample data

    @pytest.mark.parametrize(
        ("metric_agg", "expected_values"),
        [
            ("median", {"A": 125.0, "B": 225.0, "C": 325.0}),
            ("std", {"A": 35.35533905932738, "B": 35.35533905932738, "C": 35.35533905932738}),
            ("var", {"A": 1250.0, "B": 1250.0, "C": 1250.0}),
            ("first", {"A": 100, "B": 200, "C": 300}),
            ("last", {"A": 150, "B": 250, "C": 350}),
        ],
    )
    async def test_aggregate_for_dashboard_newly_reachable_members_use_own_function(
        self, aggregation_service, sample_dataframe, metric_agg, expected_values
    ):
        """DP-018: every declared member stores its own value, not a sum.

        Before the fix ``_agg_fn_map`` held only five entries and unknown names
        fell back to sum while the output column kept the requested name, so a
        dashboard configured for ``median`` stored a sum under ``sales_median``.
        Each row here asserts the stored value is the named function's value.
        """
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
            metric_agg=metric_agg,
        )

        assert len(results) == 3
        by_category = {r["dims"]["category"]: r["metrics"] for r in results}
        for category, expected in expected_values.items():
            # The key keeps the requested name and the value is that function's.
            assert by_category[category][f"sales_{metric_agg}"] == pytest.approx(expected)

    async def test_aggregate_for_dashboard_unknown_agg_falls_back_to_sum(
        self, aggregation_service, sample_dataframe
    ):
        """An unrecognised aggregation name raises VALIDATION_ERROR.

        Reversal of previously-asserted behaviour: this test was named
        ``..._falls_back_to_sum`` and asserted that an unknown name stored a sum
        under ``sales_unknown_func``. That silence *was* DP-018. The ruled
        policy resolves the name against ``AggregationFunctionEnum`` and raises
        ``AppException`` with ``VALIDATION_ERROR`` when it is not a member, so
        the test name is kept and its expectation is inverted.
        """
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        with pytest.raises(AppException) as exc_info:
            await aggregation_service.aggregate_for_dashboard(
                df=sample_dataframe,
                graphs=[graph],
                dashboard_filters=[],
                metric_agg="unknown_func",
            )

        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR

    async def test_aggregate_for_dashboard_normalises_case_and_whitespace(
        self, aggregation_service, sample_dataframe
    ):
        """A differently-cased, padded but otherwise valid name is accepted."""
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
            metric_agg="  MEAN  ",
        )

        assert len(results) == 3
        for r in results:
            assert any(k.endswith("_mean") for k in r["metrics"].keys())

    async def test_aggregate_for_dashboard_accepts_enum_member(
        self, aggregation_service, sample_dataframe
    ):
        """The enum reaches the function map both as enum and as string.

        ``AggregationFunctionEnum`` is a ``StrEnum`` and compares equal to its
        value, so a string-keyed lookup cannot tell an enum member from a string
        and a type regression would be invisible. This asserts an enum member is
        accepted and produces the same result as its string value.
        """
        dashboard_id = uuid4()
        graph = self._make_graph_read(
            graph_id=uuid4(),
            dashboard_id=dashboard_id,
            dimensions=["category"],
            metrics=["sales"],
        )

        enum_results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
            metric_agg=AggregationFunctionEnum.MEAN,
        )
        string_results = await aggregation_service.aggregate_for_dashboard(
            df=sample_dataframe,
            graphs=[graph],
            dashboard_filters=[],
            metric_agg="mean",
        )

        # group_by does not guarantee row order, so compare by category.
        enum_by_category = {r["dims"]["category"]: r["metrics"] for r in enum_results}
        string_by_category = {r["dims"]["category"]: r["metrics"] for r in string_results}
        assert enum_by_category == string_by_category
        expected = {"A": 125.0, "B": 225.0, "C": 325.0}
        for category, metrics in enum_by_category.items():
            assert metrics["sales_mean"] == pytest.approx(expected[category])

    # --- _apply_chart_sorting tests ---

    def test_apply_chart_sorting_x_chronological(self, aggregation_service):
        """Test chronological x-axis sorting using year/month columns."""
        df = pl.DataFrame({
            "year": [2024, 2024, 2023, 2023],
            "month": [3, 1, 12, 1],
            "month_label": ["Mar 2024", "Jan 2024", "Dec 2023", "Jan 2023"],
            "sales_sum": [100.0, 200.0, 300.0, 400.0],
        })

        result = aggregation_service._apply_chart_sorting(
            df,
            x_col="month_label",
            color_col=None,
            metric_cols=["sales"],
            metric_agg="sum",
        )

        # Should be sorted by year, month ascending
        assert result["month_label"][0] == "Jan 2023"
        assert result["month_label"][1] == "Dec 2023"
        assert result["month_label"][2] == "Jan 2024"
        assert result["month_label"][3] == "Mar 2024"

    def test_apply_chart_sorting_color_by_metric(self, aggregation_service):
        """Test color dimension sorting by total metric (descending)."""
        df = pl.DataFrame({
            "year": [2024, 2024, 2024, 2024],
            "month": [1, 1, 1, 1],
            "brand": ["A", "B", "A", "B"],
            "sales_sum": [100.0, 500.0, 200.0, 600.0],
        })

        result = aggregation_service._apply_chart_sorting(
            df,
            x_col="month_label",
            color_col="brand",
            metric_cols=["sales"],
            metric_agg="sum",
        )

        # Brand B has larger total (1100) than A (300), so B should come first
        # Within each brand, months are in order
        assert result["brand"][0] == "B"  # B has total 1100
        assert result["brand"][1] == "B"
        assert result["brand"][2] == "A"  # A has total 300
        assert result["brand"][3] == "A"

    def test_apply_chart_sorting_combined(self, aggregation_service):
        """Test combined x-axis chronological and color metric sorting."""
        df = pl.DataFrame({
            "year": [2024, 2024, 2023, 2023, 2024, 2024, 2023, 2023],
            "month": [1, 1, 12, 12, 3, 3, 11, 11],
            "brand": ["A", "B", "A", "B", "A", "B", "A", "B"],
            "sales_sum": [100.0, 500.0, 200.0, 600.0, 150.0, 550.0, 250.0, 650.0],
        })

        result = aggregation_service._apply_chart_sorting(
            df,
            x_col="month_label",
            color_col="brand",
            metric_cols=["sales"],
            metric_agg="sum",
        )

        # Brand B total = 500+600+550+650 = 2300, Brand A total = 100+200+150+250 = 700
        # B should come first (larger total), then A
        # Within each brand: ascending by year then month
        # For B: (2023, 11)=650, (2023, 12)=600, (2024, 1)=500, (2024, 3)=550
        # For A: (2023, 11)=250, (2023, 12)=200, (2024, 1)=100, (2024, 3)=150
        assert result["brand"][0] == "B"
        assert result["year"][0] == 2023
        assert result["month"][0] == 11

        assert result["brand"][1] == "B"
        assert result["year"][1] == 2023
        assert result["month"][1] == 12

        assert result["brand"][2] == "B"
        assert result["year"][2] == 2024
        assert result["month"][2] == 1

        assert result["brand"][3] == "B"
        assert result["year"][3] == 2024
        assert result["month"][3] == 3

        assert result["brand"][4] == "A"
        assert result["year"][4] == 2023
        assert result["month"][4] == 11

        assert result["brand"][5] == "A"
        assert result["year"][5] == 2023
        assert result["month"][5] == 12

        assert result["brand"][6] == "A"
        assert result["year"][6] == 2024
        assert result["month"][6] == 1

        assert result["brand"][7] == "A"
        assert result["year"][7] == 2024
        assert result["month"][7] == 3
