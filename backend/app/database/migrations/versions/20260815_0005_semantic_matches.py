"""Persist semantic matches for comments."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0005"
down_revision: str | None = "20260815_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "semantic_matches",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("comment_id", sa.BigInteger(), sa.ForeignKey("comments.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("video_chunk_id", sa.BigInteger(), sa.ForeignKey("video_chunks.id", ondelete="SET NULL")),
        sa.Column("match_found", sa.Boolean(), nullable=False),
        sa.Column("similarity", sa.Float()),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(128), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("candidates", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("similarity IS NULL OR (similarity >= -1 AND similarity <= 1)", name="ck_semantic_matches_similarity"),
    )


def downgrade() -> None:
    op.drop_table("semantic_matches")
