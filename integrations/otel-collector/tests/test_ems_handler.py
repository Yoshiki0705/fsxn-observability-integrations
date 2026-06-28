"""Unit tests for EMS Webhook → OTel Collector OTLP handler."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
sys.modules.pop("ems_handler", None)

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
