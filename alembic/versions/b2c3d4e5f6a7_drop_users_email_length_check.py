"""Drop the unreachable users_email_length_check constraint.

Revision ID: b2c3d4e5f6a7
Revises: a1c2d3e4f5a6
Create Date: 2026-06-15 11:00:00.000000

``users_email_length_check`` is a chain-only object: no model under
``src/mkobi/**`` declares a ``CheckConstraint``, so the constraint is invisible
to the ORM, to autogenerate and to anyone reading the model. It was created by
``000000000000`` and has no model-side counterpart.

It is also unreachable by construction. ``users.email`` is ``VARCHAR(255)``,
and PostgreSQL refuses any value longer than a ``VARCHAR(255)`` can hold, so
``length(email) <= 255`` can never be false on a stored row. Dropping the
constraint changes no admissible value.

The surviving guarantee is the column type: ``users.email`` stays
``VARCHAR(255)``, which is the limit the application actually depends on.
No ``CheckConstraint`` is added to any model — doing so would both resurrect
the drift and move a database invariant into a layer where this project does
not express them.

``downgrade()`` re-adds the constraint. The predicate names the ``users`` table
in its own expression (``email`` is unqualified), and the statement targets
``users`` explicitly, so the re-add cannot attach to an unrelated table.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the unreachable email length check from users."""
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_length_check")


def downgrade() -> None:
    """Restore the email length check on users."""
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_email_length_check "
        "CHECK (length(email) <= 255)"
    )
