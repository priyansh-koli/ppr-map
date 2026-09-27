"""Registration, sign-in and account shapes (docs/api.md, Auth and Me)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import EmailStr, Field, StringConstraints, field_validator, model_validator

from app.models.enums import County, PropertyInterest, UserType
from app.schemas.base import ApiModel, Money


class Policies(ApiModel):
    terms_version: str
    privacy_version: str


# A display name: trimmed, and no control characters (it is quoted in emails).
Name = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
# user_profile budgets are numeric(12, 2).
BUDGET_MAX = Decimal("9999999999.99")


class Profile(ApiModel):
    user_type: UserType | None = None
    counties: list[County] | None = None
    budget_min: Money | None = Field(None, ge=0, le=BUDGET_MAX, decimal_places=2)
    budget_max: Money | None = Field(None, ge=0, le=BUDGET_MAX, decimal_places=2)
    property_interest: PropertyInterest | None = None


def _check_budget(profile: Profile | None) -> None:
    """Checked on input only, so a stored profile always loads."""
    low, high = (profile.budget_min, profile.budget_max) if profile else (None, None)
    if low is not None and high is not None and low > high:
        raise ValueError("budgetMin must not be more than budgetMax")


class RegisterIn(ApiModel):
    full_name: Name
    email: EmailStr
    password: str
    age18_plus: Literal[True] = Field(alias="age18Plus")
    accept_terms: Literal[True]
    terms_version: str
    privacy_version: str
    profile: Profile | None = None
    marketing_opt_in: bool = False

    @model_validator(mode="after")
    def _budget_order(self) -> Self:
        _check_budget(self.profile)
        return self


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
    """Only the fields sent are changed; within `profile`, too."""

    full_name: Name | None = None
    history_enabled: bool | None = None
    marketing_opt_in: bool | None = None
    profile: Profile | None = None

    @field_validator("full_name", "history_enabled", "marketing_opt_in", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # Omit a field to leave it alone; null is not a value for any of these.
        if value is None:
            raise ValueError("must not be null")
        return value

    @model_validator(mode="after")
    def _budget_order(self) -> Self:
        _check_budget(self.profile)
        return self
