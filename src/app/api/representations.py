from datetime import datetime, timezone

from app.schemas.categories.models import Category
from app.schemas.products.models import Product
from app.schemas.shops.models import Shop
from app.schemas.users.models import User, Wallet
from app.schemas.users.models import WalletTransaction
from app.schemas.addresses.models import UserAddress


def timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def user_data(user: User) -> dict:
    return {"id": str(user.id), "mobile": user.mobile, "full_name": user.full_name, "role": user.role, "is_active": user.is_active, "created_at": timestamp(user.created_at)}


def wallet_data(wallet: Wallet) -> dict:
    return {"id": str(wallet.id), "balance": wallet.balance, "currency": "TOMAN", "updated_at": timestamp(wallet.updated_at)}


def wallet_transaction_data(entry: WalletTransaction) -> dict:
    return {"id": str(entry.id), "reason": entry.reason, "reference_id": str(entry.reference_id) if entry.reference_id is not None else None, "amount": entry.amount, "balance_after": entry.balance_after, "note": entry.note, "created_at": timestamp(entry.created_at)}


def address_data(address: UserAddress) -> dict:
    return {"id": str(address.id), "recipient_name": address.recipient_name, "recipient_phone": address.recipient_phone, "province": address.province, "city": address.city, "address_line": address.address_line, "postal_code": address.postal_code, "created_at": timestamp(address.created_at)}


def shop_data(shop: Shop) -> dict:
    return {"id": str(shop.id), "owner_id": str(shop.owner_id), "name": shop.name, "slug": shop.slug, "description": shop.description, "shipping_fee": shop.shipping_fee, "status": shop.status, "created_at": timestamp(shop.created_at)}


def category_data(category: Category) -> dict:
    return {"id": category.id, "parent_id": category.parent_id, "name": category.name, "slug": category.slug}


def product_data(product: Product, images: list[dict] | None = None) -> dict:
    return {"id": str(product.id), "shop_id": str(product.shop_id), "category_id": product.category_id, "title": product.title, "description": product.description, "price": product.price, "stock_quantity": product.stock_quantity, "status": product.status, "images": images or [], "created_at": timestamp(product.created_at), "updated_at": timestamp(product.updated_at)}
