from pydantic import Field

from app.api.http import StrictBody


class CartQuantity(StrictBody):
    quantity: int = Field(ge=1)
