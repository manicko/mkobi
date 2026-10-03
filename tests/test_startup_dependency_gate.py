"""Tests pinning the startup dependency gate's ruled shape.

``EXT-009`` found that the gate certified libraries the application never
imported. ``DP-8`` option (a) split the single list into an app-required set and
a worker-required set so each entrypoint gates on the libraries it actually
reaches. These tests pin that decision by assertion rather than prose so a later
edit that re-adds a certified absence, or moves ``rq`` into the app set, fails
loudly.

The five dispositions pinned here (see the ``EB-6`` commit body for evidence):

- ``rq`` stays, but in the **worker** set: it is a real worker contract, imported
  by ``rq_worker_wrapper`` and reached through ``task_queue``.
- ``httpx`` is a **tier mismatch** — a test-tier contract — and is gated at
  neither entrypoint.
- ``plotly`` and ``tenacity`` are certified absences and are gated nowhere.
- ``magic`` stays in the **app** set: it is a documented hard startup dependency.
"""

import mkobi.main
import mkobi.startup
from mkobi.startup import APP_REQUIRED_MODULES, WORKER_REQUIRED_MODULES


class TestGateShape:
    """The two sets match the ruled shape of ``DP-8`` option (a)."""

    def test_rq_is_only_in_the_worker_set(self) -> None:
        assert "rq" in WORKER_REQUIRED_MODULES
        assert "rq" not in APP_REQUIRED_MODULES

    def test_magic_is_in_the_app_set(self) -> None:
        assert "magic" in APP_REQUIRED_MODULES
        assert "magic" not in WORKER_REQUIRED_MODULES

    def test_httpx_is_gated_at_neither_entrypoint(self) -> None:
        assert "httpx" not in APP_REQUIRED_MODULES
        assert "httpx" not in WORKER_REQUIRED_MODULES

    def test_plotly_is_gated_at_neither_entrypoint(self) -> None:
        assert "plotly" not in APP_REQUIRED_MODULES
        assert "plotly" not in WORKER_REQUIRED_MODULES

    def test_tenacity_is_gated_at_neither_entrypoint(self) -> None:
        assert "tenacity" not in APP_REQUIRED_MODULES
        assert "tenacity" not in WORKER_REQUIRED_MODULES

    def test_sets_are_disjoint(self) -> None:
        assert set(APP_REQUIRED_MODULES).isdisjoint(WORKER_REQUIRED_MODULES)

    def test_main_reexports_the_gate(self) -> None:
        assert mkobi.main.APP_REQUIRED_MODULES is APP_REQUIRED_MODULES
        assert mkobi.main.WORKER_REQUIRED_MODULES is WORKER_REQUIRED_MODULES


class TestWorkerGateDoesNotBuildTheApp:
    """The worker entrypoint gates on the worker set without importing the app."""

    def test_startup_module_has_no_application_side_effect(self) -> None:
        # ``startup`` must be importable without constructing the FastAPI app,
        # so the worker process gates dependencies without booting the API.
        assert not hasattr(mkobi.startup, "app")

    def test_worker_wrapper_imports_the_gate_from_startup(self) -> None:
        import pathlib

        wrapper = pathlib.Path(mkobi.__path__[0]) / "rq_worker_wrapper.py"
        source = wrapper.read_text(encoding="utf-8")
        assert "from mkobi.startup import" in source
        assert "from mkobi.main import" not in source


class TestEntrypointGateRuns:
    """The app entrypoint still gates and still passes with the ruled list."""

    def test_import_mkobi_main_succeeds(self) -> None:
        # Importing the module runs the module-scope gate; a missing app-level
        # dependency would raise SystemExit here.
        import importlib

        importlib.reload(mkobi.main)

    def test_app_gate_passes_for_the_app_set(self) -> None:
        mkobi.startup.check_dependencies(APP_REQUIRED_MODULES)

    def test_worker_gate_passes_for_the_worker_set(self) -> None:
        mkobi.startup.check_dependencies(WORKER_REQUIRED_MODULES)
