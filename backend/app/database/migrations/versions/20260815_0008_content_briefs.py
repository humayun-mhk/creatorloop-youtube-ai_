"""Create stored content briefs."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0008"
down_revision: str | None = "20260815_0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_briefs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("opportunity_id", sa.BigInteger(), sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("suggested_title", sa.String(500), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("audience_pain", sa.Text(), nullable=False),
        sa.Column("why_users_want", sa.Text(), nullable=False),
        sa.Column("video_outline", sa.JSON(), nullable=False),
        sa.Column("faqs", sa.JSON(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("representative_comments", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("content_briefs")
