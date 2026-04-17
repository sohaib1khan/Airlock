import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url, options_to_json
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from api.deps import (
    get_access_payload,
    get_current_user,
    get_current_user_for_mfa_enrollment,
    get_current_user_full_scope,
)
from api.schemas import (
    AccessTokenResponse,
    BackupRegenerateResponse,
    MfaMethodPatchRequest,
    MfaVerifyRequest,
    TotpBeginResponse,
    TotpConfirmRequest,
    TotpConfirmResponse,
    YubikeyEnrollRequest,
    WebAuthnFinishRequest,
)
from config import get_settings
from core.audit_log import log_security_event
from core.cookies import set_refresh_cookie
from core.public_url import webauthn_origin_for_request, webauthn_rp_id_for_request
from core.datetime_util import to_utc_aware
from core.limiter import limiter
from core.mfa_ops import (
    find_webauthn_method_by_credential_id,
    generate_backup_codes,
    serialize_webauthn_credential,
    totp_for_user,
    user_has_verified_mfa,
    verify_backup_code,
    parse_yubikey_credential_public_id,
    yubikey_otp_verify,
    yubikey_public_id_from_otp,
    yubikey_verify_otp_for_user,
)
from core.security import create_access_token, create_refresh_token
from db.database import get_db
from db.models import MFAMethod, MFAMethodType, User, WebauthnChallengeStore

router = APIRouter(prefix="/auth/mfa", tags=["mfa"])
settings = get_settings()


