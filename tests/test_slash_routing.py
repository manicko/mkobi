"""Slash-redirect behaviour on the four collection paths (EB-4 / EXT-006).

Starlette's slash handling runs ahead of route resolution and therefore ahead of
every ``Depends``. With the default redirect behaviour, a declared path ending
in ``/`` requested without its slash answers an anonymous ``307`` before any
credential is examined. That is an existence oracle over the four collection
paths: a ``307`` discloses existence to an unauthenticated caller, while an
undeclared path answers ``404``.

The remedy is the application-level ``redirect_slashes=False`` on the ``FastAPI``
constructor, set in ``create_app``. It must be there and not on the routers: the
redirect is decided by the top-level router on the full path, so the twelve
per-router ``redirect_slashes`` declarations elsewhere cannot suppress it. These
tests assert the outcome against the application object the tests ship with, and
pin it so the ``307`` cannot silently return.
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
    """The application-level default governs; the per-router flags cannot.

    This is the regression guard for the mechanism. The twelve per-router
    ``redirect_slashes=False`` declarations are inert for this direction: the
    redirect is decided by the top-level router on the full path, so a
    per-router flag cannot reintroduce the ``307``. The application must carry
    the disabled behaviour itself, and the per-router flags must still be
    present unchanged (phase 08's D-08-7 owns their removal).
    """

    def test_application_router_has_redirects_disabled(self) -> None:
        app = _app()
        assert app.router.redirect_slashes is False

    def test_per_router_flags_are_inert(self) -> None:
        """The collection routers keep their per-router flag, unchanged."""
        from mkobi.api.routes.users import router as users_router
        from mkobi.api.routes.dashboards_crud import router as dashboards_crud_router
        from mkobi.api.routes.graphs import router as graphs_router
        from mkobi.api.routes.processing_logs import router as processing_logs_router

        for router in (
            users_router,
            dashboards_crud_router,
            graphs_router,
            processing_logs_router,
        ):
            assert router.redirect_slashes is False

    def test_router_flag_alone_does_not_disable_the_app_default(self) -> None:
        """A per-router ``redirect_slashes=False`` cannot set the app default.

        Constructing a fresh application with the default behaviour and
        including the collection routers proves the flag is inert at that level:
        the application router remains ``True``, which is precisely why the
        constructor argument is required.
        """
        from mkobi.api.routes.users import router as users_router

        default_app = FastAPI()
        default_app.include_router(users_router, prefix="/api/v1")

        # The per-router flag is False, yet the application router keeps the
        # default True — the flag does not propagate upward.
        assert users_router.redirect_slashes is False
        assert default_app.router.redirect_slashes is True
