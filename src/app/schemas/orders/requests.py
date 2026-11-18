from pydantic import Field, StrictInt

from app.api.http import BigintId, StrictBody


class CheckoutRequest(StrictBody):
    checkout_key: str = Field(min_length=1, max_length=64)
    address_id: BigintId
    displayed_total: StrictInt = Field(gt=0)
