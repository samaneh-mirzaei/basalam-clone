import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from random import randrange

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import unexpected_error
from app.data.session import engine
from app.main import app
from app.schemas.users.models import Cart, User, Wallet, WalletTransaction

requires_postgres = pytest.mark.skipif(not os.getenv("BASALAM_DATABASE_URL") or not os.getenv("BASALAM_JWT_SECRET"), reason="requires migrated disposable PostgreSQL")


def account(client, name):
    mobile = f"09{randrange(10**9):09d}"
    response = client.post("/api/v1/users", json={"mobile": mobile, "full_name": name, "password": "strong review password"})
    assert response.status_code == 201, response.text
    token = client.post("/api/v1/auth/tokens", json={"mobile": mobile, "password": "strong review password"}).json()["data"]["access_token"]
    return int(response.json()["data"]["user"]["id"]), mobile, {"Authorization": f"Bearer {token}"}


def make_staff(client):
    admin_id, _, admin = account(client, "Review Admin")
    operator_id, _, operator = account(client, "Review Operator")
    with Session(engine()) as session:
        session.get(User, admin_id).role = "admin"
        session.get(User, operator_id).role = "operator"
        session.commit()
    return admin, operator


def test_unexpected_errors_are_logged_without_leaking_details(caplog):
    request = Request({"type": "http", "method": "GET", "path": "/private", "headers": [], "query_string": b"", "scheme": "http", "server": ("test", 80)})
    request.state.request_id = "req_test123"
    with caplog.at_level("ERROR", logger="app.errors"):
        response = asyncio.run(unexpected_error(request, RuntimeError("private marker")))
    assert response.status_code == 500
    assert b"private marker" not in response.body
    assert b"req_test123" in response.body
    assert "private marker" in caplog.text
    assert "req_test123" in caplog.text


def test_liveness_is_independent_from_database_readiness(monkeypatch):
    class DownEngine:
        def connect(self):
            raise SQLAlchemyError("database private failure")

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        monkeypatch.setattr("app.main.engine", lambda: DownEngine())
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert "private failure" not in response.text


@requires_postgres
def test_order_receipt_is_private_and_admin_read_is_audited(caplog):
    with TestClient(app) as client:
        _, _, buyer = account(client, "Receipt Buyer")
        _, _, stranger = account(client, "Receipt Stranger")
        _, _, seller = account(client, "Receipt Seller")
        admin, operator = make_staff(client)
        assert client.get("/ready").json() == {"status": "ready"}
        shop = client.post("/api/v1/shops", headers=seller, json={"name": "Receipt Shop", "slug": f"receipt-{randrange(10**12)}", "shipping_fee": 1_000})
        assert shop.status_code == 201, shop.text
        product = client.post("/api/v1/shops/me/products", headers=seller, json={"title": "Receipt Item", "price": 10_000, "stock_quantity": 2, "status": "published"})
        assert product.status_code == 201, product.text
        product_id = product.json()["data"]["id"]
        address = client.post("/api/v1/users/me/addresses", headers=buyer, json={"recipient_name": "Buyer", "recipient_phone": "09123456789", "province": "Tehran", "city": "Tehran", "address_line": "Private address", "postal_code": "0123456789"})
        assert address.status_code == 201, address.text
        assert client.put(f"/api/v1/users/me/cart/items/{product_id}", headers=buyer, json={"quantity": 1}).status_code == 201
        paid = client.post("/api/v1/orders", headers=buyer, json={"checkout_key": f"privacy-{randrange(10**12)}", "address_id": address.json()["data"]["id"], "displayed_total": 11_000})
        assert paid.status_code == 201, paid.text
        order_id = paid.json()["data"]["id"]
        assert client.get(f"/api/v1/orders/{order_id}", headers=buyer).status_code == 200
        assert client.get(f"/api/v1/orders/{order_id}", headers=stranger).status_code == 404
        assert client.get(f"/api/v1/orders/{order_id}", headers=operator).status_code == 404
        with caplog.at_level("INFO", logger="app.audit"):
            staff_read = client.get(f"/api/v1/orders/{order_id}", headers=admin)
        assert staff_read.status_code == 200
        assert staff_read.json()["data"]["shipping_address"]["address_line"] == "Private address"
        assert f"order_id={order_id}" in caplog.text and "request_id=req_" in caplog.text
        assert "Private address" not in caplog.text


