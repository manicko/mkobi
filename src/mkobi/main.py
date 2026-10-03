"""Main FastAPI application file.

Creates and configures the FastAPI application using factory pattern.
"""

import logging

logger = logging.getLogger(__name__)

REQUIRED_MODULES = [
    "aiofiles",
    "fastapi",
    "sqlalchemy",
    "httpx",
    "pydantic",
    "polars",
    "plotly",
    "redis",
    "bcrypt",
    "jose",
    "alembic",
    "asyncpg",
    "rq",
    "tenacity",
    "magic",
]


def check_dependencies() -> None:
    """Verify that all required dependencies are importable.

    Exits the application with an error if any critical module is missing,
    preventing startup with an incomplete or broken installation.
    """
    missing: list[str] = []
    for module_name in REQUIRED_MODULES:
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


check_dependencies()

from mkobi.app import create_app  # noqa: E402

# Create application instance via factory
app = create_app()
