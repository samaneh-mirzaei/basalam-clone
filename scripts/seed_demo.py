"""Add local demo accounts and catalog records without changing existing data."""

import secrets
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.data.session import engine
from app.schemas.categories.models import Category
from app.schemas.products.models import Product
from app.schemas.shops.models import Shop
from app.schemas.users.models import Cart, User, Wallet, WalletTransaction

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = ROOT / ".demo-credentials"
ACCOUNTS = (
    ("buyer", "09000000011", "Demo Buyer", "customer"),
    ("seller", "09000000012", "Demo Seller", "customer"),
    ("operator", "09000000013", "Demo Operator", "operator"),
)


def require_local_database() -> None:
    url = make_url(settings().database_url.get_secret_value())
    if url.host not in ("127.0.0.1", "localhost") or url.database != "basalam":
        raise SystemExit("Demo seed is allowed only for a local PostgreSQL database named basalam.")


def get_or_create_user(session: Session, mobile: str, name: str, role: str, password: str) -> User:
    user = session.scalar(select(User).where(User.mobile == mobile))
    if user is not None:
        if user.full_name != name or user.role != role:
            raise SystemExit(f"Demo mobile {mobile} belongs to another account; no changes were committed.")
        return user
    user = User(mobile=mobile, full_name=name, role=role, password_hash=hash_password(password))
    session.add(user)
    session.flush()
    wallet = Wallet(user_id=user.id, balance=1_000_000)
    session.add(wallet)
    session.flush()
    session.add(WalletTransaction(wallet_id=wallet.id, reason="initial_credit", amount=1_000_000, balance_after=1_000_000))
    session.add(Cart(user_id=user.id))
    return user


def category(session: Session, slug: str, name: str, parent_id: int | None = None) -> Category:
    row = session.scalar(select(Category).where(Category.slug == slug))
    if row is None:
        row = Category(slug=slug, name=name, parent_id=parent_id)
        session.add(row)
        session.flush()
    return row


def main() -> None:
    require_local_database()
    existing_credentials = CREDENTIALS.exists()
    if existing_credentials:
        password = CREDENTIALS.read_text(encoding="utf-8").split("password=", 1)[1].splitlines()[0]
    else:
        password = secrets.token_urlsafe(18)

    with Session(engine()) as session:
        if session.scalar(text("SELECT version_num FROM alembic_version")) != "0002_full_design":
            raise SystemExit("Run uv run alembic upgrade head before seeding.")
        if not existing_credentials and session.scalar(select(User.id).where(User.mobile.in_([account[1] for account in ACCOUNTS])).limit(1)):
            raise SystemExit("Demo accounts already exist but .demo-credentials is missing; refusing to reset their passwords.")
        with session.begin_nested():
            users = {label: get_or_create_user(session, mobile, name, role, password) for label, mobile, name, role in ACCOUNTS}
            shop = session.scalar(select(Shop).where(Shop.slug == "demo-ceramics"))
            if shop is None:
                shop = Shop(owner_id=users["seller"].id, name="Demo Ceramics", slug="demo-ceramics", description="Practice catalog for the Basalam API", shipping_fee=25_000)
                session.add(shop)
                session.flush()
            elif shop.owner_id != users["seller"].id:
                raise SystemExit("Demo shop slug belongs to another owner; no changes were committed.")

            home = category(session, "demo-home", "Demo Home")
            mugs = category(session, "demo-mugs", "Demo Mugs", home.id)
            for title, price, stock, status in (
                ("Demo Blue Mug", 120_000, 8, "published"),
                ("Demo Red Mug", 135_000, 3, "published"),
                ("Demo Tea Plate", 95_000, 0, "published"),
                ("Demo Draft Cup", 110_000, 5, "draft"),
            ):
                if session.scalar(select(Product.id).where(Product.shop_id == shop.id, Product.title == title)) is None:
                    session.add(Product(shop_id=shop.id, category_id=mugs.id, title=title, description=f"{title} for API testing", price=price, stock_quantity=stock, status=status))
        session.commit()

    if not existing_credentials:
        CREDENTIALS.write_text(
            "Local demo accounts (use only on this machine)\n"
            + "\n".join(f"{label}: {mobile}" for label, mobile, _, _ in ACCOUNTS)
            + f"\npassword={password}\n",
            encoding="utf-8",
        )
    print("Demo records are ready. Read .demo-credentials for the mobile numbers and password.")


if __name__ == "__main__":
    main()
