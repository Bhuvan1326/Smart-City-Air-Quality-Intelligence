from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import nugen as nugen_module
from app.services.nugen import (
    NugenAuthenticationError,
    NugenClient,
    NugenEmptyResponseError,
    NugenInvalidResponseError,
    NugenNotConfiguredError,
    NugenRateLimitError,
    NugenTimeoutError,
)


def _response(status: int, payload: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status, json=payload or {}, request=httpx.Request("GET", "http://t")
    )


def _client(api_key: str = "k", handler=None) -> NugenClient:
    transport = httpx.MockTransport(handler or (lambda r: _response(200, {})))
    return NugenClient(
        api_key=api_key,
        base_url="http://nugen.test",
        client=httpx.AsyncClient(transport=transport, base_url="http://nugen.test"),
    )


def _completion_payload(text: str = "insight text", model: str = "model_abc"):
    return {
        "id": "cmpl-1",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "confidence_score": 0.87,
        "usage": {"prompt_tokens": 50, "completion_tokens": 40},
    }


class TestChatCompletion:
    @pytest.fixture(autouse=True)
    def _model_id(self, monkeypatch):
        monkeypatch.setattr(
            nugen_module.settings, "NUGEN_ALIGNED_MODEL_ID", "model_test"
        )

    async def test_not_configured_raises(self, monkeypatch):
        monkeypatch.setattr(nugen_module.settings, "NUGEN_API_KEY", "")
        client = _client(api_key="")
        with pytest.raises(NugenNotConfiguredError):
            await client.chat_completion([{"role": "user", "content": "hi"}])

    async def test_success_returns_validated_result(self, monkeypatch):
        monkeypatch.setattr(
            nugen_module.settings, "NUGEN_ALIGNED_MODEL_ID", "model_abc"
        )
        client = _client(handler=lambda r: _response(200, _completion_payload()))
        result = await client.chat_completion([{"role": "user", "content": "explain"}])
        assert result.content == "insight text"
        assert result.model == "model_abc"
        assert result.confidence_score == 0.87
        assert result.completion_tokens == 40

    async def test_auth_error(self):
        client = _client(handler=lambda r: _response(401, {"error": "bad key"}))
        with pytest.raises(NugenAuthenticationError):
            await client.chat_completion([{"role": "user", "content": "x"}])

    async def test_rate_limit_exhausts_retries(self):
        calls = []

        def handler(r):
            calls.append(r)
            return _response(429, {"error": "slow down"})

        client = _client(handler=handler)
        with pytest.raises(NugenRateLimitError):
            await client.chat_completion([{"role": "user", "content": "x"}])
        assert len(calls) == 3  # 1 + 2 retries

    async def test_timeout_maps_to_error(self):
        def handler(r):
            raise httpx.ReadTimeout("slow", request=r)

        client = _client(handler=handler)
        with pytest.raises(NugenTimeoutError):
            await client.chat_completion([{"role": "user", "content": "x"}])

    async def test_missing_choices_is_invalid_response(self):
        client = _client(handler=lambda r: _response(200, {"model": "m"}))
        with pytest.raises(NugenInvalidResponseError):
            await client.chat_completion([{"role": "user", "content": "x"}])

    async def test_empty_content_rejected(self):
        client = _client(
            handler=lambda r: _response(200, _completion_payload(text="  "))
        )
        with pytest.raises(NugenEmptyResponseError):
            await client.chat_completion([{"role": "user", "content": "x"}])

    async def test_4xx_surfaces_detail_not_retried(self):
        calls = []

        def handler(r):
            calls.append(r)
            return _response(404, {"error": "model not found"})

        client = _client(handler=handler)
        with pytest.raises(nugen_module.NugenError, match="404"):
            await client.chat_completion([{"role": "user", "content": "x"}])
        assert len(calls) == 1

    async def test_bearer_header_sent(self):
        seen = {}

        def handler(r):
            seen["auth"] = r.headers.get("authorization")
            return _response(200, _completion_payload())

        client = _client(api_key="secret-key-123", handler=handler)
        await client.chat_completion([{"role": "user", "content": "x"}])
        assert seen["auth"] == "Bearer secret-key-123"


