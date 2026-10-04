from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, computed_field, field_validator
from uuid import UUID

from mkobi.models.enums import UserRole
from mkobi.utils.validators import validate_password_or_raise


class UserBase(BaseModel):
    """Base user model."""

    email: EmailStr
    role: UserRole

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "role": UserRole.VIEWER,
            }
        },
    )


class UserCreate(UserBase):
    """Model for creating new user."""

    password: str

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
        """Refuse a password the hasher cannot represent (SECB-10)."""
        validate_password_or_raise(v)
        return v


class UserRead(UserBase):
    """Model for reading user data (without password)."""

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None
    force_password_change: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_name(self) -> str:
        """Derive display name from email prefix (text before @)."""
        email_str = self.email.split("@")[0]
        assert isinstance(email_str, str)
        return email_str

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "role": UserRole.VIEWER,
                "created_at": "2026-04-24T16:02:46+03:00",
                "updated_at": "2026-04-24T16:02:46+03:00",
            }
        },
    )


class UserDB(UserBase):
    """User model for database (with password hash)."""

    id: UUID
    password_hash: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "email": "user@example.com",
                "password_hash": "$2b$12$examplehash",
                "role": UserRole.VIEWER,
                "created_at": "2026-04-24T16:02:46+03:00",
                "updated_at": "2026-04-24T16:02:46+03:00",
            }
        },
    )


class UserUpdate(BaseModel):
    """Model for updating user."""

    email: EmailStr | None = None
    role: UserRole | None = None
    password: str | None = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "email": "newemail@example.com",
                "role": UserRole.EDITOR,
                "password": "new_secure_password",
            }
        },
    )

    @field_validator("password")
    @classmethod
    def validate_password_field(cls, v: str | None) -> str | None:
        """Refuse a password the hasher cannot represent (SECB-10)."""
        if v is not None:
            validate_password_or_raise(v)
        return v


class UserCreateRequest(BaseModel):
    """Request model for creating a new user."""

    email: EmailStr
    password: str
    role: UserRole

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
        """Refuse a password the hasher cannot represent (SECB-10)."""
        validate_password_or_raise(v)
        return v


class UserUpdateRequest(BaseModel):
    """Request model for updating user role."""

    role: UserRole

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "role": UserRole.EDITOR,
            }
        },
    )


class UserUpdateActiveRequest(BaseModel):
    """Request model for updating user active status."""

    is_active: bool

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "is_active": False,
            }
        },
    )
