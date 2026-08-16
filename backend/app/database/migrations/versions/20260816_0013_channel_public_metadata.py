"""Store richer public YouTube channel metadata."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260816_0013"
down_revision: str | None = "20260815_0012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("channels", sa.Column("custom_url", sa.String(255), nullable=True))
    op.add_column("channels", sa.Column("description", sa.Text(), nullable=False, server_default=""))
    op.add_column("channels", sa.Column("country", sa.String(16), nullable=True))
    op.add_column("channels", sa.Column("default_language", sa.String(32), nullable=True))
    op.add_column("channels", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("channels", sa.Column("uploads_playlist_id", sa.String(128), nullable=True))
    op.add_column("channels", sa.Column("subscriber_count", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("channels", sa.Column("hidden_subscriber_count", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("channels", sa.Column("channel_view_count", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("channels", sa.Column("public_video_count", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("channels", sa.Column("keywords", sa.Text(), nullable=True))
    op.add_column("channels", sa.Column("topic_categories", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("channels", sa.Column("privacy_status", sa.String(32), nullable=True))
    op.add_column("channels", sa.Column("made_for_kids", sa.Boolean(), nullable=True))


def downgrade() -> None:
    for column in (
        "made_for_kids", "privacy_status", "topic_categories", "keywords",
        "public_video_count", "channel_view_count", "hidden_subscriber_count",
        "subscriber_count", "uploads_playlist_id", "published_at",
        "default_language", "country", "description", "custom_url",
    ):
        op.drop_column("channels", column)
