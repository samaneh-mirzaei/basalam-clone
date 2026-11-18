import os
from concurrent.futures import ThreadPoolExecutor
from random import randrange
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.session import engine
from app.main import app
from app.schemas.cart.models import CartItem
from app.schemas.orders.models import Order, Payment
from app.schemas.products.models import Product
from app.schemas.parcels.models import OrderItem
from app.schemas.users.models import Cart, Wallet, WalletTransaction
from app.services.wallets.posting import debit_order
from app.core.errors import APIError

pytestmark = pytest.mark.skipif(not os.getenv("BASALAM_DATABASE_URL") or not os.getenv("BASALAM_JWT_SECRET"), reason="requires migrated disposable PostgreSQL")


def account(client, name):
    mobile = f"09{randrange(10**9):09d}"
    created = client.post("/api/v1/users", json={"mobile": mobile, "full_name": name, "password": "strong demo password"})
    assert created.status_code == 201, created.text
    token = client.post("/api/v1/auth/tokens", json={"mobile": mobile, "password": "strong demo password"}).json()["data"]["access_token"]
    return int(created.json()["data"]["user"]["id"]), {"Authorization": f"Bearer {token}"}


def address(client, headers):
    response = client.post("/api/v1/users/me/addresses", headers=headers, json={"recipient_name": "Buyer", "recipient_phone": "09123456789", "province": "Tehran", "city": "Tehran", "address_line": "Example 1", "postal_code": "0123456789"})
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def product(client, seller, price=100_000, stock=3, shipping=25_000):
    shop = client.post("/api/v1/shops", headers=seller, json={"name": "Shop", "slug": f"checkout-{randrange(10**12)}", "shipping_fee": shipping})
    assert shop.status_code == 201, shop.text
    response = client.post("/api/v1/shops/me/products", headers=seller, json={"title": "Snapshot Mug", "price": price, "stock_quantity": stock, "status": "published"})
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def add(client, buyer, product_id, quantity=1):
    response = client.put(f"/api/v1/users/me/cart/items/{product_id}", headers=buyer, json={"quantity": quantity})
    assert response.status_code in (200, 201), response.text


def checkout_body(key, address_id, total):
    return {"checkout_key": key, "address_id": address_id, "displayed_total": total}


def test_transfer_checkout_replay_failures_and_receipt():
    with TestClient(app) as client:
        buyer_id, buyer = account(client, "Buyer")
        _, other = account(client, "Other")
        _, seller = account(client, "Seller")
        product_id = product(client, seller)
        address_id = address(client, buyer)
        add(client, buyer, product_id, 2)
        transfer = {"product_id": product_id, "source": "cart", "destination": "saved"}
        moved = client.post("/api/v1/users/me/item-transfers", headers=buyer, json=transfer)
        assert moved.status_code == 200, moved.text
        assert moved.json()["data"]["cart_item"] is None
        assert moved.json()["data"]["saved_item"] is not None
        assert client.post("/api/v1/users/me/item-transfers", headers=buyer, json=transfer).status_code == 200
        assert client.post("/api/v1/users/me/item-transfers", headers=other, json=transfer).status_code == 404
        assert client.post("/api/v1/users/me/item-transfers", headers=buyer, json={**transfer, "destination": "cart"}).json()["error"]["code"] == "INVALID_TRANSFER"
        back = client.post("/api/v1/users/me/item-transfers", headers=buyer, json={**transfer, "source": "saved", "destination": "cart"})
        assert back.status_code == 200, back.text
        assert back.json()["data"]["cart_item"]["quantity"] == 1
        add(client, buyer, product_id, 2)
        key = f"test-{randrange(10**12)}"
        body = checkout_body(key, address_id, 225_000)
        wrong_total = client.post("/api/v1/orders", headers=buyer, json={**body, "displayed_total": 200_000})
        assert wrong_total.status_code == 409
        assert wrong_total.json()["error"]["details"] == [{"displayed_total": 200_000, "current_total": 225_000}]
        assert client.post("/api/v1/orders", headers=buyer, json={**body, "address_id": "999999999999"}).status_code == 404
        before = client.get("/api/v1/users/me/wallet", headers=buyer).json()["data"]["balance"]
        paid = client.post("/api/v1/orders", headers=buyer, json=body)
        assert paid.status_code == 201, paid.text
        receipt = paid.json()["data"]
        assert paid.headers["location"].endswith(f"/orders/{receipt['id']}")
        assert receipt["payment"]["amount"] == 225_000
        assert receipt["parcels"][0]["items"][0]["unit_price"] == 100_000
        assert receipt["shipping_address"]["postal_code"] == "0123456789"
        assert client.get("/api/v1/users/me/cart", headers=buyer).json()["data"]["items"] == []
        assert client.get("/api/v1/users/me/wallet", headers=buyer).json()["data"]["balance"] == before - 225_000
        replay = client.post("/api/v1/orders", headers=buyer, json=body)
        assert replay.status_code == 200 and replay.json()["data"] == receipt
        assert client.post("/api/v1/orders", headers=buyer, json={**body, "displayed_total": 226_000}).json()["error"]["code"] == "CHECKOUT_KEY_REUSED"
        assert client.get(f"/api/v1/orders/{receipt['id']}", headers=other).status_code == 404
        assert client.get(f"/api/v1/orders/{receipt['id']}", headers=buyer).json()["data"] == receipt
        detail = client.get(f"/api/v1/products/{product_id}", headers=seller)
        changed = client.patch(f"/api/v1/products/{product_id}", headers={**seller, "If-Match": detail.headers["etag"], "Content-Type": "application/merge-patch+json"}, content='{"title":"Renamed Mug","price":120000}')
        assert changed.status_code == 200, changed.text
        assert client.get(f"/api/v1/orders/{receipt['id']}", headers=buyer).json()["data"] == receipt
        history = client.get("/api/v1/users/me/orders", headers=buyer, params={"limit": 1})
        assert history.status_code == 200
        assert history.json()["data"][0]["parcel_status_counts"] == {"pending": 1}
        with Session(engine()) as session:
            assert session.scalar(select(func.count()).select_from(Order).where(Order.customer_id == buyer_id, Order.checkout_key == key)) == 1
            assert session.scalar(select(func.count()).select_from(Payment).where(Payment.order_id == int(receipt["id"]))) == 1
            assert session.get(Product, int(product_id)).stock_quantity == 1


