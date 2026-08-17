"""
Atmospheric Dispersion Modelling.

Implements the standard Gaussian plume model used for regulatory-grade
near-source dispersion estimates (US EPA's ISC/AERMOD family of models are
built on the same core equation), rather than the simplified fixed-wind
decorative version previously used only inside the what-if simulator (see
app.services.whatif_simulator, which still owns the scenario-comparison UX
and can be extended to call into this module for its spatial map).

Core equation (ground-level, ground-source concentration, no plume rise):

    C(x, y) = Q / (2*pi * u * sigma_y * sigma_z)
              * exp(-y^2 / (2*sigma_y^2))
              * exp(-2*Hs^2 / (2*sigma_z^2))   [reduces to the y-term only at Hs=0]

where x is downwind distance, y is crosswind distance, u is wind speed,
sigma_y/sigma_z are plume spread parameters (functions of downwind distance
and atmospheric stability), and Hs is effective source height.

Atmospheric stability (Pasquill-Gifford classes A-F) is estimated from wind
speed and time-of-day/solar-elevation proxy — the standard simplified
scheme when direct solar radiation / cloud cover isn't available.

Two pollutant-specific behaviours are modelled:
  - PM2.5: near-zero gravitational settling at this scale — transported
    essentially as a passive tracer over city distances.
  - PM10: measurable settling velocity, modelled as first-order removal
    with downwind distance (larger particles fall out of the plume faster),
    so PM10 concentration attenuates faster than PM2.5 with distance from
    source — a real, physically-grounded difference the previous
    implementation didn't have (it used the same profile for both).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

_EARTH_RADIUS_M = 6371000.0

# Approximate gravitational settling velocities (m/s) — PM10 (10 micron)
# settles meaningfully faster than PM2.5 (2.5 micron) per Stokes' law scaling
# (~d^2), which is why PM10 plumes attenuate with distance while PM2.5
# behaves almost like a passive tracer at city scale.
PM25_SETTLING_VELOCITY_MPS = 0.0004
PM10_SETTLING_VELOCITY_MPS = 0.01


class StabilityClass(str, Enum):
    A = "A"  # very unstable
    B = "B"  # unstable
    C = "C"  # slightly unstable
    D = "D"  # neutral
    E = "E"  # slightly stable
    F = "F"  # stable


def classify_stability(
    wind_speed_mps: float, hour: int, cloud_cover_fraction: float | None = None
) -> StabilityClass:
    """
    Simplified Pasquill-Gifford classification (Turner's method) from wind
    speed and insolation proxy. Real deployments with a solar radiation
    sensor or cloud-cover feed should pass `cloud_cover_fraction`; without
    one, daytime/nighttime + hour-of-day approximates insolation strength,
    which is the standard fallback when a dedicated sensor isn't available.
    """
    is_daytime = 6 <= hour <= 18
    if cloud_cover_fraction is not None and cloud_cover_fraction > 0.75:
        insolation = "weak"
    elif is_daytime:
        # Midday hours get "strong" insolation, morning/evening "moderate".
        insolation = "strong" if 10 <= hour <= 15 else "moderate"
    else:
        insolation = "night"

    if insolation == "night":
        if wind_speed_mps < 2.5:
            return StabilityClass.F
        elif wind_speed_mps < 3.5:
            return StabilityClass.E
        return StabilityClass.D

    if wind_speed_mps < 2:
        return StabilityClass.A if insolation == "strong" else StabilityClass.B
    elif wind_speed_mps < 3:
        return StabilityClass.B if insolation == "strong" else StabilityClass.C
    elif wind_speed_mps < 5:
        return StabilityClass.C if insolation == "strong" else StabilityClass.D
    elif wind_speed_mps < 6:
        return StabilityClass.D
    return StabilityClass.D


# Briggs urban dispersion coefficients: sigma_y(x) = a*x / sqrt(1 + b*x) (km),
# sigma_z(x) = c*x / sqrt(1 + d*x). Urban coefficients used throughout since
# this module targets city-scale ward-to-ward transport, not rural terrain.
_BRIGGS_URBAN = {
    StabilityClass.A: {"ay": 0.32, "by": 0.0004, "az": 0.24, "bz": 0.001, "dz_sign": 1},
    StabilityClass.B: {"ay": 0.32, "by": 0.0004, "az": 0.24, "bz": 0.001, "dz_sign": 1},
    StabilityClass.C: {"ay": 0.22, "by": 0.0004, "az": 0.20, "bz": 0.0, "dz_sign": 1},
    StabilityClass.D: {
        "ay": 0.16,
        "by": 0.0004,
        "az": 0.14,
        "bz": 0.0003,
        "dz_sign": -1,
    },
    StabilityClass.E: {
        "ay": 0.11,
        "by": 0.0004,
        "az": 0.08,
        "bz": 0.0015,
        "dz_sign": -1,
    },
    StabilityClass.F: {
        "ay": 0.11,
        "by": 0.0004,
        "az": 0.08,
        "bz": 0.0015,
        "dz_sign": -1,
    },
}


def plume_spread(x_meters: float, stability: StabilityClass) -> tuple[float, float]:
    """Returns (sigma_y, sigma_z) in meters for downwind distance x_meters."""
    if x_meters <= 0:
        return 1.0, 1.0
    coeffs = _BRIGGS_URBAN[stability]
    sigma_y = coeffs["ay"] * x_meters / math.sqrt(1 + coeffs["by"] * x_meters)
    exponent = -0.5 if coeffs["dz_sign"] > 0 else 0.5
    sigma_z = coeffs["az"] * x_meters * (1 + coeffs["bz"] * x_meters) ** exponent
    return max(sigma_y, 0.5), max(sigma_z, 0.5)


def gaussian_plume_concentration(
    downwind_m: float,
    crosswind_m: float,
    wind_speed_mps: float,
    stability: StabilityClass,
    source_strength: float = 1.0,
    settling_velocity_mps: float = 0.0,
) -> float:
    """
    Ground-level concentration at a receptor, normalized to source_strength=1
    at the source (i.e. this returns a *relative* dilution factor unless
    source_strength is given in real emission-rate units). Callers here use
    it as a relative attenuation factor applied to an upwind ward's own
    measured AQI, which sidesteps needing calibrated emission-rate data.

    `settling_velocity_mps` > 0 applies an additional first-order removal
    term with downwind travel time (used for PM10; PM2.5 uses ~0, i.e.
    passive-tracer behaviour).
    """
    wind_speed_mps = max(
        0.5, wind_speed_mps
    )  # avoid singularity in near-calm conditions; real calm-wind dispersion needs a puff model, out of scope here

    sigma_y, sigma_z = plume_spread(downwind_m, stability)

    crosswind_term = math.exp(-(crosswind_m**2) / (2 * sigma_y**2))
    concentration = (
        source_strength
        / (2 * math.pi * wind_speed_mps * sigma_y * sigma_z)
        * crosswind_term
    )

    if settling_velocity_mps > 0 and downwind_m > 0:
        travel_time_s = downwind_m / wind_speed_mps
        removal_fraction = 1 - math.exp(
            -settling_velocity_mps * travel_time_s / max(sigma_z, 1.0)
        )
        concentration *= 1 - min(0.95, removal_fraction)

    return concentration


@dataclass
class WardTransportContribution:
    source_ward_id: str
    target_ward_id: str
    pollutant: str  # "pm25" | "pm10"
    downwind_m: float
    crosswind_m: float
    is_upwind: bool
    relative_concentration: float  # dilution factor, 0..1-ish
    contribution_aqi: float


@dataclass
class DispersionForecastAdjustment:
    ward_id: str
    stability_class: StabilityClass
    wind_speed_mps: float
    wind_direction_deg: float
    pm25_transport_delta: float
    pm10_transport_delta: float
    contributing_wards: list[WardTransportContribution] = field(default_factory=list)
    confidence_penalty: float = 0.0  # subtracted from base forecast confidence
    reasoning: list[str] = field(default_factory=list)


def _bearing_and_distance(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> tuple[float, float]:
    """Returns (bearing_degrees_from_1_to_2, distance_meters)."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    distance = 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))

    y = math.sin(dlon) * math.cos(lat2_r)
    x = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(
        lat2_r
    ) * math.cos(dlon)
    bearing = (math.degrees(math.atan2(y, x)) + 360) % 360

    return bearing, distance


class DispersionModel:
    """
    Computes cross-ward pollutant transport contributions for a target ward,
    given ward centroid coordinates, each ward's own current AQI (used as
    the emission-strength proxy), and a single city-wide wind
    observation. A per-ward wind observation would be more accurate; a
    single station's reading is the standard simplification for city-scale
    hourly forecasting when a full met network isn't available.
    """

    def compute_ward_adjustment(
        self,
        target_ward_id: str,
        target_coords: tuple[float, float],
        ward_aqi: dict[str, float],
        ward_coords: dict[str, tuple[float, float]],
        wind_speed_mps: float,
        wind_direction_deg: float,
        hour: int,
    ) -> DispersionForecastAdjustment:
        stability = classify_stability(wind_speed_mps, hour)
        reasoning = [
            f"Stability class {stability.value} from wind={wind_speed_mps:.1f}m/s, hour={hour}.",
        ]

        contributions: list[WardTransportContribution] = []
        pm25_delta = 0.0
        pm10_delta = 0.0

        target_lat, target_lon = target_coords

        for source_ward, source_coords in ward_coords.items():
            if source_ward == target_ward_id:
                continue
            source_aqi = ward_aqi.get(source_ward)
            if source_aqi is None:
                continue

            source_lat, source_lon = source_coords
            # Bearing FROM source TO target, and how that compares to the
            # direction the wind is blowing TOWARD (wind_direction_deg is
            # the meteorological convention: direction the wind blows FROM,
            # so the blow-toward direction is +180).
            bearing_source_to_target, distance_m = _bearing_and_distance(
                source_lat, source_lon, target_lat, target_lon
            )
            wind_blows_toward_deg = (wind_direction_deg + 180) % 360
            angle_diff = abs(
                (bearing_source_to_target - wind_blows_toward_deg + 180) % 360 - 180
            )

            # Only wards roughly upwind (within 60 degrees of the wind's
            # travel direction) can plausibly transport pollution to the
            # target — this both matches plume physics (crosswind
            # concentration falls off fast) and keeps computation bounded.
            is_upwind = angle_diff <= 60
            if not is_upwind:
                continue

            downwind_m = distance_m * math.cos(math.radians(angle_diff))
            crosswind_m = distance_m * math.sin(math.radians(angle_diff))

            pm25_factor = gaussian_plume_concentration(
                downwind_m,
                crosswind_m,
                wind_speed_mps,
                stability,
                source_strength=source_aqi,
                settling_velocity_mps=PM25_SETTLING_VELOCITY_MPS,
            )
            pm10_factor = gaussian_plume_concentration(
                downwind_m,
                crosswind_m,
                wind_speed_mps,
                stability,
                source_strength=source_aqi,
                settling_velocity_mps=PM10_SETTLING_VELOCITY_MPS,
            )

            # Normalize: at very short range the raw Gaussian factor can
            # exceed 1 (it's a dilution term, not a bounded fraction) —
            # cap each ward's contribution to a fraction of its own AQI so
            # a single close, low-wind-speed neighbour can't dominate the
            # forecast unrealistically.
            pm25_contribution = min(source_aqi * 0.4, pm25_factor * 1000)
            pm10_contribution = min(
                source_aqi * 0.3, pm10_factor * 1000
            )  # PM10 caps lower — settles out faster

            contributions.append(
                WardTransportContribution(
                    source_ward_id=source_ward,
                    target_ward_id=target_ward_id,
                    pollutant="pm25",
                    downwind_m=downwind_m,
                    crosswind_m=crosswind_m,
                    is_upwind=True,
                    relative_concentration=round(pm25_factor, 6),
                    contribution_aqi=round(pm25_contribution, 2),
                )
            )
            pm25_delta += pm25_contribution
            pm10_delta += pm10_contribution

        if contributions:
            top = max(contributions, key=lambda c: c.contribution_aqi)
            reasoning.append(
                f"{len(contributions)} upwind ward(s) contributing; largest is {top.source_ward_id} "
                f"at {top.downwind_m:.0f}m downwind (+{top.contribution_aqi:.1f} PM2.5-equivalent AQI)."
            )
        else:
            reasoning.append(
                "No wards found upwind of the current wind direction — transport contribution is zero."
            )

        # Confidence penalty: unstable (A/B) and stable (E/F) classes carry
        # more real-world dispersion uncertainty than neutral (D); low wind
        # speed also widens uncertainty (near-calm conditions are the
        # hardest case for any Gaussian plume model, which assumes steady
        # advection).
        stability_penalty = {
            StabilityClass.A: 0.08,
            StabilityClass.B: 0.05,
            StabilityClass.C: 0.03,
            StabilityClass.D: 0.02,
            StabilityClass.E: 0.05,
            StabilityClass.F: 0.08,
        }[stability]
        calm_penalty = 0.05 if wind_speed_mps < 1.5 else 0.0
        confidence_penalty = round(stability_penalty + calm_penalty, 3)

        return DispersionForecastAdjustment(
            ward_id=target_ward_id,
            stability_class=stability,
            wind_speed_mps=wind_speed_mps,
            wind_direction_deg=wind_direction_deg,
            pm25_transport_delta=round(pm25_delta, 2),
            pm10_transport_delta=round(pm10_delta, 2),
            contributing_wards=contributions,
            confidence_penalty=confidence_penalty,
            reasoning=reasoning,
        )
