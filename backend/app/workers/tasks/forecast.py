import asyncio
from datetime import UTC, datetime, timedelta

import numpy as np

from app.core.config import settings
from app.core.logging import logger
from app.services.dispersion import DispersionForecastAdjustment
from app.workers.celery_app import celery_app

PUNE_WARDS = ["W01", "W02", "W03", "W04", "W05", "W06", "W07", "W08"]

WARD_COORDS = {
    "W01": (18.5074, 73.8077),
    "W02": (18.5308, 73.8475),
    "W03": (18.5089, 73.9259),
    "W04": (18.6298, 73.7997),
    "W05": (18.4530, 73.8618),
    "W06": (18.5989, 73.7601),
    "W07": (18.4968, 73.8126),
    "W08": (18.5559, 73.9007),
}


def _load_latest_model():
    """
    Load the most recently trained XGBoost model from the registry (see
    trigger_model_retraining below, which writes one nightly). Returns None
    if no model has been trained yet, in which case callers fall back to
    the pure statistical forecast — the model is trained as a *1-hour-ahead*
    predictor (see _retrain_async's target_aqi = avg_aqi.shift(-1)), so
    multi-step (72h) use requires recursive prediction — see
    _statistical_forecast's use of it below.

    Note: previously this feature-vector/model-loading path existed
    (_build_forecast_features) but nothing in this task ever actually
    called model.predict() — forecasts were always purely statistical
    regardless of whether a trained model existed. This closes that gap.
    """
    import glob

    pattern = f"{settings.MODEL_REGISTRY_PATH}/xgb_forecast_*.joblib"
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    try:
        import joblib

        return joblib.load(files[-1])
    except Exception as e:  # noqa: BLE001 -- ML load optional, has fallback
        logger.warning("forecast.model_load_failed", error=str(e))
        return None


def _build_forecast_features(
    current_aqi: float, hour: int, day_of_week: int, ward: str
) -> np.ndarray:
    """
    Build the feature vector for the trained XGBoost model. Must exactly
    match the feature order used in _retrain_async's `feature_cols`:
    [avg_aqi, hour_of_day, day_of_week, is_weekend, is_industrial,
     avg_temp, avg_humidity, avg_wind]. Temperature/humidity/wind aren't
    available per-forecast-hour here (we don't have an hours-ahead weather
    forecast), so climatological placeholders are used for those three —
    documented explicitly rather than silently passing zeros, which would
    look like a real (freezing, bone-dry, dead-calm) observation to the model.
    """
    is_weekend = int(day_of_week >= 5)
    is_industrial = int(ward in ("W04", "W03"))
    # Placeholder climatology for Pune — used only because no hours-ahead
    # weather forecast is available; a real deployment should replace this
    # with an actual weather forecast feed (e.g. Open-Meteo's hourly forecast).
    placeholder_temp = 26.0
    placeholder_humidity = 55.0
    placeholder_wind = 3.0

    return np.array(
        [
            [
                current_aqi,
                hour,
                day_of_week,
                is_weekend,
                is_industrial,
                placeholder_temp,
                placeholder_humidity,
                placeholder_wind,
            ]
        ]
    )


