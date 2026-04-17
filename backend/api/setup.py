from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import User


def admin_exists(db: Session) -> bool:
    stmt = select(User.id).where(User.is_admin.is_(True), User.is_active.is_(True)).limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None
