from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_ward_waste_data"
down_revision: Union[str, None] = "012_ward_green_cover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ward_demographics",
        sa.Column("waste_generation_tons_per_day", sa.Float(), nullable=True),
    )
    op.add_column(
        "ward_demographics",
        sa.Column("waste_collection_efficiency_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "ward_demographics",
        sa.Column("waste_recycling_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "ward_demographics",
        sa.Column("waste_composting_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "ward_demographics",
        sa.Column("waste_landfill_pct", sa.Float(), nullable=True),
    )
    op.add_column(
        "ward_demographics",
        sa.Column("waste_data_as_of", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ward_demographics", "waste_data_as_of")
    op.drop_column("ward_demographics", "waste_landfill_pct")
    op.drop_column("ward_demographics", "waste_composting_pct")
    op.drop_column("ward_demographics", "waste_recycling_pct")
    op.drop_column("ward_demographics", "waste_collection_efficiency_pct")
    op.drop_column("ward_demographics", "waste_generation_tons_per_day")