class TestAqiSafetyPolicy:
    @pytest.mark.parametrize(
        "aqi,band",
        [
            (35, "Good"),
            (75, "Satisfactory"),
            (165, "Moderate"),
            (245, "Poor"),
            (350, "Very Poor"),
            (450, "Severe"),
            (None, None),
        ],
    )
    def test_aqi_band_classification(self, aqi, band):
        from app.api.v1.endpoints.nugen_insights import _aqi_band

        assert _aqi_band(aqi) == band

    def test_aqi_245_is_poor_never_moderate(self):
        from app.api.v1.endpoints.nugen_insights import _aqi_band

        assert _aqi_band(245) == "Poor"

    def test_exercise_endorsement_corrected_at_poor(self):
        from app.api.v1.endpoints.nugen_insights import _safety_review

        unsafe = "Air quality is acceptable — it is safe to jog this morning."
        corrected = _safety_review(unsafe, "Poor", 245)
        assert "Platform safety policy note" in corrected
        assert "not recommended" in corrected

    def test_endorsement_allowed_at_good_aqi(self):
        from app.api.v1.endpoints.nugen_insights import _safety_review

        safe = "AQI 42 is Good (Observed) — outdoor activity is fine."
        assert _safety_review(safe, "Good", 42) == safe

    def test_no_note_when_no_endorsement(self):
        from app.api.v1.endpoints.nugen_insights import _safety_review

        cautious = "Stay indoors, AQI 245 is Poor (Observed)."
        assert _safety_review(cautious, "Poor", 245) == cautious

    def test_validated_band_in_prompt(self):
        from app.api.v1.endpoints.nugen_insights import (
            AirQualityInsightRequest,
            _build_user_prompt,
        )

        req = AirQualityInsightRequest(city="Pune", aqi=245)
        assert "Validated AQI category: Poor" in _build_user_prompt(req)


class TestInsightValidation:
    def _v(self, text, supplied=None, aqi=None):
        from app.services.insight_validation import validate_insight_response

        return validate_insight_response(text, supplied or {}, aqi)

    def test_aqi_not_confused_with_pm25(self):
        r = self._v("PM2.5 is 245 µg/m³.", supplied={"pm25": 98.0}, aqi=245.0)
        assert "245" not in r.text
        assert "98" in r.text

    def test_pm_values_preserved_when_correct(self):
        r = self._v(
            "PM2.5 is 98 µg/m³ and PM10 is 141 µg/m³.",
            supplied={"pm25": 98.0, "pm10": 141.0},
            aqi=245.0,
        )
        assert r.text == "PM2.5 is 98 µg/m³ and PM10 is 141 µg/m³."
        assert not r.notes

    def test_swapped_pm_values_fixed_in_place(self):
        r = self._v(
            "PM2.5 is 141 µg/m³ and PM10 is 98 µg/m³.",
            supplied={"pm25": 98.0, "pm10": 141.0},
            aqi=245.0,
        )
        assert "PM2.5 is 141" not in r.text
        assert "PM10 is 98" not in r.text
        assert "98" in r.text and "141" in r.text

    def test_wrong_aqi_replaced(self):
        r = self._v("AQI is 200.", supplied={}, aqi=245.0)
        assert "200" not in r.text
        assert "245" in r.text

    def test_mg_unit_replaced_for_pm(self):
        r = self._v("PM2.5 is 98 mg/m³.", supplied={"pm25": 98.0}, aqi=245.0)
        assert "mg/m" not in r.text
        assert "µg/m" in r.text

    def test_ug_unit_not_touched(self):
        r = self._v("PM2.5 is 98 µg/m³.", supplied={"pm25": 98.0}, aqi=245.0)
        assert "µg/m" in r.text and not r.notes

    def test_aqi_with_unit_removed(self):
        r = self._v("AQI is 245 µg/m³.", supplied={}, aqi=245.0)
        assert "µg/m" not in r.text
        assert "245" in r.text

    def test_missing_data_fabricated_aqi_replaced(self):
        r = self._v("The AQI is 200, which is Severe.")
        assert r.fallback_used is True
        assert "unavailable" in r.text.lower()
        assert "AQI is 200" not in r.text

    def test_missing_data_clean_response_passes(self):
        r = self._v(
            "No measurements were provided, so current conditions are "
            "unavailable. CPCB bands range from Good to Severe."
        )
        assert r.fallback_used is False
        assert not r.notes

    def test_invented_pollutant_sentence_removed(self):
        r = self._v(
            "PM2.5 is 50 µg/m³. O3 is 88 µg/m³.",
            supplied={"pm25": 50.0},
            aqi=100.0,
        )
        assert "88" not in r.text
        assert "PM2.5 is 50" in r.text

    def test_legitimate_band_numbers_not_touched(self):
        r = self._v(
            "AQI 245 is Poor (Observed), in the 201-300 band.",
            supplied={"pm25": 98.0},
            aqi=245.0,
        )
        assert "201-300" in r.text
        assert not r.notes

    def test_partial_data_missing_pm10_stays_missing(self):
        r = self._v("PM2.5 is 98 µg/m³.", supplied={"pm25": 98.0}, aqi=245.0)
        assert "PM10" not in r.text


