import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from core.datetime_util import to_utc_aware
from core.session_manager import get_session_manager
from db.database import SessionLocal
from db.models import SessionStatus, WorkspaceSession

logger = logging.getLogger("airlock.session_expiry")


def stop_expired_sessions_once() -> int:
    """Stop sessions past their configured expiry timestamp."""
    db = SessionLocal()
    stopped = 0
    try:
        now = datetime.now(timezone.utc)
        rows = (
            db.execute(
                select(WorkspaceSession).where(
                    WorkspaceSession.status.in_([SessionStatus.RUNNING, SessionStatus.PAUSED]),
                    WorkspaceSession.expires_at.is_not(None),
                )
            )
            .scalars()
            .all()
        )
        manager = get_session_manager()
        for row in rows:
            if row.expires_at is None:
                continue
            if to_utc_aware(row.expires_at) > now:
                continue
            try:
                manager.stop_session(db, row)
                stopped += 1
            except Exception:
                logger.exception("Failed to stop expired session %s", row.id)
        return stopped
    finally:
        db.close()


async def session_expiry_loop(interval_seconds: int = 30) -> None:
    while True:
        try:
            n = stop_expired_sessions_once()
            if n:
                logger.info("Stopped %d expired session(s)", n)
        except Exception:
            logger.exception("Session expiry sweep failed")
        await asyncio.sleep(interval_seconds)