def _statistical_forecast(
    current_aqi: float,
    hours_ahead: int,
    ward: str,
    dispersion: DispersionForecastAdjustment | None = None,
    model=None,
) -> list[dict]:
    """
    Forecast using historical diurnal patterns, optionally blended with a
    trained XGBoost model's recursive multi-step prediction when one is
    available in the registry (see _load_latest_model).

    The model is trained as a 1-hour-ahead predictor, so multi-step use
    here is recursive: at each hour h, the model's own prediction from h-1
    (falling back to the statistical estimate for h=1) is fed back in as
    "current_aqi" for the next step. Recursive forecasts compound error
    with lookahead distance, so the model's weight in the blend is decayed
    toward the (bounded, mean-reverting) statistical estimate as h grows —
    an unconstrained recursive XGBoost forecast can drift arbitrarily far
    from plausible AQI values over 72 hours if given full weight throughout.

    `dispersion`, when provided (see app.services.dispersion.DispersionModel,
    computed from the current wind observation), adds a physically-grounded
    cross-ward transport term on top of the diurnal baseline — PM2.5 and
    PM10 get their own transport deltas since PM10 settles out of the
    plume faster over distance. The transport estimate is only computed
    from the *current* wind reading, so its influence is decayed with
    lookahead hours (we don't have an hours-ahead wind forecast to redo the
    plume calculation against) rather than held constant across all 72
    hours, which would overstate confidence in a stale wind snapshot.
    """
    forecasts = []
    now = datetime.now(UTC)
    recursive_aqi = (
        current_aqi  # fed back in as "current_aqi" for the model at each step
    )

    for h in range(1, hours_ahead + 1):
        target_time = now + timedelta(hours=h)
        hour = target_time.hour
        dow = target_time.weekday()

        # Diurnal pattern: peaks at rush hours
        traffic_mult = 1.0
        if 7 <= hour <= 10 or 17 <= hour <= 20:
            traffic_mult = 1.4
        elif 0 <= hour <= 5:
            traffic_mult = 0.65
        if dow >= 5:
            traffic_mult *= 0.8

        base = current_aqi * traffic_mult
        noise = np.random.normal(0, base * 0.08)
        statistical_aqi = max(10, int(base + noise))

        model_weight = 0.0
        if model is not None:
            try:
                features = _build_forecast_features(recursive_aqi, hour, dow, ward)
                model_aqi = float(model.predict(features)[0])
                model_aqi = max(
                    10.0, min(model_aqi, 500.0)
                )  # AQI is bounded 0-500; clip runaway recursive drift
                # Model gets full weight at h=1 (least compounded error),
                # decaying to the bounded statistical estimate by h=24 —
                # beyond a day, an unconstrained recursive 1-step model's
                # compounded error is no longer a trustworthy contribution.
                model_weight = max(0.0, 1.0 - (h - 1) / 24)
                forecast_aqi = int(
                    model_aqi * model_weight + statistical_aqi * (1 - model_weight)
                )
                recursive_aqi = model_aqi  # next step's model input is this step's model output, not the blend
            except Exception as e:  # noqa: BLE001 -- ML predict optional, has fallback
                logger.warning(
                    "forecast.model_predict_failed",
                    ward=ward,
                    hour_ahead=h,
                    error=str(e),
                )
                forecast_aqi = statistical_aqi
                recursive_aqi = statistical_aqi
        else:
            forecast_aqi = statistical_aqi
            recursive_aqi = statistical_aqi

        # Confidence degrades with lookahead
        confidence = max(0.55, 0.92 - (h * 0.005))

        dispersion_pm25_delta = 0.0
        dispersion_pm10_delta = 0.0
        if dispersion is not None:
            # exp decay: full weight at h=1, ~37% at h=12, negligible by h=48+ —
            # a snapshot wind reading shouldn't be trusted to predict transport
            # three days out.
            decay = float(np.exp(-h / 12))
            dispersion_pm25_delta = dispersion.pm25_transport_delta * decay
            dispersion_pm10_delta = dispersion.pm10_transport_delta * decay
            # Fold the PM2.5 transport delta into the headline AQI number
            # too (PM2.5 is usually the AQI-determining pollutant in Indian
            # cities), scaled down since AQI isn't a 1:1 function of PM2.5 concentration.
            forecast_aqi = max(10, int(forecast_aqi + dispersion_pm25_delta * 0.6))
            confidence = max(0.4, confidence - dispersion.confidence_penalty * decay)

        margin = int(forecast_aqi * (1 - confidence) * 1.5)
        contributing = {
            "traffic": round(traffic_mult * 0.35, 2),
            "weather": round(0.25, 2),
            "industrial": round(0.20 if ward in ("W03", "W04") else 0.10, 2),
            "seasonal": round(0.15, 2),
        }
        if dispersion is not None:
            contributing["cross_ward_dispersion"] = round(
                min(0.5, abs(dispersion_pm25_delta) / max(forecast_aqi, 1)), 2
            )

        feature_importance = {
            "current_aqi": 0.38,
            "hour_of_day": 0.22,
            "day_of_week": 0.12,
            "ward_type": 0.18,
            "weather": 0.10,
        }
        if model is not None:
            feature_importance["trained_model_weight"] = round(model_weight, 2)

        entry = {
            "ward_id": ward,
            "hours_ahead": h,
            "forecast_timestamp": target_time,
            "aqi_forecast": forecast_aqi,
            "pm25_forecast": round(forecast_aqi * 0.55 + dispersion_pm25_delta, 1),
            "pm10_forecast": round(forecast_aqi * 1.1 + dispersion_pm10_delta, 1),
            "confidence_score": round(confidence, 3),
            "confidence_lower": max(0, forecast_aqi - margin),
            "confidence_upper": forecast_aqi + margin,
            "contributing_factors": contributing,
            "feature_importance": feature_importance,
        }
        if dispersion is not None and h == 1:
            # Attach full dispersion reasoning/evidence only on the
            # first-hour entry (where it's most relevant and the wind
            # snapshot is least stale) rather than repeating it 72 times.
            entry["contributing_factors"]["dispersion_detail"] = {
                "stability_class": dispersion.stability_class.value,
                "wind_speed_mps": dispersion.wind_speed_mps,
                "wind_direction_deg": dispersion.wind_direction_deg,
                "upwind_ward_count": len(dispersion.contributing_wards),
                "reasoning": dispersion.reasoning,
            }

        forecasts.append(entry)

    return forecasts


