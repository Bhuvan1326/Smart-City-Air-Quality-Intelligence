"""Week 2 (D1/E1): export + gap report machinery.

Fixtures are SYNTHETIC and exist only to verify the tooling; no real coverage
or model result is derived from them.
"""

import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml import dataset

START = datetime(2026, 1, 1, tzinfo=UTC)


def _frame(hours, wards=("W01", "W02"), skip=(), weather=True):
    rows = []
    for h in range(hours):
        for w in wards:
            if (w, h) in skip:
                continue
            rows.append(
                {
                    "hour": (START + timedelta(hours=h)).replace(tzinfo=None),
                    "ward_id": w,
                    "avg_aqi": 100.0,
                    "avg_temp": 25.0 if weather else None,
                    "avg_humidity": 50.0 if weather else None,
                    "avg_wind": 2.0 if weather else None,
                }
            )
    return pd.DataFrame(rows)


def test_gap_report_detects_missing_hours_runs_and_missing_ward():
    skip = {("W01", 3), ("W01", 4), ("W01", 5), ("W01", 10)}
    df = _frame(24, skip=skip)
    r = dataset.compute_gap_report(
        df, ["W01", "W02", "W03"], START, START + timedelta(hours=24), min_days=1
    )
    assert r["expected_hours_per_ward"] == 24
    assert r["per_ward"]["W01"]["hours_missing"] == 4
    assert r["per_ward"]["W01"]["longest_gap_hours"] == 3
    assert r["per_ward"]["W02"]["coverage_pct"] == 100.0
    assert r["wards_with_no_data"] == ["W03"]
    assert r["per_ward"]["W03"]["hours_present"] == 0
    assert r["weather_usable_for_training"] is True


def test_gap_report_flags_missing_weather_and_short_span():
    df = _frame(48, weather=False)
    r = dataset.compute_gap_report(
        df, ["W01", "W02"], START, START + timedelta(hours=48)
    )
    assert r["weather_coverage_pct"] == {
        "avg_temp": 0.0,
        "avg_humidity": 0.0,
        "avg_wind": 0.0,
    }
    assert r["weather_usable_for_training"] is False
    assert r["meets_min_days"] is False  # 48 h << 90 days — never claimed


def test_empty_frame_is_reported_not_crashed():
    r = dataset.compute_gap_report(
        pd.DataFrame(columns=["hour", "ward_id", "avg_aqi", *dataset.WEATHER_COLUMNS]),
        ["W01"],
        START,
        START + timedelta(hours=5),
    )
    assert r["rows"] == 0 and r["wards_with_no_data"] == ["W01"]
    assert r["meets_min_days"] is False


def test_write_export_has_no_secrets_and_records_checksum(tmp_path):
    df = _frame(5)
    r = dataset.compute_gap_report(
        df, ["W01", "W02"], START, START + timedelta(hours=5)
    )
    out = dataset.write_export(df, r, tmp_path, {"days": 1})
    meta = json.loads((tmp_path / "metadata.json").read_text())
    assert meta["csv_sha256"] == out["sha256"] and meta["contains_secrets"] is False
    blob = "".join(p.read_text() for p in tmp_path.glob("*.json"))
    assert "postgresql" not in blob and "password" not in blob.lower()
    assert (tmp_path / "gap_report.md").exists()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_hourly_frame_filters_flags_and_aggregates_in_utc(test_engine):
    from geoalchemy2.elements import WKTElement

    from app.models.monitoring import AQIReading, MonitoringStation

    t0 = datetime(2026, 3, 1, 10, 5, tzinfo=UTC)
    async with AsyncSession(test_engine, expire_on_commit=False) as s:
        st = MonitoringStation(
            name="F",
            station_code="F1",
            city="Pune",
            ward_id="W01",
            operator="x",
            latitude=18.5,
            longitude=73.8,
            is_active=True,
            station_type="CAAQMS",
            geometry=WKTElement("POINT(73.8 18.5)", srid=4326),
        )
        s.add(st)
        await s.flush()

        def rd(minutes, aqi, flag):
            return AQIReading(
                station_id=st.id,
                pm25=10.0,
                aqi=aqi,
                timestamp=t0 + timedelta(minutes=minutes),
                latitude=18.5,
                longitude=73.8,
                quality_flag=flag,
                temperature=None,
            )

        s.add_all(
            [
                rd(0, 100, "good"),
                rd(30, 120, "good"),  # same hour -> mean 110
                rd(70, 999, "synthetic"),
                rd(80, 888, "stale"),
                rd(90, 777, "invalid"),
            ]
        )
        await s.commit()
        df, flags, wards = await dataset.fetch_hourly_frame(
            s, t0 - timedelta(hours=1), t0 + timedelta(hours=5)
        )
    assert len(df) == 1
    assert df.iloc[0]["avg_aqi"] == 110.0 and df.iloc[0]["n_readings"] == 2
    assert pd.Timestamp(df.iloc[0]["hour"]) == pd.Timestamp("2026-03-01 10:00:00")
    assert flags == {"good": 2, "invalid": 1, "stale": 1, "synthetic": 1}
    assert wards == ["W01"]
    assert pd.isna(df.iloc[0]["avg_temp"])  # weather NULL is preserved, not invented
