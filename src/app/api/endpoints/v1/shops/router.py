from typing import Annotated

from fastapi import APIRouter, Body, Header, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.catalog import catalog_response, decode_cursor, encode_cursor, page_response, tag
from app.api.dependencies import CurrentUser, OptionalUser, SessionDep, can_moderate_shops, require_operator
from app.api.http import ContractRoute, created, supplied_patch_fields
from app.api.representations import shop_data
from app.core.errors import APIError
from app.schemas.shops.models import Shop
from app.schemas.shops.requests import ShopPatch, ShopWrite

router = APIRouter(route_class=ContractRoute)


@router.get(
    "/shops",
    tags=["Shops"],
    summary="Browse visible shops",
    description="List active shops, newest first. Use `q` to search names and `limit` (1–100) with the returned `next_cursor` to page forward. Operators can supply `status` to inspect active, closed, or suspended shops. Public results support an ETag and `If-None-Match` for 304 responses.",
)
def list_shops(request: Request, session: SessionDep, user: OptionalUser, q: str | None = None, status: str | None = None, cursor: str | None = None, limit: int = 20):
    if not 1 <= limit <= 100:
        raise APIError(422, "VALIDATION_FAILED", "Limit must be between 1 and 100.")
    if status:
        require_operator(user)
    if status and status not in ("active", "closed", "suspended"):
        raise APIError(422, "VALIDATION_FAILED", "Invalid shop status.")
    filters = {"q": q, "status": status}
    marker = decode_cursor(cursor, filters)
    query = select(Shop)
    if status:
        query = query.where(Shop.status == status)
    else:
        query = query.where(Shop.status == "active")
    if q:
        query = query.where(Shop.name.ilike(f"%{q}%"))
    if marker:
        from datetime import datetime
        query = query.where((Shop.created_at < datetime.fromisoformat(marker[0])) | ((Shop.created_at == datetime.fromisoformat(marker[0])) & (Shop.id < marker[1])))
    rows = session.scalars(query.order_by(Shop.created_at.desc(), Shop.id.desc()).limit(limit + 1)).all()
    next_cursor = encode_cursor(filters, [rows[limit - 1].created_at.isoformat(), rows[limit - 1].id]) if len(rows) > limit else None
    return page_response(request, [shop_data(row) for row in rows[:limit]], limit, next_cursor, private=bool(status))


@router.post(
    "/shops",
    status_code=201,
    tags=["Shops"],
    summary="Create my shop",
    description="Requires a Bearer token. A user may own one shop. Provide a name and lowercase URL-safe slug; description and nonnegative shipping fee are optional. The new shop starts active. Returns 201 with Location; duplicate owner or slug returns 409.",
)
def create_shop(body: ShopWrite, user: CurrentUser, session: SessionDep):
    shop = Shop(owner_id=user.id, **body.model_dump())
    try:
        session.add(shop)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        code = "USER_ALREADY_HAS_SHOP" if session.scalar(select(Shop.id).where(Shop.owner_id == user.id)) else "SHOP_SLUG_EXISTS"
        raise APIError(409, code, "Shop already exists.") from exc
    session.refresh(shop)
    return created(shop_data(shop), f"/api/v1/shops/{shop.id}")


@router.get(
    "/shops/me",
    tags=["Shops"],
    summary="Read my shop",
    description="Requires a Bearer token. Returns the authenticated owner's shop, including a closed or suspended shop, with an ETag for later updates. Returns 404 when the user has no shop.",
)
def my_shop(request: Request, user: CurrentUser, session: SessionDep):
    shop = session.scalar(select(Shop).where(Shop.owner_id == user.id))
    if shop is None:
        raise APIError(404, "SHOP_NOT_FOUND", "Shop not found.")
    return catalog_response(request, shop_data(shop), tag("shop", shop.id, shop.version), private=True)


@router.get(
    "/shops/{shop_id}",
    tags=["Shops"],
    summary="Read a shop",
    description="Guests see active shops only. The owner and operators can also read a closed or suspended shop. Returns an ETag; public callers may send `If-None-Match` for 304. Missing or concealed shops return 404.",
)
def get_shop(shop_id: int, request: Request, session: SessionDep, user: OptionalUser):
    shop = session.get(Shop, shop_id)
    if shop is None or (shop.status != "active" and (user is None or (user.id != shop.owner_id and not can_moderate_shops(user)))):
        raise APIError(404, "SHOP_NOT_FOUND", "Shop not found.")
    private = bool(user and (user.id == shop.owner_id or can_moderate_shops(user)))
    return catalog_response(request, shop_data(shop), tag("shop", shop.id, shop.version), private)


@router.patch(
    "/shops/{shop_id}",
    tags=["Shops"],
    summary="Update shop details or status",
    description="Requires a Bearer token, `Content-Type: application/merge-patch+json`, and the current shop `If-Match` ETag from GET. Owners edit metadata and may close or reopen their unsuspended shop. Operators may suspend or reactivate shops. Missing If-Match returns 428; a stale tag returns 412; an invalid status transition returns 409.",
)
def update_shop(shop_id: int, body: Annotated[ShopPatch, Body(media_type="application/merge-patch+json")], user: CurrentUser, session: SessionDep, if_match: Annotated[str | None, Header()] = None):
    if if_match is None:
        raise APIError(428, "PRECONDITION_REQUIRED", "If-Match is required.")
    shop = session.scalar(select(Shop).where(Shop.id == shop_id).with_for_update())
    if shop is None or (user.id != shop.owner_id and not can_moderate_shops(user)):
        raise APIError(404, "SHOP_NOT_FOUND", "Shop not found.")
    if if_match != tag("shop", shop.id, shop.version):
        raise APIError(412, "PRECONDITION_FAILED", "Shop has changed.")
    changes = supplied_patch_fields(body)
    if "status" in changes:
        allowed = {("active", "closed"), ("closed", "active")} if user.id == shop.owner_id else {("active", "suspended"), ("closed", "suspended"), ("suspended", "active")}
        if (shop.status, body.status) not in allowed:
            raise APIError(409, "INVALID_SHOP_STATUS_TRANSITION", "Invalid shop status transition.")
    if any(field != "status" for field in changes) and user.id != shop.owner_id:
        raise APIError(403, "OPERATOR_REQUIRED", "Only the shop owner can edit metadata.")
    for field, value in changes.items():
        if value is None and field != "description":
            raise APIError(422, "VALIDATION_FAILED", f"{field} cannot be null.")
        setattr(shop, field, value)
    shop.version += 1
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise APIError(409, "SHOP_SLUG_EXISTS", "Shop slug already exists.") from exc
    session.refresh(shop)
    return catalog_response_for_write(shop)


def catalog_response_for_write(shop: Shop):
    from fastapi.responses import JSONResponse
    return JSONResponse({"data": shop_data(shop)}, headers={"ETag": tag("shop", shop.id, shop.version), "Cache-Control": "private, no-store"})
