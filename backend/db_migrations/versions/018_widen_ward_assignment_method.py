"""Widen civic_issues.ward_assignment_method from VARCHAR(30) to
VARCHAR(50).

Root cause: the column was sized for the original enum values
(point_in_polygon=16, unavailable=11 chars) at the time migration 015
was written, but WardAssignmentMethod.NEAREST_WARD_CENTROID_APPROXIMATE
("nearest_ward_centroid_approximate", 33 characters) exceeds that limit.
SQLite (used in local/sandbox testing) does not enforce VARCHAR length
constraints, so this only surfaced against real PostgreSQL, which
correctly rejects the insert with StringDataRightTruncationError.

50 characters gives headroom matching ward_id's own column width in the
same table, rather than sizing exactly to today's longest value.

Migration 015 (where the column was first created) is left untouched
since it may already be applied in existing databases — this widening
is expressed as its own migration, consistent with how ward_demographics
add columns incrementally (012, 013) rather than rewriting history.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_widen_ward_assignment_method"
down_revision: Union[str, None] = "017_civic_resolution_and_clusters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "civic_issues",
        "ward_assignment_method",
        existing_type=sa.String(length=30),
        type_=sa.String(length=50),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Note: downgrading is only safe if no existing row's value exceeds
    # 30 characters. In practice this means downgrading is unsafe once
    # any issue has used the "nearest_ward_centroid_approximate" method —
    # this is a deliberate, disclosed limitation rather than a silent
    # truncation on downgrade.
    op.alter_column(
        "civic_issues",
        "ward_assignment_method",
        existing_type=sa.String(length=50),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
