import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from core.datetime_util import to_utc_aware
from core.docker_manager import DockerManagerError, get_docker_manager
from core.network_manager import NetworkManager
from db.models import ContainerTemplate, SessionStatus, User, WorkspaceSession

settings = get_settings()


def _workspace_data_volume_name(user_id: str, template_id: str) -> str:
    """Stable Docker volume per user + template for persistent workspace data."""
    digest = hashlib.sha256(f"{user_id}:{template_id}".encode()).hexdigest()[:32]
    return f"airlock_ws_{digest}"


class SessionManagerError(RuntimeError):
    pass


class SessionManager:
    def __init__(self) -> None:
        self._docker = get_docker_manager()
        self._network = NetworkManager(self._docker)

    @staticmethod
    def _session_expired(ws: WorkspaceSession) -> bool:
        if ws.expires_at is None:
            return False
        return to_utc_aware(ws.expires_at) <= datetime.now(timezone.utc)

    def start_session(
        self,
        db: Session,
        *,
        user: User,
        template: ContainerTemplate,
        launch_mode: str = "resume_existing",
        container_password: str | None = None,
    ) -> WorkspaceSession:
        existing = db.execute(
            select(WorkspaceSession)
            .where(
                WorkspaceSession.user_id == user.id,
                WorkspaceSession.template_id == template.id,
                WorkspaceSession.status.in_([SessionStatus.RUNNING, SessionStatus.PAUSED]),
            )
            .order_by(WorkspaceSession.started_at.desc())
        ).scalars().first()
        if launch_mode not in {"resume_existing", "force_new"}:
            raise SessionManagerError("Invalid launch mode")

        if existing is not None and launch_mode == "resume_existing":
            if self._session_expired(existing):
                existing = self.stop_session(db, existing)
            else:
                if existing.status == SessionStatus.PAUSED:
                    return self.resume_session(db, existing)
                return existing

        session_id = str(uuid.uuid4())
        container_name = f"airlock-{user.id[:8]}-{session_id[:8]}"
        use_pv = bool(template.persistent_volume)
        mount_path = (template.volume_path or "").strip() or "/home/kuser/workspace"
        vol_name = _workspace_data_volume_name(user.id, template.id) if use_pv else None
        env = dict(template.env_vars or {})
        if container_password:
            env["CONTAINER_PASSWORD"] = container_password
        try:
            runtime = self._docker.start_workspace_container(
                image=template.docker_image,
                name=container_name,
                env=env,
                persistent_volume=use_pv,
                named_volume_name=vol_name,
                volume_mount_path=mount_path if use_pv else None,
            )
            internal_ip = self._docker.get_container_network_ip(
                runtime.container_id,
                settings.internal_docker_network,
            )
        except DockerManagerError as exc:
            raise SessionManagerError(str(exc)) from exc

        ws = WorkspaceSession(
            id=session_id,
            user_id=user.id,
            template_id=template.id,
            container_id=runtime.container_id,
            status=SessionStatus.RUNNING,
            internal_ip=internal_ip,
            vnc_port=6901,
            started_at=datetime.now(timezone.utc),
            expires_at=(
                datetime.now(timezone.utc) + timedelta(minutes=template.max_runtime_minutes)
                if template.max_runtime_minutes
                else None
            ),
            session_token_hash=None,
        )
        db.add(ws)
        db.commit()
        db.refresh(ws)
        return ws

    def stop_session(self, db: Session, ws: WorkspaceSession) -> WorkspaceSession:
        if ws.container_id:
            try:
                self._network.detach_internal_network(ws.container_id)
            except DockerManagerError:
                pass
            try:
                self._docker.stop_container(ws.container_id)
            except DockerManagerError:
                pass
        ws.status = SessionStatus.STOPPED
        ws.ended_at = datetime.now(timezone.utc)
        db.add(ws)
        db.commit()
        db.refresh(ws)
        return ws

    def pause_session(self, db: Session, ws: WorkspaceSession) -> WorkspaceSession:
        if not ws.container_id:
            raise SessionManagerError("Session has no container")
        try:
            self._docker.pause_container(ws.container_id)
        except DockerManagerError as exc:
            raise SessionManagerError(str(exc)) from exc
        ws.status = SessionStatus.PAUSED
        db.add(ws)
        db.commit()
        db.refresh(ws)
        return ws

    def resume_session(self, db: Session, ws: WorkspaceSession) -> WorkspaceSession:
        if not ws.container_id:
            raise SessionManagerError("Session has no container")
        if self._session_expired(ws):
            self.stop_session(db, ws)
            raise SessionManagerError("Session has expired and was stopped")
        try:
            self._docker.resume_container(ws.container_id)
            ws.internal_ip = self._docker.get_container_network_ip(
                ws.container_id,
                settings.internal_docker_network,
            )
        except DockerManagerError as exc:
            raise SessionManagerError(str(exc)) from exc
        ws.status = SessionStatus.RUNNING
        ws.ended_at = None
        db.add(ws)
        db.commit()
        db.refresh(ws)
        return ws


def build_session_ticket() -> str:
    return secrets.token_urlsafe(32)


session_manager_singleton: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global session_manager_singleton
    if session_manager_singleton is None:
        session_manager_singleton = SessionManager()
    return session_manager_singleton