async def _get_ward_coords_for_city(
    session, city: str
) -> dict[str, tuple[float, float]]:
    """Ward centroid coordinates derived from that city's actual monitoring
    stations (avg station lat/lon per ward). Used instead of the Pune-only
    WARD_COORDS table so dispersion/geometry math is correct for every
    city, not just Pune.
    """
    from sqlalchemy import text

    result = await session.execute(
        text("""
            SELECT ward_id, AVG(latitude) AS lat, AVG(longitude) AS lon
            FROM monitoring_stations
            WHERE city = :city AND ward_id IS NOT NULL AND is_deleted = false
            GROUP BY ward_id
            """),
        {"city": city},
    )
    return {row.ward_id: (float(row.lat), float(row.lon)) for row in result}


async def compute_live_ward_forecast(
    session, city: str, ward_id: str, hours_ahead: int = 72
) -> dict | None:
    """
    Compute a forecast for a single ward RIGHT NOW from the current AQI/wind
    observations, bypassing the hourly ForecastGrid table and Redis cache
    that the scheduled `regenerate_ward_forecasts` task populates.

    This exists so the frontend's Forecast page "Refresh" button can do a
    real regeneration on demand (per the platform requirement that refresh
    buttons must actually re-fetch/recompute, not just re-render cached
    data) without waiting for the next hourly Celery Beat run. It reuses
    the exact same `_statistical_forecast` / dispersion / model-loading
    logic as the scheduled task so the two code paths can't drift apart -
    this call is just not persisted to `forecast_grids`.

    Returns None if there's no current AQI reading for this ward at all
    (nothing to forecast from) - the caller should surface that as
    "no current data available", not a fabricated forecast.
    """
    from sqlalchemy import text

    from app.services.dispersion import DispersionModel

    result = await session.execute(
        text("""
            SELECT s.ward_id, AVG(r.aqi) as avg_aqi
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp > NOW() - INTERVAL '1 hour'
              AND r.is_deleted = false AND r.quality_flag != 'invalid'
              AND s.ward_id IS NOT NULL
            GROUP BY s.ward_id
            """),
        {"city": city},
    )
    ward_aqi = {row.ward_id: float(row.avg_aqi) for row in result}

    if ward_id not in ward_aqi:
        return None

    ward_coords = await _get_ward_coords_for_city(session, city)

    wind_result = await session.execute(text("""
            SELECT AVG(wind_speed) AS avg_wind_speed, AVG(wind_direction) AS avg_wind_direction
            FROM aqi_readings
            WHERE timestamp > NOW() - INTERVAL '1 hour'
              AND is_deleted = false AND wind_speed IS NOT NULL AND wind_direction IS NOT NULL
            """))
    wind_row = wind_result.first()
    wind_speed = (
        float(wind_row.avg_wind_speed) if wind_row and wind_row.avg_wind_speed else None
    )
    wind_direction = (
        float(wind_row.avg_wind_direction)
        if wind_row and wind_row.avg_wind_direction
        else None
    )

    dispersion_adjustment = None
    if wind_speed is not None and wind_direction is not None and len(ward_aqi) >= 2:
        dispersion_model = DispersionModel()
        dispersion_adjustment = dispersion_model.compute_ward_adjustment(
            target_ward_id=ward_id,
            target_coords=ward_coords.get(ward_id, (18.52, 73.85)),
            ward_aqi=ward_aqi,
            ward_coords=ward_coords,
            wind_speed_mps=wind_speed,
            wind_direction_deg=wind_direction,
            hour=datetime.now(UTC).hour,
        )

    model = _load_latest_model()
    model_version = "xgb-v1.0-recursive" if model is not None else "statistical-v1.0"

    current_aqi = ward_aqi[ward_id]
    forecasts = _statistical_forecast(
        current_aqi,
        hours_ahead,
        ward_id,
        dispersion=dispersion_adjustment,
        model=model,
    )

    return {
        "current_aqi": current_aqi,
        "model_version": model_version,
        "generated_at": datetime.now(UTC),
        "forecasts": forecasts,
    }


