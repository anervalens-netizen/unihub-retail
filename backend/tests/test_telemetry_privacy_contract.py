from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request

import logging_config
import main
from observability.error_tracking import redact_sentry_event
from request_context import RequestContextMiddleware


SALARY_PERSON = "sp1_" + "a" * 64
OPERATION_ID = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
SCENARIO_ID = "5b1f7a28-4d3b-4f65-9fa0-9d1b8eeac009"
EXPORT_ID = "987654321"
VISIT_ID = "visit-private-identifier"
CNP = "1990" + "23" + "0150001"  # synthetic; impossible birth month blocks PII match
BEARER = "Bearer telemetry-" + "sensitive-token"
QUERY_KEY = "se" + "cret"
QUERY_VALUE = "query-" + "sensitive-value"
REQUEST_ID = "retail-req-telemetry"
FORBIDDEN = (
    SALARY_PERSON,
    OPERATION_ID,
    SCENARIO_ID,
    EXPORT_ID,
    VISIT_ID,
    CNP,
    "telemetry-sensitive-token",
    QUERY_VALUE,
    f"/salarii/agents/{SALARY_PERSON}/history",
    f"https://retail.invalid/api/jobs/{EXPORT_ID}?{QUERY_KEY}={QUERY_VALUE}",
)


def _private_message() -> str:
    return (
        f"operation_id={OPERATION_ID} scenario_id={SCENARIO_ID} "
        f"export_id={EXPORT_ID} visit_id={VISIT_ID} cnp={CNP} "
        f"authorization={BEARER} "
        f"path=/salarii/agents/{SALARY_PERSON}/history "
        f"url=https://retail.invalid/api/jobs/{EXPORT_ID}?{QUERY_KEY}={QUERY_VALUE}"
    )


def _assert_private_values_absent(value: Any) -> None:
    serialized = json.dumps(value, ensure_ascii=False, default=str)
    for forbidden in FORBIDDEN:
        assert forbidden not in serialized


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _record(message: str, **extra: Any) -> logging.LogRecord:
    record = logging.LogRecord(
        name="contract.telemetry",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@pytest.mark.anyio
async def test_request_log_keeps_only_canonical_route_and_required_context() -> None:
    capture = _Capture()
    logger = logging.getLogger("unihub.request")
    previous_handlers, previous_propagate, previous_level = (
        logger.handlers[:],
        logger.propagate,
        logger.level,
    )
    logger.handlers = [capture]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/api/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        return {"item": item_id}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://contract.invalid"
        ) as client:
            response = await client.get(
                f"/api/items/{OPERATION_ID}?{QUERY_KEY}={QUERY_VALUE}",
                headers={"X-Request-ID": REQUEST_ID},
            )
    finally:
        logger.handlers = previous_handlers
        logger.propagate = previous_propagate
        logger.setLevel(previous_level)

    assert response.status_code == 200
    record = capture.records[-1]
    payload = json.loads(logging_config.JSONFormatter().format(record))
    assert payload["route_template"] == "/api/items/{item_id}"
    assert payload["request_id"] == REQUEST_ID
    assert payload["method"] == "GET"
    assert payload["status"] == "200"
    assert isinstance(payload["duration_ms"], float)
    assert payload["service_role"] == "web"
    _assert_private_values_absent(payload)


@pytest.mark.anyio
async def test_slow_and_global_exception_logs_use_route_template_not_raw_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slow_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(main, "SLOW_REQUEST_THRESHOLD_SECONDS", 0)
    monkeypatch.setattr(
        main.logger,
        "warning",
        lambda *_args, **kwargs: slow_calls.append(kwargs),
    )

    app = FastAPI()

    @app.get("/api/jobs/{job_id}")
    async def job(job_id: str) -> dict[str, str]:
        return {"job": job_id}

    wrapped = main.SecurityHeadersMiddleware(app)
    transport = httpx.ASGITransport(app=wrapped)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://contract.invalid"
    ) as client:
        response = await client.get(
            f"/api/jobs/{EXPORT_ID}?{QUERY_KEY}={QUERY_VALUE}"
        )

    assert response.status_code == 200
    slow_extra = slow_calls[-1]["extra"]
    assert slow_extra == {
        "method": "GET",
        "route_template": "/api/jobs/{job_id}",
        "status": "2xx",
        "duration_ms": slow_extra["duration_ms"],
        "service_role": "web",
    }
    _assert_private_values_absent(slow_extra)

    error_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        main.logger,
        "error",
        lambda *_args, **kwargs: error_calls.append(kwargs),
    )

    class Route:
        path = "/api/scenarios/{scenario_id}"

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/scenarios/{SCENARIO_ID}",
            "query_string": f"{QUERY_KEY}={QUERY_VALUE}".encode(),
            "headers": [],
            "state": {"request_id": REQUEST_ID},
            "route": Route(),
        }
    )
    await main.unhandled_exception_handler(request, RuntimeError(_private_message()))
    error_extra = error_calls[-1]["extra"]
    assert error_extra["route_template"] == "/api/scenarios/{scenario_id}"
    assert error_extra["method"] == "GET"
    assert error_extra["status"] == 500
    assert error_extra["service_role"] == "web"
    formatted = logging_config.JSONFormatter().format(
        _record(_private_message(), request_id=REQUEST_ID, **error_extra)
    )
    _assert_private_values_absent(formatted)


