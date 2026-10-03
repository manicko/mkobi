"""Contract tests for the served frontend bundle (ART-007, FAB-7).

The catch-all mount at ``/`` and the ``static_files`` component of
``/health/detailed`` must derive their verdict from one shared predicate:
the configured bundle directory exists *and* carries an ``index.html``. Before
this fix the mount required that pair while health checked the directory alone,
so a ``dist`` without ``index.html`` produced a route table identical to an
absent bundle while health reported ``available``.

Every test that manipulates the bundle points ``FRONTEND__DIST_DIR`` at a tmp
directory, so no test creates a real ``frontend/dist`` in the ambient working
directory and changes another test's verdict.
"""

import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.routing import Mount

import mkobi.app as app_module
from mkobi.app import create_app, resolve_frontend_bundle

from mkobi.config import clear_config_cache

# The pre-FAB-7 health predicate checked the CWD-relative literal string
# ``frontend/dist``. Pinning the configured directory here (and asserting below
# that it genuinely exists) means the literal cannot coincide with it, so a
# "present but wrong" bundle cannot pass for the wrong reason.
_CWD_RELATIVE_BUNDLE_LITERAL = Path("frontend/dist")


def _set_test_credentials() -> None:
    """Populate the environment so create_app() has a usable configuration."""
    os.environ.setdefault("ENV", "test")
    os.environ.setdefault("JWT__SECRET_KEY", "test_secret_key_change_in_production")
    os.environ.setdefault("DATABASE__HOST", "localhost")
    os.environ.setdefault("DATABASE__PORT", "5434")
    os.environ.setdefault("DATABASE__DBNAME", "bidb_test")
    os.environ.setdefault("DATABASE__USER", "mkobi_app")
    os.environ.setdefault("DATABASE__PASSWORD", "StrongDbP@ss123!")
    os.environ.setdefault("DATABASE__ADMIN_USER", "postgres")
    os.environ.setdefault("DATABASE__ADMIN_PASSWORD", "StrongT3stP@ss!")


def _static_mount(application) -> Mount | None:
    """Return the catch-all static mount, or None when it was not registered."""
    return next(
        (
            route
            for route in application.routes
            if isinstance(route, Mount) and route.name == "static"
        ),
        None,
    )


