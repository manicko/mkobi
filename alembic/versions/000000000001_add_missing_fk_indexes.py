"""Retained no-op - its predecessor creates every index its name refers to.

Revision ID: 000000000001
Revises: 000000000000
Create Date: 2026-06-02 13:15:00.000000

This revision is a retained no-op. Its predecessor, the initial migration
(000000000000), creates every index this revision's name refers to, so this
revision neither adds nor removes anything on any database. It is kept in the
chain only so that version tables which already recorded it remain valid; it
does not create the indexes, and no database ever applied them through it.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "000000000001"
down_revision: str | Sequence[str] | None = "000000000000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Indexes are now created in initial migration - this is a no-op."""
    pass


def downgrade() -> None:
    """No-op - indexes remain in place."""
    pass