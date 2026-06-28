import json, sys
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))
sys.modules.pop("handler", None)
import handler

class TestFormatEvent:
    def test_basic(self):
        log = {"EventID": "4663", "SVMName": "svm-01", "UserName": "admin",
               "Operation": "ReadData", "timestamp": "2026-01-15T12:00:00Z"}
        event = handler._format_event(log, "audit/test.json")
        assert event["data"]["source"] == "fsxn-ontap"
        assert event["data"]["event_type"] == "4663"
        assert event["time"] == "2026-01-15T12:00:00Z"

    def test_no_timestamp(self):
        event = handler._format_event({"message": "raw"}, "test.json")
        assert "time" not in event

class TestSendBatch:
    @patch("handler.http")
    def test_success(self, mock_http):
        mock_http.request.return_value = MagicMock(status=200)
        events = [{"data": {"msg": "test"}}]
        assert handler._send_batch(events, "hc-team-key") is True
        call = mock_http.request.call_args
        assert call[1]["headers"]["X-Honeycomb-Team"] == "hc-team-key"
        assert "/1/batch/fsxn-audit" in call[0][1]

    @patch("handler.http")
    def test_batch_size_100(self, mock_http):
        mock_http.request.return_value = MagicMock(status=200)
        events = [{"data": {"i": i}} for i in range(100)]
        handler._send_batch(events, "key")
        body = json.loads(mock_http.request.call_args[1]["body"])
        assert len(body) == 100
