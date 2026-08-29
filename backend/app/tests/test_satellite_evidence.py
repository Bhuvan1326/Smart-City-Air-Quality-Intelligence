from datetime import date

from app.services.satellite.attribution_integration import build_satellite_evidence
from app.services.satellite.modis_firms import ThermalHotspot
from app.services.satellite.sentinel_hub import SatelliteBandSummary


def _band_summary(ndvi, ndbi):
    return SatelliteBandSummary(
        ward_id="ward-1",
        observed_date=date(2026, 6, 1),
        mean_ndvi=ndvi,
        mean_ndbi=ndbi,
        mean_swir_reflectance=0.2,
        cloud_free_fraction=0.9,
        vegetation_loss_flag=(ndvi is not None and ndvi < 0.2),
        construction_dust_flag=(ndbi is not None and ndbi > 0.1),
    )


def test_no_data_gives_zero_confidence():
    evidence = build_satellite_evidence("ward-1", None, [])
    assert evidence.confidence == 0.0
    assert evidence.sources == []


def test_construction_signal_detected_from_ndbi():
    band = _band_summary(ndvi=0.4, ndbi=0.25)
    evidence = build_satellite_evidence("ward-1", band, [])
    assert evidence.construction_activity_detected is True
    assert "construction_dust" in evidence.category_scores
    assert evidence.confidence > 0.0


def test_vegetation_loss_flagged_but_no_construction():
    band = _band_summary(ndvi=0.1, ndbi=0.05)
    evidence = build_satellite_evidence("ward-1", band, [])
    assert evidence.vegetation_loss_detected is True
    assert evidence.construction_activity_detected is False
    assert any("NDVI" in note for note in evidence.notes)


def test_biomass_burning_hotspots_classified():
    hotspots = [
        ThermalHotspot(18.5, 73.8, 330.0, "nominal", 80.0, "2026-06-01", "D"),
        ThermalHotspot(18.6, 73.9, 335.0, "high", 90.0, "2026-06-01", "D"),
    ]
    evidence = build_satellite_evidence("ward-1", None, hotspots)
    assert evidence.biomass_burning_hotspots == 2
    assert "biomass_burning" in evidence.category_scores


def test_industrial_hotspots_classified_separately_from_biomass():
    hotspots = [
        ThermalHotspot(18.5, 73.8, 320.0, "nominal", 20.0, "2026-06-01", "N"),
    ]
    evidence = build_satellite_evidence("ward-1", None, hotspots)
    assert evidence.industrial_thermal_hotspots == 1
    assert evidence.biomass_burning_hotspots == 0


def test_confidence_increases_with_more_sources():
    band = _band_summary(ndvi=0.4, ndbi=0.2)
    hotspots = [ThermalHotspot(18.5, 73.8, 320.0, "nominal", 60.0, "2026-06-01", "D")]

    only_band = build_satellite_evidence("ward-1", band, [])
    both_sources = build_satellite_evidence("ward-1", band, hotspots)

    assert both_sources.confidence >= only_band.confidence
    assert len(both_sources.sources) == 2
