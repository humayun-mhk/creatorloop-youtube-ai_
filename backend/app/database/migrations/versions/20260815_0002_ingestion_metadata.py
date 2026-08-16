"""Add YouTube metadata used by ingestion."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0002"
down_revision: str | None = "20260815_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("category_id", sa.String(32)))
    op.add_column("videos", sa.Column("default_language", sa.String(32)))
    op.add_column("videos", sa.Column("default_audio_language", sa.String(32)))
    op.add_column("videos", sa.Column("live_broadcast_content", sa.String(32)))
    op.add_column("comments", sa.Column("author_channel_url", sa.Text()))


def downgrade() -> None:
    op.drop_column("comments", "author_channel_url")
    op.drop_column("videos", "live_broadcast_content")
    op.drop_column("videos", "default_audio_language")
    op.drop_column("videos", "default_language")
    op.drop_column("videos", "category_id")
