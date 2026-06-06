"""Unit tests for CrowdStrike Falcon LogScale handler."""

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add handler to path
HANDLER_DIR = Path(__file__).resolve().parent.parent / "lambda"
sys.path.insert(0, str(HANDLER_DIR))


@pytest.fixture
def reset_handler():
    """Import handler fresh for each test."""
    if "handler" in sys.modules:
        del sys.modules["handler"]
    import handler
    handler._token_cache = None
    return handler


class TestParseXml:
    """Tests for XML audit log parsing."""

    def test_parse_valid_xml(self, reset_handler, sample_xml_audit_log):
        handler = reset_handler
        events = handler._parse_xml(sample_xml_audit_log)
        assert len(events) == 1
        assert events[0]["event_type"] == "4663"
        assert events[0]["user"] == "CORP\\testuser"
        assert events[0]["path"] == "/share/test/document.xlsx"
        assert events[0]["svm"] == "TestSVM"
        assert events[0]["client_ip"] == "10.0.1.100"
        assert events[0]["result"] == "Audit Success"

    def test_parse_empty_xml(self, reset_handler):
        handler = reset_handler
        events = handler._parse_xml("<Events></Events>")
        assert len(events) == 0

    def test_parse_invalid_xml(self, reset_handler):
        handler = reset_handler
        events = handler._parse_xml("not xml at all")
        assert len(events) == 0


class TestParseJson:
    """Tests for JSON audit log parsing."""

    def test_parse_newline_delimited(self, reset_handler, sample_json_audit_logs):
        handler = reset_handler
        events = handler._parse_json(sample_json_audit_logs)
        assert len(events) == 2
        assert events[0]["event_type"] == "4663"
        assert events[1]["event_type"] == "4656"

    def test_parse_json_array(self, reset_handler):
        handler = reset_handler
        data = json.dumps([{"EventID": "4663", "UserName": "user1"}, {"EventID": "4656", "UserName": "user2"}])
        events = handler._parse_json(data)
        assert len(events) == 2

    def test_parse_empty(self, reset_handler):
        handler = reset_handler
        events = handler._parse_json("")
        assert len(events) == 0


class TestFormatForLogscale:
    """Tests for HEC format generation."""

    def test_basic_formatting(self, reset_handler):
        handler = reset_handler
        logs = [{"timestamp": "2026-06-01T10:00:00Z", "event_type": "4663",
                 "source": "fsxn-ontap", "svm": "TestSVM", "user": "testuser",
                 "client_ip": "10.0.1.100", "operation": "File",
                 "path": "/share/test.xlsx", "result": "Audit Success"}]
        result = handler._format_for_logscale(logs, "audit/test.xml")
        assert len(result) == 1
        assert result[0]["source"] == "fsxn-ontap"
        assert result[0]["sourcetype"] == "fsxn:audit"
        assert result[0]["index"] == "fsxn_audit"
        assert result[0]["event"]["user"] == "testuser"
        assert result[0]["event"]["s3_key"] == "audit/test.xml"
        assert "time" in result[0]  # epoch seconds

    def test_empty_logs(self, reset_handler):
        handler = reset_handler
        result = handler._format_for_logscale([], "test.xml")
        assert len(result) == 0


class TestShipToLogscale:
    """Tests for LogScale HEC delivery."""

    def test_successful_delivery(self, reset_handler):
        handler = reset_handler
        events = [{"event": {"test": "data"}, "source": "fsxn", "sourcetype": "fsxn:audit",
                   "index": "fsxn_audit", "time": "2026-06-01T10:00:00Z", "fields": {}}]

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.data = b'{"text":"Success"}'

        with patch.object(handler.http, "request", return_value=mock_resp) as mock_req:
            result = handler._ship_to_logscale(events, "test-token")
            assert result == 1
            mock_req.assert_called_once()
            call_kwargs = mock_req.call_args
            assert "Bearer test-token" in str(call_kwargs)

    def test_empty_events_returns_zero(self, reset_handler):
        handler = reset_handler
        result = handler._ship_to_logscale([], "test-token")
        assert result == 0

    def test_server_error_retries(self, reset_handler):
        handler = reset_handler
        events = [{"event": {"test": "data"}, "source": "fsxn", "sourcetype": "fsxn:audit",
                   "index": "fsxn_audit", "time": "", "fields": {}}]

        mock_resp_500 = MagicMock(status=500, data=b"Internal Server Error")
        mock_resp_200 = MagicMock(status=200, data=b'{"text":"Success"}')

        with patch.object(handler.http, "request", side_effect=[mock_resp_500, mock_resp_200]):
            with patch("time.sleep"):
                result = handler._ship_to_logscale(events, "test-token")
                assert result == 1


class TestGetIngestToken:
    """Tests for token retrieval from Secrets Manager."""

    def test_plain_string_token(self, reset_handler):
        handler = reset_handler
        with patch.object(handler.secrets_client, "get_secret_value") as mock_get:
            mock_get.return_value = {"SecretString": "plain-token-value"}
            handler._token_cache = None
            token = handler.get_ingest_token()
            assert token == "plain-token-value"

    def test_json_format_token(self, reset_handler):
        handler = reset_handler
        with patch.object(handler.secrets_client, "get_secret_value") as mock_get:
            mock_get.return_value = {"SecretString": json.dumps({"ingest_token": "json-token-123"})}
            handler._token_cache = None
            token = handler.get_ingest_token()
            assert token == "json-token-123"

    def test_token_cached(self, reset_handler):
        handler = reset_handler
        handler._token_cache = "cached-token"
        token = handler.get_ingest_token()
        assert token == "cached-token"
