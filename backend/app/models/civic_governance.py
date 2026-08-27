"""Civic governance reference data: municipalities, ward offices, ward
boundary polygons, and elected ward representatives.

All four are admin-entered with NO seeded defaults, following the exact
integrity rule already established by WardDemographics/CityWaterResource
elsewhere in this codebase: a source citation is required, nothing is
auto-populated, and a lookup that finds no record returns "unavailable"
rather than guessing. This directly answers the platform-wide instruction
to replace hardcoded `if city == "Pune"` logic with data-driven lookups —
these tables are genuinely empty until an administrator populates them,
which is honest about coverage rather than pretending city-specific
knowledge this platform doesn't actually have.

WardRepresentative is explicitly NOT the same thing as "responsible civic
authority" (that's Municipality/Department, from app.services.civic_sla
and this module) — see the module docstring in
app/services/civic_governance.py for how the two are kept distinct in API
responses, per the requirement to never imply an elected official
personally performs municipal cleanup work.
"""

from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Municipality(BaseModel):
    """One municipal governing body per city. Admin-entered."""

    __tablename__ = "municipalities"
    __table_args__ = (UniqueConstraint("city", name="uq_municipalities_city"),)

    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    official_website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WardOffice(BaseModel):
    """Physical/administrative ward office for a (city, ward_id). Admin-entered."""

    __tablename__ = "ward_offices"
    __table_args__ = (
        UniqueConstraint("city", "ward_id", name="uq_ward_offices_city_ward"),
    )

    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ward_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    office_name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WardBoundary(BaseModel):
    """Ward boundary polygon for real PostGIS point-in-polygon assignment.

    Admin-entered, versioned by effective_from/effective_to so a boundary
    change (redistricting) doesn't silently erase history. Genuinely
    empty until populated — app.services.civic_ward_assignment falls back
    to an approximate nearest-centroid method (and ultimately
    "unavailable") when no polygon covers a point, rather than fabricating
    one.
    """

    __tablename__ = "ward_boundaries"

    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ward_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    geometry: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=False
    )
    source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Citation for this boundary, e.g. 'PMC ward delimitation notification 2022' "
        "or, if only an approximation is available, an explicit note saying so.",
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WardRepresentative(BaseModel):
    """Elected ward representative — accountability/contact context ONLY.

    Never treated as an operational cleanup authority (see
    app/services/civic_governance.py). Admin-entered with a required
    source citation; no default is ever seeded, and no representative is
    fabricated for a ward with no record here.
    """

    __tablename__ = "ward_representatives"

    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ward_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    official_profile_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    official_contact: Mapped[str | None] = mapped_column(String(300), nullable=True)
    term_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    term_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Citation for this record, e.g. election commission / municipal corporation records.",
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
