"""Slash-redirect behaviour on the four collection paths (EB-4 / EXT-006).

Starlette's slash handling runs ahead of route resolution and therefore ahead of
every ``Depends``. With the default redirect behaviour, a declared path ending
in ``/`` requested without its slash answers an anonymous ``307`` before any
credential is examined. That is an existence oracle over the four collection
paths: a ``307`` discloses existence to an unauthenticated caller, while an
undeclared path answers ``404``.

The remedy is the application-level ``redirect_slashes=False`` on the ``FastAPI``
constructor, set in ``create_app``. It must be there and not on the routers: the
redirect is decided by the top-level router on the full path, so per-router
``redirect_slashes`` declarations cannot suppress it. Phase 08's ``D-08-7``
removed the twelve redundant per-router declarations, so the routers now carry
the constructor default and the application decision is the only one left.
These tests assert the outcome against the application object the tests ship
with, and pin it so the ``307`` cannot silently return.
"""

from fastapi import FastAPI, status
from httpx import AsyncClient

# The four collection paths whose declared shape is the trailing-slash form.
COLLECTION_PATHS = [
    "/users",
    "/dashboards",
    "/graphs",
    "/admin/logs",
]


def _app() -> FastAPI:
    """Return the application object under test."""
    from mkobi.main import app

    return app


