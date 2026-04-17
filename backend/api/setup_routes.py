import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import SetupInitRequest
from api.setup import admin_exists
from config import get_settings
from core.audit_log import log_security_event
from core.limiter import limiter
from core.security import hash_password
from db.database import get_db
from db.models import User

router = APIRouter(prefix="/setup", tags=["setup"])
settings = get_settings()


@router.get("/status")
def setup_status(db: Session = Depends(get_db)) -> dict[str, bool]:
    return {"requires_setup": not admin_exists(db)}


@router.post("/init", status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_setup)
def setup_init(
    request: Request,
    body: SetupInitRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    tid = getattr(request.state, "trace_id", None)

    if admin_exists(db):
        log_security_event("setup_init_blocked", _client_ip(request), "BLOCKED", trace_id=tid)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Setup already completed")

    stmt = select(User).where(User.username == body.username)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    user = User(
        id=str(uuid.uuid4()),
        username=body.username,
        password_hash=hash_password(body.password),
        is_admin=True,
        is_active=True,
        created_by_id=None,
    )
    db.add(user)
    db.commit()

    log_security_event(
        "setup_init",
        _client_ip(request),
        "SUCCESS",
        trace_id=tid,
        user_id=str(user.id),
    )
    return {"message": "Admin user created"}


def _client_ip(request: Request) -> str:
    if request.client:
        return request.client.host or "unknown"
    return "unknown"
