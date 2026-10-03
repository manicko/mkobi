"""Tests for server-side MIME type validation.

These tests verify that MIME type detection from file content works correctly
and rejects spoofed Content-Type headers.

Host premise: the suite now runs against libmagic. python-magic is a hard
startup dependency enforced by main.check_dependencies, and no heuristic
fallback exists, so the expected verdicts are the test container's libmagic
verdicts and are not host-dependent.
"""

import gzip
import tempfile
from pathlib import Path

import pytest
from fastapi import status
from httpx import AsyncClient

import uuid

from mkobi.core.security import create_access_token, hash_password
from mkobi.db.models.dashboard import Dashboard
from mkobi.db.repositories.access_repo import AccessRepository
from mkobi.db.repositories.dashboard_repo import DashboardRepository
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.models.enums import DashboardPermission


class TestMimeTypeValidation:
    """Test server-side MIME type detection via python-magic.

    libmagic is a hard startup dependency (main.check_dependencies) and there is
    no heuristic fallback; libmagic and the deleted heuristic agreed on all five
    cases below, so no behavioural change was needed.
    """

    @pytest.fixture
    async def test_dashboard(self, async_db_session) -> Dashboard:
        """Create a test dashboard for upload tests."""
        repo = DashboardRepository()
        dashboard = await repo.create(
            db=async_db_session,
            name=f"test_mime_dashboard_{uuid.uuid4().hex[:8]}",
            description="Dashboard for MIME validation tests",
        )
        await async_db_session.commit()
        return dashboard

    @pytest.fixture
    async def editor_user(self, async_db_session) -> dict:
        """Create an editor user for upload tests."""
        user_repo = UserRepository()
        unique_id = uuid.uuid4().hex[:8]
        user = await user_repo.create(
            db=async_db_session,
            email=f"editor_mime_{unique_id}@example.com",
            password_hash=hash_password("TestPass123!"),
            role="editor",
        )
        await async_db_session.commit()

        token = create_access_token({"user_id": str(user.id), "email": user.email})
        return {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "token": token,
        }

    async def test_genuine_csv_passes(
        self,
        authenticated_client: AsyncClient,
        async_db_session,
        test_user: dict,
        test_dashboard: Dashboard,
    ) -> None:
        """A real CSV file with correct MIME should be accepted (201)."""
        # Grant edit access to test user
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=test_user["id"],
            dashboard_id=test_dashboard.id,
            permission=DashboardPermission.EDIT,
        )
        await async_db_session.commit()

        # Real CSV content with proper structure
        csv_content = b"date,category,revenue\n2023-01-01,A,100.5\n2023-01-02,B,200.0\n"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            csv_path = Path(f.name)

        try:
            with open(csv_path, "rb") as f:
                response = await authenticated_client.post(
                    f"/upload/{test_dashboard.id}",
                    files={"file": ("data.csv", f, "text/csv")},
                )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert "task_id" in data
        finally:
            csv_path.unlink(missing_ok=True)

    async def test_spoofed_content_type_rejected(
        self,
        authenticated_client: AsyncClient,
        async_db_session,
        test_user: dict,
        test_dashboard: Dashboard,
    ) -> None:
        """Executable content disguised as CSV should be rejected (415).

        Security test: An attacker uploads a file with ELF header and .csv extension,
        claiming it is text/csv. The actual content detection should reject it.
        """
        # Grant edit access
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=test_user["id"],
            dashboard_id=test_dashboard.id,
            permission=DashboardPermission.EDIT,
        )
        await async_db_session.commit()

        # ELF executable header - will be detected as application/x-executable or similar
        elf_header = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write(elf_header)
            fake_path = Path(f.name)

        try:
            with open(fake_path, "rb") as f:
                response = await authenticated_client.post(
                    f"/upload/{test_dashboard.id}",
                    files={"file": ("malicious.csv", f, "text/csv")},
                )

            # Should be rejected with 415 Unsupported Media Type
            assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            # Response detail should indicate invalid file type
            response_data = response.json()
            assert "detail" in response_data
        finally:
            fake_path.unlink(missing_ok=True)

    async def test_genuine_gzip_passes(
        self,
        authenticated_client: AsyncClient,
        async_db_session,
        test_user: dict,
        test_dashboard: Dashboard,
    ) -> None:
        """A real gzip file with correct MIME should pass validation (201).

        Tests that compressed CSV files (.csv.gz) are properly detected
        and accepted via gzip magic bytes.
        """
        # Grant edit access
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=test_user["id"],
            dashboard_id=test_dashboard.id,
            permission=DashboardPermission.EDIT,
        )
        await async_db_session.commit()

        # Real gzip content - gzip magic bytes are 0x1f 0x8b
        csv_content = b"date,category,revenue\n2023-01-01,A,100.5\n"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv.gz", delete=False) as f:
            with gzip.GzipFile(fileobj=f, mode="wb") as gz:
                gz.write(csv_content)
            gz_path = Path(f.name)

        try:
            with open(gz_path, "rb") as f:
                response = await authenticated_client.post(
                    f"/upload/{test_dashboard.id}",
                    files={"file": ("data.csv.gz", f, "application/gzip")},
                )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert "task_id" in data
        finally:
            gz_path.unlink(missing_ok=True)

    async def test_empty_file_handled(
        self,
        authenticated_client: AsyncClient,
        async_db_session,
        test_user: dict,
        test_dashboard: Dashboard,
    ) -> None:
        """Empty file is handled gracefully (422).

        Empty files should be rejected with a validation error.
        """
        # Grant edit access
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=test_user["id"],
            dashboard_id=test_dashboard.id,
            permission=DashboardPermission.EDIT,
        )
        await async_db_session.commit()

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write(b"")  # Empty file
            empty_path = Path(f.name)

        try:
            with open(empty_path, "rb") as f:
                response = await authenticated_client.post(
                    f"/upload/{test_dashboard.id}",
                    files={"file": ("empty.csv", f, "text/csv")},
                )

            # Empty file should be rejected
            assert response.status_code in (status.HTTP_422_UNPROCESSABLE_CONTENT, status.HTTP_400_BAD_REQUEST)
        finally:
            empty_path.unlink(missing_ok=True)

    async def test_binary_with_csv_extension_rejected(
        self,
        authenticated_client: AsyncClient,
        async_db_session,
        test_user: dict,
        test_dashboard: Dashboard,
    ) -> None:
        """Binary files with CSV extension are rejected (415).

        Tests that non-CSV binary content is rejected even when
        the filename has .csv extension and spoofed Content-Type.
        """
        # Grant edit access
        access_repo = AccessRepository()
        await access_repo.grant_access(
            db=async_db_session,
            user_id=test_user["id"],
            dashboard_id=test_dashboard.id,
            permission=DashboardPermission.EDIT,
        )
        await async_db_session.commit()

        # PNG image magic bytes
        png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as f:
            f.write(png_header)
            fake_path = Path(f.name)

        try:
            with open(fake_path, "rb") as f:
                response = await authenticated_client.post(
                    f"/upload/{test_dashboard.id}",
                    files={"file": ("image.csv", f, "text/csv")},
                )

            # Should be rejected - PNG bytes won't be detected as text/csv
            assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        finally:
            fake_path.unlink(missing_ok=True)


