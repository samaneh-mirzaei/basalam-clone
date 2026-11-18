# Basalam backend

FastAPI and PostgreSQL marketplace backend. Phase 1 includes registration, JWT authentication, profiles, shops, categories, products, and SQL product search. Phase 2 adds owned address creation/reads, wallet and ledger reads, cart and saved items, atomic item transfers, wallet checkout, and order receipts. Fulfilment, returns, refunds, and operator workflows follow in later phases.

## Requirements

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/)
- PostgreSQL 18 or a compatible recent version

## Local setup

Run from this repository root:

```powershell
uv sync --locked --extra test
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit `.env`: set `BASALAM_DATABASE_URL` to a PostgreSQL database you created and `BASALAM_JWT_SECRET` to a random secret of at least 32 characters. The example values are placeholders and cannot be used as-is. Never commit `.env`.

```powershell
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [Swagger UI](http://127.0.0.1:8000/docs) to test the API. `GET /health` checks the process only; it does not check PostgreSQL. Alembic creates the complete schema, including enums, foreign keys, indexes, and companion checks. Revision `0003_address_phone_length` permits an optional leading `+` and 15 phone digits; `0004_payment_debit_required` requires each wallet payment to reference its ledger debit; `0005_admin_role` adds the admin role without resetting users. The original DBML and SQL design files are not needed to run migrations.

## Administrative access

Accounts have `customer`, `operator`, or `admin` roles. Every role retains its own wallet, cart, addresses, and checkout. Operator and admin accounts can use existing operational shop views and status controls. Only admins can read or change account roles and activity through `/api/v1/admin/users/{user_id}`. These endpoints do not change passwords or wallet balances.

Public registration always creates a customer. To bootstrap the first admin, register an account normally, migrate the local `basalam` database, then explicitly promote that existing account on the local machine:

```powershell
uv run python scripts/promote_admin.py --mobile 09XXXXXXXXX --confirm
```

The command preserves its password, wallet, ledger, and cart. Keep local database access and `.demo-credentials` private. The demo operator remains an operator and can shop normally.

For checkout in Swagger UI: register and authenticate a buyer and seller, create the seller's shop and a published product, create a buyer address, add that product to the buyer's cart, and read `GET /api/v1/users/me/cart`. Send its `displayed_total`, your address ID, and a new `checkout_key` to `POST /api/v1/orders`. A repeat with the same key and payload returns the same receipt. The buyer can read `GET /api/v1/users/me/orders` and `GET /api/v1/orders/{order_id}`.

A fresh clone needs its own PostgreSQL database and `.env`; database files and local credentials are never included in Git.

## Demo data

`uv run python scripts/seed_demo.py` creates a buyer, seller, operator, shop, two categories, and four products in a local database named `basalam`. It is safe to rerun and does not reset existing accounts. It generates a shared demo password in the Git-ignored `.demo-credentials` file; read it locally with `Get-Content .demo-credentials`. In Swagger UI, call `POST /api/v1/auth/tokens`, copy `data.access_token`, and paste only the token into **Authorize**. Three demo products are public; the draft cup is visible only to its owner or an operator.

## Tests

```powershell
uv run --locked --extra test pytest -q
```

The PostgreSQL integration tests write data. They run only when both `BASALAM_DATABASE_URL` and `BASALAM_JWT_SECRET` are exported as environment variables. Point them at a disposable migrated database, never shared data. They cover transfer replay, checkout rollback and replay, stock contention, wallet contention, and order ownership.

