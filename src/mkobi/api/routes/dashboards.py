"""Dashboard management routes.

This module provides endpoints for CRUD operations with dashboards.

Access to most operations is restricted and requires authentication.
Create, update and delete operations are available only to owners.

For backward compatibility, this module combines all dashboards sub-routers.
"""

from fastapi import APIRouter

from mkobi.api.routes.dashboards_crud import router as crud_router
from mkobi.api.routes.dashboards_access import router as access_router
from mkobi.api.routes.dashboards_filters import router as filters_router
from mkobi.api.routes.dashboards_graphs import router as graphs_router
from mkobi.api.routes.filter_values import router as filter_values_router

# Create combined router that includes all sub-routers
router = APIRouter(prefix="/dashboards")
router.include_router(crud_router)
router.include_router(access_router)
router.include_router(filters_router)
router.include_router(graphs_router)
router.include_router(filter_values_router)