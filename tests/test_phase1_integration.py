import os
from random import randrange

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.data.session import engine
from app.main import app
from app.schemas.users.models import Cart, User, Wallet, WalletTransaction


@pytest.mark.skipif(not os.getenv("BASALAM_DATABASE_URL") or not os.getenv("BASALAM_JWT_SECRET"), reason="requires migrated disposable PostgreSQL and JWT secret")
def test_phase1_journey():
    mobile = f"09{randrange(10**9):09d}"
    with TestClient(app) as client:
        signup = client.post("/api/v1/users", json={"mobile": mobile, "full_name": "Sara", "password": "correct horse battery staple"})
        assert signup.status_code == 201, signup.text
        user_id = int(signup.json()["data"]["user"]["id"])
        assert signup.json()["data"]["wallet"]["balance"] == 1_000_000
        assert client.post("/api/v1/users", json={"mobile": mobile, "full_name": "Sara", "password": "correct horse battery staple"}).status_code == 409
        with engine().connect() as connection:
            assert connection.scalar(select(Cart.id).where(Cart.user_id == user_id))
            wallet_id = connection.scalar(select(Wallet.id).where(Wallet.user_id == user_id))
            assert connection.scalar(select(WalletTransaction.amount).where(WalletTransaction.wallet_id == wallet_id)) == 1_000_000
        token = client.post("/api/v1/auth/tokens", json={"mobile": mobile, "password": "correct horse battery staple"})
        assert token.status_code == 200, token.text
        headers = {"Authorization": "Bearer " + token.json()["data"]["access_token"]}
        assert client.get("/api/v1/users/me", headers=headers).json()["data"]["id"] == str(user_id)
        shop = client.post("/api/v1/shops", headers=headers, json={"name": "Blue Pottery", "slug": f"blue-{user_id}"})
        assert shop.status_code == 201, shop.text
        shop_id = shop.json()["data"]["id"]
        public_shop = client.get(f"/api/v1/shops/{shop_id}")
        assert public_shop.status_code == 200
        assert client.get(f"/api/v1/shops/{shop_id}", headers={"If-None-Match": public_shop.headers["etag"]}).status_code == 304
        product = client.post("/api/v1/shops/me/products", headers=headers, json={"title": "Mug", "price": 100, "stock_quantity": 2, "status": "published"})
        assert product.status_code == 201, product.text
        product_id = product.json()["data"]["id"]
        assert client.get(f"/api/v1/products/{product_id}").status_code == 200
        assert any(row["id"] == product_id for row in client.get("/api/v1/products", params={"q": "Mug"}).json()["data"])
        detail = client.get(f"/api/v1/products/{product_id}", headers=headers)
        update = client.patch(f"/api/v1/products/{product_id}", headers={**headers, "If-Match": detail.headers["etag"], "Content-Type": "application/merge-patch+json"}, content='{"status":"hidden"}')
        assert update.status_code == 200, update.text
        assert client.get(f"/api/v1/products/{product_id}").status_code == 404
        assert client.get(f"/api/v1/products/{product_id}", headers=headers).status_code == 200
        assert client.patch(f"/api/v1/products/{product_id}", headers={**headers, "If-Match": detail.headers["etag"], "Content-Type": "application/merge-patch+json"}, content='{"title":"New"}').status_code == 412
        second_mobile = f"09{randrange(10**9):09d}"
        second = client.post("/api/v1/users", json={"mobile": second_mobile, "full_name": "Other", "password": "correct horse battery staple"})
        assert second.status_code == 201
        second_token = client.post("/api/v1/auth/tokens", json={"mobile": second_mobile, "password": "correct horse battery staple"}).json()["data"]["access_token"]
        other_headers = {"Authorization": "Bearer " + second_token}
        assert client.patch(f"/api/v1/products/{product_id}", headers={**other_headers, "If-Match": update.headers["etag"], "Content-Type": "application/merge-patch+json"}, content='{"title":"Stolen"}').status_code == 404
        assert client.patch(f"/api/v1/shops/{shop_id}", headers={**other_headers, "If-Match": public_shop.headers["etag"], "Content-Type": "application/merge-patch+json"}, content='{"name":"Stolen"}').status_code == 404
        assert client.get("/api/v1/shops/me", headers=other_headers).status_code == 404
        assert client.post("/api/v1/shops/me/products", headers=other_headers, json={"title": "Stolen", "price": 1, "stock_quantity": 1}).status_code == 404
        assert client.patch(f"/api/v1/products/{product_id}", headers={**headers, "If-Match": update.headers["etag"]}, json={"title":"Wrong media"}).status_code == 415
        public_list = client.get("/api/v1/shops")
        assert public_list.headers["etag"]
        assert client.get("/api/v1/shops", headers={"If-None-Match": public_list.headers["etag"]}).status_code == 304
        assert client.get("/api/v1/categories").json()["data"] == []
        assert client.get("/api/v1/categories", params={"format": "flat"}).json()["data"] == []
        assert client.get("/api/v1/categories/999999").status_code == 404
        second_product = client.post("/api/v1/shops/me/products", headers=headers, json={"title": "Plate", "price": 200, "stock_quantity": 0, "status": "published"})
        assert second_product.status_code == 201
        third_product = client.post("/api/v1/shops/me/products", headers=headers, json={"title": "Cup", "price": 300, "stock_quantity": 1, "status": "published"})
        assert third_product.status_code == 201
        first_page = client.get("/api/v1/products", params={"limit": 1, "shop_id": shop_id})
        assert first_page.json()["page"]["has_more"]
        next_page = client.get("/api/v1/products", params={"limit": 1, "shop_id": shop_id, "cursor": first_page.json()["page"]["next_cursor"]})
        assert next_page.status_code == 200
        assert next_page.json()["data"][0]["id"] != first_page.json()["data"][0]["id"]
        assert client.get("/api/v1/products", params={"limit": 1, "q": "Plate", "cursor": first_page.json()["page"]["next_cursor"]}).status_code == 400
        assert client.get("/api/v1/products", params={"in_stock": "false"}).json()["data"][0]["id"] == second_product.json()["data"]["id"]
        owner_shop = client.get("/api/v1/shops/me", headers=headers)
        closed = client.patch(f"/api/v1/shops/{shop_id}", headers={**headers, "If-Match": owner_shop.headers["etag"], "Content-Type": "application/merge-patch+json"}, content='{"status":"closed"}')
        assert closed.status_code == 200
        assert client.get(f"/api/v1/shops/{shop_id}").status_code == 404
        assert client.get(f"/api/v1/shops/{shop_id}", headers=headers).status_code == 200
        assert client.get(f"/api/v1/products/{second_product.json()['data']['id']}").status_code == 404
        assert client.post("/api/v1/shops/me/products", headers=headers, json={"title": "No", "price": 1, "stock_quantity": 1, "status": "published"}).status_code == 409
