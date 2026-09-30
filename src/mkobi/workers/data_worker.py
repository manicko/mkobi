"""RQ worker tasks for background data processing.

Contains functions that are executed by RQ workers in separate processes.
These functions handle CSV processing, status updates, and database operations.
"""

import asyncio
import logging
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any

from uuid import UUID

import polars as pl
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.data.loaders.loader import CSVLoader
from mkobi.data.loaders.validator import DataValidator
from mkobi.data.processing.transformations import (
    _add_computed_fields,
    apply_transformations,
    calculate_aggregations,
)
from mkobi.db.models.graphs import Graph
from mkobi.db.models.processing_logs import ProcessingLog
from mkobi.db.models.filters import Filter, dashboard_filters
from mkobi.db.session import get_session
from mkobi.models.data import LoaderConfig, ProcessingConfig
from mkobi.models.enums import ErrorCode, ProcessingStatus

from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

# Default timeout for stale processing logs (in minutes)
DEFAULT_STALE_PROCESSING_TIMEOUT_MINUTES = 5


def _map_processing_error_to_code(error: Exception) -> str:
    """Map processing exception to ErrorCode string.

    Analyzes exception type and message to determine appropriate error code
    for RFC 7807 compliant error reporting.

    Args:
        error: The exception that occurred during processing.

    Returns:
        str: Error code string for error classification.
    """
    error_msg = str(error).lower()

    # File not found errors
    if isinstance(error, FileNotFoundError):
        return str(ErrorCode.FILE_UPLOAD_ERROR.value)

    # File format/encoding errors
    if "encoding" in error_msg:
        return str(ErrorCode.FILE_PROCESSING_ERROR.value)
    if "csv" in error_msg and ("read" in error_msg or "parse" in error_msg):
        return str(ErrorCode.FILE_PROCESSING_ERROR.value)

    # Validation errors
    if "missing required columns" in error_msg:
        return str(ErrorCode.VALIDATION_ERROR.value)
    if "validation failed" in error_msg:
        return str(ErrorCode.VALIDATION_ERROR.value)

    # File too large errors (caught earlier but just in case)
    if "too large" in error_msg or "size" in error_msg:
        return str(ErrorCode.FILE_TOO_LARGE.value)

    # Default to processing failed for all other errors
    return str(ErrorCode.PROCESSING_FAILED.value)


def _validate_processing_config(config: ProcessingConfig) -> None:
    """Validate ProcessingConfig fields before processing.

    Checks for invalid values in config fields that would cause errors
    during processing. Raises AppException with VALIDATION_ERROR code
    if any invalid values are found.

    Args:
        config: ProcessingConfig to validate.

    Raises:
        AppException: If any config field contains invalid values.
    """
    # Validate aggregations
    if config.aggregations:
        for agg in config.aggregations:
            column = getattr(agg, "column", None)
            if not column:
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    detail="Processing config has invalid aggregation: column name is missing or empty",
                )
            function = getattr(agg, "function", None)
            if not function:
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    detail="Processing config has invalid aggregation: function is missing or empty",
                )

    # Validate groupby for empty strings
    if config.groupby:
        if any(not col for col in config.groupby):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                detail="Processing config has empty groupby column name",
            )

    # Validate sort_by for empty strings
    if config.sort_by:
        if any(not col for col in config.sort_by):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                detail="Processing config has empty sort_by column name",
            )

    # Validate yoy_config required fields
    if config.yoy_config:
        year_col = getattr(config.yoy_config, "year_column", None)
        value_col = getattr(config.yoy_config, "value_column", None)
        if not year_col:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                detail="Processing config yoy_config missing required field: year_column",
            )
        if not value_col:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                detail="Processing config yoy_config missing required field: value_column",
            )

    # Validate share_config required fields
    if config.share_config:
        value_col = getattr(config.share_config, "value_column", None)
        if not value_col:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                detail="Processing config share_config missing required field: value_column",
            )

    # Validate custom_metrics required fields
    if config.custom_metrics:
        for metric in config.custom_metrics:
            name = getattr(metric, "name", None)
            expr = getattr(metric, "expr", None)
            if not name:
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    detail="Processing config has invalid custom_metric: name is missing or empty",
                )
            if not expr:
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    detail=f"Processing config has invalid custom_metric '{name}': expression is missing or empty",
                )

    # Validate metrics
    if config.metrics:
        for metric_dict in config.metrics:
            if not all(str(k) and str(v) for k, v in metric_dict.items()):
                raise AppException(
                    code=ErrorCode.VALIDATION_ERROR,
                    detail="Processing config has invalid metric: both name and type are required",
                )


