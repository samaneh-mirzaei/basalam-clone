from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.representations import timestamp
from app.schemas.orders.models import Order, Payment
from app.schemas.parcels.models import OrderItem, OrderParcel
from app.schemas.refunds.models import Refund
from app.schemas.returns.models import ReturnRequest


def optional_time(value):
    return timestamp(value) if value is not None else None


def order_summary(session: Session, order: Order) -> dict:
    parcels = session.scalars(select(OrderParcel).where(OrderParcel.order_id == order.id)).all()
    counts = {}
    for parcel in parcels:
        counts[parcel.status] = counts.get(parcel.status, 0) + 1
    return {"id": str(order.id), "status": order.status, "total_amount": order.total_amount, "currency": "TOMAN", "placed_at": timestamp(order.placed_at), "updated_at": timestamp(order.updated_at), "parcel_status_counts": counts}


def order_data(session: Session, order: Order) -> dict:
    payment = session.scalar(select(Payment).where(Payment.order_id == order.id))
    parcels = session.scalars(select(OrderParcel).where(OrderParcel.order_id == order.id).order_by(OrderParcel.id)).all()
    parcel_data = []
    for parcel in parcels:
        items = session.scalars(select(OrderItem).where(OrderItem.parcel_id == parcel.id).order_by(OrderItem.id)).all()
        returns = session.scalars(select(ReturnRequest).where(ReturnRequest.parcel_id == parcel.id).order_by(ReturnRequest.id)).all()
        refunds = session.scalars(select(Refund).where(Refund.parcel_id == parcel.id).order_by(Refund.id)).all()
        parcel_data.append({
            "id": str(parcel.id), "shop_id": str(parcel.shop_id), "shipping_fee": parcel.shipping_fee,
            "status": parcel.status, "tracking_code": parcel.tracking_code,
            "items": [{"id": str(item.id), "product_id": str(item.product_id), "product_title": item.product_title, "unit_price": item.unit_price, "quantity": item.quantity} for item in items],
            "return_requests": [{"id": str(row.id), "parcel_id": str(row.parcel_id), "reason_text": row.reason_text, "status": row.status, "response_note": row.response_note, "created_at": timestamp(row.created_at), "decided_at": optional_time(row.decided_at)} for row in returns],
            "refunds": [{"id": str(row.id), "parcel_id": str(row.parcel_id), "amount": row.amount, "reason": row.reason, "return_request_id": str(row.return_request_id) if row.return_request_id is not None else None, "created_at": timestamp(row.created_at)} for row in refunds],
            "created_at": timestamp(parcel.created_at), "updated_at": timestamp(parcel.updated_at),
            "shipped_at": optional_time(parcel.shipped_at), "delivered_at": optional_time(parcel.delivered_at),
            "cancelled_at": optional_time(parcel.cancelled_at), "settled_at": optional_time(parcel.settled_at),
        })
    return {
        "id": str(order.id), "status": order.status, "total_amount": order.total_amount, "currency": "TOMAN",
        "shipping_address": {"recipient_name": order.ship_recipient_name, "recipient_phone": order.ship_recipient_phone,
                             "province": order.ship_province, "city": order.ship_city, "address_line": order.ship_address_line,
                             "postal_code": order.ship_postal_code},
        "parcels": parcel_data,
        "payment": {"id": str(payment.id), "method": payment.method, "amount": payment.amount, "created_at": timestamp(payment.created_at)} if payment is not None else None,
        "placed_at": timestamp(order.placed_at), "updated_at": timestamp(order.updated_at), "cancelled_at": optional_time(order.cancelled_at),
    }
