import hashlib
import io
import logging
import posixpath
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from api.deps import get_current_user_full_scope
from api.schemas import SessionResponse, SessionStartRequest
from config import get_settings
from core.audit_log import log_security_event
from core.datetime_util import format_datetime_for_display, to_rfc3339_utc
from core.docker_manager import DockerManagerError, get_docker_manager
from core.security import decode_connect_token
from core.public_url import cookie_secure_for_request
from core.session_manager import SessionManagerError, build_session_ticket, get_session_manager
from db.database import get_db
from db.models import ContainerTemplate, SessionStatus, User, WorkspaceSession

router = APIRouter(prefix="/sessions", tags=["sessions"])
settings = get_settings()
logger = logging.getLogger("airlock.sessions")


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _workspace_home(db: Session, template_id: str) -> str:
    tpl = db.get(ContainerTemplate, template_id)
    if tpl is None:
        return "/home/kuser"
    raw = (tpl.workspace_home or "").strip()
    if not raw:
        return "/home/kuser"
    return posixpath.normpath(raw)


def _to_response(row: WorkspaceSession, db: Session) -> SessionResponse:
    tz = settings.airlock_timezone
    return SessionResponse(
        id=row.id,
        template_id=row.template_id,
        status=row.status.value,
        container_id=row.container_id,
        internal_ip=row.internal_ip,
        started_at=to_rfc3339_utc(row.started_at),
        expires_at=to_rfc3339_utc(row.expires_at) if row.expires_at else None,
        started_at_local=format_datetime_for_display(row.started_at, tz) or "",
        expires_at_local=format_datetime_for_display(row.expires_at, tz) if row.expires_at else None,
        server_timezone=tz,
        workspace_home=_workspace_home(db, row.template_id),
        proxy_path=f"/session/{row.id}",
        websocket_url=f"/ws/session/{row.id}",
    )


