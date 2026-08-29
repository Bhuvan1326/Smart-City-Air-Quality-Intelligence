"""
Copernicus Data Space Ecosystem (CDSE) Sentinel Hub-compatible client.

CDSE (https://dataspace.copernicus.eu) is the EU-operated, genuinely
free-forever access point for Sentinel data: sign-up requires no credit
card and never expires — usage is governed by a monthly processing-unit
quota that simply resets each month, not a time-limited trial. It exposes
the same Sentinel Hub Statistical/Process API used commercially, so the
request/response shapes below match the standard Sentinel Hub API docs
(https://documentation.dataspace.copernicus.eu/APIs/SentinelHub.html).

Pulls Sentinel-2 derived indices for a ward's bounding box:
  - NDVI (vegetation index) — used to flag vegetation loss consistent with
    construction/land clearing.
  - NDBI-based construction-dust proxy — bare/impervious surface fraction,
    which correlates with active construction sites.
  - SWIR reflectance — a coarse proxy for industrial/thermal hotspots (true
    thermal anomaly detection uses Sentinel-3/MODIS LST; see
    modis_firms.py for the dedicated, free, fire/thermal-anomaly product).

This module cannot be exercised against the live CDSE API from this
sandbox (network egress is restricted to package registries), so treat the
HTTP-calling paths as needing a live-credential smoke test before
production use — the request/response shapes match CDSE's documented API,
but haven't been round-tripped against the real service here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

import httpx
from app.core.config import settings
from app.core.logging import logger

# Evalscript computing NDVI + a simple bare-soil/construction index (NDBI-like)
# and mean brightness in the thermal-adjacent SWIR band, averaged over the
# queried polygon. Runs server-side on Sentinel Hub.
_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "B11", "B12", "SCL"] }],
    output: [
      { id: "ndvi", bands: 1, sampleType: "FLOAT32" },
      { id: "ndbi", bands: 1, sampleType: "FLOAT32" },
      { id: "swir", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(s) {
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04 + 1e-6);
  let ndbi = (s.B11 - s.B08) / (s.B11 + s.B08 + 1e-6);
  let cloud = (s.SCL == 8 || s.SCL == 9 || s.SCL == 10) ? 0 : 1;
  return {
    ndvi: [ndvi],
    ndbi: [ndbi],
    swir: [s.B12],
    dataMask: [cloud]
  };
}
"""


@dataclass
class SatelliteBandSummary:
    ward_id: str
    observed_date: date
    mean_ndvi: float | None
    mean_ndbi: float | None
    mean_swir_reflectance: float | None
    cloud_free_fraction: float | None
    vegetation_loss_flag: bool = False
    construction_dust_flag: bool = False
    raw: dict = field(default_factory=dict)


class SentinelHubClient:
    def __init__(self) -> None:
        self.client_id = settings.SENTINEL_HUB_CLIENT_ID
        self.client_secret = settings.SENTINEL_HUB_CLIENT_SECRET
        self.base_url = settings.SENTINEL_HUB_BASE_URL
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _get_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token
        resp = await client.post(
            settings.SENTINEL_HUB_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + payload.get("expires_in", 3600)
        return self._token

    async def fetch_ward_indices(
        self,
        ward_id: str,
        bbox: tuple[float, float, float, float],  # (min_lon, min_lat, max_lon, max_lat)
        from_date: date,
        to_date: date,
    ) -> SatelliteBandSummary | None:
        """
        Fetch mean NDVI/NDBI/SWIR over a ward bounding box for the given
        window via the Statistical API (one aggregated number per band per
        time period, not a full raster — cheaper and sufficient for
        ward-level attribution).
        """
        if not self.is_configured:
            logger.info("satellite.not_configured", ward_id=ward_id)
            return None

        request_body = {
            "input": {
                "bounds": {
                    "bbox": list(bbox),
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [{"type": "sentinel-2-l2a"}],
            },
            "aggregation": {
                "timeRange": {
                    "from": f"{from_date.isoformat()}T00:00:00Z",
                    "to": f"{to_date.isoformat()}T23:59:59Z",
                },
                "aggregationInterval": {"of": "P1D"},
                "evalscript": _EVALSCRIPT,
                "resx": 20,
                "resy": 20,
            },
            "calculations": {
                "ndvi": {"statistics": {"default": {"percentiles": {"k": [50]}}}},
                "ndbi": {"statistics": {"default": {"percentiles": {"k": [50]}}}},
                "swir": {"statistics": {"default": {"percentiles": {"k": [50]}}}},
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                token = await self._get_token(client)
                resp = await client.post(
                    f"{self.base_url}/api/v1/statistics",
                    json=request_body,
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                logger.error(
                    "satellite.sentinel_hub_error", ward_id=ward_id, error=str(e)
                )
                return None

        intervals = data.get("data", [])
        if not intervals:
            return None

        ndvi_vals, ndbi_vals, swir_vals, valid_counts, total_counts = [], [], [], 0, 0
        for interval in intervals:
            outputs = interval.get("outputs", {})
            for key, out_vals in (
                ("ndvi", ndvi_vals),
                ("ndbi", ndbi_vals),
                ("swir", swir_vals),
            ):
                stats = outputs.get(key, {}).get("bands", {}).get("B0", {}).get("stats")
                if stats and stats.get("mean") is not None:
                    out_vals.append(stats["mean"])
            mask_stats = (
                outputs.get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats")
            )
            if mask_stats:
                total_counts += mask_stats.get("sampleCount", 0)
                valid_counts += mask_stats.get("sampleCount", 0) - mask_stats.get(
                    "noDataCount", 0
                )

        mean_ndvi = sum(ndvi_vals) / len(ndvi_vals) if ndvi_vals else None
        mean_ndbi = sum(ndbi_vals) / len(ndbi_vals) if ndbi_vals else None
        mean_swir = sum(swir_vals) / len(swir_vals) if swir_vals else None
        cloud_free_fraction = (valid_counts / total_counts) if total_counts else None

        return SatelliteBandSummary(
            ward_id=ward_id,
            observed_date=to_date,
            mean_ndvi=mean_ndvi,
            mean_ndbi=mean_ndbi,
            mean_swir_reflectance=mean_swir,
            cloud_free_fraction=cloud_free_fraction,
            vegetation_loss_flag=(mean_ndvi is not None and mean_ndvi < 0.2),
            construction_dust_flag=(mean_ndbi is not None and mean_ndbi > 0.1),
            raw=data,
        )
