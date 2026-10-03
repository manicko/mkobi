"""CSV data loader.

This module provides a class for loading and reading CSV files,
including support for compressed .csv.gz files.
"""

import asyncio
import gzip
import logging
import zlib
from pathlib import Path
from typing import Any

import polars as pl
from polars.exceptions import PanicException as _PolarsPanicException

from mkobi.config import get_config
from mkobi.models.data import LoaderConfig
from mkobi.models.enums import ErrorCode, FileExtensionEnum
from mkobi.utils.exceptions import AppException

logger = logging.getLogger(__name__)

# Chunk size for the bounded decompressed-size measurement. The gzip member is
# read through gzip.open in chunks of this size, so peak memory is one chunk
# rather than the whole decompressed stream.
_SIZE_PROBE_CHUNK_BYTES = 1 << 20

# Polars is a Rust extension (pyo3) and raises ``polars.exceptions.PanicException``
# (runtime class ``pyo3_runtime.PanicException``) from inside a read. Its MRO is
# ``PanicException -> BaseException -> object``, so ``isinstance(e, Exception)``
# is False and no ``except Exception`` can see it. The reader boundary below
# converts exactly this class into the module's own ``AppException``; the handler
# must stay narrow enough not to swallow a genuine I/O fault.
#
# A mislabelled artefact (non-gzip bytes under a ``.csv.gz`` name) is now caught
# earlier, by ``_validate_file_size`` reading the gzip stream in pure Python
# (PB-12): that raises one of the ordinary ``_MALFORMED_ARCHIVE_ERRORS`` below
# before any Polars read runs. The boundary converts those too, so the
# mislabelled case escapes as a typed error rather than an untyped ``OSError``.
_MALFORMED_ARCHIVE_ERRORS: tuple[type[Exception], ...] = (
    gzip.BadGzipFile,
    EOFError,
    zlib.error,
)


async def load_csv(filepath: Path, config: dict[str, Any] | None = None) -> pl.DataFrame:
    """Load CSV file asynchronously.

    Wrapper around synchronous CSVLoader for use in async code.
    Supports .csv and .csv.gz files with UTF-8 encoding.

    Args:
        filepath: Path to CSV file.
        config: Optional configuration for reading (separator, has_header, etc.).

    Returns:
        pl.DataFrame: Loaded data.

    Raises:
        FileNotFoundError: If file does not exist.
        ValueError: If file cannot be read.
    """
    loader = CSVLoader(config=LoaderConfig(**config) if config else None)
    return await asyncio.to_thread(loader.load_csv, filepath, config)


def detect_file_type(filename: str) -> FileExtensionEnum:
    """Detect file type from filename extension.

    Filename-only extension utility; it is **not** used to name the stored
    artefact. The stored artefact's extension is content-derived (D-06-P = (a)),
    so this helper no longer decides the stored name. It is retained as a tested
    public utility over filename semantics.

    Args:
        filename: Name of the file.

    Returns:
        File extension type as FileExtensionEnum.

    Raises:
        ValueError: If file type is not supported.
    """
    filename_lower = filename.lower()

    if filename_lower.endswith(".csv.gz"):
        logger.debug("Detected file type: %s for file: %s", FileExtensionEnum.CSV_GZ, filename)
        return FileExtensionEnum.CSV_GZ
    elif filename_lower.endswith(".csv"):
        logger.debug("Detected file type: %s for file: %s", FileExtensionEnum.CSV, filename)
        return FileExtensionEnum.CSV
    else:
        error_msg = f"Unsupported file type: {filename}"
        logger.error(error_msg)
        raise ValueError(error_msg)


