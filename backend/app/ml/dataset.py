"""Reproducible hourly ward-level dataset export + gap report (Week 2, D1/E1).

* Read-only (`SET TRANSACTION READ ONLY`); never writes to the database.
* Works without TimescaleDB (uses date_trunc on UTC timestamps).
* Excludes quality_flag in ('invalid','synthetic','stale') — the same filter
  used for training (Week 1 fix M3) so exports match what models may use.
* Writes no secrets (the database URL is never serialised).
* Weather columns are exported as stored in aqi_readings. Live OpenAQ ingestion
  stores NO weather (temperature/humidity/wind are NULL), so weather coverage is
  reported explicitly rather than assumed.

CLI:  python -m app.ml.dataset --days 90 --out-dir ./exports/hourly_ward
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

EXCLUDED_FLAGS = ("invalid", "synthetic", "stale")
WEATHER_COLUMNS = ("avg_temp", "avg_humidity", "avg_wind")

COLUMN_UNITS = {
    "hour": "UTC, start of hour (timestamp without tz, UTC semantics)",
    "ward_id": "ward identifier (e.g. W01)",
    "avg_aqi": "CPCB-style AQI index, unitless 0-500 (mean of station readings)",
    "avg_pm25": "ug/m3",
    "avg_temp": "degC",
    "avg_humidity": "% relative humidity",
    "avg_wind": "m/s",
    "n_readings": "count of raw readings aggregated",
    "n_stations": "count of distinct stations aggregated",
}

HOURLY_SQL = text(
    """
    SELECT date_trunc('hour', r.timestamp AT TIME ZONE 'UTC') AS hour,
           s.ward_id                                         AS ward_id,
           AVG(r.aqi)          AS avg_aqi,
           AVG(r.pm25)         AS avg_pm25,
           AVG(r.temperature)  AS avg_temp,
           AVG(r.humidity)     AS avg_humidity,
           AVG(r.wind_speed)   AS avg_wind,
           COUNT(*)            AS n_readings,
           COUNT(DISTINCT r.station_id) AS n_stations
    FROM aqi_readings r
    JOIN monitoring_stations s ON s.id = r.station_id
    WHERE r.timestamp >= :start AND r.timestamp < :end
      AND r.is_deleted = false
      AND r.aqi IS NOT NULL
      AND r.quality_flag NOT IN ('invalid', 'synthetic', 'stale')
      AND s.ward_id IS NOT NULL
    GROUP BY 1, 2
    ORDER BY 1, 2
    """
)
EXCLUDED_SQL = text(
    """
    SELECT r.quality_flag AS flag, COUNT(*) AS n
    FROM aqi_readings r
    WHERE r.timestamp >= :start AND r.timestamp < :end AND r.is_deleted = false
    GROUP BY 1 ORDER BY 1
    """
)
WARDS_SQL = text(
    "SELECT DISTINCT ward_id FROM monitoring_stations "
    "WHERE ward_id IS NOT NULL AND is_deleted = false ORDER BY 1"
)


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


async def fetch_hourly_frame(
    session: AsyncSession, start: datetime, end: datetime
) -> tuple[pd.DataFrame, dict[str, int], list[str]]:
    await session.execute(text("SET TRANSACTION READ ONLY"))
    params = {"start": start, "end": end}
    rows = (await session.execute(HOURLY_SQL, params)).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=["hour", "ward_id", "avg_aqi", *WEATHER_COLUMNS])
    df["hour"] = pd.to_datetime(df["hour"])
    flags = {
        str(r["flag"]): int(r["n"])
        for r in (await session.execute(EXCLUDED_SQL, params)).mappings().all()
    }
    wards = [r[0] for r in (await session.execute(WARDS_SQL)).all()]
    return df, flags, wards


def _runs(missing_hours: list[pd.Timestamp]) -> list[tuple[pd.Timestamp, int]]:
    """Group sorted missing hours into (start, length_hours) runs."""
    runs: list[tuple[pd.Timestamp, int]] = []
    for h in missing_hours:
        if runs and h - (runs[-1][0] + pd.Timedelta(hours=runs[-1][1] - 1)) == (
            pd.Timedelta(hours=1)
        ):
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((h, 1))
    return runs


def compute_gap_report(
    df: pd.DataFrame,
    expected_wards: list[str],
    start: datetime,
    end: datetime,
    excluded_flag_counts: dict[str, int] | None = None,
    min_days: int = 90,
) -> dict:
    """Coverage report for an hourly ward frame over [start, end)."""
    start_h, end_h = floor_hour(start), floor_hour(end)
    grid = pd.date_range(
        start_h.replace(tzinfo=None),
        end_h.replace(tzinfo=None),
        freq="h",
        inclusive="left",
    )
    expected = len(grid)
    present_wards = sorted(df["ward_id"].unique()) if len(df) else []
    per_ward = {}
    for ward in sorted(set(expected_wards) | set(present_wards)):
        sub = df[df["ward_id"] == ward] if len(df) else df
        have = (
            pd.DatetimeIndex(pd.to_datetime(sub["hour"])).unique() if len(sub) else []
        )
        missing = sorted(set(grid) - set(have))
        runs = _runs(missing)
        per_ward[ward] = {
            "hours_present": expected - len(missing),
            "hours_missing": len(missing),
            "coverage_pct": (
                round(100 * (expected - len(missing)) / expected, 2)
                if expected
                else 0.0
            ),
            "first_hour": str(min(have)) if len(have) else None,
            "last_hour": str(max(have)) if len(have) else None,
            "longest_gap_hours": max((n for _, n in runs), default=0),
            "largest_gaps": [
                {"start": str(s), "hours": n}
                for s, n in sorted(runs, key=lambda r: -r[1])[:10]
            ],
        }
    weather = {
        c: round(100 * float(df[c].notna().mean()), 2) if len(df) else 0.0
        for c in WEATHER_COLUMNS
    }
    spans_days = (
        (pd.to_datetime(df["hour"]).max() - pd.to_datetime(df["hour"]).min()).days
        if len(df)
        else 0
    )
    full_ward_hours = (
        sum(w["hours_present"] for w in per_ward.values()) / (expected * len(per_ward))
        if expected and per_ward
        else 0.0
    )
    return {
        "window_start_utc": start_h.isoformat(),
        "window_end_utc": end_h.isoformat(),
        "expected_hours_per_ward": expected,
        "rows": int(len(df)),
        "wards_expected": sorted(expected_wards),
        "wards_with_no_data": sorted(
            w for w in expected_wards if w not in present_wards
        ),
        "wards_present_not_in_station_table": sorted(
            w for w in present_wards if w not in expected_wards
        ),
        "per_ward": per_ward,
        "overall_ward_hour_coverage_pct": round(100 * full_ward_hours, 2),
        "observed_span_days": int(spans_days),
        "weather_coverage_pct": weather,
        "excluded_reading_counts_by_quality_flag": excluded_flag_counts or {},
        "meets_min_days": bool(spans_days >= min_days),
        "min_days_required": min_days,
        "weather_usable_for_training": all(v > 0 for v in weather.values()),
        "limitations": [
            "Weather columns come from aqi_readings; live OpenAQ ingestion stores "
            "no weather, so weather coverage is usually 0% unless an external "
            "historical weather source is merged.",
            "Hourly values are means of whatever readings exist in the hour; hours "
            "with one reading and hours with many are not distinguished (see n_readings).",
        ],
    }


def to_markdown(report: dict) -> str:
    lines = [
        "# Hourly ward dataset gap report",
        "",
        f"Window (UTC): {report['window_start_utc']} -> {report['window_end_utc']}",
        f"Rows: {report['rows']} · observed span: {report['observed_span_days']} days "
        f"(required >= {report['min_days_required']}: "
        f"{'YES' if report['meets_min_days'] else 'NO'})",
        f"Overall ward-hour coverage: {report['overall_ward_hour_coverage_pct']}%",
        f"Weather coverage %: {report['weather_coverage_pct']} "
        f"(usable for training: {report['weather_usable_for_training']})",
        f"Wards with no data: {report['wards_with_no_data'] or 'none'}",
        f"Excluded readings by flag: {report['excluded_reading_counts_by_quality_flag']}",
        "",
        "| ward | coverage % | missing h | longest gap h | first | last |",
        "|---|---|---|---|---|---|",
    ]
    for w, d in report["per_ward"].items():
        lines.append(
            f"| {w} | {d['coverage_pct']} | {d['hours_missing']} | "
            f"{d['longest_gap_hours']} | {d['first_hour']} | {d['last_hour']} |"
        )
    lines += ["", "Limitations:", *[f"- {x}" for x in report["limitations"]]]
    return "\n".join(lines) + "\n"


def write_export(
    df: pd.DataFrame, report: dict, out_dir: Path, params: dict
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "hourly_ward_dataset.csv"
    df.sort_values(["hour", "ward_id"]).to_csv(csv_path, index=False)
    sha = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    meta = {
        "extracted_at_utc": datetime.now(UTC).isoformat(),
        "parameters": params,
        "row_count": int(len(df)),
        "csv_sha256": sha,
        "source_tables": ["aqi_readings", "monitoring_stations"],
        "filters": {
            "excluded_quality_flags": list(EXCLUDED_FLAGS),
            "requires": "aqi IS NOT NULL, ward_id IS NOT NULL, is_deleted = false",
        },
        "columns_and_units": COLUMN_UNITS,
        "transformations": [
            "hourly mean per (ward, UTC hour) of reading values",
            "timestamps normalised to UTC (date_trunc on AT TIME ZONE 'UTC')",
        ],
        "contains_secrets": False,
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
    (out_dir / "gap_report.json").write_text(json.dumps(report, indent=2))
    (out_dir / "gap_report.md").write_text(to_markdown(report))
    return {"csv": str(csv_path), "sha256": sha}


async def export(database_url: str, days: int, end: datetime | None, out_dir: Path):
    end_h = floor_hour(end or datetime.now(UTC))
    start_h = end_h - timedelta(days=days)
    engine = create_async_engine(database_url, echo=False)
    try:
        async with AsyncSession(engine) as session:
            df, flags, wards = await fetch_hourly_frame(session, start_h, end_h)
    finally:
        await engine.dispose()
    report = compute_gap_report(df, wards, start_h, end_h, flags, min_days=days)
    paths = write_export(
        df, report, out_dir, {"days": days, "start": str(start_h), "end": str(end_h)}
    )
    return report, paths


def main() -> None:  # pragma: no cover - thin CLI
    from app.core.config import settings

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--end", type=str, default=None, help="ISO UTC end (default: now)")
    p.add_argument("--out-dir", type=Path, default=Path("exports/hourly_ward"))
    a = p.parse_args()
    end = datetime.fromisoformat(a.end).replace(tzinfo=UTC) if a.end else None
    report, paths = asyncio.run(export(settings.DATABASE_URL, a.days, end, a.out_dir))
    print(
        json.dumps(
            {
                "paths": paths,
                "meets_min_days": report["meets_min_days"],
                "weather_usable_for_training": report["weather_usable_for_training"],
            }
        )
    )


if __name__ == "__main__":  # pragma: no cover
    main()