def test_last_stock_only_one_buyer_pays():
    with TestClient(app) as client:
        _, seller = account(client, "Seller")
        product_id = product(client, seller, stock=1)
        buyers = [account(client, "Buyer")[1] for _ in range(2)]
        addresses = [address(client, headers) for headers in buyers]
        for headers in buyers:
            add(client, headers, product_id)
        bodies = [checkout_body(f"race-{randrange(10**12)}", addresses[i], 125_000) for i in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(client.post, "/api/v1/orders", headers=buyers[i], json=bodies[i]) for i in range(2)]
            results = [future.result() for future in futures]
        assert sorted(result.status_code for result in results) == [201, 409], [result.text for result in results]
        assert next(result for result in results if result.status_code == 409).json()["error"]["code"] == "INSUFFICIENT_STOCK"
        with Session(engine()) as session:
            assert session.get(Product, int(product_id)).stock_quantity == 0


def test_concurrent_wallet_debits_only_affordable_one_commits():
    with TestClient(app) as client:
        user_id, _ = account(client, "Wallet Owner")

    def post(reference):
        with Session(engine()) as session:
            try:
                debit_order(session, user_id, reference, 800_000)
                session.commit()
                return "paid"
            except APIError as exc:
                session.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(post, [randrange(10**12), randrange(10**12)]))
    assert sorted(outcomes) == ["INSUFFICIENT_WALLET_BALANCE", "paid"]
    with Session(engine()) as session:
        wallet = session.scalar(select(Wallet).where(Wallet.user_id == user_id))
        assert wallet.balance == 200_000
        assert session.scalar(select(func.sum(WalletTransaction.amount)).where(WalletTransaction.wallet_id == wallet.id)) == wallet.balance


def test_late_checkout_failure_rolls_back_stock_and_key(monkeypatch):
    with TestClient(app, raise_server_exceptions=False) as client:
        buyer_id, buyer = account(client, "Buyer")
        _, seller = account(client, "Seller")
        product_id = product(client, seller, stock=2)
        address_id = address(client, buyer)
        add(client, buyer, product_id)
        key = f"late-{randrange(10**12)}"
        body = checkout_body(key, address_id, 125_000)

        def fail_after_stock(*args, **kwargs):
            raise RuntimeError("injected posting failure")

        with monkeypatch.context() as patch:
            patch.setattr("app.services.orders.checkout.debit_order", fail_after_stock)
            assert client.post("/api/v1/orders", headers=buyer, json=body).status_code == 500
        with Session(engine()) as session:
            assert session.get(Product, int(product_id)).stock_quantity == 2
            assert session.scalar(select(Order.id).where(Order.customer_id == buyer_id, Order.checkout_key == key)) is None
            assert session.scalar(select(func.count()).select_from(CartItem).join(Cart).where(Cart.user_id == buyer_id)) == 1
        assert client.post("/api/v1/orders", headers=buyer, json=body).status_code == 201


