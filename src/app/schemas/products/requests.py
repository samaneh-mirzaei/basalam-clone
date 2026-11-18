from typing import Literal

from pydantic import Field, model_validator

from app.api.http import StrictBody

Status = Literal["draft", "published", "hidden", "archived"]


class ProductWrite(StrictBody):
    category_id: int | None = None
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    price: int = Field(ge=0)
    stock_quantity: int = Field(ge=0)
    status: Status = "draft"


class ProductPatch(StrictBody):
    category_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    price: int | None = Field(default=None, ge=0)
    stock_quantity: int | None = Field(default=None, ge=0)
    status: Status | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self