async def _update_processing_log_status(
    task_id: str,
    status: ProcessingStatus,
    message: str,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    session: AsyncSession | None = None,
    error_code: str | None = None,
) -> None:
    """Update processing log status.

    Args:
        task_id: Task ID (UUID string).
        status: New status.
        message: Status message.
        started_at: Processing start time (only set if not already set).
        finished_at: Processing finish time.
        session: Optional database session for testing. If None, creates a new session.
            When provided, caller manages transaction (SAVEPOINT pattern).
        error_code: Error code for RFC 7807 error reporting (optional).
    """
    try:
        values: dict[str, Any] = {
            "status": status,
            "message": message,
        }

        if started_at is not None:
            values["started_at"] = started_at
        if error_code is not None:
            values["error_code"] = error_code
        if status in (ProcessingStatus.COMPLETED, ProcessingStatus.FAILED):
            values["finished_at"] = finished_at or datetime.now(UTC)

        stmt = (
            update(ProcessingLog)
            .where(ProcessingLog.id == UUID(task_id))
            .values(**values)
        )
        if session is not None:
            # Test mode - caller manages transaction (SAVEPOINT pattern in async_db_session).
            # Do NOT commit here - the caller's transaction boundary handles persistence.
            await session.execute(stmt)
        else:
            # Production mode - create new session with transaction
            async with get_session() as db:
                async with db.begin():
                    await db.execute(stmt)
        logger.info(
            "Processing log updated: task_id=%s, status=%s", task_id, status
        )
    except SQLAlchemyError as e:
        logger.error("Failed to update processing log status: %s", e)
        # No rollback in test mode - caller (SAVEPOINT) manages transaction
        raise
    except Exception as e:
        logger.exception("Unexpected error updating processing log status: %s", e)
        raise


async def cleanup_stale_processing_logs(
    timeout_minutes: int = DEFAULT_STALE_PROCESSING_TIMEOUT_MINUTES,
    session: AsyncSession | None = None,
) -> int:
    """Mark stale PROCESSING entries as FAILED.

    This function should be called periodically to detect processing jobs
    that were left in PROCESSING state due to worker crashes or timeouts.

    Args:
        timeout_minutes: Maximum age in minutes for entries to be considered stale.
            Entries older than this will be marked as FAILED.
        session: Optional database session. If None, creates a new session.

    Returns:
        int: Number of entries that were marked as FAILED.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)

    if session is not None:  # Test mode - use provided session (SAVEPOINT pattern)
        stmt = (
            update(ProcessingLog)
            .where(
                ProcessingLog.status == ProcessingStatus.PROCESSING,
                ProcessingLog.started_at < cutoff,
            )
            .values(
                status=ProcessingStatus.FAILED,
                message="Worker timeout - marked as failed by cleanup job",
                finished_at=datetime.now(UTC),
            )
        )
        result = await session.execute(stmt)
        count = result.rowcount if result.rowcount is not None else 0
    else:  # Production mode - create new session
        async with get_session() as db:
            async with db.begin():
                stmt = (
                    update(ProcessingLog)
                    .where(
                        ProcessingLog.status == ProcessingStatus.PROCESSING,
                        ProcessingLog.started_at < cutoff,
                    )
                    .values(
                        status=ProcessingStatus.FAILED,
                        message="Worker timeout - marked as failed by cleanup job",
                        finished_at=datetime.now(UTC),
                    )
                )
                result = await db.execute(stmt)
                count = result.rowcount if result.rowcount is not None else 0

    if count > 0:
        logger.info(
            "Marked %d stale PROCESSING entries as FAILED (timeout=%dm)",
            count,
            timeout_minutes,
        )
    return int(count)


async def mark_orphaned_uploaded_logs_failed(
    session: AsyncSession | None = None,
) -> int:
    """Mark UPLOADED logs older than 1 minute as FAILED.

    On startup, any log stuck in UPLOADED state means the worker
    crashed between enqueue and processing start. This function marks
    those orphaned entries as FAILED.

    Args:
        session: Optional database session for testing. If None, creates a new session
            with transaction. When provided, caller manages transaction (SAVEPOINT pattern).

    Returns:
        int: Number of entries that were marked as FAILED.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=1)

    if session is not None:
        # Test mode - use provided session (SAVEPOINT pattern)
        stmt = (
            update(ProcessingLog)
            .where(
                ProcessingLog.status == ProcessingStatus.UPLOADED,
                ProcessingLog.started_at < cutoff,
            )
            .values(
                status=ProcessingStatus.FAILED,
                message="Worker restart: orphaned UPLOADED entry detected",
                finished_at=datetime.now(UTC),
            )
        )
        result = await session.execute(stmt)
        count = result.rowcount if result.rowcount is not None else 0
    else:
        # Production mode - create new session with transaction
        async with get_session() as db:
            async with db.begin():
                stmt = (
                    update(ProcessingLog)
                    .where(
                        ProcessingLog.status == ProcessingStatus.UPLOADED,
                        ProcessingLog.started_at < cutoff,
                    )
                    .values(
                        status=ProcessingStatus.FAILED,
                        message="Worker restart: orphaned UPLOADED entry detected",
                        finished_at=datetime.now(UTC),
                    )
                )
                result = await db.execute(stmt)
                count = result.rowcount if result.rowcount is not None else 0

    if count > 0:
        logger.info(
            "Marked %d orphaned UPLOADED entries as FAILED (cutoff=1m)",
            count,
        )
    return int(count)


