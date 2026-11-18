from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError

from app.api.catalog import decode_cursor, encode_cursor, page_response
from app.api.dependencies import CurrentUser, SessionDep, has_operator_access
from app.api.http import ContractRoute
from app.core.errors import APIError
from app.schemas.orders.models import Order
from app.schemas.orders.requests import CheckoutRequest
from app.services.orders.checkout import checkout, checkout_hash, prior_order
from app.services.orders.queries import order_data, order_summary

router = APIRouter(tags=["Orders"], route_class=ContractRoute)


@router.post("/orders", responses={201: {"description": "Order paid and created"}}, summary="Pay for my cart", description="Create an order from your current cart using wallet funds. Supply an owned address, current displayed cart total, and a unique checkout key. Stock, snapshots, debit, payment and cart clearing commit together. Repeating the same key and payload returns the original receipt with 200; changing the payload returns 409.")
def create_order(body: CheckoutRequest, user: CurrentUser, session: SessionDep):
    try:
        order, created = checkout(session, user, body.checkout_key, body.address_id, body.displayed_total)
        session.commit()
    except IntegrityError:
        session.rollback()
        order = prior_order(session, user.id, body.checkout_key, checkout_hash(body.address_id, body.displayed_total))
        if order is None:
            raise
        created = False
    data = order_data(session, order)
    headers = {"Cache-Control": "private, no-store"}
    if created:
        headers["Location"] = f"/api/v1/orders/{order.id}"
    return JSONResponse({"data": data}, status_code=201 if created else 200, headers=headers)


@router.get("/users/me/orders", summary="List my orders", description="List owned order receipts newest first. Filter by paid or cancelled status and placed date range. Use limit (1–100) and next_cursor for pagination. Totals and parcel counts use purchased snapshots.")
def list_orders(request: Request, user: CurrentUser, session: SessionDep, status: Literal["paid", "cancelled"] | None = None, placed_from: datetime | None = None, placed_to: datetime | None = None, cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    if (placed_from is not None and placed_from.tzinfo is None) or (placed_to is not None and placed_to.tzinfo is None):
        raise APIError(422, "VALIDATION_FAILED", "Dates must include a timezone.")
    if placed_from is not None and placed_to is not None and placed_from > placed_to:
        raise APIError(422, "VALIDATION_FAILED", "placed_from must not exceed placed_to.")
    filters = {"customer_id": user.id, "status": status, "placed_from": placed_from.isoformat() if placed_from else None, "placed_to": placed_to.isoformat() if placed_to else None}
    marker = decode_cursor(cursor, filters)
    query = select(Order).where(Order.customer_id == user.id)
    if status is not None:
        query = query.where(Order.status == status)
    if placed_from is not None:
        query = query.where(Order.placed_at >= placed_from)
    if placed_to is not None:
        query = query.where(Order.placed_at <= placed_to)
    if marker:
        try:
            query = query.where(tuple_(Order.placed_at, Order.id) < (datetime.fromisoformat(marker[0]), int(marker[1])))
        except (IndexError, ValueError, TypeError) as exc:
            raise APIError(400, "INVALID_CURSOR", "Invalid orders cursor.") from exc
    rows = session.scalars(query.order_by(Order.placed_at.desc(), Order.id.desc()).limit(limit + 1)).all()
    last = rows[limit - 1] if len(rows) > limit else None
    next_cursor = encode_cursor(filters, [last.placed_at.isoformat(), last.id]) if last else None
    return page_response(request, [order_summary(session, order) for order in rows[:limit]], limit, next_cursor, private=True)


@router.get("/orders/{order_id}", summary="Read an order receipt", description="Return the complete purchased address, item and fee snapshots, payment, parcel states, and linked return and refund summaries. Only the customer or an operator may read it; other users receive 404.")
def get_order(order_id: Annotated[int, Path(gt=0)], user: CurrentUser, session: SessionDep):
    order = session.get(Order, order_id)
    if order is None or (order.customer_id != user.id and not has_operator_access(user)):
        raise APIError(404, "ORDER_NOT_FOUND", "Order not found.")
    return JSONResponse({"data": order_data(session, order)}, headers={"Cache-Control": "private, no-store"})
