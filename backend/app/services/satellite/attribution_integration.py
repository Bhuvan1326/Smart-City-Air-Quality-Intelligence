"""
Builds the `satellite_evidence` payload stored on PollutionAttribution
records (see app/models/analytics.py) and consumed by the Pollution
Attribution Agent's reasoning. Kept separate from the two API clients so the
evidence-weighting logic — the part with real business meaning — is testable
without any network access.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.services.satellite.modis_firms import NasaFirmsClient, ThermalHotspot
from app.services.satellite.sentinel_hub import SatelliteBandSummary


@dataclass
class SatelliteAttributionEvidence:
    ward_id: str
    sources: list[str] = field(default_factory=list)
    vegetation_index: float | None = None
    construction_dust_index: float | None = None
    vegetation_loss_detected: bool = False
    construction_activity_detected: bool = False
    thermal_hotspot_count: int = 0
    biomass_burning_hotspots: int = 0
    industrial_thermal_hotspots: int = 0
    max_fire_radiative_power_mw: float | None = None
    category_scores: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_satellite_evidence(
    ward_id: str,
    band_summary: SatelliteBandSummary | None,
    hotspots: list[ThermalHotspot],
) -> SatelliteAttributionEvidence:
    """
    Turn raw satellite observations into a category-scored evidence object
    the Pollution Attribution Agent can add directly into its weighted
    source breakdown (see PollutionAttributionAgent in
    app/agents/langgraph_agents.py, which already has a `satellite_evidence`
    input slot it previously received empty/placeholder data for).
    """
    evidence = SatelliteAttributionEvidence(ward_id=ward_id)
    sources_available = 0
    signal_strength = 0.0

    if band_summary is not None:
        sources_available += 1
        evidence.sources.append("sentinel-2")
        evidence.vegetation_index = band_summary.mean_ndvi
        evidence.construction_dust_index = band_summary.mean_ndbi
        evidence.vegetation_loss_detected = band_summary.vegetation_loss_flag
        evidence.construction_activity_detected = band_summary.construction_dust_flag

        if band_summary.construction_dust_flag:
            evidence.category_scores["construction_dust"] = min(
                1.0, (band_summary.mean_ndbi or 0) * 4
            )
            signal_strength += evidence.category_scores["construction_dust"]
            evidence.notes.append(
                f"NDBI={band_summary.mean_ndbi:.2f} indicates elevated bare/impervious "
                "surface fraction, consistent with active construction."
            )
        if band_summary.vegetation_loss_flag:
            evidence.notes.append(
                f"NDVI={band_summary.mean_ndvi:.2f} is low, indicating sparse vegetation "
                "cover — supports (but doesn't alone prove) land clearing."
            )

    if hotspots:
        sources_available += 1
        evidence.sources.append("nasa-firms")
        evidence.thermal_hotspot_count = len(hotspots)
        classifications = [NasaFirmsClient.classify_hotspot(h) for h in hotspots]
        evidence.biomass_burning_hotspots = classifications.count(
            "likely_biomass_burning"
        )
        evidence.industrial_thermal_hotspots = classifications.count(
            "likely_industrial_thermal_source"
        )
        frp_values = [h.frp_megawatts for h in hotspots if h.frp_megawatts is not None]
        evidence.max_fire_radiative_power_mw = max(frp_values) if frp_values else None

        if evidence.biomass_burning_hotspots:
            score = min(1.0, evidence.biomass_burning_hotspots / 5)
            evidence.category_scores["biomass_burning"] = score
            signal_strength += score
            evidence.notes.append(
                f"{evidence.biomass_burning_hotspots} thermal detection(s) classified as "
                "likely biomass burning within the ward's monitoring radius."
            )
        if evidence.industrial_thermal_hotspots:
            score = min(1.0, evidence.industrial_thermal_hotspots / 5)
            evidence.category_scores["industrial_hotspot"] = score
            signal_strength += score
            evidence.notes.append(
                f"{evidence.industrial_thermal_hotspots} thermal detection(s) classified as "
                "likely industrial thermal sources (continuous, moderate FRP)."
            )

    # Confidence scales with how many independent satellite sources agree
    # and how strong the combined signal is — mirrors the confidence
    # semantics used by the LangGraph agents elsewhere in this codebase.
    if sources_available == 0:
        evidence.confidence = 0.0
        evidence.notes.append("No satellite data available for this ward/window.")
    else:
        source_factor = sources_available / 2  # 2 = both Sentinel-2 and FIRMS
        evidence.confidence = round(
            min(1.0, 0.3 + 0.35 * source_factor + 0.35 * min(1.0, signal_strength)), 2
        )

    return evidence
