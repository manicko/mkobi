"""Router declaration hygiene: redundant slash flags and duplicate tags.

Two declarations in the router tree stated nothing:

* Twelve routers passed ``redirect_slashes=False`` to their own ``APIRouter``
  constructor while ``create_app`` already set the flag on the application
  router. ``APIRouter.include_router`` has no ``redirect_slashes`` parameter,
  so nothing propagates; ``starlette.routing.Router.app`` reads the dispatching
  router's attribute at request time and the routes carry none. The
  application-level flag therefore governs every route, and the twelve
  declarations were inert. Deleting them is a no-op.
* ``dashboards.py`` declared ``tags=["dashboards"]`` on the parent router while
  its five children declared the same tag. ``include_router`` concatenates the
  parent's tags with the child's and ``add_api_route`` re-applies the parent's
  own tags, so an operation under the dashboards subtree carried the tag twice.
  Removing the parent's tag (one edit) yields the same document as removing it
  from all five children.

These tests observe the generated document and the served behaviour rather than
the source text. ``tests/test_openapi.py`` asserted nothing about tags, so the
duplication was invisible before this module.
"""

from typing import Any

from fastapi import FastAPI, status
from httpx import AsyncClient, ASGITransport

# The mounted prefix every API router shares.
API_PREFIX = "/api/v1"

# One served slash path under the dashboards subtree and one outside it. Both
# are declared with the trailing slash, so the no-slash variant exercises the
# slash handling that runs ahead of route resolution.
DASHBOARDS_SLASH_PATH = f"{API_PREFIX}/dashboards/"
NON_DASHBOARDS_SLASH_PATH = f"{API_PREFIX}/graphs/"


def _app() -> FastAPI:
    """Return the application object under test."""
    from mkobi.main import app

    return app


def _operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Yield ``(path, method, operation)`` for every operation in the document."""
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                operations.append((path, method, operation))
    return operations


class TestDashboardsTagIsDeclaredOncePerOperation:
    """Every dashboards-subtree operation carries the tag exactly once."""

    def test_dashboards_subtree_operations_are_tagged_exactly_once(self) -> None:
        schema = _app().openapi()

        subtree = [
            (path, method, operation)
            for path, method, operation in _operations(schema)
            if path.startswith(f"{API_PREFIX}/dashboards")
        ]
        assert subtree, "expected at least one operation under the dashboards subtree"

        for path, method, operation in subtree:
            tags = operation.get("tags", [])
            count = tags.count("dashboards")
            assert count == 1, (
                f"{method.upper()} {path} carries 'dashboards' {count} times "
                f"in tags: {tags!r}"
            )


class TestDashboardsTagTestCanFail:
    """Negative control: the exactly-once assertion is not vacuously true."""

    def test_some_operation_outside_the_subtree_lacks_the_tag(self) -> None:
        schema = _app().openapi()

        outside = [
            (path, method, operation)
            for path, method, operation in _operations(schema)
            if not path.startswith(f"{API_PREFIX}/dashboards")
        ]
        assert outside, "expected at least one operation outside the dashboards subtree"

        untagged = [
            (path, method, operation)
            for path, method, operation in outside
            if "dashboards" not in operation.get("tags", [])
        ]
        assert untagged, (
            "every operation outside the dashboards subtree carries the tag; "
            "the exactly-once assertion cannot distinguish a real pass"
        )


class TestApplicationLevelSlashHandlingGovernsEveryRoute:
    """The application flag governs; a router flag cannot suppress it."""

    async def test_application_level_slash_handling_governs_every_route(self) -> None:
        import os

        os.environ.setdefault("ENV", "test")
        os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")

        from mkobi.config import clear_config_cache

        clear_config_cache()
        app = _app()
        assert app.router.redirect_slashes is False

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            for path in (DASHBOARDS_SLASH_PATH, NON_DASHBOARDS_SLASH_PATH):
                no_slash = path.rstrip("/")
                response = await client.get(no_slash, follow_redirects=False)
                assert response.status_code == status.HTTP_404_NOT_FOUND, (
                    f"{no_slash} returned {response.status_code}, expected 404"
                )
                assert "location" not in response.headers, (
                    f"{no_slash} returned a Location header: "
                    f"{response.headers.get('location')!r}"
                )
