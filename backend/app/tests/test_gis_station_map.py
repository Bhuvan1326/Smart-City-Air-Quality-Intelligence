"""Tests for the geographic station-map and pollution-hotspot endpoints."""

import pytest


class TestStationsMap:
    def test_unauthenticated_rejected(self):
        from fastapi.testclient import TestClient

        from app.main import app

        resp = TestClient(app).get("/api/v1/gis/stations/map?city=Pune")
        assert resp.status_code == 403

    @pytest.mark.integration
    async def test_returns_points_with_provenance(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/gis/stations/map?city=Pune", headers=auth_headers
        )
        assert resp.status_code == 200
        points = resp.json()["data"]
        assert len(points) >= 1
        for p in points:
            assert -90 <= p["latitude"] <= 90
            assert -180 <= p["longitude"] <= 180
            assert p["reading"]["data_source"] in (
                "observed",
                "synthetic",
                "unavailable",
            )
            if p["reading"]["data_source"] == "unavailable":
                assert p["reading"]["aqi"] is None

    @pytest.mark.integration
    async def test_category_matches_aqi(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/gis/stations/map?city=Pune", headers=auth_headers
        )
        for p in resp.json()["data"]:
            aqi = p["reading"]["aqi"]
            if aqi is not None:
                assert p["reading"]["aqi_category"] is not None

    @pytest.mark.integration
    async def test_hotspots_default_excludes_synthetic(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/gis/pollution-hotspots?city=Pune", headers=auth_headers
        )
        assert resp.status_code == 200
        for h in resp.json()["data"]:
            assert h.get("data_source") != "synthetic"

    @pytest.mark.integration
    async def test_hotspots_synthetic_labeled(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/gis/pollution-hotspots?city=Pune&include_synthetic=true",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        for h in resp.json()["data"]:
            assert h["data_source"] == "synthetic"
            assert h["point_count"] >= 1
            assert h["avg_aqi"] > 0
            assert "detected_at" in h
