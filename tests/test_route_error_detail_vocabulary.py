"""SECB-7: route error details are a closed vocabulary.

Twenty-four ``detail=str(...)`` sites across eleven route modules used to
interpolate an internal value into a caller-visible detail. Each site now emits
a fixed message naming the failure class; the interpolated value goes to the
operator log. These tests pin both halves: the meta-test stops the pattern from
returning, and the injection tests prove a fixed detail is served even when the
underlying exception carries internal state.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from mkobi.api.routes import __file__ as routes_init

_ROUTES_DIR = Path(routes_init).resolve().parent

# The pattern the meta-test forbids in any route module.
_FORBIDDEN = "detail=str("

# Route modules that may legitimately interpolate a value into a caller-visible
# detail. Empty: every route site now uses a fixed message. Add an entry only
# with a written justification for why the value is safe to disclose.
_EXEMPTIONS: dict[str, str] = {}


def _route_modules() -> list[Path]:
    """Return every route module under ``src/mkobi/api/routes``."""
    return sorted(p for p in _ROUTES_DIR.glob("*.py") if p.name != "__init__.py")


class TestNoRouteInterpolatesIntoDetail:
    """The tripwire: no route module contains ``detail=str(``."""

    def test_no_route_module_interpolates_into_detail(self) -> None:
        """Fail loudly if any route site reintroduces ``detail=str(...)``."""
        offenders: list[str] = []
        for path in _route_modules():
            if path.name in _EXEMPTIONS:
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if _FORBIDDEN in line:
                    offenders.append(f"{path.name}:{lineno}")

        assert offenders == [], (
            "Route modules must not interpolate a value into a caller-visible "
            f"detail; log it instead. Offenders: {offenders}"
        )

    def test_the_census_covers_every_route_module(self) -> None:
        """Guard against the meta-test silently scanning nothing."""
        modules = _route_modules()
        assert len(modules) >= 11
        assert any(p.name == "upload.py" for p in modules)


class TestFixedDetailAtTheBoundary:
    """A failing service's internal value never reaches the response detail."""

    async def test_admin_update_role_serves_fixed_detail(
        self, authenticated_client: AsyncClient
    ) -> None:
        """A ValueError carrying a marker yields the fixed detail, not the marker."""
        from uuid import uuid4

        from mkobi.api.deps import get_user_service
        from mkobi.main import app

        marker = "INTERNAL_MARKER_admin_role"

        class _FailingService:
            async def update_user_role(self, **_: object) -> None:
                raise ValueError(marker)

        app.dependency_overrides[get_user_service] = lambda: _FailingService()
        try:
            response = await authenticated_client.patch(
                f"/admin/users/{uuid4()}/role",
                json={"role": "editor"},
            )
        finally:
            app.dependency_overrides.pop(get_user_service, None)

        body = response.json()
        assert response.status_code == 422
        assert body["detail"] == "Invalid user role update"
        assert marker not in body["detail"]

    async def test_users_create_serves_fixed_detail(
        self, authenticated_client: AsyncClient
    ) -> None:
        """A ValueError on user creation yields the fixed detail, not the marker."""
        from mkobi.api.deps import get_user_service
        from mkobi.main import app

        marker = "INTERNAL_MARKER_user_create"

        class _FailingService:
            async def create_user(self, **_: object) -> None:
                raise ValueError(marker)

        app.dependency_overrides[get_user_service] = lambda: _FailingService()
        try:
            response = await authenticated_client.post(
                "/users/",
                json={
                    "email": "fixed-detail@example.com",
                    "password": "StrongPass123!",
                    "role": "viewer",
                },
            )
        finally:
            app.dependency_overrides.pop(get_user_service, None)

        body = response.json()
        assert response.status_code == 422
        assert body["detail"] == "Invalid user data"
        assert marker not in body["detail"]

    async def test_admin_delete_user_serves_fixed_detail(
        self, authenticated_client: AsyncClient
    ) -> None:
        """A ValueError on admin delete yields the fixed detail, not the marker.

        ``DELETE /admin/users/{user_id}`` raises ``ACCESS_DENIED`` on a
        ``ValueError``; the caller sees the fixed sentence, never the value.
        """
        from uuid import uuid4

        from mkobi.api.deps import get_user_service
        from mkobi.main import app

        marker = "INTERNAL_MARKER_admin_delete"

        class _FailingService:
            async def delete_user(self, **_: object) -> None:
                raise ValueError(marker)

        app.dependency_overrides[get_user_service] = lambda: _FailingService()
        try:
            response = await authenticated_client.delete(f"/admin/users/{uuid4()}")
        finally:
            app.dependency_overrides.pop(get_user_service, None)

        body = response.json()
        assert response.status_code == 403
        assert body["detail"] == "User cannot be deleted"
        assert marker not in body["detail"]


@pytest.mark.parametrize(
    "module_name",
    [
        "admin.py",
        "auth.py",
        "dashboards_crud.py",
        "dashboards_graphs.py",
        "data.py",
        "graphs.py",
        "layouts.py",
        "processing_configs.py",
        "upload.py",
        "users.py",
    ],
)
def test_module_is_clean_of_the_forbidden_pattern(module_name: str) -> None:
    """Each route module that had a site is individually clean."""
    path = _ROUTES_DIR / module_name
    text = path.read_text(encoding="utf-8")
    assert _FORBIDDEN not in text, f"{module_name} still interpolates into detail"
