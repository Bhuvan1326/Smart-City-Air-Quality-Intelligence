import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent


def _assert_all_distinct(label: str, values: list):
    assert len(values) == len(set(values)), (
        f"{label}: duplicate coordinate values found ({values}) -- "
        "this is the W01/W07 copy-paste bug class."
    )


# ─── Importable module-level dicts ─────────────────────────────────────────


def test_langgraph_agents_ward_coords_are_distinct():
    from app.agents.langgraph_agents import _WARD_COORDS

    assert len(_WARD_COORDS) == 8
    _assert_all_distinct("_WARD_COORDS", list(_WARD_COORDS.values()))


def test_satellite_ward_bboxes_are_distinct():
    from app.workers.tasks.satellite import WARD_BBOXES

    assert len(WARD_BBOXES) == 8
    _assert_all_distinct("WARD_BBOXES", list(WARD_BBOXES.values()))


def test_aqi_ingestion_pune_station_coords_are_distinct():
    from app.workers.tasks.aqi_ingestion import PUNE_STATIONS

    coords = [(s["lat"], s["lon"]) for s in PUNE_STATIONS]
    assert len(coords) == 8
    _assert_all_distinct("PUNE_STATIONS lat/lon", coords)


def test_gis_operations_ward_boundary_centers_are_distinct():
    from app.gis.operations import PUNE_WARD_BOUNDARIES

    centers = [tuple(w["center"]) for w in PUNE_WARD_BOUNDARIES.values()]
    assert len(centers) == 8
    _assert_all_distinct("PUNE_WARD_BOUNDARIES centers", centers)


def _local_dict_literals(filepath: Path, var_name: str) -> list[dict]:
    """Find every top-level assignment `var_name = {...}` anywhere in the
    file (including inside functions) and return each as an evaluated
    literal dict."""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == var_name:
                found.append(ast.literal_eval(node.value))
    return found


def test_attribution_local_ward_coords_are_distinct():
    filepath = APP_DIR / "workers" / "tasks" / "attribution.py"
    dicts = _local_dict_literals(filepath, "WARD_COORDS")
    assert dicts, "expected to find a local WARD_COORDS assignment"
    for d in dicts:
        assert len(d) == 8
        _assert_all_distinct("attribution.py WARD_COORDS", list(d.values()))


def test_forecast_local_ward_coords_are_distinct():
    filepath = APP_DIR / "workers" / "tasks" / "forecast.py"
    dicts = _local_dict_literals(filepath, "WARD_COORDS")
    assert dicts, "expected to find a local WARD_COORDS assignment"
    for d in dicts:
        assert len(d) == 8
        _assert_all_distinct("forecast.py WARD_COORDS", list(d.values()))


def test_seeder_local_ward_coords_are_distinct():
    filepath = APP_DIR / "core" / "seeder.py"
    dicts = _local_dict_literals(filepath, "WARD_COORDS")
    assert len(dicts) >= 1, "expected at least one local WARD_COORDS assignment"
    for d in dicts:
        assert len(d) == 8
        _assert_all_distinct("seeder.py WARD_COORDS", list(d.values()))


# ─── Cross-file consistency ─────────────────────────────────────────────────
# Not strictly required for correctness (each file only needs internal
# consistency to avoid the collapse bug), but any ward that appears in two
# of these sources should agree, since they're meant to represent the same
# real-world location.


def test_w07_centroid_agrees_across_all_sources():
    from app.agents.langgraph_agents import _WARD_COORDS
    from app.gis.operations import PUNE_WARD_BOUNDARIES
    from app.workers.tasks.aqi_ingestion import PUNE_STATIONS

    seeder_dicts = _local_dict_literals(APP_DIR / "core" / "seeder.py", "WARD_COORDS")
    attribution_dicts = _local_dict_literals(
        APP_DIR / "workers" / "tasks" / "attribution.py", "WARD_COORDS"
    )
    forecast_dicts = _local_dict_literals(
        APP_DIR / "workers" / "tasks" / "forecast.py", "WARD_COORDS"
    )

    station = next(s for s in PUNE_STATIONS if s["ward"] == "W07")

    w07_sources = {
        "langgraph_agents": _WARD_COORDS["W07"],
        "gis_operations": tuple(
            reversed(PUNE_WARD_BOUNDARIES["W07"]["center"])
        ),  # [lon,lat] -> (lat,lon)
        "aqi_ingestion": (station["lat"], station["lon"]),
        **{f"seeder[{i}]": d["W07"] for i, d in enumerate(seeder_dicts)},
        **{f"attribution[{i}]": d["W07"] for i, d in enumerate(attribution_dicts)},
        **{f"forecast[{i}]": d["W07"] for i, d in enumerate(forecast_dicts)},
    }

    distinct_values = set(w07_sources.values())
    assert (
        len(distinct_values) == 1
    ), f"W07 centroid disagrees across sources: {w07_sources}"
