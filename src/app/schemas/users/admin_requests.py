from typing import Literal

from pydantic import model_validator

from app.api.http import StrictBody


class UserAccessPatch(StrictBody):
    role: Literal["customer", "operator", "admin"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Provide role or is_active; null is not allowed.")
        return self
