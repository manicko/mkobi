"""Layering meta-test: route modules hold no raw SQL or business logic.

AGENTS.md section 4 states API -> Service -> Repository, with no business logic
in routes. Before this file the only backend layering meta-test was
``test_task_queue.py::TestServicesDoNotImportRq`` ("services never import rq
directly"); the rule that matters most had no enforcement at all and relied on
being respected by hand.

This test pins the route-side half of the rule:

* a route module must not build or run raw SQL — no ``select``, ``text`` or
  ``insert`` constructors and no ``.execute(...)``;
* it must not import those constructors from SQLAlchemy.

The one transaction pattern that is allowed and expected is the documented
request-boundary ``await db.commit()`` (SPEC3.17). It is not business logic: the
route opens the boundary, delegates the work to a service, and commits what the
service produced. ``test_commit_boundary_pattern_is_present`` asserts the pattern
is actually in the tree, so the allowance cannot silently become a dead branch
that shields a future raw-SQL import.
"""

from __future__ import annotations

import ast
from pathlib import Path

from mkobi.api.routes import __file__ as routes_init

_ROUTES_DIR = Path(routes_init).resolve().parent

# Raw-SQL call names a route must never invoke directly. Attribute calls such as
# ``graph_repo.update(...)`` / ``graph_repo.delete(...)`` are repository calls,
# not SQL constructors, and are not in this set.
_FORBIDDEN_CALLS = frozenset({"select", "text", "insert", "execute"})

# Raw-SQL names a route must never import from SQLAlchemy.
_FORBIDDEN_SQL_IMPORTS = frozenset({"select", "text", "insert"})


def _route_modules() -> list[Path]:
    """Return every route module under ``src/mkobi/api/routes``."""
    return sorted(p for p in _ROUTES_DIR.glob("*.py") if p.name != "__init__.py")


class TestRoutesHoldNoRawSql:
    """No route module builds or runs raw SQL."""

    def test_no_route_module_calls_raw_sql(self) -> None:
        """Assert the layering rule: routes never build or execute raw SQL."""
        offenders: list[str] = []
        for path in _route_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = _call_name(node.func)
                    if name in _FORBIDDEN_CALLS:
                        offenders.append(f"{path.name}:{node.lineno}: {name}(...)")

        assert offenders == [], (
            "Route modules must not build or execute raw SQL; that belongs in "
            f"the repository layer. Offenders: {offenders}"
        )

    def test_no_route_module_imports_raw_sql_constructors(self) -> None:
        """A route must not import ``select``/``text``/``insert`` from SQLAlchemy."""
        offenders: list[str] = []
        for path in _route_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if not module.startswith("sqlalchemy"):
                        continue
                    for alias in node.names:
                        if alias.name in _FORBIDDEN_SQL_IMPORTS:
                            offenders.append(
                                f"{path.name}: from {module} import {alias.name}"
                            )

        assert offenders == [], (
            "Route modules must not import SQL constructors; use a repository. "
            f"Offenders: {offenders}"
        )

    def test_the_census_covers_every_route_module(self) -> None:
        """Anti-vacuity: fail if the route set ever comes back empty."""
        modules = _route_modules()
        assert len(modules) >= 11, f"route census went empty: {modules}"
        assert any(p.name == "data.py" for p in modules)
        assert any(p.name == "upload.py" for p in modules)


class TestRequestBoundaryCommitIsAllowed:
    """``await db.commit()`` is the documented request-boundary pattern."""

    def test_commit_boundary_pattern_is_present(self) -> None:
        """The allowed pattern exists, so the allowance is not a dead branch.

        If routes stopped committing, the exemption above would protect nothing
        and a later raw-SQL import could hide behind it. Asserting at least one
        route still commits keeps the allowance load-bearing.
        """
        committing = [
            path.name
            for path in _route_modules()
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "commit"
                for node in ast.walk(
                    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                )
            )
        ]
        assert committing, "no route commits at the request boundary (SPEC3.17)"


def _call_name(func: ast.expr) -> str | None:
    """Return the terminal name of a call target, or None for complex targets.

    ``select(...)`` yields ``select``; ``db.execute(...)`` yields ``execute``;
    ``graph_repo.update(...)`` yields ``update`` (a repository call, not SQL).
    """
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
