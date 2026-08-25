import json
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger

if TYPE_CHECKING:
    from app.api.v1.endpoints.assistant import ChatResponse


class AssistantAgent:
    """
    Natural language assistant for city administrators.
    Uses Claude via Anthropic API with tool-augmented retrieval
    to answer questions about air quality, sources, and enforcement.
    """

    SYSTEM_PROMPT = """You are an expert urban air quality analyst embedded in the Pune Air Quality Intelligence Platform.
You have access to real-time AQI data, pollution source attributions, weather data, and enforcement records.

When answering questions:
1. Always cite the specific data sources used (station names, timestamps)
2. Express confidence as a percentage based on data completeness
3. Provide actionable recommendations when relevant
4. For spatial questions, include coordinates or ward identifiers
5. Acknowledge uncertainty when data gaps exist

CRITICAL — grounding and labeling rules:
- NEVER invent a measurement, forecast value, traffic figure, or intervention impact that
  isn't present in the data context below. If the context doesn't contain what's needed to
  answer, say plainly that you don't have that data rather than estimating or guessing.
- Label every figure you cite with exactly one of these words: Observed, Predicted,
  Estimated, Simulated, or Unavailable. For example: "PM2.5 is 142 µg/m³ (Observed, Wakad
  station, 8 minutes ago)" or "Tomorrow's AQI is forecast at 165 (Predicted)".
- "Traffic" data in this platform is a synthetic time-of-day multiplier, not a live traffic
  feed — if you reference it, label it "Estimated (synthetic traffic model)", never "Observed"
  or "live".
- If asked what would happen under a hypothetical intervention (e.g. "what if traffic were
  reduced 30%"), do not state a specific AQI reduction number yourself. Point the user to the
  What-If Simulator (/dashboard/simulator) where that scenario can actually be run through the
  dispersion/impact model, and only cite a number here if a simulation result is already
  present in the data context, labeled "Simulated".

Your audience is city administrators and pollution control officers — be precise and evidence-based, not bureaucratic."""

    def __init__(self, session: AsyncSession, city: str) -> None:
        self.session = session
        self.city = city

    async def _fetch_context(self, query: str) -> dict:
        """Fetch relevant context from database based on query content."""
        context = {}
        q_lower = query.lower()

        # Always include current city AQI snapshot
        aqi_result = await self.session.execute(
            text(
                """
            SELECT s.ward_id, s.name as station_name, r.aqi, r.pm25, r.pm10, r.no2,
                   r.timestamp, r.wind_speed, r.wind_direction, r.temperature, r.humidity,
                   r.quality_flag
            FROM aqi_readings r
            JOIN monitoring_stations s ON r.station_id = s.id
            WHERE s.city = :city
              AND r.timestamp > NOW() - INTERVAL '2 hours'
              AND r.is_deleted = false
              AND r.quality_flag != 'invalid'
            ORDER BY r.timestamp DESC
            LIMIT 20
        """
            ),
            {"city": self.city},
        )
        context["current_aqi"] = [dict(row._mapping) for row in aqi_result]

        if any(
            word in q_lower
            for word in ["hotspot", "highest", "worst", "worse", "most pollut"]
        ):
            hotspot_result = await self.session.execute(
                text(
                    """
                SELECT s.ward_id, s.name as station_name, r.aqi, r.pm25, r.timestamp,
                       r.quality_flag
                FROM aqi_readings r
                JOIN monitoring_stations s ON r.station_id = s.id
                WHERE s.city = :city
                  AND r.timestamp > NOW() - INTERVAL '2 hours'
                  AND r.is_deleted = false
                  AND r.quality_flag != 'invalid'
                ORDER BY r.aqi DESC NULLS LAST
                LIMIT 5
            """
                ),
                {"city": self.city},
            )
            context["current_hotspots"] = [dict(row._mapping) for row in hotspot_result]

        if "traffic" in q_lower:
            # This platform has no live traffic feed — traffic influence is a
            # synthetic time-of-day multiplier baked into ingestion/forecast.
            # Surface that explicitly so the model never claims it as observed.
            context["traffic_data_note"] = (
                "No live traffic provider is configured in this deployment. "
                "Traffic influence on AQI/forecasts is a synthetic time-of-day "
                "multiplier (morning/evening peak factors), not a measured "
                "traffic feed. Label any reference to it as Estimated, never Observed."
            )

        if any(
            word in q_lower
            for word in [
                "source",
                "cause",
                "attribution",
                "why",
                "industrial",
                "construction",
                "traffic",
            ]
        ):
            attr_result = await self.session.execute(
                text(
                    """
                SELECT ward_id, vehicular_pct, industrial_pct, construction_pct,
                       biomass_pct, overall_confidence, contributing_sources, timestamp
                FROM pollution_attributions
                WHERE city = :city AND timestamp > NOW() - INTERVAL '3 hours'
                  AND is_deleted = false
                ORDER BY timestamp DESC
                LIMIT 10
            """
                ),
                {"city": self.city},
            )
            context["attributions"] = [dict(row._mapping) for row in attr_result]

        if any(
            word in q_lower
            for word in ["forecast", "tomorrow", "predict", "next", "will"]
        ):
            forecast_result = await self.session.execute(
                text(
                    """
                SELECT ward_id, aqi_forecast, pm25_forecast, confidence_score,
                       confidence_lower, confidence_upper, forecast_timestamp, contributing_factors
                FROM forecast_grids
                WHERE city = :city AND forecast_timestamp > NOW()
                  AND forecast_timestamp < NOW() + INTERVAL '24 hours'
                  AND is_deleted = false
                ORDER BY forecast_timestamp, ward_id
                LIMIT 30
            """
                ),
                {"city": self.city},
            )
            context["forecasts"] = [dict(row._mapping) for row in forecast_result]

        if any(
            word in q_lower
            for word in ["enforcement", "inspection", "officer", "action", "violation"]
        ):
            enf_result = await self.session.execute(
                text(
                    """
                SELECT ea.title, ea.ward_id, ea.action_type, ea.status, ea.priority_score,
                       ea.created_at, ea.outcome_score, es.name as source_name, es.source_type
                FROM enforcement_actions ea
                LEFT JOIN emission_sources es ON ea.source_id = es.id
                WHERE ea.city = :city
                  AND ea.created_at > NOW() - INTERVAL '48 hours'
                  AND ea.is_deleted = false
                ORDER BY ea.priority_score DESC
                LIMIT 10
            """
                ),
                {"city": self.city},
            )
            context["enforcement"] = [dict(row._mapping) for row in enf_result]

        if any(word in q_lower for word in ["anomal", "spike", "sudden", "alert"]):
            anomaly_result = await self.session.execute(
                text(
                    """
                SELECT ae.ward_id, ae.aqi_spike_value, ae.probable_cause, ae.confidence_score,
                       ae.detected_at, ae.is_resolved, s.name as station_name
                FROM anomaly_events ae
                JOIN monitoring_stations s ON ae.station_id = s.id
                WHERE ae.city = :city
                  AND ae.detected_at > NOW() - INTERVAL '24 hours'
                  AND ae.is_deleted = false
                ORDER BY ae.detected_at DESC
                LIMIT 5
            """
                ),
                {"city": self.city},
            )
            context["anomalies"] = [dict(row._mapping) for row in anomaly_result]

        return context

    async def respond(
        self,
        message: str,
        history: list[tuple[str, str]],
        user_role: str,
    ) -> "ChatResponse":
        import anthropic
        from anthropic import AsyncAnthropic

        from app.api.v1.endpoints.assistant import ChatResponse

        # Explicit timeout: the SDK default can be minutes long, which is far
        # too slow for an interactive chat request. Fail fast and let the
        # endpoint return a clear, actionable error rather than hang the
        # connection.
        client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=25.0)
        context = await self._fetch_context(message)

        context_str = json.dumps(context, default=str, indent=2)
        system = f"{self.SYSTEM_PROMPT}\n\nCity: {self.city}\nUser role: {user_role}\n\nCurrent data context:\n{context_str}"

        messages = []
        for role, content in history[-6:]:  # last 6 turns
            messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        try:
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                system=system,
                messages=messages,
            )
        except anthropic.APITimeoutError as e:
            logger.warning("assistant.timeout", city=self.city, error=str(e))
            raise TimeoutError("The AI assistant took too long to respond. Please try again.") from e
        except anthropic.RateLimitError as e:
            logger.warning("assistant.rate_limited", city=self.city, error=str(e))
            raise RuntimeError("The AI assistant is temporarily rate-limited. Please try again shortly.") from e
        except anthropic.APIStatusError as e:
            logger.error("assistant.api_error", city=self.city, status=e.status_code, error=str(e))
            raise RuntimeError("The AI assistant provider returned an error. Please try again.") from e
        except anthropic.APIConnectionError as e:
            logger.error("assistant.connection_error", city=self.city, error=str(e))
            raise RuntimeError("Couldn't reach the AI assistant provider. Please try again shortly.") from e

        answer_text = response.content[0].text

        # Determine confidence based on data availability
        data_points = sum(len(v) for v in context.values() if isinstance(v, list))
        confidence = min(0.95, 0.5 + (data_points * 0.02))

        # Determine map data from context
        map_data = None
        if context.get("current_aqi"):
            map_data = {
                "type": "aqi_heatmap",
                "city": self.city,
                "points": [
                    {
                        "ward_id": r.get("ward_id"),
                        "station": r.get("station_name"),
                        "aqi": r.get("aqi"),
                        "pm25": r.get("pm25"),
                    }
                    for r in context["current_aqi"]
                ],
            }

        data_sources = ["CAAQMS stations", "TimescaleDB time-series"]
        if context.get("attributions"):
            data_sources.append("Pollution attribution model v2.1")
        if context.get("forecasts"):
            data_sources.append("XGBoost forecasting model")
        if context.get("enforcement"):
            data_sources.append("Enforcement action database")
        if context.get("current_hotspots"):
            data_sources.append("Live AQI ranking (highest-AQI stations)")
        if context.get("traffic_data_note"):
            data_sources.append("Synthetic traffic model (not a live feed)")

        evidence = []
        for reading in (context.get("current_aqi") or [])[:3]:
            evidence.append(
                {
                    "type": "sensor_reading",
                    "station": reading.get("station_name"),
                    "aqi": reading.get("aqi"),
                    "timestamp": str(reading.get("timestamp")),
                }
            )

        return ChatResponse(
            answer=answer_text,
            confidence_score=round(confidence, 2),
            data_sources=data_sources,
            map_data=map_data,
            supporting_evidence=evidence,
            reasoning_trace=f"Retrieved {data_points} data points across {len(context)} categories. "
            f"Context included: {', '.join(context.keys())}.",
        )
