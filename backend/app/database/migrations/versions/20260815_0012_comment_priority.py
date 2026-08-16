"""Add deterministic comment relevance and priority scores."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0012"
down_revision: str | None = "20260815_0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("comment_analyses", sa.Column("relevance_score", sa.Float(), nullable=False, server_default="0"))
    op.add_column("comment_analyses", sa.Column("priority_score", sa.Float(), nullable=False, server_default="0"))
    op.execute("UPDATE comment_analyses SET relevance_score = confidence * 100, priority_score = confidence * 80")
    op.create_check_constraint("ck_comment_analyses_relevance_score", "comment_analyses", "relevance_score >= 0 AND relevance_score <= 100")
    op.create_check_constraint("ck_comment_analyses_priority_score", "comment_analyses", "priority_score >= 0 AND priority_score <= 100")


def downgrade() -> None:
    op.drop_constraint("ck_comment_analyses_priority_score", "comment_analyses", type_="check")
    op.drop_constraint("ck_comment_analyses_relevance_score", "comment_analyses", type_="check")
    op.drop_column("comment_analyses", "priority_score")
    op.drop_column("comment_analyses", "relevance_score")
