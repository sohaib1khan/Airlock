import posixpath
import re

from pydantic import BaseModel, Field, field_validator


class SetupInitRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=12, max_length=256)

    @field_validator("username")
    @classmethod
    def username_chars(cls, v: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_]+", v):
            raise ValueError("username may contain only letters, digits, and underscores")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("password must contain at least one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("password must contain at least one symbol")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mfa_required: bool = False
    """True when the user must visit /mfa (verify) or /mfa/enroll (non-admin without MFA)."""
    mfa_enroll_required: bool = False
    """True when a non-admin must enroll at least one MFA method before using the app."""
    force_password_reset: bool = False


class MfaChallengeHints(BaseModel):
    """Which MFA factors apply on the /mfa challenge screen (limited-scope sessions)."""

    totp: bool
    webauthn: bool
    yubikey_otp: bool
    backup: bool


class UserMeResponse(BaseModel):
    id: str
    username: str
    is_admin: bool
    scope: str
    mfa_enrolled: bool
    mfa_enrollment_required: bool
    force_password_reset: bool
    mfa_hints: MfaChallengeHints | None = None


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MfaVerifyRequest(BaseModel):
    totp_code: str | None = None
    backup_code: str | None = None
    yubikey_otp: str | None = None
    webauthn: dict | None = None


class TotpBeginResponse(BaseModel):
    method_id: str
    otpauth_uri: str


class TotpConfirmRequest(BaseModel):
    method_id: str
    code: str = Field(..., min_length=6, max_length=12)


class TotpConfirmResponse(BaseModel):
    backup_codes: list[str] = Field(default_factory=list)
    access_token: str | None = None
    token_type: str = "bearer"


class YubikeyEnrollRequest(BaseModel):
    """44-character OTP emitted when the YubiKey is touched (Yubico OTP mode)."""

    otp: str = Field(..., min_length=1, max_length=96)

    @field_validator("otp")
    @classmethod
    def normalize_yubikey_otp(cls, v: str) -> str:
        o = v.strip()
        if len(o) != 44:
            raise ValueError("YubiKey OTP must be exactly 44 characters")
        if not o.isprintable():
            raise ValueError("invalid OTP characters")
        return o


class BackupRegenerateResponse(BaseModel):
    backup_codes: list[str]


class WebAuthnFinishRequest(BaseModel):
    credential: dict


class MfaMethodPatchRequest(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=128)


class PreconnectChallengeRequest(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=36)


class PreconnectChallengeResponse(BaseModel):
    challenge_id: str
    expires_in: int = 90


class PreconnectVerifyRequest(BaseModel):
    challenge_id: str
    totp_code: str | None = None
    backup_code: str | None = None
    yubikey_otp: str | None = None
    webauthn: dict | None = None


class PreconnectVerifyResponse(BaseModel):
    connect_token: str
    expires_in: int


class ContainerTemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    docker_image: str = Field(..., min_length=1, max_length=512)
    tools: list[str] = Field(default_factory=list)
    persistent_volume: bool = False
    volume_path: str | None = Field(default=None, max_length=512)
    env_vars: dict[str, str] = Field(default_factory=dict)
    resource_limits: dict[str, int | float] = Field(default_factory=dict)
    max_runtime_minutes: int | None = Field(default=None, ge=1, le=10080)
    workspace_home: str = Field(default="/home/kuser", max_length=512)

    @field_validator("workspace_home")
    @classmethod
    def workspace_home_absolute(cls, v: str) -> str:
        t = (v or "").strip() or "/home/kuser"
        if not t.startswith("/"):
            raise ValueError("workspace_home must be an absolute path (start with /)")
        return posixpath.normpath(t)

    @field_validator("volume_path")
    @classmethod
    def volume_path_is_absolute(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            return None
        if not trimmed.startswith("/"):
            raise ValueError("volume_path must be an absolute path (start with /)")
        return trimmed


class ContainerTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=2000)
    docker_image: str | None = Field(default=None, min_length=1, max_length=512)
    tools: list[str] | None = None
    persistent_volume: bool | None = None
    volume_path: str | None = Field(default=None, max_length=512)
    env_vars: dict[str, str] | None = None
    resource_limits: dict[str, int | float] | None = None
    max_runtime_minutes: int | None = Field(default=None, ge=1, le=10080)
    workspace_home: str | None = Field(default=None, max_length=512)

    @field_validator("workspace_home")
    @classmethod
    def update_workspace_home_absolute(cls, v: str | None) -> str | None:
        if v is None:
            return None
        t = v.strip()
        if not t:
            return None
        if not t.startswith("/"):
            raise ValueError("workspace_home must be an absolute path (start with /)")
        return posixpath.normpath(t)

    @field_validator("volume_path")
    @classmethod
    def update_volume_path_is_absolute(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            return None
        if not trimmed.startswith("/"):
            raise ValueError("volume_path must be an absolute path (start with /)")
        return trimmed


class ContainerTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    docker_image: str
    tools: list[str]
    persistent_volume: bool
    volume_path: str | None
    env_vars: dict[str, str]
    resource_limits: dict[str, int | float]
    max_runtime_minutes: int | None
    workspace_home: str
    created_at: str
    is_builtin: bool


class ContainerTemplateExportResponse(BaseModel):
    format_version: str
    exported_at: str
    template: ContainerTemplateCreateRequest


class ContainerTemplateImportRequest(BaseModel):
    format_version: str | None = None
    template: ContainerTemplateCreateRequest
    overwrite_existing: bool = False


class SessionStartRequest(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=36)
    connect_token: str = Field(..., min_length=1)
    launch_mode: str = Field(default="resume_existing")
    container_password: str | None = Field(default=None, min_length=4, max_length=128)


class SessionResponse(BaseModel):
    id: str
    template_id: str
    status: str
    container_id: str | None
    internal_ip: str | None
    started_at: str
    expires_at: str | None
    started_at_local: str
    expires_at_local: str | None = None
    server_timezone: str = "UTC"
    workspace_home: str
    proxy_path: str
    websocket_url: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=12, max_length=256)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("password must contain at least one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("password must contain at least one symbol")
        return v


class AdminUserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=12, max_length=256)
    is_admin: bool = False
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def username_chars(cls, v: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_]+", v):
            raise ValueError("username may contain only letters, digits, and underscores")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("password must contain at least one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("password must contain at least one symbol")
        return v


class AdminUserUpdateRequest(BaseModel):
    is_admin: bool | None = None
    is_active: bool | None = None
    force_password_reset: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.search(r"[A-Z]", v):
            raise ValueError("password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("password must contain at least one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("password must contain at least one symbol")
        return v


class AdminUserResponse(BaseModel):
    id: str
    username: str
    is_admin: bool
    is_active: bool
    force_password_reset: bool
    mfa_enrolled: bool
    created_by_id: str | None
    created_at: str
    last_login: str | None


class SessionRevokeResponse(BaseModel):
    id: str
    status: str
    revoked: bool


class AuditLogResponse(BaseModel):
    id: str
    timestamp: str
    event_type: str
    user_id: str | None
    source_ip: str
    result: str
    trace_id: str
    metadata: dict | None = None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    offset: int
    limit: int