class TestMimeTypeDetectionFunction:
    """Unit tests for detect_mime_type_from_content function."""

    def test_detect_csv_mime(self, tmp_path: Path) -> None:
        """Detect MIME type returns text/csv for valid CSV content."""
        from mkobi.services.file_processing import detect_mime_type_from_content

        csv_file = tmp_path / "test.csv"
        csv_file.write_bytes(b"name,value\nfoo,1\nbar,2\n")

        detected = detect_mime_type_from_content(csv_file)
        assert detected == "text/csv"

    def test_detect_gzip_mime(self, tmp_path: Path) -> None:
        """Detect MIME type returns application/gzip for valid gzip content."""
        from mkobi.services.file_processing import detect_mime_type_from_content

        gz_file = tmp_path / "test.csv.gz"
        gz_file.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff")

        detected = detect_mime_type_from_content(gz_file)
        assert detected == "application/gzip"

    def test_detect_executable_mime(self, tmp_path: Path) -> None:
        """Detect MIME type returns executable type for ELF binary."""
        from mkobi.services.file_processing import detect_mime_type_from_content

        elf_file = tmp_path / "malicious.csv"
        elf_file.write_bytes(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00")

        detected = detect_mime_type_from_content(elf_file)
        # libmagic in the test image reports application/octet-stream for this
        # 16-byte ELF header. The old "executable or octet-stream" allowance was
        # a host-branch allowance with no fallback left to justify it.
        assert detected == "application/octet-stream"

    def test_detect_plain_text_mime(self, tmp_path: Path) -> None:
        """Detect MIME type returns appropriate type for plain text content."""
        from mkobi.services.file_processing import detect_mime_type_from_content

        text_file = tmp_path / "text.csv"
        text_file.write_bytes(b"just some plain text without csv structure")

        detected = detect_mime_type_from_content(text_file)
        # The "application/octet-stream" alternative was the deleted fallback's
        # return and is now unreachable; libmagic reports text/plain.
        assert detected == "text/plain"


class TestValidateMimeType:
    """Unit tests for validate_mime_type function.

    ``validate_mime_type`` returns the detector's admitted verdict (D-06-P = (a)):
    the caller derives the stored extension from it. A disallowed verdict escapes
    as ``AppException(ErrorCode.INVALID_FILE_TYPE)``, the project's own error type.
    """

    def test_validate_csv_mime_passes(self, tmp_path: Path, valid_csv_content: bytes) -> None:
        """validate_mime_type should pass and return the detected CSV MIME type."""
        from mkobi.models.enums import MimeTypeEnum
        from mkobi.services.file_processing import validate_mime_type

        csv_file = tmp_path / "test.csv"
        csv_file.write_bytes(valid_csv_content)

        # Should not raise; the return is the verdict the naming rule consumes.
        detected = validate_mime_type(csv_file)
        assert detected == MimeTypeEnum.TEXT_CSV

    def test_validate_gzip_mime_passes(self, tmp_path: Path) -> None:
        """validate_mime_type should pass and return a gzip MIME type."""
        from mkobi.models.enums import MimeTypeEnum
        from mkobi.services.file_processing import validate_mime_type

        gz_file = tmp_path / "test.csv.gz"
        gz_file.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff")

        # Should not raise; both gzip members map to .csv.gz.
        detected = validate_mime_type(gz_file)
        assert detected in (MimeTypeEnum.APPLICATION_GZIP, MimeTypeEnum.APPLICATION_X_GZIP)

    def test_validate_invalid_mime_raises(self, tmp_path: Path) -> None:
        """validate_mime_type should raise AppException(INVALID_FILE_TYPE)."""
        from mkobi.models.enums import ErrorCode
        from mkobi.services.file_processing import validate_mime_type
        from mkobi.utils.exceptions import AppException

        elf_file = tmp_path / "malicious.csv"
        elf_file.write_bytes(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00")

        with pytest.raises(AppException) as exc_info:
            validate_mime_type(elf_file)
        assert exc_info.value.code == ErrorCode.INVALID_FILE_TYPE
        assert "Detected MIME type" in exc_info.value.detail