@celery_app.task(name="app.workers.tasks.forecast.regenerate_ward_forecasts", bind=True)
def regenerate_ward_forecasts(self):
    asyncio.run(_forecast_async())


async def _forecast_async():
    from geoalchemy2.elements import WKTElement
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.enforcement import ForecastGrid
    from app.services.dispersion import DispersionModel

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSession() as session:
        cities_result = await session.execute(
            text(
                "SELECT DISTINCT city FROM monitoring_stations WHERE is_deleted = false"
            )
        )
        cities = [row.city for row in cities_result]

        total_grids = 0
        total_wards = 0

        for city in cities:
            result = await session.execute(
                text("""
                SELECT s.ward_id, AVG(r.aqi) as avg_aqi
                FROM aqi_readings r
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE s.city = :city
                  AND r.timestamp > NOW() - INTERVAL '1 hour'
                  AND r.is_deleted = false AND r.quality_flag != 'invalid'
                  AND s.ward_id IS NOT NULL
                GROUP BY s.ward_id
            """),
                {"city": city},
            )
            ward_aqi = {
                row.ward_id: float(row.avg_aqi)
                for row in result
                if row.avg_aqi is not None
            }
            if not ward_aqi:
                # No current readings for this city — nothing to forecast
                # from; skip rather than fabricating placeholder AQI.
                continue

            ward_coords = await _get_ward_coords_for_city(session, city)

            # City-wide wind observation (average of the most recent
            # readings across this city's stations) — the standard
            # simplification for hourly city-scale dispersion when a full
            # per-ward met network isn't available. See
            # app.services.dispersion module docstring.
            wind_result = await session.execute(
                text("""
                SELECT AVG(r.wind_speed) AS avg_wind_speed, AVG(r.wind_direction) AS avg_wind_direction
                FROM aqi_readings r
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE s.city = :city
                  AND r.timestamp > NOW() - INTERVAL '1 hour'
                  AND r.is_deleted = false AND r.wind_speed IS NOT NULL AND r.wind_direction IS NOT NULL
            """),
                {"city": city},
            )
            wind_row = wind_result.first()
            wind_speed = (
                float(wind_row.avg_wind_speed)
                if wind_row and wind_row.avg_wind_speed
                else None
            )
            wind_direction = (
                float(wind_row.avg_wind_direction)
                if wind_row and wind_row.avg_wind_direction
                else None
            )

            dispersion_model = DispersionModel()
            current_hour = datetime.now(UTC).hour
            dispersion_by_ward: dict[str, object] = {}
            if (
                wind_speed is not None
                and wind_direction is not None
                and len(ward_aqi) >= 2
            ):
                for ward in ward_aqi:
                    if ward not in ward_coords:
                        continue
                    dispersion_by_ward[ward] = dispersion_model.compute_ward_adjustment(
                        target_ward_id=ward,
                        target_coords=ward_coords[ward],
                        ward_aqi=ward_aqi,
                        ward_coords=ward_coords,
                        wind_speed_mps=wind_speed,
                        wind_direction_deg=wind_direction,
                        hour=current_hour,
                    )
                logger.info(
                    "forecast.dispersion_computed",
                    city=city,
                    wind_speed=round(wind_speed, 1),
                    wind_direction=round(wind_direction, 1),
                    wards=len(dispersion_by_ward),
                )
            else:
                logger.info(
                    "forecast.dispersion_skipped",
                    city=city,
                    reason="insufficient wind or ward data",
                )

            generated_at = datetime.now(UTC)
            grids = []

            forecast_model = _load_latest_model()
            model_version = (
                "xgb-v1.0-recursive"
                if forecast_model is not None
                else "statistical-v1.0"
            )
            logger.info(
                "forecast.model_status",
                city=city,
                model_loaded=forecast_model is not None,
                version=model_version,
            )

            for ward, current_aqi in ward_aqi.items():
                forecasts = _statistical_forecast(
                    current_aqi,
                    72,
                    ward,
                    dispersion=dispersion_by_ward.get(ward),
                    model=forecast_model,
                )

                lat, lon = ward_coords.get(ward, (18.52, 73.85))
                delta = 0.01
                geom = WKTElement(
                    f"POLYGON(({lon-delta} {lat-delta}, {lon+delta} {lat-delta}, "
                    f"{lon+delta} {lat+delta}, {lon-delta} {lat+delta}, {lon-delta} {lat-delta}))",
                    srid=4326,
                )

                for fc in forecasts:
                    grid = ForecastGrid(
                        city=city,
                        ward_id=ward,
                        grid_geometry=geom,
                        forecast_timestamp=fc["forecast_timestamp"],
                        generated_at=generated_at,
                        aqi_forecast=fc["aqi_forecast"],
                        pm25_forecast=fc["pm25_forecast"],
                        pm10_forecast=fc["pm10_forecast"],
                        confidence_score=fc["confidence_score"],
                        confidence_lower=fc["confidence_lower"],
                        confidence_upper=fc["confidence_upper"],
                        model_version=model_version,
                        contributing_factors=fc["contributing_factors"],
                        feature_importance=fc["feature_importance"],
                    )
                    grids.append(grid)

            session.add_all(grids)
            total_grids += len(grids)
            total_wards += len(ward_aqi)

        await session.commit()
        logger.info(
            "forecast.regenerated",
            cities=len(cities),
            wards=total_wards,
            total_grids=total_grids,
        )

    await engine.dispose()