async def _process_csv_file_async(
    file_path_str: str,
    task_id: str,
    dashboard_id_str: str,
    processing_config_dict: dict[str, Any] | None = None,
    mode: str = "overwrite",
    db_session: AsyncSession | None = None,
) -> dict[str, Any]:
    """Async CSV processing implementation.

    Uses a single atomic transaction for all database operations. If any step
    fails (processing, storage, or status updates), the entire transaction rolls back.

    Args:
        file_path_str: Path to CSV file as string.
        task_id: Task ID (UUID string).
        dashboard_id_str: Dashboard ID as string.
        processing_config_dict: Processing configuration dictionary.
        mode: Upload mode (overwrite or append).
        db_session: Optional database session for testing. If None, creates a new session.

    Returns:
        dict: Processing result with status and data.
    """
    file_path = Path(file_path_str)
    dashboard_id = UUID(dashboard_id_str)

    # Helper to run processing with a managed session
    async def _run_with_transaction(
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Execute all processing and DB operations within a single transaction."""
        # Update status to processing (within transaction)
        await _update_processing_log_status(
            task_id=task_id,
            status=ProcessingStatus.PROCESSING,
            message="Processing started (background task)",
            started_at=datetime.now(UTC),
            session=session,
        )

        # Extract CSV parsing config from processing_config
        csv_parse_config: dict[str, Any] = {}
        column_types: dict[str, str] = {}
        settings: dict[str, Any] | None = None

        if processing_config_dict:
            settings = processing_config_dict.get("settings", processing_config_dict)
            if settings.get("separator"):
                csv_parse_config["separator"] = settings["separator"]
            if settings.get("encoding"):
                csv_parse_config["encoding"] = settings["encoding"]
            if settings.get("column_types"):
                column_types = settings["column_types"]

        # Load and process CSV (run in thread since Polars is sync)
        loader = CSVLoader()
        df = await asyncio.to_thread(
            loader.load_csv, file_path, csv_parse_config if csv_parse_config else None
        )
        logger.info("File loaded: %d rows, %d columns", df.shape[0], df.shape[1])

        # Validate loaded data using DataValidator
        loader_config = LoaderConfig(
            required_columns=settings.get("required_columns", []) if settings else [],
            column_types=column_types,
        )
        validator = DataValidator(config=loader_config)
        validation_result = validator.validate(df)
        if not validation_result.is_valid:
            error_msg = f"Data validation failed: {'; '.join(validation_result.errors)}"
            logger.error(error_msg)
            await _update_processing_log_status(
                task_id=task_id,
                status=ProcessingStatus.FAILED,
                message=error_msg,
                finished_at=datetime.now(UTC),
                session=session,
                error_code=ErrorCode.VALIDATION_ERROR.value,
            )
            raise ValueError(error_msg)

        # Apply decimal separator transformation for float columns with comma decimal
        if settings and settings.get("decimal_separator") == ",":
            for col_name, col_type in column_types.items():
                if col_type == "float" and col_name in df.columns:
                    # Only apply if column is still a string (not already parsed as float)
                    if df[col_name].dtype == pl.Utf8:
                        df = df.with_columns(
                            pl.col(col_name).str.replace(",", ".").cast(pl.Float64).alias(col_name)
                        )
                        logger.debug("Applied decimal separator transformation to column: %s", col_name)

        # Apply column type casting from processing config
        if column_types:
            date_format = settings.get("date_format") if settings else None
            for col_name, col_type in column_types.items():
                if col_name in df.columns and col_type != "float":
                    try:
                        if col_type == "date" and date_format:
                            # Parse date string with explicit format
                            df = df.with_columns(
                                pl.col(col_name).str.strptime(pl.Date, date_format).alias(col_name)
                            )
                            logger.debug("Cast column '%s' to Date with format '%s'", col_name, date_format)
                        elif col_type == "int":
                            df = df.with_columns(pl.col(col_name).cast(pl.Int64))
                        elif col_type == "str":
                            df = df.with_columns(pl.col(col_name).cast(pl.Utf8))
                        elif col_type == "bool":
                            df = df.with_columns(pl.col(col_name).cast(pl.Boolean))
                    except Exception as e:
                        logger.warning("Failed to cast column '%s' to %s: %s", col_name, col_type, e)

        # Apply column renames from processing config
        if settings and settings.get("renames"):
            rename_map = settings["renames"]
            logger.debug("Applying column renames: %s", rename_map)
            df = df.rename(rename_map)

        # Apply computed fields from processing config
        if settings and settings.get("computed_fields"):
            computed_fields = settings["computed_fields"]
            logger.debug("Applying computed fields: %s", computed_fields)
            df = await asyncio.to_thread(
                _add_computed_fields, df, computed_fields
            )

        # Apply processing config if provided
        if processing_config_dict:
            config = ProcessingConfig(**processing_config_dict)
            _validate_processing_config(config)

            # Apply transformations in thread
            df = await asyncio.to_thread(
                apply_transformations,
                df=df,
                filters=config.filters,
                groupby=config.groupby if not config.aggregations else None,
                sort_by=config.sort_by,
                descending=config.descending,
                limit=config.limit,
            )

            # Apply aggregations in thread
            if (
                config.aggregations
                or config.yoy_config
                or config.share_config
                or config.custom_metrics
            ):
                df = await asyncio.to_thread(
                    calculate_aggregations,
                    df=df,
                    groupby=config.groupby,
                    aggregations=config.aggregations,
                    yoy_config=config.yoy_config,
                    share_config=config.share_config,
                    custom_metrics=config.custom_metrics,
                )

        # Save aggregated data to database
        result_data = {
            "rows": df.shape[0],
            "columns": df.columns,
            "preview": df.head(10).to_dicts(),
        }

        # Store aggregates in database with mode (within same transaction)
        await _store_aggregates(
            df, dashboard_id, task_id, mode, db_session=session,
            processing_config_dict=processing_config_dict
        )

        # Clean up temp file
        if file_path.exists():
            await asyncio.to_thread(file_path.unlink)
            logger.info("Temp file deleted: %s", file_path)

        # Update status to completed (within same transaction)
        await _update_processing_log_status(
            task_id=task_id,
            status=ProcessingStatus.COMPLETED,
            message=f"Processing completed successfully: {result_data['rows']} rows processed",
            finished_at=datetime.now(UTC),
            session=session,
        )

        return {
            "success": True,
            "rows_processed": result_data["rows"],
            "message": "Processing completed",
        }

    # Execute with appropriate session management
    if db_session is not None:
        # Test mode - use provided session (caller manages transaction)
        try:
            return await _run_with_transaction(db_session)
        except Exception as e:
            error_msg = str(e)
            error_code = _map_processing_error_to_code(e)
            logger.exception("Processing failed: task_id=%s, error=%s, code=%s", task_id, error_msg, error_code)

            # Clean up temp file on error
            if file_path.exists():
                try:
                    await asyncio.to_thread(file_path.unlink)
                except Exception:
                    logger.warning(
                        "Failed to clean up temp file: %s",
                        file_path,
                        exc_info=True,
                    )

            # Update status to failed within the same transaction
            await _update_processing_log_status(
                task_id=task_id,
                status=ProcessingStatus.FAILED,
                message=f"Processing failed: {error_msg}",
                finished_at=datetime.now(UTC),
                session=db_session,
                error_code=error_code,
            )
            raise
    else:
        # Production mode - create new session with single transaction.
        # The failure-compensation handler wraps the whole session block so it also
        # covers failures raised before the transaction body runs (get_session() or
        # session.begin()), not just failures from _run_with_transaction.
        try:
            async with get_session() as session:
                async with session.begin():
                    return await _run_with_transaction(session)
        except Exception as e:
            error_msg = str(e)
            error_code = _map_processing_error_to_code(e)
            logger.exception("Processing failed: task_id=%s, error=%s, code=%s", task_id, error_msg, error_code)

            # Clean up temp file on error
            if file_path.exists():
                try:
                    await asyncio.to_thread(file_path.unlink)
                except Exception:
                    logger.warning(
                        "Failed to clean up temp file: %s",
                        file_path,
                        exc_info=True,
                    )

            # Report the failure on its own session, after the failed transaction has
            # exited and rolled back. Passing no session makes the helper open a fresh
            # session, so the FAILED row survives the rollback it is reporting. The
            # original exception keeps propagating below.
            try:
                await _update_processing_log_status(
                    task_id=task_id,
                    status=ProcessingStatus.FAILED,
                    message=f"Processing failed: {error_msg}",
                    finished_at=datetime.now(UTC),
                    error_code=error_code,
                )
            except Exception as status_err:
                logger.exception(
                    "Failed to update processing log status to FAILED: task_id=%s, error=%s",
                    task_id,
                    status_err,
                )

            raise


async def _store_aggregates(
    df: pl.DataFrame,
    dashboard_id: UUID,
    task_id: str,
    mode: str = "overwrite",
    db_session: AsyncSession | None = None,
    processing_config_dict: dict[str, Any] | None = None,
) -> None:
    """Store aggregated data to database.

    Args:
        df: Processed DataFrame.
        dashboard_id: Dashboard ID.
        task_id: Task ID for logging.
        mode: Upload mode - "overwrite" clears old data, "append" keeps it.
        db_session: Optional database session for testing. If None, creates a new session.
        processing_config_dict: Processing configuration for extracting metric_agg.
    """
    from mkobi.data.storage.manager import StorageManager
    from mkobi.models.enums import UploadMode
    from mkobi.models.graph import GraphRead
    from mkobi.models.filters import FilterRead
    from mkobi.services.aggregation_service import AggregationService
    from mkobi.db.repositories.dashboard_filter_values_repo import DashboardFilterValuesRepository

    # Helper to convert ORM Graph to GraphRead
    def _to_graph_read(g: Graph) -> GraphRead:
        return GraphRead(
            id=g.id,
            name=g.name,
            type=g.type,
            dashboard_id=g.dashboard_id,
            config=g.config or {},
            dimensions=g.dimensions or [],
            metrics=g.metrics or [],
            created_at=g.created_at,
        )

    # Helper to convert ORM Filter to FilterRead
    def _to_filter_read(f: Filter) -> FilterRead:
        return FilterRead(
            id=f.id,
            name=f.name,
            type=f.type,
            config=f.config or {},
            created_at=f.created_at,
        )

    if db_session is not None:
        # Test mode - use provided session without creating nested transaction.
        # Caller manages the transaction (SAVEPOINT pattern in async_db_session fixture).
        # StorageManager does not commit/rollback - transaction is managed externally.
        result = await db_session.execute(
            select(Graph).where(Graph.dashboard_id == dashboard_id)
        )
        graph_reads = [_to_graph_read(g) for g in result.scalars().all()]

        if not graph_reads:
            logger.warning("No graphs found for dashboard: %s", dashboard_id)
            return

        # Query dashboard filters via join table
        result = await db_session.execute(
            select(Filter).join(dashboard_filters).where(
                dashboard_filters.c.dashboard_id == dashboard_id
            )
        )
        filter_reads = [_to_filter_read(f) for f in result.scalars().all()]

        # Use AggregationService for per-chart GROUP BY aggregation
        agg_service = AggregationService()
        metric_agg = (processing_config_dict or {}).get("settings", {}).get("metric_agg", "sum")
        records = await agg_service.aggregate_for_dashboard(
            df, graph_reads, filter_reads, metric_agg=metric_agg
        )

        # Convert records to StorageManager format
        aggregates = [
            {"graph_id": r["graph_id"], "dims": r["dims"], "metrics": r["metrics"]}
            for r in records
        ]

        manager = StorageManager(db_session)
        clear_old = (mode == UploadMode.OVERWRITE)
        processed = await manager.save_aggregates(
            dashboard_id=dashboard_id,
            aggregates=aggregates,
            clear_old=clear_old,
        )

        logger.info(
            "Aggregates stored: dashboard_id=%s, records=%d, mode=%s, processed=%d",
            dashboard_id,
            len(records),
            mode,
            processed,
        )

        # Extract and save filter values from ALL accumulated data
        filter_names = [f.name for f in filter_reads]
        if filter_names:
            filter_values_repo = DashboardFilterValuesRepository()
            # Clear all existing filter values before saving new ones (idempotent rebuild)
            await filter_values_repo.clear_dashboard_values(dashboard_id, db_session)

            # In APPEND mode, extract from all accumulated data in the database
            # (save_aggregates already upserted the new data)
            # In OVERWRITE mode, existing data was already cleared
            if mode == UploadMode.APPEND:
                combined_records = await manager.get_aggregates(dashboard_id)
            else:
                combined_records = records

            filter_values = await agg_service.extract_filter_values(combined_records, filter_names)
            for fname, fvalues in filter_values.items():
                if fvalues:
                    # Persist filter labels as text; the filter value column is
                    # String-backed, so str() here keeps that contract honest.
                    str_values = [str(value) for value in fvalues]
                    await filter_values_repo.save_filter_values(
                        dashboard_id, fname, str_values, db_session
                    )
                    logger.info(
                        "Filter values saved: dashboard_id=%s, filter_name=%s, count=%d",
                        dashboard_id,
                        fname,
                        len(fvalues),
                    )
    else:
        # Production mode - create new session
        async with get_session() as session:
            async with session.begin():
                # Query graphs for the dashboard
                result = await session.execute(
                    select(Graph).where(Graph.dashboard_id == dashboard_id)
                )
                graph_reads = [_to_graph_read(g) for g in result.scalars().all()]

                if not graph_reads:
                    logger.warning("No graphs found for dashboard: %s", dashboard_id)
                    return

                # Query dashboard filters via join table
                result = await session.execute(
                    select(Filter).join(dashboard_filters).where(
                        dashboard_filters.c.dashboard_id == dashboard_id
                    )
                )
                filter_reads = [_to_filter_read(f) for f in result.scalars().all()]

                # Use AggregationService for per-chart GROUP BY aggregation
                agg_service = AggregationService()
                metric_agg = (processing_config_dict or {}).get("settings", {}).get("metric_agg", "sum")
                records = await agg_service.aggregate_for_dashboard(
                    df, graph_reads, filter_reads, metric_agg=metric_agg
                )

                # Convert records to StorageManager format
                aggregates = [
                    {"graph_id": r["graph_id"], "dims": r["dims"], "metrics": r["metrics"]}
                    for r in records
                ]

                manager = StorageManager(session)
                clear_old = (mode == UploadMode.OVERWRITE)
                processed = await manager.save_aggregates(
                    dashboard_id=dashboard_id,
                    aggregates=aggregates,
                    clear_old=clear_old,
                )

                logger.info(
                    "Aggregates stored: dashboard_id=%s, records=%d, mode=%s, processed=%d",
                    dashboard_id,
                    len(records),
                    mode,
                    processed,
                )

                # Extract and save filter values from ALL accumulated data
                filter_names = [f.name for f in filter_reads]
                if filter_names:
                    filter_values_repo = DashboardFilterValuesRepository()
                    # Clear all existing filter values before saving new ones (idempotent rebuild)
                    await filter_values_repo.clear_dashboard_values(dashboard_id, session)

                    # In APPEND mode, extract from all accumulated data in the database
                    # (save_aggregates already upserted the new data)
                    # In OVERWRITE mode, existing data was already cleared
                    if mode == UploadMode.APPEND:
                        combined_records = await manager.get_aggregates(dashboard_id)
                    else:
                        combined_records = records

                    filter_values = await agg_service.extract_filter_values(combined_records, filter_names)
                    for fname, fvalues in filter_values.items():
                        if fvalues:
                            # Persist filter labels as text; the filter value
                            # column is String-backed, so str() here keeps that
                            # contract honest.
                            str_values = [str(value) for value in fvalues]
                            await filter_values_repo.save_filter_values(
                                dashboard_id, fname, str_values, session
                            )
                            logger.info(
                                "Filter values saved: dashboard_id=%s, filter_name=%s, count=%d",
                                dashboard_id,
                                fname,
                                len(fvalues),
                            )


async def process_csv_background(
    file_path_str: str,
    task_id: str,
    dashboard_id_str: str,
    processing_config_dict: dict[str, Any] | None = None,
    mode: str = "overwrite",
    db_session: AsyncSession | None = None,
) -> dict[str, Any]:
    """Background task entry point for CSV processing.

    This function is the async implementation of the CSV processing job. The
    RQ worker invokes it through the synchronous ``process_csv_background_sync``
    wrapper.

    Args:
        file_path_str: Path to CSV file as string.
        task_id: Task ID (UUID string).
        dashboard_id_str: Dashboard ID as string.
        processing_config_dict: Processing configuration dictionary.
        mode: Upload mode (overwrite or append).
        db_session: Optional database session for testing. If None, creates a new session.

    Returns:
        dict: Processing result.
    """
    logger.info(
        "Starting background processing: task_id=%s, dashboard_id=%s, mode=%s",
        task_id,
        dashboard_id_str,
        mode,
    )

    # Use the internal implementation with optional session
    result = await _process_csv_file_async(
        file_path_str=file_path_str,
        task_id=task_id,
        dashboard_id_str=dashboard_id_str,
        processing_config_dict=processing_config_dict,
        mode=mode,
        db_session=db_session,
    )
    return result


def process_csv_background_sync(
    file_path_str: str,
    task_id: str,
    dashboard_id_str: str,
    processing_config_dict: dict[str, Any] | None = None,
    mode: str = "overwrite",
) -> dict[str, Any]:
    """RQ worker entry point (sync wrapper).

    This function is called by RQ worker in a separate process.
    Runs the async implementation using asyncio.run().

    The module-global async engine is disposed in a finally block so a failed
    job still releases its connection pool. rq's default Worker forks a work
    horse per job, and a pool created in the parent would otherwise survive
    across os.fork and be shared unsafely between parent and child.

    Args:
        file_path_str: Path to CSV file as string.
        task_id: Task ID (UUID string).
        dashboard_id_str: Dashboard ID as string.
        processing_config_dict: Processing configuration dictionary.
        mode: Upload mode (overwrite or append).

    Returns:
        dict: Processing result.
    """
    from mkobi.db.session import dispose_engine

    async def _run_and_dispose() -> dict[str, Any]:
        """Run the job on one loop, then dispose the engine on that same loop."""
        try:
            return await process_csv_background(
                file_path_str=file_path_str,
                task_id=task_id,
                dashboard_id_str=dashboard_id_str,
                processing_config_dict=processing_config_dict,
                mode=mode,
            )
        finally:
            # dispose_engine is async, so drive it from this sync wrapper. Running
            # it in the same loop that ran the job (not in a second asyncio.run
            # after the first loop closed) keeps the pooled connection bound to
            # the loop that created it, so the release is clean on success and on
            # failure alike.
            await dispose_engine()

    return asyncio.run(_run_and_dispose())


async def start_stale_processing_cleanup_task(
    interval_seconds: int = 300,  # Run every 5 minutes by default
    timeout_minutes: int = DEFAULT_STALE_PROCESSING_TIMEOUT_MINUTES,
) -> None:
    """Start background task for cleaning up stale processing logs.

    This function runs indefinitely, periodically checking for and marking
    stale PROCESSING entries as FAILED.

    Args:
        interval_seconds: Interval between cleanup runs in seconds.
        timeout_minutes: Timeout threshold for considering entries stale.
    """
    logger.info(
        "Starting stale processing cleanup task (interval=%ds, timeout=%dm)",
        interval_seconds,
        timeout_minutes,
    )
    while True:
        try:
            await cleanup_stale_processing_logs(timeout_minutes=timeout_minutes)
        except Exception as e:
            logger.exception("Error during stale processing cleanup: %s", e)
        await asyncio.sleep(interval_seconds)
