import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """Shared user fields."""
    email: EmailStr
    name: str | None = None
    preferred_language: str = "en"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    name: str | None = None
    avatar_url: str | None = None
    preferred_language: str | None = None


class UserOut(UserBase):
    id: uuid.UUID
    avatar_url: str | None
    is_active: bool
    is_verified: bool
    totp_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}