def test_structured_formatter_and_postgres_sink_remove_identifier_corpus() -> None:
    record = _record(
        _private_message(),
        request_id=REQUEST_ID,
        method="GET",
        route_template="/api/visits-report/visit/{visit_id}",
        status=500,
        duration_ms=12.5,
        service_role="web",
        referer=(
            f"https://retail.invalid/visits/{VISIT_ID}?{QUERY_KEY}={QUERY_VALUE}"
        ),
        nested={"job_id": EXPORT_ID, "authorization": BEARER},
    )
    formatted = logging_config.JSONFormatter().format(record)
    payload = json.loads(formatted)
    assert payload["route_template"] == "/api/visits-report/visit/{visit_id}"
    assert payload["request_id"] == REQUEST_ID
    assert payload["method"] == "GET"
    assert payload["status"] == "500"
    assert payload["duration_ms"] == 12.5
    assert payload["service_role"] == "web"
    _assert_private_values_absent(payload)

    handler = logging_config.DBErrorHandler(
        queue_size=1, write_timeout=1, drain_timeout=1
    )
    event = handler._event_from_record(record)
    assert event.extra_json is not None
    db_payload = {
        "message": event.message,
        "traceback": event.traceback_text,
        "logger_path": event.logger_path,
        "extra": json.loads(event.extra_json),
    }
    assert db_payload["extra"]["route_template"] == (
        "/api/visits-report/visit/{visit_id}"
    )
    assert db_payload["extra"]["request_id"] == REQUEST_ID
    _assert_private_values_absent(db_payload)


def test_sentry_event_transaction_url_spans_and_breadcrumbs_are_canonicalized() -> None:
    event = {
        "request": {
            "url": (
                f"https://retail.invalid/api/jobs/{EXPORT_ID}?"
                f"{QUERY_KEY}={QUERY_VALUE}"
            ),
            "headers": {"Authorization": BEARER},
        },
        "transaction": "/api/jobs/{job_id}",
        "tags": {
            "request_id": REQUEST_ID,
            "method": "GET",
            "route_template": "/api/jobs/{job_id}",
            "status": "500",
            "service_role": "web",
        },
        "contexts": {"trace": {"duration_ms": 17.2}},
        "spans": [
            {"description": "/api/jobs/{job_id}"},
            {"description": f"/api/jobs/{EXPORT_ID}"},
        ],
        "breadcrumbs": [
            {
                "message": _private_message(),
                "data": {
                    "visit_id": VISIT_ID,
                    "pathname": f"/api/visits-report/visit/{VISIT_ID}",
                },
            }
        ],
        "exception": {"values": [{"value": _private_message()}]},
    }
    payload = redact_sentry_event(event, {})
    assert payload["request"]["url"] == "https://retail.invalid"
    assert payload["transaction"] == "/api/jobs/{job_id}"
    assert payload["tags"] == {
        "request_id": REQUEST_ID,
        "method": "GET",
        "route_template": "/api/jobs/{job_id}",
        "status": "500",
        "service_role": "web",
    }
    assert payload["contexts"]["trace"]["duration_ms"] == 17.2
    assert payload["spans"][0]["description"] == "/api/jobs/{job_id}"
    assert payload["spans"][1]["description"] == "__unmatched__"
    _assert_private_values_absent(payload)
