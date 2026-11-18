from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.catalog import catalog_response, decode_cursor, encode_cursor, page_response
from app.api.dependencies import CurrentUser, OptionalUser, SessionDep
from app.api.http import ContractRoute, created, supplied_patch_fields
from app.api.representations import product_data, shop_data
from app.core.errors import APIError
from app.schemas.categories.models import Category
from app.schemas.products.models import Product, ProductImage
from app.schemas.shops.models import Shop
from app.schemas.products.requests import ProductPatch, ProductWrite

router = APIRouter(route_class=ContractRoute)


def visible(product: Product, shop: Shop, user) -> bool:
    return (product.status == "published" and shop.status == "active") or bool(user and (user.id == shop.owner_id or user.role == "operator"))


def product_tag(product: Product, shop: Shop) -> str:
    return f'"product-{product.id}-{product.version}-{shop.version}"'


@router.get(
    "/products",
    tags=["Products"],
    summary="Search visible products",
    description="SQL-backed search of published products from active shops. `q` searches title and description; category includes descendants. Filter by shop, price range, or stock, then sort by creation time or price. Use `limit` (1–100) and the returned `next_cursor`; reuse a cursor only with the same filters and sort. Public results support ETags and `If-None-Match`.",
)
def list_products(request: Request, session: SessionDep, q: str | None = None, category_id: int | None = None, shop_id: int | None = None, min_price: int | None = None, max_price: int | None = None, in_stock: bool | None = None, sort: Literal["created_at", "price"] = "created_at", direction: Literal["asc", "desc"] = "desc", cursor: str | None = None, limit: int = 20):
    if not 1 <= limit <= 100 or (min_price is not None and min_price < 0) or (max_price is not None and max_price < 0) or (min_price is not None and max_price is not None and min_price > max_price):
        raise APIError(422, "VALIDATION_FAILED", "Invalid product filters.")
    filters = {"q": q, "category_id": category_id, "shop_id": shop_id, "min_price": min_price, "max_price": max_price, "in_stock": in_stock, "sort": sort, "direction": direction}
    marker = decode_cursor(cursor, filters)
    query = select(Product).join(Shop, Shop.id == Product.shop_id).where(Product.status == "published", Shop.status == "active")
    if q:
        query = query.where(or_(Product.title.ilike(f"%{q}%"), Product.description.ilike(f"%{q}%")))
    if category_id is not None:
        descendants = select(Category.id).where(Category.id == category_id).cte(recursive=True)
        descendants = descendants.union_all(select(Category.id).where(Category.parent_id == descendants.c.id))
        query = query.where(Product.category_id.in_(select(descendants.c.id)))
    if shop_id is not None:
        query = query.where(Product.shop_id == shop_id)
    if min_price is not None:
        query = query.where(Product.price >= min_price)
    if max_price is not None:
        query = query.where(Product.price <= max_price)
    if in_stock is not None:
        query = query.where(Product.stock_quantity > 0 if in_stock else Product.stock_quantity == 0)
    field = Product.price if sort == "price" else Product.created_at
    if marker:
        value = int(marker[0]) if sort == "price" else datetime.fromisoformat(marker[0])
        comparison = (field > value) | ((field == value) & (Product.id > marker[1])) if direction == "asc" else (field < value) | ((field == value) & (Product.id < marker[1]))
        query = query.where(comparison)
    query = query.order_by(field.asc() if direction == "asc" else field.desc(), Product.id.asc() if direction == "asc" else Product.id.desc())
    rows = session.scalars(query.limit(limit + 1)).all()
    last = rows[limit - 1] if len(rows) > limit else None
    next_cursor = encode_cursor(filters, [last.price if sort == "price" else last.created_at.isoformat(), last.id]) if last else None
    return page_response(request, [product_data(row) for row in rows[:limit]], limit, next_cursor)


