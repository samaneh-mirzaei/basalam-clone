# Basalam backend

[فارسی](README.fa.md)

FastAPI and PostgreSQL marketplace backend. The implemented API covers registration, JWT authentication, profiles, shops, categories, products and SQL catalog search; owned addresses, wallet and ledger reads, cart and saved items; atomic item transfers, wallet checkout, order receipts, and admin user management. Operators and admins retain ordinary shopping access. Parcel fulfilment, returns, refunds, wallet adjustments, and product-image management are not exposed yet.

## Requirements

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/)
- PostgreSQL 18 or a compatible recent version, with a database you have created

## Local setup

Run from this repository root:

```powershell
uv sync --locked --extra test
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Create the PostgreSQL database before migrating. Edit `.env` with its real connection URL and a random JWT signing secret of at least 32 characters:

```text
BASALAM_DATABASE_URL=postgresql+psycopg://USERNAME:PASSWORD@127.0.0.1:5432/basalam
BASALAM_JWT_SECRET=YOUR_RANDOM_SECRET_OF_AT_LEAST_32_CHARACTERS
```

Use the actual host, port, database, and credentials for your PostgreSQL instance. The JWT secret is separate from the database password. Percent-encode special characters in URL credentials. `.env.example` contains unusable placeholders. Never commit `.env`.

```powershell
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [Swagger UI](http://127.0.0.1:8000/docs) to test the API. Call `POST /api/v1/auth/tokens` with a registered mobile number and password, copy `data.access_token`, then paste **only the token** into Swagger's **Authorize** dialog. `GET /health` checks process liveness; `GET /ready` checks PostgreSQL connectivity and returns 503 if unavailable. Alembic creates the schema in the existing database, including enums, foreign keys, indexes, and checks. Revisions `0003_address_phone_length` through `0006_category_active` extend the schema without resetting records. The original DBML and SQL design files are not needed to run migrations.

## Administrative access

Accounts have `customer`, `operator`, or `admin` roles. Every role retains its own wallet, cart, addresses, and checkout. Operator and admin accounts can inspect private catalog entries and use operational shop views and status controls. Full order receipts and shipping details are available only to the customer who placed the order or an admin; admin reads of another customer's receipt are audit logged without address contents. Admins can search users with `GET /api/v1/admin/users`, inspect with `GET /api/v1/admin/users/{user_id}`, create operators/admins with `POST /api/v1/admin/users`, and change role or activity with `PATCH /api/v1/admin/users/{user_id}`. PATCH requires `Content-Type: application/merge-patch+json`; it cannot remove the acting admin's access or the last active admin. These routes do not directly alter wallet balances.

Admins can create and edit categories with `POST /api/v1/categories` and `PATCH /api/v1/categories/{category_id}`. Slugs must be unique; parent categories must exist and be active; circular parent links are rejected. Setting `is_active=false` hides a category from public category reads while preserving product references. Deactivate active children first.

Public registration always creates a customer. The local demo seed below creates a demo admin. To promote a separate existing account on the local `basalam` database, run the migration and then use this explicit command:

```powershell
uv run python scripts/promote_admin.py --mobile 09XXXXXXXXX --confirm
```

The command preserves its password, wallet, ledger, and cart. Keep local database access and `.demo-credentials` private. Demo operator and admin accounts can both shop normally.

For checkout in Swagger UI: register and authenticate a buyer and seller, create the seller's shop and a published product, create a buyer address, add that product to the buyer's cart, and read `GET /api/v1/users/me/cart`. Send its `displayed_total`, the address ID **as a string**, and a new `checkout_key` to `POST /api/v1/orders`. Checkout rechecks stock, product/shop status, price, and wallet funds. An exact retry with the same key and payload returns the original receipt; a changed payload returns 409. The buyer can read `GET /api/v1/users/me/orders` and `GET /api/v1/orders/{order_id}`.

A fresh clone needs its own PostgreSQL database and `.env`; database files and local credentials are never included in Git.

## Demo data

`uv run python scripts/seed_demo.py` creates a buyer, seller, operator, **admin**, shop, two categories, and four products **only** when the configured database is local and named `basalam`. Run migrations first. Each new demo account receives a wallet, one 1,000,000 Toman welcome credit, and an empty cart. The seed is repeatable: it does not reset existing passwords or grant duplicate welcome credits. It writes the shared demo password and account mobiles to the Git-ignored `.demo-credentials` file; read it locally with `Get-Content .demo-credentials`. When upgrading an older seed, it adds the admin account and appends its mobile to the existing credentials file. Three demo products are public; the draft cup is visible to its owner, an operator, or an admin. If the demo accounts already exist but `.demo-credentials` is missing, the seed refuses to reset their passwords.

## Tests

```powershell
uv run --locked --extra test pytest -q
```

PostgreSQL integration tests write data and are skipped unless **both** `BASALAM_DATABASE_URL` and `BASALAM_JWT_SECRET` are exported as environment variables; values in `.env` alone do not enable them. Point these variables at a **separate, disposable, migrated database**, never shared or development data. The suite covers authorization, seed account invariants, transfers, checkout rollback and replay, stock and wallet contention, and order ownership. For example, after creating a disposable database:

```powershell
$env:BASALAM_DATABASE_URL = 'postgresql+psycopg://USERNAME:PASSWORD@127.0.0.1:5432/basalam_test'
$env:BASALAM_JWT_SECRET = 'a-test-only-secret-with-at-least-32-characters'
uv run --locked alembic upgrade head
uv run --locked --extra test pytest -q
```

Clear those two shell variables before using the development database again.

