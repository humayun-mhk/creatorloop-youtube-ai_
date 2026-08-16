"""Create demand clusters, memberships, and opportunities."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0007"
down_revision: str | None = "20260815_0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demand_clusters",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "cluster_memberships",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("cluster_id", sa.BigInteger(), sa.ForeignKey("demand_clusters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("comment_id", sa.BigInteger(), sa.ForeignKey("comments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cluster_memberships_cluster_id", "cluster_memberships", ["cluster_id"])
    op.create_index("uq_cluster_memberships_comment_id", "cluster_memberships", ["comment_id"], unique=True)
    op.create_table(
        "opportunities",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("cluster_id", sa.BigInteger(), sa.ForeignKey("demand_clusters.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("topic", sa.String(255), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("unique_users", sa.Integer(), nullable=False),
        sa.Column("total_engagement", sa.Integer(), nullable=False),
        sa.Column("latest_request_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("frequency_score", sa.Float(), nullable=False),
        sa.Column("engagement_score", sa.Float(), nullable=False),
        sa.Column("recency_score", sa.Float(), nullable=False),
        sa.Column("unique_users_score", sa.Float(), nullable=False),
        sa.Column("content_gap_score", sa.Float(), nullable=False),
        sa.Column("demand_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("demand_score >= 0 AND demand_score <= 100", name="ck_opportunities_demand_score"),
    )
    op.create_index("ix_opportunities_demand_score", "opportunities", ["demand_score"])


def downgrade() -> None:
    op.drop_index("ix_opportunities_demand_score", table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_index("uq_cluster_memberships_comment_id", table_name="cluster_memberships")
    op.drop_index("ix_cluster_memberships_cluster_id", table_name="cluster_memberships")
    op.drop_table("cluster_memberships")
    op.drop_table("demand_clusters")
