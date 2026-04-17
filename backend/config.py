from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = Field(default="Airlock", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_port: int = Field(default=8000, alias="APP_PORT")
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")

    database_url: str = Field(default="sqlite:///./data/airlock.db", alias="DATABASE_URL")
    # Extra static CORS origins (comma-separated). Often unnecessary: public URL is inferred from proxy headers.
    allowed_origins: str = Field(default="", alias="ALLOWED_ORIGINS")

    audit_log_file: str = Field(default="./data/audit.log", alias="AUDIT_LOG_FILE")
    audit_log_level: str = Field(default="INFO", alias="AUDIT_LOG_LEVEL")

    jwt_secret: str = Field(default="CHANGE_ME_GENERATE_WITH_OPENSSL", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_hours: int = Field(default=8, alias="REFRESH_TOKEN_EXPIRE_HOURS")

    session_cookie_domain: Optional[str] = Field(default=None, alias="SESSION_COOKIE_DOMAIN")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    # When true, X-Forwarded-Host / X-Forwarded-Proto shape CORS, WebAuthn, and cookie Secure flag.
    # Disable only if the API is exposed directly to untrusted clients (no reverse proxy).
    trust_forwarded_headers: bool = Field(default=True, alias="TRUST_FORWARDED_HEADERS")

    rate_limit_login: str = Field(default="5/minute", alias="RATE_LIMIT_LOGIN")
    rate_limit_setup: str = Field(default="10/minute", alias="RATE_LIMIT_SETUP")
    rate_limit_mfa: str = Field(default="10/minute", alias="RATE_LIMIT_MFA")
    rate_limit_preconnect: str = Field(default="10/minute", alias="RATE_LIMIT_PRECONNECT")

    connect_token_expire_minutes: int = Field(default=2, alias="CONNECT_TOKEN_EXPIRE_MINUTES")

    webauthn_rp_id: str = Field(default="localhost", alias="WEBAUTHN_RP_ID")
    webauthn_rp_name: str = Field(default="Airlock", alias="WEBAUTHN_RP_NAME")
    webauthn_origin: str = Field(default="http://localhost:5173", alias="WEBAUTHN_ORIGIN")

    yubikey_client_id: str = Field(default="", alias="YUBIKEY_CLIENT_ID")
    yubikey_secret_key: str = Field(default="", alias="YUBIKEY_SECRET_KEY")
    docker_socket: str = Field(default="/var/run/docker.sock", alias="DOCKER_SOCKET")
    internal_docker_network: str = Field(default="airlock_internal", alias="INTERNAL_DOCKER_NETWORK")
    container_cpu_limit: float = Field(default=2.0, alias="CONTAINER_CPU_LIMIT")
    container_memory_limit_mb: int = Field(default=2048, alias="CONTAINER_MEMORY_LIMIT_MB")
    container_vnc_ws_path: str = Field(default="/websockify", alias="CONTAINER_VNC_WS_PATH")
    # Override auto-discovery of repo pre-built templates (default: /app/Bastion_templates or ../Bastion_templates).
    builtin_templates_dir: Optional[str] = Field(default=None, alias="BUILTIN_TEMPLATES_DIR")

    # IANA timezone name for session time labels in the API (e.g. America/New_York). UTC if unset/invalid.
    airlock_timezone: str = Field(default="UTC", alias="AIRLOCK_TIMEZONE")

    @field_validator("session_cookie_domain", mode="before")
    @classmethod
    def empty_cookie_domain(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return v

    @field_validator("builtin_templates_dir", mode="before")
    @classmethod
    def empty_builtin_templates_dir(cls, v: object) -> object:
        if v is None or v == "":
            return None
        return v

    def builtin_templates_root(self) -> Path | None:
        """Directory containing *.airlock-template.yaml shipped with Airlock (Bastion_templates)."""
        if self.builtin_templates_dir:
            p = Path(self.builtin_templates_dir).expanduser()
            return p if p.is_dir() else None
        for candidate in (
            Path("/app/Bastion_templates"),
            Path(__file__).resolve().parent.parent / "Bastion_templates",
        ):
            if candidate.is_dir():
                return candidate
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
