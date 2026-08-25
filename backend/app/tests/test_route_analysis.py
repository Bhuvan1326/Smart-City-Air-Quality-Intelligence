"""Unit tests for app.services.route_analysis. Pure logic, no DB dependency."""

from datetime import UTC, datetime, timedelta

from app.models.monitoring import AQIReading, MonitoringStation, QualityFlag
from app.services.route_analysis import analyze_route


def _station(name: str, lat: float, lon: float) -> MonitoringStation:
    return MonitoringStation(
        name=name, station_code=name.upper(), city="Pune", ward_id="W01",
        operator="Test", latitude=lat, longitude=lon,
    )


def _reading(aqi: int | None, minutes_ago: int = 5) -> AQIReading:
    return AQIReading(aqi=aqi, timestamp=datetime.now(UTC) - timedelta(minutes=minutes_ago), quality_flag=QualityFlag.GOOD)


# Pune-ish coordinates
ORIGIN = (18.50, 73.80)
DEST = (18.56, 73.90)


def test_samples_count_matches_request():
    stations = [(_station("A", 18.52, 73.85), _reading(80))]
    result = analyze_route(
        origin_lat=ORIGIN[0], origin_lon=ORIGIN[1],
        dest_lat=DEST[0], dest_lon=DEST[1],
        stations_with_readings=stations, num_samples=5,
    )
    assert len(result.samples) == 5
    assert result.samples[0].sequence == 0
    assert result.samples[-1].sequence == 4


def test_average_and_peak_aqi_computed():
    stations = [
        (_station("Clean", 18.50, 73.80), _reading(30)),
        (_station("Dirty", 18.56, 73.90), _reading(280)),
    ]
    result = analyze_route(
        origin_lat=ORIGIN[0], origin_lon=ORIGIN[1],
        dest_lat=DEST[0], dest_lon=DEST[1],
        stations_with_readings=stations, num_samples=6,
    )
    assert result.peak_aqi == 280
    assert result.average_aqi is not None
    assert result.overall_exposure in ("low", "moderate", "high", "very_high")


def test_no_station_data_yields_unknown_exposure_not_fabricated():
    result = analyze_route(
        origin_lat=ORIGIN[0], origin_lon=ORIGIN[1],
        dest_lat=DEST[0], dest_lon=DEST[1],
        stations_with_readings=[], num_samples=4,
    )
    assert result.average_aqi is None
    assert result.peak_aqi is None
    assert result.overall_exposure == "unknown"
    assert all(s.aqi is None for s in result.samples)


def test_high_pollution_segments_flagged():
    stations = [
        (_station("Clean1", 18.50, 73.80), _reading(20)),
        (_station("Hotspot", 18.53, 73.85), _reading(250)),
        (_station("Clean2", 18.56, 73.90), _reading(25)),
    ]
    result = analyze_route(
        origin_lat=ORIGIN[0], origin_lon=ORIGIN[1],
        dest_lat=DEST[0], dest_lon=DEST[1],
        stations_with_readings=stations, num_samples=5,
    )
    assert len(result.high_pollution_segments) > 0


def test_alternative_route_is_never_fabricated():
    result = analyze_route(
        origin_lat=ORIGIN[0], origin_lon=ORIGIN[1],
        dest_lat=DEST[0], dest_lon=DEST[1],
        stations_with_readings=[],
    )
    assert "cannot be calculated" in result.alternative_route_note.lower()
    assert result.routing_data_source == "straight_line_estimate"


def test_single_sample_does_not_divide_by_zero():
    result = analyze_route(
        origin_lat=ORIGIN[0], origin_lon=ORIGIN[1],
        dest_lat=DEST[0], dest_lon=DEST[1],
        stations_with_readings=[], num_samples=1,
    )
    assert len(result.samples) == 1
    assert result.samples[0].distance_from_origin_km == 0.0
