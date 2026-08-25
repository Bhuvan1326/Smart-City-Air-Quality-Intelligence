"""Unit tests for app.services.traffic_provider. No DB dependency."""

import tempfile
from datetime import datetime

from app.core.config import settings
from app.services.traffic_provider import (
    TrafficDataSource,
    TrafficLevel,
    _demo_traffic_level,
    get_traffic_reading,
)


def _reset_csv_cache():
    import app.services.traffic_provider as mod
    mod._csv_cache = None
    mod._csv_cache_path = None


def test_morning_peak_is_high():
    assert _demo_traffic_level(datetime(2026, 1, 1, 8, 0)) == TrafficLevel.HIGH


def test_evening_peak_is_high():
    assert _demo_traffic_level(datetime(2026, 1, 1, 18, 30)) == TrafficLevel.HIGH


def test_night_hours_are_low():
    assert _demo_traffic_level(datetime(2026, 1, 1, 3, 0)) == TrafficLevel.LOW


def test_midday_is_moderate():
    assert _demo_traffic_level(datetime(2026, 1, 1, 13, 0)) == TrafficLevel.MODERATE


def test_demo_provider_never_labeled_live():
    original = settings.TRAFFIC_PROVIDER
    settings.TRAFFIC_PROVIDER = "demo"
    try:
        reading = get_traffic_reading(datetime(2026, 1, 1, 8, 0), ward_id="W01")
        assert reading.source == TrafficDataSource.DEMO
        assert "live" not in reading.note.lower() or "no live" in reading.note.lower()
    finally:
        settings.TRAFFIC_PROVIDER = original


def test_csv_provider_reads_matching_row():
    _reset_csv_cache()
    original_provider = settings.TRAFFIC_PROVIDER
    original_path = settings.TRAFFIC_CSV_PATH
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        f.write("ward_id,hour,level\nW01,8,high\nW02,8,low\n")
        path = f.name

    try:
        settings.TRAFFIC_PROVIDER = "csv"
        settings.TRAFFIC_CSV_PATH = path
        _reset_csv_cache()
        reading = get_traffic_reading(datetime(2026, 1, 1, 8, 0), ward_id="W02")
        assert reading.source == TrafficDataSource.CSV
        assert reading.level == TrafficLevel.LOW
    finally:
        settings.TRAFFIC_PROVIDER = original_provider
        settings.TRAFFIC_CSV_PATH = original_path
        _reset_csv_cache()


def test_csv_provider_falls_back_to_demo_when_no_match():
    _reset_csv_cache()
    original_provider = settings.TRAFFIC_PROVIDER
    original_path = settings.TRAFFIC_CSV_PATH
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
        f.write("ward_id,hour,level\nW99,3,high\n")
        path = f.name

    try:
        settings.TRAFFIC_PROVIDER = "csv"
        settings.TRAFFIC_CSV_PATH = path
        _reset_csv_cache()
        reading = get_traffic_reading(datetime(2026, 1, 1, 8, 0), ward_id="W01")
        assert reading.source == TrafficDataSource.DEMO
        assert "fallback" in reading.note.lower() or "demo" in reading.note.lower()
    finally:
        settings.TRAFFIC_PROVIDER = original_provider
        settings.TRAFFIC_CSV_PATH = original_path
        _reset_csv_cache()


def test_missing_csv_file_falls_back_to_demo():
    _reset_csv_cache()
    original_provider = settings.TRAFFIC_PROVIDER
    original_path = settings.TRAFFIC_CSV_PATH
    try:
        settings.TRAFFIC_PROVIDER = "csv"
        settings.TRAFFIC_CSV_PATH = "/nonexistent/path/traffic.csv"
        _reset_csv_cache()
        reading = get_traffic_reading(datetime(2026, 1, 1, 8, 0), ward_id="W01")
        assert reading.source == TrafficDataSource.DEMO
    finally:
        settings.TRAFFIC_PROVIDER = original_provider
        settings.TRAFFIC_CSV_PATH = original_path
        _reset_csv_cache()
