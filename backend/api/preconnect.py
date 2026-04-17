import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from webauthn import verify_authentication_response

from api.deps import get_current_user_full_scope
from api.schemas import (
    PreconnectChallengeRequest,
    PreconnectChallengeResponse,
    PreconnectVerifyRequest,
    PreconnectVerifyResponse,
)
from config import get_settings
from core.audit_log import log_security_event
from core.datetime_util import to_utc_aware
from core.limiter import limiter
from core.mfa_ops import (
    find_webauthn_method_by_credential_id,
    serialize_webauthn_credential,
    totp_for_user,
    verify_backup_code,
    yubikey_verify_otp_for_user,
)
from core.security import create_connect_token
from db.database import get_db
from db.models import ContainerTemplate, PreconnectChallenge, User, WebauthnChallengeStore

router = APIRouter(prefix="/auth", tags=["preconnect"])
settings = get_settings()


def _tid(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


def _ip(request: Request) -> str:
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _verify_preconnect_webauthn(db: Session, user: User, credential: dict) -> bool:
    row = db.get(WebauthnChallengeStore, user.id)
    if row is None or row.kind != "authenticate":
        return False
    if to_utc_aware(row.expires_at) < datetime.now(timezone.utc):
        db.delete(row)
        return False
    try:
        raw_id = credential.get("rawId")
        if not raw_id:
            return False
        method = find_webauthn_method_by_credential_id(db, user, raw_id)
        if method is None:
            return False
        data = json.loads(method.credential)
        cred_pub = base64.standard_b64decode(data["credential_public_key_b64"])
        sign_count = int(data["sign_count"])
        challenge_bytes = base64.b64decode(row.challenge.encode())
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge_bytes,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=settings.webauthn_origin,
            credential_public_key=cred_pub,
            credential_current_sign_count=sign_count,
            require_user_verification=True,
        )
        data["sign_count"] = verification.new_sign_count
        method.credential = serialize_webauthn_credential(data)
        method.last_used = datetime.now(timezone.utc)
        db.add(method)
        db.delete(row)
        return True
    except Exception:
        return False


@router.post("/preconnect-challenge", response_model=PreconnectChallengeResponse)
@limiter.limit(settings.rate_limit_preconnect)
def preconnect_challenge(
    request: Request,
    body: PreconnectChallengeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> PreconnectChallengeResponse:
    tpl = db.get(ContainerTemplate, body.template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace template not found")
    cid = str(uuid.uuid4())
    exp = datetime.now(timezone.utc) + timedelta(seconds=90)
    db.add(
        PreconnectChallenge(
            id=cid,
            user_id=user.id,
            template_id=body.template_id,
            expires_at=exp,
            used=False,
        )
    )
    db.commit()
    log_security_event(
        "preconnect_challenge",
        _ip(request),
        "SUCCESS",
        trace_id=_tid(request),
        user_id=str(user.id),
    )
    return PreconnectChallengeResponse(challenge_id=cid, expires_in=90)


@router.post("/preconnect-verify", response_model=PreconnectVerifyResponse)
@limiter.limit(settings.rate_limit_preconnect)
def preconnect_verify(
    request: Request,
    body: PreconnectVerifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> PreconnectVerifyResponse:
    ch = db.get(PreconnectChallenge, body.challenge_id)
    now = datetime.now(timezone.utc)
    if ch is None or ch.user_id != user.id or ch.used or to_utc_aware(ch.expires_at) < now:
        log_security_event(
            "preconnect_verify",
            _ip(request),
            "FAIL",
            trace_id=_tid(request),
            user_id=str(user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired challenge",
        )

    ok = False
    if body.totp_code and body.totp_code.strip():
        ok = totp_for_user(db, user, body.totp_code.strip())
    elif body.backup_code and body.backup_code.strip():
        ok = verify_backup_code(db, user, body.backup_code.strip(), settings)
    elif body.yubikey_otp and body.yubikey_otp.strip() and settings.yubikey_client_id:
        ok = yubikey_verify_otp_for_user(db, user, body.yubikey_otp.strip(), settings)
    elif body.webauthn:
        ok = _verify_preconnect_webauthn(db, user, body.webauthn)

    if not ok:
        log_security_event(
            "preconnect_verify",
            _ip(request),
            "FAIL",
            trace_id=_tid(request),
            user_id=str(user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA verification failed",
        )

    ch.used = True
    db.add(ch)
    db.commit()

    token = create_connect_token(user.id, ch.template_id, settings)
    log_security_event(
        "preconnect_verify",
        _ip(request),
        "SUCCESS",
        trace_id=_tid(request),
        user_id=str(user.id),
    )
    return PreconnectVerifyResponse(
        connect_token=token,
        expires_in=settings.connect_token_expire_minutes * 60,
    )
