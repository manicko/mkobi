from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator
from uuid import UUID

from mkobi.models.enums import RegistrationStatus, UserRole
from mkobi.models.user import UserRead
from mkobi.utils.validators import validate_password_or_raise


class LoginRequest(BaseModel):
    """Login request model."""

    email: EmailStr
    password: str

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "secure_password123",
            }
        },
    )


class TempPasswordRetrievalRequest(BaseModel):
    """Request body for the temp-password retrieval operation.

    The handle is carried in the body so it never reaches the request line and,
    therefore, never appears in the application access log.
    """

    retrieval_token: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "retrieval_token": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            }
        },
    )


class RegistrationRequestCreate(BaseModel):
    """Registration request model."""

    email: EmailStr

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "email": "user@example.com",
            }
        },
    )


class RegistrationRequestResponse(BaseModel):
    """Registration request response model."""

    id: UUID
    email: EmailStr
    status: RegistrationStatus

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "status": "pending",
            }
        },
    )


class RegistrationRequestItem(BaseModel):
    """Registration request item for admin listing."""

    id: UUID
    email: EmailStr
    status: RegistrationStatus
    requested_by_ip: str | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "status": "pending",
                "requested_by_ip": "192.168.1.1",
                "reviewed_by": None,
                "reviewed_at": None,
                "created_at": "2026-04-24T16:02:46+03:00",
            }
        },
    )

    @field_validator("requested_by_ip", mode="before")
    @classmethod
    def serialize_ip(cls, v: object) -> str | None:
        """Convert IP address object to string representation."""
        if v is None:
            return None
        return str(v)


class RegisterRequest(BaseModel):
    """Register request model."""

    email: EmailStr
    password: str
    role: UserRole = UserRole.VIEWER

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "secure_password123",
                "role": UserRole.VIEWER,
            }
        },
    )

    @field_validator("password")
    @classmethod
    def validate_password_field(cls, v: str) -> str:
        """Validate password meets strength requirements."""
        validate_password_or_raise(v)
        return v


class Token(BaseModel):
    """Access token model."""

    access_token: str
    token_type: str

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
            }
        },
    )


class TokenWithUser(Token):
    """Access token model with user data."""

    user: UserRead

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "email": "user@example.com",
                    "role": "viewer",
                    "created_at": "2026-04-24T16:02:46+03:00",
                },
            }
        },
    )


class TokenData(BaseModel):
    """Token data model."""

    email: EmailStr | None = None
    user_id: UUID | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        },
    )


class ChangePasswordRequest(BaseModel):
    """Password change request model."""

    current_password: str
    new_password: str
    confirm_password: str

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "current_password": "old_password123",
                "new_password": "new_secure_password456",
                "confirm_password": "new_secure_password456",
            }
        },
    )

    @model_validator(mode="after")
    def check_passwords_match(self) -> "ChangePasswordRequest":
        """Validate that new password matches confirmation."""
        if self.new_password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self

    @field_validator("new_password")
    @classmethod
    def validate_new_password_field(cls, v: str) -> str:
        """Validate new password meets strength requirements."""
        validate_password_or_raise(v)
        return v


class SuccessResponse(BaseModel):
    """Standardized success response model."""

    message: str

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "message": "Logged out successfully",
            }
        },
    )
