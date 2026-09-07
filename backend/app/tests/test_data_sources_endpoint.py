"""Tests for GET /api/v1/system/data-sources, focused on traffic status."""

import tempfile

import pytest
from httpx import AsyncClient

from app.core.config import settings


def _reset_csv_cache():
    import app.services.traffic_provider as mod

    mod._csv_cache = None
    mod._csv_cache_path = None


@pytest.mark.asyncio
async def test_data_sources_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/system/data-sources")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_data_sources_reports_demo_traffic_when_provider_is_demo(
    client: AsyncClient, auth_headers: dict
):
    original = settings.TRAFFIC_PROVIDER
    settings.TRAFFIC_PROVIDER = "demo"
    try:
        resp = await client.get("/api/v1/system/data-sources", headers=auth_headers)
        assert resp.status_code == 200
        traffic = resp.json()["data"]["traffic"]
        assert traffic["configured"] is False
        assert "demo" in traffic["note"].lower()
    finally:
        settings.TRAFFIC_PROVIDER = original


@pytest.mark.asyncio
async def test_data_sources_reports_configured_traffic_for_valid_csv(
    client: AsyncClient, auth_headers: dict
):
    original_provider = settings.TRAFFIC_PROVIDER
    original_path = settings.TRAFFIC_CSV_PATH
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as f:
        f.write("ward_id,hour,level\nW01,8,high\n")
        path = f.name

    try:
        settings.TRAFFIC_PROVIDER = "csv"
        settings.TRAFFIC_CSV_PATH = path
        _reset_csv_cache()
        resp = await client.get("/api/v1/system/data-sources", headers=auth_headers)
        assert resp.status_code == 200
        traffic = resp.json()["data"]["traffic"]
        assert traffic["configured"] is True
    finally:
        settings.TRAFFIC_PROVIDER = original_provider
        settings.TRAFFIC_CSV_PATH = original_path
        _reset_csv_cache()


@pytest.mark.asyncio
async def test_data_sources_reports_unavailable_traffic_for_missing_csv(
    client: AsyncClient, auth_headers: dict
):
    original_provider = settings.TRAFFIC_PROVIDER
    original_path = settings.TRAFFIC_CSV_PATH
    try:
        settings.TRAFFIC_PROVIDER = "csv"
        settings.TRAFFIC_CSV_PATH = "/nonexistent/path/traffic.csv"
        _reset_csv_cache()
        resp = await client.get("/api/v1/system/data-sources", headers=auth_headers)
        assert resp.status_code == 200
        traffic = resp.json()["data"]["traffic"]
        assert traffic["configured"] is False
        assert "does not exist" in traffic["note"]
    finally:
        settings.TRAFFIC_PROVIDER = original_provider
        settings.TRAFFIC_CSV_PATH = original_path
        _reset_csv_cache()


@pytest.mark.asyncio
async def test_data_sources_response_has_no_secret_mapbox_field(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/v1/system/data-sources", headers=auth_headers)
    assert resp.status_code == 200
    dumped = str(resp.json()["data"]).lower()
    assert "mapbox" not in dumped
    assert "token" not in dumped
