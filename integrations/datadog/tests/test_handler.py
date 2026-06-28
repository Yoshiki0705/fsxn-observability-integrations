"""Unit tests for Datadog log shipper Lambda handler."""

import gzip
import json
import sys
from io import BytesIO
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
                {
                    "s3": {
                        "bucket": {"name": "bucket1"},
                        "object": {"key": "key1.json"},
                    }
                },
                {
                    "s3": {
                        "bucket": {"name": "bucket2"},
                        "object": {"key": "key2.json"},
                    }
                },
            ]
        }
        records = handler._extract_s3_records(event)
        assert len(records) == 2


class TestParseJsonLogs:
    """Tests for _parse_json_logs function."""

    def test_newline_delimited_json(self, sample_json_audit_logs):
        events = handler._parse_json_logs(sample_json_audit_logs)
        assert len(events) == 3
        assert events[0]["EventID"] == "4663"
        assert events[0]["SVMName"] == "svm-prod-01"

    def test_json_array(self):
        logs = json.dumps([{"event": "test1"}, {"event": "test2"}])
        events = handler._parse_json_logs(logs)
        assert len(events) == 2

    def test_single_json_object(self):
        log = json.dumps({"event": "single"})
        events = handler._parse_json_logs(log)
        assert len(events) == 1

    def test_empty_input(self):
        events = handler._parse_json_logs("")
        assert len(events) == 0

    def test_invalid_json_lines_skipped(self):
        data = '{"valid": true}\nnot json\n{"also_valid": true}'
        events = handler._parse_json_logs(data)
        assert len(events) == 2


class TestFormatForDatadog:
    """Tests for _format_for_datadog function."""

    def test_basic_formatting(self):
        logs = [
            {
                "timestamp": "2026-01-15T12:00:01Z",
                "EventID": "4663",
                "SVMName": "svm-prod-01",
                "UserName": "admin@corp.local",
                "ClientIP": "10.0.1.50",
                "Operation": "ReadData",
                "ObjectName": "/vol/data/file.txt",
                "Result": "Success",
            }
        ]
        result = handler._format_for_datadog(logs, "audit/test.json")

        assert len(result) == 1
        dd_log = result[0]
        assert dd_log["ddsource"] == "fsxn"
        assert dd_log["service"] == "ontap-audit"
        assert dd_log["hostname"] == "svm-prod-01"
        assert dd_log["date"] == "2026-01-15T12:00:01Z"
        assert "source:fsxn" in dd_log["ddtags"]
        assert dd_log["attributes"]["event_type"] == "4663"
        assert dd_log["attributes"]["user"] == "admin@corp.local"
        assert dd_log["attributes"]["operation"] == "ReadData"

    def test_missing_fields(self):
        logs = [{"message": "raw log line"}]
        result = handler._format_for_datadog(logs, "test.json")

        assert len(result) == 1
        assert result[0]["message"] == "raw log line"
        assert result[0]["hostname"] == "fsxn-ontap"

    def test_empty_logs(self):
        result = handler._format_for_datadog([], "test.json")
        assert len(result) == 0


class TestCreateBatches:
    """Tests for _create_batches function."""

    def test_single_batch(self):
        logs = [{"message": f"log {i}"} for i in range(10)]
        batches = handler._create_batches(logs)
        assert len(batches) == 1
        assert len(batches[0]) == 10

    def test_max_items_split(self):
        logs = [{"message": f"log {i}"} for i in range(1500)]
        batches = handler._create_batches(logs)
        assert len(batches) == 2
        assert len(batches[0]) == 1000
        assert len(batches[1]) == 500

    def test_size_limit_split(self):
        # Create logs that exceed 5MB total
        large_message = "x" * 10000
        logs = [{"message": large_message} for _ in range(600)]
        batches = handler._create_batches(logs)
        assert len(batches) > 1

    def test_empty_input(self):
        batches = handler._create_batches([])
        assert len(batches) == 0


