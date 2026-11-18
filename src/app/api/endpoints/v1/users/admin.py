from typing import Annotated

from fastapi import APIRouter, Body, Path
from sqlalchemy import select

from app.api.dependencies import AdminUser, SessionDep
from app.api.http import ContractRoute, supplied_patch_fields
from app.api.representations import user_data
from app.core.errors import APIError
from app.schemas.users.admin_requests import UserAccessPatch
from app.schemas.users.models import User
from app.services.users.admin import change_user_access

router = APIRouter(tags=["Administration"], route_class=ContractRoute)


@router.get("/admin/users/{user_id}", summary="Inspect a user account", description="Admin only. Read an account's public profile and access state. Password hashes and wallet details are never returned.")
def get_user(user_id: Annotated[int, Path(gt=0)], admin: AdminUser, session: SessionDep):
    target = session.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise APIError(404, "USER_NOT_FOUND", "User not found.")
    return {"data": user_data(target)}


@router.patch("/admin/users/{user_id}", summary="Manage a user's role or activity", description="Admin only. Set role to customer, operator, or admin and/or set is_active. Cannot remove your own admin access or the last active admin. Does not alter passwords, wallets, or carts.")
def update_user_access(user_id: Annotated[int, Path(gt=0)], body: Annotated[UserAccessPatch, Body(media_type="application/merge-patch+json")], admin: AdminUser, session: SessionDep):
    target = change_user_access(session, admin, user_id, supplied_patch_fields(body))
    return {"data": user_data(target)}
