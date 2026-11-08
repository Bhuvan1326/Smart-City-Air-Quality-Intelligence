import re
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.core.config import settings
from app.core.logging import logger
from app.schemas.base import APIResponse
from app.services.insight_validation import validate_insight_response
from app.services.nugen import (
    NugenAuthenticationError,
    NugenClient,
    NugenConnectionError,
    NugenEmptyResponseError,
    NugenError,
    NugenInvalidResponseError,
    NugenNotConfiguredError,
    NugenRateLimitError,
    NugenTimeoutError,
)

router = APIRouter(prefix="/ai", tags=["Nugen AI"])

_SYSTEM_PROMPT = """You are an air-quality intelligence assistant aligned to the
Smart City Air Quality Intelligence Platform (Pune, India).
Explain air-quality conditions using ONLY the measurements and context the
user provides. Follow these rules strictly:
- NEVER invent measurement values, station names, or figures not supplied.
- The "Validated AQI category" line is AUTHORITATIVE — it is computed by the
  platform, not by you. Never restate the AQI under a different band name.
- Label every figure you cite with exactly one of: Observed, Predicted,
  Estimated, or Unavailable.
- Give health guidance and precautions; never give medical diagnoses.
- Keep the answer structured and concise: (1) condition summary,
  (2) health guidance for the requested audience, (3) actionable
  recommendations."""

# CPCB AQI bands — authoritative, computed server-side (never left to the LLM).
_AQI_BANDS = [
    (50, "Good"),
    (100, "Satisfactory"),
    (200, "Moderate"),
    (300, "Poor"),
    (400, "Very Poor"),
    (500, "Severe"),
]
# Bands at/above this AQI where outdoor-exertion endorsement is unsafe.
_STRENUOUS_UNSAFE_AQI = 201
_EXERCISE_ENDORSEMENT = (
    "safe to jog",
    "safe for jogging",
    "safe to exercise",
    "safe for exercise",
    "okay to jog",
    "fine to jog",
    "can jog",
    "go jogging",
    "outdoor exercise is safe",
    "safe for outdoor exercise",
    "safe to play",
)
_BAND_WORDS = "good|satisfactory|moderate|poor|very poor|severe"
_AQI_BAND_MENTION = re.compile(
    rf"aqi[^\n]{{0,40}}?\b({_BAND_WORDS})\b|\b({_BAND_WORDS})\b[^\n]{{0,20}}?aqi",
    re.IGNORECASE,
)
_BAND_CORRECTION_NOTE = (
    "Platform correction: the validated CPCB category for this AQI is "
    "{band} — treat that classification as authoritative over any differing "
    "label above."
)


def _check_band_contradiction(text: str, band: str | None) -> str:
    """Flag responses that restate the AQI under a different band name.

    The validated band is computed deterministically — an LLM labeling the
    same AQI differently (e.g. calling AQI 245 'Moderate') is a factual
    error, so the correction is appended rather than silently shown.
    """
    if not band:
        return text
    for m in _AQI_BAND_MENTION.finditer(text):
        mentioned = (m.group(1) or m.group(2) or "").lower()
        if mentioned and mentioned != band.lower():
            return text + "\n\n" + _BAND_CORRECTION_NOTE.format(band=band)
    return text


_DETERMINISTIC_SAFETY_NOTE = (
    "Platform safety policy note: at this validated AQI level, strenuous "
    "outdoor activity is not recommended for anyone, and all outdoor time "
    "should be minimized — especially for children, the elderly, and people "
    "with heart or lung conditions. The platform's deterministic safety "
    "policy supersedes any conflicting guidance above."
)


def _aqi_band(aqi: float | None) -> str | None:
    if aqi is None:
        return None
    for ceiling, label in _AQI_BANDS:
        if aqi <= ceiling:
            return label
    return "Severe"


def _safety_review(text: str, band: str | None, aqi: float | None) -> str:
    """Reject contradictions between model output and deterministic policy.

    If the validated band is Poor+ and the model still endorses outdoor
    exercise, the unsafe passage must not reach the user — replace the whole
    response's exercise endorsement with approved guidance appended as a
    correction note rather than silently displaying it.
    """
    text = _check_band_contradiction(text, band)
    if band is None or aqi is None or aqi < _STRENUOUS_UNSAFE_AQI:
        return text
    lowered = text.lower()
    if any(p in lowered for p in _EXERCISE_ENDORSEMENT):
        return text + "\n\n" + _DETERMINISTIC_SAFETY_NOTE
    return text


class AirQualityInsightRequest(BaseModel):
    city: str = Field(default="Pune", max_length=100)
    station: str | None = Field(default=None, max_length=200)
    ward: str | None = Field(default=None, max_length=50)
    aqi: float | None = Field(default=None, ge=0, le=1000)
    pm25: float | None = Field(default=None, ge=0, le=2000)
    pm10: float | None = Field(default=None, ge=0, le=2000)
    no2: float | None = Field(default=None, ge=0, le=2000)
    so2: float | None = Field(default=None, ge=0, le=2000)
    co: float | None = Field(default=None, ge=0, le=200)
    o3: float | None = Field(default=None, ge=0, le=2000)
    temperature_c: float | None = Field(default=None, ge=-60, le=80)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    observed_at: str | None = Field(default=None, max_length=64)
    audience: Literal["citizen", "officer", "admin"] = "citizen"
    question: str | None = Field(default=None, max_length=1000)


