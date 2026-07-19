"""Unit tests for EMS Webhook → OTel Collector OTLP handler."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))

import ems_handler


# ─── Sample EMS events ─────────────────────────────────────────────────────

SAMPLE_ARP_EVENT = {
    "messageName": "arw.volume.state",
    "severity": "alert",
    "time": "2026-01-15T12:00:01Z",
    "node": "fsxn-node-01",
    "svmName": "svm-prod-01",
    "message": "Anti-Ransomware: Volume vol_data state changed to attack-detected",
    "parameters": {
        "volume_name": "vol_data",
        "state": "attack-detected",
        "vserver": "svm-prod-01",
    },
}

SAMPLE_QUOTA_EVENT = {
    "messageName": "wafl.quota.softlimit.exceeded",
    "severity": "warning",
    "time": "2026-01-15T12:05:00Z",
    "node": "fsxn-node-01",
    "svmName": "svm-prod-01",
    "message": "Soft quota exceeded on volume vol_data",
    "parameters": {
        "volume_name": "vol_data",
        "quota_target": "/vol/data/shared",
        "used_bytes": "62914560",
        "limit_bytes": "52428800",
    },
}


class TestBuildEmsOtlpPayload:
    """Tests for build_ems_otlp_payload function."""

    def test_arp_event_payload_structure(self):
        """ARP event produces valid OTLP payload with correct attributes."""
        normalized = ems_handler.parse_ems_event(SAMPLE_ARP_EVENT)
        payload = ems_handler.build_ems_otlp_payload(normalized)

        # Validate structure
        assert "resourceLogs" in payload
        resource_log = payload["resourceLogs"][0]

        # Resource attributes
        attr_map = {
            a["key"]: a["value"]["stringValue"]
            for a in resource_log["resource"]["attributes"]
        }
        assert attr_map["service.name"] == "fsxn-ems"
        assert attr_map["service.namespace"] == "fsxn-ontap"

        # Log record
        log_record = resource_log["scopeLogs"][0]["logRecords"][0]
        assert log_record["severityNumber"] == 17  # alert → ERROR
        assert log_record["severityText"] == "ERROR"
        assert log_record["timeUnixNano"] != ""

        # Attributes
        record_attrs = {a["key"]: a["value"]["stringValue"] for a in log_record["attributes"]}
        assert record_attrs["event_name"] == "arw.volume.state"
        assert record_attrs["severity"] == "alert"
        assert record_attrs["volume_name"] == "vol_data"
        assert record_attrs["state"] == "attack-detected"

    def test_quota_event_payload_structure(self):
        """Quota event produces valid OTLP payload with correct attributes."""
        normalized = ems_handler.parse_ems_event(SAMPLE_QUOTA_EVENT)
        payload = ems_handler.build_ems_otlp_payload(normalized)

        resource_log = payload["resourceLogs"][0]
        log_record = resource_log["scopeLogs"][0]["logRecords"][0]

        assert log_record["severityNumber"] == 13  # warning → WARN
        assert log_record["severityText"] == "WARN"

        record_attrs = {a["key"]: a["value"]["stringValue"] for a in log_record["attributes"]}
        assert record_attrs["event_name"] == "wafl.quota.softlimit.exceeded"
        assert record_attrs["volume_name"] == "vol_data"
        assert record_attrs["quota_target"] == "/vol/data/shared"
        assert record_attrs["used_bytes"] == "62914560"
        assert record_attrs["limit_bytes"] == "52428800"

    def test_resource_attributes_always_present(self):
        """Resource attributes service.name and service.namespace are always set."""
        normalized = {"event_name": "test", "severity": "info", "timestamp": "", "parameters": {}}
        payload = ems_handler.build_ems_otlp_payload(normalized)

        resource_attrs = {
            a["key"]: a["value"]["stringValue"]
            for a in payload["resourceLogs"][0]["resource"]["attributes"]
        }
        assert resource_attrs["service.name"] == "fsxn-ems"
        assert resource_attrs["service.namespace"] == "fsxn-ontap"


class TestEmsSeverityMapping:
    """Tests for EMS severity to OTLP severity mapping."""

    def test_alert_maps_to_error(self):
        assert ems_handler._ems_severity_to_otlp("alert") == (17, "ERROR")

    def test_warning_maps_to_warn(self):
        assert ems_handler._ems_severity_to_otlp("warning") == (13, "WARN")

    def test_informational_maps_to_info(self):
        assert ems_handler._ems_severity_to_otlp("informational") == (9, "INFO")

    def test_emergency_maps_to_fatal(self):
        assert ems_handler._ems_severity_to_otlp("emergency") == (21, "FATAL")

    def test_unknown_maps_to_info(self):
        assert ems_handler._ems_severity_to_otlp("unknown") == (9, "INFO")


class TestSendOtlpPayload:
    """Tests for _send_otlp_payload function."""

    @patch("ems_handler.http")
    def test_successful_send(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        result = ems_handler._send_otlp_payload({"resourceLogs": []})
        assert result is True

    @patch("ems_handler.http")
    def test_retry_on_5xx(self, mock_http):
        mock_error = MagicMock()
        mock_error.status = 503
        mock_error.data = b"Service Unavailable"

        mock_success = MagicMock()
        mock_success.status = 200

        mock_http.request.side_effect = [mock_error, mock_success]

        with patch("ems_handler.time.sleep"):
            result = ems_handler._send_otlp_payload({"resourceLogs": []})

        assert result is True
        assert mock_http.request.call_count == 2

    @patch("ems_handler.http")
    def test_retry_on_429(self, mock_http):
        mock_rate = MagicMock()
        mock_rate.status = 429
        mock_rate.headers = {"Retry-After": "1"}

        mock_success = MagicMock()
        mock_success.status = 200

        mock_http.request.side_effect = [mock_rate, mock_success]

        with patch("ems_handler.time.sleep"):
            result = ems_handler._send_otlp_payload({"resourceLogs": []})

        assert result is True

    @patch("ems_handler.http")
    def test_no_retry_on_4xx(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 400
        mock_response.data = b"Bad Request"
        mock_http.request.return_value = mock_response

        result = ems_handler._send_otlp_payload({"resourceLogs": []})
        assert result is False
        assert mock_http.request.call_count == 1

    @patch("ems_handler.http")
    def test_max_retries_exhausted(self, mock_http):
        mock_error = MagicMock()
        mock_error.status = 500
        mock_error.data = b"Error"
        mock_http.request.return_value = mock_error

        with patch("ems_handler.time.sleep"):
            result = ems_handler._send_otlp_payload({"resourceLogs": []})

        assert result is False
        assert mock_http.request.call_count == 3


class TestAuthModeHeader:
    """Tests for AUTH_MODE="header" and EXTRA_HEADERS_JSON (generic
    custom-header auth support, needed for vendors like Mackerel with a
    non-Bearer/Basic auth header, e.g. "Mackerel-Api-Key")."""

    @patch("ems_handler.http")
    @patch("ems_handler.secrets_client")
    def test_header_auth_mode_uses_custom_header_name(self, mock_secrets, mock_http, monkeypatch):
        ems_handler._api_key_cache = None
        # These are module-level constants read once at import time; patch
        # the attributes directly rather than the env vars (see handler.py's
        # equivalent test for the same reasoning).
        monkeypatch.setattr(
            ems_handler, "API_KEY_SECRET_ARN",
            "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test",
        )
        monkeypatch.setattr(ems_handler, "AUTH_MODE", "header")
        monkeypatch.setattr(ems_handler, "AUTH_HEADER_NAME", "Mackerel-Api-Key")

        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"api_key": "write-scoped-key"})
        }
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_ARP_EVENT)}
        ems_handler.lambda_handler(event, None)

        _, kwargs = mock_http.request.call_args
        sent_headers = kwargs["headers"]
        assert sent_headers["Mackerel-Api-Key"] == "write-scoped-key"
        assert "Authorization" not in sent_headers

    @patch("ems_handler.http")
    @patch("ems_handler.secrets_client")
    def test_extra_headers_json_merged(self, mock_secrets, mock_http, monkeypatch):
        ems_handler._api_key_cache = None
        monkeypatch.setattr(
            ems_handler, "API_KEY_SECRET_ARN",
            "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test",
        )
        monkeypatch.setattr(ems_handler, "AUTH_MODE", "header")
        monkeypatch.setattr(ems_handler, "AUTH_HEADER_NAME", "Mackerel-Api-Key")
        monkeypatch.setattr(ems_handler, "EXTRA_HEADERS_JSON", '{"Accept": "*/*"}')

        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"api_key": "write-scoped-key"})
        }
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_ARP_EVENT)}
        ems_handler.lambda_handler(event, None)

        _, kwargs = mock_http.request.call_args
        sent_headers = kwargs["headers"]
        assert sent_headers["Mackerel-Api-Key"] == "write-scoped-key"
        assert sent_headers["Accept"] == "*/*"

    @patch("ems_handler.http")
    def test_extra_headers_json_works_without_api_key_secret(self, mock_http, monkeypatch):
        monkeypatch.setattr(ems_handler, "EXTRA_HEADERS_JSON", '{"Accept": "*/*"}')
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_ARP_EVENT)}
        ems_handler.lambda_handler(event, None)

        _, kwargs = mock_http.request.call_args
        assert kwargs["headers"]["Accept"] == "*/*"

    @patch("ems_handler.http")
    def test_malformed_extra_headers_json_ignored_not_fatal(self, mock_http, monkeypatch):
        monkeypatch.setattr(ems_handler, "EXTRA_HEADERS_JSON", "{not valid json")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_ARP_EVENT)}
        result = ems_handler.lambda_handler(event, None)

        assert result["statusCode"] == 200
        _, kwargs = mock_http.request.call_args
        assert kwargs["headers"] == {"Content-Type": "application/json"}


class TestOtlpContentTypeProtobuf:
    """Tests for OTLP_CONTENT_TYPE="protobuf" (needed for vendors like
    Mackerel whose OTLP/HTTP log endpoint rejects OTLP/JSON bodies)."""

    @patch("ems_handler.http")
    def test_protobuf_content_type_sets_correct_header_and_body_encoding(
        self, mock_http, monkeypatch,
    ):
        monkeypatch.setattr(ems_handler, "OTLP_CONTENT_TYPE", "protobuf")
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_ARP_EVENT)}
        result = ems_handler.lambda_handler(event, None)

        assert result["statusCode"] == 200
        _, kwargs = mock_http.request.call_args
        assert kwargs["headers"]["Content-Type"] == "application/x-protobuf"
        body = kwargs["body"]
        assert isinstance(body, bytes)
        with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
            json.loads(body)

    @patch("ems_handler.http")
    def test_default_content_type_is_json_unaffected(self, mock_http):
        """Regression guard: default OTLP_CONTENT_TYPE must behave exactly
        as before (OTLP/JSON body)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_ARP_EVENT)}
        ems_handler.lambda_handler(event, None)

        _, kwargs = mock_http.request.call_args
        assert kwargs["headers"]["Content-Type"] == "application/json"
        json.loads(kwargs["body"])

    @patch("ems_handler.http")
    @patch("ems_handler.secrets_client")
    def test_protobuf_content_type_combined_with_header_auth(
        self, mock_secrets, mock_http, monkeypatch,
    ):
        """The combination actually needed for Mackerel's direct-send path:
        AUTH_MODE=header + OTLP_CONTENT_TYPE=protobuf together."""
        ems_handler._api_key_cache = None
        monkeypatch.setattr(
            ems_handler, "API_KEY_SECRET_ARN",
            "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:test",
        )
        monkeypatch.setattr(ems_handler, "AUTH_MODE", "header")
        monkeypatch.setattr(ems_handler, "AUTH_HEADER_NAME", "Mackerel-Api-Key")
        monkeypatch.setattr(ems_handler, "EXTRA_HEADERS_JSON", '{"Accept": "*/*"}')
        monkeypatch.setattr(ems_handler, "OTLP_CONTENT_TYPE", "protobuf")

        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"api_key": "write-scoped-key"})
        }
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_ARP_EVENT)}
        result = ems_handler.lambda_handler(event, None)

        assert result["statusCode"] == 200
        _, kwargs = mock_http.request.call_args
        assert kwargs["headers"]["Mackerel-Api-Key"] == "write-scoped-key"
        assert kwargs["headers"]["Accept"] == "*/*"
        assert kwargs["headers"]["Content-Type"] == "application/x-protobuf"
        assert isinstance(kwargs["body"], bytes)


