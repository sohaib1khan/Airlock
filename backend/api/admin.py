import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import get_current_user_full_scope
from api.schemas import (
    AdminUserCreateRequest,
    AdminUserResponse,
    AdminUserUpdateRequest,
    AuditLogListResponse,
    AuditLogResponse,
    SessionRevokeResponse,
)
from core.audit_log import log_security_event
from core.mfa_ops import user_has_verified_mfa
from core.security import hash_password
from core.session_manager import get_session_manager
from db.database import get_db
from db.models import AuditLog, AuditResult, SessionStatus, User, WorkspaceSession

router = APIRouter(prefix="/admin", tags=["admin"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _user_response(db: Session, row: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=row.id,
        username=row.username,
        is_admin=row.is_admin,
        is_active=row.is_active,
        force_password_reset=bool(row.force_password_reset),
        mfa_enrolled=user_has_verified_mfa(db, row.id),
        created_by_id=row.created_by_id,
        created_at=row.created_at.isoformat() if row.created_at else "",
        last_login=row.last_login.isoformat() if row.last_login else None,
    )


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> list[AdminUserResponse]:
    _require_admin(user)
    rows = db.execute(select(User).order_by(User.created_at.desc(), User.username.asc())).scalars().all()
    return [_user_response(db, row) for row in rows]


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: Request,
    body: AdminUserCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> AdminUserResponse:
    _require_admin(user)
    exists = db.execute(select(User).where(User.username == body.username)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    row = User(
        id=str(uuid.uuid4()),
        username=body.username,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
        is_active=body.is_active,
        created_by_id=user.id,
        force_password_reset=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_security_event(
        "admin_user_create",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return _user_response(db, row)


@router.put("/users/{user_id}", response_model=AdminUserResponse)
def update_user(
    user_id: str,
    request: Request,
    body: AdminUserUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> AdminUserResponse:
    _require_admin(user)
    row = db.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if row.id == user.id and body.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate your own account")
    updates = body.model_dump(exclude_unset=True)
    if "password" in updates and updates["password"] is not None:
        row.password_hash = hash_password(updates.pop("password"))
        row.force_password_reset = True
    for key, value in updates.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_security_event(
        "admin_user_update",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return _user_response(db, row)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> dict[str, bool]:
    """Return JSON with a body (HTTP 200) so browsers/clients do not mishandle empty 204 DELETE responses."""
    _require_admin(user)
    row = db.get(User, user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if row.id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")
    try:
        db.delete(row)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete user: related data could not be removed",
        ) from None
    log_security_event(
        "admin_user_delete",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return {"ok": True}


@router.post("/sessions/{session_id}/revoke", response_model=SessionRevokeResponse)
def revoke_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> SessionRevokeResponse:
    _require_admin(user)
    row = db.get(WorkspaceSession, session_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    manager = get_session_manager()
    if row.status != SessionStatus.STOPPED:
        row = manager.stop_session(db, row)
    row.session_token_hash = None
    db.add(row)
    db.commit()
    db.refresh(row)
    log_security_event(
        "admin_session_revoke",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return SessionRevokeResponse(id=row.id, status=row.status.value, revoked=True)


@router.get("/audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    _request: Request,
    event_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    result: AuditResult | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> AuditLogListResponse:
    _require_admin(user)
    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)
    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)
        count_stmt = count_stmt.where(AuditLog.event_type == event_type)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
        count_stmt = count_stmt.where(AuditLog.user_id == user_id)
    if result:
        stmt = stmt.where(AuditLog.result == result)
        count_stmt = count_stmt.where(AuditLog.result == result)
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        stmt.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)
    ).scalars().all()
    return AuditLogListResponse(
        items=[
            AuditLogResponse(
                id=row.id,
                timestamp=row.timestamp.isoformat() if row.timestamp else "",
                event_type=row.event_type,
                user_id=row.user_id,
                source_ip=row.source_ip,
                result=row.result.value if isinstance(row.result, AuditResult) else str(row.result),
                trace_id=row.trace_id,
                metadata=row.meta if isinstance(row.meta, dict) else {},
            )
            for row in rows
        ],
        total=int(total),
        offset=offset,
        limit=limit,
    )
