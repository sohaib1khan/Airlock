"""phase5 admin users audit

Revision ID: d1a2b3c4d5e6
Revises: c4d7e8f9a1b2
Create Date: 2026-04-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1a2b3c4d5e6"
down_revision: str | None = "c4d7e8f9a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("users")}
    if "force_password_reset" not in existing:
        op.add_column(
            "users",
            sa.Column("force_password_reset", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("users")}
    if "force_password_reset" in existing:
        op.drop_column("users", "force_password_reset")
