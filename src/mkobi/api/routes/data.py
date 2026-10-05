"""Routes for getting dashboard aggregated data.

This module provides endpoints for:
- Getting aggregated data for dashboards
- Getting data for specific charts
- Applying filters to data

All operations require authentication and appropriate permissions.
"""

import json
import logging
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    CurrentUser,
    get_data_service,
    get_db_dependency,
    get_graph_repository,
)
from mkobi.api.schemas.responses import (
    auth_protected_responses,
)
from mkobi.config import get_config
from mkobi.core.permissions import check_dashboard_access, DashboardPermissionError
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.models.data import (
    AggregatedDataResponse,
    AggregatedFiltersRequest,
    GraphDataResponse,
)
from mkobi.models.enums import DashboardPermission, ErrorCode
from mkobi.services.data_service import DataService
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])


def _flatten_points(
    records: list[Any],
) -> list[dict[str, int | float | str]]:
    """Flatten service records' ``preview`` payloads into data points."""
    data_points: list[dict[str, int | float | str]] = []
    for item in records:
        preview = item.get("preview")
        if preview:
            data_points.extend(cast(list[dict[str, int | float | str]], preview))
    return data_points


@router.get(
    "/aggregated",
    response_model=AggregatedDataResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard aggregated data",
    description="Returns data for all dashboard charts with applied filters.",
    responses=auth_protected_responses,
)
async def get_aggregated_data_endpoint(
    current_user: CurrentUser,
    data_service: DataService = Depends(get_data_service),
    db: AsyncSession = Depends(get_db_dependency),
    graph_repo: GraphRepository = Depends(get_graph_repository),
    dashboard_id: UUID = Query(..., description="Dashboard ID"),
    graph_id: UUID | None = Query(default=None, description="Graph ID (optional, returns all dashboard graphs if absent)"),
    filters: str | None = Query(default=None, description="JSON string with filters"),
) -> AggregatedDataResponse:
    """Get aggregated data for dashboard.

    Applies filters to JSONB field dims and groups data by graph_id.
    Response format: {"graphs": [{"graph_id": "...", "type": "...", "name": "...", "data": [...]}]}

    When graph_id is provided, returns data for a single graph.
    When graph_id is absent, returns data for all graphs in the dashboard.

    Args:
        dashboard_id: Dashboard ID.
        graph_id: Graph ID (optional). If absent, returns all dashboard graphs.
        filters: JSON string with filters (optional).
        current_user: Current authenticated user.
        data_service: Data service (dependency injection).
        graph_repo: Graph repository for fetching graphs (dependency injection).

    Returns:
        AggregatedDataResponse: Data for charts in React (Plotly.js) format.

    Raises:
        AppException 403: If user has no read access to dashboard.
        AppException 404: If dashboard or graph not found.
        AppException 500: On server error.
    """
    logger.info(
        "Aggregated data request: dashboard_id=%s, user_id=%s, filters=%s",
        dashboard_id,
        current_user.id,
        filters,
    )

    # Check that user has access to the dashboard
    if not await check_dashboard_access(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        required_permission=DashboardPermission.VIEW,
        db=db,
    ):
        logger.warning(
            "Access denied to dashboard: dashboard_id=%s, user_id=%s",
            dashboard_id,
            current_user.id,
        )
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail="You do not have access to this dashboard",
        )

    try:
        # Parse filters from JSON string
        parsed_filters: dict[str, Any] | None = None
        if filters:
            try:
                parsed_filters = AggregatedFiltersRequest(
                    filters=json.loads(filters)
                ).parsed
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning("Invalid filters payload")
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    detail="Invalid filters payload",
                ) from e

        caps = get_config().data

        # When graph_id is provided, return data for single graph
        if graph_id is not None:
            # Get graph to retrieve type and name using repository
            single_graph = await graph_repo.get(id=graph_id, db=db)

            if single_graph is None:
                logger.warning("Graph not found: graph_id=%s", graph_id)
                raise AppException(
                    code=ErrorCode.GRAPH_NOT_FOUND,
                    detail="Graph not found",
                )

            # Scope the graph to the dashboard the request names. Access to the
            # parent dashboard was granted above, before this lookup, so the
            # authorization cannot be bypassed by naming another dashboard's
            # graph here. A graph that exists under a different dashboard is
            # reported as not found: to a caller who may read this dashboard it
            # must not disclose that the graph exists elsewhere, and the rows
            # read below must never cross the dashboard boundary.
            if single_graph.dashboard_id != dashboard_id:
                logger.warning(
                    "Graph does not belong to the requested dashboard: "
                    "graph_id=%s, graph_dashboard_id=%s, requested_dashboard_id=%s",
                    graph_id,
                    single_graph.dashboard_id,
                    dashboard_id,
                )
                raise AppException(
                    code=ErrorCode.GRAPH_NOT_FOUND,
                    detail="Graph not found",
                )

            records, total_rows = await data_service.get_bounded_aggregated_data(
                dashboard_id=dashboard_id,
                graph_id=graph_id,
                db=db,
                max_rows=caps.max_rows_per_graph,
                filters=parsed_filters,
            )
            data_points = _flatten_points(records)
            returned_rows = len(data_points)
            rows_truncated = total_rows > returned_rows

            logger.info(
                "Aggregated data retrieved: dashboard_id=%s, graph_id=%s, "
                "returned=%d, total=%d, truncated=%s",
                dashboard_id,
                graph_id,
                returned_rows,
                total_rows,
                rows_truncated,
            )

            return AggregatedDataResponse(
                graphs=[
                    GraphDataResponse(
                        graph_id=str(graph_id),
                        type=single_graph.type,
                        name=single_graph.name,
                        data=data_points,
                        returned_rows=returned_rows,
                        total_rows=total_rows,
                        rows_truncated=rows_truncated,
                        config=single_graph.config,
                    )
                ],
                total_rows=total_rows,
                truncated=rows_truncated,
            )

        # When graph_id is absent, return data for all graphs in dashboard
        graphs = await graph_repo.get_by_dashboard_id(dashboard_id, db)
        graph_responses: list[GraphDataResponse] = []
        remaining_budget = caps.max_rows_total
        any_truncated = False

        for graph_item in graphs:
            records, total_rows = await data_service.get_bounded_aggregated_data(
                dashboard_id=dashboard_id,
                graph_id=graph_item.id,
                db=db,
                max_rows=min(caps.max_rows_per_graph, remaining_budget),
                filters=parsed_filters,
            )
            data_points = _flatten_points(records)
            returned_rows = len(data_points)
            remaining_budget -= returned_rows
            rows_truncated = total_rows > returned_rows
            any_truncated = any_truncated or rows_truncated

            logger.info(
                "Aggregated data retrieved: dashboard_id=%s, graph_id=%s, "
                "returned=%d, total=%d, truncated=%s",
                dashboard_id,
                graph_item.id,
                returned_rows,
                total_rows,
                rows_truncated,
            )

            graph_responses.append(
                GraphDataResponse(
                    graph_id=str(graph_item.id),
                    type=graph_item.type,
                    name=graph_item.name,
                    data=data_points,
                    returned_rows=returned_rows,
                    total_rows=total_rows,
                    rows_truncated=rows_truncated,
                    config=graph_item.config,
                )
            )

        dashboard_total = await data_service.count_dashboard_aggregated_data(
            dashboard_id=dashboard_id, db=db,
        )
        return AggregatedDataResponse(
            graphs=graph_responses,
            total_rows=dashboard_total,
            truncated=any_truncated,
        )

    except AppException:
        # Propagate application exceptions untouched so their RFC 7807 code
        # and status (e.g. VALIDATION_ERROR from an invalid filters payload)
        # reach the client instead of being wrapped as INTERNAL_ERROR. The
        # broad handler below previously swallowed this route's own
        # AppException, so an invalid filters payload answered 500.
        raise
    except ValueError as e:
        logger.warning("Error getting data: %s", e)
        raise AppException(
            code=ErrorCode.NOT_FOUND,
            detail=str(e),
        ) from e
    except DashboardPermissionError as e:
        logger.warning("Access denied: %s", e)
        raise AppException(
            code=ErrorCode.PERMISSION_DENIED,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "Error getting aggregated data for dashboard id=%s: %s",
            dashboard_id,
            e,
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Error getting data",
        ) from e