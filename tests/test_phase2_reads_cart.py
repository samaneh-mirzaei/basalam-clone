import os
from concurrent.futures import ThreadPoolExecutor
from random import randrange

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.skipif(not os.getenv("BASALAM_DATABASE_URL") or not os.getenv("BASALAM_JWT_SECRET"), reason="requires migrated disposable PostgreSQL")
def test_addresses_wallet_cart_and_saved_items():
    with TestClient(app) as client:
        def account(label):
            mobile = f"09{randrange(10**9):09d}"
            response = client.post("/api/v1/users", json={"mobile": mobile, "full_name": label, "password": "strong demo password"})
            assert response.status_code == 201, response.text
            token = client.post("/api/v1/auth/tokens", json={"mobile": mobile, "password": "strong demo password"}).json()["data"]["access_token"]
            return {"Authorization": f"Bearer {token}"}

        buyer = account("Buyer")
        seller = account("Seller")
        shop = client.post("/api/v1/shops", headers=seller, json={"name": "Test Shop", "slug": f"test-shop-{randrange(10**9)}", "shipping_fee": 25_000})
        assert shop.status_code == 201
        products = []
        for title, stock in (("Test Mug", 5), ("Test Plate", 2)):
            response = client.post("/api/v1/shops/me/products", headers=seller, json={"title": title, "price": 100_000, "stock_quantity": stock, "status": "published"})
            assert response.status_code == 201
            products.append(response.json()["data"]["id"])

        address_body = {"recipient_name": "Buyer", "recipient_phone": "+123456789012345", "province": "Tehran", "city": "Tehran", "address_line": "Example 1", "postal_code": "0123456789"}
        address = client.post("/api/v1/users/me/addresses", headers=buyer, json=address_body)
        assert address.status_code == 201, address.text
        address_id = address.json()["data"]["id"]
        assert address.headers["location"].endswith(f"/addresses/{address_id}")
        assert client.get(f"/api/v1/users/me/addresses/{address_id}", headers=buyer).json()["data"]["postal_code"] == "0123456789"
        assert address.json()["data"]["recipient_phone"] == "+123456789012345"
        assert len(client.get("/api/v1/users/me/addresses", headers=buyer).json()["data"]) == 1
        assert client.get(f"/api/v1/users/me/addresses/{address_id}", headers=seller).status_code == 404
        assert client.post("/api/v1/users/me/addresses", headers=buyer, json={**address_body, "postal_code": "123"}).status_code == 422

        wallet = client.get("/api/v1/users/me/wallet", headers=buyer)
        assert wallet.json()["data"]["balance"] == 1_000_000
        assert wallet.headers["cache-control"] == "private, no-store"
        ledger = client.get("/api/v1/users/me/wallet/transactions", headers=buyer)
        assert ledger.json()["data"][0]["reason"] == "initial_credit"
        assert ledger.json()["data"][0]["balance_after"] == 1_000_000
        assert client.get("/api/v1/users/me/wallet/transactions", headers=buyer, params={"reason": "order_refund"}).json()["data"] == []

        first_saved = client.put(f"/api/v1/users/me/saved-items/{products[0]}", headers=buyer)
        assert first_saved.status_code == 201, first_saved.text
        assert client.put(f"/api/v1/users/me/saved-items/{products[0]}", headers=buyer).status_code == 200
        assert client.put(f"/api/v1/users/me/saved-items/{products[1]}", headers=buyer).status_code == 201
        page = client.get("/api/v1/users/me/saved-items", headers=buyer, params={"limit": 1}).json()
        assert page["page"]["has_more"]
        following = client.get("/api/v1/users/me/saved-items", headers=buyer, params={"limit": 1, "cursor": page["page"]["next_cursor"]})
        assert following.status_code == 200
        assert following.json()["data"][0]["id"] != page["data"][0]["id"]

        item = client.put(f"/api/v1/users/me/cart/items/{products[0]}", headers=buyer, json={"quantity": 2})
        assert item.status_code == 201, item.text
        assert client.put(f"/api/v1/users/me/cart/items/{products[0]}", headers=buyer, json={"quantity": 2}).status_code == 200
        assert client.put(f"/api/v1/users/me/saved-items/{products[0]}", headers=buyer).status_code == 409
        cart = client.get("/api/v1/users/me/cart", headers=buyer)
        assert cart.json()["data"]["item_subtotal"] == 200_000
        assert cart.json()["data"]["estimated_shipping"] == 25_000
        assert cart.json()["data"]["displayed_total"] == 225_000
        assert len(client.get("/api/v1/users/me/saved-items", headers=buyer).json()["data"]) == 1
        assert client.put(f"/api/v1/users/me/cart/items/{products[1]}", headers=seller, json={"quantity": 1}).status_code == 409
        assert client.put(f"/api/v1/users/me/cart/items/{products[1]}", headers=buyer, json={"quantity": 999}).status_code == 409
        product_detail = client.get(f"/api/v1/products/{products[0]}", headers=seller)
        hidden = client.patch(
            f"/api/v1/products/{products[0]}",
            headers={**seller, "If-Match": product_detail.headers["etag"], "Content-Type": "application/merge-patch+json"},
            content='{"status":"hidden"}',
        )
        assert hidden.status_code == 200
        unavailable = client.get("/api/v1/users/me/cart", headers=buyer).json()["data"]["items"][0]
        assert unavailable["product"]["available"] is False
        assert unavailable["product_id"] == products[0]
        assert client.delete(f"/api/v1/users/me/cart/items/{products[0]}", headers=buyer).status_code == 204
        assert client.delete(f"/api/v1/users/me/cart/items/{products[0]}", headers=buyer).status_code == 204
        assert client.delete(f"/api/v1/users/me/saved-items/{products[1]}", headers=buyer).status_code == 204
        assert client.delete(f"/api/v1/users/me/saved-items/{products[1]}", headers=buyer).status_code == 204
        with ThreadPoolExecutor(max_workers=2) as executor:
            cart_write = executor.submit(client.put, f"/api/v1/users/me/cart/items/{products[1]}", headers=buyer, json={"quantity": 1})
            saved_write = executor.submit(client.put, f"/api/v1/users/me/saved-items/{products[1]}", headers=buyer)
            assert cart_write.result().status_code == 201
            assert saved_write.result().status_code in (201, 409)
        assert all(row["product"]["id"] != products[1] for row in client.get("/api/v1/users/me/saved-items", headers=buyer).json()["data"])
        assert any(row["product_id"] == products[1] for row in client.get("/api/v1/users/me/cart", headers=buyer).json()["data"]["items"])
