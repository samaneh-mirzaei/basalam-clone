from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.representations import timestamp
from app.core.errors import APIError
from app.schemas.cart.models import CartItem, SavedItem
from app.schemas.products.models import Product
from app.schemas.shops.models import Shop
from app.schemas.users.models import Cart, User


def locked_cart(session: Session, user_id: int) -> Cart:
    cart = session.scalar(select(Cart).where(Cart.user_id == user_id).with_for_update())
    if cart is None:
        raise APIError(404, "CART_NOT_FOUND", "Cart not found.")
    return cart


def buyable_product(session: Session, product_id: int, user: User, quantity: int) -> Product:
    row = session.execute(select(Product, Shop).join(Shop, Shop.id == Product.shop_id).where(Product.id == product_id)).first()
    if row is None:
        raise APIError(404, "PRODUCT_NOT_FOUND", "Product not found.")
    product, shop = row
    if product.status != "published" or shop.status != "active":
        raise APIError(409, "PRODUCT_NOT_BUYABLE", "Product is not currently buyable.")
    if shop.owner_id == user.id:
        raise APIError(409, "SELF_PURCHASE_NOT_ALLOWED", "You cannot add your own product.")
    if product.stock_quantity < quantity:
        raise APIError(409, "INSUFFICIENT_STOCK", "Requested quantity exceeds current stock.")
    return product


def cart_summary(session: Session, cart: Cart, user_id: int) -> dict:
    rows = session.execute(
        select(CartItem, Product, Shop)
        .join(Product, Product.id == CartItem.product_id)
        .join(Shop, Shop.id == Product.shop_id)
        .where(CartItem.cart_id == cart.id)
        .order_by(CartItem.added_at, CartItem.id)
    ).all()
    items = []
    subtotal = 0
    shipping_by_shop = {}
    for item, product, shop in rows:
        available = product.status == "published" and shop.status == "active" and shop.owner_id != user_id and product.stock_quantity >= item.quantity
        summary = {"id": str(product.id), "available": available}
        if available:
            summary.update({"title": product.title, "price": product.price})
            subtotal += product.price * item.quantity
            shipping_by_shop[shop.id] = shop.shipping_fee
        items.append({"id": str(item.id), "product_id": str(product.id), "quantity": item.quantity, "product": summary})
    shipping = sum(shipping_by_shop.values())
    return {"id": str(cart.id), "items": items, "item_subtotal": subtotal, "estimated_shipping": shipping, "displayed_total": subtotal + shipping, "updated_at": timestamp(cart.updated_at)}


def put_item(session: Session, user: User, product_id: int, quantity: int) -> tuple[CartItem, Cart, bool]:
    cart = locked_cart(session, user.id)
    buyable_product(session, product_id, user, quantity)
    item = session.scalar(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == product_id))
    created = item is None
    if created:
        item = CartItem(cart_id=cart.id, product_id=product_id, quantity=quantity)
        session.add(item)
    else:
        item.quantity = quantity
    session.execute(delete(SavedItem).where(SavedItem.user_id == user.id, SavedItem.product_id == product_id))
    cart.updated_at = func.now()
    session.flush()
    return item, cart, created


def remove_item(session: Session, user: User, product_id: int) -> None:
    cart = locked_cart(session, user.id)
    result = session.execute(delete(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == product_id))
    if result.rowcount:
        cart.updated_at = func.now()


def save_item(session: Session, user: User, product_id: int) -> tuple[SavedItem, bool]:
    cart = locked_cart(session, user.id)
    if session.scalar(select(CartItem.id).where(CartItem.cart_id == cart.id, CartItem.product_id == product_id)) is not None:
        raise APIError(409, "PRODUCT_IN_CART", "Remove the product from your cart before saving it.")
    item = session.scalar(select(SavedItem).where(SavedItem.user_id == user.id, SavedItem.product_id == product_id))
    if item is not None:
        return item, False
    product = session.scalar(select(Product).join(Shop, Shop.id == Product.shop_id).where(Product.id == product_id, Product.status == "published", Shop.status == "active"))
    if product is None:
        raise APIError(404, "PRODUCT_NOT_FOUND", "Product not found.")
    item = SavedItem(user_id=user.id, product_id=product_id)
    session.add(item)
    session.flush()
    return item, True


def remove_saved_item(session: Session, user: User, product_id: int) -> None:
    locked_cart(session, user.id)
    session.execute(delete(SavedItem).where(SavedItem.user_id == user.id, SavedItem.product_id == product_id))


def transfer_item(session: Session, user: User, product_id: int, source: str, destination: str) -> dict:
    cart = locked_cart(session, user.id)
    item = session.scalar(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == product_id))
    saved = session.scalar(select(SavedItem).where(SavedItem.user_id == user.id, SavedItem.product_id == product_id))
    if source == "cart" and item is not None:
        session.delete(item)
        session.flush()
        if saved is None:
            saved = SavedItem(user_id=user.id, product_id=product_id)
            session.add(saved)
        cart.updated_at = func.now()
        item = None
    elif source == "saved" and saved is not None:
        buyable_product(session, product_id, user, item.quantity if item is not None else 1)
        session.delete(saved)
        session.flush()
        if item is None:
            item = CartItem(cart_id=cart.id, product_id=product_id, quantity=1)
            session.add(item)
        cart.updated_at = func.now()
        saved = None
    elif (destination == "cart" and item is None) or (destination == "saved" and saved is None):
        raise APIError(404, "ITEM_TRANSFER_SOURCE_NOT_FOUND", "Source item not found.")
    session.flush()
    return {
        "product_id": str(product_id), "source": source, "destination": destination,
        "cart_item": {"id": str(item.id), "product_id": str(product_id), "quantity": item.quantity, "added_at": timestamp(item.added_at)} if item is not None else None,
        "saved_item": {"id": str(saved.id), "product_id": str(product_id), "saved_at": timestamp(saved.saved_at)} if saved is not None else None,
    }
