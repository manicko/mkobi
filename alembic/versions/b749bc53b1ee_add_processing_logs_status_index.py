"""Add index on processing_logs (status, finished_at) for cleanup queries.

Revision ID: b749bc53b1ee
Revises: 4479eb53fd4e
Create Date: 2026-06-10 12:00:00.000000

The file name above says only ``status``, but this revision creates
``idx_processing_logs_status_finished_at`` on ``(status, finished_at)`` - a
composite index, which is what the cleanup query needs. The file name is
deliberately left unchanged even though it understates the column set: a
revision's file name is frozen once deployed, because renaming the file (or the
revision identifier) breaks the ``alembic_version`` tables that already record
the identifier. The revision body, not the file name, is the source of truth.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b749bc53b1ee"
down_revision: str | Sequence[str] | None = "4479eb53fd4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add composite index on processing_logs (status, finished_at) for cleanup queries."""
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_processing_logs_status_finished_at "
        "ON processing_logs (status, finished_at)"
    )


def downgrade() -> None:
    """Remove composite index added for cleanup query optimization."""
    op.execute("DROP INDEX IF EXISTS idx_processing_logs_status_finished_at")