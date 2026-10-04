"""Tests for StrEnum vs PostgreSQL ENUM consistency.

Verifies that Python StrEnum values match PostgreSQL ENUM types defined in migrations.
This prevents runtime errors when inserting enum values.

After DB-001 migration, there should be zero extra values in the database.
"""

from enum import Enum
from typing import Any

import pytest
from sqlalchemy import text

from mkobi.models.enums import (
    DashboardPermission,
    ProcessingStatus,
    UserRole,
)


def get_str_enum_values(enum_class: type[Enum]) -> set[str]:
    """Extract string values from a StrEnum class.

    Args:
        enum_class: A StrEnum subclass to extract values from.

    Returns:
        Set of string values from the enum.
    """
    return {member.value for member in enum_class}


def get_db_enum_values(db_session, enum_type_name: str) -> set[str]:
    """Query PostgreSQL for existing ENUM type values.

    Uses pg_type and pg_enum system catalogs to retrieve all
    allowed values for a named ENUM type.

    Args:
        db_session: SQLAlchemy async session.
        enum_type_name: Name of the PostgreSQL ENUM type.

    Returns:
        Set of string values from the database ENUM type.
    """
    query = text(
        """
        SELECT enumlabel
        FROM pg_enum
        JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
        WHERE pg_type.typname = :type_name
        ORDER BY pg_enum.enumsortorder
        """
    )

    result = db_session.execute(query, {"type_name": enum_type_name})
    rows = result.fetchall()
    return {row[0] for row in rows}


def compare_enum_values(
    python_values: set[str], db_values: set[str]
) -> tuple[set[str], set[str]]:
    """Compare Python enum values with PostgreSQL ENUM values in both directions.

    Args:
        python_values: Values declared by the Python StrEnum.
        db_values: Values present in the PostgreSQL ENUM type.

    Returns:
        Tuple of (missing_in_db, extra_in_db): values in Python but not in the
        database, and values in the database but not in Python.
    """
    return python_values - db_values, db_values - python_values


class TestUserRoleEnumConsistency:
    """Tests for UserRole StrEnum vs PostgreSQL user_role ENUM consistency."""

    @pytest.mark.asyncio
    async def test_user_role_values_match(self, async_db_session):
        """Verify UserRole enum values match PostgreSQL user_role type."""
        python_values = get_str_enum_values(UserRole)
        db_values = await async_db_session.run_sync(
            lambda sync_session: get_db_enum_values(sync_session, "user_role")
        )

        missing_in_db, extra_in_db = compare_enum_values(python_values, db_values)

        assert not missing_in_db, (
            f"Values in UserRole but not in PostgreSQL: {missing_in_db}"
        )

        assert not extra_in_db, (
            f"PostgreSQL user_role has extra values not in Python: {extra_in_db}. "
            "This indicates schema drift that should be resolved."
        )

    @pytest.mark.asyncio
    async def test_user_role_can_insert(self, async_db_session):
        """Verify all UserRole values can be inserted into database.

        This is the practical test - if any value can't be inserted,
        there's a mismatch that would cause runtime errors.
        """
        from uuid import uuid4

        from mkobi.core.security import hash_password
        from mkobi.db.repositories.user_repo import UserRepository

        repo = UserRepository()

        for role in UserRole:
            user = await repo.create(
                db=async_db_session,
                email=f"role_test_{role.value}_{uuid4().hex[:8]}@example.com",
                password_hash=hash_password("TestPass123!"),
                role=role,
            )
            assert user.role == role, f"Failed to insert role {role.value}"


class TestDashboardPermissionEnumConsistency:
    """Tests for DashboardPermission StrEnum vs PostgreSQL dashboard_permission_level ENUM."""

    @pytest.mark.asyncio
    async def test_dashboard_permission_values_match(self, async_db_session):
        """Verify DashboardPermission enum values match PostgreSQL type."""
        python_values = get_str_enum_values(DashboardPermission)
        db_values = await async_db_session.run_sync(
            lambda sync_session: get_db_enum_values(
                sync_session, "dashboard_permission_level"
            )
        )

        missing_in_db, extra_in_db = compare_enum_values(python_values, db_values)

        assert not missing_in_db, (
            f"Values in DashboardPermission but not in PostgreSQL: {missing_in_db}"
        )

        assert not extra_in_db, (
            "PostgreSQL dashboard_permission_level has extra values not in Python: "
            f"{extra_in_db}. This indicates schema drift that should be resolved."
        )

    @pytest.mark.asyncio
    async def test_dashboard_permission_can_insert(self, async_db_session, test_user: dict[str, Any]):
        """Verify all DashboardPermission values can be inserted into database."""
        from uuid import uuid4

        from mkobi.db.models.access import DashboardAccess
        from mkobi.db.repositories.dashboard_repo import DashboardRepository

        dashboard_repo = DashboardRepository()

        for permission in DashboardPermission:
            dashboard = await dashboard_repo.create(
                db=async_db_session,
                name=f"permission_test_{permission.value}_{uuid4().hex[:8]}",
                created_by=test_user["id"],
            )

            access = DashboardAccess(
                user_id=test_user["id"],
                dashboard_id=dashboard.id,
                permission=permission,
            )
            async_db_session.add(access)
            await async_db_session.flush()

            # Verify the permission was stored correctly by querying directly
            result = await async_db_session.execute(
                text(
                    "SELECT permission FROM dashboard_access "
                    "WHERE user_id = :uid AND dashboard_id = :did"
                ),
                {"uid": test_user["id"], "did": dashboard.id},
            )
            row = result.fetchone()
            assert row is not None, f"Failed to insert permission {permission.value}"
            assert row[0] == permission.value, (
                f"Retrieved wrong permission for {permission.value}"
            )

            # Cleanup each dashboard
            await async_db_session.delete(dashboard)


