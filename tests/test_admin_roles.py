import os
import runpy
from pathlib import Path
from random import randrange

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import has_operator_access, require_admin, require_customer, require_operator
from app.core.security import verify_password
from app.data.session import engine
from app.main import app
from app.schemas.users.models import Cart, User, Wallet, WalletTransaction
seed = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py"))
ACCOUNTS = seed["ACCOUNTS"]
get_or_create_user = seed["get_or_create_user"]


def test_role_dependencies():
    assert next(role for label, _, _, role in ACCOUNTS if label == "operator") == "operator"
    assert next(role for label, _, _, role in ACCOUNTS if label == "admin") == "admin"
    customer = User(role="customer")
    operator = User(role="operator")
    admin = User(role="admin")
    for user in (customer, operator, admin):
        assert require_customer(user) is user
    for user in (operator, admin):
        assert require_operator(user) is user
    assert require_admin(admin) is admin
    assert has_operator_access(operator) and has_operator_access(admin)
    with pytest.raises(HTTPException) as customer_denied:
        require_operator(customer)
    assert customer_denied.value.status_code == 403
    for user in (customer, operator):
        with pytest.raises(HTTPException) as denied:
            require_admin(user)
        assert denied.value.status_code == 403


requires_postgres = pytest.mark.skipif(not os.getenv("BASALAM_DATABASE_URL") or not os.getenv("BASALAM_JWT_SECRET"), reason="requires migrated disposable PostgreSQL")


def account(client, name):
    mobile = f"09{randrange(10**9):09d}"
    response = client.post("/api/v1/users", json={"mobile": mobile, "full_name": name, "password": "strong demo password"})
    assert response.status_code == 201, response.text
    token = client.post("/api/v1/auth/tokens", json={"mobile": mobile, "password": "strong demo password"}).json()["data"]["access_token"]
    return int(response.json()["data"]["user"]["id"]), {"Authorization": f"Bearer {token}"}


@requires_postgres
def test_admin_operator_and_customer_access():
    with TestClient(app) as client:
        customer_id, customer = account(client, "Customer")
        operator_id, operator = account(client, "Operator")
        admin_id, admin = account(client, "Admin")
        seller_id, seller = account(client, "Seller")
        with Session(engine()) as session:
            session.get(User, operator_id).role = "operator"
            session.get(User, admin_id).role = "admin"
            session.commit()

        assert client.get("/api/v1/shops", headers=customer, params={"status": "active"}).status_code == 403
        assert client.get("/api/v1/shops", headers=operator, params={"status": "active"}).status_code == 200
        assert client.get("/api/v1/shops", headers=admin, params={"status": "active"}).status_code == 200
        assert client.get(f"/api/v1/admin/users/{customer_id}", headers=customer).status_code == 403
        assert client.get(f"/api/v1/admin/users/{customer_id}", headers=operator).status_code == 403
        assert client.get(f"/api/v1/admin/users/{customer_id}", headers=admin).json()["data"]["role"] == "customer"
        assert client.patch(f"/api/v1/admin/users/{admin_id}", headers={**admin, "Content-Type": "application/merge-patch+json"}, json={"role": "customer"}).status_code == 403
        promotion = client.patch(f"/api/v1/admin/users/{customer_id}", headers={**admin, "Content-Type": "application/merge-patch+json"}, json={"role": "operator"})
        assert promotion.status_code == 200, promotion.text
        assert client.get("/api/v1/shops", headers=customer, params={"status": "active"}).status_code == 200
        assert client.patch(f"/api/v1/admin/users/{seller_id}", headers={**operator, "Content-Type": "application/merge-patch+json"}, json={"role": "admin"}).status_code == 403
        assert client.patch("/api/v1/users/me", headers={**operator, "Content-Type": "application/merge-patch+json"}, json={"role": "admin"}).status_code == 422
        assert client.post("/api/v1/users", json={"mobile": f"09{randrange(10**9):09d}", "full_name": "Bad", "password": "strong demo password", "role": "admin"}).status_code == 422
        assert client.post("/api/v1/users", json={"mobile": f"09{randrange(10**9):09d}", "full_name": "Bad", "password": "strong demo password", "role": "operator"}).status_code == 422

        shop = client.post("/api/v1/shops", headers=seller, json={"name": "Role Shop", "slug": f"roles-{randrange(10**12)}", "shipping_fee": 25_000})
        assert shop.status_code == 201, shop.text
        item = client.post("/api/v1/shops/me/products", headers=seller, json={"title": "Role Mug", "price": 100_000, "stock_quantity": 4, "status": "published"})
        assert item.status_code == 201, item.text
        product_id = item.json()["data"]["id"]

        for headers in (operator, admin):
            wallet = client.get("/api/v1/users/me/wallet", headers=headers)
            assert wallet.status_code == 200 and wallet.json()["data"]["balance"] == 1_000_000
            assert client.get("/api/v1/users/me/wallet/transactions", headers=headers).json()["data"][0]["reason"] == "initial_credit"
            assert client.put(f"/api/v1/users/me/saved-items/{product_id}", headers=headers).status_code == 201
            moved = client.post("/api/v1/users/me/item-transfers", headers=headers, json={"product_id": product_id, "source": "saved", "destination": "cart"})
            assert moved.status_code == 200, moved.text
            assert client.get("/api/v1/users/me/cart", headers=headers).json()["data"]["displayed_total"] == 125_000
            address = client.post("/api/v1/users/me/addresses", headers=headers, json={"recipient_name": "Buyer", "recipient_phone": "09123456789", "province": "Tehran", "city": "Tehran", "address_line": "Example 1", "postal_code": "0123456789"})
            assert address.status_code == 201, address.text
            assert len(client.get("/api/v1/users/me/addresses", headers=headers).json()["data"]) == 1
            receipt = client.post("/api/v1/orders", headers=headers, json={"checkout_key": f"roles-{randrange(10**12)}", "address_id": address.json()["data"]["id"], "displayed_total": 125_000})
            assert receipt.status_code == 201, receipt.text
            order_id = receipt.json()["data"]["id"]
            assert client.get(f"/api/v1/orders/{order_id}", headers=headers).status_code == 200
            assert client.get("/api/v1/users/me/orders", headers=headers).json()["data"][0]["id"] == order_id


@requires_postgres
@pytest.mark.parametrize("role", ["operator", "admin"])
def test_seed_privileged_accounts_keep_wallet_cart_and_existing_password(role):
    mobile = f"09{randrange(10**9):09d}"
    with Session(engine()) as session:
        user = get_or_create_user(session, mobile, f"Seed {role}", role, "first password")
        session.commit()
        user_id = user.id
    with Session(engine()) as session:
        same = get_or_create_user(session, mobile, f"Seed {role}", role, "different password")
        assert same.id == user_id
        assert same.role == role
        assert verify_password(same.password_hash, "first password")
        assert not verify_password(same.password_hash, "different password")
        wallet = session.scalar(select(Wallet).where(Wallet.user_id == user_id))
        assert wallet.balance == 1_000_000
        assert session.scalar(select(Cart.id).where(Cart.user_id == user_id)) is not None
        entries = session.scalars(select(WalletTransaction).where(WalletTransaction.wallet_id == wallet.id)).all()
        assert len(entries) == 1 and entries[0].reason == "initial_credit"
