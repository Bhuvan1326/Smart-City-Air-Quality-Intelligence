from datetime import datetime

from app.schemas.base import BaseSchema


class FuelSourceItem(BaseSchema):
    name: str
    value_mw: float
    percentage: float
    category: str  # "fossil" | "nuclear" | "renewable"


class FuelMixResponse(BaseSchema):
    sources: list[FuelSourceItem]
    total_mw: float
    as_of: str
    renewable_pct: float
    fossil_pct: float
    nuclear_pct: float
    note: str


class YearlyStats(BaseSchema):
    year: int
    renewable_pct: float
    fossil_pct: float
    nuclear_pct: float


class RenewableTrendResponse(BaseSchema):
    trend: list[YearlyStats]
    note: str


class EnergyReadingResponse(BaseSchema):
    """A single energy-intelligence data point with full provenance.

    See app/services/energy_provider.py for the provider hierarchy and
    app/services/data_freshness.py for the shared freshness rules that
    produced freshness_status here.
    """

    metric: str
    value: float | None
    unit: str
    source_type: str
    provider: str | None
    observed_at: datetime | None
    fetched_at: datetime
    data_age_seconds: float | None
    freshness_status: str
    note: str
    latitude: float
    longitude: float
    city: str | None
