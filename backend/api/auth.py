from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_access_payload, get_current_user
from api.schemas import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MfaChallengeHints,
    UserMeResponse,
)
from config import get_settings
from core.audit_log import log_security_event
from core.cookies import clear_refresh_cookie, set_refresh_cookie
from core.limiter import limiter
from core.mfa_ops import mfa_challenge_hints, user_has_verified_mfa
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from db.database import get_db
from db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=LoginResponse)
@limiter.limit(settings.rate_limit_login)
def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    stmt = select(User).where(User.username == body.username)
    user = db.execute(stmt).scalar_one_or_none()
    now = datetime.now(timezone.utc)

    tid = getattr(request.state, "trace_id", None)

    if user is None or not user.is_active:
        log_security_event("login", _client_ip(request), "FAIL", trace_id=tid)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if user.locked_until is not None and user.locked_until > now:
        log_security_event(
            "login_locked",
            _client_ip(request),
            "BLOCKED",
            trace_id=tid,
            user_id=str(user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account temporarily locked",
        )

    if not verify_password(user.password_hash, body.password):
        user.failed_attempts += 1
        if user.failed_attempts >= 5:
            user.locked_until = now + timedelta(minutes=15)
        db.add(user)
        db.commit()
        log_security_event(
            "login",
            _client_ip(request),
            "FAIL",
            trace_id=tid,
            user_id=str(user.id),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = now
    db.add(user)
    db.commit()

    has_mfa = user_has_verified_mfa(db, user.id)
    # All accounts must use 2FA: limited until enrolled + verified (or password reset handled first in UI).
    access = create_access_token(user.id, settings, "limited")
    refresh = create_refresh_token(user.id, settings, mfa_satisfied=False)
    mfa_required = True
    mfa_enroll_required = not has_mfa
    set_refresh_cookie(response, refresh, settings, request=request)

    log_security_event(
        "login",
        _client_ip(request),
        "SUCCESS",
        trace_id=tid,
        user_id=str(user.id),
    )
    return LoginResponse(
        access_token=access,
        mfa_required=mfa_required,
        mfa_enroll_required=mfa_enroll_required,
        force_password_reset=bool(user.force_password_reset),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh_session(request: Request, db: Session = Depends(get_db)) -> AccessTokenResponse:
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")
    try:
        payload = decode_token(raw, settings, "refresh")
    except PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    has_mfa = user_has_verified_mfa(db, user.id)
    mfa_ok = payload.get("mfa_sat")
    if not has_mfa:
        scope = "limited"
    elif mfa_ok is None:
        scope = "limited"
    else:
        scope = "full" if mfa_ok else "limited"

    access = create_access_token(user.id, settings, scope)
    return AccessTokenResponse(access_token=access)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict[str, bool]:
    clear_refresh_cookie(response, settings, request=request)
    return {"ok": True}


@router.get("/me", response_model=UserMeResponse)
def me(
    user: User = Depends(get_current_user),
    payload: dict = Depends(get_access_payload),
    db: Session = Depends(get_db),
) -> UserMeResponse:
    has_mfa = user_has_verified_mfa(db, user.id)
    scope = str(payload.get("scope", "full") or "full")
    hints: MfaChallengeHints | None = None
    if has_mfa and payload.get("scope") == "limited":
        hints = MfaChallengeHints(**mfa_challenge_hints(db, user, settings))
    return UserMeResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        scope=scope,
        mfa_enrolled=has_mfa,
        mfa_enrollment_required=not has_mfa,
        force_password_reset=bool(user.force_password_reset),
        mfa_hints=hints,
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.force_password_reset = False
    user.failed_attempts = 0
    user.locked_until = None
    db.add(user)
    db.commit()
    return {"ok": True}


def _client_ip(req: Request) -> str:
    if req.client:
        return req.client.host or "unknown"
    return "unknown"
