import asyncio
from datetime import UTC, datetime

from app.core.config import settings
from app.core.logging import logger
from app.workers.celery_app import celery_app

# Used only by tests exercising the pure `_attribute_sources` function
# across a representative set of ward ids; the ingestion/compute loop
# itself now derives wards per-city from real station/ward data (see
# `_attribution_async`) rather than this fixed Pune list.
PUNE_WARDS = ["W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08"]

# Legacy fallback coordinates for Pune's 8 fixture wards. `_attribution_async`
# derives each city's ward coordinates from real monitoring-station lat/lon
# (so attribution geometry is correct for every city, not just Pune) and no
# longer reads this dict for that purpose — kept as a documented reference
# constant and covered by test_ward_coordinates_regression.py's
# copy-paste-bug guard.
WARD_COORDS = {
    "W01": (18.5074, 73.8077),
    "W02": (18.5308, 73.8475),
    "W03": (18.5089, 73.9259),
    "W04": (18.6298, 73.7997),
    "W05": (18.4530, 73.8618),
    "W06": (18.5989, 73.7601),
    "W07": (18.4968, 73.8126),
    "W08": (18.5559, 73.9007),
}


def _attribute_sources(
    ward: str,
    avg_aqi: float,
    hour: int,
    dow: int,
    satellite_evidence: dict | None = None,
) -> dict:
    """
    Rule-based + statistical attribution model.
    Returns percentage contribution per source category with confidence.
    Production version uses Random Forest trained on CMB receptor modelling data.

    `satellite_evidence`, when available (see app.services.satellite.
    attribution_integration.build_satellite_evidence), nudges the base
    weights toward whichever category the satellite signal actually
    supports -- e.g. a detected construction-dust NDBI signal increases
    the construction share -- and raises overall_confidence when satellite
    and the base model agree, rather than the two being computed in
    isolation.
    """
    is_peak = (7 <= hour <= 10) or (17 <= hour <= 20)
    is_weekend = dow >= 5
    is_industrial_ward = ward in ("W03", "W04")

    if is_industrial_ward:
        industrial = 0.38 if not is_weekend else 0.22
        vehicular = 0.28 if is_peak else 0.18
    else:
        industrial = 0.12
        vehicular = 0.40 if is_peak else 0.25

    construction = 0.15 if not is_weekend else 0.08
    biomass = 0.08 if (5 <= hour <= 9) else 0.04
    dust = 0.10
    domestic = 0.06 if (6 <= hour <= 9 or 18 <= hour <= 21) else 0.03

    # Confidence reflects how much genuine signal supports this attribution
    # split -- not just a coarse "AQI above/below 100" bucket, which collapses
    # to one of two values for nearly every ward since most wards sit on the
    # same side of that threshold most of the time. Higher-AQI episodes carry
    # a clearer dominant-source signal (less dilution/mixing noise in the
    # proportional split); industrial wards have a more stable, predictable
    # emission profile than mixed residential/commercial wards; weekday peak
    # traffic gives the vehicular share firmer footing than off-peak; and
    # weekend activity patterns (construction pauses, irregular traffic) are
    # inherently less predictable than weekday ones.
    aqi_signal = min(1.0, max(0.0, (avg_aqi - 50) / 150))  # 0 at AQI<=50, 1 at AQI>=200
    confidence = 0.58 + 0.22 * aqi_signal
    if is_industrial_ward:
        confidence += 0.05
    if is_peak and not is_industrial_ward:
        confidence += 0.03
    if is_weekend:
        confidence -= 0.04
    confidence = min(0.90, max(0.55, confidence))
    satellite_agreement = 0.0

    if satellite_evidence:
        category_scores = satellite_evidence.get("category_scores") or {}
        sat_confidence = satellite_evidence.get("confidence") or 0.0

        if "construction_dust" in category_scores:
            boost = category_scores["construction_dust"] * sat_confidence * 0.12
            construction += boost
            satellite_agreement += category_scores["construction_dust"]
        if "biomass_burning" in category_scores:
            boost = category_scores["biomass_burning"] * sat_confidence * 0.10
            biomass += boost
            satellite_agreement += category_scores["biomass_burning"]
        if "industrial_hotspot" in category_scores:
            boost = category_scores["industrial_hotspot"] * sat_confidence * 0.12
            industrial += boost
            satellite_agreement += category_scores["industrial_hotspot"]

        if satellite_agreement > 0:
            confidence = min(0.95, confidence + 0.1 * min(1.0, satellite_agreement))

    total = industrial + vehicular + construction + biomass + dust + domestic
    scale = 1.0 / total

    return {
        "vehicular_pct": round(vehicular * scale * 100, 1),
        "industrial_pct": round(industrial * scale * 100, 1),
        "construction_pct": round(construction * scale * 100, 1),
        "biomass_pct": round(biomass * scale * 100, 1),
        "secondary_aerosol_pct": round(0.0, 1),
        "dust_pct": round(dust * scale * 100, 1),
        "domestic_pct": round(domestic * scale * 100, 1),
        "overall_confidence": round(confidence, 3),
    }


