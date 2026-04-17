import logging
from pathlib import Path
from typing import Optional

from config import get_settings
from db.database import SessionLocal
from db.models import AuditLog, AuditResult

settings = get_settings()


def setup_audit_logger() -> logging.Logger:
    log_path = Path(settings.audit_log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("audit")
    logger.setLevel(settings.audit_log_level.upper())

    if not logger.handlers:
        handler = logging.FileHandler(log_path)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


audit_logger = setup_audit_logger()


def log_security_event(
    event_type: str,
    source_ip: str,
    result: str = "SUCCESS",
    *,
    trace_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> None:
    audit_logger.info(
        "event_type=%s source_ip=%s result=%s trace_id=%s user_id=%s",
        event_type,
        source_ip,
        result,
        trace_id or "-",
        user_id or "-",
    )
    db = SessionLocal()
    try:
        db.add(
            AuditLog(
                event_type=event_type,
                source_ip=source_ip or "unknown",
                user_agent="",
                result=AuditResult(result),
                user_id=user_id,
                trace_id=trace_id or "",
                meta={},
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
