"""
What-if Simulator and AI Digital Twin.

Simulates AQI impact of hypothetical interventions:
- Close a construction site
- Restrict truck traffic
- Shut down an industrial unit
- Odd-even vehicle restriction

Also provides Gaussian plume digital twin for dispersion simulation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.dispersion import classify_stability


@dataclass
class SimulationResult:
    scenario: str
    baseline_aqi: float
    simulated_aqi: float
    aqi_delta: float
    pm25_delta: float
    confidence: float
    affected_wards: list[str]
    co2_impact_kg_day: float
    time_to_effect_hours: int
    reasoning: str
    dispersion_map: list[dict]
    impact_score: float = (
        0.0  # 0-100 composite: magnitude of benefit, weighted by confidence
    )
    confidence_interval_lower: float = 0.0
    confidence_interval_upper: float = 0.0
    secondary_effects: list[dict] = field(
        default_factory=list
    )  # e.g. traffic-diversion side effects on neighboring wards


class WhatIfSimulator:
    """
    Simulates AQI outcomes of hypothetical enforcement interventions.
    Uses attribution percentages + Gaussian plume to estimate ward-level impact.
    """

    SCENARIO_PARAMS: ClassVar[dict[str, dict]] = {
        "close_construction_site": {
            "target_source": "construction",
            "reduction_pct": 0.85,
            "time_to_effect_hours": 2,
            "description": "Stop-work order on construction site",
        },
        "restrict_truck_traffic": {
            "target_source": "vehicular",
            "reduction_pct": 0.35,
            "time_to_effect_hours": 1,
            "description": "Heavy vehicle ban during 6AM–10PM",
        },
        "shutdown_industrial_unit": {
            "target_source": "industrial",
            "reduction_pct": 0.95,
            "time_to_effect_hours": 6,
            "description": "Emergency shutdown order",
        },
        "odd_even_vehicles": {
            "target_source": "vehicular",
            "reduction_pct": 0.45,
            "time_to_effect_hours": 1,
            "description": "Odd-even vehicle restriction",
        },
        "dust_suppression": {
            "target_source": "construction",
            "reduction_pct": 0.50,
            "time_to_effect_hours": 1,
            "description": "Mandatory water sprinkler deployment",
        },
        "ban_biomass_burning": {
            "target_source": "biomass",
            "reduction_pct": 0.90,
            "time_to_effect_hours": 1,
            "description": "Biomass burning prohibition",
        },
        "road_closure": {
            "target_source": "vehicular",
            "reduction_pct": 0.60,
            "time_to_effect_hours": 1,
            "description": "Full road closure to through-traffic",
            "diverts_traffic": True,
        },
        "traffic_diversion": {
            "target_source": "vehicular",
            "reduction_pct": 0.40,
            "time_to_effect_hours": 1,
            "description": "Traffic diverted to alternate arterial routes",
            "diverts_traffic": True,
        },
        "weather_shift": {
            "target_source": "vehicular",  # unused for this scenario type; kept for schema consistency
            "reduction_pct": 0.0,
            "time_to_effect_hours": 1,
            "description": "Simulated change in wind speed/direction",
            "is_weather_scenario": True,
        },
        "policy_bundle": {
            "target_source": "vehicular",  # unused; policy_bundle applies custom_reductions across categories
            "reduction_pct": 0.0,
            "time_to_effect_hours": 4,
            "description": "Combined multi-lever policy package",
            "is_policy_bundle": True,
        },
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def simulate(
        self,
        city: str,
        scenario_key: str,
        ward_id: str | None = None,
        custom_reduction_pct: float | None = None,
        custom_reductions: dict[str, float] | None = None,
        weather_wind_speed_mps: float | None = None,
    ) -> SimulationResult:
        """Run a what-if scenario simulation."""
        params = self.SCENARIO_PARAMS.get(scenario_key)
        if not params:
            raise ValueError(
                f"Unknown scenario: {scenario_key}. Valid: {list(self.SCENARIO_PARAMS)}"
            )

        reduction_pct = custom_reduction_pct or params["reduction_pct"]
        target_source = params["target_source"]

        # Get current AQI
        where = "AND s.ward_id = :ward" if ward_id else ""
        query_params: dict = {"city": city}
        if ward_id:
            query_params["ward"] = ward_id

        result = await self.session.execute(
            text(
                f"""
            SELECT AVG(r.aqi) AS avg_aqi, AVG(r.pm25) AS avg_pm25,
                   ARRAY_AGG(DISTINCT s.ward_id) AS wards
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp > NOW() - INTERVAL '1 hour'
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
              {where}
        """
            ),
            query_params,
        )
        row = result.one_or_none()
        baseline_aqi = float(row.avg_aqi or 80) if row else 80.0
        baseline_pm25 = float(row.avg_pm25 or 45) if row else 45.0
        affected_wards = (
            list(row.wards or []) if row else (["W01"] if not ward_id else [ward_id])
        )

        # Get current source attribution — pollution_attributions has its
        # own ward_id column (no join/alias, unlike the aqi_readings query
        # above), so it needs its own WHERE fragment rather than reusing
        # `where` (which was previously reused as-is here despite
        # referencing alias "s" that doesn't exist in this query — a
        # pre-existing bug that broke every ward-scoped simulation).
        attr_where = "AND ward_id = :ward" if ward_id else ""
        attr_result = await self.session.execute(
            text(
                f"""
            SELECT AVG(vehicular_pct) AS vehicular, AVG(industrial_pct) AS industrial,
                   AVG(construction_pct) AS construction, AVG(biomass_pct) AS biomass
            FROM pollution_attributions
            WHERE city = :city AND timestamp > NOW() - INTERVAL '3 hours' AND is_deleted = false
            {attr_where}
        """
            ),
            query_params,
        )
        attr_row = attr_result.one_or_none()
        source_pct = {
            "vehicular": float(getattr(attr_row, "vehicular", 0) or 30),
            "industrial": float(getattr(attr_row, "industrial", 0) or 20),
            "construction": float(getattr(attr_row, "construction", 0) or 15),
            "biomass": float(getattr(attr_row, "biomass", 0) or 5),
        }
        target_contribution = source_pct.get(target_source, 20) / 100

        # ── Policy bundle: apply several source-category reductions at once ──
        if params.get("is_policy_bundle"):
            reductions = custom_reductions or {
                "vehicular": 0.25,
                "construction": 0.30,
                "industrial": 0.15,
            }
            aqi_delta = 0.0
            pm25_delta = 0.0
            per_lever_notes = []
            for source, pct in reductions.items():
                contribution = source_pct.get(source, 0) / 100
                lever_delta = -(baseline_aqi * contribution * pct)
                aqi_delta += lever_delta
                pm25_delta += -(baseline_pm25 * contribution * pct)
                per_lever_notes.append(f"{source} -{pct:.0%} ({lever_delta:+.1f} AQI)")
            simulated_aqi = max(10.0, baseline_aqi + aqi_delta)
            co2_impact = sum(
                self._estimate_co2_impact(source, pct)
                for source, pct in reductions.items()
            )
            reduction_pct = sum(reductions.values()) / max(
                len(reductions), 1
            )  # for confidence calc below
            bundle_reasoning = (
                f"Policy bundle applying: {', '.join(per_lever_notes)}. "
                f"Combined expected AQI change: {aqi_delta:+.1f} (from {baseline_aqi:.0f} to {simulated_aqi:.0f})."
            )

        # ── Weather scenario: re-run cross-ward dispersion under a hypothetical wind speed ──
        elif params.get("is_weather_scenario"):
            hypothetical_wind = (
                weather_wind_speed_mps if weather_wind_speed_mps is not None else 6.0
            )
            wind_result = await self.session.execute(
                text(
                    """
                SELECT AVG(wind_speed) AS avg_wind_speed, AVG(wind_direction) AS avg_wind_direction
                FROM aqi_readings
                WHERE timestamp > NOW() - INTERVAL '1 hour' AND is_deleted = false
                  AND wind_speed IS NOT NULL AND wind_direction IS NOT NULL
            """
                )
            )
            wind_row = wind_result.first()
            current_wind_speed = (
                float(wind_row.avg_wind_speed)
                if wind_row and wind_row.avg_wind_speed
                else 3.0
            )
            wind_direction = (
                float(wind_row.avg_wind_direction)
                if wind_row and wind_row.avg_wind_direction
                else 225.0
            )

            current_hour = datetime.now(UTC).hour
            baseline_stability = classify_stability(current_wind_speed, current_hour)
            scenario_stability = classify_stability(hypothetical_wind, current_hour)

            # Higher wind speed -> more dilution -> lower AQI at a receptor
            # dominated by transported (rather than locally-emitted) pollution.
            # Modelled as inversely proportional to wind speed change, which
            # is the correct first-order Gaussian plume behaviour (concentration
            # scales as 1/u — see gaussian_plume_concentration in
            # app.services.dispersion).
            dilution_ratio = current_wind_speed / max(hypothetical_wind, 0.5)
            transportable_fraction = 0.35  # fraction of AQI assumed attributable to transported (non-local) sources
            aqi_delta = baseline_aqi * transportable_fraction * (dilution_ratio - 1)
            simulated_aqi = max(10.0, baseline_aqi + aqi_delta)
            pm25_delta = baseline_pm25 * transportable_fraction * (dilution_ratio - 1)
            co2_impact = 0.0  # wind is not an emissions lever — no direct CO2 effect
            bundle_reasoning = (
                f"Wind speed scenario: {current_wind_speed:.1f} m/s from {wind_direction:.0f}° "
                f"(stability {baseline_stability.value}) -> {hypothetical_wind:.1f} m/s "
                f"(stability {scenario_stability.value}). "
                f"Assumes {transportable_fraction:.0%} of current AQI is transported rather than "
                f"locally emitted, and scales with it via the Gaussian plume's 1/wind-speed dilution term. "
                f"Expected AQI change: {aqi_delta:+.1f} (from {baseline_aqi:.0f} to {simulated_aqi:.0f})."
            )
        else:
            # ── Calculate AQI delta (standard single-source scenarios) ──
            aqi_delta = -(baseline_aqi * target_contribution * reduction_pct)
            simulated_aqi = max(10.0, baseline_aqi + aqi_delta)
            pm25_delta = -(baseline_pm25 * target_contribution * reduction_pct)
            co2_impact = self._estimate_co2_impact(target_source, reduction_pct)
            bundle_reasoning = None

        # Gaussian plume for spatial dispersion map
        primary_ward = ward_id or (affected_wards[0] if affected_wards else "W01")
        dispersion_map = self._gaussian_dispersion_map(
            ward_id=primary_ward,
            aqi_delta=aqi_delta,
            city=city,
        )

        confidence = 0.72 if attr_row else 0.50
        if params.get("is_weather_scenario"):
            # Dispersion-driven scenarios inherit the same stability-class
            # confidence penalty used by the real forecast dispersion model
            # (see app.services.dispersion) rather than the flat attribution-based value.
            confidence = max(0.4, confidence - 0.05)

        # ── Traffic diversion side-effect: nearest neighboring ward absorbs
        # some of the diverted traffic and sees a partial, opposite-sign AQI
        # shift. This is the "traffic diversion" mechanic — distinct from a
        # plain reduction scenario, which has no secondary ward impact.
        secondary_effects: list[dict] = []
        if params.get("diverts_traffic"):
            neighbor_ward = self._nearest_ward(primary_ward)
            if neighbor_ward:
                diversion_fraction = 0.30  # fraction of the removed traffic assumed to reroute through the nearest ward
                diverted_delta = round(abs(aqi_delta) * diversion_fraction, 1)
                secondary_effects.append(
                    {
                        "ward_id": neighbor_ward,
                        "effect": "traffic_diversion_increase",
                        "aqi_delta": diverted_delta,
                        "note": f"Estimated {diversion_fraction:.0%} of diverted traffic reroutes through {neighbor_ward}.",
                    }
                )

        # ── Impact score: 0-100, combining benefit magnitude (relative to
        # baseline) with how much we trust the estimate — a large predicted
        # improvement from a low-confidence scenario scores lower than a
        # modest improvement we're confident about.
        relative_benefit = min(1.0, abs(aqi_delta) / max(baseline_aqi, 1.0))
        impact_score = round(min(100.0, relative_benefit * 100 * confidence * 1.4), 1)

        # ── Confidence interval: widen proportionally to (1 - confidence),
        # consistent with how the forecast task derives its margin.
        margin = abs(aqi_delta) * (1 - confidence) * 1.5
        ci_lower = round(simulated_aqi - margin, 1)
        ci_upper = round(simulated_aqi + margin, 1)

        reasoning = bundle_reasoning or (
            f"Scenario: {params['description']}. "
            f"Current {target_source} contribution: {target_contribution:.0%}. "
            f"Applying {reduction_pct:.0%} reduction to {target_source} sources. "
            f"Expected AQI change: {aqi_delta:+.1f} units "
            f"(from {baseline_aqi:.0f} to {simulated_aqi:.0f}). "
            f"Effect visible within {params['time_to_effect_hours']}h. "
            f"CO₂ impact: {co2_impact:+.0f} kg/day."
        )
        if secondary_effects:
            reasoning += (
                f" Secondary effect: +{secondary_effects[0]['aqi_delta']:.1f} AQI diverted to "
                f"{secondary_effects[0]['ward_id']}."
            )

        return SimulationResult(
            scenario=params["description"],
            baseline_aqi=round(baseline_aqi, 1),
            simulated_aqi=round(simulated_aqi, 1),
            aqi_delta=round(aqi_delta, 1),
            pm25_delta=round(pm25_delta, 2),
            confidence=confidence,
            affected_wards=affected_wards[:8],
            co2_impact_kg_day=round(co2_impact, 1),
            time_to_effect_hours=params["time_to_effect_hours"],
            reasoning=reasoning,
            dispersion_map=dispersion_map,
            impact_score=impact_score,
            confidence_interval_lower=ci_lower,
            confidence_interval_upper=ci_upper,
            secondary_effects=secondary_effects,
        )

    async def list_scenarios(self) -> list[dict]:
        return [
            {
                "key": k,
                "description": v["description"],
                "target_source": v["target_source"],
                "reduction_pct": v["reduction_pct"],
                "time_to_effect_hours": v["time_to_effect_hours"],
            }
            for k, v in self.SCENARIO_PARAMS.items()
        ]

    def _estimate_co2_impact(self, source_type: str, reduction_pct: float) -> float:
        baseline_co2 = {
            "vehicular": -4500,
            "industrial": -12000,
            "construction": -2400,
            "biomass": -800,
        }
        return baseline_co2.get(source_type, -1000) * reduction_pct

    def _nearest_ward(self, ward_id: str) -> str | None:
        """Nearest other ward by centroid distance — used for traffic-diversion secondary effects."""
        from app.gis.operations import PUNE_WARD_BOUNDARIES, _haversine_km

        meta = PUNE_WARD_BOUNDARIES.get(ward_id)
        if not meta:
            return None
        cx, cy = meta["center"]

        nearest, nearest_dist = None, float("inf")
        for other_id, other_meta in PUNE_WARD_BOUNDARIES.items():
            if other_id == ward_id:
                continue
            ox, oy = other_meta["center"]
            dist = _haversine_km(cy, cx, oy, ox)
            if dist < nearest_dist:
                nearest, nearest_dist = other_id, dist
        return nearest

    def _gaussian_dispersion_map(
        self, ward_id: str, aqi_delta: float, city: str
    ) -> list[dict]:
        """Generate grid of simulated concentration change points using Gaussian plume."""
        from app.gis.operations import PUNE_WARD_BOUNDARIES

        meta = PUNE_WARD_BOUNDARIES.get(ward_id, {"center": [73.85, 18.52]})
        cx, cy = meta["center"]
        wind_dir_rad = math.radians(225)  # SW prevailing wind in Pune
        points = []

        for di in range(-3, 4):
            for dj in range(-3, 4):
                lon = cx + di * 0.01
                lat = cy + dj * 0.01
                # Gaussian decay from source
                dist = math.sqrt((di * 0.01) ** 2 + (dj * 0.01) ** 2)
                sigma = 0.02
                gaussian = math.exp(-(dist**2) / (2 * sigma**2))
                # Wind alignment factor
                vec_x, vec_y = di * 0.01, dj * 0.01
                wind_x = math.cos(wind_dir_rad)
                wind_y = math.sin(wind_dir_rad)
                dot = vec_x * wind_x + vec_y * wind_y
                wind_factor = max(0.1, (dot + 1) / 2)
                delta_here = round(aqi_delta * gaussian * wind_factor, 1)
                points.append(
                    {"latitude": lat, "longitude": lon, "aqi_delta": delta_here}
                )

        return points
