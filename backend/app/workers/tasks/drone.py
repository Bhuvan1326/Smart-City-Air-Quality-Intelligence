"""
Celery task: automatic hotspot detection for drone inspection.

Looks at the most recent PollutionAttribution + AnomalyEvent records to
find wards that plausibly warrant a physical drone inspection (high AQI,
high confidence attribution to a fixed source category like construction
or industrial, or an unresolved anomaly), then generates a DronePlanner
coverage plan for each and persists it — so an operator opens the drone
dashboard to already-generated candidate flight plans rather than an
empty screen.
"""

import asyncio

from app.core.config import settings
from app.core.logging import logger
from app.workers.celery_app import celery_app

# Same ward bounding boxes used by the satellite fetch task.
from app.workers.tasks.satellite import WARD_BBOXES


@celery_app.task(name="app.workers.tasks.drone.detect_hotspots_and_plan", bind=True)
def detect_hotspots_and_plan(self):
    asyncio.run(_detect_and_plan_async())


async def _detect_and_plan_async():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.enforcement import DroneFlightPlan
    from app.services.drone_planner import DronePlanner

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    planner = DronePlanner()

    async with AsyncSession() as session:
        # Wards with high, confidently-attributed construction/industrial
        # pollution in the last attribution run are the clearest drone
        # inspection candidates (a physical fly-over corroborates or
        # refutes what the satellite/statistical model inferred).
        result = await session.execute(text("""
            SELECT DISTINCT ON (ward_id) ward_id, city,
                   construction_pct, industrial_pct, overall_confidence
            FROM pollution_attributions
            WHERE is_deleted = false
              AND timestamp > NOW() - INTERVAL '6 hours'
              AND overall_confidence > 0.6
              AND (construction_pct > 20 OR industrial_pct > 30)
            ORDER BY ward_id, timestamp DESC
        """))
        candidates = result.fetchall()

        planned = 0
        for row in candidates:
            bbox = WARD_BBOXES.get(row.ward_id)
            if not bbox:
                continue
            min_lon, min_lat, max_lon, max_lat = bbox

            plan_result = planner.plan_coverage(
                hotspot_id=f"{row.ward_id}-auto-{planned}",
                bbox=(min_lat, min_lon, max_lat, max_lon),
            )
            if not plan_result.sorties:
                continue

            plan = DroneFlightPlan(
                hotspot_id=plan_result.hotspot_id,
                city=row.city,
                ward_id=row.ward_id,
                launch_latitude=plan_result.launch_point[0],
                launch_longitude=plan_result.launch_point[1],
                total_sorties=len(plan_result.sorties),
                total_waypoints=plan_result.total_waypoints,
                total_distance_meters=plan_result.total_distance_meters,
                coverage_area_sq_meters=plan_result.coverage_area_sq_meters,
                excluded_no_fly_zones=plan_result.excluded_no_fly_zones,
                reasoning=plan_result.reasoning
                + [
                    (
                        f"Auto-generated: construction={row.construction_pct}%, "
                        f"industrial={row.industrial_pct}%, confidence={row.overall_confidence}."
                    )
                ],
                geojson=plan_result.to_geojson(),
                status="planned",
            )
            session.add(plan)
            planned += 1

        await session.commit()
        logger.info("drone.auto_hotspot_planning_complete", plans_created=planned)

    await engine.dispose()