class TestProcessingStatusEnumConsistency:
    """Tests for ProcessingStatus StrEnum vs PostgreSQL processing_status ENUM."""

    @pytest.mark.asyncio
    async def test_processing_status_values_match(self, async_db_session):
        """Verify ProcessingStatus enum values match PostgreSQL processing_status type.

        After migration DB-001, there should be zero extra values in the database.
        """
        python_values = get_str_enum_values(ProcessingStatus)
        db_values = await async_db_session.run_sync(
            lambda sync_session: get_db_enum_values(sync_session, "processing_status")
        )

        missing_in_db, extra_in_db = compare_enum_values(python_values, db_values)

        # Only fail if Python values are missing from DB (would cause insert errors)
        assert not missing_in_db, (
            f"Values in ProcessingStatus but not in PostgreSQL: {missing_in_db}"
        )

        # Extra values in DB indicate schema drift - should be zero after cleanup
        assert not extra_in_db, (
            f"PostgreSQL processing_status has extra values not in Python: {extra_in_db}. "
            "This indicates schema drift that should be resolved."
        )

    @pytest.mark.asyncio
    async def test_processing_status_can_insert(self, async_db_session):
        """Verify all ProcessingStatus values can be inserted into database.

        This is the definitive test - if this passes, runtime insert works.
        """
        from mkobi.db.models.processing_logs import ProcessingLog

        for status in ProcessingStatus:
            log = ProcessingLog(
                dashboard_id=None,
                status=status,
                message=f"Test log for {status.value}",
            )
            async_db_session.add(log)
            await async_db_session.flush()

            # Verify the status was stored correctly by querying directly
            result = await async_db_session.execute(
                text("SELECT status FROM processing_logs WHERE id = :id"),
                {"id": log.id},
            )
            row = result.fetchone()
            assert row is not None, f"Failed to insert status {status.value}"
            assert row[0] == status.value, f"Retrieved wrong status for {status.value}"


class TestAllMappedEnumsConsistency:
    """Comprehensive test that checks all enums mapped to database columns."""

    ENUM_MAPPINGS = [
        ("user_role", UserRole),
        ("dashboard_permission_level", DashboardPermission),
        ("processing_status", ProcessingStatus),
    ]

    @pytest.mark.asyncio
    async def test_all_enums_consistent(self, async_db_session):
        """Verify all StrEnums mapped to DB columns exist in PostgreSQL.

        This test fails if Python enum values are missing from DB (would cause insert errors)
        or if DB has extra values (indicates schema drift). After DB-001 migration,
        processing_status should have zero extra values.
        """
        python_values_missing_in_db: dict[str, set[str]] = {}
        db_values_extra_in_db: dict[str, set[str]] = {}

        for db_type_name, enum_class in self.ENUM_MAPPINGS:
            python_values = get_str_enum_values(enum_class)
            db_values = await async_db_session.run_sync(
                lambda sync_session, tn=db_type_name: get_db_enum_values(
                    sync_session, tn
                )
            )

            missing, extra = compare_enum_values(python_values, db_values)

            # Track Python values that are missing from DB
            if missing:
                python_values_missing_in_db[db_type_name] = missing

            # Track DB values that are absent from Python
            if extra:
                db_values_extra_in_db[db_type_name] = extra

        assert not python_values_missing_in_db, (
            f"Enum values missing from PostgreSQL: {python_values_missing_in_db}"
        )

        assert not db_values_extra_in_db, (
            f"PostgreSQL enum types have extra values not in Python: {db_values_extra_in_db}. "
            "This indicates schema drift that should be resolved."
        )