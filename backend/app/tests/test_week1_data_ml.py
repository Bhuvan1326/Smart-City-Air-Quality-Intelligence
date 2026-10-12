"""Week 1 regression tests: training-target construction, freshness, config.

Synthetic frames below are test fixtures only — they are not evaluation data
and no model metric is derived from them.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, settings
from app.main import app
from app.services.data_freshness import FreshnessStatus, classify_freshness
from app.workers.tasks.forecast import build_training_frame, chronological_split


def _frame(wards=("W01", "W02", "W03"), hours=6, drop=None):
    rows = []
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for h in range(hours):
        for i, w in enumerate(wards):  # interleaved by hour, like the SQL
            if drop and (w, h) in drop:
                continue
            rows.append(
                {
                    "hour": base + timedelta(hours=h),
                    "ward_id": w,
                    # unique, decodable value: ward index*1000 + hour
                    "avg_aqi": float(i * 1000 + h),
                    "avg_temp": 25.0,
                    "avg_humidity": 50.0,
                    "avg_wind": 2.0,
                }
            )
    return pd.DataFrame(rows)


def test_target_is_same_ward_next_hour():
    out = build_training_frame(_frame())
    assert len(out) > 0
    # Same ward, exactly one hour later => target == avg_aqi + 1.
    assert ((out["target_aqi"] - out["avg_aqi"]) == 1.0).all()


def test_old_global_shift_would_have_mislabelled_rows():
    """Documents the defect: shift(-1) over hour-ordered, ward-interleaved
    rows pairs a ward with a different ward's value."""
    df = _frame().sort_values("hour", kind="stable").reset_index(drop=True)
    naive = df["avg_aqi"].shift(-1).dropna()
    assert ((naive - df["avg_aqi"].iloc[: len(naive)]) != 1.0).any()


def test_gap_in_hours_drops_row_instead_of_bridging():
    out = build_training_frame(_frame(drop={("W01", 2)}))
    w01 = out[out["ward_id"] == "W01"]
    assert 1.0 not in set(w01["avg_aqi"])  # hour 1 -> missing hour 2: no label
    assert 2.0 not in set(w01["avg_aqi"])


def test_chronological_split_never_leaks_future_into_train():
    out = build_training_frame(_frame(hours=20))
    train, test = chronological_split(out, 0.25)
    assert train["hour"].max() < test["hour"].min()
    assert len(train) and len(test)


def test_freshness_future_timestamp_is_not_live():
    now = datetime.now(UTC)
    assert classify_freshness(now + timedelta(hours=5, minutes=30)) == (
        FreshnessStatus.UNAVAILABLE
    )
    assert classify_freshness(now + timedelta(minutes=2)) == FreshnessStatus.LIVE
    assert classify_freshness(now - timedelta(hours=3)) == FreshnessStatus.STALE
    assert classify_freshness(None) == FreshnessStatus.UNAVAILABLE


@pytest.mark.parametrize(
    "env,flag,expected",
    [
        ("development", None, True),
        ("staging", None, True),
        ("production", None, False),
        ("production", True, True),
        ("development", False, False),
    ],
)
def test_demo_user_seeding_policy(env, flag, expected):
    s = Settings(
        ENVIRONMENT=env,
        SEED_DEMO_USERS=flag,
        SECRET_KEY="a-real-unique-secret-key-0123456789abcdef",
    )
    assert s.should_seed_demo_users is expected


@pytest.mark.asyncio
async def test_metrics_endpoint_access_policy(monkeypatch):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        monkeypatch.setattr(settings, "METRICS_TOKEN", "")
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        assert (await c.get("/api/v1/metrics")).status_code == 200

        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        assert (await c.get("/api/v1/metrics")).status_code == 404

        monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret-token")
        assert (await c.get("/api/v1/metrics")).status_code == 401
        bad = await c.get("/api/v1/metrics", headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 401
        ok = await c.get(
            "/api/v1/metrics", headers={"Authorization": "Bearer s3cret-token"}
        )
        assert ok.status_code == 200
