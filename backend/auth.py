"""Password hashing, JWT creation, and authenticated-user dependency."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from beanie import PydanticObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from config import (
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
)
from models import User

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Return a bcrypt hash for a plaintext password."""
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against its stored bcrypt hash."""
    return password_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    """Create a signed JWT whose expiry follows the configured lifetime."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": subject, "iat": now, "exp": expires},
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> User:
    """Resolve the bearer token to its active user or return HTTP 401."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise unauthorized
        user = await User.get(PydanticObjectId(subject))
    except (jwt.InvalidTokenError, InvalidId, TypeError, ValueError):
        raise unauthorized

    if user is None:
        raise unauthorized
    return user