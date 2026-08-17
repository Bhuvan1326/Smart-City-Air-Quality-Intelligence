"""
Celery task: fetch satellite-derived features per ward on a schedule and
persist them as SatelliteObservation rows. Kept separate from the
attribution task so satellite fetches (slow, external, rate-limited) don't
block the hourly attribution run — attribution just reads whatever the most
recent observation is.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.logging import logger
from app.workers.celery_app import celery_app

# Same ward centroids used by the attribution task; a real deployment would
# pull these (and full ward polygons) from the wards/GIS table instead.
WARD_BBOXES = {
    "W01": (73.7977, 18.4974, 73.8177, 18.5174),
    "W02": (73.8375, 18.5208, 73.8575, 18.5408),
    "W03": (73.9159, 18.4989, 73.9359, 18.5189),
    "W04": (73.7897, 18.6198, 73.8097, 18.6398),
    "W05": (73.8518, 18.4430, 73.8718, 18.4630),
    "W06": (73.7501, 18.5889, 73.7701, 18.6089),
    "W07": (73.8026, 18.4868, 73.8226, 18.5068),
    "W08": (73.8907, 18.5459, 73.9107, 18.5659),
}


@celery_app.task(name="app.workers.tasks.satellite.fetch_satellite_features", bind=True)
def fetch_satellite_features(self):
    asyncio.run(_fetch_async())


async def _fetch_async():
    if not settings.SATELLITE_FETCH_ENABLED:
        logger.info("satellite.fetch_disabled")
        return

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.analytics import SatelliteObservation
    from app.services.satellite import NasaFirmsClient, SentinelHubClient
    from app.services.satellite.attribution_integration import build_satellite_evidence

    sentinel = SentinelHubClient()
    firms = NasaFirmsClient()

    if not sentinel.is_configured and not firms.is_configured:
        logger.info("satellite.no_providers_configured")
        return

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    now = datetime.now(UTC)
    today = now.date()
    week_ago = today - timedelta(days=7)

    async with AsyncSession() as session:
        stored = 0
        for ward_id, bbox in WARD_BBOXES.items():
            band_summary = None
            if sentinel.is_configured:
                band_summary = await sentinel.fetch_ward_indices(
                    ward_id, bbox, week_ago, today
                )

            hotspots = []
            if firms.is_configured:
                hotspots = await firms.fetch_hotspots(bbox, days_back=1)

            if band_summary is None and not hotspots:
                continue

            evidence = build_satellite_evidence(ward_id, band_summary, hotspots)

            observation = SatelliteObservation(
                ward_id=ward_id,
                city="Pune",
                observed_at=now,
                mean_ndvi=evidence.vegetation_index,
                mean_ndbi=evidence.construction_dust_index,
                vegetation_loss_detected=evidence.vegetation_loss_detected,
                construction_activity_detected=evidence.construction_activity_detected,
                thermal_hotspot_count=evidence.thermal_hotspot_count,
                biomass_burning_hotspots=evidence.biomass_burning_hotspots,
                industrial_thermal_hotspots=evidence.industrial_thermal_hotspots,
                max_fire_radiative_power_mw=evidence.max_fire_radiative_power_mw,
                category_scores=evidence.category_scores,
                confidence=evidence.confidence,
                sources=evidence.sources,
                notes=evidence.notes,
            )
            session.add(observation)
            stored += 1

        await session.commit()
        logger.info("satellite.fetch_complete", wards_stored=stored)

    await engine.dispose()