@requires_postgres
def test_staff_catalog_permissions_do_not_grant_product_ownership():
    with TestClient(app) as client:
        _, _, seller = account(client, "Moderation Seller")
        _, _, customer = account(client, "Moderation Customer")
        admin, operator = make_staff(client)
        shop = client.post("/api/v1/shops", headers=seller, json={"name": "Moderation Shop", "slug": f"moderation-{randrange(10**12)}"})
        assert shop.status_code == 201, shop.text
        shop_id = shop.json()["data"]["id"]
        product = client.post("/api/v1/shops/me/products", headers=seller, json={"title": "Private Draft", "price": 100, "stock_quantity": 1})
        assert product.status_code == 201, product.text
        product_id = product.json()["data"]["id"]
        assert client.get(f"/api/v1/products/{product_id}", headers=customer).status_code == 404
        assert client.get(f"/api/v1/products/{product_id}", headers=operator).status_code == 200
        assert client.get(f"/api/v1/products/{product_id}", headers=admin).status_code == 200
        detail = client.get(f"/api/v1/products/{product_id}", headers=operator)
        assert client.patch(f"/api/v1/products/{product_id}", headers={**operator, "If-Match": detail.headers["etag"], "Content-Type": "application/merge-patch+json"}, json={"title": "Unauthorized"}).status_code == 404
        shop_detail = client.get(f"/api/v1/shops/{shop_id}", headers=operator)
        suspended = client.patch(f"/api/v1/shops/{shop_id}", headers={**operator, "If-Match": shop_detail.headers["etag"], "Content-Type": "application/merge-patch+json"}, json={"status": "suspended"})
        assert suspended.status_code == 200, suspended.text
        assert client.get(f"/api/v1/shops/{shop_id}", headers=customer).status_code == 404
        assert client.get(f"/api/v1/shops/{shop_id}", headers=operator).status_code == 200
        assert client.get(f"/api/v1/shops/{shop_id}", headers=admin).status_code == 200
        assert client.patch(f"/api/v1/shops/{shop_id}", headers={**operator, "If-Match": suspended.headers["etag"], "Content-Type": "application/merge-patch+json"}, json={"name": "Unauthorized"}).status_code == 403


@requires_postgres
def test_admin_user_search_creation_and_access_controls():
    with TestClient(app) as client:
        admin, operator = make_staff(client)
        _, _, customer = account(client, "Review Customer")
        prefix = f"AdminSearch{randrange(10**9)}"
        created = []
        for role in ("operator", "admin"):
            mobile = f"09{randrange(10**9):09d}"
            response = client.post("/api/v1/admin/users", headers=admin, json={"mobile": mobile, "full_name": f"{prefix} {role}", "password": "created staff password", "role": role})
            assert response.status_code == 201, response.text
            assert "password_hash" not in response.text
            created.append((response.json()["data"]["user"]["id"], mobile, role))
            with Session(engine()) as session:
                user = session.get(User, int(created[-1][0]))
                wallet = session.query(Wallet).filter_by(user_id=user.id).one()
                assert session.query(Cart).filter_by(user_id=user.id).one()
                assert wallet.balance == 1_000_000
                assert session.query(WalletTransaction).filter_by(wallet_id=wallet.id, reason="initial_credit").count() == 1
        assert client.get("/api/v1/admin/users", headers=operator).status_code == 403
        assert client.get("/api/v1/admin/users", headers=customer).status_code == 403
        assert client.post("/api/v1/admin/users", headers=operator, json={"mobile": f"09{randrange(10**9):09d}", "full_name": "No", "password": "strong password", "role": "admin"}).status_code == 403
        first = client.get("/api/v1/admin/users", headers=admin, params={"name": prefix, "limit": 1}).json()
        assert len(first["data"]) == 1 and first["page"]["has_more"]
        second = client.get("/api/v1/admin/users", headers=admin, params={"name": prefix, "limit": 1, "cursor": first["page"]["next_cursor"]}).json()
        assert len(second["data"]) == 1 and second["data"][0]["id"] != first["data"][0]["id"]
        assert client.get("/api/v1/admin/users", headers=admin, params={"mobile": created[0][1]}).json()["data"][0]["id"] == created[0][0]
        assert client.get("/api/v1/admin/users", headers=admin, params={"name": prefix, "role": "admin"}).json()["data"][0]["id"] == created[1][0]
        assert client.get(f"/api/v1/admin/users/{created[0][0]}", headers=admin).status_code == 200
        assert client.post("/api/v1/admin/users", headers=admin, json={"mobile": created[0][1], "full_name": "Duplicate", "password": "strong password", "role": "admin"}).status_code == 409
        patch_headers = {**admin, "Content-Type": "application/merge-patch+json"}
        changed = client.patch(f"/api/v1/admin/users/{created[0][0]}", headers=patch_headers, json={"role": "customer", "is_active": False})
        assert changed.status_code == 200 and changed.json()["data"]["role"] == "customer"
        assert client.get("/api/v1/admin/users", headers=admin, params={"mobile": created[0][1], "is_active": False}).json()["data"][0]["id"] == created[0][0]
        assert client.patch(f"/api/v1/admin/users/{created[0][0]}", headers=patch_headers, json={"role": "operator", "is_active": True}).status_code == 200
        assert client.post("/api/v1/users", json={"mobile": f"09{randrange(10**9):09d}", "full_name": "No", "password": "strong password", "role": "operator"}).status_code == 422


