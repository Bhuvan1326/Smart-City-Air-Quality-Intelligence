from app.api.v1.endpoints.agents import router as agents_router
from app.api.v1.endpoints.alerts import alerts_router, attribution_router
from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.aqi import router as aqi_router
from app.api.v1.endpoints.assistant import router as assistant_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.dashboard import router as dashboard_router
from app.api.v1.endpoints.drone import router as drone_router
from app.api.v1.endpoints.enforcement import router as enforcement_router
from app.api.v1.endpoints.forecast import router as forecast_router
from app.api.v1.endpoints.gis import router as gis_router
from app.api.v1.endpoints.metrics import router as metrics_router
from app.api.v1.endpoints.notifications import router as notifications_router
from app.api.v1.endpoints.replay import router as replay_router
from app.api.v1.endpoints.reports import router as reports_router
from app.api.v1.endpoints.sensors import router as sensors_router
from app.api.v1.endpoints.simulator import router as simulator_router
from fastapi import APIRouter

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(dashboard_router)
api_router.include_router(aqi_router)
api_router.include_router(forecast_router)
api_router.include_router(attribution_router)
api_router.include_router(enforcement_router)
api_router.include_router(alerts_router)
api_router.include_router(analytics_router)
api_router.include_router(assistant_router)
api_router.include_router(agents_router)
api_router.include_router(gis_router)
api_router.include_router(simulator_router)
api_router.include_router(replay_router)
api_router.include_router(reports_router)
api_router.include_router(metrics_router)
api_router.include_router(sensors_router)
api_router.include_router(notifications_router)
api_router.include_router(drone_router)
