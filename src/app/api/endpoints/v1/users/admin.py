from typing import Annotated, Literal

from fastapi import APIRouter, Body, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.catalog import decode_cursor, encode_cursor, page_response
from app.api.dependencies import AdminUser, SessionDep
from app.api.http import ContractRoute, created, supplied_patch_fields
from app.api.representations import user_data, wallet_data
from app.core.errors import APIError
from app.core.audit import audit_log
from app.schemas.users.admin_requests import PrivilegedAccountCreate, UserAccessPatch
from app.schemas.users.models import User
from app.services.users.admin import change_user_access
from app.services.users.provision import provision_user

router = APIRouter(tags=["Administration"], route_class=ContractRoute)


@router.get("/admin/users", summary="Search user accounts", description="Admin only. Search by mobile or name and filter by role or activity. Results are newest first; use the returned cursor and matching filters for the next page. Password hashes are never returned.")
def list_users(request: Request, admin: AdminUser, session: SessionDep, mobile: Annotated[str | None, Query(min_length=1, max_length=11)] = None, name: Annotated[str | None, Query(min_length=1, max_length=100)] = None, role: Literal["customer", "operator", "admin"] | None = None, is_active: bool | None = None, cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    filters = {"actor_id": admin.id, "mobile": mobile, "name": name, "role": role, "is_active": is_active}
    marker = decode_cursor(cursor, filters)
    query = select(User)
    if mobile is not None:
        query = query.where(User.mobile.contains(mobile, autoescape=True))
    if name is not None:
        query = query.where(User.full_name.icontains(name, autoescape=True))
    if role is not None:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if marker:
        try:
            query = query.where(User.id < int(marker[0]))
        except (IndexError, TypeError, ValueError) as exc:
            raise APIError(400, "INVALID_CURSOR", "Invalid users cursor.") from exc
    rows = session.scalars(query.order_by(User.id.desc()).limit(limit + 1)).all()
    last = rows[limit - 1] if len(rows) > limit else None
    next_cursor = encode_cursor(filters, [last.id]) if last else None
    return page_response(request, [user_data(user) for user in rows[:limit]], limit, next_cursor, private=True)


@router.post("/admin/users", status_code=201, summary="Create an operator or admin", description="Admin only. Create an operator or admin with a hashed password, wallet, single welcome credit, and cart in one transaction. Public registration cannot choose these roles.")
def create_privileged_user(body: PrivilegedAccountCreate, request: Request, admin: AdminUser, session: SessionDep):
    try:
        user, wallet = provision_user(session, body.mobile, body.full_name, body.password, body.role)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise APIError(409, "MOBILE_ALREADY_REGISTERED", "Mobile number is already registered.") from exc
    session.refresh(user)
    session.refresh(wallet)
    audit_log.info("admin_user_created request_id=%s actor_id=%s target_id=%s role=%s", request.state.request_id, admin.id, user.id, user.role)
    return created({"user": user_data(user), "wallet": wallet_data(wallet)}, f"/api/v1/admin/users/{user.id}")


@router.get("/admin/users/{user_id}", summary="Inspect a user account", description="Admin only. Read an account's public profile and access state. Password hashes and wallet details are never returned.")
def get_user(user_id: Annotated[int, Path(gt=0)], admin: AdminUser, session: SessionDep):
    target = session.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise APIError(404, "USER_NOT_FOUND", "User not found.")
    return {"data": user_data(target)}


@router.patch("/admin/users/{user_id}", summary="Manage a user's role or activity", description="Admin only. Set role to customer, operator, or admin and/or set is_active. Cannot remove your own admin access or the last active admin. Does not alter passwords, wallets, or carts.")
def update_user_access(user_id: Annotated[int, Path(gt=0)], body: Annotated[UserAccessPatch, Body(media_type="application/merge-patch+json")], request: Request, admin: AdminUser, session: SessionDep):
    changes = supplied_patch_fields(body)
    target = change_user_access(session, admin, user_id, changes)
    audit_log.info("admin_user_access_changed request_id=%s actor_id=%s target_id=%s fields=%s", request.state.request_id, admin.id, target.id, ",".join(sorted(changes)))
    return {"data": user_data(target)}
