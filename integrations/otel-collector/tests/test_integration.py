"""Integration tests for OTLP payload end-to-end pipeline.

Tests the full flow: sample S3 event → parse → map → build OTLP payload
→ validate structure. Mocks S3 and HTTP, verifies payload structure.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))

import handler


class TestEndToEndPipeline:
    """Test full pipeline from S3 event to OTLP payload."""

    def test_sample_audit_logs_produce_valid_otlp(self):
        """Sample audit logs produce structurally valid OTLP payload."""
        test_data_path = Path(__file__).parent / "test_data" / "sample_audit_logs.json"
        data = test_data_path.read_text(encoding="utf-8")

        logs = handler._parse_json_logs(data)
        assert len(logs) == 6

        payload = handler.build_otlp_payload(logs, "fsxn-audit", "audit/test.json")

        # Validate structure
        assert "resourceLogs" in payload
        resource_log = payload["resourceLogs"][0]

        # Resource attributes
        attr_map = {
            a["key"]: a["value"]["stringValue"]
            for a in resource_log["resource"]["attributes"]
        }
        assert attr_map["service.name"] == "fsxn-audit"
        assert attr_map["cloud.provider"] == "aws"
        assert attr_map["cloud.platform"] == "aws_fsx"

        # Log records
        log_records = resource_log["scopeLogs"][0]["logRecords"]
        assert len(log_records) == 6

        # First record should have all fields mapped
        first_record = log_records[0]
        first_attrs = {a["key"]: a["value"]["stringValue"] for a in first_record["attributes"]}
        assert first_attrs["event.type"] == "4663"
        assert first_attrs["user.name"] == "admin@corp.local"
        assert first_attrs["client.address"] == "10.0.1.50"
        assert first_attrs["fsxn.operation"] == "ReadData"
        assert first_attrs["fsxn.path"] == "/vol/data/reports/quarterly.xlsx"
        assert first_attrs["fsxn.result"] == "Success"
        assert first_attrs["fsxn.svm"] == "svm-prod-01"
        assert first_record["severityNumber"] == 9
        assert first_record["severityText"] == "INFO"

        # Third record (Failure) should be WARN
        third_record = log_records[2]
        assert third_record["severityNumber"] == 13
        assert third_record["severityText"] == "WARN"

        # Fourth record (Access Denied) should be WARN
        fourth_record = log_records[3]
        assert fourth_record["severityNumber"] == 13
        assert fourth_record["severityText"] == "WARN"

        # Fifth record (missing UserName, ClientIP) should omit those attributes
        fifth_record = log_records[4]
        fifth_attrs = {a["key"] for a in fifth_record["attributes"]}
        assert "user.name" not in fifth_attrs
        assert "client.address" not in fifth_attrs

        # Sixth record (all empty strings) should have no attributes
        sixth_record = log_records[5]
        assert sixth_record["attributes"] == []

    @patch("handler.http")
    @patch("handler.s3_client")
    def test_full_lambda_invocation_with_sample_data(self, mock_s3, mock_http):
        """Full Lambda invocation with sample data produces correct response."""
        handler._api_key_cache = None

        test_data_path = Path(__file__).parent / "test_data" / "sample_audit_logs.json"
        data = test_data_path.read_bytes()

        # Mock S3
        mock_body = MagicMock()
        mock_body.read.return_value = data
        mock_s3.get_object.return_value = {"Body": mock_body}

        # Mock HTTP (OTLP endpoint)
        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        # Load sample event
        event_path = Path(__file__).parent / "test_data" / "sample_s3_event.json"
        event = json.loads(event_path.read_text())

        with patch.dict("os.environ", {"API_KEY_SECRET_ARN": ""}):
            handler.API_KEY_SECRET_ARN = ""
            result = handler.lambda_handler(event, None)
            handler.API_KEY_SECRET_ARN = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:otel-auth"

        assert result["statusCode"] == 200
        assert result["body"]["total_logs"] == 6
        assert result["body"]["total_shipped"] == 6

        # Verify the OTLP payload was sent
        mock_http.request.assert_called_once()
        call_args = mock_http.request.call_args

        # Verify it was a POST to /v1/logs
        assert call_args[0][0] == "POST"
        assert "/v1/logs" in call_args[0][1]

        # Verify payload structure
        sent_body = json.loads(call_args[1]["body"])
        assert "resourceLogs" in sent_body

    @patch("handler.http")
    @patch("handler.s3_client")
    def test_otlp_payload_sent_to_correct_endpoint(self, mock_s3, mock_http):
        """OTLP payload is sent to the configured endpoint."""
        handler._api_key_cache = None

        mock_body = MagicMock()
        mock_body.read.return_value = b'{"EventID":"4663","Result":"Success"}'
        mock_s3.get_object.return_value = {"Body": mock_body}

        mock_response = MagicMock()
        mock_response.status = 200
        mock_http.request.return_value = mock_response

        event = {
            "Records": [
                {"s3": {"bucket": {"name": "b"}, "object": {"key": "k.json"}}}
            ]
        }

        with patch.dict("os.environ", {"API_KEY_SECRET_ARN": "", "OTLP_ENDPOINT": "http://test-collector:4318"}):
            handler.API_KEY_SECRET_ARN = ""
            handler.OTLP_ENDPOINT = "http://test-collector:4318"
            result = handler.lambda_handler(event, None)
            handler.API_KEY_SECRET_ARN = "arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:otel-auth"
            handler.OTLP_ENDPOINT = "http://localhost:4318"

        assert result["statusCode"] == 200
        call_url = mock_http.request.call_args[0][1]
        assert call_url == "http://test-collector:4318/v1/logs"
