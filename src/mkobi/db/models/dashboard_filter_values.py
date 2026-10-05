"""Dashboard filter values model for filter UI options.

Stores distinct filter values extracted from aggregated data
to populate filter UI checkboxes.

Index provenance
----------------
The two indexes in ``__table_args__`` are declared here so the model matches
the chain: both are created by revision ``000000000002``, which is the
authority for this table's index inventory. Declaring them keeps
``alembic check`` (``.\\Makefile.ps1 migration-check``) clean -- an index that
exists in the database but is declared by no model is reported as drift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mkobi.db.base import Base

if TYPE_CHECKING:
    from mkobi.db.models.dashboard import Dashboard


class DashboardFilterValue(Base):
    """Dashboard filter values model.

    Stores distinct filter values for dashboards to populate
    filter UI checkboxes. Values are extracted from aggregated data.
    """

    __tablename__ = "dashboard_filter_values"
    __table_args__ = (
        Index(
            "uq_dashboard_filter_values",
            "dashboard_id",
            "filter_name",
            "filter_value",
            unique=True,
        ),
        Index(
            "idx_dashboard_filter_values_lookup",
            "dashboard_id",
            "filter_name",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    )

    dashboard_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )

    filter_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    filter_value: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    # Relationship with dashboard
    dashboard: Mapped[Dashboard] = relationship(
        "Dashboard",
        back_populates="filter_values",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<DashboardFilterValue id={self.id} dashboard_id={self.dashboard_id} filter_name={self.filter_name}>"

    def __str__(self) -> str:
        return f"Filter value: {self.filter_name}={self.filter_value}"