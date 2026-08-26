from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "015_civic_issues"
down_revision: Union[str, None] = "014_city_water_resources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "civic_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "reporter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=True),
        sa.Column("ward_assignment_method", sa.String(30), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "geometry", Geometry(geometry_type="POINT", srid=4326), nullable=True
        ),
        sa.Column("issue_type", sa.String(40), nullable=False),
        sa.Column("classification_source", sa.String(40), nullable=False),
        sa.Column("ai_suggested_type", sa.String(40), nullable=True),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("ai_suggested_severity", sa.String(20), nullable=True),
        sa.Column("ai_reasoning", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("photo_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("assigned_department", sa.String(150), nullable=True),
        sa.Column("sla_hours", sa.Float(), nullable=False),
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_overdue", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
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
    op.create_index("ix_civic_issues_reporter_id", "civic_issues", ["reporter_id"])
    op.create_index("ix_civic_issues_city", "civic_issues", ["city"])
    op.create_index("ix_civic_issues_ward_id", "civic_issues", ["ward_id"])
    op.create_index("ix_civic_issues_status", "civic_issues", ["status"])
    op.create_index(
        "ix_civic_issues_geometry", "civic_issues", ["geometry"], postgresql_using="gist"
    )

    op.create_table(
        "civic_issue_status_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "issue_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("civic_issues.id"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column(
            "changed_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
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
    op.create_index(
        "ix_civic_issue_status_events_issue_id",
        "civic_issue_status_events",
        ["issue_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_civic_issue_status_events_issue_id",
        table_name="civic_issue_status_events",
    )
    op.drop_table("civic_issue_status_events")
    op.drop_index("ix_civic_issues_geometry", table_name="civic_issues")
    op.drop_index("ix_civic_issues_status", table_name="civic_issues")
    op.drop_index("ix_civic_issues_ward_id", table_name="civic_issues")
    op.drop_index("ix_civic_issues_city", table_name="civic_issues")
    op.drop_index("ix_civic_issues_reporter_id", table_name="civic_issues")
    op.drop_table("civic_issues")
