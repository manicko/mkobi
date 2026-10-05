"""Drop an index on dashboard_filters that no revision in this chain creates.

Revision ID: f47ac18b5b9e
Revises: b749bc53b1ee
Create Date: 2026-06-10 22:00:00.000000

The object this revision names, ``idx_dashboard_filters_dashboard_id``, is
created by no revision in this chain. The initial migration (000000000000) is
the authority for the ``dashboard_filters`` index inventory, and it creates only
the primary key index, ``dashboard_filters_pkey``. So the drop below is a no-op
on every database built from this chain, and its ``DROP INDEX IF EXISTS`` guard
is what makes that safe. The guard also covers the databases this index was
actually created in - externally, outside Alembic - which is where it existed at
all.

That object duplicates the primary key's column set. ``dashboard_filters`` has a
composite primary key on ``(dashboard_id, filter_id)``, and the primary key
constraint already builds a unique index over exactly those columns. The named
index was a plain, non-unique index over the same two columns, so it could only
add write overhead.

The reverse (``downgrade()``) therefore does not recreate that duplicate. A
reverse that rebuilt a second index over the primary key's own columns would
reintroduce a defect rather than undo one, so this revision's reverse is an
explicit no-op: after any round trip of this revision, ``dashboard_filters_pkey``
remains the only index on ``dashboard_filters``.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f47ac18b5b9e"
down_revision: str | Sequence[str] | None = "b749bc53b1ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove redundant index on dashboard_filters.

    The PRIMARY KEY creates a unique index on (dashboard_id, filter_id).
    The non-unique idx_dashboard_filters_dashboard_id is redundant and
    only adds unnecessary write overhead.
    """
    op.execute("DROP INDEX IF EXISTS idx_dashboard_filters_dashboard_id")


def downgrade() -> None:
    """No-op.

    The index this revision drops duplicates the primary key's column set, so
    recreating it would reintroduce the defect this revision exists to remove.
    ``dashboard_filters_pkey`` stays the only index on ``dashboard_filters``.
    """
    pass