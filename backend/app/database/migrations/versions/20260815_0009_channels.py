"""Add creator channels and preserve existing video/comment data."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0009"
down_revision: str | None = "20260815_0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("youtube_channel_id", sa.String(128), nullable=False, unique=True),
        sa.Column("channel_title", sa.String(255), nullable=False),
        sa.Column("channel_url", sa.Text()),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("sync_status", sa.String(32), nullable=False, server_default="not_connected"),
        sa.Column("video_sync_status", sa.String(32), nullable=False, server_default="not_connected"),
        sa.Column("comment_sync_status", sa.String(32), nullable=False, server_default="not_connected"),
        sa.Column("index_status", sa.String(32), nullable=False, server_default="not_connected"),
        sa.Column("last_video_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_comment_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_full_sync_at", sa.DateTime(timezone=True)),
        sa.Column("videos_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("videos_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "sync_status IN ('not_connected','connecting','connected','syncing','fetching_videos','saving_videos','indexing_videos','fetching_comments','processing_comments','ready','failed')",
            name="ck_channels_sync_status",
        ),
        sa.CheckConstraint(
            "video_sync_status IN ('not_connected','pending','syncing','ready','failed')",
            name="ck_channels_video_sync_status",
        ),
        sa.CheckConstraint(
            "comment_sync_status IN ('not_connected','pending','syncing','ready','failed')",
            name="ck_channels_comment_sync_status",
        ),
        sa.CheckConstraint(
            "index_status IN ('not_connected','pending','syncing','ready','failed')",
            name="ck_channels_index_status",
        ),
    )
    op.add_column("videos", sa.Column("creator_channel_id", sa.BigInteger(), nullable=True))
    op.add_column("videos", sa.Column("youtube_url", sa.Text(), nullable=True))
    op.add_column("videos", sa.Column("thumbnail_url", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_videos_creator_channel_id_channels",
        "videos", "channels", ["creator_channel_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_videos_creator_channel_id", "videos", ["creator_channel_id"])
    op.add_column("comments", sa.Column("creator_channel_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_comments_creator_channel_id_channels",
        "comments", "channels", ["creator_channel_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_comments_creator_channel_id", "comments", ["creator_channel_id"])

    # Existing rows remain intact. Distinct YouTube channel IDs become channel rows,
    # videos are linked by their existing channel_id, and comments inherit the video link.
    op.execute("""
        INSERT INTO channels (
            youtube_channel_id, channel_title, channel_url,
            sync_status, video_sync_status, comment_sync_status, index_status,
            videos_discovered, videos_indexed, comments_imported
        )
        SELECT
            v.channel_id,
            MAX(v.channel_title),
            'https://www.youtube.com/channel/' || v.channel_id,
            'connected', 'ready', 'not_connected',
            CASE WHEN COUNT(vc.id) > 0 THEN 'ready' ELSE 'pending' END,
            COUNT(DISTINCT v.id), COUNT(DISTINCT vc.video_id), COUNT(DISTINCT c.id)
        FROM videos v
        LEFT JOIN video_chunks vc ON vc.video_id = v.id
        LEFT JOIN comments c ON c.video_id = v.id
        WHERE v.channel_id IS NOT NULL AND v.channel_id <> ''
        GROUP BY v.channel_id
        ON CONFLICT (youtube_channel_id) DO NOTHING
    """)
    op.execute("""
        UPDATE videos v
        SET creator_channel_id = c.id,
            youtube_url = COALESCE(v.youtube_url, 'https://www.youtube.com/watch?v=' || v.youtube_video_id)
        FROM channels c
        WHERE c.youtube_channel_id = v.channel_id
          AND v.creator_channel_id IS NULL
    """)
    op.execute("""
        UPDATE comments c
        SET creator_channel_id = v.creator_channel_id
        FROM videos v
        WHERE v.id = c.video_id
          AND c.creator_channel_id IS NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_comments_creator_channel_id", table_name="comments")
    op.drop_constraint("fk_comments_creator_channel_id_channels", "comments", type_="foreignkey")
    op.drop_column("comments", "creator_channel_id")
    op.drop_index("ix_videos_creator_channel_id", table_name="videos")
    op.drop_constraint("fk_videos_creator_channel_id_channels", "videos", type_="foreignkey")
    op.drop_column("videos", "creator_channel_id")
    op.drop_column("videos", "thumbnail_url")
    op.drop_column("videos", "youtube_url")
    op.drop_table("channels")
