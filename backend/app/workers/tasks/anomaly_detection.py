import asyncio
from datetime import UTC, datetime

from app.core.config import settings
from app.core.logging import logger
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.anomaly_detection.detect_anomalies", bind=True)
def detect_anomalies(self):
    asyncio.run(_detect_async())


async def _detect_async():
    from geoalchemy2.elements import WKTElement
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.analytics import AnomalyEvent

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSession() as session:
        # Compare last reading to 7-day rolling average per station
        result = await session.execute(
            text(
                """
            WITH recent AS (
                SELECT r.station_id, r.aqi, r.timestamp,
                       s.ward_id, s.city, s.latitude, s.longitude, s.name
                FROM aqi_readings r
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE r.timestamp > NOW() - INTERVAL '15 minutes'
                  AND r.is_deleted = false AND r.quality_flag != 'invalid'
            ),
            baseline AS (
                SELECT r.station_id, AVG(r.aqi) AS avg_aqi, STDDEV(r.aqi) AS std_aqi
                FROM aqi_readings r
                WHERE r.timestamp BETWEEN NOW() - INTERVAL '7 days' AND NOW() - INTERVAL '1 hour'
                  AND r.is_deleted = false AND r.quality_flag != 'invalid'
                GROUP BY r.station_id
            )
            SELECT rc.station_id, rc.aqi, rc.timestamp, rc.ward_id, rc.city,
                   rc.latitude, rc.longitude, rc.name,
                   b.avg_aqi, b.std_aqi,
                   (rc.aqi - b.avg_aqi) / NULLIF(b.std_aqi, 0) AS z_score
            FROM recent rc
            JOIN baseline b ON rc.station_id = b.station_id
            WHERE (rc.aqi - b.avg_aqi) / NULLIF(b.std_aqi, 0) > 2.5
              AND rc.aqi > 150
        """
            )
        )
        spikes = result.fetchall()

        for spike in spikes:
            # Check if anomaly already logged in last 30 min
            already = await session.execute(
                text(
                    """
                SELECT id FROM anomaly_events
                WHERE station_id = :sid
                  AND detected_at > NOW() - INTERVAL '30 minutes'
                  AND is_deleted = false
                LIMIT 1
            """
                ),
                {"sid": spike.station_id},
            )
            if already.scalar():
                continue

            z = float(spike.z_score or 0)
            confidence = min(0.95, 0.6 + (z - 2.5) * 0.1)

            # Classify probable cause
            hour = datetime.now(UTC).hour
            if 7 <= hour <= 10 or 17 <= hour <= 20:
                cause = "Peak-hour vehicular emissions"
                category = "vehicular"
            elif spike.ward_id in ("W03", "W04"):
                cause = "Industrial stack emissions — elevated beyond baseline"
                category = "industrial"
            else:
                cause = "Unknown source — investigation required"
                category = "unknown"

            geom = WKTElement(f"POINT({spike.longitude} {spike.latitude})", srid=4326)
            event = AnomalyEvent(
                station_id=spike.station_id,
                ward_id=spike.ward_id,
                city=spike.city,
                detected_at=spike.timestamp,
                aqi_spike_value=int(spike.aqi),
                baseline_aqi=int(spike.avg_aqi or 0),
                probable_cause=cause,
                cause_category=category,
                confidence_score=round(confidence, 3),
                geometry=geom,
                root_cause_timeline={
                    "baseline_aqi": float(spike.avg_aqi or 0),
                    "spike_aqi": int(spike.aqi),
                    "z_score": round(float(z), 2),
                    "detected_at": (
                        spike.timestamp.isoformat() if spike.timestamp else None
                    ),
                },
            )
            session.add(event)
            logger.info(
                "anomaly.detected",
                station=spike.name,
                ward=spike.ward_id,
                aqi=spike.aqi,
                cause=category,
                confidence=confidence,
            )

        await session.commit()
        logger.info("anomaly_detection.complete", new_events=len(spikes))

    await engine.dispose()


@celery_app.task(name="app.workers.tasks.anomaly_detection.predict_sensor_maintenance")
def predict_sensor_maintenance():
    asyncio.run(_maintenance_async())


