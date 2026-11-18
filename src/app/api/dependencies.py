from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import read_token
from app.data.session import get_session
from app.schemas.users.models import User

SessionDep = Annotated[Session, Depends(get_session)]
bearer = HTTPBearer(auto_error=False)


def optional_user(session: SessionDep, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User | None:
    if credentials is None:
        return None
    user = session.get(User, read_token(credentials.credentials))
    if user is None:
        raise HTTPException(401, "Invalid token subject.", headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(403, "ACCOUNT_INACTIVE")
    return user


def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(401, "Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    return user


AuthenticatedUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]


def has_operator_access(user: User | None) -> bool:
    return user is not None and user.role in ("operator", "admin")


def can_moderate_shops(user: User | None) -> bool:
    return user is not None and user.role in ("operator", "admin")


def can_inspect_private_products(user: User | None) -> bool:
    return user is not None and user.role in ("operator", "admin")


def can_read_full_order(user: User, customer_id: int) -> bool:
    return user.id == customer_id or user.role == "admin"


def require_customer(user: AuthenticatedUser) -> User:
    if user.role not in ("customer", "operator", "admin"):
        raise HTTPException(403, "CUSTOMER_REQUIRED")
    return user


CurrentUser = Annotated[User, Depends(require_customer)]


def require_operator(user: CurrentUser) -> User:
    if not has_operator_access(user):
        raise HTTPException(403, "OPERATOR_REQUIRED")
    return user


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "ADMIN_REQUIRED")
    return user


CustomerUser = CurrentUser
OperatorUser = Annotated[User, Depends(require_operator)]
AdminUser = Annotated[User, Depends(require_admin)]
