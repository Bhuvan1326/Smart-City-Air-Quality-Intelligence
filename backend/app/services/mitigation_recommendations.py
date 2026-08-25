"""Pollution mitigation recommendation engine.

Detect -> Predict -> Recommend -> Simulate.

This module is the "Recommend" step: a deterministic rules engine over the
existing pollution-attribution percentages, current pollutant readings, and
wind speed. It does NOT estimate a quantified AQI reduction — that would
require actually running the dispersion model. Instead, each recommended
action carries the `simulation_scenario_key` that maps to a real scenario in
app/services/whatif_simulator.py, so the "Simulate" step can be triggered
with a real model rather than a guessed number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.health_risk import RiskLevel, assess_health_risk

# Attribution share above this threshold is considered a meaningful
# contributing factor worth acting on.
_CONTRIBUTION_THRESHOLD_PCT = 20.0
_LOW_WIND_THRESHOLD_MPS = 2.0


@dataclass
class RecommendedAction:
    action: str
    target_source: str  # vehicular / industrial / construction / biomass / dust
    rationale: str
    simulation_scenario_key: str | None  # maps to WhatIfSimulator.SCENARIO_PARAMS


@dataclass
class MitigationRecommendation:
    aqi: int | None
    primary_pollutant: str | None
    overall_risk: RiskLevel
    contributing_factors: list[str]
    recommended_actions: list[RecommendedAction] = field(default_factory=list)
    impact_disclaimer: str = (
        "No AQI reduction percentage is estimated here. Each action links to a "
        "real scenario in the What-If Simulator, which calculates an actual "
        "impact estimate using the dispersion model — run it there for a "
        "quantified number rather than trusting a guess."
    )


# source_key -> [(action label, simulation scenario key or None)]
_ACTIONS_BY_SOURCE: dict[str, list[tuple[str, str | None]]] = {
    "vehicular": [
        ("Traffic-flow optimization at nearby signals", None),
        ("Heavy-vehicle restriction during peak hours", "restrict_truck_traffic"),
        ("Increase public transport frequency to reduce private vehicle trips", None),
        ("Odd-even vehicle restriction", "odd_even_vehicles"),
    ],
    "construction": [
        ("Mandatory dust-suppression (water sprinklers) at active sites", "dust_suppression"),
        ("Stop-work order pending compliance check", "close_construction_site"),
    ],
    "industrial": [
        ("Emission compliance inspection", None),
        ("Emergency shutdown order for non-compliant units", "shutdown_industrial_unit"),
    ],
    "biomass": [
        ("Enforce open-burning prohibition", "ban_biomass_burning"),
        ("Deploy waste-collection outreach to reduce burning incentive", None),
    ],
    "dust": [
        ("Road dust control — mechanical sweeping / water spraying", None),
    ],
    "domestic": [
        ("Community outreach on cleaner cooking-fuel alternatives", None),
    ],
}

_SOURCE_LABELS = {
    "vehicular": "Elevated traffic emissions",
    "construction": "Construction dust and activity",
    "industrial": "Industrial emissions",
    "biomass": "Biomass / open burning",
    "dust": "Road/wind-blown dust",
    "domestic": "Domestic fuel burning",
}


def generate_recommendation(
    *,
    aqi: int | None,
    pm25: float | None = None,
    pm10: float | None = None,
    no2: float | None = None,
    co: float | None = None,
    o3: float | None = None,
    so2: float | None = None,
    vehicular_pct: float | None = None,
    industrial_pct: float | None = None,
    construction_pct: float | None = None,
    biomass_pct: float | None = None,
    dust_pct: float | None = None,
    domestic_pct: float | None = None,
    wind_speed_mps: float | None = None,
) -> MitigationRecommendation:
    """Build a mitigation recommendation from current readings + attribution.

    Never claims a specific AQI reduction — only reuses the deterministic
    health-risk engine (for primary pollutant / risk level) and a rule table
    mapping attribution shares to actions, each optionally linked to a real
    What-If Simulator scenario for actual quantified impact.
    """
    risk = assess_health_risk(aqi=aqi, pm25=pm25, pm10=pm10, no2=no2, co=co, o3=o3, so2=so2)
    primary_pollutant = risk.pollutant_risks[0].label if risk.pollutant_risks else None

    contributing_factors: list[str] = []
    triggered_sources: list[tuple[str, float]] = []

    attribution = {
        "vehicular": vehicular_pct,
        "construction": construction_pct,
        "industrial": industrial_pct,
        "biomass": biomass_pct,
        "dust": dust_pct,
        "domestic": domestic_pct,
    }
    for source, pct in attribution.items():
        if pct is not None and pct >= _CONTRIBUTION_THRESHOLD_PCT:
            contributing_factors.append(f"{_SOURCE_LABELS[source]} ({pct:.0f}% of attributed pollution)")
            triggered_sources.append((source, pct))

    if wind_speed_mps is not None and wind_speed_mps < _LOW_WIND_THRESHOLD_MPS:
        contributing_factors.append(
            f"Low wind speed ({wind_speed_mps:.1f} m/s) limiting pollutant dispersion"
        )

    if risk.overall_risk in (RiskLevel.HIGH, RiskLevel.VERY_HIGH) and primary_pollutant:
        contributing_factors.append(f"High {primary_pollutant} concentration")

    # Rank contributing sources by attribution share, most significant first,
    # and pull 1-2 actions per source so the list stays actionable rather
    # than exhaustive.
    triggered_sources.sort(key=lambda pair: pair[1], reverse=True)
    actions: list[RecommendedAction] = []
    seen_action_labels: set[str] = set()
    for source, pct in triggered_sources:
        for label, scenario_key in _ACTIONS_BY_SOURCE.get(source, [])[:2]:
            if label in seen_action_labels:
                continue
            seen_action_labels.add(label)
            actions.append(
                RecommendedAction(
                    action=label,
                    target_source=source,
                    rationale=f"{_SOURCE_LABELS[source]} contributes {pct:.0f}% of attributed pollution here.",
                    simulation_scenario_key=scenario_key,
                )
            )

    if not actions and risk.overall_risk in (RiskLevel.HIGH, RiskLevel.VERY_HIGH):
        # High risk but no dominant attributed source (e.g. regional/weather
        # driven) — still give something actionable rather than an empty list.
        actions.append(
            RecommendedAction(
                action="Issue public health advisory for sensitive groups",
                target_source="unknown",
                rationale="AQI is elevated without a single dominant attributed source in the "
                "available data — precautionary public guidance is appropriate while "
                "the cause is investigated.",
                simulation_scenario_key=None,
            )
        )

    return MitigationRecommendation(
        aqi=aqi,
        primary_pollutant=primary_pollutant,
        overall_risk=risk.overall_risk,
        contributing_factors=contributing_factors,
        recommended_actions=actions,
    )
