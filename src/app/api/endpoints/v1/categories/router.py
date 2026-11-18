from typing import Annotated, Literal

from fastapi import APIRouter, Body, Path, Request
from sqlalchemy import select

from app.api.catalog import catalog_response
from app.api.http import ContractRoute
from app.api.http import created, supplied_patch_fields
from app.api.dependencies import AdminUser, SessionDep
from app.api.representations import category_data
from app.core.errors import APIError
from app.schemas.categories.models import Category
from app.schemas.categories.requests import CategoryCreate, CategoryPatch
from app.services.categories.service import create_category, edit_category

router = APIRouter(route_class=ContractRoute)


@router.get(
    "/categories",
    tags=["Categories"],
    summary="Browse categories",
    description="Public read of active categories. `format=tree` (default) nests children under parents; `format=flat` returns a flat array. There is no pagination. Public responses support ETags and `If-None-Match`.",
)
def categories(request: Request, session: SessionDep, format: Literal["tree", "flat"] = "tree"):
    rows = session.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.id)).all()
    flat = [category_data(row) for row in rows]
    if format == "flat":
        return catalog_response(request, flat)
    nodes = {row["id"]: {**row, "children": []} for row in flat}
    roots = []
    for row in flat:
        node = nodes[row["id"]]
        parent = nodes.get(row["parent_id"])
        (parent["children"] if parent else roots).append(node)
    return catalog_response(request, roots)


@router.get(
    "/categories/{category_id}",
    tags=["Categories"],
    summary="Read a category",
    description="Public read of one active category with its ancestor path. Returns 404 when absent or inactive. Public responses support ETags and `If-None-Match`.",
)
def category(category_id: int, request: Request, session: SessionDep):
    row = session.get(Category, category_id)
    if row is None or not row.is_active:
        raise APIError(404, "CATEGORY_NOT_FOUND", "Category not found.")
    ancestors = []
    parent = row.parent_id
    while parent is not None:
        node = session.get(Category, parent)
        if node is None:
            break
        ancestors.insert(0, category_data(node))
        parent = node.parent_id
    return catalog_response(request, {**category_data(row), "ancestors": ancestors})


@router.post("/categories", status_code=201, tags=["Categories"], summary="Create a category", description="Admin only. Create a category with a unique lowercase slug and optional active parent.")
def post_category(body: CategoryCreate, admin: AdminUser, session: SessionDep):
    row = create_category(session, body.model_dump())
    return created(category_data(row), f"/api/v1/categories/{row.id}")


@router.patch("/categories/{category_id}", tags=["Categories"], summary="Edit or deactivate a category", description="Admin only. Use application/merge-patch+json to edit name, slug, parent, or is_active. Reparenting cannot create a cycle. Deactivation preserves referenced products and requires active children to be deactivated first.")
def patch_category(category_id: Annotated[int, Path(gt=0)], body: Annotated[CategoryPatch, Body(media_type="application/merge-patch+json")], admin: AdminUser, session: SessionDep):
    row = edit_category(session, category_id, supplied_patch_fields(body))
    return {"data": category_data(row)}