class TestNoSlashIsNotAnAnonymousRedirect:
    """A no-slash request is not a ``307`` — the existence oracle is gone.

    The concrete outcome the shipped application produces is ``404`` (the
    application-level redirect is disabled), which is indistinguishable from a
    genuinely undeclared path. Each case asserts that exact outcome rather than
    only the negative, so a regression to ``307`` fails loudly.
    """

    async def test_users_collection_no_slash_is_not_a_307(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/users", follow_redirects=False)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.status_code != status.HTTP_307_TEMPORARY_REDIRECT

    async def test_dashboards_collection_no_slash_is_not_a_307(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/dashboards", follow_redirects=False)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.status_code != status.HTTP_307_TEMPORARY_REDIRECT

    async def test_graphs_collection_no_slash_is_not_a_307(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/graphs", follow_redirects=False)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.status_code != status.HTTP_307_TEMPORARY_REDIRECT

    async def test_admin_logs_collection_no_slash_is_not_a_307(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get("/admin/logs", follow_redirects=False)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.status_code != status.HTTP_307_TEMPORARY_REDIRECT


class TestUndeclaredAndNoSlashAreIndistinguishable:
    """A no-slash collection request matches a genuinely undeclared path.

    This is the disclosure property the finding is about: if the two answers
    differ, an unauthenticated caller can enumerate the declared collection
    paths. Both must be ``404``.
    """

    async def test_no_slash_and_undeclared_share_the_outcome(
        self, async_client: AsyncClient
    ) -> None:
        undeclared = await async_client.get("/nonexistent", follow_redirects=False)
        assert undeclared.status_code == status.HTTP_404_NOT_FOUND

        for path in COLLECTION_PATHS:
            response = await async_client.get(path, follow_redirects=False)
            assert response.status_code == undeclared.status_code, (
                f"{path} discloses existence: got {response.status_code}, "
                f"undeclared path got {undeclared.status_code}"
            )


class TestSlashFormIsServed:
    """The slash form is the shape being kept and stays served.

    The four live test classes request this shape unmodified. It must be the
    declared path in the published document and it must reach the credential
    check (``401`` without a token), not a redirect.
    """

    async def test_slash_form_is_not_redirected(
        self, async_client: AsyncClient
    ) -> None:
        for path in COLLECTION_PATHS:
            response = await async_client.get(f"{path}/", follow_redirects=False)
            assert response.status_code != status.HTTP_307_TEMPORARY_REDIRECT
            assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestServedAndDeclaredPathsAgree:
    """The served slash shape and the published ``paths`` shape agree.

    Asserted against the generated document for the four paths and no others:
    the four collection paths are declared with the trailing slash, and their
    no-slash variants are not declared.
    """

    def test_four_collection_paths_are_declared_with_the_slash(self) -> None:
        schema = _app().openapi()
        declared = set(schema["paths"])

        expected = {
            "/api/v1/users/",
            "/api/v1/dashboards/",
            "/api/v1/graphs/",
            "/api/v1/admin/logs/",
        }
        assert expected <= declared, f"missing declared slash paths: {expected - declared}"

        # The no-slash variants of exactly these four paths are not declared.
        for path in COLLECTION_PATHS:
            assert f"/api/v1{path}" not in declared, (
                f"the no-slash variant /api/v1{path} is declared, which would "
                "make the served shape the undeclared one"
            )

    def test_collection_paths_are_the_only_trailing_slash_paths(self) -> None:
        """Exactly these four paths end in a slash in the published document."""
        schema = _app().openapi()
        trailing = {p for p in schema["paths"] if p.endswith("/")}
        expected = {
            "/api/v1/users/",
            "/api/v1/dashboards/",
            "/api/v1/graphs/",
            "/api/v1/admin/logs/",
        }
        assert trailing == expected


class TestApplicationLevelRedirectGoverns:
    """The application-level default governs; the per-router flags are gone.

    This is the regression guard for the mechanism. The twelve per-router
    ``redirect_slashes=False`` declarations were inert for this direction: the
    redirect is decided by the top-level router on the full path, so a
    per-router flag cannot reintroduce the ``307``. Phase 08's ``D-08-7``
    removed those declarations, so the routers now carry the constructor
    default and the application must carry the disabled behaviour itself.
    """

    def test_application_router_has_redirects_disabled(self) -> None:
        app = _app()
        assert app.router.redirect_slashes is False

    def test_route_modules_no_longer_declare_redirect_slashes(self) -> None:
        """No route module carries a per-router ``redirect_slashes`` flag.

        The twelve declarations phase 08's ``D-08-7`` removed are absent from
        the live routers: each reflects the ``APIRouter`` constructor default.
        Asserted on the imported router objects, not on source text, so a
        reintroduced declaration fails here even if it is written indirectly.
        """
        from mkobi.api.routes import (
            admin,
            auth,
            client_errors,
            dashboards,
            dashboards_access,
            dashboards_crud,
            dashboards_filters,
            dashboards_graphs,
            data,
            filter_values,
            graphs,
            layouts,
            processing_configs,
            processing_logs,
            upload,
            users,
        )

        modules = (
            admin,
            auth,
            client_errors,
            dashboards,
            dashboards_access,
            dashboards_crud,
            dashboards_filters,
            dashboards_graphs,
            data,
            filter_values,
            graphs,
            layouts,
            processing_configs,
            processing_logs,
            upload,
            users,
        )

        for module in modules:
            router = module.router
            assert router.redirect_slashes is True, (
                f"{module.__name__} still declares redirect_slashes="
                f"{router.redirect_slashes!r}; the constructor default is True"
            )

    def test_no_route_module_passes_redirect_slashes_to_apirouter(self) -> None:
        """Structural backstop: the argument is absent from every route module.

        The live-router assertion above is the primary check; this confirms the
        deletion reached the source uniformly, so a module that set the flag on
        a child router rather than the exported one is still caught.
        """
        import ast
        from pathlib import Path

        routes_dir = Path(__file__).resolve().parent.parent / "src" / "mkobi" / "api" / "routes"
        offenders: list[str] = []
        for path in sorted(routes_dir.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Name) and func.id == "APIRouter"):
                    continue
                if any(kw.arg == "redirect_slashes" for kw in node.keywords):
                    offenders.append(f"{path.name}:{node.lineno}")
        assert offenders == [], (
            f"route modules still pass redirect_slashes to APIRouter: {offenders}"
        )

    async def test_application_flag_gives_404_without_location_on_both_paths(
        self, async_client: AsyncClient
    ) -> None:
        """The application flag governs a dashboards and a non-dashboards path.

        A no-slash variant of a path declared with the trailing slash must
        answer ``404`` with no ``Location`` header. This is the behaviour the
        twelve deletions were proven not to change: the application router, not
        the per-router flags, decides the redirect.
        """
        for path in ("/dashboards", "/graphs"):
            response = await async_client.get(path, follow_redirects=False)
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "location" not in response.headers, (
                f"{path} returned a Location header: "
                f"{response.headers.get('location')!r}"
            )
