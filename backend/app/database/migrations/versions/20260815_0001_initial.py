"""Create videos and comments tables and enable pgvector."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    processing_status = postgresql.ENUM(
        "pending",
        "processing",
        "completed",
        "failed",
        "ignored",
        name="processing_status",
        create_type=False,
    )
    processing_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "videos",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("youtube_video_id", sa.String(64), nullable=False, unique=True),
        sa.Column("channel_id", sa.String(128), nullable=False),
        sa.Column("channel_title", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("duration", sa.String(32)),
        sa.Column("definition", sa.String(16)),
        sa.Column("caption_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("view_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("like_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("comment_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "comments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("youtube_comment_id", sa.String(128), nullable=False, unique=True),
        sa.Column("youtube_thread_id", sa.String(128), nullable=False),
        sa.Column("video_id", sa.BigInteger(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_name", sa.String(255), nullable=False),
        sa.Column("author_channel_id", sa.String(128)),
        sa.Column("author_profile_image_url", sa.Text()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reply_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("can_reply", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_status", processing_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_comments_processing_status", "comments", ["processing_status"])


def downgrade() -> None:
    op.drop_index("ix_comments_processing_status", table_name="comments")
    op.drop_table("comments")
    op.drop_table("videos")
    sa.Enum(name="processing_status").drop(op.get_bind(), checkfirst=True)
