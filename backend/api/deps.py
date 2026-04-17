from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError
from sqlalchemy.orm import Session

from config import get_settings
from core.mfa_ops import user_has_verified_mfa
from core.security import decode_token
from db.database import get_db
from db.models import User

settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


def get_access_payload(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return decode_token(creds.credentials, settings, "access")
    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_full_scope(
    payload: Annotated[dict, Depends(get_access_payload)],
) -> dict:
    if payload.get("scope") != "full":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="MFA verification required",
        )
    return payload


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[dict, Depends(get_access_payload)],
) -> User:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return user


def get_current_user_full_scope(
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[dict, Depends(require_full_scope)],
) -> User:
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    return user


def get_current_user_for_mfa_enrollment(
    db: Annotated[Session, Depends(get_db)],
    payload: Annotated[dict, Depends(get_access_payload)],
) -> User:
    """Full scope, or limited scope with no verified 2FA yet (initial enrollment)."""
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")
    scope = payload.get("scope")
    has_mfa = user_has_verified_mfa(db, user.id)
    if scope == "full":
        return user
    if scope == "limited" and not has_mfa:
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="2FA verification required before enrolling additional factors",
    )
