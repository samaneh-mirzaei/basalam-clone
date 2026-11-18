from typing import Literal

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.catalog import catalog_response
from app.api.http import ContractRoute
from app.api.dependencies import SessionDep
from app.api.representations import category_data
from app.core.errors import APIError
from app.schemas.categories.models import Category

router = APIRouter(route_class=ContractRoute)


@router.get(
    "/categories",
    tags=["Categories"],
    summary="Browse categories",
    description="Public read of the complete taxonomy. `format=tree` (default) nests children under parents; `format=flat` returns a flat array. There is no pagination. Public responses support ETags and `If-None-Match`.",
)
def categories(request: Request, session: SessionDep, format: Literal["tree", "flat"] = "tree"):
    rows = session.scalars(select(Category).order_by(Category.id)).all()
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
    description="Public read of one category with its ancestor path. Returns 404 when the category does not exist. Public responses support ETags and `If-None-Match`.",
)
def category(category_id: int, request: Request, session: SessionDep):
    row = session.get(Category, category_id)
    if row is None:
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
