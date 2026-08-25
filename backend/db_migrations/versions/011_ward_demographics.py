from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011_ward_demographics"
down_revision: Union[str, None] = "010_alert_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ward_demographics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=False),
        sa.Column("population", sa.Integer(), nullable=True),
        sa.Column("sensitive_sites_count", sa.Integer(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
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
    op.create_index("ix_ward_demographics_city", "ward_demographics", ["city"])
    op.create_index("ix_ward_demographics_ward_id", "ward_demographics", ["ward_id"])
    op.create_unique_constraint(
        "uq_ward_demographics_city_ward", "ward_demographics", ["city", "ward_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ward_demographics_city_ward", "ward_demographics", type_="unique"
    )
    op.drop_index("ix_ward_demographics_ward_id", table_name="ward_demographics")
    op.drop_index("ix_ward_demographics_city", table_name="ward_demographics")
    op.drop_table("ward_demographics")
