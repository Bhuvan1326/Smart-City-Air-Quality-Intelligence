"""Ward-level demographic context for population exposure scoring.

Deliberately has NO seeded default values. Population figures and
sensitive-site counts must be entered by an administrator from an
authoritative source (e.g. census data) — see notes field for citation.
Until a ward has a record here, exposure scoring for that ward reports
"Unavailable" rather than guessing a population figure.
"""

from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class WardDemographics(BaseModel):
    __tablename__ = "ward_demographics"

    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ward_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Combined count of sensitive public infrastructure sites (schools +
    # hospitals + elder-care facilities etc.) — a single admin-entered
    # count rather than fabricated individual site locations.
    sensitive_sites_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Citation for where this figure came from, e.g. '2011 Census, PMC ward delimitation'",
    )
    # Existing vegetation/green cover, as a percentage of ward area (0-100).
    # Same integrity rule as population: no default is seeded — an
    # administrator enters this from an authoritative source (e.g. municipal
    # green-cover survey, satellite NDVI analysis) via source_note.
    green_cover_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Smart Waste & Circularity (see app/services/waste_circularity.py).
    # There is no universal free real-time municipal-waste API, so — same
    # integrity rule as population/green_cover above — these are
    # admin-entered from an authoritative periodic source (e.g. a municipal
    # corporation's solid-waste-management annual report), never a live
    # feed and never seeded with a default. waste_data_as_of records the
    # date the source figures are "as of", since a periodic administrative
    # report can't honestly be labeled with a data-age-in-minutes freshness
    # the way a sensor reading can.
    waste_generation_tons_per_day: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    waste_collection_efficiency_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    waste_recycling_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    waste_composting_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    waste_landfill_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    waste_data_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