class AirQualityInsightResponse(BaseModel):
    insight: str
    model_id: str
    aligned: bool = True
    confidence_score: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    validation_notes: list[str] = []


def _build_user_prompt(req: AirQualityInsightRequest) -> str:
    parts = [f"City: {req.city}"]
    if req.station:
        parts.append(f"Station: {req.station}")
    if req.ward:
        parts.append(f"Ward: {req.ward}")
    measurements = {
        "AQI": req.aqi,
        "PM2.5 (µg/m³)": req.pm25,
        "PM10 (µg/m³)": req.pm10,
        "NO2 (µg/m³)": req.no2,
        "SO2 (µg/m³)": req.so2,
        "CO (mg/m³)": req.co,
        "O3 (µg/m³)": req.o3,
        "Temperature (°C)": req.temperature_c,
        "Humidity (%)": req.humidity_pct,
    }
    present = {k: v for k, v in measurements.items() if v is not None}
    parts.append(
        "Measurements (Observed): "
        + (
            ", ".join(f"{k}={v}" for k, v in present.items())
            if present
            else "none supplied"
        )
    )
    if req.observed_at:
        parts.append(f"Observed at: {req.observed_at}")
    band = _aqi_band(req.aqi)
    if band:
        parts.append(f"Validated AQI category: {band} (authoritative — do not relabel)")
    parts.append(f"Audience: {req.audience}")
    parts.append(
        "Question: "
        + (req.question or "Explain current air-quality conditions and what to do.")
    )
    return "\n".join(parts)


@router.post(
    "/air-quality-insights", response_model=APIResponse[AirQualityInsightResponse]
)
async def air_quality_insights(
    request: AirQualityInsightRequest, current_user: CurrentUser
) -> APIResponse[AirQualityInsightResponse]:
    client = NugenClient()
    try:
        result = await client.chat_completion(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(request)},
            ]
        )
    except NugenNotConfiguredError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nugen insights not configured — set NUGEN_API_KEY and "
            "NUGEN_ALIGNED_MODEL_ID",
        ) from e
    except NugenAuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nugen authentication failed — check NUGEN_API_KEY",
        ) from e
    except NugenRateLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Nugen rate limit reached — retry shortly",
        ) from e
    except (NugenTimeoutError, NugenConnectionError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nugen service unreachable — try again later",
        ) from e
    except (NugenEmptyResponseError, NugenInvalidResponseError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nugen returned an unusable response",
        ) from e
    except NugenError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nugen inference failed",
        ) from e
    finally:
        await client.aclose()

    supplied = {
        k: v
        for k, v in {
            "pm25": request.pm25,
            "pm10": request.pm10,
            "no2": request.no2,
            "so2": request.so2,
            "co": request.co,
            "o3": request.o3,
        }.items()
        if v is not None
    }
    reviewed = _safety_review(result.content, _aqi_band(request.aqi), request.aqi)
    validated = validate_insight_response(
        reviewed, supplied, request.aqi, band=_aqi_band(request.aqi)
    )
    logger.info(
        "nugen.insight_served",
        model=result.model,
        confidence=result.confidence_score,
        audience=request.audience,
        user=str(current_user.id),
        validation_issues=len(validated.notes),
        fallback=validated.fallback_used,
    )
    return APIResponse(
        data=AirQualityInsightResponse(
            insight=validated.text,
            validation_notes=validated.notes,
            model_id=result.model,
            aligned=True,
            confidence_score=result.confidence_score,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        ),
        message="Insight generated by Nugen-aligned model",
    )


class NugenStatusResponse(BaseModel):
    configured: bool
    model_id: str | None
    deployment_status: str | None
    error: str | None


@router.get("/nugen-status", response_model=APIResponse[NugenStatusResponse])
async def nugen_status(
    current_user: CurrentUser,
) -> APIResponse[NugenStatusResponse]:
    model_id = settings.NUGEN_ALIGNED_MODEL_ID or None
    if not settings.NUGEN_API_KEY:
        return APIResponse(
            data=NugenStatusResponse(
                configured=False,
                model_id=model_id,
                deployment_status=None,
                error="NUGEN_API_KEY not set",
            ),
            message="Nugen not configured",
        )
    if not model_id:
        return APIResponse(
            data=NugenStatusResponse(
                configured=True,
                model_id=None,
                deployment_status=None,
                error="NUGEN_ALIGNED_MODEL_ID not set — run the alignment pipeline",
            ),
            message="Nugen key configured, no aligned model configured",
        )

    client = NugenClient()
    try:
        status_info = await client.deployment_status(model_id)
        return APIResponse(
            data=NugenStatusResponse(
                configured=True,
                model_id=model_id,
                deployment_status=status_info.get("status"),
                error=status_info.get("error"),
            ),
            message="Nugen deployment status",
        )
    except NugenError as e:
        return APIResponse(
            data=NugenStatusResponse(
                configured=True,
                model_id=model_id,
                deployment_status=None,
                error=str(e)[:200],
            ),
            message="Nugen status check failed",
        )
    finally:
        await client.aclose()
