"""JSON 结构化日志测试。"""
import json
import logging
import os


def test_json_log_formatter_includes_extra_fields():
    from services.app_log_service import JsonLogFormatter

    record = logging.LogRecord(
        name="traesolo.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.event = "unit_test"
    record.status_code = 200
    record.duration_ms = 12.5

    line = JsonLogFormatter().format(record)
    data = json.loads(line)
    assert data["level"] == "INFO"
    assert data["message"] == "hello"
    assert data["event"] == "unit_test"
    assert data["status_code"] == 200
    assert data["duration_ms"] == 12.5
    assert "timestamp" in data


def test_log_http_access_respects_json_flag(monkeypatch):
    from services import app_log_service

    monkeypatch.setenv("TRAESOLO_JSON_LOGS", "1")
    monkeypatch.setenv("TRAESOLO_ACCESS_LOG", "")
    app_log_service._CONFIGURED = False
    app_log_service.setup_app_logging()

    logger = logging.getLogger("traesolo.access")
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger.addHandler(_Capture())
    app_log_service.log_http_access("GET", "/api/v1/health/live", 200, 3.2)
    assert records
    assert records[-1].event == "http_access"
    assert records[-1].path == "/api/v1/health/live"
