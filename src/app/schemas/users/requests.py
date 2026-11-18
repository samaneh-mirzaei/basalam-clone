from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from app.api.http import StrictBody

Mobile = Annotated[str, StringConstraints(pattern=r"^09[0-9]{9}$")]


class Registration(StrictBody):
    mobile: Mobile
    full_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=1024)


class Credentials(StrictBody):
    mobile: Mobile
    password: str


class ProfilePatch(StrictBody):
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=1024)

    @model_validator(mode="after")
    def valid_change(self):
        fields = self.model_fields_set
        if not fields or ("current_password" in fields) != ("new_password" in fields):
            raise ValueError("Provide a name or both password fields.")
        if "full_name" in fields and self.full_name is None:
            raise ValueError("Name cannot be null.")
        return self
