from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import desc, func, select, text
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

    async def get_active_all_cities(self) -> list[MonitoringStation]:
        """Active stations across every city that has monitoring stations
        defined, for the India-wide map view. Returns whatever real
        stations already exist in the DB (Pune, Mumbai, etc. per the
        seeder) — never fabricates stations for cities without data."""
        result = await self.session.execute(
            select(MonitoringStation).where(
                MonitoringStation.is_active.is_(True),
                MonitoringStation.is_deleted.is_(False),
            )
        )
        return list(result.scalars().all())

    async def search_by_geography(
        self,
        *,
        country: str | None = None,
        state: str | None = None,
        city: str | None = None,
        min_lat: float | None = None,
        min_lon: float | None = None,
        max_lat: float | None = None,
        max_lon: float | None = None,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[MonitoringStation], int]:
        """Paginated station search for GET /api/v1/aqi/india.

        Plain lat/lon bounding-box filter on the existing float columns —
        not a PostGIS ST_Within polygon query — since this platform has no
        loaded India/state boundary geometry. `country`/`state` filtering
        uses the actual `country`/`state` columns (see migration
        019_monitoring_station_state_country), never city-name matching:
        a station is "in India" because its `country` column says so (set
        at ingestion from real provider/fixture data), not because its
        city name looks Indian.

        Ordered by city then name for stable pagination.
        """
        conditions = [MonitoringStation.is_deleted.is_(False)]
        if active_only:
            conditions.append(MonitoringStation.is_active.is_(True))
        if country:
            conditions.append(MonitoringStation.country == country)
        if state:
            conditions.append(MonitoringStation.state == state)
        if city:
            conditions.append(MonitoringStation.city == city)
        if min_lat is not None:
            conditions.append(MonitoringStation.latitude >= min_lat)
        if max_lat is not None:
            conditions.append(MonitoringStation.latitude <= max_lat)
        if min_lon is not None:
            conditions.append(MonitoringStation.longitude >= min_lon)
        if max_lon is not None:
            conditions.append(MonitoringStation.longitude <= max_lon)

        query = select(MonitoringStation).where(*conditions)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query)

        query = (
            query.order_by(MonitoringStation.city, MonitoringStation.name)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all()), total or 0

    async def distinct_states(self, country: str) -> list[str]:
        """Real, sorted list of distinct non-null states actually present
        for `country` — backs GET /api/v1/aqi/india/states, so the
        frontend's state filter reflects only what the database actually
        has, never an invented list of India's states.
        """
        result = await self.session.execute(
            select(MonitoringStation.state)
            .where(
                MonitoringStation.country == country,
                MonitoringStation.state.isnot(None),
                MonitoringStation.is_deleted.is_(False),
            )
            .distinct()
            .order_by(MonitoringStation.state)
        )
        return [row[0] for row in result.all()]

    async def get_by_station_code(self, code: str) -> MonitoringStation | None:
        result = await self.session.execute(
            select(MonitoringStation).where(
                MonitoringStation.station_code == code,
                MonitoringStation.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_station_codes(
        self, codes: list[str]
    ) -> dict[str, MonitoringStation]:
        """Bulk lookup by station_code, keyed by the code itself, for the
        six-station real-time Pune Live AQI view (see
        app.services.aqi_providers.pune_stations.REQUIRED_STATIONS) where
        some codes may not have a row yet (not yet resolved against
        OpenAQ) — callers merge this against the full required list
        rather than assuming every code comes back.
        """
        if not codes:
            return {}
        result = await self.session.execute(
            select(MonitoringStation).where(
                MonitoringStation.station_code.in_(codes),
                MonitoringStation.is_deleted.is_(False),
            )
        )
        return {s.station_code: s for s in result.scalars().all()}

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

    async def get_latest_valid_by_station(self, station_id: UUID) -> AQIReading | None:
        """Latest reading for `station_id`, excluding BOTH invalid AND
        synthetic rows.

        `get_latest_by_station` above is a generic "most recent row
        regardless of provenance" lookup used across many features (India
        AQI, alerts, construction-dust, industrial-pollution, ...) and is
        deliberately left alone so this change doesn't alter their
        behaviour. Callers that must guarantee a genuinely-live observation
        — e.g. Green Infrastructure Optimization, which must never treat a
        statistical-fallback reading as real — use this method instead,
        which applies the same `quality_flag NOT IN ('invalid',
        'synthetic')` exclusion already used by get_history/
        get_city_average_aqi/get_station_trend/get_ward_aqi_snapshot above.
        """
        result = await self.session.execute(
            select(AQIReading)
            .where(
                AQIReading.station_id == station_id,
                AQIReading.quality_flag.notin_(
                    [QualityFlag.INVALID, QualityFlag.SYNTHETIC]
                ),
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
        city: str | None = None,
        ward_id: str | None = None,
    ) -> list[dict]:
        """Time-bucketed AQI history.

        Exactly one of `station_id` or `city` must be provided by the
        caller (enforced in the API layer) — this method itself still
        requires station_id XOR city to avoid silently aggregating every
        station in every city together, which was the original bug here.
        `ward_id` further narrows the city-wide query when given.
        """
        # asyncpg infers each bind parameter's Postgres type from how it's
        # used in the query — here, `CAST(:interval AS interval)` tells it
        # $1 is `interval`, so it encodes the Python value with its
        # interval codec. That codec requires a `timedelta`-like object
        # (it reads `.days` / `.seconds` / `.microseconds`); a plain str
        # like "1 hour" fails with `AttributeError: 'str' object has no
        # attribute 'days'` inside asyncpg's own encoder, surfacing as
        # `asyncpg.exceptions.DataError` before the query ever runs. Map
        # to real `timedelta`s instead of Postgres interval literals.
        interval_map = {
            "15m": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(days=1),
        }
        pg_interval = interval_map.get(interval, timedelta(hours=1))

        if station_id:
            stmt = text(
                """
                SELECT
                    time_bucket(CAST(:interval AS interval), timestamp) AS bucket,
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
                  AND quality_flag NOT IN ('invalid', 'synthetic')
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
        elif city:
            ward_clause = "AND s.ward_id = :ward_id" if ward_id else ""
            stmt = text(
                f"""
                SELECT
                    time_bucket(CAST(:interval AS interval), r.timestamp) AS bucket,
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
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE s.city = :city
                  {ward_clause}
                  AND r.timestamp BETWEEN :start_time AND :end_time
                  AND r.is_deleted = false
                  AND r.quality_flag NOT IN ('invalid', 'synthetic')
                GROUP BY bucket
                ORDER BY bucket
            """
            )
            # ward_clause is a fixed, code-controlled string (present or
            # absent) — never built from request input — so this f-string
            # is safe; the actual ward_id value is still bound below.
            params = {
                "interval": pg_interval,
                "city": city,
                "start_time": start_time,
                "end_time": end_time,
            }
            if ward_id:
                params["ward_id"] = ward_id
            result = await self.session.execute(stmt, params)
        else:
            raise ValueError("get_history requires either station_id or city")

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
              AND r.quality_flag NOT IN ('invalid', 'synthetic')
        """
        )
        result = await self.session.scalar(stmt, {"city": city})
        return float(result) if result is not None else None

    async def get_city_average_aqi_around(
        self, city: str, hours_ago: float, window_hours: float = 2.0
    ) -> float | None:
        """Average AQI for `city` in a window centered `hours_ago` in the past.

        Used to compute trend deltas (e.g. "now" vs "24h ago") from actual
        historical readings rather than a hard-coded placeholder.
        """
        half_window = window_hours / 2
        stmt = text(
            """
            SELECT AVG(r.aqi)
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp BETWEEN
                  NOW() - ((CAST(:hours_ago AS double precision) + CAST(:half_window AS double precision)) * INTERVAL '1 hour')
                  AND NOW() - ((CAST(:hours_ago AS double precision) - CAST(:half_window AS double precision)) * INTERVAL '1 hour')
              AND r.is_deleted = false
              AND r.quality_flag NOT IN ('invalid', 'synthetic')
            """
        )
        result = await self.session.scalar(
            stmt,
            {"city": city, "hours_ago": hours_ago, "half_window": half_window},
        )
        return float(result) if result is not None else None

    async def get_station_trend(self, station_id: UUID, current_aqi: int | None) -> str:
        """Compare the current reading to the station's average AQI over the
        preceding ~3 hours (excluding the very latest reading) to classify
        the short-term trend.
        """
        if current_aqi is None:
            return "unavailable"

        stmt = text(
            """
            SELECT AVG(aqi)
            FROM aqi_readings
            WHERE station_id = :station_id
              AND is_deleted = false
              AND quality_flag NOT IN ('invalid', 'synthetic')
              AND timestamp BETWEEN NOW() - INTERVAL '4 hours' AND NOW() - INTERVAL '30 minutes'
            """
        )
        result = await self.session.scalar(stmt, {"station_id": station_id})
        if result is None:
            return "unavailable"

        prior_avg = float(result)
        delta = current_aqi - prior_avg
        # A small dead-band avoids labelling normal noise as a trend.
        if abs(delta) < max(3.0, prior_avg * 0.05):
            return "stable"
        return "increasing" if delta > 0 else "decreasing"

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
              AND r.quality_flag NOT IN ('invalid', 'synthetic')
              AND s.ward_id IS NOT NULL
            GROUP BY s.ward_id
            ORDER BY avg_aqi DESC
        """
        )
        result = await self.session.execute(stmt, {"city": city})
        return [dict(row._mapping) for row in result]
