from app.services.drone_planner import DronePlanner


def test_basic_coverage_generates_waypoints():
    planner = DronePlanner()
    result = planner.plan_coverage(
        "hotspot-1", bbox=(18.50, 73.80, 18.51, 73.81), swath_meters=100
    )
    assert result.total_waypoints > 0
    assert len(result.sorties) >= 1
    assert result.coverage_area_sq_meters > 0


def test_every_sortie_returns_to_launch_point():
    planner = DronePlanner()
    result = planner.plan_coverage(
        "hotspot-2", bbox=(18.50, 73.80, 18.52, 73.82), swath_meters=150
    )
    for sortie in result.sorties:
        last_wp = sortie.waypoints[-1]
        assert last_wp.is_return_to_base is True
        assert abs(last_wp.latitude - result.launch_point[0]) < 1e-6
        assert abs(last_wp.longitude - result.launch_point[1]) < 1e-6


def test_battery_limit_forces_multiple_sorties_for_large_area():
    planner = DronePlanner()
    # A modest area with a small (but individually reachable) battery
    # budget should require multiple sorties rather than one giant loop.
    result = planner.plan_coverage(
        "hotspot-3",
        bbox=(18.500, 73.800, 18.506, 73.806),
        swath_meters=150,
        max_flight_minutes=3,
        cruise_speed_mps=8.0,
    )
    assert len(result.sorties) > 1
    for sortie in result.sorties:
        assert (
            sortie.estimated_duration_minutes <= 3.5
        )  # small tolerance for the final return leg


def test_unreachable_waypoints_are_excluded_not_force_included():
    planner = DronePlanner()
    # Area far larger than what a 2-minute battery budget could ever reach,
    # even on a dedicated single-point sortie from the launch point.
    result = planner.plan_coverage(
        "hotspot-3b",
        bbox=(18.40, 73.70, 18.60, 73.95),
        swath_meters=200,
        max_flight_minutes=2,
        cruise_speed_mps=8.0,
    )
    for sortie in result.sorties:
        assert sortie.estimated_duration_minutes <= 2.5
    assert any("battery budget allows" in r for r in result.reasoning)


def test_no_fly_zone_excludes_waypoints():
    planner = DronePlanner()
    center_lat, center_lon = 18.505, 73.805
    no_fly = [(center_lat, center_lon, 300.0)]  # 300m radius no-fly zone at bbox center

    without_nfz = planner.plan_coverage(
        "hotspot-4a", bbox=(18.50, 73.80, 18.51, 73.81), swath_meters=80
    )
    with_nfz = planner.plan_coverage(
        "hotspot-4b",
        bbox=(18.50, 73.80, 18.51, 73.81),
        swath_meters=80,
        no_fly_zones=no_fly,
    )

    assert with_nfz.excluded_no_fly_zones > 0
    assert with_nfz.total_waypoints <= without_nfz.total_waypoints


def test_geojson_export_is_valid_feature_collection():
    planner = DronePlanner()
    result = planner.plan_coverage(
        "hotspot-5", bbox=(18.50, 73.80, 18.51, 73.81), swath_meters=100
    )
    geojson = result.to_geojson()

    assert geojson["type"] == "FeatureCollection"
    assert all(f["type"] == "Feature" for f in geojson["features"])
    linestrings = [
        f for f in geojson["features"] if f["geometry"]["type"] == "LineString"
    ]
    points = [f for f in geojson["features"] if f["geometry"]["type"] == "Point"]
    assert len(linestrings) == len(result.sorties)
    assert len(points) == result.total_waypoints


def test_entirely_blocked_area_returns_empty_plan():
    planner = DronePlanner()
    # No-fly zone radius large enough to cover the whole bbox.
    no_fly = [(18.505, 73.805, 5000.0)]
    result = planner.plan_coverage(
        "hotspot-6",
        bbox=(18.50, 73.80, 18.51, 73.81),
        swath_meters=100,
        no_fly_zones=no_fly,
    )
    assert result.sorties == []
    assert any("no-fly" in r.lower() for r in result.reasoning)


def test_custom_launch_point_is_used_as_sortie_origin():
    planner = DronePlanner()
    custom_launch = (18.499, 73.799)
    result = planner.plan_coverage(
        "hotspot-7",
        bbox=(18.50, 73.80, 18.51, 73.81),
        swath_meters=100,
        launch_point=custom_launch,
    )
    assert result.launch_point == custom_launch
    assert result.sorties[0].waypoints[0].latitude == custom_launch[0]
    assert result.sorties[0].waypoints[0].longitude == custom_launch[1]
