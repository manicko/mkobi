"""Index processing_logs.started_at for the always-ordered filtered log listing.

Revision ID: a1c2d3e4f5a6
Revises: 82739c97fde1
Create Date: 2026-06-15 10:00:00.000000

``ProcessingLogRepository.get_filtered`` orders by ``started_at DESC``
unconditionally, on every call. Before this revision no index on
``processing_logs`` led with ``started_at``, so each filtered listing was a
full sort of the table. The index below leads with ``started_at``, which lets
the planner satisfy the ORDER BY from an index scan instead of sorting.

The model declares the matching ``Index`` in
``ProcessingLog.__table_args__``; a schema-only revision would make the next
``alembic check`` report model/schema drift. The two must move together.

This revision uses the same in-transaction ``CREATE INDEX IF NOT EXISTS`` shape
as the other index revisions in this chain. ``CREATE INDEX CONCURRENTLY`` was
considered and rejected here: it cannot run inside the transaction
``alembic/env.py`` opens, and the async migration connection holds that
transaction on the driver as well, so every escape to an out-of-transaction
connection either discards the migration's own work or deadlocks against the
connection ``run_sync`` is holding. The plain form is transactional, which is
the shape the rest of this chain already relies on.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c2d3e4f5a6"
down_revision: str | Sequence[str] | None = "82739c97fde1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the started_at-leading index for the ordered filtered listing."""
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_processing_logs_started_at "
        "ON processing_logs (started_at)"
    )


def downgrade() -> None:
    """Remove the started_at-leading index added for the ordered listing."""
    op.execute("DROP INDEX IF EXISTS idx_processing_logs_started_at")
