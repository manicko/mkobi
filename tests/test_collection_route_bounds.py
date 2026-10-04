"""PRF-6 / VAL-11-007: every collection-returning GET is bounded.

Exactly one collection surface was bounded before this change
(``processing_logs.py``). This module holds the invariant that stops the
defect class from returning: a meta-test that introspects the live application
and requires **every** GET route whose successful response is a collection to
declare a bounded ``limit`` parameter with a maximum. Per-endpoint tests would
not catch a *new* unbounded collection route; this does.

Exemptions are listed explicitly below, each with a justification. An exemption
is the only way a collection route may skip the bound, and adding one is a
deliberate, reviewable act.
"""

from typing import Any, get_origin

from fastapi import FastAPI
from fastapi.routing import APIRoute

from mkobi.main import app as application
from mkobi.models.data import FilterValuesResponse


# Routes whose successful response is a collection but that are deliberately
# exempt from the ``limit``/maximum rule. Each entry is (method, path) and must
# carry a justification comment.
_COLLECTION_ROUTE_EXEMPTIONS: set[tuple[str, str]] = {
    # The dashboard aggregate read is already bounded by its own per-graph and
    # dashboard-wide row caps (``DATA__MAX_ROWS_PER_GRAPH`` /
    # ``DATA__MAX_ROWS_TOTAL``); it is not a paginated collection surface and
    # the brief explicitly leaves it alone.
    ("GET", "/api/v1/data/aggregated"),
}

# Wrapper response models whose payload *is* a collection, so the route that
# returns them is a collection surface even though the annotation is a model
# rather than a ``list[...]``. Listed explicitly so a detail model that merely
# happens to carry a list field (``GraphRead.dimensions``) is not mistaken for
# a collection surface.
_COLLECTION_WRAPPER_MODELS: tuple[type, ...] = (FilterValuesResponse,)

# Decorator/signature markers: a route whose bounded response needs no
# ``limit`` query parameter because its cardinality is structurally fixed.
# None today.
_STRUCTURALLY_BOUNDED_ROUTES: set[tuple[str, str]] = set()


def _is_collection_annotation(annotation: Any) -> bool:
    """Return True when an annotation is a ``list[...]``/``Sequence[...]``."""
    origin = get_origin(annotation)
    if origin in (list, tuple, set, frozenset):
        return True
    # Unwrap ``Annotated[X, ...]`` wrappers.
    if origin is not None and get_origin(origin) is not None:
        return _is_collection_annotation(origin)
    return False


def _model_has_collection_field(model: Any) -> bool:
    """True when a declared collection-wrapper model carries a list field."""
    if model not in _COLLECTION_WRAPPER_MODELS:
        return False
    fields = getattr(model, "model_fields", None)
    if not fields:
        return False
    return any(_is_collection_annotation(f.annotation) for f in fields.values())


def _route_return_annotation(route: APIRoute) -> Any:
    """Return the declared return annotation of the endpoint function."""
    return getattr(route.endpoint, "__annotations__", {}).get("return")


def _response_model_is_collection(route: APIRoute) -> bool:
    """Return True when the route's declared response model is a collection.

    A list-typed response is a collection; so is an explicitly registered
    collection-wrapper model (e.g. ``FilterValuesResponse.values``), because
    the interesting cardinality is the list it wraps.
    """
    model = route.response_model
    if model is None:
        return False
    if _is_collection_annotation(model):
        return True
    return _model_has_collection_field(model)


def _collection_routes(app: FastAPI) -> list[APIRoute]:
    """Every GET route whose successful response is, or wraps, a collection."""
    routes: list[APIRoute] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if "GET" not in (route.methods or set()):
            continue
        if _response_model_is_collection(route) or _is_collection_annotation(
            _route_return_annotation(route)
        ):
            routes.append(route)
    return routes


def _limit_parameter(route: APIRoute):
    """Return the ``limit`` Query parameter of a route, or None."""
    for param in route.dependant.query_params:
        if param.name == "limit":
            return param
    return None


def _has_upper_bound(route: APIRoute) -> bool:
    """True when the route's ``limit`` parameter declares a numeric maximum."""
    limit = _limit_parameter(route)
    if limit is None:
        return False
    # FastAPI folds ``le=`` into the parameter's ``metadata`` as an ``Le``
    # constraint object rather than exposing it as a ``le`` attribute.
    for meta in getattr(limit.field_info, "metadata", ()):
        if type(meta).__name__ == "Le" and getattr(meta, "le", None) is not None:
            return True
    return False


class TestCollectionRoutesAreBounded:
    """Every collection-returning GET declares a bounded ``limit``."""

    def test_census_finds_the_collection_routes(self) -> None:
        """The census is not vacuous: it finds more than one collection route."""
        routes = _collection_routes(application)
        assert len(routes) > 1, (
            "the census found no collection routes; the detector has drifted "
            "from the app's response modelling"
        )

    def test_every_collection_route_has_a_bounded_limit(self) -> None:
        """No collection route is left unbounded without an exemption."""
        offenders: list[str] = []
        for route in _collection_routes(application):
            key = ("GET", route.path)
            if key in _COLLECTION_ROUTE_EXEMPTIONS:
                continue
            if key in _STRUCTURALLY_BOUNDED_ROUTES:
                continue
            if not _has_upper_bound(route):
                offenders.append(route.path)
        assert not offenders, (
            "unbounded collection GET routes: "
            + ", ".join(sorted(offenders))
            + " — each must declare a `limit` with `le=<max>`, or be added to "
            "_COLLECTION_ROUTE_EXEMPTIONS with a justification"
        )



