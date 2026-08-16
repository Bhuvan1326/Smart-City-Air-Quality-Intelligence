from datetime import datetime, timedelta

from app.ml.sensor_maintenance import SensorMaintenancePredictor


def _reading(hours_ago: int, aqi: float | None, base: datetime) -> dict:
    return {"timestamp": base - timedelta(hours=hours_ago), "aqi": aqi}


def test_no_readings_flags_urgent_with_low_confidence():
    predictor = SensorMaintenancePredictor()
    result = predictor.assess("station-1", [])
    assert result.sample_size == 0
    assert result.maintenance_priority == "urgent"
    assert result.confidence < 0.5


def test_healthy_stable_sensor_gets_routine_priority():
    base = datetime(2026, 6, 1, 12, 0, 0)
    # Realistic noisy-but-stable readings around AQI 80: enough natural
    # variance to not look flatlined, centered on the same mean as the
    # baseline so no drift is detected either.
    readings = [_reading(i, 80 + ((i * 7) % 13) - 6, base) for i in range(48)]
    baseline = [_reading(i, 80 + ((i * 5) % 13) - 6, base) for i in range(200, 260)]

    predictor = SensorMaintenancePredictor()
    result = predictor.assess("station-2", readings, baseline_readings=baseline)

    assert result.maintenance_priority in ("routine", "soon")
    assert result.failure_probability < 0.5
    assert result.confidence > 0.5
    assert "null_rate" in result.feature_importance


def test_high_null_rate_increases_failure_probability():
    base = datetime(2026, 6, 1, 12, 0, 0)
    readings = [_reading(i, None if i % 2 == 0 else 80.0, base) for i in range(48)]

    predictor = SensorMaintenancePredictor()
    result = predictor.assess("station-3", readings)

    assert result.null_rate > 0.4
    assert result.failure_probability > 0.3
    assert "null_rate" in result.contributing_factors


def test_flatlined_sensor_detected():
    base = datetime(2026, 6, 1, 12, 0, 0)
    readings = [_reading(i, 100.0, base) for i in range(24)]  # zero variance

    predictor = SensorMaintenancePredictor()
    result = predictor.assess("station-4", readings)

    assert result.flatlined is True
    assert any("flatline" in exp.lower() for exp in result.alternative_explanations)


def test_out_of_range_readings_drive_critical_priority():
    base = datetime(2026, 6, 1, 12, 0, 0)
    readings = [_reading(i, -50.0 if i < 15 else 90.0, base) for i in range(48)]

    predictor = SensorMaintenancePredictor()
    result = predictor.assess("station-5", readings)

    assert result.out_of_range_rate > 0.2
    assert result.maintenance_priority == "critical"


def test_drift_correlated_with_network_is_deprioritized():
    base = datetime(2026, 6, 1, 12, 0, 0)
    # Station readings drift upward sharply over several days
    readings = []
    for day in range(6):
        for h in range(8):
            idx = day * 8 + h
            readings.append(_reading(idx, 100 + day * 15, base))
    baseline = [_reading(i, 100.0, base) for i in range(200, 260)]
    # Network also shows the same upward trend => real pollution event
    network_means = [100 + day * 15 for day in range(6)]

    predictor = SensorMaintenancePredictor()
    result_isolated = predictor.assess(
        "station-6a", readings, baseline_readings=baseline
    )
    result_network_wide = predictor.assess(
        "station-6b",
        readings,
        baseline_readings=baseline,
        network_daily_means=network_means,
    )

    assert result_network_wide.drift_score <= result_isolated.drift_score
    assert any(
        "network" in e.lower() for e in result_network_wide.alternative_explanations
    )


def test_historical_comparison_reports_trend():
    base = datetime(2026, 6, 1, 12, 0, 0)
    readings = [_reading(i, 80.0, base) for i in range(48)]

    predictor = SensorMaintenancePredictor()
    result = predictor.assess("station-7", readings, prior_maintenance_score=0.5)

    assert result.historical_comparison is not None
    assert result.historical_comparison["previous_maintenance_score"] == 0.5
    assert result.historical_comparison["trend"] in ("improving", "declining", "stable")


def test_every_result_has_reasoning_and_confidence_bounds():
    base = datetime(2026, 6, 1, 12, 0, 0)
    readings = [_reading(i, 90.0 + i, base) for i in range(20)]

    predictor = SensorMaintenancePredictor()
    result = predictor.assess("station-8", readings)

    assert len(result.reasoning_trace) > 0
    assert 0.0 <= result.confidence <= 1.0
    assert 0.0 <= result.failure_probability <= 1.0
