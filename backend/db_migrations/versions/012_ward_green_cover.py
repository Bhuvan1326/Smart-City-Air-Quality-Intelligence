from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_ward_green_cover"
down_revision: Union[str, None] = "011_ward_demographics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ward_demographics",
        sa.Column("green_cover_pct", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ward_demographics", "green_cover_pct")
