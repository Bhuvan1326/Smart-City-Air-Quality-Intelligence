from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.core.redis_client import cache_delete


@pytest.mark.asyncio
async def test_model_performance_history_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/model-performance/history?city=Pune")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_model_performance_history_returns_evaluated_records(
    client: AsyncClient, auth_headers: dict
):
    # Endpoint is cached by (city, target); clear first so this test isn't
    # affected by a cached result from a previous run.
    await cache_delete("model-performance:history:Pune:aqi")

    fake_record = {
        "model_version": "xgb-20260816_1509",
        "model_name": "XGBoost Regressor",
        "target": "aqi",
        "city": "Pune",
        "trained_at": "2026-08-16T15:09:00+00:00",
        "training_period_start": "2026-05-18T15:09:00+00:00",
        "training_period_end": "2026-08-16T15:09:00+00:00",
        "test_sample_count": 320,
        "mae": 4.2,
        "rmse": 6.1,
        "r2": 0.87,
        "mape": 0.05,
        "features": ["current_aqi", "hour", "day_of_week"],
        "is_active": True,
    }

    with patch(
        "app.api.v1.endpoints.model_performance.evaluate_model_versions",
        new=AsyncMock(return_value=[fake_record]),
    ):
        resp = await client.get(
            "/api/v1/model-performance/history?city=Pune&target=aqi",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    records = resp.json()["data"]
    assert len(records) == 1
    assert records[0]["model_version"] == "xgb-20260816_1509"
    assert records[0]["is_active"] is True


@pytest.mark.asyncio
async def test_model_performance_active_returns_null_when_no_active_version(
    client: AsyncClient, auth_headers: dict
):
    with patch(
        "app.api.v1.endpoints.model_performance.evaluate_model_versions",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.get(
            "/api/v1/model-performance/active?city=Pune&target=aqi",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert resp.json()["data"] is None


@pytest.mark.asyncio
async def test_model_performance_active_returns_the_active_version_only(
    client: AsyncClient, auth_headers: dict
):
    records = [
        {
            "model_version": "xgb-old",
            "model_name": "XGBoost Regressor",
            "target": "aqi",
            "city": "Pune",
            "trained_at": "2026-01-01T00:00:00+00:00",
            "training_period_start": "2025-10-03T00:00:00+00:00",
            "training_period_end": "2026-01-01T00:00:00+00:00",
            "test_sample_count": 200,
            "mae": 6.0,
            "rmse": 8.0,
            "r2": 0.7,
            "mape": 0.08,
            "features": ["current_aqi"],
            "is_active": False,
        },
        {
            "model_version": "xgb-new",
            "model_name": "XGBoost Regressor",
            "target": "aqi",
            "city": "Pune",
            "trained_at": "2026-08-16T15:09:00+00:00",
            "training_period_start": "2026-05-18T15:09:00+00:00",
            "training_period_end": "2026-08-16T15:09:00+00:00",
            "test_sample_count": 320,
            "mae": 4.2,
            "rmse": 6.1,
            "r2": 0.87,
            "mape": 0.05,
            "features": ["current_aqi"],
            "is_active": True,
        },
    ]

    with patch(
        "app.api.v1.endpoints.model_performance.evaluate_model_versions",
        new=AsyncMock(return_value=records),
    ):
        resp = await client.get(
            "/api/v1/model-performance/active?city=Pune&target=aqi",
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["model_version"] == "xgb-new"
