import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pyotp
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from config import Settings
from db.models import BackupCode, MFAMethod, MFAMethodType, User


def mfa_challenge_hints(db: Session, user: User, settings: Settings) -> dict[str, bool]:
    """Which second-factor options apply for this user at MFA verify time (limited scope)."""
    stmt = select(MFAMethod.method_type).where(
        MFAMethod.user_id == user.id,
        MFAMethod.verified.is_(True),
    )
    types = set(db.execute(stmt).scalars().all())
    n_unused = db.execute(
        select(func.count())
        .select_from(BackupCode)
        .where(BackupCode.user_id == user.id, BackupCode.used.is_(False))
    ).scalar_one()
    yk_server = bool((settings.yubikey_client_id or "").strip())
    return {
        "totp": MFAMethodType.TOTP in types,
        "webauthn": MFAMethodType.WEBAUTHN in types,
        "yubikey_otp": MFAMethodType.YUBIKEY in types and yk_server,
        "backup": int(n_unused or 0) > 0,
    }


def user_has_verified_mfa(db: Session, user_id: str) -> bool:
    stmt = (
        select(func.count())
        .select_from(MFAMethod)
        .where(MFAMethod.user_id == user_id, MFAMethod.verified.is_(True))
    )
    n = db.execute(stmt).scalar_one()
    return int(n) > 0


def totp_for_user(db: Session, user: User, code: str) -> bool:
    stmt = select(MFAMethod).where(
        MFAMethod.user_id == user.id,
        MFAMethod.method_type == MFAMethodType.TOTP,
        MFAMethod.verified.is_(True),
    )
    for method in db.execute(stmt).scalars():
        secret = method.credential.strip()
        totp = pyotp.TOTP(secret)
        if totp.verify(code, valid_window=1):
            method.last_used = datetime.now(timezone.utc)
            db.add(method)
            return True
    return False


def hash_backup_code(normalized: str, settings: Settings) -> str:
    pepper = settings.jwt_secret.encode()
    return hashlib.sha256(pepper + normalized.encode()).hexdigest()


def verify_backup_code(db: Session, user: User, code: str, settings: Settings) -> bool:
    normalized = code.strip().replace(" ", "").replace("-", "").lower()
    digest = hash_backup_code(normalized, settings)
    stmt = select(BackupCode).where(
        BackupCode.user_id == user.id,
        BackupCode.code_hash == digest,
        BackupCode.used.is_(False),
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return False
    row.used = True
    row.used_at = datetime.now(timezone.utc)
    db.add(row)
    return True


def generate_backup_codes(db: Session, user: User, settings: Settings, count: int = 10) -> list[str]:
    db.execute(delete(BackupCode).where(BackupCode.user_id == user.id))
    codes: list[str] = []
    for _ in range(count):
        part_a = secrets.token_hex(2)
        part_b = secrets.token_hex(2)
        plain = f"{part_a}-{part_b}"
        codes.append(plain)
        db.add(
            BackupCode(
                id=str(uuid.uuid4()),
                user_id=user.id,
                code_hash=hash_backup_code(plain.replace("-", "").lower(), settings),
                used=False,
            )
        )
    return codes


def parse_webauthn_credential(raw: str) -> dict[str, Any]:
    return json.loads(raw)


def serialize_webauthn_credential(data: dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"))


def _norm_b64url(s: str) -> str:
    return (s or "").strip().rstrip("=")


def find_webauthn_method_by_credential_id(
    db: Session, user: User, credential_id_b64url: str
) -> Optional[MFAMethod]:
    want = _norm_b64url(credential_id_b64url)
    stmt = select(MFAMethod).where(
        MFAMethod.user_id == user.id,
        MFAMethod.method_type == MFAMethodType.WEBAUTHN,
        MFAMethod.verified.is_(True),
    )
    for method in db.execute(stmt).scalars():
        try:
            data = parse_webauthn_credential(method.credential)
            if _norm_b64url(data.get("credential_id_b64url", "")) == want:
                return method
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def yubikey_otp_verify(otp: str, client_id: str, secret_key: str) -> bool:
    import requests

    if not client_id or len(otp) != 44 or not otp.isprintable():
        return False
    nonce = secrets.token_hex(16)
    params = {"id": client_id, "otp": otp, "nonce": nonce}
    for host in ("https://api.yubico.com/wsapi/2.0/verify", "https://api2.yubico.com/wsapi/2.0/verify"):
        try:
            r = requests.get(host, params=params, timeout=5)
            text = r.text
            if "status=OK" not in text:
                continue
            if f"nonce={nonce}" not in text.replace(" ", ""):
                continue
            if secret_key:
                sig_line = [ln for ln in text.splitlines() if ln.startswith("h=")]
                if not sig_line:
                    continue
                body_for_sig = text.split("h=")[0].rstrip()
                expected = hmac.new(
                    secret_key.encode(),
                    body_for_sig.encode(),
                    hashlib.sha1,
                ).hexdigest()
                if expected != sig_line[0][2:].strip():
                    continue
            return True
        except requests.RequestException:
            continue
    return False


YUBIKEY_OTP_LENGTH = 44
YUBIKEY_PUBLIC_ID_LENGTH = 12


def yubikey_public_id_from_otp(otp: str) -> Optional[str]:
    """First 12 modhex characters of a 44-char YubiKey OTP identify the key."""
    o = otp.strip()
    if len(o) != YUBIKEY_OTP_LENGTH or not o.isprintable():
        return None
    return o[:YUBIKEY_PUBLIC_ID_LENGTH]


def parse_yubikey_credential_public_id(credential: str) -> Optional[str]:
    try:
        d = json.loads(credential)
        pid = d.get("public_id")
        if isinstance(pid, str) and len(pid) == YUBIKEY_PUBLIC_ID_LENGTH:
            return pid
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def yubikey_verify_otp_for_user(
    db: Session, user: User, otp: str, settings: Settings
) -> bool:
    """Verify a YubiKey OTP against Yubico and ensure it matches an enrolled key for this user."""
    if not settings.yubikey_client_id:
        return False
    otp = otp.strip()
    pub = yubikey_public_id_from_otp(otp)
    if pub is None:
        return False
    if not yubikey_otp_verify(otp, settings.yubikey_client_id, settings.yubikey_secret_key):
        return False
    stmt = select(MFAMethod).where(
        MFAMethod.user_id == user.id,
        MFAMethod.method_type == MFAMethodType.YUBIKEY,
        MFAMethod.verified.is_(True),
    )
    for method in db.execute(stmt).scalars():
        stored = parse_yubikey_credential_public_id(method.credential)
        if stored == pub:
            method.last_used = datetime.now(timezone.utc)
            db.add(method)
            return True
    return False
