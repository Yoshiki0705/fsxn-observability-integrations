"""Unit tests for Splunk Serverless log shipper."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
import handler


class TestFormatForSplunk:
    def test_basic_formatting(self):
        logs = [{"EventID": "4663", "SVMName": "svm-01", "UserName": "admin",
                 "Operation": "ReadData", "timestamp": "2026-01-15T12:00:00Z"}]
        result = handler._format_for_splunk(logs, "audit/test.json")
        assert len(result) == 1
        assert result[0]["sourcetype"] == "fsxn:ontap:audit"
        assert result[0]["index"] == "fsxn_audit"
        assert result[0]["host"] == "svm-01"
        assert result[0]["event"]["event_type"] == "4663"
        assert result[0]["time"] is not None

    def test_missing_timestamp(self):
        logs = [{"EventID": "4663", "SVMName": "svm-01"}]
        result = handler._format_for_splunk(logs, "test.json")
        assert "time" not in result[0]


class TestToEpoch:
    def test_iso_with_z(self):
        result = handler._to_epoch("2026-01-15T12:00:00Z")
        assert result is not None
        assert result > 0

    def test_invalid(self):
        assert handler._to_epoch("not-a-date") is None


class TestSendBatch:
    @patch("handler.http")
    def test_success(self, mock_http):
        mock_resp = MagicMock(status=200, data=b'{"text":"Success","code":0}')
        mock_http.request.return_value = mock_resp
        batch = [{"event": {"msg": "test"}, "sourcetype": "test"}]
        assert handler._send_batch(batch, "hec-token") is True

        # Verify Authorization header
        call_args = mock_http.request.call_args
        assert "Splunk hec-token" in call_args[1]["headers"]["Authorization"]

    @patch("handler.http")
    def test_retry_on_503(self, mock_http):
        mock_503 = MagicMock(status=503, data=b'{"text":"Server busy","code":9}')
        mock_ok = MagicMock(status=200, data=b'{"text":"Success","code":0}')
        mock_http.request.side_effect = [mock_503, mock_ok]
        with patch("handler.time.sleep"):
            assert handler._send_batch([{"event": {}}], "token") is True

    @patch("handler.http")
    def test_hec_newline_delimited(self, mock_http):
        """Verify HEC payload is newline-delimited JSON, not an array."""
        mock_http.request.return_value = MagicMock(status=200, data=b'{"code":0}')
        batch = [{"event": {"a": 1}}, {"event": {"b": 2}}]
        handler._send_batch(batch, "token")

        body = mock_http.request.call_args[1]["body"].decode()
        lines = body.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"]["a"] == 1
