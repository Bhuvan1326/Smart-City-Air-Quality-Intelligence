"""Create notifications table.

Revision ID: 023_notifications
Revises: 022_heat_readings
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_notifications"
down_revision: Union[str, None] = "022_heat_readings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("notification_type", sa.String(length=30), nullable=False),
        sa.Column(
            "related_alert_id",
            sa.UUID(),
            sa.ForeignKey("citizen_alerts.id"),
            nullable=True,
        ),
        sa.Column(
            "is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_notifications_user_id",
        "notifications",
        ["user_id"],
    )

    op.create_index(
        "ix_notifications_related_alert_id",
        "notifications",
        ["related_alert_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notifications_related_alert_id",
        table_name="notifications",
    )
    op.drop_index(
        "ix_notifications_user_id",
        table_name="notifications",
    )
    op.drop_table("notifications")
