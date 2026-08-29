"""Waste-Burning & Circular Economy Intelligence endpoint.

Combines a live PM2.5-vs-baseline check, proximity to known biomass-type
emission sources, ward attribution, and NASA FIRMS satellite thermal
hotspots (when configured) via app/services/waste_burning.py. Never
confirms an event — see that module's docstring.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from app.api.deps import CurrentUser, get_db
from app.models.analytics import PollutionAttribution
from app.models.emission_source import EmissionSource, EmissionSourceType
from app.repositories.aqi import MonitoringStationRepository
from app.schemas.base import APIResponse
from app.schemas.waste_burning import (WasteBurningEventResponse,
                                       WasteBurningReportResponse)
from app.services.satellite.modis_firms import NasaFirmsClient
from app.services.waste_burning import assess_waste_burning_risk
from app.utils.geo import haversine_km
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/waste-burning", tags=["Waste Burning Intelligence"])


@router.get("/events", response_model=APIResponse[WasteBurningReportResponse])
async def get_waste_burning_events(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    city: str = Query(default="Pune"),
) -> APIResponse[WasteBurningReportResponse]:
    station_repo = MonitoringStationRepository(session)
    stations = await station_repo.get_active_by_city(city)
    if not stations:
        return APIResponse(
            data=WasteBurningReportResponse(
                city=city, events=[], satellite_configured=False
            ),
            message="No active monitoring stations for this city",
        )

    # Current PM2.5 vs 24h-prior-window baseline, per station — same
    # rolling-baseline convention as the anomaly-detection worker, just
    # scoped to PM2.5 specifically (biomass burning disproportionately
    # elevates PM2.5 relative to other pollutants).
    result = await session.execute(
        text(
            """
            WITH recent AS (
                SELECT DISTINCT ON (r.station_id) r.station_id, r.pm25, r.timestamp
                FROM aqi_readings r
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE s.city = :city AND r.timestamp > NOW() - INTERVAL '30 minutes'
                  AND r.is_deleted = false AND r.quality_flag != 'invalid'
                ORDER BY r.station_id, r.timestamp DESC
            ),
            baseline AS (
                SELECT r.station_id, AVG(r.pm25) AS avg_pm25
                FROM aqi_readings r
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE s.city = :city
                  AND r.timestamp BETWEEN NOW() - INTERVAL '3 days' AND NOW() - INTERVAL '2 hours'
                  AND r.is_deleted = false AND r.quality_flag != 'invalid'
                GROUP BY r.station_id
            )
            SELECT rc.station_id, rc.pm25 AS current_pm25, b.avg_pm25 AS baseline_pm25
            FROM recent rc
            LEFT JOIN baseline b ON rc.station_id = b.station_id
            """
        ),
        {"city": city},
    )
    pm25_by_station = {
        row.station_id: (row.current_pm25, row.baseline_pm25) for row in result
    }

    biomass_sources_result = await session.execute(
        select(EmissionSource).where(
            EmissionSource.city == city,
            EmissionSource.source_type == EmissionSourceType.BIOMASS,
            EmissionSource.is_active.is_(True),
            EmissionSource.is_deleted.is_(False),
        )
    )
    biomass_sources = list(biomass_sources_result.scalars().all())

    firms_client = NasaFirmsClient()
    satellite_configured = firms_client.is_configured
    hotspots = []
    if satellite_configured:
        lats = [s.latitude for s in stations]
        lons = [s.longitude for s in stations]
        bbox = (min(lons) - 0.05, min(lats) - 0.05, max(lons) + 0.05, max(lats) + 0.05)
        hotspots = await firms_client.fetch_hotspots(bbox, days_back=1)

    three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)

    events: list[WasteBurningEventResponse] = []
    for station in stations:
        current_pm25, baseline_pm25 = pm25_by_station.get(station.id, (None, None))

        nearest_biomass = None
        nearest_biomass_distance = None
        for src in biomass_sources:
            d = haversine_km(
                station.latitude, station.longitude, src.latitude, src.longitude
            )
            if nearest_biomass_distance is None or d < nearest_biomass_distance:
                nearest_biomass_distance = d
                nearest_biomass = src

        biomass_attribution_pct = None
        if station.ward_id:
            attr_result = await session.execute(
                select(PollutionAttribution)
                .where(
                    PollutionAttribution.city == city,
                    PollutionAttribution.ward_id == station.ward_id,
                    PollutionAttribution.timestamp >= three_hours_ago,
                    PollutionAttribution.is_deleted.is_(False),
                )
                .order_by(desc(PollutionAttribution.timestamp))
                .limit(1)
            )
            attribution = attr_result.scalar_one_or_none()
            if attribution:
                biomass_attribution_pct = attribution.biomass_pct

        satellite_hotspot_nearby = any(
            haversine_km(station.latitude, station.longitude, h.latitude, h.longitude)
            <= 5.0
            for h in hotspots
        )

        assessment = assess_waste_burning_risk(
            ward_id=station.ward_id,
            current_pm25=current_pm25,
            baseline_pm25=baseline_pm25,
            nearest_biomass_source_name=(
                nearest_biomass.name if nearest_biomass else None
            ),
            nearest_biomass_source_distance_km=(
                round(nearest_biomass_distance, 2)
                if nearest_biomass_distance is not None
                else None
            ),
            biomass_attribution_pct=biomass_attribution_pct,
            satellite_hotspot_nearby=satellite_hotspot_nearby,
            satellite_configured=satellite_configured,
        )

        # Only surface stations with at least one triggering signal — an
        # "all clear" station isn't a waste-burning event worth listing.
        if assessment.confidence.value != "none":
            events.append(
                WasteBurningEventResponse(
                    ward_id=assessment.ward_id,
                    station_name=station.name,
                    current_pm25=current_pm25,
                    baseline_pm25=baseline_pm25,
                    detected=assessment.detected,
                    supporting_observations=assessment.supporting_observations,
                    confidence=assessment.confidence.value,
                    status=assessment.status,
                    circular_economy_recommendations=assessment.circular_economy_recommendations,
                )
            )

    confidence_order = {"high": 0, "moderate": 1, "low": 2}
    events.sort(key=lambda e: confidence_order.get(e.confidence, 3))

    return APIResponse(
        data=WasteBurningReportResponse(
            city=city, events=events, satellite_configured=satellite_configured
        )
    )