@router.post(
    "/shops/me/products",
    status_code=201,
    tags=["Products"],
    summary="Create a product in my shop",
    description="Requires a Bearer token and an owned shop. Provide title, nonnegative price, and nonnegative stock; category and description are optional. Products start as drafts unless `status` is supplied. Publishing requires an active shop. Returns 201 with Location; the shop ID is assigned from ownership.",
)
def create_product(body: ProductWrite, user: CurrentUser, session: SessionDep):
    shop = session.scalar(select(Shop).where(Shop.owner_id == user.id))
    if shop is None:
        raise APIError(404, "SHOP_NOT_FOUND", "Shop not found.")
    if body.status == "published" and shop.status != "active":
        raise APIError(409, "SHOP_NOT_ACTIVE", "Shop is not active.")
    if body.category_id is not None and session.get(Category, body.category_id) is None:
        raise APIError(404, "CATEGORY_NOT_FOUND", "Category not found.")
    product = Product(shop_id=shop.id, **body.model_dump())
    session.add(product)
    session.commit()
    session.refresh(product)
    return created(product_data(product), f"/api/v1/products/{product.id}")


@router.get(
    "/products/{product_id}",
    tags=["Products"],
    summary="Read a product",
    description="Guests see only published products from active shops. Owners and operators can also read nonpublic products. Includes the shop summary and ordered images. Returns an ETag for updates; public callers may use `If-None-Match`. Missing or concealed products return 404.",
)
def get_product(product_id: int, request: Request, session: SessionDep, user: OptionalUser):
    product = session.get(Product, product_id)
    shop = session.get(Shop, product.shop_id) if product else None
    if product is None or not visible(product, shop, user):
        raise APIError(404, "PRODUCT_NOT_FOUND", "Product not found.")
    images = session.scalars(select(ProductImage).where(ProductImage.product_id == product.id).order_by(ProductImage.sort_order)).all()
    representation = {**product_data(product, [{"id": str(image.id), "url": image.url, "sort_order": image.sort_order} for image in images]), "shop": shop_data(shop)}
    private = bool(user and (user.id == shop.owner_id or user.role == "operator"))
    return catalog_response(request, representation, product_tag(product, shop), private)


@router.patch(
    "/products/{product_id}",
    tags=["Products"],
    summary="Update my product",
    description="Requires the owning shop user's Bearer token, `Content-Type: application/merge-patch+json`, and the current product `If-Match` ETag from GET. Change only supplied fields; `shop_id` is immutable. Publishing requires an active shop. Missing If-Match returns 428; a stale tag returns 412; nonowned products return 404.",
)
def update_product(product_id: int, body: Annotated[ProductPatch, Body(media_type="application/merge-patch+json")], user: CurrentUser, session: SessionDep, if_match: Annotated[str | None, Header()] = None):
    if if_match is None:
        raise APIError(428, "PRECONDITION_REQUIRED", "If-Match is required.")
    product = session.scalar(select(Product).where(Product.id == product_id).with_for_update())
    shop = session.get(Shop, product.shop_id) if product else None
    if product is None or shop.owner_id != user.id:
        raise APIError(404, "PRODUCT_NOT_FOUND", "Product not found.")
    if if_match != product_tag(product, shop):
        raise APIError(412, "PRECONDITION_FAILED", "Product has changed.")
    changes = supplied_patch_fields(body)
    if any(value is None and field != "description" and field != "category_id" for field, value in changes.items()):
        raise APIError(422, "VALIDATION_FAILED", "Field cannot be null.")
    if changes.get("status") == "published" and shop.status != "active":
        raise APIError(409, "SHOP_NOT_ACTIVE", "Shop is not active.")
    if changes.get("category_id") is not None and "category_id" in changes and session.get(Category, changes["category_id"]) is None:
        raise APIError(404, "CATEGORY_NOT_FOUND", "Category not found.")
    for field, value in changes.items():
        setattr(product, field, value)
    product.version += 1
    session.commit()
    session.refresh(product)
    return JSONResponse({"data": product_data(product)}, headers={"ETag": product_tag(product, shop), "Cache-Control": "private, no-store"})
