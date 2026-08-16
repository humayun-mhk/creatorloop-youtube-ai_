"""Persist Gemini's explicit reply decision for each analyzed comment."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260816_0014"
down_revision: str | None = "20260816_0013"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "comment_analyses",
        sa.Column("should_reply", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "comment_analyses",
        sa.Column("reply_reason", sa.String(500), nullable=False, server_default="Not evaluated"),
    )


def downgrade() -> None:
    op.drop_column("comment_analyses", "reply_reason")
    op.drop_column("comment_analyses", "should_reply")