@celery_app.task(name="app.workers.tasks.attribution.compute_attribution", bind=True)
def compute_attribution(self):
    asyncio.run(_attribution_async())


async def _attribution_async():
    from geoalchemy2.elements import WKTElement
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.analytics import PollutionAttribution
    from app.services.satellite.attribution_integration import (
        SatelliteAttributionEvidence,
    )

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime.now(UTC)
    hour = now.hour
    dow = now.weekday()

    async with AsyncSession() as session:
        # Attribution must not be Pune-only: compute it for every city that
        # actually has monitoring stations, using each city's real ward
        # ids and station-derived ward centroids (never Pune's coordinates
        # for another city's wards).
        cities_result = await session.execute(
            text(
                "SELECT DISTINCT city FROM monitoring_stations WHERE is_deleted = false"
            )
        )
        cities = [row.city for row in cities_result]

        total_records = 0
        for city in cities:
            ward_result = await session.execute(
                text("""
                SELECT s.ward_id, AVG(r.aqi) AS avg_aqi,
                       AVG(s.latitude) AS lat, AVG(s.longitude) AS lon
                FROM aqi_readings r
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE s.city = :city
                  AND r.timestamp > NOW() - INTERVAL '1 hour'
                  AND r.is_deleted = false AND r.quality_flag != 'invalid'
                  AND s.ward_id IS NOT NULL
                GROUP BY s.ward_id
            """),
                {"city": city},
            )
            ward_rows = {
                row.ward_id: (float(row.avg_aqi), float(row.lat), float(row.lon))
                for row in ward_result
                if row.avg_aqi is not None
            }
            if not ward_rows:
                # No current readings for this city -- nothing to
                # attribute; leave it unavailable rather than fabricating
                # wards/coordinates for it.
                continue

            satellite_result = await session.execute(
                text("""
                SELECT DISTINCT ON (ward_id) ward_id, mean_ndvi, mean_ndbi,
                       vegetation_loss_detected, construction_activity_detected,
                       thermal_hotspot_count, biomass_burning_hotspots,
                       industrial_thermal_hotspots, max_fire_radiative_power_mw,
                       category_scores, confidence, sources, notes
                FROM satellite_observations
                WHERE city = :city AND is_deleted = false
                ORDER BY ward_id, observed_at DESC
            """),
                {"city": city},
            )
            satellite_by_ward: dict[str, dict] = {}
            for row in satellite_result:
                satellite_by_ward[row.ward_id] = SatelliteAttributionEvidence(
                    ward_id=row.ward_id,
                    sources=row.sources or [],
                    vegetation_index=row.mean_ndvi,
                    construction_dust_index=row.mean_ndbi,
                    vegetation_loss_detected=row.vegetation_loss_detected,
                    construction_activity_detected=row.construction_activity_detected,
                    thermal_hotspot_count=row.thermal_hotspot_count,
                    biomass_burning_hotspots=row.biomass_burning_hotspots,
                    industrial_thermal_hotspots=row.industrial_thermal_hotspots,
                    max_fire_radiative_power_mw=row.max_fire_radiative_power_mw,
                    category_scores=row.category_scores or {},
                    confidence=row.confidence,
                    notes=row.notes or [],
                ).to_dict()

            records = []
            for ward, (avg_aqi, lat, lon) in ward_rows.items():
                satellite_evidence = satellite_by_ward.get(ward)
                attribution = _attribute_sources(
                    ward, avg_aqi, hour, dow, satellite_evidence
                )

                delta = 0.01
                geom = WKTElement(
                    f"POLYGON(({lon - delta} {lat - delta}, {lon + delta} {lat - delta}, "
                    f"{lon + delta} {lat + delta}, {lon - delta} {lat + delta}, {lon - delta} {lat - delta}))",
                    srid=4326,
                )

                emission_sources_result = await session.execute(
                    text("""
                    SELECT id, name, source_type, violation_count
                    FROM emission_sources
                    WHERE city = :city AND ward_id = :ward AND is_active = true AND is_deleted = false
                    ORDER BY violation_count DESC LIMIT 5
                """),
                    {"city": city, "ward": ward},
                )
                sources = [dict(row._mapping) for row in emission_sources_result]

                record = PollutionAttribution(
                    ward_id=ward,
                    city=city,
                    timestamp=now,
                    **attribution,
                    contributing_sources={"top_sources": sources},
                    satellite_evidence=satellite_evidence
                    or {
                        "ndvi_anomaly": False,
                        "thermal_hotspot": False,
                        "note": "no satellite data available",
                    },
                    model_version="receptor-model-v1.2",
                    geometry=geom,
                )
                records.append(record)

            session.add_all(records)
            total_records += len(records)

        await session.commit()
        logger.info("attribution.complete", wards=total_records, cities=len(cities))

    await engine.dispose()
