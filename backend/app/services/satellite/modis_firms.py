"""
NASA FIRMS (Fire Information for Resource Management System) client.

FIRMS aggregates active-fire/thermal-anomaly detections from MODIS and
VIIRS. It's the standard public source for biomass-burning detection (crop
stubble burning is a major seasonal PM2.5 contributor around Indian cities)
and provides a genuine, well-validated thermal-anomaly signal — a stronger
basis for "biomass burning" and "industrial thermal hotspot" attribution
than trying to derive one from Sentinel-2's non-thermal bands.

API docs: https://firms.modis.gov/api/. The area API returns CSV over a
bounding box; a NASA_FIRMS_MAP_KEY (issued free at the site above) is
required. As with sentinel_hub.py, the HTTP call here can't be exercised
against the live service from this sandbox — verify against a real key
before relying on it in production.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logging import logger

_SOURCE = (
    "VIIRS_SNPP_NRT"  # 375m resolution, good balance of coverage vs. false positives
)


@dataclass
class ThermalHotspot:
    latitude: float
    longitude: float
    brightness_kelvin: float
    confidence: str  # "low" | "nominal" | "high" (VIIRS) or numeric (MODIS)
    frp_megawatts: float | None  # Fire Radiative Power — intensity proxy
    acquired_date: str
    day_night: str


class NasaFirmsClient:
    def __init__(self) -> None:
        self.map_key = settings.NASA_FIRMS_MAP_KEY
        self.base_url = settings.NASA_FIRMS_BASE_URL

    @property
    def is_configured(self) -> bool:
        return bool(self.map_key)

    async def fetch_hotspots(
        self,
        bbox: tuple[float, float, float, float],  # (min_lon, min_lat, max_lon, max_lat)
        days_back: int = 1,
    ) -> list[ThermalHotspot]:
        if not self.is_configured:
            logger.info("satellite.firms_not_configured")
            return []

        min_lon, min_lat, max_lon, max_lat = bbox
        area = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        url = f"{self.base_url}/area/csv/{self.map_key}/{_SOURCE}/{area}/{days_back}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.error("satellite.firms_error", error=str(e))
                return []

        hotspots: list[ThermalHotspot] = []
        reader = csv.DictReader(io.StringIO(resp.text))
        for row in reader:
            try:
                hotspots.append(
                    ThermalHotspot(
                        latitude=float(row["latitude"]),
                        longitude=float(row["longitude"]),
                        brightness_kelvin=float(
                            row.get("bright_ti4", row.get("brightness", 0))
                        ),
                        confidence=row.get("confidence", "unknown"),
                        frp_megawatts=float(row["frp"]) if row.get("frp") else None,
                        acquired_date=row.get("acq_date", ""),
                        day_night=row.get("daynight", ""),
                    )
                )
            except (KeyError, ValueError):
                continue

        return hotspots

    @staticmethod
    def classify_hotspot(hotspot: ThermalHotspot) -> str:
        """
        Coarse rule-of-thumb classification. FRP and time-of-day are the
        cheapest signals available without cross-referencing land-use
        polygons: industrial thermal sources tend to run continuously
        (day and night, moderate steady FRP), while agricultural/biomass
        burning is typically daytime, higher FRP, more spatially clustered.
        This is a heuristic, not a certainty — always present alongside the
        raw FRP/confidence so a human reviewer can override it.
        """
        if hotspot.frp_megawatts is None:
            return "unclassified"
        if hotspot.frp_megawatts > 50 and hotspot.day_night == "D":
            return "likely_biomass_burning"
        if hotspot.frp_megawatts <= 50 and hotspot.confidence in ("nominal", "high"):
            return "likely_industrial_thermal_source"
        return "unclassified"
