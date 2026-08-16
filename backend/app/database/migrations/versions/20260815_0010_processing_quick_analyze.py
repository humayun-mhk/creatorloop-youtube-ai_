"""Add idempotent processing state and isolated Quick Analyze jobs."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0010"
down_revision: str | None = "20260815_0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("comments", sa.Column("knowledge_channel_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_comments_knowledge_channel_id_channels",
        "comments", "channels", ["knowledge_channel_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_comments_knowledge_channel_id", "comments", ["knowledge_channel_id"])
    op.add_column("comments", sa.Column("pipeline_status", sa.String(24), nullable=False, server_default="not_started"))
    op.add_column("comments", sa.Column("pipeline_outcome", sa.String(32), nullable=True))
    op.add_column("comments", sa.Column("pipeline_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("comments", sa.Column("pipeline_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE comments SET knowledge_channel_id = creator_channel_id WHERE knowledge_channel_id IS NULL")

    op.create_table(
        "quick_analyze_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False, unique=True),
        sa.Column("youtube_video_url", sa.Text(), nullable=False),
        sa.Column("youtube_video_id", sa.String(64), nullable=False),
        sa.Column("video_id", sa.BigInteger(), sa.ForeignKey("videos.id", ondelete="SET NULL")),
        sa.Column("knowledge_channel_id", sa.BigInteger(), sa.ForeignKey("channels.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("comments_analyzed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("existing_answer_matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unanswered_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("top_topics", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("top_opportunities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error_message", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('queued','running','complete','failed')", name="ck_quick_analyze_jobs_status"),
    )
    op.create_index("ix_quick_analyze_jobs_youtube_video_id", "quick_analyze_jobs", ["youtube_video_id"])
    op.create_table(
        "quick_analyze_comments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("job_id", sa.BigInteger(), sa.ForeignKey("quick_analyze_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("comment_id", sa.BigInteger(), sa.ForeignKey("comments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_quick_analyze_comments_job_id", "quick_analyze_comments", ["job_id"])
    op.create_index("ix_quick_analyze_comments_comment_id", "quick_analyze_comments", ["comment_id"])
    op.create_index("uq_quick_analyze_comments_job_comment", "quick_analyze_comments", ["job_id", "comment_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_quick_analyze_comments_job_comment", table_name="quick_analyze_comments")
    op.drop_index("ix_quick_analyze_comments_comment_id", table_name="quick_analyze_comments")
    op.drop_index("ix_quick_analyze_comments_job_id", table_name="quick_analyze_comments")
    op.drop_table("quick_analyze_comments")
    op.drop_index("ix_quick_analyze_jobs_youtube_video_id", table_name="quick_analyze_jobs")
    op.drop_table("quick_analyze_jobs")
    op.drop_column("comments", "pipeline_completed_at")
    op.drop_column("comments", "pipeline_started_at")
    op.drop_column("comments", "pipeline_outcome")
    op.drop_column("comments", "pipeline_status")
    op.drop_index("ix_comments_knowledge_channel_id", table_name="comments")
    op.drop_constraint("fk_comments_knowledge_channel_id_channels", "comments", type_="foreignkey")
    op.drop_column("comments", "knowledge_channel_id")