class TestDimsValuesBound:
    """``get_dims_values`` respects its bound and keeps its distinct values."""

    async def test_get_dims_values_respects_its_bound(
        self, async_db_session, test_user: dict
    ) -> None:
        """A bounded distinct scan returns at most ``limit`` values."""
        from mkobi.db.repositories.aggregated_data_repo import (
            AggregatedDataRepository,
        )
        from tests.test_aggregate_row_caps import _setup_dashboard_with_aggregates

        _, graph_ids = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows_per_graph={"G": 5}
        )
        repo = AggregatedDataRepository()

        bounded = await repo.get_dims_values(
            graph_ids["G"], "category", async_db_session, limit=2
        )
        all_values = await repo.get_dims_values(
            graph_ids["G"], "category", async_db_session
        )

        assert len(bounded) == 2
        assert len(all_values) == 5
        # The bound preserves the deterministic first-seen order.
        assert bounded == all_values[:2]

    async def test_get_dims_values_returns_correct_distinct_values(
        self, async_db_session, test_user: dict
    ) -> None:
        """The bound never invents or drops a distinct value within it."""
        from mkobi.db.repositories.aggregated_data_repo import (
            AggregatedDataRepository,
        )
        from tests.test_aggregate_row_caps import _setup_dashboard_with_aggregates

        _, graph_ids = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows_per_graph={"G": 4}
        )
        repo = AggregatedDataRepository()

        values = await repo.get_dims_values(
            graph_ids["G"], "category", async_db_session
        )

        assert values == [f"G-cat-{i}" for i in range(4)]

    async def test_count_dims_values_equals_real_distinct_count(
        self, async_db_session, test_user: dict
    ) -> None:
        """``count_dims_values`` matches the true distinct-value count."""
        from mkobi.db.repositories.aggregated_data_repo import (
            AggregatedDataRepository,
        )
        from tests.test_aggregate_row_caps import _setup_dashboard_with_aggregates

        _, graph_ids = await _setup_dashboard_with_aggregates(
            async_db_session, test_user["id"], rows_per_graph={"G": 7}
        )
        repo = AggregatedDataRepository()

        total = await repo.count_dims_values(
            graph_ids["G"], "category", async_db_session
        )
        all_values = await repo.get_dims_values(
            graph_ids["G"], "category", async_db_session
        )

        assert total == 7
        assert total == len(all_values)


class TestFilterValuesTotal:
    """``FilterValuesResponse.total_values`` equals the real distinct count."""

    async def test_filter_values_response_carries_a_true_total(
        self, authenticated_client, async_db_session, test_user: dict
    ) -> None:
        """The endpoint reports the untruncated total and a bounded page."""
        from mkobi.db.models.dashboard_filter_values import DashboardFilterValue
        from mkobi.db.repositories.access_repo import AccessRepository
        from mkobi.db.repositories.dashboard_repo import DashboardRepository
        from mkobi.models.enums import DashboardPermission
        from mkobi.services.dashboard_service import DashboardService

        ds = DashboardService(DashboardRepository(), AccessRepository())
        dashboard = await ds.create_dashboard(
            name="filter-values-total",
            config={"graph_types": ["bar"]},
            owner_id=test_user["id"],
            db=async_db_session,
        )
        await AccessRepository().grant_access(
            db=async_db_session,
            user_id=test_user["id"],
            dashboard_id=dashboard.id,
            permission=DashboardPermission.VIEW,
        )
        async_db_session.add_all(
            [
                DashboardFilterValue(
                    dashboard_id=dashboard.id,
                    filter_name="region",
                    filter_value=f"r{i}",
                )
                for i in range(5)
            ]
        )
        await async_db_session.commit()

        response = await authenticated_client.get(
            f"/dashboards/{dashboard.id}/filter-values",
            params={"filter_name": "region", "limit": 2},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total_values"] == 5
        assert len(body["values"]) == 2
        assert body["values"] == ["r0", "r1"]


class TestProcessingLogsUnchanged:
    """``processing_logs``' existing bounded behaviour is unchanged."""

    def test_processing_logs_route_keeps_its_bound(self) -> None:
        """The exemplar still declares ``limit`` with a ``le`` maximum of 1000."""
        target = None
        for route in _collection_routes(application):
            if route.path.endswith("/logs/"):
                target = route
                break
        assert target is not None, "processing logs collection route not found"

        limit = _limit_parameter(target)
        assert limit is not None
        maxima = [
            meta.le
            for meta in getattr(limit.field_info, "metadata", ())
            if type(meta).__name__ == "Le"
        ]
        assert maxima == [1000]
