"""PRF-5 / VAL-11-004: the ``filters`` query payload is bounded and validated.

The ``filters`` parameter is a JSON-encoded object whose keys become one
``->>`` equality each in the aggregate query. Nothing previously bounded its
width. These tests pin the four application-layer bounds and confirm that a
valid payload still returns exactly the rows it returned before.
"""

import json

from fastapi import status
from httpx import AsyncClient

from mkobi.models.data import (
    MAX_FILTER_KEYS,
    MAX_FILTER_KEY_LENGTH,
    MAX_FILTER_PAYLOAD_BYTES,
    MAX_FILTER_VALUE_LENGTH,
)
from tests.test_aggregate_row_caps import _setup_dashboard_with_aggregates


async def _dashboard_with_rows(
    async_db_session, owner_id, *, rows: int
) -> tuple[str, str]:
    dashboard_id, graph_ids = await _setup_dashboard_with_aggregates(
        async_db_session, owner_id, rows_per_graph={"Filter": rows}
    )
    return str(dashboard_id), str(graph_ids["Filter"])


def _url(dashboard_id: str, graph_id: str) -> str:
    return "/data/aggregated"


def _params(dashboard_id: str, graph_id: str, filters: str) -> dict[str, str]:
    return {
        "dashboard_id": dashboard_id,
        "graph_id": graph_id,
        "filters": filters,
    }


