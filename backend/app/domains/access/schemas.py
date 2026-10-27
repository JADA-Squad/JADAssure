import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["admin", "analyst", "approver", "commercial", "executive"]
BusinessType = Literal["professional_services", "subscription_software", "distribution", "other"]

Password = Field(min_length=10, max_length=128)


class SignupIn(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    business_type: BusinessType = "other"
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Password


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    short_code: str
    business_type: str
    is_demo: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    role: Role
    active: bool
    created_at: datetime


class MeOut(BaseModel):
    user: UserOut
    organization: OrgOut
    capabilities: list[str]


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    me: MeOut


class UserCreateIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=200)
    role: Role
    password: str = Password


class UserUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    role: Role | None = None
    active: bool | None = None
