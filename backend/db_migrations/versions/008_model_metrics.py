from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_model_metrics"
down_revision: Union[str, None] = "007_weather_measurements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("target", sa.String(50), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=False),
        sa.Column("train_sample_count", sa.Integer(), nullable=False),
        sa.Column("test_sample_count", sa.Integer(), nullable=False),
        sa.Column("mae", sa.Float(), nullable=False),
        sa.Column("rmse", sa.Float(), nullable=False),
        sa.Column("r2", sa.Float(), nullable=False),
        sa.Column("mape", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
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
    op.create_index("ix_model_metrics_model_name", "model_metrics", ["model_name"])
    op.create_index("ix_model_metrics_trained_at", "model_metrics", ["trained_at"])


def downgrade() -> None:
    op.drop_index("ix_model_metrics_trained_at", table_name="model_metrics")
    op.drop_index("ix_model_metrics_model_name", table_name="model_metrics")
    op.drop_table("model_metrics")
