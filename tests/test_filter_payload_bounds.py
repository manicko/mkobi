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
