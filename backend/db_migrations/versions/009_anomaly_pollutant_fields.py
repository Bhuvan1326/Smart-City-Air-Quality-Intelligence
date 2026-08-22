from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_anomaly_pollutant_fields"
down_revision: Union[str, None] = "008_model_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "anomaly_events",
        sa.Column("pollutant", sa.String(20), nullable=False, server_default="aqi"),
    )
    op.add_column(
        "anomaly_events", sa.Column("observed_value", sa.Float(), nullable=True)
    )
    op.add_column(
        "anomaly_events", sa.Column("expected_value", sa.Float(), nullable=True)
    )
    op.add_column(
        "anomaly_events", sa.Column("anomaly_score", sa.Float(), nullable=True)
    )
    op.add_column(
        "anomaly_events",
        sa.Column("severity", sa.String(20), nullable=False, server_default="moderate"),
    )
    op.add_column(
        "anomaly_events",
        sa.Column(
            "detection_method",
            sa.String(50),
            nullable=False,
            server_default="z_score",
        ),
    )
    op.create_index("ix_anomaly_events_pollutant", "anomaly_events", ["pollutant"])
    op.create_index("ix_anomaly_events_severity", "anomaly_events", ["severity"])


def downgrade() -> None:
    op.drop_index("ix_anomaly_events_severity", table_name="anomaly_events")
    op.drop_index("ix_anomaly_events_pollutant", table_name="anomaly_events")
    op.drop_column("anomaly_events", "detection_method")
    op.drop_column("anomaly_events", "severity")
    op.drop_column("anomaly_events", "anomaly_score")
    op.drop_column("anomaly_events", "expected_value")
    op.drop_column("anomaly_events", "observed_value")
    op.drop_column("anomaly_events", "pollutant")
