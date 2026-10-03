"""Startup dependency gate shared by both process entrypoints.

The gate certifies that the third-party distributions a given entrypoint imports
are importable, exiting the process when one is missing so a broken installation
fails at boot rather than at first use.

The sets are split per entrypoint (``DP-8`` option (a)): the API app gates on the
libraries it reaches through ``mkobi.app``; the RQ worker gates on ``rq``, which
the API app never imports. The module holds no FastAPI application and no other
import-time side effect, so importing it from the worker entrypoint does not
construct the web application.
"""

import logging
from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Third-party distributions the API entrypoint imports. Each name is the
# distribution's import name, certified because ``mkobi.app`` (and everything it
# reaches) imports it at boot.
APP_REQUIRED_MODULES = [
    "aiofiles",
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "polars",
    "redis",
    "bcrypt",
    "jose",
    "alembic",
    "asyncpg",
    "magic",
]

# Third-party distributions the RQ worker entrypoint imports. Kept separate from
# the app set because ``rq`` is a worker contract the API app never imports.
WORKER_REQUIRED_MODULES = [
    "rq",
]

# The two sets are deliberately plain ``list[str]`` rather than StrEnum members.
# They are a build-time import gate, not a domain constant: the values are
# distribution import names consumed by ``__import__`` and are never serialized,
# compared or persisted. ``models/enums.py`` owns enumerated domain values
# (project rule §10); a list of packages to import is neither a domain value nor
# a set of states, so expressing them as StrEnum would put package metadata in
# the domain-model layer — the opposite of the rule's intent.


def check_dependencies(modules: Sequence[str]) -> None:
    """Verify that the given dependencies are importable.

    Exits the process with an error if any module is missing, preventing startup
    with an incomplete or broken installation.

    Args:
        modules: Import names to certify. The caller passes the set that governs
            its entrypoint (``APP_REQUIRED_MODULES`` or
            ``WORKER_REQUIRED_MODULES``).
    """
    missing: list[str] = []
    for module_name in modules:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)

    if missing:
        logger.error(
            "Missing required dependencies: %s. "
            "Please install them before running the application.",
            ", ".join(missing),
        )
        raise SystemExit(1)
