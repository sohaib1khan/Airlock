"""phase2_mfa_preconnect

Revision ID: b3a9c1d2e4f5
Revises: ce84e1ece9b9
Create Date: 2026-04-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3a9c1d2e4f5"
down_revision: Union[str, None] = "ce84e1ece9b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mfa_methods",
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.create_table(
        "preconnect_challenges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["container_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_preconnect_challenges_user_id"), "preconnect_challenges", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_preconnect_challenges_user_id"), table_name="preconnect_challenges")
    op.drop_table("preconnect_challenges")
    op.drop_column("mfa_methods", "verified")
