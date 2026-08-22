from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_forecast_explainability"
down_revision: Union[str, None] = "003_timescaledb_optimization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "forecast_grids",
        sa.Column(
            "explanation_method",
            sa.String(50),
            nullable=False,
            server_default="heuristic",
        ),
    )
    op.add_column(
        "forecast_grids",
        sa.Column(
            "explanation_detail",
            postgresql.JSONB(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("forecast_grids", "explanation_detail")
    op.drop_column("forecast_grids", "explanation_method")