async def _maintenance_async():
    """
    Runs the explainable SensorMaintenancePredictor (app.ml.sensor_maintenance)
    against every active station's recent readings, persists a full
    SensorHealthAssessment per station, and syncs the summary failure
    probability back onto MonitoringStation.maintenance_score so existing
    dashboard/API consumers of that field keep working unchanged.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.ml.sensor_maintenance import SensorMaintenancePredictor
    from app.models.monitoring import SensorHealthAssessment

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    predictor = SensorMaintenancePredictor()

    async with AsyncSession() as session:
        stations_result = await session.execute(
            text(
                """
            SELECT id, name, city, ward_id, maintenance_score
            FROM monitoring_stations
            WHERE is_deleted = false AND is_active = true
        """
            )
        )
        stations = stations_result.fetchall()

        # Network-wide daily means, used by the predictor to tell apart a
        # station-specific fault from a genuine city-wide pollution event.
        network_result = await session.execute(
            text(
                """
            SELECT DATE(timestamp) AS day, AVG(aqi) AS avg_aqi
            FROM aqi_readings
            WHERE timestamp > NOW() - INTERVAL '7 days'
              AND is_deleted = false AND aqi IS NOT NULL
            GROUP BY DATE(timestamp)
            ORDER BY day
        """
            )
        )
        network_daily_means = [
            float(row.avg_aqi) for row in network_result if row.avg_aqi is not None
        ]

        assessed = 0
        for station in stations:
            recent_result = await session.execute(
                text(
                    """
                SELECT timestamp, aqi FROM aqi_readings
                WHERE station_id = :sid AND timestamp > NOW() - INTERVAL '48 hours'
                  AND is_deleted = false
                ORDER BY timestamp
            """
                ),
                {"sid": station.id},
            )
            recent = [
                {"timestamp": row.timestamp, "aqi": row.aqi} for row in recent_result
            ]

            baseline_result = await session.execute(
                text(
                    """
                SELECT timestamp, aqi FROM aqi_readings
                WHERE station_id = :sid
                  AND timestamp BETWEEN NOW() - INTERVAL '30 days' AND NOW() - INTERVAL '48 hours'
                  AND is_deleted = false AND aqi IS NOT NULL
                ORDER BY timestamp
            """
                ),
                {"sid": station.id},
            )
            baseline = [
                {"timestamp": row.timestamp, "aqi": row.aqi} for row in baseline_result
            ]

            result = predictor.assess(
                station_id=str(station.id),
                readings=recent,
                baseline_readings=baseline or None,
                network_daily_means=network_daily_means or None,
                prior_maintenance_score=station.maintenance_score,
            )

            assessment = SensorHealthAssessment(
                station_id=station.id,
                assessed_at=result.assessed_at,
                drift_score=result.drift_score,
                drift_direction=result.drift_direction,
                failure_probability=result.failure_probability,
                maintenance_priority=result.maintenance_priority,
                maintenance_priority_score=result.maintenance_priority_score,
                remaining_useful_life_days=result.remaining_useful_life_days,
                confidence=result.confidence,
                feature_importance=result.feature_importance,
                contributing_factors=result.contributing_factors,
                reasoning_trace=result.reasoning_trace,
                alternative_explanations=result.alternative_explanations,
                historical_comparison=result.historical_comparison,
                sample_size=result.sample_size,
                null_rate=result.null_rate,
                flatlined=result.flatlined,
                out_of_range_rate=result.out_of_range_rate,
            )
            session.add(assessment)

            new_score = round(1.0 - result.failure_probability, 2)
            await session.execute(
                text(
                    """
                UPDATE monitoring_stations SET maintenance_score = :score, updated_at = NOW()
                WHERE id = :sid
            """
                ),
                {"score": new_score, "sid": station.id},
            )

            assessed += 1
            if result.maintenance_priority in ("urgent", "critical"):
                logger.warning(
                    "sensor_maintenance.flagged",
                    station=station.name,
                    priority=result.maintenance_priority,
                    failure_probability=result.failure_probability,
                    rul_days=result.remaining_useful_life_days,
                )

        await session.commit()
        logger.info("maintenance_prediction.complete", assessed=assessed)

    await engine.dispose()