class TestFilterPayloadBounds:
    """Each bound rejects with the RFC 7807 VALIDATION_ERROR body."""

    async def test_twenty_keys_accepted(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Exactly the maximum key count is accepted (200)."""
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=1
        )
        payload = {f"k{i}": f"v{i}" for i in range(MAX_FILTER_KEYS)}

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(dashboard_id, graph_id, json.dumps(payload)),
        )

        assert response.status_code == status.HTTP_200_OK

    async def test_twenty_one_keys_rejected(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """One key over the maximum is rejected with 422 and the RFC 7807 body."""
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=1
        )
        payload = {f"k{i}": f"v{i}" for i in range(MAX_FILTER_KEYS + 1)}

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(dashboard_id, graph_id, json.dumps(payload)),
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert body["status"] == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_over_long_key_name_rejected(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A key name one character over the maximum is rejected."""
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=1
        )
        key = "k" * (MAX_FILTER_KEY_LENGTH + 1)

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(dashboard_id, graph_id, json.dumps({key: "v"})),
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_over_long_value_rejected(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A value one character over the maximum is rejected."""
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=1
        )
        value = "v" * (MAX_FILTER_VALUE_LENGTH + 1)

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(dashboard_id, graph_id, json.dumps({"region": value})),
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_over_sized_payload_rejected(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A serialised payload one byte over the maximum is rejected.

        Each value stays inside the per-value ceiling, so only the whole-payload
        bound can reject this request.
        """
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=1
        )
        # Twenty values of 256 chars: exactly at the key-count ceiling and each
        # value exactly at the per-value ceiling, but comfortably over the 4 KB
        # whole-payload ceiling once serialised.
        payload = {
            f"k{i}": "x" * MAX_FILTER_VALUE_LENGTH for i in range(MAX_FILTER_KEYS)
        }
        serialised = json.dumps(payload)
        assert len(serialised.encode("utf-8")) > MAX_FILTER_PAYLOAD_BYTES
        assert len(payload) <= MAX_FILTER_KEYS

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(dashboard_id, graph_id, serialised),
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_malformed_json_still_rejected(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """Malformed JSON is still rejected as before the bound was added."""
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=1
        )

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(dashboard_id, graph_id, "{not-json"),
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json()["code"] == "VALIDATION_ERROR"

    async def test_valid_payload_returns_the_same_rows(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A valid payload returns exactly the rows it returned before."""
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=5
        )

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id,
                graph_id,
                json.dumps({"category": "Filter-cat-0"}),
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]
        assert graph["returned_rows"] == 1
        assert graph["total_rows"] == 1
        assert graph["data"][0]["category"] == "Filter-cat-0"

    async def test_multiselect_returns_the_union_of_the_scalar_results(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A two-value list matches the union of the two scalar results.

        Discriminates the membership branch: today a list is a 422. Set
        equality, not a count, so an "any non-empty list" stub cannot pass.
       """
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=5
        )

        multi = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id,
                graph_id,
                json.dumps({"category": ["Filter-cat-1", "Filter-cat-3"]}),
            ),
        )
        assert multi.status_code == status.HTTP_200_OK
        graph = multi.json()["graphs"][0]
        assert graph["returned_rows"] == 2
        assert graph["total_rows"] == 2
        assert sorted(r["category"] for r in graph["data"]) == [
            "Filter-cat-1",
            "Filter-cat-3",
        ]

        # Cross-check the same two values as scalars, so "union" is proven.
        for value in ("Filter-cat-1", "Filter-cat-3"):
            scalar = await authenticated_client.get(
                _url(dashboard_id, graph_id),
                params=_params(
                    dashboard_id, graph_id, json.dumps({"category": value})
                ),
            )
            assert scalar.status_code == status.HTTP_200_OK
            assert scalar.json()["graphs"][0]["returned_rows"] == 1

    async def test_single_element_multiselect_matches_that_element(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A one-element list matches exactly that element."""
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=5
        )

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id,
                graph_id,
                json.dumps({"category": ["Filter-cat-2"]}),
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]
        assert graph["returned_rows"] == 1
        assert graph["data"][0]["category"] == "Filter-cat-2"

    async def test_empty_multiselect_is_not_a_constraint(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """An empty list imposes no constraint, returning every row.

        Pins the chosen semantics: ``in_([])`` compiles to an always-false
        predicate and would return zero rows, blanking every chart.
        """
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=5
        )

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id, graph_id, json.dumps({"category": []})
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]
        assert graph["returned_rows"] == 5
        assert graph["total_rows"] == 5

    async def test_multiselect_does_not_match_an_unlisted_value(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A list with one matching and one unknown value matches only the known."""
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=5
        )

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id,
                graph_id,
                json.dumps({"category": ["Filter-cat-0", "Nope"]}),
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]
        assert graph["returned_rows"] == 1
        assert graph["data"][0]["category"] == "Filter-cat-0"

    async def test_scalar_filter_result_is_unchanged(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """The compatibility floor: a scalar filter returns the same rows.

        This passes before and after the branch by design; it exists to fail if
        the scalar expression is ever touched.
        """
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=5
        )

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id,
                graph_id,
                json.dumps({"category": "Filter-cat-4"}),
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        graph = response.json()["graphs"][0]
        assert graph["returned_rows"] == 1
        assert graph["total_rows"] == 1
        assert graph["data"][0] == {
            "category": "Filter-cat-4",
            "revenue": 104,
        }

    async def test_list_value_element_respects_the_value_length_bound(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """An over-long list element is rejected, naming the value-length bound.

        Discriminates the per-element bound: after a naive widening the list
        would measure its repr and this would return 200. The route wraps the
        model's ``ValidationError`` into a generic 422, so the bound's own
        message is pinned against the model -- the thing that enforces it --
        rather than the discarded route body.
        """
        from pydantic import ValidationError

        from mkobi.models.data import AggregatedFiltersRequest

        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=1
        )
        element = "v" * (MAX_FILTER_VALUE_LENGTH + 1)

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id, graph_id, json.dumps({"category": [element]})
            ),
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json()["code"] == "VALIDATION_ERROR"

        try:
            AggregatedFiltersRequest(filters={"category": [element]})
        except ValidationError as exc:
            message = exc.errors()[0]["msg"]
        else:  # pragma: no cover - the bound is enforced by construction
            raise AssertionError("an over-long list element was accepted")
        assert "category" in message
        assert str(MAX_FILTER_VALUE_LENGTH) in message


