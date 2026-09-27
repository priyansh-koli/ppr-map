"""Registration, sign-in and account shapes (docs/api.md, Auth and Me)."""

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.models.enums import County, PropertyInterest, UserType
from app.schemas.base import ApiModel, Money


class Policies(ApiModel):
    terms_version: str
    privacy_version: str


class Profile(ApiModel):
    user_type: UserType | None = None
    counties: list[County] | None = None
    budget_min: Money | None = Field(None, ge=0)
    budget_max: Money | None = Field(None, ge=0)
    property_interest: PropertyInterest | None = None


class RegisterIn(ApiModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str
    age18_plus: Literal[True] = Field(alias="age18Plus")
    accept_terms: Literal[True]
    terms_version: str
    privacy_version: str
    profile: Profile | None = None
    marketing_opt_in: bool = False


class LoginIn(ApiModel):
    email: EmailStr
    password: str = Field(max_length=1000)


class TokenIn(ApiModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(ApiModel):
    email: EmailStr


class ResetIn(ApiModel):
    token: str = Field(min_length=10, max_length=200)
    password: str


class PasswordChangeIn(ApiModel):
    current_password: str = Field(max_length=1000)
    new_password: str


class PasswordIn(ApiModel):
    password: str = Field(max_length=1000)


class Accepted(ApiModel):
    """202 answers never say whether an account exists."""

    status: Literal["accepted"] = "accepted"
    message: str


class Me(ApiModel):
    id: str
    email: str
    full_name: str
    email_verified: bool
    history_enabled: bool
    marketing_opt_in: bool
    roles: list[str]
    permissions: list[str]
    profile: Profile
    created_at: datetime


class MePatch(ApiModel):
    full_name: str | None = Field(None, min_length=1, max_length=200)
    history_enabled: bool | None = None
    marketing_opt_in: bool | None = None
    profile: Profile | None = None
