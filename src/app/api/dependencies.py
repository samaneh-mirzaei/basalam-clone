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


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]
