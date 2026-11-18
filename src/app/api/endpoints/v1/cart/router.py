from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select, tuple_

from app.api.catalog import decode_cursor, encode_cursor, page_response
from app.api.dependencies import CurrentUser, SessionDep
from app.api.http import ContractRoute
from app.api.representations import timestamp
from app.core.errors import APIError
from app.schemas.cart.models import SavedItem
from app.schemas.cart.requests import CartQuantity
from app.schemas.cart.transfers import ItemTransfer
from app.schemas.products.models import Product
from app.schemas.shops.models import Shop
from app.schemas.users.models import Cart
from app.services.cart.service import cart_summary, put_item, remove_item, remove_saved_item, save_item, transfer_item

router = APIRouter(tags=["Cart and saved items"], route_class=ContractRoute)
ProductId = Annotated[int, Path(gt=0)]


def saved_data(item: SavedItem, product: Product, shop: Shop) -> dict:
    available = product.status == "published" and shop.status == "active"
    summary = {"id": str(product.id), "available": available}
    if available:
        summary.update({"title": product.title, "price": product.price})
    return {"id": str(item.id), "saved_at": timestamp(item.saved_at), "product": summary}


@router.get("/users/me/cart", summary="Read my cart", description="Return current cart items and estimated subtotal, shipping and total. Unbuyable items remain identifiable but show available=false. Checkout will revalidate prices and stock.")
def get_cart(user: CurrentUser, session: SessionDep):
    cart = session.scalar(select(Cart).where(Cart.user_id == user.id))
    if cart is None:
        raise APIError(404, "CART_NOT_FOUND", "Cart not found.")
    return {"data": cart_summary(session, cart, user.id)}


@router.put("/users/me/cart/items/{product_id}", responses={201: {"description": "Cart item created"}}, summary="Set a cart item's quantity", description="Create or replace quantity for a published product in an active shop. Requires current stock and forbids buying from your own shop. Removes the same product from saved items atomically. Returns 201 on first add, otherwise 200.")
def set_cart_item(product_id: ProductId, body: CartQuantity, user: CurrentUser, session: SessionDep):
    item, cart, created = put_item(session, user, product_id, body.quantity)
    session.commit()
    summary = cart_summary(session, cart, user.id)
    data = {"item": next(row for row in summary["items"] if row["product_id"] == str(product_id)), "cart": summary}
    headers = {"Cache-Control": "private, no-store"}
    if created:
        headers["Location"] = f"/api/v1/users/me/cart/items/{product_id}"
    return JSONResponse({"data": data}, status_code=201 if created else 200, headers=headers)


@router.delete("/users/me/cart/items/{product_id}", status_code=204, summary="Remove a cart item", description="Remove this product from your cart. Deleting an absent item also returns 204.")
def delete_cart_item(product_id: ProductId, user: CurrentUser, session: SessionDep):
    remove_item(session, user, product_id)
    session.commit()
    return Response(status_code=204)


@router.get("/users/me/saved-items", summary="List my saved products", description="List saved products newest first, with current availability. Use limit (1–100) and the returned cursor for the next page. Hidden or unavailable products remain removable without exposing private product details.")
def list_saved_items(request: Request, user: CurrentUser, session: SessionDep, cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    filters = {"user_id": user.id}
    marker = decode_cursor(cursor, filters)
    query = select(SavedItem, Product, Shop).join(Product, Product.id == SavedItem.product_id).join(Shop, Shop.id == Product.shop_id).where(SavedItem.user_id == user.id)
    if marker:
        try:
            cursor_time = datetime.fromisoformat(marker[0])
            cursor_id = int(marker[1])
        except (IndexError, TypeError, ValueError) as exc:
            raise APIError(400, "INVALID_CURSOR", "Invalid saved-items cursor.") from exc
        query = query.where(tuple_(SavedItem.saved_at, SavedItem.id) < (cursor_time, cursor_id))
    rows = session.execute(query.order_by(SavedItem.saved_at.desc(), SavedItem.id.desc()).limit(limit + 1)).all()
    last = rows[limit - 1][0] if len(rows) > limit else None
    next_cursor = encode_cursor(filters, [last.saved_at.isoformat(), last.id]) if last else None
    return page_response(request, [saved_data(*row) for row in rows[:limit]], limit, next_cursor, private=True)


@router.put("/users/me/saved-items/{product_id}", responses={201: {"description": "Saved item created"}}, summary="Save a product", description="Save a visible product idempotently. Returns 201 with Location when newly saved or 200 on replay. A product currently in the cart returns 409 PRODUCT_IN_CART. This PUT has no request body.")
def put_saved_item(product_id: ProductId, user: CurrentUser, session: SessionDep):
    item, created = save_item(session, user, product_id)
    session.commit()
    row = session.execute(select(SavedItem, Product, Shop).join(Product, Product.id == SavedItem.product_id).join(Shop, Shop.id == Product.shop_id).where(SavedItem.id == item.id)).one()
    headers = {"Cache-Control": "private, no-store"}
    if created:
        headers["Location"] = f"/api/v1/users/me/saved-items/{product_id}"
    return JSONResponse({"data": saved_data(*row)}, status_code=201 if created else 200, headers=headers)


@router.delete("/users/me/saved-items/{product_id}", status_code=204, summary="Remove a saved product", description="Remove a product from saved items. Deleting an absent item also returns 204.")
def delete_saved_item(product_id: ProductId, user: CurrentUser, session: SessionDep):
    remove_saved_item(session, user, product_id)
    session.commit()
    return Response(status_code=204)


@router.post("/users/me/item-transfers", summary="Move a product between cart and saved items", description="Atomically move one owned product from cart to saved items or back. A matching replay returns the current destination state. Moving to cart validates visibility, stock and self-purchase rules.")
def create_item_transfer(body: ItemTransfer, user: CurrentUser, session: SessionDep):
    if body.source == body.destination:
        raise APIError(422, "INVALID_TRANSFER", "Source and destination must differ.")
    data = transfer_item(session, user, int(body.product_id), body.source, body.destination)
    session.commit()
    return JSONResponse({"data": data}, headers={"Cache-Control": "private, no-store"})
