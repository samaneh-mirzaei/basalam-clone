from typing import Literal

from app.api.http import BigintId, StrictBody


class ItemTransfer(StrictBody):
    product_id: BigintId
    source: Literal["cart", "saved"]
    destination: Literal["cart", "saved"]
