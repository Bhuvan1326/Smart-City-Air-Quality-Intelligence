from datetime import datetime

from app.schemas.base import BaseSchema


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
