"""Traffic-pollution correlation analysis.

Combines hourly AQI/pollutant readings with the traffic-level provider
(app.services.traffic_provider) to describe an *association* between
traffic level and pollution — never a causal claim, per the hackathon
brief's explicit "associated with, not caused by" requirement.

If every traffic reading in the window came from the demo (time-of-day)
model, the result is clearly labeled as demo-derived: on synthetic AQI
data, the "traffic effect" would just reflect the same synthetic model's
own built-in assumptions, not independent real-world evidence, and the
response says so rather than presenting it as a discovered pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.services.traffic_provider import (
    TrafficDataSource,
    TrafficLevel,
    get_traffic_reading,
)


@dataclass
class TrafficPeriodStats:
    traffic_level: TrafficLevel
    reading_count: int
    avg_aqi: float | None
    avg_pm25: float | None
    avg_pm10: float | None
    avg_no2: float | None


@dataclass
class TrafficPollutionAnalysis:
    period_stats: list[TrafficPeriodStats]
    high_vs_low_aqi_ratio: float | None
    observation: str
    traffic_data_source: TrafficDataSource
    traffic_data_note: str
    sample_size: int


def _mean(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def analyze_traffic_pollution(
    *,
    hourly_readings: list[dict],
    ward_id: str | None = None,
) -> TrafficPollutionAnalysis:
    """Group hourly readings by traffic level and summarize the association.

    `hourly_readings` should come from the existing AQI history repository
    (time-bucketed averages: bucket, aqi, pm25, pm10, no2) — no new data
    source is introduced here.
    """
    buckets: dict[TrafficLevel, dict[str, list[float]]] = {
        level: {"aqi": [], "pm25": [], "pm10": [], "no2": []} for level in TrafficLevel
    }
    sources_seen: set[TrafficDataSource] = set()
    last_note = ""

    for row in hourly_readings:
        ts: datetime = row["bucket"]
        traffic = get_traffic_reading(ts, ward_id=ward_id)
        sources_seen.add(traffic.source)
        last_note = traffic.note

        for key in ("aqi", "pm25", "pm10", "no2"):
            val = row.get(key)
            if val is not None:
                buckets[traffic.level][key].append(val)

    period_stats = [
        TrafficPeriodStats(
            traffic_level=level,
            reading_count=len(buckets[level]["aqi"]),
            avg_aqi=_mean(buckets[level]["aqi"]),
            avg_pm25=_mean(buckets[level]["pm25"]),
            avg_pm10=_mean(buckets[level]["pm10"]),
            avg_no2=_mean(buckets[level]["no2"]),
        )
        for level in TrafficLevel
    ]

    high_stats = next(s for s in period_stats if s.traffic_level == TrafficLevel.HIGH)
    low_stats = next(s for s in period_stats if s.traffic_level == TrafficLevel.LOW)

    ratio = None
    if high_stats.avg_aqi is not None and low_stats.avg_aqi and low_stats.avg_aqi > 0:
        ratio = round(high_stats.avg_aqi / low_stats.avg_aqi, 2)

    total_readings = sum(s.reading_count for s in period_stats)

    if total_readings < 4:
        observation = (
            "Not enough paired readings in this window to describe a traffic-pollution "
            "association reliably."
        )
    elif ratio is not None and ratio > 1.1:
        observation = (
            f"Higher-traffic periods are associated with higher AQI in this window "
            f"(avg {high_stats.avg_aqi} vs {low_stats.avg_aqi} during low-traffic periods). "
            "This describes an association, not a confirmed causal effect."
        )
    elif ratio is not None and ratio < 0.9:
        observation = (
            "This window does not show higher-traffic periods associated with higher AQI — "
            "other factors (wind, industrial activity, weather) may dominate here."
        )
    else:
        observation = "No clear association between traffic level and AQI is evident in this window."

    source = (
        TrafficDataSource.CSV
        if sources_seen == {TrafficDataSource.CSV}
        else TrafficDataSource.DEMO
    )
    if source == TrafficDataSource.DEMO:
        observation += (
            " Traffic levels here are a time-of-day scheduling model (Demo Data), not "
            "measured traffic — so this reflects the model's own peak-hour assumption, "
            "not independently observed traffic-pollution evidence."
        )

    return TrafficPollutionAnalysis(
        period_stats=period_stats,
        high_vs_low_aqi_ratio=ratio,
        observation=observation,
        traffic_data_source=source,
        traffic_data_note=last_note,
        sample_size=total_readings,
    )