def _tid(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


def _ip(request: Request) -> str:
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _b64url_to_bytes(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _verify_webauthn_assertion(db: Session, user: User, credential: dict, request: Request) -> bool:
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
            expected_rp_id=webauthn_rp_id_for_request(request, settings),
            expected_origin=webauthn_origin_for_request(request, settings),
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


@router.post("/verify", response_model=AccessTokenResponse)
@limiter.limit(settings.rate_limit_mfa)
def mfa_verify(
    request: Request,
    response: Response,
    body: MfaVerifyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    payload: dict = Depends(get_access_payload),
) -> AccessTokenResponse:
    if payload.get("scope") == "full":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MFA already satisfied")

    ok = False
    if body.totp_code and body.totp_code.strip():
        ok = totp_for_user(db, user, body.totp_code.strip())
    elif body.backup_code and body.backup_code.strip():
        ok = verify_backup_code(db, user, body.backup_code.strip(), settings)
    elif body.yubikey_otp and body.yubikey_otp.strip():
        if settings.yubikey_client_id:
            ok = yubikey_verify_otp_for_user(db, user, body.yubikey_otp.strip(), settings)
    elif body.webauthn:
        ok = _verify_webauthn_assertion(db, user, body.webauthn, request)

    if not ok:
        log_security_event(
            "mfa_verify",
            _ip(request),
            "FAIL",
            trace_id=_tid(request),
            user_id=str(user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA verification failed",
        )

    db.commit()

    access = create_access_token(user.id, settings, "full")
    refresh = create_refresh_token(user.id, settings, mfa_satisfied=True)
    set_refresh_cookie(response, refresh, settings, request=request)
    log_security_event(
        "mfa_verify",
        _ip(request),
        "SUCCESS",
        trace_id=_tid(request),
        user_id=str(user.id),
    )
    return AccessTokenResponse(access_token=access)


@router.post("/totp/begin", response_model=TotpBeginResponse)
def totp_begin(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_for_mfa_enrollment),
) -> TotpBeginResponse:
    db.execute(
        delete(MFAMethod).where(
            MFAMethod.user_id == user.id,
            MFAMethod.method_type == MFAMethodType.TOTP,
            MFAMethod.verified.is_(False),
        )
    )
    secret = pyotp.random_base32()
    mid = str(uuid.uuid4())
    db.add(
        MFAMethod(
            id=mid,
            user_id=user.id,
            method_type=MFAMethodType.TOTP,
            credential=secret,
            nickname="Authenticator app",
            verified=False,
        )
    )
    db.commit()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=settings.app_name)
    return TotpBeginResponse(method_id=mid, otpauth_uri=uri)


@router.post("/totp/confirm", response_model=TotpConfirmResponse)
def totp_confirm(
    request: Request,
    response: Response,
    body: TotpConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_for_mfa_enrollment),
) -> TotpConfirmResponse:
    method = db.get(MFAMethod, body.method_id)
    if (
        method is None
        or method.user_id != user.id
        or method.method_type != MFAMethodType.TOTP
        or method.verified
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    totp = pyotp.TOTP(method.credential)
    if not totp.verify(body.code.strip(), valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")
    had_any_mfa = user_has_verified_mfa(db, user.id)
    method.verified = True
    db.add(method)
    codes: list[str] = []
    if not had_any_mfa:
        codes = generate_backup_codes(db, user, settings)
    db.commit()

    access_token: str | None = None
    if not had_any_mfa:
        access = create_access_token(user.id, settings, "full")
        refresh = create_refresh_token(user.id, settings, mfa_satisfied=True)
        set_refresh_cookie(response, refresh, settings, request=request)
        access_token = access
    return TotpConfirmResponse(backup_codes=codes, access_token=access_token)


@router.get("/enrollment-capabilities")
def enrollment_capabilities(
    _user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Which optional enrollment methods the server supports (e.g. YubiKey OTP needs API credentials)."""
    cid = (settings.yubikey_client_id or "").strip()
    return {"yubikey_otp": bool(cid)}


@router.post("/yubikey/enroll", response_model=TotpConfirmResponse)
def yubikey_enroll(
    request: Request,
    response: Response,
    body: YubikeyEnrollRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_for_mfa_enrollment),
) -> TotpConfirmResponse:
    if not (settings.yubikey_client_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "YubiKey OTP is not enabled on this server. "
                "An administrator must set YUBIKEY_CLIENT_ID (and optional YUBIKEY_SECRET_KEY)."
            ),
        )
    otp = body.otp
    pub = yubikey_public_id_from_otp(otp)
    if pub is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP format (expected 44 characters from a YubiKey slot)",
        )
    if not yubikey_otp_verify(otp, settings.yubikey_client_id, settings.yubikey_secret_key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="YubiKey OTP verification failed",
        )
    stmt = select(MFAMethod).where(
        MFAMethod.user_id == user.id,
        MFAMethod.method_type == MFAMethodType.YUBIKEY,
        MFAMethod.verified.is_(True),
    )
    for m in db.execute(stmt).scalars():
        if parse_yubikey_credential_public_id(m.credential) == pub:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This YubiKey is already enrolled",
            )

    had_any_mfa = user_has_verified_mfa(db, user.id)
    mid = str(uuid.uuid4())
    cred = json.dumps({"public_id": pub}, separators=(",", ":"))
    db.add(
        MFAMethod(
            id=mid,
            user_id=user.id,
            method_type=MFAMethodType.YUBIKEY,
            credential=cred,
            nickname="YubiKey OTP",
            verified=True,
        )
    )
    codes: list[str] = []
    if not had_any_mfa:
        codes = generate_backup_codes(db, user, settings)
    db.commit()

    access_token: str | None = None
    if not had_any_mfa:
        access = create_access_token(user.id, settings, "full")
        refresh = create_refresh_token(user.id, settings, mfa_satisfied=True)
        set_refresh_cookie(response, refresh, settings, request=request)
        access_token = access
    return TotpConfirmResponse(backup_codes=codes, access_token=access_token)


@router.get("/methods")
def list_methods(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> list[dict]:
    stmt = select(MFAMethod).where(
        MFAMethod.user_id == user.id,
        MFAMethod.verified.is_(True),
    )
    out = []
    for m in db.execute(stmt).scalars():
        out.append(
            {
                "id": m.id,
                "method_type": m.method_type.value,
                "nickname": m.nickname,
                "created_at": m.created_at.isoformat(),
            }
        )
    return out


@router.patch("/methods/{method_id}")
def patch_method(
    method_id: str,
    body: MfaMethodPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> dict:
    method = db.get(MFAMethod, method_id)
    if method is None or method.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not method.verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")
    method.nickname = body.nickname.strip()[:128]
    db.add(method)
    db.commit()
    db.refresh(method)
    return {
        "id": method.id,
        "method_type": method.method_type.value,
        "nickname": method.nickname,
        "created_at": method.created_at.isoformat(),
    }


@router.delete("/{method_id}")
def delete_method(
    method_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> dict[str, bool]:
    method = db.get(MFAMethod, method_id)
    if method is None or method.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not method.verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")
    n_verified = db.execute(
        select(func.count())
        .select_from(MFAMethod)
        .where(MFAMethod.user_id == user.id, MFAMethod.verified.is_(True))
    ).scalar_one()
    if int(n_verified) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove your only 2FA method. Add another method first, then remove this one.",
        )
    db.delete(method)
    db.commit()
    return {"ok": True}


@router.post("/backup/regenerate", response_model=BackupRegenerateResponse)
def backup_regenerate(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> BackupRegenerateResponse:
    if not user_has_verified_mfa(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complete MFA enrollment first",
        )
    codes = generate_backup_codes(db, user, settings)
    db.commit()
    return BackupRegenerateResponse(backup_codes=codes)


@router.post("/webauthn/register/begin")
def webauthn_register_begin(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_for_mfa_enrollment),
) -> dict:
    stmt = select(MFAMethod).where(
        MFAMethod.user_id == user.id,
        MFAMethod.method_type == MFAMethodType.WEBAUTHN,
        MFAMethod.verified.is_(True),
    )
    exclude: list[PublicKeyCredentialDescriptor] = []
    for m in db.execute(stmt).scalars():
        try:
            d = json.loads(m.credential)
            cid = _b64url_to_bytes(d["credential_id_b64url"])
            exclude.append(PublicKeyCredentialDescriptor(id=cid))
        except (KeyError, json.JSONDecodeError, ValueError, Exception):
            continue

    uid = user.id.encode("utf-8")[:64]
    opts = generate_registration_options(
        rp_id=webauthn_rp_id_for_request(request, settings),
        rp_name=settings.webauthn_rp_name,
        user_name=user.username,
        user_id=uid,
        user_display_name=user.username,
        exclude_credentials=exclude or None,
    )
    chal_b64 = base64.b64encode(opts.challenge).decode()
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    existing = db.get(WebauthnChallengeStore, user.id)
    if existing:
        db.delete(existing)
        db.flush()
    db.add(
        WebauthnChallengeStore(
            user_id=user.id,
            challenge=chal_b64,
            kind="register",
            expires_at=expires,
        )
    )
    db.commit()
    return json.loads(options_to_json(opts))


@router.post("/webauthn/register/finish")
def webauthn_register_finish(
    request: Request,
    response: Response,
    body: WebAuthnFinishRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_for_mfa_enrollment),
) -> dict[str, str]:
    row = db.get(WebauthnChallengeStore, user.id)
    if row is None or row.kind != "register":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active registration")
    if to_utc_aware(row.expires_at) < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Challenge expired")
    try:
        had_any_mfa = user_has_verified_mfa(db, user.id)
        expected_challenge = base64.b64decode(row.challenge.encode())
        verification = verify_registration_response(
            credential=body.credential,
            expected_challenge=expected_challenge,
            expected_rp_id=webauthn_rp_id_for_request(request, settings),
            expected_origin=webauthn_origin_for_request(request, settings),
            require_user_verification=True,
        )
        cid_b64url = bytes_to_base64url(verification.credential_id)
        cred_json = {
            "credential_id_b64url": cid_b64url,
            "credential_public_key_b64": base64.standard_b64encode(
                verification.credential_public_key
            ).decode(),
            "sign_count": verification.sign_count,
        }
        mid = str(uuid.uuid4())
        db.add(
            MFAMethod(
                id=mid,
                user_id=user.id,
                method_type=MFAMethodType.WEBAUTHN,
                credential=serialize_webauthn_credential(cred_json),
                nickname="Security key",
                verified=True,
            )
        )
        db.delete(row)
        db.flush()
        out: dict = {"method_id": mid}
        if not had_any_mfa:
            out["backup_codes"] = generate_backup_codes(db, user, settings)
            access = create_access_token(user.id, settings, "full")
            refresh = create_refresh_token(user.id, settings, mfa_satisfied=True)
            set_refresh_cookie(response, refresh, settings, request=request)
            out["access_token"] = access
            out["token_type"] = "bearer"
        db.commit()
        return out
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration verification failed",
        )


@router.post("/webauthn/authenticate/begin")
def webauthn_authenticate_begin(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    payload: dict = Depends(get_access_payload),
) -> dict:
    if payload.get("scope") != "limited":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WebAuthn MFA step only applies when MFA is required",
        )
    stmt = select(MFAMethod).where(
        MFAMethod.user_id == user.id,
        MFAMethod.method_type == MFAMethodType.WEBAUTHN,
        MFAMethod.verified.is_(True),
    )
    allow: list[PublicKeyCredentialDescriptor] = []
    for m in db.execute(stmt).scalars():
        try:
            d = json.loads(m.credential)
            raw = _b64url_to_bytes(d["credential_id_b64url"])
            allow.append(PublicKeyCredentialDescriptor(id=raw))
        except (KeyError, json.JSONDecodeError, ValueError, Exception):
            continue
    if not allow:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No security keys enrolled")
    opts = generate_authentication_options(
        rp_id=webauthn_rp_id_for_request(request, settings),
        allow_credentials=allow,
    )
    chal_b64 = base64.b64encode(opts.challenge).decode()
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    existing = db.get(WebauthnChallengeStore, user.id)
    if existing:
        db.delete(existing)
        db.flush()
    db.add(
        WebauthnChallengeStore(
            user_id=user.id,
            challenge=chal_b64,
            kind="authenticate",
            expires_at=expires,
        )
    )
    db.commit()
    return json.loads(options_to_json(opts))
