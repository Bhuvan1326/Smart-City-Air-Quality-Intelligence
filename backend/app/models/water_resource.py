"""City-level municipal water resource data.

There is no universal free real-time municipal-water API (same conclusion
already reached for energy demand and municipal waste — see
app/services/energy_provider.py and app/services/waste_circularity.py).
Reservoir levels, water consumption, and groundwater depth are instead
admin-entered here from an authoritative periodic source (e.g. a water
board / municipal corporation report), following the exact same integrity
rule already established in app.models.demographics.WardDemographics: NO
default is seeded, a citation goes in source_note, and data_as_of records
how current the figures are — since a periodic administrative report can
never honestly be labeled with a sensor-style minute-scale freshness.

This is city-level (one record per city), not ward-level, because
reservoirs/water supply systems serve a whole city rather than a single
ward — a separate table from WardDemographics rather than forcing a
ward-scoped model to hold a city-scoped figure.
"""

from datetime import date

from app.models.base import BaseModel
from sqlalchemy import Date, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class CityWaterResource(BaseModel):
    __tablename__ = "city_water_resources"
    __table_args__ = (UniqueConstraint("city", name="uq_city_water_resources_city"),)

    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reservoir_level_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    water_consumption_mld: Mapped[float | None] = mapped_column(
        Float, nullable=True, doc="Million litres per day"
    )
    groundwater_level_m: Mapped[float | None] = mapped_column(
        Float, nullable=True, doc="Depth to groundwater, metres below ground level"
    )
    data_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Citation for where this figure came from, e.g. 'PMC Water Supply Dept. weekly reservoir bulletin'",
    )
