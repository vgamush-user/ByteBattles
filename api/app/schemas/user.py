from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime

import re

USERNAME_REGEX = r"^[a-zA-Z0-9_]{3,20}$"
PASSWORD_REGEX = r"^(?=.*[A-Za-z])(?=.*\d).{8,}$"

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    conf_password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if not re.match(USERNAME_REGEX, v):
            raise ValueError(
                "Username must be 3–20 chars and contain only letters, numbers, underscores"
            )
        return v
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                "Password must be at least 8 chars and include letters + numbers"
            )
        return v

class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    conf_password: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if v is None:
            return v
        if not re.match(USERNAME_REGEX, v):
            raise ValueError(
                "Username must be 3–20 chars and contain only letters, numbers, underscores"
            )
        return v
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if v is None:
            return v
        if not re.match(PASSWORD_REGEX, v):
            raise ValueError(
                "Password must be at least 8 chars and include letters + numbers"
            )
        return v

from shared.models import UserType

class UserResponseUnknown(BaseModel):
    username: str
    is_verified: bool
    created_at: datetime

    
    model_config = {
      "from_attributes": True
    }

class UserResponse(BaseModel):
    username: str
    email: EmailStr
    is_verified: bool
    user_type: UserType = UserType.USER
    created_at: datetime

    model_config = {
      "from_attributes": True
    }

class RoleUpdate(BaseModel):
    user_type: UserType

class TokenPayload(BaseModel):
    sub: int

class RefreshAccessTokenRequest(BaseModel):
    refresh_token: str