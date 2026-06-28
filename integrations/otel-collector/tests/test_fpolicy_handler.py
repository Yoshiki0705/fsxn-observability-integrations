"""Unit tests for FPolicy → OTel Collector OTLP handler."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
sys.modules.pop("fpolicy_handler", None)

import fpolicy_handler


# ─── Sample FPolicy events ─────────────────────────────────────────────────

SAMPLE_FILE_CREATE_EVENT = {
    "version": "0",
    "id": "abc123",
    "detail-type": "FPolicy File Operation",
    "source": "fpolicy.fsxn",
    "account": "123456789012",
    "time": "2026-01-15T12:00:01Z",
    "region": "ap-northeast-1",
    "detail": {
        "operation": "create",
        "file_path": "/vol/data/shared/new_document.docx",
        "user": "admin@corp.local",
        "client_ip": "10.0.1.50",
        "volume": "vol_data",
        "svm": "svm-prod-01",
        "protocol": "cifs",
        "timestamp": "2026-01-15T12:00:01Z",
    },
}

SAMPLE_FILE_WRITE_EVENT = {
    "version": "0",
    "id": "def456",
    "detail-type": "FPolicy File Operation",
    "source": "fpolicy.fsxn",
    "detail": {
        "operation": "write",
        "file_path": "/vol/data/shared/existing_file.xlsx",
        "user": "user1@corp.local",
        "client_ip": "10.0.1.51",
        "volume": "vol_data",
        "svm": "svm-prod-01",
        "protocol": "cifs",
        "timestamp": "2026-01-15T12:00:02Z",
    },
}

SAMPLE_FILE_RENAME_EVENT = {
    "version": "0",
    "id": "ghi789",
    "detail-type": "FPolicy File Operation",
    "source": "fpolicy.fsxn",
    "detail": {
        "operation": "rename",
        "file_path": "/vol/data/shared/renamed_file.txt",
        "user": "user2@corp.local",
        "client_ip": "10.0.1.52",
        "volume": "vol_data",
        "svm": "svm-prod-01",
        "protocol": "cifs",
        "timestamp": "2026-01-15T12:00:03Z",
    },
}

SAMPLE_FILE_DELETE_EVENT = {
    "version": "0",
    "id": "jkl012",
    "detail-type": "FPolicy File Operation",
    "source": "fpolicy.fsxn",
    "detail": {
        "operation": "delete",
        "file_path": "/vol/data/shared/deleted_file.tmp",
        "user": "admin@corp.local",
        "client_ip": "10.0.1.50",
        "volume": "vol_data",
        "svm": "svm-prod-01",
        "protocol": "cifs",
        "timestamp": "2026-01-15T12:00:04Z",
    },
}


class TestBuildFpolicyOtlpPayload:
    """Tests for build_fpolicy_otlp_payload function."""

    def test_file_create_payload_structure(self):
        """File create event produces valid OTLP payload."""
        detail = SAMPLE_FILE_CREATE_EVENT["detail"]
        payload = fpolicy_handler.build_fpolicy_otlp_payload(detail)

        # Validate structure
        assert "resourceLogs" in payload
        resource_log = payload["resourceLogs"][0]

        # Resource attributes
        attr_map = {
            a["key"]: a["value"]["stringValue"]
            for a in resource_log["resource"]["attributes"]
        }
        assert attr_map["service.name"] == "fsxn-fpolicy"

        # Log record
        log_record = resource_log["scopeLogs"][0]["logRecords"][0]
        assert log_record["severityNumber"] == 9
        assert log_record["severityText"] == "INFO"
        assert log_record["timeUnixNano"] != ""

        # Attributes
        record_attrs = {a["key"]: a["value"]["stringValue"] for a in log_record["attributes"]}
        assert record_attrs["operation_type"] == "create"
        assert record_attrs["file_path"] == "/vol/data/shared/new_document.docx"
        assert record_attrs["user"] == "admin@corp.local"
        assert record_attrs["client_ip"] == "10.0.1.50"

    def test_field_mapping(self):
        """FPolicy fields are correctly mapped to OTLP attributes."""
        detail = {
            "operation": "write",
            "file_path": "/vol/data/test.txt",
            "user": "testuser",
            "client_ip": "192.168.1.1",
            "timestamp": "2026-01-15T12:00:00Z",
        }
        payload = fpolicy_handler.build_fpolicy_otlp_payload(detail)
        log_record = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]

        attr_map = {a["key"]: a["value"]["stringValue"] for a in log_record["attributes"]}
        assert attr_map["operation_type"] == "write"
        assert attr_map["file_path"] == "/vol/data/test.txt"
        assert attr_map["user"] == "testuser"
        assert attr_map["client_ip"] == "192.168.1.1"

    def test_missing_fields_omitted(self):
        """Missing fields are not included in attributes."""
        detail = {"operation": "create", "timestamp": "2026-01-15T12:00:00Z"}
        payload = fpolicy_handler.build_fpolicy_otlp_payload(detail)
        log_record = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]

        attr_keys = {a["key"] for a in log_record["attributes"]}
        assert "operation_type" in attr_keys
        assert "file_path" not in attr_keys
        assert "user" not in attr_keys
        assert "client_ip" not in attr_keys

    def test_additional_fields_included(self):
        """Additional fields (volume, svm, protocol) are included."""
        detail = {
            "operation": "create",
            "file_path": "/test",
            "volume": "vol1",
            "svm": "svm1",
            "protocol": "nfs",
            "timestamp": "2026-01-15T12:00:00Z",
        }
        payload = fpolicy_handler.build_fpolicy_otlp_payload(detail)
        log_record = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]

        attr_map = {a["key"]: a["value"]["stringValue"] for a in log_record["attributes"]}
        assert attr_map["volume"] == "vol1"
        assert attr_map["svm"] == "svm1"
        assert attr_map["protocol"] == "nfs"


class TestSendOtlpPayload:
    """Tests for _send_otlp_payload function."""

    @patch("fpolicy_handler.http")
    def test_successful_send(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        result = fpolicy_handler._send_otlp_payload({"resourceLogs": []})
        assert result is True

    @patch("fpolicy_handler.http")
    def test_retry_on_5xx(self, mock_http):
        mock_error = MagicMock()
        mock_error.status = 500
        mock_error.data = b"Error"

        mock_success = MagicMock()
        mock_success.status = 200

        mock_http.request.side_effect = [mock_error, mock_success]

        with patch("fpolicy_handler.time.sleep"):
            result = fpolicy_handler._send_otlp_payload({"resourceLogs": []})

        assert result is True
        assert mock_http.request.call_count == 2

    @patch("fpolicy_handler.http")
    def test_retry_on_429(self, mock_http):
        mock_rate = MagicMock()
        mock_rate.status = 429
        mock_rate.headers = {"Retry-After": "2"}

        mock_success = MagicMock()
        mock_success.status = 200

        mock_http.request.side_effect = [mock_rate, mock_success]

        with patch("fpolicy_handler.time.sleep"):
            result = fpolicy_handler._send_otlp_payload({"resourceLogs": []})

        assert result is True

    @patch("fpolicy_handler.http")
    def test_no_retry_on_4xx(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 403
        mock_response.data = b"Forbidden"
        mock_http.request.return_value = mock_response

        result = fpolicy_handler._send_otlp_payload({"resourceLogs": []})
        assert result is False
        assert mock_http.request.call_count == 1

    @patch("fpolicy_handler.http")
    def test_max_retries_exhausted(self, mock_http):
        mock_error = MagicMock()
        mock_error.status = 500
        mock_error.data = b"Error"
        mock_http.request.return_value = mock_error

        with patch("fpolicy_handler.time.sleep"):
            result = fpolicy_handler._send_otlp_payload({"resourceLogs": []})

        assert result is False
        assert mock_http.request.call_count == 3


class TestLambdaHandler:
    """Tests for the FPolicy Lambda handler entry point."""

    @patch("fpolicy_handler.http")
    def test_file_create_event(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        result = fpolicy_handler.lambda_handler(SAMPLE_FILE_CREATE_EVENT, None)

        assert result["statusCode"] == 200
        assert result["body"]["status"] == "ok"
        assert result["body"]["operation"] == "create"
        assert result["body"]["otlp_delivered"] is True

    @patch("fpolicy_handler.http")
    def test_file_write_event(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        result = fpolicy_handler.lambda_handler(SAMPLE_FILE_WRITE_EVENT, None)

        assert result["statusCode"] == 200
        assert result["body"]["operation"] == "write"

    @patch("fpolicy_handler.http")
    def test_file_rename_event(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        result = fpolicy_handler.lambda_handler(SAMPLE_FILE_RENAME_EVENT, None)

        assert result["statusCode"] == 200
        assert result["body"]["operation"] == "rename"

    @patch("fpolicy_handler.http")
    def test_file_delete_event(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        result = fpolicy_handler.lambda_handler(SAMPLE_FILE_DELETE_EVENT, None)

        assert result["statusCode"] == 200
        assert result["body"]["operation"] == "delete"

    @patch("fpolicy_handler.http")
    def test_otlp_delivery_failure(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.data = b"Error"
        mock_http.request.return_value = mock_response

        with patch("fpolicy_handler.time.sleep"):
            result = fpolicy_handler.lambda_handler(SAMPLE_FILE_CREATE_EVENT, None)

        assert result["statusCode"] == 502
        assert result["body"]["status"] == "error"

    @patch("fpolicy_handler.http")
    def test_direct_detail_event(self, mock_http):
        """Handler works with direct detail dict (no EventBridge wrapper)."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        direct_event = {
            "operation": "create",
            "file_path": "/vol/data/test.txt",
            "user": "admin",
            "client_ip": "10.0.1.1",
            "timestamp": "2026-01-15T12:00:00Z",
        }

        result = fpolicy_handler.lambda_handler(direct_event, None)
        assert result["statusCode"] == 200
