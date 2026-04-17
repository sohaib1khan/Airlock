import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class MFAMethodType(str, enum.Enum):
    TOTP = "TOTP"
    WEBAUTHN = "WEBAUTHN"
    YUBIKEY = "YUBIKEY"


class SessionStatus(str, enum.Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class AuditResult(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    force_password_reset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    creator: Mapped[Optional["User"]] = relationship(
        "User", remote_side=[id], foreign_keys=[created_by_id]
    )
    mfa_methods: Mapped[list["MFAMethod"]] = relationship("MFAMethod", back_populates="user")
    backup_codes: Mapped[list["BackupCode"]] = relationship("BackupCode", back_populates="user")
    container_templates: Mapped[list["ContainerTemplate"]] = relationship(
        "ContainerTemplate", back_populates="creator"
    )
    workspace_sessions: Mapped[list["WorkspaceSession"]] = relationship(
        "WorkspaceSession", back_populates="user"
    )
    preconnect_challenges: Mapped[list["PreconnectChallenge"]] = relationship(
        "PreconnectChallenge", back_populates="user"
    )
    webauthn_challenge: Mapped[Optional["WebauthnChallengeStore"]] = relationship(
        "WebauthnChallengeStore",
        back_populates="user",
        uselist=False,
    )


class MFAMethod(Base):
    __tablename__ = "mfa_methods"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method_type: Mapped[MFAMethodType] = mapped_column(
        Enum(MFAMethodType, native_enum=False, length=32), nullable=False
    )
    credential: Mapped[str] = mapped_column(Text, nullable=False)
    nickname: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="mfa_methods")


class WebauthnChallengeStore(Base):
    __tablename__ = "webauthn_challenges"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    challenge: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="webauthn_challenge")


class PreconnectChallenge(Base):
    __tablename__ = "preconnect_challenges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("container_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship("User", back_populates="preconnect_challenges")
    template: Mapped["ContainerTemplate"] = relationship(
        "ContainerTemplate", foreign_keys=[template_id]
    )


class BackupCode(Base):
    __tablename__ = "backup_codes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="backup_codes")


class ContainerTemplate(Base):
    __tablename__ = "container_templates"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    docker_image: Mapped[str] = mapped_column(String(512), nullable=False)
    tools: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    persistent_volume: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    volume_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    env_vars: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    resource_limits: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    max_runtime_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Home directory for file browser / uploads (e.g. /home/kuser, /home/kasm-user).
    workspace_home: Mapped[str] = mapped_column(String(512), nullable=False, default="/home/kuser")
    created_by_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creator: Mapped[Optional["User"]] = relationship(
        "User", back_populates="container_templates"
    )
    workspace_sessions: Mapped[list["WorkspaceSession"]] = relationship(
        "WorkspaceSession",
        back_populates="template",
        passive_deletes=True,
    )
    preconnect_challenges: Mapped[list["PreconnectChallenge"]] = relationship(
        "PreconnectChallenge",
        back_populates="template",
        passive_deletes=True,
    )


class WorkspaceSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("container_templates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    container_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, native_enum=False, length=32),
        nullable=False,
        default=SessionStatus.STARTING,
    )
    internal_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    vnc_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    session_token_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="workspace_sessions")
    template: Mapped["ContainerTemplate"] = relationship(
        "ContainerTemplate", back_populates="workspace_sessions"
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_ip: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    result: Mapped[AuditResult] = mapped_column(
        Enum(AuditResult, native_enum=False, length=32),
        nullable=False,
        default=AuditResult.SUCCESS,
    )
    meta: Mapped[Optional[Any]] = mapped_column("metadata", JSON, nullable=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[user_id])
