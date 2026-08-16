"""Add derived Quick Analyze insight groups for the product UI."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0011"
down_revision: str | None = "20260815_0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("quick_analyze_jobs", sa.Column("top_question_topics", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("quick_analyze_jobs", sa.Column("top_request_topics", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("quick_analyze_jobs", sa.Column("sentiment_summary", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("quick_analyze_jobs", sa.Column("top_matches", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("quick_analyze_jobs", "top_matches")
    op.drop_column("quick_analyze_jobs", "sentiment_summary")
    op.drop_column("quick_analyze_jobs", "top_request_topics")
    op.drop_column("quick_analyze_jobs", "top_question_topics")
