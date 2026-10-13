from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.weather import WeatherMeasurement

SOURCE_OPEN_METEO = "open_meteo"

_HOURLY_FIELDS = {
    "temperature": "temperature_2m",
    "humidity": "relative_humidity_2m",
    "wind_speed": "wind_speed_10m",
    "wind_direction": "wind_direction_10m",
    "precipitation": "precipitation",
    "pressure": "surface_pressure",
    "weather_code": "weather_code",
}


def map_open_meteo_hourly(
    payload: dict,
    *,
    city: str,
    latitude: float,
    longitude: float,
    fetched_at: datetime,
    is_forecast: bool = True,
    source: str = SOURCE_OPEN_METEO,
) -> list[WeatherMeasurement]:

    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        return []
    times = hourly.get("time")
    if not isinstance(times, list):
        return []

    fetched = fetched_at if fetched_at.tzinfo else fetched_at.replace(tzinfo=UTC)
    by_hour: dict[datetime, WeatherMeasurement] = {}
    for index, raw_time in enumerate(times):
        try:
            observed_at = datetime.fromisoformat(str(raw_time))
        except (TypeError, ValueError):
            continue
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=UTC)
        else:
            observed_at = observed_at.astimezone(UTC)

        values: dict[str, float | int | None] = {}
        for column, api_field in _HOURLY_FIELDS.items():
            series = hourly.get(api_field)
            raw = (
                series[index]
                if isinstance(series, list) and index < len(series)
                else None
            )
            if raw is None:
                values[column] = None
                continue
            try:
                values[column] = int(raw) if column == "weather_code" else float(raw)
            except (TypeError, ValueError):
                values[column] = None

        by_hour[observed_at] = WeatherMeasurement(
            city=city,
            latitude=latitude,
            longitude=longitude,
            source=source,
            is_forecast=is_forecast,
            observed_at=observed_at,
            fetched_at=fetched,
            is_deleted=False,
            deleted_at=None,
            **values,
        )

    return list(by_hour.values())


async def persist_weather_rows(
    session: AsyncSession, rows: list[WeatherMeasurement]
) -> int:
    if not rows:
        return 0

    table = WeatherMeasurement.__table__
    payload = [
        {
            **{
                column.name: getattr(row, column.name)
                for column in table.columns
                if column.name not in {"id", "created_at", "updated_at"}
            },
            "is_deleted": row.is_deleted if row.is_deleted is not None else False,
            "deleted_at": row.deleted_at if row.is_deleted else None,
        }
        for row in rows
    ]
    stmt = pg_insert(table).values(payload)
    update_cols = {
        column.name: getattr(stmt.excluded, column.name)
        for column in table.columns
        if column.name
        not in {"id", "created_at", "updated_at", "city", "observed_at", "source"}
    }
    update_cols.update(
        is_deleted=table.c.is_deleted | stmt.excluded.is_deleted,
        deleted_at=case(
            (table.c.is_deleted, table.c.deleted_at),
            else_=stmt.excluded.deleted_at,
        ),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_weather_city_time_source", set_=update_cols
    )
    await session.execute(stmt)
    await session.commit()
    return len(payload)


async def fetch_and_persist_weather(
    session: AsyncSession,
    client,
    *,
    base_url: str,
    city: str,
    latitude: float,
    longitude: float,
    forecast_days: int = 3,
) -> int:
    import httpx

    url = (
        f"{base_url}/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,"
        f"wind_direction_10m,precipitation,surface_pressure,weather_code"
        f"&forecast_days={forecast_days}&timezone=UTC"
    )
    try:
        resp = await client.get(url)
    except (httpx.HTTPError, OSError) as e:
        logger.error("weather_fetch.error", city=city, error=str(e))
        return 0
    if resp.status_code != 200:
        logger.warning("weather_fetch.failed", city=city, status=resp.status_code)
        return 0

    fetched_at = datetime.now(UTC)
    rows = map_open_meteo_hourly(
        resp.json(),
        city=city,
        latitude=latitude,
        longitude=longitude,
        fetched_at=fetched_at,
        is_forecast=True,
    )
    written = await persist_weather_rows(session, rows)
    logger.info(
        "weather_fetch.persisted",
        city=city,
        rows=written,
        hours=len(rows),
    )
    return written
