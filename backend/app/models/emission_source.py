from datetime import datetime
from enum import Enum

from geoalchemy2 import Geometry
from sqlalchemy import (Boolean, DateTime, Float, Integer, String,
                        Text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class EmissionSourceType(str, Enum):
    VEHICULAR = "vehicular"
    INDUSTRIAL = "industrial"
    CONSTRUCTION = "construction"
    BIOMASS = "biomass"
    SECONDARY_AEROSOL = "secondary_aerosol"
    DUST = "dust"
    DOMESTIC = "domestic"


class PermitStatus(str, Enum):
    VALID = "valid"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    PENDING = "pending"
    NONE = "none"


class EmissionSource(BaseModel):
    __tablename__ = "emission_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[EmissionSourceType] = mapped_column(
        String(50), nullable=False, index=True
    )
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    ward_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    permit_status: Mapped[PermitStatus] = mapped_column(
        String(20), default=PermitStatus.NONE, nullable=False
    )
    permit_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    permit_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_inspected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    violation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    operator_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator_contact: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    stack_height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    emission_rate_kg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbon_estimate_ton_yr: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    enforcement_actions: Mapped[list["EnforcementAction"]] = relationship(
        "EnforcementAction", back_populates="source"
    )