@celery_app.task(name="app.workers.tasks.forecast.trigger_model_retraining")
def trigger_model_retraining():
    """Trigger nightly model retraining pipeline."""
    logger.info("model_retraining.triggered")
    asyncio.run(_retrain_async())


async def _retrain_async():
    """
    Pull 90 days of AQI history, engineer features,
    retrain XGBoost model, evaluate, and save to registry.
    In production this writes a versioned joblib file.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    async with AsyncSession() as session:
        result = await session.execute(text("""
            SELECT
                time_bucket('1 hour', r.timestamp) AS hour,
                s.ward_id,
                AVG(r.aqi) AS avg_aqi,
                AVG(r.pm25) AS avg_pm25,
                AVG(r.temperature) AS avg_temp,
                AVG(r.humidity) AS avg_humidity,
                AVG(r.wind_speed) AS avg_wind
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = 'Pune'
              AND r.timestamp > NOW() - INTERVAL '90 days'
              AND r.is_deleted = false
              AND r.quality_flag != 'invalid'
              AND s.ward_id IS NOT NULL
            GROUP BY hour, s.ward_id
            ORDER BY hour
        """))
        rows = result.fetchall()
        logger.info("model_retraining.data_loaded", records=len(rows))

        if len(rows) < 100:
            logger.warning("model_retraining.insufficient_data", records=len(rows))
            return

        # Feature engineering
        import pandas as pd

        df = pd.DataFrame(
            rows,
            columns=[
                "hour",
                "ward_id",
                "avg_aqi",
                "avg_pm25",
                "avg_temp",
                "avg_humidity",
                "avg_wind",
            ],
        )
        df["hour_of_day"] = pd.to_datetime(df["hour"]).dt.hour
        df["day_of_week"] = pd.to_datetime(df["hour"]).dt.dayofweek
        df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
        df["is_industrial"] = df["ward_id"].isin(["W03", "W04"]).astype(int)
        df["target_aqi"] = df["avg_aqi"].shift(-1)
        df = df.dropna()

        feature_cols = [
            "avg_aqi",
            "hour_of_day",
            "day_of_week",
            "is_weekend",
            "is_industrial",
            "avg_temp",
            "avg_humidity",
            "avg_wind",
        ]
        X = df[feature_cols].values
        y = df["target_aqi"].values

        from sklearn.model_selection import train_test_split

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        import xgboost as xgb

        model = xgb.XGBRegressor(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

        from sklearn import metrics

        y_pred = model.predict(X_test)
        mae = metrics.mean_absolute_error(y_test, y_pred)
        rmse = metrics.root_mean_squared_error(y_test, y_pred)

        logger.info("model_retraining.complete", mae=round(mae, 2), rmse=round(rmse, 2))

        import os

        import joblib

        os.makedirs(settings.MODEL_REGISTRY_PATH, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
        model_path = f"{settings.MODEL_REGISTRY_PATH}/xgb_forecast_{timestamp}.joblib"
        joblib.dump(model, model_path)
        logger.info("model_retraining.saved", path=model_path)

    await engine.dispose()
