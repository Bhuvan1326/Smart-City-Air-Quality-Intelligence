from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-relative base dir: app/core/config.py -> app/core -> app -> backend/.
# Used only to build safe, portable *defaults* below (e.g. MODEL_REGISTRY_PATH).
# In the Docker image (Dockerfile: WORKDIR /app, COPY . .) this resolves to
# /app, reproducing the previous hard-coded path exactly. Anywhere else
# (bare-metal dev, CI runners, Windows) it resolves to wherever the backend/
# checkout actually lives, which is always writable — unlike a hard-coded
# /app that only exists inside the container.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    APP_NAME: str = "Urban Air Quality Intelligence Platform"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://airuser:airpass@localhost:5432/airquality"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 300

    # Auth
    SECRET_KEY: str = "changeme-in-production-min-32-chars-long"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    # External APIs
    OPENWEATHER_API_KEY: str = ""
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1"
    ANTHROPIC_API_KEY: str = ""
    # Satellite imagery — Copernicus Data Space Ecosystem (CDSE).
    # This is the EU-operated, genuinely free-forever tier: no credit card,
    # no trial expiry, just a monthly processing-unit quota that resets.
    # Sign up at https://dataspace.copernicus.eu (free) to get client
    # credentials for the OAuth2 client-credentials flow used below.
    # (The old commercial trial at services.sentinel-hub.com is NOT used —
    # that one is a time-limited paid-plan trial, not free.)
    SENTINEL_HUB_CLIENT_ID: str = ""
    SENTINEL_HUB_CLIENT_SECRET: str = ""
    SENTINEL_HUB_TOKEN_URL: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    SENTINEL_HUB_BASE_URL: str = "https://sh.dataspace.copernicus.eu"

    # NASA FIRMS — fully free, government-run, no card, no trial/expiry.
    # Get a MAP_KEY at https://firms.modis.gov/api/map_key/
    NASA_FIRMS_MAP_KEY: str = ""
    NASA_FIRMS_BASE_URL: str = "https://firms.modis.gov/api"
    SATELLITE_FETCH_ENABLED: bool = True
    OPENAQ_API_KEY: str = ""
    OPENAQ_BASE_URL: str = "https://api.openaq.org/v3"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000
    RATE_LIMIT_ENABLED: bool = True

    # ML
    # Overridable via the MODEL_REGISTRY_PATH env var (see .env.example).
    # Default is project-relative (see BASE_DIR above) rather than a
    # hard-coded /app, so it's writable in any environment — Docker, CI,
    # or a bare local checkout on Windows/macOS/Linux — without extra
    # configuration, while still discovering models already committed
    # under backend/ml_models/.
    MODEL_REGISTRY_PATH: str = str(BASE_DIR / "ml_models")
    FORECAST_HORIZON_HOURS: int = 72
    GRID_RESOLUTION_KM: float = 1.0

    # ── Notifications ────────────────────────────────────────────────────
    # Firebase Cloud Messaging: genuinely free forever (Spark plan), no
    # credit card required. This is the default/primary push channel.
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CREDENTIALS_JSON: str = (
        ""  # inline service-account JSON, or a path to a file
    )

    # Email (SMTP): also genuinely free at low volume via providers such as
    # Brevo (300 free emails/day, no card) or a Gmail account with an App
    # Password. Used as the free fallback channel for citizens who haven't
    # installed the app (and therefore have no push token).
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_ADDRESS: str = "alerts@urban-air-quality.local"
    SMTP_USE_TLS: bool = True

    # Twilio (SMS / IVR voice calls): NOT free. Real carrier SMS/voice
    # termination costs money on every provider — Twilio's "free trial" is
    # a finite, one-time credit, not an ongoing free tier, and after it's
    # used real sending requires a paid account. This integration is fully
    # implemented but defaults to OFF (TWILIO_ENABLED=False) so the
    # platform never silently incurs cost and runs with zero API keys.
    # Enable it deliberately once you have a funded Twilio account.
    TWILIO_ENABLED: bool = False
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    TWILIO_MESSAGING_SERVICE_SID: str = ""
    TWILIO_VOICE_CALLER_ID: str = ""
    TWILIO_STATUS_CALLBACK_URL: str = ""
    NOTIFICATIONS_ENABLED: bool = True

    # Evidence media storage — plain local disk by default, genuinely free
    # (no S3/GCS bill). Swap MEDIA_ROOT for a mounted volume in production;
    # the storage service (app.services.evidence_storage) is the only place
    # that would need to change to move to object storage later.
    MEDIA_ROOT: str = "./media"
    MEDIA_URL_PREFIX: str = "/media"
    MAX_EVIDENCE_PHOTO_MB: float = 8.0

    # Drone inspection planning
    DRONE_MAX_FLIGHT_MINUTES: int = 22
    DRONE_CRUISE_SPEED_MPS: float = 8.0
    DRONE_CAMERA_SWATH_METERS: float = 60.0
    DRONE_NO_FLY_BUFFER_METERS: float = 500.0

    # Cities supported
    SUPPORTED_CITIES: list[str] = [
        "Pune",
        "Mumbai",
        "Delhi",
        "Bengaluru",
        "Chennai",
        "Kolkata",
    ]

    # Agent settings
    AGENT_MAX_RETRIES: int = 3
    AGENT_TIMEOUT_SECONDS: int = 30

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def sync_database_url(self) -> str:
        return self.DATABASE_URL.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
