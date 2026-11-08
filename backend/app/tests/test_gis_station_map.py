"""Tests for the geographic station-map and pollution-hotspot endpoints."""

import pytest


class TestStationsMap:
    def test_unauthenticated_rejected(self):
        from fastapi.testclient import TestClient

        from app.main import app

        resp = TestClient(app).get("/api/v1/gis/stations/map?city=Pune")
        assert resp.status_code == 403

    @pytest.mark.integration
    async def test_returns_points_with_provenance(
        self, client, auth_headers, test_engine
    ):
        from datetime import UTC, datetime

        from geoalchemy2.elements import WKTElement
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.models.monitoring import AQIReading, MonitoringStation

        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        async with session_factory() as s:
            station = MonitoringStation(
                name="Test Station",
                station_code="TEST_GIS_001",
                city="TestCity",
                ward_id="W99",
                operator="Test",
                latitude=18.5,
                longitude=73.8,
                geometry=WKTElement("POINT(73.8 18.5)", srid=4326),
                is_active=True,
                station_type="CAAQMS",
            )
            s.add(station)
            await s.flush()
            s.add(
                AQIReading(
                    station_id=station.id,
                    aqi=120,
                    pm25=50.0,
                    timestamp=datetime.now(UTC),
                    quality_flag="synthetic",
                    latitude=18.5,
                    longitude=73.8,
                )
            )
            await s.commit()

        resp = await client.get(
            "/api/v1/gis/stations/map?city=TestCity", headers=auth_headers
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
