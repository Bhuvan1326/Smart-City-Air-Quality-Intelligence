"""
Predictive Sensor Maintenance.

Estimates, per monitoring station, whether its readings show signs of sensor
drift or impending failure, and how urgently it needs a maintenance visit.

Design goals (mirrors the explainability contract used by the LangGraph
agents elsewhere in this codebase — see app/agents/langgraph_agents.py):
  - every output carries a confidence score
  - every output carries a feature-importance breakdown
  - every output carries a plain-language reasoning trace
  - every output lists at least one alternative explanation, so an operator
    reviewing the flag isn't just told "this sensor is broken" with no way
    to sanity-check it against a more mundane cause
  - nothing here is a black box: the whole computation is closed-form
    statistics (CUSUM drift, rolling variance, logistic blend), not a
    trained model with opaque internals, precisely so it stays inspectable.

This module is pure — it takes readings already pulled from the DB and
returns a dataclass. The DB/Celery plumbing lives in
app/workers/tasks/anomaly_detection.py, keeping the maths independently
testable.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime

# Physically implausible AQI readings — used to flag stuck/faulty sensors.
_MIN_PLAUSIBLE_AQI = 0
_MAX_PLAUSIBLE_AQI = 999
# A station reporting near-zero variance for a full day is almost certainly
# stuck (flatlined), not experiencing genuinely constant air quality.
_FLATLINE_STD_THRESHOLD = 1.5
# CUSUM decision threshold, in baseline standard deviations, before a drift
# is considered real rather than noise.
_CUSUM_THRESHOLD_SIGMA = 4.0


@dataclass
class SensorHealthAssessment:
    station_id: str
    assessed_at: datetime

    drift_score: float  # 0 (no drift) .. 1 (severe drift)
    drift_direction: str  # "upward" | "downward" | "none"
    failure_probability: float  # 0..1
    maintenance_priority: str  # "routine" | "soon" | "urgent" | "critical"
    maintenance_priority_score: float  # 0..100, for sorting
    remaining_useful_life_days: int | None  # None if not degrading / insufficient data
    confidence: float  # 0..1, based on sample size + estimate stability

    feature_importance: dict[str, float] = field(default_factory=dict)
    contributing_factors: list[str] = field(default_factory=list)
    reasoning_trace: list[str] = field(default_factory=list)
    alternative_explanations: list[str] = field(default_factory=list)
    historical_comparison: dict | None = None

    sample_size: int = 0
    null_rate: float = 0.0
    flatlined: bool = False
    out_of_range_rate: float = 0.0


def _cusum_drift(
    daily_means: list[float], baseline_mean: float, baseline_std: float
) -> tuple[float, str]:
    """
    Two-sided CUSUM control chart. Returns (drift_score in [0,1], direction).
    Detects a *sustained* shift away from baseline, which is what
    distinguishes genuine sensor drift from a single noisy day.
    """
    if not daily_means or baseline_std <= 0:
        return 0.0, "none"

    k = 0.5 * baseline_std  # allowance / slack, standard CUSUM tuning
    sh, sl = 0.0, 0.0
    max_sh, max_sl = 0.0, 0.0
    for x in daily_means:
        sh = max(0.0, sh + (x - baseline_mean) - k)
        sl = max(0.0, sl + (baseline_mean - x) - k)
        max_sh = max(max_sh, sh)
        max_sl = max(max_sl, sl)

    threshold = _CUSUM_THRESHOLD_SIGMA * baseline_std
    if max_sh >= max_sl and max_sh > 0:
        score = min(1.0, max_sh / threshold) if threshold > 0 else 0.0
        return score, "upward" if score > 0.15 else "none"
    elif max_sl > 0:
        score = min(1.0, max_sl / threshold) if threshold > 0 else 0.0
        return score, "downward" if score > 0.15 else "none"
    return 0.0, "none"


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class SensorMaintenancePredictor:
    """Stateless assessor — call `.assess()` per station."""

    def assess(
        self,
        station_id: str,
        readings: list[dict],
        *,
        baseline_readings: list[dict] | None = None,
        network_daily_means: list[float] | None = None,
        prior_maintenance_score: float | None = None,
        now: datetime | None = None,
    ) -> SensorHealthAssessment:
        """
        readings: recent (e.g. last 24-72h) readings for this station, each a
            dict with at least {"timestamp": datetime, "aqi": float | None}.
        baseline_readings: a longer historical window (e.g. 30 days) used to
            establish what "normal" looks like for this station.
        network_daily_means: same-period daily mean AQI across the *whole*
            monitoring network, used to distinguish a station-specific fault
            from a real, network-wide pollution event (the key alternative
            explanation for an apparent "drift").
        prior_maintenance_score: the station's previous maintenance_score,
            for historical trend comparison.
        """
        now = now or datetime.now(UTC)
        reasoning: list[str] = []
        n = len(readings)

        if n == 0:
            return SensorHealthAssessment(
                station_id=station_id,
                assessed_at=now,
                drift_score=0.0,
                drift_direction="none",
                failure_probability=0.5,
                maintenance_priority="urgent",
                maintenance_priority_score=70.0,
                remaining_useful_life_days=None,
                confidence=0.2,
                reasoning_trace=[
                    "No readings in the assessment window — station may be offline entirely."
                ],
                alternative_explanations=[
                    "Network/connectivity outage rather than sensor hardware fault."
                ],
                sample_size=0,
                null_rate=1.0,
            )

        aqi_values = [r["aqi"] for r in readings]
        null_count = sum(1 for v in aqi_values if v is None)
        null_rate = null_count / n
        present = [v for v in aqi_values if v is not None]

        out_of_range = [
            v for v in present if v < _MIN_PLAUSIBLE_AQI or v > _MAX_PLAUSIBLE_AQI
        ]
        out_of_range_rate = len(out_of_range) / n if n else 0.0

        std = statistics.pstdev(present) if len(present) > 1 else 0.0
        mean = statistics.fmean(present) if present else 0.0
        flatlined = len(present) >= 6 and std < _FLATLINE_STD_THRESHOLD

        reasoning.append(
            f"{n} readings in window; {null_count} missing ({null_rate:.0%}), "
            f"stdev={std:.2f}, mean={mean:.1f}."
        )

        # ── Drift detection (CUSUM against long-run baseline) ──────────────
        drift_score, drift_direction = 0.0, "none"
        if baseline_readings:
            baseline_vals = [
                r["aqi"] for r in baseline_readings if r.get("aqi") is not None
            ]
            if len(baseline_vals) >= 10:
                baseline_mean = statistics.fmean(baseline_vals)
                baseline_std = statistics.pstdev(baseline_vals) or 1.0
                # Group recent readings into daily means for CUSUM input.
                by_day: dict[str, list[float]] = {}
                for r in readings:
                    if r.get("aqi") is None:
                        continue
                    day_key = (
                        r["timestamp"].date().isoformat()
                        if isinstance(r["timestamp"], datetime)
                        else str(r["timestamp"])[:10]
                    )
                    by_day.setdefault(day_key, []).append(r["aqi"])
                daily_means = [statistics.fmean(v) for v in by_day.values()]
                drift_score, drift_direction = _cusum_drift(
                    daily_means, baseline_mean, baseline_std
                )
                reasoning.append(
                    f"CUSUM drift vs {len(baseline_vals)}-reading baseline "
                    f"(μ={baseline_mean:.1f}, σ={baseline_std:.1f}): "
                    f"score={drift_score:.2f}, direction={drift_direction}."
                )

        # Alternative explanation: is this drift shared network-wide (real
        # pollution event) rather than station-specific (sensor fault)?
        alt_explanations: list[str] = []
        network_wide = False
        if network_daily_means and len(network_daily_means) >= 3 and drift_score > 0.3:
            net_mean = statistics.fmean(network_daily_means)
            net_std = statistics.pstdev(network_daily_means) or 1.0
            if net_std > 0 and abs(mean - net_mean) < 1.5 * net_std:
                network_wide = True
                alt_explanations.append(
                    "The shift tracks the wider monitoring network, so this looks more like a "
                    "genuine city-wide pollution event than a station-specific sensor fault."
                )
                drift_score *= 0.4  # de-weight station-specific fault hypothesis
                reasoning.append(
                    "Drift correlates with network-wide trend — down-weighting fault likelihood."
                )

        if flatlined:
            alt_explanations.append(
                "A true flatline can also occur during a genuinely stagnant-air, unusually stable "
                "pollution episode — check nearby stations before assuming hardware failure."
            )

        # ── Failure probability (logistic blend of independent signals) ────
        # Weights are hand-set and documented rather than learned, so every
        # contribution is traceable.
        z = (
            -3.2
            + 4.0 * null_rate
            + 3.0 * (1.0 if flatlined else 0.0)
            + 5.0 * out_of_range_rate
            + 1.5 * drift_score
        )
        failure_probability = round(_logistic(z), 3)

        feature_importance = {
            "null_rate": round(4.0 * null_rate, 2),
            "flatline": round(3.0 * (1.0 if flatlined else 0.0), 2),
            "out_of_range_rate": round(5.0 * out_of_range_rate, 2),
            "drift_score": round(1.5 * drift_score, 2),
        }
        contributing_factors = [k for k, v in feature_importance.items() if v > 0.1]

        # ── Remaining useful life ───────────────────────────────────────────
        # Extrapolate the CUSUM drift trend to the point it would cross a
        # "sensor considered unreliable" threshold. Only meaningful when
        # there's an active, station-specific (not network-wide) drift.
        rul_days: int | None = None
        if drift_score > 0.05 and not network_wide and len(readings) >= 2:
            span_days = max(
                1.0,
                (
                    (
                        readings[-1]["timestamp"] - readings[0]["timestamp"]
                    ).total_seconds()
                    / 86400
                    if isinstance(readings[-1]["timestamp"], datetime)
                    else 1.0
                ),
            )
            drift_rate_per_day = drift_score / span_days
            if drift_rate_per_day > 0:
                remaining_headroom = max(0.0, 1.0 - drift_score)
                rul_days = max(1, round(remaining_headroom / drift_rate_per_day))
                rul_days = min(
                    rul_days, 365
                )  # cap — beyond a year the estimate isn't meaningful
                reasoning.append(
                    f"Drift rate ≈{drift_rate_per_day:.4f}/day → est. {rul_days} days until the sensor "
                    "is likely to need recalibration."
                )

        # ── Maintenance priority ────────────────────────────────────────────
        priority_score = round(
            min(
                100.0,
                100.0 * failure_probability * 0.7
                + drift_score * 20
                + out_of_range_rate * 30,
            ),
            1,
        )
        if priority_score >= 70 or out_of_range_rate > 0.2:
            priority = "critical"
        elif priority_score >= 45:
            priority = "urgent"
        elif priority_score >= 20:
            priority = "soon"
        else:
            priority = "routine"

        # ── Confidence ───────────────────────────────────────────────────────
        # More samples and a non-flatlined signal → higher confidence in the
        # estimate itself (distinct from failure_probability, which is the
        # estimate).
        sample_confidence = min(1.0, n / 48)  # 48 readings ≈ full day at 30-min cadence
        confidence = round(
            max(0.3, sample_confidence * (0.5 if network_wide else 1.0)), 2
        )

        historical_comparison = None
        if prior_maintenance_score is not None:
            current_score = round(1.0 - failure_probability, 2)
            trend = (
                "improving"
                if current_score > prior_maintenance_score
                else (
                    "declining" if current_score < prior_maintenance_score else "stable"
                )
            )
            historical_comparison = {
                "previous_maintenance_score": prior_maintenance_score,
                "current_maintenance_score": current_score,
                "trend": trend,
            }
            reasoning.append(
                f"Maintenance score trend: {prior_maintenance_score:.2f} → {current_score:.2f} ({trend})."
            )

        return SensorHealthAssessment(
            station_id=station_id,
            assessed_at=now,
            drift_score=round(drift_score, 3),
            drift_direction=drift_direction,
            failure_probability=failure_probability,
            maintenance_priority=priority,
            maintenance_priority_score=priority_score,
            remaining_useful_life_days=rul_days,
            confidence=confidence,
            feature_importance=feature_importance,
            contributing_factors=contributing_factors,
            reasoning_trace=reasoning,
            alternative_explanations=alt_explanations
            or [
                "No strong alternative explanation found — station-specific fault is the leading hypothesis."
            ],
            historical_comparison=historical_comparison,
            sample_size=n,
            null_rate=round(null_rate, 3),
            flatlined=flatlined,
            out_of_range_rate=round(out_of_range_rate, 3),
        )
