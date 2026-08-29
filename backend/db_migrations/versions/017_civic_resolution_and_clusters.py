from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "017_civic_resolution_clusters"
down_revision: Union[str, None] = "016_civic_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "civic_issue_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column("issue_type", sa.String(40), nullable=False),
        sa.Column("centroid_latitude", sa.Float(), nullable=False),
        sa.Column("centroid_longitude", sa.Float(), nullable=False),
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_civic_issue_clusters_city", "civic_issue_clusters", ["city"])
    op.create_index(
        "ix_civic_issue_clusters_issue_type", "civic_issue_clusters", ["issue_type"]
    )

    op.add_column(
        "civic_issues",
        sa.Column("resolution_photo_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "civic_issues", sa.Column("resolution_notes", sa.Text(), nullable=True)
    )
    op.add_column(
        "civic_issues",
        sa.Column("work_order_reference", sa.String(200), nullable=True),
    )
    op.add_column(
        "civic_issues",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "civic_issues",
        sa.Column(
            "resolved_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "civic_issues",
        sa.Column("ai_verification_result", sa.String(30), nullable=True),
    )
    op.add_column(
        "civic_issues",
        sa.Column("ai_verification_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "civic_issues",
        sa.Column("ai_verification_reasoning", sa.Text(), nullable=True),
    )
    op.add_column(
        "civic_issues", sa.Column("citizen_verified", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "civic_issues",
        sa.Column("citizen_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "civic_issues",
        sa.Column("citizen_verification_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "civic_issues",
        sa.Column("reopen_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "civic_issues",
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("civic_issue_clusters.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "civic_issues",
        sa.Column(
            "is_duplicate_of_cluster",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_civic_issues_cluster_id", "civic_issues", ["cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_civic_issues_cluster_id", table_name="civic_issues")
    op.drop_column("civic_issues", "is_duplicate_of_cluster")
    op.drop_column("civic_issues", "cluster_id")
    op.drop_column("civic_issues", "reopen_count")
    op.drop_column("civic_issues", "citizen_verification_note")
    op.drop_column("civic_issues", "citizen_verified_at")
    op.drop_column("civic_issues", "citizen_verified")
    op.drop_column("civic_issues", "ai_verification_reasoning")
    op.drop_column("civic_issues", "ai_verification_confidence")
    op.drop_column("civic_issues", "ai_verification_result")
    op.drop_column("civic_issues", "resolved_by_id")
    op.drop_column("civic_issues", "resolved_at")
    op.drop_column("civic_issues", "work_order_reference")
    op.drop_column("civic_issues", "resolution_notes")
    op.drop_column("civic_issues", "resolution_photo_url")
    op.drop_index(
        "ix_civic_issue_clusters_issue_type", table_name="civic_issue_clusters"
    )
    op.drop_index("ix_civic_issue_clusters_city", table_name="civic_issue_clusters")
    op.drop_table("civic_issue_clusters")
