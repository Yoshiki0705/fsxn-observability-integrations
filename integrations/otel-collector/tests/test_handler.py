"""Unit tests for OTel Collector log shipper."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
import handler


class TestBuildOtlpPayload:
    def test_basic_structure(self, sample_logs):
        logs = [json.loads(l) for l in sample_logs.strip().split("\n")]
        payload = handler._build_otlp_logs_payload(logs, "audit/test.json")

        assert "resourceLogs" in payload
        resource_logs = payload["resourceLogs"]
        assert len(resource_logs) == 1

        # Check resource attributes
        resource = resource_logs[0]["resource"]
        attr_keys = [a["key"] for a in resource["attributes"]]
        assert "service.name" in attr_keys
        assert "cloud.provider" in attr_keys

        # Check log records
        scope_logs = resource_logs[0]["scopeLogs"]
        assert len(scope_logs) == 1
        records = scope_logs[0]["logRecords"]
        assert len(records) == 2

    def test_severity_for_failure(self, sample_logs):
        logs = [json.loads(l) for l in sample_logs.strip().split("\n")]
        payload = handler._build_otlp_logs_payload(logs, "test.json")
        records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]

        # First record: Success -> INFO (9)
        assert records[0]["severityNumber"] == 9
        # Second record: Failure -> WARN (13)
        assert records[1]["severityNumber"] == 13

    def test_resource_attributes_from_env(self):
        logs = [{"message": "test"}]
        payload = handler._build_otlp_logs_payload(logs, "test.json")
        resource = payload["resourceLogs"][0]["resource"]
        attr_map = {a["key"]: a["value"]["stringValue"] for a in resource["attributes"]}
        assert attr_map["deployment.environment"] == "test"
        assert attr_map["cloud.region"] == "ap-northeast-1"

    def test_empty_logs(self):
        payload = handler._build_otlp_logs_payload([], "test.json")
        records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        assert len(records) == 0


class TestIsoToUnixNano:
    def test_valid_timestamp(self):
        result = handler._iso_to_unix_nano("2026-01-15T12:00:00Z")
        assert result > 0
        # Should be in nanoseconds (19 digits)
        assert len(str(result)) >= 18

    def test_invalid_timestamp(self):
        result = handler._iso_to_unix_nano("not-a-date")
        assert result > 0  # Falls back to now


class TestSendOtlpBatch:
    @patch("handler.http")
    def test_success(self, mock_http):
        mock_http.request.return_value = MagicMock(status=200)
        payload = {"resourceLogs": [{"resource": {}, "scopeLogs": [{"scope": {}, "logRecords": [{"body": {}}]}]}]}
        assert handler._send_otlp_batch(payload, {}) is True

        # Verify endpoint path
        call_args = mock_http.request.call_args
        assert call_args[0][1].endswith("/v1/logs")

    @patch("handler.http")
    def test_gzip_encoding(self, mock_http):
        mock_http.request.return_value = MagicMock(status=200)
        handler._send_otlp_batch({"resourceLogs": []}, {})
        headers = mock_http.request.call_args[1]["headers"]
        assert headers["Content-Encoding"] == "gzip"

    @patch("handler.http")
    def test_auth_headers_passed(self, mock_http):
        mock_http.request.return_value = MagicMock(status=200)
        handler._send_otlp_batch({"resourceLogs": []}, {"Authorization": "Bearer tok123"})
        headers = mock_http.request.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer tok123"

    @patch("handler.http")
    def test_retry_on_503(self, mock_http):
        mock_503 = MagicMock(status=503, data=b"unavailable")
        mock_ok = MagicMock(status=200)
        mock_http.request.side_effect = [mock_503, mock_ok]
        with patch("handler.time.sleep"):
            assert handler._send_otlp_batch({"resourceLogs": []}, {}) is True


class TestGetAuthHeaders:
    @patch("handler.secrets_client")
    def test_with_secret(self, mock_secrets, monkeypatch):
        handler._auth_header_cache = None
        monkeypatch.setenv("API_KEY_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123:secret:test")
        monkeypatch.setenv("OTLP_HEADERS", "X-Scope-OrgID=tenant1")
        # Reload module-level vars
        handler.API_KEY_SECRET_ARN = "arn:aws:secretsmanager:us-east-1:123:secret:test"
        handler.OTLP_HEADERS = "X-Scope-OrgID=tenant1"

        mock_secrets.get_secret_value.return_value = {"SecretString": "my-token"}
        headers = handler.get_auth_headers()

        assert headers["Authorization"] == "Bearer my-token"
        assert headers["X-Scope-OrgID"] == "tenant1"

        # Reset
        handler._auth_header_cache = None
        handler.API_KEY_SECRET_ARN = ""
        handler.OTLP_HEADERS = ""
