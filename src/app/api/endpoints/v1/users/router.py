from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import CurrentUser, SessionDep
from app.api.http import created, supplied_patch_fields
from app.api.http import ContractRoute
from app.api.representations import user_data, wallet_data
from app.core.config import settings
from app.core.errors import APIError
from app.core.security import hash_password, issue_token, verify_password
from app.schemas.users.models import User
from app.schemas.users.requests import Credentials, ProfilePatch, Registration
from app.services.users.provision import provision_user

router = APIRouter(route_class=ContractRoute)


@router.post(
    "/users",
    status_code=201,
    tags=["Users"],
    summary="Register a customer",
    description="Create a customer account using an Iranian mobile number, name, and password (minimum 8 characters). Registration atomically creates a wallet with a 1,000,000 Toman welcome credit and an empty cart. Returns 201 with the user and wallet; a duplicate mobile returns 409. Operator and admin accounts cannot be registered here.",
)
def register(body: Registration, request: Request, session: SessionDep):
    try:
        user, wallet = provision_user(session, body.mobile, body.full_name, body.password)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise APIError(409, "MOBILE_ALREADY_REGISTERED", "Mobile number is already registered.") from exc
    session.refresh(user)
    session.refresh(wallet)
    return created({"user": user_data(user), "wallet": wallet_data(wallet)}, "/api/v1/users/me")


@router.post(
    "/auth/tokens",
    tags=["Authentication"],
    summary="Sign in and receive a JWT",
    description="Exchange a registered mobile number and password for a Bearer access token. Include it in later requests as `Authorization: Bearer <access_token>`. Returns 401 for invalid credentials and 403 for an inactive account. Access tokens expire after the configured lifetime (60 minutes by default).",
)
def token(body: Credentials, session: SessionDep):
    user = session.scalar(select(User).where(User.mobile == body.mobile))
    if user is None or not verify_password(user.password_hash, body.password):
        raise APIError(401, "INVALID_CREDENTIALS", "Invalid credentials.")
    if not user.is_active:
        raise APIError(403, "ACCOUNT_INACTIVE", "Account is inactive.")
    return {"data": {"access_token": issue_token(user.id), "token_type": "Bearer", "expires_in_seconds": settings().access_token_minutes * 60, "user": user_data(user)}}


@router.get(
    "/users/me",
    tags=["Users"],
    summary="Read my profile",
    description="Return the profile of the user identified by the Bearer token. Requires authentication; an inactive account is rejected. The response never includes the password hash.",
)
def profile(user: CurrentUser):
    return {"data": user_data(user)}


@router.patch(
    "/users/me",
    tags=["Users"],
    summary="Update my name or password",
    description="Send `Content-Type: application/merge-patch+json` and a Bearer token. Supply `full_name`, or both `current_password` and `new_password` to change the password. Omitted fields stay unchanged; mobile, role, and active status cannot be edited here. Returns 401 if the current password is wrong.",
)
def update_profile(body: Annotated[ProfilePatch, Body(media_type="application/merge-patch+json")], user: CurrentUser, session: SessionDep):
    changes = supplied_patch_fields(body)
    if "current_password" in changes:
        if not verify_password(user.password_hash, body.current_password):
            raise APIError(401, "CURRENT_PASSWORD_INVALID", "Current password is incorrect.")
        user.password_hash = hash_password(body.new_password)
    if "full_name" in changes:
        user.full_name = body.full_name
    session.commit()
    session.refresh(user)
    return {"data": user_data(user)}
