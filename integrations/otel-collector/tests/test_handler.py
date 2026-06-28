"""Unit tests for OTel Collector OTLP shipper Lambda handler."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add lambda directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
sys.modules.pop("handler", None)

import handler


class TestExtractS3Records:
    """Tests for _extract_s3_records function."""

    def test_s3_event_notification(self, sample_s3_event):
        records = handler._extract_s3_records(sample_s3_event)
        assert len(records) == 1
        assert records[0]["bucket"] == "fsxn-audit-logs-bucket"
        assert records[0]["key"] == "audit/svm1/2026/01/15/audit_log_001.json"

    def test_eventbridge_event(self, sample_eventbridge_event):
        records = handler._extract_s3_records(sample_eventbridge_event)
        assert len(records) == 1
        assert records[0]["bucket"] == "fsxn-audit-logs-bucket"
        assert records[0]["key"] == "audit/svm1/2026/01/15/audit_log_001.json"

    def test_empty_event(self):
        records = handler._extract_s3_records({})
        assert len(records) == 0

    def test_multiple_records(self):
        event = {
            "Records": [
                {"s3": {"bucket": {"name": "b1"}, "object": {"key": "k1.json"}}},
                {"s3": {"bucket": {"name": "b2"}, "object": {"key": "k2.json"}}},
            ]
        }
        records = handler._extract_s3_records(event)
        assert len(records) == 2

    def test_missing_bucket_filtered(self):
        event = {
            "Records": [
                {"s3": {"bucket": {"name": ""}, "object": {"key": "k1.json"}}},
            ]
        }
        records = handler._extract_s3_records(event)
        assert len(records) == 0


class TestDetermineSeverity:
    """Tests for determine_severity function."""

    def test_success_returns_info(self):
        assert handler.determine_severity("Success") == (9, "INFO")

    def test_failure_returns_warn(self):
        assert handler.determine_severity("Failure") == (13, "WARN")

    def test_access_denied_returns_warn(self):
        assert handler.determine_severity("Access Denied") == (13, "WARN")

    def test_error_occurred_returns_warn(self):
        assert handler.determine_severity("Error occurred") == (13, "WARN")

    def test_case_insensitive_failure(self):
        assert handler.determine_severity("FAILURE") == (13, "WARN")
        assert handler.determine_severity("failure") == (13, "WARN")
        assert handler.determine_severity("FaIlUrE") == (13, "WARN")

    def test_none_returns_info(self):
        assert handler.determine_severity(None) == (9, "INFO")

    def test_empty_returns_info(self):
        assert handler.determine_severity("") == (9, "INFO")

    def test_partial_match(self):
        assert handler.determine_severity("failed to connect") == (13, "WARN")
        assert handler.determine_severity("permission denied by policy") == (13, "WARN")


class TestTimestampToUnixNano:
    """Tests for timestamp_to_unix_nano function."""

    def test_valid_iso8601_utc(self):
        result = handler.timestamp_to_unix_nano("2026-01-15T12:00:01Z")
        # 2026-01-15T12:00:01Z in nanoseconds
        expected_seconds = datetime(2026, 1, 15, 12, 0, 1, tzinfo=timezone.utc).timestamp()
        expected_nano = str(int(expected_seconds * 1_000_000_000))
        assert result == expected_nano

    def test_valid_iso8601_with_offset(self):
        result = handler.timestamp_to_unix_nano("2026-01-15T21:00:01+09:00")
        # Same as 2026-01-15T12:00:01Z
        expected_seconds = datetime(2026, 1, 15, 12, 0, 1, tzinfo=timezone.utc).timestamp()
        expected_nano = str(int(expected_seconds * 1_000_000_000))
        assert result == expected_nano

    def test_none_returns_current_time(self):
        before = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        result = int(handler.timestamp_to_unix_nano(None))
        after = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        assert before <= result <= after

    def test_empty_returns_current_time(self):
        before = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        result = int(handler.timestamp_to_unix_nano(""))
        after = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        assert before <= result <= after

    def test_invalid_returns_current_time(self):
        before = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        result = int(handler.timestamp_to_unix_nano("not-a-timestamp"))
        after = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        assert before <= result <= after


class TestMapLogRecord:
    """Tests for map_log_record function."""

    def test_all_fields_present(self):
        log = {
            "Timestamp": "2026-01-15T12:00:01Z",
            "EventID": "4663",
            "SVMName": "svm-prod-01",
            "UserName": "admin@corp.local",
            "ClientIP": "10.0.1.50",
            "Operation": "ReadData",
            "ObjectName": "/vol/data/file.txt",
            "Result": "Success",
        }
        record = handler.map_log_record(log)

        attr_map = {a["key"]: a["value"]["stringValue"] for a in record["attributes"]}
        assert attr_map["event.type"] == "4663"
        assert attr_map["user.name"] == "admin@corp.local"
        assert attr_map["client.address"] == "10.0.1.50"
        assert attr_map["fsxn.operation"] == "ReadData"
        assert attr_map["fsxn.path"] == "/vol/data/file.txt"
        assert attr_map["fsxn.result"] == "Success"
        assert attr_map["fsxn.svm"] == "svm-prod-01"

    def test_absent_fields_omitted(self):
        log = {"Timestamp": "2026-01-15T12:00:01Z", "Result": "Success"}
        record = handler.map_log_record(log)

        attr_keys = {a["key"] for a in record["attributes"]}
        assert "event.type" not in attr_keys
        assert "user.name" not in attr_keys
        assert "client.address" not in attr_keys
        assert "fsxn.operation" not in attr_keys
        assert "fsxn.path" not in attr_keys
        # Result is present
        assert "fsxn.result" in attr_keys

    def test_empty_fields_omitted(self):
        log = {
            "EventID": "",
            "UserName": "",
            "ClientIP": "",
            "Operation": "",
            "ObjectName": "",
            "Result": "",
            "SVMName": "",
        }
        record = handler.map_log_record(log)
        assert record["attributes"] == []

    def test_severity_in_record(self):
        log = {"Result": "Failure"}
        record = handler.map_log_record(log)
        assert record["severityNumber"] == 13
        assert record["severityText"] == "WARN"

    def test_body_contains_json(self):
        log = {"EventID": "4663", "Operation": "ReadData"}
        record = handler.map_log_record(log)
        body = json.loads(record["body"]["stringValue"])
        assert body["EventID"] == "4663"


class TestBuildOtlpPayload:
    """Tests for build_otlp_payload function."""

    def test_resource_attributes_present(self):
        logs = [{"EventID": "4663", "Result": "Success"}]
        payload = handler.build_otlp_payload(logs, "fsxn-audit", "test.json")

        resource_attrs = payload["resourceLogs"][0]["resource"]["attributes"]
        attr_map = {a["key"]: a["value"]["stringValue"] for a in resource_attrs}
        assert attr_map["service.name"] == "fsxn-audit"
        assert attr_map["cloud.provider"] == "aws"
        assert attr_map["cloud.platform"] == "aws_fsx"

    def test_scope_metadata(self):
        logs = [{"EventID": "4663"}]
        payload = handler.build_otlp_payload(logs, "fsxn-audit", "test.json")

        scope = payload["resourceLogs"][0]["scopeLogs"][0]["scope"]
        assert scope["name"] == "fsxn-otel-shipper"
        assert scope["version"] == "1.0.0"

    def test_empty_input(self):
        payload = handler.build_otlp_payload([], "fsxn-audit", "test.json")
        log_records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        assert log_records == []

    def test_multiple_logs(self):
        logs = [{"EventID": str(i)} for i in range(5)]
        payload = handler.build_otlp_payload(logs, "fsxn-audit", "test.json")
        log_records = payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        assert len(log_records) == 5


class TestSendOtlpPayload:
    """Tests for _send_otlp_payload function."""

    @patch("handler.http")
    def test_successful_send(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        payload = {"resourceLogs": []}
        result = handler._send_otlp_payload(payload, "http://localhost:4318")

        assert result is True
        mock_http.request.assert_called_once()

    @patch("handler.http")
    def test_retry_on_server_error(self, mock_http):
        mock_error = MagicMock()
        mock_error.status = 500
        mock_error.data = b"Internal Server Error"

        mock_success = MagicMock()
        mock_success.status = 200

        mock_http.request.side_effect = [mock_error, mock_success]

        with patch("handler.time.sleep"):
            result = handler._send_otlp_payload(
                {"resourceLogs": []}, "http://localhost:4318"
            )

        assert result is True
        assert mock_http.request.call_count == 2

    @patch("handler.http")
    def test_no_retry_on_client_error(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 403
        mock_response.data = b"Forbidden"
        mock_http.request.return_value = mock_response

        result = handler._send_otlp_payload(
            {"resourceLogs": []}, "http://localhost:4318"
        )

        assert result is False
        assert mock_http.request.call_count == 1

    @patch("handler.http")
    def test_retry_on_rate_limit(self, mock_http):
        mock_rate_limit = MagicMock()
        mock_rate_limit.status = 429
        mock_rate_limit.headers = {"Retry-After": "1"}

        mock_success = MagicMock()
        mock_success.status = 200

        mock_http.request.side_effect = [mock_rate_limit, mock_success]

        with patch("handler.time.sleep"):
            result = handler._send_otlp_payload(
                {"resourceLogs": []}, "http://localhost:4318"
            )

        assert result is True

    @patch("handler.http")
    def test_max_retries_exhausted(self, mock_http):
        mock_error = MagicMock()
        mock_error.status = 500
        mock_error.data = b"Error"
        mock_http.request.return_value = mock_error

        with patch("handler.time.sleep"):
            result = handler._send_otlp_payload(
                {"resourceLogs": []}, "http://localhost:4318"
            )

        assert result is False
        assert mock_http.request.call_count == 3


class TestParseJsonLogs:
    """Tests for _parse_json_logs function."""

    def test_newline_delimited_json(self):
        data = '{"EventID":"4663"}\n{"EventID":"4656"}'
        events = handler._parse_json_logs(data)
        assert len(events) == 2

    def test_json_array(self):
        data = json.dumps([{"event": "test1"}, {"event": "test2"}])
        events = handler._parse_json_logs(data)
        assert len(events) == 2

    def test_empty_input(self):
        events = handler._parse_json_logs("")
        assert len(events) == 0

    def test_invalid_json_lines_skipped(self):
        data = '{"valid": true}\nnot json\n{"also_valid": true}'
        events = handler._parse_json_logs(data)
        assert len(events) == 2


class TestLambdaHandler:
    """Integration tests for the full Lambda handler."""

    @patch("handler.http")
    @patch("handler.s3_client")
    @patch("handler.secrets_client")
    def test_full_flow(self, mock_secrets, mock_s3, mock_http, sample_s3_event, sample_json_audit_logs):
        handler._api_key_cache = None

        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"api_key": "test-token"})
        }

        mock_body = MagicMock()
        mock_body.read.return_value = sample_json_audit_logs.encode("utf-8")
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        result = handler.lambda_handler(sample_s3_event, None)

        assert result["statusCode"] == 200
        assert result["body"]["total_logs"] == 3
        assert result["body"]["total_shipped"] == 3
        assert result["body"]["errors"] == []

    @patch("handler.http")
    @patch("handler.s3_client")
    @patch("handler.secrets_client")
    def test_s3_read_error(self, mock_secrets, mock_s3, mock_http, sample_s3_event):
        handler._api_key_cache = None

        mock_secrets.get_secret_value.return_value = {
            "SecretString": "test-token"
        }

        from botocore.exceptions import ClientError
        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "GetObject",
        )

        result = handler.lambda_handler(sample_s3_event, None)

        assert result["statusCode"] == 502
        assert len(result["body"]["errors"]) == 1

    @patch("handler.http")
    @patch("handler.s3_client")
    @patch("handler.secrets_client")
    def test_otlp_delivery_failure(self, mock_secrets, mock_s3, mock_http, sample_s3_event, sample_json_audit_logs):
        handler._api_key_cache = None

        mock_secrets.get_secret_value.return_value = {
            "SecretString": "test-token"
        }

        mock_body = MagicMock()
        mock_body.read.return_value = sample_json_audit_logs.encode("utf-8")
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.data = b"Server Error"
        mock_http.request.return_value = mock_response

        with patch("handler.time.sleep"):
            result = handler.lambda_handler(sample_s3_event, None)

        assert result["statusCode"] == 502
        assert result["body"]["total_shipped"] == 0
