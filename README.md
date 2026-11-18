# Basalam backend

FastAPI and PostgreSQL marketplace backend. Phase 1 includes registration, JWT authentication, profiles, shops, categories, products, and SQL product search. The migrations include the full 17-table design; checkout and later workflows are not yet implemented.

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

Open [Swagger UI](http://127.0.0.1:8000/docs) to test the API. `GET /health` checks the process only; it does not check PostgreSQL. The Alembic revisions create the complete schema, including enums, foreign keys, indexes, and companion checks. The original DBML and SQL design files are not needed to run migrations.

A fresh clone needs its own PostgreSQL database and `.env`; database files and local credentials are never included in Git.

## Demo data

`uv run python scripts/seed_demo.py` creates a buyer, seller, operator, shop, two categories, and four products in a local database named `basalam`. It is safe to rerun and does not reset existing accounts. It generates a shared demo password in the Git-ignored `.demo-credentials` file; read it locally with `Get-Content .demo-credentials`. In Swagger UI, call `POST /api/v1/auth/tokens`, copy `data.access_token`, and paste only the token into **Authorize**. Three demo products are public; the draft cup is visible only to its owner or an operator.

## Tests

```powershell
uv run --locked --extra test pytest -q
```

The PostgreSQL integration test writes data. It runs only when both `BASALAM_DATABASE_URL` and `BASALAM_JWT_SECRET` are exported as environment variables. Point them at a disposable migrated database, never shared data.

