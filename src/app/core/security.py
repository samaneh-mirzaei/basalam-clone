from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from fastapi import HTTPException

from app.core.config import settings

hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError):
        return False


def signing_key() -> str:
    secret = settings().jwt_secret
    if secret is None or len(secret.get_secret_value()) < 32:
        raise RuntimeError("BASALAM_JWT_SECRET must contain at least 32 characters")
    return secret.get_secret_value()


def issue_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    config = settings()
    return jwt.encode(
        {"sub": str(user_id), "iss": config.jwt_issuer, "aud": config.jwt_audience, "iat": now, "exp": now + timedelta(minutes=config.access_token_minutes)},
        signing_key(),
        algorithm="HS256",
    )


def read_token(token: str) -> int:
    try:
        claims = jwt.decode(token, signing_key(), algorithms=["HS256"], issuer=settings().jwt_issuer, audience=settings().jwt_audience, options={"require": ["sub", "exp", "iss", "aud"]})
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(401, "Invalid or expired token.", headers={"WWW-Authenticate": "Bearer"}) from exc
