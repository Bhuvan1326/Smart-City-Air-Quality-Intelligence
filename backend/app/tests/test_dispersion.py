from app.services.dispersion import (DispersionModel, StabilityClass,
                                     classify_stability,
                                     gaussian_plume_concentration)


def test_low_wind_daytime_strong_sun_is_unstable():
    assert classify_stability(wind_speed_mps=1.5, hour=12) in (
        StabilityClass.A,
        StabilityClass.B,
    )


def test_high_wind_is_neutral_regardless_of_time():
    assert classify_stability(wind_speed_mps=7.0, hour=12) == StabilityClass.D
    assert classify_stability(wind_speed_mps=7.0, hour=2) == StabilityClass.D


def test_calm_clear_night_is_very_stable():
    assert classify_stability(wind_speed_mps=1.5, hour=2) == StabilityClass.F


def test_heavy_cloud_cover_treated_as_weak_insolation():
    # Weak insolation daytime should not classify as the most unstable class A.
    result = classify_stability(wind_speed_mps=1.5, hour=12, cloud_cover_fraction=0.9)
    assert result != StabilityClass.A


def test_plume_concentration_decreases_with_downwind_distance():
    near = gaussian_plume_concentration(
        100, 0, 3.0, StabilityClass.D, source_strength=100
    )
    far = gaussian_plume_concentration(
        2000, 0, 3.0, StabilityClass.D, source_strength=100
    )
    assert far < near


def test_plume_concentration_decreases_off_centerline():
    centerline = gaussian_plume_concentration(
        500, 0, 3.0, StabilityClass.D, source_strength=100
    )
    offset = gaussian_plume_concentration(
        500, 300, 3.0, StabilityClass.D, source_strength=100
    )
    assert offset < centerline


def test_pm10_settles_faster_than_pm25_at_long_range():
    pm25 = gaussian_plume_concentration(
        3000,
        0,
        3.0,
        StabilityClass.D,
        source_strength=100,
        settling_velocity_mps=0.0004,
    )
    pm10 = gaussian_plume_concentration(
        3000, 0, 3.0, StabilityClass.D, source_strength=100, settling_velocity_mps=0.01
    )
    assert pm10 < pm25


def test_unstable_class_produces_wider_plume_than_stable_at_same_distance():
    from app.services.dispersion import plume_spread

    sigma_y_unstable, _ = plume_spread(1000, StabilityClass.A)
    sigma_y_stable, _ = plume_spread(1000, StabilityClass.F)
    assert sigma_y_unstable > sigma_y_stable


# ─── Ward-to-ward transport ────────────────────────────────────────────────

WARD_COORDS = {
    "W01": (18.5074, 73.8077),
    "W02": (18.5308, 73.8475),  # roughly NE of W01
    "W03": (18.5089, 73.9259),  # far east
}


def test_downwind_ward_receives_contribution_from_upwind_source():
    model = DispersionModel()
    # Synthetic coordinates: source ward placed ~1km due west of the target,
    # nearly on the wind axis (small crosswind offset) — the case a real
    # Gaussian plume actually connects. (Two real Pune wards several km
    # apart and well off-axis correctly show ~zero contribution — a narrow
    # plume doesn't reach that far off-axis; see the reversed-direction test
    # below for that boundary behaviour.)
    target_coords = (18.5300, 73.8500)
    source_coords = (18.5300, 73.8400)  # same latitude, ~1km west
    ward_aqi = {"SRC": 150.0, "TGT": 80.0}
    result = model.compute_ward_adjustment(
        target_ward_id="TGT",
        target_coords=target_coords,
        ward_aqi=ward_aqi,
        ward_coords={"SRC": source_coords, "TGT": target_coords},
        wind_speed_mps=3.0,
        wind_direction_deg=270,  # wind FROM the west, blowing toward the target
        hour=14,
    )
    assert result.pm25_transport_delta > 0
    assert any(c.source_ward_id == "SRC" for c in result.contributing_wards)


def test_downwind_direction_reversed_gives_no_contribution():
    model = DispersionModel()
    ward_aqi = {"W01": 150.0, "W02": 80.0}
    # Wind blowing FROM the east — W01 (west of W02) is now downwind, not upwind.
    result = model.compute_ward_adjustment(
        target_ward_id="W02",
        target_coords=WARD_COORDS["W02"],
        ward_aqi=ward_aqi,
        ward_coords={"W01": WARD_COORDS["W01"], "W02": WARD_COORDS["W02"]},
        wind_speed_mps=3.0,
        wind_direction_deg=90,
        hour=14,
    )
    assert result.pm25_transport_delta == 0
    assert result.contributing_wards == []


def test_pm10_transport_delta_never_exceeds_pm25_for_same_scenario():
    model = DispersionModel()
    ward_aqi = {"W01": 150.0, "W02": 80.0, "W03": 60.0}
    result = model.compute_ward_adjustment(
        target_ward_id="W03",
        target_coords=WARD_COORDS["W03"],
        ward_aqi=ward_aqi,
        ward_coords=WARD_COORDS,
        wind_speed_mps=2.5,
        wind_direction_deg=280,
        hour=10,
    )
    assert result.pm10_transport_delta <= result.pm25_transport_delta


def test_confidence_penalty_higher_for_unstable_or_calm_conditions():
    model = DispersionModel()
    ward_aqi = {"W01": 100.0, "W02": 80.0}
    calm_unstable = model.compute_ward_adjustment(
        "W02",
        WARD_COORDS["W02"],
        ward_aqi,
        {"W01": WARD_COORDS["W01"], "W02": WARD_COORDS["W02"]},
        wind_speed_mps=1.0,
        wind_direction_deg=270,
        hour=13,
    )
    windy_neutral = model.compute_ward_adjustment(
        "W02",
        WARD_COORDS["W02"],
        ward_aqi,
        {"W01": WARD_COORDS["W01"], "W02": WARD_COORDS["W02"]},
        wind_speed_mps=6.0,
        wind_direction_deg=270,
        hour=13,
    )
    assert calm_unstable.confidence_penalty > windy_neutral.confidence_penalty


def test_no_upwind_wards_still_returns_valid_result():
    result = DispersionModel().compute_ward_adjustment(
        "W01",
        WARD_COORDS["W01"],
        {"W01": 100.0},
        {"W01": WARD_COORDS["W01"]},
        wind_speed_mps=3.0,
        wind_direction_deg=200,
        hour=12,
    )
    assert result.pm25_transport_delta == 0
    assert "zero" in result.reasoning[-1].lower()
