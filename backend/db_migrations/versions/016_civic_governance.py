from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "016_civic_governance"
down_revision: Union[str, None] = "015_civic_issues"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
    ]


def upgrade() -> None:
    op.create_table(
        "municipalities",
        *_base_columns(),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("official_website", sa.String(500), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_municipalities_city", "municipalities", ["city"])
    op.create_unique_constraint("uq_municipalities_city", "municipalities", ["city"])

    op.create_table(
        "ward_offices",
        *_base_columns(),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=False),
        sa.Column("office_name", sa.String(200), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("contact_phone", sa.String(50), nullable=True),
        sa.Column("contact_email", sa.String(200), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ward_offices_city", "ward_offices", ["city"])
    op.create_index("ix_ward_offices_ward_id", "ward_offices", ["ward_id"])
    op.create_unique_constraint(
        "uq_ward_offices_city_ward", "ward_offices", ["city", "ward_id"]
    )

    op.create_table(
        "ward_boundaries",
        *_base_columns(),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=False),
        sa.Column(
            "geometry", Geometry(geometry_type="POLYGON", srid=4326), nullable=False
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ward_boundaries_city", "ward_boundaries", ["city"])
    op.create_index("ix_ward_boundaries_ward_id", "ward_boundaries", ["ward_id"])
    op.create_index(
        "ix_ward_boundaries_geometry",
        "ward_boundaries",
        ["geometry"],
        postgresql_using="gist",
    )

    op.create_table(
        "ward_representatives",
        *_base_columns(),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("ward_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(200), nullable=False),
        sa.Column("photo_url", sa.String(500), nullable=True),
        sa.Column("official_profile_url", sa.String(500), nullable=True),
        sa.Column("official_contact", sa.String(300), nullable=True),
        sa.Column("term_start", sa.Date(), nullable=True),
        sa.Column("term_end", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ward_representatives_city", "ward_representatives", ["city"])
    op.create_index(
        "ix_ward_representatives_ward_id", "ward_representatives", ["ward_id"]
    )


def downgrade() -> None:
    op.drop_table("ward_representatives")
    op.drop_index("ix_ward_boundaries_geometry", table_name="ward_boundaries")
    op.drop_index("ix_ward_boundaries_ward_id", table_name="ward_boundaries")
    op.drop_index("ix_ward_boundaries_city", table_name="ward_boundaries")
    op.drop_table("ward_boundaries")
    op.drop_constraint("uq_ward_offices_city_ward", "ward_offices", type_="unique")
    op.drop_index("ix_ward_offices_ward_id", table_name="ward_offices")
    op.drop_index("ix_ward_offices_city", table_name="ward_offices")
    op.drop_table("ward_offices")
    op.drop_constraint("uq_municipalities_city", "municipalities", type_="unique")
    op.drop_index("ix_municipalities_city", table_name="municipalities")
    op.drop_table("municipalities")
