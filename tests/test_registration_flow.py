"""End-to-end tests for the complete registration request flow.

Tests the full flow:
1. Submit registration request
2. Admin approves request
3. User logs in with temp password
4. User changes password
5. User accesses dashboard
"""

import re
import uuid

from fastapi import status
from httpx import AsyncClient

from mkobi.core.security import create_access_token, hash_password
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.graph_repo import GraphRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import DashboardPermission, GraphType, UserRole


class TestRegistrationFlow:
    """Tests for complete registration request end-to-end flow."""

    async def test_registration_request_flow(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test complete registration flow: request -> approve -> login -> change password -> dashboard access."""
        # Step 1: Public user submits registration request
        registration_email = f"new_user_{uuid.uuid4().hex[:8]}@example.com"

        register_response = await async_client.post(
            "/auth/register-request",
            json={"email": registration_email},
        )

        assert register_response.status_code == status.HTTP_201_CREATED
        register_data = register_response.json()
        assert "id" in register_data
        assert register_data["email"] == registration_email
        assert register_data["status"] == "pending"
        request_id = register_data["id"]

        # Step 2: Admin approves the registration request
        admin_user = await UserRepository().create(
            db=async_db_session,
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        approve_response = await async_client.post(
            f"/admin/registration-requests/{request_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert approve_response.status_code == status.HTTP_200_OK
        approve_data = approve_response.json()
        assert approve_data["message"] == "Registration request approved"
        assert "user_id" in approve_data
        assert "retrieval_token" in approve_data

        created_user_id = approve_data["user_id"]
        retrieval_token = approve_data["retrieval_token"]

        # Step 3: Admin retrieves the temporary password
        temp_response = await async_client.get(
            f"/admin/temp-passwords/{retrieval_token}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert temp_response.status_code == status.HTTP_200_OK
        temp_data = temp_response.json()
        temp_password = temp_data["temp_password"]
        assert len(temp_password) >= 16
        assert re.search(r"[a-zA-Z]", temp_password)
        assert re.search(r"\d", temp_password)

        # Step 4: User logs in with temporary password
        login_response = await async_client.post(
            "/auth/login",
            json={
                "email": registration_email,
                "password": temp_password,
            },
        )

        assert login_response.status_code == status.HTTP_200_OK
        login_data = login_response.json()
        assert "access_token" in login_data
        user_token = login_data["access_token"]
        user_id = login_data["user"]["id"]
        assert user_id == created_user_id

        # Verify user has force_password_change flag set (should be True after approval)
        user_repo = UserRepository()
        user = await user_repo.get_with_hash(uuid.UUID(user_id), async_db_session)
        assert user is not None
        assert user.force_password_change is True

        # Step 5: User changes password (clearing force_password_change flag)
        new_password = "NewSecurePass123!"
        change_response = await async_client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "current_password": temp_password,
                "new_password": new_password,
                "confirm_password": new_password,
            },
        )

        assert change_response.status_code == status.HTTP_200_OK
        assert change_response.json()["message"] == "Password changed successfully"

        # Verify force_password_change is now False
        user = await user_repo.get(uuid.UUID(user_id), async_db_session)
        assert user is not None
        assert user.force_password_change is False

        # Step 5b: The password change withdrew the session's token, so the
        # user must log in again before continuing. The user-level revocation
        # marker is timestamped: it rejects credentials issued at or before the
        # change and allows a session minted afterwards, which is exactly what
        # this re-login produces. This is the landed contract for credential
        # rotation (D-04-M); only the re-login keeps the flow usable.
        relogin_response = await async_client.post(
            "/auth/login",
            json={"email": registration_email, "password": new_password},
        )
        assert relogin_response.status_code == status.HTTP_200_OK
        user_token = relogin_response.json()["access_token"]

        # Step 6: Create a dashboard and grant access to the new user
        dashboard_repo = DashboardRepository()
        graph_repo = GraphRepository()

        dashboard = await dashboard_repo.create(
            db=async_db_session,
            name=f"test_dashboard_{uuid.uuid4().hex[:8]}",
            created_by=admin_user.id,
        )
        await async_db_session.flush()

        graph = await graph_repo.create(
            db=async_db_session,
            dashboard_id=dashboard.id,
            name=f"test_graph_{uuid.uuid4().hex[:8]}",
            type=GraphType.TABLE,
            dimensions=["category"],
            metrics=["sales"],
            config={},
        )
        await async_db_session.flush()

        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=uuid.UUID(user_id),
            dashboard_id=dashboard.id,
            permission=DashboardPermission.VIEW,
        )
        await async_db_session.commit()

        # Step 7: User accesses dashboard data
        data_response = await async_client.get(
            "/data/aggregated",
            params={"dashboard_id": str(dashboard.id), "graph_id": str(graph.id)},
            headers={"Authorization": f"Bearer {user_token}"},
        )

        # Should return 200 with empty data (no data uploaded yet) or 404 for no data
        assert data_response.status_code in (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND)


class TestRegistrationFlowEdgeCases:
    """Edge case tests for registration flow."""

    async def test_duplicate_registration_request_fails(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test that duplicate registration request is rejected."""
        registration_email = f"duplicate_user_{uuid.uuid4().hex[:8]}@example.com"

        # First request
        response1 = await async_client.post(
            "/auth/register-request",
            json={"email": registration_email},
        )
        assert response1.status_code == status.HTTP_201_CREATED

        # Second request with same email should fail
        response2 = await async_client.post(
            "/auth/register-request",
            json={"email": registration_email},
        )
        assert response2.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_registration_approve_nonexistent_fails(
        self, async_client: AsyncClient, async_db_session
    ) -> None:
        """Test approving non-existent request returns 404."""
        admin_user = await UserRepository().create(
            db=async_db_session,
            email=f"admin_approve_nonexist_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
        )
        await async_db_session.commit()

        admin_token = create_access_token({
            "user_id": str(admin_user.id),
            "email": admin_user.email,
        })

        fake_request_id = uuid.uuid4()
        response = await async_client.post(
            f"/admin/registration-requests/{fake_request_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND