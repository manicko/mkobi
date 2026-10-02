"""Tests for the validation-warning consumer (DP-013).

Three contracts are pinned here.

* **Reachability.** ``ValidationResult.warnings`` had no production consumer:
  the worker read only ``is_valid`` and ``errors`` and then wrote its completion
  sentence, so a data-quality warning reached nobody. A warning must now land in
  ``processing_logs.message``.
* **The cap.** ``processing_logs.message`` is ``String(1000)``. An overflowing
  warning summary truncates by a defined, tested rule.
* **The never-true check.** The ``column_types`` ``float`` check warned on every
  run because the worker's cast loop skipped ``float``. A declared float column
  is now cast and no longer warns, while a genuinely mistyped column still does.
"""

from __future__ import annotations

from typing import Any

import pytest

from mkobi.models.enums import ProcessingStatus
from mkobi.workers.data_worker import (
    PROCESSING_LOG_MESSAGE_MAX_LENGTH,
    _compose_completion_message,
)


async def _seed_dashboard(db, *, metric: str = "revenue") -> tuple[Any, Any, str]:
    """Create a dashboard, a graph and a processing log; return them."""
    from uuid import uuid4

    from mkobi.db.repositories.dashboard_repo import DashboardRepository
    from mkobi.db.repositories.graph_repo import GraphRepository
    from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository
    from mkobi.models.enums import GraphType

    dashboard = await DashboardRepository().create(
        db=db,
        name=f"validation-warning-{uuid4().hex[:8]}",
        description="validation warning logging",
    )
    graph = await GraphRepository().create(
        db=db,
        dashboard_id=dashboard.id,
        name="Warning Graph",
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


async def _run_processing(
    *,
    csv_path: str,
    task_id: str,
    dashboard_id: Any,
    settings: dict[str, Any],
    db_session: Any,
) -> None:
    """Run the real worker against a processing-configurable settings payload."""
    from mkobi.workers.data_worker import process_csv_background

    await process_csv_background(
        file_path_str=csv_path,
        task_id=task_id,
        dashboard_id_str=str(dashboard_id),
        processing_config_dict={"settings": settings, **settings},
        mode="overwrite",
        db_session=db_session,
    )


def _write_csv(content: bytes) -> str:
    """Write a temporary CSV and return its path."""
    import tempfile

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as handle:
        handle.write(content)
        return handle.name


@pytest.mark.asyncio
class TestWarningReachesProcessingLogMessage:
    """DP-013: warnings land in ``processing_logs.message``."""

    async def test_data_quality_warning_reaches_processing_log_message(
        self, async_db_session
    ) -> None:
        """A duplicate-row warning is written to the stored completion message.

        Fails against the unfixed code: nothing read ``ValidationResult.warnings``,
        so the stored message was only the completion sentence. The duplicate
        rows survive to the validation frame (validation runs before the
        aggregation), so the warning set is non-empty.
        """
        from pathlib import Path

        from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository

        dashboard, _graph, task_id = await _seed_dashboard(async_db_session)
        settings: dict[str, Any] = {}
        csv_path = _write_csv(
            b"category,revenue\nAlpha,10\nAlpha,10\nBeta,20\n"
        )

        try:
            await _run_processing(
                csv_path=csv_path,
                task_id=task_id,
                dashboard_id=dashboard.id,
                settings=settings,
                db_session=async_db_session,
            )
            log = await ProcessingLogRepository().get_by_id(task_id, async_db_session)
            assert log is not None
            assert log.status == ProcessingStatus.COMPLETED
            assert log.message is not None
            assert "duplicate" in log.message.lower()
        finally:
            Path(csv_path).unlink(missing_ok=True)


class TestWarningSummaryCap:
    """DP-013 / D-05-F(b): the ``String(1000)`` cap and truncation rule."""

    def test_warning_summary_truncates_at_the_column_cap(self) -> None:
        """An overflowing summary is cut to the cap and marked ``...[truncated]``.

        Truncation rule (asserted exactly, not described): the completion
        sentence is the prefix and is never shortened while it fits; the warning
        summary fills the remaining budget; if it overflows, the last
        ``len("...[truncated]")`` characters of the budget are replaced by the
        marker ``...[truncated]``.
        """
        marker = "...[truncated]"
        sentence = "Processing completed successfully: 3 rows processed"
        summary = "Validation result: PASSED " + ("warning-detail " * 200)

        message = _compose_completion_message(sentence, summary)

        assert len(message) == PROCESSING_LOG_MESSAGE_MAX_LENGTH
        assert message.startswith(sentence)
        assert message.endswith(marker)
        # The exact truncation point: the summary is cut so that the marker is
        # the final ``len(marker)`` characters of the message.
        prefix_len = len(f"{sentence} | Warnings: ")
        keep = PROCESSING_LOG_MESSAGE_MAX_LENGTH - prefix_len - len(marker)
        assert message[prefix_len:-len(marker)] == summary[:keep]

    def test_summary_that_fits_is_not_marked_truncated(self) -> None:
        """A summary within budget is written whole, with no truncation marker."""
        sentence = "Processing completed successfully: 1 rows processed"
        summary = "Validation result: PASSED Warnings (1): - Found 1 duplicate rows"

        message = _compose_completion_message(sentence, summary)

        assert message == f"{sentence} | Warnings: {summary}"
        assert "...[truncated]" not in message

    def test_no_warnings_returns_the_completion_sentence_unchanged(self) -> None:
        """With no warnings the message is byte-identical to the pre-PB-9 text."""
        sentence = "Processing completed successfully: 5 rows processed"

        assert _compose_completion_message(sentence, "") == sentence


@pytest.mark.asyncio
class TestFloatCastFix:
    """DP-013: the never-true ``float`` check is made true, not deleted."""

    async def test_declared_float_column_is_cast_and_produces_no_type_warning(
        self, async_db_session
    ) -> None:
        """A declared ``{"revenue": "float"}`` column produces no type warning.

        Fails against the unfixed code: the cast loop skipped ``float``, so
        ``revenue`` stayed ``Int64`` and the validator warned
        ``expected type 'float', actual type 'Int64'`` on every run. Asserts the
        absence of that validator record directly -- the stored message alone
        would pass trivially on unfixed code, which wrote no warnings at all.
        """
        from pathlib import Path

        from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository

        from tests.test_processing_config_boundary import (
            _capture_logs,
            _release_logs,
        )

        dashboard, _graph, task_id = await _seed_dashboard(async_db_session)
        settings = {"column_types": {"revenue": "float"}}
        csv_path = _write_csv(b"category,revenue\nAlpha,10\nBeta,20\n")

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
                "expected type 'float'" in record.getMessage() for record in records
            ), "a correctly-cast float column must not produce a type warning"
            log = await ProcessingLogRepository().get_by_id(task_id, async_db_session)
            assert log is not None
            assert log.status == ProcessingStatus.COMPLETED
            assert "expected type 'float'" not in (log.message or "")
        finally:
            _release_logs("mkobi.data.loaders.validator", records)
            Path(csv_path).unlink(missing_ok=True)

    async def test_genuinely_mistyped_column_still_warns(self, async_db_session) -> None:
        """A genuinely mistyped column still produces a warning.

        Guard against removing the signal rather than fixing it: a column
        declared ``date`` with no ``date_format`` cannot be cast, so the
        validator's type check must still warn and that warning must reach the
        stored message.
        """
        from pathlib import Path

        from mkobi.db.repositories.processing_log_repo import ProcessingLogRepository

        dashboard, _graph, task_id = await _seed_dashboard(async_db_session)
        settings = {"column_types": {"revenue": "date"}}
        csv_path = _write_csv(b"category,revenue\nAlpha,10\nBeta,20\n")

        try:
            await _run_processing(
                csv_path=csv_path,
                task_id=task_id,
                dashboard_id=dashboard.id,
                settings=settings,
                db_session=async_db_session,
            )
            log = await ProcessingLogRepository().get_by_id(task_id, async_db_session)
            assert log is not None
            assert log.status == ProcessingStatus.COMPLETED
            assert "expected type 'date'" in (log.message or "")
        finally:
            Path(csv_path).unlink(missing_ok=True)
