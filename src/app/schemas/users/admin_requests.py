from typing import Literal

from pydantic import Field, model_validator

from app.api.http import StrictBody
from app.schemas.users.requests import Mobile


class PrivilegedAccountCreate(StrictBody):
    mobile: Mobile
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=1024)
    role: Literal["operator", "admin"]


class UserAccessPatch(StrictBody):
    role: Literal["customer", "operator", "admin"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Provide role or is_active; null is not allowed.")
        return self
