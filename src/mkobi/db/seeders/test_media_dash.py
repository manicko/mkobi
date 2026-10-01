"""Seeder for test_media_dash dashboard.

Creates a test dashboard with graphs, filters, and processing config.
Idempotent - can be re-run without creating duplicates, and never removes
graphs or their uploaded data.
Safe for parallel xdist execution with ON CONFLICT patterns.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.db.models import Dashboard, Graph, ProcessingConfig
from mkobi.db.models.filters import Filter, dashboard_filters
from mkobi.db.session import get_async_sessionlocal
from mkobi.models.enums import FilterType, GraphType

logger = logging.getLogger(__name__)

DASHBOARD_NAME = "test_media_dash"


async def ensure_test_media_dash(db: AsyncSession | None = None) -> dict[str, Any]:
    """Create or update test_media_dash dashboard with all related records.

    This function is idempotent and safe for parallel xdist execution.
    Uses ON CONFLICT DO UPDATE patterns to handle race conditions gracefully.

    Args:
        db: Optional AsyncSession to use. If None, creates its own session.
            When provided, the caller is responsible for commit/rollback.

    Returns:
        dict with created/updated record IDs.
    """
    result: dict[str, Any] = {
        "dashboard_id": None,
        "graph_ids": [],
        "filter_ids": [],
        "action": "none",
    }

    own_session = False
    if db is None:
        SessionLocal = await get_async_sessionlocal()
        db = SessionLocal()
        own_session = True

    try:
        # Check if dashboard already exists to determine action
        existing_dashboard_stmt = select(Dashboard).where(
            Dashboard.name == DASHBOARD_NAME
        )
        existing_dashboard = (
            await db.execute(existing_dashboard_stmt)
        ).scalar_one_or_none()
        is_update = existing_dashboard is not None

        # Upsert dashboard with ON CONFLICT DO UPDATE
        upsert_dashboard = pg_insert(Dashboard).values(
            name=DASHBOARD_NAME,
            description="Test media dashboard",
            config={
                "graph_types": ["bar"],
                "filters": [
                    {
                        "field": "targetaudience",
                        "type": "multiselect",
                        "source": "data",
                        "multi": True,
                    },
                    {
                        "field": "category",
                        "type": "multiselect",
                        "source": "data",
                        "multi": True,
                    },
                ],
            },
        )
        upsert_dashboard = upsert_dashboard.on_conflict_do_update(
            index_elements=["name"],
            set_={
                "description": upsert_dashboard.excluded.description,
                "config": upsert_dashboard.excluded.config,
            },
        ).returning(Dashboard.id)

        dashboard_id = (await db.execute(upsert_dashboard)).scalar_one()
        result["action"] = "updated" if is_update else "created"

        result["dashboard_id"] = str(dashboard_id)

        # Upsert filter for targetaudience
        upsert_filter = pg_insert(Filter).values(
            name="targetaudience",
            type=FilterType.MULTISELECT.value,
            config={"source": "data"},
        )
        upsert_filter = upsert_filter.on_conflict_do_update(
            index_elements=["name"],
            set_={
                "type": upsert_filter.excluded.type,
                "config": upsert_filter.excluded.config,
            },
        ).returning(Filter.id)
        filter1_id = (await db.execute(upsert_filter)).scalar_one()

        # Upsert filter for category
        upsert_filter2 = pg_insert(Filter).values(
            name="category",
            type=FilterType.MULTISELECT.value,
            config={"source": "data"},
        )
        upsert_filter2 = upsert_filter2.on_conflict_do_update(
            index_elements=["name"],
            set_={
                "type": upsert_filter2.excluded.type,
                "config": upsert_filter2.excluded.config,
            },
        ).returning(Filter.id)
        filter2_id = (await db.execute(upsert_filter2)).scalar_one()

        result["filter_ids"] = [str(filter1_id), str(filter2_id)]

        # Insert graph for Monthly TVR by Brand
        insert_graph = pg_insert(Graph).values(
            dashboard_id=dashboard_id,
            name="Monthly TVR by Brand",
            type=GraphType.BAR.value,
            config={
                "x": "month_label",
                "color": "brand",
                "metrics": ["tvr_sum"],
                "orientation": "v",
                "barmode": "stack",
            },
            dimensions=["year", "month", "month_label", "brand"],
            metrics=["tvr"],
        )
        insert_graph = insert_graph.on_conflict_do_nothing(
            index_elements=["dashboard_id", "name"]
        ).returning(Graph.id)
        graph1_row = (await db.execute(insert_graph)).fetchone()
        if graph1_row:
            graph1_id = graph1_row[0]
        else:
            # Fetch existing graph after conflict (race condition)
            graph1_stmt = select(Graph.id).where(
                Graph.dashboard_id == dashboard_id,
                Graph.name == "Monthly TVR by Brand",
            )
            graph1_id = (await db.execute(graph1_stmt)).scalar_one()

        # Insert graph for Monthly TVR by Advertiser
        insert_graph2 = pg_insert(Graph).values(
            dashboard_id=dashboard_id,
            name="Monthly TVR by Advertiser",
            type=GraphType.BAR.value,
            config={
                "x": "month_label",
                "color": "advertiser",
                "metrics": ["tvr_sum"],
                "orientation": "v",
                "barmode": "stack",
            },
            dimensions=["year", "month", "month_label", "advertiser"],
            metrics=["tvr"],
        )
        insert_graph2 = insert_graph2.on_conflict_do_nothing(
            index_elements=["dashboard_id", "name"]
        ).returning(Graph.id)
        graph2_row = (await db.execute(insert_graph2)).fetchone()
        if graph2_row:
            graph2_id = graph2_row[0]
        else:
            graph2_stmt = select(Graph.id).where(
                Graph.dashboard_id == dashboard_id,
                Graph.name == "Monthly TVR by Advertiser",
            )
            graph2_id = (await db.execute(graph2_stmt)).scalar_one()

        result["graph_ids"] = [str(graph1_id), str(graph2_id)]

        # Remove existing filter bindings for this dashboard
        await db.execute(
            dashboard_filters.delete().where(
                dashboard_filters.c.dashboard_id == dashboard_id
            )
        )

        # Insert filter bindings with ON CONFLICT DO NOTHING
        await db.execute(
            pg_insert(dashboard_filters).on_conflict_do_nothing(),
            [
                {"dashboard_id": dashboard_id, "filter_id": filter1_id},
                {"dashboard_id": dashboard_id, "filter_id": filter2_id},
            ],
        )

        # Upsert processing config
        upsert_proc = pg_insert(ProcessingConfig).values(
            dashboard_id=dashboard_id,
            settings={
                "separator": ";",
                "encoding": "utf-8-sig",
                "date_format": "%d/%m/%Y",
                "decimal_separator": ",",
                "column_types": {
                    "date": "date",
                    "TVR": "float",
                    "advertiser": "str",
                    "brand": "str",
                    "targetaudience": "str",
                    "category": "str",
                },
                "date_column": "date",
                "computed_fields": [
                    {"name": "year", "expr": "pl.col('date').dt.year()"},
                    {"name": "month", "expr": "pl.col('date').dt.month()"},
                    {
                        "name": "month_label",
                        "expr": "pl.col('date').dt.strftime('%b %Y')",
                    },
                ],
                "renames": {"TVR": "tvr"},
            },
        )
        upsert_proc = upsert_proc.on_conflict_do_update(
            index_elements=["dashboard_id"],
            set_={"settings": upsert_proc.excluded.settings},
        )
        await db.execute(upsert_proc)

        # Commit all changes (only if we own the session)
        if own_session:
            await db.commit()

        logger.info(
            "Test dashboard %s: id=%s, filters=%s, graphs=%s",
            result["action"],
            result["dashboard_id"],
            result["filter_ids"],
            result["graph_ids"],
        )

    finally:
        if own_session:
            await db.close()

    return result
