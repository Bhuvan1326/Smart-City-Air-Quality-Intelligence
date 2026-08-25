"""Unit tests for app.services.location_recommendation.

Uses transient (unpersisted) SQLAlchemy model instances so these tests
have zero database dependency — they test the ranking/labeling logic only.
"""

from datetime import UTC, datetime, timedelta

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.services.data_freshness import FreshnessStatus
from app.services.location_recommendation import rank_locations


def _station(name: str, lat: float, lon: float, ward: str = "W01") -> MonitoringStation:
    return MonitoringStation(
        name=name,
        station_code=name.upper().replace(" ", "_"),
        city="Pune",
        ward_id=ward,
        operator="Test",
        latitude=lat,
        longitude=lon,
    )


def _reading(
    aqi: int | None, minutes_ago: int = 5, synthetic: bool = False
) -> AQIReading:
    return AQIReading(
        aqi=aqi,
        timestamp=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        quality_flag=QualityFlag.SYNTHETIC if synthetic else QualityFlag.GOOD,
    )


ORIGIN = (18.5204, 73.8567)  # Pune city center


def test_ranks_cleaner_air_first():
    dirty = (_station("Dirty Corner", 18.53, 73.86), _reading(280))
    clean = (_station("Clean Park", 18.55, 73.88), _reading(35))
    result = rank_locations([dirty, clean], origin_lat=ORIGIN[0], origin_lon=ORIGIN[1])
    assert result[0].station.name == "Clean Park"
    assert result[0].rank == 1


def test_distance_breaks_ties_on_equal_aqi():
    far = (_station("Far Clean", 18.65, 73.95), _reading(40))
    near = (_station("Near Clean", 18.525, 73.86), _reading(40))
    result = rank_locations([far, near], origin_lat=ORIGIN[0], origin_lon=ORIGIN[1])
    assert result[0].station.name == "Near Clean"


def test_missing_aqi_ranked_last_not_fabricated():
    known = (_station("Known", 18.53, 73.86), _reading(90))
    unknown = (_station("Unknown", 18.53, 73.86), _reading(None))
    result = rank_locations([known, unknown], origin_lat=ORIGIN[0], origin_lon=ORIGIN[1])
    assert result[-1].station.name == "Unknown"
    assert result[-1].aqi is None


def test_synthetic_reading_labeled_demo_not_live():
    demo = (_station("Demo Station", 18.53, 73.86), _reading(50, synthetic=True))
    result = rank_locations([demo], origin_lat=ORIGIN[0], origin_lon=ORIGIN[1])
    assert result[0].freshness == FreshnessStatus.DEMO
    assert "demo" in result[0].reason.lower()


def test_stale_reading_flagged_in_reason():
    stale = (_station("Stale Station", 18.53, 73.86), _reading(60, minutes_ago=300))
    result = rank_locations([stale], origin_lat=ORIGIN[0], origin_lon=ORIGIN[1])
    assert result[0].freshness == FreshnessStatus.STALE
    assert "outdated" in result[0].reason.lower()


def test_limit_is_respected():
    stations = [
        (_station(f"S{i}", 18.5 + i * 0.01, 73.8 + i * 0.01), _reading(50 + i))
        for i in range(10)
    ]
    result = rank_locations(stations, origin_lat=ORIGIN[0], origin_lon=ORIGIN[1], limit=3)
    assert len(result) == 3
    assert [r.rank for r in result] == [1, 2, 3]
