import hashlib
import json

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.schemas.addresses.models import UserAddress
from app.schemas.cart.models import CartItem
from app.schemas.orders.models import Order, Payment
from app.schemas.parcels.models import OrderItem, OrderParcel
from app.schemas.products.models import Product
from app.schemas.shops.models import Shop
from app.schemas.users.models import User
from app.services.cart.service import locked_cart
from app.services.wallets.posting import debit_order


def checkout_hash(address_id: str, displayed_total: int) -> str:
    payload = json.dumps({"address_id": address_id, "displayed_total": displayed_total}, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prior_order(session: Session, customer_id: int, checkout_key: str, request_hash: str) -> Order | None:
    order = session.scalar(select(Order).where(Order.customer_id == customer_id, Order.checkout_key == checkout_key))
    if order is not None and order.request_hash != request_hash:
        raise APIError(409, "CHECKOUT_KEY_REUSED", "Checkout key was used for a different request.")
    return order


def checkout(session: Session, user: User, checkout_key: str, address_id: str, displayed_total: int) -> tuple[Order, bool]:
    request_hash = checkout_hash(address_id, displayed_total)
    original = prior_order(session, user.id, checkout_key, request_hash)
    if original is not None:
        return original, False

    cart = locked_cart(session, user.id)
    original = prior_order(session, user.id, checkout_key, request_hash)
    if original is not None:
        return original, False
    lines = session.scalars(select(CartItem).where(CartItem.cart_id == cart.id).order_by(CartItem.product_id)).all()
    if not lines:
        raise APIError(409, "EMPTY_CART", "Cart is empty.")

    address = session.scalar(select(UserAddress).where(UserAddress.id == int(address_id), UserAddress.user_id == user.id).with_for_update(read=True, key_share=True))
    if address is None:
        raise APIError(404, "ADDRESS_NOT_FOUND", "Address not found.")

    # Shop metadata can change during checkout. Lock it before products, in a stable order.
    product_shops = session.execute(select(Product.id, Product.shop_id).where(Product.id.in_([line.product_id for line in lines]))).all()
    shop_ids = sorted({shop_id for _, shop_id in product_shops})
    shops = {}
    for shop_id in shop_ids:
        shop = session.scalar(select(Shop).where(Shop.id == shop_id).with_for_update(read=True))
        if shop is not None:
            shops[shop_id] = shop
    products = {}
    for line in lines:
        product = session.scalar(select(Product).where(Product.id == line.product_id).with_for_update())
        if product is None:
            raise APIError(409, "PRODUCT_NOT_BUYABLE", "A cart product is no longer buyable.")
        products[line.product_id] = product

    subtotal = 0
    used_shops = set()
    for line in lines:
        product = products[line.product_id]
        shop = shops.get(product.shop_id)
        if shop is None or shop.status != "active" or product.status != "published":
            raise APIError(409, "PRODUCT_NOT_BUYABLE", "A cart product is no longer buyable.")
        if shop.owner_id == user.id:
            raise APIError(409, "SELF_PURCHASE_NOT_ALLOWED", "You cannot buy your own product.")
        if product.stock_quantity < line.quantity:
            raise APIError(409, "INSUFFICIENT_STOCK", "A cart product has insufficient stock.")
        subtotal += product.price * line.quantity
        used_shops.add(shop.id)
    total = subtotal + sum(shops[shop_id].shipping_fee for shop_id in used_shops)
    if total != displayed_total:
        raise APIError(409, "CHECKOUT_TOTAL_CHANGED", "The cart total changed before checkout.", [{"displayed_total": displayed_total, "current_total": total}])

    order = Order(
        customer_id=user.id, checkout_key=checkout_key, request_hash=request_hash, total_amount=total,
        ship_recipient_name=address.recipient_name, ship_recipient_phone=address.recipient_phone,
        ship_province=address.province, ship_city=address.city, ship_address_line=address.address_line,
        ship_postal_code=address.postal_code,
    )
    session.add(order)
    session.flush()
    parcels = {}
    for shop_id in sorted(used_shops):
        parcel = OrderParcel(order_id=order.id, shop_id=shop_id, shipping_fee=shops[shop_id].shipping_fee)
        session.add(parcel)
        session.flush()
        parcels[shop_id] = parcel
    for line in lines:
        product = products[line.product_id]
        result = session.execute(update(Product).where(Product.id == product.id, Product.stock_quantity >= line.quantity, Product.status == "published").values(stock_quantity=Product.stock_quantity - line.quantity, version=Product.version + 1, updated_at=func.now()))
        if result.rowcount != 1:
            raise APIError(409, "INSUFFICIENT_STOCK", "A cart product has insufficient stock.")
        session.add(OrderItem(parcel_id=parcels[product.shop_id].id, shop_id=product.shop_id, product_id=product.id, product_title=product.title, unit_price=product.price, quantity=line.quantity))
    entry = debit_order(session, user.id, order.id, total)
    session.add(Payment(order_id=order.id, wallet_transaction_id=entry.id, amount=total))
    session.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    cart.updated_at = func.now()
    session.flush()
    return order, True
