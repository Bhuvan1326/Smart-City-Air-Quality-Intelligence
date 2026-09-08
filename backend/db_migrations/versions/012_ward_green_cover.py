from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "012_ward_green_cover"
down_revision: str | None = "011_ward_demographics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ward_demographics",
        sa.Column("green_cover_pct", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ward_demographics", "green_cover_pct")