def _require_owned_session(db: Session, user: User, session_id: str) -> WorkspaceSession:
    row = db.get(WorkspaceSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return row


def _ticket_hash(ticket: str) -> str:
    return hashlib.sha256((settings.session_cookie_domain or "local").encode() + ticket.encode()).hexdigest()


def _set_session_ticket_cookie(response: Response, ticket: str, request: Request) -> None:
    response.set_cookie(
        key="session_ticket",
        value=ticket,
        httponly=True,
        secure=cookie_secure_for_request(request, settings),
        samesite="strict",
        path="/",
    )


def _rotate_session_ticket(db: Session, row: WorkspaceSession, response: Response, request: Request) -> None:
    ticket = build_session_ticket()
    row.session_token_hash = _ticket_hash(ticket)
    db.add(row)
    db.commit()
    db.refresh(row)
    _set_session_ticket_cookie(response, ticket, request)


def _normalize_workspace_path(path: str | None, root: str) -> str:
    root_norm = posixpath.normpath((root or "/home/kuser").strip() or "/home/kuser")
    if not path:
        return root_norm
    normalized = posixpath.normpath(path)
    if not normalized.startswith("/"):
        normalized = posixpath.normpath(f"{root_norm}/{normalized}")
    if not (normalized == root_norm or normalized.startswith(f"{root_norm}/")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path outside workspace")
    return normalized


def _require_file_ready_session(row: WorkspaceSession) -> str:
    if row.status == SessionStatus.STOPPED or not row.container_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not file-ready")
    return row.container_id


@router.post("/start", response_model=SessionResponse)
def start_session(
    request: Request,
    response: Response,
    body: SessionStartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> SessionResponse:
    try:
        token_payload = decode_connect_token(body.connect_token, settings)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid connect token")

    if token_payload.get("sub") != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Connect token does not belong to user")
    if token_payload.get("tpl") != body.template_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Connect token not valid for template")

    template = db.get(ContainerTemplate, body.template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    manager = get_session_manager()
    try:
        ws = manager.start_session(
            db,
            user=user,
            template=template,
            launch_mode=body.launch_mode,
            container_password=body.container_password if body.launch_mode == "force_new" else None,
        )
    except SessionManagerError as exc:
        if "Invalid launch mode" in str(exc):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        logger.warning("session_start failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    _rotate_session_ticket(db, ws, response, request)

    log_security_event(
        "session_start",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return _to_response(ws, db)


@router.get("", response_model=list[SessionResponse])
def list_sessions(
    _request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> list[SessionResponse]:
    stmt = (
        select(WorkspaceSession)
        .where(WorkspaceSession.user_id == user.id)
        .order_by(WorkspaceSession.started_at.desc())
    )
    sessions = db.execute(stmt).scalars().all()
    return [_to_response(s, db) for s in sessions]


@router.get("/{session_id}/metrics")
def session_metrics(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> dict:
    """Live CPU and memory snapshot from Docker for this workspace container."""
    row = _require_owned_session(db, user, session_id)
    if row.status in {SessionStatus.STOPPED, SessionStatus.ERROR} or not row.container_id:
        return {
            "available": False,
            "message": "Metrics are available only while the workspace has an active container.",
        }
    docker_manager = get_docker_manager()
    try:
        snap = docker_manager.get_container_resource_snapshot(row.container_id)
        return {"available": True, **snap}
    except DockerManagerError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc) or "Could not read container metrics",
        ) from exc


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    _request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> SessionResponse:
    row = db.get(WorkspaceSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return _to_response(row, db)


@router.post("/{session_id}/ticket", response_model=SessionResponse)
def issue_session_ticket(
    session_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> SessionResponse:
    row = _require_owned_session(db, user, session_id)
    _rotate_session_ticket(db, row, response, request)
    return _to_response(row, db)


@router.post("/{session_id}/stop", response_model=SessionResponse)
def stop_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> SessionResponse:
    row = _require_owned_session(db, user, session_id)
    manager = get_session_manager()
    row = manager.stop_session(db, row)
    log_security_event(
        "session_stop",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return _to_response(row, db)


@router.post("/{session_id}/pause", response_model=SessionResponse)
def pause_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> SessionResponse:
    row = _require_owned_session(db, user, session_id)
    if row.status == SessionStatus.STOPPED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stopped session cannot be paused")
    manager = get_session_manager()
    try:
        row = manager.pause_session(db, row)
    except SessionManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    log_security_event(
        "session_pause",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return _to_response(row, db)


@router.post("/{session_id}/resume", response_model=SessionResponse)
def resume_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> SessionResponse:
    row = _require_owned_session(db, user, session_id)
    if row.status == SessionStatus.STOPPED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stopped session cannot be resumed")
    manager = get_session_manager()
    try:
        row = manager.resume_session(db, row)
    except SessionManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    log_security_event(
        "session_resume",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return _to_response(row, db)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session_record(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> None:
    row = _require_owned_session(db, user, session_id)
    if row.status in {SessionStatus.RUNNING, SessionStatus.PAUSED, SessionStatus.STARTING}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stop the session before deleting its history",
        )
    db.delete(row)
    db.commit()
    log_security_event(
        "session_delete",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )


@router.post("/actions/cleanup", status_code=status.HTTP_200_OK)
def cleanup_session_history(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> dict[str, int]:
    result = db.execute(
        sa_delete(WorkspaceSession).where(
            WorkspaceSession.user_id == user.id,
            WorkspaceSession.status.in_([SessionStatus.STOPPED, SessionStatus.ERROR]),
        )
    )
    db.commit()
    deleted = int(result.rowcount or 0)
    log_security_event(
        "session_cleanup",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return {"deleted": deleted}


@router.get("/{session_id}/files")
def list_session_files(
    session_id: str,
    path: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> dict:
    row = _require_owned_session(db, user, session_id)
    container_id = _require_file_ready_session(row)
    root = _workspace_home(db, row.template_id)
    current = _normalize_workspace_path(path, root)
    docker_manager = get_docker_manager()
    try:
        cwd, items = docker_manager.list_files(container_id, current, workspace_root=root)
    except DockerManagerError as exc:
        detail = str(exc)
        if detail in {"path_not_found", "not_a_directory"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Directory not found")
        if detail == "path_outside_workspace":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Path outside workspace")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not list session files")
    return {
        "cwd": cwd,
        "items": items,
    }


@router.post("/{session_id}/upload")
async def upload_session_file(
    session_id: str,
    file: UploadFile = File(...),
    destination: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> dict:
    row = _require_owned_session(db, user, session_id)
    container_id = _require_file_ready_session(row)
    root = _workspace_home(db, row.template_id)
    safe_dest = _normalize_workspace_path(destination or root, root)
    safe_name = file.filename or "upload.bin"
    payload = await file.read()
    docker_manager = get_docker_manager()
    try:
        save_path = docker_manager.upload_file_bytes(
            container_id=container_id,
            destination_dir=safe_dest,
            filename=safe_name,
            content=payload,
        )
    except DockerManagerError as exc:
        detail = str(exc)
        if detail == "destination_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination directory not found")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not upload file")
    log_security_event("session_file_upload", "session", "SUCCESS", user_id=str(user.id))
    return {
        "ok": True,
        "filename": safe_name,
        "content_type": file.content_type,
        "saved_path": save_path,
        "message": "Upload stub accepted; container integration pending",
    }


@router.get("/{session_id}/download")
def download_session_file(
    session_id: str,
    path: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> StreamingResponse:
    row = _require_owned_session(db, user, session_id)
    container_id = _require_file_ready_session(row)
    root = _workspace_home(db, row.template_id)
    safe_path = _normalize_workspace_path(path, root)
    docker_manager = get_docker_manager()
    try:
        filename, file_bytes = docker_manager.download_file_bytes(container_id, safe_path)
    except DockerManagerError as exc:
        detail = str(exc)
        if detail == "file_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if detail == "Requested path is not a file":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Requested path is not a file")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not download file")
    payload = io.BytesIO(file_bytes)
    log_security_event("session_file_download", "session", "SUCCESS", user_id=str(user.id))
    return StreamingResponse(
        payload,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{session_id}/audio")
async def session_audio_proxy(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Proxy the container's WebM/Opus audio stream to the browser.

    Uses session_ticket cookie auth (same as the VNC WebSocket proxy) so the
    browser's <audio> element can authenticate without custom headers.
    """
    ticket = request.cookies.get("session_ticket")
    if not ticket:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session ticket")

    row = db.get(WorkspaceSession, session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if not row.session_token_hash or _ticket_hash(ticket) != row.session_token_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session ticket")
    if row.status != SessionStatus.RUNNING or not row.internal_ip or not row.vnc_port:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session not active")

    target_url = f"http://{row.internal_ip}:{row.vnc_port}/audio"

    async def _stream() -> AsyncGenerator[bytes, None]:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", target_url, timeout=None) as resp:
                async for chunk in resp.aiter_bytes(4096):
                    yield chunk

    return StreamingResponse(
        _stream(),
        media_type="audio/webm;codecs=opus",
        headers={"Cache-Control": "no-cache, no-store"},
    )
