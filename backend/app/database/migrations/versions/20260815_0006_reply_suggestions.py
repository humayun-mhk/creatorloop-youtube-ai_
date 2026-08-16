"""Create personalized reply suggestions."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0006"
down_revision: str | None = "20260815_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reply_suggestions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("comment_id", sa.BigInteger(), sa.ForeignKey("comments.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("suggested_reply", sa.Text(), nullable=False),
        sa.Column("edited_reply", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_approval"),
        sa.Column("matched_video_id", sa.BigInteger(), sa.ForeignKey("videos.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("youtube_reply_id", sa.String(128)),
        sa.CheckConstraint("status IN ('pending_approval','approved','ignored','publishing','published','failed')", name="ck_reply_suggestions_status"),
        sa.CheckConstraint("similarity >= -1 AND similarity <= 1", name="ck_reply_suggestions_similarity"),
    )


def downgrade() -> None:
    op.drop_table("reply_suggestions")