class TestLambdaHandler:
    """Tests for the EMS Lambda handler entry point."""

    @patch("ems_handler.http")
    def test_successful_arp_event(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_ARP_EVENT)}
        result = ems_handler.lambda_handler(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["status"] == "ok"
        assert body["event_name"] == "arw.volume.state"
        assert body["otlp_delivered"] is True

    @patch("ems_handler.http")
    def test_successful_quota_event(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_QUOTA_EVENT)}
        result = ems_handler.lambda_handler(event, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["event_name"] == "wafl.quota.softlimit.exceeded"

    @patch("ems_handler.http")
    def test_otlp_delivery_failure(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.data = b"Error"
        mock_http.request.return_value = mock_response

        event = {"body": json.dumps(SAMPLE_ARP_EVENT)}

        with patch("ems_handler.time.sleep"):
            result = ems_handler.lambda_handler(event, None)

        assert result["statusCode"] == 502
        body = json.loads(result["body"])
        assert body["status"] == "error"

    def test_invalid_ems_payload(self):
        event = {"body": "not valid json"}
        result = ems_handler.lambda_handler(event, None)
        assert result["statusCode"] == 400

    def test_empty_body(self):
        event = {"body": ""}
        result = ems_handler.lambda_handler(event, None)
        assert result["statusCode"] == 400
