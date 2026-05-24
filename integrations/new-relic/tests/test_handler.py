"""Unit tests for New Relic log shipper."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
import handler


class TestFormatForNewRelic:
    def test_basic_formatting(self):
        logs = [{"EventID": "4663", "SVMName": "svm-01", "UserName": "admin",
                 "Operation": "ReadData", "timestamp": "2026-01-15T12:00:00Z"}]
        result = handler._format_for_new_relic(logs, "audit/test.json")
        assert len(result) == 1
        assert result[0]["attributes"]["source"] == "fsxn-ontap"
        assert result[0]["attributes"]["event_type"] == "4663"
        assert result[0]["timestamp"] == 1768478400000  # 2026-01-15T12:00:00Z in ms

    def test_empty_logs(self):
        assert handler._format_for_new_relic([], "test.json") == []


class TestSendBatch:
    @patch("handler.http")
    def test_success(self, mock_http):
        mock_resp = MagicMock(status=202)
        mock_http.request.return_value = mock_resp
        payload = [{"common": {}, "logs": [{"message": "test"}]}]
        assert handler._send_batch(payload, "test-key") is True

    @patch("handler.http")
    def test_retry_on_429(self, mock_http):
        mock_429 = MagicMock(status=429)
        mock_ok = MagicMock(status=202)
        mock_http.request.side_effect = [mock_429, mock_ok]
        with patch("handler.time.sleep"):
            assert handler._send_batch([{"logs": []}], "key") is True

    @patch("handler.http")
    def test_fail_on_403(self, mock_http):
        mock_resp = MagicMock(status=403, data=b"Forbidden")
        mock_http.request.return_value = mock_resp
        assert handler._send_batch([{"logs": []}], "bad-key") is False


class TestLambdaHandler:
    @patch("handler.http")
    @patch("handler.s3_client")
    @patch("handler.secrets_client")
    def test_full_flow(self, mock_secrets, mock_s3, mock_http, sample_s3_event, sample_logs):
        handler._api_key_cache = None
        mock_secrets.get_secret_value.return_value = {"SecretString": "nr-license-key"}
        mock_body = MagicMock()
        mock_body.read.return_value = sample_logs.encode()
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_http.request.return_value = MagicMock(status=202)

        result = handler.lambda_handler(sample_s3_event, None)
        assert result["statusCode"] == 200
        assert result["body"]["total_logs"] == 2
        assert result["body"]["total_shipped"] == 2
