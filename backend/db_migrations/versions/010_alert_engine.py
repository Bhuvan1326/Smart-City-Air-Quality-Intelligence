from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010_alert_engine"
down_revision: Union[str, None] = "009_anomaly_pollutant_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "citizen_alerts",
        sa.Column(
            "alert_type",
            sa.String(30),
            nullable=False,
            server_default="current_threshold",
        ),
    )
    op.add_column(
        "citizen_alerts", sa.Column("threshold_value", sa.Float(), nullable=True)
    )
    op.add_column(
        "citizen_alerts", sa.Column("current_value", sa.Float(), nullable=True)
    )
    op.add_column(
        "citizen_alerts", sa.Column("predicted_value", sa.Float(), nullable=True)
    )
    op.add_column("citizen_alerts", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column(
        "citizen_alerts",
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
    )
    op.create_index("ix_citizen_alerts_alert_type", "citizen_alerts", ["alert_type"])

    op.create_table(
        "alert_thresholds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column(
            "cooldown_minutes", sa.Integer(), nullable=False, server_default="120"
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.UniqueConstraint("city", "alert_type", name="uq_alert_threshold_city_type"),
    )
    op.create_index("ix_alert_thresholds_city", "alert_thresholds", ["city"])


def downgrade() -> None:
    op.drop_index("ix_alert_thresholds_city", table_name="alert_thresholds")
    op.drop_table("alert_thresholds")
    op.drop_index("ix_citizen_alerts_alert_type", table_name="citizen_alerts")
    op.drop_column("citizen_alerts", "status")
    op.drop_column("citizen_alerts", "reason")
    op.drop_column("citizen_alerts", "predicted_value")
    op.drop_column("citizen_alerts", "current_value")
    op.drop_column("citizen_alerts", "threshold_value")
    op.drop_column("citizen_alerts", "alert_type")
