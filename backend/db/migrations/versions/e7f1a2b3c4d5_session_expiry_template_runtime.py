"""session expiry and template runtime

Revision ID: e7f1a2b3c4d5
Revises: d1a2b3c4d5e6
Create Date: 2026-04-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f1a2b3c4d5"
down_revision: str | None = "d1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    template_columns = {col["name"] for col in inspector.get_columns("container_templates")}
    if "max_runtime_minutes" not in template_columns:
        op.add_column(
            "container_templates",
            sa.Column("max_runtime_minutes", sa.Integer(), nullable=True),
        )

    session_columns = {col["name"] for col in inspector.get_columns("sessions")}
    if "expires_at" not in session_columns:
        op.add_column(
            "sessions",
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    session_columns = {col["name"] for col in inspector.get_columns("sessions")}
    if "expires_at" in session_columns:
        op.drop_column("sessions", "expires_at")

    template_columns = {col["name"] for col in inspector.get_columns("container_templates")}
    if "max_runtime_minutes" in template_columns:
        op.drop_column("container_templates", "max_runtime_minutes")
