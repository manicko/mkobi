"""Tests for users API endpoints."""

import uuid
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import delete, select

from mkobi.core.security import hash_password
from mkobi.db.models import user as user_model
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import UserRole


async def _read_role_in_new_session(async_session_maker, user_id: uuid.UUID) -> UserRole | None:
    """Re-read a user's role through a second session, independent of the request's."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(user_model.User.role).where(user_model.User.id == user_id)
        )
        return result.scalar_one_or_none()


async def _delete_committed_email(async_session_maker, email: str) -> None:
    """Delete a row committed by this test; a production commit is durable here."""
    async with async_session_maker() as session:
        await session.execute(
            delete(user_model.User).where(user_model.User.email == email)
        )
        await session.commit()


async def _read_existing_user_ids(
    async_session_maker, user_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    """Return which of the given ids are still present, via a fresh session.

    A fresh session reads committed state only, so a delete that reached the
    database durably - as opposed to merely being flushed inside the test's
    open transaction - is observed as missing.
    """
    if not user_ids:
        return set()
    async with async_session_maker() as session:
        result = await session.execute(
            select(user_model.User.id).where(user_model.User.id.in_(user_ids))
        )
        return set(result.scalars().all())


class TestGetProfile:
    """Tests for get profile endpoint."""

    async def test_get_own_profile(
        self, async_client: AsyncClient, test_user: dict
    ) -> None:
        """Test getting own profile via /auth/me."""
        login_resp = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        token = login_resp.json()["access_token"]

        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == test_user["email"]
        assert data["role"] == test_user["role"]

    async def test_get_profile_unauthorized(
        self, async_client: AsyncClient
    ) -> None:
        """Test getting profile without token."""
        response = await async_client.get("/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUpdateUserRoleDeprecatedPut:
    """Tests for the deprecated PUT /users/{user_id} surface.

    This endpoint reaches UserService.update_user_role and had no test caller at
    all; it is one of the four endpoints whose write was not committed.
    """

    async def test_deprecated_put_updates_role_durably(
        self,
        async_client: AsyncClient,
        async_db_session,
        async_session_maker,
        test_user: dict,
    ) -> None:
        """PUT /users/{user_id} returns the updated role and commits it."""
        repo = UserRepository()
        target_email = f"deprecated_put_{uuid.uuid4().hex[:8]}@example.com"
        target = await repo.create(
            db=async_db_session,
            email=target_email,
            password_hash=hash_password("TargetPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        try:
            response = await async_client.put(
                f"/users/{target.id}",
                headers={"Authorization": f"Bearer {test_user['token']}"},
                json={"role": UserRole.EDITOR},
            )
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["role"] == UserRole.EDITOR

            # Committed, not merely flushed.
            committed_role = await _read_role_in_new_session(
                async_session_maker, target.id
            )
            assert committed_role == UserRole.EDITOR
        finally:
            # The request shares this session. A failed durability assertion
            # leaves the uncommitted UPDATE holding a row lock, so release it
            # before the cleanup DELETE or a regression would hang here
            # instead of reporting red.
            await async_db_session.rollback()
            await _delete_committed_email(async_session_maker, target_email)


class TestDeleteAccount:
    """Tests for self-deletion endpoint."""

    async def test_delete_own_account(
        self, async_client: AsyncClient, test_user: dict, async_db_session
    ) -> None:
        """Test deleting own account via /users/me."""
        login_resp = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        token = login_resp.json()["access_token"]

        response = await async_client.delete(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

        login_resp = await async_client.post(
            "/auth/login",
            json={
                "email": test_user["email"],
                "password": "TestPass123!",
            },
        )
        assert login_resp.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_delete_account_unauthorized(
        self, async_client: AsyncClient
    ) -> None:
        """Test deleting account without token."""
        response = await async_client.delete("/users/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_admin_cannot_delete_self(
        self, async_client: AsyncClient, async_db_session, async_session_maker
    ) -> None:
        """Test that admin cannot delete their own account when they are the only admin.

        The _check_admin_deletion_allowed function blocks deletion when:
        - total users > 1 (other users exist)
        - admin count <= 1 (this admin is the sole admin)
        """
        repo = UserRepository()

        # Create a sole admin user
        admin_email = f"sole_admin_{uuid.uuid4().hex[:8]}@example.com"
        admin_user = await repo.create(
            db=async_db_session,
            email=admin_email,
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        # Create a non-admin user
        viewer_email = f"viewer_{uuid.uuid4().hex[:8]}@example.com"
        await repo.create(
            db=async_db_session,
            email=viewer_email,
            password_hash=hash_password("ViewerPass123!"),
            role=UserRole.VIEWER,
        )
        await async_db_session.commit()

        # Verify state scoped to this test's own rows: both exist, exactly one
        # admin. Selecting by the uuid-suffixed addresses avoids asserting on a
        # global row count, which other tests share and mutate concurrently.
        all_after = await repo.get_all(async_db_session)
        own_rows = [u for u in all_after if u.email in (admin_email, viewer_email)]
        own_admins = [u for u in own_rows if u.role == UserRole.ADMIN]
        assert len(own_rows) == 2, f"Expected 2 own users, got {len(own_rows)}"
        assert len(own_admins) == 1, f"Expected 1 own admin, got {len(own_admins)}"

        # The production guard reads global state: it forbids deleting an admin
        # only while this admin is the sole admin in the whole users table. Other
        # tests in the session commit their own admin rows, so this test must
        # make its admin the only admin relative to the guard's global read.
        # Delete only foreign ADMIN rows, and deliberately DO NOT commit: the
        # request shares this session, so the guard sees the pending deletes,
        # while the fixture's SAVEPOINT rollback at teardown restores those rows
        # for any later test. The precondition is constructed, not persisted; no
        # global state is destroyed. Non-admin rows and this test's own admin are
        # never touched. The ids are captured so the rollback can be proven to
        # restore them; see the restoration assertion below.
        foreign_admin_ids = [
            existing.id
            for existing in await repo.get_all(async_db_session)
            if existing.role == UserRole.ADMIN and existing.id != admin_user.id
        ]
        for foreign_admin_id in foreign_admin_ids:
            await repo.delete(foreign_admin_id, async_db_session)

        # Login as the admin
        login_resp = await async_client.post(
            "/auth/login",
            json={
                "email": admin_user.email,
                "password": "AdminPass123!",
            },
        )
        assert login_resp.status_code == status.HTTP_200_OK
        token = login_resp.json()["access_token"]

        # Attempt to delete own admin account
        response = await async_client.delete(
            f"/users/{admin_user.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        # Should be forbidden: sole admin cannot be deleted while users exist
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # The foreign admins above were deleted only inside this test's open
        # transaction. Roll back to the SAVEPOINT now and prove they came back:
        # if a future change ever committed those deletes, the rows would be
        # destroyed for later tests with nothing here to notice. Re-reading via
        # a fresh session sees committed state, so a durable delete fails this.
        await async_db_session.rollback()
        restored_ids = await _read_existing_user_ids(
            async_session_maker, foreign_admin_ids
        )
        assert restored_ids == set(foreign_admin_ids), (
            "Foreign admin rows were not restored after the savepoint rollback; "
            f"missing={sorted(set(foreign_admin_ids) - restored_ids)}"
        )