@pytest.fixture
def bundle_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the configured bundle directory at an isolated tmp directory.

    Yields a callable that materialises one of the three presence states and
    returns the configured path. The configuration cache is cleared so
    create_app() and resolve_frontend_bundle() observe the override.
    """
    _set_test_credentials()
    configured = tmp_path / "bundle"

    def _place(state: str) -> Path:
        monkeypatch.setenv("FRONTEND__DIST_DIR", str(configured))
        clear_config_cache()
        if state == "correct":
            configured.mkdir(parents=True, exist_ok=True)
            (configured / "index.html").write_text(
                "<!doctype html><title>mkobi</title>", encoding="utf-8"
            )
        elif state == "present_but_wrong":
            configured.mkdir(parents=True, exist_ok=True)
            (configured / "main.js").write_text("// no index", encoding="utf-8")
        elif state == "absent":
            # Nothing on disk: the configured directory does not exist.
            pass
        else:
            raise ValueError(f"unknown bundle state: {state}")
        return configured

    yield _place
    clear_config_cache()


@pytest.fixture
async def client_for_state(bundle_root):
    """Yield a factory that drives create_app() for a given presence state."""
    clients: list[AsyncClient] = []

    async def _make(state: str):
        bundle_root(state)
        app = create_app()
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://testserver")
        clients.append(client)
        return app, client

    yield _make

    for client in clients:
        await client.aclose()


class TestPresenceStatesRouteTable:
    """The route table is identical for absent and present-but-wrong."""

    async def test_absent_bundle_registers_no_catch_all(self, client_for_state) -> None:
        """No bundle on disk: the catch-all mount is not registered."""
        application, _client = await client_for_state("absent")
        assert _static_mount(application) is None

    async def test_present_but_wrong_bundle_registers_no_catch_all(
        self, client_for_state
    ) -> None:
        """A dist without index.html must leave the route table as if absent."""
        application, _client = await client_for_state("present_but_wrong")
        assert _static_mount(application) is None

    async def test_correct_bundle_registers_the_catch_all(self, client_for_state) -> None:
        """A dist with index.html registers the catch-all mount at '/'."""
        application, _client = await client_for_state("correct")
        mount = _static_mount(application)
        assert mount is not None
        assert mount.path == ""

    async def test_absent_and_present_but_wrong_have_identical_mount_verdict(
        self, bundle_root
    ) -> None:
        """The two unhealthy states agree on the mount, which is the finding."""
        # Both states are driven in turn; create_app builds one route table each.
        states = ("absent", "present_but_wrong")
        mounts: list[Mount | None] = []
        for state in states:
            bundle_root(state)
            application = create_app()
            mounts.append(_static_mount(application))
        assert mounts[0] is None
        assert mounts[1] is None


class TestPresenceStatesServed:
    """The correct bundle serves '/' and deep links with the SPA shell."""

    async def test_root_returns_html(self, client_for_state) -> None:
        """GET / returns 200 text/html from the correct bundle."""
        _application, client = await client_for_state("correct")
        response = await client.get("/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    async def test_deep_link_returns_html(self, client_for_state) -> None:
        """A client-side route falls back to index.html with 200 text/html."""
        _application, client = await client_for_state("correct")
        response = await client.get("/dashboards/42")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")

    async def test_absent_bundle_root_is_not_served(self, client_for_state) -> None:
        """Without a bundle, '/' is not a served SPA route."""
        _application, client = await client_for_state("absent")
        response = await client.get("/")
        assert response.status_code == 404

    async def test_present_but_wrong_bundle_root_is_not_served(
        self, client_for_state
    ) -> None:
        """A dist without index.html serves no SPA route either."""
        _application, client = await client_for_state("present_but_wrong")
        response = await client.get("/")
        assert response.status_code == 404


class TestStaticFilesHealthComponent:
    """The health component reports the one predicate and the resolved path."""

    async def test_absent_reports_unavailable(
        self, client_for_state, bundle_root
    ) -> None:
        """No bundle: health reports unavailable from the shared predicate.

        The configured directory is pinned to a tmp path and is asserted absent,
        so the pre-fix CWD-relative literal cannot supply the verdict instead.
        """
        configured = bundle_root("absent")
        assert not configured.exists()
        assert not _CWD_RELATIVE_BUNDLE_LITERAL.exists()
        _app, client = await client_for_state("absent")
        data = (await client.get("/health/detailed")).json()
        assert data["components"]["static_files"]["status"] == "unavailable"
        assert data["components"]["static_files"]["path"] == str(configured.resolve())

    async def test_present_but_wrong_reports_unavailable(
        self, client_for_state, bundle_root
    ) -> None:
        """A dist without index.html reports unavailable, matching the mount.

        The configured directory is pinned to a tmp path and asserted to
        genuinely exist on disk **without** ``index.html``. The verdict is
        therefore unavailable because the predicate requires ``index.html``, not
        because nothing is there -- which is the ART-007 defect.
        """
        configured = bundle_root("present_but_wrong")
        assert configured.is_dir()
        assert not (configured / "index.html").exists()
        # The pre-fix CWD-relative literal must not coincide with the pinned
        # directory, or "present but wrong" could still pass for the wrong
        # reason (the old predicate would find this literal and say available).
        assert _CWD_RELATIVE_BUNDLE_LITERAL.resolve() != configured.resolve()
        _app, client = await client_for_state("present_but_wrong")
        data = (await client.get("/health/detailed")).json()
        assert data["components"]["static_files"]["status"] == "unavailable"
        assert data["components"]["static_files"]["path"] == str(configured.resolve())

    async def test_correct_reports_available(self, client_for_state) -> None:
        """A dist with index.html reports available."""
        _application, client = await client_for_state("correct")
        data = (await client.get("/health/detailed")).json()
        assert data["components"]["static_files"]["status"] == "available"

    async def test_path_reports_resolved_absolute_path(self, bundle_root) -> None:
        """The reported path is the resolved absolute directory, not a literal."""
        configured = bundle_root("present_but_wrong")
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            data = (await client.get("/health/detailed")).json()
        reported = data["components"]["static_files"]["path"]
        assert reported == str(configured.resolve())
        assert Path(reported).is_absolute()

    async def test_health_verdict_tracks_the_shared_helper(
        self, bundle_root, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The health verdict is the helper's answer, not a second derivation.

        The helper is patched to report the bundle unavailable while index.html
        exists on disk. An independent ``isdir`` check would still say
        available; a verdict that tracks the helper reports unavailable.
        """
        configured = bundle_root("correct")
        assert (configured / "index.html").is_file()

        monkeypatch.setattr(
            app_module, "resolve_frontend_bundle", lambda: (configured.resolve(), False)
        )
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            data = (await client.get("/health/detailed")).json()
        assert data["components"]["static_files"]["status"] == "unavailable"

    def test_mount_verdict_tracks_the_shared_helper(
        self, bundle_root, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The mount is registered from the helper's answer, not a second check.

        The helper is patched to report the bundle unservable while a correct
        bundle (directory plus index.html) exists on disk. An independent
        existence check would register the mount anyway; a mount that tracks the
        helper skips it.
        """
        configured = bundle_root("correct")
        assert (configured / "index.html").is_file()

        monkeypatch.setattr(
            app_module, "resolve_frontend_bundle", lambda: (configured.resolve(), False)
        )
        application = create_app()
        assert _static_mount(application) is None

    def test_helper_reports_resolved_absolute_path(self, bundle_root) -> None:
        """The helper itself returns an absolute, resolved directory."""
        configured = bundle_root("correct")
        resolved, available = resolve_frontend_bundle()
        assert available is True
        assert resolved == configured.resolve()
        assert resolved.is_absolute()
