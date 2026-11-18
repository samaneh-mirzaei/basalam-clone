from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from app.api.http import StrictBody

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=1, max_length=50)]


class ShopWrite(StrictBody):
    name: str = Field(min_length=1, max_length=100)
    slug: Slug
    description: str | None = None
    shipping_fee: int = Field(default=0, ge=0)


class ShopPatch(StrictBody):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: Slug | None = None
    description: str | None = None
    shipping_fee: int | None = Field(default=None, ge=0)
    status: Literal["active", "closed", "suspended"] | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self
