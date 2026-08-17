from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.repositories.base import BaseRepository


class MonitoringStationRepository(BaseRepository[MonitoringStation]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MonitoringStation, session)

    async def get_active_by_city(self, city: str) -> list[MonitoringStation]:
        result = await self.session.execute(
            select(MonitoringStation).where(
                MonitoringStation.city == city,
                MonitoringStation.is_active.is_(True),
                MonitoringStation.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def get_by_station_code(self, code: str) -> MonitoringStation | None:
        result = await self.session.execute(
            select(MonitoringStation).where(
                MonitoringStation.station_code == code,
                MonitoringStation.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_stations_needing_maintenance(
        self, threshold: float = 0.7
    ) -> list[MonitoringStation]:
        result = await self.session.execute(
            select(MonitoringStation).where(
                MonitoringStation.maintenance_score < threshold,
                MonitoringStation.is_active.is_(True),
                MonitoringStation.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())


class AQIReadingRepository(BaseRepository[AQIReading]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AQIReading, session)

    async def get_latest_by_station(self, station_id: UUID) -> AQIReading | None:
        result = await self.session.execute(
            select(AQIReading)
            .where(
                AQIReading.station_id == station_id,
                AQIReading.quality_flag != QualityFlag.INVALID,
                AQIReading.is_deleted.is_(False),
            )
            .order_by(desc(AQIReading.timestamp))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_history(
        self,
        station_id: UUID | None,
        start_time: datetime,
        end_time: datetime,
        interval: str = "1h",
    ) -> list[dict]:
        interval_map = {
            "15m": "15 minutes",
            "1h": "1 hour",
            "6h": "6 hours",
            "24h": "1 day",
        }
        pg_interval = interval_map.get(interval, "1 hour")

        if station_id:
            stmt = text(
                """
                SELECT
                    time_bucket(:interval, timestamp) AS bucket,
                    AVG(pm25) AS pm25,
                    AVG(pm10) AS pm10,
                    AVG(aqi) AS aqi,
                    AVG(no2) AS no2,
                    AVG(so2) AS so2,
                    AVG(co) AS co,
                    AVG(o3) AS o3,
                    AVG(temperature) AS temperature,
                    AVG(humidity) AS humidity,
                    COUNT(*) AS reading_count
                FROM aqi_readings
                WHERE station_id = :station_id
                  AND timestamp BETWEEN :start_time AND :end_time
                  AND is_deleted = false
                  AND quality_flag != 'invalid'
                GROUP BY bucket
                ORDER BY bucket
            """
            )
            result = await self.session.execute(
                stmt,
                {
                    "interval": pg_interval,
                    "station_id": station_id,
                    "start_time": start_time,
                    "end_time": end_time,
                },
            )
        else:
            stmt = text(
                """
                SELECT
                    time_bucket(:interval, r.timestamp) AS bucket,
                    AVG(r.pm25) AS pm25,
                    AVG(r.pm10) AS pm10,
                    AVG(r.aqi) AS aqi,
                    AVG(r.no2) AS no2,
                    AVG(r.so2) AS so2,
                    AVG(r.co) AS co,
                    AVG(r.temperature) AS temperature,
                    AVG(r.humidity) AS humidity,
                    COUNT(*) AS reading_count
                FROM aqi_readings r
                WHERE r.timestamp BETWEEN :start_time AND :end_time
                  AND r.is_deleted = false
                  AND r.quality_flag != 'invalid'
                GROUP BY bucket
                ORDER BY bucket
            """
            )
            result = await self.session.execute(
                stmt,
                {
                    "interval": pg_interval,
                    "start_time": start_time,
                    "end_time": end_time,
                },
            )

        return [dict(row._mapping) for row in result]

    async def get_city_average_aqi(self, city: str) -> float | None:
        stmt = text(
            """
            SELECT AVG(r.aqi)
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp > NOW() - INTERVAL '1 hour'
              AND r.is_deleted = false
              AND r.quality_flag != 'invalid'
        """
        )
        result = await self.session.scalar(stmt, {"city": city})
        return float(result) if result is not None else None

    async def get_ward_aqi_snapshot(self, city: str) -> list[dict]:
        stmt = text(
            """
            SELECT
                s.ward_id,
                AVG(r.aqi) AS avg_aqi,
                MAX(r.aqi) AS max_aqi,
                AVG(r.pm25) AS avg_pm25,
                COUNT(DISTINCT s.id) AS station_count,
                MAX(r.timestamp) AS last_reading
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp > NOW() - INTERVAL '1 hour'
              AND r.is_deleted = false
              AND r.quality_flag != 'invalid'
              AND s.ward_id IS NOT NULL
            GROUP BY s.ward_id
            ORDER BY avg_aqi DESC
        """
        )
        result = await self.session.execute(stmt, {"city": city})
        return [dict(row._mapping) for row in result]
