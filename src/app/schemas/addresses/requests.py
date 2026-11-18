from pydantic import Field

from app.api.http import StrictBody


class AddressWrite(StrictBody):
    recipient_name: str = Field(min_length=1, max_length=100)
    recipient_phone: str = Field(min_length=10, max_length=16, pattern=r"^\+?[0-9]{10,15}$")
    province: str = Field(min_length=1, max_length=50)
    city: str = Field(min_length=1, max_length=50)
    address_line: str = Field(min_length=1, max_length=300)
    postal_code: str = Field(pattern=r"^[0-9]{10}$")