@requires_postgres
def test_category_admin_validation_cycles_and_deactivation():
    with TestClient(app) as client:
        admin, operator = make_staff(client)
        _, _, customer = account(client, "Category Customer")
        _, _, seller = account(client, "Category Seller")
        prefix = f"review-{randrange(10**12)}"
        root_body = {"name": "Review Root", "slug": f"{prefix}-root"}
        assert client.post("/api/v1/categories", headers=customer, json=root_body).status_code == 403
        assert client.post("/api/v1/categories", headers=operator, json=root_body).status_code == 403
        root = client.post("/api/v1/categories", headers=admin, json=root_body)
        assert root.status_code == 201, root.text
        root_id = root.json()["data"]["id"]
        child = client.post("/api/v1/categories", headers=admin, json={"name": "Review Child", "slug": f"{prefix}-child", "parent_id": root_id})
        assert child.status_code == 201, child.text
        child_id = child.json()["data"]["id"]
        assert client.post("/api/v1/categories", headers=admin, json=root_body).json()["error"]["code"] == "CATEGORY_SLUG_EXISTS"
        assert client.post("/api/v1/categories", headers=admin, json={"name": "Orphan", "slug": f"{prefix}-orphan", "parent_id": 999999999}).status_code == 404
        patch_headers = {**admin, "Content-Type": "application/merge-patch+json"}
        assert client.patch(f"/api/v1/categories/{root_id}", headers=patch_headers, json={"parent_id": child_id}).json()["error"]["code"] == "CATEGORY_CYCLE"
        assert client.patch(f"/api/v1/categories/{root_id}", headers=patch_headers, json={"is_active": False}).json()["error"]["code"] == "CATEGORY_HAS_ACTIVE_CHILDREN"
        assert client.patch(f"/api/v1/categories/{child_id}", headers={**customer, "Content-Type": "application/merge-patch+json"}, json={"name": "Denied"}).status_code == 403
        shop = client.post("/api/v1/shops", headers=seller, json={"name": "Category Shop", "slug": f"{prefix}-shop"})
        assert shop.status_code == 201
        product = client.post("/api/v1/shops/me/products", headers=seller, json={"title": "Categorized", "price": 100, "stock_quantity": 1, "status": "published", "category_id": child_id})
        assert product.status_code == 201, product.text
        assert client.patch(f"/api/v1/categories/{child_id}", headers=patch_headers, json={"is_active": False}).status_code == 200
        assert client.get(f"/api/v1/categories/{child_id}").status_code == 404
        assert client.get(f"/api/v1/products/{product.json()['data']['id']}").json()["data"]["category_id"] == child_id
        assert client.post("/api/v1/shops/me/products", headers=seller, json={"title": "No inactive", "price": 1, "stock_quantity": 1, "category_id": child_id}).status_code == 404
        assert client.patch(f"/api/v1/categories/{root_id}", headers=patch_headers, json={"is_active": False}).status_code == 200
        assert client.get(f"/api/v1/categories/{root_id}").status_code == 404
        a = client.post("/api/v1/categories", headers=admin, json={"name": "Race A", "slug": f"{prefix}-race-a"}).json()["data"]["id"]
        b = client.post("/api/v1/categories", headers=admin, json={"name": "Race B", "slug": f"{prefix}-race-b"}).json()["data"]["id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(client.patch, f"/api/v1/categories/{target}", headers=patch_headers, json={"parent_id": parent}) for target, parent in ((a, b), (b, a))]
            outcomes = [future.result() for future in futures]
        assert sorted(response.status_code for response in outcomes) == [200, 409], [response.text for response in outcomes]
        assert next(response for response in outcomes if response.status_code == 409).json()["error"]["code"] == "CATEGORY_CYCLE"
