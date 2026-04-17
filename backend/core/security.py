from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jwt.exceptions import InvalidTokenError, PyJWTError

from config import Settings

_hasher = PasswordHasher()

Scope = Literal["full", "limited"]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: str, settings: Settings, scope: Scope = "full") -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "typ": "access",
        "scope": scope,
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str, settings: Settings, *, mfa_satisfied: bool) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.refresh_token_expire_hours)
    payload: dict[str, Any] = {
        "sub": user_id,
        "typ": "refresh",
        "mfa_sat": mfa_satisfied,
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_connect_token(user_id: str, template_id: str, settings: Settings) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.connect_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "typ": "connect",
        "tpl": template_id,
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: Settings, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("typ") != expected_type:
        raise InvalidTokenError("wrong token type")
    return payload


def decode_connect_token(token: str, settings: Settings) -> dict[str, Any]:
    return decode_token(token, settings, "connect")
