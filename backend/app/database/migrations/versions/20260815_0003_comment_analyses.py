"""Create comment analyses table."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0003"
down_revision: str | None = "20260815_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comment_analyses",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("comment_id", sa.BigInteger(), sa.ForeignKey("comments.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("intent", sa.String(32), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("sentiment", sa.String(16), nullable=False),
        sa.Column("is_question", sa.Boolean(), nullable=False),
        sa.Column("is_content_request", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("intent IN ('question','content_request','complaint','feedback','praise','spam','other')", name="ck_comment_analyses_intent"),
        sa.CheckConstraint("sentiment IN ('positive','neutral','negative')", name="ck_comment_analyses_sentiment"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_comment_analyses_confidence"),
    )


def downgrade() -> None:
    op.drop_table("comment_analyses")