async def _dashboard_declaring_filters(
    async_db_session,
    owner_id,
    *,
    filters: list[dict[str, object]],
    rows: int = 5,
) -> tuple[str, str]:
    """Create a dashboard whose stored config declares ``filters``.

    Mirrors ``_setup_dashboard_with_aggregates`` (same service calls, grant and
    commit) with an extra ``filters`` config argument, so the read backstop has
    a declared type to compare against. The shared helper hard-codes a config
    with no ``filters`` key and is left unmodified.
    """
    from uuid import uuid4

    from mkobi.data.storage.manager import StorageManager
    from mkobi.db.repositories.access_repo import AccessRepository
    from mkobi.db.repositories.dashboard_repo import DashboardRepository
    from mkobi.db.repositories.graph_repo import GraphRepository
    from mkobi.models.enums import DashboardPermission
    from mkobi.models.graph import GraphCreate
    from mkobi.services.dashboard_service import DashboardService
    from mkobi.services.graph_service import GraphService

    ds = DashboardService(DashboardRepository(), AccessRepository())
    dashboard = await ds.create_dashboard(
        name=f"filter-backstop-{uuid4().hex[:8]}",
        config={"graph_types": ["bar"], "filters": filters},
        owner_id=owner_id,
        db=async_db_session,
    )

    graph_service = GraphService(GraphRepository())
    graph = await graph_service.create(
        GraphCreate(
            name="Filter",
            type="bar",
            dashboard_id=dashboard.id,
            config={"title": "Filter"},
            dimensions=["category"],
            metrics=["revenue"],
        ),
        db=async_db_session,
    )

    await AccessRepository().grant_access(
        db=async_db_session,
        user_id=owner_id,
        dashboard_id=dashboard.id,
        permission=DashboardPermission.VIEW,
    )
    await async_db_session.commit()

    storage = StorageManager(db=async_db_session)
    await storage.save_aggregates(
        dashboard_id=dashboard.id,
        aggregates=[
            {
                "graph_id": graph.id,
                "dims": {"category": f"Filter-cat-{i}"},
                "metrics": {"revenue": 100 + i},
            }
            for i in range(rows)
        ],
        clear_old=True,
    )
    return str(dashboard.id), str(graph.id)


class TestFilterValueAdmissibilityBackstop:
    """The read backstop refuses an undevaluable value by its declared type."""

    async def test_read_backstop_refuses_a_range_declared_filter_by_name(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A stored ``range`` filter refuses a list value, naming the reason.

        The payload must be ``["0","100"]``: a numeric list is refused by the
        union before the service sees it, so only the string form reaches the
        backstop. Today this is a 422 with no ``details``; after the widening
        alone it would be a silent 200 with zero rows.
        """
        dashboard_id, graph_id = await _dashboard_declaring_filters(
            async_db_session,
            test_user["id"],
            filters=[{"field": "price", "type": "range"}],
        )

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id, graph_id, json.dumps({"price": ["0", "100"]})
            ),
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        body = response.json()
        assert body["code"] == "VALIDATION_ERROR"
        assert body["details"]["filter"] == "price"
        assert body["details"]["declared_type"] == "range"

    async def test_read_backstop_permits_a_list_on_a_declared_multiselect(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """A list on a declared ``multiselect`` is permitted and evaluated."""
        dashboard_id, graph_id = await _dashboard_declaring_filters(
            async_db_session,
            test_user["id"],
            filters=[{"field": "category", "type": "multiselect"}],
        )

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id,
                graph_id,
                json.dumps({"category": ["Filter-cat-0", "Filter-cat-1"]}),
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["graphs"][0]["returned_rows"] == 2

    async def test_read_backstop_permits_an_undeclared_filter_key(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """An undeclared key stays permitted, so existing fixtures keep working.

        Anti-over-refusal: this fails if the backstop ever demands that every
        submitted key be declared.
        """
        dashboard_id, graph_id = await _dashboard_with_rows(
            async_db_session, test_user["id"], rows=5
        )

        response = await authenticated_client.get(
            _url(dashboard_id, graph_id),
            params=_params(
                dashboard_id,
                graph_id,
                json.dumps({"category": ["Filter-cat-0", "Filter-cat-1"]}),
            ),
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["graphs"][0]["returned_rows"] == 2

