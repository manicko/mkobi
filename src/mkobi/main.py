"""Main FastAPI application file.

Creates and configures the FastAPI application using factory pattern.
"""

from mkobi.startup import (
    APP_REQUIRED_MODULES,
    WORKER_REQUIRED_MODULES,
    check_dependencies,
)

check_dependencies(APP_REQUIRED_MODULES)

from mkobi.app import create_app  # noqa: E402

# Create application instance via factory
app = create_app()

__all__ = [
    "APP_REQUIRED_MODULES",
    "WORKER_REQUIRED_MODULES",
    "app",
    "check_dependencies",
]
