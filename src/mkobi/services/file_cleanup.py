"""Temporary file cleanup utilities.

Provides functions for cleaning up stale temporary files from the upload
directory.
"""

from pathlib import Path

from mkobi.config import get_config
from mkobi.core.logging_config import get_logger

logger = get_logger(__name__)


def cleanup_stale_temp_files(max_age_hours: int | None = None) -> int:
    """Delete stale temporary files older than the specified threshold.

    This function is designed to be called on application startup to clean up
    orphaned temp files from previous runs (e.g., worker crashes, container restarts).

    Args:
        max_age_hours: Maximum age of files in hours before deletion.
            If None, uses the configured threshold (default 24 hours).
            If 0, deletes all files regardless of age (immediate cleanup).
            Negative values are invalid and return 0 without deletion.

    Returns:
        int: Number of files deleted.
    """
    from time import time

    config = get_config()
    threshold_hours = (
        max_age_hours if max_age_hours is not None else config.stale_file_threshold_hours
    )
    upload_dir = Path(config.upload_temp_dir)

    if threshold_hours < 0:
        logger.warning("Invalid threshold %d hours, skipping cleanup", threshold_hours)
        return 0

    if not upload_dir.exists():
        logger.info("Upload temp directory does not exist: %s", upload_dir)
        return 0

    # Calculate cutoff time (seconds since epoch)
    # threshold_hours=0 means delete all files immediately (used for test cleanup)
    cutoff_seconds = 0 if threshold_hours == 0 else threshold_hours * 3600
    current_time = time()
    deleted_count = 0

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
        except Exception as e:
            logger.error("Error processing file %s: %s", file_path, e)

    if deleted_count > 0:
        logger.info("Cleaned up %d stale temp files", deleted_count)

    return deleted_count

