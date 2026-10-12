import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.core.correlation import (
    REQUEST_ID_HEADER,
    CorrelationIdMiddleware,
    _safe_request_id,
)
from app.core.request_metrics import RequestMetricsMiddleware, _status_class


def _request(path: str = "/api/v1/health", headers: dict | None = None) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": raw_headers,
            "client": ("1.2.3.4", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


async def _ok(_request: Request) -> Response:
    return Response(status_code=200)


async def _fail(_request: Request) -> Response:
    return Response(status_code=500)


class TestRequestIdValidation:
    def test_accepts_standard_uuid(self):
        rid = "550e8400-e29b-41d4-a716-446655440000"
        assert _safe_request_id(rid) == rid

    def test_accepts_proxy_style_ids(self):
        assert _safe_request_id("req_ABC-123_def") == "req_ABC-123_def"

    def test_rejects_too_long(self):
        assert _safe_request_id("a" * 65) != "a" * 65

    def test_rejects_log_injection(self):
        # Newlines/control chars in a client header must never reach the log
        # stream as a request_id.
        rid = _safe_request_id("abc\r\ninjected-log-line")
        assert "\r" not in rid and "\n" not in rid

    def test_rejects_whitespace_and_empty(self):
        assert _safe_request_id(" ") != " "
        assert _safe_request_id("") != ""
        assert _safe_request_id("a b") != "a b"

    def test_generates_for_missing(self):
        generated = _safe_request_id(None)
        assert len(generated) == 32
        int(generated, 16)  # valid hex uuid


class TestCorrelationIdMiddleware:
    async def test_echoes_incoming_valid_id(self):
        mw = CorrelationIdMiddleware(app=lambda s, r, w: None)
        resp = await mw.dispatch(
            _request(headers={REQUEST_ID_HEADER: "trace-123"}), _ok
        )
        assert resp.status_code == 200
        assert resp.headers[REQUEST_ID_HEADER] == "trace-123"

    async def test_replaces_unsafe_id(self):
        mw = CorrelationIdMiddleware(app=lambda s, r, w: None)
        resp = await mw.dispatch(
            _request(headers={REQUEST_ID_HEADER: "bad\r\nid"}), _ok
        )
        echoed = resp.headers[REQUEST_ID_HEADER]
        assert echoed != "bad\r\nid"
        assert "\r" not in echoed and "\n" not in echoed

    async def test_generates_id_when_absent(self):
        mw = CorrelationIdMiddleware(app=lambda s, r, w: None)
        resp = await mw.dispatch(_request(), _ok)
        assert REQUEST_ID_HEADER in resp.headers
        assert len(resp.headers[REQUEST_ID_HEADER]) == 32

    async def test_binds_and_unbinds_contextvar(self):
        import structlog

        captured = {}

        async def _check(_r: Request) -> Response:
            captured.update(structlog.contextvars.get_contextvars())
            return Response(status_code=200)

        mw = CorrelationIdMiddleware(app=lambda s, r, w: None)
        await mw.dispatch(_request(headers={REQUEST_ID_HEADER: "ctx-1"}), _check)
        assert captured.get("request_id") == "ctx-1"
        assert "request_id" not in structlog.contextvars.get_contextvars()


class TestRequestMetrics:
    def test_status_class(self):
        assert _status_class(200) == "2xx"
        assert _status_class(404) == "4xx"
        assert _status_class(500) == "5xx"
        assert _status_class(302) == "3xx"

    async def test_counts_requests_by_method_and_class(self):
        from app.core import request_metrics

        if request_metrics._REQUESTS is None:
            pytest.skip("prometheus_client unavailable")

        labels_before = request_metrics._REQUESTS.labels("GET", "2xx")._value.get()
        mw = RequestMetricsMiddleware(app=lambda s, r, w: None)
        resp = await mw.dispatch(_request(), _ok)
        assert resp.status_code == 200
        assert (
            request_metrics._REQUESTS.labels("GET", "2xx")._value.get()
            == labels_before + 1
        )

    async def test_500s_counted_as_5xx(self):
        from app.core import request_metrics

        if request_metrics._REQUESTS is None:
            pytest.skip("prometheus_client unavailable")

        before = request_metrics._REQUESTS.labels("GET", "5xx")._value.get()
        mw = RequestMetricsMiddleware(app=lambda s, r, w: None)
        await mw.dispatch(_request(), _fail)
        assert request_metrics._REQUESTS.labels("GET", "5xx")._value.get() == before + 1
