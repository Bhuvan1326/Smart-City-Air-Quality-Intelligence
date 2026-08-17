"""
Carbon Emission Estimator — estimates CO₂ and PM2.5 reduction potential
per source category and enforcement action type.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# IPCC-aligned emission factors (kg CO₂ per unit)
EMISSION_FACTORS = {
    "vehicular": {
        "co2_per_vehicle_km": 0.171,  # avg passenger car
        "pm25_per_vehicle_km": 0.000031,  # kg PM2.5
        "vehicles_per_hour_corridor": 3000,
        "avg_km_in_zone": 2.5,
    },
    "industrial": {
        "co2_per_kwh": 0.82,  # India grid average
        "pm25_per_kg_coal": 0.0085,
        "avg_coal_kg_hr": 450,
    },
    "construction": {
        "co2_per_sqm_per_day": 1.2,
        "pm25_per_sqm_per_day": 0.00045,
        "avg_site_sqm": 2000,
    },
    "biomass": {
        "co2_per_kg_burned": 1.65,
        "pm25_per_kg_burned": 0.0185,
        "avg_kg_per_event": 200,
    },
}


@dataclass
class EmissionEstimate:
    source_type: str
    co2_kg_per_day: float
    pm25_kg_per_day: float
    co2_ton_per_year: float
    reduction_potential_co2_pct: float
    reduction_potential_pm25_pct: float
    methodology: str
    confidence: float


class CarbonEstimatorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def estimate_city_emissions(self, city: str) -> dict:
        """
        Estimate total CO₂ and PM2.5 from all active emission sources in a city.
        """
        result = await self.session.execute(
            text(
                """
            SELECT source_type, COUNT(*) as count,
                   SUM(emission_rate_kg_hr) as total_rate_kg_hr,
                   SUM(carbon_estimate_ton_yr) as total_carbon_ton_yr,
                   AVG(violation_count) as avg_violations
            FROM emission_sources
            WHERE city = :city AND is_active = true AND is_deleted = false
            GROUP BY source_type
        """
            ),
            {"city": city},
        )
        source_summary = [dict(row._mapping) for row in result]

        estimates: list[EmissionEstimate] = []
        total_co2_day = 0.0
        total_pm25_day = 0.0

        for src in source_summary:
            stype = src["source_type"]
            est = self._estimate_by_type(stype, src)
            estimates.append(est)
            total_co2_day += est.co2_kg_per_day
            total_pm25_day += est.pm25_kg_per_day

        # Reduction scenarios
        scenarios = self._build_reduction_scenarios(
            total_co2_day, total_pm25_day, source_summary
        )

        # Source breakdown as percentages
        breakdown = {}
        for est in estimates:
            pct = (est.co2_kg_per_day / total_co2_day * 100) if total_co2_day > 0 else 0
            breakdown[est.source_type] = {
                "co2_kg_per_day": round(est.co2_kg_per_day, 1),
                "pm25_kg_per_day": round(est.pm25_kg_per_day, 2),
                "share_pct": round(pct, 1),
                "methodology": est.methodology,
                "confidence": est.confidence,
            }

        return {
            "city": city,
            "total_co2_kg_per_day": round(total_co2_day, 1),
            "total_co2_ton_per_year": round(total_co2_day * 365 / 1000, 1),
            "total_pm25_kg_per_day": round(total_pm25_day, 3),
            "source_breakdown": breakdown,
            "reduction_scenarios": scenarios,
            "methodology_note": "IPCC emission factors + CPCB stack emission norms",
        }

    async def estimate_enforcement_impact(
        self, source_type: str, action_type: str, duration_days: int = 30
    ) -> dict:
        """
        Estimate CO₂ and PM2.5 reduction from an enforcement action.
        """
        factors = EMISSION_FACTORS.get(source_type, {})

        if source_type == "vehicular":
            daily_co2 = (
                factors.get("vehicles_per_hour_corridor", 3000)
                * 16  # operational hours
                * factors.get("avg_km_in_zone", 2.5)
                * factors.get("co2_per_vehicle_km", 0.171)
            )
            daily_pm25 = (
                factors.get("vehicles_per_hour_corridor", 3000)
                * 16
                * factors.get("avg_km_in_zone", 2.5)
                * factors.get("pm25_per_vehicle_km", 0.000031)
            )
            reduction_pct = 0.30 if action_type in ("shutdown", "notice") else 0.15
        elif source_type == "industrial":
            daily_co2 = (
                factors.get("avg_coal_kg_hr", 450)
                * 16
                * factors.get("co2_per_kwh", 0.82)
            )
            daily_pm25 = (
                factors.get("avg_coal_kg_hr", 450)
                * 16
                * factors.get("pm25_per_kg_coal", 0.0085)
            )
            reduction_pct = 1.0 if action_type == "shutdown" else 0.40
        elif source_type == "construction":
            daily_co2 = factors.get("avg_site_sqm", 2000) * factors.get(
                "co2_per_sqm_per_day", 1.2
            )
            daily_pm25 = factors.get("avg_site_sqm", 2000) * factors.get(
                "pm25_per_sqm_per_day", 0.00045
            )
            reduction_pct = 1.0 if action_type == "shutdown" else 0.60
        elif source_type == "biomass":
            daily_co2 = factors.get("avg_kg_per_event", 200) * factors.get(
                "co2_per_kg_burned", 1.65
            )
            daily_pm25 = factors.get("avg_kg_per_event", 200) * factors.get(
                "pm25_per_kg_burned", 0.0185
            )
            reduction_pct = 0.80
        else:
            daily_co2 = 500.0
            daily_pm25 = 0.5
            reduction_pct = 0.20

        co2_saved = daily_co2 * reduction_pct * duration_days
        pm25_saved = daily_pm25 * reduction_pct * duration_days
        aqi_delta_estimate = round(pm25_saved / duration_days * 8, 1)

        return {
            "source_type": source_type,
            "action_type": action_type,
            "duration_days": duration_days,
            "co2_saved_kg": round(co2_saved, 1),
            "pm25_saved_kg": round(pm25_saved, 3),
            "estimated_aqi_delta": -aqi_delta_estimate,
            "reduction_pct": round(reduction_pct * 100, 0),
            "daily_co2_baseline_kg": round(daily_co2, 1),
            "methodology": "IPCC emission factors × operational hours × reduction efficiency",
        }

    def _estimate_by_type(self, source_type: str, src: dict) -> EmissionEstimate:
        total_rate = float(src.get("total_rate_kg_hr") or 0)
        total_carbon = float(src.get("total_carbon_ton_yr") or 0)
        count = int(src.get("count") or 1)

        if total_carbon > 0:
            co2_day = total_carbon * 1000 / 365
        elif total_rate > 0:
            co2_day = total_rate * 16 * 3.67  # CO2/C ratio
        else:
            co2_day = count * 500.0

        f = EMISSION_FACTORS.get(source_type, {})
        if source_type == "vehicular":
            pm25_day = (
                count * 3000 * 2.5 * f.get("pm25_per_vehicle_km", 0.000031) * 1000
            )
        elif source_type == "industrial":
            pm25_day = total_rate * 16 * 0.002
        elif source_type == "construction":
            pm25_day = count * 2000 * f.get("pm25_per_sqm_per_day", 0.00045) * 1000
        else:
            pm25_day = count * 2.0

        return EmissionEstimate(
            source_type=source_type,
            co2_kg_per_day=round(co2_day, 1),
            pm25_kg_per_day=round(pm25_day, 3),
            co2_ton_per_year=round(co2_day * 365 / 1000, 1),
            reduction_potential_co2_pct=0.35,
            reduction_potential_pm25_pct=0.40,
            methodology="IPCC factors + CPCB emission norms",
            confidence=0.70 if total_rate > 0 else 0.50,
        )

    def _build_reduction_scenarios(
        self, total_co2: float, total_pm25: float, sources: list[dict]
    ) -> list[dict]:
        return [
            {
                "scenario": "Close all expired-permit industrial units",
                "co2_reduction_kg_day": round(total_co2 * 0.22, 1),
                "pm25_reduction_kg_day": round(total_pm25 * 0.28, 3),
                "aqi_delta_estimate": -18,
                "feasibility": "medium",
            },
            {
                "scenario": "Odd-even vehicle restriction (7-10 AM, 5-8 PM)",
                "co2_reduction_kg_day": round(total_co2 * 0.12, 1),
                "pm25_reduction_kg_day": round(total_pm25 * 0.15, 3),
                "aqi_delta_estimate": -12,
                "feasibility": "high",
            },
            {
                "scenario": "Mandatory water sprinklers on all construction sites",
                "co2_reduction_kg_day": round(total_co2 * 0.08, 1),
                "pm25_reduction_kg_day": round(total_pm25 * 0.20, 3),
                "aqi_delta_estimate": -14,
                "feasibility": "high",
            },
            {
                "scenario": "Ban on biomass burning citywide",
                "co2_reduction_kg_day": round(total_co2 * 0.05, 1),
                "pm25_reduction_kg_day": round(total_pm25 * 0.12, 3),
                "aqi_delta_estimate": -8,
                "feasibility": "medium",
            },
        ]
