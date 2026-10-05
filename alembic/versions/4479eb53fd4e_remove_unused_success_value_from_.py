"""Remove unused 'success' value from processing_status ENUM.

This value was a legacy alias that is replaced by 'completed'.
No data migration needed as verified: no rows have status='success'.

The forward path has no rollback. The four statements below create a replacement
type and then drop the original; none carries an ``IF EXISTS`` guard, and an
``ALTER TYPE``/``DROP TYPE`` interruption leaves the change half-applied with no
idempotent way to retry it. A partially applied upgrade therefore cannot be
recovered with ``alembic downgrade``: the compensating procedure is a new forward
revision that reconciles the type to the desired shape. Operators read this
before applying the revision.

Revision ID: 4479eb53fd4e
Revises: 000000000002
Create Date: 2026-06-05 16:51:30.580802
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4479eb53fd4e"
down_revision: Sequence[str] | None = "000000000002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Remove unused 'success' value from processing_status ENUM.

    PostgreSQL requires CREATE TYPE ... AS ENUM with all desired values
    to remove a value from an existing ENUM type.
    """
    # Recreate the enum type without 'success' value
    op.execute(
        """
        ALTER TYPE processing_status RENAME TO processing_status_old
        """
    )
    op.execute(
        """
        CREATE TYPE processing_status AS ENUM (
            'started',
            'uploaded',
            'processing',
            'completed',
            'failed'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE processing_logs
        ALTER COLUMN status TYPE processing_status
        USING status::text::processing_status
        """
    )
    op.execute(
        """
        DROP TYPE processing_status_old
        """
    )


def downgrade() -> None:
    """Restore the pre-revision value set as a true reverse of the forward shape.

    This reverse now declares exactly the values ``upgrade()`` declares, in
    exactly the same order. It does not reintroduce 'success': a reverse that
    adds a value the forward shape never had would not be a reverse of that
    shape, and the asymmetry would be a latent ordering divergence rather than
    a restoration.
    """
    # Recreate the enum type with the forward value set and order
    op.execute(
        """
        ALTER TYPE processing_status RENAME TO processing_status_old
        """
    )
    op.execute(
        """
        CREATE TYPE processing_status AS ENUM (
            'started',
            'uploaded',
            'processing',
            'completed',
            'failed'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE processing_logs
        ALTER COLUMN status TYPE processing_status
        USING status::text::processing_status
        """
    )
    op.execute(
        """
        DROP TYPE processing_status_old
        """
    )