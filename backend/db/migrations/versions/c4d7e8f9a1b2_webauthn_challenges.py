"""webauthn_challenges

Revision ID: c4d7e8f9a1b2
Revises: b3a9c1d2e4f5
Create Date: 2026-04-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d7e8f9a1b2"
down_revision: Union[str, None] = "b3a9c1d2e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webauthn_challenges",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("challenge", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("webauthn_challenges")
