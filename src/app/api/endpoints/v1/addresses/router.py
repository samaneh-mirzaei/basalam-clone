from typing import Annotated

from fastapi import APIRouter, Path
from sqlalchemy import select

from app.api.dependencies import CurrentUser, SessionDep
from app.api.http import ContractRoute, created
from app.api.representations import address_data
from app.core.errors import APIError
from app.schemas.addresses.models import UserAddress
from app.schemas.addresses.requests import AddressWrite

router = APIRouter(tags=["Addresses"], route_class=ContractRoute)


@router.get("/users/me/addresses", summary="List my addresses", description="List the authenticated user's addresses, newest first. This owned collection is not paginated.")
def list_addresses(user: CurrentUser, session: SessionDep):
    addresses = session.scalars(select(UserAddress).where(UserAddress.user_id == user.id).order_by(UserAddress.created_at.desc(), UserAddress.id.desc())).all()
    return {"data": [address_data(address) for address in addresses]}


@router.post("/users/me/addresses", status_code=201, summary="Create an address", description="Create a shipping address for the authenticated user. All address fields are required. Returns 201 and Location.")
def create_address(body: AddressWrite, user: CurrentUser, session: SessionDep):
    address = UserAddress(user_id=user.id, **body.model_dump())
    session.add(address)
    session.commit()
    session.refresh(address)
    return created(address_data(address), f"/api/v1/users/me/addresses/{address.id}")


@router.get("/users/me/addresses/{address_id}", summary="Read my address", description="Read an owned address. An absent or another user's address returns the same 404.")
def get_address(address_id: Annotated[int, Path(gt=0)], user: CurrentUser, session: SessionDep):
    address = session.scalar(select(UserAddress).where(UserAddress.id == address_id, UserAddress.user_id == user.id))
    if address is None:
        raise APIError(404, "ADDRESS_NOT_FOUND", "Address not found.")
    return {"data": address_data(address)}
