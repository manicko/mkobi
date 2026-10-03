"""Temporary file cleanup utilities.

Provides functions for cleaning up stale temporary files from the upload
directory.
"""

from dataclasses import dataclass
from pathlib import Path

from mkobi.config import get_config
from mkobi.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CleanupResult:
    """Outcome of one stale-file sweep, with the three counts kept distinct.

    A bare ``int`` could not express *why* a candidate left the directory, so a
    benign race with another reclaimer (``FileNotFoundError``) and a genuine
    removal failure (any other ``OSError``, e.g. ``EACCES``) were both collapsed
    into one count and one ERROR log line. This type keeps them separate:

    Attributes:
        deleted: Candidates this process actually removed. ``deleted`` counts
            only files this sweep won; when several sweepers race over the same
            directory the sum of their ``deleted`` values is the number of files
            removed exactly once -- no file is ever counted by two sweepers.
        already_gone: Candidates that had disappeared before this sweep reached
            them, i.e. ``FileNotFoundError`` at ``stat``/``unlink``. This is the
            ordinary outcome of two reclaimers racing, never a failure.
        failed: Candidates whose removal raised an ``OSError`` other than
            ``FileNotFoundError``. A non-zero value is a real removal failure
            and is logged at ERROR with a traceback.

    The total across concurrent sweepers is a contract:
    ``sum(deleted) == number of files physically removed`` and
    ``sum(deleted + already_gone) == number of eligible candidates seen``.
    """

    deleted: int = 0
    already_gone: int = 0
    failed: int = 0


def cleanup_stale_temp_files(max_age_hours: int | None = None) -> CleanupResult:
    """Delete stale temporary files older than the specified threshold.

    This runs on the lease-guarded periodic reconciler loop (see
    ``workers/data_worker.start_stale_processing_cleanup_task``); it is no longer
    boot-only, so a removal that fails is retried on a later tick. It is
    idempotent and safe to run concurrently on several replicas: when two
    sweepers race over one file, exactly one removes it and the other records it
    in ``already_gone`` -- a lost race is not an error.

    Args:
        max_age_hours: Maximum age of files in hours before deletion.
            If None, uses the configured threshold (default 24 hours).
            If 0, deletes all files regardless of age (immediate cleanup).
            Negative values are invalid and return an all-zero result.

    Returns:
        CleanupResult: Counts of files deleted, already gone (lost a race), and
            failed (a real removal error).
    """
    from time import time

    config = get_config()
    threshold_hours = (
        max_age_hours if max_age_hours is not None else config.stale_file_threshold_hours
    )
    upload_dir = Path(config.upload_temp_dir)

    if threshold_hours < 0:
        logger.warning("Invalid threshold %d hours, skipping cleanup", threshold_hours)
        return CleanupResult()

    if not upload_dir.exists():
        logger.info("Upload temp directory does not exist: %s", upload_dir)
        return CleanupResult()

    # Calculate cutoff time (seconds since epoch)
    # threshold_hours=0 means delete all files immediately (used for test cleanup)
    cutoff_seconds = 0 if threshold_hours == 0 else threshold_hours * 3600
    current_time = time()
    deleted_count = 0
    already_gone_count = 0
    failed_count = 0

    # Find all CSV files in upload directory
    csv_files = list(upload_dir.glob("*.csv*"))

    for file_path in csv_files:
        try:
            # Check file modification time
            mtime = file_path.stat().st_mtime
            file_age_seconds = current_time - mtime

            if file_age_seconds > cutoff_seconds:
                file_path.unlink()
                logger.info(
                    "Deleted stale temp file: %s (age: %.1f hours)",
                    file_path,
                    file_age_seconds / 3600,
                )
                deleted_count += 1
        except FileNotFoundError:
            # The file vanished between the glob and here: another reclaimer won
            # the race. This is the ordinary concurrent-sweep outcome, not an
            # error, so it is recorded separately and logged at DEBUG.
            already_gone_count += 1
            logger.debug(
                "Stale temp file already removed by another sweeper: %s", file_path
            )
        except OSError as e:
            # Any other OS-level failure (e.g. EACCES) is a real removal error.
            # It is deliberately NOT folded into ``already_gone``: silencing a
            # genuine failure as "someone else got it" is the opposite of the
            # point of this classification.
            failed_count += 1
            logger.error("Error removing stale temp file %s: %s", file_path, e, exc_info=True)

    if deleted_count > 0:
        logger.info("Cleaned up %d stale temp files", deleted_count)
    if failed_count > 0:
        logger.error(
            "Stale temp file sweep finished with %d failure(s)", failed_count
        )

    return CleanupResult(
        deleted=deleted_count,
        already_gone=already_gone_count,
        failed=failed_count,
    )

