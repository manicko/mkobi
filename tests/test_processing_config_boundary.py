"""Tests for the processing-settings boundary (DP-014).

Two contracts are pinned here.

* **Mutation order (worker).** ``workers/data_worker.py::_run_with_transaction``
  must validate the frame *after* the column cast and the rename, before the
  computed fields. Validating the pre-rename, pre-cast frame makes a configured
  ``required_columns`` inspect a namespace the frame no longer has by the time
  it is used, and makes a ``column_types`` check inspect ``Utf8`` columns that
  are ``Int64`` by aggregation time.
* **Settings shape.** ``ProcessingConfigUpdate.settings`` is
  ``ProcessingSettingsModel`` with ``extra="forbid"``. An unknown settings key
  is a request-boundary ``422`` instead of being silently dropped.

The T-numbers label the block's required tests so a later reader can find them.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from httpx import AsyncClient

from mkobi.models.enums import DashboardPermission, ProcessingStatus
from mkobi.models.types import ProcessingSettingsModel
from mkobi.utils.exceptions import ErrorCode

# The nineteen keys the worker reads. Listed explicitly so the OpenAPI property
# assertion fails loudly if the model gains or loses a detail.
NINETEEN_SETTINGS_KEYS: frozenset[str] = frozenset(
    {
        "separator",
        "encoding",
        "column_types",
        "required_columns",
        "decimal_separator",
        "date_format",
        "renames",
        "computed_fields",
        "metric_agg",
        "filters",
        "groupby",
        "aggregations",
        "sort_by",
        "descending",
        "limit",
        "yoy_config",
        "share_config",
        "custom_metrics",
        "metrics",
    }
)

# Declared but read by nothing in src/, kept because the seeder writes them.
KEPT_UNREAD_SETTINGS_KEYS: frozenset[str] = frozenset(
    {"loader", "date_column", "timezone"}
)

# The full property set the boundary model declares.
DECLARED_SETTINGS_KEYS: frozenset[str] = (
    NINETEEN_SETTINGS_KEYS | KEPT_UNREAD_SETTINGS_KEYS
)

# The five keys the worker reads but which the retired TypedDict never declared,
# so they were silently dropped at the request boundary.
NEWLY_DECLARED_KEYS: tuple[str, ...] = (
    "required_columns",
    "limit",
    "sort_by",
    "descending",
    "metrics",
)

# Full payload used by the round-trip test (T6) -- every one of the nineteen
# keys, each with a value of its real runtime shape.
FULL_SETTINGS: dict[str, Any] = {
    "separator": ";",
    "encoding": "utf-8",
    "column_types": {"revenue": "float", "year": "int"},
    "required_columns": ["revenue", "year"],
    "decimal_separator": ",",
    "date_format": "%Y-%m-%d",
    "renames": {"revenue": "total_revenue"},
    "computed_fields": [{"name": "profit", "expr": "revenue - cost"}],
    "metric_agg": "mean",
    "filters": [{"column": "year", "operator": ">=", "value": 2020}],
    "groupby": ["category"],
    "aggregations": [{"column": "revenue", "function": "sum", "alias": "total"}],
    "sort_by": ["year"],
    "descending": True,
    "limit": 10,
    "yoy_config": {"year_column": "year", "value_column": "revenue"},
    "share_config": {"value_column": "revenue"},
    "custom_metrics": [{"name": "profit", "expr": "revenue - cost"}],
    "metrics": [{"name": "revenue", "type": "float"}],
}


async def _make_dashboard_with_edit_access(client: AsyncClient, db, user: dict) -> Any:
    """Create a dashboard owned by the test user and return it."""
    from uuid import uuid4

    from mkobi.db.repositories.access_repo import AccessRepository
    from mkobi.db.repositories.dashboard_repo import DashboardRepository
    from mkobi.services.dashboard_service import DashboardService

    service = DashboardService(DashboardRepository(), AccessRepository())
    dashboard = await service.create_dashboard(
        name=f"boundary-test-{uuid4().hex[:8]}",
        config={"graph_types": ["bar"]},
        owner_id=user["id"],
        db=db,
    )
    await AccessRepository().grant_access(
        db=db,
        user_id=user["id"],
        dashboard_id=dashboard.id,
        permission=DashboardPermission.EDIT,
    )
    await db.commit()
    return dashboard


# ==================== T1 / T2 / T5: worker mutation order ====================


@pytest.mark.asyncio
class TestWorkerMutationOrder:
    """DP-014 (i): validation runs after the cast and the rename."""

    async def _seed_dashboard(
        self, db, *, metric: str = "revenue"
    ) -> tuple[Any, Any, str]:
        """Create a dashboard, a graph and a processing log; return them."""
        from uuid import uuid4

        from mkobi.db.repositories.dashboard_repo import DashboardRepository
        from mkobi.db.repositories.graph_repo import GraphRepository
        from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository
        from mkobi.models.enums import GraphType

        dashboard = await DashboardRepository().create(
            db=db,
            name=f"mutation-order-{uuid4().hex[:8]}",
            description="mutation order dashboard",
        )
        graph = await GraphRepository().create(
            db=db,
            dashboard_id=dashboard.id,
            name="Boundary Graph",
            type=GraphType.TABLE,
            config={},
            dimensions=["category"],
            metrics=[metric],
        )
        log = await ProcessingLogRepository().create_log(
            dashboard_id=dashboard.id,
            status=ProcessingStatus.UPLOADED,
            message="Uploaded",
            db=db,
        )
        await db.commit()
        return dashboard, graph, str(log.id)

    async def test_t1_required_columns_use_post_rename_namespace(
        self, async_db_session
    ) -> None:
        """T1: ``required_columns`` naming the post-rename name completes.

        The CSV carries ``revenue``; a rename maps it to ``revenue_amount``; the
        configured ``required_columns`` names ``revenue_amount``. Validating
        after the rename is the only order in which the intended name resolves.
        Fails against the unfixed code with "Missing required columns:
        revenue_amount".
        """
        import tempfile
        from pathlib import Path

        await async_db_session.commit()
        dashboard, _graph, task_id = await self._seed_dashboard(
            async_db_session, metric="revenue_amount"
        )
        settings = {
            "renames": {"revenue": "revenue_amount"},
            "required_columns": ["revenue_amount"],
        }

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False
        ) as handle:
            handle.write(b"category,revenue\nAlpha,10\n")
            csv_path = handle.name


        try:
            await _run_processing(
                csv_path=csv_path,
                task_id=task_id,
                dashboard_id=dashboard.id,
                settings=settings,
                db_session=async_db_session,
            )
            from mkobi.db.repositories.processing_log_repo import (
                ProcessingLogRepository,
            )

            log = await ProcessingLogRepository().get_by_id(task_id, async_db_session)
            assert log is not None
            assert log.status == ProcessingStatus.COMPLETED
        finally:
            Path(csv_path).unlink(missing_ok=True)

    async def test_t2_absent_column_type_logs_warning_and_continues(
        self, async_db_session
    ) -> None:
        """T2: a ``column_types`` key naming an absent column warns and continues.

        The guard has no ``else``, so today the miss leaves no record at all and
        the run continues silently. The asserted outcome is the log record for
        the absent column.
        """
        import tempfile
        from pathlib import Path

        dashboard, _graph, task_id = await self._seed_dashboard(async_db_session)
        settings = {"column_types": {"ghost_column": "int"}}
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False
        ) as handle:
            handle.write(b"category,revenue\nAlpha,10\n")
            csv_path = handle.name

        records = _capture_logs("mkobi.workers.data_worker")
        try:
            await _run_processing(
                csv_path=csv_path,
                task_id=task_id,
                dashboard_id=dashboard.id,
                settings=settings,
                db_session=async_db_session,
            )
            assert any(
                record.levelno == logging.WARNING
                and "ghost_column" in record.getMessage()
                for record in records
            ), "an absent column_types key must be logged at warning level"
        finally:
            _release_logs("mkobi.workers.data_worker", records)
            Path(csv_path).unlink(missing_ok=True)

    async def test_t5_column_types_check_record_still_present(
        self, async_db_session
    ) -> None:
        """T5 (the record this block changed): a correctly-cast float column does not warn.

        History, kept readable: this test was written by PB-8 to pin the shipped
        state at the time -- ``DataValidator._validate_column_types`` warned
        because the worker's cast guard carried ``and col_type != "float"`` and
        the ``float`` term was deliberately left untouched, with **PB-9** and
        ``D-05-F`` named as its owner. PB-9 removed that term and taught the cast
        loop to produce ``Float64``, so the warning this assertion used to require
        is no longer the truth: a declared ``{"revenue": "float"}`` column is now
        cast and the validator finds a matching ``Float64`` dtype.

        The assertion is therefore inverted, not deleted: the type-mismatch
        warning must now be **absent** for a correctly-cast float column. A
        genuinely mistyped column still warns -- pinned separately in
        ``tests/test_validation_warning_logging.py`` -- so the signal was fixed,
        not removed.
        """
        import tempfile
        from pathlib import Path

        dashboard, _graph, task_id = await self._seed_dashboard(async_db_session)
        # ``revenue`` is inferred as Int64 from the CSV; the declared type is
        # "float", so the cast loop now casts it to Float64 and the validator's
        # type correspondence check finds a match instead of warning.
        settings = {"column_types": {"revenue": "float"}}

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False
        ) as handle:
            handle.write(b"category,revenue\nAlpha,10\n")
            csv_path = handle.name

        records = _capture_logs("mkobi.data.loaders.validator")
        try:
            await _run_processing(
                csv_path=csv_path,
                task_id=task_id,
                dashboard_id=dashboard.id,
                settings=settings,
                db_session=async_db_session,
            )
            assert not any(
                "expected type 'float'" in record.getMessage()
                for record in records
            ), "a correctly-cast float column must not produce a type-mismatch warning"
        finally:
            _release_logs("mkobi.data.loaders.validator", records)
            Path(csv_path).unlink(missing_ok=True)


def _capture_logs(logger_name: str) -> list[logging.LogRecord]:
    """Attach a warning-level collector to a named logger.

    The application's logging setup runs with ``propagate=False`` on every
    named logger, so pytest's ``caplog`` root handler never sees these records.
    A handler attached directly to the emitting logger is the project's
    established capture pattern (see ``tests/test_starter.py``).
    """
    logger = logging.getLogger(logger_name)
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    collector = _Collector(level=logging.WARNING)
    collector._additional = (logger, logger.level, logger.disabled)  # type: ignore[attr-defined]
    logger.addHandler(collector)
    logger.setLevel(logging.WARNING)
    logger.disabled = False
    return records


def _release_logs(logger_name: str, records: list[logging.LogRecord]) -> None:
    """Detach the collector attached by :func:`_capture_logs`."""
    logger = logging.getLogger(logger_name)
    for handler in list(logger.handlers):
        if isinstance(handler, logging.Handler) and getattr(
            handler, "_additional", None
        ) is not None:
            original_level = handler._additional[1]  # type: ignore[attr-defined]
            was_disabled = handler._additional[2]  # type: ignore[attr-defined]
            logger.removeHandler(handler)
            logger.setLevel(original_level)
            logger.disabled = was_disabled
            break


async def _run_processing(
    *,
    csv_path: str,
    task_id: str,
    dashboard_id: Any,
    settings: dict[str, Any],
    db_session: Any,
) -> None:
    """Run the real worker against a processing-configurable settings payload.

    Uses the top-level producer shape ``processing_config_dict`` that
    ``DataService._execute_upload`` builds, so the worker reads ``settings`` the
    same way production does.
    """
    from mkobi.workers.data_worker import process_csv_background

    await process_csv_background(
        file_path_str=csv_path,
        task_id=task_id,
        dashboard_id_str=str(dashboard_id),
        processing_config_dict={"settings": settings, **settings},
        mode="overwrite",
        db_session=db_session,
    )


# ==================== T3 / T6 / T7: settings boundary ====================


@pytest.mark.asyncio
class TestSettingsBoundaryAPI:
    """DP-014 (ii): the request boundary forbids unknown settings keys."""

    async def test_t3_unknown_settings_key_is_422_validation_error(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """T3: an unknown settings key returns 422 with ``code=VALIDATION_ERROR``.

        A single status assertion, plus a guard that the rejection is not the
        misleading route-level "Settings cannot be empty" 422: an all-unknown
        body already 422s today with that detail, so a test that only checked
        the status would pass against the unfixed code for the wrong reason.
        """
        dashboard = await _make_dashboard_with_edit_access(
            authenticated_client, async_db_session, test_user
        )
        response = await authenticated_client.put(
            f"/processing-configs/{dashboard.id}",
            json={"settings": {"loader": "L", "bogus_key": 1}},
        )
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == ErrorCode.VALIDATION_ERROR.value
        assert "Settings cannot be empty" not in response.text

    async def test_t6_full_settings_round_trip(
        self, authenticated_client: AsyncClient, async_db_session, test_user: dict
    ) -> None:
        """T6: a PUT of all nineteen keys stores every key and GET returns them.

        Fails against the unfixed code on the five keys the TypedDict dropped:
        they never reach storage.
        """
        dashboard = await _make_dashboard_with_edit_access(
            authenticated_client, async_db_session, test_user
        )
        put = await authenticated_client.put(
            f"/processing-configs/{dashboard.id}",
            json={"settings": FULL_SETTINGS},
        )
        assert put.status_code == 200

        got = await authenticated_client.get(
            f"/processing-configs/{dashboard.id}"
        )
        assert got.status_code == 200
        stored_settings = got.json()["settings"]
        # Every key survives; nested shapes may gain model defaults, so compare
        # the declared key set plus the scalar/simple values.
        assert set(stored_settings) >= set(FULL_SETTINGS)
        for key in (
            "separator",
            "encoding",
            "required_columns",
            "decimal_separator",
            "date_format",
            "renames",
            "groupby",
            "sort_by",
            "descending",
            "limit",
            "column_types",
            "metrics",
        ):
            assert stored_settings.get(key) == FULL_SETTINGS[key], (
                f"settings key {key!r} not stored"
            )

        # metric_agg still merges into / extracts from settings.
        assert got.json()["metric_agg"] == "mean"
        assert stored_settings["metric_agg"] == "mean"

    @pytest.mark.parametrize("key", NEWLY_DECLARED_KEYS)
    async def test_t7_newly_declared_keys_are_accepted(
        self,
        key: str,
        authenticated_client: AsyncClient,
        async_db_session,
        test_user: dict,
    ) -> None:
        """T7: the five newly-declared keys are accepted, not 422.

        Green-on-arrival guard, not proof of the fix: the boundary must not
        reject keys the worker reads, and the stored payload must keep them.
        """
        dashboard = await _make_dashboard_with_edit_access(
            authenticated_client, async_db_session, test_user
        )
        response = await authenticated_client.put(
            f"/processing-configs/{dashboard.id}",
            json={"settings": {key: FULL_SETTINGS[key]}},
        )
        assert response.status_code == 200
        assert response.json()["settings"][key] == FULL_SETTINGS[key]


# ==================== T4: OpenAPI tripwire ====================


class TestSettingsOpenAPISchema:
    """DP-014 (ii): the boundary type is visible in the OpenAPI document."""

    def test_t4_put_request_body_forbids_unknown_settings_keys(self) -> None:
        """T4: the PUT request body's settings object has ``additionalProperties: false``.

        Written from scratch -- ``tests/test_openapi.py`` had no ``app.openapi()``
        call. Only satisfiable once ``settings`` is a ``BaseModel``: a
        ``TypedDict`` emits no ``additionalProperties: false``. The property set
        must equal the nineteen declared keys.
        """
        from mkobi.main import app

        schema = app.openapi()
        put_path = next(
            path
            for path in schema["paths"]
            if path.endswith("/processing-configs/{dashboard_id}")
        )
        put = schema["paths"][put_path]["put"]
        request_schema = put["requestBody"]["content"]["application/json"]["schema"]
        resolved = _resolve_ref(schema, request_schema)
        settings_schema = _resolve_ref(schema, resolved["properties"]["settings"])

        assert settings_schema.get("additionalProperties") is False
        assert set(settings_schema["properties"]) == DECLARED_SETTINGS_KEYS


def _resolve_ref(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Resolve a ``$ref`` node, unwrapping an ``anyOf`` null-union.

    FastAPI emits an optional field as ``{"anyOf": [{"$ref": ...}, {"type":
    "null"}]}``, so the object schema is the non-null branch.
    """
    if "anyOf" in node:
        for branch in node["anyOf"]:
            if branch.get("type") != "null":
                return _resolve_ref(schema, branch)
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return schema["components"]["schemas"][name]
    return node


# ==================== T8: seeder compatibility ====================


class TestSeederSettingsCompatibility:
    """T8: the seeder's stored settings still validate against the model."""

    def test_t8_seeder_settings_validate(self) -> None:
        """T8: the seeder's eight keys validate as a ``ProcessingSettingsModel``.

        Green-on-arrival guard: the strict boundary must not invalidate the only
        non-API writer's stored payload.
        """
        from mkobi.db.seeders.test_media_dash import _SEEDED_PROCESSING_SETTINGS

        model = ProcessingSettingsModel.model_validate(_SEEDED_PROCESSING_SETTINGS)
        assert model.date_column == "date"