class TestEndpoint:
    # Tests using the db_session-backed `client`/`auth_headers` fixtures
    # require real PostgreSQL (project integration-test convention).

    def test_unauthenticated_rejected(self):
        from fastapi.testclient import TestClient

        from app.main import app

        resp = TestClient(app).post(
            "/api/v1/ai/air-quality-insights", json={"city": "Pune", "aqi": 120}
        )
        assert resp.status_code == 403

    @pytest.mark.integration
    async def test_503_when_unconfigured(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(nugen_module.settings, "NUGEN_API_KEY", "")
        monkeypatch.setattr(nugen_module.settings, "NUGEN_ALIGNED_MODEL_ID", "")
        resp = await client.post(
            "/api/v1/ai/air-quality-insights",
            json={"city": "Pune", "aqi": 120},
            headers=auth_headers,
        )
        assert resp.status_code == 503

    @pytest.mark.integration
    async def test_success_shape(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(nugen_module.settings, "NUGEN_API_KEY", "k")
        monkeypatch.setattr(nugen_module.settings, "NUGEN_ALIGNED_MODEL_ID", "model_x")
        fake = nugen_module.NugenChatResult(
            content="AQI 120 is Moderate (Observed). Stay hydrated.",
            model="model_x",
            confidence_score=0.9,
            prompt_tokens=10,
            completion_tokens=20,
        )
        monkeypatch.setattr(
            nugen_module.NugenClient,
            "chat_completion",
            AsyncMock(return_value=fake),
        )
        monkeypatch.setattr(nugen_module.NugenClient, "aclose", AsyncMock())
        resp = await client.post(
            "/api/v1/ai/air-quality-insights",
            json={"city": "Pune", "aqi": 120, "pm25": 45, "audience": "citizen"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["aligned"] is True
        assert body["data"]["model_id"] == "model_x"
        assert "Moderate" in body["data"]["insight"]
        assert body["data"]["confidence_score"] == 0.9

    @pytest.mark.integration
    async def test_validation_rejects_bad_input(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/ai/air-quality-insights",
            json={"city": "Pune", "aqi": -5},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    async def test_status_endpoint_shape(self, client, auth_headers, monkeypatch):
        monkeypatch.setattr(nugen_module.settings, "NUGEN_API_KEY", "k")
        monkeypatch.setattr(nugen_module.settings, "NUGEN_ALIGNED_MODEL_ID", "")
        resp = await client.get("/api/v1/ai/nugen-status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["configured"] is True
        assert data["deployment_status"] is None
