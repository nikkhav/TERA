"""Password authentication and signed access tokens."""

from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from tera.config import get_settings
from tera.db import get_session
from tera.models import User, now

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
_DUMMY_PASSWORD_HASH = password_hash.hash("unused-password-value")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    return password_hash.verify(password, encoded)


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.email == email.strip().casefold()))
    encoded = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    valid_password = verify_password(password, encoded)
    if user is None or not valid_password or not user.is_active:
        return None
    return user


def create_access_token(user: User) -> str:
    settings = get_settings()
    issued = now()
    return jwt.encode(
        {
            "sub": user.id,
            "email": user.email,
            "iat": issued,
            "exp": issued + timedelta(minutes=settings.auth_token_minutes),
            "iss": "tera",
        },
        settings.auth_secret_key,
        algorithm="HS256",
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(
            credentials.credentials,
            get_settings().auth_secret_key,
            algorithms=["HS256"],
            issuer="tera",
        )
        user_id = payload.get("sub")
        if not isinstance(user_id, str):
            raise InvalidTokenError
    except InvalidTokenError as exc:
        raise HTTPException(
            401,
            "Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            401, "Invalid or expired session", headers={"WWW-Authenticate": "Bearer"}
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
