"""Unit tests for Grafana Loki log shipper."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
import handler


class TestFormatForLoki:
    def test_basic_structure(self, sample_logs):
        logs = [json.loads(l) for l in sample_logs.strip().split("\n")]
        result = handler._format_for_loki(logs, "audit/test.json")
        assert "streams" in result
        assert len(result["streams"]) == 1  # same SVM
        stream = result["streams"][0]
        assert stream["stream"]["job"] == "fsxn-audit"
        assert stream["stream"]["svm"] == "svm-prod-01"
        assert len(stream["values"]) == 2

    def test_multiple_svms(self):
        logs = [
            {"SVMName": "svm-a", "timestamp": "2026-01-15T12:00:01Z", "msg": "a"},
            {"SVMName": "svm-b", "timestamp": "2026-01-15T12:00:02Z", "msg": "b"},
        ]
        result = handler._format_for_loki(logs, "test.json")
        assert len(result["streams"]) == 2

    def test_values_sorted_by_timestamp(self):
        logs = [
            {"SVMName": "svm", "timestamp": "2026-01-15T12:00:05Z"},
            {"SVMName": "svm", "timestamp": "2026-01-15T12:00:01Z"},
        ]
        result = handler._format_for_loki(logs, "test.json")
        values = result["streams"][0]["values"]
        assert int(values[0][0]) < int(values[1][0])


class TestSendLokiPush:
    @patch("handler.http")
    def test_success_204(self, mock_http):
        mock_http.request.return_value = MagicMock(status=204)
        assert handler._send_loki_push({"streams": []}, "Basic abc") is True

    @patch("handler.http")
    def test_gzip_and_auth(self, mock_http):
        mock_http.request.return_value = MagicMock(status=204)
        handler._send_loki_push({"streams": []}, "Basic abc123")
        headers = mock_http.request.call_args[1]["headers"]
        assert headers["Content-Encoding"] == "gzip"
        assert headers["Authorization"] == "Basic abc123"

    @patch("handler.http")
    def test_retry_on_500(self, mock_http):
        mock_500 = MagicMock(status=500, data=b"error")
        mock_ok = MagicMock(status=204)
        mock_http.request.side_effect = [mock_500, mock_ok]
        with patch("handler.time.sleep"):
            assert handler._send_loki_push({"streams": []}, "Basic x") is True
