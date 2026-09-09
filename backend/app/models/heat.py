from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class HeatReading(BaseModel):
    """Persisted snapshot of a heat assessment — written on every successful
    /heat/current request so the history endpoint has data to serve.
    """

    __tablename__ = "heat_readings"

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=func.now(),
    )
    city: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    ward_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    air_temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    apparent_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    heat_index_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    heat_risk: Mapped[str] = mapped_column(String(20), nullable=False)
    mean_ndvi: Mapped[float | None] = mapped_column(Float, nullable=True)
    cooling_priority: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