class CSVLoader:
    """CSV file loader.

    Responsible for reading CSV files (including compressed .csv.gz),
    validating data structure and transforming types.
    ``lazy_threshold_mb`` chooses how the frame is built (Polars'
    lazy query engine versus ``read_csv``), not whether the result is
    materialised -- every path returns a ``pl.DataFrame``.

    Attributes:
        config: Loader configuration.
    """

    def __init__(self, config: LoaderConfig | None = None) -> None:
        """Initialize loader.

        Args:
            config: Optional loader configuration.
        """
        self.config = config or LoaderConfig()
        logger.debug("CSVLoader initialized with config=%s", self.config)

    def load_csv(
        self,
        file_path: Path,
        config: dict[str, Any] | None = None,
        lazy_threshold_mb: float | None = None,
    ) -> pl.DataFrame:
        """Load CSV file, choosing how the frame is built by size.

        Reads CSV file (supports .csv and .csv.gz).
        Files larger than ``lazy_threshold_mb`` are built through Polars'
        lazy query engine and then materialised; smaller files are read with
        ``read_csv``. Both paths return a ``pl.DataFrame`` -- the threshold
        selects the builder, not whether the frame is materialised.
        Performs file size validation (the ceiling applies to the
        decompressed stream for .csv.gz).

        Args:
            file_path: Path to CSV file.
            config: Optional configuration for reading CSV (separator, has_header, encoding, etc.).
            lazy_threshold_mb: Threshold in MB above which the frame is built
                through Polars' lazy query engine.
                If None, uses application configuration.

        Returns:
            pl.DataFrame: Loaded data.

        Raises:
            FileNotFoundError: If file does not exist.
            AppException: If the file (decompressed, for .csv.gz) is too large,
                or if a mislabelled file makes the reader panic.
            ValueError: If the file cannot be read.
        """
        logger.info("Loading CSV file: %s", file_path)

        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            raise FileNotFoundError(f"File not found: {file_path}")

        # Determine threshold for lazy loading
        if lazy_threshold_mb is None:
            app_config = get_config()
            lazy_threshold_mb = app_config.lazy_threshold_mb

        # Read file. The size validation is inside the boundary: for a
        # ``.csv.gz`` it reads the gzip stream in pure Python and a mislabelled
        # artefact fails there, so the conversion below must cover it.
        try:
            # Validate file size
            self._validate_file_size(file_path)

            file_size_mb = self._get_file_size_mb(file_path)

            if file_size_mb > lazy_threshold_mb:
                logger.info(
                    "Building frame via the lazy query engine for file %.2f MB (threshold: %.2f MB)",
                    file_size_mb,
                    lazy_threshold_mb,
                )
                df = self._read_csv_via_scan(file_path, config)
            else:
                logger.info(
                    "Building frame via read_csv for file %.2f MB (threshold: %.2f MB)",
                    file_size_mb,
                    lazy_threshold_mb,
                )
                df = self._read_csv(file_path, config)

            logger.info(
                "File read: %d rows, %d columns",
                df.shape[0],
                df.shape[1],
            )

            # Apply type transformations
            if self.config.column_types:
                df = self._apply_type_transformations(df)

            # Check required columns
            if self.config.required_columns:
                self._validate_required_columns(df)

            return df

        except (AppException, FileNotFoundError):
            # The byte ceiling (FILE_TOO_LARGE) and the existence contract keep
            # their own meaning; the boundary must not relabel them "bad file".
            raise
        except _PolarsPanicException as e:
            # A mislabelled file (non-gzip bytes under a .gz name) makes the
            # gzip reader in _read_csv raise a pyo3 panic. It is not an
            # ``Exception``, so it would otherwise escape every handler in the
            # loader and the worker. Convert it to the module's own declared
            # error type. The handler is narrow: only this class is caught.
            logger.error(
                "Reader panicked on %s, treating as an invalid file: %s", file_path, e
            )
            raise AppException(
                code=ErrorCode.INVALID_FILE_TYPE,
                detail=f"Failed to load file {file_path}: {e}",
            ) from e
        except _MALFORMED_ARCHIVE_ERRORS as e:
            # The mislabelled artefact path: the gzip stream probe in
            # ``_validate_file_size`` raises one of these ordinary exceptions
            # (non-gzip bytes, a truncated archive, a corrupt deflate stream)
            # before any reader runs. It is a bad file, not an I/O fault, so it
            # is converted to the declared error type. Other OSErrors (a
            # permission fault, a genuine read failure) fall through to the
            # generic branch and are not relabelled "bad file".
            logger.error(
                "Malformed archive at %s, treating as an invalid file: %s", file_path, e
            )
            raise AppException(
                code=ErrorCode.INVALID_FILE_TYPE,
                detail=f"Failed to load file {file_path}: {e}",
            ) from e
        except Exception as e:
            logger.error("Error loading file %s: %s", file_path, e)
            raise ValueError(f"Failed to load file {file_path}: {e}") from e

    def load(self, file_path: Path) -> pl.DataFrame:
        """Load CSV file and return DataFrame.

        Reads CSV file (supports .csv.gz), applies
        data type transformations according to configuration.

        Args:
            file_path: Path to CSV file.

        Returns:
            pl.DataFrame: Loaded data.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If file cannot be read.
        """
        return self.load_csv(file_path)

    def _read_csv_via_scan(self, file_path: Path, config: dict[str, Any] | None = None) -> pl.DataFrame:
        """Read CSV by scanning through Polars' lazy query engine, then collect.

        The name states what the branch does. It is **not** lazy in its result:
        ``pl.scan_csv(...).collect()`` returns a materialised ``pl.DataFrame``,
        exactly like ``_read_csv``. The branch is selected only by
        ``lazy_threshold_mb``; for a plain ``.csv`` the ``st_size`` that selects
        it is the decompressed size, so that path is already correct.

        Args:
            file_path: Path to CSV file.
            config: Optional configuration for reading CSV.

        Returns:
            pl.DataFrame: Read data.
        """
        try:
            read_kwargs = {}
            if config:
                if "separator" in config:
                    read_kwargs["separator"] = config["separator"]
                if "has_header" in config:
                    read_kwargs["has_header"] = config["has_header"]
                if "encoding" in config:
                    # Polars scan_csv only supports 'utf8' or 'utf8-lossy', not 'utf-8-sig'
                    # Convert utf-8-sig to utf8 (BOM will be handled by has_header=True)
                    encoding = config["encoding"]
                    if encoding == "utf-8-sig":
                        encoding = "utf8"
                    read_kwargs["encoding"] = encoding

            if self._is_gzip_file(file_path):
                logger.debug("Reading gzipped CSV file (scan): %s", file_path)
            else:
                logger.debug("Reading normal CSV file (scan): %s", file_path)
            return pl.scan_csv(file_path, **read_kwargs).collect()
        except Exception as e:
            logger.error("Error reading CSV file (scan) %s: %s", file_path, e)
            raise

    def _get_file_size_mb(self, file_path: Path) -> float:
        """Get file size in megabytes.

        Args:
            file_path: Path to file.

        Returns:
            float: File size in MB.

        Raises:
            FileNotFoundError: If file not found.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        return file_path.stat().st_size / (1024 * 1024)

    @staticmethod
    def _is_gzip_file(file_path: Path) -> bool:
        """Return True when the path names a gzip-compressed CSV.

        The single predicate for "this file is read through gzip.open". It must
        agree with the test ``_read_csv`` uses to open the file, or a ``.csv.gz``
        could be measured by ``stat`` (its compressed size) while being read
        decompressed.
        """
        return file_path.suffix == ".gz" or file_path.name.endswith(".csv.gz")

    def _raise_file_too_large(
        self,
        file_path: Path,
        observed_bytes: int,
        max_size_bytes: int,
        *,
        decompressed: bool = False,
    ) -> None:
        """Raise the classified FILE_TOO_LARGE error for an oversized file.

        The message keeps the established "File too large" prefix so the
        substring fallback in ``_map_processing_error_to_code`` still classifies
        it, while the ``AppException``'s code makes the code-first branch of that
        classifier the one that actually applies.

        Args:
            file_path: Path to the offending file.
            observed_bytes: The size that tripped the ceiling, in bytes.
            max_size_bytes: The configured ceiling, in bytes.
            decompressed: Whether the observed size is the decompressed stream.

        Raises:
            AppException: Always, with ``ErrorCode.FILE_TOO_LARGE``.
        """
        logger.error(
            "File exceeds maximum size: %s (%d > %d bytes, decompressed=%s)",
            file_path,
            observed_bytes,
            max_size_bytes,
            decompressed,
        )
        if decompressed:
            detail = (
                f"File too large: decompressed size exceeds {max_size_bytes} bytes "
                f"(compressed: {file_path.stat().st_size} bytes)"
            )
        else:
            detail = (
                f"File too large: {file_path.stat().st_size} bytes "
                f"(max: {max_size_bytes} bytes)"
            )
        raise AppException(code=ErrorCode.FILE_TOO_LARGE, detail=detail)

    def _measure_decompressed_size(self, file_path: Path, max_size_bytes: int) -> int:
        """Measure the decompressed gzip stream, failing closed at the ceiling.

        Reads the gzip member through ``gzip.open`` in
        ``_SIZE_PROBE_CHUNK_BYTES`` chunks and aborts the moment the running
        total passes ``max_size_bytes``, so peak memory is one chunk and the
        cost is bounded by the budget. Acceptance requires reading the stream to
        EOF within budget, which keeps it fail-closed for a multi-member archive
        whose trailer understates the expansion: every member is read, not just
        the first.

        Because the stream is read here in pure Python, a malformed archive
        raises an ordinary ``Exception`` subclass before the size decision
        (``zlib.error`` for a corrupt payload, ``EOFError`` for a truncated
        archive, ``gzip.BadGzipFile`` for non-gzip bytes). Raising inside the
        Polars read instead would surface as a ``BaseException`` panic and escape
        every ``except Exception`` in the loader and the worker.

        Args:
            file_path: Path to the gzip file.
            max_size_bytes: The configured ceiling, in bytes.

        Returns:
            int: The decompressed size in bytes.

        Raises:
            AppException: If the decompressed stream exceeds the ceiling.
        """
        total = 0
        with gzip.open(file_path, "rb") as stream:
            while True:
                chunk = stream.read(_SIZE_PROBE_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size_bytes:
                    self._raise_file_too_large(
                        file_path, total, max_size_bytes, decompressed=True
                    )
        return total

    def _validate_file_size(self, file_path: Path, max_size_mb: float | None = None) -> float:
        """Validate file size against the configured ceiling.

        For a plain ``.csv`` the ceiling is compared against ``st_size``, which
        *is* the decompressed size, so that path is correct as it stands. For a
        ``.csv.gz`` the ceiling applies to the **decompressed** stream: the
        gzip member is read through ``gzip.open`` in bounded chunks and the
        running total is aborted the moment it passes the budget. Measuring
        ``st_size`` there would let a small gzip of a multi-gigabyte CSV pass the
        check and then be fully expanded by the reader.

        Args:
            file_path: Path to file.
            max_size_mb: Maximum size in MB.
                If None, uses loader configuration.

        Returns:
            float: File size in MB (decompressed for a gzip file).

        Raises:
            AppException: If the file is too large, with
                ``ErrorCode.FILE_TOO_LARGE``.
            FileNotFoundError: If file not found.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        max_size_bytes = (
            int(max_size_mb * 1024 * 1024)
            if max_size_mb is not None
            else self.config.max_file_size
        )

        if self._is_gzip_file(file_path):
            decompressed_bytes = self._measure_decompressed_size(
                file_path, max_size_bytes
            )
            file_size_mb = decompressed_bytes / (1024 * 1024)
            logger.info("File size %s: %.2f MB (decompressed)", file_path, file_size_mb)
            return file_size_mb

        file_size_mb = self._get_file_size_mb(file_path)
        if file_size_mb > max_size_bytes / (1024 * 1024):
            self._raise_file_too_large(
                file_path, file_path.stat().st_size, max_size_bytes
            )

        logger.info("File size %s: %.2f MB", file_path, file_size_mb)
        return file_size_mb

    def _read_csv(self, file_path: Path, config: dict[str, Any] | None = None) -> pl.DataFrame:
        """Read CSV file (supports gzip compression).

        Args:
            file_path: Path to CSV file.
            config: Optional configuration for reading CSV.

        Returns:
            pl.DataFrame: Read data.
        """
        try:
            read_kwargs = {}
            if config:
                if "separator" in config:
                    read_kwargs["separator"] = config["separator"]
                if "has_header" in config:
                    read_kwargs["has_header"] = config["has_header"]
            if config and "encoding" in config:
                # Polars read_csv only supports 'utf8' or 'utf8-lossy', not 'utf-8-sig'
                encoding = config["encoding"]
                if encoding == "utf-8-sig":
                    encoding = "utf8"
                read_kwargs["encoding"] = encoding

            if self._is_gzip_file(file_path):
                logger.debug("Reading gzipped CSV file: %s", file_path)
                with gzip.open(file_path, "rb") as f:
                    return pl.read_csv(f, **read_kwargs)
            else:
                logger.debug("Reading normal CSV file: %s", file_path)
                return pl.read_csv(file_path, **read_kwargs)
        except Exception as e:
            logger.error("Error reading CSV file %s: %s", file_path, e)
            raise

    def _apply_type_transformations(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply column type transformations.

        Args:
            df: Source DataFrame.

        Returns:
            pl.DataFrame: DataFrame with transformed types.
        """
        logger.debug("Applying type transformations")

        for column_name, target_type in self.config.column_types.items():
            if column_name in df.columns:
                try:
                    if target_type == "int":
                        df = df.with_columns(pl.col(column_name).cast(pl.Int64))
                    elif target_type == "float":
                        df = df.with_columns(pl.col(column_name).cast(pl.Float64))
                    elif target_type == "str":
                        df = df.with_columns(pl.col(column_name).cast(pl.Utf8))
                    elif target_type == "date":
                        df = df.with_columns(pl.col(column_name).cast(pl.Date))
                    elif target_type == "datetime":
                        df = df.with_columns(pl.col(column_name).cast(pl.Datetime))
                    elif target_type == "bool":
                        df = df.with_columns(pl.col(column_name).cast(pl.Boolean))
                    else:
                        logger.warning(
                            "Unknown data type '%s' for column '%s'",
                            target_type,
                            column_name,
                        )
                        continue

                    logger.debug(
                        "Column '%s' transformed to type '%s'",
                        column_name,
                        target_type,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to transform column '%s' to type '%s': %s",
                        column_name,
                        target_type,
                        e,
                    )
            else:
                logger.warning(
                    "Column '%s' not found in data, skipping transformation",
                    column_name,
                )

        return df

    def _validate_required_columns(self, df: pl.DataFrame) -> None:
        """Validate presence of required columns.

        Args:
            df: DataFrame to check.

        Raises:
            ValueError: If required columns are missing.
        """
        missing_columns = [
            col for col in self.config.required_columns if col not in df.columns
        ]

        if missing_columns:
            error_msg = (
                f"Missing required columns: {', '.join(missing_columns)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.debug("All required columns present")

    def get_summary(self, df: pl.DataFrame) -> dict[str, Any]:
        """Return summary information about DataFrame.

        Args:
            df: DataFrame to analyze.

        Returns:
            dict: Summary information about data.
        """
        return {
            "rows": df.shape[0],
            "columns": df.shape[1],
            "column_names": df.columns,
            "column_types": {col: str(df[col].dtype) for col in df.columns},
            "memory_usage": df.estimated_size(),
        }

    def filter_data(
        self,
        df: pl.DataFrame,
        conditions: list[dict[str, Any]],
    ) -> pl.DataFrame:
        """Apply filters to data.

        Args:
            df: Source DataFrame.
            conditions: List of filter conditions.
                Each condition is a dict with keys:
                - column: column name
                - operator: operator (==, !=, >, <, >=, <=)
                - value: value for comparison

        Returns:
            pl.DataFrame: Filtered data.
        """
        logger.debug("Applying filters: %s", conditions)

        result = df
        for condition in conditions:
            column = condition["column"]
            operator = condition["operator"]
            value = condition["value"]

            if operator == "==":
                result = result.filter(pl.col(column) == value)
            elif operator == "!=":
                result = result.filter(pl.col(column) != value)
            elif operator == ">":
                result = result.filter(pl.col(column) > value)
            elif operator == "<":
                result = result.filter(pl.col(column) < value)
            elif operator == ">=":
                result = result.filter(pl.col(column) >= value)
            elif operator == "<=":
                result = result.filter(pl.col(column) <= value)
            else:
                logger.warning("Unknown filter operator: %s", operator)
                continue

            logger.debug("Applied filter: %s %s %s", column, operator, value)

        return result

    def aggregate(
        self,
        df: pl.DataFrame,
        groupby: list[str],
        aggregations: list[dict[str, Any]],
    ) -> pl.DataFrame:
        """Perform grouping and data aggregation.

        Args:
            df: Source DataFrame.
            groupby: List of columns to group by.
            aggregations: List of aggregations.
                Each aggregation is a dict with keys:
                - column: column name
                - function: aggregation function (sum, mean, count, min, max)
                - alias: optional result column name

        Returns:
            pl.DataFrame: Aggregated data.
        """
        logger.debug(
            "Aggregation: group by %s, aggregations %s",
            groupby,
            aggregations,
        )

        agg_exprs = []
        for agg in aggregations:
            column = agg["column"]
            function = agg["function"]
            alias = agg.get("alias", f"{column}_{function}")

            if function == "sum":
                expr = pl.col(column).sum().alias(alias)
            elif function == "mean":
                expr = pl.col(column).mean().alias(alias)
            elif function == "count":
                expr = pl.col(column).count().alias(alias)
            elif function == "min":
                expr = pl.col(column).min().alias(alias)
            elif function == "max":
                expr = pl.col(column).max().alias(alias)
            else:
                logger.warning("Unknown aggregation function: %s", function)
                continue

            agg_exprs.append(expr)

        result = df.group_by(groupby).agg(agg_exprs)
        logger.info(
            "Aggregation completed: %d groups, %d columns",
            result.shape[0],
            result.shape[1],
        )

        return result
