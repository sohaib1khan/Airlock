"""template workspace_home for file browser root

Revision ID: f9e8d7c6b5a4
Revises: e7f1a2b3c4d5
Create Date: 2026-04-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9e8d7c6b5a4"
down_revision: str | None = "e7f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("container_templates")}
    if "workspace_home" not in cols:
        op.add_column(
            "container_templates",
            sa.Column(
                "workspace_home",
                sa.String(length=512),
                nullable=False,
                server_default="/home/kuser",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("container_templates")}
    if "workspace_home" in cols:
        op.drop_column("container_templates", "workspace_home")