class TestSendBatch:
    """Tests for _send_batch function."""

    @patch("handler.http")
    def test_successful_send(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 202
        mock_http.request.return_value = mock_response

        logs = [{"message": "test log"}]
        result = handler._send_batch(logs, "test-api-key")

        assert result is True
        mock_http.request.assert_called_once()

        # Verify headers
        call_kwargs = mock_http.request.call_args
        headers = call_kwargs[1]["headers"] if "headers" in call_kwargs[1] else call_kwargs[0][3]
        assert headers["DD-API-KEY"] == "test-api-key"
        assert headers["Content-Type"] == "application/json"

    @patch("handler.http")
    def test_retry_on_server_error(self, mock_http):
        mock_error = MagicMock()
        mock_error.status = 500
        mock_error.data = b"Internal Server Error"

        mock_success = MagicMock()
        mock_success.status = 202

        mock_http.request.side_effect = [mock_error, mock_success]

        with patch("handler.time.sleep"):
            result = handler._send_batch([{"message": "test"}], "key")

        assert result is True
        assert mock_http.request.call_count == 2

    @patch("handler.http")
    def test_no_retry_on_client_error(self, mock_http):
        mock_response = MagicMock()
        mock_response.status = 403
        mock_response.data = b"Forbidden"
        mock_http.request.return_value = mock_response

        result = handler._send_batch([{"message": "test"}], "bad-key")

        assert result is False
        assert mock_http.request.call_count == 1

    @patch("handler.http")
    def test_retry_on_rate_limit(self, mock_http):
        mock_rate_limit = MagicMock()
        mock_rate_limit.status = 429
        mock_rate_limit.headers = {"Retry-After": "1"}

        mock_success = MagicMock()
        mock_success.status = 202

        mock_http.request.side_effect = [mock_rate_limit, mock_success]

        with patch("handler.time.sleep"):
            result = handler._send_batch([{"message": "test"}], "key")

        assert result is True

    @patch("handler.http")
    def test_max_retries_exhausted(self, mock_http):
        mock_error = MagicMock()
        mock_error.status = 500
        mock_error.data = b"Error"
        mock_http.request.return_value = mock_error

        with patch("handler.time.sleep"):
            result = handler._send_batch([{"message": "test"}], "key")

        assert result is False
        assert mock_http.request.call_count == 3


class TestGetApiKey:
    """Tests for get_api_key function."""

    def test_json_format(self, mock_boto3_clients):
        # Reset cache
        handler._api_key_cache = None
        key = handler.get_api_key()
        assert key == "test-dd-api-key-12345"

    def test_plain_string_format(self, mock_boto3_clients):
        handler._api_key_cache = None
        mock_boto3_clients["secrets"].get_secret_value.return_value = {
            "SecretString": "plain-api-key-67890"
        }
        key = handler.get_api_key()
        assert key == "plain-api-key-67890"

    def test_caching(self, mock_boto3_clients):
        handler._api_key_cache = None
        handler.get_api_key()
        handler.get_api_key()
        # Should only call Secrets Manager once due to caching
        mock_boto3_clients["secrets"].get_secret_value.assert_called_once()


class TestLambdaHandler:
    """Integration tests for the full Lambda handler."""

    @patch("handler.http")
    @patch("handler.s3_client")
    @patch("handler.secrets_client")
    def test_full_flow(self, mock_secrets, mock_s3, mock_http, sample_s3_event, sample_json_audit_logs):
        # Reset cache
        handler._api_key_cache = None

        # Mock Secrets Manager
        mock_secrets.get_secret_value.return_value = {
            "SecretString": json.dumps({"api_key": "test-key"})
        }

        # Mock S3
        mock_body = MagicMock()
        mock_body.read.return_value = sample_json_audit_logs.encode("utf-8")
        mock_s3.get_object.return_value = {"Body": mock_body}

        # Mock HTTP (Datadog API)
        mock_response = MagicMock()
        mock_response.status = 202
        mock_http.request.return_value = mock_response

        # Execute
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
            "SecretString": "test-key"
        }

        # S3 raises an error
        from botocore.exceptions import ClientError
        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "GetObject",
        )

        result = handler.lambda_handler(sample_s3_event, None)

        assert result["statusCode"] == 207
        assert len(result["body"]["errors"]) == 1