def test_order_item_shop_must_match_parcel_and_product():
    with TestClient(app) as client:
        _, buyer = account(client, "Buyer")
        _, seller_a = account(client, "Seller A")
        _, seller_b = account(client, "Seller B")
        product_a = product(client, seller_a)
        product_b = product(client, seller_b)
        address_id = address(client, buyer)
        add(client, buyer, product_a)
        receipt = client.post("/api/v1/orders", headers=buyer, json=checkout_body(f"fk-{randrange(10**12)}", address_id, 125_000))
        assert receipt.status_code == 201, receipt.text
        parcel = receipt.json()["data"]["parcels"][0]
        with Session(engine()) as session:
            item = OrderItem(parcel_id=int(parcel["id"]), shop_id=int(parcel["shop_id"]), product_id=int(product_b), product_title="Wrong shop", unit_price=100_000, quantity=1)
            session.add(item)
            with pytest.raises(IntegrityError):
                session.commit()


def test_unaffordable_checkout_keeps_cart_stock_and_key_reusable():
    with TestClient(app) as client:
        buyer_id, buyer = account(client, "Buyer")
        _, seller = account(client, "Seller")
        product_id = product(client, seller, price=1_100_000, stock=1)
        address_id = address(client, buyer)
        add(client, buyer, product_id)
        key = f"funds-{randrange(10**12)}"
        body = checkout_body(key, address_id, 1_125_000)
        failed = client.post("/api/v1/orders", headers=buyer, json=body)
        assert failed.status_code == 409 and failed.json()["error"]["code"] == "INSUFFICIENT_WALLET_BALANCE"
        with Session(engine()) as session:
            assert session.get(Product, int(product_id)).stock_quantity == 1
            assert session.scalar(select(Order.id).where(Order.customer_id == buyer_id, Order.checkout_key == key)) is None
        assert len(client.get("/api/v1/users/me/cart", headers=buyer).json()["data"]["items"]) == 1
        detail = client.get(f"/api/v1/products/{product_id}", headers=seller)
        changed = client.patch(f"/api/v1/products/{product_id}", headers={**seller, "If-Match": detail.headers["etag"], "Content-Type": "application/merge-patch+json"}, content='{"price":100000}')
        assert changed.status_code == 200, changed.text
        assert client.post("/api/v1/orders", headers=buyer, json={**body, "displayed_total": 125_000}).status_code == 201


def test_transfer_failure_after_source_delete_rolls_back(monkeypatch):
    with TestClient(app, raise_server_exceptions=False) as client:
        _, buyer = account(client, "Buyer")
        _, seller = account(client, "Seller")
        product_id = product(client, seller)
        add(client, buyer, product_id)
        original_flush = Session.flush
        calls = 0

        def fail_second_flush(session, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected transfer failure")
            return original_flush(session, *args, **kwargs)

        body = {"product_id": product_id, "source": "cart", "destination": "saved"}
        with monkeypatch.context() as patch:
            patch.setattr(Session, "flush", fail_second_flush)
            assert client.post("/api/v1/users/me/item-transfers", headers=buyer, json=body).status_code == 500
        assert len(client.get("/api/v1/users/me/cart", headers=buyer).json()["data"]["items"]) == 1
        assert client.get("/api/v1/users/me/saved-items", headers=buyer).json()["data"] == []


def test_checkout_serializes_cart_membership_write(monkeypatch):
    from app.services.orders import checkout as checkout_module
    from app.api.endpoints.v1.cart import router as cart_module

    with TestClient(app) as client:
        _, buyer = account(client, "Buyer")
        _, seller = account(client, "Seller")
        first_product = product(client, seller, stock=2)
        second = client.post("/api/v1/shops/me/products", headers=seller, json={"title": "Second", "price": 50_000, "stock_quantity": 2, "status": "published"})
        assert second.status_code == 201, second.text
        second_product = second.json()["data"]["id"]
        address_id = address(client, buyer)
        add(client, buyer, first_product)
        reached_debit = Event()
        release_debit = Event()
        cart_started = Event()
        original_debit = checkout_module.debit_order
        original_put = cart_module.put_item

        def paused_debit(*args, **kwargs):
            reached_debit.set()
            assert release_debit.wait(5)
            return original_debit(*args, **kwargs)

        def observed_put(*args, **kwargs):
            cart_started.set()
            return original_put(*args, **kwargs)

        with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
            patch.setattr(checkout_module, "debit_order", paused_debit)
            patch.setattr(cart_module, "put_item", observed_put)
            checkout_future = pool.submit(client.post, "/api/v1/orders", headers=buyer, json=checkout_body(f"cart-race-{randrange(10**12)}", address_id, 125_000))
            assert reached_debit.wait(5)
            cart_future = pool.submit(client.put, f"/api/v1/users/me/cart/items/{second_product}", headers=buyer, json={"quantity": 1})
            assert cart_started.wait(5)
            release_debit.set()
            receipt = checkout_future.result()
            cart_write = cart_future.result()
        assert receipt.status_code == 201, receipt.text
        assert cart_write.status_code == 201, cart_write.text
        assert [item["product_id"] for item in receipt.json()["data"]["parcels"][0]["items"]] == [first_product]
        assert [item["product_id"] for item in client.get("/api/v1/users/me/cart", headers=buyer).json()["data"]["items"]] == [second_product]
