"""Create video chunks with pgvector embeddings."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

revision: str = "20260815_0004"
down_revision: str | None = "20260815_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "video_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "video_id",
            sa.BigInteger(),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float()),
        sa.Column("end_time", sa.Float()),
        sa.Column("embedding", VECTOR(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_video_chunks_video_id", "video_chunks", ["video_id"])
    op.create_index(
        "uq_video_chunks_video_chunk_index",
        "video_chunks",
        ["video_id", "chunk_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_video_chunks_video_chunk_index", table_name="video_chunks")
    op.drop_index("ix_video_chunks_video_id", table_name="video_chunks")
    op.drop_table("video_chunks")
