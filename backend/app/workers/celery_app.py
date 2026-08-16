from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "air_quality_workers",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks.aqi_ingestion",
        "app.workers.tasks.forecast",
        "app.workers.tasks.anomaly_detection",
        "app.workers.tasks.attribution",
        "app.workers.tasks.alerts",
        "app.workers.tasks.satellite",
        "app.workers.tasks.notifications",
        "app.workers.tasks.drone",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "fetch-live-aqi": {
            "task": "app.workers.tasks.aqi_ingestion.fetch_live_aqi_all_cities",
            "schedule": 300,  # every 5 minutes
        },
        "fetch-weather": {
            "task": "app.workers.tasks.aqi_ingestion.fetch_weather_data",
            "schedule": 1800,  # every 30 minutes
        },
        "regenerate-forecasts": {
            "task": "app.workers.tasks.forecast.regenerate_ward_forecasts",
            "schedule": 3600,  # every hour
        },
        "run-anomaly-detection": {
            "task": "app.workers.tasks.anomaly_detection.detect_anomalies",
            "schedule": 300,  # every 5 minutes
        },
        "run-attribution": {
            "task": "app.workers.tasks.attribution.compute_attribution",
            "schedule": 3600,  # every hour
        },
        "midnight-retraining": {
            "task": "app.workers.tasks.forecast.trigger_model_retraining",
            "schedule": crontab(hour=0, minute=30),
        },
        "maintenance-prediction": {
            "task": "app.workers.tasks.anomaly_detection.predict_sensor_maintenance",
            "schedule": crontab(hour=6, minute=0),
        },
        "fetch-satellite-features": {
            "task": "app.workers.tasks.satellite.fetch_satellite_features",
            "schedule": crontab(
                hour="*/6", minute=15
            ),  # every 6 hours (satellite revisit-time appropriate)
        },
        "dispatch-pending-alerts": {
            "task": "app.workers.tasks.notifications.dispatch_pending_alerts",
            "schedule": 60,  # every minute — alerts should go out promptly
        },
        "detect-drone-hotspots": {
            "task": "app.workers.tasks.drone.detect_hotspots_and_plan",
            "schedule": crontab(
                hour=7, minute=0
            ),  # once daily, ahead of the inspection shift
        },
    },
)
