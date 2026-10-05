"""SECB-7: route error details are a closed vocabulary.

Twenty-four ``detail=str(...)`` sites across eleven route modules used to
interpolate an internal value into a caller-visible detail. Each site now emits
a fixed message naming the failure class; the interpolated value goes to the
operator log. These tests pin both halves: the meta-test stops the pattern from
returning, and the injection tests prove a fixed detail is served even when the
underlying exception carries internal state.

Scope of the claim (option (b), narrowed honestly). The programme's rule is: a
route must not interpolate an *internal* value into a caller-visible detail. The
guard therefore forbids both interpolation forms — ``detail=str(...)`` and an
f-string ``detail=f"...{...}"`` — across every route module. Two upload sites are
the only surviving interpolation and are allow-listed by their exact source line,
not by exempting the whole module:

* ``upload.py`` (both sites) interpolates the *configured* ``max_file_size_mb``,
  a public setting the client already knows and which the request's own 413 body
  bounds. It is not internal state; the file name and byte size (the sensitive
  values) go to the operator log only. Disclosing the configured limit is
  intended.

One site is kept although it is written as ``detail=detail``: ``auth.py``'s rate
-limit helper passes a parameter whose every call site passes a fixed literal, so
no value is interpolated and the guard does not flag it. It is documented here so
a reader does not mistake its absence from the allow-list for an oversight.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from mkobi.api.routes import __file__ as routes_init

_ROUTES_DIR = Path(routes_init).resolve().parent

# The two interpolation forms the meta-test forbids in any route module.
_FORBIDDEN_PATTERNS = ("detail=str(", 'detail=f"')

# Accepted interpolations, pinned by the exact stripped source line so a *new*
# site cannot hide behind a module-level exemption. Each entry names the value
# and why disclosing it is intended; see the module docstring.
_ALLOWED_LINES: frozenset[str] = frozenset(
    {
        'detail=f"File size exceeds maximum limit of '
        '{config.upload.max_file_size_mb}MB",',
    }
)


def _route_modules() -> list[Path]:
    """Return every route module under ``src/mkobi/api/routes``."""
    return sorted(p for p in _ROUTES_DIR.glob("*.py") if p.name != "__init__.py")


class TestNoRouteInterpolatesIntoDetail:
    """The tripwire: no route module interpolates an internal value into detail."""

    def test_no_route_module_interpolates_into_detail(self) -> None:
        """Fail loudly if any route site reintroduces an interpolated detail."""
        offenders: list[str] = []
        for path in _route_modules():
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if line.strip() in _ALLOWED_LINES:
                    continue
                if any(pattern in line for pattern in _FORBIDDEN_PATTERNS):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")

        assert offenders == [], (
            "Route modules must not interpolate an internal value into a "
            f"caller-visible detail; log it instead. Offenders: {offenders}"
        )

    def test_the_census_covers_every_route_module(self) -> None:
        """Guard against the meta-test silently scanning nothing."""
        modules = _route_modules()
        assert len(modules) >= 11
        assert any(p.name == "upload.py" for p in modules)

    def test_the_allow_list_is_not_stale(self) -> None:
        """Every allow-listed line still exists verbatim in some route module.

        Without this, a closed site would leave a dead exemption that could later
        shelter a genuinely re-interpolated detail.
        """
        sources = [
            line.strip()
            for path in _route_modules()
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        for allowed in _ALLOWED_LINES:
            assert allowed in sources, (
                f"allow-listed detail line no longer exists: {allowed!r}"
            )


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
    """Each route module that had a site is individually clean.

    Allow-listed lines (the two configured-limit upload sites) are the only
    permitted exception; every other interpolation form is a failure.
    """
    path = _ROUTES_DIR / module_name
    offending = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() not in _ALLOWED_LINES
        and any(pattern in line for pattern in _FORBIDDEN_PATTERNS)
    ]
    assert offending == [], f"{module_name} still interpolates into detail: {offending}"
